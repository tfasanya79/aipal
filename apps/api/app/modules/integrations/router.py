"""Third-party integrations (v2.1+) — Spotify OAuth + Spotify Web API playback."""

import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_current_user
from app.shared.config import get_settings
from app.shared.db import get_db
from app.shared.models import IntegrationToken, User

router = APIRouter(prefix="/integrations", tags=["integrations"])
settings = get_settings()
log = logging.getLogger("aipal.spotify")

_oauth_states: dict[str, str] = {}

_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SPOTIFY_API = "https://api.spotify.com/v1"


class SpotifyAuthResponse(BaseModel):
    authorization_url: str
    state: str


class SpotifyCallbackRequest(BaseModel):
    code: str
    state: str


class SpotifyStatusResponse(BaseModel):
    connected: bool
    display_name: str | None = None


class PlayMusicRequest(BaseModel):
    provider: str = "spotify"
    query: str | None = None
    playlist_id: str | None = None
    action: str = "play"  # play | pause | skip | volume_up | volume_down


async def _refresh_spotify_token(db: AsyncSession, tok: IntegrationToken) -> IntegrationToken:
    """Refresh Spotify access token if expired or missing expiry. Mutates tok in place."""
    if tok.expires_at:
        from datetime import UTC, datetime
        if tok.expires_at.replace(tzinfo=None if tok.expires_at.tzinfo is None else tok.expires_at.tzinfo) > __import__('datetime').datetime.now(UTC).replace(tzinfo=None):
            return tok  # still valid
    if not tok.refresh_token:
        raise HTTPException(status_code=401, detail="Spotify token expired and no refresh token — reconnect Spotify")
    import base64
    from datetime import UTC, datetime, timedelta
    creds = base64.b64encode(f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _SPOTIFY_TOKEN_URL,
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": tok.refresh_token},
        )
    if resp.status_code != 200:
        log.warning("Spotify refresh failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=401, detail="Failed to refresh Spotify token — reconnect Spotify")
    data = resp.json()
    tok.access_token = data["access_token"]
    if "refresh_token" in data:
        tok.refresh_token = data["refresh_token"]
    tok.expires_at = datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600))
    await db.commit()
    await db.refresh(tok)
    return tok


async def _spotify_api(
    db: AsyncSession,
    tok: IntegrationToken,
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response:
    tok = await _refresh_spotify_token(db, tok)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.request(
            method,
            f"{_SPOTIFY_API}{path}",
            headers={"Authorization": f"Bearer {tok.access_token}"},
            **kwargs,
        )
    return resp


@router.get("/spotify/authorize", response_model=SpotifyAuthResponse)
async def spotify_authorize(user: User = Depends(get_current_user)):
    if not settings.spotify_client_id:
        raise HTTPException(status_code=501, detail="Spotify not configured on server")
    state = secrets.token_urlsafe(16)
    _oauth_states[state] = str(user.id)
    params = urlencode(
        {
            "client_id": settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": settings.spotify_redirect_uri,
            "scope": "user-read-playback-state user-modify-playback-state streaming",
            "state": state,
        }
    )
    return SpotifyAuthResponse(
        authorization_url=f"https://accounts.spotify.com/authorize?{params}",
        state=state,
    )


@router.post("/spotify/callback")
async def spotify_callback(
    body: SpotifyCallbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import base64
    from datetime import UTC, datetime, timedelta

    expected_user = _oauth_states.pop(body.state, None)
    if expected_user != str(user.id):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    if not settings.spotify_client_secret:
        raise HTTPException(status_code=501, detail="Spotify client secret not configured")

    creds = base64.b64encode(
        f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    ).decode()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            _SPOTIFY_TOKEN_URL,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": body.code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
        )
    if resp.status_code != 200:
        log.warning("Spotify token exchange failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=400, detail="Spotify token exchange failed")
    data = resp.json()

    result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user.id,
            IntegrationToken.provider == "spotify",
        )
    )
    tok = result.scalar_one_or_none()
    expires_at = datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600))
    if tok:
        tok.access_token = data["access_token"]
        tok.refresh_token = data.get("refresh_token")
        tok.expires_at = expires_at
    else:
        db.add(
            IntegrationToken(
                user_id=user.id,
                provider="spotify",
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_at=expires_at,
            )
        )
    await db.commit()
    return {"ok": True, "provider": "spotify"}


@router.get("/spotify/status", response_model=SpotifyStatusResponse)
async def spotify_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user.id,
            IntegrationToken.provider == "spotify",
        )
    )
    tok = result.scalar_one_or_none()
    if not tok:
        return SpotifyStatusResponse(connected=False)
    try:
        resp = await _spotify_api(db, tok, "GET", "/me")
        if resp.status_code == 200:
            return SpotifyStatusResponse(connected=True, display_name=resp.json().get("display_name"))
    except Exception:
        pass
    return SpotifyStatusResponse(connected=True)


@router.delete("/spotify/disconnect")
async def spotify_disconnect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user.id,
            IntegrationToken.provider == "spotify",
        )
    )
    tok = result.scalar_one_or_none()
    if tok:
        await db.delete(tok)
        await db.commit()
    return {"ok": True}


@router.post("/play-music")
async def play_music(
    body: PlayMusicRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.provider != "spotify":
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {body.provider}")

    result = await db.execute(
        select(IntegrationToken).where(
            IntegrationToken.user_id == user.id,
            IntegrationToken.provider == "spotify",
        )
    )
    tok = result.scalar_one_or_none()
    if not tok:
        return {
            "ok": False,
            "message": "Spotify not connected — go to Settings > Integrations to link it",
        }

    action = (body.action or "play").lower()

    # Pause / Skip / Volume controls (no search needed)
    if action == "pause":
        resp = await _spotify_api(db, tok, "PUT", "/me/player/pause")
        return {"ok": resp.status_code in (200, 204), "action": "pause"}

    if action == "skip":
        resp = await _spotify_api(db, tok, "POST", "/me/player/next")
        return {"ok": resp.status_code in (200, 204), "action": "skip"}

    if action == "volume_up":
        player_resp = await _spotify_api(db, tok, "GET", "/me/player")
        vol = 50
        if player_resp.status_code == 200 and player_resp.text:
            vol = min(100, (player_resp.json().get("device", {}).get("volume_percent", 50) or 50) + 20)
        resp = await _spotify_api(db, tok, "PUT", "/me/player/volume", params={"volume_percent": vol})
        return {"ok": resp.status_code in (200, 204), "action": "volume_up", "volume": vol}

    if action == "volume_down":
        player_resp = await _spotify_api(db, tok, "GET", "/me/player")
        vol = 30
        if player_resp.status_code == 200 and player_resp.text:
            vol = max(0, (player_resp.json().get("device", {}).get("volume_percent", 50) or 50) - 20)
        resp = await _spotify_api(db, tok, "PUT", "/me/player/volume", params={"volume_percent": vol})
        return {"ok": resp.status_code in (200, 204), "action": "volume_down", "volume": vol}

    # Play — search if query given, else use playlist_id directly
    if body.playlist_id:
        context_uri = body.playlist_id if body.playlist_id.startswith("spotify:") else f"spotify:playlist:{body.playlist_id}"
        resp = await _spotify_api(db, tok, "PUT", "/me/player/play", json={"context_uri": context_uri})
        return {"ok": resp.status_code in (200, 204), "action": "play", "context": context_uri}

    query = body.query or "focus"
    search_resp = await _spotify_api(db, tok, "GET", "/search", params={"q": query, "type": "playlist", "limit": 1})
    if search_resp.status_code == 200:
        items = search_resp.json().get("playlists", {}).get("items", [])
        if items and items[0]:
            uri = items[0]["uri"]
            resp = await _spotify_api(db, tok, "PUT", "/me/player/play", json={"context_uri": uri})
            return {
                "ok": resp.status_code in (200, 204),
                "action": "play",
                "playlist": items[0].get("name"),
                "context": uri,
            }
    # Fallback: track search
    search_resp = await _spotify_api(db, tok, "GET", "/search", params={"q": query, "type": "track", "limit": 1})
    if search_resp.status_code == 200:
        items = search_resp.json().get("tracks", {}).get("items", [])
        if items and items[0]:
            uri = items[0]["uri"]
            resp = await _spotify_api(db, tok, "PUT", "/me/player/play", json={"uris": [uri]})
            return {
                "ok": resp.status_code in (200, 204),
                "action": "play",
                "track": items[0].get("name"),
            }
    return {"ok": False, "message": f"No Spotify results found for: {query}"}

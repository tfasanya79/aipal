import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import get_settings
from app.shared.db import get_db
from app.shared.models import MagicLinkToken, User

security = HTTPBearer(auto_error=False)
settings = get_settings()


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def create_magic_link(db: AsyncSession, email: str) -> tuple[str, str | None]:
    email = email.strip().lower()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=1)
    db.add(MagicLinkToken(token=token, email=email, expires_at=expires))
    await db.commit()
    dev_token = token if settings.magic_link_dev_return_token else None
    return token, dev_token


async def verify_magic_link(db: AsyncSession, token: str) -> tuple[User, str]:
    result = await db.execute(select(MagicLinkToken).where(MagicLinkToken.token == token))
    row = result.scalar_one_or_none()
    if not row or row.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or used token")
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Token expired")
    row.used_at = datetime.now(UTC)
    result = await db.execute(select(User).where(User.email == row.email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=row.email, wake_name="AiPal")
        db.add(user)
        await db.flush()
    await db.commit()
    await db.refresh(user)
    access = create_access_token(user.id, user.email)
    return user, access


async def google_sign_in(db: AsyncSession, id_token_str: str) -> tuple[User, str]:
    """Verify Google ID token and return (User, jwt_access_token)."""
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    try:
        idinfo = id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), settings.google_client_id
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Google token") from exc
    email = idinfo["email"].strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=email, wake_name="AiPal", auth_provider="google")
        db.add(user)
        await db.flush()
    else:
        if user.auth_provider == "magic_link":
            user.auth_provider = "google"
    await db.commit()
    await db.refresh(user)
    access = create_access_token(user.id, user.email)
    return user, access


async def apple_sign_in(db: AsyncSession, identity_token: str, email: str | None) -> tuple[User, str]:
    """Verify Apple identity token and return (User, jwt_access_token)."""
    import urllib.request
    import json as _json
    from jose import jwt as jose_jwt
    try:
        with urllib.request.urlopen("https://appleid.apple.com/auth/keys") as resp:
            jwks = _json.loads(resp.read())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not reach Apple auth server") from exc
    try:
        header = jose_jwt.get_unverified_header(identity_token)
        key = next((k for k in jwks["keys"] if k["kid"] == header["kid"]), None)
        if key is None:
            raise ValueError("Unknown key ID")
        from jose.backends import RSAKey
        pub = RSAKey(key, algorithm="RS256")
        claims = jose_jwt.decode(
            identity_token,
            pub.public_key().to_pem().decode(),
            algorithms=["RS256"],
            audience=settings.apple_client_id or None,
            options={"verify_aud": bool(settings.apple_client_id)},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Apple token") from exc
    user_email = (claims.get("email") or email or "").strip().lower()
    if not user_email:
        raise HTTPException(status_code=400, detail="Email not provided by Apple")
    result = await db.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=user_email, wake_name="AiPal", auth_provider="apple")
        db.add(user)
        await db.flush()
    else:
        if user.auth_provider == "magic_link":
            user.auth_provider = "apple"
    await db.commit()
    await db.refresh(user)
    access = create_access_token(user.id, user.email)
    return user, access


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth import service
from app.modules.auth.service import create_magic_link, verify_magic_link
from app.shared.db import get_db
from app.shared.schemas import AuthResponse, RegisterRequest, RegisterResponse, VerifyRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    token, dev_token = await create_magic_link(db, body.email)
    return RegisterResponse(dev_token=dev_token, message=f"Magic link created for {body.email}")


@router.post("/verify", response_model=AuthResponse)
async def verify(body: VerifyRequest, db: AsyncSession = Depends(get_db)):
    user, access = await verify_magic_link(db, body.token)
    return AuthResponse(access_token=access, user_id=user.id)


class GoogleSignInRequest(BaseModel):
    id_token: str


class AppleSignInRequest(BaseModel):
    identity_token: str
    email: str | None = None


@router.post("/google", response_model=AuthResponse)
async def google_sign_in_endpoint(
    body: GoogleSignInRequest,
    db: AsyncSession = Depends(get_db),
):
    user, access = await service.google_sign_in(db, body.id_token)
    return AuthResponse(access_token=access, user_id=user.id)


@router.post("/apple", response_model=AuthResponse)
async def apple_sign_in_endpoint(
    body: AppleSignInRequest,
    db: AsyncSession = Depends(get_db),
):
    user, access = await service.apple_sign_in(db, body.identity_token, body.email)
    return AuthResponse(access_token=access, user_id=user.id)

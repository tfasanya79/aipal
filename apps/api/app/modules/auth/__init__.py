"""Auth: magic link, JWT, profile."""

from .router import router
from .profile_router import router as profile_router

__all__ = ["router", "profile_router"]

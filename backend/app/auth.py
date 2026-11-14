from __future__ import annotations
from typing import Optional

from fastapi import Header, HTTPException, status

from .config import get_settings
from .jwt_verifier import verify_token


async def current_user_id(
    authorization: Optional[str] = Header(default=None),
    x_demo_user_id: Optional[str] = Header(default=None),
) -> str:
    """Resolve the authenticated user.

    Production deployments must validate a Clerk bearer token. The demo
    header is intentionally available only in development for seeded demos.
    """
    settings = get_settings()
    if settings.environment == "development" and settings.allow_demo_auth and x_demo_user_id:
        if x_demo_user_id.startswith('user_') and len(x_demo_user_id) > 5:
            return x_demo_user_id
        raise HTTPException(status_code=401, detail="Invalid Clerk demo user id")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    return await verify_token(token, settings)


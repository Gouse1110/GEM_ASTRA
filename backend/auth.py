"""
backend/auth.py
Authentication utilities: password hashing, JWT creation/verification,
FastAPI dependency functions for authenticated and role-gated routes.

Secrets are read from environment variables only — never hardcoded.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

import utils.database as db

# --------------------------------------------------------------------------- #
#  Configuration — from environment, never hardcoded                          #
# --------------------------------------------------------------------------- #

def _require_env(key: str, default: Optional[str] = None) -> str:
    val = os.environ.get(key, default)
    if not val:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and set a secure value."
        )
    return val


def get_jwt_secret() -> str:
    return _require_env("JWT_SECRET", None)


def get_jwt_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def get_jwt_expire_minutes() -> int:
    return int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))


# --------------------------------------------------------------------------- #
#  Password hashing (bcrypt via passlib)                                      #
# --------------------------------------------------------------------------- #

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


# --------------------------------------------------------------------------- #
#  JWT tokens                                                                  #
# --------------------------------------------------------------------------- #

def create_access_token(user_id: str, role: str, email: str) -> str:
    """
    Create a signed JWT containing user_id, role, and email.
    The role comes from the database — not from the frontend request.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=get_jwt_expire_minutes()
    )
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=get_jwt_algorithm())


def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT. Raises HTTPException on failure.
    Returns the payload dict on success.
    """
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[get_jwt_algorithm()],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# --------------------------------------------------------------------------- #
#  FastAPI dependencies                                                        #
# --------------------------------------------------------------------------- #

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Dependency: verify the Bearer token and return the user row from the DB.
    The role is always re-read from the database — never trusted from the token alone.
    """
    payload = decode_token(token)
    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    # Re-fetch from DB to catch deactivated accounts and role changes
    conn = db.get_connection()
    row = conn.execute(
        "SELECT user_id, email, role, org_id, is_active FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )

    return dict(row)


def require_role(*allowed_roles: str):
    """
    Dependency factory: ensure the authenticated user has one of the allowed roles.

    Usage:
        @router.post("/publish")
        def publish(user = Depends(require_role("official", "admin"))):
            ...
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires role: {', '.join(allowed_roles)}.",
            )
        return user
    return _check

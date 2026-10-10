"""
backend/routers/auth.py
Authentication endpoints: login, current-user, and demo-account seeding.

POST /api/auth/login  — exchange credentials for a JWT
GET  /api/auth/me     — return the authenticated user's profile
POST /api/auth/seed-demo — create fictional demo accounts (dev only)

IMPORTANT
---------
- Passwords are never stored in plaintext.
- Hashes are never returned in any API response.
- Roles are read from the database, not from the request.
- Demo accounts use fictional identities only.
- Unrestricted public self-registration as an official is not exposed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

import utils.database as db
from backend.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --------------------------------------------------------------------------- #
#  Response models (no password_hash ever included)                           #
# --------------------------------------------------------------------------- #

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str
    user_id: str


class UserProfile(BaseModel):
    user_id: str
    email: str
    role: str
    org_id: Optional[str] = None
    is_active: bool


class SeedResult(BaseModel):
    message: str
    accounts_created: int
    accounts_skipped: int
    # Credentials shown once at seed time — never stored in plaintext after this
    demo_credentials: list[dict]


# --------------------------------------------------------------------------- #
#  Login                                                                       #
# --------------------------------------------------------------------------- #

@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    """
    Exchange email + password for a signed JWT.
    Returns 401 for wrong credentials; 403 for inactive accounts.
    The response body never contains a password hash.
    """
    conn = db.get_connection()
    row = conn.execute(
        "SELECT user_id, email, password_hash, role, org_id, is_active "
        "FROM users WHERE email = ?",
        (form.username.strip().lower(),)
    ).fetchone()
    conn.close()

    # Constant-time rejection — same code path for unknown user and wrong password
    if row is None or not verify_password(form.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    token = create_access_token(
        user_id=row["user_id"],
        role=row["role"],
        email=row["email"],
    )

    return TokenResponse(
        access_token=token,
        role=row["role"],
        email=row["email"],
        user_id=row["user_id"],
    )


# --------------------------------------------------------------------------- #
#  Current user                                                                #
# --------------------------------------------------------------------------- #

@router.get("/me", response_model=UserProfile)
def me(user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile. Never returns password hash."""
    return UserProfile(
        user_id=user["user_id"],
        email=user["email"],
        role=user["role"],
        org_id=user.get("org_id"),
        is_active=bool(user["is_active"]),
    )


# --------------------------------------------------------------------------- #
#  Demo-account seeding                                                        #
# --------------------------------------------------------------------------- #

_DEMO_ACCOUNTS = [
    {
        "email": "official@gem-astra.demo",
        "password": "Demo@Official1",
        "role": "official",
        "org_name": "GeM Astra Demo — Ministry of Finance",
        "org_type": "government",
    },
    {
        "email": "bidder@gem-astra.demo",
        "password": "Demo@Bidder1",
        "role": "bidder",
        "org_name": "GeM Astra Demo — Acme Supplies Pvt Ltd",
        "org_type": "bidder",
    },
    {
        "email": "reviewer@gem-astra.demo",
        "password": "Demo@Reviewer1",
        "role": "reviewer",
        "org_name": "GeM Astra Demo — Ministry of Finance",
        "org_type": "government",
    },
]


@router.post("/seed-demo", response_model=SeedResult)
def seed_demo():
    """
    Create fictional demo accounts for development and demonstration.
    Safe to call multiple times — skips accounts that already exist.

    IMPORTANT: These are fictional identities for demo purposes only.
    They do not represent real government officials or real organisations.
    Do not use demo credentials in production.
    """
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    skipped = 0
    credentials_shown: list[dict] = []

    conn = db.get_connection()

    # Map org_name → org_id (create org if needed)
    org_cache: dict[str, str] = {}

    for account in _DEMO_ACCOUNTS:
        org_name = account["org_name"]

        # Upsert organisation
        if org_name not in org_cache:
            existing_org = conn.execute(
                "SELECT org_id FROM organisations WHERE name = ?", (org_name,)
            ).fetchone()
            if existing_org:
                org_cache[org_name] = existing_org["org_id"]
            else:
                org_id = f"demo-org-{uuid.uuid4().hex[:8]}"
                conn.execute(
                    "INSERT INTO organisations (org_id, name, org_type, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (org_id, org_name, account["org_type"], now),
                )
                org_cache[org_name] = org_id

        org_id = org_cache[org_name]
        email = account["email"].lower()

        # Skip if user already exists
        existing = conn.execute(
            "SELECT user_id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            skipped += 1
            continue

        user_id = f"demo-user-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO users (user_id, email, password_hash, role, org_id, "
            "is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (user_id, email, hash_password(account["password"]),
             account["role"], org_id, now),
        )
        conn.commit()
        created += 1
        credentials_shown.append({
            "email": email,
            "password": account["password"],  # shown once — never stored plain
            "role": account["role"],
            "note": "DEMO ONLY — fictional identity, not a real government account",
        })

    conn.close()

    return SeedResult(
        message=(
            f"Demo accounts ready. {created} created, {skipped} already existed. "
            "Use credentials below to log in. "
            "These are fictional demo identities only."
        ),
        accounts_created=created,
        accounts_skipped=skipped,
        demo_credentials=credentials_shown,
    )

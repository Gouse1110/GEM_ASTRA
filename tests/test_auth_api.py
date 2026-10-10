"""
tests/test_auth_api.py
Tests for POST /api/auth/login, GET /api/auth/me, POST /api/auth/seed-demo.

Run with: python -m pytest tests/test_auth_api.py -v
"""

import os
import pytest

# JWT_SECRET must be set before importing anything that touches backend.auth
os.environ.setdefault("JWT_SECRET", "test-secret-for-auth-tests-at-least-32-chars")

import uuid
import sqlite3
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
#  Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Isolated DB + TestClient for every test."""
    tmp_db = tmp_path / "auth_test.db"
    import utils.database as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_db)
    db_mod.init_db()
    from backend.main import app
    return TestClient(app)


def _seed(client) -> dict:
    """Seed demo accounts and return the credentials list."""
    r = client.post("/api/auth/seed-demo")
    assert r.status_code == 200
    return r.json()


def _login(client, email: str, password: str):
    return client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


# --------------------------------------------------------------------------- #
#  1. Demo-account seeding                                                     #
# --------------------------------------------------------------------------- #

def test_seed_creates_accounts(client):
    result = _seed(client)
    assert result["accounts_created"] >= 2
    assert result["accounts_skipped"] == 0
    assert len(result["demo_credentials"]) >= 2


def test_seed_is_idempotent(client):
    _seed(client)
    result2 = client.post("/api/auth/seed-demo").json()
    assert result2["accounts_created"] == 0
    assert result2["accounts_skipped"] >= 2


def test_seed_passwords_not_stored_as_plaintext(client, tmp_path, monkeypatch):
    """After seeding, password_hash column must NOT equal the plaintext password."""
    import utils.database as db_mod
    _seed(client)
    conn = sqlite3.connect(str(db_mod.DB_PATH))
    rows = conn.execute("SELECT email, password_hash FROM users").fetchall()
    conn.close()
    for email, pw_hash in rows:
        assert pw_hash != "Demo@Official1", f"Plaintext password stored for {email}"
        assert pw_hash != "Demo@Bidder1",   f"Plaintext password stored for {email}"
        assert pw_hash.startswith("$2"), f"Hash not bcrypt for {email}"


def test_seed_response_never_contains_stored_hash(client):
    """The seed response may show the demo password once, but never the hash."""
    result = _seed(client)
    for cred in result["demo_credentials"]:
        assert "password_hash" not in cred, "Hash must never appear in API response"
        assert "$2b$" not in str(cred), "bcrypt hash must not leak in response"


# --------------------------------------------------------------------------- #
#  2. Successful login                                                         #
# --------------------------------------------------------------------------- #

def test_login_official_succeeds(client):
    _seed(client)
    r = _login(client, "official@gem-astra.demo", "Demo@Official1")
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "official"
    assert data["email"] == "official@gem-astra.demo"


def test_login_bidder_succeeds(client):
    _seed(client)
    r = _login(client, "bidder@gem-astra.demo", "Demo@Bidder1")
    assert r.status_code == 200
    assert r.json()["role"] == "bidder"


def test_login_response_has_no_password_hash(client):
    _seed(client)
    r = _login(client, "official@gem-astra.demo", "Demo@Official1")
    body = r.text
    assert "password_hash" not in body
    assert "$2b$" not in body


# --------------------------------------------------------------------------- #
#  3. Failed login cases                                                       #
# --------------------------------------------------------------------------- #

def test_login_wrong_password(client):
    _seed(client)
    r = _login(client, "official@gem-astra.demo", "wrongpassword")
    assert r.status_code == 401


def test_login_unknown_email(client):
    _seed(client)
    r = _login(client, "nobody@unknown.com", "anypassword")
    assert r.status_code == 401


def test_login_inactive_user(client, tmp_path, monkeypatch):
    """A deactivated account must be rejected with 403."""
    import utils.database as db_mod
    _seed(client)
    conn = sqlite3.connect(str(db_mod.DB_PATH))
    conn.execute(
        "UPDATE users SET is_active=0 WHERE email=?",
        ("official@gem-astra.demo",)
    )
    conn.commit()
    conn.close()
    r = _login(client, "official@gem-astra.demo", "Demo@Official1")
    assert r.status_code == 403


def test_login_case_insensitive_email(client):
    """Email lookup should be case-insensitive."""
    _seed(client)
    r = _login(client, "OFFICIAL@GEM-ASTRA.DEMO", "Demo@Official1")
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
#  4. GET /api/auth/me                                                         #
# --------------------------------------------------------------------------- #

def test_me_returns_profile(client):
    _seed(client)
    token = _login(client, "official@gem-astra.demo", "Demo@Official1").json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "official@gem-astra.demo"
    assert data["role"] == "official"
    assert data["is_active"] is True
    assert "password_hash" not in data


def test_me_without_token_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer notavalidtoken"})
    assert r.status_code == 401


def test_me_with_expired_token_returns_401(client, monkeypatch):
    """A token with exp in the past must be rejected."""
    import backend.auth as auth_mod
    # Monkeypatch expire to -1 minutes (already expired)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "-1")
    _seed(client)
    token = _login(client, "official@gem-astra.demo", "Demo@Official1").json()["access_token"]
    # Token is already expired; /me must reject it
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
#  5. Role-based access                                                        #
# --------------------------------------------------------------------------- #

def test_role_read_from_db_not_token(client, tmp_path, monkeypatch):
    """
    If a user's role is changed in the DB after login, /me must return
    the NEW role — proving it's re-read from the DB, not cached in the token.
    """
    import utils.database as db_mod
    _seed(client)
    token = _login(client, "official@gem-astra.demo", "Demo@Official1").json()["access_token"]

    # Change role in DB
    conn = sqlite3.connect(str(db_mod.DB_PATH))
    conn.execute(
        "UPDATE users SET role='reviewer' WHERE email=?",
        ("official@gem-astra.demo",)
    )
    conn.commit()
    conn.close()

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # Role must reflect DB state, not the original token claim
    assert r.json()["role"] == "reviewer"


def test_deactivated_user_rejected_after_login(client, tmp_path, monkeypatch):
    """
    Even with a valid token, a deactivated account must be rejected by /me.
    """
    import utils.database as db_mod
    _seed(client)
    token = _login(client, "official@gem-astra.demo", "Demo@Official1").json()["access_token"]

    conn = sqlite3.connect(str(db_mod.DB_PATH))
    conn.execute(
        "UPDATE users SET is_active=0 WHERE email=?",
        ("official@gem-astra.demo",)
    )
    conn.commit()
    conn.close()

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  6. Token integrity                                                          #
# --------------------------------------------------------------------------- #

def test_tampered_token_rejected(client):
    _seed(client)
    token = _login(client, "official@gem-astra.demo", "Demo@Official1").json()["access_token"]
    # Flip last character
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


def test_token_signed_with_different_secret_rejected(client, monkeypatch):
    """A token signed with a different secret must be rejected."""
    _seed(client)
    # Create a token with a different secret
    monkeypatch.setenv("JWT_SECRET", "completely-different-secret-value-here-32c")
    import backend.auth as auth_mod
    fake_token = auth_mod.create_access_token("fake", "official", "fake@test.com")

    # Restore original secret
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-auth-tests-at-least-32-chars")

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert r.status_code == 401

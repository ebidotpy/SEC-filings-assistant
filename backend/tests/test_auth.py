from __future__ import annotations

import pytest
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.main import app
from httpx import ASGITransport, AsyncClient


def test_password_hashing():
    raw = "supersecret123"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed)
    assert not verify_password("wrongpassword", hashed)


def test_jwt_token_creation_and_decoding():
    import uuid

    user_id = uuid.uuid4()
    email = "analyst@example.com"
    token = create_access_token(user_id, email)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["email"] == email


@pytest.mark.anyio
async def test_auth_endpoints_flow():
    import uuid

    unique_suffix = uuid.uuid4().hex[:8]
    test_email = f"user_{unique_suffix}@example.com"
    test_password = "password123"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Register
        reg_resp = await client.post(
            "/api/auth/register",
            json={
                "email": test_email,
                "password": test_password,
                "display_name": "Test User",
            },
        )
        assert reg_resp.status_code == 200, reg_resp.text
        data = reg_resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == test_email
        token = data["access_token"]

        # 2. Duplicate register fails
        dup_resp = await client.post(
            "/api/auth/register",
            json={"email": test_email, "password": test_password},
        )
        assert dup_resp.status_code == 400

        # 3. Login with wrong password fails
        bad_login = await client.post(
            "/api/auth/login",
            json={"email": test_email, "password": "wrong"},
        )
        assert bad_login.status_code == 401

        # 4. Login with correct password succeeds
        good_login = await client.post(
            "/api/auth/login",
            json={"email": test_email, "password": test_password},
        )
        assert good_login.status_code == 200
        assert "access_token" in good_login.json()

        # 5. /api/auth/me with bearer token
        me_resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == test_email

        # 6. /api/auth/me without token fails
        unauth_resp = await client.get("/api/auth/me")
        assert unauth_resp.status_code == 401

from __future__ import annotations

import jwt
import pytest
from app.api.auth import RegisterRequest
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError


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


@pytest.mark.parametrize("password", ["x" * 73, "é" * 37, "🔑" * 19])
def test_registration_rejects_passwords_above_bcrypt_byte_limit(password):
    with pytest.raises(ValidationError):
        RegisterRequest(email="analyst@example.com", password=password)


def test_registration_accepts_exactly_72_utf8_bytes():
    request = RegisterRequest(email="analyst@example.com", password="é" * 36)
    assert verify_password(request.password, hash_password(request.password))


def test_login_rejects_long_utf8_password_without_bcrypt_error():
    assert not verify_password("é" * 37, hash_password("password123"))


def test_tokens_without_expiration_are_rejected():
    token = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001", "iat": 1},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


@pytest.mark.integration
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


@pytest.mark.anyio
async def test_registration_handles_concurrent_duplicate_email(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from sqlalchemy.exc import IntegrityError

    error = IntegrityError("insert user", {}, SimpleNamespace(sqlstate="23505"))
    monkeypatch.setattr("app.api.auth.get_user_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr("app.api.auth.hash_password", lambda value: "hashed")
    monkeypatch.setattr("app.api.auth.create_user", AsyncMock(side_effect=error))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "password123",
            },
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "A user with this email already exists"


@pytest.mark.anyio
async def test_registration_hashes_password_outside_event_loop(monkeypatch):
    import threading
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    event_loop_thread = threading.get_ident()

    def hash_password_in_worker(value):
        assert threading.get_ident() != event_loop_thread
        return "hashed"

    monkeypatch.setattr("app.api.auth.get_user_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr("app.api.auth.hash_password", hash_password_in_worker)
    monkeypatch.setattr(
        "app.api.auth.create_user",
        AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(),
                email="analyst@example.com",
                display_name="Analyst",
            )
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "password123",
            },
        )
    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Analyst"


@pytest.mark.anyio
async def test_me_preserves_display_name(monkeypatch):
    from uuid import uuid4

    from app.auth.dependencies import AuthenticatedUser, get_current_user

    user = AuthenticatedUser(uuid4(), "analyst@example.com", "Analyst")
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: user)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Analyst"

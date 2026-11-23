from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.api.router import protected_router, public_router
from app.auth.dependencies import CurrentUser
from app.auth.security import create_access_token, hash_password, verify_password
from app.database.users import create_user, get_user_by_email


def _validate_email(v: str) -> str:
    v = v.strip().lower()
    if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
        raise ValueError("Invalid email address")
    return v


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=6, max_length=72)
    display_name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("password")
    @classmethod
    def check_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=72)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _validate_email(v)


class UserSummary(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSummary


@public_router.post("/auth/register", response_model=AuthResponse, tags=["auth"])
async def register(body: RegisterRequest) -> AuthResponse:
    existing = await get_user_by_email(body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        )

    hashed_pw = await run_in_threadpool(hash_password, body.password)
    try:
        user = await create_user(
            email=body.email,
            hashed_password=hashed_pw,
            display_name=body.display_name,
        )
    except IntegrityError as error:
        # A concurrent registration can pass the email check before either commits.
        if getattr(error.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        ) from error

    token = create_access_token(user.id, user.email)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserSummary(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
        ),
    )


@public_router.post("/auth/login", response_model=AuthResponse, tags=["auth"])
async def login(body: LoginRequest) -> AuthResponse:
    user = await get_user_by_email(body.email)
    if user is None or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not await run_in_threadpool(
        verify_password, body.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id, user.email)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserSummary(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
        ),
    )


@public_router.post("/auth/logout", tags=["auth"])
async def logout() -> dict[str, str]:
    return {"status": "ok"}


@protected_router.get("/me", tags=["auth"])
@protected_router.get("/auth/me", tags=["auth"])
async def me(user: CurrentUser) -> UserSummary:
    return UserSummary(id=user.id, email=user.email, display_name=user.display_name)

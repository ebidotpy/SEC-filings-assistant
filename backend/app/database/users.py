from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database.models.user import User
from app.database.session import get_db_session


async def get_user_by_email(email: str) -> User | None:
    normalized_email = email.strip().lower()
    async with get_db_session() as session:
        result = await session.execute(
            select(User).where(User.email == normalized_email)
        )
        return result.scalar_one_or_none()


async def get_user_by_id(user_id: UUID) -> User | None:
    async with get_db_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def create_user(
    *,
    email: str,
    hashed_password: str,
    display_name: str | None = None,
) -> User:
    normalized_email = email.strip().lower()
    async with get_db_session() as session:
        user = User(
            email=normalized_email,
            hashed_password=hashed_password,
            display_name=display_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def ensure_app_user(user_id: UUID, email: str) -> None:
    """Ensure user exists in database, or do nothing if already present."""
    async with get_db_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            # When needed, e.g. for mock/test users
            user = User(
                id=user_id,
                email=email.strip().lower(),
                hashed_password="",
            )
            session.add(user)
            await session.commit()

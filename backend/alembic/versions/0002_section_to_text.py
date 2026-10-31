"""change section columns to text

Revision ID: 8f2d6b1c4a9e
Revises: 3c81ca3fef26
Create Date: 2026-07-06 13:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f2d6b1c4a9e"
down_revision: str | Sequence[str] | None = "3c81ca3fef26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "document_chunks",
        "section",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "message_citations",
        "section",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "message_citations",
        "section",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "document_chunks",
        "section",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )

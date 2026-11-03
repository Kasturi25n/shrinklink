"""Initial schema: users, links, clicks.

Matches what Base.metadata.create_all() produced before migrations existed, so
databases created that way are stamped at this revision instead of re-created
(see app/migrate.py).

Revision ID: 0001
Revises:
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_links_code", "links", ["code"], unique=True)
    op.create_index("ix_links_owner_id", "links", ["owner_id"])

    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("link_id", sa.Integer(), sa.ForeignKey("links.id"), nullable=False),
        sa.Column("clicked_at", sa.DateTime(), nullable=False),
        sa.Column("referrer", sa.String(255), nullable=True),
        sa.Column("browser", sa.String(50), nullable=True),
        sa.Column("device", sa.String(50), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
    )
    op.create_index("ix_clicks_link_time", "clicks", ["link_id", "clicked_at"])


def downgrade() -> None:
    op.drop_table("clicks")
    op.drop_table("links")
    op.drop_table("users")

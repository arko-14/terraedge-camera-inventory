"""add token_version for logout revocation

Revision ID: cd9bc274d3d9
Revises: b71aefe6477c
Create Date: 2026-09-07 12:48:38.185055
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'cd9bc274d3d9'
down_revision: Union[str, None] = 'b71aefe6477c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A NOT NULL column needs a server default to be added to a table that
    # already has rows; autogenerate omits it and the migration would fail on
    # any non-empty database. Existing accounts start at version 0, which is
    # what their live tokens already claim, so nobody is signed out by this.
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    # The default has done its job; the application supplies the value from here.
    op.alter_column("users", "token_version", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "token_version")

"""Persist a non-reversible LiteLLM key digest for spend reconciliation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_litellm_key_hash"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("run", sa.Column("litellm_key_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("run", "litellm_key_hash")

"""Add paired benchmark mode and fault-event tracking for injected LLM faults."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_fault_injection"
down_revision: str | None = "0002_litellm_key_hash"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "benchmark",
        sa.Column(
            "paired",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "run",
        sa.Column(
            "fault_mode",
            sa.String(length=12),
            nullable=False,
            server_default="none",
        ),
    )
    op.create_check_constraint(
        "ck_run_fault_mode",
        "run",
        "fault_mode IN ('none', 'faulted')",
    )
    op.create_table(
        "fault_event",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("fault_type", sa.String(length=32), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_reaction", sa.String(length=32), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "fault_type IN ('rate_limit_429', 'latency_spike', "
            "'empty_response', 'error_5xx')",
            name="ck_fault_event_type",
        ),
        sa.CheckConstraint(
            "agent_reaction IN ('retried_ok', 'gave_up', 'degraded', "
            "'ignored', 'none')",
            name="ck_fault_event_reaction",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "seq"),
    )


def downgrade() -> None:
    op.drop_table("fault_event")
    op.drop_constraint("ck_run_fault_mode", "run", type_="check")
    op.drop_column("run", "fault_mode")
    op.drop_column("benchmark", "paired")

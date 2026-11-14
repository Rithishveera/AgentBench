"""Initial durable benchmark schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("framework_tag", sa.String(length=100), nullable=True),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "max_concurrency", sa.SmallInteger(), server_default="2", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('coding', 'research', 'support')", name="ck_agent_category"
        ),
        sa.CheckConstraint(
            "max_concurrency BETWEEN 1 AND 100", name="ck_agent_concurrency"
        ),
    )
    op.create_table(
        "task",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "category IN ('coding', 'research', 'support')", name="ck_task_category"
        ),
        sa.CheckConstraint("version >= 1", name="ck_task_version"),
        sa.CheckConstraint("length(digest) = 64", name="ck_task_digest_length"),
    )
    op.create_table(
        "benchmark",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("suite_id", sa.String(length=100), nullable=False),
        sa.Column(
            "agent_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column("repetitions", sa.SmallInteger(), nullable=False),
        sa.Column(
            "fault_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=24), server_default="queued", nullable=False
        ),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_benchmark_status",
        ),
        sa.CheckConstraint(
            "repetitions BETWEEN 1 AND 1000", name="ck_benchmark_repetitions"
        ),
    )
    op.create_table(
        "run",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("benchmark_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("task_digest", sa.String(length=64), nullable=False),
        sa.Column("attempt_no", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default="queued", nullable=False
        ),
        sa.Column("artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("verdict", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("failure_cause", sa.String(length=64), nullable=True),
        sa.Column("steps_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tool_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_in", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "fault_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retries", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'agent_error', "
            "'timeout', 'infra_error')",
            name="ck_run_status",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND verdict IS NOT NULL) OR "
            "(status <> 'completed' AND verdict IS NULL)",
            name="ck_run_verdict_status",
        ),
        sa.CheckConstraint("attempt_no >= 1", name="ck_run_attempt_no"),
        sa.CheckConstraint("steps_count >= 0", name="ck_run_steps_count"),
        sa.CheckConstraint("tool_calls >= 0", name="ck_run_tool_calls"),
        sa.CheckConstraint("tokens_in >= 0", name="ck_run_tokens_in"),
        sa.CheckConstraint("tokens_out >= 0", name="ck_run_tokens_out"),
        sa.CheckConstraint("cost_usd >= 0", name="ck_run_cost_usd"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_run_duration"),
        sa.ForeignKeyConstraint(["benchmark_id"], ["benchmark.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agent.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.UniqueConstraint(
            "benchmark_id", "agent_id", "task_id", "attempt_no", name="uq_run_attempt"
        ),
    )
    op.create_index("ix_run_benchmark_status", "run", ["benchmark_id", "status"])
    op.create_index("ix_run_agent_task", "run", ["agent_id", "task_id"])
    op.create_table(
        "step",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.CheckConstraint("seq >= 0", name="ck_step_seq"),
        sa.CheckConstraint("type IN ('llm', 'tool', 'retry')", name="ck_step_type"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_step_duration"),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "seq"),
    )


def downgrade() -> None:
    op.drop_table("step")
    op.drop_index("ix_run_agent_task", table_name="run")
    op.drop_index("ix_run_benchmark_status", table_name="run")
    op.drop_table("run")
    op.drop_table("benchmark")
    op.drop_table("task")
    op.drop_table("agent")

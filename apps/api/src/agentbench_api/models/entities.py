"""PostgreSQL persistence models for benchmark state."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from agentbench_api.models.base import Base


class Agent(Base):
    __tablename__ = "agent"
    __table_args__ = (
        CheckConstraint(
            "category IN ('coding', 'research', 'support')", name="ck_agent_category"
        ),
        CheckConstraint(
            "max_concurrency BETWEEN 1 AND 100", name="ck_agent_concurrency"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    framework_tag: Mapped[str | None] = mapped_column(String(100))
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    max_concurrency: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default="2"
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TaskRecord(Base):
    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint(
            "category IN ('coding', 'research', 'support')", name="ck_task_category"
        ),
        CheckConstraint("version >= 1", name="ck_task_version"),
        CheckConstraint("length(digest) = 64", name="ck_task_digest_length"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Benchmark(Base):
    __tablename__ = "benchmark"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_benchmark_status",
        ),
        CheckConstraint(
            "repetitions BETWEEN 1 AND 1000", name="ck_benchmark_repetitions"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    suite_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    repetitions: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fault_flags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="queued", server_default="queued"
    )
    paired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(Base):
    __tablename__ = "run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'agent_error', "
            "'timeout', 'infra_error')",
            name="ck_run_status",
        ),
        CheckConstraint(
            "(status = 'completed' AND verdict IS NOT NULL) OR "
            "(status <> 'completed' AND verdict IS NULL)",
            name="ck_run_verdict_status",
        ),
        CheckConstraint(
            "fault_mode IN ('none', 'faulted')",
            name="ck_run_fault_mode",
        ),
        CheckConstraint("attempt_no >= 1", name="ck_run_attempt_no"),
        CheckConstraint("steps_count >= 0", name="ck_run_steps_count"),
        CheckConstraint("tool_calls >= 0", name="ck_run_tool_calls"),
        CheckConstraint("tokens_in >= 0", name="ck_run_tokens_in"),
        CheckConstraint("tokens_out >= 0", name="ck_run_tokens_out"),
        CheckConstraint("cost_usd >= 0", name="ck_run_cost_usd"),
        CheckConstraint("duration_ms >= 0", name="ck_run_duration"),
        UniqueConstraint(
            "benchmark_id",
            "agent_id",
            "task_id",
            "attempt_no",
            name="uq_run_attempt",
        ),
        Index("ix_run_benchmark_status", "benchmark_id", "status"),
        Index("ix_run_agent_task", "agent_id", "task_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    benchmark_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("benchmark.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent.id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("task.id"), nullable=False
    )
    task_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="queued", server_default="queued"
    )
    fault_mode: Mapped[str] = mapped_column(
        String(12), nullable=False, default="none", server_default="none"
    )
    artifact: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    verdict: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    failure_cause: Mapped[str | None] = mapped_column(String(64))
    steps_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tool_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tokens_in: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    tokens_out: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    duration_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    fault_plan: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    litellm_key_hash: Mapped[str | None] = mapped_column(String(64))
    token_hash: Mapped[str | None] = mapped_column(String(64))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retries: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FaultEvent(Base):
    __tablename__ = "fault_event"
    __table_args__ = (
        CheckConstraint(
            "fault_type IN ('rate_limit_429', 'latency_spike', "
            "'empty_response', 'error_5xx')",
            name="ck_fault_event_type",
        ),
        CheckConstraint(
            "agent_reaction IN ('retried_ok', 'gave_up', 'degraded', "
            "'ignored', 'none')",
            name="ck_fault_event_reaction",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("run.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    fault_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    agent_reaction: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Step(Base):
    __tablename__ = "step"
    __table_args__ = (
        CheckConstraint("seq >= 0", name="ck_step_seq"),
        CheckConstraint("type IN ('llm', 'tool', 'retry')", name="ck_step_type"),
        CheckConstraint("duration_ms >= 0", name="ck_step_duration"),
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("run.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Host(Base):
    __tablename__ = "hosts"
    __table_args__ = (
        CheckConstraint("connection IN ('local', 'ssh')", name="ck_hosts_connection"),
        Index("uq_hosts_name", "name", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    connection: Mapped[str] = mapped_column(String(16), nullable=False)
    ssh_target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_root: Mapped[str] = mapped_column(Text, nullable=False)
    data_root: Mapped[str] = mapped_column(Text, nullable=False)
    host_key_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ModelRoot(Base):
    __tablename__ = "model_roots"
    __table_args__ = (
        Index("uq_model_roots_host_path", "host_id", "path", unique=True),
        Index("ix_model_roots_host_id", "host_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    host_id: Mapped[str] = mapped_column(String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Instance(Base):
    __tablename__ = "instances"
    __table_args__ = (
        Index("uq_instances_host_slug", "host_id", "instance_slug", unique=True),
        Index("ix_instances_host_id", "host_id"),
        Index("ix_instances_primary_model_root_id", "primary_model_root_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    host_id: Mapped[str] = mapped_column(String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    instance_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    comfy_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    python_version: Mapped[str] = mapped_column(String(32), nullable=False)
    torch_profile: Mapped[str] = mapped_column(String(64), nullable=False)
    comfy_port: Mapped[int] = mapped_column(Integer, nullable=False)
    gpu_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    primary_model_root_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("model_roots.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    last_launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InstanceModelRoot(Base):
    __tablename__ = "instance_model_roots"
    __table_args__ = (
        Index("uq_instance_model_roots_pair", "instance_id", "model_root_id", unique=True),
        Index("ix_instance_model_roots_model_root_id", "model_root_id"),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id", ondelete="CASCADE"), primary_key=True
    )
    model_root_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("model_roots.id", ondelete="CASCADE"), primary_key=True
    )


class CommandRun(Base):
    __tablename__ = "command_runs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('install', 'reinstall', 'start', 'stop', 'probe_host', 'check_model_root')",
            name="ck_command_runs_kind",
        ),
        Index("ix_command_runs_instance_started", "instance_id", "started_at"),
        Index("ix_command_runs_host_started", "host_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    host_id: Mapped[str] = mapped_column(String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instances.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_tail: Mapped[str | None] = mapped_column(Text, nullable=True)

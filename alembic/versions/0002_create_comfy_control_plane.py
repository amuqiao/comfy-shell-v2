"""create comfy control plane tables

Revision ID: 0002_create_comfy_control_plane
Revises: 0001_create_items
Create Date: 2026-09-03
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_create_comfy_control_plane"
down_revision: str | None = "0001_create_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hosts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("connection", sa.String(length=16), nullable=False),
        sa.Column("ssh_target", sa.String(length=255), nullable=True),
        sa.Column("service_root", sa.Text(), nullable=False),
        sa.Column("data_root", sa.Text(), nullable=False),
        sa.Column("host_key_fingerprint", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("connection IN ('local', 'ssh')", name="ck_hosts_connection"),
    )
    op.create_index("uq_hosts_name", "hosts", ["name"], unique=True)

    op.create_table(
        "model_roots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_model_roots_host_id", "model_roots", ["host_id"])
    op.create_index("uq_model_roots_host_path", "model_roots", ["host_id", "path"], unique=True)

    op.create_table(
        "instances",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("instance_slug", sa.String(length=80), nullable=False),
        sa.Column("comfy_ref", sa.String(length=255), nullable=False),
        sa.Column("resolved_commit", sa.String(length=64), nullable=True),
        sa.Column("python_version", sa.String(length=32), nullable=False),
        sa.Column("torch_profile", sa.String(length=64), nullable=False),
        sa.Column("comfy_port", sa.Integer(), nullable=False),
        sa.Column("gpu_ids", sa.JSON(), nullable=False),
        sa.Column(
            "primary_model_root_id",
            sa.String(length=36),
            sa.ForeignKey("model_roots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_launched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_instances_host_id", "instances", ["host_id"])
    op.create_index("ix_instances_primary_model_root_id", "instances", ["primary_model_root_id"])
    op.create_index("uq_instances_host_slug", "instances", ["host_id", "instance_slug"], unique=True)

    op.create_table(
        "instance_model_roots",
        sa.Column(
            "instance_id",
            sa.String(length=36),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "model_root_id",
            sa.String(length=36),
            sa.ForeignKey("model_roots.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    op.create_index("ix_instance_model_roots_model_root_id", "instance_model_roots", ["model_root_id"])
    op.create_index(
        "uq_instance_model_roots_pair",
        "instance_model_roots",
        ["instance_id", "model_root_id"],
        unique=True,
    )

    op.create_table(
        "command_runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "instance_id",
            sa.String(length=36),
            sa.ForeignKey("instances.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("log_path", sa.Text(), nullable=True),
        sa.Column("stderr_tail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('install', 'reinstall', 'start', 'stop', 'probe_host', 'check_model_root')",
            name="ck_command_runs_kind",
        ),
    )
    op.create_index("ix_command_runs_host_started", "command_runs", ["host_id", "started_at"])
    op.create_index("ix_command_runs_instance_started", "command_runs", ["instance_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_command_runs_instance_started", table_name="command_runs")
    op.drop_index("ix_command_runs_host_started", table_name="command_runs")
    op.drop_table("command_runs")
    op.drop_index("uq_instance_model_roots_pair", table_name="instance_model_roots")
    op.drop_index("ix_instance_model_roots_model_root_id", table_name="instance_model_roots")
    op.drop_table("instance_model_roots")
    op.drop_index("uq_instances_host_slug", table_name="instances")
    op.drop_index("ix_instances_primary_model_root_id", table_name="instances")
    op.drop_index("ix_instances_host_id", table_name="instances")
    op.drop_table("instances")
    op.drop_index("uq_model_roots_host_path", table_name="model_roots")
    op.drop_index("ix_model_roots_host_id", table_name="model_roots")
    op.drop_table("model_roots")
    op.drop_index("uq_hosts_name", table_name="hosts")
    op.drop_table("hosts")

from __future__ import annotations

from typing import Any, Literal
from pathlib import Path

from pydantic import Field, field_validator

from app.core.config.sections import SUPPORTED_TORCH_PROFILES
from app.schemas.common import StrictBaseModel

ConnectionMode = Literal["local", "ssh"]
CommandKind = Literal["install", "reinstall", "start", "stop", "probe_host", "check_model_root"]


class HostCreateRequest(StrictBaseModel):
    name: str = Field(min_length=1, max_length=120)
    connection: ConnectionMode = "local"
    service_root: str | None = None
    data_root: str | None = None
    ssh_target: str | None = None
    host_key_fingerprint: str | None = None

    @field_validator("service_root", "data_root")
    @classmethod
    def validate_optional_absolute_path(cls, value: str | None) -> str | None:
        if value is not None and not Path(value).expanduser().is_absolute():
            raise ValueError("path must be absolute")
        return value


class HostResponse(StrictBaseModel):
    id: str
    name: str
    connection: ConnectionMode
    ssh_target: str | None
    service_root: str
    data_root: str
    host_key_fingerprint: str | None
    created_at: str
    updated_at: str


class HostListResponse(StrictBaseModel):
    hosts: list[HostResponse]


class ProbeResponse(StrictBaseModel):
    ok: bool
    layer: str
    data: dict[str, Any]


class CatalogGithubResponse(StrictBaseModel):
    repo: str
    url: str
    default_branch: str


class ComfyVersionOptionResponse(StrictBaseModel):
    id: str
    label: str
    display_version: str | None = None
    channel: str
    source_type: Literal["release", "snapshot", "branch"]
    ref: str
    recommended: bool = False
    verified: bool = False
    advanced: bool = False
    description: str | None = None


class RuntimeProfileOptionResponse(StrictBaseModel):
    id: str
    label: str
    python_version: str
    torch_profile: str
    backend: str | None = None
    gpu_vendor: str | None = None
    recommended: bool = False
    verified: bool = False
    advanced: bool = False
    min_cuda: str | None = None
    packages: dict[str, str] = Field(default_factory=dict)
    description: str | None = None


class RecommendationRuleResponse(StrictBaseModel):
    id: str
    when: dict[str, Any]
    version_id: str
    runtime_profile_id: str
    gpu: str
    reason: str
    warnings: list[str] = Field(default_factory=list)


class ComfyCatalogResponse(StrictBaseModel):
    schema_version: int
    github: CatalogGithubResponse
    versions: list[ComfyVersionOptionResponse]
    runtime_profiles: list[RuntimeProfileOptionResponse]
    recommendation_rules: list[RecommendationRuleResponse]


class ModelRootCreateRequest(StrictBaseModel):
    host_id: str
    label: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_absolute_path(cls, value: str) -> str:
        if not Path(value).expanduser().is_absolute():
            raise ValueError("path must be absolute")
        return value


class ModelRootResponse(StrictBaseModel):
    id: str
    host_id: str
    label: str
    path: str
    created_at: str
    updated_at: str


class ModelRootListResponse(StrictBaseModel):
    model_roots: list[ModelRootResponse]


class ModelRootCheckResponse(StrictBaseModel):
    ok: bool
    path: str
    exists: bool
    is_dir: bool
    readable: bool


class InstanceCreateRequest(StrictBaseModel):
    host_id: str
    name: str = Field(min_length=1, max_length=120)
    instance_slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    comfy_version_id: str | None = Field(default=None, max_length=120)
    runtime_profile_id: str | None = Field(default=None, max_length=120)
    comfy_ref: str | None = Field(default=None, max_length=255)
    python_version: str | None = Field(default=None, max_length=32)
    torch_profile: str | None = Field(default=None, max_length=64)
    comfy_port: int | None = Field(default=None, ge=1, le=65535)
    gpu_ids: list[str] = Field(default_factory=list)
    model_root_ids: list[str] = Field(default_factory=list)
    primary_model_root_id: str | None = None

    @field_validator("gpu_ids")
    @classmethod
    def validate_gpu_ids(cls, value: list[str]) -> list[str]:
        if len(value) > 16:
            raise ValueError("gpu_ids must contain at most 16 values")
        return value

    @field_validator("model_root_ids")
    @classmethod
    def validate_model_root_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("model_root_ids must be unique")
        return value

    @field_validator("torch_profile")
    @classmethod
    def validate_torch_profile(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_TORCH_PROFILES:
            supported = ", ".join(sorted(SUPPORTED_TORCH_PROFILES))
            raise ValueError(f"torch_profile must be one of: {supported}")
        return value


class InstanceResponse(StrictBaseModel):
    id: str
    host_id: str
    name: str
    instance_slug: str
    install_root: str
    comfy_ref: str
    resolved_commit: str | None
    python_version: str
    torch_profile: str
    comfy_port: int
    gpu_ids: list[str]
    primary_model_root_id: str | None
    model_root_ids: list[str]
    created_at: str
    updated_at: str
    last_launched_at: str | None


class InstanceListResponse(StrictBaseModel):
    instances: list[InstanceResponse]


class InstanceInstallRequest(StrictBaseModel):
    comfy_version_id: str | None = Field(default=None, max_length=120)
    comfy_ref: str | None = Field(default=None, max_length=255)
    restart: bool = False


class InstanceLaunchConfigUpdateRequest(StrictBaseModel):
    comfy_port: int | None = Field(default=None, ge=1, le=65535)
    gpu_ids: list[str] | None = None
    model_root_ids: list[str] | None = None
    primary_model_root_id: str | None = None

    @field_validator("gpu_ids")
    @classmethod
    def validate_gpu_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) > 16:
            raise ValueError("gpu_ids must contain at most 16 values")
        return value

    @field_validator("model_root_ids")
    @classmethod
    def validate_model_root_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("model_root_ids must be unique")
        return value


class InstanceStartRequest(StrictBaseModel):
    pass


class InstanceStopRequest(StrictBaseModel):
    pass


class InstanceStatusResponse(StrictBaseModel):
    ok: bool
    instance_id: str
    layer: str
    data: dict[str, Any]


class InstanceReadyResponse(StrictBaseModel):
    ready: bool
    instance_id: str
    layer: str
    data: dict[str, Any]


class InstanceLogsResponse(StrictBaseModel):
    instance_id: str
    log_path: str
    lines: list[str]


class RunResponse(StrictBaseModel):
    id: str
    request_id: str
    host_id: str
    instance_id: str | None
    kind: CommandKind
    phase: str
    started_at: str
    ended_at: str | None
    exit_code: int | None
    error_code: str | None
    message: str | None
    log_path: str | None
    stderr_tail: str | None


class RunListResponse(StrictBaseModel):
    runs: list[RunResponse]

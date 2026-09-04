from dataclasses import dataclass

from app.core.error_registry import error_registry
from app.schemas.envelope import ErrorEnvelope

COMMON_ERROR_CODES = frozenset({"REQUEST_INVALID", "INTERNAL_ERROR"})


@dataclass(frozen=True)
class OperationSpec:
    operation_id: str
    method: str
    path: str
    success_status: int
    # Route-specific business errors. Cross-cutting errors such as auth,
    # validation, and internal failures are defined by the common HTTP contract.
    errors: frozenset[str]
    request_schema: str | None = None
    response_schema: str | None = None
    auth_required: bool = True
    prefixed: bool = True

    def full_path(self, api_prefix: str) -> str:
        if not self.prefixed:
            return self.path
        if api_prefix == "/":
            return self.path
        return f"{api_prefix}{self.path}"

    def error_codes(self) -> frozenset[str]:
        codes = set(COMMON_ERROR_CODES)
        codes.update(self.errors)
        if self.auth_required:
            codes.add("UNAUTHORIZED")
        return frozenset(codes)


class OperationRegistry:
    def __init__(self) -> None:
        self._items: dict[str, OperationSpec] = {}
        self._frozen = False

    def register(self, spec: OperationSpec) -> None:
        if self._frozen:
            raise RuntimeError("operation registry is frozen")
        if spec.operation_id in self._items:
            raise RuntimeError(f"duplicate operation id: {spec.operation_id}")
        self._items[spec.operation_id] = spec

    def all(self) -> tuple[OperationSpec, ...]:
        return tuple(self._items.values())

    def get(self, operation_id: str) -> OperationSpec:
        try:
            return self._items[operation_id]
        except KeyError as exc:
            raise RuntimeError(f"unknown operation id: {operation_id}") from exc

    def freeze(self) -> None:
        self._frozen = True

    def validate(self) -> None:
        if not self._items:
            raise RuntimeError("operation registry must not be empty")


operation_registry = OperationRegistry()
operation_registry.register(
    OperationSpec(
        "health",
        "GET",
        "/health",
        200,
        frozenset(),
        response_schema="SuccessEnvelope",
        auth_required=False,
        prefixed=False,
    )
)
operation_registry.register(
    OperationSpec(
        "ready",
        "GET",
        "/ready",
        200,
        frozenset({"DEPENDENCY_UNAVAILABLE"}),
        response_schema="SuccessEnvelope",
        auth_required=False,
        prefixed=False,
    )
)
operation_registry.register(
    OperationSpec(
        "get_comfy_catalog",
        "GET",
        "/catalog",
        200,
        frozenset(),
        response_schema="SuccessEnvelope[ComfyCatalogResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "list_hosts",
        "GET",
        "/hosts",
        200,
        frozenset(),
        response_schema="SuccessEnvelope[HostListResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "create_host",
        "POST",
        "/hosts",
        201,
        frozenset({"HOST_NAME_CONFLICT", "EXECUTOR_UNSUPPORTED"}),
        request_schema="HostCreateRequest",
        response_schema="SuccessEnvelope[HostResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "probe_host",
        "POST",
        "/hosts/{host_id}/probe",
        200,
        frozenset({"HOST_NOT_FOUND", "COMFYCTL_FAILED"}),
        response_schema="SuccessEnvelope[ProbeResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "list_model_roots",
        "GET",
        "/model-roots",
        200,
        frozenset({"REQUEST_INVALID"}),
        response_schema="SuccessEnvelope[ModelRootListResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "create_model_root",
        "POST",
        "/model-roots",
        201,
        frozenset({"HOST_NOT_FOUND", "MODEL_ROOT_CONFLICT"}),
        request_schema="ModelRootCreateRequest",
        response_schema="SuccessEnvelope[ModelRootResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "check_model_root",
        "POST",
        "/model-roots/{model_root_id}/check",
        200,
        frozenset({"MODEL_ROOT_NOT_FOUND", "COMFYCTL_FAILED"}),
        response_schema="SuccessEnvelope[ModelRootCheckResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "list_instances",
        "GET",
        "/instances",
        200,
        frozenset({"REQUEST_INVALID"}),
        response_schema="SuccessEnvelope[InstanceListResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "create_instance",
        "POST",
        "/instances",
        201,
        frozenset({"HOST_NOT_FOUND", "MODEL_ROOT_NOT_FOUND", "INSTANCE_SLUG_CONFLICT", "REQUEST_INVALID"}),
        request_schema="InstanceCreateRequest",
        response_schema="SuccessEnvelope[InstanceResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "get_instance",
        "GET",
        "/instances/{instance_id}",
        200,
        frozenset({"INSTANCE_NOT_FOUND", "HOST_NOT_FOUND"}),
        response_schema="SuccessEnvelope[InstanceResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "update_instance_launch_config",
        "PATCH",
        "/instances/{instance_id}/launch-config",
        200,
        frozenset(
            {
                "INSTANCE_NOT_FOUND",
                "HOST_NOT_FOUND",
                "MODEL_ROOT_NOT_FOUND",
                "COMFYCTL_FAILED",
                "PID_INVALID",
                "INSTANCE_RUNNING",
            }
        ),
        request_schema="InstanceLaunchConfigUpdateRequest",
        response_schema="SuccessEnvelope[InstanceResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "install_instance",
        "POST",
        "/instances/{instance_id}/install",
        200,
        frozenset(
            {
                "INSTANCE_NOT_FOUND",
                "HOST_NOT_FOUND",
                "COMFYCTL_FAILED",
                "PORT_IN_USE",
                "INSTANCE_LOCKED",
                "DEPENDENCY_MISSING",
                "GIT_FAILED",
                "UV_FAILED",
                "PYTHON_DEPENDENCY_FAILED",
            }
        ),
        request_schema="InstanceInstallRequest",
        response_schema="SuccessEnvelope[RunResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "reinstall_instance",
        "POST",
        "/instances/{instance_id}/reinstall",
        200,
        frozenset(
            {
                "INSTANCE_NOT_FOUND",
                "HOST_NOT_FOUND",
                "COMFYCTL_FAILED",
                "PORT_IN_USE",
                "INSTANCE_LOCKED",
                "DEPENDENCY_MISSING",
                "GIT_FAILED",
                "UV_FAILED",
                "PYTHON_DEPENDENCY_FAILED",
            }
        ),
        request_schema="InstanceInstallRequest",
        response_schema="SuccessEnvelope[RunResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "start_instance",
        "POST",
        "/instances/{instance_id}/start",
        200,
        frozenset(
            {
                "INSTANCE_NOT_FOUND",
                "HOST_NOT_FOUND",
                "COMFYCTL_FAILED",
                "PORT_IN_USE",
                "INSTANCE_NOT_INSTALLED",
                "VENV_MISSING",
                "PROCESS_START_FAILED",
            }
        ),
        request_schema="InstanceStartRequest",
        response_schema="SuccessEnvelope[RunResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "stop_instance",
        "POST",
        "/instances/{instance_id}/stop",
        200,
        frozenset({"INSTANCE_NOT_FOUND", "HOST_NOT_FOUND", "COMFYCTL_FAILED", "PROCESS_STOP_TIMEOUT", "PID_INVALID"}),
        request_schema="InstanceStopRequest",
        response_schema="SuccessEnvelope[RunResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "status_instance",
        "GET",
        "/instances/{instance_id}/status",
        200,
        frozenset({"INSTANCE_NOT_FOUND", "HOST_NOT_FOUND", "COMFYCTL_FAILED", "PID_INVALID"}),
        response_schema="SuccessEnvelope[InstanceStatusResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "ready_instance",
        "GET",
        "/instances/{instance_id}/ready",
        200,
        frozenset({"INSTANCE_NOT_FOUND", "HOST_NOT_FOUND", "COMFYCTL_FAILED"}),
        response_schema="SuccessEnvelope[InstanceReadyResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "logs_instance",
        "GET",
        "/instances/{instance_id}/logs",
        200,
        frozenset({"REQUEST_INVALID", "INSTANCE_NOT_FOUND", "HOST_NOT_FOUND", "COMFYCTL_FAILED"}),
        response_schema="SuccessEnvelope[InstanceLogsResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "list_runs",
        "GET",
        "/runs",
        200,
        frozenset({"REQUEST_INVALID"}),
        response_schema="SuccessEnvelope[RunListResponse]",
    )
)
operation_registry.register(
    OperationSpec(
        "get_run",
        "GET",
        "/runs/{run_id}",
        200,
        frozenset({"RUN_NOT_FOUND"}),
        response_schema="SuccessEnvelope[RunResponse]",
    )
)
operation_registry.validate()
operation_registry.freeze()


def operation_responses(operation_id: str) -> dict[int, dict[str, object]]:
    grouped: dict[int, list[str]] = {}
    for code in sorted(operation_registry.get(operation_id).error_codes()):
        status = error_registry.get(code).http_status
        grouped.setdefault(status, []).append(code)
    return {
        status: {
            "model": ErrorEnvelope,
            "description": ", ".join(codes),
        }
        for status, codes in grouped.items()
    }

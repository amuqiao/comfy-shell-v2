from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    http_status: int
    message: str
    retryable: bool
    visibility: frozenset[str]


class ErrorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ErrorSpec] = {}
        self._frozen = False

    def register(self, spec: ErrorSpec) -> None:
        if self._frozen:
            raise RuntimeError("error registry is frozen")
        if spec.code in self._items:
            raise RuntimeError(f"duplicate error code: {spec.code}")
        self._items[spec.code] = spec

    def get(self, code: str) -> ErrorSpec:
        try:
            return self._items[code]
        except KeyError as exc:
            raise RuntimeError(f"unknown error code: {code}") from exc

    def all(self) -> tuple[ErrorSpec, ...]:
        return tuple(self._items.values())

    def freeze(self) -> None:
        self._frozen = True

    def validate(self) -> None:
        if "INTERNAL_ERROR" not in self._items:
            raise RuntimeError("INTERNAL_ERROR must be registered")


error_registry = ErrorRegistry()


def _register_defaults() -> None:
    specs = [
        ErrorSpec("REQUEST_INVALID", 422, "Request is invalid.", False, frozenset({"public", "internal"})),
        ErrorSpec("UNAUTHORIZED", 401, "Authentication is required.", False, frozenset({"public", "internal"})),
        ErrorSpec("FORBIDDEN", 403, "Permission denied.", False, frozenset({"public", "internal"})),
        ErrorSpec("RESOURCE_NOT_FOUND", 404, "Resource not found.", False, frozenset({"public", "internal"})),
        ErrorSpec("RESOURCE_CONFLICT", 409, "Resource conflict.", False, frozenset({"public", "internal"})),
        ErrorSpec("DEPENDENCY_UNAVAILABLE", 503, "Dependency is unavailable.", True, frozenset({"public", "internal"})),
        ErrorSpec("INTERNAL_ERROR", 500, "Internal server error.", True, frozenset({"public", "internal"})),
        ErrorSpec("HOST_NOT_FOUND", 404, "Host not found.", False, frozenset({"public"})),
        ErrorSpec("HOST_NAME_CONFLICT", 409, "Host name already exists.", False, frozenset({"public"})),
        ErrorSpec("MODEL_ROOT_NOT_FOUND", 404, "Model root not found.", False, frozenset({"public"})),
        ErrorSpec("MODEL_ROOT_CONFLICT", 409, "Model root already exists.", False, frozenset({"public"})),
        ErrorSpec("INSTANCE_NOT_FOUND", 404, "Instance not found.", False, frozenset({"public"})),
        ErrorSpec("INSTANCE_SLUG_CONFLICT", 409, "Instance slug already exists.", False, frozenset({"public"})),
        ErrorSpec("INSTANCE_RUNNING", 409, "Instance is running.", False, frozenset({"public"})),
        ErrorSpec("RUN_NOT_FOUND", 404, "Command run not found.", False, frozenset({"public"})),
        ErrorSpec("EXECUTOR_UNSUPPORTED", 422, "Executor mode is not supported.", False, frozenset({"public"})),
        ErrorSpec("COMFYCTL_FAILED", 500, "comfyctl command failed.", False, frozenset({"public"})),
        ErrorSpec("PORT_IN_USE", 409, "Port is already in use.", False, frozenset({"public"})),
        ErrorSpec("INSTANCE_LOCKED", 409, "Instance is locked.", False, frozenset({"public"})),
        ErrorSpec("DEPENDENCY_MISSING", 503, "Required dependency is missing.", False, frozenset({"public"})),
        ErrorSpec("GIT_FAILED", 502, "Git command failed.", True, frozenset({"public"})),
        ErrorSpec("UV_FAILED", 502, "uv command failed.", True, frozenset({"public"})),
        ErrorSpec("PYTHON_DEPENDENCY_FAILED", 502, "Python dependency installation failed.", True, frozenset({"public"})),
        ErrorSpec("INSTANCE_NOT_INSTALLED", 409, "Instance is not installed.", False, frozenset({"public"})),
        ErrorSpec("VENV_MISSING", 409, "Instance virtual environment is missing.", False, frozenset({"public"})),
        ErrorSpec("PROCESS_START_FAILED", 502, "Process failed to start.", True, frozenset({"public"})),
        ErrorSpec("PROCESS_STOP_TIMEOUT", 504, "Process stop timed out.", True, frozenset({"public"})),
        ErrorSpec("PID_INVALID", 500, "PID file is invalid.", False, frozenset({"public"})),
    ]
    for spec in specs:
        error_registry.register(spec)
    error_registry.validate()
    error_registry.freeze()


_register_defaults()

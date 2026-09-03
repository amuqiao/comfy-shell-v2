from __future__ import annotations

from pathlib import Path

from app.core.config.settings import ROOT_DIR


def service_root() -> Path:
    return ROOT_DIR


def resolved_data_root(configured_data_root: str) -> Path:
    if configured_data_root:
        return Path(configured_data_root).expanduser().resolve()
    return service_root()


def instance_install_root(*, data_root: str, instance_slug: str) -> str:
    return str(Path(data_root).expanduser().resolve() / "ComfyUI-Installs" / instance_slug)


def default_model_root_path(*, data_root: str) -> str:
    return str(Path(data_root).expanduser().resolve() / "ComfyUI-Shared" / "models")

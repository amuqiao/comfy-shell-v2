from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")


@dataclass(frozen=True)
class ComfyPaths:
    data_root: Path
    installs_dir: Path
    shared_dir: Path
    default_models_root: Path
    default_input_root: Path
    default_output_root: Path
    download_cache_dir: Path


@dataclass(frozen=True)
class InstancePaths:
    root: Path
    checkout: Path
    venv: Path
    manifest: Path
    extra_model_paths: Path
    lock: Path
    run_dir: Path
    pid_file: Path
    logs_dir: Path
    log_file: Path
    staging_dir: Path
    previous_dir: Path


def validate_slug(slug: str) -> str:
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError("instance slug must match ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    return slug


def resolve_data_root(data_root: str) -> Path:
    path = Path(data_root).expanduser()
    if not path.is_absolute():
        raise ValueError("data root must be an absolute path")
    return path.resolve()


def comfy_paths(data_root: str) -> ComfyPaths:
    root = resolve_data_root(data_root)
    return ComfyPaths(
        data_root=root,
        installs_dir=root / "ComfyUI-Installs",
        shared_dir=root / "ComfyUI-Shared",
        default_models_root=root / "ComfyUI-Shared" / "models",
        default_input_root=root / "ComfyUI-Shared" / "input",
        default_output_root=root / "ComfyUI-Shared" / "output",
        download_cache_dir=root / "ComfyUI-Cache" / "download-cache",
    )


def ensure_data_dirs(data_root: str) -> ComfyPaths:
    paths = comfy_paths(data_root)
    for path in (
        paths.installs_dir,
        paths.default_models_root,
        paths.default_input_root,
        paths.default_output_root,
        paths.download_cache_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return paths


def instance_paths(data_root: str, slug: str) -> InstancePaths:
    valid_slug = validate_slug(slug)
    paths = comfy_paths(data_root)
    root = (paths.installs_dir / valid_slug).resolve()
    installs_root = paths.installs_dir.resolve()
    if root != installs_root and installs_root not in root.parents:
        raise ValueError("instance root escaped installs directory")
    return InstancePaths(
        root=root,
        checkout=root / "ComfyUI",
        venv=root / ".venv",
        manifest=root / "manifest.json",
        extra_model_paths=root / "extra_model_paths.yaml",
        lock=root / "instance.lock",
        run_dir=root / ".run",
        pid_file=root / ".run" / "comfyui.pid",
        logs_dir=root / "logs",
        log_file=root / "logs" / "comfyui.log",
        staging_dir=root / ".staging",
        previous_dir=root / ".previous",
    )


def ensure_instance_dirs(data_root: str, slug: str) -> InstancePaths:
    paths = instance_paths(data_root, slug)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.staging_dir.mkdir(parents=True, exist_ok=True)
    paths.previous_dir.mkdir(parents=True, exist_ok=True)
    return paths

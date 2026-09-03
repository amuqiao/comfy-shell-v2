from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from comfyctl.paths import ensure_data_dirs, ensure_instance_dirs, instance_paths


EXIT_USAGE = 2
EXIT_PRECONDITION = 3
EXIT_EXTERNAL = 4
EXIT_RUNTIME = 5

TORCH_REQUIREMENT_NAMES = frozenset({"torch", "torchvision", "torchaudio"})
TORCH_PROFILE_BACKENDS = {"cu124": "cu124"}
TORCH_PROFILE_PACKAGES = {
    "cu124": {
        "torch": "torch==2.6.0+cu124",
        "torchvision": "torchvision==0.21.0+cu124",
        "torchaudio": "torchaudio==2.6.0+cu124",
    }
}
SUPPORTED_CUDA_TORCH_PROFILES = frozenset(TORCH_PROFILE_BACKENDS)
DEFAULT_RECOMMENDED_PYTHON = "3.12"
DEFAULT_CU124_COMFY_REF = "8b099de36acd81acd1afa3b5442951dc847e0a52"


@dataclass(frozen=True)
class CommandFailure(Exception):
    exit_code: int
    error_code: str
    message: str
    layer: str
    log_path: str | None = None
    stderr_tail: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def success(data: dict[str, Any]) -> int:
    emit({"ok": True, "ts": utc_now(), **data})
    return 0


def failure(exc: CommandFailure) -> int:
    emit(
        {
            "ok": False,
            "ts": utc_now(),
            "error_code": exc.error_code,
            "message": exc.message,
            "layer": exc.layer,
            "log_path": exc.log_path,
            "stderr_tail": exc.stderr_tail,
        }
    )
    return exc.exit_code


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise CommandFailure(EXIT_EXTERNAL, "DEPENDENCY_MISSING", f"missing executable: {command[0]}", "python") from exc


def stderr_tail(value: str, *, limit: int = 4000) -> str:
    return value[-limit:]


def require_tool(name: str, *, layer: str = "python") -> str:
    path = shutil.which(name)
    if path is None:
        raise CommandFailure(EXIT_EXTERNAL, "DEPENDENCY_MISSING", f"missing executable: {name}", layer)
    return path


def version_parts(value: str | None) -> tuple[int, ...]:
    if value is None:
        return ()
    return tuple(int(part) for part in re.findall(r"\d+", value))


def version_at_least(value: str | None, minimum: str) -> bool:
    parts = version_parts(value)
    minimum_parts = version_parts(minimum)
    if not parts or not minimum_parts:
        return False
    length = max(len(parts), len(minimum_parts))
    padded = parts + (0,) * (length - len(parts))
    minimum_padded = minimum_parts + (0,) * (length - len(minimum_parts))
    return padded >= minimum_padded


def parse_nvidia_smi_cuda_version(value: str) -> str | None:
    match = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)?)", value)
    if match is None:
        return None
    return match.group(1)


def runtime_recommendation(*, cuda_version: str | None, gpus: list[dict[str, str]]) -> dict[str, Any]:
    warnings: list[str] = []
    if gpus and version_at_least(cuda_version, "12.4"):
        return {
            "comfy_ref": DEFAULT_CU124_COMFY_REF,
            "python_version": DEFAULT_RECOMMENDED_PYTHON,
            "torch_profile": "cu124",
            "gpu_ids": [gpus[0]["index"]],
            "reason": f"Detected NVIDIA CUDA {cuda_version}; use the verified cu124 runtime and compatible ComfyUI ref.",
            "warnings": warnings,
        }
    if gpus:
        warnings.append("No supported CUDA torch profile matches this host; add a dedicated profile before GPU install.")
        return {
            "comfy_ref": "master",
            "python_version": DEFAULT_RECOMMENDED_PYTHON,
            "torch_profile": "requirements",
            "gpu_ids": [gpus[0]["index"]],
            "reason": f"Detected NVIDIA GPU but CUDA version is {cuda_version or 'unknown'}.",
            "warnings": warnings,
        }
    return {
        "comfy_ref": "master",
        "python_version": DEFAULT_RECOMMENDED_PYTHON,
        "torch_profile": "requirements",
        "gpu_ids": [],
        "reason": "No NVIDIA GPU was detected.",
        "warnings": warnings,
    }


def normalized_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def requirement_package_name(line: str) -> str | None:
    stripped = line.split("#", 1)[0].strip()
    if not stripped or stripped.startswith(("-", "http://", "https://", ".")):
        return None
    match = re.match(r"([A-Za-z0-9_.-]+)", stripped)
    if match is None:
        return None
    return normalized_package_name(match.group(1))


def is_torch_requirement(line: str) -> bool:
    name = requirement_package_name(line)
    return name in TORCH_REQUIREMENT_NAMES


def write_requirements_without_torch(source: Path, target: Path) -> None:
    lines = [line for line in source.read_text(encoding="utf-8").splitlines() if not is_torch_requirement(line)]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def torch_requirements(source: Path, *, torch_profile: str | None = None) -> list[str]:
    lines = [line.split("#", 1)[0].strip() for line in source.read_text(encoding="utf-8").splitlines()]
    requirements = [line for line in lines if line and is_torch_requirement(line)]
    if torch_profile is None:
        if requirements:
            return requirements
        return ["torch", "torchvision", "torchaudio"]
    profile_packages = TORCH_PROFILE_PACKAGES[torch_profile]
    return [profile_packages[name] for name in ("torch", "torchvision", "torchaudio")]


def installed_torch_versions(python: Path) -> dict[str, str | None]:
    script = (
        "import json\n"
        "import torch\n"
        "import torchvision\n"
        "import torchaudio\n"
        "print(json.dumps({"
        "'torch': torch.__version__, "
        "'torch_cuda': torch.version.cuda, "
        "'torchvision': torchvision.__version__, "
        "'torchaudio': torchaudio.__version__"
        "}, sort_keys=True))\n"
    )
    result = run_command([str(python), "-c", script])
    if result.returncode != 0:
        raise CommandFailure(
            EXIT_EXTERNAL,
            "PYTHON_DEPENDENCY_FAILED",
            "torch import check failed after install",
            "python",
            stderr_tail=stderr_tail(result.stderr),
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CommandFailure(
            EXIT_EXTERNAL,
            "PYTHON_DEPENDENCY_FAILED",
            "torch import check returned invalid JSON",
            "python",
            stderr_tail=stderr_tail(result.stdout + result.stderr),
        ) from exc
    return {
        "torch": value.get("torch"),
        "torch_cuda": value.get("torch_cuda"),
        "torchvision": value.get("torchvision"),
        "torchaudio": value.get("torchaudio"),
    }


def read_pid(pid_file: Path) -> int | None:
    if not pid_file.exists():
        return None
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise CommandFailure(EXIT_RUNTIME, "PID_INVALID", f"invalid pid file: {pid_file}", "process") from exc


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def port_open(host: str, port: int, *, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def ensure_port_free(host: str, port: int) -> None:
    if port_open(host, port):
        raise CommandFailure(EXIT_PRECONDITION, "PORT_IN_USE", f"port {port} is already in use", "process")


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time())}-{os.getpid()}"


def tail_file(path: Path, *, limit: int = 4000) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]


def process_cmdline(pid: int) -> list[str] | None:
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    if proc_cmdline.exists():
        raw = proc_cmdline.read_bytes().split(b"\0")
        return [item.decode("utf-8", errors="replace") for item in raw if item]
    result = run_command(["ps", "-p", str(pid), "-o", "command="])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip().split()


def process_cwd(pid: int) -> Path | None:
    proc_cwd = Path("/proc") / str(pid) / "cwd"
    try:
        return proc_cwd.resolve(strict=True)
    except OSError:
        return None


def process_owned_by_instance(pid: int, paths) -> bool:
    if not process_alive(pid):
        return False
    cwd = process_cwd(pid)
    cmdline = process_cmdline(pid)
    if cwd is None or cmdline is None:
        return False
    try:
        checkout = paths.checkout.resolve(strict=True)
    except OSError:
        return False
    has_main = any(part == "main.py" or Path(part).name == "main.py" for part in cmdline)
    return cwd == checkout and has_main


def checkout_commit(checkout_dir: Path, *, log_path: Path) -> str:
    result = run_command(["git", "rev-parse", "HEAD"], cwd=checkout_dir)
    if result.returncode != 0 or not result.stdout.strip():
        raise CommandFailure(
            EXIT_EXTERNAL,
            "GIT_FAILED",
            "git rev-parse HEAD failed",
            "git",
            log_path=str(log_path),
            stderr_tail=stderr_tail(result.stderr),
        )
    return result.stdout.strip()


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clone_checkout(*, repo: str, ref: str, checkout_dir: Path, log_path: Path) -> None:
    clone = run_command(
        ["git", "clone", "--depth", "1", "--single-branch", "--filter=blob:none", "--branch", ref, repo, str(checkout_dir)]
    )
    if clone.returncode == 0:
        return
    shutil.rmtree(checkout_dir, ignore_errors=True)
    clone = run_command(["git", "clone", repo, str(checkout_dir)])
    if clone.returncode != 0:
        raise CommandFailure(
            EXIT_EXTERNAL,
            "GIT_FAILED",
            "git clone failed",
            "git",
            log_path=str(log_path),
            stderr_tail=stderr_tail(clone.stderr),
        )
    checkout = run_command(["git", "checkout", ref], cwd=checkout_dir)
    if checkout.returncode != 0:
        raise CommandFailure(
            EXIT_EXTERNAL,
            "GIT_FAILED",
            "git checkout failed",
            "git",
            log_path=str(log_path),
            stderr_tail=stderr_tail(checkout.stderr),
        )


def promote_install(paths, *, staging_checkout: Path, staging_venv: Path) -> None:
    previous_root = paths.previous_dir / unique_name("install")
    previous_root.mkdir(parents=True, exist_ok=False)
    for source, name in ((paths.checkout, "ComfyUI"), (paths.venv, ".venv"), (paths.manifest, "manifest.json")):
        if source.exists():
            shutil.move(str(source), str(previous_root / name))
    shutil.move(str(staging_checkout), str(paths.checkout))
    shutil.move(str(staging_venv), str(paths.venv))


def inspect_nvidia_smi(nvidia_smi: str | None) -> dict[str, Any]:
    if nvidia_smi is None:
        return {"nvidia_smi": None, "cuda_version": None, "driver_version": None, "gpus": [], "error": None}

    gpus: list[dict[str, str]] = []
    driver_versions: set[str] = set()
    gpu_result = run_command(
        [nvidia_smi, "--query-gpu=index,name,memory.total,driver_version", "--format=csv,noheader,nounits"]
    )
    error: str | None = None
    if gpu_result.returncode == 0:
        for line in gpu_result.stdout.splitlines():
            cells = [cell.strip() for cell in line.split(",")]
            if len(cells) >= 4:
                driver_versions.add(cells[3])
                gpus.append({"index": cells[0], "name": cells[1], "memory_total_mb": cells[2], "driver_version": cells[3]})
    else:
        error = stderr_tail(gpu_result.stderr)

    summary_result = run_command([nvidia_smi])
    cuda_version = parse_nvidia_smi_cuda_version(summary_result.stdout) if summary_result.returncode == 0 else None
    if summary_result.returncode != 0:
        error = stderr_tail(summary_result.stderr)
    elif cuda_version is None:
        error = "nvidia-smi output did not include a parseable CUDA Version"

    return {
        "nvidia_smi": nvidia_smi,
        "cuda_version": cuda_version,
        "driver_version": next(iter(driver_versions)) if len(driver_versions) == 1 else None,
        "gpus": gpus,
        "error": error,
    }


def command_host_probe(args: argparse.Namespace) -> int:
    data_paths = ensure_data_dirs(args.data_root)
    nvidia_smi = shutil.which("nvidia-smi")
    gpu_info = inspect_nvidia_smi(nvidia_smi)
    recommendation = runtime_recommendation(cuda_version=gpu_info["cuda_version"], gpus=gpu_info["gpus"])
    return success(
        {
            "layer": "host",
            "data": {
                "data_root": str(data_paths.data_root),
                "installs_dir": str(data_paths.installs_dir),
                "shared_dir": str(data_paths.shared_dir),
                "default_models_root": str(data_paths.default_models_root),
                "default_input_root": str(data_paths.default_input_root),
                "default_output_root": str(data_paths.default_output_root),
                "download_cache_dir": str(data_paths.download_cache_dir),
                "git": shutil.which("git"),
                "uv": shutil.which("uv"),
                "python": sys.executable,
                "nvidia_smi": gpu_info["nvidia_smi"],
                "nvidia_smi_error": gpu_info["error"],
                "driver_version": gpu_info["driver_version"],
                "cuda_version": gpu_info["cuda_version"],
                "gpus": gpu_info["gpus"],
                "runtime_recommendation": recommendation,
            },
        }
    )


def command_model_root_check(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    resolved = path.resolve()
    exists = resolved.exists()
    is_dir = resolved.is_dir()
    readable = os.access(resolved, os.R_OK) if exists else False
    return success({"path": str(resolved), "exists": exists, "is_dir": is_dir, "readable": readable})


def command_instance_install(args: argparse.Namespace) -> int:
    paths = ensure_instance_dirs(args.data_root, args.slug)
    require_tool("git", layer="git")
    require_tool("uv", layer="python")
    if args.torch_profile not in {"requirements", *sorted(SUPPORTED_CUDA_TORCH_PROFILES)}:
        supported = ", ".join(["requirements", *sorted(SUPPORTED_CUDA_TORCH_PROFILES)])
        raise CommandFailure(EXIT_USAGE, "REQUEST_INVALID", f"torch_profile must be one of: {supported}", "config")

    if paths.lock.exists():
        raise CommandFailure(EXIT_PRECONDITION, "INSTANCE_LOCKED", f"instance lock exists: {paths.lock}", "filesystem")
    paths.lock.write_text(str(os.getpid()), encoding="utf-8")
    staging_root: Path | None = None
    try:
        staging_root = paths.staging_dir / unique_name("install")
        staging_checkout = staging_root / "ComfyUI"
        staging_venv = staging_root / ".venv"
        staging_root.mkdir(parents=True, exist_ok=False)
        clone_checkout(repo=args.repo, ref=args.ref, checkout_dir=staging_checkout, log_path=paths.log_file)
        resolved_commit = checkout_commit(staging_checkout, log_path=paths.log_file)
        venv = run_command(["uv", "venv", "--python", args.python, str(staging_venv)])
        if venv.returncode != 0:
            raise CommandFailure(
                EXIT_EXTERNAL,
                "UV_FAILED",
                "uv venv failed",
                "python",
                log_path=str(paths.log_file),
                stderr_tail=stderr_tail(venv.stderr),
            )
        requirements = staging_checkout / "requirements.txt"
        torch_versions: dict[str, str | None] | None = None
        if requirements.exists():
            venv_python = staging_venv / "bin" / "python"
            if args.torch_profile == "requirements":
                install_requirements = requirements
            else:
                torch_backend = TORCH_PROFILE_BACKENDS[args.torch_profile]
                torch_packages = torch_requirements(requirements, torch_profile=args.torch_profile)
                torch_install = run_command(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        str(venv_python),
                        "--torch-backend",
                        torch_backend,
                        *torch_packages,
                    ]
                )
                if torch_install.returncode != 0:
                    raise CommandFailure(
                        EXIT_EXTERNAL,
                        "PYTHON_DEPENDENCY_FAILED",
                        f"uv pip install torch_profile={args.torch_profile} failed",
                        "python",
                        log_path=str(paths.log_file),
                        stderr_tail=stderr_tail(torch_install.stderr),
                    )
                install_requirements = staging_checkout / "requirements-without-torch.txt"
                write_requirements_without_torch(requirements, install_requirements)
            install = run_command(["uv", "pip", "install", "--python", str(venv_python), "-r", str(install_requirements)])
            if install.returncode != 0:
                raise CommandFailure(
                    EXIT_EXTERNAL,
                    "PYTHON_DEPENDENCY_FAILED",
                    "uv pip install requirements failed",
                    "python",
                    log_path=str(paths.log_file),
                    stderr_tail=stderr_tail(install.stderr),
                )
            torch_versions = installed_torch_versions(venv_python)
        promote_install(paths, staging_checkout=staging_checkout, staging_venv=staging_venv)
        write_manifest(
            paths.manifest,
            {
                "instance_id": args.id,
                "instance_slug": args.slug,
                "comfy_ref": args.ref,
                "resolved_commit": resolved_commit,
                "python_version": args.python,
                "torch_profile": args.torch_profile,
                "torch_versions": torch_versions,
                "created_at": utc_now(),
            },
        )
        return success(
            {
                "instance_id": args.id,
                "instance_slug": args.slug,
                "install_root": str(paths.root),
                "resolved_commit": resolved_commit,
                "manifest_path": str(paths.manifest),
                "log_path": str(paths.log_file),
            }
        )
    finally:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        paths.lock.unlink(missing_ok=True)


def write_extra_model_paths(path: Path, model_roots: list[str]) -> None:
    lines = ["comfy_shell:", "  base_path: /", "  checkpoints: ''"]
    if model_roots:
        lines = ["comfy_shell:", "  base_path: /", "  checkpoints: |"]
        lines.extend(f"    {model_root}" for model_root in model_roots)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def command_instance_start(args: argparse.Namespace) -> int:
    paths = ensure_instance_dirs(args.data_root, args.slug)
    if not paths.checkout.exists():
        raise CommandFailure(EXIT_PRECONDITION, "INSTANCE_NOT_INSTALLED", "ComfyUI checkout does not exist", "filesystem")
    ensure_port_free(args.host, args.port)
    write_extra_model_paths(paths.extra_model_paths, args.model_root)
    python = paths.venv / "bin" / "python"
    if not python.exists():
        raise CommandFailure(EXIT_PRECONDITION, "VENV_MISSING", "instance venv does not exist", "python")
    command = [
        str(python),
        "main.py",
        "--listen",
        args.host,
        "--port",
        str(args.port),
        "--extra-model-paths-config",
        str(paths.extra_model_paths),
    ]
    env = os.environ.copy()
    if args.gpu:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(args.gpu)
    with paths.log_file.open("ab") as log_file:
        process = subprocess.Popen(command, cwd=paths.checkout, stdout=log_file, stderr=subprocess.STDOUT, env=env)
    deadline = time.time() + args.startup_timeout
    while time.time() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise CommandFailure(
                EXIT_RUNTIME,
                "PROCESS_START_FAILED",
                f"process exited during startup with code {exit_code}",
                "process",
                log_path=str(paths.log_file),
                stderr_tail=tail_file(paths.log_file),
            )
        if port_open(args.host, args.port, timeout=0.2):
            paths.pid_file.write_text(str(process.pid), encoding="utf-8")
            return success(
                {
                    "instance_id": args.id,
                    "pid": process.pid,
                    "host": args.host,
                    "port": args.port,
                    "log_path": str(paths.log_file),
                }
            )
        time.sleep(0.2)
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    raise CommandFailure(
        EXIT_RUNTIME,
        "PROCESS_START_FAILED",
        f"process did not open port {args.port} within {args.startup_timeout} seconds",
        "process",
        log_path=str(paths.log_file),
        stderr_tail=tail_file(paths.log_file),
    )


def command_instance_stop(args: argparse.Namespace) -> int:
    paths = instance_paths(args.data_root, args.slug)
    pid = read_pid(paths.pid_file)
    if pid is None:
        return success({"instance_id": args.id, "stopped": False, "reason": "pid_file_missing"})
    if not process_alive(pid):
        paths.pid_file.unlink(missing_ok=True)
        return success({"instance_id": args.id, "stopped": False, "reason": "process_not_alive"})
    if not process_owned_by_instance(pid, paths):
        raise CommandFailure(
            EXIT_RUNTIME,
            "PID_INVALID",
            f"pid file points to a process outside this instance: {pid}",
            "process",
        )
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if not process_alive(pid):
            paths.pid_file.unlink(missing_ok=True)
            return success({"instance_id": args.id, "stopped": True, "pid": pid})
        time.sleep(0.2)
    raise CommandFailure(EXIT_RUNTIME, "PROCESS_STOP_TIMEOUT", f"process {pid} did not stop", "process")


def command_instance_status(args: argparse.Namespace) -> int:
    paths = instance_paths(args.data_root, args.slug)
    pid = read_pid(paths.pid_file)
    pid_process_alive = process_alive(pid) if pid is not None else False
    pid_owner_valid = process_owned_by_instance(pid, paths) if pid is not None and pid_process_alive else False
    alive = pid_owner_valid
    listening = port_open(args.host, args.port) if alive else False
    return success(
        {
            "instance_id": args.id,
            "layer": "process",
            "data": {
                "install_root": str(paths.root),
                "manifest_exists": paths.manifest.exists(),
                "pid": pid,
                "process_alive": alive,
                "pid_process_alive": pid_process_alive,
                "pid_owner_valid": pid_owner_valid,
                "port": args.port,
                "port_listening": listening,
                "log_path": str(paths.log_file),
            },
        }
    )


def command_instance_ready(args: argparse.Namespace) -> int:
    url = f"http://{args.host}:{args.port}/system_stats"
    try:
        with urlopen(url, timeout=args.timeout) as response:
            ready = 200 <= response.status < 300
    except URLError as exc:
        return success({"instance_id": args.id, "ready": False, "layer": "comfy", "data": {"url": url, "reason": str(exc)}})
    return success({"instance_id": args.id, "ready": ready, "layer": "comfy", "data": {"url": url}})


def command_instance_logs(args: argparse.Namespace) -> int:
    paths = instance_paths(args.data_root, args.slug)
    if not paths.log_file.exists():
        return success({"instance_id": args.id, "log_path": str(paths.log_file), "lines": []})
    lines = paths.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return success({"instance_id": args.id, "log_path": str(paths.log_file), "lines": lines[-args.tail :]})


def add_instance_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--data-root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="comfyctl")
    subparsers = parser.add_subparsers(dest="resource", required=True)

    host = subparsers.add_parser("host")
    host_sub = host.add_subparsers(dest="action", required=True)
    host_probe = host_sub.add_parser("probe")
    host_probe.add_argument("--data-root", required=True)
    host_probe.add_argument("--json", action="store_true")
    host_probe.set_defaults(func=command_host_probe)

    model_root = subparsers.add_parser("model-root")
    model_root_sub = model_root.add_subparsers(dest="action", required=True)
    model_root_check = model_root_sub.add_parser("check")
    model_root_check.add_argument("--path", required=True)
    model_root_check.add_argument("--json", action="store_true")
    model_root_check.set_defaults(func=command_model_root_check)

    instance = subparsers.add_parser("instance")
    instance_sub = instance.add_subparsers(dest="action", required=True)

    install = instance_sub.add_parser("install")
    add_instance_common(install)
    install.add_argument("--repo", required=True)
    install.add_argument("--ref", required=True)
    install.add_argument("--python", required=True)
    install.add_argument("--torch-profile", required=True)
    install.add_argument("--json", action="store_true")
    install.set_defaults(func=command_instance_install)

    start = instance_sub.add_parser("start")
    add_instance_common(start)
    start.add_argument("--host", required=True)
    start.add_argument("--port", type=int, required=True)
    start.add_argument("--extra-model-paths", dest="model_root", action="append", default=[])
    start.add_argument("--gpu", action="append", default=[])
    start.add_argument("--startup-timeout", type=float, default=15)
    start.add_argument("--json", action="store_true")
    start.set_defaults(func=command_instance_start)

    stop = instance_sub.add_parser("stop")
    add_instance_common(stop)
    stop.add_argument("--timeout", type=float, default=10)
    stop.add_argument("--json", action="store_true")
    stop.set_defaults(func=command_instance_stop)

    status = instance_sub.add_parser("status")
    add_instance_common(status)
    status.add_argument("--host", required=True)
    status.add_argument("--port", type=int, required=True)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_instance_status)

    ready = instance_sub.add_parser("ready")
    add_instance_common(ready)
    ready.add_argument("--host", required=True)
    ready.add_argument("--port", type=int, required=True)
    ready.add_argument("--timeout", type=float, default=2)
    ready.add_argument("--json", action="store_true")
    ready.set_defaults(func=command_instance_ready)

    logs = instance_sub.add_parser("logs")
    add_instance_common(logs)
    logs.add_argument("--tail", type=int, default=200)
    logs.set_defaults(func=command_instance_logs)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except CommandFailure as exc:
        return failure(exc)
    except ValueError as exc:
        return failure(CommandFailure(EXIT_USAGE, "REQUEST_INVALID", str(exc), "config"))


if __name__ == "__main__":
    raise SystemExit(main())

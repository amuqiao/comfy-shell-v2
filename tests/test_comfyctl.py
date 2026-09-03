import json
import os
import socket
import subprocess
import sys

from comfyctl.cli import (
    is_torch_requirement,
    parse_nvidia_smi_cuda_version,
    runtime_recommendation,
    torch_requirements,
    write_extra_model_paths,
    write_requirements_without_torch,
)


def run_comfyctl(*args: str, env: dict[str, str] | None = None):
    process_env = os.environ.copy()
    if env is not None:
        process_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "comfyctl.cli", *args],
        text=True,
        capture_output=True,
        check=False,
        env=process_env,
    )


def write_executable(path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fake_tool_env(tmp_path, *, fail_clone: bool = False, fail_uv: bool = False, fail_pip: bool = False) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(
        bin_dir / "git",
        """#!/bin/sh
if [ "$1" = "ls-remote" ]; then
  echo "abc123 refs/heads/main"
  exit 0
fi
if [ "$1" = "clone" ]; then
  last=""
  for arg in "$@"; do
    last="$arg"
  done
  if [ "${FAKE_GIT_FAIL_CLONE:-}" = "1" ]; then
    echo "clone failed" >&2
    exit 1
  fi
  mkdir -p "$last"
  touch "$last/main.py"
  cat > "$last/requirements.txt" <<'REQ'
torch
torchsde
torchvision
torchaudio
numpy>=1.25.0
REQ
  exit 0
fi
if [ "$1" = "checkout" ]; then
  exit 0
fi
if [ "$1" = "rev-parse" ] && [ "$2" = "HEAD" ]; then
  echo "abc123"
  exit 0
fi
exit 1
""",
    )
    write_executable(
        bin_dir / "uv",
        """#!/bin/sh
if [ "$1" = "venv" ]; then
  last=""
  for arg in "$@"; do
    last="$arg"
  done
  if [ "${FAKE_UV_FAIL:-}" = "1" ]; then
    echo "uv failed" >&2
    exit 1
  fi
  mkdir -p "$last/bin"
  cat > "$last/bin/python" <<'PYTHON'
#!/bin/sh
if [ "$1" = "-c" ]; then
  printf '%s\n' '{"torch": "2.6.0+cu124", "torch_cuda": "12.4", "torchaudio": "2.6.0+cu124", "torchvision": "0.21.0+cu124"}'
fi
exit 0
PYTHON
  chmod +x "$last/bin/python"
  exit 0
fi
if [ "$1" = "pip" ] && [ "$2" = "install" ]; then
  if [ "${FAKE_PIP_FAIL:-}" = "1" ]; then
    echo "pip failed" >&2
    exit 1
  fi
  if [ -n "${FAKE_UV_LOG:-}" ]; then
    printf '%s\n' "$*" >> "$FAKE_UV_LOG"
  fi
  exit 0
fi
exit 1
""",
    )
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    if fail_clone:
        env["FAKE_GIT_FAIL_CLONE"] = "1"
    if fail_uv:
        env["FAKE_UV_FAIL"] = "1"
    if fail_pip:
        env["FAKE_PIP_FAIL"] = "1"
    return env


def fake_nvidia_smi_env(tmp_path) -> dict[str, str]:
    bin_dir = tmp_path / "gpu-bin"
    bin_dir.mkdir()
    write_executable(
        bin_dir / "nvidia-smi",
        """#!/bin/sh
if [ "$1" = "--query-gpu=index,name,memory.total,driver_version" ]; then
  printf '%s\n' '0, NVIDIA A10, 23028, 550.127.08'
  printf '%s\n' '1, NVIDIA A10, 23028, 550.127.08'
  exit 0
fi
cat <<'OUT'
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.127.08             Driver Version: 550.127.08     CUDA Version: 12.4     |
+-----------------------------------------------------------------------------------------+
OUT
exit 0
""",
    )
    return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}


def test_parse_nvidia_smi_cuda_version():
    assert parse_nvidia_smi_cuda_version("Driver Version: 550.127.08     CUDA Version: 12.4") == "12.4"
    assert parse_nvidia_smi_cuda_version("no cuda here") is None


def test_runtime_recommendation_prefers_cu124_for_cuda_124():
    recommendation = runtime_recommendation(
        cuda_version="12.4",
        gpus=[{"index": "0", "name": "NVIDIA A10", "memory_total_mb": "23028", "driver_version": "550.127.08"}],
    )

    assert recommendation["python_version"] == "3.12"
    assert recommendation["torch_profile"] == "cu124"
    assert recommendation["gpu_ids"] == ["0"]
    assert recommendation["comfy_ref"] == "8b099de36acd81acd1afa3b5442951dc847e0a52"
    assert recommendation["warnings"] == []


def test_host_probe_creates_data_directories(tmp_path):
    result = run_comfyctl("host", "probe", "--data-root", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["data_root"] == str(tmp_path)
    assert payload["data"]["installs_dir"] == str(tmp_path / "ComfyUI-Installs")
    assert payload["data"]["shared_dir"] == str(tmp_path / "ComfyUI-Shared")
    assert payload["data"]["default_models_root"] == str(tmp_path / "ComfyUI-Shared" / "models")
    assert payload["data"]["default_input_root"] == str(tmp_path / "ComfyUI-Shared" / "input")
    assert payload["data"]["default_output_root"] == str(tmp_path / "ComfyUI-Shared" / "output")
    assert payload["data"]["download_cache_dir"] == str(tmp_path / "ComfyUI-Cache" / "download-cache")
    assert (tmp_path / "ComfyUI-Installs").is_dir()
    assert (tmp_path / "ComfyUI-Shared" / "models").is_dir()
    assert (tmp_path / "ComfyUI-Cache" / "download-cache").is_dir()


def test_host_probe_reports_gpu_runtime_recommendation(tmp_path):
    result = run_comfyctl("host", "probe", "--data-root", str(tmp_path), "--json", env=fake_nvidia_smi_env(tmp_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["driver_version"] == "550.127.08"
    assert payload["data"]["cuda_version"] == "12.4"
    assert payload["data"]["gpus"][0]["name"] == "NVIDIA A10"
    assert payload["data"]["runtime_recommendation"] == {
        "comfy_ref": "8b099de36acd81acd1afa3b5442951dc847e0a52",
        "python_version": "3.12",
        "torch_profile": "cu124",
        "gpu_ids": ["0"],
        "reason": "Detected NVIDIA CUDA 12.4; use the verified cu124 runtime and compatible ComfyUI ref.",
        "warnings": [],
    }


def test_instance_status_uses_derived_install_root(tmp_path):
    result = run_comfyctl(
        "instance",
        "status",
        "--id",
        "inst-1",
        "--slug",
        "comfy-prod",
        "--data-root",
        str(tmp_path),
        "--host",
        "127.0.0.1",
        "--port",
        "8188",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["install_root"] == str(tmp_path / "ComfyUI-Installs" / "comfy-prod")
    assert payload["data"]["process_alive"] is False


def test_invalid_slug_returns_request_invalid(tmp_path):
    result = run_comfyctl(
        "instance",
        "status",
        "--id",
        "inst-1",
        "--slug",
        "../escape",
        "--data-root",
        str(tmp_path),
        "--host",
        "127.0.0.1",
        "--port",
        "8188",
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error_code"] == "REQUEST_INVALID"


def test_extra_model_paths_uses_comfy_string_fields(tmp_path):
    path = tmp_path / "extra_model_paths.yaml"

    write_extra_model_paths(path, ["/data/wangqiao/ComfyUI-Shared/models"])

    assert path.read_text(encoding="utf-8") == (
        "comfy_shell:\n"
        "  base_path: /\n"
        "  checkpoints: |\n"
        "    /data/wangqiao/ComfyUI-Shared/models\n"
    )


def test_empty_extra_model_paths_uses_empty_string(tmp_path):
    path = tmp_path / "extra_model_paths.yaml"

    write_extra_model_paths(path, [])

    assert path.read_text(encoding="utf-8") == "comfy_shell:\n  base_path: /\n  checkpoints: ''\n"


def test_requirements_without_torch_keeps_other_torch_prefixed_packages(tmp_path):
    source = tmp_path / "requirements.txt"
    target = tmp_path / "requirements-without-torch.txt"
    source.write_text(
        "\n".join(
            [
                "torch",
                "torchvision>=0.20",
                "torchaudio",
                "torchsde",
                "numpy>=1.25.0",
                "# torch comment only",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    write_requirements_without_torch(source, target)

    assert target.read_text(encoding="utf-8") == "torchsde\nnumpy>=1.25.0\n# torch comment only\n"
    assert is_torch_requirement("torch")
    assert is_torch_requirement("torchvision>=0.20")
    assert is_torch_requirement("torchaudio")
    assert not is_torch_requirement("torchsde")


def test_torch_requirements_preserves_upstream_constraints(tmp_path):
    source = tmp_path / "requirements.txt"
    source.write_text("torch==2.6.0\ntorchvision>=0.21\ntorchaudio\nnumpy\n", encoding="utf-8")

    assert torch_requirements(source) == ["torch==2.6.0", "torchvision>=0.21", "torchaudio"]


def test_torch_requirements_uses_cu124_profile_pins_for_bare_requirements(tmp_path):
    source = tmp_path / "requirements.txt"
    source.write_text("torch\ntorchsde\ntorchvision\ntorchaudio\nnumpy\n", encoding="utf-8")

    assert torch_requirements(source, torch_profile="cu124") == [
        "torch==2.6.0+cu124",
        "torchvision==0.21.0+cu124",
        "torchaudio==2.6.0+cu124",
    ]


def test_torch_requirements_overrides_upstream_constraints_for_cu124_profile(tmp_path):
    source = tmp_path / "requirements.txt"
    source.write_text("torch==2.6.0\ntorchvision>=0.21\ntorchaudio\nnumpy\n", encoding="utf-8")

    assert torch_requirements(source, torch_profile="cu124") == [
        "torch==2.6.0+cu124",
        "torchvision==0.21.0+cu124",
        "torchaudio==2.6.0+cu124",
    ]


def test_install_clone_failure_preserves_active_instance(tmp_path):
    assert_install_failure_preserves_active_instance(tmp_path, expected_error="GIT_FAILED", env=fake_tool_env(tmp_path, fail_clone=True))


def test_install_uv_failure_preserves_active_instance(tmp_path):
    assert_install_failure_preserves_active_instance(tmp_path, expected_error="UV_FAILED", env=fake_tool_env(tmp_path, fail_uv=True))


def test_install_pip_failure_preserves_active_instance(tmp_path):
    assert_install_failure_preserves_active_instance(
        tmp_path,
        expected_error="PYTHON_DEPENDENCY_FAILED",
        env=fake_tool_env(tmp_path, fail_pip=True),
    )


def test_install_uses_uv_pip_without_venv_pip(tmp_path):
    uv_log = tmp_path / "uv.log"
    env = fake_tool_env(tmp_path)
    env["FAKE_UV_LOG"] = str(uv_log)

    result = run_comfyctl(
        "instance",
        "install",
        "--id",
        "inst-1",
        "--slug",
        "comfy-prod",
        "--data-root",
        str(tmp_path),
        "--repo",
        "https://example.invalid/ComfyUI.git",
        "--ref",
        "main",
        "--python",
        "3.12",
        "--torch-profile",
        "requirements",
        "--json",
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert (tmp_path / "ComfyUI-Installs" / "comfy-prod" / "ComfyUI").is_dir()
    assert (tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".venv" / "bin" / "python").is_file()
    assert not (tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".venv" / "bin" / "pip").exists()
    manifest = json.loads((tmp_path / "ComfyUI-Installs" / "comfy-prod" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["torch_versions"] == {
        "torch": "2.6.0+cu124",
        "torch_cuda": "12.4",
        "torchaudio": "2.6.0+cu124",
        "torchvision": "0.21.0+cu124",
    }
    logged = uv_log.read_text(encoding="utf-8")
    assert "pip install --python" in logged
    assert "/ComfyUI-Installs/comfy-prod/.staging/" in logged
    assert "/.venv/bin/python -r " in logged


def test_install_cu124_profile_installs_torch_from_cuda_index(tmp_path):
    uv_log = tmp_path / "uv.log"
    env = fake_tool_env(tmp_path)
    env["FAKE_UV_LOG"] = str(uv_log)

    result = run_comfyctl(
        "instance",
        "install",
        "--id",
        "inst-1",
        "--slug",
        "comfy-prod",
        "--data-root",
        str(tmp_path),
        "--repo",
        "https://example.invalid/ComfyUI.git",
        "--ref",
        "main",
        "--python",
        "3.12",
        "--torch-profile",
        "cu124",
        "--json",
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    logged = uv_log.read_text(encoding="utf-8").splitlines()
    assert logged[0].endswith(
        "--torch-backend cu124 torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124"
    )
    assert "requirements-without-torch.txt" in logged[1]
    assert "/ComfyUI/requirements-without-torch.txt" in logged[1]
    assert "--torch-backend cu124" not in logged[1]


def assert_install_failure_preserves_active_instance(tmp_path, *, expected_error: str, env: dict[str, str]) -> None:
    active_checkout = tmp_path / "ComfyUI-Installs" / "comfy-prod" / "ComfyUI"
    active_venv = tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".venv"
    active_checkout.mkdir(parents=True)
    active_venv.mkdir()
    (active_checkout / "active.txt").write_text("old checkout", encoding="utf-8")
    (active_venv / "active.txt").write_text("old venv", encoding="utf-8")

    result = run_comfyctl(
        "instance",
        "install",
        "--id",
        "inst-1",
        "--slug",
        "comfy-prod",
        "--data-root",
        str(tmp_path),
        "--repo",
        "https://example.invalid/ComfyUI.git",
        "--ref",
        "main",
        "--python",
        "3.12",
        "--torch-profile",
        "requirements",
        "--json",
        env=env,
    )

    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error_code"] == expected_error
    assert (active_checkout / "active.txt").read_text(encoding="utf-8") == "old checkout"
    assert (active_venv / "active.txt").read_text(encoding="utf-8") == "old venv"


def test_start_failure_does_not_write_pid_file(tmp_path):
    checkout = tmp_path / "ComfyUI-Installs" / "comfy-prod" / "ComfyUI"
    python = tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".venv" / "bin" / "python"
    checkout.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    (checkout / "main.py").write_text("", encoding="utf-8")
    write_executable(python, "#!/bin/sh\necho boot failed\nexit 7\n")

    result = run_comfyctl(
        "instance",
        "start",
        "--id",
        "inst-1",
        "--slug",
        "comfy-prod",
        "--data-root",
        str(tmp_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(free_port()),
        "--startup-timeout",
        "1",
        "--json",
    )

    assert result.returncode == 5
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error_code"] == "PROCESS_START_FAILED"
    assert "boot failed" in payload["stderr_tail"]
    assert not (tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".run" / "comfyui.pid").exists()


def test_stop_rejects_pid_owned_by_another_process(tmp_path):
    pid_file = tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".run" / "comfyui.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    result = run_comfyctl(
        "instance",
        "stop",
        "--id",
        "inst-1",
        "--slug",
        "comfy-prod",
        "--data-root",
        str(tmp_path),
        "--json",
    )

    assert result.returncode == 5
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error_code"] == "PID_INVALID"
    assert pid_file.exists()


def test_status_does_not_treat_unowned_pid_as_running(tmp_path):
    pid_file = tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".run" / "comfyui.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    result = run_comfyctl(
        "instance",
        "status",
        "--id",
        "inst-1",
        "--slug",
        "comfy-prod",
        "--data-root",
        str(tmp_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(free_port()),
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["pid_process_alive"] is True
    assert payload["data"]["pid_owner_valid"] is False
    assert payload["data"]["process_alive"] is False

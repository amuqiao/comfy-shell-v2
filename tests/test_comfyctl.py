import json
import os
import socket
import subprocess
import sys


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
  touch "$last/requirements.txt"
  exit 0
fi
if [ "$1" = "checkout" ]; then
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
  cat > "$last/bin/pip" <<'PIP'
#!/bin/sh
if [ "${FAKE_PIP_FAIL:-}" = "1" ]; then
  echo "pip failed" >&2
  exit 1
fi
exit 0
PIP
  chmod +x "$last/bin/pip"
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


def test_host_probe_creates_data_directories(tmp_path):
    result = run_comfyctl("host", "probe", "--data-root", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["data_root"] == str(tmp_path)
    assert (tmp_path / "ComfyUI-Installs").is_dir()
    assert (tmp_path / "ComfyUI-Shared" / "models").is_dir()
    assert (tmp_path / "ComfyUI-Cache" / "download-cache").is_dir()


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

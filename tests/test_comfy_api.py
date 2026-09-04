import socket
import subprocess
import sys

from fastapi.testclient import TestClient


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-service-key"}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_executable(path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def spawn_owned_instance_process(tmp_path, slug: str) -> subprocess.Popen[str]:
    checkout = tmp_path / "ComfyUI-Installs" / slug / "ComfyUI"
    run_dir = tmp_path / "ComfyUI-Installs" / slug / ".run"
    checkout.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "main.py"],
        cwd=checkout,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (run_dir / "comfyui.pid").write_text(str(process.pid), encoding="utf-8")
    return process


def test_comfy_single_host_flow(sqlite_app):
    with TestClient(sqlite_app) as client:
        catalog = client.get("/v1/catalog", headers=auth_headers())
        assert catalog.status_code == 200
        catalog_data = catalog.json()["data"]
        assert catalog_data["versions"][0]["id"] == "comfyui-0.27.0-verified"
        assert catalog_data["versions"][0]["source_type"] == "snapshot"
        assert catalog_data["runtime_profiles"][0]["id"] == "nvidia-cu124-py312-torch260"

        hosts = client.get("/v1/hosts", headers=auth_headers())
        assert hosts.status_code == 200
        host = hosts.json()["data"]["hosts"][0]
        assert host["name"] == "local"
        assert host["connection"] == "local"

        model_roots = client.get("/v1/model-roots", params={"host_id": host["id"]}, headers=auth_headers())
        assert model_roots.status_code == 200
        model_root = model_roots.json()["data"]["model_roots"][0]
        assert model_root["path"].endswith("/ComfyUI-Shared/models")

        probe = client.post(f"/v1/hosts/{host['id']}/probe", json={}, headers=auth_headers())
        assert probe.status_code == 200
        probe_data = probe.json()["data"]["data"]
        assert "driver_version" in probe_data
        assert "cuda_version" in probe_data
        assert "gpus" in probe_data
        assert "comfy_ref" in probe_data["runtime_recommendation"]
        assert "version_id" in probe_data["runtime_recommendation"]
        assert "version_source_type" in probe_data["runtime_recommendation"]
        assert "runtime_profile_id" in probe_data["runtime_recommendation"]
        assert probe_data["runtime_recommendation"]["python_version"] == "3.12"
        assert probe_data["runtime_recommendation"]["torch_profile"] in {"requirements", "cu124"}

        created = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Comfy Prod",
                "instance_slug": "comfy-prod",
                "comfy_version_id": "comfyui-0.27.0-verified",
                "runtime_profile_id": "nvidia-cu124-py312-torch260",
                "comfy_port": 8188,
                "model_root_ids": [model_root["id"]],
            },
            headers=auth_headers(),
        )
        assert created.status_code == 201
        instance = created.json()["data"]
        assert instance["install_root"].endswith("/ComfyUI-Installs/comfy-prod")
        assert instance["comfy_ref"] == "8b099de36acd81acd1afa3b5442951dc847e0a52"
        assert instance["python_version"] == "3.12"
        assert instance["torch_profile"] == "cu124"
        assert instance["model_root_ids"] == [model_root["id"]]

        fetched = client.get(f"/v1/instances/{instance['id']}", headers=auth_headers())
        assert fetched.status_code == 200
        assert fetched.json()["data"]["id"] == instance["id"]

        updated = client.patch(
            f"/v1/instances/{instance['id']}/launch-config",
            json={"comfy_port": free_port(), "gpu_ids": ["0"]},
            headers=auth_headers(),
        )
        assert updated.status_code == 200
        updated_instance = updated.json()["data"]
        assert updated_instance["comfy_port"] != 8188
        assert updated_instance["gpu_ids"] == ["0"]

        listed = client.get("/v1/instances", headers=auth_headers())
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()["data"]["instances"]] == [instance["id"]]

        status = client.get(f"/v1/instances/{instance['id']}/status", headers=auth_headers())
        assert status.status_code == 200
        assert status.json()["data"]["data"]["manifest_exists"] is False

        logs = client.get(f"/v1/instances/{instance['id']}/logs", headers=auth_headers())
        assert logs.status_code == 200
        assert logs.json()["data"]["lines"] == []


def test_create_instance_rejects_duplicate_slug(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        payload = {
            "host_id": host["id"],
            "name": "Dup",
            "instance_slug": "dup",
            "comfy_ref": "master",
            "comfy_port": 8188,
        }
        first = client.post("/v1/instances", json=payload, headers=auth_headers())
        second = client.post("/v1/instances", json=payload, headers=auth_headers())

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "INSTANCE_SLUG_CONFLICT"


def test_create_instance_rejects_catalog_and_raw_field_mix(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        response = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Mixed",
                "instance_slug": "mixed",
                "comfy_version_id": "comfyui-0.27.0-verified",
                "comfy_ref": "master",
                "comfy_port": 8188,
            },
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"
    assert response.json()["details"]["field"] == "comfy_ref"


def test_create_instance_rejects_unknown_catalog_id(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        response = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Unknown",
                "instance_slug": "unknown",
                "comfy_version_id": "missing-version",
                "comfy_port": 8188,
            },
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"
    assert response.json()["details"]["field"] == "comfy_version_id"


def test_create_instance_rejects_runtime_profile_and_raw_field_mix(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        response = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Runtime Mixed",
                "instance_slug": "runtime-mixed",
                "runtime_profile_id": "nvidia-cu124-py312-torch260",
                "torch_profile": "cu124",
                "comfy_port": 8188,
            },
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"
    assert response.json()["details"]["field"] == "runtime_profile_id"


def test_create_instance_rejects_unknown_runtime_profile_id(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        response = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Unknown Runtime",
                "instance_slug": "unknown-runtime",
                "runtime_profile_id": "missing-runtime",
                "comfy_port": 8188,
            },
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"
    assert response.json()["details"]["field"] == "runtime_profile_id"


def test_create_instance_defaults_to_verified_catalog_version(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        response = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Default",
                "instance_slug": "default",
                "comfy_port": 8188,
            },
            headers=auth_headers(),
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["comfy_ref"] == "8b099de36acd81acd1afa3b5442951dc847e0a52"
    assert data["python_version"] == "3.12"
    assert data["torch_profile"] == "requirements"


def test_update_instance_launch_config_changes_port_gpu_and_model_root(sqlite_app, tmp_path):
    first_models = tmp_path / "first-models"
    second_models = tmp_path / "second-models"
    first_models.mkdir()
    second_models.mkdir()
    with TestClient(sqlite_app) as client:
        host = client.post(
            "/v1/hosts",
            json={"name": "launch-host", "connection": "local", "data_root": str(tmp_path)},
            headers=auth_headers(),
        ).json()["data"]
        first_root = client.post(
            "/v1/model-roots",
            json={"host_id": host["id"], "label": "First", "path": str(first_models)},
            headers=auth_headers(),
        ).json()["data"]
        second_root = client.post(
            "/v1/model-roots",
            json={"host_id": host["id"], "label": "Second", "path": str(second_models)},
            headers=auth_headers(),
        ).json()["data"]
        instance = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Launch",
                "instance_slug": "launch",
                "comfy_ref": "master",
                "comfy_port": 8188,
                "model_root_ids": [first_root["id"]],
            },
            headers=auth_headers(),
        ).json()["data"]

        response = client.patch(
            f"/v1/instances/{instance['id']}/launch-config",
            json={
                "comfy_port": free_port(),
                "gpu_ids": ["0", "1"],
                "model_root_ids": [second_root["id"]],
                "primary_model_root_id": second_root["id"],
            },
            headers=auth_headers(),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["comfy_port"] != 8188
    assert data["gpu_ids"] == ["0", "1"]
    assert data["model_root_ids"] == [second_root["id"]]
    assert data["primary_model_root_id"] == second_root["id"]


def test_update_instance_launch_config_rejects_foreign_model_root(sqlite_app, tmp_path):
    with TestClient(sqlite_app) as client:
        host = client.post(
            "/v1/hosts",
            json={"name": "main-host", "connection": "local", "data_root": str(tmp_path / "main")},
            headers=auth_headers(),
        ).json()["data"]
        foreign_host = client.post(
            "/v1/hosts",
            json={"name": "foreign-host", "connection": "local", "data_root": str(tmp_path / "foreign")},
            headers=auth_headers(),
        ).json()["data"]
        foreign_root = client.post(
            "/v1/model-roots",
            json={"host_id": foreign_host["id"], "label": "Foreign", "path": str(tmp_path / "foreign-models")},
            headers=auth_headers(),
        ).json()["data"]
        instance = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Launch",
                "instance_slug": "launch",
                "comfy_ref": "master",
                "comfy_port": 8188,
            },
            headers=auth_headers(),
        ).json()["data"]

        response = client.patch(
            f"/v1/instances/{instance['id']}/launch-config",
            json={"model_root_ids": [foreign_root["id"]]},
            headers=auth_headers(),
        )

    assert response.status_code == 404
    assert response.json()["code"] == "MODEL_ROOT_NOT_FOUND"


def test_update_instance_launch_config_rejects_duplicate_model_roots(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        model_root = client.get("/v1/model-roots", params={"host_id": host["id"]}, headers=auth_headers()).json()["data"][
            "model_roots"
        ][0]
        instance = client.post(
            "/v1/instances",
            json={"host_id": host["id"], "name": "Duplicate Root", "instance_slug": "duplicate-root", "comfy_ref": "master"},
            headers=auth_headers(),
        ).json()["data"]

        response = client.patch(
            f"/v1/instances/{instance['id']}/launch-config",
            json={"model_root_ids": [model_root["id"], model_root["id"]]},
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"


def test_create_instance_rejects_duplicate_model_roots(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        model_root = client.get("/v1/model-roots", params={"host_id": host["id"]}, headers=auth_headers()).json()["data"][
            "model_roots"
        ][0]

        response = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Duplicate Root Create",
                "instance_slug": "duplicate-root-create",
                "comfy_ref": "master",
                "model_root_ids": [model_root["id"], model_root["id"]],
            },
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"


def test_update_instance_launch_config_requires_a_field(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        instance = client.post(
            "/v1/instances",
            json={"host_id": host["id"], "name": "Empty", "instance_slug": "empty", "comfy_ref": "master"},
            headers=auth_headers(),
        ).json()["data"]

        response = client.patch(f"/v1/instances/{instance['id']}/launch-config", json={}, headers=auth_headers())

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"


def test_install_rejects_running_instance(sqlite_app, tmp_path):
    process = spawn_owned_instance_process(tmp_path, "running-install")
    try:
        with TestClient(sqlite_app) as client:
            host = client.post(
                "/v1/hosts",
                json={"name": "running-host", "connection": "local", "data_root": str(tmp_path)},
                headers=auth_headers(),
            ).json()["data"]
            instance = client.post(
                "/v1/instances",
                json={
                    "host_id": host["id"],
                    "name": "Running Install",
                    "instance_slug": "running-install",
                    "comfy_ref": "master",
                    "comfy_port": free_port(),
                },
                headers=auth_headers(),
            ).json()["data"]

            status = client.get(f"/v1/instances/{instance['id']}/status", headers=auth_headers())
            response = client.post(f"/v1/instances/{instance['id']}/install", json={}, headers=auth_headers())

        assert status.status_code == 200
        assert status.json()["data"]["data"]["process_alive"] is True
        assert response.status_code == 409
        assert response.json()["code"] == "INSTANCE_RUNNING"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_reinstall_rejects_running_instance(sqlite_app, tmp_path):
    process = spawn_owned_instance_process(tmp_path, "running-reinstall")
    try:
        with TestClient(sqlite_app) as client:
            host = client.post(
                "/v1/hosts",
                json={"name": "running-host-reinstall", "connection": "local", "data_root": str(tmp_path)},
                headers=auth_headers(),
            ).json()["data"]
            instance = client.post(
                "/v1/instances",
                json={
                    "host_id": host["id"],
                    "name": "Running Reinstall",
                    "instance_slug": "running-reinstall",
                    "comfy_ref": "master",
                    "comfy_port": free_port(),
                },
                headers=auth_headers(),
            ).json()["data"]

            status = client.get(f"/v1/instances/{instance['id']}/status", headers=auth_headers())
            response = client.post(f"/v1/instances/{instance['id']}/reinstall", json={}, headers=auth_headers())

        assert status.status_code == 200
        assert status.json()["data"]["data"]["process_alive"] is True
        assert response.status_code == 409
        assert response.json()["code"] == "INSTANCE_RUNNING"
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_install_rejects_invalid_pid_file(sqlite_app, tmp_path):
    with TestClient(sqlite_app) as client:
        host = client.post(
            "/v1/hosts",
            json={"name": "invalid-pid-host", "connection": "local", "data_root": str(tmp_path)},
            headers=auth_headers(),
        ).json()["data"]
        instance = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Invalid PID",
                "instance_slug": "invalid-pid",
                "comfy_ref": "master",
                "comfy_port": free_port(),
            },
            headers=auth_headers(),
        ).json()["data"]
        pid_file = tmp_path / "ComfyUI-Installs" / "invalid-pid" / ".run" / "comfyui.pid"
        pid_file.parent.mkdir(parents=True)
        pid_file.write_text("not-a-pid", encoding="utf-8")

        response = client.post(f"/v1/instances/{instance['id']}/install", json={}, headers=auth_headers())

    assert response.status_code == 500
    assert response.json()["code"] == "PID_INVALID"


def test_reinstall_rejects_invalid_pid_file(sqlite_app, tmp_path):
    with TestClient(sqlite_app) as client:
        host = client.post(
            "/v1/hosts",
            json={"name": "invalid-pid-host-reinstall", "connection": "local", "data_root": str(tmp_path)},
            headers=auth_headers(),
        ).json()["data"]
        instance = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Invalid PID Reinstall",
                "instance_slug": "invalid-pid-reinstall",
                "comfy_ref": "master",
                "comfy_port": free_port(),
            },
            headers=auth_headers(),
        ).json()["data"]
        pid_file = tmp_path / "ComfyUI-Installs" / "invalid-pid-reinstall" / ".run" / "comfyui.pid"
        pid_file.parent.mkdir(parents=True)
        pid_file.write_text("not-a-pid", encoding="utf-8")

        response = client.post(f"/v1/instances/{instance['id']}/reinstall", json={}, headers=auth_headers())

    assert response.status_code == 500
    assert response.json()["code"] == "PID_INVALID"


def test_install_request_rejects_catalog_and_raw_field_mix(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        instance = client.post(
            "/v1/instances",
            json={"host_id": host["id"], "name": "Install Mixed", "instance_slug": "install-mixed", "comfy_ref": "master"},
            headers=auth_headers(),
        ).json()["data"]

        response = client.post(
            f"/v1/instances/{instance['id']}/install",
            json={"comfy_version_id": "comfyui-0.27.0-verified", "comfy_ref": "master"},
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"
    assert response.json()["details"]["field"] == "comfy_ref"


def test_reinstall_request_rejects_unknown_catalog_id(sqlite_app):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        instance = client.post(
            "/v1/instances",
            json={"host_id": host["id"], "name": "Reinstall Unknown", "instance_slug": "reinstall-unknown", "comfy_ref": "master"},
            headers=auth_headers(),
        ).json()["data"]

        response = client.post(
            f"/v1/instances/{instance['id']}/reinstall",
            json={"comfy_version_id": "missing-version"},
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"
    assert response.json()["details"]["field"] == "comfy_version_id"


def test_create_host_rejects_ssh_in_p1(sqlite_app):
    with TestClient(sqlite_app) as client:
        response = client.post(
            "/v1/hosts",
            json={"name": "remote", "connection": "ssh", "ssh_target": "user@gpu"},
            headers=auth_headers(),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "EXECUTOR_UNSUPPORTED"


def test_model_root_check_reports_filesystem(sqlite_app, tmp_path):
    with TestClient(sqlite_app) as client:
        host = client.get("/v1/hosts", headers=auth_headers()).json()["data"]["hosts"][0]
        created = client.post(
            "/v1/model-roots",
            json={"host_id": host["id"], "label": "Tmp Models", "path": str(tmp_path)},
            headers=auth_headers(),
        )
        checked = client.post(
            f"/v1/model-roots/{created.json()['data']['id']}/check",
            headers=auth_headers(),
        )

    assert created.status_code == 201
    assert checked.status_code == 200
    assert checked.json()["data"]["exists"] is True
    assert checked.json()["data"]["is_dir"] is True


def test_status_propagates_comfyctl_failure(sqlite_app, tmp_path):
    with TestClient(sqlite_app) as client:
        host = client.post(
            "/v1/hosts",
            json={"name": "tmp-host", "connection": "local", "data_root": str(tmp_path)},
            headers=auth_headers(),
        ).json()["data"]
        created = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Comfy Prod",
                "instance_slug": "comfy-prod",
                "comfy_ref": "master",
                "comfy_port": 8188,
            },
            headers=auth_headers(),
        )
        instance = created.json()["data"]
        pid_file = tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".run" / "comfyui.pid"
        pid_file.parent.mkdir(parents=True)
        pid_file.write_text("not-a-pid", encoding="utf-8")

        response = client.get(f"/v1/instances/{instance['id']}/status", headers=auth_headers())

    assert response.status_code == 500
    assert response.json()["code"] == "PID_INVALID"


def test_start_failure_does_not_mark_instance_launched(sqlite_app, tmp_path):
    port = free_port()
    with TestClient(sqlite_app) as client:
        host = client.post(
            "/v1/hosts",
            json={"name": "start-fail-host", "connection": "local", "data_root": str(tmp_path)},
            headers=auth_headers(),
        ).json()["data"]
        created = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Comfy Prod",
                "instance_slug": "comfy-prod",
                "comfy_ref": "master",
                "comfy_port": port,
            },
            headers=auth_headers(),
        )
        instance = created.json()["data"]
        checkout = tmp_path / "ComfyUI-Installs" / "comfy-prod" / "ComfyUI"
        python = tmp_path / "ComfyUI-Installs" / "comfy-prod" / ".venv" / "bin" / "python"
        checkout.mkdir(parents=True)
        python.parent.mkdir(parents=True)
        (checkout / "main.py").write_text("", encoding="utf-8")
        write_executable(python, "#!/bin/sh\necho boot failed\nexit 7\n")

        started = client.post(f"/v1/instances/{instance['id']}/start", json={}, headers=auth_headers())
        fetched = client.get(f"/v1/instances/{instance['id']}", headers=auth_headers())

    assert started.status_code == 502
    assert started.json()["code"] == "PROCESS_START_FAILED"
    assert fetched.status_code == 200
    assert fetched.json()["data"]["last_launched_at"] is None


def test_comfy_api_requires_auth(sqlite_app):
    with TestClient(sqlite_app) as client:
        response = client.get("/v1/hosts")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"

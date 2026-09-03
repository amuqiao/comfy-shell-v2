import socket

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


def test_comfy_single_host_flow(sqlite_app):
    with TestClient(sqlite_app) as client:
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
        assert probe_data["runtime_recommendation"]["python_version"] == "3.12"
        assert probe_data["runtime_recommendation"]["torch_profile"] in {"requirements", "cu124"}

        created = client.post(
            "/v1/instances",
            json={
                "host_id": host["id"],
                "name": "Comfy Prod",
                "instance_slug": "comfy-prod",
                "comfy_ref": "master",
                "python_version": "3.12",
                "torch_profile": "cu124",
                "comfy_port": 8188,
                "model_root_ids": [model_root["id"]],
            },
            headers=auth_headers(),
        )
        assert created.status_code == 201
        instance = created.json()["data"]
        assert instance["install_root"].endswith("/ComfyUI-Installs/comfy-prod")
        assert instance["python_version"] == "3.12"
        assert instance["torch_profile"] == "cu124"
        assert instance["model_root_ids"] == [model_root["id"]]

        fetched = client.get(f"/v1/instances/{instance['id']}", headers=auth_headers())
        assert fetched.status_code == 200
        assert fetched.json()["data"]["id"] == instance["id"]

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

# Comfy Shell

`comfy-shell-v2` 是一个轻量 Linux ComfyUI Web 启动器。P1 形态是把 FastAPI 控制面部署在远端 GPU 机器上，本机 macOS 通过 SSH tunnel 打开 Web UI。

```text
macOS Browser
  -> ssh -L 7800:127.0.0.1:7800 user@gpu-host
  -> remote FastAPI control plane
  -> remote PostgreSQL
  -> local executor
  -> comfyctl
  -> ComfyUI-Installs/<instance_slug>
```

## What Is Included

- FastAPI control plane with success/error envelope and operation registry.
- PostgreSQL metadata for Host, ModelRoot, Instance, InstanceModelRoot, and CommandRun.
- `comfyctl` host-side CLI for probe, model root check, install, start, stop, status, ready, and logs.
- Derived data directories: `ComfyUI-Installs`, `ComfyUI-Shared`, and `ComfyUI-Cache`.
- Minimal Web UI at `/ui/`.
- Service scripts: `dev.sh`, `deploy.sh`, `run.sh`, `verify.sh`, `remote.sh`, `tools.sh`.

## Remote GPU Quick Start

On the remote GPU server:

```bash
uv sync
cp .env.example .env
./scripts/verify.sh check
./scripts/deploy.sh up compose-deps
./scripts/dev.sh migrate
./scripts/dev.sh start api
```

From macOS:

```bash
ssh -L 7800:127.0.0.1:7800 user@gpu-host
```

Open:

```text
http://127.0.0.1:7800/ui/
```

Use `SECURITY__SERVICE_API_KEY` from the remote `.env` as the Bearer token in the UI.

## Directory Model

If `COMFY__DATA_ROOT` is empty, the service install directory is the data root:

```text
comfy-shell-v2/
  ComfyUI-Installs/
    comfy-prod/
      ComfyUI/
      .venv/
      manifest.json
      extra_model_paths.yaml
      .run/
      logs/
  ComfyUI-Shared/
    models/
    input/
    output/
  ComfyUI-Cache/
    download-cache/
```

Model roots are outside instance installs. Reinstalling an instance replaces that instance checkout and `.venv`; it does not delete model directories.

## Common Commands

```bash
./scripts/verify.sh check
./scripts/dev.sh start api
./scripts/dev.sh status
./scripts/dev.sh stop api
./scripts/deploy.sh up compose-deps
./scripts/remote.sh status --host user@gpu-host --dir /data/wangqiao/comfy-shell-v2
./scripts/remote.sh logs --host user@gpu-host --dir /data/wangqiao/comfy-shell-v2
./scripts/remote.sh tunnel --host user@gpu-host --local-port 7800 --remote-port 7800
```

`scripts/dev.sh` manages only the FastAPI control plane. ComfyUI instance lifecycle is managed through the Web API and `comfyctl`.

## Documentation

- Docs index: [`docs/README.md`](docs/README.md)
- Current implementation facts: [`docs/current/implementation.md`](docs/current/implementation.md)
- HTTP API contract: [`docs/contracts/api-contract.md`](docs/contracts/api-contract.md)
- Linux ComfyUI launcher plan: [`docs/plans/linux-comfyui-web-launcher.md`](docs/plans/linux-comfyui-web-launcher.md)
- Scripts contract: [`scripts/README.md`](scripts/README.md)

## Verification

Default gate:

```bash
./scripts/verify.sh check
```

PostgreSQL gates:

```bash
./scripts/verify.sh postgres
./scripts/verify.sh migration-roundtrip
```

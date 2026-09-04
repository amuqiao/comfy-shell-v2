# API Contract

本文描述当前调用者可依赖的 HTTP 合同。内部实现细节见 [`../current/implementation.md`](../current/implementation.md)。

## Common Headers

| Header | Direction | Contract |
|---|---|---|
| `X-Request-ID` | request/response | 可由调用方传入；缺失时服务生成；非法值返回 `REQUEST_INVALID`。 |
| `X-Trace-ID` | request/response | 可由调用方传入；缺失时服务生成；非法值返回 `REQUEST_INVALID`。 |
| `Authorization` | request | 受保护接口使用 `Bearer <service_api_key>`。 |

## Envelope

成功响应：

```json
{
  "request_id": "req-...",
  "trace_id": "trace-...",
  "server_time": "2026-07-22T00:00:00Z",
  "code": "OK",
  "data": {}
}
```

错误响应：

```json
{
  "request_id": "req-...",
  "trace_id": "trace-...",
  "server_time": "2026-07-22T00:00:00Z",
  "code": "REQUEST_INVALID",
  "message": "Request is invalid.",
  "retryable": false,
  "details": {}
}
```

## Routes

下表使用默认 `SERVICE__API_PREFIX=/v1` 展示公开路径。代码中的 operation registry 保存未挂载业务路径，例如 `/instances`；运行时由 `SERVICE__API_PREFIX` 渲染成公开路径。

| Operation | Method / Path | Auth | Success | Stable Errors |
|---|---|---|---|---|
| `health` | `GET /health` | no | `200` | none |
| `ready` | `GET /ready` | no | `200` | `DEPENDENCY_UNAVAILABLE` |
| `get_comfy_catalog` | `GET /v1/catalog` | yes | `200` | `UNAUTHORIZED` |
| `list_hosts` | `GET /v1/hosts` | yes | `200` | `UNAUTHORIZED` |
| `create_host` | `POST /v1/hosts` | yes | `201` | `UNAUTHORIZED`, `REQUEST_INVALID`, `HOST_NAME_CONFLICT`, `EXECUTOR_UNSUPPORTED` |
| `probe_host` | `POST /v1/hosts/{host_id}/probe` | yes | `200` | `UNAUTHORIZED`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED` |
| `list_model_roots` | `GET /v1/model-roots` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID` |
| `create_model_root` | `POST /v1/model-roots` | yes | `201` | `UNAUTHORIZED`, `REQUEST_INVALID`, `HOST_NOT_FOUND`, `MODEL_ROOT_CONFLICT` |
| `check_model_root` | `POST /v1/model-roots/{model_root_id}/check` | yes | `200` | `UNAUTHORIZED`, `MODEL_ROOT_NOT_FOUND`, `COMFYCTL_FAILED` |
| `list_instances` | `GET /v1/instances` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID` |
| `create_instance` | `POST /v1/instances` | yes | `201` | `UNAUTHORIZED`, `REQUEST_INVALID`, `HOST_NOT_FOUND`, `MODEL_ROOT_NOT_FOUND`, `INSTANCE_SLUG_CONFLICT` |
| `get_instance` | `GET /v1/instances/{instance_id}` | yes | `200` | `UNAUTHORIZED`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND` |
| `install_instance` | `POST /v1/instances/{instance_id}/install` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED`, `PORT_IN_USE`, `INSTANCE_LOCKED`, `DEPENDENCY_MISSING`, `GIT_FAILED`, `UV_FAILED`, `PYTHON_DEPENDENCY_FAILED` |
| `reinstall_instance` | `POST /v1/instances/{instance_id}/reinstall` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED`, `PORT_IN_USE`, `INSTANCE_LOCKED`, `DEPENDENCY_MISSING`, `GIT_FAILED`, `UV_FAILED`, `PYTHON_DEPENDENCY_FAILED` |
| `start_instance` | `POST /v1/instances/{instance_id}/start` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED`, `PORT_IN_USE`, `INSTANCE_NOT_INSTALLED`, `VENV_MISSING`, `PROCESS_START_FAILED` |
| `stop_instance` | `POST /v1/instances/{instance_id}/stop` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED`, `PROCESS_STOP_TIMEOUT`, `PID_INVALID` |
| `status_instance` | `GET /v1/instances/{instance_id}/status` | yes | `200` | `UNAUTHORIZED`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED`, `PID_INVALID` |
| `ready_instance` | `GET /v1/instances/{instance_id}/ready` | yes | `200` | `UNAUTHORIZED`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED` |
| `logs_instance` | `GET /v1/instances/{instance_id}/logs` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID`, `INSTANCE_NOT_FOUND`, `HOST_NOT_FOUND`, `COMFYCTL_FAILED` |
| `list_runs` | `GET /v1/runs` | yes | `200` | `UNAUTHORIZED`, `REQUEST_INVALID` |
| `get_run` | `GET /v1/runs/{run_id}` | yes | `200` | `UNAUTHORIZED`, `RUN_NOT_FOUND` |

Cross-cutting errors such as `UNAUTHORIZED`, `REQUEST_INVALID`, and `INTERNAL_ERROR` are defined by the common error contract. `app/api/operations.py` tracks route-specific business errors; the table above lists the caller-visible union where useful.

`GET /ready` returns `200` with `data.status=ok` when all checks pass. If only optional checks fail, it still returns `200` with `data.status=degraded`. If any required check fails, it returns `503 DEPENDENCY_UNAVAILABLE`.

## Comfy Request Shapes

`POST /v1/hosts`:

```json
{
  "name": "local",
  "connection": "local",
  "service_root": "/data/wangqiao/comfy-shell-v2",
  "data_root": "/data/wangqiao/comfy-shell-v2"
}
```

`POST /v1/model-roots`:

```json
{
  "host_id": "uuid",
  "label": "Shared Models",
  "path": "/data/wangqiao/comfy-shell-v2/ComfyUI-Shared/models"
}
```

`GET /v1/catalog` 返回当前服务支持的 ComfyUI 版本选项、runtime profile 和推荐规则。调用方应优先保存和提交
`comfy_version_id` 与 `runtime_profile_id`，不要让普通用户直接处理 commit SHA、Python 版本和 torch wheel 组合。

```json
{
  "schema_version": 1,
  "github": {
    "repo": "comfyanonymous/ComfyUI",
    "url": "https://github.com/comfyanonymous/ComfyUI.git",
    "default_branch": "master"
  },
  "versions": [
    {
      "id": "comfyui-0.27.0-verified",
      "label": "ComfyUI 0.27.0 verified",
      "display_version": "0.27.0",
      "channel": "stable",
      "ref": "8b099de36acd81acd1afa3b5442951dc847e0a52",
      "recommended": true,
      "verified": true,
      "advanced": false,
      "description": "Verified with Python 3.12 and PyTorch 2.6.0+cu124 on NVIDIA A10 / CUDA 12.4."
    }
  ],
  "runtime_profiles": [
    {
      "id": "nvidia-cu124-py312-torch260",
      "label": "NVIDIA CUDA 12.4 / Python 3.12 / PyTorch 2.6.0",
      "python_version": "3.12",
      "torch_profile": "cu124",
      "backend": "cu124",
      "gpu_vendor": "nvidia",
      "recommended": true,
      "verified": true,
      "advanced": false,
      "min_cuda": "12.4",
      "packages": {
        "torch": "torch==2.6.0+cu124",
        "torchvision": "torchvision==0.21.0+cu124",
        "torchaudio": "torchaudio==2.6.0+cu124"
      },
      "description": "Pins CUDA 12.4 wheels before installing the rest of ComfyUI requirements."
    }
  ],
  "recommendation_rules": [
    {
      "id": "nvidia-cuda-124",
      "when": {
        "gpu_vendor": "nvidia",
        "cuda_min": "12.4"
      },
      "version_id": "comfyui-0.27.0-verified",
      "runtime_profile_id": "nvidia-cu124-py312-torch260",
      "gpu": "first",
      "reason": "Detected NVIDIA CUDA 12.4 or newer; use the verified CUDA 12.4 runtime and compatible ComfyUI ref.",
      "warnings": []
    }
  ]
}
```

`POST /v1/hosts/{host_id}/probe` 返回运行时探测结果。调用方可以用
`runtime_recommendation` 预填新实例参数；创建实例时应优先传入 catalog id：
`comfy_version_id`、`runtime_profile_id` 和 `gpu_ids`。

```json
{
  "ok": true,
  "layer": "host",
  "data": {
    "data_root": "/data/wangqiao",
    "installs_dir": "/data/wangqiao/ComfyUI-Installs",
    "default_models_root": "/data/wangqiao/ComfyUI-Shared/models",
    "driver_version": "550.127.08",
    "cuda_version": "12.4",
    "gpus": [
      {
        "index": "0",
        "name": "NVIDIA A10",
        "memory_total_mb": "23028",
        "driver_version": "550.127.08"
      }
    ],
    "runtime_recommendation": {
      "rule_id": "nvidia-cuda-124",
      "version_id": "comfyui-0.27.0-verified",
      "version_label": "ComfyUI 0.27.0 verified",
      "version_channel": "stable",
      "runtime_profile_id": "nvidia-cu124-py312-torch260",
      "runtime_profile_label": "NVIDIA CUDA 12.4 / Python 3.12 / PyTorch 2.6.0",
      "comfy_ref": "8b099de36acd81acd1afa3b5442951dc847e0a52",
      "python_version": "3.12",
      "torch_profile": "cu124",
      "gpu_ids": ["0"],
      "reason": "Detected NVIDIA CUDA 12.4 or newer; use the verified CUDA 12.4 runtime and compatible ComfyUI ref.",
      "warnings": []
    }
  }
}
```

`POST /v1/instances`:

```json
{
  "host_id": "uuid",
  "name": "Comfy Prod",
  "instance_slug": "comfy-prod",
  "comfy_version_id": "comfyui-0.27.0-verified",
  "runtime_profile_id": "nvidia-cu124-py312-torch260",
  "comfy_port": 8188,
  "gpu_ids": ["0"],
  "model_root_ids": ["uuid"],
  "primary_model_root_id": "uuid"
}
```

高级调用方可以直接传 `comfy_ref`、`python_version`、`torch_profile`。`comfy_version_id` 不能和 `comfy_ref`
混用；`runtime_profile_id` 不能和 `python_version` 或 `torch_profile` 混用。服务入库时仍保存解析后的
`comfy_ref`、`python_version`、`torch_profile`。

`torch_profile` 当前支持 `requirements` 和 `cu124`。`requirements` 完全跟随 ComfyUI 的 requirements；`cu124`
会先使用 `uv pip install --torch-backend cu124` 安装已固定的 CUDA 12.4 版本组：
`torch==2.6.0+cu124`、`torchvision==0.21.0+cu124`、`torchaudio==2.6.0+cu124`，再安装过滤掉这三个包的
ComfyUI requirements。这样 torch 生态绑定已验证的 CUDA 12.4 wheel，普通 Python 依赖仍然可以走环境里的默认 PyPI 源或镜像。
对 NVIDIA A10 / Driver 550 / CUDA 12.4 这类主机，probe 当前推荐的兼容 ComfyUI ref 是
`8b099de36acd81acd1afa3b5442951dc847e0a52`；当前 ComfyUI `master` 已知可能要求更新的 torch 生态，不应作为这类主机的默认 happy path。

`POST /v1/instances/{instance_id}/install` and `POST /v1/instances/{instance_id}/reinstall`:

```json
{
  "comfy_ref": "v0.3.50",
  "restart": false
}
```

When `restart=true`, the control plane starts the instance after a successful install/reinstall and records a separate `start` run. The install/reinstall response still returns the install/reinstall run.

`POST /v1/instances/{instance_id}/start` and `POST /v1/instances/{instance_id}/stop`:

```json
{}
```

Query parameters:

| Query | Contract |
|---|---|
| `host_id` | Optional filter for `GET /v1/model-roots` and `GET /v1/instances`. |
| `instance_id` | Optional filter for `GET /v1/runs`. |
| `tail` | Optional integer `1..1000` for `GET /v1/instances/{instance_id}/logs`; default `200`. |

## Comfy Response Shape

Instance response data:

```json
{
  "id": "uuid",
  "host_id": "uuid",
  "name": "Comfy Prod",
  "instance_slug": "comfy-prod",
  "install_root": "/data/wangqiao/comfy-shell-v2/ComfyUI-Installs/comfy-prod",
  "comfy_ref": "v0.3.50",
  "resolved_commit": "abcdef123456",
  "python_version": "3.12",
  "torch_profile": "requirements",
  "comfy_port": 8188,
  "gpu_ids": ["0"],
  "primary_model_root_id": "uuid",
  "model_root_ids": ["uuid"],
  "created_at": "2026-07-22T00:00:00Z",
  "updated_at": "2026-07-22T00:00:00Z",
  "last_launched_at": null
}
```

Run response data:

```json
{
  "id": "uuid",
  "request_id": "req-...",
  "host_id": "uuid",
  "instance_id": "uuid",
  "kind": "install",
  "phase": "completed",
  "started_at": "2026-07-22T00:00:00Z",
  "ended_at": "2026-07-22T00:00:10Z",
  "exit_code": 0,
  "error_code": null,
  "message": null,
  "log_path": "/data/wangqiao/comfy-shell-v2/ComfyUI-Installs/comfy-prod/logs/comfyui.log",
  "stderr_tail": null
}
```

## Error Codes

| Code | HTTP | Retryable |
|---|---:|---|
| `REQUEST_INVALID` | 422 | no |
| `UNAUTHORIZED` | 401 | no |
| `FORBIDDEN` | 403 | no |
| `RESOURCE_NOT_FOUND` | 404 | no |
| `RESOURCE_CONFLICT` | 409 | no |
| `DEPENDENCY_UNAVAILABLE` | 503 | yes |
| `INTERNAL_ERROR` | 500 | yes |
| `HOST_NOT_FOUND` | 404 | no |
| `HOST_NAME_CONFLICT` | 409 | no |
| `MODEL_ROOT_NOT_FOUND` | 404 | no |
| `MODEL_ROOT_CONFLICT` | 409 | no |
| `INSTANCE_NOT_FOUND` | 404 | no |
| `INSTANCE_SLUG_CONFLICT` | 409 | no |
| `RUN_NOT_FOUND` | 404 | no |
| `EXECUTOR_UNSUPPORTED` | 422 | no |
| `COMFYCTL_FAILED` | 500 | no |
| `PORT_IN_USE` | 409 | no |
| `INSTANCE_LOCKED` | 409 | no |
| `DEPENDENCY_MISSING` | 503 | no |
| `GIT_FAILED` | 502 | yes |
| `UV_FAILED` | 502 | yes |
| `PYTHON_DEPENDENCY_FAILED` | 502 | yes |
| `INSTANCE_NOT_INSTALLED` | 409 | no |
| `VENV_MISSING` | 409 | no |
| `PROCESS_START_FAILED` | 502 | yes |
| `PROCESS_STOP_TIMEOUT` | 504 | yes |
| `PID_INVALID` | 500 | no |

## Compatibility

The public API prefix is configured by `SERVICE__API_PREFIX` and defaults to `/v1`. `./scripts/verify.sh check` verifies mounted route method/path/operation id/success status drift, OpenAPI request schema/error response/security metadata, registered error code validity, API contract route table drift, required docs, env config, migrations, scripts, and tests. Envelope fields, route-specific error sets, and schema names are stable contract surfaces maintained by registry metadata, tests, and this document.

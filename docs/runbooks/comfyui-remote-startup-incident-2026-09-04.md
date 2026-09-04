# ComfyUI Remote Startup Incident 2026-09-04

本文记录 2026-09-04 远端 GPU 服务器部署 `comfy-shell-v2` 后，安装和启动 ComfyUI 实例过程中暴露的问题、根因和修复边界。它是运行事故复盘，不是功能计划；当前实现事实见 [`../current/implementation.md`](../current/implementation.md)，HTTP 合同见 [`../contracts/api-contract.md`](../contracts/api-contract.md)。

## 结论

这次事故不是单点失败，而是“默认版本选择不适配目标 GPU 环境”叠加“控制面缺少运行时推荐和诊断信息”。

当前服务器的有效组合是：

```text
GPU: NVIDIA A10 x2
Driver: 550.127.08
CUDA upper bound: 12.4
ComfyUI ref: 8b099de36acd81acd1afa3b5442951dc847e0a52
ComfyUI version: 0.27.0
Python: 3.12
Torch profile: cu124
torch: 2.6.0+cu124
torchvision: 0.21.0+cu124
torchaudio: 2.6.0+cu124
```

当前不应把 `master + cu124` 当成这台机器的默认 happy path。实测 `master` 依赖 `comfy-kitchen==0.2.31`，在 `torch==2.6.0+cu124` 下启动阶段失败；旧工作 commit `8b099de36acd81acd1afa3b5442951dc847e0a52` 依赖 `comfy-kitchen==0.2.18`，可以启动。`ComfyUI version: 0.27.0` 来自启动成功后的 `/system_stats` 观测值。

## 运行模型

本次验证链路是：

```text
macOS Browser / curl
  -> SSH tunnel 127.0.0.1:17800
  -> remote FastAPI 127.0.0.1:7800
  -> remote comfyctl
  -> /data/wangqiao/ComfyUI-Installs/<instance>
  -> ComfyUI 127.0.0.1:8190
  -> SSH tunnel 127.0.0.1:18190
  -> macOS Browser
```

远端 FastAPI 是控制面；ComfyUI 实例是被 `comfyctl` 管理的独立进程。重启 FastAPI 不应影响已经运行的 ComfyUI 实例。

## 时间线

| 阶段 | 现象 | 定位 |
|---|---|---|
| 访问控制面 | 本机访问 `127.0.0.1:7800` 命中本地 API，不是远端 API。 | 本机和远端都使用 `7800`；最终使用本机 `17800 -> remote 7800` 的 SSH tunnel。 |
| 创建实例后直接 start | 返回 `INSTANCE_NOT_INSTALLED`。 | 实例只在数据库落库，必须先 install，再 start。 |
| 首次 install | 报缺少 `.venv/bin/pip`。 | `uv venv` 创建环境后不应依赖 venv 内 pip；改为 `uv pip install --python <venv python>`。 |
| start 失败 | `extra_model_paths.yaml` 中字段是 YAML list，ComfyUI 读取时期望 string。 | 改为 `checkpoints: |` 多行字符串格式。 |
| 使用 8188 端口 | 返回 `PORT_IN_USE`。 | 旧 `comfy-shell` 已在远端 `127.0.0.1:8188` 运行；新验证实例改用 `8190`。 |
| `requirements` 默认安装 | 启动时报 CUDA driver 不匹配。 | 服务器 Driver 550/CUDA 12.4，不适合安装 CUDA 13 wheel；需要 `cu124` profile。 |
| `cu124` 裸安装 | 安装阶段长时间卡在 PyTorch wheel 下载。 | 首次下载 `torch` 大包，网络慢但缓存会生效；后续重装明显变快。 |
| `master + cu124` start | `comfy-kitchen==0.2.31` 在 `torch 2.6.0` 下 schema 推断失败。 | 不是端口/路径问题，是 ComfyUI ref 与 torch 版本组合不兼容。 |
| 旧工作 commit + cu124 | install/start/ready 成功。 | `8b099de...` 与 `torch 2.6.0+cu124` 兼容。 |

## 根因

### 版本选择

目标机器的 NVIDIA Driver 只能稳定支持 CUDA 12.4 级别的 PyTorch wheel。若直接跟随 ComfyUI `master` 的最新依赖，可能要求更新的 torch 生态；若直接跟随 ComfyUI requirements 的裸 `torch`，resolver 可能选到与 Driver 不匹配的 CUDA wheel。

修复后，`cu124` profile 表示一个明确的版本组，而不是“让 resolver 自己猜”：

```text
torch==2.6.0+cu124
torchvision==0.21.0+cu124
torchaudio==2.6.0+cu124
```

### 接口语义

实例创建时会把 `comfy_ref`、`python_version`、`torch_profile`、`gpu_ids` 落库。安装和重装不在 install 阶段重新猜测 GPU 或 Python/Torch 版本；`python_version`、`torch_profile` 和 `gpu_ids` 来自实例记录。当前 HTTP 合同仍允许 install/reinstall 请求体临时传入 `comfy_ref` 覆盖本次安装 ref，并在安装成功后回写实例记录。

这个边界是正确的：如果 install 阶段动态改变 Python/Torch/GPU 参数，会导致数据库展示值和真实安装参数不一致，故障难定位。`comfy_ref` 的覆盖是显式请求行为，不应由服务端隐式猜测。

### 诊断信息

事故前，UI 对 probe 结果消费不完整：

- 只预填 Python/Torch，没有提交推荐的 `gpu_ids`。
- 没有显示 `nvidia_smi_error` 和 recommendation warnings。
- `master + cu124` 已知失败后，UI 仍可能让用户留空 ref 并落到 `master`。

修复后，probe 返回并由 UI 消费：

```text
driver_version
cuda_version
gpus
nvidia_smi_error
runtime_recommendation.comfy_ref
runtime_recommendation.python_version
runtime_recommendation.torch_profile
runtime_recommendation.gpu_ids
runtime_recommendation.warnings
```

## 已修复事项

- `comfyctl host probe` 增加 Driver/CUDA/GPU 探测和运行时推荐。
- A10 / Driver 550 / CUDA 12.4 推荐 `Python 3.12 + cu124 + GPU 0 + 兼容 ComfyUI ref`。
- UI 增加 Runtime 面板，显示 Driver、CUDA、GPU、推荐值、warning 和 `nvidia_smi_error`。
- UI 创建实例时提交 `gpu_ids`。
- `cu124` profile 固定 torch 三件套版本，并使用 `uv pip install --torch-backend cu124`。
- `extra_model_paths.yaml` 改为 ComfyUI 当前可读取的字符串格式。
- 安装依赖统一使用 `uv pip install --python <venv python>`。
- clone 命令增加 `--single-branch --filter=blob:none`，减少 GitHub 拉取数据量。
- 远端 `.env` 当前设置：

```text
COMFY__DATA_ROOT=/data/wangqiao
COMFY__DEFAULT_REF=8b099de36acd81acd1afa3b5442951dc847e0a52
COMFY__PYTHON_VERSION=3.12
COMFY__TORCH_PROFILE=cu124
```

## 验证结果

远端验证实例：

```text
instance_slug: comfy-a10-cu124
install_root: /data/wangqiao/ComfyUI-Installs/comfy-a10-cu124
port: 8190
local tunnel: 18190 -> remote 8190
```

安装 manifest：

```json
{
  "comfy_ref": "8b099de36acd81acd1afa3b5442951dc847e0a52",
  "python_version": "3.12",
  "resolved_commit": "8b099de36acd81acd1afa3b5442951dc847e0a52",
  "torch_profile": "cu124",
  "torch_versions": {
    "torch": "2.6.0+cu124",
    "torch_cuda": "12.4",
    "torchaudio": "2.6.0+cu124",
    "torchvision": "0.21.0+cu124"
  }
}
```

运行时验证：

```text
ready=true
ComfyUI version: 0.27.0
Python: 3.12.13
PyTorch: 2.6.0+cu124
Device: cuda:0 NVIDIA A10
```

本地验证：

```bash
./scripts/verify.sh check
```

结果：

```text
164 passed, 2 skipped, 1 warning
```

远端聚焦验证：

```bash
uv run pytest tests/test_comfyctl.py tests/test_config.py tests/test_comfy_api.py tests/test_http_contract.py -q
```

结果：

```text
53 passed, 1 warning
```

## 排查命令

查看远端控制面状态：

```bash
ssh <user@gpu-host> 'cd <remote_comfy_shell_v2_dir> && PATH=$HOME/.local/bin:$PATH ./scripts/dev.sh status'
```

查看 host probe：

```bash
curl -sS -H 'Authorization: Bearer <service_api_key>' \
  -H 'Content-Type: application/json' \
  -X POST -d '{}' \
  http://127.0.0.1:<local_control_port>/v1/hosts/<host_id>/probe
```

查看实例 ready：

```bash
curl -sS -H 'Authorization: Bearer <service_api_key>' \
  http://127.0.0.1:<local_control_port>/v1/instances/<instance_id>/ready
```

查看 ComfyUI 运行时：

```bash
curl -sS http://127.0.0.1:<local_comfyui_port>/system_stats
```

查看实例日志：

```bash
curl -sS -H 'Authorization: Bearer <service_api_key>' \
  'http://127.0.0.1:<local_control_port>/v1/instances/<instance_id>/logs?tail=200'
```

本次事故现场使用过的端口映射是 `17800 -> remote 7800` 和 `18190 -> remote 8190`。runbook 中的命令使用占位符，避免把一次现场的 token、host id、instance id 或公网地址误当成默认配置。

## 再发生时的判断顺序

1. 先看 `probe_host`：确认 Driver、CUDA、GPU、`runtime_recommendation`。
2. 再看实例记录：确认 `comfy_ref`、`python_version`、`torch_profile`、`gpu_ids` 是否符合推荐。
3. 再看 install manifest：确认实际安装出的 torch 三件套和 `torch_cuda`。
4. 再看 start/status：确认端口未占用、pid 归属有效、日志路径正确。
5. 最后看 ComfyUI 日志：区分 Python 依赖错误、ComfyUI ref 兼容错误、CUDA runtime 错误和端口/进程错误。

不要先改模型目录，也不要先清空实例目录。模型目录是共享目录，重装实例不应影响模型资产。

## 后续维护规则

- 新增 CUDA profile 时，必须同时更新 `comfyctl` profile、配置校验、API 文档、当前实现文档和测试。
- 不要把 `master` 作为所有 GPU 环境的隐式默认。默认 ref 必须能和推荐 torch profile 一起启动。
- `runtime_recommendation` 只能作为创建实例的输入建议，不应在 install 阶段隐式覆盖已落库实例参数。
- 对于远端 GitHub 网络慢的问题，优先通过 `.env` 的 `COMFY__REPO_URL` 选择可达仓库或本地 mirror，不在代码里硬编码第三方代理。
- 对于远端 PyPI 或 PyTorch wheel 下载慢的问题，优先通过 `.env` 的 `COMFY__PYTHON_INDEX_URL`、`COMFY__TORCH_INDEX_URL` 或 `COMFY__TORCH_FIND_LINKS_URL` 选择远端可达镜像源；不要把地区性镜像硬编码为全局默认。镜像是 wheel 目录时使用 `COMFY__TORCH_FIND_LINKS_URL`，不要误填进 `COMFY__TORCH_INDEX_URL`。
- 任何启动失败都要保留 `log_path`、`stderr_tail`、`request_id` 和 `trace_id`，不要吞错或降级成“启动中”。

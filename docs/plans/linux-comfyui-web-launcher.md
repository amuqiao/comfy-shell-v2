# Linux ComfyUI Web Launcher

## Current Baseline

- `comfy-shell-v2` 目前没有实现代码。当前事实见 [Project Baseline](../current/project-baseline.md)。
- 参考项目 `/Users/admin/Code/cms/embedding-service` 的可借鉴点是：`.env.example` 只暴露运维需要理解的配置意图，`.env` 不提交，入口脚本负责启动期校验，服务启停用少量脚本和 `.run/*.pid`、`logs/*.log` 记录状态。
- 参考项目 `/Users/admin/Code/Comfy-Desktop-1.0.46` 的可借鉴点是：`InstallationRecord`、最近启动时间、安装源信息、共享模型目录、独立安装路径、安装详情页和启动动作。它的 Electron、多 source plugin、cloud、OAuth、telemetry 和 updater 机制不进入本项目首版。
- 旧项目 `/Users/admin/Downloads/Code/comfy-shell` 的可借鉴点是：SSH/tunnel 操作显式化，远端写操作要求确认，参数先校验再执行，status/ready/logs/gpu 拆成可诊断命令。

## Remaining Gaps

- 需要确定并实现一个轻量 Web 控制面，让 macOS 浏览器能管理远端 Linux GPU 机器上的 ComfyUI 实例。
- 需要支持多实例：每个实例有独立 ComfyUI checkout、`.venv`、端口、pid、日志、manifest 和启动参数。
- 需要支持 ComfyUI 版本选择与重装：用户可以选择 tag 或 commit 重装某个实例，重装不影响模型目录。
- 需要支持独立模型目录管理：模型根目录是实例外部资源，可被多个实例引用，安装和重装流程不得删除、移动或重建模型目录。
- 需要把 `.env` 配置、SQLite 元数据、运行时状态、日志来源分清楚，避免排障时不知道哪一层是事实来源。
- 需要保留两种运行形态：远端部署优先，本机 macOS 控制远端作为开发/多主机场景。

## Planned Work

### 1. Product Scope

首版目标是一款轻量 Linux ComfyUI Web 启动器，接近 ComfyUI Desktop 的核心管理体验，但不做桌面壳：

- 在远端 Linux GPU 机器安装和运行 ComfyUI。
- 在 macOS 本机通过 SSH tunnel 访问远端 Web 控制面和 ComfyUI Web 端口。
- 创建、查看、启动、停止、重装多个 ComfyUI instance。
- 为每个 instance 记录 ComfyUI 版本、Python 版本、Torch/CUDA profile、端口、GPU、模型目录、日志路径和最近启动时间。
- 配置共享或独立模型目录，模型目录独立于 instance 安装目录。
- 查看安装/重装/启动命令的进度、日志、退出码和错误码。
- 用 `.env` 管理部署级配置，用 SQLite 管理 host、instance、model root 和 command run 元数据。

首版明确不做：

- 不做自动配置同步。
- 不做自动 profile 分发，不自动把 macOS `.env` 推到远端。
- 不做 Redis、Celery、Taskiq、队列系统。
- 不做额外远端 daemon。远端部署模式下 Web 服务本身可以在远端运行，但不再引入第二个常驻 agent daemon。
- 不做 Comfy Desktop 的 source plugin 系统。
- 不做 cloud、OAuth、telemetry、自动更新器。
- 不做 Docker/Kubernetes 首版部署。
- 不做复杂模型目录扫描、模型市场或模型库存数据库。
- 不做共享可变 ComfyUI 版本池；每个实例拥有自己的 checkout 和 `.venv`。
- 不做 Web terminal。需要排障时用日志、状态和命令输出定位，复杂交互回到 SSH shell。

### 2. Deployment Modes

只有一个主机制：Web 控制面调用 executor，executor 调用 `comfyctl`，`comfyctl` 管理文件、环境、进程和日志。

推荐默认形态是远端部署：

```text
macOS Browser
  -> ssh -L 7800:127.0.0.1:7800 user@gpu-host
  -> remote 127.0.0.1:7800 FastAPI Web control plane
  -> remote SQLite
  -> local executor
  -> remote comfyctl
  -> instances/<instance_id>/{ComfyUI,.venv,.run,logs,manifest.json}
```

这个形态最贴合目标：ComfyUI、模型、Python 环境、SQLite、日志都在 GPU 机器上，macOS 只负责浏览器访问和 SSH tunnel。

第二形态是本机控制远端：

```text
macOS Browser
  -> macOS 127.0.0.1:7800 FastAPI Web control plane
  -> macOS SQLite
  -> ssh executor
  -> remote comfyctl
  -> remote instances/<instance_id>/{ComfyUI,.venv,.run,logs,manifest.json}
```

这个形态用于本地开发、管理多台 GPU host、或临时不想在远端跑 Web 服务的场景。它不是默认推荐路径。

两种形态不能引入两套产品模型。区别只在 executor：

- `local`: Web 服务与 `comfyctl` 在同一台机器上。
- `ssh`: Web 服务通过 SSH 在远端执行 `comfyctl`。

### 3. Configuration Rule

`.env` 是部署级配置来源，每个部署独立维护：

- 远端部署时，远端 `.env` 是事实来源。
- macOS 本机部署时，本机 `.env` 是事实来源。
- `.env` 不提交 git。
- `.env.example` 提交 git，只作为模板，不作为运行配置。
- 不做自动双向同步，不在 UI 中承诺配置同步。
- 可以规划显式 `export-config` / `import-config`，但它不是首版必需能力，且必须由用户主动执行。

`.env.example` 应借鉴 `embedding-service` 的模板风格：只暴露用户能理解且必须配置的意图变量，内部派生值由代码计算，启动时强制校验。

配置权威边界：

```text
.env
  部署级控制意图：API 监听、数据库路径、默认 base dir、默认模型根、默认安装参数、ssh executor 默认值
  不保存 instance 状态，不保存运行中 pid，不保存安装结果

SQLite
  控制面元数据：host、model root、instance、command run
  不保存运行时权威状态

manifest.json
  单个 instance 的安装事实：requested ref、resolved commit、python、torch profile、创建时间
  不保存用户 secret，不覆盖 .env

pid/log/ready/status
  运行时证据：进程、端口、ComfyUI 健康、日志
  不回写成配置事实
```

计划中的 `.env.example` 分类：

```dotenv
# service identity
APP_ENV=local
SERVICE_NAME=comfy-shell-v2
SERVICE_TITLE=Comfy Shell

# control plane
API_HOST=127.0.0.1
API_PORT=7800
DATABASE_PATH=data/app.db
SESSION_KEY=<replace-with-random-token>
ALLOWED_ORIGINS=http://127.0.0.1:7800,http://localhost:7800

# host defaults
COMFY_BASE_DIR=/data/comfy-shell-v2
DEFAULT_MODELS_ROOT=/data/models/comfy
DEFAULT_INSTANCE_PORT_START=8188

# install defaults
COMFY_REPO_URL=https://github.com/comfyanonymous/ComfyUI.git
DEFAULT_COMFY_REF=
PYTHON_VERSION=3.12
UV_INDEX_URL=
PYPI_INDEX_URL=
TORCH_PROFILE=cu124

# runtime defaults
COMFY_BIND_HOST=127.0.0.1
CUDA_VISIBLE_DEVICES=
LOG_LEVEL=INFO

# ssh executor, only used by macOS control-plane mode
SSH_TARGET=
SSH_CONNECT_TIMEOUT_SECONDS=10
SSH_REMOTE_COMFYCTL=
```

启动期必须校验：

- `API_HOST` 绑定公网地址时必须显式开启访问控制；默认只允许 `127.0.0.1`。
- `SESSION_KEY` 不能是模板值。
- `DATABASE_PATH` 的父目录必须可写。
- `COMFY_BASE_DIR` 和 model root 必须是绝对路径。
- `ssh` 模式必须有 `SSH_TARGET`，且不能禁用 host key 检查。

### 4. Repository Structure

计划中的源码目录：

```text
comfy-shell-v2/
  .env.example
  .gitignore
  pyproject.toml
  uv.lock
  start-api.sh
  app/
    main.py
    config.py
    db.py
    schemas.py
    api/
      hosts.py
      instances.py
      model_roots.py
      runs.py
    services/
      hosts.py
      instances.py
      installer.py
      process_status.py
      model_roots.py
    executors/
      base.py
      local.py
      ssh.py
    web/
      static/
      templates/
  bin/
    comfyctl
  comfyctl/
    cli.py
    host.py
    instance.py
    install.py
    process.py
    paths.py
  scripts/
    dev.sh
    remote.sh
    verify.sh
    lib/
      common.sh
    dev/
      launch_service.py
      check_ports.py
  docs/
    README.md
    current/
    contract/
    plans/
```

计划中的运行时目录，通常在远端 GPU host 上：

```text
/data/comfy-shell-v2/
  .env
  .venv/
  data/
    app.db
  .run/
    api.pid
  logs/
    api.log
  instances/
    inst_01/
      ComfyUI/
      .venv/
      manifest.json
      extra_model_paths.yaml
      instance.lock
      .run/
        comfyui.pid
      logs/
        comfyui.log
      .staging/
      .previous/
    inst_02/
      ComfyUI/
      .venv/
      manifest.json
      extra_model_paths.yaml
      instance.lock
      .run/
        comfyui.pid
      logs/
        comfyui.log
```

模型目录不放进 instance：

```text
/data/models/comfy/
/mnt/models/shared/
```

同步或部署脚本必须排除：

```text
.env
.venv/
data/app.db
.run/
logs/
instances/
models/
ComfyUI/models/
ComfyUI/input/
ComfyUI/output/
ComfyUI/temp/
```

### 5. Data Model

SQLite 只保存控制面元数据，不保存运行时真相。

```text
Host
  id
  name
  connection            # local | ssh
  ssh_target            # ssh mode only
  base_dir
  host_key_fingerprint  # ssh mode only
  created_at
  updated_at

ModelRoot
  id
  host_id
  label
  path
  created_at
  updated_at

Instance
  id
  host_id
  name
  install_root
  comfy_ref             # user requested tag or commit
  resolved_commit       # immutable commit after install
  python_version
  torch_profile
  comfy_port
  gpu_ids
  primary_model_root_id
  created_at
  updated_at
  last_launched_at

InstanceModelRoot
  instance_id
  model_root_id

CommandRun
  id
  request_id
  host_id
  instance_id
  kind                  # install | start | stop | status | ready | logs | check_model_root
  phase
  started_at
  ended_at
  exit_code
  error_code
  message
  log_path
  stderr_tail
```

不保存权威 `Instance.status`。实例状态来自实时探测：

```text
pid file -> process alive -> port open -> ComfyUI /system_stats
```

### 6. Instance Version And Reinstall

版本属于 instance，不属于全局共享池。首版只支持 tag 或 commit 作为稳定安装输入；branch 只能作为开发模式选项，并且 UI 必须提示不可复现。

安装流程：

```text
acquire instance.lock
resolve comfy_ref -> resolved_commit
prepare .staging/<run_id>/ComfyUI
prepare .staging/<run_id>/.venv with uv
install dependencies for selected torch_profile
write staged manifest.json
run minimum verification
move active ComfyUI/.venv to .previous/<run_id>
promote .staging/<run_id> to active
write active manifest.json
release instance.lock
```

重装流程不需要一个独立复杂机制。控制面按顺序执行：

```text
stop instance
install instance with requested comfy_ref
start instance, if user selected restart after reinstall
```

重装规则：

- 永远不删除 model root。
- 永远不把模型放到 instance 的 `ComfyUI/models` 作为默认长期目录。
- `extra_model_paths.yaml` 每次启动前根据 Instance 与 ModelRoot 生成。
- 安装失败时保留当前 active 版本，不自动切到 latest，不静默回滚。
- 如果 promotion 已发生但启动失败，错误必须指向启动层，不伪装成安装失败。

重装影响范围必须固定：

```text
保留:
  instance id
  instance name
  configured model roots
  primary model root
  configured port
  configured gpu ids
  command history
  existing model files
  deployment .env

替换:
  active ComfyUI checkout
  active instance .venv
  active manifest.json
  generated extra_model_paths.yaml

追加:
  new CommandRun
  install/reinstall logs
  .previous/<run_id> backup when promotion happens
```

`manifest.json` 是 instance 目录内的本地事实记录：

```json
{
  "instance_id": "inst_01",
  "comfy_ref": "v0.3.50",
  "resolved_commit": "abcdef123456",
  "python_version": "3.12",
  "torch_profile": "cu124",
  "created_at": "2026-09-03T00:00:00Z"
}
```

### 7. Command Boundary

`comfyctl` 是唯一管理 host 文件、环境、进程和日志的命令入口。Web 控制面不拼任意 shell 字符串，只传结构化参数。

计划中的 `comfyctl` 命令：

```text
comfyctl host probe --json
comfyctl instance install --id <id> --root <path> --repo <url> --ref <tag-or-commit> --python <version> --torch-profile <profile> --json
comfyctl instance start --id <id> --root <path> --host 127.0.0.1 --port <port> --extra-model-paths <yaml> --json
comfyctl instance stop --id <id> --root <path> --json
comfyctl instance status --id <id> --root <path> --json
comfyctl instance ready --id <id> --root <path> --json
comfyctl instance logs --id <id> --root <path> --tail 200
comfyctl model-root check --path <path> --json
```

`status` 和 `ready` 必须分开：

- `status`: 检查 pid file、进程是否存活、端口是否监听、manifest 是否存在，返回诊断快照。
- `ready`: 只回答 ComfyUI 是否已经可用，核心检查是实例端口上的 `/system_stats` 是否返回成功。
- `logs`: 只读日志，不顺带改变进程状态。
- `tunnel`: 由 `scripts/remote.sh tunnel` 管理 SSH 端口映射，不放进 `comfyctl`，因为它发生在访问端而不是 instance host 内部。

返回值必须稳定：

- exit code `0`: 命令成功。
- exit code `2`: 参数或配置错误。
- exit code `3`: 前置条件不满足，例如目录不存在、端口被占用、实例锁已存在。
- exit code `4`: 外部依赖失败，例如 git、uv、pip、nvidia-smi、curl。
- exit code `5`: 运行时失败，例如进程启动后退出、健康检查失败。

JSON 输出必须包含：

```json
{
  "ok": false,
  "request_id": "req_xxx",
  "error_code": "PORT_IN_USE",
  "message": "port 8188 is already in use",
  "layer": "process",
  "log_path": "/data/comfy-shell-v2/instances/inst_01/logs/comfyui.log"
}
```

### 8. HTTP Control Plane Boundary

HTTP API 是 UI 的稳定外部接口。具体内部使用 local executor 还是 ssh executor，不应泄漏给 UI。

本节是计划阶段草案，不是当前稳定合同。实现完成后，稳定 HTTP API、`comfyctl` JSON、错误码和事件流必须迁移到 `docs/contract/`。

计划中的首版 API：

```text
GET  /api/hosts
POST /api/hosts
POST /api/hosts/{host_id}/probe

GET  /api/model-roots
POST /api/model-roots
POST /api/model-roots/{model_root_id}/check

GET  /api/instances
POST /api/instances
GET  /api/instances/{instance_id}
POST /api/instances/{instance_id}/install
POST /api/instances/{instance_id}/start
POST /api/instances/{instance_id}/stop
POST /api/instances/{instance_id}/status
POST /api/instances/{instance_id}/ready

GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/logs
```

普通响应 envelope：

```json
{
  "request_id": "req_xxx",
  "code": "OK",
  "message": "ok",
  "data": {}
}
```

异步命令应先创建 `CommandRun`，再通过事件流返回进度：

```json
{
  "request_id": "req_xxx",
  "run_id": "run_xxx",
  "seq": 12,
  "phase": "install_dependencies",
  "level": "info",
  "message": "uv sync completed",
  "ts": "2026-09-03T00:00:00Z",
  "data": {}
}
```

### 9. UI Feature Set

首版 UI 是管理工具，不是营销页。

页面：

- Hosts: 查看当前 host、连接方式、base dir、GPU 探测结果。
- Instances: 列表显示名称、版本、端口、GPU、模型目录、最近启动时间、实时状态。
- Instance Detail: 启动/停止/重装、版本信息、日志、模型目录、启动参数。
- Model Roots: 添加、检查、设置默认模型根目录。
- Runs: 查看安装/重装/启动/停止历史、退出码、错误码、日志尾部。
- Settings: 显示部署级配置状态，只显示可安全公开的 `.env` 摘要，不显示 secret。

关键交互：

- 新建 instance 时必须选择 host、install root、ComfyUI ref、Python version、Torch profile、port、model roots。
- 重装前显示将要替换的 instance、目标 ref、当前 resolved commit、模型目录“不受影响”。
- 启动前检查端口、pid、model root 可读性和 `extra_model_paths.yaml`。
- 所有长命令显示 run id、phase、日志路径和可复制的诊断摘要。

### 10. Service Management

借鉴 `embedding-service` 的服务管理模式，但保留本项目轻量边界：

```text
start-api.sh
  -> load .env by process environment or script helper
  -> validate API_HOST/API_PORT/SESSION_KEY/DATABASE_PATH
  -> exec .venv/bin/python -m uvicorn app.main:app

scripts/dev.sh
  -> uv sync
  -> create .run/
  -> start/stop/status/restart API
  -> write .run/api.pid and logs/api.log

scripts/remote.sh
  -> explicit sync/bootstrap/start/stop/status/logs/tunnel
  -> require --yes for remote write/lifecycle commands
  -> exclude .env, .venv, data/app.db, instances, models, logs

scripts/verify.sh
  -> bash -n scripts/*.sh
  -> uv run tests
  -> comfyctl command contract smoke
```

服务管理不负责 ComfyUI 实例内部生命周期；它只管理控制面服务。ComfyUI instance 生命周期由 `comfyctl instance *` 管理。

### 11. Security And Failure Diagnostics

默认安全边界：

- FastAPI 默认绑定 `127.0.0.1`。
- ComfyUI 默认绑定 `127.0.0.1`。
- 远端访问默认通过 SSH tunnel。
- 写 API 需要 `SESSION_KEY`。
- 校验 `Origin` 和 `Host`，不允许默认 `CORS *`。
- 不存 SSH 密码或私钥内容。需要 SSH 时只记录 target、key path 和 host key fingerprint。
- 不使用 `StrictHostKeyChecking=no`。
- 不接受任意 shell command 输入。
- 所有路径先做 canonical `realpath` 校验，拒绝逃逸 base dir 的 instance 路径。

失败分层：

```text
config      .env missing/invalid, database path invalid
ssh         auth failed, host key mismatch, connect timeout
filesystem  path invalid, permission denied, disk full
git         clone/fetch/checkout failed
python      uv/python/venv/dependency failed
process     pid stale, port in use, process exited
comfy       /system_stats failed, ComfyUI import/runtime failed
model       model root missing, unreadable, wrong path type
```

每个失败必须能看到：

- `request_id`
- `run_id`
- `instance_id` 或 `host_id`
- `layer`
- `error_code`
- `exit_code`
- `message`
- `log_path`
- `stderr_tail`
- 建议用户下一步检查的单一命令

### 12. Architecture Review Checklist

机制够简单吗：

- 保留一个主机制：控制面 -> executor -> `comfyctl`。
- 删除首版 plugin/source 框架；只建 `local` 和 `ssh` executor。
- 删除自动同步、队列和远端 agent daemon。

外部接口稳定吗：

- UI 只依赖 HTTP API，不依赖 `comfyctl` 内部输出。
- Web 控制面只依赖 `comfyctl` 的稳定 JSON 合同。
- `.env.example` 只暴露稳定配置意图，内部派生值不作为外部合同。

失败能定位吗：

- 每个命令有 `request_id`、`run_id`、`layer`、`error_code` 和日志路径。
- 安装、启动、健康检查、SSH、模型目录检查分层记录，不合并成一个泛化错误。
- 运行时状态实时探测，不把 SQLite 里的旧状态当事实。

半年后还能改吗：

- SQLite schema 明确 host、instance、model root、run 的边界。
- instance 自带 checkout 和 `.venv`，版本切换不会影响其他实例。
- 模型目录独立于 instance，重装不会触碰已下载模型。
- `comfyctl` 合同小，后续可以替换内部实现而不破坏 UI。

## Acceptance

计划阶段完成标准：

- 文档明确区分当前事实和未来计划。
- 文档写清默认远端部署形态、本机 SSH 控制形态，以及二者只通过 executor 区分。
- 文档明确 `.env` 不提交、不自动同步，`.env.example` 只作为模板。
- 文档写清 instance、version、reinstall、model root 的所有权边界。
- 文档写清首版删除/推迟的复杂机制。
- 文档写清目录结构、数据模型、`comfyctl` 边界、HTTP API 草案、服务管理脚本和失败诊断规则。

实现阶段完成标准：

- 提交 `.env.example`、`.gitignore`、`pyproject.toml`、`uv.lock`、`start-api.sh` 和最小 FastAPI 服务。
- `scripts/dev.sh start|stop|status|restart` 能管理控制面 pid/log。
- `comfyctl host probe --json` 和 `comfyctl instance status --json` 可在 Linux host 上运行。
- 可以创建一个 instance，安装指定 ComfyUI tag/commit，启动后通过 SSH tunnel 打开 ComfyUI Web。
- 重装同一 instance 后，原模型目录仍存在且未被修改。
- 端口冲突、SSH 失败、git 失败、uv 失败、ComfyUI 启动失败都返回稳定错误码和日志路径。

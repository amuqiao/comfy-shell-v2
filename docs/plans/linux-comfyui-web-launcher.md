# Linux ComfyUI Web Launcher

## Current Baseline

- `comfy-shell-v2` 已经落地 FastAPI 基础骨架。当前事实见 [Current Implementation](../current/implementation.md)。
- 当前骨架已经包含：FastAPI app factory、lifespan、section 化 `.env` 配置、`.env.example` manifest 校验、request/trace id、success/error envelope、error registry、operation registry、health/ready、SQLAlchemy async、Alembic、UnitOfWork、repository、示例 `items` 业务、`start-api.sh`、`scripts/dev.sh`、`scripts/run.sh`、`scripts/deploy.sh`、`scripts/verify.sh` 和 Docker Compose 辅助入口。
- 现有 HTTP 合同文档在 [API Contract](../contracts/api-contract.md)，扩展规则在 [Extension Contract](../contracts/extension-contract.md)。后续 Comfy Shell API 必须沿用现有 envelope、operation registry、错误码登记和 docs drift 检查。
- 当前骨架仍是 `fastapi-lite` 模板语义，`SERVICE__NAME`、`SERVICE__TITLE`、示例 `items` 业务、Redis fake boundary、对象存储边界和 Compose 入口尚未收敛为 Comfy Shell 业务。PostgreSQL 机制已经存在，Comfy Shell 首版直接复用它。
- 参考项目 `/Users/admin/Code/cms/embedding-service` 的可借鉴点已经部分体现在当前骨架里：`.env.example` 只暴露运维需要理解的配置意图，`.env` 不提交，入口脚本负责启动期校验，服务启停用少量脚本和 `.run/*.pid`、`logs/*.log` 记录状态。
- 参考项目 `/Users/admin/Code/Comfy-Desktop-1.0.46` 的可借鉴点是：`InstallationRecord`、最近启动时间、安装源信息、共享模型目录、独立安装路径、安装详情页和启动动作。它的 Electron、多 source plugin、cloud、OAuth、telemetry 和 updater 机制不进入本项目首版。
- 旧项目 `/Users/admin/Downloads/Code/comfy-shell` 的可借鉴点是：SSH/tunnel 操作显式化，远端写操作要求确认，参数先校验再执行，status/ready/logs/gpu 拆成可诊断命令。

## Remaining Gaps

- 需要把现有 FastAPI 模板收敛为 Comfy Shell 控制面：重命名服务身份、删除或隔离 `items` 示例业务、加入 ComfyUI domain API、schema、service、repository、model、migration 和测试。
- 需要把现有 PostgreSQL 数据层收敛为 Comfy Shell 控制面数据库：保留 SQLAlchemy async、Alembic、UnitOfWork、repository、Postgres provider、Compose 依赖管理和 migration roundtrip 验证。
- 需要支持多实例：每个实例有独立 ComfyUI checkout、`.venv`、端口、pid、日志、manifest 和启动参数。
- 需要支持 ComfyUI 版本选择与重装：用户可以选择 tag 或 commit 重装某个实例，重装不影响模型目录。
- 需要支持独立模型目录管理：模型根目录是实例外部资源，可被多个实例引用，安装和重装流程不得删除、移动或重建模型目录。
- 需要实现默认目录自动派生：不配置 `COMFY__DATA_ROOT` 时，默认从服务安装目录生成 `ComfyUI-Installs`、`ComfyUI-Shared` 和 `ComfyUI-Cache`。
- 需要把 `.env` 配置、PostgreSQL 元数据、运行时状态、日志来源分清楚，避免排障时不知道哪一层是事实来源。
- 需要保留两种运行形态：远端部署优先，本机 macOS 控制远端作为开发/多主机场景。

## Planned Work

### 1. Product Scope

首版目标是在现有 FastAPI 骨架上收敛出一款轻量 Linux ComfyUI Web 启动器，接近 ComfyUI Desktop 的核心管理体验，但不做桌面壳：

- 在远端 Linux GPU 机器安装和运行 ComfyUI。
- 在 macOS 本机通过 SSH tunnel 访问远端 Web 控制面和 ComfyUI Web 端口。
- 创建、查看、启动、停止、重装多个 ComfyUI instance。
- 为每个 instance 记录 ComfyUI 版本、Python 版本、Torch/CUDA profile、端口、GPU、模型目录、日志路径和最近启动时间。
- 配置共享或独立模型目录，模型目录独立于 instance 安装目录。
- 查看安装/重装/启动命令的进度、日志、退出码和错误码。
- 沿用现有 `.env` section 化配置、HTTP envelope、operation registry、error registry、脚本管理和 drift check。
- 用 `.env` 管理部署级配置，用 PostgreSQL 管理 host、instance、model root 和 command run 元数据。

首版明确不做：

- 不做自动配置同步。
- 不做自动 profile 分发，不自动把 macOS `.env` 推到远端。
- 不做 Redis queue/cache 作为首版必需业务能力，不做 Celery、Taskiq 或队列系统。当前骨架里的 Redis fake boundary 和 Compose helper 可以保留，但不能进入 Comfy Shell 首版关键路径。
- 不做额外远端 daemon。远端部署模式下 Web 服务本身可以在远端运行，但不再引入第二个常驻 agent daemon。
- 不做 Comfy Desktop 的 source plugin 系统。
- 不做 cloud、OAuth、telemetry、自动更新器。
- 不做 Kubernetes 首版部署。
- 不把 ComfyUI instance 容器化；Docker Compose 只作为 PostgreSQL/Redis 等控制面依赖的可用启动方式。
- 不做复杂模型目录扫描、模型市场或模型库存数据库。
- 不做共享可变 ComfyUI 版本池；每个实例拥有自己的 checkout 和 `.venv`。
- 不做 Web terminal。需要排障时用日志、状态和命令输出定位，复杂交互回到 SSH shell。

### 2. Delivery Phases

阶段划分只改变交付顺序，不改变系统边界。P1/P2 必须使用同一套数据模型、HTTP 路径、错误码、`comfyctl` JSON 合同和目录派生规则；P1 可以暂时只启用 `local` executor，但不能为了图快做一套将来要推倒的 instance 或 model root 语义。

P1 是远端单机闭环：

```text
macOS Browser
  -> ssh tunnel
  -> remote FastAPI control plane
  -> remote PostgreSQL
  -> local executor
  -> remote comfyctl
  -> remote ComfyUI instances and shared model roots
```

P1 必须交付从安装服务到管理单台 GPU host 的完整生命周期：`.env` 校验、PostgreSQL migration、默认目录派生、model root 登记、instance 创建、指定 tag/commit 安装、启动、停止、重装、状态探测、ready 检查、日志查看、run 记录、错误分层、最小 Web UI、服务脚本和验证脚本。P1 不交付多 host 控制，但 Host 表、Instance 表、API 命名和 UI 心智模型必须按多 host 设计，默认创建并管理一个 `local` Host。

P2 是 macOS 本机控制远端和多 host 管理：

```text
macOS Browser
  -> macOS FastAPI control plane
  -> configured PostgreSQL
  -> ssh executor
  -> remote comfyctl
  -> remote ComfyUI instances and shared model roots
```

P2 不重新设计产品，只把 executor 从 `local` 扩展到 `ssh`。P2 必须让同一套 Host、ModelRoot、Instance、Run、HTTP API 和 UI 可以管理远端 GPU host：SSH host key 校验、远端 `comfyctl` 探测、显式 bootstrap/sync、远端 status/ready/logs、远端 install/reinstall/start/stop、端口 tunnel 辅助和跨主机失败定位。P2 仍然不做自动配置同步；本机 `.env` 和远端 `.env` 各自是部署事实来源，脚本只做用户显式要求的代码/脚本同步，并继续排除 `.env`、运行时目录和大数据目录。

分阶段覆盖矩阵：

| Area | P1 | P2 |
| --- | --- | --- |
| Deployment | 远端 FastAPI + 远端 Postgres + SSH tunnel 访问 | macOS FastAPI + ssh executor 管理一台或多台远端 host |
| Config | 远端 `.env` 是事实来源，`COMFY__DATA_ROOT` 可空并自动派生 | 本机 `.env` 只管理本机控制面和 SSH 默认值，不自动推送到远端 |
| Database | 建立 Host、ModelRoot、Instance、InstanceModelRoot、CommandRun | 复用同一 schema，新增/启用 `connection=ssh` 的 Host 行为 |
| Directories | 创建 `ComfyUI-Installs`、`ComfyUI-Shared`、`ComfyUI-Cache` | 远端路径仍由远端 `service_root/data_root` 派生，本机不猜远端目录 |
| Instance Lifecycle | local executor 完整支持 create/install/start/stop/reinstall/status/ready/logs | ssh executor 完整支持同一生命周期，不新增第二套 API |
| Version/Reinstall | tag/commit 安装，staging + promotion，模型目录不受影响 | 同一 reinstall 语义通过 SSH 执行，失败 layer 区分 ssh/git/python/process/comfy |
| Model Roots | 默认共享模型目录 + 用户登记外部模型目录 | model root 归属 host，路径按远端文件系统校验 |
| UI | Hosts/Instances/Instance Detail/Model Roots/Runs/Settings 最小可用 | Hosts 页面启用 SSH host 新增、探测、tunnel 辅助和远端诊断 |
| Scripts | `dev.sh`、`deploy.sh`、`run.sh`、`verify.sh`、`remote.sh tunnel/status/logs` | `remote.sh sync/bootstrap/start/stop/status/logs/tunnel` 完整远端入口 |
| Security | 默认 bind `127.0.0.1`，写 API 要 token，路径限制在 data root | SSH host key 固定，不存私钥内容，不允许 `StrictHostKeyChecking=no` |
| Diagnostics | `request_id/run_id/layer/error_code/log_path/stderr_tail` | 所有 SSH 失败单独标记 `ssh` layer，不吞成普通 process 失败 |
| Verification | 本机/远端单机 check、postgres、migration、comfyctl contract smoke | fake ssh executor 测试 + 有远端环境时执行 real remote smoke |

### 3. Deployment Modes

只有一个主机制：Web 控制面调用 executor，executor 调用 `comfyctl`，`comfyctl` 管理文件、环境、进程和日志。

推荐默认形态是远端部署：

```text
macOS Browser
  -> ssh -L 7800:127.0.0.1:7800 user@gpu-host
  -> remote 127.0.0.1:7800 FastAPI Web control plane
  -> remote PostgreSQL
  -> executor(local mode, running on the remote host)
  -> comfyctl on the same remote host
  -> ComfyUI-Installs/<instance_slug>/{ComfyUI,.venv,.run,logs,manifest.json}
```

这个形态最贴合目标：ComfyUI、模型、Python 环境、PostgreSQL、日志都在 GPU 机器上，macOS 只负责浏览器访问和 SSH tunnel。

第二形态是本机控制远端：

```text
macOS Browser
  -> macOS 127.0.0.1:7800 FastAPI Web control plane
  -> configured PostgreSQL
  -> ssh executor
  -> remote comfyctl
  -> remote ComfyUI-Installs/<instance_slug>/{ComfyUI,.venv,.run,logs,manifest.json}
```

这个形态用于本地开发、管理多台 GPU host、或临时不想在远端跑 Web 服务的场景。它不是默认推荐路径。

两种形态不能引入两套产品模型。区别只在 executor：

- `local`: Web 服务与 `comfyctl` 在同一台机器上。
- `ssh`: Web 服务通过 SSH 在远端执行 `comfyctl`。

### 4. Configuration Rule

`.env` 是部署级配置来源，每个部署独立维护：

- 远端部署时，远端 `.env` 是事实来源。
- macOS 本机部署时，本机 `.env` 是事实来源。
- `.env` 不提交 git。
- `.env.example` 提交 git，只作为模板，不作为运行配置。
- 不做自动双向同步，不在 UI 中承诺配置同步。
- P1/P2 都不包含配置迁移工具；迁移配置就是用户分别编辑各部署自己的 `.env`。

`.env.example` 应沿用当前骨架的 section 化 env key 风格：只暴露用户能理解且必须配置的意图变量，内部派生值由代码计算，启动时强制校验。

配置权威边界：

```text
.env
  部署级控制意图：API 监听、DATABASE__URL 数据库连接、可选数据根目录、默认安装参数、ssh executor 默认值
  不保存 instance 状态，不保存运行中 pid，不保存安装结果

PostgreSQL
  控制面元数据：host、model root、instance、command run
  不保存运行时权威状态
  不保存模型文件内容、模型扫描结果或模型库存

manifest.json
  单个 instance 的安装事实：requested ref、resolved commit、python、torch profile、创建时间
  不保存用户 secret，不覆盖 .env

pid/log/ready/status
  运行时证据：进程、端口、ComfyUI 健康、日志
  不回写成配置事实
```

计划中的 `.env.example` 分类：

```dotenv
# application identity
RUNTIME__APP_ENV=local
SERVICE__NAME=comfy-shell-v2
SERVICE__TITLE=Comfy Shell
SERVICE__API_PREFIX=/v1

# security
SECURITY__SERVICE_API_KEY=<replace-with-random-token>
SECURITY__DISABLE_AUTH=false
SECURITY__ALLOWED_ORIGINS=http://127.0.0.1:7800,http://localhost:7800

# control-plane database
DATABASE__URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:25432/comfy_shell
DATABASE__SSL=false
DATABASE__POOL_SIZE=5
DATABASE__MAX_OVERFLOW=10

# observability
OBSERVABILITY__LOG_LEVEL=INFO
OBSERVABILITY__ACCESS_LOG_ENABLED=true
OBSERVABILITY__HEALTH_ACCESS_LOG=false

# launcher process
API_HOST=127.0.0.1
API_PORT=7800
API_HOST_PORT=7800
COMPOSE_PROJECT_NAME=comfy-shell-v2
POSTGRES_DB=comfy_shell
POSTGRES_HOST_PORT=25432
REDIS_HOST_PORT=26379

# comfy shell defaults
# Empty means: derive data root from the comfy-shell-v2 service install directory.
COMFY__DATA_ROOT=
COMFY__INSTANCE_PORT_START=8188
COMFY__REPO_URL=https://github.com/comfyanonymous/ComfyUI.git
COMFY__DEFAULT_REF=
COMFY__PYTHON_VERSION=3.12
COMFY__TORCH_PROFILE=cu124
COMFY__BIND_HOST=127.0.0.1

# package indexes
UV_INDEX_URL=
PYPI_INDEX_URL=

# ssh executor, only used by macOS control-plane mode
EXECUTOR__MODE=local
SSH__TARGET=
SSH__CONNECT_TIMEOUT_SECONDS=10
SSH__REMOTE_COMFYCTL=
```

启动期必须校验：

- `API_HOST` 绑定公网地址时必须显式开启访问控制；默认只允许 `127.0.0.1`。
- `SECURITY__SERVICE_API_KEY` 不能是模板值。
- `DATABASE__URL` 必须是 PostgreSQL URL；远端部署时 Postgres 可由系统服务或当前 `scripts/deploy.sh compose-deps` 管理。
- `COMFY__DATA_ROOT` 为空时从服务安装目录自动派生；非空时必须是绝对路径。
- `EXECUTOR__MODE=ssh` 时必须有 `SSH__TARGET`，且不能禁用 host key 检查。
- 新增 Comfy/SSH env key 时必须同步 `app/core/config/env_manifest.py` 和 `.env.example`，否则 `scripts/verify.sh check` 应失败。

### 5. Path Derivation

默认目录借鉴 Comfy Desktop 的 `DataRoot -> Installs / Shared / Cache` 思路，但 Linux 远端不使用 `%LOCALAPPDATA%`、home 或写死 `/data/comfy-shell-v2`。

唯一默认规则：

```text
service_root = comfy-shell-v2 服务安装目录
data_root    = COMFY__DATA_ROOT if set else service_root
```

示例：服务安装在 `/data/wangqiao/comfy-shell-v2`，且 `COMFY__DATA_ROOT` 为空：

```text
/data/wangqiao/comfy-shell-v2/
  ComfyUI-Installs/
  ComfyUI-Shared/
    models/
    input/
    output/
  ComfyUI-Cache/
    download-cache/
```

派生规则：

```text
installs_dir          = data_root/ComfyUI-Installs
shared_dir            = data_root/ComfyUI-Shared
default_models_root   = data_root/ComfyUI-Shared/models
default_input_root    = data_root/ComfyUI-Shared/input
default_output_root   = data_root/ComfyUI-Shared/output
download_cache_dir    = data_root/ComfyUI-Cache/download-cache
```

`.env.example` 不暴露 `COMFY__INSTALLS_DIR`、`COMFY__SHARED_DIR`、`COMFY__CACHE_DIR`、`COMFY__DEFAULT_MODELS_ROOT`、`COMFY__DEFAULT_INPUT_ROOT` 或 `COMFY__DEFAULT_OUTPUT_ROOT`。这些路径都能从 `COMFY__DATA_ROOT` 和服务安装目录推导，写进 `.env` 只会增加漂移风险。

### 6. Repository Structure

当前骨架已经存在的通用目录应保留并复用：

```text
comfy-shell-v2/
  .env.example
  .gitignore
  pyproject.toml
  uv.lock
  start-api.sh
  app/
    main.py
    core/
      config/
      error_registry.py
      lifecycle.py
      middleware.py
      registry_checks.py
    api/
      operations.py
      routes/
        health.py
    schemas/
      envelope.py
      common.py
    db/
      database.py
      unit_of_work.py
      base.py
    repositories/
      base.py
    integrations/
      http_client.py
  alembic/
  tests/
  scripts/
    dev.sh
    run.sh
    deploy.sh
    verify.sh
    tools.sh
    lib/
    dev/
    verify/
  docs/
    current/
    contracts/
    plans/
    notes/
```

计划新增或替换为 Comfy Shell 领域目录：

```text
comfy-shell-v2/
  app/
    api/
      routes/
        hosts.py
        instances.py
        model_roots.py
        runs.py
    services/
      host_service.py
      instance_service.py
      installer_service.py
      process_status.py
      model_roots.py
      run_service.py
    schemas/
      host.py
      instance.py
      model_root.py
      run.py
      comfyctl.py
    models/
      host.py
      instance.py
      model_root.py
      command_run.py
    repositories/
      host_repository.py
      instance_repository.py
      model_root_repository.py
      command_run_repository.py
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
    remote.sh
  tests/
    test_hosts_api.py
    test_instances_api.py
    test_model_roots_api.py
    test_comfyctl_contract.py
    test_executors.py
```

当前 `items` 示例业务进入 Comfy Shell 实现阶段后应删除或隔离到模板示例之外，不能继续作为产品 API 暴露。

`docs/contracts/` 是当前仓库的稳定合同目录。不要再新增单数形式的合同目录。

计划中的运行时目录，默认从服务安装目录派生。示例中服务安装在 `/data/wangqiao/comfy-shell-v2`：

```text
/data/wangqiao/comfy-shell-v2/
  .env
  .venv/
  .run/
    api.pid
  logs/
    api.log
  ComfyUI-Installs/
    comfy-prod/
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
    comfy-test/
      ComfyUI/
      .venv/
      manifest.json
      extra_model_paths.yaml
      instance.lock
      .run/
        comfyui.pid
      logs/
        comfyui.log

  ComfyUI-Shared/
    models/
    input/
    output/

  ComfyUI-Cache/
    download-cache/
```

模型目录不放进 instance。默认共享模型目录是：

```text
/data/wangqiao/comfy-shell-v2/ComfyUI-Shared/models/
```

用户仍可在 UI 里额外登记外部模型目录，例如 `/mnt/models/shared`，但它是 `ModelRoot` 记录，不是 `.env` 默认派生路径。外部模型目录列表只能进入 PostgreSQL 的 `ModelRoot`，不得新增 `.env` 路径键来管理。

同步或部署脚本必须排除 service root 下的运行时与大数据目录：

```text
.env
.venv/
.run/
logs/
ComfyUI-Installs/
ComfyUI-Shared/
ComfyUI-Cache/
```

如果同步命令允许从 instance checkout 反向同步或打包，还必须排除每个 `ComfyUI/` checkout 内的运行时目录：

```text
ComfyUI/models/
ComfyUI/input/
ComfyUI/output/
ComfyUI/temp/
```

### 7. Data Model

PostgreSQL 只保存控制面元数据，不保存运行时真相。实现时复用当前 SQLAlchemy async、Alembic、UnitOfWork、repository、Postgres provider、Compose dependency 和 migration roundtrip 范式。

```text
Host
  id
  name
  connection            # local | ssh
  ssh_target            # ssh mode only
  service_root          # comfy-shell-v2 install directory on this host
  data_root             # resolved COMFY__DATA_ROOT or service_root
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
  instance_slug
  install_root          # computed read-only API field: data_root/ComfyUI-Installs/<instance_slug>
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
  kind                  # install | reinstall | start | stop | probe_host | check_model_root
  phase
  started_at
  ended_at
  exit_code
  error_code
  message
  log_path
  stderr_tail
```

`install_root` 可以作为 API 返回字段，但不应作为用户输入。实现时如果它始终能从 `Host.data_root` 和 `Instance.instance_slug` 推导，就不要单独建可写数据库列；需要缓存展示时也必须以派生值为准。

`CommandRun` 只记录会改变实例状态，或跨主机执行且需要审计的操作。`status`、`ready` 和 `logs` 是只读诊断，不默认写 `CommandRun`；它们通过 HTTP access log、`request_id` 和当前探测结果定位问题。这样不会把频繁刷新状态污染成业务历史。

不保存权威 `Instance.status`。实例状态来自实时探测：

```text
pid file -> process alive -> port open -> ComfyUI /system_stats
```

### 8. Instance Version And Reinstall

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

### 9. Command Boundary

`comfyctl` 是唯一管理 host 文件、环境、进程和日志的命令入口。Web 控制面不拼任意 shell 字符串，只传结构化参数。

计划中的 `comfyctl` 命令：

```text
comfyctl host probe --json
comfyctl instance install --id <id> --slug <instance_slug> --data-root <path> --repo <url> --ref <tag-or-commit> --python <version> --torch-profile <profile> --json
comfyctl instance start --id <id> --slug <instance_slug> --data-root <path> --host 127.0.0.1 --port <port> --extra-model-paths <yaml> --json
comfyctl instance stop --id <id> --slug <instance_slug> --data-root <path> --json
comfyctl instance status --id <id> --slug <instance_slug> --data-root <path> --json
comfyctl instance ready --id <id> --slug <instance_slug> --data-root <path> --json
comfyctl instance logs --id <id> --slug <instance_slug> --data-root <path> --tail 200
comfyctl model-root check --path <path> --json
```

`--data-root` 只能来自 `.env` 解析结果或 Host 记录里的 `data_root`，`--slug` 必须按 instance slug 规则校验。`comfyctl` 内部统一通过 `comfyctl/paths.py` 派生 `install_root = data_root/ComfyUI-Installs/<instance_slug>`；Web API 不接受用户提交任意 `install_root`，也不把 `ComfyUI-Installs`、`ComfyUI-Shared`、`ComfyUI-Cache` 拆成多个外部配置入口。

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
  "log_path": "/data/wangqiao/comfy-shell-v2/ComfyUI-Installs/comfy-prod/logs/comfyui.log"
}
```

### 10. HTTP Control Plane Boundary

HTTP API 是 UI 的稳定外部接口。具体内部使用 local executor 还是 ssh executor，不应泄漏给 UI。

本节是计划阶段草案，不是当前稳定合同。实现完成后，稳定 HTTP API、`comfyctl` JSON、错误码和事件流必须迁移到 `docs/contracts/`。

计划中的首版 API 使用当前骨架的 `SERVICE__API_PREFIX` 挂载机制。下表按默认 `/v1` 展示公开路径；operation registry 内部仍记录未挂载路径。

```text
GET  /v1/hosts
POST /v1/hosts
POST /v1/hosts/{host_id}/probe

GET  /v1/model-roots
POST /v1/model-roots
POST /v1/model-roots/{model_root_id}/check

GET  /v1/instances
POST /v1/instances
GET  /v1/instances/{instance_id}
POST /v1/instances/{instance_id}/install
POST /v1/instances/{instance_id}/reinstall
POST /v1/instances/{instance_id}/start
POST /v1/instances/{instance_id}/stop
GET  /v1/instances/{instance_id}/status
GET  /v1/instances/{instance_id}/ready
GET  /v1/instances/{instance_id}/logs

GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/events
GET  /v1/runs/{run_id}/logs
```

`POST /install`、`POST /reinstall`、`POST /start`、`POST /stop` 会创建 `CommandRun`。`GET /status`、`GET /ready` 和 `GET /logs` 是只读诊断接口，不创建 `CommandRun`，不改变 pid、manifest、model root 或数据库元数据。

普通成功响应沿用当前骨架 envelope：

```json
{
  "request_id": "req_xxx",
  "trace_id": "trace_xxx",
  "server_time": "2026-09-03T00:00:00Z",
  "code": "OK",
  "data": {}
}
```

普通错误响应沿用当前骨架 error envelope：

```json
{
  "request_id": "req_xxx",
  "trace_id": "trace_xxx",
  "server_time": "2026-09-03T00:00:00Z",
  "code": "PORT_IN_USE",
  "message": "port 8188 is already in use",
  "retryable": false,
  "details": {
    "layer": "process",
    "log_path": "/data/wangqiao/comfy-shell-v2/ComfyUI-Installs/comfy-prod/logs/comfyui.log"
  }
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

### 11. UI Feature Set

首版 UI 是管理工具，不是营销页。

页面：

- Hosts: 查看当前 host、连接方式、service root、data root、GPU 探测结果。
- Instances: 列表显示名称、版本、端口、GPU、模型目录、最近启动时间、实时状态。
- Instance Detail: 启动/停止/重装、版本信息、日志、模型目录、启动参数。
- Model Roots: 添加、检查、设置默认模型根目录。
- Runs: 查看安装/重装/启动/停止历史、退出码、错误码、日志尾部。
- Settings: 显示部署级配置状态，只显示可安全公开的 `.env` 摘要，不显示 secret。

关键交互：

- 新建 instance 时必须选择 host、instance name/slug、ComfyUI ref、Python version、Torch profile、port、model roots；`install_root` 由 `data_root/ComfyUI-Installs/<instance_slug>` 派生，不能作为用户输入。
- 重装前显示将要替换的 instance、目标 ref、当前 resolved commit、模型目录“不受影响”。
- 启动前检查端口、pid、model root 可读性和 `extra_model_paths.yaml`。
- 所有长命令显示 run id、phase、日志路径和可复制的诊断摘要。

### 12. Service Management

当前骨架已经落地 `embedding-service` 风格的服务管理模式。Comfy Shell 实现阶段应扩展现有入口，而不是新增一套平行脚本体系：

```text
start-api.sh
  -> load .env through current settings path
  -> validate API_HOST/API_PORT/SECURITY__SERVICE_API_KEY/DATABASE__URL
  -> exec .venv/bin/python -m uvicorn app.main:app

scripts/dev.sh
  -> keep current bootstrap/doctor/ports/run/start/stop/status/restart/logs/migrate/test
  -> continue writing .run/api.pid and logs/api.log
  -> add Comfy-specific doctor checks only when they are local and cheap

scripts/remote.sh
  -> new Comfy Shell entry, not present in current skeleton
  -> explicit sync/bootstrap/start/stop/status/logs/tunnel
  -> require --yes for remote write/lifecycle commands
  -> exclude .env, .venv, .run, logs, ComfyUI-Installs, ComfyUI-Shared, ComfyUI-Cache

scripts/run.sh
  -> keep as daily local recipe wrapper
  -> P1 keep dev recipe only
  -> P2 may add remote-gpu recipe, but it must call remote.sh instead of duplicating ssh logic

scripts/deploy.sh
  -> existing Docker Compose helper can manage PostgreSQL for local/dev deployment
  -> Redis helper remains skeleton capability, not a required Comfy Shell business dependency
  -> must not containerize ComfyUI instances

scripts/verify.sh
  -> keep current env/syntax/registry/alembic/scripts/pytest checks
  -> add comfyctl command contract smoke
  -> add Comfy domain API contract drift checks

scripts/tools.sh
  -> keep current no-persistent-side-effect tools
  -> may add token/path helper commands only if they do not mutate instance state
```

服务管理不负责 ComfyUI 实例内部生命周期；它只管理控制面服务和开发/部署入口。ComfyUI instance 生命周期由 `comfyctl instance *` 管理。

### 13. Security And Failure Diagnostics

默认安全边界：

- FastAPI 默认绑定 `127.0.0.1`。
- ComfyUI 默认绑定 `127.0.0.1`。
- 远端访问默认通过 SSH tunnel。
- 写 API 需要 `SECURITY__SERVICE_API_KEY`。
- 校验 `Origin` 和 `Host`，不允许默认 `CORS *`。
- 不存 SSH 密码或私钥内容。需要 SSH 时只记录 target、key path 和 host key fingerprint。
- 不使用 `StrictHostKeyChecking=no`。
- 不接受任意 shell command 输入。
- 所有路径先做 canonical `realpath` 校验，拒绝 instance 路径逃逸 `data_root/ComfyUI-Installs`。

失败分层：

```text
config      .env missing/invalid, database connection invalid
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

### 14. Architecture Review Checklist

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
- 运行时状态实时探测，不把 PostgreSQL 里的旧记录当进程事实。

半年后还能改吗：

- PostgreSQL schema 明确 host、instance、model root、run 的边界。
- instance 自带 checkout 和 `.venv`，版本切换不会影响其他实例。
- 模型目录独立于 instance，重装不会触碰已下载模型。
- `comfyctl` 合同小，后续可以替换内部实现而不破坏 UI。

## Acceptance

计划阶段完成标准：

- 文档明确区分当前事实和未来计划。
- 文档承认当前已有 FastAPI-lite 骨架，不再把 FastAPI 控制面写成未开始。
- 文档明确当前骨架仍是模板语义，Comfy Shell domain 还未实现。
- 文档写清默认远端部署形态、本机 SSH 控制形态，以及二者只通过 executor 区分。
- 文档明确 `.env` 不提交、不自动同步，`.env.example` 只作为模板。
- 文档明确 `COMFY__DATA_ROOT` 为空时从服务安装目录派生默认目录，且派生目录不写进 `.env.example`。
- 文档写清 instance、version、reinstall、model root 的所有权边界。
- 文档写清首版不做的复杂机制。
- 文档写清现有骨架复用点、目标目录结构、数据模型、`comfyctl` 边界、HTTP API 草案、服务管理脚本和失败诊断规则。

P1 实现阶段完成标准：

- 服务身份从 `fastapi-lite` 收敛为 `comfy-shell-v2`，包括 `pyproject.toml`、`.env.example`、README 和 docs。
- 示例 `items` 业务被删除或隔离，不作为产品 API 暴露。
- `DATABASE__URL` 使用 PostgreSQL；现有 Postgres provider、Compose 依赖管理和 migration roundtrip 验证继续有效。
- 新增 Host、Instance、ModelRoot、InstanceModelRoot、CommandRun 的 schema、ORM model、repository、service、migration、route、operation registry 和测试。
- 默认生成一个 `connection=local` 的 Host，并能显示 `service_root`、`data_root` 和 GPU 探测结果。
- `COMFY__DATA_ROOT` 为空时，从服务安装目录创建 `ComfyUI-Installs`、`ComfyUI-Shared/models`、`ComfyUI-Shared/input`、`ComfyUI-Shared/output` 和 `ComfyUI-Cache/download-cache`。
- `docs/contracts/api-contract.md` 更新为 Comfy Shell API 合同，包含 `POST /install`、`POST /reinstall`、`POST /start`、`POST /stop` 和只读 `GET /status`、`GET /ready`、`GET /logs`，且 registry/docs drift check 通过。
- `app/core/config/env_manifest.py` 和 `.env.example` 包含 Comfy/SSH 配置 key，未知或废弃 key 能被验证拦住。
- `comfyctl` 只接受 `--data-root` 和 `--slug` 派生 instance 路径，不接受任意 `--root` 或用户提交的 `install_root`。
- `scripts/dev.sh start|stop|status|restart` 继续能管理控制面 pid/log。
- `scripts/remote.sh` 提供显式 status/logs/tunnel；如果执行远端写操作，必须要求 `--yes`，并排除 `.env`、`.venv`、`.run`、`logs`、`ComfyUI-Installs`、`ComfyUI-Shared`、`ComfyUI-Cache` 和本地运行产物。
- `comfyctl host probe --json`、`comfyctl instance install --json`、`comfyctl instance status --json`、`comfyctl instance ready --json` 和 `comfyctl instance logs` 可在 Linux host 上运行。
- UI 至少提供 Hosts、Instances、Instance Detail、Model Roots、Runs 和 Settings 页面，覆盖单 host 完整生命周期。
- 可以创建一个 instance，安装指定 ComfyUI tag/commit，启动后通过 SSH tunnel 打开 ComfyUI Web。
- 重装同一 instance 后，原模型目录仍存在且未被修改。
- 端口冲突、SSH 失败、git 失败、uv 失败、ComfyUI 启动失败都返回稳定错误码和日志路径。

P1 关闭前必须通过：

```bash
./scripts/verify.sh check
./scripts/verify.sh postgres
./scripts/verify.sh migration-roundtrip
```

P2 实现阶段完成标准：

- `EXECUTOR__MODE=ssh` 可用，同一套 HTTP API 和 UI 可以管理 `connection=ssh` 的 Host。
- Host 新增/编辑支持 `ssh_target`、`service_root`、`data_root`、`host_key_fingerprint` 和远端 `comfyctl` 路径。
- SSH executor 只执行结构化 `comfyctl` 命令，不接受 UI 或 API 传入任意 shell command。
- 远端 `comfyctl host probe` 能返回 GPU、Python、uv、git、磁盘和目录权限诊断。
- SSH host key mismatch、auth failed、connect timeout、remote comfyctl missing、remote permission denied 都必须归类为 `ssh` 或 `filesystem` layer，而不是合并为 generic error。
- 同一个远端 Host 上可以创建、安装、启动、停止、重装、查看 status/ready/logs，不新增第二套 instance API。
- model root 归属于 Host；检查远端 model root 时使用远端文件系统事实，不用 macOS 本机路径判断。
- `scripts/remote.sh` 提供 sync/bootstrap/start/stop/status/logs/tunnel，远端写操作要求 `--yes`，并继续排除 `.env`、运行时目录和大数据目录。
- P2 不做自动配置同步；用户需要分别维护本机 `.env` 和远端 `.env`。

P2 关闭前必须通过：

```bash
./scripts/verify.sh check
./scripts/remote.sh status --host <user@host> --dir <remote-dir>
./scripts/remote.sh tunnel --host <user@host>
```

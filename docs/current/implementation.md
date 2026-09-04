# Current Implementation

本文记录 `comfy-shell-v2` 当前已经实现并由测试覆盖的工程事实。它不描述未来计划；未实现内容见 [`../plans/linux-comfyui-web-launcher.md`](../plans/linux-comfyui-web-launcher.md)。

## Runtime Model

`comfy-shell-v2` 当前按三层组织：

```text
foundation
  -> config / logging / request context / error envelope / registries / scripts
integrations
  -> Postgres lifecycle / Redis fake boundary / object storage / shared HTTP client
comfy domain
  -> hosts / model roots / instances / command runs / local executor / comfyctl
```

FastAPI app 由 `app.main.create_app()` 创建。`lifespan` 在启动期构建 health registry 和 lifecycle provider registry，按顺序启动 provider，注册 readiness checks，并在启动后冻结 registry；关闭时按反序释放资源。

## HTTP Foundation

已实现的 HTTP 基础能力：

- `/health` 返回进程存活状态。
- `/ready` 聚合 `process`、`postgres`、`redis`、`object_storage`、`http_client` checks。
- 响应统一使用 success/error envelope。
- `X-Request-ID` 和 `X-Trace-ID` 会被生成、校验、透传并写回响应 header。
- `RequestContextMiddleware` 负责 request/trace header 校验、context 注入、响应 header 回写和 access log。`create_app()` 显式安装 `RequestContextMiddleware` 和 `CORSMiddleware`。
- `RequestValidationError` 映射为 `REQUEST_INVALID`。
- `AppError` 通过 error registry 映射为注册错误码。
- 未捕获异常映射为 `INTERNAL_ERROR`，响应不暴露内部异常细节。
- access log、`AppError` log 和未捕获异常 log 都带稳定字段：`request_id`、`trace_id`、`method`、`path`、`operation_id`、`status`、`duration_ms`、`error_code`。
- operation registry 记录 method、未挂载 path、operation id、成功状态码、auth 要求、route-specific 业务错误码和 schema 名称。业务 route 的公开路径由 `SERVICE__API_PREFIX` 渲染，避免在 registry、router 和文档中重复硬编码 `/v1`。
- registry drift check 会校验 route method/path/operation id/成功状态码、OpenAPI request schema、OpenAPI error response、OpenAPI security、已注册错误码，以及 `docs/contracts/api-contract.md` 的 Routes 表关键字段。
- `/ui/` 返回轻量 Web 控制台 HTML，并从 `SERVICE__API_PREFIX` 注入 API 前缀；该页面不进入 operation registry，HTTP API 合同仍以 `/v1/*` 为默认展示。

## Configuration

配置使用 `app/core/config/` 的 section 化模型：

- `RuntimeSettings`
- `ServiceSettings`
- `SecuritySettings`
- `DatabaseSettings`
- `RedisSettings`
- `StorageSettings`
- `HttpClientSettings`
- `ObservabilitySettings`
- `ComfySettings`
- `ExecutorSettings`
- `SshSettings`

`AppSettings` 只聚合 section 并执行跨 section 校验。`env_manifest.py` 是 `.env.example` key 的可执行清单，`scripts/verify/env_config_check.py` 会校验 example key、未知 key、废弃 key、派生 key 和 release profile 约束。

## Database And Comfy Domain

当前数据库层使用 SQLAlchemy async 和 Alembic：

```text
route
  -> service
  -> UnitOfWork
  -> repository
  -> ORM model
  -> migration
```

Comfy Shell P1 产品 API 已经实现：

- `GET /v1/hosts`
- `POST /v1/hosts`
- `POST /v1/hosts/{host_id}/probe`
- `GET /v1/model-roots`
- `POST /v1/model-roots`
- `POST /v1/model-roots/{model_root_id}/check`
- `GET /v1/instances`
- `POST /v1/instances`
- `GET /v1/instances/{instance_id}`
- `POST /v1/instances/{instance_id}/install`
- `POST /v1/instances/{instance_id}/reinstall`
- `POST /v1/instances/{instance_id}/start`
- `POST /v1/instances/{instance_id}/stop`
- `GET /v1/instances/{instance_id}/status`
- `GET /v1/instances/{instance_id}/ready`
- `GET /v1/instances/{instance_id}/logs`
- `GET /v1/runs`
- `GET /v1/runs/{run_id}`

`hosts`、`model_roots`、`instances`、`instance_model_roots` 和 `command_runs` 是当前控制面表。`install_root` 不是用户输入字段，由 `Host.data_root` 和 `Instance.instance_slug` 派生为 `data_root/ComfyUI-Installs/<instance_slug>`。

`POST /v1/hosts/{host_id}/probe` 调用 `comfyctl host probe`，会创建并返回 data root 下的标准目录，探测 `git`、`uv`、当前 Python、`nvidia-smi`、NVIDIA driver、CUDA runtime 上限和 GPU 列表。probe 同时返回 `runtime_recommendation`，用于 UI 预填新实例的 `comfy_ref`、`python_version`、`torch_profile` 和 `gpu_ids`；它不会修改已创建实例。当前推荐规则很窄：探测到 NVIDIA GPU 且 CUDA 版本不低于 12.4 时推荐 `comfy_ref=8b099de36acd81acd1afa3b5442951dc847e0a52`、`python_version=3.12`、`torch_profile=cu124` 和第一张 GPU；否则推荐 `comfy_ref=master`、`python_version=3.12`、`torch_profile=requirements`，并在 GPU 存在但没有匹配 profile 时返回 warning。远端实测结论是：NVIDIA A10 / Driver 550 / CUDA 12.4 可以运行该兼容 ref、Python 3.12 和 torch 2.6.0+cu124；当前 ComfyUI master 搭配 torch 2.6.0+cu124 会在 `comfy-kitchen==0.2.31` 初始化阶段失败。

`status`、`ready` 和 `logs` 是只读诊断接口，不写入 `CommandRun`。`install`、`reinstall`、`start`、`stop` 会创建 `CommandRun`，保存 exit code、错误码、日志路径和 stderr tail。

旧 `items` 示例代码仍保留在仓库中作为隔离的模板示例和 repository/service 测试对象，但不再由 `app.main.create_app()` 挂载为产品 API。

普通测试使用 SQLite in-memory session override；PostgreSQL integration 测试必须显式通过 `./scripts/verify.sh postgres` 启用，并由 `_test` 数据库保护。

`app.models` 是 ORM metadata 的显式注册入口。Alembic env、SQLite 测试建表和 migration roundtrip 都通过导入 `app.models` 触发已注册模型加载，再使用 `Base.metadata` 作为表集合来源。`scripts/verify/migration_roundtrip.py` 的 head schema 断言按 registered metadata 表集合校验，不硬编码 `items`。

`UnitOfWork` 必须显式接收 `session_factory`，业务 service 必须由 route、worker 或测试这样的 composition root 注入 `UowFactory`。HTTP route 从 `request.app.state.db_session_factory` 构造 `UowFactory`，避免 service 或 repository 隐式依赖进程级全局数据库状态。

## Providers

当前 lifecycle providers：

| Provider | 当前实现 | Ready 语义 |
|---|---|---|
| `postgres` | app lifespan 内创建 async engine 和 session factory；测试可显式覆盖 session factory。 | 非 override 场景必须是 PostgreSQL URL，并执行 `SELECT 1`。 |
| `redis` | fake client；`REDIS__ENABLED=true` 会显式失败。 | fake client 未关闭则 ok。 |
| `object_storage` | `disabled` backend 和 local filesystem backend。 | provider 成功启动则 ok。 |
| `http_client` | shared `httpx.AsyncClient`，注入 request/trace headers。 | client 未关闭则 ok。 |

业务请求路径通过 typed dependency 从 `request.app.state` 获取资源，不通过 lifecycle registry 字符串查找，也不依赖模块级数据库懒初始化。

## Tools

`app/tools/example_tool.py` 提供一个纯函数工具示例：

- `ToolSpec` metadata。
- `ExampleToolInput` / `ExampleToolOutput` schema。
- `slugify_text()` callable。
- `validate_example_tool_spec()` drift check。

首版工具模块不做运行时动态发现和动态执行。

## Comfyctl

`comfyctl` 是主机侧唯一命令入口，源码在 `comfyctl/`，可执行入口在 `bin/comfyctl`。当前支持：

- `comfyctl host probe --data-root <path> --json`
- `comfyctl model-root check --path <path> --json`
- `comfyctl instance install --id <id> --slug <slug> --data-root <path> --repo <url> --ref <ref> --python <version> --torch-profile <profile> --json`
- `comfyctl instance start --id <id> --slug <slug> --data-root <path> --host <host> --port <port> --extra-model-paths <path> --gpu <id> --json`
- `comfyctl instance stop --id <id> --slug <slug> --data-root <path> --json`
- `comfyctl instance status --id <id> --slug <slug> --data-root <path> --host <host> --port <port> --json`
- `comfyctl instance ready --id <id> --slug <slug> --data-root <path> --host <host> --port <port> --json`
- `comfyctl instance logs --id <id> --slug <slug> --data-root <path> --tail <n>`

`comfyctl` 不接受任意 `install_root`。它只接受 `--data-root` 和 `--slug`，再由 `comfyctl.paths` 派生安装目录、共享目录和缓存目录。
`host probe` 会输出 `driver_version`、`cuda_version`、`gpus`、`nvidia_smi_error` 和 `runtime_recommendation`。推荐结果只是调用方创建实例时的输入建议；`install` 和 `reinstall` 默认使用实例记录中已经保存的 `comfy_ref`、`python_version` 和 `torch_profile`，也可以通过 API 请求中的 `comfy_version_id` 或高级 `comfy_ref` 明确切换安装 ref。成功安装后，实例记录保存解析后的 `comfy_ref` 和 `resolved_commit`。
`--torch-profile` 当前支持 `requirements` 和 `cu124`；`cu124` 会先使用 `uv pip install --torch-backend cu124`
安装已固定的 CUDA 12.4 版本组：`torch==2.6.0+cu124`、`torchvision==0.21.0+cu124`、`torchaudio==2.6.0+cu124`，再安装过滤掉这三个包的 ComfyUI requirements。普通 Python
依赖继续使用环境中的默认 PyPI 源或镜像，避免把所有包都压到 PyTorch wheel index 上。

## Scripts And Verification

可用入口：

- `./scripts/dev.sh help`
- `./scripts/dev.sh doctor`
- `./scripts/dev.sh ports`
- `./scripts/dev.sh migrate`
- `./scripts/deploy.sh help`
- `./scripts/deploy.sh up|down|status compose-deps`
- `./scripts/deploy.sh up|down|status compose-full`
- `./scripts/run.sh up|status|down|restart|check dev`
- `./scripts/verify.sh check`
- `./scripts/verify.sh postgres`
- `./scripts/verify.sh migration-roundtrip`
- `./scripts/remote.sh status|logs|tunnel`
- `./scripts/tools.sh secret`
- `./scripts/tools.sh env-url`

`dev.sh` 当前提供本地 API 进程管理、端口扫描、环境检查、迁移和测试快捷入口，`status` 会展示有效的 API URL、Web UI URL、Comfy data root、installs、shared、models、input、output 和 download cache 目录，但不创建这些目录。`deploy.sh` 当前只管理 Docker Compose 目标：`compose-deps` 管理 Docker PostgreSQL / Redis；`compose-full` 管理 Docker API / PostgreSQL / Redis，并通过 `start-api.sh` 作为 API 容器入口。`run.sh` 当前提供日常本地开发 recipe：`dev` 表示日常开发环境全集，`up dev` 固定顺序是 `deploy.sh up compose-deps`、`dev.sh migrate`、`dev.sh start api`、`dev.sh status`；`status dev` 汇总宿主机 API 状态和 compose-deps 状态。`remote.sh` 当前提供 macOS 到远端 GPU host 的 `status`、`logs` 和 `tunnel` 辅助，可从 CLI、环境变量、`.env`、`ENV_FILE` 或 `--profile` 读取 `REMOTE_HOST`、`REMOTE_DIR` 和 tunnel 端口；CLI 参数优先级最高，未配置远端地址时直接报错，不猜 hostname，不同步 `.env`，不管理 ComfyUI instance 生命周期。三种管理方式分别是：日常入口 `run.sh up|status|down|restart|check dev`；单进程入口 `dev.sh start|status|stop api`；Docker 入口 `deploy.sh up|status|down compose-deps|compose-full`。`verify.sh check` 当前覆盖 env、syntax、registry、alembic、scripts、`comfyctl` smoke 和 pytest；`postgres` 与 `migration-roundtrip` 是显式 PostgreSQL gate。`tools.sh` 当前提供无默认持久副作用的 secret 和 env URL 生成工具。

## Verification Baseline

当前验收命令：

```bash
./scripts/verify.sh check
./scripts/deploy.sh check
```

PostgreSQL 集成测试和 migration roundtrip 是显式 gate：

```bash
./scripts/verify.sh postgres
./scripts/verify.sh migration-roundtrip
```

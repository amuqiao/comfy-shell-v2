# Comfy Shell Docs

本文是 `comfy-shell-v2` 的文档入口。当前项目已经从 FastAPI 模板收敛为 Linux ComfyUI Web 启动器的 P1 实现。

## 阅读路径

```text
current/implementation.md
  -> contracts/api-contract.md
  -> runbooks/comfyui-remote-startup-incident-2026-09-04.md
  -> plans/linux-comfyui-web-launcher.md
  -> ../scripts/README.md
```

各文档职责：

| 文档 | 职责 |
|---|---|
| [Current Implementation](current/implementation.md) | 当前已经实现并由测试覆盖的工程事实。 |
| [API Contract](contracts/api-contract.md) | 当前调用方可依赖的 HTTP header、envelope、route、错误码和兼容性合同。 |
| [ComfyUI Remote Startup Incident 2026-09-04](runbooks/comfyui-remote-startup-incident-2026-09-04.md) | 远端 A10/CUDA 12.4 环境安装启动事故复盘、根因、验证结果和再发生排查顺序。 |
| [Linux ComfyUI Launcher Plan](plans/linux-comfyui-web-launcher.md) | P1/P2 阶段边界、架构约束和验收标准。 |
| [Extension Contract](contracts/extension-contract.md) | 新增业务模块、配置、provider、middleware、工具和脚本时必须遵守的工程合同。 |
| [Scripts Contract](../scripts/README.md) | 本地开发、验证、部署和远端辅助脚本的稳定入口合同。 |

## 文档边界

```text
docs/current/    -> 已实现事实
docs/contracts/  -> 调用方或开发者可依赖的稳定合同
docs/runbooks/   -> 事故复盘、现场排查顺序和运维记录
docs/plans/      -> 未完成缺口、计划和验收标准
docs/notes/      -> 心智模型和历史输入，不等同于当前实现合同
```

不要把 `docs/plans/` 中的内容当作当前能力；只有代码、测试、脚本或迁移已经支持的行为，才能进入 `docs/current/` 或 `docs/contracts/`。

# Changelog

本文件记录对使用者可见的版本变化。版本号遵循 `pyproject.toml`；GitHub Tag、Release 和制品发布仍由维护者手动执行。

## [0.1.0] - 2026-08-29

`0.1.0` 已于 2026-08-29 从提交 `33cbb6e` 发布；GitHub Release 附带经过验收的 sdist 和 wheel。

### Added

- Windows `scan`、`snapshot`、`compare` 和有限工作区探针；
- `agent-doctor`、`command-doctor`、`git-doctor`、`project-doctor` 和 `support-report`；
- Host 与 Coding Agent 分别采样、再进行差分的稳定 JSON 协议；
- PATH refresh、PowerShell launcher、Execution Policy、WindowsApps 候选和工作区能力的脱敏诊断；
- Windows CI（Python 3.12/3.14）、261 项自动化测试、Ruff 和 sdist/wheel 本地安装验收；
- 英文访客入口、中文完整说明、外部试运行手册和最小隐私边界说明；
- 面向报告者的 GitHub Bug Issue 表单，仅收集脱敏的最小复现。

### Boundaries

- 诊断默认离线、只读，不登录、不联网、不自动修复、不提权；
- 不修改 PATH、注册表、Execution Policy、ACL、Agent 配置或项目代码；
- 不采集凭据，不要求上传原始快照、完整 PATH 或业务文件；
- 外部试运行是可选反馈入口，不是使用本版本的前置条件；
- `0.1.0` 发布后暂缓功能扩展，维护和反馈响应继续。只有新的外部证据达到项目路线中记录的恢复条件时，才重新评估实现工作。

### Validation

- 本地全量 pytest：261 passed；
- Ruff：通过；
- `git diff --check`：通过；
- 真实只读 CLI、脱敏规则、Markdown 本地链接和公开身份语气检查：通过；
- sdist/wheel 构建与两个临时干净环境安装：已在本地完成；首次隔离构建受 PyPI 网络权限限制，按授权重试成功；两个制品已上传到 GitHub Release。
- 发布提交 `33cbb6e` 的 [Windows CI](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/33254944797) 已通过 Python 3.12、Python 3.14 和包构建安装验收。

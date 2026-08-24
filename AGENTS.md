# Windows Agent Preflight Agent 规则

本文件只写项目特有约定；通用协作规则由上级工作区 `AGENTS.md` 提供。

## 项目概述

- 目标：诊断 Windows 宿主与 Coding Agent 使用的命令、Shell 和项目工具链事实。
- 核心入口：`src/win_agent_preflight/cli.py`，CLI 名称 `agent-preflight`。
- 当前阶段：`scan`、`snapshot`/`compare`、只读注册表 PATH 刷新诊断、`workspace-probe`、`agent-doctor`、`support-report` v2、`project-doctor`、snapshot 写入快速失败修复和 Windows CI/包验收均已有稳定远程验证。

## 环境和命令

- 安装/准备：`python -m pip install -e ".[dev]"`
- 构建验收：`python -m build --sdist --wheel`（完整步骤见 `docs/release-check.md`）
- 运行：`python -m win_agent_preflight scan`、`agent-preflight snapshot --label host --output .\\snapshots\\host.json`、`agent-preflight compare baseline.json current.json`、`agent-preflight workspace-probe --target . --allow-write`、`agent-preflight agent-doctor --json`、`agent-preflight support-report --json`、`agent-preflight project-doctor --target . --json --pretty`
- 针对性测试：`python -B -m pytest -q -p no:cacheprovider`
- 完整测试：先运行 `python -B -m pytest -q -p no:cacheprovider`，通过后再运行 `python -m ruff check . --no-cache`。
- 构建或检查：`python -m ruff check . --no-cache`；打包验收不得替代测试。
- 清理缓存：本阶段不建设项目缓存；pytest/ruff 生成的缓存可直接删除。

## 项目约定

- 目录职责：`models.py` scan 数据模型；`runner.py` 外部命令边界；`windows.py` Windows 事实采集和 Agent launcher lstat；`checks.py` 诊断分类与预计算检查注入；`snapshot.py` EnvironmentSnapshot v1、解析、写出与比较；`compare.py` 差异输出；`workspace_probe.py` 独立 WorkspaceProbeReport v1 与有边界的写入探针；`agent_doctor.py` 独立 AgentDoctorReport v1 与最小版本探针；`support_report.py` 独立 SupportReport v2 组合和纯 `next_checks` 推导；`project_doctor.py` 独立 ProjectDoctorReport v1、固定第一层 marker 推导和工具版本探测；`reporting.py` 输出；`cli.py` 参数与编排。
- `snapshot.py` 的写入只使用目标父目录内本次生成的 UUID 临时名和一次 `O_EXCL` 创建；最多重试三次名称碰撞，其他写入错误立即失败。写入完成后按 `--force` 选择替换或硬链接，失败时只清理本次已知临时文件，不扫描目录。
- 代码风格：Python 类型标注、不可变数据模型优先；公共序列化字段使用稳定 snake_case。
- 数据和配置位置：扫描只读取当前环境，不保存配置和凭据。
- 不得修改的上游或生成文件：不触碰工作区其他项目；不创建项目级 `.codex`。

## 修改边界

- 当前允许的结构调整：围绕既有 CLI 稳定边界、只读注册表 PATH 刷新诊断、独立 `agent-doctor` 和 `support-report` v2 的最小模块调整。
- 需要保留的数据或接口：`CheckResult` JSON 字段、`Runner` 注入边界和 `%USERPROFILE%` 脱敏规则。
- 默认不兼容的旧实现：项目尚无旧版本；不为假设中的 Linux/macOS 兼容矩阵设计。

## 项目级效率规则

- 外部命令只能通过 `Runner` 执行，并且必须有超时。
- `scan` v1 JSON 和退出语义保持稳定；快照只内嵌已有 scan，不另造检查协议。
- 快照默认不覆盖已有输出，比较输入错误/版本错误/类型错误退出 2。
- 快照写出使用有界临时文件创建：单次 `O_EXCL` 创建只对 `FileExistsError` 重试，最多三个 UUID 名称；权限或其他写入错误快速返回 `SnapshotError`，不扫描目录或后台重试。
- 不联网、不修改 PATH、注册表、执行策略或 Agent 配置。
- `workspace-probe` 只接受显式 `--target` 与 `--allow-write`；结论只适用于一次命令、一个目标目录和当前进程上下文。
- `workspace-probe` 只创建目标直接子目录中的本次随机探针；按 Windows 对象身份复核本次已知两个文件和空目录后做路径级清理，不遍历目标、不递归删除、不处理历史残留。
- `workspace-probe` 面向非对抗的本地诊断；不支持其他进程在“身份复核—路径操作”的瞬间替换同名对象，也不为消除该 TOCTOU 窗口引入句柄级安全实现。
- `workspace-probe` 的固定六项使用独立 v1 schema，不修改 `scan`/`snapshot` 的 JSON 字段和退出语义。
- `agent-doctor` 使用独立 AgentDoctorReport v1，不复用 `CheckResult`，不修改 `scan`/`snapshot`/`workspace-probe` schema 或 checks 语义。
- `agent-doctor` 默认只检查 `codex`、`claude`、`dsh`；重复 `--agent` 固定去重顺序；同一 Agent 可按 PATH 顺序探测多个已解析的 `.exe`/`.cmd`/`.bat`/`.ps1` 普通 launcher，每个候选最多执行一次 `--version`。
- `agent-doctor` 只有 `--version` 退出 0 且 stdout/stderr 至少有一条非空文本时才报告 `usable`；成功结果保存脱敏后的第一条非空版本行（最多 200 字符），报告固定包含 `kind=agent_doctor` 和 `offline=true`。
- `agent-doctor` 禁止 login/doctor/npx/web/网络调用；lstat/Runner 错误只使用结构化 `error_type`/`winerror`/返回码/超时，不回显 stdout/stderr。
- `agent-doctor` 的 `command_not_found` 退出 0；其他非 `usable` 状态退出 1；输入错误退出 2。WindowsApps alias/lstat 异常不得降级为 command_not_found。
- `support-report` 复用同一个 Runner、env 和 timeout，先执行 `agent-doctor`，再将三类 Agent 结果作为预计算 `CheckResult` 注入 `scan_environment`；Agent Doctor 的多候选回退由其自身完成，scan 不再重复探测这三个 Agent。
- `support-report` 是离线只读组合报告：不运行 workspace-probe/login/doctor/npx/web/网络，不写文件；只保留有限环境事实，采集异常脱敏截断并保留另一部分结果。完整退出 0，部分采集失败退出 1，输入错误退出 2。
- `project-doctor` 只接受显式 `--target`，仅检查十个固定第一层 basename：Python、Node/npm/pnpm、yarn/bun lockfile 和 CMake marker；不 glob、递归或读取内容。未列入固定表的项目文件（例如 Makefile、Cargo.toml、go.mod）忽略，不否定其他可靠 marker。
- `project-doctor` 的 target/platform/timeout 错误退出 2；marker 的 PermissionError/OSError、symlink、reparse point 或非普通项累计为脱敏 `unknown`，继续处理其他可靠 marker 和工具，最终退出 1。报告 checks 固定以 `project.markers` 开头，再按 python、node、npm、pnpm、cmake 顺序排列；工具 details 的 `required_by` 为固定有序 marker 名称。
- `SupportReport v2` 顶层固定保留 v1 字段并增加 `next_checks`；内嵌 scan/Agent Doctor 仍为 v1。`derive_next_checks(scan, doctor)` 是纯函数，只读取既有模型，不解析 summary/evidence、不运行命令、不读取环境。
- `next_checks` 只允许 Agent `access_denied`/`version_probe_failed`、PowerShell 裸 npm warning、PATH refresh warning/unknown 四类触发；不为 `command_not_found`、`resolved_but_not_executable`、`usable` 或注入的 Agent scan checks 生成建议，按固定优先级和 codex/claude/dsh 顺序去重。
- CI 只运行在 Windows，测试 Python 3.12/3.14；Ruff 只在 3.12 运行；不启用 Actions 缓存。
- CI 包验收只构建并安装 sdist/wheel，不自动发布 PyPI、创建 Release、签名、生成 SBOM 或构建其他平台制品；Python 3.12/3.14 已由 Windows CI 实际验证。
- 不采集或打印密钥值；不计算哈希。
- 未安装的可选 Agent 为 `warning`，不是 `fail`；此规则仅适用于 `scan` 的 `CheckResult`，`agent-doctor` 使用 `command_not_found` 并按约定退出 0。
- `fail` 必须带证据；证据不足使用 `unknown`。

## Git

- 分支约定：由主 Agent 建立仓库后确认。
- 提交粒度：一个可运行、可验证的切片一个逻辑提交。
- 提交前必须运行：`python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache` 和一次真实 CLI。
- 远程推送由主 Agent 按用户已给授权执行。

## 本机环境建议

- 保留已验证的 Python 3.12，并建议并行安装 Python 3.14，使用 `py -3.12`/`py -3.14` 选择解释器。
- 远程操作前用 `gh auth status` 核对 GitHub CLI 身份；当前恢复点已验证认证可用。Node.js、Docker 和 WSL 对当前项目不是必需依赖。

# Windows Agent Preflight Agent 规则

本文件只写项目特有约定；通用协作规则由上级工作区 `AGENTS.md` 提供。

## 项目概述

- 目标：作为 Windows Coding Agent 的执行上下文差异诊断工具，比较宿主终端与 Agent 沙箱中的命令、PATH、Shell、启动器和工作区能力。
- 核心入口：`src/win_agent_preflight/cli.py`，CLI 名称 `agent-preflight`。
- 当前阶段：既有切片、`command-doctor`、`git-doctor` 和 `workspace-scope` 均有本地及远程 Windows CI/包验收证据；路线已收敛到真实 host/Agent 成对证据、单一推荐入口和外部用户验证，当前暂停等待用户采集 host 快照。

## 环境和命令

- 安装/准备：`python -m pip install -e ".[dev]"`
- 构建验收：`python -m build --sdist --wheel`（完整步骤见 `docs/release-check.md`）
- 运行：`python -m win_agent_preflight scan`、`agent-preflight snapshot --label host --output .\\snapshots\\host.json`、`agent-preflight compare baseline.json current.json`、`agent-preflight workspace-probe --target . --allow-write`、`agent-preflight workspace-scope --target <dir> --control <dir> --allow-write`、`agent-preflight agent-doctor --json`、`agent-preflight command-doctor npm --json --pretty`、`agent-preflight git-doctor --target . --json --pretty`、`agent-preflight support-report --json`、`agent-preflight project-doctor --target . --json --pretty`
- 针对性测试：`python -B -m pytest -q -p no:cacheprovider`
- 完整测试：先运行 `python -B -m pytest -q -p no:cacheprovider`，通过后再运行 `python -m ruff check . --no-cache`。
- 构建或检查：`python -m ruff check . --no-cache`；打包验收不得替代测试。
- 清理缓存：本阶段不建设项目缓存；pytest/ruff 生成的缓存可直接删除。

## 项目约定

- 目录职责：`models.py` scan 数据模型；`runner.py` 外部命令边界；`windows.py` Windows 事实采集、launcher lstat 和 PowerShell 检查；`launcher_probe.py` Agent/command doctor 共用的候选启动、状态分类和版本提取；`checks.py` 诊断分类与预计算检查注入；`snapshot.py` EnvironmentSnapshot v1、解析、写出与比较；`compare.py` 差异输出；`workspace_probe.py` 独立 WorkspaceProbeReport v1 与有边界的写入探针；`workspace_scope.py` 独立 WorkspaceScopeReport v1 与双目录编排；`agent_doctor.py` 独立 AgentDoctorReport v1 与最小版本探针；`command_doctor.py` 独立 CommandDoctorReport v1 与单命令诊断；`support_report.py` 独立 SupportReport v2 组合和纯 `next_checks` 推导；`project_doctor.py` 独立 ProjectDoctorReport v1、固定第一层 marker 推导和工具版本探测；`reporting.py` 输出；`cli.py` 参数与编排。
- `snapshot.py` 的写入只使用目标父目录内本次生成的 UUID 临时名和一次 `O_EXCL` 创建；最多重试三次名称碰撞，其他写入错误立即失败。写入完成后按 `--force` 选择替换或硬链接，失败时只清理本次已知临时文件，不扫描目录。
- 代码风格：Python 类型标注、不可变数据模型优先；公共序列化字段使用稳定 snake_case。
- 数据和配置位置：扫描只读取当前环境，不保存配置和凭据。
- 不得修改的上游或生成文件：不触碰工作区其他项目；不创建项目级 `.codex`。

## 修改边界

- 当前允许的结构调整：围绕既有 CLI 稳定边界、只读注册表 PATH 刷新诊断、独立 doctor 报告和 `support-report` v2 的最小模块调整。
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
- `workspace-scope` 必须同时接受现有普通 `--target`、`--control` 目录和显式 `--allow-write`；在任何 probe 写入前完成两个目录的 lstat/reparse/strict-resolve 预验证，然后严格按 target、control 各调用一次既有 `workspace-probe`。普通失败继续第二个目录；子报告归约为 usable、failed（有 FAIL 或 residual）或 unknown，任一 unknown 使正常双返回报告为 `inconclusive` 且 `complete=true`。非预期异常或 Ctrl-C 生成 `inconclusive` partial 且不再继续；`both_usable`、`target_specific_failure`、`control_specific_failure`、`both_failed`、`inconclusive` 为固定状态，退出码分别按成功 0、能力/部分失败 1、输入 2、Ctrl-C 130。
- `workspace-scope` 使用独立 WorkspaceScopeReport v1，顶层 `complete` 仅表示两个 probe 是否都返回；不修改 WorkspaceProbeReport v1，不联网、不枚举目录、不扩大写入边界。
- `agent-doctor` 使用独立 AgentDoctorReport v1，不复用 `CheckResult`，不修改 `scan`/`snapshot`/`workspace-probe` schema 或 checks 语义。
- `agent-doctor` 默认只检查 `codex`、`claude`、`dsh`；重复 `--agent` 固定去重顺序；同一 Agent 可按 PATH 顺序探测多个已解析的 `.exe`/`.cmd`/`.bat`/`.ps1` 普通 launcher，每个候选最多执行一次 `--version`。
- `agent-doctor` 只有 `--version` 退出 0 且 stdout/stderr 至少有一条非空文本时才报告 `usable`；成功结果保存脱敏后的第一条非空版本行（最多 200 字符），报告固定包含 `kind=agent_doctor` 和 `offline=true`。
- `agent-doctor` 禁止 login/doctor/npx/web/网络调用；lstat/Runner 错误只使用结构化 `error_type`/`winerror`/返回码/超时，不回显 stdout/stderr。
- `agent-doctor` 的 `command_not_found` 退出 0；其他非 `usable` 状态退出 1；输入错误退出 2。WindowsApps alias/lstat 异常不得降级为 command_not_found。
- `command-doctor` 是独立 CommandDoctorReport v1：只接受 1–128 字符的 ASCII 安全 basename，显式扩展仅允许 `.exe`、`.cmd`、`.bat`、`.ps1`；只诊断 PATH 外部 launcher，固定使用 `--version`，不接收路径、参数、批处理或网络操作。
- `command-doctor` 无扩展名时按 PATHEXT 相对顺序探测 `.exe`/`.cmd`/`.bat`，末尾追加 `.ps1`，并执行一次只读 PowerShell 裸命令检查；显式 `.ps1` 或无扩展名时发现 `.ps1` 才采集执行策略；所有调用都经有界 Runner，始终采集只读 PATH refresh。成功为 0，能力失败（含明确请求的 `command_not_found`）为 1，输入或非 Windows 平台为 2。
- `command-doctor` 的 `path_refresh` warning/unknown 不使已可用的显式 launcher 失败；候选失败只保留结构化状态、错误类型/WinError/返回码和尝试路径，不保存 stdout/stderr；成功只保留脱敏、最多 200 字符的第一条非空版本行。
- `git-doctor` 使用独立 GitDoctorReport v1；必须显式提供普通目录 `--target`，只运行 PATH 中 Git launcher 的 `--version`、同一 target 上的固定只读 `git -C` 查询，以及仅对 GitHub remote 的 `gh --version`。不运行 `gh auth`、credential fill、push/fetch/pull/ls-remote/ssh、网络或任何写入。
- `git-doctor` 只报告 `local_ready`，固定 `remote_auth_verified=false`；name/email、remote URL、credential helper 原值在函数内立即归约为配置状态、scope、transport、host_class、目标一致性和 userinfo 布尔值，不进入 evidence、异常、Console 或 JSON。GitHub 认证固定为离线 `unknown/not_checked_offline`，不影响 `local_ready`。
- `git-doctor` 检查顺序固定为 `git.launcher`、`git.repository`、`git.commit_identity`、`git.remote.origin`、`git.credential_helper`、`github.cli`、`github.auth`；Git/repository/identity/origin 是 `local_ready` 的必要条件，helper、gh 和离线 auth 不单独阻断本地就绪。成功退出 0，本地能力缺口退出 1，target/platform/timeout 输入错误退出 2。
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

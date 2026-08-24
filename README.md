# Windows Agent Preflight

Windows-first preflight and differential diagnostics for AI coding agents.

`Windows Agent Preflight` 面向使用 Codex、Claude Code、DeepSeek Harness 等工具的开发者，先从确定性的本地事实采集开始，帮助区分：命令未安装、PATH 未刷新、PowerShell 脚本被阻止、命令启动失败，还是 Agent 内部环境与宿主不同。

## 当前状态

公开仓库：[CrAyoN-V587/win-agent-preflight](https://github.com/CrAyoN-V587/win-agent-preflight)。`workspace-scope` 提交 `b981bf1` 已推送，main CI run [`32712146556`](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32712146556) 已全部通过。项目现提供 `scan`、`snapshot`、`compare`、`workspace-probe`、`workspace-scope`、`agent-doctor`、`command-doctor`、`git-doctor`、`support-report` 和 `project-doctor` 命令：

- 发现并列出 Windows PATH 中的候选命令路径；
- 通过统一的超时 Runner 做真实启动和版本采集；
- 采集 PowerShell 执行策略事实；
- 只读采集 HKLM/HKCU 的注册表 PATH，比较当前进程是否已继承机器/用户 PATH；
- 按 Windows 规则展开 PATH 中的 `%NAME%`（最多 8 轮），并在证据中保留机器/用户来源；
- 输出人类可读 Console 或稳定 JSON；
- 将有限的宿主事实和同次 `scan` 保存为 v1 快照；
- 比较两个快照的命令、Shell、PATH/PATHEXT 和检查证据差异；
- 在显式授权下验证当前 Windows 进程对指定目录的创建、写入、读取、重命名、删除和清理能力；
- 在显式授权下按 target/control 顺序各运行一次既有 workspace probe，比较两个已预验证目录的单次能力结果；
- 对 PATH 中已解析的 Codex、Claude Code、DeepSeek Harness 候选启动器执行有界的 `--version` 探测，输出独立 Agent 状态报告；
- 对用户明确指定的一个 PATH launcher 执行严格校验、固定 `--version` 探测和有限的 PowerShell 旁路检查，输出独立 Command Doctor 状态报告；
- 先复用 Agent Doctor 结果，再生成不让 scan 重复探测三个 Agent 的离线支持报告；
- 从已有 scan/Agent Doctor 事实纯推导有限的 `next_checks`，不在建议阶段运行命令或读取环境；
- 根据项目根目录第一层的固定 marker 推导 Python、Node/npm/pnpm 或 CMake 工具需求，并只对实际需要的工具执行有界 `--version` 探测；
- 对显式 Git target 做离线本地就绪诊断：检查 Git launcher、work tree、commit identity、origin 归约、credential helper 和必要的 GitHub CLI launcher，不验证远程认证；
- 对用户目录进行 `%USERPROFILE%` 脱敏，不采集密钥值，不联网，不修改系统配置。

真实 Agent 宿主终端快照仍需在各上下文中分别采集，进度见 [`docs/PROGRESS.md`](docs/PROGRESS.md)。

## 环境

- 设计目标：Windows；
- 安装元数据要求 Python `>=3.12`；当前本机验证环境为 Python 3.12.7，Windows CI 已验证 Python 3.12/3.14；
- 运行时：`typer>=0.16,<1`；
- 开发：`build>=1,<2`、`pytest>=8,<9`、`ruff>=0.12,<1`。

本机若尚未安装，可并行安装 Python 3.14，并使用 Windows Python Launcher（`py -3.12`、`py -3.14`）选择版本；GitHub CLI 已认证，可直接用于本仓库后续远程操作。当前项目不需要 Node.js、Docker 或 WSL。

## 使用

```powershell
python -m pip install -e ".[dev]"
python -m win_agent_preflight scan
python -m win_agent_preflight scan --json
agent-preflight scan --json --pretty
agent-preflight snapshot --label host --output .\snapshots\host.json --pretty
agent-preflight compare .\snapshots\host.json .\snapshots\host.json --json
agent-preflight workspace-probe --target . --allow-write --json --pretty
agent-preflight workspace-scope --target . --control $env:TEMP --allow-write --json --pretty
agent-preflight agent-doctor --json --pretty
agent-preflight agent-doctor --agent codex --agent claude
agent-preflight command-doctor npm --json --pretty
agent-preflight git-doctor --target . --json --pretty
agent-preflight support-report --json --pretty --timeout 2
agent-preflight project-doctor --target . --json --pretty
```

## Host/Agent 成对采集

真实环境差异必须由宿主终端和对应 Agent 的实际命令执行器分别运行一次 `snapshot`，再回到宿主执行 `compare`。单个进程不能代替另一个执行上下文采集，也不要用宿主快照冒充 Agent 快照。

完整的 `%TEMP%` 证据目录、PowerShell 命令、退出码、公开检查和清理边界见 [`docs/context-comparison.md`](docs/context-comparison.md)。

构建源码包和 wheel 的本地验收见 [`docs/release-check.md`](docs/release-check.md)：

```powershell
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m build --sdist --wheel
```

## CI 与包验收

`.github/workflows/ci.yml` 只使用 Windows runner，在推送 `main`、面向 `main` 的 Pull Request 或手动触发时运行。测试矩阵为 Python 3.12/3.14，不启用 Actions 缓存；两个版本运行完整测试、CLI 帮助和 `RUNNER_TEMP` 工作区探针，Ruff 只在 Python 3.12 上运行。测试成功后，Python 3.12 打包 job 会构建恰好一个 sdist 和一个 wheel，并分别安装到干净虚拟环境运行 CLI；非 PR 运行上传保留 7 天的构建制品。首次 run `32691934171` 暴露根帮助的 cp1252 编码问题；包含 `command-doctor` 的 main run `32703174150` 已完成整条流水线和制品上传。

这套 CI 只做项目测试和包安装验收，不自动发布 PyPI、不创建 Release、不生成签名/SBOM，也不做跨平台构建。最新 run `32712146556` 已验证包含 `workspace-scope` 的 Python 3.12/3.14 全量 261 项测试、严格帮助检查、Ruff、sdist/wheel 双安装和制品上传。

全局 `scan` 仍检查固定集合：`python`、`git`、`node`、`npm`、`npm.cmd`、`npm.ps1`、`pnpm`、`codex`、`claude`、`dsh`；需要按项目 marker 缩小到实际工具链时使用 `project-doctor --target <目录>`。

`snapshot` 的 `--label` 和 `--output` 必填；输出目录会创建，已有文件默认不会覆盖，需显式加 `--force`。写出时只在目标父目录创建本次 UUID 临时文件，使用一次 `O_EXCL` 打开并最多对三次名称碰撞重试；权限或其他写入错误立即返回 `SnapshotError`，不扫描目录、不后台重试。完成后 `--force` 使用替换，默认模式使用硬链接后删除临时文件；失败只清理本次已知临时文件。即使嵌入的 `scan` 有 `fail`，快照仍会写出并以 0 退出；写入或输入错误以 2 退出。

`compare` 的退出码为：等价 0、有实质差异 1、输入/版本/类型错误 2。比较会忽略 label、采集时间、summary 和 candidate_count，并对 Windows 路径、PATH/PATHEXT、候选集合和 evidence 做规范化。

`workspace-probe` 必须同时提供现有目录 `--target` 和显式 `--allow-write`。它只在目标目录的直接子目录创建本次随机探针，完成六项固定操作，并在复核 Windows 对象身份后清理本次路径；成功为 0，能力失败或残留为 1，输入拒绝为 2，Ctrl-C 为 130。JSON 使用独立的 `WorkspaceProbeReport v1`，包含 `successful` 和相对 `residual_paths`，不回显探针内容。结论只适用于本次命令、目标目录和当前进程上下文；不遍历目标、不递归清理历史残留。

`workspace-scope` 必须同时提供两个现有普通目录 `--target`、`--control` 和显式 `--allow-write`。命令先完成两个目录的 lstat、重解析点和 strict resolve 预验证，确认无输入问题后再严格按 target、control 顺序各调用一次既有 probe；预验证失败保证零写入。普通能力失败仍继续 control；子报告归约为 usable、failed（有 FAIL 或 residual）或 unknown，任一 unknown 使正常双返回报告成为 `inconclusive` 且 `complete=true`。非预期异常或 Ctrl-C 保留 partial、`complete=false` 并停止后续调用。独立 `WorkspaceScopeReport v1` 的状态固定为 `both_usable`、`target_specific_failure`、`control_specific_failure`、`both_failed` 或 `inconclusive`；成功 0，能力/部分失败 1，输入 2，Ctrl-C 130。它不改变 workspace-probe schema，不遍历目录或扩大写入边界。

`agent-doctor` 默认按 `codex`、`claude`、`dsh` 固定顺序检查，可重复 `--agent` 选择子集并自动去重。它只读取 PATH 中的 `.exe`、`.cmd`、`.bat`、`.ps1` 普通启动器；同一 Agent 若有多个候选，会按 PATH 顺序依次探测，每个候选最多经 Runner 执行一次 `--version`，不会调用 `login`、`doctor`、`npx`、网络或网页命令。只有退出码为 0 且 stdout/stderr 至少有一条非空文本时才是 `usable`；成功结果保存经脱敏、最多 200 字符的第一条非空版本行，空输出归类为 `version_probe_failed`。状态为 `command_not_found`、`resolved_but_not_executable`、`access_denied`、`version_probe_failed` 或 `usable`；全部未安装退出 0，已解析但存在不可用状态退出 1，输入错误退出 2。输出为独立的 `AgentDoctorReport v1`，固定包含 `kind=agent_doctor` 和 `offline=true`；失败只包含结构化错误类型/Win32 错误码/返回码，不回显 stdout/stderr。

`command-doctor` 只接受一个 1–128 字符的 ASCII 安全 basename；首字符必须是字母或数字，其余只能是字母、数字、点、下划线或横线，显式扩展仅允许 `.exe`、`.cmd`、`.bat`、`.ps1`。它只诊断 PATH 中的外部 launcher，固定调用 `--version`，不接收路径、额外参数、批处理、登录、网络或写入操作。无扩展名时按当前 PATHEXT 相对顺序探测 `.exe`/`.cmd`/`.bat`，末尾追加 `.ps1`，并执行一次 PowerShell 裸命令检查；显式 `.ps1` 或无扩展名时发现 `.ps1` 才读取执行策略；所有调用都有 timeout，并始终执行只读 `windows.path_refresh`。报告为独立 `CommandDoctorReport v1`，包含固定五态、`kind=command_doctor` 和 `offline=true`；成功版本只保存脱敏且最多 200 字符的第一条非空行，候选失败不保存 stdout/stderr。成功退出 0，能力失败（包括明确请求但未发现的命令）退出 1，输入或非 Windows 平台退出 2。

`git-doctor` 必须显式提供现有普通目录 `--target`，可以是仓库子目录。它只通过统一 Runner 执行 Git launcher 的 `--version`、`git -C TARGET rev-parse/config/remote` 的固定只读查询，以及在安全分类为 GitHub remote 时的 `gh --version`。检查顺序固定为 `git.launcher`、`git.repository`、`git.commit_identity`、`git.remote.origin`、`git.credential_helper`、`github.cli`、`github.auth`。name/email、remote URL 和 helper 原值只在函数内立即归约，不进入报告；输出只保留 scope/configured、transport、`github.com|other|local|unknown`、fetch/push 是否同目的、userinfo 是否存在、GCM 是否检测到等有限事实。`local_ready` 只要求 Git、repository、identity 和 origin 可读且无 embedded userinfo；helper、gh 和 `github.auth=not_checked_offline` 不单独阻断它，`remote_auth_verified` 永远为 `false`。该命令绝不运行 `gh auth`、credential fill、GCM diagnose、push/fetch/pull/ls-remote/ssh，不联网、不读 token、不写文件；成功退出 0，确认存在本地缺口退出 1，输入/platform/timeout 错误退出 2。

上面的 `warning`/`fail` 语义仅适用于 `scan` 的 `CheckResult`：可选 Agent 未安装会显示为 `warning`，不是 `fail`。`agent-doctor` 使用独立报告，未发现命令明确记录为 `command_not_found`，按约定退出 0；`command-doctor` 面向用户明确请求，未发现命令属于能力失败并退出 1。`scan` 的 `fail` 结果必须携带证据，无法判断时使用 `unknown`。

`support-report` 默认输出 Console，`--json` 输出独立 `SupportReport v2`，不提供 `--output`。它在同一个 Runner、环境映射和超时下先执行 Agent Doctor；Agent Doctor 可依次探测同一 Agent 的多个候选，随后把三个 Agent 的最终结果注入 `scan`，因此 scan 不会再次执行这三个 Agent 的版本命令。顶层保留 v1 的 `scan`/`agent_doctor` 等字段，并增加固定 `next_checks` 数组；内嵌两个报告仍为 v1。`next_checks` 是纯模型推导，只允许 Agent `access_denied`/`version_probe_failed`、PowerShell 裸 `npm` warning、PATH refresh warning/unknown 四类触发；不为命令缺失、不可执行、可用或 Agent scan 注入检查生成建议。报告只保留 `platform`、Python 版本和架构等有限环境事实，标记 `offline=true`、`workspace_probe_run=false`，不运行 workspace-probe、login、doctor、npx、web、网络或写文件。采集完整退出 0，部分采集失败退出 1，输入错误退出 2。Console 会显示 next checks 或 `Next checks: none.`，分享前请检查报告边界提醒。

`project-doctor` 必须显式提供 `--target`，只对目标目录第一层的十个固定 basename 做 `lstat`，不 glob、不递归、不打开 marker 内容，也不以目标目录作为外部工具 cwd。`pyproject.toml`/`requirements.txt` 推导 `python`；`package.json` 推导 `node`，再按 `package-lock.json`/`npm-shrinkwrap.json` 或 `pnpm-lock.yaml` 推导 npm/pnpm；npm 与 pnpm lock 冲突时只推导 node 并将 marker 标为 `unknown`；yarn/bun 或孤立 lockfile 也保持 `unknown`，未列入固定表的项目文件（例如 Makefile、Cargo.toml）直接忽略；`CMakeLists.txt` 推导 `cmake`。marker 的权限异常、symlink、reparse point 或非普通项会累计为脱敏 `unknown`，但会继续处理其他可靠 marker。报告 checks 固定以 `project.markers` 开头，再按 python、node、npm、pnpm、cmake 排列；工具 details 保存固定有序 `required_by`。工具仅执行 `--version`。成功为 0，目标有效但 marker unknown 或必需工具失败为 1，输入/平台错误为 2。

`windows.path_refresh` 只在 Windows 上读取 `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment` 和 `HKCU\Environment` 的 `Path`。读取是只读的，不修改注册表、PATH 或执行策略。缺失键/值视为空的完整事实；读取异常、类型错误或未解析变量会报告为 `unknown`，但如果另一 scope 已证明存在未继承目录，结果仍为 `warning`。旧的 `user_path` 参数仍可用于测试注入。

## 项目文档

- [`PROJECT.md`](PROJECT.md)：目标、范围、成功标准、暂停恢复入口；
- [`docs/design.md`](docs/design.md)：首阶段架构和数据边界；
- [`docs/research.md`](docs/research.md)：需求研究和取舍；
- [`docs/PROGRESS.md`](docs/PROGRESS.md)：按里程碑记录实际验证与下一步；
- [`docs/release-check.md`](docs/release-check.md)：本地构建、双制品和干净虚拟环境验收。

## 开发

```powershell
python -B -m pytest -q -p no:cacheprovider
python -m ruff check . --no-cache
python -m win_agent_preflight scan --json
```

本项目处于本地开发阶段，不提供自动修改执行策略、PATH、注册表或 Agent 配置的命令。

## 已知限制

- 注册表 PATH 采集仅在 Windows 可用；非 Windows 平台明确返回 `unknown`。权限或类型异常不会被当成空 PATH；
- PATH 中无法解析的变量只报告变量名，不展示其值，也不会把部分展开结果当作可比较路径；
- 当前快照命令采集的是执行它的宿主终端；要比较真实 host/agent，用户需要分别在宿主终端和 Agent 实际终端中运行 `snapshot`，再交给 `compare`；
- 当前 Codex 上下文已分别探测项目目录和 `%TEMP%`；尚未完成普通宿主与 Codex 的成对 snapshot/compare，也未采集 Claude/DSH 上下文，单次探针或快照差异都不能代表其他上下文的权限；
- `workspace-probe` 只验证一个指定目录的最小文件生命周期，不代表整个 Agent 或系统权限；未知残留不会自动删除；
- `workspace-scope` 只比较本次命令中两个指定目录的 probe 结果；`both_usable` 不代表目录具有相同 ACL 或跨上下文权限，`inconclusive` 既可能表示两个 probe 正常返回但存在 unknown，也可能表示异常/中断导致的 partial；
- 同一 Agent 上下文对不同项目目录的结果可能不同；普通 ACL 文本不能替代目标目录上的实际探针，也不能单独证明失败来自 Windows ACL 或 Agent 沙箱；
- `workspace-probe` 假设没有其他进程在对象身份复核与紧随其后的路径操作之间恶意替换同名文件或目录；当前不引入 Windows 句柄级删除来消除这一 TOCTOU 窗口；
- WindowsApps 执行别名或 lstat 权限异常会保留为 `access_denied` 证据；这不等于 Agent 已成功可用，仍需在权限合适的宿主上下文中复验。
- `command-doctor` 只说明一次当前 Windows 进程的 PATH、launcher 和 PowerShell 事实；`usable` 不代表账号登录、网络或 Agent 沙箱权限可用。非 Windows 平台不执行 discovery、registry 或 Runner。

## 许可证

[MIT License](LICENSE)

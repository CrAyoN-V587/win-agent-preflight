# Windows Agent Preflight

状态：进行中（第六里程碑 `agent-doctor` 已实现并通过本地验证，待提交；第五里程碑待远程推送和首次 CI）
类型：P3 Agent  
开始日期：2026-08-24  
最近更新：2026-08-24  
时间箱：首个可运行切片 1 周；快照/比较里程碑 1 周；后续总计 3–5 周

## 30 秒上下文

一句话目标：通过 Windows 宿主与 Coding Agent 运行环境的事实采集和差分探针，定位 PATH、Shell、命令启动和项目工具链问题。

当前阶段：第六里程碑——增加独立 `agent-doctor`，检查已解析的本地 Agent 启动器版本探针。

下一步：提交第六里程碑；随后恢复认证并推送，等待 Python 3.12/3.14 CI 首次通过，再由用户分别在宿主终端与 Agent 实际终端生成 host/agent 快照。

最近验证：第六里程碑全量 96 项测试与 Ruff 通过；第五里程碑的 `build 1.5.0` 已生成并验收 sdist/wheel。真实 `agent-doctor --json --pretty` 已执行并报告当前 Codex WindowsApps launcher 为 `access_denied`、其余默认 Agent 为 `command_not_found`；第五里程碑尚未在 GitHub runner 执行，Python 3.14 仍待首次 CI（详见 `docs/PROGRESS.md`）。

## 问题和价值

- 要解决的问题：Windows 上“命令已安装但 Agent 无法使用”的分层诊断问题。
- 目标用户：使用 Codex、Claude Code、DeepSeek Harness 等工具的 Windows 开发者。
- 为什么值得做：把安装检查、实际启动、PowerShell 策略和脱敏证据统一成可复验报告，减少把 PATH、Shell 或沙箱问题误判成项目代码问题。

## 学习与作品集信号

- 重点练习能力：系统边界设计、可注入测试、CLI 后端和 Git 里程碑管理。
- 希望证明的工程能力：稳定数据模型、超时控制、分层诊断、JSON/人类可读输出和 Windows CI 基础。
- 可能的个人增量：覆盖自己遇到的 npm.ps1、pnpm PATH 未刷新和 Codex 环境差异案例。

## 范围

包含：

- Python `>=3.12` 下的 `scan`、`snapshot`、`compare` CLI；
- `python`、`git`、`node`、`npm`、`npm.cmd`、`npm.ps1`、`pnpm`、`codex`、`claude`、`dsh` 命令发现与真实启动；
- PowerShell 执行策略事实采集；
- 只读采集 HKLM/HKCU 注册表 PATH，展开变量并诊断当前进程 PATH 是否继承；
- Console 和稳定 JSON 报告；
- 可注入 Runner、超时、路径脱敏和模型序列化测试。
- EnvironmentSnapshot v1、嵌入 scan、输出目录创建和不覆盖保护；
- Windows 路径、PATH/PATHEXT、候选集合和 evidence 的规范化比较。
- 显式 `--target PATH --allow-write` 的 Windows 工作区写入、读取、重命名、删除和清理能力探针；结论只适用于本次命令、目标目录和当前进程上下文。
- Windows-only CI：Python 3.12/3.14 测试矩阵、3.12 Ruff、`RUNNER_TEMP` workspace-probe 和 Python 3.12 的 sdist/wheel 干净环境安装验收。
- 独立 `agent-doctor`：默认/重复 `--agent` 选择、PATH 中 `.exe`/`.cmd`/`.bat`/`.ps1` launcher 解析、一次 `--version` 探针和脱敏状态报告。

不包含：

- 自动进入 Agent 沙箱或自动生成真实 host/agent 双端快照；
- 联网、自动修复、注册表或执行策略写入/修改；
- 密钥采集、哈希、发布级安全审计；
- GUI、数据库和 LLM 调用。
- 递归删除、历史探针清理、目标目录遍历、ACL/提权审计或自动修复。
- PyPI/Release 自动发布、签名、SBOM、Actions 缓存和跨平台 CI/制品。
- `agent-doctor` 不执行 login、doctor、npx、网页或网络调用，不改变既有 scan/snapshot/workspace schema。

## 成功标准

- [x] 首个切片可通过一条命令执行 `scan`，并同时支持 Console 与 JSON。
- [x] 命令缺失、多候选、超时、PowerShell 脚本阻止和 PATH 未刷新注入场景均有测试。
- [x] 只读采集 HKLM/HKCU PATH，完成非注入的 PATH 未刷新诊断；异常/类型错误保持为不完整事实。
- [x] `scan` 中可选 Agent 未安装不产生 `fail`；所有 `scan` 的 `fail` 都包含证据，`agent-doctor` 使用独立的 `command_not_found`。
- [x] 用户目录统一脱敏为 `%USERPROFILE%`，不输出密钥值或哈希。
- [x] PROJECT.md 与 `docs/PROGRESS.md` 能在暂停后直接恢复。
- [x] probe 只接受显式目标和 `--allow-write`，输入拒绝前不写入；报告独立于 scan/snapshot schema。
- [x] probe 固定六项输出 `successful` 与相对 `residual_paths`，不回显固定内容，清理不递归。
- [x] 创建 Windows-only CI 配置：Python 3.12/3.14 测试、3.12 Ruff、CLI/runner-temp probe 和测试后包验收。
- [x] 配置 sdist/wheel 各一个、干净虚拟环境安装和非 PR 7 天制品上传；不配置自动发布。
- [ ] GitHub 首次 CI 在 Python 3.12/3.14 均通过；3.14 仍待实际 runner 验证。
- [x] `agent-doctor` 全量回归测试、Ruff 和真实 CLI 验收通过；当前真实上下文结果为 Codex `access_denied`、Claude/DSH `command_not_found`。

## 计划

- [x] 1. 建立数据模型、Runner、命令发现和 PowerShell 事实采集边界。
- [x] 2. 实现 `scan` 的 Console/JSON 输出并覆盖首批故障案例。
- [x] 3. 加入 EnvironmentSnapshot v1、`snapshot` 写出和 `compare` 差异退出语义。
- [x] 4. 加入只读注册表 PATH 事实、变量展开和跨 scope 刷新诊断。
- [x] 5. 增加有边界的 `workspace-probe`，验证当前进程上下文的最小文件能力并保留清理证据。
- [x] 6. 增加 Windows CI、包构建验收和本地 release-check 文档。
- [ ] 7. 由用户在宿主终端和 Agent 实际终端分别生成快照，验证真实环境差异。
- [x] 8. 增加独立 `agent-doctor` 版本探针和结构化状态报告；发布仍保持显式、手动边界。

## 技术和环境

- 操作系统：Windows（设计目标）；当前验证环境 Windows，PowerShell，Python 3.12.7。
- 语言与版本：Python `>=3.12`；当前实际验证 Python 3.12.7，Python 3.14 已进入 CI 矩阵但尚未完成首次 runner 验证。
- 主要依赖：运行时 `typer>=0.16,<1`；开发依赖 `build>=1,<2`、`pytest>=8,<9`、`ruff>=0.12,<1`。
- 安装/准备命令：`python -m pip install -e ".[dev]"`
- 本地包验收：`py -3.12 -m build --sdist --wheel`，再按 `docs/release-check.md` 分别安装两个制品。
- 运行命令：`python -m win_agent_preflight scan`、`agent-preflight snapshot --label host --output .\\snapshots\\host.json`、`agent-preflight compare baseline.json current.json`、`agent-preflight workspace-probe --target . --allow-write --json --pretty`、`agent-preflight agent-doctor --json --pretty`
- 针对性验证命令：`python -B -m pytest -q -p no:cacheprovider`
- 完整验证命令：先运行 `python -B -m pytest -q -p no:cacheprovider`，通过后再运行 `python -m ruff check . --no-cache`。

本机建议安装环境（基于当前验证和第五里程碑）：

- 必须：已验证的 Python 3.12.7、本项目开发依赖和 Git。
- 明显提效：并行安装 Python 3.14；本机 Python Launcher 已可用，可用 `py -3.12`/`py -3.14` 选择解释器；GitHub CLI 重新认证后用于远程仓库工作流；PowerShell 7 已可用。
- 暂不需要：Node.js、Docker、WSL、数据库、GUI 工具和额外 Agent CLI；它们不属于当前测试和打包路径。

## 当前状态

已完成：

- 文档、src 布局和项目元数据；
- 稳定数据模型与序列化；
- 可注入超时 Runner；
- Windows PATH 候选发现、真实启动、PowerShell 事实采集和裸 `npm` PowerShell 解析检查；
- `scan` Console/JSON；
- EnvironmentSnapshot v1、`snapshot` 写出和 `compare` Console/JSON；
- 快照输入窄解析、版本/类型错误处理和规范化差异退出码；
- 只读 HKLM/HKCU PATH 事实、大小写不敏感变量展开和刷新状态分类；
- 首批模型、脱敏、缺失、候选、超时和注册表事实测试；
- 独立 `WorkspaceProbeReport v1`、六步文件能力探针、相对残留报告和 CLI 130 中断交接。
- Windows-only CI、Python 3.12/3.14 测试矩阵、3.12 Ruff、runner-temp probe 和 sdist/wheel 包验收配置。
- 独立 `AgentDoctorReport v1`、固定 Agent 选择、四类 launcher 解析、`--version` 最小探针、结构化 Runner 错误和失败输出脱敏实现，并已通过全量验证。

当前阻塞：

- 本机 `gh` 已安装，但保存的 GitHub token 已失效；网页创建页已准备好，远程创建/推送仍需恢复 GitHub 命令行认证。
- Python 3.14 尚未在本机或 GitHub runner 首次验证；需要推送第五里程碑后观察 CI。
- 第五里程碑已完成本地测试、双制品安装验收和独立审阅，并提交为 `c936e3d`，尚待推送；本阶段不自动修改系统配置。
- 第六里程碑尚未提交；当前改动仅涉及委派的 Agent Doctor 源码、测试和同步文档。

下一步：

- 创建/更新 GitHub 公开仓库并推送，观察 Python 3.12/3.14 CI 与包 job；
- 之后用户在宿主终端和 Agent 实际终端分别运行 `snapshot --label host/agent`，再用 `compare` 验证真实差异解释。
- 由主 Agent 审阅当前差异后形成第六里程碑独立提交；随后恢复 GitHub 认证并推送。

未提交修改：

- 第六里程碑的 `agent_doctor.py`、Runner/Windows/reporting/CLI 增量、对应测试和同步文档；尚未提交。

## 关键决策

| 决策 | 原因 | 日期 |
| --- | --- | --- |
| 使用 Python 3.12.7 | 本机没有 3.14，且 Windows CLI 原型不需要追新版本 | 2026-08-24 |
| Snapshot 内嵌已有 scan v1 | 保持 scan JSON 语义唯一，快照只增加有限宿主事实 | 2026-08-24 |
| Compare 忽略 label/time/summary/candidate_count | 这些字段会在同一环境重复运行时自然变化，不应制造实质差异 | 2026-08-24 |
| 外部命令统一经可注入 Runner | 让超时、启动失败和环境差异可以稳定复现 | 2026-08-24 |
| `scan` 中可选 Agent 缺失为 warning | “未安装”不是 Agent 故障，避免误报；`agent-doctor` 使用独立的 `command_not_found` | 2026-08-24 |
| 注册表 PATH 只读且异常不降级为空 | 区分真实空值和权限/类型错误，避免误报 PATH 已刷新 | 2026-08-24 |
| 刷新检查永不 fail | PATH 缺失/不完整是环境事实不足或提示，不是项目命令本身已证实失败 | 2026-08-24 |
| probe 使用独立 v1 schema | 有副作用的最小能力验证不混入只读 scan/snapshot 协议 | 2026-08-24 |
| probe 按对象身份复核本次路径 | 不把能力诊断变成目标目录清理器；身份变化或未知内容保留并用相对路径报告 | 2026-08-24 |
| probe 结论限定为单次上下文 | 一次宿主或 Agent 运行不能替另一个上下文作权限结论 | 2026-08-24 |
| probe 采用非对抗本地并发假设 | 对象身份变化会保守拒绝，但首版不为身份核对与路径删除之间的瞬时替换引入 Win32 句柄级安全实现 | 2026-08-24 |
| CI 只验证 Windows Python 3.12/3.14 和包安装 | 项目目标是 Windows Agent 环境；保持最短反馈路径，不引入跨平台矩阵 | 2026-08-24 |
| 构建验收不等于发布 | 本阶段只需要确认 sdist/wheel 可安装并启动 CLI，发布、签名和 SBOM 留待明确发布阶段 | 2026-08-24 |
| Agent Doctor 使用独立 v1 状态 | Agent 启动器的“未发现”和“已发现但不可用”不应改变 scan/snapshot/workspace 的既有 schema/退出语义 | 2026-08-24 |
| Agent Doctor 只探测已解析 launcher 的 `--version` | 保持本地、低副作用和可复验边界，不触发 login、doctor、npx、网络或网页流程 | 2026-08-24 |
| Agent Doctor 保留 lstat/Runner 结构化错误 | WindowsApps alias 和权限异常不能被静默降级为 command_not_found；失败证据不回显 stdout/stderr | 2026-08-24 |

## 验证证据

| 日期 | 验证内容 | 命令或步骤 | 结果 |
| --- | --- | --- | --- |
| 2026-08-24 | 运行时 | `python --version` | Python 3.12.7 |
| 2026-08-24 | Python Launcher | `py -0p` | 已可用；当前登记 Python 3.12.7，尚无 3.14 |
| 2026-08-24 | 单元、场景和 CLI 端到端测试 | `python -B -m pytest -q -p no:cacheprovider` | 42 passed |
| 2026-08-24 | 静态检查 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | 真实 Windows 注册表和 CLI | `python -B -c "from win_agent_preflight.windows import collect_registry_path_facts; print(collect_registry_path_facts())"`、`python -B -m win_agent_preflight scan --json --pretty --timeout 2` | HKLM/HKCU 读取完整；CLI 退出 0，JSON 可解析，10 pass、3 warning、0 fail、0 unknown；未写入注册表 |
| 2026-08-24 | 完整测试 | `python -B -m pytest -q -p no:cacheprovider` | 75 passed；其中 workspace-probe 27 项，覆盖身份变化、输入零写、步骤失败、未知残留、异常和 CLI 退出码 |
| 2026-08-24 | workspace-probe 静态检查 | `python -m ruff check src tests --no-cache` | All checks passed |
| 2026-08-24 | workspace-probe 真实验收 | `python -B -m win_agent_preflight workspace-probe --target $env:TEMP --allow-write --json --pretty` | 退出 0；六项 pass；`successful=true`；`residual_paths=[]`；无 `.agent-preflight-probe-*` 残留 |
| 2026-08-24 | Codex 项目根诊断 | `python -B -m win_agent_preflight workspace-probe --target . --allow-write --json --pretty` | 退出 1；创建目录 WinError 5；1 pass、1 fail、4 unknown；`residual_paths=[]`，未产生探针残留 |
| 2026-08-24 | 第五里程碑配置检查 | `.github/workflows/ci.yml`、`docs/release-check.md`、`pyproject.toml` 和项目状态文档已更新 | 已写入 Windows-only CI、3.12/3.14 矩阵、包验收和本地恢复说明；尚未在 GitHub runner 执行 |
| 2026-08-24 | 标准打包工具 | `python -m pip install -e ".[dev]"`、`python -m build --version` | 安装成功；build 1.5.0 |
| 2026-08-24 | 本地双制品构建 | `python -m build --sdist --wheel` | 默认隔离构建成功生成 `win_agent_preflight-0.1.0.tar.gz` 与 `win_agent_preflight-0.1.0-py3-none-any.whl`，各 1 个 |
| 2026-08-24 | 干净环境安装 | 在 `.artifacts\\sdist-check` 与 `.artifacts\\wheel-check` 分别安装制品并运行 `python -m win_agent_preflight --help` | 两个环境均退出 0 |
| 2026-08-24 | 第六里程碑专项测试 | `python -B -m pytest tests/test_agent_doctor.py tests/test_cli.py tests/test_runner.py -q -p no:cacheprovider` | Agent Doctor 场景与 CLI/Runner 回归测试通过 |
| 2026-08-24 | 第六里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 96 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | Agent Doctor 真实 CLI | `python -B -m win_agent_preflight agent-doctor --json --pretty` | 退出 1；Codex WindowsApps launcher 为 `access_denied`（WinError 5），Claude/DSH 为 `command_not_found`；未回显 stdout/stderr |

## 暂停检查点

- 当前分支：`main`。
- 最近稳定提交：第五里程碑 `c936e3d`；第六里程碑尚未提交，提交后以新的 `main` HEAD 为恢复点。
- 不能丢失的本地数据：`src/`、`tests/`、`docs/`、`pyproject.toml`、本文件。
- 临时假设：当前只针对 Windows；Linux/macOS 只允许导出 `unknown` 或明确的非 Windows 提示。
- 恢复时第一步：进入项目根目录，运行 `python -B -m pytest -q -p no:cacheprovider`，再查看 `docs/PROGRESS.md` 的最近验证。
- 恢复/验证命令：`python -B -m pytest -q -p no:cacheprovider`；`python -m ruff check . --no-cache`；`py -3.12 -m build --sdist --wheel`；`agent-preflight scan --json`；`agent-preflight agent-doctor --json --pretty`；`agent-preflight workspace-probe --target . --allow-write --json --pretty`；`agent-preflight snapshot --label host --output .\\snapshots\\host.json --pretty`。

## 已知限制和后续

- 当前未执行真实 Agent 沙箱探针，不能据此判断 Codex/Claude/DSH 内部权限。
- 第五里程碑的 Python 3.14 兼容性必须以首次 GitHub CI 结果确认；本地 Python 3.12 双制品构建和安装已通过，不能替代 runner 结果。
- `agent-doctor` 只判断一次当前进程 PATH/launcher 版本探针；`usable` 不等于账号登录、网络或 Agent 沙箱权限可用。
- WindowsApps alias 或 lstat 受限会保守报告为 `access_denied`/结构化不可用状态，不把它当作命令缺失；其他进程或权限变化可能使后续启动结果不同。
- `agent-doctor` 不保存或回显 stdout/stderr 原文；成功结果仅保存经脱敏且最多 200 字符的第一条非空版本行，失败结果不保存版本文本。
- `npm.ps1` 的阻止判断来自实际 Runner 结果和 PowerShell 事实，不会修改执行策略。
- 注册表 PATH 只读采集已实现；非 Windows 平台、读取异常、类型错误或未解析变量返回 `unknown`，但另一 scope 已证明缺失时返回 `warning`。
- 命令发现遇到不可访问的 PATH 候选会跳过并继续扫描；当前不会把该情况细分为“不可访问候选”，只在后续版本增加精确分类。
- `workspace-probe` 不代表整个 Agent 或系统权限；它只验证一次运行上下文对一个现有普通目录的最小文件操作。目标目录中的未知残留不会自动删除，需用户自行处理。
- 对象身份检查可以拒绝复核前发生的同名替换，但路径级删除仍存在身份复核与系统调用之间的 TOCTOU 窗口；首版定位为非对抗本地诊断，不承诺抵御恶意并发替换。

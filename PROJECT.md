# Windows Agent Preflight

状态：进行中（`command-doctor` 提交 `a311f96` 已推送；main CI run `32703174150` 全部通过）
类型：P3 Agent  
开始日期：2026-08-24  
最近更新：2026-08-24  
时间箱：首个可运行切片 1 周；快照/比较里程碑 1 周；后续总计 3–5 周

## 30 秒上下文

一句话目标：通过 Windows 宿主与 Coding Agent 运行环境的事实采集和差分探针，定位 PATH、Shell、命令启动和项目工具链问题。

当前阶段：`command-doctor` 已完成设计、实现、复审、本地回归和远程 CI；双端协议仍等待宿主端手动采集。

下一步：按 `docs/context-comparison.md` 在普通 PowerShell 生成 `host.json`，并运行 host ↔ Codex `compare`。

最近验证：`command-doctor` 定向回归 82 项、全量回归 200 项、Ruff、diff check，以及真实 `command-doctor npm`/`npm.cmd`/`pnpm` 均已通过；三者退出 0，npm 为 11.17.0、pnpm 为 11.22.0，PATH refresh 均为 pass。main CI run [`32703174150`](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32703174150) 的 Python 3.12/3.14 测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建和两个干净环境安装也全部通过（详见 `docs/PROGRESS.md`）。

真实项目复验：`project-doctor` 正确识别 MyMineCraft 的 Node + pnpm 和 MCP Interop Lab 的 Python；两份无标准依赖 marker 的旧 Triton 源码树保守返回 `unknown`。同一 Codex 上下文的 `workspace-probe` 在 Triton 优化项目六步通过，在 MyMineCraft 与 MCP Interop Lab 创建目录时返回 WinError 5；三次均无残留。

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
- 独立 `agent-doctor`：默认/重复 `--agent` 选择、PATH 中多类 launcher 解析、同一 Agent 多候选回退、每个候选最多一次 `--version` 探针和脱敏状态报告。
- 独立 `support-report`：固定 v2 组合 envelope、有限环境事实、Agent Doctor 结果复用、scan 预计算注入、纯 `next_checks` 推导和脱敏采集错误。
- 独立 `project-doctor`：只读取目标第一层十个固定 marker，推导 python/node/npm/pnpm/cmake，按固定顺序执行必需工具的 `--version`，不递归、不读 marker 内容、不使用目标目录 cwd。
- 独立 `command-doctor`：只接受一个 ASCII 安全 basename，按 PATH/PATHEXT 探测 `.exe`/`.cmd`/`.bat` 并追加 `.ps1`，固定执行 `--version`，按需要采集 PowerShell 裸命令/执行策略和只读 PATH refresh；不递归、不联网、不写文件。
- snapshot 写出：目标父目录内最多三次 UUID 临时名的 `O_EXCL` 创建，只有名称碰撞重试；完成后按 force/non-force 语义提交，失败只清理本次已知临时文件。

不包含：

- 自动进入 Agent 沙箱或自动生成真实 host/agent 双端快照；
- 联网、自动修复、注册表或执行策略写入/修改；
- 密钥采集、哈希、发布级安全审计；
- GUI、数据库和 LLM 调用。
- 递归删除、历史探针清理、目标目录遍历、ACL/提权审计或自动修复。
- PyPI/Release 自动发布、签名、SBOM、Actions 缓存和跨平台 CI/制品。
- `agent-doctor` 不执行 login、doctor、npx、网页或网络调用，不改变既有 scan/snapshot/workspace schema。
- `support-report` 不执行 workspace-probe、login、doctor、npx、web、网络或写文件，不提供自动行动建议；仅组合已有本地报告。
- `next_checks` 只由既有 scan/Agent Doctor 模型触发，不解析自由文本、不运行命令、不读取环境；仅覆盖明确的 Agent launcher/version、PowerShell npm 和 PATH refresh 场景。
- CLI 公开帮助使用 ASCII 文字并关闭 Rich Unicode 帮助边框；实际报告输出和中文文档不因此改变。
- `project-doctor` 只接受显式 `--target`；冲突/孤立 lockfile、yarn/bun lockfile 或 marker 检查异常标记为 `unknown`，未列入固定表的项目文件直接忽略；实现已完成独立审阅和远程 CI 验证。
- `command-doctor` 不诊断 PATH 之外的命令，不执行 login/doctor/npx/web 或其他参数；明确请求的缺失命令是能力失败（退出 1），非法输入和非 Windows 平台退出 2；实现已完成独立复审和远程 CI 验证。

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
- [x] 首次 CI run 已实际验证 Python 3.12/3.14 的安装与 pytest，3.12 Ruff 通过；失败根因集中在根 `--help` 的 cp1252 编码。
- [x] 修复后的 Windows CI 在两个矩阵 job 及后续 sdist/wheel package job 全部通过。
- [x] `agent-doctor` 全量回归测试、Ruff 和真实 CLI 验收通过；当前真实上下文结果为 Codex `access_denied`、Claude/DSH `command_not_found`。
- [x] `support-report` 复用共享 Runner/env/timeout；Agent Doctor 每个已发现候选最多执行一次，scan 不重复探测三个 Agent；Console/JSON 和部分失败退出语义有测试。
- [x] `SupportReport v2` 保留 v1 顶层字段并增加不可变 `next_checks`；固定优先级/Agent 顺序、去重、触发边界和 Console/JSON 展示均有测试。
- [x] 根命令和全部子命令 help 在严格 `PYTHONIOENCODING=cp1252:strict` 下可解码并退出 0，且不会执行采集或写文件。
- [x] `project-doctor` 的固定 marker 推导、冲突/孤立、marker 异常累计、输入边界、工具调用/required_by、脱敏、JSON/Console 和退出码已有本地及远程测试。
- [x] snapshot 写入改为有界 `O_EXCL` 临时文件流程；权限/其他写入错误快速退出 2，失败不留下本次临时文件，覆盖碰撞、写入、fsync、替换和 CLI 错误路径测试。
- [x] `command-doctor` 独立 v1、严格输入、候选回退、固定 `--version`、裸 PowerShell/执行策略/Path refresh 边界和 cp1252/退出码测试已通过本地及远程验证。

## 计划

- [x] 1. 建立数据模型、Runner、命令发现和 PowerShell 事实采集边界。
- [x] 2. 实现 `scan` 的 Console/JSON 输出并覆盖首批故障案例。
- [x] 3. 加入 EnvironmentSnapshot v1、`snapshot` 写出和 `compare` 差异退出语义。
- [x] 4. 加入只读注册表 PATH 事实、变量展开和跨 scope 刷新诊断。
- [x] 5. 增加有边界的 `workspace-probe`，验证当前进程上下文的最小文件能力并保留清理证据。
- [x] 6. 增加 Windows CI、包构建验收和本地 release-check 文档。
- [ ] 7. 由用户在宿主终端和 Agent 实际终端分别生成快照，验证真实环境差异。
- [x] 8. 增加独立 `agent-doctor` 版本探针和结构化状态报告；发布仍保持显式、手动边界。
- [x] 9. 增加离线 `support-report` 组合报告；不增加 workspace-probe、网络或自动修复流程。
- [x] 10. 将 `support-report` 升级为 v2，增加纯 `next_checks` 推导；不维护双版本或执行自动建议。
- [x] 11. 将 Typer 公开 help/docstring 调整为 ASCII，关闭 Unicode 帮助格式，并加入 cp1252 子进程 smoke test；不改变报告输出（已推送并通过 CI）。
- [x] 12. 增加独立 `project-doctor` v1：第一层 marker 推导与必需工具 `--version` 探测；设计、实现、复审与远程验证完成。
- [x] 13. 修复 snapshot 在拒绝写入目录中可能高 CPU/长时间重试的问题；实现有界临时文件创建和失败清理，并通过远程 CI。
- [x] 14. 建立 host/Agent 双端采集协议；不新增伪自动化包装，Codex 端已在 `%TEMP%` 生成并验证首份快照。
- [x] 15. 增加独立 `command-doctor` v1：单命令 PATH launcher 诊断和只读 PowerShell 辅助检查；设计、实现、复审与远程验证完成。

## 技术和环境

- 操作系统：Windows（设计目标）；当前验证环境 Windows，PowerShell，Python 3.12.7。
- 语言与版本：Python `>=3.12`；当前本机实际验证 Python 3.12.7；Windows CI 已完整验证 Python 3.12/3.14 矩阵。
- 主要依赖：运行时 `typer>=0.16,<1`；开发依赖 `build>=1,<2`、`pytest>=8,<9`、`ruff>=0.12,<1`。
- 安装/准备命令：`python -m pip install -e ".[dev]"`
- 本地包验收：`py -3.12 -m build --sdist --wheel`，再按 `docs/release-check.md` 分别安装两个制品。
- 运行命令：`python -m win_agent_preflight scan`、`agent-preflight snapshot --label host --output .\\snapshots\\host.json`、`agent-preflight compare baseline.json current.json`、`agent-preflight workspace-probe --target . --allow-write --json --pretty`、`agent-preflight agent-doctor --json --pretty`、`agent-preflight command-doctor npm --json --pretty`、`agent-preflight support-report --json --pretty`、`agent-preflight project-doctor --target . --json --pretty`
- 针对性验证命令：`python -B -m pytest -q -p no:cacheprovider`
- 完整验证命令：先运行 `python -B -m pytest -q -p no:cacheprovider`，通过后再运行 `python -m ruff check . --no-cache`。

本机建议安装环境（基于当前验证和第八里程碑）：

- 必须：已验证的 Python 3.12.7、本项目开发依赖和 Git。
- 明显提效：本机若尚未安装可并行安装 Python 3.14；Python Launcher 已可用，可用 `py -3.12`/`py -3.14` 选择解释器；GitHub CLI 已认证并可用于公开仓库工作流；PowerShell 7 已可用。
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
- Windows-only CI、Python 3.12/3.14 测试矩阵、3.12 Ruff、runner-temp probe 和 sdist/wheel 包验收；包含 `command-doctor` 的 main run `32703174150` 已全部通过。
- 独立 `AgentDoctorReport v1`、固定 Agent 选择、四类 launcher 解析、`--version` 最小探针、结构化 Runner 错误和失败输出脱敏实现，并已通过全量验证。
- 独立 `SupportReport v2`、不可变 `NextCheck` 和纯 `derive_next_checks` 推导；实现、测试和独立复审已完成并提交为 `9f5b951`。
- CLI help cp1252 修复：Typer 公开 help/docstring 使用 ASCII，关闭 Rich Unicode 边框；根命令和全部子命令由严格 cp1252 子进程测试覆盖。
- 独立 `ProjectDoctorReport v1`、固定第一层 marker 推导、首项 marker CheckResult、必需工具 `--version` 探测、目标边界拒绝和独立 JSON/Console 输出已在本地实现。
- snapshot 写入已改为最多三次 UUID 临时名的 `O_EXCL` 创建；只对名称碰撞重试，写入/替换/清理失败路径只处理本次已知临时文件。
- `command-doctor` 已完成独立 v1 报告、严格 basename、PATHEXT 候选、共享 launcher probe、固定 `--version`、裸 PowerShell/执行策略/Path refresh 检查、非 Windows 门禁和 CLI 退出码，并在 `a311f96` 推送后通过远程验证。

当前阻塞：

- 无认证、本地实现、Windows CI 或制品安装阻塞。
- Codex 端快照已生成；宿主端必须由用户在普通 PowerShell 手动运行一次，当前尚未形成成对证据，因此不能断言两者的 PATH、权限或 launcher 差异。

下一步：

- 用户按 `docs/context-comparison.md` 在普通 PowerShell 生成 `host.json`，再用现有 Codex 快照执行首次 `compare`。
- 根据真实差异决定下一诊断切片；Claude/DSH 不可用时明确记录未采集，不用 host 快照替代。

工作区恢复检查：

- 先运行 `git status --short`，以实际输出判断是否存在未提交修改；不要在此维护容易过期的文件清单。
- 最近稳定功能提交为 `a311f96`，远程 `main` 已包含该提交及其 CI 结果记录。

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
| SupportReport v2 只组合本地结果并纯推导 next_checks | 避免分享报告触发写入、联网、登录、重复 Agent 探针或隐式自动修复 | 2026-08-24 |
| CLI help 使用 ASCII 并关闭 Rich Unicode 格式 | 兼容严格 cp1252 的 Windows 旧代码页控制台；不改变实际报告和中文文档 | 2026-08-24 |
| project-doctor 使用固定第一层 marker 和独立 v1 报告 | 在不读项目内容、不递归、不改变既有 scan/support/snapshot schema 的前提下推导本地工具链 | 2026-08-24 |
| snapshot 写入使用有界 `O_EXCL` 临时文件 | Codex 工作区拒绝写入时必须快速返回；只对名称碰撞重试，避免 `NamedTemporaryFile` 的不可控等待，不扫描目录或引入哈希 | 2026-08-24 |
| `command-doctor` 使用独立 v1 和共享 launcher probe | 单命令诊断需要严格输入、固定 `--version` 和有限的 PowerShell 辅助事实，同时不改变既有 scan/agent schema 或引入网络/写入操作 | 2026-08-24 |

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
| 2026-08-24 | 第五里程碑配置检查 | `.github/workflows/ci.yml`、`docs/release-check.md`、`pyproject.toml` 和项目状态文档已更新 | 已写入 Windows-only CI、3.12/3.14 矩阵、包验收和本地恢复说明；旧 HEAD `9259a4d` 已推送，首次 run 的实际失败记录见下方 |
| 2026-08-24 | 标准打包工具 | `python -m pip install -e ".[dev]"`、`python -m build --version` | 安装成功；build 1.5.0 |
| 2026-08-24 | 本地双制品构建 | `python -m build --sdist --wheel` | 默认隔离构建成功生成 `win_agent_preflight-0.1.0.tar.gz` 与 `win_agent_preflight-0.1.0-py3-none-any.whl`，各 1 个 |
| 2026-08-24 | 干净环境安装 | 在 `.artifacts\\sdist-check` 与 `.artifacts\\wheel-check` 分别安装制品并运行 `python -m win_agent_preflight --help` | 两个环境均退出 0 |
| 2026-08-24 | 第六里程碑专项测试 | `python -B -m pytest tests/test_agent_doctor.py tests/test_cli.py tests/test_runner.py -q -p no:cacheprovider` | Agent Doctor 场景与 CLI/Runner 回归测试通过 |
| 2026-08-24 | 第六里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 96 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | Agent Doctor 真实 CLI | `python -B -m win_agent_preflight agent-doctor --json --pretty` | 退出 1；Codex WindowsApps launcher 为 `access_denied`（WinError 5），Claude/DSH 为 `command_not_found`；未回显 stdout/stderr |
| 2026-08-24 | 第七里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 104 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | Support Report 真实 CLI | `python -B -m win_agent_preflight support-report --json --pretty --timeout 1` | 退出 0；JSON 可解析；`offline=true`、`workspace_probe_run=false`；多候选回退由 Agent Doctor 负责，scan 不重复探测三个 Agent（候选调用由测试验证） |
| 2026-08-24 | 第七里程碑制品复验 | 当前进程设 `PYTHONUTF8=1` 后默认隔离构建，并在 `.artifacts\\m7-sdist`、`.artifacts\\m7-wheel` 安装两个制品 | sdist/wheel 均包含 `support_report.py`；两个全新 Python 3.12 环境的 `support-report --help` 均退出 0；首次沙箱构建的真实阻塞为 PyPI 网络权限，不是源码或构建后端错误 |
| 2026-08-24 | 第八里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 113 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | SupportReport v2 真实 CLI | `python -B -m win_agent_preflight support-report --json --pretty --timeout 1` | 退出 0；顶层 `schema_version=2`、`kind=support_report`；内嵌 scan/Agent Doctor 为 v1；`offline=true`、`workspace_probe_run=false`；本次推导 1 项 next check |
| 2026-08-24 | CLI help cp1252 smoke | `python -B -m pytest tests/test_cli_help.py -q -p no:cacheprovider` | 根命令和全部子命令在严格 cp1252 子进程中均退出 0；stdout/stderr 严格解码；临时工作目录无文件 |
| 2026-08-24 | cp1252 修复全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 114 passed；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | 首次 GitHub Windows CI | [run 32691934171](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32691934171) | Python 3.12/3.14 安装与 pytest 通过，3.12 Ruff 通过；两个矩阵 job 均在根 `--help` 的 cp1252 `UnicodeEncodeError` 失败；package job 因 `needs: test` 跳过，远程 sdist/wheel 未验证 |
| 2026-08-24 | cp1252 修复后 GitHub Windows CI | [run 32693383743](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32693383743) | Python 3.12/3.14 测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | project-doctor GitHub Windows CI | [run 32696172691](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32696172691) | Python 3.12/3.14 的 145 项测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | snapshot 修复前一轮 main CI | [run 32696504545](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32696504545) | 当时已推送内容的 Python 3.12/3.14 测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建和干净环境安装全部通过；不包含后续 snapshot 修复 |
| 2026-08-24 | snapshot 修复 GitHub Windows CI | [run 32699112641](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32699112641) | Python 3.12/3.14 的 158 项测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | Codex 上下文快照 | `%TEMP%\win-agent-preflight\context-run-01\codex.json` | snapshot 退出 0；`load_snapshot` 返回 label `codex`、cwd 为本仓库、schema v1；用户目录明文未出现；临时残留 0；自比较退出 0 |
| 2026-08-24 | project-doctor 定向测试 | `python -B -m pytest tests/test_project_doctor.py tests/test_cli.py tests/test_cli_help.py -ra -p no:cacheprovider` | 41 passed；覆盖 marker 组合/锁文件去重/冲突/孤立、ignored marker、marker 异常累计、第一层边界、reparse/symlink/非普通项、无内容读取、工具调用/required_by 和 CLI 退出语义 |
| 2026-08-24 | project-doctor 全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 145 passed；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | project-doctor 真实仓库根 | `python -B -m win_agent_preflight project-doctor --target . --json --pretty --timeout 1` | 退出 0；`project.markers` 与 `project.python` 均 pass；仅推导并探测 python；未写入文件 |
| 2026-08-24 | snapshot/CLI 定向回归 | `python -B -m pytest tests/test_snapshot.py tests/test_cli.py -q -p no:cacheprovider` | 28 passed；覆盖权限首错单次失败、三次名称碰撞、碰撞后成功、竞争输出保留、write/fsync/replace/fdopen 失败清理和 CLI 退出 2 |
| 2026-08-24 | snapshot 静态检查 | `python -m ruff check src/win_agent_preflight/snapshot.py tests/test_snapshot.py tests/test_cli.py --no-cache` | All checks passed |
| 2026-08-24 | snapshot P1/P2 全量回归 | `python -B -m pytest -ra -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 158 passed；父路径为普通文件时 force/non-force 均为 `cannot write snapshot`，link 竞争仍保留 `output already exists`，主失败叠加 cleanup 失败及 non-force 提交后删除失败均保留残留并报告；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | command-doctor 定向回归 | `python -B -m pytest tests/test_command_doctor.py tests/test_windows.py tests/test_cli.py tests/test_cli_help.py -ra -p no:cacheprovider` | 82 passed；覆盖严格输入零 Runner、非 Windows 零 facts/Runner、PATHEXT 顺序和候选回退、五态/WinError/timeout/空输出、PowerShell 裸命令和显式扩展检查、direct + bare 恰好两次同 timeout、JSON/Console/退出码/cp1252 help |
| 2026-08-24 | command-doctor 全量与静态检查 | `python -B -m pytest -ra -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 200 passed；Ruff 和 diff check 通过 |
| 2026-08-24 | command-doctor 真实本机 CLI | `python -B -m win_agent_preflight command-doctor npm/npm.cmd/pnpm --json --pretty --timeout 1` | 三个命令均退出 0；npm `11.17.0`、npm.cmd `11.17.0`、pnpm `11.22.0`；均为 `usable` 且 `windows.path_refresh=pass`，pnpm 报告主安装与 fallback 候选，未写文件 |
| 2026-08-24 | command-doctor GitHub Windows CI | [run 32703174150](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32703174150) | Python 3.12/3.14 的 200 项测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |

## 暂停检查点

- 当前分支：`main`。
- 最近稳定功能提交：`command-doctor` `a311f96`，已推送并通过 Windows CI run `32703174150`。
- 不能丢失的本地数据：`src/`、`tests/`、`docs/`、`pyproject.toml`、本文件。
- 临时假设：当前只针对 Windows；Linux/macOS 只允许导出 `unknown` 或明确的非 Windows 提示。
- 恢复时第一步：进入项目根目录，运行 `python -B -m pytest -q -p no:cacheprovider`，再查看 `docs/PROGRESS.md` 的最近验证。
- 恢复/验证命令：`python -B -m pytest -q -p no:cacheprovider`；`python -m ruff check . --no-cache`；`py -3.12 -m build --sdist --wheel`；`agent-preflight scan --json`；`agent-preflight agent-doctor --json --pretty`；`agent-preflight support-report --json --pretty --timeout 1`；`agent-preflight workspace-probe --target . --allow-write --json --pretty`；`agent-preflight snapshot --label host --output .\\snapshots\\host.json --pretty`；PowerShell 中设置 `$env:PYTHONIOENCODING=\"cp1252:strict\"` 后运行 `python -B -m win_agent_preflight --help`。

## 已知限制和后续

- 当前 Codex 上下文已完成项目目录和 `%TEMP%` 的 workspace probe；尚未完成普通宿主与 Codex 的成对 snapshot/compare，也未采集 Claude/DSH 上下文，因此不能把单次探针外推为其他上下文的权限结论。
- Windows CI `32703174150` 已确认包括 `command-doctor`、snapshot 修复和 project-doctor 在内的 Python 3.12/3.14 矩阵及远程 sdist/wheel 安装验收通过；本机仍只安装并直接验证了 Python 3.12.7。
- `project-doctor` 只检查固定第一层十个 basename，marker 语义不等同于构建系统完整识别；冲突、孤立 lockfile、yarn/bun lockfile 和 marker lstat 异常会保守返回 `unknown`，未列入固定表的文件会忽略。它不读取 marker 内容、不递归、不以 target 作为工具 cwd。
- `agent-doctor` 只描述当前进程这一次 PATH/launcher 探测上下文；同一 Agent 可能依次尝试多个候选；`usable` 不等于账号登录、网络或 Agent 沙箱权限可用。
- WindowsApps alias 或 lstat 受限会保守报告为 `access_denied`/结构化不可用状态，不把它当作命令缺失；其他进程或权限变化可能使后续启动结果不同。
- `agent-doctor` 不保存或回显 stdout/stderr 原文；成功结果仅保存经脱敏且最多 200 字符的第一条非空版本行，失败结果不保存版本文本。
- `support-report` 只表示一次当前进程的本地组合采集；`complete=true` 表示采集流程完成，不表示所有命令或 Agent 健康。
- `support-report` 的 scan 仍包含既有诊断证据和脱敏候选路径；分享前应使用 Console 提醒复核公开边界，不把它当成安全审计或完整环境导出。
- `npm.ps1` 的阻止判断来自实际 Runner 结果和 PowerShell 事实，不会修改执行策略。
- `command-doctor` 只描述单次 Windows PATH/launcher 上下文；无扩展名会追加 `.ps1` 并按需读取执行策略，显式 `.cmd`/`.exe` 不执行裸命令检查；`usable` 不等于登录、网络或 Agent 沙箱可用。
- 注册表 PATH 只读采集已实现；非 Windows 平台、读取异常、类型错误或未解析变量返回 `unknown`，但另一 scope 已证明缺失时返回 `warning`。
- 命令发现遇到不可访问的 PATH 候选会跳过并继续扫描；当前不会把该情况细分为“不可访问候选”，只在后续版本增加精确分类。
- `workspace-probe` 不代表整个 Agent 或系统权限；它只验证一次运行上下文对一个现有普通目录的最小文件操作。目标目录中的未知残留不会自动删除，需用户自行处理。
- 对象身份检查可以拒绝复核前发生的同名替换，但路径级删除仍存在身份复核与系统调用之间的 TOCTOU 窗口；首版定位为非对抗本地诊断，不承诺抵御恶意并发替换。

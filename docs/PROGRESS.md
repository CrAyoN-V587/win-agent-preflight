# 项目进程

## 当前快照

- 当前阶段：第七里程碑 `support-report` 已实现、复审并提交为 `10dc7a6`，待推送与首次 GitHub runner 执行。
- 完成度：首阶段 `scan` 保持稳定；EnvironmentSnapshot v1、`snapshot` 写出、`compare` 规范化差异、窄解析、CLI 退出码、只读注册表 PATH 刷新诊断、独立 `workspace-probe`、Agent Doctor、Support Report 和 CI/构建入口已实现。
- 最近验证：第七里程碑全量 104 项测试和 Ruff 通过；`build 1.5.0` 成功生成 1 个 sdist 与 1 个 wheel，两个制品分别在干净 Python 3.12 虚拟环境安装并启动 CLI；真实 Support Report JSON 退出 0，未运行 workspace-probe。不能据此声称 GitHub CI 或 Python 3.14 已运行。
- 未完成项：第七里程碑提交、Python 3.14 首次 CI、远程推送、用户在真实宿主终端和各 Agent 实际终端分别生成快照。
- 下一步：恢复 GitHub CLI 认证并推送；观察 CI 后再生成 host/agent 快照。

本机建议安装环境（基于当前验证）：

- 必须：Python 3.12.7（已实际验证）和本项目开发依赖；Git 用于后续提交和版本回滚。
- 明显提效：并行安装 Python 3.14；本机 Python Launcher 已可用，可用 `py -3.12`/`py -3.14` 选择解释器；GitHub CLI 重新认证后用于仓库工作流；PowerShell 7 已可用。
- 暂不需要：Node.js、WSL、Docker、数据库、GUI 和额外 Agent CLI；当前测试、探针和打包路径不依赖它们。

## 阶段 0：研究和边界

状态：完成

- 确认展示名 Windows Agent Preflight、包名 `win_agent_preflight`、CLI `agent-preflight`。
- 确认 Python 3.12.7 是本机可用版本；不为本阶段引入 3.14 兼容矩阵。
- 固定范围：`scan`、稳定模型、可注入超时 Runner、Windows 命令和 PowerShell 事实、两种输出。

## 阶段 1：首个可运行切片

状态：完成

- [x] 创建 `PROJECT.md`、项目级 `AGENTS.md`、README 和设计/研究/进程文档。
- [x] 创建 `src` 布局、依赖元数据和忽略规则。
- [x] 实现模型、Runner、命令发现、PowerShell 事实和诊断分类。
- [x] 实现 `scan` Console/JSON 输出。
- [x] 覆盖缺失、多候选、npm.ps1 阻止/npm.cmd 可用、裸 npm PowerShell 解析、PATH 未刷新注入场景、超时、脱敏、模型序列化。
- [x] 记录依赖安装和真实 CLI 的最终输出。

## 阶段 2：EnvironmentSnapshot v1 与 compare

状态：完成

- [x] 新建独立 `EnvironmentSnapshot` v1，内嵌已有 `scan` v1 JSON。
- [x] 采集并脱敏 cwd、sys.executable、platform、PATH、PATHEXT；不采集完整环境变量。
- [x] `snapshot` 支持必填 `--label`/`--output`、目录创建、默认不覆盖、`--force`、`--timeout`、`--pretty`。
- [x] `scan` 即使有 fail 也能写出快照并由 snapshot 以 0 退出；工具错误以 2 退出。
- [x] `compare` 支持 Console/JSON/pretty；等价 0、实质差异 1、输入/版本/类型错误 2。
- [x] 窄解析器支持 v1、忽略未知字段，拒绝顶层/内嵌 scan 更高版本和已知字段错误类型。
- [x] 比较忽略 label、captured_at、summary、candidate_count，并按 CheckResult.id 稳定匹配和规范化集合。
- [ ] 用户仍需在宿主终端和 Agent 实际终端分别生成两端快照；当前只完成同一当前 Agent 环境自比较。

## 阶段 3：只读注册表 PATH 刷新诊断

状态：完成，待远程推送

- [x] `RegistryPathFacts` 使用不可变字段保存 HKLM/HKCU PATH、变量值和 scope 完整性。
- [x] 默认 reader 只读两个环境注册表键；缺失键/值为空且完整，异常/`Path` 非字符串为不完整。
- [x] `user_path` 注入继续优先于用户 registry 值，`scan_environment`/`capture_snapshot` 可透传 reader。
- [x] 机器 PATH 按 HKLM→process、用户 PATH 按 HKCU→HKLM→process 展开 `%NAME%`，最多 8 轮。
- [x] Windows `ntpath` 规范化比较；来源进入 evidence，details 仅保留 `missing_count`。
- [x] 13+ 个 registry/刷新场景测试，刷新检查永不返回 `fail`。

## 阶段 4：一次性 workspace-probe

状态：完成并通过独立审阅，已提交 `623ef26`，待推送

- [x] 新增独立 WorkspaceProbeReport v1，固定六项 workspace.* 检查顺序，并校验 successful 与状态/残留一致。
- [x] CLI 要求 --target PATH --allow-write；输入拒绝 2，能力失败/残留 1，成功 0，Ctrl-C 130。
- [x] 仅 Windows；写入前验证目标普通目录、非重解析点和 strict resolve。
- [x] 只在目标直接子目录创建 .agent-preflight-probe-<uuid>，独占写 before.txt，重命名为 after.txt，再删除并清理空目录。
- [x] 记录探针目录和文件的 Windows 对象身份；身份不可用或复核前变化时保守拒绝，预存或外部出现的 after.txt 不按存在性删除，只作为相对残留报告。
- [x] 注入式 WorkspaceOperations 覆盖各步骤失败、读不一致、未知内容、重解析点、中断和 cleanup unexpected exception；unexpected exception 保留报告后继续抛出。
- [x] 清理不遍历目标、不使用 shutil.rmtree、不处理历史残留；residual_paths 仅相对路径。

本阶段诊断过的环境事实：Codex 线程工作区对项目目录执行写入时曾出现 Windows 拒绝访问，不能把该失败误判成项目代码故障；同一机器对 %TEMP% 运行六项 probe 全部通过且零残留。

结论边界：probe 只说明“该次命令进程对该目标目录的最小文件生命周期能力”，不说明整个 Agent、系统 ACL 或其他上下文权限。它不抵御其他进程在身份复核与紧随其后的路径删除之间刻意替换同名对象；首版不建设 Win32 句柄级安全删除。

## 阶段 5：Windows CI 与包验收

状态：本地验收与独立审阅完成，已提交 `c936e3d`，待首次远程运行

- [x] 新增 Windows-only CI：Python 3.12/3.14 测试矩阵、3.12 Ruff、CLI 帮助和 `RUNNER_TEMP` workspace-probe。
- [x] 测试全部通过后在 Python 3.12 构建一个 sdist 与一个 wheel，并在两个干净虚拟环境分别安装启动。
- [x] 非 PR 运行上传 7 天制品；不启用缓存、自动发布、签名、SBOM 或跨平台矩阵。
- [x] 本机 Python 3.12.7 安装 `build 1.5.0`，完成两个制品的真实构建和安装验收。
- [ ] GitHub 远程首次运行；Python 3.14 兼容性只能在推送后确认。

本阶段本机结论：Git、PowerShell 7、Python 3.12.7、Python Launcher 和项目依赖已足够完成本地研发与打包；并行安装 Python 3.14、重新认证 GitHub CLI，会最直接地推进远程兼容性和仓库工作流。Node.js、Docker、WSL、数据库和 `act` 当前没有必要。

## 阶段 6：Agent Doctor 最小版本探针

状态：实现、全量测试和真实 CLI 完成，已提交 `f7e3503`，待推送

- [x] 新增独立 `AgentDoctorReport v1`，固定 `codex`、`claude`、`dsh` 顺序；重复 `--agent` 去重，未知输入退出 2。
- [x] 对 PATH 中已通过 lstat 解析的 `.exe`、`.cmd`、`.bat`、`.ps1` 普通 launcher 按顺序探测；同一 Agent 可多候选回退，每个候选经 Runner 最多执行一次 `--version`。
- [x] 覆盖 `command_not_found`、`resolved_but_not_executable`、`access_denied`、`version_probe_failed`、`usable` 五种状态；全部未安装退出 0，已解析但不可用退出 1。
- [x] Runner OSError 增加 `error_type`/`winerror`；WindowsApps alias/lstat 异常保留结构化证据，不降级为缺失。
- [x] 失败报告不回显 stdout/stderr，路径按 `%USERPROFILE%` 脱敏；不调用 login、doctor、npx、网页或网络流程。
- [x] `usable` 要求 `--version` 退出 0 且 stdout/stderr 存在非空文本；成功只保存脱敏后的第一条非空版本行（最多 200 字符），空输出为 `version_probe_failed`。
- [x] 报告固定包含 `kind=agent_doctor`、`offline=true`；WinError 1920 纳入 `access_denied` 优先级，并覆盖多个候选的失败分类。
- [x] 全量 pytest（96 项）、Ruff 和真实 `agent-doctor --json` CLI 已完成；该命令只代表一次当前进程 PATH/权限上下文。

## 阶段 7：Support Report 离线组合报告

状态：实现、全量测试和真实 JSON 完成，待提交

- [x] 新增独立 `SupportReport v1`，固定 `kind=support_report`、`generated_at`、有限 environment、collection、scan、agent_doctor 和 errors 字段。
- [x] `support-report` 共享同一个 Runner/env/timeout，先执行 Agent Doctor，再将 `codex`、`claude`、`dsh` 最终结果作为预计算 `CheckResult` 注入 scan；多候选回退由 Agent Doctor 完成，每个已发现候选最多一次，scan 不再重复探测三个 Agent。
- [x] 默认 Console、`--json`/`--pretty` 输出；不提供 `--output`；Console 复用 scan/Agent Doctor renderer 并给出分享前边界提醒。
- [x] 离线只读边界：不运行 workspace-probe、login、doctor、npx、web、网络或写文件；不提供行动建议。
- [x] 健康异常保持退出 0；部分采集异常保留另一部分结果、记录脱敏截断错误并退出 1；输入错误退出 2。
- [x] 全量 pytest（104 项）、Ruff、diff check 和真实 `support-report --json --pretty --timeout 1` 完成。

## 暂停检查点

- 当前阶段：第七里程碑 `support-report` 实现、全量验证和独立复审完成，已提交 `10dc7a6`；GitHub runner 尚未执行。
- 最近验证：104 项测试与 Ruff 通过；build 1.5.0 构建 sdist/wheel 各 1 个；两个干净 Python 3.12 环境安装并启动 CLI 成功；真实 Support Report JSON 已输出 `offline=true`、`workspace_probe_run=false`。多候选回退及 scan 不重复由自动化测试验证，真实命令记录不声称列出候选调用次数。
- 未完成项：GitHub 远程创建/推送、Python 3.14 首次 CI，以及用户在宿主与 Agent 两端手动生成快照。
- 下一步：恢复 GitHub 认证后创建/更新远程并推送。
- 恢复命令：

```powershell
Set-Location <repo-path>
python -m pip install -e ".[dev]"
python -B -m pytest -q -p no:cacheprovider
python -m ruff check . --no-cache
agent-preflight scan --json
agent-preflight agent-doctor --json --pretty
agent-preflight support-report --json --pretty
agent-preflight snapshot --label host --output .\snapshots\host.json --pretty
```

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-08-24 | `python --version` | Python 3.12.7 |
| 2026-08-24 | `py -0p` | Python Launcher 已可用；当前登记 Python 3.12.7，尚无 3.14 |
| 2026-08-24 | `python -B -m pytest -q -p no:cacheprovider` | 42 passed |
| 2026-08-24 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；10 pass、3 warning、0 fail、0 unknown；JSON 可解析 |
| 2026-08-24 | `python -B -m pytest -q -p no:cacheprovider` | 75 passed；包含 27 个 workspace-probe 专项测试，覆盖对象身份变化、外部 after 残留、报告一致性、输入零写、异常和 CLI 退出码 |
| 2026-08-24 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | `python -B -m win_agent_preflight workspace-probe --target $env:TEMP --allow-write --json --pretty` | 退出 0；六项 pass；`successful=true`；`residual_paths=[]`；无 `.agent-preflight-probe-*` 残留 |
| 2026-08-24 | `python -B -m win_agent_preflight workspace-probe --target . --allow-write --json --pretty` | 当前 Codex 沙箱中退出 1；创建目录 WinError 5；1 pass、1 fail、4 unknown；`residual_paths=[]`，无探针残留 |
| 2026-08-24 | `python -m build --version` | build 1.5.0 |
| 2026-08-24 | `python -m build --sdist --wheel` | 默认隔离构建成功生成 1 个 sdist 与 1 个 wheel |
| 2026-08-24 | `.artifacts\\sdist-check`、`.artifacts\\wheel-check` 两个干净环境安装制品并运行 CLI 帮助 | 两个环境均退出 0 |
| 2026-08-24 | `agent-preflight scan --timeout 2` | 退出 0；Console 报告生成成功 |
| 2026-08-24 | `agent-preflight snapshot --label host --output %TEMP%\\win-agent-preflight-m2\\cli-host.json --timeout 1` | 退出 0；输出目录已存在时写出快照 |
| 2026-08-24 | `agent-preflight snapshot --label current --output %TEMP%\\win-agent-preflight-m2\\cli-current.json --timeout 1` | 退出 0；第二快照写出 |
| 2026-08-24 | `agent-preflight compare %TEMP%\\win-agent-preflight-m2\\cli-host.json %TEMP%\\win-agent-preflight-m2\\cli-current.json --json --pretty` | 退出 0；`equivalent: true`，JSON 可解析 |
| 2026-08-24 | `python -m pip install -e ".[dev]" --no-build-isolation` | 安装成功，`agent-preflight.exe` 位于当前 Python Scripts 目录 |
| 2026-08-24 | `python -B -c "from win_agent_preflight.windows import collect_registry_path_facts; ..."` | HKLM/HKCU 读取完整；异常/类型/缺失场景由测试覆盖 |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；10 pass、3 warning、0 fail、0 unknown；JSON 可解析 |
| 2026-08-24 | 第七里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 104 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | Support Report 真实 CLI | `python -B -m win_agent_preflight support-report --json --pretty --timeout 1` | 退出 0；JSON 可解析；`offline=true`、`workspace_probe_run=false`；未运行 workspace-probe |

## 下一里程碑验收

- GitHub Windows runner 的 Python 3.12 与 3.14 测试全部通过；
- 包 job 构建并安装 sdist/wheel，非 PR 运行可下载 7 天制品；
- 用户在宿主与实际 Agent 上分别生成脱敏快照并完成 compare；
- 不增加自动发布、缓存、签名或额外平台基础设施。

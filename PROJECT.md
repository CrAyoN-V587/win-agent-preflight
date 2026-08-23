# Windows Agent Preflight

状态：进行中（首个里程碑完成）  
类型：P3 Agent  
开始日期：2026-08-24  
最近更新：2026-08-24  
时间箱：首个可运行切片 1 周；后续总计 3–5 周

## 30 秒上下文

一句话目标：通过 Windows 宿主与 Coding Agent 运行环境的事实采集和差分探针，定位 PATH、Shell、命令启动和项目工具链问题。

当前阶段：首个可运行切片——命令发现、PowerShell 事实采集、Console/JSON 扫描。

下一步唯一动作：补充宿主/Agent 快照比较与第一个真实项目能力探针。

最近验证：`python -m pytest`、`python -m ruff check . --no-cache` 和 `python -m win_agent_preflight scan --json`（详见 `docs/PROGRESS.md`）。

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

- Python 3.12.7 下的 `scan` CLI；
- `python`、`git`、`node`、`npm`、`npm.cmd`、`npm.ps1`、`pnpm`、`codex`、`claude`、`dsh` 命令发现与真实启动；
- PowerShell 执行策略事实采集；
- Console 和稳定 JSON 报告；
- 可注入 Runner、超时、路径脱敏和模型序列化测试。

不包含：

- snapshot/compare/probe 子命令；
- 联网、自动修复、注册表或执行策略修改；
- 密钥采集、哈希、发布级安全审计；
- GUI、数据库和 LLM 调用。

## 成功标准

- [x] 首个切片可通过一条命令执行 `scan`，并同时支持 Console 与 JSON。
- [x] 命令缺失、多候选、超时、PowerShell 脚本阻止和 PATH 未刷新注入场景均有测试。
- [ ] 从 Windows 用户 PATH 注册表采集真实 PATH，完成非注入的 PATH 未刷新诊断。
- [x] 可选 Agent 未安装不产生 `fail`；所有 `fail` 都包含证据。
- [x] 用户目录统一脱敏为 `%USERPROFILE%`，不输出密钥值或哈希。
- [x] PROJECT.md 与 `docs/PROGRESS.md` 能在暂停后直接恢复。

## 计划

- [x] 1. 建立数据模型、Runner、命令发现和 PowerShell 事实采集边界。
- [x] 2. 实现 `scan` 的 Console/JSON 输出并覆盖首批故障案例。
- [ ] 3. 加入宿主/Agent 快照比较和最小项目能力探针。
- [ ] 4. 增加 Agent 原生 Doctor 适配器、Windows CI 和发布文档。

## 技术和环境

- 操作系统：Windows（设计目标）；当前验证环境 Windows，PowerShell，Python 3.12.7。
- 语言与版本：Python `>=3.12`；当前实际验证 Python 3.12.7，Python 3.14 尚未验证。
- 主要依赖：运行时 `typer>=0.16,<1`；开发依赖 `pytest>=8,<9`、`ruff>=0.12,<1`。
- 安装/准备命令：`python -m pip install -e ".[dev]"`
- 运行命令：`python -m win_agent_preflight scan` 或 `agent-preflight scan`
- 针对性验证命令：`python -m pytest`
- 完整验证命令：`python -m pytest && python -m ruff check .`

本机建议安装环境（基于首版验证）：

- 必须：Python 3.12.7（首版已验证）、本项目开发依赖；Git（项目版本管理需要）。
- 明显提效：Python 3.14（后续兼容性复验）、GitHub CLI（创建 Issue/仓库和认证检查）、PowerShell 7（验证 `pwsh` 场景）。
- 暂不需要：WSL、Docker、数据库、GUI 工具和额外 Agent CLI；它们属于后续对照探针或适配器阶段。

## 当前状态

已完成：

- 文档、src 布局和项目元数据；
- 稳定数据模型与序列化；
- 可注入超时 Runner；
- Windows PATH 候选发现、真实启动、PowerShell 事实采集和裸 `npm` PowerShell 解析检查；
- `scan` Console/JSON；
- 首批模型、脱敏、缺失、候选和超时测试。

当前阻塞：

- 无。

下一步：

- 实现宿主/Agent 快照导出与比较，保留本项目当前 JSON 模型作为输入输出边界。

未提交修改：

- 本首个切片尚未由本 Agent 创建提交；由主 Agent 检查差异后按里程碑提交和推送。

## 关键决策

| 决策 | 原因 | 日期 |
| --- | --- | --- |
| 使用 Python 3.12.7 | 本机没有 3.14，且 Windows CLI 原型不需要追新版本 | 2026-08-24 |
| 首阶段只保留 `scan` | 先形成可运行、可测试的诊断核心，避免提前建设快照系统 | 2026-08-24 |
| 外部命令统一经可注入 Runner | 让超时、启动失败和环境差异可以稳定复现 | 2026-08-24 |
| 可选 Agent 缺失为 warning | “未安装”不是 Agent 故障，避免误报 | 2026-08-24 |

## 验证证据

| 日期 | 验证内容 | 命令或步骤 | 结果 |
| --- | --- | --- | --- |
| 2026-08-24 | 运行时 | `python --version` | Python 3.12.7 |
| 2026-08-24 | 单元、场景和 CLI 端到端测试 | `python -B -m pytest -q -p no:cacheprovider` | 14 passed |
| 2026-08-24 | 静态检查 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | 真实 Windows CLI | `python -B -m win_agent_preflight scan --json --pretty --timeout 2`、`agent-preflight scan --timeout 2` | 均退出 0；JSON 可解析，4 pass、8 warning、0 fail、1 unknown；WindowsApps 不可访问别名已被安全跳过 |

## 暂停检查点

- 当前分支：`main`。
- 最近稳定提交：首个切片正在形成首次提交；提交后以 `main` 的当前 HEAD 为稳定恢复点。
- 不能丢失的本地数据：`src/`、`tests/`、`docs/`、`pyproject.toml`、本文件。
- 临时假设：当前只针对 Windows；Linux/macOS 只允许导出 `unknown` 或明确的非 Windows 提示。
- 恢复时第一步：进入项目根目录，运行 `python -m pytest`，再查看 `docs/PROGRESS.md` 的最近验证。
- 恢复/验证命令：`python -m pytest`；`python -m ruff check . --no-cache`；`agent-preflight scan --json`。

## 已知限制和后续

- 当前未执行真实 Agent 沙箱探针，不能据此判断 Codex/Claude/DSH 内部权限。
- `npm.ps1` 的阻止判断来自实际 Runner 结果和 PowerShell 事实，不会修改执行策略。
- PATH 未刷新目前只完成注入场景比较；尚未读取 Windows 用户 PATH 注册表，因此真实用户 PATH 采集留待下一阶段。
- 命令发现遇到不可访问的 PATH 候选会跳过并继续扫描；当前不会把该情况细分为“不可访问候选”，只在后续版本增加精确分类。

# Windows Agent Preflight

状态：进行中（第三里程碑完成）
类型：P3 Agent  
开始日期：2026-08-24  
最近更新：2026-08-24  
时间箱：首个可运行切片 1 周；快照/比较里程碑 1 周；后续总计 3–5 周

## 30 秒上下文

一句话目标：通过 Windows 宿主与 Coding Agent 运行环境的事实采集和差分探针，定位 PATH、Shell、命令启动和项目工具链问题。

当前阶段：第三里程碑——在稳定 `scan` 和快照比较上增加只读注册表 PATH 事实与刷新诊断。

下一步唯一动作：创建 GitHub 公开仓库并推送三个本地里程碑；随后由用户分别在宿主终端与 Agent 实际终端生成 host/agent 快照。

最近验证：`python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、同一当前 Agent 环境快照自比较（详见 `docs/PROGRESS.md`）。

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

不包含：

- 自动进入 Agent 沙箱或自动生成真实 host/agent 双端快照；
- 联网、自动修复、注册表或执行策略写入/修改；
- 密钥采集、哈希、发布级安全审计；
- GUI、数据库和 LLM 调用。

## 成功标准

- [x] 首个切片可通过一条命令执行 `scan`，并同时支持 Console 与 JSON。
- [x] 命令缺失、多候选、超时、PowerShell 脚本阻止和 PATH 未刷新注入场景均有测试。
- [x] 只读采集 HKLM/HKCU PATH，完成非注入的 PATH 未刷新诊断；异常/类型错误保持为不完整事实。
- [x] 可选 Agent 未安装不产生 `fail`；所有 `fail` 都包含证据。
- [x] 用户目录统一脱敏为 `%USERPROFILE%`，不输出密钥值或哈希。
- [x] PROJECT.md 与 `docs/PROGRESS.md` 能在暂停后直接恢复。

## 计划

- [x] 1. 建立数据模型、Runner、命令发现和 PowerShell 事实采集边界。
- [x] 2. 实现 `scan` 的 Console/JSON 输出并覆盖首批故障案例。
- [x] 3. 加入 EnvironmentSnapshot v1、`snapshot` 写出和 `compare` 差异退出语义。
- [x] 4. 加入只读注册表 PATH 事实、变量展开和跨 scope 刷新诊断。
- [ ] 5. 由用户在宿主终端和 Agent 实际终端分别生成快照，验证真实环境差异。
- [ ] 6. 增加 Agent 原生 Doctor 适配器、Windows CI 和发布文档。

## 技术和环境

- 操作系统：Windows（设计目标）；当前验证环境 Windows，PowerShell，Python 3.12.7。
- 语言与版本：Python `>=3.12`；当前实际验证 Python 3.12.7，Python 3.14 尚未验证。
- 主要依赖：运行时 `typer>=0.16,<1`；开发依赖 `pytest>=8,<9`、`ruff>=0.12,<1`。
- 安装/准备命令：`python -m pip install -e ".[dev]"`
- 运行命令：`python -m win_agent_preflight scan`、`agent-preflight snapshot --label host --output .\\snapshots\\host.json`、`agent-preflight compare baseline.json current.json`
- 针对性验证命令：`python -m pytest`
- 完整验证命令：先运行 `python -m pytest`，通过后再运行 `python -m ruff check .`。

本机建议安装环境（基于首版验证）：

- 必须：Python 3.12.7（首版已验证）、本项目开发依赖；Git（项目版本管理需要）。
- 明显提效：保留 3.12.7 主环境并可并行安装 Python 3.14（只做后续兼容性复验）、GitHub CLI（创建 Issue/仓库和认证检查）、PowerShell 7（验证 `pwsh` 场景）。
- 暂不需要：WSL、Docker、数据库、GUI 工具和额外 Agent CLI；它们属于后续对照探针或适配器阶段。

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
- 首批模型、脱敏、缺失、候选、超时和注册表事实测试。

当前阻塞：

- 本机 `gh` 已安装，但保存的 GitHub token 已失效；网页创建页已准备好，远程创建/推送仍需恢复 GitHub 命令行认证。

下一步：

- 创建 GitHub 公开仓库并推送当前 `main`；之后用户在宿主终端和 Agent 实际终端分别运行 `snapshot --label host/agent`，再用 `compare` 验证真实差异解释。

未提交修改：

- 第三里程碑将由当前里程碑提交保存；提交后应保持工作区干净。

## 关键决策

| 决策 | 原因 | 日期 |
| --- | --- | --- |
| 使用 Python 3.12.7 | 本机没有 3.14，且 Windows CLI 原型不需要追新版本 | 2026-08-24 |
| Snapshot 内嵌已有 scan v1 | 保持 scan JSON 语义唯一，快照只增加有限宿主事实 | 2026-08-24 |
| Compare 忽略 label/time/summary/candidate_count | 这些字段会在同一环境重复运行时自然变化，不应制造实质差异 | 2026-08-24 |
| 外部命令统一经可注入 Runner | 让超时、启动失败和环境差异可以稳定复现 | 2026-08-24 |
| 可选 Agent 缺失为 warning | “未安装”不是 Agent 故障，避免误报 | 2026-08-24 |
| 注册表 PATH 只读且异常不降级为空 | 区分真实空值和权限/类型错误，避免误报 PATH 已刷新 | 2026-08-24 |
| 刷新检查永不 fail | PATH 缺失/不完整是环境事实不足或提示，不是项目命令本身已证实失败 | 2026-08-24 |

## 验证证据

| 日期 | 验证内容 | 命令或步骤 | 结果 |
| --- | --- | --- | --- |
| 2026-08-24 | 运行时 | `python --version` | Python 3.12.7 |
| 2026-08-24 | 单元、场景和 CLI 端到端测试 | `python -B -m pytest -q -p no:cacheprovider` | 42 passed |
| 2026-08-24 | 静态检查 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | 真实 Windows 注册表和 CLI | `python -B -c "from win_agent_preflight.windows import collect_registry_path_facts; print(collect_registry_path_facts())"`、`python -B -m win_agent_preflight scan --json --pretty --timeout 2` | HKLM/HKCU 读取完整；CLI 退出 0，JSON 可解析，10 pass、3 warning、0 fail、0 unknown；未写入注册表 |

## 暂停检查点

- 当前分支：`main`。
- 最近稳定提交：第三里程碑提交后的 `main` 当前 HEAD；上一稳定提交为 `b3f5d23`。
- 不能丢失的本地数据：`src/`、`tests/`、`docs/`、`pyproject.toml`、本文件。
- 临时假设：当前只针对 Windows；Linux/macOS 只允许导出 `unknown` 或明确的非 Windows 提示。
- 恢复时第一步：进入项目根目录，运行 `python -B -m pytest -q -p no:cacheprovider`，再查看 `docs/PROGRESS.md` 的最近验证。
- 恢复/验证命令：`python -B -m pytest -q -p no:cacheprovider`；`python -m ruff check . --no-cache`；`agent-preflight scan --json`；`agent-preflight snapshot --label host --output .\\snapshots\\host.json --pretty`。

## 已知限制和后续

- 当前未执行真实 Agent 沙箱探针，不能据此判断 Codex/Claude/DSH 内部权限。
- `npm.ps1` 的阻止判断来自实际 Runner 结果和 PowerShell 事实，不会修改执行策略。
- 注册表 PATH 只读采集已实现；非 Windows 平台、读取异常、类型错误或未解析变量返回 `unknown`，但另一 scope 已证明缺失时返回 `warning`。
- 命令发现遇到不可访问的 PATH 候选会跳过并继续扫描；当前不会把该情况细分为“不可访问候选”，只在后续版本增加精确分类。

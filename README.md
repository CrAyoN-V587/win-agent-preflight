# Windows Agent Preflight

[![Windows CI](https://github.com/CrAyoN-V587/win-agent-preflight/actions/workflows/ci.yml/badge.svg)](https://github.com/CrAyoN-V587/win-agent-preflight/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Windows execution-context differential preflight for AI coding agents.

`Windows Agent Preflight` 是一个面向 Windows Coding Agent 的离线诊断 CLI。它帮助回答一个常见但难以定位的问题：

> 为什么命令在普通 PowerShell 中可以运行，进入 Codex、Claude Code 或其他 Agent 的执行环境后却找不到、启动失败或表现不同？

工具通过采集确定性的本地事实，区分命令未安装、PATH 未刷新、PowerShell launcher/Execution Policy、候选命令差异和 Agent 注入环境等情况。它不会登录账号、自动修复系统或修改 PATH、注册表、ACL 和 Agent 配置。

## 参与试运行

项目正在招募 **3–5 名使用 Windows + Coding Agent 的开发者**参与首轮试运行。

- 预计耗时：10–20 分钟；
- 支持场景：Windows 10/11，Codex Desktop/CLI、Claude Code 或其他能够执行本机 PowerShell 的 Agent；
- 不需要：管理员权限、GitHub 登录、API Key、Docker、WSL 或真实业务项目；
- 默认回传：匿名环境类别、三个退出码、差异数量和使用体验；
- 默认不回传：原始快照、完整 PATH、绝对路径、账号、密钥或完整 compare 输出。

请直接转发或遵循：

**[外部试运行手册：操作、回传信息与风险边界](docs/external-pilot-guide.md)**

如果愿意参与，请按手册第 8 节的模板返回结果。遇到登录、提权、要求关闭安全策略、输出疑似凭据或目标路径不一致时应立即停止，不需要为了完成测试自行修改环境。

## 项目能做什么

- 枚举 Windows PATH 中的命令候选，并通过有界 `--version` 验证实际 launcher；
- 读取 PowerShell 解析、Execution Policy 和 HKLM/HKCU 注册表 PATH 事实；
- 判断当前进程是否尚未继承已经配置的 PATH 项；
- 生成 Console 或稳定 JSON 报告，并将用户目录脱敏为 `%USERPROFILE%`；
- 分别采集 Host 与 Agent 快照，比较 PATH、PATHEXT、Shell、命令候选和检查结果；
- 有边界地探测指定工作区的创建、读写、重命名、删除与清理能力；
- 提供 Agent、单命令、Git、本地项目工具链和组合支持报告。

项目当前保持 Windows-only、offline-first 和 evidence-first。它不是通用 Agent 管理平台、安全扫描器或自动修复工具。

## 环境要求

- Windows 10 或 Windows 11；
- Python `>=3.12`；
- 运行时依赖：`typer>=0.16,<1`。

Windows CI 覆盖 Python 3.12 和 3.14。Node.js、Docker、WSL、数据库和其他 Agent CLI 都不是运行本工具的必需依赖；它们只会在对应诊断场景中作为可选目标出现。

## 快速开始

当前版本从源码安装。建议使用项目内虚拟环境，避免改变全局 Python：

```powershell
git clone https://github.com/CrAyoN-V587/win-agent-preflight.git
Set-Location .\win-agent-preflight

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\agent-preflight.exe scan
```

准备阶段的 Git/pip 可能联网；安装完成后的 scan、doctor、snapshot 和 compare 诊断不联网。

生成一份组合支持报告：

```powershell
.\.venv\Scripts\agent-preflight.exe support-report --json --pretty --timeout 5
```

诊断一个明确的 PATH 命令：

```powershell
.\.venv\Scripts\agent-preflight.exe command-doctor npm --json --pretty --timeout 5
```

输出可能包含软件版本和非用户目录。分享前请人工检查；原始 JSON 不应默认发布到 Issue、群聊或论坛。

## Host/Agent 差分

真实差分必须由普通宿主终端和 Agent 自己的命令执行器分别运行 `snapshot`。一个进程连续生成两份文件，不能代表两个执行上下文。

```text
普通 PowerShell ── snapshot(host)  ─┐
                                    ├─ compare ── 差异报告
Agent 命令执行器 ─ snapshot(agent) ─┘
```

两端必须使用同一台机器、同一项目 cwd、同一代码版本、同一轮名称和相同 timeout。短 timeout、不同 cwd 或跨日期快照都可能制造无法归因的差异。

- 完整采集协议：[Host 与 Agent 上下文成对采集](docs/context-comparison.md)
- 已验证案例：[首组 Host ↔ Codex 执行上下文案例](docs/host-codex-case-study.md)

首组案例验证了 Codex 会注入自己的 runtime PATH、PowerShell、fallback 工具和内部 CLI，同时 Git、Python、npm、pnpm 的最终选择仍可能与 Host 一致。原始快照没有提交到仓库。

## 命令概览

| 命令 | 用途 | 是否写入 |
| --- | --- | --- |
| `scan` | 固定工具、PowerShell 与 PATH 事实总览 | 否 |
| `support-report` | 组合 scan 与 Agent launcher 结果，给出有限 next checks | 否 |
| `agent-doctor` | 检查 Codex、Claude Code、DSH launcher | 否 |
| `command-doctor NAME` | 诊断一个明确的 PATH launcher | 否 |
| `git-doctor --target PATH` | 检查本地 Git readiness，不验证远程认证 | 否 |
| `project-doctor --target PATH` | 根据第一层 marker 推导并验证项目工具链 | 否 |
| `snapshot` | 把当前执行上下文写成 JSON 快照 | 写指定输出文件 |
| `compare` | 比较两份快照 | 否 |
| `workspace-probe --allow-write` | 探测一个目录的最小文件生命周期 | 是，限一次性随机探针并尝试清理 |
| `workspace-scope --allow-write` | 比较 target/control 两个目录的能力 | 是，分别运行一次既有探针 |

所有外部命令都有 timeout。`workspace-probe` 和 `workspace-scope` 必须显式提供 `--allow-write`；不要在重要、敏感或不允许临时写入的目录中运行。

## 输出与退出码

- 通用诊断通常以 `0` 表示采集成功；确认存在能力缺口时根据具体命令返回 `1`；输入或平台错误返回 `2`。
- `compare`：等价为 `0`，发现有效差异为 `1`，输入/格式错误为 `2`。
- `workspace-probe`/`workspace-scope`：成功为 `0`，能力失败或部分结果为 `1`，输入错误为 `2`，Ctrl-C 为 `130`。

请注意：`compare` 返回 `1` 表示成功发现差异，不是程序崩溃。不同命令的完整退出语义见 `--help` 和[设计说明](docs/design.md)。

## 隐私与安全边界

工具不采集密钥值，也不会执行登录、push/fetch、`npx`、网页、自动修复或提权流程。但报告仍可能暴露：

- 已安装的软件及版本；
- 非用户目录的绝对路径；
- 项目名、组织目录或 Agent runtime 布局；
- PATH 候选与 Execution Policy 事实。

因此：

1. 原始 snapshot/JSON 和完整 compare 输出默认只保留在本机；
2. 对外反馈优先使用[试运行手册](docs/external-pilot-guide.md)中的最小模板；
3. 只有经过人工归约和明确同意后，才公开案例摘要；
4. 不要在真实业务仓库、客户目录或包含秘密路径的工作区做首次试运行。

## 当前成熟度与路线

当前版本为早期可运行原型：

- 已有 Windows Python 3.12/3.14 CI、261 项自动化测试和 sdist/wheel 安装验收；
- 已完成首组严格 Host ↔ Codex 差分案例；
- 正在收集 3–5 名外部参与者对“一次完成率”和“结果可解释性”的反馈。

在外部反馈形成重复证据前，项目不会继续堆叠新探针。若参与者持续混用 cwd、轮次或 timeout，将优先评估紧凑 Agent 输出或成对证据预验证；Shell/runtime、WindowsApps launcher chain 和可选网络对照只有在真实需求重复出现后才会进入设计。

## 文档

- [外部试运行手册](docs/external-pilot-guide.md)：适合直接转发给参与者；
- [首组 Host ↔ Codex 案例](docs/host-codex-case-study.md)：真实差异和路线影响；
- [成对采集协议](docs/context-comparison.md)：详细命令、退出码与证据边界；
- [需求与竞品研究](docs/research.md)：需求证据、相似项目和产品边界；
- [设计说明](docs/design.md)：模块、schema 和命令语义；
- [项目状态](PROJECT.md)与[进度记录](docs/PROGRESS.md)：维护与恢复入口；
- [构建验收](docs/release-check.md)：开发者的本地 sdist/wheel 检查。

## 开发

```powershell
python -m pip install -e ".[dev]"
python -B -m pytest -q -p no:cacheprovider
python -m ruff check . --no-cache
```

贡献前请阅读 [`AGENTS.md`](AGENTS.md)。Bug 报告请提供最小复现和脱敏后的错误摘要，不要附加原始快照、完整 PATH、凭据或业务文件。

## 许可证

[MIT License](LICENSE)

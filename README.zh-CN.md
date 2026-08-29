# Windows Agent Preflight

[![Windows CI](https://github.com/CrAyoN-V587/win-agent-preflight/actions/workflows/ci.yml/badge.svg)](https://github.com/CrAyoN-V587/win-agent-preflight/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

英文入口：[README.md](README.md)

**面向 Windows 的 AI Coding Agent 执行上下文差异诊断工具。**

## 为什么需要它

在 Windows 上，一条命令可能在普通 PowerShell 中可以运行，进入 Codex、Claude Code 或其他 Coding Agent 后却找不到、启动失败或表现不同。原因可能是继承的 `PATH` 没有刷新、PowerShell launcher 不同、命中了 WindowsApps 打包程序、工作区写入能力不同，或 `PATHEXT` 选择了另一条候选路径。

Windows Agent Preflight 将这些层次归约为可检查的本地报告，帮助判断问题属于命令未安装、进程环境差异、launcher 解析差异还是工作区能力差异。

## 能做什么

- 枚举 Windows `PATH` 中的命令候选，并通过有界、只读的 `--version` 探针验证 launcher；
- 报告 PowerShell 解析、Execution Policy、注册表 `PATH` 和当前进程 `PATH` 刷新事实；
- 诊断 Codex、Claude Code、DSH、指定命令、Git readiness 和项目第一层工具链标记；
- 由宿主终端或 Agent 执行器分别生成 JSON 快照，再比较两种执行上下文；
- 在明确指定的目录中，有边界地探测最小文件生命周期；
- 将当前用户目录脱敏为 `%USERPROFILE%`，并保持稳定的报告 schema。

项目保持 Windows-only、offline-first、evidence-first。它不是 Agent 管理平台、安全扫描器、配置同步器或自动修复工具。

## v0.1.0 快速开始

环境要求：Windows 10/11 和 Python `>=3.12`。运行时依赖为 `typer`；Node.js、Docker、WSL、数据库和其他 Agent CLI 不是安装本工具的必需条件，只会作为对应诊断场景中的可选目标出现。

```powershell
git clone https://github.com/CrAyoN-V587/win-agent-preflight.git
Set-Location .\win-agent-preflight

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\agent-preflight.exe scan
```

生成组合支持报告：

```powershell
.\.venv\Scripts\agent-preflight.exe support-report --json --pretty --timeout 5
```

诊断一个明确的 PATH 命令：

```powershell
.\.venv\Scripts\agent-preflight.exe command-doctor npm --json --pretty --timeout 5
```

安装阶段的 `pip` 可能需要联网。安装完成后，`scan`、各类 doctor 命令、`snapshot` 和 `compare` 不会登录、访问 Web 服务、修改系统或执行包管理器安装流程。

## Host 与 Agent 差分

真实差分需要由普通宿主 PowerShell 和 Agent 自己的命令执行器分别触发 `snapshot`。同一个进程连续生成两份快照，只能得到两个相同上下文的报告，不能证明 Host 与 Agent 存在或不存在差异。

```text
普通 PowerShell ── snapshot(host)  ─┐
                                    ├─ compare ── 差异报告
Agent 执行器   ── snapshot(agent) ─┘
```

两端应使用同一台机器、同一项目目录、同一代码版本、同一轮次名称和相同 timeout。可参考[首组 Host ↔ Codex 案例](docs/host-codex-case-study.md)和[成对采集协议](docs/context-comparison.md)。

## 命令概览

| 命令 | 用途 | 是否写入文件 |
| --- | --- | --- |
| `scan` | 固定命令、PowerShell 和 `PATH` 事实总览 | 否 |
| `support-report` | 组合本地 scan 与 Agent launcher 结果 | 否 |
| `agent-doctor` | 探测 Codex、Claude Code 和 DSH launcher | 否 |
| `command-doctor NAME` | 诊断一个 `PATH` launcher | 否 |
| `git-doctor --target PATH` | 检查本地 Git readiness，不验证远程认证 | 否 |
| `project-doctor --target PATH` | 根据第一层 marker 推导受支持的项目工具链 | 否 |
| `snapshot` | 将当前执行上下文写成 JSON 快照 | 只写指定输出 |
| `compare` | 比较两份快照 | 否 |
| `workspace-probe --allow-write` | 探测一个目录的最小文件生命周期 | 是，临时探针 |
| `workspace-scope --allow-write` | 比较 target/control 两个目录的能力 | 是，分别运行临时探针 |

所有外部命令都有 timeout。`workspace-probe` 和 `workspace-scope` 必须显式提供 `--allow-write`；不要在重要、敏感或不允许临时写入的目录中运行。

## 边界与隐私

常规诊断路径是离线、只读且不需要登录。项目不会：

- 执行 `login`、`doctor`、`npx`、Web、push/fetch 或其他网络流程；
- 修改 `PATH`、注册表、Execution Policy、ACL、Agent 配置或项目代码；
- 自动修复、提权、收集密钥或上传报告；
- 将本地 launcher `usable` 解释为账号认证、网络访问或完整 Agent 沙箱能力可用。

报告仍可能暴露软件名称、版本、非用户目录、项目名和 Agent runtime 布局。分享前应人工替换剩余私有路径，并在不需要时删除原始快照。外部反馈请使用[外部试运行手册](docs/external-pilot-guide.md)中的最小模板，不要附加原始 JSON、完整 `PATH`、凭据或业务文件。

## 状态与下一阶段边界

仓库当前已按 `0.1.0` 发布边界整理，本地包验收已完成。发布顺序是：维护者先确定日期并定稿 0.1.0 Changelog，提交并推送最终发布材料，等待该提交的 Windows CI 成功，再在同一提交创建 `v0.1.0` tag/Release 并上传已验制品。完成后功能开发将暂缓；维护、文档修正和反馈响应仍然保留。

只有出现以下证据之一，才重新评估功能开发：外部 Issue、PR 或真实报告；至少两个独立环境重复出现同类缺口；或稳定存在、且当前工具无法区分的上游问题。若完成发布并进行至少两次相关分享，14 天后仍有访问或克隆但没有 Star，只允许先做一次定位或演示调整，再决定是否恢复实现工作。GitHub Star 是采用信号，不等于项目质量的直接排名。

外部试运行手册仍可供愿意提供脱敏报告的参与者使用；外部测试不是完成 v0.1.0 发布顺序或执行暂缓决定的前置条件。

## 文档

- [英文入口](README.md)
- [首组 Host ↔ Codex 案例](docs/host-codex-case-study.md)
- [Host 与 Agent 成对采集协议](docs/context-comparison.md)
- [需求与竞品研究](docs/research.md)
- [设计说明](docs/design.md)
- [外部试运行手册](docs/external-pilot-guide.md)
- [项目状态](PROJECT.md)与[进度记录](docs/PROGRESS.md)
- [本地包验收](docs/release-check.md)
- [变更记录](CHANGELOG.md)

## 开发

```powershell
python -m pip install -e ".[dev]"
python -B -m pytest -q -p no:cacheprovider
python -m ruff check . --no-cache
```

贡献时请保持 visitor、user、participant、host operator、maintainer 和 Agent 的身份边界清晰，并提供最小、脱敏的复现信息。修改前请阅读 [AGENTS.md](AGENTS.md)。

## 许可证

[MIT License](LICENSE)

# 项目进程

## 当前快照

- 当前阶段：首个可运行切片已完成，准备首个 Git/GitHub 里程碑。
- 完成度：文档、数据模型、Runner、Windows 命令扫描、PowerShell 事实采集、Console/JSON 输出和测试已实现。
- 最近验证：14 个测试通过，Ruff 通过，真实 Console/JSON 扫描通过；裸 `npm` PowerShell 检查已独立于 npm.cmd/npm.ps1 候选；WindowsApps 执行别名在文件状态查询时会被安全跳过。
- 未完成项：宿主/Agent snapshot compare、真实项目 probe、Agent 原生 Doctor 适配器、Windows CI。
- 下一步唯一动作：提交并推送首个稳定里程碑，然后设计 `snapshot`/`compare` 的最小输入输出模型。

本机建议安装环境（基于首版验证）：

- 必须：Python 3.12.7（已实际验证）和本项目开发依赖；Git 用于后续提交和版本回滚。
- 明显提效：Python 3.14（后续复验）、GitHub CLI（仓库/Issue 工作流）、PowerShell 7（`pwsh` 事实采集场景）。
- 暂不需要：WSL、Docker、数据库、GUI 和额外 Agent CLI；首版不依赖它们。

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
- [ ] 读取 Windows 用户 PATH 注册表，完成真实 PATH 未刷新采集。
- [x] 记录依赖安装和真实 CLI 的最终输出。

## 暂停检查点

- 当前阶段：首个切片已通过实现、独立审阅、修复和本机复验；本地仓库已初始化为 `main`，等待首次提交和推送。
- 最近验证：14 个测试通过；Ruff 通过；可编辑安装成功；真实 Console/JSON 扫描均退出 0。
- 未完成项：真实用户 PATH 注册表采集、首个 Git 提交与远程仓库推送。
- 下一步唯一动作：提交并推送 `feat: add deterministic Windows environment scan`。
- 恢复命令：

```powershell
Set-Location <repo-path>
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check . --no-cache
agent-preflight scan --json
```

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-08-24 | `python --version` | Python 3.12.7 |
| 2026-08-24 | `python -B -m pytest -q -p no:cacheprovider` | 14 passed |
| 2026-08-24 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；4 pass、8 warning、0 fail、1 unknown；JSON 可解析 |
| 2026-08-24 | `agent-preflight scan --timeout 2` | 退出 0；Console 报告生成成功 |
| 2026-08-24 | `python -m pip install -e ".[dev]" --no-build-isolation` | 安装成功，`agent-preflight.exe` 位于当前 Python Scripts 目录 |

## 下一里程碑验收

- `snapshot` 能导出脱敏的环境事实；
- `compare` 能把宿主/Agent 差异归类为命令、Shell、PATH 或未知；
- 所有外部命令仍由 Runner 执行并有超时；
- 不修改系统配置，不联网，不输出密钥值。

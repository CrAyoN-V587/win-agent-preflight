# 项目进程

## 当前快照

- 当前阶段：第二里程碑已实现，等待主 Agent 验收和提交。
- 完成度：首阶段 `scan` 保持稳定；EnvironmentSnapshot v1、`snapshot` 写出、`compare` 规范化差异、窄解析和 CLI 退出码已实现。
- 最近验证：27 个测试通过，Ruff 通过；同一当前 Agent 环境自比较等价。
- 未完成项：用户在真实宿主终端和 Agent 实际终端分别生成快照、真实项目 probe、Agent 原生 Doctor 适配器、Windows CI。
- 下一步唯一动作：用户在宿主终端和 Agent 实际终端分别运行 `snapshot --label host/agent`，再用 `compare` 检查真实差异。

本机建议安装环境（基于首版验证）：

- 必须：Python 3.12.7（已实际验证）和本项目开发依赖；Git 用于后续提交和版本回滚。
- 明显提效：保留 3.12.7 主环境并可并行安装 Python 3.14（只做后续兼容性复验）、GitHub CLI（仓库/Issue 工作流）、PowerShell 7（`pwsh` 事实采集场景）。
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

## 阶段 2：EnvironmentSnapshot v1 与 compare

状态：实现完成，待主 Agent 验收

- [x] 新建独立 `EnvironmentSnapshot` v1，内嵌已有 `scan` v1 JSON。
- [x] 采集并脱敏 cwd、sys.executable、platform、PATH、PATHEXT；不采集完整环境变量。
- [x] `snapshot` 支持必填 `--label`/`--output`、目录创建、默认不覆盖、`--force`、`--timeout`、`--pretty`。
- [x] `scan` 即使有 fail 也能写出快照并由 snapshot 以 0 退出；工具错误以 2 退出。
- [x] `compare` 支持 Console/JSON/pretty；等价 0、实质差异 1、输入/版本/类型错误 2。
- [x] 窄解析器支持 v1、忽略未知字段，拒绝顶层/内嵌 scan 更高版本和已知字段错误类型。
- [x] 比较忽略 label、captured_at、summary、candidate_count，并按 CheckResult.id 稳定匹配和规范化集合。
- [ ] 用户仍需在宿主终端和 Agent 实际终端分别生成两端快照；当前只完成同一当前 Agent 环境自比较。

## 暂停检查点

- 当前阶段：第二里程碑已通过本机测试和真实自比较，等待主 Agent 检查差异。
- 最近验证：27 个测试通过；Ruff 通过；同一当前 Agent 环境的两份快照写出和 compare 自比较均退出 0。
- 未完成项：用户在宿主与 Agent 两端手动生成快照、真实用户 PATH 注册表采集、第二里程碑 Git 提交与远程仓库推送。
- 下一步唯一动作：用户在宿主终端和 Agent 实际终端分别生成快照，再让主 Agent 审阅差异。
- 恢复命令：

```powershell
Set-Location <repo-path>
python -m pip install -e ".[dev]"
python -B -m pytest -q -p no:cacheprovider
python -m ruff check . --no-cache
agent-preflight scan --json
agent-preflight snapshot --label host --output .\snapshots\host.json --pretty
```

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-08-24 | `python --version` | Python 3.12.7 |
| 2026-08-24 | `python -B -m pytest -q -p no:cacheprovider` | 27 passed |
| 2026-08-24 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；4 pass、8 warning、0 fail、1 unknown；JSON 可解析 |
| 2026-08-24 | `agent-preflight scan --timeout 2` | 退出 0；Console 报告生成成功 |
| 2026-08-24 | `agent-preflight snapshot --label host --output %TEMP%\\win-agent-preflight-m2\\cli-host.json --timeout 1` | 退出 0；输出目录已存在时写出快照 |
| 2026-08-24 | `agent-preflight snapshot --label current --output %TEMP%\\win-agent-preflight-m2\\cli-current.json --timeout 1` | 退出 0；第二快照写出 |
| 2026-08-24 | `agent-preflight compare %TEMP%\\win-agent-preflight-m2\\cli-host.json %TEMP%\\win-agent-preflight-m2\\cli-current.json --json --pretty` | 退出 0；`equivalent: true`，JSON 可解析 |
| 2026-08-24 | `python -m pip install -e ".[dev]" --no-build-isolation` | 安装成功，`agent-preflight.exe` 位于当前 Python Scripts 目录 |

## 下一里程碑验收

- `snapshot` 能导出脱敏的环境事实；
- `compare` 能把宿主/Agent 差异归类为命令、Shell、PATH 或未知；
- 所有外部命令仍由 Runner 执行并有超时；
- 不修改系统配置，不联网，不输出密钥值。

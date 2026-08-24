# 项目进程

## 当前快照

- 当前阶段：第三里程碑已完成，等待创建 GitHub 远程并推送。
- 完成度：首阶段 `scan` 保持稳定；EnvironmentSnapshot v1、`snapshot` 写出、`compare` 规范化差异、窄解析、CLI 退出码和只读注册表 PATH 刷新诊断已实现。
- 最近验证：42 个测试通过，Ruff 通过；真实 HKLM/HKCU PATH 读取完整，CLI JSON 可解析。
- 未完成项：用户在真实宿主终端和 Agent 实际终端分别生成快照、真实项目 probe、Agent 原生 Doctor 适配器、Windows CI。
- 下一步唯一动作：创建 GitHub 公开仓库并推送当前 `main`；随后用户在宿主终端和 Agent 实际终端分别运行 `snapshot --label host/agent`，再用 `compare` 检查真实差异。

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

## 暂停检查点

- 当前阶段：第三里程碑已通过本机测试、独立审阅和真实 registry/CLI 验收。
- 最近验证：42 个测试通过；Ruff 通过；真实 HKLM/HKCU PATH 读取完整，CLI scan 退出 0。
- 未完成项：GitHub 远程创建/推送，以及用户在宿主与 Agent 两端手动生成快照。
- 下一步唯一动作：创建 GitHub 公开仓库并推送当前 `main`，然后用户在宿主终端和 Agent 实际终端分别生成快照。
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
| 2026-08-24 | `python -B -m pytest -q -p no:cacheprovider` | 42 passed |
| 2026-08-24 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；10 pass、3 warning、0 fail、0 unknown；JSON 可解析 |
| 2026-08-24 | `agent-preflight scan --timeout 2` | 退出 0；Console 报告生成成功 |
| 2026-08-24 | `agent-preflight snapshot --label host --output %TEMP%\\win-agent-preflight-m2\\cli-host.json --timeout 1` | 退出 0；输出目录已存在时写出快照 |
| 2026-08-24 | `agent-preflight snapshot --label current --output %TEMP%\\win-agent-preflight-m2\\cli-current.json --timeout 1` | 退出 0；第二快照写出 |
| 2026-08-24 | `agent-preflight compare %TEMP%\\win-agent-preflight-m2\\cli-host.json %TEMP%\\win-agent-preflight-m2\\cli-current.json --json --pretty` | 退出 0；`equivalent: true`，JSON 可解析 |
| 2026-08-24 | `python -m pip install -e ".[dev]" --no-build-isolation` | 安装成功，`agent-preflight.exe` 位于当前 Python Scripts 目录 |
| 2026-08-24 | `python -B -c "from win_agent_preflight.windows import collect_registry_path_facts; ..."` | HKLM/HKCU 读取完整；异常/类型/缺失场景由测试覆盖 |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；10 pass、3 warning、0 fail、0 unknown；JSON 可解析 |

## 下一里程碑验收

- `snapshot` 能导出脱敏的环境事实；
- `compare` 能把宿主/Agent 差异归类为命令、Shell、PATH 或未知；
- `windows.path_refresh` 能从真实 Windows registry PATH 判断继承，错误和未解析值不误报为 pass；
- 所有外部命令仍由 Runner 执行并有超时；
- 不修改系统配置，不联网，不输出密钥值。

# Host ↔ Codex 执行上下文案例

## 案例结论

2026-08-27 在同一台 Windows 机器、同一项目根目录、同一 Python 解释器和相同 5 秒命令 timeout 下，普通 PowerShell 与 Codex Desktop 命令执行器分别生成快照。两次采集相隔约 9 分钟，`compare` 正常以退出码 `1` 报告 8 项有效差异。

这组证据验证了项目的核心假设：Codex 执行环境不是宿主终端环境的简单复制。它会注入自己的 PATH、PowerShell、Git/pnpm fallback 和内部 CLI；同时，Git、Python、npm、pnpm 等共享工具仍可能选择与宿主完全相同的版本。

原始 `host.json`/`codex.json` 只保留在采集机器的 `%TEMP%`，没有提交或上传。本文件只记录人工归约后的公开摘要。

## 采集条件

| 条件 | Host | Codex |
| --- | --- | --- |
| cwd | 项目根目录 | 同一项目根目录 |
| Python | Python `3.12.7`（绝对路径已脱敏） | 同一解释器 |
| timeout | 5 秒 | 5 秒 |
| snapshot schema | v1 | v1 |
| 采集时间差 | 约 9 分钟 | 同轮 |
| 敏感模式检查 | 用户名、常见 GitHub/OpenAI token/key、邮箱命中均为 0 | 同一组合检查 |

## 主要差异

| 维度 | Host | Codex | 解释 |
| --- | --- | --- | --- |
| PATH | 常规系统与用户 PATH | 额外注入 Codex 临时目录、runtime override/fallback、原生 PowerShell/Git 和内部 CLI 目录 | 证明 Agent 子进程环境经过显式编排 |
| Codex launcher | 当前 PATH 未发现 | 内部 `codex.exe` 可执行，版本 `codex-cli 0.150.0-alpha.8` | 桌面 Agent 内部 CLI 可用不代表宿主已安装公开 CLI |
| Git | 选择系统 Git `2.55.0.windows.2` | 选择同一系统 Git，同时存在 Codex fallback 候选 | fallback 存在但没有改变该案例的实际选择 |
| pnpm | 选择 Host 侧安装的 `pnpm.cmd` `11.22.0` | 选择同一 `pnpm.cmd` `11.22.0`，同时存在未被选择的 Codex fallback 候选 | 两端实际工具一致；严格案例没有执行或推断 fallback 版本 |
| Python | 选择 `%PYTHON_HOME%\python.exe`，另可见 WindowsApps alias | 选择同一 Python，未报告该 alias 候选 | `%PYTHON_HOME%` 是公开摘要占位符；不应只比较“命令成功”，候选链也可能不同 |
| npm Shell | Windows PowerShell，npm `11.17.0` | Codex 捆绑 `pwsh`，npm 仍为 `11.17.0` | Shell 不同但该案例的命令结果一致 |
| PATH refresh | warning：当前宿主进程缺少两个配置项占位符 | pass | 当前进程继承状态不同，不等同于工具不可用 |
| Execution Policy | `CurrentUser=RemoteSigned`、`LocalMachine=Undefined` | `CurrentUser=Undefined`、`LocalMachine=RemoteSigned` | 由不同 PowerShell 实现报告；不能直接解释成权限更强或更弱 |

没有差异的关键事实同样重要：两端 cwd、Python 解释器、PATHEXT 以及 Git/Python/npm/pnpm 的最终选择或版本保持一致。差分报告因此既能发现隔离层，也能避免把所有 Agent 行为都误判为不同。

## 被拒绝的前两轮

- `context-run-01`：Host 与 Codex 快照相隔三天，且 1 秒 timeout 让宿主 pnpm 冷启动超时，只保留为流程发现证据。
- `context-run-02`：采集时间接近，但 host cwd 是 `%SYSTEMROOT%\System32`；2 秒 timeout 仍使 pnpm 超时，因此不能满足同项目对照条件。
- `context-run-03`：固定同一 cwd、同一解释器和 5 秒 timeout 后，pnpm 两端均稳定选择 `11.22.0`，成为首个可公开案例。

## 对产品路线的影响

1. 暂不增加新的系统探针。现有能力已经能发现 PATH 注入、launcher 候选和 Shell 差异。
2. 首要体验问题是成对采集容易混用 cwd、轮次和 timeout；短 timeout 还会制造假差异。
3. `v0.1.0` 已从通过 Windows CI 的发布提交创建 Tag/Release，并上传经过验收的制品；外部试运行手册保留为可选反馈入口。
4. 当前暂缓功能开发，优先通过公开访问、克隆、Issue/PR 和脱敏报告观察采用信号；不立即建设自动进入 Agent、自动修复或更多 doctor。
5. 只有外部证据、至少两个独立环境重复缺口，或稳定且现有工具无法区分的上游问题支持时，才从 Shell/runtime mismatch、WindowsApps launcher chain 或显式 opt-in 网络对照中选择一个切片。发布和至少两次相关分享后 14 天仍有访问/克隆但没有 Star 时，只允许先做一次定位或演示调整。

## 复验入口

完整命令、退出码和公开检查边界见 [`context-comparison.md`](context-comparison.md)。`compare` 返回 `1` 表示成功发现有效差异，不是工具运行失败。

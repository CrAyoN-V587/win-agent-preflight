# 需求与研究记录

## 研究结论

Windows 上的 Coding Agent 故障通常不是“程序是否存在”一个问题，而是分层问题：当前进程 PATH、PowerShell 解析、脚本执行策略、子进程继承、Agent 沙箱和工作区能力可能不同。产品自带诊断通常只覆盖自己的产品，不能形成跨 Agent 的中立事实报告。

首阶段因此只做确定性本地扫描，优先覆盖用户已经遇到的 npm.ps1 被阻止、pnpm 安装后旧终端 PATH 未刷新和命令多版本冲突；第六里程碑的 `agent-doctor` 进一步只探测已解析启动器的离线版本能力。

## 官方 CLI 事实与本项目边界（2026-08-24）

- [OpenAI Codex 官方仓库](https://github.com/openai/codex) 是本地终端 coding agent。本项目只执行已解析本地 `codex --version`；不调用 `codex login status`，也不执行交互式 `debug-config`，因为账户状态和交互配置诊断不属于离线 launcher 可用性探针。
- [Claude Code 官方安装文档](https://code.claude.com/docs/en/getting-started) 建议用 `claude --version` 验证安装，并提供只读的 `claude doctor` 安装/设置诊断。本项目的跨 Agent 探针只执行本地 `claude --version`，不触发 `doctor`、登录、网络或其他交互流程。
- [DeepSeek Harness 官方页面](https://www.deepseek.com/harness/en/) 和[官方仓库](https://github.com/deepseek-ai/deepseek-harness)均标注 DSH 为 developer preview。官方快速开始使用 `npx @deepseek-ai/dsh web`，但本项目明确不运行 `npx` 或 `web`，只在 PATH 已有本地 launcher 时执行 `dsh --version`。

这些边界使报告可重复、低副作用，并避免把登录、联网、包管理器安装或网页启动误判为本地命令可用性。

## 相似实现与差异

- Codex、Claude Code 和 DSH 各自的 CLI/文档提供产品内入口；本项目不复刻它们的内部诊断，而报告跨 Agent 都能理解的 launcher 状态和结构化 Runner 证据。
- 第三方跨 Agent 工具多集中于配置同步或 Agent 编排；本项目首阶段保持离线、只读和证据优先。

## 真实场景

1. `node --version` 成功，`npm` 命令被 PowerShell 选中的 `npm.ps1` 阻止；`npm.cmd` 仍可用。
2. 新安装 pnpm 后安装器更新了用户 PATH，但当前 PowerShell 进程仍使用旧 PATH。
3. 同一命令在 PATH 中有多个候选版本，Agent 和宿主可能选到不同路径。
4. 可选 Agent 未安装不应被错误报告为系统故障。
5. 外部命令卡住时，诊断工具必须在有限时间内返回并报告 timeout，而不是继续等待。

## 首阶段取舍

- 不联网：网络本身属于下一阶段对照探针，且无需 API。
- 不自动修复：修改 PATH、注册表或执行策略会改变用户环境，先提供证据和复验方向。
- 不采集密钥：本地环境变量只采集存在性/命名，不保存值。
- 不计算哈希：当前没有缓存身份或完整性消费者。
- Python 3.12.7：本机实际可用版本；记录此事实，后续可在 3.14 环境复验。

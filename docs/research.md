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

## Git Doctor 研究与离线边界（2026-08-24）

### 官方事实

- [Git `config` 官方文档](https://git-scm.com/docs/git-config)说明 `user.name`/`user.email` 属于本地提交身份配置；`credential.helper` 是 Git 在需要凭据时调用的外部 helper，helper 可以访问外部凭据存储或缓存。因此本项目只读取配置是否存在、scope 和 helper 是否像 GCM，不执行 helper，也不把原值写入报告。
- [GitHub 提交邮箱文档](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address)说明可使用 GitHub 提供的 `noreply` 地址作为提交邮箱。Git Doctor 只报告 name/email 是否配置及 scope，不验证邮箱格式、账号关联或 GitHub 接受结果。
- [GitHub CLI `gh auth status` 手册](https://cli.github.com/manual/gh_auth_status)说明该命令会检查已知 GitHub host 的认证状态；`gh auth` 还涉及凭据存储和登录流程。因此本项目只在 GitHub remote 下探测本地 `gh --version`，固定把 `github.auth` 标记为 `not_checked_offline`，不运行 `gh auth status`、`gh auth token` 或登录。
- [Git Credential Manager 官方仓库](https://github.com/git-ecosystem/git-credential-manager)说明 GCM 是跨平台 Git credential helper，支持 GitHub 等 HTTP(S) host；其[凭据存储文档](https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/credstores.md)列出 Windows Credential Manager、DPAPI 等存储。Git Doctor 不读取这些存储、不执行 GCM、也不做 `diagnose`，只将 `credential.helper` 配置归约为 `configured`、`gcm_detected` 和 `helper_count`。

### 项目取舍

- Git Doctor 的“ready”只表示本地 launcher、工作树、提交身份和 origin 配置达到可读条件，不表示远程网络、账号授权、push 权限或 Agent 沙箱可用。
- 固定查询全部走同一个有界 Runner；Git 子命令使用 `-C TARGET` 而不是改变 Runner cwd。除版本探测外不运行 push、fetch、pull、ls-remote、ssh、credential fill、GCM diagnose 或网络命令。
- remote URL 只归约为 transport、`github.com|other|local|unknown`、fetch/push 是否同目的和 embedded userinfo 布尔值；不输出 owner/repo、用户名、密码、企业 host、helper 路径或命令 stderr。该归约用于选择是否需要本地 `gh --version`，不是远程连通性验证。
- 归约边界需区分协议语义：标准 `ssh://git@github.com/...` 的 `git` 是 SSH username，不是 HTTP 凭据；只有 SSH URI 携带 password 才告警。Windows 本地 remote 先按本地路径解析，因此 `C:\Repos\My Repo\origin.git` 中的空格不会被当成 malformed URL；未知 `--show-scope` 输出不算已配置身份。
- 认证结果必须固定为 `remote_auth_verified=false`，否则离线报告会把“安装了 gh”误写成“已登录 GitHub”。真正的认证/网络验收留给用户显式运行并承担副作用的 Git/gh 工作流。

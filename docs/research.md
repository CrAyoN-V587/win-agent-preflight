# 需求与研究记录

## 研究结论

Windows 上的 Coding Agent 故障通常不是“程序是否存在”一个问题，而是分层问题：当前进程 PATH、PowerShell 解析、脚本执行策略、子进程继承、Agent 沙箱和工作区能力可能不同。产品自带诊断通常只覆盖自己的产品，不能形成跨 Agent 的中立事实报告。

首阶段因此只做确定性本地扫描，优先覆盖用户已经遇到的 npm.ps1 被阻止、pnpm 安装后旧终端 PATH 未刷新和命令多版本冲突；第六里程碑的 `agent-doctor` 进一步只探测已解析启动器的离线版本能力。2026-08-27 复审后，主路线进一步收敛为“Windows host/Agent 执行上下文差异诊断”，不再用新增 doctor 数量衡量进度。

## 官方 CLI 事实与本项目边界（2026-08-24）

- [OpenAI Codex 官方仓库](https://github.com/openai/codex) 是本地终端 coding agent。本项目只执行已解析本地 `codex --version`；不调用 `codex login status`，也不执行交互式 `debug-config`，因为账户状态和交互配置诊断不属于离线 launcher 可用性探针。
- [Claude Code 官方安装文档](https://code.claude.com/docs/en/getting-started) 建议用 `claude --version` 验证安装，并提供只读的 `claude doctor` 安装/设置诊断。本项目的跨 Agent 探针只执行本地 `claude --version`，不触发 `doctor`、登录、网络或其他交互流程。
- [DeepSeek Harness 官方页面](https://www.deepseek.com/harness/en/) 和[官方仓库](https://github.com/deepseek-ai/deepseek-harness)均标注 DSH 为 developer preview。官方快速开始使用 `npx @deepseek-ai/dsh web`，但本项目明确不运行 `npx` 或 `web`，只在 PATH 已有本地 launcher 时执行 `dsh --version`。

这些边界使报告可重复、低副作用，并避免把登录、联网、包管理器安装或网页启动误判为本地命令可用性。

## 相似实现与差异

- [EXboys/agent-doctor](https://github.com/EXboys/agent-doctor) 覆盖多 Agent 发现、配置/网关漂移、备份修复、回滚、工作区隔离和团队治理，是名称与类别上最接近的项目；本项目不进入配置修复和控制面，保留 Windows 执行上下文差分边界。
- [windows-claude-code-doctor](https://github.com/IliaMalkin/windows-claude-code-doctor) 覆盖 PowerShell、Git Bash、WSL、路径转换、换行符、端口和文件锁，是问题域最接近的脚本/Skill；本项目的差异是独立 CLI、稳定 JSON、snapshot/compare 和跨 Agent 的有界探针。
- [microsoft/ArgusAgent](https://github.com/microsoft/ArgusAgent) 的 `argus doctor` 可让 Agent 主动检查并修复 Argus 环境；本项目不启动真实 Agent 回合，也不执行修复。
- [Microsoft APM Doctor](https://microsoft.github.io/apm/reference/cli/doctor/)、[React Native Doctor](https://reactnative.dev/blog/2019/11/18/react-native-doctor.html)、[Expo Doctor](https://docs.expo.dev/develop/tools/) 和 [.NET MAUI 环境诊断](https://learn.microsoft.com/en-us/dotnet/maui/developer-tools/cli/environment-diagnostics?view=net-maui-10.0) 证明确定性 preflight/doctor 是成熟的工具形态，但它们服务各自生态，不比较编码 Agent 与宿主进程。
- [NVIDIA-Agent-Doctor](https://github.com/karthikrshet/NVIDIA-Agent-Doctor) 同样采用本地优先、结构化 JSON 和只读默认值，但服务 GPU/CUDA/Docker/MCP 环境；[Laravel Doctor](https://github.com/laravel/doctor) 的紧凑 Agent 输出值得作为后续入口设计参考。

本轮检索没有发现成熟且完全替代“同机 host 与真实 Coding Agent 分别采样，再比较 PATH、launcher、Shell 和工作区能力”的项目。组件重合度较高，产品级完全重合度较低；因此不应宣称没有竞品，也不应把项目描述成通用 Agent Doctor。

## 公开需求证据（2026-08-27）

- Codex 已出现“PATH 中存在但沙箱执行被拒绝”和捆绑 `rg.exe` 可解析却 `Access Denied` 的报告：[openai/codex#28075](https://github.com/openai/codex/issues/28075)、[openai/codex#15148](https://github.com/openai/codex/issues/15148)。
- Windows 受限 Token/目录写入和宿主网络正常但沙箱 DNS/代理失败也有公开案例：[openai/codex#22044](https://github.com/openai/codex/issues/22044)、[openai/codex#18675](https://github.com/openai/codex/issues/18675)。
- Claude Code 已出现用户 PATH 已更新但继承进程仍提示命令缺失、终端重启后才刷新，以及 PowerShell/Git Bash 选择不一致的问题：[anthropics/claude-code#32098](https://github.com/anthropics/claude-code/issues/32098)、[anthropics/claude-code#18064](https://github.com/anthropics/claude-code/issues/18064)、[anthropics/claude-code#83889](https://github.com/anthropics/claude-code/issues/83889)。
- WindowsApps alias 劫持或不可访问的 launcher 也有公开报告：[anthropics/claude-code#25075](https://github.com/anthropics/claude-code/issues/25075)、[openai/codex#35871](https://github.com/openai/codex/issues/35871)。

这些证据支持需求存在，但本仓库当前尚无 Star、Issue 或外部试用反馈形成的采用证据。下一阶段必须用真实双端案例和 3–5 名用户试运行验证可理解性与使用价值，不能把 261 项测试或 CI 通过直接解释为市场验证。

## 路线评估（2026-08-27）

- 需求真实性：高；公开问题直接覆盖 PATH 继承、launcher access denied、Shell 差异和目录能力。
- 重合风险：中等；配置修复、生态 doctor 和 Windows 排障脚本已经存在，但 host ↔ Agent 独立差分仍有空间。
- 当前实现难度：中等；生产级覆盖 Codex/Claude、Store/原生安装、PowerShell/Git Bash/WSL 和变化中的沙箱行为属于高难度测试矩阵。
- 最优路线：真实成对案例 → 首选入口或紧凑 Agent 输出 → 3–5 名外部用户 → 一个重复证据驱动的切片。
- 候选切片：Shell/runtime mismatch、WindowsApps launcher chain、显式 opt-in 网络上下文对照；三者都不是当前承诺。
- 明确非目标：自动修复、Agent 配置治理、MCP/Memory/Skill 管理、GUI/团队控制面、广泛安全审计和通用 Windows 全科诊断。

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

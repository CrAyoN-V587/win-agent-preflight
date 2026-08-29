# Windows Agent Preflight

状态：0.1.0 发布材料整理完成，等待本轮提交及 Windows CI；发布后暂缓功能开发
类型：P3 Agent  
开始日期：2026-08-24  
最近更新：2026-08-29
时间箱：首个可运行切片 1 周；快照/比较里程碑 1 周；后续总计 3–5 周

## 30 秒上下文

一句话目标：提供面向 Windows Coding Agent 的执行上下文差异诊断，比较宿主终端与 Agent 沙箱中的命令、PATH、Shell、启动器和工作区能力。

当前阶段：首组严格 Host ↔ Codex 案例、公开文档身份审阅和 `0.1.0` 发布整理已完成。两端使用相同项目 cwd、Python 解释器和 5 秒 timeout，采集相隔约 9 分钟；`compare` 退出 1 并报告 8 项有效差异，归约结果见 `docs/host-codex-case-study.md`。下一步按“维护者先确定日期并定稿 0.1.0 Changelog → 提交并推送最终发布材料 → 等待该提交 Windows CI 成功 → 在同一提交创建 `v0.1.0` tag/Release 并上传制品”执行，随后暂缓功能扩展；外部试运行保留为可选反馈入口。

下一步：由具有仓库权限的维护者先确定日期并定稿 0.1.0 Changelog，提交并推送最终发布材料，等待该提交的 Windows CI 成功，再在同一提交创建 `v0.1.0` tag/Release 并上传制品；随后暂停功能开发，继续接受 Issue/PR/脱敏报告并观察采用信号。外部手册可选，不把找不到参与者作为发布阻塞。

最近验证（2026-08-29）：全量 261 项测试、Ruff、`git diff --check`、真实只读 `scan`/`support-report`/`agent-doctor`、Markdown 本地链接、敏感路径和身份语气检查通过；v0.1.0 sdist/wheel 构建及两个临时干净环境安装后的 CLI help 通过。严格 Host ↔ Codex compare 仍退出 1 并报告 8 项有效差异；原始快照未提交。已推送功能基线的 Windows CI `32712146556` 仅是既有功能证据，不是本轮发布材料的 CI 验收；本轮尚未执行发布材料提交、该提交的 Windows CI、GitHub Tag/Release 或制品上传。

真实项目复验：`project-doctor` 正确识别 MyMineCraft 的 Node + pnpm 和 MCP Interop Lab 的 Python；两份无标准依赖 marker 的旧 Triton 源码树保守返回 `unknown`。同一 Codex 上下文的 `workspace-probe` 在 Triton 优化项目六步通过，在 MyMineCraft 与 MCP Interop Lab 创建目录时返回 WinError 5；三次均无残留。

## 问题和价值

- 要解决的问题：Windows 上“命令已安装但 Agent 无法使用”的分层诊断问题。
- 目标用户：使用 Codex、Claude Code、DeepSeek Harness 等工具的 Windows 开发者。
- 核心差异：由宿主终端和真实 Agent 执行器分别采样，再比较进程继承的 PATH、launcher 解析和目录能力；不把同一进程生成的两份报告伪装成跨上下文证据。
- 为什么值得做：公开问题中反复出现“宿主可用、Agent 不可用”、WindowsApps/launcher `Access Denied`、PowerShell/Git Bash 不一致和用户 PATH 已更新但 Agent 进程未继承等故障；项目把这些现象归约为可复验、可分享的脱敏报告，减少误判为项目代码问题。
- 产品定位：不是通用配置修复器、Agent 管理平台或 Windows 全科排障工具，而是 Windows Coding Agent execution-context differential preflight。

## 工程学习与作品集价值

- 可体现的能力：系统边界设计、可注入测试、CLI 后端和 Git 里程碑管理。
- 工程证据：稳定数据模型、超时控制、分层诊断、JSON/人类可读输出和 Windows CI。
- 项目来源：早期本地开发中实际出现的 npm.ps1、pnpm PATH 未刷新和 Codex 环境差异问题。

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
- 显式 `--target PATH --allow-write` 的 Windows 工作区写入、读取、重命名、删除和清理能力探针；结论只适用于本次命令、目标目录和当前进程上下文。
- Windows-only CI：Python 3.12/3.14 测试矩阵、3.12 Ruff、`RUNNER_TEMP` workspace-probe 和 Python 3.12 的 sdist/wheel 干净环境安装验收。
- 独立 `agent-doctor`：默认/重复 `--agent` 选择、PATH 中多类 launcher 解析、同一 Agent 多候选回退、每个候选最多一次 `--version` 探针和脱敏状态报告。
- 独立 `support-report`：固定 v2 组合 envelope、有限环境事实、Agent Doctor 结果复用、scan 预计算注入、纯 `next_checks` 推导和脱敏采集错误。
- 独立 `project-doctor`：只读取目标第一层十个固定 marker，推导 python/node/npm/pnpm/cmake，按固定顺序执行必需工具的 `--version`，不递归、不读 marker 内容、不使用目标目录 cwd。
- 独立 `command-doctor`：只接受一个 ASCII 安全 basename，按 PATH/PATHEXT 探测 `.exe`/`.cmd`/`.bat` 并追加 `.ps1`，固定执行 `--version`，按需要采集 PowerShell 裸命令/执行策略和只读 PATH refresh；不递归、不联网、不写文件。
- 独立 `git-doctor`：显式 target 的 Git launcher/worktree/commit identity/origin/helper/必要 GitHub CLI 离线诊断；固定只读命令、远端归约和 `remote_auth_verified=false`，不做网络或认证验证。
- 独立 `workspace-scope`：显式 target/control 双目录和 `--allow-write`，预验证后按固定顺序各调用一次既有 workspace probe，比较单次上下文能力并保留 inconclusive partial。
- snapshot 写出：目标父目录内最多三次 UUID 临时名的 `O_EXCL` 创建，只有名称碰撞重试；完成后按 force/non-force 语义提交，失败只清理本次已知临时文件。

不包含：

- 自动进入 Agent 沙箱或自动生成真实 host/agent 双端快照；
- 联网、自动修复、注册表或执行策略写入/修改；
- 密钥采集、哈希、发布级安全审计；
- GUI、数据库和 LLM 调用。
- 递归删除、历史探针清理、目标目录遍历、ACL/提权审计或自动修复。
- Agent 配置同步、MCP/Memory/Skill 治理、网关修复、团队控制面和主动调用 Agent 自我修复。
- 在没有外部证据或至少两个独立环境重复缺口前增加端口、文件锁、Defender、GPU、Docker、WSL、代理或通用网络诊断。
- PyPI/Release 自动发布、签名、SBOM、Actions 缓存和跨平台 CI/制品。
- `agent-doctor` 不执行 login、doctor、npx、网页或网络调用，不改变既有 scan/snapshot/workspace schema。
- `support-report` 不执行 workspace-probe、login、doctor、npx、web、网络或写文件，不提供自动行动建议；仅组合已有本地报告。
- `next_checks` 只由既有 scan/Agent Doctor 模型触发，不解析自由文本、不运行命令、不读取环境；仅覆盖明确的 Agent launcher/version、PowerShell npm 和 PATH refresh 场景。
- CLI 公开帮助使用 ASCII 文字并关闭 Rich Unicode 帮助边框；实际报告输出和中文文档不因此改变。
- `project-doctor` 只接受显式 `--target`；冲突/孤立 lockfile、yarn/bun lockfile 或 marker 检查异常标记为 `unknown`，未列入固定表的项目文件直接忽略；实现已完成独立审阅和远程 CI 验证。
- `command-doctor` 不诊断 PATH 之外的命令，不执行 login/doctor/npx/web 或其他参数；明确请求的缺失命令是能力失败（退出 1），非法输入和非 Windows 平台退出 2；实现已完成独立复审和远程 CI 验证。
- `git-doctor` 不运行认证、credential fill、GCM diagnose、push/fetch/pull/ls-remote/ssh 或网络；原始 identity、remote、helper 值不进入报告，GitHub auth 固定为离线 unknown；实现已完成独立复审和远程 CI 验证。
- `workspace-scope` 不改变 WorkspaceProbeReport v1；预验证失败退出 2 且零写入，普通 probe 失败继续 control，子报告若无 PASS/FAIL 可归约证据则为 unknown 并使完整报告 `inconclusive`，异常/中断不继续并报告 partial `inconclusive`；不枚举、不递归、不联网。

## 成功标准

- [x] 首个切片可通过一条命令执行 `scan`，并同时支持 Console 与 JSON。
- [x] 命令缺失、多候选、超时、PowerShell 脚本阻止和 PATH 未刷新注入场景均有测试。
- [x] 只读采集 HKLM/HKCU PATH，完成非注入的 PATH 未刷新诊断；异常/类型错误保持为不完整事实。
- [x] `scan` 中可选 Agent 未安装不产生 `fail`；所有 `scan` 的 `fail` 都包含证据，`agent-doctor` 使用独立的 `command_not_found`。
- [x] 用户目录统一脱敏为 `%USERPROFILE%`，不输出密钥值或哈希。
- [x] PROJECT.md 与 `docs/PROGRESS.md` 能在暂停后直接恢复。
- [x] probe 只接受显式目标和 `--allow-write`，输入拒绝前不写入；报告独立于 scan/snapshot schema。
- [x] probe 固定六项输出 `successful` 与相对 `residual_paths`，不回显固定内容，清理不递归。
- [x] 创建 Windows-only CI 配置：Python 3.12/3.14 测试、3.12 Ruff、CLI/runner-temp probe 和测试后包验收。
- [x] 配置 sdist/wheel 各一个、干净虚拟环境安装和非 PR 7 天制品上传；不配置自动发布。
- [x] 首次 CI run 已实际验证 Python 3.12/3.14 的安装与 pytest，3.12 Ruff 通过；失败根因集中在根 `--help` 的 cp1252 编码。
- [x] 修复后的 Windows CI 在两个矩阵 job 及后续 sdist/wheel package job 全部通过。
- [x] `agent-doctor` 全量回归测试、Ruff 和真实 CLI 验收通过；2026-08-24 初次实测结果为 Codex `access_denied`、Claude/DSH `command_not_found`。
- [x] `support-report` 复用共享 Runner/env/timeout；Agent Doctor 每个已发现候选最多执行一次，scan 不重复探测三个 Agent；Console/JSON 和部分失败退出语义有测试。
- [x] `SupportReport v2` 保留 v1 顶层字段并增加不可变 `next_checks`；固定优先级/Agent 顺序、去重、触发边界和 Console/JSON 展示均有测试。
- [x] 根命令和全部子命令 help 在严格 `PYTHONIOENCODING=cp1252:strict` 下可解码并退出 0，且不会执行采集或写文件。
- [x] `project-doctor` 的固定 marker 推导、冲突/孤立、marker 异常累计、输入边界、工具调用/required_by、脱敏、JSON/Console 和退出码已有本地及远程测试。
- [x] snapshot 写入改为有界 `O_EXCL` 临时文件流程；权限/其他写入错误快速退出 2，失败不留下本次临时文件，覆盖碰撞、写入、fsync、替换和 CLI 错误路径测试。
- [x] `command-doctor` 独立 v1、严格输入、候选回退、固定 `--version`、裸 PowerShell/执行策略/Path refresh 边界和 cp1252/退出码测试已通过本地及远程验证。
- [x] `git-doctor` 独立 v1：固定只读命令、状态归约、脱敏、CLI/退出码和常见 remote 边界已通过本地及远程验证。
- [x] `workspace-scope` 独立 v1：双目录预验证、target/control 单次顺序调用、usable/failed/unknown 归约、完整/partial `inconclusive`、CLI/Console/JSON 和 cp1252 help 已完成本地及远程验证。
- [x] 完成一组同机、同项目、同工具版本的真实 host ↔ Codex 快照和差异报告，并公开一份人工检查后的脱敏案例。
- [x] 用真实案例验证现有成对采集路径：确认 cwd/轮次/timeout 是必要前置条件；外部试运行保留为可选反馈，不作为发布前置条件。
- [x] 公开文档按访问者、参与者、宿主操作者、维护者和 Agent 分配受众，不把本地认证或个人机器状态写成仓库事实。
- [x] 形成可选的外部试运行手册和最小回传模板；是否有参与者不作为 `0.1.0` 发布前置条件。

## 计划

- [x] 1. 建立数据模型、Runner、命令发现和 PowerShell 事实采集边界。
- [x] 2. 实现 `scan` 的 Console/JSON 输出并覆盖首批故障案例。
- [x] 3. 加入 EnvironmentSnapshot v1、`snapshot` 写出和 `compare` 差异退出语义。
- [x] 4. 加入只读注册表 PATH 事实、变量展开和跨 scope 刷新诊断。
- [x] 5. 增加有边界的 `workspace-probe`，验证当前进程上下文的最小文件能力并保留清理证据。
- [x] 6. 增加 Windows CI、包构建验收和本地 release-check 文档。
- [x] 7. 由宿主操作者与真实 Agent 执行器分别生成快照，验证真实环境差异。
- [x] 8. 增加独立 `agent-doctor` 版本探针和结构化状态报告；发布仍保持显式、手动边界。
- [x] 9. 增加离线 `support-report` 组合报告；不增加 workspace-probe、网络或自动修复流程。
- [x] 10. 将 `support-report` 升级为 v2，增加纯 `next_checks` 推导；不维护双版本或执行自动建议。
- [x] 11. 将 Typer 公开 help/docstring 调整为 ASCII，关闭 Unicode 帮助格式，并加入 cp1252 子进程 smoke test；不改变报告输出（已推送并通过 CI）。
- [x] 12. 增加独立 `project-doctor` v1：第一层 marker 推导与必需工具 `--version` 探测；设计、实现、复审与远程验证完成。
- [x] 13. 修复 snapshot 在拒绝写入目录中可能高 CPU/长时间重试的问题；实现有界临时文件创建和失败清理，并通过远程 CI。
- [x] 14. 建立 host/Agent 双端采集协议；不新增伪自动化包装，Codex 端已在 `%TEMP%` 生成并验证首份快照。
- [x] 15. 增加独立 `command-doctor` v1：单命令 PATH launcher 诊断和只读 PowerShell 辅助检查；设计、实现、复审与远程验证完成。
- [x] 16. 增加独立 `git-doctor` v1：离线判断本地 Git readiness；不验证远程认证、不联网、不写配置；设计、实现、复审与远程验证完成。
- [x] 17. 增加独立 `workspace-scope` v1：预验证两个显式目录后按 target/control 各调用一次既有 probe；设计、实现、复审、真实矩阵与远程验证完成。
- [x] 18. 复审同类项目和公开需求，将主路线收敛为 Windows host/Agent 执行上下文差异诊断；保留离线、只读、不自动修复边界。
- [x] 19. 完成真实 host ↔ Codex 成对采集，形成脱敏案例、差异解释和可复验命令。
- [x] 20. 根据真实案例收敛路线：将外部手册保留为可选反馈入口；发布前不新增探针，后续是否恢复只由公开采用证据和重复环境缺口决定。
- [x] 21. 完成 `0.1.0` 发布整理；发布后暂缓功能扩展，恢复条件改由外部证据、独立环境重复缺口、稳定且现有工具无法区分的上游问题，或一次有限的定位/演示调整决定。

## 技术和环境

- 操作系统：Windows（设计目标）；首次本地验证环境为 Windows、PowerShell 和 Python 3.12.7。
- 语言与版本：Python `>=3.12`；首次本地验证使用 Python 3.12.7；Windows CI 已完整验证 Python 3.12/3.14 矩阵。
- 主要依赖：运行时 `typer>=0.16,<1`；开发依赖 `build>=1,<2`、`pytest>=8,<9`、`ruff>=0.12,<1`。
- 安装/准备命令：`python -m pip install -e ".[dev]"`
- 本地包验收：`py -3.12 -m build --sdist --wheel`，再按 `docs/release-check.md` 分别安装两个制品。
- 运行命令：`python -m win_agent_preflight scan`、`agent-preflight snapshot --label host --output .\\snapshots\\host.json`、`agent-preflight compare baseline.json current.json`、`agent-preflight workspace-probe --target . --allow-write --json --pretty`、`agent-preflight workspace-scope --target . --control $env:TEMP --allow-write --json --pretty`、`agent-preflight agent-doctor --json --pretty`、`agent-preflight command-doctor npm --json --pretty`、`agent-preflight git-doctor --target . --json --pretty`、`agent-preflight support-report --json --pretty`、`agent-preflight project-doctor --target . --json --pretty`
- 针对性验证命令：`python -B -m pytest -q -p no:cacheprovider`
- 完整验证命令：先运行 `python -B -m pytest -q -p no:cacheprovider`，通过后再运行 `python -m ruff check . --no-cache`。

维护与开发环境建议：

- 必须：Python 3.12 或更高版本、本项目开发依赖和 Git；Python 3.12.7 已完成首次本地验证。
- 可选：Python 3.14、Python Launcher、GitHub CLI 和 PowerShell 7。账号与认证状态属于各维护者的本地环境，不记录为项目状态。
- 暂不需要：Node.js、Docker、WSL、数据库、GUI 工具和额外 Agent CLI；它们不属于当前测试和打包路径。

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
- 首批模型、脱敏、缺失、候选、超时和注册表事实测试；
- 独立 `WorkspaceProbeReport v1`、六步文件能力探针、相对残留报告和 CLI 130 中断交接。
- Windows-only CI、Python 3.12/3.14 测试矩阵、3.12 Ruff、runner-temp probe 和 sdist/wheel 包验收；包含 `command-doctor` 的 main run `32703174150` 已全部通过。
- 独立 `AgentDoctorReport v1`、固定 Agent 选择、四类 launcher 解析、`--version` 最小探针、结构化 Runner 错误和失败输出脱敏实现，并已通过全量验证。
- 独立 `SupportReport v2`、不可变 `NextCheck` 和纯 `derive_next_checks` 推导；实现、测试和独立复审已完成并提交为 `9f5b951`。
- CLI help cp1252 修复：Typer 公开 help/docstring 使用 ASCII，关闭 Rich Unicode 边框；根命令和全部子命令由严格 cp1252 子进程测试覆盖。
- 独立 `ProjectDoctorReport v1`、固定第一层 marker 推导、首项 marker CheckResult、必需工具 `--version` 探测、目标边界拒绝和独立 JSON/Console 输出已在本地实现。
- snapshot 写入已改为最多三次 UUID 临时名的 `O_EXCL` 创建；只对名称碰撞重试，写入/替换/清理失败路径只处理本次已知临时文件。
- `command-doctor` 已完成独立 v1 报告、严格 basename、PATHEXT 候选、共享 launcher probe、固定 `--version`、裸 PowerShell/执行策略/Path refresh 检查、非 Windows 门禁和 CLI 退出码，并在 `a311f96` 推送后通过远程验证。
- `git-doctor` 已完成独立 v1 报告、Git/remote/helper 归约、GitHub CLI 条件探测、固定命令白名单、失败结构化证据、37 项定向回归和真实仓库根只读验收；提交 `67697c7` 已通过 Windows CI `32708225452`。
- `workspace-scope` 已完成独立 v1 报告、双目录输入预验证、target/control 顺序各一次既有 probe、usable/failed/unknown 归约、五种固定状态、partial 异常/中断和 CLI 输出；提交 `b981bf1` 已通过 Windows CI `32712146556`。

当前阻塞：

- 无实现、认证或成对采集阻塞。`context-run-03` 已完成严格比较；原始快照只保留在采集机器的 `%TEMP%`，公开仓库只记录脱敏归约摘要。

发布前后边界：

- 发布动作按以下顺序执行：维护者先确定日期并定稿 0.1.0 Changelog；提交并推送 README、中文说明、CHANGELOG、Issue 表单及其他最终发布材料；等待该提交的 Windows CI 成功；再在同一提交创建 `v0.1.0` tag/Release 并上传制品。既有功能基线 CI 只能作为历史证据，不能替代本轮发布提交验收。
- 发布后保持运行时代码不变；`docs/external-pilot-guide.md` 作为可选反馈材料，案例和详细采集协议作为公开背景。
- 只有满足恢复条件，才重新设计紧凑 Agent 输出、成对证据预验证或至多一个证据驱动切片；不因缺少外部参与者而猜测实现。

暂停与恢复边界：

- 历史时间箱结束后暂停推测性功能扩展；当前不再新增 ACL、代理、网络、长路径或更多生态识别功能。
- 只有外部 Issue/PR/真实报告、至少两个独立环境重复同类缺口，或稳定且现有工具无法区分的上游问题时，才恢复功能设计。
- 发布并完成至少两次相关分享后，若 14 天仍有访问/克隆但没有 Star，只允许进行一次定位或演示调整，再决定是否恢复实现。
- 不进入自动修复、Agent 配置治理、GUI/团队控制面和广泛 Windows 全科诊断；这些方向与现有项目重合且会显著扩大维护和误修风险。
- 恢复时先读取本文件与 `docs/PROGRESS.md`，检查 `git status --short`，不要重复已经通过的 261 项/CI 验证；Star 是采用信号，不直接等于质量。

工作区恢复检查：

- 先运行 `git status --short`，以实际输出判断是否存在未提交修改；不要在此维护容易过期的文件清单。
- 远程 `main` 的最近已验证功能基线为 `b981bf1`（Workspace Scope），对应 Windows CI `32712146556`。

## 关键决策

| 决策 | 原因 | 日期 |
| --- | --- | --- |
| 首次本地验证使用 Python 3.12.7 | 当时的维护环境只有 3.12.7，且 Windows CLI 原型不需要为追新版本延迟验证 | 2026-08-24 |
| Snapshot 内嵌已有 scan v1 | 保持 scan JSON 语义唯一，快照只增加有限宿主事实 | 2026-08-24 |
| Compare 忽略 label/time/summary/candidate_count | 这些字段会在同一环境重复运行时自然变化，不应制造实质差异 | 2026-08-24 |
| 外部命令统一经可注入 Runner | 让超时、启动失败和环境差异可以稳定复现 | 2026-08-24 |
| `scan` 中可选 Agent 缺失为 warning | “未安装”不是 Agent 故障，避免误报；`agent-doctor` 使用独立的 `command_not_found` | 2026-08-24 |
| 注册表 PATH 只读且异常不降级为空 | 区分真实空值和权限/类型错误，避免误报 PATH 已刷新 | 2026-08-24 |
| 刷新检查永不 fail | PATH 缺失/不完整是环境事实不足或提示，不是项目命令本身已证实失败 | 2026-08-24 |
| probe 使用独立 v1 schema | 有副作用的最小能力验证不混入只读 scan/snapshot 协议 | 2026-08-24 |
| probe 按对象身份复核本次路径 | 不把能力诊断变成目标目录清理器；身份变化或未知内容保留并用相对路径报告 | 2026-08-24 |
| probe 结论限定为单次上下文 | 一次宿主或 Agent 运行不能替另一个上下文作权限结论 | 2026-08-24 |
| probe 采用非对抗本地并发假设 | 对象身份变化会保守拒绝，但首版不为身份核对与路径删除之间的瞬时替换引入 Win32 句柄级安全实现 | 2026-08-24 |
| CI 只验证 Windows Python 3.12/3.14 和包安装 | 项目目标是 Windows Agent 环境；保持最短反馈路径，不引入跨平台矩阵 | 2026-08-24 |
| 构建验收不等于发布 | 本阶段只需要确认 sdist/wheel 可安装并启动 CLI，发布、签名和 SBOM 留待明确发布阶段 | 2026-08-24 |
| Agent Doctor 使用独立 v1 状态 | Agent 启动器的“未发现”和“已发现但不可用”不应改变 scan/snapshot/workspace 的既有 schema/退出语义 | 2026-08-24 |
| Agent Doctor 只探测已解析 launcher 的 `--version` | 保持本地、低副作用和可复验边界，不触发 login、doctor、npx、网络或网页流程 | 2026-08-24 |
| Git Doctor 使用独立 v1 且只报告 local readiness | Git 身份、远端和 helper 只能输出归约事实；离线诊断不应伪称 GitHub 登录或 push 可用 | 2026-08-24 |
| Agent Doctor 保留 lstat/Runner 结构化错误 | WindowsApps alias 和权限异常不能被静默降级为 command_not_found；失败证据不回显 stdout/stderr | 2026-08-24 |
| SupportReport v2 只组合本地结果并纯推导 next_checks | 避免分享报告触发写入、联网、登录、重复 Agent 探针或隐式自动修复 | 2026-08-24 |
| CLI help 使用 ASCII 并关闭 Rich Unicode 格式 | 兼容严格 cp1252 的 Windows 旧代码页控制台；不改变实际报告和中文文档 | 2026-08-24 |
| project-doctor 使用固定第一层 marker 和独立 v1 报告 | 在不读项目内容、不递归、不改变既有 scan/support/snapshot schema 的前提下推导本地工具链 | 2026-08-24 |
| snapshot 写入使用有界 `O_EXCL` 临时文件 | Codex 工作区拒绝写入时必须快速返回；只对名称碰撞重试，避免 `NamedTemporaryFile` 的不可控等待，不扫描目录或引入哈希 | 2026-08-24 |
| `command-doctor` 使用独立 v1 和共享 launcher probe | 单命令诊断需要严格输入、固定 `--version` 和有限的 PowerShell 辅助事实，同时不改变既有 scan/agent schema 或引入网络/写入操作 | 2026-08-24 |
| 主路线收敛为 Windows host/Agent 执行上下文差异诊断 | 同类项目已覆盖配置修复和通用 Windows 排障；本项目最稀缺、最可验证的能力是双端独立采样和差分，而不是更多 doctor 数量 | 2026-08-27 |
| 0.1.0 发布后暂缓功能扩展 | 在没有外部采用证据前继续堆叠探针会扩大维护面；先通过公开发布、分享和真实反馈观察采用信号 | 2026-08-29 |
| 外部验证不可得时不冒充采用验证 | 可使用公开问题、首组案例和本地/CI证据支撑需求判断，但不能把它们写成外部用户验证 | 2026-08-29 |
| Star 观察只允许一次定位/演示调整 | 发布和至少两次相关分享后 14 天仍有访问/克隆但无 Star 时，先做一次有限展示调整，再决定是否恢复开发 | 2026-08-29 |

## 验证证据

| 日期 | 验证内容 | 命令或步骤 | 结果 |
| --- | --- | --- | --- |
| 2026-08-24 | 运行时 | `python --version` | Python 3.12.7 |
| 2026-08-24 | Python Launcher | `py -0p` | 已可用；当前登记 Python 3.12.7，尚无 3.14 |
| 2026-08-24 | 单元、场景和 CLI 端到端测试 | `python -B -m pytest -q -p no:cacheprovider` | 42 passed |
| 2026-08-24 | 静态检查 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | 真实 Windows 注册表和 CLI | `python -B -c "from win_agent_preflight.windows import collect_registry_path_facts; print(collect_registry_path_facts())"`、`python -B -m win_agent_preflight scan --json --pretty --timeout 2` | HKLM/HKCU 读取完整；CLI 退出 0，JSON 可解析，10 pass、3 warning、0 fail、0 unknown；未写入注册表 |
| 2026-08-24 | 完整测试 | `python -B -m pytest -q -p no:cacheprovider` | 75 passed；其中 workspace-probe 27 项，覆盖身份变化、输入零写、步骤失败、未知残留、异常和 CLI 退出码 |
| 2026-08-24 | workspace-probe 静态检查 | `python -m ruff check src tests --no-cache` | All checks passed |
| 2026-08-24 | workspace-probe 真实验收 | `python -B -m win_agent_preflight workspace-probe --target $env:TEMP --allow-write --json --pretty` | 退出 0；六项 pass；`successful=true`；`residual_paths=[]`；无 `.agent-preflight-probe-*` 残留 |
| 2026-08-24 | Codex 项目根诊断 | `python -B -m win_agent_preflight workspace-probe --target . --allow-write --json --pretty` | 退出 1；创建目录 WinError 5；1 pass、1 fail、4 unknown；`residual_paths=[]`，未产生探针残留 |
| 2026-08-24 | 第五里程碑配置检查 | `.github/workflows/ci.yml`、`docs/release-check.md`、`pyproject.toml` 和项目状态文档已更新 | 已写入 Windows-only CI、3.12/3.14 矩阵、包验收和本地恢复说明；旧 HEAD `9259a4d` 已推送，首次 run 的实际失败记录见下方 |
| 2026-08-24 | 标准打包工具 | `python -m pip install -e ".[dev]"`、`python -m build --version` | 安装成功；build 1.5.0 |
| 2026-08-24 | 本地双制品构建 | `python -m build --sdist --wheel` | 默认隔离构建成功生成 `win_agent_preflight-0.1.0.tar.gz` 与 `win_agent_preflight-0.1.0-py3-none-any.whl`，各 1 个 |
| 2026-08-24 | 干净环境安装 | 在 `.artifacts\\sdist-check` 与 `.artifacts\\wheel-check` 分别安装制品并运行 `python -m win_agent_preflight --help` | 两个环境均退出 0 |
| 2026-08-24 | 第六里程碑专项测试 | `python -B -m pytest tests/test_agent_doctor.py tests/test_cli.py tests/test_runner.py -q -p no:cacheprovider` | Agent Doctor 场景与 CLI/Runner 回归测试通过 |
| 2026-08-24 | 第六里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 96 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | Agent Doctor 真实 CLI | `python -B -m win_agent_preflight agent-doctor --json --pretty` | 退出 1；Codex WindowsApps launcher 为 `access_denied`（WinError 5），Claude/DSH 为 `command_not_found`；未回显 stdout/stderr |
| 2026-08-24 | 第七里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 104 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | Support Report 真实 CLI | `python -B -m win_agent_preflight support-report --json --pretty --timeout 1` | 退出 0；JSON 可解析；`offline=true`、`workspace_probe_run=false`；多候选回退由 Agent Doctor 负责，scan 不重复探测三个 Agent（候选调用由测试验证） |
| 2026-08-24 | 第七里程碑制品复验 | 当前进程设 `PYTHONUTF8=1` 后默认隔离构建，并在 `.artifacts\\m7-sdist`、`.artifacts\\m7-wheel` 安装两个制品 | sdist/wheel 均包含 `support_report.py`；两个全新 Python 3.12 环境的 `support-report --help` 均退出 0；首次沙箱构建的真实阻塞为 PyPI 网络权限，不是源码或构建后端错误 |
| 2026-08-24 | 第八里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 113 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | SupportReport v2 真实 CLI | `python -B -m win_agent_preflight support-report --json --pretty --timeout 1` | 退出 0；顶层 `schema_version=2`、`kind=support_report`；内嵌 scan/Agent Doctor 为 v1；`offline=true`、`workspace_probe_run=false`；本次推导 1 项 next check |
| 2026-08-24 | CLI help cp1252 smoke | `python -B -m pytest tests/test_cli_help.py -q -p no:cacheprovider` | 根命令和全部子命令在严格 cp1252 子进程中均退出 0；stdout/stderr 严格解码；临时工作目录无文件 |
| 2026-08-24 | cp1252 修复全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 114 passed；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | 首次 GitHub Windows CI | [run 32691934171](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32691934171) | Python 3.12/3.14 安装与 pytest 通过，3.12 Ruff 通过；两个矩阵 job 均在根 `--help` 的 cp1252 `UnicodeEncodeError` 失败；package job 因 `needs: test` 跳过，远程 sdist/wheel 未验证 |
| 2026-08-24 | cp1252 修复后 GitHub Windows CI | [run 32693383743](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32693383743) | Python 3.12/3.14 测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | project-doctor GitHub Windows CI | [run 32696172691](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32696172691) | Python 3.12/3.14 的 145 项测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | snapshot 修复前一轮 main CI | [run 32696504545](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32696504545) | 当时已推送内容的 Python 3.12/3.14 测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建和干净环境安装全部通过；不包含后续 snapshot 修复 |
| 2026-08-24 | snapshot 修复 GitHub Windows CI | [run 32699112641](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32699112641) | Python 3.12/3.14 的 158 项测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | Codex 上下文快照 | `%TEMP%\win-agent-preflight\context-run-01\codex.json` | snapshot 退出 0；`load_snapshot` 返回 label `codex`、cwd 为本仓库、schema v1；用户目录明文未出现；临时残留 0；自比较退出 0 |
| 2026-08-24 | project-doctor 定向测试 | `python -B -m pytest tests/test_project_doctor.py tests/test_cli.py tests/test_cli_help.py -ra -p no:cacheprovider` | 41 passed；覆盖 marker 组合/锁文件去重/冲突/孤立、ignored marker、marker 异常累计、第一层边界、reparse/symlink/非普通项、无内容读取、工具调用/required_by 和 CLI 退出语义 |
| 2026-08-24 | project-doctor 全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 145 passed；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | project-doctor 真实仓库根 | `python -B -m win_agent_preflight project-doctor --target . --json --pretty --timeout 1` | 退出 0；`project.markers` 与 `project.python` 均 pass；仅推导并探测 python；未写入文件 |
| 2026-08-24 | snapshot/CLI 定向回归 | `python -B -m pytest tests/test_snapshot.py tests/test_cli.py -q -p no:cacheprovider` | 28 passed；覆盖权限首错单次失败、三次名称碰撞、碰撞后成功、竞争输出保留、write/fsync/replace/fdopen 失败清理和 CLI 退出 2 |
| 2026-08-24 | snapshot 静态检查 | `python -m ruff check src/win_agent_preflight/snapshot.py tests/test_snapshot.py tests/test_cli.py --no-cache` | All checks passed |
| 2026-08-24 | snapshot P1/P2 全量回归 | `python -B -m pytest -ra -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 158 passed；父路径为普通文件时 force/non-force 均为 `cannot write snapshot`，link 竞争仍保留 `output already exists`，主失败叠加 cleanup 失败及 non-force 提交后删除失败均保留残留并报告；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | command-doctor 定向回归 | `python -B -m pytest tests/test_command_doctor.py tests/test_windows.py tests/test_cli.py tests/test_cli_help.py -ra -p no:cacheprovider` | 82 passed；覆盖严格输入零 Runner、非 Windows 零 facts/Runner、PATHEXT 顺序和候选回退、五态/WinError/timeout/空输出、PowerShell 裸命令和显式扩展检查、direct + bare 恰好两次同 timeout、JSON/Console/退出码/cp1252 help |
| 2026-08-24 | command-doctor 全量与静态检查 | `python -B -m pytest -ra -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 200 passed；Ruff 和 diff check 通过 |
| 2026-08-24 | command-doctor 首次维护环境 CLI | `python -B -m win_agent_preflight command-doctor npm/npm.cmd/pnpm --json --pretty --timeout 1` | 三个命令均退出 0；npm `11.17.0`、npm.cmd `11.17.0`、pnpm `11.22.0`；均为 `usable` 且 `windows.path_refresh=pass`，pnpm 报告主安装与 fallback 候选，未写文件 |
| 2026-08-24 | command-doctor GitHub Windows CI | [run 32703174150](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32703174150) | Python 3.12/3.14 的 200 项测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | git-doctor 定向回归 | `python -B -m pytest tests/test_git_doctor.py tests/test_cli_help.py -ra -p no:cacheprovider`、`python -m ruff check src/win_agent_preflight/git_doctor.py tests/test_git_doctor.py --no-cache`、`git diff --check` | 38 passed（Git Doctor 37 项，CLI help 1 项）；固定 Git/gh 命令白名单、身份/remote/helper 脱敏、失败/超时、输入边界、JSON/Console/退出码通过 |
| 2026-08-24 | git-doctor GitHub Windows CI | [run 32708225452](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32708225452) | 提交 `67697c7` 的 Python 3.12/3.14 全量 237 项测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | git-doctor 真实仓库根 | `python -B -m win_agent_preflight git-doctor --target . --json --pretty --timeout 1` | 退出 0；`local_ready=true`，6 pass、`github.auth` 为固定 `unknown/not_checked_offline`；无文件写入，未执行认证或网络命令 |
| 2026-08-24 | workspace-scope 定向回归 | `python -B -m pytest tests/test_workspace_scope.py tests/test_cli_help.py -q -p no:cacheprovider` | workspace-scope 24 项 + CLI help 1 项，共 25 passed；覆盖四种状态、纯 unknown 归约、预验证零 probe 调用、顺序/次数、异常/中断 partial、脱敏、CLI JSON/Console/退出码和 cp1252 help |
| 2026-08-24 | workspace-scope 全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 提交前本地验证 261 passed；Ruff 通过；diff check 无内容错误 |
| 2026-08-24 | workspace-scope 真实项目矩阵 | 分别以 Evolutionary Triton Optimizer、MyMineCraft、MCP Interop Lab 为 `--target`，以 `%TEMP%` 为 `--control` | Triton 与 control 均六项通过，状态 `both_usable`、退出 0；MyMineCraft/MCP Lab 均在 target 创建目录时返回 WinError 5，control 六项通过，状态 `target_specific_failure`、退出 1；四个目录探针残留均为 0 |
| 2026-08-24 | workspace-scope GitHub Windows CI | [run 32712146556](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32712146556) | 提交 `b981bf1` 的 Python 3.12/3.14 全量 261 项测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-27 | 公开文档受众审阅 | 全量测试、Ruff、diff check、真实 `support-report`、本地 Markdown 链接、敏感文本与对话式身份关键词检查 | 261 项测试、Ruff、diff check 和真实 CLI 通过；本地链接、敏感文本与受众关键词检查均通过；运行时代码未修改 |

## 暂停检查点

- 当前分支：`main`。
- 最近已验证远程功能基线：`workspace-scope` `b981bf1`，已推送并通过 Windows CI run `32712146556`。
- 不能丢失的本地数据：`src/`、`tests/`、`docs/`、`pyproject.toml`、本文件。
- 临时假设：当前只针对 Windows；Linux/macOS 只允许导出 `unknown` 或明确的非 Windows 提示。
- 恢复时第一步：进入项目根目录，运行 `python -B -m pytest -q -p no:cacheprovider`，再查看 `docs/PROGRESS.md` 的最近验证。
- 恢复/验证命令：`python -B -m pytest -q -p no:cacheprovider`；`python -m ruff check . --no-cache`；`py -3.12 -m build --sdist --wheel`；`agent-preflight scan --json`；`agent-preflight agent-doctor --json --pretty`；`agent-preflight support-report --json --pretty --timeout 1`；`agent-preflight workspace-probe --target . --allow-write --json --pretty`；`agent-preflight snapshot --label host --output .\\snapshots\\host.json --pretty`；PowerShell 中设置 `$env:PYTHONIOENCODING=\"cp1252:strict\"` 后运行 `python -B -m win_agent_preflight --help`。

## 已知限制和后续

- 2026-08-27 已完成首组 host ↔ Codex 成对 snapshot/compare；Claude/DSH 尚未形成同类案例，单次案例仍不能外推为其他 Agent 或机器的权限结论。
- Windows CI `32703174150` 已确认包括 `command-doctor`、snapshot 修复和 project-doctor 在内的 Python 3.12/3.14 矩阵及远程 sdist/wheel 安装验收通过；首次维护环境只直接验证了 Python 3.12.7。
- `project-doctor` 只检查固定第一层十个 basename，marker 语义不等同于构建系统完整识别；冲突、孤立 lockfile、yarn/bun lockfile 和 marker lstat 异常会保守返回 `unknown`，未列入固定表的文件会忽略。它不读取 marker 内容、不递归、不以 target 作为工具 cwd。
- `agent-doctor` 只描述当前进程这一次 PATH/launcher 探测上下文；同一 Agent 可能依次尝试多个候选；`usable` 不等于账号登录、网络或 Agent 沙箱权限可用。
- WindowsApps alias 或 lstat 受限会保守报告为 `access_denied`/结构化不可用状态，不把它当作命令缺失；其他进程或权限变化可能使后续启动结果不同。
- `agent-doctor` 不保存或回显 stdout/stderr 原文；成功结果仅保存经脱敏且最多 200 字符的第一条非空版本行，失败结果不保存版本文本。
- `support-report` 只表示一次当前进程的本地组合采集；`complete=true` 表示采集流程完成，不表示所有命令或 Agent 健康。
- `support-report` 的 scan 仍包含既有诊断证据和脱敏候选路径；分享前应使用 Console 提醒复核公开边界，不把它当成安全审计或完整环境导出。
- `npm.ps1` 的阻止判断来自实际 Runner 结果和 PowerShell 事实，不会修改执行策略。
- `command-doctor` 只描述单次 Windows PATH/launcher 上下文；无扩展名会追加 `.ps1` 并按需读取执行策略，显式 `.cmd`/`.exe` 不执行裸命令检查；`usable` 不等于登录、网络或 Agent 沙箱可用。
- 注册表 PATH 只读采集已实现；非 Windows 平台、读取异常、类型错误或未解析变量返回 `unknown`，但另一 scope 已证明缺失时返回 `warning`。
- 命令发现遇到不可访问的 PATH 候选会跳过并继续扫描；当前不会把该情况细分为“不可访问候选”，只在后续版本增加精确分类。
- `workspace-probe` 不代表整个 Agent 或系统权限；它只验证一次运行上下文对一个现有普通目录的最小文件操作。目标目录中的未知残留不会自动删除，需由目录操作者检查和处理。
- 对象身份检查可以拒绝复核前发生的同名替换，但路径级删除仍存在身份复核与系统调用之间的 TOCTOU 窗口；首版定位为非对抗本地诊断，不承诺抵御恶意并发替换。

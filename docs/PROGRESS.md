# 项目进程

## 当前快照

- 当前阶段：`workspace-scope` 提交 `b981bf1` 已推送并通过 Windows CI `32712146556`；本轮按用户要求停止扩展，双端采集协议等待用户在普通 PowerShell 生成 host 快照。
- 完成度：首阶段 `scan` 保持稳定；EnvironmentSnapshot v1、`snapshot` 写出、`compare` 规范化差异、窄解析、CLI 退出码、只读注册表 PATH 刷新诊断、独立 `workspace-probe`、Agent Doctor、Command Doctor、Support Report、project-doctor 和 CI/构建入口已实现。
- 最近验证：`workspace-scope` 24 项加 CLI help 1 项（定向命令共 25 passed）、全量回归 261 项、Ruff、diff check 和真实三项目矩阵已通过；Windows CI `32712146556` 的 Python 3.12/3.14、严格帮助检查、workspace probe、sdist/wheel 双安装和制品上传也已通过。
- 未完成项：用户在普通 PowerShell 生成 `context-run-02\host.json`，与已验证的同轮 Codex 快照完成严格比较。
- 2026-08-27 路线复审完成：定位收敛为 Windows host/Agent 执行上下文差异诊断；不再以增加 doctor 数量为进度指标。
- 下一步：用户按 `docs/context-comparison.md` 在普通 PowerShell 以 `--timeout 2` 采集 `context-run-02\host.json`；恢复任务后由 Agent 运行严格 host ↔ Codex `compare`、形成脱敏案例并收敛首选入口。GitHub CLI 已认证，无需再次认证。

本机建议安装环境（基于当前验证）：

- 必须：Python 3.12.7（已实际验证）和本项目开发依赖；Git 用于后续提交和版本回滚。
- 明显提效：本机若尚未安装可并行安装 Python 3.14；Python Launcher 已可用，可用 `py -3.12`/`py -3.14` 选择解释器；GitHub CLI 已认证并可用于仓库工作流；PowerShell 7 已可用。
- 暂不需要：Node.js、WSL、Docker、数据库、GUI 和额外 Agent CLI；当前测试、探针和打包路径不依赖它们。

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

状态：完成，已随公开仓库旧 HEAD `9259a4d` 推送

- [x] `RegistryPathFacts` 使用不可变字段保存 HKLM/HKCU PATH、变量值和 scope 完整性。
- [x] 默认 reader 只读两个环境注册表键；缺失键/值为空且完整，异常/`Path` 非字符串为不完整。
- [x] `user_path` 注入继续优先于用户 registry 值，`scan_environment`/`capture_snapshot` 可透传 reader。
- [x] 机器 PATH 按 HKLM→process、用户 PATH 按 HKCU→HKLM→process 展开 `%NAME%`，最多 8 轮。
- [x] Windows `ntpath` 规范化比较；来源进入 evidence，details 仅保留 `missing_count`。
- [x] 13+ 个 registry/刷新场景测试，刷新检查永不返回 `fail`。

## 阶段 4：一次性 workspace-probe

状态：完成并通过独立审阅，已提交 `623ef26`，已随 `9259a4d` 推送

- [x] 新增独立 WorkspaceProbeReport v1，固定六项 workspace.* 检查顺序，并校验 successful 与状态/残留一致。
- [x] CLI 要求 --target PATH --allow-write；输入拒绝 2，能力失败/残留 1，成功 0，Ctrl-C 130。
- [x] 仅 Windows；写入前验证目标普通目录、非重解析点和 strict resolve。
- [x] 只在目标直接子目录创建 .agent-preflight-probe-<uuid>，独占写 before.txt，重命名为 after.txt，再删除并清理空目录。
- [x] 记录探针目录和文件的 Windows 对象身份；身份不可用或复核前变化时保守拒绝，预存或外部出现的 after.txt 不按存在性删除，只作为相对残留报告。
- [x] 注入式 WorkspaceOperations 覆盖各步骤失败、读不一致、未知内容、重解析点、中断和 cleanup unexpected exception；unexpected exception 保留报告后继续抛出。
- [x] 清理不遍历目标、不使用 shutil.rmtree、不处理历史残留；residual_paths 仅相对路径。

本阶段诊断过的环境事实：Codex 线程工作区对项目目录执行写入时曾出现 Windows 拒绝访问，不能把该失败误判成项目代码故障；同一机器对 %TEMP% 运行六项 probe 全部通过且零残留。

结论边界：probe 只说明“该次命令进程对该目标目录的最小文件生命周期能力”，不说明整个 Agent、系统 ACL 或其他上下文权限。它不抵御其他进程在身份复核与紧随其后的路径删除之间刻意替换同名对象；首版不建设 Win32 句柄级安全删除。

## 阶段 5：Windows CI 与包验收

状态：本地验收与独立审阅完成，已提交 `c936e3d`；修复后远程 CI 与 package job 已全部通过

- [x] 新增 Windows-only CI：Python 3.12/3.14 测试矩阵、3.12 Ruff、CLI 帮助和 `RUNNER_TEMP` workspace-probe。
- [x] 测试全部通过后在 Python 3.12 构建一个 sdist 与一个 wheel，并在两个干净虚拟环境分别安装启动。
- [x] 非 PR 运行上传 7 天制品；不启用缓存、自动发布、签名、SBOM 或跨平台矩阵。
- [x] 本机 Python 3.12.7 安装 `build 1.5.0`，完成两个制品的真实构建和安装验收。
- [x] 首次 GitHub CI run `32691934171` 已验证 Python 3.12/3.14 安装与 pytest，以及 Python 3.12 Ruff；两个矩阵 job 在根 `--help` 的 cp1252 `UnicodeEncodeError` 失败。
- [x] 修复后两个矩阵 job 与 package job 已通过；sdist/wheel 均在干净环境安装并运行严格 cp1252 根帮助。

本阶段结论：Git、PowerShell 7、Python 3.12.7、Python Launcher 和项目依赖已足够完成本地研发与打包；本机若尚未安装可并行安装 Python 3.14，GitHub CLI 已认证。Windows CI 已完整验证 3.12/3.14、严格 cp1252 help 与 package job。Node.js、Docker、WSL、数据库和 `act` 当前没有必要。

## 阶段 6：Agent Doctor 最小版本探针

状态：实现、全量测试和真实 CLI 完成，已提交 `f7e3503`，已随 `9259a4d` 推送

- [x] 新增独立 `AgentDoctorReport v1`，固定 `codex`、`claude`、`dsh` 顺序；重复 `--agent` 去重，未知输入退出 2。
- [x] 对 PATH 中已通过 lstat 解析的 `.exe`、`.cmd`、`.bat`、`.ps1` 普通 launcher 按顺序探测；同一 Agent 可多候选回退，每个候选经 Runner 最多执行一次 `--version`。
- [x] 覆盖 `command_not_found`、`resolved_but_not_executable`、`access_denied`、`version_probe_failed`、`usable` 五种状态；全部未安装退出 0，已解析但不可用退出 1。
- [x] Runner OSError 增加 `error_type`/`winerror`；WindowsApps alias/lstat 异常保留结构化证据，不降级为缺失。
- [x] 失败报告不回显 stdout/stderr，路径按 `%USERPROFILE%` 脱敏；不调用 login、doctor、npx、网页或网络流程。
- [x] `usable` 要求 `--version` 退出 0 且 stdout/stderr 存在非空文本；成功只保存脱敏后的第一条非空版本行（最多 200 字符），空输出为 `version_probe_failed`。
- [x] 报告固定包含 `kind=agent_doctor`、`offline=true`；WinError 1920 纳入 `access_denied` 优先级，并覆盖多个候选的失败分类。
- [x] 全量 pytest（96 项）、Ruff 和真实 `agent-doctor --json` CLI 已完成；该命令只代表一次当前进程 PATH/权限上下文。

## 阶段 7：Support Report 离线组合报告

状态：实现、全量测试和真实 JSON 完成，已提交

- [x] 新增独立 `SupportReport v1`，固定 `kind=support_report`、`generated_at`、有限 environment、collection、scan、agent_doctor 和 errors 字段。
- [x] `support-report` 共享同一个 Runner/env/timeout，先执行 Agent Doctor，再将 `codex`、`claude`、`dsh` 最终结果作为预计算 `CheckResult` 注入 scan；多候选回退由 Agent Doctor 完成，每个已发现候选最多一次，scan 不再重复探测三个 Agent。
- [x] 默认 Console、`--json`/`--pretty` 输出；不提供 `--output`；Console 复用 scan/Agent Doctor renderer 并给出分享前边界提醒。
- [x] 离线只读边界：不运行 workspace-probe、login、doctor、npx、web、网络或写文件；不提供行动建议。
- [x] 健康异常保持退出 0；部分采集异常保留另一部分结果、记录脱敏截断错误并退出 1；输入错误退出 2。
- [x] 全量 pytest（104 项）、Ruff、diff check 和真实 `support-report --json --pretty --timeout 1` 完成。

## 阶段 8：SupportReport v2 next_checks

状态：实现、全量测试、独立复审和提交完成，已随 `9259a4d` 推送

- [x] 外层 SupportReport schema 升为 v2，固定保留 v1 采集字段；内嵌 scan/Agent Doctor 仍为 v1，不维护双版本 flag。
- [x] 新增不可变 `NextCheck` 与纯 `derive_next_checks(scan, doctor)`；不运行命令、不读取环境、不解析自由文本。
- [x] 仅允许 Agent `access_denied`/`version_probe_failed`、PowerShell 裸 npm warning、PATH refresh warning/unknown 触发；明确忽略缺失、不可执行、可用和注入的 Agent scan checks。
- [x] 固定优先级、codex/claude/dsh 顺序和 `(code, target)` 去重；Console 显示 next checks 或 `Next checks: none.`。
- [x] 覆盖所有触发、不触发、去重、summary/evidence 无关性、纯函数零调用、v2/子报告 schema、JSON 和 Console。
- [x] 全量 pytest（113 项）、Ruff、diff check 和真实 `support-report --json --pretty --timeout 1` 完成；JSON 顶层 schema 为 2，子报告仍为 v1。

## 阶段 9：CLI help 的 cp1252 兼容

状态：完成，已提交 `affa4a3` 并通过远程 CI

- [x] 所有 Typer 公开 help/docstring 改为纯 ASCII；实际报告输出和中文文档保持原约定。
- [x] 关闭 Rich Unicode 帮助边框，避免严格 cp1252 控制台在子命令 help 上解码失败。
- [x] 新增真实 subprocess smoke test：根命令和全部子命令在 `PYTHONIOENCODING=cp1252:strict` 下严格解码、退出 0，且不触发操作或在临时目录写文件。
- [x] CI 根命令及 sdist/wheel 安装后的 help smoke 显式设置 `PYTHONIOENCODING=cp1252:strict`；发布复验文档同步。
- [x] 全量回归 114 项测试、Ruff 和 diff check 已通过；本地修复未改变报告输出。
- [x] GitHub Windows runner 已确认 Python 3.12/3.14 的 cp1252 help smoke，后续 package job 已完成两个制品的干净环境安装验收。

## 阶段 10：project-doctor 第一层项目工具诊断

状态：完成，已提交 `4b12475` 并通过远程 CI

- [x] 新增独立 `ProjectDoctorReport v1`，固定工具顺序为 python、node、npm、pnpm、cmake；不改变 scan/support/snapshot schema。
- [x] 仅接受显式 `--target`；target 拒绝 symlink、reparse point、非普通项；marker 异常累计为脱敏 unknown 并继续扫描；不 glob、不递归、不打开 marker 内容。
- [x] 仅检查十个固定 basename：`pyproject.toml`/`requirements.txt` 推导 python；`package.json` 推导 node，npm/pnpm lockfile 分别推导对应工具；npm+pnpm 冲突只推导 node 并标记 unknown；孤立/yarn/bun lockfile 标记 unknown，未列入固定表的项目文件忽略；`CMakeLists.txt` 推导 cmake。
- [x] 仅对推导工具通过现有 Runner 执行 `--version`，不把 target 作为 cwd；必需工具缺失、超时或启动失败为 fail，路径和异常脱敏。
- [x] 报告 checks 固定以 `project.markers` 开头，再按工具顺序排列；覆盖 marker 组合、npm-shrinkwrap/锁文件去重、冲突、孤立、ignored marker、PermissionError/OSError、reparse/symlink/非普通项、固定顺序、边界/不递归、无内容读取、工具调用/required_by、脱敏、JSON/Console、退出码和 cp1252 help。
- [x] 真实仓库根 `project-doctor --target . --json --pretty --timeout 1` 退出 0，识别 `pyproject.toml` 并仅探测 python，工作区无变化。
- [x] Windows CI run `32696172691` 已验证 project-doctor、既有回归和 package job。

## 阶段 11：snapshot 写入快速失败

状态：设计、实现、独立复审、本地边界验证、提交推送和远程 CI 均已完成。

- [x] 删除 `tempfile.NamedTemporaryFile`，改用目标父目录内最多三个 UUID 临时名和单次 `os.open(O_WRONLY|O_CREAT|O_EXCL|O_BINARY, 0o600)`。
- [x] 只对 `FileExistsError` 重试；`PermissionError`/其他 `OSError` 第一次即转为 `SnapshotError`，避免拒绝写入目录中无界等待或高 CPU。
- [x] 保持 UTF-8、`newline="\n"`、write/flush/fsync，以及 force 的 replace、非 force 的 link 后 unlink 语义；fdopen 构造失败防止文件描述符泄漏。
- [x] 所有已知失败只清理本次成功创建的临时文件，不扫描目录、不处理历史残留；测试覆盖权限首错、三次碰撞、碰撞后成功、竞争输出、write/fsync/replace/fdopen 失败和 CLI 退出 2。
- [x] 提交 `4b8d16d` 已推送，main CI run `32699112641` 的 Python 3.12/3.14 测试与包验收全部通过。

## 阶段 12：Host/Agent 双端采集协议

状态：`context-run-01` 初步比较完成；`context-run-02` Codex 端证据已完成，等待同轮 host 端手动触发。

- [x] 新增 `docs/context-comparison.md`，固定同机、同 cwd、同轮 `%TEMP%` 证据目录和逐对比较流程。
- [x] 明确只有进入真实 Agent 上下文必须由用户完成；不新增 `capture-pair`、PowerShell 包装或外部 Agent 控制。
- [x] 当前 Codex 已生成 `context-run-01\codex.json`：写出和重新加载成功，label/cwd/schema 正确，用户目录明文未出现，临时残留为 0，自比较退出 0。
- [x] 用户已生成 `context-run-01\host.json` 并完成初步 compare：共 8 项差异；因两端相隔三天且宿主 `--timeout 1` 导致 pnpm 冷启动超时，该轮不升级为严格公开案例。
- [x] 当前 Codex 已用 `--timeout 2` 生成 `context-run-02\codex.json`：label/cwd/schema 正确，用户名、常见 token/key 和邮箱模式命中为 0，自比较退出 0。
- [ ] 用户在宿主 PowerShell 以相同 `--timeout 2` 生成 `context-run-02\host.json`，完成严格 host ↔ Codex 比较；Claude/DSH 未安装或不可用时明确记录未采集。

## 阶段 13：command-doctor 单命令诊断

状态：设计、实现、审阅修复、本地回归、提交推送和远程 Windows CI 均已完成。

- [x] 新增独立 `CommandDoctorReport v1` 与 `command-doctor NAME --json/--pretty/--timeout`；固定 `kind=command_doctor`、`offline=true`、五态、路径/版本/attempts/details/checks 字段。
- [x] 输入只允许 1–128 字符 ASCII 安全 basename，显式扩展仅 `.exe`/`.cmd`/`.bat`/`.ps1`；非法输入和非 Windows 平台在任何 discovery、registry 或 Runner 调用前退出 2。
- [x] 新增共享 `launcher_probe`，Agent Doctor 映射回原 v1 字段；候选按 PATHEXT 相对顺序探测 `.exe`/`.cmd`/`.bat` 并追加 `.ps1`，每候选最多一次固定 `--version`，首个有非空版本输出且退出 0 的候选停止。
- [x] 无扩展名追加一次只读 PowerShell 裸命令检查；显式 `.ps1` 或无扩展名发现 `.ps1` 时采集只读执行策略；始终采集只读 `windows.path_refresh`，刷新 warning/unknown 不否定已可用显式 launcher。
- [x] 失败不保存 launcher stdout/stderr；成功只保存脱敏、最多 200 字符的首条非空版本行；PowerShell 裸命令成功证据同样只保留首行并脱敏截断。
- [x] 测试覆盖候选顺序/回退、空输出/超时/WinError、显式扩展边界、npm bare warning、pnpm 缺失与 refresh 独立性、非 Windows 零 Runner/facts、CLI JSON/Console/0/1/2 和 cp1252 help。
- [x] 本机真实命令：`npm`、`npm.cmd`、`pnpm` 均退出 0、状态 `usable`、`windows.path_refresh=pass`；npm 为 11.17.0，pnpm 为 11.22.0，pnpm 记录主安装与 fallback 候选。
- [x] 提交 `a311f96` 已推送，Windows CI run `32703174150` 的 3.12/3.14、cp1252、sdist/wheel 干净环境验收全部通过。

## 阶段 14：git-doctor 离线本地 Git 诊断

状态：完成；提交 `67697c7` 已推送并通过远程 Windows CI `32708225452`。

- [x] 新增独立 `GitDoctorReport v1` 与 `git-doctor --target PATH --json/--pretty/--timeout`；固定 `kind=git_doctor`、`offline=true`、`remote_auth_verified=false`、七项 checks 和本地 readiness 语义。
- [x] 只通过同一 Runner/env/timeout 执行 Git launcher `--version`、`git -C TARGET` 的 worktree、identity、origin 和 helper 查询；仅安全分类为 GitHub remote 时执行 `gh --version`。
- [x] 明确不运行 `gh auth`、credential fill、GCM diagnose、push/fetch/pull/ls-remote/ssh，不联网、不读取 token、配置原值或 helper 原文，不写文件。
- [x] 覆盖 HTTPS GitHub、SCP-like/SSH GitHub、other/local remote、fetch/push 差异、embedded userinfo、GCM/其他/无 helper、身份缺失/空值/scope、launcher 缺失/失败/超时、非 repo、目标边界、脱敏、JSON/Console/退出码；报告不回显 sentinel。
- [x] `python -B -m pytest tests/test_git_doctor.py tests/test_cli_help.py -ra -p no:cacheprovider`：38 passed（Git Doctor 37 项，CLI help 1 项）；`python -m ruff check src/win_agent_preflight/git_doctor.py tests/test_git_doctor.py --no-cache`：通过；`git diff --check`：无内容错误。
- [x] 全量 `python -B -m pytest -ra -p no:cacheprovider`：237 passed；全量 `ruff check . --no-cache` 通过；`git diff --check` 无内容错误（仅 CRLF 转换提示）。
- [x] 真实仓库根 `python -B -m win_agent_preflight git-doctor --target . --json --pretty --timeout 1`：退出 0；`local_ready=true`，6 pass、`github.auth` 固定 unknown/not_checked_offline；无文件写入、无认证或网络调用。
- [x] Windows CI `32708225452` 的 Python 3.12/3.14、237 项测试、严格帮助检查、workspace probe、Ruff、sdist/wheel 双安装和制品上传全部通过。

## 阶段 15：workspace-scope 双目录能力比较

状态：完成；提交 `b981bf1` 已推送并通过远程 Windows CI `32712146556`。

- [x] 新增独立 `WorkspaceScopeReport v1` 与 `workspace-scope --target TARGET --control CONTROL --allow-write`；不修改既有 `WorkspaceProbeReport v1`。
- [x] 两个目录先完成 lstat、重解析点、普通目录和 strict resolve 预验证；任一输入失败在零 probe/零写入前退出 2。
- [x] 预验证成功后严格 target → control 各调用一次既有 probe；普通失败继续 control；子报告归约为 usable、failed（FAIL 或 residual）或 unknown，任一 unknown 使完整报告为 `inconclusive`。
- [x] 非预期异常或 Ctrl-C 保留已取得子报告为 `inconclusive` partial，顶层 `complete=false`，不调用后续 probe；正常返回的 unknown 报告允许 `inconclusive` 且 `complete=true`；Console/JSON/退出码和严格 cp1252 help 已覆盖。
- [x] `tests/test_workspace_scope.py`：24 passed；加 CLI help 1 项的定向命令共 25 passed；全量 `python -B -m pytest -p no:cacheprovider -ra`：261 passed；Ruff 和 `git diff --check` 通过。
- [x] 真实项目矩阵：Triton target + `%TEMP%` control 为 `both_usable`；MyMineCraft/MCP Lab target + `%TEMP%` control 为 `target_specific_failure`；四个目录探针残留均为 0。
- [x] Windows CI `32712146556` 的 Python 3.12/3.14、261 项测试、严格帮助检查、workspace probe、Ruff、sdist/wheel 双安装和制品上传全部通过。

## 阶段 16：项目路线与重合度复审

状态：文档路线已于 2026-08-27 更新；未修改运行时代码。

- [x] 复审 Agent Doctor、Windows Claude Code Doctor、Argus Agent、APM Doctor、NVIDIA Agent Doctor 和生态型 doctor 工具，确认存在组件级重合但未发现成熟的“Windows host ↔ Coding Agent 独立采样与差分”完全替代品。
- [x] 结合 Codex/Claude Code 的 PATH 未继承、Access Denied、WindowsApps launcher 和 Shell 差异公开问题，确认需求真实；同时记录项目当前尚无用户采用证据，不能把功能完成度等同于市场验证。
- [x] 路线收敛为：真实成对案例 → 首选入口/紧凑输出 → 3–5 名外部用户验证 → 至多一个证据驱动的新切片。
- [x] 明确排除自动修复、Agent 配置治理、GUI/团队控制面和没有用户证据的通用 Windows 全科诊断。
- [ ] 等待用户采集 host 快照，完成阶段 12 的首组真实比较。

## 暂停检查点

- 当前阶段：路线与重合度复审已完成；现有实现保持不变，等待 host 快照，不继续增加推测性功能。
- 最近验证：Workspace Scope 24 项 + CLI help 1 项（共 25 passed）、全量回归 261 项、Ruff、diff check、真实项目矩阵和 Windows CI `32712146556` 均通过。
- 未完成项：用户生成 `context-run-02\host.json`，与已生成的同轮 Codex 快照完成严格 compare。
- 下一步：用户在普通 PowerShell 使用 `--timeout 2` 采集 host 快照；恢复任务后由 Agent 执行 compare。GitHub CLI 已认证，无需再次认证。
- 后续先完成真实案例和用户验证；只有真实 compare、至少两名用户重复反馈或实际项目必要缺口才设计新功能。当前不建设自动修复、Agent 配置治理、ACL 深挖、通用网络、GUI/团队控制面或更多生态识别。
- 恢复命令：

```powershell
Set-Location <repo-path>
python -m pip install -e ".[dev]"
python -B -m pytest -q -p no:cacheprovider
python -m ruff check . --no-cache
agent-preflight scan --json
agent-preflight agent-doctor --json --pretty
agent-preflight command-doctor npm --json --pretty --timeout 1
agent-preflight workspace-scope --target . --control $env:TEMP --allow-write --json --pretty
agent-preflight support-report --json --pretty
agent-preflight snapshot --label host --output .\snapshots\host.json --pretty
$env:PYTHONIOENCODING = "cp1252:strict"
python -B -m win_agent_preflight --help
Remove-Item Env:PYTHONIOENCODING
```

## 验证记录

| 日期 | 命令 | 结果 |
| --- | --- | --- |
| 2026-08-24 | `python --version` | Python 3.12.7 |
| 2026-08-24 | `py -0p` | Python Launcher 已可用；当前登记 Python 3.12.7，尚无 3.14 |
| 2026-08-24 | `python -B -m pytest -q -p no:cacheprovider` | 42 passed |
| 2026-08-24 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；10 pass、3 warning、0 fail、0 unknown；JSON 可解析 |
| 2026-08-24 | `python -B -m pytest -q -p no:cacheprovider` | 75 passed；包含 27 个 workspace-probe 专项测试，覆盖对象身份变化、外部 after 残留、报告一致性、输入零写、异常和 CLI 退出码 |
| 2026-08-24 | `python -m ruff check . --no-cache` | All checks passed |
| 2026-08-24 | `python -B -m win_agent_preflight workspace-probe --target $env:TEMP --allow-write --json --pretty` | 退出 0；六项 pass；`successful=true`；`residual_paths=[]`；无 `.agent-preflight-probe-*` 残留 |
| 2026-08-24 | `python -B -m win_agent_preflight workspace-probe --target . --allow-write --json --pretty` | 当前 Codex 沙箱中退出 1；创建目录 WinError 5；1 pass、1 fail、4 unknown；`residual_paths=[]`，无探针残留 |
| 2026-08-24 | `python -m build --version` | build 1.5.0 |
| 2026-08-24 | `python -m build --sdist --wheel` | 默认隔离构建成功生成 1 个 sdist 与 1 个 wheel |
| 2026-08-24 | `.artifacts\\sdist-check`、`.artifacts\\wheel-check` 两个干净环境安装制品并运行 CLI 帮助 | 两个环境均退出 0 |
| 2026-08-24 | `agent-preflight scan --timeout 2` | 退出 0；Console 报告生成成功 |
| 2026-08-24 | `agent-preflight snapshot --label host --output %TEMP%\\win-agent-preflight-m2\\cli-host.json --timeout 1` | 退出 0；输出目录已存在时写出快照 |
| 2026-08-24 | `agent-preflight snapshot --label current --output %TEMP%\\win-agent-preflight-m2\\cli-current.json --timeout 1` | 退出 0；第二快照写出 |
| 2026-08-24 | `agent-preflight compare %TEMP%\\win-agent-preflight-m2\\cli-host.json %TEMP%\\win-agent-preflight-m2\\cli-current.json --json --pretty` | 退出 0；`equivalent: true`，JSON 可解析 |
| 2026-08-24 | `python -m pip install -e ".[dev]" --no-build-isolation` | 安装成功，`agent-preflight.exe` 位于当前 Python Scripts 目录 |
| 2026-08-24 | `python -B -c "from win_agent_preflight.windows import collect_registry_path_facts; ..."` | HKLM/HKCU 读取完整；异常/类型/缺失场景由测试覆盖 |
| 2026-08-24 | `python -B -m win_agent_preflight scan --json --pretty --timeout 2` | 退出 0；10 pass、3 warning、0 fail、0 unknown；JSON 可解析 |
| 2026-08-24 | 第七里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 104 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | Support Report 真实 CLI | `python -B -m win_agent_preflight support-report --json --pretty --timeout 1` | 退出 0；JSON 可解析；`offline=true`、`workspace_probe_run=false`；未运行 workspace-probe |
| 2026-08-24 | 第七里程碑制品复验 | 当前进程设 `PYTHONUTF8=1` 后默认隔离构建，并在 `.artifacts\\m7-sdist`、`.artifacts\\m7-wheel` 安装两个制品 | sdist/wheel 均包含 `support_report.py`；两个全新 Python 3.12 环境的 `support-report --help` 均退出 0；沙箱中暴露的真实失败为 PyPI 网络权限 |
| 2026-08-24 | 第八里程碑全量验证 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 113 passed；Ruff 通过；diff check 仅报告 CRLF 转换提示，无内容错误 |
| 2026-08-24 | SupportReport v2 真实 CLI | `python -B -m win_agent_preflight support-report --json --pretty --timeout 1` | 退出 0；顶层 `schema_version=2`、`kind=support_report`；内嵌 scan/Agent Doctor 为 v1；`offline=true`、`workspace_probe_run=false`；本次推导 1 项 next check |
| 2026-08-24 | CLI help cp1252 smoke | `python -B -m pytest tests/test_cli_help.py -q -p no:cacheprovider` | 根命令和全部子命令在严格 cp1252 子进程中均退出 0；stdout/stderr 严格解码；临时工作目录无文件 |
| 2026-08-24 | cp1252 修复全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 114 passed；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | 首次 GitHub Windows CI | [run 32691934171](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32691934171) | Python 3.12/3.14 安装与 pytest 通过，3.12 Ruff 通过；两个矩阵 job 均在根 `--help` 的 cp1252 `UnicodeEncodeError` 失败；package job 因 `needs: test` 跳过，远程 sdist/wheel 未验证 |
| 2026-08-24 | cp1252 修复后 GitHub Windows CI | [run 32693383743](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32693383743) | Python 3.12/3.14 测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | project-doctor GitHub Windows CI | [run 32696172691](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32696172691) | Python 3.12/3.14 的 145 项测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | snapshot 修复前一轮 main CI | [run 32696504545](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32696504545) | 当时已推送内容的 Python 3.12/3.14 测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建和干净环境安装全部通过；不包含后续 snapshot 修复 |
| 2026-08-24 | snapshot 修复 GitHub Windows CI | [run 32699112641](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32699112641) | Python 3.12/3.14 的 158 项测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | Codex 上下文快照 | `%TEMP%\win-agent-preflight\context-run-01\codex.json` | snapshot 退出 0；重载得到 label `codex`、cwd 为本仓库、schema v1；无用户目录明文；临时残留 0；自比较退出 0 |
| 2026-08-24 | project-doctor 定向测试 | `python -B -m pytest tests/test_project_doctor.py tests/test_cli.py tests/test_cli_help.py -ra -p no:cacheprovider` | 41 passed；覆盖 marker 组合/锁文件去重/冲突/孤立、ignored marker、marker 异常累计、第一层边界、reparse/symlink/非普通项、无内容读取、工具调用/required_by 和 CLI 退出语义 |
| 2026-08-24 | project-doctor 全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 145 passed；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | project-doctor 真实仓库根 | `python -B -m win_agent_preflight project-doctor --target . --json --pretty --timeout 1` | 退出 0；`project.markers` 与 `project.python` 均 pass；仅推导并探测 python；未写入文件 |
| 2026-08-24 | snapshot/CLI 定向回归 | `python -B -m pytest tests/test_snapshot.py tests/test_cli.py -ra -p no:cacheprovider` | 30 passed；覆盖父路径普通文件分类、权限首错单次失败、三次名称碰撞、碰撞后成功、竞争输出保留、write/fsync/replace/fdopen/cleanup 失败和 CLI 退出 2 |
| 2026-08-24 | snapshot 全量回归与静态检查 | `python -B -m pytest -ra -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 154 passed；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | snapshot P1/P2 回归 | `python -B -m pytest -ra -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 158 passed；父路径为普通文件时 force/non-force 均为 `cannot write snapshot`，link 竞争仍保留 `output already exists`，主失败叠加 cleanup 失败及 non-force 提交后删除失败均保留残留并报告；Ruff 通过；diff check 无内容错误（仅 CRLF 转换提示） |
| 2026-08-24 | snapshot 拒绝写入边界 | 两次 `snapshot` 指向项目 `.artifacts` 的唯一输出路径，`--timeout 1` | 两次均在 3.7–4.4 秒内退出 2；`Permission denied`；输出不存在；已知 `.tmp` 残留为 0 |
| 2026-08-24 | snapshot 可写目录边界 | 唯一 `%TEMP%` 目录中运行 `snapshot`，随后 `load_snapshot` 读取并显式清理该目录 | 写出退出 0，`load_snapshot` 读取 `temp-check 1 environment_snapshot`；临时文件 0；目录已清理 |
| 2026-08-24 | command-doctor 定向回归 | `python -B -m pytest tests/test_command_doctor.py tests/test_windows.py tests/test_cli.py tests/test_cli_help.py -ra -p no:cacheprovider` | 82 passed；覆盖严格输入零 Runner、非 Windows 零 facts/Runner、PATHEXT 顺序和候选回退、五态/WinError/timeout/空输出、PowerShell 裸命令和显式扩展检查、direct + bare 恰好两次同 timeout、JSON/Console/退出码/cp1252 help |
| 2026-08-24 | command-doctor 全量与静态检查 | `python -B -m pytest -ra -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check` | 200 passed；Ruff 和 diff check 通过 |
| 2026-08-24 | command-doctor 真实本机 CLI | `python -B -m win_agent_preflight command-doctor npm/npm.cmd/pnpm --json --pretty --timeout 1` | 三个命令均退出 0；npm `11.17.0`、npm.cmd `11.17.0`、pnpm `11.22.0`；均为 `usable` 且 `windows.path_refresh=pass`，pnpm 报告主安装与 fallback 候选，未写文件 |
| 2026-08-24 | command-doctor GitHub Windows CI | [run 32703174150](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32703174150) | Python 3.12/3.14 的 200 项测试、严格 cp1252 help、workspace probe、Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-24 | 真实项目 project-doctor 矩阵 | MyMineCraft、MCP Interop Lab、两份 Triton 源码树 | MyMineCraft 识别 Node + pnpm 并退出 0；MCP Lab 识别 Python 并退出 0；两份未提供 `pyproject.toml`/`requirements.txt` 等受支持 marker 的旧 Triton 源码树均以 `no supported project marker` 退出 1，未凭 `.py` 文件猜测工具链 |
| 2026-08-24 | 真实项目 workspace-probe 矩阵 | MyMineCraft、Evolutionary Triton Optimizer、MCP Interop Lab | 同一 Codex 上下文中，Triton 项目六步通过；MyMineCraft 与 MCP Lab 均在创建探针目录时返回 PermissionError/WinError 5；三次 `residual_paths=[]`。只读目录属性与 ACL 未解释差异，因此不把失败武断归因于 Windows ACL 或 Agent 沙箱 |
| 2026-08-24 | workspace-scope 定向回归 | `python -B -m pytest tests/test_workspace_scope.py tests/test_cli_help.py -q -p no:cacheprovider` | workspace-scope 24 项 + CLI help 1 项，共 25 passed；覆盖四种完整状态、纯 unknown 归约、预验证零 probe 调用、target/control 顺序和次数、异常/中断 partial、脱敏、JSON/Console/退出码和 cp1252 help |
| 2026-08-24 | workspace-scope 全量回归 | `python -B -m pytest -p no:cacheprovider -ra`、`python -m ruff check . --no-cache`、`git diff --check` | 提交前本地验证 261 passed；Ruff 通过；diff check 无内容错误 |
| 2026-08-24 | workspace-scope 真实项目矩阵 | 分别以 Evolutionary Triton Optimizer、MyMineCraft、MCP Interop Lab 为 `--target`，以 `%TEMP%` 为 `--control` | Triton 与 control 均六项通过，状态 `both_usable`、退出 0；MyMineCraft/MCP Lab 的 target 创建目录均返回 WinError 5，control 六项通过，状态 `target_specific_failure`、退出 1；四个目录 `.agent-preflight-probe-*` 残留均为 0 |
| 2026-08-24 | workspace-scope GitHub Windows CI | [run 32712146556](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32712146556) | 提交 `b981bf1` 的 Python 3.12/3.14 全量 261 项测试、严格 cp1252 help、workspace probe、3.12 Ruff、sdist/wheel 构建、两个干净环境安装和制品上传全部通过 |
| 2026-08-27 | 路线文档复审 | `python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache`、`git diff --check`、真实 `support-report --json --timeout 1` | 全量 261 项测试通过；Ruff、diff check 和真实 CLI 通过；本轮只更新定位、路线、需求证据与用户操作说明，未修改运行时代码 |

## 下一里程碑验收

- [x] 已推送内容的 GitHub Windows runner Python 3.12 与 3.14 矩阵 job 全部通过；
- [x] 已推送内容的 package job 构建并安装 sdist/wheel，非 PR 运行可下载 7 天制品；
- [x] project-doctor 的 Windows CI 已验证该命令的测试、help 和包验收；
- [x] snapshot 写入快速失败修复已提交/推送，Windows CI 和本地拒绝写入目录退出边界均通过；
- 用户在宿主与实际 Agent 上分别生成脱敏快照并完成 compare；
- 不增加自动发布、缓存、签名或额外平台基础设施。

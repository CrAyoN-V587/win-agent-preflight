# 设计说明

## 目标

第三里程碑在首阶段稳定诊断核心和第二里程碑 `snapshot`/`compare` 上增加只读注册表 PATH 事实：快照仍保存有限宿主事实和同次 `scan`，比较只使用规范化后的稳定字段。真实 Agent 宿主终端仍需用户在对应环境中分别生成快照；本阶段不自动进入沙箱。

## 模块边界

```text
cli.py
  ├─ checks.py（诊断分类与扫描编排）
  ├─ agent_doctor.py（AgentDoctorReport v1 与最小版本探针）
  ├─ support_report.py（SupportReport v1 与离线组合采集）
  ├─ snapshot.py（EnvironmentSnapshot v1、解析、写入和比较）
  └─ compare.py（差异输出）
       ├─ windows.py（PATH 候选、注册表 PATH 和 PowerShell 事实）
       ├─ runner.py（所有外部命令的唯一执行边界）
       └─ models.py（不可变、可序列化模型）
  └─ reporting.py（Console/JSON，不改变诊断语义）
```

- `models.py` 不调用系统；字段和序列化顺序稳定。
- `runner.py` 接收可注入的执行函数，统一超时、返回码、stdout/stderr 和启动异常。
- `windows.py` 负责当前进程环境中的 Windows 事实采集；注册表只读 HKLM/HKCU 环境键，路径只作为脱敏后的证据流出；Agent 解析只读 lstat，不在发现阶段启动命令。
- `checks.py` 将事实转换为 `pass`、`warning`、`fail`、`unknown`，不负责 CLI 参数或输出格式。
- `agent_doctor.py` 使用独立状态和 v1 报告，不复用 `CheckResult`，也不改变 `scan`、`snapshot` 或 `workspace-probe` schema。
- `support_report.py` 先收集 Agent Doctor，再将其结果映射为既有 `CheckResult` 并注入 `scan_environment`；Agent Doctor 可依次尝试同一 Agent 的多个候选，每个候选最多一次，scan 不再重复探测三个 Agent，不改变 standalone `scan` 的 schema 或行为。
- `cli.py` 负责解析子命令；既有命令的调用路径和 v1 JSON/退出语义保持不变。
- `reporting.py` 只渲染已有结果，不再次运行命令。

## 状态语义

| 状态 | 语义 |
| --- | --- |
| `pass` | 已实际验证满足条件 |
| `warning` | 可运行但存在缺失、冲突或可选能力未安装 |
| `fail` | 已有证据证明本项不能按预期工作 |
| `unknown` | 证据不足或当前平台不支持该事实 |

对 `scan` 的 `CheckResult` 而言，可选 Agent（`codex`、`claude`、`dsh`）缺失只能产生 `warning`。`agent-doctor` 使用独立状态，其中未发现命令为 `command_not_found`。任何 `fail` 必须有至少一条证据字符串；模型构造函数会拒绝没有证据的 fail。

## 命令发现

扫描当前进程 `PATH`，按 Windows 的 `PATHEXT` 和显式扩展名列出候选路径。发现不等于可用：每个候选的首选项再由 Runner 真实启动一次。`npm` 会把 `npm.cmd`、`npm.exe`、`npm.bat`、`npm.ps1` 作为候选；显式扫描项也会单独报告。

`npm.ps1` 不通过普通进程直接运行，而是经 PowerShell 的 `-NoProfile -Command` 调用，以便识别脚本执行策略阻止；不会修改策略。

裸 `npm` 另有独立的 `powershell.command.npm` 检查：在选定 PowerShell 中执行 `Get-Command npm` 和 `npm --version`。因此 `npm.cmd` 候选可启动不等于 PowerShell 裸命令可用。

## 注册表 PATH 与刷新诊断

`RegistryPathFacts` 是不可变的两 scope 事实模型。默认 reader 只读：

- HKLM：`SYSTEM\CurrentControlSet\Control\Session Manager\Environment`；
- HKCU：`Environment`。

缺失键或 `Path` 值表示为空且事实完整；读取异常或 `Path` 不是字符串表示对应 scope 不完整。测试和嵌入调用可向 `collect_registry_path_facts`、`collect_path_refresh_check`、`scan_environment` 或 `capture_snapshot` 注入按 `machine`/`user` 读取的 reader，不需要修改本机注册表。

注册表 PATH 中的 `%NAME%` 按大小写不敏感展开，最多 8 轮：机器 PATH 使用 HKLM 值再回退到当前进程环境，用户 PATH 使用 HKCU、HKLM、当前进程环境。未解析变量只报告变量名。比较使用 `ntpath`，忽略大小写、斜杠、引号和尾分隔符，不解析真实路径，也不检查目录是否存在；诊断证据保留 `machine`/`user` 来源。

刷新检查只产生 `pass`、`warning` 或 `unknown`，不会产生 `fail`：完整且全部继承为 `pass`，已证明缺失为 `warning`（即便另一 scope 不完整），只有错误/未解析且没有已证明缺失为 `unknown`。

## EnvironmentSnapshot v1

快照顶层字段为 `schema_version`、`tool`、`kind`、`label`、`captured_at`、`environment` 和 `scan`。`environment` 只保存 `cwd`、`sys_executable`、`platform`、PATH 集合和 PATHEXT 集合；不保存完整环境变量。`scan` 使用已有 v1 JSON，不另造第二套检查模型。

解析器只接受 v1，拒绝顶层或内嵌 scan 的更高版本及已知字段类型错误，未知字段忽略。快照写出时父目录可创建，默认不覆盖已有文件，`--force` 才覆盖；扫描失败不会阻止快照写出。

## Compare 规范化

比较忽略 `label`、`captured_at`、scan `summary`、check `summary` 和 `candidate_count`。cwd、sys.executable、候选路径按 Windows 规则规范化；PATH、PATHEXT 与 candidates 保留原有顺序，仅去除后续重复项，因为顺序会影响 Windows 命令解析。evidence 只统一换行和行尾空白后去重排序，保留大小写与非路径斜杠语义；检查按 `CheckResult.id` 稳定匹配。等价返回 0，实质差异返回 1，输入/版本/类型错误返回 2。

## 脱敏

报告渲染前统一将当前用户目录（大小写不敏感）替换为 `%USERPROFILE%`，同时替换 `USERPROFILE` 变量值和常见临时目录中的用户名段。只输出变量名和脱敏状态，不输出 token、密码、API key 或完整环境变量值。

## 未来扩展

## 第六里程碑：agent-doctor

`agent-doctor` 是独立的 `AgentDoctorReport v1`，只回答“当前进程 PATH 中已解析的本地 Agent 启动器能否完成版本探测流程”。默认检查 `codex`、`claude`、`dsh`；重复的 `--agent` 先去重，再按这个固定顺序输出。其他输入直接作为输入错误，不静默扩展支持范围。

发现阶段只读取当前 PATH 中的 `.exe`、`.cmd`、`.bat` 和 `.ps1` 启动器，并使用 `lstat` 保留 WindowsApps alias 或权限异常的结构化证据。同一 Agent 的多个普通候选按 PATH 顺序依次通过 Runner 执行 `--version`，每个候选最多一次；`.ps1` 通过已有 PowerShell launcher 处理。不会调用 `login`、`doctor`、`npx`、网络或网页命令。

每个 Agent 的状态固定为 `command_not_found`、`resolved_but_not_executable`、`access_denied`、`version_probe_failed` 或 `usable`。只有 `--version` 退出码为 0 且 stdout/stderr 至少有一条非空文本时才是 `usable`；成功结果保存脱敏后最多 200 字符的第一条非空版本行，空输出归类为 `version_probe_failed`。未发现命令不是失败，全部未安装时 CLI 退出 0；已发现但不可用时退出 1；输入错误退出 2。顶层报告固定含 `kind=agent_doctor` 与 `offline=true`。Runner 错误只输出 `error_type`、`winerror`、返回码和超时标记，不回显 stdout/stderr；路径按 `%USERPROFILE%` 脱敏。

## 第七里程碑：support-report

`support-report` 是独立的 `SupportReport v1` 分享 envelope。它只接受 `--json`、`--pretty` 和 `--timeout`，默认输出 Console，不提供 `--output`。一次调用只创建一个共享 `Runner`、环境映射和超时：先运行默认 `codex`、`claude`、`dsh` 的 Agent Doctor（允许同一 Agent 的多候选回退，每个已发现候选最多一次），再把三个最终结果映射为既有 `CheckResult`，通过 `scan_environment(precomputed_commands=...)` 注入，避免 scan 再次执行这三个 Agent 的版本命令；不改变 standalone `scan` 的默认行为和 schema。

顶层字段固定为 `schema_version`、`tool`、`kind=support_report`、`generated_at`、有限 `environment`、`collection`、`scan`、`agent_doctor` 和 `errors`。environment 只保留 `platform`、`python_version`、`architecture`；collection 固定记录 `offline=true`、`workspace_probe_run=false`、`timeout_seconds` 和 `complete`。报告不保存主机名、cwd、`sys.executable`、完整 PATH 或环境变量值，也不运行 workspace-probe、login、doctor、npx、web、网络或写文件。

健康异常仍属于采集成功：Agent 命令缺失或不可用由既有 warning/独立 Agent 状态表达，CLI 退出 0。只有部分采集抛出异常时记录脱敏、截断且不含 traceback/stdout/stderr 的 `errors`，保留另一部分结果并退出 1；输入错误退出 2。首版只组合证据，不给出行动建议。Console 复用 scan 和 Agent Doctor renderer，并固定输出分享前边界提醒。

## 第四里程碑：workspace-probe

`workspace-probe` 是与 `scan`/`snapshot` 独立的 `WorkspaceProbeReport v1`，用于回答一个窄问题：当前一次命令进程在指定 Windows 目录中，是否能完成最小的创建、写入、读取、重命名、删除和清理。结论只适用于这一次运行、这个目标目录和当前进程上下文，不能替宿主或其他 Agent 上下文作权限结论。

探针记录创建目录和文件的 Windows `st_dev`/`st_ino` 身份，并在重命名、删除和移除目录前重新核对；身份不可用或变化时保守失败并报告残留。它采用非对抗的本地并发假设：Python 路径级 `unlink`/`rmdir` 无法把身份核对与删除合并为原子操作，因此不承诺抵御其他进程在二者之间刻意替换同名对象。首版不为这一安全场景引入 Win32 句柄级删除。

命令必须同时提供 `--target PATH` 和显式 `--allow-write`。输入验证在任何写入前完成：仅 Windows、目标已存在且是普通目录、目标本身不是重解析点、`Path.resolve(strict=True)` 成功。探针只创建目标直接子目录 `.agent-preflight-probe-<uuid>`，其中独占创建 `before.txt`，重命名为 `after.txt`，最后删除已知文件和空目录。

报告固定六项并保持顺序：`workspace.create_directory`、`workspace.write_file`、`workspace.read_file`、`workspace.rename_file`、`workspace.delete_file`、`workspace.cleanup`。`successful` 仅在六项均为 `pass` 且 `residual_paths` 为空时为真；残留只使用相对目标目录的本次已知路径。读取不一致不会阻止后续重命名/删除尝试；创建或写入失败时依赖步骤为 `unknown`。异常证据只保留类型、`winerror`（若有）和脱敏截断消息，不回显探针内容。

清理不使用 `shutil.rmtree`，不遍历目标、不处理历史目录；清理前若探针目录是重解析点或状态不明则不进入，并以相对路径报告残留。普通能力失败退出 1，输入拒绝退出 2，Ctrl-C 尽力清理后由 CLI 输出部分报告并退出 130。该功能不联网、不提权、不修改 ACL、PATH、注册表、执行策略或 Agent 配置。

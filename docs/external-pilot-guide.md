# Windows Agent Preflight 外部试运行手册

这份手册可以直接发给试运行者。目标不是检查对方的代码或账号，而是比较同一台 Windows 机器上普通 PowerShell 与 Coding Agent 命令执行器看到的环境差异。

整个流程通常需要 10–20 分钟。默认只回传归约结果，不发送原始快照。

## 1. 参与条件

需要：

- Windows 10 或 Windows 11；
- Python 3.12 或更高版本；
- Codex、Claude Code 或其他能够在本机运行 PowerShell 命令的 Coding Agent；
- 能下载公开仓库：[CrAyoN-V587/win-agent-preflight](https://github.com/CrAyoN-V587/win-agent-preflight)；
- 一个 Codex 外部的普通 PowerShell 窗口。

不需要管理员权限、GitHub 登录、API Key、Docker、WSL、数据库或真实业务项目。建议直接以本工具仓库作为目标目录，不要在包含公司代码、客户数据或秘密路径的项目中试运行。

## 2. 操作前需要知道的边界

工具会：

- 在 `%TEMP%\win-agent-preflight\<本轮名称>` 写入两份 JSON 快照；
- 读取当前进程的 cwd、Python 路径、PATH、PATHEXT、PowerShell/注册表 PATH 事实；
- 在 PATH 中查找固定工具，并对候选执行有 5 秒上限的 `--version`；
- 将当前用户目录替换为 `%USERPROFILE%`。

工具不会：

- 登录 Agent、GitHub 或其他账号；
- 读取 Token、密码、API Key 或完整环境变量值；
- 联网、安装软件、修改 PATH/注册表/Execution Policy/ACL；
- 自动修复、提权、上传或删除文件；
- 读取目标项目的业务代码内容。

## 3. 准备仓库

可以使用 Git：

```powershell
git clone https://github.com/CrAyoN-V587/win-agent-preflight.git
Set-Location .\win-agent-preflight
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m win_agent_preflight --help
```

也可以从 GitHub 下载 ZIP、解压后进入目录，再创建 `.venv` 并执行后两条命令。准备阶段的 pip 可能访问 Python 包索引以安装缺失依赖；后续 scan/snapshot/compare 诊断本身不联网。`.venv` 只服务本次仓库，避免改变全局 Python 环境。

如果安装或帮助命令失败，请停止并回传错误，不要改执行策略、关闭安全软件或使用管理员权限强行继续。

## 4. 固定本轮参数

先为本轮选择一个不含姓名、邮箱、学号或公司名的编号，例如 `pilot-01`。以下两个值必须在普通 PowerShell 和 Agent 中完全一致：

```powershell
$TargetProject = "C:\path\to\win-agent-preflight"
$RunId = "pilot-01"
$EvidenceDir = Join-Path $env:TEMP "win-agent-preflight\$RunId"
```

将 `$TargetProject` 改成实际仓库根目录。每轮使用新的 `$RunId`；如果输出文件已经存在，不要使用 `--force` 覆盖。

## 5. 在 Coding Agent 中采集

把下面这段话发给正在试用的 Agent，并替换项目路径和 Agent 名称：

> 请只在指定项目目录执行下面的 PowerShell 命令，生成一份本地环境快照。不要修改项目、系统配置或账号，不要上传快照。命令退出后只告诉我退出码和输出文件是否存在。

让 Agent 通过自己的命令执行器运行：

```powershell
$TargetProject = "C:\path\to\win-agent-preflight"
$RunId = "pilot-01"
$EvidenceDir = Join-Path $env:TEMP "win-agent-preflight\$RunId"

Set-Location $TargetProject

.\.venv\Scripts\python.exe -B -m win_agent_preflight snapshot `
  --label codex `
  --output (Join-Path $EvidenceDir "codex.json") `
  --pretty `
  --timeout 5

Write-Host "Exit code: $LASTEXITCODE"
Get-Item (Join-Path $EvidenceDir "codex.json")
```

使用 Claude Code 时，把 `codex`/`codex.json` 改为 `claude`/`claude.json`。其他 Agent 使用简短、无个人信息的 label 和文件名。不要在普通 PowerShell 中代替 Agent 生成这份文件。

## 6. 在普通 PowerShell 中采集 Host

必须在 Coding Agent 外部的新 PowerShell 窗口运行：

```powershell
$TargetProject = "C:\path\to\win-agent-preflight"
$RunId = "pilot-01"
$EvidenceDir = Join-Path $env:TEMP "win-agent-preflight\$RunId"

Set-Location $TargetProject

.\.venv\Scripts\python.exe -B -m win_agent_preflight snapshot `
  --label host `
  --output (Join-Path $EvidenceDir "host.json") `
  --pretty `
  --timeout 5

Write-Host "Exit code: $LASTEXITCODE"
Get-Item (Join-Path $EvidenceDir "host.json")
```

Host 与 Agent 两端必须满足：同一台机器、同一项目目录、同一仓库版本、同一个 `$RunId`、相同 timeout。任一项不一致时不要把比较结果当成有效案例。

## 7. 比较结果

回到普通 PowerShell，运行：

```powershell
.\.venv\Scripts\python.exe -B -m win_agent_preflight compare `
  (Join-Path $EvidenceDir "host.json") `
  (Join-Path $EvidenceDir "codex.json")

Write-Host "Compare exit code: $LASTEXITCODE"
```

使用其他 Agent 时替换第二个文件名。

退出码含义：

- `0`：两份快照在比较规则下等价；
- `1`：成功发现有效差异，不是程序故障；
- `2`：输入文件缺失、损坏、版本不支持或命令参数错误。

完整 compare 输出可能包含安装目录、软件版本和非用户目录路径。不要直接粘贴到公开 Issue、群聊或论坛。

## 8. 请回传这些信息

默认只需要复制下面模板并填写，不要附加原始 JSON 或完整 PATH：

```text
参与编号：（不要填写真实姓名、邮箱或账号）
Windows：10 / 11
Agent 与安装方式：例如 Codex Desktop / Codex CLI / Claude Code
Python 版本：
仓库提交：运行 git rev-parse --short HEAD；没有 Git 时填 ZIP
Agent snapshot 退出码：
Host snapshot 退出码：
Compare 退出码：
差异数量：只填第一行显示的数字
是否第一次就完成：是 / 否
如果没有一次完成，卡在哪一步：
结果是否帮助你理解环境差异：是 / 部分 / 否
最难理解的提示：
是否同意公开匿名归约摘要：是 / 否
```

如果命令失败，再补充：

- 失败步骤编号；
- 实际执行的命令，但先把本机绝对路径替换为 `%PROJECT_ROOT%`、`%PYTHON_HOME%`、`%USERPROFILE%` 等占位符；
- 错误类型、退出码和最后 5–10 行错误信息；
- 文件是否创建以及文件大小，不发送文件内容。

## 9. 不要回传这些信息

- `host.json`、`codex.json` 等原始快照，除非双方另行确认私下诊断范围；
- 完整 compare 输出；
- 完整 PATH、用户名、邮箱、机器名、公司目录、仓库绝对路径；
- GitHub Token、API Key、密码、SSH Key、Cookie 或任何凭据；
- 包含浏览器账号、终端历史、其他项目或聊天内容的截图；
- 与本次试运行无关的业务代码、日志或配置。

即使工具会脱敏 `%USERPROFILE%`，其他盘符、软件目录、项目名和组织路径仍可能保留，因此原始 JSON 不能默认视为可公开文件。

## 10. 风险与停止条件

主要风险：

1. **准备阶段写入与联网**：Git/ZIP 会创建仓库目录，`.venv` 会占用本地空间，pip 可能联网下载依赖；这些行为发生在准备阶段，不是诊断命令的隐式操作。
2. **隐私暴露**：原始快照和 compare 输出可能反映已安装软件、版本、目录结构和 Agent runtime。
3. **工具启动副作用**：工具只请求 `--version`，但第三方或损坏的 launcher 仍可能表现异常；每次调用有 timeout，不代表所有第三方程序都绝对无副作用。
4. **Agent 写入限制**：Agent 可能无法写入 `%TEMP%` 或目标位置。遇到拒绝访问时停止，不要提权或修改 ACL。
5. **误判**：不同 cwd、仓库版本、轮次或 timeout 会制造假差异；短 timeout 也可能把冷启动误判成不可用。
6. **资源占用**：少数异常命令可能持续到 timeout；流程通常较轻，但不应在重要构建或演示期间运行。

出现以下情况立即停止：

- 命令要求登录、输入密码、管理员授权或关闭安全策略；
- 输出出现疑似 Token、密钥、公司内部地址或客户信息；
- Agent 提议修改 PATH、注册表、Execution Policy、ACL 或项目代码；
- 目标目录或证据目录与预期不一致；
- 已有同名快照，无法确认来源。

停止后只回传步骤编号和脱敏错误摘要，不需要为了完成试运行自行修复环境。

## 11. 证据保留与清理

在确认反馈已记录前，可以暂时保留本轮证据。结束后建议通过文件资源管理器只删除：

```text
%TEMP%\win-agent-preflight\<本轮 RunId>
```

不要删除整个 `%TEMP%`、整个用户目录或不确定来源的其他轮次。项目不会自动清理、上传、压缩或计算哈希。

## 12. 联系维护者时的默认原则

默认按“最少信息”原则交流：先发第 8 节模板；只有维护者说明为什么需要更多字段、通过什么渠道传输，并获得参与者明确同意后，才扩大材料范围。是否同意公开匿名摘要不影响参与试运行。

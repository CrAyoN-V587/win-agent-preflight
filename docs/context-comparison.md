# Host 与 Agent 上下文成对采集

这份协议用于比较同一台 Windows 机器上“普通宿主终端”和 Coding Agent 实际命令执行器看到的环境。它复用现有 `snapshot` 与 `compare`，不启动外部 Agent、不登录账户、不修改 PATH、权限或执行策略。

这是当前项目路线的最高优先级验收。完成首组真实证据前，不继续增加新探针。

## 为什么必须双端手动触发

一个进程只能采集自己的环境。若在普通 PowerShell 中连续生成 `host.json` 和 `codex.json`，得到的仍是两份宿主快照，不能证明 Codex 的 PATH、Shell 或权限。无法由当前 Agent 或单进程脚本替代的边界，是进入对应 Agent 会话，让该 Agent 自己的命令执行器运行一次快照命令；host 快照同样需要用户在普通 PowerShell 中触发。

首轮建议只比较 host 与当前正在使用的 Agent。Claude 或 DSH 尚未安装、没有命令执行能力或看不到本工具时，记录“未采集”，不要用宿主快照代替。

## 0. 约定目标和证据目录

两端都使用同一台机器、同一目标项目目录和同一轮名称：

```powershell
$TargetProject = "D:\path\to\target-project"
$EvidenceDir = Join-Path $env:TEMP "win-agent-preflight\context-run-01"
Set-Location $TargetProject
```

当前仓库自测时，将 `$TargetProject` 设为本仓库根目录，并在两端都使用 `python -B -m win_agent_preflight`。诊断其他项目时，在两端都使用已经确认指向预期安装的 `agent-preflight`；不要让 host 与 Agent 使用不同代码版本，也不要为了完成采集临时修改 PATH。

推荐每轮使用新的目录名，默认不加 `--force`，避免覆盖旧证据。

## 1. 在普通 PowerShell 采集 host

```powershell
Set-Location $TargetProject
python -B -m win_agent_preflight snapshot `
  --label host `
  --output (Join-Path $EvidenceDir "host.json") `
  --pretty `
  --timeout 2
```

若诊断的不是本仓库，且工具已安装为命令行入口，将 `python -B -m win_agent_preflight` 替换为 `agent-preflight`。

## 2. 在真实 Agent 执行器采集

进入 Codex 任务，让 Codex 通过自己的命令执行工具运行：

```powershell
$TargetProject = "D:\path\to\target-project"
$EvidenceDir = Join-Path $env:TEMP "win-agent-preflight\context-run-01"
Set-Location $TargetProject
python -B -m win_agent_preflight snapshot `
  --label codex `
  --output (Join-Path $EvidenceDir "codex.json") `
  --pretty `
  --timeout 2
```

上例是本仓库自测入口。诊断其他项目时，与 host 端相同，把 `python -B -m win_agent_preflight` 替换为两端均已验证的 `agent-preflight`。

Claude 与 DSH 的流程相同，只分别改为 `--label claude`/`claude.json` 和 `--label dsh`/`dsh.json`。每条命令必须由对应 Agent 的执行器启动。

当前 Codex 上下文已验证项目内 `.artifacts` 可能拒绝写入，而 `%TEMP%` 可写，因此协议默认使用 `%TEMP%`。若不同上下文的 `%TEMP%` 指向不同位置，让 Agent 报告其实际输出路径，再由用户在宿主侧明确复制该文件；首版不自动搬运。

## 3. 回到宿主逐对比较

```powershell
python -B -m win_agent_preflight compare `
  (Join-Path $EvidenceDir "host.json") `
  (Join-Path $EvidenceDir "codex.json") `
  --json `
  --pretty
```

若存在 Claude 或 DSH 快照，分别把第二个路径换成相应文件。逐对比较比一次聚合多个文件更容易确认差异来源。

退出码含义：

- `snapshot` 成功为 `0`，输入或写入失败为 `2`；内嵌 scan 有失败项仍可写出快照并返回 `0`。
- `compare` 等价为 `0`，发现有效差异为 `1`，缺失、损坏或不支持的快照为 `2`。
- `compare` 返回 `1` 是成功发现差异，不是工具故障。

## 4. 人工检查与清理

快照只保存有限环境事实，不保存完整环境变量或凭据，并会把用户目录替换为 `%USERPROFILE%`。但项目名、非用户目录和工具安装位置仍可能出现；公开前必须人工检查 JSON。

至少确认：

- `label` 分别为 `host` 和对应 Agent 名称；
- 两份 `environment.cwd` 指向同一项目；
- JSON 中没有用户名明文、密钥或不应公开的业务路径；
- `captured_at` 表明确实来自两次独立采集。

工具不会自动上传、压缩、哈希或删除证据。完成检查后，由用户显式删除本轮 `%TEMP%\win-agent-preflight\context-run-01`；不要使用宽泛目录作为清理目标。

## 当前实测状态

- Codex 端 `context-run-01\codex.json` 已在 `%TEMP%` 成功生成并由 `load_snapshot` 重新读取。
- label 为 `codex`，cwd 为本仓库根目录，schema 为 v1，明文用户目录未出现在 JSON 中，临时文件残留为 0。
- 该文件与自身比较返回等价 `0`。
- host 端仍需用户在普通 PowerShell 中执行第 1 步，才能形成真实成对证据。
- 2026-08-27 已完成 `context-run-01` 初步比较并发现 8 项差异，但两份快照相隔三天；宿主侧 1 秒 timeout 还造成 pnpm 冷启动超时，因此该轮只用于发现流程问题，不作为严格公开案例。
- 当前 Codex 已用 2 秒 timeout 生成并验证 `context-run-02\codex.json`；用户名、常见 token/key 和邮箱模式命中均为 0，自比较等价。

## 用户现在需要完成

1. 打开 Codex 外部的普通 PowerShell 窗口，不要在 Codex 内置终端运行 host 命令。
2. 将第 0 节 `$TargetProject` 改为本仓库绝对路径，并将证据目录改为 `context-run-02`，以便与新生成的 `codex.json` 配对。
3. 原样运行第 1 节命令，确认退出码为 `0` 且 `host.json` 存在；不要加 `--force` 覆盖来源不明的旧文件。
4. 把 PowerShell 输出以及 `host.json` 的实际完整路径发给 Codex。不要直接粘贴整个 JSON；Codex 会读取文件、运行 `compare` 并检查脱敏边界。
5. 首次比较完成后，确认是否允许把脱敏后的案例摘要加入公开文档。原始快照不会被自动提交或上传。

如果 `context-run-02\host.json` 已存在，不要覆盖；告诉 Codex 后改用新的轮次目录，并在两端都使用相同 timeout 重新采集，不要混用不同轮次或不同 timeout 的文件。

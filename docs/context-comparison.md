# Host 与 Agent 上下文成对采集

这份协议用于比较同一台 Windows 机器上“普通宿主终端”和 Coding Agent 实际命令执行器看到的环境。它复用现有 `snapshot` 与 `compare`，不启动外部 Agent、不登录账户、不修改 PATH、权限或执行策略。

需要把流程直接发给外部试运行者时，优先使用 [`external-pilot-guide.md`](external-pilot-guide.md)；本文件保留协议细节和项目实测记录。

首组严格证据已完成；本协议继续作为外部试运行的采集基线。在形成重复参与者反馈前，不继续增加新探针。

## 为什么必须双端手动触发

一个进程只能采集自己的环境。若在普通 PowerShell 中连续生成 `host.json` 和 `codex.json`，得到的仍是两份宿主快照，不能证明 Codex 的 PATH、Shell 或权限。单一进程不能替代另一个上下文：Agent 快照由对应 Agent 执行器触发，Host 快照由宿主操作者在 Agent 外部的普通 PowerShell 中触发。

首轮建议只比较 Host 与本次参与测试的一个 Agent。Claude 或 DSH 尚未安装、没有命令执行能力或看不到本工具时，记录“未采集”，不要用宿主快照代替。

## 0. 约定目标和证据目录

两端都使用同一台机器、同一目标项目目录和同一轮名称：

```powershell
$TargetProject = "D:\path\to\target-project"
$EvidenceDir = Join-Path $env:TEMP "win-agent-preflight\context-run-01"
Set-Location $TargetProject
```

以本仓库作为测试目标时，将 `$TargetProject` 设为仓库根目录，并在两端都使用 `python -B -m win_agent_preflight`。诊断其他项目时，在两端都使用已经确认指向预期安装的 `agent-preflight`；不要让 Host 与 Agent 使用不同代码版本，也不要为了完成采集临时修改 PATH。

推荐每轮使用新的目录名，默认不加 `--force`，避免覆盖旧证据。

## 1. 在普通 PowerShell 采集 host

```powershell
Set-Location $TargetProject
python -B -m win_agent_preflight snapshot `
  --label host `
  --output (Join-Path $EvidenceDir "host.json") `
  --pretty `
  --timeout 5
```

若诊断的不是本仓库，且工具已安装为命令行入口，将 `python -B -m win_agent_preflight` 替换为 `agent-preflight`。

## 2. 在真实 Agent 执行器采集

参与者在对应 Agent 会话中，由该 Agent 的命令执行器运行：

```powershell
$TargetProject = "D:\path\to\target-project"
$EvidenceDir = Join-Path $env:TEMP "win-agent-preflight\context-run-01"
Set-Location $TargetProject
python -B -m win_agent_preflight snapshot `
  --label codex `
  --output (Join-Path $EvidenceDir "codex.json") `
  --pretty `
  --timeout 5
```

上例是本仓库自测入口。诊断其他项目时，与 host 端相同，把 `python -B -m win_agent_preflight` 替换为两端均已验证的 `agent-preflight`。

Claude 与 DSH 的流程相同，只分别改为 `--label claude`/`claude.json` 和 `--label dsh`/`dsh.json`。每条命令必须由对应 Agent 的执行器启动。

2026-08-24 的 Codex 实测表明项目内 `.artifacts` 可能拒绝写入，而 `%TEMP%` 可写，因此协议默认使用 `%TEMP%`。若不同上下文的 `%TEMP%` 指向不同位置，Agent 只报告其实际输出路径，再由宿主操作者明确复制该文件；首版不自动搬运。

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

工具不会自动上传、压缩、哈希或删除证据。完成检查后，由证据目录的创建者显式删除该次 `$EvidenceDir`；不要使用宽泛目录作为清理目标。

## 历史实测状态（截至 2026-08-27）

- Codex 端 `context-run-01\codex.json` 已在 `%TEMP%` 成功生成并由 `load_snapshot` 重新读取。
- label 为 `codex`，cwd 为本仓库根目录，schema 为 v1，明文用户目录未出现在 JSON 中，临时文件残留为 0。
- 该文件与自身比较返回等价 `0`。
- 2026-08-27 已完成 `context-run-01` 初步比较并发现 8 项差异，但两份快照相隔三天；宿主侧 1 秒 timeout 还造成 pnpm 冷启动超时，因此该轮只用于发现流程问题，不作为严格公开案例。
- `context-run-02` 的两端采集时间接近，但 host cwd 为 `%SYSTEMROOT%\System32`，且 2 秒 timeout 仍让宿主 pnpm 超时；该轮只用于验证 cwd 和 timeout 必须进入采集协议。
- 2026-08-27 的 Codex 执行上下文在项目根以 5 秒 timeout 生成并验证 `context-run-03\codex.json`；pnpm/Codex 均 pass，用户名、常见 token/key 和邮箱模式命中均为 0，自比较等价。
- 宿主操作者随后在同一项目根以相同 5 秒 timeout 生成 `context-run-03\host.json`。两端使用同一 Python 解释器，采集相隔约 9 分钟；严格 compare 退出 1 并报告 8 项有效差异。
- 首组公开归约结果见 [`host-codex-case-study.md`](host-codex-case-study.md)。原始快照没有提交或上传。

## 可选外部试运行

1. 参与者打开 Coding Agent 外部的普通 PowerShell 窗口，不要在 Agent 内置终端运行 host 命令。
2. 参与者将第 0 节 `$TargetProject` 改为实际项目绝对路径，为本次试运行使用新的轮次目录名；必须实际执行 `Set-Location $TargetProject`。
3. 参与者让真实 Agent 执行器按第 2 节在同一轮目录生成对应快照；两端必须使用相同代码版本和 timeout。
4. 参与者在普通 PowerShell 原样运行第 1 节命令，确认退出码为 `0` 且 `host.json` 存在；不要加 `--force` 覆盖来源不明的旧文件。
5. 参与者按第 3 节运行 compare，并记录是否一次完成、差异是否能解释当前问题。不要直接公开整个 JSON；先按第 4 节检查边界。
6. 只有参与者明确同意公开时，才提交人工归约后的案例摘要；原始快照不会被工具自动提交或上传。

如果本轮任一输出已存在，不要覆盖；改用新的轮次目录，并在两端都使用相同 cwd、工具版本和 timeout 重新采集，不要混用不同轮次或参数的文件。

外部采集是可选反馈入口，不是 `0.1.0` 发布或发布后暂缓决定的前置条件。若未来功能设计必须依赖外部验证，应先完成当时的整理与最新版本发布，再暂停等待证据。

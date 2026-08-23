# 设计说明

## 目标

首阶段只建立一个稳定的诊断核心：`scan` 采集 Windows 命令发现、真实启动和 PowerShell 执行策略事实，并以相同模型渲染 Console/JSON。后续的 snapshot、compare 和 probe 应复用这些模型，不在本阶段提前引入。

## 模块边界

```text
cli.py
  └─ checks.py（诊断分类与扫描编排）
       ├─ windows.py（PATH 候选和 PowerShell 事实）
       ├─ runner.py（所有外部命令的唯一执行边界）
       └─ models.py（不可变、可序列化模型）
  └─ reporting.py（Console/JSON，不改变诊断语义）
```

- `models.py` 不调用系统；字段和序列化顺序稳定。
- `runner.py` 接收可注入的执行函数，统一超时、返回码、stdout/stderr 和启动异常。
- `windows.py` 负责当前进程环境中的 Windows 事实采集；路径只作为脱敏后的证据流出。
- `checks.py` 将事实转换为 `pass`、`warning`、`fail`、`unknown`，不负责 CLI 参数或输出格式。
- `cli.py` 只负责解析 `scan` 参数、选择输出并调用扫描。
- `reporting.py` 只渲染已有结果，不再次运行命令。

## 状态语义

| 状态 | 语义 |
| --- | --- |
| `pass` | 已实际验证满足条件 |
| `warning` | 可运行但存在缺失、冲突或可选能力未安装 |
| `fail` | 已有证据证明本项不能按预期工作 |
| `unknown` | 证据不足或当前平台不支持该事实 |

可选 Agent（`codex`、`claude`、`dsh`）缺失只能产生 `warning`。任何 `fail` 必须有至少一条证据字符串；模型构造函数会拒绝没有证据的 fail。

## 命令发现

扫描当前进程 `PATH`，按 Windows 的 `PATHEXT` 和显式扩展名列出候选路径。发现不等于可用：每个候选的首选项再由 Runner 真实启动一次。`npm` 会把 `npm.cmd`、`npm.exe`、`npm.bat`、`npm.ps1` 作为候选；显式扫描项也会单独报告。

`npm.ps1` 不通过普通进程直接运行，而是经 PowerShell 的 `-NoProfile -Command` 调用，以便识别脚本执行策略阻止；不会修改策略。

裸 `npm` 另有独立的 `powershell.command.npm` 检查：在选定 PowerShell 中执行 `Get-Command npm` 和 `npm --version`。因此 `npm.cmd` 候选可启动不等于 PowerShell 裸命令可用。

## 脱敏

报告渲染前统一将当前用户目录（大小写不敏感）替换为 `%USERPROFILE%`，同时替换 `USERPROFILE` 变量值和常见临时目录中的用户名段。只输出变量名和脱敏状态，不输出 token、密码、API key 或完整环境变量值。

## 未来扩展

后续 snapshot/compare 应将宿主快照与 Agent 内部导出的快照视为两个输入，不让当前 `scan` 隐式联网或调用模型。真实 probe 需要单独的最小工作区和清理策略；完成前不加入当前切片。

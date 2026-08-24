# Windows Agent Preflight

Windows-first preflight and differential diagnostics for AI coding agents.

`Windows Agent Preflight` 面向使用 Codex、Claude Code、DeepSeek Harness 等工具的开发者，先从确定性的本地事实采集开始，帮助区分：命令未安装、PATH 未刷新、PowerShell 脚本被阻止、命令启动失败，还是 Agent 内部环境与宿主不同。

## 当前状态

当前版本已完成第三个可运行里程碑，提供 `scan`、`snapshot` 和 `compare` 命令：

- 发现并列出 Windows PATH 中的候选命令路径；
- 通过统一的超时 Runner 做真实启动和版本采集；
- 采集 PowerShell 执行策略事实；
- 只读采集 HKLM/HKCU 的注册表 PATH，比较当前进程是否已继承机器/用户 PATH；
- 按 Windows 规则展开 PATH 中的 `%NAME%`（最多 8 轮），并在证据中保留机器/用户来源；
- 输出人类可读 Console 或稳定 JSON；
- 将有限的宿主事实和同次 `scan` 保存为 v1 快照；
- 比较两个快照的命令、Shell、PATH/PATHEXT 和检查证据差异；
- 对用户目录进行 `%USERPROFILE%` 脱敏，不采集密钥值，不联网，不修改系统配置。

真实 Agent 宿主终端快照和沙箱能力探针仍需后续手动采集/实现，进度见 [`docs/PROGRESS.md`](docs/PROGRESS.md)。

## 环境

- 设计目标：Windows；
- 安装元数据要求 Python `>=3.12`；当前验证环境为 Python 3.12.7，Python 3.14 尚未验证；
- 运行时：`typer>=0.16,<1`；
- 开发：`pytest>=8,<9`、`ruff>=0.12,<1`。

## 使用

```powershell
python -m pip install -e ".[dev]"
python -m win_agent_preflight scan
python -m win_agent_preflight scan --json
agent-preflight scan --json --pretty
agent-preflight snapshot --label host --output .\snapshots\host.json --pretty
agent-preflight compare .\snapshots\host.json .\snapshots\host.json --json
```

只检查当前项目实际需要的工具尚未实现；首阶段扫描固定集合：`python`、`git`、`node`、`npm`、`npm.cmd`、`npm.ps1`、`pnpm`、`codex`、`claude`、`dsh`。

`snapshot` 的 `--label` 和 `--output` 必填；输出目录会创建，已有文件默认不会覆盖，需显式加 `--force`。即使嵌入的 `scan` 有 `fail`，快照仍会写出并以 0 退出；写入或输入错误以 2 退出。

`compare` 的退出码为：等价 0、有实质差异 1、输入/版本/类型错误 2。比较会忽略 label、采集时间、summary 和 candidate_count，并对 Windows 路径、PATH/PATHEXT、候选集合和 evidence 做规范化。

可选 Agent 未安装会显示为 `warning`，不是 `fail`。`fail` 结果必须携带证据；无法判断时使用 `unknown`。

`windows.path_refresh` 只在 Windows 上读取 `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment` 和 `HKCU\Environment` 的 `Path`。读取是只读的，不修改注册表、PATH 或执行策略。缺失键/值视为空的完整事实；读取异常、类型错误或未解析变量会报告为 `unknown`，但如果另一 scope 已证明存在未继承目录，结果仍为 `warning`。旧的 `user_path` 参数仍可用于测试注入。

## 项目文档

- [`PROJECT.md`](PROJECT.md)：目标、范围、成功标准、暂停恢复入口；
- [`docs/design.md`](docs/design.md)：首阶段架构和数据边界；
- [`docs/research.md`](docs/research.md)：需求研究和取舍；
- [`docs/PROGRESS.md`](docs/PROGRESS.md)：按里程碑记录实际验证与下一步。

## 开发

```powershell
python -m pytest
python -m ruff check . --no-cache
python -m win_agent_preflight scan --json
```

本项目处于本地开发阶段，不提供自动修改执行策略、PATH、注册表或 Agent 配置的命令。

## 已知限制

- 注册表 PATH 采集仅在 Windows 可用；非 Windows 平台明确返回 `unknown`。权限或类型异常不会被当成空 PATH；
- PATH 中无法解析的变量只报告变量名，不展示其值，也不会把部分展开结果当作可比较路径；
- 当前快照命令采集的是执行它的宿主终端；要比较真实 host/agent，用户需要分别在宿主终端和 Agent 实际终端中运行 `snapshot`，再交给 `compare`；
- 尚未执行真实 Agent 沙箱能力探针，快照差异本身不等于权限结论；
- 不可访问的 WindowsApps 执行别名会被安全跳过，但尚未单独分类为“发现但不可检查”。

## 许可证

[MIT License](LICENSE)

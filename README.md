# Windows Agent Preflight

Windows-first preflight and differential diagnostics for AI coding agents.

`Windows Agent Preflight` 面向使用 Codex、Claude Code、DeepSeek Harness 等工具的开发者，先从确定性的本地事实采集开始，帮助区分：命令未安装、PATH 未刷新、PowerShell 脚本被阻止、命令启动失败，还是 Agent 内部环境与宿主不同。

## 当前状态

当前版本是首个可运行切片，提供 `scan` 命令：

- 发现并列出 Windows PATH 中的候选命令路径；
- 通过统一的超时 Runner 做真实启动和版本采集；
- 采集 PowerShell 执行策略事实；
- 输出人类可读 Console 或稳定 JSON；
- 对用户目录进行 `%USERPROFILE%` 脱敏，不采集密钥值，不联网，不修改系统配置。

快照、宿主/Agent 对比和真实沙箱探针属于后续阶段，进度见 [`docs/PROGRESS.md`](docs/PROGRESS.md)。

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
```

只检查当前项目实际需要的工具尚未实现；首阶段扫描固定集合：`python`、`git`、`node`、`npm`、`npm.cmd`、`npm.ps1`、`pnpm`、`codex`、`claude`、`dsh`。

可选 Agent 未安装会显示为 `warning`，不是 `fail`。`fail` 结果必须携带证据；无法判断时使用 `unknown`。

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

- 当前尚未读取 Windows 注册表中的用户 PATH，因此真实 PATH 刷新判断仍为 `unknown`；
- 只采集宿主环境，宿主/Agent 快照比较和工作区能力探针属于下一里程碑；
- 不可访问的 WindowsApps 执行别名会被安全跳过，但尚未单独分类为“发现但不可检查”。

## 许可证

[MIT License](LICENSE)

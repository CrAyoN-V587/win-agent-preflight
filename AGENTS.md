# Windows Agent Preflight Agent 规则

本文件只写项目特有约定；通用协作规则由上级工作区 `AGENTS.md` 提供。

## 项目概述

- 目标：诊断 Windows 宿主与 Coding Agent 使用的命令、Shell 和项目工具链事实。
- 核心入口：`src/win_agent_preflight/cli.py`，CLI 名称 `agent-preflight`。
- 当前阶段：`scan`、`snapshot`/`compare` 和只读注册表 PATH 刷新诊断已稳定；第四里程碑的 `workspace-probe` 已实现。

## 环境和命令

- 安装/准备：`python -m pip install -e ".[dev]"`
- 运行：`python -m win_agent_preflight scan`、`agent-preflight snapshot --label host --output .\\snapshots\\host.json`、`agent-preflight compare baseline.json current.json`、`agent-preflight workspace-probe --target . --allow-write`
- 针对性测试：`python -B -m pytest -q -p no:cacheprovider`
- 完整测试：先运行 `python -B -m pytest -q -p no:cacheprovider`，通过后再运行 `python -m ruff check . --no-cache`。
- 构建或检查：`python -m ruff check . --no-cache`
- 清理缓存：本阶段不建设项目缓存；pytest/ruff 生成的缓存可直接删除。

## 项目约定

- 目录职责：`models.py` scan 数据模型；`runner.py` 外部命令边界；`windows.py` Windows 事实采集；`checks.py` 诊断分类；`snapshot.py` EnvironmentSnapshot v1、解析、写出与比较；`compare.py` 差异输出；`workspace_probe.py` 独立 WorkspaceProbeReport v1 与有边界的写入探针；`reporting.py` 输出；`cli.py` 参数与编排。
- 代码风格：Python 类型标注、不可变数据模型优先；公共序列化字段使用稳定 snake_case。
- 数据和配置位置：扫描只读取当前环境，不保存配置和凭据。
- 不得修改的上游或生成文件：不触碰工作区其他项目；不创建项目级 `.codex`。

## 修改边界

- 当前允许的结构调整：围绕 `scan`、`snapshot`/`compare` 稳定边界和只读注册表 PATH 刷新诊断的最小模块调整。
- 需要保留的数据或接口：`CheckResult` JSON 字段、`Runner` 注入边界和 `%USERPROFILE%` 脱敏规则。
- 默认不兼容的旧实现：项目尚无旧版本；不为假设中的 Linux/macOS 兼容矩阵设计。

## 项目级效率规则

- 外部命令只能通过 `Runner` 执行，并且必须有超时。
- `scan` v1 JSON 和退出语义保持稳定；快照只内嵌已有 scan，不另造检查协议。
- 快照默认不覆盖已有输出，比较输入错误/版本错误/类型错误退出 2。
- 不联网、不修改 PATH、注册表、执行策略或 Agent 配置。
- `workspace-probe` 只接受显式 `--target` 与 `--allow-write`；结论只适用于一次命令、一个目标目录和当前进程上下文。
- `workspace-probe` 只创建目标直接子目录中的本次随机探针；按 Windows 对象身份复核本次已知两个文件和空目录后做路径级清理，不遍历目标、不递归删除、不处理历史残留。
- `workspace-probe` 面向非对抗的本地诊断；不支持其他进程在“身份复核—路径操作”的瞬间替换同名对象，也不为消除该 TOCTOU 窗口引入句柄级安全实现。
- `workspace-probe` 的固定六项使用独立 v1 schema，不修改 `scan`/`snapshot` 的 JSON 字段和退出语义。
- 不采集或打印密钥值；不计算哈希。
- 未安装的可选 Agent 为 `warning`，不是 `fail`。
- `fail` 必须带证据；证据不足使用 `unknown`。

## Git

- 分支约定：由主 Agent 建立仓库后确认。
- 提交粒度：一个可运行、可验证的切片一个逻辑提交。
- 提交前必须运行：`python -B -m pytest -q -p no:cacheprovider`、`python -m ruff check . --no-cache` 和一次真实 CLI。
- 远程推送由主 Agent 按用户已给授权执行。

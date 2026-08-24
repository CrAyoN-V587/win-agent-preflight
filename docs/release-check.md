# 本地包验收

本文只描述本地构建和安装验收，不执行 PyPI 发布、自动发布、签名或 SBOM 生成。CI 的对应流程位于 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)，仅运行在 Windows runner。

## 环境

- Python 3.12 是当前已验证版本；Python 3.14 已加入 CI 矩阵，但等待首次 CI 运行确认。
- Windows 上优先使用 Python Launcher 区分并行版本：`py -3.12`、`py -3.14`。
- 需要 Git 和本项目开发依赖；当前项目不需要 Node.js、Docker 或 WSL。

## 构建

在项目根目录执行：

```powershell
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m build --sdist --wheel
```

`dist` 中应恰好有一个 `.tar.gz` 源码包和一个 `.whl` wheel 包。默认隔离构建会按 `pyproject.toml` 准备 `setuptools>=68`，避免依赖当前 Python 环境中碰巧存在的构建后端版本；因此首次构建通常需要联网。

## 干净虚拟环境安装

分别为两个制品创建新的虚拟环境，并运行 CLI 帮助。PowerShell 中先解析制品路径，避免把通配符原样传给 pip：

```powershell
$sdists = @(Get-ChildItem -LiteralPath .\dist -Filter *.tar.gz -File)
$wheels = @(Get-ChildItem -LiteralPath .\dist -Filter *.whl -File)
if ($sdists.Count -ne 1) { throw "expected exactly one sdist" }
if ($wheels.Count -ne 1) { throw "expected exactly one wheel" }

py -3.12 -m venv .artifacts\sdist-check
.\.artifacts\sdist-check\Scripts\python.exe -m pip install $sdists[0].FullName
.\.artifacts\sdist-check\Scripts\python.exe -m win_agent_preflight --help

py -3.12 -m venv .artifacts\wheel-check
.\.artifacts\wheel-check\Scripts\python.exe -m pip install $wheels[0].FullName
.\.artifacts\wheel-check\Scripts\python.exe -m win_agent_preflight --help
```

安装制品时不使用 `--no-deps`：运行时依赖 Typer 需要由包管理器解析。若网络不可用，应先准备可用的依赖源或 wheel；本项目不额外建设离线镜像、缓存或依赖打包层。`.artifacts\sdist-check` 和 `.artifacts\wheel-check` 是本地验收临时目录，已被忽略，不纳入提交。

## CI 边界

CI 在 Python 3.12 和 3.14 上运行测试；Ruff 只在 3.12 上运行，两个版本都会运行 CLI 帮助和 `%RUNNER_TEMP%` 工作区探针。打包 job 在测试成功后构建并分别安装 sdist/wheel 到干净虚拟环境；非 PR 运行只保留 7 天构建制品。CI 不发布 PyPI，不创建 Release，不生成签名、SBOM 或跨平台构建。

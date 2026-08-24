# 本地包验收

本文只描述本地构建和安装验收，不执行 PyPI 发布、自动发布、签名或 SBOM 生成。CI 的对应流程位于 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)，仅运行在 Windows runner。

## 环境

- 本机当前已验证 Python 3.12；Windows CI run `32693383743` 已完整验证 Python 3.12/3.14 矩阵、严格 cp1252 help 和 package job。
- Windows 上优先使用 Python Launcher 区分并行版本：`py -3.12`、`py -3.14`。
- 需要 Git 和本项目开发依赖；当前项目不需要 Node.js、Docker 或 WSL。

## 构建

在项目根目录执行：

```powershell
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m build --sdist --wheel
```

`dist` 中应恰好有一个 `.tar.gz` 源码包和一个 `.whl` wheel 包。默认隔离构建会按 `pyproject.toml` 准备 `setuptools>=68`，避免依赖当前 Python 环境中碰巧存在的构建后端版本；因此首次构建通常需要联网。

中文 Windows 上若隔离环境中的 pip 先输出本地代码页错误，`build` 可能只显示 `UnicodeDecodeError`，遮住真正原因。可只为当前 PowerShell 进程设置 `$env:PYTHONUTF8='1'` 后重试；这不会修改系统设置。若随后出现网络权限或依赖下载错误，应处理该真实原因，不要因此改成非隔离构建。

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

## cp1252 帮助复验

Windows 旧代码页控制台也应能显示 CLI 帮助。公开的 Typer help/docstring 保持 ASCII；报告正文仍按项目输出约定保留中文。以下命令使用严格 `cp1252`，只请求帮助，不执行扫描、探针、联网或写文件：

```powershell
$env:PYTHONIOENCODING = "cp1252:strict"
python -B -m win_agent_preflight --help
.\.artifacts\sdist-check\Scripts\python.exe -B -m win_agent_preflight --help
.\.artifacts\wheel-check\Scripts\python.exe -B -m win_agent_preflight --help
Remove-Item Env:PYTHONIOENCODING
```

`tests/test_cli_help.py` 会在隔离子进程中用同一设置检查根命令和全部子命令，并严格解码 stdout/stderr；它还确认帮助调用不会在临时工作目录创建文件。

## CI 边界

CI 在 Python 3.12 和 3.14 上运行测试；Ruff 只在 3.12 上运行，两个版本都会运行 CLI 帮助和 `%RUNNER_TEMP%` 工作区探针。首次 run [`32691934171`](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32691934171) 暴露根 help 的 cp1252 `UnicodeEncodeError`；修复提交 `affa4a3` 对应的 run [`32693383743`](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32693383743) 已完成两个矩阵 job、sdist/wheel 构建、两个干净环境安装和制品上传。

GitHub CLI 已认证，远程包验收已有成功证据。CI 不发布 PyPI，不创建 Release，不生成签名、SBOM 或跨平台构建。

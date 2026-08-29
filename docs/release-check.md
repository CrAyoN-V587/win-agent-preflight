# 本地包验收

本文只描述本地构建和安装验收，不执行 PyPI 发布、自动发布、签名或 SBOM 生成。CI 的对应流程位于 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)，仅运行在 Windows runner。

## 环境

- 首次维护环境已验证 Python 3.12；main Windows CI run `32703174150` 已完整验证包含 `command-doctor` 的 Python 3.12/3.14 矩阵、严格 cp1252 help 和 package job，但这是既有功能基线。
- `git-doctor` 提交 `67697c7` 已通过 main Windows CI run `32708225452` 的 Python 3.12/3.14 矩阵、严格 cp1252 help 和 package job；这同样不是本轮发布材料提交的 CI 验收。GitHub 认证仍不在离线验收范围内。
- Windows 上优先使用 Python Launcher 区分并行版本：`py -3.12`、`py -3.14`。
- 需要 Git 和本项目开发依赖；当前项目不需要 Node.js、Docker 或 WSL。

## v0.1.0 发布交接

本文件记录 `v0.1.0` 的本地验收和远端发布边界。维护者已定稿 Changelog、提交并推送最终材料，在该提交 Windows CI 成功后从同一提交创建 `v0.1.0` Tag/Release 并上传已验制品；本地认证状态不是项目事实，也不应写入公开文档。

发布前应确认：

- 工作区只包含预期的 `0.1.0` 文档和代码变更，且 `git diff --check` 通过；
- sdist/wheel 已在两个干净虚拟环境安装并运行 CLI 帮助；
- 维护者已确定日期并定稿 0.1.0 Changelog，本轮最终发布材料已提交并推送；
- 该发布材料提交的 Windows CI 有实际成功证据；既有功能基线 CI 不能替代本轮发布提交验收；
- Release 说明引用 `CHANGELOG.md`，并明确 Windows-only、offline/no-login/no-auto-fix 边界；
- 上述 CI 已成功，`v0.1.0` Tag/Release 已从同一提交创建并上传已验制品；项目状态已切换为“发布后暂缓功能开发”。

如果后续实现必须依赖无法取得的外部验证，先完成上述整理与最新版本发布，再暂停等待外部证据；外部试运行手册是可选反馈入口，不是发布前置条件。

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

## project-doctor 本地边界

`project-doctor` 已包含在此前的 Windows CI run `32696504545`，Python 3.12/3.14 测试与后续包验收均通过。真实仓库根的本地验证命令为：

```powershell
python -B -m win_agent_preflight project-doctor --target . --json --pretty --timeout 1
```

该命令只读取第一层十个固定 marker 并探测推导工具的 `--version`，不写文件、不递归、不打开 marker 内容，也不以目标目录作为工具 cwd。marker 的权限异常、symlink、reparse point 或非普通项会进入首项 `project.markers` 的 `unknown`，而不是把有效 target 判为输入错误；未列入固定表的文件直接忽略。

## command-doctor 本地边界

`command-doctor` 已在首次维护环境完成实现和回归，并随提交 `a311f96` 通过 Windows CI run `32703174150`。它只接受安全的单个 ASCII basename，只在 Windows PATH 中探测 launcher，并通过有界 Runner 固定执行 `--version`：

```powershell
python -B -m win_agent_preflight command-doctor npm --json --pretty --timeout 1
python -B -m win_agent_preflight command-doctor npm.cmd --json --pretty --timeout 1
python -B -m win_agent_preflight command-doctor pnpm --json --pretty --timeout 1
```

首次维护环境中的三条命令均退出 0、状态为 `usable`、`windows.path_refresh=pass`；npm/npm.cmd 为 `11.17.0`，pnpm 为 `11.22.0`，pnpm 报告主安装和 fallback 候选。无扩展名会按 PATHEXT 探测 `.exe`/`.cmd`/`.bat` 并追加 `.ps1`，必要时进行一次 PowerShell 裸命令或执行策略只读检查；显式 `.cmd`/`.exe` 不执行裸命令检查。该命令不登录、不联网、不写文件，能力失败退出 1，输入或非 Windows 错误退出 2。

## git-doctor 本地边界

`git-doctor` 需要显式 target，只读取普通目录和 Git 的固定本地事实：Git launcher `--version`、`git -C TARGET` 的 worktree/identity/origin/helper 查询，以及 GitHub remote 下的 `gh --version`。它不运行 `gh auth`、credential fill、GCM diagnose、push/fetch/pull/ls-remote/ssh，不联网、不读取 token 或 Windows Credential Manager、不写文件；`remote_auth_verified` 永远为 `false`。

定向回归命令：

```powershell
python -B -m pytest tests/test_git_doctor.py tests/test_cli_help.py -q -p no:cacheprovider
python -m ruff check src/win_agent_preflight/git_doctor.py tests/test_git_doctor.py --no-cache
git diff --check
```

当前结果为 38 passed（Git Doctor 37 项，CLI help 1 项）、全量 237 passed、Ruff 通过、diff check 无内容错误；真实仓库根只读验收退出 0，`local_ready=true`，认证仍固定为 `not_checked_offline`。提交 `67697c7` 的 Windows CI `32708225452` 已完成两个 Python 矩阵 job、sdist/wheel 双安装和制品上传；不要把本地报告中的 `github.auth=not_checked_offline` 解释为登录失败或登录成功。

## workspace-scope 本地边界

`workspace-scope` 提交 `b981bf1` 已通过 Windows CI `32712146556`；本地与远程全量均为 261 passed。它要求两个现有普通目录和显式 `--allow-write`：

```powershell
python -B -m win_agent_preflight workspace-scope --target . --control $env:TEMP --allow-write --json --pretty
```

命令先对两个目录执行只读 `lstat`、重解析点检查和 `resolve(strict=True)`，预验证失败时不调用 probe、不写入；通过后按固定 target → control 顺序各调用一次既有 `workspace-probe`。普通失败仍执行第二个目录；子报告归约为 usable、failed（FAIL 或 residual）或 unknown，任一 unknown 使完整结果为 `inconclusive` 且 `complete=true`，异常或 Ctrl-C 则为 `complete=false` 的 partial 并停止。`both_usable` 退出 0，其余完整状态或 partial 退出 1，输入 2，Ctrl-C 130。该命令不联网、不递归、不枚举目录，不改变既有 probe schema。真实矩阵中 Triton target 与 `%TEMP%` control 为 `both_usable`；MyMineCraft/MCP Lab target 为 WinError 5、control 可用，均归为 `target_specific_failure`；四个目录均无探针残留。远程 CI `32712146556` 已完成两个 Python 矩阵 job、Ruff、sdist/wheel 双安装和制品上传。

## snapshot 写入边界

快照写出在目标父目录内创建本次 UUID 临时文件，使用 `O_EXCL` 且最多尝试三个名称；只有 `FileExistsError` 会触发下一名称，权限或其他写入错误应立即以 CLI 退出码 2 返回。写入通过 UTF-8 `fdopen`、write、flush 和 fsync 完成，`--force` 使用 replace，默认模式使用 link 后 unlink；失败只清理本次已知临时文件，不扫描目录或处理历史 `.tmp`。

本地拒绝写入边界可用一个明确的输出路径复验：命令应在 capture 后快速退出 2，不能产生输出或临时残留。可写 `%TEMP%` 目录则应能写出并由 `load_snapshot` 读取；这两类验证只代表当前进程和目录上下文，不代表其他 Agent 上下文。

## CI 边界

CI 在 Python 3.12 和 3.14 上运行测试；Ruff 只在 3.12 上运行，两个版本都会运行 CLI 帮助和 `%RUNNER_TEMP%` 工作区探针。首次 run [`32691934171`](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32691934171) 暴露根 help 的 cp1252 `UnicodeEncodeError`；包含 `command-doctor` 的 main run [`32703174150`](https://github.com/CrAyoN-V587/win-agent-preflight/actions/runs/32703174150) 已完成两个矩阵 job、sdist/wheel 构建、两个干净环境安装和制品上传。

远程包验收已有成功证据。GitHub CLI 认证属于执行远程操作的维护者本地状态，不作为项目验收前提。CI 不发布 PyPI，不创建 Release，不生成签名、SBOM 或跨平台构建。

"""Windows command discovery and PowerShell fact collection."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from .models import CheckResult, CheckStatus, CommandCandidate
from .runner import CommandExecution, Runner

DEFAULT_PATHEXT = (
    ".COM",
    ".EXE",
    ".BAT",
    ".CMD",
    ".VBS",
    ".VBE",
    ".JS",
    ".JSE",
    ".WSF",
    ".WSH",
    ".MSC",
)
SCRIPT_COMMANDS = frozenset({"npm", "pnpm", "npx", "yarn"})


def redact_text(value: str, *, user_profile: str | None = None) -> str:
    """Replace the current user's home directory without exposing its name."""

    if not value:
        return value
    profile = user_profile or os.environ.get("USERPROFILE")
    if not profile:
        return value
    return re.sub(re.escape(profile), "%USERPROFILE%", value, flags=re.IGNORECASE)


def discover_command(
    name: str,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
) -> tuple[CommandCandidate, ...]:
    """Return all existing PATH candidates in search order.

    Discovery is deliberately filesystem-only. It never treats discovery as
    proof that a command can start; the caller must use ``Runner`` for that.
    """

    environment = env if env is not None else os.environ
    path_value = environment.get("PATH", "")
    path_separator = ";" if os.name == "nt" else os.pathsep
    pathext = tuple(
        extension.upper()
        for extension in environment.get("PATHEXT", "").split(";")
        if extension
    ) or DEFAULT_PATHEXT
    explicit_extension = bool(Path(name).suffix)
    names = [name]
    if not explicit_extension:
        names.extend(f"{name}{extension.lower()}" for extension in pathext)
        if name.lower() in SCRIPT_COMMANDS:
            names.append(f"{name}.ps1")

    candidates: list[CommandCandidate] = []
    seen: set[str] = set()
    for raw_directory in path_value.split(path_separator):
        directory = raw_directory.strip().strip('"')
        if not directory:
            continue
        for candidate_name in names:
            candidate_path = Path(directory) / candidate_name
            try:
                is_file = candidate_path.is_file()
            except OSError:
                # WindowsApps execution aliases and inaccessible PATH entries can
                # fail stat() even though their names are visible. One broken
                # candidate must not abort discovery of the remaining PATH.
                continue
            if not is_file:
                continue
            key = os.path.normcase(str(candidate_path))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                CommandCandidate(
                    name=name,
                    path=redact_text(str(candidate_path), user_profile=user_profile),
                )
            )
    if not candidates and os.name != "nt":
        found = shutil.which(name, path=path_value)
        if found:
            candidates.append(
                CommandCandidate(name=name, path=redact_text(found, user_profile=user_profile))
            )
    return tuple(candidates)


def collect_path_refresh_check(
    *,
    process_path: str | None = None,
    user_path: str | None = None,
    user_profile: str | None = None,
) -> CheckResult:
    """Compare a user PATH snapshot with the current process PATH.

    ``user_path`` is injectable so tests do not need to modify the registry.
    The first slice does not read or write the registry itself.
    """

    if process_path is None:
        process_path = os.environ.get("PATH")
    if not process_path or user_path is None:
        return CheckResult(
            id="windows.path_refresh",
            status=CheckStatus.UNKNOWN,
            summary="无法获得用户 PATH 与当前进程 PATH 的可比事实",
            evidence=("需要同时提供 process PATH 和 user PATH",),
        )
    separator = ";" if os.name == "nt" else os.pathsep
    current = {
        os.path.normcase(item.strip().strip('"'))
        for item in process_path.split(separator)
        if item
    }
    configured = [item.strip().strip('"') for item in user_path.split(separator) if item]
    missing = [item for item in configured if os.path.normcase(item) not in current]
    if missing:
        shown = ", ".join(redact_text(item, user_profile=user_profile) for item in missing[:5])
        return CheckResult(
            id="windows.path_refresh",
            status=CheckStatus.WARNING,
            summary="用户 PATH 中存在当前进程尚未继承的目录",
            evidence=(
                f"current process is missing {len(missing)} configured PATH entries: {shown}",
            ),
            details={"missing_count": len(missing)},
        )
    return CheckResult(
        id="windows.path_refresh",
        status=CheckStatus.PASS,
        summary="当前进程 PATH 包含用户 PATH 中的目录",
    )


def collect_powershell_check(
    runner: Runner,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> CheckResult:
    """Collect execution-policy facts without changing policy."""

    candidates = discover_command("pwsh", env=env, user_profile=user_profile)
    candidates += discover_command("powershell.exe", env=env, user_profile=user_profile)
    if not candidates:
        return CheckResult(
            id="windows.powershell.execution_policy",
            status=CheckStatus.UNKNOWN,
            summary="未发现 PowerShell，无法采集执行策略",
            evidence=("pwsh and powershell.exe were not found in PATH",),
        )
    selected = candidates[0]
    execution = runner.run(
        (
            selected.path.replace(
                "%USERPROFILE%",
                user_profile or os.environ.get("USERPROFILE", "%USERPROFILE%"),
            ),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-ExecutionPolicy -List | ForEach-Object { "
            "[pscustomobject]@{Scope=$_.Scope.ToString(); "
            "ExecutionPolicy=$_.ExecutionPolicy.ToString()} } | "
            "ConvertTo-Json -Compress",
        ),
        timeout=timeout,
        env=env,
    )
    evidence = _execution_evidence(execution, user_profile=user_profile)
    if execution.timed_out or execution.error:
        return CheckResult(
            id="windows.powershell.execution_policy",
            status=CheckStatus.FAIL,
            summary="PowerShell 执行策略采集未能在超时内完成",
            evidence=evidence,
        )
    if execution.returncode != 0:
        return CheckResult(
            id="windows.powershell.execution_policy",
            status=CheckStatus.FAIL,
            summary="PowerShell 执行策略命令返回失败",
            evidence=evidence,
        )
    return CheckResult(
        id="windows.powershell.execution_policy",
        status=CheckStatus.PASS,
        summary="已采集 PowerShell 执行策略（未修改）",
        evidence=(
            redact_text(execution.stdout.strip(), user_profile=user_profile) or "命令返回空结果",
        ),
        details={"shell": selected.path},
    )


def collect_powershell_command_check(
    runner: Runner,
    *,
    command: str,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> CheckResult:
    """Check how a bare command resolves inside a clean PowerShell process.

    This is intentionally separate from PATH candidate checks. For example,
    ``npm`` can have a working ``npm.cmd`` candidate while PowerShell still
    resolves the bare command to a policy-blocked ``npm.ps1``.
    """

    candidates = discover_command("pwsh", env=env, user_profile=user_profile)
    candidates += discover_command("powershell.exe", env=env, user_profile=user_profile)
    check_id = f"powershell.command.{command}"
    if not candidates:
        return CheckResult(
            id=check_id,
            status=CheckStatus.UNKNOWN,
            summary=f"未发现 PowerShell，无法验证裸命令：{command}",
            evidence=("pwsh and powershell.exe were not found in PATH",),
        )

    selected = candidates[0]
    shell_path = selected.path.replace(
        "%USERPROFILE%", user_profile or os.environ.get("USERPROFILE", "")
    )
    execution = runner.run(
        (
            shell_path,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Get-Command {command} -ErrorAction Stop | Out-Null; {command} --version",
        ),
        timeout=timeout,
        env=env,
    )
    if execution.succeeded:
        output = execution.stdout.strip() or execution.stderr.strip() or "started"
        return CheckResult(
            id=check_id,
            status=CheckStatus.PASS,
            summary=f"PowerShell 裸命令可启动：{command}",
            evidence=(f"shell: {selected.path}", redact_text(output, user_profile=user_profile)),
            details={"shell": selected.path, "command": command},
        )
    evidence = _execution_evidence(execution, user_profile=user_profile)
    return CheckResult(
        id=check_id,
        status=CheckStatus.WARNING,
        summary=f"PowerShell 裸命令无法启动：{command}",
        evidence=(f"shell: {selected.path}", *evidence),
        details={"shell": selected.path, "command": command},
    )


def run_candidate(
    candidate: CommandCandidate,
    runner: Runner,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> CommandExecution:
    """Start a candidate, routing PowerShell scripts through PowerShell."""

    raw_path = candidate.path.replace(
        "%USERPROFILE%", user_profile or os.environ.get("USERPROFILE", "")
    )
    if raw_path.lower().endswith(".ps1"):
        shell = discover_command("pwsh", env=env, user_profile=user_profile)
        if not shell:
            shell = discover_command("powershell.exe", env=env, user_profile=user_profile)
        if not shell:
            return CommandExecution(
                argv=(raw_path,),
                returncode=None,
                error="PowerShell host was not found for .ps1 candidate",
            )
        escaped = raw_path.replace("'", "''")
        argv: Sequence[str] = (
            shell[0].path.replace(
                "%USERPROFILE%", user_profile or os.environ.get("USERPROFILE", "")
            ),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"& '{escaped}' --version",
        )
    else:
        argv = (raw_path, "--version")
    return runner.run(argv, timeout=timeout, env=env)


def _execution_evidence(
    execution: CommandExecution, *, user_profile: str | None
) -> tuple[str, ...]:
    evidence: list[str] = []
    if execution.error:
        evidence.append(redact_text(execution.error, user_profile=user_profile))
    if execution.returncode is not None and execution.returncode != 0:
        evidence.append(f"exit code: {execution.returncode}")
    if execution.stderr.strip():
        evidence.append(redact_text(execution.stderr.strip()[:500], user_profile=user_profile))
    if execution.timed_out and not evidence:
        evidence.append("external command timed out")
    return tuple(evidence) or ("external command returned no usable output",)

"""Convert Windows facts and Runner results into diagnostic checks."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .models import CheckResult, CheckStatus, CommandCandidate, ScanReport
from .runner import Runner
from .windows import (
    RegistryValueReader,
    collect_path_refresh_check,
    collect_powershell_check,
    collect_powershell_command_check,
    discover_command,
    redact_text,
    run_candidate,
)

COMMANDS: tuple[tuple[str, bool], ...] = (
    ("python", True),
    ("git", True),
    ("node", False),
    ("npm", False),
    ("npm.cmd", False),
    ("npm.ps1", False),
    ("pnpm", False),
    ("codex", False),
    ("claude", False),
    ("dsh", False),
)
OPTIONAL_AGENTS = frozenset({"codex", "claude", "dsh"})


def scan_environment(
    *,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    user_path: str | None = None,
    registry_reader: RegistryValueReader | Mapping[str, object] | None = None,
    timeout: float = 5.0,
) -> ScanReport:
    environment = env if env is not None else os.environ
    active_runner = runner or Runner(default_timeout=timeout)
    results: list[CheckResult] = []
    candidate_map: dict[str, tuple[CommandCandidate, ...]] = {}
    for name, required in COMMANDS:
        candidate_map[name] = discover_command(name, env=environment, user_profile=user_profile)
        results.append(
            check_command(
                name,
                candidate_map[name],
                active_runner,
                required=required,
                optional_agent=name in OPTIONAL_AGENTS,
                env=environment,
                user_profile=user_profile,
                timeout=timeout,
            )
        )
    results.append(
        collect_path_refresh_check(
            process_path=environment.get("PATH"),
            process_env=environment,
            user_path=user_path,
            user_profile=user_profile,
            registry_reader=registry_reader,
        )
    )
    results.append(
        collect_powershell_check(
            active_runner,
            env=environment,
            user_profile=user_profile,
            timeout=timeout,
        )
    )
    results.append(
        collect_powershell_command_check(
            active_runner,
            command="npm",
            env=environment,
            user_profile=user_profile,
            timeout=timeout,
        )
    )
    return ScanReport(schema_version=1, tool="win-agent-preflight", checks=tuple(results))


def check_command(
    name: str,
    candidates: tuple[CommandCandidate, ...],
    runner: Runner,
    *,
    required: bool,
    optional_agent: bool = False,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> CheckResult:
    check_id = f"command.{name.replace('.', '_')}"
    candidate_details = [candidate.to_dict() for candidate in candidates]
    base_details = {"candidate_count": len(candidates), "candidates": candidate_details}
    if not candidates:
        status = CheckStatus.FAIL if required else CheckStatus.WARNING
        return CheckResult(
            id=check_id,
            status=status,
            summary=f"未发现命令：{name}",
            evidence=(f"{name} was not found in the current PATH",),
            details=base_details,
        )

    failures: list[str] = []
    for candidate in candidates:
        execution = run_candidate(
            candidate,
            runner,
            env=env,
            user_profile=user_profile,
            timeout=timeout,
        )
        if execution.succeeded:
            version = _first_line(execution.stdout) or _first_line(execution.stderr) or "started"
            return CheckResult(
                id=check_id,
                status=CheckStatus.PASS,
                summary=f"命令可启动：{name}",
                evidence=(
                    f"selected: {candidate.path}",
                    f"version: {redact_text(version, user_profile=user_profile)}",
                ),
                details={**base_details, "selected": candidate.path},
            )
        failures.extend(_candidate_failure(candidate, execution, user_profile=user_profile))

    status = CheckStatus.FAIL if required else CheckStatus.WARNING
    if optional_agent:
        summary = f"可选 Agent 命令存在但无法启动：{name}"
    else:
        summary = f"命令存在但无法启动：{name}"
    return CheckResult(
        id=check_id,
        status=status,
        summary=summary,
        evidence=tuple(failures) or ("all discovered candidates failed",),
        details=base_details,
    )


def _candidate_failure(
    candidate: CommandCandidate, execution, *, user_profile: str | None
) -> list[str]:
    prefix = f"{candidate.path}: "
    if execution.timed_out:
        return [prefix + "timeout"]
    if execution.error:
        return [prefix + redact_text(execution.error, user_profile=user_profile)]
    if execution.returncode is not None:
        detail = f"exit code {execution.returncode}"
        if execution.stderr.strip():
            detail += f"; {redact_text(execution.stderr.strip()[:300], user_profile=user_profile)}"
        return [prefix + detail]
    return [prefix + "no successful execution evidence"]


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")

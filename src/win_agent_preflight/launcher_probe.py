"""Shared bounded launcher probing for Agent Doctor and Command Doctor."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import CommandCandidate
from .runner import CommandExecution, Runner
from .windows import redact_text, run_candidate


class LauncherProbeState(StrEnum):
    """Stable launcher health states shared by the two doctor reports."""

    COMMAND_NOT_FOUND = "command_not_found"
    RESOLVED_BUT_NOT_EXECUTABLE = "resolved_but_not_executable"
    ACCESS_DENIED = "access_denied"
    VERSION_PROBE_FAILED = "version_probe_failed"
    USABLE = "usable"


@dataclass(frozen=True, slots=True)
class LauncherProbeOutcome:
    """Result of probing a finite ordered candidate list."""

    state: LauncherProbeState
    path: str | None = None
    version: str | None = None
    attempts: tuple[dict[str, Any], ...] = ()


def probe_launchers(
    candidates: Sequence[CommandCandidate],
    runner: Runner,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> LauncherProbeOutcome:
    """Probe each candidate at most once and stop at the first usable one."""

    attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        execution = run_candidate(
            candidate,
            runner,
            env=env,
            user_profile=user_profile,
            timeout=timeout,
        )
        version = _version_line(execution, user_profile=user_profile)
        attempts.append(
            _execution_details(candidate.path, execution, has_output=version is not None)
        )
        if execution.succeeded and version is not None:
            return LauncherProbeOutcome(
                state=LauncherProbeState.USABLE,
                path=candidate.path,
                version=version,
                attempts=tuple(attempts),
            )

    return LauncherProbeOutcome(
        state=_failed_probe_state(attempts),
        path=candidates[0].path if candidates else None,
        attempts=tuple(attempts),
    )


def _failed_probe_state(attempts: Sequence[Mapping[str, Any]]) -> LauncherProbeState:
    if any(
        attempt.get("winerror") in (5, 13, 32, 1920)
        or str(attempt.get("error_type", "")).casefold()
        in {"permissionerror", "accessdeniederror"}
        for attempt in attempts
    ):
        return LauncherProbeState.ACCESS_DENIED
    if any(attempt.get("winerror") in (193, 216) for attempt in attempts):
        return LauncherProbeState.RESOLVED_BUT_NOT_EXECUTABLE
    if any(attempt.get("launcher_host_missing") for attempt in attempts):
        return LauncherProbeState.RESOLVED_BUT_NOT_EXECUTABLE
    return LauncherProbeState.VERSION_PROBE_FAILED


def _execution_details(
    path: str, execution: CommandExecution, *, has_output: bool
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "path": path,
        "returncode": execution.returncode,
        "timed_out": execution.timed_out,
        "version_output_present": has_output,
    }
    error_type = execution.error_type
    if execution.error and "PowerShell host was not found" in execution.error:
        details["launcher_host_missing"] = True
    if error_type is None and execution.error:
        error_type = "RunnerError"
    if error_type is not None:
        details["error_type"] = error_type
    if execution.winerror is not None:
        details["winerror"] = execution.winerror
    return details


def _version_line(execution: CommandExecution, *, user_profile: str | None) -> str | None:
    """Return one bounded, redacted non-empty version line from a probe."""

    for stream in (execution.stdout, execution.stderr):
        for raw_line in stream.splitlines():
            line = raw_line.strip()
            if line:
                return redact_text(line, user_profile=user_profile)[:200]
    return None

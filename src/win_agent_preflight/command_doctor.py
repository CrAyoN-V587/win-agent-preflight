"""Focused diagnostics for one explicitly requested PATH command."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .launcher_probe import LauncherProbeState, probe_launchers
from .models import CheckResult, CheckStatus
from .runner import Runner
from .windows import (
    COMMAND_LAUNCHER_EXTENSIONS,
    DEFAULT_PATHEXT,
    RegistryValueReader,
    collect_path_refresh_check,
    collect_powershell_check,
    collect_powershell_command_check,
    discover_command_details,
)

COMMAND_DOCTOR_SCHEMA_VERSION = 1
COMMAND_DOCTOR_TOOL = "win-agent-preflight"
_COMMAND_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_COMMAND_EXTENSIONS = frozenset((*COMMAND_LAUNCHER_EXTENSIONS, ".ps1"))


class CommandDoctorInputError(ValueError):
    """Raised when a command-doctor input is not a safe basename."""


CommandDoctorState = LauncherProbeState


@dataclass(frozen=True, slots=True)
class CommandDoctorReport:
    """Independent v1 report for one requested command."""

    schema_version: int
    tool: str
    command: str
    state: LauncherProbeState
    successful: bool
    path: str | None = None
    version: str | None = None
    evidence: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    checks: tuple[CheckResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": "command_doctor",
            "tool": self.tool,
            "offline": True,
            "command": self.command,
            "state": self.state.value,
            "successful": self.successful,
            "path": self.path,
            "version": self.version,
            "evidence": list(self.evidence),
            "details": _json_copy(self.details),
            "checks": [check.to_dict() for check in self.checks],
        }


def normalize_command_name(name: str) -> str:
    """Validate a basename and return its lowercase canonical form."""

    if not isinstance(name, str) or not 1 <= len(name) <= 128:
        raise CommandDoctorInputError("command must be 1 to 128 ASCII characters")
    if not _COMMAND_NAME_PATTERN.fullmatch(name):
        raise CommandDoctorInputError("command must be an ASCII basename")
    if name.endswith("."):
        raise CommandDoctorInputError("command must not end with a dot")
    canonical = name.casefold()
    if "." in canonical:
        extension = canonical[canonical.rfind(".") :]
        if extension not in _COMMAND_EXTENSIONS:
            raise CommandDoctorInputError(
                "explicit command extensions must be .exe, .cmd, .bat, or .ps1"
            )
    return canonical


def run_command_doctor(
    name: str,
    *,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    user_path: str | None = None,
    registry_reader: RegistryValueReader | Mapping[str, object] | None = None,
    timeout: float = 5.0,
) -> CommandDoctorReport:
    """Probe one PATH command and its relevant PowerShell facts."""

    command = normalize_command_name(name)
    if timeout <= 0:
        raise CommandDoctorInputError("timeout must be positive")
    if os.name != "nt":
        raise CommandDoctorInputError("command-doctor is Windows-only")
    environment = env if env is not None else os.environ
    active_profile = user_profile or environment.get("USERPROFILE") or os.environ.get("USERPROFILE")
    active_runner = runner or Runner(default_timeout=timeout)
    extension = _explicit_extension(command)
    if extension is None:
        extensions = _command_extensions(environment)
    else:
        extensions = (extension,)
    discovery = discover_command_details(
        command,
        env=environment,
        user_profile=active_profile,
        extensions=extensions,
    )
    direct_state, direct_path, direct_version, direct_evidence, direct_details = _probe_direct(
        command,
        discovery,
        active_runner,
        env=environment,
        user_profile=active_profile,
        timeout=timeout,
    )

    checks: list[CheckResult] = [
        collect_path_refresh_check(
            process_path=environment.get("PATH"),
            process_env=environment,
            user_path=user_path,
            user_profile=active_profile,
            registry_reader=registry_reader,
        )
    ]
    has_ps1 = _has_ps1(discovery)
    if extension == ".ps1" or has_ps1:
        checks.append(
            collect_powershell_check(
                active_runner,
                env=environment,
                user_profile=active_profile,
                timeout=timeout,
            )
        )
    bare_check: CheckResult | None = None
    if extension is None:
        bare_check = collect_powershell_command_check(
            active_runner,
            command=command,
            env=environment,
            user_profile=active_profile,
            timeout=timeout,
        )
        checks.append(bare_check)

    successful = direct_state is LauncherProbeState.USABLE and (
        bare_check is None or bare_check.status is CheckStatus.PASS
    )
    return CommandDoctorReport(
        schema_version=COMMAND_DOCTOR_SCHEMA_VERSION,
        tool=COMMAND_DOCTOR_TOOL,
        command=command,
        state=direct_state,
        successful=successful,
        path=direct_path,
        version=direct_version,
        evidence=direct_evidence,
        details=direct_details,
        checks=tuple(checks),
    )


def _probe_direct(
    command: str,
    discovery,
    runner: Runner,
    *,
    env: Mapping[str, str],
    user_profile: str | None,
    timeout: float,
) -> tuple[LauncherProbeState, str | None, str | None, tuple[str, ...], dict[str, Any]]:
    paths = tuple(candidate.path for candidate in discovery.candidates)
    details: dict[str, Any] = {
        "candidate_count": len(discovery.candidates),
        "candidate_paths": list(paths),
    }
    if discovery.inaccessible_paths:
        details["lstat_errors"] = [
            {
                "path": error.path,
                "error_type": error.error_type,
                **({"winerror": error.winerror} if error.winerror is not None else {}),
            }
            for error in discovery.inaccessible_paths
        ]
    if not discovery.candidates:
        if discovery.inaccessible_paths:
            return (
                LauncherProbeState.ACCESS_DENIED,
                None,
                None,
                ("PATH candidate inspection was denied",),
                details,
            )
        if discovery.non_executable_paths:
            details["non_executable_paths"] = list(discovery.non_executable_paths)
            return (
                LauncherProbeState.RESOLVED_BUT_NOT_EXECUTABLE,
                discovery.non_executable_paths[0],
                None,
                ("resolved launcher path is not a regular file",),
                details,
            )
        return (
            LauncherProbeState.COMMAND_NOT_FOUND,
            None,
            None,
            ("command was not found in the current PATH",),
            details,
        )

    outcome = probe_launchers(
        discovery.candidates,
        runner,
        env=env,
        user_profile=user_profile,
        timeout=timeout,
    )
    details["attempts"] = list(outcome.attempts)
    if outcome.state is LauncherProbeState.USABLE:
        return (
            outcome.state,
            outcome.path,
            outcome.version,
            ("version probe succeeded",),
            details,
        )
    evidence = {
        LauncherProbeState.ACCESS_DENIED: "version probe access was denied",
        LauncherProbeState.RESOLVED_BUT_NOT_EXECUTABLE: "resolved launcher could not be started",
        LauncherProbeState.VERSION_PROBE_FAILED: "version probe did not complete successfully",
    }.get(outcome.state, "version probe failed")
    return outcome.state, outcome.path, None, (evidence,), details


def _explicit_extension(command: str) -> str | None:
    if "." not in command:
        return None
    return command[command.rfind(".") :]


def _command_extensions(environment: Mapping[str, str]) -> tuple[str, ...]:
    raw_pathext = environment.get("PATHEXT", "")
    requested = tuple(
        f".{item.strip().lstrip('.').casefold()}"
        for item in raw_pathext.split(";")
        if item.strip()
    )
    source_extensions = requested or tuple(item.casefold() for item in DEFAULT_PATHEXT)
    ordered: list[str] = []
    for extension in source_extensions:
        if extension in COMMAND_LAUNCHER_EXTENSIONS and extension not in ordered:
            ordered.append(extension)
    if ".ps1" not in ordered:
        ordered.append(".ps1")
    return tuple(ordered)


def _has_ps1(discovery) -> bool:
    paths = [candidate.path for candidate in discovery.candidates]
    paths.extend(discovery.non_executable_paths)
    paths.extend(error.path for error in discovery.inaccessible_paths)
    return any(path.casefold().endswith(".ps1") for path in paths)


def _json_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    if isinstance(value, LauncherProbeState):
        return value.value
    return value

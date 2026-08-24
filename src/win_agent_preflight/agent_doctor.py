"""Bounded local health checks for installed coding-agent launchers."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .runner import CommandExecution, Runner
from .windows import (
    CommandPathError,
    discover_agent_command_details,
    redact_text,
    run_candidate,
)

DEFAULT_AGENTS = ("codex", "claude", "dsh")


class AgentDoctorState(StrEnum):
    COMMAND_NOT_FOUND = "command_not_found"
    RESOLVED_BUT_NOT_EXECUTABLE = "resolved_but_not_executable"
    ACCESS_DENIED = "access_denied"
    VERSION_PROBE_FAILED = "version_probe_failed"
    USABLE = "usable"


class AgentDoctorInputError(ValueError):
    """Raised when the requested agent selection is invalid."""


@dataclass(frozen=True, slots=True)
class AgentDoctorResult:
    agent: str
    command: str
    state: AgentDoctorState
    summary: str
    path: str | None = None
    evidence: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "command": self.command,
            "state": self.state.value,
            "summary": self.summary,
            "path": self.path,
            "version": self.version,
            "evidence": list(self.evidence),
            "details": _json_copy(self.details),
        }


@dataclass(frozen=True, slots=True)
class AgentDoctorReport:
    """Independent v1 schema for agent launcher health."""

    schema_version: int
    tool: str
    agents: tuple[AgentDoctorResult, ...]

    @property
    def has_unusable_agent(self) -> bool:
        return any(
            result.state is not AgentDoctorState.COMMAND_NOT_FOUND
            and result.state is not AgentDoctorState.USABLE
            for result in self.agents
        )

    def to_dict(self) -> dict[str, Any]:
        counts = {state.value: 0 for state in AgentDoctorState}
        for result in self.agents:
            counts[result.state.value] += 1
        return {
            "schema_version": self.schema_version,
            "kind": "agent_doctor",
            "tool": self.tool,
            "offline": True,
            "summary": counts,
            "agents": [result.to_dict() for result in self.agents],
        }


def normalize_agents(agents: Sequence[str] | None) -> tuple[str, ...]:
    """Validate and canonicalize repeated agent options in fixed order."""

    requested = DEFAULT_AGENTS if agents is None else tuple(agents)
    selected: set[str] = set()
    for raw_name in requested:
        name = str(raw_name).strip().casefold()
        if name not in DEFAULT_AGENTS:
            allowed = ", ".join(DEFAULT_AGENTS)
            raise AgentDoctorInputError(f"unsupported agent {raw_name!r}; choose from {allowed}")
        selected.add(name)
    if not selected:
        raise AgentDoctorInputError("at least one --agent is required")
    return tuple(name for name in DEFAULT_AGENTS if name in selected)


def run_agent_doctor(
    *,
    agents: Sequence[str] | None = None,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> AgentDoctorReport:
    """Resolve and minimally probe selected local agent launchers.

    Discovery is filesystem-only.  The only command ever passed to the
    runner is the discovered launcher (or its PowerShell host) with
    ``--version``; no login, doctor, package-manager, or web command is used.
    """

    if timeout <= 0:
        raise AgentDoctorInputError("timeout must be positive")
    selected = normalize_agents(agents)
    environment = env if env is not None else os.environ
    active_profile = user_profile or environment.get("USERPROFILE") or os.environ.get("USERPROFILE")
    active_runner = runner or Runner(default_timeout=timeout)
    results = tuple(
        _check_agent(
            name,
            active_runner,
            env=environment,
            user_profile=active_profile,
            timeout=timeout,
        )
        for name in selected
    )
    return AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=results,
    )


def _check_agent(
    name: str,
    runner: Runner,
    *,
    env: Mapping[str, str],
    user_profile: str | None,
    timeout: float,
) -> AgentDoctorResult:
    discovery = discover_agent_command_details(
        name,
        env=env,
        user_profile=user_profile,
    )
    paths = tuple(candidate.path for candidate in discovery.candidates)
    base_details: dict[str, Any] = {
        "candidate_count": len(discovery.candidates),
        "candidate_paths": list(paths),
    }
    if discovery.inaccessible_paths:
        base_details["lstat_errors"] = [
            _path_error_to_dict(error) for error in discovery.inaccessible_paths
        ]

    if not discovery.candidates:
        if discovery.inaccessible_paths:
            return AgentDoctorResult(
                agent=name,
                command=name,
                state=AgentDoctorState.ACCESS_DENIED,
                summary=f"无法检查 Agent 启动器：{name}",
                evidence=("PATH candidate inspection was denied",),
                details=base_details,
            )
        if discovery.non_executable_paths:
            base_details["non_executable_paths"] = list(discovery.non_executable_paths)
            return AgentDoctorResult(
                agent=name,
                command=name,
                state=AgentDoctorState.RESOLVED_BUT_NOT_EXECUTABLE,
                summary=f"已解析 Agent 路径但不是可执行启动器：{name}",
                evidence=("resolved launcher path is not a regular file",),
                path=discovery.non_executable_paths[0],
                details=base_details,
            )
        return AgentDoctorResult(
            agent=name,
            command=name,
            state=AgentDoctorState.COMMAND_NOT_FOUND,
            summary=f"未发现 Agent 命令：{name}",
            evidence=("agent command was not found in PATH",),
            details=base_details,
        )

    attempts: list[dict[str, Any]] = []
    for candidate in discovery.candidates:
        execution = run_candidate(
            candidate,
            runner,
            env=env,
            user_profile=user_profile,
            timeout=timeout,
        )
        version = _version_line(execution, user_profile=user_profile)
        attempt = _execution_details(candidate.path, execution, has_output=version is not None)
        attempts.append(attempt)
        if execution.succeeded and version is not None:
            return AgentDoctorResult(
                agent=name,
                command=name,
                state=AgentDoctorState.USABLE,
                summary=f"Agent 可用：{name}",
                evidence=("version probe succeeded",),
                path=candidate.path,
                version=version,
                details={**base_details, "attempts": attempts},
            )

    state = _failed_probe_state(attempts)
    evidence = {
        AgentDoctorState.ACCESS_DENIED: "version probe access was denied",
        AgentDoctorState.RESOLVED_BUT_NOT_EXECUTABLE: "resolved launcher could not be started",
        AgentDoctorState.VERSION_PROBE_FAILED: "version probe did not complete successfully",
    }[state]
    return AgentDoctorResult(
        agent=name,
        command=name,
        state=state,
        summary=f"Agent 启动器不可用：{name}",
        evidence=(evidence,),
        path=discovery.candidates[0].path,
        details={**base_details, "attempts": attempts},
    )


def _failed_probe_state(attempts: Sequence[Mapping[str, Any]]) -> AgentDoctorState:
    if any(
        attempt.get("winerror") in (5, 13, 32, 1920)
        or str(attempt.get("error_type", "")).casefold()
        in {"permissionerror", "accessdeniederror"}
        for attempt in attempts
    ):
        return AgentDoctorState.ACCESS_DENIED
    if any(attempt.get("winerror") in (193, 216) for attempt in attempts):
        return AgentDoctorState.RESOLVED_BUT_NOT_EXECUTABLE
    if any(attempt.get("launcher_host_missing") for attempt in attempts):
        return AgentDoctorState.RESOLVED_BUT_NOT_EXECUTABLE
    return AgentDoctorState.VERSION_PROBE_FAILED


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
    """Return one bounded, redacted non-empty version line from the probe."""

    for stream in (execution.stdout, execution.stderr):
        for raw_line in stream.splitlines():
            line = raw_line.strip()
            if line:
                return redact_text(line, user_profile=user_profile)[:200]
    return None


def _path_error_to_dict(error: CommandPathError) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": error.path,
        "error_type": error.error_type,
    }
    if error.winerror is not None:
        result["winerror"] = error.winerror
    return result


def _json_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value

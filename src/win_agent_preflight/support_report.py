"""Collect one bounded, shareable support report from local facts."""

from __future__ import annotations

import os
import platform as platform_module
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .agent_doctor import (
    DEFAULT_AGENTS,
    AgentDoctorReport,
    AgentDoctorResult,
    AgentDoctorState,
    run_agent_doctor,
)
from .checks import agent_doctor_to_check, scan_environment
from .models import CheckResult, CheckStatus, ScanReport
from .runner import Runner
from .windows import redact_text


class SupportReportInputError(ValueError):
    """Raised when support-report input cannot be accepted."""


SupportClock = Callable[[], datetime | str]
_MAX_ERROR_MESSAGE = 240


@dataclass(frozen=True, slots=True)
class SupportReport:
    """Stable v1 envelope for a local, offline support handoff."""

    schema_version: int
    tool: str
    generated_at: str
    environment: Mapping[str, str]
    collection: Mapping[str, Any]
    scan: ScanReport
    agent_doctor: AgentDoctorReport
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "kind": "support_report",
            "generated_at": self.generated_at,
            "environment": _json_copy(self.environment),
            "collection": _json_copy(self.collection),
            "scan": self.scan.to_dict(),
            "agent_doctor": self.agent_doctor.to_dict(),
            "errors": list(self.errors),
        }


def run_support_report(
    *,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
    clock: SupportClock | None = None,
) -> SupportReport:
    """Collect Agent Doctor first, then reuse it when producing the scan."""

    if timeout <= 0:
        raise SupportReportInputError("timeout must be positive")

    environment = env if env is not None else os.environ
    active_profile = user_profile or environment.get("USERPROFILE")
    active_runner = runner or Runner(default_timeout=timeout)
    errors: list[str] = []

    try:
        agent_doctor = run_agent_doctor(
            runner=active_runner,
            env=environment,
            user_profile=active_profile,
            timeout=timeout,
        )
        precomputed = {
            name: agent_doctor_to_check(_agent_result_for(agent_doctor, name))
            for name in DEFAULT_AGENTS
        }
    except Exception as exc:
        errors.append(_safe_error("agent_doctor", exc, user_profile=active_profile))
        agent_doctor = _empty_agent_doctor()
        precomputed = {
            name: _agent_collection_error_check(name, errors[-1]) for name in DEFAULT_AGENTS
        }

    try:
        scan = scan_environment(
            runner=active_runner,
            env=environment,
            user_profile=active_profile,
            precomputed_commands=precomputed,
            timeout=timeout,
        )
    except Exception as exc:
        errors.append(_safe_error("scan", exc, user_profile=active_profile))
        scan = ScanReport(schema_version=1, tool="win-agent-preflight", checks=())

    return SupportReport(
        schema_version=1,
        tool="win-agent-preflight",
        generated_at=_generated_at(clock),
        environment=_environment_facts(),
        collection={
            "offline": True,
            "workspace_probe_run": False,
            "timeout_seconds": timeout,
            "complete": not errors,
        },
        scan=scan,
        agent_doctor=agent_doctor,
        errors=tuple(errors),
    )


def _agent_result_for(report: AgentDoctorReport, name: str) -> AgentDoctorResult:
    for result in report.agents:
        if result.agent == name:
            return result
    return AgentDoctorResult(
        agent=name,
        command=name,
        state=AgentDoctorState.VERSION_PROBE_FAILED,
        summary=f"Agent Doctor 未返回结果：{name}",
        evidence=("agent-doctor returned no result for this agent",),
    )


def _agent_collection_error_check(name: str, error: str) -> CheckResult:
    return CheckResult(
        id=f"command.{name}",
        status=CheckStatus.WARNING,
        summary=f"Agent Doctor 采集失败：{name}",
        evidence=(error,),
        details={"agent_doctor_collection_failed": True},
    )


def _empty_agent_doctor() -> AgentDoctorReport:
    return AgentDoctorReport(schema_version=1, tool="win-agent-preflight", agents=())


def _environment_facts() -> dict[str, str]:
    return {
        "platform": platform_module.system(),
        "python_version": platform_module.python_version(),
        "architecture": platform_module.machine(),
    }


def _generated_at(clock: SupportClock | None) -> str:
    value = clock() if clock is not None else datetime.now(UTC)
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _safe_error(scope: str, error: Exception, *, user_profile: str | None) -> str:
    message = str(error)
    if getattr(error, "stdout", None) or getattr(error, "stderr", None):
        message = "external command output omitted"
    message = re.sub(
        r"(?is)\b(stdout|stderr)\b(?:\s*[:=]|\s+).*$",
        r"\1: [omitted]",
        message,
    )
    message = redact_text(message, user_profile=user_profile).strip()[:_MAX_ERROR_MESSAGE]
    if not message:
        message = "no error message"
    winerror = getattr(error, "winerror", None)
    suffix = f" (winerror={winerror})" if winerror is not None else ""
    return f"{scope}: {type(error).__name__}: {message}{suffix}"


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return value

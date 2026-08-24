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
class NextCheck:
    """One deterministic, manual follow-up derived from existing reports."""

    code: str
    source: str
    target: str
    observed: str
    summary: str
    manual_commands: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "manual_commands", tuple(self.manual_commands))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "source": self.source,
            "target": self.target,
            "observed": self.observed,
            "summary": self.summary,
            "manual_commands": list(self.manual_commands),
        }


@dataclass(frozen=True, slots=True)
class SupportReport:
    """Stable v2 envelope for a local, offline support handoff."""

    schema_version: int
    tool: str
    generated_at: str
    environment: Mapping[str, str]
    collection: Mapping[str, Any]
    scan: ScanReport
    agent_doctor: AgentDoctorReport
    errors: tuple[str, ...] = ()
    next_checks: tuple[NextCheck, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("SupportReport schema_version must be 2")
        if self.scan.schema_version != 1:
            raise ValueError("SupportReport scan schema_version must be 1")
        if self.agent_doctor.schema_version != 1:
            raise ValueError("SupportReport agent_doctor schema_version must be 1")
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "next_checks", tuple(self.next_checks))

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
            "next_checks": [item.to_dict() for item in self.next_checks],
        }


def derive_next_checks(
    scan: ScanReport,
    doctor: AgentDoctorReport,
) -> tuple[NextCheck, ...]:
    """Derive bounded manual follow-ups without calling tools or reading state."""

    derived: list[NextCheck] = []
    seen: set[tuple[str, str]] = set()

    def add(item: NextCheck) -> None:
        key = (item.code, item.target)
        if key not in seen:
            seen.add(key)
            derived.append(item)

    results: dict[str, AgentDoctorResult] = {}
    for result in doctor.agents:
        results.setdefault(result.agent.casefold(), result)

    agent_rules = (
        (
            AgentDoctorState.ACCESS_DENIED,
            "agent.launcher_access_denied",
            "启动器访问被拒绝",
            ("Get-Command {agent} -All", "{agent} --version"),
        ),
        (
            AgentDoctorState.VERSION_PROBE_FAILED,
            "agent.version_probe_failed",
            "版本探针失败",
            ("{agent} --version",),
        ),
    )
    for state, code, label, command_templates in agent_rules:
        for agent in DEFAULT_AGENTS:
            result = results.get(agent)
            if result is None or result.state != state:
                continue
            add(
                NextCheck(
                    code=code,
                    source="agent_doctor",
                    target=agent,
                    observed=state.value,
                    summary=f"{agent} {label}；请在标准 Windows PowerShell 中复现。",
                    manual_commands=tuple(
                        template.format(agent=agent) for template in command_templates
                    ),
                )
            )

    npm_warning = any(
        check.id == "powershell.command.npm" and check.status == CheckStatus.WARNING
        for check in scan.checks
    )
    if npm_warning:
        add(
            NextCheck(
                code="powershell.npm_bare_command_failed",
                source="scan",
                target="npm",
                observed=CheckStatus.WARNING.value,
                summary="PowerShell 裸 npm 命令失败；请在标准 Windows PowerShell 中复现。",
                manual_commands=("Get-Command npm -All", "npm.cmd --version"),
            )
        )

    path_warning = any(
        check.id == "windows.path_refresh" and check.status == CheckStatus.WARNING
        for check in scan.checks
    )
    path_unknown = any(
        check.id == "windows.path_refresh" and check.status == CheckStatus.UNKNOWN
        for check in scan.checks
    )
    if path_warning:
        add(
            NextCheck(
                code="windows.path_refresh_pending",
                source="scan",
                target="PATH",
                observed=CheckStatus.WARNING.value,
                summary="PATH 可能尚未刷新；请重开终端，并在标准 Windows PowerShell 中复现。",
                manual_commands=("agent-preflight scan --json --pretty",),
            )
        )
    elif path_unknown:
        add(
            NextCheck(
                code="windows.path_refresh_unknown",
                source="scan",
                target="PATH",
                observed=CheckStatus.UNKNOWN.value,
                summary=(
                    "无法确认 PATH 是否已刷新；请重开终端，并在标准 Windows PowerShell 中复现。"
                ),
                manual_commands=("agent-preflight scan --json --pretty",),
            )
        )
    return tuple(derived)


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
        schema_version=2,
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
        next_checks=derive_next_checks(scan, agent_doctor),
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

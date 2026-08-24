"""Render scan models without running additional commands."""

from __future__ import annotations

import json

from .agent_doctor import AgentDoctorReport
from .command_doctor import CommandDoctorReport
from .git_doctor import GitDoctorReport
from .models import ScanReport
from .project_doctor import ProjectDoctorReport
from .support_report import SupportReport
from .workspace_probe import WorkspaceProbeReport


def render_json(report: ScanReport, *, pretty: bool = False) -> str:
    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_console(report: ScanReport) -> str:
    lines = ["Windows Agent Preflight", "=" * 24]
    for check in report.checks:
        lines.append(f"[{check.status.value.upper():7}] {check.id}: {check.summary}")
        for evidence in check.evidence:
            lines.append(f"  - {evidence}")
    summary = report.to_dict()["summary"]
    counts = ", ".join(f"{key}={summary[key]}" for key in ("pass", "warning", "fail", "unknown"))
    lines.extend(("", f"Summary: {counts}"))
    return "\n".join(lines)


def render_workspace_probe_json(
    report: WorkspaceProbeReport, *, pretty: bool = False
) -> str:
    """Render the independent workspace-probe schema without side effects."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_workspace_probe_console(report: WorkspaceProbeReport) -> str:
    """Render probe statuses and evidence without exposing fixed file content."""

    lines = ["Windows Agent Preflight workspace probe", "=" * 39]
    lines.append(f"Target: {report.target}")
    lines.append(f"Successful: {str(report.successful).lower()}")
    for check in report.checks:
        lines.append(f"[{check.status.value.upper():7}] {check.id}: {check.summary}")
        for evidence in check.evidence:
            lines.append(f"  - {evidence}")
    summary = report.to_dict()["summary"]
    counts = ", ".join(
        f"{key}={summary[key]}" for key in ("pass", "warning", "fail", "unknown")
    )
    lines.extend(("", f"Summary: {counts}"))
    if report.residual_paths:
        lines.append("Residual paths: " + ", ".join(report.residual_paths))
    return "\n".join(lines)


def render_agent_doctor_json(report: AgentDoctorReport, *, pretty: bool = False) -> str:
    """Render the independent agent-doctor v1 schema."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_agent_doctor_console(report: AgentDoctorReport) -> str:
    """Render agent states without exposing process output."""

    lines = ["Windows Agent Preflight agent doctor", "=" * 38]
    for result in report.agents:
        lines.append(f"[{result.state.value.upper():30}] {result.agent}: {result.summary}")
        if result.version is not None:
            lines.append(f"  - version: {result.version}")
        for evidence in result.evidence:
            lines.append(f"  - {evidence}")
    counts = ", ".join(
        f"{key}={value}" for key, value in report.to_dict()["summary"].items()
    )
    lines.extend(("", f"Summary: {counts}"))
    return "\n".join(lines)


def render_command_doctor_json(
    report: CommandDoctorReport, *, pretty: bool = False
) -> str:
    """Render the independent command-doctor v1 schema."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_command_doctor_console(report: CommandDoctorReport) -> str:
    """Render command state and bounded checks without process output."""

    lines = ["Windows Agent Preflight command doctor", "=" * 40]
    lines.append(f"Command: {report.command}")
    lines.append(f"State: {report.state.value}")
    lines.append(f"Successful: {str(report.successful).lower()}")
    if report.path:
        lines.append(f"Path: {report.path}")
    if report.version:
        lines.append(f"Version: {report.version}")
    for evidence in report.evidence:
        lines.append(f"  - {evidence}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"[{check.status.value.upper():7}] {check.id}: {check.summary}")
        for evidence in check.evidence:
            lines.append(f"  - {evidence}")
    return "\n".join(lines)


def render_git_doctor_json(report: GitDoctorReport, *, pretty: bool = False) -> str:
    """Render the independent git-doctor v1 schema."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_git_doctor_console(report: GitDoctorReport) -> str:
    """Render safe local Git facts without remote or identity values."""

    lines = ["Windows Agent Preflight git doctor", "=" * 36]
    lines.append(f"Target: {report.target}")
    lines.append(f"Local ready: {str(report.local_ready).lower()}")
    lines.append("Remote auth verified: false")
    for check in report.checks:
        lines.append(f"[{check.status.value.upper():7}] {check.id}: {check.summary}")
        for evidence in check.evidence:
            lines.append(f"  - {evidence}")
    summary = report.to_dict()["summary"]
    counts = ", ".join(
        f"{key}={summary[key]}" for key in ("pass", "warning", "fail", "unknown")
    )
    lines.append(f"Summary: {counts}")
    return "\n".join(lines)


def render_project_doctor_json(report: ProjectDoctorReport, *, pretty: bool = False) -> str:
    """Render the independent project-doctor v1 schema."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_project_doctor_console(report: ProjectDoctorReport) -> str:
    """Render project markers and required tool checks without file contents."""

    lines = ["Windows Agent Preflight project doctor", "=" * 40]
    lines.append(f"Target: {report.target}")
    lines.append("Markers: " + (", ".join(report.markers) if report.markers else "none"))
    lines.append(f"Marker status: {report.marker_status.value}")
    if report.unknown_reasons:
        lines.append("Unknown reasons: " + "; ".join(report.unknown_reasons))
    lines.append(
        "Required tools: "
        + (", ".join(report.required_tools) if report.required_tools else "none")
    )
    for check in report.checks:
        lines.append(f"[{check.status.value.upper():7}] {check.id}: {check.summary}")
        for evidence in check.evidence:
            lines.append(f"  - {evidence}")
    summary = report.to_dict()["summary"]
    counts = ", ".join(
        f"{key}={summary[key]}" for key in ("pass", "warning", "fail", "unknown")
    )
    lines.extend(("", f"Successful: {str(report.successful).lower()}", f"Summary: {counts}"))
    return "\n".join(lines)


def render_support_report_json(report: SupportReport, *, pretty: bool = False) -> str:
    """Render the bounded support-report v2 schema."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_support_report_console(report: SupportReport) -> str:
    """Render finite environment facts alongside the existing reports."""

    lines = ["Windows Agent Preflight support report", "=" * 40, "Environment:"]
    for key in ("platform", "python_version", "architecture"):
        lines.append(f"  {key}: {report.environment.get(key, '')}")
    lines.append(
        "Collection: "
        f"offline={str(report.collection.get('offline', False)).lower()}, "
        f"workspace_probe_run={str(report.collection.get('workspace_probe_run', False)).lower()}, "
        f"timeout_seconds={report.collection.get('timeout_seconds', '')}, "
        f"complete={str(report.collection.get('complete', False)).lower()}"
    )
    lines.extend(
        ("", render_console(report.scan), "", render_agent_doctor_console(report.agent_doctor))
    )
    if report.next_checks:
        lines.extend(("", "Next checks:"))
        for item in report.next_checks:
            lines.append(
                f"  - {item.code} [{item.source}/{item.target}; observed={item.observed}]: "
                f"{item.summary}"
            )
            lines.extend(f"    $ {command}" for command in item.manual_commands)
    else:
        lines.extend(("", "Next checks: none."))
    if report.errors:
        lines.extend(("", "Errors:"))
        lines.extend(f"  - {error}" for error in report.errors)
    lines.extend(
        (
            "",
            "分享前请确认：报告未包含主机名、cwd、sys.executable、完整 PATH 或环境变量值。",
        )
    )
    return "\n".join(lines)

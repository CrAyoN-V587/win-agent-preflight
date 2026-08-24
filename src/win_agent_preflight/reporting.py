"""Render scan models without running additional commands."""

from __future__ import annotations

import json

from .models import ScanReport
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

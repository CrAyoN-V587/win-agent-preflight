"""Render scan models without running additional commands."""

from __future__ import annotations

import json

from .models import ScanReport


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

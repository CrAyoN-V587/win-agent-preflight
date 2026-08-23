from __future__ import annotations

from win_agent_preflight.models import CheckResult, CheckStatus, ScanReport
from win_agent_preflight.reporting import render_console, render_json


def test_renderers_do_not_change_model_semantics() -> None:
    report = ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=(
            CheckResult(
                id="windows.path_refresh",
                status=CheckStatus.WARNING,
                summary="path stale",
                evidence=("missing: %USERPROFILE%\\bin",),
            ),
        ),
    )
    assert '"status":"warning"' in render_json(report)
    assert "WARNING" in render_console(report)

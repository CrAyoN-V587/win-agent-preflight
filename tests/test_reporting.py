from __future__ import annotations

from win_agent_preflight.agent_doctor import (
    AgentDoctorReport,
    AgentDoctorResult,
    AgentDoctorState,
)
from win_agent_preflight.models import CheckResult, CheckStatus, ScanReport
from win_agent_preflight.reporting import (
    render_agent_doctor_console,
    render_console,
    render_json,
)


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


def test_agent_doctor_console_shows_version_but_not_process_output() -> None:
    report = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.USABLE,
                summary="usable",
                version=r"%USERPROFILE%/bin/codex 1.2.3",
            ),
            AgentDoctorResult(
                agent="claude",
                command="claude",
                state=AgentDoctorState.VERSION_PROBE_FAILED,
                summary="failed",
                evidence=("version probe did not complete successfully",),
                details={"attempts": [{"stdout": "SECRET", "stderr": "SECRET"}]},
            ),
        ),
    )

    rendered = render_agent_doctor_console(report)

    assert "version: %USERPROFILE%/bin/codex 1.2.3" in rendered
    assert "SECRET" not in rendered

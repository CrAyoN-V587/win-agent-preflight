from __future__ import annotations

import pytest

from win_agent_preflight.models import CheckResult, CheckStatus, ScanReport


def test_report_serialization_is_stable_and_json_friendly() -> None:
    report = ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=(
            CheckResult(
                id="command.git",
                status=CheckStatus.PASS,
                summary="ok",
                evidence=("selected: %USERPROFILE%\\bin\\git.exe",),
                details={"candidate_count": 1},
            ),
        ),
    )
    assert report.to_dict() == {
        "schema_version": 1,
        "tool": "win-agent-preflight",
        "summary": {"pass": 1, "warning": 0, "fail": 0, "unknown": 0},
        "checks": [
            {
                "id": "command.git",
                "status": "pass",
                "summary": "ok",
                "evidence": ["selected: %USERPROFILE%\\bin\\git.exe"],
                "details": {"candidate_count": 1},
            }
        ],
    }


def test_fail_requires_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        CheckResult(id="bad", status=CheckStatus.FAIL, summary="guess")

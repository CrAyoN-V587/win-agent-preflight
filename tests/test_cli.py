from __future__ import annotations

import json

from typer.testing import CliRunner

from win_agent_preflight import cli
from win_agent_preflight.models import CheckResult, CheckStatus, ScanReport


def _report(*statuses: CheckStatus) -> ScanReport:
    return ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=tuple(
            CheckResult(
                id=f"test.{index}",
                status=status,
                summary=status.value,
                evidence=("fixture evidence",) if status is CheckStatus.FAIL else (),
            )
            for index, status in enumerate(statuses)
        ),
    )


def test_scan_json_is_parseable_and_warnings_do_not_fail(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "scan_environment",
        lambda **kwargs: _report(CheckStatus.WARNING, CheckStatus.UNKNOWN),
    )
    result = CliRunner().invoke(cli.app, ["scan", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["warning"] == 1
    assert payload["summary"]["unknown"] == 1
    assert payload["summary"]["fail"] == 0


def test_scan_returns_one_for_fail(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "scan_environment",
        lambda **kwargs: _report(CheckStatus.FAIL),
    )
    result = CliRunner().invoke(cli.app, ["scan", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["summary"]["fail"] == 1

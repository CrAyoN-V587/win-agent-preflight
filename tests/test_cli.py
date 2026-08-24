from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from win_agent_preflight import cli
from win_agent_preflight.agent_doctor import (
    AgentDoctorReport,
    AgentDoctorResult,
    AgentDoctorState,
)
from win_agent_preflight.models import CheckResult, CheckStatus, ScanReport
from win_agent_preflight.snapshot import capture_snapshot, write_snapshot


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


def test_snapshot_writes_even_when_embedded_scan_has_fail(monkeypatch, tmp_path: Path) -> None:
    fixture = capture_snapshot("host", env={})
    monkeypatch.setattr(cli, "capture_snapshot", lambda label, timeout: fixture)
    output = tmp_path / "nested" / "host.json"
    result = CliRunner().invoke(
        cli.app,
        ["snapshot", "--label", "host", "--output", str(output), "--pretty"],
    )
    assert result.exit_code == 0
    assert output.exists()
    profile = os.environ.get("USERPROFILE")
    assert profile is None or profile.casefold() not in result.output.casefold()
    assert fixture.scan["summary"]["fail"] > 0

    refused = CliRunner().invoke(
        cli.app,
        ["snapshot", "--label", "host", "--output", str(output)],
    )
    assert refused.exit_code == 2
    assert profile is None or profile.casefold() not in refused.output.casefold()


def test_compare_cli_json_exit_codes(tmp_path: Path) -> None:
    baseline = capture_snapshot("host", env={})
    current = capture_snapshot("agent", env={})
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    write_snapshot(baseline, baseline_path)
    write_snapshot(current, current_path)

    equivalent = CliRunner().invoke(
        cli.app,
        ["compare", str(baseline_path), str(current_path), "--json"],
    )
    assert equivalent.exit_code == 0
    assert json.loads(equivalent.stdout)["equivalent"] is True

    changed = current.to_dict()
    changed["environment"]["path"] = [r"C:\Different"]
    current_path.write_text(json.dumps(changed), encoding="utf-8")
    different = CliRunner().invoke(
        cli.app,
        ["compare", str(baseline_path), str(current_path), "--json", "--pretty"],
    )
    assert different.exit_code == 1
    assert json.loads(different.stdout)["equivalent"] is False


def test_compare_invalid_input_is_tool_error(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schema_version": 2}', encoding="utf-8")
    result = CliRunner().invoke(cli.app, ["compare", str(invalid), str(invalid)])
    assert result.exit_code == 2


def test_compare_missing_file_is_redacted_tool_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    result = CliRunner().invoke(cli.app, ["compare", str(missing), str(missing)])
    assert result.exit_code == 2
    profile = os.environ.get("USERPROFILE")
    assert profile is None or profile.casefold() not in result.output.casefold()


def test_agent_doctor_cli_json_preserves_fixed_selection_order(monkeypatch) -> None:
    report = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.COMMAND_NOT_FOUND,
                summary="missing",
            ),
            AgentDoctorResult(
                agent="dsh",
                command="dsh",
                state=AgentDoctorState.COMMAND_NOT_FOUND,
                summary="missing",
            ),
        ),
    )
    received: list[object] = []

    def fake_doctor(*, agents, timeout):
        received.append(agents)
        assert timeout == 5.0
        return report

    monkeypatch.setattr(cli, "run_agent_doctor", fake_doctor)
    result = CliRunner().invoke(
        cli.app,
        ["agent-doctor", "--agent", "dsh", "--agent", "codex", "--json"],
    )

    assert result.exit_code == 0
    assert received == [["dsh", "codex"]]
    payload = json.loads(result.stdout)
    assert payload["kind"] == "agent_doctor"
    assert payload["offline"] is True
    assert [item["agent"] for item in payload["agents"]] == ["codex", "dsh"]


def test_agent_doctor_cli_capability_failure_is_exit_one_json(monkeypatch) -> None:
    report = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.ACCESS_DENIED,
                summary="denied",
                evidence=("structured failure",),
                details={"attempts": [{"error_type": "PermissionError", "winerror": 5}]},
            ),
        ),
    )
    monkeypatch.setattr(cli, "run_agent_doctor", lambda **kwargs: report)

    result = CliRunner().invoke(cli.app, ["agent-doctor", "--agent", "codex", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["agents"][0]["state"] == "access_denied"


def test_agent_doctor_cli_rejects_unknown_agent() -> None:
    result = CliRunner().invoke(cli.app, ["agent-doctor", "--agent", "unknown"])

    assert result.exit_code == 2
    assert "unsupported agent" in result.stderr

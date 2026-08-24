from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from typer.testing import CliRunner

from win_agent_preflight import cli
from win_agent_preflight.agent_doctor import (
    AgentDoctorReport,
    AgentDoctorResult,
    AgentDoctorState,
)
from win_agent_preflight.models import CheckResult, CheckStatus, ScanReport
from win_agent_preflight.reporting import render_support_report_console
from win_agent_preflight.runner import CommandExecution, Runner
from win_agent_preflight.support_report import (
    NextCheck,
    SupportReport,
    SupportReportInputError,
    derive_next_checks,
    run_support_report,
)


def _touch(path: Path) -> None:
    path.write_text("launcher", encoding="utf-8")


def _report(
    *, errors: tuple[str, ...] = (), next_checks: tuple[NextCheck, ...] = ()
) -> SupportReport:
    return SupportReport(
        schema_version=2,
        tool="win-agent-preflight",
        generated_at="2026-08-24T04:30:00+00:00",
        environment={"platform": "Windows", "python_version": "3.12.7", "architecture": "AMD64"},
        collection={
            "offline": True,
            "workspace_probe_run": False,
            "timeout_seconds": 5.0,
            "complete": not errors,
        },
        scan=ScanReport(schema_version=1, tool="win-agent-preflight", checks=()),
        agent_doctor=AgentDoctorReport(
            schema_version=1,
            tool="win-agent-preflight",
            agents=(),
        ),
        errors=errors,
        next_checks=next_checks,
    )


def _usable_agent_report() -> AgentDoctorReport:
    return AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.USABLE,
                summary="usable",
                path=r"%USERPROFILE%\bin\codex.exe",
                version="codex 1.0",
                evidence=("version probe succeeded",),
            ),
        ),
    )


def test_support_report_reuses_agent_results_in_scan(tmp_path: Path) -> None:
    for name in ("codex", "claude", "dsh"):
        _touch(tmp_path / f"{name}.exe")
    calls: list[tuple[str, ...]] = []

    def executor(argv: Sequence[str], timeout, env, cwd) -> CommandExecution:
        del timeout, env, cwd
        args = tuple(argv)
        calls.append(args)
        return CommandExecution(argv=args, returncode=0, stdout="agent 1.0\n")

    environment = {"PATH": str(tmp_path), "PATHEXT": ".EXE;.CMD;.BAT;.PS1"}
    report = run_support_report(
        env=environment,
        user_profile=str(tmp_path / "alice"),
        runner=Runner(executor=executor),
        timeout=2.5,
        clock=lambda: "2026-08-24T04:30:00+00:00",
    )

    payload = report.to_dict()
    assert payload["schema_version"] == 2
    assert payload["kind"] == "support_report"
    assert payload["generated_at"] == "2026-08-24T04:30:00+00:00"
    assert set(payload["environment"]) == {"platform", "python_version", "architecture"}
    assert payload["collection"] == {
        "offline": True,
        "workspace_probe_run": False,
        "timeout_seconds": 2.5,
        "complete": True,
    }
    assert payload["errors"] == []
    assert all(item[1:] == ("--version",) for item in calls)
    assert [Path(item[0]).stem for item in calls] == ["codex", "claude", "dsh"]
    assert len(calls) == 3
    agent_checks = {
        check["id"]: check
        for check in payload["scan"]["checks"]
        if check["id"].startswith("command.")
    }
    assert agent_checks["command.codex"]["status"] == "pass"
    assert agent_checks["command.claude"]["status"] == "pass"
    assert agent_checks["command.dsh"]["status"] == "pass"


def test_support_report_allows_agent_multi_candidate_fallback(tmp_path: Path) -> None:
    _touch(tmp_path / "codex.exe")
    _touch(tmp_path / "codex.cmd")
    calls: list[tuple[str, ...]] = []

    def executor(argv: Sequence[str], timeout, env, cwd) -> CommandExecution:
        del timeout, env, cwd
        args = tuple(argv)
        calls.append(args)
        if str(args[0]).casefold().endswith("codex.exe"):
            return CommandExecution(argv=args, returncode=1, stderr="first candidate failed")
        return CommandExecution(argv=args, returncode=0, stdout="codex fallback 1.0\n")

    report = run_support_report(
        env={"PATH": str(tmp_path), "PATHEXT": ".EXE;.CMD"},
        runner=Runner(executor=executor),
        clock=lambda: "fixed",
    )

    assert [Path(item[0]).name for item in calls] == ["codex.exe", "codex.cmd"]
    assert all(item[1:] == ("--version",) for item in calls)
    assert report.agent_doctor.agents[0].agent == "codex"
    assert report.agent_doctor.agents[0].state is AgentDoctorState.USABLE
    assert Path(report.agent_doctor.agents[0].path or "").name == "codex.cmd"
    codex_check = next(check for check in report.scan.checks if check.id == "command.codex")
    assert codex_check.status.value == "pass"
    assert codex_check.details["agent_doctor_state"] == "usable"


def test_derive_next_checks_has_fixed_priority_and_agent_order() -> None:
    doctor = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="dsh",
                command="dsh",
                state=AgentDoctorState.VERSION_PROBE_FAILED,
                summary="ignored summary",
            ),
            AgentDoctorResult(
                agent="claude",
                command="claude",
                state=AgentDoctorState.VERSION_PROBE_FAILED,
                summary="another summary",
            ),
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.ACCESS_DENIED,
                summary="not parsed",
            ),
        ),
    )
    scan = ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=(
            CheckResult(
                id="windows.path_refresh",
                status=CheckStatus.WARNING,
                summary="arbitrary summary",
                evidence=("arbitrary evidence",),
            ),
            CheckResult(
                id="powershell.command.npm",
                status=CheckStatus.WARNING,
                summary="arbitrary npm summary",
            ),
        ),
    )

    result = derive_next_checks(scan, doctor)

    assert [(item.code, item.target, item.observed) for item in result] == [
        ("agent.launcher_access_denied", "codex", "access_denied"),
        ("agent.version_probe_failed", "claude", "version_probe_failed"),
        ("agent.version_probe_failed", "dsh", "version_probe_failed"),
        ("powershell.npm_bare_command_failed", "npm", "warning"),
        ("windows.path_refresh_pending", "PATH", "warning"),
    ]
    assert result[0].manual_commands == (
        "Get-Command codex -All",
        "codex --version",
    )
    assert "重开终端" in result[-1].summary
    assert "标准 Windows PowerShell" in result[-1].summary


def test_derive_next_checks_uses_state_specific_agent_commands() -> None:
    doctor = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.ACCESS_DENIED,
                summary="denied",
            ),
            AgentDoctorResult(
                agent="claude",
                command="claude",
                state=AgentDoctorState.VERSION_PROBE_FAILED,
                summary="failed",
            ),
            AgentDoctorResult(
                agent="dsh",
                command="dsh",
                state=AgentDoctorState.VERSION_PROBE_FAILED,
                summary="failed",
            ),
        ),
    )

    result = derive_next_checks(
        ScanReport(schema_version=1, tool="win-agent-preflight", checks=()),
        doctor,
    )
    by_target = {item.target: item for item in result}

    assert by_target["codex"].manual_commands == (
        "Get-Command codex -All",
        "codex --version",
    )
    assert by_target["claude"].manual_commands == ("claude --version",)
    assert by_target["dsh"].manual_commands == ("dsh --version",)


def test_derive_next_checks_ignores_non_actionable_and_injected_agent_checks() -> None:
    doctor = AgentDoctorReport(
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
                agent="claude",
                command="claude",
                state=AgentDoctorState.RESOLVED_BUT_NOT_EXECUTABLE,
                summary="not executable",
            ),
            AgentDoctorResult(
                agent="dsh",
                command="dsh",
                state=AgentDoctorState.USABLE,
                summary="usable",
            ),
        ),
    )
    scan = ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=tuple(
            CheckResult(
                id=check_id,
                status=CheckStatus.WARNING,
                summary="agent check should not produce advice",
            )
            for check_id in ("command.codex", "command.claude", "command.dsh")
        )
        + (
            CheckResult(
                id="powershell.command.npm",
                status=CheckStatus.PASS,
                summary="ok",
            ),
            CheckResult(
                id="windows.path_refresh",
                status=CheckStatus.PASS,
                summary="ok",
            ),
        ),
    )

    assert derive_next_checks(scan, doctor) == ()


def test_derive_next_checks_reports_path_unknown_with_one_manual_command() -> None:
    scan = ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=(
            CheckResult(
                id="windows.path_refresh",
                status=CheckStatus.UNKNOWN,
                summary="text is not parsed",
                evidence=("not parsed",),
            ),
        ),
    )

    result = derive_next_checks(
        scan,
        AgentDoctorReport(schema_version=1, tool="win-agent-preflight", agents=()),
    )

    assert [(item.code, item.target, item.observed) for item in result] == [
        ("windows.path_refresh_unknown", "PATH", "unknown")
    ]
    assert result[0].manual_commands == ("agent-preflight scan --json --pretty",)


def test_derive_next_checks_deduplicates_same_code_and_target() -> None:
    doctor = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.ACCESS_DENIED,
                summary="first",
            ),
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.ACCESS_DENIED,
                summary="second",
            ),
        ),
    )
    warning = CheckResult(
        id="powershell.command.npm", status=CheckStatus.WARNING, summary="first"
    )
    warning_again = CheckResult(
        id="powershell.command.npm", status=CheckStatus.WARNING, summary="second"
    )
    path_warning = CheckResult(
        id="windows.path_refresh", status=CheckStatus.WARNING, summary="first"
    )
    path_warning_again = CheckResult(
        id="windows.path_refresh", status=CheckStatus.WARNING, summary="second"
    )
    scan = ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=(warning, warning_again, path_warning, path_warning_again),
    )

    result = derive_next_checks(scan, doctor)

    assert [(item.code, item.target) for item in result] == [
        ("agent.launcher_access_denied", "codex"),
        ("powershell.npm_bare_command_failed", "npm"),
        ("windows.path_refresh_pending", "PATH"),
    ]


def test_derive_next_checks_is_pure(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "win_agent_preflight.support_report.run_agent_doctor",
        lambda **kwargs: calls.append("agent") or None,
    )
    monkeypatch.setattr(
        "win_agent_preflight.support_report.scan_environment",
        lambda **kwargs: calls.append("scan") or None,
    )

    derive_next_checks(
        ScanReport(schema_version=1, tool="win-agent-preflight", checks=()),
        AgentDoctorReport(schema_version=1, tool="win-agent-preflight", agents=()),
    )

    assert calls == []


def test_support_report_v2_preserves_v1_children_and_next_checks(monkeypatch) -> None:
    doctor = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.ACCESS_DENIED,
                summary="denied",
            ),
        ),
    )
    scan = ScanReport(
        schema_version=1,
        tool="win-agent-preflight",
        checks=(
            CheckResult(
                id="powershell.command.npm",
                status=CheckStatus.WARNING,
                summary="npm failed",
            ),
        ),
    )
    monkeypatch.setattr(
        "win_agent_preflight.support_report.run_agent_doctor",
        lambda **kwargs: doctor,
    )
    monkeypatch.setattr(
        "win_agent_preflight.support_report.scan_environment",
        lambda **kwargs: scan,
    )

    payload = run_support_report(clock=lambda: "fixed").to_dict()

    assert payload["schema_version"] == 2
    assert payload["scan"]["schema_version"] == 1
    assert payload["agent_doctor"]["schema_version"] == 1
    assert [item["code"] for item in payload["next_checks"]] == [
        "agent.launcher_access_denied",
        "powershell.npm_bare_command_failed",
    ]
    assert set(payload) == {
        "schema_version",
        "tool",
        "kind",
        "generated_at",
        "environment",
        "collection",
        "scan",
        "agent_doctor",
        "errors",
        "next_checks",
    }


def test_next_check_and_support_report_are_immutable_and_v2_only() -> None:
    item = NextCheck(
        code="test.code",
        source="test",
        target="target",
        observed="warning",
        summary="summary",
        manual_commands=["command"],  # type: ignore[arg-type]
    )
    assert item.manual_commands == ("command",)
    with pytest.raises(FrozenInstanceError):
        item.code = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="schema_version must be 2"):
        SupportReport(
            schema_version=1,
            tool="win-agent-preflight",
            generated_at="fixed",
            environment={},
            collection={},
            scan=ScanReport(schema_version=1, tool="win-agent-preflight", checks=()),
            agent_doctor=AgentDoctorReport(
                schema_version=1,
                tool="win-agent-preflight",
                agents=(),
            ),
        )


def test_support_report_console_lists_next_checks() -> None:
    rendered = render_support_report_console(
        _report(
            next_checks=(
                NextCheck(
                    code="agent.version_probe_failed",
                    source="agent_doctor",
                    target="codex",
                    observed="version_probe_failed",
                    summary="codex version probe failed",
                    manual_commands=("codex --version",),
                ),
            )
        )
    )

    assert "Next checks:" in rendered
    assert "agent.version_probe_failed" in rendered
    assert "$ codex --version" in rendered


def test_support_report_preserves_scan_when_agent_collection_fails(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fail_doctor(**kwargs):
        received["runner"] = kwargs["runner"]
        raise RuntimeError(r"C:\Users\alice\secret stdout=DO-NOT-PRINT")

    scan = ScanReport(schema_version=1, tool="win-agent-preflight", checks=())

    def fake_scan(**kwargs):
        received["scan_runner"] = kwargs["runner"]
        return scan

    monkeypatch.setattr("win_agent_preflight.support_report.run_agent_doctor", fail_doctor)
    monkeypatch.setattr("win_agent_preflight.support_report.scan_environment", fake_scan)

    report = run_support_report(
        env={"PATH": "C:\\Users\\alice\\bin"},
        user_profile=r"C:\Users\alice",
        clock=lambda: "fixed",
    )

    payload = report.to_dict()
    assert payload["scan"] == scan.to_dict()
    assert payload["agent_doctor"]["agents"] == []
    assert payload["collection"]["complete"] is False
    assert payload["errors"]
    error_text = json.dumps(payload, ensure_ascii=False)
    assert "alice" not in error_text
    assert "DO-NOT-PRINT" not in error_text
    assert received["runner"] is received["scan_runner"]


def test_support_report_maps_agent_states_into_scan_checks(monkeypatch) -> None:
    doctor = AgentDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        agents=(
            AgentDoctorResult(
                agent="codex",
                command="codex",
                state=AgentDoctorState.COMMAND_NOT_FOUND,
                summary="missing",
                evidence=("missing",),
            ),
            AgentDoctorResult(
                agent="claude",
                command="claude",
                state=AgentDoctorState.ACCESS_DENIED,
                summary="denied",
                evidence=("denied",),
            ),
            AgentDoctorResult(
                agent="dsh",
                command="dsh",
                state=AgentDoctorState.USABLE,
                summary="usable",
                version="dsh 1.0",
                evidence=("version probe succeeded",),
            ),
        ),
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "win_agent_preflight.support_report.run_agent_doctor",
        lambda **kwargs: doctor,
    )

    def fake_scan(**kwargs):
        captured["precomputed"] = kwargs["precomputed_commands"]
        return ScanReport(schema_version=1, tool="win-agent-preflight", checks=())

    monkeypatch.setattr("win_agent_preflight.support_report.scan_environment", fake_scan)

    run_support_report(clock=lambda: "fixed")

    checks = captured["precomputed"]
    assert checks["codex"].status.value == "warning"
    assert checks["claude"].status.value == "warning"
    assert checks["dsh"].status.value == "pass"
    assert checks["dsh"].evidence[-1] == "version: dsh 1.0"


def test_support_report_preserves_agent_doctor_when_scan_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "win_agent_preflight.support_report.run_agent_doctor",
        lambda **kwargs: _usable_agent_report(),
    )
    monkeypatch.setattr(
        "win_agent_preflight.support_report.scan_environment",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("scan failed")),
    )

    report = run_support_report(clock=lambda: "fixed")

    assert report.agent_doctor.agents[0].agent == "codex"
    assert report.scan.checks == ()
    assert report.collection["complete"] is False
    assert report.errors == ("scan: RuntimeError: scan failed",)


def test_support_report_console_lists_finite_facts_and_share_reminder() -> None:
    rendered = render_support_report_console(_report())

    assert "platform: Windows" in rendered
    assert "workspace_probe_run=false" in rendered
    assert "Next checks: none." in rendered
    assert "主机名" in rendered
    assert "cwd" in rendered
    assert "sys.executable" in rendered
    assert "PATH" in rendered


def test_support_report_cli_json_exit_codes(monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_support_report", lambda **kwargs: _report())
    healthy = CliRunner().invoke(cli.app, ["support-report", "--json", "--pretty"])

    assert healthy.exit_code == 0
    payload = json.loads(healthy.stdout)
    assert payload["kind"] == "support_report"
    assert payload["schema_version"] == 2
    assert payload["collection"]["offline"] is True

    monkeypatch.setattr(cli, "run_support_report", lambda **kwargs: _report(errors=("failed",)))
    partial = CliRunner().invoke(cli.app, ["support-report", "--json"])
    assert partial.exit_code == 1
    assert json.loads(partial.stdout)["errors"] == ["failed"]

    monkeypatch.setattr(
        cli,
        "run_support_report",
        lambda **kwargs: (_ for _ in ()).throw(SupportReportInputError("invalid")),
    )
    invalid = CliRunner().invoke(cli.app, ["support-report", "--json"])
    assert invalid.exit_code == 2


def test_support_report_cli_rejects_non_positive_timeout() -> None:
    result = CliRunner().invoke(cli.app, ["support-report", "--timeout", "0"])

    assert result.exit_code == 2

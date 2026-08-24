from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

import win_agent_preflight.command_doctor as command_doctor_module
from win_agent_preflight.command_doctor import (
    CommandDoctorInputError,
    normalize_command_name,
    run_command_doctor,
)
from win_agent_preflight.launcher_probe import LauncherProbeState
from win_agent_preflight.models import CheckResult, CheckStatus
from win_agent_preflight.runner import CommandExecution, Runner
from win_agent_preflight.windows import discover_command_details


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("launcher", encoding="utf-8")


def _env(directory: Path, *, pathext: str = ".EXE;.CMD;.BAT;.PS1") -> dict[str, str]:
    return {"PATH": str(directory), "PATHEXT": pathext}


def _check(check_id: str, status: CheckStatus) -> CheckResult:
    return CheckResult(
        id=check_id,
        status=status,
        summary=status.value,
        evidence=("fixture evidence",) if status is CheckStatus.FAIL else (),
    )


def _patch_facts(monkeypatch, *, bare: CheckStatus = CheckStatus.PASS) -> None:
    monkeypatch.setattr(
        command_doctor_module,
        "collect_path_refresh_check",
        lambda **kwargs: _check("windows.path_refresh", CheckStatus.PASS),
    )
    monkeypatch.setattr(
        command_doctor_module,
        "collect_powershell_check",
        lambda *args, **kwargs: _check(
            "windows.powershell.execution_policy", CheckStatus.PASS
        ),
    )
    monkeypatch.setattr(
        command_doctor_module,
        "collect_powershell_command_check",
        lambda *args, **kwargs: _check(
            f"powershell.command.{kwargs.get('command', 'tool')}", bare
        ),
    )


def _runner(calls: list[tuple[str, ...]], executor) -> Runner:
    def wrapped(argv: Sequence[str], timeout, env, cwd) -> CommandExecution:
        del timeout, env, cwd
        args = tuple(argv)
        calls.append(args)
        return executor(args)

    return Runner(executor=wrapped)


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "npm.",
        "npm.com",
        "npm.cmd --version",
        "npm/cmd",
        "npm\\cmd",
        "npm:cmd",
        "npm cmd",
        "_npm",
        "é",
        "a" * 129,
    ],
)
def test_invalid_names_are_rejected_before_runner_calls(value: str, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    runner = _runner(calls, lambda args: CommandExecution(argv=args, returncode=0))

    with pytest.raises(CommandDoctorInputError):
        run_command_doctor(value, env=_env(tmp_path), runner=runner)

    assert calls == []


def test_non_windows_is_rejected_before_runner_or_fact_collection(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(command_doctor_module.os, "name", "posix")
    calls: list[tuple[str, ...]] = []
    runner = _runner(calls, lambda args: CommandExecution(argv=args, returncode=0))

    def facts_must_not_run(**kwargs):
        raise AssertionError("facts must not be collected on non-Windows")

    monkeypatch.setattr(command_doctor_module, "collect_path_refresh_check", facts_must_not_run)
    with pytest.raises(CommandDoctorInputError, match="Windows-only"):
        run_command_doctor("tool", env=_env(tmp_path), runner=runner)
    assert calls == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [("NPM", "npm"), ("Tool.CMD", "tool.cmd"), ("tool.Ps1", "tool.ps1")],
)
def test_valid_name_is_canonicalized(value: str, expected: str) -> None:
    assert normalize_command_name(value) == expected


def test_generic_discovery_preserves_pathext_order_and_structures_non_regular(
    tmp_path: Path,
) -> None:
    _touch(tmp_path / "tool.cmd")
    (tmp_path / "tool.exe").mkdir()

    discovery = discover_command_details(
        "tool",
        env=_env(tmp_path, pathext=".CMD;.EXE;.BAT"),
        extensions=(".cmd", ".exe", ".bat"),
    )

    assert [Path(item.path).name for item in discovery.candidates] == ["tool.cmd"]
    assert [Path(path).name for path in discovery.non_executable_paths] == ["tool.exe"]


def test_generic_discovery_retains_access_error_without_runner(
    monkeypatch, tmp_path: Path
) -> None:
    original_lstat = command_doctor_module.os.lstat

    def denied(path):
        if str(path).casefold().endswith("tool.exe"):
            error = PermissionError("denied")
            error.winerror = 5  # type: ignore[attr-defined]
            raise error
        return original_lstat(path)

    monkeypatch.setattr(command_doctor_module.os, "lstat", denied)
    discovery = discover_command_details(
        "tool", env=_env(tmp_path, pathext=".EXE"), extensions=(".exe",)
    )

    assert discovery.candidates == ()
    assert discovery.inaccessible_paths[0].error_type == "PermissionError"
    assert discovery.inaccessible_paths[0].winerror == 5


def test_candidate_order_follows_pathext_and_stops_after_first_usable(
    monkeypatch, tmp_path: Path
) -> None:
    for extension in (".bat", ".exe", ".cmd", ".ps1"):
        _touch(tmp_path / f"tool{extension}")
    _patch_facts(monkeypatch)
    calls: list[tuple[str, ...]] = []

    report = run_command_doctor(
        "tool",
        env=_env(tmp_path, pathext=".CMD;.BAT;.EXE"),
        runner=_runner(
            calls,
            lambda args: CommandExecution(argv=args, returncode=0, stdout="tool 1\n"),
        ),
    )

    assert report.state is LauncherProbeState.USABLE
    assert report.successful is True
    assert Path(calls[0][0]).name == "tool.cmd"
    assert calls[0][1:] == ("--version",)
    assert len(calls) == 1
    assert [check.id for check in report.checks] == [
        "windows.path_refresh",
        "windows.powershell.execution_policy",
        "powershell.command.tool",
    ]


def test_bare_candidates_do_not_add_extensions_absent_from_pathext(
    monkeypatch, tmp_path: Path
) -> None:
    _touch(tmp_path / "tool.bat")
    _touch(tmp_path / "tool.exe")
    _touch(tmp_path / "tool.ps1")
    _patch_facts(monkeypatch)
    calls: list[tuple[str, ...]] = []

    report = run_command_doctor(
        "tool",
        env=_env(tmp_path, pathext=".EXE"),
        runner=_runner(
            calls,
            lambda args: CommandExecution(argv=args, returncode=0, stdout="tool 1\n"),
        ),
    )

    assert report.state is LauncherProbeState.USABLE
    assert Path(calls[0][0]).name == "tool.exe"
    assert [Path(path).name for path in report.details["candidate_paths"]] == [
        "tool.exe",
        "tool.ps1",
    ]


def test_candidate_failure_falls_back_and_records_attempts_without_output(
    monkeypatch, tmp_path: Path
) -> None:
    _touch(tmp_path / "tool.exe")
    _touch(tmp_path / "tool.cmd")
    _patch_facts(monkeypatch)
    calls: list[tuple[str, ...]] = []

    def execute(args: tuple[str, ...]) -> CommandExecution:
        if args[0].casefold().endswith("tool.exe"):
            return CommandExecution(
                argv=args,
                returncode=1,
                stdout="SECRET-STDOUT",
                stderr="SECRET-STDERR",
            )
        return CommandExecution(argv=args, returncode=0, stderr="tool 2\n")

    report = run_command_doctor(
        "tool",
        env=_env(tmp_path, pathext=".EXE;.CMD"),
        runner=_runner(calls, execute),
    )

    assert report.state is LauncherProbeState.USABLE
    assert report.version == "tool 2"
    assert len(report.details["attempts"]) == 2
    assert "SECRET" not in str(report.to_dict())
    assert [Path(call[0]).name for call in calls] == ["tool.exe", "tool.cmd"]


def test_empty_output_and_timeout_are_version_probe_failures(
    monkeypatch, tmp_path: Path
) -> None:
    _touch(tmp_path / "tool.exe")
    _patch_facts(monkeypatch)

    empty = run_command_doctor(
        "tool.exe",
        env=_env(tmp_path),
        runner=Runner(
            executor=lambda argv, timeout, env, cwd: CommandExecution(
                argv=tuple(argv), returncode=0
            )
        ),
    )
    assert empty.state is LauncherProbeState.VERSION_PROBE_FAILED
    assert empty.successful is False

    timed_out = run_command_doctor(
        "tool.exe",
        env=_env(tmp_path),
        runner=Runner(
            executor=lambda argv, timeout, env, cwd: CommandExecution(
                argv=tuple(argv), returncode=None, timed_out=True, error_type="TimeoutExpired"
            )
        ),
    )
    assert timed_out.state is LauncherProbeState.VERSION_PROBE_FAILED


@pytest.mark.parametrize(
    ("winerror", "expected"),
    [(5, LauncherProbeState.ACCESS_DENIED), (193, LauncherProbeState.RESOLVED_BUT_NOT_EXECUTABLE)],
)
def test_runner_winerror_maps_to_shared_launcher_state(
    tmp_path: Path, winerror: int, expected: LauncherProbeState
) -> None:
    _touch(tmp_path / "tool.exe")
    report = run_command_doctor(
        "tool.exe",
        env=_env(tmp_path),
        runner=Runner(
            executor=lambda argv, timeout, env, cwd: CommandExecution(
                argv=tuple(argv), returncode=None, error_type="OSError", winerror=winerror
            )
        ),
    )

    assert report.state is expected
    assert report.details["attempts"][0]["winerror"] == winerror


def test_explicit_cmd_skips_bare_and_execution_policy_checks(monkeypatch, tmp_path: Path) -> None:
    _touch(tmp_path / "npm.cmd")
    _touch(tmp_path / "npm.ps1")
    _patch_facts(monkeypatch)
    calls: list[tuple[str, ...]] = []

    report = run_command_doctor(
        "NPM.CMD",
        env=_env(tmp_path, pathext=".CMD;.PS1"),
        runner=_runner(
            calls,
            lambda args: CommandExecution(argv=args, returncode=0, stdout="11.0.0\n"),
        ),
    )

    assert report.command == "npm.cmd"
    assert report.successful is True
    assert [check.id for check in report.checks] == ["windows.path_refresh"]
    assert calls[0][1:] == ("--version",)


def test_bare_npm_warning_makes_direct_success_unsuccessful(monkeypatch, tmp_path: Path) -> None:
    _touch(tmp_path / "npm.cmd")
    _patch_facts(monkeypatch, bare=CheckStatus.WARNING)
    report = run_command_doctor(
        "npm",
        env=_env(tmp_path, pathext=".CMD"),
        runner=Runner(
            executor=lambda argv, timeout, env, cwd: CommandExecution(
                argv=tuple(argv), returncode=0, stdout="11.0.0\n"
            )
        ),
    )

    assert report.state is LauncherProbeState.USABLE
    assert report.successful is False
    assert [check.id for check in report.checks] == [
        "windows.path_refresh",
        "powershell.command.npm",
    ]


def test_bare_command_runs_one_direct_and_one_powershell_probe_with_same_timeout(
    monkeypatch, tmp_path: Path
) -> None:
    _touch(tmp_path / "tool.cmd")
    _touch(tmp_path / "powershell.exe")
    monkeypatch.setattr(
        command_doctor_module,
        "collect_path_refresh_check",
        lambda **kwargs: _check("windows.path_refresh", CheckStatus.PASS),
    )
    calls: list[tuple[str, ...]] = []
    timeouts: list[float] = []

    def execute(argv, timeout, env, cwd):
        del env, cwd
        args = tuple(argv)
        calls.append(args)
        timeouts.append(timeout)
        return CommandExecution(argv=args, returncode=0, stdout="tool 1\n")

    report = run_command_doctor(
        "tool",
        env=_env(tmp_path, pathext=".EXE;.CMD"),
        runner=Runner(executor=execute),
        timeout=1.25,
    )

    assert report.successful is True
    assert len(calls) == 2
    assert calls[0][1:] == ("--version",)
    assert "Get-Command tool" in calls[1][-1]
    assert timeouts == [1.25, 1.25]
    assert [check.id for check in report.checks] == [
        "windows.path_refresh",
        "powershell.command.tool",
    ]


def test_explicit_ps1_collects_policy_but_not_bare(monkeypatch, tmp_path: Path) -> None:
    _touch(tmp_path / "tool.ps1")
    _touch(tmp_path / "powershell.exe")
    _patch_facts(monkeypatch)
    calls: list[tuple[str, ...]] = []

    report = run_command_doctor(
        "tool.ps1",
        env=_env(tmp_path, pathext=".EXE"),
        runner=_runner(
            calls,
            lambda args: CommandExecution(argv=args, returncode=0, stdout="tool 1\n"),
        ),
    )

    assert report.successful is True
    assert [check.id for check in report.checks] == [
        "windows.path_refresh",
        "windows.powershell.execution_policy",
    ]
    assert "--version" in calls[0][-1]


def test_refresh_warning_does_not_fail_usable_explicit_command(monkeypatch, tmp_path: Path) -> None:
    _touch(tmp_path / "pnpm.exe")
    monkeypatch.setattr(
        command_doctor_module,
        "collect_path_refresh_check",
        lambda **kwargs: _check("windows.path_refresh", CheckStatus.WARNING),
    )

    report = run_command_doctor(
        "pnpm.exe",
        env=_env(tmp_path),
        runner=Runner(
            executor=lambda argv, timeout, env, cwd: CommandExecution(
                argv=tuple(argv), returncode=0, stdout="9.0.0\n"
            )
        ),
    )

    assert report.successful is True
    assert report.checks[0].status is CheckStatus.WARNING


def test_missing_pnpm_and_refresh_unknown_are_independent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        command_doctor_module,
        "collect_path_refresh_check",
        lambda **kwargs: _check("windows.path_refresh", CheckStatus.UNKNOWN),
    )
    monkeypatch.setattr(
        command_doctor_module,
        "collect_powershell_command_check",
        lambda *args, **kwargs: _check("powershell.command.pnpm", CheckStatus.UNKNOWN),
    )

    report = run_command_doctor("pnpm", env=_env(tmp_path), runner=Runner())

    assert report.state is LauncherProbeState.COMMAND_NOT_FOUND
    assert report.successful is False
    assert report.checks[0].status is CheckStatus.UNKNOWN
    assert report.checks[1].status is CheckStatus.UNKNOWN
    assert "pnpm" not in report.checks[0].summary.casefold()


def test_report_has_stable_v1_shape_and_console_safe_fields(monkeypatch, tmp_path: Path) -> None:
    _touch(tmp_path / "tool.exe")
    _patch_facts(monkeypatch)
    report = run_command_doctor(
        "tool.exe",
        env=_env(tmp_path),
        runner=Runner(
            executor=lambda argv, timeout, env, cwd: CommandExecution(
                argv=tuple(argv), returncode=0, stdout="tool 1\n"
            )
        ),
    )

    payload = report.to_dict()
    assert payload["schema_version"] == 1
    assert payload["kind"] == "command_doctor"
    assert payload["offline"] is True
    assert list(payload) == [
        "schema_version",
        "kind",
        "tool",
        "offline",
        "command",
        "state",
        "successful",
        "path",
        "version",
        "evidence",
        "details",
        "checks",
    ]

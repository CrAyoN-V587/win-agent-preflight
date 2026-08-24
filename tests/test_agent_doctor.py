from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

import win_agent_preflight.windows as windows
from win_agent_preflight.agent_doctor import (
    AgentDoctorState,
    normalize_agents,
    run_agent_doctor,
)
from win_agent_preflight.runner import CommandExecution, Runner


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("launcher", encoding="utf-8")


def _env(directory: Path, *, pathext: str = ".EXE;.CMD;.BAT;.PS1") -> dict[str, str]:
    return {"PATH": str(directory), "PATHEXT": pathext}


def _success_runner(calls: list[tuple[str, ...]]) -> Runner:
    def executor(argv: Sequence[str], timeout, env, cwd) -> CommandExecution:
        del timeout, env, cwd
        args = tuple(argv)
        calls.append(args)
        return CommandExecution(argv=args, returncode=0, stdout="agent 1.0\n")

    return Runner(executor=executor)


def test_agent_selection_is_canonical_and_deduplicated() -> None:
    assert normalize_agents(("dsh", "codex", "codex")) == ("codex", "dsh")


def test_missing_agents_are_not_failures(tmp_path: Path) -> None:
    report = run_agent_doctor(env=_env(tmp_path), runner=Runner())

    assert [item.agent for item in report.agents] == ["codex", "claude", "dsh"]
    assert all(item.state is AgentDoctorState.COMMAND_NOT_FOUND for item in report.agents)
    assert report.has_unusable_agent is False
    assert report.to_dict()["summary"]["command_not_found"] == 3
    assert report.to_dict()["kind"] == "agent_doctor"
    assert report.to_dict()["offline"] is True


def test_only_discovered_launchers_are_probed_in_fixed_order(tmp_path: Path) -> None:
    _touch(tmp_path / "dsh.exe")
    _touch(tmp_path / "codex.cmd")
    calls: list[tuple[str, ...]] = []

    report = run_agent_doctor(
        agents=("dsh", "codex", "dsh"),
        env=_env(tmp_path),
        runner=_success_runner(calls),
    )

    assert [item.agent for item in report.agents] == ["codex", "dsh"]
    assert all(item.state is AgentDoctorState.USABLE for item in report.agents)
    assert all(item.version == "agent 1.0" for item in report.agents)
    assert [Path(call[0]).name for call in calls] == ["codex.cmd", "dsh.exe"]
    assert all(call[1:] == ("--version",) for call in calls)


def test_non_regular_launcher_is_not_reported_as_missing(tmp_path: Path) -> None:
    (tmp_path / "codex.exe").mkdir()

    report = run_agent_doctor(agents=("codex",), env=_env(tmp_path), runner=Runner())

    result = report.agents[0]
    assert result.state is AgentDoctorState.RESOLVED_BUT_NOT_EXECUTABLE
    assert result.details["non_executable_paths"]


def test_lstat_permission_is_access_denied_not_missing(tmp_path: Path, monkeypatch) -> None:
    original_lstat = windows.os.lstat

    def fake_lstat(path):
        if str(path).casefold().endswith("codex.exe"):
            error = PermissionError("secret path")
            error.winerror = 5  # type: ignore[attr-defined]
            raise error
        return original_lstat(path)

    monkeypatch.setattr(windows.os, "lstat", fake_lstat)
    report = run_agent_doctor(
        agents=("codex",),
        env=_env(tmp_path, pathext=".EXE"),
        runner=Runner(),
    )

    result = report.agents[0]
    assert result.state is AgentDoctorState.ACCESS_DENIED
    assert result.details["lstat_errors"][0]["error_type"] == "PermissionError"
    assert result.details["lstat_errors"][0]["winerror"] == 5


def test_version_failure_does_not_echo_stdout_or_stderr(tmp_path: Path) -> None:
    _touch(tmp_path / "claude.exe")
    secret = "TOKEN-DO-NOT-PRINT"

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        args = tuple(argv)
        return CommandExecution(
            argv=args,
            returncode=1,
            stdout=secret,
            stderr=secret,
            error_type="ProcessError",
        )

    report = run_agent_doctor(
        agents=("claude",),
        env=_env(tmp_path),
        runner=Runner(executor=executor),
    )
    result = report.agents[0]

    assert result.state is AgentDoctorState.VERSION_PROBE_FAILED
    assert secret not in str(report.to_dict())
    assert result.details["attempts"][0]["error_type"] == "ProcessError"


def test_success_extracts_first_non_empty_redacted_version_line(tmp_path: Path) -> None:
    profile = tmp_path / "alice"
    profile.mkdir()
    _touch(profile / "codex.exe")

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        return CommandExecution(
            argv=tuple(argv),
            returncode=0,
            stdout=f"\n{profile}\\bin\\codex 1.2.3\nsecond line\n",
        )

    report = run_agent_doctor(
        agents=("codex",),
        env=_env(profile),
        user_profile=str(profile),
        runner=Runner(executor=executor),
    )

    result = report.agents[0]
    assert result.state is AgentDoctorState.USABLE
    assert result.version == r"%USERPROFILE%\bin\codex 1.2.3"
    assert len(result.version) <= 200  # type: ignore[arg-type]
    assert "second line" not in str(report.to_dict())


def test_success_version_redacts_forward_slash_profile(tmp_path: Path) -> None:
    profile = tmp_path / "alice"
    profile.mkdir()
    _touch(profile / "codex.exe")
    output_path = str(profile / "bin" / "codex").replace("\\", "/")

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        return CommandExecution(
            argv=tuple(argv),
            returncode=0,
            stdout=f"{output_path} 1.2.3\n",
        )

    report = run_agent_doctor(
        agents=("codex",),
        env=_env(profile),
        user_profile=str(profile),
        runner=Runner(executor=executor),
    )

    assert report.agents[0].state is AgentDoctorState.USABLE
    assert report.agents[0].version == r"%USERPROFILE%/bin/codex 1.2.3"
    assert "alice" not in str(report.to_dict())


def test_success_uses_stderr_when_stdout_is_empty(tmp_path: Path) -> None:
    _touch(tmp_path / "claude.exe")

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        return CommandExecution(argv=tuple(argv), returncode=0, stdout=" \n", stderr="Claude 2.0\n")

    report = run_agent_doctor(
        agents=("claude",),
        env=_env(tmp_path),
        runner=Runner(executor=executor),
    )

    assert report.agents[0].state is AgentDoctorState.USABLE
    assert report.agents[0].version == "Claude 2.0"


def test_zero_exit_with_empty_output_is_version_failure(tmp_path: Path) -> None:
    _touch(tmp_path / "dsh.exe")

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        return CommandExecution(argv=tuple(argv), returncode=0)

    report = run_agent_doctor(
        agents=("dsh",),
        env=_env(tmp_path),
        runner=Runner(executor=executor),
    )

    result = report.agents[0]
    assert result.state is AgentDoctorState.VERSION_PROBE_FAILED
    assert result.version is None
    assert result.details["attempts"][0]["version_output_present"] is False


def test_runner_permission_failure_has_structured_evidence(tmp_path: Path) -> None:
    _touch(tmp_path / "codex.exe")

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        error = PermissionError("private output")
        error.winerror = 5  # type: ignore[attr-defined]
        return CommandExecution(
            argv=tuple(argv),
            returncode=None,
            error=str(error),
            error_type="PermissionError",
            winerror=5,
        )

    report = run_agent_doctor(
        agents=("codex",),
        env=_env(tmp_path),
        runner=Runner(executor=executor),
    )
    result = report.agents[0]

    assert result.state is AgentDoctorState.ACCESS_DENIED
    assert result.details["attempts"][0]["winerror"] == 5
    assert "private output" not in str(report.to_dict())


@pytest.mark.parametrize(
    ("first_result", "second_result", "expected"),
    [
        (
            CommandExecution(argv=("codex.exe", "--version"), returncode=1),
            CommandExecution(
                argv=("codex.cmd", "--version"),
                returncode=None,
                error_type="OSError",
                winerror=1920,
            ),
            AgentDoctorState.ACCESS_DENIED,
        ),
        (
            CommandExecution(
                argv=("codex.exe", "--version"),
                returncode=None,
                error_type="OSError",
                winerror=193,
            ),
            CommandExecution(argv=("codex.cmd", "--version"), returncode=1),
            AgentDoctorState.RESOLVED_BUT_NOT_EXECUTABLE,
        ),
    ],
)
def test_multiple_candidate_failure_priority(
    tmp_path: Path,
    first_result: CommandExecution,
    second_result: CommandExecution,
    expected: AgentDoctorState,
) -> None:
    _touch(tmp_path / "codex.exe")
    _touch(tmp_path / "codex.cmd")

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        return first_result if str(argv[0]).casefold().endswith("codex.exe") else second_result

    report = run_agent_doctor(
        agents=("codex",),
        env=_env(tmp_path),
        runner=Runner(executor=executor),
    )

    assert report.agents[0].state is expected


def test_ps1_launcher_uses_power_shell_and_only_version(tmp_path: Path) -> None:
    _touch(tmp_path / "codex.ps1")
    _touch(tmp_path / "powershell.exe")
    calls: list[tuple[str, ...]] = []

    report = run_agent_doctor(
        agents=("codex",),
        env=_env(tmp_path, pathext=".EXE"),
        runner=_success_runner(calls),
    )

    assert report.agents[0].state is AgentDoctorState.USABLE
    assert Path(report.agents[0].path or "").suffix.casefold() == ".ps1"
    assert "--version" in calls[0][-1]
    command_line = " ".join(calls[0]).casefold()
    assert all(forbidden not in command_line for forbidden in (" login ", " npx ", " web "))


def test_agent_path_is_redacted(tmp_path: Path) -> None:
    profile = tmp_path / "alice"
    profile.mkdir()
    _touch(profile / "codex.exe")
    environment = _env(profile)
    environment["PATH"] = str(profile)

    report = run_agent_doctor(
        agents=("codex",),
        env=environment,
        user_profile=str(profile),
        runner=_success_runner([]),
    )

    payload = str(report.to_dict())
    assert "alice" not in payload
    assert "%USERPROFILE%" in payload

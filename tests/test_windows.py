from __future__ import annotations

from pathlib import Path

from win_agent_preflight.checks import check_command
from win_agent_preflight.models import CheckStatus
from win_agent_preflight.runner import CommandExecution, Runner
from win_agent_preflight.windows import (
    collect_path_refresh_check,
    collect_powershell_command_check,
    discover_command,
    redact_text,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_missing_required_command_is_fail_with_evidence(tmp_path: Path) -> None:
    result = check_command(
        "git",
        (),
        Runner(),
        required=True,
        env={"PATH": str(tmp_path)},
    )
    assert result.status is CheckStatus.FAIL
    assert result.evidence


def test_discovery_returns_multiple_candidates_in_path_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _touch(first / "tool.cmd")
    _touch(second / "tool.cmd")
    candidates = discover_command(
        "tool",
        env={"PATH": f"{first};{second}", "PATHEXT": ".CMD"},
    )
    assert [Path(item.path).parent.name for item in candidates] == ["first", "second"]


def test_discovery_skips_inaccessible_path_candidate(tmp_path: Path, monkeypatch) -> None:
    blocked = tmp_path / "blocked"
    working = tmp_path / "working"
    _touch(working / "tool.exe")
    original_is_file = Path.is_file

    def fake_is_file(path: Path) -> bool:
        if path.parent == blocked:
            raise OSError("inaccessible execution alias")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    candidates = discover_command(
        "tool",
        env={"PATH": f"{blocked};{working}", "PATHEXT": ".EXE"},
    )

    assert [Path(item.path).parent.name for item in candidates] == ["working"]


def test_npm_cmd_can_start_while_npm_ps1_is_blocked(tmp_path: Path) -> None:
    _touch(tmp_path / "npm.cmd")
    _touch(tmp_path / "npm.ps1")
    _touch(tmp_path / "powershell.exe")
    env = {"PATH": str(tmp_path), "PATHEXT": ".CMD;.EXE"}

    def executor(argv, timeout, environment, cwd):
        del timeout, environment, cwd
        args = tuple(argv)
        if args[0].lower().endswith("npm.cmd"):
            return CommandExecution(argv=args, returncode=0, stdout="11.0.0\n")
        return CommandExecution(
            argv=args,
            returncode=1,
            stderr="cannot be loaded because running scripts is disabled",
        )

    runner = Runner(executor=executor)
    cmd_result = check_command(
        "npm",
        discover_command("npm", env=env),
        runner,
        required=False,
        env=env,
    )
    ps1_result = check_command(
        "npm.ps1",
        discover_command("npm.ps1", env=env),
        runner,
        required=False,
        env=env,
    )
    assert cmd_result.status is CheckStatus.PASS
    assert ps1_result.status is CheckStatus.WARNING
    assert any("scripts" in item for item in ps1_result.evidence)


def test_powershell_bare_npm_detects_blocked_ps1_independently(tmp_path: Path) -> None:
    _touch(tmp_path / "npm.cmd")
    _touch(tmp_path / "npm.ps1")
    _touch(tmp_path / "powershell.exe")
    env = {"PATH": str(tmp_path), "PATHEXT": ".CMD;.EXE"}

    def executor(argv, timeout, environment, cwd):
        del timeout, environment, cwd
        args = tuple(argv)
        if "Get-Command npm" in args[-1]:
            return CommandExecution(
                argv=args,
                returncode=1,
                stderr="npm.ps1 cannot be loaded because running scripts is disabled",
            )
        return CommandExecution(argv=args, returncode=0, stdout="RemoteSigned\n")

    result = collect_powershell_command_check(
        Runner(executor=executor),
        command="npm",
        env=env,
    )
    assert result.id == "powershell.command.npm"
    assert result.status is CheckStatus.WARNING
    assert result.evidence
    assert any("scripts" in item for item in result.evidence)


def test_empty_environment_does_not_inherit_host_path(tmp_path: Path) -> None:
    _touch(tmp_path / "python.exe")
    assert discover_command("python", env={}) == ()


def test_path_refresh_warns_for_uninherited_user_entry(tmp_path: Path) -> None:
    result = collect_path_refresh_check(
        process_path=str(tmp_path / "old"),
        user_path=f"{tmp_path / 'old'};{tmp_path / 'new'}",
    )
    assert result.status is CheckStatus.WARNING
    assert result.details["missing_count"] == 1


def test_user_path_is_redacted() -> None:
    assert redact_text(r"C:\Users\alice\repo\file.txt", user_profile=r"C:\Users\alice") == (
        r"%USERPROFILE%\repo\file.txt"
    )

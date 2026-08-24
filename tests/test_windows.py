from __future__ import annotations

from pathlib import Path

import pytest

import win_agent_preflight.windows as windows
from win_agent_preflight.checks import check_command
from win_agent_preflight.models import CheckStatus
from win_agent_preflight.runner import CommandExecution, Runner
from win_agent_preflight.windows import (
    RegistryPathFacts,
    collect_path_refresh_check,
    collect_powershell_command_check,
    collect_registry_path_facts,
    discover_command,
    expand_registry_path,
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


def test_powershell_bare_success_keeps_only_first_bounded_redacted_line(
    tmp_path: Path,
) -> None:
    _touch(tmp_path / "powershell.exe")
    profile = r"C:\Users\Alice"
    first = rf"{profile}\bin\npm 11.17.0"
    secret = "LATER-SECRET-OUTPUT"
    long_tail = "x" * 400

    def executor(argv, timeout, environment, cwd):
        del timeout, environment, cwd
        return CommandExecution(
            argv=tuple(argv),
            returncode=0,
            stdout=f"\n{first}\n{secret}\n{long_tail}\n",
        )

    result = collect_powershell_command_check(
        Runner(executor=executor),
        command="npm",
        env={"PATH": str(tmp_path), "PATHEXT": ".EXE"},
        user_profile=profile,
    )

    assert result.id == "powershell.command.npm"
    assert result.status is CheckStatus.PASS
    assert len(result.evidence[1]) <= 200
    assert "%USERPROFILE%" in result.evidence[1]
    assert profile.casefold() not in result.evidence[1].casefold()
    assert secret not in result.evidence[1]
    assert long_tail not in result.evidence[1]


@pytest.mark.parametrize("command", ["npm.", "npm.com", "npm.cmd", "bad/name", "bad name"])
def test_powershell_bare_check_rejects_unvalidated_basename(
    command: str, tmp_path: Path
) -> None:
    calls = 0

    def executor(argv, timeout, environment, cwd):
        nonlocal calls
        calls += 1
        return CommandExecution(argv=tuple(argv), returncode=0, stdout="ok\n")

    with pytest.raises(ValueError):
        collect_powershell_command_check(
            Runner(executor=executor), command=command, env={"PATH": str(tmp_path)}
        )
    assert calls == 0


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


def test_registry_facts_are_immutable_and_reader_covers_both_scopes() -> None:
    calls: list[str] = []

    def reader(scope: str):
        calls.append(scope)
        return {
            "Path": rf"%ROOT%;C:\{scope}",
            "Root": rf"C:\{scope}\root",
        }

    facts = collect_registry_path_facts(reader=reader)
    assert calls == ["machine", "user"]
    assert facts.machine_path == r"%ROOT%;C:\machine"
    assert facts.user_path == r"%ROOT%;C:\user"
    assert facts.machine_complete is True
    assert facts.user_complete is True
    assert facts.machine_values == (("Path", r"%ROOT%;C:\machine"), ("Root", r"C:\machine\root"))
    with pytest.raises(Exception):
        facts.machine_path = "changed"  # type: ignore[misc]


def test_registry_missing_key_or_path_is_complete_empty_fact() -> None:
    facts = collect_registry_path_facts(
        reader=lambda scope: {} if scope == "machine" else {"Other": "x"}
    )
    assert facts.machine_path == ""
    assert facts.user_path == ""
    assert facts.complete is True


def test_registry_reader_exception_is_incomplete_not_empty_success() -> None:
    def reader(scope: str):
        if scope == "machine":
            raise PermissionError("denied")
        return {"Path": r"C:\UserTools"}

    facts = collect_registry_path_facts(reader=reader)
    assert facts.machine_path == ""
    assert facts.machine_complete is False
    assert facts.user_complete is True
    assert facts.machine_error


def test_reader_file_not_found_is_an_incomplete_scope() -> None:
    def reader(scope: str):
        if scope == "machine":
            raise FileNotFoundError("key does not exist")
        return {"Path": ""}

    facts = collect_registry_path_facts(reader=reader)
    assert facts.machine_complete is False
    assert facts.machine_path == ""


def test_registry_path_type_error_is_incomplete() -> None:
    facts = collect_registry_path_facts(
        reader=lambda scope: {"Path": 123} if scope == "machine" else {"Path": ""}
    )
    assert facts.machine_complete is False
    assert facts.user_complete is True
    assert facts.machine_error and "not a string" in facts.machine_error


@pytest.mark.parametrize("value_type", [windows._REG_SZ, windows._REG_EXPAND_SZ])
def test_registry_string_types_are_accepted(value_type: int) -> None:
    facts = collect_registry_path_facts(
        reader=lambda scope: {
            "Path": windows._RegistryValue(r"C:\Tools", value_type)
        }
    )
    assert facts.machine_complete is True
    assert facts.user_complete is True
    assert facts.machine_path == r"C:\Tools"


def test_registry_path_other_type_is_incomplete() -> None:
    other_type = next(
        value for value in range(1, 32) if value not in windows._ALLOWED_REGISTRY_TYPES
    )
    facts = collect_registry_path_facts(
        reader=lambda scope: {"Path": (r"C:\Tools", other_type)}
    )
    assert facts.machine_complete is False
    assert facts.user_complete is False


def test_registry_path_none_is_incomplete_but_missing_path_is_empty() -> None:
    facts = collect_registry_path_facts(
        reader=lambda scope: {"Path": None} if scope == "machine" else {"Other": "value"}
    )
    assert facts.machine_complete is False
    assert facts.machine_path == ""
    assert facts.user_complete is True
    assert facts.user_path == ""


def test_registry_path_expansion_is_case_insensitive_and_scope_ordered() -> None:
    facts = RegistryPathFacts(
        machine_values=(("Root", r"C:\Machine"), ("Shared", r"C:\MachineShared")),
        user_values=(("ROOT", r"C:\User"), ("Shared", r"C:\UserShared")),
    )
    machine, machine_unresolved = expand_registry_path(
        r"%root%;%shared%;%ProcessOnly%",
        scope="machine",
        facts=facts,
        process_env={"PROCESSONLY": r"C:\Process", "Root": r"C:\ProcessRoot"},
    )
    user, user_unresolved = expand_registry_path(
        r"%root%;%shared%;%ProcessOnly%",
        scope="user",
        facts=facts,
        process_env={"PROCESSONLY": r"C:\Process", "Root": r"C:\ProcessRoot"},
    )
    assert machine == r"C:\Machine;C:\MachineShared;C:\Process"
    assert user == r"C:\User;C:\UserShared;C:\Process"
    assert machine_unresolved == ()
    assert user_unresolved == ()


def test_registry_path_expansion_allows_nested_references_for_eight_rounds() -> None:
    facts = RegistryPathFacts(
        machine_values=tuple((f"V{index}", f"%V{index + 1}%") for index in range(1, 8))
        + (("V8", r"C:\Deep"),)
    )
    expanded, unresolved = expand_registry_path(
        "%V1%", scope="machine", facts=facts, process_env={}
    )
    assert expanded == r"C:\Deep"
    assert unresolved == ()


def test_registry_path_unresolved_evidence_only_contains_variable_names() -> None:
    secret = r"C:\Users\alice\private-token"
    result = collect_path_refresh_check(
        process_path=r"C:\Windows",
        registry_facts=RegistryPathFacts(user_path=r"%MISSING%"),
    )
    assert result.status is CheckStatus.UNKNOWN
    joined = " ".join(result.evidence)
    assert "MISSING" in joined
    assert secret not in joined


def test_path_refresh_handles_unresolved_and_missing_items_independently() -> None:
    result = collect_path_refresh_check(
        process_path=r"C:\Present",
        registry_facts=RegistryPathFacts(
            user_path=r"%UNSET_ROOT%;C:\Missing;C:\Present"
        ),
    )
    assert result.status is CheckStatus.WARNING
    assert result.details == {"missing_count": 1}
    joined = " ".join(result.evidence)
    assert "UNSET_ROOT" in joined
    assert r"C:\Missing" in joined


def test_path_refresh_uses_windows_path_normalization_and_preserves_source() -> None:
    result = collect_path_refresh_check(
        process_path=r'"C:/Tools/";C:\Windows\\',
        registry_facts=RegistryPathFacts(
            machine_path=r"C:\Tools",
            user_path=r'"C:/Missing/"',
        ),
    )
    assert result.status is CheckStatus.WARNING
    assert result.details == {"missing_count": 1}
    assert any("user:" in item and "C:/Missing" in item for item in result.evidence)


def test_path_refresh_passes_when_both_scopes_are_fully_inherited() -> None:
    result = collect_path_refresh_check(
        process_path=r"C:\Machine;C:\User",
        registry_facts=RegistryPathFacts(
            machine_path=r"c:/machine/",
            user_path=r'"C:\user\\"',
        ),
    )
    assert result.status is CheckStatus.PASS
    assert result.details == {}


def test_path_refresh_warning_survives_error_in_other_scope() -> None:
    result = collect_path_refresh_check(
        process_path=r"C:\Windows",
        registry_facts=RegistryPathFacts(
            machine_path=r"C:\MissingMachine",
            user_complete=False,
            user_error="user registry read failed",
        ),
    )
    assert result.status is CheckStatus.WARNING
    assert result.details == {"missing_count": 1}
    assert any("user registry PATH fact is incomplete" in item for item in result.evidence)


def test_path_refresh_is_unknown_without_process_path() -> None:
    result = collect_path_refresh_check(
        process_path="",
        registry_facts=RegistryPathFacts(user_path=r"C:\Missing"),
    )
    assert result.status is CheckStatus.UNKNOWN


def test_path_refresh_is_unknown_for_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(windows.os, "name", "posix")
    result = collect_path_refresh_check(
        process_path=r"C:\Windows",
        user_path=r"C:\Missing",
    )
    assert result.status is CheckStatus.UNKNOWN


def test_path_refresh_is_unknown_for_only_registry_errors() -> None:
    result = collect_path_refresh_check(
        process_path=r"C:\Windows",
        registry_facts=RegistryPathFacts(
            machine_complete=False,
            machine_error="machine registry read failed",
            user_complete=False,
            user_error="user registry read failed",
        ),
    )
    assert result.status is CheckStatus.UNKNOWN


def test_injected_user_path_takes_precedence_over_registry_reader() -> None:
    calls: list[str] = []

    def reader(scope: str):
        calls.append(scope)
        return {"Path": r"C:\Reader"}

    result = collect_path_refresh_check(
        process_path=r"C:\Injected",
        user_path=r"C:\Injected",
        registry_reader=reader,
    )
    assert result.status is CheckStatus.WARNING
    assert result.details == {"missing_count": 1}
    assert calls == ["machine", "user"]


def test_user_path_is_redacted() -> None:
    assert redact_text(r"C:\Users\alice\repo\file.txt", user_profile=r"C:\Users\alice") == (
        r"%USERPROFILE%\repo\file.txt"
    )


def test_user_path_redaction_accepts_mixed_separators_and_respects_boundary() -> None:
    profile = r"C:\Users\alice"

    assert redact_text("C:/Users/alice/repo/file.txt", user_profile=profile) == (
        "%USERPROFILE%/repo/file.txt"
    )
    unchanged = "C:/Users/alice2/repo/file.txt"
    assert redact_text(unchanged, user_profile=profile) == unchanged

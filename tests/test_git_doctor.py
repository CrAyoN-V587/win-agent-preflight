from __future__ import annotations

import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import win_agent_preflight.git_doctor as git_doctor_module
from win_agent_preflight import cli
from win_agent_preflight.git_doctor import (
    GIT_CHECK_IDS,
    GitDoctorInputError,
    GitDoctorReport,
    run_git_doctor,
)
from win_agent_preflight.models import CheckResult, CheckStatus
from win_agent_preflight.runner import CommandExecution, Runner
from win_agent_preflight.windows import redact_text


def _windows(monkeypatch) -> None:
    monkeypatch.setattr(git_doctor_module.os, "name", "nt")


def _environment(tmp_path: Path, tools: Sequence[str] = ("git",)) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in tools:
        (bin_dir / f"{tool}.exe").write_text("launcher", encoding="utf-8")
    return {
        "PATH": str(bin_dir),
        "PATHEXT": ".EXE;.CMD;.BAT",
        "USERPROFILE": str(tmp_path),
    }


def _recording_runner(
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]],
    factory,
) -> Runner:
    def executor(
        argv: Sequence[str],
        timeout: float,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> CommandExecution:
        normalized = tuple(str(item) for item in argv)
        calls.append((normalized, timeout, env, cwd))
        return factory(normalized)

    return Runner(executor=executor)


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    target.mkdir()
    return target


def _git_tail(argv: tuple[str, ...]) -> tuple[str, ...] | None:
    if "-C" not in argv:
        return None
    index = argv.index("-C")
    return argv[index + 2 :]


def _success_factory(
    *,
    fetch: str = "https://github.com/example/repo.git",
    push: str | None = None,
    name: str = "global\tExample Name",
    email: str = "global\texample@example.invalid",
    helper: str = "manager-core",
    gh: bool = True,
):
    push = fetch if push is None else push

    def factory(argv: tuple[str, ...]) -> CommandExecution:
        executable = Path(argv[0]).stem.casefold()
        tail = _git_tail(argv)
        if tail is None:
            if executable == "git":
                stdout = "git version 2.47.0\n"
            else:
                assert executable == "gh"
                assert gh
                stdout = "gh version 2.60.0\n"
        elif tail == ("rev-parse", "--is-inside-work-tree"):
            stdout = "true\n"
        elif tail == ("config", "--show-scope", "--get", "user.name"):
            stdout = f"{name}\n" if name else ""
        elif tail == ("config", "--show-scope", "--get", "user.email"):
            stdout = f"{email}\n" if email else ""
        elif tail == ("remote", "get-url", "origin"):
            stdout = f"{fetch}\n" if fetch else ""
        elif tail == ("remote", "get-url", "--push", "origin"):
            stdout = f"{push}\n" if push else ""
        elif tail == ("config", "--get-all", "credential.helper"):
            stdout = f"{helper}\n" if helper else ""
        else:  # pragma: no cover - locks the command allow-list in test failures.
            raise AssertionError(f"unexpected Git Doctor command: {argv!r}")
        return CommandExecution(argv=argv, returncode=0, stdout=stdout)

    return factory


def _run_success(
    tmp_path: Path,
    monkeypatch,
    *,
    tools: Sequence[str] = ("git", "gh"),
    factory=None,
    timeout: float = 1.25,
):
    _windows(monkeypatch)
    target = _target(tmp_path)
    environment = _environment(tmp_path, tools)
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]] = []
    report = run_git_doctor(
        target,
        runner=_recording_runner(calls, factory or _success_factory()),
        env=environment,
        user_profile=str(tmp_path),
        timeout=timeout,
    )
    return report, calls, target, environment


def test_success_uses_fixed_commands_and_safe_reduction(tmp_path: Path, monkeypatch) -> None:
    name_secret = "IDENTITY_NAME_SENTINEL"
    email_secret = "IDENTITY_EMAIL_SENTINEL"
    remote_secret = "OWNER_SENTINEL/REPO_SENTINEL"
    helper_secret = "CREDENTIAL_HELPER_PATH_SENTINEL"
    stderr_secret = "STDERR_SENTINEL"

    def factory(argv: tuple[str, ...]) -> CommandExecution:
        execution = _success_factory(
            fetch=f"https://github.com/{remote_secret}.git",
            name=f"global\t{name_secret}",
            email=f"global\t{email_secret}",
            helper=f"manager-core\n{helper_secret}",
        )(argv)
        return CommandExecution(
            argv=execution.argv,
            returncode=execution.returncode,
            stdout=execution.stdout,
            stderr=stderr_secret,
        )

    report, calls, target, environment = _run_success(
        tmp_path, monkeypatch, factory=factory
    )

    assert report.local_ready is True
    assert report.remote_auth_verified is False
    assert [check.id for check in report.checks] == list(GIT_CHECK_IDS)
    assert [check.status for check in report.checks] == [
        CheckStatus.PASS,
        CheckStatus.PASS,
        CheckStatus.PASS,
        CheckStatus.PASS,
        CheckStatus.PASS,
        CheckStatus.PASS,
        CheckStatus.UNKNOWN,
    ]
    assert report.checks[3].details["fetch"]["host_class"] == "github.com"
    assert report.checks[3].details["fetch"]["embedded_userinfo"] is False
    assert report.checks[3].details["fetch_push_same_destination"] is True
    assert report.checks[4].details["helper_count"] == 2
    assert report.checks[4].details["gcm_detected"] is True
    assert report.checks[6].details["reason"] == "not_checked_offline"

    assert [
        (Path(argv[0]).stem.casefold(), _git_tail(argv)) for argv, *_ in calls
    ] == [
        ("git", None),
        ("git", ("rev-parse", "--is-inside-work-tree")),
        ("git", ("config", "--show-scope", "--get", "user.name")),
        ("git", ("config", "--show-scope", "--get", "user.email")),
        ("git", ("remote", "get-url", "origin")),
        ("git", ("remote", "get-url", "--push", "origin")),
        ("git", ("config", "--get-all", "credential.helper")),
        ("gh", None),
    ]
    assert all(timeout == 1.25 for _, timeout, _, _ in calls)
    assert all(env is environment for _, _, env, _ in calls)
    assert all(cwd is None for _, _, _, cwd in calls)

    rendered = json.dumps(report.to_dict(), ensure_ascii=False) + str(report)
    from win_agent_preflight.reporting import render_git_doctor_console

    rendered += render_git_doctor_console(report)
    for secret in (name_secret, email_secret, remote_secret, helper_secret, stderr_secret):
        assert secret not in rendered
    assert "remote_auth_verified" in json.dumps(report.to_dict())
    assert str(target).casefold() not in json.dumps(report.to_dict()).casefold()


def test_git_launcher_failure_short_circuits_all_git_commands(
    tmp_path: Path, monkeypatch
) -> None:
    _windows(monkeypatch)
    target = _target(tmp_path)
    environment = _environment(tmp_path, ("git", "gh"))
    calls: list[tuple[str, ...]] = []
    secret = "LAUNCHER_FAILURE_SENTINEL"

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        args = tuple(argv)
        calls.append(args)
        return CommandExecution(argv=args, returncode=1, stderr=secret, error_type="ProcessError")

    report = run_git_doctor(
        target,
        runner=Runner(executor=executor),
        env=environment,
        user_profile=str(tmp_path),
    )

    assert report.local_ready is False
    assert report.checks[0].status is CheckStatus.FAIL
    assert all(check.status is CheckStatus.UNKNOWN for check in report.checks[1:])
    assert len(calls) == 1
    assert calls[0][1:] == ("--version",)
    assert secret not in str(report.to_dict())


def test_git_launcher_timeout_is_structured_and_does_not_echo_output(
    tmp_path: Path, monkeypatch
) -> None:
    _windows(monkeypatch)
    target = _target(tmp_path)
    environment = _environment(tmp_path, ("git",))
    secret = "TIMEOUT_STDERR_SENTINEL"

    def executor(argv, timeout, env, cwd):
        del timeout, env, cwd
        args = tuple(argv)
        return CommandExecution(
            argv=args,
            returncode=None,
            timed_out=True,
            stderr=secret,
            error_type="TimeoutExpired",
        )

    report = run_git_doctor(
        target,
        runner=Runner(executor=executor),
        env=environment,
        user_profile=str(tmp_path),
        timeout=0.5,
    )

    assert report.checks[0].status is CheckStatus.FAIL
    assert report.checks[0].details["state"] == "version_probe_failed"
    assert report.checks[0].details["attempts"][0]["timed_out"] is True
    assert secret not in str(report.to_dict())


def test_missing_git_has_fail_and_no_runner_calls(tmp_path: Path, monkeypatch) -> None:
    _windows(monkeypatch)
    target = _target(tmp_path)
    environment = _environment(tmp_path, ())
    calls: list[object] = []

    def executor(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("missing Git must not invoke Runner")

    report = run_git_doctor(
        target,
        runner=Runner(executor=executor),
        env=environment,
        user_profile=str(tmp_path),
    )

    assert report.checks[0].status is CheckStatus.FAIL
    assert report.checks[0].details["state"] == "command_not_found"
    assert calls == []


def test_non_repo_short_circuits_dependent_checks(tmp_path: Path, monkeypatch) -> None:
    _windows(monkeypatch)
    target = _target(tmp_path)
    environment = _environment(tmp_path, ("git",))
    calls: list[tuple[str, ...]] = []

    def factory(argv: tuple[str, ...]) -> CommandExecution:
        calls.append(argv)
        if _git_tail(argv) is None:
            return CommandExecution(argv=argv, returncode=0, stdout="git version 2.47\n")
        return CommandExecution(argv=argv, returncode=1, stderr="repo failure sentinel")

    report = run_git_doctor(
        target,
        runner=_recording_runner([], factory),
        env=environment,
        user_profile=str(tmp_path),
    )

    assert report.checks[0].status is CheckStatus.PASS
    assert report.checks[1].status is CheckStatus.FAIL
    assert all(check.status is CheckStatus.UNKNOWN for check in report.checks[2:])
    assert len(calls) == 2
    assert "repo failure sentinel" not in str(report.to_dict())


@pytest.mark.parametrize(
    ("name", "email", "expected_status", "expected_local_ready"),
    [
        ("global\tAlice", "global\talice@example.invalid", CheckStatus.PASS, True),
        ("global\tAlice", "", CheckStatus.WARNING, False),
        ("", "global\talice@example.invalid", CheckStatus.WARNING, False),
        ("global\t", "global\talice@example.invalid", CheckStatus.WARNING, False),
    ],
)
def test_identity_missing_and_empty_values_are_reduced_without_echo(
    tmp_path: Path,
    monkeypatch,
    name: str,
    email: str,
    expected_status: CheckStatus,
    expected_local_ready: bool,
) -> None:
    factory = _success_factory(
        fetch="git@github.com:example/repo.git",
        name=name,
        email=email,
        helper="",
    )
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        tools=("git", "gh"),
        factory=factory,
    )
    assert report.checks[2].status is expected_status
    assert report.local_ready is expected_local_ready
    name_value = name.replace("global\t", "")
    email_value = email.replace("global\t", "")
    assert not name_value or name_value not in str(report.to_dict())
    assert not email_value or email_value not in str(report.to_dict())


def test_identity_scope_is_recorded_but_value_is_not(tmp_path: Path, monkeypatch) -> None:
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(
            fetch="git@github.com:example/repo.git",
            name="worktree\tIDENTITY_SCOPE_SENTINEL",
            email="system\tEMAIL_SCOPE_SENTINEL",
            helper="",
        ),
    )
    details = report.checks[2].details
    assert details["name_scope"] == "worktree"
    assert details["email_scope"] == "system"
    assert "IDENTITY_SCOPE_SENTINEL" not in str(report.to_dict())
    assert "EMAIL_SCOPE_SENTINEL" not in str(report.to_dict())


@pytest.mark.parametrize(
    ("fetch", "push", "transport", "host_class", "github", "origin_status"),
    [
        (
            "https://github.com/example/repo.git",
            "https://github.com/example/repo.git",
            "https",
            "github.com",
            True,
            CheckStatus.PASS,
        ),
        (
            "git@github.com:example/repo.git",
            "git@github.com:example/repo.git",
            "ssh",
            "github.com",
            True,
            CheckStatus.PASS,
        ),
        (
            "ssh://git@github.com/example/repo.git",
            "ssh://git@github.com/example/repo.git",
            "ssh",
            "github.com",
            True,
            CheckStatus.PASS,
        ),
        (
            "https://gitlab.com/example/repo.git",
            "https://gitlab.com/example/repo.git",
            "https",
            "other",
            False,
            CheckStatus.PASS,
        ),
        (r"C:\repos\example", r"C:\repos\example", "local", "local", False, CheckStatus.PASS),
    ],
)
def test_remote_classes_are_reduced_without_running_network(
    tmp_path: Path,
    monkeypatch,
    fetch: str,
    push: str,
    transport: str,
    host_class: str,
    github: bool,
    origin_status: CheckStatus,
) -> None:
    report, calls, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        tools=("git", "gh"),
        factory=_success_factory(fetch=fetch, push=push, helper=""),
    )
    origin = report.checks[3]
    assert origin.status is origin_status
    assert origin.details["fetch"]["transport"] == transport
    assert origin.details["fetch"]["host_class"] == host_class
    if not github:
        assert report.checks[5].details.get("not_applicable") is True
    if github:
        assert any(Path(argv[0]).stem.casefold() == "gh" for argv, *_ in calls)
    else:
        assert not any(Path(argv[0]).stem.casefold() == "gh" for argv, *_ in calls)


def test_remote_userinfo_warns_and_is_only_a_boolean(tmp_path: Path, monkeypatch) -> None:
    secret = "REMOTE_PASSWORD_SENTINEL"
    remote = f"https://user:{secret}@github.com/example/repo.git"
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(fetch=remote, push=remote, helper="manager-core"),
    )
    assert report.local_ready is False
    assert report.checks[3].status is CheckStatus.WARNING
    assert report.checks[3].details["embedded_userinfo"] is True
    assert secret not in str(report.to_dict())


def test_ssh_username_is_not_embedded_http_userinfo(tmp_path: Path, monkeypatch) -> None:
    secret = "SSH_USERNAME_SENTINEL"
    remote = f"ssh://{secret}@github.com/example/repo.git"
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(fetch=remote, push=remote, helper=""),
    )

    assert report.local_ready is True
    assert report.checks[3].status is CheckStatus.PASS
    assert report.checks[3].details["fetch"]["transport"] == "ssh"
    assert report.checks[3].details["fetch"]["embedded_userinfo"] is False
    assert secret not in str(report.to_dict())


def test_ssh_password_warns_without_exposing_value(tmp_path: Path, monkeypatch) -> None:
    secret = "SSH_PASSWORD_SENTINEL"
    remote = f"ssh://git:{secret}@github.com/example/repo.git"
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(fetch=remote, push=remote, helper=""),
    )

    from win_agent_preflight.reporting import render_git_doctor_console

    assert report.local_ready is False
    assert report.checks[3].status is CheckStatus.WARNING
    assert report.checks[3].details["fetch"]["embedded_userinfo"] is True
    rendered = json.dumps(report.to_dict(), ensure_ascii=False)
    rendered += render_git_doctor_console(report)
    assert secret not in rendered


def test_local_remote_with_spaces_is_parsed_without_exposing_path(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "LOCAL_REMOTE_SENTINEL"
    remote = rf"C:\Repos\My Repo\{secret}.git"
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(fetch=remote, push=remote, helper=""),
    )

    assert report.local_ready is True
    assert report.checks[3].status is CheckStatus.PASS
    assert report.checks[3].details["fetch"]["transport"] == "local"
    assert report.checks[3].details["push"]["transport"] == "local"
    assert secret not in str(report.to_dict())


@pytest.mark.parametrize(
    ("name", "email"),
    [
        ("mystery-scope\tIDENTITY_UNKNOWN_SENTINEL", "global\tvalid@example.invalid"),
        ("global\tvalid-name", "mystery-scope\tEMAIL_UNKNOWN_SENTINEL"),
        ("mystery-scope\tIDENTITY_UNKNOWN_SENTINEL", "other-scope\tEMAIL_UNKNOWN_SENTINEL"),
    ],
)
def test_unknown_identity_scope_is_not_treated_as_configured(
    tmp_path: Path, monkeypatch, name: str, email: str
) -> None:
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(
            fetch="git@github.com:example/repo.git",
            name=name,
            email=email,
            helper="",
        ),
    )

    assert report.checks[2].status is CheckStatus.UNKNOWN
    assert report.local_ready is False
    payload = str(report.to_dict())
    assert "IDENTITY_UNKNOWN_SENTINEL" not in payload
    assert "EMAIL_UNKNOWN_SENTINEL" not in payload


def test_fetch_and_push_destinations_are_compared_without_exposing_paths(
    tmp_path: Path, monkeypatch
) -> None:
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(
            fetch="https://github.com/example/repo.git",
            push="https://github.com/example/other.git",
        ),
    )
    assert report.local_ready is True
    assert report.checks[3].details["fetch_push_same_destination"] is False
    assert report.checks[3].status is CheckStatus.PASS


def test_missing_origin_is_warning_and_does_not_run_gh(tmp_path: Path, monkeypatch) -> None:
    def factory(argv: tuple[str, ...]) -> CommandExecution:
        tail = _git_tail(argv)
        if tail == ("remote", "get-url", "origin"):
            return CommandExecution(argv=argv, returncode=1)
        if tail == ("remote", "get-url", "--push", "origin"):
            return CommandExecution(argv=argv, returncode=1)
        return _success_factory(fetch="git@github.com:example/repo.git", helper="")(argv)

    report, calls, _, _ = _run_success(tmp_path, monkeypatch, factory=factory)

    assert report.local_ready is False
    assert report.checks[3].status is CheckStatus.WARNING
    assert report.checks[3].details["fetch"]["configured"] is False
    assert report.checks[3].details["push"]["configured"] is False
    assert report.checks[5].status is CheckStatus.UNKNOWN
    assert not any(Path(argv[0]).stem.casefold() == "gh" for argv, *_ in calls)


@pytest.mark.parametrize(
    ("helper", "transport", "status", "gcm"),
    [
        ("manager-core", "https", CheckStatus.PASS, True),
        ("", "https", CheckStatus.WARNING, False),
        ("custom-helper", "https", CheckStatus.WARNING, False),
        ("", "ssh", CheckStatus.PASS, False),
    ],
)
def test_credential_helper_is_summarized_and_never_verified(
    tmp_path: Path,
    monkeypatch,
    helper: str,
    transport: str,
    status: CheckStatus,
    gcm: bool,
) -> None:
    remote = (
        "https://github.com/example/repo.git"
        if transport == "https"
        else "git@github.com:example/repo.git"
    )
    report, _, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        factory=_success_factory(fetch=remote, push=remote, helper=helper),
    )
    helper_check = report.checks[4]
    assert helper_check.status is status
    assert helper_check.details["gcm_detected"] is gcm
    assert helper_check.details["credentials_verified"] is False
    assert set(helper_check.details) == {
        "configured",
        "gcm_detected",
        "helper_count",
        "credentials_verified",
    }
    assert helper not in str(report.to_dict()) if helper else True


def test_gh_missing_is_warning_but_does_not_block_local_ready(tmp_path: Path, monkeypatch) -> None:
    report, calls, _, _ = _run_success(
        tmp_path,
        monkeypatch,
        tools=("git",),
        factory=_success_factory(gh=False),
    )
    assert report.local_ready is True
    assert report.checks[5].status is CheckStatus.WARNING
    assert report.checks[6].status is CheckStatus.UNKNOWN
    assert not any(Path(argv[0]).stem.casefold() == "gh" for argv, *_ in calls)


@pytest.mark.parametrize("target_kind", ["missing", "file", "symlink", "reparse"])
def test_invalid_target_is_rejected_before_any_runner_call(
    tmp_path: Path, monkeypatch, target_kind: str
) -> None:
    _windows(monkeypatch)
    target = tmp_path / "target"
    if target_kind == "missing":
        pass
    elif target_kind == "file":
        target.write_text("fixture", encoding="utf-8")
    else:
        target.mkdir()
        if target_kind == "symlink":
            original_lstat = Path.lstat

            def fake_lstat(path: Path):
                if path == target:
                    return SimpleNamespace(
                        st_mode=stat.S_IFLNK, st_file_attributes=0, st_reparse_tag=0
                    )
                return original_lstat(path)

            monkeypatch.setattr(Path, "lstat", fake_lstat)
        else:
            original_lstat = Path.lstat

            def fake_lstat(path: Path):
                if path == target:
                    return SimpleNamespace(
                        st_mode=stat.S_IFDIR,
                        st_file_attributes=0x400,
                        st_reparse_tag=1,
                    )
                return original_lstat(path)

            monkeypatch.setattr(Path, "lstat", fake_lstat)
    calls: list[object] = []

    def executor(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid targets must not invoke Runner")

    with pytest.raises(GitDoctorInputError):
        run_git_doctor(
            target,
            runner=Runner(executor=executor),
            env=_environment(tmp_path, ("git",)),
            user_profile=str(tmp_path),
        )
    assert calls == []


def test_non_windows_and_invalid_timeout_are_input_errors_without_runner(
    tmp_path: Path, monkeypatch
) -> None:
    target = _target(tmp_path)
    calls: list[object] = []
    runner = Runner(executor=lambda *args, **kwargs: calls.append((args, kwargs)))

    monkeypatch.setattr(git_doctor_module.os, "name", "posix")
    with pytest.raises(GitDoctorInputError):
        run_git_doctor(target, runner=runner, env={}, user_profile=str(tmp_path))
    assert calls == []

    monkeypatch.setattr(git_doctor_module.os, "name", "nt")
    with pytest.raises(GitDoctorInputError):
        run_git_doctor(target, runner=runner, env={}, user_profile=str(tmp_path), timeout=0)
    with pytest.raises(GitDoctorInputError):
        run_git_doctor(
            target, runner=runner, env={}, user_profile=str(tmp_path), timeout=float("nan")
        )
    assert calls == []


def test_report_requires_fixed_checks_and_never_claims_remote_auth() -> None:
    checks = tuple(
        CheckResult(id=check_id, status=CheckStatus.PASS, summary="fixture")
        for check_id in GIT_CHECK_IDS
    )
    report = GitDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        kind="git_doctor",
        target="%USERPROFILE%\\repo",
        local_ready=False,
        remote_auth_verified=False,
        checks=checks,
    )
    assert report.to_dict()["kind"] == "git_doctor"
    assert report.to_dict()["offline"] is True
    assert report.to_dict()["remote_auth_verified"] is False
    with pytest.raises(ValueError):
        GitDoctorReport(
            schema_version=1,
            tool="win-agent-preflight",
            kind="git_doctor",
            target="target",
            local_ready=True,
            remote_auth_verified=True,
            checks=checks,
        )
    with pytest.raises(ValueError):
        GitDoctorReport(
            schema_version=1,
            tool="win-agent-preflight",
            kind="git_doctor",
            target="target",
            local_ready=True,
            remote_auth_verified=False,
            checks=checks[:-1],
        )


def test_cli_json_console_exit_codes_and_target_requirement(tmp_path: Path, monkeypatch) -> None:
    checks = tuple(
        CheckResult(id=check_id, status=CheckStatus.PASS, summary="fixture")
        for check_id in GIT_CHECK_IDS
    )
    success = GitDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        kind="git_doctor",
        target="%USERPROFILE%\\repo",
        local_ready=True,
        remote_auth_verified=False,
        checks=checks,
    )
    failure = GitDoctorReport(
        schema_version=1,
        tool="win-agent-preflight",
        kind="git_doctor",
        target="%USERPROFILE%\\repo",
        local_ready=False,
        remote_auth_verified=False,
        checks=tuple(
            CheckResult(
                id=check_id,
                status=CheckStatus.FAIL if index == 0 else CheckStatus.UNKNOWN,
                summary="fixture",
                evidence=("failure",) if index == 0 else (),
            )
            for index, check_id in enumerate(GIT_CHECK_IDS)
        ),
    )
    monkeypatch.setattr(cli, "run_git_doctor", lambda target, timeout: success)
    json_result = CliRunner().invoke(
        cli.app, ["git-doctor", "--target", str(tmp_path), "--json", "--pretty"]
    )
    assert json_result.exit_code == 0
    assert json.loads(json_result.stdout)["kind"] == "git_doctor"

    monkeypatch.setattr(cli, "run_git_doctor", lambda target, timeout: failure)
    console_result = CliRunner().invoke(cli.app, ["git-doctor", "--target", str(tmp_path)])
    assert console_result.exit_code == 1
    assert "Local ready: false" in console_result.stdout
    assert "remote_auth_verified" not in console_result.stdout

    monkeypatch.setattr(
        cli,
        "run_git_doctor",
        lambda target, timeout: (_ for _ in ()).throw(
            GitDoctorInputError("invalid target SECRET_TARGET_SENTINEL")
        ),
    )
    input_result = CliRunner().invoke(cli.app, ["git-doctor", "--target", str(tmp_path)])
    assert input_result.exit_code == 2
    assert "SECRET_TARGET_SENTINEL" in input_result.stderr

    required = CliRunner().invoke(cli.app, ["git-doctor"])
    assert required.exit_code == 2
    assert "--target" in required.stderr


def test_redact_text_keeps_user_directory_private_in_git_target() -> None:
    profile = r"C:\Users\GitDoctorAlice"
    assert redact_text(profile + r"\repo", user_profile=profile) == r"%USERPROFILE%\repo"
    assert "GitDoctorAlice" not in redact_text(profile + r"\repo", user_profile=profile)

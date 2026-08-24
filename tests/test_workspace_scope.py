from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import win_agent_preflight.workspace_scope as workspace_scope_module
from win_agent_preflight import cli
from win_agent_preflight.models import CheckResult, CheckStatus
from win_agent_preflight.workspace_probe import (
    WORKSPACE_PROBE_CHECK_IDS,
    WorkspaceProbeInterrupted,
    WorkspaceProbeReport,
    WorkspaceProbeUnexpectedError,
)
from win_agent_preflight.workspace_scope import (
    WORKSPACE_SCOPE_KIND,
    WORKSPACE_SCOPE_SCHEMA_VERSION,
    WORKSPACE_SCOPE_TOOL,
    WorkspaceScopeInputError,
    WorkspaceScopeInterrupted,
    WorkspaceScopeReport,
    WorkspaceScopeState,
    WorkspaceScopeUnexpectedError,
    run_workspace_scope,
)


def _probe(path: str = "workspace", successful: bool = True) -> WorkspaceProbeReport:
    checks = tuple(
        CheckResult(
            id=check_id,
            status=(
                CheckStatus.PASS
                if successful or index != 0
                else CheckStatus.FAIL
            ),
            summary="fixture",
            evidence=("fixture failure",)
            if not successful and index == 0
            else (),
        )
        for index, check_id in enumerate(WORKSPACE_PROBE_CHECK_IDS)
    )
    return WorkspaceProbeReport(
        schema_version=1,
        tool=WORKSPACE_SCOPE_TOOL,
        kind="workspace_probe",
        target=path,
        successful=successful,
        checks=checks,
    )


def _unknown_probe(path: str = "workspace") -> WorkspaceProbeReport:
    checks = tuple(
        CheckResult(
            id=check_id,
            status=CheckStatus.UNKNOWN,
            summary="fixture unknown",
        )
        for check_id in WORKSPACE_PROBE_CHECK_IDS
    )
    return WorkspaceProbeReport(
        schema_version=1,
        tool=WORKSPACE_SCOPE_TOOL,
        kind="workspace_probe",
        target=path,
        successful=False,
        checks=checks,
    )


def _scope(
    target: WorkspaceProbeReport | None = None,
    control: WorkspaceProbeReport | None = None,
    *,
    state: WorkspaceScopeState = WorkspaceScopeState.INCONCLUSIVE,
    complete: bool = False,
) -> WorkspaceScopeReport:
    return WorkspaceScopeReport(
        schema_version=WORKSPACE_SCOPE_SCHEMA_VERSION,
        tool=WORKSPACE_SCOPE_TOOL,
        kind=WORKSPACE_SCOPE_KIND,
        target="%USERPROFILE%\\target",
        control="%USERPROFILE%\\control",
        target_probe=target,
        control_probe=control,
        state=state,
        complete=complete,
    )


@pytest.fixture(autouse=True)
def windows_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("win_agent_preflight.workspace_scope.os.name", "nt")


@pytest.mark.parametrize(
    ("target_ok", "control_ok", "expected"),
    [
        (True, True, WorkspaceScopeState.BOTH_USABLE),
        (False, True, WorkspaceScopeState.TARGET_SPECIFIC_FAILURE),
        (True, False, WorkspaceScopeState.CONTROL_SPECIFIC_FAILURE),
        (False, False, WorkspaceScopeState.BOTH_FAILED),
    ],
)
def test_state_matrix_runs_target_then_control(
    tmp_path: Path,
    target_ok: bool,
    control_ok: bool,
    expected: WorkspaceScopeState,
) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()
    calls: list[Path] = []

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        assert allow_write is True
        calls.append(path)
        return _probe(str(path), target_ok if path == target_dir.resolve() else control_ok)

    report = run_workspace_scope(target_dir, control_dir, allow_write=True, probe_runner=probe)

    assert report.state is expected
    assert report.complete is True
    assert report.successful is (expected is WorkspaceScopeState.BOTH_USABLE)
    assert calls == [target_dir.resolve(), control_dir.resolve()]
    assert report.to_dict()["state"] == expected.value


def test_report_rejects_conflicting_complete_state() -> None:
    target = _probe("target", True)
    control = _probe("control", False)
    with pytest.raises(ValueError):
        WorkspaceScopeReport(
            schema_version=1,
            tool=WORKSPACE_SCOPE_TOOL,
            kind=WORKSPACE_SCOPE_KIND,
            target="target",
            control="control",
            target_probe=target,
            control_probe=control,
            state=WorkspaceScopeState.BOTH_USABLE,
            complete=True,
        )


@pytest.mark.parametrize("field", ["target_probe", "control_probe"])
def test_report_rejects_invalid_nested_types_for_partial_state(field: str) -> None:
    values = {"target_probe": None, "control_probe": None}
    values[field] = "not a report"
    with pytest.raises(ValueError, match=field):
        WorkspaceScopeReport(
            schema_version=1,
            tool=WORKSPACE_SCOPE_TOOL,
            kind=WORKSPACE_SCOPE_KIND,
            target="target",
            control="control",
            target_probe=values["target_probe"],  # type: ignore[arg-type]
            control_probe=values["control_probe"],  # type: ignore[arg-type]
            state=WorkspaceScopeState.INCONCLUSIVE,
            complete=False,
        )


@pytest.mark.parametrize(
    ("unknown_target", "unknown_control"),
    [(True, False), (False, True), (True, True)],
)
def test_unknown_probe_outcome_is_inconclusive_but_complete(
    tmp_path: Path,
    unknown_target: bool,
    unknown_control: bool,
) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()
    calls: list[Path] = []

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        calls.append(path)
        is_target = path == target_dir.resolve()
        unknown = unknown_target if is_target else unknown_control
        return (_unknown_probe if unknown else _probe)(str(path))

    report = run_workspace_scope(
        target_dir,
        control_dir,
        allow_write=True,
        probe_runner=probe,
    )

    assert report.state is WorkspaceScopeState.INCONCLUSIVE
    assert report.complete is True
    assert report.successful is False
    assert calls == [target_dir.resolve(), control_dir.resolve()]
    with pytest.raises(ValueError):
        WorkspaceScopeReport(
            schema_version=1,
            tool=WORKSPACE_SCOPE_TOOL,
            kind=WORKSPACE_SCOPE_KIND,
            target="target",
            control="control",
            target_probe=None,
            control_probe=None,
            state=WorkspaceScopeState.INCONCLUSIVE,
            complete=True,
        )


@pytest.mark.parametrize(
    "case", ["missing", "control_missing", "file", "same", "not_allowed"]
)
def test_all_input_validation_precedes_probe_calls(
    tmp_path: Path, case: str
) -> None:
    target = tmp_path / "target"
    control = tmp_path / "control"
    target.mkdir()
    control.mkdir()
    calls: list[Path] = []

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        calls.append(path)
        return _probe(str(path))

    if case == "missing":
        target = tmp_path / "does-not-exist"
    elif case == "control_missing":
        control = tmp_path / "does-not-exist"
    elif case == "file":
        target = tmp_path / "file"
        target.write_text("not a directory", encoding="utf-8")
    elif case == "same":
        control = target

    with pytest.raises(WorkspaceScopeInputError):
        run_workspace_scope(
            target,
            control,
            allow_write=case != "not_allowed",
            probe_runner=probe,
        )
    assert calls == []


def test_non_windows_rejects_before_directory_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("win_agent_preflight.workspace_scope.os.name", "posix")
    calls: list[Path] = []

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        calls.append(path)
        return _probe(str(path))

    with pytest.raises(WorkspaceScopeInputError, match="Windows"):
        run_workspace_scope(tmp_path, tmp_path, allow_write=True, probe_runner=probe)
    assert calls == []


def test_target_unexpected_error_is_partial_and_does_not_probe_control(
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()
    calls: list[Path] = []
    partial = _probe(str(target_dir), False)

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        calls.append(path)
        raise WorkspaceProbeUnexpectedError(partial, RuntimeError("SECRET path"))

    with pytest.raises(WorkspaceScopeUnexpectedError) as raised:
        run_workspace_scope(target_dir, control_dir, allow_write=True, probe_runner=probe)
    assert calls == [target_dir.resolve()]
    assert raised.value.report.state is WorkspaceScopeState.INCONCLUSIVE
    assert raised.value.report.target_probe is not None
    assert raised.value.report.target_probe.target.endswith("target")
    assert raised.value.report.control_probe is None
    assert "SECRET" not in str(raised.value)


def test_control_interrupt_is_partial_and_does_not_retry(
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()
    target_report = _probe(str(target_dir), True)
    control_report = _probe(str(control_dir), False)
    calls: list[Path] = []

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        calls.append(path)
        if path == target_dir.resolve():
            return target_report
        raise WorkspaceProbeInterrupted(control_report)

    with pytest.raises(WorkspaceScopeInterrupted) as raised:
        run_workspace_scope(target_dir, control_dir, allow_write=True, probe_runner=probe)
    assert calls == [target_dir.resolve(), control_dir.resolve()]
    assert raised.value.report.complete is False
    assert raised.value.report.state is WorkspaceScopeState.INCONCLUSIVE
    assert raised.value.report.target_probe is not None
    assert raised.value.report.control_probe is not None
    assert raised.value.report.target_probe.target.endswith("target")
    assert raised.value.report.control_probe.target.endswith("control")


def test_raw_unexpected_exception_is_redacted_partial(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        raise RuntimeError("SECRET_OUTPUT C:\\Users\\alice\\private")

    with pytest.raises(WorkspaceScopeUnexpectedError) as raised:
        run_workspace_scope(
            target_dir,
            control_dir,
            allow_write=True,
            probe_runner=probe,
            user_profile=r"C:\Users\alice",
        )
    assert "SECRET_OUTPUT" not in str(raised.value)
    assert "C:\\Users\\alice" not in json.dumps(raised.value.report.to_dict())


def test_scope_paths_are_redacted(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()
    profile = str(tmp_path)

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        return _probe(str(path))

    report = run_workspace_scope(
        target_dir,
        control_dir,
        allow_write=True,
        probe_runner=probe,
        user_profile=profile,
    )
    payload = json.dumps(report.to_dict())
    assert profile.casefold() not in payload.casefold()
    assert "%USERPROFILE%" in payload


def test_default_probe_receives_user_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()
    received: list[str | None] = []

    def fake_probe(
        path: Path, *, allow_write: bool, user_profile: str | None
    ) -> WorkspaceProbeReport:
        received.append(user_profile)
        return _probe(str(path))

    monkeypatch.setattr(workspace_scope_module, "run_workspace_probe", fake_probe)
    profile = r"C:\Users\alice"
    run_workspace_scope(target_dir, control_dir, allow_write=True, user_profile=profile)

    assert received == [profile, profile]


def test_nested_exception_evidence_is_redacted(tmp_path: Path) -> None:
    target_dir = tmp_path / "target"
    control_dir = tmp_path / "control"
    target_dir.mkdir()
    control_dir.mkdir()
    sentinel = r"C:\Users\alice\nested-secret"
    checks = list(_probe(str(target_dir), False).checks)
    checks[0] = CheckResult(
        id=checks[0].id,
        status=CheckStatus.FAIL,
        summary=checks[0].summary,
        evidence=(sentinel,),
    )
    nested = WorkspaceProbeReport(
        schema_version=1,
        tool=WORKSPACE_SCOPE_TOOL,
        kind="workspace_probe",
        target=str(target_dir),
        successful=False,
        checks=tuple(checks),
    )

    def probe(path: Path, *, allow_write: bool) -> WorkspaceProbeReport:
        raise WorkspaceProbeUnexpectedError(nested, RuntimeError("nested failure"))

    with pytest.raises(WorkspaceScopeUnexpectedError) as raised:
        run_workspace_scope(
            target_dir,
            control_dir,
            allow_write=True,
            probe_runner=probe,
            user_profile=r"C:\Users\alice",
        )

    payload = raised.value.report.to_dict()
    assert sentinel.casefold() not in json.dumps(payload).casefold()
    assert payload["target_probe"]["checks"][0]["evidence"] == [
        "%USERPROFILE%\\nested-secret"
    ]


def test_cli_workspace_scope_json_exit_codes_and_required_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    success = _scope(
        _probe("target", True),
        _probe("control", True),
        state=WorkspaceScopeState.BOTH_USABLE,
        complete=True,
    )
    failure = _scope(
        _probe("target", False),
        _probe("control", True),
        state=WorkspaceScopeState.TARGET_SPECIFIC_FAILURE,
        complete=True,
    )
    received: list[tuple[Path, Path, bool]] = []

    def fake_scope(target: Path, control: Path, *, allow_write: bool) -> WorkspaceScopeReport:
        received.append((target, control, allow_write))
        return success

    monkeypatch.setattr(cli, "run_workspace_scope", fake_scope)
    target = tmp_path / "target"
    control = tmp_path / "control"
    target.mkdir()
    control.mkdir()
    result = CliRunner().invoke(
        cli.app,
        [
            "workspace-scope",
            "--target",
            str(target),
            "--control",
            str(control),
            "--allow-write",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["state"] == "both_usable"
    assert received == [(target, control, True)]

    monkeypatch.setattr(cli, "run_workspace_scope", lambda *args, **kwargs: failure)
    failed = CliRunner().invoke(
        cli.app,
        [
            "workspace-scope",
            "--target",
            str(target),
            "--control",
            str(control),
            "--allow-write",
            "--json",
        ],
    )
    assert failed.exit_code == 1
    assert json.loads(failed.stdout)["state"] == "target_specific_failure"

    unknown = _scope(
        _unknown_probe("target"),
        _probe("control", True),
        state=WorkspaceScopeState.INCONCLUSIVE,
        complete=True,
    )
    monkeypatch.setattr(cli, "run_workspace_scope", lambda *args, **kwargs: unknown)
    unknown_result = CliRunner().invoke(
        cli.app,
        [
            "workspace-scope",
            "--target",
            str(target),
            "--control",
            str(control),
            "--allow-write",
            "--json",
        ],
    )
    assert unknown_result.exit_code == 1
    assert json.loads(unknown_result.stdout)["state"] == "inconclusive"

    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        return success

    monkeypatch.setattr(cli, "run_workspace_scope", should_not_run)
    refused = CliRunner().invoke(
        cli.app,
        [
            "workspace-scope",
            "--target",
            str(target),
            "--control",
            str(control),
        ],
    )
    assert refused.exit_code == 2
    assert refused.stdout == ""
    assert called is False


def test_cli_workspace_scope_console_and_partial_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    control = tmp_path / "control"
    target.mkdir()
    control.mkdir()
    partial = _scope(_probe("target", False))

    monkeypatch.setattr(
        cli,
        "run_workspace_scope",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WorkspaceScopeUnexpectedError(partial, RuntimeError("secret"))
        ),
    )
    unexpected = CliRunner().invoke(
        cli.app,
        [
            "workspace-scope",
            "--target",
            str(target),
            "--control",
            str(control),
            "--allow-write",
        ],
    )
    assert unexpected.exit_code == 1
    assert "State: inconclusive" in unexpected.stdout
    assert "secret" not in unexpected.output

    monkeypatch.setattr(
        cli,
        "run_workspace_scope",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WorkspaceScopeInterrupted(partial)
        ),
    )
    interrupted = CliRunner().invoke(
        cli.app,
        [
            "workspace-scope",
            "--target",
            str(target),
            "--control",
            str(control),
            "--allow-write",
            "--json",
        ],
    )
    assert interrupted.exit_code == 130
    assert json.loads(interrupted.stdout)["complete"] is False

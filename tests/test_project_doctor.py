from __future__ import annotations

import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from win_agent_preflight import cli, project_doctor
from win_agent_preflight.models import CheckResult, CheckStatus
from win_agent_preflight.project_doctor import (
    PROJECT_DOCTOR_KIND,
    PROJECT_DOCTOR_SCHEMA_VERSION,
    PROJECT_DOCTOR_TOOL,
    ProjectDoctorInputError,
    ProjectDoctorReport,
    ProjectMarkerStatus,
    run_project_doctor,
)
from win_agent_preflight.runner import CommandExecution, Runner

ALL_TOOLS = ("python", "node", "npm", "pnpm", "cmake")


def _windows(monkeypatch) -> None:
    monkeypatch.setattr(project_doctor.os, "name", "nt")


def _environment(tmp_path: Path, tools: Sequence[str] = ALL_TOOLS) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in tools:
        (bin_dir / f"{tool}.exe").write_text("launcher", encoding="utf-8")
    return {
        "PATH": str(bin_dir),
        "PATHEXT": ".EXE;.CMD;.BAT",
        "USERPROFILE": str(tmp_path),
    }


def _runner(
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]],
    *,
    execution_factory=None,
) -> Runner:
    def executor(
        argv: Sequence[str],
        timeout: float,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> CommandExecution:
        normalized = tuple(str(item) for item in argv)
        calls.append((normalized, timeout, env, cwd))
        if execution_factory is None:
            return CommandExecution(
                argv=normalized,
                returncode=0,
                stdout=f"{Path(normalized[0]).stem} 1.0\n",
            )
        return execution_factory(normalized)

    return Runner(executor=executor)


def _run(
    tmp_path: Path,
    monkeypatch,
    markers: Sequence[str],
    *,
    tools: Sequence[str] = ALL_TOOLS,
    execution_factory=None,
):
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    for marker in markers:
        (target / marker).write_text("marker contents are never read", encoding="utf-8")
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]] = []
    report = run_project_doctor(
        target,
        runner=_runner(calls, execution_factory=execution_factory),
        env=_environment(tmp_path, tools),
        user_profile=str(tmp_path),
        timeout=1.5,
    )
    return report, calls, target


def test_python_markers_are_deduplicated_and_only_python_runs(tmp_path: Path, monkeypatch) -> None:
    report, calls, _ = _run(
        tmp_path,
        monkeypatch,
        ["pyproject.toml", "requirements.txt"],
    )

    assert report.schema_version == PROJECT_DOCTOR_SCHEMA_VERSION
    assert report.tool == PROJECT_DOCTOR_TOOL
    assert report.kind == PROJECT_DOCTOR_KIND
    assert report.markers == ("pyproject.toml", "requirements.txt")
    assert report.marker_status is ProjectMarkerStatus.CLEAR
    assert report.required_tools == ("python",)
    assert [check.id for check in report.checks] == ["project.markers", "project.python"]
    assert report.checks[0].status is CheckStatus.PASS
    assert report.checks[1].details["required_by"] == [
        "pyproject.toml",
        "requirements.txt",
    ]
    assert report.successful is True
    assert [Path(argv[0]).stem for argv, _, _, _ in calls] == ["python"]
    assert all(argv[1:] == ("--version",) for argv, _, _, _ in calls)
    assert all(cwd is None for _, _, _, cwd in calls)


@pytest.mark.parametrize(
    ("markers", "required", "status"),
    [
        (["package.json", "package-lock.json"], ("node", "npm"), ProjectMarkerStatus.CLEAR),
        (["package.json", "npm-shrinkwrap.json"], ("node", "npm"), ProjectMarkerStatus.CLEAR),
        (
            ["package.json", "package-lock.json", "npm-shrinkwrap.json"],
            ("node", "npm"),
            ProjectMarkerStatus.CLEAR,
        ),
        (["package.json", "pnpm-lock.yaml"], ("node", "pnpm"), ProjectMarkerStatus.CLEAR),
        (
            ["package.json", "package-lock.json", "pnpm-lock.yaml"],
            ("node",),
            ProjectMarkerStatus.UNKNOWN,
        ),
        (["package-lock.json"], (), ProjectMarkerStatus.UNKNOWN),
        (["yarn.lock"], (), ProjectMarkerStatus.UNKNOWN),
        (["package.json", "yarn.lock"], ("node",), ProjectMarkerStatus.UNKNOWN),
        (["CMakeLists.txt"], ("cmake",), ProjectMarkerStatus.CLEAR),
        (["Makefile"], (), ProjectMarkerStatus.UNKNOWN),
        (["pyproject.toml", "Makefile"], ("python",), ProjectMarkerStatus.CLEAR),
        (
            ["pyproject.toml", "package.json", "package-lock.json", "CMakeLists.txt"],
            ("python", "node", "npm", "cmake"),
            ProjectMarkerStatus.CLEAR,
        ),
    ],
)
def test_marker_derivation_and_fixed_tool_order(
    tmp_path: Path,
    monkeypatch,
    markers: Sequence[str],
    required: tuple[str, ...],
    status: ProjectMarkerStatus,
) -> None:
    report, calls, _ = _run(tmp_path, monkeypatch, markers)

    assert report.required_tools == required
    assert report.marker_status is status
    assert tuple(Path(argv[0]).stem for argv, _, _, _ in calls) == required
    assert all(argv[1:] == ("--version",) for argv, _, _, _ in calls)
    assert all(cwd is None for _, _, _, cwd in calls)
    assert report.successful is (status is ProjectMarkerStatus.CLEAR)
    assert report.checks[0].id == "project.markers"
    assert report.checks[0].status is (
        CheckStatus.PASS if status is ProjectMarkerStatus.CLEAR else CheckStatus.UNKNOWN
    )


def test_nested_or_boundary_names_are_ignored_without_directory_walk(
    tmp_path: Path, monkeypatch
) -> None:
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    (target / "package.json.bak").write_text("fixture", encoding="utf-8")
    nested = target / "nested"
    nested.mkdir()
    (nested / "package.json").write_text("fixture", encoding="utf-8")
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]] = []

    report = run_project_doctor(
        target,
        runner=_runner(calls),
        env=_environment(tmp_path, ()),
        user_profile=str(tmp_path),
    )

    assert report.markers == ()
    assert report.marker_status is ProjectMarkerStatus.UNKNOWN
    assert report.required_tools == ()
    assert calls == []


def test_required_by_is_fixed_and_ordered_for_package_tools(
    tmp_path: Path, monkeypatch
) -> None:
    report, _, _ = _run(
        tmp_path,
        monkeypatch,
        ["package.json", "package-lock.json", "npm-shrinkwrap.json"],
    )

    assert [check.id for check in report.checks] == [
        "project.markers",
        "project.node",
        "project.npm",
    ]
    assert report.checks[1].details["required_by"] == ["package.json"]
    assert report.checks[2].details["required_by"] == [
        "package-lock.json",
        "npm-shrinkwrap.json",
    ]
    assert report.to_dict()["summary"] == {
        "pass": 3,
        "warning": 0,
        "fail": 0,
        "unknown": 0,
    }


def test_marker_contents_are_never_opened(tmp_path: Path, monkeypatch) -> None:
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    (target / "pyproject.toml").write_text("fixture", encoding="utf-8")
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]] = []

    def forbidden_read(*args, **kwargs):
        raise AssertionError("project-doctor must not read marker contents")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    report = run_project_doctor(
        target,
        runner=_runner(calls),
        env=_environment(tmp_path, ("python",)),
        user_profile=str(tmp_path),
    )

    assert report.successful is True
    assert len(calls) == 1


@pytest.mark.parametrize("target_kind", ["missing", "file", "symlink", "reparse"])
def test_invalid_target_is_rejected_before_marker_scan(
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

    if target_kind in {"symlink", "reparse"}:
        original_lstat = Path.lstat

        def fake_lstat(path: Path):
            if path == target:
                mode = stat.S_IFLNK if target_kind == "symlink" else stat.S_IFDIR
                return SimpleNamespace(
                    st_mode=mode,
                    st_file_attributes=0x400 if target_kind == "reparse" else 0,
                    st_reparse_tag=1 if target_kind == "reparse" else 0,
                )
            return original_lstat(path)

        monkeypatch.setattr(Path, "lstat", fake_lstat)

    with pytest.raises(ProjectDoctorInputError):
        run_project_doctor(
            target,
            runner=_runner([]),
            env=_environment(tmp_path, ()),
            user_profile=str(tmp_path),
        )


@pytest.mark.parametrize("invalid_kind", ["directory", "symlink", "reparse"])
def test_invalid_marker_is_unknown_without_stopping_scan(
    tmp_path: Path, monkeypatch, invalid_kind: str
) -> None:
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    marker = target / "package.json"
    if invalid_kind == "directory":
        marker.mkdir()
    else:
        marker.write_text("fixture", encoding="utf-8")
        original_lstat = Path.lstat

        def fake_lstat(path: Path):
            if path == marker:
                mode = stat.S_IFLNK if invalid_kind == "symlink" else stat.S_IFREG
                return SimpleNamespace(
                    st_mode=mode,
                    st_file_attributes=0x400 if invalid_kind == "reparse" else 0,
                    st_reparse_tag=1 if invalid_kind == "reparse" else 0,
                )
            return original_lstat(path)

        monkeypatch.setattr(Path, "lstat", fake_lstat)

    report = run_project_doctor(
        target,
        runner=_runner([]),
        env=_environment(tmp_path, ()),
        user_profile=str(tmp_path),
    )
    assert report.markers == ()
    assert report.marker_status is ProjectMarkerStatus.UNKNOWN
    assert report.checks[0].id == "project.markers"
    assert report.checks[0].status is CheckStatus.UNKNOWN
    assert report.to_dict()["summary"]["unknown"] == 1


def test_marker_permission_error_is_unknown_and_other_tools_continue(
    tmp_path: Path, monkeypatch
) -> None:
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    (target / "pyproject.toml").write_text("fixture", encoding="utf-8")
    denied = target / "package.json"
    denied.write_text("fixture", encoding="utf-8")
    original_lstat = Path.lstat

    def fake_lstat(path: Path):
        if path == denied:
            raise PermissionError(f"denied {tmp_path}\\private")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]] = []
    report = run_project_doctor(
        target,
        runner=_runner(calls),
        env=_environment(tmp_path, ("python",)),
        user_profile=str(tmp_path),
    )

    assert report.markers == ("pyproject.toml",)
    assert report.required_tools == ("python",)
    assert report.marker_status is ProjectMarkerStatus.UNKNOWN
    assert report.checks[0].status is CheckStatus.UNKNOWN
    assert report.checks[1].status is CheckStatus.PASS
    assert "private" in report.unknown_reasons[0]
    assert "%USERPROFILE%" in report.unknown_reasons[0]
    assert str(tmp_path).casefold() not in json.dumps(report.to_dict()).casefold()
    assert all(argv[1:] == ("--version",) and cwd is None for argv, _, _, cwd in calls)


def test_marker_anomaly_report_is_cli_exit_one(tmp_path: Path, monkeypatch) -> None:
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    marker = target / "package.json"
    marker.mkdir()
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]] = []
    report = run_project_doctor(
        target,
        runner=_runner(calls),
        env=_environment(tmp_path, ()),
        user_profile=str(tmp_path),
    )
    monkeypatch.setattr(cli, "run_project_doctor", lambda target, timeout: report)

    result = CliRunner().invoke(
        cli.app,
        ["project-doctor", "--target", str(target), "--json"],
    )

    payload = json.loads(result.stdout)
    assert result.exit_code == 1
    assert payload["checks"][0]["id"] == "project.markers"
    assert payload["checks"][0]["status"] == "unknown"
    assert payload["summary"]["unknown"] == 1


@pytest.mark.parametrize("mode", ["missing", "exit", "timeout"])
def test_required_tool_failures_are_failures(tmp_path: Path, monkeypatch, mode: str) -> None:
    def execution_factory(argv: tuple[str, ...]) -> CommandExecution:
        if mode == "timeout":
            return CommandExecution(
                argv=argv,
                returncode=None,
                timed_out=True,
                error="timeout at C:\\Users\\alice\\private",
            )
        return CommandExecution(
            argv=argv,
            returncode=1,
            stderr="failed at C:\\Users\\alice\\private",
        )

    tools = () if mode == "missing" else ("python",)
    report, calls, _ = _run(
        tmp_path,
        monkeypatch,
        ["pyproject.toml"],
        tools=tools,
        execution_factory=execution_factory,
    )

    assert report.successful is False
    assert report.checks[0].status is CheckStatus.PASS
    assert report.checks[1].status is CheckStatus.FAIL
    assert report.to_dict()["summary"]["fail"] == 1
    assert str(tmp_path).casefold() not in json.dumps(report.to_dict()).casefold()
    assert all(cwd is None for _, _, _, cwd in calls)


def test_report_and_cli_json_console_and_exit_codes(tmp_path: Path, monkeypatch) -> None:
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    success = ProjectDoctorReport(
        schema_version=1,
        tool=PROJECT_DOCTOR_TOOL,
        kind=PROJECT_DOCTOR_KIND,
        target="%USERPROFILE%/project",
        markers=("pyproject.toml",),
        marker_status=ProjectMarkerStatus.CLEAR,
        unknown_reasons=(),
        required_tools=("python",),
        checks=(
            CheckResult(
                id="project.markers",
                status=CheckStatus.PASS,
                summary="markers are clear",
                evidence=("fixed marker set is clear",),
            ),
            CheckResult(
                id="project.python",
                status=CheckStatus.PASS,
                summary="usable",
                evidence=("version probe succeeded",),
            ),
        ),
    )
    unknown = ProjectDoctorReport(
        schema_version=1,
        tool=PROJECT_DOCTOR_TOOL,
        kind=PROJECT_DOCTOR_KIND,
        target="%USERPROFILE%/project",
        markers=(),
        marker_status=ProjectMarkerStatus.UNKNOWN,
        unknown_reasons=("no supported project marker",),
        required_tools=(),
        checks=(
            CheckResult(
                id="project.markers",
                status=CheckStatus.UNKNOWN,
                summary="markers are unknown",
                evidence=("no supported project marker",),
            ),
        ),
    )

    monkeypatch.setattr(cli, "run_project_doctor", lambda target, timeout: success)
    result = CliRunner().invoke(
        cli.app,
        ["project-doctor", "--target", str(target), "--json", "--pretty"],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["kind"] == PROJECT_DOCTOR_KIND
    assert "project.python" in result.stdout

    monkeypatch.setattr(cli, "run_project_doctor", lambda target, timeout: unknown)
    unknown_result = CliRunner().invoke(
        cli.app,
        ["project-doctor", "--target", str(target)],
    )
    assert unknown_result.exit_code == 1
    assert "Marker status: unknown" in unknown_result.stdout

    monkeypatch.setattr(
        cli,
        "run_project_doctor",
        lambda target, timeout: (_ for _ in ()).throw(
            ProjectDoctorInputError("bad target C:\\Users\\alice\\secret")
        ),
    )
    input_result = CliRunner().invoke(
        cli.app,
        ["project-doctor", "--target", str(target)],
    )
    assert input_result.exit_code == 2
    assert "secret" in input_result.stderr


def test_project_doctor_requires_explicit_target() -> None:
    result = CliRunner().invoke(cli.app, ["project-doctor"])
    assert result.exit_code == 2
    assert "--target" in result.stderr


def test_first_candidate_failure_falls_back_to_second_version_probe(
    tmp_path: Path, monkeypatch
) -> None:
    _windows(monkeypatch)
    target = tmp_path / "project"
    target.mkdir()
    (target / "pyproject.toml").write_text("fixture", encoding="utf-8")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "python.exe").write_text("launcher", encoding="utf-8")
    (second / "python.exe").write_text("launcher", encoding="utf-8")
    environment = {
        "PATH": f"{first};{second}",
        "PATHEXT": ".EXE",
        "USERPROFILE": str(tmp_path),
    }
    calls: list[tuple[tuple[str, ...], float, Mapping[str, str] | None, str | None]] = []

    def execution_factory(argv: tuple[str, ...]) -> CommandExecution:
        if Path(argv[0]).parent == first:
            return CommandExecution(argv=argv, returncode=1, stderr="first failed")
        return CommandExecution(argv=argv, returncode=0, stdout="Python 3.12\n")

    report = run_project_doctor(
        target,
        runner=_runner(calls, execution_factory=execution_factory),
        env=environment,
        user_profile=str(tmp_path),
    )

    assert report.successful is True
    assert len(calls) == 2
    assert all(argv[1:] == ("--version",) for argv, _, _, _ in calls)
    assert all(cwd is None for _, _, _, cwd in calls)

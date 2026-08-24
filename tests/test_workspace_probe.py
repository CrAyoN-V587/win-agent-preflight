from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from win_agent_preflight import cli
from win_agent_preflight.models import CheckResult, CheckStatus
from win_agent_preflight.workspace_probe import (
    PROBE_CONTENT_PREFIX,
    WORKSPACE_PROBE_CHECK_IDS,
    WORKSPACE_PROBE_KIND,
    WORKSPACE_PROBE_SCHEMA_VERSION,
    WORKSPACE_PROBE_TOOL,
    WorkspaceOperations,
    WorkspaceProbeInputError,
    WorkspaceProbeInterrupted,
    WorkspaceProbeReport,
    WorkspaceProbeUnexpectedError,
    run_workspace_probe,
)


def _run(tmp_path: Path, operations: WorkspaceOperations | None = None):
    return run_workspace_probe(
        tmp_path,
        allow_write=True,
        operations=operations,
        token_factory=lambda: "fixture",
        user_profile=r"C:\Users\alice",
    )


class FailingOperations(WorkspaceOperations):
    def __init__(self, method: str, *, interrupt: bool = False, once: bool = False) -> None:
        self.method = method
        self.interrupt = interrupt
        self.once = once
        self.calls: list[str] = []

    def _maybe_fail(self, method: str) -> None:
        self.calls.append(method)
        if method != self.method:
            return
        if self.once:
            self.once = False
            raise OSError(f"{method} failed at C:\\Users\\alice\\private")
        if self.method == "unlink":
            return
        if self.interrupt:
            raise KeyboardInterrupt
        raise OSError(f"{method} failed at C:\\Users\\alice\\private")

    def mkdir(self, path: Path) -> None:
        self._maybe_fail("mkdir")
        super().mkdir(path)

    def write_text_exclusive(self, path: Path, text: str) -> None:
        self._maybe_fail("write_text_exclusive")
        super().write_text_exclusive(path, text)

    def read_text(self, path: Path) -> str:
        self._maybe_fail("read_text")
        return super().read_text(path)

    def rename(self, source: Path, destination: Path) -> None:
        self._maybe_fail("rename")
        super().rename(source, destination)

    def unlink(self, path: Path) -> None:
        self._maybe_fail("unlink")
        super().unlink(path)


def test_success_has_independent_v1_schema_and_no_residue(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report.schema_version == WORKSPACE_PROBE_SCHEMA_VERSION
    assert report.tool == WORKSPACE_PROBE_TOOL
    assert report.kind == WORKSPACE_PROBE_KIND
    assert tuple(check.id for check in report.checks) == WORKSPACE_PROBE_CHECK_IDS
    assert all(check.status is CheckStatus.PASS for check in report.checks)
    assert list(tmp_path.iterdir()) == []
    payload = json.dumps(report.to_dict(), ensure_ascii=False)
    assert PROBE_CONTENT_PREFIX not in payload


def test_report_rejects_successful_state_that_conflicts_with_checks_or_residue() -> None:
    passing = _report(CheckStatus.PASS)
    with pytest.raises(ValueError):
        WorkspaceProbeReport(
            schema_version=passing.schema_version,
            tool=passing.tool,
            kind=passing.kind,
            target=passing.target,
            successful=False,
            checks=passing.checks,
            residual_paths=(),
        )
    failing = _report(CheckStatus.FAIL)
    with pytest.raises(ValueError):
        WorkspaceProbeReport(
            schema_version=failing.schema_version,
            tool=failing.tool,
            kind=failing.kind,
            target=failing.target,
            successful=True,
            checks=failing.checks,
            residual_paths=(),
        )


def test_report_rejects_absolute_residual_path() -> None:
    passing = _report(CheckStatus.PASS)
    with pytest.raises(ValueError):
        WorkspaceProbeReport(
            schema_version=passing.schema_version,
            tool=passing.tool,
            kind=passing.kind,
            target=passing.target,
            successful=False,
            checks=passing.checks,
            residual_paths=(r"C:\outside",),
        )


def test_input_rejection_happens_before_any_write(tmp_path: Path, monkeypatch) -> None:
    operations = FailingOperations("mkdir")
    monkeypatch.setattr("win_agent_preflight.workspace_probe.os.name", "posix")
    with pytest.raises(WorkspaceProbeInputError):
        run_workspace_probe(tmp_path, allow_write=True, operations=operations)
    assert operations.calls == []


@pytest.mark.parametrize("target_kind", ["missing", "file", "reparse"])
def test_invalid_target_is_rejected_without_writes(
    tmp_path: Path, target_kind: str
) -> None:
    if target_kind == "missing":
        target = tmp_path / "does-not-exist"
    elif target_kind == "file":
        target = tmp_path / "file.txt"
        target.write_text("fixture", encoding="utf-8")
    else:
        target = tmp_path / "reparse-shaped"
        target.mkdir()

    class CountingOperations(WorkspaceOperations):
        def __init__(self) -> None:
            self.writes = 0

        def mkdir(self, path: Path) -> None:
            self.writes += 1
            super().mkdir(path)

        def write_text_exclusive(self, path: Path, text: str) -> None:
            self.writes += 1
            super().write_text_exclusive(path, text)

        def lstat(self, path: Path):
            value = super().lstat(path)
            if target_kind == "reparse" and path == target:
                return type("ReparseStat", (), {
                    "st_mode": stat.S_IFDIR,
                    "st_file_attributes": 0x400,
                    "st_reparse_tag": 1,
                })()
            return value

    operations = CountingOperations()
    with pytest.raises(WorkspaceProbeInputError):
        run_workspace_probe(target, allow_write=True, operations=operations)
    assert operations.writes == 0


def test_create_failure_makes_dependent_steps_unknown(tmp_path: Path) -> None:
    report = _run(tmp_path, FailingOperations("mkdir"))
    assert [check.status for check in report.checks] == [
        CheckStatus.FAIL,
        CheckStatus.UNKNOWN,
        CheckStatus.UNKNOWN,
        CheckStatus.UNKNOWN,
        CheckStatus.UNKNOWN,
        CheckStatus.PASS,
    ]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("method", "expected_index"),
    [("write_text_exclusive", 1), ("read_text", 2), ("rename", 3)],
)
def test_each_middle_failure_keeps_order_and_cleans(
    tmp_path: Path, method: str, expected_index: int
) -> None:
    report = _run(tmp_path, FailingOperations(method))
    assert report.checks[expected_index].status is CheckStatus.FAIL
    if expected_index == 1:
        assert all(
            check.status is CheckStatus.UNKNOWN
            for check in report.checks[expected_index + 1 : 5]
        )
    else:
        assert all(
            check.status is CheckStatus.PASS
            for check in report.checks[expected_index + 1 : 5]
        )
    assert report.checks[5].status is CheckStatus.PASS
    assert list(tmp_path.iterdir()) == []


def test_delete_failure_is_retried_by_bounded_cleanup(tmp_path: Path) -> None:
    report = _run(tmp_path, FailingOperations("unlink", once=True))
    assert report.checks[4].status is CheckStatus.FAIL
    assert report.checks[5].status is CheckStatus.PASS
    assert list(tmp_path.iterdir()) == []


def test_preexisting_after_is_preserved_and_reported_as_residue(tmp_path: Path) -> None:
    class ExternalAfter(WorkspaceOperations):
        def rename(self, source: Path, destination: Path) -> None:
            destination.write_text("external", encoding="utf-8")
            raise FileExistsError("after appeared during rename")

    report = _run(tmp_path, ExternalAfter())
    assert report.checks[3].status is CheckStatus.FAIL
    assert report.checks[4].status is CheckStatus.PASS
    assert report.checks[5].status is CheckStatus.FAIL
    assert any(path.endswith("after.txt") for path in report.residual_paths)
    after = tmp_path / ".agent-preflight-probe-fixture" / "after.txt"
    assert after.read_text(encoding="utf-8") == "external"
    after.unlink()
    after.parent.rmdir()


def test_before_replaced_before_rename_is_not_deleted(tmp_path: Path) -> None:
    class ReplaceBefore(WorkspaceOperations):
        def read_text(self, path: Path) -> str:
            value = super().read_text(path)
            path.unlink()
            path.write_text("external-before", encoding="utf-8")
            return value

    report = _run(tmp_path, ReplaceBefore())
    assert report.checks[3].status is CheckStatus.FAIL
    assert report.checks[4].status is CheckStatus.FAIL
    assert any(path.endswith("before.txt") for path in report.residual_paths)
    before = tmp_path / ".agent-preflight-probe-fixture" / "before.txt"
    assert before.read_text(encoding="utf-8") == "external-before"
    before.unlink()
    before.parent.rmdir()


def test_rename_success_followed_by_after_replacement_is_not_deleted(
    tmp_path: Path,
) -> None:
    class ReplaceAfterAfterRename(WorkspaceOperations):
        def rename(self, source: Path, destination: Path) -> None:
            super().rename(source, destination)
            destination.unlink()
            destination.write_text("external-after", encoding="utf-8")

    report = _run(tmp_path, ReplaceAfterAfterRename())
    assert report.checks[3].status is CheckStatus.FAIL
    assert report.checks[4].status is CheckStatus.FAIL
    assert any(path.endswith("after.txt") for path in report.residual_paths)
    after = tmp_path / ".agent-preflight-probe-fixture" / "after.txt"
    assert after.read_text(encoding="utf-8") == "external-after"
    after.unlink()
    after.parent.rmdir()


def test_after_replaced_between_rename_and_delete_is_not_deleted(tmp_path: Path) -> None:
    class ReplaceBeforeDelete(WorkspaceOperations):
        def __init__(self) -> None:
            self.after_lstat_count = 0

        def lstat(self, path: Path):
            if path.name == "after.txt":
                self.after_lstat_count += 1
                if self.after_lstat_count == 3:
                    path.unlink()
                    path.write_text("external-before-delete", encoding="utf-8")
            return super().lstat(path)

    report = _run(tmp_path, ReplaceBeforeDelete())
    assert report.checks[3].status is CheckStatus.PASS
    assert report.checks[4].status is CheckStatus.FAIL
    assert any(path.endswith("after.txt") for path in report.residual_paths)
    after = tmp_path / ".agent-preflight-probe-fixture" / "after.txt"
    assert after.read_text(encoding="utf-8") == "external-before-delete"
    after.unlink()
    after.parent.rmdir()


def test_probe_directory_replacement_prevents_rmdir(tmp_path: Path) -> None:
    class ReplaceProbeDirectory(WorkspaceOperations):
        def unlink(self, path: Path) -> None:
            super().unlink(path)
            if path.name == "after.txt":
                directory = path.parent
                moved = directory.with_name("moved-probe")
                directory.rename(moved)
                directory.mkdir()

    report = _run(tmp_path, ReplaceProbeDirectory())
    assert report.checks[5].status is CheckStatus.FAIL
    assert report.residual_paths == (".agent-preflight-probe-fixture",)
    current = tmp_path / ".agent-preflight-probe-fixture"
    moved = tmp_path / "moved-probe"
    assert current.is_dir() and moved.is_dir()
    current.rmdir()
    moved.rmdir()


def test_unavailable_identity_is_handled_conservatively(tmp_path: Path) -> None:
    class NoIdentityProbeDirectory(WorkspaceOperations):
        def __init__(self) -> None:
            self.created = False

        def mkdir(self, path: Path) -> None:
            super().mkdir(path)
            self.created = True

        def lstat(self, path: Path):
            value = super().lstat(path)
            if self.created and path.name.startswith(".agent-preflight-probe-"):
                return type("NoIdentity", (), {
                    "st_mode": stat.S_IFDIR,
                    "st_dev": 0,
                    "st_ino": 0,
                    "st_file_attributes": 0,
                })()
            return value

    report = _run(tmp_path, NoIdentityProbeDirectory())
    assert report.successful is False
    assert report.checks[0].status is CheckStatus.FAIL
    assert report.checks[5].status is CheckStatus.FAIL
    assert report.residual_paths == (".agent-preflight-probe-fixture",)
    (tmp_path / ".agent-preflight-probe-fixture").rmdir()


def test_cleanup_does_not_traverse_unknown_content_and_reports_relative_residue(
    tmp_path: Path,
) -> None:
    class UnknownContent(WorkspaceOperations):
        def rmdir(self, path: Path) -> None:
            (path / "unknown.txt").write_text("do not remove", encoding="utf-8")
            raise OSError("directory is not empty")

    report = _run(tmp_path, UnknownContent())
    assert report.successful is False
    assert report.checks[5].status is CheckStatus.FAIL
    assert report.residual_paths == (".agent-preflight-probe-fixture",)
    assert "unknown.txt" not in json.dumps(report.to_dict())
    unknown = tmp_path / ".agent-preflight-probe-fixture" / "unknown.txt"
    assert unknown.exists()
    unknown.unlink()
    unknown.parent.rmdir()


def test_exception_evidence_is_redacted_and_bounded(tmp_path: Path) -> None:
    class PermissionFailure(WorkspaceOperations):
        def write_text_exclusive(self, path: Path, text: str) -> None:
            del path, text
            raise OSError("C:\\Users\\alice\\secret-" + "x" * 500)

    report = _run(tmp_path, PermissionFailure())
    evidence = report.checks[1].evidence
    assert any(item.startswith("exception_type: OSError") for item in evidence)
    joined = " ".join(evidence)
    assert r"C:\Users\alice" not in joined
    message = next(item for item in evidence if item.startswith("message:"))
    assert len(message) <= 250
    assert list(tmp_path.iterdir()) == []


def test_cleanup_unexpected_exception_keeps_report_on_raised_error(tmp_path: Path) -> None:
    class UnexpectedCleanup(WorkspaceOperations):
        def rmdir(self, path: Path) -> None:
            raise RuntimeError("cleanup implementation failure")

    with pytest.raises(WorkspaceProbeUnexpectedError) as raised:
        _run(tmp_path, UnexpectedCleanup())
    report = raised.value.report
    assert report.successful is False
    assert report.checks[5].status is CheckStatus.FAIL
    assert report.residual_paths == (".agent-preflight-probe-fixture",)
    assert (tmp_path / ".agent-preflight-probe-fixture").is_dir()
    (tmp_path / ".agent-preflight-probe-fixture").rmdir()


def test_content_mismatch_does_not_echo_content(tmp_path: Path) -> None:
    class Mismatch(WorkspaceOperations):
        def read_text(self, path: Path) -> str:
            del path
            return "secret-value-that-must-not-be-echoed"

    report = _run(tmp_path, Mismatch())
    assert report.checks[2].status is CheckStatus.FAIL
    assert "secret-value" not in json.dumps(report.to_dict())
    assert list(tmp_path.iterdir()) == []


def test_unexpected_exception_is_reraised_after_cleanup(tmp_path: Path) -> None:
    class Unexpected(WorkspaceOperations):
        def write_text_exclusive(self, path: Path, text: str) -> None:
            del path, text
            raise RuntimeError("injected programming failure")

    with pytest.raises(RuntimeError, match="injected programming failure"):
        _run(tmp_path, Unexpected())
    assert list(tmp_path.iterdir()) == []


def test_keyboard_interrupt_returns_partial_report_and_cleans(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceProbeInterrupted) as raised:
        _run(tmp_path, FailingOperations("write_text_exclusive", interrupt=True))
    report = raised.value.report
    assert report.checks[0].status is CheckStatus.PASS
    assert report.checks[1].status is CheckStatus.UNKNOWN
    assert report.checks[5].status is CheckStatus.PASS
    assert list(tmp_path.iterdir()) == []


def test_reparse_probe_directory_is_not_entered_or_removed(tmp_path: Path) -> None:
    class ReparseAfterCreate(WorkspaceOperations):
        def __init__(self) -> None:
            self.created = False
            self.removed = False

        def mkdir(self, path: Path) -> None:
            super().mkdir(path)
            self.created = True

        def lstat(self, path: Path):
            value = super().lstat(path)
            if self.created and path.name.startswith(".agent-preflight-probe-"):
                return type("ReparseStat", (), {
                    "st_mode": stat.S_IFDIR,
                    "st_file_attributes": 0x400,
                    "st_reparse_tag": 1,
                })()
            return value

        def unlink(self, path: Path) -> None:
            self.removed = True
            super().unlink(path)

    operations = ReparseAfterCreate()
    report = _run(tmp_path, operations)
    assert report.checks[0].status is CheckStatus.FAIL
    assert report.checks[5].status is CheckStatus.FAIL
    assert any(
        "residual: .agent-preflight-probe-fixture" in item
        for item in report.checks[5].evidence
    )
    assert operations.removed is False
    # The fixture intentionally leaves the reparse-shaped directory; the probe
    # is forbidden from entering it.  Remove only this test's known directory.
    (tmp_path / ".agent-preflight-probe-fixture").rmdir()


def _report(status: CheckStatus) -> WorkspaceProbeReport:
    return WorkspaceProbeReport(
        schema_version=1,
        tool="win-agent-preflight",
        kind="workspace_probe",
        target="target",
        successful=status is CheckStatus.PASS,
        checks=tuple(
            CheckResult(
                id=check_id,
                status=status if index == 0 else CheckStatus.PASS,
                summary="fixture",
                evidence=("fixture failure",) if status is CheckStatus.FAIL and index == 0 else (),
            )
            for index, check_id in enumerate(WORKSPACE_PROBE_CHECK_IDS)
        ),
        residual_paths=(),
    )


def test_cli_workspace_probe_exit_codes_and_json(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli,
        "run_workspace_probe",
        lambda target, allow_write: _report(CheckStatus.PASS),
    )
    ok = CliRunner().invoke(
        cli.app,
        ["workspace-probe", "--target", str(tmp_path), "--allow-write", "--json"],
    )
    assert ok.exit_code == 0
    assert json.loads(ok.stdout)["summary"]["fail"] == 0

    monkeypatch.setattr(
        cli,
        "run_workspace_probe",
        lambda target, allow_write: _report(CheckStatus.FAIL),
    )
    failed = CliRunner().invoke(
        cli.app,
        ["workspace-probe", "--target", str(tmp_path), "--allow-write", "--json"],
    )
    assert failed.exit_code == 1
    assert json.loads(failed.stdout)["summary"]["fail"] == 1

    rejected = CliRunner().invoke(cli.app, ["workspace-probe", "--target", str(tmp_path)])
    assert rejected.exit_code == 2

    partial = _report(CheckStatus.FAIL)
    monkeypatch.setattr(
        cli,
        "run_workspace_probe",
        lambda target, allow_write: (_ for _ in ()).throw(WorkspaceProbeInterrupted(partial)),
    )
    interrupted = CliRunner().invoke(
        cli.app,
        ["workspace-probe", "--target", str(tmp_path), "--allow-write", "--json"],
    )
    assert interrupted.exit_code == 130
    assert json.loads(interrupted.stdout)["successful"] is False


def test_cli_unexpected_cleanup_emits_failure_json(monkeypatch, tmp_path: Path) -> None:
    report = _report(CheckStatus.FAIL)
    error = WorkspaceProbeUnexpectedError(report, RuntimeError("cleanup failure"))
    monkeypatch.setattr(
        cli,
        "run_workspace_probe",
        lambda target, allow_write: (_ for _ in ()).throw(error),
    )
    result = CliRunner().invoke(
        cli.app,
        ["workspace-probe", "--target", str(tmp_path), "--allow-write", "--json"],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["successful"] is False

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from win_agent_preflight.models import CheckStatus
from win_agent_preflight.snapshot import (
    EnvironmentSnapshot,
    SnapshotInputError,
    SnapshotVersionError,
    capture_snapshot,
    compare_snapshots,
    parse_snapshot,
    write_snapshot,
)


def _snapshot(*, label: str = "host", path: tuple[str, ...] = ()) -> EnvironmentSnapshot:
    return capture_snapshot(
        label,
        env={},
        user_profile=r"C:\Users\crayon",
        cwd=r"C:\Users\crayon\repo",
        executable=r"C:\Users\crayon\python.exe",
        platform="win32",
        captured_at="2026-08-24T00:00:00Z",
    ) if not path else EnvironmentSnapshot(
        schema_version=1,
        tool="win-agent-preflight",
        kind="environment_snapshot",
        label=label,
        captured_at="2026-08-24T00:00:00Z",
        cwd=r"C:\Users\crayon\repo",
        sys_executable=r"C:\Users\crayon\python.exe",
        platform="win32",
        path=path,
        pathext=(".CMD", ".EXE"),
        scan={
            "schema_version": 1,
            "tool": "win-agent-preflight",
            "summary": {"pass": 1},
            "checks": [
                {
                    "id": "command.git",
                    "status": CheckStatus.PASS.value,
                    "summary": "ok",
                    "evidence": ["selected: C:/Tools/git.exe"],
                    "details": {
                        "candidate_count": 1,
                        "candidates": [
                            {"name": "git", "path": "C:/Tools/git.exe", "source": "PATH"}
                        ],
                        "selected": "C:/Tools/git.exe",
                    },
                }
            ],
        },
    )


def test_snapshot_contains_only_selected_environment_facts() -> None:
    snapshot = capture_snapshot(
        "host",
        env={
            "PATH": r"C:\Users\crayon\bin;C:\Windows",
            "PATHEXT": ".EXE;.CMD",
            "SECRET_TOKEN": "must-not-appear",
            "USERPROFILE": r"C:\Users\crayon",
        },
        user_profile=r"C:\Users\crayon",
        cwd=r"C:\Users\crayon\repo",
        executable=r"C:\Users\crayon\python.exe",
        platform="win32",
        captured_at="fixed-time",
    )
    payload = snapshot.to_dict()
    assert payload["environment"]["path"] == [r"%USERPROFILE%\bin", r"C:\Windows"]
    assert "SECRET_TOKEN" not in str(payload)
    assert payload["scan"]["schema_version"] == 1


def test_snapshot_does_not_serialize_expanded_registry_path_values() -> None:
    private_value = r"C:\Users\alice\private-token-root"
    snapshot = capture_snapshot(
        "host",
        env={"PATH": r"C:\Windows", "PATHEXT": ".EXE", "USERPROFILE": r"C:\Users\alice"},
        user_profile=r"C:\Users\alice",
        registry_reader={
            "machine": {"Path": ""},
            "user": {"Path": r"%PRIVATE_ROOT%\bin", "PRIVATE_ROOT": private_value},
        },
        cwd=r"C:\Users\alice\repo",
        executable=r"C:\Users\alice\python.exe",
        platform="win32",
        captured_at="fixed-time",
    )
    serialized = json.dumps(snapshot.to_dict(), ensure_ascii=False)
    assert private_value not in serialized
    path_check = next(
        item for item in snapshot.scan["checks"] if item["id"] == "windows.path_refresh"
    )
    assert path_check["status"] == CheckStatus.WARNING.value
    assert any("%PRIVATE_ROOT%" in item for item in path_check["evidence"])


def test_parser_ignores_unknown_fields_but_rejects_higher_versions() -> None:
    payload = _snapshot().to_dict()
    payload["future_field"] = {"ignored": True}
    payload["scan"]["future_field"] = "ignored"
    parsed = parse_snapshot(payload)
    assert parsed.label == "host"

    higher = deepcopy(payload)
    higher["schema_version"] = 2
    with pytest.raises(SnapshotVersionError):
        parse_snapshot(higher)

    higher_scan = deepcopy(payload)
    higher_scan["scan"]["schema_version"] = 2
    with pytest.raises(SnapshotVersionError):
        parse_snapshot(higher_scan)


def test_parser_rejects_wrong_known_field_types() -> None:
    payload = _snapshot().to_dict()
    payload["environment"]["path"] = r"C:\Windows"
    with pytest.raises(SnapshotInputError):
        parse_snapshot(payload)


def test_compare_ignores_label_time_summary_and_candidate_count() -> None:
    baseline = _snapshot(label="host", path=(r"C:\Tools", r"C:\Windows"))
    current = _snapshot(label="agent", path=(r"c:/tools", r"c:/windows"))
    current_scan = deepcopy(current.scan)
    current_scan["summary"] = {"pass": 99, "warning": 2}
    current_scan["checks"][0]["summary"] = "different wording"
    current_scan["checks"][0]["details"]["candidate_count"] = 42
    current_scan["checks"][0]["evidence"] = ["selected: C:/Tools/git.exe \r\n"]
    current = EnvironmentSnapshot(
        schema_version=current.schema_version,
        tool=current.tool,
        kind=current.kind,
        label=current.label,
        captured_at="later",
        cwd=current.cwd,
        sys_executable=current.sys_executable,
        platform=current.platform,
        path=current.path,
        pathext=current.pathext,
        scan=current_scan,
    )
    assert compare_snapshots(baseline, current).equivalent


def test_order_changes_are_substantive_but_later_duplicates_are_ignored() -> None:
    baseline = _snapshot(path=(r"C:\Tools", r"C:\Windows"))
    reordered_path = replace(baseline, path=(r"C:\Windows", r"C:\Tools"))
    path_comparison = compare_snapshots(baseline, reordered_path)
    assert [item.field for item in path_comparison.differences] == ["environment.path"]

    reordered_extensions = replace(baseline, pathext=(".EXE", ".CMD"))
    extension_comparison = compare_snapshots(baseline, reordered_extensions)
    assert [item.field for item in extension_comparison.differences] == ["environment.pathext"]

    baseline_scan = deepcopy(baseline.scan)
    candidates = baseline_scan["checks"][0]["details"]["candidates"]
    candidates.append(deepcopy(candidates[0]))
    candidates.append({"name": "git", "path": r"C:\Other\git.exe", "source": "PATH"})
    with_duplicates = replace(baseline, scan=baseline_scan)
    reordered_scan = deepcopy(baseline_scan)
    reordered_scan["checks"][0]["details"]["candidates"] = [
        candidates[-1],
        candidates[0],
        candidates[1],
    ]
    reordered_candidates = replace(baseline, scan=reordered_scan)
    candidate_comparison = compare_snapshots(with_duplicates, reordered_candidates)
    assert candidate_comparison.equivalent is False
    assert candidate_comparison.differences[0].field == "scan.checks[command.git]"


def test_evidence_only_normalizes_line_endings_and_trailing_whitespace() -> None:
    baseline = _snapshot(path=(r"C:\Tools",))
    base_scan = deepcopy(baseline.scan)
    base_scan["checks"][0]["evidence"] = ["Version: 1.0\nline with slash http://example/a/b "]
    baseline = replace(baseline, scan=base_scan)

    equivalent_scan = deepcopy(base_scan)
    equivalent_scan["checks"][0]["evidence"] = [
        "Version: 1.0\r\nline with slash http://example/a/b\t"
    ]
    equivalent = replace(baseline, scan=equivalent_scan)
    assert compare_snapshots(baseline, equivalent).equivalent

    case_changed_scan = deepcopy(base_scan)
    case_changed_scan["checks"][0]["evidence"] = [
        "version: 1.0\nline with slash http://example/a/b"
    ]
    assert (
        compare_snapshots(baseline, replace(baseline, scan=case_changed_scan)).equivalent is False
    )

    slash_changed_scan = deepcopy(base_scan)
    slash_changed_scan["checks"][0]["evidence"] = [
        "Version: 1.0\nline with slash http:\\example\\a\\b"
    ]
    assert (
        compare_snapshots(baseline, replace(baseline, scan=slash_changed_scan)).equivalent is False
    )


def test_compare_reports_substantive_difference() -> None:
    baseline = _snapshot(path=(r"C:\Tools",))
    current = _snapshot(path=(r"C:\Other",))
    comparison = compare_snapshots(baseline, current)
    assert comparison.equivalent is False
    assert comparison.differences[0].field == "environment.path"


def test_write_snapshot_creates_parent_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "host.json"
    snapshot = _snapshot()
    write_snapshot(snapshot, output, pretty=True)
    assert output.exists()
    with pytest.raises(ValueError, match="already exists"):
        write_snapshot(snapshot, output)
    original = output.read_text(encoding="utf-8")
    assert original
    write_snapshot(snapshot, output, pretty=True, force=True)
    assert output.read_text(encoding="utf-8") == original


def test_failed_atomic_replace_keeps_existing_file_and_cleans_temp(
    monkeypatch, tmp_path: Path
) -> None:
    output = tmp_path / "snapshot.json"
    output.write_text("original\n", encoding="utf-8")

    def fail_replace(source, destination):
        del source, destination
        raise OSError("simulated replace failure")

    monkeypatch.setattr("win_agent_preflight.snapshot.os.replace", fail_replace)
    with pytest.raises(ValueError, match="cannot write snapshot"):
        write_snapshot(_snapshot(), output, force=True)
    assert output.read_text(encoding="utf-8") == "original\n"
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []

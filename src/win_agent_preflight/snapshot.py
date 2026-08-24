"""Environment snapshot v1 and deterministic snapshot comparison."""

from __future__ import annotations

import json
import ntpath
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .checks import scan_environment
from .models import CheckStatus
from .runner import Runner
from .windows import RegistryValueReader, redact_text

SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_TOOL = "win-agent-preflight"
SNAPSHOT_KIND = "environment_snapshot"


class SnapshotError(ValueError):
    """A user-visible snapshot input or output error."""


class SnapshotInputError(SnapshotError):
    """Snapshot JSON is malformed or has an unsupported shape."""


class SnapshotVersionError(SnapshotInputError):
    """Snapshot or embedded scan uses a schema version we cannot read."""


@dataclass(frozen=True, slots=True)
class EnvironmentSnapshot:
    """Portable v1 facts plus the scan performed in the same environment."""

    schema_version: int
    tool: str
    kind: str
    label: str
    captured_at: str
    cwd: str
    sys_executable: str
    platform: str
    path: tuple[str, ...]
    pathext: tuple[str, ...]
    scan: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "kind": self.kind,
            "label": self.label,
            "captured_at": self.captured_at,
            "environment": {
                "cwd": self.cwd,
                "sys_executable": self.sys_executable,
                "platform": self.platform,
                "path": list(self.path),
                "pathext": list(self.pathext),
            },
            "scan": _copy_json(self.scan),
        }


@dataclass(frozen=True, slots=True)
class SnapshotDifference:
    field: str
    baseline: Any
    current: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "baseline": _copy_json(self.baseline),
            "current": _copy_json(self.current),
        }


@dataclass(frozen=True, slots=True)
class SnapshotComparison:
    differences: tuple[SnapshotDifference, ...]

    @property
    def equivalent(self) -> bool:
        return not self.differences

    def to_dict(self) -> dict[str, Any]:
        return {
            "equivalent": self.equivalent,
            "differences": [difference.to_dict() for difference in self.differences],
        }


def capture_snapshot(
    label: str,
    *,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    user_path: str | None = None,
    registry_reader: RegistryValueReader | Mapping[str, object] | None = None,
    timeout: float = 5.0,
    cwd: str | None = None,
    executable: str | None = None,
    platform: str | None = None,
    captured_at: str | None = None,
) -> EnvironmentSnapshot:
    """Capture a deliberately small, redacted environment snapshot."""

    if not isinstance(label, str) or not label.strip():
        raise SnapshotInputError("label must be a non-empty string")
    environment = env if env is not None else os.environ
    profile = user_profile or environment.get("USERPROFILE") or os.environ.get("USERPROFILE")
    scan = scan_environment(
        runner=runner,
        env=environment,
        user_profile=profile,
        user_path=user_path,
        registry_reader=registry_reader,
        timeout=timeout,
    )
    return EnvironmentSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        tool=SNAPSHOT_TOOL,
        kind=SNAPSHOT_KIND,
        label=label,
        captured_at=captured_at or _now_utc(),
        cwd=redact_text(cwd if cwd is not None else os.getcwd(), user_profile=profile),
        sys_executable=redact_text(
            executable if executable is not None else sys.executable,
            user_profile=profile,
        ),
        platform=platform if platform is not None else sys.platform,
        path=_split_environment_set(environment.get("PATH", ""), profile),
        pathext=_split_environment_set(environment.get("PATHEXT", ""), profile),
        scan=scan.to_dict(),
    )


def write_snapshot(
    snapshot: EnvironmentSnapshot,
    output: Path,
    *,
    pretty: bool = False,
    force: bool = False,
) -> None:
    """Create parent directories and write once unless ``force`` is set."""

    if output.exists() and not force:
        raise SnapshotError(f"output already exists; pass --force to replace: {output}")
    if output.exists() and output.is_dir():
        raise SnapshotError(f"output is a directory: {output}")
    temporary: Path | None = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(
            snapshot.to_dict(),
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temporary, output)
            temporary = None
        else:
            # A hard link can only be created when the destination does not
            # exist, so this preserves no-overwrite semantics even if another
            # process creates the destination after the initial existence check.
            os.link(temporary, output)
            temporary.unlink()
            temporary = None
    except FileExistsError as exc:
        raise SnapshotError(f"output already exists; pass --force to replace: {output}") from exc
    except OSError as exc:
        raise SnapshotError(f"cannot write snapshot: {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def load_snapshot(path: Path) -> EnvironmentSnapshot:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SnapshotError(f"snapshot file not found: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"cannot read snapshot JSON: {path}: {exc}") from exc
    return parse_snapshot(payload)


def parse_snapshot(payload: Any) -> EnvironmentSnapshot:
    """Parse only known v1 fields and ignore unknown fields."""

    root = _mapping(payload, "snapshot")
    version = _version(root.get("schema_version"), "snapshot")
    if version != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotVersionError(f"unsupported snapshot schema_version: {version}")
    _exact_string(root, "tool", SNAPSHOT_TOOL, "snapshot")
    _exact_string(root, "kind", SNAPSHOT_KIND, "snapshot")
    label = _string(root.get("label"), "snapshot.label")
    captured_at = _string(root.get("captured_at"), "snapshot.captured_at")
    environment = _mapping(root.get("environment"), "snapshot.environment")
    cwd = _string(environment.get("cwd"), "snapshot.environment.cwd")
    executable = _string(
        environment.get("sys_executable"), "snapshot.environment.sys_executable"
    )
    platform = _string(environment.get("platform"), "snapshot.environment.platform")
    path = _string_list(environment.get("path"), "snapshot.environment.path")
    pathext = _string_list(environment.get("pathext"), "snapshot.environment.pathext")
    scan = _parse_scan(root.get("scan"))
    return EnvironmentSnapshot(
        schema_version=version,
        tool=SNAPSHOT_TOOL,
        kind=SNAPSHOT_KIND,
        label=label,
        captured_at=captured_at,
        cwd=cwd,
        sys_executable=executable,
        platform=platform,
        path=tuple(path),
        pathext=tuple(pathext),
        scan=scan,
    )


def compare_snapshots(
    baseline: EnvironmentSnapshot,
    current: EnvironmentSnapshot,
) -> SnapshotComparison:
    """Compare stable facts while excluding labels, time and volatile summaries."""

    left = _canonical_environment(baseline)
    right = _canonical_environment(current)
    differences: list[SnapshotDifference] = []
    for field in ("cwd", "sys_executable", "platform", "path", "pathext"):
        if left[field] != right[field]:
            differences.append(
                SnapshotDifference(
                    field=f"environment.{field}",
                    baseline=left[field],
                    current=right[field],
                )
            )

    left_checks = _canonical_checks(baseline.scan)
    right_checks = _canonical_checks(current.scan)
    for check_id in sorted(set(left_checks) | set(right_checks)):
        if left_checks.get(check_id) != right_checks.get(check_id):
            differences.append(
                SnapshotDifference(
                    field=f"scan.checks[{check_id}]",
                    baseline=left_checks.get(check_id),
                    current=right_checks.get(check_id),
                )
            )
    return SnapshotComparison(tuple(differences))


def _canonical_environment(snapshot: EnvironmentSnapshot) -> dict[str, Any]:
    return {
        "cwd": _normalize_windows_path(snapshot.cwd),
        "sys_executable": _normalize_windows_path(snapshot.sys_executable),
        "platform": snapshot.platform.casefold(),
        "path": _normalize_path_set(snapshot.path),
        "pathext": _normalize_extension_set(snapshot.pathext),
    }


def _canonical_checks(scan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    checks = scan.get("checks", [])
    result: dict[str, dict[str, Any]] = {}
    for check in checks:
        check_id = check["id"]
        details = check.get("details", {})
        canonical_details: dict[str, Any] = {}
        if "candidates" in details:
            candidates: list[list[str]] = []
            seen_candidates: set[tuple[str, str, str]] = set()
            for candidate in details["candidates"]:
                normalized = (
                    str(candidate["name"]).casefold(),
                    _normalize_windows_path(candidate["path"]),
                    str(candidate["source"]).casefold(),
                )
                if normalized not in seen_candidates:
                    seen_candidates.add(normalized)
                    candidates.append(list(normalized))
            canonical_details["candidates"] = candidates
        for key in ("selected", "shell"):
            if key in details:
                canonical_details[key] = _normalize_windows_path(details[key])
        if "command" in details:
            canonical_details["command"] = str(details["command"]).casefold()
        if "missing_count" in details:
            canonical_details["missing_count"] = details["missing_count"]
        result[check_id] = {
            "status": check["status"],
            "evidence": _normalize_evidence_sequence(check.get("evidence", [])),
            "details": canonical_details,
        }
    return result


def _parse_scan(value: Any) -> dict[str, Any]:
    scan = _mapping(value, "snapshot.scan")
    version = _version(scan.get("schema_version"), "snapshot.scan")
    if version != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotVersionError(f"unsupported embedded scan schema_version: {version}")
    _exact_string(scan, "tool", SNAPSHOT_TOOL, "snapshot.scan")
    if "summary" in scan and not isinstance(scan["summary"], dict):
        raise SnapshotInputError("snapshot.scan.summary must be an object")
    checks = scan.get("checks")
    if not isinstance(checks, list):
        raise SnapshotInputError("snapshot.scan.checks must be an array")
    parsed_checks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_check in enumerate(checks):
        check = _mapping(raw_check, f"snapshot.scan.checks[{index}]")
        check_id = _string(check.get("id"), f"snapshot.scan.checks[{index}].id")
        if check_id in seen:
            raise SnapshotInputError(f"duplicate check id: {check_id}")
        seen.add(check_id)
        status = _string(check.get("status"), f"snapshot.scan.checks[{index}].status")
        if status not in {item.value for item in CheckStatus}:
            raise SnapshotInputError(f"invalid check status: {status}")
        summary = _string(check.get("summary"), f"snapshot.scan.checks[{index}].summary")
        evidence = _string_list(
            check.get("evidence"), f"snapshot.scan.checks[{index}].evidence"
        )
        details = check.get("details", {})
        details_mapping = _mapping(details, f"snapshot.scan.checks[{index}].details")
        parsed_details: dict[str, Any] = {}
        if "candidates" in details_mapping:
            candidates = details_mapping["candidates"]
            if not isinstance(candidates, list):
                raise SnapshotInputError("check.details.candidates must be an array")
            parsed_candidates: list[dict[str, str]] = []
            for candidate_index, raw_candidate in enumerate(candidates):
                candidate = _mapping(
                    raw_candidate,
                    f"snapshot.scan.checks[{index}].details.candidates[{candidate_index}]",
                )
                parsed_candidates.append(
                    {
                        "name": _string(candidate.get("name"), "candidate.name"),
                        "path": _string(candidate.get("path"), "candidate.path"),
                        "source": _string(candidate.get("source"), "candidate.source"),
                    }
                )
            parsed_details["candidates"] = parsed_candidates
        for key in ("selected", "shell", "command"):
            if key in details_mapping:
                parsed_details[key] = _string(details_mapping[key], f"check.details.{key}")
        if "missing_count" in details_mapping:
            missing_count = details_mapping["missing_count"]
            if not isinstance(missing_count, int) or isinstance(missing_count, bool):
                raise SnapshotInputError("check.details.missing_count must be an integer")
            parsed_details["missing_count"] = missing_count
        parsed_checks.append(
            {
                "id": check_id,
                "status": status,
                "summary": summary,
                "evidence": evidence,
                "details": parsed_details,
            }
        )
    return {
        "schema_version": version,
        "tool": SNAPSHOT_TOOL,
        "summary": _copy_json(scan.get("summary", {})),
        "checks": parsed_checks,
    }


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotInputError(f"{field} must be an object")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise SnapshotInputError(f"{field} must be a string")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SnapshotInputError(f"{field} must be an array")
    return [_string(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _version(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SnapshotInputError(f"{field}.schema_version must be an integer")
    return value


def _exact_string(mapping: Mapping[str, Any], key: str, expected: str, field: str) -> None:
    value = _string(mapping.get(key), f"{field}.{key}")
    if value != expected:
        raise SnapshotInputError(f"{field}.{key} must be {expected!r}")


def _split_environment_set(value: str, user_profile: str | None) -> tuple[str, ...]:
    separator = ";" if os.name == "nt" else os.pathsep
    values: list[str] = []
    seen: set[str] = set()
    for item in value.split(separator):
        cleaned = item.strip().strip('"')
        if not cleaned:
            continue
        redacted = redact_text(cleaned, user_profile=user_profile)
        key = redacted.casefold()
        if key not in seen:
            seen.add(key)
            values.append(redacted)
    return tuple(values)


def _normalize_windows_path(value: str) -> str:
    path = str(value).replace("/", "\\")
    if not path:
        return path
    normalized = ntpath.normpath(path)
    if normalized == "." and path != ".":
        normalized = path
    return normalized.casefold()


def _normalize_path_set(values: Sequence[str]) -> list[str]:
    return _ordered_unique(_normalize_windows_path(value) for value in values if value)


def _normalize_extension_set(values: Sequence[str]) -> list[str]:
    return _ordered_unique(str(value).strip().casefold() for value in values if value.strip())


def _normalize_evidence(value: str) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip(" \t") for line in text.split("\n")).rstrip(" \t\n")


def _normalize_evidence_sequence(values: Sequence[str]) -> list[str]:
    return _ordered_unique(sorted(_normalize_evidence(value) for value in values))


def _ordered_unique(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    return value


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

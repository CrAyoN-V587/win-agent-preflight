"""Infer a small project toolchain from first-level marker files."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .checks import check_command
from .models import CheckResult, CheckStatus
from .runner import Runner
from .windows import discover_command, redact_text

PROJECT_DOCTOR_SCHEMA_VERSION = 1
PROJECT_DOCTOR_TOOL = "win-agent-preflight"
PROJECT_DOCTOR_KIND = "project_doctor"
PROJECT_TOOL_ORDER = ("python", "node", "npm", "pnpm", "cmake")

# This is deliberately a fixed, small list.  Project Doctor never enumerates
# a directory, glob-matches it, or opens a marker file.
PROJECT_MARKER_BASENAMES = (
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "CMakeLists.txt",
)
PYTHON_MARKERS = frozenset({"pyproject.toml", "requirements.txt"})
NPM_LOCK_MARKERS = ("package-lock.json", "npm-shrinkwrap.json")
NPM_LOCK_MARKER_SET = frozenset(NPM_LOCK_MARKERS)
PNPM_LOCK_MARKER = "pnpm-lock.yaml"
UNSUPPORTED_PACKAGE_LOCK_MARKERS = frozenset({"yarn.lock", "bun.lock", "bun.lockb"})
_REPARSE_POINT = 0x400
_MAX_ERROR_TEXT = 240


class ProjectDoctorInputError(ValueError):
    """The target or platform cannot be accepted for a read-only diagnosis."""


class ProjectMarkerStatus(StrEnum):
    CLEAR = "clear"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProjectDoctorReport:
    """Independent v1 report for one first-level project inspection."""

    schema_version: int
    tool: str
    kind: str
    target: str
    markers: tuple[str, ...]
    marker_status: ProjectMarkerStatus
    unknown_reasons: tuple[str, ...]
    required_tools: tuple[str, ...]
    checks: tuple[CheckResult, ...]

    def __post_init__(self) -> None:
        if self.schema_version != PROJECT_DOCTOR_SCHEMA_VERSION:
            raise ValueError("unsupported project doctor schema version")
        if self.tool != PROJECT_DOCTOR_TOOL or self.kind != PROJECT_DOCTOR_KIND:
            raise ValueError("invalid project doctor identity")
        if any(marker not in PROJECT_MARKER_BASENAMES for marker in self.markers):
            raise ValueError("project doctor markers must use the fixed marker list")
        if tuple(
            marker for marker in PROJECT_MARKER_BASENAMES if marker in self.markers
        ) != self.markers:
            raise ValueError("project doctor markers must be in fixed order")
        if tuple(
            tool for tool in PROJECT_TOOL_ORDER if tool in self.required_tools
        ) != self.required_tools:
            raise ValueError("project doctor tools must be unique and ordered")
        expected_ids = ("project.markers",) + tuple(
            f"project.{tool}" for tool in self.required_tools
        )
        if tuple(check.id for check in self.checks) != expected_ids:
            raise ValueError("project doctor checks must match required tools")
        if self.marker_status is ProjectMarkerStatus.UNKNOWN and not self.unknown_reasons:
            raise ValueError("unknown project markers require a reason")
        if self.marker_status is ProjectMarkerStatus.CLEAR and self.unknown_reasons:
            raise ValueError("clear project markers cannot have unknown reasons")
        marker_check = self.checks[0]
        expected_marker_status = (
            CheckStatus.PASS
            if self.marker_status is ProjectMarkerStatus.CLEAR
            else CheckStatus.UNKNOWN
        )
        if marker_check.status is not expected_marker_status:
            raise ValueError("project marker check status conflicts with marker_status")
        if self.marker_status is ProjectMarkerStatus.CLEAR and not self.required_tools:
            raise ValueError("clear project markers must derive at least one tool")

    @property
    def successful(self) -> bool:
        return bool(self.required_tools) and all(
            check.status is CheckStatus.PASS for check in self.checks
        )

    def to_dict(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in CheckStatus}
        for check in self.checks:
            counts[check.status.value] += 1
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "tool": self.tool,
            "offline": True,
            "target": self.target,
            "markers": list(self.markers),
            "marker_status": self.marker_status.value,
            "unknown_reasons": list(self.unknown_reasons),
            "required_tools": list(self.required_tools),
            "successful": self.successful,
            "summary": counts,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True, slots=True)
class _MarkerScan:
    present: tuple[str, ...]
    unknown_reasons: tuple[str, ...] = ()


def run_project_doctor(
    target: Path | str,
    *,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> ProjectDoctorReport:
    """Inspect fixed first-level markers and probe only derived tools."""

    if os.name != "nt":
        raise ProjectDoctorInputError("project-doctor is supported on Windows only")
    if timeout <= 0:
        raise ProjectDoctorInputError("timeout must be positive")

    environment = env if env is not None else os.environ
    active_profile = user_profile or environment.get("USERPROFILE") or os.environ.get(
        "USERPROFILE"
    )
    target_path = _validate_target(Path(target), user_profile=active_profile)
    marker_scan = _scan_markers(target_path, user_profile=active_profile)
    required_tools, marker_status, derived_reasons = _derive_tools(marker_scan.present)
    unknown_reasons = tuple(
        dict.fromkeys((*marker_scan.unknown_reasons, *derived_reasons))
    )
    if unknown_reasons:
        marker_status = ProjectMarkerStatus.UNKNOWN
    active_runner = runner or Runner(default_timeout=timeout)
    marker_check = _marker_check(
        marker_status,
        marker_scan.present,
        unknown_reasons,
    )
    checks = (marker_check,) + tuple(
        _check_tool(
            name,
            active_runner,
            markers=marker_scan.present,
            env=environment,
            user_profile=active_profile,
            timeout=timeout,
        )
        for name in required_tools
    )
    return ProjectDoctorReport(
        schema_version=PROJECT_DOCTOR_SCHEMA_VERSION,
        tool=PROJECT_DOCTOR_TOOL,
        kind=PROJECT_DOCTOR_KIND,
        target=redact_text(str(target_path), user_profile=active_profile),
        markers=marker_scan.present,
        marker_status=marker_status,
        unknown_reasons=unknown_reasons,
        required_tools=required_tools,
        checks=checks,
    )


def _check_tool(
    name: str,
    runner: Runner,
    *,
    markers: tuple[str, ...],
    env: Mapping[str, str],
    user_profile: str | None,
    timeout: float,
) -> CheckResult:
    candidates = discover_command(name, env=env, user_profile=user_profile)
    result = check_command(
        name,
        candidates,
        runner,
        required=True,
        env=env,
        user_profile=user_profile,
        timeout=timeout,
    )
    return CheckResult(
        id=f"project.{name}",
        status=result.status,
        summary=result.summary,
        evidence=result.evidence,
        details={
            "tool": name,
            "required": True,
            "required_by": list(_required_by(name, markers)),
            **result.details,
        },
    )


def _marker_check(
    status: ProjectMarkerStatus,
    markers: tuple[str, ...],
    unknown_reasons: tuple[str, ...],
) -> CheckResult:
    if status is ProjectMarkerStatus.CLEAR:
        return CheckResult(
            id="project.markers",
            status=CheckStatus.PASS,
            summary="项目标记明确",
            evidence=("fixed first-level project markers are clear",),
            details={"markers": list(markers), "marker_status": status.value},
        )
    return CheckResult(
        id="project.markers",
        status=CheckStatus.UNKNOWN,
        summary="项目标记无法明确",
        evidence=unknown_reasons or ("project markers are not sufficient",),
        details={
            "markers": list(markers),
            "marker_status": status.value,
            "unknown_reasons": list(unknown_reasons),
        },
    )


def _required_by(name: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    present = set(markers)
    if name == "python":
        return tuple(
            marker
            for marker in PROJECT_MARKER_BASENAMES
            if marker in present & PYTHON_MARKERS
        )
    if name == "node":
        return ("package.json",) if "package.json" in present else ()
    if name == "npm":
        return tuple(marker for marker in NPM_LOCK_MARKERS if marker in present)
    if name == "pnpm":
        return (PNPM_LOCK_MARKER,) if PNPM_LOCK_MARKER in present else ()
    if name == "cmake":
        return ("CMakeLists.txt",) if "CMakeLists.txt" in present else ()
    return ()


def _validate_target(target: Path, *, user_profile: str | None) -> Path:
    try:
        target_info = target.lstat()
    except OSError as exc:
        raise ProjectDoctorInputError(
            "target cannot be resolved or inspected: "
            + _redacted_exception(exc, user_profile=user_profile)
        ) from exc
    if _is_reparse(target_info) or stat.S_ISLNK(target_info.st_mode):
        raise ProjectDoctorInputError("target is a symlink or reparse point")
    if not stat.S_ISDIR(target_info.st_mode):
        raise ProjectDoctorInputError("target must be an existing ordinary directory")
    try:
        resolved = target.resolve(strict=True)
        resolved_info = resolved.lstat()
    except OSError as exc:
        raise ProjectDoctorInputError(
            "target cannot be resolved or inspected: "
            + _redacted_exception(exc, user_profile=user_profile)
        ) from exc
    if _is_reparse(resolved_info) or stat.S_ISLNK(resolved_info.st_mode):
        raise ProjectDoctorInputError("target is a symlink or reparse point")
    if not stat.S_ISDIR(resolved_info.st_mode):
        raise ProjectDoctorInputError("target must be an existing ordinary directory")
    return resolved


def _scan_markers(target: Path, *, user_profile: str | None) -> _MarkerScan:
    present: list[str] = []
    unknown_reasons: list[str] = []
    for basename in PROJECT_MARKER_BASENAMES:
        marker = target / basename
        try:
            info = marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            unknown_reasons.append(
                f"marker cannot be inspected: {basename}: "
                + _redacted_exception(exc, user_profile=user_profile)
            )
            continue
        if _is_reparse(info) or stat.S_ISLNK(info.st_mode):
            unknown_reasons.append(f"marker is a symlink or reparse point: {basename}")
            continue
        if not stat.S_ISREG(info.st_mode):
            unknown_reasons.append(f"marker must be an ordinary file: {basename}")
            continue
        present.append(basename)
    return _MarkerScan(
        present=tuple(present),
        unknown_reasons=tuple(unknown_reasons),
    )


def _derive_tools(
    markers: tuple[str, ...],
) -> tuple[tuple[str, ...], ProjectMarkerStatus, tuple[str, ...]]:
    present = set(markers)
    required: set[str] = set()
    reasons: list[str] = []

    if present & PYTHON_MARKERS:
        required.add("python")

    has_package = "package.json" in present
    npm_locks = present & NPM_LOCK_MARKER_SET
    has_pnpm_lock = PNPM_LOCK_MARKER in present
    unsupported_locks = present & UNSUPPORTED_PACKAGE_LOCK_MARKERS

    if has_package:
        required.add("node")
        if npm_locks and has_pnpm_lock:
            reasons.append("npm and pnpm lockfiles conflict")
        elif npm_locks:
            required.add("npm")
        elif has_pnpm_lock:
            required.add("pnpm")
        if present & {"yarn.lock", "bun.lock", "bun.lockb"}:
            reasons.append("unsupported package-manager lockfile")
    elif npm_locks or has_pnpm_lock or unsupported_locks:
        reasons.append("orphan lockfile")

    if "CMakeLists.txt" in present:
        required.add("cmake")

    if not required:
        reasons.append("no supported project marker")

    deduplicated_reasons = tuple(dict.fromkeys(reasons))
    ordered_tools = tuple(tool for tool in PROJECT_TOOL_ORDER if tool in required)
    status = (
        ProjectMarkerStatus.UNKNOWN
        if deduplicated_reasons
        else ProjectMarkerStatus.CLEAR
    )
    return ordered_tools, status, deduplicated_reasons


def _is_reparse(value: os.stat_result | Any) -> bool:
    tag = int(getattr(value, "st_reparse_tag", 0) or 0)
    attributes = int(getattr(value, "st_file_attributes", 0) or 0)
    return bool(tag or attributes & _REPARSE_POINT)


def _redacted_exception(exc: BaseException, *, user_profile: str | None) -> str:
    text = redact_text(str(exc), user_profile=user_profile)
    return text[:_MAX_ERROR_TEXT]

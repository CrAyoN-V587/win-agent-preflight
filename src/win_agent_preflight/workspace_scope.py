"""Compare the bounded workspace probe in two explicitly named directories."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .models import CheckResult, CheckStatus
from .windows import redact_text
from .workspace_probe import (
    WorkspaceProbeInterrupted,
    WorkspaceProbeReport,
    WorkspaceProbeUnexpectedError,
    run_workspace_probe,
)

WORKSPACE_SCOPE_SCHEMA_VERSION = 1
WORKSPACE_SCOPE_TOOL = "win-agent-preflight"
WORKSPACE_SCOPE_KIND = "workspace_scope"
_REPARSE_POINT = 0x400


class WorkspaceScopeState(StrEnum):
    """Stable conclusion values for the two-directory comparison."""

    BOTH_USABLE = "both_usable"
    TARGET_SPECIFIC_FAILURE = "target_specific_failure"
    CONTROL_SPECIFIC_FAILURE = "control_specific_failure"
    BOTH_FAILED = "both_failed"
    INCONCLUSIVE = "inconclusive"


class WorkspaceScopeInputError(ValueError):
    """The scope directories or write authorization are invalid."""


class WorkspaceScopeInterrupted(KeyboardInterrupt):
    """A Ctrl-C carrying the partial two-directory report."""

    def __init__(self, report: WorkspaceScopeReport) -> None:
        self.report = report
        super().__init__("workspace scope interrupted")


class WorkspaceScopeUnexpectedError(RuntimeError):
    """An unexpected probe failure carrying its bounded partial report."""

    def __init__(self, report: WorkspaceScopeReport, cause: BaseException) -> None:
        self.report = report
        self.cause = cause
        # Do not stringify an injected exception: its message could contain a
        # path or process output that is outside the report's privacy boundary.
        super().__init__("workspace scope failed unexpectedly")


@dataclass(frozen=True, slots=True)
class WorkspaceScopeReport:
    """Independent v1 report containing two single-directory probe reports."""

    schema_version: int
    tool: str
    kind: str
    target: str
    control: str
    target_probe: WorkspaceProbeReport | None
    control_probe: WorkspaceProbeReport | None
    state: WorkspaceScopeState | str
    complete: bool

    def __post_init__(self) -> None:
        if self.schema_version != WORKSPACE_SCOPE_SCHEMA_VERSION:
            raise ValueError("unsupported workspace scope schema version")
        if self.tool != WORKSPACE_SCOPE_TOOL or self.kind != WORKSPACE_SCOPE_KIND:
            raise ValueError("invalid workspace scope identity")
        try:
            state = WorkspaceScopeState(self.state)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid workspace scope state") from exc
        object.__setattr__(self, "state", state)
        if not isinstance(self.complete, bool):
            raise ValueError("workspace scope complete must be a boolean")
        if not isinstance(self.target, str) or not isinstance(self.control, str):
            raise ValueError("workspace scope paths must be strings")
        if self.target_probe is not None and not isinstance(
            self.target_probe, WorkspaceProbeReport
        ):
            raise ValueError("workspace scope target_probe must be a WorkspaceProbeReport")
        if self.control_probe is not None and not isinstance(
            self.control_probe, WorkspaceProbeReport
        ):
            raise ValueError("workspace scope control_probe must be a WorkspaceProbeReport")
        if state is WorkspaceScopeState.INCONCLUSIVE:
            if self.complete:
                if self.target_probe is None or self.control_probe is None:
                    raise ValueError(
                        "complete inconclusive scope requires both probe reports"
                    )
                if not (
                    _probe_outcome(self.target_probe) is _ProbeOutcome.UNKNOWN
                    or _probe_outcome(self.control_probe) is _ProbeOutcome.UNKNOWN
                ):
                    raise ValueError(
                        "complete inconclusive scope requires an unknown probe"
                    )
            return
        if (
            not self.complete
            or not isinstance(self.target_probe, WorkspaceProbeReport)
            or not isinstance(self.control_probe, WorkspaceProbeReport)
        ):
            raise ValueError("complete scope states require both probe reports")
        target_outcome = _probe_outcome(self.target_probe)
        control_outcome = _probe_outcome(self.control_probe)
        if (
            target_outcome is _ProbeOutcome.UNKNOWN
            or control_outcome is _ProbeOutcome.UNKNOWN
        ):
            raise ValueError("unknown probe outcomes require inconclusive state")
        expected = {
            (_ProbeOutcome.USABLE, _ProbeOutcome.USABLE): (
                WorkspaceScopeState.BOTH_USABLE
            ),
            (_ProbeOutcome.FAILED, _ProbeOutcome.USABLE): (
                WorkspaceScopeState.TARGET_SPECIFIC_FAILURE
            ),
            (_ProbeOutcome.USABLE, _ProbeOutcome.FAILED): (
                WorkspaceScopeState.CONTROL_SPECIFIC_FAILURE
            ),
            (_ProbeOutcome.FAILED, _ProbeOutcome.FAILED): WorkspaceScopeState.BOTH_FAILED,
        }[(target_outcome, control_outcome)]
        if state is not expected:
            raise ValueError("workspace scope state conflicts with probe reports")

    @property
    def successful(self) -> bool:
        """Whether both directories completed a successful probe."""

        return WorkspaceScopeState(self.state) is WorkspaceScopeState.BOTH_USABLE

    @property
    def target_report(self) -> WorkspaceProbeReport | None:
        """Compatibility alias for callers that name nested reports explicitly."""

        return self.target_probe

    @property
    def control_report(self) -> WorkspaceProbeReport | None:
        """Compatibility alias for callers that name nested reports explicitly."""

        return self.control_probe

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "kind": self.kind,
            "target": self.target,
            "control": self.control,
            "state": WorkspaceScopeState(self.state).value,
            "complete": self.complete,
            "target_probe": (
                self.target_probe.to_dict() if self.target_probe is not None else None
            ),
            "control_probe": (
                self.control_probe.to_dict() if self.control_probe is not None else None
            ),
        }


class _ProbeOutcome(StrEnum):
    USABLE = "usable"
    FAILED = "failed"
    UNKNOWN = "unknown"


ProbeRunner = Callable[..., WorkspaceProbeReport]


def run_workspace_scope(
    target: Path | str,
    control: Path | str,
    *,
    allow_write: bool = False,
    probe_runner: ProbeRunner | None = None,
    user_profile: str | None = None,
) -> WorkspaceScopeReport:
    """Run exactly one existing workspace probe in each validated directory.

    Both directory inputs are inspected and resolved before the first probe is
    called.  A normal unsuccessful report still permits the control probe;
    unexpected exceptions and Ctrl-C produce an inconclusive partial report
    and never start the other probe.
    """

    if os.name != "nt":
        raise WorkspaceScopeInputError("workspace-scope is supported on Windows only")
    if not allow_write:
        raise WorkspaceScopeInputError("workspace-scope requires --allow-write")

    resolved_target = _validate_scope_directory(target, user_profile=user_profile)
    resolved_control = _validate_scope_directory(control, user_profile=user_profile)
    if os.path.normcase(str(resolved_target)) == os.path.normcase(str(resolved_control)):
        raise WorkspaceScopeInputError("target and control must be different directories")

    target_text = redact_text(str(resolved_target), user_profile=user_profile)
    control_text = redact_text(str(resolved_control), user_profile=user_profile)
    probe = probe_runner if probe_runner is not None else run_workspace_probe

    target_report: WorkspaceProbeReport | None = None
    control_report: WorkspaceProbeReport | None = None
    try:
        target_report = _invoke_probe(
            probe,
            resolved_target,
            user_profile=user_profile,
            injected=probe_runner is not None,
        )
    except WorkspaceProbeInterrupted as exc:
        partial = _partial_report(
            target_text,
            control_text,
            target_probe=_redact_probe_report(exc.report, user_profile=user_profile),
            control_probe=None,
        )
        raise WorkspaceScopeInterrupted(partial) from exc
    except WorkspaceProbeUnexpectedError as exc:
        partial = _partial_report(
            target_text,
            control_text,
            target_probe=_redact_probe_report(exc.report, user_profile=user_profile),
            control_probe=None,
        )
        raise WorkspaceScopeUnexpectedError(partial, exc.cause) from exc
    except KeyboardInterrupt as exc:
        partial = _partial_report(target_text, control_text)
        raise WorkspaceScopeInterrupted(partial) from exc
    except Exception as exc:
        partial = _partial_report(target_text, control_text)
        raise WorkspaceScopeUnexpectedError(partial, exc) from exc

    if not isinstance(target_report, WorkspaceProbeReport):
        partial = _partial_report(target_text, control_text)
        raise WorkspaceScopeUnexpectedError(
            partial, TypeError("probe runner returned an invalid target report")
        )
    target_report = _redact_probe_report(target_report, user_profile=user_profile)

    try:
        control_report = _invoke_probe(
            probe,
            resolved_control,
            user_profile=user_profile,
            injected=probe_runner is not None,
        )
    except WorkspaceProbeInterrupted as exc:
        partial = _partial_report(
            target_text,
            control_text,
            target_probe=target_report,
            control_probe=_redact_probe_report(exc.report, user_profile=user_profile),
        )
        raise WorkspaceScopeInterrupted(partial) from exc
    except WorkspaceProbeUnexpectedError as exc:
        partial = _partial_report(
            target_text,
            control_text,
            target_probe=target_report,
            control_probe=_redact_probe_report(exc.report, user_profile=user_profile),
        )
        raise WorkspaceScopeUnexpectedError(partial, exc.cause) from exc
    except KeyboardInterrupt as exc:
        partial = _partial_report(
            target_text,
            control_text,
            target_probe=target_report,
        )
        raise WorkspaceScopeInterrupted(partial) from exc
    except Exception as exc:
        partial = _partial_report(
            target_text,
            control_text,
            target_probe=target_report,
        )
        raise WorkspaceScopeUnexpectedError(partial, exc) from exc

    if not isinstance(control_report, WorkspaceProbeReport):
        partial = _partial_report(
            target_text,
            control_text,
            target_probe=target_report,
        )
        raise WorkspaceScopeUnexpectedError(
            partial, TypeError("probe runner returned an invalid control report")
        )
    control_report = _redact_probe_report(control_report, user_profile=user_profile)

    state = _state_for(target_report, control_report)
    return WorkspaceScopeReport(
        schema_version=WORKSPACE_SCOPE_SCHEMA_VERSION,
        tool=WORKSPACE_SCOPE_TOOL,
        kind=WORKSPACE_SCOPE_KIND,
        target=target_text,
        control=control_text,
        target_probe=target_report,
        control_probe=control_report,
        state=state,
        complete=True,
    )


def _invoke_probe(
    probe: ProbeRunner,
    path: Path,
    *,
    user_profile: str | None,
    injected: bool,
) -> WorkspaceProbeReport:
    """Keep test runners narrow while forwarding profile to the real probe."""

    if injected:
        return probe(path, allow_write=True)
    return probe(path, allow_write=True, user_profile=user_profile)


def _validate_scope_directory(
    value: Path | str,
    *,
    user_profile: str | None,
) -> Path:
    try:
        path = Path(value)
        item = path.lstat()
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise WorkspaceScopeInputError(
            "workspace scope directory cannot be resolved or inspected: "
            + _safe_exception_text(exc, user_profile=user_profile)
        ) from exc
    if _is_reparse(item):
        raise WorkspaceScopeInputError(
            "workspace scope directory is a reparse point; refusing to write"
        )
    if not stat.S_ISDIR(item.st_mode):
        raise WorkspaceScopeInputError(
            "workspace scope directory must be an existing ordinary directory"
        )
    try:
        resolved = path.resolve(strict=True)
        resolved_item = resolved.lstat()
    except (OSError, UnicodeError, RuntimeError) as exc:
        raise WorkspaceScopeInputError(
            "workspace scope directory cannot be resolved or inspected: "
            + _safe_exception_text(exc, user_profile=user_profile)
        ) from exc
    if _is_reparse(resolved_item) or not stat.S_ISDIR(resolved_item.st_mode):
        raise WorkspaceScopeInputError(
            "workspace scope directory is not an ordinary resolved directory"
        )
    return resolved


def _state_for(
    target: WorkspaceProbeReport, control: WorkspaceProbeReport
) -> WorkspaceScopeState:
    target_outcome = _probe_outcome(target)
    control_outcome = _probe_outcome(control)
    if (
        target_outcome is _ProbeOutcome.UNKNOWN
        or control_outcome is _ProbeOutcome.UNKNOWN
    ):
        return WorkspaceScopeState.INCONCLUSIVE
    if target_outcome is _ProbeOutcome.USABLE and control_outcome is _ProbeOutcome.USABLE:
        return WorkspaceScopeState.BOTH_USABLE
    if target_outcome is _ProbeOutcome.FAILED and control_outcome is _ProbeOutcome.USABLE:
        return WorkspaceScopeState.TARGET_SPECIFIC_FAILURE
    if target_outcome is _ProbeOutcome.USABLE and control_outcome is _ProbeOutcome.FAILED:
        return WorkspaceScopeState.CONTROL_SPECIFIC_FAILURE
    return WorkspaceScopeState.BOTH_FAILED


def _probe_outcome(report: WorkspaceProbeReport) -> _ProbeOutcome:
    if any(check.status is CheckStatus.FAIL for check in report.checks):
        return _ProbeOutcome.FAILED
    if report.residual_paths:
        return _ProbeOutcome.FAILED
    if report.successful and all(
        check.status is CheckStatus.PASS for check in report.checks
    ):
        return _ProbeOutcome.USABLE
    return _ProbeOutcome.UNKNOWN


def _partial_report(
    target: str,
    control: str,
    *,
    target_probe: WorkspaceProbeReport | None = None,
    control_probe: WorkspaceProbeReport | None = None,
) -> WorkspaceScopeReport:
    return WorkspaceScopeReport(
        schema_version=WORKSPACE_SCOPE_SCHEMA_VERSION,
        tool=WORKSPACE_SCOPE_TOOL,
        kind=WORKSPACE_SCOPE_KIND,
        target=target,
        control=control,
        target_probe=target_probe,
        control_probe=control_probe,
        state=WorkspaceScopeState.INCONCLUSIVE,
        complete=False,
    )


def _redact_probe_report(
    report: WorkspaceProbeReport,
    *,
    user_profile: str | None,
) -> WorkspaceProbeReport:
    """Copy only when an injected probe report still contains a user path."""

    target = redact_text(report.target, user_profile=user_profile)
    checks = tuple(
        CheckResult(
            id=check.id,
            status=check.status,
            summary=check.summary,
            evidence=tuple(
                redact_text(item, user_profile=user_profile) for item in check.evidence
            ),
            details=check.details,
        )
        for check in report.checks
    )
    if target == report.target and checks == report.checks:
        return report
    return WorkspaceProbeReport(
        schema_version=report.schema_version,
        tool=report.tool,
        kind=report.kind,
        target=target,
        successful=report.successful,
        checks=checks,
        residual_paths=report.residual_paths,
    )


def _is_reparse(value: os.stat_result) -> bool:
    attributes = int(getattr(value, "st_file_attributes", 0) or 0)
    tag = int(getattr(value, "st_reparse_tag", 0) or 0)
    return bool(attributes & _REPARSE_POINT or tag)


def _safe_exception_text(exc: BaseException, *, user_profile: str | None) -> str:
    message = redact_text(str(exc), user_profile=user_profile)
    return f"exception_type: {type(exc).__name__}" + (
        f"; message: {message[:200]}" if message else ""
    )

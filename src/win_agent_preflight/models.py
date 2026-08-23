"""Stable, JSON-friendly models used by the first scan slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CheckStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CommandCandidate:
    """A command path found in the current process environment."""

    name: str
    path: str
    source: str = "PATH"

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": self.path, "source": self.source}


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One deterministic diagnostic result.

    Failures are intentionally required to carry evidence. This prevents a
    renderer from presenting a guess as a confirmed failure.
    """

    id: str
    status: CheckStatus
    summary: str
    evidence: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status is CheckStatus.FAIL and not self.evidence:
            raise ValueError("fail results must contain evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "details": _json_copy(self.details),
        }


@dataclass(frozen=True, slots=True)
class ScanReport:
    """Top-level scan result with stable check ordering."""

    schema_version: int
    tool: str
    checks: tuple[CheckResult, ...]

    def to_dict(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in CheckStatus}
        for check in self.checks:
            counts[check.status.value] += 1
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "summary": counts,
            "checks": [check.to_dict() for check in self.checks],
        }


def _json_copy(value: Any) -> Any:
    """Copy supported model values without exposing mutable model state."""

    if isinstance(value, dict):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value

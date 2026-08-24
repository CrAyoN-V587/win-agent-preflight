"""Presentation helpers for snapshot comparison."""

from __future__ import annotations

import json

from .snapshot import SnapshotComparison


def render_compare_json(comparison: SnapshotComparison, *, pretty: bool = False) -> str:
    return json.dumps(
        comparison.to_dict(),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )


def render_compare_console(comparison: SnapshotComparison) -> str:
    if comparison.equivalent:
        return "Snapshots are equivalent."
    lines = [f"Snapshot differences: {len(comparison.differences)}"]
    for difference in comparison.differences:
        lines.append(f"- {difference.field}")
        lines.append(f"  baseline: {difference.baseline!r}")
        lines.append(f"  current:  {difference.current!r}")
    return "\n".join(lines)

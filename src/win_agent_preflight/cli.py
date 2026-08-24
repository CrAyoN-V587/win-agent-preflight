"""Typer entrypoint for the deterministic first scan slice."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from .checks import scan_environment
from .compare import render_compare_console, render_compare_json
from .reporting import (
    render_console,
    render_json,
    render_workspace_probe_console,
    render_workspace_probe_json,
)
from .snapshot import (
    SnapshotError,
    capture_snapshot,
    compare_snapshots,
    load_snapshot,
    write_snapshot,
)
from .windows import redact_text
from .workspace_probe import (
    WorkspaceProbeInputError,
    WorkspaceProbeInterrupted,
    WorkspaceProbeUnexpectedError,
    run_workspace_probe,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Windows Agent Preflight CLI."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


@app.command()
def scan(
    json_output: bool = typer.Option(False, "--json", help="输出稳定 JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="JSON 使用缩进格式"),
    timeout: float = typer.Option(5.0, min=0.1, help="每个外部命令的超时秒数"),
) -> None:
    """扫描当前 Windows 环境中的命令和 PowerShell 事实。"""

    report = scan_environment(timeout=timeout)
    typer.echo(render_json(report, pretty=pretty) if json_output else render_console(report))
    if report.to_dict()["summary"]["fail"]:
        raise typer.Exit(code=1)


@app.command()
def snapshot(
    label: str = typer.Option(..., "--label", help="快照标签，例如 host 或 agent"),
    output: Path = typer.Option(..., "--output", "-o", help="快照 JSON 输出路径"),
    pretty: bool = typer.Option(False, "--pretty", help="JSON 使用缩进格式"),
    force: bool = typer.Option(False, "--force", help="覆盖已有输出文件"),
    timeout: float = typer.Option(5.0, min=0.1, help="每个外部命令的超时秒数"),
) -> None:
    """写出当前宿主环境的 v1 快照。"""

    try:
        captured = capture_snapshot(label, timeout=timeout)
        write_snapshot(captured, output, pretty=pretty, force=force)
    except (SnapshotError, OSError, ValueError) as exc:
        typer.echo(f"snapshot error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"snapshot written: {redact_text(str(output))}")


@app.command()
def compare(
    baseline: Path = typer.Argument(..., help="基线快照 JSON"),
    current: Path = typer.Argument(..., help="当前快照 JSON"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON 差异"),
    pretty: bool = typer.Option(False, "--pretty", help="JSON 使用缩进格式"),
) -> None:
    """比较两个 v1 快照；等价为 0，有差异为 1，输入错误为 2。"""

    try:
        result = compare_snapshots(load_snapshot(baseline), load_snapshot(current))
    except (SnapshotError, OSError, ValueError) as exc:
        typer.echo(f"compare error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        render_compare_json(result, pretty=pretty)
        if json_output
        else render_compare_console(result)
    )
    if not result.equivalent:
        raise typer.Exit(code=1)


@app.command("workspace-probe")
def workspace_probe(
    target: Path = typer.Option(..., "--target", help="已存在的普通工作区目录"),
    allow_write: bool = typer.Option(
        False,
        "--allow-write",
        help="明确允许在 target 直接子目录中执行一次性探针",
    ),
    json_output: bool = typer.Option(False, "--json", help="输出独立的 v1 JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="JSON 使用缩进格式"),
) -> None:
    """验证当前 Windows 工作区的最小写入、重命名和清理能力。"""

    if not allow_write:
        typer.echo("workspace-probe error: --allow-write is required", err=True)
        raise typer.Exit(code=2)
    try:
        report = run_workspace_probe(target, allow_write=allow_write)
    except WorkspaceProbeInterrupted as exc:
        report = exc.report
        typer.echo(
            render_workspace_probe_json(report, pretty=pretty)
            if json_output
            else render_workspace_probe_console(report)
        )
        raise typer.Exit(code=130) from exc
    except WorkspaceProbeUnexpectedError as exc:
        typer.echo(
            render_workspace_probe_json(exc.report, pretty=pretty)
            if json_output
            else render_workspace_probe_console(exc.report)
        )
        raise typer.Exit(code=1) from exc
    except (WorkspaceProbeInputError, OSError, ValueError) as exc:
        typer.echo(f"workspace-probe error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        render_workspace_probe_json(report, pretty=pretty)
        if json_output
        else render_workspace_probe_console(report)
    )
    if not report.successful:
        raise typer.Exit(code=1)

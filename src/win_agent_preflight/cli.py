"""Typer entrypoint for the deterministic first scan slice."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from .agent_doctor import (
    AgentDoctorInputError,
    run_agent_doctor,
)
from .checks import scan_environment
from .command_doctor import (
    CommandDoctorInputError,
    run_command_doctor,
)
from .compare import render_compare_console, render_compare_json
from .project_doctor import ProjectDoctorInputError, run_project_doctor
from .reporting import (
    render_agent_doctor_console,
    render_agent_doctor_json,
    render_command_doctor_console,
    render_command_doctor_json,
    render_console,
    render_json,
    render_project_doctor_console,
    render_project_doctor_json,
    render_support_report_console,
    render_support_report_json,
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
from .support_report import SupportReportInputError, run_support_report
from .windows import redact_text
from .workspace_probe import (
    WorkspaceProbeInputError,
    WorkspaceProbeInterrupted,
    WorkspaceProbeUnexpectedError,
    run_workspace_probe,
)

app = typer.Typer(add_completion=False, no_args_is_help=True, rich_markup_mode=None)


@app.callback()
def main() -> None:
    """Windows Agent Preflight CLI."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


@app.command()
def scan(
    json_output: bool = typer.Option(False, "--json", help="Print stable JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
    timeout: float = typer.Option(5.0, min=0.1, help="Timeout per external command in seconds"),
) -> None:
    """Scan current Windows commands and PowerShell facts."""

    report = scan_environment(timeout=timeout)
    typer.echo(render_json(report, pretty=pretty) if json_output else render_console(report))
    if report.to_dict()["summary"]["fail"]:
        raise typer.Exit(code=1)


@app.command()
def snapshot(
    label: str = typer.Option(..., "--label", help="Snapshot label, for example host or agent"),
    output: Path = typer.Option(..., "--output", "-o", help="Snapshot JSON output path"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing output file"),
    timeout: float = typer.Option(5.0, min=0.1, help="Timeout per external command in seconds"),
) -> None:
    """Write a v1 snapshot of the current host environment."""

    try:
        captured = capture_snapshot(label, timeout=timeout)
        write_snapshot(captured, output, pretty=pretty, force=force)
    except (SnapshotError, OSError, ValueError) as exc:
        typer.echo(f"snapshot error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"snapshot written: {redact_text(str(output))}")


@app.command()
def compare(
    baseline: Path = typer.Argument(..., help="Baseline snapshot JSON"),
    current: Path = typer.Argument(..., help="Current snapshot JSON"),
    json_output: bool = typer.Option(False, "--json", help="Print JSON differences"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
) -> None:
    """Compare two v1 snapshots; exit 0 if equal, 1 if different, 2 for bad input."""

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


@app.command("agent-doctor")
def agent_doctor(
    agents: list[str] | None = typer.Option(
        None,
        "--agent",
        help="Agents to check; repeatable; defaults to codex, claude, dsh",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print standalone v1 JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
    timeout: float = typer.Option(5.0, min=0.1, help="Timeout per version probe in seconds"),
) -> None:
    """Run --version only for Agent launchers found on PATH."""

    try:
        report = run_agent_doctor(agents=agents, timeout=timeout)
    except AgentDoctorInputError as exc:
        typer.echo(f"agent-doctor error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        render_agent_doctor_json(report, pretty=pretty)
        if json_output
        else render_agent_doctor_console(report)
    )
    if report.has_unusable_agent:
        raise typer.Exit(code=1)


@app.command("command-doctor")
def command_doctor(
    command: str = typer.Argument(..., help="PATH command basename to check"),
    json_output: bool = typer.Option(False, "--json", help="Print standalone v1 JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
    timeout: float = typer.Option(5.0, min=0.1, help="Timeout per version probe in seconds"),
) -> None:
    """Probe one PATH launcher with --version only."""

    try:
        report = run_command_doctor(command, timeout=timeout)
    except CommandDoctorInputError as exc:
        typer.echo(f"command-doctor error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        render_command_doctor_json(report, pretty=pretty)
        if json_output
        else render_command_doctor_console(report)
    )
    if not report.successful:
        raise typer.Exit(code=1)


@app.command("support-report")
def support_report(
    json_output: bool = typer.Option(False, "--json", help="Print shareable v2 JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
    timeout: float = typer.Option(5.0, min=0.1, help="Timeout per external command in seconds"),
) -> None:
    """Collect an offline support report without write probes or network calls."""

    try:
        report = run_support_report(timeout=timeout)
    except SupportReportInputError as exc:
        typer.echo(f"support-report error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        render_support_report_json(report, pretty=pretty)
        if json_output
        else render_support_report_console(report)
    )
    if report.errors:
        raise typer.Exit(code=1)


@app.command("project-doctor")
def project_doctor(
    target: Path = typer.Option(..., "--target", help="Existing project directory"),
    json_output: bool = typer.Option(False, "--json", help="Print standalone v1 JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
    timeout: float = typer.Option(5.0, min=0.1, help="Timeout per version probe in seconds"),
) -> None:
    """Infer required local tools from fixed first-level project markers."""

    try:
        report = run_project_doctor(target, timeout=timeout)
    except ProjectDoctorInputError as exc:
        typer.echo(f"project-doctor error: {redact_text(str(exc))}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        render_project_doctor_json(report, pretty=pretty)
        if json_output
        else render_project_doctor_console(report)
    )
    if not report.successful:
        raise typer.Exit(code=1)


@app.command("workspace-probe")
def workspace_probe(
    target: Path = typer.Option(..., "--target", help="Existing regular workspace directory"),
    allow_write: bool = typer.Option(
        False,
        "--allow-write",
        help="Allow one probe in a direct child of target",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print standalone v1 JSON"),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON"),
) -> None:
    """Check minimal Windows workspace write, rename, and cleanup capabilities."""

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

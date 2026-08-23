"""Typer entrypoint for the deterministic first scan slice."""

from __future__ import annotations

import sys

import typer

from .checks import scan_environment
from .reporting import render_console, render_json

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

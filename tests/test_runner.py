from __future__ import annotations

from collections.abc import Mapping, Sequence

from win_agent_preflight.runner import CommandExecution, Runner


def test_runner_injects_timeout_and_arguments() -> None:
    received: list[tuple[tuple[str, ...], float]] = []

    def executor(
        argv: Sequence[str],
        timeout: float,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> CommandExecution:
        del env, cwd
        received.append((tuple(argv), timeout))
        return CommandExecution(argv=tuple(argv), returncode=None, timed_out=True, error="timeout")

    result = Runner(executor=executor).run(("slow-tool", "--version"), timeout=0.25)
    assert result.timed_out is True
    assert received == [(("slow-tool", "--version"), 0.25)]


def test_runner_keeps_structured_os_error_fields(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        error = PermissionError("private detail")
        error.winerror = 5  # type: ignore[attr-defined]
        raise error

    monkeypatch.setattr("win_agent_preflight.runner.subprocess.run", fail)
    result = Runner().run(("blocked.exe", "--version"))

    assert result.error_type == "PermissionError"
    assert result.winerror == 5
    assert "private detail" in (result.error or "")

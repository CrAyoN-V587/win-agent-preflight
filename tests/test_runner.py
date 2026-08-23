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

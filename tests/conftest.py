from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from win_agent_preflight.runner import CommandExecution, Runner


@pytest.fixture
def recording_runner():
    calls: list[tuple[str, ...]] = []

    def executor(
        argv: Sequence[str],
        timeout: float,
        env: Mapping[str, str] | None,
        cwd: str | None,
    ) -> CommandExecution:
        del timeout, env, cwd
        normalized = tuple(str(item) for item in argv)
        calls.append(normalized)
        return CommandExecution(argv=normalized, returncode=0, stdout="tool 1.0\n")

    runner = Runner(executor=executor)
    return runner, calls

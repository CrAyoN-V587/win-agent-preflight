"""The only boundary through which diagnostics execute external commands."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandExecution:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    elapsed_ms: int = 0
    timed_out: bool = False
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.error is None


Executor = Callable[
    [Sequence[str], float, Mapping[str, str] | None, str | None], CommandExecution
]


class Runner:
    """Run commands with bounded time and an injectable executor for tests."""

    def __init__(self, executor: Executor | None = None, default_timeout: float = 5.0) -> None:
        if default_timeout <= 0:
            raise ValueError("default_timeout must be positive")
        self._executor = executor or _subprocess_executor
        self.default_timeout = default_timeout

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandExecution:
        if not argv or not all(str(item) for item in argv):
            raise ValueError("argv must contain at least one non-empty argument")
        effective_timeout = self.default_timeout if timeout is None else timeout
        if effective_timeout <= 0:
            raise ValueError("timeout must be positive")
        return self._executor(tuple(str(item) for item in argv), effective_timeout, env, cwd)


def _subprocess_executor(
    argv: Sequence[str],
    timeout: float,
    env: Mapping[str, str] | None,
    cwd: str | None,
) -> CommandExecution:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=dict(env) if env is not None else None,
            cwd=cwd,
            shell=False,
            check=False,
        )
        return CommandExecution(
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_ms=_elapsed_ms(started),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandExecution(
            argv=tuple(argv),
            returncode=None,
            stdout=_text(exc.stdout),
            stderr=_text(exc.stderr),
            elapsed_ms=_elapsed_ms(started),
            timed_out=True,
            error=f"timeout after {timeout:g}s",
        )
    except OSError as exc:
        return CommandExecution(
            argv=tuple(argv),
            returncode=None,
            elapsed_ms=_elapsed_ms(started),
            error=f"{type(exc).__name__}: {exc}",
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

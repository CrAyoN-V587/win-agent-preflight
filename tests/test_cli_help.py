from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HELP_COMMANDS: tuple[tuple[str, ...], ...] = (
    (),
    ("scan",),
    ("snapshot",),
    ("compare",),
    ("agent-doctor",),
    ("support-report",),
    ("project-doctor",),
    ("workspace-probe",),
)


def test_all_cli_help_is_ascii_under_cp1252(tmp_path: Path) -> None:
    """Help must be safe for a strict legacy Windows console code page."""

    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252:strict"
    source_path = str(project_root / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (source_path, environment.get("PYTHONPATH")) if item
    )

    for command in HELP_COMMANDS:
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "win_agent_preflight", *command, "--help"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            check=False,
        )
        stdout = completed.stdout.decode("cp1252", errors="strict")
        stderr = completed.stderr.decode("cp1252", errors="strict")

        assert completed.returncode == 0, (command, stdout, stderr)
        assert "Usage:" in stdout, (command, stdout)
        assert all(ord(char) < 128 for char in stdout), (command, stdout)
        assert all(ord(char) < 128 for char in stderr), (command, stderr)
        assert tuple(tmp_path.iterdir()) == ()

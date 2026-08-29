# Windows Agent Preflight

[![Windows CI](https://github.com/CrAyoN-V587/win-agent-preflight/actions/workflows/ci.yml/badge.svg)](https://github.com/CrAyoN-V587/win-agent-preflight/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Offline, Windows-first diagnostics for differences between a host terminal and AI coding-agent execution contexts.**

中文完整说明：[README.zh-CN.md](README.zh-CN.md)

## Why this exists

On Windows, a command can work in a normal PowerShell window and fail inside Codex, Claude Code, or another coding agent. The cause may be a stale inherited `PATH`, a different PowerShell launcher, a packaged WindowsApps executable, a restricted workspace, or a different candidate chosen from `PATHEXT`.

Windows Agent Preflight turns those layers into small, inspectable local reports. It is useful when a project failure looks like a missing dependency but the real difference is the process that launched it.

## What it does

- Discovers Windows command candidates and performs bounded, read-only `--version` probes.
- Reports PowerShell parsing, execution-policy, registry `PATH`, and current-process `PATH` refresh facts.
- Diagnoses Codex, Claude Code, DSH, a selected command, Git readiness, and project toolchain markers.
- Captures a host or agent execution context as JSON and compares two separately collected snapshots.
- Optionally probes the smallest file lifecycle in an explicitly selected directory.
- Redacts the current user directory to `%USERPROFILE%` and keeps the report schema stable.

The tool is Windows-only, offline-first, and evidence-first. It is not an agent manager, security scanner, configuration synchronizer, or automatic repair tool.

## v0.1.0 quick start

Requirements: Windows 10/11 and Python `>=3.12`. The runtime dependency is `typer`; Node.js, Docker, WSL, databases, and other agent CLIs are optional diagnostic targets, not installation requirements.

```powershell
git clone https://github.com/CrAyoN-V587/win-agent-preflight.git
Set-Location .\win-agent-preflight

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\agent-preflight.exe scan
```

Create a compact support report:

```powershell
.\.venv\Scripts\agent-preflight.exe support-report --json --pretty --timeout 5
```

Diagnose one command without logging in or installing it:

```powershell
.\.venv\Scripts\agent-preflight.exe command-doctor npm --json --pretty --timeout 5
```

Installation may use `pip` and therefore the network. After installation, `scan`, the doctor commands, `snapshot`, and `compare` do not log in, call a web service, modify the system, or run package-manager installation flows.

## Host and agent evidence

A real comparison requires two independently triggered snapshots: one from a normal host PowerShell window and one from the coding agent's own command executor. Running both commands in one process only produces two reports of the same context.

```text
Host PowerShell  ── snapshot(host)  ─┐
                                     ├─ compare ── differences
Agent executor  ── snapshot(agent) ─┘
```

Use the same machine, project directory, code revision, run identifier, and timeout on both sides. The [host↔Codex case study](docs/host-codex-case-study.md) records a sanitized real comparison; the [paired-collection protocol](docs/context-comparison.md) explains how to reproduce it.

## Command overview

| Command | Purpose | Writes files? |
| --- | --- | --- |
| `scan` | Fixed command, PowerShell, and `PATH` facts | No |
| `support-report` | Combines local scan and agent-launcher results | No |
| `agent-doctor` | Probes Codex, Claude Code, and DSH launchers | No |
| `command-doctor NAME` | Diagnoses one `PATH` launcher | No |
| `git-doctor --target PATH` | Checks local Git readiness; no remote auth check | No |
| `project-doctor --target PATH` | Infers supported project tools from first-level markers | No |
| `snapshot` | Writes the current execution context as JSON | Selected output only |
| `compare` | Compares two snapshots | No |
| `workspace-probe --allow-write` | Tests a bounded file lifecycle in one directory | Yes, temporary probe |
| `workspace-scope --allow-write` | Compares target and control directory capability | Yes, temporary probes |

All external commands have a timeout. Write probes require an explicit `--allow-write`; do not use them in sensitive or important directories.

## Boundaries and privacy

The normal diagnostic path is offline, read-only, and does not require login. The project does not:

- execute `login`, `doctor`, `npx`, web, push/fetch, or other network flows;
- modify `PATH`, the registry, execution policy, ACLs, agent configuration, or project code;
- auto-fix, elevate privileges, collect secrets, or upload reports;
- claim that a local `usable` launcher means account authentication, network access, or full agent sandbox access.

Reports can still reveal installed software, versions, non-user directories, project names, and agent runtime layout. Before sharing, replace remaining private paths and remove raw snapshots when they are no longer needed. For external reports, use the minimal template in the [optional pilot guide](docs/external-pilot-guide.md); do not attach raw JSON, full `PATH`, credentials, or business files.

## Status and next boundary

The repository is prepared for the `0.1.0` release boundary. Local package checks are complete; the release sequence is: the maintainer confirms the date and finalizes the 0.1.0 changelog, commits and pushes the final release materials, waits for Windows CI on that commit to succeed, then creates the `v0.1.0` tag/Release from that same commit and uploads the validated artifacts. Feature development is then intentionally paused.

The pause is lifted only when there is useful evidence: an external Issue or PR or real report; the same gap appears in at least two independent environments; or a stable upstream problem cannot be distinguished by the current tool. If the project has release and at least two relevant shares but no stars after 14 days despite visits or clones, allow one positioning/demo adjustment before considering implementation work. GitHub stars are an adoption signal, not a direct measure of quality.

The optional [external pilot guide](docs/external-pilot-guide.md) remains available for anyone who wants to provide a sanitized report. External testing is not required for the v0.1.0 release sequence or to make the pause decision.

## Documentation

- [中文完整说明](README.zh-CN.md)
- [Host↔Codex case study](docs/host-codex-case-study.md)
- [Paired collection protocol](docs/context-comparison.md)
- [Research and overlap review](docs/research.md)
- [Design notes](docs/design.md)
- [External pilot guide](docs/external-pilot-guide.md)
- [Project state](PROJECT.md) and [progress log](docs/PROGRESS.md)
- [Local package acceptance](docs/release-check.md)
- [Changelog](CHANGELOG.md)

## Development

```powershell
python -m pip install -e ".[dev]"
python -B -m pytest -q -p no:cacheprovider
python -m ruff check . --no-cache
```

Contributions should keep the host/agent distinction explicit and include a minimal, sanitized reproduction. See [AGENTS.md](AGENTS.md) before changing the project.

## License

[MIT License](LICENSE)

"""Offline, local-only diagnostics for a Git working tree."""

from __future__ import annotations

import math
import ntpath
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .launcher_probe import LauncherProbeOutcome, LauncherProbeState, probe_launchers
from .models import CheckResult, CheckStatus, CommandCandidate
from .runner import CommandExecution, Runner
from .windows import (
    COMMAND_LAUNCHER_EXTENSIONS,
    discover_command_details,
    redact_text,
)

GIT_DOCTOR_SCHEMA_VERSION = 1
GIT_DOCTOR_TOOL = "win-agent-preflight"
GIT_DOCTOR_KIND = "git_doctor"
GIT_CHECK_IDS = (
    "git.launcher",
    "git.repository",
    "git.commit_identity",
    "git.remote.origin",
    "git.credential_helper",
    "github.cli",
    "github.auth",
)
_REPARSE_POINT = 0x400
_MAX_TEXT = 240
_CONFIG_SCOPES = frozenset({"system", "global", "local", "command", "worktree"})
_SCP_REMOTE = re.compile(
    r"^(?:(?P<user>[^/@:\s]+)@)?(?P<host>[^/:\s]+):(?P<path>[^\s].*)$"
)


class GitDoctorInputError(ValueError):
    """Raised when the platform, target, or timeout is not acceptable."""


@dataclass(frozen=True, slots=True)
class GitDoctorReport:
    """Independent v1 report containing only safe local Git facts."""

    schema_version: int
    tool: str
    kind: str
    target: str
    local_ready: bool
    remote_auth_verified: bool
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.schema_version != GIT_DOCTOR_SCHEMA_VERSION:
            raise ValueError("unsupported git doctor schema version")
        if self.tool != GIT_DOCTOR_TOOL or self.kind != GIT_DOCTOR_KIND:
            raise ValueError("invalid git doctor identity")
        if self.remote_auth_verified is not False:
            raise ValueError("git doctor never verifies remote authentication")
        if tuple(check.id for check in self.checks) != GIT_CHECK_IDS:
            raise ValueError("git doctor checks must use the fixed order")

    def to_dict(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in CheckStatus}
        for check in self.checks:
            counts[check.status.value] += 1
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "tool": self.tool,
            "offline": True,
            "target": self.target,
            "local_ready": self.local_ready,
            "remote_auth_verified": False,
            "summary": counts,
            "checks": [check.to_dict() for check in self.checks],
        }


def run_git_doctor(
    target: Path | str,
    *,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> GitDoctorReport:
    """Collect bounded local Git facts without touching credentials or remotes."""

    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise GitDoctorInputError("timeout must be positive")
    if os.name != "nt":
        raise GitDoctorInputError("git-doctor is supported on Windows only")
    environment = env if env is not None else os.environ
    active_profile = user_profile or environment.get("USERPROFILE") or os.environ.get(
        "USERPROFILE"
    )
    target_path = _validate_target(target, user_profile=active_profile)
    active_runner = runner or Runner(default_timeout=timeout)

    git_discovery = discover_command_details(
        "git",
        env=environment,
        user_profile=active_profile,
        extensions=COMMAND_LAUNCHER_EXTENSIONS,
    )
    git_probe = _probe_launcher(
        git_discovery.candidates,
        git_discovery.non_executable_paths,
        git_discovery.inaccessible_paths,
        active_runner,
        env=environment,
        user_profile=active_profile,
        timeout=timeout,
    )
    launcher_check = _launcher_check(git_probe, len(git_discovery.candidates), "git")
    if git_probe.state is not LauncherProbeState.USABLE:
        return _report(
            target_path,
            active_profile,
            local_ready=False,
            checks=(
                launcher_check,
                _dependency_check("git.repository"),
                _dependency_check("git.commit_identity"),
                _dependency_check("git.remote.origin"),
                _dependency_check("git.credential_helper"),
                _dependency_check("github.cli"),
                _dependency_check("github.auth"),
            ),
        )

    git_path = _expand_path(git_probe.path, active_profile)
    repository_execution = _run_git(
        active_runner,
        git_path,
        target_path,
        ("rev-parse", "--is-inside-work-tree"),
        env=environment,
        timeout=timeout,
    )
    repository_check, repository_ok = _repository_check(repository_execution)
    if not repository_ok:
        return _report(
            target_path,
            active_profile,
            local_ready=False,
            checks=(
                launcher_check,
                repository_check,
                _dependency_check("git.commit_identity"),
                _dependency_check("git.remote.origin"),
                _dependency_check("git.credential_helper"),
                _dependency_check("github.cli"),
                _dependency_check("github.auth"),
            ),
        )

    identity_name = _run_git(
        active_runner,
        git_path,
        target_path,
        ("config", "--show-scope", "--get", "user.name"),
        env=environment,
        timeout=timeout,
    )
    identity_email = _run_git(
        active_runner,
        git_path,
        target_path,
        ("config", "--show-scope", "--get", "user.email"),
        env=environment,
        timeout=timeout,
    )
    identity_check, identity_ok = _identity_check(identity_name, identity_email)

    fetch_execution = _run_git(
        active_runner,
        git_path,
        target_path,
        ("remote", "get-url", "origin"),
        env=environment,
        timeout=timeout,
    )
    push_execution = _run_git(
        active_runner,
        git_path,
        target_path,
        ("remote", "get-url", "--push", "origin"),
        env=environment,
        timeout=timeout,
    )
    origin_check, origin_facts, github_remote = _origin_check(
        fetch_execution, push_execution
    )

    helper_execution = _run_git(
        active_runner,
        git_path,
        target_path,
        ("config", "--get-all", "credential.helper"),
        env=environment,
        timeout=timeout,
    )
    helper_check = _credential_helper_check(helper_execution, origin_facts)

    if github_remote is True:
        gh_discovery = discover_command_details(
            "gh",
            env=environment,
            user_profile=active_profile,
            extensions=COMMAND_LAUNCHER_EXTENSIONS,
        )
        gh_probe = _probe_launcher(
            gh_discovery.candidates,
            gh_discovery.non_executable_paths,
            gh_discovery.inaccessible_paths,
            active_runner,
            env=environment,
            user_profile=active_profile,
            timeout=timeout,
        )
        github_cli_check = _launcher_check(
            gh_probe, len(gh_discovery.candidates), "gh", missing_is_warning=True
        )
        github_auth_check = CheckResult(
            id="github.auth",
            status=CheckStatus.UNKNOWN,
            summary="GitHub 远程认证未验证",
            evidence=("remote authentication was not checked offline",),
            details={"reason": "not_checked_offline"},
        )
    elif github_remote is False:
        github_cli_check = _not_applicable_check("github.cli", "remote is not GitHub")
        github_auth_check = _not_applicable_check("github.auth", "remote is not GitHub")
    else:
        github_cli_check = _unknown_check("github.cli", "remote host was not classified")
        github_auth_check = _unknown_check(
            "github.auth", "remote host was not classified"
        )

    local_ready = (
        git_probe.state is LauncherProbeState.USABLE
        and repository_ok
        and identity_ok
        and origin_check.status is CheckStatus.PASS
        and not bool(origin_check.details.get("embedded_userinfo"))
    )
    return _report(
        target_path,
        active_profile,
        local_ready=local_ready,
        checks=(
            launcher_check,
            repository_check,
            identity_check,
            origin_check,
            helper_check,
            github_cli_check,
            github_auth_check,
        ),
    )


def _report(
    target: Path,
    user_profile: str | None,
    *,
    local_ready: bool,
    checks: tuple[CheckResult, ...],
) -> GitDoctorReport:
    return GitDoctorReport(
        schema_version=GIT_DOCTOR_SCHEMA_VERSION,
        tool=GIT_DOCTOR_TOOL,
        kind=GIT_DOCTOR_KIND,
        target=redact_text(str(target), user_profile=user_profile),
        local_ready=local_ready,
        remote_auth_verified=False,
        checks=checks,
    )


def _validate_target(target: Path | str, *, user_profile: str | None) -> Path:
    del user_profile
    try:
        target_path = Path(target)
        info = target_path.lstat()
    except (OSError, TypeError, ValueError) as exc:
        raise GitDoctorInputError("target cannot be resolved or inspected") from exc
    if _is_reparse(info) or stat.S_ISLNK(info.st_mode):
        raise GitDoctorInputError("target is a symlink or reparse point")
    if not stat.S_ISDIR(info.st_mode):
        raise GitDoctorInputError("target must be an existing ordinary directory")
    try:
        resolved = target_path.resolve(strict=True)
        resolved_info = resolved.lstat()
    except (OSError, RuntimeError) as exc:
        raise GitDoctorInputError("target cannot be resolved or inspected") from exc
    if _is_reparse(resolved_info) or stat.S_ISLNK(resolved_info.st_mode):
        raise GitDoctorInputError("target is a symlink or reparse point")
    if not stat.S_ISDIR(resolved_info.st_mode):
        raise GitDoctorInputError("target must be an existing ordinary directory")
    return resolved


def _is_reparse(value: os.stat_result) -> bool:
    tag = int(getattr(value, "st_reparse_tag", 0) or 0)
    attributes = int(getattr(value, "st_file_attributes", 0) or 0)
    return bool(tag or attributes & _REPARSE_POINT)


def _probe_launcher(
    candidates: tuple[CommandCandidate, ...],
    non_executable_paths: tuple[str, ...],
    inaccessible_paths,
    runner: Runner,
    *,
    env: Mapping[str, str],
    user_profile: str | None,
    timeout: float,
) -> LauncherProbeOutcome:
    if candidates:
        return probe_launchers(
            candidates,
            runner,
            env=env,
            user_profile=user_profile,
            timeout=timeout,
        )
    if inaccessible_paths:
        state = LauncherProbeState.ACCESS_DENIED
    elif non_executable_paths:
        state = LauncherProbeState.RESOLVED_BUT_NOT_EXECUTABLE
    else:
        state = LauncherProbeState.COMMAND_NOT_FOUND
    return LauncherProbeOutcome(state=state)


def _launcher_check(
    outcome: LauncherProbeOutcome,
    candidate_count: int,
    command: str,
    *,
    missing_is_warning: bool = False,
) -> CheckResult:
    details: dict[str, Any] = {
        "state": outcome.state.value,
        "candidate_count": candidate_count,
        "attempts": list(outcome.attempts),
    }
    if outcome.version is not None:
        details["version"] = outcome.version
    if outcome.state is LauncherProbeState.USABLE:
        return CheckResult(
            id="git.launcher" if command == "git" else "github.cli",
            status=CheckStatus.PASS,
            summary=f"{command} launcher is usable",
            evidence=(f"{command} --version completed",),
            details=details,
        )
    status = CheckStatus.WARNING if missing_is_warning else CheckStatus.FAIL
    return CheckResult(
        id="git.launcher" if command == "git" else "github.cli",
        status=status,
        summary=f"{command} launcher is unavailable",
        evidence=(f"{command} launcher could not complete --version",),
        details=details,
    )


def _run_git(
    runner: Runner,
    git_path: str | None,
    target: Path,
    args: tuple[str, ...],
    *,
    env: Mapping[str, str],
    timeout: float,
) -> CommandExecution:
    if not git_path:
        return CommandExecution(
            argv=("git", "-C", str(target), *args),
            returncode=None,
            error_type="LauncherUnavailable",
        )
    return runner.run(
        (git_path, "-C", str(target), *args),
        timeout=timeout,
        env=env,
    )


def _expand_path(path: str | None, user_profile: str | None) -> str | None:
    if path is None:
        return None
    return path.replace("%USERPROFILE%", user_profile or os.environ.get("USERPROFILE", ""))


def _execution_details(execution: CommandExecution) -> dict[str, Any]:
    details: dict[str, Any] = {
        "returncode": execution.returncode,
        "timed_out": execution.timed_out,
    }
    if execution.error_type is not None:
        details["error_type"] = execution.error_type
    elif execution.error:
        details["error_type"] = "RunnerError"
    if execution.winerror is not None:
        details["winerror"] = execution.winerror
    return details


def _repository_check(execution: CommandExecution) -> tuple[CheckResult, bool]:
    details = _execution_details(execution)
    if execution.succeeded:
        value = _first_nonempty(execution.stdout)
        if value.casefold() == "true":
            return (
                CheckResult(
                    id="git.repository",
                    status=CheckStatus.PASS,
                    summary="target is inside a Git work tree",
                    evidence=("Git work-tree check passed",),
                    details={**details, "is_inside_work_tree": True},
                ),
                True,
            )
        return (
            CheckResult(
                id="git.repository",
                status=CheckStatus.FAIL,
                summary="target is not inside a Git work tree",
                evidence=("Git work-tree check did not return true",),
                details={**details, "is_inside_work_tree": False},
            ),
            False,
        )
    status = CheckStatus.UNKNOWN if execution.error or execution.timed_out else CheckStatus.FAIL
    return (
        CheckResult(
            id="git.repository",
            status=status,
            summary="Git work-tree check could not be completed",
            evidence=("Git work-tree check failed",),
            details=details,
        ),
        False,
    )


def _identity_check(
    name_execution: CommandExecution, email_execution: CommandExecution
) -> tuple[CheckResult, bool]:
    name_configured, name_scope = _reduce_identity(name_execution)
    email_configured, email_scope = _reduce_identity(email_execution)
    name_unknown = name_scope == "unknown" and not name_configured
    email_unknown = email_scope == "unknown" and not email_configured
    details = {
        "name_configured": name_configured,
        "name_scope": name_scope,
        "email_configured": email_configured,
        "email_scope": email_scope,
    }
    if name_unknown or email_unknown:
        status = CheckStatus.UNKNOWN
        evidence = ("Git commit identity could not be read",)
    elif name_configured and email_configured:
        status = CheckStatus.PASS
        evidence = ("Git commit identity is configured",)
    else:
        status = CheckStatus.WARNING
        evidence = ("Git commit identity is incomplete",)
    return (
        CheckResult(
            id="git.commit_identity",
            status=status,
            summary="Git commit identity is available"
            if status is CheckStatus.PASS
            else "Git commit identity needs attention",
            evidence=evidence,
            details=details,
        ),
        status is CheckStatus.PASS,
    )


def _reduce_identity(execution: CommandExecution) -> tuple[bool, str]:
    if execution.succeeded:
        line = _first_nonempty_raw(execution.stdout)
        if not line:
            return False, "missing"
        parts = line.lstrip().split(None, 1)
        scope = parts[0].casefold()
        if scope in _CONFIG_SCOPES:
            return len(parts) == 2 and bool(parts[1].strip()), scope
        return False, "unknown"
    if execution.error or execution.timed_out or execution.returncode not in (1,):
        return False, "unknown"
    return False, "unknown" if execution.returncode is None else "missing"


def _origin_check(
    fetch_execution: CommandExecution, push_execution: CommandExecution
) -> tuple[CheckResult, dict[str, Any], bool | None]:
    fetch_state, fetch_details, fetch_key = _reduce_remote(fetch_execution)
    push_state, push_details, push_key = _reduce_remote(push_execution)
    same_destination = (
        fetch_key == push_key if fetch_state == "parsed" and push_state == "parsed" else None
    )
    details: dict[str, Any] = {
        "fetch": fetch_details,
        "push": push_details,
        "fetch_push_same_destination": same_destination,
    }
    details["embedded_userinfo"] = bool(
        fetch_details["embedded_userinfo"] or push_details["embedded_userinfo"]
    )
    if fetch_state == "unknown" or push_state == "unknown":
        status = CheckStatus.UNKNOWN
        evidence = ("Git origin remote could not be read",)
    elif fetch_state != "parsed" or push_state != "parsed":
        status = CheckStatus.WARNING
        evidence = ("Git origin fetch and push URLs are incomplete",)
    elif details["embedded_userinfo"]:
        status = CheckStatus.WARNING
        evidence = ("Git origin URL contains embedded user information",)
    else:
        status = CheckStatus.PASS
        evidence = ("Git origin fetch and push URLs are readable",)
    github_remote = (
        True
        if fetch_state == "parsed"
        and push_state == "parsed"
        and fetch_details["host_class"] == "github.com"
        and push_details["host_class"] == "github.com"
        else False
        if fetch_state == "parsed" and push_state == "parsed"
        else None
    )
    return (
        CheckResult(
            id="git.remote.origin",
            status=status,
            summary="Git origin remote is readable"
            if status is CheckStatus.PASS
            else "Git origin remote needs attention",
            evidence=evidence,
            details=details,
        ),
        details,
        github_remote,
    )


def _reduce_remote(
    execution: CommandExecution,
) -> tuple[str, dict[str, Any], tuple[str, ...] | None]:
    if not execution.succeeded:
        details = _empty_remote(configured=False)
        if execution.error or execution.timed_out or execution.returncode not in (1,):
            return "unknown", details, None
        return "missing", details, None
    line = _first_nonempty(execution.stdout)
    if not line:
        return "missing", _empty_remote(configured=False), None
    lines = [item.strip() for item in execution.stdout.splitlines() if item.strip()]
    if len(lines) != 1:
        return "malformed", _empty_remote(configured=True), None
    parsed = _parse_remote(lines[0])
    if parsed is None:
        return "malformed", _empty_remote(configured=True), None
    return "parsed", parsed[0], parsed[1]


def _empty_remote(*, configured: bool) -> dict[str, Any]:
    return {
        "configured": configured,
        "transport": "unknown",
        "host_class": "unknown",
        "embedded_userinfo": False,
    }


def _parse_remote(value: str) -> tuple[dict[str, Any], tuple[str, ...]] | None:
    text = value.strip()
    if not text:
        return None
    if _looks_like_local_path(text):
        return _local_remote(text)
    if any(char.isspace() for char in text):
        return None
    if "://" in text:
        try:
            parsed = urlsplit(text)
            hostname = parsed.hostname
        except ValueError:
            return None
        scheme = parsed.scheme.casefold()
        if scheme in {"file", "local"}:
            return _local_remote(parsed.path or text)
        if scheme not in {"http", "https", "ssh", "git+ssh"} or not hostname:
            return None
        path = parsed.path.strip("/")
        if not path:
            return None
        transport = "ssh" if scheme in {"ssh", "git+ssh"} else scheme
        host_class = "github.com" if hostname.casefold() == "github.com" else "other"
        if scheme in {"ssh", "git+ssh"}:
            embedded_userinfo = parsed.password is not None
        else:
            embedded_userinfo = parsed.username is not None or parsed.password is not None
        details = {
            "configured": True,
            "transport": transport,
            "host_class": host_class,
            "embedded_userinfo": embedded_userinfo,
        }
        port = ""
        try:
            if parsed.port is not None:
                port = str(parsed.port)
        except ValueError:
            return None
        return details, ("host", hostname.casefold(), port, _normalize_repo_path(path))
    match = _SCP_REMOTE.fullmatch(text)
    if match:
        host = match.group("host")
        path = match.group("path")
        if not path:
            return None
        details = {
            "configured": True,
            "transport": "ssh",
            "host_class": "github.com" if host.casefold() == "github.com" else "other",
            "embedded_userinfo": False,
        }
        return details, ("host", host.casefold(), "", _normalize_repo_path(path))
    return None


def _looks_like_local_path(value: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", value)
        or value.startswith(("\\\\", "/", "./", "../", "~/"))
    )


def _local_remote(value: str) -> tuple[dict[str, Any], tuple[str, ...]]:
    normalized = ntpath.normcase(value.replace("/", "\\"))
    return (
        {
            "configured": True,
            "transport": "local",
            "host_class": "local",
            "embedded_userinfo": False,
        },
        ("local", normalized),
    )


def _normalize_repo_path(value: str) -> str:
    path = value.strip("/").casefold()
    return path[:-4] if path.endswith(".git") else path


def _credential_helper_check(
    execution: CommandExecution, origin_details: dict[str, Any]
) -> CheckResult:
    helper_details, helper_known = _reduce_helper(execution)
    details = {**helper_details, "credentials_verified": False}
    transports = {
        origin_details.get("fetch", {}).get("transport"),
        origin_details.get("push", {}).get("transport"),
    }
    if "unknown" in transports:
        return _unknown_check(
            "git.credential_helper", "origin transport was not classified", details
        )
    if "https" in transports:
        if not helper_known:
            return _unknown_check(
                "git.credential_helper", "credential helper could not be read", details
            )
        if helper_details["gcm_detected"]:
            return CheckResult(
                id="git.credential_helper",
                status=CheckStatus.PASS,
                summary="HTTPS credential helper is configured",
                evidence=("Git Credential Manager was detected",),
                details=details,
            )
        return CheckResult(
            id="git.credential_helper",
            status=CheckStatus.WARNING,
            summary="HTTPS credential helper needs attention",
            evidence=("Git Credential Manager was not detected",),
            details=details,
        )
    return CheckResult(
        id="git.credential_helper",
        status=CheckStatus.PASS,
        summary="Git credential helper is not applicable",
        evidence=("origin transport does not require HTTPS helper",),
        details=details,
    )


def _reduce_helper(execution: CommandExecution) -> tuple[dict[str, Any], bool]:
    if execution.error or execution.timed_out or execution.returncode not in (0, 1):
        return {
            "configured": False,
            "gcm_detected": False,
            "helper_count": 0,
        }, False
    lines = [line.strip() for line in execution.stdout.splitlines() if line.strip()]
    return {
        "configured": bool(lines),
        "gcm_detected": any(_is_gcm_helper(line) for line in lines),
        "helper_count": len(lines),
    }, True


def _is_gcm_helper(value: str) -> bool:
    lowered = value.casefold()
    return "manager-core" in lowered or lowered in {
        "manager",
        "manager-core",
        "git-credential-manager",
        "git credential-manager",
    }


def _dependency_check(check_id: str) -> CheckResult:
    return _unknown_check(check_id, "dependency check was not run")


def _unknown_check(
    check_id: str, reason: str, details: Mapping[str, Any] | None = None
) -> CheckResult:
    return CheckResult(
        id=check_id,
        status=CheckStatus.UNKNOWN,
        summary="Git check is unavailable",
        evidence=(reason,),
        details=dict(details or {}),
    )


def _not_applicable_check(check_id: str, reason: str) -> CheckResult:
    return CheckResult(
        id=check_id,
        status=CheckStatus.PASS,
        summary="GitHub check is not applicable",
        evidence=(reason,),
        details={"not_applicable": True},
    )


def _first_nonempty(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


def _first_nonempty_raw(value: str) -> str:
    return next((line for line in value.splitlines() if line.strip()), "")

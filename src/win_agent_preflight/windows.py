"""Windows command discovery and read-only platform fact collection."""

from __future__ import annotations

import ntpath
import os
import re
import shutil
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

try:
    import winreg
except ImportError:  # pragma: no cover - exercised on non-Windows Python builds.
    winreg = None  # type: ignore[assignment]

from .models import CheckResult, CheckStatus, CommandCandidate
from .runner import CommandExecution, Runner

DEFAULT_PATHEXT = (
    ".COM",
    ".EXE",
    ".BAT",
    ".CMD",
    ".VBS",
    ".VBE",
    ".JS",
    ".JSE",
    ".WSF",
    ".WSH",
    ".MSC",
)
SCRIPT_COMMANDS = frozenset({"npm", "pnpm", "npx", "yarn"})
AGENT_LAUNCHER_EXTENSIONS = (".exe", ".cmd", ".bat", ".ps1")
REGISTRY_SCOPES = ("machine", "user")
RegistryScope = Literal["machine", "user"]
_REGISTRY_SUBKEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
_USER_REGISTRY_SUBKEY = r"Environment"
_VARIABLE_PATTERN = re.compile(r"%([^%]+)%")
_MAX_PATH_EXPANSION_ROUNDS = 8
_REG_SZ = getattr(winreg, "REG_SZ", 1)
_REG_EXPAND_SZ = getattr(winreg, "REG_EXPAND_SZ", 2)
_ALLOWED_REGISTRY_TYPES = frozenset({_REG_SZ, _REG_EXPAND_SZ})


class RegistryValueReader(Protocol):
    """Read string environment values for one registry scope.

    Implementations receive ``machine`` or ``user`` and return the values from
    that scope.  Returning a mapping lets PATH expansion use the same
    precedence as Windows (user, machine, then process); a string is also
    accepted by the collector as a PATH-only test double.
    """

    def __call__(self, scope: RegistryScope) -> Mapping[str, object] | str | None: ...


@dataclass(frozen=True, slots=True)
class RegistryPathFacts:
    """Immutable PATH values and completeness facts from HKLM/HKCU.

    An absent registry key or ``Path`` value is represented by an empty string
    and remains a complete fact.  Exceptions and a non-string ``Path`` value
    set the corresponding completeness flag to ``False``; the diagnostic layer
    can then distinguish a proven empty PATH from an unavailable observation.
    ``*_values`` contain only string environment values and are used for
    case-insensitive ``%NAME%`` expansion.
    """

    machine_path: str = ""
    user_path: str = ""
    machine_complete: bool = True
    user_complete: bool = True
    machine_error: str | None = None
    user_error: str | None = None
    machine_values: tuple[tuple[str, str], ...] = ()
    user_values: tuple[tuple[str, str], ...] = ()

    @property
    def complete(self) -> bool:
        return self.machine_complete and self.user_complete

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(
            error
            for error in (self.machine_error, self.user_error)
            if error
        )

    def values_for(self, scope: RegistryScope) -> Mapping[str, str]:
        values = self.machine_values if scope == "machine" else self.user_values
        return dict(values)


@dataclass(frozen=True, slots=True)
class _RegistryScopeFact:
    path: str
    complete: bool
    error: str | None
    values: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _RegistryValue:
    """Internal winreg value carrying the type needed for validation."""

    value: object
    value_type: int


@dataclass(frozen=True, slots=True)
class _PathEntry:
    source: str
    value: str
    display: str
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandPathError:
    """Structured evidence for a path that could not be inspected."""

    path: str
    error_type: str
    winerror: int | None = None


@dataclass(frozen=True, slots=True)
class AgentCommandDiscovery:
    """Agent launcher paths found without executing any command."""

    candidates: tuple[CommandCandidate, ...] = ()
    non_executable_paths: tuple[str, ...] = ()
    inaccessible_paths: tuple[CommandPathError, ...] = ()


def redact_text(value: str, *, user_profile: str | None = None) -> str:
    """Replace the current user's home directory without exposing its name."""

    if not value:
        return value
    profile = user_profile or os.environ.get("USERPROFILE")
    if not profile:
        return value
    normalized_profile = profile.rstrip("\\/")
    if not normalized_profile:
        return value
    profile_parts = re.split(r"[\\/]", normalized_profile)
    profile_pattern = r"[\\/]".join(re.escape(part) for part in profile_parts)
    profile_pattern += r"(?=$|[\\/])"
    return re.sub(profile_pattern, "%USERPROFILE%", value, flags=re.IGNORECASE)


def discover_command(
    name: str,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
) -> tuple[CommandCandidate, ...]:
    """Return all existing PATH candidates in search order.

    Discovery is deliberately filesystem-only. It never treats discovery as
    proof that a command can start; the caller must use ``Runner`` for that.
    """

    environment = env if env is not None else os.environ
    path_value = environment.get("PATH", "")
    path_separator = ";" if os.name == "nt" else os.pathsep
    pathext = tuple(
        extension.upper()
        for extension in environment.get("PATHEXT", "").split(";")
        if extension
    ) or DEFAULT_PATHEXT
    explicit_extension = bool(Path(name).suffix)
    names = [name]
    if not explicit_extension:
        names.extend(f"{name}{extension.lower()}" for extension in pathext)
        if name.lower() in SCRIPT_COMMANDS:
            names.append(f"{name}.ps1")

    candidates: list[CommandCandidate] = []
    seen: set[str] = set()
    for raw_directory in path_value.split(path_separator):
        directory = raw_directory.strip().strip('"')
        if not directory:
            continue
        for candidate_name in names:
            candidate_path = Path(directory) / candidate_name
            try:
                is_file = candidate_path.is_file()
            except OSError:
                # WindowsApps execution aliases and inaccessible PATH entries can
                # fail stat() even though their names are visible. One broken
                # candidate must not abort discovery of the remaining PATH.
                continue
            if not is_file:
                continue
            key = os.path.normcase(str(candidate_path))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                CommandCandidate(
                    name=name,
                    path=redact_text(str(candidate_path), user_profile=user_profile),
                )
            )
    if not candidates and os.name != "nt":
        found = shutil.which(name, path=path_value)
        if found:
            candidates.append(
                CommandCandidate(name=name, path=redact_text(found, user_profile=user_profile))
            )
    return tuple(candidates)


def discover_agent_command_details(
    name: str,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
) -> AgentCommandDiscovery:
    """Resolve known agent launchers without starting them.

    Agent names are intentionally checked against only the four Windows
    launcher forms used by this project.  ``lstat`` is used so an inaccessible
    WindowsApps alias is retained as structured evidence instead of being
    silently classified as a missing command.
    """

    environment = env if env is not None else os.environ
    path_separator = ";" if os.name == "nt" else os.pathsep
    path_value = environment.get("PATH", "")
    extensions = _agent_launcher_extensions(environment.get("PATHEXT", ""))
    candidates: list[CommandCandidate] = []
    non_executable: list[str] = []
    inaccessible: list[CommandPathError] = []
    seen: set[str] = set()

    for raw_directory in path_value.split(path_separator):
        directory = raw_directory.strip().strip('"')
        if not directory:
            continue
        directory_path = Path(directory)
        try:
            os.lstat(directory_path)
        except OSError as exc:
            if _is_missing_path_error(exc):
                continue
            inaccessible.append(_path_error(directory_path, exc, user_profile=user_profile))
            continue

        for extension in extensions:
            candidate_path = directory_path / f"{name}{extension.lower()}"
            display_path = redact_text(str(candidate_path), user_profile=user_profile)
            key = os.path.normcase(str(candidate_path))
            if key in seen:
                continue
            try:
                info = os.lstat(candidate_path)
            except OSError as exc:
                if _is_missing_path_error(exc):
                    continue
                inaccessible.append(_path_error(candidate_path, exc, user_profile=user_profile))
                continue
            seen.add(key)
            if not stat.S_ISREG(info.st_mode):
                non_executable.append(display_path)
                continue
            candidates.append(
                CommandCandidate(name=name, path=display_path, source="PATH")
            )

    return AgentCommandDiscovery(
        candidates=tuple(candidates),
        non_executable_paths=tuple(non_executable),
        inaccessible_paths=tuple(inaccessible),
    )


def discover_agent_command(
    name: str,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
) -> tuple[CommandCandidate, ...]:
    """Return only regular agent launcher candidates in PATH order."""

    return discover_agent_command_details(
        name, env=env, user_profile=user_profile
    ).candidates


def _agent_launcher_extensions(pathext: str) -> tuple[str, ...]:
    requested = tuple(
        f".{item.strip().lstrip('.').lower()}"
        for item in pathext.split(";")
        if item.strip()
    )
    ordered: list[str] = []
    for extension in (*requested, *AGENT_LAUNCHER_EXTENSIONS):
        if extension in AGENT_LAUNCHER_EXTENSIONS and extension not in ordered:
            ordered.append(extension)
    return tuple(ordered)


def _is_missing_path_error(exc: OSError) -> bool:
    return isinstance(exc, FileNotFoundError) or getattr(exc, "winerror", None) in (2, 3)


def _path_error(path: Path, exc: OSError, *, user_profile: str | None) -> CommandPathError:
    return CommandPathError(
        path=redact_text(str(path), user_profile=user_profile),
        error_type=type(exc).__name__,
        winerror=getattr(exc, "winerror", None),
    )


class _WinregValueReader:
    """Read one Windows environment registry scope without writing it."""

    def __call__(self, scope: RegistryScope) -> Mapping[str, object]:
        if winreg is None:
            raise OSError("winreg is unavailable on this Python platform")
        if scope == "machine":
            root = winreg.HKEY_LOCAL_MACHINE
            subkey = _REGISTRY_SUBKEY
        elif scope == "user":
            root = winreg.HKEY_CURRENT_USER
            subkey = _USER_REGISTRY_SUBKEY
        else:  # pragma: no cover - RegistryScope keeps this unreachable for callers.
            raise ValueError(f"unsupported registry scope: {scope}")

        try:
            key = winreg.OpenKey(root, subkey, 0, winreg.KEY_READ)
        except FileNotFoundError:
            # A missing registry key is a known empty scope, not an
            # unavailable observation.
            return {}
        with key:
            # QueryInfoKey gives us a bounded enumeration.  This avoids
            # mistaking an enumeration failure halfway through a key for
            # the normal end-of-key condition.
            value_count = winreg.QueryInfoKey(key)[1]
            values: dict[str, object] = {}
            for index in range(value_count):
                name, value, value_type = winreg.EnumValue(key, index)
                values[str(name)] = _RegistryValue(value, value_type)
            return values


DEFAULT_REGISTRY_VALUE_READER: RegistryValueReader = _WinregValueReader()


def collect_registry_path_facts(
    *, reader: RegistryValueReader | Mapping[str, object] | None = None
) -> RegistryPathFacts:
    """Read HKLM/HKCU environment values into immutable facts.

    The default reader only opens the two environment keys with ``KEY_READ``.
    A missing key or ``Path`` value is a complete empty observation.  Any
    other read exception, or a non-string ``Path`` value, is retained as an
    incomplete scope fact so callers never silently treat an error as empty.
    ``reader`` is intentionally injectable for deterministic tests.
    """

    active_reader = reader if reader is not None else DEFAULT_REGISTRY_VALUE_READER
    scope_facts = {
        scope: _read_registry_scope(active_reader, scope) for scope in REGISTRY_SCOPES
    }
    machine = scope_facts["machine"]
    user = scope_facts["user"]
    return RegistryPathFacts(
        machine_path=machine.path,
        user_path=user.path,
        machine_complete=machine.complete,
        user_complete=user.complete,
        machine_error=machine.error,
        user_error=user.error,
        machine_values=machine.values,
        user_values=user.values,
    )


# Keep a short read-oriented alias for callers that prefer noun-style APIs.
read_registry_path_facts = collect_registry_path_facts


def _read_registry_scope(
    reader: RegistryValueReader | Mapping[str, object], scope: RegistryScope
) -> _RegistryScopeFact:
    try:
        if isinstance(reader, Mapping):
            # Mapping test doubles may be either {scope: {Path: ...}} or
            # {scope: "PATH"}.  The latter mirrors a PATH-only reader.
            raw_scope = reader.get(scope)
        else:
            raw_scope = reader(scope)
    except Exception as exc:
        return _RegistryScopeFact(
            path="",
            complete=False,
            error=f"{scope} registry read failed ({type(exc).__name__})",
            values=(),
        )

    if raw_scope is None:
        return _RegistryScopeFact(path="", complete=True, error=None, values=())
    if isinstance(raw_scope, str):
        return _RegistryScopeFact(path=raw_scope, complete=True, error=None, values=())
    if not isinstance(raw_scope, Mapping):
        return _RegistryScopeFact(
            path="",
            complete=False,
            error=f"{scope} registry values are not a mapping",
            values=(),
        )

    path_value: object | None = None
    path_present = False
    path_type_invalid = False
    string_values: list[tuple[str, str]] = []
    for raw_name, raw_value in raw_scope.items():
        name = str(raw_name)
        value, value_type = _registry_value_parts(raw_value)
        is_string_type = value_type is None or value_type in _ALLOWED_REGISTRY_TYPES
        if name.casefold() == "path":
            path_present = True
            path_value = value
            path_type_invalid = not is_string_type or not isinstance(value, str)
        if is_string_type and isinstance(value, str):
            string_values.append((name, value))

    if not path_present:
        return _RegistryScopeFact(
            path="",
            complete=True,
            error=None,
            values=tuple(string_values),
        )
    if path_type_invalid:
        return _RegistryScopeFact(
            path="",
            complete=False,
            error=f"{scope} registry Path value has an unsupported type or is not a string",
            values=tuple(string_values),
        )
    return _RegistryScopeFact(
        path=path_value,
        complete=True,
        error=None,
        values=tuple(string_values),
    )


def _registry_value_parts(raw_value: object) -> tuple[object, int | None]:
    if isinstance(raw_value, _RegistryValue):
        return raw_value.value, raw_value.value_type
    # Keep a convenient, dependency-free injection form for tests that need
    # to model winreg's ``(value, value_type)`` metadata explicitly.  Existing
    # bare string mappings continue to work unchanged.
    if (
        isinstance(raw_value, tuple)
        and len(raw_value) == 2
        and isinstance(raw_value[1], int)
    ):
        return raw_value[0], raw_value[1]
    return raw_value, None


def expand_registry_path(
    value: str,
    *,
    scope: RegistryScope,
    facts: RegistryPathFacts,
    process_env: Mapping[str, str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Expand ``%NAME%`` at most eight rounds and return unresolved names.

    Lookup is case-insensitive.  Machine PATH uses machine then process
    values; user PATH uses user, machine, then process values.  The returned
    unresolved tuple contains names only, never the value of a variable.
    """

    process_values = process_env if process_env is not None else os.environ
    machine_values = _casefold_values(facts.machine_values)
    user_values = _casefold_values(facts.user_values)
    process_values_folded = {str(key).casefold(): value for key, value in process_values.items()}
    if scope == "machine":
        sources = (machine_values, process_values_folded)
    else:
        sources = (user_values, machine_values, process_values_folded)

    unresolved: dict[str, str] = {}
    current = value
    for _ in range(_MAX_PATH_EXPANSION_ROUNDS):
        before = current
        changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            name = match.group(1)
            variable = name.casefold()
            replacement: str | None = None
            for source in sources:
                if variable in source:
                    candidate = source[variable]
                    if isinstance(candidate, str):
                        replacement = candidate
                    break
            if replacement is None:
                unresolved.setdefault(variable, name)
                return match.group(0)
            changed = True
            return replacement

        expanded = _VARIABLE_PATTERN.sub(replace, current)
        current = expanded
        if not changed or expanded == before:
            break

    # A variable can be introduced by a replacement in the last round, so
    # inspect the final text once more.  Only names are retained for evidence.
    for match in _VARIABLE_PATTERN.finditer(current):
        unresolved.setdefault(match.group(1).casefold(), match.group(1))
    return current, tuple(unresolved[key] for key in sorted(unresolved))


def _casefold_values(values: Sequence[tuple[str, str]]) -> dict[str, str]:
    return {name.casefold(): value for name, value in values}


def collect_path_refresh_check(
    *,
    process_path: str | None = None,
    process_env: Mapping[str, str] | None = None,
    user_path: str | None = None,
    user_profile: str | None = None,
    registry_reader: RegistryValueReader | Mapping[str, object] | None = None,
    registry_facts: RegistryPathFacts | None = None,
) -> CheckResult:
    """Compare read-only registry PATH facts with the current process PATH.

    ``user_path`` remains an explicit test injection and takes precedence over
    the user registry value.  The default Windows path reads HKLM and HKCU;
    this function never writes registry state and never returns ``fail``.
    """

    if process_path is None:
        process_values = process_env if process_env is not None else os.environ
        process_path = process_values.get("PATH")
    if os.name != "nt":
        return CheckResult(
            id="windows.path_refresh",
            status=CheckStatus.UNKNOWN,
            summary="当前平台不是 Windows，无法读取注册表 PATH",
            evidence=("registry PATH comparison is Windows-only",),
        )
    if not process_path:
        return CheckResult(
            id="windows.path_refresh",
            status=CheckStatus.UNKNOWN,
            summary="无法获得当前进程 PATH，不能比较注册表 PATH",
            evidence=("process PATH is missing or empty",),
        )

    facts = registry_facts
    if facts is None:
        if user_path is not None and registry_reader is None:
            # Preserve the original injection boundary without touching the
            # real registry in existing tests or embedding applications.
            facts = RegistryPathFacts(user_path=user_path)
        else:
            facts = collect_registry_path_facts(reader=registry_reader)
            if user_path is not None:
                facts = RegistryPathFacts(
                    machine_path=facts.machine_path,
                    user_path=user_path,
                    machine_complete=facts.machine_complete,
                    user_complete=True,
                    machine_error=facts.machine_error,
                    machine_values=facts.machine_values,
                    user_values=facts.user_values,
                )
    elif user_path is not None:
        facts = RegistryPathFacts(
            machine_path=facts.machine_path,
            user_path=user_path,
            machine_complete=facts.machine_complete,
            user_complete=True,
            machine_error=facts.machine_error,
            machine_values=facts.machine_values,
            user_values=facts.user_values,
        )

    current = {
        _canonical_windows_path(item)
        for item in process_path.split(";")
        if _canonical_windows_path(item)
    }
    configured: list[_PathEntry] = []
    unresolved: dict[str, str] = {}
    for source, raw_path in (("machine", facts.machine_path), ("user", facts.user_path)):
        if not raw_path:
            continue
        for raw_item in raw_path.split(";"):
            display = raw_item.strip()
            if not display:
                continue
            expanded, unresolved_names = expand_registry_path(
                display,
                scope="machine" if source == "machine" else "user",
                facts=facts,
                process_env=process_env,
            )
            for name in unresolved_names:
                unresolved.setdefault(name.casefold(), name)
            if unresolved_names:
                # Do not compare this partially expanded item.  Other PATH
                # entries remain independently comparable.
                continue
            cleaned = expanded.strip()
            if cleaned:
                # Keep the raw expression for evidence.  In particular, a
                # resolved private variable must never expose its value.
                configured.append(
                    _PathEntry(source=source, value=cleaned, display=display)
                )

    missing: list[_PathEntry] = []
    seen_missing: set[str] = set()
    for entry in configured:
        key = _canonical_windows_path(entry.value)
        if key and key not in current and key not in seen_missing:
            seen_missing.add(key)
            missing.append(entry)

    incomplete_scopes = [
        (scope, error)
        for scope, complete, error in (
            ("machine", facts.machine_complete, facts.machine_error),
            ("user", facts.user_complete, facts.user_error),
        )
        if not complete
    ]
    evidence: list[str] = []
    if missing:
        shown = ", ".join(
            f"{entry.source}: {redact_text(entry.display, user_profile=user_profile)}"
            for entry in missing[:5]
        )
        evidence.append(
            f"current process is missing {len(missing)} configured PATH entries: {shown}"
        )
    if unresolved:
        evidence.append(
            "unresolved registry PATH variables: "
            + ", ".join(unresolved[key] for key in sorted(unresolved))
        )
    if incomplete_scopes:
        evidence.extend(
            f"{scope} registry PATH fact is incomplete"
            + (f": {error}" if error else "")
            for scope, error in incomplete_scopes
        )
    if missing:
        summary = "注册表 PATH 中存在当前进程尚未继承的目录"
        if incomplete_scopes or unresolved:
            summary += "（同时存在未完整采集的 PATH 事实）"
        return CheckResult(
            id="windows.path_refresh",
            status=CheckStatus.WARNING,
            summary=summary,
            evidence=tuple(evidence),
            details={"missing_count": len(missing)},
        )
    if unresolved or incomplete_scopes:
        return CheckResult(
            id="windows.path_refresh",
            status=CheckStatus.UNKNOWN,
            summary="注册表 PATH 事实不完整，无法确认继承状态",
            evidence=tuple(evidence),
        )
    return CheckResult(
        id="windows.path_refresh",
        status=CheckStatus.PASS,
        summary="当前进程 PATH 已包含注册表 PATH 中的目录",
    )


def _canonical_windows_path(value: str) -> str:
    cleaned = str(value).strip().strip('"').strip("'").strip()
    if not cleaned:
        return ""
    normalized = ntpath.normpath(cleaned.replace("/", "\\"))
    if normalized == "." and cleaned != ".":
        normalized = cleaned
    return normalized.casefold()


def collect_powershell_check(
    runner: Runner,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> CheckResult:
    """Collect execution-policy facts without changing policy."""

    candidates = discover_command("pwsh", env=env, user_profile=user_profile)
    candidates += discover_command("powershell.exe", env=env, user_profile=user_profile)
    if not candidates:
        return CheckResult(
            id="windows.powershell.execution_policy",
            status=CheckStatus.UNKNOWN,
            summary="未发现 PowerShell，无法采集执行策略",
            evidence=("pwsh and powershell.exe were not found in PATH",),
        )
    selected = candidates[0]
    execution = runner.run(
        (
            selected.path.replace(
                "%USERPROFILE%",
                user_profile or os.environ.get("USERPROFILE", "%USERPROFILE%"),
            ),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-ExecutionPolicy -List | ForEach-Object { "
            "[pscustomobject]@{Scope=$_.Scope.ToString(); "
            "ExecutionPolicy=$_.ExecutionPolicy.ToString()} } | "
            "ConvertTo-Json -Compress",
        ),
        timeout=timeout,
        env=env,
    )
    evidence = _execution_evidence(execution, user_profile=user_profile)
    if execution.timed_out or execution.error:
        return CheckResult(
            id="windows.powershell.execution_policy",
            status=CheckStatus.FAIL,
            summary="PowerShell 执行策略采集未能在超时内完成",
            evidence=evidence,
        )
    if execution.returncode != 0:
        return CheckResult(
            id="windows.powershell.execution_policy",
            status=CheckStatus.FAIL,
            summary="PowerShell 执行策略命令返回失败",
            evidence=evidence,
        )
    return CheckResult(
        id="windows.powershell.execution_policy",
        status=CheckStatus.PASS,
        summary="已采集 PowerShell 执行策略（未修改）",
        evidence=(
            redact_text(execution.stdout.strip(), user_profile=user_profile) or "命令返回空结果",
        ),
        details={"shell": selected.path},
    )


def collect_powershell_command_check(
    runner: Runner,
    *,
    command: str,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> CheckResult:
    """Check how a bare command resolves inside a clean PowerShell process.

    This is intentionally separate from PATH candidate checks. For example,
    ``npm`` can have a working ``npm.cmd`` candidate while PowerShell still
    resolves the bare command to a policy-blocked ``npm.ps1``.
    """

    candidates = discover_command("pwsh", env=env, user_profile=user_profile)
    candidates += discover_command("powershell.exe", env=env, user_profile=user_profile)
    check_id = f"powershell.command.{command}"
    if not candidates:
        return CheckResult(
            id=check_id,
            status=CheckStatus.UNKNOWN,
            summary=f"未发现 PowerShell，无法验证裸命令：{command}",
            evidence=("pwsh and powershell.exe were not found in PATH",),
        )

    selected = candidates[0]
    shell_path = selected.path.replace(
        "%USERPROFILE%", user_profile or os.environ.get("USERPROFILE", "")
    )
    execution = runner.run(
        (
            shell_path,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Get-Command {command} -ErrorAction Stop | Out-Null; {command} --version",
        ),
        timeout=timeout,
        env=env,
    )
    if execution.succeeded:
        output = execution.stdout.strip() or execution.stderr.strip() or "started"
        return CheckResult(
            id=check_id,
            status=CheckStatus.PASS,
            summary=f"PowerShell 裸命令可启动：{command}",
            evidence=(f"shell: {selected.path}", redact_text(output, user_profile=user_profile)),
            details={"shell": selected.path, "command": command},
        )
    evidence = _execution_evidence(execution, user_profile=user_profile)
    return CheckResult(
        id=check_id,
        status=CheckStatus.WARNING,
        summary=f"PowerShell 裸命令无法启动：{command}",
        evidence=(f"shell: {selected.path}", *evidence),
        details={"shell": selected.path, "command": command},
    )


def run_candidate(
    candidate: CommandCandidate,
    runner: Runner,
    *,
    env: Mapping[str, str] | None = None,
    user_profile: str | None = None,
    timeout: float = 5.0,
) -> CommandExecution:
    """Start a candidate, routing PowerShell scripts through PowerShell."""

    raw_path = candidate.path.replace(
        "%USERPROFILE%", user_profile or os.environ.get("USERPROFILE", "")
    )
    if raw_path.lower().endswith(".ps1"):
        shell = discover_command("pwsh", env=env, user_profile=user_profile)
        if not shell:
            shell = discover_command("powershell.exe", env=env, user_profile=user_profile)
        if not shell:
            return CommandExecution(
                argv=(raw_path,),
                returncode=None,
                error="PowerShell host was not found for .ps1 candidate",
            )
        escaped = raw_path.replace("'", "''")
        argv: Sequence[str] = (
            shell[0].path.replace(
                "%USERPROFILE%", user_profile or os.environ.get("USERPROFILE", "")
            ),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"& '{escaped}' --version",
        )
    else:
        argv = (raw_path, "--version")
    return runner.run(argv, timeout=timeout, env=env)


def _execution_evidence(
    execution: CommandExecution, *, user_profile: str | None
) -> tuple[str, ...]:
    evidence: list[str] = []
    if execution.error:
        evidence.append(redact_text(execution.error, user_profile=user_profile))
    if execution.returncode is not None and execution.returncode != 0:
        evidence.append(f"exit code: {execution.returncode}")
    if execution.stderr.strip():
        evidence.append(redact_text(execution.stderr.strip()[:500], user_profile=user_profile))
    if execution.timed_out and not evidence:
        evidence.append("external command timed out")
    return tuple(evidence) or ("external command returned no usable output",)

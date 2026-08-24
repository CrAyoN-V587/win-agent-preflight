"""A deliberately small, Windows-only write/rename/delete capability probe.

The probe is intentionally separate from :mod:`models` and the scan schema.
It writes only a newly-created direct child of the user-selected directory and
revalidates recorded Windows object identities before path-based cleanup.  It
must never be used as a general workspace cleaner.  The checks are deliberately
non-adversarial: another process must not replace probe entries between the
identity check and the following filesystem operation.
"""

from __future__ import annotations

import os
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CheckResult, CheckStatus
from .windows import redact_text

WORKSPACE_PROBE_SCHEMA_VERSION = 1
WORKSPACE_PROBE_TOOL = "win-agent-preflight"
WORKSPACE_PROBE_KIND = "workspace_probe"
WORKSPACE_PROBE_CHECK_IDS = (
    "workspace.create_directory",
    "workspace.write_file",
    "workspace.read_file",
    "workspace.rename_file",
    "workspace.delete_file",
    "workspace.cleanup",
)
PROBE_CONTENT_PREFIX = "win-agent-preflight workspace probe v1"
PROBE_AFTER_NAME = "after.txt"
PROBE_BEFORE_NAME = "before.txt"
_REPARSE_POINT = 0x400
_MAX_EXCEPTION_MESSAGE = 240
ObjectIdentity = tuple[int, int]


class WorkspaceProbeInputError(ValueError):
    """The requested target or write authorization cannot be accepted."""


class WorkspaceProbeInterrupted(KeyboardInterrupt):
    """A Ctrl-C carrying the partial report produced after bounded cleanup."""

    def __init__(self, report: WorkspaceProbeReport) -> None:
        self.report = report
        super().__init__("workspace probe interrupted")


class WorkspaceProbeUnexpectedError(RuntimeError):
    """Unexpected probe exception carrying the report built before re-raising."""

    def __init__(self, report: WorkspaceProbeReport, cause: BaseException) -> None:
        self.report = report
        self.cause = cause
        super().__init__(str(cause))


class WorkspaceOperations:
    """Minimal filesystem boundary used by the probe.

    Tests and embedding applications can provide an object with the same
    methods instead of touching the real filesystem.  No method recursively
    walks a directory and no method changes system configuration.
    """

    def lstat(self, path: Path) -> os.stat_result:
        return path.lstat()

    def mkdir(self, path: Path) -> None:
        path.mkdir()

    def write_text_exclusive(self, path: Path, text: str) -> None:
        # Exclusive creation prevents an existing entry from being overwritten.
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def rename(self, source: Path, destination: Path) -> None:
        source.rename(destination)

    def unlink(self, path: Path) -> None:
        path.unlink()

    def rmdir(self, path: Path) -> None:
        path.rmdir()


@dataclass(frozen=True, slots=True)
class WorkspaceProbeReport:
    """Independent v1 report for one bounded workspace probe invocation."""

    schema_version: int
    tool: str
    kind: str
    target: str
    successful: bool
    checks: tuple[CheckResult, ...]
    residual_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != WORKSPACE_PROBE_SCHEMA_VERSION:
            raise ValueError("unsupported workspace probe schema version")
        if self.tool != WORKSPACE_PROBE_TOOL or self.kind != WORKSPACE_PROBE_KIND:
            raise ValueError("invalid workspace probe identity")
        if len(self.checks) != len(WORKSPACE_PROBE_CHECK_IDS):
            raise ValueError("workspace probe must contain exactly six checks")
        if tuple(check.id for check in self.checks) != WORKSPACE_PROBE_CHECK_IDS:
            raise ValueError("workspace probe checks are out of order")
        if not isinstance(self.successful, bool):
            raise ValueError("workspace probe successful must be a boolean")
        if any(
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or path.replace("\\", "/").startswith("../")
            or path.replace("\\", "/") == ".."
            for path in self.residual_paths
        ):
            raise ValueError("workspace probe residual_paths must be relative")
        expected_success = all(
            check.status is CheckStatus.PASS for check in self.checks
        ) and not self.residual_paths
        if self.successful != expected_success:
            raise ValueError(
                "workspace probe successful conflicts with checks or residual_paths"
            )

    @property
    def failed(self) -> bool:
        return any(check.status is CheckStatus.FAIL for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in CheckStatus}
        for check in self.checks:
            counts[check.status.value] += 1
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "kind": self.kind,
            "target": self.target,
            "successful": self.successful,
            "summary": counts,
            "checks": [check.to_dict() for check in self.checks],
            "residual_paths": list(self.residual_paths),
        }


def run_workspace_probe(
    target: Path | str,
    *,
    allow_write: bool = False,
    operations: WorkspaceOperations | Any | None = None,
    token_factory: Callable[[], object] | None = None,
    user_profile: str | None = None,
) -> WorkspaceProbeReport:
    """Run the six-step probe and always attempt bounded cleanup.

    Input validation happens before the first write.  Expected filesystem
    failures become ``fail`` results and dependent steps become ``unknown``;
    unexpected exceptions are re-raised only after cleanup.  ``KeyboardInterrupt``
    is represented in the returned partial report so the CLI can render it and
    return the conventional 130 exit code.
    """

    if os.name != "nt":
        raise WorkspaceProbeInputError("workspace-probe is supported on Windows only")
    if not allow_write:
        raise WorkspaceProbeInputError("workspace-probe requires --allow-write")

    ops = operations if operations is not None else WorkspaceOperations()
    target_path = Path(target)
    resolved_target = _validate_target(ops, target_path, user_profile=user_profile)
    token_source = token_factory if token_factory is not None else (lambda: uuid.uuid4().hex)
    token = _safe_token(token_source())
    probe_name = f".agent-preflight-probe-{token}"
    probe_content = f"{PROBE_CONTENT_PREFIX} {token}\n"
    probe_dir = resolved_target / probe_name
    before = probe_dir / PROBE_BEFORE_NAME
    after = probe_dir / PROBE_AFTER_NAME

    # A token collision must never make us touch a pre-existing entry.
    try:
        collision = _path_exists(ops, probe_dir)
    except (OSError, UnicodeError) as exc:
        raise WorkspaceProbeInputError(
            "cannot verify generated probe directory: "
            + _exception_text(exc, user_profile=user_profile)
        ) from exc
    if collision:
        raise WorkspaceProbeInputError(
            "generated probe directory already exists; choose another token"
        )

    checks: list[CheckResult] = []
    probe_created = False
    probe_owned = False
    probe_identity: ObjectIdentity | None = None
    owned_files: dict[Path, ObjectIdentity] = {}
    interrupted = False
    pending_unexpected: BaseException | None = None

    try:
        create, probe_created, probe_owned, probe_identity = _create_probe_directory(
            ops, resolved_target, probe_dir, user_profile=user_profile
        )
        checks.append(create)

        if not probe_created:
            checks.extend(_unknown_checks(len(checks), 4, "依赖的探针目录未创建"))
        else:
            write = _write_probe_file(
                ops,
                probe_dir,
                before,
                content=probe_content,
                owned_files=owned_files,
                probe_identity=probe_identity,
                user_profile=user_profile,
            )
            checks.append(write)
            if write.status is not CheckStatus.PASS:
                checks.extend(_unknown_checks(len(checks), 3, "依赖的固定内容写入未成功"))
            else:
                read = _read_probe_file(
                    ops,
                    before,
                    expected=probe_content,
                    owned_files=owned_files,
                    user_profile=user_profile,
                )
                checks.append(read)
                # Read is diagnostic but does not prevent the independent
                # rename/delete attempt while the known source file exists.
                rename = _rename_probe_file(
                    ops,
                    before,
                    after,
                    owned_files=owned_files,
                    user_profile=user_profile,
                )
                checks.append(rename)
                checks.append(
                    _delete_probe_file(
                        ops,
                        before,
                        after,
                        owned_files=owned_files,
                        user_profile=user_profile,
                    )
                )
    except KeyboardInterrupt:
        interrupted = True
        checks.extend(
            _unknown_checks(
                len(checks),
                len(WORKSPACE_PROBE_CHECK_IDS) - len(checks) - 1,
                "用户中断",
            )
        )
    except Exception as exc:
        # OSError/UnicodeError are handled at the individual operation layer;
        # any other exception indicates a programming or injected-boundary
        # failure and must remain visible after bounded cleanup.
        pending_unexpected = exc
        checks.extend(
            _unknown_checks(
                len(checks),
                len(WORKSPACE_PROBE_CHECK_IDS) - len(checks) - 1,
                "探针执行因未预期异常中断",
            )
        )

    try:
        cleanup, residual_paths = _cleanup_probe(
            ops,
            resolved_target,
            probe_dir,
            before,
            after,
            probe_created=probe_created,
            probe_owned=probe_owned,
            probe_identity=probe_identity,
            owned_files=owned_files,
            user_profile=user_profile,
        )
    except KeyboardInterrupt:
        interrupted = True
        residual_paths = (_relative(probe_dir, resolved_target),)
        cleanup = _fail(
            WORKSPACE_PROBE_CHECK_IDS[-1],
            "探针清理被用户中断",
            evidence=("residual: " + _relative(probe_dir, resolved_target),),
            user_profile=user_profile,
        )
    except Exception as exc:
        residual_paths = (_relative(probe_dir, resolved_target),)
        cleanup = _fail(
            WORKSPACE_PROBE_CHECK_IDS[-1],
            "清理发生未预期异常",
            evidence=("residual: " + _relative(probe_dir, resolved_target),),
            exception=exc,
            user_profile=user_profile,
        )
        if pending_unexpected is None:
            pending_unexpected = exc
    checks.append(cleanup)

    # The normal operation path always has exactly five operation results
    # before cleanup.  If interruption happened before any operation result,
    # fill the fixed slots without inventing a successful capability claim.
    checks = _pad_operation_checks(checks, interrupted=interrupted)
    successful = all(check.status is CheckStatus.PASS for check in checks) and not residual_paths
    report = WorkspaceProbeReport(
        schema_version=WORKSPACE_PROBE_SCHEMA_VERSION,
        tool=WORKSPACE_PROBE_TOOL,
        kind=WORKSPACE_PROBE_KIND,
        target=redact_text(str(resolved_target), user_profile=user_profile),
        successful=successful,
        checks=tuple(checks),
        residual_paths=tuple(dict.fromkeys(residual_paths)),
    )
    if pending_unexpected is not None:
        raise WorkspaceProbeUnexpectedError(report, pending_unexpected) from pending_unexpected
    if interrupted:
        raise WorkspaceProbeInterrupted(report)
    return report


def _validate_target(
    ops: WorkspaceOperations | Any,
    target: Path,
    *,
    user_profile: str | None,
) -> Path:
    try:
        target_stat = ops.lstat(target)
    except (OSError, UnicodeError) as exc:
        raise WorkspaceProbeInputError(
            "target cannot be resolved or inspected: "
            + _exception_text(exc, user_profile=user_profile)
        ) from exc
    except Exception:
        raise
    if _is_reparse(target_stat):
        raise WorkspaceProbeInputError("target is a reparse point; refusing to write")
    if not stat.S_ISDIR(target_stat.st_mode):
        raise WorkspaceProbeInputError("target must be an existing ordinary directory")
    try:
        # Resolve only after the input lstat checks; the resolved directory is
        # the boundary from which all generated direct-child paths are built.
        resolved = target.resolve(strict=True)
    except (OSError, UnicodeError) as exc:
        raise WorkspaceProbeInputError(
            "target cannot be resolved or inspected: "
            + _exception_text(exc, user_profile=user_profile)
        ) from exc
    return resolved


def _safe_token(value: object) -> str:
    token = str(value)
    if not token or any(not (char.isalnum() or char == "-") for char in token):
        raise WorkspaceProbeInputError("token_factory returned an unsafe directory token")
    return token


def _create_probe_directory(
    ops: WorkspaceOperations | Any,
    target: Path,
    probe_dir: Path,
    *,
    user_profile: str | None,
) -> tuple[CheckResult, bool, bool, ObjectIdentity | None]:
    created = False
    owned = False
    identity: ObjectIdentity | None = None
    try:
        # Revalidate immediately before the first write.
        target_stat = ops.lstat(target)
        if _is_reparse(target_stat) or not stat.S_ISDIR(target_stat.st_mode):
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[0],
                "目标目录在写入前不再是普通目录",
                evidence=("target validation failed before create",),
            ), created, owned, identity
        ops.mkdir(probe_dir)
        created = True
        probe_stat = ops.lstat(probe_dir)
        if _is_reparse(probe_stat) or not stat.S_ISDIR(probe_stat.st_mode):
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[0],
                "探针目录不是普通目录",
                evidence=("created probe directory failed ordinary-directory validation",),
            ), created, owned, identity
        identity = _object_identity(probe_stat)
        if identity is None:
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[0],
                "无法确认探针目录对象身份",
                evidence=("probe directory identity is unavailable",),
                user_profile=user_profile,
            ), created, owned, identity
        owned = True
    except (OSError, UnicodeError) as exc:
        return _fail(
                WORKSPACE_PROBE_CHECK_IDS[0],
                "无法创建或验证探针目录",
                exception=exc,
                user_profile=user_profile,
            ), created, owned, identity
    return _pass(WORKSPACE_PROBE_CHECK_IDS[0], "已创建并验证探针目录"), created, owned, identity


def _write_probe_file(
    ops: WorkspaceOperations | Any,
    probe_dir: Path,
    before: Path,
    *,
    content: str,
    owned_files: dict[Path, ObjectIdentity],
    probe_identity: ObjectIdentity | None = None,
    user_profile: str | None,
) -> CheckResult:
    try:
        _require_probe_dir(ops, probe_dir, expected=probe_identity)
        ops.write_text_exclusive(before, content)
        file_stat = ops.lstat(before)
        if _is_reparse(file_stat) or not stat.S_ISREG(file_stat.st_mode):
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[1],
                "写入结果不是普通文件",
                evidence=("before.txt failed ordinary-file validation",),
                user_profile=user_profile,
            )
        identity = _object_identity(file_stat)
        if identity is None:
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[1],
                "无法确认 before.txt 对象身份",
                evidence=("before.txt identity is unavailable",),
                user_profile=user_profile,
            )
        owned_files[before] = identity
    except (OSError, UnicodeError) as exc:
        return _fail(
            WORKSPACE_PROBE_CHECK_IDS[1],
            "固定内容写入失败",
            exception=exc,
            user_profile=user_profile,
        )
    return _pass(WORKSPACE_PROBE_CHECK_IDS[1], "已写入固定探针内容")


def _read_probe_file(
    ops: WorkspaceOperations | Any,
    before: Path,
    *,
    expected: str,
    owned_files: dict[Path, ObjectIdentity],
    user_profile: str | None,
) -> CheckResult:
    try:
        identity = _require_regular_file(ops, before, "before.txt")
        if owned_files.get(before) != identity:
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[2],
                "读取前 before.txt 对象身份已变化",
                evidence=("before.txt identity changed before read",),
                user_profile=user_profile,
            )
        value = ops.read_text(before)
    except (OSError, UnicodeError) as exc:
        return _fail(
            WORKSPACE_PROBE_CHECK_IDS[2],
            "固定内容读取失败",
            exception=exc,
            user_profile=user_profile,
        )
    if value != expected:
        return _fail(
            WORKSPACE_PROBE_CHECK_IDS[2],
            "读取内容与固定探针内容不一致",
            evidence=("read content did not match the fixed probe content",),
        )
    return _pass(WORKSPACE_PROBE_CHECK_IDS[2], "固定探针内容读取一致")


def _rename_probe_file(
    ops: WorkspaceOperations | Any,
    before: Path,
    after: Path,
    *,
    owned_files: dict[Path, ObjectIdentity],
    user_profile: str | None,
) -> CheckResult:
    try:
        before_identity = _require_regular_file(ops, before, "before.txt")
        if owned_files.get(before) != before_identity:
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[3],
                "重命名前 before.txt 对象身份已变化",
                evidence=("before.txt identity changed before rename",),
                user_profile=user_profile,
            )
        if _path_exists(ops, after):
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[3],
                "重命名目标已存在，拒绝覆盖",
                evidence=("after.txt already exists",),
                user_profile=user_profile,
            )
        ops.rename(before, after)
        after_identity = _require_regular_file(ops, after, "after.txt")
        if after_identity != before_identity:
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[3],
                "重命名后的 after.txt 对象身份不一致",
                evidence=("after.txt identity did not match before.txt",),
                user_profile=user_profile,
            )
        if _path_exists(ops, before):
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[3],
                "重命名后源文件仍存在",
                evidence=("before.txt remained after rename",),
                user_profile=user_profile,
            )
        owned_files.pop(before, None)
        owned_files[after] = after_identity
    except (OSError, UnicodeError) as exc:
        return _fail(
            WORKSPACE_PROBE_CHECK_IDS[3],
            "固定文件重命名失败",
            exception=exc,
            user_profile=user_profile,
        )
    return _pass(WORKSPACE_PROBE_CHECK_IDS[3], "已将 before.txt 重命名为 after.txt")


def _delete_probe_file(
    ops: WorkspaceOperations | Any,
    before: Path,
    after: Path,
    *,
    owned_files: dict[Path, ObjectIdentity],
    user_profile: str | None,
) -> CheckResult:
    try:
        if after in owned_files:
            active = after
        elif before in owned_files:
            active = before
        else:
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[4],
                "没有已确认归属的活动探针文件",
                evidence=("no owned probe file is available for delete",),
                user_profile=user_profile,
            )
        identity = _require_regular_file(ops, active, active.name)
        if owned_files.get(active) != identity:
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[4],
                f"删除前 {active.name} 对象身份已变化",
                evidence=(f"{active.name} identity changed before delete",),
                user_profile=user_profile,
            )
        ops.unlink(active)
        if _path_exists(ops, active):
            return _fail(
                WORKSPACE_PROBE_CHECK_IDS[4],
                "删除后文件仍存在",
                evidence=(f"{active.name} remained after delete",),
                user_profile=user_profile,
            )
        owned_files.pop(active, None)
    except (OSError, UnicodeError) as exc:
        return _fail(
            WORKSPACE_PROBE_CHECK_IDS[4],
            "活动探针文件删除失败",
            exception=exc,
            user_profile=user_profile,
        )
    return _pass(WORKSPACE_PROBE_CHECK_IDS[4], "已删除 after.txt")


def _cleanup_probe(
    ops: WorkspaceOperations | Any,
    target: Path,
    probe_dir: Path,
    before: Path,
    after: Path,
    *,
    probe_created: bool,
    probe_owned: bool,
    probe_identity: ObjectIdentity | None,
    owned_files: dict[Path, ObjectIdentity],
    user_profile: str | None,
) -> tuple[CheckResult, tuple[str, ...]]:
    """Best-effort cleanup of this run's identity-checked files and directory.

    Python's path-based unlink/rmdir calls cannot make identity verification
    and deletion atomic.  This is a local capability probe, not a defence
    against an adversarial process racing the cleanup.
    """

    check_id = WORKSPACE_PROBE_CHECK_IDS[5]
    if not probe_created:
        return _pass(check_id, "没有已创建的探针目录需要清理"), ()

    residual: list[str] = []
    evidence: list[str] = []
    try:
        probe_stat = ops.lstat(probe_dir)
    except (OSError, UnicodeError) as exc:
        if _is_missing_error(exc):
            return _pass(check_id, "探针目录已不存在"), ()
        relative = _relative(probe_dir, target)
        return _fail(
            check_id,
            "无法检查探针目录，未进入清理",
            evidence=("residual: " + relative,),
            exception=exc,
            user_profile=user_profile,
        ), (relative,)

    if _is_reparse(probe_stat) or not stat.S_ISDIR(probe_stat.st_mode):
        relative = _relative(probe_dir, target)
        return _fail(
            check_id,
            "探针目录不是普通目录，拒绝进入清理",
            evidence=("residual: " + relative,),
        ), (relative,)
    if not probe_owned:
        relative = _relative(probe_dir, target)
        return _fail(
            check_id,
            "探针目录归属未确认，拒绝进入清理",
            evidence=("residual: " + relative,),
        ), (relative,)
    current_probe_identity = _object_identity(probe_stat)
    if current_probe_identity is None or current_probe_identity != probe_identity:
        relative = _relative(probe_dir, target)
        return _fail(
            check_id,
            "清理前探针目录对象身份已变化",
            evidence=("residual: " + relative, "probe directory identity changed"),
        ), (relative,)

    # The loop is deliberately over two known paths; it never enumerates the
    # directory and never recursively removes unknown entries.
    for path in (before, after):
        try:
            file_stat = ops.lstat(path)
        except (OSError, UnicodeError) as exc:
            if _is_missing_error(exc):
                continue
            residual.append(_relative(path, target))
            evidence.extend(_exception_evidence(exc, user_profile=user_profile))
            continue
        if _is_reparse(file_stat) or not stat.S_ISREG(file_stat.st_mode):
            residual.append(_relative(path, target))
            continue
        if path not in owned_files:
            residual.append(_relative(path, target))
            continue
        current_identity = _object_identity(file_stat)
        if current_identity is None or current_identity != owned_files[path]:
            residual.append(_relative(path, target))
            continue
        try:
            ops.unlink(path)
        except (OSError, UnicodeError) as exc:
            residual.append(_relative(path, target))
            evidence.extend(_exception_evidence(exc, user_profile=user_profile))

    # A transient sharing/permission error on the operation delete may be
    # recoverable immediately during cleanup.  Retry only those same known
    # file paths once; never enumerate or recursively remove anything else.
    for path in (before, after):
        relative = _relative(path, target)
        if relative not in residual or path not in owned_files:
            continue
        try:
            file_stat = ops.lstat(path)
            if _is_reparse(file_stat) or not stat.S_ISREG(file_stat.st_mode):
                continue
            current_identity = _object_identity(file_stat)
            if current_identity is None or current_identity != owned_files[path]:
                continue
            ops.unlink(path)
        except (OSError, UnicodeError) as exc:
            evidence.extend(_exception_evidence(exc, user_profile=user_profile))
            continue
        residual.remove(relative)
        owned_files.pop(path, None)

    try:
        probe_stat = ops.lstat(probe_dir)
        if _is_reparse(probe_stat) or not stat.S_ISDIR(probe_stat.st_mode):
            residual.append(_relative(probe_dir, target))
        elif (
            _object_identity(probe_stat) is None
            or _object_identity(probe_stat) != probe_identity
        ):
            residual.append(_relative(probe_dir, target))
        else:
            ops.rmdir(probe_dir)
    except (OSError, UnicodeError) as exc:
        if not _is_missing_error(exc):
            residual.append(_relative(probe_dir, target))
            evidence.extend(_exception_evidence(exc, user_profile=user_profile))

    # Only relative residue names are reported.  Do not inspect unknown
    # directory contents to discover more names.
    if residual:
        unique_residual = tuple(dict.fromkeys(residual))
        evidence.insert(0, "residual: " + ", ".join(unique_residual))
        return _fail(
            check_id,
            "探针清理后仍有残留",
            evidence=tuple(evidence),
            user_profile=user_profile,
        ), unique_residual
    return _pass(check_id, "已删除本次探针文件并清理空目录"), ()


def _require_probe_dir(
    ops: WorkspaceOperations | Any,
    probe_dir: Path,
    *,
    expected: ObjectIdentity | None,
) -> ObjectIdentity:
    value = ops.lstat(probe_dir)
    if _is_reparse(value) or not stat.S_ISDIR(value.st_mode):
        raise OSError("probe directory failed ordinary-directory validation")
    identity = _object_identity(value)
    if identity is None or (expected is not None and identity != expected):
        raise OSError("probe directory identity changed")
    return identity


def _require_regular_file(
    ops: WorkspaceOperations | Any, path: Path, label: str
) -> ObjectIdentity:
    value = ops.lstat(path)
    if _is_reparse(value) or not stat.S_ISREG(value.st_mode):
        raise OSError(f"{label} failed ordinary-file validation")
    identity = _object_identity(value)
    if identity is None:
        raise OSError(f"{label} identity is unavailable")
    return identity


def _object_identity(value: os.stat_result | Any) -> ObjectIdentity | None:
    """Return a stable Windows identity, or None when it cannot be trusted."""

    try:
        device = int(getattr(value, "st_dev", 0) or 0)
        inode = int(getattr(value, "st_ino", 0) or 0)
    except (TypeError, ValueError):
        return None
    if device <= 0 or inode <= 0:
        return None
    return device, inode


def _is_reparse(value: os.stat_result | Any) -> bool:
    attributes = int(getattr(value, "st_file_attributes", 0) or 0)
    tag = int(getattr(value, "st_reparse_tag", 0) or 0)
    return bool(attributes & _REPARSE_POINT or tag)


def _path_exists(ops: WorkspaceOperations | Any, path: Path) -> bool:
    try:
        ops.lstat(path)
    except (OSError, UnicodeError) as exc:
        if _is_missing_error(exc):
            return False
        raise
    return True


def _is_missing_error(exc: BaseException) -> bool:
    return isinstance(exc, FileNotFoundError) or getattr(exc, "winerror", None) == 2


def _relative(path: Path, target: Path) -> str:
    try:
        return str(path.relative_to(target)).replace("\\", "/") or "."
    except ValueError:
        # This should be unreachable because all paths are constructed below
        # target, but never emit an absolute path if an injected boundary lies.
        return path.name or "."


def _exception_text(exc: BaseException, *, user_profile: str | None) -> str:
    return "; ".join(_exception_evidence(exc, user_profile=user_profile))


def _exception_evidence(
    exc: BaseException,
    *,
    user_profile: str | None,
) -> tuple[str, ...]:
    evidence = [f"exception_type: {type(exc).__name__}"]
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        evidence.append(f"winerror: {winerror}")
    message = redact_text(str(exc), user_profile=user_profile)
    if message:
        evidence.append(f"message: {message[:_MAX_EXCEPTION_MESSAGE]}")
    return tuple(evidence)


def _pass(check_id: str, summary: str) -> CheckResult:
    return CheckResult(id=check_id, status=CheckStatus.PASS, summary=summary)


def _fail(
    check_id: str,
    summary: str,
    *,
    evidence: tuple[str, ...] = (),
    exception: BaseException | None = None,
    user_profile: str | None = None,
) -> CheckResult:
    items = list(evidence)
    if exception is not None:
        items.extend(_exception_evidence(exception, user_profile=user_profile))
    if not items:
        items.append("operation failed")
    return CheckResult(
        id=check_id,
        status=CheckStatus.FAIL,
        summary=summary,
        evidence=tuple(items),
    )


def _unknown_check(check_id: str, summary: str) -> CheckResult:
    return CheckResult(id=check_id, status=CheckStatus.UNKNOWN, summary=summary)


def _unknown_checks(start: int, count: int, summary: str) -> list[CheckResult]:
    """Build the next contiguous unknown operation checks."""
    return [
        _unknown_check(WORKSPACE_PROBE_CHECK_IDS[start + index], summary)
        for index in range(max(0, count))
    ]


def _pad_operation_checks(
    checks: list[CheckResult],
    *,
    interrupted: bool,
) -> list[CheckResult]:
    """Normalize partial interruption output to the fixed six-check schema."""

    by_id = {check.id: check for check in checks}
    for index, check_id in enumerate(WORKSPACE_PROBE_CHECK_IDS[:-1]):
        by_id.setdefault(
            check_id,
            _unknown_check(check_id, "用户中断" if interrupted else "依赖步骤未执行"),
        )
    cleanup = by_id.get(WORKSPACE_PROBE_CHECK_IDS[-1])
    if cleanup is None:
        cleanup = _unknown_check(WORKSPACE_PROBE_CHECK_IDS[-1], "清理未执行")
    return [by_id[check_id] for check_id in WORKSPACE_PROBE_CHECK_IDS[:-1]] + [cleanup]

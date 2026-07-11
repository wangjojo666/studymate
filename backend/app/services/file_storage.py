from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


class FileCleanupError(RuntimeError):
    pass


@dataclass(frozen=True)
class StagedFileDeletion:
    original: Path
    staged: Path


def stage_files_for_deletion(
    paths: list[Path],
    *,
    allowed_root: Path,
) -> list[StagedFileDeletion]:
    """Atomically hide files before their SQL records are removed.

    All existing paths are validated before the first rename. If any rename
    fails, earlier renames are restored so the database can safely remain the
    source of truth and the caller can retry deletion later.
    """
    root = allowed_root.resolve()
    candidates: list[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = raw_path.resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        if not path.is_relative_to(root):
            raise FileCleanupError(f"拒绝删除上传目录之外的文件：{path}")
        if not path.is_file():
            raise FileCleanupError(f"资料路径不是普通文件：{path}")
        candidates.append(path)

    staged: list[StagedFileDeletion] = []
    try:
        for original in candidates:
            tombstone = original.with_name(f".{original.name}.{uuid4().hex}.deleting")
            original.replace(tombstone)
            staged.append(StagedFileDeletion(original=original, staged=tombstone))
    except OSError as exc:
        restore_staged_deletions(staged)
        raise FileCleanupError(f"资料文件正被占用或无法移动，请稍后重试：{exc}") from exc
    return staged


def restore_staged_deletions(staged: list[StagedFileDeletion]) -> list[str]:
    failures: list[str] = []
    for item in reversed(staged):
        if not item.staged.exists():
            continue
        try:
            item.staged.replace(item.original)
        except OSError as exc:
            failures.append(f"{item.original}: {exc}")
    return failures


def finalize_staged_deletions(staged: list[StagedFileDeletion]) -> list[str]:
    failures: list[str] = []
    for item in staged:
        if not item.staged.exists():
            continue
        try:
            item.staged.unlink()
        except OSError as exc:
            failures.append(f"{item.staged}: {exc}")
    return failures


def reconcile_staged_deletions(root: Path) -> dict[str, int | bool | list[str]]:
    """Retry tombstone cleanup left behind by an earlier successful SQL delete."""
    resolved_root = root.resolve()
    if not resolved_root.exists():
        return {"checked": 0, "deleted": 0, "ok": True, "failures": []}
    tombstones = [
        path
        for path in resolved_root.rglob(".*.deleting")
        if path.is_file() and path.resolve().is_relative_to(resolved_root)
    ]
    failures: list[str] = []
    deleted = 0
    for path in tombstones:
        try:
            path.unlink()
            deleted += 1
        except OSError as exc:
            failures.append(f"{path}: {exc}")
    return {
        "checked": len(tombstones),
        "deleted": deleted,
        "ok": not failures,
        "failures": failures,
    }

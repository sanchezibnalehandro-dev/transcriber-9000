"""Non-destructive import of files from an older portable folder."""

from __future__ import annotations

import re
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from runtime_paths import transcription_data_root
from safe_file_ops import publish_staged_file


DATA_FOLDERS = (Path("input"), Path("output"), Path(".cache/whisper"), Path("models"))
_STAGED_IMPORT_NAME = re.compile(r"^\..+\.[0-9a-f]{32}\.importing$")
MIN_STALE_IMPORT_AGE_SECONDS = 60 * 60


@dataclass(frozen=True)
class ImportResult:
    copied: int
    skipped: int


def has_legacy_data(root: Path) -> bool:
    if not root.is_dir():
        return False
    for folder in DATA_FOLDERS:
        candidate = root / folder
        if candidate.is_dir() and any(path.is_file() and not path.is_symlink() for path in candidate.rglob("*")):
            return True
    return False


def legacy_data_candidates() -> tuple[Path, ...]:
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return ()
    app_parent = Path(sys.executable).absolute().parents[3]
    candidates = (app_parent, Path.home() / "Documents" / "Transcriber 9000")
    destination = transcription_data_root().resolve()
    return tuple(path for path in candidates if path.resolve() != destination and has_legacy_data(path))


def prune_stale_legacy_imports(
    destination_root: Path,
    *,
    min_age_seconds: float = MIN_STALE_IMPORT_AGE_SECONDS,
    now: float | None = None,
) -> int:
    """Remove only old UUID staging copies inside managed data folders.

    Keep source files, final files, and recent copies that another instance may
    still be writing. Unreadable entries must never prevent app startup.
    """
    current_time = time.time() if now is None else now
    data_root = destination_root.expanduser().resolve()
    removed = 0
    for folder in DATA_FOLDERS:
        folder_path = destination_root / folder
        try:
            if folder_path.is_symlink() or not folder_path.is_dir():
                continue
            if not folder_path.resolve().is_relative_to(data_root):
                continue
            candidates = list(folder_path.rglob("*.importing"))
        except (OSError, RuntimeError):
            continue
        for candidate in candidates:
            if not _STAGED_IMPORT_NAME.fullmatch(candidate.name):
                continue
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                if not candidate.resolve().is_relative_to(data_root):
                    continue
                if current_time - candidate.stat().st_mtime < min_age_seconds:
                    continue
                candidate.unlink()
                removed += 1
            except (OSError, RuntimeError):
                continue
    return removed


def copy_legacy_data(source_root: Path, destination_root: Path) -> ImportResult:
    source_root = source_root.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()
    if source_root == destination_root or destination_root.is_relative_to(source_root):
        raise ValueError("Выберите другую папку с прежними данными")
    if not has_legacy_data(source_root):
        raise ValueError("В выбранной папке нет input, output или моделей")

    copied = skipped = 0
    for folder in DATA_FOLDERS:
        source_dir = source_root / folder
        if not source_dir.is_dir() or source_dir.is_symlink():
            continue
        for source in source_dir.rglob("*"):
            if not source.is_file() or source.is_symlink():
                continue
            relative = source.relative_to(source_root)
            if any(part == ".." for part in relative.parts):
                continue
            target = destination_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                skipped += 1
                continue
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.importing")
            try:
                shutil.copy2(source, temporary)
                try:
                    publish_staged_file(temporary, target)
                except FileExistsError:
                    skipped += 1
                else:
                    copied += 1
            finally:
                temporary.unlink(missing_ok=True)
    return ImportResult(copied=copied, skipped=skipped)

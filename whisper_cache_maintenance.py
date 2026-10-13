"""Conservative cleanup of incomplete Whisper model downloads."""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from pathlib import Path


_DOWNLOAD_NAME = re.compile(r"^(?P<model>[A-Za-z0-9_-]+)\.[0-9a-f]{32}\.pt\.download$")
# An active download in another app instance may be hours old. Avoid deleting
# fresh temporary files; older leftovers are removed on startup/next download.
MIN_STALE_AGE_SECONDS = 60 * 60


def prune_stale_whisper_downloads(
    cache_dir: Path,
    model_names: Iterable[str],
    *,
    min_age_seconds: float = MIN_STALE_AGE_SECONDS,
    now: float | None = None,
) -> int:
    """Remove old UUID-named partials only, preserving models and recent files.

    Failures to inspect/delete a cache entry must not prevent app startup or
    a new download. On restart after an interrupted download, a partial
    becomes eligible once it has been untouched for min_age_seconds.
    """
    known_models = set(model_names)
    current_time = time.time() if now is None else now
    try:
        candidates = list(cache_dir.iterdir())
    except OSError:
        return 0

    removed = 0
    for candidate in candidates:
        match = _DOWNLOAD_NAME.fullmatch(candidate.name)
        if not match or match.group("model") not in known_models:
            continue
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if current_time - candidate.stat().st_mtime < min_age_seconds:
                continue
            candidate.unlink()
            removed += 1
        except OSError:
            # Concurrent cleanup or restrictive filesystem permissions.
            continue
    return removed

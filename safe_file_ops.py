"""Publish a staged file without silently replacing an existing file.

A same-directory rename is no-overwrite on Windows and works on FAT/exFAT.
On POSIX, prefer an atomic hard link. Some filesystems lack both, so fall
back to exclusive creation and a bounded-memory copy.
"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path


_NO_LINK_ERRNOS = {
    errno.EPERM,
    errno.EACCES,
    errno.ENOSYS,
    errno.EOPNOTSUPP,
    errno.ENOTSUP,
    errno.EXDEV,
}


def publish_staged_file(staged: Path, target: Path) -> None:
    """Promote a completed same-directory staging file, never replacing target.

    Callers own staging-file cleanup. The fallback removes a partially written
    target if a normal write fails; it cannot guarantee atomic visibility on
    filesystems without hard links or no-replace rename support.
    """
    try:
        if os.name == "nt":
            # Windows rename refuses an existing destination, unlike POSIX.
            os.rename(staged, target)
        else:
            os.link(staged, target)
        return
    except FileExistsError:
        raise
    except OSError as error:
        if target.exists() or target.is_symlink():
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target)) from error
        if error.errno not in _NO_LINK_ERRNOS:
            raise

    created = False
    try:
        with staged.open("rb") as reader, target.open("xb") as writer:
            created = True
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        try:
            shutil.copystat(staged, target)
        except OSError:
            # Preserving timestamps is best-effort; the complete copy is valid.
            pass
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise

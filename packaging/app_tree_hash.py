"""Hash a .app tree including file paths and symlink targets."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def app_tree_digest(root: Path) -> dict[str, int | str]:
    digest = hashlib.sha256()
    files = total_bytes = 0
    for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root))):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + str(path.readlink()).encode("utf-8") + b"\0")
        elif path.is_file():
            files += 1
            total_bytes += path.stat().st_size
            digest.update(b"F\0" + relative + b"\0")
            with path.open("rb") as source:
                while chunk := source.read(4 * 1024 * 1024):
                    digest.update(chunk)
            digest.update(b"\0")
    return {"files": files, "bytes": total_bytes, "sha256": digest.hexdigest()}


if __name__ == "__main__":
    print(json.dumps(app_tree_digest(Path(sys.argv[1])), sort_keys=True))

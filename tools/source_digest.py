"""Print the path-ordered digest of the application sources used in reports.

Method: every ``src/**/*.py`` file contributes one ``relative/path sha256`` line,
lines are sorted by path and joined with LF (no trailing newline), and the
SHA-256 of that UTF-8 text is the reported digest.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def digest(root: Path) -> tuple[int, str]:
    files = sorted(
        (path for path in root.rglob("*.py") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    lines = [
        f"{path.relative_to(root).as_posix()} {hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in files
    ]
    return len(files), hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest().upper()


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "src").resolve()
    count, value = digest(root)
    print(f"{root}: {count} files, digest {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

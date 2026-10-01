"""Launch the built app with local media and no development PATH dependencies."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("video", "image"), default="video")
    parser.add_argument("files", nargs=2, type=Path)
    args = parser.parse_args()
    exe = args.exe.resolve(strict=True)
    files = [path.resolve(strict=True) for path in args.files]
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"self-test output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    system_root = env.get("SystemRoot", r"C:\Windows")
    env["PATH"] = str(Path(system_root) / "System32")
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "VIDEO_COMPARE_FFPROBE", "QT_QPA_PLATFORM"):
        env.pop(name, None)
    flag = "--self-test-image-output" if args.mode == "image" else "--self-test-output"
    command = [str(exe), "--mode", args.mode, *(str(path) for path in files), flag, str(output)]
    result = subprocess.run(
        command,
        cwd=exe.parent,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=120,
        check=False,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    print(f"PACKAGE_EXIT_CODE={result.returncode}")
    expected = "IMAGE_SELF_TEST_OK:" if args.mode == "image" else "SELF_TEST_OK:"
    if result.returncode or expected not in result.stdout:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

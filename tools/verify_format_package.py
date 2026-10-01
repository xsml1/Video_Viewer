"""Verify all generated format pairs in independently launched packaged processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    media = root / "tests/assets/generated/formats-20261001"
    hdr = root / "tests/assets/generated/hdr-20261001"
    output = args.output.resolve()
    if output.exists():
        parser.error("use a new output directory")
    output.mkdir(parents=True)
    manifest = json.loads((media / "manifest.json").read_text("utf-8"))
    hdr_rows = json.loads((hdr / "manifest.json").read_text("utf-8"))
    results = []
    for kind, rows, folder in (
        ("video", manifest["videos"], media),
        ("video", hdr_rows, hdr),
        ("image", manifest["images"], media),
    ):
        for offset in range(0, len(rows), 2):
            pair = rows[offset : offset + 2]
            if len(pair) == 1:
                pair = pair + pair
            target = output / f"{folder.name}-{kind}-{offset:02d}"
            inputs = [folder / row["filename"] for row in pair]
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools/verify_package.py"),
                    "--exe",
                    str(args.exe.resolve()),
                    "--output",
                    str(target),
                    "--mode",
                    kind,
                    *map(str, inputs),
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=150,
            )
            (output / f"{target.name}.log").write_text(
                result.stdout + "\n" + result.stderr, "utf-8"
            )
            print(f"{kind} {offset}: exit {result.returncode}", flush=True)
            if result.returncode:
                print(result.stdout, result.stderr)
                return 1
            if kind == "image":
                with Image.open(target / "image_compare.png") as image:
                    pixels = np.array(image.convert("RGB"), dtype=np.int16)
                for row in pair:
                    # Independent known source color must survive real decode and composite.
                    matching = np.all(np.abs(pixels - row["rgb"]) <= row["tolerance"], axis=2)
                    if np.count_nonzero(matching) < 50:
                        raise AssertionError(f"packaged image pixels mismatch: {row['filename']}")
            for path, row in zip(inputs, pair, strict=True):
                if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                    raise AssertionError(f"input changed: {path.name}")
            results.append(
                {
                    "mode": kind,
                    "files": [path.name for path in inputs],
                    "exit_code": result.returncode,
                    "report": target.name,
                }
            )
    report = {
        "status": "passed",
        "video_variants": len(manifest["videos"]) + len(hdr_rows),
        "image_variants": len(manifest["images"]),
        "runs": results,
        "exe_sha256": hashlib.sha256(args.exe.read_bytes()).hexdigest(),
    }
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(f"PACKAGE_FORMAT_MATRIX_OK: {len(results)} launched processes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Map scan-matrix byte ranges back to decrypted calibration without dumping data."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path


def direct_runs(calibration: bytes, matrix: bytes, width: int = 16) -> list[dict[str, int]]:
    matcher = difflib.SequenceMatcher(None, calibration, matrix, autojunk=False)
    runs = [
        {"matrix_offset": block.b, "calibration_offset": block.a, "length": block.size}
        for block in matcher.get_matching_blocks()
        if block.size >= width
    ]
    return sorted(runs, key=lambda run: (-run["length"], run["matrix_offset"]))


def summarize(calibration: bytes, matrix: bytes, width: int = 16) -> dict[str, object]:
    runs = direct_runs(calibration, matrix, width)
    covered = bytearray(len(matrix))
    for run in runs:
        start = run["matrix_offset"]
        covered[start:start + run["length"]] = b"\x01" * run["length"]
    return {
        "calibration": {"length": len(calibration), "sha256": hashlib.sha256(calibration).hexdigest()},
        "matrix": {"length": len(matrix), "sha256": hashlib.sha256(matrix).hexdigest()},
        "window": width,
        "directly_mapped_bytes": sum(covered),
        "direct_coverage": round(sum(covered) / len(matrix), 6) if matrix else 0,
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("scan_matrix", type=Path)
    parser.add_argument("--window", type=int, default=16)
    args = parser.parse_args()
    if args.window < 4:
        parser.error("--window must be at least 4")
    result = summarize(args.calibration.read_bytes(), args.scan_matrix.read_bytes(), args.window)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

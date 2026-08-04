#!/usr/bin/env python3
"""Summarize the device-specific 06cb:0082 calibration records."""

from __future__ import annotations

import argparse
import collections
import difflib
from pathlib import Path


def offsets(data: bytes, needle: bytes) -> list[int]:
    found: list[int] = []
    start = 0
    while (index := data.find(needle, start)) >= 0:
        found.append(index)
        start = index + 1
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("calibration", type=Path)
    parser.add_argument("--scan-matrix", type=Path)
    args = parser.parse_args()

    calibration = args.calibration.read_bytes()
    print(f"calibration_length={len(calibration)}")

    patterns = {
        "row_prefix": bytes.fromhex("01fe"),
        "row_suffix": bytes.fromhex("f0f70100"),
        "block_header": bytes.fromhex("0700000004000000"),
    }
    for name, pattern in patterns.items():
        matches = offsets(calibration, pattern)
        print(f"{name}_count={len(matches)}")
        print(f"{name}_offsets={','.join(map(str, matches[:32]))}")

    prefix_offsets = offsets(calibration, patterns["row_prefix"])
    if len(prefix_offsets) > 1:
        strides = collections.Counter(
            right - left for left, right in zip(prefix_offsets, prefix_offsets[1:])
        )
        print(f"row_prefix_strides={strides.most_common(16)}")

    if args.scan_matrix:
        matrix = args.scan_matrix.read_bytes()
        matcher = difflib.SequenceMatcher(None, calibration, matrix, autojunk=False)
        blocks = sorted(matcher.get_matching_blocks(), key=lambda block: block.size, reverse=True)
        print(f"scan_matrix_length={len(matrix)}")
        for block in blocks[:20]:
            if block.size == 0:
                continue
            print(
                "matching_block="
                f"calibration:{block.a},matrix:{block.b},length:{block.size}"
            )


if __name__ == "__main__":
    main()

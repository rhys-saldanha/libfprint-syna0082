#!/usr/bin/env python3
"""Apply experimentally identified raster transforms to 06cb:0082 PGMs."""

from __future__ import annotations

import argparse
from pathlib import Path


WIDTH = 56
HEIGHT = 144


def read_pgm(path: Path) -> bytes:
    data = path.read_bytes()
    magic, dimensions, maximum, pixels = data.split(b"\n", 3)
    if magic != b"P5" or dimensions != b"56 144" or maximum != b"255":
        raise ValueError(f"unsupported PGM header in {path}")
    if len(pixels) != WIDTH * HEIGHT:
        raise ValueError(f"unexpected pixel count in {path}: {len(pixels)}")
    return pixels


def column_major_to_raster(pixels: bytes) -> bytes:
    return bytes(
        pixels[column * HEIGHT + row]
        for row in range(HEIGHT)
        for column in range(WIDTH)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    pixels = column_major_to_raster(read_pgm(args.input))
    args.output.write_bytes(b"P5\n56 144\n255\n" + pixels)


if __name__ == "__main__":
    main()

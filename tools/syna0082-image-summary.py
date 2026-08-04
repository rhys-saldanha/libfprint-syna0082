#!/usr/bin/env python3
"""Find and validate raw image responses in normalized 06cb:0082 captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path


HEADER_SIZE = 18


@dataclass(frozen=True)
class ImageRecord:
    frame: str
    width: int
    height: int
    flags: bytes
    pixels: bytes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="write sensitive raw images as PGM files outside any Git worktree",
    )
    return parser.parse_args()


def parse_image(frame: str, payload_hex: str) -> ImageRecord | None:
    try:
        payload = bytes.fromhex(payload_hex)
    except ValueError as error:
        raise ValueError(f"frame {frame}: invalid hexadecimal payload") from error

    if len(payload) < HEADER_SIZE:
        return None

    status = int.from_bytes(payload[0:2], "little")
    declared_length = int.from_bytes(payload[2:6], "little")
    width = int.from_bytes(payload[6:8], "little")
    height = int.from_bytes(payload[8:10], "little")
    pixels = payload[HEADER_SIZE:]

    if status != 0 or declared_length != len(payload) - 6:
        return None
    if width == 0 or height == 0 or width * height != len(pixels):
        return None

    return ImageRecord(
        frame=frame,
        width=width,
        height=height,
        flags=payload[10:18],
        pixels=pixels,
    )


def find_git_worktree(path: Path) -> Path | None:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def load_images(path: Path) -> list[ImageRecord]:
    images: list[ImageRecord] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"line {line_number}: invalid JSON") from error

            if record.get("usb.endpoint_address") != "0x81":
                continue
            image = parse_image(
                str(record.get("frame.number", "?")),
                str(record.get("usb.capdata", "")),
            )
            if image is not None:
                images.append(image)
    return images


def write_pgm(path: Path, image: ImageRecord) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    with path.open("wb") as stream:
        stream.write(f"P5\n{image.width} {image.height}\n255\n".encode("ascii"))
        stream.write(image.pixels)


def main() -> int:
    args = parse_args()
    if not args.jsonl.is_file():
        print(f"normalized capture does not exist: {args.jsonl}", file=sys.stderr)
        return 2

    try:
        images = load_images(args.jsonl)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2

    if args.output_dir:
        worktree = find_git_worktree(args.output_dir)
        if worktree is not None:
            print(
                f"refusing to write biometric images inside Git worktree {worktree}",
                file=sys.stderr,
            )
            return 2
        args.output_dir.mkdir(parents=True, exist_ok=True)

    for index, image in enumerate(images, 1):
        digest = hashlib.sha256(image.pixels).hexdigest()
        print(
            f"image={index} frame={image.frame} size={image.width}x{image.height} "
            f"flags={image.flags.hex()} pixels={len(image.pixels)} "
            f"range={min(image.pixels)}..{max(image.pixels)} sha256={digest}"
        )
        if args.output_dir:
            write_pgm(args.output_dir / f"image-{index:03d}.pgm", image)

    print(f"images={len(images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

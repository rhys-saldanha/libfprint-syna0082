#!/usr/bin/env python3
"""Summarize a libfprint FP3 template without exposing biometric payloads."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from gi.repository import GLib


FP3_TYPE = GLib.VariantType.new("(issbymsmsia{sv}v)")
FEATURE_MAGIC = b"SY82FT01"
FEATURE_HEADER_SIZE = 12
FEATURE_ROW_SIZE = (2 + 128) * 4


def unbox(value: GLib.Variant) -> GLib.Variant:
    while value.get_type_string() == "v":
        value = value.get_variant()
    return value


def summarize(path: Path) -> None:
    encoded = path.read_bytes()
    if len(encoded) <= 3 or encoded[:3] != b"FP3":
        raise ValueError("not a libfprint FP3 template")

    container = GLib.Variant.new_from_bytes(
        FP3_TYPE,
        GLib.Bytes.new(encoded[3:]),
        False,
    ).get_normal_form()
    payload = unbox(container.get_child_value(9))

    print(f"file_size={len(encoded)}")
    print(f"container_type={container.get_type_string()}")
    print(f"payload_type={payload.get_type_string()}")
    print(f"sample_count={payload.n_children()}")

    if payload.get_type_string() != "aay":
        return

    for index in range(payload.n_children()):
        sample = payload.get_child_value(index)
        sample_data = bytes(sample.get_data_as_bytes().get_data())
        magic_valid = sample_data[: len(FEATURE_MAGIC)] == FEATURE_MAGIC
        count = (
            struct.unpack_from("<I", sample_data, len(FEATURE_MAGIC))[0]
            if len(sample_data) >= FEATURE_HEADER_SIZE and magic_valid
            else None
        )
        size_valid = (
            count is not None
            and len(sample_data) == FEATURE_HEADER_SIZE + count * FEATURE_ROW_SIZE
        )
        print(
            f"sample_{index}_size={len(sample_data)} "
            f"magic_valid={str(magic_valid).lower()} "
            f"feature_count={count if count is not None else 'unknown'} "
            f"size_valid={str(size_valid).lower()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    args = parser.parse_args()
    summarize(args.template)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

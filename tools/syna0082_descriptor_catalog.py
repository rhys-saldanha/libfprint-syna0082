#!/usr/bin/env python3
"""Inventory the vendor sensor-configuration catalog without dumping payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


DESCRIPTOR_SIZE = 0x50
SELECTOR_OFFSETS = tuple(range(0x10, 0x44, 4))
LENGTH_OFFSET = 0x44
PAYLOAD_POINTER_OFFSET = 0x48
DEFAULT_CATALOG_RVA = 0x161470


@dataclass(frozen=True)
class Descriptor:
    index: int
    rva: int
    selectors: tuple[int, ...]
    payload_length: int
    payload_rva: int
    payload_sha256: str
    container_header: str
    body_multiple_of_16: bool

    def as_json(self) -> dict[str, object]:
        return {
            "index": self.index,
            "descriptor_rva": f"0x{self.rva:x}",
            "selectors": [f"0x{value:x}" for value in self.selectors],
            "payload_length": self.payload_length,
            "payload_rva": f"0x{self.payload_rva:x}",
            "payload_sha256": self.payload_sha256,
            "container_header": self.container_header,
            "body_length": self.payload_length - 4,
            "body_multiple_of_16": self.body_multiple_of_16,
        }


class PEReader:
    def __init__(self, path: Path):
        try:
            import pefile
        except ImportError as exc:
            raise RuntimeError("pefile is required (python -m pip install pefile)") from exc
        self.path = path
        self.data = path.read_bytes()
        self.pe = pefile.PE(data=self.data, fast_load=True)
        self.image_base = self.pe.OPTIONAL_HEADER.ImageBase

    def read_rva(self, rva: int, length: int) -> bytes:
        if rva < 0 or length < 0:
            raise ValueError("negative RVA or length")
        try:
            offset = self.pe.get_offset_from_rva(rva)
        except Exception as exc:
            raise ValueError(f"RVA 0x{rva:x} is not mapped by the PE file") from exc
        value = self.data[offset:offset + length]
        if len(value) != length:
            raise ValueError(f"RVA 0x{rva:x} extends beyond the PE file")
        return value

    def pointer_to_rva(self, pointer: int) -> int:
        rva = pointer - self.image_base
        if rva < 0:
            raise ValueError(f"pointer 0x{pointer:x} is below the image base")
        return rva


def parse_descriptor(index: int, rva: int, record: bytes, reader: PEReader) -> Descriptor:
    if len(record) != DESCRIPTOR_SIZE:
        raise ValueError("descriptor must be exactly 0x50 bytes")
    if any(record[:0x10]):
        raise ValueError(f"descriptor {index} has a non-zero reserved prefix")
    selectors = tuple(struct.unpack_from("<I", record, offset)[0] for offset in SELECTOR_OFFSETS)
    payload_length = struct.unpack_from("<I", record, LENGTH_OFFSET)[0]
    payload_pointer = struct.unpack_from("<Q", record, PAYLOAD_POINTER_OFFSET)[0]
    payload_rva = reader.pointer_to_rva(payload_pointer)
    payload = reader.read_rva(payload_rva, payload_length)
    if payload_length < 4:
        raise ValueError(f"descriptor {index} payload is shorter than its container header")
    return Descriptor(
        index=index,
        rva=rva,
        selectors=selectors,
        payload_length=payload_length,
        payload_rva=payload_rva,
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        container_header=payload[:4].hex(),
        body_multiple_of_16=(payload_length - 4) % 16 == 0,
    )


def parse_catalog(reader: PEReader, catalog_rva: int, maximum: int = 4096) -> list[Descriptor]:
    descriptors = []
    for index in range(maximum):
        pointer = struct.unpack("<Q", reader.read_rva(catalog_rva + index * 8, 8))[0]
        if pointer == 0:
            return descriptors
        descriptor_rva = reader.pointer_to_rva(pointer)
        record = reader.read_rva(descriptor_rva, DESCRIPTOR_SIZE)
        descriptors.append(parse_descriptor(index, descriptor_rva, record, reader))
    raise ValueError(f"catalog is not null-terminated within {maximum} entries")


def match_payload(path: Path, descriptors: list[Descriptor], reader: PEReader) -> dict[str, object]:
    captured = path.read_bytes()
    candidates = [("complete", captured)]
    if captured:
        candidates.append(("command_byte_removed", captured[1:]))
    matches = []
    for form, candidate in candidates:
        digest = hashlib.sha256(candidate).hexdigest()
        for descriptor in descriptors:
            if len(candidate) != descriptor.payload_length or digest != descriptor.payload_sha256:
                continue
            # The hash is enough to identify ordinary input, but retain an exact
            # comparison so this remains correct even under adversarial input.
            if candidate == reader.read_rva(descriptor.payload_rva, descriptor.payload_length):
                matches.append({"form": form, "descriptor_index": descriptor.index})
    return {
        "file": path.name,
        "length": len(captured),
        "sha256": hashlib.sha256(captured).hexdigest(),
        "matches": matches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument(
        "--catalog-rva", type=lambda value: int(value, 0), default=DEFAULT_CATALOG_RVA,
        help=f"pointer-table RVA (default: 0x{DEFAULT_CATALOG_RVA:x})",
    )
    parser.add_argument("--payload", type=Path, help="identify a captured payload by hash/exact match")
    args = parser.parse_args()
    try:
        reader = PEReader(args.binary)
        descriptors = parse_catalog(reader, args.catalog_rva)
        result: dict[str, object] = {
            "binary": {
                "file": args.binary.name,
                "length": len(reader.data),
                "sha256": hashlib.sha256(reader.data).hexdigest(),
            },
            "catalog_rva": f"0x{args.catalog_rva:x}",
            "descriptor_size": DESCRIPTOR_SIZE,
            "descriptor_count": len(descriptors),
            "descriptors": [descriptor.as_json() for descriptor in descriptors],
        }
        if args.payload:
            result["payload_match"] = match_payload(args.payload, descriptors, reader)
        print(json.dumps(result, indent=2))
    except (OSError, RuntimeError, ValueError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

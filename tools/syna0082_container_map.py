#!/usr/bin/env python3
"""Map protected sensor-config containers and security-key catalogs by hash."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from syna0082_descriptor_catalog import DEFAULT_CATALOG_RVA, PEReader, parse_catalog


BLOCK_SIZE = 16
HEADER_SIZE = 4
SECURITY_KEY_RECORD_SIZE = 0x103
SECURITY_KEY_SIZE = 0x100
DEFAULT_SECURITY_KEY_CATALOG_RVAS = (0x13B3F0, 0x13C120)


@dataclass(frozen=True)
class RepeatedRun:
    left_descriptor: int
    right_descriptor: int
    left_block: int
    right_block: int
    block_count: int
    sha256: str

    def as_json(self) -> dict[str, object]:
        return {
            "left_descriptor": self.left_descriptor,
            "right_descriptor": self.right_descriptor,
            "left_body_block": self.left_block,
            "right_body_block": self.right_block,
            "payload_offset": HEADER_SIZE + self.left_block * BLOCK_SIZE,
            "length": self.block_count * BLOCK_SIZE,
            "sha256": self.sha256,
        }


def maximal_repeated_runs(payloads: list[bytes], minimum_blocks: int = 2) -> list[RepeatedRun]:
    """Return maximal equal aligned-block runs shared by different payloads."""
    blocks = [[p[i:i + BLOCK_SIZE] for i in range(HEADER_SIZE, len(p), BLOCK_SIZE)]
              for p in payloads]
    occurrences: dict[bytes, list[tuple[int, int]]] = defaultdict(list)
    for descriptor, values in enumerate(blocks):
        for position, value in enumerate(values):
            occurrences[value].append((descriptor, position))

    starts: set[tuple[int, int, int, int]] = set()
    for locations in occurrences.values():
        for left_index, (left_descriptor, left_block) in enumerate(locations):
            for right_descriptor, right_block in locations[left_index + 1:]:
                if left_descriptor == right_descriptor:
                    continue
                if (left_block and right_block and
                        blocks[left_descriptor][left_block - 1] ==
                        blocks[right_descriptor][right_block - 1]):
                    continue
                starts.add((left_descriptor, right_descriptor, left_block, right_block))

    runs = []
    for left_descriptor, right_descriptor, left_block, right_block in sorted(starts):
        count = 0
        while (left_block + count < len(blocks[left_descriptor]) and
               right_block + count < len(blocks[right_descriptor]) and
               blocks[left_descriptor][left_block + count] ==
               blocks[right_descriptor][right_block + count]):
            count += 1
        if count < minimum_blocks:
            continue
        value = b"".join(blocks[left_descriptor][left_block:left_block + count])
        runs.append(RepeatedRun(
            left_descriptor, right_descriptor, left_block, right_block, count,
            hashlib.sha256(value).hexdigest(),
        ))
    return runs


def summarize_containers(payloads: list[bytes]) -> dict[str, object]:
    if not payloads or any(len(payload) < HEADER_SIZE for payload in payloads):
        raise ValueError("all payloads must contain a four-byte header")
    if any((len(payload) - HEADER_SIZE) % BLOCK_SIZE for payload in payloads):
        raise ValueError("all payload bodies must be 16-byte aligned")
    body_blocks = [payload[offset:offset + BLOCK_SIZE]
                   for payload in payloads
                   for offset in range(HEADER_SIZE, len(payload), BLOCK_SIZE)]
    counts = Counter(body_blocks)
    repeated_values = sum(1 for count in counts.values() if count > 1)
    repeated_occurrences = sum(count for count in counts.values() if count > 1)
    runs = maximal_repeated_runs(payloads)
    return {
        "payload_count": len(payloads),
        "headers": dict(sorted(Counter(payload[:HEADER_SIZE].hex() for payload in payloads).items())),
        "body_block_size": BLOCK_SIZE,
        "body_block_count": len(body_blocks),
        "unique_body_block_count": len(counts),
        "repeated_body_block_value_count": repeated_values,
        "repeated_body_block_occurrence_count": repeated_occurrences,
        "cross_descriptor_runs_at_least_two_blocks": [run.as_json() for run in runs],
    }


def classify_security_key(key: bytes) -> tuple[str, str]:
    if len(key) != SECURITY_KEY_SIZE:
        raise ValueError("security key field must be 256 bytes")
    # The P-256 table stores 32-byte X and Y coordinates in two 68-byte
    # internal big-number slots. Hash the canonical X||Y form, not padding.
    if not any(key[32:68]) and not any(key[100:]) and any(key[:32]) and any(key[68:100]):
        canonical = key[:32] + key[68:100]
        return "p256_xy_in_68_byte_slots", hashlib.sha256(canonical).hexdigest()
    return "opaque_256_byte_integer", hashlib.sha256(key).hexdigest()


def parse_security_key_catalog(reader: PEReader, catalog_rva: int,
                               maximum: int = 256) -> list[dict[str, object]]:
    records = []
    for index in range(maximum):
        rva = catalog_rva + index * SECURITY_KEY_RECORD_SIZE
        record = reader.read_rva(rva, SECURITY_KEY_RECORD_SIZE)
        selector = record[:3]
        if selector[0] == 0:
            return records
        key = record[3:]
        layout, digest = classify_security_key(key)
        records.append({
            "index": index,
            "record_rva": f"0x{rva:x}",
            "selector": selector.hex(),
            "layout": layout,
            "canonical_key_sha256": digest,
        })
    raise ValueError(f"security-key catalog at 0x{catalog_rva:x} is not terminated")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--catalog-rva", type=lambda value: int(value, 0),
                        default=DEFAULT_CATALOG_RVA)
    parser.add_argument("--security-key-catalog-rva", action="append",
                        type=lambda value: int(value, 0), dest="key_rvas")
    args = parser.parse_args()
    try:
        reader = PEReader(args.binary)
        descriptors = parse_catalog(reader, args.catalog_rva)
        payloads = [reader.read_rva(item.payload_rva, item.payload_length)
                    for item in descriptors]
        key_rvas = args.key_rvas or list(DEFAULT_SECURITY_KEY_CATALOG_RVAS)
        result = {
            "binary_sha256": hashlib.sha256(reader.data).hexdigest(),
            "sensor_config_catalog_rva": f"0x{args.catalog_rva:x}",
            "containers": summarize_containers(payloads),
            "security_key_catalogs": [
                {
                    "catalog_rva": f"0x{rva:x}",
                    "records": parse_security_key_catalog(reader, rva),
                }
                for rva in key_rvas
            ],
        }
        print(json.dumps(result, indent=2))
    except (OSError, RuntimeError, ValueError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
PROTECTED_PREFIX_SIZE = 256
PROTECTED_BODY_OFFSET = HEADER_SIZE + PROTECTED_PREFIX_SIZE
SECURITY_KEY_RECORD_SIZE = 0x103
SECURITY_KEY_SIZE = 0x100
DEFAULT_SECURITY_KEY_CATALOG_RVAS = (0x13B3F0, 0x13C120)
COMMON_RSA_EXPONENTS = (3, 17, 65537)


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
    protected_body_blocks = sum(
        (len(payload) - PROTECTED_BODY_OFFSET) // BLOCK_SIZE
        for payload in payloads
    )
    return {
        "payload_count": len(payloads),
        "headers": dict(sorted(Counter(payload[:HEADER_SIZE].hex() for payload in payloads).items())),
        "body_block_size": BLOCK_SIZE,
        "observed_layout": {
            "header_offset": 0,
            "header_size": HEADER_SIZE,
            "protected_prefix_offset": HEADER_SIZE,
            "protected_prefix_size": PROTECTED_PREFIX_SIZE,
            "protected_body_offset": PROTECTED_BODY_OFFSET,
        },
        "body_block_count": len(body_blocks),
        "post_prefix_body_block_count": protected_body_blocks,
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


def has_pkcs1_v1_5_type_1_padding(encoded: bytes) -> bool:
    """Recognize a complete PKCS#1 v1.5 type-1 padded block."""
    if len(encoded) < 12 or not encoded.startswith(b"\x00\x01"):
        return False
    separator = encoded.find(b"\x00", 2)
    return (separator >= 10 and
            encoded[2:separator] == b"\xff" * (separator - 2) and
            separator + 1 < len(encoded))


def rsa_prefix_check(payloads: list[bytes], keys: list[bytes]) -> dict[str, object]:
    """Test protected prefixes against candidate RSA moduli without exposing bytes."""
    prefixes = [payload[HEADER_SIZE:PROTECTED_BODY_OFFSET] for payload in payloads]
    if any(len(prefix) != PROTECTED_PREFIX_SIZE for prefix in prefixes):
        raise ValueError("all payloads must contain the complete protected prefix")
    if any(len(key) != SECURITY_KEY_SIZE for key in keys):
        raise ValueError("all candidate RSA moduli must be 256 bytes")

    checks = 0
    representatives_below_modulus = 0
    matches = []
    for descriptor, prefix in enumerate(prefixes):
        for key_index, key in enumerate(keys):
            for modulus_byte_order in ("big", "little"):
                modulus = int.from_bytes(key, modulus_byte_order)
                if modulus <= 1:
                    continue
                for signature_byte_order in ("big", "little"):
                    signature = int.from_bytes(prefix, signature_byte_order)
                    for exponent in COMMON_RSA_EXPONENTS:
                        checks += 1
                        if signature >= modulus:
                            continue
                        representatives_below_modulus += 1
                        encoded = pow(signature, exponent, modulus).to_bytes(
                            PROTECTED_PREFIX_SIZE, "big"
                        )
                        if has_pkcs1_v1_5_type_1_padding(encoded):
                            matches.append({
                                "descriptor": descriptor,
                                "key_index": key_index,
                                "exponent": exponent,
                                "modulus_byte_order": modulus_byte_order,
                                "signature_byte_order": signature_byte_order,
                            })
    return {
        "candidate_key_count": len(keys),
        "common_exponents": list(COMMON_RSA_EXPONENTS),
        "interpretation_count": checks,
        "representatives_below_modulus": representatives_below_modulus,
        "strict_type_1_padding_matches": matches,
    }


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


def read_opaque_security_keys(reader: PEReader, catalog_rva: int,
                              maximum: int = 256) -> list[bytes]:
    """Read only opaque 256-byte values from a terminated security-key catalog."""
    keys = []
    for index in range(maximum):
        record = reader.read_rva(
            catalog_rva + index * SECURITY_KEY_RECORD_SIZE,
            SECURITY_KEY_RECORD_SIZE,
        )
        if record[0] == 0:
            return keys
        key = record[3:]
        if classify_security_key(key)[0] == "opaque_256_byte_integer":
            keys.append(key)
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
        opaque_keys = [
            key
            for rva in key_rvas
            for key in read_opaque_security_keys(reader, rva)
        ]
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
            "protected_prefix_rsa_check": rsa_prefix_check(payloads, opaque_keys),
        }
        print(json.dumps(result, indent=2))
    except (OSError, RuntimeError, ValueError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

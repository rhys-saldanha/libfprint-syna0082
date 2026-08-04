#!/usr/bin/env python3
"""Provision the two private 06cb:0082 initialization records locally.

The scan matrix always comes from the user's own normalized USB capture.  The
static protected configuration can come from that capture too, or be checked
and extracted from a locally installed Synaptics vendor DLL.  No proprietary
payload is printed or stored inside the source repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

import syna0082_descriptor_catalog as catalog


CONFIG_NAME = "config-06.bin"
MATRIX_NAME = "scan-matrix-02.bin"
MANIFEST_NAME = "manifest.json"
CONFIG_COMMAND = 0x06
CONFIG_PAYLOAD_LENGTH = 10_500
CONFIG_MESSAGE_LENGTH = CONFIG_PAYLOAD_LENGTH + 1
CONFIG_PREFIX = bytes.fromhex("0602000001")
MATRIX_LENGTH = 18_869
MATRIX_PREFIX = bytes.fromhex("0298000000")
MODE_OFFSET = 1_749
ACQUISITION_MODE = 0x02
DEFAULT_DESCRIPTOR_INDEX = 39
KNOWN_CATALOG_RVAS = (0x161470, 0x161370)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def find_git_worktree(path: Path) -> Path | None:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def capture_candidates(path: Path) -> tuple[set[bytes], set[bytes]]:
    configs: set[bytes] = set()
    matrices: set[bytes] = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
                payload = bytes.fromhex(record.get("usb.capdata", ""))
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(
                    f"line {line_number}: invalid normalized USB record"
                ) from error
            if record.get("usb.endpoint_address") != "0x01":
                continue
            if len(payload) == CONFIG_MESSAGE_LENGTH and payload.startswith(CONFIG_PREFIX):
                configs.add(payload)
            if (
                len(payload) == MATRIX_LENGTH
                and payload.startswith(MATRIX_PREFIX)
                and payload[MODE_OFFSET] == ACQUISITION_MODE
            ):
                matrices.add(payload)
    return configs, matrices


def config_from_reader(
    reader: catalog.PEReader,
    catalog_rva: int,
    descriptor_index: int = DEFAULT_DESCRIPTOR_INDEX,
) -> bytes:
    descriptors = catalog.parse_catalog(reader, catalog_rva)
    if descriptor_index >= len(descriptors):
        raise ValueError(
            f"descriptor {descriptor_index} is absent from the vendor catalog"
        )
    descriptor = descriptors[descriptor_index]
    if (
        descriptor.payload_length != CONFIG_PAYLOAD_LENGTH
        or descriptor.container_header != "02000001"
        or not descriptor.body_multiple_of_16
    ):
        raise ValueError(
            f"descriptor {descriptor_index} does not have the expected protected layout"
        )
    payload = reader.read_rva(descriptor.payload_rva, descriptor.payload_length)
    return bytes((CONFIG_COMMAND,)) + payload


def config_from_dll(
    path: Path,
    catalog_rva: int | None,
    descriptor_index: int = DEFAULT_DESCRIPTOR_INDEX,
) -> tuple[bytes, int, str]:
    reader = catalog.PEReader(path)
    candidates = (catalog_rva,) if catalog_rva is not None else KNOWN_CATALOG_RVAS
    successes: list[tuple[bytes, int]] = []
    errors: list[str] = []
    for candidate in candidates:
        try:
            successes.append(
                (config_from_reader(reader, candidate, descriptor_index), candidate)
            )
        except (ValueError, struct.error) as error:
            errors.append(f"0x{candidate:x}: {error}")
    unique = {value for value, _ in successes}
    if len(unique) != 1:
        detail = "; ".join(errors) if errors else "ambiguous catalog matches"
        raise ValueError(f"could not identify one supported vendor catalog ({detail})")
    value = next(iter(unique))
    selected_rva = next(rva for candidate, rva in successes if candidate == value)
    return value, selected_rva, sha256(reader.data)


def select_one(values: set[bytes], description: str) -> bytes:
    if len(values) != 1:
        raise ValueError(
            f"expected exactly one {description} in the capture, found {len(values)}"
        )
    return next(iter(values))


def provision(
    capture: Path,
    output_dir: Path,
    vendor_dll: Path | None = None,
    catalog_rva: int | None = None,
    descriptor_index: int = DEFAULT_DESCRIPTOR_INDEX,
) -> dict[str, object]:
    if not capture.is_file():
        raise ValueError(f"normalized capture does not exist: {capture}")
    if vendor_dll is not None and not vendor_dll.is_file():
        raise ValueError(f"vendor DLL does not exist: {vendor_dll}")
    worktree = find_git_worktree(output_dir)
    if worktree is not None:
        raise ValueError(
            f"refusing to write private device records inside Git worktree {worktree}"
        )

    configs, matrices = capture_candidates(capture)
    matrix = select_one(matrices, "acquisition scan matrix")
    config_source: dict[str, object]
    if vendor_dll is None:
        config = select_one(configs, "protected configuration")
        config_source = {"kind": "normalized-capture"}
    else:
        config, selected_rva, dll_digest = config_from_dll(
            vendor_dll, catalog_rva, descriptor_index
        )
        if configs and configs != {config}:
            raise ValueError(
                "captured protected configuration does not match the selected DLL descriptor"
            )
        config_source = {
            "kind": "vendor-dll",
            "vendor_binary_sha256": dll_digest,
            "catalog_rva": f"0x{selected_rva:x}",
            "descriptor_index": descriptor_index,
        }

    outputs = {
        CONFIG_NAME: config,
        MATRIX_NAME: matrix,
    }
    paths = [output_dir / name for name in (*outputs, MANIFEST_NAME)]
    existing = [path for path in paths if path.exists()]
    if existing:
        raise ValueError(f"refusing to overwrite existing output: {existing[0]}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in outputs.items():
        path = output_dir / name
        path.write_bytes(value)
        if os.name != "nt":
            path.chmod(0o600)

    manifest: dict[str, object] = {
        "schema": 1,
        "device": "usb:06cb:0082",
        "capture_sha256": sha256(capture.read_bytes()),
        "config_source": config_source,
        "files": [
            {"name": name, "length": len(value), "sha256": sha256(value)}
            for name, value in outputs.items()
        ],
    }
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if os.name != "nt":
        manifest_path.chmod(0o600)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="normalized USB JSON Lines capture")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--vendor-dll", type=Path)
    parser.add_argument(
        "--catalog-rva",
        type=lambda value: int(value, 0),
        help="override the known vendor catalog RVAs",
    )
    parser.add_argument(
        "--descriptor-index", type=int, default=DEFAULT_DESCRIPTOR_INDEX
    )
    args = parser.parse_args()
    try:
        manifest = provision(
            args.capture,
            args.output_dir,
            args.vendor_dll,
            args.catalog_rva,
            args.descriptor_index,
        )
        print(json.dumps(manifest, indent=2))
    except (OSError, RuntimeError, ValueError, struct.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

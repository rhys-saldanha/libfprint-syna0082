#!/usr/bin/env python3
"""Extract device-specific initialization blobs from normalized captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


EXPECTED = {
    "config-39.bin": (125, bytes.fromhex("3920bf0200")),
    "config-06.bin": (10501, bytes.fromhex("0602000001")),
    "scan-matrix-02.bin": (18869, bytes.fromhex("0298000000")),
}
MODE_OFFSET = 1749
ACQUISITION_MODE = 0x02


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def find_git_worktree(path: Path) -> Path | None:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def load_candidates(path: Path) -> dict[str, set[bytes]]:
    candidates = {name: set() for name in EXPECTED}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
                payload = bytes.fromhex(record.get("usb.capdata", ""))
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"line {line_number}: invalid record") from error

            if record.get("usb.endpoint_address") != "0x01":
                continue
            for name, (length, prefix) in EXPECTED.items():
                if len(payload) != length or not payload.startswith(prefix):
                    continue
                if (
                    name == "scan-matrix-02.bin"
                    and payload[MODE_OFFSET] != ACQUISITION_MODE
                ):
                    continue
                candidates[name].add(payload)
    return candidates


def main() -> int:
    args = parse_args()
    if not args.jsonl.is_file():
        print(f"normalized capture does not exist: {args.jsonl}", file=sys.stderr)
        return 2

    worktree = find_git_worktree(args.output_dir)
    if worktree is not None:
        print(
            f"refusing to write device-specific blobs inside Git worktree "
            f"{worktree}",
            file=sys.stderr,
        )
        return 2

    try:
        candidates = load_candidates(args.jsonl)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2

    selected: dict[str, bytes] = {}
    for name, values in candidates.items():
        if len(values) != 1:
            print(
                f"expected exactly one unique {name} payload, found {len(values)}",
                file=sys.stderr,
            )
            return 2
        selected[name] = next(iter(values))

    output_paths = [args.output_dir / name for name in selected]
    manifest_path = args.output_dir / "manifest.json"
    existing = [path for path in (*output_paths, manifest_path) if path.exists()]
    if existing:
        print(f"refusing to overwrite {existing[0]}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": 1, "source": args.jsonl.name, "files": []}
    for name, payload in selected.items():
        output = args.output_dir / name
        output.write_bytes(payload)
        manifest["files"].append(
            {
                "name": name,
                "length": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

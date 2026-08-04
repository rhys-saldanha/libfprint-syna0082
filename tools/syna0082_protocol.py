#!/usr/bin/env python3
"""Decode and validate normalized 06cb:0082 USB captures without replaying them."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "protocol" / "commands.json"


def load_schema(path: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).split(",", 1)[0].strip()
    try:
        return int(text, 0)
    except ValueError:
        try:
            return int(text, 16)
        except ValueError:
            return None


def _payload(record: dict[str, Any]) -> bytes:
    value = str(record.get("usb.capdata", "")).replace(":", "").replace(" ", "")
    try:
        return bytes.fromhex(value) if value else b""
    except ValueError as exc:
        raise ValueError(f"frame {record.get('frame.number')}: invalid usb.capdata") from exc


def read_capture(path: Path) -> list[dict[str, Any]]:
    records = []
    source = sys.stdin if str(path) == "-" else path.open(encoding="utf-8")
    try:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            payload = _payload(record)
            if payload:
                records.append({
                    "frame": _integer(record.get("frame.number")) or line_number,
                    "time": record.get("frame.time_relative", ""),
                    "endpoint": _integer(record.get("usb.endpoint_address")),
                    "transfer_type": _integer(record.get("usb.transfer_type")),
                    "request": _integer(record.get("usb.setup.bRequest")),
                    "payload": payload,
                })
    finally:
        if source is not sys.stdin:
            source.close()
    return sorted(records, key=lambda item: item["frame"])


def transactions(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for record in records:
        endpoint = record["endpoint"]
        if endpoint == 0x01:
            if pending is not None:
                result.append(pending)
            payload = record["payload"]
            pending = {"kind": "command", "frame": record["frame"], "payload": payload, "responses": []}
        elif endpoint == 0x81 and pending is not None:
            pending["responses"].append({"frame": record["frame"], "payload": record["payload"]})
        elif endpoint == 0x83:
            result.append({"kind": "interrupt", "frame": record["frame"], "payload": record["payload"]})
        elif record["transfer_type"] == 2 and record["request"] is not None:
            result.append({"kind": "control", "frame": record["frame"], "request": record["request"], "payload": record["payload"]})
    if pending is not None:
        result.append(pending)
    return sorted(result, key=lambda item: item["frame"])


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def public_payload(payload: bytes, include_payload: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {"length": len(payload), "sha256": digest(payload)}
    if payload:
        value["prefix"] = payload[:8].hex()
    if include_payload:
        value["payload"] = payload.hex()
    return value


def decoded(path: Path, include_payload: bool = False) -> dict[str, Any]:
    items = []
    for tx in transactions(read_capture(path)):
        item = {"kind": tx["kind"], "frame": tx["frame"]}
        if tx["kind"] == "command":
            item["opcode"] = f"{tx['payload'][0]:02x}"
            item.update(public_payload(tx["payload"], include_payload))
            item["responses"] = [public_payload(response["payload"], include_payload) for response in tx["responses"]]
        elif tx["kind"] == "control":
            item["request"] = f"{tx['request']:02x}"
            item.update(public_payload(tx["payload"], include_payload))
        else:
            item.update(public_payload(tx["payload"], include_payload))
        items.append(item)
    return {"capture": str(path), "transactions": items}


def validate_capture(path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    errors, warnings = [], []
    command_defs = schema["commands"]
    command_count: Counter[str] = Counter()
    for tx in transactions(read_capture(path)):
        if tx["kind"] != "command":
            continue
        opcode = f"{tx['payload'][0]:02x}"
        command_count[opcode] += 1
        definition = command_defs.get(opcode)
        if definition is None:
            warnings.append(f"frame {tx['frame']}: unknown opcode 0x{opcode}")
            continue
        if len(tx["payload"]) not in definition["lengths"]:
            errors.append(f"frame {tx['frame']}: 0x{opcode} length {len(tx['payload'])}, expected {definition['lengths']}")
        expected = definition.get("responses", [])
        observed = [len(response["payload"]) for response in tx["responses"]]
        if expected and observed != expected:
            warnings.append(f"frame {tx['frame']}: 0x{opcode} responses {observed}, expected {expected}")
    return {"capture": str(path), "valid": not errors, "errors": errors, "warnings": warnings, "command_counts": dict(sorted(command_count.items()))}


def diff_captures(paths: list[Path]) -> dict[str, Any]:
    groups: dict[tuple[str, int], list[tuple[str, bytes]]] = defaultdict(list)
    for path in paths:
        for tx in transactions(read_capture(path)):
            if tx["kind"] == "command":
                payload = tx["payload"]
                groups[(f"{payload[0]:02x}", len(payload))].append((str(path), payload))
    output = []
    for (opcode, length), values in sorted(groups.items()):
        variants = {digest(payload) for _, payload in values}
        differing = []
        if len(variants) > 1:
            baseline = values[0][1]
            differing = [index for index in range(length) if any(payload[index] != baseline[index] for _, payload in values[1:])]
        output.append({"opcode": opcode, "length": length, "occurrences": len(values), "variants": len(variants), "differing_offsets": differing})
    return {"captures": [str(path) for path in paths], "groups": output}


def coverage(paths: list[Path], schema: dict[str, Any]) -> dict[str, Any]:
    observed: Counter[str] = Counter()
    variants: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        for tx in transactions(read_capture(path)):
            if tx["kind"] == "command":
                opcode = f"{tx['payload'][0]:02x}"
                observed[opcode] += 1
                variants[opcode].add(digest(tx["payload"]))
    defined = set(schema["commands"])
    seen = set(observed)
    return {
        "captures": [str(path) for path in paths],
        "observed": {opcode: {"occurrences": observed[opcode], "variants": len(variants[opcode])} for opcode in sorted(seen)},
        "schema_not_observed": sorted(defined - seen),
        "observed_not_in_schema": sorted(seen - defined),
        "generator_coverage": sorted(opcode for opcode in seen if schema["commands"].get(opcode, {}).get("generator")),
    }


def generate(command: str, mode: str | None = None) -> bytes:
    command = command.lower().removeprefix("0x")
    if command in {"01", "19", "1a", "75"}:
        return bytes.fromhex(command)
    if command == "51":
        capture_modes = {None: 0x20, "image": 0x20, "transition": 0x00}
        if mode not in capture_modes:
            raise ValueError("0x51 mode must be image or transition")
        return bytes((0x51, 0x00, capture_modes[mode], 0x00, 0x00))
    if command == "39":
        if mode not in (None, "observed-v1"):
            raise ValueError("0x39 mode must be observed-v1")
        payload = bytearray(125)
        fields = {0: 0x39, 1: 0x20, 2: 0xBF, 3: 0x02, 5: 0xFF, 6: 0xFF, 9: 0x01, 10: 0xD1, 12: 0x20, 17: 0xD1, 18: 0xD1, 32: 0x20, 45: 0xFF, 46: 0xFF, 50: 0xD1, 52: 0x20, 72: 0x20}
        for offset, value in fields.items():
            payload[offset] = value
        return bytes(payload)
    raise ValueError(f"command 0x{command} is not independently generatable")


def write_generated(payload: bytes, output: Path | None) -> None:
    if output is None:
        print(payload.hex())
        return
    resolved = output.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("generated binary output must stay outside the Git worktree")
    if output.exists():
        raise ValueError(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    sub = parser.add_subparsers(dest="action", required=True)
    decode = sub.add_parser("decode")
    decode.add_argument("capture", type=Path)
    decode.add_argument("--include-payload", action="store_true")
    for name in ("diff", "validate", "coverage"):
        child = sub.add_parser(name)
        child.add_argument("captures", type=Path, nargs="+")
    generator = sub.add_parser("generate")
    generator.add_argument("command")
    generator.add_argument("--mode")
    generator.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        schema = load_schema(args.schema)
        if args.action == "decode":
            result = decoded(args.capture, args.include_payload)
        elif args.action == "diff":
            result = diff_captures(args.captures)
        elif args.action == "coverage":
            result = coverage(args.captures, schema)
        elif args.action == "validate":
            reports = [validate_capture(path, schema) for path in args.captures]
            result = {"valid": all(report["valid"] for report in reports), "reports": reports}
        else:
            write_generated(generate(args.command, args.mode), args.output)
            return 0
        print(json.dumps(result, indent=2))
        return 0 if result.get("valid", True) else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Normalize one USB device's TShark records into JSON Lines."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path


FIELDS = (
    "frame.number",
    "frame.time_relative",
    "usb.bus_id",
    "usb.device_address",
    "usb.endpoint_address",
    "usb.transfer_type",
    "usb.urb_type",
    "usb.urb_status",
    "usb.data_len",
    "usb.setup.bRequest",
    "usb.capdata",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--device-address", type=int, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tshark", default="tshark")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tshark = shutil.which(args.tshark)
    if tshark is None:
        print(f"TShark executable not found: {args.tshark}", file=sys.stderr)
        return 2
    if not args.capture.is_file():
        print(f"Capture does not exist: {args.capture}", file=sys.stderr)
        return 2

    command = [
        tshark,
        "-n",
        "-r",
        str(args.capture),
        "-Y",
        f"usb.device_address == {args.device_address}",
        "-T",
        "fields",
        "-E",
        "separator=\\t",
        "-E",
        "quote=d",
        "-E",
        "occurrence=a",
    ]
    for field in FIELDS:
        command.extend(("-e", field))

    result = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output = (
        args.output.open("w", encoding="utf-8", newline="\n")
        if args.output
        else sys.stdout
    )
    try:
        reader = csv.reader(
            result.stdout.splitlines(), delimiter="\t", quotechar='"'
        )
        for values in reader:
            values.extend([""] * (len(FIELDS) - len(values)))
            record = dict(zip(FIELDS, values, strict=False))
            output.write(json.dumps(record, separators=(",", ":")) + "\n")
    finally:
        if output is not sys.stdout:
            output.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create a hash-only static capability inventory for the vendor PE binary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


CATEGORIES = {
    "cryptoapi": re.compile(r"^(Crypt(?:AcquireContext|CreateHash|Decrypt|DestroyHash|DestroyKey|Encrypt|ExportKey|GenKey|GenRandom|GetHashParam|HashData|ImportKey|ProtectData|ReleaseContext|SignHash|UnprotectData|VerifySignature)[AW]?)$", re.I),
    "bcrypt": re.compile(r"^BCrypt(?:CreateHash|Decrypt|DeriveKey|DestroyHash|DestroyKey|Encrypt|FinalizeKeyPair|FinishHash|GenerateKeyPair|GenerateSymmetricKey|HashData|ImportKeyPair|OpenAlgorithmProvider|SecretAgreement|SignHash|VerifySignature)$", re.I),
    "registry": re.compile(r"^Reg(?:CloseKey|CreateKeyEx|DeleteKey|DeleteValue|EnumKeyEx|EnumValue|OpenKeyEx|QueryValueEx|SetValueEx)[AW]?$", re.I),
    "io": re.compile(r"^(?:ReadFile|WriteFile|DeviceIoControl|CreateFile[AW]?)$", re.I),
}

KEYWORDS = re.compile(
    r"calibration|firmware|erase|ownership|fingerprint|template|database|CryptProtectData|CryptUnprotectData",
    re.I,
)


def strings(data: bytes, minimum: int = 5) -> set[str]:
    ascii_values = {match.decode("ascii") for match in re.findall(rb"[ -~]{%d,}" % minimum, data)}
    # Do not treat the final byte of a neighbouring ASCII string as the first
    # UTF-16LE character when that ASCII string happens to end in NUL.
    wide_pattern = rb"(?<![ -~])(?:[ -~]\x00){%d,}" % minimum
    wide_values = {match.decode("utf-16le") for match in re.findall(wide_pattern, data)}
    return ascii_values | wide_values


def imported_symbols(path: Path) -> set[str]:
    executable = shutil.which("llvm-readobj")
    command = [executable, "--coff-imports", str(path)] if executable else None
    if command is None:
        executable = shutil.which("llvm-objdump") or shutil.which("objdump")
        command = [executable, "-p", str(path)] if executable else None
    if command is None:
        raise RuntimeError("llvm-readobj, llvm-objdump, or objdump is required")
    result = subprocess.run(command, check=True, capture_output=True, text=True, errors="replace")
    symbols = set()
    for line in result.stdout.splitlines():
        match = re.search(r"\bSymbol:\s+([A-Za-z_][A-Za-z0-9_@?$]+)", line)
        if match is None:
            # GNU/LLVM objdump -p prints the ordinal/hint before the symbol.
            match = re.search(r"^\s*[0-9a-fA-F]+\s+([A-Za-z_][A-Za-z0-9_@?$]+)\s*$", line)
        if match:
            symbols.add(match.group(1).split("@", 1)[0])
    return symbols


def inventory(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    imports = imported_symbols(path)
    capabilities = {
        category: sorted(symbol for symbol in imports if pattern.match(symbol))
        for category, pattern in CATEGORIES.items()
    }


def payload_provenance(payload: bytes, binary: bytes) -> dict[str, object]:
    embedded = None
    for payload_offset in range(len(payload)):
        binary_offset = binary.find(payload[payload_offset:])
        if binary_offset >= 0:
            embedded = {
                "payload_offset": payload_offset,
                "binary_offset": binary_offset,
                "length": len(payload) - payload_offset,
            }
            break
    return {
        "length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "embedded_suffix": embedded,
    }
    evidence = sorted(
        value for value in strings(data)
        if KEYWORDS.search(value) and len(value) <= 160
    )
    return {
        "file": path.name,
        "length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "capabilities": capabilities,
        "keyword_evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--payload", type=Path, help="map a captured payload without printing its bytes")
    args = parser.parse_args()
    try:
        result = inventory(args.binary)
        if args.payload:
            result["payload_provenance"] = payload_provenance(
                args.payload.read_bytes(), args.binary.read_bytes()
            )
        print(json.dumps(result, indent=2))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

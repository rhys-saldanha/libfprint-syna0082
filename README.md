# libfprint support research for Synaptics 06cb:0082

This repository tracks protocol research and driver work for the PQI My
Lockey / Synaptics WBDI fingerprint reader with USB ID `06cb:0082`.

The target device currently under test reports firmware revision `1.54` and a
single vendor-specific interface with these endpoints:

| Endpoint | Type | Direction |
| --- | --- | --- |
| `0x01` | Bulk | Host to device |
| `0x81` | Bulk | Device to host |
| `0x82` | Bulk | Device to host |
| `0x83` | Interrupt | Device to host |
| `0x84` | Interrupt | Device to host |

The device is not supported by current libfprint. The old
[Validity90 issue #32](https://github.com/nmikhailov/Validity90/issues/32)
contains partial USB experiments, not a working driver.

## Safety boundary

- No reset, firmware, database-delete, or template-delete commands.
- No raw USB replay until each command has been decoded and explicitly
  approved.
- Existing Windows Hello and Linux enrollments must remain intact.
- Captures, biometric data, serial numbers, and proprietary driver files stay
  outside Git.

## Layout

- `tools/inventory-windows.ps1`: read-only Windows device/driver inventory.
- `tools/inventory-linux`: read-only Linux USB/fprint inventory.
- `tools/setup-saber-root`: reproducible Arch build/capture dependencies.
- `tools/capture-windows.ps1`: bounded, single-device USBPcap capture helper.
- `tools/inspect-windows-calibration.ps1`: elevated, hash-only DPAPI
  inspection that never persists decrypted calibration data.
- `tools/run-windows-calibration-inspection.ps1`: one-shot scheduled-task
  launcher with collision checks and automatic cleanup.
- `tools/usbpcap-summary.py`: normalize one USB device's capture to JSON Lines.
- `tools/syna0082_protocol.py`: offline decode, diff, validation, safe message
  generation, and capture-coverage reports; see `docs/protocol-tooling.md`.
- `protocol/commands.json`: machine-readable command/risk/evidence schema.
- `tools/syna0082_driver_inventory.py`: hash-only static crypto, registry,
  I/O, firmware, and calibration capability inventory for the vendor DLL.
- `tools/syna0082_descriptor_catalog.py`: hash-only inventory of the vendor
  sensor-configuration descriptor catalog; it never prints table bytes.
- `tools/syna0082_container_map.py`: hash-only protected-container comparison,
  public-key catalog inventory, and strict RSA-prefix hypothesis check.
- `tools/DumpNamedFunctions.java`, `tools/DumpFunctionsBySourceString.java`,
  and `tools/DumpCallerTree.java`: generic headless-Ghidra helpers; decompiler
  output stays outside Git.
- `tools/syna0082_calibration_map.py`: report byte-range provenance from
  decrypted calibration to scan matrix without dumping either artifact.
- `tools/syna0082-image-summary.py`: validate raw image records and optionally
  extract them outside any Git worktree.
- `tools/syna0082_matcher.py`: independent descriptor-gallery matcher for the
  reader's unusually small image area; see `docs/matcher.md` for safety gates.
- `patches/libfprint/syna0082-matcher.cpp`: the same independent matcher
  integrated into the experimental libfprint image-device flow.
- `tools/syna0082-extract-init.py`: extract device-specific initialization
  blobs outside Git without replaying them.
- `probe/syna0082-info.c`: descriptor-only Linux inventory; it never opens the
  device or sends transfers.
- `probe/syna0082-query.c`: guarded 0x01/0x19/0x3e information-query probe;
  `0x3e` parses the read-only flash/partition inventory.
- `probe/syna0082-scan.c`: guarded single-frame acquisition probe; its `0x39`
  message is generated from fields while two unresolved device records remain
  outside Git.
- `udev/60-libfprint-06cb0082.rules`: grants the active local session access
  to the development reader without running probes as root.
- `udev/60-usbmon-wireshark.rules`: permits reproducible Linux USB captures
  for members of the `wireshark` group.
- `docs/capture-matrix.md`: repeatable Windows traffic-capture procedure.
- `docs/matcher.md`: matcher design, template handling, and validation status.
- `patches/`: eventual patches against a pinned upstream libfprint commit.
- `packaging/arch/PKGBUILD`: reversible Arch package for fprintd integration;
  it replaces `libfprint-git` only when explicitly installed with pacman.

## Development gates

1. Capture and document Windows initialization and verification traffic.
2. Decode framing, state transitions, counters, key exchange, and payloads.
3. Build a standalone read-only libusb probe.
4. Obtain explicit approval before any state-changing USB command.
5. Implement scan/enroll/verify behavior and port it to modern libfprint.
6. Validate through libfprint and fprintd, then prepare an upstream merge
   request.

The working upstream clone belongs outside this repository at
`~/src/libfprint-06cb0082`. Its exact base commit will be recorded in
`patches/UPSTREAM_COMMIT`, and reviewable commits will be exported with
`git format-patch`.

Build the safe descriptor probe with:

```bash
meson setup build
meson compile -C build
./build/syna0082-info
```

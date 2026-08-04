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
- `tools/syna0082-image-summary.py`: validate raw image records and optionally
  extract them outside any Git worktree.
- `probe/syna0082-info.c`: descriptor-only Linux inventory; it never opens the
  device or sends transfers.
- `docs/capture-matrix.md`: repeatable Windows traffic-capture procedure.
- `patches/`: eventual patches against a pinned upstream libfprint commit.

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

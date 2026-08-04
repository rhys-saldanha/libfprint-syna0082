# Development baseline

The pinned libfprint revision builds on Saber (Arch Linux) with GCC 16.1.1,
Meson 1.11.2, and Ninja 1.13.2.

Baseline command:

```bash
cd ~/src/libfprint-06cb0082
meson setup build -Ddoc=false
meson compile -C build
meson test -C build --print-errorlogs
```

Baseline result on 2026-08-04:

- 37 tests passed;
- 0 failed;
- 2 virtual-device tests skipped with status 77.

The Windows enrollment, match, and miss-then-match captures normalize to 336,
100, and 148 USB records respectively using `tools/usbpcap-summary.py`.

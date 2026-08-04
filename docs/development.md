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

The Windows cold-plug, enrollment, match, and miss-then-match captures normalize
to 54, 336, 100, and 148 USB records respectively using
`tools/usbpcap-summary.py`.

## Linux detection baseline

With the external reader attached to Saber on 2026-08-04, Linux enumerates it
as `06cb:0082`, firmware revision `1.54`, on bus 3 address 12 at 12 Mbps. The
descriptor-only probe reports one vendor-specific interface with this endpoint
layout:

| Endpoint | Direction | Type | Maximum packet |
| --- | --- | --- | ---: |
| `0x01` | out | bulk | 64 |
| `0x81` | in | bulk | 64 |
| `0x82` | in | bulk | 64 |
| `0x83` | in | interrupt | 8 |
| `0x84` | in | interrupt | 16 |

Installed versions are `libfprint-git 1.94.10.r188.g6df065c-1.1` and
`fprintd 1.94.5-2`. fprintd exposes only the laptop's built-in `Goodix MOC
Fingerprint Sensor`; it does not expose the external `06cb:0082` reader. This
is the expected unsupported-device baseline and confirms that a new libfprint
driver or device-ID implementation is required.

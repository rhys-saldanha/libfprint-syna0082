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

After adding the experimental `syna0082` driver and independent OpenCV matcher,
the current upstream tree passes 130/130 tests. OpenCV is linked as the minimal
core, image-processing, feature, geometry/calibration, and FLANN module set so
optional VTK/HDF modules do not leak into libfprint's introspection link.

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

The standalone C protocol parser validates the 18-byte image header, declared
record length, dimensions, metadata, and pixel span without accessing USB.
Its synthetic Meson test passes on Saber with warnings treated as errors.

## Development USB access

`udev/60-libfprint-06cb0082.rules` applies `uaccess` only to `06cb:0082`, so
the active local session can run libusb probes without root. The usbmon rule
sets monitor nodes to group `wireshark` and mode `0660`. Install both using
`tools/install-saber-udev`, add the developer to `wireshark`, and load the
kernel monitor when packet capture is needed:

```bash
sudo tools/install-saber-udev
sudo usermod -aG wireshark alperen
sudo modprobe usbmon
```

The single-frame probe consumes device-specific blobs kept outside Git:

```bash
build/syna0082-scan \
  --blob-dir ~/fingerprint-lab/device-data-06cb0082 \
  --output ~/fingerprint-lab/scan.pgm \
  --i-understand-device-state-will-change
```

On Saber, `tools/run-saber-captured-scan scan-linux-NN` records usbmon3 and the
probe log alongside the PGM while refusing to overwrite any existing output.

## fprintd integration

The development examples honor `LIBFPRINT_SYNA0082_BLOB_DIR`. The system
fprintd unit uses `ProtectHome=true`, so the driver defaults to
`/var/lib/libfprint/syna0082`. `tools/install-saber-fprintd-root` copies only
`config-39.bin`, `config-06.bin`, and `scan-matrix-02.bin` there as root-owned
mode-0600 files, installs the locally built package, and restarts fprintd if it
is already running.

The operation replaces the installed `libfprint-git` package. Saber keeps its
previous package in `/var/cache/pacman/pkg`, so rollback is available with
`pacman -U` using that cached package. Do not place the device blobs in Git.

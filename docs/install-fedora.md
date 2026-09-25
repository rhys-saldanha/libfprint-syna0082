# Fedora installation (manual, no packaging yet)

Validated on Fedora 44 Workstation against a real PQI My Lockey /
Synaptics WBDI reader (`06cb:0082`, firmware `1.54`). This is a manual
procedure, not an RPM; `packaging/` currently only covers Arch. Fedora/RPM
packaging is welcome as a contribution.

## 1. Provision the two private records

Follow the Windows-side capture and `syna0082_provision.py` steps in
[install.md](install.md) to obtain `config-06.bin` and
`scan-matrix-02.bin` for your physical reader. Nothing in this document
substitutes for that step.

One Fedora-specific capture note: if you capture on the Linux host while
the reader is passed through to a Windows VM (rather than capturing inside
the VM with USBPcap), and the VM's virtual USB controller is UHCI (as
opposed to XHCI), `usbmon` reports each individual USB transaction
separately instead of one reassembled URB per bulk transfer. The `0x06`
and `0x02` messages will show up **fragmented into 64-byte chunks**
(`wMaxPacketSize` for the bulk endpoints) rather than as single large
records, and `tools/usbpcap-summary.py` / `tools/syna0082_provision.py`
will find zero candidates in a capture like that. Reassemble consecutive
same-direction chunks on endpoint `0x01` (each run terminated by a
chunk shorter than 64 bytes) into complete messages before matching against
the expected lengths and prefixes. Capturing through an XHCI-attached
passthrough device instead avoids the fragmentation entirely.

## 2. Build dependencies

```
sudo dnf install -y meson ninja-build gcc gcc-c++ pkg-config \
  glib2-devel libusb1-devel nss-devel cairo-devel pixman-devel \
  gobject-introspection-devel libgusb-devel libgudev-devel \
  opencv-devel systemd-devel json-glib-devel
```

## 3. Build

```
git clone --branch fedora-support https://github.com/rhys-saldanha/libfprint-syna0082.git
# apply patches/0001-0009 to a fresh checkout of libfprint at
# patches/UPSTREAM_COMMIT, then:
meson setup build -Ddoc=false -Dudev_rules=disabled
ninja -C build
```

Introspection must stay enabled (the default): disabling it trips an
unrelated pre-existing bug in `tests/meson.build`'s driver-test globbing
when introspection bindings are absent.

## 4. Install the library

Fedora's `libfprint` is a normal RPM-tracked file. This manual install
replaces it in place; `rpm -V libfprint` will flag it as modified, and
`dnf upgrade` will silently revert it on the next libfprint update. Proper
RPM packaging (parallel to the Arch `-git` package) is the correct long-term
fix and is not done here yet.

```
sudo cp /usr/lib64/libfprint-2.so.2.0.0 /root/libfprint-2.so.2.0.0.stock-backup
sudo cp build/libfprint/libfprint-2.so.2.0.0 /usr/lib64/libfprint-2.so.2.0.0
sudo ldconfig
```

Two things that will silently break this if you get them wrong:

- **Never** overwrite the file while `fprintd` still has the old one
  mapped (e.g. a service left running from a previous test). Linux will
  happily let you rewrite the bytes under a running process's feet, and a
  later lazy page-fault into the now-mismatched file can crash it with
  `SIGILL`. Stop `fprintd` (`sudo systemctl stop fprintd`) before copying,
  then start it fresh afterward.
- **Never** name the backup file `libfprint-2.so.2.0.0.<anything>` in the
  same directory. `ldconfig` matches sonames loosely enough that a backup
  named e.g. `libfprint-2.so.2.0.0.stock-backup` can itself win the
  `libfprint-2.so.2` symlink race, silently pointing the system back at the
  old library. Keep backups outside `/usr/lib64` entirely (e.g. under
  `/root`).

## 5. Blob directory and SELinux

Fedora's `fprintd.service` runs confined (`fprintd_t`) under
`ProtectSystem=strict`. A directory you `mkdir` yourself under `/var/lib`
inherits the generic `var_lib_t` label, which `fprintd_t` is **not**
permitted to read — you'll see `avc: denied { read }` in `ausearch -m avc`
even though the files are readable by root. Use the `StateDirectory` the
unit already owns (`/var/lib/fprint`, labelled `fprintd_var_lib_t`)
instead of `/var/lib/libfprint/syna0082`:

```
sudo mkdir -p /var/lib/fprint/syna0082
sudo cp config-06.bin scan-matrix-02.bin /var/lib/fprint/syna0082/
sudo chown -R root:root /var/lib/fprint/syna0082
sudo chmod 700 /var/lib/fprint/syna0082
sudo chmod 600 /var/lib/fprint/syna0082/*.bin
sudo restorecon -Rv /var/lib/fprint/syna0082
```

Point the driver at it with a systemd drop-in (the driver's built-in
default of `/var/lib/libfprint/syna0082` does not have the right label and
is not writable by the unit):

```
sudo mkdir -p /etc/systemd/system/fprintd.service.d
sudo tee /etc/systemd/system/fprintd.service.d/10-syna0082-blobs.conf <<'EOF'
[Service]
Environment=LIBFPRINT_SYNA0082_BLOB_DIR=/var/lib/fprint/syna0082
EOF
sudo systemctl daemon-reload
sudo systemctl restart fprintd
```

## 6. USB passthrough permissions (VM-only capture setups)

If you provisioned the blobs by passing the physical reader through to a
QEMU/KVM VM (rather than capturing with USBPcap natively on Windows
hardware), the device node under `/dev/bus/usb/<bus>/<addr>` is
`root:root 0664` by default and QEMU's `usb-host` device silently degrades
to a non-functional stub (reporting a bogus Low-Speed placeholder instead
of erroring) if it can only open the node read-only. Either run QEMU as
root, or add a udev rule scoped to this exact device:

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="06cb", ATTR{idProduct}=="0082", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-syna0082-passthrough.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## 7. Known hardware quirks

The physical sensor appears to enter a low-power/idle USB state whenever no
host has actively talked to it for a while (matching `fprintd.service`'s
own default ~30 second idle auto-exit). The **first** attempt to activate
the device after such a gap reliably fails with `device was disconnected`
(visible as `usb <bus>-<port>: USB disconnect` immediately followed by a
fresh re-enumeration in `dmesg`) as the sensor wakes and re-enumerates.
This experimental driver retries that first activation once on the idle-wake
disconnect (patch 0006) and then proceeds normally.

Separately, the sensor only answers the init handshake in full once it has
seen a USB port reset; without one it silently acks the final init write
with a 2-byte stub instead of the expected scan configuration, and
activation fails with a short-read error every time (not just after an
idle gap - this reproduces on the very first activation since power-up).
The driver resets the device at the start of every `open` to cover this
(patch 0009), matching the same pattern `vfs7552.c` uses for a related
Validity-family device.

Neither quirk is currently handled if it happens **mid-enrollment**, i.e.
between two of the several finger touches a single enrollment requires: the
driver's wait for the next touch has no timeout, so a long pause between
touches can hang the operation rather than erroring or retrying. Keep
enrollment touches close together (a few seconds apart) until this is
addressed.

## 8. Validate

```
fprintd-enroll -f right-index-finger
fprintd-verify -f right-index-finger      # touch the same finger -> verify-match
fprintd-verify -f right-index-finger      # touch a different finger -> verify-no-match
```

All three passed against a real `06cb:0082` unit on Fedora 44 with this
patch series (0001-0009) applied. Not yet enabled for PAM/screen unlock,
consistent with the project's general threshold-tuning caveat in
[matcher.md](matcher.md).

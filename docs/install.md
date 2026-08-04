# End-to-end installation

This guide provisions a PQI My Lockey / Synaptics `06cb:0082` reader without
redistributing Synaptics software or another device's calibration. The tested
path uses Windows once to collect the reader's initialization records and Arch
Linux for the final libfprint/fprintd installation.

The two private records are not fingerprints:

- `config-06.bin` is a static protected sensor configuration selected from the
  proprietary Windows driver catalog;
- `scan-matrix-02.bin` contains device-specific calibration and must come from
  the reader being installed.

Download the Windows driver only from the
[official PQI product page](https://us.pqigroup.com/prod_driver.aspx?mnuid=1286&modid=138&prodid=1472).
Synaptics' published license does not permit publishing its software for
others to copy, so neither the DLL nor its extracted protected configuration
is redistributed here; review the
[Synaptics license terms](https://www.synaptics.com/legal) yourself.

Keep captures and generated records outside Git. They are ignored by this
repository, and the provisioning tool refuses to write into a Git worktree.

## 1. Prepare Windows capture tools

Install the official PQI/Synaptics driver, Python 3, and Wireshark with the
USBPcap component. Clone this repository, then run `USBPcapCMD.exe` without
arguments or inspect the USBPcap interfaces in Wireshark. Note:

- the USBPcap interface containing `VID_06CB&PID_0082`;
- the reader's USB device address on that interface.

The address is an ephemeral USB address, not the device serial number.

Create a private working directory outside the repository:

```powershell
New-Item -ItemType Directory -Force C:\fingerprint-lab\raw
```

## 2. Capture one initialized acquisition

Start a 45-second bounded capture. Replace the interface and device address
with the values observed above:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\capture-windows.ps1 `
  -Interface '\\.\USBPcap1' `
  -DeviceAddress 12 `
  -Name provision-01 `
  -DurationSeconds 45 `
  -Action 'Open fingerprint verification and touch the reader once' `
  -ExpectedOutcome 'One acquisition completes'
```

While it runs, open Windows Hello or PQI Fingerprint Manager, begin a
verification, and touch the reader once. Do not publish the resulting PCAP: it
may contain raw fingerprint frames and device identifiers.

Normalize only this USB address:

```powershell
py .\tools\usbpcap-summary.py `
  C:\fingerprint-lab\raw\provision-01.pcap `
  --device-address 12 `
  --output C:\fingerprint-lab\raw\provision-01.usb.jsonl
```

## 3. Provision the private records

The capture-only path needs no proprietary binary in the repository:

```powershell
py .\tools\syna0082_provision.py `
  C:\fingerprint-lab\raw\provision-01.usb.jsonl `
  --output-dir C:\fingerprint-lab\device-data-06cb0082
```

The command must find exactly one acquisition-mode scan matrix and one
protected configuration. It creates:

```text
config-06.bin
scan-matrix-02.bin
manifest.json
```

For an additional provenance check, locate the installed vendor DLL and ask
the provisioner to verify/extract catalog descriptor 39 locally:

```powershell
Get-ChildItem "$env:windir\System32\DriverStore\FileRepository" `
  -Recurse -Filter synaWudfBioUsb52.dll

py -m pip install pefile
py .\tools\syna0082_provision.py `
  C:\fingerprint-lab\raw\provision-01.usb.jsonl `
  --vendor-dll 'C:\path\to\synaWudfBioUsb52.dll' `
  --output-dir C:\fingerprint-lab\device-data-06cb0082-verified
```

Known catalog locations for driver versions 5.5.4021 and 5.5.4018 are detected
automatically. `--catalog-rva` exists only for a separately analyzed version.
The tool never prints the protected bytes and refuses to overwrite an existing
output.

## 4. Transfer only the provisioned directory

Copy the generated directory to Linux over a private channel. For example:

```powershell
scp -r C:\fingerprint-lab\device-data-06cb0082 `
  user@linux-host:~/fingerprint-lab/
```

Do not copy the PCAP into the source repository or attach it to a public issue.

## 5. Prepare patched libfprint on Arch Linux

Clone this repository and install build dependencies:

```bash
git clone https://github.com/oae/libfprint-syna0082.git
cd libfprint-syna0082
sudo tools/setup-arch-root
```

Create a fresh upstream libfprint clone at the pinned base and apply the four
reviewable patches:

```bash
tools/prepare-libfprint-source ~/src/libfprint-syna0082
```

The helper refuses to replace an existing directory. Build and test the Arch
package:

```bash
SYNA0082_LIBFPRINT_SOURCE=~/src/libfprint-syna0082 \
  tools/build-arch-package
```

The package build runs the complete libfprint test suite before producing the
package under `${XDG_CACHE_HOME:-$HOME/.cache}/syna0082/package-build`.

## 6. Install the package and records

Select the non-debug package that the preceding command printed, then install
it with the private record directory:

```bash
package=$(find "${XDG_CACHE_HOME:-$HOME/.cache}/syna0082/package-build" \
  -maxdepth 1 -type f \
  -name 'libfprint-syna0082-git-*.pkg.tar.zst' \
  ! -name '*-debug-*' -print -quit)

sudo tools/install-arch-fprintd-root \
  "$package" \
  "$HOME/fingerprint-lab/device-data-06cb0082"
```

On the first installation, pacman asks permission to replace the system
`libfprint` or `libfprint-git` package. Review and approve that transaction.
The installer then stores both records under `/var/lib/libfprint/syna0082` as
root-owned mode-0600 files and restarts fprintd. The previous package normally
remains available in `/var/cache/pacman/pkg` for rollback.

Unplug and reconnect the reader, then confirm both USB and fprintd detection:

```bash
lsusb -d 06cb:0082
busctl --system call net.reactivated.Fprint \
  /net/reactivated/Fprint/Manager \
  net.reactivated.Fprint.Manager GetDevices
```

If more than one fingerprint reader is present, inspect each returned device:

```bash
busctl --system introspect net.reactivated.Fprint \
  /net/reactivated/Fprint/Device/1 \
  net.reactivated.Fprint.Device
```

The target name is `Synaptics/PQI 06cb:0082`. Device numbers are assigned at
runtime and may differ from the example.

## 7. Enroll and verify

The standard fprintd command-line tools operate on fprintd's default device.
Confirm that the default path above resolves to the PQI reader before
enrolling, especially on laptops with a built-in sensor:

```bash
busctl --system call net.reactivated.Fprint \
  /net/reactivated/Fprint/Manager \
  net.reactivated.Fprint.Manager GetDefaultDevice

fprintd-enroll -f right-index-finger "$USER"
fprintd-verify -f right-index-finger "$USER"
```

Lift the finger fully between enrollment stages. A held touch is deliberately
release-gated and cannot satisfy two stages.

Successful integration should report `verify-match` for the enrolled finger
and `verify-no-match` for a different finger. Do not enable PAM, sudo, or
screen-unlock authentication yet: the independent matcher's current threshold
has passed bounded positive/negative testing but not a large population study.

## Other distributions

The four patches are distribution-independent Meson/libfprint changes, but
only the Arch package and service integration above have been exercised end to
end. Other distributions should package the prepared source rather than run an
untracked `sudo meson install` over their system libfprint. Contributions for
Debian, Fedora, and openSUSE packaging are welcome.

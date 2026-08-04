# Protocol observations

These observations come from USBPcap captures made with Windows driver
`5.5.4021.1052`. Raw payloads and biometric material are not committed.

## Transport

- Endpoint `0x01`: bulk host-to-device commands and payloads.
- Endpoint `0x81`: bulk device-to-host responses and payloads.
- Endpoint `0x83`: five-byte interrupt events associated with finger state.
- Endpoints `0x82` and `0x84` are exposed by the descriptor but were not
  active in the first enrollment and verification captures.
- The initialized device is silent when idle.

## Common session start

Enrollment and verification begin with the same one-byte commands on endpoint
`0x01`:

```text
1a
01
19
75
```

Immediately before `0x1a`, Windows sends a device-to-host vendor control
transfer with `bmRequestType=0xc0`, `bRequest=0x14`, `wValue=0`, `wIndex=0`,
and `wLength=2`. The reader returns `00 00`. This operation-control step is
required when reproducing the session start; bulk initialization alone is not
equivalent.

They are followed by a 125-byte message beginning `39 20 bf 02`, a
10,501-byte message beginning `06 02 00 00`, and an 18,869-byte message
beginning `02 98 00 00`. The large records may contain initialization,
cryptographic, or opaque vendor data; their meaning is not yet established.

The `cold-plug-01` capture starts before USB enumeration and records the device
being assigned address 7. After standard descriptor and configuration control
transfers, the Windows driver immediately sends these endpoint `0x01` payloads:

```text
01
19
08 60 20 00 80 0b 00 00 00 04
07 80 20 00 80 04
75
```

The device answers each command on endpoint `0x81`. This 54-packet trace lasts
107 ms and establishes that `01`, `19`, and `75` belong to cold initialization,
not only to an enrollment or verification operation. The earlier leading `1a`
was not present in this cold-plug trace, so its role remains operation-specific
or dependent on prior device state.

## Acquisition cycle

A finger acquisition begins with the five-byte host message:

```text
51 00 20 00 00
```

The first enrollment capture repeats the acquisition sequence fourteen times.
Each repetition includes a 125-byte `0x39` message and an 18,869-byte `0x02`
message, with device-to-host transfers commonly sized 8,082 and 2,154 bytes.

Endpoint `0x83` produces paired interrupt submissions/completions, with a
five-byte payload when a finger-state event is delivered.

### Raw image response

The 8,082-byte endpoint 0x81 response to 51 00 20 00 00 contains an 18-byte
header followed by an unencrypted 8-bit grayscale image:

    00 00             status
    8c 1f 00 00       bytes following this field (8,076)
    38 00             width (56)
    90 00             height (144)
    4d 01 08 00
    00 00 00 00       metadata/flags, not fully decoded
    ...               56 * 144 raw pixels

All fourteen enrollment samples and the normal verification samples have the
same dimensions and header. Pixel ranges span nearly the full 0-255 range and
the pixel hashes differ between acquisitions. One verification response ends
its header in 20 80 and has only a 116-141 pixel range; it is likely an empty,
invalid, or intermediate frame and must not yet be treated as a usable
fingerprint image.

No TLS record headers are present in the Windows captures. This device/driver
mode therefore appears to expose raw host-match image data without the
modified TLS transport used by the older Validity90 prototype. The
10,501-byte 0x06 payload is identical across the three operation captures,
while the 18,869-byte 0x02 payload has operation-dependent variants. Their
roles remain unknown.

## Windows calibration source

The Windows device instance stores a 26,470-byte DPAPI-protected
CalibrationData value below its Device Parameters/Device Data registry key.
No calibration bytes or registry exports are committed.

Static disassembly of driver version 5.5.4021.1052 shows that its
CryptUnprotectData wrapper passes NULL for optional entropy, reserved data,
prompt data, and description output. The wrapper selects either protect or
unprotect and passes a scope/flags value separately. Attempts to decrypt the
blob in the interactive Windows user's CurrentUser and LocalMachine contexts
both fail, which is consistent with it being protected in the WUDF service
account's DPAPI context. Accessing that context requires a separately approved
elevated diagnostic; it is not required for capture parsing.

An approved one-shot diagnostic running as SYSTEM successfully decrypted the
value in memory. The plaintext is 26,244 bytes with a SHA-256 of
15198b4707710388def9bdc7449dac558012776fc77681b4ee1397fba3dc236b
and Shannon entropy of approximately 4.88 bits per byte. The approved research
workflow later persisted it outside Git under `~/fingerprint-lab`; neither it
nor material derived from it is committed.

The diagnostic sampled non-overlapping 64-byte chunks every 256 bytes from
each large host-to-device capture payload. For all three observed 18,869-byte
0x02 variants, 33 of 74 sampled chunks occur verbatim in the calibration
plaintext. No sampled chunk from the 10,501-byte 0x06 payload occurs there.
This establishes that 0x02 is substantially assembled from calibration data,
while 0x06 has a different source.

The source of `0x06` is now localized precisely. Bytes `[1, 10501)` of the
captured message are identical to one contiguous 10,500-byte `.rdata` record
in the reference DLL (file offset 1,694,432); only the leading `0x06` command
byte is prepended. The DLL's adjacent descriptor records the same payload
length as `0x2904`. Thus `0x06` is a static vendor table, not per-session
ciphertext. The table is not copied into this repository; its internal format
still needs an independent specification or generator.

An exhaustive byte-sequence map strengthens that result: scan-matrix range
`[10356, 18869)` is exactly calibration range `[8915, 17428)`. This single
8,513-byte run accounts for 45.1163% of the complete `0x02` message. The
10,356-byte prefix contains structured sensor/register records and is not a
direct calibration copy. `tools/syna0082_calibration_map.py` reproduces this
mapping using only hashes, offsets, and lengths in its output.

The three captured 18,869-byte 0x02 variants differ at exactly one byte:
offset 1,749. The value is 0x02 for initial acquisition setup, 0x23 during
enrollment, and 0x13 during verification. All other 18,868 bytes are
identical. This identifies the record as a device-specific scan matrix with a
single operation-mode field, rather than an encrypted or per-scan payload.

## Verification outcomes

The successful lock-screen capture has one acquisition followed by short
commands `17`, `51 00 00 00 00`, another acquisition, then:

```text
04
52
39 01 00 00 ...
```

The miss-then-match capture contains two distinguishable acquisition groups:

- first attempt at roughly 6.32–7.12 seconds;
- second attempt at roughly 11.06–11.64 seconds.

The final `04`, `52`, and 125-byte `0x39` exchange is present after both
groups, but its payload differs. The exact status field must be isolated by
comparing repeated match and miss captures before assigning semantics.

## Current hypotheses

- `0x51` controls or requests acquisition.
- `0x83` reports touch/finger state.
- `0x39` is an envelope or operation-status structure.
- `0x06` and `0x02` carry session/configuration or cryptographic records.

These remain hypotheses, not stable command definitions. Replays should retain
strict length checks and save the resulting device state for comparison.

The five-byte capture-ready events observed so far are `03 42 04 00 40` and
`03 43 04 00 41`. Byte offset 2 (not offset 3) contains the shared `0x04`
capture-ready value; Windows sends `51 00 20 00 00` immediately afterward.

## Linux query validation

The guarded Linux probe successfully queried the reader on 2026-08-04 without
resetting or reconfiguring it. Command `0x01` returned 38 bytes beginning with
`00 00 10 b6 04`, matching the Windows capture. Command `0x19` returned the
expected 68-byte frame but began with `00 00 02 00 21`; the Windows capture's
`00 00 00 03 01` must therefore be treated as device state, not a fixed magic
prefix.

## Linux acquisition validation

The standalone Linux probe completed a single acquisition on 2026-08-04. It
sent the captured operation-control and bulk initialization sequence, observed
`03 42 04 00 40`, queued an 8,082-byte bulk-IN transfer, and sent
`51 00 20 00 00`. The response parsed as an 18-byte header plus a 56x144
grayscale frame with metadata `4d 01 08 00 00 00 00 00`.

The resulting PGM and simultaneous usbmon capture remain outside Git. The PGM
SHA-256 is `570d45ad8857eb868148d3bf5ef96b8a295c53d59d4a69c313a322bdca034cb6`.
Its uncalibrated appearance is consistent with raw frames extracted from the
Windows enrollment capture; it is not evidence of a failed USB transfer.

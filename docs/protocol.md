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
elevated diagnostic; it is not required for capture parsing and has not been
performed.

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

These are hypotheses, not command definitions. No message is approved for
Linux replay until its state effects have been determined.

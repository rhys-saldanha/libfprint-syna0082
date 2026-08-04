# Windows capture matrix

Use signed Wireshark and USBPcap releases. Start capture before inserting the
reader so the descriptors and initialization sequence are present. Store raw
files under `C:\fingerprint-lab\raw`; they are intentionally ignored by Git.

Before and after the matrix, run `tools/inventory-windows.ps1` and save the
JSON beside the captures.

| File prefix | Action | Repetitions |
| --- | --- | ---: |
| `cold-plug` | Insert the reader and wait 15 seconds | 3 |
| `idle` | Leave the initialized reader untouched for 30 seconds | 3 |
| `verify-match` | Verify with an already enrolled finger | 3 |
| `verify-miss` | Verify with an unenrolled finger | 3 |
| `verify-timeout` | Start verification and do not touch the reader | 3 |
| `lock-unlock` | Lock Windows and unlock with the reader | 3 |
| `sleep-resume` | Suspend, resume, and wait 15 seconds | 3 |

For every capture record:

- UTC start/end time;
- USBPcap root hub;
- USB device address;
- Windows action and expected outcome;
- SHA-256 of the PCAP;
- Windows driver version and INF name.

Do not capture enrollment, deletion, reset, or firmware operations in the
initial matrix. Adding an unused test finger and all deletion operations need
separate approval.

Normalize a capture after identifying its device address:

```powershell
python .\tools\usbpcap-summary.py `
  C:\fingerprint-lab\raw\cold-plug-01.pcapng `
  --device-address 7 `
  --output C:\fingerprint-lab\raw\cold-plug-01.usb.jsonl
```

## Completed captures

`cold-plug-01` was captured on 2026-08-04 from `USBPcap5`, with the newly
inserted reader assigned USB address 7. It contains 54 packets over 107 ms and
includes enumeration plus the first Windows-driver initialization commands.
Its PCAP SHA-256 is
`d42dccd0b42b27a0db83d2113914baf08ea01d05340355a07dad73e4e5cebe18`.

The PCAP, metadata JSON, and 54-line normalized JSONL remain outside Git under
`C:\fingerprint-lab\raw` and `/home/alperen/fingerprint-lab/raw`.

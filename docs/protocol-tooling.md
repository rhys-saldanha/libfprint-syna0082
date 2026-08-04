# Offline protocol tooling

`tools/syna0082_protocol.py` turns normalized USB JSON Lines into a stable,
machine-readable protocol view. It never opens the USB device and never sends
traffic. Payloads are represented by length, prefix, and SHA-256 unless the
caller explicitly requests them.

```bash
python tools/syna0082_protocol.py decode capture.usb.jsonl
python tools/syna0082_protocol.py validate capture.usb.jsonl
python tools/syna0082_protocol.py diff first.usb.jsonl second.usb.jsonl
python tools/syna0082_protocol.py coverage *.usb.jsonl
python tools/syna0082_protocol.py generate 39
```

Use `-` as the capture path to read JSON Lines from standard input. Binary
generation refuses to write inside this Git worktree and refuses to overwrite
an existing file. Commands `0x02`, `0x06`, `0x04`, `0x07`, `0x08`, `0x17`,
and `0x52` intentionally have no generator because their construction or
side effects are not independently understood.

The schema is `protocol/commands.json`. Confidence and risk describe the
current evidence, not a promise that a command is universally safe on other
firmware.

## Current capture coverage

Four captures contain all 13 command opcodes currently represented by the
schema. Across them:

- `0x02` occurs 22 times with three variants; only offset 1,749 differs.
- `0x39` occurs 24 times with four variants.
- `0x51` occurs 19 times with two variants; only offset 2 differs.
- `0x06` occurs three times and is byte-identical.
- No captured opcode is missing from the schema.

The field-built `0x39` `observed-v1` generator has SHA-256
`271b4d6a852fd14b50d8674e10f6345dfefdc837100f97585e001f7a6181392b`.
It matches every enrollment `0x39` record and the baseline records in both
verification captures. The three remaining variants are final/status records
and are deliberately not generated.

One lock/unlock transaction associates a six-byte response with `0x51`
instead of the normal 8,082-byte image. This is retained as a validation
warning because sequential endpoint pairing cannot distinguish every
asynchronous response without URB correlation.

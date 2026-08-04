# Development rules

- Ask before sending any raw command that may reset the reader, change
  firmware, alter its database, or add/delete fingerprint templates.
- Preserve all existing Windows Hello and Linux fingerprint enrollments.
- Do not commit PCAP files, fingerprint images/templates, device serials,
  proprietary Windows driver binaries, or credentials.
- Keep raw artifacts outside this repository in `C:\fingerprint-lab\raw` and
  `~/fingerprint-lab/raw`.
- Start with captured-traffic analysis and read-only device inspection.
- Use Conventional Commits.
- Keep third-party code attribution and license notices intact. Validity90 and
  libfprint-derived work must remain LGPL-2.1-or-later compatible.

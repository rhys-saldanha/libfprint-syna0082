# Public development rules

These instructions apply to human contributors and automated coding agents.

## Device safety

- Start with offline capture analysis and read-only device inspection.
- Never send a raw USB command to a physical reader without the operator's
  explicit approval for that exact experiment.
- Treat reset, firmware, flash, ownership, database, calibration-write, and
  fingerprint-template operations as destructive. Do not run them merely to
  test a hypothesis.
- Preserve existing Windows Hello and Linux enrollments. Ask before adding,
  replacing, or deleting any fingerprint template.
- Bound live experiments by command, duration, and expected response. Record a
  recovery control and power-cycle instructions when device state may change.

## Private and proprietary data

- Never commit USB captures, normalized raw traffic, fingerprint images,
  feature templates, device serial numbers, registry exports, calibration
  records, extracted initialization records, proprietary driver binaries, or
  credentials.
- Keep all such artifacts in a private directory outside every Git worktree.
  Do not attach them to public issues or CI artifacts.
- Public diagnostics should report only the minimum required metadata, such as
  lengths, offsets, status values, and cryptographic hashes. Do not print raw
  biometric or proprietary payloads.
- Do not vendor `config-06.bin` or `scan-matrix-02.bin`. Users must provision
  them locally by following `docs/install.md`.

## Source and patch workflow

- `patches/UPSTREAM_COMMIT` is the canonical libfprint base. The numbered
  patches in `patches/` must apply incrementally to that commit.
- Keep earlier non-installable research snapshots under `patches/legacy/`, not
  in the numbered install series.
- Do not vendor a complete libfprint or Validity90 source tree.
- Keep the mirrored driver sources under `patches/libfprint/` synchronized
  with the installable patch series.
- Preserve third-party copyright, attribution, and license notices. Original
  project code and libfprint-derived changes must remain compatible with
  LGPL-2.1-or-later.

## Validation and contributions

- Use Conventional Commits.
- Run `git diff --check` and the Python unit tests after tooling changes.
- Apply the full patch series to a fresh upstream clone after changing patches.
- Run the upstream libfprint test suite for driver or matcher changes.
- Keep installation and recovery instructions reproducible and update the
  public documentation whenever behavior, prerequisites, or file formats
  change.

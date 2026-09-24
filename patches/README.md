# libfprint patch series

`UPSTREAM_COMMIT` records the exact upstream base. Numbered patches 0001
through 0005 form an incremental series reproducing the current experimental
driver head `0e7802da`.

Patch 0005 fixes a real bug found provisioning a second physical unit on
Fedora: OpenCV's SIFT `nfeatures` cap is not strictly enforced (ties at the
response cutoff can yield `nfeatures+1` keypoints), which produced a
701-feature encoded reference against the hard 700 bound `decode_features()`
enforces on read, breaking every verification after a successful enrollment
with `Feature count is invalid (count=701)`. See `docs/install-fedora.md`
for the full validation this patch was tested against on real hardware.

`legacy/` keeps an earlier single-frame driver snapshot for research history.
It is superseded by patch 0001 and is not applied by the installation helper.

Do not vendor the complete upstream source tree or raw capture data.

# libfprint patch series

`UPSTREAM_COMMIT` records the exact upstream base. Numbered patches 0001
through 0007 form an incremental series reproducing the current driver head
(based on `0e7802da`, plus the two fixes below).

Patch 0005 fixes a real bug found provisioning a second physical unit on
Fedora: OpenCV's SIFT `nfeatures` cap is not strictly enforced (ties at the
response cutoff can yield `nfeatures+1` keypoints), which produced a
701-feature encoded reference against the hard 700 bound `decode_features()`
enforces on read, breaking every verification after a successful enrollment
with `Feature count is invalid (count=701)`. See `docs/install-fedora.md`
for the full validation this patch was tested against on real hardware.

Patch 0006 absorbs the hardware wake cycle: the sensor powers down its
imaging hardware when idle and wakes on the first vendor command, which the
physical device answers by dropping off the bus and re-enumerating as a
genuine new USB device. Any activation transfer in flight at that moment
failed with `G_USB_DEVICE_ERROR_NO_DEVICE` and aborted the action; the
patch waits for the reconnect to settle and restarts the activation once.

Patch 0007 stops reporting the sensor's power-down disconnect (an
outstanding interrupt poll answers with `NO_DEVICE` on release) as a
session error after the framework already went inactive, which tripped an
`fpi_image_device_activate_complete()` assertion on every normal session
end.

`legacy/` keeps an earlier single-frame driver snapshot for research history.
It is superseded by patch 0001 and is not applied by the installation helper.

Do not vendor the complete upstream source tree or raw capture data.

# Independent small-area matcher

`tools/syna0082_matcher.py` is an original matcher for the 56x144 image stream
produced by the PQI My Lockey / Synaptics 06cb:0082 reader. It uses only public
OpenCV primitives and observed input/output behavior. It contains no Synaptics
code, lookup tables, templates, or binary artifacts.

The proprietary Windows engine established two useful constraints without
dictating this implementation: matching is performed on the host, and its
test interface accepts an uncompressed ANSI-381 raster. The independent
matcher instead uses this pipeline:

1. Validate the native 56x144 grayscale raster.
2. Optionally subtract a sensor background image.
3. Upscale and locally normalize contrast.
4. Extract SIFT keypoints and descriptors.
5. Apply a Lowe ratio test between each enrollment sample and the probe.
6. Fit a partial affine transform with RANSAC.
7. Reject insufficient, inconsistent, degenerate, or implausibly scaled fits.
8. Accept one strong gallery fit or consensus from two moderate fits.

Enrollment templates contain keypoint coordinates and descriptors for several
samples, not the raw images. They are still sensitive biometric data and must
remain outside Git with mode 0600. The writer refuses to replace an existing
template.

Create a template from corrected, raster-order images:

```bash
python tools/syna0082_matcher.py enroll \
  --output ~/fingerprint-lab/right-index.npz \
  ~/fingerprint-lab/enroll/image-*.pgm
```

Verify one corrected capture:

```bash
python tools/syna0082_matcher.py verify \
  --template ~/fingerprint-lab/right-index.npz \
  ~/fingerprint-lab/probe.pgm
```

The verify command prints JSON and exits with status 0 for a match or 3 for a
non-match. Invalid input and processing failures use a different nonzero exit.

## Validation status

On 2026-08-04, a 14-sample Windows enrollment gallery was tested on Linux
against two new right-index captures and nine captures from five non-enrolled
fingers:

| Probe | Decision | Best ratio-test matches | RANSAC inliers | Inlier ratio |
| --- | --- | ---: | ---: | ---: |
| Right index 1 | match | 18 | 14 | 0.778 |
| Right index 2 | match | 58 | 47 | 0.810 |
| Left index | non-match | 11 | 7 | 0.636 |
| Right middle (2 captures) | non-match | 14 | 6 | 0.429 |
| Right ring (2 captures) | non-match | 3 | 3 | 1.000 |
| Left middle (2 captures) | non-match | 6 | 5 | 0.833 |
| Left thumb (2 captures) | non-match | 4 | 3 | 1.000 |

All 2/2 genuine probes were accepted and all 9/9 impostor probes were rejected.
High-ratio impostor fits had too few inliers, implausible scale, or insufficient
coverage. Three deterministic synthetic regression tests cover affine matching,
unrelated-pattern rejection, and template round-tripping without raw pixels.

The C++ port was then exercised through libfprint with a fresh five-touch
right-index gallery. A live right-index probe matched with 17 ratio-test matches
and 15 RANSAC inliers; a live right-middle probe was rejected with at most two
ratio-test matches against any gallery member. The reader's
repeated finger-on interrupt was also release-gated so one held touch cannot
satisfy two enrollment stages. The complete upstream libfprint suite passes
130/130 tests with the matcher enabled.

The same positive/negative behavior was subsequently validated through the
system fprintd service: a stored right-index print produced `verify-match`, and
a right-middle probe produced `verify-no-match`. This confirms the complete
device, libfprint serialization, fprintd storage, and reload path rather than
only the standalone matcher.

These thresholds are experimental. Five impostor fingers are not enough to
estimate useful false-accept or false-reject rates, so the matcher must not yet be
enabled for PAM, sudo, screen unlock, or other security decisions. The next
gate is a labeled dataset containing repeated captures from several enrolled
and non-enrolled fingers, followed by threshold selection on disjoint data.

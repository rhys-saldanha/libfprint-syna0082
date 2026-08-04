#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "tools" / "syna0082_matcher.py"
SPEC = importlib.util.spec_from_file_location("syna0082_matcher", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
matcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = matcher
SPEC.loader.exec_module(matcher)


def texture(seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    image = np.full(matcher.NATIVE_SHAPE, 220, dtype=np.uint8)
    for _ in range(45):
        x = int(generator.integers(3, matcher.NATIVE_SHAPE[1] - 3))
        y = int(generator.integers(3, matcher.NATIVE_SHAPE[0] - 3))
        length = int(generator.integers(6, 20))
        angle = float(generator.uniform(-np.pi, np.pi))
        end = (
            int(round(x + length * np.cos(angle))),
            int(round(y + length * np.sin(angle))),
        )
        cv2.line(image, (x, y), end, int(generator.integers(20, 90)), 1, cv2.LINE_AA)
    image = cv2.GaussianBlur(image, (3, 3), 0.7)
    noise = generator.normal(0, 2.0, image.shape)
    return np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def transformed(image: np.ndarray, angle: float, x: float, y: float) -> np.ndarray:
    center = (image.shape[1] / 2.0, image.shape[0] / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    matrix[:, 2] += (x, y)
    return cv2.warpAffine(
        image,
        matrix,
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )


class MatcherTests(unittest.TestCase):
    def test_affine_variant_matches(self) -> None:
        reference = matcher.extract(texture(4))
        probe = matcher.extract(transformed(texture(4), 7.0, 2.0, -3.0))
        score = matcher.compare(reference, probe)
        self.assertTrue(score.accepted, score)
        self.assertGreaterEqual(score.inliers, matcher.DEFAULT_MIN_STRONG_INLIERS)

    def test_unrelated_texture_is_rejected(self) -> None:
        reference = matcher.extract(texture(4))
        probe = matcher.extract(texture(99))
        score = matcher.compare(reference, probe)
        self.assertFalse(score.accepted, score)

    def test_template_round_trip_contains_no_raw_image(self) -> None:
        base = texture(7)
        samples = [
            matcher.extract(base),
            matcher.extract(transformed(base, -4.0, 1.0, 2.0)),
            matcher.extract(transformed(base, 5.0, -2.0, -1.0)),
        ]
        probe = matcher.extract(transformed(base, 2.0, 1.0, -2.0))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.npz"
            matcher.save_template(path, samples)
            with np.load(path, allow_pickle=False) as archive:
                self.assertFalse(any("image" in key or "pixel" in key for key in archive.files))
            restored = matcher.load_template(path)
        result = matcher.verify(restored, probe)
        self.assertTrue(result.matched, result)


if __name__ == "__main__":
    unittest.main()

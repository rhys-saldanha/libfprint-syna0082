#!/usr/bin/env python3
"""Research a small-area matcher for Synaptics/PQI 06cb:0082 images."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def load(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"cannot read {path}")
    if image.shape == (288, 112):
        image = cv2.resize(image, (56, 144), interpolation=cv2.INTER_AREA)
    if image.shape != (144, 56):
        raise ValueError(f"unexpected image shape {image.shape} in {path}")
    return image


def preprocess(image: np.ndarray) -> np.ndarray:
    image = image.astype(np.float32)
    background = cv2.GaussianBlur(image, (0, 0), 5.0)
    detail = image - background
    scale = float(np.std(detail))
    if scale < 1.0:
        raise ValueError("image has no usable contrast")
    return detail / scale


def score(reference: np.ndarray, probe: np.ndarray) -> tuple[float, float, int, int]:
    reference = preprocess(reference)
    probe = preprocess(probe)
    # Match a central crop so normal placement differences retain substantial
    # overlap. Padding permits translation without inventing edge texture.
    crop = reference[20:124, 8:48]
    padded = cv2.copyMakeBorder(probe, 30, 30, 24, 24, cv2.BORDER_CONSTANT, value=0)
    best = (-1.0, 0.0, 0, 0)
    center = (padded.shape[1] / 2.0, padded.shape[0] / 2.0)
    for angle in np.arange(-30.0, 30.01, 2.0):
        transform = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(
            padded,
            transform,
            (padded.shape[1], padded.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        result = cv2.matchTemplate(rotated, crop, cv2.TM_CCOEFF_NORMED)
        _, maximum, _, location = cv2.minMaxLoc(result)
        candidate = (float(maximum), float(angle), int(location[0]), int(location[1]))
        if candidate[0] > best[0]:
            best = candidate
    return best


def feature_score(reference: np.ndarray, probe: np.ndarray) -> tuple[int, int, float]:
    reference = cv2.resize(reference, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    probe = cv2.resize(probe, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    detector = cv2.SIFT_create(nfeatures=500, contrastThreshold=0.01, edgeThreshold=15)
    keypoints_a, descriptors_a = detector.detectAndCompute(reference, None)
    keypoints_b, descriptors_b = detector.detectAndCompute(probe, None)
    if descriptors_a is None or descriptors_b is None:
        return 0, 0, 0.0
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(descriptors_a, descriptors_b, k=2)
    good = [first for first, second in pairs if first.distance < 0.72 * second.distance]
    if len(good) < 3:
        return len(good), 0, 0.0
    points_a = np.float32([keypoints_a[item.queryIdx].pt for item in good])
    points_b = np.float32([keypoints_b[item.trainIdx].pt for item in good])
    _, mask = cv2.estimateAffinePartial2D(
        points_a,
        points_b,
        method=cv2.RANSAC,
        ransacReprojThreshold=8.0,
        maxIters=2000,
        confidence=0.995,
    )
    inliers = int(mask.sum()) if mask is not None else 0
    return len(good), inliers, inliers / max(len(good), 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("probes", type=Path, nargs="+")
    args = parser.parse_args()

    reference = load(args.reference)
    for path in args.probes:
        probe = load(path)
        value, angle, x, y = score(reference, probe)
        matches, inliers, ratio = feature_score(reference, probe)
        print(
            f"{path}: score={value:.6f} angle={angle:.1f} location={x},{y} "
            f"sift_matches={matches} sift_inliers={inliers} sift_ratio={ratio:.3f}"
        )


if __name__ == "__main__":
    main()

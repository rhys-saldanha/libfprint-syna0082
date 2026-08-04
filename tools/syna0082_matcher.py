#!/usr/bin/env python3
"""Independent small-area fingerprint matcher for Synaptics/PQI 06cb:0082.

This implementation is based on public computer-vision primitives and observed
input/output behaviour. It does not contain code, constants, or templates from
the proprietary Synaptics matcher.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


NATIVE_SHAPE = (144, 56)
TEMPLATE_VERSION = 1
UPSCALE = 4
RATIO_THRESHOLD = 0.72
RANSAC_THRESHOLD = 8.0
MIN_ENROLLMENT_SAMPLES = 3
MIN_KEYPOINTS = 8
DEFAULT_MIN_INLIERS = 6
DEFAULT_MIN_INLIER_RATIO = 0.65
DEFAULT_MIN_STRONG_INLIERS = 8


@dataclass(frozen=True)
class FeatureSet:
    points: np.ndarray
    descriptors: np.ndarray
    quality: float


@dataclass(frozen=True)
class PairScore:
    matches: int
    inliers: int
    inlier_ratio: float
    scale: float
    rotation: float
    coverage: float

    @property
    def accepted(self) -> bool:
        return (
            self.inliers >= DEFAULT_MIN_INLIERS
            and self.inlier_ratio >= DEFAULT_MIN_INLIER_RATIO
            and 0.70 <= self.scale <= 1.35
            and self.coverage >= 0.015
        )


@dataclass(frozen=True)
class Verification:
    matched: bool
    best: PairScore
    accepted_samples: int
    sample_count: int


def load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"cannot read image: {path}")
    if image.shape == (288, 112):
        image = cv2.resize(image, (56, 144), interpolation=cv2.INTER_AREA)
    if image.shape != NATIVE_SHAPE:
        raise ValueError(f"unexpected image shape {image.shape} in {path}")
    if float(np.std(image)) < 3.0:
        raise ValueError(f"image contrast is too low: {path}")
    return image


def prepare_image(image: np.ndarray, background: np.ndarray | None = None) -> np.ndarray:
    if background is not None:
        if background.shape != image.shape:
            raise ValueError("background and sample dimensions differ")
        # Preserve both ridge polarities while removing fixed-pattern sensor
        # structure. A mid-gray bias avoids clipping negative differences.
        image = np.clip(
            image.astype(np.int16) - background.astype(np.int16) + 128,
            0,
            255,
        ).astype(np.uint8)

    enlarged = cv2.resize(
        image,
        None,
        fx=UPSCALE,
        fy=UPSCALE,
        interpolation=cv2.INTER_CUBIC,
    )
    # Local contrast normalization makes descriptors less sensitive to the LED
    # level and to gradual background variation across this narrow sensor.
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 8)).apply(enlarged)


def extract(image: np.ndarray, background: np.ndarray | None = None) -> FeatureSet:
    prepared = prepare_image(image, background)
    detector = cv2.SIFT_create(
        nfeatures=700,
        contrastThreshold=0.01,
        edgeThreshold=15,
        sigma=1.6,
    )
    keypoints, descriptors = detector.detectAndCompute(prepared, None)
    if descriptors is None or len(keypoints) < MIN_KEYPOINTS:
        raise ValueError("sample contains too few stable keypoints")
    points = np.asarray([point.pt for point in keypoints], dtype=np.float32)
    descriptors = np.asarray(descriptors, dtype=np.float32)
    # Quality is deliberately descriptive, not an authentication score.
    occupied = np.ptp(points, axis=0)
    area_ratio = float(np.prod(occupied) / np.prod(prepared.shape[::-1]))
    quality = min(1.0, len(keypoints) / 120.0) * min(1.0, area_ratio / 0.35)
    return FeatureSet(points=points, descriptors=descriptors, quality=quality)


def _ratio_matches(first: FeatureSet, second: FeatureSet) -> list[cv2.DMatch]:
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(
        first.descriptors,
        second.descriptors,
        k=2,
    )
    return [
        near
        for pair in pairs
        if len(pair) == 2
        for near, far in [pair]
        if near.distance < RATIO_THRESHOLD * far.distance
    ]


def compare(reference: FeatureSet, probe: FeatureSet) -> PairScore:
    matches = _ratio_matches(reference, probe)
    if len(matches) < 3:
        return PairScore(len(matches), 0, 0.0, 0.0, 0.0, 0.0)

    reference_points = np.float32([reference.points[item.queryIdx] for item in matches])
    probe_points = np.float32([probe.points[item.trainIdx] for item in matches])
    transform, mask = cv2.estimateAffinePartial2D(
        reference_points,
        probe_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=RANSAC_THRESHOLD,
        maxIters=3000,
        confidence=0.997,
        refineIters=10,
    )
    if transform is None or mask is None:
        return PairScore(len(matches), 0, 0.0, 0.0, 0.0, 0.0)

    selected = mask.ravel().astype(bool)
    inliers = int(selected.sum())
    ratio = inliers / len(matches)
    scale = math.hypot(float(transform[0, 0]), float(transform[1, 0]))
    rotation = math.degrees(math.atan2(float(transform[1, 0]), float(transform[0, 0])))
    if inliers >= 2:
        spread = np.ptp(reference_points[selected], axis=0)
        coverage = float(np.prod(spread) / ((NATIVE_SHAPE[1] * UPSCALE) * (NATIVE_SHAPE[0] * UPSCALE)))
    else:
        coverage = 0.0
    return PairScore(len(matches), inliers, ratio, scale, rotation, coverage)


def _score_key(score: PairScore) -> tuple[int, float, float]:
    return score.inliers, score.inlier_ratio, score.coverage


def verify(features: Iterable[FeatureSet], probe: FeatureSet) -> Verification:
    scores = [compare(reference, probe) for reference in features]
    if not scores:
        raise ValueError("template contains no enrollment samples")
    best = max(scores, key=_score_key)
    accepted = sum(score.accepted for score in scores)
    # One strong geometric fit is sufficient. Two moderate fits also accept a
    # placement that overlaps different parts of the narrow enrollment strip.
    matched = (
        best.accepted
        and (best.inliers >= DEFAULT_MIN_STRONG_INLIERS or accepted >= 2)
    )
    return Verification(matched, best, accepted, len(scores))


def save_template(path: Path, samples: list[FeatureSet]) -> None:
    if len(samples) < MIN_ENROLLMENT_SAMPLES:
        raise ValueError(f"at least {MIN_ENROLLMENT_SAMPLES} enrollment samples are required")
    if path.exists():
        raise FileExistsError(f"refusing to overwrite template: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {}
    metadata = {
        "format": "syna0082-independent-features",
        "version": TEMPLATE_VERSION,
        "native_shape": list(NATIVE_SHAPE),
        "upscale": UPSCALE,
        "sample_count": len(samples),
        "algorithm": "SIFT-Lowe-RANSAC-gallery",
    }
    arrays["metadata"] = np.frombuffer(
        json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
        dtype=np.uint8,
    )
    for index, sample in enumerate(samples):
        arrays[f"points_{index:03d}"] = sample.points
        arrays[f"descriptors_{index:03d}"] = sample.descriptors
        arrays[f"quality_{index:03d}"] = np.asarray([sample.quality], dtype=np.float32)

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, **arrays)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_template(path: Path) -> list[FeatureSet]:
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(bytes(archive["metadata"]).decode("utf-8"))
        if metadata.get("format") != "syna0082-independent-features":
            raise ValueError("unsupported template format")
        if metadata.get("version") != TEMPLATE_VERSION:
            raise ValueError("unsupported template version")
        count = int(metadata["sample_count"])
        samples = []
        for index in range(count):
            points = np.asarray(archive[f"points_{index:03d}"], dtype=np.float32)
            descriptors = np.asarray(archive[f"descriptors_{index:03d}"], dtype=np.float32)
            quality = float(archive[f"quality_{index:03d}"][0])
            if points.ndim != 2 or points.shape[1] != 2:
                raise ValueError("invalid point array in template")
            if descriptors.ndim != 2 or len(descriptors) != len(points):
                raise ValueError("invalid descriptor array in template")
            samples.append(FeatureSet(points, descriptors, quality))
        return samples


def _pair_dict(score: PairScore) -> dict[str, object]:
    return {
        "matches": score.matches,
        "inliers": score.inliers,
        "inlier_ratio": round(score.inlier_ratio, 4),
        "scale": round(score.scale, 4),
        "rotation": round(score.rotation, 3),
        "coverage": round(score.coverage, 4),
        "accepted": score.accepted,
    }


def command_enroll(args: argparse.Namespace) -> int:
    background = load_image(args.background) if args.background else None
    samples = [extract(load_image(path), background) for path in args.images]
    save_template(args.output, samples)
    print(json.dumps({
        "template": str(args.output),
        "samples": len(samples),
        "quality": [round(sample.quality, 4) for sample in samples],
        "raw_images_stored": False,
    }))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    background = load_image(args.background) if args.background else None
    template = load_template(args.template)
    probe = extract(load_image(args.image), background)
    result = verify(template, probe)
    print(json.dumps({
        "matched": result.matched,
        "accepted_samples": result.accepted_samples,
        "sample_count": result.sample_count,
        "best": _pair_dict(result.best),
    }))
    return 0 if result.matched else 3


def command_evaluate(args: argparse.Namespace) -> int:
    """Score labeled research samples without using decisions as an exit code."""
    background = load_image(args.background) if args.background else None
    template = load_template(args.template)
    for path in args.images:
        probe = extract(load_image(path), background)
        result = verify(template, probe)
        print(json.dumps({
            "image": str(path),
            "matched": result.matched,
            "accepted_samples": result.accepted_samples,
            "sample_count": result.sample_count,
            "best": _pair_dict(result.best),
        }))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    enroll_parser = subparsers.add_parser("enroll", help="create a descriptor-only gallery template")
    enroll_parser.add_argument("--output", type=Path, required=True)
    enroll_parser.add_argument("--background", type=Path)
    enroll_parser.add_argument("images", type=Path, nargs="+")
    enroll_parser.set_defaults(handler=command_enroll)

    verify_parser = subparsers.add_parser("verify", help="verify one image against a gallery template")
    verify_parser.add_argument("--template", type=Path, required=True)
    verify_parser.add_argument("--background", type=Path)
    verify_parser.add_argument("image", type=Path)
    verify_parser.set_defaults(handler=command_verify)

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="score several research images and always return success",
    )
    evaluate_parser.add_argument("--template", type=Path, required=True)
    evaluate_parser.add_argument("--background", type=Path)
    evaluate_parser.add_argument("images", type=Path, nargs="+")
    evaluate_parser.set_defaults(handler=command_evaluate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

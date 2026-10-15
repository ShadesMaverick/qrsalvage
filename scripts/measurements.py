"""Shared, dependency-free measurements for recovery experiments."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypedDict

import numpy as np

RecoveryOutcome = Literal["correct", "wrong", "failed"]


class Interval(TypedDict):
    estimate: float
    low: float
    high: float


class CalibrationSummary(TypedDict):
    images: int
    brier: Interval
    log_loss: Interval
    ece: Interval
    accuracy: Interval


def classify_recovery(recovered: str | None, expected: str) -> RecoveryOutcome:
    """Classify a decode without treating a valid wrong payload as success."""
    if recovered is None:
        return "failed"
    return "correct" if recovered == expected else "wrong"


def count_recoveries(recovered: Iterable[str | None], expected: str) -> tuple[int, int, int]:
    """Return correct, wrong, and failed counts for known-answer experiments."""
    counts: dict[RecoveryOutcome, int] = {"correct": 0, "wrong": 0, "failed": 0}
    for text in recovered:
        counts[classify_recovery(text, expected)] += 1
    return counts["correct"], counts["wrong"], counts["failed"]


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = min(int(round(quantile * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[index]


def paired_difference(
    before: Iterable[bool],
    after: Iterable[bool],
    *,
    bootstrap: int = 2000,
    seed: int = 0,
) -> dict[str, float | int]:
    """Paired success-rate difference with a case-level bootstrap interval."""
    pairs = tuple(zip(before, after, strict=True))
    if not pairs:
        raise ValueError("paired comparison needs at least one case")
    improved = sum(not old and new for old, new in pairs)
    regressed = sum(old and not new for old, new in pairs)
    difference = (improved - regressed) / len(pairs)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(bootstrap):
        sample = rng.integers(0, len(pairs), len(pairs))
        draws.append(sum(int(pairs[i][1]) - int(pairs[i][0]) for i in sample) / len(pairs))
    return {
        "difference": difference,
        "low": _percentile(draws, 0.025),
        "high": _percentile(draws, 0.975),
        "improved": improved,
        "regressed": regressed,
        "pairs": len(pairs),
    }


def clustered_rate_interval(
    clusters: Iterable[Iterable[bool]],
    *,
    bootstrap: int = 2000,
    seed: int = 0,
) -> dict[str, float | int]:
    """Rate interval that resamples whole trials, preserving within-trial dependence."""
    groups = tuple(tuple(group) for group in clusters)
    if not groups or any(not group for group in groups):
        raise ValueError("clustered rate needs non-empty clusters")

    def rate(selected: Iterable[int]) -> float:
        values = [value for index in selected for value in groups[index]]
        return sum(values) / len(values)

    estimate = rate(range(len(groups)))
    rng = np.random.default_rng(seed)
    draws = [rate(rng.integers(0, len(groups), len(groups)).tolist()) for _ in range(bootstrap)]
    return {
        "rate": estimate,
        "low": _percentile(draws, 0.025),
        "high": _percentile(draws, 0.975),
        "clusters": len(groups),
        "trials": sum(len(group) for group in groups),
    }


def calibration_metrics(
    posterior: np.ndarray,
    truth: np.ndarray,
    *,
    bins: tuple[tuple[float, float], ...] = (
        (0.5, 0.7),
        (0.7, 0.9),
        (0.9, 0.99),
        (0.99, 0.999),
        (0.999, 1.001),
    ),
) -> dict[str, float]:
    """Brier score, log loss, ECE, and accuracy for dark-module probabilities."""
    probabilities = np.asarray(posterior, dtype=np.float64).ravel()
    expected = np.asarray(truth, dtype=bool).ravel()
    if probabilities.size == 0 or probabilities.shape != expected.shape:
        raise ValueError("posterior and truth need the same non-empty shape")
    clipped = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
    labels = expected.astype(np.float64)
    brier = float(np.mean((probabilities - labels) ** 2))
    log_loss = float(-np.mean(labels * np.log(clipped) + (1.0 - labels) * np.log1p(-clipped)))
    claimed = np.maximum(probabilities, 1.0 - probabilities)
    correct = (probabilities >= 0.5) == expected
    ece = 0.0
    for low, high in bins:
        inside = (claimed >= low) & (claimed < high)
        if inside.any():
            ece += (
                abs(float(claimed[inside].mean()) - float(correct[inside].mean()))
                * int(inside.sum())
                / probabilities.size
            )
    return {
        "brier": brier,
        "log_loss": log_loss,
        "ece": ece,
        "accuracy": float(correct.mean()),
    }


def bootstrap_image_metrics(
    images: Iterable[tuple[np.ndarray, np.ndarray]],
    *,
    bootstrap: int = 2000,
    seed: int = 0,
) -> CalibrationSummary:
    """Calibration intervals from image-level, rather than cell-level, resampling."""
    cases = tuple(images)
    if not cases:
        raise ValueError("calibration bootstrap needs at least one image")

    def score(indices: Iterable[int]) -> dict[str, float]:
        selected = tuple(indices)
        posterior = np.concatenate([np.asarray(cases[i][0]).ravel() for i in selected])
        truth = np.concatenate([np.asarray(cases[i][1]).ravel() for i in selected])
        return calibration_metrics(posterior, truth)

    estimate = score(range(len(cases)))
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {metric: [] for metric in estimate}
    for _ in range(bootstrap):
        measured = score(rng.integers(0, len(cases), len(cases)).tolist())
        for metric, value in measured.items():
            draws[metric].append(value)

    def interval(metric: str) -> Interval:
        return {
            "estimate": estimate[metric],
            "low": _percentile(draws[metric], 0.025),
            "high": _percentile(draws[metric], 0.975),
        }

    return {
        "images": len(cases),
        "brier": interval("brier"),
        "log_loss": interval("log_loss"),
        "ece": interval("ece"),
        "accuracy": interval("accuracy"),
    }

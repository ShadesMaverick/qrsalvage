"""The measurement scripts distinguish a correct recovery from plausible garbage."""

import math
from types import SimpleNamespace

import numpy as np

from qrsalvage.synth import Damage
from scripts import difficulty
from scripts.measurements import (
    bootstrap_image_metrics,
    calibration_metrics,
    classify_recovery,
    clustered_rate_interval,
    count_recoveries,
    paired_difference,
)


def test_recovery_outcome_requires_the_exact_expected_payload():
    assert classify_recovery("EXPECTED", "EXPECTED") == "correct"
    assert classify_recovery("VALID-BUT-WRONG", "EXPECTED") == "wrong"
    assert classify_recovery(None, "EXPECTED") == "failed"


def test_recovery_counts_keep_valid_wrong_payloads_visible():
    assert count_recoveries(("EXPECTED", "VALID-BUT-WRONG", None), "EXPECTED") == (1, 1, 1)


def test_paired_difference_keeps_the_pairing_and_reports_discordance():
    summary = paired_difference(
        before=(False, False, True, True),
        after=(True, False, True, False),
        bootstrap=200,
        seed=7,
    )

    assert summary["improved"] == 1
    assert summary["regressed"] == 1
    assert summary["difference"] == 0.0
    assert summary["low"] <= summary["difference"] <= summary["high"]


def test_clustered_rate_resamples_trials_not_their_members():
    summary = clustered_rate_interval(
        ((True, False), (True, False), (True, False)), bootstrap=100, seed=3
    )

    assert summary == {"rate": 0.5, "low": 0.5, "high": 0.5, "clusters": 3, "trials": 6}


def test_calibration_metrics_score_probabilities_against_module_truth():
    metrics = calibration_metrics(
        np.array([0.9, 0.1]), np.array([True, False]), bins=((0.5, 1.01),)
    )

    assert math.isclose(metrics["brier"], 0.01)
    assert math.isclose(metrics["log_loss"], -math.log(0.9))
    assert math.isclose(metrics["ece"], 0.1)
    assert metrics["accuracy"] == 1.0


def test_calibration_bootstrap_uses_whole_images_as_units():
    image = (np.array([0.9, 0.1]), np.array([True, False]))
    summary = bootstrap_image_metrics((image, image), bootstrap=50, seed=11)

    assert summary["images"] == 2
    for metric in ("brier", "log_loss", "ece", "accuracy"):
        assert summary[metric]["low"] == summary[metric]["estimate"]
        assert summary[metric]["high"] == summary[metric]["estimate"]


def test_difficulty_counts_valid_wrong_text_separately(monkeypatch):
    outcomes = ("EXPECTED", "VALID-BUT-WRONG", None)

    monkeypatch.setattr(difficulty, "TEXT", "EXPECTED")
    monkeypatch.setattr(difficulty, "reencode", lambda _text: object())
    monkeypatch.setattr(difficulty, "render_photo", lambda _matrix, _damage, seed: seed)
    monkeypatch.setattr(
        difficulty,
        "solve",
        lambda seed, budget: SimpleNamespace(
            text=outcomes[seed],
            candidates_tried=1,
            wrong_sampled=seed,
        ),
    )

    correct, wrong, median, attempts, seconds = difficulty.measure(Damage(), samples=3, budget=1)

    assert (correct, wrong) == (1, 1)
    assert median == 1
    assert attempts == 3
    assert seconds >= 0.0

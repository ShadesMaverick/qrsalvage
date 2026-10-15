"""Recovery policy is explicit rather than hidden inside orchestration."""

from qrsalvage.core.geometry import GridFit
from qrsalvage.core.policy import (
    attempt_error_rate,
    choose_grid,
    fusion_rank,
    should_restart,
)


def _fit(wrong: int, quality: float, total: int = 100) -> GridFit:
    return GridFit(
        modules=21,
        corners=None,  # type: ignore[arg-type]
        quality=quality,
        wrong_known=wrong,
        known_total=total,
        means=None,  # type: ignore[arg-type]
        posterior=None,  # type: ignore[arg-type]
    )


def test_grid_choice_prefers_evidence_then_smooth_quality():
    best = choose_grid((_fit(2, 0.2), _fit(1, 0.1), _fit(1, 0.8)))

    assert best.wrong_known == 1
    assert best.quality == 0.8


def test_attempt_error_rate_names_an_attempt_without_a_grid_as_total_failure():
    assert attempt_error_rate(()) == 1.0
    assert attempt_error_rate((_fit(5, 0.1, total=100),)) == 0.05


def test_restart_gate_is_a_fraction_of_living_evidence():
    assert should_restart(_fit(6, 0.1, total=100), threshold=0.05)
    assert not should_restart(_fit(5, 0.1, total=100), threshold=0.05)


def test_fusion_rank_puts_the_cleanest_best_timed_member_first():
    clean = type("Member", (), {"wrong_known": 1, "timing": 0.99})()
    noisy = type("Member", (), {"wrong_known": 2, "timing": 1.0})()

    assert fusion_rank(clean) < fusion_rank(noisy)

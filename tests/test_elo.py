"""Deterministic tests for the Elo system.

Catch regressions in the core rating math before they propagate.
"""

from __future__ import annotations

import math
from datetime import date

from src.config import ELO_DEFAULT_RATING
from src.features.elo import MMAElo


def test_initial_rating_is_default():
    elo = MMAElo()
    assert elo.get("anyone") == ELO_DEFAULT_RATING


def test_winner_gains_loser_loses_zero_sum():
    # When both fighters have equal experience, K-factors match and the system is
    # exactly zero-sum: winner gains K*(1−E), loser loses K*(1−E).
    elo = MMAElo()
    elo.update("A", "B", "Decision", date(2024, 1, 1))
    a, b = elo.get("A"), elo.get("B")
    assert a > ELO_DEFAULT_RATING
    assert b < ELO_DEFAULT_RATING
    assert math.isclose(a + b, 2 * ELO_DEFAULT_RATING, abs_tol=0.01)


def test_unequal_experience_breaks_zero_sum():
    # When fighters differ in experience their K-factors differ, so the rating pool
    # is NOT conserved. This is a deliberate design choice — the test documents it.
    elo = MMAElo()
    elo.fight_counts["vet"] = 30   # K will be at the 1.0× floor
    elo.fight_counts["new"] = 0    # K will be at the 1.5× peak
    elo.update("vet", "new", "Decision", date(2024, 1, 1))
    total = elo.get("vet") + elo.get("new")
    assert not math.isclose(total, 2 * ELO_DEFAULT_RATING, abs_tol=0.01)


def test_method_bonus_amplifies_swing():
    decision_elo = MMAElo()
    ko_elo = MMAElo()
    d = date(2024, 1, 1)
    decision_elo.update("A", "B", "Decision", d)
    ko_elo.update("A", "B", "KO/TKO", d)
    assert ko_elo.get("A") > decision_elo.get("A")


def test_inactivity_decay_pulls_rating_to_default():
    elo = MMAElo()
    # Make A clearly above default
    for _ in range(5):
        elo.update("A", "B", "KO/TKO", date(2020, 1, 1))
    rating_before = elo.get("A")
    # 3-year layoff
    elo.apply_inactivity_decay("A", date(2023, 1, 1))
    rating_after = elo.get("A")
    assert rating_before > rating_after > ELO_DEFAULT_RATING


def test_win_probability_within_bounds():
    elo = MMAElo()
    p = elo.win_probability("X", "Y")
    assert 0.0 <= p <= 1.0
    assert math.isclose(p, 0.5, abs_tol=1e-9)


def test_recent_fighter_has_higher_k():
    elo = MMAElo()
    elo.fight_counts["new"] = 0
    elo.fight_counts["vet"] = 30
    assert elo.k_factor("new", "Decision") > elo.k_factor("vet", "Decision")

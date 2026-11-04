"""Custom MMA Elo rating system.

Differs from chess Elo in three ways:
    1. K-factor scales with fighter experience (volatile when new, stable when veteran).
    2. K-factor scales with method bonus (KO/TKO * 1.15, Sub * 1.10, Decision * 1.0).
    3. Inactivity decay regresses long-idle fighters back toward the mean.

The class is mutable (ratings update in place). Always replay history in
chronological order; never feed test-period fights into the rating store you
use to score training fights.

Constants live in src.config: ELO_K_BASE, ELO_DEFAULT_RATING,
ELO_INACTIVITY_THRESHOLD_DAYS.

USAGE
    elo = MMAElo()
    for fight in fights_sorted_by_date.itertuples():
        elo.update(fight.winner_id, fight.loser_id, fight.method, fight.event_date)
    rating = elo.get(fighter_id)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from src.config import ELO_DEFAULT_RATING, ELO_INACTIVITY_THRESHOLD_DAYS, ELO_K_BASE


@dataclass
class MMAElo:
    k_base: int = ELO_K_BASE
    default: int = ELO_DEFAULT_RATING
    ratings: dict[str, float] = field(default_factory=dict)
    fight_counts: dict[str, int] = field(default_factory=dict)
    last_fight_dates: dict[str, date] = field(default_factory=dict)

    def get(self, fighter_id: str) -> float:
        return self.ratings.get(fighter_id, float(self.default))

    def expected(self, r_a: float, r_b: float) -> float:
        return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))

    def k_factor(self, fighter_id: str, method: str) -> float:
        fights = self.fight_counts.get(fighter_id, 0)
        # Experience multiplier: 1.5× for a debut, linearly decays to 1.0× at fight 17,
        # then stays flat. This means a 20-fight UFC vet and a 100-fight vet have the same
        # K — intentional; at that volume the career sample is sufficient for stable ratings.
        experience_adj = max(1.0, 1.5 - fights * 0.03)
        method_mult = {"KO/TKO": 1.15, "Submission": 1.10, "Decision": 1.0}.get(method, 1.0)
        return self.k_base * experience_adj * method_mult

    def apply_inactivity_decay(
        self,
        fighter_id: str,
        current_date: date,
        decay_rate: float = 0.02,
        threshold_days: int = ELO_INACTIVITY_THRESHOLD_DAYS,
    ) -> None:
        last = self.last_fight_dates.get(fighter_id)
        if last is None:
            return
        days_inactive = (current_date - last).days
        if days_inactive <= threshold_days:
            return
        years_inactive = days_inactive / 365.0
        decay = min(decay_rate * years_inactive, 0.25)
        current = self.get(fighter_id)
        self.ratings[fighter_id] = current + (self.default - current) * decay

    def update(self, winner_id: str, loser_id: str, method: str, fight_date: date) -> None:
        # Apply decay BEFORE the fight is scored so the rating reflects rust.
        self.apply_inactivity_decay(winner_id, fight_date)
        self.apply_inactivity_decay(loser_id, fight_date)

        r_w = self.get(winner_id)
        r_l = self.get(loser_id)
        expected_w = self.expected(r_w, r_l)
        k_w = self.k_factor(winner_id, method)
        k_l = self.k_factor(loser_id, method)

        self.ratings[winner_id] = r_w + k_w * (1 - expected_w)
        self.ratings[loser_id] = r_l - k_l * (1 - expected_w)

        self.fight_counts[winner_id] = self.fight_counts.get(winner_id, 0) + 1
        self.fight_counts[loser_id] = self.fight_counts.get(loser_id, 0) + 1
        self.last_fight_dates[winner_id] = fight_date
        self.last_fight_dates[loser_id] = fight_date

    def win_probability(self, a_id: str, b_id: str) -> float:
        """Pure Elo win probability — used as a baseline model and as a feature."""
        return self.expected(self.get(a_id), self.get(b_id))

    def __repr__(self) -> str:
        return f"MMAElo(n_fighters={len(self.ratings)}, k_base={self.k_base})"


def _sanity() -> None:
    """Tiny smoke check; tests/test_elo.py is the real suite."""
    elo = MMAElo()
    elo.update("A", "B", "KO/TKO", date(2024, 1, 1))
    assert elo.get("A") > ELO_DEFAULT_RATING
    assert elo.get("B") < ELO_DEFAULT_RATING
    assert math.isclose(elo.get("A") + elo.get("B"), 2 * ELO_DEFAULT_RATING, abs_tol=0.01)


if __name__ == "__main__":
    _sanity()
    print("elo sanity OK")

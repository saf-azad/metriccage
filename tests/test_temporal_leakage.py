"""Temporal-leakage regression tests for the feature builder.

The project's central correctness contract (docs/PLAN.md §4.2, the shared
contract 4): every feature for a fight on date `d` must be computable using
ONLY data strictly before `d`. No feature may peek at the future.

The gold-standard enforcement is *truncation invariance*: a fight's feature
row must be identical whether or not fights that come after it exist in the
input frame. If any feature leaked future information, removing the later
fights would change that row. These tests build the full matrix, then rebuild
on a prefix and assert the shared row is bit-identical.

This is a regression guard: it must be strengthened, never weakened.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.features.build_matrix import build_full_matrix


def _distinct_date_fights(n: int = 30, seed: int = 7) -> pd.DataFrame:
    """Toy fight log with strictly-distinct dates (no same-day ambiguity).

    Distinct dates make the chronological order total, so 'the prefix before
    fight k' is unambiguous and position k is stable between the full frame and
    any prefix of it.
    """
    rng = np.random.default_rng(seed)
    fighters = [f"f{i}" for i in range(8)]
    base = date(2015, 1, 1)
    rows = []
    for i in range(n):
        a, b = rng.choice(fighters, size=2, replace=False)
        winner_id = a if rng.random() < 0.5 else b
        rows.append(
            {
                "fight_id": f"fight_{i:03d}",
                "event_id": f"e{i}",
                "event_date": base + timedelta(days=45 * i),  # strictly increasing
                "weight_class": "Lightweight",
                "fighter_a_id": a,
                "fighter_b_id": b,
                "fighter_a_name": a,
                "fighter_b_name": b,
                "winner_id": winner_id,
                "method": "U-DEC",
                "method_canon": "Decision",
                "round_finished": 3,
                "fight_duration_min": 15.0,
                "fight_duration_sec": 900,
                "ss_landed_a": int(rng.integers(20, 80)),
                "ss_landed_b": int(rng.integers(20, 80)),
                "td_landed_a": int(rng.integers(0, 5)),
                "td_landed_b": int(rng.integers(0, 5)),
                "sub_att_a": int(rng.integers(0, 3)),
                "sub_att_b": int(rng.integers(0, 3)),
                "kd_a": 0,
                "kd_b": 0,
                "fighter_a_won": int(winner_id == a),
            }
        )
    return pd.DataFrame(rows)


def _feature_cols(matrix: pd.DataFrame) -> list[str]:
    """Numeric feature columns to compare (exclude ids / labels / metadata)."""
    non_features = {
        "fight_id", "event_id", "event_date", "weight_class",
        "fighter_a_id", "fighter_b_id", "fighter_a_name", "fighter_b_name",
        "winner_id", "method", "method_canon", "round_finished",
        "fight_duration_min", "fight_duration_sec", "fighter_a_won",
    }
    return [
        c for c in matrix.columns
        if c not in non_features and pd.api.types.is_numeric_dtype(matrix[c])
    ]


def test_feature_row_is_invariant_to_future_fights():
    """A fight's features must not change when later fights are removed.

    Build the full matrix, then rebuild on the prefix ending at each probe
    fight. The probe fight's feature row must be bit-identical — anything else
    means a feature read data from after the fight's date (future leakage).
    """
    fights = _distinct_date_fights(n=30)
    full = build_full_matrix(fights).set_index("fight_id")
    feat_cols = _feature_cols(full.reset_index())
    assert feat_cols, "no numeric feature columns found to compare"

    fights_sorted = fights.sort_values("event_date").reset_index(drop=True)

    # Probe several positions incl. a fighter's later fight (where non-trivial
    # history exists and a leak would actually manifest).
    for k in (5, 12, 20, 29):
        probe_id = fights_sorted.iloc[k]["fight_id"]
        prefix = fights_sorted.iloc[: k + 1].copy()  # fights 0..k only, none after
        truncated = build_full_matrix(prefix).set_index("fight_id")

        assert probe_id in truncated.index
        full_row = full.loc[probe_id, feat_cols].to_numpy(dtype=float)
        trunc_row = truncated.loc[probe_id, feat_cols].to_numpy(dtype=float)
        # Exact equality (NaN-aware): identical computation on an identical
        # prefix must yield identical numbers.
        np.testing.assert_array_equal(
            np.nan_to_num(full_row, nan=-999.0),
            np.nan_to_num(trunc_row, nan=-999.0),
            err_msg=f"feature row for {probe_id} changed when future fights were removed",
        )


def test_first_fight_has_no_prior_signal():
    """The earliest fight has no history: differential/history features are 0."""
    fights = _distinct_date_fights(n=12)
    matrix = build_full_matrix(fights)
    first = matrix.sort_values("event_date").iloc[0]
    assert first["elo_diff"] == 0.0
    assert first["n_fights_a"] == 0
    assert first["n_fights_b"] == 0


def test_history_is_strictly_prior_never_inclusive():
    """A rematch's second bout must 'see' exactly one prior meeting, not two.

    Force two fights between the same pair on distinct dates. The second fight's
    per-fighter experience counts must reflect exactly ONE prior fight — proving
    the current fight itself is excluded from its own history (no off-by-one
    that would let a fight see itself or its future).
    """
    base = date(2016, 3, 1)
    common = {
        "event_id": "e", "weight_class": "Lightweight",
        "fighter_a_name": "A", "fighter_b_name": "B",
        "method": "U-DEC", "method_canon": "Decision", "round_finished": 3,
        "fight_duration_min": 15.0, "fight_duration_sec": 900,
        "ss_landed_a": 50, "ss_landed_b": 40, "td_landed_a": 1, "td_landed_b": 0,
        "sub_att_a": 0, "sub_att_b": 0, "kd_a": 0, "kd_b": 0,
    }
    fights = pd.DataFrame(
        [
            {**common, "fight_id": "bout1", "event_date": base,
             "fighter_a_id": "A", "fighter_b_id": "B", "winner_id": "A", "fighter_a_won": 1},
            {**common, "fight_id": "bout2", "event_date": base + timedelta(days=200),
             "fighter_a_id": "A", "fighter_b_id": "B", "winner_id": "B", "fighter_a_won": 0},
        ]
    )
    matrix = build_full_matrix(fights).set_index("fight_id")
    # First bout: neither fighter has prior fights.
    assert matrix.loc["bout1", "n_fights_a"] == 0
    assert matrix.loc["bout1", "n_fights_b"] == 0
    # Second bout: each has exactly ONE prior fight (bout1) — not two, not zero.
    assert matrix.loc["bout2", "n_fights_a"] == 1
    assert matrix.loc["bout2", "n_fights_b"] == 1

"""Smoke tests for the Track 1 implementations."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features import core_features as cf
from src.features.build_matrix import build_full_matrix

# Local data artifacts (gitignored — absent on CI). Data-dependent tests below
# are guarded with inline skipif so they run locally but skip cleanly on CI.
_DATA = Path(__file__).resolve().parents[1] / "data"
_HAS_LOCAL_DATA = (
    (_DATA / "processed" / "final_model_bundle.pkl").exists()
    and (
        (_DATA / "interim" / "fights.parquet").exists()
        or (_DATA / "interim" / "fights_enriched.parquet").exists()
    )
    and (_DATA / "interim" / "fighters.parquet").exists()
)


# --- core_features ----------------------------------------------------------


def _toy_history(rows: int = 4, won: bool = True) -> pd.DataFrame:
    base = date(2024, 1, 1)
    return pd.DataFrame(
        {
            "event_date": pd.to_datetime([base - timedelta(days=180 * (rows - i)) for i in range(rows)]),
            "fighter_role": ["a"] * rows,
            "sig_strikes_landed": [40] * rows,
            "opp_sig_strikes_landed": [25] * rows,
            "takedowns_landed": [2] * rows,
            "opp_takedowns_landed": [1] * rows,
            "sub_attempts": [1] * rows,
            "knockdowns": [0] * rows,
            "opp_knockdowns": [0] * rows,
            "fight_duration_minutes": [15.0] * rows,
            "winner": [won] * rows,
            "method": ["Decision"] * rows,
        }
    )


def test_slpm_basic():
    h = _toy_history()
    val = cf.slpm(h, date(2024, 6, 1))
    # 40 strikes / 15 min ≈ 2.67/min; weighted average should be in that vicinity
    assert 2.0 < val < 4.0


def test_slpm_empty_history_returns_zero():
    assert cf.slpm(pd.DataFrame(), date.today()) == 0.0


def test_finish_rate_zero_when_no_wins():
    h = _toy_history(won=False)
    assert cf.finish_rate(h) == 0.0


def test_td_accuracy_proxy_in_unit_interval():
    h = _toy_history()
    a = cf.td_accuracy(h, date(2024, 6, 1))
    assert 0.0 <= a <= 1.0


def test_streak_counts_consecutive_wins():
    h = _toy_history(won=True)
    assert cf.streak(h) == len(h)


# --- weight-class change ------------------------------------------------------


def _wc_history(classes: list[str], days_apart: int = 180) -> pd.DataFrame:
    base = date(2023, 1, 1)
    return pd.DataFrame(
        {
            "event_date": pd.to_datetime(
                [base + timedelta(days=days_apart * i) for i in range(len(classes))]
            ),
            "weight_class": classes,
        }
    )


def test_weight_change_up_one_division():
    h = _wc_history(["Light Heavyweight", "Light Heavyweight"])
    assert cf.weight_change(h, "Heavyweight") == 1.0


def test_weight_change_down_two_divisions():
    h = _wc_history(["Middleweight", "Light Heavyweight"])
    assert cf.weight_change(h, "Welterweight") == -2.0


def test_weight_change_zero_when_staying_put():
    h = _wc_history(["Lightweight", "Lightweight"])
    assert cf.weight_change(h, "Lightweight") == 0.0


def test_weight_change_debutant_and_catchweight_default_zero():
    assert cf.weight_change(pd.DataFrame(), "Lightweight") == 0.0
    h = _wc_history(["Lightweight"])
    assert cf.weight_change(h, "Catch Weight") == 0.0


def test_weight_change_skips_intermediate_catchweight():
    # Last real division was LW; a one-off catchweight bout must not mask the move.
    h = _wc_history(["Lightweight", "Catch Weight"])
    assert cf.weight_change(h, "Welterweight") == 1.0


def test_weight_change_womens_ladder_shares_rungs():
    h = _wc_history(["Women's Strawweight"])
    assert cf.weight_change(h, "Women's Flyweight") == 1.0


def test_first_fight_at_class_flags_novel_division():
    h = _wc_history(["Light Heavyweight", "Light Heavyweight"])
    assert cf.first_fight_at_class(h, "Heavyweight") == 1.0
    assert cf.first_fight_at_class(h, "Light Heavyweight") == 0.0


def test_first_fight_at_class_returning_is_not_first():
    # Boser pattern: HW career, one LHW detour, back up to HW → a move, not a debut.
    h = _wc_history(["Heavyweight", "Heavyweight", "Light Heavyweight"])
    assert cf.weight_change(h, "Heavyweight") == 1.0
    assert cf.first_fight_at_class(h, "Heavyweight") == 0.0


def test_first_fight_at_class_debutant_is_zero():
    assert cf.first_fight_at_class(pd.DataFrame(), "Lightweight") == 0.0


def test_natural_weight_deviation_stays_elevated_after_move():
    # Second fight at the new class: acute weight_change is 0 again, but the
    # decayed home class is still ~LHW so the chronic signal stays > 0.5.
    h = _wc_history(["Light Heavyweight"] * 4 + ["Heavyweight"])
    ref = date(2024, 6, 1)
    assert cf.weight_change(h, "Heavyweight") == 0.0
    assert cf.natural_weight_deviation(h, "Heavyweight", ref) > 0.5


def test_natural_weight_deviation_zero_at_home_class():
    h = _wc_history(["Lightweight"] * 3)
    assert cf.natural_weight_deviation(h, "Lightweight", date(2024, 6, 1)) == 0.0


# --- build_matrix -----------------------------------------------------------


def _toy_fights() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    fighters = ["F1", "F2", "F3", "F4", "F5"]
    base = date(2020, 1, 1)
    for i in range(30):
        a, b = rng.choice(fighters, size=2, replace=False)
        ev = base + timedelta(days=30 * i)
        winner_id = a if rng.random() < 0.5 else b
        rows.append(
            {
                "fight_id": f"fight_{i}",
                "event_id": "e1",
                "event_date": ev,
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


def test_build_full_matrix_shape_and_no_future_leak():
    fights = _toy_fights()
    matrix = build_full_matrix(fights)
    assert len(matrix) == len(fights)
    # Track-contracted columns must be present
    for col in ("elo_diff", "sg_mismatch_net", "sub_danger_diff", "win_pct_diff", "fighter_a_won"):
        assert col in matrix.columns
    # First fight must have all-zero/default features (no prior data)
    first = matrix.iloc[0]
    assert first["elo_diff"] == 0.0
    assert first["n_fights_a"] == 0
    assert first["n_fights_b"] == 0


def test_build_full_matrix_emits_weight_change_columns():
    fights = _toy_fights()
    # Move fight_5's bout up a division so at least one row registers a change.
    fights.loc[fights["fight_id"] == "fight_5", "weight_class"] = "Welterweight"
    matrix = build_full_matrix(fights)
    for col in (
        "weight_change_a", "weight_change_b", "weight_change_diff",
        "first_at_class_a", "first_at_class_b",
        "natural_wc_dev_a", "natural_wc_dev_b",
    ):
        assert col in matrix.columns, col

    moved = matrix[matrix["fight_id"] == "fight_5"].iloc[0]
    # Both corners fought at LW before (toy pool is small, everyone has history
    # by fight 5 except possibly one corner — a debutant legitimately reads 0).
    for side in ("a", "b"):
        if moved[f"n_fights_{side}"] > 0:
            assert moved[f"weight_change_{side}"] == 1.0
            assert moved[f"first_at_class_{side}"] == 1.0
            assert moved[f"natural_wc_dev_{side}"] == 1.0
    # Everyone else stayed at LW: acute change must be 0 except the fight
    # right after fight_5 for its participants (they moved back down).
    assert (matrix["weight_change_a"].abs() <= 1.0).all()


def test_build_full_matrix_history_grows_monotonically():
    fights = _toy_fights().sort_values("event_date").reset_index(drop=True)
    matrix = build_full_matrix(fights)
    last_n = matrix.iloc[-1]["n_fights_a"] + matrix.iloc[-1]["n_fights_b"]
    first_n = matrix.iloc[0]["n_fights_a"] + matrix.iloc[0]["n_fights_b"]
    assert last_n > first_n


# --- ensemble ---------------------------------------------------------------


def test_ensemble_weights_sum_to_one():
    from src.models.ensemble import fit_ensemble

    rng = np.random.default_rng(0)
    n = 200
    streams = pd.DataFrame(
        {
            "elo": rng.uniform(0.3, 0.7, n),
            "xgb": rng.uniform(0.2, 0.8, n),
            "logreg": rng.uniform(0.25, 0.75, n),
        }
    )
    y = pd.Series(rng.integers(0, 2, n))
    bundle = fit_ensemble(streams, y)
    assert pytest.approx(sum(bundle.weights.values()), abs=1e-6) == 1.0
    assert all(w >= 0 for w in bundle.weights.values())


# --- predict_fight integration smoke ---------------------------------------


@pytest.mark.skipif(
    not _HAS_LOCAL_DATA,
    reason="requires local data artifacts (model bundle + fights/fighters parquets)",
)
def test_predict_fight_smoke():
    """Real bundle path: predict a real matchup and check shape."""
    from src.api.predict_fight import predict_fight

    p = predict_fight("Islam Makhachev", "Charles Oliveira", date(2025, 4, 12))
    a = p.winner_prob["a"]
    b = p.winner_prob["b"]
    assert 0.0 < a < 1.0
    assert pytest.approx(a + b, abs=1e-6) == 1.0
    assert p.confidence in ("high", "medium", "low")
    md = p.to_markdown()
    assert "WHO WINS?" in md
    assert "%" in md

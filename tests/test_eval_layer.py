"""Tests for the evaluation layer: temporal CV, calibration, backtest, metrics.

Everything runs on tiny synthetic data — no data files, no model bundles,
no network.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from src.eval.backtest import BacktestResult, run_backtest
from src.eval.calibration import fit_isotonic, reliability_curve, temperature_scale
from src.eval.metrics import accuracy_at_threshold, auc, brier, expected_calibration_error, logloss
from src.eval.temporal_cv import walk_forward_splits

RNG = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# walk_forward_splits
# ---------------------------------------------------------------------------


def _cv_df(n_dates: int = 10, per_date: int = 2, shuffle: bool = True) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="7D").repeat(per_date)
    df = pd.DataFrame({"event_date": dates, "x": np.arange(len(dates))})
    if shuffle:
        df = df.sample(frac=1.0, random_state=7)
    # Non-default index to pin down that returned indices are POSITIONAL.
    df.index = [f"row_{i}" for i in range(len(df))]
    return df


def test_walk_forward_indices_disjoint_and_strictly_ordered():
    df = _cv_df()
    folds = list(walk_forward_splits(df, n_splits=3, min_train_size=5))
    assert len(folds) == 3
    for train_idx, val_idx in folds:
        assert len(train_idx) > 0 and len(val_idx) > 0
        assert set(train_idx.tolist()).isdisjoint(val_idx.tolist())
        train_dates = df.iloc[train_idx]["event_date"]
        val_dates = df.iloc[val_idx]["event_date"]
        assert train_dates.max() < val_dates.min()  # strict — no same-day overlap


def test_walk_forward_expanding_property():
    df = _cv_df()
    folds = list(walk_forward_splits(df, n_splits=3, min_train_size=5))
    for (train_a, val_a), (train_b, _) in zip(folds, folds[1:], strict=False):
        # Next train set = previous train set + previous val window, exactly.
        assert set(train_b.tolist()) == set(train_a.tolist()) | set(val_a.tolist())
    # Validation windows tile everything after the base train block.
    all_val = np.concatenate([v for _, v in folds])
    assert len(all_val) == len(set(all_val.tolist()))
    assert set(all_val.tolist()) | set(folds[0][0].tolist()) == set(range(len(df)))


def test_walk_forward_date_ties_never_straddle():
    # 4 dates x 4 rows; min_train_size=5 falls mid-date -> cut must snap to 8.
    dates = pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]).repeat(4)
    df = pd.DataFrame({"event_date": dates}).sample(frac=1.0, random_state=3).reset_index(drop=True)
    folds = list(walk_forward_splits(df, n_splits=2, min_train_size=5))
    first_train, first_val = folds[0]
    assert len(first_train) == 8  # snapped up to the 2024-02-01 boundary, not 5
    for train_idx, val_idx in folds:
        train_days = set(df.iloc[train_idx]["event_date"].tolist())
        val_days = set(df.iloc[val_idx]["event_date"].tolist())
        assert train_days.isdisjoint(val_days)


def test_walk_forward_unsorted_input_indices_point_into_original_df():
    df = _cv_df(shuffle=True)
    for train_idx, val_idx in walk_forward_splits(df, n_splits=2, min_train_size=4):
        # Positional indices must be valid and temporally coherent on the
        # original (shuffled) frame.
        assert train_idx.max() < len(df) and val_idx.max() < len(df)
        assert df.iloc[train_idx]["event_date"].max() < df.iloc[val_idx]["event_date"].min()


def test_walk_forward_raises_on_tiny_df():
    df = _cv_df(n_dates=3, per_date=1)
    with pytest.raises(ValueError, match="min_train_size"):
        list(walk_forward_splits(df, n_splits=2, min_train_size=500))


def test_walk_forward_raises_when_not_enough_dates_for_folds():
    df = pd.DataFrame({"event_date": pd.to_datetime(["2024-01-01"] * 600)})
    with pytest.raises(ValueError, match="n_splits"):
        list(walk_forward_splits(df, n_splits=5, min_train_size=500))


def test_walk_forward_raises_on_nat_and_missing_column():
    df = _cv_df()
    df.iloc[0, df.columns.get_loc("event_date")] = pd.NaT
    with pytest.raises(ValueError, match="NaT"):
        list(walk_forward_splits(df, n_splits=2, min_train_size=4))
    with pytest.raises(ValueError, match="not found"):
        list(walk_forward_splits(_cv_df(), date_col="nope", n_splits=2, min_train_size=4))


# ---------------------------------------------------------------------------
# reliability_curve
# ---------------------------------------------------------------------------


def test_reliability_curve_two_bin_hand_case():
    y_true = np.array([0, 1, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.6, 0.8])
    centres, observed, predicted, counts = reliability_curve(y_true, y_prob, n_bins=2)
    np.testing.assert_allclose(centres, [0.25, 0.75])
    np.testing.assert_allclose(observed, [0.5, 1.0])
    np.testing.assert_allclose(predicted, [0.15, 0.7])
    np.testing.assert_array_equal(counts, [2, 2])


def test_reliability_curve_empty_bins_are_nan_with_zero_count():
    y_true = np.array([0, 1])
    y_prob = np.array([0.05, 0.06])
    _, observed, predicted, counts = reliability_curve(y_true, y_prob, n_bins=10)
    assert counts[0] == 2 and counts[1:].sum() == 0
    assert np.isnan(observed[1:]).all() and np.isnan(predicted[1:]).all()
    assert not np.isnan(observed[0])


def test_reliability_curve_perfect_calibration_accuracy_matches_confidence():
    n = 20_000
    p = RNG.uniform(0.02, 0.98, size=n)
    y = (RNG.random(n) < p).astype(float)
    _, observed, predicted, counts = reliability_curve(y, p, n_bins=10)
    mask = counts > 0
    np.testing.assert_allclose(observed[mask], predicted[mask], atol=0.05)


# ---------------------------------------------------------------------------
# fit_isotonic
# ---------------------------------------------------------------------------


def test_fit_isotonic_monotone_and_clips_out_of_bounds():
    n = 500
    p = RNG.uniform(0, 1, size=n)
    y = (RNG.random(n) < p).astype(float)
    iso = fit_isotonic(y, p)

    grid = np.linspace(0, 1, 101)
    out = iso.predict(grid)
    assert np.all(np.diff(out) >= -1e-12)  # monotone non-decreasing
    assert out.min() >= 0.0 and out.max() <= 1.0

    # out_of_bounds="clip": inputs beyond the training range clamp to the edges.
    lo, hi = iso.predict([-0.5, 1.5])
    assert lo == pytest.approx(out[0])
    assert hi == pytest.approx(out[-1])
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0


# ---------------------------------------------------------------------------
# temperature_scale
# ---------------------------------------------------------------------------


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def test_temperature_scale_recovers_t1_when_calibrated():
    z = RNG.normal(0.0, 2.0, size=8000)
    y = (RNG.random(z.size) < _sigmoid(z)).astype(float)
    t = temperature_scale(y, z)
    assert t == pytest.approx(1.0, abs=0.15)


def test_temperature_scale_detects_overconfidence():
    z = RNG.normal(0.0, 2.0, size=8000)
    y = (RNG.random(z.size) < _sigmoid(z)).astype(float)
    t = temperature_scale(y, 2.0 * z)  # logits doubled -> need T ~= 2 to undo
    assert t == pytest.approx(2.0, abs=0.3)
    assert t > 1.0


# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------

EVENT_DATES = ["2026-02-07", "2026-02-21", "2026-03-07", "2026-03-21"]


def _synthetic_fights() -> pd.DataFrame:
    """8 warm-up fights + 4 in-window events x 6 fights = 32 rows.

    In-window pattern (repeated per event, hand-checkable):
      2 fights: p=0.8, a won,  method Decision  -> correct, high conf, rank 1
      1 fight : p=0.8, b won,  method KO/TKO    -> wrong,   high conf, rank 2
      1 fight : p=0.8, b won,  method Submission-> wrong,   high conf, rank 3
      1 fight : p=0.3, b won,  method Decision  -> correct, low conf,  rank 1
      1 fight : p=0.3, b won,  method KO/TKO    -> correct, low conf,  rank 2
    Wait — see totals asserted in the test; per event: 3 correct of 5? No:
    totals are computed below, per event = 6 fights, 18/24 correct overall.
    """
    rows = []
    for i in range(8):  # warm-up: before the eval window, never predicted
        rows.append(
            {
                "event_date": "2026-01-10",
                "event_name": "UFC Warmup",
                "fighter_a_name": f"Warm A{i}",
                "fighter_b_name": f"Warm B{i}",
                "fighter_a_won": i % 2,
                "method": "Decision",
                "stub_p": 0.5,
                "stub_conf": "low",
            }
        )
    # Per event: 3x (p=.8, a won, Decision), 1x (p=.8, b won, KO/TKO),
    #            1x (p=.8, b won, Submission... adjusted below), 1x (p=.3, b won, ...)
    per_event = [
        (0.8, 1, "Decision", "high"),
        (0.8, 1, "Decision", "high"),
        (0.8, 1, "Decision", "high"),
        (0.8, 0, "KO/TKO", "high"),
        (0.8, 0, "Submission", "high"),
        (0.3, 0, "KO/TKO", "low"),
    ]
    for e, date in enumerate(EVENT_DATES):
        for f, (p, a_won, method, conf) in enumerate(per_event):
            rows.append(
                {
                    "event_date": date,
                    "event_name": f"UFC Test {e + 1}",
                    "fighter_a_name": f"A{e}-{f}",
                    "fighter_b_name": f"B{e}-{f}",
                    "fighter_a_won": a_won,
                    "method": method,
                    "stub_p": p,
                    "stub_conf": conf,
                }
            )
    # One DQ, folded into Decision by run_backtest (rank stays 1, still correct).
    rows[8]["method"] = "DQ"
    df = pd.DataFrame(rows)
    return df.sample(frac=1.0, random_state=11).reset_index(drop=True)  # unsorted on purpose


class RecordingFactory:
    """Deterministic stub predictor factory that records the training snapshot
    it is handed for every event (to prove no same-day/future leakage)."""

    def __init__(self) -> None:
        self.snapshots: list[pd.DataFrame] = []

    def __call__(self, train_fights: pd.DataFrame) -> object:
        self.snapshots.append(train_fights.copy())

        def _predict(fight: pd.Series) -> dict:
            return {
                "p_a": float(fight["stub_p"]),
                "method_probs": {"Decision": 0.5, "KO/TKO": 0.3, "Submission": 0.2},
                "confidence": str(fight["stub_conf"]),
            }

        return _predict


def test_run_backtest_rows_leakage_and_summary_math():
    fights = _synthetic_fights()
    factory = RecordingFactory()
    result = run_backtest(fights, factory, "2026-02-01", "2026-03-31")
    assert isinstance(result, BacktestResult)
    per_fight, summary = result  # tuple unpacking is part of the contract

    # --- shape: only the 24 in-window fights are predicted, warm-up is not.
    assert len(per_fight) == 24
    assert (per_fight["error"].isna()).all() or (per_fight["error"].isnull()).all()
    assert summary["n_events"] == 4 and summary["n_fights"] == 24 and summary["n_errors"] == 0

    # --- no future leak: one snapshot per event, strictly-prior fights only,
    #     expanding by exactly one event (6 fights) each time.
    assert [len(s) for s in factory.snapshots] == [8, 14, 20, 26]
    for snapshot, ev_date in zip(factory.snapshots, pd.to_datetime(EVENT_DATES), strict=True):
        assert snapshot["event_date"].max() < ev_date  # never same-day, never future

    # --- summary math (hand-computed from the pattern in _synthetic_fights):
    # per event: 4 correct (3x p=.8 a-won + 1x p=.3 b-won), 2 wrong -> 16/24.
    assert summary["winners_correct"] == 16
    assert summary["accuracy"] == pytest.approx(16 / 24)
    # brier: 12x(.8,1)->0.04, 8x(.8,0)->0.64, 4x(.3,0)->0.09
    expected_brier = (12 * 0.04 + 8 * 0.64 + 4 * 0.09) / 24
    assert summary["brier"] == pytest.approx(expected_brier)
    expected_logloss = -(12 * math.log(0.8) + 8 * math.log(0.2) + 4 * math.log(0.7)) / 24
    assert summary["logloss"] == pytest.approx(expected_logloss, abs=1e-6)
    # confidence buckets: high = 20 fights (12 correct), low = 4 fights (all correct).
    assert summary["by_confidence"]["high"] == {"n": 20, "correct": 12, "accuracy": 0.6}
    assert summary["by_confidence"]["low"] == {"n": 4, "correct": 4, "accuracy": 1.0}
    # method: stub always ranks Decision > KO/TKO > Submission.
    # Actuals per event: 3x Decision(rank1, incl. the DQ), 2x KO/TKO(rank2), 1x Sub(rank3).
    assert summary["method_top1"] == 12
    assert summary["method_top1_accuracy"] == pytest.approx(0.5)
    assert summary["method_mean_rank"] == pytest.approx((12 * 1 + 8 * 2 + 4 * 3) / 24)

    # --- per-fight tidy columns behave.
    assert set(per_fight["predicted_winner"]) <= {"a", "b"}
    assert bool(per_fight["winner_correct"].sum() == 16)
    dq_rows = per_fight[per_fight["actual_method"] == "Decision"]
    assert len(dq_rows) == 12  # DQ folded into Decision


def test_run_backtest_records_predictor_errors_without_dying():
    fights = _synthetic_fights()

    def exploding_factory(train_fights: pd.DataFrame) -> object:
        def _predict(fight: pd.Series) -> dict:
            if fight["fighter_a_name"] == "A0-0":
                raise RuntimeError("boom")
            return {"p_a": float(fight["stub_p"])}

        return _predict

    per_fight, summary = run_backtest(fights, exploding_factory, "2026-02-01", "2026-03-31")
    assert len(per_fight) == 24
    assert summary["n_errors"] == 1 and summary["n_fights"] == 23
    err_rows = per_fight[per_fight["error"].notna()]
    assert len(err_rows) == 1 and "boom" in err_rows.iloc[0]["error"]


def test_run_backtest_validates_inputs():
    fights = _synthetic_fights()
    with pytest.raises(ValueError, match="missing required column"):
        run_backtest(fights.drop(columns=["fighter_a_won"]), RecordingFactory(), "2026-01-01", "2026-12-31")
    with pytest.raises(ValueError, match="after end_date"):
        run_backtest(fights, RecordingFactory(), "2026-12-31", "2026-01-01")


# ---------------------------------------------------------------------------
# metrics (already implemented) — sanity vs sklearn / hand values
# ---------------------------------------------------------------------------

Y_TRUE = np.array([0, 1, 1, 0, 1, 0, 1, 1])
Y_PROB = np.array([0.1, 0.9, 0.8, 0.3, 0.65, 0.45, 0.55, 0.35])


def test_brier_matches_sklearn_and_hand_value():
    assert brier(Y_TRUE, Y_PROB) == pytest.approx(brier_score_loss(Y_TRUE, Y_PROB))
    y = np.array([0, 1, 1, 0])
    p = np.array([0.1, 0.9, 0.8, 0.3])
    assert brier(y, p) == pytest.approx((0.01 + 0.01 + 0.04 + 0.09) / 4)


def test_logloss_matches_sklearn():
    assert logloss(Y_TRUE, Y_PROB) == pytest.approx(log_loss(Y_TRUE, Y_PROB, labels=[0, 1]))
    # Single-class y_true must not crash thanks to labels=[0, 1].
    assert logloss(np.array([1, 1]), np.array([0.9, 0.8])) == pytest.approx(
        -(math.log(0.9) + math.log(0.8)) / 2
    )


def test_auc_matches_sklearn_and_is_1_for_perfect_ranking():
    assert auc(Y_TRUE, Y_PROB) == pytest.approx(roc_auc_score(Y_TRUE, Y_PROB))
    assert auc(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])) == 1.0


def test_ece_hand_value_and_calibrated_limit():
    y = np.array([1, 1, 0, 0])
    p = np.array([0.95, 0.85, 0.15, 0.05])
    # per-bin |acc-conf| = .05, .15, .15, .05, each weighted 1/4 -> 0.1
    assert expected_calibration_error(y, p, n_bins=10) == pytest.approx(0.1)

    n = 20_000
    probs = RNG.uniform(0.02, 0.98, size=n)
    labels = (RNG.random(n) < probs).astype(float)
    assert expected_calibration_error(labels, probs, n_bins=10) < 0.02


def test_accuracy_at_threshold():
    y = np.array([1, 0, 1, 0])
    p = np.array([0.7, 0.4, 0.2, 0.6])
    assert accuracy_at_threshold(y, p) == pytest.approx(0.5)
    assert accuracy_at_threshold(y, p, threshold=0.65) == pytest.approx(0.75)

"""Model-layer tests: two-stage method head, Model B RF, round regressor, config.

All training here is on tiny synthetic data (XGB/RF n_estimators <= 20) so the
suite runs in seconds. Tests that need real artifacts (production bundle /
feature matrix) are guarded with skipif so the suite passes on a fresh clone.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.models.method_rf import METHOD_LABELS, predict_method_proba, train_model_b
from src.models.method_two_stage import (
    METHOD_CLASS_NAMES,
    as_bundle_keys,
    predict_method_proba_two_stage,
    train_method_two_stage,
)
from src.models.round_regressor import predict_round, train_round_regressor

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = ROOT / "data" / "processed" / "final_model_bundle.pkl"
MATRIX_PATH = ROOT / "data" / "processed" / "feature_matrix_built.parquet"

TINY_XGB = {"n_estimators": 15, "learning_rate": 0.3, "max_depth": 3, "early_stopping_rounds": 5}


# --- Synthetic 3-class method data -------------------------------------------


def _synthetic_method_data(n: int = 300, seed: int = 42):
    """~300 rows, 6 features; finish driven by f0, sub-given-finish by f1."""
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 6)), columns=[f"f{i}" for i in range(6)])
    p_finish = 1.0 / (1.0 + np.exp(-1.5 * X["f0"].to_numpy()))
    is_finish = rng.random(n) < p_finish
    p_sub = 1.0 / (1.0 + np.exp(-1.5 * X["f1"].to_numpy()))
    is_sub = rng.random(n) < p_sub
    y = np.zeros(n, dtype=int)  # 0=Decision
    y[is_finish & ~is_sub] = 1  # 1=KO/TKO
    y[is_finish & is_sub] = 2  # 2=Submission
    n_tr = int(n * 2 / 3)
    return X.iloc[:n_tr], y[:n_tr], X.iloc[n_tr:], y[n_tr:]


# --- Two-stage method head ----------------------------------------------------


def test_two_stage_trains_and_predicts_valid_distribution():
    X_tr, y_tr, X_v, y_v = _synthetic_method_data()
    result = train_method_two_stage(X_tr, y_tr, X_v, y_v, params=TINY_XGB)
    probs = predict_method_proba_two_stage(result, X_v)

    assert list(probs.columns) == METHOD_CLASS_NAMES == ["Decision", "KO/TKO", "Submission"]
    assert len(probs) == len(X_v)
    arr = probs.to_numpy()
    assert np.all(arr > 0.0) and np.all(arr < 1.0)
    np.testing.assert_allclose(arr.sum(axis=1), 1.0, atol=1e-9)
    assert "val_top1_acc" in result.metrics


def test_two_stage_sub_boost_shifts_submission_mass_up():
    X_tr, y_tr, X_v, y_v = _synthetic_method_data()
    base = train_method_two_stage(X_tr, y_tr, X_v, y_v, params=TINY_XGB, sub_boost=1.0)
    boosted = train_method_two_stage(X_tr, y_tr, X_v, y_v, params=TINY_XGB, sub_boost=10.0)

    # The boost acts on stage-2 sample weights, so the raw (pre-isotonic)
    # sub-given-finish scores must shift up strictly.
    raw_base = base.stage2_sub.predict_proba(X_v)[:, 1].mean()
    raw_boost = boosted.stage2_sub.predict_proba(X_v)[:, 1].mean()
    assert raw_boost > raw_base

    # Same holds for the combined 3-class output before calibration (stage 1 is
    # unaffected by sub_boost, so this isolates the stage-2 shift). The val-fit
    # isotonics deliberately re-anchor calibrated means to empirical rates, so
    # the calibrated mean is NOT expected to shift — don't assert on it.
    def _uncalibrated(result):
        return {
            "method_stage1_finish": result.stage1_finish,
            "method_stage1_iso": None,
            "method_stage2_sub": result.stage2_sub,
            "method_stage2_iso": None,
        }

    sub_base = predict_method_proba_two_stage(_uncalibrated(base), X_v)["Submission"].mean()
    sub_boosted = predict_method_proba_two_stage(_uncalibrated(boosted), X_v)["Submission"].mean()
    assert sub_boosted > sub_base


def test_as_bundle_keys_emits_production_key_names_and_scores_identically():
    X_tr, y_tr, X_v, y_v = _synthetic_method_data()
    result = train_method_two_stage(X_tr, y_tr, X_v, y_v, params=TINY_XGB)
    keys = as_bundle_keys(result)

    assert set(keys) == {
        "method_head",
        "method_stage1_finish",
        "method_stage1_iso",
        "method_stage2_sub",
        "method_stage2_iso",
    }
    assert keys["method_head"] == "two_stage"

    # The raw-bundle-dict path must score identically to the dataclass path.
    via_result = predict_method_proba_two_stage(result, X_v).to_numpy()
    via_dict = predict_method_proba_two_stage(keys, X_v).to_numpy()
    np.testing.assert_array_equal(via_result, via_dict)


@pytest.mark.requires_data
@pytest.mark.skipif(
    not (BUNDLE_PATH.exists() and MATRIX_PATH.exists()),
    reason="needs local production bundle + built feature matrix",
)
def test_two_stage_port_matches_production_bundle_math():
    """Faithfulness check: scoring the REAL bundle through the ported function
    must reproduce the api's two-stage math (stage predict_proba + isotonics +
    clipping + normalisation) exactly."""
    with open(BUNDLE_PATH, "rb") as f:
        bundle = pickle.load(f)
    if bundle.get("method_head") != "two_stage":
        pytest.skip("production bundle does not use the two-stage method head")
    method_feats = bundle["method_feats"]

    # The bundle's method head may carry features beyond the canonical matrix
    # (a hybrid bundle's method_feats superset); production reindexes with
    # fill_value=0.0 at predict time, so the parity check does the same.
    matrix = pd.read_parquet(MATRIX_PATH)
    rows = matrix.sample(5, random_state=7)
    X = rows.reindex(columns=method_feats, fill_value=0.0).fillna(0.0)

    ported = predict_method_proba_two_stage(bundle, X)

    stage1 = bundle["method_stage1_finish"]
    iso1 = bundle["method_stage1_iso"]
    stage2 = bundle["method_stage2_sub"]
    iso2 = bundle["method_stage2_iso"]

    max_abs_diff = 0.0
    for i in range(len(X)):
        xi = X.iloc[[i]]
        # Manual recompute — mirrors src/api/predict_fight._method_distribution
        # (two-stage branch, before the sub_danger overlay).
        p_finish = float(stage1.predict_proba(xi)[0, 1])
        p_finish = float(iso1.predict([p_finish])[0])
        p_finish = float(np.clip(p_finish, 1e-6, 1 - 1e-6))
        p_sub_g_finish = float(stage2.predict_proba(xi)[0, 1])
        p_sub_g_finish = float(iso2.predict([p_sub_g_finish])[0])
        p_sub_g_finish = float(np.clip(p_sub_g_finish, 1e-6, 1 - 1e-6))
        p_decision = 1.0 - p_finish
        p_ko = p_finish * (1.0 - p_sub_g_finish)
        p_sub = p_finish * p_sub_g_finish
        total = p_decision + p_ko + p_sub
        expected = {
            "Decision": p_decision / total,
            "KO/TKO": p_ko / total,
            "Submission": p_sub / total,
        }
        for label, exp in expected.items():
            diff = abs(float(ported.iloc[i][label]) - exp)
            max_abs_diff = max(max_abs_diff, diff)

    assert max_abs_diff < 1e-9, f"port diverges from api math: max_abs_diff={max_abs_diff}"


# --- Model B RF (PLAN §6.4 interface) ----------------------------------------


def test_method_rf_fits_and_outputs_method_labels():
    X_tr, y_tr_int, X_v, y_v_int = _synthetic_method_data()
    label_map = {0: "Decision", 1: "KO/TKO", 2: "Submission"}
    y_tr = pd.Series([label_map[y] for y in y_tr_int])
    y_v = pd.Series([label_map[y] for y in y_v_int])

    rf, metrics = train_model_b(X_tr, y_tr, X_v, y_v, params={"n_estimators": 10})
    probs = predict_method_proba(rf, X_v)

    assert list(probs.columns) == METHOD_LABELS == ["KO/TKO", "Submission", "Decision"]
    assert len(probs) == len(X_v)
    np.testing.assert_allclose(probs.to_numpy().sum(axis=1), 1.0, atol=1e-9)
    assert 0.0 <= metrics["val_accuracy"] <= 1.0
    assert metrics["n_train"] == len(X_tr)


# --- Round regressor ----------------------------------------------------------


def test_round_regressor_predictions_clipped_to_1_5():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(200, 4)), columns=list("abcd"))
    # Extreme target range so raw regression output would leave [1, 5].
    y = pd.Series(np.clip(3.0 + 4.0 * X["a"], 1, 5).round())

    model = train_round_regressor(X.iloc[:150], y.iloc[:150], params={"n_estimators": 10})
    preds = predict_round(model, X.iloc[150:])

    assert isinstance(preds, pd.Series)
    assert len(preds) == 50
    assert preds.index.equals(X.iloc[150:].index)
    assert float(preds.min()) >= 1.0
    assert float(preds.max()) <= 5.0


# --- Config -------------------------------------------------------------------


@pytest.mark.requires_data
@pytest.mark.skipif(not BUNDLE_PATH.exists(), reason="needs local production bundle")
def test_xgb_optuna_tuned_matches_bundle_params_exactly():
    from src.config import XGB_OPTUNA_TUNED

    with open(BUNDLE_PATH, "rb") as f:
        bundle = pickle.load(f)
    assert XGB_OPTUNA_TUNED == bundle["xgb_optuna_params"]

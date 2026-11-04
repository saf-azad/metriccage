"""Train every model in sequence and persist artefacts + model cards.

    python scripts/train_all.py [--skip-lstm | --with-lstm] [--rebuild-matrix]
                                [--out-dir DIR] [--smoke]

--smoke runs the ENTIRE pipeline (load matrix → split → tiny Model A + Model B →
ensemble + isotonic → method head → blind backtest → bundle + metrics) in a few
seconds on a hard-subsampled slice, writing only to a scratch dir (default
ROOT/.smoke/) so the production artifacts in data/processed/ are never touched.
It prints a single "SMOKE OK …" summary line and exits 0. This is the
definition-of-done smoke target (`make smoke`).

Steps:
    1. (optional) Build feature_matrix.parquet from data/interim/fights.parquet
    2. Split via src.data.splits (TRAIN_*, VAL_*, TEST_* in src.config)
    3. Train Model A (XGBoost) → save + model card
    4. Train Model B (logreg with scaler) → save
    5. Train Model C (PyTorch LSTM) → save  (skippable)
    6. Fit ensemble + isotonic calibration on validation
    7. Train method classifier + fit per-class isotonic calibrators (Step 4b)
    8. Run blind backtest on test slice → final metrics report

Outputs:
    data/processed/feature_matrix.parquet
    data/processed/model_a_xgb_v{ts}.json + .metrics.json
    data/processed/model_b_logreg.pkl
    data/processed/model_c_lstm.pt           (if not --skip-lstm)
    data/processed/final_model_bundle.pkl    (includes method_calibrators)
    data/processed/final_model_metrics.json
    docs/model_cards/model_a_v{ts}.md
    reports/method_calibration_curves.png
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Allow `python scripts/train_all.py` to find the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config import PROCESSED, ROOT
from src.data.clean import balance_fight_labels
from src.data.splits import assert_no_leakage, split
from src.features.build_matrix import build_full_matrix
from src.features.method_calibration import (
    calibrate_method_probs,
    encode_method_labels,
)
from src.models import win_loss_xgb
from src.models.ensemble import fit_ensemble

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train_all")


FEATURE_MATRIX_PATH = PROCESSED / "feature_matrix_built.parquet"
BUNDLE_PATH = PROCESSED / "final_model_bundle.pkl"
METRICS_PATH = PROCESSED / "final_model_metrics.json"


# Column convention: target = fighter_a_won (0/1). Feature columns = everything
# except identifiers and targets.
NON_FEATURE_COLS = {
    "fight_id",
    "event_id",
    "event_date",
    "weight_class",
    "fighter_a_id",
    "fighter_b_id",
    "fighter_a_name",
    "fighter_b_name",
    "method",
    "round_finished",
    "fight_duration_min",
    "fighter_a_won",
}


def _select_feature_cols(matrix: pd.DataFrame) -> list[str]:
    return [c for c in matrix.columns if c not in NON_FEATURE_COLS]


def _resolve_fights_path() -> pd.DataFrame:
    """Return the most-enriched bilateral fights parquet that exists.

    Prefers the Track 2B enriched file (adds ss_attempted, td_attempted,
    control_time) over the v1 file when present. Logs which one we picked so
    surprising bundle changes are obvious in the run output.
    """
    enriched = ROOT / "data" / "interim" / "fights_enriched.parquet"
    canonical = ROOT / "data" / "interim" / "fights.parquet"
    if enriched.exists():
        log.info("Using Track-2B enriched fights at %s", enriched)
        return enriched
    log.info("Using v1 fights at %s (no enrichment)", canonical)
    return canonical


def _step_load_or_build(rebuild: bool) -> pd.DataFrame:
    if not rebuild and FEATURE_MATRIX_PATH.exists():
        log.info("Loading existing feature matrix %s", FEATURE_MATRIX_PATH)
        return pd.read_parquet(FEATURE_MATRIX_PATH)

    fights_path = _resolve_fights_path()
    fighters_path = ROOT / "data" / "interim" / "fighters.parquet"
    log.info("Building feature matrix from %s", fights_path)
    fights = pd.read_parquet(fights_path)
    fighters = pd.read_parquet(fighters_path) if fighters_path.exists() else None
    # Source data lists the winner as fighter_a everywhere (label is 100% class 1).
    # Deterministically swap ~half the rows so the binary target balances ~50/50.
    fights = balance_fight_labels(fights, seed=42)
    log.info(
        "Balanced fight labels — A wins: %d / %d (%.1f%%)",
        int(fights["fighter_a_won"].sum()), len(fights),
        100 * fights["fighter_a_won"].mean(),
    )
    cluster_model = None
    cluster_path = PROCESSED / "cluster_model.pkl"
    if cluster_path.exists():
        with open(cluster_path, "rb") as f:
            cluster_model = pickle.load(f)
        log.info(
            "Loaded archetype cluster model (K=%d, %d feature cols)",
            cluster_model.k_chosen, len(cluster_model.feature_cols),
        )
    matrix = build_full_matrix(fights, fighters, cluster_model=cluster_model, progress=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    matrix.to_parquet(FEATURE_MATRIX_PATH, index=False)
    log.info("Wrote %s (%d rows, %d cols)", FEATURE_MATRIX_PATH, *matrix.shape)
    return matrix


# --- Smoke-test dataset ------------------------------------------------------
# The real config split is train ≤2022 / val =2023 / test 2024–2025, so a naive
# tail sample would populate only one split. These helpers build a tiny matrix
# that still spans all three splits with both winner classes present, so the
# real wiring (split → models → ensemble → method head → backtest) runs end to
# end on ~a few hundred rows in seconds.


def _stratified_sample(df: pd.DataFrame, k: int, seed: int) -> pd.DataFrame:
    """~k rows with BOTH winner-label classes present (roc_auc/log_loss safety)."""
    pos = df[df["fighter_a_won"] == 1]
    neg = df[df["fighter_a_won"] == 0]
    kp = min(len(pos), max(1, k // 2))
    kn = min(len(neg), max(1, k - kp))
    parts = []
    if kp:
        parts.append(pos.sample(kp, random_state=seed))
    if kn:
        parts.append(neg.sample(kn, random_state=seed))
    return pd.concat(parts)


def _synth_matrix(n_per_split: int = 60, n_feats: int = 12, seed: int = 42) -> pd.DataFrame:
    """Fabricate a tiny matrix with the right columns/dtypes when no real matrix
    exists (e.g. CI). Not honest data — only exercises the code paths."""
    rng = np.random.default_rng(seed)
    methods = ["Decision", "KO/TKO", "Submission"]
    feat_names = [f"feat_{i}" for i in range(n_feats)]
    blocks = []
    for split_date, label in (
        (date(2015, 6, 1), "train"),
        (date(2023, 6, 1), "val"),
        (date(2024, 6, 1), "test"),
    ):
        n = n_per_split
        df = pd.DataFrame({fn: rng.normal(size=n) for fn in feat_names})
        df["elo_diff"] = rng.normal(0, 120, size=n)  # required by the elo stream
        df["fighter_a_won"] = np.tile([0, 1], n // 2 + 1)[:n]
        df["event_date"] = pd.Timestamp(split_date)
        df["method"] = [methods[j % 3] for j in range(n)]
        df["fight_id"] = [f"{label}_{j}" for j in range(n)]
        df["event_id"] = f"E_{label}"
        df["weight_class"] = "Lightweight"
        df["fighter_a_id"] = [f"a{label}{j}" for j in range(n)]
        df["fighter_b_id"] = [f"b{label}{j}" for j in range(n)]
        df["fighter_a_name"] = [f"A {label} {j}" for j in range(n)]
        df["fighter_b_name"] = [f"B {label} {j}" for j in range(n)]
        df["round_finished"] = 3
        df["fight_duration_min"] = 15.0
        blocks.append(df)
    return pd.concat(blocks).reset_index(drop=True)


def _smoke_matrix(k_per_split: int = 150, seed: int = 42) -> pd.DataFrame:
    """Prefer the real built matrix (subsampled hard); synthesise only if absent."""
    if FEATURE_MATRIX_PATH.exists():
        log.info("[SMOKE] subsampling %s (read-only)", FEATURE_MATRIX_PATH)
        parts = split(pd.read_parquet(FEATURE_MATRIX_PATH))
        frames = []
        for name in ("train", "val", "test"):
            part = parts[name]
            if len(part) == 0:
                raise RuntimeError(
                    f"[SMOKE] split '{name}' empty in built matrix — cannot subsample"
                )
            frames.append(_stratified_sample(part, k_per_split, seed))
        m = pd.concat(frames).sort_values("event_date").reset_index(drop=True)
        log.info(
            "[SMOKE] subsampled matrix: %d rows (train/val/test = %d/%d/%d)",
            len(m), *(len(f) for f in frames),
        )
        return m
    log.warning("[SMOKE] no built matrix at %s — synthesising a tiny matrix", FEATURE_MATRIX_PATH)
    return _synth_matrix()


def _step_split(matrix: pd.DataFrame) -> dict[str, pd.DataFrame]:
    s = split(matrix)
    log.info(
        "Split sizes — train=%d val=%d test=%d",
        len(s["train"]),
        len(s["val"]),
        len(s["test"]),
    )
    if len(s["test"]) > 0 and len(s["train"]) > 0:
        assert_no_leakage(s["train"], s["test"])
    return s


def _train_model_a(
    s: dict[str, pd.DataFrame],
    feat_cols: list[str],
    *,
    params: dict | None = None,
    save_artifacts: bool = True,
):
    log.info("[Model A] XGBoost — %s", "tiny (smoke)" if params else "Phase-2 hyperparams")
    X_train, y_train = s["train"][feat_cols], s["train"]["fighter_a_won"]
    X_val, y_val = s["val"][feat_cols], s["val"]["fighter_a_won"]
    result = win_loss_xgb.train_model_a(X_train, y_train, X_val, y_val, params=params)
    log.info("[Model A] val metrics: %s", result.metrics)
    if save_artifacts:
        # Skipped in --smoke so no versioned booster/model-card pollutes
        # data/processed and docs/model_cards.
        win_loss_xgb.save_booster(result)
        win_loss_xgb.write_model_card(result, feat_cols)
    return result


def _train_model_b(s: dict[str, pd.DataFrame], feat_cols: list[str]):
    """Logistic regression with feature scaling — fast, well-calibrated baseline."""
    log.info("[Model B] Logistic regression")
    X_train, y_train = s["train"][feat_cols], s["train"]["fighter_a_won"]
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(C=1.0, max_iter=400, random_state=42)),
        ]
    )
    pipe.fit(X_train, y_train)
    p_val = pipe.predict_proba(s["val"][feat_cols])[:, 1]
    metrics = {
        "val_logloss": float(log_loss(s["val"]["fighter_a_won"], np.clip(p_val, 1e-6, 1 - 1e-6))),
        "val_brier": float(brier_score_loss(s["val"]["fighter_a_won"], p_val)),
        "val_auc": float(roc_auc_score(s["val"]["fighter_a_won"], p_val)),
        "val_accuracy": float(accuracy_score(s["val"]["fighter_a_won"], (p_val >= 0.5).astype(int))),
    }
    log.info("[Model B] val metrics: %s", metrics)
    return pipe, metrics


def _maybe_train_model_c(s: dict[str, pd.DataFrame], feat_cols: list[str], skip: bool):
    if skip:
        log.info("[Model C] LSTM — skipped")
        return None, {}
    try:
        from src.models.career_lstm import train_model_c

        log.info("[Model C] LSTM — training")
        result = train_model_c(s["train"], s["val"], feat_cols)
        log.info("[Model C] val metrics: %s", getattr(result, "metrics", {}))
        return result, getattr(result, "metrics", {})
    except Exception as exc:  # pragma: no cover — best-effort
        log.warning("[Model C] training failed (%s); continuing without LSTM", exc)
        return None, {}


def _train_method_model(
    s: dict[str, pd.DataFrame],
    feat_cols: list[str],
    *,
    n_estimators: int = 400,
    max_depth: int = 4,
    reports_dir: Path | None = None,
):
    """Train an XGBoost method classifier and fit per-class isotonic calibrators.

    Returns (xgb_model, calibrators) where calibrators is a list[IsotonicRegression]
    for [Decision=0, KO/TKO=1, Submission=2]. These are saved in the bundle as
    'method_model' and 'method_calibrators' and consumed by predict_fight().

    XGBoost is preferred over RF here because RF + class_weight=balanced + isotonic
    flattens outputs near class priors, producing nearly identical predictions for
    all fights (the failure mode UPDATE_2 Step 4 was meant to fix).

    ``n_estimators`` / ``max_depth`` are lowered in --smoke; ``reports_dir``
    defaults to ROOT/reports (redirected to the scratch dir in --smoke).
    """
    from xgboost import XGBClassifier

    log.info("[Method] Training method classifier (XGBoost, 3-class)")
    X_train = s["train"][feat_cols].fillna(0.0)
    y_train = encode_method_labels(s["train"]["method"])
    X_val = s["val"][feat_cols].fillna(0.0)
    y_val = encode_method_labels(s["val"]["method"])

    rf = XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=3,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        eval_metric="mlogloss",
    )
    rf.fit(X_train, y_train)

    raw_probs_val = rf.predict_proba(X_val)
    val_acc = float((rf.predict(X_val) == y_val).mean())
    log.info("[Method] val accuracy: %.3f", val_acc)
    log.info("[Method] val sub-prob spread: min=%.3f max=%.3f std=%.3f",
             float(raw_probs_val[:, 2].min()),
             float(raw_probs_val[:, 2].max()),
             float(raw_probs_val[:, 2].std()))

    # Fit per-class isotonic calibrators on validation set (never training data).
    calibrators = calibrate_method_probs(raw_probs_val, y_val)
    log.info("[Method] Fitted %d isotonic calibrators (one per method class)", len(calibrators))

    # Save reliability curve plots for manual inspection
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.calibration import calibration_curve

        from src.features.method_calibration import METHOD_LABELS, apply_method_calibration

        calibrated_val = apply_method_calibration(raw_probs_val, calibrators)
        REPORTS = reports_dir if reports_dir is not None else (ROOT / "reports")
        REPORTS.mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        for i, name in enumerate(METHOD_LABELS):
            frac_pos, mean_pred = calibration_curve(
                (y_val == i).astype(int), calibrated_val[:, i], n_bins=10,
            )
            axes[i].plot(mean_pred, frac_pos, marker="o", label="calibrated")
            axes[i].plot([0, 1], [0, 1], "k--", label="perfect")
            axes[i].set_title(name)
            axes[i].legend(fontsize=8)
        plt.tight_layout()
        curve_path = REPORTS / "method_calibration_curves.png"
        plt.savefig(curve_path, dpi=100)
        plt.close(fig)
        log.info("[Method] Saved calibration curves to %s", curve_path)
    except Exception as exc:
        log.warning("[Method] Could not save calibration curves: %s", exc)

    return rf, calibrators


def _stream_for_logreg(pipe, df: pd.DataFrame, feat_cols: list[str]) -> np.ndarray:
    return pipe.predict_proba(df[feat_cols])[:, 1]


def _stream_for_xgb(model, df: pd.DataFrame, feat_cols: list[str]) -> np.ndarray:
    return model.predict_proba(df[feat_cols])[:, 1]


def _stream_for_elo(df: pd.DataFrame, scale: float = 400.0) -> np.ndarray:
    return 1.0 / (1.0 + 10 ** (-df["elo_diff"].to_numpy(dtype=float) / scale))


def main(
    rebuild_matrix: bool = False,
    skip_lstm: bool = True,
    *,
    smoke: bool = False,
    out_dir: str | Path | None = None,
) -> None:
    t0 = time.time()

    if smoke:
        # Force everything to a scratch dir; never overwrite production artifacts.
        skip_lstm = True
        out_path = Path(out_dir) if out_dir is not None else (ROOT / ".smoke")
        reports_dir = out_path / "reports"
        log.info("[SMOKE] scratch out-dir=%s (production artifacts untouched)", out_path)
        matrix = _smoke_matrix()
        model_a_params: dict | None = {"n_estimators": 15, "max_depth": 3}
        method_kwargs: dict = {"n_estimators": 15, "max_depth": 3, "reports_dir": reports_dir}
        save_model_a_artifacts = False
    else:
        out_path = Path(out_dir) if out_dir is not None else PROCESSED
        reports_dir = ROOT / "reports"
        matrix = _step_load_or_build(rebuild_matrix)
        model_a_params = None
        method_kwargs = {"reports_dir": reports_dir}
        save_model_a_artifacts = True

    out_path.mkdir(parents=True, exist_ok=True)
    bundle_path = out_path / "final_model_bundle.pkl"
    metrics_path = out_path / "final_model_metrics.json"

    feat_cols = _select_feature_cols(matrix)
    log.info("Feature columns (%d): %s", len(feat_cols), feat_cols[:8])

    s = _step_split(matrix)
    if len(s["train"]) == 0 or len(s["val"]) == 0 or len(s["test"]) == 0:
        log.error("Empty split (train/val/test); check data dates vs config")
        sys.exit(2)

    a = _train_model_a(s, feat_cols, params=model_a_params, save_artifacts=save_model_a_artifacts)
    b_pipe, b_metrics = _train_model_b(s, feat_cols)
    c_result, c_metrics = _maybe_train_model_c(s, feat_cols, skip=skip_lstm)

    # --- Build val/test stream matrices for ensemble ---
    streams_val = pd.DataFrame(
        {
            "logreg": _stream_for_logreg(b_pipe, s["val"], feat_cols),
            "xgb": _stream_for_xgb(a.booster, s["val"], feat_cols),
            "elo": _stream_for_elo(s["val"]),
        }
    )
    streams_test = pd.DataFrame(
        {
            "logreg": _stream_for_logreg(b_pipe, s["test"], feat_cols),
            "xgb": _stream_for_xgb(a.booster, s["test"], feat_cols),
            "elo": _stream_for_elo(s["test"]),
        }
    )

    if c_result is not None:
        from src.models.career_lstm import predict_model_c

        full_fights_path = _resolve_fights_path()
        full_fights = pd.read_parquet(full_fights_path).sort_values("event_date").reset_index(drop=True)
        full_fights["event_date"] = pd.to_datetime(full_fights["event_date"])
        streams_val["lstm"] = predict_model_c(c_result, full_fights, s["val"])
        streams_test["lstm"] = predict_model_c(c_result, full_fights, s["test"])

    log.info("[Ensemble] fitting on validation slice")
    bundle = fit_ensemble(streams_val, s["val"]["fighter_a_won"])
    log.info("[Ensemble] weights: %s", bundle.weights)
    log.info("[Ensemble] metrics: %s", bundle.metrics)

    # --- Step 4b: Method classifier + per-class isotonic calibration ---
    method_model, method_calibrators = _train_method_model(s, feat_cols, **method_kwargs)

    # --- Blind backtest on test slice ---
    from src.models.ensemble import predict_ensemble

    p_test = predict_ensemble(streams_test, bundle)
    y_test = s["test"]["fighter_a_won"].to_numpy(dtype=int)
    test_metrics = {
        "n": int(len(y_test)),
        "accuracy": float(accuracy_score(y_test, (p_test >= 0.5).astype(int))),
        "brier": float(brier_score_loss(y_test, p_test)),
        "logloss": float(log_loss(y_test, np.clip(p_test, 1e-6, 1 - 1e-6))),
        "auc": float(roc_auc_score(y_test, p_test)),
    }
    log.info("[Backtest] test metrics: %s", test_metrics)

    # --- Persist final bundle in the format predict_fight expects ---
    weights_dict = {k: float(v) for k, v in bundle.weights.items()}
    final_bundle: dict = {
        "feats": feat_cols,
        "lr": b_pipe,
        "xgb": a.booster,
        # Use a dict so 4-stream (with LSTM) and 3-stream bundles share one shape.
        "weights": weights_dict,
        "elo_scale": 400.0,
        "iso_lr": None,
        "iso_xg": None,
        "iso_el": None,
        "iso_blend": bundle.calibrator,
        "streams": list(bundle.streams),
        "method_model": method_model,
        "method_calibrators": method_calibrators,
        "best_config": {
            "phase": "smoke" if smoke else ("track2b_full" if c_result is not None else "track1_v2"),
            "trained_at": datetime.now(UTC).isoformat(),
            "stream_weights": weights_dict,
            "ensemble_metrics": bundle.metrics,
            "model_b_metrics": b_metrics,
            "model_a_metrics": a.metrics,
            "model_c_metrics": c_metrics,
            "test_metrics": test_metrics,
        },
    }
    if c_result is not None:

        final_bundle["lstm_state_dict"] = {
            k: v.detach().cpu() for k, v in c_result.model.state_dict().items()
        }
        final_bundle["lstm_config"] = {
            "sequence_input_dim": int(c_result.model.encoder.lstm.input_size),
            "diff_feature_dim": len(feat_cols),
        }
        final_bundle["lstm_diff_cols"] = feat_cols
        final_bundle["lstm_seq_len"] = 20
    out_path.mkdir(parents=True, exist_ok=True)
    with open(bundle_path, "wb") as f:
        pickle.dump(final_bundle, f)
    log.info("Wrote %s", bundle_path)

    metrics_path.write_text(
        json.dumps(
            {
                "test_metrics": test_metrics,
                "ensemble": bundle.metrics,
                "weights": bundle.weights,
                "n_features": len(feat_cols),
                "feats": feat_cols,
                "feature_importance": [
                    [name, float(score)] for name, score in a.feature_importance[:30]
                ],
            },
            indent=2,
        )
    )
    log.info("Wrote %s", metrics_path)
    log.info("All done in %.1fs", time.time() - t0)

    if smoke:
        print(
            "SMOKE OK — "
            f"splits train/val/test={len(s['train'])}/{len(s['val'])}/{len(s['test'])} "
            f"| features={len(feat_cols)} streams={list(bundle.streams)} "
            f"| backtest n={test_metrics['n']} "
            f"acc={test_metrics['accuracy']:.3f} brier={test_metrics['brier']:.3f} "
            f"logloss={test_metrics['logloss']:.3f} auc={test_metrics['auc']:.3f} "
            f"| bundle={bundle_path} ({time.time() - t0:.1f}s)"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--skip-lstm", action="store_true", default=False,
                        help="skip Model C (LSTM) training (default)")
    parser.add_argument("--with-lstm", dest="skip_lstm", action="store_false",
                        help="train Model C (LSTM) too")
    parser.add_argument("--rebuild-matrix", action="store_true",
                        help="rebuild the feature matrix from interim data before training")
    parser.add_argument("--out-dir", default=None, metavar="DIR",
                        help="where to write the bundle + metrics "
                             "(default: data/processed; forced to a scratch dir under --smoke)")
    parser.add_argument("--smoke", action="store_true",
                        help="fast end-to-end smoke run on a tiny subsample; writes only to a "
                             "scratch dir (never touches production artifacts) and prints SMOKE OK")
    args = parser.parse_args()
    main(
        rebuild_matrix=args.rebuild_matrix,
        skip_lstm=args.skip_lstm,
        smoke=args.smoke,
        out_dir=args.out_dir,
    )

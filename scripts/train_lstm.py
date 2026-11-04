"""Train Model C (career LSTM) and integrate it as a 4th ensemble stream.

Loads the existing bundle (logreg + xgb + elo) and the v2 feature matrix, trains
the LSTM on the train slice, scores val + test with all four streams, refits
ensemble weights via constrained log-loss + isotonic calibrator, then writes a
new bundle preserving the original models.

    python scripts/train_lstm.py [--epochs N] [--batch-size N] [--seq-len N]
                                 [--feature-matrix path] [--out path]

The new bundle adds:
    lstm_state_dict   torch state_dict for FightPredictor
    lstm_config       {'sequence_input_dim', 'diff_feature_dim', ...}
    lstm_diff_cols    list of feature names (== bundle['feats'])
    lstm_seq_len      max sequence length used at training time

And replaces:
    weights           dict {logreg, xgb, elo, lstm}
    iso_blend         IsotonicRegression on the 4-stream blend
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from src.config import PROCESSED, ROOT
from src.data.splits import assert_no_leakage, split
from src.models.career_lstm import (
    CareerSequenceDataset,
    FightPredictor,
    _collate,
    train_model_c,
)
from src.models.ensemble import fit_ensemble, predict_ensemble

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("train_lstm")


BUNDLE_PATH = PROCESSED / "final_model_bundle.pkl"
DEFAULT_FEATURE_MATRIX = PROCESSED / "feature_matrix.parquet"
_FIGHTS_PATH_V1 = ROOT / "data" / "interim" / "fights.parquet"
_FIGHTS_PATH_ENRICHED = ROOT / "data" / "interim" / "fights_enriched.parquet"
FIGHTS_PATH = _FIGHTS_PATH_ENRICHED if _FIGHTS_PATH_ENRICHED.exists() else _FIGHTS_PATH_V1


def _stream_logreg(pipe, df: pd.DataFrame, feats: list[str]) -> np.ndarray:
    return pipe.predict_proba(df[feats])[:, 1]


def _stream_xgb(model, df: pd.DataFrame, feats: list[str]) -> np.ndarray:
    return model.predict_proba(df[feats])[:, 1]


def _stream_elo(df: pd.DataFrame, scale: float) -> np.ndarray:
    return 1.0 / (1.0 + 10 ** (-df["elo_diff"].to_numpy(dtype=float) / scale))


def _score_lstm(model: FightPredictor, fights_full: pd.DataFrame, df: pd.DataFrame,
                feats: list[str], seq_len: int, batch_size: int = 256) -> np.ndarray:
    pfd = model.encoder.lstm.input_size
    ds = CareerSequenceDataset(
        fights_full, df.reset_index(drop=True), feats,
        max_seq_len=seq_len, past_fight_dim=pfd,
    )
    loader = torch.utils.data.DataLoader(ds, batch_size=batch_size, shuffle=False, collate_fn=_collate)
    model.eval()
    out: list[np.ndarray] = []
    with torch.no_grad():
        for batch in loader:
            logits = model(batch["a_seq"], batch["a_lengths"], batch["b_seq"],
                           batch["b_lengths"], batch["diff"])
            out.append(torch.sigmoid(logits).numpy())
    return np.concatenate(out) if out else np.zeros(0)


def _enrich_for_bundle(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """Make sure the bundle's expected feature columns all exist in df."""
    out = df.copy()
    for f in feats:
        if f not in out.columns:
            out[f] = 0.0
    return out


def main(*, epochs: int, batch_size: int, seq_len: int, feature_matrix: Path, out: Path) -> None:
    t0 = time.time()
    log.info("Loading bundle %s", BUNDLE_PATH)
    with open(BUNDLE_PATH, "rb") as f:
        bundle = pickle.load(f)
    feats: list[str] = list(bundle["feats"])
    elo_scale = float(bundle.get("elo_scale", 400.0))
    log.info("Bundle features (%d): %s ...", len(feats), feats[:6])

    log.info("Loading feature matrix %s", feature_matrix)
    matrix = pd.read_parquet(feature_matrix)
    matrix = _enrich_for_bundle(matrix, feats)
    log.info("Matrix shape: %s", matrix.shape)

    log.info("Loading bilateral fights %s", FIGHTS_PATH)
    fights_full = pd.read_parquet(FIGHTS_PATH).sort_values("event_date").reset_index(drop=True)
    fights_full["event_date"] = pd.to_datetime(fights_full["event_date"])
    log.info("Fights: %d rows", len(fights_full))

    s = split(matrix)
    log.info("Splits — train=%d val=%d test=%d", len(s["train"]), len(s["val"]), len(s["test"]))
    assert_no_leakage(s["train"], s["test"])

    # --- Train LSTM ---
    log.info("[Model C] Training LSTM — epochs=%d batch=%d seq_len=%d", epochs, batch_size, seq_len)
    lstm_result = train_model_c(
        s["train"], s["val"], feats,
        full_fights=fights_full,
        feature_matrix_full=matrix,
        epochs=epochs, batch_size=batch_size, seq_len=seq_len,
    )
    log.info("[Model C] val metrics: %s", lstm_result.metrics)

    # --- Score all four streams on val + test ---
    log.info("[Streams] scoring val + test with logreg, xgb, elo, lstm")
    lr_pipe = bundle["lr"]
    xgb_model = bundle["xgb"]

    val_streams = pd.DataFrame({
        "logreg": _stream_logreg(lr_pipe, s["val"], feats),
        "xgb":    _stream_xgb(xgb_model, s["val"], feats),
        "elo":    _stream_elo(s["val"], elo_scale),
        "lstm":   _score_lstm(lstm_result.model, fights_full, s["val"], feats, seq_len),
    })
    test_streams = pd.DataFrame({
        "logreg": _stream_logreg(lr_pipe, s["test"], feats),
        "xgb":    _stream_xgb(xgb_model, s["test"], feats),
        "elo":    _stream_elo(s["test"], elo_scale),
        "lstm":   _score_lstm(lstm_result.model, fights_full, s["test"], feats, seq_len),
    })
    y_val = s["val"]["fighter_a_won"]
    y_test = s["test"]["fighter_a_won"].to_numpy(dtype=int)

    # Per-stream val metrics for the model card
    per_stream_val = {}
    for name in val_streams.columns:
        p = val_streams[name].to_numpy()
        per_stream_val[name] = {
            "logloss": float(log_loss(y_val, np.clip(p, 1e-6, 1 - 1e-6))),
            "brier":   float(brier_score_loss(y_val, p)),
            "auc":     float(roc_auc_score(y_val, p)),
            "accuracy": float(accuracy_score(y_val, (p >= 0.5).astype(int))),
        }
    log.info("[Streams] per-stream val metrics: %s",
             {k: round(v["logloss"], 4) for k, v in per_stream_val.items()})

    # --- Refit ensemble weights + isotonic calibrator ---
    log.info("[Ensemble] fitting on val (4 streams)")
    new_bundle = fit_ensemble(val_streams, y_val)
    log.info("[Ensemble] weights: %s", new_bundle.weights)
    log.info("[Ensemble] val metrics: %s", new_bundle.metrics)

    # --- Blind backtest on test ---
    p_test = predict_ensemble(test_streams, new_bundle)
    test_metrics = {
        "n":        int(len(y_test)),
        "accuracy": float(accuracy_score(y_test, (p_test >= 0.5).astype(int))),
        "brier":    float(brier_score_loss(y_test, p_test)),
        "logloss":  float(log_loss(y_test, np.clip(p_test, 1e-6, 1 - 1e-6))),
        "auc":      float(roc_auc_score(y_test, p_test)),
    }
    log.info("[Backtest] test metrics: %s", test_metrics)

    # --- Build output bundle (preserving original models, replacing weights/iso/streams) ---
    new_weights_dict = {k: float(v) for k, v in new_bundle.weights.items()}
    out_bundle = {
        # preserved
        "feats":     feats,
        "lr":        lr_pipe,
        "xgb":       xgb_model,
        "elo_scale": elo_scale,
        "iso_lr":    bundle.get("iso_lr"),
        "iso_xg":    bundle.get("iso_xg"),
        "iso_el":    bundle.get("iso_el"),
        # replaced
        "weights":   new_weights_dict,
        "iso_blend": new_bundle.calibrator,
        "streams":   list(new_bundle.streams),
        # new — LSTM
        "lstm_state_dict": {k: v.detach().cpu() for k, v in lstm_result.model.state_dict().items()},
        "lstm_config": {
            "sequence_input_dim": int(lstm_result.model.encoder.lstm.input_size),
            "diff_feature_dim":   len(feats),
        },
        "lstm_diff_cols": feats,
        "lstm_seq_len":   seq_len,
        # config / metadata
        "best_config": {
            "phase":             "track2a_lstm",
            "trained_at":        datetime.now(UTC).isoformat(),
            "stream_weights":    new_weights_dict,
            "ensemble_metrics":  new_bundle.metrics,
            "lstm_metrics":      lstm_result.metrics,
            "per_stream_val":    per_stream_val,
            "test_metrics":      test_metrics,
            "previous_test":     bundle.get("best_config", {}).get("test_metrics"),
            "lstm_history":      lstm_result.history,
            "lstm_train_config": {
                "epochs": epochs, "batch_size": batch_size, "seq_len": seq_len,
            },
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        pickle.dump(out_bundle, f)
    log.info("Wrote %s", out)

    # Update the canonical metrics file too
    metrics_path = PROCESSED / "lstm_run_metrics.json"
    metrics_path.write_text(json.dumps({
        "test_metrics":     test_metrics,
        "ensemble":         new_bundle.metrics,
        "weights":          new_weights_dict,
        "lstm_val":         lstm_result.metrics,
        "per_stream_val":   per_stream_val,
        "previous_test":    bundle.get("best_config", {}).get("test_metrics"),
        "n_features":       len(feats),
        "lstm_train_config": {"epochs": epochs, "batch_size": batch_size, "seq_len": seq_len},
    }, indent=2))
    log.info("Wrote %s", metrics_path)
    log.info("Total %.1fs", time.time() - t0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seq-len", type=int, default=20)
    parser.add_argument("--feature-matrix", type=Path, default=DEFAULT_FEATURE_MATRIX)
    parser.add_argument("--out", type=Path, default=BUNDLE_PATH)
    args = parser.parse_args()
    main(
        epochs=args.epochs,
        batch_size=args.batch_size,
        seq_len=args.seq_len,
        feature_matrix=args.feature_matrix,
        out=args.out,
    )

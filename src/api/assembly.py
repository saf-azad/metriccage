"""Per-fight feature assembly, stream scoring, blending, and card-content builders.

Everything here takes an explicit `_State` (see `src.api.loading`) so it stays
side-effect-free: build the one-row feature frame, score each ensemble stream,
blend/calibrate to a single win probability, then derive method/round
distributions, drivers, and warnings for the `FightPrediction` card.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from src.api.loading import _State
from src.api.types import Confidence, _humanise
from src.features import core_features as cf
from src.features.build_matrix import build_feature_row

# Raw absolute context fields — they're not signal, just noise, so they are
# filtered out of the driver/advantage lists.
_NON_DRIVER = {"a_elo_pre", "b_elo_pre", "n_fights_a", "n_fights_b", "year_idx"}


def _build_feature_row_for_pair(
    fighter_a_id: str, fighter_b_id: str, event_date: date, state: _State,
    weight_class: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    a_hist = pd.DataFrame(
        [r for r in state.history.get(fighter_a_id, []) if pd.to_datetime(r["event_date"]).date() < event_date]
    )
    b_hist = pd.DataFrame(
        [r for r in state.history.get(fighter_b_id, []) if pd.to_datetime(r["event_date"]).date() < event_date]
    )
    elo = state.elo
    assert elo is not None, "state not loaded — call _load_state() first"
    feat = build_feature_row(
        fighter_a_id,
        fighter_b_id,
        event_date,
        {fighter_a_id: a_hist, fighter_b_id: b_hist},
        elo,
        state.bio_lookup or {},
        cluster_model=state.cluster_model,
        weight_class=weight_class,
    )
    return pd.DataFrame([feat]), a_hist, b_hist


def _score_lstm_row(row: pd.DataFrame, state: _State, feats: list[str]) -> float | None:
    """Score one matchup with the LSTM. Returns None if no model is loaded."""
    if state.lstm_model is None or state.fights is None:
        return None
    # Imported lazily: only reachable when loading.py successfully imported
    # torch + career_lstm and reconstructed an LSTM from the bundle.
    import torch as _torch

    from src.models.career_lstm import PAST_FIGHT_DIM, CareerSequenceDataset, _collate

    # Use the same dataset class as training. It only reads `event_date`,
    # `fighter_a_id`, `fighter_b_id`, the diff feature columns, and `fight_id`.
    fm = row.copy()
    if "fighter_a_won" not in fm.columns:
        fm["fighter_a_won"] = 0.0  # ignored at inference
    if "fight_id" not in fm.columns:
        fm["fight_id"] = "predict_one"
    bundle_cfg = (state.bundle or {}).get("lstm_config") or {}
    pfd = int(bundle_cfg.get("sequence_input_dim", PAST_FIGHT_DIM))
    ds = CareerSequenceDataset(
        state.fights, fm.reset_index(drop=True), feats,
        max_seq_len=state.lstm_seq_len, past_fight_dim=pfd,
    )
    if len(ds) == 0:
        return None
    batch = _collate([ds[0]])
    with _torch.no_grad():
        logits = state.lstm_model(
            batch["a_seq"], batch["a_lengths"], batch["b_seq"],
            batch["b_lengths"], batch["diff"],
        )
        return float(_torch.sigmoid(logits).numpy()[0])


def _build_streams_for_row(row: pd.DataFrame, state: _State) -> dict[str, float]:
    """Produce stream probabilities from a one-row feature DataFrame.

    Always emits {'logreg', 'xgb', 'elo'}; adds 'lstm' when the bundle has one.
    """
    bundle = state.bundle
    assert bundle is not None, "state not loaded — call _load_state() first"
    feats = bundle["feats"]

    # Some engineered features in the bundle ('layoff_signed', 'elo_x_streak',
    # 'slpm_x_sapm', 'year_idx', etc.) are computed from the diff features the
    # build_matrix path emits. Construct them lazily.
    enriched = row.copy()
    if "layoff_signed" in feats and "layoff_signed" not in enriched.columns:
        enriched["layoff_signed"] = enriched.get("days_inactive_diff", 0.0)
    if "elo_x_streak" in feats and "elo_x_streak" not in enriched.columns:
        enriched["elo_x_streak"] = enriched["elo_diff"] * enriched.get("streak_diff", 0)
    if "slpm_x_sapm" in feats and "slpm_x_sapm" not in enriched.columns:
        enriched["slpm_x_sapm"] = enriched["slpm_diff"] * enriched["sapm_diff"]
    if "year_idx" in feats and "year_idx" not in enriched.columns:
        ev_year = pd.to_datetime(enriched["event_date"]).dt.year.iloc[0]
        enriched["year_idx"] = float(ev_year - 2005)

    # For features unique to v1 phase-2 engineering that we cannot reproduce
    # from build_matrix alone, fall back to 0 (safe centred default) so the
    # model still scores. This is a known limitation called out in the
    # IMPROVEMENT_PLAN — Track 1B unifies the feature pipeline.
    for f in feats:
        if f not in enriched.columns:
            enriched[f] = 0.0

    X = enriched[feats]
    p_lr = float(bundle["lr"].predict_proba(X)[:, 1][0])

    # Win/loss XGBoost may have been retrained on a pruned feature subset —
    # use bundle['xgb_feats'] when present so we route the right columns in.
    xgb_feats = bundle.get("xgb_feats") or feats
    X_xgb = enriched.reindex(columns=xgb_feats, fill_value=0.0).fillna(0.0)
    p_xg = float(bundle["xgb"].predict_proba(X_xgb)[:, 1][0])

    elo_diff = float(enriched["elo_diff"].iloc[0])
    elo_scale = float(bundle.get("elo_scale", 400.0))
    p_elo = 1.0 / (1.0 + math.pow(10.0, -elo_diff / elo_scale))

    # Apply per-stream isotonic calibrators if present (v1 bundle uses them).
    if bundle.get("iso_lr") is not None:
        p_lr = float(bundle["iso_lr"].predict([p_lr])[0])
    if bundle.get("iso_xg") is not None:
        p_xg = float(bundle["iso_xg"].predict([p_xg])[0])
    if bundle.get("iso_el") is not None:
        p_elo = float(bundle["iso_el"].predict([p_elo])[0])

    streams = {"logreg": p_lr, "xgb": p_xg, "elo": p_elo}
    lstm_feats = bundle.get("lstm_diff_cols") or feats
    for f in lstm_feats:
        if f not in enriched.columns:
            enriched[f] = 0.0
    p_lstm = _score_lstm_row(enriched, state, lstm_feats)
    if p_lstm is not None:
        streams["lstm"] = p_lstm
    return streams


def _blend(streams: dict[str, float], state: _State) -> float:
    bundle = state.bundle
    assert bundle is not None, "state not loaded — call _load_state() first"
    weights = bundle.get("weights", (0.35, 0.57, 0.08))
    if isinstance(weights, dict):
        # Sum over every stream the bundle weights AND we have a value for.
        # This naturally handles the 3-stream legacy bundle (no 'lstm') and
        # the 4-stream bundle (track2a) from a single code path.
        p = 0.0
        for name, w in weights.items():
            if name in streams:
                p += float(w) * streams[name]
    else:
        # Legacy tuple — (logreg, xgb, elo)
        w_lr, w_xg, w_el = weights
        p = w_lr * streams["logreg"] + w_xg * streams["xgb"] + w_el * streams["elo"]
    p = max(min(p, 1 - 1e-6), 1e-6)
    # Optional final blend calibrator (v2 bundle uses this; v1 didn't).
    iso_blend = bundle.get("iso_blend")
    if iso_blend is not None:
        try:
            p = float(iso_blend.predict([p])[0])
        except Exception:
            pass
    # Isotonic regression can saturate to exactly 0.0/1.0; re-clamp before the
    # logit transform below to avoid a divide-by-zero in temperature scaling.
    p = max(min(p, 1 - 1e-6), 1e-6)
    # Optional temperature scaling — pulls probabilities toward 0.5 to address
    # overconfidence at the extremes. T=1.0 disables; T>1 shrinks. Set in bundle
    # by training pipeline. Default 1.30 lands prior baseline behaviour where
    # 75/25 calls become 70/30 (closer-to-coin-flip stance the original model had).
    T = float(bundle.get("calibration_temperature", 1.0))
    if T != 1.0 and T > 0:
        logit = math.log(p / (1 - p))
        p = 1.0 / (1.0 + math.exp(-logit / T))
    return max(min(p, 1 - 1e-6), 1e-6)


def _method_distribution(
    a_hist: pd.DataFrame,
    b_hist: pd.DataFrame,
    prob_a: float,
    state: _State,
    row: pd.DataFrame | None = None,
) -> dict[str, float]:
    """Method probability distribution.

    Prefers the trained Random Forest method classifier + per-class isotonic
    calibrators (UPDATE_2.md Step 4b) when present in the bundle. Falls back
    to the heuristic blend if the trained method head is unavailable.
    """
    # --- UPDATE_2 Step 4b: trained method model + isotonic calibration ---
    bundle = state.bundle or {}
    method_model = bundle.get("method_model")
    method_calibrators = bundle.get("method_calibrators")
    feats = bundle.get("feats")

    # --- UPDATE_2 Step 4b: two-stage method head (preferred when present) ---
    if (
        bundle.get("method_head") == "two_stage"
        and bundle.get("method_stage1_finish") is not None
        and bundle.get("method_stage2_sub") is not None
        and row is not None
        and feats
    ):
        try:
            method_feats = bundle.get("method_feats") or feats
            X = row.reindex(columns=method_feats, fill_value=0.0).fillna(0.0)

            # Stage 1: P(finish | features)
            stage1 = bundle["method_stage1_finish"]
            iso1 = bundle.get("method_stage1_iso")
            p_finish = float(stage1.predict_proba(X)[0, 1])
            if iso1 is not None:
                p_finish = float(iso1.predict([p_finish])[0])
            p_finish = float(np.clip(p_finish, 1e-6, 1 - 1e-6))

            # Stage 2: P(sub | finish, features)
            stage2 = bundle["method_stage2_sub"]
            iso2 = bundle.get("method_stage2_iso")
            p_sub_g_finish = float(stage2.predict_proba(X)[0, 1])
            if iso2 is not None:
                p_sub_g_finish = float(iso2.predict([p_sub_g_finish])[0])
            p_sub_g_finish = float(np.clip(p_sub_g_finish, 1e-6, 1 - 1e-6))

            p_decision = 1.0 - p_finish
            p_ko = p_finish * (1.0 - p_sub_g_finish)
            p_sub = p_finish * p_sub_g_finish

            # Sub-danger blend (engineered domain feature as a soft prior).
            # Stage 2 val AUC is only ~0.56 (sub vs ko given finish), so we mix in
            # the rules-based sub_danger_combined as a low-weight prior whenever it
            # signals a real threat. Helps grappler-vs-striker cases the classifier
            # mis-ranks (UFC 328 Dawson, Susurkaev).
            try:
                sub_danger_combined = float(row["sub_danger_combined"].iloc[0])
            except Exception:
                sub_danger_combined = 0.0
            if sub_danger_combined > 0.15:
                blend_alpha = 0.4  # weight on domain prior
                p_sub_blend = (1.0 - blend_alpha) * p_sub + blend_alpha * sub_danger_combined
                # Subtract the additional sub mass from Decision + KO proportionally
                delta = p_sub_blend - p_sub
                sum_dk = p_decision + p_ko
                if sum_dk > 1e-9 and delta > 0:
                    p_decision = max(0.0, p_decision - delta * (p_decision / sum_dk))
                    p_ko = max(0.0, p_ko - delta * (p_ko / sum_dk))
                p_sub = p_sub_blend

            total = p_decision + p_ko + p_sub
            return {
                "Decision":   p_decision / total,
                "KO/TKO":     p_ko / total,
                "Submission": p_sub / total,
            }
        except Exception:
            pass  # fall through to legacy method head

    # --- Legacy 3-class method head with isotonic calibrators ---
    if method_model is not None and method_calibrators is not None and row is not None and feats:
        try:
            from src.features.method_calibration import (
                METHOD_LABELS,
                apply_method_calibration,
            )

            method_feats = bundle.get("method_feats") or feats
            X = row.reindex(columns=method_feats, fill_value=0.0).fillna(0.0)
            raw = method_model.predict_proba(X)
            cal = apply_method_calibration(raw, method_calibrators)
            return {
                METHOD_LABELS[i]: float(cal[0, i]) for i in range(len(METHOD_LABELS))
            }
        except Exception:
            pass

    # --- Heuristic fallback ---
    base = state.method_freq.copy()
    if len(a_hist):
        a_finish = cf.finish_rate(a_hist)
        a_sub = cf.sub_avg(a_hist, date.today())
    else:
        a_finish, a_sub = 0.5, 1.0
    if len(b_hist):
        b_finish = cf.finish_rate(b_hist)
        b_sub = cf.sub_avg(b_hist, date.today())
    else:
        b_finish, b_sub = 0.5, 1.0

    favoured_finish = prob_a * a_finish + (1 - prob_a) * b_finish
    favoured_sub_pref = (prob_a * a_sub + (1 - prob_a) * b_sub) / 4.0
    decision = max(0.20, min(0.75, base.get("Decision", 0.5) - 0.4 * favoured_finish + 0.4 * (1 - favoured_finish)))
    finish_pool = 1 - decision
    sub_share = max(0.10, min(0.70, 0.4 + 0.6 * favoured_sub_pref - 0.3 * favoured_finish))
    sub = finish_pool * sub_share
    ko = finish_pool * (1 - sub_share)
    total = decision + ko + sub
    return {
        "Decision": float(decision / total),
        "KO/TKO": float(ko / total),
        "Submission": float(sub / total),
    }


def _round_distribution(method_probs: dict[str, float]) -> dict[str, float]:
    """Heuristic round distribution from method probs.

    Decisions are decisions; finishes are skewed toward rounds 1–2 (UFC
    historical: ~40% R1, ~30% R2, ~15% R3, the rest 4–5).
    """
    decision = method_probs.get("Decision", 0.5)
    finish_pool = 1 - decision
    return {
        "round_1": float(finish_pool * 0.40),
        "round_2": float(finish_pool * 0.30),
        "round_3": float(finish_pool * 0.15),
        "round_4": float(finish_pool * 0.10),
        "round_5": float(finish_pool * 0.05),
        "decision": float(decision),
    }


def _round_estimate(round_dist: dict[str, float]) -> tuple[int, int] | None:
    if round_dist.get("decision", 0.0) >= 0.50:
        return None
    # Otherwise, take the two consecutive rounds with the highest combined mass.
    best = (1, 2)
    best_mass = 0.0
    for lo in range(1, 5):
        m = round_dist.get(f"round_{lo}", 0.0) + round_dist.get(f"round_{lo+1}", 0.0)
        if m > best_mass:
            best_mass = m
            best = (lo, lo + 1)
    return best


def _confidence(streams: dict[str, float]) -> tuple[Confidence, float]:
    vals = list(streams.values())
    spread = float(max(vals) - min(vals))
    if spread <= 0.04:
        return "high", spread
    if spread <= 0.10:
        return "medium", spread
    return "low", spread


def _build_drivers(
    row: pd.DataFrame, prob_a: float, state: _State
) -> tuple[list[str], list[str], list[str]]:
    """Return (top_drivers, advantages_a, advantages_b) using SHAP from the xgb model.

    Falls back to absolute feature contributions when SHAP isn't installed.
    """
    bundle = state.bundle
    assert bundle is not None, "state not loaded — call _load_state() first"
    feats = bundle["feats"]
    X = row.copy()
    for f in feats:
        if f not in X.columns:
            X[f] = 0.0
    X = X[feats]
    contributions: dict[str, float] = {}
    try:
        import shap

        explainer = shap.TreeExplainer(bundle["xgb"])
        sv = explainer.shap_values(X)
        if isinstance(sv, list):
            sv = sv[1]
        for f, v in zip(feats, sv[0], strict=False):
            contributions[f] = float(v)
    except Exception:
        # Heuristic: use feature value × global importance as a stand-in.
        booster = bundle["xgb"].get_booster() if hasattr(bundle["xgb"], "get_booster") else bundle["xgb"]
        try:
            gain = booster.get_score(importance_type="gain")
        except Exception:
            gain = {}
        for f in feats:
            contributions[f] = float(X.iloc[0][f]) * float(gain.get(f, 1.0))

    # Filter out raw absolute context fields — they're not signal, just noise.
    contributions = {k: v for k, v in contributions.items() if k not in _NON_DRIVER}
    ranked = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top = [_humanise(f, float(X.iloc[0][f])) for f, _ in ranked[:5]]
    a_advs: list[str] = []
    b_advs: list[str] = []
    for f, c in ranked[:8]:
        line = _humanise(f, float(X.iloc[0][f]))
        if c >= 0:
            a_advs.append(line)  # positive contribution favours fighter A
        else:
            b_advs.append(line)
    return top, a_advs[:5], b_advs[:5]


def _build_warnings(
    streams: dict[str, float],
    a_hist: pd.DataFrame,
    b_hist: pd.DataFrame,
    method_probs: dict[str, float],
    prob_a: float,
    confidence: Confidence,
) -> list[str]:
    warnings: list[str] = []
    spread = max(streams.values()) - min(streams.values())
    if spread > 0.10:
        warnings.append(
            f"High ensemble disagreement (spread {spread*100:.0f} pp); favourite uncertain."
        )

    # Recent submission threat from the underdog
    underdog_hist = b_hist if prob_a >= 0.5 else a_hist
    if len(underdog_hist):
        sub_recent = cf.sub_avg(underdog_hist.tail(8), date.today())
        if sub_recent > 1.5 and method_probs.get("Submission", 0.0) > 0.18:
            warnings.append(
                f"Underdog has live submission threat (sub_avg/15 = {sub_recent:.1f}); upset risk on the ground."
            )

    # KO loss recency on the favourite
    fav_hist = a_hist if prob_a >= 0.5 else b_hist
    if len(fav_hist):
        recent = fav_hist.tail(5)
        ko_losses = (
            recent["winner"].astype(bool).eq(False)
            & recent["method"].astype(str).str.contains("KO", na=False)
        ).sum()
        if ko_losses >= 1:
            warnings.append("Favourite has a recent KO loss (last 5 fights) — chin caveat.")

    if confidence == "low":
        warnings.append("Low-confidence call — model says coinflip-adjacent.")
    return warnings


def _n_similar_fights(matrix: pd.DataFrame | None, row: pd.DataFrame) -> int:
    """How many training-window fights are k-NN-like to this matchup?

    Cheap proxy: count fights within ±100 Elo diff and same weight class.
    """
    if matrix is None or len(matrix) == 0:
        return 0
    elo_diff = float(row["elo_diff"].iloc[0])
    wc = row["weight_class"].iloc[0] if "weight_class" in row.columns else None
    mask = (matrix["elo_diff"] - elo_diff).abs() <= 100
    if wc is not None and "weight_class" in matrix.columns:
        mask &= matrix["weight_class"] == wc
    return int(mask.sum())

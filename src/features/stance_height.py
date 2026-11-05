"""Stance-context × height-context matchup feature pack.

Extends the Step-6 stance geometry features with *evidence from each
fighter's own history*: how did this fighter actually perform in
open-stance pairings (orthodox vs southpaw) versus closed-stance pairings
(same stance), and against taller versus shorter opponents — then
conditions those bucket edges on the CURRENT matchup.

All bucket metrics are time-decayed (same half-life as core_features) and
shrunk toward the fighter's own baseline by rounds of evidence in the
bucket, so a fighter with 2 open-stance rounds contributes almost nothing
while a fighter with 40 contributes nearly the raw edge.

Two feature packs live here:

`stance_height_matchup_features` — context-edge pack (11 features): how each
fighter performed in the CURRENT stance/height context vs their baseline.

`adaptability_features` — adaptability pack (12 features): how context-
SENSITIVE each fighter is at all (some fighters perform identically no matter
the stance pairing, height gap, or opponent striking style — for them the
context edges are noise), plus a striking-style context edge covering the
axes stance/height miss: opponent volume, grappling pressure, clinch vs
range profile (dirty boxer / Muay Thai vs rangey point fighter), and
kick-centricity.

Context-edge pack features:
    height_diff                     raw height diff a − b (inches, 0 if unknown)
    stance_ctx_strike_edge_a/b      per-15 net-strike edge of each fighter in
                                    the current stance context (open or closed)
                                    relative to their own overall baseline
    stance_ctx_strike_edge_diff     a − b
    stance_ctx_win_edge_diff        same conditioning, win-rate based, a − b
    height_ctx_strike_edge_a/b      per-15 net-strike edge of each fighter vs
                                    the current height context (opp taller /
                                    shorter) relative to their baseline
    height_ctx_strike_edge_diff     a − b
    height_ctx_win_edge_diff        win-rate based, a − b
    stance_height_combo_diff        stance_ctx_strike_edge_diff +
                                    height_ctx_strike_edge_diff (the ensemble)
    open_stance_height_diff         open_stance flag × height_diff (geometry
                                    interaction: e.g. southpaw giving up height
                                    to an orthodox opponent)

Adaptability pack features:
    stance_sens_a/b                 |open − closed| performance swing
    height_sens_a/b                 |vs-taller − vs-shorter| swing
    style_sens_a/b                  mean swing across the 4 striking-style
                                    axes (volume, grappling, clinch/range,
                                    kicks/hands)
    adaptability_a/b/diff           −mean(sensitivities); higher = style-proof
    style_ctx_edge_a/b/diff         historical edge vs opponents of the class
                                    the current opponent belongs to

Temporal-leakage contract: only the fighter's PRIOR fights (the history
slice handed to build_feature_row) are used; opponent stance/height come
from the static bio table, exactly like the existing stance/reach features.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.features.core_features import _decay_weights, _safe_minutes

# Rounds of in-bucket evidence at which the shrinkage weight reaches 0.5.
SHRINK_K_ROUNDS = 8.0

# Height differences inside this band (inches) count as "even" and fall out
# of both the taller and shorter buckets (they still feed the baseline).
HEIGHT_NEUTRAL_BAND_IN = 1.0

# Striking-style context thresholds. Deliberately the same definitions for
# tagging PAST opponents (what they landed in that fight) and classifying the
# CURRENT opponent (their decayed career rates), so the buckets line up:
# slpm ≈ league-average sig-strike output; td15 = takedowns landed per 15.
# Range and kick shares split striking archetypes volume alone can't — a
# clinch-heavy Muay Thai fighter or dirty boxer vs a rangey point fighter
# (high distance share), and kickers vs pure-hands strikers.
HIGH_VOLUME_SLPM = 4.5
GRAPPLING_TD15 = 1.5
CLINCH_SHARE = 0.25
LEG_SHARE = 0.25
# Shares from fights where the opponent landed fewer sig strikes than this
# are meaningless (3 strikes, all in the clinch ≠ clinch fighter) → untagged.
MIN_STRIKES_FOR_SHARE = 10.0

_PAIRED_STANCES = {"orthodox", "southpaw"}


def _stance_pairing(stance_x: str, stance_y: str) -> str | None:
    """'open' | 'closed' for orthodox/southpaw pairings, else None (switch etc.)."""
    sx = (stance_x or "").lower().strip()
    sy = (stance_y or "").lower().strip()
    if sx not in _PAIRED_STANCES or sy not in _PAIRED_STANCES:
        return None
    return "open" if sx != sy else "closed"


def _height_context(own_height: float, opp_height: float) -> str | None:
    """'taller' | 'shorter' (the OPPONENT relative to self), else None."""
    if own_height is None or opp_height is None:
        return None
    if np.isnan(own_height) or np.isnan(opp_height):
        return None
    delta = float(opp_height) - float(own_height)
    if delta >= HEIGHT_NEUTRAL_BAND_IN:
        return "taller"
    if delta <= -HEIGHT_NEUTRAL_BAND_IN:
        return "shorter"
    return None


def _bucket_metrics(
    history: pd.DataFrame,
    mask: np.ndarray,
    weights: np.ndarray,
    minutes: np.ndarray,
) -> tuple[float, float, float]:
    """(net strikes per 15, win rate, rounds of evidence) over history[mask]."""
    if not mask.any():
        return np.nan, np.nan, 0.0
    w = weights[mask]
    m = minutes[mask]
    landed = history["sig_strikes_landed"].to_numpy(dtype=float)[mask]
    absorbed = history["opp_sig_strikes_landed"].to_numpy(dtype=float)[mask]
    wins = history["winner"].astype(bool).to_numpy(dtype=float)[mask]

    denom_min = float((w * m).sum())
    strike_net_15 = (
        float((w * (landed - absorbed)).sum()) / denom_min * 15.0
        if denom_min > 1e-9 else np.nan
    )
    denom_w = float(w.sum())
    win_rate = float((w * wins).sum()) / denom_w if denom_w > 1e-9 else np.nan

    if "round_finished" in history.columns:
        rounds = pd.to_numeric(
            history["round_finished"], errors="coerce"
        ).to_numpy(dtype=float)[mask]
        rounds = np.where(np.isnan(rounds), m / 5.0, rounds)
    else:
        rounds = m / 5.0
    return strike_net_15, win_rate, float(rounds.sum())


def _shrunk_edge(bucket_val: float, baseline_val: float, n_rounds: float) -> float:
    """Empirical-Bayes edge: (bucket − baseline) shrunk by rounds of evidence."""
    if np.isnan(bucket_val) or np.isnan(baseline_val):
        return 0.0
    shrink = n_rounds / (n_rounds + SHRINK_K_ROUNDS)
    return float(shrink * (bucket_val - baseline_val))


def _fighter_context_edges(
    history: pd.DataFrame,
    own_stance: str,
    own_height: float,
    reference_date: date,
    bio_lookup: dict,
    ctx_stance: str | None,
    ctx_height: str | None,
) -> dict:
    """Per-fighter edges in the current stance/height context vs own baseline."""
    out = {
        "stance_strike_edge": 0.0,
        "stance_win_edge": 0.0,
        "height_strike_edge": 0.0,
        "height_win_edge": 0.0,
    }
    if len(history) == 0 or "opponent_id" not in history.columns:
        return out

    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)

    stance_tags: list[str | None] = []
    height_tags: list[str | None] = []
    for opp_id in history["opponent_id"]:
        opp_bio = bio_lookup.get(opp_id, {})
        stance_tags.append(_stance_pairing(own_stance, opp_bio.get("stance", "")))
        height_tags.append(
            _height_context(own_height, opp_bio.get("height_in", np.nan))
        )
    stance_arr = np.array([t or "" for t in stance_tags])
    height_arr = np.array([t or "" for t in height_tags])

    all_mask = np.ones(len(history), dtype=bool)
    base_strike, base_win, _ = _bucket_metrics(history, all_mask, weights, minutes)

    if ctx_stance in ("open", "closed"):
        mask = stance_arr == ctx_stance
        strike, win, n_rounds = _bucket_metrics(history, mask, weights, minutes)
        out["stance_strike_edge"] = _shrunk_edge(strike, base_strike, n_rounds)
        out["stance_win_edge"] = _shrunk_edge(win, base_win, n_rounds)

    if ctx_height in ("taller", "shorter"):
        mask = height_arr == ctx_height
        strike, win, n_rounds = _bucket_metrics(history, mask, weights, minutes)
        out["height_strike_edge"] = _shrunk_edge(strike, base_strike, n_rounds)
        out["height_win_edge"] = _shrunk_edge(win, base_win, n_rounds)

    return out


def _all_bucket_edges(
    history: pd.DataFrame,
    own_stance: str,
    own_height: float,
    reference_date: date,
    bio_lookup: dict,
) -> dict[str, float]:
    """Shrunk per-15 net-strike edges for EVERY context bucket vs baseline.

    Buckets: open/closed (stance pairing), taller/shorter (opponent height),
    high_vol/low_vol (opponent striking output in that fight), grap/no_grap
    (opponent takedowns landed in that fight), clinch_fight/range_fight
    (opponent's clinch share of landed strikes) and kicker/hands (opponent's
    leg-strike share). Missing evidence → 0.0.
    """
    keys = ("open", "closed", "taller", "shorter",
            "high_vol", "low_vol", "grap", "no_grap",
            "clinch_fight", "range_fight", "kicker", "hands")
    if len(history) == 0 or "opponent_id" not in history.columns:
        return dict.fromkeys(keys, 0.0)

    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)

    stance_tags, height_tags = [], []
    for opp_id in history["opponent_id"]:
        opp_bio = bio_lookup.get(opp_id, {})
        stance_tags.append(_stance_pairing(own_stance, opp_bio.get("stance", "")) or "")
        height_tags.append(
            _height_context(own_height, opp_bio.get("height_in", np.nan)) or ""
        )
    stance_arr = np.array(stance_tags)
    height_arr = np.array(height_tags)

    # Striking-style tags come from what the opponent DID in that fight —
    # observable in the fighter's own history row, so fully leakage-free.
    opp_land = history["opp_sig_strikes_landed"].fillna(0).to_numpy(dtype=float)
    if "opp_takedowns_landed" in history.columns:
        opp_td = history["opp_takedowns_landed"].fillna(0).to_numpy(dtype=float)
    else:
        opp_td = np.zeros(len(history))
    opp_slpm = opp_land / minutes
    opp_td15 = opp_td / minutes * 15.0

    def _opp_share(col: str) -> np.ndarray:
        """Opponent's share of landed strikes from `col`; NaN when unknowable."""
        if col not in history.columns:
            return np.full(len(history), np.nan)
        num = pd.to_numeric(history[col], errors="coerce").to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            share = num / opp_land
        share[opp_land < MIN_STRIKES_FOR_SHARE] = np.nan
        return share

    clinch_share = _opp_share("opp_clinch_landed")
    leg_share = _opp_share("opp_leg_landed")

    def _split(vals: np.ndarray, thresh: float) -> tuple[np.ndarray, np.ndarray]:
        known = ~np.isnan(vals)
        return known & (vals >= thresh), known & (vals < thresh)

    clinch_hi, clinch_lo = _split(clinch_share, CLINCH_SHARE)
    leg_hi, leg_lo = _split(leg_share, LEG_SHARE)

    masks = {
        "open":         stance_arr == "open",
        "closed":       stance_arr == "closed",
        "taller":       height_arr == "taller",
        "shorter":      height_arr == "shorter",
        "high_vol":     opp_slpm >= HIGH_VOLUME_SLPM,
        "low_vol":      opp_slpm < HIGH_VOLUME_SLPM,
        "grap":         opp_td15 >= GRAPPLING_TD15,
        "no_grap":      opp_td15 < GRAPPLING_TD15,
        "clinch_fight": clinch_hi,
        "range_fight":  clinch_lo,
        "kicker":       leg_hi,
        "hands":        leg_lo,
    }

    all_mask = np.ones(len(history), dtype=bool)
    base_strike, _, _ = _bucket_metrics(history, all_mask, weights, minutes)

    out = {}
    for key, mask in masks.items():
        strike, _, n_rounds = _bucket_metrics(history, mask, weights, minutes)
        out[key] = _shrunk_edge(strike, base_strike, n_rounds)
    return out


def _sensitivity_spreads(edges: dict[str, float]) -> tuple[float, float, float]:
    """(stance, height, style) sensitivity: bucket-to-bucket performance swing.

    Each is |edge(bucket) − edge(counter-bucket)| of already-shrunk edges, so
    thin evidence reads as ~0 (indistinguishable from genuinely adaptable —
    both mean "no demonstrated context dependence"). Style averages its two
    sub-dimensions (opponent volume, opponent grappling).
    """
    stance_sens = abs(edges["open"] - edges["closed"])
    height_sens = abs(edges["taller"] - edges["shorter"])
    style_sens = 0.25 * (
        abs(edges["high_vol"] - edges["low_vol"])
        + abs(edges["grap"] - edges["no_grap"])
        + abs(edges["clinch_fight"] - edges["range_fight"])
        + abs(edges["kicker"] - edges["hands"])
    )
    return stance_sens, height_sens, style_sens


def adaptability_features(
    a_hist: pd.DataFrame,
    b_hist: pd.DataFrame,
    stance_a: str,
    stance_b: str,
    height_a: float,
    height_b: float,
    reference_date: date,
    bio_lookup: dict,
    stats_a: dict,
    stats_b: dict,
) -> dict:
    """Adaptability (context-insensitivity) + striking-style context edges.

    `stats_a`/`stats_b` are compute_fighter_style_stats dicts for the CURRENT
    fighters — used to classify what style of opponent each one is about to
    face (same thresholds as the historical bucket tags).
    """
    ha = float(height_a) if height_a is not None else np.nan
    hb = float(height_b) if height_b is not None else np.nan

    edges_a = _all_bucket_edges(a_hist, stance_a, ha, reference_date, bio_lookup)
    edges_b = _all_bucket_edges(b_hist, stance_b, hb, reference_date, bio_lookup)

    sens_a = _sensitivity_spreads(edges_a)
    sens_b = _sensitivity_spreads(edges_b)
    adapt_a = -float(np.mean(sens_a))
    adapt_b = -float(np.mean(sens_b))

    # Style-context edge: each fighter's historical edge vs opponents of the
    # class the CURRENT opponent belongs to. Volume/grappling come from the
    # opponent's decayed rate stats; range/kick profile from their decayed
    # clinch and leg shares (what a rangey point fighter, a clinch-heavy Muay
    # Thai fighter, and a dirty boxer actually look like in the data).
    def _decayed_share(hist: pd.DataFrame, num_col: str) -> float:
        if len(hist) == 0 or num_col not in hist.columns:
            return np.nan
        w = _decay_weights(hist, reference_date)
        num = pd.to_numeric(hist[num_col], errors="coerce").fillna(0).to_numpy(dtype=float)
        den = hist["sig_strikes_landed"].fillna(0).to_numpy(dtype=float)
        total = float((w * den).sum())
        if total < MIN_STRIKES_FOR_SHARE:
            return np.nan
        return float((w * num).sum()) / total

    def _style_ctx(edges: dict, opp_stats: dict, opp_hist: pd.DataFrame) -> float:
        vol_key = "high_vol" if opp_stats["slpm"] >= HIGH_VOLUME_SLPM else "low_vol"
        grap_key = "grap" if opp_stats["td15"] >= GRAPPLING_TD15 else "no_grap"
        total = edges[vol_key] + edges[grap_key]
        clinch = _decayed_share(opp_hist, "clinch_landed")
        if not np.isnan(clinch):
            total += edges["clinch_fight" if clinch >= CLINCH_SHARE else "range_fight"]
        leg = _decayed_share(opp_hist, "leg_landed")
        if not np.isnan(leg):
            total += edges["kicker" if leg >= LEG_SHARE else "hands"]
        return float(total)

    style_ctx_a = _style_ctx(edges_a, stats_b, b_hist)
    style_ctx_b = _style_ctx(edges_b, stats_a, a_hist)

    return {
        "stance_sens_a":      float(sens_a[0]),
        "stance_sens_b":      float(sens_b[0]),
        "height_sens_a":      float(sens_a[1]),
        "height_sens_b":      float(sens_b[1]),
        "style_sens_a":       float(sens_a[2]),
        "style_sens_b":       float(sens_b[2]),
        "adaptability_a":     adapt_a,
        "adaptability_b":     adapt_b,
        "adaptability_diff":  adapt_a - adapt_b,
        "style_ctx_edge_a":   style_ctx_a,
        "style_ctx_edge_b":   style_ctx_b,
        "style_ctx_edge_diff": style_ctx_a - style_ctx_b,
    }


def stance_height_matchup_features(
    a_hist: pd.DataFrame,
    b_hist: pd.DataFrame,
    stance_a: str,
    stance_b: str,
    height_a: float,
    height_b: float,
    reference_date: date,
    bio_lookup: dict,
) -> dict:
    """History-conditioned stance × height matchup features for A vs B."""
    ha = float(height_a) if height_a is not None else np.nan
    hb = float(height_b) if height_b is not None else np.nan
    heights_known = not (np.isnan(ha) or np.isnan(hb))
    height_diff = (ha - hb) if heights_known else 0.0

    ctx_stance = _stance_pairing(stance_a, stance_b)
    # Opponent's height relative to each fighter, for bucket selection.
    ctx_height_a = _height_context(ha, hb)  # is B taller/shorter than A?
    ctx_height_b = _height_context(hb, ha)

    edges_a = _fighter_context_edges(
        a_hist, stance_a, ha, reference_date, bio_lookup, ctx_stance, ctx_height_a
    )
    edges_b = _fighter_context_edges(
        b_hist, stance_b, hb, reference_date, bio_lookup, ctx_stance, ctx_height_b
    )

    stance_edge_diff = edges_a["stance_strike_edge"] - edges_b["stance_strike_edge"]
    height_edge_diff = edges_a["height_strike_edge"] - edges_b["height_strike_edge"]
    open_flag = 1.0 if ctx_stance == "open" else 0.0

    return {
        "height_diff": float(height_diff),
        "stance_ctx_strike_edge_a": edges_a["stance_strike_edge"],
        "stance_ctx_strike_edge_b": edges_b["stance_strike_edge"],
        "stance_ctx_strike_edge_diff": float(stance_edge_diff),
        "stance_ctx_win_edge_diff": float(
            edges_a["stance_win_edge"] - edges_b["stance_win_edge"]
        ),
        "height_ctx_strike_edge_a": edges_a["height_strike_edge"],
        "height_ctx_strike_edge_b": edges_b["height_strike_edge"],
        "height_ctx_strike_edge_diff": float(height_edge_diff),
        "height_ctx_win_edge_diff": float(
            edges_a["height_win_edge"] - edges_b["height_win_edge"]
        ),
        "stance_height_combo_diff": float(stance_edge_diff + height_edge_diff),
        "open_stance_height_diff": float(open_flag * height_diff),
    }

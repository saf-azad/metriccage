"""Assemble the final feature matrix used by all models.

Every feature for fight on date `d` is computed using ONLY data with date < d.
This module is the choke point that enforces that contract; if a feature can
peek at the future, the bug is here.

PIPELINE
    1. Load `data/interim/fights.parquet` (canonical bilateral fights schema)
    2. Sort chronologically; build a per-fighter history view as we go
    3. For each fight, with state = "everything strictly before event_date":
         - derive each fighter's history slice
         - call core_features.* + Elo lookup + bio lookup
         - call style_mismatch.* (archetype-conditioned composite features)
         - assemble diff features (a − b)
         - emit one feature row
    4. After scoring the row, update Elo with the fight result and append the
       fight to each fighter's history
    5. Write data/processed/feature_matrix.parquet

OUTPUT SCHEMA (UPDATE_2.md feature pack — ~45 features):

    fight_id, event_id, event_date, weight_class,
    fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name,
    method, round_finished, fight_duration_min, fighter_a_won,

    --- Kept legacy diff features (fallback if new SHAP < 2.0 post-retrain) ---
    elo_diff, elo_prob_a, strike_net_diff,
    kd_absorbed_per15_diff,
    win_pct_diff, finish_rate_diff, rounds_exp_diff, streak_diff,
    days_inactive_diff, n_fights_a, n_fights_b,
    reach_diff,
    strike_acc_diff, strike_def_diff, control_pct_diff,
    td_acc_diff, td_def_acc_diff,
    a_elo_pre, b_elo_pre,

    --- Weight-class change ---
    weight_change_a, weight_change_b, weight_change_diff,
    first_at_class_a, first_at_class_b,
    natural_wc_dev_a, natural_wc_dev_b,

    --- UPDATE_2 Style Archetype (Step 1) ---
    arch_a_{0..7}, arch_b_{0..7}, arch_distance, arch_similarity,

    --- UPDATE_2 Striker-Grappler Mismatch (Step 2) ---
    grappler_path_a, grappler_path_b, striker_path_a, striker_path_b,
    sg_mismatch_net, td_dominance_diff,

    --- UPDATE_2 Power-Durability Mismatch (Step 3) ---
    ko_danger_a, ko_danger_b, chin_durability_a, chin_durability_b,
    ko_threat_net, ko_danger_differential, b_chin_vulnerable,

    --- UPDATE_2 Submission Chain Danger (Step 4, PRIORITY) ---
    sub_danger_a, sub_danger_b, sub_danger_diff,
    sub_danger_combined, sub_att_rate_diff,

    --- UPDATE_2 Pace-Pressure Mismatch (Step 5) ---
    pace_mismatch_diff, counter_efficiency_diff,
    pressure_index_a, pressure_index_b,
    counter_threat_b_vs_a, counter_threat_a_vs_b,
    gas_out_risk_diff, b_counter_upset_setup,

    --- UPDATE_2 Stance Geometry (Step 6) ---
    stance_advantage_a, stance_score_amplified,
    stance_win_prob_uplift, open_stance,

    --- Stance-context × height-context matchup layer (stance_height.py) ---
    height_diff,
    stance_ctx_strike_edge_a, stance_ctx_strike_edge_b,
    stance_ctx_strike_edge_diff, stance_ctx_win_edge_diff,
    height_ctx_strike_edge_a, height_ctx_strike_edge_b,
    height_ctx_strike_edge_diff, height_ctx_win_edge_diff,
    stance_height_combo_diff, open_stance_height_diff,

    --- Adaptability / context-insensitivity layer (stance_height.py) ---
    stance_sens_a, stance_sens_b, height_sens_a, height_sens_b,
    style_sens_a, style_sens_b,
    adaptability_a, adaptability_b, adaptability_diff,
    style_ctx_edge_a, style_ctx_edge_b, style_ctx_edge_diff,

    --- UPDATE_2 Upset Fingerprint (Step 7) ---
    trajectory_diff, elo_form_divergence_a, elo_form_divergence_b,
    age_curve_a, age_curve_b, age_curve_diff, prime_mismatch,
    rust_a, rust_b, rust_diff, favourite_rusty,
    fr1_danger_diff, a_upset_risk_score,

Cluster membership columns are added downstream by clustering.assign_membership().
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import numpy as np
import pandas as pd

from src.features import core_features as cf
from src.features.archetypes import (
    ARCHETYPES,
    archetype_vector_with_fallback,
    compute_fighter_style_stats,
)
from src.features.elo import MMAElo
from src.features.stance_height import (
    adaptability_features,
    stance_height_matchup_features,
)
from src.features.style_mismatch import (
    pace_pressure_features,
    power_durability_features,
    stance_advantage_features,
    striker_grappler_mismatch,
    submission_chain_features,
    upset_fingerprint_features,
)

# --- Per-fighter history view ------------------------------------------------


def _fight_to_perfighter_rows(fight: pd.Series) -> tuple[dict, dict]:
    """Split one bilateral fight row into two per-fighter rows (one per corner)."""
    base = {
        "event_date": pd.to_datetime(fight["event_date"]),
        "weight_class": fight.get("weight_class"),
        "round_finished": fight.get("round_finished"),
        "fight_duration_seconds": float(fight.get("fight_duration_sec", 0.0)),
        "fight_duration_minutes": float(fight.get("fight_duration_min", 0.0)),
        "method": str(fight.get("method_canon", fight.get("method", ""))),
    }

    a_won = bool(int(fight.get("fighter_a_won", 0)))

    a_row = {
        **base,
        "fighter_id": fight["fighter_a_id"],
        "opponent_id": fight["fighter_b_id"],
        "fighter_role": "a",
        "winner": a_won,
        "sig_strikes_landed": int(fight.get("ss_landed_a", 0)),
        "opp_sig_strikes_landed": int(fight.get("ss_landed_b", 0)),
        "takedowns_landed": int(fight.get("td_landed_a", 0)),
        "opp_takedowns_landed": int(fight.get("td_landed_b", 0)),
        "sub_attempts": int(fight.get("sub_att_a", 0)),
        "knockdowns": int(fight.get("kd_a", 0)),
        "opp_knockdowns": int(fight.get("kd_b", 0)),
    }
    for src_col, dst_col in [
        ("ss_attempted_a", "sig_strikes_attempted"),
        ("ss_attempted_b", "opp_sig_strikes_attempted"),
        ("td_attempted_a", "takedowns_attempted"),
        ("td_attempted_b", "opp_takedowns_attempted"),
        ("control_time_a", "control_time_seconds"),
        ("control_time_b", "opp_control_time_seconds"),
        # Target-zone significant strikes (head/body/leg landed + attempted)
        ("head_landed_a", "head_landed"),
        ("head_att_a", "head_attempted"),
        ("body_landed_a", "body_landed"),
        ("body_att_a", "body_attempted"),
        ("leg_landed_a", "leg_landed"),
        ("leg_att_a", "leg_attempted"),
        ("head_landed_b", "opp_head_landed"),
        ("head_att_b", "opp_head_attempted"),
        ("body_landed_b", "opp_body_landed"),
        ("body_att_b", "opp_body_attempted"),
        ("leg_landed_b", "opp_leg_landed"),
        ("leg_att_b", "opp_leg_attempted"),
        # Positional splits (range/clinch profile for the adaptability layer)
        ("clinch_landed_a", "clinch_landed"),
        ("distance_landed_a", "distance_landed"),
        ("clinch_landed_b", "opp_clinch_landed"),
        ("distance_landed_b", "opp_distance_landed"),
    ]:
        if src_col in fight and pd.notna(fight[src_col]):
            a_row[dst_col] = float(fight[src_col])

    b_row = {
        **base,
        "fighter_id": fight["fighter_b_id"],
        "opponent_id": fight["fighter_a_id"],
        "fighter_role": "b",
        "winner": (not a_won),
        "sig_strikes_landed": int(fight.get("ss_landed_b", 0)),
        "opp_sig_strikes_landed": int(fight.get("ss_landed_a", 0)),
        "takedowns_landed": int(fight.get("td_landed_b", 0)),
        "opp_takedowns_landed": int(fight.get("td_landed_a", 0)),
        "sub_attempts": int(fight.get("sub_att_b", 0)),
        "knockdowns": int(fight.get("kd_b", 0)),
        "opp_knockdowns": int(fight.get("kd_a", 0)),
    }
    for src_col, dst_col in [
        ("ss_attempted_b", "sig_strikes_attempted"),
        ("ss_attempted_a", "opp_sig_strikes_attempted"),
        ("td_attempted_b", "takedowns_attempted"),
        ("td_attempted_a", "opp_takedowns_attempted"),
        ("control_time_b", "control_time_seconds"),
        ("control_time_a", "opp_control_time_seconds"),
        ("head_landed_b", "head_landed"),
        ("head_att_b", "head_attempted"),
        ("body_landed_b", "body_landed"),
        ("body_att_b", "body_attempted"),
        ("leg_landed_b", "leg_landed"),
        ("leg_att_b", "leg_attempted"),
        ("head_landed_a", "opp_head_landed"),
        ("head_att_a", "opp_head_attempted"),
        ("body_landed_a", "opp_body_landed"),
        ("body_att_a", "opp_body_attempted"),
        ("leg_landed_a", "opp_leg_landed"),
        ("leg_att_a", "opp_leg_attempted"),
        ("clinch_landed_b", "clinch_landed"),
        ("distance_landed_b", "distance_landed"),
        ("clinch_landed_a", "opp_clinch_landed"),
        ("distance_landed_a", "opp_distance_landed"),
    ]:
        if src_col in fight and pd.notna(fight[src_col]):
            b_row[dst_col] = float(fight[src_col])

    return a_row, b_row


# --- Bio helpers -------------------------------------------------------------


def _build_bio_lookup(fighters: pd.DataFrame | None) -> dict:
    if fighters is None or len(fighters) == 0:
        return {}
    out: dict[str, dict] = {}
    for r in fighters.itertuples(index=False):
        out[r.fighter_id] = {
            "name": getattr(r, "name", ""),
            "height_in": float(getattr(r, "height_in", np.nan) or np.nan),
            "reach_in": float(getattr(r, "reach_in", np.nan) or np.nan),
            "stance": str(getattr(r, "stance", "") or ""),
            "dob": getattr(r, "dob", None),
        }
    return out


def _age(dob, ref: date) -> float:
    if dob is None or (isinstance(dob, float) and np.isnan(dob)):
        return np.nan
    if isinstance(dob, str):
        try:
            dob = pd.to_datetime(dob).date()
        except Exception:
            return np.nan
    if isinstance(dob, pd.Timestamp):
        dob = dob.date()
    days = (ref - dob).days
    return days / 365.25 if days > 0 else np.nan


# --- Public API --------------------------------------------------------------


def build_feature_row(
    fighter_a_id: str,
    fighter_b_id: str,
    event_date: date,
    fights_history: dict[str, pd.DataFrame],
    elo_state: MMAElo,
    bio_lookup: dict | None = None,
    *,
    cluster_model=None,
    weight_class: str = "",
    n_rounds: int = 3,
) -> dict:
    """Return one feature dict for the (A vs B, on event_date) pairing.

    `fights_history` is a {fighter_id: history DataFrame} cache where each
    DataFrame holds that fighter's PRIOR fights (strictly before event_date).
    `elo_state` is the live MMAElo replayed up to but not including this date.
    """
    a_hist = fights_history.get(fighter_a_id, pd.DataFrame())
    b_hist = fights_history.get(fighter_b_id, pd.DataFrame())

    # -------------------------------------------------------------------------
    # Legacy Tier-1 rate features (kept for backward-compat + SHAP comparison)
    # -------------------------------------------------------------------------
    a_sapm = cf.sapm(a_hist, event_date)
    b_sapm = cf.sapm(b_hist, event_date)
    a_kd_abs = cf.kd_absorbed_per15(a_hist, event_date)
    b_kd_abs = cf.kd_absorbed_per15(b_hist, event_date)

    # Target-zone strike rates (head/body/leg landed + absorbed, per 15 min, time-decayed)
    a_head_l, b_head_l = cf.head_landed_per15(a_hist, event_date), cf.head_landed_per15(b_hist, event_date)
    a_body_l, b_body_l = cf.body_landed_per15(a_hist, event_date), cf.body_landed_per15(b_hist, event_date)
    a_leg_l,  b_leg_l  = cf.leg_landed_per15(a_hist, event_date),  cf.leg_landed_per15(b_hist, event_date)
    a_head_a, b_head_a = cf.head_absorbed_per15(a_hist, event_date), cf.head_absorbed_per15(b_hist, event_date)
    a_body_a, b_body_a = cf.body_absorbed_per15(a_hist, event_date), cf.body_absorbed_per15(b_hist, event_date)
    a_leg_a,  b_leg_a  = cf.leg_absorbed_per15(a_hist, event_date),  cf.leg_absorbed_per15(b_hist, event_date)
    a_head_acc, b_head_acc = cf.head_accuracy(a_hist, event_date), cf.head_accuracy(b_hist, event_date)
    a_leg_acc,  b_leg_acc  = cf.leg_accuracy(a_hist, event_date),  cf.leg_accuracy(b_hist, event_date)
    a_slpm_legacy = cf.slpm(a_hist, event_date)
    b_slpm_legacy = cf.slpm(b_hist, event_date)

    a_sacc = cf.strike_accuracy(a_hist, event_date)
    b_sacc = cf.strike_accuracy(b_hist, event_date)
    a_sdef = cf.strike_defence(a_hist, event_date)
    b_sdef = cf.strike_defence(b_hist, event_date)
    a_ctrl = cf.control_pct(a_hist, event_date)
    b_ctrl = cf.control_pct(b_hist, event_date)
    a_tdt = cf.td_true_accuracy(a_hist, event_date)
    b_tdt = cf.td_true_accuracy(b_hist, event_date)
    a_tdtd = cf.td_true_defence(a_hist, event_date)
    b_tdtd = cf.td_true_defence(b_hist, event_date)

    def _diff_or_zero(x: float, y: float) -> float:
        if x != x or y != y:
            return 0.0
        return float(x - y)

    a_winp = cf.win_pct(a_hist, event_date)
    b_winp = cf.win_pct(b_hist, event_date)
    a_finish = cf.finish_rate(a_hist)
    b_finish = cf.finish_rate(b_hist)
    a_rexp = cf.rounds_experience(a_hist)
    b_rexp = cf.rounds_experience(b_hist)
    a_streak = cf.streak(a_hist)
    b_streak = cf.streak(b_hist)

    a_last = pd.to_datetime(a_hist["event_date"]).max().date() if len(a_hist) else None
    b_last = pd.to_datetime(b_hist["event_date"]).max().date() if len(b_hist) else None
    a_inactive = cf.days_inactive(a_last, event_date)
    b_inactive = cf.days_inactive(b_last, event_date)

    # Elo
    a_elo_pre = elo_state.get(fighter_a_id)
    b_elo_pre = elo_state.get(fighter_b_id)
    elo_prob_a = elo_state.win_probability(fighter_a_id, fighter_b_id)

    # Bio
    bios = bio_lookup or {}
    a_bio = bios.get(fighter_a_id, {})
    b_bio = bios.get(fighter_b_id, {})
    a_reach = a_bio.get("reach_in", np.nan)
    b_reach = b_bio.get("reach_in", np.nan)
    a_age = _age(a_bio.get("dob"), event_date)
    b_age = _age(b_bio.get("dob"), event_date)
    stance_a = (a_bio.get("stance") or "").lower()
    stance_b = (b_bio.get("stance") or "").lower()

    wc = weight_class or ""

    # -------------------------------------------------------------------------
    # Weight-class change (bout's declared class is known pre-fight, so this
    # is legitimate pre-fight information — same contract as stance features)
    # -------------------------------------------------------------------------
    a_wchg = cf.weight_change(a_hist, wc)
    b_wchg = cf.weight_change(b_hist, wc)
    a_first_wc = cf.first_fight_at_class(a_hist, wc)
    b_first_wc = cf.first_fight_at_class(b_hist, wc)
    a_wc_dev = cf.natural_weight_deviation(a_hist, wc, event_date)
    b_wc_dev = cf.natural_weight_deviation(b_hist, wc, event_date)

    # -------------------------------------------------------------------------
    # UPDATE_2 Step 1 — Archetype vectors
    # -------------------------------------------------------------------------
    arch_vec_a = archetype_vector_with_fallback(a_hist, event_date, wc)
    arch_vec_b = archetype_vector_with_fallback(b_hist, event_date, wc)
    arch_feats: dict = {}
    for i, k in enumerate(ARCHETYPES):
        arch_feats[f"arch_a_{k}"] = float(arch_vec_a[i])
        arch_feats[f"arch_b_{k}"] = float(arch_vec_b[i])
    arch_feats["arch_distance"]   = float(np.linalg.norm(arch_vec_a - arch_vec_b))
    arch_feats["arch_similarity"] = float(np.dot(arch_vec_a, arch_vec_b))

    # Full style stats (used by Steps 2–7)
    stats_a = compute_fighter_style_stats(a_hist, event_date)
    stats_b = compute_fighter_style_stats(b_hist, event_date)

    # -------------------------------------------------------------------------
    # UPDATE_2 Steps 2–7 — Style mismatch features
    # -------------------------------------------------------------------------
    sg_feats   = striker_grappler_mismatch(stats_a, stats_b, arch_vec_a, arch_vec_b)
    pd_feats   = power_durability_features(stats_a, stats_b, arch_vec_a, arch_vec_b, len(a_hist), len(b_hist))
    sub_feats  = submission_chain_features(stats_a, stats_b, arch_vec_a, arch_vec_b, len(a_hist), len(b_hist), n_rounds)
    pp_feats   = pace_pressure_features(stats_a, stats_b, arch_vec_a, arch_vec_b)
    stance_feats = stance_advantage_features(stance_a, stance_b, arch_vec_a, arch_vec_b, wc)
    sh_feats = stance_height_matchup_features(
        a_hist, b_hist, stance_a, stance_b,
        a_bio.get("height_in", np.nan), b_bio.get("height_in", np.nan),
        event_date, bios,
    )
    adapt_feats = adaptability_features(
        a_hist, b_hist, stance_a, stance_b,
        a_bio.get("height_in", np.nan), b_bio.get("height_in", np.nan),
        event_date, bios, stats_a, stats_b,
    )
    upset_feats = upset_fingerprint_features(
        a_hist, b_hist, event_date,
        a_elo_pre, b_elo_pre,
        a_age if not (isinstance(a_age, float) and np.isnan(a_age)) else 29.0,
        b_age if not (isinstance(b_age, float) and np.isnan(b_age)) else 29.0,
        float(a_inactive), float(b_inactive),
        sg_feats, pd_feats, pp_feats, stats_a, stats_b,
    )

    # -------------------------------------------------------------------------
    # Assemble the row
    # -------------------------------------------------------------------------
    row: dict = {
        "event_date": pd.Timestamp(event_date),
        "fighter_a_id": fighter_a_id,
        "fighter_b_id": fighter_b_id,

        # --- Elo ---
        "elo_diff":    a_elo_pre - b_elo_pre,
        "elo_prob_a":  elo_prob_a,

        # --- Legacy raw diffs (carried for XGBoost; SHAP-pruned if below 2.0)
        "slpm_diff":          a_slpm_legacy - b_slpm_legacy,
        "sapm_diff":          a_sapm - b_sapm,
        "strike_net_diff":    (a_slpm_legacy - a_sapm) - (b_slpm_legacy - b_sapm),
        "td_per15_diff":      stats_a["td15"] - stats_b["td15"],
        "td_def_per15_diff":  stats_a["td_def15"] - stats_b["td_def15"],
        "sub_att_per15_diff": stats_a["sub15"] - stats_b["sub15"],
        "kd_per15_diff":      stats_a["kd15"] - stats_b["kd15"],
        "kd_absorbed_per15_diff": a_kd_abs - b_kd_abs,

        # --- Target-zone strike rates ---
        "head_landed_per15_diff":   a_head_l - b_head_l,
        "body_landed_per15_diff":   a_body_l - b_body_l,
        "leg_landed_per15_diff":    a_leg_l  - b_leg_l,
        "head_absorbed_per15_diff": a_head_a - b_head_a,
        "body_absorbed_per15_diff": a_body_a - b_body_a,
        "leg_absorbed_per15_diff":  a_leg_a  - b_leg_a,
        "head_acc_diff":            a_head_acc - b_head_acc,
        "leg_acc_diff":             a_leg_acc  - b_leg_acc,
        # Cross-fighter: how much A targets B's vulnerable zone
        "a_legs_vs_b_chin":  a_leg_l  - b_leg_a,    # A throws legs vs B getting hit in legs
        "a_head_vs_b_chin": a_head_l - b_head_a,   # A throws head vs B getting hit in head
        "b_legs_vs_a_chin":  b_leg_l  - a_leg_a,
        "b_head_vs_a_chin": b_head_l - a_head_a,
        "age_diff":           (a_age - b_age) if not (np.isnan(a_age) or np.isnan(b_age)) else 0.0,
        "stance_mismatch":    int(bool(stance_a) and bool(stance_b) and stance_a != stance_b),

        # --- Career / outcome features ---
        "win_pct_diff":      a_winp - b_winp,
        "finish_rate_diff":  a_finish - b_finish,
        "rounds_exp_diff":   a_rexp - b_rexp,
        "streak_diff":       a_streak - b_streak,
        "days_inactive_diff": a_inactive - b_inactive,
        "n_fights_a":        len(a_hist),
        "n_fights_b":        len(b_hist),

        # --- Bio ---
        "reach_diff": (a_reach - b_reach) if not (np.isnan(a_reach) or np.isnan(b_reach)) else 0.0,

        # --- Weight-class change ---
        "weight_change_a":    a_wchg,
        "weight_change_b":    b_wchg,
        "weight_change_diff": a_wchg - b_wchg,
        "first_at_class_a":   a_first_wc,
        "first_at_class_b":   b_first_wc,
        "natural_wc_dev_a":   a_wc_dev,
        "natural_wc_dev_b":   b_wc_dev,

        # --- Track 2B accuracy + control-time ---
        "strike_acc_diff":  _diff_or_zero(a_sacc, b_sacc),
        "strike_def_diff":  _diff_or_zero(a_sdef, b_sdef),
        "control_pct_diff": _diff_or_zero(a_ctrl, b_ctrl),
        "td_acc_diff":      _diff_or_zero(a_tdt, b_tdt),
        "td_def_acc_diff":  _diff_or_zero(a_tdtd, b_tdtd),

        # Elo absolute (for downstream tools)
        "a_elo_pre": a_elo_pre,
        "b_elo_pre": b_elo_pre,
    }

    # --- UPDATE_2 feature groups ---
    row.update(arch_feats)
    row.update(sg_feats)
    row.update(pd_feats)
    row.update(sub_feats)
    row.update(pp_feats)
    row.update(stance_feats)
    row.update(sh_feats)
    row.update(adapt_feats)
    row.update(upset_feats)

    # --- Optional cluster membership ---
    if cluster_model is not None:
        try:
            from src.models.clustering import aggregate_career_features

            a_career = aggregate_career_features(a_hist, fighter_a_id, a_bio, reference_date=event_date)
            b_career = aggregate_career_features(b_hist, fighter_b_id, b_bio, reference_date=event_date)
            cols = cluster_model.feature_cols
            X = pd.DataFrame(
                [
                    [float(a_career.get(c, 0.0) or 0.0) for c in cols],
                    [float(b_career.get(c, 0.0) or 0.0) for c in cols],
                ],
                columns=cols,
            ).fillna(0.0)
            memb = cluster_model.predict_membership(X.to_numpy(dtype=float))
            for i, p in enumerate(memb[0]):
                row[f"cluster_a_{i}"] = float(p)
            for i, p in enumerate(memb[1]):
                row[f"cluster_b_{i}"] = float(p)
        except Exception:
            pass

    return row


def build_full_matrix(
    fights: pd.DataFrame,
    fighters: pd.DataFrame | None = None,
    *,
    cluster_model=None,
    elo: MMAElo | None = None,
    progress: bool = False,
    limit_to_last_n: int | None = None,
) -> pd.DataFrame:
    """Walk through fights chronologically, building one feature row per fight.

    Critical contract: every feature for a fight on date `d` is built ONLY
    from rows whose event_date < d. Verified by the order of operations
    below: row is computed FIRST, history/Elo updated AFTER.

    `limit_to_last_n` restricts the OUTPUT to the last N fights
    (chronologically) while still replaying the FULL history — every earlier
    fight updates Elo and the per-fighter history caches, it just skips the
    expensive feature-row computation. Temporal correctness is unchanged.
    None (or <= 0) builds the full matrix.
    """
    if elo is None:
        elo = MMAElo()
    bio_lookup = _build_bio_lookup(fighters)

    fights_sorted = fights.sort_values("event_date").reset_index(drop=True).copy()
    fights_sorted["event_date"] = pd.to_datetime(fights_sorted["event_date"])

    history: dict[str, list[dict]] = {}
    rows: list[dict] = []

    # First chronological position whose feature row is actually emitted.
    # Everything before it still replays history + Elo (temporal correctness).
    emit_from = 0
    if limit_to_last_n is not None and limit_to_last_n > 0:
        emit_from = max(0, len(fights_sorted) - limit_to_last_n)

    iterator: Iterable = fights_sorted.itertuples(index=False)
    if progress:
        try:
            from tqdm import tqdm  # type: ignore

            iterator = tqdm(iterator, total=len(fights_sorted))
        except Exception:
            pass

    for pos, fight in enumerate(iterator):
        fight_dict = fight._asdict()
        a_id = fight_dict["fighter_a_id"]
        b_id = fight_dict["fighter_b_id"]
        ev_date = pd.to_datetime(fight_dict["event_date"]).date()
        wc = str(fight_dict.get("weight_class") or "")

        if pos >= emit_from:
            # Detect title fights for n_rounds (5 rounds for title/main events)
            title_col = fight_dict.get("is_title_fight", fight_dict.get("title_fight", 0))
            n_rounds = 5 if int(title_col or 0) else 3

            a_hist_df = pd.DataFrame(history.get(a_id, []))
            b_hist_df = pd.DataFrame(history.get(b_id, []))

            feat = build_feature_row(
                a_id, b_id, ev_date,
                {a_id: a_hist_df, b_id: b_hist_df},
                elo, bio_lookup,
                cluster_model=cluster_model,
                weight_class=wc,
                n_rounds=n_rounds,
            )

            feat.update(
                {
                    "fight_id":        fight_dict.get("fight_id"),
                    "event_id":        fight_dict.get("event_id"),
                    "weight_class":    wc,
                    "fighter_a_name":  fight_dict.get("fighter_a_name"),
                    "fighter_b_name":  fight_dict.get("fighter_b_name"),
                    "method":          fight_dict.get("method_canon", fight_dict.get("method")),
                    "round_finished":  fight_dict.get("round_finished"),
                    "fight_duration_min": fight_dict.get("fight_duration_min"),
                    "fighter_a_won":   int(fight_dict.get("fighter_a_won", 0)),
                }
            )
            rows.append(feat)

        a_pf, b_pf = _fight_to_perfighter_rows(pd.Series(fight_dict))
        history.setdefault(a_id, []).append(a_pf)
        history.setdefault(b_id, []).append(b_pf)

        winner_id = fight_dict.get("winner_id")
        if winner_id and winner_id in {a_id, b_id}:
            loser_id = b_id if winner_id == a_id else a_id
            method = fight_dict.get("method_canon") or fight_dict.get("method") or "Decision"
            elo.update(winner_id, loser_id, method, ev_date)

    matrix = pd.DataFrame(rows)
    leading = [
        "fight_id", "event_id", "event_date", "weight_class",
        "fighter_a_id", "fighter_b_id", "fighter_a_name", "fighter_b_name",
        "method", "round_finished", "fight_duration_min", "fighter_a_won",
    ]
    leading = [c for c in leading if c in matrix.columns]
    rest = [c for c in matrix.columns if c not in leading]
    return matrix[leading + rest]

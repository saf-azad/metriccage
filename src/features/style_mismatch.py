"""Style-mismatch feature pack (UPDATE_2.md Steps 1–7).

All public functions return flat feature dicts ready to merge into the
feature row produced by build_matrix.build_feature_row().

Dependency order:
    style_archetype_classifier (archetypes.py) — prerequisite for all
    → striker_grappler_mismatch
    → power_durability_mismatch        (b_chin_vulnerable →)
    → submission_chain_danger          (td_def_rate shared with sg_mismatch)
    → pace_pressure_mismatch           (b_counter_upset_setup →)
    → stance_advantage
    → upset_fingerprint                (depends on all above)
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.features.archetypes import ARCHETYPES, arch_idx

# ---------------------------------------------------------------------------
# Index shortcuts (safe because ARCHETYPES is never reordered)
# ---------------------------------------------------------------------------

_IDX_POWER_PUNCHER    = arch_idx("power_puncher")
_IDX_MUAY_THAI        = arch_idx("muay_thai")
_IDX_DUTCH_KICKBOXER  = arch_idx("dutch_kickboxer")
_IDX_COUNTER_STRIKER  = arch_idx("counter_striker")
_IDX_WRESTLE_STRIKER  = arch_idx("wrestle_striker")
_IDX_GRAPPLING_FIRST  = arch_idx("grappling_first")
_IDX_PRESSURE_STRIKER = arch_idx("pressure_striker")
_IDX_DECISION_FIGHTER = arch_idx("decision_fighter")

# ---------------------------------------------------------------------------
# Step 2 — Striker vs. Grappler Mismatch
# ---------------------------------------------------------------------------

def grappler_path_score(
    td_per15: float,
    td_def_rate_opp: float,
    sub_att_per15: float,
    arch_grappling_first: float,
    arch_wrestle_striker: float,
) -> float:
    td_def_clamped = float(np.clip(td_def_rate_opp, 0.0, 0.95))
    lambda_td = (td_per15 / 15.0) * (1.0 - td_def_clamped)
    p_td_round = 1.0 - np.exp(-lambda_td * 5.0)
    ground_danger = (
        0.55 * arch_grappling_first
        + 0.30 * arch_wrestle_striker
        + 0.15 * float(np.clip(sub_att_per15 / 2.0, 0, 1))
    )
    return float(p_td_round * ground_danger)


def striker_path_score(
    slpm: float,
    td_def_rate: float,
    finish_rate: float,
    arch_muay_thai: float,
    arch_dutch_kickboxer: float,
    arch_counter_striker: float,
) -> float:
    standing_control = float(np.clip(td_def_rate, 0.0, 1.0))
    striking_threat = float(np.clip(slpm / 9.6, 0, 1))
    arch_rest = float(np.clip(1.0 - arch_muay_thai - arch_dutch_kickboxer - arch_counter_striker, 0, 1))
    archetype_multiplier = (
        1.25 * arch_muay_thai
        + 1.22 * arch_dutch_kickboxer
        + 1.10 * arch_counter_striker
        + 0.60 * arch_rest
    )
    striking_danger = float(np.clip(striking_threat * archetype_multiplier, 0, 1))
    return float(standing_control * 0.5 + striking_danger * 0.3 + finish_rate * 0.2)


def striker_grappler_mismatch(
    stats_a: dict,
    stats_b: dict,
    arch_vec_a: np.ndarray,
    arch_vec_b: np.ndarray,
) -> dict:
    """6 features capturing the striker-grappler style interaction."""
    td_def_rate_a = float(np.clip(stats_a["td_def15"] / 5.5, 0, 0.97))
    td_def_rate_b = float(np.clip(stats_b["td_def15"] / 5.5, 0, 0.97))

    gps_a = grappler_path_score(
        stats_a["td15"], td_def_rate_b, stats_a["sub15"],
        arch_vec_a[_IDX_GRAPPLING_FIRST], arch_vec_a[_IDX_WRESTLE_STRIKER],
    )
    sps_b = striker_path_score(
        stats_b["slpm"], td_def_rate_b, stats_b["finish_rate"],
        arch_vec_b[_IDX_MUAY_THAI], arch_vec_b[_IDX_DUTCH_KICKBOXER], arch_vec_b[_IDX_COUNTER_STRIKER],
    )
    gps_b = grappler_path_score(
        stats_b["td15"], td_def_rate_a, stats_b["sub15"],
        arch_vec_b[_IDX_GRAPPLING_FIRST], arch_vec_b[_IDX_WRESTLE_STRIKER],
    )
    sps_a = striker_path_score(
        stats_a["slpm"], td_def_rate_a, stats_a["finish_rate"],
        arch_vec_a[_IDX_MUAY_THAI], arch_vec_a[_IDX_DUTCH_KICKBOXER], arch_vec_a[_IDX_COUNTER_STRIKER],
    )

    td_dominance = (
        (stats_a["td15"] * (1.0 - td_def_rate_b)) -
        (stats_b["td15"] * (1.0 - td_def_rate_a))
    )

    return {
        "grappler_path_a":   gps_a,
        "grappler_path_b":   gps_b,
        "striker_path_a":    sps_a,
        "striker_path_b":    sps_b,
        "sg_mismatch_net":   (gps_a - gps_b) + (sps_a - sps_b),
        "td_dominance_diff": td_dominance,
    }


# ---------------------------------------------------------------------------
# Step 3 — Power vs. Durability Mismatch
# ---------------------------------------------------------------------------

_ARCHETYPE_P_BAR = {
    "power_puncher":    0.022,
    "muay_thai":        0.025,
    "dutch_kickboxer":  0.020,
    "counter_striker":  0.022,
    "wrestle_striker":  0.016,
    "grappling_first":  0.008,
    "pressure_striker": 0.010,
    "decision_fighter": 0.007,
}
_P_BAR_VEC = np.array([_ARCHETYPE_P_BAR[k] for k in ARCHETYPES])


def ko_danger_score(
    slpm: float,
    kd15: float,
    finish_rate: float,
    arch_vec: np.ndarray,
) -> float:
    p_bar = float(np.dot(arch_vec, _P_BAR_VEC))
    N = slpm * 5.0
    p_ko_round = 1.0 - np.exp(-N * p_bar)
    kd_bonus = float(np.clip(kd15 / 1.5, 0, 1))
    fr_component = float(np.clip(finish_rate, 0, 1))
    score = 0.50 * p_ko_round + 0.30 * kd_bonus + 0.20 * fr_component
    return float(np.clip(score, 0, 1))


def chin_durability_score(
    kd_abs15: float,
    sapm: float,
    ko_loss_rate: float,
    n_ko_losses: int,
    n_kd_absorbed_career: int,
    n_total_fights: int,
) -> float:
    kd_abs_norm = float(np.clip(1.0 - kd_abs15 / 0.8, 0, 1))
    sapm_norm   = float(np.clip(1.0 - sapm / 9.6, 0, 1))
    ko_fragility = float(np.clip(ko_loss_rate, 0, 1))
    n_trauma = n_ko_losses * 3 + n_kd_absorbed_career * 1.5 + n_total_fights * 0.2
    vulnerability = float(np.exp(0.025 * n_trauma))
    cte_penalty = float(np.clip(1.0 - (vulnerability - 1.0) / 3.0, 0, 1))
    score = 0.35 * kd_abs_norm + 0.25 * sapm_norm + 0.25 * (1.0 - ko_fragility) + 0.15 * cte_penalty
    return float(np.clip(score, 0, 1))


def power_durability_features(
    stats_a: dict,
    stats_b: dict,
    arch_vec_a: np.ndarray,
    arch_vec_b: np.ndarray,
    n_fights_a: int,
    n_fights_b: int,
) -> dict:
    ko_danger_a = ko_danger_score(stats_a["slpm"], stats_a["kd15"], stats_a["finish_rate"], arch_vec_a)
    ko_danger_b = ko_danger_score(stats_b["slpm"], stats_b["kd15"], stats_b["finish_rate"], arch_vec_b)
    chin_a = chin_durability_score(
        stats_a["kd_abs15"], stats_a["sapm"], stats_a["ko_loss_rate"],
        stats_a["n_ko_losses"], stats_a["n_kd_absorbed_career"], n_fights_a,
    )
    chin_b = chin_durability_score(
        stats_b["kd_abs15"], stats_b["sapm"], stats_b["ko_loss_rate"],
        stats_b["n_ko_losses"], stats_b["n_kd_absorbed_career"], n_fights_b,
    )
    a_power_vs_b_chin = ko_danger_a * (1.0 - chin_b)
    b_power_vs_a_chin = ko_danger_b * (1.0 - chin_a)
    return {
        "ko_danger_a":             ko_danger_a,
        "ko_danger_b":             ko_danger_b,
        "chin_durability_a":       chin_a,
        "chin_durability_b":       chin_b,
        "ko_threat_net":           ko_danger_a - ko_danger_b,
        "ko_danger_differential":  a_power_vs_b_chin - b_power_vs_a_chin,
        "b_chin_vulnerable":       float(chin_b < 0.35),
    }


# ---------------------------------------------------------------------------
# Step 4 — Submission Chain Danger (UPDATE_2.md position-conditioned approach)
# ---------------------------------------------------------------------------

SUB_PROB_BY_POSITION = {
    "back_ctrl":    0.38,
    "mount":        0.22,
    "side_ctrl":    0.14,
    "half_guard":   0.12,
    "guard_top":    0.08,
    "guard_bottom": 0.19,
    "clinch":       0.08,
    "standing":     0.01,
}

ROUND_FATIGUE_SUB_MULTIPLIER = {1: 1.00, 2: 1.05, 3: 1.12, 4: 1.18, 5: 1.25}


def _position_distribution(arch_vec: np.ndarray) -> dict:
    """Estimate position distribution from archetype vector.

    grappling_first score drives toward dominant positions (back, mount).
    Low grappling scores → mostly standing / guard_top.
    guard_bottom is only populated for fighters with strong grappling_first.
    """
    gf = float(arch_vec[_IDX_GRAPPLING_FIRST])
    ws = float(arch_vec[_IDX_WRESTLE_STRIKER])
    grappling_score = gf + 0.5 * ws

    t = float(np.clip(grappling_score / 1.5, 0, 1))

    base_dist = {
        "back_ctrl":    0.05 + 0.35 * t,
        "mount":        0.08 + 0.17 * t,
        "side_ctrl":    0.15 + 0.10 * t,
        "half_guard":   0.10 + 0.05 * t,
        "guard_top":    0.15 - 0.10 * t,
        "clinch":       0.12 - 0.05 * t,
        "standing":     0.35 - 0.55 * t,
    }
    guard_bottom_eligible = gf > 0.30
    base_dist["guard_bottom"] = gf * 0.15 if guard_bottom_eligible else 0.0

    total = sum(base_dist.values())
    return {k: v / max(total, 1e-9) for k, v in base_dist.items()}


def sub_danger_score(
    position_dist: dict,
    arch_vec: np.ndarray,
    n_rounds: int = 3,
) -> float:
    base = sum(SUB_PROB_BY_POSITION.get(pos, 0.0) * pct for pos, pct in position_dist.items())
    chain_weight = float(arch_vec[_IDX_GRAPPLING_FIRST])
    archetype_factor = 1.0 + 0.40 * chain_weight
    fatigue_factor = ROUND_FATIGUE_SUB_MULTIPLIER.get(n_rounds, 1.0)
    return float(np.clip(base * archetype_factor * fatigue_factor, 0, 0.45))


def submission_chain_features(
    stats_a: dict,
    stats_b: dict,
    arch_vec_a: np.ndarray,
    arch_vec_b: np.ndarray,
    n_fights_a: int,
    n_fights_b: int,
    n_rounds: int = 3,
) -> dict:
    """5 submission-chain features replacing sub_att_per15_diff."""
    td_def_rate_a = float(np.clip(stats_a["td_def15"] / 5.5, 0, 0.97))
    td_def_rate_b = float(np.clip(stats_b["td_def15"] / 5.5, 0, 0.97))

    pos_a = _position_distribution(arch_vec_a)
    pos_b = _position_distribution(arch_vec_b)

    # Gate guard_bottom by grappling score as per UPDATE_2.md
    if arch_vec_a[_IDX_GRAPPLING_FIRST] <= 0.30:
        pos_a["guard_bottom"] = 0.0
    if arch_vec_b[_IDX_GRAPPLING_FIRST] <= 0.30:
        pos_b["guard_bottom"] = 0.0

    # Renormalise after guard_bottom gate
    for d in (pos_a, pos_b):
        t = sum(d.values())
        if t > 1e-9:
            for k in d:
                d[k] /= t

    raw_a = sub_danger_score(pos_a, arch_vec_a, n_rounds)
    raw_b = sub_danger_score(pos_b, arch_vec_b, n_rounds)

    # Incorporate takedown gateway: P(ground) modulated by opponent TD defence
    lambda_a = (stats_a["td15"] / 15.0) * (1.0 - td_def_rate_b)
    p_td_a = float(1.0 - (1.0 - (1.0 - np.exp(-lambda_a * 5.0))) ** n_rounds)
    lambda_b = (stats_b["td15"] / 15.0) * (1.0 - td_def_rate_a)
    p_td_b = float(1.0 - (1.0 - (1.0 - np.exp(-lambda_b * 5.0))) ** n_rounds)

    sub_danger_a = float(np.clip(raw_a * p_td_a, 0, 0.45))
    sub_danger_b = float(np.clip(raw_b * p_td_b, 0, 0.45))

    # Sparse fighter regression toward 0.12 population mean
    POPULATION_MEAN = 0.12
    if n_fights_a < 5:
        shrink = float(n_fights_a) / 5.0
        sub_danger_a = shrink * sub_danger_a + (1.0 - shrink) * POPULATION_MEAN
    if n_fights_b < 5:
        shrink = float(n_fights_b) / 5.0
        sub_danger_b = shrink * sub_danger_b + (1.0 - shrink) * POPULATION_MEAN

    return {
        "sub_danger_a":       sub_danger_a,
        "sub_danger_b":       sub_danger_b,
        "sub_danger_diff":    sub_danger_a - sub_danger_b,
        "sub_danger_combined": sub_danger_a + sub_danger_b,
        "sub_att_rate_diff":  stats_a["sub15"] - stats_b["sub15"],
    }


# ---------------------------------------------------------------------------
# Step 5 — Pace and Pressure Mismatch
# ---------------------------------------------------------------------------

def _pace_score(slpm: float, sapm: float) -> float:
    return float(slpm + sapm)


def _counter_efficiency(finish_rate: float, slpm: float) -> float:
    if slpm < 0.5:
        return 0.0
    return float(np.clip(finish_rate / slpm, 0, 0.50))


def pace_pressure_features(
    stats_a: dict,
    stats_b: dict,
    arch_vec_a: np.ndarray,
    arch_vec_b: np.ndarray,
) -> dict:
    """8 pace/pressure features replacing slpm_diff and sapm_diff."""
    pace_a = _pace_score(stats_a["slpm"], stats_a["sapm"])
    pace_b = _pace_score(stats_b["slpm"], stats_b["sapm"])
    ce_a = _counter_efficiency(stats_a["finish_rate"], stats_a["slpm"])
    ce_b = _counter_efficiency(stats_b["finish_rate"], stats_b["slpm"])

    pressure_index_a = (
        1.4 * float(arch_vec_a[_IDX_PRESSURE_STRIKER])
        + 1.2 * float(arch_vec_a[_IDX_DUTCH_KICKBOXER])
        + 0.9 * float(arch_vec_a[_IDX_MUAY_THAI])
        - 0.8 * float(arch_vec_a[_IDX_COUNTER_STRIKER])
        - 0.5 * float(arch_vec_a[_IDX_DECISION_FIGHTER])
    )
    pressure_index_b = (
        1.4 * float(arch_vec_b[_IDX_PRESSURE_STRIKER])
        + 1.2 * float(arch_vec_b[_IDX_DUTCH_KICKBOXER])
        + 0.9 * float(arch_vec_b[_IDX_MUAY_THAI])
        - 0.8 * float(arch_vec_b[_IDX_COUNTER_STRIKER])
        - 0.5 * float(arch_vec_b[_IDX_DECISION_FIGHTER])
    )

    counter_threat_b_vs_a = (
        float(arch_vec_b[_IDX_COUNTER_STRIKER])
        * (1.0 + float(np.clip(pressure_index_a, 0, None)))
        * ce_b
    )
    counter_threat_a_vs_b = (
        float(arch_vec_a[_IDX_COUNTER_STRIKER])
        * (1.0 + float(np.clip(pressure_index_b, 0, None)))
        * ce_a
    )

    gas_out_risk_a = float(np.clip(stats_a["sapm"] / max(stats_a["slpm"], 0.5), 0, 2))
    gas_out_risk_b = float(np.clip(stats_b["sapm"] / max(stats_b["slpm"], 0.5), 0, 2))

    b_counter_upset_setup = int(
        pressure_index_a > 0.4
        and float(arch_vec_b[_IDX_COUNTER_STRIKER]) > 0.5
        and stats_a["td15"] < 2.0
        and ce_b > 0.12
    )

    return {
        "pace_mismatch_diff":      pace_a - pace_b,
        "counter_efficiency_diff": ce_a - ce_b,
        "pressure_index_a":        pressure_index_a,
        "pressure_index_b":        pressure_index_b,
        "counter_threat_b_vs_a":   counter_threat_b_vs_a,
        "counter_threat_a_vs_b":   counter_threat_a_vs_b,
        "gas_out_risk_diff":        gas_out_risk_a - gas_out_risk_b,
        "b_counter_upset_setup":   b_counter_upset_setup,
    }


# ---------------------------------------------------------------------------
# Step 6 — Stance Geometry Advantage
# ---------------------------------------------------------------------------

_ARCHETYPE_STANCE_MULTIPLIERS = {
    "power_puncher":    1.30,
    "muay_thai":        1.35,
    "dutch_kickboxer":  1.40,
    "counter_striker":  1.20,
    "wrestle_striker":  0.85,
    "grappling_first":  0.50,
    "pressure_striker": 1.10,
    "decision_fighter": 0.70,
}
_STANCE_MULT_VEC = np.array([_ARCHETYPE_STANCE_MULTIPLIERS[k] for k in ARCHETYPES])

DIVISION_SOUTHPAW_FRACTION = {
    "Lightweight":            0.28,
    "Welterweight":           0.27,
    "Middleweight":           0.29,
    "Light Heavyweight":      0.31,
    "Heavyweight":            0.26,
    "Featherweight":          0.30,
    "Bantamweight":           0.32,
    "Flyweight":              0.29,
    "Women's Strawweight":    0.22,
    "Women's Flyweight":      0.20,
    "Women's Bantamweight":   0.18,
    "_global":                0.28,
}


def stance_advantage_features(
    stance_a: str,
    stance_b: str,
    arch_vec_a: np.ndarray,
    arch_vec_b: np.ndarray,
    weight_class: str,
) -> dict:
    """Replace binary stance_mismatch with 4 calibrated stance features."""
    sa = (stance_a or "").lower().strip()
    sb = (stance_b or "").lower().strip()

    if sa == "southpaw" and sb == "orthodox":
        advantage_a, open_stance = 1.0, 1
    elif sa == "orthodox" and sb == "southpaw":
        advantage_a, open_stance = -1.0, 1
    else:
        advantage_a, open_stance = 0.0, 0

    if advantage_a == 0.0:
        return {
            "stance_advantage_a":     0.0,
            "stance_score_amplified": 0.0,
            "stance_win_prob_uplift": 0.0,
            "open_stance":            open_stance,
        }

    if advantage_a > 0:
        mult = float(np.dot(arch_vec_a, _STANCE_MULT_VEC))
    else:
        mult = float(np.dot(arch_vec_b, _STANCE_MULT_VEC))

    sp_frac = DIVISION_SOUTHPAW_FRACTION.get(weight_class, DIVISION_SOUTHPAW_FRACTION["_global"])
    rarity = float(max(0, 0.30 - sp_frac) / 0.30)
    rarity_modifier = 1.0 + 0.25 * rarity

    amp_score = advantage_a * mult * rarity_modifier
    win_prob_uplift = float(0.065 * amp_score)

    return {
        "stance_advantage_a":     advantage_a,
        "stance_score_amplified": amp_score,
        "stance_win_prob_uplift": win_prob_uplift,
        "open_stance":            open_stance,
    }


# ---------------------------------------------------------------------------
# Step 7 — Upset Fingerprint Features
# ---------------------------------------------------------------------------

def ascending_trajectory_score(
    history: pd.DataFrame,
    reference_date: date,
    half_life_days: float = 200.0,
    n_recent: int = 5,
) -> float:
    if len(history) == 0:
        return 0.0
    from src.features.core_features import _decay_weights
    recent = history.sort_values("event_date").tail(n_recent).copy()
    w = _decay_weights(recent, reference_date, half_life_days)
    wins = recent["winner"].astype(bool).to_numpy(dtype=float)
    results = wins * 2 - 1
    opp_quality = np.zeros(len(recent))
    if "opp_n_fights" in recent.columns:
        opp_quality = (recent["opp_n_fights"].to_numpy(dtype=float) - 10.0) / 10.0
    weighted = np.dot(w, results * (1.0 + 0.3 * np.clip(opp_quality, -2, 2)))
    return float(np.clip(weighted / max(w.sum(), 1e-6), -2.0, 2.0))


def elo_form_divergence(
    elo_pre: float,
    history: pd.DataFrame,
    reference_date: date,
    division_median_elo: float = 1500.0,
    n_recent: int = 3,
) -> float:
    if len(history) == 0:
        return 0.0
    from src.features.core_features import _decay_weights
    recent = history.sort_values("event_date").tail(n_recent).copy()
    if len(recent) == 0:
        return 0.0
    w = _decay_weights(recent, reference_date, half_life_days=120)
    W = float(w.sum())
    if W < 1e-9:
        return 0.0
    recent_win_rate = float(np.dot(w, recent["winner"].astype(bool).to_numpy(dtype=float)) / W)
    elo_percentile = float(np.clip((elo_pre - division_median_elo) / 300.0, -1, 1))
    return float(elo_percentile - (recent_win_rate - 0.5) / 0.25)


def age_curve_position(age: float) -> float:
    if age < 26:
        return 0.85 + 0.015 * (age - 20)
    elif age <= 31:
        return 1.00
    elif age <= 36:
        return 1.00 - 0.020 * (age - 31)
    else:
        return float(np.clip(0.90 - 0.035 * (age - 36), 0.5, 1.0))


def rust_penalty(days_inactive: float) -> float:
    d = float(max(0, days_inactive))
    return 0.60 * np.exp(-0.0009 * d) + 0.40 * np.exp(-0.0050 * d)


def first_round_danger(
    kd15: float,
    ko_danger: float,
    finish_rate: float,
    rounds_exp: float,
) -> float:
    early_finish_proxy = float(np.clip(kd15 / 0.8, 0, 1))
    experience_factor = float(np.clip(1.0 - rounds_exp / 60.0, 0, 1))
    return float(0.5 * early_finish_proxy + 0.3 * ko_danger + 0.2 * experience_factor)


def upset_fingerprint_features(
    history_a: pd.DataFrame,
    history_b: pd.DataFrame,
    reference_date: date,
    elo_pre_a: float,
    elo_pre_b: float,
    age_a: float,
    age_b: float,
    days_inactive_a: float,
    days_inactive_b: float,
    sg_feats: dict,
    pd_feats: dict,
    pp_feats: dict,
    stats_a: dict,
    stats_b: dict,
) -> dict:
    """Full upset fingerprint combining trajectory, form, age, rust, and style signals."""
    traj_a = ascending_trajectory_score(history_a, reference_date)
    traj_b = ascending_trajectory_score(history_b, reference_date)
    div_a = elo_form_divergence(elo_pre_a, history_a, reference_date)
    div_b = elo_form_divergence(elo_pre_b, history_b, reference_date)

    f_a = age_curve_position(age_a) if not (np.isnan(age_a) if isinstance(age_a, float) else False) else 1.0
    f_b = age_curve_position(age_b) if not (np.isnan(age_b) if isinstance(age_b, float) else False) else 1.0
    age_curve_diff = float(f_a - f_b)
    prime_mismatch = int(age_a > 34 and 26 <= age_b <= 31)

    rust_a = rust_penalty(days_inactive_a)
    rust_b = rust_penalty(days_inactive_b)
    rust_diff = float(rust_a - rust_b)
    favourite_rusty = int(days_inactive_a > 365 and days_inactive_b < 90)

    ko_danger_a = pd_feats.get("ko_danger_a", 0.0)
    ko_danger_b = pd_feats.get("ko_danger_b", 0.0)
    fr1_a = first_round_danger(stats_a["kd15"], ko_danger_a, stats_a["finish_rate"], stats_a["rounds_exp"])
    fr1_b = first_round_danger(stats_b["kd15"], ko_danger_b, stats_b["finish_rate"], stats_b["rounds_exp"])

    traj_diff = float(traj_a - traj_b)
    sg_net = sg_feats.get("sg_mismatch_net", 0.0)
    ko_diff = pd_feats.get("ko_danger_differential", 0.0)
    b_counter = float(pp_feats.get("b_counter_upset_setup", 0))
    b_chin = float(pd_feats.get("b_chin_vulnerable", 0))

    a_upset_risk = (
        0.25 * float(-sg_net)
        + 0.20 * float(-ko_diff)
        + 0.15 * float(-age_curve_diff)
        + 0.15 * float(-rust_diff)
        + 0.10 * float(-traj_diff)
        + 0.10 * float(div_a)
        + 0.05 * float(b_counter + b_chin + favourite_rusty + prime_mismatch)
    )

    return {
        "trajectory_diff":       traj_diff,
        "elo_form_divergence_a": div_a,
        "elo_form_divergence_b": div_b,
        "age_curve_a":           f_a,
        "age_curve_b":           f_b,
        "age_curve_diff":        age_curve_diff,
        "prime_mismatch":        prime_mismatch,
        "rust_a":                rust_a,
        "rust_b":                rust_b,
        "rust_diff":             rust_diff,
        "favourite_rusty":       favourite_rusty,
        "fr1_danger_diff":       fr1_a - fr1_b,
        "a_upset_risk_score":    float(np.clip(a_upset_risk, -2, 2)),
    }

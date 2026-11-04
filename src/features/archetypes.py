"""Fighter style archetype classifier.

8-component soft archetype vector derived from division-normalised z-scores of
career stats. Every downstream style-mismatch feature depends on this module.

Import ARCHETYPES and compute_archetype_vector from here only — never redefine
the list inline, as index-based access is shared across style_mismatch.py.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Canonical archetype list — NEVER reorder; downstream code uses index access.
# ---------------------------------------------------------------------------

ARCHETYPES = [
    "power_puncher",    # 0  explosive KO threat, lower volume; win by one-shot damage
    "muay_thai",        # 1  high slpm, high finish rate, moderate TD; win by output volume
    "dutch_kickboxer",  # 2  very high slpm + sapm (volume brawler); wins by accumulation
    "counter_striker",  # 3  reactive, timing-based, efficient; wins by precision
    "wrestle_striker",  # 4  high TD, moderate slpm, low sub; wins by top position + GnP
    "grappling_first",  # 5  TD-oriented + submission chain; wins by ground control / sub
    "pressure_striker", # 6  forward pressure, high output; wins by relentless volume
    "decision_fighter", # 7  points-based, distance management; wins by accumulated scoring
]

# ---------------------------------------------------------------------------
# Division normalisation constants (median, std) — fit on training set only.
# Update via `scripts/compute_division_norms.py` after each full retrain.
# Columns: slpm, sapm, td15, sub15, kd15, finish_rate
# ---------------------------------------------------------------------------

DIVISION_NORMS: dict[str, dict[str, tuple[float, float]]] = {
    "Lightweight": dict(
        slpm=(4.9, 2.1), sapm=(4.8, 2.0), td15=(1.9, 1.9),
        sub15=(0.7, 1.3), kd15=(0.22, 0.38), finish_rate=(0.48, 0.30),
    ),
    "Welterweight": dict(
        slpm=(4.7, 2.0), sapm=(4.6, 1.9), td15=(2.0, 2.0),
        sub15=(0.6, 1.2), kd15=(0.19, 0.34), finish_rate=(0.45, 0.29),
    ),
    "Middleweight": dict(
        slpm=(4.8, 2.1), sapm=(4.7, 2.0), td15=(1.7, 1.8),
        sub15=(0.6, 1.2), kd15=(0.23, 0.40), finish_rate=(0.52, 0.30),
    ),
    "Light Heavyweight": dict(
        slpm=(4.6, 2.2), sapm=(4.5, 2.1), td15=(1.6, 1.7),
        sub15=(0.5, 1.1), kd15=(0.28, 0.48), finish_rate=(0.58, 0.30),
    ),
    "Heavyweight": dict(
        slpm=(4.4, 2.3), sapm=(4.3, 2.2), td15=(1.4, 1.6),
        sub15=(0.4, 0.9), kd15=(0.35, 0.58), finish_rate=(0.68, 0.28),
    ),
    "Featherweight": dict(
        slpm=(5.0, 2.1), sapm=(4.9, 2.0), td15=(1.8, 1.9),
        sub15=(0.7, 1.3), kd15=(0.20, 0.36), finish_rate=(0.48, 0.30),
    ),
    "Bantamweight": dict(
        slpm=(5.1, 2.2), sapm=(5.0, 2.1), td15=(1.7, 1.8),
        sub15=(0.7, 1.3), kd15=(0.18, 0.34), finish_rate=(0.46, 0.29),
    ),
    "Flyweight": dict(
        slpm=(5.0, 2.1), sapm=(4.9, 2.0), td15=(1.9, 1.9),
        sub15=(0.8, 1.4), kd15=(0.15, 0.30), finish_rate=(0.42, 0.28),
    ),
    "Women's Strawweight": dict(
        slpm=(4.5, 2.0), sapm=(4.4, 1.9), td15=(1.6, 1.7),
        sub15=(0.7, 1.3), kd15=(0.12, 0.26), finish_rate=(0.40, 0.28),
    ),
    "Women's Flyweight": dict(
        slpm=(4.4, 2.0), sapm=(4.3, 1.9), td15=(1.5, 1.7),
        sub15=(0.6, 1.2), kd15=(0.10, 0.24), finish_rate=(0.38, 0.27),
    ),
    "Women's Bantamweight": dict(
        slpm=(4.3, 2.0), sapm=(4.2, 1.9), td15=(1.5, 1.7),
        sub15=(0.8, 1.4), kd15=(0.12, 0.26), finish_rate=(0.42, 0.28),
    ),
    "_global": dict(
        slpm=(4.8, 2.2), sapm=(4.8, 2.1), td15=(1.8, 1.9),
        sub15=(0.6, 1.2), kd15=(0.22, 0.38), finish_rate=(0.48, 0.30),
    ),
}

# ---------------------------------------------------------------------------
# Archetype weight matrices: each row = one archetype's linear combination of
# z-scored stats [slpm, sapm, td15, sub15, kd15, finish_rate].
# Signs derived from strategy-mechanics/striking-outcome-probabilities.md §5.1.
# ---------------------------------------------------------------------------

ARCHETYPE_WEIGHTS: dict[str, list[float]] = {
    #                      slpm  sapm   td15  sub15  kd15   fr
    "power_puncher":   [ 0.3, -0.4,  -0.5,  -0.5,  1.5,  0.8],
    "muay_thai":       [ 0.9, -0.2,   0.1,  -0.3,  0.4,  0.7],
    "dutch_kickboxer": [ 1.1,  0.8,  -0.2,  -0.6,  0.5,  0.4],
    "counter_striker": [-0.5, -0.9,  -0.4,  -0.4,  0.3,  0.9],
    "wrestle_striker": [ 0.4, -0.3,   1.2,  -0.2, -0.1,  0.3],
    "grappling_first": [-0.4, -0.4,   1.0,   1.4, -0.3,  0.5],
    "pressure_striker":[ 1.2,  0.9,  -0.3,  -0.4, -0.1, -0.2],
    "decision_fighter":[ 0.2, -0.5,  -0.1,  -0.5, -0.8, -1.2],
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-float(np.clip(x, -20, 20))))


def _z_score(val: float, median: float, std: float) -> float:
    if std < 1e-6:
        return 0.0
    return float((val - median) / std)


def _safe_mins(history: pd.DataFrame) -> np.ndarray:
    for col in ("fight_duration_minutes", "fight_duration_min"):
        if col in history.columns:
            m = history[col].to_numpy(dtype=float)
            return np.where(m > 0.1, m, 15.0)
    if "fight_duration_seconds" in history.columns:
        return np.clip(history["fight_duration_seconds"].to_numpy(dtype=float) / 60.0, 0.5, None)
    return np.full(len(history), 15.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_fighter_style_stats(
    history: pd.DataFrame,
    reference_date: date,
    half_life_days: float = 365.0,
) -> dict:
    """Compute absolute (un-diffed) style stats for one fighter.

    Returns a dict with keys: slpm, sapm, td15, sub15, kd15, kd_abs15,
    finish_rate, ko_loss_rate, n_ko_losses, n_kd_absorbed_career,
    rounds_exp, td_def15.

    All rate features use time-decayed weighted averages so that recent
    fights dominate. Missing optional columns (knockdowns, opp_knockdowns)
    are treated as zero rather than crashing.
    """
    if len(history) == 0:
        return _zero_style_stats()

    from src.features.core_features import _decay_weights  # local import avoids circular

    w = _decay_weights(history, reference_date, half_life_days)
    W = float(w.sum())
    if W < 1e-9:
        return _zero_style_stats()

    mins = _safe_mins(history)
    mins = np.clip(mins, 0.5, None)

    def _wrate(col: str, *, per: float = 1.0) -> float:
        if col not in history.columns:
            return 0.0
        vals = history[col].fillna(0).to_numpy(dtype=float)
        denom = float((w * mins).sum())
        if denom < 1e-9:
            return 0.0
        return float((w * vals).sum()) / denom * per

    slpm      = _wrate("sig_strikes_landed")
    sapm      = _wrate("opp_sig_strikes_landed")
    td15      = _wrate("takedowns_landed", per=15.0)
    sub15     = _wrate("sub_attempts", per=15.0)
    kd15      = _wrate("knockdowns", per=15.0)
    kd_abs15  = _wrate("opp_knockdowns", per=15.0)
    td_def15  = _wrate("opp_takedowns_landed", per=15.0)

    wins = history["winner"].astype(bool).to_numpy(dtype=float) if "winner" in history.columns else np.zeros(len(history))
    methods = history["method"].fillna("").astype(str).to_numpy() if "method" in history.columns else np.full(len(history), "")
    is_ko_finish = np.array(
        [("KO/TKO" in m or "TKO" in m or " KO" in m) and "Decision" not in m for m in methods],
        dtype=float,
    )
    is_sub_finish = np.array(
        [("Submission" in m or "SUB" in m) and "Decision" not in m for m in methods],
        dtype=float,
    )
    is_finish = np.clip(is_ko_finish + is_sub_finish, 0, 1)
    finish_rate = float(np.dot(w, wins * is_finish)) / W

    n_losses = int((wins < 0.5).sum())
    ko_losses = is_ko_finish * (1.0 - wins)
    n_ko_losses = int(ko_losses.sum())
    ko_loss_rate = float(n_ko_losses) / max(1, n_losses)

    kd_abs_col = history["opp_knockdowns"].fillna(0).to_numpy(dtype=float) if "opp_knockdowns" in history.columns else np.zeros(len(history))
    n_kd_absorbed_career = int(kd_abs_col.sum())

    if "round_finished" in history.columns:
        rounds_exp = float(history["round_finished"].fillna(0).sum())
    else:
        rounds_exp = float(len(history) * 2.5)

    return dict(
        slpm=slpm, sapm=sapm, td15=td15, sub15=sub15, kd15=kd15, kd_abs15=kd_abs15,
        finish_rate=finish_rate, ko_loss_rate=ko_loss_rate, n_ko_losses=n_ko_losses,
        n_kd_absorbed_career=n_kd_absorbed_career, rounds_exp=rounds_exp, td_def15=td_def15,
    )


def _zero_style_stats() -> dict:
    return dict(
        slpm=0.0, sapm=0.0, td15=0.0, sub15=0.0, kd15=0.0, kd_abs15=0.0,
        finish_rate=0.0, ko_loss_rate=0.0, n_ko_losses=0, n_kd_absorbed_career=0,
        rounds_exp=0.0, td_def15=0.0,
    )


def normalise_stats(stats: dict, weight_class: str) -> dict:
    """Division-normalise style stats to z-scores. Clamps at ±4σ."""
    norms = DIVISION_NORMS.get(weight_class, DIVISION_NORMS["_global"])
    result = {}
    for k in ("slpm", "sapm", "td15", "sub15", "kd15", "finish_rate"):
        if k in stats and k in norms:
            result[k] = float(np.clip(_z_score(stats[k], norms[k][0], norms[k][1]), -4, 4))
        else:
            result[k] = 0.0
    return result


def compute_archetype_vector(z_stats: dict) -> np.ndarray:
    """Return 8-element soft archetype vector (independent sigmoid scores in [0,1]).

    Values do NOT sum to 1 — each archetype is scored independently.
    High score = strong presence of that archetype trait.
    """
    z = np.array([
        z_stats.get("slpm", 0.0),
        z_stats.get("sapm", 0.0),
        z_stats.get("td15", 0.0),
        z_stats.get("sub15", 0.0),
        z_stats.get("kd15", 0.0),
        z_stats.get("finish_rate", 0.0),
    ])
    return np.array([_sigmoid(float(np.dot(np.array(ARCHETYPE_WEIGHTS[k]), z))) for k in ARCHETYPES])


def archetype_vector_with_fallback(
    history: pd.DataFrame,
    reference_date: date,
    weight_class: str,
    min_fights: int = 3,
) -> np.ndarray:
    """Archetype vector with sparse-fighter shrinkage.

    Fighters with < min_fights return the division-average vector (all 0.5).
    Fighters with 3–5 fights are shrunk 50% toward the division mean per
    UPDATE_2.md sparse-fighter correction.
    """
    n = len(history)
    if n < min_fights:
        return np.full(8, 0.5)
    stats = compute_fighter_style_stats(history, reference_date)
    z = normalise_stats(stats, weight_class)
    vec = compute_archetype_vector(z)
    if n < 5:
        shrink = float(n) / 5.0
        vec = shrink * vec + (1.0 - shrink) * np.full(8, 0.5)
    return vec


def arch_idx(name: str) -> int:
    """Return the index of an archetype name in ARCHETYPES."""
    return ARCHETYPES.index(name)

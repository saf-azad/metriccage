"""Tier-1 feature builders.

Each function takes a fighter's fight history (DataFrame, restricted to fights
strictly before the prediction date) AND the reference date of the fight being
predicted. The reference_date is required so that time-decay weights can be
computed correctly — history rows closer to reference_date receive higher weight.

Column assumptions for `history` (mirrors the per-fighter view derived from the
interim bilateral fights schema; build_matrix.build_full_matrix is the canonical
producer of this view):
    event_date                  datetime64[ns]
    fighter_role                str  "a" | "b"   (which corner this fighter was in)
    sig_strikes_landed          int
    sig_strikes_attempted       int   (optional; only present after Track 2B scrape)
    opp_sig_strikes_landed      int
    opp_sig_strikes_attempted   int   (optional)
    takedowns_landed            int
    takedowns_attempted         int   (optional)
    opp_takedowns_landed        int
    opp_takedowns_attempted     int   (optional)
    sub_attempts                int
    fight_duration_seconds      float
    fight_duration_minutes      float (= fight_duration_seconds / 60)
    winner                      bool  (True if this fighter won)
    method                      str   "KO/TKO" | "Submission" | "Decision" | ...

If `*_attempted` columns are absent we fall back to landed-only proxies. That
is the current production state of the data; Track 2B will fill the gap.

The full feature dictionary lives in docs/feature_dictionary.md.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.config import DECAY_HALF_LIFE_DAYS

# --- decay weights -----------------------------------------------------------


def _decay_weights(
    history: pd.DataFrame,
    reference: date,
    half_life_days: float = DECAY_HALF_LIFE_DAYS,
) -> np.ndarray:
    """Exponential decay weights with `half_life_days` half-life.

    Weight = exp(-λ * days_ago) where λ = ln(2) / half_life.
    Most recent fight → weight near 1.0; fight from 3 years ago → weight ~0.16.
    Returns a 1-D numpy array aligned with history's index order.
    """
    if len(history) == 0:
        return np.zeros(0, dtype=float)
    ref = pd.Timestamp(reference)
    days_ago = (
        (ref - pd.to_datetime(history["event_date"])).dt.days.clip(lower=0).to_numpy()
    )
    lam = np.log(2) / float(half_life_days)
    return np.exp(-lam * days_ago)


def _safe_minutes(history: pd.DataFrame) -> np.ndarray:
    """Return a positive-definite minutes column, falling back across schemas."""
    if "fight_duration_minutes" in history.columns:
        m = history["fight_duration_minutes"].to_numpy(dtype=float)
    elif "fight_duration_min" in history.columns:
        m = history["fight_duration_min"].to_numpy(dtype=float)
    elif "fight_duration_seconds" in history.columns:
        m = history["fight_duration_seconds"].to_numpy(dtype=float) / 60.0
    elif "fight_duration_sec" in history.columns:
        m = history["fight_duration_sec"].to_numpy(dtype=float) / 60.0
    else:
        # Best effort — assume 15 min for an unknown duration.
        m = np.full(len(history), 15.0)
    # Guard divide-by-zero; a 1-second draw should not blow up to inf.
    return np.where(m <= 0.1, 0.1, m)


def _weighted_rate(
    numerator: np.ndarray,
    minutes: np.ndarray,
    weights: np.ndarray,
    *,
    per_minutes: float = 1.0,
) -> float:
    """Time-decayed rate (events per `per_minutes` minutes of fight time).

    Sum(weight * events) / Sum(weight * minutes) — this is the correct
    aggregation when minutes vary fight-to-fight, because it credits a long
    fight with more minutes than a short one. A flat per-fight average would
    over-weight 30-second knockouts.
    """
    denom = float((weights * minutes).sum())
    if denom <= 1e-9:
        return 0.0
    return float((weights * numerator).sum()) / denom * float(per_minutes)


def _weighted_ratio(
    num: np.ndarray, den: np.ndarray, weights: np.ndarray
) -> float:
    """Time-decayed ratio (e.g. landed / attempted). Returns 0.0 if no attempts."""
    denom = float((weights * den).sum())
    if denom <= 1e-9:
        return 0.0
    return float((weights * num).sum()) / denom


# --- Tier-1 features ---------------------------------------------------------


def slpm(history: pd.DataFrame, reference_date: date) -> float:
    """Significant strikes landed per minute, time-decayed.

    Uses sum(weight * strikes) / sum(weight * minutes) so longer fights get
    proportionally more weight — see _weighted_rate for the rationale.
    """
    if len(history) == 0:
        return 0.0
    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)
    landed = history["sig_strikes_landed"].to_numpy(dtype=float)
    return _weighted_rate(landed, minutes, weights)


def sapm(history: pd.DataFrame, reference_date: date) -> float:
    """Significant strikes absorbed per minute, time-decayed."""
    if len(history) == 0:
        return 0.0
    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)
    absorbed = history["opp_sig_strikes_landed"].to_numpy(dtype=float)
    return _weighted_rate(absorbed, minutes, weights)


def td_accuracy(history: pd.DataFrame, reference_date: date) -> float:
    """Takedown landing rate proxy — a tanh-rescaled per-15-min density.

    Historically named `td_accuracy` because the original feature_matrix used
    it where a true accuracy would naturally fit, but the formula has always
    been ``tanh(landings_per_15min / 3)`` because v1 lacked the attempted
    counts. We keep the legacy semantics under this name for backward-compat
    with the saved XGB/logreg/LSTM bundles whose `td_per15_diff` column was
    trained on the tanh proxy. Use ``td_true_accuracy`` for the true ratio.
    """
    if len(history) == 0:
        return 0.0
    weights = _decay_weights(history, reference_date)
    landed = history["takedowns_landed"].to_numpy(dtype=float)
    minutes = _safe_minutes(history)
    rate_per_15 = _weighted_rate(landed, minutes, weights, per_minutes=15.0)
    return float(np.tanh(rate_per_15 / 3.0))  # ~3 TD/15min ≈ 0.76


def td_defence(history: pd.DataFrame, reference_date: date) -> float:
    """1 - tanh(opp_landings_per_15min / 3) — the legacy `td_def_per15_diff` proxy.

    See ``td_accuracy`` re: backward-compat. The true defence-vs-accuracy is
    available as ``td_true_defence`` once Track 2B columns are populated.
    """
    if len(history) == 0:
        return 0.0
    weights = _decay_weights(history, reference_date)
    opp_landed = history["opp_takedowns_landed"].to_numpy(dtype=float)
    minutes = _safe_minutes(history)
    opp_rate = _weighted_rate(opp_landed, minutes, weights, per_minutes=15.0)
    return float(1.0 - np.tanh(opp_rate / 3.0))


def td_true_accuracy(history: pd.DataFrame, reference_date: date) -> float:
    """True takedown accuracy = TDs landed / TDs attempted, time-decayed.

    Returns NaN when no past fight has Track 2B `takedowns_attempted` data
    (callers can coerce to 0). NaN-safe per-row: masks out fights with
    missing attempted values rather than poisoning the aggregation.
    """
    if len(history) == 0 or "takedowns_attempted" not in history.columns:
        return float("nan")
    weights = _decay_weights(history, reference_date)
    landed = history["takedowns_landed"].to_numpy(dtype=float)
    attempted = history["takedowns_attempted"].to_numpy(dtype=float)
    mask = ~np.isnan(attempted)
    if not mask.any():
        return float("nan")
    return _weighted_ratio(landed[mask], attempted[mask], weights[mask])


def td_true_defence(history: pd.DataFrame, reference_date: date) -> float:
    """1 - opponent's true TD accuracy against this fighter (Track 2B feature)."""
    if len(history) == 0 or "opp_takedowns_attempted" not in history.columns:
        return float("nan")
    weights = _decay_weights(history, reference_date)
    opp_landed = history["opp_takedowns_landed"].to_numpy(dtype=float)
    opp_attempted = history["opp_takedowns_attempted"].to_numpy(dtype=float)
    mask = ~np.isnan(opp_attempted)
    if not mask.any():
        return float("nan")
    opp_acc = _weighted_ratio(opp_landed[mask], opp_attempted[mask], weights[mask])
    return float(1.0 - opp_acc)


def strike_accuracy(history: pd.DataFrame, reference_date: date) -> float:
    """Significant-strike accuracy = landed / attempted, time-decayed.

    Returns NaN when `sig_strikes_attempted` is unavailable for every past
    fight so callers can distinguish "no signal" from "0% accuracy" — a real
    fighter never has 0% over a career, so 0 means missing data.
    """
    if len(history) == 0 or "sig_strikes_attempted" not in history.columns:
        return float("nan")
    weights = _decay_weights(history, reference_date)
    landed = history["sig_strikes_landed"].to_numpy(dtype=float)
    attempted = history["sig_strikes_attempted"].to_numpy(dtype=float)
    mask = ~np.isnan(attempted)
    if not mask.any():
        return float("nan")
    return _weighted_ratio(landed[mask], attempted[mask], weights[mask])


def strike_defence(history: pd.DataFrame, reference_date: date) -> float:
    """1 - opponent's significant-strike accuracy against this fighter."""
    if len(history) == 0 or "opp_sig_strikes_attempted" not in history.columns:
        return float("nan")
    weights = _decay_weights(history, reference_date)
    opp_landed = history["opp_sig_strikes_landed"].to_numpy(dtype=float)
    opp_attempted = history["opp_sig_strikes_attempted"].to_numpy(dtype=float)
    mask = ~np.isnan(opp_attempted)
    if not mask.any():
        return float("nan")
    opp_acc = _weighted_ratio(opp_landed[mask], opp_attempted[mask], weights[mask])
    return float(1.0 - opp_acc)


def control_pct(history: pd.DataFrame, reference_date: date) -> float:
    """Fraction of fight time spent controlling, time-decayed.

    Sum(weight * control_seconds) / Sum(weight * fight_seconds). UFCStats
    Ctrl is the "this fighter on top in dominant position" timer, so this is
    a clean grappling-pressure signal that's invisible without the detail
    pages. Returns NaN when control time is unavailable for every past fight.
    """
    if len(history) == 0 or "control_time_seconds" not in history.columns:
        return float("nan")
    weights = _decay_weights(history, reference_date)
    ctrl = history["control_time_seconds"].to_numpy(dtype=float)
    seconds = _safe_minutes(history) * 60.0  # reuse the safe-minutes guard
    mask = ~np.isnan(ctrl)
    if not mask.any():
        return float("nan")
    denom = float((weights[mask] * seconds[mask]).sum())
    if denom <= 1e-9:
        return 0.0
    return float((weights[mask] * ctrl[mask]).sum()) / denom


def sub_avg(history: pd.DataFrame, reference_date: date) -> float:
    """Submission attempts per 15 minutes, time-decayed."""
    if len(history) == 0:
        return 0.0
    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)
    attempts = history["sub_attempts"].to_numpy(dtype=float)
    return _weighted_rate(attempts, minutes, weights, per_minutes=15.0)


def finish_rate(history: pd.DataFrame) -> float:
    """Career finishes / total wins. Not time-decayed — career-level signal.

    Returns 0.0 for fighters with zero career wins. KO/TKO and Submission both
    count as finishes; Decision wins do not.
    """
    if len(history) == 0:
        return 0.0
    wins = history["winner"].astype(bool).to_numpy()
    n_wins = int(wins.sum())
    if n_wins == 0:
        return 0.0
    methods = history["method"].astype(str).to_numpy()
    finish_keywords = ("KO/TKO", "TKO", "KO", "Submission", "SUB")
    is_finish = np.array(
        [any(k in m for k in finish_keywords) and "Decision" not in m for m in methods]
    )
    n_finishes = int((wins & is_finish).sum())
    return float(n_finishes) / float(n_wins)


# --- Convenience helpers -----------------------------------------------------


def days_inactive(last_fight: date | None, reference: date) -> int:
    if last_fight is None:
        return 9999
    return (reference - last_fight).days


def remove_vig(prob_a: float, prob_b: float) -> tuple[float, float]:
    """Remove bookmaker overround so prob_a + prob_b == 1."""
    total = prob_a + prob_b
    return prob_a / total, prob_b / total


def moneyline_to_probability(odds: int) -> float:
    """American moneyline → implied probability."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


# --- Compound / Tier-2 features ---------------------------------------------
# These compose the Tier-1 features above into the engineered signals the
# production feature matrix actually uses (see data/processed/feature_matrix.parquet).


def kd_per15(history: pd.DataFrame, reference_date: date) -> float:
    """Knockdowns scored per 15 minutes."""
    if len(history) == 0 or "knockdowns" not in history.columns:
        return 0.0
    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)
    kd = history["knockdowns"].to_numpy(dtype=float)
    return _weighted_rate(kd, minutes, weights, per_minutes=15.0)


def kd_absorbed_per15(history: pd.DataFrame, reference_date: date) -> float:
    """Knockdowns absorbed per 15 minutes."""
    if len(history) == 0 or "opp_knockdowns" not in history.columns:
        return 0.0
    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)
    kd = history["opp_knockdowns"].to_numpy(dtype=float)
    return _weighted_rate(kd, minutes, weights, per_minutes=15.0)


def _target_landed_per15(history: pd.DataFrame, reference_date: date, col: str) -> float:
    if len(history) == 0 or col not in history.columns:
        return 0.0
    weights = _decay_weights(history, reference_date)
    minutes = _safe_minutes(history)
    vals = history[col].fillna(0).to_numpy(dtype=float)
    return _weighted_rate(vals, minutes, weights, per_minutes=15.0)


def _target_accuracy(history: pd.DataFrame, reference_date: date, landed_col: str, att_col: str) -> float:
    if len(history) == 0 or landed_col not in history.columns or att_col not in history.columns:
        return 0.0
    weights = _decay_weights(history, reference_date)
    landed = history[landed_col].fillna(0).to_numpy(dtype=float)
    attempted = history[att_col].fillna(0).to_numpy(dtype=float)
    return _weighted_ratio(landed, attempted, weights)


def head_landed_per15(h, d):     return _target_landed_per15(h, d, "head_landed")
def body_landed_per15(h, d):     return _target_landed_per15(h, d, "body_landed")
def leg_landed_per15(h, d):      return _target_landed_per15(h, d, "leg_landed")
def head_absorbed_per15(h, d):   return _target_landed_per15(h, d, "opp_head_landed")
def body_absorbed_per15(h, d):   return _target_landed_per15(h, d, "opp_body_landed")
def leg_absorbed_per15(h, d):    return _target_landed_per15(h, d, "opp_leg_landed")
def head_accuracy(h, d):         return _target_accuracy(h, d, "head_landed", "head_attempted")
def leg_accuracy(h, d):          return _target_accuracy(h, d, "leg_landed", "leg_attempted")


def win_pct(history: pd.DataFrame, reference_date: date) -> float:
    """Time-decayed win percentage."""
    if len(history) == 0:
        return 0.5
    weights = _decay_weights(history, reference_date)
    wins = history["winner"].astype(bool).to_numpy(dtype=float)
    denom = float(weights.sum())
    if denom <= 1e-9:
        return 0.5
    return float((weights * wins).sum()) / denom


def streak(history: pd.DataFrame) -> int:
    """Current win streak (positive) or losing streak (negative).

    Walks history from most recent backwards and counts consecutive wins
    or losses. History must be sorted by event_date ascending.
    """
    if len(history) == 0:
        return 0
    wins = history.sort_values("event_date")["winner"].astype(bool).to_numpy()
    last = wins[-1]
    streak_len = 1
    for w in reversed(wins[:-1]):
        if w == last:
            streak_len += 1
        else:
            break
    return int(streak_len if last else -streak_len)


def rounds_experience(history: pd.DataFrame) -> float:
    """Total rounds fought across career (a coarse durability/experience proxy)."""
    if len(history) == 0:
        return 0.0
    if "round_finished" in history.columns:
        return float(history["round_finished"].fillna(0).sum())
    if "fight_duration_minutes" in history.columns:
        return float(history["fight_duration_minutes"].fillna(0).sum() / 5.0)
    return 0.0


# --- Weight-class change ------------------------------------------------------

# Unified division ladder (contract weight limits in lbs). Men's and women's
# divisions share the same poundage rungs, so one ladder covers both; a move
# is measured in rungs, not lbs, so LHW→HW (60 lbs) counts the same as
# WW→MW (15 lbs) — one division up. Catch Weight has no rung (NaN).
WEIGHT_CLASS_LBS: dict[str, int] = {
    "Strawweight": 115,
    "Women's Strawweight": 115,
    "Flyweight": 125,
    "Women's Flyweight": 125,
    "Bantamweight": 135,
    "Women's Bantamweight": 135,
    "Featherweight": 145,
    "Women's Featherweight": 145,
    "Lightweight": 155,
    "Welterweight": 170,
    "Middleweight": 185,
    "Light Heavyweight": 205,
    "Heavyweight": 265,
}

_LADDER: list[int] = sorted(set(WEIGHT_CLASS_LBS.values()))
_RUNG: dict[int, int] = {lbs: i for i, lbs in enumerate(_LADDER)}


def weight_class_rung(weight_class) -> float:
    """Ladder rung index (0 = 115 lbs … 8 = HW) for a class name; NaN if unknown."""
    lbs = WEIGHT_CLASS_LBS.get(str(weight_class or "").strip())
    return float(_RUNG[lbs]) if lbs is not None else np.nan


def _history_rungs(history: pd.DataFrame) -> pd.Series:
    """History's weight classes as rung indices, sorted by date, unknowns dropped."""
    if len(history) == 0 or "weight_class" not in history.columns:
        return pd.Series(dtype=float)
    hist = history.sort_values("event_date")
    return hist["weight_class"].map(weight_class_rung).dropna()


def weight_change(history: pd.DataFrame, current_weight_class) -> float:
    """Divisions moved since the fighter's most recent fight at a known class.

    +1 = up one division (e.g. LW→WW), -1 = down one, ±2 for double jumps.
    0.0 for debutants, catchweight bouts, or an all-catchweight history —
    a centred "no known move" default, matching the diff-feature convention.
    A catchweight in between is skipped: the comparison anchors on the last
    fight with a real division so a one-off 180-lb bout doesn't mask a move.
    """
    cur = weight_class_rung(current_weight_class)
    if np.isnan(cur):
        return 0.0
    rungs = _history_rungs(history)
    if len(rungs) == 0:
        return 0.0
    return float(cur - rungs.iloc[-1])


def first_fight_at_class(history: pd.DataFrame, current_weight_class) -> float:
    """1.0 if the fighter has prior fights but has never fought at this class.

    Debutants return 0.0 — with no history at all, "new class" carries no
    information beyond n_fights == 0, which the model already sees.
    """
    cur = weight_class_rung(current_weight_class)
    if np.isnan(cur):
        return 0.0
    rungs = _history_rungs(history)
    if len(rungs) == 0:
        return 0.0
    return 0.0 if bool((rungs == cur).any()) else 1.0


def natural_weight_deviation(
    history: pd.DataFrame, current_weight_class, reference_date: date
) -> float:
    """Rungs between this bout's class and the fighter's time-decayed home class.

    The "natural" class is the decay-weighted mean rung over the fighter's
    prior fights, so it drifts as a fighter settles into a new division.
    Unlike weight_change (which is 0 again by a fighter's second fight at a
    new weight), this stays elevated while the move is still recent — the
    chronic-displacement signal. 0.0 when either side is unknown.
    """
    cur = weight_class_rung(current_weight_class)
    if np.isnan(cur):
        return 0.0
    if len(history) == 0 or "weight_class" not in history.columns:
        return 0.0
    hist = history.sort_values("event_date")
    rungs = hist["weight_class"].map(weight_class_rung).to_numpy(dtype=float)
    weights = _decay_weights(hist, reference_date)
    mask = ~np.isnan(rungs)
    denom = float(weights[mask].sum())
    if denom <= 1e-9:
        return 0.0
    home = float((weights[mask] * rungs[mask]).sum()) / denom
    dev = float(cur - home)
    # Snap float noise (weighted mean of identical rungs ≈ 1e-16 off) to 0.
    return dev if abs(dev) > 1e-9 else 0.0

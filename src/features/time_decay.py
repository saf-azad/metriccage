"""Time-decayed averages for fighter statistics.

Raw career averages overweight ancient fights. Use exponential decay with a
half-life of 365 days so a 1-year-old fight contributes half as much as today.
See docs/PLAN.md §5.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from src.config import DECAY_HALF_LIFE_DAYS


def time_decayed_average(
    values: np.ndarray | list[float],
    dates: list[date],
    reference_date: date,
    half_life_days: int = DECAY_HALF_LIFE_DAYS,
) -> float:
    """Exponentially weighted mean of `values` with weights based on age vs reference_date.

    Returns 0.0 (or NaN — TBD) if the input is empty.
    """
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return float("nan")
    lambda_ = np.log(2) / half_life_days
    days_ago = np.array([(reference_date - d).days for d in dates], dtype=float)
    weights = np.exp(-lambda_ * np.maximum(days_ago, 0.0))
    return float(np.average(values, weights=weights))

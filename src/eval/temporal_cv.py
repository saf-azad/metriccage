"""Walk-forward (expanding window) cross-validation.

The ONLY valid CV scheme for time-ordered fights. Standard k-fold leaks. This
generator yields (train_idx, val_idx) pairs where every val date strictly
exceeds every train date.

See docs/PLAN.md §7.1: each fold trains on all data before its cutoff and
evaluates on the next window.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pandas as pd


def walk_forward_splits(
    df: pd.DataFrame,
    *,
    date_col: str = "event_date",
    n_splits: int = 5,
    min_train_size: int = 500,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (train_indices, val_indices). Expanding train, fixed val window.

    Semantics mirror ``sklearn.model_selection.TimeSeriesSplit`` but are
    date-aware: fold boundaries are snapped to date-group boundaries so that a
    single date can never straddle train and validation. Every fold therefore
    satisfies ``max(train dates) < min(val dates)`` *strictly*.

    Parameters
    ----------
    df : DataFrame with a parseable date column ``date_col``. May be unsorted;
        rows are ordered by date internally (stable sort, so within-date order
        is preserved).
    date_col : name of the date column.
    n_splits : number of expanding-window folds to yield.
    min_train_size : minimum number of rows in the first fold's training set.
        The actual first cut is the smallest date boundary at or beyond this
        count (never mid-date).

    Yields
    ------
    (train_idx, val_idx) : two ``np.ndarray`` of *positional* indices into the
        original ``df`` (use with ``df.iloc[...]`` / ``X[idx]``). Train windows
        expand: fold ``i``'s train set is the base block plus all previous
        folds' validation rows. Validation windows are contiguous, mutually
        disjoint chunks of the remaining date groups, split as evenly as
        possible by date group.

    Raises
    ------
    ValueError : if ``date_col`` is missing or contains NaT, if
        ``n_splits``/``min_train_size`` are < 1, or if there are not at least
        ``n_splits`` distinct dates left after the minimum training block.
    """
    if date_col not in df.columns:
        raise ValueError(
            f"date_col {date_col!r} not found in DataFrame columns {list(df.columns)!r}"
        )
    if n_splits < 1:
        raise ValueError(f"n_splits must be >= 1, got {n_splits}")
    if min_train_size < 1:
        raise ValueError(f"min_train_size must be >= 1, got {min_train_size}")

    dates = pd.to_datetime(df[date_col])
    if dates.isna().any():
        n_bad = int(dates.isna().sum())
        raise ValueError(
            f"{date_col!r} contains {n_bad} NaT/unparseable value(s); "
            "drop or fix them before splitting"
        )

    n = len(df)
    date_values = dates.to_numpy()
    order = np.argsort(date_values, kind="stable")  # positions into the ORIGINAL df
    sorted_dates = date_values[order]

    # group_ends[j] = number of rows on or before the j-th unique date
    # (i.e. exclusive end position, in sorted order, of that date's group).
    _, counts = np.unique(sorted_dates, return_counts=True)
    group_ends = np.cumsum(counts)

    if n < min_train_size:
        raise ValueError(
            f"Not enough rows for walk-forward CV: need at least "
            f"min_train_size={min_train_size} training rows plus validation data, "
            f"got only {n} rows"
        )

    # First date boundary at or beyond min_train_size rows — the base train block.
    j0 = int(np.searchsorted(group_ends, min_train_size, side="left"))
    remaining_groups = np.arange(j0 + 1, len(group_ends))
    if len(remaining_groups) < n_splits:
        raise ValueError(
            f"Only {len(remaining_groups)} distinct date(s) remain after the initial "
            f"{int(group_ends[j0])}-row training block; need at least n_splits={n_splits}. "
            "Reduce n_splits or min_train_size, or provide more data."
        )

    for chunk in np.array_split(remaining_groups, n_splits):
        # Validation rows = all rows of the chunk's date groups, in sorted order.
        val_start = int(group_ends[chunk[0] - 1])
        val_end = int(group_ends[chunk[-1]])
        train_idx = order[:val_start].copy()
        val_idx = order[val_start:val_end].copy()
        yield train_idx, val_idx

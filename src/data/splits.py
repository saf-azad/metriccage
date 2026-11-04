"""Temporal train / validation / test splits.

The ONLY valid splitting scheme for this project. Standard random splits leak
the future. See docs/PLAN.md §4.2 for the date ranges.
"""

from __future__ import annotations

import pandas as pd

from src.config import TEST_END, TEST_START, TRAIN_END, TRAIN_START, VAL_END, VAL_START


def split(df: pd.DataFrame, *, date_col: str = "event_date") -> dict[str, pd.DataFrame]:
    """Return {'train': df, 'val': df, 'test': df}. df must have a date column."""
    d = pd.to_datetime(df[date_col]).dt.date
    return {
        "train": df[(d >= TRAIN_START) & (d <= TRAIN_END)].copy(),
        "val": df[(d >= VAL_START) & (d <= VAL_END)].copy(),
        "test": df[(d >= TEST_START) & (d <= TEST_END)].copy(),
    }


def assert_no_leakage(train: pd.DataFrame, test: pd.DataFrame, *, date_col: str = "event_date") -> None:
    """Hard assertion that every train row is strictly before every test row."""
    if len(train) == 0 or len(test) == 0:
        return
    train_max = pd.to_datetime(train[date_col]).max()
    test_min = pd.to_datetime(test[date_col]).min()
    if train_max >= test_min:
        raise AssertionError(f"Temporal leak: train max {train_max.date()} >= test min {test_min.date()}")

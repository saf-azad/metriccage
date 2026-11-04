"""Tests that the temporal split contract is honoured."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.splits import assert_no_leakage, split


def _toy_df():
    return pd.DataFrame(
        {
            "event_date": pd.to_datetime(
                [
                    "2010-06-01",
                    "2018-09-01",
                    "2022-11-30",
                    "2023-06-15",
                    "2024-04-04",
                    "2025-02-02",
                ]
            ),
            "fight_id": list("abcdef"),
        }
    )


def test_split_assigns_each_fight_to_at_most_one_bucket():
    df = _toy_df()
    s = split(df)
    counts = sum(len(v) for v in s.values())
    assert counts == len(df)
    union = pd.concat(s.values())["fight_id"]
    assert union.is_unique


def test_assert_no_leakage_passes_for_clean_split():
    df = _toy_df()
    s = split(df)
    assert_no_leakage(s["train"], s["test"])


def test_assert_no_leakage_raises_on_overlap():
    df = _toy_df()
    s = split(df)
    bad_train = pd.concat([s["train"], s["test"].iloc[:1]])
    with pytest.raises(AssertionError):
        assert_no_leakage(bad_train, s["test"])


def test_boundary_dates_land_in_correct_buckets():
    # The last day of each window and the first day of the next must not overlap.
    # TRAIN_END = 2022-12-31, VAL_START = 2023-01-01, VAL_END = 2023-12-31, TEST_START = 2024-01-01.
    boundary = pd.DataFrame(
        {
            "event_date": pd.to_datetime(
                [
                    "2022-12-31",  # last train day  → train
                    "2023-01-01",  # first val day   → val
                    "2023-12-31",  # last val day    → val
                    "2024-01-01",  # first test day  → test
                ]
            ),
            "fight_id": list("wxyz"),
        }
    )
    s = split(boundary)
    assert set(s["train"]["fight_id"]) == {"w"}
    assert set(s["val"]["fight_id"]) == {"x", "y"}
    assert set(s["test"]["fight_id"]) == {"z"}

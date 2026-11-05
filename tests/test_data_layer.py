"""Data-layer tests: cleaning, label balancing, scraper deferrals, build_features CLI.

Pure-synthetic tests always run; tests marked with ``requires_fights_parquet``
need the local data/interim parquets and are skipped when absent (e.g. CI).
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data import scrape_odds, scrape_ufcstats
from src.data.clean import (
    WEIGHT_CLASS_MAP,
    balance_fight_labels,
    clean_fighters,
    clean_fights,
)

ROOT = Path(__file__).resolve().parents[1]
FIGHTS_PARQUET = ROOT / "data" / "interim" / "fights.parquet"
FIGHTERS_PARQUET = ROOT / "data" / "interim" / "fighters.parquet"

requires_fights_parquet = pytest.mark.skipif(
    not FIGHTS_PARQUET.exists(), reason="needs data/interim/fights.parquet"
)
requires_fighters_parquet = pytest.mark.skipif(
    not FIGHTERS_PARQUET.exists(), reason="needs data/interim/fighters.parquet"
)


# --- synthetic raw-frame factories -------------------------------------------


def _raw_fight_row(i: int, **overrides) -> dict:
    row = {
        "fight_id": f"f{i:03d}",
        "event_id": f"e{i // 10:03d}",
        "event_date": "2012-06-01",
        "event_name": "UFC Test Night",
        "weight_class": "Lightweight",
        "fighter_a_id": f"a{i:03d}",
        "fighter_a_name": f"Alpha {i}",
        "fighter_b_id": f"b{i:03d}",
        "fighter_b_name": f"Bravo {i}",
        "winner_id": f"a{i:03d}",
        "method": "U-DEC",
        "method_detail": "",
        "round_finished": "3",
        "time_finished": "5:00",
        "kd_a": "0", "kd_b": 0,
        "ss_landed_a": 40, "ss_landed_b": 25,
        "td_landed_a": 2, "td_landed_b": 0,
        "sub_att_a": 0, "sub_att_b": 1,
        "fight_url": f"http://ufcstats.com/fight-details/f{i:03d}",
    }
    row.update(overrides)
    return row


def _make_synthetic_fights(n: int = 30, n_fighters: int = 8, seed: int = 0) -> pd.DataFrame:
    """A small raw-style fights frame: n fights among n_fighters over 2010-2015."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        a, b = rng.choice(n_fighters, size=2, replace=False)
        winner_is_a = rng.random() < 1.0  # winner-first bias, like the real raw data
        methods = ["U-DEC", "KO/TKO", "SUB", "S-DEC"]
        method = methods[int(rng.integers(len(methods)))]
        rows.append(
            _raw_fight_row(
                i,
                event_date=str(date(2010 + i // 6, 1 + (i % 6) * 2, 15)),
                fighter_a_id=f"ftr{a}", fighter_a_name=f"Fighter {a}",
                fighter_b_id=f"ftr{b}", fighter_b_name=f"Fighter {b}",
                winner_id=f"ftr{a}" if winner_is_a else f"ftr{b}",
                method=method,
                round_finished=str(int(rng.integers(1, 4))),
                time_finished=f"{int(rng.integers(0, 5))}:{int(rng.integers(0, 60)):02d}",
                kd_a=int(rng.integers(0, 2)), kd_b=int(rng.integers(0, 2)),
                ss_landed_a=int(rng.integers(0, 120)), ss_landed_b=int(rng.integers(0, 120)),
                td_landed_a=int(rng.integers(0, 6)), td_landed_b=int(rng.integers(0, 6)),
                sub_att_a=int(rng.integers(0, 3)), sub_att_b=int(rng.integers(0, 3)),
            )
        )
    return pd.DataFrame(rows)


def _make_synthetic_fighters(n_fighters: int = 8) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fighter_id": [f"ftr{i}" for i in range(n_fighters)],
            "name": [f"Fighter {i}" for i in range(n_fighters)],
            "height_in": ["""5' 11\"""", """6' 2\"""", 70, "68", None, """5' 6\"""", 74.0, "--"],
            "reach_in": ['72"', "76", 71.5, None, "--", '66"', 78, "70"],
            "stance": ["Orthodox", "SOUTHPAW", " switch ", "", None, "Open Stance", "orthodox", "--"],
            "dob": ["1985-02-07", "Apr 28, 1990", None, "1992-11-30", "--", "1988-06-15",
                    "1991-01-01", "1979-12-25"],
        }
    )


# --- clean_fights -------------------------------------------------------------


def test_clean_fights_synthetic_canonicalisation() -> None:
    raw = pd.DataFrame(
        [
            _raw_fight_row(0, event_date="2011-03-19", method="U-DEC"),
            _raw_fight_row(1, event_date="2009-05-02", method="KO/TKO",
                           round_finished="1", time_finished="2:24"),
            _raw_fight_row(2, event_date="2013-08-03", method="SUB", winner_id="b002"),
            _raw_fight_row(3, event_date="2014-01-04", method="DQ"),
            _raw_fight_row(4, event_date="2014-02-01", method="NC"),          # dropped: no contest
            _raw_fight_row(5, event_date="2010-07-03", method="M-DEC"),
            _raw_fight_row(6, event_date="2010-09-25", method="S-DEC",
                           weight_class="lhw"),                                # alias -> full name
            _raw_fight_row(0, event_date="2011-03-19", method="U-DEC"),        # dropped: dupe fight_id
            _raw_fight_row(7, event_date="2015-05-23", fighter_a_id=None),     # dropped: missing id
            _raw_fight_row(8, event_date=None),                                # dropped: missing date
            _raw_fight_row(9, event_date="2012-12-08", weight_class="women's bantamweight"),
        ]
    )
    out = clean_fights(raw)

    # NC, dupe, missing-id and missing-date rows are gone
    assert list(out["fight_id"]) == ["f001", "f005", "f006", "f000", "f009", "f002", "f003"]
    # stable chronological sort
    assert out["event_date"].is_monotonic_increasing
    assert isinstance(out["event_date"].iloc[0], date)

    canon = dict(zip(out["fight_id"], out["method_canon"], strict=True))
    assert canon["f000"] == "Decision"      # U-DEC
    assert canon["f005"] == "Decision"      # M-DEC
    assert canon["f006"] == "Decision"      # S-DEC
    assert canon["f001"] == "KO/TKO"
    assert canon["f002"] == "Submission"
    assert canon["f003"] == "DQ"            # empirical v1 mapping: DQ stays DQ

    wc = dict(zip(out["fight_id"], out["weight_class"], strict=True))
    assert wc["f006"] == "Light Heavyweight"        # abbreviation alias restored
    assert wc["f009"] == "Women's Bantamweight"     # case variant restored
    assert wc["f000"] == "Lightweight"              # canonical passes through

    # label + derived columns
    a_won = dict(zip(out["fight_id"], out["fighter_a_won"], strict=True))
    assert a_won["f000"] == 1 and a_won["f002"] == 0
    row1 = out[out["fight_id"] == "f001"].iloc[0]
    assert row1["time_finished_sec"] == 144
    assert row1["fight_duration_sec"] == 144            # round 1: (1-1)*300 + 144
    assert row1["fight_duration_min"] == pytest.approx(2.4)
    row0 = out[out["fight_id"] == "f000"].iloc[0]
    assert row0["fight_duration_sec"] == 900            # round 3 decision

    # numeric coercion ("0" strings become int64)
    assert out["kd_a"].dtype == np.dtype("int64")
    assert str(out["round_finished"].dtype) == "Int64"


def test_clean_fights_missing_critical_column_raises() -> None:
    raw = _make_synthetic_fights(5).drop(columns=["winner_id"])
    with pytest.raises(KeyError, match="winner_id"):
        clean_fights(raw)


@requires_fights_parquet
def test_clean_fights_roundtrip_real_sample() -> None:
    """Deliberately un-clean a 200-row sample of the canonical parquet, re-clean
    it, and require exact equivalence (values AND dtypes)."""
    full = pd.read_parquet(FIGHTS_PARQUET)
    sample = full.sample(n=200, random_state=0)
    original = sample.sort_values(["event_date", "fight_id"], kind="stable").reset_index(drop=True)

    raw = original.copy()
    # strip the derived columns a raw scrape would not carry
    raw = raw.drop(columns=["method_canon", "fighter_a_won", "time_finished_sec",
                            "fight_duration_sec", "fight_duration_min"])
    # stringify dates + numerics
    raw["event_date"] = raw["event_date"].astype(str)
    raw["kd_a"] = raw["kd_a"].astype(str)
    raw["round_finished"] = raw["round_finished"].astype(str)
    # scramble weight-class aliases on the first 10 mappable rows
    scrambled = 0
    for i in raw.index:
        wc = raw.at[i, "weight_class"]
        if wc in WEIGHT_CLASS_MAP and scrambled < 10:
            raw.at[i, "weight_class"] = WEIGHT_CLASS_MAP[wc]  # "Light Heavyweight" -> "lhw"
            scrambled += 1
    assert scrambled == 10
    # inject a duplicate and a No Contest
    dupe = raw.iloc[[0]]
    nc = raw.iloc[[1]].copy()
    nc["fight_id"] = "deadbeef00000000"
    nc["method"] = "NC"
    raw = pd.concat([raw, dupe, nc], ignore_index=True)
    raw = raw.sample(frac=1.0, random_state=1).reset_index(drop=True)  # shuffle order

    cleaned = (
        clean_fights(raw)
        .sort_values(["event_date", "fight_id"], kind="stable")
        .reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(cleaned, original)


# --- clean_fighters -----------------------------------------------------------


def test_clean_fighters_synthetic_coercion() -> None:
    raw = _make_synthetic_fighters()
    # add a duplicate fighter_id (kept-first) and a missing-id row (dropped)
    raw = pd.concat(
        [raw, raw.iloc[[0]], pd.DataFrame([{"fighter_id": None, "name": "Ghost"}])],
        ignore_index=True,
    )
    out = clean_fighters(raw)

    assert list(out.columns[:6]) == ["fighter_id", "name", "height_in", "reach_in", "stance", "dob"]
    assert len(out) == 8  # dupe deduped, missing-id dropped
    assert out["fighter_id"].is_unique

    h = dict(zip(out["fighter_id"], out["height_in"], strict=True))
    assert h["ftr0"] == 71.0        # 5' 11"
    assert h["ftr1"] == 74.0        # 6' 2"
    assert h["ftr2"] == 70.0        # numeric passthrough
    assert h["ftr3"] == 68.0        # bare-string number
    assert np.isnan(h["ftr4"]) and np.isnan(h["ftr7"])  # None / "--"

    r = dict(zip(out["fighter_id"], out["reach_in"], strict=True))
    assert r["ftr0"] == 72.0        # '72"'
    assert r["ftr2"] == 71.5
    assert np.isnan(r["ftr3"]) and np.isnan(r["ftr4"])

    s = dict(zip(out["fighter_id"], out["stance"], strict=True))
    assert s["ftr0"] == "orthodox" and s["ftr1"] == "southpaw" and s["ftr2"] == "switch"
    assert s["ftr5"] == "open stance"
    assert pd.isna(s["ftr3"]) and pd.isna(s["ftr4"]) and pd.isna(s["ftr7"])

    d = dict(zip(out["fighter_id"], out["dob"], strict=True))
    assert d["ftr0"] == "1985-02-07"
    assert d["ftr1"] == "1990-04-28"  # "Apr 28, 1990" normalised to ISO
    assert pd.isna(d["ftr2"]) and pd.isna(d["ftr4"])

    assert out["height_in"].dtype == np.dtype("float64")
    assert out["reach_in"].dtype == np.dtype("float64")


@requires_fighters_parquet
def test_clean_fighters_idempotent_on_real_sample() -> None:
    """Cleaning already-canonical fighter rows must be a no-op."""
    sample = (
        pd.read_parquet(FIGHTERS_PARQUET).sample(n=100, random_state=0).reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(clean_fighters(sample), sample)


# --- balance_fight_labels ------------------------------------------------------


def test_balance_fight_labels_deterministic_and_consistent() -> None:
    fights = clean_fights(_make_synthetic_fights(n=400, n_fighters=40, seed=3))
    assert (fights["fighter_a_won"] == 1).all()  # raw winner-first bias

    b1 = balance_fight_labels(fights, seed=42)
    b2 = balance_fight_labels(fights, seed=42)
    pd.testing.assert_frame_equal(b1, b2)  # seed-42 determinism

    # ~50% of rows swapped (binomial bounds for n=400)
    swap_rate = float(b1["fighter_a_won"].eq(0).mean())
    assert 0.40 <= swap_rate <= 0.60

    # a different seed produces a different swap pattern
    assert not b1["fighter_a_id"].equals(balance_fight_labels(fights, seed=7)["fighter_a_id"])

    # label consistency: fighter_a_won still means winner_id == fighter_a_id,
    # and swapped rows really moved both sides together
    assert (b1["fighter_a_won"] == (b1["winner_id"] == b1["fighter_a_id"]).astype(int)).all()
    swapped = b1["fighter_a_won"] == 0
    assert (b1.loc[swapped, "fighter_a_id"] == fights.loc[swapped, "fighter_b_id"]).all()
    assert (b1.loc[swapped, "ss_landed_a"] == fights.loc[swapped, "ss_landed_b"]).all()
    unswapped = ~swapped
    assert b1.loc[unswapped].equals(fights.loc[unswapped])
    # invariants: fight identity columns never move
    assert b1["fight_id"].equals(fights["fight_id"])
    assert b1["winner_id"].equals(fights["winner_id"])


# --- scraper deferral stubs -----------------------------------------------------


@pytest.mark.parametrize(
    "func, args",
    [
        (scrape_ufcstats.scrape_all_events, ()),
        (scrape_ufcstats.scrape_event_page, ("a6d8bfe9e0c8153b",)),
        (scrape_ufcstats.assemble_fights_dataframe, ()),
        (scrape_odds.scrape_all_odds, ()),
    ],
)
def test_scraper_stubs_are_self_documenting_deferrals(func, args) -> None:
    with pytest.raises(NotImplementedError, match="PLAN"):
        func(*args)


# --- scripts/build_features.py CLI ----------------------------------------------


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_features.py"), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )


def test_build_features_cli_synthetic(tmp_path: Path) -> None:
    fights = clean_fights(_make_synthetic_fights(n=30, n_fighters=8, seed=0))
    fighters = clean_fighters(_make_synthetic_fighters(8))
    fights_pq = tmp_path / "fights.parquet"
    fighters_pq = tmp_path / "fighters.parquet"
    fights.to_parquet(fights_pq, index=False)
    fighters.to_parquet(fighters_pq, index=False)

    common = ["--fights", str(fights_pq), "--fighters", str(fighters_pq), "--no-cluster"]

    # full build
    full_out = tmp_path / "matrix_full.parquet"
    res = _run_cli([*common, "--out", str(full_out)])
    assert res.returncode == 0, res.stderr
    full = pd.read_parquet(full_out)
    assert len(full) == 30
    assert full.shape[1] >= 100, f"expected 100+ feature columns, got {full.shape[1]}"
    for col in ["fight_id", "event_date", "fighter_a_won", "elo_diff", "elo_prob_a",
                "win_pct_diff", "arch_distance", "reach_diff"]:
        assert col in full.columns

    # --sample 5: last-5 rows only, but identical to the full build's tail
    # (proves the full history was still replayed -> temporal correctness)
    sample_out = tmp_path / "matrix_sample.parquet"
    res = _run_cli([*common, "--out", str(sample_out), "--sample", "5"])
    assert res.returncode == 0, res.stderr
    sampled = pd.read_parquet(sample_out)
    assert len(sampled) == 5
    pd.testing.assert_frame_equal(
        sampled.reset_index(drop=True), full.tail(5).reset_index(drop=True)
    )

    # refuses to overwrite without --force ...
    res = _run_cli([*common, "--out", str(sample_out), "--sample", "5"])
    assert res.returncode != 0
    assert "refusing to overwrite" in res.stderr
    # ... but allows it with --force
    res = _run_cli([*common, "--out", str(sample_out), "--sample", "5", "--force"])
    assert res.returncode == 0, res.stderr


def test_build_features_cli_requires_out(tmp_path: Path) -> None:
    res = _run_cli(["--sample", "5", "--no-cluster"])
    assert res.returncode != 0
    assert "--out" in res.stderr


# --- A/B side alignment of detail-page parsers ------------------------------
# fights.parquet has ~50% of rows deliberately A/B-swapped (balance_fight_labels),
# so anything parsed from a UFCStats page in page order must be realigned by
# fighter ID. Regression for the 2026-09 bug where 3,051 fights had
# ss_attempted / td_attempted / control_time and every target-zone column on
# the wrong side.


def test_align_detail_to_sides_swaps_when_page_order_is_reversed():
    from src.data.scrape_ufcstats import align_detail_to_sides

    data = {
        "page_fighter_0": "b" * 16, "page_fighter_1": "a" * 16,
        "ss_landed_a": 10, "ss_landed_b": 20, "ss_attempted_a": 30, "ss_attempted_b": 40,
        "td_landed_a": 1, "td_landed_b": 2, "td_attempted_a": 3, "td_attempted_b": 4,
        "control_time_a": 5.0, "control_time_b": 6.0,
    }
    out, status = align_detail_to_sides(dict(data), "a" * 16, "b" * 16)
    assert status == "swapped"
    assert (out["ss_landed_a"], out["ss_landed_b"]) == (20, 10)
    assert (out["ss_attempted_a"], out["ss_attempted_b"]) == (40, 30)
    assert (out["td_attempted_a"], out["td_attempted_b"]) == (4, 3)
    assert (out["control_time_a"], out["control_time_b"]) == (6.0, 5.0)

    out, status = align_detail_to_sides(dict(data), "b" * 16, "a" * 16)
    assert status == "direct" and out["ss_landed_a"] == 10

    out, status = align_detail_to_sides(dict(data), "c" * 16, "d" * 16)
    assert status == "unknown" and out["ss_landed_a"] == 10


def test_enriched_parquet_sides_are_consistent():
    """head+body+leg must equal ss_landed on the same side; attempted >= landed."""
    from pathlib import Path

    import pandas as pd
    import pytest

    path = Path(__file__).resolve().parents[1] / "data" / "interim" / "fights_enriched.parquet"
    if not path.exists():
        pytest.skip("fights_enriched.parquet not present")
    f = pd.read_parquet(path)
    needed = {"head_landed_a", "body_landed_a", "leg_landed_a", "ss_attempted_a"}
    if not needed.issubset(f.columns):
        pytest.skip("enriched columns not present")
    sum_a = f["head_landed_a"] + f["body_landed_a"] + f["leg_landed_a"]
    sum_b = f["head_landed_b"] + f["body_landed_b"] + f["leg_landed_b"]
    assert int(((sum_a != f["ss_landed_a"]) | (sum_b != f["ss_landed_b"])).sum()) == 0
    assert int(((f["ss_attempted_a"] < f["ss_landed_a"]) | (f["ss_attempted_b"] < f["ss_landed_b"])).sum()) == 0
    assert int(((f["td_attempted_a"] < f["td_landed_a"]) | (f["td_attempted_b"] < f["td_landed_b"])).sum()) == 0

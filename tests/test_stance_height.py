"""Tests for the stance-context × height-context matchup feature pack."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.features.stance_height import (
    _height_context,
    _stance_pairing,
    adaptability_features,
    stance_height_matchup_features,
)

REF = date(2026, 1, 1)

EXPECTED_KEYS = {
    "height_diff",
    "stance_ctx_strike_edge_a", "stance_ctx_strike_edge_b",
    "stance_ctx_strike_edge_diff", "stance_ctx_win_edge_diff",
    "height_ctx_strike_edge_a", "height_ctx_strike_edge_b",
    "height_ctx_strike_edge_diff", "height_ctx_win_edge_diff",
    "stance_height_combo_diff", "open_stance_height_diff",
}


def _hist(rows: list[dict]) -> pd.DataFrame:
    """History frame in the per-fighter schema build_matrix produces."""
    base = {
        "event_date": pd.Timestamp("2024-06-01"),
        "fight_duration_minutes": 15.0,
        "round_finished": 3,
        "winner": True,
        "sig_strikes_landed": 50,
        "opp_sig_strikes_landed": 30,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


BIOS = {
    "orth_tall":  {"stance": "orthodox", "height_in": 74.0},
    "orth_short": {"stance": "orthodox", "height_in": 68.0},
    "south_tall": {"stance": "southpaw", "height_in": 74.0},
    "south_even": {"stance": "southpaw", "height_in": 70.0},
    "switch_guy": {"stance": "switch",   "height_in": 70.0},
}


def test_stance_pairing_classification():
    assert _stance_pairing("orthodox", "southpaw") == "open"
    assert _stance_pairing("Southpaw", "orthodox") == "open"
    assert _stance_pairing("orthodox", "orthodox") == "closed"
    assert _stance_pairing("southpaw", "southpaw") == "closed"
    assert _stance_pairing("switch", "orthodox") is None
    assert _stance_pairing("", "orthodox") is None


def test_height_context_neutral_band():
    assert _height_context(70.0, 74.0) == "taller"
    assert _height_context(70.0, 66.0) == "shorter"
    assert _height_context(70.0, 70.5) is None      # inside 1-inch band
    assert _height_context(70.0, np.nan) is None


def test_empty_history_all_zero():
    feats = stance_height_matchup_features(
        pd.DataFrame(), pd.DataFrame(),
        "orthodox", "southpaw", 70.0, 74.0, REF, BIOS,
    )
    assert set(feats) == EXPECTED_KEYS
    assert feats["height_diff"] == -4.0
    assert feats["open_stance_height_diff"] == -4.0
    for k in feats:
        if "edge" in k or "combo" in k:
            assert feats[k] == 0.0


def test_open_stance_specialist_gets_positive_edge():
    # A dominates southpaws (net +20/15min) but only breaks even vs orthodox.
    a_hist = _hist([
        {"opponent_id": "south_even", "sig_strikes_landed": 60, "opp_sig_strikes_landed": 40},
        {"opponent_id": "south_even", "sig_strikes_landed": 60, "opp_sig_strikes_landed": 40},
        {"opponent_id": "orth_short", "sig_strikes_landed": 40, "opp_sig_strikes_landed": 40,
         "winner": False},
        {"opponent_id": "orth_short", "sig_strikes_landed": 40, "opp_sig_strikes_landed": 40,
         "winner": False},
    ])
    # Current fight is an open-stance pairing → A's open bucket applies.
    feats = stance_height_matchup_features(
        a_hist, pd.DataFrame(),
        "orthodox", "southpaw", 70.0, 70.0, REF, BIOS,
    )
    assert feats["stance_ctx_strike_edge_a"] > 0.0
    assert feats["stance_ctx_strike_edge_b"] == 0.0
    assert feats["stance_ctx_strike_edge_diff"] == pytest.approx(
        feats["stance_ctx_strike_edge_a"]
    )
    # Closed-stance current fight flips to the (worse) closed bucket.
    feats_closed = stance_height_matchup_features(
        a_hist, pd.DataFrame(),
        "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
    )
    assert feats_closed["stance_ctx_strike_edge_a"] < 0.0
    assert feats_closed["open_stance_height_diff"] == 0.0


def test_height_context_uses_each_fighters_own_perspective():
    # A (70in) struggles vs taller opponents.
    a_hist = _hist([
        {"opponent_id": "orth_tall", "sig_strikes_landed": 20,
         "opp_sig_strikes_landed": 50, "winner": False},
        {"opponent_id": "orth_tall", "sig_strikes_landed": 20,
         "opp_sig_strikes_landed": 50, "winner": False},
        {"opponent_id": "orth_short", "sig_strikes_landed": 60,
         "opp_sig_strikes_landed": 20},
    ])
    # Current opponent B is 74in → taller → A's vs-taller bucket (negative edge).
    feats = stance_height_matchup_features(
        a_hist, pd.DataFrame(),
        "orthodox", "orthodox", 70.0, 74.0, REF, BIOS,
    )
    assert feats["height_ctx_strike_edge_a"] < 0.0
    # Same history but a shorter current opponent → vs-shorter bucket (positive).
    feats2 = stance_height_matchup_features(
        a_hist, pd.DataFrame(),
        "orthodox", "orthodox", 70.0, 66.0, REF, BIOS,
    )
    assert feats2["height_ctx_strike_edge_a"] > 0.0


def test_shrinkage_scales_with_rounds_of_evidence():
    one = _hist([
        {"opponent_id": "south_even", "sig_strikes_landed": 80, "opp_sig_strikes_landed": 20},
        {"opponent_id": "orth_short", "sig_strikes_landed": 40, "opp_sig_strikes_landed": 40},
    ])
    many = _hist(
        [{"opponent_id": "south_even", "sig_strikes_landed": 80,
          "opp_sig_strikes_landed": 20}] * 10
        + [{"opponent_id": "orth_short", "sig_strikes_landed": 40,
            "opp_sig_strikes_landed": 40}] * 10
    )
    f_one = stance_height_matchup_features(
        one, pd.DataFrame(), "orthodox", "southpaw", 70.0, 70.0, REF, BIOS)
    f_many = stance_height_matchup_features(
        many, pd.DataFrame(), "orthodox", "southpaw", 70.0, 70.0, REF, BIOS)
    assert 0.0 < f_one["stance_ctx_strike_edge_a"] < f_many["stance_ctx_strike_edge_a"]


def test_switch_fighter_neutralizes_stance_context_only():
    a_hist = _hist([
        {"opponent_id": "orth_tall", "sig_strikes_landed": 20,
         "opp_sig_strikes_landed": 50, "winner": False},
        {"opponent_id": "orth_short", "sig_strikes_landed": 60,
         "opp_sig_strikes_landed": 20},
    ])
    feats = stance_height_matchup_features(
        a_hist, pd.DataFrame(),
        "switch", "orthodox", 70.0, 74.0, REF, BIOS,
    )
    assert feats["stance_ctx_strike_edge_a"] == 0.0
    assert feats["stance_ctx_win_edge_diff"] == 0.0
    assert feats["open_stance_height_diff"] == 0.0
    # Height layer still fires — it does not depend on stance.
    assert feats["height_ctx_strike_edge_a"] < 0.0


ADAPT_KEYS = {
    "stance_sens_a", "stance_sens_b", "height_sens_a", "height_sens_b",
    "style_sens_a", "style_sens_b",
    "adaptability_a", "adaptability_b", "adaptability_diff",
    "style_ctx_edge_a", "style_ctx_edge_b", "style_ctx_edge_diff",
}

NEUTRAL_STATS = {"slpm": 3.0, "td15": 0.0}


def test_adaptability_empty_history_is_neutral():
    feats = adaptability_features(
        pd.DataFrame(), pd.DataFrame(),
        "orthodox", "southpaw", 70.0, 74.0, REF, BIOS,
        NEUTRAL_STATS, NEUTRAL_STATS,
    )
    assert set(feats) == ADAPT_KEYS
    for v in feats.values():
        assert v == 0.0


def test_context_sensitive_fighter_scores_lower_adaptability():
    # Sensitive: dominates southpaws, collapses vs orthodox.
    sensitive = _hist(
        [{"opponent_id": "south_even", "sig_strikes_landed": 80,
          "opp_sig_strikes_landed": 20}] * 5
        + [{"opponent_id": "orth_short", "sig_strikes_landed": 20,
            "opp_sig_strikes_landed": 80, "winner": False}] * 5
    )
    # Adaptable: identical output in both pairings.
    adaptable = _hist(
        [{"opponent_id": "south_even", "sig_strikes_landed": 50,
          "opp_sig_strikes_landed": 30}] * 5
        + [{"opponent_id": "orth_short", "sig_strikes_landed": 50,
            "opp_sig_strikes_landed": 30}] * 5
    )
    f = adaptability_features(
        sensitive, adaptable, "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
        NEUTRAL_STATS, NEUTRAL_STATS,
    )
    assert f["stance_sens_a"] > f["stance_sens_b"]
    assert f["stance_sens_b"] == pytest.approx(0.0, abs=1e-9)
    assert f["adaptability_a"] < f["adaptability_b"]
    assert f["adaptability_diff"] < 0.0


def test_style_ctx_edge_tracks_current_opponent_class():
    # A eats volume strikers alive but struggles in low-output fights.
    a_hist = _hist(
        [{"opponent_id": "orth_short", "sig_strikes_landed": 70,
          "opp_sig_strikes_landed": 75}] * 5      # opp 5.0/min → high volume
        + [{"opponent_id": "orth_short", "sig_strikes_landed": 30,
            "opp_sig_strikes_landed": 40, "winner": False}] * 5  # 2.7/min → low
    )
    vs_volume = adaptability_features(
        a_hist, pd.DataFrame(), "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
        NEUTRAL_STATS, {"slpm": 6.0, "td15": 0.0},   # B is a volume striker
    )
    vs_low = adaptability_features(
        a_hist, pd.DataFrame(), "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
        NEUTRAL_STATS, {"slpm": 2.0, "td15": 0.0},   # B is low output
    )
    assert vs_volume["style_ctx_edge_a"] > vs_low["style_ctx_edge_a"]
    # Style sensitivity is symmetric evidence — same either way.
    assert vs_volume["style_sens_a"] == pytest.approx(vs_low["style_sens_a"])
    assert vs_volume["style_sens_a"] > 0.0


def test_grappling_context_from_takedowns():
    # A's striking holds up fine vs strikers, degrades in grappling-heavy fights.
    a_hist = _hist(
        [{"opponent_id": "orth_short", "sig_strikes_landed": 60,
          "opp_sig_strikes_landed": 20, "opp_takedowns_landed": 0}] * 4
        + [{"opponent_id": "orth_short", "sig_strikes_landed": 20,
            "opp_sig_strikes_landed": 30, "opp_takedowns_landed": 4,
            "winner": False}] * 4
    )
    vs_grappler = adaptability_features(
        a_hist, pd.DataFrame(), "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
        NEUTRAL_STATS, {"slpm": 2.0, "td15": 3.0},
    )
    vs_striker = adaptability_features(
        a_hist, pd.DataFrame(), "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
        NEUTRAL_STATS, {"slpm": 2.0, "td15": 0.0},
    )
    assert vs_grappler["style_ctx_edge_a"] < vs_striker["style_ctx_edge_a"]


def test_range_vs_clinch_striking_style_axis():
    # A handles rangey fights fine but gets mauled in clinch-heavy fights.
    a_hist = _hist(
        [{"opponent_id": "orth_short", "sig_strikes_landed": 55,
          "opp_sig_strikes_landed": 40, "opp_clinch_landed": 2.0,
          "opp_leg_landed": 4.0}] * 4          # 5% clinch → range fight
        + [{"opponent_id": "orth_short", "sig_strikes_landed": 20,
            "opp_sig_strikes_landed": 45, "opp_clinch_landed": 20.0,
            "opp_leg_landed": 4.0, "winner": False}] * 4  # 44% clinch
    )
    # Current opponent B: dirty boxer / Muay Thai profile — high clinch share.
    clinch_b_hist = _hist(
        [{"opponent_id": "orth_short", "sig_strikes_landed": 40,
          "clinch_landed": 16.0, "leg_landed": 3.0}] * 3
    )
    # Current opponent B: rangey point fighter — distance, kicks, low clinch.
    rangey_b_hist = _hist(
        [{"opponent_id": "orth_short", "sig_strikes_landed": 40,
          "clinch_landed": 2.0, "leg_landed": 14.0}] * 3
    )
    vs_clinch = adaptability_features(
        a_hist, clinch_b_hist, "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
        NEUTRAL_STATS, NEUTRAL_STATS,
    )
    vs_rangey = adaptability_features(
        a_hist, rangey_b_hist, "orthodox", "orthodox", 70.0, 70.0, REF, BIOS,
        NEUTRAL_STATS, NEUTRAL_STATS,
    )
    assert vs_clinch["style_ctx_edge_a"] < vs_rangey["style_ctx_edge_a"]
    assert vs_clinch["style_sens_a"] > 0.0


def test_build_feature_row_emits_new_columns():
    from src.features.build_matrix import build_feature_row
    from src.features.elo import MMAElo

    bios = {
        "A": {"name": "A", "height_in": 70.0, "reach_in": 72.0,
              "stance": "orthodox", "dob": None},
        "B": {"name": "B", "height_in": 74.0, "reach_in": 76.0,
              "stance": "southpaw", "dob": None},
    }
    row = build_feature_row(
        "A", "B", REF, {"A": pd.DataFrame(), "B": pd.DataFrame()},
        MMAElo(), bios, weight_class="Lightweight",
    )
    assert EXPECTED_KEYS <= set(row)
    assert row["height_diff"] == -4.0
    assert row["open_stance_height_diff"] == -4.0
    for k in EXPECTED_KEYS:
        assert np.isfinite(row[k])

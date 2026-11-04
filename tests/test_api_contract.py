"""Contract tests for the public prediction API surface.

These tests need NO local data artifacts: they cover the facade's import
surface, the frozen `FightPrediction` field set (the frozen API contract),
and the rendering helpers on a synthetically constructed dataclass instance.
End-to-end tests that call `predict_fight` against the real bundle live in
tests/test_features_and_api.py behind data-existence guards.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from src.api.predict_fight import FightPrediction, _load_state, predict_fight

# Field names are frozen: the public API contract.
FROZEN_FIELD_NAMES = {
    "fighter_a",
    "fighter_b",
    "event_date",
    "winner_prob",
    "method_prob",
    "round_estimate",
    "confidence",
    "top_drivers",
    "cluster_matchup",
    "warnings",
    "fighter_a_id",
    "fighter_b_id",
    "weight_class",
    "event_name",
    "confidence_spread",
    "ensemble_streams",
    "key_advantages_a",
    "key_advantages_b",
    "finish_round_dist",
    "n_similar_fights",
    "cluster_a",
    "cluster_b",
}


# --- 1. Facade import surface ------------------------------------------------


def test_facade_exports_public_contract():
    """`from src.api.predict_fight import predict_fight, FightPrediction, _load_state`."""
    assert callable(predict_fight)
    assert callable(_load_state)
    assert dataclasses.is_dataclass(FightPrediction)


def test_facade_reexports_names_used_by_scripts():
    """Every name external scripts import from the facade must stay importable."""
    import src.api.predict_fight as pf_mod

    # scripts/events/figgy_sub.py, sergei_check.py, predict_kape_horiguchi.py,
    # find_names.py, check_baku_names.py, verify_last4.py, backtest_2026_events.py
    for name in (
        "predict_fight",
        "FightPrediction",
        "_load_state",
        "_resolve_fighter_id",
        "_build_feature_row_for_pair",
    ):
        assert hasattr(pf_mod, name), f"facade lost re-export: {name}"

    # Everything declared re-exported must actually resolve.
    for name in pf_mod.__all__:
        assert hasattr(pf_mod, name), f"__all__ lists missing name: {name}"


# --- 2. FightPrediction field names frozen ------------------------------------


def test_fightprediction_field_names_frozen():
    actual = {f.name for f in dataclasses.fields(FightPrediction)}
    assert actual == FROZEN_FIELD_NAMES


# --- 3. Rendering on a synthetic instance -------------------------------------


def _synthetic_prediction() -> FightPrediction:
    return FightPrediction(
        fighter_a="Aiko Tanaka",
        fighter_b="Bruno Silva",
        event_date=date(2026, 1, 24),
        winner_prob={"a": 0.64, "b": 0.36},
        method_prob={"Decision": 0.5, "KO/TKO": 0.3, "Submission": 0.2},
        round_estimate=(1, 2),
        confidence="medium",
        top_drivers=["Elo rating (25 Elo points)"],
        cluster_matchup="",
        warnings=["Low-confidence call — model says coinflip-adjacent."],
        fighter_a_id="id-a",
        fighter_b_id="id-b",
        weight_class="Lightweight",
        event_name="UFC Test Night",
        confidence_spread=0.08,
        ensemble_streams={"logreg": 0.60, "xgb": 0.68, "elo": 0.62},
        key_advantages_a=["Takedown rate (diff +1.10)"],
        key_advantages_b=["Reach (diff +2.00)"],
        finish_round_dist={
            "round_1": 0.20,
            "round_2": 0.15,
            "round_3": 0.075,
            "round_4": 0.05,
            "round_5": 0.025,
            "decision": 0.50,
        },
        n_similar_fights=123,
        cluster_a="",
        cluster_b="",
    )


def test_to_markdown_synthetic_card():
    md = _synthetic_prediction().to_markdown()
    lines = md.split("\n")

    assert "  Aiko Tanaka vs. Bruno Silva" in lines
    assert "  UFC Test Night · Lightweight · 2026-01-24" in lines
    assert "  WHO WINS?" in lines

    # Probability rows: 0.64 * 24 → 15 filled cells; 0.36 * 24 → 9 filled cells.
    (row_a,) = [ln for ln in lines if ln.startswith("  Aiko Tanaka ") and "█" in ln]
    assert "█" * 15 + "░" * 9 in row_a
    assert row_a.endswith("64%")
    (row_b,) = [ln for ln in lines if ln.startswith("  Bruno Silva ") and "█" in ln]
    assert "█" * 9 + "░" * 15 in row_b
    assert row_b.endswith("36%")

    assert "  Confidence: MEDIUM  (ensemble spread: ±8 pp)" in lines

    # Top-4 outcomes: Tanaka Dec .32, Tanaka KO .192, Silva Dec .18, Tanaka Sub .128.
    assert any("1. Tanaka by Decision" in ln and "32%" in ln for ln in lines)
    assert any("2. Tanaka by KO/TKO" in ln and "19%" in ln for ln in lines)
    assert any("3. Silva by Decision" in ln and "18%" in ln for ln in lines)
    assert any("4. Tanaka by Submission" in ln and "13%" in ln for ln in lines)
    assert "  IF FINISHED — Decision (50%)" in lines

    assert "  WHY IS AIKO TANAKA FAVOURED?" in lines
    assert "    • Takedown rate (diff +1.10)" in lines
    assert "  WARNINGS" in lines
    assert "    ⚠ Low-confidence call — model says coinflip-adjacent." in lines
    assert (
        "  Model uncertainty: medium  |  n similar fights in training: 123" in lines
    )
    assert "  Not betting advice. This model is wrong ~40% of the time." in lines


def test_to_dict_synthetic():
    p = _synthetic_prediction()
    d = p.to_dict()

    assert d["fighter_a"] == "Aiko Tanaka"
    assert d["fighter_b"] == "Bruno Silva"
    assert d["fighter_a_id"] == "id-a"
    assert d["fighter_b_id"] == "id-b"
    assert d["event_date"] == "2026-01-24"
    assert d["event_name"] == "UFC Test Night"
    assert d["weight_class"] == "Lightweight"
    assert d["winner_prob"] == {"a": 0.64, "b": 0.36}
    assert d["round_estimate"] == [1, 2]
    assert d["confidence"] == "medium"
    assert d["confidence_spread"] == 0.08
    assert d["n_similar_fights"] == 123

    outcomes = d["top_outcomes"]
    assert len(outcomes) == 4
    assert [o["label"] for o in outcomes] == [
        "Tanaka by Decision",
        "Tanaka by KO/TKO",
        "Silva by Decision",
        "Tanaka by Submission",
    ]
    assert outcomes[0]["prob"] == pytest.approx(0.32)

    expected_keys = {
        "fighter_a", "fighter_b", "fighter_a_id", "fighter_b_id", "event_date",
        "event_name", "weight_class", "winner_prob", "method_prob", "top_outcomes",
        "round_estimate", "confidence", "confidence_spread", "ensemble_streams",
        "top_drivers", "key_advantages_a", "key_advantages_b", "warnings",
        "cluster_matchup", "cluster_a", "cluster_b", "finish_round_dist",
        "n_similar_fights",
    }
    assert set(d.keys()) == expected_keys


def test_to_dict_none_round_estimate_serialises_to_none():
    p = _synthetic_prediction()
    p.round_estimate = None
    assert p.to_dict()["round_estimate"] is None


# --- 4. Static helper unit behavior -------------------------------------------


def test_compute_top_outcomes_ranking_and_probs():
    outcomes = FightPrediction._compute_top_outcomes(
        0.7,
        {"Decision": 0.5, "KO/TKO": 0.3, "Submission": 0.2},
        "Aiko Tanaka",
        "Bruno Silva",
        top_n=6,
    )
    assert len(outcomes) == 6
    probs = [o["prob"] for o in outcomes]
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) == pytest.approx(1.0)
    assert outcomes[0] == {
        "fighter": "Aiko Tanaka",
        "method": "Decision",
        "prob": pytest.approx(0.35),
        "label": "Tanaka by Decision",
    }


def test_compute_top_outcomes_top_n_and_mononym_label():
    outcomes = FightPrediction._compute_top_outcomes(
        0.5,
        {"Decision": 0.6, "KO/TKO": 0.3, "Submission": 0.1},
        "Shogun",
        "Bruno Silva",
    )
    assert len(outcomes) == 4  # default top_n
    labels = {o["label"] for o in outcomes}
    assert "Shogun by Decision" in labels  # mononym keeps the full name


def test_compute_top_outcomes_accepts_lowercase_method_keys():
    outcomes = FightPrediction._compute_top_outcomes(
        0.9, {"decision": 0.2, "ko": 0.7, "submission": 0.1}, "A A", "B B", top_n=1
    )
    assert outcomes[0]["label"] == "A by KO/TKO"
    assert outcomes[0]["prob"] == pytest.approx(0.63)


def test_render_probability_bar_fill_and_clamp():
    bar = FightPrediction._render_probability_bar
    assert bar(0.0) == "░" * 24
    assert bar(1.0) == "█" * 24
    assert bar(0.5) == "█" * 12 + "░" * 12
    # Out-of-range inputs clamp rather than raise.
    assert bar(-0.3) == "░" * 24
    assert bar(1.7) == "█" * 24
    # Custom width.
    assert bar(0.5, width=10) == "█" * 5 + "░" * 5
    assert len(bar(0.37)) == 24


def test_classify_confidence_thresholds():
    clf = FightPrediction._classify_confidence
    assert clf(0.0) == "high"
    assert clf(0.04) == "high"  # boundary is inclusive
    assert clf(0.041) == "medium"
    assert clf(0.10) == "medium"  # boundary is inclusive
    assert clf(0.101) == "low"
    assert clf(0.5) == "low"

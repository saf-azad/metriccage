"""Public prediction interface.

Loads the trained ensemble and any required state (Elo store, GMM, calibrator)
on import; subsequent calls are fast. The function signature is the contract
every consumer (CLI, notebook, future web UI) depends on.

EXAMPLE
    from datetime import date
    from src.api.predict_fight import predict_fight
    p = predict_fight("Islam Makhachev", "Charles Oliveira", date(2025, 4, 12))
    print(p.to_markdown())

DESIGN
    The first call to `predict_fight` is responsible for warming the cache:
        1. Load data/processed/final_model_bundle.pkl
        2. Load data/interim/fights.parquet + fighters.parquet
        3. Replay the Elo state up to "now" and per-fighter histories
        4. Cache everything in module-level state for subsequent calls
    Re-loading is automatic if the underlying file mtimes change (handy when
    train_all.py rewrites the bundle while a notebook is open).

    This module is a thin facade: the implementation is decomposed into
        src/api/types.py     — FightPrediction dataclass + rendering helpers
        src/api/loading.py   — bundle/data loading, `_State`, name resolution
        src/api/assembly.py  — feature assembly, stream scoring, blending,
                               method/round/driver/warning builders
    Every previously module-level name is re-exported below so existing
    consumers (scripts/, tests/) keep working unchanged.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.api.assembly import (
    _blend,
    _build_drivers,
    _build_feature_row_for_pair,
    _build_streams_for_row,
    _build_warnings,
    _confidence,
    _method_distribution,
    _n_similar_fights,
    _round_distribution,
    _round_estimate,
    _score_lstm_row,
)
from src.api.loading import (
    _BUNDLE_PATH,
    _CLUSTER_PATH,
    _FEATURE_MATRIX_PATH,
    _FIGHTERS_PATH,
    _FIGHTS_PATH_ENRICHED,
    _FIGHTS_PATH_V1,
    _HAS_TORCH,
    _fights_path,
    _load_state,
    _resolve_fighter_id,
    _State,
    _state,
)
from src.api.types import (
    _FEATURE_LABELS,
    Confidence,
    FightPrediction,
    _humanise,
)

__all__ = [
    # Public contract
    "predict_fight",
    "FightPrediction",
    "Confidence",
    # Loading / state (used by scripts/events/*, scripts/backtest_2026_events.py)
    "_State",
    "_state",
    "_load_state",
    "_fights_path",
    "_resolve_fighter_id",
    "_HAS_TORCH",
    "_BUNDLE_PATH",
    "_CLUSTER_PATH",
    "_FIGHTS_PATH_V1",
    "_FIGHTS_PATH_ENRICHED",
    "_FIGHTERS_PATH",
    "_FEATURE_MATRIX_PATH",
    # Assembly helpers
    "_build_feature_row_for_pair",
    "_score_lstm_row",
    "_build_streams_for_row",
    "_blend",
    "_method_distribution",
    "_round_distribution",
    "_round_estimate",
    "_confidence",
    "_build_drivers",
    "_build_warnings",
    "_n_similar_fights",
    # Rendering helpers
    "_FEATURE_LABELS",
    "_humanise",
]


# --- Public entry point -----------------------------------------------------


def predict_fight(
    fighter_a: str,
    fighter_b: str,
    event_date: date,
    *,
    include_odds: bool = False,
    event_name: str = "",
    weight_class: str = "",
) -> FightPrediction:
    """Top-level entry point. See docs/PLAN.md §8."""
    state = _load_state()

    a_id = _resolve_fighter_id(fighter_a, state)
    b_id = _resolve_fighter_id(fighter_b, state)

    row, a_hist, b_hist = _build_feature_row_for_pair(
        a_id, b_id, event_date, state, weight_class=weight_class or ""
    )
    streams = _build_streams_for_row(row, state)
    p_a = _blend(streams, state)
    confidence, spread = _confidence(streams)

    method_probs = _method_distribution(a_hist, b_hist, p_a, state, row=row)
    round_dist = _round_distribution(method_probs)
    rest = _round_estimate(round_dist)

    drivers, a_advs, b_advs = _build_drivers(row, p_a, state)
    warnings = _build_warnings(streams, a_hist, b_hist, method_probs, p_a, confidence)

    # Try to count similar training fights (cheap context).
    matrix = None
    if _FEATURE_MATRIX_PATH.exists():
        try:
            matrix = pd.read_parquet(_FEATURE_MATRIX_PATH)
        except Exception:
            matrix = None
    n_similar = _n_similar_fights(matrix, row)

    # Pull display names back out of the bio lookup if available.
    bio = state.bio_lookup or {}
    a_name = bio.get(a_id, {}).get("name") or fighter_a
    b_name = bio.get(b_id, {}).get("name") or fighter_b
    wc = weight_class or (row["weight_class"].iloc[0] if "weight_class" in row.columns else "")

    return FightPrediction(
        fighter_a=a_name,
        fighter_b=b_name,
        fighter_a_id=a_id,
        fighter_b_id=b_id,
        event_date=event_date,
        winner_prob={"a": float(p_a), "b": float(1 - p_a)},
        method_prob=method_probs,
        round_estimate=rest,
        confidence=confidence,
        confidence_spread=float(spread),
        ensemble_streams={k: float(v) for k, v in streams.items()},
        top_drivers=drivers,
        key_advantages_a=a_advs,
        key_advantages_b=b_advs,
        finish_round_dist=round_dist,
        warnings=warnings,
        weight_class=str(wc) if wc else "",
        event_name=event_name,
        n_similar_fights=n_similar,
    )

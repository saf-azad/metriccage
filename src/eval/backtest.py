"""Event-by-event blind backtest.

For each event in the test period: train on everything strictly before that
event, predict the event, score, accumulate. This is the deployment
simulation — the numbers it produces are what we report.

The walk-forward structure (chronological event loop, predict-then-absorb
ordering) is ported from ``scripts/backtest_2026_events.py`` into a reusable,
dependency-injected function: the prediction logic is supplied by the caller
as a ``model_factory``, so tests can use a stub and the production run can
wrap ``src.api.predict_fight`` (see :func:`api_model_factory`).

Importing this module never loads data files or model bundles.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

import numpy as np
import pandas as pd

from src.eval.metrics import brier as _brier
from src.eval.metrics import logloss as _logloss


def _clean_str(val: Any) -> str:
    """str(val) with None/NaN normalised to '' (np.nan is truthy, so `val or ''`
    would stringify to 'nan')."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return str(val)

# A predictor maps one fight row (a pd.Series from the fights frame) to a
# mapping with at least {"p_a": float}; optional keys: "method_probs"
# (dict method -> prob) and "confidence" (str bucket, e.g. "high").
Predictor = Callable[[pd.Series], Mapping[str, Any]]
# A model factory receives ALL fights strictly before the current event's
# date (including warm-up fights before start_date) and returns a predictor.
# It is invoked once per event, so the training view expands event by event.
ModelFactory = Callable[[pd.DataFrame], Predictor]
DateLike: TypeAlias = str | dt.date | dt.datetime | pd.Timestamp

_METHOD_RANK_DEFAULT = 3  # model output space is {Decision, KO/TKO, Submission}


@dataclass(frozen=True)
class BacktestResult:
    """Return type of :func:`run_backtest`.

    Attributes
    ----------
    per_fight : tidy DataFrame, one row per fight in [start_date, end_date]
        (scored rows plus rows whose predictor call failed, flagged in the
        ``error`` column).
    summary : aggregate metrics dict — see :func:`run_backtest`.

    Supports tuple unpacking: ``per_fight, summary = run_backtest(...)``.
    """

    per_fight: pd.DataFrame
    summary: dict[str, Any]

    def __iter__(self) -> Iterator[Any]:
        return iter((self.per_fight, self.summary))


def api_model_factory(train_fights: pd.DataFrame) -> Predictor:
    """Default production predictor: wraps ``src.api.predict_fight``.

    Imports lazily so that importing ``src.eval.backtest`` stays cheap and
    data-free; the bundle/data load happens on the first prediction.

    ``train_fights`` is ignored: the production API threads ``event_date``
    (as-of) through every feature function itself (shared contract #4), so no
    per-event refit is needed. Note it does NOT replay Elo/history beyond its
    cached state the way ``scripts/backtest_2026_events.py`` does — for a
    strict replay against events newer than the cached state, use that
    script's ``_replay_elo_and_history``.

    Expects canonical column names on each fight row: ``fighter_a_name``,
    ``fighter_b_name``, ``event_date`` and optionally ``weight_class``.
    """
    del train_fights  # as-of correctness is handled inside the API
    from src.api.predict_fight import predict_fight  # lazy: loads bundle + data

    def _predict(fight: pd.Series) -> dict[str, Any]:
        pred = predict_fight(
            str(fight["fighter_a_name"]),
            str(fight["fighter_b_name"]),
            pd.Timestamp(fight["event_date"]).date(),
            weight_class=_clean_str(fight.get("weight_class")),
        )
        return {
            "p_a": float(pred.winner_prob.get("a", 0.5)),
            "method_probs": dict(pred.method_prob or {}),
            "confidence": str(pred.confidence or ""),
        }

    return _predict


def _method_rank(method_probs: Mapping[str, Any], actual: str) -> int:
    """1-based rank of the actual method in the predicted distribution.

    Ported from scripts/backtest_2026_events.py: missing/unmatched -> 3
    (worst rank in the 3-class method space).
    """
    if not method_probs:
        return _METHOD_RANK_DEFAULT
    ranked = sorted(method_probs.items(), key=lambda kv: -float(kv[1] or 0))
    for i, (m, _) in enumerate(ranked):
        if m.lower() == actual.lower():
            return i + 1
    return _METHOD_RANK_DEFAULT


def _fallback_confidence(p_a: float) -> str:
    """Confidence bucket from win prob, used only when the predictor supplies
    none. (The production API derives confidence from ensemble stream spread
    instead — predictors that care should report their own.)"""
    edge = abs(p_a - 0.5)
    if edge >= 0.15:
        return "high"
    if edge >= 0.07:
        return "medium"
    return "low"


def _summarise(rows: list[dict[str, Any]], n_events: int) -> dict[str, Any]:
    scored = [r for r in rows if r.get("error") is None]
    n = len(scored)
    summary: dict[str, Any] = {
        "n_events": n_events,
        "n_fights": n,
        "n_errors": len(rows) - n,
        "winners_correct": int(sum(r["winner_correct"] for r in scored)),
        "accuracy": float("nan"),
        "brier": float("nan"),
        "logloss": float("nan"),
        "by_confidence": {},
        "method_top1": 0,
        "method_top1_accuracy": float("nan"),
        "method_mean_rank": float("nan"),
    }
    if n == 0:
        return summary

    y = np.array([1.0 if r["actual_winner"] == "a" else 0.0 for r in scored])
    p = np.array([r["p_a"] for r in scored], dtype=float)
    summary["accuracy"] = summary["winners_correct"] / n
    summary["brier"] = _brier(y, p)
    summary["logloss"] = _logloss(y, np.clip(p, 1e-6, 1 - 1e-6))

    by_conf: dict[str, dict[str, Any]] = {}
    for r in scored:
        bucket = by_conf.setdefault(r["confidence"], {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += int(r["winner_correct"])
    for bucket in by_conf.values():
        bucket["accuracy"] = bucket["correct"] / bucket["n"]
    summary["by_confidence"] = by_conf

    method_rows = [r for r in scored if r["method_rank_actual"] is not None]
    if method_rows:
        top1 = sum(int(r["method_top1"]) for r in method_rows)
        summary["method_top1"] = int(top1)
        summary["method_top1_accuracy"] = top1 / len(method_rows)
        summary["method_mean_rank"] = float(
            np.mean([r["method_rank_actual"] for r in method_rows])
        )
    return summary


def run_backtest(
    fights: pd.DataFrame,
    model_factory: ModelFactory,
    start_date: DateLike,
    end_date: DateLike,
    *,
    date_col: str = "event_date",
    event_col: str = "event_name",
    label_col: str = "fighter_a_won",
    method_col: str = "method",
) -> BacktestResult:
    """Walk event-by-event through [start_date, end_date] and score blind picks.

    For each event (chronologically): ``model_factory`` is called with every
    fight strictly *before* the event's date — never same-day, never future —
    and the returned predictor is applied to each of the event's fights. Only
    after an event is fully predicted do its fights enter the training view of
    subsequent events (predict-then-absorb, as in
    ``scripts/backtest_2026_events.py``). Fights before ``start_date`` are
    never predicted but do serve as warm-up training context.

    Parameters
    ----------
    fights : one row per fight. Required columns: ``date_col`` and
        ``label_col`` (1 if fighter_a won, else 0). Optional: ``event_col``
        (falls back to grouping by date alone), ``method_col`` (enables method
        scoring; "DQ" is folded into "Decision"), ``fighter_a_name`` /
        ``fighter_b_name`` (carried into the output when present).
    model_factory : see :data:`ModelFactory`. Use :func:`api_model_factory`
        for the production pipeline; inject a stub for tests.
    start_date, end_date : inclusive bounds of the evaluation window.

    Returns
    -------
    BacktestResult — ``per_fight`` tidy DataFrame (one row per fight, with
    ``p_a``, ``predicted_winner``, ``actual_winner``, ``winner_correct``,
    ``confidence``, method columns and an ``error`` column for fights whose
    predictor call raised) and a ``summary`` dict with keys ``n_events``,
    ``n_fights``, ``n_errors``, ``winners_correct``, ``accuracy``, ``brier``,
    ``logloss``, ``by_confidence`` ({bucket: {n, correct, accuracy}}),
    ``method_top1``, ``method_top1_accuracy``, ``method_mean_rank``,
    ``start_date``, ``end_date``. Metrics are NaN when nothing was scored.
    Supports ``df, summary = run_backtest(...)``.
    """
    for col in (date_col, label_col):
        if col not in fights.columns:
            raise ValueError(f"fights is missing required column {col!r}")
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    if start_ts > end_ts:
        raise ValueError(f"start_date {start_ts.date()} is after end_date {end_ts.date()}")

    fights = fights.copy()
    fights[date_col] = pd.to_datetime(fights[date_col])
    if fights[date_col].isna().any():
        raise ValueError(f"{date_col!r} contains NaT/unparseable dates")
    fights = fights.sort_values(date_col, kind="stable")

    in_window = fights[(fights[date_col] >= start_ts) & (fights[date_col] <= end_ts)]
    group_keys = [date_col, event_col] if event_col in in_window.columns else [date_col]
    events = list(in_window.groupby(group_keys, sort=True))

    rows: list[dict[str, Any]] = []
    for key, group in events:
        ev_date = key[0] if isinstance(key, tuple) else key
        ev_name = str(key[1]) if isinstance(key, tuple) and len(key) > 1 else ""
        # Strictly-prior state only: no same-day, no future fights.
        train_view = fights[fights[date_col] < ev_date]
        predictor = model_factory(train_view)

        for _, fight in group.iterrows():
            row: dict[str, Any] = {
                "event_date": pd.Timestamp(ev_date).date(),
                "event_name": ev_name,
                "fighter_a": _clean_str(fight.get("fighter_a_name")),
                "fighter_b": _clean_str(fight.get("fighter_b_name")),
                "error": None,
            }
            actual_winner = "a" if int(fight[label_col]) == 1 else "b"
            actual_method = _clean_str(fight.get(method_col)) if method_col in fights else ""
            if actual_method == "DQ":
                # Model method space is {Decision, KO/TKO, Submission}.
                actual_method = "Decision"
            try:
                pred = predictor(fight)
                p_a = float(pred["p_a"])
                predicted_winner = "a" if p_a >= 0.5 else "b"
                method_probs = dict(pred.get("method_probs") or {})
                confidence = str(pred.get("confidence") or "") or _fallback_confidence(p_a)

                row.update(
                    {
                        "p_a": p_a,
                        "predicted_winner": predicted_winner,
                        "actual_winner": actual_winner,
                        "winner_correct": predicted_winner == actual_winner,
                        "confidence": confidence,
                        "actual_method": actual_method,
                        "method_pick": (
                            max(method_probs.items(), key=lambda kv: float(kv[1]))[0]
                            if method_probs
                            else ""
                        ),
                    }
                )
                if method_probs and actual_method:
                    rank = _method_rank(method_probs, actual_method)
                    row["method_rank_actual"] = rank
                    row["method_top1"] = rank == 1
                else:
                    row["method_rank_actual"] = None
                    row["method_top1"] = None
            except Exception as exc:  # mirror the script: record the error, keep walking
                row["error"] = f"{type(exc).__name__}: {exc}"
                row["actual_winner"] = actual_winner
            rows.append(row)

    summary = _summarise(rows, n_events=len(events))
    summary["start_date"] = str(start_ts.date())
    summary["end_date"] = str(end_ts.date())
    return BacktestResult(per_fight=pd.DataFrame(rows), summary=summary)

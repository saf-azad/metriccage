"""Backtest the final model against every UFC event in 2026.

The training set ended 2025-05-04 (TEST_END in src.config) and the final 5-yr
retrain explicitly excluded all 2026 fights (EXCLUDE_FROM=2026-01-01 in
scripts/retrain_5yr_with_misses.py), so every 2026 event is a clean holdout.

We replay Elo + per-fighter history chronologically: predict an event using
state strictly *before* its date, then replay that event into Elo/history so
the next event sees the correct as-of state.
"""
from __future__ import annotations

import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.api import predict_fight as pf_mod
from src.api.predict_fight import predict_fight
from src.features.build_matrix import _fight_to_perfighter_rows
from src.features.elo import MMAElo

FIGHTS_PATH = ROOT / "data" / "interim" / "fights.parquet"
MATRIX_PATH = ROOT / "data" / "processed" / "feature_matrix.parquet"
OUT_PATH = ROOT / "data" / "processed" / "backtest_2026_events.json"


def _replay_elo_and_history(fights: pd.DataFrame):
    elo = MMAElo()
    history: dict[str, list[dict]] = defaultdict(list)
    for fight in fights.itertuples(index=False):
        fd = fight._asdict()
        ev = pd.to_datetime(fd["event_date"]).date()
        a_pf, b_pf = _fight_to_perfighter_rows(pd.Series(fd))
        history[fd["fighter_a_id"]].append(a_pf)
        history[fd["fighter_b_id"]].append(b_pf)
        winner = fd.get("winner_id")
        if winner and winner in {fd["fighter_a_id"], fd["fighter_b_id"]}:
            loser = (
                fd["fighter_b_id"] if winner == fd["fighter_a_id"] else fd["fighter_a_id"]
            )
            method = fd.get("method_canon") or fd.get("method") or "Decision"
            elo.update(winner, loser, method, ev)
    return elo, dict(history)


def _method_rank(method_probs: dict, actual: str) -> int:
    if not method_probs:
        return 3
    ranked = sorted(method_probs.items(), key=lambda kv: -float(kv[1] or 0))
    for i, (m, _) in enumerate(ranked):
        if m.lower() == actual.lower():
            return i + 1
    return 3


def main() -> None:
    # Raw fights.parquet is used to replay Elo + history (fighter_a is always the
    # winner there — fine for state replay since we only consume winner_id/method).
    fights = pd.read_parquet(FIGHTS_PATH)
    fights["event_date"] = pd.to_datetime(fights["event_date"])
    fights = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    pre_2026 = fights[fights["event_date"].dt.year < 2026]

    # feature_matrix.parquet has the properly randomized (a/b) labels used at
    # training time — that's what we score against to avoid a degenerate target.
    matrix = pd.read_parquet(MATRIX_PATH)
    matrix["event_date"] = pd.to_datetime(matrix["event_date"])
    in_2026 = matrix[matrix["event_date"].dt.year == 2026].sort_values(
        ["event_date", "fight_id"]
    ).copy()
    # event_name lives in fights.parquet, not the matrix — join it back in.
    ev_name_map = (
        fights[["fight_id", "event_name"]].drop_duplicates("fight_id").set_index("fight_id")["event_name"].to_dict()
    )
    in_2026["event_name"] = in_2026["fight_id"].map(ev_name_map).fillna("UFC event")

    print(f"Pre-2026 fights (Elo warmup): {len(pre_2026)}")
    print(f"2026 fights to backtest:      {len(in_2026)}")
    events = list(in_2026.groupby(["event_date", "event_name"], sort=True))
    print(f"2026 events:                  {len(events)}\n")

    # Warm cached state.
    _ = predict_fight  # ensure module imported
    state = pf_mod._load_state()
    state.elo, state.history = _replay_elo_and_history(pre_2026)

    all_results = []
    per_event = []
    tot_n = 0
    tot_w = 0
    tot_m1 = 0
    tot_m2 = 0
    tot_high = 0
    tot_high_correct = 0
    tot_med = 0
    tot_med_correct = 0
    tot_low = 0
    tot_low_correct = 0

    for (ev_date, ev_name), group in events:
        ev_date_only = ev_date.date()
        print(f"{'='*100}")
        print(f"{ev_name}  ({ev_date_only})  — {len(group)} fights")
        print(f"{'-'*100}")
        print(f"{'Fight':<48} {'Pred':<5} {'Act':<5} {'OK?':<4} {'P(A)':<6} "
              f"{'Conf':<7} {'M-pick':<10} {'M-act':<10} {'M✓?':<4}")
        print(f"{'-'*100}")

        ev_n = ev_w = ev_m1 = ev_m2 = 0
        ev_rows = []
        for fight in group.itertuples(index=False):
            fa = fight.fighter_a_name
            fb = fight.fighter_b_name
            wc = getattr(fight, "weight_class", "") or ""
            actual_winner = "a" if int(fight.fighter_a_won) == 1 else "b"
            actual_method = str(getattr(fight, "method", "") or "Decision")
            if actual_method == "DQ":
                # Treat DQ as Decision for top-1 method comparison (model output
                # space is {Decision, KO/TKO, Submission}).
                actual_method = "Decision"

            try:
                p = predict_fight(fa, fb, ev_date_only, weight_class=wc)
                pa = float(p.winner_prob.get("a", 0.5))
                pred_winner = "a" if pa >= 0.5 else "b"
                winner_correct = pred_winner == actual_winner

                method_probs = p.method_prob or {}
                m_rank = _method_rank(method_probs, actual_method)
                top_method = (
                    max(method_probs.items(), key=lambda kv: kv[1])[0]
                    if method_probs else ""
                )
                m1 = m_rank == 1
                m2 = m_rank <= 2
                conf = p.confidence or "unknown"

                ev_n += 1
                ev_w += int(winner_correct)
                ev_m1 += int(m1)
                ev_m2 += int(m2)
                if conf == "high":
                    tot_high += 1
                    tot_high_correct += int(winner_correct)
                elif conf == "medium":
                    tot_med += 1
                    tot_med_correct += int(winner_correct)
                elif conf == "low":
                    tot_low += 1
                    tot_low_correct += int(winner_correct)

                label = f"{fa[:22]} vs {fb[:22]}"
                ok = "OK" if winner_correct else "X"
                m_ok = "OK" if m1 else f"#{m_rank}"
                print(f"{label:<48} {pred_winner.upper():<5} {actual_winner.upper():<5} "
                      f"{ok:<4} {pa*100:>4.0f}%  {conf:<7} {top_method[:8]:<10} "
                      f"{actual_method[:8]:<10} {m_ok:<4}")

                row = {
                    "event_date": str(ev_date_only),
                    "event_name": ev_name,
                    "fighter_a": fa,
                    "fighter_b": fb,
                    "weight_class": wc,
                    "actual_winner": actual_winner,
                    "actual_method": actual_method,
                    "predicted_winner": pred_winner,
                    "p_a": pa,
                    "winner_correct": bool(winner_correct),
                    "method_pick": top_method,
                    "method_rank_actual": m_rank,
                    "method_top1": bool(m1),
                    "method_top2": bool(m2),
                    "confidence": conf,
                }
                ev_rows.append(row)
                all_results.append(row)
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                print(f"{fa[:22]} vs {fb[:22]:<22}  ERROR  {msg}")
                all_results.append({
                    "event_date": str(ev_date_only),
                    "event_name": ev_name,
                    "fighter_a": fa, "fighter_b": fb, "error": msg,
                })

        # Replay this event into Elo/history from the raw fights table (where
        # fighter_a is always the winner — same fights, canonical orientation).
        raw_ev = fights[fights["event_date"].dt.date == ev_date_only]
        for fight in raw_ev.itertuples(index=False):
            fd = fight._asdict()
            ev = pd.to_datetime(fd["event_date"]).date()
            a_pf, b_pf = _fight_to_perfighter_rows(pd.Series(fd))
            state.history.setdefault(fd["fighter_a_id"], []).append(a_pf)
            state.history.setdefault(fd["fighter_b_id"], []).append(b_pf)
            winner = fd.get("winner_id")
            if winner and winner in {fd["fighter_a_id"], fd["fighter_b_id"]}:
                loser = (
                    fd["fighter_b_id"] if winner == fd["fighter_a_id"] else fd["fighter_a_id"]
                )
                method = fd.get("method_canon") or fd.get("method") or "Decision"
                state.elo.update(winner, loser, method, ev)

        if ev_n:
            print(f"{'-'*100}")
            print(f"  Event summary: winners {ev_w}/{ev_n} ({100*ev_w/ev_n:.1f}%)  "
                  f"method top-1 {ev_m1}/{ev_n} ({100*ev_m1/ev_n:.1f}%)  "
                  f"top-2 {ev_m2}/{ev_n} ({100*ev_m2/ev_n:.1f}%)")
        print()
        per_event.append({
            "event_date": str(ev_date_only),
            "event_name": ev_name,
            "n": ev_n,
            "winners_correct": ev_w,
            "method_top1": ev_m1,
            "method_top2": ev_m2,
        })
        tot_n += ev_n
        tot_w += ev_w
        tot_m1 += ev_m1
        tot_m2 += ev_m2

    print(f"\n{'='*100}")
    print("2026 SEASON BACKTEST — final model (out-of-sample)")
    print(f"{'='*100}")
    print(f"  Events:          {len(events)}")
    print(f"  Total fights:    {tot_n}")
    if tot_n:
        print(f"  Winners:         {tot_w}/{tot_n} ({100*tot_w/tot_n:.1f}%)")
        print(f"  Method top-1:    {tot_m1}/{tot_n} ({100*tot_m1/tot_n:.1f}%)")
        print(f"  Method top-2:    {tot_m2}/{tot_n} ({100*tot_m2/tot_n:.1f}%)")
        if tot_high:
            print(f"  HIGH conf:       {tot_high_correct}/{tot_high} "
                  f"({100*tot_high_correct/tot_high:.1f}%)")
        if tot_med:
            print(f"  MEDIUM conf:     {tot_med_correct}/{tot_med} "
                  f"({100*tot_med_correct/tot_med:.1f}%)")
        if tot_low:
            print(f"  LOW conf:        {tot_low_correct}/{tot_low} "
                  f"({100*tot_low_correct/tot_low:.1f}%)")
    print(f"{'='*100}\n")

    OUT_PATH.write_text(json.dumps({
        "summary": {
            "n_events": len(events),
            "n_fights": tot_n,
            "winners_correct": tot_w,
            "winners_pct": (tot_w / tot_n) if tot_n else 0.0,
            "method_top1": tot_m1,
            "method_top1_pct": (tot_m1 / tot_n) if tot_n else 0.0,
            "method_top2": tot_m2,
            "method_top2_pct": (tot_m2 / tot_n) if tot_n else 0.0,
            "high_conf": {"n": tot_high, "correct": tot_high_correct},
            "medium_conf": {"n": tot_med, "correct": tot_med_correct},
            "low_conf": {"n": tot_low, "correct": tot_low_correct},
        },
        "per_event": per_event,
        "fights": all_results,
    }, indent=2, default=str))
    print(f"Saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()

"""Predict every bout on UFC 334: Gane vs. Hokit (2026-11-14, Madison Square Garden).

    PYTHONPATH=. .venv/bin/python scripts/events/ufc334_gane_hokit.py [--bundle PATH] [--out PATH]

Uses fighter state strictly before the event date (Elo and history are replayed
from pre-event fights only, so bouts already finished on the night cannot leak).
Attaches official weigh-in weights from data/processed/ufc334_weighins.json —
the model has no weigh-in input, so these are context, not a model feature.
Writes a JSON payload and prints a summary table.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

EVENT, EVENT_DATE = "UFC 334: Gane vs. Hokit", date(2026, 11, 14)
CARD = [  # (fighter A, fighter B, weight class, card segment)
    ("Ciryl Gane", "Josh Hokit", "Heavyweight", "main"),
    ("Kayla Harrison", "Amanda Nunes", "Women's Bantamweight", "main"),
    ("Caio Borralho", "Yousri Belgaroui", "Middleweight", "main"),
    ("Kevin Holland", "Uros Medic", "Welterweight", "main"),
    ("Luis Gurule", "Bilal Hasan", "Flyweight", "main"),
    ("Stephen Thompson", "Charles Radtke", "Welterweight", "prelim"),
    ("Drew Dober", "Chris Duncan", "Lightweight", "prelim"),
    ("Jim Miller", "Terrance McKinney", "Lightweight", "prelim"),
    ("Cesar Almeida", "Donte Johnson", "Catch Weight", "prelim"),
    ("Jared Gordon", "Melquizael Costa", "Lightweight", "prelim"),
    ("Macy Chiasson", "Bia Mesquita", "Women's Bantamweight", "prelim"),
    ("Alatengheili", "Juan Diaz", "Bantamweight", "prelim"),
    ("Evan Elder", "Samuel Sanches", "Lightweight", "prelim"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=None, help="model bundle to use (default: data/processed)")
    ap.add_argument("--out", default=str(ROOT / "data" / "processed" / "ufc334_predictions.json"))
    args = ap.parse_args()

    from src.api import loading

    if args.bundle:
        loading._BUNDLE_PATH = Path(args.bundle)
    from src.api.predict_fight import predict_fight

    import pandas as pd

    from scripts.backtest_2026_events import _replay_elo_and_history

    state = loading._load_state()
    pre = state.fights[pd.to_datetime(state.fights["event_date"]).dt.date < EVENT_DATE]
    state.elo, state.history = _replay_elo_and_history(pre.sort_values("event_date"))
    wi = json.loads((ROOT / "data" / "processed" / "ufc334_weighins.json").read_text())
    wts, missed = wi["weights_lb"], wi["missed_weight"]

    out = []
    print(f"{EVENT} — {EVENT_DATE}\n")
    print(f"{'Bout':<42}{'Pick':<20}{'P(win)':>7}  {'Conf':<7}{'Dec/KO/Sub':<10} Weigh-in (lb)")
    for a, b, wc, seg in CARD:
        try:
            p = predict_fight(a, b, EVENT_DATE, event_name=EVENT, weight_class=wc)
        except Exception as exc:  # unknown fighter (no UFC history) etc.
            print(f"{a + ' vs ' + b:<42}no prediction — {type(exc).__name__}: {exc}")
            out.append({"fighter_a": a, "fighter_b": b, "segment": seg, "error": str(exc)})
            continue
        d = p.to_dict()
        pa = float(p.winner_prob["a"])
        pick, pw = (a, pa) if pa >= 0.5 else (b, 1 - pa)
        mp = p.method_prob or {}
        ms = "/".join(f"{100 * float(mp.get(k, 0)):.0f}" for k in ("Decision", "KO/TKO", "Submission"))
        print(f"{a + ' vs ' + b:<42}{pick:<20}{pw * 100:>6.1f}%  {p.confidence or '':<7}{ms:<10} {wts.get(a)} v {wts.get(b)}"
              + "".join(f"  [{n} missed by {missed[n]}]" for n in (a, b) if n in missed))
        d["segment"] = seg
        d["weigh_in"] = {n: {"weight_lb": wts.get(n), "missed_by_lb": missed.get(n, 0.0)} for n in (a, b)}
        out.append(d)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()

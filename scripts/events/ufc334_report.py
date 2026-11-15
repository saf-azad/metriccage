"""Render top-3 outcomes and probability trees for UFC 334 from a predictions JSON.

    .venv/bin/python scripts/events/ufc334_report.py [predictions.json] [out.md]

Joint outcome = P(winner) x P(method). The method head is not conditioned on who
wins, so both fighters share the same method split.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/processed/ufc334_predictions.json"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "reports/ufc334_outcomes.md"
METHODS = ("KO/TKO", "Decision", "Submission")


def main() -> None:
    fights = [f for f in json.loads(SRC.read_text()) if "error" not in f]
    lines = ["# UFC 334: Gane vs. Hokit — top outcomes and probability trees", "",
             f"Source: `{SRC.name}`. Joint outcome = P(winner) × P(method); "
             "the method split is the same for both fighters.", "",
             "## Top 3 outcomes per fight", "",
             "| Bout | #1 | #2 | #3 |", "|---|---|---|---|"]
    trees = ["", "## Probability trees", ""]
    for f in fights:
        a, b = f["fighter_a"], f["fighter_b"]
        pw = {a: f["winner_prob"]["a"], b: f["winner_prob"]["b"]}
        mp = f["method_prob"]
        joint = sorted(((pw[n] * mp[m], f"{n.split()[-1]} by {m}") for n in pw for m in METHODS),
                       reverse=True)
        lines.append(f"| {a} vs {b} | " + " | ".join(f"{lab} {100 * p:.1f}%" for p, lab in joint[:3]) + " |")
        trees += [f"### {a} vs {b} ({f.get('weight_class', '')}, {f['segment']} card)", "", "```"]
        order = sorted(pw, key=pw.get, reverse=True)
        for i, n in enumerate(order):
            last = i == len(order) - 1
            trees.append(f"{'└─' if last else '├─'} {n} wins  {100 * pw[n]:.1f}%")
            ms = sorted(METHODS, key=lambda m: mp[m], reverse=True)
            for j, m in enumerate(ms):
                trees.append(f"{'   ' if last else '│  '}{'└─' if j == 2 else '├─'} by {m:<11}"
                             f"{100 * mp[m]:5.1f}% of the time  →  {100 * pw[n] * mp[m]:4.1f}% overall")
        rd = f.get("finish_round_dist") or {}
        if rd:
            trees.append("When it ends: " + " · ".join(
                f"{k.replace('round_', 'R').replace('decision', 'goes to decision')} {100 * v:.0f}%"
                for k, v in rd.items() if v >= 0.005))
        trees += ["```", ""]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines + trees))
    print("\n".join(lines + trees))


if __name__ == "__main__":
    main()

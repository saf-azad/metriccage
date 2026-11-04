"""Predict a single fight through the public API — the ONE prediction entry point.

Thin CLI wrapper over ``src.api.predict_fight``. Prints the human-readable
Markdown card by default, or the raw ``to_dict()`` payload as JSON with --json.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/predict.py \\
        --a "Islam Makhachev" --b "Charles Oliveira" --date 2025-04-12 \\
        --weight-class Lightweight

    PYTHONPATH=. .venv/bin/python scripts/predict.py \\
        --a "Khamzat Chimaev" --b "Sean Strickland" --date 2026-05-09 \\
        --event "UFC 328" --weight-class "Middleweight (Title)" --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Allow `python scripts/predict.py` (no PYTHONPATH) to find the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as exc:  # noqa: BLE001 — turn into an argparse-style error
        raise argparse.ArgumentTypeError(f"date must be YYYY-MM-DD, got {s!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--a", required=True, metavar="NAME", help="fighter A name")
    parser.add_argument("--b", required=True, metavar="NAME", help="fighter B name")
    parser.add_argument("--date", required=True, type=_parse_date, metavar="YYYY-MM-DD",
                        help="event date (features use only data strictly before this)")
    parser.add_argument("--event", default="", metavar="NAME", help="event name (optional)")
    parser.add_argument("--weight-class", default="", metavar="WC",
                        help="weight class, e.g. 'Lightweight' (optional)")
    parser.add_argument("--include-odds", action="store_true",
                        help="attach implied-odds fields to the prediction")
    parser.add_argument("--json", action="store_true",
                        help="print to_dict() as JSON instead of the Markdown card")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Lazy import: loads the bundle + data on first call (keeps --help instant).
    from src.api.predict_fight import predict_fight

    pred = predict_fight(
        args.a,
        args.b,
        args.date,
        include_odds=args.include_odds,
        event_name=args.event,
        weight_class=args.weight_class,
    )

    if args.json:
        print(json.dumps(pred.to_dict(), indent=2, default=str))
    else:
        print(pred.to_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())

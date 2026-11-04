"""Walk-forward backtest over an arbitrary date range — the canonical backtest CLI.

Thin, parametrized wrapper over ``src.eval.backtest.run_backtest`` (workstream A):
it walks event-by-event through [--start, --end], predicting each event with state
strictly *before* its date and scoring blind picks (winner accuracy, Brier, logloss,
per-confidence buckets, method top-1). The predictor is the production
``src.api.predict_fight``, injected via ``src.eval.backtest.api_model_factory``.

Data source: the built feature matrix (``feature_matrix_built.parquet``, which carries
the properly randomised a/b labels used at training time — never the winner-first raw
``fights.parquet``). ``event_name`` is joined from ``fights.parquet`` when available so
events group by card; otherwise fights group by date.

CAVEAT (Elo/history freshness): ``api_model_factory`` uses the API's cached as-of state.
The API threads ``event_date`` through every feature function itself (shared contract #4),
so predictions are as-of-correct for events within the model's known data window. For a
STRICT chronological Elo+history replay against events NEWER than the cached state
(e.g. the live 2026 season), use ``scripts/backtest_2026_events.py`` — it replays winner_id
/ method into Elo before each event. This CLI is the general date-range tool; that script
is the specialised 2026 holdout runner.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/backtest.py --start 2024-01-01 --end 2025-05-04
    PYTHONPATH=. .venv/bin/python scripts/backtest.py --start 2024-01-01 --end 2024-06-30 \\
        --limit 3 --json                       # bound to the first 3 events (quick wiring check)

NOTE: a full range hits real data and can take a while — bound it with --limit while
iterating. This session does NOT run a full backtest.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Allow `python scripts/backtest.py` (no PYTHONPATH) to find the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MATRIX_PATH = ROOT / "data" / "processed" / "feature_matrix_built.parquet"
FALLBACK_MATRIX_PATH = ROOT / "data" / "processed" / "feature_matrix.parquet"
FIGHTS_PATH = ROOT / "data" / "interim" / "fights.parquet"


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"date must be YYYY-MM-DD, got {s!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--start", required=True, type=_parse_date, metavar="YYYY-MM-DD",
                        help="inclusive start of the evaluation window")
    parser.add_argument("--end", required=True, type=_parse_date, metavar="YYYY-MM-DD",
                        help="inclusive end of the evaluation window")
    parser.add_argument("--matrix", type=Path, default=None,
                        help="feature matrix parquet with a/b labels + names "
                             f"(default: {MATRIX_PATH.name}, falling back to "
                             f"{FALLBACK_MATRIX_PATH.name})")
    parser.add_argument("--fights", type=Path, default=FIGHTS_PATH,
                        help="raw fights parquet, used only to join event_name (optional)")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="bound the run to the first N in-window events (quick check)")
    parser.add_argument("--out", type=Path, default=None,
                        help="optional path to write per-fight results (.csv or .json)")
    parser.add_argument("--json", action="store_true",
                        help="print the summary dict as JSON instead of a table")
    return parser


def _load_fights(matrix_path: Path | None, fights_path: Path):
    import pandas as pd

    path = matrix_path or (MATRIX_PATH if MATRIX_PATH.exists() else FALLBACK_MATRIX_PATH)
    if not path.exists():
        raise SystemExit(
            f"feature matrix not found: {path}\n"
            "Build it first: PYTHONPATH=. .venv/bin/python scripts/build_features.py "
            "--out data/processed/feature_matrix_built.parquet"
        )
    df = pd.read_parquet(path)
    df["event_date"] = pd.to_datetime(df["event_date"])

    if "event_name" not in df.columns and fights_path.exists() and "fight_id" in df.columns:
        fights = pd.read_parquet(fights_path)
        if {"fight_id", "event_name"}.issubset(fights.columns):
            name_map = (
                fights[["fight_id", "event_name"]]
                .drop_duplicates("fight_id")
                .set_index("fight_id")["event_name"]
            )
            df["event_name"] = df["fight_id"].map(name_map).fillna("UFC event")
    return df, path


def _apply_limit(df, start: date, end: date, limit: int):
    """Restrict the evaluation window to the first `limit` in-window event dates.

    Warm-up rows before `start` are untouched (run_backtest still uses them as
    training context); we only pull the effective end date back.
    """
    import pandas as pd

    in_window = df[(df["event_date"] >= pd.Timestamp(start)) & (df["event_date"] <= pd.Timestamp(end))]
    keys = "event_name" if "event_name" in df.columns else None
    group_cols = ["event_date", keys] if keys else ["event_date"]
    event_dates = (
        in_window[group_cols].drop_duplicates().sort_values("event_date")["event_date"].tolist()
    )
    if not event_dates:
        return end
    capped = event_dates[: max(1, limit)]
    return pd.Timestamp(capped[-1]).date()


def _print_summary(summary: dict) -> None:
    print("=" * 68)
    print(f"BACKTEST {summary['start_date']} → {summary['end_date']}")
    print("=" * 68)
    print(f"  events:        {summary['n_events']}")
    print(f"  fights scored: {summary['n_fights']}  (errors: {summary['n_errors']})")
    if summary["n_fights"]:
        print(f"  winners:       {summary['winners_correct']}/{summary['n_fights']} "
              f"({100 * summary['accuracy']:.1f}%)")
        print(f"  brier:         {summary['brier']:.4f}")
        print(f"  logloss:       {summary['logloss']:.4f}")
        if summary.get("method_top1_accuracy") == summary.get("method_top1_accuracy"):  # not NaN
            print(f"  method top-1:  {summary['method_top1']} "
                  f"({100 * summary['method_top1_accuracy']:.1f}%)  "
                  f"mean-rank {summary['method_mean_rank']:.2f}")
        for bucket, stats in sorted(summary.get("by_confidence", {}).items()):
            print(f"    {bucket:<8} {stats['correct']}/{stats['n']} "
                  f"({100 * stats['accuracy']:.1f}%)")
    print("=" * 68)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.start > args.end:
        build_parser().error(f"--start {args.start} is after --end {args.end}")

    # Lazy imports so `--help` stays instant and data-free.
    from src.eval.backtest import api_model_factory, run_backtest

    fights, matrix_path = _load_fights(args.matrix, args.fights)
    end = args.end
    if args.limit is not None:
        end = _apply_limit(fights, args.start, args.end, args.limit)
        print(f"[limit] capped to first {args.limit} event(s): end -> {end}", file=sys.stderr)

    print(f"[data] {matrix_path}  ({len(fights)} rows)", file=sys.stderr)
    result = run_backtest(fights, api_model_factory, args.start, end)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        if args.out.suffix == ".json":
            args.out.write_text(result.per_fight.to_json(orient="records", indent=2))
        else:
            result.per_fight.to_csv(args.out, index=False)
        print(f"[out] wrote per-fight results -> {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps(result.summary, indent=2, default=str))
    else:
        _print_summary(result.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

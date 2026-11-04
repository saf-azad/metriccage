"""One-shot scraper entry point.

    python scripts/scrape_all.py --enrich-details            # Track 2B backfill
    python scripts/scrape_all.py --enrich-details --limit 50 # smoke run
    python scripts/scrape_all.py --enrich-details --refresh  # force re-fetch

Track 2B backfills four columns missing from the v1 fights parquet:
    ss_attempted_a/b, td_attempted_a/b (true accuracy)
    control_time_a/b (control-time, in seconds)

Polite delay = SCRAPE_RATE_LIMIT_SECONDS (1.5 s by default). For 7,400 fights
the full backfill is ~3 hours; HTML pages are cached on disk so re-runs are
near-instant.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import ROOT
from src.data.scrape_ufcstats import enrich_with_fight_details

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2005)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch even if cached")
    parser.add_argument(
        "--enrich-details",
        action="store_true",
        help="Backfill attempted-strikes / TD-attempted / control-time on existing fights.parquet",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap pages fetched (smoke runs)")
    parser.add_argument(
        "--recompute",
        action="store_true",
        help="Re-parse every fight from cached HTML (no re-fetch) — repairs A/B side alignment",
    )
    parser.add_argument("--progress", action="store_true", default=True)
    args = parser.parse_args()

    interim = ROOT / "data" / "interim" / "fights.parquet"
    if not interim.exists():
        raise SystemExit(f"No fights at {interim}; v1 scrape must run first.")

    fights = pd.read_parquet(interim)

    if args.enrich_details:
        src = ROOT / "data" / "interim" / "fights_enriched.parquet"
        if args.recompute and src.exists():
            fights = pd.read_parquet(src)  # keep target-strike columns already merged
        enriched = enrich_with_fight_details(
            fights, refresh=args.refresh, progress=args.progress, limit=args.limit,
            recompute=args.recompute,
        )
        out_path = ROOT / "data" / "interim" / "fights_enriched.parquet"
        enriched.to_parquet(out_path, index=False)
        print(f"Wrote {out_path} ({len(enriched)} rows, {len(enriched.columns)} cols)")
        return

    raise SystemExit(
        "No action requested. The full re-scrape is not needed; pass --enrich-details "
        "to backfill the Track 2B columns."
    )


if __name__ == "__main__":
    main()

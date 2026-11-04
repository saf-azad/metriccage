"""Build the feature matrix from cleaned interim data.

Canonical invocation (mirrors scripts/train_all.py's `_step_load_or_build`):
    balance_fight_labels(fights, seed=42) -> build_full_matrix(fights, fighters, cluster_model)

Usage:
    PYTHONPATH=. .venv/bin/python scripts/build_features.py --out /path/to/matrix.parquet
    PYTHONPATH=. .venv/bin/python scripts/build_features.py \\
        --out /tmp/smoke.parquet --sample 20 --no-cluster

`--out` is REQUIRED and never defaults to the canonical
data/processed/feature_matrix*.parquet, so a casual run cannot clobber the
production matrix; an existing file is only overwritten with `--force`.

`--sample N` emits feature rows for only the last N fights (chronologically)
while still replaying the FULL prior history for Elo / per-fighter state —
temporal correctness is preserved (see build_full_matrix's `limit_to_last_n`).
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

from src.config import INTERIM, PROCESSED
from src.data.clean import balance_fight_labels
from src.features.build_matrix import build_full_matrix

log = logging.getLogger("build_features")


def _default_fights_path() -> Path:
    """Prefer the Track-2B enriched fights parquet when present (as train_all does)."""
    enriched = INTERIM / "fights_enriched.parquet"
    return enriched if enriched.exists() else INTERIM / "fights.parquet"


def _load_cluster_model(path: Path):
    if not path.exists():
        log.warning("No cluster model at %s — cluster_a_*/cluster_b_* columns will be absent", path)
        return None
    with open(path, "rb") as fh:
        model = pickle.load(fh)
    log.info("Loaded archetype cluster model (K=%d, %d feature cols)",
             model.k_chosen, len(model.feature_cols))
    return model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fights", type=Path, default=None,
                        help="bilateral fights parquet (default: data/interim/"
                             "fights_enriched.parquet, falling back to fights.parquet)")
    parser.add_argument("--fighters", type=Path, default=INTERIM / "fighters.parquet",
                        help="fighters parquet (default: data/interim/fighters.parquet)")
    parser.add_argument("--out", type=Path, required=True,
                        help="output parquet path (required; no default so the canonical "
                             "feature matrix cannot be clobbered accidentally)")
    parser.add_argument("--sample", type=int, default=None, metavar="N",
                        help="emit only the last N fights' rows (full history is still "
                             "replayed for temporal correctness) — smoke-testing aid")
    parser.add_argument("--no-cluster", action="store_true",
                        help="skip the archetype cluster model (no cluster_* columns)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite --out if it already exists")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.out.exists() and not args.force:
        parser.error(f"refusing to overwrite existing {args.out} (pass --force to allow)")

    fights_path = args.fights if args.fights is not None else _default_fights_path()
    if not fights_path.exists():
        parser.error(f"fights parquet not found: {fights_path}")

    log.info("Loading fights from %s", fights_path)
    fights = pd.read_parquet(fights_path)
    fighters = pd.read_parquet(args.fighters) if args.fighters.exists() else None
    if fighters is None:
        log.warning("No fighters parquet at %s — bio features will be NaN-backed", args.fighters)

    # Source data lists the winner as fighter_a everywhere (label is 100% class 1).
    # Deterministically swap ~half the rows so the binary target balances ~50/50.
    # seed=42 is the canonical value used by train_all.py — do not parametrize it,
    # or the rebuilt matrix stops matching the production one row-for-row.
    fights = balance_fight_labels(fights, seed=42)
    log.info("Balanced fight labels — A wins: %d / %d (%.1f%%)",
             int(fights["fighter_a_won"].sum()), len(fights),
             100 * fights["fighter_a_won"].mean())

    cluster_model = None if args.no_cluster else _load_cluster_model(PROCESSED / "cluster_model.pkl")

    t0 = time.monotonic()
    matrix = build_full_matrix(
        fights, fighters,
        cluster_model=cluster_model,
        progress=True,
        limit_to_last_n=args.sample,
    )
    elapsed = time.monotonic() - t0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_parquet(args.out, index=False)
    log.info("Wrote %s (%d rows, %d cols) in %.1fs", args.out, matrix.shape[0], matrix.shape[1], elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())

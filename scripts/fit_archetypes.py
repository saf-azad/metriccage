"""Fit the GMM archetype clustering on train-period fighter career vectors.

For every fighter with >= MIN_FIGHTS UFC fights before TRAIN_END, builds the
career vector (decayed strikes/TDs/etc) AS OF TRAIN_END and feeds the matrix
into `fit_archetype_model`. The fitted bundle is pickled to
`data/processed/cluster_model.pkl` and consumed at matrix-build time by
`build_feature_row(cluster_model=...)`.

Temporal correctness: the cluster centroids see ZERO post-2022 data; at
predict time, build_feature_row computes the fighter's as-of-event career
vector and scores it through `bundle.predict_membership(...)` — the
centroids are frozen, only the fighter's position relative to them moves.

    python scripts/fit_archetypes.py [--min-fights 3] [--ref-date 2022-12-31]
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
from datetime import date as dt_date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import PROCESSED, ROOT, TRAIN_END
from src.features.build_matrix import _fight_to_perfighter_rows
from src.models.clustering import aggregate_career_features, fit_archetype_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fit_archetypes")


def _fights_path() -> Path:
    enriched = ROOT / "data" / "interim" / "fights_enriched.parquet"
    return enriched if enriched.exists() else ROOT / "data" / "interim" / "fights.parquet"


def _build_fighter_table(
    fights: pd.DataFrame,
    fighters: pd.DataFrame | None,
    ref_date: dt_date,
    min_fights: int,
) -> pd.DataFrame:
    """One row per fighter with career stats AS OF `ref_date`.

    Walks the bilateral fights frame chronologically, accumulates per-fighter
    history, and at the end aggregates each fighter's history into the
    DEFAULT_FEATURE_COLS career vector.
    """
    fights = fights.sort_values("event_date").reset_index(drop=True)
    fights["event_date"] = pd.to_datetime(fights["event_date"])
    cutoff = pd.Timestamp(ref_date)

    bio = {}
    if fighters is not None:
        for r in fighters.itertuples(index=False):
            bio[r.fighter_id] = {
                "reach_in": float(getattr(r, "reach_in", float("nan")) or float("nan")),
                "stance": str(getattr(r, "stance", "") or ""),
                "weight_class": "",
            }

    history: dict[str, list[dict]] = {}
    last_wc: dict[str, str] = {}
    for f in fights.itertuples(index=False):
        d = f._asdict()
        if pd.to_datetime(d["event_date"]) > cutoff:
            break
        a_pf, b_pf = _fight_to_perfighter_rows(pd.Series(d))
        history.setdefault(d["fighter_a_id"], []).append(a_pf)
        history.setdefault(d["fighter_b_id"], []).append(b_pf)
        if pd.notna(d.get("weight_class")):
            last_wc[d["fighter_a_id"]] = d["weight_class"]
            last_wc[d["fighter_b_id"]] = d["weight_class"]

    rows = []
    for fid, hist in history.items():
        if len(hist) < min_fights:
            continue
        career = aggregate_career_features(
            pd.DataFrame(hist), fid, bio.get(fid), reference_date=ref_date
        )
        career["weight_class"] = last_wc.get(fid, "")
        rows.append(career)

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-fights", type=int, default=3)
    parser.add_argument(
        "--ref-date",
        type=lambda s: dt_date.fromisoformat(s),
        default=TRAIN_END,
        help="Build career vectors as of this date (default: TRAIN_END)",
    )
    parser.add_argument("--out", type=Path, default=PROCESSED / "cluster_model.pkl")
    args = parser.parse_args()

    fp = _fights_path()
    log.info("Loading fights from %s", fp)
    fights = pd.read_parquet(fp)
    fighters_path = ROOT / "data" / "interim" / "fighters.parquet"
    fighters = pd.read_parquet(fighters_path) if fighters_path.exists() else None

    log.info("Building per-fighter career table (cutoff=%s, min_fights=%d)",
             args.ref_date, args.min_fights)
    table = _build_fighter_table(fights, fighters, args.ref_date, args.min_fights)
    log.info("Career table: %d fighters × %d cols", *table.shape)

    log.info("Fitting GMM archetype model")
    bundle = fit_archetype_model(table, save=False)
    log.info(
        "Picked K=%d (BIC=%.1f, silhouette=%.3f); covers %d weight classes",
        bundle.k_chosen, bundle.bic, bundle.silhouette,
        len(bundle.division_priors or {}),
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(bundle, f)
    log.info("Wrote %s", args.out)


if __name__ == "__main__":
    main()

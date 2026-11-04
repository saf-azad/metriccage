"""Parse target-zone significant strikes from raw UFCStats fight HTML.

Source: data/raw/fights/<fight_id>.html
Output: data/interim/fight_target_strikes.parquet — one row per fight with:

  head_landed_a, head_att_a, body_landed_a, body_att_a, leg_landed_a, leg_att_a,
  distance_landed_a, distance_att_a, clinch_landed_a, clinch_att_a, ground_landed_a, ground_att_a,
  (same with _b suffix)

Each value is the fight TOTAL (sum across rounds). Per-round splits skipped
for v1 — career rates from totals already capture the bulk of the signal.

Side alignment
--------------
UFCStats lists the two fighters in page order, but fights.parquet has ~50% of
rows deliberately A/B-swapped for label balance (see clean.balance_fight_labels).
The parser therefore reads the two fighter IDs from the table's first cell and
maps page-order values onto fighter_a_id / fighter_b_id explicitly. Before this
fix (2026-09), 2,985 of 7,270 fights had every target column on the wrong side.

Run with --merge-enriched to also overwrite the target columns in
data/interim/fights_enriched.parquet with the realigned values.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw" / "fights"
FIGHTS = ROOT / "data" / "interim" / "fights.parquet"
OUT = ROOT / "data" / "interim" / "fight_target_strikes.parquet"
ENRICHED = ROOT / "data" / "interim" / "fights_enriched.parquet"

TARGET_ORDER = ["head", "body", "leg", "distance", "clinch", "ground"]
TARGET_COLS = [f"{t}_{k}_{s}" for t in TARGET_ORDER for k in ("landed", "att") for s in ("a", "b")]

_FIGHTER_ID_RE = re.compile(r"fighter-details/([0-9a-f]{16})")

# Pattern: "X of Y X of Y" (fighter A then fighter B in same cell)
PAIR_RE = re.compile(r"(\d+)\s+of\s+(\d+)\s+(\d+)\s+of\s+(\d+)")


def parse_pair_cell(text: str) -> tuple[int, int, int, int] | None:
    m = PAIR_RE.search(text or "")
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # (la, aa, lb, ab)


def parse_fight_html(html: str) -> dict | None:
    """Extract totals-by-target from a fight detail HTML page."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")

    target_table = None
    for t in tables:
        headers = [th.get_text(strip=True) for th in t.find_all("th")]
        if "Head" in headers and "Body" in headers and "Leg" in headers and "Distance" in headers:
            # Distinguish per-round table (row count > 2) from totals (row count == 2)
            data_rows = [r for r in t.find_all("tr") if r.find("td")]
            if len(data_rows) == 1:
                target_table = t
                break
            elif target_table is None:
                target_table = t  # fallback if we don't find a 1-row version

    if target_table is None:
        return None

    data_rows = [r for r in target_table.find_all("tr") if r.find("td")]
    if not data_rows:
        return None

    tds = data_rows[0].find_all("td")
    cells = [td.get_text(" ", strip=True) for td in tds]
    # Expected order: Fighter | Sig.str | Sig.str% | Head | Body | Leg | Distance | Clinch | Ground
    if len(cells) < 9:
        return None

    # Page-order fighter IDs from the first cell's two fighter-details links.
    # Values below are stored in PAGE order ("_p0"/"_p1"); main() maps them
    # onto fighter_a / fighter_b using fights.parquet.
    page_ids = _FIGHTER_ID_RE.findall(str(tds[0]))
    result: dict = {"page_fighter_0": page_ids[0] if len(page_ids) > 0 else None,
                    "page_fighter_1": page_ids[1] if len(page_ids) > 1 else None}
    for i, name in enumerate(TARGET_ORDER):
        pair = parse_pair_cell(cells[3 + i])
        if pair is None:
            return None
        l0, a0, l1, a1 = pair
        result[f"{name}_landed_p0"] = l0
        result[f"{name}_att_p0"] = a0
        result[f"{name}_landed_p1"] = l1
        result[f"{name}_att_p1"] = a1
    return result


def align_to_fight_sides(parsed: dict, fighter_a_id: str, fighter_b_id: str) -> tuple[dict, str]:
    """Map page-order values onto fighter_a / fighter_b.

    Returns (row, status) where status is one of:
      "direct"   — page order == (a, b)
      "swapped"  — page order == (b, a); values were flipped
      "unknown"  — IDs could not be matched; page order assumed (a, b)
    """
    p0, p1 = parsed.get("page_fighter_0"), parsed.get("page_fighter_1")
    if p0 == fighter_a_id and p1 == fighter_b_id:
        status, a_side, b_side = "direct", "p0", "p1"
    elif p0 == fighter_b_id and p1 == fighter_a_id:
        status, a_side, b_side = "swapped", "p1", "p0"
    else:
        status, a_side, b_side = "unknown", "p0", "p1"

    row = {}
    for name in TARGET_ORDER:
        for k in ("landed", "att"):
            row[f"{name}_{k}_a"] = parsed[f"{name}_{k}_{a_side}"]
            row[f"{name}_{k}_b"] = parsed[f"{name}_{k}_{b_side}"]
    return row, status


def verify_alignment(df: pd.DataFrame, fights: pd.DataFrame) -> int:
    """Return the number of fights whose head+body+leg landed != ss_landed for side A.

    Uses fights.parquet's ss_landed_a/b as ground truth (those columns come from
    the round tables, which carry fighter IDs and were never mis-sided).
    """
    m = df.merge(fights[["fight_id", "ss_landed_a", "ss_landed_b"]], on="fight_id", how="inner")
    sum_a = m["head_landed_a"] + m["body_landed_a"] + m["leg_landed_a"]
    sum_b = m["head_landed_b"] + m["body_landed_b"] + m["leg_landed_b"]
    mismatch = int(((sum_a != m["ss_landed_a"]) | (sum_b != m["ss_landed_b"])).sum())
    still_swapped = int(((sum_a == m["ss_landed_b"]) & (sum_a != m["ss_landed_a"])).sum())
    print(f"Verify: {len(m)} fights checked, {mismatch} mismatches vs ss_landed, {still_swapped} look side-swapped")
    return mismatch


def merge_into_enriched(df: pd.DataFrame) -> None:
    """Overwrite the target columns in fights_enriched.parquet with realigned values."""
    if not ENRICHED.exists():
        print(f"No {ENRICHED}; skipping merge")
        return
    enriched = pd.read_parquet(ENRICHED)
    base = enriched.drop(columns=[c for c in TARGET_COLS if c in enriched.columns])
    merged = base.merge(df[["fight_id"] + TARGET_COLS], on="fight_id", how="left")
    # Keep the original column order where possible.
    ordered = [c for c in enriched.columns if c in merged.columns] + [c for c in merged.columns if c not in enriched.columns]
    merged = merged[ordered]
    merged.to_parquet(ENRICHED, index=False)
    print(f"Merged realigned target columns into {ENRICHED} ({len(merged)} rows)")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-enriched", action="store_true",
                    help="Also overwrite target columns in fights_enriched.parquet")
    args = ap.parse_args()

    fights = pd.read_parquet(FIGHTS)
    fights["event_date"] = pd.to_datetime(fights["event_date"])
    side_lookup = dict(zip(fights["fight_id"], zip(fights["fighter_a_id"], fights["fighter_b_id"])))

    rows = []
    n_ok = n_miss = n_bad = 0
    status_counts = {"direct": 0, "swapped": 0, "unknown": 0}
    for i, fid in enumerate(fights["fight_id"]):
        path = RAW_DIR / f"{fid}.html"
        if not path.exists():
            n_miss += 1
            continue
        try:
            parsed = parse_fight_html(path.read_text())
        except Exception:
            parsed = None
        if not parsed:
            n_bad += 1
            continue
        a_id, b_id = side_lookup[fid]
        row, status = align_to_fight_sides(parsed, a_id, b_id)
        status_counts[status] += 1
        row["fight_id"] = fid
        rows.append(row)
        n_ok += 1
        if (i + 1) % 1000 == 0:
            print(f"  parsed {i+1}/{len(fights)}  ok={n_ok} bad={n_bad} miss={n_miss}", flush=True)

    df = pd.DataFrame(rows)
    print(f"\nDone: ok={n_ok} bad={n_bad} miss={n_miss}  -> {len(df)} rows")
    print(f"Side alignment: {status_counts}")
    if status_counts["unknown"]:
        print("  WARNING: 'unknown' rows fell back to page order — check those fight pages")
    verify_alignment(df, fights)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"Wrote -> {OUT}")

    if args.merge_enriched:
        merge_into_enriched(df)

    # Spot check: Prates vs JDM
    pj = fights[fights["fight_id"] == "eb6d9fef6c374830"]
    if len(pj):
        row = df[df["fight_id"] == "eb6d9fef6c374830"]
        if len(row):
            r = row.iloc[0]
            print("\nSpot check (Prates fight, fight_id eb6d9fef…):")
            print(f"  A (JDM):    head {r.head_landed_a}/{r.head_att_a}, body {r.body_landed_a}/{r.body_att_a}, leg {r.leg_landed_a}/{r.leg_att_a}")
            print(f"  B (Prates): head {r.head_landed_b}/{r.head_att_b}, body {r.body_landed_b}/{r.body_att_b}, leg {r.leg_landed_b}/{r.leg_att_b}")


if __name__ == "__main__":
    main()

"""Re-parse per-round stats from locally cached UFCStats fight HTML.

The fight-level parquets only keep whole-fight totals. The raw HTML in
data/raw/fights/<fight_id>.html still contains the per-round breakdown
tables, so we can reconstruct round-level data with no network access.

Output: data/interim/fight_rounds.parquet  (long format, one row per
fighter per round per fight).

Fighter identity is keyed by fighter_id pulled from the <a> href inside
each row's first cell (robust to name-spelling differences like
"Bobby Green" vs "King Green"). Falls back to header person-link order.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
FIGHTS_DIR = ROOT / "data" / "raw" / "fights"
OUT = ROOT / "data" / "interim" / "fight_rounds.parquet"

FID_RE = re.compile(r"fighter-details/([0-9a-f]+)")


def fid_from_a(a) -> str | None:
    if a is None:
        return None
    href = a.get("href", "") or ""
    m = FID_RE.search(href)
    return m.group(1) if m else None


def num(s):
    """Parse a single numeric stat cell. Handles '', '---', '52%', '4:13' (ctrl)."""
    if s is None:
        return None
    s = s.strip()
    if s in ("", "---", "--"):
        return None
    if ":" in s:  # control time mm:ss
        mm, ss = s.split(":")
        try:
            return int(mm) * 60 + int(ss)
        except ValueError:
            return None
    s = s.replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def of_pair(s):
    """Parse 'X of Y' -> (landed, attempted). Plain 'N' -> (N, None)."""
    if s is None:
        return (None, None)
    s = s.strip()
    if s in ("", "---", "--"):
        return (None, None)
    m = re.match(r"(\d+)\s+of\s+(\d+)", s)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    try:
        return (float(s), None)
    except ValueError:
        return (None, None)


def data_rows(table):
    """Yield (cells, fids) per data row. cells[i] = list of <p> texts; fids = per-column fighter_id from first cell anchors."""
    rows = []
    for tr in table.find_all("tr"):
        if tr.find("td") is None:  # header / round-label row
            continue
        tds = tr.find_all("td")
        cells = [[p.get_text(strip=True) for p in td.find_all("p")] for td in tds]
        fids = [fid_from_a(a) for a in tds[0].find_all("a")]
        rows.append((cells, fids))
    return rows


def parse_fight(path: Path):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 4:
        return []  # missing per-round tables

    # header person links as fallback id source (column order)
    hdr_fids = [fid_from_a(a) for a in soup.select("a.b-fight-details__person-link")]

    tot_rows = data_rows(tables[1])  # per-round Totals
    sig_rows = data_rows(tables[3])  # per-round Significant Strikes
    if not tot_rows:
        return []

    out = []
    n_rounds = len(tot_rows)
    for ridx in range(n_rounds):
        cells, fids = tot_rows[ridx]
        names = cells[0]
        for col in range(len(names)):
            fid = (fids[col] if col < len(fids) and fids[col] else
                   (hdr_fids[col] if col < len(hdr_fids) else None))
            sig_l, sig_a = of_pair(cells[2][col]) if len(cells[2]) > col else (None, None)
            tot_l, tot_a = of_pair(cells[4][col]) if len(cells[4]) > col else (None, None)
            td_l, td_a = of_pair(cells[5][col]) if len(cells[5]) > col else (None, None)
            rec = dict(
                fight_id=path.stem,
                round=ridx + 1,
                col=col,
                fighter_id=fid,
                fighter_name=names[col],
                kd=num(cells[1][col]) if len(cells[1]) > col else None,
                sig_landed=sig_l, sig_att=sig_a,
                total_landed=tot_l, total_att=tot_a,
                td_landed=td_l, td_att=td_a,
                sub_att=num(cells[7][col]) if len(cells[7]) > col else None,
                rev=num(cells[8][col]) if len(cells[8]) > col else None,
                ctrl_sec=num(cells[9][col]) if len(cells[9]) > col else None,
            )
            # significant-strike target breakdown (same row order/columns)
            if ridx < len(sig_rows):
                scells, _ = sig_rows[ridx]
                def grab(idx, scells=scells, col=col):
                    return of_pair(scells[idx][col]) if len(scells) > idx and len(scells[idx]) > col else (None, None)
                rec["head_landed"], rec["head_att"] = grab(3)
                rec["body_landed"], rec["body_att"] = grab(4)
                rec["leg_landed"], rec["leg_att"] = grab(5)
                rec["dist_landed"], rec["dist_att"] = grab(6)
                rec["clinch_landed"], rec["clinch_att"] = grab(7)
                rec["ground_landed"], rec["ground_att"] = grab(8)
            out.append(rec)
    return out


def main():
    only = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    files = sorted(FIGHTS_DIR.glob("*.html"))
    if only:
        files = [f for f in files if f.stem in only]
    all_rows = []
    bad = 0
    for i, f in enumerate(files):
        try:
            rows = parse_fight(f)
            if not rows:
                bad += 1
            all_rows.extend(rows)
        except Exception as e:  # noqa
            bad += 1
        if i % 1000 == 0:
            print(f"  {i}/{len(files)} parsed, rows={len(all_rows)}, empty={bad}", flush=True)
    df = pd.DataFrame(all_rows)
    df.to_parquet(OUT, index=False)
    print(f"\nWrote {OUT}")
    print(f"fights parsed: {df['fight_id'].nunique()} | rows: {len(df)} | empty/failed files: {bad}")
    print(f"rows missing fighter_id: {df['fighter_id'].isna().sum()}")


if __name__ == "__main__":
    main()

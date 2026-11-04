"""UFCStats.com scraper.

Pulls UFC events since 2005 (configurable). Output schema is the canonical
fight record used everywhere downstream — every other module trusts these
columns.

PRIMARY OUTPUT
    data/raw/events/{event_id}.html              raw HTML cache (never re-fetched if present)
    data/raw/fights/{fight_id}.html              per-fight detail page cache
    data/interim/fights.parquet                  one row per fight, full schema
    data/interim/fighters.parquet                one row per fighter, with vitals

FIGHT SCHEMA — the existing v1 parquet already has
    fight_id, event_id, event_date, weight_class, fighter_a_id, fighter_b_id,
    method, round_finished, time_finished, ss_landed_a/b, td_landed_a/b,
    sub_att_a/b, kd_a/b, fight_url, ...

Track 2B EXTENSIONS — added by `enrich_with_fight_details()`:
    ss_attempted_a, ss_attempted_b      sig strikes attempted (true accuracy)
    td_attempted_a, td_attempted_b      takedowns attempted    (true TD accuracy)
    control_time_a, control_time_b      seconds of cage control per fighter

Implementation notes:
    - Rate limit: SCRAPE_RATE_LIMIT_SECONDS between every network request,
      enforced with `time.sleep`. Tenacity retries on 5xx / connection drops.
    - On-disk cache: never re-fetch if the HTML for that page already exists.
    - User-agent: identifies us per SCRAPE_USER_AGENT (academic-purpose tag).
    - The bilateral fights.parquet schema already exists; this module's job is
      to BACKFILL the four attempted columns + control time. ~7,400 detail
      pages × 1.5s = ~3 hours, fully automatable.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import RAW, SCRAPE_RATE_LIMIT_SECONDS, SCRAPE_USER_AGENT

logger = logging.getLogger(__name__)


@dataclass
class ScrapeStats:
    events_seen: int = 0
    events_skipped_cached: int = 0
    fights_parsed: int = 0
    fight_pages_fetched: int = 0
    fight_pages_skipped_cached: int = 0
    errors: int = 0


# --- HTTP layer -------------------------------------------------------------


def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _polite_get(url: str, *, session=None, last_request: list[float] | None = None) -> str:
    """GET with rate limiting + tenacity retry. Returns response text.

    `last_request` is a one-element list used as a mutable timestamp marker so
    successive calls can space themselves SCRAPE_RATE_LIMIT_SECONDS apart.
    """
    import requests
    from tenacity import retry, stop_after_attempt, wait_exponential

    last_request = last_request if last_request is not None else [0.0]
    elapsed = time.monotonic() - last_request[0]
    if elapsed < SCRAPE_RATE_LIMIT_SECONDS:
        time.sleep(SCRAPE_RATE_LIMIT_SECONDS - elapsed)

    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": SCRAPE_USER_AGENT})

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
    def _do() -> str:
        r = session.get(url, timeout=15)
        if r.status_code >= 500:
            raise RuntimeError(f"server {r.status_code} on {url}")
        r.raise_for_status()
        return r.text

    text = _do()
    last_request[0] = time.monotonic()
    return text


def _cache_or_fetch(url: str, cache_path: Path, *, session=None, last_request=None, refresh=False) -> str:
    if cache_path.exists() and not refresh:
        return cache_path.read_text(errors="ignore")
    html = _polite_get(url, session=session, last_request=last_request)
    _ensure_dir(cache_path.parent)
    cache_path.write_text(html)
    return html


# --- Detail-page parser (Track 2B core) -------------------------------------


_OF_RE = re.compile(r"\s*(\d+)\s*of\s*(\d+)\s*", re.IGNORECASE)
_FIGHTER_ID_RE = re.compile(r"fighter-details/([0-9a-f]{16})")

# Per-side columns written by the detail-page parser. Used to flip A/B when the
# page lists the fighters in the opposite order to fights.parquet (which has
# ~50% of rows deliberately swapped by clean.balance_fight_labels).
_SIDE_PAIRS = [
    ("ss_landed_a", "ss_landed_b"),
    ("ss_attempted_a", "ss_attempted_b"),
    ("td_landed_a", "td_landed_b"),
    ("td_attempted_a", "td_attempted_b"),
    ("control_time_a", "control_time_b"),
]


def align_detail_to_sides(data: dict, fighter_a_id: str, fighter_b_id: str) -> tuple[dict, str]:
    """Reorder a parsed detail dict (page order) onto fighter_a / fighter_b.

    Returns (data, status): "direct", "swapped" or "unknown" (IDs not matched;
    page order kept). Mutates and returns the same dict.
    """
    p0, p1 = data.get("page_fighter_0"), data.get("page_fighter_1")
    if p0 == fighter_a_id and p1 == fighter_b_id:
        return data, "direct"
    if p0 == fighter_b_id and p1 == fighter_a_id:
        for ca, cb in _SIDE_PAIRS:
            if ca in data and cb in data:
                data[ca], data[cb] = data[cb], data[ca]
        return data, "swapped"
    return data, "unknown"
_DIGIT_RE = re.compile(r"\d+")
_TIME_RE = re.compile(r"^\s*(\d+):(\d{1,2})\s*$")


def _parse_of_pair(cell: str) -> tuple[int, int]:
    """Parse 'X of Y' UFCStats cells. Returns (landed, attempted)."""
    m = _OF_RE.search(cell or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    digits = _DIGIT_RE.findall(cell or "")
    if len(digits) >= 2:
        return int(digits[0]), int(digits[1])
    if digits:
        return int(digits[0]), int(digits[0])
    return 0, 0


def _parse_control_time(cell: str) -> float:
    m = _TIME_RE.match(cell or "")
    if not m:
        return 0.0
    return float(m.group(1)) * 60 + float(m.group(2))


def parse_fight_detail_html(html: str) -> dict:
    """Parse a UFCStats fight detail page. Returns dict with attempted + control time.

    UFCStats has a "Totals" table with rows: Sig. str. (landed / attempted),
    Total str., Td (landed / attempted), Sub. att, Pass, Reversals, Ctrl. We
    extract sig strikes attempted, takedowns attempted, and control time —
    the columns missing from the v1 fights parquet.

    Values are returned in PAGE order (a = first fighter listed). The two
    fighter IDs are returned as ``page_fighter_0`` / ``page_fighter_1`` so the
    caller can realign with :func:`align_detail_to_sides`.
    """
    from bs4 import BeautifulSoup  # lazy import to keep deps optional

    soup = BeautifulSoup(html, "html.parser")
    out: dict = {
        "ss_landed_a": 0,
        "ss_attempted_a": 0,
        "ss_landed_b": 0,
        "ss_attempted_b": 0,
        "td_landed_a": 0,
        "td_attempted_a": 0,
        "td_landed_b": 0,
        "td_attempted_b": 0,
        "control_time_a": 0.0,
        "control_time_b": 0.0,
        "page_fighter_0": None,
        "page_fighter_1": None,
    }

    # Pick the Totals table. It's the first table on the page whose tbody has
    # exactly one row (per-fight totals). The per-round and significant-strike
    # breakdown tables have multiple rows. Class names on UFCStats are not
    # reliable across vintages — structural shape is.
    target_row = None
    for table in soup.find_all("table"):
        body = table.find("tbody")
        if body is None:
            continue
        rows = body.find_all("tr", recursive=False)
        if len(rows) != 1:
            continue
        cells = rows[0].find_all("td")
        # Need at least: Fighter, KD, Sig.Str., Sig.Str.%, Total Str., Td,
        # Td%, Sub.Att, Pass/Rev, Ctrl  → 10 columns
        if len(cells) >= 9 and "of" in cells[2].get_text(" ", strip=True):
            target_row = rows[0]
            break
    if target_row is None:
        return out

    cells = target_row.find_all("td")
    page_ids = _FIGHTER_ID_RE.findall(str(cells[0]))
    if len(page_ids) >= 2:
        out["page_fighter_0"], out["page_fighter_1"] = page_ids[0], page_ids[1]

    def _split_per_fighter(cell) -> tuple[str, str]:
        ps = [p.get_text(strip=True) for p in cell.find_all("p")]
        if len(ps) >= 2:
            return ps[0], ps[1]
        text = cell.get_text(" ", strip=True)
        # Fallback: split into two halves
        bits = text.split()
        if len(bits) >= 2:
            return " ".join(bits[: len(bits) // 2]), " ".join(bits[len(bits) // 2 :])
        return text, text

    # Layout (UFCStats totals): 0 Fighters, 1 KD, 2 Sig.Str., 3 Sig.Str.%,
    # 4 Total Str., 5 Td, 6 Td%, 7 Sub.Att, 8 Pass (or Rev), 9 Ctrl.
    # Some older pages have an 11-cell layout (Pass + Rev + Ctrl); detect by length.
    ctrl_idx = 10 if len(cells) >= 11 else 9
    sig_a, sig_b = _split_per_fighter(cells[2])
    td_a, td_b = _split_per_fighter(cells[5])
    ctrl_a, ctrl_b = _split_per_fighter(cells[ctrl_idx])

    out["ss_landed_a"], out["ss_attempted_a"] = _parse_of_pair(sig_a)
    out["ss_landed_b"], out["ss_attempted_b"] = _parse_of_pair(sig_b)
    out["td_landed_a"], out["td_attempted_a"] = _parse_of_pair(td_a)
    out["td_landed_b"], out["td_attempted_b"] = _parse_of_pair(td_b)
    out["control_time_a"] = _parse_control_time(ctrl_a)
    out["control_time_b"] = _parse_control_time(ctrl_b)
    return out


def scrape_fight_detail(fight_url: str, *, session=None, last_request=None, refresh=False) -> dict:
    """Fetch (with cache) and parse one fight detail page."""
    fight_id = fight_url.rstrip("/").split("/")[-1]
    cache = RAW / "fights" / f"{fight_id}.html"
    html = _cache_or_fetch(fight_url, cache, session=session, last_request=last_request, refresh=refresh)
    return parse_fight_detail_html(html)


# --- Backfill driver --------------------------------------------------------


def enrich_with_fight_details(
    fights: pd.DataFrame,
    *,
    refresh: bool = False,
    progress: bool = False,
    limit: int | None = None,
    recompute: bool = False,
) -> pd.DataFrame:
    """Add ss_attempted_a/b, td_attempted_a/b, control_time_a/b to a fights frame.

    Parsed values are realigned from page order onto fighter_a / fighter_b via
    the fighter IDs on the page (fights.parquet has ~50% of rows A/B-swapped).

    If a fight already has the columns and they're non-NaN we skip it, unless
    ``recompute`` is set (re-parse every row from the cached HTML without
    re-fetching — use this to repair mis-sided values). The
    bottleneck is the ~1.5 s polite delay per page; iteration is otherwise
    cheap (HTML caches reuse prior runs). Run nightly via train_all if you
    want fresh data.
    """
    import requests

    out = fights.copy()
    # Only the 6 columns below are written by enrichment. The parser also
    # extracts ss_landed/td_landed from the same totals row, but those
    # fields already exist in the v1 fights frame and use a different
    # convention (total strikes vs significant strikes); overwriting them
    # silently breaks every model trained on the v1 numbers.
    new_cols = [
        "ss_attempted_a",
        "ss_attempted_b",
        "td_attempted_a",
        "td_attempted_b",
        "control_time_a",
        "control_time_b",
    ]
    for c in new_cols:
        if c not in out.columns:
            out[c] = pd.NA

    todo_mask = out["ss_attempted_a"].isna() | refresh | recompute
    todo_idx = out.index[todo_mask]
    if limit:
        todo_idx = todo_idx[:limit]

    iterator: Iterable = todo_idx
    if progress:
        try:
            from tqdm import tqdm  # type: ignore

            iterator = tqdm(todo_idx, desc="fight detail")
        except Exception:
            pass

    session = requests.Session()
    session.headers.update({"User-Agent": SCRAPE_USER_AGENT})
    last_request = [0.0]

    parsed = 0
    errors = 0
    side_counts = {"direct": 0, "swapped": 0, "unknown": 0}
    for i in iterator:
        url = out.at[i, "fight_url"]
        if not url or pd.isna(url):
            continue
        try:
            data = scrape_fight_detail(
                url, session=session, last_request=last_request, refresh=refresh
            )
            data, status = align_detail_to_sides(
                data, out.at[i, "fighter_a_id"], out.at[i, "fighter_b_id"]
            )
            side_counts[status] += 1
            for k in new_cols:
                if k in data:
                    out.at[i, k] = data[k]
            parsed += 1
        except Exception as exc:
            errors += 1
            logger.warning("Failed to parse %s: %s", url, exc)

    logger.info("enrich_with_fight_details: parsed=%d errors=%d sides=%s", parsed, errors, side_counts)
    if side_counts["unknown"]:
        logger.warning("%d fights had unmatched page fighter IDs; page order assumed", side_counts["unknown"])
    return out


# --- Deliberate deferrals (kept for the original module surface) ------------
#
# The three functions below are DELIBERATELY unimplemented: the v1
# data/interim/fights.parquet is canonical (docs/PLAN.md §4.1 source 1 was scraped
# once and cached under data/raw/), and re-scraping UFCStats from scratch is
# out of scope. The implemented path in this module is the Track-2B
# enrichment: `enrich_with_fight_details()` backfills ss_attempted_*,
# td_attempted_* and control_time_* onto the existing frame from cached /
# politely-fetched detail pages.


def scrape_all_events(start_year: int = 2005, end_year: int | None = None) -> ScrapeStats:
    """Top-level driver. Walks the events index and pulls everything.

    DELIBERATE DEFERRAL — not implemented by design. The bilateral fights
    parquet already exists in data/interim/fights.parquet (docs/PLAN.md §4.1,
    source 1: UFCStats) and a full re-scrape would only reproduce it. The
    implemented path is `enrich_with_fight_details`, which fills the
    ss_attempted / td_attempted / control_time columns missing from v1.
    Use `python scripts/scrape_all.py --enrich-details` for that.
    """
    raise NotImplementedError(
        "Deliberate deferral (docs/PLAN.md §4.1 source 1): full UFCStats re-scrape is not "
        "needed — the v1 data/interim/fights.parquet is canonical. Use "
        "enrich_with_fight_details() (Track 2B) to backfill attempted/control columns."
    )


def scrape_event_page(event_id: str) -> dict:
    """Parse one UFCStats event page into fight rows.

    DELIBERATE DEFERRAL — not implemented by design. The v1 event index
    (docs/PLAN.md §4.1 source 1) already covers 2005–present and is baked into
    data/interim/fights.parquet; only the detail-page enrichment path
    (`enrich_with_fight_details`) is implemented in Track 2B.
    """
    raise NotImplementedError(
        "Deliberate deferral (docs/PLAN.md §4.1 source 1): the v1 event index already covers "
        "2005–present; only enrich_with_fight_details() is implemented in Track 2B."
    )


def assemble_fights_dataframe() -> pd.DataFrame:
    """Assemble the bilateral fights DataFrame from scraped event pages.

    DELIBERATE DEFERRAL — not implemented by design. The v1
    data/interim/fights.parquet is the source of truth (docs/PLAN.md §4.1,
    source 1); Track 2B only enriches it via `enrich_with_fight_details()`.
    New raw frames are canonicalised by `src.data.clean.clean_fights`.
    """
    raise NotImplementedError(
        "Deliberate deferral (docs/PLAN.md §4.1 source 1): the v1 fights.parquet is the "
        "source of truth. Track 2B only enriches it; see enrich_with_fight_details()."
    )

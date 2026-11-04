"""Clean and validate the raw scraped data into the canonical interim format.

Steps applied (in order):
    1. Drop No Contests and Doctor Stoppages from training data (keep flagged for analysis).
    2. Reconcile fighter aliases (e.g., "Jon Jones" vs "Jonathan Jones") via a manual map.
    3. Normalise weight class strings ("Light Heavyweight" -> "lhw").
    4. Coerce types, sort by event_date, drop exact duplicates.
    5. Hash fight_id deterministically.
    6. Write data/interim/fights.parquet and data/interim/fighters.parquet.

A pandera schema in tests/ enforces the contract.

IMPLEMENTATION NOTES (empirical ground truth = the shipped v1 parquets)
    The cleaning rules below were derived by introspecting the canonical
    ``data/interim/fights.parquet`` / ``fighters.parquet`` rather than from the
    aspirational prose above, so that ``clean_fights(raw_like_frame)``
    reproduces the canonical frames exactly. Deliberate divergences:

    * Weight classes are stored as FULL names ("Light Heavyweight"), not the
      abbreviations in ``WEIGHT_CLASS_MAP``. Normalisation therefore maps
      aliases / abbreviations / case variants back TO the full canonical name.
    * docs/PLAN.md §6.4 rolls NC/DQ into Decision at the MODEL level. The interim
      parquet instead preserves ``DQ`` as its own ``method_canon`` value (18
      rows) and contains zero NC rows — i.e. No Contests are DROPPED during
      cleaning while DQs are kept and labelled ``"DQ"``. Doctor stoppages are
      ordinary KO/TKOs in the v1 data (no dedicated method), so nothing is
      dropped for them.
    * ``dob`` in fighters.parquet is an ISO "YYYY-MM-DD" *string* (downstream
      code parses it lazily); we validate through ``pd.to_datetime`` and store
      back the ISO string, not a datetime column.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

WEIGHT_CLASS_MAP = {
    "Strawweight": "sw",
    "Flyweight": "fly",
    "Bantamweight": "bw",
    "Featherweight": "fw",
    "Lightweight": "lw",
    "Welterweight": "ww",
    "Middleweight": "mw",
    "Light Heavyweight": "lhw",
    "Heavyweight": "hw",
    "Women's Strawweight": "wsw",
    "Women's Flyweight": "wfly",
    "Women's Bantamweight": "wbw",
    "Women's Featherweight": "wfw",
}

# --- Canonical schemas (column order matches the shipped v1 parquets) --------

FIGHTS_CANONICAL_COLS = [
    "fight_id", "event_id", "event_date", "event_name", "weight_class",
    "fighter_a_id", "fighter_a_name", "fighter_b_id", "fighter_b_name",
    "winner_id", "method", "method_detail", "round_finished", "time_finished",
    "kd_a", "kd_b", "ss_landed_a", "ss_landed_b", "td_landed_a", "td_landed_b",
    "sub_att_a", "sub_att_b", "fight_url", "time_finished_sec",
    "fight_duration_sec", "fight_duration_min", "method_canon", "fighter_a_won",
]

FIGHTERS_CANONICAL_COLS = ["fighter_id", "name", "height_in", "reach_in", "stance", "dob"]

# Rows without these cannot be identified/ordered/labelled — they are dropped.
_FIGHTS_CRITICAL_COLS = ["fight_id", "event_date", "fighter_a_id", "fighter_b_id", "winner_id"]

# Optional string columns: filled with "" when the raw frame lacks them
# (the v1 parquet uses "" — never NaN — for absent string values).
_FIGHTS_OPTIONAL_STR_COLS = [
    "event_id", "event_name", "fighter_a_name", "fighter_b_name",
    "method_detail", "time_finished", "fight_url",
]

# Per-side counting stats: int64, missing values become 0 (v1 convention).
_FIGHTS_COUNT_COLS = [
    "kd_a", "kd_b", "ss_landed_a", "ss_landed_b",
    "td_landed_a", "td_landed_b", "sub_att_a", "sub_att_b",
]

# Track-2B / target-zone enrichment columns: kept as nullable floats when
# present (fights_enriched.parquet), never fabricated when absent.
_FIGHTS_OPTIONAL_NUMERIC_COLS = [
    "ss_attempted_a", "ss_attempted_b", "td_attempted_a", "td_attempted_b",
    "control_time_a", "control_time_b",
    "head_landed_a", "head_att_a", "head_landed_b", "head_att_b",
    "body_landed_a", "body_att_a", "body_landed_b", "body_att_b",
    "leg_landed_a", "leg_att_a", "leg_landed_b", "leg_att_b",
    "distance_landed_a", "distance_att_a", "distance_landed_b", "distance_att_b",
    "clinch_landed_a", "clinch_att_a", "clinch_landed_b", "clinch_att_b",
    "ground_landed_a", "ground_att_a", "ground_landed_b", "ground_att_b",
]

# Empirical method -> method_canon mapping (groupby on the v1 parquet):
#   KO/TKO -> KO/TKO   SUB -> Submission   U-DEC/S-DEC/M-DEC -> Decision
#   DQ -> DQ (18 rows; NOT rolled into Decision — see module docstring)
# Keys are matched case-insensitively after stripping whitespace.
_METHOD_CANON_MAP = {
    "KO/TKO": "KO/TKO",
    "TKO": "KO/TKO",
    "KO": "KO/TKO",
    "SUB": "Submission",
    "SUBMISSION": "Submission",
    "U-DEC": "Decision",
    "S-DEC": "Decision",
    "M-DEC": "Decision",
    "DEC": "Decision",
    "DECISION": "Decision",
    "DQ": "DQ",
}

# No Contests never appear in the canonical parquet — dropped outright.
_NO_CONTEST_METHODS = {"NC", "CNC", "NO CONTEST", "OVERTURNED"}

# Alias lookup back to the canonical FULL weight-class name: accepts the
# abbreviations in WEIGHT_CLASS_MAP ("lhw"), any case variant of the full
# name ("light heavyweight"), and passes unknown values ("Catch Weight")
# through untouched.
_WC_ALIASES: dict[str, str] = {}
for _full, _abbr in WEIGHT_CLASS_MAP.items():
    _WC_ALIASES[_full.casefold()] = _full
    _WC_ALIASES[_abbr.casefold()] = _full

_TIME_MMSS_RE = re.compile(r"^\s*(\d+):(\d{1,2})\s*$")
_FEET_INCHES_RE = re.compile(r"""^\s*(\d+)\s*'\s*(\d+(?:\.\d+)?)\s*"?\s*$""")
_NUMBER_RE = re.compile(r'''^\s*(\d+(?:\.\d+)?)\s*(?:"|in\.?|inches)?\s*$''', re.IGNORECASE)


def _normalise_weight_class(value: object) -> str:
    """Map any weight-class alias back to the canonical full name."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip()
    return _WC_ALIASES.get(text.casefold(), text)


def _canon_method(value: object) -> str | None:
    """Return the canonical method label, or None for No Contests (drop row)."""
    text = ("" if value is None else str(value)).strip()
    key = text.upper()
    if key in _NO_CONTEST_METHODS:
        return None
    return _METHOD_CANON_MAP.get(key, text)


def _time_finished_to_seconds(value: object) -> int:
    """Parse a 'M:SS' round clock into seconds (0 when missing/unparseable)."""
    m = _TIME_MMSS_RE.match("" if value is None else str(value))
    if not m:
        return 0
    return int(m.group(1)) * 60 + int(m.group(2))


def clean_fights(raw: pd.DataFrame) -> pd.DataFrame:
    """Canonicalise a raw scraped fights frame into the interim fights schema.

    Applied, in order:
        1. Drop rows missing any critical identifier (fight_id, event_date,
           fighter ids, winner_id — draws/NCs carry no winner and are gone).
        2. Coerce ``event_date`` to ``datetime.date`` (unparseable -> dropped).
        3. Drop No Contest rows; derive ``method_canon`` for the rest
           (empirical mapping — KO/TKO, Submission, Decision, DQ).
        4. Normalise ``weight_class`` aliases to the canonical full name.
        5. Coerce counting stats to int64 (missing -> 0, v1 convention),
           ``round_finished`` to nullable Int64, enrichment columns to float.
        6. Re-derive ``time_finished_sec``, ``fight_duration_sec`` (5-minute
           rounds), ``fight_duration_min`` and ``fighter_a_won``
           (winner_id == fighter_a_id) from primitives.
        7. Deduplicate on ``fight_id`` (keep first), stable-sort by
           ``event_date``, order columns canonically (extras appended).

    Columns that CANNOT be derived from a raw frame and must be scraped:
    fight_id, event_id, event_name, fighter names, winner_id, method,
    method_detail, round_finished, time_finished, the counting stats and
    fight_url. Absent optional string columns are filled with "" (and
    time-derived columns then compute to 0); absent counting stats become 0.

    Raises KeyError if a critical column is missing entirely.
    """
    missing = [c for c in [*_FIGHTS_CRITICAL_COLS, "method"] if c not in raw.columns]
    if missing:
        raise KeyError(f"clean_fights: raw frame is missing critical columns {missing}")

    df = raw.copy()

    # -- 1. drop rows missing critical identifiers ----------------------------
    for col in _FIGHTS_CRITICAL_COLS:
        values = df[col]
        df = df[values.notna() & (values.astype(str).str.strip() != "")]

    # -- 2. dates -------------------------------------------------------------
    event_dt = pd.to_datetime(df["event_date"], errors="coerce")
    df = df[event_dt.notna()]
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.date

    # -- 3. methods (drop NC, canonicalise the rest) --------------------------
    df["method"] = df["method"].astype(str).str.strip()
    canon = df["method"].map(_canon_method)
    df = df[canon.notna()]
    df["method_canon"] = df["method"].map(_canon_method)

    # -- 4. weight class ------------------------------------------------------
    if "weight_class" not in df.columns:
        df["weight_class"] = ""
    df["weight_class"] = df["weight_class"].map(_normalise_weight_class)

    # -- 5. numeric coercion --------------------------------------------------
    for col in _FIGHTS_COUNT_COLS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    if "round_finished" not in df.columns:
        df["round_finished"] = pd.NA
    df["round_finished"] = pd.to_numeric(df["round_finished"], errors="coerce").astype("Int64")
    for col in _FIGHTS_OPTIONAL_NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # -- optional string columns ----------------------------------------------
    for col in _FIGHTS_OPTIONAL_STR_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype("str")
    for col in ["fight_id", "fighter_a_id", "fighter_b_id", "winner_id",
                "weight_class", "method", "method_canon"]:
        df[col] = df[col].astype("str")

    # -- 6. derived columns ---------------------------------------------------
    df["time_finished_sec"] = (
        df["time_finished"].map(_time_finished_to_seconds).astype("int64")
    )
    rounds = df["round_finished"].fillna(1).astype("int64")
    df["fight_duration_sec"] = ((rounds - 1) * 300 + df["time_finished_sec"]).astype("int64")
    df["fight_duration_min"] = df["fight_duration_sec"] / 60.0
    df["fighter_a_won"] = (df["winner_id"] == df["fighter_a_id"]).astype("int64")

    # -- 7. dedupe, sort, order columns ----------------------------------------
    df = df.drop_duplicates(subset="fight_id", keep="first")
    df = df.sort_values("event_date", kind="stable").reset_index(drop=True)

    extras = [c for c in df.columns if c not in FIGHTS_CANONICAL_COLS]
    return df[FIGHTS_CANONICAL_COLS + extras]


def _parse_length_inches(value: object) -> float:
    """Coerce a height/reach value to inches. Accepts 71, '71', `5' 11"`, '72"'."""
    if value is None:
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"--", "-", "N/A", "n/a"}:
        return np.nan
    m = _FEET_INCHES_RE.match(text)
    if m:
        return float(m.group(1)) * 12.0 + float(m.group(2))
    m = _NUMBER_RE.match(text)
    if m:
        return float(m.group(1))
    return np.nan


def _normalise_stance(value: object) -> object:
    """Lowercase/strip stance; empty or placeholder values become NaN."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    text = str(value).strip().lower()
    if not text or text in {"--", "-", "n/a", "nan"}:
        return np.nan
    return text


def _normalise_dob(value: object) -> object:
    """Validate a date-of-birth and store it as the canonical ISO string."""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return np.nan
    return parsed.strftime("%Y-%m-%d")


def clean_fighters(raw: pd.DataFrame) -> pd.DataFrame:
    """Canonicalise a raw scraped fighters frame into the interim schema.

    fighter_id/name are required; rows without a fighter_id are dropped and
    the frame is deduplicated on fighter_id (keep first, input order kept).
    height_in/reach_in accept numerics or UFCStats strings (`5' 11"`, '72"',
    '--') and become float64 inches (NaN when unknown). stance is lowercased
    ({orthodox, southpaw, switch, open stance}; NaN when unknown). dob is
    validated via pd.to_datetime (any parseable format) and stored back as an
    ISO 'YYYY-MM-DD' string — the canonical fighters.parquet dtype.
    """
    missing = [c for c in ("fighter_id", "name") if c not in raw.columns]
    if missing:
        raise KeyError(f"clean_fighters: raw frame is missing critical columns {missing}")

    df = raw.copy()
    ids = df["fighter_id"]
    df = df[ids.notna() & (ids.astype(str).str.strip() != "")]
    df["fighter_id"] = df["fighter_id"].astype("str").str.strip()
    df["name"] = df["name"].fillna("").astype("str").str.strip()

    for col in ("height_in", "reach_in"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = df[col].map(_parse_length_inches).astype("float64")

    if "stance" not in df.columns:
        df["stance"] = np.nan
    df["stance"] = df["stance"].map(_normalise_stance).astype("str")

    if "dob" not in df.columns:
        df["dob"] = np.nan
    df["dob"] = df["dob"].map(_normalise_dob).astype("str")

    df = df.drop_duplicates(subset="fighter_id", keep="first").reset_index(drop=True)

    extras = [c for c in df.columns if c not in FIGHTERS_CANONICAL_COLS]
    return df[FIGHTERS_CANONICAL_COLS + extras]


# --- A/B label balancing ----------------------------------------------------

# The raw bilateral fights frame stores the winner as fighter_a everywhere
# (`fighter_a_won == 1` for every row). Training on that produces a single-
# class target — useless for a binary classifier. We deterministically swap
# the A and B sides on a Bernoulli(0.5) sample so labels balance to ~50/50,
# while keeping the swap reproducible across rebuilds via a fixed seed.

# Columns that store side-specific values and must move together when swapped.
_BILATERAL_PAIRS = [
    ("fighter_a_id", "fighter_b_id"),
    ("fighter_a_name", "fighter_b_name"),
    ("ss_landed_a", "ss_landed_b"),
    ("td_landed_a", "td_landed_b"),
    ("sub_att_a", "sub_att_b"),
    ("kd_a", "kd_b"),
    # Track 2B detail-page columns
    ("ss_attempted_a", "ss_attempted_b"),
    ("td_attempted_a", "td_attempted_b"),
    ("control_time_a", "control_time_b"),
]


def balance_fight_labels(fights: pd.DataFrame, *, seed: int = 42) -> pd.DataFrame:
    """Return a copy of `fights` with ~50% of rows A/B-swapped for label balance.

    `fight_id`, `event_*`, `weight_class`, `winner_id`, `method*`, `round_*`,
    and durations stay put — only the per-side columns plus `fighter_a_won`
    flip. The swap is deterministic with `seed=42`, so a feature matrix
    rebuilt today matches the matrix rebuilt tomorrow.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    flip = rng.random(len(fights)) < 0.5
    out = fights.copy()

    for a_col, b_col in _BILATERAL_PAIRS:
        if a_col in out.columns and b_col in out.columns:
            tmp = out.loc[flip, a_col].copy()
            out.loc[flip, a_col] = out.loc[flip, b_col]
            out.loc[flip, b_col] = tmp

    if "fighter_a_won" in out.columns:
        out.loc[flip, "fighter_a_won"] = 1 - out.loc[flip, "fighter_a_won"].astype(int)

    return out

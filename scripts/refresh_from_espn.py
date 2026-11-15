"""Append recent UFC fights to the interim parquets from ESPN's public MMA API.

UFCStats (the original source) now sits behind a browser check, so this fills
the gap between the last scraped event and "now" from ESPN's core API, mapped
onto the canonical bilateral schema (fighter_a is always the winner; draws and
no-contests are dropped — same conventions as ``src.data.clean``).

    PYTHONPATH=. .venv/bin/python scripts/refresh_from_espn.py \\
        --start 2026-05-03 --end 2026-11-13

Rewrites data/interim/{fights,fights_enriched,fighters}.parquet in place
(originals are copied to ``*.pre_espn`` once). Idempotent: fights already
present (same date + same pair of names) are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import INTERIM

CORE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"
_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0 (research script)"


def _get(url: str) -> dict:
    url = url.replace("http://", "https://")
    for attempt in range(4):
        try:
            r = _session.get(url, timeout=30)
            if r.status_code == 404:
                return {}
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 3:
                raise
    return {}


# ESPN spelling -> UFCStats spelling, for fighters already in the dataset.
ALIASES = {"bernardo sopaj": "benardo sopaj", "michael aswell": "michael aswell jr",
           "klaudia sygua": "klaudia sygula"}


def norm_name(s: str) -> str:
    s = _norm(s)
    return ALIASES.get(s, s)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", "").replace("-", " ").replace("'", "").split())


def ascii_name(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().strip()


def _hid(kind: str, espn_id: str) -> str:
    return hashlib.md5(f"espn-{kind}-{espn_id}".encode()).hexdigest()[:16]


def _method(result_name: str) -> str | None:
    n = (result_name or "").lower()
    if "no-contest" in n or "no contest" in n or "draw" in n or not n:
        return None
    if "dq" in n or "disqual" in n:
        return "DQ"
    if "decision" in n:
        if "split" in n:
            return "S-DEC"
        if "majority" in n:
            return "M-DEC"
        return "U-DEC"
    if "sub" in n:
        return "SUB"
    if "ko" in n or "stoppage" in n:
        return "KO/TKO"
    return None


CANON = {"U-DEC": "Decision", "S-DEC": "Decision", "M-DEC": "Decision",
         "KO/TKO": "KO/TKO", "SUB": "Submission", "DQ": "DQ"}


def _weight_class(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("W "):
        t = "Women's " + t[2:]
    if t.lower().startswith("catch"):
        return "Catch Weight"
    return t


def _mmss(v: str) -> int:
    try:
        m, s = str(v).split(":")
        return int(m) * 60 + int(s)
    except Exception:
        return 0


def _stats(ref: str) -> dict[str, str]:
    d = _get(ref) if ref else {}
    out: dict[str, str] = {}
    for cat in d.get("splits", {}).get("categories", []):
        for s in cat.get("stats", []):
            out[s["name"]] = s.get("displayValue", "0")
    return out


def _i(st: dict, k: str) -> int:
    try:
        return int(float(st.get(k, 0) or 0))
    except Exception:
        return 0


def _side(st: dict) -> dict:
    def tot(pos: list[str], tgt: list[str], suffix: str) -> int:
        return sum(_i(st, f"sig{p}{t}Strikes{suffix}") for p in pos for t in tgt)

    P, T = ["Distance", "Clinch", "Ground"], ["Head", "Body", "Leg"]
    return {
        "kd": _i(st, "knockDowns"),
        "ss_landed": _i(st, "sigStrikesLanded"),
        "ss_attempted": _i(st, "sigStrikesAttempted"),
        "td_landed": _i(st, "takedownsLanded"),
        "td_attempted": _i(st, "takedownsAttempted"),
        "sub_att": _i(st, "submissions"),
        "control_time": float(_mmss(st.get("timeInControl", "0:00"))),
        "head_landed": tot(P, ["Head"], "Landed"), "head_att": tot(P, ["Head"], "Attempted"),
        "body_landed": tot(P, ["Body"], "Landed"), "body_att": tot(P, ["Body"], "Attempted"),
        "leg_landed": tot(P, ["Leg"], "Landed"), "leg_att": tot(P, ["Leg"], "Attempted"),
        "distance_landed": tot(["Distance"], T, "Landed"),
        "distance_att": tot(["Distance"], T, "Attempted"),
        "clinch_landed": tot(["Clinch"], T, "Landed"), "clinch_att": tot(["Clinch"], T, "Attempted"),
        "ground_landed": tot(["Ground"], T, "Landed"), "ground_att": tot(["Ground"], T, "Attempted"),
    }


def _athlete(ref: str) -> dict:
    d = _get(ref)
    stance = (d.get("stance") or {}).get("text")
    dob = d.get("dateOfBirth")
    return {
        "espn_id": str(d.get("id", "")),
        "name": ascii_name(d.get("fullName") or d.get("displayName") or ""),
        "height_in": d.get("height"),
        "reach_in": d.get("reach"),
        "stance": stance.lower() if stance else None,
        "dob": dob[:10] if dob else None,
    }


def fetch_fight(ev: dict, comp: dict) -> dict | None:
    status = _get(comp["status"]["$ref"]) if "$ref" in comp.get("status", {}) else comp.get("status", {})
    if not status.get("type", {}).get("completed"):
        return None
    method = _method((status.get("result") or {}).get("name", ""))
    cs = comp.get("competitors", [])
    if method is None or len(cs) != 2 or not any(c.get("winner") for c in cs):
        return None
    cs = sorted(cs, key=lambda c: not c.get("winner"))  # winner first
    ath = [_athlete(c["athlete"]["$ref"]) for c in cs]
    sts = [_side(_stats((c.get("statistics") or {}).get("$ref", ""))) for c in cs]
    rnd = int(status.get("period") or 0)
    tsec = int(status.get("clock") or _mmss(status.get("displayClock", "0:00")))
    return {
        "espn_comp": str(comp["id"]), "espn_event": str(ev["id"]),
        "event_date": ev["date"][:10], "event_name": ev.get("name", ""),
        "weight_class": _weight_class((comp.get("type") or {}).get("text")
                                      or (comp.get("type") or {}).get("abbreviation", "")),
        "method": method, "round": rnd, "tsec": tsec,
        "clock": status.get("displayClock", ""), "ath": ath, "sts": sts,
        "url": comp.get("$ref", ""), "has_stats": sts[0]["ss_attempted"] + sts[1]["ss_attempted"] > 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()
    span = f"{args.start.replace('-', '')}-{args.end.replace('-', '')}"

    refs = [it["$ref"] for it in _get(f"{CORE}/events?dates={span}&limit=200").get("items", [])]
    with ThreadPoolExecutor(8) as ex:
        events = list(ex.map(_get, refs))
    # The scraped dataset is UFC cards only — Contender Series bouts are not in it.
    events = [ev for ev in events if "Contender Series" not in ev.get("name", "")]
    jobs = [(ev, comp) for ev in events for comp in ev.get("competitions", [])]
    print(f"{len(events)} events, {len(jobs)} bouts listed")
    with ThreadPoolExecutor(8) as ex:
        fetched = [f for f in ex.map(lambda j: fetch_fight(*j), jobs) if f]
    print(f"{len(fetched)} completed bouts with a winner")

    enr_p, v1_p, ftr_p = (INTERIM / n for n in
                          ("fights_enriched.parquet", "fights.parquet", "fighters.parquet"))
    for p in (enr_p, v1_p, ftr_p):
        bak = p.with_suffix(p.suffix + ".pre_espn")
        if not bak.exists():
            shutil.copy(p, bak)
    enr, v1, ftr = pd.read_parquet(enr_p), pd.read_parquet(v1_p), pd.read_parquet(ftr_p)

    name_to_id: dict[str, str] = {}
    for a, b in (("fighter_a_name", "fighter_a_id"), ("fighter_b_name", "fighter_b_id")):
        name_to_id.update({norm_name(n): i for n, i in zip(enr[a], enr[b], strict=True)})
    name_to_id.update({norm_name(n): i for n, i in zip(ftr["name"], ftr["fighter_id"], strict=True)})
    id_to_name = dict(zip(ftr["fighter_id"], ftr["name"], strict=True))
    seen = {(str(d)[:10], frozenset((norm_name(a), norm_name(b))))
            for d, a, b in zip(enr["event_date"], enr["fighter_a_name"], enr["fighter_b_name"], strict=True)}

    rows, new_fighters, no_stats = [], {}, 0
    for f in sorted(fetched, key=lambda f: (f["event_date"], f["espn_comp"])):
        key = (f["event_date"], frozenset(norm_name(a["name"]) for a in f["ath"]))
        if key in seen:
            continue
        seen.add(key)
        ids = []
        for a in f["ath"]:
            k = norm_name(a["name"])
            if k not in name_to_id:
                name_to_id[k] = _hid("athlete", a["espn_id"])
                new_fighters[name_to_id[k]] = a
            ids.append(name_to_id[k])
        names = [id_to_name.get(i, a["name"]) for i, a in zip(ids, f["ath"], strict=True)]
        no_stats += not f["has_stats"]
        row = {
            "fight_id": _hid("fight", f["espn_comp"]), "event_id": _hid("event", f["espn_event"]),
            "event_date": pd.to_datetime(f["event_date"]).date(), "event_name": f["event_name"],
            "weight_class": f["weight_class"],
            "fighter_a_id": ids[0], "fighter_a_name": names[0],
            "fighter_b_id": ids[1], "fighter_b_name": names[1],
            "winner_id": ids[0], "method": f["method"], "method_detail": "",
            "round_finished": f["round"], "time_finished": f["clock"], "fight_url": f["url"],
            "time_finished_sec": f["tsec"],
            "fight_duration_sec": max(f["round"] - 1, 0) * 300 + f["tsec"],
            "method_canon": CANON[f["method"]], "fighter_a_won": 1,
        }
        row["fight_duration_min"] = row["fight_duration_sec"] / 60
        for side, st in zip("ab", f["sts"], strict=True):
            for k, v in st.items():
                row[f"{k}_{side}"] = v
        rows.append(row)

    if not rows:
        print("Nothing new to add.")
        return
    new = pd.DataFrame(rows)
    if type(enr["event_date"].iloc[0]) is not type(new["event_date"].iloc[0]):
        new["event_date"] = new["event_date"].astype(str)
    out_enr = pd.concat([enr, new[enr.columns]], ignore_index=True)
    out_v1 = pd.concat([v1, new[v1.columns]], ignore_index=True)
    for df, src in ((out_enr, enr), (out_v1, v1)):
        for c in src.columns:
            if c != "event_date":
                df[c] = df[c].astype(src[c].dtype)
    out_enr.to_parquet(enr_p, index=False)
    out_v1.to_parquet(v1_p, index=False)

    upsert_fighters(ftr, new_fighters).to_parquet(ftr_p, index=False)
    print(f"Added {len(new)} fights ({new['event_date'].min()} → {new['event_date'].max()}, "
          f"{new['event_id'].nunique()} events); {no_stats} had no strike stats on ESPN; "
          f"{len(new_fighters)} new fighters.")


def upsert_fighters(ftr: pd.DataFrame, new_fighters: dict[str, dict]) -> pd.DataFrame:
    add = pd.DataFrame([
        {"fighter_id": fid, "name": a["name"], "height_in": a["height_in"],
         "reach_in": a["reach_in"], "stance": a["stance"], "dob": a["dob"]}
        for fid, a in new_fighters.items() if fid not in set(ftr["fighter_id"])
    ], columns=ftr.columns)
    if add.empty:
        return ftr
    for c in ("height_in", "reach_in"):
        add[c] = pd.to_numeric(add[c], errors="coerce")
    return pd.concat([ftr, add], ignore_index=True)


if __name__ == "__main__":
    main()

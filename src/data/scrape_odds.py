"""BestFightOdds.com scraper.

Pulls historical opening and closing American moneylines for every UFC fight we
have. Output is joined to fights by (event_date, fighter_a, fighter_b). Used as
a benchmark and as an OPTIONAL feature — the model must work without odds.

OUTPUT
    data/external/odds.parquet
        fight_id           str   matches fights.parquet
        opener_a           int   American moneyline at line open
        opener_b           int
        closer_a           int   American moneyline at fight time
        closer_b           int
        implied_prob_a     float vig-removed implied probability
        implied_prob_b     float

STATUS — DELIBERATE DEFERRAL
    The odds scrape (docs/PLAN.md §4.1, source 2: BestFightOdds) is deferred by
    design: odds are an OPTIONAL benchmark feature and the model must work
    without them, so v1 shipped without this scraper. The TODO list below is
    the implementation plan for whoever picks it up.

TODO
    [ ] Map UFC events from BestFightOdds to UFCStats event_ids (fuzzy match by date + name)
    [ ] Scrape the event page, parse opener/closer columns
    [ ] Apply remove_vig() from src.features.core_features
    [ ] Write parquet with idempotent merge on fight_id
"""

from __future__ import annotations

import pandas as pd


def scrape_all_odds() -> pd.DataFrame:
    """Scrape historical opening/closing moneylines for all known UFC fights.

    DELIBERATE DEFERRAL — not implemented by design. docs/PLAN.md §4.1 lists
    BestFightOdds as source 2, used only for benchmarking and as an optional
    feature; the predictor must work odds-free, so this scraper was deferred
    from v1. See the module docstring for the implementation TODO list.
    """
    raise NotImplementedError(
        "Deliberate deferral (docs/PLAN.md §4.1 source 2): the BestFightOdds scrape is "
        "deferred — odds are optional/benchmark-only and the model must work without "
        "them. See the TODO plan in src/data/scrape_odds.py's module docstring."
    )

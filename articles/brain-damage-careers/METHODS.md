# Methods note and reproduction guide

Article: *After the Knockdown*. Everything in this folder was produced by the scripts listed below, run on 21 September 2026. The project's database, scripts and saved results were read and never modified.

## Input files (read only)

| File | Used for |
|---|---|
| `data/interim/fights_enriched.parquet` | 7,270 bouts, 2 Jan 2010 to 2 May 2026: result, method, round and time, bout totals by target and position |
| `data/interim/fight_rounds.parquet` | 35,218 fighter-rounds: knockdowns, strikes by target and position, takedowns, control time |
| `data/interim/fighters.parquet` | Dates of birth (three missing) |
| `data/raw/fights_summary.parquet` | Full list of 7,410 listed bouts, including the 140 draws, no-contests and overturned results that the cleaned table drops. Used only to measure true layoffs and to draw the two timelines |
| `data/raw/fighters/*.html` | Each fighter's listed bout history, used to flag careers that began before the data window |

## Scripts, in run order

1. `00_verify_data.py` writes `data_out/verification.json`.
2. `01a_parse_fighter_pages.py` writes `data_out/fighter_pages.parquet`.
3. `01b_build_tables.py` writes `data_out/career.parquet` and `data_out/rounds.parquet`. The round builder is adapted from `articles/song-umar-body-work/build_rounds.py`.
4. `02_round_after_knockdown.py` writes `data_out/results_round.json` and `data_out/next_round.parquet`.
5. `03_recovery_tactics.py` writes `data_out/results_tactics.json`.
6. `04_career_knockdowns_vs_volume.py` writes `data_out/results_career.json`, the matched-pair lists and `data_out/survival.parquet`. It reuses the definitions from `articles/head-trauma-career-arc/`.
7. `05_break_after_knockout.py` writes `data_out/results_breaks.json`.
8. `06_figures.py` writes the five charts to `figures/` as PNG and SVG. Fonts are in `fonts/` (Fraunces and IBM Plex Mono, SIL Open Font Licence); the script falls back to DejaVu if they are absent.
9. `07_multiple_testing.py` writes `data_out/results_holm.json`.

Requirements: Python 3.10+, pandas, numpy, pyarrow, scipy, statsmodels, lifelines, matplotlib, beautifulsoup4.

## Verification performed

- No duplicate `fight_id`; no duplicate (fight, round, fighter) rows; exactly two rows per round; no fight without round data; no fighter matched against himself.
- No missing values in any bout or round field used.
- Alignment: round totals summed by `fighter_id` equal the bout-level a/b columns for knockdowns, significant strikes, head strikes and takedowns in all 7,270 bouts (zero mismatches), so the fighter and opponent columns are correctly paired.
- The recorded finishing round equals the last round with data in every bout.
- Date coverage is continuous: 24 to 46 events in every calendar year from 2010 to 2025, 14 so far in 2026.
- Coverage is not complete: 140 of 7,410 listed bouts (1.9 per cent) are absent because they had no winner. Head strikes from those bouts are missing from career ledgers. Layoffs use the full list, so they are unaffected.
- Leakage: all career exposures are cumulative sums minus the current bout; the wrestling-habit label uses prior bouts only; the opponent's knockdown power uses the opponent's prior bouts only. Next-round models use only the current and earlier rounds as predictors.
- Spot checks against published accounts: UFC 318 round two knockdown and rounds three to five striking totals; Volkanovski's 105, 119 and 420-day gaps; Choi's 706-day gap and the 2023 draw that sits outside the cleaned table.

## Known weaknesses

- Round totals have no timestamps. The grappling comparison in the article is conditional on finishing the round and is labelled exploratory for that reason.
- Pre-fight wrestling habit needs at least two prior bouts, which removes debutants from that comparison.
- The break analysis has 80 per cent power only for differences of about eight percentage points.
- Two first-loss comparisons disagree (all fighters: knockout v submission log-rank p < 0.001; fighters with a prior UFC win: p = 0.95). Both are reported.
- An earlier career study in `articles/head-trauma-career-arc/` reported only the second of those comparisons. The full-sample result here supersedes it.

/* ===========================================================================
   MetricCage — single source of truth for every number on the site.
   Loaded as a plain <script> (not fetch) so the site works from file://
   with no server and no build step.

   VERIFICATION CONTRACT
   ---------------------
   Every figure below carries a `src` field naming the file it came from.
   Anything with  verified: false  is PROVISIONAL — it was transcribed from
   the planning doc or is a placeholder shape awaiting a real export.
   Provisional charts render a small caveat tag on the page.

   To publish: replace provisional values from the repo, flip verified to
   true, and the caveat tags disappear automatically.
   =========================================================================== */

const SITE = {

  meta: {
    name: "MetricCage",
    tagline:
      "A calibrated UFC fight prediction system — probabilities you can trust, not just picks.",
    author: "Safwat Al Azad",
    blurb:
      "Second-year BSc Data Science & Computer Science, University of Sydney.",
    email: "alazadsafwat@gmail.com",
    github: "https://github.com/REPLACE-ME/ufc-fight-predictor", // TODO: real URL
    linkedin: "", // leave empty to hide the link
    cv: "cv.pdf", // drop your CV PDF next to index.html, or blank to hide
    dashboardUrl: "viz/showcase/index.html", // relative path to the live tool
  },

  /* ---- Hero stat tiles ------------------------------------------------- */
  heroStats: [
    { value: "8,794", label: "real fights analysed", note: "41,392 scored rounds · 1994–2026" },
    { value: "102", label: "engineered features", note: "per fight, per side" },
    { value: "4", label: "model ensemble", note: "weight-optimised blend" },
    { value: "0.049", label: "expected calibration error", note: "re-measured on the shipped 4-stream bundle · was 0.011 on a superseded model" },
  ],

  /* ---- Headline scoreboard --------------------------------------------- */
  results: {
    split: "Blind test slice, 2024–2025",
    n: 695,
    src: "final_model_metrics.json / docs/MODEL_STATUS.md",
    rows: [
      {
        metric: "AUC-ROC",
        target: "≥ 0.740",
        result: "0.670",
        status: "miss",
        note: "Short of target by 0.07 — disclosed, not buried.",
        verified: true,
      },
      {
        metric: "Brier score",
        target: "< 0.225",
        result: "0.229",
        status: "near",
        note: "0.222 on validation, post-calibration.",
        verified: true,
      },
      {
        metric: "Log-loss",
        target: "—",
        result: "0.646",
        status: "neutral",
        note: "Calibration alone moved it 0.657 → 0.632.",
        verified: true,
      },
      {
        metric: "ECE (10-bin)",
        target: "< 0.050",
        result: "0.049",
        status: "hit",
        note: "Re-measured on the shipped bundle; 95% CI 0.033–0.092, so the target sits inside the interval.",
        verified: true,
      },
      {
        metric: "Accuracy",
        target: "context only",
        result: "59.6%",
        status: "neutral",
        note: "Naive favourite baseline sits near 60%.",
        verified: true,
      },
    ],
  },

  /* ---- Pipeline -------------------------------------------------------- */
  pipeline: [
    {
      step: "Collect",
      body:
        "Scraped from UFCStats, BestFightOdds, Tapology and Sherdog — bout results, round-by-round statistics, physical attributes and market lines.",
      tag: "4 sources",
    },
    {
      step: "Clean & reconcile",
      body:
        "Name resolution across sources, duplicate bout collapsing, unit normalisation, and explicit handling of missing pre-2010 statistics rather than silent imputation.",
      tag: "canonical fighter IDs",
    },
    {
      step: "Engineer",
      body:
        "A 102-feature matrix: full Elo replay over fight history, GMM archetype clustering of fighting style, and time-decayed rolling statistics so recent form outweighs a decade-old record.",
      tag: "102 features",
    },
    {
      step: "Split temporally",
      body:
        "Train on 2005–2022, validate on 2023, test blind on 2024–2025. No shuffled split, no random K-fold — a model that has seen the future is not a model.",
      tag: "walk-forward",
    },
  ],

  /* ---- Ensemble -------------------------------------------------------- */
  ensemble: {
    src: "docs/architecture.md",
    members: [
      {
        name: "XGBoost",
        weight: 35.3,
        role:
          "The workhorse. Captures the non-linear interactions between reach, pace and grappling volume that a linear model flattens — and it is the source of every SHAP attribution on this site.",
      },
      {
        name: "Logistic regression",
        weight: 29.2,
        role:
          "The honest linear baseline. Well-behaved probabilities, interpretable coefficients, and a constant check that the gradient-boosted model is earning its complexity.",
      },
      {
        name: "Career LSTM",
        weight: 23.1,
        role:
          "A PyTorch sequence model over each fighter's career. The other three see a snapshot; this one sees a trajectory — whether a fighter is ascending, plateauing or eroding.",
      },
      {
        name: "Elo",
        weight: 12.4,
        role:
          "The sanity anchor. Decades of chess and sport have shown Elo is hard to beat; keeping it in the blend means the ensemble can never drift far from a defensible baseline.",
      },
    ],
    blend:
      "Constrained least-squares over the four streams, minimising log-loss on the validation year, with weights forced non-negative and summing to one.",
    calibration:
      "Isotonic regression, then temperature scaling at T = 1.3 — the step that turns a ranking into a probability.",
    methodHead:
      "A separate two-stage XGBoost head predicts method of victory: first finish-versus-decision, then submission-versus-knockout. Each stage is isotonic-calibrated independently, then blended with a rules-based submission-danger prior.",
  },

  /* ---- Feature importance ---------------------------------------------- */
  featureImportance: {
    src: "final_model_metrics.json",
    verified: false, // PROVISIONAL — ordering is real, magnitudes are placeholders
    caveat:
      "Ordering taken from the model report; bar magnitudes await a fresh export.",
    insight:
      "The two strongest signals are archetype cluster memberships — the GMM-derived style groupings — not raw striking volume, not Elo, not age. Style matchup outranks output.",
    items: [
      { name: "Archetype cluster (red corner)", value: 100, family: "style" },
      { name: "Archetype cluster (blue corner)", value: 92, family: "style" },
      { name: "Significant strikes landed / min (diff)", value: 71, family: "striking" },
      { name: "Elo rating differential", value: 66, family: "rating" },
      { name: "Takedown accuracy (diff)", value: 58, family: "grappling" },
      { name: "Age differential", value: 51, family: "physical" },
      { name: "Striking defence (diff)", value: 47, family: "striking" },
      { name: "Career LSTM trajectory score", value: 43, family: "form" },
      { name: "Reach differential", value: 34, family: "physical" },
      { name: "Days since last bout (diff)", value: 28, family: "form" },
    ],
  },

  /* ---- SHAP case study -------------------------------------------------- */
  shapCase: {
    src: "docs/MODEL_STATUS.md (reproduction confirmed)",
    verified: false, // headline probability is real; per-feature deltas are provisional
    title: "Makhachev vs. Oliveira",
    probability: 0.73,
    subject: "Makhachev",
    caveat: "Output probability reproduced from the model report; component contributions await a fresh SHAP export.",
    drivers: [
      { name: "Archetype matchup (grappler vs. submission-hunter)", value: 0.11 },
      { name: "Elo differential", value: 0.07 },
      { name: "Takedown accuracy differential", value: 0.05 },
      { name: "Career trajectory (LSTM)", value: 0.04 },
      { name: "Age differential", value: -0.02 },
      { name: "Opponent submission threat", value: -0.06 },
    ],
  },

  /* ---- Reliability curve ------------------------------------------------ */
  reliability: {
    src: "viz reliability.js / calibration_compare.png",
    verified: false,
    caveat: "Bin values pending export from the current 4-stream bundle.",
    // [predicted midpoint, observed frequency, n in bin]
    bins: [
      [0.05, 0.06, 21],
      [0.15, 0.14, 44],
      [0.25, 0.27, 68],
      [0.35, 0.34, 91],
      [0.45, 0.46, 112],
      [0.55, 0.54, 118],
      [0.65, 0.66, 96],
      [0.75, 0.74, 78],
      [0.85, 0.86, 47],
      [0.95, 0.93, 20],
    ],
  },

  /* ---- Brier over time --------------------------------------------------- */
  brierByYear: {
    src: "brier_by_year.png",
    verified: false,
    caveat: "Yearly values pending export.",
    series: [
      { year: 2019, value: 0.238 },
      { year: 2020, value: 0.234 },
      { year: 2021, value: 0.231 },
      { year: 2022, value: 0.227 },
      { year: 2023, value: 0.222 },
      { year: 2024, value: 0.228 },
      { year: 2025, value: 0.230 },
    ],
    reference: 0.25,
    referenceLabel: "Coin-flip (0.250)",
  },

  /* ---- Known limitations -------------------------------------------------- */
  limitations: [
    {
      title: "The method head skews toward decisions",
      body:
        "Stage-two of the method-of-victory model reaches an AUC of only 0.56 — barely above chance. It systematically under-predicts finishes, because finishes are the rarer and noisier class and the model has learned that predicting a decision is the safer bet.",
      severity: "known",
    },
    {
      title: "No short-notice or weight-change feature",
      body:
        "Nothing in the 102 features encodes a fight taken on two weeks' notice, or a fighter moving up a division at catchweight. This is exactly why the model missed Pereira's catchweight move — it had no way to see that the fight had changed.",
      severity: "known",
    },
    {
      title: "UFC-only fight history",
      body:
        "A fighter's record begins the day they enter the UFC. Regional-circuit veterans and international debutants arrive as near-blanks, which is the single clearest cause of the Macau card result below.",
      severity: "structural",
    },
  ],

  /* ---- Roadmap ------------------------------------------------------------ */
  roadmap: {
    src: "docs/MODEL_STATUS.md §4",
    note: "AUC deltas below are the project's own estimates, not measured results.",
    items: [
      {
        work: "Retrain the LSTM on richer per-round sequences",
        gain: "+0.02 – 0.04 AUC",
        rationale:
          "The current sequence model consumes fight-level summaries; round-level input should let it see momentum within a bout, not just across a career.",
        stage: "Next",
      },
      {
        work: "True-accuracy features from attempt counts",
        gain: "+0.01 – 0.02 AUC",
        rationale:
          "Landed-strike counts conflate volume with precision. Dividing by attempts separates a busy fighter from an accurate one.",
        stage: "Next",
      },
      {
        work: "GMM archetypes with Bayesian shrinkage",
        gain: "not estimated",
        rationale:
          "Archetype assignment is the strongest feature but is unstable for fighters with few bouts. Shrinking sparse fighters toward the population prior should stop the top feature from being the noisiest one.",
        stage: "Later",
      },
      {
        work: "Optional closing-odds feature",
        gain: "≈ +0.04 AUC",
        rationale:
          "The market is a strong predictor, so adding it would help — but it changes what the model is from an independent forecast into a market-follower. Flagged as a product decision, not a modelling one.",
        stage: "Deliberately deferred",
      },
    ],
  },

  /* ---- Engineering rigor -------------------------------------------------- */
  rigor: [
    {
      title: "Dedicated leakage tests",
      body:
        "test_temporal_leakage.py and test_temporal_split.py exist for one purpose: to fail the build if any feature for a fight can see information dated after that fight.",
    },
    {
      title: "Truncation invariance",
      body:
        "A guarantee that a fighter's features computed at fight N are identical whether or not fights N+1 onward exist in the dataset. Without it, backtests silently flatter themselves.",
    },
    {
      title: "Model cards per version",
      body:
        "Every trained bundle ships a card recording its training window, feature set, metrics and known failure modes — so a result can always be traced to the model that produced it.",
    },
    {
      title: "CI targets",
      body:
        "make test lint typecheck smoke runs on every change. The smoke target predicts a real card end-to-end, so a broken pipeline fails loudly rather than quietly returning 0.5.",
    },
  ],

  /* ---- Live dashboard feature list ---------------------------------------- */
  dashboardFeatures: [
    "Matchup picker across the active roster",
    "Win-probability meter with calibrated uncertainty",
    "Method-of-victory ring (KO / submission / decision)",
    "Key-stat differential meters",
    "Force-directed career opponent graph",
    "Per-fight SHAP driver breakdown",
    "Reliability and Elo-trajectory tabs",
  ],
};

/* ===========================================================================
   Case studies — 2026 real-card backtests.
   Only the Macau card is fully documented in the source material. The others
   are stubs: fill `record`, `notes` and `verified` from your backtest logs.
   Stubs render with a visible "awaiting write-up" state rather than fiction.
   =========================================================================== */

const CASE_STUDIES = [
  {
    slug: "macau",
    card: "UFC Fight Night — Macau",
    date: "2026",
    record: "5 / 8 scored",
    headline: "The most useful thing this model has ever gotten wrong.",
    verified: true,
    featured: true,
    lede:
      "An international card, heavy with fighters who built their records outside the UFC. This page used to say the model went 9 for 13. It did not: of the thirteen bouts, one was a no-contest and four were UFC debutants the model cannot score at all, so five of those nine picks were market-led. On the eight it actually scored it went five — against an expected 5.33 from its own probabilities.",
    body: [
      "The model's fight history begins at a fighter's UFC debut. For a card assembled largely from regional and international circuits, that means several fighters arrived as statistical blanks: no Elo history to speak of, unstable archetype assignment from a handful of bouts, and rolling statistics computed over a sample too small to mean anything.",
      "Faced with a blank, the model does not say \"I don't know.\" It regresses toward the population average and reports a confident-looking number near the middle. That is the failure mode worth naming: the uncertainty was real, but it was invisible in the output.",
      "The card itself is unremarkable evidence either way — the central 80% of its own predicted distribution runs from four correct to seven, and five lands in the middle of it. The version of this story that actually carries weight is not a card at all: across the whole blind test set, AUC is 0.718 where both fighters have five or more UFC bouts and 0.603 where either has fewer than three, a gap of 0.114 with a 95% interval of 0.033 to 0.198. That is the anecdote converted into a measurement.",
      "This is a data-coverage problem, not a modelling one, and it has two fixes on the roadmap — Bayesian shrinkage on sparse-fighter archetypes so thin evidence is treated as thin, and eventually ingesting pre-UFC records so debutants are not blanks in the first place.",
    ],
    lesson:
      "A calibrated model can still be confidently wrong about a population it has never seen — and the right response to a misleading win rate is not silence, it is the distribution the model itself implies. Calibration is measured in aggregate; coverage gaps hide inside it.",
  },
  {
    slug: "ufc-328",
    card: "UFC 328",
    date: "2026",
    record: "",
    headline: "",
    verified: false,
    featured: false,
    lede: "",
    body: [],
    lesson: "",
  },
  {
    slug: "ufc-329",
    card: "UFC 329",
    date: "2026",
    record: "",
    headline: "",
    verified: false,
    featured: false,
    lede: "",
    body: [],
    lesson: "",
  },
  {
    slug: "baku",
    card: "UFC Fight Night — Baku",
    date: "2026",
    record: "",
    headline: "",
    verified: false,
    featured: false,
    lede: "",
    body: [],
    lesson: "",
  },
  {
    slug: "kape-horiguchi",
    card: "Kape vs. Horiguchi",
    date: "2026",
    record: "",
    headline: "",
    verified: false,
    featured: false,
    lede: "",
    body: [],
    lesson: "",
  },
];

/* ===========================================================================
   DISCOVERIES — computed from real UFCStats data (8,794 fights, 41,392
   fighter-rounds, 1994 → July 2026). Chart series live in data/real-stats.js
   (generated — do not hand-edit); this block holds the narrative copy.
   Verified figures cite their n. The one illustrative visual left on the
   site is the GSP ring rendering (public fight record, year-level).
   =========================================================================== */

const DISCOVERIES = {

  intro: {
    grammar:
      "Every discovery below was computed from 8,794 real fights — 41,392 fighter-rounds of public fight records, 1994 to July 2026. One analytical grammar throughout: establish the baseline, then show where reality breaks from it. Nulls are reported next to hits.",
  },

  sequence: {
    headline: "Distance striking swallowed the sport.",
    srcnote: "UFCStats public records · position of every landed significant strike · era cells shown per chart; corpus n = 41,392 fighter-rounds",
    body: [
      "Chart where significant strikes actually land — at distance, in the clinch, or on the ground. Ground share fell from 44% to 9%, and this page used to read that as the ground emptying out. It is not what happened: combined output went from 2.8 to 8.0 significant strikes per fight-minute over the same window, so a falling share and a falling rate are different claims. Per minute, ground striking fell 38%, the clinch is 16% busier than it was in 1997, and distance striking grew 657%.",
      "Wrestling did not disappear; it changed jobs. Takedown attempts rose 1.42\u00d7 per minute of fight time \u2014 not the 2.35\u00d7 the per-fight count implies \u2014 and the series is one step at the Unified Rules followed by twenty-two flat years, not a trend. Takedown accuracy has the same shape: 0.51 \u2192 0.41 in one move, then a slow drift to 0.36. Narrating a discontinuity at a rule boundary as a continuous learning story is the kind of thing a reviewer picks up.",
      "Read together, the real finding is bigger than the one this page used to publish. Nothing emptied out and nothing died. Distance striking grew more than sevenfold and out-voted everything else \u2014 a stronger claim, more defensible, from exactly the same three numbers.",
    ],
    falsify:
      "Test we ran: recompute every position figure against elapsed fight time rather than as a share of a moving total. If combined output had been flat, shares and rates would agree; it went 2.76 \u2192 8.04 per minute. Next sharper test: full play-by-play transition matrices \u2014 these aggregates cannot approximate them, because a transition matrix needs event sequences, not round totals.",
  },

  momentum: {
    headline: "Round one said what 73% couldn\u2019t.",
    srcnote: "UFC 280, October 2022 · official round-by-round statistics",
    body: [
      "The model gave Makhachev 73% before the fight. A single pre-fight number is mute about how a fight actually unfolds \u2014 so here is the real round data.",
      "Round one: Makhachev out-landed Oliveira 12\u20136, took him down twice, and held him for 228 seconds of control \u2014 76% of the round. Oliveira\u2019s total: 38 seconds. Round two: strikes 18\u201313, then the arm-triangle at 3:16.",
      "The pre-fight 73% looks conservative in hindsight \u2014 but that is exactly what calibration means. A 73% is supposed to lose about once in four. The round data shows what the number could not: this was the three-in-four, arriving on schedule.",
    ],
    falsify:
      "Next test: score every fight\u2019s rounds this way and check whether round-1 dominance (control + strike differential) predicts finishes better than the pre-fight line alone.",
  },

  quiz: {
    headline: "You can carbon-date a fight from three bars.",
    srcnote: "3-round decisions only · combined strikes landed per round, normalised per era",
    body: [
      "Strip the names and dates. Keep only three bars: how much both fighters landed in rounds one, two, three \u2014 the real average shape of a fight in that era, computed from every three-round decision on record.",
      "The shape flipped. Nineties fights front-loaded and faded. The 2000s ran flat. Modern fights climb \u2014 round three is the busiest round. If eras are real, you should be able to date a fight from its silhouette. Try.",
    ],
    falsify:
      "Test we ran: the era arcs differ beyond noise for the modern buckets (n up to 1,482 fights per era). The 1990s arc rests on n = 3 \u2014 because 85% of nineties fights never reached a decision, which is itself the era\u2019s signature.",
  },

  eras: {
    headline: "Finishes halved. Violence didn\u2019t.",
    srcnote: "UFCStats public records · n = 8,678 method-classified fights, 1994\u20132026",
    body: [
      "Two curves that should not coexist, and do. The share of fights ending early collapsed \u2014 84% in the 1990s to 50% today \u2014 while the pace of fighting tripled: from 6 to 18 significant strikes landed per fighter per round.",
      "The resolution of the paradox is skill symmetry. Early MMA was mismatch harvesting \u2014 one fighter knew something the other didn\u2019t, and it ended fast: 93% of nineties finishes came in round one. Modern fighters are complete, so fights last longer, at far higher output, and the finish \u2014 when it comes \u2014 arrives later: round one\u2019s share of finishes fell from 77% to 49%.",
      "The rulebook\u2019s fingerprints are on the curve too \u2014 gloves in 1997, the Unified Rules in 2001, and in late 2024 the 12-6 elbow came back from a 23-year ban.",
    ],
    falsify:
      "Test we ran: the decision share rises monotonically across eras while per-minute output rises alongside it. Confound to keep honest about: judging criteria changed too \u2014 some of the decision growth is scoring culture, not just skill parity.",
  },

  redlist: {
    headline: "A red list for fighting behaviours.",
    srcnote: "Era-level usage curves computed from all fighter-rounds · statuses follow the measured trend",
    body: [
      "Give every fighting behaviour a conservation status from its real usage curve \u2014 and take the denominator seriously, because the first version of this list got one wrong. The clinch was listed as dying on the strength of its collapsing share. Per minute of cage time it is busier than it was in the 1990s. Status corrected.",
      "And one correction the data forced on us: this page previously showcased the famous calf-kick boom. The target mix says leg-strike share has been flat for twenty years (~15\u201317%). The boom was real but it was a substitution \u2014 calf instead of thigh \u2014 invisible in aggregate counts. Aggregates hide substitutions; that lesson earned its place here.",
    ],
    falsify:
      "Statuses are era-level trends from n = 41,392 rounds. Next test: per-technique granularity (calf vs thigh, heel hook vs armbar) needs play-by-play data this source doesn\u2019t carry.",
  },

  bodies: {
    headline: "Age beats reach.",
    srcnote: "Fighter-clustered bootstrap CIs · reach present on 76% of decided fights, not the 99.8% name-join rate",
    body: [
      "Take every physical advantage a tale-of-the-tape can show and measure what it is actually worth \u2014 on a scale where the comparison means something. Seven years and five inches are not a common unit, so the old version of this claim was really a statement about which bins were chosen. Standardised within weight class and fitted jointly, youth is +0.343 log-odds per SD, the southpaw edge +0.145, reach +0.099, and height \u2212 0.017 with an interval that crosses zero. Age still beats reach, by about 3.5\u00d7.",
      "Being the younger fighter (56.9%, n = 8,377) is a stronger simple predictor than any reach advantage short of freakish. Win rate by age is a cliff, not a slope: 58.8% in a fighter\u2019s early twenties, 49.6% at 30\u201334, 35.8% past 40. And the sport is walking up that cliff \u2014 the average fighter aged from 29.7 to 31.9 since 1994.",
      "And one reversal. This page used to report that submission winners hold less control time than decision winners (144s against 266s) and conclude that submissions are ambushes rather than sieges. A decision runs fifteen minutes and a submission ends around six, so that comparison was settled by arithmetic before anyone threw a punch. As a share of the time the fight actually lasted, submission winners control 39.6% against 28.6% for decision winners \u2014 a gap of +11.0 points, 95% CI +9.4 to +12.6. Submissions are sieges that end early.",
    ],
    falsify:
      "These are associations, not causes \u2014 age gaps correlate with matchmaking (prospects get fed veterans). Intervals now resample fighters rather than fights, because a twenty-fight career is not twenty independent observations; that widens them by 1.04\u20131.17\u00d7, less than you might guess. Next test: condition on betting lines or Elo to see how much of the youth edge survives.",
  },

  warnings: {
    headline: "The round before the end has a fingerprint.",
    srcnote: "Finished fights reaching round 2+ · penultimate-round stats vs decision baseline at the same round number",
    body: [
      "Autopsy every finish: take the round immediately before the fight ended and compare the eventual loser\u2019s numbers against fighters in the same round of fights that went the distance. The warning signs are specific \u2014 and they differ by how the end comes.",
      "Before a knockout, the tell is damage: knockdowns suffered run 2.2\u00d7 the baseline, head strikes absorbed 1.4\u00d7. Before a submission, the tell is territory: submission attempts against run 2.8\u00d7, control time conceded 1.8\u00d7, takedowns absorbed 1.7\u00d7. Knockouts announce themselves through the head; submissions through the map.",
      "The single loudest alarm in the sport: suffer one knockdown, in any round, and the loss rate is 85.6% (n = 3,184). And fights die at the ends of rounds \u2014 a quarter of all finishes land in a round\u2019s final minute, versus 14% in a round\u2019s first.",
    ],
    falsify:
      "Confound kept honest: referees and corners also act at round ends, which inflates the last-minute share independent of fighter state. Next test: control for stoppage source (referee vs corner vs tap).",
  },

  /* ---- Career tree rings (public fight record, year-level) --------------- */
  rings: {
    src: "public fight record, Georges St-Pierre, approximate",
    verified: false,
    caveat: "Ring geometry derived from the public fight record at year level; approximate by design.",
    headline: "Read a career like a tree.",
    body: [
      "Dendrochronologists read a tree\u2019s whole life from one cross-section: wide rings for good years, thin rings for drought, scars for fire. A fighter\u2019s career slices the same way \u2014 one ring per year, thickness for activity, colour for finishes, scars for the bad nights.",
      "This is Georges St-Pierre. The wide early rings are the climb. The scar in 2007 is the Serra knockout \u2014 the loss that rebuilt his entire style. The dense disciplined rings after it are the greatest title run of his era. Then the drought: four empty years away from the sport. And one final ring in 2017 \u2014 a comeback, a title in a second division, a finish, and retirement at the peak.",
      "Careers have climate. Layoffs, damage and reinvention leave structure in the data \u2014 and once you can read one career like a tree, you can cross-date a prospect\u2019s first rings against a forest of finished careers and ask whose shape they are growing into.",
    ],
    falsify:
      "Smallest test: have readers date the scar and the drought without labels. If the events aren\u2019t findable in the geometry, the rings are just a pretty circle.",
    fighter: "Georges St-Pierre \u00b7 2002\u20132017",
    years: [
      { year: 2002, fights: 3, finishes: 3, note: "" },
      { year: 2003, fights: 2, finishes: 1, note: "" },
      { year: 2004, fights: 3, finishes: 2, note: "UFC arrival" },
      { year: 2005, fights: 3, finishes: 2, note: "" },
      { year: 2006, fights: 2, finishes: 2, note: "wins title" },
      { year: 2007, fights: 3, finishes: 1, note: "Serra KO \u2014 the scar", scar: true },
      { year: 2008, fights: 3, finishes: 2, note: "rebuilt" },
      { year: 2009, fights: 2, finishes: 1, note: "" },
      { year: 2010, fights: 2, finishes: 0, note: "" },
      { year: 2011, fights: 1, finishes: 0, note: "" },
      { year: 2012, fights: 1, finishes: 0, note: "knee reconstruction", scar: true },
      { year: 2013, fights: 2, finishes: 0, note: "steps away" },
      { year: 2014, fights: 0, finishes: 0, note: "hiatus" },
      { year: 2015, fights: 0, finishes: 0, note: "hiatus" },
      { year: 2016, fights: 0, finishes: 0, note: "hiatus" },
      { year: 2017, fights: 1, finishes: 1, note: "comeback \u2014 second-division title, retires" },
    ],
  },

  methods: {
    source: "All computed figures derive from UFCStats.com public fight records (snapshot 2 August 2026, via the open scrape_ufc_stats mirror): 8,794 fights, 41,392 fighter-round stat lines, 4,578 fighter profiles, 1994 \u2192 July 2026.",
    bullets: [
      "116 fights dropped from method analyses (overturned results, DQs, no-contests). Draws and no-contests excluded from win-rate analyses.",
      "Duration and pace restricted to standard 5-minute-round formats; early no-time-limit fights excluded, which is why some 1990s cells carry small n.",
      "Control time is fully tracked only from 2000 onward; earlier control figures are treated as missing, never as zero.",
      "Fighter attributes joined by name (99.8% match). Ages from date of birth to event date. 95% confidence intervals via normal approximation.",
      "Era buckets: 1994\u201399, 2000\u201304, 2005\u201309, 2010\u201314, 2015\u201319, 2020\u201326.",
      "All of this is observational. Every \u2018advantage\u2019 is an association; matchmaking, judging-culture shifts and stoppage norms are named confounds in each section.",
    ],
    nulls: [
      { claim: "Long arms mean long control", result: "Refuted \u2014 reach vs control time r = \u22120.055 (n = 2,013 fighters). Essentially zero." },
      { claim: "The calf-kick boom shows in target mix", result: "Refuted \u2014 leg-strike share flat at ~15\u201317% for two decades. The boom was a substitution, invisible in aggregates." },
      { claim: "Heavyweights are wilder round to round", result: "Refuted \u2014 round volatility 6.36 (HW) vs 6.40 (FW); knockdowns per fight 0.24 vs 0.22. The chaos is evenly distributed." },
      { claim: "Championship rounds are where fighters fade", result: "Refuted \u2014 in 5-round decisions, round 5 output (19.3) beats round 3 (18.3). Fighters surge, not fade." },
    ],
  },

  next: [
    {
      title: "Fighter cross-dating",
      body: "Match a prospect\u2019s first five fights against a library of completed careers and surface their nearest historical twin \u2014 then use the twin\u2019s trajectory as a forecast. Test: backtest on known careers; if the twin beats a naive baseline, ship it.",
    },
    {
      title: "Style-drift alerts",
      body: "A rolling fingerprint of how each fighter fights, flagging the bout where they stopped fighting like themselves \u2014 new camp, new coach, or decline, detected from shape alone. Test: flagged bouts should coincide with documented camp changes more often than chance.",
    },
    {
      title: "Round-1 dominance index",
      body: "From the momentum work: does round-1 control-plus-strike differential predict the finish better than pre-fight odds? The data to run it is already in hand \u2014 41,392 scored rounds.",
    },
    {
      title: "Fight sonification",
      body: "The sequence data rendered as audio \u2014 strikes as notes, takedowns as bass, eras as tempo \u2014 so 1995 and 2025 can be compared by ear. Test: listeners should date era-blind clips better than chance.",
    },
  ],
};

/* ===========================================================================
   MetricCage — the corrections ledger.

   This file is the spine of the site. Every claim that the August 2026
   correctness pass changed lives here, in the form:

        was  →  now  →  the MECHANISM that changed it

   Nothing is deleted. A portfolio whose pitch is calibrated honesty does not
   get to quietly edit its own conclusions, and the ledger is more persuasive
   than the conclusions were.

   `severity` drives the tag colour and the site's own win/loss record:
     reversed     the sign or direction of the published claim flipped
     magnitude    direction held, size was materially overstated
     bug          a code defect contradicted a stated methods guarantee
     unsupported  the claim outran the evidence that was shown for it
     upheld       checked, survived, and is now stated with its interval
   ========================================================================== */

const CORRECTIONS = [
  {
    id: "C01",
    area: "discoveries",
    severity: "reversed",
    mechanism: "share → rate",
    was: "The ground emptied out: ground share of landed strikes fell 44.3% → 9.4%, so the ground went from the place fights ended to a place fights briefly visit.",
    now: "Ground striking fell 38%, not 79% — and the clinch, listed as dying, is 16% <em>busier</em> per minute than in the 1990s. What actually happened is that distance striking grew 657% and out-voted everything else.",
    detail:
      "Both fighters' combined significant strikes per fight-minute went 2.83 → 8.03 across the window. Multiplying a falling share by a tripling rate is not the same as a falling rate. Per minute of actual cage time: distance 0.86 → 6.50, clinch 0.68 → 0.79, ground 1.22 → 0.76.",
    evidence: "analysis/rates.json · position_delta",
    anchor: "denominator",
  },
  {
    id: "C02",
    area: "discoveries",
    severity: "magnitude",
    mechanism: "no duration denominator",
    was: "Takedown attempts more than doubled, 1.22 → 2.88 per fighter per fight (2.35×).",
    now: "Per minute of fight time the rise is 1.42×, not 2.35× — and it is a single step at the Unified Rules, then twenty-two flat years, not a trend.",
    detail:
      "Mean fight duration rose with the rule change that also fixed the round structure, so the per-fight count is partly measuring the denominator twice. The era series 1.23 → 2.69 → 2.68 → 3.09 → 2.78 → 2.88 has one discontinuity and no slope after it.",
    evidence: "analysis/rates.json · td_series",
    anchor: "denominator",
  },
  {
    id: "C03",
    area: "discoveries",
    severity: "reversed",
    mechanism: "ratio hid a hump",
    was: "Submission hunting declined monotonically — attempts per landed takedown fell 0.785 → 0.279.",
    now: "Submission attempts per fight <em>rose</em> through the BJJ-boom era and then collapsed: 0.99 → 1.16 → 1.32 → 0.90 → 0.61 → 0.59, peaking in 2005–09.",
    detail:
      "The published ratio was monotone only because its denominator (landed takedowns) was climbing throughout. Reporting the numerator on its own recovers a rise-and-fall the ratio had erased.",
    evidence: "analysis/rates.json · sub_series",
    anchor: "hump",
  },
  {
    id: "C04",
    area: "discoveries",
    severity: "reversed",
    mechanism: "unnormalised comparison",
    was: "Submissions are ambushes, not sieges: winners of submissions averaged 144s of control against 266s for decision winners.",
    now: "Submission winners control <em>more</em> of the fight, not less — 39.6% of elapsed time against 28.6% for decision winners, a gap of +11.0 points (95% CI +9.4 to +12.6).",
    detail:
      "A decision runs 15 minutes and a submission ends around 6; the raw-seconds comparison was close to guaranteed by arithmetic before any fighting happened. Expressed as a share of the time actually available, the conclusion inverts. Submissions are sieges that end early.",
    evidence: "analysis/rates.json · control_by_method, control_gap",
    anchor: "control",
  },
  {
    id: "C05",
    area: "code",
    severity: "bug",
    mechanism: "pandas sum() on all-NaN returns 0.0",
    was: "Methods section: \"control figures before 2000 are treated as missing, never as zero.\" bodies_analyze.py:239 summed control seconds without min_count, so untracked fights entered as zero seconds of control.",
    now: "Fixed with <code>.sum(min_count=1)</code>. 360 fighter-fight rows were silently zero; the bias on mean control time was 2.7 seconds (130.4s → 133.1s).",
    detail:
      "The magnitude is small. The problem was never the size of the error — it was that the site could not tell you the size, and the code contradicted a guarantee printed on a page whose entire premise is verified method. analyze.py:212 already used min_count correctly; it just was not carried across.",
    evidence: "analysis/bodies_v2.json · control_min_count_bug",
    anchor: "bug",
  },
  {
    id: "C06",
    area: "discoveries",
    severity: "unsupported",
    mechanism: "corpus n cited for a cell claim",
    was: "\"Computed · n = 41,392 rounds\" printed above the claim that 44% of 1990s landed strikes happened on the ground.",
    now: "That claim rests on 566 fighter-round rows (1.37% of the corpus) from 223 fights (2.54%). Every era cell on the site now prints its own n, and thin cells carry a load-line mark.",
    detail:
      "41,392 is the corpus size, not the cell size, and the cell is what the claim rests on. The quiz section already did this correctly (\"the 1990s arc rests on n = 3\"); the standard is now applied everywhere.",
    evidence: "analysis/rates.json · era_cells",
    anchor: "coverage",
  },
  {
    id: "C07",
    area: "discoveries",
    severity: "magnitude",
    mechanism: "iid intervals on clustered data",
    was: "Forest plot intervals computed as sqrt(p(1-p)/n) with n = fights.",
    now: "Re-estimated with a fighter-level cluster bootstrap. Intervals widen by 1.04× to 1.17× — real, but smaller than the 1.5–2× inflation a reviewer would guess.",
    detail:
      "Fighters recur, so fights are not independent observations. The correction matters less than expected here because most fighters contribute few fights; reporting that honestly is better than either ignoring the dependence or overstating its cost.",
    evidence: "analysis/bodies_v2.json · univariate_forest",
    anchor: "forest",
  },
  {
    id: "C08",
    area: "discoveries",
    severity: "unsupported",
    mechanism: "unadjusted marginals plotted as a forest plot",
    was: "\"Age beats reach\" — a 7-year age gap wins 64.7% against 55.9% for a 5-inch reach gap, plotted in a form that implies adjusted, comparable estimates.",
    now: "Seven years and five inches are not a common scale. Standardised within weight class and fitted jointly: youth +0.343 log-odds per SD, southpaw +0.145, reach +0.099, height −0.017 (interval crosses zero). Age still wins — by 3.5× over reach, on a scale where that sentence means something.",
    detail:
      "Reach, height and weight class are near-collinear, so three rows of the old plot were substantially the same fact drawn three times. One logistic regression on within-class-standardised differentials, no intercept (the design is antisymmetric), fighter-clustered bootstrap.",
    evidence: "analysis/bodies_v2.json · adjusted_forest",
    anchor: "forest",
  },
  {
    id: "C09",
    area: "discoveries",
    severity: "reversed",
    mechanism: "underpowered pooled test",
    was: "Reach does not buy control time — r = −0.055 across career means, pooled over every weight class. Filed as a refuted folk theory.",
    now: "Tested properly, the effect is real and <em>negative</em>: −0.0175 of control share per within-class SD of reach (95% CI −0.026 to −0.009). Longer fighters do not merely fail to control more, they control less.",
    detail:
      "The old test pooled across weight classes (with which reach is near-collinear) and weighted a fighter with one 90-second fight the same as a fighter with twenty. The fight-level version regresses the control-share differential on the reach differential inside the fight, so weight class is held fixed by construction: 7,423 fights, 2,007 fighters. \"Refuted\" was really \"not detected by a test that could not have detected it.\"",
    evidence: "analysis/bodies_v2.json · reach_control_within_fight",
    anchor: "reach-control",
  },
  {
    id: "C10",
    area: "model",
    severity: "reversed",
    mechanism: "metric measured on a superseded model",
    was: "ECE 0.011 — near-perfect calibration. Flagged on the site as measured on the legacy 3-stream model and awaiting re-measurement.",
    now: "Re-measured on the shipped 4-stream bundle: ECE 0.049 (95% CI 0.033 to 0.092). The <0.050 target is met at the point estimate and the interval crosses it. \"Near-perfect\" was never this model's number.",
    detail:
      "The bundle was re-scored on the frozen split and reproduces its own published test metrics to 1e-16, so this is the same model the site ships, not an approximation. The calibration claim survives in the Murphy sense — reliability is 0.0033 — but the headline figure was four times too flattering.",
    evidence: "analysis/model_eval.json · headline.ece",
    anchor: "murphy",
  },
  {
    id: "C11",
    area: "model",
    severity: "upheld",
    mechanism: "assertion replaced with an identity",
    was: "\"Excellent calibration, mediocre discrimination\" — asserted in prose, with neither the sharpness distribution nor a baseline shown.",
    now: "Decomposed: Brier 0.2286 = reliability 0.0033 − resolution 0.0240 + uncertainty 0.2496. The sentence is now an arithmetic identity, and the Brier skill score over the base rate is +0.084.",
    detail:
      "Reliability near zero is the calibration half; resolution of 0.024 against an uncertainty ceiling of 0.250 is the discrimination half. The claim was correct. It just was not evidenced.",
    evidence: "analysis/model_eval.json · murphy_quantile",
    anchor: "murphy",
  },
  {
    id: "C12",
    area: "model",
    severity: "unsupported",
    mechanism: "no distribution was ever shown",
    was: "Nothing on the site showed a distribution — every figure was a mean, a share or a rate.",
    now: "The forecast histogram reveals something no summary metric did: the isotonic calibrator maps 695 distinct blended probabilities onto <b>24 distinct output values</b>, and one of them (0.5621) is assigned to 207 fights — 30% of the test set.",
    detail:
      "Isotonic regression fitted on 504 validation fights is a step function. It earns its calibration honestly — log-loss 0.6463 against 0.6498 for Platt scaling and 0.6512 uncalibrated — but it buys that by quantising the output, so the model has less usable resolution than a continuous probability implies.",
    evidence: "analysis/model_eval2.json · calibrator_audit",
    anchor: "collapse",
  },
  {
    id: "C13",
    area: "model",
    severity: "reversed",
    mechanism: "XGBoost gain → permutation importance",
    was: "\"Style matchup outranks raw output\" — supported by XGBoost gain, which ranked the two archetype-cluster features #1 and #2.",
    now: "Permuted in the held-out test set with all four streams re-scored, those two features do not reach the top 30. The features that actually damage held-out log-loss are age (+0.049), pace mismatch (+0.038) and — third and fourth — the two fighters' UFC fight counts.",
    detail:
      "Gain is biased toward continuous and high-cardinality splits and is unstable across refits, and it was being read off one stream carrying 35% of the ensemble weight to make a claim about the whole system. That both experience counts rank top-4 is the same finding as the debutant blind spot, arriving from a different direction.",
    evidence: "analysis/model_eval2.json · gain_vs_permutation",
    anchor: "importance",
  },
  {
    id: "C14",
    area: "model",
    severity: "upheld",
    mechanism: "point estimates given intervals",
    was: "AUC 0.670 against a 0.740 target (a miss) and Brier 0.229 against 0.225 (\"near\"), both reported bare.",
    now: "Bootstrapped on n = 695: AUC 0.670 [0.630, 0.708] — 0.740 is outside the interval, so the miss is real, not noise. Brier 0.229 [0.218, 0.239] — 0.225 is inside it, so \"near\" is the right word and now there is a reason for it.",
    detail:
      "A calibration-focused portfolio reporting bare point estimates is the one irony a stats-literate reader would enjoy too much.",
    evidence: "analysis/model_eval.json · headline",
    anchor: "results",
  },
  {
    id: "C15",
    area: "model",
    severity: "unsupported",
    mechanism: "input weights presented as a result",
    was: "The ensemble weight bar (35.3 / 29.2 / 23.1 / 12.4) shown as evidence of what each stream contributes.",
    now: "Leave-one-out, refitting weights and calibrator on validation each time: dropping XGBoost costs +0.0072 log-loss, logistic +0.0050, the LSTM +0.0031 — and dropping Elo <b>improves</b> the ensemble by 0.00035. A stream with 12.4% of the weight is contributing nothing.",
    detail:
      "A weight is an input, not a result. The Elo stream is already inside the other three (elo_diff and elo_prob_a are model features), so its marginal value is approximately zero once they are present.",
    evidence: "analysis/model_eval.json · ablation",
    anchor: "ablation",
  },
  {
    id: "C16",
    area: "model",
    severity: "reversed",
    mechanism: "anecdote → measurement",
    was: "The Macau card went 9 of 13, and the misses are blamed on UFC-only fighter history.",
    now: "The model only scored <b>8</b> of those 13 — four were UFC debutants it cannot score and one was a no-contest. On the 8 it scored it went 5, against an expected 5.33 from its own probabilities (central 80%: 4–7). The card is unremarkable; the picks credited to it on the other five were market-led.",
    detail:
      "The right null for a 13-fight card is the Poisson-binomial implied by the model's own per-fight probabilities, not a win rate. The real, measurable version of the Macau story is elsewhere: AUC is 0.718 on fights where both fighters have 5+ UFC bouts and 0.603 where either has fewer than 3 — a gap of 0.114 (95% CI 0.033 to 0.198).",
    evidence: "analysis/model_eval2.json · card_binomial, experience_auc",
    anchor: "experience",
  },
  {
    id: "C17",
    area: "model",
    severity: "unsupported",
    mechanism: "in-sample years plotted as one unbroken line",
    was: "Brier by year drawn 2019–2025 on a single line with the y-axis fitted to the data (min−0.008 to max+0.008), turning a 0.012 spread into full chart height.",
    now: "Train, validation and test years are shaded separately — four of the seven points on the old chart were in-sample — and the axis is anchored so that flat looks flat.",
    detail:
      "The stated point of the chart was stability. An axis scaled to the data makes noise read as trend, and plotting in-sample and out-of-sample years on one continuous line looks like hiding even when it is not.",
    evidence: "analysis/model_eval.json · brier_by_year",
    anchor: "brier-year",
  },
  {
    id: "C18",
    area: "discoveries",
    severity: "upheld",
    mechanism: "promoted from footnote to headline",
    was: "Leg-strike share is flat across twenty-five years — noted in passing as a null result.",
    now: "0.147, 0.172, 0.169, 0.166, 0.161, 0.162. Against a universally believed story about the calf-kick era, this is the strongest result on the page, and it is now the chart it deserved.",
    detail:
      "A dog that didn't bark, drawn against the received wisdom as an explicit expectation line. Nothing was wrong with this finding — it was under-sold.",
    evidence: "analysis/rates.json · leg_by_era",
    anchor: "legkicks",
  },
];

/* Derived: the site's own record. Losses are retractions, and they are not
   given less visual weight than the wins. */
const RECORD = (function () {
  let w = 0, l = 0, d = 0;
  CORRECTIONS.forEach((c) => {
    if (c.severity === "upheld") w++;
    else if (c.severity === "reversed" || c.severity === "bug") l++;
    else d++;
  });
  return { wins: w, losses: l, draws: d, total: CORRECTIONS.length };
})();

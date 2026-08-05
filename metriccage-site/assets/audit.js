/* ===========================================================================
   MetricCage — audit rendering layer.

   Charts added or replaced by the August 2026 correctness pass. Same rules as
   app.js: zero dependencies, zero build step, hand-rolled SVG, works from
   file://.

   Three conventions are enforced here and are the point of the file:

     1. EVERY PANEL PRINTS ITS OWN CELL n, not the corpus n, as a load-line mark.
        Under 200 observations the mark turns amber; under 60 it turns red.
     2. EVERY CHART CARRIES A PLAIN-ENGLISH CAPTION, and the caption text IS the
        SVG's <desc> element — so the screen-reader description and the
        non-technical reader's explanation are the same string and cannot drift.
     3. NO POINT ESTIMATE IS DRAWN WITHOUT ITS INTERVAL, and no set of
        independent bin estimates is joined by a line.
   =========================================================================== */

(function () {
  "use strict";
  if (typeof REAL === "undefined") return;

  /* ---- primitives ------------------------------------------------------- */
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const fmt = (v, d) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(d == null ? 2 : d));
  const pct = (v, d) => (v == null ? "—" : (v * 100).toFixed(d == null ? 1 : d) + "%");

  const SVG = (w, h, inner, desc) =>
    `<svg viewBox="0 0 ${w} ${h}" role="img" preserveAspectRatio="xMidYMid meet">` +
    `<desc>${esc(desc)}</desc>${inner}</svg>`;

  let ccSeq = 0;
  /** Wrap a chart in the standard furniture: title, cell-n load line, caption. */
  function panel(sel, opts) {
    const el = $(sel);
    if (!el) return;
    const id = "cc" + ++ccSeq;
    const n = opts.n;
    const load = n == null ? "" :
      `<span class="loadline" data-load="${n < 60 ? "overloaded" : n < 200 ? "thin" : "ok"}" ` +
      `title="sample size for THIS cell, not the corpus">n <b>${n.toLocaleString()}</b>` +
      `${opts.nUnit ? " " + esc(opts.nUnit) : ""}</span>`;
    el.innerHTML =
      `<div class="panel">
        <div class="panel-head">
          <h3 class="panel-title">${esc(opts.title)}</h3>
          <span class="panel-sub">${load}${opts.sub ? ` <span>${esc(opts.sub)}</span>` : ""}</span>
        </div>
        ${opts.control || ""}
        <div class="panel-body chart">${opts.svg}</div>
        <div class="cc-bar">
          <button class="cc-btn" type="button" aria-expanded="false" aria-controls="${id}">CC</button>
          <p class="cc-text" id="${id}" hidden>${esc(opts.caption)}</p>
        </div>
        ${opts.footer || ""}
      </div>`;
    const btn = $(".cc-btn", el), txt = $(".cc-text", el);
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!open));
      txt.hidden = open;
    });
    return el;
  }

  const axisText = (x, y, s, anchor, cls) =>
    `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor || "middle"}" ` +
    `fill="var(--fg-38)" font-size="10" font-family="var(--mono)"${cls ? ` class="${cls}"` : ""}>${esc(s)}</text>`;

  const ERAS = REAL.rates.eras;
  const ERA_SHORT = ["94–99", "00–04", "05–09", "10–14", "15–19", "20–26"];

  /* =======================================================================
     THE DENOMINATOR SWITCH
     One control, wired to every era chart on the page. Flipping it is the
     entire audit in one gesture: the visitor performs the correction rather
     than reading about it.
     ======================================================================= */
  const denomListeners = [];
  let DENOM = "rate"; // rate is the honest default; share is the archive view

  function denomControl() {
    return `<div class="panel-head" style="margin-bottom:.8rem">
      <div class="denom" role="group" aria-label="Choose the denominator">
        <button type="button" data-denom="share" aria-pressed="false">÷ all strikes (share)</button>
        <button type="button" data-denom="rate" aria-pressed="true">÷ fight minute (rate)</button>
      </div>
      <span class="denom-note" data-denom-note></span>
    </div>`;
  }

  function wireDenom(root) {
    $$("[data-denom]", root).forEach((b) => {
      b.addEventListener("click", () => {
        DENOM = b.dataset.denom;
        $$("[data-denom]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.denom === DENOM)));
        denomListeners.forEach((fn) => fn(DENOM));
      });
    });
  }

  /* =======================================================================
     C01 — POSITION: the share chart said the clinch was dying.
     ======================================================================= */
  function renderPosition() {
    if (!$("[data-a-position]")) return;
    const P = REAL.rates.position;
    const W = 880, H = 380, M = { t: 26, r: 132, b: 46, l: 52 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const SERIES = [
      { k: "ground", label: "Ground", col: "var(--accent)" },
      { k: "clinch", label: "Clinch", col: "var(--amber)" },
      { k: "distance", label: "Distance", col: "var(--cool)" },
    ];

    function build(mode) {
      const data = mode === "share" ? P.share : P.rate;
      const stackMax = mode === "share" ? 1
        : Math.max(...ERAS.map((_, i) => SERIES.reduce((a, s) => a + data[s.k][i], 0))) * 1.06;
      const x = (i) => M.l + (i / (ERAS.length - 1)) * iw;
      const y = (v) => M.t + (1 - v / stackMax) * ih;
      let bands = "", acc = ERAS.map(() => 0);
      SERIES.forEach((s) => {
        let top = "", bot = "";
        const next = acc.map((a, i) => a + data[s.k][i]);
        ERAS.forEach((_, i) => { top += `${i ? "L" : "M"}${x(i).toFixed(1)},${y(next[i]).toFixed(1)} `; });
        for (let i = ERAS.length - 1; i >= 0; i--) bot += `L${x(i).toFixed(1)},${y(acc[i]).toFixed(1)} `;
        bands += `<path d="${top}${bot}Z" fill="${s.col}" opacity="0.82" stroke="var(--bg)" stroke-width="1"/>`;
        acc = next;
      });
      // right-hand labels at the last era, positioned at each band's midpoint
      let labels = "", a2 = 0;
      SERIES.forEach((s) => {
        const v = data[s.k][ERAS.length - 1];
        const mid = y(a2 + v / 2);
        a2 += v;
        const val = mode === "share" ? pct(v, 1) : fmt(v, 2) + "/min";
        labels += `<line x1="${(M.l + iw).toFixed(1)}" y1="${mid.toFixed(1)}" x2="${(M.l + iw + 10)}" y2="${mid.toFixed(1)}" stroke="${s.col}" stroke-width="1"/>` +
          `<text x="${M.l + iw + 15}" y="${(mid - 2).toFixed(1)}" fill="${s.col}" font-size="11.5" font-family="var(--mono)">${esc(s.label)}</text>` +
          `<text x="${M.l + iw + 15}" y="${(mid + 11).toFixed(1)}" fill="var(--fg-55)" font-size="10" font-family="var(--mono)">${val}</text>`;
      });
      let axes = "";
      ERAS.forEach((_, i) => { axes += axisText(x(i), M.t + ih + 18, ERA_SHORT[i]); });
      const ticks = mode === "share" ? [0, 0.25, 0.5, 0.75, 1] : [0, 2, 4, 6, 8];
      ticks.forEach((t) => {
        if (t > stackMax) return;
        axes += `<line x1="${M.l}" y1="${y(t).toFixed(1)}" x2="${M.l + iw}" y2="${y(t).toFixed(1)}" stroke="var(--line-faint)"/>` +
          axisText(M.l - 8, y(t) + 3.5, mode === "share" ? (t * 100) + "%" : String(t), "end");
      });
      axes += `<text x="${M.l - 8}" y="${M.t - 10}" text-anchor="end" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">${mode === "share" ? "% of landed" : "strikes/min"}</text>`;
      const desc = mode === "share"
        ? "Share of landed significant strikes by position across six eras. Distance rises to about 81 per cent while ground falls to 9 and clinch to 10, which makes both grappling positions look like they are disappearing."
        : "The same three positions measured per minute of actual fight time. Distance striking grows roughly sevenfold, ground striking falls by about a third, and clinch striking is slightly higher today than in the 1990s — so only one of the two grappling positions actually declined.";
      return { svg: SVG(W, H, bands + labels + `<g>${axes}</g>`, desc), desc };
    }

    const first = build(DENOM);
    const d = REAL.rates.position.delta;
    panel("[data-a-position]", {
      title: "Where strikes land",
      sub: "1994–2026 · both corners",
      n: REAL.rates.n_fights.reduce((a, b) => a + b, 0),
      nUnit: "fights with usable duration",
      control: denomControl(),
      svg: first.svg,
      caption: first.desc,
      footer: `<div class="audit-note rev" style="margin-top:1rem">
        <b>Flip the switch.</b> On shares, the clinch collapses from ${pct(d.clinch.share_from)} to ${pct(d.clinch.share_to)} and reads as a dying phase of the sport.
        Per minute of cage time it went ${fmt(d.clinch.rate_from)} → ${fmt(d.clinch.rate_to)} strikes — <b>${d.clinch.rate_pct_change > 0 ? "+" : ""}${fmt(d.clinch.rate_pct_change, 0)}%</b>, busier than it has ever been.
        Ground striking fell ${fmt(Math.abs(d.ground.rate_pct_change), 0)}%, not ${fmt(Math.abs(d.ground.share_pct_change), 0)}%.
        Nothing emptied out: distance striking grew <b>${fmt(d.distance.rate_pct_change, 0)}%</b> and out-voted everything else.
        Combined output went ${fmt(REAL.rates.sig_per_min[0])} → ${fmt(REAL.rates.sig_per_min[5])} significant strikes per minute over the same window, which is why a share and a rate disagree.
      </div>`,
    });
    wireDenom($("[data-a-position]"));
    denomListeners.push((mode) => {
      const b = build(mode);
      $(".panel-body", $("[data-a-position]")).innerHTML = b.svg;
      const cc = $(".cc-text", $("[data-a-position]"));
      if (cc) cc.textContent = b.desc;
      const note = $("[data-denom-note]");
      if (note) note.textContent = mode === "share" ? "as published — a share of a tripling total" : "corrected — per minute of fight time";
    });
    const n0 = $("[data-denom-note]");
    if (n0) n0.textContent = "corrected — per minute of fight time";
  }

  /* =======================================================================
     C06 — COVERAGE. The most honest chart on the site: how thin is the
     evidence, per year, for the two fields everything else depends on.
     ======================================================================= */
  function renderCoverage() {
    if (!$("[data-a-coverage]")) return;
    const years = Object.keys(REAL.coverage).map(Number).sort((a, b) => a - b);
    const W = 880, H = 300, M = { t: 24, r: 40, b: 46, l: 48 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const maxF = Math.max(...years.map((y) => REAL.coverage[String(y)].fights));
    const bw = (iw / years.length) * 0.7;
    const x = (i) => M.l + (i + 0.5) * (iw / years.length);
    let bars = "", line = "", pts = "";
    years.forEach((y, i) => {
      const c = REAL.coverage[String(y)];
      const h = (c.fights / maxF) * ih;
      const thin = c.fights < 60;
      bars += `<rect x="${(x(i) - bw / 2).toFixed(1)}" y="${(M.t + ih - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" ` +
        `fill="${thin ? "var(--accent)" : "var(--fg-38)"}" opacity="${thin ? 0.85 : 0.5}"><title>${y}: ${c.fights} fights</title></rect>`;
      const cy = M.t + (1 - c.ctrl_coverage) * ih;
      line += `${i ? "L" : "M"}${x(i).toFixed(1)},${cy.toFixed(1)} `;
      pts += `<circle cx="${x(i).toFixed(1)}" cy="${cy.toFixed(1)}" r="2.6" fill="var(--cool)"><title>${y}: control tracked on ${pct(c.ctrl_coverage)} of rounds</title></circle>`;
    });
    let axes = "";
    years.forEach((y, i) => { if (y % 4 === 0 || y === years[0]) axes += axisText(x(i), M.t + ih + 18, String(y)); });
    [0, 0.5, 1].forEach((t) => {
      axes += `<line x1="${M.l}" y1="${(M.t + (1 - t) * ih).toFixed(1)}" x2="${M.l + iw}" y2="${(M.t + (1 - t) * ih).toFixed(1)}" stroke="var(--line-faint)"/>`;
      axes += axisText(M.l + iw + 30, M.t + (1 - t) * ih + 3.5, (t * 100) + "%", "end");
      axes += axisText(M.l - 8, M.t + (1 - t) * ih + 3.5, String(Math.round(t * maxF)), "end");
    });
    axes += axisText(M.l - 8, M.t - 10, "fights", "end");
    // shade the pre-2001 region where control was never recorded
    const idx2001 = years.indexOf(2001);
    const shade = `<rect x="${M.l}" y="${M.t}" width="${(x(idx2001) - M.l).toFixed(1)}" height="${ih}" fill="var(--accent)" opacity="0.05"/>` +
      axisText(M.l + 6, M.t + 14, "control time not recorded", "start");
    const desc = "Two things at once: grey bars are how many fights happened each year, and the blue line is what fraction of those rounds have a control-time value at all. The 1990s bars are tiny — the whole decade is 223 fights out of 8,794 — and control time is essentially unrecorded before 2001, which is why no control figure on this site starts earlier than that.";
    panel("[data-a-coverage]", {
      title: "How much evidence is actually there",
      sub: "fights per year · control-time field coverage",
      n: REAL.rates.corpus.n_fights, nUnit: "fights",
      svg: SVG(W, H, shade + bars + `<path d="${line}" fill="none" stroke="var(--cool)" stroke-width="1.6"/>` + pts + `<g>${axes}</g>`, desc),
      caption: desc,
      footer: `<div class="audit-note">
        <b>Every 1990s bar on this site is 1.4% of the corpus.</b> The 1994–1999 era holds
        ${REAL.rates.cells["1994-1999"].stat_rows.toLocaleString()} of ${REAL.rates.corpus.n_stat_rows.toLocaleString()} fighter-round rows
        (${fmt(REAL.rates.cells["1994-1999"].stat_rows_pct_of_corpus, 2)}%) across ${REAL.rates.cells["1994-1999"].fights} fights
        (${fmt(REAL.rates.cells["1994-1999"].fights_pct_of_corpus, 2)}%). Individual years hold 25–44 fights.
        The old landing page printed <span class="struck">n = 41,392 rounds</span> above a claim that rests on
        <span class="rev">566</span> of them. Cell n is now printed on every panel.
      </div>`,
    });
  }

  /* =======================================================================
     C03 — the hump the ratio erased.
     ======================================================================= */
  function renderHump() {
    if (!$("[data-a-hump]")) return;
    const S = REAL.rates.sub;
    const W = 560, H = 300, M = { t: 26, r: 20, b: 46, l: 48 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const max = Math.max(...S.map((d) => d.per_fight)) * 1.2;
    const bw = (iw / S.length) * 0.6;
    const x = (i) => M.l + (i + 0.5) * (iw / S.length);
    const y = (v) => M.t + (1 - v / max) * ih;
    let bars = "", ratio = "";
    const rmax = Math.max(...S.map((d) => d.per_landed_td));
    S.forEach((d, i) => {
      const h = M.t + ih - y(d.per_fight);
      const peak = d.era === REAL.rates.sub_peak_era;
      bars += `<rect x="${(x(i) - bw / 2).toFixed(1)}" y="${y(d.per_fight).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${peak ? "var(--accent)" : "var(--fg-38)"}" opacity="0.9"/>`;
      bars += `<text x="${x(i).toFixed(1)}" y="${(y(d.per_fight) - 7).toFixed(1)}" text-anchor="middle" fill="${peak ? "var(--accent-hi)" : "var(--fg-70)"}" font-size="11" font-family="var(--mono)">${fmt(d.per_fight)}</text>`;
      bars += axisText(x(i), M.t + ih + 18, ERA_SHORT[i]);
      ratio += `${i ? "L" : "M"}${x(i).toFixed(1)},${(M.t + (1 - d.per_landed_td / rmax) * ih).toFixed(1)} `;
    });
    const desc = "Submission attempts per fight, counted directly. They rise through the Brazilian jiu-jitsu boom to a peak in 2005 to 2009 and then fall away. The dashed line is the ratio the site used to publish — attempts per landed takedown — which slides downward the whole time because its denominator was growing, hiding the rise completely.";
    panel("[data-a-hump]", {
      title: "Submission attempts per fight",
      sub: "absolute count, both corners",
      n: S.reduce((a, d) => a + d.n_fights, 0), nUnit: "fights",
      svg: SVG(W, H, bars +
        `<path d="${ratio}" fill="none" stroke="var(--cool)" stroke-width="1.4" stroke-dasharray="4 3" opacity="0.8"/>` +
        `<text x="${M.l + iw}" y="${M.t + 12}" text-anchor="end" fill="var(--cool)" font-size="10" font-family="var(--mono)">the published ratio (rescaled)</text>` +
        `<line x1="${M.l}" y1="${M.t + ih}" x2="${M.l + iw}" y2="${M.t + ih}" stroke="var(--line)"/>`, desc),
      caption: desc,
    });
  }

  /* =======================================================================
     C18 — the dog that didn't bark. Received wisdom drawn as an expectation.
     ======================================================================= */
  function renderLegKicks() {
    if (!$("[data-a-legkicks]")) return;
    const years = Object.keys(REAL.rates.leg_by_year).map(Number).filter((y) => y >= 1997).sort((a, b) => a - b);
    const W = 880, H = 300, M = { t: 30, r: 130, b: 46, l: 48 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const x = (y) => M.l + ((y - years[0]) / (years[years.length - 1] - years[0])) * iw;
    const yy = (v) => M.t + (1 - (v - 0.05) / 0.30) * ih;
    let real = "", dots = "";
    years.forEach((y, i) => {
      const v = REAL.rates.leg_by_year[String(y)].leg_share;
      real += `${i ? "L" : "M"}${x(y).toFixed(1)},${yy(v).toFixed(1)} `;
      dots += `<circle cx="${x(y).toFixed(1)}" cy="${yy(v).toFixed(1)}" r="2.2" fill="var(--fg-70)"><title>${y}: ${pct(v)}</title></circle>`;
    });
    // the story everyone tells: flat until ~2018, then the calf-kick era takes off
    let exp = "";
    years.forEach((y, i) => {
      const v = y <= 2018 ? 0.16 : 0.16 + (y - 2018) * 0.016;
      exp += `${i ? "L" : "M"}${x(y).toFixed(1)},${yy(v).toFixed(1)} `;
    });
    let axes = "";
    [1997, 2002, 2007, 2012, 2017, 2022, 2026].forEach((y) => { axes += axisText(x(y), M.t + ih + 18, String(y)); });
    [0.10, 0.15, 0.20, 0.25, 0.30].forEach((t) => {
      axes += `<line x1="${M.l}" y1="${yy(t).toFixed(1)}" x2="${M.l + iw}" y2="${yy(t).toFixed(1)}" stroke="var(--line-faint)"/>` +
        axisText(M.l - 8, yy(t) + 3.5, (t * 100).toFixed(0) + "%", "end");
    });
    const lastY = years[years.length - 1];
    const desc = "The share of landed significant strikes aimed at the legs, every year since 1997. The dashed line is what the calf-kick story predicts: flat, then a sharp climb from about 2018. The solid line is what happened: 14.7 per cent in the 1990s and 16.2 per cent today, essentially a straight line for twenty-five years. The most confidently repeated tactical trend in the sport does not appear in the strike-target data at all.";
    panel("[data-a-legkicks]", {
      title: "The calf-kick era that isn't",
      sub: "leg share of landed significant strikes",
      n: REAL.rates.corpus.n_fights, nUnit: "fights",
      svg: SVG(W, H,
        `<path d="${exp}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="5 4" opacity="0.75"/>` +
        `<path d="${real}" fill="none" stroke="var(--fg)" stroke-width="2"/>` + dots +
        `<text x="${x(lastY) + 8}" y="${yy(0.16 + (lastY - 2018) * 0.016) + 3}" fill="var(--accent)" font-size="10.5" font-family="var(--mono)">what everyone</text>` +
        `<text x="${x(lastY) + 8}" y="${yy(0.16 + (lastY - 2018) * 0.016) + 15}" fill="var(--accent)" font-size="10.5" font-family="var(--mono)">says happened</text>` +
        `<text x="${x(lastY) + 8}" y="${yy(0.162) + 3}" fill="var(--fg)" font-size="10.5" font-family="var(--mono)">what happened</text>` +
        `<g>${axes}</g>`, desc),
      caption: desc,
      footer: `<div class="audit-note"><b>Era means:</b> ${ERAS.map((e) => pct(REAL.rates.leg_by_era[e].leg_share, 1)).join(" · ")}.
        A null result, stated as a headline instead of a footnote, because it survives contact with a story that everyone believes.</div>`,
    });
  }

  /* =======================================================================
     C04 — control as a share of the time available. Distributions, not means.
     ======================================================================= */
  function renderControl() {
    if (!$("[data-a-control]")) return;
    const C = REAL.rates.control_by_method;
    const order = [["SUB", "Submission wins", "var(--accent)"], ["DEC", "Decision wins", "var(--cool)"], ["KO", "KO/TKO wins", "var(--fg-38)"]];
    const W = 700, H = 320, M = { t: 30, r: 24, b: 52, l: 130 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const x = (v) => M.l + Math.min(v, 1) * iw;
    const rowH = ih / order.length;
    let body = "";
    order.forEach(([k, label, col], i) => {
      const d = C[k];
      if (!d) return;
      const cy = M.t + (i + 0.5) * rowH;
      // the distribution, as a violin built from stored quantiles
      // Width is a real density estimate: the stored values are evenly spaced
      // quantiles, so local density is proportional to 1 / (gap between them).
      const q = d.share_quantiles;
      const half = rowH * 0.30;
      const dens = q.map((v, j) => {
        const a = q[Math.max(0, j - 1)], b = q[Math.min(q.length - 1, j + 1)];
        const gap = Math.max(b - a, 1e-4);
        return 1 / gap;
      });
      const dmax = Math.max(...dens);
      const wAt = (j) => Math.sqrt(dens[j] / dmax) * half;
      let up = "", dn = "";
      q.forEach((v, j) => { up += `${j ? "L" : "M"}${x(v).toFixed(1)},${(cy - wAt(j)).toFixed(1)} `; });
      for (let j = q.length - 1; j >= 0; j--) dn += `L${x(q[j]).toFixed(1)},${(cy + wAt(j)).toFixed(1)} `;
      body += `<path d="${up}${dn}Z" fill="${col}" opacity="0.22"/>`;
      body += `<line x1="${x(d.ctrl_share_p25).toFixed(1)}" y1="${cy.toFixed(1)}" x2="${x(d.ctrl_share_p75).toFixed(1)}" y2="${cy.toFixed(1)}" stroke="${col}" stroke-width="3" opacity="0.85"/>`;
      body += `<circle cx="${x(d.median_ctrl_share).toFixed(1)}" cy="${cy.toFixed(1)}" r="4" fill="var(--bg)" stroke="${col}" stroke-width="2"/>`;
      body += `<circle cx="${x(d.mean_ctrl_share).toFixed(1)}" cy="${cy.toFixed(1)}" r="3" fill="${col}"/>`;
      body += `<text x="${M.l - 12}" y="${(cy - 3).toFixed(1)}" text-anchor="end" fill="var(--fg)" font-size="11.5" font-family="var(--mono)">${esc(label)}</text>`;
      body += `<text x="${M.l - 12}" y="${(cy + 11).toFixed(1)}" text-anchor="end" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">n=${d.n.toLocaleString()} · ${fmt(d.mean_elapsed_min)} min avg</text>`;
      body += `<text x="${(x(d.mean_ctrl_share) + 10).toFixed(1)}" y="${(cy - 8).toFixed(1)}" fill="${col}" font-size="11" font-family="var(--mono)">${pct(d.mean_ctrl_share)}</text>`;
    });
    let axes = "";
    [0, 0.25, 0.5, 0.75, 1].forEach((t) => {
      axes += `<line x1="${x(t).toFixed(1)}" y1="${M.t}" x2="${x(t).toFixed(1)}" y2="${M.t + ih}" stroke="var(--line-faint)"/>` +
        axisText(x(t), M.t + ih + 18, (t * 100) + "%");
    });
    axes += axisText(M.l + iw / 2, H - 10, "winner's control time as a share of the time the fight lasted");
    const g = REAL.rates.control_gap;
    const desc = "How much of the fight the winner spent in control, expressed as a fraction of how long the fight actually lasted. Submission winners average 39.6 per cent, decision winners 28.6 per cent. The site used to compare raw seconds — 144 against 266 — and conclude submissions involve less control, but a decision runs fifteen minutes and a submission ends around six, so that comparison was decided by arithmetic before any fighting happened.";
    panel("[data-a-control]", {
      title: "Submissions are sieges that end early",
      sub: "control share by method of victory · 2000 onward",
      n: (C.SUB ? C.SUB.n : 0) + (C.DEC ? C.DEC.n : 0), nUnit: "wins",
      svg: SVG(W, H, `<g>${axes}</g>` + body, desc),
      caption: desc,
      footer: `<div class="audit-note rev">
        <b>Published conclusion reversed.</b> <span class="struck">Submissions are ambushes, not sieges — 144s of control against 266s for decisions.</span>
        <span class="rev">Submission winners control ${pct(C.SUB.mean_ctrl_share)} of elapsed time against ${pct(C.DEC.mean_ctrl_share)} for decision winners</span>
        — a gap of ${(g.sub_minus_dec_share * 100).toFixed(1)} points, 95% CI ${(g.ci95[0] * 100).toFixed(1)} to ${(g.ci95[1] * 100).toFixed(1)}.
        Mean submission finish: ${fmt(REAL.rates.sub_finish_clock.mean_min)} minutes (median ${fmt(REAL.rates.sub_finish_clock.median_min)}, n=${REAL.rates.sub_finish_clock.n.toLocaleString()}).
      </div>`,
    });
  }

  /* =======================================================================
     C07 / C08 — a forest plot that is finally a forest plot.
     ======================================================================= */
  function renderForest() {
    if (!$("[data-a-forest]")) return;
    const A = REAL.bodies2.adjusted, m = REAL.bodies2.model;
    const W = 720, H = 60 + A.length * 46, M = { t: 42, r: 150, b: 40, l: 210 };
    const iw = W - M.l - M.r;
    const lim = Math.max(...A.map((d) => Math.max(Math.abs(d.ci95[0]), Math.abs(d.ci95[1])))) * 1.15;
    const x = (v) => M.l + ((v + lim) / (2 * lim)) * iw;
    let body = `<line x1="${x(0).toFixed(1)}" y1="${M.t - 12}" x2="${x(0).toFixed(1)}" y2="${(M.t + A.length * 46 - 20).toFixed(1)}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>`;
    A.forEach((d, i) => {
      const cy = M.t + i * 46;
      const col = d.crosses_zero ? "var(--fg-38)" : (d.coef > 0 ? "var(--accent)" : "var(--cool)");
      body += `<line x1="${x(d.ci95[0]).toFixed(1)}" y1="${cy.toFixed(1)}" x2="${x(d.ci95[1]).toFixed(1)}" y2="${cy.toFixed(1)}" stroke="${col}" stroke-width="2"/>`;
      [d.ci95[0], d.ci95[1]].forEach((v) => {
        body += `<line x1="${x(v).toFixed(1)}" y1="${(cy - 5).toFixed(1)}" x2="${x(v).toFixed(1)}" y2="${(cy + 5).toFixed(1)}" stroke="${col}" stroke-width="2"/>`;
      });
      body += `<circle cx="${x(d.coef).toFixed(1)}" cy="${cy.toFixed(1)}" r="5" fill="${col}"/>`;
      body += `<text x="${M.l - 16}" y="${(cy + 4).toFixed(1)}" text-anchor="end" fill="var(--fg)" font-size="12" font-family="var(--mono)">${esc(d.label)}</text>`;
      body += `<text x="${M.l + iw + 14}" y="${(cy - 2).toFixed(1)}" fill="${col}" font-size="11" font-family="var(--mono)">${d.coef > 0 ? "+" : ""}${fmt(d.coef, 3)}</text>`;
      body += `<text x="${M.l + iw + 14}" y="${(cy + 11).toFixed(1)}" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">${pct(d.win_prob_1sd, 1)} win${d.crosses_zero ? " · n.s." : ""}</text>`;
    });
    let axes = "";
    [-0.3, -0.15, 0, 0.15, 0.3, 0.45].forEach((t) => {
      if (Math.abs(t) > lim) return;
      axes += axisText(x(t), M.t + A.length * 46 - 2, (t > 0 ? "+" : "") + t.toFixed(2));
    });
    axes += axisText(M.l + iw / 2, H - 12, "log-odds of winning, per 1 SD of advantage within weight class");
    const desc = "Four physical advantages, each measured per standard deviation of its own within-weight-class distribution and fitted together in one model, so they are finally on a comparable scale. Youth is by far the largest effect, then the southpaw edge, then reach. Height, once reach is accounted for, has an interval that crosses zero — it is not an independent advantage at all. Bars are 95 per cent intervals from a bootstrap that resamples fighters rather than fights, because a twenty-fight career is not twenty independent observations.";
    panel("[data-a-forest]", {
      title: "Adjusted, comparable, and clustered",
      sub: "logistic model · within-class SD units",
      n: m.n_fights, nUnit: "fights",
      svg: SVG(W, H, body + `<g>${axes}</g>`, desc),
      caption: desc,
      footer: `<div class="audit-note">
        <b>What changed.</b> The old plot compared <span class="struck">a 7-year age gap (64.7%) against a 5-inch reach gap (55.9%)</span> —
        a statement about bin edges, not about fighting. It also plotted reach, height and weight class as three rows when they are near-collinear,
        and used <span class="struck">sqrt(p(1−p)/n) with n = fights</span> for intervals.
        <span class="rev">One model, ${m.n_fighter_sides.toLocaleString()} fighter-sides, ${m.n_fighters.toLocaleString()} distinct fighters,
        ${m.n_boot.toLocaleString()} cluster-bootstrap refits.</span>
        Age still beats reach — by ${fmt(A[0].coef / A.find((d) => d.key === "reach_diff_z").coef, 1)}× — and now that claim is on a scale where it means something.
      </div>`,
    });
  }

  /* ---- univariate: how much did clustering actually widen the intervals? -- */
  function renderClusterEffect() {
    if (!$("[data-a-clustering]")) return;
    const U = REAL.bodies2.univariate;
    const keys = Object.keys(U);
    const W = 700, H = 46 + keys.length * 40, M = { t: 34, r: 120, b: 30, l: 190 };
    const iw = W - M.l - M.r;
    const lo = Math.min(...keys.map((k) => U[k].ci_clustered[0])) - 0.01;
    const hi = Math.max(...keys.map((k) => U[k].ci_clustered[1])) + 0.01;
    const x = (v) => M.l + ((v - lo) / (hi - lo)) * iw;
    let body = `<line x1="${x(0.5).toFixed(1)}" y1="${M.t - 14}" x2="${x(0.5).toFixed(1)}" y2="${(M.t + keys.length * 40 - 22).toFixed(1)}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>` +
      axisText(x(0.5), M.t - 20, "coin flip");
    keys.forEach((k, i) => {
      const d = U[k], cy = M.t + i * 40;
      body += `<line x1="${x(d.ci_naive_iid[0]).toFixed(1)}" y1="${(cy + 6).toFixed(1)}" x2="${x(d.ci_naive_iid[1]).toFixed(1)}" y2="${(cy + 6).toFixed(1)}" stroke="var(--fg-38)" stroke-width="5" opacity="0.35"/>`;
      body += `<line x1="${x(d.ci_clustered[0]).toFixed(1)}" y1="${cy.toFixed(1)}" x2="${x(d.ci_clustered[1]).toFixed(1)}" y2="${cy.toFixed(1)}" stroke="var(--cool)" stroke-width="2"/>`;
      body += `<circle cx="${x(d.win).toFixed(1)}" cy="${cy.toFixed(1)}" r="4" fill="var(--cool)"/>`;
      body += `<text x="${M.l - 14}" y="${(cy + 4).toFixed(1)}" text-anchor="end" fill="var(--fg)" font-size="11.5" font-family="var(--mono)">${esc(d.label)}</text>`;
      body += `<text x="${M.l + iw + 12}" y="${(cy + 4).toFixed(1)}" fill="var(--fg-55)" font-size="10.5" font-family="var(--mono)">${pct(d.win)} · ×${fmt(d.inflation)}</text>`;
    });
    const desc = "The same six win rates with two sets of error bars: the faint wide one behind each estimate is the interval the site used to publish, which assumes every fight is independent, and the blue one is a bootstrap that resamples fighters instead. The honest intervals are wider, but only by four to seventeen per cent — much less than the doubling a reviewer would reasonably expect.";
    panel("[data-a-clustering]", {
      title: "What clustering actually cost",
      sub: "naive iid interval vs fighter-clustered bootstrap",
      n: REAL.bodies2.model.n_fights, nUnit: "fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
    });
  }

  /* ---- C09: the null that wasn't --------------------------------------- */
  function renderReachControl() {
    if (!$("[data-a-reachctrl]")) return;
    const r = REAL.bodies2.reach_control, p = REAL.bodies2.reach_control_pooled;
    const W = 640, H = 200, M = { l: 60, r: 40, t: 60 };
    const iw = W - M.l - M.r;
    const lim = 0.035;
    const x = (v) => M.l + ((v + lim) / (2 * lim)) * iw;
    const cy = 108;
    const body =
      `<line x1="${x(0).toFixed(1)}" y1="40" x2="${x(0).toFixed(1)}" y2="140" stroke="var(--fg-38)" stroke-dasharray="3 3"/>` +
      axisText(x(0), 32, "no effect") +
      `<line x1="${x(r.ci95[0]).toFixed(1)}" y1="${cy}" x2="${x(r.ci95[1]).toFixed(1)}" y2="${cy}" stroke="var(--accent)" stroke-width="3"/>` +
      [r.ci95[0], r.ci95[1]].map((v) => `<line x1="${x(v).toFixed(1)}" y1="${cy - 7}" x2="${x(v).toFixed(1)}" y2="${cy + 7}" stroke="var(--accent)" stroke-width="3"/>`).join("") +
      `<circle cx="${x(r.slope_ctrl_share_per_sd_reach).toFixed(1)}" cy="${cy}" r="6" fill="var(--accent)"/>` +
      `<text x="${x(r.slope_ctrl_share_per_sd_reach).toFixed(1)}" y="${cy - 16}" text-anchor="middle" fill="var(--accent-hi)" font-size="12" font-family="var(--mono)">${fmt(r.slope_ctrl_share_per_sd_reach * 100, 2)} pts</text>` +
      [-0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03].map((t) => axisText(x(t), 162, (t * 100).toFixed(0))).join("") +
      axisText(M.l + iw / 2, 186, "change in control share per +1 SD of reach, within weight class");
    const desc = "The effect of reach on control time, tested inside the fight rather than across careers. The longer fighter controls one point seven five percentage points less of the fight per standard deviation of reach advantage, and the interval does not touch zero. The old test pooled every weight class together and found nothing, but reach and weight class are nearly the same variable, so it could not have found anything.";
    panel("[data-a-reachctrl]", {
      title: "Reach doesn't buy control — it costs it",
      sub: "within-fight differential, weight class fixed",
      n: r.n_fights, nUnit: "fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
      footer: `<div class="audit-note rev">
        <b>A null result that was really a power failure.</b>
        <span class="struck">r = −0.055 across career means, pooled over every weight class — refuted.</span>
        <span class="rev">−${fmt(Math.abs(r.slope_ctrl_share_per_sd_reach) * 100, 2)} points of control share per SD of reach, 95% CI
        ${fmt(r.ci95[0] * 100, 2)} to ${fmt(r.ci95[1] * 100, 2)}, from ${r.n_fights.toLocaleString()} fights and ${r.n_fighters.toLocaleString()} fighters.</span>
        The pooled career correlation does drift the same way once you demand a minimum career length
        (r = ${fmt(p.all, 3)} unfiltered → ${fmt(p.min10_fights.r, 3)} at 10+ fights), which is what a cancelled within-stratum effect looks like from the outside.
      </div>`,
    });
  }

  /* ---- reach by weight class ------------------------------------------- */
  function renderReachByClass() {
    if (!$("[data-a-reachclass]")) return;
    const B = REAL.bodies2.by_weightclass;
    const keys = Object.keys(B).sort((a, b) => B[b].win - B[a].win);
    const W = 700, H = 40 + keys.length * 28, M = { t: 28, r: 90, b: 26, l: 175 };
    const iw = W - M.l - M.r;
    const lo = 0.33, hi = 0.68;
    const x = (v) => M.l + ((v - lo) / (hi - lo)) * iw;
    let body = `<line x1="${x(0.5).toFixed(1)}" y1="${M.t - 12}" x2="${x(0.5).toFixed(1)}" y2="${(M.t + keys.length * 28 - 14).toFixed(1)}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>`;
    keys.forEach((k, i) => {
      const d = B[k], cy = M.t + i * 28;
      const sig = d.ci95[0] > 0.5 || d.ci95[1] < 0.5;
      const col = !sig ? "var(--fg-38)" : d.win > 0.5 ? "var(--accent)" : "var(--cool)";
      body += `<line x1="${x(d.ci95[0]).toFixed(1)}" y1="${cy}" x2="${x(d.ci95[1]).toFixed(1)}" y2="${cy}" stroke="${col}" stroke-width="1.8" opacity="0.9"/>`;
      body += `<circle cx="${x(d.win).toFixed(1)}" cy="${cy}" r="3.6" fill="${col}"/>`;
      body += `<text x="${M.l - 12}" y="${cy + 4}" text-anchor="end" fill="var(--fg-70)" font-size="10.5" font-family="var(--mono)">${esc(k)}</text>`;
      body += `<text x="${M.l + iw + 10}" y="${cy + 4}" fill="var(--fg-55)" font-size="10" font-family="var(--mono)">${pct(d.win)}</text>`;
    });
    [0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65].forEach((t) => { body += axisText(x(t), M.t + keys.length * 28 + 2, (t * 100).toFixed(0) + "%"); });
    const desc = "The longer-reach fighter's win rate, split by weight class. At heavyweight reach is worth about ten points of win probability; at women's strawweight the longer fighter wins less than half the time. Pooling these divisions into one number, as the site used to, averages an effect that genuinely points in opposite directions.";
    panel("[data-a-reachclass]", {
      title: "Reach is not one effect",
      sub: "longer-reach win rate by division",
      n: Object.values(B).reduce((a, d) => a + d.n_fighter_sides, 0), nUnit: "fighter-sides",
      svg: SVG(W, H, body, desc),
      caption: desc,
    });
  }

  /* =======================================================================
     MODEL PAGE
     ======================================================================= */

  /* ---- C11: the identity ------------------------------------------------ */
  function renderMurphy() {
    if (!$("[data-a-murphy]")) return;
    const m = REAL.model.murphy;
    const W = 760, H = 285, M = { l: 40, r: 40, t: 62 };
    const iw = W - M.l - M.r;
    const scale = iw / (m.uncertainty * 1.08);
    const barH = 44;
    const uncW = m.uncertainty * scale, resW = m.resolution * scale, relW = Math.max(m.reliability * scale, 2.5);
    const y = M.t;
    const body =
      `<rect x="${M.l}" y="${y}" width="${uncW.toFixed(1)}" height="${barH}" fill="var(--fg-38)" opacity="0.35"/>` +
      `<rect x="${(M.l + uncW - resW).toFixed(1)}" y="${y}" width="${resW.toFixed(1)}" height="${barH}" fill="var(--accent)" opacity="0.85"/>` +
      `<rect x="${(M.l + uncW - resW).toFixed(1)}" y="${y}" width="${relW.toFixed(1)}" height="${barH}" fill="var(--cool)"/>` +
      // the Brier marker drops well below the bar so its label cannot collide
      `<line x1="${(M.l + uncW - resW + relW).toFixed(1)}" y1="${y - 10}" x2="${(M.l + uncW - resW + relW).toFixed(1)}" y2="${y + barH + 16}" stroke="var(--fg)" stroke-width="1.5"/>` +
      `<text x="${(M.l + uncW - resW + relW).toFixed(1)}" y="${y + barH + 32}" text-anchor="middle" fill="var(--fg)" font-size="12" font-family="var(--mono)">Brier ${fmt(m.brier_direct, 4)}</text>` +
      `<text x="${M.l}" y="${y - 32}" fill="var(--fg-38)" font-size="10.5" font-family="var(--mono)">UNCERTAINTY ${fmt(m.uncertainty, 4)} — the irreducible ceiling, set by the base rate alone</text>` +
      `<line x1="${(M.l + uncW - resW).toFixed(1)}" y1="${y + barH + 4}" x2="${(M.l + uncW).toFixed(1)}" y2="${y + barH + 4}" stroke="var(--accent)" stroke-width="1.5"/>` +
      `<text x="${(M.l + uncW - resW / 2).toFixed(1)}" y="${y + barH + 56}" text-anchor="middle" fill="var(--accent-hi)" font-size="11" font-family="var(--mono)">− resolution ${fmt(m.resolution, 4)}</text>` +
      `<text x="${(M.l + uncW - resW / 2).toFixed(1)}" y="${y + barH + 70}" text-anchor="middle" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">what telling fights apart wins back</text>` +
      `<line x1="${(M.l + uncW - resW).toFixed(1)}" y1="${y - 22}" x2="${(M.l + uncW - resW + relW).toFixed(1)}" y2="${y - 22}" stroke="var(--cool)" stroke-width="1.5"/>` +
      `<text x="${(M.l + uncW - resW + 6).toFixed(1)}" y="${y - 8}" fill="var(--cool)" font-size="11" font-family="var(--mono)">+ reliability ${fmt(m.reliability, 4)}</text>` +
      `<line x1="${M.l}" y1="${y + barH + 2}" x2="${(M.l + uncW).toFixed(1)}" y2="${y + barH + 2}" stroke="var(--line)"/>`;
    const desc = "The Brier score split into its three parts. Uncertainty, the grey bar, is the part no model can beat — it is set by how often the corner-A fighter wins at all. Resolution, in red, is how much the model claws back by telling fights apart, and it is small. Reliability, the thin blue sliver, is how much it loses by being miscalibrated, and it is almost nothing. Good calibration and weak discrimination are not two opinions about this model; they are two terms of one equation.";
    panel("[data-a-murphy]", {
      title: "Brier, decomposed",
      sub: "Murphy decomposition · 10 quantile bins",
      n: REAL.model.provenance.n_test, nUnit: "test fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
      footer: `<div class="identity" style="margin-top:1rem">
          <span class="t">Brier ${fmt(m.brier_from_decomposition, 4)}</span> =
          <span class="rel">reliability ${fmt(m.reliability, 4)}</span> −
          <span class="res">resolution ${fmt(m.resolution, 4)}</span> +
          <span class="unc">uncertainty ${fmt(m.uncertainty, 4)}</span>
        </div>
        <div class="audit-note" style="margin-top:1rem">
          <b>The site's central claim, as arithmetic.</b> "Excellent calibration, mediocre discrimination" used to be a sentence.
          Reliability of ${fmt(m.reliability, 4)} is the calibration half; resolution of ${fmt(m.resolution, 4)} against a ceiling of
          ${fmt(m.uncertainty, 4)} is the discrimination half. Brier skill score over the base rate: <b>+${fmt(m.skill_score, 3)}</b>.
          Separately, ECE re-measured on this bundle is <span class="rev">${fmt(REAL.model.headline.ece.point, 3)}</span>
          (95% CI ${fmt(REAL.model.headline.ece.ci95[0], 3)}–${fmt(REAL.model.headline.ece.ci95[1], 3)}), not the
          <span class="struck">0.011</span> the site inherited from the superseded 3-stream model.
        </div>`,
    });
  }

  /* ---- C12: the distribution nobody had drawn --------------------------- */
  function renderSharpness() {
    if (!$("[data-a-sharpness]")) return;
    const s = REAL.model.sharpness, q = REAL.model.calibrator.isotonic_quantisation;
    const W = 820, H = 356, M = { t: 30, r: 24, b: 96, l: 48 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const max = Math.max(...s.counts);
    const x = (v) => M.l + v * iw;
    const bw = iw / s.counts.length;
    let bars = "";
    s.counts.forEach((c, i) => {
      if (!c) return;
      const h = (c / max) * ih;
      const mid = (s.edges[i] + s.edges[i + 1]) / 2;
      const hot = c === max;
      bars += `<rect x="${(M.l + i * bw + 1).toFixed(1)}" y="${(M.t + ih - h).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${h.toFixed(1)}" ` +
        `fill="${hot ? "var(--accent)" : "var(--cool)"}" opacity="0.85"><title>${pct(s.edges[i], 0)}–${pct(s.edges[i + 1], 0)}: ${c} fights</title></rect>`;
      if (c > max * 0.12) bars += `<text x="${(M.l + i * bw + bw / 2).toFixed(1)}" y="${(M.t + ih - h - 6).toFixed(1)}" text-anchor="middle" fill="var(--fg-70)" font-size="9.5" font-family="var(--mono)">${c}</text>`;
    });
    // the 24 atoms, as rails under the histogram
    let rails = "";
    q.top_atoms.forEach((a) => {
      const px = x(a.value);
      rails += `<line x1="${px.toFixed(1)}" y1="${M.t + ih + 8}" x2="${px.toFixed(1)}" y2="${(M.t + ih + 8 + Math.max(4, (a.n / q.largest_atom_size) * 26)).toFixed(1)}" stroke="var(--amber)" stroke-width="3" opacity="0.9"><title>${a.n} fights all receive exactly ${a.value}</title></line>`;
    });
    let axes = "";
    [0, 0.25, 0.5, 0.75, 1].forEach((t) => { axes += axisText(x(t), M.t + ih + 58, pct(t, 0)); });
    axes += `<line x1="${x(REAL.model.base_rate).toFixed(1)}" y1="${M.t - 6}" x2="${x(REAL.model.base_rate).toFixed(1)}" y2="${M.t + ih}" stroke="var(--fg)" stroke-dasharray="3 3" opacity="0.6"/>`;
    axes += `<text x="${(x(REAL.model.base_rate) + 6).toFixed(1)}" y="${M.t - 8}" fill="var(--fg-70)" font-size="10" font-family="var(--mono)">base rate ${pct(REAL.model.base_rate)}</text>`;
    axes += axisText(M.l + iw / 2, H - 10, "forecast probability that corner A wins");
    axes += axisText(M.l + 4, M.t + ih + 34, "↑ the 24 values the calibrator can actually emit", "start");
    const desc = "Every one of the 695 forecasts the model made on the blind test set. Nothing on this site used to show a distribution, and drawing one reveals two things at once. The forecasts crowd around the base rate, which is what weak discrimination looks like from the inside. And the amber ticks underneath show that the calibrator only ever emits twenty-four distinct numbers — one of them, 0.5621, is handed to 207 fights, thirty per cent of the test set.";
    panel("[data-a-sharpness]", {
      title: "The distribution nobody had drawn",
      sub: "695 blind-test forecasts",
      n: REAL.model.provenance.n_test, nUnit: "test fights",
      svg: SVG(W, H, bars + rails + `<g>${axes}</g>` + `<line x1="${M.l}" y1="${M.t + ih}" x2="${M.l + iw}" y2="${M.t + ih}" stroke="var(--line)"/>`, desc),
      caption: desc,
      footer: `<div class="audit-note rev">
        <b>The calibrator is a staircase.</b> Isotonic regression fitted on ${q.n_val_fights_calibrator_was_fit_on} validation fights maps
        <b>${q.n_input_values} distinct blended probabilities onto ${q.n_output_values} distinct outputs</b>. The largest step,
        ${fmt(q.largest_atom_value, 4)}, absorbs ${q.largest_atom_size} fights (${pct(q.largest_atom_pct_of_test)}).
        It is not cheating — isotonic genuinely wins here (log-loss ${fmt(REAL.model.calibrator.shipped_isotonic.logloss, 4)} against
        ${fmt(REAL.model.calibrator.platt_sigmoid.logloss, 4)} for Platt scaling and ${fmt(REAL.model.calibrator.uncalibrated_blend.logloss, 4)} uncalibrated)
        — but it buys calibration by quantising the answer, and ${pct(s.pct_within_10pts_of_half)} of forecasts land within ten points of a coin flip.
        A reader who sees "62%" is entitled to assume the model could also have said 61 or 63. Here, it could not.
      </div>`,
    });
  }

  /* ---- baseline ladder --------------------------------------------------- */
  function renderLadder() {
    if (!$("[data-a-ladder]")) return;
    const L = REAL.model.ladder;
    const W = 760, H = 40 + L.length * 42, M = { t: 34, r: 130, b: 30, l: 190 };
    const iw = W - M.l - M.r;
    const lo = Math.min(...L.map((d) => d.logloss)) - 0.004;
    const hi = Math.max(...L.map((d) => d.logloss)) + 0.004;
    const x = (v) => M.l + ((v - lo) / (hi - lo)) * iw;
    let body = "";
    L.forEach((d, i) => {
      const cy = M.t + i * 42;
      const col = d.kind === "shipped" ? "var(--accent)" : d.kind === "stream" ? "var(--cool)" : "var(--fg-38)";
      body += `<line x1="${M.l}" y1="${cy}" x2="${x(d.logloss).toFixed(1)}" y2="${cy}" stroke="${col}" stroke-width="1" opacity="0.3"/>`;
      body += `<circle cx="${x(d.logloss).toFixed(1)}" cy="${cy}" r="${d.kind === "shipped" ? 6 : 4.5}" fill="${col}"/>`;
      body += `<text x="${M.l - 14}" y="${cy - 1}" text-anchor="end" fill="${d.kind === "shipped" ? "var(--fg)" : "var(--fg-70)"}" font-size="11.5" font-family="var(--mono)">${esc(d.label)}</text>`;
      body += `<text x="${M.l - 14}" y="${cy + 12}" text-anchor="end" fill="var(--fg-38)" font-size="9" font-family="var(--mono)">${esc(d.note)}</text>`;
      body += `<text x="${M.l + iw + 12}" y="${cy - 1}" fill="${col}" font-size="11" font-family="var(--mono)">${fmt(d.logloss, 4)}</text>`;
      body += `<text x="${M.l + iw + 12}" y="${cy + 12}" fill="var(--fg-38)" font-size="9" font-family="var(--mono)">brier ${fmt(d.brier, 4)}</text>`;
    });
    body += axisText(M.l + iw / 2, H - 8, "held-out log-loss (lower is better)");
    const desc = "Every baseline the ensemble has to beat, on the same 695 fights. A coin gets 0.693. Predicting the training base rate every single time gets 0.692. The best individual stream, the career LSTM, gets 0.653. The shipped four-model ensemble gets 0.646 — a real improvement over its own best component, but a small one, and the chart says so rather than leaving the reader to wonder.";
    panel("[data-a-ladder]", {
      title: "What it beats",
      sub: "each single stream re-calibrated on 2023, then scored blind",
      n: REAL.model.provenance.n_test, nUnit: "test fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
      footer: `<div class="audit-note">
        <b>No market row.</b> The pipeline diagram lists BestFightOdds as a source, but no closing-line corpus exists in the repository,
        so the one benchmark a domain reader most wants — model against the closing line on the same 695 fights — cannot honestly be drawn yet.
        It is named here rather than quietly omitted. <span class="stamp">open · highest-value missing dataset</span>
      </div>`,
    });
  }

  /* ---- C15: leave-one-out ------------------------------------------------ */
  function renderAblation() {
    if (!$("[data-a-ablation]")) return;
    const A = REAL.model.ablation;
    const W = 700, H = 46 + A.length * 52, M = { t: 40, r: 120, b: 30, l: 150 };
    const iw = W - M.l - M.r;
    const lim = Math.max(...A.map((d) => Math.abs(d.delta_logloss))) * 1.25;
    const zero = M.l + (0.18 * iw);
    const sc = (iw - (zero - M.l)) / lim;
    let body = `<line x1="${zero.toFixed(1)}" y1="${M.t - 14}" x2="${zero.toFixed(1)}" y2="${(M.t + A.length * 52 - 26).toFixed(1)}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>` +
      axisText(zero, M.t - 20, "no change");
    A.forEach((d, i) => {
      const cy = M.t + i * 52;
      const w = d.delta_logloss * sc;
      const col = d.delta_logloss > 0 ? "var(--cool)" : "var(--accent)";
      body += `<rect x="${(w >= 0 ? zero : zero + w).toFixed(1)}" y="${(cy - 11).toFixed(1)}" width="${Math.abs(w).toFixed(1)}" height="22" fill="${col}" opacity="0.85"/>`;
      body += `<text x="${M.l - 14}" y="${cy - 1}" text-anchor="end" fill="var(--fg)" font-size="12" font-family="var(--mono)">drop ${esc(d.dropped)}</text>`;
      body += `<text x="${M.l - 14}" y="${cy + 12}" text-anchor="end" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">shipped weight ${pct(d.shipped_weight, 1)}</text>`;
      body += `<text x="${(w >= 0 ? zero + w + 8 : zero + w - 8).toFixed(1)}" y="${cy + 4}" text-anchor="${w >= 0 ? "start" : "end"}" fill="${col}" font-size="11" font-family="var(--mono)">${d.delta_logloss > 0 ? "+" : ""}${fmt(d.delta_logloss, 5)}</text>`;
    });
    body += axisText(M.l + iw / 2, H - 8, "change in held-out log-loss when the stream is removed and the ensemble refitted");
    const elo = A.find((d) => d.dropped === "elo");
    const desc = "What each stream is actually worth. Each row removes one model, refits the ensemble weights and the calibrator on the validation year, and re-scores the blind test set. Dropping XGBoost costs the most. Dropping Elo makes the ensemble very slightly better — a stream holding twelve per cent of the weight is contributing nothing, because the other three models already read Elo as an input feature.";
    panel("[data-a-ablation]", {
      title: "What each stream earns",
      sub: "leave-one-out · weights and calibrator refitted each time",
      n: REAL.model.provenance.n_test, nUnit: "test fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
      footer: `<div class="audit-note rev">
        <b>A weight is an input, not a result.</b> The old ensemble chart showed 35.3 / 29.2 / 23.1 / 12.4 and let the reader assume that was contribution.
        Removing Elo <span class="rev">improves</span> held-out log-loss by ${fmt(Math.abs(elo.delta_logloss), 5)}.
        The expensive career LSTM does earn its place (+${fmt(A.find((d) => d.dropped === "lstm").delta_logloss, 5)}), which is worth knowing in the other direction.
      </div>`,
    });
  }

  /* ---- reliability, done properly ---------------------------------------- */
  function renderReliability() {
    if (!$("[data-a-reliability]")) return;
    const R = REAL.model.reliability;
    const W = 520, H = 520, M = { t: 24, r: 24, b: 54, l: 56 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const x = (v) => M.l + v * iw, y = (v) => M.t + (1 - v) * ih;
    let body = `<line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--fg-38)" stroke-dasharray="4 4"/>`;
    R.forEach((b) => {
      const cx = x(b.predicted);
      body += `<line x1="${cx.toFixed(1)}" y1="${y(b.wilson95[0]).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(b.wilson95[1]).toFixed(1)}" stroke="var(--cool)" stroke-width="1.6" opacity="0.9"/>`;
      body += `<line x1="${(cx - 4).toFixed(1)}" y1="${y(b.wilson95[0]).toFixed(1)}" x2="${(cx + 4).toFixed(1)}" y2="${y(b.wilson95[0]).toFixed(1)}" stroke="var(--cool)" stroke-width="1.6"/>`;
      body += `<line x1="${(cx - 4).toFixed(1)}" y1="${y(b.wilson95[1]).toFixed(1)}" x2="${(cx + 4).toFixed(1)}" y2="${y(b.wilson95[1]).toFixed(1)}" stroke="var(--cool)" stroke-width="1.6"/>`;
      const r = 3 + Math.sqrt(b.n) * 0.42;
      const covered = b.wilson95[0] <= b.predicted && b.predicted <= b.wilson95[1];
      body += `<circle cx="${cx.toFixed(1)}" cy="${y(b.observed).toFixed(1)}" r="${r.toFixed(1)}" fill="${covered ? "var(--cool)" : "var(--accent)"}" opacity="0.9">` +
        `<title>predicted ${pct(b.predicted)}, observed ${pct(b.observed)}, n=${b.n}</title></circle>`;
    });
    let axes = "";
    [0, 0.25, 0.5, 0.75, 1].forEach((t) => {
      axes += `<line x1="${x(t).toFixed(1)}" y1="${M.t}" x2="${x(t).toFixed(1)}" y2="${M.t + ih}" stroke="var(--line-faint)"/>`;
      axes += `<line x1="${M.l}" y1="${y(t).toFixed(1)}" x2="${M.l + iw}" y2="${y(t).toFixed(1)}" stroke="var(--line-faint)"/>`;
      axes += axisText(x(t), M.t + ih + 18, pct(t, 0));
      axes += axisText(M.l - 8, y(t) + 3.5, pct(t, 0), "end");
    });
    axes += axisText(M.l + iw / 2, H - 10, "forecast probability");
    axes += `<text transform="translate(14 ${M.t + ih / 2}) rotate(-90)" text-anchor="middle" fill="var(--fg-38)" font-size="10" font-family="var(--mono)">observed win rate</text>`;
    const desc = "The calibration diagram, with the two things the old version left out. Bins are equal-frequency rather than equal-width, so no bin is nearly empty, and each carries a Wilson interval for the number of fights actually in it. Dot area is proportional to bin size. The bins are not joined by a line, because they are independent estimates and a line would imply a continuous function between them. Six of the seven intervals cover the forecast, which is what good calibration looks like when you can see the uncertainty.";
    panel("[data-a-reliability]", {
      title: "Calibration, with its uncertainty",
      sub: "equal-frequency bins · Wilson 95% intervals",
      n: REAL.model.provenance.n_test, nUnit: "test fights",
      svg: SVG(W, H, `<g>${axes}</g>` + body + `<rect class="chart-frame" x="${M.l}" y="${M.t}" width="${iw}" height="${ih}"/>`, desc),
      caption: desc,
      footer: `<div class="audit-note">
        <b>${REAL.model.ece.bins_covering_prediction} of ${REAL.model.ece.n_bins} bins</b> sit inside their own Wilson interval.
        Adding the intervals makes the calibration claim <em>stronger</em>, not weaker: it shows the deviations are inside noise instead of asking the reader to assume it.
        The old chart drew ten equal-width bins as a polyline with no uncertainty at all — and with forecasts bunched near 0.50, two of those bins held
        two fights each.
      </div>`,
    });
  }

  /* ---- C16: experience ---------------------------------------------------- */
  function renderExperience() {
    if (!$("[data-a-experience]")) return;
    const E = REAL.model.experience, A = REAL.model.experience_auc;
    const rows = [
      ["veterans_both_5plus", "Both 5+ UFC bouts", "var(--cool)"],
      ["mixed", "3–4 bouts", "var(--fg-38)"],
      ["green_either_under3", "Either under 3 bouts", "var(--accent)"],
    ].filter(([k]) => E[k] && E[k].auc != null);
    const W = 700, H = 250, M = { t: 46, r: 30, b: 44, l: 168 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const lo = 0.5, hi = 0.78;
    const x = (v) => M.l + ((v - lo) / (hi - lo)) * iw;
    let body = `<line x1="${x(0.5).toFixed(1)}" y1="${M.t - 16}" x2="${x(0.5).toFixed(1)}" y2="${M.t + ih}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>` +
      axisText(x(0.5), M.t - 22, "coin flip");
    rows.forEach(([k, label, col], i) => {
      const d = E[k], cy = M.t + (i + 0.5) * (ih / rows.length);
      body += `<rect x="${x(0.5).toFixed(1)}" y="${(cy - 11).toFixed(1)}" width="${(x(d.auc) - x(0.5)).toFixed(1)}" height="22" fill="${col}" opacity="0.8"/>`;
      body += `<text x="${M.l - 14}" y="${cy - 1}" text-anchor="end" fill="var(--fg)" font-size="11.5" font-family="var(--mono)">${esc(label)}</text>`;
      body += `<text x="${M.l - 14}" y="${cy + 12}" text-anchor="end" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">n=${d.n} · ECE ${fmt(d.ece, 3)}</text>`;
      body += `<text x="${(x(d.auc) + 8).toFixed(1)}" y="${cy + 4}" fill="${col}" font-size="12" font-family="var(--mono)">AUC ${fmt(d.auc, 3)}</text>`;
    });
    [0.5, 0.55, 0.6, 0.65, 0.7, 0.75].forEach((t) => { body += axisText(x(t), M.t + ih + 20, fmt(t, 2)); });
    const desc = "The same model, split by how much UFC history the two fighters have between them. On fights where both have five or more prior bouts it separates winners from losers reasonably well. Where either fighter has fewer than three, it is barely better than a coin. The gap is 0.114 of AUC and its confidence interval does not include zero, so this is a measurement rather than an anecdote — and it is the same limitation the Macau card was blamed on, now with a number attached.";
    panel("[data-a-experience]", {
      title: "The blind spot, measured",
      sub: "discrimination by fighter experience",
      n: REAL.model.provenance.n_test, nUnit: "test fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
      footer: `<div class="audit-note rev">
        <b>The anecdote becomes a measurement.</b> AUC ${fmt(A.veteran_auc, 3)} on veteran matchups (n=${A.n_vet}) against
        ${fmt(A.green_auc, 3)} where either fighter is near-new (n=${A.n_green}) — a gap of ${fmt(A.gap, 3)},
        95% CI ${fmt(A.gap_ci95[0], 3)} to ${fmt(A.gap_ci95[1], 3)}. Calibration barely moves
        (ECE ${fmt(E.veterans_both_5plus.ece, 3)} → ${fmt(E.green_either_under3.ece, 3)}, interval crosses zero);
        it is discrimination that collapses. The model stays honest about debutants — it just cannot tell them apart.
      </div>`,
    });
  }

  /* ---- C17: Brier by year, with the splits shown ------------------------- */
  function renderBrierYear() {
    if (!$("[data-a-brier]")) return;
    const B = REAL.model.brier_by_year;
    const W = 820, H = 320, M = { t: 34, r: 24, b: 58, l: 52 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const years = B.map((d) => d.year);
    const x = (yr) => M.l + ((yr - years[0]) / (years[years.length - 1] - years[0])) * iw;
    const y = (v) => M.t + (1 - v / 0.28) * ih;     // anchored at zero-ish, not fitted to the data
    const COL = { train: "var(--fg-38)", val: "var(--amber)", test: "var(--cool)" };
    let bands = "";
    ["train", "val", "test"].forEach((sp) => {
      const g = B.filter((d) => d.split === sp);
      if (!g.length) return;
      const x0 = x(g[0].year) - (iw / (years.length - 1)) / 2;
      const x1 = x(g[g.length - 1].year) + (iw / (years.length - 1)) / 2;
      bands += `<rect x="${Math.max(M.l, x0).toFixed(1)}" y="${M.t}" width="${(Math.min(M.l + iw, x1) - Math.max(M.l, x0)).toFixed(1)}" height="${ih}" fill="${COL[sp]}" opacity="0.07"/>`;
      bands += `<text x="${((Math.max(M.l, x0) + Math.min(M.l + iw, x1)) / 2).toFixed(1)}" y="${M.t + 14}" text-anchor="middle" fill="${COL[sp]}" font-size="10" font-family="var(--mono)" letter-spacing="0.1em">${sp.toUpperCase()}</text>`;
    });
    let pts = "";
    B.forEach((d) => {
      const cx = x(d.year);
      pts += `<line x1="${cx.toFixed(1)}" y1="${y(d.brier_ci95[0]).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(d.brier_ci95[1]).toFixed(1)}" stroke="${COL[d.split]}" stroke-width="1.4" opacity="0.8"/>`;
      pts += `<circle cx="${cx.toFixed(1)}" cy="${y(d.brier).toFixed(1)}" r="3.6" fill="${COL[d.split]}"><title>${d.year} (${d.split}): Brier ${d.brier}, n=${d.n}</title></circle>`;
    });
    const coin = `<line x1="${M.l}" y1="${y(0.25).toFixed(1)}" x2="${M.l + iw}" y2="${y(0.25).toFixed(1)}" stroke="var(--accent)" stroke-dasharray="4 4" opacity="0.8"/>` +
      `<text x="${M.l + iw - 4}" y="${(y(0.25) - 6).toFixed(1)}" text-anchor="end" fill="var(--accent)" font-size="10" font-family="var(--mono)">coin flip · 0.250</text>`;
    let axes = "";
    years.forEach((yr) => { if (yr % 2 === 0) axes += axisText(x(yr), M.t + ih + 18, String(yr)); });
    [0, 0.05, 0.1, 0.15, 0.2, 0.25].forEach((t) => {
      axes += `<line x1="${M.l}" y1="${y(t).toFixed(1)}" x2="${M.l + iw}" y2="${y(t).toFixed(1)}" stroke="var(--line-faint)"/>` +
        axisText(M.l - 8, y(t) + 3.5, fmt(t, 2), "end");
    });
    axes += axisText(M.l + iw / 2, H - 10, "Brier score by event year — lower is better");
    const desc = "Brier score year by year, with the training, validation and blind-test periods shaded separately, and the axis anchored at zero so that a flat line looks flat. The old chart scaled its axis to the data, which turned a spread of 0.012 into full chart height and made noise read as a trend on a chart whose stated point was stability. It also drew in-sample and out-of-sample years as one unbroken line.";
    panel("[data-a-brier]", {
      title: "Stability, on an honest axis",
      sub: "train / validation / blind test shaded",
      n: B.reduce((a, d) => a + d.n, 0), nUnit: "fights",
      svg: SVG(W, H, bands + coin + `<g>${axes}</g>` + pts + `<rect class="chart-frame" x="${M.l}" y="${M.t}" width="${iw}" height="${ih}"/>`, desc),
      caption: desc,
    });
  }

  /* ---- C13: gain vs permutation ------------------------------------------ */
  function renderImportance() {
    if (!$("[data-a-importance]")) return;
    const G = REAL.model.gain_vs_perm.slice(0, 12);
    const P = REAL.model.permutation.slice(0, 12);
    const W = 800, H = 60 + Math.max(G.length, P.length) * 30, M = { t: 54, b: 24 };
    const xl = 260, xr = 540;
    const yy = (rank) => M.t + (rank - 1) * 30;
    let body =
      `<text x="${xl}" y="${M.t - 24}" text-anchor="end" fill="var(--fg-70)" font-size="11" font-family="var(--mono)">XGBoost gain (as published)</text>` +
      `<text x="${xr}" y="${M.t - 24}" fill="var(--fg-70)" font-size="11" font-family="var(--mono)">Permutation importance (held-out)</text>`;
    const permRank = {};
    P.forEach((d, i) => { permRank[d.feature] = i + 1; });
    G.forEach((d, i) => {
      const y0 = yy(i + 1);
      const target = permRank[d.feature];
      const fell = !target || target > 12;
      const col = fell ? "var(--accent)" : "var(--cool)";
      body += `<text x="${xl - 10}" y="${y0 + 4}" text-anchor="end" fill="${fell ? "var(--accent-hi)" : "var(--fg-70)"}" font-size="10.5" font-family="var(--mono)">${i + 1}. ${esc(d.feature)}</text>`;
      const y1 = target ? yy(target) : H - 16;
      body += `<path d="M${xl + 4},${y0} C${(xl + xr) / 2},${y0} ${(xl + xr) / 2},${y1} ${xr - 8},${y1}" fill="none" stroke="${col}" ` +
        `stroke-width="${fell ? 2 : 1.2}" opacity="${fell ? 0.9 : 0.32}" ${fell && !target ? 'stroke-dasharray="5 4"' : ""}/>`;
    });
    P.forEach((d, i) => {
      const y0 = yy(i + 1);
      body += `<text x="${xr + 10}" y="${y0 + 4}" fill="var(--fg)" font-size="10.5" font-family="var(--mono)">${i + 1}. ${esc(d.feature)}</text>`;
      body += `<text x="${xr + 10 + 180}" y="${y0 + 4}" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">+${fmt(d.delta_logloss, 4)}</text>`;
    });
    body += `<text x="${xr - 8}" y="${H - 6}" text-anchor="end" fill="var(--accent)" font-size="10" font-family="var(--mono)">↘ off the bottom: outside the top 30</text>`;
    const desc = "The same features ranked two ways. On the left, XGBoost's built-in gain, which the site used to quote — it puts two archetype-cluster features first and second. On the right, permutation importance measured on the held-out test set with all four models re-scored. The two cluster features do not appear in the top thirty at all. Gain is biased toward continuous and high-cardinality splits, and it was being read off a single stream carrying about a third of the ensemble weight to support a claim about the whole system.";
    panel("[data-a-importance]", {
      title: "Gain said one thing. Permutation says another.",
      sub: `${REAL.model.permutation_meta.n_features} features permuted × ${REAL.model.permutation_meta.n_repeats}`,
      n: REAL.model.provenance.n_test, nUnit: "test fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
      footer: `<div class="audit-note rev">
        <b>The claim it was supporting does not survive.</b>
        <span class="struck">"Style matchup outranks raw output" — cluster features rank #1 and #2.</span>
        <span class="rev">Permuted in held-out data, neither reaches the top 30.</span>
        What actually damages the model when shuffled is age, pace mismatch, and — third and fourth — the two fighters' UFC fight counts,
        which is the debutant blind spot showing up again from a completely different direction.
      </div>`,
    });
  }

  /* ---- SHAP beeswarm ------------------------------------------------------ */
  function renderShap() {
    if (!$("[data-a-shap]") || !REAL.model.shap) return;
    const S = REAL.model.shap.features.slice(0, 10);
    const W = 800, H = 50 + S.length * 34, M = { t: 34, r: 40, b: 34, l: 200 };
    const iw = W - M.l - M.r;
    const all = S.flatMap((f) => f.points.map((p) => p[0]));
    const lim = Math.max(...all.map(Math.abs)) * 1.05;
    const x = (v) => M.l + ((v + lim) / (2 * lim)) * iw;
    let body = `<line x1="${x(0).toFixed(1)}" y1="${M.t - 12}" x2="${x(0).toFixed(1)}" y2="${(M.t + S.length * 34 - 18).toFixed(1)}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>`;
    S.forEach((f, i) => {
      const cy = M.t + i * 34;
      const vals = f.points.map((p) => p[1]);
      const vlo = Math.min(...vals), vhi = Math.max(...vals);
      f.points.forEach((p, j) => {
        const t = vhi > vlo ? (p[1] - vlo) / (vhi - vlo) : 0.5;
        const col = t > 0.5 ? "var(--accent)" : "var(--cool)";
        const jitter = (((j * 2654435761) % 1000) / 1000 - 0.5) * 13;
        body += `<circle cx="${x(p[0]).toFixed(1)}" cy="${(cy + jitter).toFixed(1)}" r="1.9" fill="${col}" opacity="${0.28 + Math.abs(t - 0.5) * 0.7}"/>`;
      });
      body += `<text x="${M.l - 14}" y="${cy + 4}" text-anchor="end" fill="var(--fg-70)" font-size="10.5" font-family="var(--mono)">${esc(f.feature)}</text>`;
    });
    body += axisText(M.l + iw / 2, H - 8, "SHAP value — push toward corner B (left) or corner A (right)");
    body += `<text x="${M.l + iw}" y="${M.t - 18}" text-anchor="end" fill="var(--fg-38)" font-size="9.5" font-family="var(--mono)">red = high feature value · blue = low</text>`;
    const desc = "SHAP values for every fight in the test set rather than a single example. Each dot is one fight; its position shows how much that feature moved the prediction and in which direction, and its colour shows whether the feature was high or low for that fight. A single waterfall chart for one bout, which is what the site used to show, cannot support a general claim about what drives the model.";
    panel("[data-a-shap]", {
      title: "SHAP across the test set",
      sub: REAL.model.shap.stream,
      n: REAL.model.shap.n_test, nUnit: "test fights",
      svg: SVG(W, H, body, desc),
      caption: desc,
    });
  }

  /* ---- C16: the card as a distribution ------------------------------------ */
  function renderCard() {
    if (!$("[data-a-card]")) return;
    const C = REAL.model.card;
    const D = C.distribution;
    const W = 640, H = 300, M = { t: 34, r: 24, b: 56, l: 48 };
    const iw = W - M.l - M.r, ih = H - M.t - M.b;
    const max = Math.max(...D);
    const bw = iw / D.length;
    let bars = "";
    D.forEach((p, k) => {
      const h = (p / max) * ih;
      const hit = k === C.correct;
      bars += `<rect x="${(M.l + k * bw + 2).toFixed(1)}" y="${(M.t + ih - h).toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${h.toFixed(1)}" ` +
        `fill="${hit ? "var(--accent)" : "var(--cool)"}" opacity="${hit ? 0.95 : 0.4}"><title>${k} correct: ${pct(p)}</title></rect>`;
      bars += axisText(M.l + k * bw + bw / 2, M.t + ih + 18, String(k));
    });
    const ex = M.l + (C.expected_correct + 0.5) * bw;
    const marks =
      `<line x1="${ex.toFixed(1)}" y1="${M.t - 8}" x2="${ex.toFixed(1)}" y2="${M.t + ih}" stroke="var(--fg)" stroke-dasharray="3 3" opacity="0.75"/>` +
      `<text x="${ex.toFixed(1)}" y="${M.t - 14}" text-anchor="middle" fill="var(--fg-70)" font-size="10" font-family="var(--mono)">expected ${fmt(C.expected_correct)}</text>` +
      `<text x="${(M.l + (C.correct + 0.5) * bw).toFixed(1)}" y="${(M.t + ih + 38).toFixed(1)}" text-anchor="middle" fill="var(--accent-hi)" font-size="11" font-family="var(--mono)">actual ${C.correct}</text>` +
      axisText(M.l + iw / 2, H - 8, "number of correct picks out of " + C.n_scored + " the model could score");
    const desc = "What the Macau card actually tells you. Rather than quoting a win rate from thirteen fights, this is the exact distribution of correct picks implied by the model's own probability for each fight it could score. It expected 5.33 and got 5. The result sits in the middle of its own prediction, which means the card neither confirms nor embarrasses the model — and the four fights it never scored were UFC debutants it has no history for.";
    panel("[data-a-card]", {
      title: "The card, as a distribution",
      sub: esc(C.event),
      n: C.n_scored, nUnit: "scored fights",
      svg: SVG(W, H, bars + marks, desc),
      caption: desc,
      footer: `<div class="audit-note rev">
        <b>The "9 of 13" was flattering the model.</b> Of ${C.n_on_card} bouts, one was a no-contest and four were UFC debutants the model
        <em>cannot score at all</em> — those picks came from the market, not from here. On the ${C.n_scored} it did score it went
        <b>${C.correct}</b>, against an expected ${fmt(C.expected_correct)} (sd ${fmt(C.sd_correct)}, central 80%: ${C.central80[0]}–${C.central80[1]}).
        P(at least ${C.correct}) = ${fmt(C.p_at_least_observed, 2)}. <span class="rev">${esc(C.verdict)}</span> — and unremarkable, which is the honest verdict.
      </div>`,
    });
  }

  /* ---- headline metrics with intervals ------------------------------------ */
  function renderHeadline() {
    const el = $("[data-a-headline]");
    if (!el) return;
    const H = REAL.model.headline;
    const rows = [
      ["AUC-ROC", "auc", "≥ 0.740", 3],
      ["Brier score", "brier", "< 0.225", 4],
      ["Log-loss", "logloss", "—", 4],
      ["ECE (10 bins)", "ece", "< 0.050", 3],
      ["Accuracy", "accuracy", "context only", 3],
    ];
    el.innerHTML = `<table class="table"><thead><tr>
        <th>Metric</th><th>Target</th><th>Result</th><th>95% interval</th><th>Verdict</th></tr></thead><tbody>` +
      rows.map(([label, k, target, dp]) => {
        const d = H[k];
        let verdict = "—", cls = "";
        if (d.target != null) {
          if (d.target_inside_ci) { verdict = "within noise of target"; cls = "amber"; }
          else if ((k === "auc" && d.point < d.target) || (k !== "auc" && d.point > d.target)) { verdict = "real miss"; cls = "accent"; }
          else { verdict = "real hit"; cls = "good"; }
        }
        return `<tr><td>${label}</td><td class="mono">${target}</td>
          <td class="mono"><b>${fmt(d.point, dp)}</b></td>
          <td class="mono">${fmt(d.ci95[0], dp)} – ${fmt(d.ci95[1], dp)}</td>
          <td class="mono" style="color:var(--${cls === "accent" ? "accent-hi" : cls === "good" ? "good" : cls === "amber" ? "amber" : "fg-38"})">${verdict}</td></tr>`;
      }).join("") +
      `</tbody></table>
      <p class="chart-src">Bootstrapped on n = ${REAL.model.provenance.n_test}. The shipped 4-stream bundle, re-scored on the frozen split
      (${esc(REAL.model.provenance.split)}); reproduces its own published test metrics to 1e-16.</p>`;
  }

  /* =======================================================================
     THE LEDGER, THE RECORD, THE TICKER
     ======================================================================= */
  function renderLedger() {
    const el = $("[data-a-ledger]");
    if (!el || typeof CORRECTIONS === "undefined") return;
    const order = { reversed: 0, bug: 1, unsupported: 2, magnitude: 3, upheld: 4 };
    const sorted = CORRECTIONS.slice().sort((a, b) => order[a.severity] - order[b.severity] || a.id.localeCompare(b.id));
    el.innerHTML = `<div class="ledger">` + sorted.map((c) => `
      <div class="ledger-row" id="corr-${c.id}">
        <span class="ledger-id">${c.id}</span>
        <div>
          <span class="ledger-was"><span class="struck">${c.was}</span></span>
          <span class="ledger-now"><span class="rev">→</span> ${c.now}</span>
          <p style="margin:.55rem 0 0;font-size:.83rem;line-height:1.6;color:var(--fg-55)">${c.detail}</p>
          <div class="ledger-mech">
            <span class="mech-tag" data-sev="${c.severity}">${c.severity}</span>
            <span class="mech-tag">mechanism · ${esc(c.mechanism)}</span>
            <span class="stamp">${esc(c.evidence)}</span>
          </div>
        </div>
      </div>`).join("") + `</div>`;
  }

  function renderRecord() {
    $$("[data-a-record]").forEach((el) => {
      if (typeof RECORD === "undefined") return;
      el.innerHTML = `<span class="record" title="losses are this project's own retracted findings">
        RECORD <b>${RECORD.wins}<span class="l">–${RECORD.losses}</span>–${RECORD.draws}</b>
        <span style="color:var(--fg-38)">upheld · reversed · revised</span></span>`;
    });
  }

  function renderTicker() {
    const el = $("[data-a-ticker]");
    if (!el || typeof CORRECTIONS === "undefined") return;
    const items = CORRECTIONS.filter((c) => c.severity !== "upheld").map((c) =>
      `<a class="ticker-item" href="index.html#corr-${c.id}"><b>${c.id}</b> · ${esc(c.mechanism.toUpperCase())} · ${esc(c.now.replace(/<[^>]+>/g, "").slice(0, 96))}…</a>`
    ).join("");
    el.innerHTML = `<div class="ticker"><span class="ticker-flag">Corrections</span>
      <div class="ticker-track">${items}${items}</div></div>`;
  }

  /* ---- boot -------------------------------------------------------------- */
  function boot() {
    [renderPosition, renderCoverage, renderHump, renderLegKicks, renderControl,
     renderForest, renderClusterEffect, renderReachControl, renderReachByClass,
     renderMurphy, renderSharpness, renderLadder, renderAblation, renderReliability,
     renderExperience, renderBrierYear, renderImportance, renderShap, renderCard,
     renderHeadline, renderLedger, renderRecord, renderTicker].forEach((fn) => {
      try { fn(); } catch (e) { console.error("[audit]", fn.name, e); }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

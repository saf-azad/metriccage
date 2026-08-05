/* ===========================================================================
   MetricCage — rendering layer.
   Zero dependencies, zero build step. Charts are hand-rolled SVG so the site
   works offline, from file://, and without a CDN round-trip.
   All content comes from data/site-data.js.
   =========================================================================== */

(function () {
  "use strict";

  /* ---- helpers --------------------------------------------------------- */
  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = (s) =>
    String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const mount = (sel, html) => {
    const el = $(sel);
    if (el) el.innerHTML = html;
    return el;
  };

  const caveat = (obj) =>
    obj && obj.verified === false && obj.caveat
      ? `<span class="caveat">${esc(obj.caveat)}</span>`
      : "";

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = (w, h, inner, label) =>
    `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label || "")}">${inner}</svg>`;

  /* =======================================================================
     HERO + META
     ======================================================================= */
  function renderMeta() {
    const m = SITE.meta;
    document.querySelectorAll("[data-site-name]").forEach((el) => {
      el.innerHTML = "Metric<span>Cage</span>";
    });
    document.querySelectorAll("[data-author]").forEach((el) => {
      el.textContent = m.author;
    });
    document.querySelectorAll("[data-github]").forEach((el) => {
      el.setAttribute("href", m.github);
    });
    document.querySelectorAll("[data-dashboard]").forEach((el) => {
      el.setAttribute("href", m.dashboardUrl);
    });
    const y = $("[data-year]");
    if (y) y.textContent = new Date().getFullYear();
  }

  function renderHero() {
    mount(
      "[data-hero-stats]",
      SITE.heroStats
        .map(
          (s) => `
      <div class="stat">
        <span class="stat-value">${esc(s.value)}</span>
        <span class="stat-label">${esc(s.label)}</span>
        <span class="stat-note">${esc(s.note)}</span>
      </div>`
        )
        .join("")
    );
  }

  /* =======================================================================
     PIPELINE
     ======================================================================= */
  function renderPipeline() {
    mount(
      "[data-pipeline]",
      SITE.pipeline
        .map(
          (s) => `
      <div class="step">
        <div>
          <h3>${esc(s.step)}</h3>
          <p>${esc(s.body)}</p>
        </div>
        <span class="step-tag">${esc(s.tag)}</span>
      </div>`
        )
        .join("")
    );
  }

  /* =======================================================================
     ENSEMBLE
     ======================================================================= */
  function renderEnsemble() {
    const e = SITE.ensemble;
    const total = e.members.reduce((a, m) => a + m.weight, 0);

    mount(
      "[data-weight-bar]",
      e.members
        .map(
          (m, i) =>
            `<div class="weight-seg" data-i="${i}" style="flex:${m.weight} 1 0"
                  title="${esc(m.name)} — ${m.weight}%">${m.weight}%</div>`
        )
        .join("")
    );

    mount(
      "[data-ensemble]",
      e.members
        .map(
          (m) => `
      <div class="member">
        <div class="member-head">
          <h3>${esc(m.name)}</h3>
          <span class="member-weight">${m.weight.toFixed(1)}%</span>
        </div>
        <p>${esc(m.role)}</p>
      </div>`
        )
        .join("") +
        `<p class="stat-note" style="margin-top:1rem">Weights sum to ${total.toFixed(1)}% · ${esc(e.src)}</p>`
    );
  }

  /* =======================================================================
     RESULTS TABLE
     ======================================================================= */
  function renderResults() {
    const r = SITE.results;
    mount(
      "[data-results]",
      `<tbody>${r.rows
        .map(
          (row) => `
      <tr>
        <td class="td-metric">${esc(row.metric)}</td>
        <td class="td-num">${esc(row.target)}</td>
        <td><span class="result-figure" data-status="${esc(row.status)}">${esc(row.result)}</span></td>
        <td class="td-note">${esc(row.note)}</td>
      </tr>`
        )
        .join("")}</tbody>`
    );
    const cap = $("[data-results-caption]");
    if (cap) cap.textContent = `${r.split} · n = ${r.n} fights · source: ${r.src}`;
  }

  /* =======================================================================
     CHART — reliability diagram
     ======================================================================= */
  function renderReliability() {
    const d = SITE.reliability;
    const W = 340,
      H = 340,
      P = { t: 12, r: 12, b: 34, l: 40 };
    const iw = W - P.l - P.r,
      ih = H - P.t - P.b;
    const x = (v) => P.l + v * iw;
    const y = (v) => P.t + (1 - v) * ih;

    let g = "";
    for (let i = 0; i <= 5; i++) {
      const v = i / 5;
      g += `<line class="chart-grid" x1="${P.l}" y1="${y(v)}" x2="${P.l + iw}" y2="${y(v)}"/>`;
      g += `<line class="chart-grid" x1="${x(v)}" y1="${P.t}" x2="${x(v)}" y2="${P.t + ih}"/>`;
    }

    // perfect-calibration diagonal
    const diag = `<line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"
      stroke="var(--fg)" stroke-width="1" stroke-dasharray="3 3" opacity="0.45"/>`;

    const pts = d.bins;
    const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
    const line = `<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.75"/>`;

    const maxN = Math.max.apply(null, pts.map((p) => p[2]));
    const dots = pts
      .map((p) => {
        const rr = 2.5 + 4 * Math.sqrt(p[2] / maxN);
        return `<circle cx="${x(p[0]).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="${rr.toFixed(1)}"
                fill="var(--accent)" stroke="var(--bg)" stroke-width="1"><title>predicted ${p[0]}, observed ${p[1]} (n=${p[2]})</title></circle>`;
      })
      .join("");

    let axes = "";
    for (let i = 0; i <= 5; i++) {
      const v = i / 5;
      axes += `<text x="${x(v)}" y="${P.t + ih + 15}" text-anchor="middle">${v.toFixed(1)}</text>`;
      axes += `<text x="${P.l - 8}" y="${y(v) + 3.5}" text-anchor="end">${v.toFixed(1)}</text>`;
    }

    const labels =
      `<text class="chart-label" x="${P.l + iw / 2}" y="${H - 2}" text-anchor="middle">predicted probability</text>` +
      `<text class="chart-label" transform="rotate(-90 12 ${P.t + ih / 2})" x="12" y="${P.t + ih / 2}" text-anchor="middle">observed frequency</text>`;

    const frame = `<rect class="chart-frame" x="${P.l}" y="${P.t}" width="${iw}" height="${ih}"/>`;

    mount(
      "[data-chart-reliability]",
      svg(W, H, `${g}${frame}${diag}${line}${dots}<g class="chart-axis">${axes}</g>${labels}`,
        "Reliability diagram: predicted probability against observed win frequency, tracking the diagonal closely.") + caveat(d)
    );
  }

  /* =======================================================================
     CHART — Brier score over time
     ======================================================================= */
  function renderBrier() {
    const d = SITE.brierByYear;
    const W = 460,
      H = 250,
      P = { t: 16, r: 16, b: 34, l: 46 };
    const iw = W - P.l - P.r,
      ih = H - P.t - P.b;

    const years = d.series.map((s) => s.year);
    const vals = d.series.map((s) => s.value).concat([d.reference]);
    const yMin = Math.min.apply(null, vals) - 0.008;
    const yMax = Math.max.apply(null, vals) + 0.008;

    const x = (yr) =>
      P.l + ((yr - years[0]) / Math.max(1, years[years.length - 1] - years[0])) * iw;
    const y = (v) => P.t + (1 - (v - yMin) / (yMax - yMin)) * ih;

    // horizontal gridlines at rounded steps
    let g = "",
      axesY = "";
    const step = 0.01;
    const first = Math.ceil(yMin / step) * step;
    for (let v = first; v <= yMax; v += step) {
      const yy = y(v);
      g += `<line class="chart-grid" x1="${P.l}" y1="${yy.toFixed(1)}" x2="${P.l + iw}" y2="${yy.toFixed(1)}"/>`;
      axesY += `<text x="${P.l - 8}" y="${(yy + 3.5).toFixed(1)}" text-anchor="end">${v.toFixed(3)}</text>`;
    }

    const ref = `<line x1="${P.l}" y1="${y(d.reference).toFixed(1)}" x2="${P.l + iw}" y2="${y(d.reference).toFixed(1)}"
      stroke="var(--cool)" stroke-width="1" stroke-dasharray="4 3"/>
      <text class="chart-label" x="${P.l + iw}" y="${(y(d.reference) - 6).toFixed(1)}" text-anchor="end" fill="var(--cool)">${esc(d.referenceLabel)}</text>`;

    const path = d.series
      .map((s, i) => `${i ? "L" : "M"}${x(s.year).toFixed(1)},${y(s.value).toFixed(1)}`)
      .join(" ");
    const line = `<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.75"/>`;
    const dots = d.series
      .map(
        (s) =>
          `<circle cx="${x(s.year).toFixed(1)}" cy="${y(s.value).toFixed(1)}" r="3.25" fill="var(--accent)" stroke="var(--bg)" stroke-width="1"><title>${s.year}: ${s.value}</title></circle>`
      )
      .join("");

    const axesX = d.series
      .map(
        (s) =>
          `<text x="${x(s.year).toFixed(1)}" y="${P.t + ih + 16}" text-anchor="middle">${s.year}</text>`
      )
      .join("");

    const frame = `<rect class="chart-frame" x="${P.l}" y="${P.t}" width="${iw}" height="${ih}"/>`;

    mount(
      "[data-chart-brier]",
      svg(W, H, `${g}${frame}${ref}${line}${dots}<g class="chart-axis">${axesX}${axesY}</g>`,
        "Brier score by year, staying well below the coin-flip reference across the whole window.") + caveat(d)
    );
  }

  /* =======================================================================
     Feature importance
     ======================================================================= */
  function renderFeatures() {
    const f = SITE.featureImportance;
    const max = Math.max.apply(null, f.items.map((i) => i.value));
    mount(
      "[data-features]",
      f.items
        .map(
          (i) => `
      <div class="fbar" data-family="${esc(i.family)}">
        <div class="fbar-head">
          <span class="fbar-name">${esc(i.name)}</span>
          <span class="fbar-fam">${esc(i.family)}</span>
        </div>
        <div class="fbar-track"><span class="fbar-fill" style="width:${((i.value / max) * 100).toFixed(1)}%"></span></div>
      </div>`
        )
        .join("")
    );
    mount("[data-features-caveat]", caveat(f));
  }

  /* =======================================================================
     SHAP case
     ======================================================================= */
  function renderShap() {
    const s = SITE.shapCase;
    const max = Math.max.apply(null, s.drivers.map((d) => Math.abs(d.value)));
    mount(
      "[data-shap]",
      s.drivers
        .map((d) => {
          const pct = (Math.abs(d.value) / max) * 50;
          const dir = d.value >= 0 ? "pos" : "neg";
          return `
        <div class="shap-row">
          <span class="shap-name">${esc(d.name)}</span>
          <span class="shap-track"><span class="shap-fill" data-dir="${dir}" style="width:${pct.toFixed(1)}%"></span></span>
          <span class="shap-val">${d.value > 0 ? "+" : ""}${d.value.toFixed(2)}</span>
        </div>`;
        })
        .join("")
    );
    const p = $("[data-shap-prob]");
    if (p) {
      p.innerHTML = `<b>${(s.probability * 100).toFixed(0)}%</b><span>win probability, ${esc(s.subject)} — reproduced from the documented model output</span>`;
    }
    mount("[data-shap-caveat]", caveat(s));
    document.querySelectorAll("[data-shap-title]").forEach((el) => {
      el.textContent = s.title;
    });
  }

  /* =======================================================================
     Limitations + roadmap
     ======================================================================= */
  function renderLimitations() {
    mount(
      "[data-limitations]",
      SITE.limitations
        .map(
          (l) => `
      <div class="limit">
        <div class="limit-head">
          <h3>${esc(l.title)}</h3>
          <span class="sev">${esc(l.severity)}</span>
        </div>
        <p>${esc(l.body)}</p>
      </div>`
        )
        .join("")
    );
  }

  function renderRoadmap() {
    const r = SITE.roadmap;
    mount(
      "[data-roadmap]",
      `<tbody>${r.items
        .map(
          (i) => `
      <tr>
        <td class="td-metric">${esc(i.work)}</td>
        <td><span class="gain">${esc(i.gain)}</span></td>
        <td class="td-note">${esc(i.rationale)}</td>
        <td><span class="stage-tag">${esc(i.stage)}</span></td>
      </tr>`
        )
        .join("")}</tbody>`
    );
    const n = $("[data-roadmap-note]");
    if (n) n.textContent = `${r.note} Source: ${r.src}`;
  }

  /* =======================================================================
     Rigor + dashboard
     ======================================================================= */
  function renderRigor() {
    mount(
      "[data-rigor]",
      SITE.rigor
        .map(
          (r) => `
      <div class="card">
        <h3>${esc(r.title)}</h3>
        <p>${esc(r.body)}</p>
      </div>`
        )
        .join("")
    );
  }

  function renderDashboard() {
    mount(
      "[data-dashboard-features]",
      SITE.dashboardFeatures.map((f) => `<li>${esc(f)}</li>`).join("")
    );
  }

  /* =======================================================================
     Case studies
     ======================================================================= */
  function renderCaseTeasers() {
    const el = $("[data-case-teasers]");
    if (!el) return;
    const written = CASE_STUDIES.filter((c) => c.verified);
    const queued = CASE_STUDIES.filter((c) => !c.verified);

    let html = written
      .map(
        (c) => `
      <a class="card card-feature" href="case-studies.html#${esc(c.slug)}">
        <div class="card-feature-side">
          <span class="card-tag">${esc(c.card)}</span>
          <span class="case-record">${esc(c.record)}</span>
          <span class="stat-note">correct picks</span>
        </div>
        <div class="card-feature-main">
          <h3>${esc(c.headline)}</h3>
          <p>${esc(c.lede)}</p>
          <span class="card-more">Read the breakdown →</span>
        </div>
      </a>`
      )
      .join("");

    if (queued.length) {
      html += `
      <a class="card card-queued" href="case-studies.html#queued">
        <span class="card-tag">Also backtested</span>
        <h3>${queued.length} more 2026 cards</h3>
        <p>${queued.map((c) => esc(c.card)).join(" · ")} — run through the model, write-ups pending.</p>
        <span class="card-more">See the list →</span>
      </a>`;
    }

    el.innerHTML = html;
  }

  function renderCaseStudies() {
    const el = $("[data-cases]");
    if (!el) return;
    const written = CASE_STUDIES.filter((c) => c.verified);
    const stubs = CASE_STUDIES.filter((c) => !c.verified);

    let html = written
      .map(
        (c) => `
      <article class="case split" id="${esc(c.slug)}">
        <div class="sticky-side">
          <p class="eyebrow">${esc(c.card)}</p>
          <span class="case-record">${esc(c.record)}</span>
          <div class="case-meta">correct picks · ${esc(c.date)}</div>
        </div>
        <div class="case-body">
          <h2 style="margin-bottom:1.25rem">${esc(c.headline)}</h2>
          <p class="lede" style="margin-bottom:1.75rem">${esc(c.lede)}</p>
          ${c.body.map((p) => `<p>${esc(p)}</p>`).join("")}
          <div class="case-lesson">
            <span class="k">What it taught the model</span>
            <p>${esc(c.lesson)}</p>
          </div>
        </div>
      </article>`
      )
      .join("");

    if (stubs.length) {
      html += `
      <section class="case" id="queued">
        <p class="eyebrow">Backtested, write-up queued</p>
        <p class="lede" style="margin-bottom:2rem">These cards have been run through the model. Their breakdowns are pending a write-up rather than a result — listed here rather than omitted, because a portfolio that only shows finished work is its own kind of overselling.</p>
        <div class="grid-2">
          ${stubs
            .map(
              (c) => `
            <div class="stub">
              <h3>${esc(c.card)}</h3>
              <span class="case-meta">${esc(c.date)} · write-up pending</span>
            </div>`
            )
            .join("")}
        </div>
      </section>`;
    }

    el.innerHTML = html;
  }

  /* =======================================================================
     Scroll-spy nav
     ======================================================================= */
  function initScrollSpy() {
    const links = Array.prototype.slice.call(
      document.querySelectorAll('.nav-links a[href^="#"]')
    );
    if (!links.length || !("IntersectionObserver" in window)) return;
    const map = {};
    links.forEach((a) => {
      const id = a.getAttribute("href").slice(1);
      const sec = document.getElementById(id);
      if (sec) map[id] = a;
    });
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) {
            links.forEach((a) => a.removeAttribute("aria-current"));
            const a = map[en.target.id];
            if (a) a.setAttribute("aria-current", "page");
          }
        });
      },
      { rootMargin: "-45% 0px -50% 0px" }
    );
    Object.keys(map).forEach((id) => obs.observe(document.getElementById(id)));
  }

  /* =======================================================================
     DISCOVERIES PAGE — all values computed from REAL (data/real-stats.js)
     ======================================================================= */
  const paras = (sel, arr) =>
    mount(sel, (arr || []).map((p) => `<p>${esc(p)}</p>`).join(""));

  const hasReal = () => typeof REAL !== "undefined" && typeof DISCOVERIES !== "undefined";

  function fill(prefix, d) {
    document.querySelectorAll(`[data-d-${prefix}-headline]`).forEach((el) => (el.textContent = d.headline));
    paras(`[data-d-${prefix}-body]`, d.body);
    const f = $(`[data-d-${prefix}-falsify]`);
    if (f) f.innerHTML = `<strong>Falsifiable.</strong> ${esc(d.falsify)}`;
    const sc = $(`[data-d-${prefix}-src]`);
    if (sc) sc.textContent = d.srcnote || "";
  }

  const legend = (sel, items) =>
    mount(sel, items.map((i) => `<span class="legend-chip"><span class="legend-swatch" style="background:${i[1]}"></span>${esc(i[0])}</span>`).join(""));

  const ERA_KEYS = ["1994-1999", "2000-2004", "2005-2009", "2010-2014", "2015-2019", "2020-2026"];
  const ERA_SHORT = ["'94-99", "'00-04", "'05-09", "'10-14", "'15-19", "'20-26"];

  /* ---- 01: where strikes land (stacked area by year) --------------------- */
  function renderPosition() {
    const el = $("[data-chart-position]");
    if (!el || !hasReal()) return;
    fill("seq", DISCOVERIES.sequence);

    const data = Object.entries(REAL.position_by_year)
      .map(([y, v]) => ({ y: +y, ...v }))
      .filter((d) => d.y >= 1994)
      .sort((a, b) => a.y - b.y);

    const W = 560, H = 300, P = { t: 16, r: 14, b: 30, l: 40 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const x = (yr) => P.l + ((yr - data[0].y) / (data[data.length - 1].y - data[0].y)) * iw;
    const y = (v) => P.t + (1 - v) * ih;

    const keys = ["ground", "clinch", "distance"];
    const cols = { ground: "var(--accent)", clinch: "var(--fg-38)", distance: "var(--fg-55)" };
    const areas = keys.map((k, ki) => {
      let top = "", bot = "";
      data.forEach((d, i) => {
        let acc = 0;
        for (let j = 0; j <= ki; j++) acc += d[keys[j]];
        top += `${i ? "L" : "M"}${x(d.y).toFixed(1)},${y(acc).toFixed(1)} `;
      });
      for (let i = data.length - 1; i >= 0; i--) {
        let acc = 0;
        for (let j = 0; j < ki; j++) acc += data[i][keys[j]];
        bot += `L${x(data[i].y).toFixed(1)},${y(acc).toFixed(1)} `;
      }
      return `<path d="${top}${bot}Z" fill="${cols[k]}" opacity="${k === "ground" ? 0.85 : k === "distance" ? 0.35 : 0.45}" stroke="var(--bg)" stroke-width="0.75"><title>${k}</title></path>`;
    }).join("");

    const g44 = REAL.position_by_era["1994-1999"].ground, g9 = REAL.position_by_era["2020-2026"].ground;
    const ann =
      `<text class="chart-label" x="${(x(1996)).toFixed(1)}" y="${(y(0.22)).toFixed(1)}" fill="var(--bg)" font-weight="600">ground ${(g44 * 100).toFixed(0)}%</text>` +
      `<text class="chart-label" x="${(x(2024)).toFixed(1)}" y="${(y(0.028)).toFixed(1)}" text-anchor="end" fill="var(--accent-hi)">ground ${(g9 * 100).toFixed(0)}%</text>` +
      `<text class="chart-label" x="${(x(2018)).toFixed(1)}" y="${(y(0.6)).toFixed(1)}" fill="var(--bg)" font-weight="600">distance</text>`;

    let axes = "";
    [1994, 2000, 2006, 2012, 2018, 2026].forEach((yr) => {
      axes += `<text x="${x(yr).toFixed(1)}" y="${P.t + ih + 18}" text-anchor="middle">${yr}</text>`;
    });
    [0, 0.5, 1].forEach((v) => (axes += `<text x="${P.l - 8}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end">${v * 100}%</text>`));
    const frame = `<rect class="chart-frame" x="${P.l}" y="${P.t}" width="${iw}" height="${ih}"/>`;

    mount("[data-chart-position]",
      svg(W, H, `${areas}${ann}${frame}<g class="chart-axis">${axes}</g>`,
        "Stacked area chart: the ground share of landed strikes collapses from 44 percent in the 1990s to 9 percent today while distance striking grows to 81 percent."));

    legend("[data-seq-legend]", [["Ground", "var(--accent)"], ["Clinch", "var(--fg-38)"], ["Distance", "var(--fg-55)"]]);

    const td0 = REAL.td_by_era["1994-1999"], td1 = REAL.td_by_era["2020-2026"];
    const sq0 = REAL.seq_proxies["1994-1999"], sq1 = REAL.seq_proxies["2020-2026"];
    mount("[data-seq-stats]", [
      { v: `${(g44 * 100).toFixed(0)}% → ${(g9 * 100).toFixed(0)}%`, l: "ground share of landed strikes", n: "1990s → 2020s" },
      { v: `${td0.att_per_fight.toFixed(1)} → ${td1.att_per_fight.toFixed(1)}`, l: "takedown attempts per fighter", n: `accuracy ${(td0.accuracy * 100).toFixed(0)}% → ${(td1.accuracy * 100).toFixed(0)}%` },
      { v: `${sq0.subatt_per_td.toFixed(2)} → ${sq1.subatt_per_td.toFixed(2)}`, l: "sub attempts per landed takedown", n: "the funnel closed" },
    ].map((s) => `
      <div class="stat">
        <span class="stat-value" style="font-size:clamp(1.5rem,1.2rem+1.2vw,2.1rem)">${esc(s.v)}</span>
        <span class="stat-label">${esc(s.l)}</span>
        <span class="stat-note">${esc(s.n)}</span>
      </div>`).join(""));
  }

  /* ---- 02: Makhachev–Oliveira, real rounds ------------------------------- */
  function renderMomentum() {
    const el = $("[data-chart-momentum]");
    if (!el || !hasReal()) return;
    fill("mom", DISCOVERIES.momentum);
    const M = REAL.mak_oli;

    const rows = [];
    M.rounds.forEach((r) => {
      rows.push({ label: `R${r.round} · sig strikes`, a: r.makhachev.sig, b: r.oliveira.sig, unit: "" });
      rows.push({ label: `R${r.round} · control`, a: r.makhachev.ctrl_sec, b: r.oliveira.ctrl_sec, unit: "s" });
      rows.push({ label: `R${r.round} · takedowns`, a: r.makhachev.td, b: r.oliveira.td, unit: "" });
    });

    const W = 520, H = 320, P = { t: 34, r: 16, b: 16, l: 16 };
    const iw = W - P.l - P.r;
    const mid = P.l + iw / 2;
    const rowH = (H - P.t - P.b) / rows.length;
    const maxHalf = iw / 2 - 60;

    let out = `<line x1="${mid}" y1="${P.t - 6}" x2="${mid}" y2="${H - P.b}" stroke="var(--line)"/>`;
    out += `<text class="chart-label" x="${P.l}" y="${P.t - 14}" fill="var(--accent-hi)" font-weight="600">MAKHACHEV</text>`;
    out += `<text class="chart-label" x="${P.l + iw}" y="${P.t - 14}" text-anchor="end" fill="var(--cool)" font-weight="600">OLIVEIRA</text>`;

    rows.forEach((r, i) => {
      const cy = P.t + i * rowH + rowH / 2;
      const maxV = Math.max(r.a, r.b, 1);
      const scale = maxHalf / Math.max(maxV, 1);
      const wa = r.a * scale, wb = r.b * scale;
      out += `<rect x="${(mid - wa).toFixed(1)}" y="${(cy - 7).toFixed(1)}" width="${wa.toFixed(1)}" height="14" fill="var(--accent)" opacity="0.85"><title>Makhachev ${r.a}${r.unit}</title></rect>`;
      out += `<rect x="${mid.toFixed(1)}" y="${(cy - 7).toFixed(1)}" width="${wb.toFixed(1)}" height="14" fill="var(--cool)" opacity="0.85"><title>Oliveira ${r.b}${r.unit}</title></rect>`;
      out += `<text class="chart-axis-strong" x="${(mid - wa - 6).toFixed(1)}" y="${(cy + 3.5).toFixed(1)}" text-anchor="end">${r.a}${r.unit}</text>`;
      out += `<text class="chart-axis-strong" x="${(mid + wb + 6).toFixed(1)}" y="${(cy + 3.5).toFixed(1)}" text-anchor="start">${r.b}${r.unit}</text>`;
      out += `<text class="chart-label" x="${mid.toFixed(1)}" y="${(cy - 12).toFixed(1)}" text-anchor="middle">${esc(r.label)}</text>`;
      if (i === 2) out += `<line x1="${P.l}" y1="${(P.t + 3 * rowH).toFixed(1)}" x2="${P.l + iw}" y2="${(P.t + 3 * rowH).toFixed(1)}" stroke="var(--line-faint)"/>`;
    });
    out += `<text class="chart-label" x="${(P.l + iw).toFixed(1)}" y="${(H - P.b + 2).toFixed(1)}" text-anchor="end" fill="var(--accent-hi)">arm-triangle · R${M.round} ${esc(M.time)}</text>`;

    const t = $("[data-mom-title]");
    if (t) t.textContent = "Makhachev vs. Oliveira — the real rounds";
    mount("[data-chart-momentum]",
      svg(W, H, out, "Mirrored bar chart of official round statistics: Makhachev dominates strikes, control time and takedowns in both rounds before the arm-triangle finish."));
  }

  /* ---- 03: era quiz from real shapes ------------------------------------- */
  function renderQuiz() {
    const chartEl = $("[data-quiz-chart]");
    if (!chartEl || !hasReal()) return;
    fill("quiz", DISCOVERIES.quiz);

    const ERAS = ["1994-1999", "2005-2009", "2010-2014", "2020-2026"];
    const LABELS = { "1994-1999": "1990s", "2005-2009": "2000s", "2010-2014": "2010s", "2020-2026": "2020s" };
    const REVEAL = {
      "1994-1999": `Front-loaded, fading. Almost a trick question: only 3 three-round decisions exist in the whole era, because ${(REAL.quiz_shapes["1994-1999"].finish_rate * 100).toFixed(0)}% of nineties fights ended early — which is itself the era's signature.`,
      "2005-2009": `Flat as a metronome — the sprawl-and-grind years. Output barely moves across rounds, and ${(REAL.quiz_shapes["2005-2009"].finish_rate * 100).toFixed(0)}% of fights still finished (n = ${REAL.quiz_shapes["2005-2009"].n} decisions).`,
      "2010-2014": `A gentle climb — the point-fighting decade learns to pace. Round 3 becomes the busiest round for the first time (n = ${REAL.quiz_shapes["2010-2014"].n}).`,
      "2020-2026": `The modern shape: starts measured, escalates hard — round 3 output is 18% above round 1. Fighters now finish faster than they start (n = ${REAL.quiz_shapes["2020-2026"].n}).`,
    };

    const order = ERAS.map((e, i) => i).sort(() => Math.random() - 0.5);
    let idx = 0, score = 0, asked = 0, locked = false;

    const drawShape = (shape) => {
      const W = 420, H = 190, P = { t: 18, r: 14, b: 28, l: 14 };
      const iw = W - P.l - P.r, ih = H - P.t - P.b;
      const bw = iw / 3 * 0.6;
      let out = `<line x1="${P.l}" y1="${P.t + ih}" x2="${P.l + iw}" y2="${P.t + ih}" stroke="var(--line)"/>`;
      shape.forEach((v, i) => {
        const cx = P.l + (i + 0.5) * (iw / 3);
        const h = v * ih;
        out += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${(P.t + ih - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="var(--accent)" opacity="0.85"/>`;
        out += `<text class="chart-label" x="${cx.toFixed(1)}" y="${H - 8}" text-anchor="middle">round ${i + 1}</text>`;
      });
      chartEl.innerHTML = svg(W, H, out, "Three anonymised bars: combined strikes landed in rounds one, two and three for a mystery era.");
    };

    const scoreEl = $("[data-quiz-score]");
    const revealEl = $("[data-quiz-reveal]");
    const actionsEl = $("[data-quiz-actions]");

    const ask = () => {
      locked = false;
      const era = ERAS[order[idx % order.length]];
      drawShape(REAL.quiz_shapes[era].shape);
      revealEl.textContent = "";
      revealEl.className = "quiz-reveal";
      actionsEl.innerHTML = ERAS.map((e) => `<button class="quiz-btn" data-pick="${e}">${LABELS[e]}</button>`).join("");
      actionsEl.querySelectorAll("button").forEach((b) =>
        b.addEventListener("click", () => {
          if (locked) return;
          locked = true;
          asked += 1;
          const right = b.getAttribute("data-pick") === era;
          if (right) score += 1;
          scoreEl.textContent = `${score} / ${asked}`;
          actionsEl.querySelectorAll("button").forEach((btn) => {
            const isAns = btn.getAttribute("data-pick") === era;
            btn.classList.add(isAns ? "is-right" : btn === b ? "is-wrong" : "is-dim");
            btn.disabled = true;
          });
          revealEl.className = "quiz-reveal " + (right ? "ok" : "no");
          revealEl.innerHTML = `<strong>${right ? "Correct — the " + LABELS[era] : "It's the " + LABELS[era]}.</strong> ${esc(REVEAL[era])} <button class="quiz-next">Next shape →</button>`;
          revealEl.querySelector(".quiz-next").addEventListener("click", () => { idx += 1; ask(); });
        })
      );
    };
    ask();
  }

  /* ---- 04: method mix by year + pace by era ------------------------------ */
  function renderEras() {
    const el = $("[data-chart-methods]");
    if (!el || !hasReal()) return;
    fill("eras", DISCOVERIES.eras);

    // 3-year centred rolling mean over yearly ko/sub/dec shares
    const years = Object.keys(REAL.method_by_year).map(Number).filter((y) => y >= 1994).sort((a, b) => a - b);
    const smooth = (key) => years.map((y, i) => {
      const win = [years[i - 1], y, years[i + 1]].filter((w) => w !== undefined);
      let num = 0, den = 0;
      win.forEach((w) => {
        const d = REAL.method_by_year[String(w)];
        if (d) { num += d[key] * d.n; den += d.n; }
      });
      return num / den;
    });
    const ko = smooth("ko"), sub = smooth("sub"), dec = smooth("dec");

    const W = 860, H = 330, P = { t: 34, r: 16, b: 40, l: 40 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const x = (yr) => P.l + ((yr - years[0]) / (years[years.length - 1] - years[0])) * iw;
    const y = (v) => P.t + (1 - v) * ih;

    const seriesList = [
      { vals: ko, col: "var(--accent)", op: 0.8, name: "KO/TKO" },
      { vals: sub, col: "var(--cool)", op: 0.7, name: "Submission" },
      { vals: dec, col: "var(--fg-38)", op: 0.5, name: "Decision" },
    ];
    let stackedAreas = "";
    seriesList.forEach((s, si) => {
      let top = "", bot = "";
      years.forEach((yr, i) => {
        let acc = 0;
        for (let j = 0; j <= si; j++) acc += seriesList[j].vals[i];
        top += `${i ? "L" : "M"}${x(yr).toFixed(1)},${y(acc).toFixed(1)} `;
      });
      for (let i = years.length - 1; i >= 0; i--) {
        let acc = 0;
        for (let j = 0; j < si; j++) acc += seriesList[j].vals[i];
        bot += `L${x(years[i]).toFixed(1)},${y(acc).toFixed(1)} `;
      }
      stackedAreas += `<path d="${top}${bot}Z" fill="${s.col}" opacity="${s.op}" stroke="var(--bg)" stroke-width="0.75"><title>${s.name}</title></path>`;
    });

    const shocks = [
      { year: 1997, label: "Gloves mandatory" },
      { year: 2001, label: "Unified Rules" },
      { year: 2009, label: "Rules nationwide" },
      { year: 2024, label: "12-6 elbow returns" },
    ].map((sh, i) => {
      const sx = x(sh.year);
      const flip = sx > P.l + iw * 0.72;
      return `<line x1="${sx.toFixed(1)}" y1="${P.t - 4}" x2="${sx.toFixed(1)}" y2="${P.t + ih}" stroke="var(--fg)" stroke-width="1" stroke-dasharray="2 3" opacity="0.75"/>
      <text class="chart-label" x="${(sx + (flip ? -4 : 4)).toFixed(1)}" y="${P.t + 10 + (i % 2) * 13}" text-anchor="${flip ? "end" : "start"}">${esc(sh.label)}</text>`;
    }).join("");

    const inlbl =
      `<text class="chart-label" x="${x(1999).toFixed(1)}" y="${y(0.2).toFixed(1)}" fill="var(--bg)" font-weight="600">KO</text>` +
      `<text class="chart-label" x="${x(1999).toFixed(1)}" y="${y(0.55).toFixed(1)}" fill="var(--bg)" font-weight="600">SUB</text>` +
      `<text class="chart-label" x="${x(2016).toFixed(1)}" y="${y(0.78).toFixed(1)}" fill="var(--fg)" font-weight="600">DECISION</text>`;

    let axes = "";
    [1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022, 2026].forEach((yr) => {
      axes += `<text x="${x(yr).toFixed(1)}" y="${P.t + ih + 18}" text-anchor="middle">${yr}</text>`;
    });
    [0, 0.5, 1].forEach((v) => (axes += `<text x="${P.l - 8}" y="${(y(v) + 3.5).toFixed(1)}" text-anchor="end">${v * 100}%</text>`));
    const frame = `<rect class="chart-frame" x="${P.l}" y="${P.t}" width="${iw}" height="${ih}"/>`;

    mount("[data-chart-methods]",
      svg(W, H, `${stackedAreas}${inlbl}${shocks}${frame}<g class="chart-axis">${axes}</g>`,
        "Stacked area of fight outcomes by year: knockouts and submissions shrink while decisions grow to half of all fights, with rule changes marked."));
    legend("[data-eras-legend]", [["KO/TKO", "var(--accent)"], ["Submission", "var(--cool)"], ["Decision", "var(--fg-38)"]]);

    // pace bars by era
    const paceEl = $("[data-chart-pace]");
    if (paceEl) {
      const vals = ERA_KEYS.map((k) => REAL.eras[k].mean_sig_landed_per_round_per_fighter);
      const W2 = 420, H2 = 240, P2 = { t: 16, r: 12, b: 30, l: 34 };
      const iw2 = W2 - P2.l - P2.r, ih2 = H2 - P2.t - P2.b;
      const max = Math.max(...vals) * 1.15;
      const bw = iw2 / vals.length * 0.62;
      let out = "";
      vals.forEach((v, i) => {
        const cx = P2.l + (i + 0.5) * (iw2 / vals.length);
        const h = (v / max) * ih2;
        const hot = i === vals.length - 1;
        out += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${(P2.t + ih2 - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${hot ? "var(--accent)" : "var(--fg-38)"}" opacity="0.9"/>`;
        out += `<text class="chart-axis-strong" x="${cx.toFixed(1)}" y="${(P2.t + ih2 - h - 7).toFixed(1)}" text-anchor="middle">${v.toFixed(1)}</text>`;
        out += `<text class="chart-label" x="${cx.toFixed(1)}" y="${H2 - 8}" text-anchor="middle">${ERA_SHORT[i]}</text>`;
      });
      out += `<line x1="${P2.l}" y1="${P2.t + ih2}" x2="${P2.l + iw2}" y2="${P2.t + ih2}" stroke="var(--line)"/>`;
      mount("[data-chart-pace]", svg(W2, H2, out, "Bar chart: significant strikes landed per fighter per round triples from 6 in the 1990s to 18.2 in the 2020s."));
    }
  }

  /* ---- 05: behaviour red list -------------------------------------------- */
  function renderRedlist() {
    const el = $("[data-redlist]");
    if (!el || !hasReal()) return;
    fill("red", DISCOVERIES.redlist);

    const eras = ERA_KEYS;
    const items = [
      {
        name: "Ground striking",
        status: "Critically endangered",
        tone: "down",
        spark: eras.map((e) => REAL.position_by_era[e].ground),
        note: `From ${(REAL.position_by_era["1994-1999"].ground * 100).toFixed(0)}% of all landed strikes to ${(REAL.position_by_era["2020-2026"].ground * 100).toFixed(0)}%. The single steepest behavioural decline in the sport's history.`,
      },
      {
        name: "Submission hunting",
        status: "Endangered",
        tone: "down",
        spark: eras.map((e) => REAL.subatt_by_era[e].subatt_per_fight),
        note: `Submission attempts per fight peaked at ${REAL.subatt_by_era["2005-2009"].subatt_per_fight.toFixed(2)} in the late 2000s and have fallen to ${REAL.subatt_by_era["2020-2026"].subatt_per_fight.toFixed(2)} — down 56% from peak.`,
      },
      {
        name: "Takedown efficiency",
        status: "Declining",
        tone: "watch",
        spark: eras.map((e) => REAL.td_by_era[e].accuracy),
        note: `Attempts doubled while accuracy fell ${(REAL.td_by_era["1994-1999"].accuracy * 100).toFixed(0)}% → ${(REAL.td_by_era["2020-2026"].accuracy * 100).toFixed(0)}%. Everyone learned to shoot; everyone learned to sprawl faster.`,
      },
      {
        name: "Leg kicks",
        status: "Stable — surprisingly",
        tone: "stable",
        spark: eras.map((e) => REAL.target_by_era[e].leg),
        note: "Flat at ~15–17% of landed strikes for two decades. The famous calf-kick boom is invisible in aggregate — it substituted calf for thigh, not more for less.",
      },
      {
        name: "12-6 elbow",
        status: "Back from extinct",
        tone: "revived",
        spark: [0.4, 0, 0, 0, 0, 0.15],
        note: "Banned by the Unified Rules in 2001, re-legalised late 2024. Twenty-three years of enforced zero, now recolonising. (Rule record, not usage data.)",
      },
    ];

    const sparkSvg = (vals, tone) => {
      const W = 130, H = 34;
      const max = Math.max(...vals) || 1;
      const x = (i) => (i / (vals.length - 1)) * (W - 4) + 2;
      const y = (v) => 2 + (1 - v / max) * (H - 6);
      const path = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
      const col = tone === "down" ? "var(--cool)" : tone === "stable" ? "var(--fg-55)" : "var(--accent)";
      return svg(W, H, `<path d="${path}" fill="none" stroke="${col}" stroke-width="1.75"/>`, "era usage trend");
    };

    el.innerHTML = items.map((t) => `
      <div class="card redlist-card" data-tone="${esc(t.tone)}">
        <div class="redlist-head">
          <h3>${esc(t.name)}</h3>
          <span class="redlist-badge" data-tone="${esc(t.tone)}">${esc(t.status)}</span>
        </div>
        <div class="redlist-spark">${sparkSvg(t.spark, t.tone)}</div>
        <p>${esc(t.note)}</p>
      </div>`).join("");
  }

  /* ---- 06: forest plot + age cliff --------------------------------------- */
  function renderBodies() {
    const el = $("[data-chart-forest]");
    if (!el || !hasReal()) return;
    fill("bodies", DISCOVERIES.bodies);

    const rows = [
      { name: "Age gap 7+ years (younger)", d: REAL.age.by_gap["7+y"] },
      { name: "Younger fighter (any gap)", d: REAL.age.younger_overall },
      { name: "Reach advantage 5″+", d: REAL.reach.by_bin["5+in"] },
      { name: "Southpaw (vs orthodox)", d: REAL.stance.southpaw_vs_orthodox },
      { name: "Height advantage (any)", d: REAL.height.overall },
      { name: "Reach advantage (any)", d: REAL.reach.overall },
    ];

    const W = 520, H = 46 * rows.length + 44, P = { t: 22, r: 56, b: 26, l: 6 };
    const x0 = 0.45, x1 = 0.7;
    const iw = W - P.l - P.r;
    const x = (v) => P.l + ((v - x0) / (x1 - x0)) * iw;

    let out = `<line x1="${x(0.5)}" y1="${P.t - 6}" x2="${x(0.5)}" y2="${H - P.b}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>` +
      `<text class="chart-label" x="${x(0.5)}" y="${P.t - 10}" text-anchor="middle">coin flip</text>`;
    rows.forEach((r, i) => {
      const cy = P.t + i * 46 + 30;
      out += `<text class="chart-axis-strong" x="${P.l}" y="${cy - 14}">${esc(r.name)}</text>`;
      out += `<line x1="${x(r.d.ci[0]).toFixed(1)}" y1="${cy}" x2="${x(r.d.ci[1]).toFixed(1)}" y2="${cy}" stroke="var(--fg-55)" stroke-width="2"/>`;
      [r.d.ci[0], r.d.ci[1]].forEach((c) => {
        out += `<line x1="${x(c).toFixed(1)}" y1="${cy - 4}" x2="${x(c).toFixed(1)}" y2="${cy + 4}" stroke="var(--fg-55)" stroke-width="2"/>`;
      });
      const big = r.d.win >= 0.55;
      out += `<circle cx="${x(r.d.win).toFixed(1)}" cy="${cy}" r="5.5" fill="${big ? "var(--accent)" : "var(--fg)"}" stroke="var(--bg)" stroke-width="1.5"/>`;
      out += `<text class="chart-axis-strong" x="${W - P.r + 8}" y="${cy + 3.5}" fill="${big ? "var(--accent-hi)" : "var(--fg-55)"}">${(r.d.win * 100).toFixed(1)}%</text>`;
      out += `<text class="chart-label" x="${W - P.r + 8}" y="${cy + 15}" opacity="0.7">n=${r.d.n.toLocaleString()}</text>`;
    });

    mount("[data-chart-forest]",
      svg(W, H, out, "Forest plot of win rates with confidence intervals: age advantages clear 55 percent while reach, height and stance sit just above a coin flip."));

    // age cliff
    const cliffEl = $("[data-chart-agecliff]");
    if (cliffEl) {
      const bands = ["20-24", "25-29", "30-34", "35-39", "40+"];
      const W2 = 520, H2 = 220, P2 = { t: 18, r: 16, b: 30, l: 40 };
      const iw2 = W2 - P2.l - P2.r, ih2 = H2 - P2.t - P2.b;
      const y = (v) => P2.t + (1 - (v - 0.3) / (0.65 - 0.3)) * ih2;
      const x = (i) => P2.l + (i + 0.5) * (iw2 / bands.length);
      let out2 = `<line x1="${P2.l}" y1="${y(0.5)}" x2="${P2.l + iw2}" y2="${y(0.5)}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>` +
        `<text class="chart-label" x="${P2.l + iw2}" y="${(y(0.5) - 6).toFixed(1)}" text-anchor="end">50%</text>`;
      const path = bands.map((b, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(REAL.age.by_band[b].win).toFixed(1)}`).join(" ");
      out2 += `<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
      bands.forEach((b, i) => {
        const d = REAL.age.by_band[b];
        out2 += `<line x1="${x(i).toFixed(1)}" y1="${y(d.ci[0]).toFixed(1)}" x2="${x(i).toFixed(1)}" y2="${y(d.ci[1]).toFixed(1)}" stroke="var(--accent)" opacity="0.45" stroke-width="2"/>`;
        out2 += `<circle cx="${x(i).toFixed(1)}" cy="${y(d.win).toFixed(1)}" r="4.5" fill="var(--accent)" stroke="var(--bg)" stroke-width="1.5"><title>${b}: ${(d.win * 100).toFixed(1)}% (n=${d.n})</title></circle>`;
        out2 += `<text class="chart-axis-strong" x="${x(i).toFixed(1)}" y="${(y(d.win) - 12).toFixed(1)}" text-anchor="middle">${(d.win * 100).toFixed(0)}%</text>`;
        out2 += `<text class="chart-label" x="${x(i).toFixed(1)}" y="${H2 - 8}" text-anchor="middle">${b}</text>`;
      });
      mount("[data-chart-agecliff]",
        svg(W2, H2, out2, "Line chart: win rate falls from 58.8 percent for fighters aged 20 to 24 down to 35.8 percent past 40."));
    }
  }

  /* ---- 07: warnings — KD doom, finish clock, autopsy ---------------------- */
  function renderWarnings() {
    const el = $("[data-chart-clock]");
    if (!el || !hasReal()) return;
    fill("warn", DISCOVERIES.warnings);

    const kd = $("[data-kd-doom]");
    if (kd) kd.textContent = (REAL.kd_doom.any_kd_loss_rate * 100).toFixed(1) + "%";
    const kdn = $("[data-kd-n]");
    if (kdn) kdn.textContent = `(n = ${REAL.kd_doom.n.toLocaleString()}, 95% CI ${(REAL.kd_doom.ci[0] * 100).toFixed(1)}–${(REAL.kd_doom.ci[1] * 100).toFixed(1)}%)`;

    // finish clock, minutes 1..15 (3-round window covers the bulk)
    const mins = Array.from({ length: 15 }, (_, i) => i + 1);
    const koV = mins.map((m) => REAL.finish_clock.ko_by_minute[String(m)] || 0);
    const subV = mins.map((m) => REAL.finish_clock.sub_by_minute[String(m)] || 0);
    const W = 520, H = 240, P = { t: 20, r: 12, b: 34, l: 34 };
    const iw = W - P.l - P.r, ih = H - P.t - P.b;
    const max = Math.max(...koV.map((v, i) => v + subV[i])) * 1.08;
    const bw = iw / mins.length * 0.66;
    let out = "";
    mins.forEach((m, i) => {
      const cx = P.l + (i + 0.5) * (iw / mins.length);
      const hk = (koV[i] / max) * ih, hs = (subV[i] / max) * ih;
      out += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${(P.t + ih - hk).toFixed(1)}" width="${bw.toFixed(1)}" height="${hk.toFixed(1)}" fill="var(--accent)" opacity="0.85"><title>min ${m}: ${koV[i]} KOs</title></rect>`;
      out += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${(P.t + ih - hk - hs).toFixed(1)}" width="${bw.toFixed(1)}" height="${hs.toFixed(1)}" fill="var(--cool)" opacity="0.8"><title>min ${m}: ${subV[i]} subs</title></rect>`;
      if (m % 5 === 0 || m === 1) out += `<text class="chart-label" x="${cx.toFixed(1)}" y="${H - 8}" text-anchor="middle">${m}</text>`;
    });
    [5, 10].forEach((m) => {
      const bx = P.l + m * (iw / mins.length);
      out += `<line x1="${bx.toFixed(1)}" y1="${P.t}" x2="${bx.toFixed(1)}" y2="${P.t + ih}" stroke="var(--fg-38)" stroke-dasharray="2 3"/>`;
      out += `<text class="chart-label" x="${(bx - 4).toFixed(1)}" y="${P.t + 10}" text-anchor="end">end R${m / 5}</text>`;
    });
    out += `<line x1="${P.l}" y1="${P.t + ih}" x2="${P.l + iw}" y2="${P.t + ih}" stroke="var(--line)"/>`;
    out += `<text class="chart-label" x="${(P.l + iw / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle" opacity="0">.</text>`;
    mount("[data-chart-clock]",
      svg(W, H, out, "Stacked histogram of finishes by fight minute: spikes at minutes 5, 10 and 15 — the final minute of each round."));
    legend("[data-clock-legend]", [["KO/TKO", "var(--accent)"], ["Submission", "var(--cool)"]]);

    // autopsy bars
    const NAMES = {
      kd_suffered: "Knockdowns suffered",
      head_absorbed: "Head strikes absorbed",
      sig_absorbed: "Sig. strikes absorbed",
      subatt_against: "Sub attempts against",
      ctrl_conceded: "Control time conceded",
      td_landed_against: "Takedowns absorbed",
    };
    const autopsyChart = (sel, data, col) => {
      const rows = data.top_warnings;
      const W3 = 460, H3 = 40 * rows.length + 36, P3 = { t: 12, r: 52, b: 24, l: 6 };
      const iw3 = W3 - P3.l - P3.r;
      const maxR = 3.0;
      const x = (v) => P3.l + (v / maxR) * iw3;
      let o = `<line x1="${x(1)}" y1="${P3.t}" x2="${x(1)}" y2="${H3 - P3.b}" stroke="var(--fg-38)" stroke-dasharray="3 3"/>` +
        `<text class="chart-label" x="${x(1)}" y="${H3 - 8}" text-anchor="middle">1.0× (decision baseline)</text>`;
      rows.forEach((r, i) => {
        const cy = P3.t + i * 40 + 26;
        o += `<text class="chart-axis-strong" x="${P3.l}" y="${cy - 12}">${esc(NAMES[r.sign] || r.sign)}</text>`;
        o += `<rect x="${x(0).toFixed(1)}" y="${cy - 6}" width="${(x(r.ratio) - x(0)).toFixed(1)}" height="12" fill="${col}" opacity="0.85"/>`;
        o += `<text class="chart-axis-strong" x="${(x(r.ratio) + 6).toFixed(1)}" y="${cy + 3.5}" fill="${col}">${r.ratio.toFixed(2)}×</text>`;
      });
      mount(sel, svg(W3, H3, o, "Horizontal bars showing how elevated each warning sign is versus the decision baseline."));
    };
    autopsyChart("[data-chart-autopsy-ko]", REAL.autopsy.ko, "var(--accent)");
    autopsyChart("[data-chart-autopsy-sub]", REAL.autopsy.sub, "var(--cool)");
  }

  /* ---- 08: career tree rings (unchanged concept) -------------------------- */
  function renderRings() {
    const el = $("[data-chart-rings]");
    if (!el || typeof DISCOVERIES === "undefined") return;
    const d = DISCOVERIES.rings;
    document.querySelectorAll("[data-d-rings-headline]").forEach((e) => (e.textContent = d.headline));
    paras("[data-d-rings-body]", d.body);
    const fEl = $("[data-d-rings-falsify]");
    if (fEl) fEl.innerHTML = `<strong>Falsifiable.</strong> ${esc(d.falsify)}`;
    mount("[data-d-rings-caveat]", caveat(d));
    const f = $("[data-d-rings-fighter]");
    if (f) f.textContent = d.fighter;

    const W = 420, H = 420, cx = W / 2, cy = H / 2;
    const inner = 26;
    let r = inner, out = "";
    d.years.forEach((yr) => {
      const thick = 2.5 + yr.fights * 2.6;
      const rMid = r + thick / 2;
      const finishRate = yr.fights ? yr.finishes / yr.fights : 0;
      const col = yr.fights === 0 ? "var(--line-faint)" : finishRate > 0.5 ? "var(--accent)" : finishRate > 0 ? "rgba(255,77,61,0.45)" : "var(--fg-38)";
      out += `<circle cx="${cx}" cy="${cy}" r="${rMid.toFixed(1)}" fill="none" stroke="${col}" stroke-width="${thick.toFixed(1)}" opacity="${yr.fights === 0 ? 0.9 : 0.85}"><title>${yr.year}: ${yr.fights} fight${yr.fights === 1 ? "" : "s"}, ${yr.finishes} finish${yr.finishes === 1 ? "" : "es"}${yr.note ? " — " + esc(yr.note) : ""}</title></circle>`;
      if (yr.scar) {
        const a = -Math.PI / 4;
        const sx = cx + rMid * Math.cos(a), sy = cy + rMid * Math.sin(a);
        out += `<circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="${(thick / 2 + 2).toFixed(1)}" fill="var(--bg)" stroke="var(--fg)" stroke-width="1.25"/>`;
      }
      r += thick + 2;
    });

    const ann = [
      { yi: 5, text: "2007 — the scar" },
      { yi: 13, text: "the drought" },
      { yi: 15, text: "2017 — one last ring" },
    ];
    let notes = "";
    ann.forEach((a, k) => {
      let rr = inner;
      for (let i = 0; i < a.yi; i++) rr += 2.5 + d.years[i].fights * 2.6 + 2;
      rr += (2.5 + d.years[a.yi].fights * 2.6) / 2;
      const ang = (-160 + k * 115) * (Math.PI / 180);
      const px = cx + rr * Math.cos(ang), py = cy + rr * Math.sin(ang);
      const lx = cx + (rr + 46) * Math.cos(ang), ly = cy + (rr + 46) * Math.sin(ang);
      const anchor = lx > cx ? "start" : "end";
      notes += `<line x1="${px.toFixed(1)}" y1="${py.toFixed(1)}" x2="${lx.toFixed(1)}" y2="${ly.toFixed(1)}" stroke="var(--fg-38)" stroke-width="1"/>
        <text class="chart-label" x="${(lx + (anchor === "start" ? 4 : -4)).toFixed(1)}" y="${(ly + 3).toFixed(1)}" text-anchor="${anchor}" fill="var(--fg-70)" stroke="var(--bg)" stroke-width="3.5" paint-order="stroke" stroke-linejoin="round">${esc(a.text)}</text>`;
    });

    const core = `<circle cx="${cx}" cy="${cy}" r="${inner - 8}" fill="none" stroke="var(--line)" stroke-width="1"/>
      <text class="chart-label" x="${cx}" y="${cy + 3}" text-anchor="middle">debut</text>`;

    mount("[data-chart-rings]",
      svg(W, H, core + out + notes,
        "A fighter's career rendered as tree rings: one ring per year read outward from debut, with visible scars and a four-year gap before a final ring."));
  }

  /* ---- methods + nulls + next queue --------------------------------------- */
  function renderDiscoveryExtras() {
    if (typeof DISCOVERIES === "undefined") return;
    const g = $("[data-grammar]");
    if (g) g.textContent = DISCOVERIES.intro.grammar;

    const ms = $("[data-methods-source]");
    if (ms && DISCOVERIES.methods) ms.textContent = DISCOVERIES.methods.source;
    if (DISCOVERIES.methods) {
      mount("[data-methods-bullets]", DISCOVERIES.methods.bullets.map((b) => `<li>${esc(b)}</li>`).join(""));
      mount("[data-nulls]", DISCOVERIES.methods.nulls.map((nl) => `
        <div class="null-row">
          <span class="null-claim">${esc(nl.claim)}</span>
          <span class="null-result">${esc(nl.result)}</span>
        </div>`).join(""));
    }

    mount("[data-next]", DISCOVERIES.next.map((nx) => `
      <div class="card">
        <span class="card-tag">Queued</span>
        <h3>${esc(nx.title)}</h3>
        <p>${esc(nx.body)}</p>
      </div>`).join(""));
  }

  /* =======================================================================
     Scroll reveal — classes are added from JS so a no-JS load still shows
     everything; bars animate when their section enters the viewport.
     ======================================================================= */
  function initReveal() {
    const targets = document.querySelectorAll(".section > .wrap, .case, .footer .wrap");
    if (!("IntersectionObserver" in window)) {
      targets.forEach((t) => t.classList.add("inview"));
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) {
            en.target.classList.add("inview");
            obs.unobserve(en.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }
    );
    targets.forEach((t) => {
      t.classList.add("reveal");
      obs.observe(t);
    });
  }

  /* =======================================================================
     Boot
     ======================================================================= */
  function boot() {
    try {
      renderMeta();
      renderHero();
      renderPipeline();
      renderEnsemble();
      renderResults();
      renderReliability();
      renderBrier();
      renderFeatures();
      renderShap();
      renderLimitations();
      renderRoadmap();
      renderRigor();
      renderDashboard();
      renderCaseTeasers();
      renderCaseStudies();
      renderPosition();
      renderMomentum();
      renderQuiz();
      renderEras();
      renderRedlist();
      renderBodies();
      renderWarnings();
      renderRings();
      renderDiscoveryExtras();
      initScrollSpy();
      initReveal();
    } catch (err) {
      console.error("[MetricCage] render failed:", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

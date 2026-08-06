/* ===========================================================================
   MetricCage — interactive charts (D3 v7, self-hosted at assets/vendor/).
   Every number drawn here is a value published in the 2026 season report;
   nothing is interpolated or invented between stated data points. Charts
   render into placeholder elements by id and are skipped when absent, so
   each page loads only what it declares. The pages remain readable with
   JavaScript off: every chart repeats its headline figures in the
   surrounding prose and tables.
   =========================================================================== */
(function () {
  "use strict";
  if (typeof d3 === "undefined") return;

  var css = getComputedStyle(document.documentElement);
  function tok(name, fallback) {
    var v = css.getPropertyValue(name).trim();
    return v || fallback;
  }
  var INK = tok("--ink", "#000");
  var SLATE = tok("--slate", "#9CABC2");
  var SLATE60 = tok("--slate-a60", "rgba(156,171,194,.6)");
  var SLATE15 = tok("--slate-a15", "rgba(156,171,194,.15)");
  var FILL = tok("--fill", "#DDE3EA");
  var QUIET = tok("--ink-a62", "rgba(0,0,0,.62)");
  var PAPER = tok("--paper", "#ECF0F3");
  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var DUR = REDUCED ? 0 : 600;

  /* ---- tooltip (one per page) --------------------------------------------- */
  var tip = d3.select("body").append("div").attr("class", "d3tip").style("opacity", 0);
  function tipShow(event, html) {
    tip.html(html).style("opacity", 1);
    tipMove(event);
  }
  function tipMove(event) {
    var pad = 14, w = tip.node().offsetWidth;
    var x = event.pageX + pad;
    if (x + w > window.scrollX + document.documentElement.clientWidth - 8) x = event.pageX - w - pad;
    tip.style("left", x + "px").style("top", (event.pageY - 12) + "px");
  }
  function tipHide() { tip.style("opacity", 0); }

  function svgIn(sel, w, h, label) {
    return d3.select(sel).append("svg")
      .attr("viewBox", [0, 0, w, h])
      .attr("role", "img")
      .attr("aria-label", label)
      .attr("style", "width:100%;height:auto;display:block");
  }
  function fmtPct(v) { return d3.format(".1f")(v) + "%"; }

  /* =========================================================================
     1. Season, card by card — high-conviction calls per event
     ========================================================================= */
  if (document.getElementById("chart-season")) {
    var SEASON = [
      { card: "Gaethje vs. Pimblett", kind: "UFC 324", date: "24 Jan", calls: 3, correct: 2, slug: "ufc-324" },
      { card: "Volkanovski vs. Lopes 2", kind: "UFC 325", date: "31 Jan", calls: 3, correct: 3, slug: "ufc-325" },
      { card: "Bautista vs. Oliveira", kind: "Fight Night", date: "7 Feb", calls: 4, correct: 3, slug: "fn-bautista" },
      { card: "Strickland vs. Hernandez", kind: "Fight Night", date: "21 Feb", calls: 5, correct: 4, slug: "fn-strickland" },
      { card: "Moreno vs. Kavanagh", kind: "Fight Night", date: "28 Feb", calls: 4, correct: 4, slug: "fn-moreno" },
      { card: "Holloway vs. Oliveira 2", kind: "UFC 326", date: "7 Mar", calls: 4, correct: 3, slug: "ufc-326" },
      { card: "Emmett vs. Vallejos", kind: "Fight Night", date: "14 Mar", calls: 4, correct: 3, slug: "fn-emmett" },
      { card: "Evloev vs. Murphy", kind: "Fight Night", date: "21 Mar", calls: 6, correct: 5, slug: "fn-evloev" },
      { card: "Adesanya vs. Pyfer", kind: "Fight Night", date: "28 Mar", calls: 8, correct: 4, slug: "fn-adesanya" },
      { card: "Moicano vs. Duncan", kind: "Fight Night", date: "4 Apr", calls: 3, correct: 2, slug: "fn-moicano" },
      { card: "Prochazka vs. Ulberg", kind: "UFC 327", date: "11 Apr", calls: 2, correct: 2, slug: "ufc-327" },
      { card: "Burns vs. Malott", kind: "Fight Night", date: "18 Apr", calls: 1, correct: 1, slug: "fn-burns" },
      { card: "Sterling vs. Zalal", kind: "Fight Night", date: "25 Apr", calls: 2, correct: 1, slug: "fn-sterling" },
      { card: "Della Maddalena vs. Prates", kind: "Fight Night", date: "2 May", calls: 6, correct: 5, slug: "fn-dellamaddalena" }
    ];
    var mw = 660, mh = 250, mt = 16, mr = 8, mb = 54, ml = 30;
    var svg = svgIn("#chart-season", mw, mh,
      "High-conviction calls per 2026 card: correct calls in black over total calls in grey, 42 of 55 across the season");
    var x = d3.scaleBand().domain(SEASON.map(function (d) { return d.date; })).range([ml, mw - mr]).padding(0.28);
    var y = d3.scaleLinear().domain([0, 8]).range([mh - mb, mt]);

    svg.append("g").selectAll("line").data(y.ticks(4)).join("line")
      .attr("x1", ml).attr("x2", mw - mr).attr("y1", y).attr("y2", y)
      .attr("stroke", SLATE15).attr("stroke-width", 1);

    var g = svg.append("g").selectAll("g").data(SEASON).join("g")
      .attr("class", "hoverable")
      .style("cursor", "pointer")
      .on("pointerenter", function (event, d) {
        d3.select(this).selectAll("rect").attr("opacity", 0.82);
        tipShow(event, "<b>" + d.kind + " — " + d.card + "</b><br>" + d.date + " 2026 · " +
          d.correct + " of " + d.calls + " high-conviction calls correct");
      })
      .on("pointermove", tipMove)
      .on("pointerleave", function () { d3.select(this).selectAll("rect").attr("opacity", 1); tipHide(); })
      .on("click", function (event, d) { window.location.href = "case-studies.html#" + d.slug; });

    g.append("rect")
      .attr("x", function (d) { return x(d.date); }).attr("width", x.bandwidth())
      .attr("fill", SLATE60).attr("rx", 2)
      .attr("y", y(0)).attr("height", 0)
      .transition().duration(DUR)
      .attr("y", function (d) { return y(d.calls); })
      .attr("height", function (d) { return y(0) - y(d.calls); });
    g.append("rect")
      .attr("x", function (d) { return x(d.date); }).attr("width", x.bandwidth())
      .attr("fill", INK).attr("rx", 2)
      .attr("y", y(0)).attr("height", 0)
      .transition().duration(DUR).delay(REDUCED ? 0 : 150)
      .attr("y", function (d) { return y(d.correct); })
      .attr("height", function (d) { return y(0) - y(d.correct); });
    g.append("text")
      .attr("x", function (d) { return x(d.date) + x.bandwidth() / 2; })
      .attr("y", function (d) { return y(d.calls) - 5; })
      .attr("text-anchor", "middle").attr("font-size", 10).attr("font-weight", 700).attr("fill", INK)
      .text(function (d) { return d.correct + "/" + d.calls; });

    svg.append("g").attr("transform", "translate(0," + (mh - mb) + ")")
      .call(d3.axisBottom(x).tickSize(0).tickPadding(8))
      .call(function (ax) { ax.select(".domain").attr("stroke", QUIET); })
      .selectAll("text").attr("font-size", 9).attr("fill", QUIET)
      .attr("transform", "rotate(-38)").attr("text-anchor", "end").attr("dx", "-4");
    svg.append("g").attr("transform", "translate(" + ml + ",0)")
      .call(d3.axisLeft(y).ticks(4).tickSize(0).tickPadding(6))
      .call(function (ax) { ax.select(".domain").remove(); })
      .selectAll("text").attr("font-size", 9.5).attr("fill", QUIET);
  }

  /* =========================================================================
     2. Vallejos vs Emmett — the two-level outcome tree
     ========================================================================= */
  if (document.getElementById("chart-tree")) {
    var tw = 660, th = 216;
    var svg2 = svgIn("#chart-tree", tw, th,
      "Two-level outcome tree for Vallejos against Emmett: Vallejos 69.6% split into knockout 26.8, decision 24.7 and submission 18.1; Emmett 30.4%");
    var bx = d3.scaleLinear().domain([0, 100]).range([16, tw - 16]);
    function branchRow(y, items, label, note) {
      var row = svg2.append("g");
      row.append("text").attr("x", 16).attr("y", y - 10).attr("font-size", 10.5)
        .attr("fill", QUIET).attr("letter-spacing", "0.06em").text(label.toUpperCase());
      var acc = 0;
      items.forEach(function (d) {
        var x0 = bx(acc), x1 = bx(acc + d.v); acc += d.v;
        var seg = row.append("g")
          .style("cursor", "default")
          .on("pointerenter", function (event) {
            d3.select(this).select("rect").attr("opacity", 0.82);
            tipShow(event, "<b>" + d.name + "</b><br>" + d.tip);
          })
          .on("pointermove", tipMove)
          .on("pointerleave", function () { d3.select(this).select("rect").attr("opacity", 1); tipHide(); });
        seg.append("rect").attr("x", x0).attr("y", y).attr("height", 34).attr("rx", 3)
          .attr("width", 0).attr("fill", d.fill).attr("stroke", INK).attr("stroke-width", d.stroke || 0)
          .transition().duration(DUR).attr("width", Math.max(0, x1 - x0 - 2));
        if (x1 - x0 > 58) {
          seg.append("text").attr("x", x0 + 8).attr("y", y + 21).attr("font-size", 11)
            .attr("font-weight", 700).attr("fill", d.text || INK)
            .text(d.name + " " + d.v + "%");
        }
      });
      if (note) row.append("text").attr("x", 16).attr("y", y + 52).attr("font-size", 10)
        .attr("fill", QUIET).text(note);
    }
    branchRow(34, [
      { name: "Vallejos", v: 69.6, fill: INK, text: PAPER, tip: "Level one — who wins.<br>Model: Vallejos 69.6%" },
      { name: "Emmett", v: 30.4, fill: SLATE60, tip: "Level one — who wins.<br>Model: Emmett 30.4%" }
    ], "Level 1 · who wins");
    branchRow(122, [
      { name: "KO/TKO", v: 26.8, fill: INK, text: PAPER, tip: "Of Vallejos’s 69.6% — knockout 26.8%.<br>The single heaviest branch of six." },
      { name: "Decision", v: 24.7, fill: SLATE, tip: "Of Vallejos’s 69.6% — decision 24.7%" },
      { name: "Submission", v: 18.1, fill: FILL, tip: "Of Vallejos’s 69.6% — submission 18.1%" },
      { name: "Emmett wins", v: 30.4, fill: SLATE15, stroke: 0, tip: "Emmett’s 30.4%, across his three methods.<br>The report states only Vallejos’s split." }
    ], "Level 2 · how it ends", "Result: Vallejos by KO, round one, 3:33 — the heaviest branch of the six.");
  }

  /* =========================================================================
     3. Two heads compared — AUC with bootstrap intervals
     ========================================================================= */
  if (document.getElementById("chart-heads")) {
    var HEADS = [
      { name: "Winner head", auc: 0.691, lo: 0.614, hi: 0.764, n: "all 175 fights", fill: INK },
      { name: "Method head, stage one", auc: 0.416, lo: 0.330, hi: 0.501, n: "finish or decision · all 175 fights", fill: SLATE },
      { name: "Method head, stage two", auc: 0.580, lo: null, hi: null, n: "KO or submission · 79 finished fights", fill: SLATE60 }
    ];
    var hw = 660, hh = 190, hml = 190, hmr = 30, hmt = 18, hmb = 34;
    var svg3 = svgIn("#chart-heads", hw, hh,
      "AUC by model head: winner 0.691, method stage one 0.416 which is below the 0.5 no-information line, stage two 0.580");
    var hx = d3.scaleLinear().domain([0.25, 0.8]).range([hml, hw - hmr]);
    var hy = d3.scalePoint().domain(HEADS.map(function (d) { return d.name; })).range([hmt + 18, hh - hmb - 10]).padding(0.4);

    svg3.append("line").attr("x1", hx(0.5)).attr("x2", hx(0.5)).attr("y1", hmt).attr("y2", hh - hmb)
      .attr("stroke", QUIET).attr("stroke-width", 1.5).attr("stroke-dasharray", "4 4");
    svg3.append("text").attr("x", hx(0.5)).attr("y", hmt - 4).attr("text-anchor", "middle")
      .attr("font-size", 9.5).attr("fill", QUIET).text("0.50 = no information");

    var hg = svg3.append("g").selectAll("g").data(HEADS).join("g")
      .on("pointerenter", function (event, d) {
        tipShow(event, "<b>" + d.name + "</b><br>AUC " + d.auc.toFixed(3) +
          (d.lo ? " · 95% interval " + d.lo.toFixed(3) + " – " + d.hi.toFixed(3) : " · interval not reported") +
          "<br>" + d.n);
      })
      .on("pointermove", tipMove).on("pointerleave", tipHide);
    hg.filter(function (d) { return d.lo != null; }).append("line")
      .attr("x1", function (d) { return hx(d.lo); }).attr("x2", function (d) { return hx(d.lo); })
      .attr("y1", function (d) { return hy(d.name); }).attr("y2", function (d) { return hy(d.name); })
      .attr("stroke", function (d) { return d.fill; }).attr("stroke-width", 3).attr("stroke-linecap", "round")
      .transition().duration(DUR).attr("x2", function (d) { return hx(d.hi); });
    hg.append("circle")
      .attr("cx", function (d) { return hx(d.auc); }).attr("cy", function (d) { return hy(d.name); })
      .attr("r", 0).attr("fill", function (d) { return d.fill; })
      .attr("stroke", PAPER).attr("stroke-width", 2)
      .transition().duration(DUR).attr("r", 7);
    hg.append("text")
      .attr("x", hml - 12).attr("y", function (d) { return hy(d.name) + 4; })
      .attr("text-anchor", "end").attr("font-size", 11).attr("fill", INK).attr("font-weight", 500)
      .text(function (d) { return d.name; });
    hg.append("text")
      .attr("x", function (d) { return hx(d.auc); }).attr("y", function (d) { return hy(d.name) - 12; })
      .attr("text-anchor", "middle").attr("font-size", 11).attr("font-weight", 700).attr("fill", INK)
      .text(function (d) { return d.auc.toFixed(3); });
    svg3.append("g").attr("transform", "translate(0," + (hh - hmb) + ")")
      .call(d3.axisBottom(hx).ticks(6).tickSize(0).tickPadding(8).tickFormat(d3.format(".2f")))
      .call(function (ax) { ax.select(".domain").attr("stroke", QUIET); })
      .selectAll("text").attr("font-size", 9.5).attr("fill", QUIET);
  }

  /* =========================================================================
     4. Method head against a rule that always says "decision"
     ========================================================================= */
  if (document.getElementById("chart-rule")) {
    var RULE = [
      { metric: "Method called correctly", model: 44.6, rule: 54.9 },
      { metric: "Fighter + method ranked first, all fights", model: 26.9, rule: 34.9 },
      { metric: "Fighter + method ranked first, high conviction", model: 27.3, rule: 41.8 }
    ];
    var rw = 660, rh = 240, rml = 12, rmr = 60, rmt = 8, rowH = 74;
    var svg4 = svgIn("#chart-rule", rw, rh,
      "Method head against an always-decision rule: the rule wins every comparison, 54.9 against 44.6, 34.9 against 26.9, 41.8 against 27.3 per cent");
    var rx = d3.scaleLinear().domain([0, 60]).range([rml, rw - rmr]);
    RULE.forEach(function (d, i) {
      var gy = rmt + i * rowH;
      var grp = svg4.append("g");
      grp.append("text").attr("x", rml).attr("y", gy + 12).attr("font-size", 11)
        .attr("fill", INK).attr("font-weight", 500).text(d.metric);
      [{ k: "Method head", v: d.model, fill: SLATE60, dy: 20 },
       { k: "Always say “decision”", v: d.rule, fill: INK, dy: 40 }].forEach(function (b) {
        var bar = grp.append("g")
          .on("pointerenter", function (event) {
            d3.select(this).select("rect").attr("opacity", 0.82);
            tipShow(event, "<b>" + b.k + "</b><br>" + d.metric + ": " + fmtPct(b.v));
          })
          .on("pointermove", tipMove)
          .on("pointerleave", function () { d3.select(this).select("rect").attr("opacity", 1); tipHide(); });
        bar.append("rect").attr("x", rml).attr("y", gy + b.dy).attr("height", 13).attr("rx", 2)
          .attr("fill", b.fill).attr("width", 0)
          .transition().duration(DUR).attr("width", rx(b.v) - rml);
        bar.append("text").attr("x", rx(b.v) + 6).attr("y", gy + b.dy + 11)
          .attr("font-size", 10.5).attr("font-weight", 700).attr("fill", INK).text(fmtPct(b.v));
      });
    });
    var lg = svg4.append("g").attr("transform", "translate(" + rml + "," + (rh - 8) + ")");
    lg.append("rect").attr("width", 10).attr("height", 10).attr("rx", 2).attr("y", -9).attr("fill", SLATE60);
    lg.append("text").attr("x", 15).attr("font-size", 10).attr("fill", QUIET).text("method head");
    lg.append("rect").attr("x", 108).attr("width", 10).attr("height", 10).attr("rx", 2).attr("y", -9).attr("fill", INK);
    lg.append("text").attr("x", 123).attr("font-size", 10).attr("fill", QUIET).text("always say “decision” — no model at all");
  }

  /* =========================================================================
     5. Submission-danger quartiles — historical against 2026
     ========================================================================= */
  if (document.getElementById("chart-subq")) {
    var SUBQ = [
      { q: "Lowest", hist: 11.6, now: 11.4 },
      { q: "Second", hist: 18.8, now: 11.1 },
      { q: "Third", hist: 18.8, now: 19.0 },
      { q: "Highest", hist: 22.6, now: 9.1 }
    ];
    var sw = 660, sh = 240, sml = 34, smr = 8, smt = 16, smb = 46;
    var svg5 = svgIn("#chart-subq", sw, sh,
      "Submission rate by predicted danger quartile: 2015 to 2025 rises from 11.6 to 22.6 per cent, 2026 collapses to 9.1 per cent in the highest quartile");
    var sx0 = d3.scaleBand().domain(SUBQ.map(function (d) { return d.q; })).range([sml, sw - smr]).paddingInner(0.3).paddingOuter(0.12);
    var sx1 = d3.scaleBand().domain(["hist", "now"]).range([0, sx0.bandwidth()]).padding(0.12);
    var sy = d3.scaleLinear().domain([0, 25]).range([sh - smb, smt]);
    svg5.append("g").selectAll("line").data(sy.ticks(5)).join("line")
      .attr("x1", sml).attr("x2", sw - smr).attr("y1", sy).attr("y2", sy)
      .attr("stroke", SLATE15);
    var sg = svg5.append("g").selectAll("g").data(SUBQ).join("g")
      .attr("transform", function (d) { return "translate(" + sx0(d.q) + ",0)"; });
    [{ key: "hist", label: "2015–2025", fill: SLATE60 }, { key: "now", label: "2026 season", fill: INK }].forEach(function (s) {
      sg.append("rect")
        .attr("x", sx1(s.key)).attr("width", sx1.bandwidth()).attr("rx", 2)
        .attr("fill", s.fill).attr("y", sy(0)).attr("height", 0)
        .on("pointerenter", function (event, d) {
          d3.select(this).attr("opacity", 0.82);
          tipShow(event, "<b>" + d.q + " quartile of predicted danger</b><br>" + s.label + ": " + fmtPct(d[s.key]) + " of fights ended by submission");
        })
        .on("pointermove", tipMove)
        .on("pointerleave", function () { d3.select(this).attr("opacity", 1); tipHide(); })
        .transition().duration(DUR)
        .attr("y", function (d) { return sy(d[s.key]); })
        .attr("height", function (d) { return sy(0) - sy(d[s.key]); });
      sg.append("text")
        .attr("x", sx1(s.key) + sx1.bandwidth() / 2)
        .attr("y", function (d) { return sy(d[s.key]) - 5; })
        .attr("text-anchor", "middle").attr("font-size", 9.5).attr("font-weight", 700).attr("fill", INK)
        .text(function (d) { return d[s.key].toFixed(1); });
    });
    svg5.append("g").attr("transform", "translate(0," + (sh - smb) + ")")
      .call(d3.axisBottom(sx0).tickSize(0).tickPadding(8))
      .call(function (ax) { ax.select(".domain").attr("stroke", QUIET); })
      .selectAll("text").attr("font-size", 10).attr("fill", QUIET);
    svg5.append("g").attr("transform", "translate(" + sml + ",0)")
      .call(d3.axisLeft(sy).ticks(5).tickSize(0).tickPadding(6).tickFormat(function (v) { return v + "%"; }))
      .call(function (ax) { ax.select(".domain").remove(); })
      .selectAll("text").attr("font-size", 9.5).attr("fill", QUIET);
    var l5 = svg5.append("g").attr("transform", "translate(" + sml + "," + (sh - 8) + ")");
    l5.append("rect").attr("width", 10).attr("height", 10).attr("rx", 2).attr("y", -9).attr("fill", SLATE60);
    l5.append("text").attr("x", 15).attr("font-size", 10).attr("fill", QUIET).text("2015–2025");
    l5.append("rect").attr("x", 92).attr("width", 10).attr("height", 10).attr("rx", 2).attr("y", -9).attr("fill", INK);
    l5.append("text").attr("x", 107).attr("font-size", 10).attr("fill", QUIET).text("2026 season");
  }

  /* =========================================================================
     6. Styles and fight length — shift in the share reaching the judges
     ========================================================================= */
  if (document.getElementById("chart-styles")) {
    var STYLES = [
      { s: "Points fighter", shift: 6.4, present: 52.1, absent: 45.7 },
      { s: "Pressure striker", shift: 2.8, present: 51.9, absent: 49.1 },
      { s: "Counter striker", shift: -1.5, present: 49.4, absent: 50.9 },
      { s: "Grappling-first", shift: -1.9, present: 48.8, absent: 50.7 },
      { s: "Power puncher", shift: -3.1, present: 48.4, absent: 51.5 },
      { s: "Muay Thai volume striker", shift: -4.3, present: 47.1, absent: 51.4 }
    ];
    var dw = 660, dh = 230, dml = 170, dmr = 50, dmt = 20, dmb = 30;
    var svg6 = svgIn("#chart-styles", dw, dh,
      "Shift in the share of fights reaching the judges when a style is present: points fighter plus 6.4 points, Muay Thai volume striker minus 4.3");
    var dx = d3.scaleLinear().domain([-6, 8]).range([dml, dw - dmr]);
    var dy = d3.scaleBand().domain(STYLES.map(function (d) { return d.s; })).range([dmt, dh - dmb]).padding(0.32);
    svg6.append("line").attr("x1", dx(0)).attr("x2", dx(0)).attr("y1", dmt - 6).attr("y2", dh - dmb)
      .attr("stroke", QUIET).attr("stroke-width", 1.5);
    var dgg = svg6.append("g").selectAll("g").data(STYLES).join("g")
      .on("pointerenter", function (event, d) {
        d3.select(this).select("rect").attr("opacity", 0.82);
        tipShow(event, "<b>" + d.s + "</b><br>Style present: " + fmtPct(d.present) + " reach the judges<br>Style absent: " + fmtPct(d.absent) +
          "<br>Shift " + (d.shift > 0 ? "+" : "−") + Math.abs(d.shift).toFixed(1) + " points");
      })
      .on("pointermove", tipMove)
      .on("pointerleave", function () { d3.select(this).select("rect").attr("opacity", 1); tipHide(); });
    dgg.append("rect")
      .attr("x", dx(0)).attr("width", 0)
      .attr("y", function (d) { return dy(d.s); }).attr("height", dy.bandwidth()).attr("rx", 2)
      .attr("fill", function (d) { return d.shift > 0 ? INK : SLATE; })
      .transition().duration(DUR)
      .attr("x", function (d) { return Math.min(dx(0), dx(d.shift)); })
      .attr("width", function (d) { return Math.abs(dx(d.shift) - dx(0)); });
    dgg.append("text")
      .attr("x", dml - 10).attr("y", function (d) { return dy(d.s) + dy.bandwidth() / 2 + 4; })
      .attr("text-anchor", "end").attr("font-size", 10.5).attr("fill", INK).attr("font-weight", 500)
      .text(function (d) { return d.s; });
    dgg.append("text")
      .attr("x", function (d) { return d.shift > 0 ? dx(d.shift) + 6 : dx(d.shift) - 6; })
      .attr("y", function (d) { return dy(d.s) + dy.bandwidth() / 2 + 4; })
      .attr("text-anchor", function (d) { return d.shift > 0 ? "start" : "end"; })
      .attr("font-size", 10.5).attr("font-weight", 700).attr("fill", INK)
      .text(function (d) { return (d.shift > 0 ? "+" : "−") + Math.abs(d.shift).toFixed(1); });
    svg6.append("text").attr("x", dx(0)).attr("y", dh - 8).attr("text-anchor", "middle")
      .attr("font-size", 9.5).attr("fill", QUIET).text("← fights end early · fights reach the judges →");
  }

  /* =========================================================================
     7. Feature families — win rate, bottom group against top group
     ========================================================================= */
  if (document.getElementById("chart-families")) {
    var FAM = [
      { f: "Trajectory", lo: 40.3, hi: 60.7, note: "the strongest curve in the feature set" },
      { f: "Striking defence", lo: 43.4, hi: 59.7, note: "clean and close to monotone" },
      { f: "Striker against grappler", lo: 43.6, hi: 57.5, note: "close to monotone throughout" },
      { f: "Cardio (fade risk)", lo: 44.0, hi: 56.0, note: "best two groups against the worst group" },
      { f: "Control time", lo: 46.3, hi: 53.4, note: "weaker than most people expect" },
      { f: "Upset-risk composite", lo: 62.3, hi: 39.3, note: "runs the other way by design — high upset risk, fewer wins" }
    ];
    var fw = 660, fh = 260, fml = 190, fmr = 46, fmt = 24, fmb = 34;
    var svg7 = svgIn("#chart-families", fw, fh,
      "Win rate from the bottom to the top group of each feature family: trajectory spans 40.3 to 60.7 per cent, the widest spread");
    var fx = d3.scaleLinear().domain([35, 65]).range([fml, fw - fmr]);
    var fy = d3.scalePoint().domain(FAM.map(function (d) { return d.f; })).range([fmt + 10, fh - fmb - 10]).padding(0.3);
    svg7.append("line").attr("x1", fx(50)).attr("x2", fx(50)).attr("y1", fmt - 4).attr("y2", fh - fmb)
      .attr("stroke", QUIET).attr("stroke-width", 1).attr("stroke-dasharray", "4 4");
    svg7.append("text").attr("x", fx(50)).attr("y", fmt - 10).attr("text-anchor", "middle")
      .attr("font-size", 9.5).attr("fill", QUIET).text("50%");
    var fg = svg7.append("g").selectAll("g").data(FAM).join("g")
      .on("pointerenter", function (event, d) {
        tipShow(event, "<b>" + d.f + "</b><br>Bottom group " + fmtPct(d.lo) + " → top group " + fmtPct(d.hi) +
          "<br>" + d.note + "<br><span class='tq'>5,522 bouts since 2015, split into five equal groups</span>");
      })
      .on("pointermove", tipMove).on("pointerleave", tipHide);
    fg.append("line")
      .attr("x1", function (d) { return fx(d.lo); }).attr("x2", function (d) { return fx(d.lo); })
      .attr("y1", function (d) { return fy(d.f); }).attr("y2", function (d) { return fy(d.f); })
      .attr("stroke", SLATE60).attr("stroke-width", 3).attr("stroke-linecap", "round")
      .transition().duration(DUR).attr("x2", function (d) { return fx(d.hi); });
    fg.append("circle").attr("cx", function (d) { return fx(d.lo); }).attr("cy", function (d) { return fy(d.f); })
      .attr("r", 5).attr("fill", PAPER).attr("stroke", INK).attr("stroke-width", 2);
    fg.append("circle").attr("cx", function (d) { return fx(d.hi); }).attr("cy", function (d) { return fy(d.f); })
      .attr("r", 0).attr("fill", INK)
      .transition().duration(DUR).attr("r", 6);
    fg.append("text").attr("x", fml - 12).attr("y", function (d) { return fy(d.f) + 4; })
      .attr("text-anchor", "end").attr("font-size", 10.5).attr("fill", INK).attr("font-weight", 500)
      .text(function (d) { return d.f; });
    fg.append("text")
      .attr("x", function (d) { return fx(d.hi) + (d.hi >= d.lo ? 10 : -10); })
      .attr("y", function (d) { return fy(d.f) + 4; })
      .attr("text-anchor", function (d) { return d.hi >= d.lo ? "start" : "end"; })
      .attr("font-size", 10).attr("font-weight", 700).attr("fill", INK)
      .text(function (d) { return d.hi.toFixed(1); });
    svg7.append("g").attr("transform", "translate(0," + (fh - fmb) + ")")
      .call(d3.axisBottom(fx).ticks(6).tickSize(0).tickPadding(8).tickFormat(function (v) { return v + "%"; }))
      .call(function (ax) { ax.select(".domain").attr("stroke", QUIET); })
      .selectAll("text").attr("font-size", 9.5).attr("fill", QUIET);
    var l7 = svg7.append("g").attr("transform", "translate(" + fml + "," + (fh - 6) + ")");
    l7.append("circle").attr("cx", 5).attr("cy", -4).attr("r", 4.5).attr("fill", PAPER).attr("stroke", INK).attr("stroke-width", 2);
    l7.append("text").attr("x", 15).attr("font-size", 10).attr("fill", QUIET).text("bottom group");
    l7.append("circle").attr("cx", 110).attr("cy", -4).attr("r", 5).attr("fill", INK);
    l7.append("text").attr("x", 120).attr("font-size", 10).attr("fill", QUIET).text("top group · win rate for fighter A");
  }

  /* =========================================================================
     8. Knockout threat and the chin flag
     ========================================================================= */
  if (document.getElementById("chart-ko")) {
    var KO = [
      { k: "KO danger differential, top group", v: 57.8, base: 49.4, unit: "A wins", fill: INK },
      { k: "KO danger differential, bottom group", v: 40.9, base: 49.4, unit: "A wins", fill: SLATE },
      { k: "Net KO threat, top group", v: 39.5, base: 31.4, unit: "of fights end by KO", fill: INK },
      { k: "Chin-vulnerable flag raised", v: 44.2, base: 31.4, unit: "of fights end by KO · 274 fights", fill: INK }
    ];
    var kw = 660, kh = 210, kml = 12, kmr = 56, kmt = 6, krow = 50;
    var svg8 = svgIn("#chart-ko", kw, kh,
      "Knockout family signals against their baselines: top-group danger differential lifts A's win rate to 57.8 per cent, the chin flag lifts the knockout rate to 44.2");
    var kx = d3.scaleLinear().domain([0, 62]).range([kml, kw - kmr]);
    KO.forEach(function (d, i) {
      var gy = kmt + i * krow;
      var grp = svg8.append("g")
        .on("pointerenter", function (event) {
          d3.select(this).select(".kbar").attr("opacity", 0.82);
          tipShow(event, "<b>" + d.k + "</b><br>" + fmtPct(d.v) + " " + d.unit + "<br>baseline " + fmtPct(d.base));
        })
        .on("pointermove", tipMove)
        .on("pointerleave", function () { d3.select(this).select(".kbar").attr("opacity", 1); tipHide(); });
      grp.append("text").attr("x", kml).attr("y", gy + 12).attr("font-size", 10.5)
        .attr("fill", INK).attr("font-weight", 500).text(d.k);
      grp.append("rect").attr("class", "kbar").attr("x", kml).attr("y", gy + 19).attr("height", 13).attr("rx", 2)
        .attr("fill", d.fill).attr("width", 0)
        .transition().duration(DUR).attr("width", kx(d.v) - kml);
      grp.append("line")
        .attr("x1", kx(d.base)).attr("x2", kx(d.base)).attr("y1", gy + 15).attr("y2", gy + 36)
        .attr("stroke", QUIET).attr("stroke-width", 2).attr("stroke-dasharray", "3 3");
      grp.append("text").attr("x", kx(d.v) + 6).attr("y", gy + 30)
        .attr("font-size", 10.5).attr("font-weight", 700).attr("fill", INK).text(fmtPct(d.v));
    });
    svg8.append("text").attr("x", kml).attr("y", kh - 4).attr("font-size", 10).attr("fill", QUIET)
      .text("dashed marker = baseline rate for that measure");
  }

  /* =========================================================================
     9. Base submission probability by position
     ========================================================================= */
  if (document.getElementById("chart-positions")) {
    var POS = [
      { p: "Back control", v: 0.38 }, { p: "Mount", v: 0.22 }, { p: "Guard bottom", v: 0.19 },
      { p: "Side control", v: 0.14 }, { p: "Half guard", v: 0.12 }, { p: "Guard top", v: 0.08 },
      { p: "Clinch", v: 0.08 }, { p: "Standing", v: 0.01 }
    ];
    var pw = 660, ph = 250, pml = 120, pmr = 50, pmt = 10, pmb = 8;
    var svg9 = svgIn("#chart-positions", pw, ph,
      "Base submission probability by grappling position, from back control at 0.38 down to standing at 0.01");
    var px = d3.scaleLinear().domain([0, 0.42]).range([pml, pw - pmr]);
    var py = d3.scaleBand().domain(POS.map(function (d) { return d.p; })).range([pmt, ph - pmb]).padding(0.3);
    var pg = svg9.append("g").selectAll("g").data(POS).join("g")
      .on("pointerenter", function (event, d) {
        d3.select(this).select("rect").attr("opacity", 0.82);
        tipShow(event, "<b>" + d.p + "</b><br>Base submission probability " + d.v.toFixed(2) +
          "<br><span class='tq'>derived from historical rates; the entry point of the submission-chain feature</span>");
      })
      .on("pointermove", tipMove)
      .on("pointerleave", function () { d3.select(this).select("rect").attr("opacity", 1); tipHide(); });
    pg.append("rect")
      .attr("x", pml).attr("y", function (d) { return py(d.p); })
      .attr("height", py.bandwidth()).attr("rx", 2)
      .attr("fill", function (d, i) { return i < 3 ? INK : SLATE60; })
      .attr("width", 0)
      .transition().duration(DUR).attr("width", function (d) { return Math.max(2, px(d.v) - pml); });
    pg.append("text").attr("x", pml - 10).attr("y", function (d) { return py(d.p) + py.bandwidth() / 2 + 4; })
      .attr("text-anchor", "end").attr("font-size", 10.5).attr("fill", INK).attr("font-weight", 500)
      .text(function (d) { return d.p; });
    pg.append("text").attr("x", function (d) { return px(d.v) + 6; })
      .attr("y", function (d) { return py(d.p) + py.bandwidth() / 2 + 4; })
      .attr("font-size", 10.5).attr("font-weight", 700).attr("fill", INK)
      .text(function (d) { return d.v.toFixed(2); });
  }

  /* =========================================================================
     10. Stance multipliers by archetype
     ========================================================================= */
  if (document.getElementById("chart-stance")) {
    var STANCE = [
      { s: "Dutch kickboxer", v: 1.40 }, { s: "Muay Thai", v: 1.35 }, { s: "Power puncher", v: 1.30 },
      { s: "Counter striker", v: 1.20 }, { s: "Pressure striker", v: 1.10 }, { s: "Wrestle-striker", v: 0.85 },
      { s: "Decision fighter", v: 0.70 }, { s: "Grappling-first", v: 0.50 }
    ];
    var tw2 = 660, th2 = 250, tml = 130, tmr = 50, tmt = 18, tmb = 8;
    var svgA = svgIn("#chart-stance", tw2, th2,
      "Stance multiplier by archetype: Dutch kickboxer 1.40 down to grappling-first 0.50, around a neutral 1.0");
    var tx = d3.scaleLinear().domain([0, 1.5]).range([tml, tw2 - tmr]);
    var ty = d3.scaleBand().domain(STANCE.map(function (d) { return d.s; })).range([tmt, th2 - tmb]).padding(0.3);
    svgA.append("line").attr("x1", tx(1)).attr("x2", tx(1)).attr("y1", tmt - 6).attr("y2", th2 - tmb)
      .attr("stroke", QUIET).attr("stroke-width", 1).attr("stroke-dasharray", "4 4");
    svgA.append("text").attr("x", tx(1)).attr("y", tmt - 10).attr("text-anchor", "middle")
      .attr("font-size", 9.5).attr("fill", QUIET).text("neutral 1.0");
    var tg = svgA.append("g").selectAll("g").data(STANCE).join("g")
      .on("pointerenter", function (event, d) {
        d3.select(this).select("rect").attr("opacity", 0.82);
        tipShow(event, "<b>" + d.s + "</b><br>Stance multiplier " + d.v.toFixed(2) +
          "<br><span class='tq'>how much the open-stance edge is amplified for this style</span>");
      })
      .on("pointermove", tipMove)
      .on("pointerleave", function () { d3.select(this).select("rect").attr("opacity", 1); tipHide(); });
    tg.append("rect")
      .attr("x", tml).attr("y", function (d) { return ty(d.s); })
      .attr("height", ty.bandwidth()).attr("rx", 2)
      .attr("fill", function (d) { return d.v >= 1 ? INK : SLATE; })
      .attr("width", 0)
      .transition().duration(DUR).attr("width", function (d) { return tx(d.v) - tml; });
    tg.append("text").attr("x", tml - 10).attr("y", function (d) { return ty(d.s) + ty.bandwidth() / 2 + 4; })
      .attr("text-anchor", "end").attr("font-size", 10.5).attr("fill", INK).attr("font-weight", 500)
      .text(function (d) { return d.s; });
    tg.append("text").attr("x", function (d) { return tx(d.v) + 6; })
      .attr("y", function (d) { return ty(d.s) + ty.bandwidth() / 2 + 4; })
      .attr("font-size", 10.5).attr("font-weight", 700).attr("fill", INK)
      .text(function (d) { return d.v.toFixed(2); });
  }

  /* =========================================================================
     11. The art, then and now — four era shifts as paired panels
     ========================================================================= */
  if (document.getElementById("chart-era")) {
    var ERA = [
      { t: "Decisions", unit: "% of fights", then: 48, now: 54.9, max: 60, thenL: "early 2010s", nowL: "2026",
        tip: "Share of fights reaching the judges — up roughly seven points since the early 2010s." },
      { t: "Fight time", unit: "avg minutes", then: 10.8, now: 11.4, max: 15, thenL: "early 2010s", nowL: "2026",
        tip: "Average fight time — up more than half a minute across the same window." },
      { t: "Submissions", unit: "% of fights", then: 18.6, now: 12.6, max: 25, thenL: "2010–2025 avg", nowL: "2026",
        tip: "Submission rate — 12.6% in 2026 is the lowest in sixteen years of data." },
      { t: "Points fighter", unit: "mean archetype score", then: 0.50, now: 0.59, max: 0.7, thenL: "2010", nowL: "2026",
        tip: "Mean points-fighter prevalence — risen almost without interruption for fifteen years." }
    ];
    var ew = 660, eh = 210, panelW = ew / 4;
    var svgB = svgIn("#chart-era", ew, eh,
      "Four era shifts: decisions up from 48 to 54.9 per cent, fight time up from 10.8 to 11.4 minutes, submissions down from 18.6 to 12.6 per cent, points-fighter prevalence up from 0.50 to 0.59");
    ERA.forEach(function (d, i) {
      var gx = i * panelW;
      var ex = d3.scaleBand().domain(["then", "now"]).range([gx + 26, gx + panelW - 22]).padding(0.3);
      var ey = d3.scaleLinear().domain([0, d.max]).range([eh - 48, 34]);
      var grp = svgB.append("g")
        .on("pointerenter", function (event) {
          d3.select(this).selectAll("rect").attr("opacity", 0.82);
          tipShow(event, "<b>" + d.t + "</b><br>" + d.thenL + ": " + d.then + " → " + d.nowL + ": " + d.now + " " + d.unit + "<br>" + d.tip);
        })
        .on("pointermove", tipMove)
        .on("pointerleave", function () { d3.select(this).selectAll("rect").attr("opacity", 1); tipHide(); });
      grp.append("text").attr("x", gx + panelW / 2).attr("y", 16).attr("text-anchor", "middle")
        .attr("font-size", 11).attr("font-weight", 700).attr("fill", INK).text(d.t);
      grp.append("text").attr("x", gx + panelW / 2).attr("y", 28).attr("text-anchor", "middle")
        .attr("font-size", 9).attr("fill", QUIET).text(d.unit);
      [["then", SLATE60, d.thenL], ["now", INK, d.nowL]].forEach(function (s) {
        var key = s[0], fill = s[1], lab = s[2];
        grp.append("rect").attr("x", ex(key)).attr("width", ex.bandwidth()).attr("rx", 2)
          .attr("fill", fill).attr("y", ey(0)).attr("height", 0)
          .transition().duration(DUR)
          .attr("y", ey(d[key])).attr("height", ey(0) - ey(d[key]));
        grp.append("text").attr("x", ex(key) + ex.bandwidth() / 2).attr("y", ey(d[key]) - 5)
          .attr("text-anchor", "middle").attr("font-size", 9.5).attr("font-weight", 700).attr("fill", INK)
          .text(d[key]);
        grp.append("text").attr("x", ex(key) + ex.bandwidth() / 2).attr("y", eh - 32)
          .attr("text-anchor", "middle").attr("font-size", 8.5).attr("fill", QUIET).text(lab);
      });
      if (i) svgB.append("line").attr("x1", gx).attr("x2", gx).attr("y1", 10).attr("y2", eh - 26)
        .attr("stroke", SLATE15);
    });
  }
})();

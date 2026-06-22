/* mastermind.js — renders the static Mastermind dashboard snapshot
   (mastermind/mastermind_snapshot.json, pushed twice daily from the local
   Mastermind server) into a book-tabbed view. RESEARCH / DISPLAY ONLY — paper
   book, never a signal. Bilingual (EN / 中文), re-rendering on 'langchange';
   all values are escaped before insertion (no raw HTML). Degrades to a friendly
   "snapshot pending" state when the JSON is absent/offline. */
(function () {
  var SNAP = null, ACTIVE = null;

  var LBL = {
    en: { nav: "Book value", ret: "Total return", vs: "vs", day: "Day", mdd: "Max drawdown",
          invested: "Invested", cash: "Cash", regime: "Regime", asof: "as of", perf: "Performance",
          alloc: "Allocation", positions: "Positions", decisions: "Recent decisions",
          track: "Track record", trades: "decisions logged", hit: "hit rate", brier: "Brier",
          skill: "skill", status: "status", pending: "pending", hold: "hold",
          colT: "Ticker", colW: "Weight", colS: "Sleeve", colRS: "RS %ile", colSt: "Status",
          equity: "Equity curve", book: "book", bench: "benchmark", building: "building — too few decided to grade",
          empty: "No book has been published yet — the snapshot will appear after the next push.",
          off: "Snapshot pending — the local Mastermind server hasn't pushed yet, or you're offline.",
          leadership: "Leadership", conviction: "Conviction", none: "—" },
    zh: { nav: "账本市值", ret: "总回报", vs: "对比", day: "当日", mdd: "最大回撤",
          invested: "已投资", cash: "现金", regime: "市场格局", asof: "截至", perf: "业绩",
          alloc: "仓位分配", positions: "持仓", decisions: "近期决策",
          track: "战绩", trades: "条决策记录", hit: "胜率", brier: "Brier", skill: "技巧",
          status: "状态", pending: "待成交", hold: "持有",
          colT: "代码", colW: "权重", colS: "沟槽", colRS: "RS 百分位", colSt: "状态",
          equity: "净值曲线", book: "账本", bench: "基准", building: "构建中 — 已决策样本过少",
          empty: "尚未发布账本 — 快照将在下次推送后出现。",
          off: "快照待推送 — 本地 Mastermind 服务器尚未推送，或你处于离线状态。",
          leadership: "领涨", conviction: "信念", none: "—" }
  };

  function esc(s) { var d = document.createElement("div"); d.textContent = (s == null ? "" : String(s)); return d.innerHTML; }
  function curLang() { return document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"; }
  function tt() { return LBL[curLang()]; }

  function pct(x, dp) {
    if (x == null || isNaN(x)) return "—";
    return (x).toFixed(dp == null ? 2 : dp) + "%";
  }
  function signed(x) {
    if (x == null || isNaN(x)) return { txt: "—", cls: "" };
    var v = Number(x);
    return { txt: (v > 0 ? "+" : "") + v.toFixed(2) + "%", cls: v > 0 ? "up" : (v < 0 ? "down" : "") };
  }
  function money(x) {
    if (x == null || isNaN(x)) return "—";
    return "$" + Math.round(Number(x)).toLocaleString("en-US");
  }
  function span(cls, txt) { return '<span class="' + cls + '">' + esc(txt) + "</span>"; }

  // ---- sparkline (nav vs benchmark) -------------------------------------
  function sparkline(series, benchSym) {
    if (!series || series.length < 2) return "";
    var W = 640, H = 90, P = 4;
    var navs = [], bens = [];
    for (var i = 0; i < series.length; i++) {
      var n = Number(series[i].nav); if (!isNaN(n)) navs.push(n);
      var b = Number(series[i].spy_nav); if (!isNaN(b)) bens.push(b);
    }
    var all = navs.concat(bens), lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    if (!(hi > lo)) hi = lo + 1;
    function pathFor(arr) {
      var pts = [];
      for (var k = 0; k < arr.length; k++) {
        var x = P + (W - 2 * P) * (k / (arr.length - 1));
        var y = P + (H - 2 * P) * (1 - (arr[k] - lo) / (hi - lo));
        pts.push(x.toFixed(1) + "," + y.toFixed(1));
      }
      return pts.join(" ");
    }
    var s = '<svg class="spark" viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H +
            '" preserveAspectRatio="none" role="img">';
    if (bens.length > 1)
      s += '<polyline points="' + pathFor(bens) + '" fill="none" stroke="var(--muted)" stroke-width="1.4" stroke-dasharray="4 3" opacity="0.8"/>';
    if (navs.length > 1)
      s += '<polyline points="' + pathFor(navs) + '" fill="none" stroke="var(--link)" stroke-width="2"/>';
    s += "</svg>";
    var L = tt();
    s += '<div class="spark-leg"><span style="color:var(--link)">▬ ' + esc(L.book) +
         '</span> &nbsp; <span style="color:var(--muted)">┄ ' + esc(benchSym || L.bench) + "</span></div>";
    return '<div class="sparkwrap">' + s + "</div>";
  }

  // ---- sub-panels --------------------------------------------------------
  function perfPanel(b) {
    var L = tt(), p = b.performance || {};
    var ret = signed(p.total_return_pct), vs = signed(p.vs_spy_pct), day = signed(p.day_change_pct);
    var stat = function (k, vhtml) { return '<div class="mm-stat"><div class="k">' + esc(k) + '</div><div class="v">' + vhtml + "</div></div>"; };
    var grid = '<div class="mm-stats">' +
      stat(L.nav, esc(money(p.current_nav))) +
      stat(L.ret, span(ret.cls, ret.txt)) +
      stat(L.vs + " " + (b.benchmark || "SPY"), span(vs.cls, vs.txt)) +
      stat(L.day, span(day.cls, day.txt)) +
      stat(L.mdd, esc(p.max_drawdown_pct != null ? "-" + Math.abs(p.max_drawdown_pct).toFixed(2) + "%" : "—")) +
      "</div>";
    var sub = '<div class="muted sm" style="margin:8px 0 10px">' +
      (b.as_of ? esc(L.asof + " " + b.as_of) : "") +
      (b.market_status ? " · " + esc(b.market_status) : "") +
      (b.regime && b.regime.quad_name ? " · " + esc(L.regime + ": " + b.regime.quad_name +
        (b.regime.liquidity_overlay ? " / " + b.regime.liquidity_overlay : "")) : "") + "</div>";
    return '<div class="panel"><h2>📈 ' + esc(L.perf) + ' — ' + esc(b.name || b.id) + "</h2>" +
      grid + sub + sparkline(p.series, b.benchmark) + "</div>";
  }

  var SLEEVE_COLORS = { leadership: "var(--link)", conviction: "var(--up)", cash: "var(--muted)" };
  function allocPanel(b) {
    var L = tt(), sl = b.sleeves || {};
    var keys = Object.keys(sl);
    if (!keys.length) return "";
    var bar = '<div class="mm-bar">', leg = '<div class="mm-legend">';
    keys.forEach(function (k) {
      var w = Number(sl[k]) || 0, col = SLEEVE_COLORS[k] || "var(--card)";
      var label = L[k] || (k.charAt(0).toUpperCase() + k.slice(1));
      bar += '<span style="width:' + (w * 100).toFixed(2) + "%;background:" + col + '"></span>';
      leg += '<span><i style="background:' + col + '"></i>' + esc(label) + " " + pct(w * 100, 1) + "</span>";
    });
    bar += "</div>"; leg += "</div>";
    return '<div class="panel"><h2>🧮 ' + esc(L.alloc) + "</h2>" + bar + leg + "</div>";
  }

  function positionsPanel(b) {
    var L = tt(), pos = b.positions || [];
    if (!pos.length) return "";
    var rows = pos.map(function (p) {
      var st = p.pending ? '<span class="pill pend">' + esc(L.pending) + "</span>"
        : (p.verdict ? '<span class="pill ' + (p.verdict === "hold" ? "hold" : "") + '">' + esc(p.verdict) + "</span>" : "");
      return "<tr><td>" + esc(p.ticker || "") + '</td><td class="num">' + pct((Number(p.weight) || 0) * 100, 1) +
        "</td><td>" + esc(p.sleeve || "—") + '</td><td class="num">' +
        (p.rs_pctile != null ? esc(Number(p.rs_pctile).toFixed(0)) : "—") + "</td><td>" + st + "</td></tr>";
    }).join("");
    return '<div class="panel"><h2>📊 ' + esc(L.positions) + " (" + pos.length + ')</h2>' +
      '<table class="mm"><thead><tr><th>' + esc(L.colT) + '</th><th class="num">' + esc(L.colW) +
      '</th><th>' + esc(L.colS) + '</th><th class="num">' + esc(L.colRS) + '</th><th>' + esc(L.colSt) +
      "</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  function decisionsPanel(b) {
    var L = tt(), dec = (b.decisions || []).slice(0, 12);
    if (!dec.length) return "";
    var items = dec.map(function (d) {
      var conv = [d.lean, d.conviction].filter(Boolean).join(" · ");
      var prob = d.prob_correct != null ? " · p=" + Number(d.prob_correct).toFixed(2) : "";
      var hz = d.horizon_d != null ? " · " + d.horizon_d + "d" : "";
      return '<div class="mm-dec"><div class="h">' + esc(d.subject || d.id || "") +
        ' <span class="muted sm">' + esc(conv + prob + hz) + "</span></div>" +
        (d.thesis ? '<div class="muted sm">' + esc(d.thesis) + "</div>" : "") + "</div>";
    }).join("");
    return '<div class="panel"><h2>🧠 ' + esc(L.decisions) + "</h2>" + items + "</div>";
  }

  function trackPanel(b) {
    var L = tt(), tr = b.track_record || {};
    var parts = [esc((tr.n != null ? tr.n : 0) + " " + L.trades)];
    if (tr.hit_rate != null) parts.push(esc(L.hit + " " + (Number(tr.hit_rate) * 100).toFixed(0) + "%"));
    if (tr.brier != null) parts.push(esc(L.brier + " " + Number(tr.brier).toFixed(3)));
    if (tr.skill != null) parts.push(esc(L.skill + " " + Number(tr.skill).toFixed(3)));
    var statusTxt = (tr.status === "building" || tr.n === 0) ? L.building : (tr.status || "");
    return '<div class="panel"><h2>🎯 ' + esc(L.track) + '</h2><div class="sm">' + parts.join(" · ") +
      (statusTxt ? ' · <span class="muted">' + esc(statusTxt) + "</span>" : "") + "</div></div>";
  }

  function renderTabs() {
    var wrap = document.getElementById("mm-tabs");
    if (!wrap || !SNAP || !SNAP.books) return;
    wrap.innerHTML = SNAP.books.map(function (b) {
      return '<button class="mm-tab-btn' + (b.id === ACTIVE ? " active" : "") + '" data-book="' + esc(b.id) +
        '" role="tab">' + esc(b.name || b.id) +
        (b.tagline ? '<span class="tl">' + esc(b.tagline) + "</span>" : "") + "</button>";
    }).join("");
    var btns = wrap.querySelectorAll(".mm-tab-btn");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function () { ACTIVE = this.getAttribute("data-book"); render(); });
    }
  }

  function render() {
    var root = document.getElementById("mm-root");
    if (!root) return;
    if (!SNAP || !SNAP.books || !SNAP.books.length) {
      root.innerHTML = '<div class="panel mm-empty">' + esc(SNAP ? tt().empty : tt().off) + "</div>";
      return;
    }
    if (!ACTIVE || !SNAP.books.some(function (b) { return b.id === ACTIVE; }))
      ACTIVE = SNAP.default_book || SNAP.books[0].id;
    renderTabs();
    var book = SNAP.books.filter(function (b) { return b.id === ACTIVE; })[0];
    root.innerHTML = perfPanel(book) + allocPanel(book) + positionsPanel(book) +
      decisionsPanel(book) + trackPanel(book);
    // localize the live-dashboard URL from the snapshot, if present
    var live = document.getElementById("mm-live");
    if (live && SNAP.live_url) live.setAttribute("href", SNAP.live_url);
  }

  fetch("mastermind/mastermind_snapshot.json?_=" + Date.now())
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { SNAP = j; render(); })
    .catch(function () { SNAP = null; render(); });
  document.addEventListener("langchange", render);
})();

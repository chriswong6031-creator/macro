/* gex.js — the interactive Options Desk (templates/gex.html.j2 + build_gex_board.py).
   Reads the embedded manifest (window.GEX_MANIFEST) for the at-a-glance board + search,
   and fetches gex/<KEY>.json on demand to render the rich per-symbol views: the
   dealer-gamma WALLS bar chart, the net-gamma PROFILE curve, the strike×expiry
   HEATMAP, the vol SMILE and IV TERM structure, expected move + key levels.

   Pure, dependency-free, theme-/language-aware: SVG/HTML is regenerated on
   themechange / langchange so colours flip with the site convention (read live from
   CSS custom properties). DISPLAY ONLY — see the page footer + LIMITATIONS.md. */
(function () {
  "use strict";
  var M = window.GEX_MANIFEST || [];
  var BYKEY = {}; M.forEach(function (m) { BYKEY[m.key] = m; });
  var cache = {};               // key -> fetched payload (or null on miss)
  var cur = null;               // current model
  var curKey = null;
  var heatMode = "gex";         // gex | oi | vol
  var barMode = "gamma";        // gamma | oi | vol
  var boardSort = { key: "net_gex_bn", dir: -1 };
  var grpFilter = "__all";

  // ---- small helpers -------------------------------------------------------
  function lang() { return document.documentElement.getAttribute("data-lang") || "en"; }
  function lz(en, zh) { return lang() === "zh" && zh ? zh : (en || ""); }
  function cssv(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function hexToRgb(h) {
    h = (h || "").replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return isNaN(n) ? [136, 136, 136] : [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgba(name, a) { var c = hexToRgb(cssv(name)); return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + a + ")"; }
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstElementChild; }

  function price(v) { return (v === null || v === undefined) ? "—" : (+(+v).toFixed(2)).toString(); }
  function sgn(v, d) { if (v === null || v === undefined) return "—"; d = d == null ? 1 : d; return (v >= 0 ? "+" : "") + (+v).toFixed(d); }
  function pct(v, d) { if (v === null || v === undefined) return "—"; d = d == null ? 2 : d; return (v >= 0 ? "+" : "") + (+v).toFixed(d) + "%"; }
  function pctU(v, d) { if (v === null || v === undefined) return "—"; d = d == null ? 1 : d; return (+v).toFixed(d) + "%"; }
  function compact(v) {
    if (v === null || v === undefined) return "—";
    var a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(1) + "B";
    if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(1) + "k";
    return "" + Math.round(v);
  }
  function regWord(r) {
    if (r === "long") return lz("🛡️ Calm", "🛡️ 平静");
    if (r === "short") return lz("⚡ Jumpy", "⚡ 跳动");
    return lz("⚖️ Mixed", "⚖️ 中性");
  }
  function regClass(r) { return "reg-" + (r === "long" ? "long" : r === "short" ? "short" : "na"); }

  // ---- floating tooltip ----------------------------------------------------
  var tip = document.getElementById("gx-tip");
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.style.display = "block";
    var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 12)) + "px";
    tip.style.top = Math.max(8, y - h - 10) + "px";
  }
  function hideTip() { tip.style.display = "none"; }

  // ---- wrapping help popover (board-column "?" — escapes the table's overflow) ----
  var htip = document.getElementById("gx-htip");
  function showHelp(html, x, y) {
    htip.innerHTML = html; htip.style.display = "block";
    var w = htip.offsetWidth, h = htip.offsetHeight;
    htip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 12)) + "px";
    htip.style.top = Math.min(window.innerHeight - h - 8, Math.max(8, y + 16)) + "px";
  }
  function hideHelp() { if (htip) htip.style.display = "none"; }

  // Plain-English explainers for each board column (bilingual; read live so they
  // always match the current language). Keyed by the th's data-h attribute.
  var BOARD_HELP = {
    regime: {
      t_en: "Regime — calm or jumpy", t_zh: "体制 — 平静或跳动",
      en: "Are dealers calming the market or making it jumpy today? “Calm” means their hedging pushes back against moves, so price tends to stick in a range. “Jumpy” means their hedging adds to moves, so swings run bigger. This is about volatility, not direction — and it's the single most important read on the row.",
      zh: "今天做市商是在让市场平静还是跳动？“平静”指对冲逆势而行，价格倾向停在区间；“跳动”指对冲顺势而行，波动更大。这关乎波动而非方向 — 也是整行最重要的读数。" },
    volhole: {
      t_en: "Vol hole — trapped vs. free", t_zh: "波动洞 — 被困或自由",
      en: "A quick label for how trapped vs. free the price is to move. “In hole” = parked calmly between a floor and a ceiling. “Coiled” = pressed against one of those walls, where a daily close through it could release a bigger move. “Expansion” = already in the jumpy state, with no calming band.",
      zh: "快速标示价格被困还是可自由波动。“洞内”=平静地停在下沿与上沿之间；“蓄势”=贴住其中一面墙，日线收盘越过可能释放更大走势；“扩张”=已处于跳动状态、没有压制带。" },
    netgex: {
      t_en: "Net GEX — the volatility regime", t_zh: "净GEX — 波动体制",
      en: "One number for today's volatility regime, not direction. Positive (green) = dealer hedging tends to calm the market (pinning, smaller moves). Negative (red) = it tends to amplify moves (trending, bigger moves). Measured in billions of dollars of hedging per 1% move; bigger size means a stronger effect, but don't compare the raw number across different stocks.",
      zh: "用一个数表示今日的波动体制，而非方向。正（绿）=对冲倾向让市场平静（磁吸、波动更小）；负（红）=倾向放大走势（趋势、波动更大）。单位为每1%波动对应的十亿美元对冲；数值越大效果越强，但不同股票之间不可直接比较原始数值。" },
    flip: {
      t_en: "Flip — distance to the regime line", t_zh: "翻转 — 距体制分界的距离",
      en: "How far today's price is from the “flip” — the line between the calm and jumpy regimes. Positive = price is above the line, in the calmer zone with room before it switches. Negative = below the line, already in the jumpier zone. The closer to 0%, the closer the market is to switching modes. It's a regime boundary, not a price target.",
      zh: "今日价格距“翻转”有多远 — 翻转是平静与跳动体制的分界。正=价格在线之上、处于较平静区且距切换尚有空间；负=在线之下、已处于较跳动区。越接近0%，越接近切换模式。它是体制边界，而非目标价。" },
    iv30: {
      t_en: "IV30 — implied volatility", t_zh: "IV30 — 隐含波动率",
      en: "The 30-day expected volatility priced into options, annualized. Higher = options are pricing bigger swings (fear or a known event); lower = a calmer, cheaper market. It's the market's forward expectation of how much price could move, not how much it already moved and not which direction.",
      zh: "期权定价隐含的30天预期波动率（年化）。越高=期权在为更大的波动定价（恐慌或已知事件）；越低=更平静、更便宜的市场。这是市场对未来可能波动幅度的预期，而非已发生的波动、也不含方向。" },
    expmove: {
      t_en: "Exp. move — typical daily move", t_zh: "预期波动 — 典型单日波动",
      en: "The size of a typical one-day move options are pricing in, as a percent of today's price. A 1.0% reading means a daily move of roughly ±1% is “normal” — price stays inside it about 2 days out of 3, and breaks out the other 1 in 3. It's a symmetric range, not a forecast of up or down and not a cap.",
      zh: "期权定价的典型单日波动幅度，以今日价格的百分比表示。读数1.0%意味着约±1%的单日波动属“正常” — 约三分之二的交易日落在其内，另有三分之一突破。这是对称区间，既非涨跌预测、也非上限。" },
    pc: {
      t_en: "P/C — put/call ratio", t_zh: "P/C — 认沽/认购比",
      en: "Put-to-call ratio — how many put contracts are outstanding versus calls. Above 1.0 = more puts; below 1.0 = more calls. Often contrarian, not directional: heavy puts are frequently hedges, not bearish bets, and open interest can't tell who's long or short. Weak, noisy context only — never a signal.",
      zh: "认沽/认购比 — 未平仓的看跌合约相对看涨合约的数量。大于1.0=看跌更多；小于1.0=看涨更多。常具反向意味、非方向性：大量看跌往往是对冲而非看空，且未平仓量无法分辨多空。仅作弱而嘈杂的背景 — 绝非信号。" }
  };

  function setupBoardHelp() {
    document.querySelectorAll("#gx-board th .bhelp").forEach(function (b) {
      var k = b.getAttribute("data-h");
      function shw(e) {
        var d = BOARD_HELP[k]; if (!d) return;
        var r = b.getBoundingClientRect();
        var x = e && e.clientX ? e.clientX : r.left;
        var y = e && e.clientY ? e.clientY : r.bottom - 8;
        showHelp("<b>" + esc(lz(d.t_en, d.t_zh)) + "</b><br>" + esc(lz(d.en, d.zh)), x, y);
      }
      b.addEventListener("mouseenter", shw);
      b.addEventListener("mousemove", shw);
      b.addEventListener("mouseleave", hideHelp);
      b.addEventListener("click", function (e) { e.stopPropagation(); });   // don't trigger column sort
      b.addEventListener("focus", function () { shw(null); });
      b.addEventListener("blur", hideHelp);
    });
  }

  // ========================================================================
  // BOARD (at-a-glance table from the manifest)
  // ========================================================================
  function renderBoard() {
    var tb = document.querySelector("#gx-board tbody");
    if (!tb) return;
    var rows = M.filter(function (m) { return grpFilter === "__all" || m.grp === grpFilter; });
    rows.sort(function (a, b) {
      var k = boardSort.key, va = a[k], vb = b[k];
      if (k === "key" || k === "regime") { va = "" + (va || ""); vb = "" + (vb || ""); return va < vb ? -boardSort.dir : va > vb ? boardSort.dir : 0; }
      va = va == null ? -1e18 : va; vb = vb == null ? -1e18 : vb;
      return (va - vb) * boardSort.dir;
    });
    // group section headers preserved only when sorting by symbol or when "all"
    var html = "", lastGrp = null, grouped = (boardSort.key === "key");
    rows.forEach(function (m) {
      if (grouped && m.grp !== lastGrp) { html += '<tr class="ghead"><td colspan="9">' + esc(lz(m.grp, m.grp)) + "</td></tr>"; lastGrp = m.grp; }
      html += '<tr class="sym' + (m.key === curKey ? " sel" : "") + '" data-key="' + m.key + '">' +
        '<td><span class="symk">' + esc(m.key) + '</span><span class="symn">' + esc(lz(m.en, m.zh)) + "</span></td>" +
        "<td>" + price(m.spot) + "</td>" +
        '<td><span class="reg ' + regClass(m.regime) + '">' + regWord(m.regime) + "</span></td>" +
        vhCell(m) +
        '<td class="' + (m.net_gex_bn >= 0 ? "pos" : "neg") + '">' + sgn(m.net_gex_bn, 1) + "</td>" +
        '<td class="' + (m.dist_to_flip_pct >= 0 ? "pos" : "neg") + '">' + pct(m.dist_to_flip_pct, 1) + "</td>" +
        "<td>" + pctU(m.iv30, 1) + "</td>" +
        "<td>" + pctU(m.daily_move_pct, 2) + "</td>" +
        "<td>" + (m.put_call_oi_ratio == null ? "—" : (+m.put_call_oi_ratio).toFixed(2)) + "</td>" +
        "</tr>";
    });
    tb.innerHTML = html;
    tb.querySelectorAll("tr.sym").forEach(function (tr) {
      tr.addEventListener("click", function () { selectSymbol(tr.getAttribute("data-key")); });
    });
    document.querySelectorAll("#gx-board th[data-sort]").forEach(function (th) {
      th.onclick = function () {
        var k = th.getAttribute("data-sort");
        if (boardSort.key === k) boardSort.dir *= -1; else { boardSort.key = k; boardSort.dir = (k === "key") ? 1 : -1; }
        renderBoard();
      };
    });
  }

  // ========================================================================
  // SEARCH (look up any prebuilt ticker)
  // ========================================================================
  function setupSearch() {
    var inp = document.getElementById("gx-q"), sg = document.getElementById("gx-sugg");
    if (!inp) return;
    var hl = -1, shown = [];
    function close() { sg.classList.remove("on"); hl = -1; }
    function render(q) {
      q = q.trim().toUpperCase();
      shown = M.filter(function (m) {
        return !q || m.key.indexOf(q) === 0 || m.key.indexOf(q) >= 0 || (m.en || "").toUpperCase().indexOf(q) >= 0;
      }).slice(0, 12);
      if (!shown.length) { close(); return; }
      sg.innerHTML = shown.map(function (m, i) {
        return '<div class="row' + (i === hl ? " hl" : "") + '" data-key="' + m.key + '">' +
          "<span><b>" + esc(m.key) + "</b> <span class=\"g\">" + esc(lz(m.en, m.zh)) + "</span></span>" +
          '<span class="g">' + regWord(m.regime) + " · " + sgn(m.net_gex_bn, 1) + "bn</span></div>";
      }).join("");
      sg.classList.add("on");
      sg.querySelectorAll(".row").forEach(function (r) {
        r.addEventListener("mousedown", function (e) { e.preventDefault(); selectSymbol(r.getAttribute("data-key")); inp.value = ""; close(); });
      });
    }
    inp.addEventListener("input", function () { hl = -1; render(inp.value); });
    inp.addEventListener("focus", function () { render(inp.value); });
    inp.addEventListener("blur", function () { setTimeout(close, 150); });
    inp.addEventListener("keydown", function (e) {
      if (!sg.classList.contains("on")) return;
      if (e.key === "ArrowDown") { hl = Math.min(shown.length - 1, hl + 1); render(inp.value); e.preventDefault(); }
      else if (e.key === "ArrowUp") { hl = Math.max(0, hl - 1); render(inp.value); e.preventDefault(); }
      else if (e.key === "Enter") { var pick = shown[hl < 0 ? 0 : hl]; if (pick) { selectSymbol(pick.key); inp.value = ""; close(); } }
      else if (e.key === "Escape") { close(); }
    });
  }

  function setupChips() {
    document.querySelectorAll("#gx-chips .chip").forEach(function (c) {
      c.addEventListener("click", function () {
        document.querySelectorAll("#gx-chips .chip").forEach(function (x) { x.classList.remove("on"); });
        c.classList.add("on"); grpFilter = c.getAttribute("data-grp"); renderBoard();
      });
    });
    var bt = document.getElementById("gx-board-toggle"), sc = document.getElementById("gx-board-scroll");
    if (bt) bt.addEventListener("click", function () {
      var hidden = sc.style.display === "none";
      sc.style.display = hidden ? "" : "none";
      bt.textContent = hidden ? lz("hide", "隐藏") : lz("show", "显示");
    });
  }

  // ========================================================================
  // LOAD + DETAIL
  // ========================================================================
  function selectSymbol(key) {
    if (!key) return;
    curKey = key;
    renderBoard();
    var box = document.getElementById("gx-detail");
    if (cache[key]) { cur = cache[key]; renderDetail(); return; }
    box.innerHTML = '<div class="gx-loading">' + lz("Loading " + key + "…", "加载 " + key + "…") + "</div>";
    fetch("gex/" + encodeURIComponent(key) + ".json").then(function (r) {
      if (!r.ok) throw new Error("absent"); return r.json();
    }).then(function (j) { cache[key] = j; if (curKey === key) { cur = j; renderDetail(); } })
      .catch(function () {
        cache[key] = null;
        if (curKey === key) box.innerHTML = '<div class="panel gx-loading">' + lz("No options data for " + key + ".", key + " 暂无期权数据。") + "</div>";
      });
  }

  function renderDetail() {
    if (!cur) return;
    var s = cur.summary, em = cur.expected_move, meta = cur.meta || {};
    var box = document.getElementById("gx-detail");
    var flipTxt = s.gamma_flip == null ? "—" : price(s.gamma_flip) + " (" + pct(s.dist_to_flip_pct, 1) + ")";
    var frontMove = em.front ? ("±" + price(em.front.abs) + " / " + pctU(em.front.pct, 1) + " <span class='muted xs'>(" + esc(em.front.expiry) + ")</span>") : "—";

    var hero =
      '<div class="panel"><div class="hero">' +
        '<span><span class="sym">' + esc(meta.key || curKey) + '</span> <span class="nm">' + esc(lz(meta.en, meta.zh)) + "</span></span>" +
        '<span class="regbadge ' + regClass(s.regime) + '">' +
          (s.regime === "long" ? lz("🛡️ Calm regime · dealers fade moves, price tends to pin", "🛡️ 平静体制 · 做市商抑制走势，价格倾向被磁吸")
            : s.regime === "short" ? lz("⚡ Jumpy regime · dealers chase moves, price tends to trend", "⚡ 跳动体制 · 做市商追逐走势，价格倾向趋势化")
            : lz("⚖️ Mixed regime · no clear dealer lean", "⚖️ 中性体制 · 做市商无明显倾向")) + "</span>" +
        '<span class="heronum big"><span class="muted sm">' + lz("Spot", "现价") + "</span> <b>" + price(s.spot) + "</b></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Net GEX", "净GEX") + '</span> <b class="' + (s.net_gex_bn >= 0 ? "pos" : "neg") + '">' + sgn(s.net_gex_bn, 1) + " $bn</b></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Gamma flip", "Gamma翻转") + "</span> <b>" + flipTxt + "</b></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Exp. daily move", "预期单日波动") + '</span> <b>±' + pctU(em.daily_pct, 2) + "</b> <span class='muted sm'>±" + price(em.daily_abs) + "</span></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Front-expiry move", "近月预期波动") + "</span> <b>" + frontMove + "</b></span>" +
        '<span id="gx-spark"></span>' +
      "</div>" + gamePlanHTML() + rulerHTML() + "</div>";

    var charts =
      '<div class="grid2">' +
        '<div class="panel"><div class="topline" style="justify-content:space-between"><h2>' + lz("Dealer gamma by strike — the walls", "按行权价的做市商Gamma — 墙") +
          help(lz("Net dealer GEX summed at each strike (across expiries). Green = call-heavy resistance above; red = put-heavy support below. The call wall caps rallies; the put wall cushions selloffs under long gamma. Toggle to see raw open interest / volume by strike.",
                  "每个行权价上的做市商净GEX之和（跨到期）。绿=上方看涨阻力；红=下方看跌支撑。多头Gamma下，看涨墙压制上涨、看跌墙缓冲下跌。可切换查看按行权价的未平仓量/成交量。")) +
          "</h2><div class='hm-tabs' id='gx-bartabs'>" + barTabs() + "</div></div>" +
          '<div class="chartbox" id="gx-bars"></div>' + barLegend() + "</div>" +
        '<div class="panel"><h2>' + lz("Net-gamma profile — where the flip is", "净Gamma曲线 — 翻转所在") +
          help(lz("Dealer $gamma re-evaluated as spot moves across the grid. Where the curve crosses zero is the gamma flip: above it dealers are long gamma (dampen); below it short gamma (amplify). Steeper negative = faster vol on the way down.",
                  "随现价在网格上移动重估的做市商$Gamma。曲线穿越零点处即Gamma翻转：之上做市商多头Gamma（抑制），之下空头Gamma（放大）。负值越陡，下跌时波动放大越快。")) + "</h2>" +
          '<div class="chartbox" id="gx-profile"></div></div>' +
      "</div>";

    var heat =
      '<div class="panel"><div class="topline" style="justify-content:space-between"><h2>' + lz("Heatmap — strike × expiry", "热力图 — 行权价 × 到期") +
        help(lz("The options surface. Rows = strikes (spot row outlined), columns = expiries. Toggle: net dealer gamma (green call / red put), open interest, or volume. Bright clusters are where positioning — and dealer hedging — concentrate.",
                "期权曲面。行=行权价（现价行加框），列=到期。可切换：做市商净Gamma（绿看涨/红看跌）、未平仓量、成交量。亮区即仓位与做市商对冲集中之处。")) +
        '</h2><div class="hm-tabs" id="gx-heattabs">' + heatTabs() + "</div></div>" +
        '<div class="hm-scroll" id="gx-heat"></div>' + heatLegend() + "</div>";

    var vol =
      '<div class="grid2">' +
        '<div class="panel"><h2>' + lz("Volatility smile / skew", "波动率微笑/偏斜") +
          help(lz("Implied vol by strike for the front liquid expiry. A steep left side (puts richer than calls) is downside skew — the market paying up for crash protection.",
                  "近月主力到期按行权价的隐含波动。左侧更陡（看跌比看涨更贵）即下行偏斜 — 市场为下跌保护付溢价。")) + "</h2>" +
          '<div class="chartbox" id="gx-smile"></div></div>' +
        '<div class="panel"><h2>' + lz("IV term structure", "隐含波动期限结构") +
          help(lz("ATM implied vol by expiry. Upward-sloping (contango) is the calm default; an inverted (backwardated) curve — near dates above far — flags an event or stress priced in.",
                  "按到期的平值隐含波动。向上倾斜（contango）为平静常态；倒挂（近高远低）预示已计入的事件或压力。")) + "</h2>" +
          '<div class="chartbox" id="gx-term"></div></div>' +
      "</div>";

    var termTbl = termTableHTML();
    var cards = cardsHTML();

    box.innerHTML = hero + volHoleHTML() + charts + heat + vol + termTbl + cards + caveatHTML();
    // draw the SVG/HTML views
    drawBars(); drawProfile(); drawHeat(); drawSmile(); drawTerm(); drawSpark();
    wireBarTabs(); wireHeatTabs();
  }

  function help(txt) {
    return '<span class="help">?<span class="tip">' + esc(txt) + "</span></span>";
  }

  // ---- the Game Plan (beginner-readable signal card; replaces the old read line) ----
  // A plain-English verdict (calm vs jumpy) + the levels to watch with explicit
  // daily-close triggers + today's expected range. Display-only: a levels/regime
  // playbook, never a buy/sell score. Drives off summary + vol_hole + expected_move.
  function gamePlanHTML() {
    var s = cur.summary, em = cur.expected_move || {}, vh = cur.vol_hole || {}, meta = cur.meta || {};
    if (!s) return "";
    var regime = s.regime, st = vh.state;

    // verdict: regime (short→jumpy, neutral→mixed) then long crossed with vol-hole state
    var V;
    if (regime === "short") {
      V = { cls: "gp-jumpy", icon: "🌪", h_en: "Amplified & jumpy", h_zh: "放大 · 跳动",
        s_en: "Moves tend to feed on themselves — expect bigger swings and air-pockets, and don't count on dips getting bought back the way they do in calm tape.",
        s_zh: "走势倾向自我强化 — 预期更大的波动与急跌，且别指望像平静行情那样回调会自动被买回。" };
    } else if (regime === "neutral") {
      V = { cls: "gp-neutral", icon: "⚖️", h_en: "No strong pull", h_zh: "无明显牵引",
        s_en: "Dealer hedging isn't leaning either way today, so the levels below matter less than usual — trade the chart, not the gamma.",
        s_zh: "今日做市商对冲无明显倾向，下方价位的作用弱于平常 — 看图表，而非Gamma。" };
    } else if (st === "COILED_UP") {
      V = { cls: "gp-up", icon: "⬆", h_en: "Coiled at the ceiling", h_zh: "贴近上沿蓄势",
        s_en: "Quiet but wound tight just under the ceiling — it usually fades back inside, but a daily CLOSE above the ceiling can let it run.",
        s_zh: "平静却在上沿之下紧绷 — 通常回落区间内，但日线收于上沿之上可能放行上涨。" };
    } else if (st === "COILED_DOWN") {
      V = { cls: "gp-warn", icon: "⬇", h_en: "Coiled at the floor", h_zh: "贴近下沿蓄势",
        s_en: "Quiet but wound tight just above the floor — it usually holds, but a daily CLOSE below the floor removes the cushion and can speed up the drop.",
        s_zh: "平静却在下沿之上紧绷 — 通常守住，但日线收于下沿之下会移除缓冲、可能加速下跌。" };
    } else if (st === "IN_HOLE") {
      V = { cls: "gp-calm", icon: "🧲", h_en: "Pinned & calm", h_zh: "磁吸 · 平静",
        s_en: "Expect chop, not trend: price tends to get pulled back toward the middle, so extremes toward the ceiling or floor often fade.",
        s_zh: "预期震荡而非趋势：价格倾向被拉回中部，逼近上/下沿的极端常常回落。" };
    } else {
      V = { cls: "gp-neutral", icon: "🧲", h_en: "Calm, no clear walls", h_zh: "平静 · 无明显墙",
        s_en: "Calm regime, but no firm walls are mapped today — lean on the chart and the expected range below.",
        s_zh: "平静体制，但今日无明确的墙 — 参考图表与下方预期区间。" };
    }

    var vHelp = help(lz(
      "A plain-English summary of today's options map. Dealers must hedge the options they hold: in a calm (long-gamma) regime they trade against moves, so price gets pinned; in a jumpy (short-gamma) regime they trade with moves, so price trends and jumps. The levels below are where that hedging clusters — a magnet, a ceiling and a floor. It's a MAP of where pressure sits, from delayed end-of-day data — not buy/sell advice and not price targets.",
      "今日期权地图的通俗总结。做市商必须对冲手中的期权：平静（多头Gamma）体制下逆势交易，价格被磁吸；跳动（空头Gamma）体制下顺势交易，价格趋势化与跳动。下方价位即对冲聚集处 — 磁吸位、上沿与下沿。这是压力分布的地图（延迟收盘数据），并非买卖建议或目标价。"));
    var head = '<div class="gp-head"><span class="gp-icon">' + V.icon + '</span><span class="gp-verdict">' +
      esc(lz(V.h_en, V.h_zh)) + "</span>" + vHelp + "</div>" +
      '<div class="gp-sub">' + esc(lz(V.s_en, V.s_zh)) + "</div>";

    // ---- levels to watch (ceiling, magnet, floor — ordered to match the ruler) ----
    var rows = [];
    if (s.call_wall != null) {
      rows.push(lvlRow("🟢", "Ceiling", "上沿（看涨墙）", s.call_wall,
        "Heavy call positioning caps rallies here. A daily CLOSE above " + price(s.call_wall) + " releases upside.",
        "此处大量看涨持仓压制上涨。日线收于 " + price(s.call_wall) + " 之上释放上行。",
        "The “call wall” — the strike with the most dealer gamma above today's price. Rallies often stall into it; a daily close through it can accelerate up. A level, not a target.",
        "“看涨墙” — 现价之上做市商Gamma最重的行权价。上涨常在此停滞；日线突破可能加速上行。是价位，非目标。"));
    } else if (s.magnet_up != null) {
      rows.push(lvlRow("🟢", "Resistance", "上方阻力", s.magnet_up,
        "Heaviest dealer gamma above price — a soft ceiling.",
        "现价之上做市商Gamma最重处 — 软上沿。",
        "The strike with the most dealer gamma above spot — a softer ceiling than a true call wall.",
        "现价之上做市商Gamma最大的行权价 — 比真正看涨墙更软的上沿。"));
    }
    var magVal = s.max_pain != null ? s.max_pain : s.gamma_flip;
    if (magVal != null) {
      var mt_en, mt_zh;
      if (regime === "short") { mt_en = "Magnet pull is weak in this jumpy regime."; mt_zh = "跳动体制下磁吸作用较弱。"; }
      else if (s.max_pain != null) { mt_en = "On quiet days price tends to drift toward " + price(s.max_pain) + " (where the most options expire worthless)."; mt_zh = "平静日价格倾向漂向 " + price(s.max_pain) + "（最多期权到期作废之处）。"; }
      else { mt_en = "On quiet days price tends to drift toward the " + price(s.gamma_flip) + " flip — the line between calm and jumpy."; mt_zh = "平静日价格倾向漂向 " + price(s.gamma_flip) + " 翻转 — 平静与跳动的分界。"; }
      var mh_en, mh_zh;
      if (s.max_pain != null) {
        mh_en = "“Max pain” — the price where the most options expire worthless, so hedging gently pulls price toward it on quiet days. Not a forecast.";
        mh_zh = "“最大痛点” — 最多期权到期作废的价格，平静日对冲会温和地把价格拉向它。并非预测。";
      } else {
        mh_en = "The gamma flip — the line between the calm and jumpy regimes; on quiet days price tends to drift toward it. A level, not a forecast.";
        mh_zh = "Gamma翻转 — 平静与跳动体制的分界；平静日价格倾向漂向它。是价位，非预测。";
      }
      rows.push(lvlRow("🧲", "Magnet", "磁吸位", magVal, mt_en, mt_zh, mh_en, mh_zh));
    }
    if (s.put_wall != null) {
      var ft_en = "Heavy put positioning cushions selloffs here. A daily CLOSE below " + price(s.put_wall) + " opens downside.";
      var ft_zh = "此处大量看跌持仓缓冲下跌。日线收于 " + price(s.put_wall) + " 之下打开下行。";
      if (regime === "short" && s.gamma_flip != null) {
        ft_en += " Below the " + price(s.gamma_flip) + " flip the cushion is gone — that's why swings are bigger now.";
        ft_zh += " 跌破 " + price(s.gamma_flip) + " 翻转后缓冲消失 — 这正是当前波动更大的原因。";
      }
      rows.push(lvlRow("🔴", "Floor", "下沿（看跌墙）", s.put_wall, ft_en, ft_zh,
        "The “put wall” — the strike with the most dealer gamma below today's price. Selloffs often slow into it; a daily close through it can accelerate down.",
        "“看跌墙” — 现价之下做市商Gamma最重的行权价。下跌常在此放缓；日线突破可能加速下行。"));
    } else if (s.magnet_down != null) {
      rows.push(lvlRow("🔴", "Support", "下方支撑", s.magnet_down,
        "Heaviest dealer gamma below price — a soft floor.",
        "现价之下做市商Gamma最重处 — 软下沿。",
        "The strike with the most dealer gamma below spot — a softer floor than a true put wall.",
        "现价之下做市商Gamma最大的行权价 — 比真正看跌墙更软的下沿。"));
    }
    var weakNote = (regime === "neutral" && rows.length)
      ? '<div class="gp-weak">' + esc(lz("Walls are weak guides today.", "今日墙的指引较弱。")) + "</div>" : "";
    var levels = rows.length ? '<div class="gp-levels">' + weakNote + rows.join("") + "</div>" : "";

    // ---- today's expected range ----
    var range = "";
    if (em.daily_pct != null && s.spot != null) {
      var lo = s.spot * (1 - em.daily_pct / 100), hi = s.spot * (1 + em.daily_pct / 100);
      range = '<div class="gp-range"><div class="gp-rk">📏 ' + esc(lz("Today's expected range", "今日预期区间")) + "</div>" +
        '<div class="gp-rv"><b>' + price(lo) + " – " + price(hi) + "</b> <span class='muted sm'>(±" +
        em.daily_pct.toFixed(2) + "%" + (em.daily_abs != null ? " / ±" + price(em.daily_abs) : "") + ")</span></div>" +
        '<div class="muted xs gp-rc">' + esc(lz(
          "Options imply a roughly 2-out-of-3 chance the close lands inside this band today.",
          "期权隐含：今日收盘约有三分之二的概率落在此区间内。")) + "</div></div>";
    }

    // ---- single-name caveat (the dealer sign is fragile off the indices/ETFs) ----
    var chip = "", grp = meta.grp || "";
    if (grp !== "Index" && grp.indexOf("ETF") < 0) {
      chip = '<div class="gp-chip">⚠ ' + esc(lz(
        "Single stock — the dealer-positioning sign here is an assumption and can be wrong (covered-call funds or heavy retail call-buying can flip it). Treat these levels as loose context, not lines to trade against.",
        "个股 — 此处做市商持仓符号为假设、可能出错（备兑基金或散户大量买看涨可使其翻转）。这些价位仅作宽松背景，切勿据此逆向交易。")) + "</div>";
    }

    return '<div class="gx-gameplan ' + V.cls + '">' + head + levels + range + dirTiltHTML() + chip + "</div>";
  }

  function lvlRow(icon, lab_en, lab_zh, val, trig_en, trig_zh, help_en, help_zh) {
    return '<div class="gp-lvl"><div class="gp-lk"><span class="gp-li">' + icon + "</span>" +
      '<span class="gp-ll">' + esc(lz(lab_en, lab_zh)) + '</span> <b class="gp-lv">' + price(val) + "</b>" +
      help(lz(help_en, help_zh)) + "</div>" +
      '<div class="gp-lt">' + esc(lz(trig_en, trig_zh)) + "</div></div>";
  }

  // ---- directional tilt (a ROUGH, approximate probability lean — risk & context only) ----
  // Built ONLY from the genuinely directional-ish (but weak) options pressures, never from
  // the GEX sign (which is about volatility, not direction). Every leg is shown so the read
  // is interpretable, and the output is deliberately near coin-flip most of the time.
  function skewPts(smile, spot) {
    if (!smile || !smile.strikes || smile.strikes.length < 3 || !spot) return null;
    var ks = smile.strikes, pv = smile.put_iv || [], cv = smile.call_iv || [], put = [], call = [];
    for (var i = 0; i < ks.length; i++) {
      if (ks[i] <= spot * 0.97 && pv[i] != null) put.push(pv[i]);
      if (ks[i] >= spot * 1.03 && cv[i] != null) call.push(cv[i]);
    }
    if (!put.length || !call.length) return null;
    var mean = function (a) { return a.reduce(function (x, y) { return x + y; }, 0) / a.length; };
    return mean(put) - mean(call);          // vol points; + = downside skew (puts richer)
  }

  function directionalLean() {
    var s = cur.summary, em = cur.expected_move || {};
    if (!s || s.spot == null) return null;
    var legs = [], score = 0, riskLegs = [], riskScore = 0;

    // ---- DIRECTIONAL legs: only forces that actually differ across names / over time ----
    // (charm drift & raw equity skew are structurally one-signed here — they carry no
    //  cross-sectional direction, so they feed the TAIL-RISK read below, not the tilt.)
    // 1) max-pain pin — only meaningful when price is genuinely NEAR the magnet
    if (s.max_pain != null) {
      var d = (s.max_pain - s.spot) / s.spot * 100;
      var near = Math.max(2.5, (em.weekly_pct || 0) * 1.3);
      if (Math.abs(d) >= 0.4 && Math.abs(d) <= near) {
        var mdir = d > 0 ? 1 : -1; score += mdir;
        legs.push({ dir: mdir, en: "Near the " + price(s.max_pain) + " max-pain magnet (" + (d > 0 ? "+" : "") + d.toFixed(1) + "%) — a mild pin pull " + (d > 0 ? "up" : "down") + " into expiry.",
          zh: "接近最大痛点 " + price(s.max_pain) + "（" + (d > 0 ? "+" : "") + d.toFixed(1) + "%）— 临近到期有轻微" + (d > 0 ? "上" : "下") + "磁吸。" });
      } else {
        legs.push({ dir: 0, en: "Max-pain " + price(s.max_pain) + " is " + (Math.abs(d) > near ? "far from price — negligible pull" : "right at price — no pull") + ".",
          zh: "最大痛点 " + price(s.max_pain) + (Math.abs(d) > near ? " 距现价较远 — 拉力可忽略" : " 正处于现价 — 无拉力") + "。" });
      }
    }
    // 2) put/call positioning — extreme readings are a weak CONTRARIAN tilt
    if (s.put_call_oi_ratio != null) {
      if (s.put_call_oi_ratio > 1.5) { score += 0.5; legs.push({ dir: 1, en: "Heavy put/call (" + s.put_call_oi_ratio.toFixed(2) + ") — the crowd is well-hedged; a weak contrarian-up read.", zh: "认沽/认购偏高（" + s.put_call_oi_ratio.toFixed(2) + "）— 人群对冲充分；弱反向偏上。" }); }
      else if (s.put_call_oi_ratio < 0.55) { score -= 0.5; legs.push({ dir: -1, en: "Light put/call (" + s.put_call_oi_ratio.toFixed(2) + ") — the crowd is call-heavy / unhedged; a weak contrarian-down read.", zh: "认沽/认购偏低（" + s.put_call_oi_ratio.toFixed(2) + "）— 人群偏看涨/对冲不足；弱反向偏下。" }); }
      else { legs.push({ dir: 0, en: "Put/call (" + s.put_call_oi_ratio.toFixed(2) + ") is unremarkable — no contrarian tilt.", zh: "认沽/认购（" + s.put_call_oi_ratio.toFixed(2) + "）无异常 — 无反向倾向。" }); }
    }

    // ---- TAIL-RISK read: which way a surprise is likelier to break (NOT the tilt) ----
    if (s.regime === "short") { riskScore++; riskLegs.push(lz("Jumpy short-gamma regime — moves amplify and air-pockets skew to the downside.", "跳动空头Gamma体制 — 走势放大、急跌偏下行。")); }
    else { riskLegs.push(lz("Calm long-gamma regime — dealer hedging dampens both directions.", "平静多头Gamma体制 — 做市商对冲双向抑制。")); }
    var sk = skewPts(cur.smile, s.spot);
    if (sk != null && sk > 6) { riskScore++; riskLegs.push(lz("Steep put skew — the market is paying up for downside protection.", "看跌偏斜陡峭 — 市场为下行保护付溢价。")); }
    else if (sk != null && sk < 0) { riskScore--; riskLegs.push(lz("Inverted skew — calls bid over puts (upside / squeeze risk).", "偏斜反转 — 看涨比看跌更贵（上行/逼空风险）。")); }

    return { score: score, legs: legs, riskScore: riskScore, riskLegs: riskLegs };
  }

  function leanBucket(score) {
    if (score >= 1.5) return { cls: "up", en: "Upside tilt", zh: "偏上行", odds_en: "≈60 / 40 up", odds_zh: "≈60 / 40 偏上" };
    if (score >= 0.5) return { cls: "up", en: "Leans higher", zh: "略偏上", odds_en: "≈55 / 45 up", odds_zh: "≈55 / 45 偏上" };
    if (score > -0.5) return { cls: "neu", en: "Balanced", zh: "均衡", odds_en: "≈50 / 50 — a coin flip", odds_zh: "≈50 / 50 — 接近抛硬币" };
    if (score > -1.5) return { cls: "down", en: "Leans lower", zh: "略偏下", odds_en: "≈55 / 45 down", odds_zh: "≈55 / 45 偏下" };
    return { cls: "down", en: "Downside tilt", zh: "偏下行", odds_en: "≈60 / 40 down", odds_zh: "≈60 / 40 偏下" };
  }

  function riskBucket(rs) {
    if (rs >= 2) return { cls: "down", en: "Elevated · downside", zh: "偏高 · 下行" };
    if (rs === 1) return { cls: "warn", en: "Moderate · downside-tilted", zh: "中等 · 偏下行" };
    if (rs < 0) return { cls: "up", en: "Upside / squeeze", zh: "上行 / 逼空" };
    return { cls: "neu", en: "Low / normal", zh: "低 / 正常" };
  }

  function dirTiltHTML() {
    var d = directionalLean(); if (!d) return "";
    var b = leanBucket(d.score), rb = riskBucket(d.riskScore);
    var pos = Math.max(3, Math.min(97, 50 + d.score / 1.5 * 47));
    var arrow = b.cls === "up" ? "▲" : b.cls === "down" ? "▼" : "●";
    var dHelp = help(lz(
      "A ROUGH directional lean from options positioning — built only from the forces that actually vary: a max-pain pin pull when price is near it, and an extreme put/call (contrarian) reading. Charm drift and equity skew are deliberately excluded from the tilt because they're one-signed across all names (they feed the Tail-risk read instead). It's a probabilistic lean, not a forecast — direction is inherently far less reliable than the volatility regime above, and most names sit near a coin-flip.",
      "由期权持仓推算的粗略方向倾向 — 仅采用真正会变化的因素：价格接近最大痛点时的磁吸，以及极端认沽/认购（反向）读数。Charm漂移与股票偏斜被刻意排除在倾向之外，因为它们对所有标的同号（改而计入尾部风险）。这是概率性倾向、并非预测 — 方向本质上远不如上方的波动体制可靠，多数标的接近抛硬币。"));
    var head = '<div class="dt-head"><span class="dt-k">🧭 ' + lz("Directional tilt", "方向倾向") + ' <span class="muted">' + lz("(rough, approximate)", "（粗略、近似）") + "</span>" + dHelp + "</span>" +
      '<span class="dt-verdict dt-' + b.cls + '">' + arrow + " " + esc(lz(b.en, b.zh)) + ' <span class="dt-odds">' + esc(lz(b.odds_en, b.odds_zh)) + "</span></span></div>";
    var meter = '<div class="dt-meter"><div class="dt-track"></div><div class="dt-mid"></div>' +
      '<div class="dt-needle dt-' + b.cls + '" style="left:' + pos.toFixed(1) + '%"></div>' +
      '<span class="dt-end l">↓ ' + lz("downside", "下行") + '</span><span class="dt-end r">' + lz("upside", "上行") + " ↑</span></div>";
    var legs = '<ul class="dt-legs">' + d.legs.map(function (l) {
      var ic = l.dir > 0 ? '<span class="pos">↑</span>' : l.dir < 0 ? '<span class="neg">↓</span>' : '<span class="muted">•</span>';
      return "<li>" + ic + " " + esc(lz(l.en, l.zh)) + "</li>";
    }).join("") + "</ul>";
    var risk = '<div class="dt-risk"><span class="dt-rk">' + lz("Tail risk", "尾部风险") + ': <b class="dt-' + rb.cls + '">' + esc(lz(rb.en, rb.zh)) + "</b></span>" +
      '<span class="muted xs">' + esc(d.riskLegs.join(lz("  ·  ", "  ·  "))) + "</span></div>";
    var disc = '<div class="dt-disc">⚠ ' + lz(
      "Approximate probability tilt from options positioning — NOT a trade signal. Use it for risk &amp; context (what to hedge, how to size), never as a reason to buy or sell. Most of the time it sits near a coin-flip; direction is far less reliable than the volatility read above.",
      "由期权持仓推算的近似概率倾向 — 并非交易信号。仅用于风险与背景（对冲什么、如何控制仓位），切勿作为买卖理由。多数时候接近抛硬币；方向远不如上方的波动读数可靠。") + "</div>";
    return '<div class="dt">' + head + meter + legs + risk + disc + "</div>";
  }

  // ---- volatility hole (dealer-gamma compression band, DannyTrades framing) ----
  var VHS = {
    IN_HOLE:     { emo: "🧲", en: "In the hole — boxed in",  zh: "洞内 · 被困",  cls: "neu",  sh_en: "In hole",     sh_zh: "洞内" },
    COILED_UP:   { emo: "⬆",  en: "Coiled at the ceiling",   zh: "贴上沿蓄势",   cls: "up",   sh_en: "Coiled up",   sh_zh: "贴上沿" },
    COILED_DOWN: { emo: "⬇",  en: "Coiled at the floor",     zh: "贴下沿蓄势",   cls: "down", sh_en: "Coiled down", sh_zh: "贴下沿" },
    EXPANSION:   { emo: "🌪", en: "Expansion — jumpy zone",  zh: "扩张 · 跳动区", cls: "vol",  sh_en: "Expansion",   sh_zh: "扩张" },
    NONE:        { emo: "·",  en: "No clear hole",           zh: "无明显洞",     cls: "na",   sh_en: "—",           sh_zh: "—" }
  };

  function vhCell(m) {
    if (!m.vh_state || m.vh_state === "NONE") return '<td><span class="vh-pill na">—</span></td>';
    var v = VHS[m.vh_state] || VHS.NONE;
    return '<td><span class="vh-pill ' + v.cls + '" title="' + esc(lz(v.en, v.zh)) + '">' + v.emo + " " + esc(lz(v.sh_en, v.sh_zh)) + "</span></td>";
  }

  function sigTxt(x) { return x == null ? "—" : (+x).toFixed(1) + "σ"; }

  function vhRead(vh, s) {
    var up = price(vh.upper), lo = price(vh.lower);
    var hasFlip = s.gamma_flip != null, flip = price(s.gamma_flip);
    switch (vh.state) {
      case "IN_HOLE":
        return lz(
          "<b>In the calm zone.</b> Price is parked between a <b>" + lo + "</b> floor and a <b>" + up + "</b> ceiling, and dealer hedging leans against moves — so it tends to drift back toward the middle and stay range-bound. The zone holds until a daily CLOSE outside " + lo + "–" + up + " breaks the spell and lets a bigger move run.",
          "<b>处于平静区。</b> 价格停在 <b>" + lo + "</b> 下沿与 <b>" + up + "</b> 上沿之间，做市商对冲逆势而行 — 因而倾向回到中部、维持区间。该区间持续，直到日线收于 " + lo + "–" + up + " 之外打破平衡、放行更大的走势。");
      case "COILED_UP":
        return lz(
          "<b>Coiled at the ceiling.</b> Price is pressed against the <b>" + up + "</b> call wall, where dealers have been capping the rally. While it holds, that wall acts like a lid. But a daily CLOSE above " + up + " can flip dealers into chasing the move — turning the ceiling into a launchpad for a faster push higher.",
          "<b>贴近上沿蓄势。</b> 价格贴住 <b>" + up + "</b> 看涨墙，做市商一直在此压制上涨。只要守住，该墙就像盖子。但日线收于 " + up + " 之上会使做市商转为追逐 — 让上沿变成更快上行的跳板。");
      case "COILED_DOWN":
        return lz(
          "<b>Coiled at the floor.</b> Price is pressed against the <b>" + lo + "</b> put wall, where dealer buying has been cushioning the drop. While it holds, that wall acts like a trampoline. But a daily CLOSE below " + lo + " can flip dealers into selling with the move — pulling the floor out and opening an air-pocket lower.",
          "<b>贴近下沿蓄势。</b> 价格贴住 <b>" + lo + "</b> 看跌墙，做市商买入一直在此缓冲下跌。只要守住，该墙就像蹦床。但日线收于 " + lo + " 之下会使做市商转为顺势卖出 — 抽走下沿、向下打开急跌缺口。");
      case "EXPANSION":
        var fl = hasFlip ? "<b>" + flip + "</b> " : "";
        var fb = hasFlip ? flip : lz("the flip", "翻转");
        return lz(
          "<b>Already in the jumpy zone.</b> Price is below the " + fl + "flip line, so dealers are now hedging with the move — both trends and sudden air-pockets run bigger than normal, and the downside tends to move faster. There's no calming band here until price climbs back above " + fb + " and the market flips calm again.",
          "<b>已处于跳动区。</b> 价格位于 " + fl + "翻转线之下，做市商现在顺势对冲 — 趋势与突发急跌都比平常更大，下行往往更快。在价格重新升破 " + fb + " 、市场转回平静之前，这里没有压制带。");
      default:
        return "";
    }
  }

  function vhBand(vh, s) {
    var lo = vh.lower, hi = vh.upper, sp = s.spot;
    var vals = [sp]; if (lo != null) vals.push(lo); if (hi != null) vals.push(hi);
    if (vals.length < 2 || sp == null) return "";
    var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
    var pad = (mx - mn) * 0.18 || (sp * 0.02) || 1; mn -= pad; mx += pad;
    function xp(v) { return (v - mn) / (mx - mn) * 100; }
    var html = '<div class="vh-band"><div class="track">';
    if (lo != null && hi != null) {
      var x1 = xp(lo), x2 = xp(hi);
      html += '<div class="fill" style="left:' + x1.toFixed(1) + "%;width:" + (x2 - x1).toFixed(1) + "%;background:var(--info)\"></div>";
    }
    html += "</div>";
    function mk(v, cls, lab) {
      if (v == null) return "";
      var x = xp(v).toFixed(1);
      return '<div class="mk ' + cls + '" style="left:' + x + '%"></div>' +
        '<div class="cap ' + (cls === "spot" ? "spot" : "") + '" style="left:' + x + '%"><span class="v">' + price(v) + "</span>" + esc(lab) + "</div>";
    }
    html += mk(lo, "lo", lz("floor", "下沿")) + mk(hi, "hi", lz("ceiling", "上沿")) + mk(sp, "spot", lz("spot", "现价"));
    return html + "</div>";
  }

  function vhStats(vh) {
    var out = [];
    if (vh.to_lower_sigma != null) out.push(lz("To floor: ", "距下沿：") + "<b>" + sigTxt(vh.to_lower_sigma) + "</b>" + (vh.to_lower_pct != null ? " (" + vh.to_lower_pct + "%)" : ""));
    if (vh.to_upper_sigma != null) out.push(lz("To ceiling: ", "距上沿：") + "<b>" + sigTxt(vh.to_upper_sigma) + "</b>" + (vh.to_upper_pct != null ? " (" + vh.to_upper_pct + "%)" : ""));
    if (vh.band_width_pct != null) out.push(lz("Band width: ", "区间宽度：") + "<b>" + vh.band_width_pct + "%</b>");
    if (vh.compression) {
      var cc = vh.compression === "tight" ? lz("tight (coiled)", "紧（蓄势）")
        : vh.compression === "wide" ? lz("wide (loose)", "宽（松散）") : lz("normal", "一般");
      out.push(lz("Compression: ", "压缩：") + "<b>" + cc + "</b>");
    }
    return out.length ? '<div class="vh-stats">' + out.join("") + "</div>" : "";
  }

  function volHoleHTML() {
    var vh = cur.vol_hole; if (!vh || vh.state === "NONE") return "";
    var s = cur.summary;
    var v = VHS[vh.state] || VHS.NONE;
    var biasCls = vh.bias === "up" ? "vh-up" : vh.bias === "down" ? "vh-down"
      : vh.bias === "volatile" ? "vh-volatile" : "vh-neutral";
    var hHelp = help(lz(
      "In a calm (long-gamma) regime, dealer hedging defends a floor and a ceiling, trapping price in a low-volatility band — the “hole.” Pressed against a wall = “coiled,” where the next daily close decides whether it pins or breaks. Below the flip, that band is gone and volatility expands. It's a relabeling of the flip and walls from delayed end-of-day data — not a backtested or proprietary edge.",
      "在平静（多头Gamma）体制下，做市商对冲守住下沿与上沿，把价格困在低波动带 — 即“洞”。贴住某墙=“蓄势”，下一根日线收盘决定是被磁吸还是突破。翻转之下，该带消失、波动扩张。这是对翻转与墙的重新表述（延迟收盘数据）— 并非回测或专有优势。"));
    var head = '<div class="topline" style="justify-content:space-between;align-items:center"><h2 style="margin:0">' +
      lz("🕳️ Volatility Hole", "🕳️ 波动洞") + hHelp + '</h2><span class="vh-badge ' + v.cls + '">' + v.emo + " " + esc(lz(v.en, v.zh)) + "</span></div>" +
      '<p class="muted xs" style="margin:6px 0 0">' + esc(lz(
        "How trapped vs. free the price is to move — a plain-English read of the flip and the walls (sometimes nicknamed the “volatility hole”). It's a relabeling of those levels, not a separate indicator.",
        "价格被困还是可自由波动 — 对翻转与墙的通俗解读（有时戏称“波动洞”）。它是对这些价位的重新表述，并非独立指标。")) + "</p>";
    var caveat = '<p class="muted xs" style="margin:8px 0 0">' + esc(lz(
      "Walls are measured from yesterday's close, so on any single day price sits inside the band by construction — you can't read a live wall break from one snapshot; only the daily close beyond a level counts, and the dealer sign is an assumption that's shaky for single names.",
      "墙以昨日收盘计算，因此任意单日价格按构造必在带内 — 无法从单帧快照读出实时突破；只有日线收盘越过某价位才算数，且做市商符号为假设、对个股不稳。")) + "</p>";
    return '<div class="panel vhole ' + biasCls + '">' + head +
      '<div class="vh-read">' + vhRead(vh, s) + "</div>" + vhBand(vh, s) + vhStats(vh) + caveat + "</div>";
  }

  // ---- key-levels ruler (two label lanes so close markers don't collide) ----
  function rulerHTML() {
    var s = cur.summary;
    var pts = [
      { v: s.put_wall, lab: lz("Put wall", "看跌墙"), cls: "pw" },
      { v: s.gamma_flip, lab: lz("Flip", "翻转"), cls: "flip" },
      { v: s.max_pain, lab: lz("Max pain", "最大痛点"), cls: "mp" },
      { v: s.call_wall, lab: lz("Call wall", "看涨墙"), cls: "cw" },
      { v: s.spot, lab: lz("Spot", "现价"), cls: "spot" }
    ].filter(function (p) { return p.v != null; });
    if (pts.length < 2) return "";
    var vals = pts.map(function (p) { return p.v; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pad = (hi - lo) * 0.10 || 1; lo -= pad; hi += pad;
    function xp(v) { return (v - lo) / (hi - lo) * 100; }
    pts.sort(function (a, b) { return a.v - b.v; });
    var lastX = [-99, -99], GAP = 11;       // assign 2 lanes by horizontal proximity
    pts.forEach(function (p) {
      var px = xp(p.v);
      var lane = (px - lastX[0] >= GAP) ? 0 : (px - lastX[1] >= GAP) ? 1 : (lastX[0] <= lastX[1] ? 0 : 1);
      p.lane = lane; lastX[lane] = px;
    });
    var mk = pts.map(function (p) {
      return '<div class="mk ' + p.cls + " lane" + p.lane + '" style="left:' + xp(p.v).toFixed(2) + '%">' +
        '<i></i><span class="lbl"><span class="val">' + price(p.v) + '</span><span class="lab">' + esc(p.lab) + "</span></span></div>";
    }).join("");
    return '<div class="ruler"><div class="axis"></div>' + mk + "</div>";
  }

  // ========================================================================
  // BAR CHART (walls / OI / volume by strike)
  // ========================================================================
  function barTabs() {
    return [["gamma", lz("Dealer gamma", "做市商Gamma")], ["oi", lz("Open interest", "未平仓")], ["vol", lz("Volume", "成交量")]]
      .map(function (t) { return '<span class="hm-tab' + (barMode === t[0] ? " on" : "") + '" data-m="' + t[0] + '">' + t[1] + "</span>"; }).join("");
  }
  function barLegend() {
    if (barMode === "gamma") return '<div class="legend"><span><i style="background:var(--up)"></i>' + lz("call gamma (+)", "看涨Gamma(+)") + '</span><span><i style="background:var(--down)"></i>' + lz("put gamma (−)", "看跌Gamma(−)") + "</span></div>";
    return '<div class="legend"><span><i style="background:var(--up)"></i>' + lz("calls →", "看涨 →") + '</span><span><i style="background:var(--down)"></i>' + lz("← puts", "← 看跌") + "</span></div>";
  }
  function wireBarTabs() {
    document.querySelectorAll("#gx-bartabs .hm-tab").forEach(function (t) {
      t.addEventListener("click", function () {
        barMode = t.getAttribute("data-m");
        document.querySelectorAll("#gx-bartabs .hm-tab").forEach(function (x) { x.classList.remove("on"); });
        t.classList.add("on");
        document.querySelector("#gx-bars").parentNode.querySelector(".legend").outerHTML = barLegend();
        drawBars();
      });
    });
  }
  function drawBars() {
    var host = document.getElementById("gx-bars"); if (!host) return;
    var w = cur.walls, rows = (w.by_strike || []).slice();
    if (!rows.length) { host.innerHTML = '<div class="muted sm">—</div>'; return; }
    var s = cur.summary;
    var W = 540, H = 400, mL = 50, mR = 74, mT = 12, mB = 22;
    var ks = rows.map(function (r) { return r.K; });
    var loK = Math.min.apply(null, ks), hiK = Math.max.apply(null, ks);
    if (s.spot != null) { loK = Math.min(loK, s.spot); hiK = Math.max(hiK, s.spot); }
    var padK = (hiK - loK) * 0.04 || 1; loK -= padK; hiK += padK;
    function y(v) { return mT + (hiK - v) / (hiK - loK) * (H - mT - mB); }
    var plotW = W - mL - mR, x0 = mL + plotW / 2;
    // values per mode
    var vals = rows.map(function (r) {
      if (barMode === "gamma") return { L: r.net_mn < 0 ? -r.net_mn : 0, R: r.net_mn >= 0 ? r.net_mn : 0, net: r.net_mn };
      if (barMode === "oi") return { L: r.put_oi, R: r.call_oi };
      return { L: r.put_vol, R: r.call_vol };
    });
    var maxAbs = 0; vals.forEach(function (v) { maxAbs = Math.max(maxAbs, v.L, v.R); }); maxAbs = maxAbs || 1;
    var half = plotW / 2 - 4, sc = half / maxAbs;
    var bh = Math.max(2, Math.min(13, (H - mT - mB) / rows.length * 0.78));
    var up = cssv("--up"), down = cssv("--down"), info = cssv("--info"), text = cssv("--text"), muted = cssv("--muted"), line = cssv("--line"), orange = cssv("--orange");

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img">';
    // center axis
    svg += '<line x1="' + x0 + '" y1="' + mT + '" x2="' + x0 + '" y2="' + (H - mB) + '" stroke="' + line + '" stroke-width="1"/>';
    // price ticks (left)
    for (var i = 0; i <= 5; i++) {
      var pv = loK + (hiK - loK) * i / 5, yy = y(pv);
      svg += '<text x="' + (mL - 6) + '" y="' + (yy + 3) + '" text-anchor="end" font-size="10" fill="' + muted + '">' + price(pv) + "</text>";
      svg += '<line x1="' + mL + '" y1="' + yy + '" x2="' + (W - mR) + '" y2="' + yy + '" stroke="' + line + '" stroke-width="0.5" opacity="0.4"/>';
    }
    // bars
    rows.forEach(function (r, idx) {
      var v = vals[idx], yy = y(r.K);
      if (v.R > 0) svg += '<rect x="' + x0 + '" y="' + (yy - bh / 2) + '" width="' + (v.R * sc) + '" height="' + bh + '" fill="' + up + '" opacity="0.82"><title>' + r.K + "</title></rect>";
      if (v.L > 0) svg += '<rect x="' + (x0 - v.L * sc) + '" y="' + (yy - bh / 2) + '" width="' + (v.L * sc) + '" height="' + bh + '" fill="' + down + '" opacity="0.82"><title>' + r.K + "</title></rect>";
    });
    // level lines (lines at true y; right-edge labels dodged so close levels don't overlap)
    var levels = [
      { v: s.call_wall, c: up, t: lz("call wall", "看涨墙") },
      { v: s.spot, c: text, t: lz("spot", "现价") },
      { v: s.gamma_flip, c: info, t: lz("flip", "翻转") },
      { v: s.put_wall, c: down, t: lz("put wall", "看跌墙") }
    ].filter(function (L) { return L.v != null; }).map(function (L) { return { c: L.c, t: L.t, y: y(L.v) }; });
    levels.forEach(function (L) {
      svg += '<line x1="' + mL + '" y1="' + L.y.toFixed(1) + '" x2="' + (W - mR) + '" y2="' + L.y.toFixed(1) + '" stroke="' + L.c + '" stroke-width="1.3" stroke-dasharray="4 3"/>';
    });
    var sortedL = levels.slice().sort(function (a, b) { return a.y - b.y; });
    var GAPL = 13, prevLy = -1e9;
    sortedL.forEach(function (L) { L.ly = Math.max(L.y, prevLy + GAPL); prevLy = L.ly; });
    var overflow = sortedL.length ? sortedL[sortedL.length - 1].ly - (H - 4) : 0;
    if (overflow > 0) sortedL.forEach(function (L) { L.ly -= overflow; });
    sortedL.forEach(function (L) {
      if (Math.abs(L.ly - L.y) > 2)
        svg += '<line x1="' + (W - mR) + '" y1="' + L.y.toFixed(1) + '" x2="' + (W - mR + 4) + '" y2="' + L.ly.toFixed(1) + '" stroke="' + L.c + '" stroke-width="0.7" opacity="0.55"/>';
      svg += '<text x="' + (W - mR + 5) + '" y="' + (L.ly + 3).toFixed(1) + '" font-size="10" fill="' + L.c + '">' + L.t + "</text>";
    });
    svg += "</svg>";
    host.innerHTML = svg;
  }

  // ========================================================================
  // PROFILE CURVE (net gamma vs spot grid)
  // ========================================================================
  function drawProfile() {
    var host = document.getElementById("gx-profile"); if (!host) return;
    var p = cur.profile;
    if (!p || !p.spots || !p.spots.length) { host.innerHTML = '<div class="muted sm">—</div>'; return; }
    var W = 540, H = 300, mL = 46, mR = 14, mT = 14, mB = 26;
    var xs = p.spots, ys = p.gamma_bn;
    var xlo = Math.min.apply(null, xs), xhi = Math.max.apply(null, xs);
    var ylo = Math.min.apply(null, ys), yhi = Math.max.apply(null, ys);
    if (ylo > 0) ylo = 0; if (yhi < 0) yhi = 0;
    var ypad = (yhi - ylo) * 0.08 || 1; ylo -= ypad; yhi += ypad;
    function X(v) { return mL + (v - xlo) / (xhi - xlo) * (W - mL - mR); }
    function Y(v) { return mT + (yhi - v) / (yhi - ylo) * (H - mT - mB); }
    var zeroY = Y(0);
    var up = cssv("--up"), down = cssv("--down"), info = cssv("--info"), text = cssv("--text"), muted = cssv("--muted"), line = cssv("--line");

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img">';
    // y grid + labels
    for (var i = 0; i <= 4; i++) {
      var gv = ylo + (yhi - ylo) * i / 4, yy = Y(gv);
      svg += '<line x1="' + mL + '" y1="' + yy + '" x2="' + (W - mR) + '" y2="' + yy + '" stroke="' + line + '" stroke-width="0.5" opacity="0.4"/>';
      svg += '<text x="' + (mL - 5) + '" y="' + (yy + 3) + '" text-anchor="end" font-size="10" fill="' + muted + '">' + (+gv).toFixed(1) + "</text>";
    }
    // zero line emphasised
    svg += '<line x1="' + mL + '" y1="' + zeroY + '" x2="' + (W - mR) + '" y2="' + zeroY + '" stroke="' + muted + '" stroke-width="1"/>';
    // signed area fills (split at zero crossings)
    for (var k = 0; k < xs.length - 1; k++) {
      var xA = X(xs[k]), xB = X(xs[k + 1]), yA = ys[k], yB = ys[k + 1];
      if ((yA < 0) !== (yB < 0) && yA !== yB) {
        var xc = xA + (0 - yA) / (yB - yA) * (xB - xA);
        svg += areaSeg(xA, Y(yA), xc, zeroY, zeroY, yA >= 0 ? up : down);
        svg += areaSeg(xc, zeroY, xB, Y(yB), zeroY, yB >= 0 ? up : down);
      } else {
        svg += areaSeg(xA, Y(yA), xB, Y(yB), zeroY, (yA + yB) / 2 >= 0 ? up : down);
      }
    }
    // line
    var d = xs.map(function (v, i2) { return (i2 ? "L" : "M") + X(v).toFixed(1) + " " + Y(ys[i2]).toFixed(1); }).join(" ");
    svg += '<path d="' + d + '" fill="none" stroke="' + text + '" stroke-width="1.6"/>';
    // spot + flip markers
    if (p.spot != null) {
      svg += '<line x1="' + X(p.spot) + '" y1="' + mT + '" x2="' + X(p.spot) + '" y2="' + (H - mB) + '" stroke="' + text + '" stroke-width="1" stroke-dasharray="3 3"/>';
      svg += '<text x="' + X(p.spot) + '" y="' + (mT + 9) + '" text-anchor="middle" font-size="10" fill="' + text + '">' + lz("spot", "现价") + " " + price(p.spot) + "</text>";
    }
    if (p.flip != null) {
      svg += '<line x1="' + X(p.flip) + '" y1="' + mT + '" x2="' + X(p.flip) + '" y2="' + (H - mB) + '" stroke="' + info + '" stroke-width="1.2" stroke-dasharray="4 3"/>';
      // flip label stacked under the spot label (top) so the two don't collide when close
      svg += '<text x="' + X(p.flip) + '" y="' + (mT + 22) + '" text-anchor="middle" font-size="10" fill="' + info + '">' + lz("flip", "翻转") + " " + price(p.flip) + "</text>";
    }
    // x ticks
    for (var j = 0; j <= 4; j++) {
      var xv = xlo + (xhi - xlo) * j / 4;
      svg += '<text x="' + X(xv) + '" y="' + (H - mB + 14) + '" text-anchor="middle" font-size="9.5" fill="' + muted + '">' + price(xv) + "</text>";
    }
    svg += "</svg>";
    host.innerHTML = svg;
  }
  function areaSeg(xA, yA, xB, yB, zeroY, color) {
    return '<path d="M' + xA.toFixed(1) + " " + zeroY.toFixed(1) + " L" + xA.toFixed(1) + " " + yA.toFixed(1) +
      " L" + xB.toFixed(1) + " " + yB.toFixed(1) + " L" + xB.toFixed(1) + " " + zeroY.toFixed(1) + 'Z" fill="' + color + '" opacity="0.16"/>';
  }

  // ========================================================================
  // HEATMAP (strike × expiry)
  // ========================================================================
  function heatTabs() {
    return [["gex", lz("Dealer gamma", "做市商Gamma")], ["oi", lz("Open interest", "未平仓")], ["vol", lz("Volume", "成交量")]]
      .map(function (t) { return '<span class="hm-tab' + (heatMode === t[0] ? " on" : "") + '" data-m="' + t[0] + '">' + t[1] + "</span>"; }).join("");
  }
  function heatLegend() {
    if (heatMode === "gex") return '<div class="hm-legend"><span><span class="sw" style="background:var(--down)"></span>' + lz("put-gamma (−)", "看跌Gamma(−)") + '</span><span><span class="sw" style="background:var(--up)"></span>' + lz("call-gamma (+)", "看涨Gamma(+)") + '</span><span>' + lz("outlined row = nearest strike to spot", "加框行 = 最接近现价的行权价") + "</span></div>";
    return '<div class="hm-legend"><span><span class="sw" style="background:linear-gradient(90deg,var(--panel2),var(--info))"></span>' + (heatMode === "oi" ? lz("low → high open interest", "未平仓 低 → 高") : lz("low → high volume", "成交量 低 → 高")) + "</span></div>";
  }
  function wireHeatTabs() {
    document.querySelectorAll("#gx-heattabs .hm-tab").forEach(function (t) {
      t.addEventListener("click", function () {
        heatMode = t.getAttribute("data-m");
        document.querySelectorAll("#gx-heattabs .hm-tab").forEach(function (x) { x.classList.remove("on"); });
        t.classList.add("on");
        var p = document.getElementById("gx-heat").parentNode;
        p.querySelector(".hm-legend").outerHTML = heatLegend();
        drawHeat();
      });
    });
  }
  function drawHeat() {
    var host = document.getElementById("gx-heat"); if (!host) return;
    var sf = cur.surface, s = cur.summary;
    if (!sf || !sf.strikes || !sf.strikes.length) { host.innerHTML = '<div class="muted sm">—</div>'; return; }
    var z = heatMode === "gex" ? sf.z_gex : heatMode === "oi" ? sf.z_oi : sf.z_vol;
    var mx = heatMode === "gex" ? sf.gex_max : heatMode === "oi" ? sf.oi_max : sf.vol_max;
    mx = mx || 1;
    // strike nearest spot -> outline
    var nearest = null, best = 1e18;
    sf.strikes.forEach(function (k) { var d = Math.abs(k - s.spot); if (d < best) { best = d; nearest = k; } });
    var html = '<table class="heat"><thead><tr><th></th>';
    sf.expiries.forEach(function (e, i) { html += '<th class="col">' + esc(e) + '<br><span class="xs muted">' + sf.days[i] + "d</span></th>"; });
    html += "</tr></thead><tbody>";
    sf.strikes.forEach(function (k, ri) {
      var rowCls = (k === nearest) ? " spotrow" : "";
      html += '<tr><td class="kk">' + price(k) + "</td>";
      sf.expiries.forEach(function (e, ci) {
        var v = z[ri][ci];
        if (v === null || v === undefined) { html += '<td class="cell' + rowCls + '" style="background:' + rgba("--g-mid", 0.10) + '">·</td>'; return; }
        var bg, txt;
        if (heatMode === "gex") {
          var a = 0.12 + 0.8 * Math.min(1, Math.abs(v) / mx);
          bg = rgba(v >= 0 ? "--up" : "--down", a);
          txt = Math.abs(v) >= 1 ? Math.round(v) : "";
        } else {
          var a2 = 0.10 + 0.85 * Math.min(1, v / mx);
          bg = rgba("--info", a2);
          txt = v > 0 ? compact(v) : "";
        }
        html += '<td class="cell' + rowCls + '" style="background:' + bg + '" data-k="' + k + '" data-e="' + esc(e) + '" data-v="' + v + '">' + txt + "</td>";
      });
      html += "</tr>";
    });
    html += "</tbody></table>";
    host.innerHTML = html;
    // hover tooltips
    var unit = heatMode === "gex" ? lz("$mn dealer gamma", "百万$做市商Gamma") : heatMode === "oi" ? lz("contracts OI", "未平仓合约") : lz("contracts vol", "成交合约");
    host.querySelectorAll("td.cell[data-v]").forEach(function (td) {
      td.addEventListener("mousemove", function (e) {
        var v = +td.getAttribute("data-v");
        showTip("<b>" + esc(td.getAttribute("data-e")) + "</b> · " + lz("strike", "行权") + " " + price(+td.getAttribute("data-k")) +
          "<br>" + (heatMode === "gex" ? sgn(v, v >= 100 || v <= -100 ? 0 : 1) : compact(v)) + " " + unit, e.clientX, e.clientY);
      });
      td.addEventListener("mouseleave", hideTip);
    });
  }

  // ========================================================================
  // VOL SMILE + IV TERM
  // ========================================================================
  function drawSmile() {
    var host = document.getElementById("gx-smile"); if (!host) return;
    var sm = cur.smile, s = cur.summary;
    if (!sm || !sm.strikes || sm.strikes.length < 3) { host.innerHTML = '<div class="muted sm">' + lz("not enough strikes", "行权价不足") + "</div>"; return; }
    var W = 540, H = 280, mL = 40, mR = 14, mT = 26, mB = 26;
    var ks = sm.strikes;
    var all = sm.call_iv.concat(sm.put_iv).filter(function (v) { return v != null; });
    var ylo = Math.min.apply(null, all), yhi = Math.max.apply(null, all);
    var yp = (yhi - ylo) * 0.12 || 1; ylo -= yp; yhi += yp; if (ylo < 0) ylo = 0;
    var xlo = ks[0], xhi = ks[ks.length - 1];
    function X(v) { return mL + (v - xlo) / (xhi - xlo) * (W - mL - mR); }
    function Y(v) { return mT + (yhi - v) / (yhi - ylo) * (H - mT - mB); }
    var up = cssv("--up"), down = cssv("--down"), text = cssv("--text"), muted = cssv("--muted"), line = cssv("--line");
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img">';
    for (var i = 0; i <= 4; i++) {
      var gv = ylo + (yhi - ylo) * i / 4, yy = Y(gv);
      svg += '<line x1="' + mL + '" y1="' + yy + '" x2="' + (W - mR) + '" y2="' + yy + '" stroke="' + line + '" stroke-width="0.5" opacity="0.4"/>';
      svg += '<text x="' + (mL - 5) + '" y="' + (yy + 3) + '" text-anchor="end" font-size="10" fill="' + muted + '">' + (+gv).toFixed(0) + "%</text>";
    }
    svg += polyline(ks, sm.put_iv, X, Y, down, 1.6);
    svg += polyline(ks, sm.call_iv, X, Y, up, 1.6);
    if (s.spot != null && s.spot >= xlo && s.spot <= xhi) {
      svg += '<line x1="' + X(s.spot) + '" y1="' + mT + '" x2="' + X(s.spot) + '" y2="' + (H - mB) + '" stroke="' + text + '" stroke-width="1" stroke-dasharray="3 3"/>' +
        '<text x="' + X(s.spot) + '" y="' + (mT - 6) + '" text-anchor="middle" font-size="10" fill="' + text + '">' + lz("ATM", "平值") + "</text>";
    }
    for (var j = 0; j <= 4; j++) { var xv = xlo + (xhi - xlo) * j / 4; svg += '<text x="' + X(xv) + '" y="' + (H - mB + 14) + '" text-anchor="middle" font-size="9.5" fill="' + muted + '">' + price(xv) + "</text>"; }
    svg += '<text x="' + (W - mR) + '" y="' + (mT - 8) + '" text-anchor="end" font-size="10" fill="' + muted + '">' + esc(sm.expiry || "") + " · " + (sm.days != null ? sm.days + "d" : "") + "</text>";
    svg += "</svg>";
    host.innerHTML = svg + '<div class="legend"><span><i style="background:var(--up)"></i>' + lz("call IV", "看涨IV") + '</span><span><i style="background:var(--down)"></i>' + lz("put IV", "看跌IV") + "</span></div>";
  }

  function drawTerm() {
    var host = document.getElementById("gx-term"); if (!host) return;
    var tm = cur.term || [];
    if (tm.length < 2) { host.innerHTML = '<div class="muted sm">—</div>'; return; }
    var W = 540, H = 280, mL = 40, mR = 14, mT = 16, mB = 26;
    var xs = tm.map(function (r) { return r.days; }), ys = tm.map(function (r) { return r.atm_iv; });
    var xlo = Math.min.apply(null, xs), xhi = Math.max.apply(null, xs);
    var ylo = Math.min.apply(null, ys), yhi = Math.max.apply(null, ys);
    var yp = (yhi - ylo) * 0.15 || 1; ylo -= yp; yhi += yp; if (ylo < 0) ylo = 0;
    function X(v) { return mL + (v - xlo) / (xhi - xlo || 1) * (W - mL - mR); }
    function Y(v) { return mT + (yhi - v) / (yhi - ylo) * (H - mT - mB); }
    var info = cssv("--info"), text = cssv("--text"), muted = cssv("--muted"), line = cssv("--line");
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img">';
    for (var i = 0; i <= 4; i++) {
      var gv = ylo + (yhi - ylo) * i / 4, yy = Y(gv);
      svg += '<line x1="' + mL + '" y1="' + yy + '" x2="' + (W - mR) + '" y2="' + yy + '" stroke="' + line + '" stroke-width="0.5" opacity="0.4"/>';
      svg += '<text x="' + (mL - 5) + '" y="' + (yy + 3) + '" text-anchor="end" font-size="10" fill="' + muted + '">' + (+gv).toFixed(0) + "%</text>";
    }
    svg += polyline(xs, ys, X, Y, info, 1.8);
    tm.forEach(function (r) {
      svg += '<circle cx="' + X(r.days) + '" cy="' + Y(r.atm_iv) + '" r="2.6" fill="' + info + '"><title>' + esc(r.expiry) + " " + r.atm_iv + "%</title></circle>";
    });
    var step = Math.ceil(tm.length / 6);
    tm.forEach(function (r, i2) { if (i2 % step === 0 || i2 === tm.length - 1) svg += '<text x="' + X(r.days) + '" y="' + (H - mB + 14) + '" text-anchor="middle" font-size="9.5" fill="' + muted + '">' + r.days + "d</text>"; });
    svg += "</svg>";
    host.innerHTML = svg;
  }
  function polyline(xs, ys, X, Y, color, w) {
    var d = "", started = false;
    for (var i = 0; i < xs.length; i++) {
      if (ys[i] == null) { started = false; continue; }
      d += (started ? "L" : "M") + X(xs[i]).toFixed(1) + " " + Y(ys[i]).toFixed(1) + " "; started = true;
    }
    return '<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="' + w + '" stroke-linejoin="round"/>';
  }

  // ---- term table, cards, spark, caveat -----------------------------------
  function termTableHTML() {
    var tm = cur.term || []; if (!tm.length) return "";
    var rows = tm.map(function (r) {
      return "<tr><td>" + esc(r.expiry) + "</td><td>" + r.days + "</td><td>" + pctU(r.atm_iv, 1) + "</td><td>±" + pctU(r.move_pct, 1) +
        "</td><td>" + (r.straddle_pct == null ? "—" : "±" + pctU(r.straddle_pct, 1)) + "</td><td>" + price(r.max_pain) + "</td></tr>";
    }).join("");
    return '<div class="panel"><h2>' + lz("Expiry ladder — IV, expected move & max pain", "到期阶梯 — IV、预期波动与最大痛点") + "</h2>" +
      '<table class="term"><thead><tr><th>' + lz("Expiry", "到期") + "</th><th>" + lz("Days", "天数") + "</th><th>" + lz("ATM IV", "平值IV") +
      "</th><th>" + lz("IV move", "IV波动") + "</th><th>" + lz("Straddle", "跨式") + "</th><th>" + lz("Max pain", "最大痛点") + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }

  function cardsHTML() {
    var s = cur.summary;
    function c(k, v, sub) { return '<div class="gcard"><div class="k">' + k + '</div><div class="v">' + v + "</div>" + (sub ? '<div class="muted xs">' + sub + "</div>" : "") + "</div>"; }
    var cells = [
      c(lz("Call wall", "看涨墙"), price(s.call_wall)),
      c(lz("Put wall", "看跌墙"), price(s.put_wall)),
      c(lz("Largest OI", "最大未平仓"), price(s.largest_oi)),
      c(lz("Max pain", "最大痛点"), price(s.max_pain)),
      c(lz("Magnet ↑ / ↓", "磁吸 ↑ / ↓"), price(s.magnet_up) + " / " + price(s.magnet_down)),
      c("IV30", pctU(s.iv30, 1)),
      c(lz("Put/Call OI", "认沽/认购OI"), s.put_call_oi_ratio == null ? "—" : (+s.put_call_oi_ratio).toFixed(2)),
      c(lz("Put/Call vol", "认沽/认购量"), s.put_call_vol_ratio == null ? "—" : (+s.put_call_vol_ratio).toFixed(2)),
      c(lz("Net delta", "净Delta"), s.net_delta_bn == null ? "—" : sgn(s.net_delta_bn, 1) + " $bn"),
      c(lz("Net vanna", "净Vanna"), s.net_vex == null ? "—" : compact(s.net_vex)),
      c(lz("Charm bias", "Charm偏向"), s.charm_net_sign > 0 ? lz("↑ up-drift", "↑ 上漂") : s.charm_net_sign < 0 ? lz("↓ down-drift", "↓ 下漂") : "—", lz("anchor " + price(s.charm_anchor), "锚 " + price(s.charm_anchor))),
      c(lz("Chain", "链路"), (s.n_strikes || "—") + "", s.tier === "full" ? lz("deep", "深度") : lz("thin — fragile", "稀疏 — 脆弱"))
    ];
    return '<div class="panel"><h2>' + lz("Positioning summary", "持仓概览") + '</h2><div class="cards">' + cells.join("") + "</div></div>";
  }

  function drawSpark() {
    var host = document.getElementById("gx-spark"); if (!host) return;
    var h = (cur.history || []).filter(function (r) { return r.net_gex_bn != null; });
    if (h.length < 3) { host.innerHTML = ""; return; }
    var W = 150, H = 38, vals = h.map(function (r) { return r.net_gex_bn; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (lo > 0) lo = 0; if (hi < 0) hi = 0; var pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad;
    function X(i) { return 2 + i / (h.length - 1) * (W - 4); }
    function Y(v) { return 2 + (hi - v) / (hi - lo) * (H - 4); }
    var up = cssv("--up"), down = cssv("--down"), muted = cssv("--muted");
    var last = vals[vals.length - 1];
    var d = vals.map(function (v, i) { return (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1); }).join(" ");
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" style="vertical-align:middle">';
    svg += '<line x1="2" y1="' + Y(0) + '" x2="' + (W - 2) + '" y2="' + Y(0) + '" stroke="' + muted + '" stroke-width="0.5" opacity="0.5"/>';
    svg += '<path d="' + d + '" fill="none" stroke="' + (last >= 0 ? up : down) + '" stroke-width="1.4"/>';
    svg += '<circle cx="' + X(h.length - 1) + '" cy="' + Y(last) + '" r="2.2" fill="' + (last >= 0 ? up : down) + '"/></svg>';
    host.innerHTML = '<span class="heronum"><span class="muted sm">' + lz("GEX trend", "GEX走势") + " " + h.length + "d</span><br>" + svg + "</span>";
  }

  function caveatHTML() {
    var s = cur.summary, meta = cur.meta || {}, grp = meta.grp || "";
    if (grp === "Index" || grp.indexOf("ETF") >= 0) return "";
    return '<div class="panel"><p class="muted xs note" style="margin:0">' + lz(
      "Single-name caveat: the dealer long-call / short-put sign is FRAGILE here — concentration, covered-call ETFs or heavy retail call-buying can flip the true positioning. Top-strike OI share " + (s.top_oi_share == null ? "—" : s.top_oi_share) + ", chain tier “" + s.tier + "”. Read these as loose context, never a level to trade against.",
      "个股提示：此处“多头看涨/空头看跌”的做市商符号脆弱 — 集中度、备兑ETF或散户大量买看涨可翻转真实持仓。最大行权价OI占比 " + (s.top_oi_share == null ? "—" : s.top_oi_share) + "，链路等级“" + s.tier + "”。仅作宽松背景，切勿据此逆向交易。") + "</p></div>";
  }

  // ========================================================================
  // INIT + re-render on theme/lang change
  // ========================================================================
  function init() {
    renderBoard(); setupSearch(); setupChips(); setupBoardHelp();
    selectSymbol(window.GEX_DEFAULT || (M[0] && M[0].key));
  }
  ["langchange", "themechange"].forEach(function (e) {
    document.addEventListener(e, function () { renderBoard(); if (cur) renderDetail(); });
  });
  window.addEventListener("resize", function () { hideTip(); hideHelp(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

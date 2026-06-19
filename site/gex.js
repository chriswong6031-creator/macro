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
    if (r === "long") return lz("Long γ", "多头γ");
    if (r === "short") return lz("Short γ", "空头γ");
    return lz("Neutral", "中性");
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
          (s.regime === "long" ? lz("Long gamma · dealers fade / pins", "多头Gamma · 做市商抑制/磁吸")
            : s.regime === "short" ? lz("Short gamma · dealers chase / amplifies", "空头Gamma · 做市商追逐/放大")
            : lz("Neutral", "中性")) + "</span>" +
        '<span class="heronum big"><span class="muted sm">' + lz("Spot", "现价") + "</span> <b>" + price(s.spot) + "</b></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Net GEX", "净GEX") + '</span> <b class="' + (s.net_gex_bn >= 0 ? "pos" : "neg") + '">' + sgn(s.net_gex_bn, 1) + " $bn</b></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Gamma flip", "Gamma翻转") + "</span> <b>" + flipTxt + "</b></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Exp. daily move", "预期单日波动") + '</span> <b>±' + pctU(em.daily_pct, 2) + "</b> <span class='muted sm'>±" + price(em.daily_abs) + "</span></span>" +
        '<span class="heronum"><span class="muted sm">' + lz("Front-expiry move", "近月预期波动") + "</span> <b>" + frontMove + "</b></span>" +
        '<span id="gx-spark"></span>' +
      "</div>" + readLine() + rulerHTML() + "</div>";

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

  // ---- plain-English read --------------------------------------------------
  function readLine() {
    var s = cur.summary, em = cur.expected_move; if (!s) return "";
    var parts = [];
    if (s.regime === "short") parts.push(lz("<b>Short gamma</b> — dealers hedge <i>with</i> the move, so it tends to <b>amplify</b> (trending, higher realized vol)", "<b>空头Gamma</b> — 做市商<i>顺势</i>对冲，走势倾向<b>放大</b>（趋势化、已实现波动更高）"));
    else if (s.regime === "long") parts.push(lz("<b>Long gamma</b> — dealers hedge <i>against</i> the move, so it tends to be <b>dampened</b> (pinning / mean-reversion, lower realized vol)", "<b>多头Gamma</b> — 做市商<i>逆势</i>对冲，走势倾向<b>被抑制</b>（磁吸/均值回归、已实现波动更低）"));
    else parts.push(lz("<b>Neutral gamma</b> — no strong dealer-hedging tilt", "<b>中性Gamma</b> — 做市商对冲无明显倾向"));
    if (s.gamma_flip != null && s.dist_to_flip_pct != null) {
      var d = Math.abs(s.dist_to_flip_pct).toFixed(1);
      parts.push(lz("spot " + price(s.spot) + " is " + d + "% " + (s.dist_to_flip_pct >= 0 ? "above" : "below") + " the " + price(s.gamma_flip) + " flip", "现价 " + price(s.spot) + " 位于 " + price(s.gamma_flip) + " 翻转" + (s.dist_to_flip_pct >= 0 ? "上方" : "下方") + " " + d + "%"));
    }
    var w = [];
    if (s.call_wall != null) w.push(lz("the <b>" + price(s.call_wall) + "</b> call wall caps upside", "<b>" + price(s.call_wall) + "</b> 看涨墙压制上行"));
    if (s.put_wall != null) w.push(lz("the <b>" + price(s.put_wall) + "</b> put wall cushions downside", "<b>" + price(s.put_wall) + "</b> 看跌墙缓冲下行"));
    if (s.max_pain != null) w.push(lz(price(s.max_pain) + " max-pain", price(s.max_pain) + " 最大痛点"));
    if (w.length) parts.push(w.join(lz("; ", "；")));
    if (em && em.daily_pct != null) {
      var mv = lz("options price a <b>±" + em.daily_pct.toFixed(2) + "%/day</b> move", "期权定价 <b>±" + em.daily_pct.toFixed(2) + "%/日</b> 波动");
      if (em.front) mv += lz(" (±" + price(em.front.abs) + " by " + em.front.expiry + ")", "（至 " + em.front.expiry + " ±" + price(em.front.abs) + "）");
      parts.push(mv);
    }
    return '<div class="gx-read">' + parts.join(lz(". ", "。")) + (lang() === "zh" ? "。" : ".") + "</div>";
  }

  // ---- volatility hole (dealer-gamma compression band, DannyTrades framing) ----
  var VHS = {
    IN_HOLE:     { emo: "🕳️", en: "In the hole",           zh: "洞内",        cls: "neu",  sh_en: "In hole",   sh_zh: "洞内" },
    COILED_UP:   { emo: "⬆",  en: "Coiled · ceiling",      zh: "贴上沿蓄势",  cls: "up",   sh_en: "Coiled ↑",  sh_zh: "贴上沿" },
    COILED_DOWN: { emo: "⬇",  en: "Coiled · floor",        zh: "贴下沿承压",  cls: "down", sh_en: "Coiled ↓",  sh_zh: "贴下沿" },
    EXPANSION:   { emo: "🌪", en: "Expansion · black hole", zh: "扩张 · 黑洞", cls: "vol",  sh_en: "Expansion", sh_zh: "扩张" },
    NONE:        { emo: "·",  en: "No clear hole",          zh: "无明显洞",    cls: "na",   sh_en: "—",         sh_zh: "—" }
  };

  function vhCell(m) {
    if (!m.vh_state || m.vh_state === "NONE") return '<td><span class="vh-pill na">—</span></td>';
    var v = VHS[m.vh_state] || VHS.NONE;
    return '<td><span class="vh-pill ' + v.cls + '" title="' + esc(lz(v.en, v.zh)) + '">' + v.emo + " " + esc(lz(v.sh_en, v.sh_zh)) + "</span></td>";
  }

  function sigTxt(x) { return x == null ? "—" : (+x).toFixed(1) + "σ"; }

  function vhRead(vh, s) {
    var up = price(vh.upper), lo = price(vh.lower), flip = price(s.gamma_flip);
    var usrc = vh.upper_src === "call_wall" ? lz("call wall", "看涨墙") : lz("magnet", "磁吸位");
    var lsrc = vh.lower_src === "put_wall" ? lz("put wall", "看跌墙") : lz("magnet", "磁吸位");
    var su = sigTxt(vh.to_upper_sigma), sl = sigTxt(vh.to_lower_sigma);
    var bw = vh.band_width_pct, tu = vh.to_upper_pct, tl = vh.to_lower_pct;
    switch (vh.state) {
      case "IN_HOLE":
        return lz(
          "<b>Inside the hole.</b> Long gamma pins price between the <b>" + lo + "</b> " + lsrc + " floor and the <b>" + up + "</b> " + usrc + " ceiling" + (bw != null ? " (a <b>" + bw + "%</b>-wide band)" : "") + ". Spot sits " + sl + " above the floor and " + su + " below the ceiling — dealers fade moves, so expect chop / mean-reversion toward the magnets. The trigger is a <b>daily close</b> beyond a wall: through " + up + " releases upside (accumulate); through " + lo + " releases downside (de-risk).",
          "<b>洞内。</b> 多头Gamma将价格压在 <b>" + lo + "</b> " + lsrc + "下沿与 <b>" + up + "</b> " + usrc + "上沿之间" + (bw != null ? "（区间宽 <b>" + bw + "%</b>）" : "") + "。现价距下沿 " + sl + "、距上沿 " + su + " — 做市商抑制走势，预期在磁吸位之间震荡/均值回归。触发条件是<b>日线收盘</b>突破某墙：上破 " + up + " 释放上行（可加仓），下破 " + lo + " 释放下行（应减仓）。");
      case "COILED_UP":
        return lz(
          "<b>Coiled at the ceiling.</b> Spot is only " + su + " (~" + tu + "%) below the <b>" + up + "</b> " + usrc + " — the top edge of the long-gamma hole. A <b>daily close above " + up + "</b> unclenches dealer hedging and can accelerate up (the DannyTrades 'close above the upper boundary' = buy / accumulate). Until then the wall still caps and price tends to fade back inside.",
          "<b>贴近上沿蓄势。</b> 现价距 <b>" + up + "</b> " + usrc + " 仅 " + su + "（约 " + tu + "%）— 多头Gamma洞的上缘。<b>日线收于 " + up + " 之上</b>会松开做市商对冲、可能加速上行（即DannyTrades“收于上沿之上”=买入/加仓）。在此之前该墙仍压制，价格倾向回落洞内。");
      case "COILED_DOWN":
        return lz(
          "<b>Coiled at the floor.</b> Spot is only " + sl + " (~" + tl + "%) above the <b>" + lo + "</b> " + lsrc + ". A <b>daily close below " + lo + "</b> removes the cushion; losing the <b>" + flip + "</b> flip tips into short-gamma expansion where downside accelerates. Holding the floor keeps the pin intact.",
          "<b>贴近下沿承压。</b> 现价距 <b>" + lo + "</b> " + lsrc + " 仅 " + sl + "（约 " + tl + "%）。<b>日线收于 " + lo + " 之下</b>将失去缓冲；跌破 <b>" + flip + "</b> 翻转则进入空头Gamma扩张、下行加速。守住下沿则磁吸延续。");
      case "EXPANSION":
        return lz(
          "<b>Expansion — the black hole.</b> Spot is below the <b>" + flip + "</b> flip, in short gamma: dealers hedge WITH the move so realized vol <b>expands</b> (trends and air-pockets both run larger, downside-skewed). There is no suppressive hole until price <b>reclaims the " + flip + " flip</b> — size moves bigger and don't fade breaks the way you would inside a long-gamma hole.",
          "<b>扩张 — 黑洞。</b> 现价位于 <b>" + flip + "</b> 翻转之下、处于空头Gamma：做市商顺势对冲，已实现波动<b>放大</b>（趋势与急跌都更大，偏下行）。在价格<b>收复 " + flip + " 翻转</b>之前没有压制洞 — 应放大波动预期，勿像在多头Gamma洞内那样去做反向。");
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
      "The dealer-gamma map re-expressed as a 'volatility hole' (the DannyTrades idea, given a mechanism). LONG gamma is a suppressive band — dealers fade moves so price pins between the put-wall floor and call-wall ceiling. A daily CLOSE beyond a wall flips hedging pro-cyclical and releases the move. SHORT gamma (below the flip) is the 'black hole' where vol expands. Distances are in daily expected-move σ. Display-only — a relabeling of the flip / walls / expected move above, never a price target or a backtested signal.",
      "把做市商Gamma地图重新表述为“波动洞”（DannyTrades的概念，但带机制）。多头Gamma是压制区间 — 做市商抑制走势，价格被压在看跌墙下沿与看涨墙上沿之间。日线收盘突破某墙会使对冲转为顺势、释放走势。空头Gamma（翻转之下）即“黑洞”，波动放大。距离以单日预期波动σ计。仅供展示 — 是对上方翻转/墙/预期波动的重新表述，绝非目标价或回测信号。"));
    var head = '<div class="topline" style="justify-content:space-between;align-items:center"><h2 style="margin:0">' +
      lz("🕳️ Volatility Hole", "🕳️ 波动洞") + hHelp + '</h2><span class="vh-badge ' + v.cls + '">' + v.emo + " " + esc(lz(v.en, v.zh)) + "</span></div>";
    var caveat = '<p class="muted xs" style="margin:8px 0 0">' + lz(
      "Derived entirely from the gamma flip, walls and expected move above (EOD delayed Cboe) — a vol-regime relabeling, display-only. The dealer long-call / short-put sign is an assumption, fragile for single names; 'close' means the daily EOD level.",
      "完全由上方的Gamma翻转、墙与预期波动推导（Cboe延迟收盘数据）— 波动率体制的重新表述，仅供展示。做市商“多头看涨/空头看跌”符号为假设，对个股脆弱；“收盘”指每日收盘价位。") + "</p>";
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
    return [["gamma", lz("Net γ", "净γ")], ["oi", lz("Open interest", "未平仓")], ["vol", lz("Volume", "成交量")]]
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
    return [["gex", lz("Net γ", "净γ")], ["oi", lz("Open interest", "未平仓")], ["vol", lz("Volume", "成交量")]]
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
    var unit = heatMode === "gex" ? lz("$mn net γ", "百万$净γ") : heatMode === "oi" ? lz("contracts OI", "未平仓合约") : lz("contracts vol", "成交合约");
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
    var s = cur.summary, meta = cur.meta || {};
    if (meta.grp === "Index" || meta.grp === "ETF") return "";
    return '<div class="panel"><p class="muted xs note" style="margin:0">' + lz(
      "Single-name caveat: the dealer long-call / short-put sign is FRAGILE here — concentration, covered-call ETFs or heavy retail call-buying can flip the true positioning. Top-strike OI share " + (s.top_oi_share == null ? "—" : s.top_oi_share) + ", chain tier “" + s.tier + "”. Read these as loose context, never a level to trade against.",
      "个股提示：此处“多头看涨/空头看跌”的做市商符号脆弱 — 集中度、备兑ETF或散户大量买看涨可翻转真实持仓。最大行权价OI占比 " + (s.top_oi_share == null ? "—" : s.top_oi_share) + "，链路等级“" + s.tier + "”。仅作宽松背景，切勿据此逆向交易。") + "</p></div>";
  }

  // ========================================================================
  // INIT + re-render on theme/lang change
  // ========================================================================
  function init() {
    renderBoard(); setupSearch(); setupChips();
    selectSymbol(window.GEX_DEFAULT || (M[0] && M[0].key));
  }
  ["langchange", "themechange"].forEach(function (e) {
    document.addEventListener(e, function () { renderBoard(); if (cur) renderDetail(); });
  });
  window.addEventListener("resize", function () { hideTip(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

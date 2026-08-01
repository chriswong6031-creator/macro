/* gex.js — the interactive Options Desk (templates/gex.html.j2 + build_gex_board.py).
   Detail view: verdict hero → price ladder → three reads → flow → raw shelf.
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
  // group order as the manifest presents it (curated groups first, then themes) — used to
  // keep the Symbol sort grouped by theme rather than scattering groups alphabetically.
  var GROUP_ORDER = []; M.forEach(function (m) { if (GROUP_ORDER.indexOf(m.grp) < 0) GROUP_ORDER.push(m.grp); });
  var cache = {};               // key -> fetched payload (or null on miss)
  var cur = null;               // current model
  var curKey = null;
  var heatMode = "gex";         // gex | oi | vol
  var barMode = "gamma";        // gamma | oi | vol
  var boardSort = { key: "key", dir: 1 };   // default: grouped by theme
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

  // ---- shared label maps for the new scored signals (engine emits neutral KEYS) ----
  var BANDS = {
    very_strong: { en: "Very strong", zh: "极强" }, strong: { en: "Strong", zh: "强" },
    moderate: { en: "Moderate", zh: "中等" }, weak: { en: "Weak", zh: "弱" },
    faint: { en: "Faint", zh: "微弱" }
  };
  var HORIZONS = {
    intraday_days: { en: "Intraday → 1–2 days", zh: "日内至1–2日" },
    into_expiry: { en: "Into front expiry", zh: "至近月到期" },
    days_weeks: { en: "Days → ~2 weeks", zh: "数日至约两周" },
    days_regime: { en: "Days, while regime holds", zh: "数日 · 体制延续期间" }
  };
  var TONES = {
    fear: { en: "Puts bid · downside skew", zh: "看跌偏贵 · 下行偏斜", cls: "down", sh_en: "Fear", sh_zh: "恐慌" },
    greed: { en: "Calls bid · upside chase", zh: "看涨偏贵 · 上行追逐", cls: "up", sh_en: "Greed", sh_zh: "贪婪" },
    balanced: { en: "Balanced skew", zh: "偏斜均衡", cls: "neu", sh_en: "Balanced", sh_zh: "均衡" }
  };
  var IVRANK = {
    rich: { en: "Vol rich", zh: "波动偏贵", cls: "down" }, elevated: { en: "Elevated", zh: "偏高", cls: "warn" },
    normal: { en: "Normal", zh: "正常", cls: "neu" }, cheap: { en: "Cheap", zh: "偏低", cls: "up" },
    very_cheap: { en: "Very cheap", zh: "便宜", cls: "up" }
  };
  var READS = {
    agree_up: { en: "Leans higher", zh: "偏上行", cls: "up", arrow: "▲" },
    lean_up: { en: "Slight upward lean", zh: "轻微偏上", cls: "up", arrow: "▲" },
    agree_down: { en: "Leans lower", zh: "偏下行", cls: "down", arrow: "▼" },
    lean_down: { en: "Slight downward lean", zh: "轻微偏下", cls: "down", arrow: "▼" },
    pinned: { en: "Pinned to the magnet", zh: "磁吸钉住", cls: "pin", arrow: "●" },
    volatile: { en: "Two-sided / jumpy", zh: "双向 · 跳动", cls: "vol", arrow: "⇅" },
    mixed: { en: "Signals disagree", zh: "信号分歧", cls: "neu", arrow: "⚖" },
    balanced: { en: "Balanced", zh: "均衡", cls: "neu", arrow: "●" }
  };
  function bandWord(b) { var d = BANDS[b]; return d ? lz(d.en, d.zh) : ""; }
  function horizonText(key, days) {
    var d = HORIZONS[key]; if (!d) return "";
    if (key === "into_expiry" && days != null) return lz("Into front expiry (" + days + "d)", "至近月到期（" + days + "日）");
    return lz(d.en, d.zh);
  }
  function horizonPill(key, days) { return '<span class="hpill">' + esc(horizonText(key, days)) + "</span>"; }
  function levelVar(type) { return type === "cw" ? "--up" : type === "pw" ? "--down" : type === "mp" ? "--orange" : "--info"; }
  function strengthBar(strength, type) {
    if (strength == null) return "";
    var n = Math.max(0, Math.min(6, Math.round(strength / 100 * 6)));
    var c = "var(" + levelVar(type) + ")", out = "";
    for (var i = 0; i < 6; i++) out += '<i style="background:' + (i < n ? c : "var(--line)") + '"></i>';
    return '<span class="sbar" aria-label="' + strength + '/100">' + out + "</span>";
  }
  function strengthPill(band, type) {
    if (!band) return "";
    var col = (band === "very_strong" || band === "strong") ? "var(" + levelVar(type) + ")"
      : band === "moderate" ? "var(--orange)" : "var(--muted)";
    return '<span class="spill" style="color:' + col + ';border-color:' + col + '">' + esc(bandWord(band)) + "</span>";
  }

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
    lean: {
      t_en: "Lean — the timeframed tilt", t_zh: "倾向 — 带时间窗的方向",
      en: "A rough directional LEAN synthesised from the options legs (each acting on its own clock). “Up/Down” = the leans agree one way; “Pin” = pulled toward the max-pain magnet into expiry; “Jumpy” = short-gamma, swings both ways; “Mixed” = the leans disagree (no clear direction). It's a tendency from delayed positioning, NOT a trade signal or target — open the name to see each lean and its horizon.",
      zh: "由各期权分量（各有自己的时间窗）综合出的粗略方向倾向。“偏上/偏下”=各分量同向；“钉住”=临近到期被最大痛点磁吸；“跳动”=空头Gamma、双向波动；“分歧”=各分量不一致（无明确方向）。这是延迟仓位的倾向，并非交易信号或目标 — 点开标的可看每条分量及其时间窗。" },
    ivr: {
      t_en: "IVR — IV rank (short window)", t_zh: "IVR — IV分位（短窗）",
      en: "Where today's 30-day implied vol sits versus its OWN recent history — “Rich” = options are expensive (vol high vs lately), “Cheap” = options are inexpensive. NOTE: only ~40 trading days of history, so it's a SHORT-window rank, not a true 52-week IV rank. Blank when there isn't enough stored history yet.",
      zh: "今日30天隐含波动率相对其自身近期历史的位置 — “偏贵”=期权较贵（波动较近期偏高），“偏低”=期权较便宜。注意：仅约40个交易日历史，故为短窗分位、并非真正的52周IV分位。历史不足时留空。" },
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
  var COV = window.GEX_COVERAGE || {};
  var LEAN_SH = {
    agree_up: ["Up", "偏上"], lean_up: ["Up", "偏上"], agree_down: ["Down", "偏下"],
    lean_down: ["Down", "偏下"], pinned: ["Pin", "钉住"], volatile: ["Jumpy", "跳动"],
    mixed: ["Mixed", "分歧"], balanced: ["Flat", "均衡"]
  };
  function leanCell(m) {
    var r = READS[m.tilt_read]; if (!r) return "<td>—</td>";
    var col = r.cls === "up" ? "var(--up)" : r.cls === "down" ? "var(--down)"
      : (r.cls === "pin" || r.cls === "vol") ? "var(--orange)" : "var(--muted)";
    var sh = LEAN_SH[m.tilt_read] || [r.en, r.zh];
    return '<td style="color:' + col + ';white-space:nowrap" title="' + esc(lz(r.en, r.zh)) + '">' +
      r.arrow + " " + esc(lz(sh[0], sh[1])) + "</td>";
  }
  function ivrCell(m) {
    var d = IVRANK[m.iv_rank_band]; if (!d) return "<td>—</td>";
    var col = d.cls === "down" ? "var(--down)" : d.cls === "up" ? "var(--up)"
      : d.cls === "warn" ? "var(--orange)" : "var(--muted)";
    return '<td style="color:' + col + ';white-space:nowrap">' + esc(lz(d.en, d.zh)) + "</td>";
  }
  function renderBoard() {
    var tb = document.querySelector("#gx-board tbody");
    if (!tb) return;
    var cov = COV["__all__"];
    var covEl = document.getElementById("gx-coverage");
    if (covEl && cov) covEl.textContent = lz(
      cov.covered + " of " + cov.total + " symbols have liquid options",
      cov.total + " 个标的中 " + cov.covered + " 个有活跃期权");
    var rows = M.filter(function (m) { return grpFilter === "__all" || m.grp === grpFilter; });
    rows.sort(function (a, b) {
      var k = boardSort.key;
      // Symbol sort keeps groups contiguous (group order, then ticker) so theme sections render cleanly
      if (k === "key") {
        var ga = GROUP_ORDER.indexOf(a.grp), gb = GROUP_ORDER.indexOf(b.grp);
        if (ga !== gb) return (ga - gb) * boardSort.dir;
        return a.key < b.key ? -boardSort.dir : a.key > b.key ? boardSort.dir : 0;
      }
      var va = a[k], vb = b[k];
      if (k === "vh_state") {   // sort by vol-hole intensity, not raw string (string − string = NaN)
        var VR = { EXPANSION: 4, COILED_UP: 3, COILED_DOWN: 3, IN_HOLE: 2, NONE: 1 };
        return ((VR[a.vh_state] || 0) - (VR[b.vh_state] || 0)) * boardSort.dir;
      }
      if (k === "regime" || k === "tilt_read" || k === "iv_rank_band") {
        va = "" + (va || ""); vb = "" + (vb || ""); return va < vb ? -boardSort.dir : va > vb ? boardSort.dir : 0;
      }
      va = va == null ? -1e18 : va; vb = vb == null ? -1e18 : vb;
      return (va - vb) * boardSort.dir;
    });
    // group section headers preserved only when sorting by symbol or when "all"
    var html = "", lastGrp = null, grouped = (boardSort.key === "key");
    rows.forEach(function (m) {
      if (grouped && m.grp !== lastGrp) {
        var c = COV[m.grp];
        var covtxt = c ? ' <span class="cov">' + c.covered + "/" + c.total + "</span>" : "";
        html += '<tr class="ghead"><td colspan="11">' + esc(lz(m.grp, m.grp)) + covtxt + "</td></tr>"; lastGrp = m.grp;
      }
      var thinMk = m.thin ? '<span class="thinmk" title="' + esc(lz("chain too thin to trust the dealer sign", "期权链过薄，方向不可靠")) + '">◐</span>' : "";
      html += '<tr class="sym' + (m.key === curKey ? " sel" : "") + (m.thin ? " thin" : "") + '" data-key="' + m.key + '">' +
        '<td><span class="symk">' + esc(m.key) + "</span>" + thinMk + (m.en ? '<span class="symn">' + esc(lz(m.en, m.zh)) + "</span>" : "") + "</td>" +
        "<td>" + price(m.spot) + "</td>" +
        '<td><span class="reg ' + regClass(m.regime) + '">' + regWord(m.regime) + "</span></td>" +
        vhCell(m) + leanCell(m) +
        '<td class="' + (m.net_gex_bn >= 0 ? "pos" : "neg") + '">' + sgn(m.net_gex_bn, 1) + "</td>" +
        '<td class="' + (m.dist_to_flip_pct >= 0 ? "pos" : "neg") + '">' + pct(m.dist_to_flip_pct, 1) + "</td>" +
        "<td>" + pctU(m.iv30, 1) + "</td>" +
        ivrCell(m) +
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

  function setupBoardControls() {
    document.querySelectorAll("#gx-chips .chip").forEach(function (c) {
      c.addEventListener("click", function () {
        document.querySelectorAll("#gx-chips .chip").forEach(function (x) { x.classList.remove("on"); });
        c.classList.add("on"); grpFilter = c.getAttribute("data-grp"); renderBoard();
      });
    });
    var sub = document.getElementById("gx-board-cta-sub");
    var cov = COV["__all__"];
    if (sub && cov) sub.textContent = lz(
      cov.total + " symbols · sortable · scored", cov.total + " 个标的 · 可排序 · 已评分");
    var wrap = document.getElementById("gx-boardwrap"), cta = document.getElementById("gx-board-expand");
    if (!wrap || !cta) return;
    function open() { wrap.classList.remove("collapsed"); try { localStorage.setItem("gx_board_open", "1"); } catch (e) {} }
    function close() {
      wrap.classList.add("collapsed");
      try { localStorage.setItem("gx_board_open", "0"); } catch (e) {}
      try { cta.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) {}
    }
    cta.addEventListener("click", open);
    wrap.querySelectorAll(".board-collapse").forEach(function (b) { b.addEventListener("click", close); });
    var was = "0"; try { was = localStorage.getItem("gx_board_open") || "0"; } catch (e) {}
    wrap.classList[was === "1" ? "remove" : "add"]("collapsed");   // hidden on entry by default
  }

  // ========================================================================
  // LOAD + DETAIL
  // ========================================================================
  function selectSymbol(key) {
    if (!key) return;
    curKey = key;
    try { history.replaceState(null, "", "#" + key); } catch (e) {}
    pushRecent(key);
    renderBoard();
    loadFlow(key);
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

  // ========================================================================
  // DETAIL COMPOSITION — verdict hero → price ladder → three reads → flow →
  // raw-structure shelf. The workspace (.ws) carries the regime accent class.
  // ========================================================================
  var helpAnchor = null;          // current .help icon shown in the floating popover
  var QUICK = ["SPY", "QQQ", "SPX", "NVDA", "TSLA", "AAPL"];

  function renderDetail() {
    if (!cur) return;
    var box = document.getElementById("gx-detail");
    var ws = document.getElementById("gx-ws");
    var V = verdict();
    if (ws) { ws.classList.remove("gx-calm", "gx-jumpy", "gx-mixed"); ws.classList.add(V.cls); }
    box.innerHTML =
      heroHTML(V) +
      ladderCardHTML() +
      '<div class="reads">' + tapeReadHTML() + moodReadHTML() + leanReadHTML() + "</div>" +
      '<div id="gx-flow"></div>' +
      shelfHTML();
    drawLadder(); drawSpark(); drawIvSpark();
    drawBars(); drawProfile(); drawHeat(); drawSmile(); drawTerm();
    wireBarTabs(); wireHeatTabs();
    renderFlow();
    renderQuick();
  }

  function help(html) {
    return '<span class="help" tabindex="0" role="button" aria-label="What is this?">?<span class="tip">' + html + "</span></span>";
  }

  // ---- one floating popover for every "?" — never clipped by a card ----
  function setupHelpTips() {
    function show(h) {
      var t = h.querySelector(".tip"); if (!t) return;
      helpAnchor = h;
      var r = h.getBoundingClientRect();
      showHelp(t.innerHTML, r.left - 8, r.bottom - 10);
    }
    document.addEventListener("mouseover", function (e) {
      var h = e.target.closest && e.target.closest(".help");
      if (h && h !== helpAnchor) show(h);
      else if (!h && helpAnchor && !(e.target.closest && e.target.closest(".help-pop"))) { helpAnchor = null; hideHelp(); }
    });
    document.addEventListener("focusin", function (e) {
      var h = e.target.closest && e.target.closest(".help"); if (h) show(h);
    });
    document.addEventListener("focusout", function (e) {
      if (e.target.closest && e.target.closest(".help")) { helpAnchor = null; hideHelp(); }
    });
    window.addEventListener("scroll", function () { if (helpAnchor) { helpAnchor = null; hideHelp(); } }, { passive: true });
  }

  // ---- quick-pick chips: majors + recently viewed ----
  function recents() { try { return JSON.parse(localStorage.getItem("gx_recent") || "[]"); } catch (e) { return []; } }
  function pushRecent(k) {
    try {
      var r = recents().filter(function (x) { return x !== k; });
      r.unshift(k); localStorage.setItem("gx_recent", JSON.stringify(r.slice(0, 8)));
    } catch (e) {}
  }
  function renderQuick() {
    var host = document.getElementById("gx-quick"); if (!host) return;
    var keys = [], seen = {};
    QUICK.forEach(function (k) { if (BYKEY[k] && !seen[k]) { keys.push(k); seen[k] = 1; } });
    recents().forEach(function (k) { if (BYKEY[k] && !seen[k] && keys.length < 9) { keys.push(k); seen[k] = 1; } });
    host.innerHTML = keys.map(function (k) {
      return '<button type="button" class="qchip' + (k === curKey ? " on" : "") + '" data-k="' + esc(k) + '">' + esc(k) + "</button>";
    }).join("");
    host.querySelectorAll(".qchip").forEach(function (b) {
      b.addEventListener("click", function () { selectSymbol(b.getAttribute("data-k")); });
    });
  }

  // ---- the one-line verdict: regime × vol-hole → headline + plain say + stance ----
  function verdict() {
    var s = cur.summary || {}, vh = cur.vol_hole || {}, regime = s.regime, st = vh.state;
    var cw = price(s.call_wall), pw = price(s.put_wall);
    var lo = vh.lower != null ? price(vh.lower) : null, hi = vh.upper != null ? price(vh.upper) : null;
    if (regime === "short") return { cls: "gx-jumpy", icon: "⚡",
      h_en: "Jumpy — moves get amplified", h_zh: "跳动 — 波动被放大",
      s_en: "Dealer hedging is trading <b>with</b> the market today, so swings run larger and sell-offs can pick up speed. Don't assume dips get bought back the way they do on calm days.",
      s_zh: "今日做市商对冲<b>顺势</b>而行：波动更大、下跌可能加速。别指望回调像平静日那样被自动买回。",
      st_en: "Watch — don't chase", st_zh: "观察 — 勿追" };
    if (!regime) return { cls: "gx-mixed", icon: "⚖️",
      h_en: "Neutral — no strong dealer influence", h_zh: "中性 — 做市商影响不明显",
      s_en: "Hedging pressure is roughly balanced today, so the levels below matter less than usual. Let price action lead.",
      s_zh: "今日对冲力量大致均衡，下方价位的作用弱于平常。以盘面走势为准。",
      st_en: "Let the chart lead", st_zh: "以图表为准" };
    if (st === "COILED_UP") return { cls: "gx-calm", icon: "⬆",
      h_en: "Calm, pressed against the ceiling", h_zh: "平静 · 紧贴上沿",
      s_en: "Price is pinned just under the <b>" + cw + "</b> call wall. Pushes like this usually stall — unless a full day <b>closes above " + cw + "</b>, which can unlock a faster move higher.",
      s_zh: "价格贴在 <b>" + cw + "</b> 看涨墙之下。这种上顶通常会停滞 — 除非日线<b>收于 " + cw + " 之上</b>，才可能放行更快的上涨。",
      st_en: "Watch the ceiling", st_zh: "盯住上沿" };
    if (st === "COILED_DOWN") return { cls: "gx-calm", icon: "⬇",
      h_en: "Calm, pressed against the floor", h_zh: "平静 · 紧贴下沿",
      s_en: "Price is sitting just above the <b>" + pw + "</b> put wall. The floor usually holds — but a full day <b>closing below " + pw + "</b> removes that cushion and can speed up the drop.",
      s_zh: "价格停在 <b>" + pw + "</b> 看跌墙之上。下沿通常守得住 — 但日线<b>收于 " + pw + " 之下</b>会撤走缓冲、可能加速下跌。",
      st_en: "Watch the floor", st_zh: "盯住下沿" };
    if (st === "IN_HOLE" && lo && hi) return { cls: "gx-calm", icon: "🧲",
      h_en: "Calm — pinned between the walls", h_zh: "平静 — 被钉在两墙之间",
      s_en: "Dealer hedging is absorbing moves, so price tends to drift back toward the middle of the <b>" + lo + "–" + hi + "</b> band. Expect a range, not a trend.",
      s_zh: "做市商对冲在吸收波动：价格倾向回到 <b>" + lo + "–" + hi + "</b> 区间中部。预期震荡区间，而非趋势。",
      st_en: "Range day — edges usually hold", st_zh: "区间日 — 边沿通常守住" };
    return { cls: "gx-calm", icon: "🧲",
      h_en: "Calm — moves get absorbed", h_zh: "平静 — 波动被吸收",
      s_en: "Dealer hedging is leaning against moves today, but no firm walls are mapped. Lean on the chart and the expected range below.",
      s_zh: "今日做市商对冲逆势而行，但没有明确的墙。参考图表与下方预期区间。",
      st_en: "Watch — don't chase", st_zh: "观察 — 勿追" };
  }

  // ---- "how long has this regime held" — from the daily history ----
  function regimeChange() {
    var h = (cur.history || []).filter(function (r) { return r.regime; });
    if (h.length < 2) return null;
    var last = h[h.length - 1].regime, days = 0, i;
    for (i = h.length - 1; i >= 0; i--) { if (h[i].regime === last) days++; else break; }
    var prior = null;
    for (var j = h.length - 1 - days; j >= 0; j--) { if (h[j].regime) { prior = h[j].regime; break; } }
    return { reg: last, days: days, prior: prior, flipped: !!(prior && prior !== last && days <= 3) };
  }

  // ---- HERO ----
  function heroHTML(V) {
    var s = cur.summary || {}, em = cur.expected_move || {}, meta = cur.meta || {}, grp = meta.grp || "";
    var chips = '<span class="stance"><span class="bd"></span>' + esc(lz(V.st_en, V.st_zh)) + "</span>";
    if (em.daily_pct != null && s.spot != null) {
      var lo = s.spot * (1 - em.daily_pct / 100), hi = s.spot * (1 + em.daily_pct / 100);
      chips += '<span class="hchip tabnum"><span class="k">' + lz("Expected today", "今日预期") + "</span><b>" +
        price(lo) + "–" + price(hi) + '</b><span class="muted xs">±' + em.daily_pct.toFixed(2) + "%</span>" +
        help(lz("From option prices: about a 2-in-3 chance today's close lands inside this band. A symmetric range — not a direction call and not a limit.",
                "由期权价格推得：今日收盘约有三分之二的概率落在此区间内。对称区间 — 非方向判断、非涨跌上限。")) + "</span>";
    }
    var rc = regimeChange();
    if (rc) {
      var wEn = rc.reg === "long" ? "calm" : rc.reg === "short" ? "jumpy" : "mixed";
      var wZh = rc.reg === "long" ? "平静" : rc.reg === "short" ? "跳动" : "中性";
      var cEn = rc.flipped
        ? "Flipped " + wEn + " " + rc.days + (rc.days === 1 ? " session ago" : " sessions ago")
        : wEn.charAt(0).toUpperCase() + wEn.slice(1) + " for " + rc.days + (rc.days === 1 ? " session" : " sessions");
      var cZh = rc.flipped ? "转为" + wZh + "已 " + rc.days + " 个交易日" : wZh + "已持续 " + rc.days + " 个交易日";
      chips += '<span class="hchip">' + esc(lz(cEn, cZh)) + "</span>";
    }
    if (grp !== "Index" && grp.indexOf("ETF") < 0) {
      chips += '<span class="hchip warn">⚠ ' + esc(lz("Single stock — treat levels loosely", "个股 — 价位仅作宽松参考")) +
        help(lz("For single stocks the dealer-positioning math relies on an assumption that often breaks (covered-call funds, heavy retail call-buying can flip it). Indices and big ETFs are far more reliable. Top-strike OI share " + (s.top_oi_share == null ? "—" : s.top_oi_share) + " · chain depth: " + (s.tier === "full" ? "deep" : "thin") + ".",
                "个股的做市商持仓推算依赖常被打破的假设（备兑基金、散户大量买购都可使其翻转）。指数与大型ETF可靠得多。最大行权价OI占比 " + (s.top_oi_share == null ? "—" : s.top_oi_share) + " · 链路深度：" + (s.tier === "full" ? "深" : "薄") + "。")) + "</span>";
    }
    // Live continuation: this board is settled EOD data, the Terminal is the live view of
    // the same name. Built through theme.js's shared MDXTerminal.url() so the &ret= stamp
    // matches every other macro deep link and the Terminal's "← Dashboard" button returns
    // here. location.href already carries #TICKER — selectSymbol replaceStates the hash
    // before renderDetail runs. The literal fallback mirrors that builder exactly, for the
    // case where theme.js has not evaluated yet.
    var termKey = meta.key || curKey;
    if (termKey) {
      var termUrl = (window.MDXTerminal && window.MDXTerminal.url)
        ? window.MDXTerminal.url(termKey)
        : "https://app.mastermind-x.com/terminal?sym=" + encodeURIComponent(termKey) +
          "&from=macro&ret=" + encodeURIComponent(location.href);
      chips += '<a class="hchip gx-term" href="' + esc(termUrl) + '" rel="noopener">' +
        esc(lz("Open live in Terminal", "在终端实时查看")) +
        '<span class="gx-term-ar" aria-hidden="true">↗</span></a>';
    }
    chips += '<span class="hasof"><span class="bd"></span>' + esc(lz("EOD · delayed", "延迟收盘数据")) + "</span>";
    return '<div class="card anim">' +
      '<div class="hero-top">' +
        '<div class="hid"><span class="sym">' + esc(meta.key || curKey) + "</span>" +
          (meta.en ? '<span class="nm">' + esc(lz(meta.en, meta.zh)) + "</span>" : "") +
          '<span class="tag">' + esc(lz(grp, grp)) + " · " + esc(lz("as of ", "截至 ")) + esc(meta.asof || "") + "</span></div>" +
        '<div class="hspot"><span class="k">' + lz("Last close", "最新收盘") + '</span><span class="v tabnum">' + price(s.spot) + "</span></div>" +
      "</div>" +
      '<div class="hv"><span class="hv-ic">' + V.icon + "</span>" +
        '<div><div class="hv-h">' + esc(lz(V.h_en, V.h_zh)) + "</div>" +
        '<div class="hv-s">' + lz(V.s_en, V.s_zh) + "</div></div></div>" +
      '<div class="hchips">' + chips + "</div>" +
    "</div>";
  }

  // ========================================================================
  // PRICE LADDER — walls, flip, magnet, expected range on one horizontal axis
  // ========================================================================
  function levelList() {
    var s = cur.summary || {}, regime = s.regime, out = [];
    if (s.call_wall != null) {
      out.push({ cls: "cw", v: s.call_wall, str: s.call_wall_strength, band: s.call_wall_band, hard: s.call_wall_hard, sigma: s.call_wall_dist_sigma,
        n_en: "Ceiling — call wall", n_zh: "上沿 — 看涨墙", sh_en: "ceiling", sh_zh: "上沿",
        why_en: "Rallies tend to stall into this wall. Only a daily <b>close above " + price(s.call_wall) + "</b> opens the upside.",
        why_zh: "上涨往往在此受阻。只有日线<b>收于 " + price(s.call_wall) + " 之上</b>才打开上行空间。" });
    } else if (s.magnet_up != null) {
      out.push({ cls: "cw", v: s.magnet_up, n_en: "Soft ceiling", n_zh: "软上沿", sh_en: "ceiling", sh_zh: "上沿",
        why_en: "The heaviest dealer positioning above — a softer lid than a true wall.",
        why_zh: "上方做市商持仓最重处 — 比真正的墙更松的盖子。" });
    }
    if (s.gamma_flip != null) {
      var d = s.dist_to_flip_pct, side_en = "", side_zh = "";
      if (d != null) {
        var ab = d >= 0;
        side_en = " Price is " + pctU(Math.abs(d), 1) + " " + (ab ? "above" : "below") + " it — on the " + (ab ? "calm" : "jumpy") + " side.";
        side_zh = " 价格在其" + (ab ? "上" : "下") + "方 " + pctU(Math.abs(d), 1) + " — 处于" + (ab ? "平静" : "跳动") + "一侧。";
      }
      out.push({ cls: "flip", v: s.gamma_flip, str: s.flip_strength, band: s.flip_band, sh_en: "flip", sh_zh: "翻转",
        n_en: "Flip — the regime line", n_zh: "翻转 — 体制分界线",
        why_en: "Calm above this line, jumpy below." + side_en,
        why_zh: "线上平静、线下跳动。" + side_zh });
    }
    if (s.max_pain != null) {
      var wk = regime === "short";
      out.push({ cls: "mp", v: s.max_pain, str: s.magnet_strength, band: s.magnet_band, sigma: s.magnet_dist_sigma, sh_en: "magnet", sh_zh: "磁吸",
        n_en: "Magnet — max pain", n_zh: "磁吸 — 最大痛点",
        why_en: "On quiet days hedging drifts price toward this level into expiry." + (wk ? " The pull is weak while the tape is jumpy." : ""),
        why_zh: "平静日对冲会在临近到期时把价格拖向此处。" + (wk ? "跳动体制下这种磁吸较弱。" : "") });
    }
    if (s.put_wall != null) {
      var thin = (regime === "short" && s.gamma_flip != null);
      out.push({ cls: "pw", v: s.put_wall, str: s.put_wall_strength, band: s.put_wall_band, hard: s.put_wall_hard, sigma: s.put_wall_dist_sigma,
        n_en: "Floor — put wall", n_zh: "下沿 — 看跌墙", sh_en: "floor", sh_zh: "下沿",
        why_en: "Sell-offs tend to slow into this wall. A daily <b>close below " + price(s.put_wall) + "</b> pulls that cushion away" +
          (thin ? " — and with price already below the flip, the cushion is thinner than usual." : "."),
        why_zh: "下跌往往在此放缓。日线<b>收于 " + price(s.put_wall) + " 之下</b>将撤走缓冲" + (thin ? " — 且价格已在翻转线之下，缓冲本就偏薄。" : "。") });
    } else if (s.magnet_down != null) {
      out.push({ cls: "pw", v: s.magnet_down, n_en: "Soft floor", n_zh: "软下沿", sh_en: "floor", sh_zh: "下沿",
        why_en: "The heaviest dealer positioning below — a softer cushion than a true wall.",
        why_zh: "下方做市商持仓最重处 — 比真正的墙更松的缓冲。" });
    }
    out.sort(function (a, b) { return b.v - a.v; });
    return out;
  }
  function levelTip(p) {
    var bits = [];
    if (p.str != null) bits.push(lz("strength " + p.str + "/100" + (p.band ? " — " + bandWord(p.band) : ""),
                                    "强度 " + p.str + "/100" + (p.band ? " — " + bandWord(p.band) : "")));
    if (p.hard === true) bits.push(lz("one dominant strike — a hard line", "单一主导行权价 — 界线清晰"));
    else if (p.hard === false) bits.push(lz("spread across nearby strikes — treat it as a zone", "分散于邻近行权价 — 视作一个区域"));
    if (p.sigma != null) bits.push(lz(p.sigma + "σ from the last close", "距最新收盘 " + p.sigma + "σ"));
    var base = lz("The score blends how much dealer gamma clusters at the level and how close it is. Display-only context — never a target.",
                  "评分综合该价位的Gamma聚集程度与距离。仅供展示的背景 — 绝非目标价。");
    return (bits.length ? "<b>" + bits.join(" · ") + "</b><br>" : "") + base;
  }
  function strengthDots(str, colorVar) {
    if (str == null) return "";
    var n = Math.max(0, Math.min(6, Math.round(str / 100 * 6))), out = "";
    for (var i = 0; i < 6; i++) out += '<i style="background:' + (i < n ? "var(" + colorVar + ")" : "var(--line)") + '"></i>';
    return '<span class="lstr" aria-label="' + str + '/100">' + out + "</span>";
  }
  function ladderCardHTML() {
    var L = levelList(), s = cur.summary || {}, vh = cur.vol_hole || {};
    var headHelp = help(lz("One picture of where dealer hedging concentrates, on a price axis (low → high, like a chart). Colored bands are the walls — taller means stronger. The dashed line is the flip between the calm and jumpy regimes. The ring is the expiry magnet. The horizontal strip on the axis is today's expected range — you can see at a glance whether it collides with a wall. Levels to watch, never targets.",
      "做市商对冲集中位置的单幅图，横轴为价格（左低右高，与图表一致）。色带是墙 — 越高越强。虚线是平静/跳动体制的翻转分界。圆圈是到期磁吸位。轴上的横条是今日预期区间 — 一眼即可看出它是否会撞上某面墙。仅供观察，绝非目标价。"));
    var badge = "";
    if (vh.state && vh.state !== "NONE") {
      var v = VHS[vh.state] || VHS.NONE;
      badge = '<span class="vh-pill ' + v.cls + '">' + v.emo + " " + esc(lz(v.en, v.zh)) + "</span>";
    }
    if (L.length < 2) {
      return '<div class="card anim d1"><div class="cardhead"><span class="kick">📍 ' + lz("The map — where dealer hedging sits", "地图 — 做市商对冲所在") + "</span>" + headHelp + badge + "</div>" +
        '<p class="lad-empty">' + esc(lz("No reliable walls mapped for this name today — lean on the chart and the expected range above.", "今日该标的没有可靠的墙 — 参考图表与上方预期区间。")) + "</p></div>";
    }
    var clsVar = { cw: "--up", pw: "--down", flip: "--info", mp: "--orange" };
    var spot = s.spot;
    var rows = L.map(function (p) {
      var dist = "";
      if (spot != null) {
        var d = (p.v - spot) / spot * 100;
        dist = '<span class="ldist tabnum"><b class="' + (d >= 0 ? "pos" : "neg") + '">' + pct(d, 1) + "</b> " + lz("from close", "距收盘") + "</span>";
      }
      return '<div class="lrow ' + p.cls + '"><span class="ldot"></span>' +
        '<span class="lname">' + esc(lz(p.n_en, p.n_zh)) + strengthDots(p.str, clsVar[p.cls]) + help(levelTip(p)) + "</span>" +
        dist +
        '<span class="lprice tabnum">' + price(p.v) + "</span>" +
        '<div class="lwhy">' + lz(p.why_en, p.why_zh) + "</div></div>";
    }).join("");
    var em = cur.expected_move || {};
    var key = '<div class="lad-key">' +
      '<span><i style="background:var(--up);opacity:.55"></i>' + lz("ceiling (call wall)", "上沿（看涨墙）") + "</span>" +
      '<span><i style="background:var(--down);opacity:.55"></i>' + lz("floor (put wall)", "下沿（看跌墙）") + "</span>" +
      (s.gamma_flip != null ? '<span><i style="background:transparent;border-top:2px dashed var(--info);height:0"></i>' + lz("flip line", "翻转线") + "</span>" : "") +
      (s.max_pain != null ? '<span><i style="background:transparent;border:2px solid var(--orange);border-radius:50%;width:9px;height:9px"></i>' + lz("magnet", "磁吸") + "</span>" : "") +
      (em.daily_pct != null ? '<span><i style="background:var(--info);opacity:.4;border-radius:4px"></i>' + lz("expected range today", "今日预期区间") + "</span>" : "") +
      '<span><i style="background:var(--text);border-radius:50%;width:9px;height:9px"></i>' + lz("last close", "最新收盘") + "</span>" +
    "</div>";
    var foot = '<p class="lad-foot">' + lz(
      "Walls are measured from yesterday's close, so price always starts inside the band. Only a <b>full day's close</b> beyond a level counts — an intraday poke doesn't.",
      "墙以昨日收盘计算，价格开盘时必然在带内。只有<b>日线收盘</b>越过某价位才算数 — 盘中触碰不算。") + "</p>";
    return '<div class="card anim d1"><div class="cardhead"><span class="kick">📍 ' + lz("The map — where dealer hedging sits", "地图 — 做市商对冲所在") + "</span>" + headHelp + badge + "</div>" +
      '<div class="lad" id="gx-ladder"></div>' + key +
      '<div class="lrows">' + rows + "</div>" + foot + "</div>";
  }
  function drawLadder() {
    var host = document.getElementById("gx-ladder"); if (!host || !cur) return;
    var s = cur.summary || {}, em = cur.expected_move || {};
    var L = levelList(), spot = s.spot, flip = s.gamma_flip;
    var pts = L.map(function (p) { return p.v; });
    if (spot != null) pts.push(spot);
    var rlo = null, rhi = null;
    if (em.daily_pct != null && spot != null) {
      rlo = spot * (1 - em.daily_pct / 100); rhi = spot * (1 + em.daily_pct / 100);
      pts.push(rlo, rhi);
    }
    if (pts.length < 2) { host.innerHTML = ""; return; }
    var lo = Math.min.apply(null, pts), hi = Math.max.apply(null, pts);
    var pad = (hi - lo) * 0.07 || 1; lo -= pad; hi += pad;
    var w = Math.max(320, host.clientWidth || 640), H = 170, mX = 14, AX = 92;
    function X(v) { return mX + (v - lo) / (hi - lo) * (w - 2 * mX); }
    var up = cssv("--up"), down = cssv("--down"), info = cssv("--info"), orange = cssv("--orange"),
        text = cssv("--text"), muted = cssv("--muted"), line = cssv("--line");
    var svg = '<svg viewBox="0 0 ' + w + " " + H + '" role="img" aria-label="' + esc(lz("price map of dealer levels", "做市商价位图")) + '">';
    // regime tint: jumpy side below the flip (left), calm side above (right)
    if (flip != null) {
      var xf = X(flip);
      svg += '<rect x="' + mX + '" y="26" width="' + Math.max(0, xf - mX).toFixed(1) + '" height="' + (AX - 26) + '" fill="' + down + '" opacity="0.055"/>';
      svg += '<rect x="' + xf.toFixed(1) + '" y="26" width="' + Math.max(0, (w - mX) - xf).toFixed(1) + '" height="' + (AX - 26) + '" fill="' + up + '" opacity="0.05"/>';
      if (xf - mX > 76) svg += '<text x="' + (xf - 9).toFixed(1) + '" y="38" text-anchor="end" font-size="9" fill="' + muted + '">' + esc(lz("jumpy side", "跳动侧")) + "</text>";
      if ((w - mX) - xf > 76) svg += '<text x="' + (xf + 9).toFixed(1) + '" y="38" font-size="9" fill="' + muted + '">' + esc(lz("calm side", "平静侧")) + "</text>";
    }
    // expected range strip on the axis
    if (rlo != null) svg += '<rect x="' + X(rlo).toFixed(1) + '" y="' + (AX - 4) + '" width="' + (X(rhi) - X(rlo)).toFixed(1) + '" height="8" rx="4" fill="' + info + '" opacity="0.32"/>';
    // axis
    svg += '<line x1="' + mX + '" y1="' + AX + '" x2="' + (w - mX) + '" y2="' + AX + '" stroke="' + line + '" stroke-width="1.5"/>';
    var labs = [];
    L.forEach(function (p) {
      var x = X(p.v), col = p.cls === "cw" ? up : p.cls === "pw" ? down : p.cls === "flip" ? info : orange;
      if (p.cls === "cw" || p.cls === "pw") {
        var hgt = 26 + (p.str != null ? p.str / 100 * 40 : 16);
        svg += '<rect x="' + (x - 6).toFixed(1) + '" y="' + (AX - hgt).toFixed(1) + '" width="12" height="' + hgt.toFixed(1) + '" rx="4" fill="' + col + '" opacity="0.30"/>';
        svg += '<line x1="' + x.toFixed(1) + '" y1="' + (AX - hgt).toFixed(1) + '" x2="' + x.toFixed(1) + '" y2="' + AX + '" stroke="' + col + '" stroke-width="2.2"/>';
      } else if (p.cls === "flip") {
        svg += '<line class="lad-flip" x1="' + x.toFixed(1) + '" y1="26" x2="' + x.toFixed(1) + '" y2="' + (AX + 10) + '" stroke="' + info + '" stroke-width="1.6" stroke-dasharray="5 4"/>';
      } else {
        svg += '<circle cx="' + x.toFixed(1) + '" cy="' + AX + '" r="5.5" fill="none" stroke="' + orange + '" stroke-width="2"/>';
      }
      labs.push({ x: x, col: col, p: price(p.v), n: lz(p.sh_en, p.sh_zh) });
    });
    if (spot != null) {
      var xs = X(spot);
      svg += '<line x1="' + xs.toFixed(1) + '" y1="20" x2="' + xs.toFixed(1) + '" y2="' + (AX + 8) + '" stroke="' + text + '" stroke-width="1" stroke-dasharray="2 3" opacity="0.8"/>';
      svg += '<circle class="lad-halo" cx="' + xs.toFixed(1) + '" cy="' + AX + '" r="10" fill="' + text + '" opacity="0.14"/>';
      svg += '<circle cx="' + xs.toFixed(1) + '" cy="' + AX + '" r="4.5" fill="' + text + '"/>';
      var sx = Math.min(w - 48, Math.max(48, xs));
      svg += '<text x="' + sx.toFixed(1) + '" y="12" text-anchor="middle" font-size="11" font-weight="800" fill="' + text + '">' + price(spot) + "</text>";
      svg += '<text x="' + sx.toFixed(1) + '" y="23" text-anchor="middle" font-size="8.5" fill="' + muted + '">' + esc(lz("last close", "最新收盘")) + "</text>";
    }
    labs.sort(function (a, b) { return a.x - b.x; });
    var lastX = [-1e9, -1e9], GAP = 62;
    labs.forEach(function (l) {
      var lane = (l.x - lastX[0] >= GAP) ? 0 : (l.x - lastX[1] >= GAP) ? 1 : (lastX[0] <= lastX[1] ? 0 : 1);
      l.lane = lane; lastX[lane] = Math.max(lastX[lane], l.x);
    });
    labs.forEach(function (l) {
      var y = l.lane ? 141 : 115, x = Math.min(w - 30, Math.max(30, l.x));
      svg += '<text x="' + x.toFixed(1) + '" y="' + y + '" text-anchor="middle" font-size="11" font-weight="700" fill="' + l.col + '">' + l.p + "</text>";
      if (l.n) svg += '<text x="' + x.toFixed(1) + '" y="' + (y + 11) + '" text-anchor="middle" font-size="8.5" fill="' + muted + '">' + esc(l.n) + "</text>";
    });
    svg += "</svg>";
    host.innerHTML = svg;
  }

  // ========================================================================
  // THREE READS — the tape · the mood · the lean
  // ========================================================================
  function tapeReadHTML() {
    var s = cur.summary || {}, regime = s.regime;
    var word = regime === "long" ? lz("Calm", "平静") : regime === "short" ? lz("Jumpy", "跳动") : lz("Neutral", "中性");
    var cls = regime === "long" ? "up" : regime === "short" ? "down" : "info";
    var sub = regime === "long" ? lz("Dealer hedging pushes back against moves — price tends to pin and mean-revert.", "做市商对冲逆势而行 — 价格倾向被钉住、均值回归。")
      : regime === "short" ? lz("Dealer hedging adds to moves — swings and air-pockets run bigger than usual.", "做市商对冲顺势而行 — 波动与急跌比平常更大。")
      : lz("No clear dealer lean today — hedging pressure is roughly balanced.", "今日做市商无明显倾向 — 对冲力量大致均衡。");
    var netCls = (s.net_gex_bn != null && s.net_gex_bn >= 0) ? "pos" : "neg";
    var foot = "";
    if (s.gamma_flip != null && s.dist_to_flip_pct != null) {
      var ab = s.dist_to_flip_pct >= 0;
      foot = '<div class="rfoot">' + esc(lz(
        "The regime switches at the " + price(s.gamma_flip) + " flip — price is " + pctU(Math.abs(s.dist_to_flip_pct), 1) + " " + (ab ? "above" : "below") + " it.",
        "体制在 " + price(s.gamma_flip) + " 翻转处切换 — 价格在其" + (ab ? "上" : "下") + "方 " + pctU(Math.abs(s.dist_to_flip_pct), 1) + "。")) + "</div>";
    }
    return '<div class="card read anim d2"><div class="cardhead"><span class="kick">' + lz("The tape — calm or jumpy?", "盘面 — 平静还是跳动？") +
      "</span>" + help(lz("The single most important read on this page, and it's about volatility, not direction. Positive net GEX = dealers hedge against moves (calmer, pinning). Negative = they hedge with moves (bigger swings). Net GEX is the size of that hedging per 1% move, in billions of dollars — don't compare the raw number across different names.",
        "本页最重要的读数，而且它关乎波动、不关乎方向。净GEX为正 = 做市商逆势对冲（更平静、磁吸）；为负 = 顺势对冲（波动更大）。净GEX是每1%波动对应的对冲规模（十亿美元）— 不同标的之间不要直接比较原始数值。")) + "</div>" +
      '<div class="rhead ' + cls + '">' + word + "</div>" +
      '<div class="rsub">' + sub + "</div>" +
      '<div class="rmet"><b class="' + netCls + ' tabnum">' + sgn(s.net_gex_bn, 1) + '</b><span class="u">' + lz("$bn of dealer hedging per 1% move (net GEX)", "每1%波动对应的对冲规模（净GEX，十亿$）") + "</span></div>" +
      regimeStrip() +
      '<div class="rspark" id="gx-spark"></div>' +
      foot + "</div>";
  }
  function regimeStrip() {
    var h = (cur.history || []).slice(-30).filter(function (r) { return r.regime != null; });
    if (h.length < 5) return "";
    var cells = h.map(function (r) {
      var c = r.regime === "long" ? "var(--up)" : r.regime === "short" ? "var(--down)" : "var(--g-mid)";
      return '<i style="background:' + c + '" title="' + esc(r.date || "") + '"></i>';
    }).join("");
    return '<div class="rgs">' + cells + "</div>" +
      '<div class="rgs-cap"><span><i style="background:var(--up)"></i>' + lz("calm", "平静") + "</span>" +
      '<span><i style="background:var(--down)"></i>' + lz("jumpy", "跳动") + "</span>" +
      "<span>" + esc(lz("last " + h.length + " sessions", "近 " + h.length + " 个交易日")) + "</span></div>";
  }
  function moodReadHTML() {
    var s = cur.summary || {}, sk = s.skew, em = cur.expected_move || {}, ivr = s.iv_rank;
    var kick = '<div class="cardhead"><span class="kick">' + lz("The mood — what options cost", "情绪 — 期权贵不贵") + "</span>" +
      help(lz("Read from option prices. IV30 is the expected 30-day volatility priced into options — the cost of protection. The 25Δ skew compares equally-far puts vs calls: puts pricier = fear, calls pricier = chasing upside. Context, not a signal.",
        "由期权价格读出。IV30 是期权定价隐含的30天预期波动率 — 保护的成本。25Δ偏斜比较等距的看跌与看涨：看跌更贵 = 恐慌；看涨更贵 = 追逐上行。仅作背景，非信号。")) + "</div>";
    var word, cls, sub;
    if (sk && sk.rr25 != null) {
      word = sk.tone === "fear" ? lz("Fear", "恐慌") : sk.tone === "greed" ? lz("Greed", "贪婪") : lz("Balanced", "均衡");
      cls = sk.tone === "fear" ? "down" : sk.tone === "greed" ? "up" : "info";
      sub = sk.tone === "fear" ? lz("The market is paying a premium for downside protection.", "市场在为下行保护支付溢价。")
        : sk.tone === "greed" ? lz("Calls are bid over puts — the market is chasing upside.", "看涨比看跌更贵 — 市场在追逐上行。")
        : lz("Puts and calls are priced roughly evenly.", "看跌与看涨定价大致均衡。");
    } else {
      word = lz("No skew read", "无偏斜读数"); cls = "info";
      sub = lz("Not enough strikes to read the put/call skew for this name.", "该标的行权价不足，无法读取偏斜。");
    }
    var ivrHtml = "";
    if (ivr) {
      if (ivr.low_confidence) {
        ivrHtml = '<span class="ivr-building">' + esc(lz("history building — " + (ivr.n_days || "?") + "d", "历史积累中 — " + (ivr.n_days || "?") + "天")) + "</span>";
      } else {
        var d = IVRANK[ivr.band] || {};
        var col = d.cls === "down" ? "var(--down)" : d.cls === "up" ? "var(--up)" : d.cls === "warn" ? "var(--orange)" : "var(--muted)";
        ivrHtml = '<span class="ivr-chip" style="color:' + col + ';border-color:' + col + '">' + esc(lz(d.en, d.zh)) + "</span>";
      }
    }
    function met(k, v) { return v == null ? "" : '<span class="met"><span class="k">' + k + '</span><span class="v">' + v + "</span></span>"; }
    var mets = '<div class="mets">' +
      met("IV30", s.iv30 != null ? pctU(s.iv30, 1) + ivrHtml : null) +
      met(lz("25Δ skew", "25Δ偏斜"), sk && sk.rr25 != null ? sgn(sk.rr25, 1) : null) +
      met(lz("Move / day", "日预期波动"), em.daily_pct != null ? "±" + pctU(em.daily_pct, 2) : null) +
      met(lz("Move / week", "周预期波动"), em.weekly_pct != null ? "±" + pctU(em.weekly_pct, 1) : null) +
      "</div>";
    var foot = (sk && sk.expiry) ? '<div class="rfoot">' + esc(lz("Skew read from the " + sk.expiry + " chain" + (sk.days != null ? " (" + sk.days + "d)" : "") + ". IV rank compares today's IV30 with its own recent ~40 sessions.",
      "偏斜取自 " + sk.expiry + " 期权链" + (sk.days != null ? "（" + sk.days + "天）" : "") + "。IV分位为 IV30 与其自身近约40个交易日的比较。")) + "</div>" : "";
    return '<div class="card read anim d3">' + kick +
      '<div class="rhead ' + cls + '">' + word + "</div>" +
      '<div class="rsub">' + sub + "</div>" + mets +
      '<div class="rspark" id="gx-ivspark"></div>' + foot + "</div>";
  }
  function drawIvSpark() {
    var host = document.getElementById("gx-ivspark"); if (!host) return;
    var h = (cur.history || []).filter(function (r) { return r.iv30 != null; });
    if (h.length < 3) { host.innerHTML = ""; return; }
    var W = 150, H = 34, vals = h.map(function (r) { return r.iv30; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pad = (hi - lo) * 0.12 || 1; lo -= pad; hi += pad;
    function X(i) { return 2 + i / (h.length - 1) * (W - 4); }
    function Y(v) { return 2 + (hi - v) / (hi - lo) * (H - 4); }
    var info = cssv("--info");
    var d = vals.map(function (v, i) { return (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1); }).join(" ");
    host.innerHTML = '<span class="muted xs">' + esc(lz("IV30 · last " + h.length + " sessions", "IV30 · 近 " + h.length + " 个交易日")) + "</span><br>" +
      '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" style="vertical-align:middle">' +
      '<path d="' + d + '" fill="none" stroke="' + info + '" stroke-width="1.4"/>' +
      '<circle cx="' + X(h.length - 1) + '" cy="' + Y(vals[vals.length - 1]) + '" r="2.2" fill="' + info + '"/></svg>';
  }
  function leanReadHTML() {
    var t = cur.tilt, meta = cur.meta || {}, grp = meta.grp || "";
    var kick = '<div class="cardhead"><span class="kick">' + lz("The lean — direction, by time window", "倾向 — 按时间窗的方向") + "</span>" +
      help(lz("Different option forces act on different clocks, so the lean is split by time window instead of blended into one arrow. Each row is a tendency from delayed end-of-day positioning — not a trade and not a target. Direction is far less reliable than the tape read; most names sit near a coin-flip.",
        "不同期权力量作用于不同时间窗，因此按时间窗拆分、而非合成一个箭头。每行是延迟收盘仓位的方向倾向 — 非交易、非目标。方向的可靠性远低于盘面读数；多数标的接近抛硬币。")) + "</div>";
    if (!t || !t.legs || !t.legs.length) {
      return '<div class="card read anim d4">' + kick +
        '<div class="rhead info">—</div><div class="rsub">' + esc(lz("No directional lean today.", "今日无方向倾向。")) + "</div></div>";
    }
    var r = READS[t.read] || READS.balanced;
    var cls = r.cls === "up" ? "up" : r.cls === "down" ? "down" : (r.cls === "pin" || r.cls === "vol") ? "warn" : "info";
    var legs = t.legs.map(function (leg) {
      var a = tiltArrow(leg), sig = TILT_SIG[leg.signal] || { en: leg.signal, zh: leg.signal };
      return '<div class="leg"><div class="leg-t"><span class="leg-ar ' + a.c + '">' + a.g + "</span>" +
        '<span class="leg-n">' + esc(lz(sig.en, sig.zh)) + "</span>" +
        '<span class="leg-hz">' + esc(horizonText(leg.horizon, leg.days)) + "</span></div>" +
        '<div class="leg-w">' + esc(tiltWhy(leg)) + "</div></div>";
    }).join("");
    var confTxt = t.confidence === "low" ? lz("low", "低") : t.confidence === "high" ? lz("high", "高") : lz("medium", "中");
    var frag = (grp !== "Index" && grp.indexOf("ETF") < 0)
      ? " " + lz("Single stock: the dealer sign is an assumption and can be wrong.", "个股：做市商符号为假设、可能出错。") : "";
    return '<div class="card read anim d4">' + kick +
      '<div class="rhead ' + cls + '">' + esc(lz(r.en, r.zh)) + "</div>" +
      '<div class="rsub">' + esc(lz("Weaker evidence than the tape read — treat as context.", "证据弱于盘面读数 — 仅作背景。")) + "</div>" +
      '<div class="legs">' + legs + "</div>" +
      '<div class="rfoot">' + esc(lz("Not a trade signal or a target — a balance-of-pressures read from delayed EOD options. Confidence: ", "非交易信号、非目标 — 由延迟收盘期权得出的力量平衡读数。可信度：") + confTxt + "." + frag) + "</div></div>";
  }

  // ---- tilt leg helpers ----
  var TILT_SIG = {
    charm: { en: "Charm drift", zh: "Charm 漂移" },
    pin: { en: "Max-pain pin", zh: "最大痛点磁吸" },
    skew: { en: "25Δ skew", zh: "25Δ 偏斜" },
    regime: { en: "Gamma regime", zh: "Gamma 体制" }
  };
  function tiltArrow(leg) {
    if (leg.signal === "pin") return { g: "●", c: "pin" };
    if (leg.dir === "up") return { g: "▲", c: "up" };
    if (leg.dir === "down") return { g: "▼", c: "down" };
    return { g: "⇅", c: "flat" };
  }
  function tiltWhy(leg) {
    switch (leg.signal) {
      case "charm":
        return lz("Dealer charm hedging tends to drift price " + (leg.dir === "up" ? "up" : "down") + " as time passes — weak and short-lived.",
          "做市商 charm 对冲随时间推移倾向把价格往" + (leg.dir === "up" ? "上" : "下") + "带 — 弱且短暂。");
      case "pin":
        return lz("Options cluster at the magnet" + (leg.target != null ? " (" + price(leg.target) + ")" : "") + ", so on quiet days price is pulled " + (leg.toward === "up" ? "up" : "down") + " toward it into expiry.",
          "期权在磁吸位" + (leg.target != null ? "（" + price(leg.target) + "）" : "") + "聚集，平静日临近到期价格被往" + (leg.toward === "up" ? "上" : "下") + "拉向它。");
      case "skew":
        return leg.dir === "down"
          ? lz("Puts are bid over calls — the market is paying for downside protection.", "看跌比看涨更贵 — 市场在为下行保护付费。")
          : lz("Calls are bid over puts — the market is chasing upside.", "看涨比看跌更贵 — 市场在追逐上行。");
      case "regime":
        return leg.dir === "two_sided"
          ? lz("Short gamma — dealers amplify moves, so swings run both ways and bigger.", "空头Gamma — 做市商放大走势，双向且更大。")
          : lz("Long gamma — dealers absorb moves, so pushes toward either wall tend to fade.", "多头Gamma — 做市商吸收走势，逼近任一墙的冲击往往回落。");
      default: return "";
    }
  }

  // ---- vol-hole label map + board cell (board + ladder badge) ----
  var VHS = {
    IN_HOLE:     { emo: "🧲", en: "Boxed in between walls",  zh: "被困两墙之间",  cls: "neu",  sh_en: "In hole",     sh_zh: "洞内" },
    COILED_UP:   { emo: "⬆",  en: "Pressed at the ceiling",  zh: "紧贴上沿",     cls: "up",   sh_en: "At ceiling",  sh_zh: "贴上沿" },
    COILED_DOWN: { emo: "⬇",  en: "Pressed at the floor",    zh: "紧贴下沿",     cls: "down", sh_en: "At floor",    sh_zh: "贴下沿" },
    EXPANSION:   { emo: "⚡", en: "In the jumpy zone",        zh: "处于跳动区",   cls: "vol",  sh_en: "Jumpy zone",  sh_zh: "跳动区" },
    NONE:        { emo: "·",  en: "No clear band",           zh: "无明显区间",   cls: "na",   sh_en: "—",           sh_zh: "—" }
  };
  function vhCell(m) {
    if (!m.vh_state || m.vh_state === "NONE") return '<td><span class="vh-pill na">—</span></td>';
    var v = VHS[m.vh_state] || VHS.NONE;
    return '<td><span class="vh-pill ' + v.cls + '">' + v.emo + " " + esc(lz(v.sh_en, v.sh_zh)) + "</span></td>";
  }

  // ========================================================================
  // RAW-STRUCTURE SHELF — the full charts, collapsed by default (walls open)
  // ========================================================================
  function shelfTermHTML() {
    var tm = cur.term || []; if (!tm.length) return '<p class="sh-sub">—</p>';
    var rows = tm.map(function (r) {
      return "<tr><td>" + esc(r.expiry) + "</td><td>" + r.days + "</td><td>" + pctU(r.atm_iv, 1) + "</td><td>±" + pctU(r.move_pct, 1) +
        "</td><td>" + (r.straddle_pct == null ? "—" : "±" + pctU(r.straddle_pct, 1)) + "</td><td>" + price(r.max_pain) + "</td></tr>";
    }).join("");
    return '<table class="term"><thead><tr><th>' + lz("Expiry", "到期") + "</th><th>" + lz("Days", "天数") + "</th><th>" + lz("ATM IV", "平值IV") +
      "</th><th>" + lz("IV move", "IV波动") + "</th><th>" + lz("Straddle", "跨式") + "</th><th>" + lz("Max pain", "最大痛点") + "</th></tr></thead><tbody>" + rows + "</tbody></table>";
  }
  function greeksHTML() {
    var s = cur.summary || {};
    function g(k, v, sub) { return '<div class="greek"><div class="k">' + esc(k) + '</div><div class="v">' + v + "</div>" + (sub ? '<div class="muted xs">' + esc(sub) + "</div>" : "") + "</div>"; }
    var cells = [
      g(lz("Net delta", "净Delta"), s.net_delta_bn == null ? "—" : sgn(s.net_delta_bn, 1) + " $bn"),
      g(lz("Net vanna", "净Vanna"), s.net_vex == null ? "—" : compact(s.net_vex)),
      g(lz("Charm bias", "Charm偏向"), s.charm_net_sign > 0 ? lz("↑ up-drift", "↑ 上漂") : s.charm_net_sign < 0 ? lz("↓ down-drift", "↓ 下漂") : "—", s.charm_anchor != null ? lz("anchor " + price(s.charm_anchor), "锚 " + price(s.charm_anchor)) : ""),
      g(lz("Put/Call OI", "认沽/认购OI"), s.put_call_oi_ratio == null ? "—" : (+s.put_call_oi_ratio).toFixed(2)),
      g(lz("Put/Call vol", "认沽/认购量"), s.put_call_vol_ratio == null ? "—" : (+s.put_call_vol_ratio).toFixed(2)),
      g(lz("Largest OI", "最大未平仓"), price(s.largest_oi)),
      g(lz("Chain depth", "链路深度"), (s.n_strikes || "—") + "", s.tier === "full" ? lz("deep", "深") : lz("thin — fragile", "薄 — 脆弱"))
    ];
    return '<div class="greeks">' + cells.join("") + "</div>";
  }
  function shelfHTML() {
    function panel(ic, ti_en, ti_zh, hint_en, hint_zh, body, open) {
      return "<details" + (open ? " open" : "") + '><summary><span class="sh-ic">' + ic + "</span>" + esc(lz(ti_en, ti_zh)) +
        (hint_en ? '<span class="sh-hint">' + esc(lz(hint_en, hint_zh)) + "</span>" : "") + '<span class="sh-caret">▸</span></summary>' +
        '<div class="sh-body">' + body + "</div></details>";
    }
    var walls = '<p class="sh-sub">' + esc(lz("Net dealer gamma summed at each strike. Green = call-heavy resistance above; red = put-heavy support below.", "每个行权价上的做市商净Gamma。绿=上方看涨阻力；红=下方看跌支撑。")) + "</p>" +
      '<div class="hm-tabs" id="gx-bartabs">' + barTabs() + '</div><div><div class="chartbox" id="gx-bars"></div>' + barLegend() + "</div>";
    var prof = '<p class="sh-sub">' + esc(lz("Dealer $gamma re-evaluated as spot moves. Where the curve crosses zero is the flip: above it dealers dampen, below they amplify.", "随现价移动重估的做市商$Gamma。曲线穿越零点即翻转：之上抑制，之下放大。")) + '</p><div class="chartbox" id="gx-profile"></div>';
    var heat = '<p class="sh-sub">' + esc(lz("The options surface. Rows = strikes (spot outlined), columns = expiries. Bright clusters are where positioning concentrates.", "期权曲面。行=行权价（现价加框），列=到期。亮区即仓位集中处。")) + "</p>" +
      '<div class="hm-tabs" id="gx-heattabs">' + heatTabs() + '</div><div class="hm-scroll" id="gx-heat"></div>' + heatLegend();
    var vol = '<div class="sh-grid2"><div><h3 style="font-size:13px;margin:0 0 2px">' + lz("Volatility smile / skew", "波动率微笑/偏斜") + "</h3>" +
      '<p class="sh-sub">' + esc(lz("Implied vol by strike, front expiry. A steep left side (puts richer) is downside skew.", "近月按行权价的隐含波动。左侧更陡（看跌更贵）即下行偏斜。")) + '</p><div class="chartbox" id="gx-smile"></div></div>' +
      '<div><h3 style="font-size:13px;margin:0 0 2px">' + lz("IV term structure", "隐含波动期限结构") + "</h3>" +
      '<p class="sh-sub">' + esc(lz("ATM vol by expiry. Upward-sloping is the calm default; inverted flags an event or stress.", "按到期的平值波动。向上倾斜为平静常态；倒挂预示事件或压力。")) + '</p><div class="chartbox" id="gx-term"></div></div></div>';
    return '<div class="shelf">' +
      '<div class="shelf-cap">' + lz("Under the hood — the raw options structure", "深入研究 — 原始期权结构") + "</div>" +
      panel("🧱", "Dealer gamma by strike — the walls", "按行权价的做市商Gamma — 墙", "gamma · OI · volume", "Gamma · 未平仓 · 成交量", walls, true) +
      panel("📉", "Net-gamma profile — where the flip is", "净Gamma曲线 — 翻转所在", "", "", prof, false) +
      panel("🗺️", "Options surface heatmap", "期权曲面热力图", "gamma · OI · volume", "Gamma · 未平仓 · 成交量", heat, false) +
      panel("🌋", "Vol smile & IV term structure", "波动率微笑与期限结构", "", "", vol, false) +
      panel("🪜", "Expiry ladder — IV, expected move & max pain", "到期阶梯 — IV、预期波动与最大痛点", "", "", shelfTermHTML(), false) +
      panel("Σ", "Positioning greeks", "持仓希腊字母", "delta · vanna · charm · chain", "Delta · Vanna · Charm · 链路", greeksHTML(), false) +
    "</div>";
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
    // 25Δ risk-reversal readout (the directional skew tell)
    var rr = "", sk = s.skew;
    if (sk && sk.rr25 != null) {
      var tn = TONES[sk.tone] || TONES.balanced;
      var col = tn.cls === "down" ? "var(--down)" : tn.cls === "up" ? "var(--up)" : "var(--muted)";
      rr = '<span style="color:' + col + '"><b>25Δ RR ' + sgn(sk.rr25, 1) + "</b> · " + esc(lz(tn.en, tn.zh)) + "</span>";
    }
    host.innerHTML = svg + '<div class="legend"><span><i style="background:var(--up)"></i>' + lz("call IV", "看涨IV") + '</span><span><i style="background:var(--down)"></i>' + lz("put IV", "看跌IV") + "</span>" + rr + "</div>";
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

  // ---- net-GEX history sparkline (used by the regime read) ----
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

  // ========================================================================
  // INIT + re-render on theme/lang change
  // ========================================================================
  // ====== Options-flow desk + vol-regime hero (decoupled client-side fetches) ======
  var flowCache = {}, weatherData;
  function loadFlow(key) {
    if (flowCache[key] !== undefined) { renderFlow(); return; }
    fetch("flow/" + encodeURIComponent(key) + ".json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { flowCache[key] = j; if (curKey === key) renderFlow(); })
      .catch(function () { flowCache[key] = null; });
  }
  // W0.7: FLOW_ACCRUAL_SINCE is the program start date (W0.1 secrets fix); used in the
  // "accruing" state card when flow data is not yet available for a name.
  var FLOW_ACCRUAL_SINCE = "2026-07-03";
  function renderFlow() {
    var host = document.getElementById("gx-flow"); if (!host) return;
    var f = flowCache[curKey];
    if (!f || !f.available) {
      // Show an honest "accruing" state rather than a blank panel — F12 UI honesty fix.
      host.innerHTML =
        '<div class="card anim fl fl-accruing">' +
          '<div class="fl-head"><span class="fl-tag">📊 ' +
            esc(lz("Options flow desk", "期权流动台")) +
          "</span></div>" +
          '<div class="fl-accruing-msg">' +
            esc(lz(
              "Flow accruing since " + FLOW_ACCRUAL_SINCE + " — no data yet for this name. "
                + "Magnitude signals (premium, same-day share, ΔOI) populate once the S3 pull runs.",
              "流动数据自 " + FLOW_ACCRUAL_SINCE + " 起积累中 — 该标的暂无数据。"
                + "S3拉取运行后，量级信号（权利金、当日到期占比、ΔOI）将自动填充。"
            )) +
          "</div>" +
        "</div>";
      return;
    }
    var d = f.dealer || {}, np = f.net_premium_mn, v = f.verdict || {}, sg = f.signing || {};
    var p = (f.positioning && f.positioning.available) ? f.positioning : null;
    var dirOK = !!sg.direction_reliable;
    function mn(x) { return x == null ? "—" : (x >= 0 ? "+$" : "-$") + Math.abs(x).toFixed(0) + "M"; }
    function bn(x) { return x == null ? "—" : (x >= 0 ? "$" : "-$") + Math.abs(x >= 1000 ? x / 1000 : x).toFixed(x >= 1000 ? 1 : 0) + (x >= 1000 ? "B" : "M"); }
    function compact(x) { if (x == null) return "—"; var s = x < 0 ? "-" : "+", a = Math.abs(x); return s + (a >= 1e6 ? (a / 1e6).toFixed(2) + "M" : a >= 1e3 ? (a / 1e3).toFixed(1) + "k" : a); }
    function sbn(x) { if (x == null) return "—"; var a = Math.abs(x), s = x < 0 ? "-$" : "$"; return a >= 1000 ? s + (a / 1000).toFixed(1) + "B" : s + a.toFixed(0) + "M"; }   // signed $, B/M on |x| (x in $M)
    function chip(k, val, cls, soft) { return '<span class="fl-chip ' + (cls || "") + (soft ? " soft" : "") + '"><span class="k">' + k + '</span><span class="v">' + val + "</span></span>"; }
    var chips =
      chip(lz("Premium", "权利金"), bn(f.premium_mn), "") +
      // Plain words on the glance tier: the acronym this chip label used to carry
      // is banned Tier-1 vocabulary (docs/DESIGN_DOCTRINE.md Law 2) and nothing on
      // this page defines it. "Same-day" is the estate's house phrase for it.
      chip(lz("Same-day", "当日到期"), f.zerodte_share == null ? "—" : Math.round(f.zerodte_share * 100) + "%", "") +
      ((f.new_positions && f.new_positions.fresh_contracts != null) ? chip(lz("New positions", "新建仓"), f.new_positions.fresh_contracts, "") : "") +
      chip("P/C", f.pc_ratio == null ? "—" : f.pc_ratio, "") +
      // ΔOI positioning — RELIABLE (no signing), so it is NOT soft and carries its tone directly
      (p ? chip(lz("Positioning ΔOI", "净持仓ΔOI"), compact(p.net_doi), (p.tone === "pos" ? "pos" : p.tone === "neg" ? "neg" : "")) : "") +
      chip(lz("Net premium", "净权利金"), (dirOK ? "" : "~") + mn(np), (dirOK ? (np > 0 ? "pos" : np < 0 ? "neg" : "") : ""), !dirOK) +
      chip(lz("Signed P/C", "带向P/C"), (dirOK ? "" : "~") + (f.signed_pc == null ? "—" : f.signed_pc), (dirOK ? ((f.signed_pc > 1.3) ? "neg" : (f.signed_pc < 0.7 ? "pos" : "")) : ""), !dirOK) +
      (d.gamma_flow_bn != null ? chip(lz("Dealer γ-flow", "做市商γ流"), (dirOK ? "" : "~") + (d.gamma_flow_bn >= 0 ? "+" : "") + d.gamma_flow_bn + "bn", (dirOK ? (d.gamma_flow_bn < 0 ? "neg" : "pos") : ""), !dirOK) : "");
    var div = (d.divergence || []).slice(0, 4).map(function (x) {
      return "<li>" + esc((x.cp === "C" ? lz("Call ", "看涨 ") : lz("Put ", "看跌 ")) + x.k + " — " + lz(x.flow, x.flow) + " (" + mn(x.prem_mn) + ")") + "</li>"; }).join("");
    var np2 = ((f.new_positions && f.new_positions.top) || []).slice(0, 4).map(function (x) {
      return "<li>" + esc((x.cp === "C" ? "C" : "P") + x.k + " " + x.exp + " — " + x.vol.toLocaleString() + " vol @ " + x.x_oi + "× OI, " + x.dir + " (" + mn(x.prem_mn) + ")") + "</li>"; }).join("");
    // multi-day ΔOI net-demand: where open interest is being BUILT (opening = new positioning)
    var posBuild = p ? (p.top_build || []).slice(0, 4).map(function (x) {
      return "<li>" + esc((x.cp === "C" ? "C" : "P") + x.k + " " + x.exp + " — " + (x.doi >= 0 ? "+" : "") + x.doi.toLocaleString() + " OI (" + x.oi_prior.toLocaleString() + "→" + x.oi.toLocaleString() + ")") + "</li>"; }).join("") : "";
    host.innerHTML =
      '<div class="card anim fl s-' + (v.tone || "neutral") + '">' +
        '<div class="fl-head"><span class="fl-tag">📊 ' + lz("Today’s measured flow", "今日实测流动") + "</span>" +
          '<span class="fl-verdict">' + esc(lz(v.en, v.zh)) + "</span></div>" +
        '<div class="fl-chips">' + chips + "</div>" +
        (p && p.lean_en ? '<div class="fl-sec"><div class="fl-h">' + lz("Smart-money positioning — ΔOI net demand (RELIABLE, no trade-signing)", "聪明钱持仓 — ΔOI净需求（可靠，无需定向）") + "</div>" +
          '<div class="sm" style="margin:.2em 0">' + esc(lz(p.lean_en, p.lean_zh || p.lean_en)) + " · " + lz("calls", "看涨") + " " + compact(p.call_doi) + " / " + lz("puts", "看跌") + " " + compact(p.put_doi) + (p.net_delta_doi_mn != null ? " · " + lz("net Δ-exposure", "净Δ敞口") + " " + sbn(p.net_delta_doi_mn) : "") + "</div>" +
          (posBuild ? "<ul>" + posBuild + "</ul>" : "") +
          '<div class="sm muted">' + esc(lz("Day-over-day open-interest change vs " + (p.prior_asof || "") + " (" + p.days_back + "d) over " + (p.n_matched || 0).toLocaleString() + " matched contracts. Rising OI = opening; needs ≥2 snapshot days and sharpens as history accrues.", "相对 " + (p.prior_asof || "") + " 的逐日未平仓量变化（" + p.days_back + "天），覆盖 " + (p.n_matched || 0).toLocaleString() + " 个匹配合约。未平仓上升=开仓；需≥2个快照日，随历史累积而更清晰。")) + "</div></div>" : "") +
        (div ? '<div class="fl-sec"><div class="fl-h">' + lz("Flow vs the dealer-sign assumption", "流动 vs 做市商符号假设") + "</div><ul>" + div + "</ul></div>" : "") +
        (np2 ? '<div class="fl-sec"><div class="fl-h">' + lz("Fresh positioning (volume > OI)", "新建仓（成交>未平仓）") + "</div><ul>" + np2 + "</ul></div>" : "") +
        '<div class="fl-foot">' + esc(lz(
          "Reliable (no signing): premium, same-day share, new positions, P/C. Direction (~) is SOFT — tick-rule recovers net buy/sell only " + (sg.net_sign_recovery != null ? Math.round(sg.net_sign_recovery * 100) + "%" : "~") + " of the time on minute bars (option ticks are delta-dominated; per-trade " + (sg.per_trade_agreement != null ? Math.round(sg.per_trade_agreement * 100) + "%" : "~80%") + " vs NBBO, Databento-calibrated). EOD, as of " + (f.asof || "") + ". Never a buy/sell.",
          "可靠（无需定向）：权利金、当日到期占比、新建仓、P/C。方向(~)为软信号 — tick规则在分钟数据上仅约" + (sg.net_sign_recovery != null ? Math.round(sg.net_sign_recovery * 100) : "") + "%能还原净买卖（期权由delta主导；逐笔约" + (sg.per_trade_agreement != null ? Math.round(sg.per_trade_agreement * 100) : 80) + "% 对NBBO，经Databento校准）。收盘数据，截至 " + (f.asof || "") + "。绝非买卖信号。")) + "</div>" +
      "</div>";
  }
  function renderWeather() {
    var box = document.getElementById("gx-weather"), body = document.getElementById("gx-weather-body");
    var R = weatherData;
    if (!box || !body || !R || !R.snapshot || !R.game_plan || !R.game_plan.available) { if (box) box.hidden = true; return; }
    var snap = R.snapshot, gp = R.game_plan; box.hidden = false;
    var sb = document.getElementById("wx-scored"); if (sb) sb.hidden = !snap.scored_active;
    var cls = { "gp-calm": "wx-calm", "gp-up": "wx-up", "gp-jumpy": "wx-jumpy", "gp-warn": "wx-warn", "gp-neutral": "wx-neutral" }[gp.css] || "wx-neutral";
    var rs = (snap.risk_score == null) ? 0 : snap.risk_score, pos = Math.max(2, Math.min(98, (rs + 1) / 2 * 100));
    var bullets = (gp.bullets || []).map(function (b) { return "<li>" + esc(lz(b.en, b.zh)) + "</li>"; });
    if (R.opex && R.opex.available) bullets.push("<li>" + esc(lz("Calendar", "日历") + ": " + (R.opex.phase || "").replace(/_/g, " ") + (R.opex.is_quad_cycle ? lz(" · quad-witching", " · 四巫日") : "") + " — " + (R.opex.read || "")) + "</li>");
    function stat(k, v) { return v == null ? "" : '<span class="wx-stat"><span class="k">' + k + '</span><span class="v">' + v + "</span></span>"; }
    var stats = stat("VIX", snap.vix) +
      stat(lz("VIX/VIX3M", "期限比"), snap.ts_slope != null ? snap.ts_slope.toFixed(3) : null) +
      stat(lz("MOVE %ile", "MOVE分位"), snap.move_pctile != null ? Math.round(snap.move_pctile * 100) + "%" : null) +
      stat(lz("Sizing", "仓位系数"), snap.vol_target_scalar != null ? snap.vol_target_scalar.toFixed(2) + "×" : null);
    body.innerHTML =
      '<div class="wx-row ' + cls + '"><span class="wx-ic">' + esc(gp.icon || "") + "</span>" +
        '<span class="wx-v">' + esc(lz(gp.verdict.en, gp.verdict.zh)) + "</span>" +
        '<span class="wx-gauge"><span class="track"><span class="mk" style="left:' + pos.toFixed(1) + '%"></span></span>' +
          '<span class="lbls"><span>' + lz("risk-off", "避险") + "</span><span>" + lz("risk-on", "进取") + "</span></span></span>" +
        stats + "</div>" +
      '<div class="wx-sub">' + esc(lz(gp.sub.en, gp.sub.zh)) + "</div>" +
      (bullets.length
        ? '<details class="wx-more"><summary>' + lz("Why · details", "原因 · 详情") + "</summary>" +
          '<ul class="wx-bullets">' + bullets.join("") + "</ul>" +
          '<div class="wx-foot">' + esc(lz(
            "Validated on 1990+ history (term-structure + bond-vol forward-vol gate). A subtract-only risk/sizing read — not a stock picker, not an intraday timer. As of " + (snap.asof || "") + ".",
            "基于1990年以来历史验证（期限结构+债券波动率前瞻门槛）。仅做减法的风险/仓位读数 — 非选股、非盘中择时。截至 " + (snap.asof || "") + "。")) + "</div></details>"
        : "");
  }
  function loadWeather() {
    if (weatherData !== undefined) { renderWeather(); return; }
    fetch("vol/regime.json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { weatherData = j; renderWeather(); }).catch(function () { weatherData = null; });
  }

  function init() {
    renderBoard(); setupSearch(); setupBoardControls(); setupBoardHelp(); setupHelpTips();
    loadWeather();
    var hk = (location.hash || "").replace("#", "").toUpperCase();
    selectSymbol(BYKEY[hk] ? hk : (window.GEX_DEFAULT || (M[0] && M[0].key)));
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || "")) {
        var q = document.getElementById("gx-q"); if (q) { q.focus(); e.preventDefault(); }
      }
    });
  }
  ["langchange", "themechange"].forEach(function (e) {
    document.addEventListener(e, function () { renderBoard(); renderWeather(); if (cur) renderDetail(); });
  });
  var gxRsz = null;
  function queueLadderRedraw() {
    clearTimeout(gxRsz);
    gxRsz = setTimeout(function () {
      var host = document.getElementById("gx-ladder");
      // redraw only when the drawn width no longer matches the host width
      if (cur && host && host.firstChild) {
        var vb = host.firstChild.viewBox && host.firstChild.viewBox.baseVal;
        if (!vb || Math.abs(vb.width - Math.max(320, host.clientWidth || 640)) > 8) drawLadder();
      }
    }, 120);
  }
  window.addEventListener("resize", function () {
    hideTip(); hideHelp(); helpAnchor = null;
    queueLadderRedraw();
  });
  if (window.ResizeObserver) {
    new ResizeObserver(queueLadderRedraw).observe(document.getElementById("gx-detail") || document.body);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

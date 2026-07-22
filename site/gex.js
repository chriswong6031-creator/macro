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
    var hint = document.getElementById("gx-board-hint");
    if (hint && cov) hint.textContent = lz(cov.covered + " of " + cov.total + " have liquid options", cov.total + " 中 " + cov.covered + " 个有活跃期权");
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
  // DETAIL COMPOSITION — hero verdict → Levels Map → three reads → flow → shelf
  // ========================================================================
  function renderDetail() {
    if (!cur) return;
    var box = document.getElementById("gx-detail");
    var V = verdict();
    box.innerHTML =
      '<div class="' + V.cls + '">' +
        heroHTML(V) +
        '<div class="eyebrow anim"><span class="dot"></span>' + lz("Where the walls are", "墙在何处") +
          '<span class="hint">' + lz("the levels dealers defend", "做市商守护的价位") + "</span></div>" +
        levelsMapHTML() +
        '<div class="eyebrow"><span class="dot"></span>' + lz("Three reads", "三项读数") +
          '<span class="hint">' + lz("regime · tone · lean", "体制 · 情绪 · 倾向") + "</span></div>" +
        '<div class="reads">' + regimeReadHTML() + toneReadHTML() + tiltReadHTML() + "</div>" +
        '<div class="eyebrow"><span class="dot"></span>' + lz("Today’s measured flow", "今日实测流动") + "</div>" +
        '<div id="gx-flow"></div>' +
        '<div class="eyebrow"><span class="dot"></span>' + lz("Study — the raw options structure", "研究 — 原始期权结构") +
          '<span class="hint">' + lz("open a panel for the charts", "展开面板查看图表") + "</span></div>" +
        shelfHTML() +
      "</div>";
    drawBars(); drawProfile(); drawHeat(); drawSmile(); drawTerm(); drawSpark();
    wireBarTabs(); wireHeatTabs();
    renderFlow();
  }

  function help(txt) {
    return '<span class="help" tabindex="0">?<span class="tip">' + txt + "</span></span>";
  }

  // ---- the one-line verdict (regime × vol-hole → state + plain say + stance) ----
  function verdict() {
    var s = cur.summary || {}, vh = cur.vol_hole || {}, regime = s.regime, st = vh.state;
    var cw = price(s.call_wall), pw = price(s.put_wall);
    if (regime === "short") {
      return { cls: "gx-jumpy", icon: "🌪",
        state_en: "Jumpy — dealers amplify moves", state_zh: "跳动 — 做市商放大走势",
        say_en: "Moves feed on themselves — expect <b>bigger swings and air-pockets</b>, and don’t count on dips getting bought back the way they do in calm tape.",
        say_zh: "走势自我强化 — 预期<b>更大的波动与急跌</b>，别指望像平静行情那样回调自动被买回。",
        stance_en: "Watch — don’t chase", stance_zh: "观察 — 勿追高" };
    }
    if (!regime) {
      return { cls: "gx-mixed", icon: "⚖️",
        state_en: "No strong pull", state_zh: "无明显牵引",
        say_en: "Dealer hedging isn’t leaning either way today, so the levels below matter less than usual.",
        say_zh: "今日做市商对冲无明显倾向，下方价位的作用弱于平常。",
        stance_en: "Trade the chart, not the gamma", stance_zh: "看图表，而非Gamma" };
    }
    if (st === "COILED_UP") return { cls: "gx-calm", icon: "⬆",
      state_en: "Coiled at the ceiling", state_zh: "贴近上沿蓄势",
      say_en: "Quiet but wound tight under the ceiling — it usually fades back inside, but a <b>daily close above " + cw + "</b> can let it run.",
      say_zh: "平静却在上沿之下紧绷 — 通常回落，但<b>日线收于 " + cw + " 之上</b>可能放行上涨。",
      stance_en: "Watch the ceiling", stance_zh: "关注上沿" };
    if (st === "COILED_DOWN") return { cls: "gx-calm", icon: "⬇",
      state_en: "Coiled at the floor", state_zh: "贴近下沿蓄势",
      say_en: "Quiet but wound tight above the floor — it usually holds, but a <b>daily close below " + pw + "</b> removes the cushion.",
      say_zh: "平静却在下沿之上紧绷 — 通常守住，但<b>日线收于 " + pw + " 之下</b>会移除缓冲。",
      stance_en: "Watch the floor", stance_zh: "关注下沿" };
    if (st === "IN_HOLE") return { cls: "gx-calm", icon: "🧲",
      state_en: "Pinned & calm", state_zh: "磁吸 · 平静",
      say_en: "Expect chop, not trend: price gets pulled toward the middle, so pushes toward the ceiling or floor tend to fade.",
      say_zh: "预期震荡而非趋势：价格被拉回中部，逼近上/下沿常回落。",
      stance_en: "Range day — fade the edges", stance_zh: "区间日 — 逢边回落" };
    return { cls: "gx-calm", icon: "🧲",
      state_en: "Calm, no firm walls", state_zh: "平静 · 无明显墙",
      say_en: "Calm regime, but no firm walls are mapped today — lean on the chart and the expected range below.",
      say_zh: "平静体制，但今日无明确的墙 — 参考图表与下方预期区间。",
      stance_en: "Watch — don’t chase", stance_zh: "观察 — 勿追高" };
  }

  // ---- "what changed" — most recent regime run from the daily history ----
  function regimeChange() {
    var h = (cur.history || []).filter(function (r) { return r.regime; });
    if (h.length < 2) return null;
    var last = h[h.length - 1].regime, days = 0, i;
    for (i = h.length - 1; i >= 0; i--) { if (h[i].regime === last) days++; else break; }
    var prior = null;
    for (var j = h.length - 1 - days; j >= 0; j--) { if (h[j].regime) { prior = h[j].regime; break; } }
    return { reg: last, days: days, prior: prior, flipped: !!(prior && prior !== last && days <= 3) };
  }

  // ---- HERO: identity + verdict + stance + expected range + as-of ----
  function heroHTML(V) {
    var s = cur.summary || {}, em = cur.expected_move || {}, meta = cur.meta || {}, grp = meta.grp || "";
    var range = "";
    if (em.daily_pct != null && s.spot != null) {
      var lo = s.spot * (1 - em.daily_pct / 100), hi = s.spot * (1 + em.daily_pct / 100);
      range = '<span class="range-chip"><span class="k">' + lz("Range today", "今日区间") + "</span> <b>" +
        price(lo) + " – " + price(hi) + '</b> <span class="muted sm">±' + em.daily_pct.toFixed(2) + "%</span>" +
        help(lz("Options imply a roughly 2-in-3 chance the close lands inside this band today. A symmetric range, not a forecast of direction and not a cap.",
                "期权隐含今日收盘约三分之二概率落在此区间。对称区间，非方向预测、非上限。")) + "</span>";
    }
    var rc = regimeChange(), changed = "";
    if (rc) {
      var wEn = rc.reg === "long" ? "calm" : rc.reg === "short" ? "jumpy" : "mixed";
      var wZh = rc.reg === "long" ? "平静" : rc.reg === "short" ? "跳动" : "中性";
      var cEn = rc.flipped ? ("Flipped to " + wEn + " " + rc.days + (rc.days === 1 ? " session ago" : " sessions ago"))
        : (wEn.charAt(0).toUpperCase() + wEn.slice(1) + " for " + rc.days + (rc.days === 1 ? " session" : " sessions"));
      var cZh = rc.flipped ? ("转为" + wZh + "已" + rc.days + "个交易日") : (wZh + "已持续" + rc.days + "个交易日");
      changed = '<span class="changed-chip"><span class="bd"></span>' + esc(lz(cEn, cZh)) + "</span>";
    }
    var warn = "";
    if (grp !== "Index" && grp.indexOf("ETF") < 0) {
      warn = '<div class="single-warn">⚠ <b>' + esc(lz("Single stock", "个股")) + "</b> " +
        esc(lz("— the dealer-positioning sign here is an assumption and can be wrong (covered-call funds or heavy retail call-buying can flip it). Treat these levels as loose context.",
               "— 此处做市商持仓符号为假设、可能出错（备兑基金或散户大量买看涨可翻转）。价位仅作宽松背景。")) +
        help(lz("Top-strike OI share " + (s.top_oi_share == null ? "—" : s.top_oi_share) + ", chain tier “" + s.tier + "”. The long-call/short-put sign is unobservable and least reliable when one strike dominates.",
                "最大行权价OI占比 " + (s.top_oi_share == null ? "—" : s.top_oi_share) + "，链路等级“" + s.tier + "”。多空符号不可观测，单一行权价主导时最不可靠。")) + "</div>";
    }
    return '<div class="card hero accent anim">' +
      '<div class="hero-glow"></div>' +
      '<div class="hero-top">' +
        '<div class="hero-id"><span class="sym">' + esc(meta.key || curKey) + "</span>" +
          (meta.en ? '<span class="nm">' + esc(lz(meta.en, meta.zh)) + "</span>" : "") +
          '<span class="grp">' + esc(lz(grp, grp)) + " · " + esc(lz("as of " + (meta.asof || ""), "截至 " + (meta.asof || ""))) + "</span></div>" +
        '<div class="hero-spot"><span class="k">' + lz("Spot", "现价") + '</span><span class="v">' + price(s.spot) + "</span></div>" +
      "</div>" +
      '<div class="hero-verdict"><span class="hero-vicon">' + V.icon + "</span>" +
        '<div class="hero-vtext"><div class="state">' + esc(lz(V.state_en, V.state_zh)) + "</div>" +
          '<div class="say">' + lz(V.say_en, V.say_zh) + "</div></div></div>" +
      '<div class="hero-row"><span class="stance"><span class="bd"></span>' + esc(lz(V.stance_en, V.stance_zh)) + "</span>" +
        range + changed +
        '<span class="hero-asof"><span class="bd"></span>' + esc(lz("delayed EOD", "延迟收盘")) + "</span></div>" +
      warn +
    "</div>";
  }

  // ========================================================================
  // LEVELS MAP (signature) — a spatial gravity map of the key levels
  // ========================================================================
  function strengthDots(str, colorVar) {
    if (str == null) return "";
    var n = Math.max(0, Math.min(6, Math.round(str / 100 * 6))), out = "";
    for (var i = 0; i < 6; i++) out += '<i style="background:' + (i < n ? "var(" + colorVar + ")" : "var(--line)") + '"></i>';
    return '<span class="lvl-str" title="' + str + '/100">' + out + "</span>";
  }
  function buildRail(L, s) {
    var spot = s.spot;
    var vals = L.map(function (p) { return p.v; }); if (spot != null) vals.push(spot);
    vals = vals.filter(function (v) { return v != null; });
    if (vals.length < 2) return "";
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pad = (hi - lo) * 0.10 || 1; lo -= pad; hi += pad;
    var W = 180, H = 300, xC = 52, mT = 14, mB = 14;
    function Y(v) { return mT + (hi - v) / (hi - lo) * (H - mT - mB); }
    var up = cssv("--up"), down = cssv("--down"), info = cssv("--info"), orange = cssv("--orange"),
        text = cssv("--text"), muted = cssv("--muted"), line = cssv("--line");
    var flip = s.gamma_flip, svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="levels map">';
    if (flip != null) {
      var yf = Y(flip);
      svg += '<rect x="8" y="' + mT + '" width="' + (W - 16) + '" height="' + (yf - mT).toFixed(1) + '" fill="' + up + '" opacity="0.05"/>';
      svg += '<rect x="8" y="' + yf.toFixed(1) + '" width="' + (W - 16) + '" height="' + (H - mB - yf).toFixed(1) + '" fill="' + down + '" opacity="0.06"/>';
    }
    svg += '<line class="lmap-axis" x1="' + xC + '" y1="' + mT + '" x2="' + xC + '" y2="' + (H - mB) +
      '" stroke="' + line + '" stroke-width="1.5" stroke-dasharray="2 4" pathLength="100" style="stroke-dashoffset:100;animation:gxDraw 1s ease forwards"/>';
    var labels = [];
    L.forEach(function (p) {
      var y = Y(p.v), col = p.cls === "cw" ? up : p.cls === "pw" ? down : p.cls === "flip" ? info : p.cls === "mp" ? orange : text;
      if (p.cls === "cw" || p.cls === "pw") {
        var th = 6 + (p.str ? Math.round(p.str / 100 * 20) : 8);
        svg += '<rect x="20" y="' + (y - th / 2).toFixed(1) + '" width="64" height="' + th + '" rx="3" fill="' + col + '" opacity="0.22"/>';
        svg += '<line x1="16" y1="' + y.toFixed(1) + '" x2="88" y2="' + y.toFixed(1) + '" stroke="' + col + '" stroke-width="2.4"/>';
      } else if (p.cls === "flip") {
        svg += '<line x1="16" y1="' + y.toFixed(1) + '" x2="88" y2="' + y.toFixed(1) + '" stroke="' + col + '" stroke-width="1.6" stroke-dasharray="5 4"/>';
        svg += '<line class="lmap-pulse" x1="16" y1="' + y.toFixed(1) + '" x2="88" y2="' + y.toFixed(1) + '" stroke="' + col +
          '" stroke-width="1.6" stroke-dasharray="6 66" pathLength="100" style="animation:gxFlow 3s linear infinite;filter:drop-shadow(0 0 3px ' + col + ')"/>';
      } else if (p.cls === "mp") {
        svg += '<circle cx="' + xC + '" cy="' + y.toFixed(1) + '" r="5" fill="none" stroke="' + col + '" stroke-width="2"/>';
      }
      labels.push({ y: y, col: col, txt: price(p.v), bold: false });
    });
    if (spot != null) {
      var ys = Y(spot);
      svg += '<line x1="16" y1="' + ys.toFixed(1) + '" x2="88" y2="' + ys.toFixed(1) + '" stroke="' + text + '" stroke-width="1" stroke-dasharray="2 3" opacity="0.7"/>';
      svg += '<circle class="lmap-halo" cx="' + xC + '" cy="' + ys.toFixed(1) + '" r="9" fill="var(--rg,' + info + ')" opacity="0.18" style="transform-origin:' + xC + 'px ' + ys.toFixed(1) + 'px;animation:gxBreathe 3s ease-in-out infinite"/>';
      svg += '<circle cx="' + xC + '" cy="' + ys.toFixed(1) + '" r="4.5" fill="' + text + '"/>';
      labels.push({ y: ys, col: text, txt: price(spot) + " ●", bold: true });
    }
    labels.sort(function (a, b) { return a.y - b.y; });
    var GAP = 13, prev = -99;
    labels.forEach(function (l) { l.ly = Math.max(l.y, prev + GAP); prev = l.ly; });
    var of = labels.length ? labels[labels.length - 1].ly - (H - 6) : 0;
    if (of > 0) labels.forEach(function (l) { l.ly -= of; });
    labels.forEach(function (l) {
      if (Math.abs(l.ly - l.y) > 2) svg += '<line x1="88" y1="' + l.y.toFixed(1) + '" x2="93" y2="' + l.ly.toFixed(1) + '" stroke="' + l.col + '" stroke-width="0.6" opacity="0.5"/>';
      svg += '<text x="96" y="' + (l.ly + 3).toFixed(1) + '" font-size="10" font-weight="' + (l.bold ? "800" : "600") + '" fill="' + l.col + '" font-family="Inter,sans-serif">' + esc(l.txt) + "</text>";
    });
    if (flip != null) {
      svg += '<text x="12" y="' + (mT + 9) + '" font-size="8" fill="' + muted + '" font-family="Inter,sans-serif">' + esc(lz("calmer", "较平静")) + "</text>";
      svg += '<text x="12" y="' + (H - mB - 3) + '" font-size="8" fill="' + muted + '" font-family="Inter,sans-serif">' + esc(lz("jumpier", "较跳动")) + "</text>";
    }
    return svg + "</svg>";
  }
  function levelsMapHTML() {
    var s = cur.summary || {}, vh = cur.vol_hole || {}, spot = s.spot, regime = s.regime;
    var L = [];
    if (s.call_wall != null) {
      L.push({ cls: "cw", v: s.call_wall, str: s.call_wall_strength, sigma: s.call_wall_dist_sigma,
        tag_en: "Ceiling · call wall", tag_zh: "上沿 · 看涨墙",
        say_en: "Heavy call positioning caps rallies. A <b>daily close above " + price(s.call_wall) + "</b> releases upside.",
        say_zh: "大量看涨持仓压制上涨。<b>日线收于 " + price(s.call_wall) + " 之上</b>释放上行。" });
    } else if (s.magnet_up != null) {
      L.push({ cls: "cw", v: s.magnet_up, tag_en: "Resistance", tag_zh: "上方阻力",
        say_en: "Heaviest dealer gamma above price — a soft ceiling.", say_zh: "现价之上做市商Gamma最重处 — 软上沿。" });
    }
    if (s.gamma_flip != null) {
      L.push({ cls: "flip", v: s.gamma_flip, str: s.flip_strength,
        tag_en: "The flip", tag_zh: "翻转",
        say_en: "The line between <b>calm above</b> and <b>jumpy below</b>. On quiet days price tends to drift toward it.",
        say_zh: "<b>之上平静</b>、<b>之下跳动</b>的分界。平静日价格倾向漂向它。" });
    }
    if (s.max_pain != null) {
      var mE = "On quiet days price tends to drift toward " + price(s.max_pain) + ", where the most options expire worthless.";
      var mZ = "平静日价格倾向漂向 " + price(s.max_pain) + "（最多期权到期作废之处）。";
      if (regime === "short") { mE += " Pull is weak in this jumpy regime."; mZ += " 跳动体制下磁吸较弱。"; }
      L.push({ cls: "mp", v: s.max_pain, str: s.magnet_strength, sigma: s.magnet_dist_sigma,
        tag_en: "Magnet · max pain", tag_zh: "磁吸 · 最大痛点", say_en: mE, say_zh: mZ });
    }
    if (s.put_wall != null) {
      var fE = "Heavy put positioning cushions selloffs. A <b>daily close below " + price(s.put_wall) + "</b> opens downside.";
      var fZ = "大量看跌持仓缓冲下跌。<b>日线收于 " + price(s.put_wall) + " 之下</b>打开下行。";
      if (regime === "short" && s.gamma_flip != null) { fE += " Below the " + price(s.gamma_flip) + " flip the cushion is already gone."; fZ += " 跌破 " + price(s.gamma_flip) + " 翻转后缓冲已消失。"; }
      L.push({ cls: "pw", v: s.put_wall, str: s.put_wall_strength, sigma: s.put_wall_dist_sigma,
        tag_en: "Floor · put wall", tag_zh: "下沿 · 看跌墙", say_en: fE, say_zh: fZ });
    } else if (s.magnet_down != null) {
      L.push({ cls: "pw", v: s.magnet_down, tag_en: "Support", tag_zh: "下方支撑",
        say_en: "Heaviest dealer gamma below price — a soft floor.", say_zh: "现价之下做市商Gamma最重处 — 软下沿。" });
    }
    if (L.length < 2) {
      return '<div class="card anim d1"><div class="lmap-head"><span class="lmap-title">📍 ' + lz("Levels map", "价位地图") + "</span></div>" +
        '<p class="read-sub" style="margin-top:10px">' + esc(lz("No firm walls are mapped today — trade the chart and the expected range in the hero.", "今日无明确的墙 — 参考图表与上方预期区间。")) + "</p></div>";
    }
    var disp = L.slice();
    if (spot != null) {
      var flip = s.gamma_flip, above = flip != null && spot >= flip;
      disp.push({ cls: "spot", v: spot, tag_en: "Spot · you are here", tag_zh: "现价 · 当前所在",
        say_en: flip != null ? ("Currently " + pct(s.dist_to_flip_pct, 1) + " " + (above ? "above" : "below") + " the flip — " + (above ? "in the calmer zone." : "in the jumpier zone.")) : "Where price sits now.",
        say_zh: flip != null ? ("当前距翻转 " + pct(s.dist_to_flip_pct, 1) + "，" + (above ? "处于较平静区。" : "处于较跳动区。")) : "当前价格所在。" });
    }
    disp.sort(function (a, b) { return b.v - a.v; });
    var clsVar = { cw: "--up", pw: "--down", flip: "--info", mp: "--orange", spot: "--text" };
    var cards = disp.map(function (p, i) {
      var dist = (spot != null && p.cls !== "spot") ? ((p.v - spot) / spot * 100) : null;
      var distHtml = dist != null ? '<b class="' + (dist >= 0 ? "pos" : "neg") + '">' + pct(dist, 1) + "</b>" +
        (p.sigma != null ? ' <span class="muted">· ' + p.sigma + "σ</span>" : "") + " — " : "";
      var dots = (p.str != null) ? strengthDots(p.str, clsVar[p.cls]) : "";
      return '<div class="lvl ' + p.cls + '" style="animation-delay:' + (i * 0.04).toFixed(2) + 's">' +
        '<div class="lvl-top"><span class="lvl-tag">' + esc(lz(p.tag_en, p.tag_zh)) + "</span>" + dots +
          '<span class="lvl-val">' + price(p.v) + "</span></div>" +
        '<div class="lvl-say">' + distHtml + lz(p.say_en, p.say_zh) + "</div></div>";
    }).join("");
    var badge = "";
    if (vh.state && vh.state !== "NONE") { var v = VHS[vh.state] || VHS.NONE;
      badge = '<span class="vh-pill ' + v.cls + '">' + v.emo + " " + esc(lz(v.sh_en, v.sh_zh)) + "</span>"; }
    var foot = lz("Walls are measured from yesterday’s close, so price sits inside the band by construction — only a <b>daily close</b> beyond a level counts, never an intraday touch.",
      "墙以昨日收盘计算，价格按构造必在带内 — 只有<b>日线收盘</b>越过某价位才算数，盘中触碰不算。");
    return '<div class="card anim d1"><div class="lmap-head"><span class="lmap-title">📍 ' + lz("Levels map", "价位地图") +
      help(lz("A single picture of where dealer hedging clusters: the call-wall ceiling, the put-wall floor, the flip line (calm above / jumpy below) and the max-pain magnet. Band thickness ≈ strength. Levels to watch, never targets.",
              "做市商对冲聚集处的单幅图：看涨墙上沿、看跌墙下沿、翻转线（之上平静/之下跳动）与最大痛点磁吸。带厚≈强度。仅供观察，绝非目标价。")) + "</span>" + badge + "</div>" +
      '<div class="lmap"><div class="lmap-rail">' + buildRail(L, s) + '</div><div class="lmap-levels">' + cards + "</div></div>" +
      '<div class="lmap-foot">' + foot + "</div></div>";
  }

  // ========================================================================
  // THREE READS — regime · options tone · directional lean
  // ========================================================================
  function regimeReadHTML() {
    var s = cur.summary || {}, regime = s.regime;
    var word = regime === "long" ? lz("Calm", "平静") : regime === "short" ? lz("Jumpy", "跳动") : lz("Mixed", "中性");
    var scls = regime === "long" ? "up" : regime === "short" ? "down" : "info";
    var sub = regime === "long" ? lz("Dealer hedging pushes back against moves — price tends to pin and mean-revert.", "对冲逆势 — 价格倾向磁吸与均值回归。")
      : regime === "short" ? lz("Dealer hedging adds to moves — swings and air-pockets run bigger.", "对冲顺势 — 波动与急跌更大。")
      : lz("No clear dealer lean — hedging isn’t pushing either way today.", "做市商无明显倾向 — 今日对冲不偏向任一方。");
    var netCls = (s.net_gex_bn != null && s.net_gex_bn >= 0) ? "pos" : "neg";
    var foot = "";
    if (s.gamma_flip != null) { var ab = (s.dist_to_flip_pct != null && s.dist_to_flip_pct >= 0);
      foot = lz("Flip " + price(s.gamma_flip) + " · price " + pct(s.dist_to_flip_pct, 1) + " " + (ab ? "above" : "below"),
                "翻转 " + price(s.gamma_flip) + " · 价格 " + pct(s.dist_to_flip_pct, 1) + (ab ? " 在上" : " 在下")); }
    return '<div class="card read anim d1">' +
      '<div class="read-eyebrow">' + lz("Volatility regime", "波动率体制") +
        help(lz("Are dealers calming the market or making it jumpy today? The single most important read. Positive Net GEX = calming (pinning, smaller moves); negative = amplifying (trending, bigger moves). About volatility, not direction.",
                "今天做市商让市场平静还是跳动？最重要的读数。净GEX为正=平静（磁吸、更小波动）；为负=放大（趋势、更大波动）。关乎波动，非方向。")) + "</div>" +
      '<div class="read-state ' + scls + '">' + word + "</div>" +
      '<div class="read-sub">' + sub + "</div>" +
      '<div class="read-metric"><span class="big ' + netCls + '">' + sgn(s.net_gex_bn, 1) + '</span><span class="unit">' + lz("$bn / 1% · Net GEX", "十亿$/1% · 净GEX") + "</span></div>" +
      '<div class="read-spark" id="gx-spark"></div>' +
      (foot ? '<div class="read-foot">' + esc(foot) + "</div>" : "") +
    "</div>";
  }
  function toneReadHTML() {
    var s = cur.summary || {}, sk = s.skew;
    if (!sk || sk.rr25 == null) {
      return '<div class="card read anim d2"><div class="read-eyebrow">' + lz("Options tone", "期权情绪") +
        help(lz("Whether the market is paying up for downside protection (fear) or chasing upside (greed), read from the 25-delta risk-reversal — the price gap between equally-far puts and calls. Context, not a signal.",
                "市场是在为下行保护付费（恐慌）还是追逐上行（贪婪），取自25Δ风险逆转 — 等距看跌与看涨的价差。仅作背景，非信号。")) + "</div>" +
        '<div class="read-state info">—</div><div class="read-sub">' + esc(lz("Not enough strikes to read option skew for this name.", "该标的行权价不足，无法读取偏斜。")) + "</div></div>";
    }
    var tone = sk.tone;
    var word = tone === "fear" ? lz("Fear", "恐慌") : tone === "greed" ? lz("Greed", "贪婪") : lz("Balanced", "均衡");
    var scls = tone === "fear" ? "down" : tone === "greed" ? "up" : "info";
    var sub = tone === "fear" ? lz("The market is paying up for downside protection.", "市场为下行保护付溢价。")
      : tone === "greed" ? lz("The market is chasing upside — calls bid over puts.", "市场追逐上行 — 看涨比看跌更贵。")
      : lz("Puts and calls are priced roughly evenly.", "看跌与看涨定价大致均衡。");
    var foot = lz("25Δ risk-reversal on the " + (sk.expiry || "") + " chain" + (sk.days != null ? " (" + sk.days + "d)" : "") + ". Puts richer = fear; calls richer = greed.",
                  "25Δ风险逆转（" + (sk.expiry || "") + "）" + (sk.days != null ? " " + sk.days + "天" : "") + "。看跌更贵=恐慌；看涨更贵=贪婪。");
    return '<div class="card read anim d2"><div class="read-eyebrow">' + lz("Options tone", "期权情绪") +
      help(lz("Whether the market is paying up for downside protection (fear) or chasing upside (greed), read from the 25-delta risk-reversal — the price gap between equally-far puts and calls. Context, not a signal.",
              "市场是在为下行保护付费（恐慌）还是追逐上行（贪婪），取自25Δ风险逆转 — 等距看跌与看涨的价差。仅作背景，非信号。")) + "</div>" +
      '<div class="read-state ' + scls + '">' + word + '</div><div class="read-sub">' + sub + "</div>" +
      '<div class="read-metric"><span class="big">' + sgn(sk.rr25, 1) + '</span><span class="unit">' + lz("25Δ risk-reversal", "25Δ风险逆转") + "</span></div>" +
      '<div class="read-foot">' + esc(foot) + "</div></div>";
  }
  function tiltReadHTML() {
    var t = cur.tilt, meta = cur.meta || {}, grp = meta.grp || "";
    var hHelp = help(lz("Different option forces act on different clocks, so the lean is split BY TIME WINDOW. Each row is a directional tendency from delayed end-of-day positioning — not a trade, not a target. Direction is far less reliable than the regime; most names sit near a coin-flip.",
                        "不同期权力量作用于不同时间窗，故按时间窗拆分。每条为延迟收盘仓位的方向倾向 — 非交易、非目标。方向远不如体制可靠；多数标的接近抛硬币。"));
    if (!t || !t.legs || !t.legs.length) {
      return '<div class="card read anim d3"><div class="read-eyebrow">' + lz("Directional lean", "方向倾向") + hHelp + "</div>" +
        '<div class="read-state info">—</div><div class="read-sub">' + esc(lz("No directional lean today.", "今日无方向倾向。")) + "</div></div>";
    }
    var r = READS[t.read] || READS.balanced;
    var scls = r.cls === "up" ? "up" : r.cls === "down" ? "down" : (r.cls === "pin" || r.cls === "vol") ? "warn" : "info";
    var legs = t.legs.map(function (leg) {
      var a = tiltArrow(leg), sig = TILT_SIG[leg.signal] || { en: leg.signal, zh: leg.signal };
      return '<div class="leg"><div class="leg-ar ' + a.c + '">' + a.g + "</div>" +
        '<div><span class="leg-sig">' + esc(lz(sig.en, sig.zh)) + '</span><span class="leg-hz">' + esc(horizonText(leg.horizon, leg.days)) + "</span></div>" +
        '<div class="leg-why">' + esc(tiltWhy(leg)) + "</div></div>";
    }).join("");
    var frag = (grp !== "Index" && grp.indexOf("ETF") < 0) ? lz(" Single-name: the dealer sign is an assumption and can be wrong.", " 个股：做市商符号为假设、可能出错。") : "";
    return '<div class="card read anim d3"><div class="read-eyebrow">' + lz("Directional lean", "方向倾向") + hHelp + "</div>" +
      '<div class="read-state ' + scls + '">' + esc(lz(r.en, r.zh)) + "</div>" +
      '<div class="read-sub">' + esc(lz("Direction is far less reliable than the regime above.", "方向远不如上方体制可靠。")) + "</div>" +
      '<div class="read-legs">' + legs + "</div>" +
      '<div class="read-foot">' + esc(lz("Not a trade signal or target — a balance-of-pressures read from delayed EOD options.", "非交易信号或目标 — 延迟收盘期权的力量平衡读数。") + frag) + "</div>" +
    "</div>";
  }

  // ---- directional-tilt leg helpers (used by the lean read) ----
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
          "期权在磁吸位" + (leg.target != null ? "（" + price(leg.target) + "）" : "") + "聚集，平静日临近到期价格被" + (leg.toward === "up" ? "上" : "下") + "拉向它。");
      case "skew":
        return leg.dir === "down"
          ? lz("Puts are bid over calls (rr25 " + (leg.rr25 != null ? "+" + leg.rr25 : "+") + ") — the market is paying for downside protection (fear).", "看跌比看涨更贵（rr25 " + (leg.rr25 != null ? "+" + leg.rr25 : "+") + "）— 市场为下行保护付费（恐慌）。")
          : lz("Calls are bid over puts (rr25 " + (leg.rr25 != null ? leg.rr25 : "−") + ") — the market is chasing upside (greed).", "看涨比看跌更贵（rr25 " + (leg.rr25 != null ? leg.rr25 : "−") + "）— 市场追逐上行（贪婪）。");
      case "regime":
        return leg.dir === "two_sided"
          ? lz("Short gamma — dealers amplify moves, so swings run both ways and bigger.", "空头Gamma — 做市商放大走势，双向且更大。")
          : lz("Long gamma — dealers fade moves, so extremes toward either wall tend to mean-revert.", "多头Gamma — 做市商抑制走势，逼近任一墙的极端倾向均值回归。");
      default: return "";
    }
  }

  // ---- vol-hole label map + board cell (kept: renderBoard + the levels-map badge use these) ----
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

  // ========================================================================
  // STUDY SHELF — the raw options charts (collapsed by default; walls open)
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
      g(lz("Chain depth", "链路深度"), (s.n_strikes || "—") + "", s.tier === "full" ? lz("deep", "深度") : lz("thin — fragile", "稀疏 — 脆弱"))
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
                + "Magnitude signals (premium, 0DTE, ΔOI) populate once the S3 pull runs.",
              "流动数据自 " + FLOW_ACCRUAL_SINCE + " 起积累中 — 该标的暂无数据。"
                + "S3拉取运行后，量级信号（权利金、0DTE、ΔOI）将自动填充。"
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
      chip("0DTE", f.zerodte_share == null ? "—" : Math.round(f.zerodte_share * 100) + "%", "") +
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
          "Reliable (no signing): premium, 0DTE, new positions, P/C. Direction (~) is SOFT — tick-rule recovers net buy/sell only " + (sg.net_sign_recovery != null ? Math.round(sg.net_sign_recovery * 100) + "%" : "~") + " of the time on minute bars (option ticks are delta-dominated; per-trade " + (sg.per_trade_agreement != null ? Math.round(sg.per_trade_agreement * 100) + "%" : "~80%") + " vs NBBO, Databento-calibrated). EOD, as of " + (f.asof || "") + ". Never a buy/sell.",
          "可靠（无需定向）：权利金、0DTE、新建仓、P/C。方向(~)为软信号 — tick规则在分钟数据上仅约" + (sg.net_sign_recovery != null ? Math.round(sg.net_sign_recovery * 100) : "") + "%能还原净买卖（期权由delta主导；逐笔约" + (sg.per_trade_agreement != null ? Math.round(sg.per_trade_agreement * 100) : 80) + "% 对NBBO，经Databento校准）。收盘数据，截至 " + (f.asof || "") + "。绝非买卖信号。")) + "</div>" +
      "</div>";
  }
  function renderWeather() {
    var box = document.getElementById("gx-weather"), body = document.getElementById("gx-weather-body");
    var R = weatherData;
    if (!box || !body || !R || !R.snapshot || !R.game_plan || !R.game_plan.available) { if (box) box.hidden = true; return; }
    var snap = R.snapshot, gp = R.game_plan; box.hidden = false;
    var sb = document.getElementById("wx-scored"); if (sb) sb.hidden = !snap.scored_active;
    var clsMap = { "gp-calm": "wx-calm", "gp-up": "wx-up", "gp-jumpy": "wx-jumpy", "gp-warn": "wx-warn", "gp-neutral": "wx-neutral" };
    var rs = (snap.risk_score == null) ? 0 : snap.risk_score, pos = Math.max(2, Math.min(98, (rs + 1) / 2 * 100));
    var bullets = (gp.bullets || []).map(function (b) { return "<li>" + esc(lz(b.en, b.zh)) + "</li>"; });
    if (R.opex && R.opex.available) bullets.push("<li>" + esc(lz("Calendar", "日历") + ": " + (R.opex.phase || "").replace(/_/g, " ") + (R.opex.is_quad_cycle ? lz(" · quad-witching", " · 四巫日") : "") + " — " + (R.opex.read || "")) + "</li>");
    function stat(k, v2) { return v2 == null ? "" : '<span class="wx-stat"><span class="k">' + k + '</span><span class="v">' + v2 + "</span></span>"; }
    var stats = stat("VIX", snap.vix) +
      stat(lz("Term VIX/VIX3M", "期限 VIX/VIX3M"), snap.ts_slope != null ? (snap.ts_slope.toFixed(3) + " · " + esc(snap.ts_slope_state || "")) : null) +
      stat(lz("MOVE %ile", "MOVE分位"), snap.move_pctile != null ? Math.round(snap.move_pctile * 100) + "%" : null) +
      stat(lz("VRP %ile", "VRP分位"), snap.vrp_pctile != null ? Math.round(snap.vrp_pctile * 100) + "%" : null) +
      stat(lz("Insurance", "保险成本"), snap.insurance_cost ? esc(snap.insurance_cost) : null) +
      stat(lz("Gross scalar", "总仓系数"), snap.vol_target_scalar != null ? snap.vol_target_scalar.toFixed(2) + "×" : null);
    body.innerHTML =
      '<div class="wx-head ' + (clsMap[gp.css] || "wx-neutral") + '">' +
        '<span class="wx-icon">' + esc(gp.icon || "") + "</span>" +
        '<span class="wx-verdict">' + esc(lz(gp.verdict.en, gp.verdict.zh)) + "</span>" +
        '<span class="wx-gauge"><div class="track"><div class="mk" style="left:' + pos.toFixed(1) + '%"></div></div>' +
          '<div class="lbls"><span>' + lz("risk-off", "避险") + "</span><span>" + lz("risk-on", "偏多") + "</span></div></span></div>" +
      '<div class="wx-sub">' + esc(lz(gp.sub.en, gp.sub.zh)) + "</div>" +
      (bullets.length ? '<ul class="wx-bullets">' + bullets.join("") + "</ul>" : "") +
      '<div class="wx-stats">' + stats + "</div>" +
      '<div class="wx-foot">' + esc(lz("Validated on 1990+ history (term-structure + bond-vol forward-vol gate). A subtract-only risk/sizing read — not a stock picker, not an intraday timer. As of " + (snap.asof || "") + ".",
        "基于1990年以来历史验证（期限结构+债券波动率前瞻门槛）。仅做减法的风险/仓位读数 — 非选股、非盘中择时。截至 " + (snap.asof || "") + "。")) + "</div>";
  }
  function loadWeather() {
    if (weatherData !== undefined) { renderWeather(); return; }
    fetch("vol/regime.json").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { weatherData = j; renderWeather(); }).catch(function () { weatherData = null; });
  }

  function init() {
    renderBoard(); setupSearch(); setupBoardControls(); setupBoardHelp();
    loadWeather();
    selectSymbol(window.GEX_DEFAULT || (M[0] && M[0].key));
  }
  ["langchange", "themechange"].forEach(function (e) {
    document.addEventListener(e, function () { renderBoard(); renderWeather(); if (cur) renderDetail(); });
  });
  window.addEventListener("resize", function () { hideTip(); hideHelp(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();

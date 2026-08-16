/* cn_prophet_live.js — the runtime China board client (CN-W-L3 / CN-PR-3).

   Contract: research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md §6 (payload) + §7
   (delivery). Payload: `cn_prophet_live.states/v1`, served same-origin at
   live/cn_prophet_live.json by the VPS evaluator every ~5 min during the mainland
   session. Ships as a PAIRED plain-copy asset: templates/cn_prophet_live.js must
   byte-match site/cn_prophet_live.js.

   WHAT THIS IS FOR. china_stocks.html is server-rendered once a night, hours after the
   mainland close. Between bakes the board is a photograph of session N−1. This module is
   the only thing that makes it breathe: it patches TODAY'S provisional per-name reads onto
   yesterday's render, and stamps — loudly, in one place — which session the reader is
   actually looking at.

   PRESENTATION-TIER FENCE (§7.6, §11). This file writes to EXACTLY two places:
     1. #cn-live-board  — its own strip, an empty SSR container it owns outright;
     2. .pvcard[data-ticker] .pv-ov.pv-ovl > .pv-live — the chip slot _prophet_card.html.j2
        already reserves, empty and [hidden], on every card.
   It never touches card ordering, card membership, the pv-* verb hue, .pv-chip, .pv-edn,
   .pv-stp/.pv-stl, .pv-zn, .pv-trg, the table view, the facet bar, or any lane or count on
   the board. It computes NO score, NO rank and NO ordering — membership and states come
   from the payload and from nowhere else. asia-close's nightly build is the only confirmer.

   VOCABULARY IS LOAD-BEARING (DESIGN_DOCTRINE §2 Law 2/Law 5, operator 2026-07-27).
   Nothing here says fired, refuted, falsifier or 证伪 — those words are not front-facing on
   any cycle surface, at any tier. No raw machine state name reaches the reader either:
   `at_risk`, `session_break`, `limit_up_locked` and friends are payload vocabulary and are
   translated at the boundary, in both languages, by the copy tables below. Every state
   here settles at the evening build and every surface says so.

   HONEST BY CONSTRUCTION (§0.4). A name with no lawful current quote reads "No quote",
   never yesterday's price. Limit-locked and possibly-halted are distinct words, because a
   one-price session is a REAL price and a halt is an absence. Coverage is published in the
   strip. And yesterday's feed can never overwrite today's render, nor today's feed be
   discarded onto a stale one — that is feedIsCurrent() below, ported from
   china_risk_state_live.js, which exists because the same class of bug shipped a live
   badge over a staler number on this very page (operator report 2026-08-02).

   NO PULSE, NO STATUS DOT. On a 15-minute-delayed plane a green "live" dot is both
   unreachable and a claim of certainty. The session ribbon is the sanctioned proof of
   life: it draws the mainland day as two bars with a gap where lunch is, and fills to the
   artifact's own as-of — so a dead feed freezes it rather than marching it forward. */
(function () {
  "use strict";

  var URL_LIVE = "live/cn_prophet_live.json";
  var SCHEMA   = "cn_prophet_live.states/";

  var POLL_MS  = 120000;  /* producer writes every ~5 min; 120s bounds staleness at ~2 min */
  var FLOOR_MS = 30000;   /* floor on a visibility-triggered refetch */
  var CLOCK_MS = 60000;   /* local re-render so the age gate trips with the network down */
  var MAXAGE_MS = 2700000; /* 45 min — 9 missed passes. Intraday phases only (see _ageOk) */
  var MAX_FAILS = 3;      /* consecutive fetch failures before the layer tears down */

  /* Poll window, UTC minutes-of-day. The mainland session is 01:10–07:15 UTC year-round
     (no DST in Asia/Shanghai); 00:30–08:00 is that window plus a grace band on both ends —
     40 min for a late arming pass, 45 min for a late close board. Outside it the artifact
     cannot move, so neither does this module: a closed market must not cost 30 GETs/hour. */
  var POLL_FROM_UTC = 30;   /* 00:30 UTC */
  var POLL_TO_UTC   = 480;  /* 08:00 UTC */

  /* Mainland session boundaries, Asia/Shanghai minutes-of-day. */
  var AM_OPEN = 570, AM_SHUT = 690;    /* 09:30 – 11:30 */
  var PM_OPEN = 780, PM_SHUT = 900;    /* 13:00 – 15:00 */
  var CLOSE_GRACE = 905;               /* 15:05 — past this a missing close is worth saying */

  var DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

  /* ══ Copy tables ═══════════════════════════════════════════════════════════════
     The client maps machine states to plain words and NEVER surfaces a raw one. Keyed to
     PHASE (not to the row set) so the sentence under the board does not rewrite itself
     every five minutes — a subtitle that churns is its own kind of noise. */

  /* Phase word. `opening_auction` folds into pre-open and `closing_auction` reads as the
     late tape, exactly as §2's evaluator behaviour column describes them. */
  var CNL_PHASE = {
    pre_open:        ["Pre-open",    "开盘前"],
    opening_auction: ["Pre-open",    "开盘前"],
    morning:         ["Trading",     "盘中"],
    session_break:   ["Lunch break", "午间休市"],
    afternoon:       ["Trading",     "盘中"],
    closing_auction: ["Closing",     "尾盘"],
    post_close:      ["Just closed", "刚收盘"],
    closed:          ["Closed",      "已收盘"]
  };

  /* The stance line (Law 1 — every panel answers "so what do I do", even when the honest
     answer is nothing). Hard budget: 14 words / one line. */
  var CNL_SUB = {
    trading: ["Reads move while the market is open; the board settles tonight. Watch, don't chase.",
              "开市期间判读会变动，下方看板今晚才结算。观察为主 — 勿追高。"],
    brk:     ["Trading resumes at 13:00. Reads are frozen at 11:30 — nothing to do here.",
              "13:00 恢复交易。判读定格在 11:30 — 此刻无需操作。"],
    preopen: ["Yesterday's reads, waiting on the open. Nothing has moved yet — stand by.",
              "开盘前仍是昨日判读，尚未变动 — 静候开盘。"],
    closeb:  ["A first pass at today's close. Tonight's build settles it — don't act yet.",
              "今日收盘的第一遍读数。今晚的生成才算结算 — 暂勿据此操作。"],
    pending: ["Today's close is still coming in. Nothing below has settled — stand by.",
              "今日收盘仍在陆续到位。下方尚未结算 — 请稍候。"],
    closed:  ["Frozen at today's close. Tonight's build settles them — nothing to act on yet.",
              "已在今日收盘定格。今晚的生成完成结算 — 暂无可操作项。"]
  };

  /* The close-board lead-in. NOT "provisional close board": `provisional` is the correct
     word for the tier in the spec and the wrong word to say to a reader, who is owed the
     plain-word version (the same ruling the US W-L1 board shipped under — its shooter's
     banned list carries `provisional` for exactly this reason). "First read" carries the
     whole meaning: it is today's close, and something later revises it. */
  var CNL_CLOSE_HD = ["Today's close — first read", "今日收盘初值"];

  /* Per-name STATE words. `at_risk` renders "Below range" and never anything
     verdict-flavoured: at_risk is an internal state name, and every verdict phrasing of it
     invites the reader to hear a sell call on an ungraded provisional read, which the
     watch-don't-chase law forbids. "Below range" is an unimpeachable statement about the
     tape. `dormant` and `unknown` deliberately map to NOTHING — see _paintCards. */
  var CNL_STATE = {
    forming: ["Forming",     "正在形成"],
    near:    ["Near",        "临近"],
    faded:   ["Fell back",   "回落"],
    at_risk: ["Below range", "低于区间"]
  };
  var CNL_STATE_TIP = {
    forming: ["Today's tape has crossed the level tonight's build checks, and held it. Nothing is settled: the evening build decides, and it can differ. Price is delayed.",
              "今日盘面已上穿今晚生成要检查的价位，并且守住了。但这不是确认：今晚的生成才决定，结果可能不同。价格为延迟行情。"],
    near:    ["Trading close to the level tonight's build checks, but not through it yet. Watch — don't chase. Price is delayed.",
              "价格已接近今晚生成要检查的价位，但尚未穿过。观察为主 — 勿追高。价格为延迟行情。"],
    faded:   ["It crossed earlier today and has since traded back below that level. Nothing to do; the evening build re-settles it either way. Price is delayed.",
              "今日早前曾上穿，随后回落至该价位之下。无需操作；无论如何今晚的生成都会重新结算。价格为延迟行情。"],
    at_risk: ["Trading below the range tonight's build would still accept. Nothing on the board has changed yet, and this is not a sell call — the evening build re-settles it. Price is delayed.",
              "当前价格低于今晚生成仍会接受的区间。看板尚未发生变化，这也不是卖出建议 — 今晚的生成会重新结算。价格为延迟行情。"]
  };

  /* Per-name MARKET STATUS overlay. When it is anything but `trading` it REPLACES the
     state word rather than crowding in beside it: a locked or unquoted name has no
     meaningful live read to report, the regime IS the news, and the glance budget is one
     to two words. The state stays available underneath — the card's own verb chip is the
     nightly stance and this module never touches it.

     `session_break` is absent ON PURPOSE. It is true of every name at once, so painting it
     107 times would be a constant repeated per row (Law 4) and the pill spam of a vetoed
     idiom. Lunch is a BOARD fact: the strip says it once, and the frozen state chips stay
     exactly where 11:30 left them, which is what §2 means by states freezing.

     glyph: `◐` is the house provisional half-disc; `▲`/`▼` mark a limit lock (direction
     reads the same in both languages — it is the COLOUR that flips, via --ink-up/--ink-down
     below); `—` marks an absence. The glyph is a bare text node, not an l-en/l-zh span, so
     it survives the ≤680px rule that collapses these pills to their glyph. */
  var CNL_STATUS = {
    limit_up_locked:     ["Limit up",       "一字涨停", "cnlv-up",   "▲"],
    limit_down_locked:   ["Limit down",     "一字跌停", "cnlv-down", "▼"],
    suspended_suspected: ["Possibly halted", "或已停牌", "cnlv-off",  "—"],
    unavailable:         ["No quote",       "暂无行情", "cnlv-off",  "—"]
  };
  var CNL_STATUS_TIP = {
    limit_up_locked:     ["Locked at today's upside limit — a one-price session, not a missing quote. The read underneath still settles at tonight's build.",
                          "已封于当日涨停价 — 属于一字板行情，并非没有报价。下方判读仍以今晚的生成为准。"],
    limit_down_locked:   ["Locked at today's downside limit — a one-price session, not a missing quote. The read underneath still settles at tonight's build.",
                          "已封于当日跌停价 — 属于一字板行情，并非没有报价。下方判读仍以今晚的生成为准。"],
    suspended_suspected: ["No trades are coming through, so this name may be halted today. Yesterday's price is deliberately not shown in its place.",
                          "当前没有成交，该股今日可能停牌。此处刻意不用昨日价格顶替。"],
    unavailable:         ["No lawful current quote for this name right now. Yesterday's price is deliberately not shown in its place.",
                          "目前拿不到该股的合法实时报价。此处刻意不用昨日价格顶替。"]
  };

  /* The strip's `?` tip — Tier 2, ≤80 words, the sanctioned home for mechanics. The repaint
     disclosure lives HERE and not in the headline: "15.1%" is a statistic, "about 1 in 7 of
     these change again before the close" is information (Law 3), and neither belongs in a
     glance-tier stamp row. The precise figure rides the receipt line below it. */
  var CNL_TIP = [
    "Prices are the mainland delayed feed (15 minutes), re-read every five minutes while the market is open. A read here describes today's tape only — the evening build is what settles the board below, and it can differ. About 1 in 7 of these intraday reads changes again before the close. Coverage counts names with a lawful current quote; a name without one reads “no quote”, never yesterday's price.",
    "价格来自内地延迟行情（15分钟），开市期间每5分钟重读一次。此处的判读只反映当日盘面 — 真正结算下方看板的是今晚的生成，两者可能不同。这类盘中判读中，约每7个就有1个会在收盘前再次变化。覆盖数只统计当前有合法报价的个股；没有报价的显示「暂无行情」，绝不用昨天的价格顶替。"
  ];
  var CNL_TIP_RC = [
    "intraday repaint rate 15.1% · delayed feed floor 15 min · settles at the evening build",
    "盘中重绘率 15.1% · 延迟行情下限 15 分钟 · 以今晚生成结算"
  ];

  /* ══ Style ═════════════════════════════════════════════════════════════════════
     Injected once, on first paint, so a page that never receives a payload carries no
     bytes of this design at all. Every colour is an existing theme token: --prov (the
     provisional blue, the same hue --plvc gives the reserved chip, so strip and chips read
     as one system), --prov-ink (its text-grade twin, already light-corrected), --muted for
     absence, and --ink-up/--ink-down for the ONE genuinely price-directional thing here —
     a limit lock — which therefore flips with 红涨绿跌 for free under html[data-lang=zh].
     No red/green anywhere else: a state is not a price direction. */
  var CSS = [
    '#cn-live-board[hidden]{display:none}',
    /* class-level display out-specifies the UA [hidden] rule — the .pv-live[hidden] trap */
    '#cn-live-board{display:block;margin:9px 0 2px;padding:8px 12px 9px;border-radius:9px;',
      'border:1px solid color-mix(in srgb,var(--prov) 26%,transparent);',
      'border-left:3px solid var(--prov);',
      'background:color-mix(in srgb,var(--prov) 7%,var(--panel))}',
    '.cnlv-r1{display:flex;flex-wrap:wrap;align-items:center;gap:4px 7px;font-size:11.5px;',
      'font-weight:600;line-height:1.5;color:var(--muted)}',
    '.cnlv-dt{font-family:var(--font-mono,monospace);font-variant-numeric:tabular-nums;',
      'font-size:11px;font-weight:700;color:var(--text)}',
    '.cnlv-ph{font-weight:800;letter-spacing:.02em;color:var(--prov-ink)}',
    '.cnlv-n{font-family:var(--font-mono,monospace);font-variant-numeric:tabular-nums;',
      'font-weight:700;color:var(--text)}',
    '.cnlv-sep{opacity:.45}',
    '.cnlv-r2{margin:5px 0 0;font-size:11.5px;line-height:1.5;color:var(--muted)}',
    '.cnlv-r2 b{font-weight:700;color:var(--text)}',
    '#cn-live-board .help{margin-left:3px;vertical-align:1px}',
    /* ── THE SESSION RIBBON — this module's one geometric decision ────────────────
       The mainland day is two two-hour halves with a real hole between them, and that
       hole is the single thing about this market no US surface has to express. Two bars
       and a gap ARE the day; the fill runs to the artifact's own as-of, so at lunch the
       fill stops dead at the end of the morning bar with the gap visibly empty ahead —
       geometry and the words "Lunch break" saying the same thing. Anchored to the
       payload, never to the reader's clock: a dead feed must freeze this, not march it. */
    '.cnlv-day{display:inline-flex;align-items:center;gap:5px;flex:none;margin-right:1px}',
    '.cnlv-day i{display:block;position:relative;width:15px;height:4px;border-radius:2px;',
      'background:color-mix(in srgb,var(--prov) 20%,transparent)}',
    '.cnlv-day i::before{content:"";position:absolute;top:0;bottom:0;left:0;',
      'width:var(--f,0%);border-radius:2px;background:var(--prov)}',
    /* Close board: the day is whole, so the strip steps up rather than shouting. Deeper
       tint, the ◐ lead-in in ink, and a ribbon that is finally solid end to end. */
    '#cn-live-board.cnlv-close{background:color-mix(in srgb,var(--prov) 14%,var(--panel));',
      'border-color:color-mix(in srgb,var(--prov) 42%,transparent)}',
    '.cnlv-hd{font-weight:800;letter-spacing:.01em;color:var(--prov-ink)}',
    /* Pending is the one non-blue state: nothing has arrived and saying so is a caution,
       not a reading. Amber is directionless in both colour conventions. */
    '#cn-live-board.cnlv-pending{border-left-color:var(--ink-warn,var(--warn));',
      'background:color-mix(in srgb,var(--warn) 7%,var(--panel));',
      'border-color:color-mix(in srgb,var(--warn) 26%,transparent)}',
    '#cn-live-board.cnlv-pending .cnlv-ph,#cn-live-board.cnlv-pending .cnlv-hd{color:var(--ink-warn,var(--warn))}',
    '#cn-live-board.cnlv-pending .cnlv-day i::before{background:var(--ink-warn,var(--warn))}',
    '#cn-live-board.cnlv-pending .cnlv-day i{background:color-mix(in srgb,var(--warn) 20%,transparent)}',
    /* ── chip hues, riding the slot's own --plvc token ─────────────────────────── */
    '.pv-live.cnlv-up{--plvc:var(--ink-up,var(--up))}',
    '.pv-live.cnlv-down{--plvc:var(--ink-down,var(--down))}',
    '.pv-live.cnlv-off{--plvc:var(--muted)}',
    '.pv-live .cnlv-t{font-variant-numeric:tabular-nums;opacity:.72;font-weight:700}',
    '@media (max-width:680px){#cn-live-board{padding:7px 10px 8px}',
      '.cnlv-r1,.cnlv-r2{font-size:11px}}'
  ].join("");

  /* ══ Small helpers ═════════════════════════════════════════════════════════════ */

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  /* Both languages are written into the DOM at once so switching language never needs a
     re-render or a fresh fetch — and a node patched by the feed keeps switching after the
     reader changes language, which a single-language text node would not. */
  function BL(en, zh) {
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(zh == null ? en : zh) + "</span>";
  }

  /* ══ The Asia/Shanghai wall clock ══════════════════════════════════════════════
     Every window in this component is a MAINLAND clock window. The reader's own timezone
     is irrelevant to when the A-share tape moves, and a UTC-pinned one would put lunch in
     the wrong place. Asia/Shanghai has no DST, but Intl is still the honest way to ask. */
  var _cstFmt = null;
  function cst(d) {
    try {
      if (!_cstFmt) {
        _cstFmt = new Intl.DateTimeFormat("en-US", {
          timeZone: "Asia/Shanghai", hour12: false,
          year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
        });
      }
      var parts = _cstFmt.formatToParts(d), p = {}, i;
      for (i = 0; i < parts.length; i++) p[parts[i].type] = parts[i].value;
      var h = parseInt(p.hour, 10); if (h === 24) h = 0;   /* en-US hour12:false prints 24 */
      return { ymd: p.year + "-" + p.month + "-" + p.day, min: h * 60 + parseInt(p.minute, 10) };
    } catch (e) { return null; }
  }
  /* An ISO stamp as {ymd, min} in Shanghai, or null. Never throws, never guesses. */
  function cstOf(iso) {
    if (!iso) return null;
    var ms = Date.parse(iso);
    if (!isFinite(ms)) return null;
    return cst(new Date(ms));
  }
  function hm(min) {
    var h = Math.floor(min / 60), m = min % 60;
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }

  /* ══ Feed floor ════════════════════════════════════════════════════════════════
     The page is baked nightly; this artifact is published by the intraday VPS lane. The
     two can disagree in BOTH directions, and only one of them is safe: today's feed
     upgrading yesterday's render is the entire point of this module, while yesterday's
     feed repainting today's render would put a stale read behind a fresh stamp — the
     failure china_risk_state_live.js's own header describes shipping on this page.
     Captured once, BEFORE any DOM write, so a live overwrite can never feed back in. */
  var _pageSession;   /* undefined until first read; "" when the page carries none */
  function pageSession() {
    if (_pageSession !== undefined) return _pageSession;
    _pageSession = "";
    try {
      var best = "", t, i;
      /* The strip's own anchor carries the board's as-of, stamped by the render. */
      var host = document.getElementById("cn-live-board");
      t = host ? (host.getAttribute("data-session") || "").trim() : "";
      if (DATE_RE.test(t)) best = t;
      /* Belt and braces: the board's visible as-of stamps. Newest wins — the floor is
         the freshest thing the reader can already see, not the first one found. */
      var stamps = document.querySelectorAll("#standouts .rip-shelf-asof .l-en");
      for (i = 0; i < stamps.length; i++) {
        t = (stamps[i].textContent || "").replace(/[^0-9-]/g, "");
        if (DATE_RE.test(t) && t > best) best = t;
      }
      _pageSession = best;
    } catch (e) { _pageSession = ""; }
    return _pageSession;
  }

  /* True when the feed is at least as current as the rendered page. An unreadable feed
     session counts as behind: failing closed keeps the served render, which is always a
     real single-session snapshot. */
  function feedIsCurrent(d) {
    var floor = pageSession();
    var s = d && DATE_RE.test(String(d.session || "")) ? String(d.session) : "";
    if (!s) return false;                 /* a payload that will not name its session */
    if (!floor) return true;              /* page carries no as-of — nothing to hold */
    return s >= floor;
  }

  /* ══ Freshness ═════════════════════════════════════════════════════════════════
     §2's quote-age law, ported. The ceiling is measured against the expected latest
     observation — min(now, end of the current-or-last segment) — and NOT against wall
     clock. At 12:55 CST an artifact built at 11:32 is the newest thing that can exist, so
     measuring it against 12:55 would tear the layer down through every single lunch break;
     at 14:30 an artifact built at 10:15 is genuinely stale and must. This is the
     CN-specific correctness detail the US single-window model cannot express. */
  function expectedLatest(nowMin) {
    if (nowMin < AM_OPEN) return nowMin;          /* pre-open: nothing has happened yet */
    if (nowMin <= AM_SHUT) return nowMin;         /* morning */
    if (nowMin < PM_OPEN) return AM_SHUT;         /* lunch — anchored to 11:30 */
    if (nowMin <= PM_SHUT) return nowMin;         /* afternoon */
    return PM_SHUT;                               /* after 15:00 — anchored to the close */
  }
  function ageOk(d, now, nowCst) {
    /* A close board is a settled-for-the-day artifact, not a ticking intraday read: it
       stops being current when its SESSION does, which the session gate below owns. */
    if (d.revision === "close_provisional") return true;
    var built = Date.parse(d.built_at || "");
    if (!isFinite(built)) return false;                 /* undated ⇒ refused, never excused */
    var builtCst = cst(new Date(built));
    if (!builtCst || builtCst.ymd !== nowCst.ymd) return false;
    var anchor = expectedLatest(nowCst.min);
    var lagMin = anchor - builtCst.min;
    if (lagMin < 0) lagMin = 0;                         /* built after the anchor: fresh */
    return lagMin * 60000 <= MAXAGE_MS && (now - built) >= -300000;  /* 5-min clock slack */
  }

  /* ══ Gates ═════════════════════════════════════════════════════════════════════
     One place, first refusal wins, and every refusal returns null — which the caller
     turns into a full teardown to the SSR board. There is no partial paint. */
  function qualify(d, now) {
    if (!d || typeof d !== "object") return null;
    if (typeof d.schema !== "string" || d.schema.indexOf(SCHEMA) !== 0) return null;
    if (d.dark) return null;                            /* the producer declined to speak */
    var nowCst = cst(new Date(now));
    if (!nowCst) return null;
    if (!DATE_RE.test(String(d.session || ""))) return null;
    /* A session that is not today's mainland date cannot describe today's tape. Combined
       with the floor below, yesterday's board can never masquerade as today's. */
    if (String(d.session) !== nowCst.ymd) return null;
    if (!feedIsCurrent(d)) return null;
    if (!ageOk(d, now, nowCst)) return null;
    return { d: d, cst: nowCst };
  }

  /* ══ Teardown ══════════════════════════════════════════════════════════════════
     A flat list of every node this module has written to. Restoring is not "guess what it
     looked like": the SSR state of a chip slot is exactly `class="pv-live" hidden` and
     empty, and of the strip exactly empty and hidden, so the restore is a constant. */
  var _touched = [];
  var _painted = false;
  var _styled = false;
  var _sessionYmd = "";

  function teardown() {
    var i, el;
    for (i = 0; i < _touched.length; i++) {
      el = _touched[i];
      el.hidden = true;
      el.className = "pv-live";
      el.innerHTML = "";
      el.removeAttribute("data-tip-en");
      el.removeAttribute("data-tip-zh");
    }
    _touched.length = 0;
    var host = document.getElementById("cn-live-board");
    if (host) {
      host.className = "";
      host.innerHTML = "";
      host.hidden = true;
    }
    _painted = false;
  }

  /* ══ Card chips ════════════════════════════════════════════════════════════════
     The ONLY node touched on a card is its reserved .pv-live span, addressed through the
     slot's own selector so a card without one is simply skipped.

     THE CHIP IS NEWS, NOT A STATUS LIGHT. `dormant` and `unknown` paint nothing at all,
     and neither does a plainly trading name with no state worth reporting: a pill on 90 of
     107 cards is pill spam, it destroys the board's scannability, and it teaches the
     reader to stop seeing the pills that matter. Absent ⇒ hidden + empty ⇒ zero width and
     zero layout change, so a board with nothing to say renders byte-identical to the
     nightly one. */
  function paintCards(names) {
    var slots = document.querySelectorAll(".pvcard[data-ticker] .pv-ov.pv-ovl > .pv-live");
    var i, el, card, tk, st, c, tip, glyph, cls, since, html;
    _touched.length = 0;
    for (i = 0; i < slots.length; i++) {
      el = slots[i];
      card = el.closest ? el.closest(".pvcard") : null;
      tk = card ? card.getAttribute("data-ticker") : null;
      st = (tk && names && Object.prototype.hasOwnProperty.call(names, tk)) ? names[tk] : null;

      c = null; tip = null; glyph = "◐"; cls = ""; since = "";
      if (st && typeof st === "object") {
        var ms = String(st.market_status || "trading");
        if (CNL_STATUS[ms]) {
          /* The regime replaces the state word — see the CNL_STATUS note. */
          c = CNL_STATUS[ms]; tip = CNL_STATUS_TIP[ms];
          cls = c[2]; glyph = c[3];
        } else if (CNL_STATE[st.state]) {
          c = CNL_STATE[st.state]; tip = CNL_STATE_TIP[st.state];
          /* The time is shown only when `since` is genuinely part of THIS session — a
             state carried over from the prior close would otherwise print a wrong-day
             clock time with no date to disown it. */
          var sc = cstOf(st.since_ts);
          if (sc && sc.ymd === _sessionYmd) since = hm(sc.min);
        }
      }

      if (!c) {
        if (!el.hidden) {
          el.hidden = true; el.className = "pv-live"; el.innerHTML = "";
          el.removeAttribute("data-tip-en"); el.removeAttribute("data-tip-zh");
        }
        continue;
      }
      el.className = "pv-live" + (cls ? " " + cls : "");
      if (tip) { el.setAttribute("data-tip-en", tip[0]); el.setAttribute("data-tip-zh", tip[1]); }
      html = esc(glyph) + " " + BL(c[0], c[1]) +
             (since ? ' <span class="cnlv-t">' + esc(since) + "</span>" : "");
      if (el.innerHTML !== html) el.innerHTML = html;
      el.hidden = false;
      _touched.push(el);
    }
  }

  /* ══ The board strip ═══════════════════════════════════════════════════════════ */

  function seg(fromMin, toMin, atMin) {
    var f = (atMin - fromMin) / (toMin - fromMin);
    if (!(f > 0)) f = 0;
    if (f > 1) f = 1;
    return (f * 100).toFixed(0);
  }
  /* The ribbon, filled to the artifact's own as-of. `full` short-circuits it for the
     close board, where the day is complete by definition. */
  function ribbon(atMin, full) {
    var a = full ? "100" : seg(AM_OPEN, AM_SHUT, atMin);
    var b = full ? "100" : seg(PM_OPEN, PM_SHUT, atMin);
    return '<span class="cnlv-day" aria-hidden="true">' +
           '<i style="--f:' + a + '%"></i><i style="--f:' + b + '%"></i></span>';
  }
  function sep() { return '<span class="cnlv-sep">·</span>'; }

  function paintStrip(d, nowCst) {
    var host = document.getElementById("cn-live-board");
    if (!host) return;

    var phase = String(d.market_phase || "");
    var isClose = d.revision === "close_provisional";
    var pending = !!d.close_pending && (phase === "post_close" || phase === "closed") &&
                  nowCst.min >= CLOSE_GRACE;

    var builtCst = cstOf(d.built_at);
    var atMin = builtCst ? builtCst.min : nowCst.min;

    /* Stance key. Pending outranks the close board: a board that is still filling in must
       not wear the finished-close sentence. */
    var subKey = pending ? "pending"
               : isClose ? "closeb"
               : phase === "session_break" ? "brk"
               : (phase === "pre_open" || phase === "opening_auction") ? "preopen"
               : (phase === "post_close" || phase === "closed") ? "closed"
               : "trading";

    var ph = CNL_PHASE[phase] || CNL_PHASE.closed;
    var r1 = ribbon(atMin, isClose || phase === "closed" || phase === "post_close");

    /* ── the stamp row ─────────────────────────────────────────────────────────── */
    if (isClose) r1 += '<span class="cnlv-hd">◐ ' + BL(CNL_CLOSE_HD[0], CNL_CLOSE_HD[1]) + "</span>" + sep();
    r1 += '<span class="cnlv-dt">' + esc(String(d.session)) + "</span>";
    r1 += sep() + '<span class="cnlv-ph">' + BL(ph[0], ph[1]) + "</span>";

    /* ONE as-of for the whole strip (Law 4). The close board stamps the moment the close
       first became readable, which is a different and more useful fact than "written at".
       §6 puts `first_close_board_at` on `liveness` and §5 writes it into the close board;
       read BOTH rather than pick one, and fall back to `built_at` rather than to nothing. */
    var _cbAt = (d.close_board || {}).first_close_board_at || (d.liveness || {}).first_close_board_at;
    var asOfCst = isClose ? (cstOf(_cbAt) || builtCst) : builtCst;
    if (asOfCst) {
      r1 += sep() + BL("as of", "截至") +
            ' <span class="cnlv-n">' + esc(hm(asOfCst.min)) + "</span>";
    }

    var dly = Number(d.delay_floor_min);
    if (isFinite(dly) && dly > 0) {
      r1 += sep() + BL(dly + "-min delayed", "延迟" + dly + "分钟");
    }

    /* Coverage (§0.4 — coverage is published). On the close board the useful count is how
       much of the close is IN; intraday it is how many names have a lawful quote. A count
       the producer did not publish is NOT derived from a percentage here — the strip
       either states an observed pair or says nothing at all. */
    var cov = d.coverage || {}, cb = d.close_board || {};
    var closeCov = isClose || pending;   /* a close still filling in counts closes, not quotes */
    var _cbN = isFinite(Number(cb.close_n)) ? cb.close_n : cb.observable_n;
    var have = Number(closeCov && isFinite(Number(_cbN)) ? _cbN : cov.observable_n);
    var tot = Number(cov.armed_n);
    if (isFinite(have) && isFinite(tot) && tot > 0) {
      var n1 = '<span class="cnlv-n">' + esc(have) + "</span>";
      var n2 = '<span class="cnlv-n">' + esc(tot) + "</span>";
      r1 += sep() +
        '<span class="l-en">' + n1 + " of " + n2 + (closeCov ? " close prices in" : " quoted") + "</span>" +
        '<span class="l-zh">' + n2 + (closeCov ? "只中已到 " + n1 + "只收盘价" : "只中 " + n1 + "只有报价") + "</span>";
    }

    /* ── the stance line, plus the one `?` this panel gets ─────────────────────── */
    var sub = CNL_SUB[subKey];
    var r2 = BL(sub[0], sub[1]) +
      '<span class="help" data-tip-en="' + esc(CNL_TIP[0]) + '" data-tip-zh="' + esc(CNL_TIP[1]) +
      '" data-tip-rc-en="' + esc(CNL_TIP_RC[0]) + '" data-tip-rc-zh="' + esc(CNL_TIP_RC[1]) + '">?</span>';

    var html = '<div class="cnlv-r1">' + r1 + '</div><p class="cnlv-r2">' + r2 + "</p>";
    if (host.innerHTML !== html) host.innerHTML = html;
    host.className = isClose && !pending ? "cnlv-close" : (pending ? "cnlv-pending" : "");
    host.hidden = false;
  }

  /* ══ Render ════════════════════════════════════════════════════════════════════ */
  var _data = null, _fetchedAt = 0, _fetching = false, _fails = 0;

  function render() {
    if (!document.getElementById("cn-live-board")) return;
    var q = qualify(_data, Date.now());
    if (!q || _fails >= MAX_FAILS) { if (_painted) teardown(); return; }
    if (!_styled) {
      var s = document.createElement("style");
      s.id = "cnlv-css"; s.textContent = CSS;
      document.head.appendChild(s);
      _styled = true;
    }
    _sessionYmd = String(q.d.session);
    try {
      paintCards(q.d.names && typeof q.d.names === "object" ? q.d.names : null);
      paintStrip(q.d, q.cst);
      _painted = true;
    } catch (e) { teardown(); }
  }

  /* ══ Fetch ═════════════════════════════════════════════════════════════════════
     Graceful-absent: 404 (not shipped yet) and 401 (the artifact is served under /live/,
     so anonymous readers are gated out by design) are indistinguishable from here and
     need no distinction — both mean "no runtime layer", and the SSR board is the whole
     product for those readers. A LATER failure keeps the last good payload only until the
     gates refuse it; three in a row is a route that has gone away, and the layer goes with
     it rather than pinning one frozen read on the board. */
  function inPollWindow(now) {
    var m = now.getUTCHours() * 60 + now.getUTCMinutes();
    return m >= POLL_FROM_UTC && m <= POLL_TO_UTC;
  }

  function tick(force) {
    var now = new Date();
    if (!force && !inPollWindow(now)) { render(); return; }
    if (_fetching) return;
    _fetching = true;
    fetch(URL_LIVE + "?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function (j) {
        if (j && typeof j === "object" && typeof j.schema === "string" &&
            j.schema.indexOf(SCHEMA) === 0) { _data = j; _fetchedAt = Date.now(); _fails = 0; }
        else { _fails++; }
        _fetching = false;
        render();
      })
      .catch(function () {
        _fetching = false;
        _fails++;
        render();
      });
  }

  function boot() {
    if (!document.getElementById("cn-live-board")) return;   /* not this page */
    tick(false);
    setInterval(function () { if (!document.hidden) tick(false); }, POLL_MS);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && (Date.now() - _fetchedAt) > FLOOR_MS) tick(false);
    });
    /* A local clock with no network, so the age gate still trips — and the layer still
       tears down — when the producer, the route or the reader's connection has gone. */
    setInterval(render, CLOCK_MS);
  }

  /* Test seam, declared BEFORE boot so requiring this file under node never reaches the
     DOM below. The gates are the half of this file that decides whether a reader is shown
     a stale board; without a seam they would be provable only by grepping source text,
     which passes on a comment. `expectedLatest` and `ageOk` are pure; `qualify` reaches
     the DOM only through pageSession(), whose own try/catch answers "no floor" off-page. */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { qualify: qualify, feedIsCurrent: feedIsCurrent, ageOk: ageOk,
                       expectedLatest: expectedLatest, SCHEMA: SCHEMA };
  }

  if (typeof document === "undefined") return;
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();

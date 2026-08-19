/* ═══════════════════════════════════════════════════════════════════════════
   PROPHET OPERATOR LAB — the R5 controller (D-LAB-R5)

   This file is the mockup stand-in for LAB-0 §6.5's ONE `ProphetBoardController`:
   the sole painter of the principal grid, holding `desiredMode`, `labSelection`,
   `labClass` and the Lab payload. It is ADDITIVE — board.js (the frozen R4
   reference) is loaded unmodified and is still the only thing that paints LIVE.

   THREE LAWS THIS FILE EXISTS TO MAKE TRUE, not merely to assert:

   1. LAB → LIVE re-derives the live board from the CURRENT source; it never
      restores a pre-LAB snapshot. `repaintLive()` destroys the board subtree
      and RE-EXECUTES board.js, so a LIVE page after a Lab excursion is
      produced by the same code path as a cold load — there is no cached DOM
      that could be stale. The harness prints the repaint count so the
      behaviour is observable rather than claimed.

   2. A fresh page ALWAYS defaults LIVE. The mode control never writes the URL
      or storage; `desiredMode` is in-memory. `?mode=lab` is a HARNESS lens for
      hand inspection only, and tools/capture.py CLICKS the control instead of
      using it (R4's own standard: a capability that only exists after a click
      cannot be evidenced by a URL).

   3. LAB stale / empty / unavailable stays visibly LAB. There is no code path
      from a degraded Lab feed to LIVE content under a LAB label: when the feed
      has nothing, the Lab says so in its own voice and names what still works.

   The Lab has zero authority (LAB-0 §1): this file reads, filters, joins and
   decorates. It mints nothing, ranks nothing, and cannot reach Prophet state.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var L = window.PROPHET_LAB;
  var B = window.BOARD;
  var root = document.documentElement;
  var qs = new URLSearchParams(location.search);

  var BOARD_IDS = L.boards.map(function (b) { return b.id; });

  /* ── controller state ──────────────────────────────────────────────────
     `desiredMode` is memory, never a URL. The harness may seed it once. */
  var C = {
    desiredMode: qs.get("mode") === "lab" ? "lab" : "live",
    labSelection: BOARD_IDS.indexOf(qs.get("board")) >= 0 ? qs.get("board") : "lab-all-early-v1",
    labClass: ["all", "live", "seed"].indexOf(qs.get("cls")) >= 0 ? qs.get("cls") : "all",
    feed: ["ok", "stale", "down", "empty"].indexOf(qs.get("feed")) >= 0 ? qs.get("feed") : "ok",
    repaints: 0
  };

  /* OPERATOR-ONLY. The Lab is an authenticated operator surface: an anonymous
     or unentitled reader never sees the affordance at all — not a disabled
     control, not a teaser. `?op=0` proves the page is the R4 board exactly. */
  var operator = qs.get("op") !== "0" && qs.get("state") !== "anon";

  function lang() { return root.getAttribute("data-lang") === "zh" ? "zh" : "en"; }
  function t(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + "</span>";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function tip(tEn, tZh, bEn, bZh, rcEn, rcZh) {
    return ' tabindex="0" data-tip-t-en="' + esc(tEn) + '" data-tip-t-zh="' + esc(tZh) +
           '" data-tip-en="' + esc(bEn) + '" data-tip-zh="' + esc(bZh) + '"' +
           (rcEn ? ' data-tip-rc-en="' + esc(rcEn) + '" data-tip-rc-zh="' + esc(rcZh || rcEn) + '"' : "");
  }

  /* THE RULED LEXICON, verbatim from the R4 reference (board.js LEX / the
     J9C-J10 lifecycle ruling §6). Quoted, never re-authored: the Prophet
     comparison must speak Prophet's own words or it is a second vocabulary
     for one referent. */
  var LEX = {
    watch:       { en: "Watch",       zh: "观察" },
    ready:       { en: "Ready",       zh: "就绪" },
    entered:     { en: "Entered",     zh: "入场" },
    delivering:  { en: "Delivering",  zh: "达标" },
    overtime:    { en: "Overtime",    zh: "超时" },
    invalidated: { en: "Invalidated", zh: "失效" },
    resolved:    { en: "Resolved",    zh: "已结" }
  };

  /* Plain-word bodies for each reading. The exact expert slug NEVER appears
     above the fold; it travels on the receipt line of the LENS popover, which
     is the sanctioned Tier-2 home for machine identity (DESIGN_DOCTRINE §1). */
  var EXBODY = {
    g0_grey_dot: [
      "The first mark our earliest detector puts on a name. It says something started, not that anything is ready.",
      "最早的检测器给这只股票打上的第一个标记。它表示「有事情开始了」，并不表示可以操作。"],
    c1_live_washout: [
      "A sharp sell-off that has not finished yet. Shown while it is still running, which is why it can change.",
      "一轮尚未结束的急跌。因为还在进行中，所以随时可能变化。"],
    c2a_kd_cross: [
      "Two momentum lines crossed back upward — the reading we have watched longest.",
      "两条动能线重新上穿 —— 我们观察时间最长的一项读数。"],
    c2b_k_slope: [
      "The momentum line stopped falling and turned upward.",
      "动能线停止下行并开始上行。"],
    c2c_higher_k_low: [
      "The latest momentum low came in above the previous one.",
      "最近一个动能低点高于上一个低点。"],
    c2d_hist_trough: [
      "Downward momentum reached its deepest point and began to ease.",
      "下行动能达到最深处后开始收敛。"],
    c2e_hist_curvature: [
      "Momentum is still negative but the curve has begun to bend upward.",
      "动能仍为负，但曲线已经开始上弯。"],
    c2f_rebound_atr: [
      "The bounce off the low is large relative to this name's own recent range.",
      "自低点的反弹幅度，相对该股自身近期波动区间已经不小。"]
  };

  /* ── the deterministic demo change, exactly as R4 does it. `quotes.json`
        carries 27 index/futures symbols and no per-ticker intraday change, so
        these are the ONLY fabricated numbers on the row and they are marked
        data-mock-live in the DOM, as the R4 reference marks its own. ─────── */
  function demoChange(tk) {
    var h = 0, i;
    for (i = 0; i < tk.length; i++) h = (h * 31 + tk.charCodeAt(i)) >>> 0;
    return ((h % 701) - 320) / 100;
  }

  /* ═══════════════ selection ════════════════════════════════════════════ */
  function boardDef(id) {
    for (var i = 0; i < L.boards.length; i++) if (L.boards[i].id === id) return L.boards[i];
    return L.boards[L.boards.length - 1];
  }
  function boardRows(id) {
    if (C.feed === "down" || C.feed === "empty") return [];
    var ids = boardDef(id).rows, out = [];
    L.rows.forEach(function (r) { if (ids.indexOf(r.id) >= 0) out.push(r); });
    return out;   /* already newest-first from the generator; sort law is §3 */
  }
  function classFilter(rows) {
    if (C.labClass === "live") return rows.filter(function (r) { return r.cls === "live_forward"; });
    if (C.labClass === "seed") return rows.filter(function (r) { return r.cls === "seed"; });
    return rows;
  }

  /* ═══════════════ 1. MODE CONTROL ══════════════════════════════════════
     Quiet at rest, loud when engaged, and — on the LIVE board — COSTING NO
     VERTICAL SPACE. The control mounts inline in the page's existing status
     cluster (`.bh-stamp`, beside the freshness token and the as-of), so the
     production composition below it is unmoved: same ladder position, same
     cards above the fold, at 1440 and at 390. A reference that pushed the
     board down by a row to hold its own new affordance would be paying for
     the Lab out of the product's budget.

     In LAB the status cluster belongs to a different producer and is replaced,
     so the control re-mounts into the Lab band with the mode eyebrow. */
  function segHtml() {
    var h = '<span class="lab-seg" role="radiogroup" aria-label="Board mode">';
    h += '<button type="button" role="radio" data-mode="live" aria-checked="' +
         (C.desiredMode === "live") + '" tabindex="' + (C.desiredMode === "live" ? "0" : "-1") +
         '">' + t("Live", "实时") + "</button>";
    h += '<button type="button" role="radio" data-mode="lab" aria-checked="' +
         (C.desiredMode === "lab") + '" tabindex="' + (C.desiredMode === "lab" ? "0" : "-1") +
         '">' + t("Lab", "实验台") + "</button>";
    return h + "</span>";
  }
  function modebar() {
    return '<div class="lab-modebar"><span class="lab-eyebrow"><span class="dtp-dot"></span>' +
      t("Lab &middot; read-only", "实验台 &middot; 只读") + "</span>" + segHtml() + "</div>";
  }
  function mountModebar() {
    if (!operator) return;
    var stamp = document.querySelector(".bh-stamp");
    if (!stamp || stamp.querySelector(".lab-seg")) return;
    stamp.insertAdjacentHTML("beforeend",
      '<span class="lab-opv">' + t("Operator view", "操作台视图") + "</span>" + segHtml());
  }

  /* ═══════════════ 2. THE LAB PLANE ═════════════════════════════════════ */
  function feedStamp() {
    var g = C.feed === "stale" ? L.stale_gen : L.gen;
    var h = '<div class="lab-stamp">';
    if (C.feed === "down") {
      h += '<span class="lab-feed lab-feed--rest"><span class="dtp-dot"></span>' +
           t("Feed unavailable", "数据源不可用") + "</span>";
      return h + "</div>";
    }
    if (C.feed === "stale") {
      h += '<span class="lab-feed lab-feed--rest"><span class="dtp-dot"></span>' +
           t("Feed behind", "数据源滞后") + "</span>";
    } else {
      h += '<span class="lab-feed"><span class="dtp-dot"></span>' +
           t("Feed reporting", "数据源正常") + "</span>";
    }
    h += '<span class="dtp-asof">' + t(
      "last pass " + g.hm + " ET &middot; " + g.day.en,
      "最近一次 " + g.hm + " 美东 &middot; " + g.day.zh) + "</span>";
    return h + "</div>";
  }

  function band() {
    var h = '<div class="lab-band" data-mock-lab="1">' + modebar() +
            '<div class="lab-band-top"><div>';
    h += '<p class="lab-purpose">' + t(
      "Early-entry candidates as they are detected, before Prophet writes a plan.",
      "早期入场候选：在 Prophet 形成计划之前，检测到即呈现。") + "</p>";
    /* Law 1 — a stance on the glance tier, even when the stance is "watch". */
    h += '<p class="lab-stance">' + t(
      "Watch &mdash; don&rsquo;t chase. Nothing here is a Prophet call.",
      "观察，勿追。此处内容不构成 Prophet 的判断。") + "</p>";
    h += '<span class="lab-auth"' + tip(
      "What this view can and cannot do", "本视图的权限",
      "The Lab shows what the detectors saw. It does not rank names, decide position size, open or close anything, or change a Prophet plan in any way. Everything below is a read of another system's output.",
      "实验台只呈现检测器看到的内容。它不对股票排序，不决定仓位，不开仓不平仓，也不会以任何方式改动 Prophet 计划。以下全部内容都只是对另一套系统输出的读取。",
      "authority: rank=false · gate=false · size=false · originate=false · mutate_prophet=false (LAB-0 §1/§5). Source: " + L.source.pack + " → " + L.source.event + ". Kill switch: " + L.source.kill + ".",
      "权限位：rank=false · gate=false · size=false · originate=false · mutate_prophet=false（LAB-0 §1/§5）。来源：" + L.source.pack + " → " + L.source.event + "。停用开关：" + L.source.kill + "。") + ">" +
      t("Observation only &mdash; nothing here ranks, sizes, or changes a plan.",
        "仅供观察 —— 不参与排序、仓位或任何计划变更。") + "</span>";
    h += "</div>" + feedStamp() + "</div>";

    /* the Lab's own degraded-feed disclosure. Deliberately NOT production's
       behind-the-tape banner: that one describes the plan book's price
       vintage, and re-using its words for a different producer would tell the
       reader the wrong thing is late. */
    if (C.feed === "stale") {
      var mins = L.stale_gen.behind_min, hrs = Math.floor(mins / 60), rem = mins % 60;
      h += '<p class="lab-note lab-note--warn">' + t(
        "The last pass that reached this view was " + L.stale_gen.hm + " ET, <b>" + hrs +
        "h " + rem + "m</b> ago. Everything below is from that pass &mdash; nothing newer has arrived.",
        "最近送达本视图的一次采集是美东 " + L.stale_gen.hm + "，距今 <b>" + hrs + " 小时 " + rem +
        " 分</b>。以下内容全部来自那一次采集，之后没有新的数据到达。") + "</p>";
    }
    h += selectors() + "</div>";
    return h;
  }

  function selectors() {
    var h = '<div class="lab-sel-wrap"><div class="lab-sel" role="group" aria-label="Lab boards">';
    L.boards.forEach(function (b) {
      var on = b.id === C.labSelection;
      var n = (C.feed === "down" || C.feed === "empty") ? 0 : b.rows.length;
      h += '<button type="button" data-lab-board="' + b.id + '" aria-pressed="' + on + '"' +
           tip(lang() === "zh" ? b.zh : b.en, b.zh,
               (lang() === "zh" ? b.sub_zh : b.sub_en), b.sub_zh,
               b.rc_en, b.rc_zh) + ">" +
           t(b.en, b.zh) + '<span class="lab-n">' + n + "</span></button>";
    });
    return h + "</div></div>";
  }

  function meta(rows, all) {
    var b = boardDef(C.labSelection);
    var lf = all.filter(function (r) { return r.cls === "live_forward"; }).length;
    var sd = all.length - lf;
    var h = '<div class="lab-meta">';
    h += '<span class="lab-sub">' + t(b.sub_en, b.sub_zh) + "</span>";
    /* the sort key and its basis are STATED, because two clocks feed one
       stream and a reader must know which one ordered the row they are on.
       At 390w the sentence is DEMOTED to this chip's LENS rather than cut —
       demotion with a landing, never silent removal (§15). */
    h += '<span class="lab-split"' + tip(
      "How this stream is ordered", "本时间流的排序方式",
      "Newest first. A row we watched live is placed by the moment we first saw it; a historical row is placed by the signal's own date, because no sighting time exists for it.",
      "按时间倒序。实时观测到的记录按首次看到的时刻排列；历史记录按信号自身的日期排列，因为它没有观测时刻。") + ">" + t(
      "<b>" + lf + "</b> live &middot; <b>" + sd + "</b> seeds",
      "实时 <b>" + lf + "</b> &middot; 回溯 <b>" + sd + "</b>") + "</span>";
    h += '<span class="lab-basis">' + t(
      "Newest first &mdash; by first sighting where there is one, otherwise by the signal&rsquo;s own date.",
      "按时间倒序 —— 有首次观测时间的用该时间，否则用信号自身的日期。") + "</span>";
    h += '<span class="lab-cls-filter" role="group" aria-label="Observation class">';
    [["all", "All", "全部"], ["live", "Live only", "仅实时"], ["seed", "Seeds only", "仅回溯"]]
      .forEach(function (o) {
        h += '<button type="button" data-lab-cls="' + o[0] + '" aria-pressed="' +
             (C.labClass === o[0]) + '">' + t(o[1], o[2]) + "</button>";
      });
    h += "</span></div>";
    return h;
  }

  /* ── one observation ─────────────────────────────────────────────────── */
  function row(r) {
    var seed = r.cls === "seed";
    var h = '<li class="lab-row ' + (seed ? "lab-row--seed" : "lab-row--live") +
            '" data-mock-lab="1" data-obs="' + esc(r.id) + '">';

    /* WHEN — the spine cell. A live sighting can print a clock time because
       the feed supplied one. A seed cannot: `signal_known_ts` was never
       supplied and LAB-0 §4 forbids reconstructing it, so the slot prints the
       signal's own date and says, in the label, that this is not a sighting. */
    h += '<div class="lab-when"><span class="lab-node" aria-hidden="true"></span>';
    if (seed) {
      h += '<b class="lab-t">' + t(r.sig.en, r.sig.zh) + "</b>";
      h += '<span class="lab-tl">' + t("signal date<br>not a sighting", "信号日期<br>非观测记录") + "</span>";
    } else {
      h += '<b class="lab-t">' + esc(r.first.hm) + '<i class="lab-tz">ET</i></b>';
      h += '<span class="lab-tl">' + t("first seen<br>" + r.first.day.en,
                                       "首次观测<br>" + r.first.day.zh) + "</span>";
    }
    h += "</div>";

    /* CHART FIRST — same order as the Prophet card, and the same printed null
       at the same height when the payload carries no spark for this ticker. */
    h += '<div class="lab-chart">';
    h += r.spark ? '<div class="lab-spark">' + r.spark + "</div>"
                 : '<div class="lab-nochart"><span>' + t("No chart yet", "暂无图表") + "</span></div>";
    /* The quote slot is UNCONDITIONAL and keyed on data-sym, exactly as the
       R4 card is: in production live.js paints .nb-px/.nb-chg client-side for
       100% of rows regardless of the enrichment join, because data-sym is an
       attribute rather than a payload field. Un-hydrated it reads em dashes in
       muted ink — price and change together, never one without the other. */
    var chg = demoChange(r.tk);
    h += '<div class="lab-q" data-sym="' + esc(r.tk) + '" data-mkt="us">';
    if (r.px == null) {
      h += '<span class="nb-px">&mdash;</span><span class="nb-chg">&mdash;</span>';
    } else {
      h += '<span class="nb-px">$' + Number(r.px).toFixed(2) + "</span>";
      h += '<span class="nb-chg ' + (chg >= 0 ? "up" : "down") + '" data-mock-live="1">' +
           (chg >= 0 ? "+" : "&minus;") + Math.abs(chg).toFixed(2) + "%</span>";
    }
    h += "</div></div>";

    /* IDENTITY + THE EXACT READINGS */
    h += '<div class="lab-id"><div class="lab-idw"><a class="lab-open" href="stock.html#' +
         esc(r.tk) + '"><b class="lab-tk">' + esc(r.tk) + "</b>" +
         (r.nm ? '<span class="lab-nm">' + esc(r.nm) + "</span>" : "") + "</a></div>";
    if (r.sec) h += '<div class="lab-sec">' + esc(r.sec) + "</div>";
    h += '<div class="lab-chips">';
    if (seed) {
      h += '<span class="lab-cls lab-cls--seed"' + tip(
        "Retrospective seed", "回溯样本",
        "A historical event, shown so you can see the shape it makes. It is not evidence that we saw anything early, and it can never carry a lead over Prophet.",
        "这是一条历史事件，呈现出来是为了让您看清它的形态。它不能作为「我们提前看到」的证据，也永远不会带有相对 Prophet 的提前量。",
        "observation_class = retrospective_seed · evidence_eligible = false · measured lead = null, always (LAB-0 §4). signal_known_ts was not supplied and is never reconstructed.",
        "observation_class = retrospective_seed · evidence_eligible = false · 测得提前量恒为 null（LAB-0 §4）。emitter 未提供 signal_known_ts，且我们不做任何重建。") + ">" +
        t("Seed &middot; history, not a sighting", "回溯样本 &middot; 非实时观测") + "</span>";
    } else {
      h += '<span class="lab-cls lab-cls--live"' + tip(
        "Live sighting", "实时观测",
        "The feed carried this for the first time at " + r.first.hm + " ET on " + r.sig.en +
        ". It is a new observation, not history — so it is the only kind of row that can show a lead.",
        "数据源在 " + r.sig.zh + " 美东 " + r.first.hm + " 首次带来这条记录。它是新的观测，不是历史 —— 因此只有这类行可以显示提前量。",
        "observation_class = live_forward · first_observed_at derived from the live pack envelope pass_ts at the consumption plane; the immutable event is never mutated (LAB-0 §4).",
        "observation_class = live_forward · first_observed_at 由消费层的 live pack envelope pass_ts 推导；不可变事件本身从不被改写（LAB-0 §4）。") + ">" +
        t("Live sighting", "实时观测") + "</span>";
    }
    /* one chip per expert — identities are never merged into "3 signals"
       (DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED) */
    r.ex.forEach(function (e) {
      var body = EXBODY[e.exp] || ["", ""];
      h += '<span class="lab-ex"' + tip(
        lang() === "zh" ? e.zh : e.en, e.zh, body[0], body[1],
        e.det + (e.det.indexOf("C2_") === 0 ? " / " + e.exp : ""),
        e.det + (e.det.indexOf("C2_") === 0 ? " / " + e.exp : "")) + ">" +
        t(e.en, e.zh) + "</span>";
    });
    h += "</div></div>";

    /* PROPHET — quoted, in Prophet's own ruled words. Never restated. */
    h += '<div class="lab-pro"><div class="lab-pro-row">';
    h += '<div class="lab-pro-eb">' + t("Prophet", "Prophet") + "</div></div>";
    if (r.pro) {
      var lx = LEX[r.pro.life] || { en: r.pro.life, zh: r.pro.life };
      h += '<div class="lab-pro-state">' + t(lx.en, lx.zh) + "</div>";
      if (r.pro.opened) {
        h += '<div class="lab-pro-when">' + t(
          "plan opened " + r.pro.opened.en, "计划开启于 " + r.pro.opened.zh) + "</div>";
      }
    } else {
      h += '<div class="lab-pro-state lab-pro-state--none">' +
           t("Not on the board", "尚未进入名单") + "</div>";
      h += '<div class="lab-pro-when">' + t("no plan tonight", "今晚没有计划") + "</div>";
    }
    h += lead(r);
    h += "</div></li>";
    return h;
  }

  /* THE LEAD SLOT. Only a true live-forward observation may ever carry a
     measured number (LAB-0 §4). Every other case prints WHY there is none —
     an empty slot would read as "zero lead", which is a claim nobody made. */
  function lead(r) {
    if (r.cls === "live_forward" && r.lead != null) {
      var d = Math.abs(r.lead);
      return '<span class="lab-lead">' + t(
        "Seen <b>" + d + "</b> day" + (d === 1 ? "" : "s") + " before Prophet",
        "比 Prophet 早 <b>" + d + "</b> 天看到") + "</span>";
    }
    if (r.cls === "live_forward" && !r.pro) {
      return '<span class="lab-lead lab-lead--none"' + tip(
        "Nothing to compare yet", "暂无可比对象",
        "We saw this today and Prophet has no plan on this name, so there is no plan date to measure against. If a plan opens later, the comparison appears then.",
        "我们今天看到了它，而 Prophet 目前对这只股票没有计划，因此没有可比的计划日期。若之后开启计划，这里会出现比较结果。") +
        ">" + t("Nothing to compare yet", "暂无可比对象") + "</span>";
    }
    if (r.cls === "live_forward") {
      return '<span class="lab-lead lab-lead--none"' + tip(
        "No lead here", "此处没有提前量",
        "Prophet already had a plan open on this name before we saw this. That is a real result and it is shown as it is.",
        "在我们看到这条记录之前，Prophet 已经对这只股票开启了计划。这是一个真实结果，如实呈现。") +
        ">" + t("No lead &mdash; Prophet was first", "无提前量 —— Prophet 更早") + "</span>";
    }
    return '<span class="lab-lead lab-lead--none"' + tip(
      "Lead cannot be measured", "无法测量提前量",
      "This is a historical event. The feed never supplied the moment it was first observed, and we do not invent one — so there is no honest number to put against Prophet&rsquo;s plan date.",
      "这是一条历史事件。数据源从未提供它被首次观测到的时刻，我们也不会编造一个 —— 因此没有可以与 Prophet 计划日期对比的诚实数字。",
      "retrospective_seed ⇒ measured lead = null by contract, not by absence of effort (LAB-0 §4).",
      "retrospective_seed ⇒ 依契约测得提前量恒为 null，并非「没算出来」（LAB-0 §4）。") +
      ">" + t("Lead not measurable", "无法测量提前量") + "</span>";
  }

  /* ── the three degraded states. Each one stays visibly LAB. ───────────── */
  function stateBlock() {
    var h = '<div class="lab-state">';
    if (C.feed === "down") {
      h += '<div class="mx-empty"><b>' + t(
        "The Lab feed is not answering", "实验台数据源没有响应") + "</b>";
      h += '<div class="mx-empty-why">' + t(
        "No candidates can be shown until it does. Prophet&rsquo;s live board is unaffected &mdash; switch back to Live to use it.",
        "在它恢复之前无法显示任何候选。Prophet 的实时看板不受影响 —— 切回「实时」即可正常使用。") + "</div>";
      h += '<button type="button" class="lab-state-act" data-mode="live">' +
           t("Back to Live", "返回实时") + "</button>";
      return h + "</div></div>";
    }
    h += '<div class="mx-empty"><b>' + t(
      "Nothing early on this board right now", "该板目前没有早期候选") + "</b>";
    h += '<div class="mx-empty-why">' + t(
      "The feed is reporting and it is reporting nothing. That is a real zero, not a gap &mdash; try another board, or check back after the next pass.",
      "数据源正常，且确实没有内容。这是真实的零，不是数据缺失 —— 可以换一个板查看，或等下一次采集后再来。") + "</div>";
    return h + "</div></div>";
  }

  function baselineMark() {
    return '<li class="lab-mark"><div class="lab-mark-when">' +
      t(L.baseline.en, L.baseline.zh) + "</div>" +
      '<div class="lab-mark-l">' + t(
        "Continuous live watching began here. Everything below is history we already had.",
        "从这里开始持续实时观测。以下均为此前已有的历史记录。") + "</div></li>";
  }

  /* the spine's own way of saying "and nothing since" */
  function gapHead() {
    if (C.feed !== "stale") return "";
    return '<div class="lab-gap"><div class="lab-gap-rail"></div><div class="lab-gap-l">' +
      t("nothing since " + L.stale_gen.hm + " ET", "自美东 " + L.stale_gen.hm + " 起没有新记录") +
      "</div></div>";
  }

  function plane() {
    var all = boardRows(C.labSelection);
    var rows = classFilter(all);
    var h = '<div class="lab-plane">' + band();
    if (C.feed === "down" || all.length === 0) return h + stateBlock() + "</div>";
    h += meta(rows, all);
    if (rows.length === 0) {
      h += '<div class="lab-state"><div class="mx-empty"><b>' + t(
        "No rows of that kind on this board", "该板没有这一类记录") + "</b>";
      h += '<div class="mx-empty-why">' + t(
        "This board has rows, but none of the kind you filtered to. Choose All to see the rest.",
        "该板有记录，但没有您所筛选的那一类。选择「全部」可查看其余记录。") + "</div></div></div>";
      return h + "</div>";
    }
    h += gapHead();
    h += '<ul class="lab-stream">';
    /* THE BASELINE MARKER. LAB-0 §4 makes the live/seed split a function of one
       date — the moment continuous live watching began. Drawing that date on
       the spine explains the whole distinction structurally, so a reader never
       has to infer from a chip why one row counts as evidence and the next one
       cannot. It is placed where the stream actually crosses it, so it is a
       reading of the data rather than a caption. */
    var marked = false;
    rows.forEach(function (r) {
      if (!marked && r.cls === "seed") { h += baselineMark(); marked = true; }
      h += row(r);
    });
    return h + "</ul></div>";
  }

  /* ═══════════════ 3. PAINT ═════════════════════════════════════════════ */
  function paintLab() {
    root.setAttribute("data-mode", "lab");
    /* the LIVE furniture is REMOVED from view, not decorated. A lifecycle
       ladder counting the plan book, a candidates shelf, a groups band or a
       track record left standing above Lab rows would be LIVE content under a
       LAB label — the one thing LAB-0 §6.5 forbids by name. */
    ["ladder-block"].forEach(function (c) {
      var n = document.querySelector("." + c); if (n) n.style.display = "none";
    });
    ["candidates", "groups", "evidence", "record"].forEach(function (id) {
      var n = document.getElementById(id); if (n) n.style.display = "none";
    });
    document.querySelectorAll(".mx-sec").forEach(function (n) {
      if (n.id !== "setups") n.style.display = "none";
    });
    /* the page header speaks for the Lab's producer while the Lab is shown —
       printing the plan book's as-of or its behind-the-tape banner over Lab
       rows would date the wrong thing */
    var p = document.querySelector(".bh-purpose"); if (p) p.style.display = "none";
    var s = document.querySelector(".bh-stamp");
    if (s) {
      /* the inline LIVE control is REMOVED, not hidden. Two radiogroups with
         the same label — one of them invisible — is an assistive-technology
         defect, and a hidden duplicate is also the kind of thing an automated
         check clicks by accident and reports as a pass. */
      var dup = s.querySelector(".lab-seg"); if (dup) dup.remove();
      var opv = s.querySelector(".lab-opv"); if (opv) opv.remove();
      s.style.display = "none";
    }
    var sn = document.querySelector(".nb-stale-note"); if (sn) sn.style.display = "none";
    var setups = document.getElementById("setups");
    if (setups) setups.innerHTML = plane();
    syncSeg();
  }

  function paintLive() {
    root.setAttribute("data-mode", "live");
    var plane_ = document.querySelector(".lab-plane");
    if (plane_) plane_.remove();
    /* RE-DERIVE, never restore. board.js is re-executed against the current
       payload, so the LIVE board after a Lab excursion is produced by exactly
       the code path a cold load uses. Nothing of the Lab can persist, and no
       pre-LAB snapshot exists to go stale. */
    document.querySelectorAll(".lens-pop").forEach(function (n) { n.remove(); });
    var b = document.getElementById("board");
    if (b) b.innerHTML = "";
    var sc = document.createElement("script");
    sc.src = "../institutionalize/us_stocks/board.js?repaint=" + (++C.repaints);
    sc.onload = function () { mountModebar(); syncSeg(); harnessStamp(); };
    document.body.appendChild(sc);
  }

  /* `initial` skips the LIVE repaint on a cold load: board.js has already
     painted, so re-executing it would be a wasted full re-render AND would
     make the repaint counter lie about how the board on screen was produced.
     The counter is evidence (D15d), so it may only count real re-derivations. */
  function apply(initial) {
    if (C.desiredMode === "lab") paintLab();
    else if (initial) { root.setAttribute("data-mode", "live"); harnessStamp(); }
    else paintLive();
  }

  function syncSeg() {
    document.querySelectorAll(".lab-seg button").forEach(function (b) {
      var on = b.getAttribute("data-mode") === C.desiredMode;
      b.setAttribute("aria-checked", on ? "true" : "false");
      b.setAttribute("tabindex", on ? "0" : "-1");
    });
  }

  /* ═══════════════ 4. EVENTS ════════════════════════════════════════════ */
  document.addEventListener("click", function (e) {
    var m = e.target.closest("[data-mode]");
    if (m && (m.closest(".lab-seg") || m.classList.contains("lab-state-act"))) {
      var want = m.getAttribute("data-mode");
      if (want !== C.desiredMode) { C.desiredMode = want; apply(); }
      return;
    }
    var b = e.target.closest("[data-lab-board]");
    if (b) { C.labSelection = b.getAttribute("data-lab-board"); paintLab(); return; }
    var c = e.target.closest("[data-lab-cls]");
    if (c) { C.labClass = c.getAttribute("data-lab-cls"); paintLab(); return; }
  });
  /* arrow keys move within the radiogroup, per the segmented-control pattern */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    if (!e.target.closest || !e.target.closest(".lab-seg")) return;
    e.preventDefault();
    C.desiredMode = C.desiredMode === "lab" ? "live" : "lab";
    apply();
    var sel = document.querySelector('.lab-seg button[aria-checked="true"]');
    if (sel) sel.focus();
  });

  /* ═══════════════ 5. HARNESS ═══════════════════════════════════════════ */
  function harnessStamp() {
    var hn = document.getElementById("harness");
    if (!hn || !hn.firstChild) return;
    var old = hn.querySelector(".lab-hstamp");
    if (old) old.remove();
    var g = document.createElement("span");
    g.className = "harness-g lab-hstamp";
    g.innerHTML = "<strong>Lab</strong>" +
      '<a class="on" title="Lab-plane facts are synthetic — see DESIGN_NOTES §Evidence">' +
      "data-mock-lab</a>" +
      '<a title="LIVE is re-derived by re-executing board.js, never restored from a snapshot">' +
      "live repaints: " + C.repaints + "</a>";
    hn.querySelector(".harness").appendChild(g);
  }
  function harnessLinks() {
    var hn = document.querySelector(".harness");
    if (!hn) return;
    function grp(label, key, opts) {
      var g = '<span class="harness-g"><strong>' + label + "</strong>";
      opts.forEach(function (o) {
        var p = new URLSearchParams(location.search);
        p.set(key, o[0]);
        var on = (qs.get(key) || (key === "mode" ? "live" : key === "feed" ? "ok" :
                 key === "cls" ? "all" : key === "op" ? "1" : "lab-all-early-v1")) === o[0];
        g += '<a class="' + (on ? "on" : "") + '" href="?' + p.toString() + '">' + o[1] + "</a>";
      });
      return g + "</span>";
    }
    hn.insertAdjacentHTML("beforeend",
      grp("Mode", "mode", [["live", "Live"], ["lab", "Lab"]]) +
      grp("Operator", "op", [["1", "Yes"], ["0", "No"]]) +
      grp("Lab board", "board", L.boards.map(function (b) { return [b.id, b.en]; })) +
      grp("Class", "cls", [["all", "All"], ["live", "Live only"], ["seed", "Seeds only"]]) +
      grp("Lab feed", "feed", [["ok", "Reporting"], ["stale", "Behind"],
                               ["empty", "Empty"], ["down", "Unavailable"]]));
    harnessStamp();
  }

  /* ═══════════════ 6. MOUNT ═════════════════════════════════════════════ */
  harnessLinks();
  mountModebar();
  /* If the operator affordance is absent the page must be the R4 board and
     nothing else — so the controller does not even set data-mode. */
  if (operator) apply(true); else root.setAttribute("data-mode", "live");
})();

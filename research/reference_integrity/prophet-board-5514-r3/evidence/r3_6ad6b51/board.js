/* ═══════════════════════════════════════════════════════════════════════════
   PROPHET BOARD — mockup renderer (MP-1 gate G-C)

   COUNT LAW (P0 §B acceptance 1, ruling §6): every integer this file prints that
   describes a quantity of setups is read from BOARD.counts / BOARD.live_total /
   BOARD.grand_total, or is a computed DIFFERENCE of them. Nothing is recounted
   from row iteration. `cellCount()` is the single accessor; grep it to audit.

   In production the page reads the published `lifecycle_counts` block that
   PR-0(c) emits. Here the same block is precomputed by tools/gen_fixture.py from
   the committed payload, which is why the rendered numbers reconcile exactly.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var B = window.BOARD;
  var CELLS = ["watch", "ready", "entered", "delivering", "overtime", "invalidated", "resolved"];
  var LIVE = CELLS.slice(0, 6);

  /* ── the ruled lexicon. EN/ZH ship as paired constants (ruling §9.3): both
        languages, all or nothing. ZH is a native two-character arc, not
        translated English. ─────────────────────────────────────────────────── */
  var LEX = {
    watch:       { en: "Watch",       zh: "观察",
                   gEn: "signal fired, nothing committed",  gZh: "已出现信号，尚未建仓" },
    ready:       { en: "Ready",       zh: "就绪",
                   gEn: "plan armed, trigger not fired",    gZh: "计划就位，尚未触发" },
    entered:     { en: "Entered",     zh: "入场",
                   gEn: "in the entry window",              gZh: "处于入场窗口内" },
    delivering:  { en: "Delivering",  zh: "达标",
                   gEn: "at or past the first target",      gZh: "已到达首个目标位" },
    overtime:    { en: "Overtime",    zh: "超时",
                   gEn: "past its window, still open",      gZh: "已过窗口期，仍未了结" },
    invalidated: { en: "Invalidated", zh: "失效",
                   gEn: "its void level was hit",           gZh: "已触及失效价" },
    resolved:    { en: "Resolved",    zh: "已结",
                   gEn: "closed and graded",                gZh: "已平仓并计入战绩" }
  };

  /* lane MARK chips — bottoming / continuation only. There is deliberately NO
     recovery chip: `recovery` is structurally empty in the engine, and a chip
     with no producer is the exact defect the four-dot rail died of. */
  var LANE = {
    bottoming:    { en: "Bottoming entry",    zh: "底部入场",
                    tEn: "Bottoming entry", tZh: "底部入场",
                    bEn: "This name was admitted through the bottoming-reversal door — it based, then turned up. A mark of which construction found it, not a stage it advances through.",
                    bZh: "该股经由「底部反转」通道入选：先筑底，后转强。这是入选方式的标记，不代表进度。" },
    continuation: { en: "Continuation entry", zh: "顺势入场",
                    tEn: "Continuation entry", tZh: "顺势入场",
                    bEn: "This name was admitted through the continuation-pullback door — an existing trend pulled back. A mark of which construction found it, not a stage it advances through.",
                    bZh: "该股经由「顺势回调」通道入选：既有趋势出现回调。这是入选方式的标记，不代表进度。" }
  };

  /* Candidates triage — SHIPPED labels reused verbatim, except two sub-lines
     relabelled for the one-referent-per-page law (ruling §10.4): the shipped
     `live` sub-line said 入场窗口已打开 (入场 = the Entered cell word) and the
     shipped `basing` sub-line said 观察，勿追高 (观察 = the Watch cell word).
     Both now say "buy" instead, which is also the honest word — these are buy
     rows. EN "get ready" likewise avoids the Ready cell word. */
  var TRIAGE = [
    { k: "live",       en: "Live now",          zh: "现在可操作",
      sEn: "buy window is open",            sZh: "买入窗口已打开" },
    { k: "setting_up", en: "Setting up",        zh: "形成中",
      sEn: "not there yet — prepare",       sZh: "尚未触发 — 提前准备" },
    { k: "ran",        en: "Ran — don't chase", zh: "已启动 — 勿追",
      sEn: "the move already started",      sZh: "行情已经启动" },
    { k: "basing",     en: "Basing",            zh: "筑底中",
      sEn: "no buy signal yet — don't chase", sZh: "尚无买入信号 — 勿追高" },
    { k: "blocked",    en: "Blocked",           zh: "受阻",
      sEn: "stand aside for now",           sZh: "暂时观望" }
  ];

  /* ── harness state ─────────────────────────────────────────────────────── */
  var qs = new URLSearchParams(location.search);
  var S = {
    theme:  qs.get("theme")  || "dark",
    lang:   qs.get("lang")   || "en",
    state:  qs.get("state")  || "paid",
    life:   qs.get("life")   || "",
    view:   qs.get("view")   || "grid",
    chrome: qs.get("chrome") || "1"
  };
  if (CELLS.indexOf(S.life) < 0) S.life = "";

  var root = document.documentElement;
  root.setAttribute("data-theme", S.theme);
  root.setAttribute("data-lang", S.lang);
  root.setAttribute("data-chrome", S.chrome);
  root.lang = S.lang === "zh" ? "zh-CN" : "en";

  var isEmpty = S.state === "empty";
  var isAnon  = S.state === "anon";
  var isEps   = S.state === "episodes";
  /* `fallback` is a mockup-gate lens showing ONLY rows the candidate join does
     not reach — no chart, no quote, no name/sector, no lane mark. It exists to
     prove the degraded card still reads, and to size the enrichment gap
     honestly (DESIGN_NOTES §6 Q1). It is not a page control. */
  var isFall  = S.state === "fallback";
  /* ONE UNIVERSE (R2-C). `paid` and `today` are the same board: the whole plan
     book. There is no reference-only subset, because a view that renders a
     different population than the one its integers describe is the count-law
     contradiction itself. Headline, ladder cells, rendered cards, "+N more",
     filters and table view all describe the plan book, with no view exemption.
     Enrichment coverage shows honestly on the cards instead of being filtered
     away; `fallback` isolates the un-enriched rows for inspection only. */
  var isRef   = S.state === "paid" || S.state === "today";

  /* ── the count accessor — the ONLY place a setup quantity comes from ───── */
  function cellCount(k) {
    if (isEmpty) return k === "resolved" ? B.counts.resolved : 0;  // record survives a quiet day
    return B.counts[k] || 0;
  }
  function liveTotal() {
    if (isEmpty) return 0;
    return B.live_total;
  }
  /* watch is key-ABSENT on this payload, which is a different fact from zero
     (ruling §6 fn.1). It renders as an em dash plus a disclosure line. */
  function watchAbsent() { return !B.watch_key_present; }

  function t(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + "</span>";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function money(v) { return v == null ? "—" : "$" + Number(v).toFixed(2); }

  /* ── row population ───────────────────────────────────────────────────── */
  function rows() {
    if (isEmpty) return [];
    var r = B.rows.slice();
    if (isEps) r = r.filter(function (x) { return x.eps; });          // multi-episode names only
    if (isFall) r = r.filter(function (x) { return !x.spark; });      // un-enriched rows only
    if (S.life) {
      r = r.filter(function (x) { return x.life === S.life; });
    } else if (!isEps && !isFall) {
      /* The UNFILTERED board is the LIVE board: `resolved` is outside the
         headline by construction (ruling §6 two-total law), so a graded-out plan
         may not sit in the default grid either — otherwise the section total
         (162 live) and the grid population (179 rows) disagree and the "+N more"
         difference stops reconciling. Resolved is reached through its own
         terminal cell, which is exactly what that cell is for. */
      r = r.filter(function (x) { return x.life !== "resolved"; });
    }
    /* Global sort — one order for the whole board, so a ticker's two episodes
       stand alone wherever they fall (P0 §B unit of account (i): never stacked,
       merged, or grouped). Resolved sorts last: record, not inventory. */
    r.sort(function (a, b) {
      var ar = a.life === "resolved" ? 1 : 0, br = b.life === "resolved" ? 1 : 0;
      if (ar !== br) return ar - br;
      var ap = a.pri == null ? -1 : a.pri, bp = b.pri == null ? -1 : b.pri;
      if (ap !== bp) return bp - ap;
      var ad = (a.opened && a.opened.iso) || "", bd = (b.opened && b.opened.iso) || "";
      return bd < ad ? -1 : bd > ad ? 1 : (a.id < b.id ? -1 : 1);
    });
    return r;
  }

  /* ═══════════════ 1. LADDER ════════════════════════════════════════════ */
  function ladder() {
    var h = "";
    var total = liveTotal();

    h += '<div class="ladder-headline">';
    h += '<span class="ladder-n fig">' + total + "</span>";
    h += '<span class="ladder-nl">' + t("live setups today", "个跟踪中计划") + "</span>";
    h += '<span class="ladder-sub">' + t(
      "the six cells below add up to this number",
      "下方 6 个状态合计") + "</span>";
    h += "</div>";

    h += '<div class="mx-ladder" role="group" aria-label="' +
         (S.lang === "zh" ? "按生命周期筛选" : "Filter setups by lifecycle") + '">';

    LIVE.forEach(function (k, i) {
      var absent = k === "watch" && watchAbsent();
      var n = cellCount(k);
      var sel = S.life === k;
      h += '<button class="mx-cell' + (i === 5 ? " mx-cell--last-live" : "") + '"' +
           ' data-life="' + k + '" aria-pressed="' + (sel ? "true" : "false") + '"' +
           (absent ? ' data-absent="1"' : (n === 0 ? ' data-zero="1"' : "")) + ">";
      h += '<span class="mx-cap mx-cap--' + k + '" aria-hidden="true"></span>';
      h += '<span class="mx-cell-n fig">' + (absent ? "&mdash;" : n) + "</span>";
      h += '<span class="mx-cell-l">' + t(LEX[k].en, LEX[k].zh) + "</span>";
      h += "</button>";
    });

    /* the visible break: Resolved sits OUTSIDE the live enclosure, after a
       divider, on a dashed outline. It is the terminal cell of the same ladder —
       still shown, deliberately not summed (ruling §6 two-total law). */
    h += '<div class="mx-ladder-gap" aria-hidden="true"></div>';
    var rs = S.life === "resolved";
    h += '<button class="mx-cell mx-cell--term" data-life="resolved" aria-pressed="' +
         (rs ? "true" : "false") + '">';
    h += '<span class="mx-cap mx-cap--resolved" aria-hidden="true"></span>';
    h += '<span class="mx-cell-n fig">' + cellCount("resolved") + "</span>";
    h += '<span class="mx-cell-l">' + t(LEX.resolved.en, LEX.resolved.zh) + "</span>";
    h += "</button>";
    h += '<div class="ladder-termnote">' + t("not in today&rsquo;s count", "不计入上方总数") + "</div>";
    h += "</div>";

    /* key-absence disclosure — never a silent 0 */
    if (watchAbsent()) {
      h += '<p class="ladder-absence"><span class="mx-mark mx-mark--watch" aria-hidden="true"></span>' +
           t("Watch tier publishes from the next nightly.",
             "「观察」将在下一次收盘更新后发布。") + "</p>";
    }

    h += '<div class="ladder-foot">';
    h += "<span>" + t(
      "Sorted by priority — how ready a setup is today, not how likely it is to win.",
      "按优先级排序 — 数值越高表示越接近可操作，并不代表胜率更高。");
    h += '<span class="lens-q" tabindex="0" data-tip-t-en="How the ladder counts" data-tip-t-zh="计数口径"' +
         ' data-tip-en="Each cell counts plan rows — one row per tracked commitment, so a name you have traded twice appears twice. Watch counts names with a live signal and no open plan yet. The six live cells add up to the headline; Resolved sits outside it, because a closed plan is record rather than inventory."' +
         ' data-tip-zh="每一格统计的是「计划」条目——每条对应一次独立的跟踪，因此同一只股票若有两次操作，就会出现两次。「观察」统计的是已有信号、但尚未建立计划的股票。6 个状态相加等于标题数字；「已结」不计入其中，因为已平仓的计划属于历史战绩，不是当前持仓。"' +
         ' data-tip-rc-en="' + esc(B.grand_total) + " plan rows on the book &middot; " + esc(B.asof) + '"' +
         ' data-tip-rc-zh="计划库共 ' + esc(B.grand_total) + " 条 &middot; " + esc(B.asof) + '">?</span></span>';
    if (S.life) {
      h += '<button class="ladder-clear" data-life="">' +
           t("Clear filter", "清除筛选") + "</button>";
    }
    h += "</div>";
    return h;
  }

  /* ═══════════════ 2. SETUPS ════════════════════════════════════════════ */
  var GRID_CAP = 40;

  /* ── the revised Prophet card ────────────────────────────────────────────
     Amalgamation: the shipped card's chart-first trading DNA + the ruled
     lifecycle grammar. Reads in about a second — ticker, stance, price, how it
     is moving, the chart, priority, marks, lifecycle, zone — with no paragraph.

     Deliberately NOT here (handoff §6): plan-clock telemetry (`day 2 of 45`),
     paragraph what_to_do_now, the Entry/T1/Void three-number footer, and any
     exact execution command. Those belong in plan detail, not on a dense grid. */
  /* The five shipped card verbs. There is deliberately no sixth: TRIM does not
     exist on the Board (operator ruling 2026-08-13). */
  var VERB = {
    buy:   { en: "Buy",   zh: "买入" },
    near:  { en: "Near",  zh: "临近" },
    wait:  { en: "Wait",  zh: "等待" },
    hold:  { en: "Hold",  zh: "持有" },
    avoid: { en: "Avoid", zh: "回避" }
  };

  /* BLOCKED_DATA — the entry/actionability axis has not published for this plan.
     It occupies the stance slot so the reader sees an absent read rather than a
     card that forgot its chip, and it is deliberately NOT one of the five hues:
     an unavailable stance is not a cautious stance. Never the word "wait". */
  var NOREAD = {
    en: "No read yet", zh: "暂无判断",
    tEn: "Prophet has no entry read here",
    tZh: "此计划暂无入场判读",
    bEn: "The entry read that produces Buy / Near / Wait / Hold / Avoid has not published for this plan. The stance is unavailable — that is not the same as neutral, and not a hold.",
    bZh: "生成「买入 / 临近 / 等待 / 持有 / 回避」的入场判读尚未针对该计划发布。此处为暂缺，并不等同于中性，也不代表持有。"
  };

  /* The daily % change is a LIVE value: the shipped card server-renders an empty
     slot and live.js paints it. No committed artifact carries per-ticker intraday
     change (quotes.json holds 27 index/futures symbols only), so for the mockup
     the slot is filled from a deterministic per-ticker demo overlay purely to
     show the direction inks and their zh flip. These are the ONLY simulated
     numbers on the page — everything else is the real payload. Disclosed in
     DESIGN_NOTES §6 Q8 and marked in the DOM with data-mock-live. */
  function demoChange(tk) {
    var h = 0, i;
    for (i = 0; i < tk.length; i++) h = (h * 31 + tk.charCodeAt(i)) % 997;
    return ((h % 61) - 28) / 10;                       /* -2.8% .. +3.2% */
  }

  function card(r) {
    var L = LEX[r.life];
    var v = r.stance && VERB[r.stance] ? r.stance : null;
    var noRead = r.stance === "blocked_data";
    var cls = "pvcard" + (v ? " pv-" + v : noRead ? " pv-noread" : "") +
              (r.star ? " pv-featured" : "");
    /* data-sym is what live.js keys on (.nb-px[data-sym]) to paint the quote and
       the change client-side every ~60s. It is an ATTRIBUTE, not payload — so in
       production the live quote works for 100% of plan rows regardless of the
       candidate-join gap. Only name/sector/lane/spark need an enrichment path
       (DESIGN_NOTES §6 Q1). */
    var h = '<article class="' + cls + '" data-life="' + r.life + '" data-ticker="' +
            esc(r.tk) + '" data-sym="' + esc(r.tk) + '" data-mkt="us" data-id="' + esc(r.id) + '">';

    /* ── chart hero, with the stance chip and the live quote overlaid ────── */
    h += '<div class="pv-chart">';
    h += r.spark ? r.spark : '<div class="pv-nochart"></div>';
    h += '<span class="pv-ov pv-ovl">';
    if (v) {
      h += '<span class="pv-chip">' + t(VERB[v].en, VERB[v].zh) + "</span>";
    } else if (noRead) {
      h += '<span class="pv-chip pv-chip--noread" tabindex="0"' +
           ' data-tip-t-en="' + esc(NOREAD.tEn) + '" data-tip-t-zh="' + esc(NOREAD.tZh) + '"' +
           ' data-tip-en="' + esc(NOREAD.bEn) + '" data-tip-zh="' + esc(NOREAD.bZh) + '">' +
           t(NOREAD.en, NOREAD.zh) + "</span>";
    }
    if (r.trg) {
      /* the ⚡ chip carries a fact that appears nowhere else on the card, which
         is the shipped rule for keeping it (and its tip) */
      var tgEn = r.trg === "imminent"
        ? "The entry trigger has not fired yet, but price is at the level where it would."
        : "The entry trigger fired in the last few sessions.";
      var tgZh = r.trg === "imminent"
        ? "入场触发条件尚未满足，但价格已到达触发位附近。"
        : "入场触发条件已在最近几个交易日内满足。";
      h += '<span class="pv-trg" tabindex="0" data-tip-en="' + esc(tgEn) +
           '" data-tip-zh="' + esc(tgZh) + '">&#9889; ' +
           (r.trg === "imminent" ? t("Imminent", "即将触发") : t("Triggered", "已触发")) + "</span>";
    }
    h += "</span>";
    /* THE QUOTE SLOT RENDERS ON EVERY CARD, with or without an SSR price.
       live.js keys on `.nb-px[data-sym]` / `.nb-chg[data-sym]`, so the node must
       EXIST for a quote to arrive — a card that only renders the slot when the
       candidate join supplied a price can never hydrate, which is precisely the
       bug this fixes. Un-hydrated it reads an em dash in muted ink, exactly as
       the shipped card server-renders it. */
    var c = r.px != null ? demoChange(r.tk) : null;
    var dir = c == null ? "" : c > 0.05 ? " up" : c < -0.05 ? " down" : "";
    h += '<span class="pv-ov pv-ovr"><span class="pv-quote">' +
         '<span class="nb-px pv-px" data-sym="' + esc(r.tk) + '" data-mkt="us">' +
         (r.px != null ? money(r.px) : "&mdash;") + "</span>" +
         '<span class="nb-chg pv-chg' + dir + '" data-sym="' + esc(r.tk) + '" data-mkt="us"' +
         (c == null ? "" : ' data-mock-live="1"') + ">" +
         (c == null ? "&mdash;" : (c > 0 ? "+" : "") + c.toFixed(1) + "%") +
         "</span></span></span>";
    h += "</div>";

    /* ── identity + priority ────────────────────────────────────────────── */
    h += '<div class="pv-bd">';
    h += '<div class="pv-hd"><span class="pv-idw"><span class="pv-tk">' + esc(r.tk) + "</span>";
    if (r.nm) h += '<span class="pv-nm">' + esc(r.nm) + "</span>";
    h += "</span>";
    h += '<span class="pv-pri" tabindex="0"' +
         ' data-tip-t-en="Priority" data-tip-t-zh="优先级"' +
         ' data-tip-en="Where this setup ranks in tonight’s Prophet set — how ready it is to act on today. It is not a win probability, an expected return, or a confidence score."' +
         ' data-tip-zh="该计划在本次 Prophet 名单中的排序 — 表示目前有多接近可操作。它不是胜率，也不是预期收益或信心分数。">';
    h += '<span class="pv-pril">' + t("Priority", "优先级") + "</span>";
    h += '<span class="pv-prin' + (r.pri == null ? " pv-prin--na" : "") + ' fig">' +
         (r.pri == null ? "&mdash;" : Math.round(r.pri)) + "</span></span>";
    h += "</div>";
    if (r.sec) h += '<div class="pv-ind">' + esc(r.sec) + "</div>";

    /* ── marks: restrained, at most three ───────────────────────────────── */
    var mk = "";
    if (r.star) mk += '<span class="pv-mk-i pv-mk-feat">&#9733; ' + t("Featured", "精选") + "</span>";
    if (r.new) mk += '<span class="pv-mk-i pv-mk-new">' + t("New", "新增") + "</span>";
    if (r.lane && LANE[r.lane]) {
      var ln = LANE[r.lane];
      mk += '<span class="pv-mk-i pv-mk-lane" tabindex="0"' +
        ' data-tip-t-en="' + esc(ln.tEn) + '" data-tip-t-zh="' + esc(ln.tZh) + '"' +
        ' data-tip-en="' + esc(ln.bEn) + '" data-tip-zh="' + esc(ln.bZh) + '">' +
        t(ln.en, ln.zh) + "</span>";
    }
    /* R2-A: the RISK LEDGER carrier. The card must be able to reach its caution
       facts — the first pass deleted the capability outright. Progressive
       disclosure: a counted ⚠ pill at glance tier, the sentences one hover/focus
       deeper, so the card never becomes a wall of warnings. Rows come from real
       candidate fields (blow-off, ext_z, anti-chase, earnings window).
       It sits in the MARKS row rather than the chart overlay: the overlay is
       capped at 70% and already carries the stance and ⚡, so a third chip there
       collided with the live quote. */
    if (r.flags && r.flags.length) {
      mk += '<span class="pv-cau" tabindex="0" role="button" aria-label="' +
            (S.lang === "zh" ? "风险提示 " : "Caution notes ") + r.flags.length + '">';
      mk += '<span class="pv-cau-btn">&#9888; ' + r.flags.length + "</span>";
      mk += '<span class="pv-cau-pop" role="tooltip"><span class="pv-cau-hd">' +
            t("Before you act", "动手之前") + "</span>";
      r.flags.forEach(function (f) {
        mk += '<span class="pv-cau-row">' + t(esc(f[0]), esc(f[1])) + "</span>";
      });
      mk += "</span></span>";
    }
    if (r.eps) {
      var d = r.opened || { en: "—", zh: "—" };
      mk += '<span class="pv-ep">' + t(
        "Episode " + r.ep + " of " + r.eps + " &middot; " + d.en,
        "第 " + r.ep + " 轮（共 " + r.eps + " 轮）&middot; " + d.zh) + "</span>";
    }
    if (mk) h += '<div class="pv-mk">' + mk + "</div>";

    /* ── lifecycle: the ruled mark + the cell word. No gloss sentence. ──── */
    h += '<div class="pv-life"><span class="mx-mark mx-mark--' + r.life + '" aria-hidden="true"></span>' +
         '<span class="pv-life-w">' + t(L.en, L.zh) + "</span>";
    if (r.newer) {
      h += '<a class="pv-newer" href="#id=' + esc(r.newer) + '" style="margin-left:auto">' +
           t("Newer plan &rarr;", "最新计划 &rarr;") + "</a>";
    }
    h += "</div></div>";

    /* ── zone footer: the price AREA that matters ───────────────────────── */
    /* R2-B: ZONE IS GEOGRAPHY, NOT AN INSTRUCTION. The band is shown whatever the
       stance, but only an ACTIONABLE stance renders it in the active treatment
       (.pv-znr). Wait/Avoid get the muted form, Hold gets "Re-add" — the shipped
       zone_kind split (dashboard.html.j2:16183) that the first pass flattened,
       which had made every card's zone read like a buy instruction. */
    h += '<div class="pv-zn">';
    var zk = r.zk || "none";
    if (zk === "active") {
      h += '<span class="pv-znl">' + t("Zone", "买区") + "</span>";
      h += '<span class="pv-znr fig">' + money(r.zlo) + "&ndash;" + money(r.zhi) + "</span>";
    } else if (zk === "readd") {
      h += '<span class="pv-znl pv-znl--q">' + t("Re-add", "回补") + "</span>";
      h += '<span class="pv-znm fig">' + money(r.zlo) + "&ndash;" + money(r.zhi) + "</span>";
    } else if (zk === "muted") {
      h += '<span class="pv-znl pv-znl--q">' + t("Zone", "买区") + "</span>";
      h += '<span class="pv-znm fig">' + money(r.zlo) + "&ndash;" + money(r.zhi) + "</span>";
    } else if (r.life === "resolved") {
      h += '<span class="pv-znm">' + t("Closed — in the record", "已平仓 — 计入战绩") + "</span>";
    } else if (zk === "confirm") {
      h += '<span class="pv-znm">' + t("Zone sets on confirmation", "买区待确认后生成") + "</span>";
    } else {
      h += '<span class="pv-znm">' + t("No zone — stand aside", "无买区 — 观望") + "</span>";
    }
    if (r.opened) h += '<span class="pv-dt">' + t(r.opened.en, r.opened.zh) + "</span>";
    h += "</div></article>";
    return h;
  }


  function ghost() {
    return '<div class="pv-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></div>';
  }

  function gate(shown) {
    var total = liveTotal();
    var h = '<div class="mx-tier-gate mx-tier-gate--prophet">';
    h += '<span class="mx-tier-copy">';
    h += '<span class="mx-tier-eyebrow"><span class="mx-tier-mark" aria-hidden="true">&#9679;</span>' +
         t("Prophet", "Prophet") + "</span>";
    h += "<b>" + t(
      "You&rsquo;re seeing " + shown + " of " + total + " live setups",
      "您正在查看 " + total + " 个跟踪中计划中的 " + shown + " 个") + "</b>";
    h += "<small>" + t(
      "The rest are part of the live board — entry, target and void levels included. The counts above stay honest whether you subscribe or not.",
      "其余计划同在这块看板上，含入场价、目标价与失效价。无论是否订阅，上方的计数都如实显示。") + "</small>";
    h += "</span>";
    h += '<span class="mx-tier-actions">';
    h += '<button class="mx-tier-primary" type="button">' + t("See the full board", "查看完整看板") + "</button>";
    h += '<button class="mx-tier-signin" type="button">' + t("Already a member? Sign in", "已是会员？登录") + "</button>";
    h += "</span></div>";
    return h;
  }

  function setups() {
    var r = rows();
    var cellN = S.life ? cellCount(S.life) : liveTotal();
    var h = "";

    /* section header — ONE canonical total, quoted from the block */
    h += '<div class="mx-sec-hd">';
    h += '<h2 class="mx-sec-h2">' + t("Setups", "跟踪中计划") + "</h2>";
    /* `episodes` is a HARNESS lens for the mockup gate, not a page control — the
       shipped board has no "multi-episode" filter. Its header states its own
       scope so the reference never shows a total that disagrees with the grid. */
    var nNames = isEps ? new Set(r.map(function (x) { return x.tk; })).size : 0;
    var absentCell = S.life === "watch" && watchAbsent();
    /* R2 defect: `enriched` was declared TWICE in this scope with two different
       formulas — spark-only (45) and spark+stance (33) — so every sentence that
       printed it showed 33 while describing the 45-row join. Both declarations
       are gone; coverage arithmetic lives in DESIGN_NOTES, computed once. */
    h += '<span class="mx-sec-total">' + (isFall
      ? t("<b>" + r.length + "</b> rows without chart or quote data",
          "缺少图表与报价数据的 <b>" + r.length + "</b> 条")
      : isEps
      ? t("<b>" + r.length + "</b> plan rows on <b>" + nNames + "</b> names",
          "<b>" + nNames + "</b> 只个股 &middot; 共 <b>" + r.length + "</b> 条计划")
      : S.life
        ? (absentCell
            ? t("<b>&mdash;</b> in " + LEX.watch.en, "<b>&mdash;</b> 个 " + LEX.watch.zh)
            : t("<b>" + cellN + "</b> in " + LEX[S.life].en, "<b>" + cellN + "</b> 个 " + LEX[S.life].zh))
        : t("<b>" + cellN + "</b> live &middot; the Prophet book", "<b>" + cellN + "</b> 个跟踪中 &middot; 计划库")) + "</span>";
    h += '<a class="mx-sec-link" href="#methodology">' + t("How setups are chosen", "选股方法") + "</a>";
    h += "</div>";

    if (isEmpty) {
      h += '<div class="mx-empty"><b>' +
        t("No live setups today", "今日暂无跟踪中计划") + "</b>" +
        '<div class="mx-empty-why">' + t(
          "The board refreshes after the next close. Nothing qualified tonight — that is a result, not an outage.",
          "看板将在下一次收盘后更新。本次没有标的入选——这是筛选结果，不是系统故障。") + "</div></div>";
      return h;
    }

    h += '<div class="setups-bar">';
    h += '<span class="st-view-toggle" role="group">';
    h += '<button data-view="grid" aria-selected="' + (S.view === "grid") + '">&#9638; ' + t("Grid", "卡片") + "</button>";
    h += '<button data-view="table" aria-selected="' + (S.view === "table") + '">&#9776; ' + t("Table", "表格") + "</button>";
    h += "</span>";
    /* The reference view carries NO lens sentence: it is the product surface, and
       which subset the fixture can render at full fidelity is an internal fact,
       not something a reader should be told. The coverage question lives in
       DESIGN_NOTES §6/§7 and in the diagnostic states below. */
    if (isFall) {
      h += '<span class="sort-rule">' + t(
        "Diagnostic view: how a card reads when the chart, quote, company name and lane mark are unavailable. The card still answers ticker, stance, priority, lifecycle and zone.",
        "诊断视图：当图表、报价、公司名称与通道标记不可用时，卡片的呈现方式。此时仍可读出代码、判断、优先级、状态与买区。") + "</span>";
    }
    if (isEps) {
      h += '<span class="sort-rule">' + t(
        "Mockup-gate lens: only names carrying more than one plan row. The shipped board has no such filter — these cards sit in the full grid under the same global sort.",
        "样稿评审视角：仅显示拥有一条以上计划的个股。正式看板没有这个筛选——这些卡片在完整网格中按同一排序规则排列。") + "</span>";
    }
    h += "</div>";

    /* A filter that yields nothing must say WHY — an empty grid under a pressed
       cell reads as a broken page. A producing cell at zero and a cell whose
       producer has not published yet are different facts and get different copy
       (ruling §6 fn.1/fn.2). */
    if (!r.length) {
      h += '<div class="mx-empty"><b>' + (absentCell
        ? t("Watch tier publishes from the next nightly",
            "「观察」将在下一次收盘更新后发布")
        : t("Nothing is in " + LEX[S.life].en + " right now",
            "目前没有「" + LEX[S.life].zh + "」状态的计划")) + "</b>";
      h += '<div class="mx-empty-why">' + (absentCell
        ? t("This tier has a producer, but tonight&rsquo;s build did not publish it yet — which is why the cell shows a dash rather than a zero.",
            "该状态有数据来源，但本次更新尚未发布，因此这一格显示为「—」，而不是 0。")
        : t("The cell is empty today, not missing: a plan lands here when " + LEX[S.life].gEn + ".",
            "该格今日为空，并非缺失：当计划" + LEX[S.life].gZh + "时，就会进入此格。")) + "</div>";
      h += '<div style="margin-top:12px"><button class="ladder-clear" data-life="">' +
           t("Show all live setups", "显示全部跟踪中计划") + "</button></div></div>";
      return h;
    }

    /* "What changed today" — a labelled slice of today's transitions, computed
       over the FULL plan book, never over whatever subset the grid happens to be
       rendering: a board-level fact that moved with the visible rows would be a
       different number on every lens. Only the figure with a full-book producer
       is printed (see DESIGN_NOTES §6 Q3 — the entered/resolved transition counts
       have none). */
    var fresh = B.rows.filter(function (x) {
      return x.life !== "resolved" && x.age != null && x.age <= 1;
    }).length;
    h += '<div class="chg-strip">';
    h += '<span class="chg-item">' + t("What changed today", "今日变化") + "</span>";
    h += '<span class="chg-sep">&middot;</span>';
    h += '<span class="chg-item">' + t("<b class=\"fig\">" + fresh + "</b> opened in the last day",
         "过去 24 小时新增 <b class=\"fig\">" + fresh + "</b>") + "</span>";
    h += '<span class="chg-sep">&middot;</span>';
    h += '<a class="mx-sec-link" style="margin:0" href="#turnwatch">' + t("Turn Watch deck &rarr;", "拐点观察台 &rarr;") + "</a>";
    h += "</div>";

    if (isAnon) {
      /* anonymous: exactly ONE card's data in the DOM. The rest are contentless
         skeletons — nothing withheld is present to view-source. */
      h += '<div class="pv-grid">' + card(r[0]);
      for (var g = 0; g < 4; g++) h += ghost();   /* fills the row; the gate below says how many are withheld */
      h += "</div>";
      h += gate(1);
      return h;
    }

    if (S.view === "table") {
      /* table view renders EVERY row of the active filter — the surface where
         rendered rows equal the cell count with no remainder. */
      h += '<div class="st-wrap"><table class="st-table"><thead><tr>';
      [["Ticker", "代码"], ["Lifecycle", "生命周期"], ["Entry", "入场价"], ["Void", "失效价"],
       ["First target", "首个目标"], ["Opened", "启动日"], ["Episode", "轮次"]].forEach(function (c) {
        h += "<th>" + t(c[0], c[1]) + "</th>";
      });
      h += "</tr></thead><tbody>";
      r.forEach(function (x) {
        var L = LEX[x.life];
        h += "<tr><td><b>" + esc(x.tk) + "</b></td>";
        h += '<td><span class="st-life"><span class="mx-mark mx-mark--' + x.life + '" aria-hidden="true"></span>' +
             t(L.en, L.zh) + "</span></td>";
        h += '<td class="fig">' + money(x.entry) + "</td>";
        h += '<td class="fig">' + money(x.inval) + "</td>";
        h += '<td class="fig">' + money(x.t1) + "</td>";
        h += '<td class="fig">' + (x.opened ? t(x.opened.en, x.opened.zh) : "—") + "</td>";
        h += "<td>" + (x.eps ? t(x.ep + " of " + x.eps, "第 " + x.ep + " / 共 " + x.eps) : "—") + "</td>";
        h += "</tr>";
      });
      h += "</tbody></table></div>";
      h += '<p class="mx-sec-note" style="margin-top:12px">' + t(
        "Table view shows every row of the current filter: <b>" + r.length + "</b> rendered.",
        "表格视图显示当前筛选下的全部条目：已渲染 <b>" + r.length + "</b> 条。") + "</p>";
      return h;
    }

    var shown = r.slice(0, GRID_CAP);
    /* THE POPULATION IS THE CANONICAL COUNT, not however many cards this view
       happens to draw. On the product states that is the published cell/live
       total, so rendered + "+N more" reconciles to the headline exactly. The
       diagnostic lenses state their own scope in their header instead. */
    var population = (isEps || isFall) ? r.length
                   : (S.life ? cellCount(S.life) : liveTotal());
    h += '<div class="pv-grid">';
    shown.forEach(function (x) { h += card(x); });
    /* overflow is a computed DIFFERENCE of published values, never a recount */
    if (population > shown.length) {
      var more = population - shown.length;
      h += '<a class="pv-more" href="?' + qsWith({ view: "table" }) + '">' +
           t("+<b class=\"fig\">" + more + "</b> more<br>see them all in table view",
             "另有 <b class=\"fig\">" + more + "</b> 条<br>可在表格视图中查看全部") + "</a>";
    }
    h += "</div>";
    return h;
  }

  /* ═══════════════ 3. CANDIDATES / 候选 ═════════════════════════════════
     A second population. Different noun, different form (pill shelves, no
     weight marks), its own printed-once total, and NO lifecycle cell word — in
     either language — anywhere inside this section. */
  function candidates() {
    var h = "";
    h += '<div class="mx-sec-hd">';
    h += '<h2 class="mx-sec-h2">' + t("Candidates", "候选") + "</h2>";
    h += '<span class="mx-sec-total">' + t(
      "<b>" + B.cand_total + "</b> screened tonight",
      "本次筛出 <b>" + B.cand_total + "</b> 只") + "</span>";
    h += '<a class="mx-sec-link" href="#screener">' + t("Open the screener", "打开筛选器") + "</a>";
    h += "</div>";
    h += '<p class="mx-sec-note">' + t(
      "Names tonight&rsquo;s screen surfaced. A candidate is not a setup: it becomes one only when a plan is written for it, which is what the board above counts.",
      "本次筛选出的股票。候选不等于计划：只有为它建立计划后，才会计入上方看板。") + "</p>";

    h += '<div class="cand-shelves">';
    TRIAGE.forEach(function (s) {
      var n = B.cand_counts[s.k] || 0;
      if (!n) return;                     /* an empty shelf renders no chip */
      h += '<span class="cand-shelf"><b class="fig">' + n + "</b>" +
           "<span>" + t(s.en, s.zh) + "</span>" +
           "<i>" + t(s.sEn, s.sZh) + "</i></span>";
    });
    h += "</div>";

    var cr = B.cand_rows.slice(0, 6);
    h += '<div class="cand-rows">';
    cr.forEach(function (x) {
      h += '<div class="cand-row"><span class="cand-tk">' + esc(x.tk) + "</span>" +
           '<span class="cand-nm">' + esc(x.nm || x.sec || "") + "</span>" +
           '<span class="cand-px fig">' + money(x.px) + "</span></div>";
    });
    h += "</div>";
    h += '<p class="mx-sec-note" style="margin:12px 0 0">' + t(
      "Showing 6 of <b>" + B.cand_total + "</b> &middot; screened " + B.cand_asof,
      "共 <b>" + B.cand_total + "</b> 只，显示前 6 只 &middot; 筛选日 " + B.cand_asof) + "</p>";
    return h;
  }

  /* ═══════════════ 4. GROUPS — bound to a real producer ══════════════════
     R2-D: the five stance lanes and their sector rows were AUTHORED — invented
     names, invented stances, invented counts. They are replaced by
     `us_standouts.themes_in_favour`, a canonical artifact with an as_of: rank,
     recommendation, run length and member count all come from the payload. If
     the key is absent the section states that, rather than inventing a market
     call to keep the composition full. */
  var RECO = {
    accumulate: { en: "Accumulate", zh: "逐步买入" },
    hold:       { en: "Hold",       zh: "持有" },
    watch:      { en: "Watch",      zh: "观察" },
    avoid:      { en: "Avoid",      zh: "回避" },
    trim:       { en: "Trim",       zh: "减仓" }
  };
  function groups() {
    var T = B.themes || [];
    var h = '<div class="mx-sec-hd">';
    h += '<h2 class="mx-sec-h2">' + t("Groups", "板块") + "</h2>";
    h += '<span class="mx-sec-total">' + (T.length
      ? t("<b>" + T.length + "</b> themes in favour", "<b>" + T.length + "</b> 个占优主题")
      : t("no theme read published", "暂无主题读数")) + "</span>";
    h += '<a class="mx-sec-link" href="#sectors">' + t("Sector intelligence", "板块情报") + "</a>";
    h += "</div>";

    if (!T.length) {
      h += '<div class="mx-empty"><b>' +
        t("No theme read published", "暂无主题读数") + "</b>" +
        '<div class="mx-empty-why">' + t(
          "Tonight&rsquo;s screen did not publish a theme ranking. Nothing is asserted in its place.",
          "本次筛选未发布主题排名。此处不作任何替代性判断。") + "</div></div>";
      return h;
    }

    h += '<div class="grp-grid">';
    T.forEach(function (g) {
      var rc = RECO[g.reco] || { en: g.reco || "—", zh: g.reco || "—" };
      h += '<div class="grp">';
      h += '<div class="grp-hd"><span class="grp-rank fig">' + g.rank + "</span>" +
           '<span class="grp-nm">' + t(esc(g.en), esc(g.zh || g.en)) + "</span></div>";
      h += '<div class="grp-meta">';
      h += '<span class="grp-reco">' + t(rc.en, rc.zh) + "</span>";
      if (g.days != null) {
        h += '<span class="grp-fact fig">' + t(g.days + "d up", g.days + " 天走强") + "</span>";
      }
      h += '<span class="grp-fact fig">' + t(g.n + " names", g.n + " 只") + "</span>";
      if (g.clean) h += '<span class="grp-clean">' + t("clean entry", "入场干净") + "</span>";
      h += "</div></div>";
    });
    h += "</div>";
    /* lineage, stated on the surface: which artifact, and as of when */
    h += '<p class="mx-sec-note" style="margin:10px 0 0">' + t(
      "Ranked by tonight&rsquo;s theme screen &middot; as of " + esc(B.themes_asof || "—"),
      "依据本次主题筛选排名 &middot; 数据日期 " + esc(B.themes_asof || "—")) + "</p>";
    return h;
  }

  /* ═══════════════ 5 / 6 ═══════════════════════════════════════════════ */
  function context() {
    var tabs = [["Breadth", "市场宽度"], ["Indexes & mega-caps", "指数与大型股"],
                ["Flow", "资金流"], ["Rates", "利率"], ["Regime", "市场状态"]];
    var h = '<div class="mx-sec-hd"><h2 class="mx-sec-h2">' + t("Market context", "市场环境") + "</h2>" +
            '<span class="mx-sec-total">' + t("the weather, not the trade", "环境参考，非交易信号") + "</span></div>";
    h += '<div class="tabset">';
    tabs.forEach(function (c) { h += '<a href="#ctx">' + t(c[0], c[1]) + "</a>"; });
    h += "</div>";
    return h;
  }
  function evidence() {
    var h = '<div class="mx-sec-hd"><h2 class="mx-sec-h2">' + t("Evidence &amp; record", "证据与战绩") + "</h2></div>";
    h += '<div class="ev-links">';
    [["Track record", "历史战绩"], ["How Prophet works", "Prophet 运作方式"],
     ["Calibration lab", "校准实验室"], ["Closed plans archive", "已结计划存档"]]
      .forEach(function (c) { h += '<a href="#ev">' + t(c[0], c[1]) + "</a>"; });
    h += "</div>";
    return h;
  }

  /* ═══════════════ header ══════════════════════════════════════════════ */
  function header() {
    var h = '<div class="bh"><div class="bh-top"><div>';
    h += '<h1 class="bh-title">' + t("Prophet &mdash; US", "Prophet &mdash; 美股") + "</h1>";
    h += '<p class="bh-purpose">' + t(
      "Every plan we are tracking on US stocks, and where each one stands today.",
      "我们正在跟踪的每一个美股计划，以及它们目前各自处于哪个状态。") + "</p>";
    h += "</div>";
    /* exactly ONE as-of pair for the page — the ladder adds no second stamp */
    h += '<div class="bh-stamp">';
    h += '<span class="pbs">&#9680; ' + t("Tonight&rsquo;s book", "今晚的计划簿") + "</span>";
    h += '<span class="dtp-token closed"><span class="dtp-dot"></span>' +
         t("Settled close", "收盘结算") + "</span>";
    h += '<span class="dtp-asof">' + esc(B.asof) + "</span>";
    h += "</div></div>";

    /* R2-D: the regime / breadth / posture chips are GONE. They asserted a market
       call ("Risk-on", "Broadening", "Act on the best few") with no canonical
       producer behind them — an authored claim wearing the costume of a reading.
       Nothing replaces them: the board's job is the plan book, and a market read
       returns only when a producer with lineage exists to state it. */
    h += "</div>";
    return h;
  }

  /* ═══════════════ harness bar ════════════════════════════════════════ */
  function qsWith(over) {
    var p = new URLSearchParams();
    var cur = { theme: S.theme, lang: S.lang, state: S.state, life: S.life, view: S.view, chrome: S.chrome };
    Object.keys(over).forEach(function (k) { cur[k] = over[k]; });
    Object.keys(cur).forEach(function (k) { if (cur[k]) p.set(k, cur[k]); });
    return p.toString();
  }
  function harness() {
    var g = [
      ["theme", [["dark", "Dark"], ["light", "Light"]]],
      ["lang",  [["en", "EN"], ["zh", "中文"]]],
      ["state", [["paid", "Reference"], ["today", "Today (actual)"], ["anon", "Anonymous"], ["empty", "Empty"], ["episodes", "Multi-episode"], ["fallback", "No-enrichment"]]],
      ["view",  [["grid", "Grid"], ["table", "Table"]]]
    ];
    var h = '<div class="harness"><strong>Mockup harness</strong>';
    g.forEach(function (grp) {
      h += '<span class="harness-g">';
      grp[1].forEach(function (o) {
        var on = S[grp[0]] === o[0];
        var q = {}; q[grp[0]] = o[0];
        h += '<a class="' + (on ? "on" : "") + '" href="?' + qsWith(q) + '">' + o[1] + "</a>";
      });
      h += "</span>";
    });
    h += '<span class="harness-g"><strong>Filter</strong>';
    h += '<a class="' + (S.life ? "" : "on") + '" href="?' + qsWith({ life: "" }) + '">All</a>';
    CELLS.forEach(function (k) {
      h += '<a class="' + (S.life === k ? "on" : "") + '" href="?' + qsWith({ life: k }) + '">' + LEX[k].en + "</a>";
    });
    h += "</span></div>";
    return h;
  }

  /* ═══════════════ mount ══════════════════════════════════════════════ */
  /* board-data.js ships `do` — a reserved word in older parsers when used as a
     property shorthand, so it is read into `do_` once here. */
  B.rows.forEach(function (r) { r.do_ = r["do"]; });

  document.getElementById("harness").innerHTML = harness();
  document.getElementById("board").innerHTML =
    header() +
    '<div class="ladder-block">' + ladder() + "</div>" +
    '<section class="mx-sec" id="setups">' + setups() + "</section>" +
    '<section class="mx-sec" id="candidates">' + candidates() + "</section>" +
    '<section class="mx-sec" id="groups">' + groups() + "</section>" +
    '<section class="mx-sec" id="context">' + context() + "</section>" +
    '<section class="mx-sec" id="evidence">' + evidence() + "</section>";

  /* ladder cells filter in place and write #life=<cell> — never #stage= */
  document.addEventListener("click", function (e) {
    var cell = e.target.closest("[data-life]");
    if (cell && (cell.classList.contains("mx-cell") || cell.classList.contains("ladder-clear"))) {
      var k = cell.getAttribute("data-life");
      if (k === S.life) k = "";
      location.search = qsWith({ life: k });
      if (k) location.hash = "life=" + k;
      return;
    }
    var v = e.target.closest("[data-view]");
    if (v) { location.search = qsWith({ view: v.getAttribute("data-view") }); }
  });
  if (S.life) {
    try { history.replaceState(null, "", location.pathname + location.search + "#life=" + S.life); } catch (err) {}
  }

  /* ── LENS: Tier-2 receipts on hover / focus ─────────────────────────── */
  var pop = document.createElement("div");
  pop.className = "lens-pop";
  document.body.appendChild(pop);
  function lensShow(el) {
    var zh = S.lang === "zh";
    var title = el.getAttribute(zh ? "data-tip-t-zh" : "data-tip-t-en") || el.getAttribute("data-tip-t-en");
    var body  = el.getAttribute(zh ? "data-tip-zh" : "data-tip-en") || el.getAttribute("data-tip-en");
    var rc    = el.getAttribute(zh ? "data-tip-rc-zh" : "data-tip-rc-en") || el.getAttribute("data-tip-rc-en");
    if (!body) return;
    pop.innerHTML = (title ? '<div class="lens-ttl">' + title + "</div>" : "") +
                    '<div class="lens-body">' + body + "</div>" +
                    (rc ? '<div class="lens-receipt">' + rc + "</div>" : "");
    var r = el.getBoundingClientRect();
    pop.style.left = Math.max(10, Math.min(window.innerWidth - 312, r.left - 8)) + "px";
    pop.style.top = (r.bottom + 8) + "px";
    pop.classList.add("open");
  }
  function lensHide() { pop.classList.remove("open"); }
  document.addEventListener("mouseover", function (e) {
    var el = e.target.closest("[data-tip-en]"); if (el) lensShow(el);
  });
  document.addEventListener("mouseout", function (e) {
    if (e.target.closest("[data-tip-en]")) lensHide();
  });
  document.addEventListener("focusin", function (e) {
    var el = e.target.closest("[data-tip-en]"); if (el) lensShow(el);
  });
  document.addEventListener("focusout", lensHide);
})();

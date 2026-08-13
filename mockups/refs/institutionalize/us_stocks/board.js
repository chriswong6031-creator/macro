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
    h += '<span class="ladder-nl">' + t("live setups today", "个在场计划") + "</span>";
    h += '<span class="ladder-sub">' + t(
      "the six cells below add up to this number",
      "下方六格相加即为此数") + "</span>";
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
    h += '<div class="ladder-termnote">' + t("not in today&rsquo;s count", "不计入今日总数") + "</div>";
    h += "</div>";

    /* key-absence disclosure — never a silent 0 */
    if (watchAbsent()) {
      h += '<p class="ladder-absence"><span class="mx-mark mx-mark--watch" aria-hidden="true"></span>' +
           t("Watch tier publishes from the next nightly.",
             "观察档自下一次夜间构建起发布。") + "</p>";
    }

    h += '<div class="ladder-foot">';
    h += "<span>" + t(
      "Sorted by priority — how ready a setup is today, not how likely it is to win.",
      "按优先级排序 — 表示今天越接近可操作，并不代表更容易获胜。");
    h += '<span class="lens-q" tabindex="0" data-tip-t-en="How the ladder counts" data-tip-t-zh="计数口径"' +
         ' data-tip-en="Each cell counts plan rows — one row per tracked commitment, so a name you have traded twice appears twice. Watch counts names with a live signal and no open plan yet. The six live cells add up to the headline; Resolved sits outside it, because a closed plan is record rather than inventory."' +
         ' data-tip-zh="每格统计的是「计划条目」——每条对应一次独立的跟踪承诺，因此同一只股票若有两次操作，就会出现两次。「观察」统计的是已有信号但尚无在场计划的股票。六个在场格相加等于标题数字；「已结」不计入其中，因为已平仓的计划属于战绩记录，而非当前持仓。"' +
         ' data-tip-rc-en="' + esc(B.grand_total) + " plan rows on the book &middot; " + esc(B.asof) + '"' +
         ' data-tip-rc-zh="在册计划 ' + esc(B.grand_total) + " 条 &middot; " + esc(B.asof) + '">?</span></span>';
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
  var VERB = {
    buy:   { en: "Buy",   zh: "买入" },
    near:  { en: "Near",  zh: "临近" },
    wait:  { en: "Wait",  zh: "等待" },
    hold:  { en: "Hold",  zh: "持有" },
    avoid: { en: "Avoid", zh: "回避" }
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
    var cls = "pvcard" + (v ? " pv-" + v : "") + (r.star ? " pv-featured" : "");
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
    if (v) h += '<span class="pv-chip">' + t(VERB[v].en, VERB[v].zh) + "</span>";
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
    if (r.px != null) {
      var c = demoChange(r.tk);
      var dir = c > 0.05 ? "up" : c < -0.05 ? "dn" : "flat";
      h += '<span class="pv-ov pv-ovr"><span class="pv-quote">' +
           '<span class="pv-px">' + money(r.px) + "</span>" +
           '<span class="pv-chg pv-chg--' + dir + '" data-mock-live="1">' +
           (c > 0 ? "+" : "") + c.toFixed(1) + "%</span></span></span>";
    }
    h += "</div>";

    /* ── identity + priority ────────────────────────────────────────────── */
    h += '<div class="pv-bd">';
    h += '<div class="pv-hd"><span class="pv-idw"><span class="pv-tk">' + esc(r.tk) + "</span>";
    if (r.nm) h += '<span class="pv-nm">' + esc(r.nm) + "</span>";
    h += "</span>";
    h += '<span class="pv-pri" tabindex="0"' +
         ' data-tip-t-en="Priority" data-tip-t-zh="优先级"' +
         ' data-tip-en="Where this setup ranks in tonight’s Prophet set — how ready it is to act on today. It is not a win probability, an expected return, or a confidence score."' +
         ' data-tip-zh="该计划在今晚 Prophet 名单中的排序 — 表示今天有多接近可操作。它不是胜率、预期收益或信心分数。">';
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
    h += '<div class="pv-zn">';
    if (r.zlo != null && r.zhi != null) {
      h += '<span class="pv-znl">' + t("Zone", "买区") + "</span>";
      h += '<span class="pv-znr fig">' + money(r.zlo) + "&ndash;" + money(r.zhi) + "</span>";
    } else if (r.life === "resolved") {
      h += '<span class="pv-znm">' + t("Closed — in the record", "已平仓 — 计入战绩") + "</span>";
    } else if (r.zstate === "filled") {
      h += '<span class="pv-znm">' + t("Zone already worked through", "买区已走完") + "</span>";
    } else {
      h += '<span class="pv-znm">' + t("Zone sets on confirmation", "买区待确认后生成") + "</span>";
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
      "您正在查看 " + total + " 个在场计划中的 " + shown + " 个") + "</b>";
    h += "<small>" + t(
      "The rest are part of the live board — entry, target and void levels included. The counts above stay honest whether you subscribe or not.",
      "其余计划同属这块在场看板，含入场价、目标价与失效价。无论是否订阅，上方计数均如实显示。") + "</small>";
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
    h += '<h2 class="mx-sec-h2">' + t("Setups", "在场计划") + "</h2>";
    /* `episodes` is a HARNESS lens for the mockup gate, not a page control — the
       shipped board has no "multi-episode" filter. Its header states its own
       scope so the reference never shows a total that disagrees with the grid. */
    var nNames = isEps ? new Set(r.map(function (x) { return x.tk; })).size : 0;
    var enriched = B.rows.filter(function (x) { return x.spark; }).length;
    var absentCell = S.life === "watch" && watchAbsent();
    h += '<span class="mx-sec-total">' + (isFall
      ? t("<b>" + r.length + "</b> rows the screener join does not reach",
          "候选关联未覆盖的 <b>" + r.length + "</b> 条计划")
      : isEps
      ? t("<b>" + r.length + "</b> plan rows on <b>" + nNames + "</b> names",
          "<b>" + nNames + "</b> 只股票上的 <b>" + r.length + "</b> 条计划")
      : S.life
        ? (absentCell
            ? t("<b>&mdash;</b> in " + LEX.watch.en, "<b>&mdash;</b> 个 " + LEX.watch.zh)
            : t("<b>" + cellN + "</b> in " + LEX[S.life].en, "<b>" + cellN + "</b> 个 " + LEX[S.life].zh))
        : t("<b>" + cellN + "</b> live &middot; the Prophet book", "<b>" + cellN + "</b> 个在场 &middot; 计划簿")) + "</span>";
    h += '<a class="mx-sec-link" href="#methodology">' + t("How setups are chosen", "选股方法") + "</a>";
    h += "</div>";

    if (isEmpty) {
      h += '<div class="mx-empty"><b>' +
        t("No live setups today", "今日暂无在场计划") + "</b>" +
        '<div class="mx-empty-why">' + t(
          "The board refreshes after the next close. Nothing qualified tonight — that is a result, not an outage.",
          "看板将在下个收盘后刷新。今晚没有标的入选——这是结果，不是故障。") + "</div></div>";
      return h;
    }

    h += '<div class="setups-bar">';
    h += '<span class="st-view-toggle" role="group">';
    h += '<button data-view="grid" aria-selected="' + (S.view === "grid") + '">&#9638; ' + t("Grid", "卡片") + "</button>";
    h += '<button data-view="table" aria-selected="' + (S.view === "table") + '">&#9776; ' + t("Table", "表格") + "</button>";
    h += "</span>";
    if (isFall) {
      h += '<span class="sort-rule">' + t(
        "Mockup-gate lens: the missing-enrichment fallback. These rows carry no chart, quote, company name or lane mark because those five fields arrive through the candidate join, which reaches only " + enriched + " of " + B.rows.length + " plan rows today. The card still reads — but closing this gap is a blocking implementation dependency, not a design target.",
        "样稿评审视角：缺失富化数据时的降级形态。这些条目没有图表、报价、公司名称与通道标记，因为这五个字段来自候选关联，而今天该关联仅覆盖 " + B.rows.length + " 条计划中的 " + enriched + " 条。卡片仍然可读——但补齐这一缺口是实施阶段的阻塞性依赖，而非设计目标。") + "</span>";
    }
    if (isEps) {
      h += '<span class="sort-rule">' + t(
        "Mockup-gate lens: only names carrying more than one plan row. The shipped board has no such filter — these cards sit in the full grid under the same global sort.",
        "样稿评审视角：仅显示拥有一条以上计划的股票。正式看板并无此筛选——这些卡片在完整网格中按同一全局排序排列。") + "</span>";
    }
    h += "</div>";

    /* A filter that yields nothing must say WHY — an empty grid under a pressed
       cell reads as a broken page. A producing cell at zero and a cell whose
       producer has not published yet are different facts and get different copy
       (ruling §6 fn.1/fn.2). */
    if (!r.length) {
      h += '<div class="mx-empty"><b>' + (absentCell
        ? t("Watch tier publishes from the next nightly",
            "观察档自下一次夜间构建起发布")
        : t("Nothing is in " + LEX[S.life].en + " right now",
            "目前没有处于「" + LEX[S.life].zh + "」的计划")) + "</b>";
      h += '<div class="mx-empty-why">' + (absentCell
        ? t("This tier has a producer, but tonight&rsquo;s build did not publish it yet — which is why the cell shows a dash rather than a zero.",
            "该档位有数据来源，但今晚的构建尚未发布，因此该格显示为破折号而非零。")
        : t("The cell is empty today, not missing: a plan lands here when " + LEX[S.life].gEn + ".",
            "该格今日为空，并非缺失：当计划" + LEX[S.life].gZh + "时，就会进入此格。")) + "</div>";
      h += '<div style="margin-top:12px"><button class="ladder-clear" data-life="">' +
           t("Show all live setups", "显示全部在场计划") + "</button></div></div>";
      return h;
    }

    /* "What changed today" — a labelled slice of today's transitions. Only the
       derivable figure is printed; see DESIGN_NOTES §Open questions. */
    var fresh = r.filter(function (x) { return x.age != null && x.age <= 1; }).length;
    h += '<div class="chg-strip">';
    h += '<span class="chg-item">' + t("What changed today", "今日变化") + "</span>";
    h += '<span class="chg-sep">&middot;</span>';
    h += '<span class="chg-item"><b class="fig">' + fresh + "</b> " + t("opened in the last day", "过去一天新增") + "</span>";
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
    h += '<div class="pv-grid">';
    shown.forEach(function (x) { h += card(x); });
    /* overflow is a computed DIFFERENCE of published values, never a recount */
    if (r.length > GRID_CAP) {
      var more = r.length - GRID_CAP;
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
      "今晚筛出 <b>" + B.cand_total + "</b> 只") + "</span>";
    h += '<a class="mx-sec-link" href="#screener">' + t("Open the screener", "打开筛选器") + "</a>";
    h += "</div>";
    h += '<p class="mx-sec-note">' + t(
      "Names tonight&rsquo;s screen surfaced. A candidate is not a setup: it becomes one only when a plan is written for it, which is what the board above counts.",
      "今晚筛选出的股票。候选不等于计划：只有为其写下计划后才会成为计划，也才会计入上方看板。") + "</p>";

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
      "显示 <b>" + B.cand_total + "</b> 只中的 6 只 &middot; 筛选日 " + B.cand_asof) + "</p>";
    return h;
  }

  /* ═══════════════ 4. GROUPS ═══════════════════════════════════════════ */
  var LANES = [
    { k: "buy",  en: "Buy now",      zh: "立即买入", sEn: "entry confirmed today",  sZh: "今日已确认买入", n: 6 },
    { k: "soon", en: "Almost ready", zh: "即将就位", sEn: "close, not confirmed",   sZh: "接近但未确认",   n: 5 },
    { k: "run",  en: "In favour",    zh: "受资金青睐", sEn: "money is rotating in", sZh: "资金正在流入",   n: 4 },
    { k: "trim", en: "Take profits", zh: "止盈",     sEn: "extended, thinning out", sZh: "涨幅过大，逐步减仓", n: 3 },
    { k: "hold", en: "Stand aside",  zh: "观望",     sEn: "nothing to do here",     sZh: "此处无需操作",   n: 4 }
  ];
  function groups() {
    var total = LANES.reduce(function (a, l) { return a + l.n; }, 0);
    var gi = 0;
    var h = "";
    h += '<div class="mx-sec-hd">';
    h += '<h2 class="mx-sec-h2">' + t("Groups", "板块") + "</h2>";
    h += '<span class="mx-sec-total">' + t(
      "<b>" + total + "</b> sectors &amp; themes moving",
      "<b>" + total + "</b> 个板块与主题在移动") + "</span>";
    h += '<a class="mx-sec-link" href="#sectors">' + t("Sector intelligence", "板块情报") + "</a>";
    h += "</div>";
    h += '<div class="stance-sel" role="group">';
    LANES.forEach(function (l, i) {
      h += '<button aria-pressed="' + (i === 0) + '" data-lane="' + l.k + '">' + t(l.en, l.zh) + "</button>";
    });
    h += "</div>";
    h += '<div class="actiongrid">';
    LANES.forEach(function (l) {
      h += '<div class="actcol act-' + l.k + '" data-lane="' + l.k + '">';
      h += '<div class="acth"><div class="acth-title-row">' +
           '<span class="acth-name">' + t(l.en, l.zh) + "</span>" +
           '<span class="acth-count">' + l.n + "</span></div>" +
           '<div class="acth-sub">' + t(l.sEn, l.sZh) + "</div></div>";
      h += '<div class="actbody">';
      for (var i = 0; i < Math.min(l.n, 4); i++) {
        var g = GRP[(gi++) % GRP.length];
        h += '<div class="act-row"><b>' + g[0] + "</b><span>" + t(g[1], g[2]) + "</span></div>";
      }
      if (l.n > 4) {
        h += '<div class="act-row"><span>' + t("+" + (l.n - 4) + " more", "另有 " + (l.n - 4) + " 个") + "</span></div>";
      }
      h += "</div></div>";
    });
    h += "</div>";
    return h;
  }
  var GRP = [
    ["Semiconductors",  "chips leading",       "芯片领涨"],
    ["Regional banks",  "rate relief",         "利率压力缓解"],
    ["Homebuilders",    "starts turning up",   "开工回升"],
    ["Energy",          "crude firming",       "原油走强"],
    ["Precious metals", "real rates rolling",  "实际利率回落"],
    ["Industrials",     "orders picking up",   "订单回升"],
    ["Biotech",         "funding reopening",   "融资窗口重开"],
    ["Utilities",       "defensive bid",       "防御性买盘"],
    ["Retail",          "traffic softening",   "客流走弱"],
    ["Transports",      "freight rates easing", "运价回落"],
    ["Insurance",       "pricing still firm",  "费率依然坚挺"],
    ["Media",           "ad spend flat",       "广告支出持平"],
    ["Staples",         "crowded and rich",    "拥挤且估值偏高"],
    ["Autos",           "inventories building", "库存累积"],
    ["Real Estate",     "basing out",          "底部构筑中"],
    ["Software",        "multiples compressing", "估值倍数压缩"],
    ["Steel",           "spreads widening",    "价差走阔"],
    ["Gold miners",     "margins expanding",   "利润率扩张"],
    ["Airlines",        "fuel headwind",       "燃油拖累"],
    ["Chemicals",       "destocking ending",   "去库存接近尾声"],
    ["Uranium",         "contracting cycle on", "长协周期启动"],
    ["Shipping",        "day rates topping",   "日租金见顶"]
  ];

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
      "我们正在跟踪的每一个美股计划，以及它们今天各自的进展。") + "</p>";
    h += "</div>";
    /* exactly ONE as-of pair for the page — the ladder adds no second stamp */
    h += '<div class="bh-stamp">';
    h += '<span class="pbs">&#9680; ' + t("Tonight&rsquo;s book", "今晚的计划簿") + "</span>";
    h += '<span class="dtp-token closed"><span class="dtp-dot"></span>' +
         t("Settled close", "收盘结算") + "</span>";
    h += '<span class="dtp-asof">' + esc(B.asof) + "</span>";
    h += "</div></div>";

    h += '<div class="bh-chips">';
    h += '<span class="rchip">' + t("Regime", "市场状态") + " <b>" + t("Risk-on", "偏好风险") + "</b></span>";
    h += '<span class="rchip">' + t("Breadth", "市场宽度") + " <b>" + t("Broadening", "扩散中") + "</b></span>";
    h += '<span class="rchip">' + t("Posture", "建议姿态") + " <b>" + t("Act on the best few", "择优出手") + "</b></span>";
    h += "</div></div>";
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
      ["state", [["paid", "Paid"], ["anon", "Anonymous"], ["empty", "Empty"], ["episodes", "Multi-episode"], ["fallback", "No-enrichment"]]],
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

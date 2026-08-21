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
    /* PRC-312: the gloss used to read "trigger not fired", which a sourced
       ⚡ Triggered chip on the same card flatly contradicts (5 rows do exactly
       that). Ready is a LIFECYCLE fact — the plan is armed and no position is
       open yet — and the trigger is a separate, independently sourced event.
       Restated as the lifecycle fact; the trigger claim is withdrawn from it.
       Escalated to the owning lifecycle ruling in DESIGN_NOTES. */
    ready:       { en: "Ready",       zh: "就绪",
                   gEn: "plan armed, not yet entered",      gZh: "计划就位，尚未入场" },
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

  /* ── SECTOR lexicon (V-B3) ────────────────────────────────────────────────
     The card's sector line was the last English string left on a zh card: it
     printed `esc(r.sec)` with no t() twin, so a Chinese reader got "Energy" on
     a page where every other word had been through a native pass. Same class
     the R4 pass already cured at PRC-316 for the theme RECO slug.

     The words are the ones a Chinese brokerage app uses, not literal GICS
     translations — the same register rule §0b.5 applied to the rest of the
     copy (可选消费, not 非必需消费品). The payload publishes the eleven GICS
     sectors and all eleven are mapped; coverage is asserted, not assumed
     (verify_r4.py R31 joins this table against board-data.js).

     UNMAPPED IS AN HONEST FALLBACK, NOT A SILENT PASS-THROUGH. A sector this
     table does not carry renders its English term unchanged, marked as
     untranslated, with a LENS receipt saying so — because a Chinese reader
     must be able to tell "we have no Chinese name for this" from "this name
     is English". Zero rows take that branch tonight, exactly like ⚡ Imminent:
     a real path with an honest zero, never a guess. */
  var SECTOR = {
    "Energy":                 "能源",
    "Materials":              "原材料",
    "Industrials":            "工业",
    "Consumer Discretionary": "可选消费",
    "Consumer Staples":       "日常消费",
    "Health Care":            "医疗保健",
    "Financials":             "金融",
    "Information Technology": "信息技术",
    "Communication Services": "通信服务",
    "Utilities":              "公用事业",
    "Real Estate":            "房地产"
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
    chrome: qs.get("chrome") || "1",
    /* P-K19 — the watch key moved under the frozen fixture. `early_turn_watch`
       was genuinely ABSENT when this payload was extracted (2026-08-13) and is
       present-and-empty in production from 2026-08-18, which is a different
       rendering: a literal 0 inside the enclosure, six published cells instead
       of five, and no absence disclosure line. The fixture is deliberately NOT
       re-baked (§0c.2), so the second state is reached by a declared forced
       state rather than by moving the population under the verdict. */
    watch:  qs.get("watch")  || "",
    /* P-B2 — the plan id the board should land on, written by the newer-plan
       link. A plan id, never a lifecycle cell: it selects a CARD, not a filter. */
    focus:  qs.get("focus")  || ""
  };
  if (CELLS.indexOf(S.life) < 0) S.life = "";
  if (["present", "absent"].indexOf(S.watch) < 0) S.watch = "";

  var root = document.documentElement;
  root.setAttribute("data-theme", S.theme);
  root.setAttribute("data-lang", S.lang);
  root.setAttribute("data-chrome", S.chrome);
  root.lang = S.lang === "zh" ? "zh-CN" : "en";

  var isEmpty = S.state === "empty";
  var isAnon  = S.state === "anon";
  var isEps   = S.state === "episodes";
  /* PRC-305: the behind-the-tape lens. Same population, same everything — the
     ONE thing that changes is what the freshness producer reports, which is
     the state the artifact previously had no way to express at all. */
  var isStale = S.state === "stale";
  /* `fallback` is a mockup-gate lens showing ONLY rows the candidate join does
     not reach — no chart, no quote, no name/sector, no lane mark. It exists to
     prove the degraded card still reads, and to size the enrichment gap
     honestly (DESIGN_NOTES §6 Q1). It is not a page control. */
  var isFall  = S.state === "fallback";
  /* V-B4 — the two states the specimen ships and this reference did not.
     They are scoped to the SAME region on purpose: the ladder and the Setups
     grid are one producer (the plan payload), while Candidates, Groups and
     Evidence come from their own artifacts. So loading skeletons that region
     and error names that region, and both leave the rest of the page alone —
     which is exactly what the error sentence promises the reader. Two states
     that teach one page model, rather than two ad-hoc treatments. */
  var isLoad  = S.state === "loading";
  var isErr   = S.state === "error";
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
  /* Watch is key-ABSENT on this payload, which is a different fact from zero
     (ruling §6 fn.1): key-absent renders an em dash plus a disclosure line,
     present-and-zero renders a literal 0 inside the enclosure.

     P-K19: production's payload flipped from the first to the second on
     2026-08-18, after this fixture was frozen. `?watch=present|absent` forces
     either reading of the SAME frozen counts, so the reference can photograph
     the state production is actually in without re-baking the population the
     verdict was issued over (§0c.2). The count law is unaffected either way —
     `counts.watch` is 0 in both, and 0+62+95+0+0+2 = 159 = live_total. */
  function watchAbsent() {
    if (S.watch === "present") return false;
    if (S.watch === "absent") return true;
    return !B.watch_key_present;
  }

  function t(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + "</span>";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function money(v) { return v == null ? "—" : "$" + Number(v).toFixed(2); }

  /* V-B3 — the sector line's zh twin. Mapped: the native term. Unmapped: the
     English term, VISIBLY marked as untranslated and carrying its own receipt,
     so an untranslated string can never pass as a translated one. */
  function sectorLabel(sec) {
    if (!sec) return "";
    var en = esc(sec);
    var zh = SECTOR[sec];
    if (zh) return t(en, zh);
    return '<span class="l-en">' + en + "</span>" +
           '<span class="l-zh pv-ind--raw" tabindex="0"' +
           ' data-tip-t-en="Sector name" data-tip-t-zh="行业名称"' +
           ' data-tip-en="No Chinese name has published for this sector, so the English term is shown unchanged."' +
           ' data-tip-zh="该行业暂无中文名称发布，此处保留英文原文，未作翻译。">' + en + "</span>";
  }

  /* PRC-318: a zone whose endpoints are equal is a PRICE, not a range. 4 of the
     61 zone-bearing rows are zero-width (CENX, BKSY, FBRT, SBSI) and printed
     "$46.46–$46.46"; a single price is a different instruction from a band. */
  function zoneRange(lo, hi) {
    if (lo == null && hi == null) return "—";
    if (lo == null || hi == null) return money(lo == null ? hi : lo);
    if (Number(lo) === Number(hi)) return money(lo);
    return money(lo) + "&ndash;" + money(hi);
  }

  var NUMWORD = { 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven" };

  /* ── FRESHNESS (PRC-305) ────────────────────────────────────────────────
     Production's producer, not an invented one: _compute_board_staleness()
     (scripts/build_stock_library.py:1469-1624, called :5734) emits
     {price_through, sessions_behind, delayed, unknown} into wide["staleness"],
     which reaches the template as _su.staleness. tools/gen_fixture.py mirrors
     that shape into B.staleness, so the state here is read, never guessed.
     `delayed` is production's own threshold: >= 2 sessions behind. */
  function sessionShift(iso, back) {
    var d = new Date(String(iso) + "T00:00:00Z"), n = 0;
    while (n < back) {
      d.setUTCDate(d.getUTCDate() - 1);
      if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) n++;
    }
    return d.toISOString().slice(0, 10);
  }
  function freshness() {
    var f = B.staleness;
    if (!f) {
      /* No staleness block on this fixture vintage: derive the same shape from
         the two as-ofs the payload DOES carry — the plan book's date and the
         ranking screen's date. Both are real payload facts. */
      var pt = B.cand_asof || B.asof;
      var n = 0, cur = String(B.asof);
      while (n < 12 && cur > String(pt)) { cur = sessionShift(cur, 1); n++; }
      f = { price_through: pt, sessions_behind: cur === String(pt) ? n : null,
            unknown: !B.cand_asof };
      f.delayed = f.sessions_behind != null && f.sessions_behind >= 2;
    }
    if (isStale) {
      /* the harness lens, at production's own delayed threshold */
      f = { price_through: sessionShift(B.asof, 2), sessions_behind: 2,
            delayed: true, unknown: false, lens: true };
    }
    return f;
  }

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

    /* PRC-310 / VTC-312 — the claim is SCOPED to the cells that actually print
       a value. The sub-line used to say "the six cells below add up to this
       number" above a row whose first cell is a deliberate em dash, and the
       artifact's own absence copy says that dash means NOT PUBLISHED, not zero.
       So the sentence asked for a sum the surface cannot complete, and it would
       read as an error on any night Watch is both unpublished and non-zero.
       `published` is a computed difference of published values (COUNT LAW). */
    var published = LIVE.length - (watchAbsent() ? 1 : 0);
    /* V-B4 — under load the ladder keeps its GEOMETRY and its ruled cell WORDS
       (both are constants, not data) and skeletons only the counts, which are
       the only unknown. It does NOT fall back to em dashes: on this surface the
       dash already means "published and absent" (ruling §6 fn.1), and one glyph
       may not carry two facts. Declared divergence from MP-1 §10 — DESIGN_NOTES
       §9 records which string is law and why. */
    if (isLoad) {
      h += '<div class="ladder-headline">';
      h += '<span class="skel sk-head" aria-hidden="true"></span>';
      h += '<span class="ladder-nl">' + t("live setups today", "个跟踪中计划") + "</span>";
      h += "</div>";
      h += '<div class="mx-ladder" role="group" aria-busy="true" aria-label="' +
           (S.lang === "zh" ? "生命周期状态加载中" : "Lifecycle counts loading") + '">';
      LIVE.forEach(function (k, i) {
        h += '<div class="mx-cell' + (i === 5 ? " mx-cell--last-live" : "") + '">';
        h += '<span class="mx-cap mx-cap--' + k + '" aria-hidden="true"></span>';
        h += '<span class="skel sk-n" aria-hidden="true"></span>';
        h += '<span class="mx-cell-l">' + t(LEX[k].en, LEX[k].zh) + "</span>";
        h += "</div>";
      });
      h += '<div class="mx-ladder-gap" aria-hidden="true"></div>';
      h += '<div class="mx-cell mx-cell--term">';
      h += '<span class="mx-cap mx-cap--resolved" aria-hidden="true"></span>';
      h += '<span class="skel sk-n" aria-hidden="true"></span>';
      h += '<span class="mx-cell-l">' + t(LEX.resolved.en, LEX.resolved.zh) + "</span>";
      h += "</div>";
      h += '<div class="ladder-termnote">' + t("not in today&rsquo;s count", "不计入上方总数") + "</div>";
      h += "</div>";
      return h;
    }
    h += '<div class="ladder-headline">';
    h += '<span class="ladder-n fig">' + total + "</span>";
    h += '<span class="ladder-nl">' + t("live setups today", "个跟踪中计划") + "</span>";
    h += '<span class="ladder-sub">' + t(
      "the " + (NUMWORD[published] || published) + " published cells below add up to this number",
      "下方 " + published + " 个已发布状态合计") + "</span>";
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

  /* PRC-303 — A CAUTION MAY NOT NAME A ZONE THE CARD SAYS DOES NOT EXIST.
     3 rows pair "Don't chase above the buy zone" with a "No zone — stand aside"
     footer; 2 of them (GPCR, VSEC) are inside the visible 40 and both are
     ★Featured, GPCR being the rank-1 card. The collision is NEW in R3 and was
     created by curing R2's PRC-201 — restoring the risk ledger was right, and
     this edge was not anticipated. The row is REWRITTEN to the zone-free
     statement of the same fact: the risk is real and stays on the card. No zone
     is fabricated to make the sentence true, and a row with no zone-free form
     is dropped rather than reworded into something the payload never said. */
  var CAUTION_NOZONE = {
    "Already moving. Don't chase above the buy zone.":
      ["Already moving. Treat any entry here as a chase.",
       "已在异动。此处入场应视同追高。"]
  };
  function cautionRows(r, hasZone) {
    var out = [], seen = {};
    (r.flags || []).forEach(function (f) {
      var en = f[0], zh = f[1];
      if (!hasZone && (/buy zone/i.test(en) || zh.indexOf("买区") >= 0)) {
        var alt = CAUTION_NOZONE[en];
        if (!alt) return;
        en = alt[0]; zh = alt[1];
      }
      if (seen[en]) return;                 /* a rewrite must not duplicate a row */
      seen[en] = 1;
      out.push([en, zh]);
    });
    return out;
  }

  /* VTC-308 — WHICH ROWS GET THE COMPACT FORM.
     A row with no chart, no quote, no stance rank and no priority has nothing
     for the full card to show; 5-across, ~20 of them became near-identical
     husks each printing "PRIORITY —", with no hierarchy for the eye to use.
     Resolved is compact by definition (a closed plan is record, not inventory);
     a live row is compact only when the enrichment gap has taken everything
     the full form exists to display. */
  function isCompact(r) {
    if (r.life === "resolved") return true;
    return !r.spark && r.px == null && r.pri == null && r.stance === "blocked_data";
  }

  /* PRC-301 — the card's route to the name's detail surface. `stock.html#TICKER`
     is the live cross-market house convention (dashboard.html.j2:19285). The
     anchor carries the ticker and, when the join supplied one, the company
     name — so its accessible name is the name of the thing it opens. */
  function idLink(r) {
    var s = '<a class="pv-open" href="stock.html#' + esc(r.tk) + '">';
    s += '<span class="pv-tk">' + esc(r.tk) + "</span>";
    if (r.nm) s += '<span class="pv-nm">' + esc(r.nm) + "</span>";
    return s + "</a>";
  }

  /* PRC-312 — the stance slot NAMES ITS AXIS.
     27 rows are life=entered + stance=wait, and an unlabelled "WAIT" sitting
     above "Entered" tells a user who is already in the trade not to enter. The
     five sourced verbs are unchanged and there is no sixth; what changes is
     that the card now says which question the verb answers. zh uses 买点, not
     入场: 入场 IS the Entered cell word, and printing it twice is the collision. */
  function stanceGroup(v, noRead) {
    if (!v && !noRead) return "";
    var s = '<span class="pv-stance"><span class="pv-axis">' + t("Entry", "买点") + "</span>";
    if (v) {
      s += '<span class="pv-chip">' + t(VERB[v].en, VERB[v].zh) + "</span>";
    } else {
      s += '<span class="pv-chip pv-chip--noread" tabindex="0"' +
           ' data-tip-t-en="' + esc(NOREAD.tEn) + '" data-tip-t-zh="' + esc(NOREAD.tZh) + '"' +
           ' data-tip-en="' + esc(NOREAD.bEn) + '" data-tip-zh="' + esc(NOREAD.bZh) + '">' +
           t(NOREAD.en, NOREAD.zh) + "</span>";
    }
    return s + "</span>";
  }

  /* the ⚡ chip carries a fact that appears nowhere else on the card, which is
     the shipped rule for keeping it (and its tip). PRC-303: a no-read card
     KEEPS it — the trigger has its own producer and refusing the stance does
     not refuse the event. */
  function triggerChip(r) {
    if (!r.trg) return "";
    var tgEn = r.trg === "imminent"
      ? "The entry trigger has not fired yet, but price is at the level where it would."
      : "The entry trigger fired in the last few sessions.";
    var tgZh = r.trg === "imminent"
      ? "入场触发条件尚未满足，但价格已到达触发位附近。"
      : "入场触发条件已在最近几个交易日内满足。";
    return '<span class="pv-trg" tabindex="0" data-tip-en="' + esc(tgEn) +
           '" data-tip-zh="' + esc(tgZh) + '">&#9889; ' +
           (r.trg === "imminent" ? t("Imminent", "即将触发") : t("Triggered", "已触发")) + "</span>";
  }

  /* THE QUOTE SLOT RENDERS ON EVERY LIVE CARD, with or without an SSR price.
     live.js keys on `.nb-px[data-sym]` / `.nb-chg[data-sym]`, so the node must
     EXIST for a quote to arrive — a card that only renders the slot when the
     candidate join supplied a price can never hydrate. That includes the
     compact form: those rows are exactly the ones with no SSR price, so
     dropping their slot would re-open the bug the slot exists to close.
     PRC-314: a RESOLVED row gets no slot at all — a closed, graded plan has no
     live tape, and printing one made it read as an open position with a gain. */
  function quoteSlot(r) {
    if (r.life === "resolved") return "";
    var c = r.px != null ? demoChange(r.tk) : null;
    var dir = c == null ? "" : c > 0.05 ? " up" : c < -0.05 ? " down" : "";
    return '<span class="pv-quote">' +
      '<span class="nb-px pv-px" data-sym="' + esc(r.tk) + '" data-mkt="us">' +
      (r.px != null ? money(r.px) : "&mdash;") + "</span>" +
      '<span class="nb-chg pv-chg' + dir + '" data-sym="' + esc(r.tk) + '" data-mkt="us"' +
      (c == null ? "" : ' data-mock-live="1"') + ">" +
      (c == null ? "&mdash;" : (c > 0 ? "+" : "") + c.toFixed(1) + "%") +
      "</span></span>";
  }

  function marksRow(r, flags) {
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
       capped and already carries the stance and ⚡, so a third chip there
       collided with the live quote. The count is flags.length AFTER the PRC-303
       coherence pass, so the pill can never over-count its own sentences. */
    if (flags.length) {
      mk += '<span class="pv-cau" tabindex="0" role="button" aria-label="' +
            (S.lang === "zh" ? "风险提示 " : "Caution notes ") + flags.length + '">';
      mk += '<span class="pv-cau-btn">&#9888; ' + flags.length + "</span>";
      mk += '<span class="pv-cau-pop" role="tooltip"><span class="pv-cau-hd">' +
            t("Before you act", "动手之前") + "</span>";
      flags.forEach(function (f) {
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
    return mk;
  }

  function lifeRow(r, L) {
    var h = '<div class="pv-life"><span class="mx-mark mx-mark--' + r.life + '" aria-hidden="true"></span>' +
            '<span class="pv-life-w">' + t(L.en, L.zh) + "</span>";
    if (r.newer) h += newerLink(r);
    return h + "</div>";
  }

  function rowById(id) {
    for (var i = 0; i < B.rows.length; i++) {
      if (B.rows[i].id === id) return B.rows[i];
    }
    return null;
  }

  /* ── P-B2: the newer-plan affordance, which now RESOLVES ──────────────────
     It used to emit `href="#id=<plan>"`. Nothing on this page has ever read an
     `#id=` fragment (the state machine reads location.search only), the cards
     key on `data-id`, and in the one view where these cards appear — the
     Resolved partition — the live row it points at has been filtered out of
     the DOM. Three independent reasons it could not work, in every state.

     MP-1 §10 mandates the capability, so the answer is a mechanism, not a
     deletion. The link is now an ordinary <a> onto the board's own
     query-string contract — `?focus=<plan id>` with the lifecycle filter
     cleared — and applyFocus() below unfilters, expands past the initial cap
     if it has to, scrolls the card into view, rings it and says what it did.
     Ordinary href: middle-click, copy-link and open-in-new-tab all behave, and
     a full navigation lands on the same view a click does.

     If the payload ever carries a `newer` id with no row behind it, the
     affordance renders DISABLED and says why, rather than offering a link that
     goes nowhere — the failure this finding exists to end. Zero rows take that
     branch tonight; both `newer` targets resolve. */
  function newerLink(r) {
    var tgt = rowById(r.newer);
    if (!tgt) {
      return '<span class="pv-newer pv-newer--off" tabindex="0"' +
             ' data-tip-t-en="Newer plan" data-tip-t-zh="最新计划"' +
             ' data-tip-en="This name has a newer plan, but tonight&rsquo;s board does not carry it, so there is nothing to open yet."' +
             ' data-tip-zh="该股已有更新的计划，但今晚的看板尚未收录，因此暂时无法打开。">' +
             t("Newer plan", "最新计划") + "</span>";
    }
    /* the lens states (`episodes`, `fallback`) and the degraded states render a
       SUBSET, so a focus link out of one of them must land on the whole book —
       otherwise the target could be filtered away a second time. */
    var whole = (S.state === "today" || S.state === "stale") ? S.state : "paid";
    var q = qsWith({ state: whole, life: "", view: "grid", focus: tgt.id });
    return '<a class="pv-newer" href="?' + q + '">' +
           t("Newer plan &rarr;", "最新计划 &rarr;") + "</a>";
  }

  /* ── zone footer: the price AREA that matters ─────────────────────────────
     R2-B: ZONE IS GEOGRAPHY, NOT AN INSTRUCTION. The band is shown whatever the
     stance, but only an ACTIONABLE stance renders it in the active treatment
     (.pv-znr). Wait/Avoid get the muted form, Hold gets "Re-add" — the shipped
     zone_kind split (dashboard.html.j2:16183) that the first pass flattened,
     which had made every card's zone read like a buy instruction.
     PRC-314: RESOLVED IS TESTED FIRST. The branch order used to put zk ahead of
     the lifecycle, so AGNT — a closed, graded plan — printed a live buy zone
     while the other 19 read "Closed — in the record". A closed record wins
     precedence over any zone treatment that implies an open plan. */
  function zoneFooter(r, zk) {
    var h = '<div class="pv-zn">';
    if (r.life === "resolved") {
      h += '<span class="pv-znm">' + t("Closed — in the record", "已平仓 — 计入战绩") + "</span>";
    } else if (zk === "active") {
      h += '<span class="pv-znl">' + t("Zone", "买区") + "</span>";
      h += '<span class="pv-znr fig">' + zoneRange(r.zlo, r.zhi) + "</span>";
    } else if (zk === "readd") {
      h += '<span class="pv-znl pv-znl--q">' + t("Re-add", "回补") + "</span>";
      h += '<span class="pv-znm fig">' + zoneRange(r.zlo, r.zhi) + "</span>";
    } else if (zk === "muted") {
      h += '<span class="pv-znl pv-znl--q">' + t("Zone", "买区") + "</span>";
      h += '<span class="pv-znm fig">' + zoneRange(r.zlo, r.zhi) + "</span>";
    } else if (zk === "confirm") {
      h += '<span class="pv-znm">' + t("Zone sets on confirmation", "买区待确认后生成") + "</span>";
    } else {
      h += '<span class="pv-znm">' + t("No zone — stand aside", "无买区 — 观望") + "</span>";
    }
    if (r.opened) h += '<span class="pv-dt">' + t(r.opened.en, r.opened.zh) + "</span>";
    return h + "</div>";
  }

  function card(r, hidden) {
    var L = LEX[r.life];
    var v = r.stance && VERB[r.stance] ? r.stance : null;
    var noRead = r.stance === "blocked_data";
    var resolved = r.life === "resolved";
    var compact = isCompact(r);
    var zk = r.zk || "none";
    /* a zone is on the CARD only where the footer actually prints numbers */
    var hasZone = !resolved && (zk === "active" || zk === "readd" || zk === "muted");
    var flags = cautionRows(r, hasZone);
    var cls = "pvcard" + (v ? " pv-" + v : noRead ? " pv-noread" : "") +
              (r.star ? " pv-featured" : "") +
              (compact ? " pvcard--compact" : "") +
              (hidden ? " sm-hidden" : "");
    /* data-sym is what live.js keys on (.nb-px[data-sym]) to paint the quote and
       the change client-side every ~60s. It is an ATTRIBUTE, not payload — so in
       production the live quote works for 100% of plan rows regardless of the
       candidate-join gap. Only name/sector/lane/spark need an enrichment path
       (DESIGN_NOTES §6 Q1). */
    var h = '<article class="' + cls + '" data-life="' + r.life + '" data-ticker="' +
            esc(r.tk) + '" data-sym="' + esc(r.tk) + '" data-mkt="us" data-id="' + esc(r.id) + '">';

    if (compact) {
      /* the compact archive row: same disclosures, empty slots removed rather
         than drawn empty. No chart hero and no Priority label — those are the
         two slots that had nothing to put in them. */
      h += '<div class="pv-bd">';
      h += '<div class="pv-hd"><span class="pv-idw">' + idLink(r) + "</span>";
      h += quoteSlot(r);
      h += "</div>";
      var cmk = stanceGroup(v, noRead) + triggerChip(r) + marksRow(r, flags);
      if (cmk) h += '<div class="pv-mk">' + cmk + "</div>";
      h += lifeRow(r, L);
      h += "</div>";
      h += zoneFooter(r, zk);
      return h + "</article>";
    }

    /* ── chart hero, with the stance chip and the live quote overlaid ────── */
    h += '<div class="pv-chart">';
    /* VTC-301 / PRC-309: the null is PRINTED, at the chart's own height. */
    h += r.spark ? r.spark
       : '<div class="pv-nochart"><span class="pv-nochart-l">' +
         t("No chart yet", "暂无图表") + "</span></div>";
    h += '<span class="pv-ov pv-ovl">' + stanceGroup(v, noRead) + triggerChip(r) + "</span>";
    h += '<span class="pv-ov pv-ovr">' + quoteSlot(r) + "</span>";
    h += "</div>";

    /* ── identity + priority ────────────────────────────────────────────── */
    h += '<div class="pv-bd">';
    h += '<div class="pv-hd"><span class="pv-idw">' + idLink(r) + "</span>";
    h += '<span class="pv-pri" tabindex="0"' +
         ' data-tip-t-en="Priority" data-tip-t-zh="优先级"' +
         ' data-tip-en="Where this setup ranks in tonight’s Prophet set — how ready it is to act on today. It is not a win probability, an expected return, or a confidence score."' +
         ' data-tip-zh="该计划在本次 Prophet 名单中的排序 — 表示目前有多接近可操作。它不是胜率，也不是预期收益或信心分数。">';
    h += '<span class="pv-pril">' + t("Priority", "优先级") + "</span>";
    h += '<span class="pv-prin' + (r.pri == null ? " pv-prin--na" : "") + ' fig">' +
         (r.pri == null ? "&mdash;" : Math.round(r.pri)) + "</span></span>";
    h += "</div>";
    if (r.sec) h += '<div class="pv-ind">' + sectorLabel(r.sec) + "</div>";

    /* ── marks: restrained, at most three ───────────────────────────────── */
    var mk = marksRow(r, flags);
    if (mk) h += '<div class="pv-mk">' + mk + "</div>";

    /* ── lifecycle: the ruled mark + the cell word. No gloss sentence. ──── */
    h += lifeRow(r, L);
    h += "</div>";
    h += zoneFooter(r, zk);
    return h + "</article>";
  }


  function ghost() {
    return '<div class="pv-ghost" aria-hidden="true"><i></i><i></i><i></i><i></i></div>';
  }

  /* ── V-B4: the LOADING card ────────────────────────────────────────────────
     The shipped card's real geometry — 74px hero, the same body padding, the
     same zone footer rule — so the grid does not reflow when the payload
     lands. Deliberately wordless: a skeleton that labels itself is telling the
     reader about the pipeline, which is the one thing the states section of
     MP-1 forbids. Distinct from ghost(): the lock BLURS content that exists,
     this SHIMMERS where content has not arrived. */
  function skcard() {
    return '<div class="pv-skcard" aria-hidden="true">' +
           '<span class="skel sk-chart"></span>' +
           '<span class="sk-bd"><span class="skel"></span><span class="skel"></span>' +
           '<span class="skel"></span><span class="skel"></span></span>' +
           '<span class="sk-zn"><span class="skel"></span></span></div>';
  }

  /* ── V-B4: the ERROR state ────────────────────────────────────────────────
     The specimen's .mx-error (:114-116, used at :455-459), with MP-1 §10's
     copy shape — name what failed AND what still works, then give a control.

     ONE DELIBERATE DEPARTURE FROM MP-1 §10's VERBATIM STRING: the packet's
     sentence names "Market context" as one of the sections that is still
     current. That section was DELETED at R4 (VTC-307 / §0a.D) for having no
     producer, so the packet's copy would tell the reader to look at something
     that is not on the page. The sentence names the three sections that
     actually survive. MP-1 §10 has to move; the C8-A amendment owns that edit
     (V-B2), and DESIGN_NOTES §9 records which string is law meanwhile.

     No apology, no "oops", no pipeline vocabulary: the sentence says what
     happened, what is unaffected, and what the reader can do. */
  function boardError() {
    var h = '<div class="mx-error" role="alert">';
    h += "<span>" + t(
      "<b>The board didn&rsquo;t load.</b> Candidates, Groups and the record below are current.",
      "<b>看板未能加载。</b>下方的候选、板块与战绩仍是最新。") + "</span>";
    h += '<button class="mx-error-retry" type="button" data-retry="1">' +
         t("Retry", "重试") + "</button>";
    h += "</div>";
    return h;
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
    /* PRC-302 — THE GATE DESCRIBES WHAT A SUBSCRIBER LANDS ON.
       It used to promise "entry, target and void levels included" — three
       numbers no card at any tier renders, because the card tier bans them as
       execution-prescriptive (auth.zone_vs_levels). Either the copy matches the
       product or the ban is re-adjudicated, not both. The ban stands; the copy
       moves. What is listed below is exactly what card() emits. */
    h += "<small>" + t(
      "The rest are part of the live board — every setup with its stance, priority, lifecycle, live quote, buy zone and cautions. The counts above stay honest whether you subscribe or not.",
      "其余计划同在这块看板上——每个计划都含判断、优先级、状态、实时报价、买区与风险提示。无论是否订阅，上方的计数都如实显示。") + "</small>";
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

    /* V-B4 — LOADING. The section keeps its heading (a constant) and skeletons
       the total and the grid. Two rows of cards, because the state has to show
       the grid RHYTHM, not one lonely placeholder; and no expansion bar, since
       there is nothing yet to be showing N of M of. */
    if (isLoad) {
      h += '<div class="mx-sec-hd">';
      h += '<h2 class="mx-sec-h2">' + t("Setups", "跟踪中计划") + "</h2>";
      h += '<span class="mx-sec-total"><span class="skel" style="width:118px;height:12px"' +
           ' aria-hidden="true"></span></span>';
      h += "</div>";
      h += '<div class="pv-grid" aria-busy="true">';
      for (var sk = 0; sk < 10; sk++) h += skcard();
      h += "</div>";
      return h;
    }

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
    if (isStale) {
      h += '<span class="sort-rule">' + t(
        "Mockup-gate lens: how the board reads when the ranking prices are behind the tape. Production computes this state from the board's own freshness check.",
        "样稿评审视角：当排序所用的价格落后于行情时，看板会这样呈现。正式环境下这一状态由看板自身的数据新鲜度判定得出。") + "</span>";
    }
    /* P-K19 — a forced state has to say it is one, on the surface, where a crop
       can see it. This one renders the frozen fixture's counts under the watch
       key production began publishing on 2026-08-18. */
    if (S.watch === "present") {
      h += '<span class="sort-rule">' + t(
        "Mockup-gate lens: the same frozen counts read with <b>early_turn_watch</b> published and empty — the state production has been in since 2026-08-18. Watch shows a real <b>0</b> inside the enclosure and six cells are published, not five.",
        "样稿评审视角：同一份冻结数据，按「观察」名单已发布但为空来呈现——这是 2026-08-18 起正式环境所处的状态。此时「观察」格显示真实的 <b>0</b> 并计入合计，已发布状态为 6 个而非 5 个。") + "</span>";
    }
    /* PRC-304 — the ONE simulated number, disclosed where a crop can see it.
       Every % change in every crop is a deterministic hash of the ticker, and
       the DOM marks it data-mock-live — but that mark is invisible in a
       screenshot, which is how the whole crop set could be read as a live tape. */
    h += '<span class="mock-note">' + t(
      "Quotes are wired to the live feed but not hydrated on this reference: each <b>% change</b> is a per-ticker demo overlay, not a live tape. It is the only simulated number on the page.",
      "本页已接入实时报价接口但未取数：每张卡片的<b>涨跌幅</b>为按代码生成的演示数值，并非真实行情。这是全页唯一的模拟数字。") + "</span>";
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
    /* PRC-311 — a BOARD-LEVEL fact belongs on the BOARD, not inside a frame the
       user has narrowed. The count is right to compute over the whole book (a
       number that moved with the visible rows would be a different number on
       every lens, which is the defect this board exists to cure) — but printing
       it above 2 invalidated cards, or above 20 closed plans, put the one
       integer on the page that does not describe what is on screen. It renders
       on the unfiltered Board and is withheld under a lifecycle filter. */
    if (!S.life) {
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
    }

    /* THE POPULATION IS THE CANONICAL COUNT, not however many cards this view
       happens to draw. On the product states that is the published cell/live
       total, so the expansion bar reconciles to the headline exactly. The
       diagnostic lenses state their own scope in their header instead. */
    var population = (isEps || isFall) ? r.length
                   : (S.life ? cellCount(S.life) : liveTotal());

    if (isAnon) {
      /* anonymous: exactly ONE card's data in the DOM. The rest are contentless
         skeletons — nothing withheld is present to view-source.
         VTC-306: the specimen has to be what the gate is ADVERTISING. It used
         to be r[0] — the rank-1 card, which is a no-read row reading "No read
         yet" and "No zone — stand aside" — so the shop window showed the one
         card that carries none of the goods. The specimen is now the
         highest-priority row that actually holds them: a published entry read,
         a live quote and a zone. It is still ONE real payload row, chosen by
         the board's own sort, with nothing fabricated. */
      var spec = r.filter(function (x) {
        return x.stance && VERB[x.stance] && x.zk === "active" && x.px != null;
      })[0] || r[0];
      h += '<div class="pv-grid">' + card(spec);
      for (var g = 0; g < 4; g++) h += ghost();   /* fills the row; the gate below says how many are withheld */
      h += "</div>";
      h += gate(1);
      return h;
    }

    if (S.view === "table") {
      /* PRC-306 / PRC-313 — THE TABLE CARRIES THE BOARD'S OWN DECISION FIELDS.
         It used to be Ticker · Lifecycle · Entry · Void · First target · Opened
         · Episode: it kept the three execution numbers the card tier bans as
         prescriptive, dropped every instrument a reader would need to judge
         them (stance, priority, zone, caution, chart), applied no validation to
         them (the fixture holds a BULL row whose void sits above its entry and
         the reference published it unremarked) — and, before the grid became
         fully expandable, it was the ONLY representation 77 rows ever got.
         Exact execution geometry belongs in plan detail. What the board ranks
         on belongs here, with honest dashes where a value has not published. */
      h += '<div class="st-wrap"><table class="st-table"><thead><tr>';
      [["Ticker", "代码"], ["Entry read", "买点"], ["Lifecycle", "生命周期"],
       ["Priority", "优先级"], ["Quote", "报价"], ["Zone", "买区"],
       ["Episode", "轮次"], ["Opened", "启动日"]].forEach(function (c) {
        h += "<th>" + t(c[0], c[1]) + "</th>";
      });
      h += "</tr></thead><tbody>";
      r.forEach(function (x) {
        var xl = LEX[x.life];
        var xv = x.stance && VERB[x.stance] ? x.stance : null;
        var xres = x.life === "resolved";
        var xzk = x.zk || "none";
        var xc = (!xres && x.px != null) ? demoChange(x.tk) : null;
        h += "<tr><td><b>" + esc(x.tk) + "</b></td>";
        h += "<td>" + (xv ? t(VERB[xv].en, VERB[xv].zh)
                          : x.stance === "blocked_data" ? t(NOREAD.en, NOREAD.zh) : "—") + "</td>";
        h += '<td><span class="st-life"><span class="mx-mark mx-mark--' + x.life + '" aria-hidden="true"></span>' +
             t(xl.en, xl.zh) + "</span></td>";
        h += '<td class="fig">' + (xres || x.pri == null ? "—" : Math.round(x.pri)) + "</td>";
        h += '<td class="fig">' + (xres || x.px == null ? "—" : money(x.px) +
             ' <span class="pv-chg' + (xc > 0.05 ? " up" : xc < -0.05 ? " down" : "") +
             '" data-mock-live="1">' + (xc > 0 ? "+" : "") + xc.toFixed(1) + "%</span>") + "</td>";
        h += '<td class="fig">' + (xres || !(xzk === "active" || xzk === "readd" || xzk === "muted")
             ? "—" : zoneRange(x.zlo, x.zhi)) + "</td>";
        h += "<td>" + (x.eps ? t(x.ep + " of " + x.eps, "第 " + x.ep + " / 共 " + x.eps) : "—") + "</td>";
        h += "<td>" + (x.opened ? t(x.opened.en, x.opened.zh) : "—") + "</td>";
        h += "</tr>";
      });
      h += "</tbody></table></div>";
      h += '<p class="mx-sec-note" style="margin-top:12px">' + t(
        "Table view shows every row of the current filter: <b>" + population + "</b> rendered. " +
        "Exact entry, target and void levels live in plan detail, not on the board.",
        "表格视图显示当前筛选下的全部条目：已渲染 <b>" + population + "</b> 条。" +
        "具体的入场、目标与失效价位在计划详情页查看，不在看板上呈现。") + "</p>";
      return h;
    }

    /* PRC-306 — EVERY ROW OF THE ACTIVE PARTITION IS A CARD.
       GRID_CAP was a hard ceiling with no expander and a single overflow route
       into the stripped table, so 77 of 179 rows were card-unreachable in every
       state and every filter — and because null-priority rows sort last, the 86
       unscored rows were pushed below the cap by construction. The cap is now
       the INITIAL viewport only: the whole partition is in the DOM and the bar
       below reveals it in place, exactly as production's own initShowMore does. */
    h += '<div class="pv-grid" data-showmore-rows="3">';
    r.forEach(function (x, i) { h += card(x, i >= GRID_CAP); });
    h += "</div>";
    if (population > GRID_CAP) h += showMore(Math.min(GRID_CAP, population), population);
    return h;
  }

  /* ── the expansion bar (production's .sm-* component, theme.js:4784-4869) ──
     COUNT LAW: `shown` and `total` are the canonical population or a computed
     difference of it; `step` is a LAYOUT quantity (rows x the live column
     count), which is where production's "Show 15 more" comes from. Nothing here
     is recounted from rendered rows. */
  function smCount(shown, total) {
    return t('Showing <b class="fig">' + shown + '</b> of <b class="fig">' + total + "</b>",
             '已显示 <b class="fig">' + shown + '</b> / <b class="fig">' + total + "</b>");
  }
  function showMore(shown, total) {
    var h = '<div class="sm-bar" data-total="' + total + '" data-init="' + shown + '">';
    h += '<span class="sm-count">' + smCount(shown, total) + "</span>";
    h += '<span class="sm-btns">';
    h += '<button class="sm-btn" type="button" data-sm="more"></button>';
    h += '<button class="sm-btn sm-ghost" type="button" data-sm="all">' +
         t("Show all " + total, "全部显示 " + total) + "</button>";
    h += '<button class="sm-btn sm-collapse" type="button" data-sm="less" hidden>' +
         t("Show fewer", "收起") + "</button>";
    return h + "</span></div>";
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

    /* VTC-309 — a section whose whole reason to exist is a SECOND population
       may not illustrate itself with a 6-of-6 sample of the first one. All six
       rendered candidates (DAR, MRK, GPCR, CVCO, KEYS, WBD) were setup cards
       directly above. The sample now prefers names the plan book does not
       already carry — a payload fact, not a recount of what the grid drew — and
       the pool permits it (26 of the 70 screened names have no plan row). The
       full population is unchanged and still printed once. */
    var planTk = {};
    B.rows.forEach(function (x) { planTk[x.tk] = 1; });
    var pool = B.cand_rows.filter(function (x) { return !planTk[x.tk]; });
    var cr = (pool.length >= 6 ? pool : B.cand_rows).slice(0, 6);
    h += '<div class="cand-rows">';
    cr.forEach(function (x) {
      h += '<div class="cand-row"><span class="cand-tk">' + esc(x.tk) + "</span>" +
           /* V-B3: the sector is a legitimate name FALLBACK here, so it goes
              through the same twin — otherwise a zh candidate row could still
              print an English sector under a Chinese heading. 0 rows tonight
              (all 70 carry `nm`); the path is bilingual anyway. */
           '<span class="cand-nm">' + (x.nm ? esc(x.nm) : sectorLabel(x.sec)) + "</span>" +
           '<span class="cand-px fig">' + money(x.px) + "</span></div>";
    });
    h += "</div>";
    h += '<p class="mx-sec-note" style="margin:12px 0 0">' + t(
      "Showing 6 that carry no plan yet &middot; <b>" + B.cand_total + "</b> screened " + B.cand_asof,
      "显示其中 6 只尚未建立计划的 &middot; 本次共筛出 <b>" + B.cand_total + "</b> 只 &middot; 筛选日 " + B.cand_asof) + "</p>";
    return h;
  }

  /* ═══════════════ 4. GROUPS — bound to a real producer ══════════════════
     R2-D: the five stance lanes and their sector rows were AUTHORED — invented
     names, invented stances, invented counts. They are replaced by
     `us_standouts.themes_in_favour`, a canonical artifact with an as_of: rank,
     recommendation, run length and member count all come from the payload. If
     the key is absent the section states that, rather than inventing a market
     call to keep the composition full. */
  /* PRC-316 — EVERY SLUG THE PRODUCER CAN EMIT IS MAPPED IN BOTH LANGUAGES.
     Binding the section to a real producer was the right cure for R2's invented
     sector rows, and "straight from the payload" is exactly the path that leaks
     an internal token: the payload carries `enter` (Space Economy) and the map
     knew five values, so the card read "enter 5d up · 15 names" in English on
     the CHINESE surface. The failure was silent by construction — any value the
     map does not know reached the user verbatim. Two changes: `enter` (and the
     rest of the producer's vocabulary) are mapped, and an unknown slug now
     renders NOTHING rather than itself. A missing label is a disclosed gap; a
     raw slug is an untranslated internal token wearing the costume of copy. */
  var RECO = {
    accumulate: { en: "Accumulate", zh: "逐步买入" },
    enter:      { en: "Enter",      zh: "建仓" },
    add:        { en: "Add",        zh: "加仓" },
    hold:       { en: "Hold",       zh: "持有" },
    watch:      { en: "Watch",      zh: "观察" },
    reduce:     { en: "Reduce",     zh: "减仓" },
    trim:       { en: "Trim",       zh: "减仓" },
    exit:       { en: "Exit",       zh: "离场" },
    avoid:      { en: "Avoid",      zh: "回避" }
  };
  function groups() {
    /* rank order is the ordering the section ships; PRC-317 withholds the
       ordinal itself, so the SEQUENCE has to carry it — pin it explicitly
       rather than relying on the producer's array order. */
    var T = (B.themes || []).slice().sort(function (a, b) {
      return (a.rank == null ? 1e9 : a.rank) - (b.rank == null ? 1e9 : b.rank);
    });
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
      var rc = RECO[g.reco];
      h += '<div class="grp">';
      /* PRC-317 — an ORDINAL WITHOUT ITS DENOMINATOR is a stronger claim than
         the producer supports. The eight themes carry ranks 1, 5, 6, 7, 9, 11,
         12, 19 beside a header reading "8 themes in favour", so the surface
         exposed a scale of at least 19 while naming 8 members, and a reader
         could not tell whether "7 · Gold Miners" was 7 of 8 or 7 of 40. The
         payload carries no denominator, so the ordinal is withheld — the list
         is already in rank order, and order carries the ranking without
         asserting a population that is not published. */
      h += '<div class="grp-hd">' +
           '<span class="grp-nm">' + t(esc(g.en), esc(g.zh || g.en)) + "</span></div>";
      h += '<div class="grp-meta">';
      if (rc) h += '<span class="grp-reco">' + t(rc.en, rc.zh) + "</span>";
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

  /* ═══════════════ 5. EVIDENCE ═════════════════════════════════════════
     VTC-307: the page used to end on two consecutive sections of pure
     navigation furniture — "Market context · the weather, not the trade" over
     five contentless pills, then four bare links with no number anywhere, as
     the last things on a 2782px page. Deleting the producer-less regime chips
     was right (R2's PRC-207); keeping their SECTION HEADER and turning the
     chips into links was the defect. The Market context shell is removed
     outright: there is no producer to bind it to, and a header retained over
     deleted content reads as unfinished rather than as restraint.

     PRC-307: the record comes back with NUMBERS, from its real producer —
     engine/track_scoring.summarize() (track_scoring.py:330-392) ->
     emit_ledger() (scripts/grade_us_board.py:2625) ->
     site/factordata/us_track_ledger.json — vendored into the fixture by
     tools/gen_fixture.py, so a rebake keeps it honest and nothing here is
     typed by hand.

     EPISTEMICS: the interval is printed BESIDE the rate, never under it. 58.6%
     with a 50.4-64.4 interval straddles a coin flip on 18 boards over about
     five weeks; a bare win rate here would be exactly the overclaim this review
     cycle exists to catch. The maturity split (how many of the graded rows are
     actually closed) and the window are glance-tier facts, not footnotes. */
  function evidence() {
    var K = B.track;
    var h = '<div class="mx-sec-hd"><h2 class="mx-sec-h2">' + t("Evidence &amp; record", "证据与战绩") + "</h2>";
    if (K) {
      h += '<span class="mx-sec-total">' + t(
        "graded on closed plans &middot; as of " + esc(K.as_of),
        "以已平仓计划评分 &middot; 数据日期 " + esc(K.as_of)) + "</span>";
    }
    h += "</div>";

    if (!K) {
      h += '<div class="mx-empty"><b>' + t("No graded record published", "暂无评分战绩") + "</b>" +
        '<div class="mx-empty-why">' + t(
          "The track ledger has not published. Nothing is asserted in its place.",
          "战绩台账尚未发布。此处不作任何替代性判断。") + "</div></div>";
      return h;
    }

    var sign = K.expectancy_pct > 0 ? "+" : "";
    var expHi = (K.exp_hi_pct > 0 ? "+" : "") + K.exp_hi_pct;
    /* production's shipped strip copy, _track_record_dlg.html.j2:424 — with
       P-B6 applied: BOTH figures now carry their interval on the same line,
       in the same type size, one weight quieter (.trd-band).

       The strip used to print two bare numbers. The win rate survives that
       treatment badly and the per-trade figure does not survive it at all:
       its 95% interval is -0.61 to +1.25, which CROSSES ZERO, so "+0.45% a
       trade" at glance tier states a positive edge the sample does not
       establish. The interval is not a footnote to that claim — it is the
       claim's actual shape, and Law 3 puts it beside the number, not under it.

       The two ranges are punctuated differently ON PURPOSE: an en dash reads
       cleanly between two positive rates (50.4-64.4) and becomes unreadable
       between two signed ones (-0.61-+1.25), so the signed pair takes the
       word. Precision is not worth a glyph the reader has to parse. */
    h += '<div class="trd-wrap"><span class="trd-btn">';
    h += '<span class="trd-lead">' + t("Track record", "往绩") + "</span>";
    h += '<span class="trd-sep">&middot;</span>';
    h += '<span class="trd-stat">' + t(
      "<b>" + K.win_pct + "% win</b> <span class=\"trd-band\">" +
        K.ci_lo_pct + "&ndash;" + K.ci_hi_pct + "</span>",
      "<b>胜率 " + K.win_pct + "%</b> <span class=\"trd-band\">" +
        K.ci_lo_pct + "&ndash;" + K.ci_hi_pct + "</span>") + "</span>";
    h += '<span class="trd-sep">&middot;</span>';
    h += '<span class="trd-stat">' + t(
      "<b>" + sign + K.expectancy_pct + "%</b> a trade <span class=\"trd-band\">" +
        K.exp_lo_pct + " to " + expHi + "</span>",
      "每笔 <b>" + sign + K.expectancy_pct + "%</b> <span class=\"trd-band\">" +
        K.exp_lo_pct + " 至 " + expHi + "</span>") + "</span>";
    h += "</span></div>";

    var cells = [
      [t("Win rate", "胜率"), K.win_pct + "%",
       t("95% CI " + K.ci_lo_pct + "&ndash;" + K.ci_hi_pct,
         "95% 置信区间 " + K.ci_lo_pct + "&ndash;" + K.ci_hi_pct)],
      [t("Per trade", "每笔盈亏"), sign + K.expectancy_pct + "%",
       t("95% CI " + K.exp_lo_pct + "&ndash;" + (K.exp_hi_pct > 0 ? "+" : "") + K.exp_hi_pct,
         "95% 置信区间 " + K.exp_lo_pct + "&ndash;" + (K.exp_hi_pct > 0 ? "+" : "") + K.exp_hi_pct)],
      [t("Median trade", "中位数"), (K.median_pct > 0 ? "+" : "") + K.median_pct + "%",
       t("half land above this", "一半的交易好于此值")],
      [t("Profit factor", "盈亏比"), String(K.profit_factor),
       t("gains over losses", "总盈利 / 总亏损")],
      [t("Graded", "已评分"), K.n_matured + " / " + K.n_total,
       t(K.n_inflight + " still open", "另有 " + K.n_inflight + " 笔未了结")],
      [t("Median hold", "持有天数"), K.median_hold,
       t(K.horizon + "-session verdict", "满 " + K.horizon + " 个交易日强制结算")]
    ];
    h += '<div class="trk-grid">';
    cells.forEach(function (c) {
      /* .fig is tabular numerals for FIGURES only, never words: the headline
         value is a pure figure and takes it; the sub-line is prose carrying a
         number and does not. */
      h += '<div class="trk-i"><span class="trk-l">' + c[0] + "</span>" +
           '<span class="trk-v fig">' + c[1] + "</span>" +
           '<span class="trk-ci">' + c[2] + "</span></div>";
    });
    h += "</div>";

    /* the honest read of the interval, in plain words — not a footnote.
       P-B6: BOTH straddles are translated here now. The win-rate sentence
       existed; the per-trade one did not, and it is the one that matters more,
       because its interval crosses zero rather than merely widening. Plain
       words, no refutation vocabulary (#3821): the sentence says what the
       sample can and cannot settle, and stops. */
    h += '<p class="trk-note">' + t(
      "Read it as an early record, not a settled edge: the win-rate interval " +
      "(<b>" + K.ci_lo_pct + "&ndash;" + K.ci_hi_pct + "</b>) still spans a coin flip, and it is built from " +
      "<b>" + K.n_boards + "</b> boards since " + esc(K.first_board) + ". The per-trade interval " +
      "(<b>" + K.exp_lo_pct + " to " + expHi + "</b>) still crosses zero, so on this much history the average " +
      "trade could as easily have been a small loss as the <b>" + sign + K.expectancy_pct + "%</b> shown. " +
      "Every plan is scored against " + t_bench(K) + " on the same rule for every name.",
      "请把它当作一份仍在积累的早期记录，而不是已经确定的优势：胜率区间（<b>" + K.ci_lo_pct + "&ndash;" + K.ci_hi_pct +
      "</b>）仍跨过 50% 一线，样本为 " + esc(K.first_board) + " 以来的 <b>" + K.n_boards + "</b> 期看板。" +
      "每笔盈亏的区间（<b>" + K.exp_lo_pct + " 至 " + expHi + "</b>）仍跨过 0：以目前的样本量，每笔的真实平均值" +
      "既可能是所示的 <b>" + sign + K.expectancy_pct + "%</b>，也可能是小幅亏损。" +
      "所有计划都以同一规则对照" + t_bench_zh(K) + "评分。") + "</p>";
    h += '<p class="trk-note">' + t(
      "<b>" + K.n_skipped_no_price + "</b> of " + K.n_total + " rows had no usable price and are left out of the scoring; " +
      "rows that have not been graded stay published rather than being dropped from the count.",
      "共 " + K.n_total + " 条中有 <b>" + K.n_skipped_no_price + "</b> 条因缺少可用价格未纳入评分；" +
      "尚未评分的条目照常发布，不会从计数中剔除。") + "</p>";

    h += '<div class="ev-links">';
    [["Track record", "历史战绩"], ["How Prophet works", "Prophet 运作方式"],
     ["Calibration lab", "校准实验室"], ["Closed plans archive", "已结计划存档"]]
      .forEach(function (c) { h += '<a href="#ev">' + t(c[0], c[1]) + "</a>"; });
    h += "</div>";
    return h;
  }
  function t_bench(K) { return esc(K.bench_en || K.bench || "the benchmark"); }
  function t_bench_zh(K) { return esc(K.bench_zh || K.bench || "基准"); }

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
    /* PRC-305 — THE FRESHNESS SLOT. The header could previously only assert
       "Settled close": there was no branch, so the one disclosure that exists
       to stop a reader acting on stale prices could not be expressed in any
       state. Fresh keeps the settled-close token; behind states the state. */
    var fr = freshness();
    if (fr.delayed) {
      h += '<span class="pv-fresh pv-fresh--behind"><span class="dtp-dot"></span>' +
           t("Delayed", "延迟") + "</span>";
    } else {
      h += '<span class="pv-fresh"><span class="dtp-token closed"><span class="dtp-dot"></span>' +
           t("Settled close", "收盘结算") + "</span></span>";
    }
    h += '<span class="dtp-asof">' + esc(B.asof) + "</span>";
    h += "</div></div>";

    /* Production's behind-the-tape banner, verbatim (dashboard.html.j2:15784-89,
       class .nb-stale-note). It already carries exactly the three things this
       disclosure has to carry: the vintage the ranking is on, how far behind
       that is, and what to do about it before acting. */
    if (fr.delayed) {
      var sb = fr.sessions_behind;
      h += '<p class="nb-stale-note">' + t(
        "Still ranked on prices as of " + esc(fr.price_through) + " &mdash; <b>" + sb +
        "</b> session" + (sb === 1 ? "" : "s") + " behind. We&rsquo;re updating it; check a live quote before you act.",
        "仍按截至 " + esc(fr.price_through) + " 的价格排序，落后 <b>" + sb +
        "</b> 个交易日。数据正在更新，操作前请先看一下实时报价。") + "</p>";
    }

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
    var cur = { theme: S.theme, lang: S.lang, state: S.state, life: S.life, view: S.view,
                chrome: S.chrome, watch: S.watch };
    Object.keys(over).forEach(function (k) { cur[k] = over[k]; });
    Object.keys(cur).forEach(function (k) { if (cur[k]) p.set(k, cur[k]); });
    return p.toString();
  }
  function harness() {
    var g = [
      ["theme", [["dark", "Dark"], ["light", "Light"]]],
      ["lang",  [["en", "EN"], ["zh", "中文"]]],
      ["state", [["paid", "Reference"], ["today", "Today (actual)"], ["anon", "Anonymous"], ["empty", "Empty"], ["loading", "Loading"], ["error", "Error"], ["stale", "Behind the tape"], ["episodes", "Multi-episode"], ["fallback", "No-enrichment"]]],
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
    h += "</span>";
    /* P-K19: the watch key's two readings, switchable. Labelled by the FACT
       each one renders, not by the flag name — "present, 0" is what the ladder
       shows, "key absent" is what the frozen fixture carries. */
    h += '<span class="harness-g"><strong>Watch key</strong>';
    h += '<a class="' + (S.watch ? "" : "on") + '" href="?' + qsWith({ watch: "" }) + '">Fixture (absent)</a>';
    h += '<a class="' + (S.watch === "present" ? "on" : "") + '" href="?' + qsWith({ watch: "present" }) + '">Present, 0</a>';
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
    /* V-B4 — in the ERROR state the board's own region is REPLACED by the
       error, not decorated with it: the ladder has no counts and the grid has
       no rows, and a Setups heading standing over nothing is precisely the
       defect VTC-307 deleted a whole section for. The failure sits exactly
       where the failed content would have been, and the page continues. */
    (isErr
      ? '<div class="ladder-block">' + boardError() + "</div>"
      : '<div class="ladder-block">' + ladder() + "</div>" +
        '<section class="mx-sec" id="setups">' + setups() + "</section>") +
    '<section class="mx-sec" id="candidates">' + candidates() + "</section>" +
    '<section class="mx-sec" id="groups">' + groups() + "</section>" +
    /* VTC-307: no `context` section. It had no producer left after the regime
       chips were (correctly) deleted, and a header kept over deleted content is
       the defect the finding names. The page ends on evidence with numbers. */
    '<section class="mx-sec" id="evidence">' + evidence() + "</section>";

  /* ── PRC-306: progressive in-place expansion ─────────────────────────────
     Production's initShowMore (templates/theme.js:4784-4869): the page size is
     the row step x the LIVE column count, which is where "Show 15 more" comes
     from on a 5-column desktop and "Show 6 more" on mobile. Reveal is a class
     toggle on rows already in the DOM, so nothing re-renders and nothing is
     re-fetched.
     COUNT LAW: `total` is the canonical population the renderer printed from
     cellCount()/liveTotal(); `shown` moves by a computed difference of it. The
     column count is a LAYOUT measurement, never a count of setups. */
  (function initShowMore() {
    var grid = document.querySelector(".pv-grid[data-showmore-rows]");
    var bar = document.querySelector(".sm-bar");
    if (!grid || !bar) return;
    var cards = Array.prototype.slice.call(grid.children);
    var total = parseInt(bar.getAttribute("data-total"), 10);
    var init = parseInt(bar.getAttribute("data-init"), 10);
    var step = parseInt(grid.getAttribute("data-showmore-rows"), 10) || 3;
    var shown = init;
    var moreBtn = bar.querySelector('[data-sm="more"]');
    var allBtn = bar.querySelector('[data-sm="all"]');
    var lessBtn = bar.querySelector('[data-sm="less"]');

    function page() {
      var cols = getComputedStyle(grid).gridTemplateColumns.split(/\s+/).filter(Boolean).length;
      /* the floor keeps the mobile step usable: at 390w the grid is ONE column,
         so a bare rows x cols would advance 3 at a time through a 159-row book.
         Production reveals 6 on mobile and 15 on a 5-column desktop; this
         reproduces both. */
      return Math.max(6, step * Math.max(1, cols));
    }
    function paint(reveal) {
      cards.forEach(function (c, i) {
        var hide = i >= shown;
        if (reveal && !hide && c.classList.contains("sm-hidden")) c.classList.add("sm-reveal");
        c.classList.toggle("sm-hidden", hide);
      });
      bar.querySelector(".sm-count").innerHTML = smCount(shown, total);
      var left = total - shown;
      moreBtn.hidden = left <= 0;
      allBtn.hidden = left <= 0;
      lessBtn.hidden = shown <= init;
      if (left > 0) {
        var n = Math.min(page(), left);
        moreBtn.innerHTML = t("Show " + n + " more", "再显示 " + n + " 个");
      }
    }
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("[data-sm]");
      if (!b) return;
      var k = b.getAttribute("data-sm");
      if (k === "more") shown = Math.min(total, shown + page());
      else if (k === "all") shown = total;
      else if (k === "less") { shown = init; grid.scrollIntoView({ block: "start" }); }
      paint(k !== "less");
    });
    window.addEventListener("resize", function () { paint(false); });
    paint(false);
  })();

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
    /* V-B4: Retry re-requests the board. There is no failing fetch to retry in
       a static reference, so it returns to the loaded state — the control does
       the one thing its word promises and nothing is faked around it. */
    if (e.target.closest("[data-retry]")) { location.search = qsWith({ state: "paid" }); }
  });
  if (S.life) {
    try { history.replaceState(null, "", location.pathname + location.search + "#life=" + S.life); } catch (err) {}
  }

  /* ── P-B2: land on the plan the newer-plan link asked for ─────────────────
     Three outcomes, all of them honest:
       1. the card is in the DOM  -> reveal it if the initial cap is hiding it,
          scroll, ring it, move focus there, and say what happened;
       2. the row exists but sits behind a filter this view is not showing ->
          offer the one link that reaches it, never a silent no-op;
       3. no such row on tonight's book -> say exactly that.
     The note is written in the reader's vocabulary — ticker, not plan id: a
     plan slug is an internal identifier and never reaches a user surface. */
  (function applyFocus() {
    if (!S.focus) return;
    var sec = document.getElementById("setups");
    if (!sec) return;
    var grid = sec.querySelector(".pv-grid");
    var target = null, cards = sec.querySelectorAll(".pvcard");
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].getAttribute("data-id") === S.focus) { target = cards[i]; break; }
    }

    function note(inner) {
      var p = document.createElement("p");
      p.className = "pv-landnote";
      p.innerHTML = inner;
      if (grid) grid.parentNode.insertBefore(p, grid);
      else sec.appendChild(p);
    }

    if (!target) {
      var row = rowById(S.focus);
      if (row) {
        var href = "?" + qsWith({ state: "paid", life: row.life, view: "grid", focus: row.id });
        note(t("<b>" + esc(row.tk) + "</b> is on tonight&rsquo;s book, but not in this view. " +
               '<a href="' + href + '">Open it in ' + LEX[row.life].en + "</a>",
               "<b>" + esc(row.tk) + "</b> 在今晚的计划簿中，但不在当前视图内。" +
               '<a href="' + href + '">在「' + LEX[row.life].zh + "」中打开</a>"));
      } else {
        note(t("That plan is not on tonight&rsquo;s board. " +
               '<a href="?' + qsWith({ focus: "" }) + '">Back to the full board</a>',
               "该计划不在今晚的看板上。" +
               '<a href="?' + qsWith({ focus: "" }) + '">返回完整看板</a>'));
      }
      return;
    }

    /* reveal through the expansion bar rather than around it, so `Showing N of
       M` repaints from the same accessor instead of disagreeing with the DOM */
    if (target.classList.contains("sm-hidden")) {
      var all = document.querySelector('.sm-bar [data-sm="all"]');
      if (all) all.click();
    }
    target.classList.add("pv-landed");
    var tk = target.getAttribute("data-ticker") || "";
    note(t("Showing the live plan on <b>" + esc(tk) + "</b>. " +
           '<a href="?' + qsWith({ focus: "" }) + '">Back to the full board</a>',
           "已定位到 <b>" + esc(tk) + "</b> 的最新计划。" +
           '<a href="?' + qsWith({ focus: "" }) + '">返回完整看板</a>'));
    /* Focus lands on the CARD, not on its title link: the thing the reader
       asked for is the plan, and focusing the anchor painted a second ring
       inside the first. `tabindex="-1"` makes the card programmatically
       focusable without entering the tab order, and .pv-landed IS the visible
       focus indicator — one ring, one meaning. */
    try {
      target.setAttribute("tabindex", "-1");
      target.scrollIntoView({ block: "center" });
      target.focus({ preventScroll: true });
    } catch (err) {}
  })();

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

/* portfolio.js — the Position Assessment desk for the watchlist page.

   Owns #pf_section and all DOM within it. Inert on pages that lack the section.
   Auth state arrives via document 'wl-auth' events dispatched by watchstore.js.
   Price/signal data comes from window.SD (stockdata.js, store-aware per market).
   Portfolio CRUD goes through window.WatchStore.portfolio — Supabase when signed in,
   the localStorage book when signed out (same API either way).

   Every row carries the desk's read: signal state, stage of rise, extension, role
   ladder — and opens into a per-name drawer built from the SAME laneRead engine the
   cards use (window.WRI, exported by watchlist_risk.js — never duplicated here).

   Books: rows partition by market (window.MB). Each book's totals stay in its OWN
   currency — there is no cross-currency sum anywhere in this file.

   Factor wiring: after every render, pushes {ticker->dollarValue} weights to
   window.FX.setAutoWeights() — filtered to the MODELED (US-store, USD) subset, so a
   HKD/CNY/CAD value can never enter a USD weight sum (A3 law 3).

   No engine/data writes, no network except WatchStore.portfolio, SD.loadTicker/
   loadIndexes, and ONE idle-deferred ctx fetch. Nothing position-derived is logged. */
(function () {
  'use strict';

  // ---- guard: only active when the section exists --------------------------
  // The workspace's holdings table is this file's host — #pf_section is gone with
  // the old IA. Inert on any page that does not carry it.
  function section() { return document.getElementById('ws_sec_hold'); }

  // ---- i18n ----------------------------------------------------------------
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  function isZh() { return lang() === 'zh'; }
  var T = {
    en: {
      emptyHeading: 'No open positions yet.',
      addBtn: '+ Add position',
      colPosition: 'Position',
      colValue: 'Value',
      colSince: 'Since entry',
      colAssess: 'Assessment',
      editBtn: 'Edit position',
      removeBtn: 'Remove',
      closedHeading: 'Closed positions',
      closedCount: function (n) { return n + ' closed'; },
      unavailable: 'Portfolio unavailable right now — your data is safe.',
      modalAddTitle: 'Add position',
      modalEditTitle: 'Edit position',
      tickerLabel: 'Ticker', sharesLabel: 'Shares', entryLabel: 'Entry price',
      dateLabel: 'Entry date', notesLabel: 'Notes', statusLabel: 'Status',
      statusOpen: 'Open', statusClosed: 'Closed', saveBtn: 'Save',
      tickerRequired: 'Ticker is required.',
      saveError: 'Could not save — please try again.',
      notCovered: 'Not in our coverage — price and signal will show —',
      asof: 'as of',
      atCost: 'at cost',
      localCcy: 'local currency',
      positions: function (n) { return n + (n === 1 ? ' position' : ' positions'); },
      book: 'book',
      signinKeep: 'Sign in to keep this book tracked across devices — free.',
      signIn: 'Sign in',
      privLocal: 'Holdings stay in this browser until you sign in.',
      privAccount: 'Holdings are stored privately in your account.',
      noEntryRead: 'No entry read tonight',
      notInLibrary: "This name isn't in tonight's library — value shown at cost.",
      dossier: 'Full dossier →',
      terminal: 'Chart in Terminal →',
      lblStage: 'Stage',
      // A1A frozen copy (research/market_os/…A1A_COMMISSIONING…md §13c) — verbatim
      degradedBanner: 'Cloud portfolio unavailable — showing your last saved positions (read-only).',
      errorBanner: "Cloud portfolio unavailable. We can't show your positions right now.",
      loadingMsg: 'Loading your positions…',
      equalAssumed: 'Equal weights assumed — no position sizes entered.',
      mixedAbstain: 'Weights not shown — mix of sized and unsized positions.',
      mixedBasisAbstain: 'Weights not shown — mix of live-priced and at-cost positions.',
      unresolvedBasisAbstain: 'Weights not shown — a position has no resolvable price.',
      singlePositionBook: 'One position in this book — a relationship read needs at least two.',
      costWeighted: 'Weighted by entry cost — live prices are not available for these positions.',
      onePosSay: 'This book is one position',
      onePosBecause: 'There is nothing to compare it against yet. Add a second position and this reads what your book really is.',
      emptyBookSay: 'Add a second position and this reads what your book really is.'
    },
    zh: {
      emptyHeading: '暂无开仓持仓。',
      addBtn: '+ 添加持仓',
      colPosition: '持仓',
      colValue: '市值',
      colSince: '入场以来',
      colAssess: '系统评估',
      editBtn: '编辑持仓',
      removeBtn: '移除',
      closedHeading: '已平仓',
      closedCount: function (n) { return n + ' 条已平仓'; },
      unavailable: '暂时无法加载持仓——你的数据安全无虞。',
      modalAddTitle: '添加持仓',
      modalEditTitle: '编辑持仓',
      tickerLabel: '代码', sharesLabel: '股数', entryLabel: '入场价',
      dateLabel: '入场日期', notesLabel: '备注', statusLabel: '状态',
      statusOpen: '开仓', statusClosed: '已平仓', saveBtn: '保存',
      tickerRequired: '代码不能为空。',
      saveError: '保存失败——请重试。',
      notCovered: '不在覆盖范围——价格与信号将显示 —',
      asof: '数据截至',
      atCost: '按成本',
      localCcy: '本币',
      positions: function (n) { return n + ' 笔持仓'; },
      book: '账本',
      signinKeep: '登录即可跨设备保存并追踪——免费。',
      signIn: '登录',
      privLocal: '持仓保存在本浏览器中，登录后同步。',
      privAccount: '持仓仅保存在你的账户中。',
      noEntryRead: '今晚无入场读数',
      notInLibrary: '该名称不在今晚的库中——数值按成本显示。',
      dossier: '完整档案 →',
      terminal: '在终端查看图表 →',
      /* This comment used to sit here explaining the DISTANCE row's zh label (偏离度,
         not 拉伸度). That row moved into the shared composer in round 3 and the note
         stayed behind attached to Stage, describing a key it has nothing to do with —
         so it is retired here. The live version of the ruling, now that the lane is
         labelled 入场拉伸 and the row 偏离度, lives beside each of them in
         `watchlist_risk.js`. */
      lblStage: '阶段',
      degradedBanner: '云端持仓暂不可用 —— 显示你最后一次保存的持仓（只读）。',
      errorBanner: '云端持仓暂不可用。目前无法显示你的持仓。',
      loadingMsg: '正在加载持仓…',
      equalAssumed: '按等权重计算 —— 未输入仓位大小。',
      mixedAbstain: '未显示权重 —— 部分持仓有仓位大小，部分没有。',
      mixedBasisAbstain: '未显示权重 —— 部分按现价，部分按成本价。',
      unresolvedBasisAbstain: '未显示权重 —— 有一笔持仓没有可用价格。',
      singlePositionBook: '这本账簿只有一笔持仓——关系读数需要至少两笔。',
      costWeighted: '按成本价加权 —— 这些持仓暂无实时价格。',
      onePosSay: '这本账簿只有一笔持仓',
      onePosBecause: '目前还没有可比较的对象。再添加一笔持仓，这里就会读出你的账簿到底是什么。',
      emptyBookSay: '再添加一笔持仓，这里就会读出你的账簿到底是什么。'
    }
  };
  function L(k) { return (T[lang()] || T.en)[k]; }
  function te(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>';
  }

  // ---- tiny utils ----------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function num(v) {
    if (v === '' || v == null) return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }
  function group(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

  // ---- state ---------------------------------------------------------------
  var rows = null;          // portfolio rows; null until first load OR genuinely unknown
                             // (A1A: a cloud read error with no last-good — never [])
  var editingId = null;
  var priceCache = {};      // ticker -> {price, asof} | null (uncovered)
  var jsonCache = {};       // ticker -> full per-ticker JSON | null
  var hydrated = false;     // per-ticker fetch pass already kicked off
  var lastListAt = 0;
  var sdIndex = null;       // merged {list, byTicker} across the markets in play
  var ctxMap = null;        // portfolio_ctx tickers map (US stage rows); null until loaded
  var ctxTried = false;
  var prevFocusEl = null;
  var openDrawers = {};     // row id -> true (survives re-render)
  // A1A: {authority, state, last_good_at, warning} from watchstore.js's read seam —
  // 'ready' | 'degraded' (last-good, read-only) | 'error' (unknown, nothing to show)
  var readState = { authority: 'local', state: 'ready', last_good_at: null, warning: null };
  // A1A blocker 3 (write-failure honesty): 'clean' | 'saving' | 'saved' | 'failed'.
  // Never stores 'offline_readonly' directly — that word is DERIVED (see
  // refreshSnapshot below) whenever the read authority itself is degraded/error and
  // no write is in flight; there is no authenticated outbox to call anything "clean".
  var writeState = 'clean';
  // N2 (Sol post-review, MAJOR, re-opens F3 — proofG d2/d3): `writeState` used to
  // survive an auth identity change untouched — a signed-in user's write FAILURE
  // (the account-scoped 'failed' word) leaked onto the NEXT identity's very first
  // read: an anonymous visitor who never wrote anything saw "Change not saved" the
  // instant they signed out, and a SECOND user's first healthy read painted the
  // same false disclosure for a write they never made. Tracked the same way
  // watchlist.js tracks its own auth boundary (undefined = never seen a wl-auth
  // yet, so no reset needed — writeState is already 'clean' at that point).
  var lastAuthIdentity;
  // A1A blocker 2 decision (Sol): the ONE portfolio_snapshot.v1 this file consumes —
  // never a second, independently-derived mirror of the same population/read/write
  // facts. Refreshed by refreshSnapshot(); null whenever window.PS has not deployed
  // yet (B2 split-deploy window) or rows is genuinely unknown.
  var snapshot = null;
  // LAW 2 (A1A round-3, consumer request-generation guard): every list() CALL bumps
  // this counter; a resolution (.then OR .catch) whose captured `gen` no longer
  // matches the CURRENT `loadGen` is stale and mutates NOTHING — not rows, not
  // readState, not the chip dispatch, not DOM, not count, not the FX push chain.
  // This is the CONSUMER-side half of LAW 1's auth-epoch binding: even a
  // watchstore.js resolution that legitimately resolves rows (e.g. a plain slow
  // network read under the SAME identity, no auth transition at all) must still be
  // discarded here if a NEWER list() call has since superseded it — reload()'s
  // visibility refetch and onAuth()'s auth-flip trigger can both fire while an
  // older call is still in flight.
  var loadGen = 0;

  // ---- portfolio_state.js seam ----------------------------------------------
  function PS() { return window.PS || null; }

  /* Assembles the canonical `portfolio_snapshot.v1` (research/market_os/…A1A…§9-12)
     from the CURRENT rows/readState/writeState and holds it in `snapshot`. Every
     population, read-state and write-state question this file answers reads THIS
     object — openRows()/closedRows() (population + the table's row set),
     renderReadBanner() (the read story) and the write-honesty dispatch all route
     through it, rather than re-deriving the same fact a second, independent way.
     PS-absent (split-deploy window, B2): `snapshot` stays null and every consumer
     below falls back to its own pre-PS literal check on rows/readState — legacy-
     quiet, no weighting-law claim, the existing B2 fallback untouched. */
  function refreshSnapshot() {
    var ps = PS();
    if (!ps) { snapshot = null; return null; }
    var effWrite = writeState;
    if (effWrite === 'clean' && readState.authority === 'cloud' &&
        (readState.state === 'degraded' || readState.state === 'error')) {
      effWrite = 'offline_readonly';
    }
    snapshot = ps.computeSnapshot({
      rows: rows,
      authority: readState.authority,
      readState: readState.state,
      writeState: effWrite,
      priceOf: priceOf,
      bookOf: marketOf,
      lastGoodAt: readState.last_good_at,
      warning: readState.warning
    });
    return snapshot;
  }

  // ---- market/book seam ----------------------------------------------------
  function MB() { return window.MB || null; }
  function marketOf(t) { var m = MB(); return m ? m.marketOf(t) : 'us'; }
  function isModeled(t) { var m = MB(); return m ? m.isModeled(t) : true; }
  function activeBook() { var m = MB(); return m ? m.getBook() : 'all'; }
  function bookMeta(b) { var m = MB(); return m && m.BOOKS[b] ? m.BOOKS[b] : null; }
  function bookOrder() { var m = MB(); return m ? m.BOOK_ORDER : ['us']; }
  function bookName(b) { var m = MB(); return m ? m.bookName(b, false) : b; }
  function bookNameZh(b) { var m = MB(); return m ? m.bookName(b, true) : b; }

  // ---- view helpers --------------------------------------------------------
  function showEl(id) { var e = el(id); if (e) e.style.display = ''; }
  function hideEl(id) { var e = el(id); if (e) e.style.display = 'none'; }
  function setText(id, txt) { var e = el(id); if (e) e.textContent = txt; }

  function showError() {
    hideEl('pf_desk'); hideEl('pf_empty'); hideEl('pf_add'); hideEl('pf_import'); hideEl('pf_closed');
    var errDiv = el('pf_err_inline');
    // A1A frozen copy (§13c): a cloud read error with no last-good rows — never a
    // silent zero, never the local book substituted in.
    if (errDiv) { errDiv.textContent = L('errorBanner'); errDiv.style.display = 'block'; }
  }
  /* A1A blocker 2 (Sol, consumer-level auth-transition fix): the delayed-cloud window
     (onAuth()'s synchronous rows=null + 'loading' clear, below) must paint HONESTLY
     too — never silently leave a PRIOR authority's table (the anonymous local rows,
     or a previous signed-in user's cloud rows, B1) standing on screen while THIS
     authority's real read is still unknown. Table content is cleared, not merely
     hidden — a hidden-but-present stale row is still a leak the moment anything
     un-hides it. Never an error tone: this is expected, resolving traffic. */
  function showLoading() {
    hideEl('pf_desk'); hideEl('pf_empty'); hideEl('pf_add'); hideEl('pf_import'); hideEl('pf_closed');
    var host = el('tbl_pf');
    if (host) host.innerHTML = '';
    var errDiv = el('pf_err_inline');
    if (errDiv) {
      errDiv.textContent = L('loadingMsg');
      errDiv.className = 'pf-err-inline is-loading';
      errDiv.style.display = 'block';
    }
  }

  // ---- index ---------------------------------------------------------------
  // Load the indexes for every market the user actually touches (watchlist ∪ rows),
  // so a .HK / .SS / .TO row resolves its name + signal state like any US name.
  function marketsInPlay() {
    var want = { us: 1 };
    (rows || []).forEach(function (r) { if (r && r.ticker) want[marketOf(r.ticker)] = 1; });
    var wl = (window.WL && window.WL.getBlob) ? window.WL.getBlob() : null;
    if (wl && wl.items) wl.items.forEach(function (it) { want[marketOf(it.t)] = 1; });
    return Object.keys(want);
  }
  function ensureIndex() {
    if (!window.SD || !window.SD.loadIndexes) return Promise.resolve(null);
    return window.SD.loadIndexes(marketsInPlay()).then(function (r) {
      sdIndex = r; return r;
    }).catch(function () { return null; });
  }
  function idxRec(t) {
    return (sdIndex && sdIndex.byTicker && sdIndex.byTicker[t]) || null;
  }
  function tickerName(t) { var r = idxRec(t); return r ? (r.n || '') : ''; }
  function tickerSt(t) { var r = idxRec(t); return r ? (r.st || null) : null; }

  // ---- open/closed split -----------------------------------------------------
  // A1A blocker 2: sourced from the ONE portfolio_snapshot.v1 (refreshSnapshot()) —
  // never a second independent filter of `rows`. PS-absent falls back to the exact
  // pre-PS literal filter (B2: legacy-quiet, never a divergent answer).
  function openRows() {
    if (!rows) return [];
    var snap = refreshSnapshot();
    // F5 (Sol post-review): the PS-absent fallback must filter IDENTICALLY to
    // portfolio_state.js's own openRowsOf() (a truthy `r.ticker` required, not
    // just `r`) — a divergent fallback filter is exactly the kind of second,
    // independent population answer this file is meant to have retired.
    var list = snap ? snap.open_rows
      : rows.filter(function (r) { return r && r.ticker && r.status !== 'closed'; });
    return list.slice().sort(function (a, b) { return (a.ticker || '').localeCompare(b.ticker || ''); });
  }
  function closedRows() {
    if (!rows) return [];
    var snap = refreshSnapshot();
    var list = snap ? snap.closed_rows
      : rows.filter(function (r) { return r && r.ticker && r.status === 'closed'; });
    return list.slice().sort(function (a, b) { return (a.ticker || '').localeCompare(b.ticker || ''); });
  }

  // ---- value math (per row; never crosses a currency) ----------------------
  function priceOf(t) {
    var pc = priceCache[t];
    return (pc && isNum(pc.price)) ? pc.price : null;
  }
  /* {value, atCost} for a row — shares×price, else shares×entry ("at cost").
     null value when the row carries no shares (a watch-only holding). */
  function rowValue(r) {
    var sh = num(r.shares), px = priceOf(r.ticker), entry = num(r.entry_price);
    if (sh == null || sh <= 0) return { value: null, atCost: false };
    if (px != null && px > 0) return { value: sh * px, atCost: false };
    if (entry != null && entry > 0) return { value: sh * entry, atCost: true };
    return { value: null, atCost: false };
  }
  function fmtMoney(v, book) {
    var meta = bookMeta(book);
    var ccy = meta ? meta.ccy : '$';
    return (ccy || '') + group(Math.round(v));
  }

  // ---- factor weight wiring (FX-corruption guard) --------------------------
  // Only US-store names (us + crypto + macro — all USD) may enter the weight sum.
  // A .HK / .SS / .TO dollar value in here would silently corrupt every book
  // statistic downstream (betas, ENB, correlations, MCTR). A3 law 3.
  function pushFxWeights() {
    if (!window.FX || !window.FX.setAutoWeights) return;
    /* Harness non-vacuity finding (Sol post-review, F2 follow-on): this function
       runs on every one of THIS file's own render passes, regardless of which
       workspace tab is active — a hydration wave, ensureIndex(), or a background
       reload() can all trigger it while the reader is sitting on the Watchlists
       tab. AUTO_W is a non-null value the instant this pushes ANYTHING (even the
       honest-empty {} F2 requires), and factor_exposure.js's `autoMode = AUTO_W
       !== null` check does not know or care which tab is active — so a push here
       permanently overrides the Watchlists tab's OWN FX.update() reset (browser
       after-proof: the watchlist-mode fx-weights trace went empty/auto even
       though the reader was looking straight at the Watchlists panel). "Watchlist
       names feed FX ONLY in [watchlists] mode" (watchlist.js's own render()) has
       the same law in reverse here: Portfolio dollar values feed FX ONLY while
       the Portfolio tab is the active mode. `window.WS.mode` absent (an isolated
       test harness, or watchlist.js not on the page) defaults to allowing the
       push — unchanged from every existing behavior that never depended on mode. */
    var activeMode = (window.WS && window.WS.mode) ? window.WS.mode() : 'portfolio';
    if (activeMode !== 'portfolio') return;
    var modeled = openRows().filter(function (r) { return r.ticker && isModeled(r.ticker); });
    var w = {};
    /* A1A weighting law (§12): "for an all-unsized modeled book the page applies
       FX.setAutoWeights({SYM:1,...})" — an unsized modeled book used to push an EMPTY
       weight map (every row skipped by the shares>0 guard below), so the factor read
       never activated for it at all. computeWeighting's `all_unsized_equal` state is
       what names that case; everything else keeps the original real-value math. */
    var ps = PS();
    var wgt = ps ? ps.computeWeighting(modeled, priceOf) : null;
    if (wgt && wgt.state === 'all_unsized_equal') {
      modeled.forEach(function (r) { w[r.ticker] = 1; });
    } else if (wgt && wgt.complete !== true) {
      /* S3 (review): an ABSTAINING book (mixed sizing, mixed price basis, unresolved
         basis) must reach the factor engine with NO weights at all — the page's own
         Book Read says "weights not shown"; it must not also be true that FX is
         silently computing betas/ENB/MCTR from a distribution the user was told does
         not exist. `w` stays `{}` and is pushed via the dedicated call below rather
         than through the `keys.length>=2 ? w : null` ternary, because `null` here
         would fall FX back to its manual/equal-weight path over `LAST` (whatever
         watchlist.js most recently fed `FX.update` — a DIFFERENT leak: the book's
         factor read would silently become a Watchlist-derived one). Verified against
         factor_exposure.js: `setAutoWeights({})` sets `AUTO_W={}` (an object, so
         `autoMode` stays true — `null` is the only value that flips it off), giving
         `render()` an empty `universe`; `aggregate([]...)` returns `{ok:false}` on
         `held.length < 2`, so the panel hides — an honest absence, not garbage. */
      window.FX.setAutoWeights({});
      return;
    } else if (wgt && wgt.complete === true) {
      modeled.forEach(function (r) {
        var t = r.ticker;
        var sh = num(r.shares), px = priceOf(t);
        if (sh != null && sh > 0 && px != null && px > 0) w[t] = sh * px;
      });
    } else {
      /* F5 (Sol post-review, MAJOR): PS-absent (`wgt === null`, split-deploy
         window) used to silently DROP any row that was not both sized and live-
         priced from `w` — the weights that DID make it in still summed to 100%
         of THEMSELVES, presented as if they were the whole book: a fabricated
         distribution, the same class of defect §12/S3 exist to forbid. Mirrors
         renderBookRead's own B2 `allCurrent` condition: real per-row weights are
         pushed ONLY when EVERY open modeled row is sized AND live-priced;
         anything else pushes the honest-empty `{}` (no claim) rather than a
         partial view of who is actually weighted. */
      var allCurrent = modeled.length > 0 && modeled.every(function (r) {
        var sh = num(r.shares), px = priceOf(r.ticker);
        return sh != null && sh > 0 && px != null && px > 0;
      });
      if (allCurrent) {
        modeled.forEach(function (r) { w[r.ticker] = num(r.shares) * priceOf(r.ticker); });
      } else {
        window.FX.setAutoWeights({});
        return;
      }
    }
    var keys = Object.keys(w);
    /* W2 seeded `FX.update(keys)` here before announcing, because `FX.setAutoWeights`
       bailed on an empty `LAST` — so a full book with an EMPTY watchlist never reached
       RiskCore. W3 fixed that at the mechanism (factor_exposure.js: the auto path's
       universe is the weight map, never `LAST`), so the seeding call is retired rather
       than left as a second, silent guarantee of the same property. One owner for the
       auto path means the regression test pins the path production actually takes.
       Sol blocker 1 (Risk Center residue, producer (c), PS-absent): `null` here means
       "fall back to manual mode over LAST" in factor_exposure.js — LAST is whatever
       watchlist.js most recently fed FX.update(), i.e. the WATCHLIST universe. A
       resolved-but-thin Portfolio book (keys.length < 2) used to push exactly that
       null, actively re-rendering a Watchlist-derived read into the Concentration tab
       while Portfolio mode shows 0/1 positions. The honest-empty `{}` (the same
       signal the S3 abstain branch above already uses) keeps `autoMode` true and the
       universe empty — an honest absence, never a fallback to someone else's data.
       `null` must stay unreachable from a resolved portfolio state. */
    window.FX.setAutoWeights(keys.length >= 2 ? w : {});
  }

  // =========================================================================
  //  Assessment cell — Tier-1 budget: 1 pill + at most 2 chips + 1 badge
  // =========================================================================
  var STAGE_WORDS = {
    1: { chipEn: 'Stage 1 · basing',    chipZh: '第1阶段 · 筑底',
         drawEn: 'Basing — stage 1 of 4',    drawZh: '筑底——第1阶段（共4段）' },
    2: { chipEn: 'Stage 2 · rising',    chipZh: '第2阶段 · 上行',
         drawEn: 'Rising — stage 2 of 4',    drawZh: '上行——第2阶段（共4段）' },
    3: { chipEn: 'Stage 3 · topping',   chipZh: '第3阶段 · 筑顶',
         drawEn: 'Topping — stage 3 of 4',   drawZh: '筑顶——第3阶段（共4段）' },
    4: { chipEn: 'Stage 4 · declining', chipZh: '第4阶段 · 下行',
         drawEn: 'Declining — stage 4 of 4', drawZh: '下行——第4阶段（共4段）' }
  };
  function ctxStage(t) {
    if (!ctxMap) return null;
    var e = ctxMap[t];
    var s = e && e.stage;
    if (!s) return null;
    var w = STAGE_WORDS[s.n];
    if (!w) {
      // n outside 1–4: fall back to the verbatim engine label, never an invented word
      if (!s.label) return null;
      return { chipEn: esc(s.label), chipZh: esc(s.label),
               drawEn: esc(s.label), drawZh: esc(s.label), weeks: s.weeks };
    }
    return { chipEn: w.chipEn, chipZh: w.chipZh, drawEn: w.drawEn, drawZh: w.drawZh,
             weeks: s.weeks };
  }

  /* Stretch read. US names carry the precise 4-grade `ext` block; every other market
     carries the universal `ladder.alignment.overextended` bool instead (the engine
     classifies the 4-grade extension for US listings only). */
  function stretchOf(t, j) {
    if (!j) return null;
    if (isModeled(t) && j.ext && j.ext.grade) {
      var g = j.ext.grade;
      if (g === 'parabolic') return { grade: g, hot: true, en: 'Parabolic', zh: '抛物线拉伸' };
      if (g === 'stretched') return { grade: g, hot: false, en: 'Stretched', zh: '过度拉伸' };
      return null;   // intrend / steady -> no chip
    }
    var al = j.ladder && j.ladder.alignment;
    if (al && al.overextended === true) {
      return { grade: 'stretched', hot: false, en: 'Stretched', zh: '过度拉伸' };
    }
    return null;
  }

  function extGradeOf(t, j) {
    if (isModeled(t) && j && j.ext && j.ext.grade) return j.ext.grade;
    var al = j && j.ladder && j.ladder.alignment;
    if (al && al.overextended === true) return 'stretched';
    return 'intrend';
  }
  /* The elevated half of that vocabulary, named ONCE. The engine emits exactly five
     words (engine/extension.py GRADES: intrend / steady / stretched / parabolic / na)
     and flags two of them is_caution=True — the same two watchlist_sentinel.py vetoes
     on (_BLOCKED_GRADES) and the same two stretchOf() above puts a chip on.

     It is named once because it was not: three readers each carried their own
     `g === 'high' || g === 'extreme'` — words this engine has never emitted in any
     version — so the "Stretched" row flag and stack rules 1 and 3 were dead from the
     day they shipped, silently, on 467 of the 1630 modeled names (28.6%) carrying an
     elevated grade. Three copies of a comparison drift as one; one copy cannot. */
  function isElevatedGrade(g) { return g === 'stretched' || g === 'parabolic'; }

  function roleOf(t, j) {
    if (!j || !window.WRI || !window.WRI.laneRead || !window.WRI.roleBadge) return null;
    try { return window.WRI.roleBadge(window.WRI.laneRead(j)); } catch (e) { return null; }
  }

  // =========================================================================
  //  Drawer — the per-name detail, and the ONE place a lane failure is spoken
  // =========================================================================
  /* Row painter. Delegates to `WRI.lrowHTML` when the gated risk layer is present, so
     the drawer has ONE row grammar rather than two that drift; the local fallback keeps
     the stateless rows rendering when it is not (an anonymous visitor, or a 401 on the
     gated bundle). Both emit the EMPTY `.st` cell: the row is a three-column grid, and
     the old local version omitted it, which dropped every stateless row's read into the
     state column. */
  function lrow(labEn, labZh, stCls, stTok, readEn, readZh) {
    if (window.WRI && window.WRI.lrowHTML) {
      return window.WRI.lrowHTML({ lab: { en: labEn, zh: labZh },
        state: stCls, token: stTok, en: readEn, zh: readZh });
    }
    return '<div class="wri-lrow"><span class="ln">' + te(labEn, labZh) + '</span>' +
      (stCls ? '<span class="st ' + stCls + '">' + stTok + '</span>' : '<span class="st"></span>') +
      '<span class="rs">' + te(readEn, readZh) + '</span></div>';
  }
  function terminalHref(t) {
    // verified route (charting-app terminal/app/terminal/page.tsx reads ?symbol ?? ?sym)
    return 'https://app.mastermind-x.com/terminal?sym=' + encodeURIComponent(t) + '&from=macro';
  }
  /* The dossier. `stock.html` reads its ticker from `location.hash` and from nothing
     else (templates/stock.html.j2 — four separate readers, all `location.hash`), so the
     hash form is the only one that arrives carrying a name. */
  function dossierHref(t) { return 'stock.html#' + encodeURIComponent(t); }

  /* The drawer is where the 390px demotions live (Day, Since entry, Risk share,
     Sector) AND where the per-name detail appears. Its honesty rule: when a lane the
     drawer would normally show cannot be read, the drawer SAYS SO on its own line —
     it never renders a shorter drawer and lets the reader assume there was nothing to
     say. An absent lane and a quiet lane look identical otherwise, and only one of
     them is information. */
  function drawerBody(r) {
    var t = r.ticker, j = jsonCache[t], out = '';
    var b = marketOf(t), v = rowValue(r);

    // the demoted columns, restated in full
    out += '<div class="drw">';
    out += '<div><span class="k">' + te('Day', '当日') + '</span>' + WS().dayCell() + '</div>';
    var entryP = num(r.entry_price), cur = priceOf(t);
    out += '<div><span class="k">' + te('Since entry', '持有以来') + '</span>' +
      (entryP != null && entryP !== 0 && cur != null
        ? '<span class="fig ' + (cur >= entryP ? 'pos' : 'neg') + '">' +
          ((cur - entryP) / entryP * 100 >= 0 ? '+' : '') +
          ((cur - entryP) / entryP * 100).toFixed(1) + '%</span>'
        : WS().dash('No entry price saved for this position, so there is nothing to measure from.',
                    '这笔持仓没有保存买入价，因此没有基准可比。')) + '</div>';
    var share = RISK_SHARES[t];
    out += '<div><span class="k">' + te('Risk share', '风险占比') + '</span>' +
      (isNum(share)
        ? '<span class="fig">' + Math.round(Math.abs(share) * 100) + '%</span>'
        : WS().dash('Not covered by the risk model, so there is no share to give.',
                    '不在风险模型覆盖范围内，因此没有占比可给。')) + '</div>';
    if (v.value != null) {
      out += '<div><span class="k">' + te('Position value', '仓位市值') + '</span><span class="fig">' +
        esc(fmtMoney(v.value, b)) + '</span>' +
        (v.atCost ? ' <span class="mut">' + te('at cost', '按成本') + '</span>' : '') + '</div>';
    }
    out += '</div>';

    if (!window.WRI || !window.WRI.intelSections) {
      /* The gated intelligence layer is not on the page — which here can only mean the
         bundle failed, never that the visitor is anonymous. `render()` returns early on
         every `anon*` state, so this file NEVER paints a drawer for a signed-out
         visitor; that path belongs to watchlist.js, which draws the lock shell. This
         branch used to carry a lock shell of its own for the anonymous case, and it was
         unreachable code telling an audience it could not have that they needed a free
         account they already had. */
      out += '<div class="drw-honest">' + te(
        'The detail layer for this name did not load. That is a gap in what we can show you, not a clean bill of health.',
        '这只票的详情层没有加载出来。这是我们能展示的内容缺了一块，不代表它没问题。') + '</div>';
    } else if (j === null || j === undefined) {
      /* Truly uncovered, or not read yet — either way we have no lanes. One honest
         line, never an empty drawer that reads as "all clear". */
      out += '<div class="drw-honest">' + (j === null
        ? te(esc(T.en.notInLibrary), esc(T.zh.notInLibrary))
        : te('Reading this name&rsquo;s detail…', '正在读取该股详情…')) + '</div>';
    } else {
      // ---- Tier 1: the instant read, in plain words ----------------------
      try { out += window.WRI.intelTier1(t, j) || ''; } catch (e) {
        out += '<div class="drw-honest">' + te(esc(T.en.noEntryRead), esc(T.zh.noEntryRead)) + '</div>';
      }

      var stg = ctxStage(t);
      if (stg) {
        var wEn = isNum(stg.weeks) ? ' · ' + Math.round(stg.weeks) + ' wks in' : '';
        var wZh = isNum(stg.weeks) ? ' · 已' + Math.round(stg.weeks) + '周' : '';
        out += lrow(T.en.lblStage, T.zh.lblStage, '', '', stg.drawEn + wEn, stg.drawZh + wZh);
      } else if (isModeled(t) && ctxTried && !ctxMap) {
        // the lane exists but its source did not answer — say it, do not just omit
        out += '<div class="drw-honest">' + te(
          'The stage read for this name is not available right now. Nothing else on this row depends on it.',
          '这只票的阶段判断暂时读不到。本行其余内容不依赖它。') + '</div>';
      }

      /* The distance-from-trend row moved into the shared composer (WRI.intelSections),
         so the holdings drawer and the watchlist drawer now render it identically. It
         used to live here, which meant one name read differently depending on which mode
         you opened it from. `extGradeOf` stays — the attention stack still uses it. */

      /* ---- Tier 2: every section, from the ONE composer ------------------
         The weight is this position's value over its OWN market book's total — the
         same denominator the row's weight cell uses, and never a cross-currency one.
         One failed section cannot empty the drawer: the composer is a string builder,
         so a throw here loses Tier 2 and says so, and Tier 1 above is already painted. */
      var wPct = null;
      if (v.value != null) {
        var bt = bookValueTotals(openRows())[b];
        if (bt && bt.value > 0) wPct = v.value / bt.value * 100;
      }
      var sections = '';
      try {
        sections = window.WRI.intelSections(t, j, { inBook: true, weightPct: wPct }) || '';
      } catch (e) { sections = ''; }
      if (sections) out += sections;
      else out += '<div class="drw-honest">' + te(
        'The per-lane checks for this name did not load. That is a gap in what we can show you, not a clean bill of health.',
        '这只票的各项检查没有加载出来。这是我们能展示的内容缺了一块，不代表它没问题。') + '</div>';

      if (j.asof) {
        out += '<div class="asof mut" style="font-size:11px;margin-top:7px">' +
          te('signals as of ' + esc(j.asof), '信号截至 ' + esc(j.asof)) + '</div>';
      }
    }

    out += '<div class="drw-act">' +
      '<a href="' + esc(dossierHref(t)) + '">' + te(T.en.dossier, T.zh.dossier) + '</a>' +
      '<a href="' + esc(terminalHref(t)) + '" target="_blank" rel="noopener noreferrer">' +
        te(T.en.terminal, T.zh.terminal) + '</a>' +
      '<button class="drw-rm" type="button" data-edit="' + esc(String(r.id)) + '">' +
        te(T.en.editBtn, T.zh.editBtn) + '</button>' +
      '<button class="drw-rm" type="button" data-rm-pos="' + esc(String(r.id)) + '">' +
        te(T.en.removeBtn, T.zh.removeBtn) + '</button></div>';
    return out;
  }

  // =========================================================================
  //  The dense holdings table
  // =========================================================================
  function WS() { return window.WS || {}; }
  var RISK_SHARES = {};    // ticker -> |mctr share| (0..1), published by watchlist_risk.js
  var RISK_COVERED = {};   // ticker -> true when the factor model covers it

  function bookValueTotals(list) {
    // {book -> {value, priced}} over the given rows; per book, never across books
    var out = {};
    list.forEach(function (r) {
      var b = marketOf(r.ticker), v = rowValue(r);
      var e = out[b] || (out[b] = { value: 0, priced: 0, n: 0, atCost: false });
      e.n++;
      if (v.value != null) { e.value += v.value; if (v.atCost) e.atCost = true; else e.priced++; }
    });
    return out;
  }

  var HEAD =
    '<thead><tr>' +
      '<th class="srt" data-sort="sym">' + te('Symbol', '代码') + '<span class="ar">▴</span></th>' +
      '<th class="num srt" data-sort="value">' + te('Value / weight', '市值 / 占比') + '<span class="ar">▴</span></th>' +
      '<th class="num">' + te('Day', '当日') + '</th>' +
      '<th class="num srt" data-sort="since">' + te('Since entry', '持有以来') + '<span class="ar">▴</span></th>' +
      '<th>' + te('Signal', '信号阶段') + '</th>' +
      '<th class="num srt" data-sort="risk">' + te('Risk share', '风险占比') + '<span class="ar">▴</span></th>' +
      '<th>' + te('Attention', '留意') + '</th>' +
      '<th>' + te('Next event', '下一个事件') + '</th>' +
      '<th></th>' +
    '</tr></thead>';

  function holdRowHTML(r, totals) {
    var t = r.ticker || '', b = marketOf(t);
    var v = rowValue(r), tot = totals[b];
    var uncovered = !RISK_COVERED[t];

    var valHtml;
    if (v.value != null) {
      valHtml = '<span class="fig">' + esc(fmtMoney(v.value, b)) + '</span>';
      if (tot && tot.value > 0) {
        valHtml += '<span class="w fig">' + (v.value / tot.value * 100).toFixed(1) + '%' +
          (v.atCost ? ' ' + te('at cost', '按成本') : '') + '</span>';
      }
    } else {
      valHtml = WS().dash('This position has no share count saved, so there is no value to show.',
                          '这笔持仓没有保存股数，因此没有市值可显示。');
    }

    var entryP = num(r.entry_price), cur = priceOf(t), sinceHtml;
    if (entryP != null && entryP !== 0 && cur != null) {
      var pct = (cur - entryP) / entryP * 100;
      sinceHtml = '<span class="fig ' + (pct >= 0 ? 'pos' : 'neg') + '">' +
        (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%</span>';
    } else {
      sinceHtml = WS().dash('No entry price saved for this position, so there is nothing to measure from.',
                            '这笔持仓没有保存买入价，因此没有基准可比。');
    }

    /* Risk share on ONE shared scale: the bar is full at 30% of book risk and the
       printed number is the truth. No per-row rescaling, no fake magnitude. A name
       the model does not cover gets "—" and is left out of the denominator. */
    var share = RISK_SHARES[t];
    var rcHtml;
    if (uncovered || !isNum(share)) {
      rcHtml = WS().dash('Not covered by the risk model, so there is no share to give.',
                         '不在风险模型覆盖范围内，因此没有占比可给。');
    } else {
      var p = Math.round(Math.abs(share) * 100);
      rcHtml = '<span class="rc' + (p >= 13 ? ' is-big' : '') + '"><span class="bar"><span style="width:' +
        Math.min(100, Math.abs(share) * 100 / 30 * 100).toFixed(0) + '%"></span></span>' +
        '<span class="fig">' + p + '%</span></span>';
    }

    var j = jsonCache[t];
    var st = tickerSt(t);
    var sig = WS().stageCell ? WS().stageCell(WS().stageOf(st)) : '';
    var att = attentionFlag(r, j);
    var evt = eventCell(j);

    var isOpen = !!openDrawers[r.id];
    return '<tr class="pfx-row' + (uncovered ? ' is-uncovered' : '') + '" data-t="' + esc(t) +
      '" data-row="' + esc(String(r.id)) + '" tabindex="0" aria-expanded="' + (isOpen ? 'true' : 'false') + '">' +
      '<td class="c-sym"><b>' + esc(t) + '</b><span class="co">' + esc(tickerName(t)) + '</span></td>' +
      '<td class="c-val num">' + valHtml + '</td>' +
      '<td class="c-day num">' + WS().dayCell() + '</td>' +
      '<td class="c-since num">' + sinceHtml + '</td>' +
      '<td class="c-sig">' + sig + '</td>' +
      '<td class="c-rc num">' + rcHtml + '</td>' +
      '<td class="c-att">' + (att ? '<span class="flag ' + att[0] + '">' + te(att[1], att[2]) + '</span>'
                                  : '<span class="dash">—</span>') + '</td>' +
      '<td class="c-evt">' + evt + '</td>' +
      '<td class="c-exp"><button class="exp" type="button" data-row-exp="' + esc(String(r.id)) +
        '" aria-expanded="' + (isOpen ? 'true' : 'false') + '" aria-label="' +
        (isZh() ? '详情' : 'Details') + '"><span class="car">⌄</span></button></td>' +
      '</tr>' +
      (isOpen ? '<tr class="row-drawer" data-drawer="' + esc(String(r.id)) + '"><td colspan="9">' +
        drawerBody(r) + '</td></tr>' : '');
  }

  /* WHICH oracle produced a name's stretch grade — 'ext' | 'alignment' | null.

     `extGradeOf` answers in ONE vocabulary drawn from TWO sources that do not measure
     the same thing. US-store names carry `ext`, whose number is literally
     price/SMA200 − 1, z-scored against the name's own trailing year
     (engine/extension.py) — a distance-above-the-200-day read, always. Every other
     market falls back to `ladder.alignment.overextended`, which is a first-true-wins OR
     of three legs (engine/cycles.py `_overextended`): 3-day or daily StochRSI > 80,
     daily RSI14 > 62, or +30% over the 200-day. Only the third leg is a distance read,
     and it is by far the hardest to trip — a name at RSI 63 sitting 2% above its
     200-day line comes back `true` on the first leg it tests. So `true` here does not
     imply a statement about distance, and most of the time is not one.

     The distinction is load-bearing only where the COPY makes a claim about how the
     read was taken: a line that says "elevated" is honest either way, a line that says
     "measured against its own 200-day path" is honest only for 'ext'. Gate on this,
     not on the grade word, wherever the sentence promises the method. */
  function stretchBasis(t, j) {
    if (isModeled(t) && j && j.ext && j.ext.grade) return 'ext';
    var al = j && j.ladder && j.ladder.alignment;
    if (al && al.overextended === true) return 'alignment';
    return null;
  }

  /* The attention flag on a row is the SAME rule the attention stack sorts by, read
     for one name. Precedence is fixed and stated; there is no score anywhere. */
  function attentionFlag(r, j) {
    var t = r.ticker;
    var share = RISK_SHARES[t];
    var days = eventDays(j);
    if (isNum(share) && Math.abs(share) >= 0.20) return ['f-warn', 'Biggest risk share', '风险占比最大'];
    if (days != null && days >= 0 && days <= 5) return ['f-warn', 'Event window', '关键窗口'];
    /* `extGradeOf` speaks the engine's vocabulary (engine/extension.py GRADES:
       intrend / steady / stretched / parabolic / na) and has never returned anything
       else. This branch shipped comparing it against 'high' / 'extreme' — words no
       extension oracle in this repo produces — so from #5496 until now the flag was
       structurally unreachable and this column simply never said "stretched" about
       anything. The zh word is the one the chip lane already uses (过度拉伸, see
       `stretchOf`), NOT the 偏离过大 an earlier draft used: the flag takes
       either oracle (see `stretchBasis` above) and only one of those always measures
       distance, so a 偏离 (deviation) word here would make a claim the alignment path
       cannot carry. One word, one column, and it must be true both ways.
       Elevated is named once (`isElevatedGrade`); the two caution grades then split
       their copy so parabolic is not silently folded into "Stretched". */
    var g = extGradeOf(t, j);
    if (isElevatedGrade(g) && g === 'parabolic') return ['f-warn', 'Parabolic', '抛物线拉伸'];
    if (isElevatedGrade(g) && g === 'stretched') return ['f-warn', 'Stretched', '过度拉伸'];
    if (!RISK_COVERED[t] && isModeled(t) === false) return ['f-info', 'Outside risk model', '不在风险模型内'];
    return null;
  }
  function eventDays(j) {
    var d = j && j.earnings && j.earnings.next_date;
    if (!d) return null;
    var m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return Math.round((Date.UTC(+m[1], +m[2] - 1, +m[3]) - Date.now()) / 86400000);
  }
  var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function eventCell(j) {
    var d = j && j.earnings && j.earnings.next_date;
    if (!d) return '<span class="dash">—</span>';
    var m = String(d).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return '<span class="dash">—</span>';
    var dt = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    var days = eventDays(j);
    // the ZH date deliberately drops .fig — "8月27日" contains WORDS, and mono
    // numerals are for figures, never for words
    return '<span class="evt">' + te('Earnings', '财报') +
      ' <b class="fig l-en">' + MON[dt.getUTCMonth()] + ' ' + dt.getUTCDate() + '</b>' +
      '<b class="l-zh">' + (dt.getUTCMonth() + 1) + '月' + dt.getUTCDate() + '日</b>' +
      (days != null && days >= 0 && days <= 5
        ? ' <span class="soon">' + te('in ' + days + (days === 1 ? ' day' : ' days'), '还有 ' + days + ' 天') + '</span>'
        : '') + '</span>';
  }

  var sortKey = 'value', sortDir = -1;
  function sortRows(list, totals) {
    var d = sortDir;
    return list.slice().sort(function (a, b) {
      var r = 0;
      if (sortKey === 'sym') r = (a.ticker || '').localeCompare(b.ticker || '');
      else if (sortKey === 'risk') r = (RISK_SHARES[a.ticker] || 0) - (RISK_SHARES[b.ticker] || 0);
      else if (sortKey === 'since') r = sincePct(a) - sincePct(b);
      else r = (rowValue(a).value || 0) - (rowValue(b).value || 0);
      return (r || (a.ticker || '').localeCompare(b.ticker || '')) * d;
    });
  }
  function sincePct(r) {
    var e = num(r.entry_price), c = priceOf(r.ticker);
    return (e != null && e !== 0 && c != null) ? (c - e) / e * 100 : -1e9;
  }

  function renderTable() {
    var host = el('tbl_pf');
    if (!host) return;
    var open = openRows();
    var book = activeBook();
    var shown = book === 'all' ? open : open.filter(function (r) { return marketOf(r.ticker) === book; });
    var q = (el('pf_q') && el('pf_q').value || '').trim().toLowerCase();
    if (q) shown = shown.filter(function (r) {
      return (r.ticker || '').toLowerCase().indexOf(q) >= 0 ||
             (tickerName(r.ticker) || '').toLowerCase().indexOf(q) >= 0;
    });
    var totals = bookValueTotals(open);

    if (!open.length) {
      host.innerHTML = '<tbody><tr><td><div class="tbl-empty">' + te(
        'No positions yet. Add your first with the button above, or paste a book on the Portfolio tab.',
        '还没有持仓。用上方的按钮添加第一笔，或在「持仓」页贴入一份账簿。') + '</div></td></tr></tbody>';
    } else if (!shown.length) {
      host.innerHTML = '<tbody><tr><td><div class="tbl-empty">' + te(
        'No positions in this book yet.', '这个市场里还没有持仓。') + '</div></td></tr></tbody>';
    } else {
      host.innerHTML = HEAD + '<tbody>' +
        sortRows(shown, totals).map(function (r) { return holdRowHTML(r, totals); }).join('') + '</tbody>';
    }

    // the disclosure line — ALWAYS rendered, so a persisted book filter can never
    // silently shorten the list (packet §11)
    var scope = el('pf_scope');
    if (scope && WS().scopeLine) scope.innerHTML = WS().scopeLine(shown.length, open.length);
    var rc = el('pf_rowcount');
    if (rc) rc.innerHTML = te(shown.length + (shown.length === 1 ? ' row' : ' rows'), shown.length + ' 行');
  }

  // =========================================================================
  //  BOOK READ — the plain-language sentence the Book Seam is evidence for
  // =========================================================================
  var BOOK = null;   // published by watchlist_risk.js: {bets, cluster, coverage, ...}

  function renderBookRead() {
    var open = openRows();
    var totals = bookValueTotals(open);
    var say = el('ws_book_say'), because = el('ws_book_because'),
        meta = el('ws_book_meta'), stance = el('ws_book_stance'),
        cov = el('ws_book_coverage'), sub = el('ws_book_sub');
    if (!say) return;

    /* A1A (§13, defect "zero/one collapse"): 0 and 1 open positions used to share ONE
       message ("Add a SECOND position…", which presupposes a first). They are now two
       distinct states. Neither shows a relationship/cluster read — there is nothing to
       relate a single position to. */
    if (open.length === 0) {
      if (meta) meta.innerHTML = '';
      say.innerHTML = te(T.en.emptyBookSay, T.zh.emptyBookSay);
      if (because) because.innerHTML = '';
      if (stance) stance.innerHTML = '';
      if (cov) cov.innerHTML = '';
      if (WS().seam) WS().seam(el('ws_seam'), null);
      return;
    }
    if (open.length === 1) {
      var only = open[0];
      if (meta) meta.innerHTML = '<span>' + te('1 position', '1 只持仓') + '</span>';
      say.innerHTML = te(T.en.onePosSay, T.zh.onePosSay) + ' — <b>' + esc(only.ticker) + '</b>.';
      if (because) because.innerHTML = te(T.en.onePosBecause, T.zh.onePosBecause);
      if (stance) stance.innerHTML = '';
      if (cov) cov.innerHTML = '';
      if (WS().seam) WS().seam(el('ws_seam'), null);
      return;
    }

    // money shares within the DOMINANT book only — we never add two currencies
    var byBook = {};
    open.forEach(function (r) { byBook[marketOf(r.ticker)] = (byBook[marketOf(r.ticker)] || 0) + 1; });
    var lead = Object.keys(byBook).sort(function (a, b) { return byBook[b] - byBook[a]; })[0] || 'us';
    var leadTot = totals[lead] ? totals[lead].value : 0;
    var leadRows = open.filter(function (r) { return marketOf(r.ticker) === lead; });

    /* A1A weighting law (§12): the distribution below must come from ONE basis — never
       an actual proportional value blended with an equal-split fallback for the rows
       that had none (defect "hidden weighting completion"). A book too thin to have
       exactly one basis (mixed sized/unsized, or mixed live/cost pricing) ABSTAINS —
       it shows no money bars rather than a fabricated one. */
    var ps = PS();
    var W;
    if (ps) {
      /* F5 (Sol post-review, MAJOR — real snapshot consumption): a single-currency
         book (the common case, `byBook` has exactly one key) reads the ONE
         snapshot's own `weighting` field directly — computeSnapshot() computes it
         over the exact same `open` rows this function already partitions into
         `leadRows` whenever there is only one book, so the two calls would be
         identical; re-deriving a second time is exactly the "3-field pass-through"
         the review named. A MULTI-currency book keeps the DIRECT per-book call
         (§12 currency-partition law, carve-out) — the snapshot's own weighting is
         `cross_currency_partitioned` (a stub, `complete:false`) precisely because
         it spans books, and blending across currencies is the one thing §12
         forbids; only a call scoped to `leadRows` alone answers honestly there. */
      var singleBookSnap = Object.keys(byBook).length === 1 ? refreshSnapshot() : null;
      W = (singleBookSnap && singleBookSnap.weighting)
        ? singleBookSnap.weighting
        : ps.computeWeighting(leadRows, priceOf);
    } else {
      /* B2 (review — split-deploy falsehood): portfolio_state.js is a NEW paired
         script; the .j2 markup that references it goes live within minutes, but
         `site/watchlist.html` itself re-bakes far slower (measured "over an hour" —
         see watchlist.js's own LEGACY RENDER PATH comment). In that window `ps` is
         null on every page — not just a mixed book. The old shape here (`!W ||
         W.complete !== true`) printed the ABSTAIN copy for every book whenever PS was
         merely absent, including a fully sized, fully live-priced one — a false
         "weights not shown" over a book that had a perfectly good answer. PS's
         ABSENCE must never make a weighting-law claim: only the one case computable
         without it (every row sized AND live-priced) gets real numbers, with no
         basis label; anything else is a silent minimal state — no abstain copy, no
         equal-assumption label, no claim this module is not ready to make. */
      var allCurrent = leadRows.length > 0 && leadRows.every(function (r) {
        var sh = num(r.shares), px = priceOf(r.ticker);
        return sh != null && sh > 0 && px != null && px > 0;
      });
      if (!allCurrent) {
        if (meta) meta.innerHTML = '<span>' + te(open.length + (open.length === 1 ? ' position' : ' positions'),
                                                   open.length + ' 只持仓') + '</span>';
        say.innerHTML = te('This book holds ' + open.length + (open.length === 1 ? ' position.' : ' positions.'),
                            '这本账簿共有 ' + open.length + ' 笔持仓。');
        if (because) because.innerHTML = '';
        if (stance) stance.innerHTML = '';
        if (cov) cov.innerHTML = '';
        if (WS().seam) WS().seam(el('ws_seam'), null);
        return;
      }
      var psSum = 0, psVal = {};
      leadRows.forEach(function (r) { var v = num(r.shares) * priceOf(r.ticker); psVal[r.ticker] = v; psSum += v; });
      var psWeights = {};
      leadRows.forEach(function (r) {
        psWeights[r.ticker] = psSum > 0 ? (psVal[r.ticker] / psSum * 100) : (100 / leadRows.length);
      });
      W = { state: 'all_sized_current', weights: psWeights, basis: 'current_value',
            complete: true, reason: null };
    }
    if (!W || W.complete !== true) {
      if (meta) meta.innerHTML = '<span>' + te(open.length + ' positions', open.length + ' 只持仓') + '</span>';
      /* M-a (review): `unresolved_basis` (a SIZED row with neither a live price nor
         an entry price) is not "mixed sized/unsized" — every row in that book DID
         carry a size. Routing it through the mixed-sizing copy said something false.
         It gets its own sentence naming the real reason: no resolvable price. */
      var abstainMsg = T.en.mixedAbstain, abstainMsgZh = T.zh.mixedAbstain;
      if (W && W.reason === 'mixed_price_basis') { abstainMsg = T.en.mixedBasisAbstain; abstainMsgZh = T.zh.mixedBasisAbstain; }
      else if (W && W.reason === 'unresolved_basis') { abstainMsg = T.en.unresolvedBasisAbstain; abstainMsgZh = T.zh.unresolvedBasisAbstain; }
      /* A 1-US + 1-HK all-sized book (core audience) reaches this block via the
         lead-book restriction: leadRows.length===1 → 'insufficient'/'single_position'.
         The generic mixed-sizing sentence is FALSE for it — every position carries a
         size. Name the real reason instead ('no_positions' defensively: same copy). */
      else if (W && (W.reason === 'single_position' || W.reason === 'no_positions')) { abstainMsg = T.en.singlePositionBook; abstainMsgZh = T.zh.singlePositionBook; }
      say.innerHTML = te(abstainMsg, abstainMsgZh);
      if (because) because.innerHTML = '';
      if (stance) stance.innerHTML = '';
      if (cov) cov.innerHTML = '';
      if (WS().seam) WS().seam(el('ws_seam'), null);
      return;
    }

    var items = leadRows.map(function (r) {
      return {
        sym: r.ticker,
        money: (W.weights[r.ticker] != null) ? W.weights[r.ticker] : 0,
        risk: RISK_COVERED[r.ticker] && isNum(RISK_SHARES[r.ticker])
                ? Math.abs(RISK_SHARES[r.ticker]) * 100 : null,
        role: ''
      };
    }).sort(function (a, b) { return b.money - a.money; });

    // A1A (defect "fabricated cluster"): no source cluster means no cluster role,
    // bracket, coloring or explanatory caption — never a top-half-by-money invention.
    var clusterSet = (BOOK && BOOK.cluster) || null;
    if (clusterSet) {
      items.forEach(function (x) {
        x.role = clusterSet[x.sym] ? 'cluster' : (BOOK.ballast && BOOK.ballast[x.sym] ? 'ballast' : '');
      });
    }

    var nUncovered = items.filter(function (x) { return x.risk == null; }).length;

    if (meta) {
      var parts = ['<span>' + te(open.length + (open.length === 1 ? ' position' : ' positions'),
                                 open.length + ' 只持仓') + '</span>'];
      if (leadTot > 0) {
        parts.push('<span class="sep">·</span><span class="fig">' + esc(fmtMoney(leadTot, lead)) + '</span>' +
          '<span>' + te('tracked', '在管') + '</span>');
      }
      // the weighting basis is disclosed whenever it is not the unlabeled default
      // (real current-value weights need no caveat; an assumption always does)
      if (W.state === 'all_unsized_equal') {
        parts.push('<span class="sep">·</span><span>' + te(T.en.equalAssumed, T.zh.equalAssumed) + '</span>');
      } else if (W.state === 'all_sized_cost') {
        parts.push('<span class="sep">·</span><span>' + te(T.en.costWeighted, T.zh.costWeighted) + '</span>');
      }
      meta.innerHTML = parts.join('');
    }
    if (sub) sub.innerHTML = (BOOK && BOOK.regime) ? BOOK.regime : '';

    /* "moves like about K bets" is FACTOR OUTPUT — it is printed only when the model
       actually produced it, and it names the MODELED subset rather than the user's
       list size whenever those differ. A book whose model read is missing gets the
       money-only sentence, never a bet count we did not compute. */
    if (BOOK && isNum(BOOK.bets) && BOOK.modeledN >= 2) {
      var n = BOOK.modeledN, all = open.length;
      say.innerHTML = (n === all)
        ? te('These <span class="fig">' + all + '</span> positions move like about <span class="fig">' +
             BOOK.bets + '</span> bets.',
             '<span class="fig">' + all + '</span> 只持仓，实际只相当于大约 <span class="fig">' +
             BOOK.bets + '</span> 个方向。')
        : te('The <span class="fig">' + n + '</span> positions our model covers move like about <span class="fig">' +
             BOOK.bets + '</span> bets.',
             '模型覆盖的这 <span class="fig">' + n + '</span> 只持仓，实际只相当于大约 <span class="fig">' +
             BOOK.bets + '</span> 个方向。');
    } else {
      var topShare = 0, topN = Math.max(1, Math.min(3, Math.ceil(items.length / 4)));
      items.slice(0, topN).forEach(function (x) { topShare += x.money; });
      say.innerHTML = te(
        'Most of this book — <span class="fig">' + Math.round(topShare) + '%</span> of the money — sits in <span class="fig">' +
          topN + '</span> ' + (topN === 1 ? 'position' : 'positions') + '.',
        '这本账簿的大部分 —— <span class="fig">' + Math.round(topShare) + '%</span> 的资金 —— 压在 <span class="fig">' +
          topN + '</span> 只持仓上。');
    }
    if (because) because.innerHTML = (BOOK && BOOK.because) ? BOOK.because : te(
      'The biggest weights are <b>' + esc(items.slice(0, 3).map(function (x) { return x.sym; }).join(' · ')) + '</b>.',
      '权重最大的是 <b>' + esc(items.slice(0, 3).map(function (x) { return x.sym; }).join(' · ')) + '</b>。');

    // Stance vocabulary on portfolio surfaces is DESCRIPTIVE ONLY (DESIGN_NOTES §7b):
    // Watch · Get ready · No action, plus this plain line when the answer is nothing.
    /* Descriptive only (DESIGN_NOTES §7b). "Worth a look" is claimed ONLY when a row
       actually carries Watch or Get ready — a stack of five No-action rows means the
       honest answer is still nothing, and Law 1 is satisfied by saying so. */
    if (stance) {
      var live = attentionStack().some(function (x) { return !!x.stance; });
      stance.innerHTML = live
        ? te('A few names are worth a look today.', '今天有几只票值得看一眼。')
        : te('Nothing here needs a decision today.', '今天没有需要决定的事。');
    }

    /* The caption's two figures come from the SAME distribution the two rails draw:
       the cluster's share of THIS money and of THIS modeled risk. Any other
       denominator produces a sentence that contradicts the bracket directly above it. */
    var moneyAll = 0, riskAll = 0, moneyCl = 0, riskCl = 0, nCl = 0;
    items.forEach(function (x) {
      moneyAll += x.money;
      if (x.risk != null) riskAll += x.risk;
      if (x.role === 'cluster') {
        nCl++; moneyCl += x.money;
        if (x.risk != null) riskCl += x.risk;
      }
    });
    var cap = '';
    if (nCl >= 2 && moneyAll > 0 && riskAll > 0) {
      var mp = Math.round(moneyCl / moneyAll * 100), rp = Math.round(riskCl / riskAll * 100);
      cap = te(
        nCl + ' names hold <b>' + mp + '% of the money</b> and <b>' + rp + '% of the risk</b>. ' +
          'That gap is the difference between how this book is sized and how it actually moves.',
        nCl + ' 只票占了 <b>' + mp + '% 的资金</b>，却占了 <b>' + rp + '% 的风险</b>。' +
          '这个差，就是「你怎么配的」和「它实际怎么动」之间的距离。');
    }
    if (WS().seam) {
      WS().seam(el('ws_seam'), {
        items: items,
        lockedRisk: !items.some(function (x) { return x.risk != null; }),
        cap: cap
      });
    }
    /* Two disclosures, and they must not blur into one. The seam draws ONE currency —
       adding two would be the law this page states in its own toolbar — so when the
       book spans markets the rails describe the LEAD book and the line says which.
       The coverage count is then over exactly the set the rails drew, never over the
       whole book, or the sentence contradicts the shape directly above it. */
    if (cov) {
      var lines = [];
      if (Object.keys(byBook).length > 1) {
        lines.push(te(
          'The two lines above read your <b>' + esc(bookName(lead)) + '</b> book — ' +
            items.length + ' of ' + open.length + ' positions. Each book totals in its own currency, ' +
            'so we never draw two of them on one line.',
          '上面两条读的是你的 <b>' + esc(bookNameZh(lead)) + '</b> 账本 —— ' + open.length +
            ' 只持仓中的 ' + items.length + ' 只。每个市场各自计价，因此我们不会把两个市场画在同一条线上。'));
      }
      if (nUncovered) {
        lines.push(te(
          '<b>' + nUncovered + ' of ' + (lines.length ? 'them' : 'your ' + items.length + ' positions') + ' ' +
            (nUncovered === 1 ? 'sits' : 'sit') + ' outside the risk model.</b> ' +
            (nUncovered === 1 ? 'It is' : 'They are') +
            ' shown on the money line above and in the table below, and left out of every risk figure — never quietly folded in.',
          '<b>其中有 ' + nUncovered + ' 只不在风险模型内。</b>' +
            '它们照常出现在上方的资金分布和下方的表格里，但不计入任何风险数字 —— 不会被悄悄算进去。'));
      }
      cov.innerHTML = lines.length
        ? '<span class="mark"></span><span>' + lines.join(' ') + '</span>' : '';
    }
  }

  // =========================================================================
  //  WHAT NEEDS ATTENTION — a fixed precedence, printed. Never a score.
  // =========================================================================
  /* The order is a RULE, in this order, and the hover on each row names which rule
     put it there:
       1  large risk contribution AND its own checks turned elevated
       2  an event inside its critical window
       3  an elevated check on a position large enough to matter
       4  a major status transition
       5  context — the names holding the book apart from its dominant idea
     At most five rows; the section header discloses "5 of N positions". */
  function attentionStack() {
    var open = openRows();
    if (!open.length) return [];
    var out = [], used = {};
    function push(r, rule, whatEn, whatZh, stance, tipEn, tipZh) {
      if (used[r.ticker] || out.length >= 5) return;
      used[r.ticker] = 1;
      out.push({ sym: r.ticker, rule: rule, en: whatEn, zh: whatZh,
                 stance: stance, tipEn: tipEn, tipZh: tipZh });
    }
    var byRisk = open.slice().sort(function (a, b) {
      return (RISK_SHARES[b.ticker] || 0) - (RISK_SHARES[a.ticker] || 0);
    });

    // rule 1
    byRisk.forEach(function (r) {
      var s = RISK_SHARES[r.ticker];
      if (!isNum(s) || s < 0.18) return;
      /* Elevated = the engine's two caution grades. Rule 1's copy says only "its
         checks turned elevated", which BOTH oracles behind `extGradeOf` can back, so
         this rule takes either one (rule 3 below is the one that cannot). */
      var g = extGradeOf(r.ticker, jsonCache[r.ticker]);
      if (!isElevatedGrade(g)) return;
      push(r, 1, 'Your largest risk share, and its checks turned elevated.',
           '它占你账簿的风险最大，指标也转为偏高。', 's-watch',
           'Rule 1 — largest share of book risk, and its own checks are elevated. Source: last night&#39;s close.',
           '规则 1 —— 占本账簿风险最大，且其自身指标偏高。来源：昨夜收盘数据。');
    });
    // rule 2
    open.forEach(function (r) {
      var d = eventDays(jsonCache[r.ticker]);
      if (d == null || d < 0 || d > 5) return;
      push(r, 2, 'Reports in ' + d + (d === 1 ? ' day' : ' days') + '.',
           d + ' 天后发财报。', 's-ready',
           'Rule 2 — an event inside its critical window.',
           '规则 2 —— 事件进入关键窗口。');
    });
    // rule 3
    byRisk.forEach(function (r) {
      var j3 = jsonCache[r.ticker];
      var g = extGradeOf(r.ticker, j3);
      if (!isElevatedGrade(g)) return;
      /* This rule's hover NAMES its method — "measured against its own 200-day path".
         Only the `ext` oracle takes the read that way, so an alignment-sourced grade
         may not raise THIS rule: it would print a sentence about a 200-day distance
         over a number that is not one. Such a name is not silently dropped from the
         desk — rule 1 above still speaks for it in the words both oracles support. */
      if (stretchBasis(r.ticker, j3) !== 'ext') return;
      var s = RISK_SHARES[r.ticker];
      if (!isNum(s) || s < 0.08) return;
      push(r, 3, 'Sitting far above its own trend after a long run up.',
           '在一轮长涨之后，已经远离自己的趋势线。', 's-watch',
           'Rule 3 — an elevated check on a position large enough to matter. Stretch is measured against its own 200-day path.',
           '规则 3 —— 一只体量足够大的持仓出现偏高指标。偏离度以其自身 200 日均线路径为基准。');
    });
    /* Rule 4 takes at most ONE row. Five names that all changed stage this week is a
       true statement and a useless stack — the reader learns nothing from the fifth
       identical sentence. The freshest transition stands for the rest. */
    var fresh = open.filter(function (r) {
      var stg = ctxStage(r.ticker);
      return stg && isNum(stg.weeks) && stg.weeks <= 2 && !used[r.ticker];
    }).sort(function (a, b) { return ctxStage(a.ticker).weeks - ctxStage(b.ticker).weeks; })[0];
    if (fresh) {
      push(fresh, 4, 'Changed status recently, after months in one place.',
           '在长期横盘之后，最近状态发生了变化。', '',
           'Rule 4 — a major status transition. This is the most recent one on your book.',
           '规则 4 —— 重要状态变化。这是你账簿上最近的一次。');
    }
    // rule 5 — context
    if (out.length < 5 && BOOK && BOOK.ballast) {
      var ball = Object.keys(BOOK.ballast).filter(function (t) { return !used[t]; });
      if (ball.length) {
        out.push({ sym: ball.slice(0, 2).join(' · '), rule: 5,
          en: 'The names holding this book apart from its dominant idea.',
          zh: '是这几只把整本账簿和主线拉开了距离。', stance: '',
          tipEn: 'Rule 5 — context. These are the reason the book is not a single position.',
          tipZh: '规则 5 —— 背景信息。正是它们让这本账簿没有变成一笔仓位。' });
      }
    }
    return out;
  }

  var STANCE = { 's-watch': ['Watch', '留意'], 's-ready': ['Get ready', '做好准备'],
                 '': ['No action', '暂不需要动作'] };
  function renderAttention() {
    var host = el('ws_att'); if (!host) return;
    var sec = el('ws_sec_att');
    var stack = attentionStack();
    var open = openRows();
    if (!stack.length) {
      if (sec) sec.style.display = open.length ? '' : 'none';
      host.innerHTML = '<div class="att-row"><span class="att-sym"></span>' +
        '<span class="att-what">' + te(
          'Nothing on this book crossed a line overnight.', '昨夜这本账簿没有出现越线。') + '</span>' +
        '<span class="att-stance">' + te('No action', '暂不需要动作') + '</span><span class="att-chev"></span></div>';
    } else {
      if (sec) sec.style.display = '';
      host.innerHTML = stack.map(function (x) {
        var s = STANCE[x.stance] || STANCE[''];
        return '<div class="att-row" data-t="' + esc(x.sym) + '" data-tip-en="' + esc(x.tipEn) +
          '" data-tip-zh="' + esc(x.tipZh) + '">' +
          '<span class="att-sym">' + esc(x.sym) + '</span>' +
          '<span class="att-what">' + te(esc(x.en), esc(x.zh)) + '</span>' +
          '<span class="att-stance ' + x.stance + '">' + te(s[0], s[1]) + '</span>' +
          '<span class="att-chev">›</span></div>';
      }).join('');
    }
    var scope = el('ws_att_scope');
    if (scope) {
      scope.innerHTML = te(stack.length + ' of ' + open.length + ' positions',
                           open.length + ' 只中的 ' + stack.length + ' 只');
    }
  }

  // ---- render --------------------------------------------------------------
  /* The workspace owns the page STATE; this file owns the signed-in composition of it.
     An anonymous visitor's book read and holdings table are drawn by watchlist.js from
     what they pasted, so painting here as soon as `rows` resolves would overwrite that
     read with an empty signed-in shell — which is exactly what it did: the anonymous
     analysis appeared for one frame and was then replaced by "No positions yet". */
  function wsState() {
    return document.documentElement.getAttribute('data-ws-state') || 'signed';
  }
  function renderReadBanner() {
    var host = el('pf_readbanner'); if (!host) return;
    /* A1A (§10, defect "authenticated cloud-to-local fork"): a degraded cloud read
       shows the LAST-GOOD rows read-only, disclosed here — never silently, never as an
       unqualified "Saved" table. An error with no last-good never reaches this line
       (render() returns before it — showError() handles that case instead).
       M-c (review): a LATER read that fails while `rows` still holds an EARLIER
       successful read's content also lands here with `state === 'error'` (reload()'s
       `.catch()` sets 'error' but deliberately never touches `rows`) — that used to
       render the stale table with no disclosure at all. It reads exactly like
       'degraded' to the visitor (last-good rows, read-only) and gets the same banner.
       A1A blocker 2: read through the ONE snapshot (refreshSnapshot()), never a
       second literal mirror of `readState.state` — PS-absent falls back to the exact
       same reads on `readState` directly (B2: legacy-quiet). */
    var snap = refreshSnapshot();
    var rs = snap ? snap.read_state : readState.state;
    if (rs === 'degraded' || (rs === 'error' && rows && rows.length)) {
      host.textContent = L('degradedBanner');
      host.className = 'pf-readbanner is-degraded';
      host.style.display = 'block';
      /* F5 (Sol post-review): the banner's frozen copy (§13c) is verbatim
         regardless of WHY the read degraded — but the reason (cloud-unavailable,
         F6's client-timeout/read-timeout, …) is still real information, exposed
         as a machine-readable attribute rather than silently discarded. Read
         through the ONE snapshot's own `warning` field, PS-present. */
      var warn = snap ? snap.warning : readState.warning;
      host.setAttribute('data-warning', warn || '');
    } else {
      host.style.display = 'none';
      host.textContent = '';
      host.setAttribute('data-warning', '');
    }
  }
  function render() {
    if (!section()) return;
    // A1A blocker 2: assemble the ONE portfolio_snapshot.v1 for this render pass.
    // openRows()/closedRows()/renderReadBanner() below all read it (or refresh their
    // own equivalent copy of the same inputs, PS-present) rather than re-deriving
    // population/read-state a second, independent way.
    refreshSnapshot();
    if (rows === null) {
      /* A1A: `rows === null` now means one of three honest things — not loaded yet
         (readState still its default 'ready'), a cloud read that genuinely failed
         with no last-good rows to fall back to (readState.state === 'error'), or the
         delayed-cloud window on an auth flip (readState.state === 'loading', onAuth()
         below) — the previous authority's rows were cleared and the real read has not
         settled yet. Each gets its own explicit, honest paint; NEVER a silent zero
         and NEVER a PRIOR authority's rows (anonymous local, or a previous user's
         cloud book, B1) left standing or substituted in.
         Sol blocker 1 (Risk Center residue, root-caused by parallel debugger, producer
         (d)): this branch used to return without ever calling pushFxWeights() below —
         FX was told NOTHING, so watchlist.js's mode render simply repainted whatever
         RISK payload it last retained (a Watchlist-derived read, or a stale prior
         Portfolio one) under "positions unknown". Clearing FX's own weights here,
         honest-empty and before ANY return in this block, closes that gap at its
         source — "unknown" can never render as someone else's risk.
         Harness non-vacuity finding (F2 follow-on): same mode-gate as
         pushFxWeights() — this file's `rows` can turn null (a background read
         failing) while the reader is on the WATCHLISTS tab; pushing here
         unconditionally would re-lock AUTO_W into empty-auto mode and silently
         blank the Watchlists tab's own FX panel the reader is looking at.
         Portfolio dollar values (honest-empty or real) feed FX ONLY while the
         Portfolio tab is the active mode — switching INTO it re-runs this exact
         render() pass (window.PF.render() from watchlist.js's own dispatcher) and
         pushes the correct honest-empty state at that point instead. */
      var pushMode = (window.WS && window.WS.mode) ? window.WS.mode() : 'portfolio';
      if (pushMode === 'portfolio' && window.FX && window.FX.setAutoWeights) window.FX.setAutoWeights({});
      if (readState.state === 'error' && wsState().indexOf('anon') !== 0) { showError(); return; }
      if (readState.state === 'loading' && wsState().indexOf('anon') !== 0) { showLoading(); return; }
      return;
    }
    if (wsState().indexOf('anon') === 0) return;

    renderReadBanner();
    renderTable();
    renderBookRead();
    renderAttention();

    // books strip + factor weights — Portfolio rows ONLY (A1A §11: no Watchlist name
    // may enter the Portfolio's own book model; watchlist.js no longer feeds this call).
    if (MB()) MB().refresh(rows, priceOf);
    pushFxWeights();
    publishEarningsFact();

    hydrate();
  }

  /* Progressive hydration through SD's bounded-concurrency batcher. Each name repaints
     its OWN row as it lands, so a 100-position book never blocks first paint and ONE
     failed ticker degrades exactly one row. */
  function hydrate() {
    if (hydrated || !rows || !rows.length) return;
    hydrated = true;
    var tickers = [], seen = {};
    rows.forEach(function (r) {
      if (r.ticker && !seen[r.ticker]) { seen[r.ticker] = 1; tickers.push(r.ticker); }
    });
    if (!tickers.length || !window.SD || !window.SD.loadTickers) return;
    window.SD.loadTickers(tickers, function (t, j) {
      jsonCache[t] = j;
      priceCache[t] = (j && j.tech && j.tech.price != null)
        ? { price: j.tech.price, asof: j.asof || '' } : null;
      if (j && window.WRI && window.WRI.noteJson) { try { window.WRI.noteJson(t, j); } catch (e) {} }
      repaintRow(t);
    }).then(function () {
      render();          // one settled pass with prices + reads filled
      loadCtx();
    });
  }

  var pending = {}, rafOn = false, focusAfter = null;
  function focusExp(id) {
    var btn = document.querySelector('#tbl_pf .exp[data-row-exp="' + CSS_escape(id) + '"]');
    if (btn && btn.focus) btn.focus();
  }
  function repaintRow(t, keepFocusId) {
    pending[t] = 1;
    if (keepFocusId) focusAfter = keepFocusId;
    if (rafOn) return;
    rafOn = true;
    var run = function () {
      rafOn = false;
      var todo = Object.keys(pending); pending = {};
      var open = openRows(), totals = bookValueTotals(open);
      todo.forEach(function (tk) {
        var row = document.querySelector('#tbl_pf tr[data-t="' + CSS_escape(tk) + '"]');
        if (!row) return;
        var r = null;
        for (var i = 0; i < open.length; i++) if (open[i].ticker === tk) { r = open[i]; break; }
        if (!r) return;
        var frag = document.createElement('tbody');
        frag.innerHTML = holdRowHTML(r, totals);
        var drawer = row.nextElementSibling;
        if (drawer && drawer.classList.contains('row-drawer')) drawer.remove();
        var parent = row.parentNode, anchor = row.nextSibling;
        parent.removeChild(row);
        while (frag.firstElementChild) parent.insertBefore(frag.firstElementChild, anchor);
      });
      if (focusAfter) { focusExp(focusAfter); focusAfter = null; }
    };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
    else setTimeout(run, 16);
  }

  /* ctx (US stage rows) — deferred to idle, and only when a modeled position exists.
     Account-gated: a 401 resolves to null and the stage rows simply omit (the drawer
     says so rather than rendering a shorter, quieter drawer). */
  function loadCtx() {
    if (ctxTried) return;
    var anyModeled = openRows().some(function (r) { return isModeled(r.ticker); });
    if (!anyModeled) return;
    ctxTried = true;
    var go = function () {
      fetch('data/portfolio_ctx.json')
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          ctxMap = (j && j.tickers) || null;
          render();
        })
        .catch(function () { ctxMap = null; render(); });
    };
    if (window.requestIdleCallback) window.requestIdleCallback(go, { timeout: 3000 });
    else setTimeout(go, 1200);
  }

  // ---- fact: names reporting this week --------------------------------------
  function publishEarningsFact() {
    if (!MB() || !MB().setFact) return;
    var n = 0, seen = {};
    openRows().forEach(function (r) {
      var t = r.ticker, j = jsonCache[t];
      if (!t || seen[t] || !j) return;
      seen[t] = 1;
      var d = eventDays(j);
      if (d != null && d >= 0 && d <= 7) n++;
    });
    MB().setFact('earn', n);
  }

  /* N1 (Sol post-review, MAJOR, freeze §5 — inverse of blocker 1, proofF/proofF2):
     watchlist_risk.js's publish() forwards EVERY payload it computes to this seam
     with no mode/universe guard. F2's own fix made FX correctly announce the
     WATCHLIST universe while the reader is on the Watchlists tab — which means
     watchlist_risk.js can now genuinely compute a payload keyed to WATCHLIST
     names and hand it here. Consumer-side validation: the payload's per-name maps
     (shares/covered/cluster/ballast) must name ONLY tickers that are actually in
     THIS book's own open rows. An empty payload (no per-name keys at all) is
     always accepted as a clear — that is the honest S3/F2 "nothing to weight"
     signal. A payload naming even ONE foreign ticker is rejected WHOLESALE —
     never partially accepted, never repainted from. */
  function payloadIsConsistentWithBook(payload) {
    if (!payload) return true;
    var maps = [payload.shares, payload.covered, payload.cluster, payload.ballast];
    var seen = {}, any = false;
    maps.forEach(function (m) {
      if (!m) return;
      for (var k in m) {
        if (!Object.prototype.hasOwnProperty.call(m, k)) continue;
        any = true;
        seen[k] = true;
      }
    });
    if (!any) return true;
    var openTickers = {};
    openRows().forEach(function (r) { if (r.ticker) openTickers[r.ticker] = true; });
    for (var t in seen) {
      if (Object.prototype.hasOwnProperty.call(seen, t) && !openTickers[t]) return false;
    }
    return true;
  }

  /* The risk publisher's landing pad (watchlist_risk.js computes, this file composes).
     Everything here is DISPLAY of a number the model produced — nothing is derived,
     re-scaled or re-ranked on the way in. */
  /* LAW 3 (A1A round-3, Sol P0 — risk provenance): fail-closed provenance check,
     run BEFORE payloadIsConsistentWithBook()'s empty-payload early-accept — a
     stale or wrong-scope EMPTY {} payload must still be rejected, never waved
     through as "nothing to weight". Symbol overlap alone is not provenance (Sol,
     verbatim): payloadIsConsistentWithBook() STAYS as an ADDITIONAL layer on top
     of this (do_not_redo: never remove it), not a replacement for it. */
  function setBookRisk(payload) {
    var curGen = (window.WS && window.WS.prov) ? window.WS.prov().gen : null;
    if (!payload || !payload.prov || payload.prov.scope !== 'portfolio' ||
        curGen === null || payload.prov.gen !== curGen) return;
    if (!payloadIsConsistentWithBook(payload)) return;
    BOOK = payload || null;
    RISK_SHARES = (payload && payload.shares) || {};
    RISK_COVERED = (payload && payload.covered) || {};
    if (section() && rows && wsState().indexOf('anon') !== 0) {
      renderTable(); renderBookRead(); renderAttention();
    }
  }

  function relabelStatic() { /* every label on the workspace is a dual-emit span now */ }

  // ---- modal ---------------------------------------------------------------
  function pfOpenDlg() {
    var dlg = el('dlg-holding'); if (!dlg) return;
    prevFocusEl = document.activeElement;
    dlg.classList.add('open');
    document.documentElement.classList.add('mx5-dlg-lock');
    var first = dlg.querySelector('input, select, textarea, button');
    if (first) setTimeout(function () { first.focus(); }, 0);
  }
  function pfCloseDlg() {
    var dlg = el('dlg-holding'); if (!dlg) return;
    dlg.classList.remove('open');
    document.documentElement.classList.remove('mx5-dlg-lock');
    if (prevFocusEl && prevFocusEl.focus) { try { prevFocusEl.focus(); } catch (e) {} }
    prevFocusEl = null;
  }
  function clearModal() {
    ['pfm_ticker', 'pfm_shares', 'pfm_price', 'pfm_date', 'pfm_notes'].forEach(function (id) {
      var e = el(id); if (e) e.value = '';
    });
    var statusRow = el('pfm_status_row'); if (statusRow) statusRow.style.display = 'none';
    var statusSel = el('pfm_status'); if (statusSel) statusSel.value = 'open';
    var errEl = el('pfm_err'); if (errEl) errEl.textContent = '';
    var hintEl = el('pfm_hint'); if (hintEl) hintEl.textContent = '';
    var suggEl = el('pfm_sugg'); if (suggEl) suggEl.innerHTML = '';
  }
  function openAddModal() {
    if (!section()) return;
    editingId = null; clearModal();
    setText('pfm_title', L('modalAddTitle'));
    pfOpenDlg();
  }
  function openEditModal(id) {
    if (!section() || !rows) return;
    var row = null;
    for (var i = 0; i < rows.length; i++) {
      if (String(rows[i].id) === String(id)) { row = rows[i]; break; }
    }
    if (!row) return;
    editingId = id; clearModal();
    setText('pfm_title', L('modalEditTitle'));
    var te2 = el('pfm_ticker'); if (te2) te2.value = row.ticker || '';
    var se = el('pfm_shares'); if (se) se.value = row.shares != null ? String(row.shares) : '';
    var pe = el('pfm_price'); if (pe) pe.value = row.entry_price != null ? String(row.entry_price) : '';
    var de = el('pfm_date'); if (de) de.value = row.entry_date || '';
    var ne = el('pfm_notes'); if (ne) ne.value = row.notes || '';
    var statusRow = el('pfm_status_row'); if (statusRow) statusRow.style.display = '';
    var statusSel = el('pfm_status');
    if (statusSel) statusSel.value = row.status === 'closed' ? 'closed' : 'open';
    updateTickerHint(row.ticker || '');
    pfOpenDlg();
  }

  // ---- ticker suggest in modal (searches every loaded market index) ---------
  function updateTickerHint(ticker) {
    var hintEl = el('pfm_hint'); if (!hintEl) return;
    if (!ticker || !sdIndex) { hintEl.textContent = ''; hintEl.style.display = 'none'; return; }
    // "not covered" only when the name misses EVERY loaded index
    if (idxRec(ticker.toUpperCase())) { hintEl.textContent = ''; hintEl.style.display = 'none'; }
    else { hintEl.textContent = L('notCovered'); hintEl.style.display = 'block'; }
  }
  function wireTickerSuggest() {
    var input = el('pfm_ticker'); if (!input) return;
    var suggEl = el('pfm_sugg'); if (!suggEl) return;
    var retried = false;

    function paint(v) {
      var vl = v.toLowerCase();
      if (!sdIndex || !sdIndex.list) { suggEl.innerHTML = ''; return; }
      var matches = sdIndex.list.filter(function (x) {
        return x.t.toLowerCase().indexOf(vl) === 0 ||
               (x.n && x.n.toLowerCase().indexOf(vl) >= 0);
      }).slice(0, 8);
      // a suffixed query or a miss: pull the remaining market indexes once, then retry
      if ((!matches.length || v.indexOf('.') >= 0) && !retried && window.SD && window.SD.loadIndexes) {
        retried = true;
        window.SD.loadIndexes(['us', 'cn', 'hk', 'ca', 'intl']).then(function (r) {
          sdIndex = r; paint(v);
        });
      }
      if (!matches.length) { suggEl.innerHTML = ''; suggEl.style.display = 'none'; return; }
      suggEl.innerHTML = matches.map(function (x) {
        var mkt = marketOf(x.t), meta = bookMeta(mkt);
        var glyph = (mkt !== 'us' && meta)
          ? '<span class="bk-glyph pfm-mkt">' + esc(meta.glyph) + '</span>' : '';
        return '<div data-sugg="' + esc(x.t) + '"><b>' + esc(x.t) + '</b> ' + glyph +
          '<small>' + esc(x.n || '') + '</small></div>';
      }).join('');
      suggEl.style.display = 'block';
    }

    input.addEventListener('input', function () {
      var v = input.value.trim();
      updateTickerHint(v.toUpperCase());
      if (!v) { suggEl.innerHTML = ''; suggEl.style.display = 'none'; return; }
      paint(v);
    });
    suggEl.addEventListener('mousedown', function (e) {
      var d = e.target.closest('[data-sugg]'); if (!d) return;
      var t = d.getAttribute('data-sugg');
      input.value = t; updateTickerHint(t);
      suggEl.innerHTML = ''; suggEl.style.display = 'none';
      e.preventDefault();
    });
    input.addEventListener('blur', function () {
      setTimeout(function () {
        if (suggEl) { suggEl.innerHTML = ''; suggEl.style.display = 'none'; }
      }, 200);
    });
  }

  // ---- save / remove -------------------------------------------------------
  /* A1A (§13, defect "Save-state crossover"): the header save chip used to be driven
     ONLY by Watchlist synchronization (watchstore.js's `ws-save`), so it was never a
     reliable answer for "did my POSITION save?" — a Portfolio write could fail while
     the chip still said "Saved" (that was true of the Watchlist, not the Portfolio).
     `pf-save` is a parallel event carrying Portfolio write/read authority specifically;
     watchlist.js's chip picks whichever event matches the active mode (portfolio.js
     never touches the chip's DOM directly — same seam discipline as the Watchlist). */
  function dispatchPfSave(state) {
    /* A1A blocker 2/3: keep the tracked write_state (feeds refreshSnapshot()) in
       lockstep with whatever word this dispatch just told the chip — so the ONE
       snapshot this file assembles always answers "what did we just say happened"
       consistently, rather than a second silent mirror of the same fact that could
       drift from it. Every other chip word ('local', 'clean', 'unavailable', a plain
       read's 'saving' during the S6 loading window) means "nothing is currently
       in-flight or just landed" -> 'clean' (refreshSnapshot derives 'offline_readonly'
       from readState when that is also honest). */
    writeState = (state === 'saving' || state === 'saved' || state === 'failed' ||
                  state === 'failed_local') ? state : 'clean';
    try { document.dispatchEvent(new CustomEvent('pf-save', { detail: { state: state } })); }
    catch (e) { /* no CustomEvent (very old browser / test shell) */ }
  }
  /* F3 (Sol post-review, MAJOR — proofC_anon_write_failure.py): 'failed' and
     'unavailable' are ACCOUNT-scoped copy ("The write to your account failed…",
     "We cannot reach your cloud portfolio…") — both false for an anonymous
     visitor, who has no account and no cloud portfolio to fail against. A local
     write failure (Safari private mode, storage quota) used to dispatch the same
     account-scoped 'failed' word regardless of authority. Authority-aware: under
     LOCAL authority a write failure is 'failed_local' (device-storage copy);
     'failed'/'unavailable' become unreachable under local authority — the guard
     is on the CURRENT `readState.authority`, the same field every other A1A
     authority check in this file already reads. */
  function dispatchWriteFailure() {
    // F5: reads authority via the ONE snapshot (PS-present); PS-absent falls back
    // to the raw readState field directly.
    var snap = refreshSnapshot();
    var authority = snap ? snap.authority : readState.authority;
    dispatchPfSave(authority === 'local' ? 'failed_local' : 'failed');
  }
  function dispatchReadUnavailable() {
    // 'unavailable' names an unreachable CLOUD read; under local authority there is
    // no cloud account to be unavailable — nothing is actually wrong.
    var snap = refreshSnapshot();
    var authority = snap ? snap.authority : readState.authority;
    dispatchPfSave(authority === 'local' ? 'local' : 'unavailable');
  }
  /* M-d (review): a plain READ that succeeds is not a WRITE claim — 'Saved' means
     "the write you just made landed," and a first load / background re-read never
     made one. `afterWrite` is true ONLY when this settles a doSave()/doRemove() call;
     everything else (onAuth's first load, the visibilitychange refetch, 'pf-folded')
     settles to the neutral 'clean' state instead.
     A1A blocker 3 (Sol, verbatim: "A1A has no authenticated Portfolio outbox, so
     failed Portfolio writes must never claim they are locally retained or will sync
     later"): a non-ready read state used to map to 'offline' unconditionally — the
     WATCHLIST word that claims local retention and push-through sync, both false for
     the authenticated Portfolio. A confirmed write (afterWrite) still reports 'saved'
     even when the FOLLOW-UP read comes back non-ready — the write itself already
     landed (doSave/doRemove only call reload(true) after a truthy result); the read
     story is the read banner's job, not the chip's. A plain (non-afterWrite) non-ready
     read reports the honest 'unavailable', never 'offline'. */
  function pfChipStateFor(rs, afterWrite) {
    /* F4 (Sol post-review, MAJOR — sticky failure disclosure): a FAILED write's
       chip word must not be silently downgraded to clean/saved/local by the NEXT
       unrelated background read (visibilitychange's 60s refetch) — only a
       subsequent CONFIRMED write (afterWrite, settling to 'saved' below) may
       clear it. Consulted via the tracked `writeState` — the same field
       refreshSnapshot() feeds into the snapshot's write_state, so this reads the
       ONE tracked fact rather than a second independent notion of "did the last
       write fail".
       N2 (Sol post-review, MAJOR, proofG d2/d3): the sticky check used to run
       BEFORE the authority guard — a STALE account-scoped 'failed' surviving an
       identity change (onAuth() now resets writeState on identity change, but
       this is the belt-and-suspenders half) leaked into the very NEXT identity's
       first read: an anonymous sign-out, or user B's first healthy read, both
       painted "Change not saved" for a write that was never theirs. The
       authority guard now runs FIRST — a local-authority view can only ever see
       ITS OWN `failed_local` (still honest: this device's own write really did
       fail), never the account-scoped `failed` a prior CLOUD identity left
       behind. */
    // F5 (Sol post-review, MAJOR — real snapshot consumption): the write_state and
    // authority checks below read the ONE snapshot (PS-present), never the raw
    // `writeState`/`rs.authority` fields a second, independently-derived way.
    // PS-absent falls back to the raw fields directly (B2: legacy-quiet).
    var chipSnap = refreshSnapshot();
    var chipWriteState = chipSnap ? chipSnap.write_state : writeState;
    var chipAuthority = chipSnap ? chipSnap.authority : (rs && rs.authority);
    if (!rs || chipAuthority === 'local') {
      if (!afterWrite && chipWriteState === 'failed_local') return 'failed_local';
      return 'local';
    }
    if (!afterWrite && (chipWriteState === 'failed' || chipWriteState === 'failed_local')) {
      return chipWriteState;
    }
    // S6's brief cloud-loading window ('user' set, the shared Supabase client not yet
    // resolved) is NOT offline — 'saving' is the closest honest existing word for "a
    // read is in flight," and it self-corrects within the tick the re-fired 'wl-auth'
    // lands (watchstore.js dispatches it the instant `sb` resolves).
    if (rs.state === 'loading') return 'saving';
    if (rs.state !== 'ready') return afterWrite ? 'saved' : 'unavailable';
    return afterWrite ? 'saved' : 'clean';
  }

  function reload(afterWrite) {
    if (!window.WatchStore || !window.WatchStore.portfolio) return;
    hydrated = false;
    // LAW 2: this call's own generation — a later reload()/onAuth() call bumping
    // loadGen before THIS one resolves makes both handlers below no-ops.
    var gen = ++loadGen;
    window.WatchStore.portfolio.list().then(function (newRows) {
      if (gen !== loadGen) return;
      var rs = window.WatchStore.portfolio.readState ? window.WatchStore.portfolio.readState() : null;
      readState = rs || { authority: 'local', state: 'ready', last_good_at: null, warning: null };
      dispatchPfSave(pfChipStateFor(readState, afterWrite));
      /* A1A: `newRows === null` is the explicit "genuinely unknown" answer (§10) —
         keep whatever `rows` already held (last-good was already folded into
         readState.state === 'degraded' by watchstore.js; a bare `null` here only
         happens with NO last-good, i.e. readState.state === 'error') and let render()
         decide what to show. NEVER coerce it to []  — that is the "never assert zero"
         law, and `rows || []` was exactly that coercion. */
      if (newRows === null) { render(); return; }
      rows = newRows;
      ensureIndex().then(render);
    }).catch(function () {
      if (gen !== loadGen) return;
      readState = { authority: readState.authority, state: 'error',
                    last_good_at: readState.last_good_at, warning: 'read-failed' };
      /* A1A blocker 3: this catch fires for a READ failure. When it follows a
         CONFIRMED write (afterWrite — doSave()/doRemove() only call reload(true)
         after upsert/remove already returned a truthy result), the write itself
         landed; only the follow-up read failed. 'saved' stays honest; the read
         banner (renderReadBanner, driven by the same readState) carries the read
         story. Otherwise this is a plain read failure with no write involved:
         'unavailable' (or, under local authority, F3's 'local' — see
         dispatchReadUnavailable()), never 'offline' (this file has no local
         retention to claim for the cloud case). */
      if (afterWrite) { dispatchPfSave('saved'); } else { dispatchReadUnavailable(); }
      render();
    });
  }

  function doSave() {
    if (!section()) return;
    var saveBtn = el('pfm_save'); if (!saveBtn) return;
    var errEl = el('pfm_err');
    var ticker = (el('pfm_ticker') ? el('pfm_ticker').value.trim().toUpperCase() : '');
    if (!ticker) { if (errEl) errEl.textContent = L('tickerRequired'); return; }

    var pos = {
      ticker: ticker,
      shares: el('pfm_shares') ? el('pfm_shares').value.trim() : '',
      entry_price: el('pfm_price') ? el('pfm_price').value.trim() : '',
      entry_date: (el('pfm_date') ? el('pfm_date').value.trim() : '') || null,
      notes: el('pfm_notes') ? el('pfm_notes').value.trim() : '',
      status: (el('pfm_status') && el('pfm_status').value === 'closed') ? 'closed' : 'open'
    };
    if (editingId) pos.id = editingId;

    if (errEl) errEl.textContent = '';
    saveBtn.disabled = true;
    if (!window.WatchStore || !window.WatchStore.portfolio) {
      if (errEl) errEl.textContent = L('saveError');
      saveBtn.disabled = false; return;
    }
    dispatchPfSave('saving');
    window.WatchStore.portfolio.upsert(pos).then(function (result) {
      saveBtn.disabled = false;
      if (!result) {
        if (errEl) errEl.textContent = L('saveError');
        // A1A blocker 3: never claim Saved OR account-side retention on a write
        // that did not happen. F3: authority-aware — 'failed' (account copy) is
        // false for an anonymous visitor; dispatchWriteFailure() picks the right
        // word.
        dispatchWriteFailure();
        return;
      }
      pfCloseDlg();
      reload(true);   // afterWrite: reload() dispatches 'saved', not 'clean' (M-d)
    }).catch(function () {
      saveBtn.disabled = false;
      if (errEl) errEl.textContent = L('saveError');
      dispatchWriteFailure();
    });
  }

  function doRemove(id) {
    if (!window.WatchStore || !window.WatchStore.portfolio ||
        !window.WatchStore.portfolio.remove) return;
    delete openDrawers[id];
    dispatchPfSave('saving');
    window.WatchStore.portfolio.remove(id).then(function (result) {
      // A1A blocker 3/F3: a failed remove is authority-aware too — see doSave().
      if (!result) { dispatchWriteFailure(); return; }
      reload(true);   // afterWrite (M-d)
    }).catch(function () { dispatchWriteFailure(); });
  }

  // ---- drawer toggle -------------------------------------------------------
  function toggleDrawer(id) {
    if (openDrawers[id]) delete openDrawers[id]; else openDrawers[id] = true;
    var row = document.querySelector('#tbl_pf tr.pfx-row[data-row="' + CSS_escape(id) + '"]');
    if (row) repaintRow(row.getAttribute('data-t'), id);
    else { renderTable(); focusExp(id); }
  }
  // attribute-selector safety for ids that came from Supabase (uuid) or 'loc-<n>'
  function CSS_escape(s) { return String(s).replace(/["\\]/g, '\\$&'); }

  // ---- visibility refetch --------------------------------------------------
  document.addEventListener('visibilitychange', function () {
    if (!section() || document.hidden) return;
    var dlg = el('dlg-holding');
    if (dlg && dlg.classList.contains('open')) return;
    var now = Date.now();
    if (now - lastListAt < 60000) return;
    if (!window.WatchStore || !window.WatchStore.user || !window.WatchStore.user()) return;
    lastListAt = now;
    reload();
  });

  // ---- auth event ----------------------------------------------------------
  /* A1A: the FIRST load (init -> onAuth, and every 'wl-auth' transition) used to run
     its own copy of the pre-A1A bug — `rows = newRows || []` coerced a genuinely
     unknown cloud read into a false zero, and never touched `readState` at all, so
     the very first paint of a degraded/errored authenticated session could never show
     the banner reload() now shows. Both paths share the same corrected logic. */
  function onAuth() {
    if (!section()) return;
    if (!window.WatchStore || !window.WatchStore.portfolio) { showError(); return; }
    lastListAt = Date.now();
    hydrated = false;
    /* A1A blocker 2 (Sol, verbatim): "prove anonymous rows never render under
       authenticated authority ... loading always resolves to ready/degraded/error".
       Authority is flipping (either direction) the instant this fires —
       `window.WatchStore.portfolio.list()` below is ASYNC (the S6 cloud-loading
       race, a client-init failure, OR just the local store's own promise
       microtask), so whatever `rows` currently holds (a PRIOR user's cloud book, or
       the anonymous local book) must never be left standing for an interim
       render() — a price tick, a language toggle, an fx event — to paint while the
       real read for THIS authority is still in flight. Clear SYNCHRONOUSLY and
       render the loading state before the list() call below settles anything; the
       unknown-rows branch of render() then paints loading (and, per F2(ii), pushes
       window.FX's honest-empty clear) rather than repainting the OTHER authority's
       book or risk. F2 (Sol post-review): this used to be gated on `user()` being
       truthy (sign-IN only) — a sign-OUT left A's rows/readState/FX weights
       standing through the exact same async gap, just on the local-list side. */
    var authedNow = !!(window.WatchStore.user && window.WatchStore.user());
    /* N2 (Sol post-review, MAJOR): reset the write-failure disclosure on every
       genuine identity change (sign-in, sign-out, or a DIFFERENT uid replacing
       the previous one) — never on the S6 double-fire of the SAME identity,
       which must not clear a write that is still legitimately in flight for
       THIS session. `lastAuthIdentity === undefined` is the one-time "never
       seen a wl-auth yet" state and needs no reset (writeState is already
       'clean' at page load). */
    var uidNow = authedNow ? window.WatchStore.user().id : null;
    if (lastAuthIdentity !== undefined && uidNow !== lastAuthIdentity) {
      writeState = 'clean';
    }
    lastAuthIdentity = uidNow;
    rows = null;
    readState = authedNow
      ? { authority: 'cloud', state: 'loading', last_good_at: null, warning: null }
      : { authority: 'local', state: 'loading', last_good_at: null, warning: null };
    render();
    // LAW 2 (A1A round-3): this call's own generation. onAuth() fires on EVERY
    // 'wl-auth' — including the S6 double-fire (user set, then the shared client
    // resolving) and a genuine identity flip mid-flight — so an OLDER call's
    // resolution must never land after a NEWER one has already started (or
    // finished) painting the new identity's answer.
    var gen = ++loadGen;
    window.WatchStore.portfolio.list().then(function (newRows) {
      if (gen !== loadGen) return;
      var rs = window.WatchStore.portfolio.readState ? window.WatchStore.portfolio.readState() : null;
      readState = rs || { authority: 'local', state: 'ready', last_good_at: null, warning: null };
      dispatchPfSave(pfChipStateFor(readState));
      hideEl('pf_err_inline');
      showEl('pf_add');
      showEl('pf_import');
      if (newRows === null) { render(); return; }   // genuinely unknown — never []
      rows = newRows;
      ensureIndex().then(render);
    }).catch(function () {
      if (gen !== loadGen) return;
      readState = { authority: readState.authority, state: 'error',
                    last_good_at: readState.last_good_at, warning: 'read-failed' };
      // A1A blocker 3/F3: no write is ever involved in onAuth()'s plain read —
      // always the honest, authority-aware word, never 'offline'.
      dispatchReadUnavailable();
      showError();
    });
  }

  // ---- event wiring --------------------------------------------------------
  function wireEvents() {
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var dlg = el('dlg-holding');
      if (dlg && dlg.classList.contains('open')) { pfCloseDlg(); return; }
      var ids = Object.keys(openDrawers);
      if (!ids.length) return;
      var id = ids[0];
      delete openDrawers[id];
      var row = document.querySelector('#tbl_pf tr.pfx-row[data-row="' + CSS_escape(id) + '"]');
      if (row) repaintRow(row.getAttribute('data-t'), id);
      else { renderTable(); focusExp(id); }
      e.preventDefault();
    });
    var dlg = el('dlg-holding');
    if (dlg) dlg.addEventListener('click', function (e) {
      if (e.target && e.target.getAttribute('data-close') !== null) pfCloseDlg();
    });
    var addBtn = el('pf_add'); if (addBtn) addBtn.addEventListener('click', openAddModal);
    var saveBtn = el('pfm_save'); if (saveBtn) saveBtn.addEventListener('click', doSave);

    var sec = section();
    if (sec) {
      sec.addEventListener('click', function (e) {
        var tgt = e.target;
        var editBtn = tgt.closest ? tgt.closest('[data-edit]') : null;
        if (editBtn) { openEditModal(editBtn.getAttribute('data-edit')); return; }
        var rmBtn = tgt.closest ? tgt.closest('[data-rm-pos]') : null;
        if (rmBtn) { doRemove(rmBtn.getAttribute('data-rm-pos')); return; }
        if (tgt.closest && tgt.closest('#pf_signin_inline')) {
          if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signin');
          return;
        }
        /* The ⌄ affordance, handled BEFORE the generic link/button bail — because it IS
           a button, and the bail below was swallowing it. The chevron rotated (it is
           driven by `aria-expanded` on the row, which the renderer sets from
           `openDrawers`) while clicking it did nothing at all: the drawer could only be
           opened by clicking some OTHER part of the row. The one control the design
           points at was the one control that did not work, and it looked live because
           the rotation is CSS. The watchlist table's own delegation already handles
           `[data-exp]` first, which is why only this half was dark. */
        var expBtn = tgt.closest ? tgt.closest('[data-row-exp]') : null;
        if (expBtn) { toggleDrawer(expBtn.getAttribute('data-row-exp')); return; }
        // a click anywhere else on the row (but not on a link/button) toggles it too
        if (tgt.closest && (tgt.closest('a') || tgt.closest('button'))) return;
        var row = tgt.closest ? tgt.closest('tr.pfx-row') : null;
        if (row) toggleDrawer(row.getAttribute('data-row'));
      });
      // keyboard: Enter/Space on a focused row toggles its drawer
      sec.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var row = e.target && e.target.closest ? e.target.closest('tr.pfx-row') : null;
        if (!row) return;
        e.preventDefault();
        toggleDrawer(row.getAttribute('data-row'));
      });
    }

    document.addEventListener('langchange', function () { if (section()) render(); });
    document.addEventListener('wl-auth', function () { onAuth(); });
    document.addEventListener('pf-folded', function () { reload(); });
    /* A1B's paste/review surface owns no Portfolio state. It reports only a
       privacy-safe lifecycle word; this canonical consumer keeps the existing
       write-honesty chip and authoritative reread path in one place. */
    document.addEventListener('pf-import-state', function (e) {
      var state = e && e.detail && e.detail.state;
      if (state === 'saving') dispatchPfSave('saving');
      else if (state === 'saved') reload(1); // confirmed import write; truthy afterWrite
      else if (state === 'failed') dispatchWriteFailure();
    });
    document.addEventListener('bk-change', function () { if (section() && rows) render(); });
    /* A1A (§11): the Portfolio's own book model is built from Portfolio rows ONLY —
       a Watchlist change can no longer move it, so there is nothing for a `wl-changed`
       listener to do here any more (it used to re-run the union-based MB().refresh).
       Removed rather than left as a silent no-op wire. */
    wireTickerSuggest();
  }

  // ---- init ----------------------------------------------------------------
  function init() {
    if (!section()) return;
    wireEvents();
    // The book is real whether or not anyone is signed in: load it immediately.
    // watchstore.js resolves signed-out to the localStorage book behind the same API.
    onAuth();
  }

  /* The workspace seam. watchlist.js owns the page's render pass and calls in here
     for the Portfolio mode; watchlist_risk.js publishes the model read through
     setBookRisk. Nothing outside this file touches `rows`. */
  window.PF = {
    render: render,
    // A1A: never a Watchlist-derived number and never a false zero — `null` when the
    // canonical count is genuinely unknown. Callers (watchlist.js's pfCount) must
    // treat `null` as "show unavailable", not as 0.
    // F1 (Sol post-review, blocker): population is assertable ONLY when the read
    // genuinely resolved — 'ready', or 'degraded' with last-good rows (which always
    // arrives WITH non-null rows, never null). `rows === null` is the ONE honest
    // signal covering BOTH the terminal 'error' window AND the 'loading' delayed-
    // cloud window (onAuth's synchronous clear, A1A blocker 2) — the old
    // `readState.state === 'error'`-only check let 'loading' fall through to
    // `openRows().length`, which is 0 whenever rows is null (openRows()'s own early
    // return) — a false zero rendered on a signed-in visitor's Portfolio tab mid-read.
    count: function () { return rows === null ? null : openRows().length; },
    repaintRow: repaintRow,
    setBookRisk: setBookRisk,
    // N1 (Sol post-review, MAJOR): explicit reset seam for the mode/auth boundary
    // — mirrors watchlist.js's own RISK reset (setMode()'s enteringPortfolio
    // branch and the wl-auth identity-change listener) so a stale (possibly
    // foreign-keyed) BOOK/RISK_SHARES/RISK_COVERED payload is cleared BEFORE the
    // Portfolio's own publisher round-trip has a chance to replace it — never
    // left painting until that async trip lands.
    resetBookRisk: function () {
      BOOK = null; RISK_SHARES = {}; RISK_COVERED = {};
      if (section() && rows && wsState().indexOf('anon') !== 0) {
        renderTable(); renderBookRead(); renderAttention();
      }
    },
    readState: function () { return readState; }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

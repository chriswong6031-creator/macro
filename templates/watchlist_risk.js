/* watchlist_risk.js — the Watchlist Risk Intelligence render layer (WRI W3).

   Renders the three-layer risk read the repo already computes but never showed
   the user (masterplan §6), into the pinned W2 markup/CSS:

     L3  regime rail   — window.WRI_REGIME (baked risk_radar state + dominant
                         label + vol regime) crossed with the book's measured
                         market beta.
     L2  Book Risk hero— lens-aware verdict + named state chip, the bets
                         "patch-bay" signature (data-driven port of the mockup
                         SVG builder), three sub-cards (what drives your swings /
                         move as one / biggest single risks), method footnote.
                         Absorbs the old #fx_panel: its beta table + shocks +
                         weight editor move into a <details> drawer in sub-card 1.
     L1  card lanes    — per-name lane chips + a drawer of plain-word reads,
                         composed CLIENT-SIDE from stockdata/<T>.json real fields,
                         plus the Risk Desk role badge (review labels only).

   All book math is RiskCore (templates/risk_core.js); weights come from the FX
   panel's plumbing (window.FX.currentWeights — portfolio dollar values, or the
   manual editor / equal-weight fallback) so the two layers never fork. Display
   tier only: measurement, not a forecast (WRI-R8); no fused composite (WRI-R2);
   review language only, no advice verbs (WRI-R4).

   Depends on window.RiskCore, window.SD (stockdata.js), window.FX
   (factor_exposure.js). Degrades to nothing when its DOM host is absent. */
(function () {
  'use strict';

  function lang() { return document.documentElement.getAttribute('data-lang') === 'zh' ? 'zh' : 'en'; }
  function isZh() { return lang() === 'zh'; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function te(en, zh) {   // bilingual span pair (matches the t() macro output)
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>';
  }
  function pct0(x) { return Math.round(x * 100) + '%'; }
  function isNum(x) { return typeof x === 'number' && isFinite(x); }

  // ---- FX-corruption guard (A3 law 3) -------------------------------------
  // The 9-factor model is USD and carries zero suffixed tickers. Non-US books price
  // in HKD/CNY/CAD, so their values must never reach a book statistic: one HK$ figure
  // inside the weight sum silently corrupts every number this layer prints (factor
  // shares, effective bets, correlations, MCTR). Filter at the book-math boundary —
  // not only at the producer — so any future weights source is covered too.
  function isModeled(t) {
    return (window.MB && window.MB.isModeled) ? window.MB.isModeled(t) : true;
  }
  function modeledUniverse(list) {
    return (list || []).filter(isModeled);
  }
  function activeBook() {
    return (window.MB && window.MB.getBook) ? window.MB.getBook() : 'all';
  }
  // books whose names the factor/risk model actually covers
  function bookIsModeled(b) { return b === 'all' || b === 'us' || b === 'crypto' || b === 'macro'; }
  // does the user hold names in more than one market? (drives the scope wording)
  function multiBook() {
    return !!(window.MB && window.MB.presentBooks && window.MB.presentBooks().length > 1);
  }

  // ---- condition counts (§5.4) --------------------------------------------
  // Registry of per-name JSONs already fetched by the cards / the position table.
  // No new fetches: the counts simply read what the page has hydrated so far and
  // refresh as more arrives.
  var CARD_JSON = {};
  function noteJson(t, j) {
    if (!t || !j) return;
    if (CARD_JSON[t] === j) return;
    CARD_JSON[t] = j;
    /* The Events tab reads this registry, so a hydration wave has to reach it — but
       it must NOT reach it one re-render per resolved name, and it must not re-run
       RiskCore (the book has not changed; only what we know about its names has).
       `republishTabs` rebuilds the tab strings from the cached read on ONE frame. */
    scheduleTabRefresh();
  }

  /* The cached read the tabs were last built from. Held so a hydration wave can
     refresh the event calendar without a second RiskCore pass, and so the two are
     never built from different books. */
  var LAST_READ = null;   // { RR, active, cov }
  var _tabsPending = false;
  function scheduleTabRefresh() {
    if (_tabsPending || !LAST_READ) return;
    _tabsPending = true;
    var run = function () { _tabsPending = false; republishTabs(); };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
    else setTimeout(run, 16);
  }
  function republishTabs() {
    if (!LAST_READ || !window.WS || !window.WS.setRisk) return;
    try { window.WS.setRisk(tabPayload(LAST_READ)); } catch (e) {}
  }
  function tabPayload(R) {
    var active = R.active, RR = R.RR, cov = R.cov;
    return {
      concHTML: concentrationHTML(active, cov),
      rcTabs: {
        conc: concentrationHTML(active, cov),
        corr: correlationHTML(active, cov),
        fact: factorsHTML(active, cov),
        strs: stressHTML(RR, cov),
        evt:  eventsHTML(cov),
        weak: weakLinksHTML(active, cov)
      },
      labHTML: labIntroHTML()
    };
  }
  /* The condition-count line ("N of M names in review or worse") is retired with the
     braid hero. Its job — telling the reader how much of the book the summary above is
     actually about — is done better and in plain words by the attention stack's own
     "5 of 12 positions" disclosure, which the pinned design makes part of the section
     header. Two sentences answering one question, one line apart, was the defect. */
  // ---- factor display metadata (hue class + bilingual label) --------------
  // labels mirror factor_exposure.js ZH map + the mockup's plain words.
  var FLABEL = {
    mkt: { en: 'Market', zh: '大盘' }, growth: { en: 'Growth / Tech', zh: '成长/科技' },
    size: { en: 'Small-cap', zh: '小盘' }, rates: { en: 'Rates', zh: '利率' },
    usd: { en: 'US dollar', zh: '美元' }, oil: { en: 'Oil / energy', zh: '石油/能源' },
    china: { en: 'China', zh: '中国' }, btc: { en: 'Bitcoin', zh: '比特币' },
    gold: { en: 'Gold', zh: '黄金' }
  };
  function fhue(k) { return 'var(--f-' + k + ')'; }
  function flabel(k) { var f = FLABEL[k]; return f ? (isZh() ? f.zh : f.en) : k; }

  // =========================================================================
  //  L1 — per-name lane engine (composed from stockdata/<T>.json real fields)
  // =========================================================================
  // Each lane -> { state:'ok'|'watch'|'elev'|'na', chip:{...}|null, en, zh } where
  // `chip` (when present) surfaces on the card at rest. Missing source block =>
  // state 'na' + plain "not covered"; never invents a read. Lane names + chip
  // vocabulary are the pinned W2 §7 plain words.
  var LANES = ['price_trend', 'stretch', 'events', 'estimates', 'balance', 'selling', 'rates'];
  var LANE_LABEL = {
    price_trend: { en: 'Price & trend', zh: '价格与趋势' }, stretch: { en: 'Stretch', zh: '拉伸度' },
    events: { en: 'Events', zh: '事件' }, estimates: { en: 'Estimates', zh: '盈利预期' },
    balance: { en: 'Balance sheet', zh: '资产负债' }, selling: { en: "Who's selling", zh: '谁在卖出' },
    rates: { en: 'Rate sensitivity', zh: '利率敏感' }
  };
  var NA = { en: 'not covered', zh: '未覆盖' };

  function laneRead(j) {
    var out = {};
    var tech = (j && j.tech) || null;
    // --- price & trend --------------------------------------------------
    if (tech && (tech.above200 != null || tech.above50 != null)) {
      var above200 = !!tech.above200, off = tech.off_52w_high_pct;   // off is SIGNED (neg = below high)
      var offAbs = isNum(off) ? Math.abs(Math.round(off)) : null;
      var weak = (tech.rs_1m != null && tech.rs_1m < 0) && (tech.rs_3m != null && tech.rs_3m < 0);
      var below = !above200 || (tech.above50 === false);
      var st = below ? 'elev' : (weak ? 'watch' : 'ok');
      var enR = above200
        ? ('above the 200-day' + (offAbs != null ? ', ' + offAbs + '% off its high' : ''))
        : 'below the 200-day' + (offAbs != null ? ', ' + offAbs + '% off its high' : '');
      var zhR = above200
        ? ('位于200日线上方' + (offAbs != null ? '，距高点' + offAbs + '%' : ''))
        : '跌破200日线' + (offAbs != null ? '，距高点' + offAbs + '%' : '');
      out.price_trend = { state: st, en: enR, zh: zhR,
        chip: below ? { cls: '', en: 'Below trend', zh: '跌破趋势' } : null };
    } else out.price_trend = { state: 'na', en: NA.en, zh: NA.zh, chip: null };
    // --- stretch (extension) -------------------------------------------
    var es = (j && j.entry_signal) || null;
    var stretched = es && es.status === 'extended';
    var hv = tech && tech.hv20;
    if (es && es.status != null) {
      out.stretch = { state: stretched ? 'watch' : 'ok',
        en: stretched ? 'ran hard; entries here have chased before' : 'not stretched',
        zh: stretched ? '涨势过快；此位追入历史上多为追高' : '未过度拉伸',
        chip: stretched ? { cls: '', en: 'Stretched', zh: '过度拉伸' } : null };
    } else if (tech && isNum(hv)) {
      var hot = hv > 0.6;
      out.stretch = { state: hot ? 'watch' : 'ok',
        en: hot ? 'very volatile lately' : 'volatility contained',
        zh: hot ? '近期波动很大' : '波动可控', chip: null };
    } else out.stretch = { state: 'na', en: NA.en, zh: NA.zh, chip: null };
    // --- events (earnings window) --------------------------------------
    var earn = (j && j.earnings) || null;
    if (earn && earn.next_date) {
      var days = daysUntil(earn.next_date);
      var when = earn.next_time ? (' ' + timeWord(earn.next_time)) : '';
      var hot2 = isNum(days) && days <= 5 && days >= 0;
      var chipEn = isNum(days) ? (days < 0 ? null : 'Earnings in ' + days + 'd') : null;
      var chipZh = isNum(days) ? (days < 0 ? null : '财报 ' + days + '天内') : null;
      out.events = {
        state: hot2 ? 'elev' : (isNum(days) && days <= 14 && days >= 0 ? 'watch' : 'ok'),
        en: 'reports ' + fmtDate(earn.next_date) + when,
        zh: fmtDateZh(earn.next_date) + timeWordZh(earn.next_time) + '发布',
        chip: chipEn ? { cls: hot2 ? 'hot' : '', en: chipEn, zh: chipZh } : null
      };
    } else out.events = { state: 'na', en: NA.en, zh: NA.zh, chip: null };
    // --- estimates (revisions + surprise) ------------------------------
    var rev = (j && j.revisions) || null, sue = earn && earn.sue_z;
    if (rev && (isNum(rev.breadth) || isNum(rev.net_up_30d) || isNum(rev.est_chg_30d))) {
      var falling = (isNum(rev.est_chg_30d) && rev.est_chg_30d < 0)
        || (isNum(rev.breadth) && rev.breadth < 0.4);
      var rising = (isNum(rev.est_chg_30d) && rev.est_chg_30d > 0)
        || (isNum(rev.breadth) && rev.breadth >= 0.6);
      var nA = isNum(rev.n_analysts) ? Math.round(rev.n_analysts) : null;
      var st2 = falling ? 'elev' : (rising ? 'ok' : 'watch');
      var enR2 = falling ? 'analysts cutting numbers'
        : (rising ? ('analysts still raising numbers' + (nA ? ' (' + nA + ' covering)' : '')) : 'estimates steady');
      var zhR2 = falling ? '分析师下调预期'
        : (rising ? ('分析师仍在上调' + (nA ? '（' + nA + ' 位覆盖）' : '')) : '预期平稳');
      out.estimates = { state: st2, en: enR2, zh: zhR2,
        chip: falling ? { cls: '', en: 'Estimates falling', zh: '盈利预期下调' } : null };
    } else if (isNum(sue)) {
      out.estimates = { state: sue < -1 ? 'watch' : 'ok',
        en: sue < -1 ? 'recent earnings missed' : 'recent earnings in line or better',
        zh: sue < -1 ? '近期财报不及预期' : '近期财报符合或优于预期', chip: null };
    } else out.estimates = { state: 'na', en: NA.en, zh: NA.zh, chip: null };
    // --- balance sheet (solvency / accounting) -------------------------
    var fin = (j && j.financials) || null, aq = (j && j.accounting_quality) || null;
    var dta = fin && fin.debt_to_assets, fcf = fin && fin.fcf_margin;
    var aqv = aq && aq.verdict;
    if (fin || aq) {
      var warn = (aqv === 'warn') || (isNum(dta) && dta > 0.6);
      var watchB = (aqv === 'watch') || (isNum(aq && aq.n_caution) && aq.n_caution >= 2);
      var st3 = warn ? 'elev' : (watchB ? 'watch' : 'ok');
      var lowDebt = isNum(dta) && dta < 0.35, strongCash = isNum(fcf) && fcf > 0.1;
      var enR3 = warn ? 'debt or accounting flags to check'
        : (lowDebt && strongCash ? 'little debt, strong cash generation'
          : lowDebt ? 'little debt' : strongCash ? 'strong cash generation' : 'balance sheet ordinary');
      var zhR3 = warn ? '债务或会计存在需关注项'
        : (lowDebt && strongCash ? '负债很低，现金流强劲'
          : lowDebt ? '负债较低' : strongCash ? '现金流强劲' : '资产负债一般');
      out.balance = { state: st3, en: enR3, zh: zhR3,
        chip: warn ? { cls: '', en: 'Debt watch', zh: '债务关注' } : null };
    } else out.balance = { state: 'na', en: NA.en, zh: NA.zh, chip: null };
    // --- who's selling (positioning + smart money) ---------------------
    var pos = (j && j.positioning) || null, sm = (j && j.smart_money) || null;
    var shortObj = pos && pos.short, sflow = pos && pos.short_flow, ins = pos && pos.insider;
    if (pos || sm) {
      var shortRising = sflow && isNum(sflow.trend_pp) && sflow.trend_pp > 1;
      var shortHigh = shortObj && isNum(shortObj.pct_float) && shortObj.pct_float > 0.1;
      var smSelling = sm && isNum(sm.n_selling) && isNum(sm.n_buying) && sm.n_selling > sm.n_buying + 1;
      var insiderSell = insiderCluster(ins);
      var elev = shortRising || insiderSell;
      var watchS = shortHigh || smSelling;
      var st4 = elev ? 'elev' : (watchS ? 'watch' : 'ok');
      var enR4 = insiderSell ? 'insider selling cluster'
        : shortRising ? 'short interest rising'
          : smSelling ? 'more smart-money exits than adds'
            : shortHigh ? 'elevated short interest' : 'shorts near lows; no insider cluster';
      var zhR4 = insiderSell ? '内部人集中卖出'
        : shortRising ? '空头持续增加'
          : smSelling ? '机构减持多于增持'
            : shortHigh ? '空头占比偏高' : '空头接近低位；无内部人集中卖出';
      var chip4 = insiderSell ? { cls: '', en: 'Insiders selling', zh: '内部人卖出' }
        : (shortRising || shortHigh) ? { cls: '', en: 'Shorts rising', zh: '空头增加' } : null;
      out.selling = { state: st4, en: enR4, zh: zhR4, chip: chip4 };
    } else out.selling = { state: 'na', en: NA.en, zh: NA.zh, chip: null };
    // --- rate sensitivity (macro) --------------------------------------
    var ms = (j && j.macro_sensitivity) || null;
    if (ms && ms.tier != null) {
      var sensitive = ms.tier === 'high' && isNum(ms.rate_beta) && Math.abs(ms.rate_beta) > 0.3;
      var headwind = ms.regime === 'headwind';
      out.rates = { state: (sensitive && headwind) ? 'watch' : 'ok',
        en: sensitive ? ('moves with rates' + (headwind ? ' — a headwind now' : '')) : 'not very rate-sensitive',
        zh: sensitive ? ('对利率敏感' + (headwind ? '——当前为逆风' : '')) : '对利率不太敏感',
        chip: sensitive ? { cls: 'info', en: 'Rate-sensitive', zh: '利率敏感' } : null };
    } else out.rates = { state: 'na', en: NA.en, zh: NA.zh, chip: null };
    return out;
  }

  function insiderCluster(ins) {
    if (!ins) return false;
    // insider block is a passthrough; look for a net-sell / cluster signal defensively
    var n = ins.n_sellers != null ? ins.n_sellers : ins.sellers;
    if (isNum(n) && n >= 3) return true;
    if (ins.cluster === true || ins.net === 'sell') return true;
    return false;
  }

  // ---- Risk Desk role ladder (§7) — first match top-down; review labels only.
  // Rungs (asc): info < monitor < review < tighten < trim_review < exit_review.
  // Badge renders ONLY at ≥ review. `tighten` has no distinct review label in §7,
  // so it surfaces under the plain "Review" label (it is above review in severity;
  // the distinct take-profit / exit labels are reserved for those two named rungs).
  function roleBadge(lanes) {
    function elev(k) { return lanes[k] && lanes[k].state === 'elev'; }
    function watch(k) { return lanes[k] && lanes[k].state === 'watch'; }
    var pt = elev('price_trend'), ev = elev('events'), est = elev('estimates'),
      bal = elev('balance'), sell = elev('selling'), rat = elev('rates');
    // "extension elevated" (Risk Desk §7) = the name flags as stretched/extended.
    // In the L1 lane model that is the stretch WATCH state (extended flag).
    var ext = (lanes.stretch && (lanes.stretch.state === 'watch' || lanes.stretch.state === 'elev'));
    // exit_review: solvency critical + downtrend, OR earnings-risk + downtrend
    if ((bal && pt) || (est && pt)) return label('exit');
    // trim_review: extended + a second pressure (near-term event / distribution / rate headwind)
    if (ext && (ev || sell || rat)) return label('trim');
    // tighten -> "Review": downtrend + (event | rate pressure)
    if (pt && (ev || rat)) return label('review');
    // review: ≥2 elevated lanes across independent groups
    var groups = [pt || ext, ev, est || bal, sell, rat];
    var nElev = groups.filter(Boolean).length;
    if (nElev >= 2) return label('review');
    return null;   // monitor / info -> quiet name, no badge
    function label(kind) {
      if (kind === 'exit') return { kind: 'exit', en: 'Exit review', zh: '离场复查' };
      if (kind === 'trim') return { kind: 'trim', en: 'Take-profit review', zh: '止盈复查' };
      return { kind: 'review', en: 'Review', zh: '复查' };
    }
  }

  /* The lane state token. It lives HERE, beside its only caller, because it used to sit
     700 lines away inside the braid-hero block — and when W2 deleted that block it took
     this function with it. `laneRowsHTML` then threw ReferenceError on every call,
     portfolio.js's try/catch swallowed it, and the drawer printed its honest-null line:
     the per-name lane read shipped 100% dark for every signed-in user, disguised as a
     data gap. tests/test_watchlist_workspace_js.py now calls laneRows on a real payload
     and asserts a non-empty string, so a catch can never hide this class again. */
  function stateToken(s) {
    if (s === 'ok') return 'OK';
    if (s === 'watch') return te('WATCH', '关注');
    if (s === 'elev') return te('ELEVATED', '升高');
    return te('n/a', '未覆盖');
  }

  // The seven lane rows as HTML — the ONE renderer, shared by the watchlist cards and
  // the portfolio assessment drawer (portfolio.js calls it through window.WRI). Keeping
  // a single implementation is why the drawer and the card can never drift apart.
  function laneRowsHTML(j) {
    var lanes = laneRead(j);
    return LANES.map(function (k) {
      var L = lanes[k], lbl = LANE_LABEL[k];
      return '<div class="wri-lrow"><span class="ln">' + te(lbl.en, lbl.zh) + '</span>' +
        '<span class="st ' + L.state + '">' + stateToken(L.state) + '</span>' +
        '<span class="rs">' + te(esc(L.en), esc(L.zh)) + '</span></div>';
    }).join('');
  }

  // ---- date helpers ---------------------------------------------------
  function daysUntil(iso) {
    var d = parseISO(iso); if (!d) return null;
    var ms = d.getTime() - Date.now();
    return Math.round(ms / 86400000);
  }
  function parseISO(iso) {
    if (!iso) return null;
    var m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  }
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function fmtDate(iso) { var d = parseISO(iso); return d ? MON[d.getUTCMonth()] + ' ' + d.getUTCDate() : iso; }
  function fmtDateZh(iso) { var d = parseISO(iso); return d ? (d.getUTCMonth() + 1) + '月' + d.getUTCDate() + '日' : iso; }
  function timeWord(t) { return t === 'pre-market' ? 'before the open' : t === 'after-hours' ? 'after close' : ''; }
  function timeWordZh(t) { return t === 'pre-market' ? '盘前' : t === 'after-hours' ? '盘后' : ''; }

  // =========================================================================
  //  Transmission CHAINS lane (TXI W4) — INFO-tier context from
  //  transmission_chains.json. A name that sits in an ARMED chain's blast radius
  //  gets a deliberately COOL info chip + a drawer read. Display-only WATCH
  //  context: never a signal, size, or call. All logic below is pure + DOM-free
  //  (exported for node tests); the wiring lives in loadChains and the publisher.
  // =========================================================================
  var CHAIN_ARMED = { arming: 1, propagating: 1, expressed: 1 };
  // most-progressed first (a name in several chains leads with the furthest along)
  var CHAIN_RANK = { expressed: 0, propagating: 1, arming: 2 };
  var CHAIN_STATE_WORD = {
    arming: { en: 'arming', zh: '触发中' }, propagating: { en: 'propagating', zh: '传导中' },
    expressed: { en: 'expressed', zh: '已兑现' }
  };

  // plain driver word for a chain id (the "{driver} risk building" chip). Falls back to
  // the chain's EN label's first word so a new chain id still reads sensibly.
  function chainDriver(m) {
    var id = (m && m.id) || '';
    if (/^dollar/.test(id)) return { en: 'Dollar', zh: '美元' };
    if (/^oil/.test(id)) return { en: 'Oil→rates', zh: '油价利率' };
    if (/^credit/.test(id)) return { en: 'Credit-spread', zh: '信用利差' };
    if (/^vol/.test(id)) return { en: 'Volatility', zh: '波动率' };
    var lab = (m && m.label) || {};
    var en = String(lab.en || id).split(' ')[0];
    return { en: en, zh: String(lab.zh || en).slice(0, 4) };
  }

  // invert the published subset ({chains:[{id,label,state,hops,blast:{ch:{names,...}}}]})
  // into { TICKER: [membership,...] } — ARMED chains only. A membership carries the chain
  // id/label/state, its confirmed/total hop counts, and the channel it was caught by (with
  // the channel label + coverage counts for the drawer read). Deduped per chain×channel.
  function chainIndex(subset) {
    var idx = {};
    var chains = (subset && subset.chains) || [];
    for (var i = 0; i < chains.length; i++) {
      var c = chains[i] || {};
      if (!CHAIN_ARMED[c.state]) continue;
      var hops = c.hops || [];
      var nh = hops.length, conf = 0;
      for (var h = 0; h < hops.length; h++) if (hops[h] && hops[h].confirmed) conf++;
      var blast = c.blast || {};
      for (var flag in blast) {
        if (!Object.prototype.hasOwnProperty.call(blast, flag)) continue;
        var ch = blast[flag] || {}, names = ch.names || [];
        for (var n = 0; n < names.length; n++) {
          var tk = String(names[n] || '').toUpperCase();
          if (!tk) continue;
          var bucket = idx[tk] || (idx[tk] = []);
          var dup = false;
          for (var b = 0; b < bucket.length; b++) if (bucket[b].id === c.id && bucket[b].channel === flag) { dup = true; break; }
          if (dup) continue;
          bucket.push({
            id: c.id, label: c.label || {}, state: c.state,
            links_confirmed: conf, n_hops: nh,
            channel: flag, channel_label: ch.label || {},
            channel_n: ch.n, unevaluable: ch.unevaluable
          });
        }
      }
    }
    return idx;
  }

  // the furthest-progressed chain membership for a name (expressed > propagating > arming;
  // ties broken by more links confirmed). null when the name is in no armed chain.
  function furthestChain(memberships) {
    if (!memberships || !memberships.length) return null;
    var best = null;
    for (var i = 0; i < memberships.length; i++) {
      var m = memberships[i];
      if (best === null) { best = m; continue; }
      var rm = CHAIN_RANK[m.state], rb = CHAIN_RANK[best.state];
      if (rm < rb || (rm === rb && (m.links_confirmed || 0) > (best.links_confirmed || 0))) best = m;
    }
    return best;
  }

  // the ONE hero-rail sentence: fires only when some chain is propagating|expressed AND at
  // least one of the book's names sits in that chain's blast. Returns {en,zh,id} or null.
  // Picks the most-progressed such chain; m = count of the book's names downstream of it.
  function railChainSentence(idx, bookTickers) {
    if (!idx || !bookTickers || !bookTickers.length) return null;
    var perChain = {};   // id -> {state, label, names:Set-ish}
    for (var i = 0; i < bookTickers.length; i++) {
      var tk = String(bookTickers[i] || '').toUpperCase();
      var ms = idx[tk]; if (!ms) continue;
      for (var j = 0; j < ms.length; j++) {
        var m = ms[j];
        if (m.state !== 'propagating' && m.state !== 'expressed') continue;
        var e = perChain[m.id] || (perChain[m.id] = { state: m.state, label: m.label, names: {} });
        e.names[tk] = 1;
      }
    }
    var pick = null;
    for (var id in perChain) {
      if (!Object.prototype.hasOwnProperty.call(perChain, id)) continue;
      var c = perChain[id];
      if (pick === null || CHAIN_RANK[c.state] < CHAIN_RANK[pick.state]) pick = { id: id, state: c.state, label: c.label, m: Object.keys(c.names).length };
    }
    if (!pick) return null;
    var nm = (pick.label && pick.label.en) || pick.id;
    var nmz = (pick.label && pick.label.zh) || nm;
    return {
      id: pick.id,
      en: 'A ' + nm + ' cascade is propagating — ' + pick.m + ' of your names sit downstream',
      zh: nmz + '传导推进中——你的 ' + pick.m + ' 只持仓位于下游'
    };
  }

  // the drawer read for every armed chain a name sits downstream of (most-progressed first).
  // A plain review line + a coverage note; receipts ride data-tip-*, never title=. Returns an
  // HTML string of .wri-lrow rows (empty when the name is in no armed chain). PURE.
  function chainDrawerRows(memberships) {
    if (!memberships || !memberships.length) return '';
    var ms = memberships.slice().sort(function (a, b) {
      var r = CHAIN_RANK[a.state] - CHAIN_RANK[b.state];
      return r !== 0 ? r : (b.links_confirmed || 0) - (a.links_confirmed || 0);
    });
    var out = '';
    for (var i = 0; i < ms.length; i++) {
      var m = ms[i];
      var nm = (m.label && m.label.en) || m.id, nmz = (m.label && m.label.zh) || nm;
      var chn = (m.channel_label && m.channel_label.en) || m.channel;
      var chnz = (m.channel_label && m.channel_label.zh) || chn;
      var k = m.links_confirmed || 0, n = m.n_hops || 0;
      var cov = isNum(m.channel_n) ? (m.channel_n + ' names' + (isNum(m.unevaluable) ? ', ' + m.unevaluable + ' unevaluable' : '')) : 'coverage partial';
      var covz = isNum(m.channel_n) ? (m.channel_n + ' 只' + (isNum(m.unevaluable) ? '，' + m.unevaluable + ' 只无法评估' : '')) : '口径部分覆盖';
      var sw = CHAIN_STATE_WORD[m.state] || { en: m.state, zh: m.state };
      var readEn = 'Sits downstream of the ' + esc(nm) + ' cascade — ' + k + ' of ' + n +
        ' links confirmed (' + esc(chn) + ', ' + esc(cov) + '). Early monitor — not a signal.';
      var readZh = '处于' + esc(nmz) + '传导下游——已确认 ' + k + '/' + n + ' 环节（' + esc(chnz) +
        '，' + esc(covz) + '）。早期监测——非信号。';
      var tipEn = 'The chain is ' + esc(sw.en) + '. A named channel screen (' + esc(chn) +
        ') places this name in the blast radius; a missing field is neither in nor out. Display-only WATCH context — never a signal, size, or call.';
      var tipZh = '该链' + esc(sw.zh) + '。命名通道筛选（' + esc(chnz) +
        '）将此股纳入波及范围；字段缺失既不纳入也不排除。仅供观察的上下文——绝非信号、仓位或指令。';
      out += '<div class="wri-lrow"><span class="ln">' + te('Transmission', '传导链') +
        '<span class="wri-q" tabindex="0" data-tip-en="' + tipEn + '" data-tip-zh="' + tipZh + '">?</span></span>' +
        '<span class="st info">' + te('WATCH', '关注') + '</span>' +
        '<span class="rs">' + te(readEn, readZh) + '</span></div>';
    }
    return out;
  }

  // =========================================================================
  //  L3 — regime rail (window.WRI_REGIME crossed with the book's market beta)
  // =========================================================================
  // state ramp tint (never --up/--down; zh-flip trap). state from risk_radar.
  var STATE_TINT = { calm: 'ok', normal: 'ok', watch: 'tilt', caution: 'tilt', elevated: 'conc', high: 'conc', extreme: 'one' };
  /* W2: the L3 regime read is no longer a rail of its own — the pinned design gives
     it the book read's SUBLINE ("Quiet tape · nothing crossed a line overnight"), one
     quiet line above the sentence it qualifies. This function therefore returns HTML
     for portfolio.js to place rather than painting a host of its own. */
  function regimeSentence(bookBeta) {
    var R = window.WRI_REGIME;
    if (!R || (!R.dominant_label_en && !R.state)) return '';
    var tint = STATE_TINT[(R.state || '').toLowerCase()] || 'tilt';
    var domEn = R.dominant_label_en || 'Market read', domZh = R.dominant_label_zh || R.dominant_label_en || '市场状态';
    var stateEn = stateWord(R.state, 'en'), stateZh = stateWord(R.state, 'zh');
    // book beta sentence (client) — only when we have a market beta to show
    var betaFrag = '';
    if (isNum(bookBeta)) {
      var bx = (Math.round(bookBeta * 10) / 10);
      betaFrag = ' · ' + '<span>' +
        te('your book moves about <b class="num">' + bx + '×</b> the market',
          '你的组合波动约为大盘的 <b class="num">' + bx + '×</b>') + '</span>';
    }
    // ONE appended chain sentence — only when a chain is propagating|expressed AND ≥1 book
    // name sits downstream of it. Links to the Cascade Monitor. The rail's single-line law
    // wins: this rides at the end, after the base state + beta, so the base read always shows.
    var chainFrag = '';
    var cs = railChainSentence(CHAINS_IDX, Object.keys(BOOK_SHARES));
    if (cs) {
      chainFrag = ' · ' + '<span class="wri-rail-chain">' +
        te(esc(cs.en), esc(cs.zh)) + ' <a href="transmission.html">' +
        te('cascade →', '传导链 →') + '</a></span>';
    }
    // the regime artifact reads the US tape; say so once the user holds other markets
    var scope = multiBook() ? te('US tape · ', '美股行情 · ') : '';
    return scope +
      te(esc(domEn) + ' — market on ' + esc(stateEn), esc(domZh) + '——市场' + esc(stateZh)) +
      betaFrag + chainFrag;
  }
  // tint is computed above and deliberately not used for ink here: the subline is a
  // quiet muted line in the pinned design, and a state ramp on it would be a fifth
  // reserved hue on a page whose palette decision allows four.
  function renderRail(bookBeta) { return regimeSentence(bookBeta); }
  function stateWord(s, l) {
    s = (s || '').toLowerCase();
    var m = {
      caution: { en: 'caution', zh: '谨慎' }, watch: { en: 'watch', zh: '观察' },
      elevated: { en: 'alert', zh: '警戒' }, high: { en: 'high alert', zh: '高度警戒' },
      extreme: { en: 'high alert', zh: '高度警戒' }, calm: { en: 'calm', zh: '平静' },
      normal: { en: 'normal footing', zh: '正常状态' }
    };
    var w = m[s] || { en: s || 'watch', zh: s || '观察' };
    return l === 'zh' ? w.zh : w.en;
  }

  // =========================================================================
  //  L2 — Book Risk hero (verdict + patch-bay + sub-cards + footnote)
  // =========================================================================
  var W = 1000, TOPY = 24, BENDY = 92, RAILY = 150, LABY = 172, LABY2 = 185;
  var animatedOnce = false;

  // Build the render model for BOTH lenses from RiskCore, then paint the active one.
  /* A non-modeled book (cn/hk/ca/intl): the USD factor stack does not cover these
     names, so the hero collapses to ONE honest line instead of a verdict computed
     from a different book's names (WRI-R6 / gate 6). Their per-name signals are
     unaffected — they render in full below, which is what the line says. */
  /* A non-modeled book (cn/hk/ca/intl): the USD factor stack does not cover these
     names, so `publishBook` above publishes coverage-only and the workspace draws the
     seam's risk rail as a lock shell. There is no separate "book note" render any
     more — the honest statement is the coverage line the book read already carries. */

  /* W2 — THE RISK PUBLISHER.

     The braid hero is superseded by the Book Seam (DESIGN_NOTES §1): one signature,
     drawn in ONE place (watchlist.js `WS.seam`), fed from here. This function no
     longer paints — it computes the model read and hands portfolio.js a payload to
     compose. Nothing about the arithmetic changed; only who owns the pixels.

     The honesty rule this file is now responsible for: `modeledN` travels WITH the
     bet count, so the headline can never print the model's subset size as if it were
     the user's list size. That was the specific defect the pinned design calls out —
     "12 positions move like 3 bets" while the model had only ever seen 11 of them. */
  /* Plain-word names for the dominant idea, for the ONE sentence that says what the
     book is leaning on. The factor labels above are the right words inside a factor
     table and the wrong words here: "Most of it is one idea — market." is not a
     sentence a reader learns anything from. Glance tier gets the idea, not the key. */
  var IDEA = {
    mkt:    ['the market itself',      '大盘本身'],
    growth: ['big technology',         '大型科技股'],
    size:   ['smaller companies',      '中小盘'],
    rates:  ['where interest rates go', '利率走向'],
    usd:    ['the US dollar',          '美元'],
    oil:    ['oil and energy',         '石油与能源'],
    china:  ['China',                  '中国'],
    btc:    ['bitcoin',                '比特币'],
    gold:   ['gold',                   '黄金']
  };

  function publishBook(data, weights) {
    var universe = modeledUniverse(weights.universe);
    var wmap = weights.wmap;
    var wIn = {};
    universe.forEach(function (t) { var v = wmap[t]; wIn[t] = isNum(v) && v > 0 ? v : 1; });

    /* The active BOOK CHIP is deliberately not consulted here. Under the pinned
       semantics (DESIGN_NOTES §7d) the chips filter the holdings TABLE VIEW only —
       the book read, the attention stack and the Risk Center always describe the whole
       portfolio. Scoping this read to the chip meant selecting "Hong Kong" silently
       emptied the book read above it, which is the same class of defect as a filter
       that shortens a list without saying so. The USD-only guard that matters is
       `modeledUniverse`, applied to the weights, and it is applied above. */

    var RR = RiskCore.read(data, wIn);
    var cov = (RR.calm && RR.calm.coverage) || RiskCore.coverage(data, wIn);

    /* The Scenario Lab compares against THIS book under THIS lens. Caching the two
       here — rather than re-deriving them when the user runs a comparison — is what
       makes "before" in the lab and the figures in the tabs the same object. */
    LAST_WMAP = wIn;
    LAST_LENS = RR.defaultLens === 'stress' ? 'stress' : 'calm';

    if (!RR.calm.ok) {
      // a thin/uncovered book has no read to cache — drop it, so a later hydration
      // wave cannot republish tab strings describing a book we no longer have
      LAST_READ = null;
      publish({ shares: {}, covered: {}, bets: null, modeledN: 0,
                regime: regimeSentence(null), rcTabs: null, labHTML: labIntroHTML() });
      return;
    }

    var b = RR.hasStress ? RR.stress : RR.calm;
    var active = RR.calm;                       // the seam describes the ALL-DAYS read
    var shares = {}, covered = {};
    (active.held || []).forEach(function (t) {
      shares[t] = active.mctrShare[t];
      covered[t] = true;
    });

    // cluster / ballast membership — the biggest factor group is the dominant idea;
    // anything that OFFSETS the book (negative MCTR share) is its ballast. Both come
    // straight from RiskCore; nothing is re-ranked here.
    var groups = clustersFor(active);
    var cluster = {}, ballast = {};
    if (groups.length) {
      (groups[0].members || []).forEach(function (t) { cluster[t] = 1; });
      groups.forEach(function (g, i) {
        if (i === 0) return;
        g.members.forEach(function (t) {
          if ((active.mctrShare[t] || 0) < 0 || g.hedge) ballast[t] = 1;
        });
      });
    }
    // a book with no negative-MCTR name still has a smallest group; call the two
    // smallest contributors ballast so the seam has a readable third role
    if (!Object.keys(ballast).length && active.held.length >= 4) {
      active.held.slice().sort(function (x, y) {
        return Math.abs(active.mctrShare[x]) - Math.abs(active.mctrShare[y]);
      }).slice(0, 2).forEach(function (t) { if (!cluster[t]) ballast[t] = 1; });
    }

    var clamp = enbClamp(active.enb, active.held.length);
    var lead = groups.length ? groups[0] : null;
    var leadShare = lead ? Math.round(lead.share * 100) : 0;
    var because = '';
    if (lead && lead.members.length >= 2) {
      var ideaEn = lead.fk && IDEA[lead.fk] ? IDEA[lead.fk][0]
                                            : lead.members.slice(0, 2).join(' and ');
      var ideaZh = lead.fk && IDEA[lead.fk] ? IDEA[lead.fk][1]
                                            : lead.members.slice(0, 2).join('和');
      because = te('Most of it is one idea — <b>' + esc(ideaEn) + '</b>.',
                   '大部分压在同一件事上 —— <b>' + esc(ideaZh) + '</b>。');
      var ballNames = Object.keys(ballast).slice(0, 2);
      if (ballNames.length) {
        because += ' ' + te(
          esc(ballNames.join(' and ')) + (ballNames.length === 1 ? ' is what keeps' : ' are what keep') +
            ' this book from being a single position.',
          '是' + esc(ballNames.join('和')) + '让这本账簿没有变成一笔仓位。');
      }
    }

    /* The seam CAPTION is deliberately NOT built here. Its two figures — the
       cluster's share of the money and of the risk — must come from the same
       distribution the two rails are drawn from, and that distribution lives with
       the items in portfolio.js. Computing the money side off the modeled weight
       map here produced a caption that said 51% over a bracket that drew 40%: one
       claim, two denominators, one line apart. */

    var out = {
      shares: shares, covered: covered,
      bets: clamp.bets, modeledN: active.held.length,
      cluster: cluster, ballast: ballast,
      because: because, clusterN: lead ? lead.members.length : 0,
      regime: regimeSentence(active.bookBeta && active.bookBeta.mkt)
    };
    /* All six tabs are built from the SAME two reads (`active` = the all-days book,
       `RR` = both lenses) in ONE pass, so no two tabs can describe different books.
       The workspace picks which string to paint; it never recomputes — the same split
       the seam already uses, for the same reason. */
    LAST_READ = { RR: RR, active: active, cov: cov };
    var tabs = tabPayload(LAST_READ);
    out.concHTML = tabs.concHTML;
    out.rcTabs = tabs.rcTabs;
    out.labHTML = tabs.labHTML;
    publish(out);
  }

  function publish(payload) {
    if (window.PF && window.PF.setBookRisk) { try { window.PF.setBookRisk(payload); } catch (e) {} }
    if (window.WS && window.WS.setRisk) {
      try {
        window.WS.setRisk({
          concHTML: payload.concHTML || '',
          rcTabs: payload.rcTabs || null,
          labHTML: payload.labHTML || ''
        });
      } catch (e) {}
    }
  }

  /* Risk Center → Concentration. The seam already carries the CLUSTER claim, so this
     tab deliberately carries the SINGLE-NAME one — one dominant idea per section, no
     duplicate content (DESIGN_NOTES §5.5). Bars share ONE scale, printed once, with
     the number beside every bar as the truth. */
  function concentrationHTML(b, cov) {
    if (!b || !b.ok || !b.held.length) return '';
    var ranked = b.held.slice().sort(function (x, y) {
      return Math.abs(b.mctrShare[y]) - Math.abs(b.mctrShare[x]);
    });
    var top = ranked[0];
    var topShare = Math.abs(b.mctrShare[top] || 0);
    var SCALE = 0.30;                     // a full bar is 30% of book risk
    var rows = ranked.slice(0, 5).map(function (t) {
      var sh = Math.abs(b.mctrShare[t] || 0);
      var hedge = (b.mctrShare[t] || 0) < 0;
      return '<div class="conc-row' + (hedge ? ' is-ballast' : '') + '">' +
        '<span class="who">' + esc(t) + '</span>' +
        '<span class="track"><span style="width:' + Math.min(100, sh / SCALE * 100).toFixed(0) + '%"></span></span>' +
        '<span class="pct fig">' + Math.round(sh * 100) + '%</span></div>';
    }).join('');

    var claim = te(
      'One name, ' + esc(top) + ', carries <span class="fig">' + Math.round(topShare * 100) +
        '%</span> of this book&rsquo;s risk.',
      '单是 ' + esc(top) + ' 一只，就扛下了本账簿 <span class="fig">' + Math.round(topShare * 100) +
        '%</span> 的风险。');

    var unmodeled = (cov && cov.unmodeled) || [];
    return '<p class="rc-claim">' + claim + '</p>' +
      '<p class="rc-note">' + te(
        'Each bar is that name&rsquo;s share of the book&rsquo;s modeled risk, on one shared scale.',
        '每根条形是该股在本账簿模型风险中的占比，统一刻度。') + '</p>' +
      '<div class="conc">' + rows + '</div>' +
      '<p class="rc-note" style="margin-top:12px">' + te(
        'Scale: a full bar is <span class="fig">30%</span> of book risk.',
        '刻度：满格代表占本账簿风险 <span class="fig">30%</span>。') +
      (unmodeled.length ? ' ' + te(
        esc(unmodeled.join(', ')) + ' ' + (unmodeled.length === 1 ? 'is' : 'are') + ' not on this list — outside the model.',
        esc(unmodeled.join('、')) + ' 不在此列 —— 不在模型内。') : '') + '</p>';
  }

  // =========================================================================
  //  W3 — the remaining five Risk Center tabs, over the SAME RiskCore reads.
  //
  //  Nothing here computes a new statistic. Every figure below is a value
  //  RiskCore already published (mctrShare, W, rho, twinPairs, factorShare,
  //  idioShare, enb under each lens, coverage) or a comparison of two of them.
  //  The tabs differ in WHICH published distribution they point at, never in the
  //  arithmetic — which is why no two tabs can disagree about the same book.
  //
  //  One dominant idea per tab, and no tab repeats another's claim:
  //    Concentration  the single largest name's share of the risk
  //    Correlation    how closely any two names actually move together
  //    Factors        which outside force the whole book leans on
  //    Stress         whether that changes on the days the market falls
  //    Events         when the book's names next report
  //    Weak links     risk PER DOLLAR — who overpays, and who pulls the other way
  // =========================================================================

  /* Read LAZILY, never at load: this file and risk_core.js are two separate <script>
     tags, so a module-level `window.RiskCore.TWIN_RHO` would resolve to the fallback on
     whichever load order the browser happens to give us and then silently disagree with
     the engine that actually drew the clusters. */
  function twinLine() {
    var R = (typeof window !== 'undefined') && window.RiskCore;
    return (R && isNum(R.TWIN_RHO)) ? R.TWIN_RHO : 0.70;
  }

  // The shared shape of a tab: one claim sentence, one how-to-read line, a compact
  // visual, then the honest footer. `claim`/`note`/`foot` are already-bilingual HTML.
  function tabHTML(claim, note, body, foot) {
    return '<p class="rc-claim">' + claim + '</p>' +
      (note ? '<p class="rc-note">' + note + '</p>' : '') +
      (body || '') +
      (foot ? '<p class="rc-note" style="margin-top:12px">' + foot + '</p>' : '');
  }
  // the "we cannot read this yet" body — a plain sentence, never an empty panel
  function tabNull(en, zh) { return '<p class="rc-soon">' + te(en, zh) + '</p>'; }

  /* COVERAGE FOOTER — the same two disclosures on every tab that reads the factor
     model, because a reader who lands on Stress must learn what it does not cover
     without first visiting Concentration. Names the model has no read for, and the
     markets the model does not price at all. Never a cross-currency total: the
     non-US books are named as SEPARATE reads, not folded into these figures. */
  function coverageFoot(cov) {
    var un = (cov && cov.unmodeled) || [];
    var out = '';
    if (un.length) {
      var shown = un.slice(0, 6), more = un.length - shown.length;
      out += te(
        esc(shown.join(', ')) + (more > 0 ? ' and ' + more + ' more' : '') + ' ' +
          (un.length === 1 && !more ? 'is' : 'are') +
          ' not in these figures — the nightly model has no read for ' +
          (un.length === 1 && !more ? 'it' : 'them') + '. ' +
          (un.length === 1 && !more ? 'Its' : 'Their') + ' own price signals still show in the table above.',
        esc(shown.join('、')) + (more > 0 ? ' 等 ' + un.length + ' 只' : '') +
          ' 不在以上数字里 —— 每晚的模型没有它们的读数。它们自己的价格信号仍在上方表格中。');
    }
    if (multiBook()) {
      out += (out ? ' ' : '') + te(
        'These reads cover your US-listed names. Positions in other markets keep their own signals in the table and are never added into one number across currencies.',
        '以上读数覆盖你的美股持仓。其他市场的持仓在表格里保留各自的信号，绝不会跨币种加总成一个数字。');
    }
    return out;
  }

  // ---- 2. CORRELATION -----------------------------------------------------
  /* The one question: which two of these names are really the same trade?
     Source: RiskCore's implied pairwise correlation and its ρ ≥ 0.70 clusters —
     both already computed inside book(). The honest case this surface must handle
     is the COMMON one: on an orthogonalized factor model with real per-name idio
     vol, most equity pairs land well below 0.70. "No pair crosses the line" is a
     finding, not an empty state, and printing the closest pair anyway is what
     stops it from reading as "these names are unrelated". */
  function correlationHTML(b, cov) {
    if (!b || !b.ok || b.held.length < 2) return '';
    var held = b.held, pairs = [];
    for (var i = 0; i < held.length; i++) {
      for (var j = i + 1; j < held.length; j++) {
        pairs.push({ a: held[i], c: held[j], r: b.rho(held[i], held[j]) });
      }
    }
    pairs.sort(function (x, y) { return y.r - x.r; });
    if (!pairs.length) return '';

    // the ρ ≥ 0.70 groups, from RiskCore's own connected components (size ≥ 2 only)
    var groups = (b.clusters || []).filter(function (g) { return g.members.length >= 2; });
    var top = pairs[0];
    var claim, note;
    if (groups.length) {
      var g0 = groups[0], names = g0.members;
      claim = te(
        '<b>' + esc(names.join(' and ')) + '</b> move almost as one position — you own ' +
          'the same trade <span class="fig">' + names.length + '</span> times.',
        '<b>' + esc(names.join('、')) + '</b> 几乎是同一笔仓位 —— 同一笔交易你持有了 <span class="fig">' +
          names.length + '</span> 次。');
      note = te(
        'A pair at <span class="fig">1.00</span> would move identically. We draw the line at <span class="fig">0.70</span>: above it, two names stop being two.',
        '两只票若为 <span class="fig">1.00</span> 即完全同步。我们以 <span class="fig">0.70</span> 为界：越过这条线，两只票就不再算两只。');
    } else {
      claim = te(
        'Nothing in this book moves in lockstep. The closest pair is <b>' + esc(top.a) +
          '</b> and <b>' + esc(top.c) + '</b>, at <span class="fig">' + top.r.toFixed(2) + '</span>.',
        '这本账簿里没有完全同步的持仓。最接近的一对是 <b>' + esc(top.a) + '</b> 与 <b>' +
          esc(top.c) + '</b>，为 <span class="fig">' + top.r.toFixed(2) + '</span>。');
      note = te(
        'A pair at <span class="fig">1.00</span> would move identically; we draw the line at <span class="fig">0.70</span>. Below it these names still lean the same way — they just do not move as one.',
        '两只票若为 <span class="fig">1.00</span> 即完全同步；我们以 <span class="fig">0.70</span> 为界。低于这条线，它们仍会同向倾斜 —— 只是不会作为一只票波动。');
    }

    var LINE = twinLine();
    var rows = pairs.slice(0, 6).map(function (p) {
      var strong = p.r >= LINE;
      return '<div class="pair-row' + (strong ? ' is-twin' : '') + '">' +
        '<span class="who">' + esc(p.a) + ' · ' + esc(p.c) + '</span>' +
        '<span class="track"><span style="width:' +
          Math.max(0, Math.min(100, p.r * 100)).toFixed(0) + '%"></span></span>' +
        '<span class="pct fig">' + p.r.toFixed(2) + '</span></div>';
    }).join('');

    var foot = te('The closest <span class="fig">' + Math.min(6, pairs.length) +
        '</span> of <span class="fig">' + pairs.length + '</span> pairs. Full bar is <span class="fig">1.00</span>.',
      '共 <span class="fig">' + pairs.length + '</span> 对中最接近的 <span class="fig">' +
        Math.min(6, pairs.length) + '</span> 对。满格为 <span class="fig">1.00</span>。');
    var cf = coverageFoot(cov);
    if (cf) foot += ' ' + cf;
    return tabHTML(claim, note, '<div class="conc">' + rows + '</div>', foot);
  }

  // ---- 3. FACTORS & MACRO -------------------------------------------------
  /* The one question: which outside force is this book actually leaning on?
     Source: factorShare (Euler variance shares) + idioShareTotal, both published.
     The rate line reads the book's own rates beta and the rates share — the two
     things that decide whether "where interest rates go" matters to this book. */
  function factorsHTML(b, cov) {
    if (!b || !b.ok) return '';
    var ranked = (b.rankedFactors || []).filter(function (k) { return (b.factorShare[k] || 0) > 0.005; });
    var topK = b.topFactor, topS = b.topFactorShare || 0;
    var idio = b.idioShareTotal || 0;
    var ideaEn = IDEA[topK] ? IDEA[topK][0] : flabel(topK);
    var ideaZh = IDEA[topK] ? IDEA[topK][1] : flabel(topK);

    var claim = (topS >= idio)
      ? te('About <span class="fig">' + pct0(topS) + '</span> of what moves this book is one outside force — <b>' +
             esc(ideaEn) + '</b>.',
           '本账簿约 <span class="fig">' + pct0(topS) + '</span> 的波动来自同一股外部力量 —— <b>' +
             esc(ideaZh) + '</b>。')
      : te('No single outside force runs this book — <span class="fig">' + pct0(idio) +
             '</span> of what moves it is the individual companies&rsquo; own stories.',
           '没有哪股外部力量主导这本账簿 —— <span class="fig">' + pct0(idio) +
             '</span> 的波动来自各家公司自己的故事。');

    var SCALE = Math.max(0.10, topS, idio);      // one shared scale, printed below
    var rows = ranked.slice(0, 6).map(function (k) {
      var s = b.factorShare[k] || 0;
      return '<div class="conc-row"><span class="who">' + esc(flabel(k)) + '</span>' +
        '<span class="track"><span style="width:' + Math.min(100, s / SCALE * 100).toFixed(0) + '%"></span></span>' +
        '<span class="pct fig">' + pct0(s) + '</span></div>';
    }).join('');
    rows += '<div class="conc-row is-ballast"><span class="who">' +
      te('Own story', '个股自身') + '</span>' +
      '<span class="track"><span style="width:' + Math.min(100, idio / SCALE * 100).toFixed(0) + '%"></span></span>' +
      '<span class="pct fig">' + pct0(idio) + '</span></div>';

    // the macro half: does this book care where rates go?
    var rateBeta = (b.bookBeta && b.bookBeta.rates);
    var rateShare = (b.factorShare && b.factorShare.rates) || 0;
    var rateLine = '';
    if (isNum(rateBeta)) {
      var matters = rateShare >= 0.05 || Math.abs(rateBeta) >= 0.30;
      var withRates = rateBeta >= 0;
      /* The Tier-2 receipt rides the SENTENCE, not a separate `?` glyph. The old
         `.wri-q` affordance belonged to the braid hero W2 deleted and is styled
         nowhere on this page any more, so it rendered as a bare question mark
         hanging off the end of the line. The workspace's own pattern is
         `data-tip-en`/`data-tip-zh` on the element carrying the copy, wired to the
         LENS popover by theme.js — technical quantities live there, never at glance
         tier, and never in a title= attribute. */
      rateLine = '<p class="rc-note" style="margin-top:12px">' +
        '<span class="rc-tip" tabindex="0" data-tip-en="' +
          esc('Measured against the nightly rates factor: net beta ' + rateBeta.toFixed(2) +
              ', share of book variance ' + (rateShare * 100).toFixed(1) +
              '%. Measurement over the model window, not a forecast.') +
        '" data-tip-zh="' +
          esc('对每晚利率因子的测量：净贝塔 ' + rateBeta.toFixed(2) + '，占账簿方差 ' +
              (rateShare * 100).toFixed(1) + '%。为模型窗口内的测量，非预测。') + '">' +
        (matters
        ? te('Where interest rates go matters here: the book leans <b>' +
               (withRates ? 'with' : 'against') + '</b> them, and they account for <span class="fig">' +
               pct0(rateShare) + '</span> of its movement.',
             '利率走向对这本账簿有影响：账簿与利率<b>' + (withRates ? '同向' : '反向') +
               '</b>，并占其波动的 <span class="fig">' + pct0(rateShare) + '</span>。')
        : te('Interest rates barely move this book — under <span class="fig">' +
               pct0(Math.max(rateShare, 0.01)) + '</span> of its movement.',
             '利率对这本账簿影响很小 —— 占其波动不足 <span class="fig">' +
               pct0(Math.max(rateShare, 0.01)) + '</span>。')) +
        '</span></p>';
    }

    /* THE GROUPING CAVEAT, surfaced where the grouping is displayed (packet §8-W3).
       `RiskCore.factorBets` files each name under the single force that explains most
       of its OWN variance, and it measures that with the factor covariance's DIAGONAL
       only — cross-factor terms are dropped. For a name pulled by two correlated
       forces the runner-up can therefore be understated, which is why the group a name
       is filed under and the book-level ranking above it can name different forces for
       the same ticker. Said in plain words rather than left as a code comment, because
       the reader is the one looking at the two lists. */
    var caveat = te(
      'Each name is filed under the one force that explains most of its own moves, measured one force at a time. A name pulled by two related forces is filed under the larger one, so its second force can read smaller here than in the list above.',
      '每只票按“最能解释其自身波动”的那一股力量归类，且逐一测量。若一只票同时受两股相关力量牵引，会归入较大的那一股 —— 因此它的第二股力量在这里可能比上面的列表显得更小。');

    var foot = te('Shares of everything that moves this book. Full bar is <span class="fig">' +
        pct0(SCALE) + '</span>.',
      '各项占本账簿全部波动的比例。满格为 <span class="fig">' + pct0(SCALE) + '</span>。') +
      ' ' + caveat;
    var cf = coverageFoot(cov);
    if (cf) foot += ' ' + cf;
    // `is-factors` widens the label column: factor names are words ("Growth / Tech"),
    // not tickers, and wrapping one across two lines breaks the ladder's rhythm
    return tabHTML(claim, te('Each bar is that force&rsquo;s share of the book&rsquo;s movement, on one shared scale.',
      '每根条形是该力量在本账簿波动中的占比，统一刻度。'),
      '<div class="conc is-factors">' + rows + '</div>' + rateLine, foot);
  }

  // ---- 4. STRESS ----------------------------------------------------------
  /* The one question: is this the same book on the days the market falls?
     Source: the SECOND RiskCore read the engine already performs under
     factor_cov_stress (re-estimated on worst-quartile market days), compared with
     the calm read. Nothing is recomputed — `read()` returns both.

     This tab must be honest in BOTH directions. A book can tighten under stress
     (the interesting case) and it can also spread — and on an orthogonalized model
     with per-name idio vol held v1-invariant, spreading is common. Reporting only
     the tightening direction would make the calm case look like a missing read. */
  function stressHTML(RR, cov) {
    var calm = RR && RR.calm;
    if (!calm || !calm.ok) return '';
    if (!RR.hasStress || !RR.stress || !RR.stress.ok) {
      return tabHTML(
        te('Tonight&rsquo;s model has no falling-days lens.',
           '今晚的模型没有「下跌日」视角。'),
        te('Everything else in this Risk Center is the all-days read. When the falling-days lens is in the nightly model, this tab compares the two.',
           '风险中心其余部分均为「全部交易日」的读数。当每晚的模型带有「下跌日」视角时，这个标签会对比两者。'),
        '', coverageFoot(cov));
    }
    var st = RR.stress;
    var nNames = calm.held.length;
    var cB = enbClamp(calm.enb, nNames).bets, sB = enbClamp(st.enb, nNames).bets;
    var cTop = calm.topFactorShare || 0, sTop = st.topFactorShare || 0;
    var tightens = st.enb < calm.enb - 1e-9;

    var claim;
    if (RR.diverges) {
      claim = te('On the days the market falls, this book tightens: your <span class="fig">' + nNames +
          '</span> names move like about <span class="fig">' + sB + '</span>, not <span class="fig">' + cB + '</span>.',
        '在市场下跌的日子里，这本账簿会收紧：你的 <span class="fig">' + nNames +
          '</span> 只持仓更像 <span class="fig">' + sB + '</span> 个方向，而不是 <span class="fig">' + cB + '</span> 个。');
    } else if (tightens) {
      claim = te('On the days the market falls, this book tightens a little — but it does not collapse into one position.',
        '在市场下跌的日子里，这本账簿会略微收紧 —— 但不会塌缩成一笔仓位。');
    } else {
      claim = te('On the days the market falls, this book does not tighten — its names spread out slightly rather than moving as one.',
        '在市场下跌的日子里，这本账簿并未收紧 —— 持仓略微分散，而不是同步波动。');
    }

    function lensRow(label, topShare, ballast) {
      var SC = Math.max(0.10, cTop, sTop);
      return '<div class="conc-row' + (ballast ? ' is-ballast' : '') + '">' +
        '<span class="who">' + label + '</span>' +
        '<span class="track"><span style="width:' + Math.min(100, topShare / SC * 100).toFixed(0) + '%"></span></span>' +
        '<span class="pct fig">' + pct0(topShare) + '</span></div>';
    }
    /* Both counts print under the bars whichever way the comparison came out. The
       claim sentence above can only lead with ONE of the three outcomes; a reader who
       gets the "does not tighten" wording would otherwise never see the two numbers
       that sentence is about. Nulls printed — and so are unremarkable results. */
    var counts = '<p class="rc-note">' + te(
      'On an average day this book moves in about <span class="fig">' + cB +
        '</span> separate directions; on the falling days, about <span class="fig">' + sB + '</span>.',
      '在平均日，这本账簿约有 <span class="fig">' + cB +
        '</span> 个独立方向；在下跌日，约有 <span class="fig">' + sB + '</span> 个。') + '</p>';
    var body = '<div class="conc">' +
      lensRow(te('Average day', '平均日'), cTop, true) +
      lensRow(te('Falling days', '下跌日'), sTop, false) +
      '</div>' + counts;

    var note = te(
      'Each bar is how much of the book&rsquo;s movement its single biggest force accounts for, under each lens.',
      '每根条形表示在该视角下，最大的那股力量占本账簿波动的比例。');

    // pairs that only move together when it matters — the finding this lens exists for
    var only = (RR.stressOnlyPairs || []).slice(0, 3);
    var extra = '';
    if (only.length) {
      var names = only.map(function (p) { return p.a + ' · ' + p.c; });
      extra = ' ' + te(
        '<b>' + esc(names.join('; ')) + '</b> only move together on the falling days.',
        '<b>' + esc(names.join('；')) + '</b> 只在下跌日才同步波动。');
    }
    var foot = te(
      'The falling-days lens re-measures how the forces move together using only the market&rsquo;s worst days. Each name&rsquo;s own story is held unchanged between the two.',
      '「下跌日」视角仅用市场表现最差的那些交易日，重新测量各股力量之间的联动。两个视角下，个股自身的故事保持不变。') + extra;
    var cf = coverageFoot(cov);
    if (cf) foot += ' ' + cf;
    return tabHTML(claim, note, body, foot);
  }

  // ---- 5. EVENTS ----------------------------------------------------------
  /* The one question: what is coming, and when? Source: the SAME events lane the
     per-name drawer already renders (`laneRead(j).events`), over the per-ticker JSON
     the page has already hydrated — CARD_JSON. No new fetch: a name whose detail has
     not arrived is simply not claimed, which is why the footer counts what it read. */
  function eventsHTML(cov) {
    var rows = [], seen = 0;
    Object.keys(CARD_JSON).forEach(function (t) {
      var j = CARD_JSON[t]; if (!j) return;
      seen++;
      var earn = j.earnings || null;
      if (!earn || !earn.next_date) return;
      var d = daysUntil(earn.next_date);
      if (!isNum(d) || d < 0) return;
      rows.push({ t: t, d: d, iso: earn.next_date, when: earn.next_time || '' });
    });
    rows.sort(function (a, b) { return a.d - b.d; });

    if (!seen) {
      return tabHTML(
        te('Event dates arrive with each name&rsquo;s detail.',
           '事件日期随每只票的详细数据一起载入。'),
        te('Nothing has loaded yet. Open the holdings table and this fills in as each name resolves.',
           '目前尚未载入。打开持仓表格，各只票的数据到位后这里会自动填充。'), '', '');
    }
    if (!rows.length) {
      return tabHTML(
        te('No reporting dates ahead for the <span class="fig">' + seen + '</span> names we have a calendar for.',
           '在我们有日历的 <span class="fig">' + seen + '</span> 只票中，暂无即将到来的财报日。'),
        te('A name with no date here either reports outside the covered window or has no scheduled date we can read.',
           '此处没有日期的票，要么财报日不在覆盖窗口内，要么没有我们能读到的排定日期。'), '',
        coverageFoot(cov));
    }
    var soon = rows.filter(function (r) { return r.d <= 14; });
    var first = rows[0];
    var claim = soon.length
      ? te('<span class="fig">' + soon.length + '</span> of your names report within two weeks — <b>' +
             esc(first.t) + '</b> is first, in <span class="fig">' + first.d + '</span> ' +
             (first.d === 1 ? 'day' : 'days') + '.',
           '你有 <span class="fig">' + soon.length + '</span> 只持仓将在两周内发布财报 —— 最早的是 <b>' +
             esc(first.t) + '</b>，还有 <span class="fig">' + first.d + '</span> 天。')
      : te('Nothing reports in the next two weeks. The next is <b>' + esc(first.t) +
             '</b>, in <span class="fig">' + first.d + '</span> days.',
           '未来两周没有财报。下一个是 <b>' + esc(first.t) + '</b>，还有 <span class="fig">' +
             first.d + '</span> 天。');

    var list = rows.slice(0, 8).map(function (r) {
      var w = r.when === 'pre-market' ? te('before the open', '盘前')
        : r.when === 'after-hours' ? te('after close', '盘后') : '';
      return '<div class="evt-row' + (r.d <= 5 ? ' is-near' : '') + '">' +
        '<span class="who">' + esc(r.t) + '</span>' +
        '<span class="when">' + te(esc(fmtDate(r.iso)), esc(fmtDateZh(r.iso))) +
          (w ? ' <span class="sub">' + w + '</span>' : '') + '</span>' +
        '<span class="pct"><span class="fig">' + r.d + '</span>d</span></div>';
    }).join('');

    var foot = te('Read from the <span class="fig">' + seen +
        '</span> names whose detail has loaded. A name without a covered calendar is not listed and is not counted.',
      '读取自已载入详细数据的 <span class="fig">' + seen +
        '</span> 只票。没有覆盖日历的票不会列出，也不计入。');
    return tabHTML(claim, te('Nearest first. Dates come from each company&rsquo;s own reported schedule.',
      '按时间由近及远排列。日期来自各公司自己公布的排期。'),
      '<div class="conc">' + list + '</div>', foot);
  }

  // ---- 6. WEAK LINKS & STRENGTHS ------------------------------------------
  /* The one question Concentration does NOT answer: risk per dollar. Concentration
     ranks names by how much of the risk they carry; this ranks them by how much they
     carry RELATIVE TO WHAT THEY COST — which is how a small position turns out to be
     the problem and a large one turns out to be the ballast.

     Both distributions are published by RiskCore over the SAME modeled book: `W` (the
     normalized money weights) and `mctrShare`. Comparing them is the seam's claim in
     numbers, per name; no new estimator is involved. A name whose risk share is
     negative moves against the rest of the book — the model's own statement, reported
     as such and never as an instruction. */
  function weakLinksHTML(b, cov) {
    if (!b || !b.ok || b.held.length < 2) return '';
    var rows = b.held.map(function (t) {
      var money = b.W[t] || 0, risk = b.mctrShare[t] || 0;
      return { t: t, money: money, risk: risk,
               ratio: money > 0 ? risk / money : 0, own: b.idioShare[t] || 0 };
    });
    // the weak link: most risk per dollar. the strength: least (negative = pulls back).
    var byRatio = rows.slice().sort(function (x, y) { return y.ratio - x.ratio; });
    var weak = byRatio[0], strong = byRatio[byRatio.length - 1];
    if (!weak || !strong || weak.t === strong.t) return '';

    var claim = te(
      '<b>' + esc(weak.t) + '</b> takes <span class="fig">' + pct0(weak.money) +
        '</span> of the money and <span class="fig">' + pct0(Math.abs(weak.risk)) + '</span> of the risk.',
      '<b>' + esc(weak.t) + '</b> 占用了 <span class="fig">' + pct0(weak.money) +
        '</span> 的资金，却扛下 <span class="fig">' + pct0(Math.abs(weak.risk)) + '</span> 的风险。');

    var strongLine = (strong.risk < 0)
      ? te('<b>' + esc(strong.t) + '</b> is the one pulling the other way — when the rest of the book moves, it leans against it.',
           '<b>' + esc(strong.t) + '</b> 是往反方向拉的那一只 —— 账簿其余部分波动时，它反向倾斜。')
      : te('<b>' + esc(strong.t) + '</b> is the quiet one: <span class="fig">' + pct0(strong.money) +
             '</span> of the money for <span class="fig">' + pct0(Math.abs(strong.risk)) + '</span> of the risk.',
           '<b>' + esc(strong.t) + '</b> 是安静的那一只：占 <span class="fig">' + pct0(strong.money) +
             '</span> 的资金，只承担 <span class="fig">' + pct0(Math.abs(strong.risk)) + '</span> 的风险。');

    /* ONE scale across BOTH columns, not one per column.
       The first build normalised money and risk independently, so the name with the
       largest money drew a full bar and the name with the largest risk drew a full
       bar — and the row the headline was about (most risk PER DOLLAR) drew neither.
       The picture contradicted the sentence above it. On a shared scale the finding
       is the thing you actually see: a risk bar longer than its own money bar is a
       name carrying more than it costs, and that is the whole tab. */
    var SCALE = Math.max(0.01, maxOf(rows, 'money'), maxAbsRisk(rows));
    // ordered by risk-per-dollar so the two ends of the list ARE the two findings
    var list = byRatio.slice(0, 6).map(function (r) {
      var heavy = r.ratio > 1.15, light = r.ratio < 0.85;
      return '<div class="wk-row' + (light ? ' is-ballast' : '') + '">' +
        '<span class="who">' + esc(r.t) + '</span>' +
        '<span class="two"><span class="track"><span style="width:' +
          Math.min(100, r.money / SCALE * 100).toFixed(0) + '%"></span></span>' +
        '<span class="track"><span style="width:' +
          Math.min(100, Math.abs(r.risk) / SCALE * 100).toFixed(0) + '%"></span></span></span>' +
        // a direction glyph is not a figure — it stays out of the tabular-mono span
        '<span class="pct mark">' + (heavy ? '↑' : light ? '↓' : '·') + '</span></div>';
    }).join('');

    var body = '<div class="conc wk">' +
      '<div class="wk-hd"><span></span><span class="two"><span>' + te('Money', '资金') +
        '</span><span>' + te('Risk', '风险') + '</span></span><span></span></div>' + list + '</div>' +
      '<p class="rc-note" style="margin-top:12px">' + strongLine + '</p>';

    // per-name own story — the idio half of the brief, from the published idioShare
    var ownTop = rows.slice().sort(function (x, y) { return y.own - x.own; })[0];
    var foot = '';
    if (ownTop && ownTop.own > 0.02) {
      foot += te('Of everything that moves this book, <span class="fig">' + pct0(ownTop.own) +
          '</span> is <b>' + esc(ownTop.t) + '</b>&rsquo;s own story — news that belongs to that company alone.',
        '在本账簿的全部波动中，<span class="fig">' + pct0(ownTop.own) + '</span> 来自 <b>' +
          esc(ownTop.t) + '</b> 自身的故事 —— 只属于这家公司的消息。') + ' ';
    }
    foot += te('Both bars share one scale, so a risk bar longer than its own money bar is a name carrying more than it costs: <span class="mark">↑</span>. Shorter is <span class="mark">↓</span>.',
      '两根条形共用同一刻度：风险条比自身的资金条长，说明这只票承担的风险高于它占用的资金 —— <span class="mark">↑</span>；反之为 <span class="mark">↓</span>。');
    var cf = coverageFoot(cov);
    if (cf) foot += ' ' + cf;
    return tabHTML(claim, te('Risk per dollar, biggest first. A name can be small and still be the largest thing in the book.',
      '按「每一元资金承担的风险」排序，由高到低。一只票可以仓位很小，却是账簿里最大的一件事。'), body, foot);
  }
  function maxOf(rows, k) {
    var m = 0; rows.forEach(function (r) { if (r[k] > m) m = r[k]; }); return m;
  }
  function maxAbsRisk(rows) {
    var m = 0; rows.forEach(function (r) { var v = Math.abs(r.risk); if (v > m) m = v; }); return m;
  }

  /* RETIRED IN W2 — the braid hero, its verdict/sub-card layer and the in-hero
     pre-trade check all rendered into #wri_hero, which the pinned workspace design
     replaces with the Book Seam + the Risk Center. They are deleted rather than left
     guarded: a render function whose host no longer exists is dead code that still
     reviews as live. W3 gives the Scenario Lab that replaced the pre-trade check its
     real body (below); the MEASUREMENT layer this file exists for — RiskCore reads,
     the lane engine, the chain index, enbClamp — is untouched throughout. */

  // =========================================================================
  //  SCENARIO LAB — the pre-trade check, rehomed (packet §12 / §14 A4).
  //
  //  WRI-R3 stands in full: the user constructs, we describe. There is no
  //  optimizer here, no recommended size, no "consider" and no verb telling
  //  anyone to do anything. Every sentence below is a statement about a book
  //  that would exist, in the same words the tabs above use for the book that
  //  does. The engine is RiskCore.whatIf, unchanged.
  // =========================================================================
  /* The default size, stated rather than assumed. Production shipped this figure
     into an unlabelled box beside an empty ticker field, which is how a round
     number becomes a suggestion by accident: the reader assumes a $10,000 default
     means something about their book. It means nothing about their book — it is a
     comparison unit, and the lab says so in the copy under the form. */
  var W4_DEFAULT_DOLLARS = 10000;
  var LAST_WMAP = {}, LAST_LENS = 'calm';

  function money0(v) {
    var s = String(Math.round(Math.abs(v)));
    return '$' + s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function labIntroHTML() {
    return '<p class="lab-say">' + te(
      'Name a position and a size, and this prints the same figures for the book you would have — how many separate directions it would move in, how much of the risk that position would carry, and which of your names it would move with.',
      '输入一个代码和一个金额，这里会用同样的口径打印「加仓后」的账簿数字 —— 会剩下几个独立方向、这笔仓位会扛下多少风险、以及它会和你的哪些持仓同步波动。') +
      '</p>' +
      '<div class="lab-form">' +
        '<input class="lab-in lab-t" id="rc_lab_t" type="text" maxlength="12" autocomplete="off"' +
          ' data-ph-en="Ticker" data-ph-zh="代码" aria-label="' + (isZh() ? '代码' : 'Ticker') + '">' +
        '<span class="lab-d">' +
          '<span class="lab-cur">$</span>' +
          '<input class="lab-in lab-amt" id="rc_lab_d" type="number" min="0" step="any" value="' +
            W4_DEFAULT_DOLLARS + '" aria-label="' + (isZh() ? '金额' : 'Size in dollars') + '">' +
        '</span>' +
        '<button class="gbtn gbtn-sm" type="button" id="rc_lab_go">' +
          te('See the change', '查看变化') + '</button>' +
      '</div>' +
      '<div class="lab-out" id="rc_lab_out"></div>' +
      '<p class="lab-note">' + te(
        'The size starts at <span class="fig">' + money0(W4_DEFAULT_DOLLARS) +
          '</span> because a round number makes two runs comparable — it is not drawn from your book and it is not a suggested size. Change it to whatever you are actually weighing.',
        '默认金额为 <span class="fig">' + money0(W4_DEFAULT_DOLLARS) +
          '</span>，只是为了让两次试算可比 —— 它不是根据你的账簿算出来的，也不是建议仓位。请改成你实际在考虑的金额。') +
      '</p>';
  }

  /* Returns the lab's RESULT html for one candidate. PURE with respect to the DOM —
     it reads the module's cached model + weights and returns a string, so the caller
     owns the pixels exactly as it does for the tabs. */
  function scenarioHTML(ticker, dollars) {
    ticker = String(ticker || '').trim().toUpperCase();
    if (!ticker) {
      return '<p class="rc-soon">' + te('Name a position to compare.', '请输入一个代码进行对比。') + '</p>';
    }
    if (!DATA || !window.RiskCore) {
      return '<p class="rc-soon">' + te(
        'The nightly model is not loaded, so there is nothing to compare against yet.',
        '每晚的模型尚未载入，暂时无法进行对比。') + '</p>';
    }
    var d = (isNum(dollars) && dollars > 0) ? dollars : W4_DEFAULT_DOLLARS;
    var r;
    try { r = RiskCore.whatIf(DATA, LAST_WMAP, ticker, d, LAST_LENS); }
    catch (e) { r = null; }
    if (!r) {
      return '<p class="rc-soon">' + te('That comparison could not be run.', '该对比无法完成。') + '</p>';
    }

    // an unmodeled candidate never gets numbers invented for it
    if (!r.modeled) {
      return '<p class="lab-line">' + te(
        'The nightly model has no read for <b>' + esc(ticker) +
          '</b>, so we cannot say what it would do to this book&rsquo;s structure. Its own price signals still show in the table above.',
        '每晚的模型没有 <b>' + esc(ticker) +
          '</b> 的读数，因此无法说明它会如何改变这本账簿的结构。它自己的价格信号仍在上方表格中。') + '</p>';
    }
    if (!r.after || !r.after.ok) {
      return '<p class="rc-soon">' + te(
        'This needs at least two covered positions to compare against.',
        '至少需要两笔已覆盖的持仓才能进行对比。') + '</p>';
    }

    var beforeOk = r.before && r.before.ok;
    var nAfter = r.after.held.length;
    var bAfter = enbClamp(r.after.enb, nAfter).bets;
    var bBefore = beforeOk ? enbClamp(r.before.enb, r.before.held.length).bets : null;
    var cand = r.candidate || {};
    var share = isNum(cand.mctrShare) ? Math.abs(cand.mctrShare) : null;

    var head;
    if (bBefore == null) {
      head = te('With <b>' + esc(ticker) + '</b> at <span class="fig">' + money0(d) +
          '</span>, this book would move in about <span class="fig">' + bAfter + '</span> separate directions.',
        '加入 <b>' + esc(ticker) + '</b>（<span class="fig">' + money0(d) +
          '</span>）后，这本账簿大约会有 <span class="fig">' + bAfter + '</span> 个独立方向。');
    } else if (bAfter === bBefore) {
      head = te('<b>' + esc(ticker) + '</b> at <span class="fig">' + money0(d) +
          '</span> would leave this book moving in about <span class="fig">' + bAfter +
          '</span> separate directions — the same as now.',
        '<b>' + esc(ticker) + '</b>（<span class="fig">' + money0(d) +
          '</span>）不会改变方向数：仍约为 <span class="fig">' + bAfter + '</span> 个，与当前相同。');
    } else {
      head = te('<b>' + esc(ticker) + '</b> at <span class="fig">' + money0(d) +
          '</span> would take this book from about <span class="fig">' + bBefore +
          '</span> separate directions to <span class="fig">' + bAfter + '</span>.',
        '<b>' + esc(ticker) + '</b>（<span class="fig">' + money0(d) +
          '</span>）会把这本账簿从大约 <span class="fig">' + bBefore +
          '</span> 个独立方向变成 <span class="fig">' + bAfter + '</span> 个。');
    }

    var lines = '<p class="lab-line">' + head + '</p>';
    if (share != null) {
      var rankTxt = isNum(cand.rank) ? cand.rank : null;
      lines += '<p class="lab-line">' + (cand.hedge
        ? te('It would carry <span class="fig">' + pct0(share) +
               '</span> of the risk and lean <b>against</b> the rest of the book.',
             '它将承担 <span class="fig">' + pct0(share) + '</span> 的风险，并与账簿其余部分<b>反向</b>。')
        : te('It would carry <span class="fig">' + pct0(share) + '</span> of the risk' +
               (rankTxt ? ', the <span class="fig">' + rankTxt + '</span>' + ordSuffix(rankTxt) +
                 ' largest of <span class="fig">' + nAfter + '</span>' : '') + '.',
             '它将承担 <span class="fig">' + pct0(share) + '</span> 的风险' +
               (rankTxt ? '，在 <span class="fig">' + nAfter + '</span> 只中排第 <span class="fig">' +
                 rankTxt + '</span>' : '') + '。')) + '</p>';
    }
    if (cand.twinWith && cand.twinWith.length) {
      var tw = cand.twinWith.slice(0, 4);
      lines += '<p class="lab-line">' + te(
        'It moves as one with <b>' + esc(tw.join(', ')) + '</b> — adding it would be owning that trade again.',
        '它与 <b>' + esc(tw.join('、')) + '</b> 同步波动 —— 加入它等于再持有一次同一笔交易。') + '</p>';
    } else if (isNum(cand.topFactorShareOfName) && cand.topFactor) {
      var idEn = IDEA[cand.topFactor] ? IDEA[cand.topFactor][0] : flabel(cand.topFactor);
      var idZh = IDEA[cand.topFactor] ? IDEA[cand.topFactor][1] : flabel(cand.topFactor);
      lines += '<p class="lab-line">' + te(
        'What mostly moves <b>' + esc(ticker) + '</b> is <b>' + esc(idEn) +
          '</b>; nothing in this book moves as one with it.',
        '主要驱动 <b>' + esc(ticker) + '</b> 的是<b>' + esc(idZh) +
          '</b>；本账簿中没有与它同步波动的持仓。') + '</p>';
    }
    lines += '<p class="lab-line lab-lens">' + (LAST_LENS === 'stress'
      ? te('Measured on the falling-days lens, the same one the tabs above lead with.',
           '按「下跌日」视角测量，与上方标签所采用的视角一致。')
      : te('Measured on the all-days lens, the same one the tabs above lead with.',
           '按「全部交易日」视角测量，与上方标签所采用的视角一致。')) +
      ' ' + te('A description of a book that would exist — not a recommendation.',
               '这是对「假如存在」的那本账簿的描述 —— 不构成任何建议。') + '</p>';
    return lines;
  }
  /* The ordinal SUFFIX only — the digit stays inside `.fig` and the letters stay
     outside it. Mono tabular numerals are for figures, never for words, and "4th"
     set entirely in mono renders the "th" as a figure glyph. */
  function ordSuffix(n) {
    var s = ['th', 'st', 'nd', 'rd'], v = n % 100;
    return (s[(v - 20) % 10] || s[v] || s[0]);
  }

  function clustersFor(b) {
    var bets = RiskCore.factorBets(b, 0.25);
    return bets.map(function (g) {
      var fk = g.factor;
      var single = g.members.length === 1;
      var lab = clusterLabel(g.members, fk);
      // a singleton with a negative MCTR share is a hedge (⇄)
      var hedge = single && (b.mctrShare[g.members[0]] || 0) < 0;
      return { members: g.members, share: g.share, hue: fk ? fhue(fk) : 'var(--f-idio)',
        fk: fk, labelEn: lab.en, labelZh: lab.zh, hedge: hedge };
    });
  }
  function clusterLabel(members, fk) {
    if (members.length >= 2 && fk) {
      var f = FLABEL[fk] || { en: fk, zh: fk };
      return { en: (f.en + ' bet').toUpperCase(), zh: f.zh + '押注' };
    }
    if (members.length === 1) return { en: members[0], zh: members[0] };   // its own bet
    // a multi-name idio group (rare) -> label by the names
    return { en: members.join(' · '), zh: members.join(' · ') };
  }

  // verdict sentence — the bet count is the EFFECTIVE number of bets (ENB rounded,
  // ≥1): the rigorous "how many independent bets" measure (masterplan §3.2), which
  // coheres with the ENB-driven state chip. The measured ENB also prints in
  // sub-card 1. The stress lens re-words the line (WRI-R7 / §4): calm shows the
  // calm count, and — when a stress lens exists — how it collapses in selloffs.
  /* ENB display clamp. The measure is a factor + per-name bucket composition, and on a
     small book it can land ABOVE the number of names held — "your 3 names move as about
     4 bets" is not something a reader can act on. Tier 1 caps the printed number at the
     name count; the unclamped value is disclosed in the Tier-2 method tip rather than
     hidden (nulls printed, not swallowed). PURE — exported for the node test. */
  function enbClamp(raw, nNames) {
    var n = Math.max(1, nNames || 0);
    return {
      raw: raw,
      shown: Math.min(raw, n),                          // the 1dp footer figure
      bets: Math.max(1, Math.min(Math.round(raw), n)),  // the whole-number verdict figure
      clamped: raw > n + 1e-9
    };
  }
  /* The one dynamic sentence the method tip gains when the clamp engages. Returns null
     when it does not, so the tip is unchanged in the ordinary case. PURE. */
  function enbTipSuffix(info) {
    if (!info || !info.clamped) return null;
    var raw = info.raw.toFixed(1);
    return {
      en: ' Factor + per-name bucket math can read above your name count; the display ' +
          'caps at the count (raw tonight: ' + raw + ').',
      zh: ' 因子与个股桶的计算可能高于名称数量；展示以名称数量为上限（今晚原始值：' + raw + '）。'
    };
  }
  function betCount(b) { return enbClamp(b.enb, b.held.length).bets; }
  // =========================================================================
  //  L1 card decoration — add lane chips + role badge + drawer to each card
  // =========================================================================
  // =========================================================================
  //  Row decoration — batched, and scoped to the dense tables
  // =========================================================================
  /* The card grid this layer used to decorate is gone. What replaced it is a dense
     table whose rows are rebuilt by their owning renderer (watchlist.js for the
     watchlist, portfolio.js for the holdings), so decoration is no longer a second
     DOM pass over painted cards — it is an input to the ONE pass that draws the row.

     What still belongs here is the BATCHING: a hydration wave over 100 names used to
     fire one decoration pass per resolved name. `scheduleDecorate` coalesces the whole
     wave into a single animation frame, so the wave costs one re-render, not a hundred. */
  var _decorPending = false;
  function scheduleDecorate() {
    if (_decorPending) return;
    _decorPending = true;
    var run = function () {
      _decorPending = false;
      if (window.PF && window.PF.render) { try { window.PF.render(); } catch (e) {} }
    };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
    else setTimeout(run, 16);
  }

  // =========================================================================
  //  Book risk shares — the numbers, published, never painted here
  // =========================================================================
  /* This file no longer draws anything into the holdings table. It computes the book
     read and PUBLISHES it (`publish` above); watchlist.js draws the seam and
     portfolio.js draws the rows. That split is what makes the signature impossible to
     draw twice, and it is why the risk share a row prints and the risk share the seam
     paints can never disagree — they are the same object. */
  var BOOK_SHARES = {};   // {ticker -> mctr share} from the last read
  var UNMODELED = {};     // {ticker -> 1} names present in the list but absent from the model

  // =========================================================================
  //  Orchestration — recompute whenever the weights change
  // =========================================================================
  var DATA = null, DATA_LOADING = null;
  function loadData() {
    if (DATA) return Promise.resolve(DATA);
    if (DATA_LOADING) return DATA_LOADING;
    DATA_LOADING = fetch('factor_betas.json').then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { DATA = j; return j; }).catch(function () { return null; });
    return DATA_LOADING;
  }

  // transmission chains subset — fetched once, 404 => the whole chain lane stays silently
  // absent (no chips, no drawer line, no rail sentence). Never blocks the book render.
  var CHAINS_IDX = {}, CHAINS_LOADED = false, CHAINS_LOADING = null;
  function loadChains() {
    if (CHAINS_LOADED) return Promise.resolve(CHAINS_IDX);
    if (CHAINS_LOADING) return CHAINS_LOADING;
    CHAINS_LOADING = fetch('transmission_chains.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { CHAINS_IDX = j ? chainIndex(j) : {}; CHAINS_LOADED = true; return CHAINS_IDX; })
      .catch(function () { CHAINS_IDX = {}; CHAINS_LOADED = true; return CHAINS_IDX; });
    return CHAINS_LOADING;
  }

  function recomputeBook(weights) {
    loadData().then(function (data) {
      if (!data) {
        // no factor model reachable (401 signed out, or the artifact is absent): the
        // workspace still renders — the seam's risk rail becomes a lock shell and the
        // Risk Center says so. Silence here would leave the page claiming coverage.
        BOOK_SHARES = {}; UNMODELED = {}; LAST_READ = null;
        publish({ shares: {}, covered: {}, bets: null, modeledN: 0, regime: '' });
        return;
      }
      // fill BOOK_SHARES from the default-lens read (MODELED only — a non-USD value
      // entering here would corrupt every downstream statistic)
      var wIn = {};
      modeledUniverse(weights.universe).forEach(function (t) {
        var v = weights.wmap[t]; wIn[t] = isNum(v) && v > 0 ? v : 1;
      });
      var RR = RiskCore.read(data, wIn);
      BOOK_SHARES = {}; UNMODELED = {};
      var b = RR.hasStress ? RR.stress : RR.calm;
      if (b && b.ok) b.held.forEach(function (t) { BOOK_SHARES[t] = b.mctrShare[t]; });
      // names in the list but not in the factor model. A non-US name is not
      // "unmodeled" in this sense — it has its own market's signals; it is simply
      // outside the USD factor stack, which the coverage line already says.
      (weights.universe || []).forEach(function (t) {
        if (isModeled(t) && !(data.betas && data.betas[t])) UNMODELED[t] = 1;
      });
      publishBook(data, weights);
    });
  }

  function init() {
    // the workspace's Book Seam is this file's host now (#wri_hero is gone with the
    // braid). A page without it gets the measurement layer and no render at all.
    if (!document.getElementById('ws_seam')) return;
    // 0) load the transmission chains subset once; when it resolves, re-publish so the
    //    chain sentence and the drawer rows appear (404 => silent, never a blank claim).
    loadChains().then(function () { scheduleDecorate(); });
    // 1) recompute the book whenever the FX layer republishes weights
    document.addEventListener('fx-weights', function (e) { recomputeBook(e.detail); });
    // 2) first read: pull current weights if the FX panel already resolved them
    if (window.FX && window.FX.currentWeights) recomputeBook(window.FX.currentWeights());
    else loadData().then(function () { recomputeBook({ universe: [], wmap: {}, mode: 'manual' }); });
    // 3) language / theme flips -> re-derive the wording (the numbers are unchanged)
    document.addEventListener('langchange', onLangTheme);
    document.addEventListener('themechange', onLangTheme);
    // 4) book switch -> the read is scoped to the active book (modeled vs coverage-only)
    document.addEventListener('bk-change', function () {
      if (window.FX && window.FX.currentWeights) recomputeBook(window.FX.currentWeights());
      else onLangTheme();
    });
    // theme.js toggles data-lang via attribute; also observe it directly
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) if (muts[i].attributeName === 'data-lang') { onLangTheme(); return; }
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-lang'] });
  }
  function onLangTheme() {
    if (window.FX && window.FX.currentWeights) recomputeBook(window.FX.currentWeights());
    else scheduleDecorate();
  }

  // keyboard: Enter/Space on a ? tip is a no-op focus target; tips are CSS/hover +
  // focus. (data-tip-en/zh consumed by the page's shared tooltip, no title=.)

  /* Shared seam for the position table (portfolio.js). The assessment drawer renders
     the SAME seven lane rows and the SAME role ladder the cards do — exported here
     rather than duplicated there, so the two surfaces can never drift. */
  if (typeof window !== 'undefined') {
    window.WRI = {
      laneRead: laneRead,
      roleBadge: roleBadge,
      laneRows: laneRowsHTML,
      chainRows: function (t) { return chainDrawerRows(CHAINS_IDX[t]); },
      noteJson: noteJson,
      /* The Scenario Lab's engine seam. The workspace owns the form and the pixels;
         this owns the model. Same split as the tabs, and the same reason: two places
         that could compute a book read are two places that can disagree about one. */
      scenario: scenarioHTML,
      defaultDollars: function () { return W4_DEFAULT_DOLLARS; }
    };
  }

  // Browser bootstrap — guarded so `require()` under node (the unit-test shell) never
  // touches the DOM at load. In node `document` is undefined; we skip straight to the export.
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }

  // Node-test surface (TXI W4): expose the PURE chain-lane helpers so the node-shelled
  // unit tests can exercise the furthest-progressed selection, the 404-empty path, and the
  // rail-sentence condition without a DOM. No-op in the browser (module is undefined).
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      chainIndex: chainIndex, furthestChain: furthestChain,
      railChainSentence: railChainSentence, chainDrawerRows: chainDrawerRows,
      chainDriver: chainDriver,
      enbClamp: enbClamp, enbTipSuffix: enbTipSuffix, betCount: betCount,
      /* W3 Risk Center tab builders — PURE string builders over a RiskCore result, so
         the node shell can hand them a crafted book (a stress lens that really does
         converge, a book with an unmodeled name, an empty event calendar) and assert
         the sentence that comes back. Everything the tabs claim is testable without a
         browser, which is the point: a crop shows one book on one night. */
      correlationHTML: correlationHTML, factorsHTML: factorsHTML,
      stressHTML: stressHTML, weakLinksHTML: weakLinksHTML,
      eventsHTML: eventsHTML, concentrationHTML: concentrationHTML,
      coverageFoot: coverageFoot, labIntroHTML: labIntroHTML,
      scenarioHTML: scenarioHTML,
      W4_DEFAULT_DOLLARS: W4_DEFAULT_DOLLARS,
      /* the node shell's only way to seat a book/model without a DOM or a fetch */
      __setModel: function (data, wmap, lens) { DATA = data; LAST_WMAP = wmap || {}; LAST_LENS = lens || 'calm'; },
      __setCardJson: function (map) { CARD_JSON = map || {}; }
    };
  }
})();

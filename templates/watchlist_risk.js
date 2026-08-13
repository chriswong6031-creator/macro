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

    if (!RR.calm.ok) {
      publish({ shares: {}, covered: {}, bets: null, modeledN: 0,
                regime: regimeSentence(null) });
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

    publish({
      shares: shares, covered: covered,
      bets: clamp.bets, modeledN: active.held.length,
      cluster: cluster, ballast: ballast,
      because: because, clusterN: lead ? lead.members.length : 0,
      regime: regimeSentence(active.bookBeta && active.bookBeta.mkt),
      concHTML: concentrationHTML(active, cov)
    });
  }

  function publish(payload) {
    if (window.PF && window.PF.setBookRisk) { try { window.PF.setBookRisk(payload); } catch (e) {} }
    if (window.WS && window.WS.setRisk) {
      try { window.WS.setRisk({ concHTML: payload.concHTML || '' }); } catch (e) {}
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

  /* RETIRED IN W2 — the braid hero, its verdict/sub-card layer and the in-hero
     pre-trade check all rendered into #wri_hero, which the pinned workspace design
     replaces with the Book Seam + the Risk Center. They are deleted rather than left
     guarded: a render function whose host no longer exists is dead code that still
     reviews as live, and the Scenario Lab that replaces the pre-trade check is a
     declared W3 shell. The MEASUREMENT layer this file exists for — RiskCore reads,
     the lane engine, the chain index, enbClamp — is untouched and is what
     `publishBook` above and portfolio.js's drawer now consume. */

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
        BOOK_SHARES = {}; UNMODELED = {};
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
      noteJson: noteJson
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
      enbClamp: enbClamp, enbTipSuffix: enbTipSuffix, betCount: betCount
    };
  }
})();

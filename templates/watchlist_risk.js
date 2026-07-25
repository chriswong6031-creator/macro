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
  //  (exported for node tests); the wiring lives in loadChains / paintLanes / rail.
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
  function renderRail(bookBeta) {
    var host = document.getElementById('wri_rail');
    if (!host) return;
    var R = window.WRI_REGIME;
    if (!R || (!R.dominant_label_en && !R.state)) { host.style.display = 'none'; return; }
    var tint = STATE_TINT[(R.state || '').toLowerCase()] || 'tilt';
    var domEn = R.dominant_label_en || 'Market read', domZh = R.dominant_label_zh || R.dominant_label_en || '市场状态';
    var stateEn = stateWord(R.state, 'en'), stateZh = stateWord(R.state, 'zh');
    // book beta sentence (client) — only when we have a market beta to show
    var betaFrag = '';
    if (isNum(bookBeta)) {
      var bx = (Math.round(bookBeta * 10) / 10);
      betaFrag = '<span class="sep">·</span><span>' +
        te('your book moves about <b class="num">' + bx + '×</b> the market',
          '你的组合波动约为大盘的 <b class="num">' + bx + '×</b>') + '</span>';
    }
    host.style.display = 'flex';
    host.style.setProperty('--wri-rail-tint', 'var(--wri-' + tint + ')');
    host.className = 'wri-rail wri-rail-' + tint;
    // ONE appended chain sentence — only when a chain is propagating|expressed AND ≥1 book
    // name sits downstream of it. Links to the Cascade Monitor. The rail's single-line law
    // wins: this rides at the end, after the base state + beta, so the base read always shows.
    var chainFrag = '';
    var cs = railChainSentence(CHAINS_IDX, Object.keys(BOOK_SHARES));
    if (cs) {
      chainFrag = '<span class="sep">·</span><span class="wri-rail-chain">' +
        te(esc(cs.en), esc(cs.zh)) + ' <a href="transmission.html">' +
        te('cascade →', '传导链 →') + '</a></span>';
    }
    host.innerHTML =
      '<span class="dot"></span>' +
      '<b>' + te(esc(domEn) + ' — market on ' + esc(stateEn), esc(domZh) + '——市场' + esc(stateZh)) + '</b>' +
      betaFrag + chainFrag +
      '<a href="macro.html">' + te('market state →', '市场状态 →') + '</a>';
  }
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
  function renderHero(data, weights) {
    var hero = document.getElementById('wri_hero');
    if (!hero) return;
    var wmap = weights.wmap, universe = weights.universe;
    // filter the weights map to the universe the FX layer resolved (auto: portfolio
    // dollar values; manual: watchlist tickers). Build a {ticker->value} map.
    var wIn = {};
    universe.forEach(function (t) { var v = wmap[t]; wIn[t] = isNum(v) && v > 0 ? v : 1; });

    var RR = RiskCore.read(data, wIn);
    var cov = (RR.calm && RR.calm.coverage) || RiskCore.coverage(data, wIn);

    // empty / thin -> collapse hero to a single invitation line (empty = invitation)
    if (!RR.calm.ok) {
      var railBeta = null;
      renderRail(railBeta);
      hero.setAttribute('data-state', 'ok');
      hero.innerHTML = '<div class="wri-empty muted">' + te(
        'Add a few holdings and this reads what your book really is — how many independent bets you hold, and what moves together.',
        '添加几项持仓，这里会读出你的组合到底押了什么——你持有多少项独立押注，以及什么在同涨同跌。') + '</div>';
      hidePanel();  // no book -> keep the old fx panel hidden
      return;
    }

    // book market beta for the rail (client)
    var mktBeta = RR.calm.bookBeta && RR.calm.bookBeta.mkt;
    renderRail(mktBeta);

    // stash the model so lens toggle / lang flip re-render without recompute.
    // wIn + mode feed the W4 pre-trade check (hypothetical-book math + $ prefill).
    hero.__wri = { RR: RR, cov: cov, data: data, wmap: wIn, mode: weights.mode };
    var lens = hero.getAttribute('data-lens') || RR.defaultLens;
    if (!RR.hasStress) lens = 'calm';
    hero.setAttribute('data-lens', lens);
    paintHero(hero, lens);
  }

  function paintHero(hero, lens) {
    var st = hero.__wri; if (!st) return;
    var RR = st.RR, cov = st.cov;
    var abstain = cov.abstain;
    var active = lens === 'stress' && RR.hasStress ? RR.stress : RR.calm;
    var stateLens = RR.hasStress ? RR.stress : RR.calm;   // state chip pinned to stress read
    var enb = stateLens && stateLens.ok ? stateLens.enb : (RR.calm.enb);
    var stateKey = abstain ? null : RiskCore.enbState(enb);

    hero.setAttribute('data-state', stateKey || 'tilt');
    hero.className = 'tile wri wri-hero';

    // ---- header + verdict ----
    var asof = (window.WRI_REGIME && window.WRI_REGIME.asof) || (st.data && st.data.as_of) || '';
    var html = '<div class="eyebrow"><span>' + te('BOOK RISK', '组合风险') + '</span>' +
      '<span class="asof">' + te('AS OF ' + esc(asof), '截至 ' + esc(asof)) + '</span></div>';

    if (abstain) {
      html += '<div class="wri-verdict"><h2>' + te(
        'Not enough modeled names to read the book',
        '可建模持仓不足，暂不给出组合判读') + '</h2></div>';
      html += '<p class="wri-so">' + te(
        'Most of your book is in names the model doesn\'t cover, so a book-level read here would be misleading.',
        '你的组合大部分为模型未覆盖的标的，此处给出组合级判读会产生误导。');
      if (cov.unmodeled.length) html += ' ' + te('Not modeled: ', '未纳入模型：') +
        '<b class="num">' + esc(cov.unmodeled.join(', ')) + '</b>.';
      html += '</p>';
      hero.innerHTML = html;
      absorbFxPanel(hero, RR.calm);   // still offer the beta table drawer if computable
      return;
    }

    // clusters (patch-bay picture) under the ACTIVE lens; verdict count = ENB.
    var clusters = clustersFor(active);
    var verdict = verdictSentence(RR, active);

    var stateChip = stateChipText(stateKey);
    html += '<div class="wri-verdict"><h2 id="wri_verdict">' + verdict.h2 + '</h2>' +
      '<span class="wri-state">' + stateChip + '</span></div>';
    html += '<p class="wri-so">' + soWhat(active, cov) + '</p>';

    // ---- lens toggle (only when stress available) ----
    if (RR.hasStress) {
      var stressOn = lens === 'stress';
      var hint = lensHint(RR);
      html += '<div class="wri-lens"><div class="seg" role="group" aria-label="' +
        (isZh() ? '视角' : 'lens') + '">' +
        '<button id="wri_lensCalm" type="button" aria-pressed="' + (!stressOn) + '" data-lens="calm">' +
        te('ALL DAYS', '全部交易日') + '</button>' +
        '<button id="wri_lensStress" type="button" aria-pressed="' + stressOn + '" data-lens="stress">' +
        te('IN SELLOFFS', '跌市中') + '</button></div>' +
        (hint ? '<span class="hint">' + hint + '</span>' : '') + '</div>';
    }

    // ---- patch-bay + bucket fallback ----
    html += '<div class="wri-braid" role="img" aria-label="' + esc(braidAria(active, clusters)) + '">' +
      '<svg viewBox="0 0 1000 192" xmlns="http://www.w3.org/2000/svg" id="wri_braidSvg">' +
      '<g id="wri_guides"></g><g id="wri_threads"></g><g id="wri_railg"></g>' +
      '<g id="wri_ticks"></g><g id="wri_strands"></g></svg></div>' +
      '<div class="wri-buckets" id="wri_buckets"></div>';

    // ---- sub-cards ----
    html += subCards(RR, active, cov);

    // ---- pre-trade check (W4) — inside the hero, after the sub-cards, before
    //      the footnote. Hidden below 1 modeled holding (handled in wireWhatIf). ----
    html += whatIfRow(RR, active);

    // ---- footnote + method receipt ----
    html += footnote(RR, cov);

    hero.innerHTML = html;
    // paint the patch-bay from the active-lens model
    paintBraid(active, clusters);
    absorbFxPanel(hero, RR.calm);
    // wire the pre-trade check (suggestions + resolve); restores the user's typed
    // candidate across lens/lang re-renders from hero.__w4.
    wireWhatIf(hero, RR, active);
  }

  // clusters(active): the patch-bay PICTURE — names grouped by their dominant
  // factor-bet (RiskCore.factorBets), so market-driven names converge on one bus
  // while idiosyncratic / oil / rates names sit on their own. This is the visual
  // composition of the book (where the risk sits). Distinct from ρ≥0.70 twins
  // (the "Move as one" card) and from ENB (the verdict's independence count).
  //   [{ key, members[], share, hue, labelEn, labelZh, hedge }]
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
  function betCount(b) { return Math.max(1, Math.round(b.enb)); }
  function verdictSentence(RR, active) {
    var n = active.held.length;
    var lens = active.lens;
    var nBets = betCount(active);
    if (RR.hasStress && lens === 'calm' && RR.stress && RR.stress.ok) {
      var nStress = betCount(RR.stress);
      return { h2: te(
        'Calm days: about <span class="num">' + nBets + '</span> bets. Selloffs: <span class="num">' + nStress + '</span>',
        '平日约 <span class="num">' + nBets + '</span> 项押注；跌市中只剩 <span class="num">' + nStress + '</span> 项') };
    }
    var betWord = nBets === 1 ? 'bet' : 'bets';
    return { h2: te(
      'Your <span class="num">' + n + '</span> names move as about <span class="num">' + nBets + '</span> ' + betWord,
      '你的 <span class="num">' + n + '</span> 只持仓实际上约为 <span class="num">' + nBets + '</span> 项押注') };
  }

  // so-what: top factor + its share + consequence + what moves independently.
  // "Independent" = the factor-bet groups OTHER than the dominant one (their names
  // are the pieces not riding the top factor) — never the top-factor names.
  function soWhat(b, cov) {
    var top = b.topFactor, share = b.topFactorShare;
    var fmeta = FLABEL[top] || { en: top, zh: top };
    var bets = clustersFor(b);
    var dom = bets[0];   // dominant bet (largest risk share)
    // independent pieces = members of the non-dominant bets (cap 3 for the sentence)
    var indep = [];
    bets.slice(1).forEach(function (g) { g.members.forEach(function (t) { if (indep.length < 4) indep.push(t); }); });
    var indepEn = indep.length ? (indep.slice(0, 3).join(', ') + (indep.length > 3 ? '…' : '')) : '';
    var enParts = ['<b>' + esc(fmeta.en) + ' drives ' + pct0(share) + '</b> of your swings'];
    var zhParts = ['<b>' + esc(fmeta.zh) + '驱动你 ' + pct0(share) + ' 的波动</b>'];
    if (share >= 0.5) {
      enParts.push('if that one trade turns, most of this book turns with it');
      zhParts.push('这笔交易一转向，组合大部分随之转向');
    }
    if (indepEn) {
      enParts.push(esc(indepEn) + (indep.length === 1 ? ' is the piece moving on its own' : ' are the pieces moving on their own'));
      zhParts.push('只有 ' + esc(indepEn) + ' 在独立行走');
    }
    return te(enParts.join(' — ') + '.', zhParts.join('——') + '。');
  }

  function stateChipText(key) {
    var m = {
      ok: { en: 'Spread out', zh: '分散' }, tilt: { en: 'Leaning one way', zh: '偏向一侧' },
      conc: { en: 'Mostly one bet', zh: '高度集中' }, one: { en: 'Effectively one bet', zh: '实为单一押注' }
    };
    var w = m[key] || m.tilt;
    return te(w.en, w.zh);
  }

  function lensHint(RR) {
    if (RR.stressOnlyPairs && RR.stressOnlyPairs.length) {
      var p = RR.stressOnlyPairs[0];
      return te('on bad market days, ' + esc(p.a) + ' joins the ' + esc(p.b) + ' cluster',
        '大盘下跌日，' + esc(p.a) + ' 也并入 ' + esc(p.b) + ' 集群');
    }
    return '';
  }

  function braidAria(b, clusters) {
    var n = b.held.length, nb = clusters.length;
    return n + ' holdings connect into ' + nb + ' ' + (nb === 1 ? 'bet' : 'bets') + '.';
  }

  // ---- the three sub-cards -------------------------------------------
  function subCards(RR, active, cov) {
    var b = active;
    // 1) what drives your swings — factor shares (calm-model betas; use active lens)
    var top = b.rankedFactors.filter(function (k) { return (b.factorShare[k] || 0) > 0.005; }).slice(0, 5);
    var rows = top.map(function (k) {
      return frow(flabel(k), fhue(k), b.factorShare[k]);
    }).join('');
    rows += frow(isZh() ? '个股特有' : 'Stock-specific', 'var(--f-idio)', b.idioShareTotal);
    var enb = (RR.hasStress ? RR.stress : RR.calm).enb;
    var card1 = card('What drives your swings', '波动的来源',
      'Share of your book\'s day-to-day variance attributed to each factor, from a 9-factor model of daily moves. Measurement, not a forecast.',
      '各因子对组合日度波动方差的贡献，来自 9 因子日度模型。为测量而非预测。',
      rows +
      '<div class="wri-enb">' + te('effective bets ≈ <b class="num">' + enb.toFixed(1) + '</b> of ' + b.held.length + ' names',
        '有效押注数 ≈ <b class="num">' + enb.toFixed(1) + '</b>（共 ' + b.held.length + ' 只）') + '</div>' +
      '<div id="wri_fxhome"></div>');   // absorbed FX panel drawer mounts here

    // 2) move as one — twin clusters (active lens) + stress-only joins
    var twins = twinCards(RR, active);
    var card2 = card('Move as one', '同涨同跌',
      'Pairs whose modeled correlation is 0.70 or higher under the selected lens. "Selloffs only" pairs decouple on calm days but move together on bad market days.',
      '在所选视角下建模相关性达到 0.70 或以上的组合。“仅跌市”组合在平日相互独立，但在大盘下跌日同向移动。',
      twins);

    // 3) biggest single risks — top |MCTR share|
    var pr = b.rankedPositions.slice(0, 4).map(function (t) {
      var s = b.mctrShare[t] || 0, neg = s < 0;
      return '<div class="wri-crow' + (neg ? ' neg' : '') + '"><span class="tk">' + esc(t) + '</span>' +
        '<span class="wri-track" style="--hue:' + (neg ? 'var(--wri-ok)' : fhue(b.topFactor)) + '"><i style="width:' +
        Math.min(100, Math.abs(s) * 100).toFixed(0) + '%"></i></span>' +
        '<span class="pct">' + (neg ? '−' : '') + Math.abs(Math.round(s * 100)) + '%</span></div>';
    }).join('');
    var negName = b.rankedPositions.filter(function (t) { return (b.mctrShare[t] || 0) < 0; })[0];
    var note3 = negName ? '<div class="wri-note">' + te(esc(negName) + ' leans against the rest of the book',
      esc(negName) + ' 与组合其余部分反向而行') + '</div>' : '';
    var card3 = card('Biggest single risks', '最大单一风险',
      'Each position\'s contribution to the book\'s overall volatility (weight x co-movement). A small position in a volatile, correlated name can out-risk a large quiet one. Negative = moves against the rest of the book.',
      '各持仓对组合整体波动的贡献（权重 x 联动）。一个波动大、相关性高的小仓位，风险可能超过一个安静的大仓位。负值 = 与组合其余部分反向。',
      pr + note3);

    return '<div class="wri-sub">' + card1 + card2 + card3 + '</div>';
  }
  function card(hEn, hZh, tipEn, tipZh, body) {
    return '<div class="wri-card2"><h3>' + te(hEn, hZh) +
      '<span class="q" data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh) + '" tabindex="0" role="button" aria-label="' +
      esc(isZh() ? tipZh : tipEn) + '">?</span></h3>' + body + '</div>';
  }
  function frow(lab, hue, share) {
    return '<div class="wri-frow"><span class="lab">' + esc(lab) + '</span>' +
      '<span class="wri-track" style="--hue:' + hue + '"><i style="width:' + Math.min(100, share * 100).toFixed(0) + '%"></i></span>' +
      '<span class="pct">' + Math.round(share * 100) + '%</span></div>';
  }
  function twinCards(RR, active) {
    var calmClusters = active.clusters.filter(function (c) { return c.members.length >= 2; });
    var html = '';
    if (!calmClusters.length && !(RR.stressOnlyPairs && RR.stressOnlyPairs.length)) {
      return '<div class="wri-note" style="border:0;padding:0">' + te(
        'No two names move as one under this lens — your positions are pulling their own weight.',
        '在此视角下没有两只持仓同涨同跌——各仓位各自独立。') + '</div>';
    }
    calmClusters.forEach(function (c) {
      html += '<div class="wri-twin">' +
        c.members.map(function (t) { return '<span class="tk">' + esc(t) + '</span>'; }).join('') +
        '<span class="lnk">' + te('one trade', '同一笔交易') + '</span></div>';
    });
    // stress-only joins — dedupe by the joining name (a name can pair with several
    // cluster members; surface it once). Skip names already shown in a calm cluster.
    if (RR.stressOnlyPairs && RR.stressOnlyPairs.length) {
      var inCalm = {};
      calmClusters.forEach(function (c) { c.members.forEach(function (t) { inCalm[t] = 1; }); });
      var seen = {};
      RR.stressOnlyPairs.forEach(function (p) {
        // the "joining" name is whichever of the pair is NOT already in a calm cluster
        var joiner = inCalm[p.a] ? p.b : p.a;
        if (seen[joiner] || Object.keys(seen).length >= 3) return;
        seen[joiner] = 1;
        html += '<div class="wri-twin stress"><span class="tk">' + esc(joiner) + '</span>' +
          '<span class="lnk">' + te('joins in selloffs', '跌市中并入') + '</span>' +
          '<span class="why">' + te('holds up on calm days, falls with the cluster on bad ones',
            '平日独立，大跌日与集群同跌') + '</span></div>';
      });
    }
    return '<div class="wri-twins">' + html + '</div>';
  }

  function footnote(RR, cov) {
    var unmod = cov.unmodeled.length;
    var unEn = unmod ? (' ' + unmod + ' name' + (unmod > 1 ? 's' : '') + ' (' + esc(cov.unmodeled.join(', ')) +
      ') ' + (unmod > 1 ? 'aren\'t' : 'isn\'t') + ' modeled and sit outside these numbers.') : '';
    var unZh = unmod ? (' ' + unmod + ' 只（' + esc(cov.unmodeled.join(', ')) + '）未纳入模型，不在上述数字内。') : '';
    var clampEn = (RR.calm.clampDisclose) ? ' A small share of variance nets out and is not shown.' : '';
    var clampZh = (RR.calm.clampDisclose) ? ' 少量方差相互抵消，未予显示。' : '';
    var methodEn = 'Betas fit on 252 trading days' + (RR.hasStress
      ? '; the selloffs lens re-estimates factor co-movement on the worst quarter of market days over 3 years'
      : '') + '; stock-specific risk estimated on all days. Full method on the stock pages.';
    var methodZh = 'Beta 基于 252 个交易日拟合' + (RR.hasStress
      ? '；跌市视角在三年内最差四分位的大盘交易日上重估因子联动' : '') + '；个股特有风险按全部交易日估计。';
    return '<div class="wri-foot">' +
      '<span class="l-en">Measurement from a 9-factor model of daily moves — not a forecast, and not a recommendation.' + unEn + clampEn +
      ' <span class="q" data-tip-en="' + esc(methodEn) + '" data-tip-zh="' + esc(methodZh) +
      '" tabindex="0" role="button">method</span></span>' +
      '<span class="l-zh">基于 9 因子日度模型的测量——并非预测，也非建议。' + unZh + clampZh +
      ' <span class="q" data-tip-en="' + esc(methodEn) + '" data-tip-zh="' + esc(methodZh) +
      '" tabindex="0" role="button">方法</span></span></div>';
  }

  // =========================================================================
  //  W4 — the pre-trade check (what-if diagnostic). Operator-signed NWP-U18
  //  carve-out (WRI-R3): the user proposes ONE candidate (ticker + optional $
  //  size); we print the SAME descriptive statistics for the hypothetical book.
  //  The user constructs; WE DESCRIBE. No optimizer, no suggested weight/size, no
  //  advice verbs — ever. Deltas are NEVER tinted (a diversification delta is a
  //  measurement, not a verdict). Math is RiskCore.whatIf (pure composition of
  //  book(), no new estimator); result respects the surface's active lens.
  // =========================================================================
  var W4_DEFAULT_DOLLARS = 10000;   // manual-mode fallback (no real dollars exist)

  // static markup: header + input row + (empty) live result container. The row
  // is present only when the book has ≥1 modeled holding (wireWhatIf hides it
  // otherwise — the empty-book state).
  function whatIfRow(RR, active) {
    var tipEn = 'Type a name to see what it would do to the book’s structure. A measurement of the hypothetical book — not a recommendation.';
    var tipZh = '输入代码，查看它对组合结构的影响。对假设组合的测量——并非建议。';
    var subEn = 'assuming a position about the size of your average holding — adjust to your intent';
    var subZh = '默认按你的平均持仓规模——可自行调整';
    return '<div class="wri-w4" id="wri_w4">' +
      '<div class="wri-w4-head"><span>' + te('PRE-TRADE CHECK', '试仓检查') + '</span>' +
      '<span class="q" data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh) +
      '" tabindex="0" role="button" aria-label="' + esc(isZh() ? tipZh : tipEn) + '">?</span></div>' +
      '<div class="wri-w4-in">' +
      '<div class="wri-w4-tk"><input id="wri_w4_tk" type="text" autocomplete="off" ' +
      'autocapitalize="characters" placeholder="' + (isZh() ? '代码或名称' : 'ticker or name') +
      '" aria-label="' + (isZh() ? '候选代码' : 'candidate ticker') + '">' +
      '<div class="wri-w4-sugg" id="wri_w4_sugg"></div></div>' +
      '<div class="wri-w4-amt"><div class="wri-w4-amtrow"><span class="cur">$</span>' +
      '<input id="wri_w4_amt" type="text" inputmode="numeric" aria-label="' +
      (isZh() ? '仓位金额' : 'position amount in dollars') + '"></div>' +
      '<span class="sub">' + te(subEn, subZh) + '</span></div>' +
      '<button class="wri-w4-clear" id="wri_w4_clear" type="button" style="display:none">' +
      te('clear', '清除') + '</button></div>' +
      '<div class="wri-w4-res" id="wri_w4_res" aria-live="polite"></div></div>';
  }

  // average position size for the $ prefill. Averaged from the book's OWN per-name
  // weight values so the candidate is scaled to the book and the deltas are
  // meaningful (a size that dwarfs every holding would read as "100% of the swing"
  // regardless of the name). AUTO mode: those values are real dollars, so the
  // prefill is the real average holding. MANUAL mode: the book carries only
  // relative weights (equal-weight => 1 each); scaling the candidate to that same
  // average keeps it comparable, and we express it as a round default only when
  // the weights are unit-scale (≤ a few) so the $ field never shows a bare "1".
  function avgPositionSize(hero) {
    var st = hero.__wri; if (!st) return W4_DEFAULT_DOLLARS;
    var vals = [];
    if (st.wmap) Object.keys(st.wmap).forEach(function (t) {
      var v = st.wmap[t]; if (isNum(v) && v > 0) vals.push(v);
    });
    if (!vals.length) return W4_DEFAULT_DOLLARS;
    var m = vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
    // real dollars (auto, or a manual editor in dollars) -> use the average as-is.
    // unit-scale weights (manual equal-weight, avg ~1) carry no dollar meaning, so
    // show a round nominal ($10k) — but the RESOLVE always re-scales to the book's
    // average weight so the delta stays comparable regardless of what's displayed.
    if (m >= 100) return Math.max(1, Math.round(m));
    return W4_DEFAULT_DOLLARS;
  }
  // the dollar size to actually FEED whatIf: in a real-dollar book it's the typed
  // amount; in a unit-weight book (manual equal-weight) the typed "$10,000" is
  // nominal, so we translate it into the book's own weight scale — the candidate
  // is sized at (typed / displayed-default) × average-book-weight, i.e. "about one
  // average holding" when left at the prefill. Keeps the what-if honest either way.
  function effectiveDollars(hero, typed) {
    var st = hero.__wri; if (!st) return typed;
    var vals = [];
    if (st.wmap) Object.keys(st.wmap).forEach(function (t) {
      var v = st.wmap[t]; if (isNum(v) && v > 0) vals.push(v);
    });
    if (!vals.length) return typed;
    var m = vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
    if (m >= 100) return typed;                 // real-dollar book: feed dollars directly
    // unit-weight book: map the displayed $ onto the book's weight scale so the
    // candidate is ~one average holding at the prefill, and scales linearly if edited.
    var disp = avgPositionSize(hero) || W4_DEFAULT_DOLLARS;
    return (typed / disp) * m;
  }
  function fmtDollars(n) { return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  function parseDollars(s) {
    var v = parseFloat(String(s == null ? '' : s).replace(/[^0-9.]/g, ''));
    return isNum(v) && v > 0 ? v : 0;
  }

  function wireWhatIf(hero, RR, active) {
    var row = document.getElementById('wri_w4'); if (!row) return;
    // empty-book state: hide the row below 1 modeled holding.
    var modeledN = (active && active.held) ? active.held.length : 0;
    if (modeledN < 1) { row.style.display = 'none'; return; }
    row.style.display = '';

    var tk = document.getElementById('wri_w4_tk');
    var amt = document.getElementById('wri_w4_amt');
    var sugg = document.getElementById('wri_w4_sugg');
    var clear = document.getElementById('wri_w4_clear');
    if (!tk || !amt || !sugg) return;

    // restore prior state (survives lens/lang re-render); default $ = avg holding.
    // The typed amount is sticky ONLY when the user hand-edited it (userAmt) — a
    // lens/lang flip keeps their number, but a book change (e.g. weights→dollars)
    // refreshes the prefill to the new average holding.
    var prior = hero.__w4 || {};
    var avg = avgPositionSize(hero);
    var keepAmt = prior.userAmt && isNum(prior.dollars) && prior.dollars > 0;
    amt.value = fmtDollars(keepAmt ? prior.dollars : avg);
    if (prior.ticker) { tk.value = prior.ticker; clear.style.display = '';
      // re-sync the stashed dollars to the (possibly refreshed) default
      if (!keepAmt) hero.__w4.dollars = avg; }

    var sel = -1, items = [];
    // suggestions from the SAME index the watchlist search uses (SD.loadIndex).
    function renderSugg() {
      var v = tk.value.trim().toLowerCase(); sel = -1;
      if (!v || !W4_INDEX) { sugg.style.display = 'none'; return; }
      items = W4_INDEX.filter(function (x) {
        return x.t.toLowerCase().indexOf(v) === 0 ||
          x.n.toLowerCase().indexOf(v) >= 0 || (x.s || '').toLowerCase().indexOf(v) >= 0;
      }).sort(function (a, b) {
        var ae = a.t.toLowerCase() === v ? -1 : 0, be = b.t.toLowerCase() === v ? -1 : 0;
        if (ae !== be) return ae - be;
        var ap = a.t.toLowerCase().indexOf(v) === 0 ? 0 : 1, bp = b.t.toLowerCase().indexOf(v) === 0 ? 0 : 1;
        return ap - bp || a.t.localeCompare(b.t);
      }).slice(0, 10);
      sugg.innerHTML = items.map(function (x, i) {
        return '<div data-i="' + i + '"><b>' + esc(x.t) + '</b><small>' + esc(x.n) +
          (x.s ? ' · ' + esc(x.s) : '') + '</small></div>';
      }).join('');
      sugg.style.display = items.length ? 'block' : 'none';
    }
    function pickSugg(i) {
      var x = items[i] || (items[0]); if (!x) { commit(tk.value.trim().toUpperCase()); return; }
      sugg.style.display = 'none';
      commit(x.t);
    }
    // commit a candidate: stash state + resolve. Resolve to the index's CANONICAL
    // ticker (x.t) so it matches the factor_betas.json / stockdata keys exactly
    // (GC=F, BRK-B, ^GSPC keep their case/symbols — never blindly uppercased).
    function commit(ticker) {
      if (!ticker) return;
      var canon = canonTicker(ticker);
      var wasUserAmt = !!(hero.__w4 && hero.__w4.userAmt);   // preserve hand-edited size
      tk.value = canon;
      hero.__w4 = { ticker: canon, dollars: parseDollars(amt.value) || avg, userAmt: wasUserAmt };
      clear.style.display = '';
      resolveWhatIf(hero, canon);
    }

    ensureW4Index(function () { /* index ready; input handlers already live */ });

    tk.addEventListener('input', renderSugg);
    tk.addEventListener('keydown', function (e) {
      if (sugg.style.display !== 'none') {
        var divs = sugg.querySelectorAll('div');
        if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, divs.length - 1); e.preventDefault(); divs.forEach(function (d, i) { d.classList.toggle('sel', i === sel); }); return; }
        if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); e.preventDefault(); divs.forEach(function (d, i) { d.classList.toggle('sel', i === sel); }); return; }
        if (e.key === 'Escape') { sugg.style.display = 'none'; return; }
      }
      if (e.key === 'Enter') { e.preventDefault(); pickSugg(sel >= 0 ? sel : 0); }
    });
    sugg.addEventListener('mousedown', function (e) {
      var d = e.target.closest('div[data-i]'); if (d) { e.preventDefault(); pickSugg(+d.dataset.i); }
    });
    // amount edits re-resolve live (only when a candidate is set). Mark the size
    // as user-owned so a later lens/lang flip keeps it (userAmt).
    amt.addEventListener('input', function () {
      if (!hero.__w4 || !hero.__w4.ticker) return;
      hero.__w4.dollars = parseDollars(amt.value) || avg;
      hero.__w4.userAmt = true;
      resolveWhatIf(hero, hero.__w4.ticker);
    });
    clear.addEventListener('click', function () {
      hero.__w4 = null; tk.value = ''; sugg.style.display = 'none';
      amt.value = fmtDollars(avg); clear.style.display = 'none';
      var res = document.getElementById('wri_w4_res'); if (res) res.innerHTML = '';
      tk.focus();
    });

    // re-resolve on a lens/lang re-render if a candidate is already set
    if (hero.__w4 && hero.__w4.ticker) resolveWhatIf(hero, hero.__w4.ticker);
  }

  // resolve a typed string to the index's canonical ticker key (exact match,
  // then case-insensitive), else fall back to the trimmed input as-is (so an
  // unmodeled name still resolves to the honest-null branch, never crashes).
  function canonTicker(s) {
    var raw = String(s || '').trim();
    if (!raw) return raw;
    if (W4_BY && W4_BY[raw]) return raw;
    var up = raw.toUpperCase();
    if (W4_BY && W4_BY[up]) return up;
    if (W4_BY) {
      var lo = raw.toLowerCase();
      var hit = Object.keys(W4_BY).filter(function (t) { return t.toLowerCase() === lo; })[0];
      if (hit) return hit;
    }
    return up;
  }

  // resolve + render the neutral result block for the current candidate. Reads
  // the ACTIVE lens off the hero so the deltas match what the surface shows.
  function resolveWhatIf(hero, ticker) {
    var st = hero.__wri; if (!st) return;
    var res = document.getElementById('wri_w4_res'); if (!res) return;
    var lens = hero.getAttribute('data-lens') || st.RR.defaultLens;
    if (!st.RR.hasStress) lens = 'calm';
    var typed = (hero.__w4 && hero.__w4.dollars) || avgPositionSize(hero);
    // feed whatIf the size on the BOOK's own scale (dollars in a real-dollar book;
    // translated to the weight scale in a unit-weight manual book) so the delta is
    // comparable — see effectiveDollars.
    var dollars = effectiveDollars(hero, typed);
    var wi = RiskCore.whatIf(st.data, st.wmap, ticker, dollars, lens);
    res.innerHTML = whatIfResult(wi);
    // the candidate's own lane chips (reuse the L1 lane engine) mount async
    mountCandidateChips(res, ticker);
  }

  // build the neutral result lines. NUMBERS mono, arrows plain, deltas untinted.
  function whatIfResult(wi) {
    var T = esc(wi.ticker || '');
    // unmodeled candidate -> honest null, no fabricated numbers (WRI-R6/R3).
    if (!wi.modeled) {
      return '<p class="ln"><span class="dot"></span><span class="null">' +
        te('<span class="tk">' + T + '</span> — not in the risk model, price signals only.',
          '<span class="tk">' + T + '</span> —— 未纳入风险模型，仅价格信号。') +
        '</span></p>';
    }
    var before = wi.before, after = wi.after;
    if (!after || !after.ok) {
      // e.g. the candidate is the only modeled name (thin after-book) — stay honest.
      return '<p class="ln"><span class="dot"></span><span class="null">' +
        te('Add another modeled holding to compare the book with and without ' + '<span class="tk">' + T + '</span>.',
          '再添加一项可建模持仓，以比较加入 <span class="tk">' + T + '</span> 前后的组合。') +
        '</span></p>';
    }
    // Line 1: bets before->after · top-factor share before->after
    var enb0 = before && before.ok ? Math.max(1, Math.round(before.enb)) : null;
    var enb1 = Math.max(1, Math.round(after.enb));
    var topK = after.topFactor;
    var topLab = flabel(topK);
    var a0 = before && before.ok ? Math.round((before.factorShare[topK] || 0) * 100) : null;
    var a1 = Math.round((after.factorShare[topK] || 0) * 100);
    var enbFrag = (enb0 != null)
      ? '<span class="num">' + enb0 + '</span><span class="arw">→</span><span class="num">' + enb1 + '</span>'
      : '<span class="num">' + enb1 + '</span>';
    var shFrag = (a0 != null)
      ? '<span class="num">' + a0 + '%</span><span class="arw">→</span><span class="num">' + a1 + '%</span>'
      : '<span class="num">' + a1 + '%</span>';
    var line1 = '<p class="ln"><span class="dot"></span><span>' + te(
      'With <span class="tk">' + T + '</span>: effectively ' + enbFrag + ' bets · ' + esc(topLab) + ' share ' + shFrag,
      '加入 <span class="tk">' + T + '</span>：有效押注数 ' + enbFrag + ' · ' + esc(topLab) + '占比 ' + shFrag
    ) + '</span></p>';

    // Line 2 (conditional): twin membership OR hedge lean
    var line2 = '';
    var cand = wi.candidate;
    if (cand.hedge) {
      line2 = '<p class="ln"><span class="dot"></span><span>' + te(
        '<span class="tk">' + T + '</span> would lean against the rest of the book',
        '<span class="tk">' + T + '</span> 将与组合其余部分反向') + '</span></p>';
    } else if (cand.twinWith && cand.twinWith.length) {
      var withT = esc(cand.twinWith.slice(0, 3).join(', '));
      var inSell = (wi.lens === 'stress');
      line2 = '<p class="ln"><span class="dot"></span><span>' + te(
        'moves with <span class="tk">' + withT + '</span>' + (inSell ? ' in selloffs' : ''),
        '与 <span class="tk">' + withT + '</span> 同步' + (inSell ? '（跌市中）' : '')) + '</span></p>';
    }

    // Line 3: candidate's own swing share + rank
    var c = Math.abs(Math.round((cand.mctrShare || 0) * 100));
    var k = cand.rank || after.rankedPositions.length;
    var line3 = '<p class="ln"><span class="dot"></span><span>' + te(
      'would carry about <span class="num">' + c + '%</span> of the book’s swing (#<span class="num">' + k + '</span> largest)',
      '约占组合波动的 <span class="num">' + c + '%</span>（第<span class="num">' + k + '</span>大）') + '</span></p>';

    return line1 + line2 + line3 + '<div class="wri-lanes" id="wri_w4_chips"></div>';
  }

  // reuse the L1 lane engine to build the candidate's own chips (async — its
  // stockdata JSON loads on demand; degrades to nothing if absent).
  function mountCandidateChips(res, ticker) {
    var host = res.querySelector('#wri_w4_chips'); if (!host) return;
    window.SD.loadTicker(ticker).then(function (j) {
      if (!host.isConnected || !j) return;
      var lanes = laneRead(j);
      var chips = [];
      LANES.forEach(function (kk) {
        var L = lanes[kk];
        if (L && L.chip) chips.push('<span class="wri-chip ' + (L.chip.cls || '') + '">' +
          te(esc(L.chip.en), esc(L.chip.zh)) + '</span>');
      });
      host.innerHTML = chips.join('');
    });
  }

  // shared search index for the what-if input (same source as the watchlist
  // search: stockdata/index.json via SD.loadIndex). Loaded once, cached.
  var W4_INDEX = null, W4_BY = null, W4_INDEX_LOADING = null;
  function ensureW4Index(cb) {
    if (W4_INDEX) { cb && cb(); return; }
    if (!W4_INDEX_LOADING) {
      W4_INDEX_LOADING = window.SD.loadIndex().then(function (r) {
        W4_INDEX = r.list; W4_BY = r.byTicker; return r;
      }).catch(function () { W4_INDEX = []; W4_BY = {}; });
    }
    W4_INDEX_LOADING.then(function () { cb && cb(); });
  }

  // ---- patch-bay painter (data-driven port of the mockup SVG builder) -----
  // model rows: NAMES = [{t, share (signed MCTR share), cl (cluster index)}].
  function paintBraid(active, clusters) {
    var svg = document.getElementById('wri_braidSvg'); if (!svg) return;
    var names = active.rankedPositions.map(function (t) { return t; });
    // stable left-to-right order = ranked positions; cluster index per name
    var clOf = {};
    clusters.forEach(function (c, i) { c.members.forEach(function (t) { clOf[t] = i; }); });
    var NAMES = names.map(function (t) { return { t: t, share: active.mctrShare[t] || 0, cl: clOf[t] }; });
    var n = NAMES.length;
    var xs = {}; for (var i = 0; i < n; i++) xs[NAMES[i].t] = 64 + (W - 128) * (n > 1 ? i / (n - 1) : 0.5);
    // order clusters as they first appear L->R; segment widths ∝ cluster share
    var order = [], seen = {};
    NAMES.forEach(function (m) { if (!seen[m.cl]) { seen[m.cl] = 1; order.push(m.cl); } });
    var shares = {}, members = {};
    order.forEach(function (c) { shares[c] = 0; members[c] = []; });
    NAMES.forEach(function (m) { shares[m.cl] += Math.abs(m.share); members[m.cl].push(m.t); });
    var total = 0; order.forEach(function (c) { total += shares[c]; }); total = total || 1;
    var gap = 24, usable = W - 128 - gap * (order.length - 1), sumw = 0, ws = {};
    order.forEach(function (c) { ws[c] = Math.max(56, usable * shares[c] / total); sumw += ws[c]; });
    var scale = usable / (sumw || 1), x = 64, cx = {};
    order.forEach(function (c) { var w = ws[c] * scale; cx[c] = { x: x, w: w }; x += w + gap; });
    var dom = order.reduce(function (a, b) { return shares[a] >= shares[b] ? a : b; }, order[0]);

    var guides = '', threads = '', ticks = '', strands = '';
    var railg = '<line class="rail" x1="40" y1="' + RAILY + '" x2="' + (W - 40) + '" y2="' + RAILY + '"/>';
    NAMES.forEach(function (m, i) {
      var xp = xs[m.t], c = cx[m.cl], neg = m.share < 0;
      var k = members[m.cl].indexOf(m.t), nm = members[m.cl].length;
      var bx = c.x + c.w * (k + 0.5) / nm;
      var fil = Math.min(6, 1 + Math.round(Math.abs(m.share) * 14));
      var hue = clusters[m.cl] ? clusters[m.cl].hue : 'var(--f-idio)';
      var col = cmix(hue, m.cl === dom ? 72 : 48, 'var(--muted)');
      guides += '<line class="guide" x1="' + xp + '" y1="' + (TOPY - 4) + '" x2="' + xp + '" y2="' + (RAILY - 4) + '"/>';
      ticks += '<text class="tick' + (neg ? ' neg' : '') + '" x="' + xp + '" y="12" text-anchor="middle">' + esc(m.t) + (neg ? ' ⇄' : '') + '</text>';
      for (var f = 0; f < fil; f++) {
        var dx = (f - (fil - 1) / 2) * 2.6;
        threads += '<path class="cord' + (neg ? ' hedge' : '') + '" stroke="' + col + '" style="animation-delay:' + (i * 45 + f * 18) + 'ms" d="' +
          'M' + (xp + dx) + ',' + TOPY + ' L' + (xp + dx) + ',' + BENDY +
          ' C' + (xp + dx) + ',' + (BENDY + 34) + ' ' + (bx + dx * 0.4) + ',' + (RAILY - 30) + ' ' + (bx + dx * 0.4) + ',' + RAILY + '"/>';
      }
    });
    order.forEach(function (cl, j) {
      var c = cx[cl], isDom = cl === dom, cluster = clusters[cl];
      var hue = cluster ? cluster.hue : 'var(--f-idio)';
      var col = isDom ? hue : cmix(hue, 55, 'var(--muted)');
      var y = (c.w < 96 && j % 2) ? LABY2 : LABY;
      var lab = cluster ? (isZh() ? cluster.labelZh : cluster.labelEn) : members[cl][0];
      if (cluster && cluster.hedge) lab = lab + ' ⇄';
      strands += '<g' + (isDom ? ' class="seg-dom"' : '') + '>' +
        '<line class="segbase" x1="' + c.x + '" y1="' + RAILY + '" x2="' + (c.x + c.w) + '" y2="' + RAILY + '" stroke="' + col + '"/>' +
        '<line class="segtick" x1="' + c.x + '" y1="' + (RAILY - 4) + '" x2="' + c.x + '" y2="' + (RAILY + 4) + '" stroke="' + col + '"/>' +
        '<line class="segtick" x1="' + (c.x + c.w) + '" y1="' + (RAILY - 4) + '" x2="' + (c.x + c.w) + '" y2="' + (RAILY + 4) + '" stroke="' + col + '"/></g>' +
        '<text class="wri-strandlab' + (isDom ? ' dom' : '') + '" x="' + (c.x + c.w / 2) + '" y="' + y + '" text-anchor="middle">' + esc(lab) + '</text>';
    });
    svg.querySelector('#wri_guides').innerHTML = guides;
    svg.querySelector('#wri_threads').innerHTML = threads;
    svg.querySelector('#wri_railg').innerHTML = railg;
    svg.querySelector('#wri_ticks').innerHTML = ticks;
    svg.querySelector('#wri_strands').innerHTML = strands;

    // bucket-list fallback (≤560px)
    var bhtml = '';
    order.forEach(function (cl) {
      var cluster = clusters[cl];
      var lab = cluster ? (isZh() ? cluster.labelZh : cluster.labelEn) : members[cl][0];
      var hue = cluster ? cluster.hue : 'var(--f-idio)';
      var tks = members[cl].join(' · ');
      var showTks = (tks !== lab.replace(' ⇄', ''));
      bhtml += '<div class="wri-bucket"><span class="swatch" style="background:' + hue + '"></span>' +
        '<b style="font-size:12px">' + esc(lab) + '</b>' + (showTks ? ' <span class="tks">' + esc(tks) + '</span>' : '') + '</div>';
    });
    var bEl = document.getElementById('wri_buckets'); if (bEl) bEl.innerHTML = bhtml;

    // first-paint-only draw-in animation
    var braid = document.querySelector('.wri-braid');
    if (braid && !animatedOnce && !prefersReduced()) {
      braid.classList.add('animate');
      animatedOnce = true;
      setTimeout(function () { braid.classList.remove('animate'); }, 1400);
    }
  }
  function cmix(hue, p, base) { return 'color-mix(in srgb, ' + hue + ' ' + p + '%, ' + base + ')'; }
  function prefersReduced() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  // ---- absorb the old #fx_panel into sub-card 1's <details> drawer --------
  // factor_exposure.js renders into #fx_panel; we relocate that node into
  // #wri_fxhome inside a collapsed <details> so the full beta table / shocks /
  // weight editor stay a Tier-2 home (spec §2, §6.1). The panel keeps working.
  function absorbFxPanel(hero, calm) {
    var home = document.getElementById('wri_fxhome');
    var fx = document.getElementById('fx_panel');
    if (!home || !fx) return;
    // wrap in a details the first time; move the live #fx_panel inside it
    var det = home.querySelector('details.wri-fxdrawer');
    if (!det) {
      det = document.createElement('details');
      det.className = 'wri-fxdrawer';
      det.innerHTML = '<summary>' + te('Full factor detail — beta table, shocks, weights',
        '完整因子明细——贝塔表、情景冲击、权重') + '</summary>';
      home.appendChild(det);
    }
    if (fx.parentNode !== det) { fx.style.display = ''; det.appendChild(fx); }
  }
  function hidePanel() {
    var fx = document.getElementById('fx_panel');
    if (fx) fx.style.display = 'none';
  }

  // =========================================================================
  //  L1 card decoration — add lane chips + role badge + drawer to each card
  // =========================================================================
  function decorateCards() {
    var cards = document.querySelectorAll('#wl_list .wl-card[data-t]');
    cards.forEach(function (card) {
      var t = card.getAttribute('data-t');
      if (card.querySelector('.wri-lanes')) return;   // already decorated this render
      window.SD.loadTicker(t).then(function (j) {
        if (!card.isConnected) return;
        card.__wriJson = j;
        paintLanes(card, j);
      });
    });
  }
  function paintLanes(card, j) {
    if (card.querySelector('.wri-lanes')) card.querySelector('.wri-lanes').remove();
    if (card.querySelector('.wri-drawer')) card.querySelector('.wri-drawer').remove();
    var lanes = laneRead(j);
    var role = roleBadge(lanes);
    // chips at rest: max 3 real-signal chips; the rest live in the drawer
    var chips = [];
    LANES.forEach(function (k) {
      var L = lanes[k];
      if (L && L.chip) chips.push('<span class="wri-chip ' + (L.chip.cls || '') + '">' +
        te(esc(L.chip.en), esc(L.chip.zh)) + '</span>');
    });
    var tkr = card.getAttribute('data-t');
    // transmission chain chip (INFO tier — deliberately NOT hot/red): the furthest-progressed
    // armed chain this name sits downstream of. At-rest cap = 1 chain chip; the rest live in
    // the drawer. Display-only WATCH context, never a signal.
    var chainMs = CHAINS_IDX[tkr];
    var chainLead = furthestChain(chainMs);
    if (chainLead) {
      var drv = chainDriver(chainLead);
      chips.push('<span class="wri-chip info">' +
        te(esc(drv.en) + ' risk building', esc(drv.zh) + '风险酝酿') + '</span>');
    }
    // book-risk share chip (info, from L2) if we have it for this name
    var shareChip = BOOK_SHARES[tkr];
    if (shareChip != null) {
      var pctv = Math.round(Math.abs(shareChip) * 100);
      chips.unshift('<span class="wri-chip info">' + te(pctv + '% of book risk', '占组合风险' + pctv + '%') + '</span>');
    } else if (UNMODELED[tkr]) {
      // out-of-model name: keep its price-tier lanes, but say what's missing (WRI-R6)
      chips.push('<span class="wri-chip info">' +
        te('price signals only — not in the risk model', '仅价格信号——未纳入风险模型') + '</span>');
    }
    var shown = chips.slice(0, 3);
    var lanesHtml = '<div class="wri-lanes">' + shown.join('') +
      '<button class="wri-more" type="button" aria-expanded="false">' + te('details', '详情') + '</button></div>';
    // role badge -> top-right of .wl-top
    if (role) {
      var top = card.querySelector('.wl-top');
      if (top && !top.querySelector('.wri-role')) {
        var span = document.createElement('span');
        span.className = 'wri-role wri-role-' + role.kind;
        span.innerHTML = te(esc(role.en), esc(role.zh));
        top.appendChild(span);
      }
    }
    // drawer: one row per lane
    var rows = LANES.map(function (k) {
      var L = lanes[k], lbl = LANE_LABEL[k];
      var stCls = L.state, stTok = stateToken(L.state);
      return '<div class="wri-lrow"><span class="ln">' + te(lbl.en, lbl.zh) + '</span>' +
        '<span class="st ' + stCls + '">' + stTok + '</span>' +
        '<span class="rs">' + te(esc(L.en), esc(L.zh)) + '</span></div>';
    }).join('');
    // chain drawer rows — ALL armed chains this name sits downstream of (the chip shows only
    // the furthest along; the drawer carries the rest). Each is a plain review read, never a call.
    rows += chainDrawerRows(chainMs);
    var asof = j && j.asof ? ('<div class="asof">' + te('signals as of ' + esc(j.asof), '信号截至 ' + esc(j.asof)) + '</div>') : '';
    var drawerHtml = '<div class="wri-drawer">' + rows + asof + '</div>';
    // insert after .wl-enrich (or .wl-sig)
    var anchor = card.querySelector('.wl-enrich') || card.querySelector('.wl-sig');
    if (anchor) {
      anchor.insertAdjacentHTML('afterend', lanesHtml + drawerHtml);
    } else {
      card.insertAdjacentHTML('beforeend', lanesHtml + drawerHtml);
    }
    var more = card.querySelector('.wri-more');
    if (more) more.addEventListener('click', function () {
      var d = card.querySelector('.wri-drawer');
      var open = d.classList.toggle('open');
      more.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
  function stateToken(s) {
    if (s === 'ok') return 'OK';
    if (s === 'watch') return te('WATCH', '关注');
    if (s === 'elev') return te('ELEVATED', '升高');
    return te('n/a', '未覆盖');
  }
  // repaint decorations in the current language without refetch (lang flip)
  function repaintCards() {
    document.querySelectorAll('#wl_list .wl-card[data-t]').forEach(function (card) {
      if ('__wriJson' in card) {
        // strip role badge too (rebuilt in paintLanes)
        var role = card.querySelector('.wri-role'); if (role) role.remove();
        paintLanes(card, card.__wriJson);
      }
    });
  }

  // =========================================================================
  //  Portfolio table columns — Share of book risk + Risk read
  // =========================================================================
  var BOOK_SHARES = {};   // {ticker -> mctr share} from the last L2 read (for chips + table)
  var BOOK_ROLES = {};    // {ticker -> role badge} from lane reads (filled lazily)
  var UNMODELED = {};     // {ticker -> 1} names present in the list but absent from the factor model
  function decorateTable() {
    var table = document.querySelector('#pf_desk table');
    if (!table) return;
    // header: insert two columns before the trailing action <th> (last child)
    var headRow = table.querySelector('thead tr');
    if (headRow && !headRow.querySelector('.wri-th-share')) {
      var thShare = document.createElement('th');
      thShare.className = 'wri-th-share'; thShare.style.textAlign = 'right';
      thShare.innerHTML = te('Share of book risk', '组合风险占比');
      var thRead = document.createElement('th');
      thRead.className = 'wri-th-read';
      thRead.innerHTML = te('Risk read', '风险状态');
      var lastTh = headRow.lastElementChild;
      headRow.insertBefore(thShare, lastTh);
      headRow.insertBefore(thRead, lastTh);
    }
    // body rows: pf_rows carries data via td:first-child = ticker. Build the two
    // cells once, then UPDATE their contents on later passes (share + role can
    // arrive after the row first renders — the card's lane read is async).
    table.querySelectorAll('tbody tr').forEach(function (tr) {
      var tkCell = tr.querySelector('td'); if (!tkCell) return;
      var t = (tkCell.textContent || '').trim().toUpperCase();
      var share = BOOK_SHARES[t], role = BOOK_ROLES[t];
      var tdShare = tr.querySelector('.wri-td-share');
      var tdRead = tr.querySelector('.wri-td-read');
      var fresh = !tdShare;
      if (fresh) { tdShare = document.createElement('td'); tdRead = document.createElement('td'); }
      // share cell
      tdShare.className = 'tabnum wri-td-share';
      if (share != null) {
        var neg = share < 0, pctv = Math.abs(Math.round(share * 100));
        // mini-bar width is the share relative to the book's largest |share|
        var barW = Math.min(100, Math.abs(share) / (maxAbsShare() || 1) * 100);
        tdShare.innerHTML = (neg ? '<span style="color:var(--wri-ok)">−' + pctv + '%</span>' : pctv + '%') +
          '<span class="wri-rsbar"><i class="' + (neg ? 'neg' : '') + '" style="width:' + barW.toFixed(0) + '%"></i></span>';
      } else { tdShare.className = 'wri-td-share muted'; tdShare.style.fontSize = '12px'; tdShare.textContent = '—'; }
      // read cell
      tdRead.className = 'wri-td-read';
      if (role) tdRead.innerHTML = '<span class="wri-role wri-role-' + role.kind + '" style="margin:0">' + te(esc(role.en), esc(role.zh)) + '</span>';
      else if (share != null && share < 0) tdRead.innerHTML = '<span class="muted" style="font-size:12px">' + te('offsets the book', '对冲组合') + '</span>';
      else { tdRead.className = 'wri-td-read muted'; tdRead.style.fontSize = '12px'; tdRead.textContent = '—'; }
      if (!fresh) return;   // already inserted; contents updated in place
      var lastTd = tr.lastElementChild;
      tr.insertBefore(tdShare, lastTd);
      tr.insertBefore(tdRead, lastTd);
    });
  }
  function maxAbsShare() {
    var m = 0; Object.keys(BOOK_SHARES).forEach(function (k) { m = Math.max(m, Math.abs(BOOK_SHARES[k])); });
    return m;
  }

  // =========================================================================
  //  Orchestration — recompute L2/L3 whenever weights change; decorate L1 on
  //  every watchlist render; keep the fx panel absorbed.
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
      if (!data) { var h = document.getElementById('wri_hero'); if (h) h.style.display = 'none'; return; }
      var hero = document.getElementById('wri_hero'); if (hero) hero.style.display = '';
      // fill BOOK_SHARES for chips + table from the default-lens read
      var wIn = {};
      (weights.universe || []).forEach(function (t) { var v = weights.wmap[t]; wIn[t] = isNum(v) && v > 0 ? v : 1; });
      var RR = RiskCore.read(data, wIn);
      BOOK_SHARES = {}; UNMODELED = {};
      var b = RR.hasStress ? RR.stress : RR.calm;
      if (b && b.ok) b.held.forEach(function (t) { BOOK_SHARES[t] = b.mctrShare[t]; });
      // names in the list but not in the factor model (for the "price signals only" chip)
      (weights.universe || []).forEach(function (t) { if (!(data.betas && data.betas[t])) UNMODELED[t] = 1; });
      renderHero(data, weights);
      // book shares changed -> refresh card chips + table columns
      refreshShareConsumers();
    });
  }
  function refreshShareConsumers() {
    // repaint the "% of book risk" chip on decorated cards (shares just changed) and
    // capture each name's role for the portfolio table's Risk-read column.
    document.querySelectorAll('#wl_list .wl-card[data-t]').forEach(function (card) {
      if (!('__wriJson' in card)) return;
      var role = card.querySelector('.wri-role'); if (role) role.remove();
      paintLanes(card, card.__wriJson);
      var r = roleBadge(laneRead(card.__wriJson));
      if (r) BOOK_ROLES[card.getAttribute('data-t')] = r;
    });
    decorateTable();
  }

  var scheduled = false;
  function scheduleDecorate() {
    if (scheduled) return; scheduled = true;
    requestAnimationFrame(function () { scheduled = false; decorateCards(); decorateTable(); });
  }

  function init() {
    if (!document.getElementById('wri_hero')) return;   // page without the WRI host
    // 0) load the transmission chains subset once; when it resolves, re-decorate cards +
    //    re-render the rail so the chain chips/drawer/rail sentence appear (404 => silent).
    loadChains().then(function () {
      repaintCards();
      var hero = document.getElementById('wri_hero');
      if (hero && hero.__wri && hero.__wri.RR.calm.ok) renderRail(hero.__wri.RR.calm.bookBeta.mkt);
      else renderRail(null);
    });
    // 1) recompute the book whenever the FX layer republishes weights
    document.addEventListener('fx-weights', function (e) { recomputeBook(e.detail); });
    // 2) first read: pull current weights if the FX panel already resolved them
    if (window.FX && window.FX.currentWeights) recomputeBook(window.FX.currentWeights());
    else loadData().then(function () { recomputeBook({ universe: [], wmap: {}, mode: 'manual' }); });
    // 3) decorate cards on each watchlist render (watchlist.js repaints #wl_list)
    var listEl = document.getElementById('wl_list');
    if (listEl && 'MutationObserver' in window) {
      new MutationObserver(scheduleDecorate).observe(listEl, { childList: true });
    }
    scheduleDecorate();
    // 4) portfolio table re-renders too
    var pfRows = document.getElementById('pf_rows');
    if (pfRows && 'MutationObserver' in window) {
      new MutationObserver(function () { decorateTable(); }).observe(pfRows, { childList: true });
    }
    // 5) language / theme flips -> re-render L2 wording + L1 decorations + rail
    document.addEventListener('langchange', onLangTheme);
    document.addEventListener('themechange', onLangTheme);
    // theme.js toggles data-lang via attribute; also observe it directly
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) if (muts[i].attributeName === 'data-lang') { onLangTheme(); return; }
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-lang'] });
  }
  function onLangTheme() {
    var hero = document.getElementById('wri_hero');
    if (hero && hero.__wri) paintHero(hero, hero.getAttribute('data-lens') || hero.__wri.RR.defaultLens);
    else if (window.FX && window.FX.currentWeights) recomputeBook(window.FX.currentWeights());
    repaintCards();
    // rail re-render (book beta preserved from last hero read)
    if (hero && hero.__wri && hero.__wri.RR.calm.ok) renderRail(hero.__wri.RR.calm.bookBeta.mkt);
  }

  // keyboard: Enter/Space on a ? tip is a no-op focus target; tips are CSS/hover +
  // focus. (data-tip-en/zh consumed by the page's shared tooltip, no title=.)

  // Browser bootstrap — guarded so `require()` under node (the unit-test shell) never
  // touches the DOM at load. In node `document` is undefined; we skip straight to the export.
  if (typeof document !== 'undefined') {
    // lens toggle (delegated — buttons are re-created each paint)
    document.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('#wri_lensCalm, #wri_lensStress') : null;
      if (!btn) return;
      var hero = document.getElementById('wri_hero'); if (!hero || !hero.__wri) return;
      var lens = btn.getAttribute('data-lens');
      hero.setAttribute('data-lens', lens);
      paintHero(hero, lens);
    });
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
      chainDriver: chainDriver
    };
  }
})();

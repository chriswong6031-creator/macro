(function () {
  'use strict';

  var API = '/api/market-memory/v1';
  var state = {
    macro: null,
    symbol: null,
    ticker: 'AAPL',
    macroRequest: 0,
    symbolRequest: 0,
    macroAuthBlocked: false,
    symbolAuthBlocked: false
  };
  var ui = {};

  function isZh() { return document.documentElement.getAttribute('data-lang') === 'zh'; }
  function copy(en, zh) { return isZh() ? (zh || en) : en; }
  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }
  function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
  function asArray(value) { return Array.isArray(value) ? value : []; }
  function present(value) { return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)); }
  function num(value, digits) { return present(value) ? Number(value).toFixed(digits === undefined ? 1 : digits) : '—'; }
  function signed(value, digits, suffix) {
    if (!present(value)) return '—';
    var n = Number(value);
    return (n > 0 ? '+' : '') + n.toFixed(digits === undefined ? 1 : digits) + (suffix || '');
  }
  function logReturn(value) {
    if (!present(value)) return null;
    return (Math.exp(Number(value)) - 1) * 100;
  }
  function basisPoints(value) { return present(value) ? Number(value) * 100 : null; }
  function tone(value) {
    if (!present(value) || Number(value) === 0) return '';
    return Number(value) > 0 ? ' is-up' : ' is-down';
  }
  function apiBase() {
    return /(^|\.)mastermind-x\.com$/i.test(location.hostname || '') ? '' : (window.MM_API || '');
  }

  function withAuth(headers) {
    headers = headers || {};
    if (!(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(headers);
    return window.MDXAuth.client()
      .then(function (client) { return client.auth.getSession(); })
      .then(function (result) {
        var token = result && result.data && result.data.session && result.data.session.access_token;
        if (token) headers.Authorization = 'Bearer ' + token;
        return headers;
      })
      .catch(function () { return headers; });
  }

  function request(path) {
    return withAuth({ Accept: 'application/json' }).then(function (headers) {
      return fetch(apiBase() + API + path, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: headers
      });
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (payload) {
        if (!response.ok) {
          var error = new Error((payload && payload.detail) || ('HTTP ' + response.status));
          error.status = response.status;
          error.payload = payload;
          throw error;
        }
        return payload;
      });
    });
  }

  function empty(titleEn, titleZh, bodyEn, bodyZh, error) {
    var action = '';
    var upgradeRequired = error && (error.status === 402 || error.status === 403);
    if (error && error.status === 401) {
      action = ' <a href="plans.html" data-mm-action="signin">' + esc(copy('Sign in', '登录')) + ' →</a>';
    } else if (upgradeRequired) {
      action = ' <a href="plans.html">' + esc(copy('View plans', '查看方案')) + ' →</a>';
    }
    return '<div class="mm-empty"><strong>' + esc(copy(titleEn, titleZh)) + '</strong>' +
      '<span>' + esc(copy(bodyEn, bodyZh)) + action + '</span></div>';
  }

  function chip(value, extra) {
    if (!value && value !== 0) return '';
    return '<span class="mm-chip' + (extra || '') + '">' + esc(String(value).replace(/_/g, ' ')) + '</span>';
  }

  function queryCard(labelEn, labelZh, value, note, extra) {
    return '<div class="mm-query-card' + (extra || '') + '"><span>' + esc(copy(labelEn, labelZh)) +
      '</span><strong>' + esc(value || '—') + '</strong>' + (note ? '<small>' + esc(note) + '</small>' : '') + '</div>';
  }

  function deltaText(query, episode) {
    var bits = [];
    if (present(episode.vix) && present(query.vix)) {
      bits.push('<b>VIX</b> ' + num(episode.vix, 1) + ' ' + esc(copy('then', '当时')) + ' / ' + num(query.vix, 1) + ' ' + esc(copy('now', '现在')));
    }
    if (present(episode.spread_2s10s) && present(query.spread_2s10s)) {
      bits.push('<b>2s10s</b> ' + signed(basisPoints(episode.spread_2s10s), 0, 'bp') + ' / ' + signed(basisPoints(query.spread_2s10s), 0, 'bp'));
    }
    if (present(episode.breadth_pct_above_200) && present(query.breadth_pct_above_200)) {
      bits.push('<b>' + esc(copy('breadth', '广度')) + '</b> ' + num(episode.breadth_pct_above_200, 0) + '% / ' + num(query.breadth_pct_above_200, 0) + '%');
    }
    return bits.length ? bits.join(' · ') : esc(copy('Difference detail unavailable', '差异细节暂不可用'));
  }

  function outcome(label, value) {
    var pct = logReturn(value);
    return '<div class="mm-outcome' + tone(pct) + '"><span>' + esc(label) +
      '</span><strong>' + (pct === null ? '—' : esc(signed(pct, 1, '%'))) + '</strong></div>';
  }

  function renderMacro() {
    var data = state.macro;
    if (!data) return;
    var query = asObject(data.query);
    ui.macroState.className = 'mm-state-pill is-live';
    ui.macroState.textContent = copy('State through ', '状态截至 ') + (data.as_of || '—');
    ui.macroQuery.innerHTML =
      queryCard('Current state', '当前状态', query.date || data.as_of || '—', [query.quad, query.liquidity, query.cycle].filter(Boolean).join(' · '), ' is-state') +
      queryCard('Growth', '增长', signed(query.growth_z, 2, 'σ')) +
      queryCard('Inflation', '通胀', signed(query.inflation_z, 2, 'σ')) +
      queryCard('2s10s', '2年/10年', signed(basisPoints(query.spread_2s10s), 0, 'bp')) +
      queryCard('10y3m', '10年/3月', signed(basisPoints(query.spread_10y3m), 0, 'bp')) +
      queryCard('VIX · Breadth', 'VIX · 广度', num(query.vix, 1), present(query.breadth_pct_above_200) ? num(query.breadth_pct_above_200, 0) + '% > 200d' : '—');

    var episodes = asArray(data.episodes);
    if (!episodes.length) {
      ui.macroEpisodes.innerHTML = empty('No comparable episodes', '暂无可比片段', 'The complete-state history did not return a dated match.', '完整状态历史未返回可比日期。');
    } else {
      ui.macroEpisodes.innerHTML = episodes.map(function (episode) {
        var fwd = asObject(episode.fwd);
        var chips = chip(episode.quad) + chip(episode.liquidity) + chip(episode.cycle);
        return '<article class="mm-episode">' +
          '<div class="mm-episode-date"><strong>' + esc(episode.date || '—') + '</strong><span>' +
            esc(copy('retrieval distance ', '检索距离 ')) + esc(num(episode.distance, 3)) + '</span></div>' +
          '<div class="mm-state-chips">' + chips + '</div>' +
          '<div class="mm-difference">' + deltaText(query, episode) + '</div>' +
          outcome(copy('S&P · 5 sessions', '标普 · 5交易日'), fwd.spx_h5) +
          outcome(copy('S&P · 20 sessions', '标普 · 20交易日'), fwd.spx_h20) +
          outcome(copy('S&P · 60 sessions', '标普 · 60交易日'), fwd.spx_h60) +
        '</article>';
      }).join('');
    }
    var note = copy(
      'Eligible coverage ' + (data.coverage || '—') + ' · ' + (data.n_candidates || 0) + ' candidate days after the exclusion window.',
      '可用覆盖 ' + (data.coverage || '—') + ' · 排除窗口后共有 ' + (data.n_candidates || 0) + ' 个候选交易日。'
    );
    var basis = String(data.historical_basis || 'basis unavailable').replace(/_/g, ' ');
    note = copy(
      'Historical basis: ' + basis + '. These states are recomputed today from later-complete/currently available history, not a record of what Mastermind knew on each date. ',
      '历史基础：' + basis + '。这些状态按今日可得且事后完整的历史重新计算，并非 Mastermind 在各历史日期当时已知内容的记录。'
    ) + note;
    if (data.query_lag_note) note += ' ' + data.query_lag_note;
    ui.macroNote.textContent = note + ' ' + (data.context_note || '');
  }

  function loadMacro() {
    var requestId = ++state.macroRequest;
    request('/macro?limit=6').then(function (payload) {
      if (requestId !== state.macroRequest) return;
      state.macroAuthBlocked = false;
      state.macro = payload;
      renderMacro();
    }).catch(function (error) {
      if (requestId !== state.macroRequest) return;
      state.macroAuthBlocked = error.status === 401;
      state.macro = null;
      ui.macroState.className = 'mm-state-pill is-error';
      ui.macroState.textContent = copy('Memory unavailable', '记忆暂不可用');
      ui.macroQuery.innerHTML = empty(
        error.status === 401 ? 'Sign in to open Market Memory' : 'Macro memory unavailable',
        error.status === 401 ? '登录以打开市场记忆' : '宏观记忆暂不可用',
        error.status === 402 || error.status === 403 ? 'This evidence surface requires full-site access.' : 'The source engine did not return a complete state.',
        error.status === 402 || error.status === 403 ? '该证据页面需要完整站点权限。' : '源引擎未返回完整状态。',
        error
      );
      ui.macroEpisodes.innerHTML = '';
    });
  }

  function redactForSignOut() {
    state.macroRequest += 1;
    state.symbolRequest += 1;
    state.macro = null;
    state.symbol = null;
    state.macroAuthBlocked = true;
    state.symbolAuthBlocked = true;
    ui.macroState.className = 'mm-state-pill is-error';
    ui.macroState.textContent = copy('Sign in required', '需要登录');
    ui.macroQuery.innerHTML = empty(
      'Sign in to open Market Memory',
      '登录以打开市场记忆',
      'Authenticated context is cleared when you sign out.',
      '退出登录后，已验证的上下文将被清除。',
      { status: 401 }
    );
    ui.macroEpisodes.innerHTML = '';
    ui.macroNote.textContent = copy(
      'No historical payload remains in this browser view.',
      '此浏览器视图中未保留历史载荷。'
    );
    ui.symbolSummary.innerHTML = empty(
      'Sign in to open symbol memory',
      '登录以打开个股记忆',
      'Authenticated symbol context is cleared when you sign out.',
      '退出登录后，已验证的个股上下文将被清除。',
      { status: 401 }
    );
    ui.gridList.innerHTML = '';
  }

  var GRID_LABELS = {
    W: ['Weekly bars', '周线'],
    '2B': ['2-session bars', '2交易日线'],
    '3B': ['3-session bars', '3交易日线']
  };
  var HORIZON_LABELS = {
    '13w': ['13 weeks', '13周'],
    '26w': ['26 weeks', '26周'],
    '21s': ['21 sessions', '21交易日'],
    '63s': ['63 sessions', '63交易日']
  };

  function horizonStat(labelEn, labelZh, value, suffix) {
    return '<div class="mm-stat"><span>' + esc(copy(labelEn, labelZh)) + '</span><strong>' +
      (present(value) ? esc(signed(value, 1, suffix || '%')) : '—') + '</strong></div>';
  }

  function renderHorizon(key, block) {
    block = asObject(block);
    var posterior = asObject(block.name_post);
    var post = asObject(block.post2010);
    var postPosterior = asObject(post.name_post);
    var label = HORIZON_LABELS[key] || [key, key];
    var years = asObject(block.global).n_distinct_years;
    var support = copy(
      'name n=' + (block.n_name || 0) + ' · cohort n=' + (block.n_archetype || 0) + ' · library n=' + (block.n_global || 0) + (years ? ' · ' + years + ' distinct years' : ''),
      '本股 n=' + (block.n_name || 0) + ' · 同类组 n=' + (block.n_archetype || 0) + ' · 全库 n=' + (block.n_global || 0) + (years ? ' · ' + years + ' 个不同年份' : '')
    );
    var detail = copy(
      'Post-2010 posterior: typical ' + signed(postPosterior.med, 1, '%') + ' · positive share ' + num(postPosterior.win, 1) + '%. Name weight ' + num(posterior.w, 3) + '.',
      '2010年后收缩结果：典型 ' + signed(postPosterior.med, 1, '%') + ' · 正收益占比 ' + num(postPosterior.win, 1) + '%。本股权重 ' + num(posterior.w, 3) + '。'
    );
    return '<section class="mm-horizon"><div class="mm-horizon-head"><strong>' + esc(copy(label[0], label[1])) +
      '</strong><span>' + esc(copy('shrunk receipt', '收缩凭据')) + '</span></div>' +
      '<div class="mm-stat-row">' +
        horizonStat('Typical return', '典型收益', posterior.med, '%') +
        horizonStat('Positive share', '正收益占比', posterior.win, '%') +
        horizonStat('Excess vs SPY', '相对SPY超额', posterior.med_exc, '%') +
      '</div><div class="mm-support">' + esc(support) + '</div>' +
      (block.era_note ? '<div class="mm-era-note">' + esc(block.era_note) + '</div>' : '') +
      '<details class="mm-details"><summary>' + esc(copy('Open era and weighting receipt', '展开年代与权重凭据')) +
      '</summary><p>' + esc(detail) + '</p></details></section>';
  }

  function renderGrid(key, grid) {
    grid = asObject(grid);
    var label = GRID_LABELS[key] || [key, key];
    var receipt = asObject(grid.receipt);
    var horizons = asObject(receipt.horizons);
    var direction = String(grid.direction || '—').toLowerCase();
    var freshness = grid.live_fresh === true;
    var bars = present(grid.bars_since) ? Number(grid.bars_since) : null;
    var meta = copy(
      (freshness ? 'recent episode' : 'historical class') + (bars === null ? '' : ' · ' + bars + ' completed bars ago'),
      (freshness ? '近期事件' : '历史类别') + (bars === null ? '' : ' · ' + bars + ' 根完整K线前')
    );
    var classes = chip(direction, direction === 'bull' ? ' is-bull' : (direction === 'bear' ? ' is-bear' : '')) +
      chip(grid.depth_class) + chip(grid.level) + chip(grid.washout_len_class) + chip(copy('align ', '共振 ') + (grid.align_class === null || grid.align_class === undefined ? '—' : grid.align_class));
    var body = Object.keys(horizons).map(function (h) { return renderHorizon(h, horizons[h]); }).join('');
    if (!body) body = empty('Receipt is still accruing', '凭据仍在积累', 'No matured outcome cell is available for this event class.', '该事件类别尚无成熟结果单元。');
    return '<article class="mm-grid-card"><header class="mm-grid-head"><div><h3>' + esc(copy(label[0], label[1])) +
      '</h3><p>' + esc(grid.date || '—') + ' · ' + esc(meta) + '</p></div>' +
      chip(freshness ? copy('fresh', '近期') : copy('older', '较早'), freshness ? ' is-fresh' : ' is-old') +
      '</header><div class="mm-class-row">' + classes + '</div>' + body + '</article>';
  }

  function renderSymbol() {
    var data = state.symbol;
    if (!data) return;
    var grids = asObject(data.grids);
    var bull = asObject(data.bull_now);
    var bullish = Object.keys(bull).filter(function (key) { return bull[key] === true; }).length;
    ui.symbolSummary.innerHTML = '<div class="mm-symbol-id"><span class="mm-symbol-ticker">' + esc(data.ticker || state.ticker) +
      '</span><div><strong>' + esc(copy('Episode memory', '事件记忆')) + '</strong><span>' +
      esc(copy('Current class compared with matching matured episodes', '当前类别与匹配的成熟历史事件比较')) + '</span></div></div>' +
      '<div class="mm-symbol-meta"><div><span>' + esc(copy('As of', '截至')) + '</span><strong>' + esc(data.as_of || '—') +
      '</strong></div><div><span>' + esc(copy('Bull grids', '多头周期')) + '</span><strong>' + bullish + '/3</strong></div>' +
      '<div><span>' + esc(copy('Authority', '权限')) + '</span><strong>A0 · ' + esc(copy('context', '语境')) + '</strong></div></div>';

    var order = ['W', '2B', '3B'];
    var cards = order.filter(function (key) { return grids[key]; }).map(function (key) {
      return renderGrid(key, grids[key]);
    });
    ui.gridList.innerHTML = cards.length ? cards.join('') : empty(
      'No episode history for ' + (data.ticker || state.ticker),
      (data.ticker || state.ticker) + ' 暂无事件历史',
      'The symbol may be unsupported or too new for the frozen taxonomy.',
      '该代码可能尚未覆盖，或历史不足以进入固定分类。'
    );
  }

  function normalizeTicker(raw) {
    var ticker = String(raw || '').trim().toUpperCase();
    return /^[A-Z0-9^][A-Z0-9.^=_-]{0,19}$/.test(ticker) ? ticker : '';
  }

  function loadSymbol(raw) {
    var requestId = ++state.symbolRequest;
    var ticker = normalizeTicker(raw);
    if (!ticker) {
      ui.symbolSummary.innerHTML = empty('Check the ticker', '请检查代码', 'Use a canonical market symbol such as AAPL, BRK-B or BTC-USD.', '请输入 AAPL、BRK-B 或 BTC-USD 等标准市场代码。');
      ui.gridList.innerHTML = '';
      return;
    }
    state.ticker = ticker;
    ui.symbolInput.value = ticker;
    ui.symbolSummary.innerHTML = '<div class="mm-skeleton mm-skeleton-query"></div>';
    ui.gridList.innerHTML = '<div class="mm-skeleton"></div><div class="mm-skeleton"></div><div class="mm-skeleton"></div>';
    try { localStorage.setItem('market_memory_ticker', ticker); } catch (error) { /* no-op */ }
    try {
      var url = new URL(location.href);
      url.searchParams.set('ticker', ticker);
      history.replaceState(null, '', url.pathname + '?' + url.searchParams.toString());
    } catch (error) { /* old browser fallback */ }

    request('/symbol/' + encodeURIComponent(ticker)).then(function (payload) {
      if (requestId !== state.symbolRequest) return;
      state.symbolAuthBlocked = false;
      state.symbol = payload;
      renderSymbol();
    }).catch(function (error) {
      if (requestId !== state.symbolRequest) return;
      state.symbolAuthBlocked = error.status === 401;
      state.symbol = null;
      ui.symbolSummary.innerHTML = empty(
        error.status === 404 ? 'No memory for ' + ticker : (error.status === 401 ? 'Sign in to open symbol memory' : 'Symbol memory unavailable'),
        error.status === 404 ? ticker + ' 暂无记忆' : (error.status === 401 ? '登录以打开个股记忆' : '个股记忆暂不可用'),
        error.status === 402 || error.status === 403 ? 'This evidence surface requires full-site access.' : 'No supported price history or event receipt was returned.',
        error.status === 402 || error.status === 403 ? '该证据页面需要完整站点权限。' : '未返回受支持的价格历史或事件凭据。',
        error
      );
      ui.gridList.innerHTML = '';
    });
  }

  function boot() {
    ui.macroState = document.getElementById('mm-macro-state');
    ui.macroQuery = document.getElementById('mm-macro-query');
    ui.macroEpisodes = document.getElementById('mm-macro-episodes');
    ui.macroNote = document.getElementById('mm-macro-note');
    ui.symbolForm = document.getElementById('mm-symbol-form');
    ui.symbolInput = document.getElementById('mm-symbol-input');
    ui.symbolSummary = document.getElementById('mm-symbol-summary');
    ui.gridList = document.getElementById('mm-grid-list');

    ui.symbolForm.addEventListener('submit', function (event) {
      event.preventDefault();
      loadSymbol(ui.symbolInput.value);
    });
    document.addEventListener('click', function (event) {
      var action = event.target && event.target.closest && event.target.closest('[data-mm-action="signin"]');
      if (!action) return;
      if (window.MDXAuth && typeof window.MDXAuth.open === 'function') {
        event.preventDefault();
        window.MDXAuth.open('signin');
      }
    });
    if (window.MDXAuth && typeof window.MDXAuth.onChange === 'function') {
      window.MDXAuth.onChange(function (user) {
        if (!user) {
          redactForSignOut();
          return;
        }
        var retryMacro = state.macroAuthBlocked;
        var retrySymbol = state.symbolAuthBlocked;
        if (retryMacro) loadMacro();
        if (retrySymbol) loadSymbol(state.ticker);
      });
    }
    document.addEventListener('langchange', function () {
      if (state.macro) renderMacro();
      if (state.symbol) renderSymbol();
    });

    var initial = '';
    try { initial = new URL(location.href).searchParams.get('ticker') || localStorage.getItem('market_memory_ticker') || ''; } catch (error) { /* no-op */ }
    initial = normalizeTicker(initial) || 'AAPL';
    loadMacro();
    loadSymbol(initial);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
}());

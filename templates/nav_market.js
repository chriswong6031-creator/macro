/* nav_market.js — fold the non-home country menus into International.

   THE PROBLEM (operator, 2026-07-25): the rail carries United States · China ·
   Hong Kong · Canada · International · Other Assets · Research. A US-only trader
   — which is most of them — stares at three markets they will never open, and
   those three slots are the most valuable real estate on the site.

   THE RULING (masterplan R1): fold, do NOT delete. The operator's own answer —
   "don't we have that international menu? we can just put the other countries in
   there?" — is the right one. Deleting would strip nav-level internal links from
   whole market estates (an SEO cost paid on 3,000+ pages) and force a multi-market
   user through settings to reach a market they actively trade. Folding costs one
   extra hover and keeps every page one hop away.

   WHY THIS RUNS IN THE BROWSER, NOT IN JINJA
   The home market is per-USER; the nav is baked once into every rendered page.
   A build-time fold is therefore impossible without splitting the estate per
   market. Doing it client-side also means the SERVED html keeps every country
   link, so crawlers and signed-out visitors see the complete nav — which is
   exactly the SEO property the ruling was protecting.

   WHY ITS OWN FILE
   theme.js and onboard.js both have a large PR in flight (#3560, desk prefs).
   This needs neither: account.js — loaded on every page and untouched by that
   work — pulls it in. It also keeps the nav transform in a module named after
   what it does.

   CONTRACT
   Reads the SAME shape the Terminal reads (charting-app terminal/lib/markets.ts):
     user_metadata.markets      = { home, enabled[], autoNarrowed }   ← canonical
     user_metadata.market_focus = ["us"|"cn"|"hk"|"ca"|"global", …]   ← legacy, migrated
   An explicit `markets` object always wins, or a preference narrowed in settings
   would be silently reverted by the signup-time array on the next load.

   EVERY followed market stays on the rail — not just the home one. enabled[] is
   the source of truth: pick two or three markets and all of them keep their rail
   slot; only the markets you don't follow fold into International. (An earlier cut
   kept solely the home market, so a two- or three-market trader still lost the
   rest to the dropdown — the bug this fixes.)

   NO MARKETS TO FOLD => NO CHANGE. Anonymous visitors, crawlers, users who skipped
   the question, "global" users, and anyone following all four markets keep today's
   full rail. */
(function () {
  'use strict';

  // Country dropdowns are identified by their trigger href, not by label text or
  // icon class: hrefs are the one part of the nav that cannot drift with a
  // rewording or an icon pass (two of which have already landed — #3508, #3525).
  var COUNTRY_BY_HREF = {
    'macro.html': 'us',
    'china.html': 'cn',
    'hk.html': 'hk',
    'canada.html': 'ca'
  };
  var INTL_HREF = 'intl.html';

  /* One destination map drives every wide market panel, whether that market is
     visible on the top rail or folded into International for this user. This is
     the important maintenance property: a new China page is added here once,
     not to separate "top-level China" and "China inside International" menus. */
  var MARKET_KEY_BY_HREF = {
    'macro.html': 'us',
    'china.html': 'cn',
    'hk.html': 'hk',
    'canada.html': 'ca',
    'intl.html': 'intl',
    'crypto.html': 'crypto'
  };
  var MARKET_MENU = {
    us: {
      title: 'United States',
      subtitle: 'Macro context, stocks, sectors and live market desks.',
      sections: [
        ['Market overview', [
          ['Macro Dashboard', 'Regime, growth and inflation now', 'macro.html', 'dashboard'],
          ['Stock Dashboard', 'Standouts, sectors and flows', 'us_stocks.html', 'stocks'],
          ['Sector Central', 'Every sector in one view', 'sector_central.html', 'intelligence'],
          ['Theme Baskets', 'Themes, leaders and rotation', 'baskets.html', 'baskets']
        ]],
        ['Signals & strategy', [
          ['Subsector Rotation', 'Catch emerging groups early', 'subsector_rotation.html', 'rotation'],
          ['Strategies', 'Tactical scorecards and positioning', 'strategies.html', 'strategy'],
          ['Alert Center', 'Ranked market-moving alerts', 'alerts.html', 'alert'],
          ['News Feed', 'Catalysts, headlines and sentiment', 'news.html', 'news']
        ]],
        ['Market structure', [
          ['Options Desk', 'Gamma, walls and volatility', 'gex.html', 'options'],
          ['Group Flow Heatmap', 'Follow sector capital flows', 'flow_desk.html', 'flow'],
          ['Options Screener', 'Find liquid volatility setups', 'options_screener.html', 'dashboard'],
          ['Dark Pool Desk', 'Track off-exchange positioning', 'darkpool.html', 'darkpool']
        ]]
      ],
      rail: [
        ['Stock Terminal', 'Open any U.S. ticker', 'stock.html', 'stocks'],
        ['Market Heatmap', 'See the whole tape', 'sector_central.html', 'heatmap'],
        ['Subsector Confluence', 'Find aligned groups', 'subsectors.html', 'confluence'],
        ['Browse U.S. markets', 'All U.S. destinations', 'macro.html', 'dashboard']
      ],
      note: ['Built for quick decisions', 'The most-used desks stay one click away.']
    },
    cn: {
      title: 'China',
      subtitle: 'A-shares, policy, capital flow and narrative intelligence.',
      sections: [
        ['Market overview', [
          ['Macro Dashboard', 'Regime, sectors and policy pulse', 'china.html', 'dashboard'],
          ['Stock Dashboard', 'A-share leaders and setups', 'china_stocks.html', 'stocks'],
          ['Market Heatmap', 'Every A-share in one view', 'china_heatmap.html', 'heatmap'],
          ['China Intelligence', 'Policy, markets and signal context', 'china_intel.html', 'intelligence']
        ]],
        ['Themes & rotation', [
          ['Sector Central', 'Cycle map and gated reads', 'sector_central_china.html', 'intelligence'],
          ['Theme Baskets', 'Equal-weight themes and leaders', 'baskets_china.html', 'baskets'],
          ['Subsector Rotation', 'Catch concepts gaining speed', 'subsector_rotation_china.html', 'rotation'],
          ['Narrative Radar', 'See which story is running', 'narrative_radar.html', 'narrative']
        ]],
        ['Flows & policy', [
          ['Capital Flow Velocity', 'Track accelerating big money', 'flow_velocity.html', 'flow'],
          ['Policy Watch', 'Rates, liquidity and sector policy', 'china_policy_watch.html', 'policy'],
          ['Market Mechanics', 'Participation and policy tape', 'china_mechanics.html', 'structure'],
          ['Special Situations', 'Unlocks, filings and stress', 'china_special_situations.html', 'event']
        ]]
      ],
      rail: [
        ['China News', 'Official sources and catalysts', 'china_news.html', 'news'],
        ['Strategies', 'Tactical China scorecards', 'china_strategies.html', 'strategy'],
        ['Alternative Data', 'Signals beyond price', 'china_altdata.html', 'research'],
        ['Browse China', 'All China research', 'china_intel.html', 'intelligence']
      ]
    },
    hk: {
      title: 'Hong Kong',
      subtitle: 'Hong Kong equities, southbound flow and thematic rotation.',
      sections: [
        ['Market overview', [
          ['Macro Dashboard', 'HSI, southbound and global risk', 'hk.html', 'dashboard'],
          ['Stock Dashboard', 'Hong Kong leaders and setups', 'hk_stocks.html', 'stocks'],
          ['Market Heatmap', 'Turnover-sized market map', 'hk_heatmap.html', 'heatmap'],
          ['Capital Flow Velocity', 'Southbound money in motion', 'flow_velocity.html', 'flow']
        ]],
        ['Themes & rotation', [
          ['Thematic Baskets', 'Equal-weight themes versus HSI', 'baskets_hk.html', 'baskets'],
          ['Narrative Rotation', 'What to hold and when to rotate', 'allocation_hk.html', 'rotation']
        ]]
      ],
      rail: [
        ['China Intelligence', 'Shared policy context', 'china_intel.html', 'intelligence'],
        ['Policy Watch', 'Liquidity and policy shifts', 'china_policy_watch.html', 'policy'],
        ['Hong Kong Baskets', 'Browse active themes', 'baskets_hk.html', 'baskets'],
        ['Browse Hong Kong', 'Return to market overview', 'hk.html', 'dashboard']
      ]
    },
    ca: {
      title: 'Canada',
      subtitle: 'TSX equities, Bank of Canada and commodity-sensitive leadership.',
      sections: [
        ['Market overview', [
          ['Macro Dashboard', 'TSX, BoC and commodity overlay', 'canada.html', 'dashboard'],
          ['Stock Dashboard', 'Canadian leaders and setups', 'canada_stocks.html', 'stocks'],
          ['Market Heatmap', 'Every TSX name in one view', 'canada_heatmap.html', 'heatmap']
        ]],
        ['Themes & rotation', [
          ['Thematic Baskets', 'Equal-weight themes versus TSX', 'baskets_canada.html', 'baskets'],
          ['Narrative Rotation', 'What to hold and when to rotate', 'allocation_canada.html', 'rotation']
        ]]
      ],
      rail: [
        ['Banks & insurers', 'Canadian financial leadership', 'canada_stocks.html', 'stocks'],
        ['Energy complex', 'Oil-sensitive market context', 'commodities.html', 'commodities'],
        ['Gold & materials', 'Materials leadership', 'baskets_canada.html', 'baskets'],
        ['Browse Canada', 'Return to market overview', 'canada.html', 'dashboard']
      ]
    },
    intl: {
      title: 'International',
      subtitle: 'Compare the world’s equity markets, cycles and leadership.',
      sections: [
        ['Global overview', [
          ['World Dashboard', 'Major markets compared', 'intl.html', 'dashboard'],
          ['Stock Dashboard', 'Cross-market leaders and sectors', 'intl_stocks.html', 'stocks'],
          ['Global Market Cycles', 'Compare national equity clocks', 'markets.html', 'rotation'],
          ['Country Cycles', 'Every country on one cycle map', 'country_cycles.html', 'intelligence']
        ]],
        ['Themes & regions', [
          ['Thematic Baskets', 'Cross-country themes beyond the U.S.', 'baskets_intl.html', 'baskets']
        ]]
      ],
      rail: [
        ['Japan', 'Tokyo market overview', 'intl.html#japan', 'dashboard'],
        ['South Korea', 'Seoul market overview', 'intl.html#south-korea', 'dashboard'],
        ['Europe', 'Continental markets', 'intl.html#europe', 'dashboard'],
        ['United Kingdom', 'London market overview', 'intl.html#united-kingdom', 'dashboard'],
        ['India', 'Indian market overview', 'intl.html#india', 'dashboard']
      ],
      note: ['Your other markets appear here', 'The same panels move with your market preferences.']
    },
    crypto: {
      title: 'Crypto',
      subtitle: 'Cycle, risk, allocation and strategy for digital assets.',
      sections: [
        ['Market overview', [
          ['Crypto Cockpit', 'Market board, flows and leverage', 'crypto.html', 'dashboard'],
          ['Bitcoin Vector', 'State, risk and cycle', 'vector.html', 'bitcoin']
        ]],
        ['Portfolio', [
          ['Allocation', 'Bitcoin, ether, alts and cash', 'crypto.html#allocation', 'allocation'],
          ['Strategy Track Record', 'Cycle and allocation evidence', 'vector.html#strategy-track-record', 'strategy']
        ]]
      ],
      rail: [
        ['Bitcoin Terminal', 'Open the BTC chart', 'stock.html?ticker=BTC-USD', 'bitcoin'],
        ['Allocation', 'Current portfolio stance', 'crypto.html#allocation', 'allocation'],
        ['Browse Crypto', 'Return to the cockpit', 'crypto.html', 'dashboard']
      ]
    },
    assets: {
      title: 'Other Assets',
      subtitle: 'Commodities, currencies and bonds in one coherent workspace.',
      sections: [
        ['Commodities', [
          ['Commodity Dashboard', 'Gold, metals, energy and softs', 'commodities.html', 'commodities'],
          ['Commodity Strategies', 'Tactical calls by commodity', 'commodity_strategies.html', 'strategy'],
          ['Strategic Reserves', 'Global stockpiles versus price', 'spr.html', 'commodities']
        ]],
        ['Macro assets', [
          ['Forex', 'Dollar, G10 carry and pairs', 'forex.html', 'forex'],
          ['Bonds', 'Curve, credit and duration', 'bonds.html', 'policy']
        ]]
      ],
      rail: [
        ['Gold', 'Precious metals context', 'commodities.html#gold', 'commodities'],
        ['Crude oil', 'Energy market context', 'commodities.html#oil', 'commodities'],
        ['Copper', 'Industrial metals context', 'commodities.html#copper', 'commodities'],
        ['Browse other assets', 'All non-equity desks', 'commodities.html', 'dashboard']
      ]
    }
  };

  function fileOf(a) {
    var h = a && a.getAttribute ? (a.getAttribute('href') || '') : '';
    return h.split('?')[0].split('#')[0].split('/').pop().toLowerCase();
  }

  function prefixOf(dd) {
    var a = dd.querySelector(':scope > a[href], :scope > .nav-dd-menu a[href]');
    var h = a ? (a.getAttribute('href') || '') : '';
    if (/^(?:https?:|javascript:|#)/i.test(h)) {
      a = dd.querySelector(':scope > .nav-dd-menu a[href]:not([href^="javascript:"]):not([href^="#"])');
      h = a ? (a.getAttribute('href') || '') : '';
    }
    var slash = h.lastIndexOf('/');
    return slash > -1 ? h.slice(0, slash + 1) : '';
  }

  function marketKeyOf(dd) {
    var trig = dd && dd.querySelector ? dd.querySelector(':scope > a') : null;
    var file = fileOf(trig);
    if (MARKET_KEY_BY_HREF[file]) return MARKET_KEY_BY_HREF[file];
    if (trig && trig.getAttribute('href') === 'javascript:void(0)') return 'assets';
    return null;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function langText(en, zh) {
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(zh || en) + '</span>';
  }

  function destinationMarkup(item, prefix, rail) {
    var cls = rail ? 'nav-market-rail-item' : 'nav-market-item';
    return '<a class="' + cls + '" href="' + esc(prefix + item[2]) + '">' +
      '<span class="nav-market-icon submenu-icon submenu-icon-' + esc(item[3]) + '" aria-hidden="true"></span>' +
      '<span class="nav-market-copy"><span class="nav-market-title">' + langText(item[0], item[4]) + '</span>' +
      '<span class="d">' + langText(item[1], item[5]) + '</span></span>' +
      (rail ? '<span class="nav-market-arrow" aria-hidden="true">↗</span>' : '') +
      '</a>';
  }

  function marketMarkup(key, prefix) {
    var data = MARKET_MENU[key], main = '', rail = '';
    if (!data) return '';
    for (var i = 0; i < data.sections.length; i++) {
      var section = data.sections[i], items = '';
      for (var j = 0; j < section[1].length; j++) items += destinationMarkup(section[1][j], prefix, false);
      main += '<section class="nav-market-section"><div class="nav-market-heading">' +
        langText(section[0]) + '</div><div class="nav-market-grid">' + items + '</div></section>';
    }
    for (var k = 0; k < data.rail.length; k++) rail += destinationMarkup(data.rail[k], prefix, true);
    if (data.note) {
      rail += '<div class="nav-market-note"><strong>' + langText(data.note[0]) +
        '</strong><span>' + langText(data.note[1]) + '</span></div>';
    }
    return '<div class="nav-market-main"><header class="nav-market-intro">' +
      '<div><div class="nav-market-name">' + langText(data.title) + '</div>' +
      '<div class="nav-market-subtitle">' + langText(data.subtitle) + '</div></div>' +
      '<span class="nav-market-count">' + data.sections.reduce(function (n, s) { return n + s[1].length; }, 0) +
      ' destinations</span></header>' + main + '</div>' +
      '<aside class="nav-market-rail"><div class="nav-market-heading">' + langText('Explore') +
      '</div>' + rail + '</aside>';
  }

  function enhanceMarketMenus(links) {
    if (!links) return;
    var top = links.querySelectorAll(':scope > .nav-dd');
    for (var i = 0; i < top.length; i++) {
      var dd = top[i], key = marketKeyOf(dd);
      if (!key || dd.getAttribute('data-nav-market-ready') === '1') continue;
      var menu = dd.querySelector(':scope > .nav-dd-menu');
      if (!menu) continue;
      dd.setAttribute('data-nav-market-ready', '1');
      dd.classList.add('nav-market-dd');
      menu.className = 'nav-dd-menu nav-market-menu';
      menu.setAttribute('data-nav-market-key', key);
      menu.innerHTML = marketMarkup(key, prefixOf(dd));
    }
  }

  /* ---- preference ------------------------------------------------------- */
  // The four country dropdowns the rail can fold. intl/crypto ride along in the
  // stored preference (enabled[] carries them) but are not country markets, so
  // they never fold and never count toward "kept".
  var COUNTRY_SET = { us: 1, cn: 1, hk: 1, ca: 1 };
  // The onboarding chips. "global" means "I trade everywhere" — it is NOT the
  // `intl` bucket, and it must leave the rail alone rather than fold anything.
  var LEGACY = { us: 'us', cn: 'cn', china: 'cn', hk: 'hk', ca: 'ca', canada: 'ca',
                 intl: 'intl', international: 'intl', global: 'all' };
  var currentPreference = { home: null, enabled: [] };

  function preferenceOf(user) {
    var meta = (user && user.user_metadata) || null;
    if (!meta) return { home: null, enabled: [] };
    var m = meta.markets;
    var raw = [], home = null;
    if (m && typeof m === 'object') {
      home = typeof m.home === 'string' ? (LEGACY[m.home.toLowerCase()] || m.home.toLowerCase()) : null;
      raw = Object.prototype.toString.call(m.enabled) === '[object Array]' ? m.enabled : (home ? [home] : []);
    } else if (Object.prototype.toString.call(meta.market_focus) === '[object Array]') {
      raw = meta.market_focus;
    }
    var enabled = [], seen = {};
    for (var i = 0; i < raw.length; i++) {
      var hit = typeof raw[i] === 'string' ? (LEGACY[raw[i].toLowerCase()] || raw[i].toLowerCase()) : null;
      if (hit === 'all') {
        enabled = ['us', 'cn', 'hk', 'ca', 'intl'];
        seen = { us: 1, cn: 1, hk: 1, ca: 1, intl: 1 };
        break;
      }
      if (hit && !seen[hit]) { seen[hit] = 1; enabled.push(hit); }
    }
    if (!home || home === 'all') home = enabled[0] || null;
    return { home: home, enabled: enabled };
  }

  // The country markets to KEEP on the rail, or null when we must not touch the
  // nav. One pick keeps one and folds the other three; two or three picks keep
  // exactly those and fold the rest; four picks (or "global", or nothing set)
  // return null so the full rail is left alone.
  function keptMarketsOf(user) {
    var meta = (user && user.user_metadata) || null;
    if (!meta) return null;

    // Canonical shape wins. enabled[] is the source of truth — every market the
    // user follows, not just the home one — so all of them keep their rail slot.
    // home is only a fallback for old rows written before enabled[] existed.
    var m = meta.markets;
    if (m && typeof m === 'object') {
      var src = (Object.prototype.toString.call(m.enabled) === '[object Array]' && m.enabled.length)
        ? m.enabled
        : (typeof m.home === 'string' ? [m.home] : []);
      return countriesFrom(src);
    }

    // Legacy signup array: every recognised pick is kept (mirrors enabled[]),
    // not just the first. "global" anywhere means trade-everywhere → leave whole.
    var focus = meta.market_focus;
    if (Object.prototype.toString.call(focus) === '[object Array]' && focus.length) {
      var mapped = [];
      for (var i = 0; i < focus.length; i++) {
        var hit = typeof focus[i] === 'string' ? LEGACY[focus[i].toLowerCase()] : null;
        if (hit === 'all') return null;      // trades everywhere — leave the rail whole
        if (hit) mapped.push(hit);
      }
      return countriesFrom(mapped);
    }
    return null;
  }

  // Reduce an enabled/focus list to the DISTINCT country markets on the rail
  // (us/cn/hk/ca), dropping intl/crypto and duplicates. Returns null — "leave the
  // rail whole" — when nothing is recognised or when all four are kept (there is
  // then nothing to fold).
  function countriesFrom(list) {
    var kept = [], seen = {};
    for (var i = 0; i < list.length; i++) {
      var s = list[i];
      if (COUNTRY_SET[s] && !seen[s]) { seen[s] = 1; kept.push(s); }
    }
    return (kept.length && kept.length < 4) ? kept : null;
  }

  /* ---- DOM ---------------------------------------------------------------- */
  // Pristine markup of the whole rail, captured once before any edit.
  //
  // Restoring the ENTIRE .nav-links innerHTML — rather than swapping individual
  // dropdowns back — is deliberate. A folded country lives INSIDE the
  // International menu, so an in-place replace would put the restored top-level
  // markup back where it currently sits (nested), not where it came from: the
  // rail would lose that country for good and a home-market change would corrupt
  // the nav. Wholesale restore is the only version that is correct for every
  // transition, including fold → refold → signed out.
  var ORIGINAL_HTML = null;

  function capture(links) {
    if (ORIGINAL_HTML === null) ORIGINAL_HTML = links.innerHTML;
    return ORIGINAL_HTML;
  }

  // Re-class a top-level country dropdown as a nested submenu, matching the
  // idiom already used inside the US and China menus (.nav-dd.nav-sub with a
  // .nav-sub-trig > .nav-sub-text trigger and a right-pointing caret).
  // The flag icon and both language spans ride along untouched, so the folded
  // entry stays bilingual and keeps the icon the icon pass gave it.
  function toSubmenu(dd) {
    var trig = dd.querySelector(':scope > a');
    if (!trig) return dd;
    dd.classList.add('nav-sub', 'nav-drill', 'nav-market-drill');

    var text = document.createElement('span');
    text.className = 'nav-sub-text';
    var kids = [].slice.call(trig.childNodes);
    for (var i = 0; i < kids.length; i++) {
      var k = kids[i];
      // Drop the ▾ caret — the submenu uses its own ▸ on the right.
      if (k.nodeType === 1 && k.classList && k.classList.contains('caret')) { trig.removeChild(k); continue; }
      text.appendChild(k);
    }
    trig.className = 'nav-sub-trig';
    trig.setAttribute('data-nav-drill-open', '');
    trig.setAttribute('aria-expanded', 'false');
    trig.appendChild(text);

    var caret = document.createElement('span');
    caret.className = 'caret-r';
    caret.textContent = '›';
    trig.appendChild(caret);

    var panel = dd.querySelector(':scope > .nav-dd-menu');
    if (panel) {
      panel.classList.add('nav-drill-panel', 'nav-market-drill-panel');
      panel.setAttribute('data-nav-drill-panel', '');
      panel.setAttribute('aria-hidden', 'true');
      var back = document.createElement('button');
      back.className = 'nav-drill-back';
      back.type = 'button';
      back.setAttribute('data-nav-drill-back', '');
      back.innerHTML = '‹ <span class="l-en">International</span><span class="l-zh">国际</span>';
      panel.insertBefore(back, panel.firstChild);
    }
    return dd;
  }

  // theme.js marks the active page (and its ancestor triggers) at DOMContentLoaded,
  // which is BEFORE this runs — a folded menu would otherwise lose its highlight,
  // and the International trigger would never gain one. Re-apply with the same rule.
  function remarkActive(links) {
    var here = (location.pathname.split('/').pop() || '').toLowerCase() || 'index.html';
    links.querySelectorAll('a.active').forEach(function (a) { a.classList.remove('active'); });
    links.querySelectorAll('a[href]').forEach(function (a) {
      if (fileOf(a) !== here) return;
      a.classList.add('active');
      var p = a.parentElement;
      while (p && p !== links) {
        if (p.classList && p.classList.contains('nav-dd')) {
          var trig = p.querySelector(':scope > a');
          if (trig) trig.classList.add('active');
        }
        p = p.parentElement;
      }
    });
  }

  // Tracks what the rail is currently folded to, so an auth event that changes
  // nothing (theme.js emits several) does not needlessly rebuild the DOM.
  var applied = false;

  function apply(kept) {
    var links = document.querySelector('.site-nav .nav-links, .topbar .nav-links');
    if (!links) return;
    capture(links);

    // `kept` is the 1–3 country markets to keep on the rail (fold the rest), or
    // null to leave the full rail alone.
    var folding = !!(kept && kept.length);

    // Nothing to fold and nothing folded — leave the DOM completely alone so an
    // anonymous page never pays a rebuild.
    if (!folding && !applied) return;

    // Restore pristine, then fold from scratch. Every transition (fold, refold on
    // a preference change, unfold on sign-out) is the same code path.
    links.innerHTML = ORIGINAL_HTML;
    applied = false;
    // The restored nodes are brand new, so the per-node accordion handlers
    // theme.js bound at DOMContentLoaded are gone. Re-bind before a tap can land.
    rebindAccordion(links);

    if (!folding) { remarkActive(links); return; }   // nothing to fold

    // Keep every followed country on the rail; fold only the ones not in the set.
    var keptSet = {};
    for (var i = 0; i < kept.length; i++) keptSet[kept[i]] = 1;

    var intlMenu = null, countries = [];
    var top = links.querySelectorAll(':scope > .nav-dd');
    for (var j = 0; j < top.length; j++) {
      var trig = top[j].querySelector(':scope > a');
      var file = fileOf(trig);
      if (file === INTL_HREF) intlMenu = top[j].querySelector(':scope > .nav-dd-menu');
      else if (COUNTRY_BY_HREF[file] && !keptSet[COUNTRY_BY_HREF[file]]) countries.push(top[j]);
    }
    if (!intlMenu || !countries.length) { remarkActive(links); return; }

    // Fold in rail order, appended after International's own entries — its three
    // items stay first because they are the menu's own subject; the countries
    // read as "also here" rather than displacing it.
    // A labelled divider before the folded entries. Without it the countries read
    // as three more International links rather than as the markets that used to
    // live on the rail — and a user who has "lost" China needs to recognise where
    // it went on the first look, not hunt for it.
    injectCSS();
    var foldTarget = intlMenu.querySelector(':scope > .nav-market-rail') || intlMenu;
    var head = document.createElement('div');
    head.className = 'nav-mkt-h';
    head.innerHTML = '<span class="l-en">Other markets</span><span class="l-zh">其他市场</span>';
    foldTarget.appendChild(head);

    for (var k = 0; k < countries.length; k++) foldTarget.appendChild(toSubmenu(countries[k]));
    applied = true;

    remarkActive(links);
  }

  // Mirrors theme.js initMobileNav's accordion binding for nodes it never saw.
  // Guarded by a data flag so a re-fold cannot stack duplicate handlers (which
  // would toggle a menu twice per tap and leave it looking unresponsive).
  function rebindAccordion(links) {
    links.querySelectorAll('.nav-dd').forEach(function (dd) {
      if (dd.getAttribute('data-nm-bound')) return;
      var trigger = dd.querySelector(':scope > a');
      if (!trigger) return;
      dd.setAttribute('data-nm-bound', '1');
      trigger.addEventListener('click', function (e) {
        if (window.innerWidth > 900) return;
        e.preventDefault(); e.stopPropagation();
        var wasOpen = dd.classList.contains('open');
        dd.parentElement.querySelectorAll(':scope > .nav-dd.open').forEach(function (d) {
          if (d !== dd) d.classList.remove('open');
        });
        if (wasOpen) {
          dd.querySelectorAll('.nav-dd.open').forEach(function (d) { d.classList.remove('open'); });
          dd.classList.remove('open');
        } else {
          dd.classList.add('open');
        }
      });
    });
  }

  // Group heading, styled to match the Research mega-menu's .nav-mega-h eyebrow so
  // the fold looks native rather than bolted on. Injected once, on first fold, so
  // an anonymous page ships no extra CSS. Chinese drops the wide letter-spacing —
  // tracking that flatters uppercase Latin makes CJK look broken.
  var _cssDone = false;
  function injectCSS() {
    if (_cssDone || document.getElementById('nav-mkt-css')) { _cssDone = true; return; }
    _cssDone = true;
    var st = document.createElement('style');
    st.id = 'nav-mkt-css';
    st.textContent =
      '.nav-mkt-h{display:flex;align-items:center;gap:8px;padding:9px 10px 5px;margin-top:4px;' +
      'font-size:9.5px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;' +
      'color:var(--muted,#8b93a1);white-space:nowrap}' +
      '.nav-mkt-h::after{content:"";flex:1;height:1px;' +
      'background:color-mix(in srgb,var(--text,#cbd5e1) 12%,transparent)}' +
      'html[data-lang="zh"] .nav-mkt-h{letter-spacing:.02em}';
    (document.head || document.documentElement).appendChild(st);
  }

  function boot() {
    var links = document.querySelector('.site-nav .nav-links, .topbar .nav-links');
    if (links) {
      enhanceMarketMenus(links);
      capture(links);
      remarkActive(links);
    }
    if (!window.MDXAuth || !window.MDXAuth.onChange) return;
    window.MDXAuth.onChange(function (user) {
      try {
        currentPreference = preferenceOf(user);
        apply(keptMarketsOf(user));
        document.dispatchEvent(new CustomEvent('mmx-markets-change', {
          detail: { home: currentPreference.home, enabled: currentPreference.enabled.slice() }
        }));
      } catch (e) { /* nav must never break a page */ }
    });
  }

  window.MMXMarkets = window.MMXMarkets || {};
  window.MMXMarkets.current = function () {
    return { home: currentPreference.home, enabled: currentPreference.enabled.slice() };
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

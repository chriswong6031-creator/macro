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

  /* Exact drawing paths from the approved HTML mockup.  These are intentionally
     inline SVG paths rather than the legacy CSS-mask icon library: the mockup's
     ghost construction lines, soft fills, accent strokes, and 48px geometry are
     part of the approved product, not a loose visual reference. */
  var MOCKUP_ICON_PATHS = {
    dashboard: '<rect x="6" y="7" width="36" height="32" rx="3"/><path class="ghost" d="M11 12h11v9H11zM26 12h11v9H26zM11 25h26v9H11z"/><path class="accent" d="m14 31 5-4 5 2 6-5 4 3"/>',
    stocks: '<path class="ghost" d="M7 40h34M9 7v33"/><path class="accent" d="m11 33 7-9 6 4 10-14 5 4"/><path d="M16 14v14M13 18h6M29 8v18M26 12h6M37 12v12M34 16h6"/>',
    sectors: '<path d="m8 14 10-6 10 6-10 6ZM20 28l10-6 10 6-10 6ZM6 31l8-5 8 5-8 5Z"/><path class="accent" d="M18 20v9M28 14v9M22 31h8"/>',
    themes: '<path class="ghost" d="m8 12 16-8 16 8-16 8Z"/><path d="m8 19 16 8 16-8M8 27l16 8 16-8M8 35l16 8 16-8"/><path class="accent" d="M13 14 24 9l11 5"/>',
    rotation: '<circle cx="24" cy="24" r="15"/><path class="accent" d="M13 14a15 15 0 0 1 21 0M34 10v5h-5M35 34a15 15 0 0 1-21 0M14 38v-5h5"/><circle class="soft-fill" cx="24" cy="24" r="4"/>',
    strategy: '<path d="M8 11h32M8 24h32M8 37h32"/><circle class="soft-fill" cx="17" cy="11" r="4"/><circle class="soft-fill" cx="31" cy="24" r="4"/><circle class="soft-fill" cx="21" cy="37" r="4"/>',
    alerts: '<path d="M24 7a11 11 0 0 0-11 11c0 8-3 11-5 14h32c-2-3-5-6-5-14A11 11 0 0 0 24 7Z"/><path class="accent" d="M19 38a5 5 0 0 0 10 0"/><path class="ghost" d="M24 3v4"/>',
    news: '<path d="M9 6h25l6 6v30H9zM34 6v7h6"/><path class="accent" d="M15 18h18M15 24h18M15 30h12M15 36h15"/><rect class="soft-fill" x="15" y="10" width="10" height="5" rx="1"/>',
    options: '<path class="ghost" d="M6 39h36M9 8v31"/><path d="M10 35c7 0 7-22 14-22s7 22 14 22"/><path class="accent" d="M14 29h20M24 13v22"/><circle class="soft-fill" cx="24" cy="22" r="3"/>',
    flows: '<path d="M6 14c8-8 13 8 21 0s11 4 15 0M6 24c8-8 13 8 21 0s11 4 15 0M6 34c8-8 13 8 21 0s11 4 15 0"/><path class="accent" d="m35 10 7 4-7 4M35 30l7 4-7 4"/>',
    scanner: '<circle cx="24" cy="24" r="17"/><circle class="ghost" cx="24" cy="24" r="10"/><path d="M24 7v34M7 24h34"/><path class="accent" d="M24 24 37 13"/><circle class="soft-fill" cx="31" cy="19" r="3"/>',
    darkpool: '<circle cx="24" cy="24" r="17"/><path class="ghost" d="M9 24h30M24 9v30"/><path d="M14 30c5-11 15-11 20 0"/><circle class="soft-fill" cx="24" cy="21" r="6"/><path class="accent" d="M18 35h12"/>',
    intelligence: '<path class="ghost" d="M6 12 24 3l18 9v23l-18 10L6 35Z"/><path d="m24 9 12 7v15l-12 7-12-7V16Z"/><circle class="soft-fill" cx="24" cy="24" r="4"/><path class="accent" d="M24 20V9M28 24h8M24 28v10M20 24h-8M21 21l-6-5M27 21l6-5M21 27l-6 5M27 27l6 5"/>',
    heatmap: '<rect x="6" y="7" width="36" height="34" rx="3"/><path d="M18 7v34M30 7v34M6 18h36M6 30h36"/><rect class="soft-fill" x="19" y="19" width="10" height="10"/><path class="accent" d="M31 8h10v9M7 31h10v9"/>',
    policy: '<path d="M7 17h34L24 6Z"/><path d="M11 20v17M19 20v17M29 20v17M37 20v17M7 40h34"/><path class="accent" d="M5 15h38M9 37h30"/><circle class="soft-fill" cx="24" cy="12" r="2"/>',
    mechanics: '<circle cx="18" cy="21" r="8"/><circle cx="32" cy="29" r="8"/><path class="accent" d="M18 9v4M18 29v4M6 21h4M26 21h4M32 17v4M32 37v4M20 29h4M40 29h4"/><circle class="soft-fill" cx="18" cy="21" r="3"/><circle class="soft-fill" cx="32" cy="29" r="3"/>',
    narrative: '<circle cx="24" cy="24" r="17"/><path class="ghost" d="M24 7v34M7 24h34"/><path d="m18 30 4-11 11-5-5 11Z"/><path class="accent" d="m22 19 6 6"/><circle class="soft-fill" cx="24" cy="24" r="2"/>',
    special: '<path d="M8 24h11M29 12h11M29 36h11M19 24c8 0 4-12 10-12M19 24c8 0 4 12 10 12"/><circle class="soft-fill" cx="8" cy="24" r="3"/><circle cx="40" cy="12" r="3"/><circle cx="40" cy="36" r="3"/><path class="accent" d="m24 7-5 9h6l-4 8"/>',
    global: '<circle cx="24" cy="24" r="17"/><path d="M7 24h34M11 15h26M11 33h26M24 7c4 5 6 10 6 17s-2 12-6 17c-4-5-6-10-6-17s2-12 6-17Z"/><path class="accent" d="M36 8h6v6"/>',
    country: '<path d="M24 42S10 31 10 19a14 14 0 0 1 28 0c0 12-14 23-14 23Z"/><circle class="soft-fill" cx="24" cy="19" r="5"/><path class="accent" d="M6 40c9 4 27 4 36 0"/>',
    cycle: '<circle cx="24" cy="24" r="17"/><circle class="ghost" cx="24" cy="24" r="11"/><path d="M24 7v6M41 24h-6M24 41v-6M7 24h6"/><path class="accent" d="M24 24 34 14M34 10v4h4"/><circle class="soft-fill" cx="24" cy="24" r="3"/>',
    crypto: '<path d="M18 9h11a6 6 0 0 1 0 12H18m0 0h13a7 7 0 0 1 0 14H18M18 9v26M15 9h3M15 35h3M23 4v5M29 4v5M23 35v5M29 35v5"/><path class="accent" d="M21 15h8M21 28h10"/>',
    allocation: '<circle cx="24" cy="24" r="17"/><path d="M24 7v17h17"/><path class="accent" d="M36 12A17 17 0 0 1 41 24H24Z"/><path class="ghost" d="M24 24 13 37"/><circle class="soft-fill" cx="24" cy="24" r="3"/>',
    commodity: '<path d="M12 10h24v28H12zM12 18h24M12 30h24"/><path class="accent" d="M19 10v28M29 10v28"/><path d="M24 4s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11Z"/>',
    reserves: '<path d="M8 38h32M11 34V18h8v16M20 34V10h8v24M29 34V22h8v12"/><path class="accent" d="M7 14h13M16 6h13M25 18h13"/><path class="ghost" d="M5 42h38"/>',
    forex: '<path d="M8 16h30M33 11l5 5-5 5M40 32H10M15 27l-5 5 5 5"/><circle class="soft-fill" cx="18" cy="16" r="5"/><circle class="soft-fill" cx="30" cy="32" r="5"/>',
    bonds: '<path d="M7 17h34L24 6Z"/><path d="M11 20v17M19 20v17M29 20v17M37 20v17M7 40h34"/><path class="accent" d="M5 15h38M9 37h30"/><path class="ghost" d="M17 27h14"/>'
  };
  MOCKUP_ICON_PATHS.baskets = MOCKUP_ICON_PATHS.themes;
  MOCKUP_ICON_PATHS.alert = MOCKUP_ICON_PATHS.alerts;
  MOCKUP_ICON_PATHS.flow = MOCKUP_ICON_PATHS.flows;
  MOCKUP_ICON_PATHS.event = MOCKUP_ICON_PATHS.special;
  MOCKUP_ICON_PATHS.structure = MOCKUP_ICON_PATHS.mechanics;
  MOCKUP_ICON_PATHS.commodities = MOCKUP_ICON_PATHS.commodity;
  MOCKUP_ICON_PATHS.bitcoin = MOCKUP_ICON_PATHS.crypto;
  MOCKUP_ICON_PATHS.confluence = '<rect x="6" y="8" width="36" height="28" rx="3"/><path class="ghost" d="M11 13h26v18H11z"/><path class="accent" d="m12 27 6-7 5 4 7-9 6 4"/><circle class="soft-fill" cx="30" cy="15" r="2.4"/><path d="M18 41h12M24 36v5"/>';
  MOCKUP_ICON_PATHS.research = MOCKUP_ICON_PATHS.intelligence;
  MOCKUP_ICON_PATHS.intelligence_hub = MOCKUP_ICON_PATHS.intelligence +
    '<circle cx="24" cy="9" r="1.5"/><circle cx="36" cy="24" r="1.5"/>' +
    '<circle cx="24" cy="38" r="1.5"/><circle cx="12" cy="24" r="1.5"/>';
  MOCKUP_ICON_PATHS.reports = '<path class="ghost" d="M13 7h22l6 6v28H13z"/><path d="M9 4h22l6 6v28H9z"/><path d="M31 4v7h6"/><path class="accent" d="M15 29h16M15 33h12M15 16h16"/><path d="m15 25 4-4 4 2 6-7 3 3"/><circle class="soft-fill" cx="29" cy="16" r="2"/>';
  MOCKUP_ICON_PATHS.vault = '<path class="ghost" d="m7 14 17-9 17 9v23l-17 8-17-8Z"/><path d="m10 16 14-7 14 7v19l-14 7-14-7Z"/><path d="M10 16l14 7 14-7M24 23v19"/><circle class="soft-fill" cx="24" cy="27" r="6"/><path class="accent" d="M24 24v6M21 27h6"/>';
  MOCKUP_ICON_PATHS.neural = '<path class="ghost" d="M6 24h36M24 6v36"/><circle class="soft-fill" cx="24" cy="24" r="5"/><circle cx="11" cy="12" r="3"/><circle cx="37" cy="12" r="3"/><circle cx="9" cy="34" r="3"/><circle cx="39" cy="34" r="3"/><path class="accent" d="M20 21 13 14M28 21l7-7M20 27l-8 5M28 27l8 5M14 12h20M11 15l-2 16M37 15l2 16M12 34h24"/>';
  MOCKUP_ICON_PATHS.foresight = '<path class="ghost" d="M4 24h40M24 4v40"/><path d="M7 25s7-11 17-11 17 11 17 11-7 11-17 11S7 25 7 25Z"/><circle class="soft-fill" cx="24" cy="25" r="5"/><path class="accent" d="M31 12 38 5M34 16h9M13 14 8 9"/>';
  MOCKUP_ICON_PATHS.theme_tracker = '<path class="ghost" d="M8 11h30v23H8z"/><rect x="6" y="8" width="30" height="23" rx="2"/><rect x="12" y="15" width="30" height="23" rx="2"/><path class="accent" d="m17 31 5-6 5 3 8-9M31 19h4v4"/><circle class="soft-fill" cx="22" cy="25" r="2"/>';
  MOCKUP_ICON_PATHS.divergence = '<path class="ghost" d="M6 39h36M9 7v32"/><path d="M10 32c7-1 10-6 15-8s8-1 13-10"/><path class="accent" d="M10 18c7 1 10 6 15 8s9 2 13 10"/><circle class="soft-fill" cx="25" cy="24" r="2.5"/><path d="M36 12h4v4M36 36h4v-4"/>';
  MOCKUP_ICON_PATHS.signal_board = MOCKUP_ICON_PATHS.confluence;
  MOCKUP_ICON_PATHS.smart_money = '<rect x="7" y="15" width="34" height="25" rx="4"/><path d="M17 15v-5h14v5M7 24h34"/><circle class="soft-fill" cx="24" cy="24" r="4"/><path class="accent" d="M24 21v6M21 24h6M13 10 8 5M35 10l5-5"/>';
  MOCKUP_ICON_PATHS.fund_flows = '<path d="m8 14 16-8 16 8-16 8Z"/><path d="m8 22 16 8 16-8M8 30l16 8 16-8"/><path class="accent" d="M14 18v12c0 5 4 9 10 9s10-4 10-9V18"/><path class="ghost" d="M24 22v15"/>';
  MOCKUP_ICON_PATHS.macro_weather = '<circle class="soft-fill" cx="31" cy="14" r="7"/><path class="accent" d="M31 3v4M31 21v4M20 14h4M38 14h4M23 6l3 3M36 19l3 3"/><path d="M11 34c-4 0-6-3-6-6s2-6 6-6c2-6 11-7 15-2 5-1 9 2 9 7 0 4-3 7-8 7Z"/><path d="m13 42 5-5 4 3 6-5 6 2"/>';

  var MOCKUP_TONE_BY_ICON = {
    stocks: 'cyan', sectors: 'violet', rotation: 'violet', alerts: 'cyan',
    alert: 'cyan', options: 'violet', flows: 'cyan', flow: 'cyan',
    scanner: 'violet', darkpool: 'violet', heatmap: 'violet',
    narrative: 'cyan', event: 'violet', commodities: 'cyan',
    commodity: 'cyan', bitcoin: 'violet', crypto: 'violet',
    allocation: 'violet', forex: 'cyan', country: 'cyan', cycle: 'violet'
  };

  var MOCKUP_RESEARCH_ICON_BY_FILE = {
    'intelligence_hub.html': ['intelligence_hub', ''],
    'reports.html': ['reports', ''],
    'research_vault.html': ['vault', 'violet'],
    'neural_web.html': ['neural', 'cyan'],
    'foresight.html': ['foresight', ''],
    'state_of_themes.html': ['theme_tracker', 'violet'],
    'radar.html': ['divergence', 'cyan'],
    'confluence_screener.html': ['signal_board', ''],
    'smart_money.html': ['smart_money', 'violet'],
    'etfs.html': ['fund_flows', 'cyan'],
    'cycle.html': ['cycle', ''],
    'macro_context.html': ['macro_weather', 'cyan'],
    'markets.html': ['global', ''],
    'country_cycles.html': ['country', 'cyan'],
    'sector_cycles.html': ['sectors', 'violet'],
    'sector_cycles_china.html': ['rotation', ''],
    'policy_watch.html': ['policy', ''],
    'alt_data.html': ['research', 'cyan'],
    'special_situations.html': ['special', 'violet']
  };
  var MOCKUP_RESEARCH_DESCRIPTION_BY_FILE = {
    'intelligence_hub.html': 'Your complete market command center',
    'reports.html': 'Deep dives and market calls',
    'research_vault.html': 'Search every published research note',
    'neural_web.html': 'See how every signal votes',
    'foresight.html': 'Themes before markets price them',
    'state_of_themes.html': 'What’s strengthening and fading now',
    'radar.html': 'Where price and reality split',
    'confluence_screener.html': 'Today’s strongest confirmed setups',
    'smart_money.html': 'How top investors are positioned',
    'etfs.html': 'Where institutional capital is moving',
    'cycle.html': 'Where the economy is heading',
    'macro_context.html': 'Growth, inflation and liquidity now'
  };

  /* Country macro hrefs live in _navlinks.html.j2.  Read those canonical
     anchors here so the adaptive wide menu, folded rail and mobile accordion
     all inherit the same destinations (including ../ prefixes on deep pages). */
  function intlCountryHref(key, fallback) {
    var anchor = document.querySelector('[data-intl-country="' + key + '"]');
    return anchor ? anchor.getAttribute('href') : fallback;
  }

  var MARKET_MENU = {
    us: {
      title: 'United States',
      subtitle: 'Macro context, stocks, sectors and live market desks.',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'Regime, growth and inflation now', 'macro.html', 'dashboard'],
          ['Stock Dashboard', 'Standouts, sectors and flows', 'us_stocks.html', 'stocks'],
          ['Sector Central', 'Every sector in one view', 'sector_central.html', 'sectors'],
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
          ['Options Screener', 'Find liquid volatility setups', 'options_screener.html', 'scanner', null, null, ''],
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
      subtitle: 'A-shares, policy, capital flows and fast-moving themes.',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'A-share regime and breadth', 'china.html', 'dashboard'],
          ['Stock Dashboard', 'Standouts, alpha and setups', 'china_stocks.html', 'stocks'],
          ['Market Heatmap', 'Every A-share at a glance', 'china_heatmap.html', 'heatmap'],
          ['China Intelligence', 'Signals, policy and narratives', 'china_intel.html', 'intelligence']
        ]],
        ['Themes & rotation', [
          ['Sector Central', 'Cycles, heat and gated reads', 'sector_central_china.html', 'sectors'],
          ['Theme Baskets', 'Tonghuashun concepts compared', 'baskets_china.html', 'baskets'],
          ['Subsector Rotation', 'Catch concepts gaining velocity', 'subsector_rotation_china.html', 'rotation', null, null, 'cyan'],
          ['Narrative Radar', 'See which stories are running', 'narrative_radar.html', 'narrative', null, null, '']
        ]],
        ['Flows & policy', [
          ['Capital Flow Velocity', 'Where big money accelerates', 'flow_velocity.html', 'flow'],
          ['Policy Watch', 'PBoC and sector policy shifts', 'china_policy_watch.html', 'policy'],
          ['Market Mechanics', 'Participation, limits and tape', 'china_mechanics.html', 'structure', null, null, 'violet'],
          ['Special Situations', 'Unlocks, pledges and catalysts', 'china_special_situations.html', 'event', null, null, '']
        ]]
      ],
      railTitle: 'Explore',
      rail: [
        ['China News', 'Official sources and catalysts', 'china_news.html', 'news'],
        ['Strategies', 'Tactical China scorecards', 'china_strategies.html', 'strategy'],
        ['Alternative Data', 'Signals beyond price', 'china_altdata.html', 'research'],
        ['Browse China research', 'All China research', 'china_intel.html', 'intelligence']
      ],
      note: ['One China system', 'Market, policy and capital context stay connected.']
    },
    hk: {
      title: 'Hong Kong',
      subtitle: 'HSI context, southbound flows and Hong Kong-listed leaders.',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'HSI, liquidity and global risk', 'hk.html', 'dashboard'],
          ['Stock Dashboard', 'Hong Kong standouts and alpha', 'hk_stocks.html', 'stocks'],
          ['Market Heatmap', 'Turnover-sized market overview', 'hk_heatmap.html', 'heatmap'],
          ['Capital Flow Velocity', 'Southbound money in motion', 'flow_velocity.html', 'flow']
        ]],
        ['Themes & rotation', [
          ['Thematic Baskets', 'Equal-weight themes versus HSI', 'baskets_hk.html', 'baskets'],
          ['Narrative Rotation', 'What to hold and rotate', 'allocation_hk.html', 'rotation']
        ]]
      ],
      railTitle: 'Quick access',
      rail: [
        ['China Intelligence', 'Shared policy context', 'china_intel.html', 'intelligence'],
        ['Policy Watch', 'Liquidity and policy shifts', 'china_policy_watch.html', 'policy'],
        ['Hong Kong baskets', 'Browse active themes', 'baskets_hk.html', 'baskets'],
        ['Browse Hong Kong', 'Return to market overview', 'hk.html', 'dashboard']
      ],
      note: ['Lean by design', 'Six core destinations cover the Hong Kong workflow.']
    },
    ca: {
      title: 'Canada',
      subtitle: 'TSX context, commodity sensitivity and Canadian market leaders.',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'TSX, BoC and commodities', 'canada.html', 'dashboard'],
          ['Stock Dashboard', 'Canadian standouts and alpha', 'canada_stocks.html', 'stocks'],
          ['Market Heatmap', 'Every TSX name at a glance', 'canada_heatmap.html', 'heatmap']
        ]],
        ['Themes & rotation', [
          ['Thematic Baskets', 'Themes versus the TSX', 'baskets_canada.html', 'baskets'],
          ['Narrative Rotation', 'What to hold and rotate', 'allocation_canada.html', 'rotation']
        ]]
      ],
      railTitle: 'Quick access',
      rail: [
        ['Banks & insurers', 'Canadian financial leadership', 'canada_stocks.html', 'stocks'],
        ['Energy complex', 'Oil-sensitive market context', 'commodities.html', 'commodities'],
        ['Gold & materials', 'Materials leadership', 'baskets_canada.html', 'baskets'],
        ['Browse Canada', 'Return to market overview', 'canada.html', 'dashboard']
      ],
      note: ['Home-market aware', 'Search examples and popular tickers adapt to Canada.']
    },
    intl: {
      title: 'International',
      subtitle: 'Compare major markets, global leaders and cross-country themes.',
      sections: [
        ['Global markets', [
          ['World Dashboard', 'Major markets compared together', 'intl.html', 'global'],
          ['Stock Dashboard', 'Cross-market standouts and sectors', 'intl_stocks.html', 'stocks'],
          ['Global Market Cycles', 'Every major market on one clock', 'markets.html', 'cycle'],
          ['Country Cycles', 'Countries and regions compared', 'country_cycles.html', 'country', null, null, '']
        ]],
        ['Themes', [
          ['Thematic Baskets', 'Cross-country themes outside America', 'baskets_intl.html', 'baskets', null, null, 'cyan']
        ]]
      ],
      railTitle: 'Regions',
      rail: [
        ['Japan', 'BoJ, wages, JGBs and yen', intlCountryHref('jp', 'japan.html'), 'dashboard'],
        ['South Korea', 'BOK, exports, credit and won', intlCountryHref('kr', 'south_korea.html'), 'dashboard'],
        ['Euro Area', 'EA21, ECB, HICP and bank credit', intlCountryHref('ez', 'euro_area.html'), 'dashboard'],
        ['United Kingdom', 'BoE, services inflation and gilts', intlCountryHref('gb', 'united_kingdom.html'), 'dashboard'],
        ['India', 'RBI, food inflation, credit and rupee', intlCountryHref('in', 'india.html'), 'dashboard']
      ],
      note: ['One global lens', 'Country context without a maze of nested menus.']
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
      subtitle: 'Digital assets, commodities, currencies and fixed income.',
      sections: [
        ['Digital assets', [
          ['Crypto Intelligence', 'Market state, flows, leverage and asset lanes', 'crypto.html', 'crypto'],
          ['Bitcoin Vector', 'Bitcoin state, risk and cycle evidence', 'vector.html', 'bitcoin', null, null, ''],
          ['Strategy Track Record', 'Cycle and allocation evidence', 'vector.html#strategy-track-record', 'strategy', null, null, 'cyan']
        ]],
        ['Commodities', [
          ['Commodity Dashboard', 'Gold, oil, copper and silver', 'commodities.html', 'commodity', null, null, ''],
          ['Commodity Strategies', 'Tactical views by commodity', 'commodity_strategies.html', 'scanner', null, null, 'violet'],
          ['Strategic Reserves', 'Global stockpiles versus oil', 'spr.html', 'reserves', null, null, 'cyan']
        ]],
        ['Rates & FX', [
          ['Forex', 'Dollar, carry and currency pairs', 'forex.html', 'forex'],
          ['Bonds', 'Curve, credit and duration', 'bonds.html', 'bonds']
        ]]
      ],
      railTitle: 'Quick access',
      rail: [
        ['Gold', 'Precious metals context', 'commodities.html#gold', 'commodities'],
        ['Crude oil', 'Energy market context', 'commodities.html#oil', 'commodities'],
        ['Copper', 'Industrial metals context', 'commodities.html#copper', 'commodities'],
        ['Bitcoin Terminal', 'Open the BTC chart', 'stock.html?ticker=BTC-USD', 'crypto'],
        ['Browse other assets', 'All non-equity desks', 'commodities.html', 'dashboard']
      ],
      note: ['Grouped by behavior', 'Related assets sit together without extra hover layers.']
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

  function iconMarkup(type, tone) {
    var path = MOCKUP_ICON_PATHS[type] || MOCKUP_ICON_PATHS.dashboard;
    var resolvedTone = tone === undefined ? (MOCKUP_TONE_BY_ICON[type] || '') : tone;
    return '<span class="icon-drawing nav-market-icon ' + esc(resolvedTone) + '" aria-hidden="true">' +
      '<svg viewBox="0 0 48 48">' + path + '</svg></span>';
  }

  function destinationMarkup(item, prefix, rail) {
    if (rail) {
      return '<a class="rail-link nav-market-rail-item" href="' + esc(prefix + item[2]) + '">' +
        '<span>' + langText(item[0], item[4]) + '</span>' +
        '<span class="rail-arrow nav-market-arrow" aria-hidden="true">↗</span></a>';
    }
    return '<a class="mega-item nav-market-item" href="' + esc(prefix + item[2]) + '">' +
      iconMarkup(item[3], item[6]) +
      '<span class="nav-market-copy"><span class="item-title nav-market-title">' + langText(item[0], item[4]) + '</span>' +
      '<span class="item-desc d">' + langText(item[1], item[5]) + '</span></span></a>';
  }

  function marketMarkup(key, prefix) {
    var data = MARKET_MENU[key], main = '', rail = '';
    if (!data) return '';
    for (var i = 0; i < data.sections.length; i++) {
      var section = data.sections[i], items = '';
      for (var j = 0; j < section[1].length; j++) items += destinationMarkup(section[1][j], prefix, false);
      main += '<section class="mega-section nav-market-section"><div class="section-label nav-market-heading">' +
        langText(section[0]) + '</div><div class="item-grid nav-market-grid">' + items + '</div></section>';
    }
    for (var k = 0; k < data.rail.length; k++) rail += destinationMarkup(data.rail[k], prefix, true);
    if (data.note) {
      rail += '<div class="rail-note nav-market-note"><strong>' + langText(data.note[0]) +
        '</strong><span>' + langText(data.note[1]) + '</span></div>';
    }
    return '<div class="mega-main nav-market-main"><header class="menu-intro nav-market-intro">' +
      '<div><h2 class="nav-market-name">' + langText(data.title) + '</h2>' +
      '<p class="nav-market-subtitle">' + langText(data.subtitle) + '</p></div>' +
      '<span class="menu-count nav-market-count">' + data.sections.reduce(function (n, s) { return n + s[1].length; }, 0) +
      ' destinations</span></header>' + main + '</div>' +
      '<aside class="mega-rail nav-market-rail"><div class="section-label nav-market-heading">' +
      langText(data.railTitle || 'Explore') +
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
      menu.className = 'nav-dd-menu mega-menu nav-market-menu';
      menu.setAttribute('data-nav-market-key', key);
      menu.innerHTML = marketMarkup(key, prefixOf(dd));
    }
  }

  function removeLegacyCryptoMenu(links) {
    if (!links) return;
    var top = links.querySelectorAll(':scope > .nav-dd');
    for (var i = 0; i < top.length; i++) {
      if (marketKeyOf(top[i]) === 'crypto') {
        top[i].remove();
        return;
      }
    }
  }

  /* Existing rendered pages are deployed independently from the shared
     template.  During that rollout window, normalize their Research DOM to the
     same exact component emitted by _navlinks.html.j2.  This is a compatibility
     bridge only: it adds the approved classes and replaces the old mask glyphs
     with the mockup's inline drawings; it does not maintain a second design. */
  function enhanceResearchMenu(links) {
    var menu = links && links.querySelector('.nav-dd-menu.nav-mega');
    if (!menu || menu.getAttribute('data-mockup-exact') === '1') return;
    menu.setAttribute('data-mockup-exact', '1');
    menu.classList.add('mega-menu');

    var main = menu.querySelector(':scope > .nav-mega-main');
    var rail = menu.querySelector(':scope > .nav-mega-rail');
    if (main) main.classList.add('mega-main');
    if (rail) rail.classList.add('mega-rail');

    menu.querySelectorAll('.nav-mega-section').forEach(function (section) {
      section.classList.add('mega-section');
    });
    menu.querySelectorAll('.nav-mega-h').forEach(function (heading) {
      heading.classList.add('section-label');
    });
    menu.querySelectorAll('.nav-mega-item-grid').forEach(function (grid) {
      grid.classList.add('item-grid');
    });

    menu.querySelectorAll('.nm-feat, .nav-mega-item').forEach(function (item) {
      item.classList.add('mega-item');
      var title = item.querySelector('.nm-t');
      var desc = item.querySelector('.d');
      if (title) title.classList.add('item-title');
      if (desc) desc.classList.add('item-desc');

      var file = fileOf(item);
      var iconSpec = MOCKUP_RESEARCH_ICON_BY_FILE[file] || ['dashboard', ''];
      var exactDescription = MOCKUP_RESEARCH_DESCRIPTION_BY_FILE[file];
      var englishDescription = desc && desc.querySelector('.l-en');
      if (exactDescription && englishDescription) {
        englishDescription.textContent = exactDescription;
      }
      var oldIcon = item.querySelector('.nm-ic');
      if (oldIcon) {
        oldIcon.className = 'icon-drawing nm-ic ' + iconSpec[1];
        oldIcon.innerHTML = '<svg viewBox="0 0 48 48" aria-hidden="true">' +
          (MOCKUP_ICON_PATHS[iconSpec[0]] || MOCKUP_ICON_PATHS.dashboard) + '</svg>';
      }
    });

    if (!rail) return;
    var railHeading = rail.querySelector(':scope > .nav-mega-h');
    if (railHeading) railHeading.classList.add('section-label');

    rail.querySelectorAll(':scope > .nav-rail-item').forEach(function (item) {
      item.classList.add('rail-link');
      var title = item.querySelector('.nm-t');
      var arrow = item.querySelector('.nav-drill-arrow');
      if (title) {
        item.innerHTML = '<span>' + title.innerHTML + '</span>' +
          '<span class="rail-arrow nav-drill-arrow" aria-hidden="true">' +
          (arrow ? arrow.textContent : '↗') + '</span>';
      }
    });

    var drillTrigger = rail.querySelector(':scope > .nav-drill > .nav-drill-trigger');
    if (drillTrigger) {
      var drillTitle = drillTrigger.querySelector('.nm-t');
      drillTrigger.classList.add('rail-link');
      drillTrigger.innerHTML = '<span>' + (drillTitle ? drillTitle.innerHTML : 'Global Cycles') +
        '</span><span class="rail-arrow nav-drill-arrow" aria-hidden="true">›</span>';
    }

    var cta = rail.querySelector(':scope > .nav-mastermind-cta');
    if (cta) cta.remove();
    if (!rail.querySelector(':scope > .mockup-browse-research')) {
      var browse = document.createElement('a');
      browse.className = 'rail-link nav-rail-item mockup-browse-research';
      browse.href = prefixOf(menu.closest('.nav-dd')) + 'intelligence_hub.html';
      browse.innerHTML = '<span><span class="l-en">Browse all research</span><span class="l-zh">浏览全部研究</span></span>' +
        '<span class="rail-arrow nav-drill-arrow" aria-hidden="true">→</span>';
      rail.appendChild(browse);
    }
    if (!rail.querySelector(':scope > .rail-note')) {
      var note = document.createElement('div');
      note.className = 'rail-note';
      note.innerHTML = '<strong><span class="l-en">Cleaner by design</span><span class="l-zh">简洁设计</span></strong>' +
        '<span class="l-en">Detailed diagnostics and proprietary labs move to the admin console.</span>' +
        '<span class="l-zh">详细诊断和专有实验室移至管理控制台。</span>';
      rail.appendChild(note);
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
    // This node was initialized while it still lived on the top rail. Folding
    // it must synchronously clear any inherited hover-open state; from here on
    // the explicit drill trigger is the only owner of its country panel.
    dd.classList.remove('nav-hover-open');

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

  // Wide desktop menus are anchored to the full navigation rail so they can
  // stay viewport-safe. That leaves the intentional visual air gap below the
  // trigger outside the CSS :hover tree. Keep the current menu alive briefly
  // while a fine pointer crosses the gap, then close it only if neither the
  // trigger/menu nor keyboard focus was reached. Touch/mobile keeps its
  // existing click accordion and never enters this path.
  function bindHoverSafeDropdowns(links) {
    var fineHover = window.matchMedia('(hover: hover) and (pointer: fine)');
    links.querySelectorAll(':scope > .nav-dd').forEach(function (dd) {
      if (dd.getAttribute('data-nav-hover-safe')) return;
      dd.setAttribute('data-nav-hover-safe', '1');

      var closeTimer = 0;
      var trigger = dd.querySelector(':scope > a.nav-link');
      var menu = dd.querySelector(':scope > .nav-dd-menu');
      if (!trigger || !menu) return;

      function canHover() {
        // A country node may be moved under International after this listener
        // is attached. Once folded, it is a click-owned drill and must never
        // reuse its former top-rail hover behavior.
        return dd.parentElement === links &&
          !dd.classList.contains('nav-market-drill') &&
          window.innerWidth > 900 && fineHover.matches;
      }

      function openMenu() {
        if (!canHover()) {
          dd.classList.remove('nav-hover-open');
          return;
        }
        window.clearTimeout(closeTimer);
        dd.parentElement.querySelectorAll(':scope > .nav-dd.nav-hover-open').forEach(function (other) {
          if (other !== dd) other.classList.remove('nav-hover-open');
        });
        dd.classList.add('nav-hover-open');
      }

      function hoverGraceMs() {
        var triggerRect = trigger.getBoundingClientRect();
        var menuRect = menu.getBoundingClientRect();
        var gap = Math.max(0, menuRect.top - triggerRect.bottom);
        return Math.min(1000, Math.max(420, 360 + Math.round(gap * 8)));
      }

      function closeMenuSoon() {
        window.clearTimeout(closeTimer);
        closeTimer = window.setTimeout(function () {
          if (!dd.matches(':hover') && !dd.contains(document.activeElement)) {
            dd.classList.remove('nav-hover-open');
          }
        }, hoverGraceMs());
      }

      dd.addEventListener('pointerenter', openMenu);
      dd.addEventListener('pointerleave', closeMenuSoon);
      menu.addEventListener('pointerenter', openMenu);
      menu.addEventListener('pointerleave', closeMenuSoon);
      dd.addEventListener('focusin', openMenu);
      dd.addEventListener('focusout', closeMenuSoon);
      dd.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        window.clearTimeout(closeTimer);
        dd.classList.remove('nav-hover-open');
      });
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
    bindHoverSafeDropdowns(links);

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
      removeLegacyCryptoMenu(links);
      enhanceMarketMenus(links);
      enhanceResearchMenu(links);
      capture(links);
      remarkActive(links);
      bindHoverSafeDropdowns(links);
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

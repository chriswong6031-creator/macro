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
    bonds: '<path d="M7 17h34L24 6Z"/><path d="M11 20v17M19 20v17M29 20v17M37 20v17M7 40h34"/><path class="accent" d="M5 15h38M9 37h30"/><path class="ghost" d="M17 27h14"/>',
    /* The two Mastermind cards' own template glyphs (_navlinks.html.j2),
       verbatim: the allocation donut (Portfolio — the user's book) and the
       pinned processor (Bot — the AI's own paper book). They exist here so the
       compatibility bridge can only ever normalise these cards to their REAL
       icons — before this, both fell through to the `dashboard` default and the
       two adjacent "Mastermind …" cards rendered byte-identical glyphs, which
       read as one product listed twice (operator report, 2026-08-07). */
    portfolio: '<path class="ghost" d="M25 7a17 17 0 0 1 16 16"/><circle cx="21" cy="26" r="14"/><circle class="ghost" cx="21" cy="26" r="6"/><path class="accent" d="M21 12a14 14 0 0 1 12.1 7L21 26Z"/><path d="M21 12v14l12.1-7"/><circle class="soft-fill" cx="21" cy="26" r="3.2"/><path class="accent" d="M39 41v-9M44 41v-15"/>',
    bot: '<path d="M17 11V6M24 11V6M31 11V6M17 37v5M24 37v5M31 37v5M11 17H6M11 24H6M11 31H6M37 17h5M37 24h5M37 31h5"/><rect x="11" y="11" width="26" height="26" rx="5"/><path class="accent" d="m15 29 4-4 3.5 2.5 3.5-5.5"/><circle class="soft-fill" cx="26" cy="22" r="2.4"/><path class="ghost" d="m28 20.5 6-5"/>'
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
  MOCKUP_ICON_PATHS.market_memory = '<path class="ghost" d="M8 10h32v28H8z"/><path d="M7 8h14c5 0 8 3 8 8v24c0-5-3-8-8-8H7zM41 8H27v32c0-5 3-8 8-8h6z"/><path class="accent" d="M13 16h9M13 21h7M33 15h4M33 20h4"/><circle class="soft-fill" cx="27" cy="29" r="4"/><path d="M24 29h6"/>';
  MOCKUP_ICON_PATHS.foresight = '<path class="ghost" d="M4 24h40M24 4v40"/><path d="M7 25s7-11 17-11 17 11 17 11-7 11-17 11S7 25 7 25Z"/><circle class="soft-fill" cx="24" cy="25" r="5"/><path class="accent" d="M31 12 38 5M34 16h9M13 14 8 9"/>';
  MOCKUP_ICON_PATHS.theme_tracker = '<path class="ghost" d="M8 11h30v23H8z"/><rect x="6" y="8" width="30" height="23" rx="2"/><rect x="12" y="15" width="30" height="23" rx="2"/><path class="accent" d="m17 31 5-6 5 3 8-9M31 19h4v4"/><circle class="soft-fill" cx="22" cy="25" r="2"/>';
  MOCKUP_ICON_PATHS.divergence = '<path class="ghost" d="M6 39h36M9 7v32"/><path d="M10 32c7-1 10-6 15-8s8-1 13-10"/><path class="accent" d="M10 18c7 1 10 6 15 8s9 2 13 10"/><circle class="soft-fill" cx="25" cy="24" r="2.5"/><path d="M36 12h4v4M36 36h4v-4"/>';
  MOCKUP_ICON_PATHS.signal_board = MOCKUP_ICON_PATHS.confluence;
  MOCKUP_ICON_PATHS.smart_money = '<rect x="7" y="15" width="34" height="25" rx="4"/><path d="M17 15v-5h14v5M7 24h34"/><circle class="soft-fill" cx="24" cy="24" r="4"/><path class="accent" d="M24 21v6M21 24h6M13 10 8 5M35 10l5-5"/>';
  MOCKUP_ICON_PATHS.fund_flows = '<path d="m8 14 16-8 16 8-16 8Z"/><path d="m8 22 16 8 16-8M8 30l16 8 16-8"/><path class="accent" d="M14 18v12c0 5 4 9 10 9s10-4 10-9V18"/><path class="ghost" d="M24 22v15"/>';
  MOCKUP_ICON_PATHS.macro_weather = '<circle class="soft-fill" cx="31" cy="14" r="7"/><path class="accent" d="M31 3v4M31 21v4M20 14h4M38 14h4M23 6l3 3M36 19l3 3"/><path d="M11 34c-4 0-6-3-6-6s2-6 6-6c2-6 11-7 15-2 5-1 9 2 9 7 0 4-3 7-8 7Z"/><path d="m13 42 5-5 4 3 6-5 6 2"/>';
  MOCKUP_ICON_PATHS.earnings_wire = '<path class="ghost" d="M8 7h25l7 7v27H8z"/><path d="M6 5h25l7 7v27H6zM31 5v8h7"/><path class="accent" d="M12 29h5l3-7 5 12 4-9 3 4h3"/><path d="M12 16h14M12 20h9"/><circle class="soft-fill" cx="34" cy="29" r="3"/>';

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
    /* fileOf() reduces the Bot card's absolute href to its host string. */
    'watchlist.html': ['portfolio', 'violet'],
    'bot.mastermind-x.com': ['bot', 'cyan'],
    'reports.html': ['reports', ''],
    'research_vault.html': ['vault', 'violet'],
    'earnings_wire': ['earnings_wire', 'cyan'],
    'neural_web.html': ['neural', 'cyan'],
    'market_memory.html': ['market_memory', 'violet'],
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
    'earnings_wire': 'Verified calls, weekly intelligence and company context',
    'neural_web.html': 'See how every signal votes',
    'market_memory.html': 'Put today beside comparable episodes',
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

  /* Every row is bilingual. The row shape is
       [en title, en desc, href, icon, zh title, zh desc, tone, href-gate]
     and a section is [en heading, rows, zh heading]; titles/subtitles/rail
     headings/notes carry a `…Zh` sibling key. langText() below picks the pair,
     so a row that forgets its Chinese silently ships English into Chinese mode
     — which is exactly the bug this table used to have. Keep both columns
     filled when adding a destination. */
  var MARKET_MENU = {
    us: {
      title: 'United States',
      titleZh: '美国',
      subtitle: 'Macro context, stocks, sectors and live market desks.',
      subtitleZh: '宏观环境、个股、板块与实时行情台。',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'Regime, growth and inflation now', 'macro.html', 'dashboard',
            '宏观仪表盘', '当前周期、增长与通胀'],
          ['Stock Dashboard', 'Standouts, sectors and flows', 'us_stocks.html', 'stocks',
            '股票仪表盘', '领涨股、板块与资金流'],
          // OIP W1.6-B: Intraday Flow Tracker moves OUT of the options section to
          // sit beside the Stock Dashboard, mirroring _navlinks.html.j2 — it is a
          // live session board, not an options page. The 8th element is
          // still its href gate, so it stays as conditional here as in the template.
          ['Intraday Flow Tracker', 'Live session board — volume, tape and stance lanes · ≈15-min delayed',
            'intraday_flow.html', 'dashboard', '盘中资金流追踪', '盘中实时看板 — 量能、盘面与操作分级 · 约延迟15分钟',
            null, 'intraday_flow.html'],
          // Sector Intelligence consolidation (#4237, 2026-08): Sector Central + Theme
          // Baskets + Subsector Rotation are ONE page now (the old URLs are redirect
          // stubs) — one menu row, matching the collapsed _navlinks flyout.
          ['Sector Intelligence', 'Sectors, themes & rotation in one read', 'sector_central.html', 'sectors',
            '行业情报', '板块、主题与轮动一页读']
        ], '市场总览'],
        ['Signals & strategy', [
          ['Subsector Confluence', 'Entry-ready subsectors and stocks to review', 'sector_central.html#confluence', 'confluence',
            '子行业汇聚', '可关注的子行业与个股'],
          ['Strategies', 'Tactical scorecards and positioning', 'strategies.html', 'strategy',
            '策略', '战术记分卡与仓位'],
          ['Alert Center', 'Ranked market-moving alerts', 'alerts.html', 'alert',
            '警报中心', '分级的市场异动警报'],
          ['News Feed', 'Catalysts, headlines and sentiment', 'news.html', 'news',
            '新闻流', '催化事件、头条与情绪']
        ], '信号与策略'],
        // OIP W1.6-B "One Door", mirrored from _navlinks.html.j2's own flyout
        // (ONE_DOOR_RULING_AND_SPEC.md §3/§4). The workspace absorbed gex.html
        // along with the screener, flow desk and flow leaders; all four are
        // redirect stubs now, so this section drops the 'Options Desk' row rather
        // than pointing a reader at a bounce. Intraday Flow Tracker moved up to
        // 'Market overview'. Dark Pool Desk stays guarded exactly like its
        // template row (8th element = the href gate). The label the ruling
        // renamed is the template flyout's trigger, which has no counterpart
        // here.
        ['Market structure', [
          ['Options — the workspace', 'Daily Brief · Flow · Scanner · Ticker · Leaders',
            'options.html', 'options', '期权工作台', '每日简报 · 资金流 · 筛选 · 个股 · 领头股'],
          ['Dark Pool Desk', 'Off-exchange volume · short ratio · ATS venues',
            'darkpool.html', 'darkpool', '暗池成交', '场外成交量 · 融券比率 · ATS 交易平台',
            null, 'darkpool.html'],
          ['Market Structure', 'GEX regime · machine flows · dispersion · weekly range',
            'market_structure.html', 'structure', '市场结构', '做市商持仓 · 程序化资金 · 离散度 · 周内区间']
        ], '市场结构']
      ],
      // 'Stock Terminal' (stock.html with no ticker) was removed 2026-08-04 on
      // operator report: the bare analyzer has nothing to show until a ticker is
      // picked, so the rail's most prominent row led to an empty page. Ticker
      // entry belongs to the global nav search, which every page already carries.
      rail: [
        ['Market Heatmap', 'See the whole tape', 'sector_central.html', 'heatmap', '市场热力图'],
        ['Subsector Confluence', 'Find aligned groups', 'sector_central.html#confluence', 'confluence', '子行业汇聚'],
        ['Browse U.S. markets', 'All U.S. destinations', 'macro.html', 'dashboard', '浏览美国全部页面']
      ],
      note: ['Built for quick decisions', 'The most-used desks stay one click away.'],
      noteZh: ['为快速决策而建', '最常用的页面永远一键可达。']
    },
    cn: {
      title: 'China',
      titleZh: '中国',
      subtitle: 'A-shares, policy, capital flows and fast-moving themes.',
      subtitleZh: 'A股、政策、资金流，以及轮动最快的那些题材。',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'A-share regime and breadth', 'china.html', 'dashboard',
            '宏观仪表盘', 'A股市况与市场广度'],
          ['Stock Dashboard', 'Standouts, alpha and setups', 'china_stocks.html', 'stocks',
            '股票仪表盘', '强势股、超额收益与买点'],
          ['Market Heatmap', 'Every A-share at a glance', 'china_heatmap.html', 'heatmap',
            '市场热力图', '全部A股一眼看尽'],
          ['China Intelligence', 'Signals, policy and narratives', 'china_intel.html', 'intelligence',
            '中国情报中心', '信号、政策与市场叙事']
        ], '市场总览'],
        ['Themes & rotation', [
          // 2026-08 China SI consolidation: the three sector/theme/rotation pages are one now
          // (baskets_china.html / subsector_rotation_china.html are redirect stubs).
          ['Sector Intelligence', 'Gated board, cycle map and rotation in one', 'sector_central_china.html', 'sectors',
            '行业情报', '研判、周期图谱和轮动，一页看完'],
          ['Narrative Radar', 'See which stories are running', 'narrative_radar.html', 'narrative',
            '题材雷达', '看清现在哪些题材在走', '']
        ], '主题与轮动'],
        ['Flows & policy', [
          ['Capital Flow Velocity', 'Where big money accelerates', 'flow_velocity.html', 'flow',
            '资金流速', '主力资金在哪里加速'],
          ['Policy Watch', 'PBoC and sector policy shifts', 'china_policy_watch.html', 'policy',
            '政策观察', '央行动向与行业政策'],
          ['Market Mechanics', 'Participation, limits and tape', 'china_mechanics.html', 'structure',
            '盘面机制', '参与度、涨跌停与盘面', 'violet'],
          ['Special Situations', 'Unlocks, pledges and catalysts', 'china_special_situations.html', 'event',
            '特殊事件', '解禁、质押与催化事件', '']
        ], '资金与政策']
      ],
      railTitle: 'Explore',
      railTitleZh: '探索',
      rail: [
        ['China News', 'Official sources and catalysts', 'china_news.html', 'news', '中国新闻'],
        ['Strategies', 'Tactical China scorecards', 'china_strategies.html', 'strategy', '策略'],
        ['Alternative Data', 'Signals beyond price', 'china_altdata.html', 'research', '另类数据'],
        ['Browse China research', 'All China research', 'china_intel.html', 'intelligence', '浏览中国全部研究']
      ],
      note: ['One China system', 'Market, policy and capital context stay connected.'],
      noteZh: ['中国板块，一套系统', '市场、政策和资金脉络始终连在一起。']
    },
    hk: {
      title: 'Hong Kong',
      titleZh: '香港',
      subtitle: 'HSI context, southbound flows and Hong Kong-listed leaders.',
      subtitleZh: '恒指环境、南向资金与港股龙头。',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'HSI, liquidity and global risk', 'hk.html', 'dashboard',
            '宏观仪表盘', '恒指、流动性与全球风险'],
          ['Stock Dashboard', 'Hong Kong standouts and alpha', 'hk_stocks.html', 'stocks',
            '股票仪表盘', '港股领涨股与阿尔法'],
          ['Market Heatmap', 'Turnover-sized market overview', 'hk_heatmap.html', 'heatmap',
            '市场热力图', '按成交额加权的全景'],
          ['Capital Flow Velocity', 'Southbound money in motion', 'flow_velocity.html', 'flow',
            '资金流速', '南向资金动向']
        ], '市场总览'],
        ['Themes & rotation', [
          ['Thematic Baskets', 'Equal-weight themes versus HSI', 'baskets_hk.html', 'baskets',
            '主题篮子', '等权主题篮子 vs 恒指'],
          ['Narrative Rotation', 'What to hold and rotate', 'allocation_hk.html', 'rotation',
            '主题轮动', '持有哪个主题 · 何时轮动']
        ], '主题与轮动']
      ],
      railTitle: 'Quick access',
      railTitleZh: '快速入口',
      rail: [
        ['China Intelligence', 'Shared policy context', 'china_intel.html', 'intelligence', '中国情报中心'],
        ['Policy Watch', 'Liquidity and policy shifts', 'china_policy_watch.html', 'policy', '政策观察'],
        ['Hong Kong baskets', 'Browse active themes', 'baskets_hk.html', 'baskets', '香港主题篮子'],
        ['Browse Hong Kong', 'Return to market overview', 'hk.html', 'dashboard', '浏览香港全部页面']
      ],
      note: ['Lean by design', 'Six core destinations cover the Hong Kong workflow.'],
      noteZh: ['精简设计', '六个核心页面覆盖香港的完整流程。']
    },
    ca: {
      title: 'Canada',
      titleZh: '加拿大',
      subtitle: 'TSX context, commodity sensitivity and Canadian market leaders.',
      subtitleZh: '多伦多指数环境、商品敏感度与加股龙头。',
      sections: [
        ['Market overview', [
          ['Market Dashboard', 'TSX, BoC and commodities', 'canada.html', 'dashboard',
            '宏观仪表盘', 'TSX、加央行与大宗商品'],
          ['Stock Dashboard', 'Canadian standouts and alpha', 'canada_stocks.html', 'stocks',
            '股票仪表盘', '加股领涨股与阿尔法'],
          ['Market Heatmap', 'Every TSX name at a glance', 'canada_heatmap.html', 'heatmap',
            '市场热力图', '全部TSX个股一眼看尽']
        ], '市场总览'],
        ['Themes & rotation', [
          ['Thematic Baskets', 'Themes versus the TSX', 'baskets_canada.html', 'baskets',
            '主题篮子', '主题篮子 vs 标普/多伦多'],
          ['Narrative Rotation', 'What to hold and rotate', 'allocation_canada.html', 'rotation',
            '主题轮动', '持有哪个主题 · 何时轮动']
        ], '主题与轮动']
      ],
      railTitle: 'Quick access',
      railTitleZh: '快速入口',
      rail: [
        ['Banks & insurers', 'Canadian financial leadership', 'canada_stocks.html', 'stocks', '银行与保险'],
        ['Energy complex', 'Oil-sensitive market context', 'commodities.html', 'commodities', '能源板块'],
        ['Gold & materials', 'Materials leadership', 'baskets_canada.html', 'baskets', '黄金与原材料'],
        ['Browse Canada', 'Return to market overview', 'canada.html', 'dashboard', '浏览加拿大全部页面']
      ],
      note: ['Home-market aware', 'Search examples and popular tickers adapt to Canada.'],
      noteZh: ['识别主场市场', '搜索示例与热门代码会跟着切到加拿大。']
    },
    intl: {
      title: 'International',
      titleZh: '国际',
      subtitle: 'Compare major markets, global leaders and cross-country themes.',
      subtitleZh: '比较主要市场、全球龙头与跨国主题。',
      sections: [
        ['Global markets', [
          ['World Dashboard', 'Major markets compared together', 'intl.html', 'global',
            '全球仪表盘', '主要市场同台对比'],
          ['Stock Dashboard', 'Cross-market standouts and sectors', 'intl_stocks.html', 'stocks',
            '股票仪表盘', '跨市场领涨股与板块'],
          ['Global Market Cycles', 'Every major market on one clock', 'markets.html', 'cycle',
            '全球市场周期', '主要市场同在一张周期钟上'],
          ['Country Cycles', 'Countries and regions compared', 'country_cycles.html', 'country',
            '国家周期', '国家与区域对比', '']
        ], '全球市场'],
        ['Themes', [
          ['Thematic Baskets', 'Cross-country themes outside America', 'baskets_intl.html', 'baskets',
            '主题篮子', '跨国主题篮子 · 除美', 'cyan']
        ], '主题']
      ],
      railTitle: 'Regions',
      railTitleZh: '国家与区域',
      rail: [
        ['Japan', 'BoJ, wages, JGBs and yen', intlCountryHref('jp', 'japan.html'), 'dashboard', '日本'],
        ['South Korea', 'BOK, exports, credit and won', intlCountryHref('kr', 'south_korea.html'), 'dashboard', '韩国'],
        ['Euro Area', 'EA21, ECB, HICP and bank credit', intlCountryHref('ez', 'euro_area.html'), 'dashboard', '欧元区'],
        ['United Kingdom', 'BoE, services inflation and gilts', intlCountryHref('gb', 'united_kingdom.html'), 'dashboard', '英国'],
        ['India', 'RBI, food inflation, credit and rupee', intlCountryHref('in', 'india.html'), 'dashboard', '印度']
      ],
      note: ['One global lens', 'Country context without a maze of nested menus.'],
      noteZh: ['一个全球视角', '看懂各国脉络，不必层层翻菜单。']
    },
    crypto: {
      title: 'Crypto',
      titleZh: '加密资产',
      subtitle: 'Cycle, risk, allocation and strategy for digital assets.',
      subtitleZh: '数字资产的周期、风险、配置与策略。',
      sections: [
        ['Market overview', [
          ['Crypto Cockpit', 'Market board, flows and leverage', 'crypto.html', 'dashboard',
            '加密驾驶舱', '行情盘、资金流与杠杆'],
          ['Bitcoin Vector', 'State, risk and cycle', 'vector.html', 'bitcoin',
            '比特币向量', '状态、风险与周期']
        ], '市场总览'],
        ['Portfolio', [
          ['Allocation', 'Bitcoin, ether, alts and cash', 'crypto.html#allocation', 'allocation',
            '配置', '比特币、以太坊、山寨与现金'],
          ['Strategy Track Record', 'Cycle and allocation evidence', 'vector.html#strategy-track-record', 'strategy',
            '策略战绩', '周期与配置的实证']
        ], '组合']
      ],
      rail: [
        ['Bitcoin Terminal', 'Open the BTC chart', 'stock.html?ticker=BTC-USD', 'bitcoin', '比特币终端'],
        ['Allocation', 'Current portfolio stance', 'crypto.html#allocation', 'allocation', '配置'],
        ['Browse Crypto', 'Return to the cockpit', 'crypto.html', 'dashboard', '浏览加密全部页面']
      ]
    },
    assets: {
      title: 'Other Assets',
      titleZh: '其他资产',
      subtitle: 'Digital assets, commodities, currencies and fixed income.',
      subtitleZh: '数字资产、大宗商品、货币与固定收益。',
      sections: [
        ['Digital assets', [
          ['Crypto Intelligence', 'Market state, flows, leverage and asset lanes', 'crypto.html', 'crypto',
            '加密情报', '市场状态、资金流、杠杆与资产分道'],
          ['Bitcoin Vector', 'Bitcoin state, risk and cycle evidence', 'vector.html', 'bitcoin',
            '比特币向量', '比特币状态、风险与周期实证', ''],
          ['Strategy Track Record', 'Cycle and allocation evidence', 'vector.html#strategy-track-record', 'strategy',
            '策略战绩', '周期与配置的实证', 'cyan']
        ], '数字资产'],
        ['Commodities', [
          ['Commodity Dashboard', 'Gold, oil, copper and silver', 'commodities.html', 'commodity',
            '商品仪表盘', '黄金、原油、铜与白银', ''],
          ['Commodity Strategies', 'Tactical views by commodity', 'commodity_strategies.html', 'scanner',
            '商品策略', '分品种的战术观点', 'violet'],
          ['Strategic Reserves', 'Global stockpiles versus oil', 'spr.html', 'reserves',
            '战略储备', '各国储备水平与油价对照', 'cyan']
        ], '大宗商品'],
        ['Rates & FX', [
          ['Forex', 'Dollar, carry and currency pairs', 'forex.html', 'forex',
            '外汇', '美元、套息与货币对'],
          ['Bonds', 'Curve, credit and duration', 'bonds.html', 'bonds',
            '债券', '曲线、信用与久期']
        ], '利率与外汇']
      ],
      railTitle: 'Quick access',
      railTitleZh: '快速入口',
      rail: [
        ['Gold', 'Precious metals context', 'commodities.html#gold', 'commodities', '黄金'],
        ['Crude oil', 'Energy market context', 'commodities.html#oil', 'commodities', '原油'],
        ['Copper', 'Industrial metals context', 'commodities.html#copper', 'commodities', '铜'],
        ['Bitcoin Terminal', 'Open the BTC chart', 'stock.html?ticker=BTC-USD', 'crypto', '比特币终端'],
        ['Browse other assets', 'All non-equity desks', 'commodities.html', 'dashboard', '浏览其他资产']
      ],
      note: ['Grouped by behavior', 'Related assets sit together without extra hover layers.'],
      noteZh: ['按行为分组', '相关资产放在一起，不必再多一层悬停。']
    }
  };

  function fileOf(a) {
    var declared = a && a.getAttribute ? (a.getAttribute('data-nav-file') || '') : '';
    if (declared) return declared.toLowerCase();
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

  /* OIP W1 §1 nav regroup, extended to this JS mega-menu (adversarial review B1):
     enhanceMarketMenus below replaces the ENTIRE United States .nav-dd-menu, so
     the server-rendered Options & Flow flyout (_navlinks.html.j2) never reaches
     a JS-enabled user unless this table is regrouped to match. Two of its rows
     (Intraday Flow Tracker, Dark Pool Desk) are conditionally rendered server-
     side ({% if intraday_flow_enabled/darkpool_enabled is not defined or ... %})
     — an item's OPTIONAL 8th element names the href its row requires to already
     exist in the source dd's pre-replacement DOM (the same source of truth
     intlCountryHref reads from, just scoped to presence rather than an href
     value); absent that href, the flag was false for this page and the row is
     skipped here too. Items with no 8th element are unconditional and always
     render — matching every unguarded row in the template. */
  function hrefPresent(scope, file) {
    return !!(scope && scope.querySelector && scope.querySelector('a[href$="' + file + '"]'));
  }

  function marketMarkup(key, prefix, sourceScope) {
    var data = MARKET_MENU[key], main = '', rail = '', total = 0;
    if (!data) return '';
    for (var i = 0; i < data.sections.length; i++) {
      var section = data.sections[i], items = '';
      for (var j = 0; j < section[1].length; j++) {
        var item = section[1][j];
        if (item[7] && !hrefPresent(sourceScope, item[7])) continue;
        items += destinationMarkup(item, prefix, false);
        total++;
      }
      main += '<section class="mega-section nav-market-section"><div class="section-label nav-market-heading">' +
        langText(section[0], section[2]) + '</div><div class="item-grid nav-market-grid">' + items + '</div></section>';
    }
    for (var k = 0; k < data.rail.length; k++) rail += destinationMarkup(data.rail[k], prefix, true);
    if (data.note) {
      var noteZh = data.noteZh || [];
      rail += '<div class="rail-note nav-market-note"><strong>' + langText(data.note[0], noteZh[0]) +
        '</strong><span>' + langText(data.note[1], noteZh[1]) + '</span></div>';
    }
    return '<div class="mega-main nav-market-main"><header class="menu-intro nav-market-intro">' +
      '<div><h2 class="nav-market-name">' + langText(data.title, data.titleZh) + '</h2>' +
      '<p class="nav-market-subtitle">' + langText(data.subtitle, data.subtitleZh) + '</p></div>' +
      '<span class="menu-count nav-market-count">' +
      langText(total + ' destinations', total + ' 个入口') + '</span></header>' + main + '</div>' +
      '<aside class="mega-rail nav-market-rail"><div class="section-label nav-market-heading">' +
      langText(data.railTitle || 'Explore', data.railTitleZh || '探索') +
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
      // marketMarkup's item[7] gate reads conditional-row presence from `menu`
      // — this argument is evaluated (and hrefPresent's queries run) BEFORE
      // the assignment below replaces menu's own content, so it still sees
      // the server-rendered source DOM, never its own freshly-built markup.
      menu.innerHTML = marketMarkup(key, prefixOf(dd), menu);
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
  function ensureEarningsWireCard(menu) {
    // The shared runtime can reach production before every page is re-rendered.
    // Keep older Research menus useful until their static navigation catches up.
    if (menu.querySelector('[data-nav-file="earnings_wire"]')) return;

    var main = menu.querySelector(':scope > .nav-mega-main');
    if (!main) return;
    var sections = main.querySelectorAll(':scope > .nav-mega-section');
    var grid = null;
    for (var i = 0; i < sections.length; i++) {
      var heading = sections[i].querySelector(':scope > .nav-mega-h');
      if (!heading || !/(?:Core Research|核心研究)/.test(heading.textContent || '')) continue;
      grid = sections[i].querySelector(':scope > .nav-mega-item-grid');
      if (grid) break;
    }
    if (!grid) return;

    var dropdown = menu.closest ? menu.closest('.nav-dd') : null;
    var item = document.createElement('a');
    item.className = 'mega-item nm-feat';
    item.setAttribute('data-nav-file', 'earnings_wire');
    item.href = (dropdown ? prefixOf(dropdown) : '') + 'stocks/earnings/index.html';
    item.innerHTML = '<span class="icon-drawing nm-ic cyan" aria-hidden="true"><svg viewBox="0 0 48 48">' +
      MOCKUP_ICON_PATHS.earnings_wire +
      '</svg></span><span class="nm-tx"><span class="item-title nm-t"><span class="l-en">Earnings Wire</span><span class="l-zh">财报情报线</span></span>' +
      '<span class="item-desc d"><span class="l-en">Verified calls, weekly intelligence and company context</span>' +
      '<span class="l-zh">已核验电话会、每周情报与公司语境</span></span></span>';

    var next = null;
    var cards = grid.querySelectorAll(':scope > a');
    for (var j = 0; j < cards.length; j++) {
      if (fileOf(cards[j]) === 'fundamental_forensics.html') {
        next = cards[j];
        break;
      }
    }
    grid.insertBefore(item, next);
  }

  function enhanceResearchMenu(links) {
    var menu = links && links.querySelector('.nav-dd-menu.nav-mega');
    if (!menu) return;
    ensureEarningsWireCard(menu);
    if (menu.getAttribute('data-mockup-exact') === '1') return;
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
      var iconSpec = MOCKUP_RESEARCH_ICON_BY_FILE[file];
      var exactDescription = MOCKUP_RESEARCH_DESCRIPTION_BY_FILE[file];
      var englishDescription = desc && desc.querySelector('.l-en');
      if (exactDescription && englishDescription) {
        englishDescription.textContent = exactDescription;
      }
      /* Cards this bridge does not know KEEP their server-rendered icon.
         The old fallback substituted the default dashboard spec for every
         unknown card, stomping each one with the same identical glyph —
         measured live 2026-08-07: the adjacent Mastermind Portfolio and
         Mastermind Bot cards (plus Filing Forensics and Stock Seasonality)
         all rendered the same dashboard square, and the two Mastermind cards
         read as one product listed twice. Every card added since the mockup
         era already ships its real icon-drawing markup server-side, so
         leaving it alone IS the exact normalisation; only files named in the
         map are legacy shapes this bridge exists to rewrite. */
      var oldIcon = iconSpec ? item.querySelector('.nm-ic') : null;
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
      // The label may arrive as an older page's `.nm-t`, or as the current
      // template's bare bilingual <span>. Take whichever exists and keep its
      // markup: the previous hardcoded 'Global Cycles' fallback fired on every
      // current page (they have no .nm-t here) and replaced the l-en/l-zh pair
      // with one English string, so this row shipped English in Chinese mode.
      var drillTitle = drillTrigger.querySelector('.nm-t') ||
        drillTrigger.querySelector(':scope > span:not(.nav-drill-arrow):not(.rail-arrow)');
      drillTrigger.classList.add('rail-link');
      drillTrigger.innerHTML = '<span>' + (drillTitle ? drillTitle.innerHTML :
        '<span class="l-en">Global Cycles</span><span class="l-zh">全球周期</span>') +
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

  /* ---- Panel choreography -------------------------------------------------
     Every wide panel lands on the SAME rect and differs only in height (780px
     for the United States and China maps, 690-694px for the rest), so a switch
     between two triggers needs no shared wrapper element: pinning the outgoing
     AND the incoming panel to one animated height makes their chromes
     pixel-identical for the crossing, and the pair reads as a single plate
     that morphs while the contents cross-fade. Before this, a switch removed
     the outgoing panel in the same frame the incoming one started at opacity
     zero — one blank frame, then a slow re-entrance. That was the flicker.

     Timings live in navigation-refresh.css and are read back from there, so
     the stylesheet stays the single source of truth for the motion. */
  var SWAP_DEFAULTS = { '--nav-close': 110, '--nav-morph': 170 };

  function navRootOf(el) {
    return (el && el.closest) ? el.closest('.site-nav, .topbar') : null;
  }

  function motionMs(root, name) {
    var raw = root ? getComputedStyle(root).getPropertyValue(name).trim() : '';
    var n = parseFloat(raw);
    if (!isFinite(n) || n <= 0) return SWAP_DEFAULTS[name] || 0;
    return /ms$/.test(raw) ? n : n * 1000;
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  // Natural height of a panel that is currently display:none. Measured once per
  // (viewport width, language) pair — both change the panel's content box — and
  // cached on the node, so a traverse costs no repeated reflow.
  function naturalHeight(menu) {
    var key = window.innerWidth + '|' + (document.documentElement.getAttribute('data-lang') || 'en');
    if (menu._navHKey === key && menu._navH) return menu._navH;
    var prev = menu.getAttribute('style');
    menu.style.display = 'grid';
    menu.style.visibility = 'hidden';
    menu.style.height = 'auto';
    menu.style.animation = 'none';
    menu.style.transition = 'none';
    var h = menu.offsetHeight;
    if (prev === null) menu.removeAttribute('style'); else menu.setAttribute('style', prev);
    // Commit the restored hidden state before the caller applies the swap
    // classes. Without this flush the last style the engine saw for this panel
    // is the measurement's display:grid, so the cross-fade's opacity:0 start
    // reads as a transition TARGET rather than a start value and the incoming
    // contents never fade in — they sit at 1 for the whole crossing.
    void menu.offsetHeight;
    menu._navHKey = key;
    menu._navH = h;
    return h;
  }

  // One rail owns one open panel at a time. Shared across every .nav-dd so a
  // switch can see both sides of the crossing.
  function choreographer(links) {
    var root = navRootOf(links) || links;
    var activeDd = null;
    var swapTimer = 0;

    function menuOf(dd) { return dd.querySelector(':scope > .nav-dd-menu'); }

    function order(dd) {
      var sibs = links.querySelectorAll(':scope > .nav-dd');
      for (var i = 0; i < sibs.length; i++) if (sibs[i] === dd) return i;
      return -1;
    }

    // Drop every transient class and let the surviving panel own its own chrome
    // again. Runs at the end of a swap, and defensively before a new one.
    function settle() {
      window.clearTimeout(swapTimer);
      swapTimer = 0;
      root.style.removeProperty('--nav-plate-h');
      links.querySelectorAll('.nav-panel-in, .nav-panel-out').forEach(function (m) {
        var leaving = m.classList.contains('nav-panel-out');
        m.classList.remove('nav-panel-in', 'nav-panel-out', 'nav-panel-live');
        var owner = m.parentElement;
        if (leaving && owner && owner !== activeDd) {
          owner.classList.remove('nav-hover-open');
          m.classList.remove('nav-panel-swapped');
        }
      });
    }

    // Cancel an exit that is mid-fade (the pointer came back). The timer is
    // held ON THE PANEL, not in one shared slot: with a single slot, closing a
    // second menu would clear the first one's pending cleanup and strand it at
    // display:grid — an invisible panel that still contributes its scroll
    // width, exactly the failure the closed-state rules above guard against.
    function cancelClose(menu) {
      if (!menu) return;
      if (menu._navCloseTimer) {
        window.clearTimeout(menu._navCloseTimer);
        menu._navCloseTimer = 0;
      }
      menu.classList.remove('nav-panel-closing', 'nav-panel-live');
    }

    function hardOpen(dd) {
      links.querySelectorAll(':scope > .nav-dd.nav-hover-open').forEach(function (other) {
        if (other !== dd) other.classList.remove('nav-hover-open');
      });
      var menu = menuOf(dd);
      if (menu) menu.classList.remove('nav-panel-swapped');
      dd.classList.add('nav-hover-open');
    }

    // The Attio-style crossing: lock both panels to one height, walk that height
    // to the incoming panel's natural size, and cross-fade the contents with a
    // drift that follows the pointer's travel direction.
    function crossFade(fromDd, toDd) {
      var out = menuOf(fromDd);
      var incoming = menuOf(toDd);
      if (!out || !incoming) return false;

      var from = Math.round(out.getBoundingClientRect().height);
      var to = naturalHeight(incoming);
      if (!from || !to) return false;

      settle();
      // +1 travelling right along the rail. Both panels then drift LEFT: the
      // incoming enters from the right, the outgoing leaves to the left.
      var dir = order(toDd) > order(fromDd) ? 1 : -1;
      root.style.setProperty('--nav-plate-h', from + 'px');
      root.style.setProperty('--nav-drift', (dir * 10) + 'px');
      out.classList.add('nav-panel-out', 'nav-panel-swapped');
      incoming.classList.add('nav-panel-in', 'nav-panel-swapped');
      toDd.classList.add('nav-hover-open');

      // Flush the start state before flipping to the target, or the browser
      // coalesces both into one frame and nothing animates.
      void incoming.offsetWidth;
      root.style.setProperty('--nav-plate-h', to + 'px');
      out.classList.add('nav-panel-live');
      incoming.classList.add('nav-panel-live');
      swapTimer = window.setTimeout(settle, motionMs(root, '--nav-morph'));
      return true;
    }

    return {
      open: function (dd) {
        var menu = menuOf(dd);
        cancelClose(menu);
        var previous = activeDd;
        activeDd = dd;
        if (previous === dd) { dd.classList.add('nav-hover-open'); return; }
        var wide = menu && menu.classList.contains('mega-menu');
        var previousWide = previous && previous.isConnected &&
          previous.parentElement === links &&
          previous.classList.contains('nav-hover-open') &&
          menuOf(previous) && menuOf(previous).classList.contains('mega-menu');
        if (wide && previousWide && !prefersReducedMotion() && crossFade(previous, dd)) return;
        settle();
        hardOpen(dd);
      },

      close: function (dd) {
        if (activeDd === dd) activeDd = null;
        var menu = menuOf(dd);
        if (!menu || !dd.classList.contains('nav-hover-open') ||
            !menu.classList.contains('mega-menu') || prefersReducedMotion()) {
          dd.classList.remove('nav-hover-open');
          if (menu) menu.classList.remove('nav-panel-swapped');
          return;
        }
        // display:none cannot transition, so hold the panel rendered for the
        // length of the exit and let CSS fade it.
        cancelClose(menu);
        menu.classList.add('nav-panel-closing');
        dd.classList.remove('nav-hover-open');
        void menu.offsetWidth;
        menu.classList.add('nav-panel-live');
        menu._navCloseTimer = window.setTimeout(function () {
          menu.classList.remove('nav-panel-closing', 'nav-panel-live', 'nav-panel-swapped');
          menu._navCloseTimer = 0;
        }, motionMs(root, '--nav-close'));
      },

      abort: function (dd) {
        if (activeDd === dd) activeDd = null;
        var menu = menuOf(dd);
        cancelClose(menu);
        settle();
        dd.classList.remove('nav-hover-open');
        if (menu) menu.classList.remove('nav-panel-swapped');
      }
    };
  }

  // Wide desktop menus are anchored to the full navigation rail so they can
  // stay viewport-safe. That leaves the intentional visual air gap below the
  // trigger outside the CSS :hover tree. Keep the current menu alive briefly
  // while a fine pointer crosses the gap, then close it only if neither the
  // trigger/menu nor keyboard focus was reached. Touch/mobile keeps its
  // existing click accordion and never enters this path.
  function bindHoverSafeDropdowns(links) {
    var fineHover = window.matchMedia('(hover: hover) and (pointer: fine)');
    var stage = choreographer(links);
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
        stage.open(dd);
        // Publish AFTER opening: a display:none panel reports a zero rect, so
        // the gap can only be measured once the panel is actually rendered.
        measureGap();
      }

      // The air gap between the trigger row and the panel. Doubles as the
      // invisible bridge's vertical reach, published to CSS so the hover-safe
      // zone is the real gap and can never overhang a control in a layout
      // whose geometry differs. Clamped so a bad measurement stays harmless.
      function measureGap() {
        var triggerRect = trigger.getBoundingClientRect();
        var menuRect = menu.getBoundingClientRect();
        if (!menuRect.height) return 0;
        var gap = Math.round(Math.max(0, menuRect.top - triggerRect.bottom));
        var root = navRootOf(links);
        if (root) root.style.setProperty('--nav-bridge', Math.min(24, gap) + 'px');
        return gap;
      }

      function hoverGraceMs() {
        var gap = measureGap();
        return Math.min(1000, Math.max(420, 360 + Math.round(gap * 8)));
      }

      function closeMenuSoon() {
        window.clearTimeout(closeTimer);
        closeTimer = window.setTimeout(function () {
          if (!dd.matches(':hover') && !dd.contains(document.activeElement)) {
            stage.close(dd);
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
        stage.abort(dd);
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
        // Same yield as theme.js initMobileNav: a folded country's trigger is a
        // drill, owned by the delegated [data-nav-drill-open] handler on
        // `document`. stopPropagation() here would strand it closed on mobile.
        if (trigger.hasAttribute('data-nav-drill-open')) return;
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

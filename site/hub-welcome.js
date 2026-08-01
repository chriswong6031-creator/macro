/* hub-welcome.js — the signed-in hub's opening moment.
 *
 * A name greeting, then a short spoken-aloud read of TODAY's markets in the voice of a
 * calm senior strategist: observant, direct, and never theatrical. A few remarks land
 * with natural pauses, then the intelligence surface dissolves into the MASTERMIND brand.
 *
 * No LLM. Every remark is assembled from the engine data already on the page
 * (#globe-data: per-region regime quadrant, index direction, risk read, breadth — plus
 * the newest "What changed" alert and the Bitcoin Vector chip) and light per-visit
 * memory. One idea has many phrasings; topics are mood-gated to the real tape; nothing
 * repeats within a day; repeat visits are recalled and get shorter, fresher reads.
 *
 * It also knows what day it is:
 *  • WEEKENDS (viewer's local clock) — markets are closed, so the desk stops pretending
 *    the tape is live: Friday's close is read AS Friday's close, the only open market
 *    (crypto) gets its beat, and the nudge is about rest, sun, and next week's plan.
 *  • HOLIDAYS — the viewer's country is guessed from their timezone (refined by
 *    navigator.language); each country carries its own holiday table (fixed dates,
 *    nth-weekday rules, Easter computus, and lunar lookup tables for 2026–28). A holiday
 *    greeting fires ONCE per occurrence (localStorage mm.hub.hols) — never nagged twice.
 *
 * The viewer's HOME market drives the tape/mood/regime beats: a Shanghai visitor hears
 * about the A-share board, not the S&P. Chinese copy is written natively (红涨绿跌 —
 * in zh, red means up; 端午安康, not 端午快乐; no "happy" Qingming), not translated.
 *
 * Test seam: localStorage.setItem('mm.hub.fakeNow','2026-12-25T10:00') pins the clock
 * for manual verification of weekend/holiday paths. Dev-only; absent in normal use.
 */
(function () {
  var hdr = document.querySelector('header.h'); if (!hdr) return;
  var greet = hdr.querySelector('.hub-greet'); if (!greet) return;
  var tx = greet.querySelector('.greet-tx'); if (!tx) return;
  if (window.__hubWelcomeInit) return;
  window.__hubWelcomeInit = true;

  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function reduced() { try { return window.matchMedia && matchMedia('(prefers-reduced-motion:reduce)').matches; } catch (e) { return false; } }

  /* ---- viewer's first name (from the session cookie; no network) ---------- */
  function sessUser() {
    try {
      var m = {}, P = (document.cookie || '').split(';'), i;
      for (i = 0; i < P.length; i++) { var p = P[i].trim(), e = p.indexOf('='); if (e > 0) m[p.slice(0, e)] = p.slice(e + 1); }
      var K = null, k; for (k in m) { if (/^sb-.*-auth-token(\.\d+)?$/.test(k)) { K = k.replace(/\.\d+$/, ''); break; } }
      if (!K) return null;
      var r = m[K], j = r;
      if (r == null) { var v = [], n = 0, c; while ((c = m[K + '.' + n]) != null) { v.push(c); n++; } j = v.length ? v.join('') : null; }
      if (j == null) return null;
      var B = 'base64-';
      if (j.indexOf(B) === 0) { var b = j.slice(B.length).replace(/-/g, '+').replace(/_/g, '/'); while (b.length % 4) b += '='; j = decodeURIComponent(escape(atob(b))); }
      var s = JSON.parse(j); return (s && s.user) || null;
    } catch (e) { return null; }
  }
  var u = sessUser(); if (!u) { try { u = window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user(); } catch (e) {} }
  var md = (u && u.user_metadata) || {};
  var name = (md.first_name || md.display_name || md.name || md.full_name || '').toString().trim();
  if (!name && u && u.email) name = String(u.email).split('@')[0];
  name = name.replace(/[<>]/g, '').slice(0, 24);
  if (name && name === name.toLowerCase()) name = name.charAt(0).toUpperCase() + name.slice(1);

  /* ---- the clock (with a dev seam so holiday/weekend paths are testable) --- */
  var d0 = new Date();
  try { var fk = localStorage.getItem('mm.hub.fakeNow'); if (fk) { var fkd = new Date(fk); if (!isNaN(fkd)) d0 = fkd; } } catch (e) {}
  var dow = d0.getDay(), wknd = (dow === 0 || dow === 6);

  /* ---- ever-signed-in-before? (greeting flavour) + visits today (recall) --- */
  var everKey = 'mm.hub.welcomed', firstEver = false;
  try { firstEver = !localStorage.getItem(everKey); localStorage.setItem(everKey, '1'); } catch (e) {}
  var today = d0.getFullYear() + '-' + (d0.getMonth() + 1) + '-' + d0.getDate();
  var MEM; try { MEM = JSON.parse(localStorage.getItem('mm.hub.convo') || 'null'); } catch (e) {}
  if (!MEM || MEM.day !== today) MEM = { day: today, visits: 0, seen: [], mids: [], lastSeen: 0 };
  if (!MEM.mids) MEM.mids = [];
  // A "visit" is a genuine RETURN, not a page refresh. Opening and closing the tab three
  // times in a minute is ONE visit playing with the door — count it once. Only a real gap of
  // time (you went and did something, then came back) makes it a new visit; anything sooner is
  // a reload, and we recognise it AS one instead of pretending you just walked back in.
  var SESSION_GAP = 25 * 60 * 1000, nowMs = Date.now();
  var reload = !!(MEM.lastSeen && (nowMs - MEM.lastSeen) < SESSION_GAP);
  if (!reload) MEM.visits += 1;
  MEM.lastSeen = nowMs;
  var visit = MEM.visits;
  function fresh(id) { return MEM.seen.indexOf(id) < 0; }
  function keep(id) { if (MEM.seen.indexOf(id) < 0) MEM.seen.push(id); }
  function save() { try { localStorage.setItem('mm.hub.convo', JSON.stringify(MEM)); } catch (e) {} }

  /* ---- where is the viewer? tz → country (refined by navigator.language) ---
   * Best-effort only, and it degrades to nothing: an unknown place gets no holiday
   * beat and the US board as its home read — never a wrong-country greeting. */
  function guessCC() {
    var tz = '', lg = '';
    try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) {}
    try { lg = (navigator.language || '').toLowerCase(); } catch (e) {}
    if (/Shanghai|Chongqing|Urumqi|Harbin|Kashgar|Chungking|Beijing/.test(tz)) return 'CN';
    if (/Hong_Kong|Macau/.test(tz)) return 'HK';
    if (/Taipei/.test(tz)) return 'TW';
    if (/Tokyo/.test(tz)) return 'JP';
    if (/Seoul/.test(tz)) return 'KR';
    if (/Singapore/.test(tz)) return 'SG';
    if (/Kolkata|Calcutta/.test(tz)) return 'IN';
    if (/^Australia\//.test(tz)) return 'AU';
    if (/Auckland|Chatham/.test(tz)) return 'NZ';
    if (/London/.test(tz)) return 'GB';
    if (/Dublin/.test(tz)) return 'IE';
    if (/Paris/.test(tz)) return 'FR';
    if (/Berlin|Busingen|Vienna|Zurich/.test(tz)) return 'DE';
    if (/Toronto|Montreal|Vancouver|Edmonton|Winnipeg|Halifax|Regina|St_Johns|Moncton|Yellowknife|Whitehorse|Iqaluit/.test(tz)) return 'CA';
    if (/Honolulu/.test(tz)) return 'US';
    if (/^America\//.test(tz)) {
      if (/-ca\b/.test(lg)) return 'CA';
      if (/New_York|Chicago|Denver|Los_Angeles|Phoenix|Detroit|Anchorage|Boise|Indiana|Kentucky|Juneau|Sitka|Menominee|North_Dakota|Metlakatla|Adak/.test(tz)) return 'US';
      return null;                       // rest of the Americas: no holiday table, US board
    }
    if (/^Europe\//.test(tz)) return 'EU';   // generic EU: Jan 1 / May 1 / Christmas only
    if (/^zh\b/.test(lg)) return /-tw/.test(lg) ? 'TW' : /-hk|-mo/.test(lg) ? 'HK' : 'CN';
    return null;
  }
  var CC = guessCC();

  /* ---- the holiday calendar -----------------------------------------------
   * Rules: [m,d] fixed · {w:[m,weekday,n]} nth weekday (n:-1 = last) · {e:days}
   * offset from Easter Sunday (Gregorian computus) · {t:{year:'MM-DD'}} lookup for
   * lunar/observed dates (2026–28 baked in; an absent year = no greeting, never a
   * wrong one). Greetings are written once per holiday, market-closure phrased in. */
  function easterMD(y) {
    var a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4,
        f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30,
        i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7,
        m = Math.floor((a + 11 * h + 22 * l) / 451), mo = Math.floor((h + l - 7 * m + 114) / 31);
    return [mo, ((h + l - 7 * m + 114) % 31) + 1];
  }
  function nthDow(y, m, wd, n) {
    if (n > 0) { var f = new Date(y, m - 1, 1).getDay(); return 1 + ((wd - f + 7) % 7) + (n - 1) * 7; }
    var last = new Date(y, m, 0); return last.getDate() - ((last.getDay() - wd + 7) % 7);
  }
  function ruleMD(rule, y) {
    if (rule.length) return [rule[0], rule[1]];
    if (rule.w) return [rule.w[0], nthDow(y, rule.w[0], rule.w[1], rule.w[2])];
    if (rule.e != null) { var em = easterMD(y), dt = new Date(y, em[0] - 1, em[1] + rule.e); return [dt.getMonth() + 1, dt.getDate()]; }
    if (rule.t) { var s = rule.t[y]; if (!s) return null; var p = s.split('-'); return [+p[0], +p[1]]; }
    return null;
  }
  var HOL = {
    newyear:      [[1, 1], "New Year's Day. Markets are closed; start the year with a clear head.", '元旦休市。新的一年，先把节奏稳下来。'],
    christmas:    [[12, 25], "Merry Christmas. Markets are closed; leave them closed for the day.", '圣诞快乐。今天休市，好好过节。'],
    boxing:       [[12, 26], 'Boxing Day. Markets remain closed, and there is nothing you need to do.', '今天是节礼日，市场继续休市。'],
    goodfri:      [{ e: -2 }, 'Good Friday. Markets are closed for the long weekend.', '耶稣受难日，市场休市，长周末开始了。'],
    eastermon:    [{ e: 1 }, 'Easter Monday. Markets are still closed.', '复活节星期一，市场继续休市。'],
    may1:         [[5, 1], 'May Day. Markets are closed; take the day properly.', '五一假期，市场休市。先放下盘面，好好休息。'],
    cnyeve:       [{ t: { 2026: '2-16', 2027: '2-5', 2028: '1-25' } }, "Lunar New Year's Eve. The market can wait; dinner cannot.", '除夕了。今晚先吃好团圆饭，行情留到年后。'],
    cny:          [{ t: { 2026: '2-17', 2027: '2-6', 2028: '1-26' } }, 'Happy Lunar New Year. Markets are closed; a new trading year can begin later.', '新年好，祝新的一年顺顺利利。今天休市，先好好过年。'],
    qingming:     [{ t: { 2026: '4-5', 2027: '4-5', 2028: '4-4' } }, 'The market is closed for Qingming today.', '清明假期，市场休市。'],
    duanwu:       [{ t: { 2026: '6-19', 2027: '6-9', 2028: '5-28' } }, 'Dragon Boat Festival. Markets are closed today.', '端午安康。今天休市，记得吃粽子。'],
    zhongqiu:     [{ t: { 2026: '9-25', 2027: '9-15', 2028: '10-3' } }, 'Mid-Autumn Festival. Markets are closed; make time for family.', '中秋快乐。今天休市，陪家人吃顿饭。'],
    guoqing:      [[10, 1], 'National Day. Markets are closed for the holiday.', '国庆假期开始了，市场休市。好好放松。'],
    mlk:          [{ w: [1, 1, 3] }, 'MLK Day. US markets are closed.', '今天是马丁·路德·金纪念日，美股休市。'],
    presidents:   [{ w: [2, 1, 3] }, "Presidents' Day. US markets are closed.", '今天是总统日，美股休市。'],
    memorial:     [{ w: [5, 1, -1] }, 'Memorial Day. US markets are closed for the long weekend.', '今天是阵亡将士纪念日，美股休市。'],
    juneteenth:   [[6, 19], 'Juneteenth. US markets are closed today.', '今天是六月节，美股休市。'],
    july4:        [[7, 4], 'Independence Day. US markets are closed.', '今天是美国独立日，美股休市。'],
    labor:        [{ w: [9, 1, 1] }, 'Labor Day. US markets are closed.', '今天是美国劳动节，美股休市。'],
    thanksgiving: [{ w: [11, 4, 4] }, 'Thanksgiving. US markets are closed; family gets the day.', '感恩节快乐。美股休市，今天多陪陪家人。'],
    familyday:    [{ w: [2, 1, 3] }, 'Family Day. Canadian markets are closed.', '今天是加拿大家庭日，多伦多市场休市。'],
    victoria:     [{ t: { 2026: '5-18', 2027: '5-24', 2028: '5-22' } }, 'Victoria Day. Canadian markets are closed for the long weekend.', '今天是维多利亚日，加拿大市场休市。'],
    canadaday:    [[7, 1], 'Canada Day. Markets are closed.', '今天是加拿大国庆日，市场休市。'],
    civic:        [{ w: [8, 1, 1] }, "Toronto is closed for the civic holiday.", '今天是公民假日，多伦多市场休市。'],
    labourca:     [{ w: [9, 1, 1] }, 'Labour Day. Canadian markets are closed.', '今天是加拿大劳动节，市场休市。'],
    thanksca:     [{ w: [10, 1, 2] }, 'Canadian Thanksgiving. Markets are closed today.', '今天是加拿大感恩节，市场休市。'],
    mayday:       [{ w: [5, 1, 1] }, 'The early May bank holiday. London is closed.', '五月初银行假日，伦敦市场休市。'],
    springbank:   [{ w: [5, 1, -1] }, 'The spring bank holiday. London is closed today.', '春季银行假日，伦敦市场休市。'],
    summerbank:   [{ w: [8, 1, -1] }, 'The summer bank holiday. London is closed.', '夏季银行假日，伦敦市场休市。'],
    australiaday: [[1, 26], 'Australia Day. The ASX is closed.', '今天是澳大利亚国庆日，澳股休市。'],
    anzac:        [[4, 25], 'Anzac Day. Australian markets are closed.', '今天是澳新军团日，澳洲市场休市。'],
    waitangi:     [[2, 6], 'Waitangi Day. New Zealand markets are closed.', '今天是怀唐伊日，新西兰市场休市。'],
    stpatrick:    [[3, 17], "St Patrick's Day. Dublin is closed.", '今天是圣帕特里克节，都柏林市场休市。'],
    hksar:        [[7, 1], 'HKSAR Establishment Day. Hong Kong markets are closed.', '今天是香港回归纪念日，港股休市。'],
    t228:         [[2, 28], 'Peace Memorial Day. Taiwan markets are closed.', '今天是和平纪念日，台股休市。'],
    childtomb:    [[4, 4], "The Children's Day and Qingming break. Taiwan markets are closed.", '儿童节、清明连假，台股休市。'],
    double10:     [[10, 10], 'Double Tenth Day. Taiwan markets are closed.', '今天是双十节，台股休市。'],
    goldenweek:   [[5, 3], 'Golden Week. Tokyo is closed.', '日本黄金周，东京市场休市。'],
    liberation:   [[8, 15], 'Liberation Day. The KOSPI is closed.', '今天是韩国光复节，韩国股市休市。'],
    sgnational:   [[8, 9], 'Singapore National Day. Markets are closed.', '今天是新加坡国庆日，市场休市。'],
    republic:     [[1, 26], 'Republic Day. Indian markets are closed.', '今天是印度共和国日，市场休市。'],
    indep:        [[8, 15], 'Independence Day. Indian markets are closed.', '今天是印度独立日，市场休市。'],
    gandhi:       [[10, 2], 'Gandhi Jayanti. Indian markets are closed.', '今天是甘地诞辰纪念日，印度市场休市。'],
    diwali:       [{ t: { 2026: '11-8', 2027: '10-29' } }, 'Happy Diwali. May the year ahead be a steady one.', '排灯节快乐，祝新的一年平安顺遂。'],
    unity:        [[10, 3], 'German Unity Day. Frankfurt is closed.', '今天是德国统一日，法兰克福市场休市。'],
    bastille:     [[7, 14], 'Bastille Day. Paris is closed.', '今天是法国国庆日，巴黎市场休市。']
  };
  var HOLCC = {
    US: ['newyear', 'mlk', 'presidents', 'goodfri', 'memorial', 'juneteenth', 'july4', 'labor', 'thanksgiving', 'christmas'],
    CA: ['newyear', 'familyday', 'goodfri', 'victoria', 'canadaday', 'civic', 'labourca', 'thanksca', 'christmas', 'boxing'],
    GB: ['newyear', 'goodfri', 'eastermon', 'mayday', 'springbank', 'summerbank', 'christmas', 'boxing'],
    IE: ['newyear', 'stpatrick', 'eastermon', 'christmas', 'boxing'],
    AU: ['newyear', 'australiaday', 'goodfri', 'anzac', 'christmas', 'boxing'],
    NZ: ['newyear', 'waitangi', 'goodfri', 'anzac', 'christmas', 'boxing'],
    CN: ['newyear', 'cnyeve', 'cny', 'qingming', 'may1', 'duanwu', 'zhongqiu', 'guoqing'],
    HK: ['newyear', 'cnyeve', 'cny', 'qingming', 'goodfri', 'may1', 'duanwu', 'hksar', 'zhongqiu', 'guoqing', 'christmas'],
    TW: ['newyear', 'cnyeve', 'cny', 't228', 'childtomb', 'duanwu', 'zhongqiu', 'double10'],
    JP: ['newyear', 'goldenweek'],
    KR: ['newyear', 'cny', 'liberation', 'zhongqiu', 'christmas'],
    SG: ['newyear', 'cny', 'goodfri', 'may1', 'sgnational', 'christmas'],
    IN: ['republic', 'indep', 'gandhi', 'diwali'],
    DE: ['newyear', 'may1', 'unity', 'christmas', 'boxing'],
    FR: ['newyear', 'may1', 'bastille', 'christmas'],
    EU: ['newyear', 'may1', 'christmas'],
    '*': ['newyear']                       // unknown country: only the near-universal one
  };
  function holidayToday() {
    var y = d0.getFullYear(), m = d0.getMonth() + 1, dd = d0.getDate();
    var L = HOLCC[CC] || HOLCC['*'];
    for (var i = 0; i < L.length; i++) {
      var h = HOL[L[i]]; if (!h) continue;
      var md2 = ruleMD(h[0], y);
      if (md2 && md2[0] === m && md2[1] === dd) return { id: L[i], en: h[1], zh: h[2], y: y };
    }
    return null;
  }
  // Each holiday greets ONCE per occurrence — a greeting repeated all day stops being a
  // greeting and starts being a nag. Marked seen only when actually spoken (see assembly).
  function holMarkOnce(hol) {
    var key = hol.id + '@' + hol.y, arr;
    try { arr = JSON.parse(localStorage.getItem('mm.hub.hols') || '[]'); } catch (e) { arr = []; }
    if (!Array.isArray(arr)) arr = [];
    if (arr.indexOf(key) >= 0) return false;
    arr.push(key); while (arr.length > 16) arr.shift();
    try { localStorage.setItem('mm.hub.hols', JSON.stringify(arr)); } catch (e) {}
    return true;
  }
  var HOLIDAY = holidayToday();
  var closedDay = wknd || !!HOLIDAY;       // a matched holiday closes the viewer's home market

  /* ---- today's market context, read straight off #globe-data --------------
   * The HOME board (by the viewer's country) drives direction, mood and the regime
   * beats — a Shanghai visitor's "the market" is the A-share board, not the S&P.
   * Breadth, movers and cross-region color stay global. */
  var CC2BOARD = { CN: 'CN', HK: 'HK', TW: 'TW', JP: 'JP', KR: 'KR', CA: 'CA', GB: 'GB', IE: 'EZ', FR: 'EZ', DE: 'EZ', EU: 'EZ', US: 'US' };
  function ctx() {
    var el = document.getElementById('globe-data'); if (!el) return null;
    var d; try { d = JSON.parse(el.textContent); } catch (e) { return null; }
    if (!Array.isArray(d) || !d.length) return null;
    var by = {}; d.forEach(function (m) { by[m.cc] = m; });
    var us = by.US || d[0];
    var home = (CC && by[CC2BOARD[CC]]) || us;
    var chg = d.filter(function (m) { return typeof m.index_chg_pct === 'number' && isFinite(m.index_chg_pct); });
    var up = chg.filter(function (m) { return m.index_chg_pct > 0.05; }).length;
    var down = chg.filter(function (m) { return m.index_chg_pct < -0.05; }).length;
    var stag = d.filter(function (m) { return m.quad === 'q3'; });
    var gold = d.filter(function (m) { return m.quad === 'q1'; });
    var mover = chg.slice().sort(function (a, b) { return Math.abs(b.index_chg_pct) - Math.abs(a.index_chg_pct); })[0] || us;
    var uc = (home && home.index_chg_pct) || 0;
    // NB: the calm q1 risk_text is "calm — low macro stress" — do NOT match bare "stress"
    // (it flagged every calm day risky). Key off the genuinely-elevated words only.
    var risky = /elevat|stagfl|scare|fragile|panic|high —/i.test((home && home.risk_text_en) || '');
    var mood;
    if ((home && home.quad === 'q4') || (risky && uc < -0.8) || down >= chg.length * 0.72) mood = 'off';
    else if ((home && home.quad === 'q3') || risky || uc < -0.4) mood = 'careful';
    else if (home && home.quad === 'q1' && uc > 0.3 && !risky) mood = 'on';
    else if (uc > 0.12 && !risky) mood = 'good';
    else mood = 'mixed';
    return { d: d, us: us, home: home, up: up, down: down, total: chg.length, stag: stag, gold: gold, mover: mover, uc: uc, risky: risky, mood: mood };
  }
  var C = ctx();

  /* ---- extra sources already on the page: newest alert + the Bitcoin chip -- */
  function alertRead() {   // the freshest "What changed" signal, if it's genuinely fresh
    try {
      var it = document.querySelector('#alerts .ha-item'); if (!it) return null;
      var wEl = it.querySelector('.ha-when .l-en');
      var w = (wEl && wEl.textContent || '').trim();
      if (!/^\s*(\d+)\s*h\b|^\s*1\s*d\b/.test(w)) return null;   // ≤1 day old only
      var he = it.querySelector('.ha-head .l-en'), hz = it.querySelector('.ha-head .l-zh');
      var en = (he && he.textContent || '').replace(/\s+/g, ' ').trim();
      var zt = (hz && hz.textContent || '').replace(/\s+/g, ' ').trim() || en;
      if (!en || en.length > 90) return null;
      return [en, zt];
    } catch (e) { return null; }
  }
  function btcRead() {     // 'on' | 'off' | null — crypto is the only open market on a closed day
    try {
      var p = document.querySelector('.card.btc .pill'); if (!p) return null;
      var en = p.querySelector('.l-en');
      var m = /risk\s*(on|off)/i.exec((en && en.textContent) || p.textContent || '');
      return m ? m[1].toLowerCase() : null;
    } catch (e) { return null; }
  }
  var ALERTX = alertRead(), BTC = btcRead();

  /* ---- display slots (filled per-language so both sides read naturally) --- */
  function nm(m, en) { return m ? (en ? (m.name_en || m.cc) : (m.name_zh || m.name_en || m.cc)) : ''; }
  // conversational names (no clunky "United States's"); the region beat prefers a
  // NON-US board — highlighting a foreign divergence reads smarter than the home tape.
  var ALIAS = { US: ['the US', '美国'], CN: ['China', '中国'], HK: ['Hong Kong', '香港'], JP: ['Japan', '日本'], CA: ['Canada', '加拿大'], GB: ['the UK', '英国'], UK: ['the UK', '英国'], EZ: ['Europe', '欧洲'], EU: ['Europe', '欧洲'], IN: ['India', '印度'], KR: ['Korea', '韩国'], TW: ['Taiwan', '台湾'], AU: ['Australia', '澳洲'] };
  function cname(m, en) { if (!m) return ''; var a = ALIAS[m.cc]; return a ? a[en ? 0 : 1] : nm(m, en); }
  function firstNonUS(arr) { for (var i = 0; i < arr.length; i++) if (arr[i].cc !== 'US') return arr[i]; return arr[0]; }
  function regimeName(m, en) { return m ? (en ? (m.quad_name_en || '') : (m.quad_name_zh || m.quad_name_en || '')) : ''; }
  function asof(en) {
    try { var s = C && C.us && C.us.macro_asof; if (!s) return ''; var p = String(s).split('-'); var dt = new Date(+p[0], +p[1] - 1, +p[2]);
      return en ? dt.toLocaleDateString('en', { month: 'short', day: 'numeric' }) : (dt.getMonth() + 1) + '月' + dt.getDate() + '日'; } catch (e) { return ''; }
  }
  // ASOF defaults keep the META lines whole even when #globe-data is absent
  var EN = { V: visit, LASTD: wknd ? 'Friday' : 'The last session', ASOF: 'today' };
  var ZH = { V: visit, LASTD: wknd ? '周五' : '上个交易日', ASOF: '今天' };
  if (ALERTX) { EN.ALERT = ALERTX[0]; ZH.ALERT = ALERTX[1]; }
  if (C) {
    var pct = Math.abs(C.uc).toFixed(1);
    var mpct = Math.abs(C.mover.index_chg_pct || 0).toFixed(1);
    var rd = C.home.rdir;
    var twEn = C.home.rtoward_en || (rd === 'improving' ? 'firmer ground' : 'a worse spot');
    var twZh = C.home.rtoward_zh || (rd === 'improving' ? '更稳的位置' : '更差的位置');
    EN.PCT = pct; EN.DOWN = C.down; EN.UP = C.up; EN.TOTAL = C.total; EN.MOVER = cname(C.mover, 1); EN.MOVERPCT = mpct;
    EN.MOVERDIR = (C.mover.index_chg_pct || 0) >= 0 ? 'up' : 'down';
    EN.STAG = C.stag.length ? cname(firstNonUS(C.stag), 1) : ''; EN.GOLD = C.gold.length ? cname(firstNonUS(C.gold), 1) : '';
    EN.REGIME = regimeName(C.home, 1); EN.TOWARD = twEn; EN.ASOF = asof(1);
    ZH.PCT = pct; ZH.DOWN = C.down; ZH.UP = C.up; ZH.TOTAL = C.total; ZH.MOVER = cname(C.mover, 0); ZH.MOVERPCT = mpct;
    ZH.MOVERDIR = (C.mover.index_chg_pct || 0) >= 0 ? '涨' : '跌';
    ZH.STAG = C.stag.length ? cname(firstNonUS(C.stag), 0) : ''; ZH.GOLD = C.gold.length ? cname(firstNonUS(C.gold), 0) : '';
    ZH.REGIME = regimeName(C.home, 0); ZH.TOWARD = twZh; ZH.ASOF = asof(0);
  }
  function fill(s, map) { return s.replace(/\{(\w+)\}/g, function (_, k) { return map[k] != null ? map[k] : ''; }); }

  /* ---- the material. draw() returns a phrasing not used today, slots filled.
   * The zh side of every pair is WRITTEN, not translated: 红涨绿跌 (in Chinese
   * copy red is up, green is down — the reverse of the EN screens), native trader
   * vernacular, full-width punctuation. Keep it that way when adding lines. */
  function draw(poolId, pool) {
    var cands = [], i;
    for (i = 0; i < pool.length; i++) if (fresh(poolId + i)) cands.push(i);
    if (!cands.length) for (i = 0; i < pool.length; i++) cands.push(i);   // all seen → allow reuse
    var idx = pick(cands); keep(poolId + idx);
    var v = pool[idx];
    return [fill(v[0], EN), fill(v[1], ZH)];
  }

  var dir = C ? (C.uc > 0.12 ? 'up' : C.uc < -0.12 ? 'down' : 'flat') : 'flat';
  var quad = (C && C.home && C.home.quad) || '';

  var OPEN = [
    ["I've done the first pass. Here's what matters.", '盘面我先过了一遍。先看最重要的。'],
    ['Before you start, one clean read on the day.', '开工前，先把今天的主线说清楚。'],
    ['I checked the tape. Start here.', '行情我看过了。先从这里开始。'],
    ['Let me save you a few minutes.', '我先替你筛一遍，省点时间。'],
    ["The broad picture is clear. Here's the useful part.", '大方向很清楚。下面这点最值得看。'],
    ['Start with the signal, not the noise.', '先看信号，别被杂音带走。']
  ];
  // Recall lines fire only on a GENUINE return (a real gap of time). Kept clear, not
  // cryptic — they say what the count means ("look today", "check-ins today").
  var VISIT2 = [
    ["You're back. I'll skip the recap.", '又回来了。前情不重复，直接看现在。'],
    ['Second check today. Straight to the current read.', '今天第二次看盘。直接说当前结论。'],
    ['Another look. I’ll keep it brief.', '再看一眼。这次只说重点。'],
    ['Back at the desk. No need to start from zero.', '又回到台前了。我们不用从头说起。']
  ];
  var VISIT3 = [
    ["{V} checks today. I'll keep this to what still matters.", '今天已经看了 {V} 次。我只说还值得注意的。'],
    ['Another check. No preamble.', '又来看了。省掉开场，直接说结论。'],
    ["You know the picture. Here's where it stands now.", '大方向你已经知道了。现在是这个位置。'],
    ['Back again. One useful line, then the board.', '又回来了。先说一句有用的，再看面板。'],
    ["{V} looks today. I'll be precise.", '今天第 {V} 次看盘。只说重点。']
  ];
  // A page REFRESH (same session) — honest and brief. NOT a "you're back".
  var RELOAD = [
    ['No material change in the last few minutes.', '这几分钟没有实质变化。'],
    ['Same read. I’ll spare you the replay.', '结论没变，就不重复了。'],
    ['Nothing new enough to change the decision.', '暂时没有新变化需要调整判断。'],
    ['The picture is unchanged. The board is ready below.', '盘面没有变化。下面可以直接看。'],
    ['You have the latest read already.', '你刚看到的就是最新结论。'],
    ['No update yet. Better to wait than invent one.', '还没有新情况。没变化，就不硬说。']
  ];
  var TAPE = { up: [
      ['Buyers have control, and the move is orderly. No need to chase it.', '买盘占优，涨势也算稳。可以跟强，但没必要追。'],
      ['The tape is firm and holding. Let strength come to you.', '盘面偏强，承接还在。按计划做，不用加戏。'],
      ['Gains are broad enough to trust, not strong enough to get careless.', '上涨有一定广度，可以参与，但别放松纪律。'],
      ['Good setups are working. Chasing is not.', '走得好的机会可以跟，别急着追。'],
      ['The bid is steady. Keep participating where price confirms the idea.', '买盘稳定。价格确认的方向，可以继续做。'],
      ['A constructive session so far. Stay selective.', '到目前为止盘面偏强，但还是要挑着做。']
    ], down: [
      ["Sellers have control. Nothing is broken, but there is no reason to force an entry.", '卖压占优。还没到失控，但也没必要硬做。'],
      ['The tape is heavy and bids are thin. Let the market prove itself first.', '盘面偏弱，承接也薄。先让市场自己站稳。'],
      ['Weak session. Reduce the number of decisions, not the quality of them.', '行情偏弱。少做几笔，但标准别降。'],
      ['Price is drifting lower without much resistance. Patience is useful here.', '价格缓慢走低，承接不强。这里耐心更值钱。'],
      ['Buyers are not defending much yet. Wait for evidence.', '买方暂时没怎么防守。先等证据。'],
      ['The market is asking for less risk, not a better story.', '市场要你收风险，不是要你找个更好听的理由。']
    ], flat: [
      ['Little directional edge so far. Wait for the market to show its hand.', '方向还没走出来。等市场先表态。'],
      ['The tape is balanced. Selectivity matters more than conviction.', '多空暂时平衡。选对标的，比押方向更重要。'],
      ['Not much is moving with purpose yet. There is no penalty for waiting.', '暂时没有明确主线。等一等，不吃亏。'],
      ['Sideways for now. There is no need to react to every move.', '目前还是横盘。别对每个小波动都做反应。']
    ] };
  /* Weekend / holiday tape: the market is CLOSED, so the last session is read as the
   * last session — never dressed up as a live print. {LASTD} = Friday / last session. */
  var WTAPE = { up: [
      ['{LASTD} closed higher. The market entered the break on firm footing.', '{LASTD}收涨，休市前的状态还算稳。'],
      ['The last session held its gains into the close.', '上个交易日涨幅守到了收盘。'],
      ['Buyers were still present at the close. That is the last confirmed read.', '收盘前买盘仍在。这是最近一次确认过的盘面。']
    ], down: [
      ['{LASTD} closed lower. The weak finish matters when trading resumes, not before.', '{LASTD}收跌。这个弱势要等开市后再处理。'],
      ['The last session was heavy and finished without much recovery.', '上个交易日偏弱，收盘前也没有明显修复。'],
      ['The market entered the break defensively. Keep that context for the reopen.', '休市前盘面偏防守。下次开市时，先记住这一点。']
    ], flat: [
      ['{LASTD} finished flat. No directional signal carried into the break.', '{LASTD}基本收平，没有把明确方向带进休市。'],
      ['The last session ended quietly. The next useful information comes at the reopen.', '上个交易日平静收盘。下一条有用信息，要等开市。']
    ] };
  // Regime beats are DIRECTION-first, never label-first: the same quad means opposite
  // things depending on whether we're firming into it or rolling out of it — and the
  // confirmed label LAGS the score, so a deteriorating "Goldilocks" is the trap. {REGIME}
  // = the HOME board's quad, {TOWARD} = where its trajectory is dragging it.
  var REGD = [   // DETERIORATING — the label still says {REGIME}, but the trend is down
      ["The label still says {REGIME}, but the trend is weakening toward {TOWARD}. Reduce risk before the label catches up.", '标签还是「{REGIME}」，底层趋势却在转弱，正往「{TOWARD}」靠。别等标签改了才收风险。'],
      ['{REGIME} is the last confirmed state, not the current direction. The direction is toward {TOWARD}.', '「{REGIME}」是最近一次确认的状态，不代表当前方向。现在正往「{TOWARD}」走。'],
      ['The backdrop is still {REGIME}; the internals are not. The move toward {TOWARD} matters more.', '大环境仍标作「{REGIME}」，内部结构已经不是原来的样子。往「{TOWARD}」走，才是重点。'],
      ['The regime has not changed yet. The trajectory has — toward {TOWARD}. Act on the change, not the old label.', '周期标签还没变，走势已经变了，方向是「{TOWARD}」。操作要跟着变化走。']
    ];
  var REGI = [   // IMPROVING — still {REGIME} on the print, but turning UP toward {TOWARD}
      ['The label still says {REGIME}, but the trend is improving toward {TOWARD}. It is early, but direction is now constructive.', '标签还是「{REGIME}」，趋势已经开始改善，正往「{TOWARD}」走。还早，但方向转对了。'],
      ['{REGIME} remains the confirmed state. The improvement toward {TOWARD} is the part worth watching.', '当前确认状态仍是「{REGIME}」。更值得看的是，它正在往「{TOWARD}」改善。'],
      ['The backdrop is still {REGIME}, but it is getting less hostile. Let the move toward {TOWARD} earn more trust over time.', '大环境仍是「{REGIME}」，但压力在减轻。往「{TOWARD}」走的趋势，还需要时间确认。']
    ];
  var REGSG = [  // STABLE + good quad — genuinely holding
      ['{REGIME} is intact and stable. The backdrop supports risk, but entries still need to earn it.', '「{REGIME}」状态稳定，大环境支持承担风险，但每个买点仍要单独确认。'],
      ['The {REGIME} backdrop is holding. Stay involved where price agrees.', '「{REGIME}」格局还稳。价格配合的方向，可以继续参与。'],
      ['No deterioration in {REGIME} yet. Keep what works; do not manufacture trades.', '「{REGIME}」暂时没有转弱。跑得好的继续拿，不必硬找新机会。']
    ];
  var REGSB = [  // STABLE + bad quad — stuck, no thaw
      ['{REGIME} is stable, but it is not a supportive backdrop. Keep the burden of proof high.', '「{REGIME}」状态稳定，但并不友好。出手前，多要一点确认。'],
      ['No improvement in {REGIME} yet. Patience remains the better position.', '「{REGIME}」暂时没有改善。继续等，比勉强出手好。']
    ];
  var RISK = { calm: [
      ['Systemic stress is low. That gives the tape room, not immunity.', '系统性压力不高，盘面有回旋余地，但不等于没有风险。'],
      ['The risk layer is quiet. You can focus on selection instead of defense.', '风险层面较平静。今天可以把注意力放在选股，而不是防守。'],
      ['No broad stress signal underneath the market right now.', '目前市场底层没有出现广泛压力信号。']
    ], hot: [
      ['Stress is rising beneath the index. Reduce size before you reduce standards.', '指数下面的压力在上升。先降仓位，别降标准。'],
      ['The risk layer is tightening. Slow the pace and demand cleaner entries.', '风险环境正在收紧。放慢节奏，只做更清楚的机会。'],
      ['Credit and stress measures are worsening together. That deserves more caution.', '信用和压力指标同时走弱，值得多一层防守。']
    ] };
  var REGION = [
    ['China remains out of sync with the rest of the board. Treat it as a separate trade, not global confirmation.', '中国市场仍在走独立节奏。单独判断，别拿它替全球行情背书。'],
    ['{STAG} remains in a stagflationary backdrop. Price needs to offer more before the risk is attractive.', '{STAG}仍处在滞胀环境。价格要更有吸引力，风险才值得承担。'],
    ['{GOLD} has one of the cleaner macro backdrops on the board. Let price confirm it.', '{GOLD}的宏观环境相对干净，但仍要等价格确认。'],
    ['Global markets are not moving as one. Regional selection matters more than the headline.', '全球市场没有同涨同跌。今天看地区差异，比看总标题更重要。']
  ];
  var BREADTH = { down: [
      ['{DOWN} of {TOTAL} tracked markets are lower. That is broad enough to treat as macro pressure.', '跟踪的 {TOTAL} 个市场中有 {DOWN} 个下跌，已经是比较广泛的宏观压力。'],
      ['Weakness spans {DOWN} of {TOTAL} markets. This is bigger than one index.', '{TOTAL} 个市场里有 {DOWN} 个走弱，不只是某一个指数的问题。']
    ], up: [
      ['{UP} of {TOTAL} tracked markets are higher. The move has useful breadth.', '跟踪的 {TOTAL} 个市场中有 {UP} 个上涨，涨势有一定广度。'],
      ['Strength spans {UP} of {TOTAL} markets. Participation is healthier than the headline alone suggests.', '{TOTAL} 个市场里有 {UP} 个走强，参与度比单看指数更健康。']
    ], split: [
      ['The global board is split. This is a selection day, not a conviction day.', '全球盘面分化。今天更适合精选，而不是重仓押方向。'],
      ['Markets are evenly divided. Let individual setups carry the decision.', '各市场涨跌参半。是否出手，交给具体机会决定。']
    ] };
  var MOVER = [
    ['{MOVER} is the outlier, {MOVERDIR} {MOVERPCT}%. Start there if you want to know what changed.', '{MOVER}是今天的异动，{MOVERDIR} {MOVERPCT}%。想看变化从哪来，先看这里。'],
    ['{MOVER} moved {MOVERPCT}%. That is large enough to deserve a separate look.', '{MOVER}波动 {MOVERPCT}%，幅度已经值得单独看。'],
    ["Today's largest move is in {MOVER}: {MOVERDIR} {MOVERPCT}%. Treat it as information, not an invitation.", '今天波动最大的是{MOVER}，{MOVERDIR} {MOVERPCT}%。先把它当信息，不要当成追单理由。']
  ];
  var META = [
    ['The cross-asset pass is current through {ASOF}.', '跨资产数据已更新至 {ASOF}。'],
    ['The read above uses data current through {ASOF}.', '上面的判断基于截至 {ASOF} 的最新数据。'],
    ['The useful part is not one indicator; it is where independent signals agree.', '真正有用的，不是某一个指标，而是几条独立线索指向同一个方向。'],
    ['Nine markets, one consistent frame. The detail is below if you want it.', '九个市场，用同一套框架看。需要细节，下面都有。'],
    ['The first pass is complete. What remains is the decision, not more noise.', '第一轮筛选已经完成。接下来需要的是判断，不是更多杂音。']
  ];
  // The freshest "What changed" signal, quoted in the alert's own plain words.
  var ALERTP = [
    ['Most recent change: “{ALERT}.” I would open that before anything else.', '最新变化是：「{ALERT}」。如果只看一条，先看这个。'],
    ['One fresh signal deserves attention: “{ALERT}.” The evidence is below.', '有一条新信号值得注意：「{ALERT}」。依据就在下面。']
  ];
  // Crypto never closes — on a weekend/holiday it's the only board still printing.
  var CRYPTO = { on: [
      ['Equities are closed. Bitcoin is still trading, and its risk backdrop is constructive. Observe first; no need to chase.', '股市休市，比特币仍在交易，风险环境偏积极。先观察，不必追。'],
      ['Crypto is the live market today. Bitcoin is constructive, but a quiet day does not need to become a trade.', '今天还在交易的是加密市场。比特币偏强，但没必要为了交易而交易。']
    ], off: [
      ['Crypto is the only live market, and Bitcoin remains defensive. There is no reason to force exposure.', '目前只有加密市场在交易，比特币仍偏防守。没必要勉强参与。'],
      ['Bitcoin is trading, but its risk backdrop is cautious. Watching is enough for now.', '比特币还在交易，但风险环境偏谨慎。现在先看就够了。']
    ] };
  var NUDGE = { on: [
      ['Conditions support taking risk, not abandoning discipline. Add only where the setup already works.', '环境支持承担风险，但不支持放松纪律。只给已经走对的机会加仓。'],
      ['Today favors participation. Keep size deliberate and let winners earn more capital.', '今天适合参与。仓位有计划，走强的标的再多给一点。'],
      ['The backdrop is clean enough to act. Keep the threshold for quality where it is.', '大环境够干净，可以行动。但机会的质量标准不能降。'],
      ['Risk is being rewarded. Use that permission carefully.', '当前承担风险有回报。可以做，但别做过头。']
    ], good: [
      ['Constructive, not effortless. Add to strength; leave weak ideas alone.', '盘面偏积极，但不是随便做都行。强的可以加，弱的别碰。'],
      ['There is room to participate. Keep the size proportionate to the evidence.', '今天有参与空间。证据有多强，仓位就做多大。'],
      ['The backdrop is helping. Add to what is working and skip the rest.', '大环境在帮忙。跑得好的可以加，其余的先放着。'],
      ['A decent tape. Stay selective and let price do the convincing.', '盘面不错。继续精选，让价格自己证明。']
    ], mixed: [
      ['No broad edge right now. Keep the best positions and leave the rest alone.', '眼下没有明显的整体优势。最好的仓位继续拿，其余的先别动。'],
      ['Mixed tape. Patience is more useful than a market call.', '盘面分化。现在耐心比判断大盘方向更有用。'],
      ['The market is not offering a clear advantage. Make fewer decisions.', '市场没有给出清楚优势。少做决定。'],
      ['Choppy conditions. Trade less and require more.', '行情反复。少出手，多确认。']
    ], careful: [
      ['Risk is rising faster than opportunity. Cut size and keep optionality.', '风险上升得比机会快。降一点仓位，保留选择。'],
      ['This tape deserves smaller positions and cleaner entries.', '这种盘面适合小仓位，只做更清楚的买点。'],
      ['Keep the core if the thesis is intact; trim anything you are only hoping for.', '逻辑没变的核心仓位可以留。只是靠期待撑着的，先减。'],
      ['Uncertainty is high enough to matter. Size down.', '不确定性已经高到会影响结果。仓位降一点。'],
      ['This pace is too noisy for frequent decisions. Slow down.', '这种节奏不适合频繁出手。慢一点。'],
      ['Protect the downside first. Better prices can wait.', '先管好下行风险。更好的价格，值得等。']
    ], off: [
      ['Preserve capital today. Conditions do not justify the exposure yet.', '今天先保住本金。当前条件还不足以支持持仓。'],
      ['Stand aside until the tape stabilizes. Missing the first bounce is the cheaper mistake.', '等盘面稳住再说。错过第一下反弹，代价通常更小。'],
      ['Cash is useful when the market offers no clean edge.', '市场没有清楚优势时，现金就是有用的仓位。'],
      ['Until conditions improve, staying out is the cleanest decision.', '环境改善之前，先不参与最稳妥。'],
      ['Do not try to predict the low. Wait for buyers to prove it.', '别猜底。等买方自己证明。'],
      ['Keep capital available. There will be cleaner entries later.', '先把资金留着，后面会有更清楚的机会。']
    ] };
  var CLOSE = [
    ["That's the read. The dashboards below have the detail.", '结论就这些。细节都在下面的看板里。'],
    ['That is enough for now. Start with the strongest signal.', '先说到这里。从最强的信号开始看。'],
    ['The broad picture is set. Use the board for the evidence.', '大方向已经清楚。证据和细节，下面都有。'],
    ['You have the context. Now keep the decision simple.', '背景已经交代清楚。接下来，把决定做简单。']
  ];

  /* ---- weekend & holiday material ----------------------------------------- */
  var WOPEN = { sat: [
      ['Saturday. Cash markets are closed; this is a review, not a live tape.', '周六，现货市场休市。现在适合复盘，不是看实时行情。'],
      ['Markets are closed. Slow down and use the time to review.', '市场休市。把节奏慢下来，趁现在好好复盘。'],
      ['Weekend. Nothing on the board needs an immediate decision.', '周末了。盘面上没有什么需要立刻决定。']
    ], sun: [
      ['Sunday. One quiet day left before the week begins.', '周日。新一周开始前，还有一天安静时间。'],
      ['This is a planning day, not a trading day.', '今天适合做计划，不适合找交易。'],
      ['Set the plan while the market is quiet.', '趁市场安静，把下周计划写清楚。']
    ] };
  var HOPEN = [   // a market-closed holiday, greeting already spoken earlier today
    ['The home market is closed for the holiday. This is context, not a live session.', '本地市场因假期休市。现在看到的是背景信息，不是实时交易。'],
    ['Holiday session. Nothing in the home market needs action today.', '假期休市，本地市场今天没有需要处理的行情。']
  ];
  // The weekend nudge: finish the useful work, then stop.
  var WNUDGE = [
    ['Review the decisions, write the plan, then step away.', '复盘这周的操作，写好计划，然后离开屏幕。'],
    ['Use the quiet to improve the process, not to manufacture a trade.', '趁安静把流程理顺，别为了交易而找交易。'],
    ['Rest is part of risk management. Once the plan is written, close the screen.', '休息也是风险管理。计划写完，就把屏幕关掉。'],
    ['The charts will still be here Monday. Your attention is the scarcer asset.', '图表周一还在，注意力更值钱。'],
    ['You have done enough market work for today.', '今天的市场功课已经够了。'],
    ['One useful weekend task: decide in advance what would change your mind.', '周末最值得做的一件事，是提前想清楚什么情况会让你改变判断。'],
    ['Leave the next decision to the next session.', '下一次决定，留到下一次开市再做。']
  ];
  var HNUDGE = [
    ['The market is closed. No trading decision is required today.', '市场休市。今天不需要做交易决定。'],
    ['There is no reason to treat a holiday like a trading day.', '假期就别按交易日过了，没这个必要。']
  ];
  var WCLOSE = [
    ["That's the weekend read. Back to the rest of your day.", '周末的盘面就说到这里。剩下的时间留给自己吧。'],
    ['The plan can wait until the next session.', '剩下的，等下个交易日再处理。']
  ];

  /* ---- assemble the sequence: greeting + a few reads, tapering on repeat --- */
  var GREET = {
    morning: [['Good morning', '早上好'], ['Morning', '早'], ["You're early", '来得挺早'], ['Ready when you are', '准备好了就开始']],
    afternoon: [['Good afternoon', '下午好'], ['Afternoon', '下午好'], ['Back at the desk', '回来了'], ['Let’s continue', '继续吧']],
    evening: [['Good evening', '晚上好'], ['Evening', '晚上好'], ['Still at it', '还在看盘'], ['Let’s take one more look', '再看一眼']],
    late: [["You're up late", '夜深了'], ['Late one', '还没收工'], ['Still working', '这么晚还在看'], ['One last look', '睡前再看一眼']]
  };
  function greetingLine() {
    var H = d0.getHours(), tod = H < 5 ? 'late' : H < 12 ? 'morning' : H < 18 ? 'afternoon' : H < 23 ? 'evening' : 'late';
    var g = firstEver ? ['Welcome', '欢迎'] : draw('greet.' + tod, GREET[tod]);   // draw() → no repeat in a day
    return [name ? g[0] + ', ' + name : g[0], name ? g[1] + '，' + name : g[1]];
  }
  var lines = [];
  if (reload && C) {
    // A page REFRESH (same session) — one honest beat that acknowledges it, then straight to
    // the brand. We don't re-welcome someone standing right here, or re-read a market they
    // saw a minute ago. (This is the smarter move than pretending it's a fresh visit.)
    lines.push({ s: draw('reload', RELOAD) });
  } else {
  lines.push({ big: true, s: greetingLine() });                       // the name (large)

  // A holiday greets exactly once per occurrence, right after the name — after that,
  // the day still KNOWS it's a holiday (closed-market framing), it just stops repeating it.
  var holSpoken = false;
  if (HOLIDAY && holMarkOnce(HOLIDAY)) { holSpoken = true; lines.push({ s: [HOLIDAY.en, HOLIDAY.zh] }); }

  if (closedDay) {
    // The market is CLOSED (weekend, or the viewer's holiday). Honest framing: last
    // session read as the last session, crypto as the only live board, rest as the nudge.
    if (!holSpoken) {
      if (wknd) lines.push({ s: draw('wopen.' + (dow === 6 ? 'sat' : 'sun'), WOPEN[dow === 6 ? 'sat' : 'sun']) });
      else lines.push({ s: draw('hopen', HOPEN) });
    }
    if (C && visit < 3) lines.push({ s: draw('wtape.' + dir, WTAPE[dir]) });
    if (visit < 3) {
      var wmids = [];
      if (BTC) wmids.push(['crypto.' + BTC, CRYPTO[BTC]]);
      if (C) {
        var wrd = C.home.rdir || 'stable', wgoodQ = (quad === 'q1' || quad === 'q2');
        wmids.push(wrd === 'deteriorating' ? ['regime.det', REGD] : wrd === 'improving' ? ['regime.imp', REGI] : wgoodQ ? ['regime.sg', REGSG] : ['regime.sb', REGSB]);
      }
      wmids.push(['meta', META]);
      wmids.sort(function (a, b) { return (MEM.mids.indexOf(a[0].split('.')[0]) >= 0 ? 1 : 0) - (MEM.mids.indexOf(b[0].split('.')[0]) >= 0 ? 1 : 0); });
      if (wmids.length) { MEM.mids.push(wmids[0][0].split('.')[0]); lines.push({ s: draw(wmids[0][0], wmids[0][1]) }); }
    }
    lines.push({ s: draw(wknd ? 'wnudge' : 'hnudge', wknd ? WNUDGE : HNUDGE) });
    if (visit === 1 && wknd) lines.push({ s: draw('wclose', WCLOSE) });
  } else if (C) {
    // The regime TREND biases the day's advice, symmetrically — the whole point of this:
    //  • a good regime DETERIORATING is a slow headwind → one notch more cautious even on a
    //    green tape (don't let a lagging "Goldilocks" talk you into risk while it rolls over);
    //  • a bad regime IMPROVING toward a better quad is a tailwind → ease one notch (bad-to-
    //    better is when you lean in early). Direction, not just the last print.
    if (C.home.rdir === 'deteriorating' && (quad === 'q1' || quad === 'q2')) {
      C.mood = { on: 'good', good: 'mixed', mixed: 'careful', careful: 'off', off: 'off' }[C.mood] || C.mood;
    } else if (C.home.rdir === 'improving' && C.home.rtoward_en) {
      C.mood = { off: 'careful', careful: 'mixed', mixed: 'good', good: 'good', on: 'on' }[C.mood] || C.mood;
    }
    // opener / recall
    if (visit >= 3) lines.push({ s: draw('v3', VISIT3) });
    else if (visit === 2) lines.push({ s: draw('v2', VISIT2) });
    else lines.push({ s: draw('open', OPEN) });
    // today's tape (always)
    lines.push({ s: draw('tape.' + dir, TAPE[dir]) });
    // one "middle" beat (context or texture), rotated so a new subject shows each visit
    var budget = visit >= 3 ? 0 : 1;
    if (budget) {
      var mids = [];
      var rdir = C.home.rdir || 'stable', goodQ = (quad === 'q1' || quad === 'q2'), turning = (rdir === 'deteriorating' || rdir === 'improving');
      var rgm = rdir === 'deteriorating' ? ['regime.det', REGD] : rdir === 'improving' ? ['regime.imp', REGI] : goodQ ? ['regime.sg', REGSG] : ['regime.sb', REGSB];
      if (ALERTX) mids.push(['alert', ALERTP]);   // the freshest change on the board leads
      if (turning) mids.push(rgm);   // a regime that's TURNING is the headline — surface it early
      mids.push(['region', REGION]);
      mids.push(['risk.' + (C.risky ? 'hot' : 'calm'), RISK[C.risky ? 'hot' : 'calm']]);
      var bk = C.down >= C.total * 0.6 ? 'down' : C.up >= C.total * 0.6 ? 'up' : 'split';
      mids.push(['breadth.' + bk, BREADTH[bk]]);
      if (C.mover && Math.abs(C.mover.index_chg_pct || 0) >= 0.8) mids.push(['mover', MOVER]);
      mids.push(['meta', META]);
      if (!turning) mids.push(rgm);   // a stable regime is just part of the rotation
      // prefer a topic not used as a middle beat yet today (rotate subjects across visits)
      mids.sort(function (a, b) { return (MEM.mids.indexOf(a[0].split('.')[0]) >= 0 ? 1 : 0) - (MEM.mids.indexOf(b[0].split('.')[0]) >= 0 ? 1 : 0); });
      var beat = mids[0];
      MEM.mids.push(beat[0].split('.')[0]);
      lines.push({ s: draw(beat[0], beat[1]) });
    }
    // the take-away
    lines.push({ s: draw('nudge.' + C.mood, NUDGE[C.mood]) });
    if (visit === 1) lines.push({ s: draw('close', CLOSE) });   // first read of the day gets a sign-off
  } else {
    // no market data on the page → still human, just a couple of generic beats
    lines.push({ s: draw('open', OPEN) });
    lines.push({ s: draw('meta', META) });
    lines.push({ s: draw('close', CLOSE) });
  }
  }
  save();

  /* ---- play it: type, hold to let it land, fade, next; then slow dissolve -- */
  var text = function (p) { return document.documentElement.getAttribute('data-lang') === 'zh' ? p[1] : p[0]; };
  var activePair = null, typingActive = false;
  document.addEventListener('langchange', function () {
    // The settings panel switches the rest of the hub without a reload. Keep the
    // sentence in step too; a line already resting on screen changes immediately,
    // while an active type pass picks up the new script on its next character.
    if (activePair && !typingActive) tx.textContent = text(activePair);
  });
  hdr.classList.add('greet-run');
  var LINE_HOLD_MIN_MS = 3000;
  var LINE_HOLD_MAX_MS = 4600;
  var FINAL_HOLD_MS = 6500;
  var BRAND_HANDOFF_MS = 900;
  function finish() {
    greet.classList.remove('convo', 'is-speaking', 'is-thinking');
    hdr.classList.remove('greet-run');
  }   // slow CSS crossfade → brand

  // Every pause below goes through wait(), never a bare setTimeout: timers keep running
  // (throttled) in a HIDDEN tab, so a hub opened in a background tab used to deliver its
  // whole read to nobody and be back to the brand by the time you looked. Hold while the
  // page is hidden; pick up from the same character when the reader actually arrives.
  // Belt AND braces: a pointer moving across the page proves a reader is there even if the
  // flag never flips (non-composited embeddings can hold it true), and that rescue is
  // STICKY — otherwise every character re-parks and the read crawls one glyph per twitch.
  // A visibilitychange resume does NOT set it: there the flag works, and leaving again
  // should park again, which is the whole point.
  var awake = false;
  function wait(ms, fn) {
    if (awake || !document.hidden) return setTimeout(fn, ms);
    var EV = ['visibilitychange', 'pointermove'], i;
    function go(e) {
      if (e.type === 'visibilitychange' && document.hidden) return;
      if (e.type === 'pointermove') awake = true;
      for (i = 0; i < EV.length; i++) document.removeEventListener(EV[i], go, true);
      setTimeout(fn, ms);
    }
    for (i = 0; i < EV.length; i++) document.addEventListener(EV[i], go, { passive: true, capture: true });
  }

  if (reduced()) {
    // no typing/animation: show the greeting + one read, then leave the last thought
    // in place for the same full reading window as the animated path.
    var seq = [lines[0], lines[1] || lines[0]], si = 0;
    (function step() {
      var ln = seq[si];
      greet.classList.toggle('convo', !ln.big);
      greet.classList.add('is-speaking');
      activePair = ln.s;
      tx.textContent = text(ln.s);
      si++;
      if (si < seq.length) wait(LINE_HOLD_MIN_MS, step);
      else wait(FINAL_HOLD_MS + BRAND_HANDOFF_MS, finish);
    })();
    return;
  }

  // The sequence owns its own lifecycle. Incidental clicks and keystrokes never dismiss
  // it: the greeting may scroll naturally out of view, but it cannot vanish mid-word.
  var li = 0;
  function playLine() {
    var ln = lines[li];
    greet.classList.toggle('convo', !ln.big);
    greet.classList.remove('is-thinking');
    greet.classList.add('is-speaking');
    activePair = ln.s;
    var full = text(ln.s), i = 0;
    typingActive = true;
    tx.style.opacity = '1';
    (function type() {
      full = text(ln.s);
      tx.textContent = full.slice(0, i);
      if (i <= full.length) {
        var ch = full.charAt(i - 1); i++;
        // pause at breath points in BOTH scripts (、； and full-width ？！ included)
        var d = /[\s，,、；;]/.test(ch) ? 90 : /[.。—？?！!…：]/.test(ch) ? 150 : 26;
        wait(d, type);
      } else {
        typingActive = false;
        var hold = Math.min(LINE_HOLD_MAX_MS, LINE_HOLD_MIN_MS + full.length * 18);
        if (li === lines.length - 1) hold = Math.max(hold, FINAL_HOLD_MS);
        wait(hold, nextLine);
      }
    })();
  }
  function nextLine() {
    li++;
    if (li >= lines.length) { wait(BRAND_HANDOFF_MS, finish); return; }
    greet.classList.remove('is-speaking');
    greet.classList.add('is-thinking');
    tx.style.transition = 'opacity .34s ease'; tx.style.opacity = '0';   // soft fade between remarks
    wait(360, playLine);
  }
  playLine();
})();

/* ── checkout-return confirmation ────────────────────────────────────────────
 *
 * Hosted Stripe Checkout returns a PAYING customer to start.html?checkout=success
 * (app/billing.py::checkout). Before 2026-07-25 it returned them to
 * /plans.html?checkout=success — the pricing page — where a dismissible banner said
 * "head to the dashboard" without a link and the plan cards still read "Subscribe".
 *
 * The tier is NOT taken from the query string (a user can type that). We strip the
 * param immediately, then read the truth back from same-origin /api/me — which the
 * webhook + the /subscribe/complete fast path have already converged — and name the
 * plan the server actually granted. If /api/me is slow or unhappy we still confirm,
 * just without the tier name; we never claim a plan we could not verify.
 *
 * Lives in this external asset ON PURPOSE: the hub HTML is generated by
 * scripts/build_vector.py and the render bot STRIPS large non-ASCII inline <script>
 * blocks from it (burned in macro #3381). External assets survive and get ?v=hash.
 */
(function () {
  var m = /[?&]checkout=(success|cancel)\b/.exec(location.search);
  if (!m) return;
  var ok = m[1] === 'success';
  try {  // never re-show on refresh / back
    history.replaceState({}, '', location.pathname + location.search
      .replace(/([?&])checkout=(success|cancel)\b&?/, '$1').replace(/[?&]$/, '') + location.hash);
  } catch (e) {}
  if (!ok) return;   // a cancel lands on plans.html; nothing to say on the desk

  var host = document.querySelector('.wrap') || document.body;
  var top = document.querySelector('.hub-top');

  var el = document.createElement('div');
  el.className = 'hub-billing-flag';
  el.setAttribute('role', 'status');
  el.style.cssText = [
    'display:flex', 'align-items:center', 'gap:10px',
    'margin:10px 0 0', 'padding:11px 14px',
    'border:1px solid var(--line,#2a2f3a)', 'border-radius:12px',
    'background:var(--panel,#181b21)', 'color:var(--text,#d7dce3)',
    'font-size:14px', 'line-height:1.45',
    'opacity:0', 'transition:opacity .5s ease'
  ].join(';');

  function span(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + zh + '</span>';
  }
  function paint(html) {
    el.innerHTML =
      '<span aria-hidden="true" style="flex:0 0 auto;width:20px;height:20px;border-radius:50%;' +
      'display:inline-flex;align-items:center;justify-content:center;font-size:12px;' +
      'background:var(--accent,#285fff);color:#fff">&#10003;</span>' +
      '<span style="flex:1 1 auto">' + html + '</span>' +
      '<button type="button" aria-label="Dismiss" style="flex:0 0 auto;background:none;border:0;' +
      'color:var(--muted,#8b93a1);font-size:15px;cursor:pointer;padding:2px 4px">&#10005;</button>';
    el.querySelector('button').addEventListener('click', function () { el.remove(); });
  }

  paint(span('You’re in. Your subscription is active.', '开通成功，订阅已生效。'));
  if (top && top.parentNode) top.parentNode.insertBefore(el, top.nextSibling);
  else host.insertBefore(el, host.firstChild);
  // Belt AND braces: requestAnimationFrame does not fire in a hidden/background tab, and
  // this banner must never be stuck at opacity:0 — a customer who just paid has to see the
  // confirmation. The timeout is the fallback; setting opacity twice is harmless.
  function reveal() { el.style.opacity = '1'; }
  requestAnimationFrame(reveal);
  setTimeout(reveal, 80);

  var NAMES = { insider: ['Insider', '内圈'], pro: ['Pro', '专业版'] };
  function fmt(iso, zh) {
    try {
      var d = new Date(iso);
      if (isNaN(d)) return '';
      return d.toLocaleDateString(zh ? 'zh-CN' : 'en-US',
        { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) { return ''; }
  }

  fetch('/api/me', { credentials: 'include', headers: { Accept: 'application/json' } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (me) {
      if (!me || !me.tier || me.tier === 'free') return;   // don't overclaim
      var nm = NAMES[me.tier] || [me.tier, me.tier];
      var enD = fmt(me.current_period_end, false), zhD = fmt(me.current_period_end, true);
      if (me.status === 'trialing' && enD) {
        paint(span(nm[0] + ' is live. Your free trial runs to ' + enD + ' — cancel any time before then and you won’t be charged.',
                   nm[1] + ' 已开通。免费试用至 ' + zhD + '，在此之前取消不会扣费。'));
      } else if (enD) {
        paint(span(nm[0] + ' is active — your plan renews ' + enD + '.',
                   nm[1] + ' 已生效 — 下次续费日期 ' + zhD + '。'));
      } else {
        paint(span(nm[0] + ' is active.', nm[1] + ' 已生效。'));
      }
    })
    .catch(function () { /* keep the generic confirmation */ });
})();

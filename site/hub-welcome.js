/* hub-welcome.js — the signed-in hub's opening moment.
 *
 * A name greeting, then a short spoken-aloud read of TODAY's markets in the voice of a
 * brilliant, casual friend who happens to run a hedge fund — a few remarks with pauses,
 * then a slow dissolve back into the MASTERMIND brand.
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

  var zh = document.documentElement.getAttribute('data-lang') === 'zh';
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
    newyear:      [[1, 1], "Happy New Year — new year, clean slate. Markets are closed today.", '元旦快乐！新的一年，新的开始。今天休市。'],
    christmas:    [[12, 25], "Merry Christmas — the market's closed, and so am I. Enjoy the day.", '圣诞快乐！市场休市，好好过节。'],
    boxing:       [[12, 26], 'Happy Boxing Day — still closed, still quiet. Enjoy it.', '节礼日快乐，市场继续休市，继续清净。'],
    goodfri:      [{ e: -2 }, "It's Good Friday — markets are closed for the long weekend.", '耶稣受难日，市场休市——是个长周末。'],
    eastermon:    [{ e: 1 }, "Easter Monday — the market's still closed. Enjoy the long weekend.", '复活节星期一，还在休市。好好过长周末。'],
    may1:         [[5, 1], 'Happy May Day — even the market takes today off.', '五一快乐！劳动节这天，连市场都不劳动。'],
    cnyeve:       [{ t: { 2026: '2-16', 2027: '2-5', 2028: '1-25' } }, "It's Lunar New Year's Eve — go enjoy the reunion dinner. The market can wait till next year.", '除夕快乐！今晚好好吃年夜饭，行情的事，明年再说。'],
    cny:          [{ t: { 2026: '2-17', 2027: '2-6', 2028: '1-26' } }, 'Happy Lunar New Year — markets are closed, red envelopes are open.', '新年快乐，恭喜发财！市场休市，红包开市。'],
    qingming:     [{ t: { 2026: '4-5', 2027: '4-5', 2028: '4-4' } }, "It's the Qingming break — markets are closed today. If the weather's kind, take a walk.", '清明假期，市场休市。天气好的话，出去走走。'],
    duanwu:       [{ t: { 2026: '6-19', 2027: '6-9', 2028: '5-28' } }, 'Happy Dragon Boat Festival — markets are closed today. Go find a zongzi.', '端午安康！市场休市，记得吃粽子。'],
    zhongqiu:     [{ t: { 2026: '9-25', 2027: '9-15', 2028: '10-3' } }, "Happy Mid-Autumn Festival — markets closed, moon's full. Head home early.", '中秋快乐，人月两团圆。今天休市，早点回家。'],
    guoqing:      [[10, 1], 'Happy National Day — the long holiday is on, markets are closed.', '国庆快乐！长假开始，市场休市，好好休息。'],
    mlk:          [{ w: [1, 1, 3] }, "It's MLK Day — US markets are closed. See you tomorrow.", '马丁·路德·金纪念日，美股休市一天。'],
    presidents:   [{ w: [2, 1, 3] }, "It's Presidents' Day — US markets are closed.", '总统日，美股休市。'],
    memorial:     [{ w: [5, 1, -1] }, "It's Memorial Day — markets are closed for the long weekend.", '阵亡将士纪念日，美股休市，长周末。'],
    juneteenth:   [[6, 19], "It's Juneteenth — US markets are closed today.", '六月节，美股休市一天。'],
    july4:        [[7, 4], 'Happy Fourth of July — markets are closed. Go find the fireworks.', '美国独立日快乐！美股休市，看烟花去。'],
    labor:        [{ w: [9, 1, 1] }, "Happy Labor Day — the market's taking the day off too.", '劳动节快乐！市场今天也带薪休假。'],
    thanksgiving: [{ w: [11, 4, 4] }, 'Happy Thanksgiving — markets are closed. Family first today.', '感恩节快乐！美股休市，今天家人优先。'],
    familyday:    [{ w: [2, 1, 3] }, "It's Family Day — Canadian markets are closed. The clue is in the name.", '加拿大家庭日，多伦多休市。节日名字已经把今天安排明白了。'],
    victoria:     [{ t: { 2026: '5-18', 2027: '5-24', 2028: '5-22' } }, "It's Victoria Day — Canadian markets are closed for the long weekend.", '维多利亚日，加拿大休市，长周末。'],
    canadaday:    [[7, 1], 'Happy Canada Day — markets are closed. Enjoy it.', '加拿大国庆快乐！市场休市。'],
    civic:        [{ w: [8, 1, 1] }, "It's the civic holiday — Toronto's closed. A long weekend in August: take it.", '八月公民假日，多伦多休市。夏天的长周末，值得好好过。'],
    labourca:     [{ w: [9, 1, 1] }, "Happy Labour Day — the market's taking the day off too.", '劳动节快乐！市场今天也放假。'],
    thanksca:     [{ w: [10, 1, 2] }, 'Happy Thanksgiving — Canadian markets are closed today.', '加拿大感恩节快乐！市场休市。'],
    mayday:       [{ w: [5, 1, 1] }, "It's the early May bank holiday — London's closed. Enjoy the long weekend.", '五月初的银行假日，伦敦休市。长周末愉快。'],
    springbank:   [{ w: [5, 1, -1] }, "It's the spring bank holiday — London's closed today.", '春季银行假日，伦敦今天休市。'],
    summerbank:   [{ w: [8, 1, -1] }, "It's the summer bank holiday — London's closed. Squeeze the last out of summer.", '夏末银行假日，伦敦休市。抓住夏天的尾巴。'],
    australiaday: [[1, 26], "Happy Australia Day — the ASX is closed. It's summer there; go enjoy it.", '澳大利亚国庆日快乐！澳股休市。'],
    anzac:        [[4, 25], "It's Anzac Day — markets are closed in Australia.", '澳新军团日，澳洲市场休市。'],
    waitangi:     [[2, 6], "It's Waitangi Day — markets are closed in New Zealand.", '怀唐伊日，新西兰休市。'],
    stpatrick:    [[3, 17], "Happy St Patrick's Day — Dublin's closed. The one day green is mandatory.", '圣帕特里克节快乐！都柏林休市。'],
    hksar:        [[7, 1], "It's HKSAR Establishment Day — Hong Kong markets are closed.", '香港回归纪念日，港股休市。'],
    t228:         [[2, 28], 'Peace Memorial Day — Taiwan markets are closed today.', '和平纪念日，台股休市一天。'],
    childtomb:    [[4, 4], "It's the Children's Day / Tomb-Sweeping break — Taiwan markets are closed.", '儿童节、清明连假，台股休市。'],
    double10:     [[10, 10], 'Happy Double Tenth — Taiwan markets are closed today.', '双十节快乐！台股休市。'],
    goldenweek:   [[5, 3], "It's Golden Week in Japan — Tokyo's closed. Enjoy the break.", '日本黄金周，东京休市。好好休息。'],
    liberation:   [[8, 15], "It's Liberation Day in Korea — the KOSPI's closed today.", '韩国光复节，首尔休市。'],
    sgnational:   [[8, 9], 'Happy National Day, Singapore — markets are closed today.', '新加坡国庆快乐！市场休市。'],
    republic:     [[1, 26], 'Happy Republic Day — Indian markets are closed today.', '印度共和国日快乐！市场休市。'],
    indep:        [[8, 15], 'Happy Independence Day — Indian markets are closed today.', '印度独立日快乐！市场休市。'],
    gandhi:       [[10, 2], "It's Gandhi Jayanti — Indian markets are closed today.", '甘地诞辰纪念日，印度市场休市。'],
    diwali:       [{ t: { 2026: '11-8', 2027: '10-29' } }, 'Happy Diwali — may the year ahead glow.', '排灯节快乐！愿新的一年亮亮堂堂。'],
    unity:        [[10, 3], "It's German Unity Day — Frankfurt's closed today.", '德国统一日，法兰克福休市。'],
    bastille:     [[7, 14], 'Happy Bastille Day — Paris is closed today.', '法国国庆日快乐！巴黎休市。']
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
    ['Give me ten seconds before you dive in.', '先别急，给我十秒钟。'],
    ['Quick read while you settle in.', '趁你坐下的工夫，我先说两句。'],
    ["Alright — here's the lay of the land.", '来，先把今天的大盘说清楚。'],
    ["Let me do this morning's homework for you.", '今天的功课，我先帮你做了。'],
    ['Two things before you get to work.', '开工之前，先说两件事。'],
    ["Before you touch anything — here's the temperature.", '下手之前——先感受一下今天的温度。']
  ];
  // Recall lines fire only on a GENUINE return (a real gap of time). Kept clear, not
  // cryptic — they say what the count means ("look today", "check-ins today").
  var VISIT2 = [
    ['Good to have you back at the desk today.', '今天又回来盯盘了，挺好。'],
    ["Back for a second look — let's see what moved.", '回来看第二眼——瞧瞧有什么动了。'],
    ['Second visit today. Something on your mind?', '今天第二趟了。心里惦记着什么？'],
    ["You're back. I'll keep this one short.", '你回来啦。这回我长话短说。']
  ];
  var VISIT3 = [
    ["That's your {V}th look today — you're locked in.", '今天第 {V} 次来了——够专注的。'],
    ['Back again — {V} check-ins today. Markets keeping you busy?', '又来了——今天第 {V} 趟。行情让你闲不住？'],
    ["{V} visits today. You know the drill — I'll be quick.", '今天第 {V} 次了。老规矩——我快点说。'],
    ['You keep coming back. Fine by me — let’s talk.', '一趟又一趟地来。行啊，我乐意陪聊。'],
    ["{V} looks today. When you watch this closely, so do I.", '今天第 {V} 眼了。你盯得这么紧，我也不敢松。']
  ];
  // A page REFRESH (same session) — witty, honest, brief. NOT a "you're back".
  var RELOAD = [
    ['Same desk, same read — you were just here.', '还是这张台子，还是那个结论——你刚来过。'],
    ["Back that fast? Nothing's moved much since you looked.", '这么快又刷？你刚看过，没什么大变化。'],
    ["I'll save us both the time — the read hasn't changed.", '省点时间——结论没变。'],
    ['Still here, still watching. Nothing new to add yet.', '我还在，还盯着。暂时没有新东西。'],
    ['Refreshing won’t move the market — but hi again.', '刷新是刷不出行情的——不过，又见面啦。'],
    ['You just looked. Give it a minute to do something.', '你刚看过。给市场一分钟，让它自己动动。']
  ];
  var TAPE = { up: [
      ['Buyers are in charge today. Nothing wild — a steady green day.', '今天买方说了算。不疯不闹，稳稳的红盘。'],
      ["It's the kind of up day you don't have to fight. Enjoy those.", '今天是不用硬扛的上涨日。且涨且珍惜。'],
      ["Some lift out there today — the easy kind. I'll take it.", '今天盘面有点起色——是轻松的那种。我照单全收。'],
      ['Buyers showed up. Quiet, steady gains.', '买盘来了。安安静静，稳稳地涨。'],
      ["Green on my screens, and it's holding. I like when it holds.", '我这边满屏飘红，而且守得住。守得住的红，才是好红。'],
      ["Up day, and nothing forced about it. That's the good kind.", '涨得一点不勉强。这种涨法，最健康。']
    ], down: [
      ["Heavy day out there. Nothing's broken — it's just heavy.", '今天盘子有点沉。没出大事，就是沉。'],
      ["Red across the screens. The kind of day you sit on your hands.", '今天绿油油一片。这种日子，手别痒，坐住。'],
      ['Down day, and buyers are scarce. Not the day to chase anything.', '下跌日，买盘稀稀拉拉。今天什么都别追。'],
      ['Sellers are writing the story today. Let them tire out.', '今天是卖方在讲故事。等他们讲累了再说。'],
      ["It's drifting lower — not a crash, a slow leak. Patience.", '阴跌磨人——不是崩，是慢慢渗。耐心点。'],
      ['A red day like this rewards patience, not bravado.', '这种下跌日，奖励耐心，不奖励逞强。']
    ], flat: [
      ["Quiet out there. Everyone's waiting on something.", '盘面很静。大家都在等一个说法。'],
      ['Flat and boring — which is honestly fine by me.', '又平又闷——说实话，我不嫌弃。'],
      ['Not much moving today. Coiled, not dead.', '今天没什么动静。是在蓄力，不是躺平。'],
      ["Sideways and patient — the market's holding its breath.", '横盘，有耐心——市场在屏住呼吸。']
    ] };
  /* Weekend / holiday tape: the market is CLOSED, so the last session is read as the
   * last session — never dressed up as a live print. {LASTD} = Friday / last session. */
  var WTAPE = { up: [
      ['{LASTD} closed green, so we go into the break on a decent note.', '{LASTD}收红，这个收尾还算体面。'],
      ["Last look before the close: green, and holding. Nothing to worry about while it's shut.", '休市前最后一眼：红盘，还站得稳。这几天不用惦记。'],
      ["The board went out with buyers under it. It'll keep till the bell.", '收市前还有买盘托着。放心，开盘它还在。']
    ], down: [
      ['{LASTD} closed red — not pretty, but the break came at a good time.', '{LASTD}收绿，不太好看——不过正好趁休市喘口气。'],
      ["The last session was heavy. Good news: nothing can fall while it's closed.", '上一场收得偏沉。好消息是：休市的时候，它跌不了。'],
      ["Went out weak. Let it sit — that's a problem for the reopen, not for today.", '收得偏弱。先放着——那是开盘以后的事，不归今天管。']
    ], flat: [
      ['{LASTD} went out quiet — flat, no drama. A clean pause.', '{LASTD}收平，波澜不惊。停得干干净净。'],
      ["Nothing moved much into the close. The board's asleep, as it should be.", '收市前没什么动静。盘面睡了，本来也该睡。']
    ] };
  // Regime beats are DIRECTION-first, never label-first: the same quad means opposite
  // things depending on whether we're firming into it or rolling out of it — and the
  // confirmed label LAGS the score, so a deteriorating "Goldilocks" is the trap. {REGIME}
  // = the HOME board's quad, {TOWARD} = where its trajectory is dragging it.
  var REGD = [   // DETERIORATING — the label still says {REGIME}, but the trend is down
      ["We're still calling it {REGIME} — but it's rolling over. The label lags; the trend is dragging toward {TOWARD}.", '牌子上还写着「{REGIME}」——但势头在往下翻。标签是滞后的，趋势正把它拖向「{TOWARD}」。'],
      ["Careful with the {REGIME} tag today — the score's slipping toward {TOWARD}. Same word, opposite trade from a month ago.", '「{REGIME}」这个标签先别全信——分数正往「{TOWARD}」滑。词还是那个词，做法得跟一个月前反着来。'],
      ["{REGIME} on paper, but it's aging — momentum leans toward {TOWARD}. I'd turn defensive early, not late.", '纸面上是「{REGIME}」，但成色在变——动能偏向「{TOWARD}」。防守要趁早，别拖到晚。'],
      ["The backdrop still reads {REGIME}, but it's cracking. Trust the direction of change, not the last print.", '大环境还写着「{REGIME}」，但已经有裂缝。信变化的方向，别信最后那个读数。']
    ];
  var REGI = [   // IMPROVING — still {REGIME} on the print, but turning UP toward {TOWARD}
      ["Still {REGIME} on the label, but it's turning up — climbing toward {TOWARD}. Early, but the direction's finally right.", '标签还是「{REGIME}」，但在往上走——朝着「{TOWARD}」爬。还早，但方向终于对了。'],
      ["{REGIME} is the print; the trend is better — headed for {TOWARD}. Bad-to-better is the good kind of change.", '读数还是「{REGIME}」，趋势却在好转——奔着「{TOWARD}」去。由坏转好，是最值钱的那种变化。'],
      ["Don't over-read the {REGIME} tag — it's thawing. Getting less bad is how bottoms start.", '别把「{REGIME}」看得太死——正在解冻。“没那么差了”，往往就是底部的开场白。']
    ];
  var REGSG = [  // STABLE + good quad — genuinely holding
      ["Clean {REGIME}, and it's holding — growth without the heat. Enjoy it while it lasts.", '干干净净的「{REGIME}」，而且稳得住——有增长，不发烫。且涨且珍惜。'],
      ["{REGIME}, steady — no cracks in the score yet. Rare. Don't waste it.", '「{REGIME}」，稳稳的——分数暂时没裂缝。难得，别浪费。'],
      ["The backdrop's {REGIME}, and it isn't going anywhere fast. The regime is your friend here.", '大环境是「{REGIME}」，一时半会儿变不了。这时候，大势是你的朋友。']
    ];
  var REGSB = [  // STABLE + bad quad — stuck, no thaw
      ["Still stuck in {REGIME}, and it's not letting up. Nothing to force here.", '还困在「{REGIME}」里，没有松动的迹象。这里别硬来。'],
      ["{REGIME}, and flat — no thaw in the score yet. Patience beats hope.", '「{REGIME}」，横着——还没解冻。耐心比指望管用。']
    ];
  var RISK = { calm: [
      ["The risk gauges are quiet. Stress is low — rare, clean water.", '风险仪表很安静。压力不大——难得的干净水域。'],
      ["Nothing's flashing red on the risk side. I'll take it.", '风险那边没有红灯在闪。这我收下了。'],
      ['Under the hood, stress is low. If it sells off, that’s mood, not machinery.', '底盘上压力其实不大。就算跌，也是情绪在跌，不是机器坏了。']
    ], hot: [
      ["The risk gauges are lit up. I'd keep the size honest today.", '风险仪表亮起来了。今天仓位放老实点。'],
      ['Stress is climbing under the surface. Move a little slower out there.', '水面下的压力在涨。动作放慢半拍。'],
      ["Credit and stress gauges are tightening — that's the part I watch closest.", '信用和压力的仪表都在收紧——这是我盯得最紧的部分。']
    ] };
  var REGION = [
    ["China's running its own cycle again — out of step with everyone else. The gap itself is information.", '中国又在走自己的周期——和别人不同步。这个“不同步”，本身就是信息。'],
    ["{STAG} is boxed into stagflation. I'd leave that one alone for now.", '{STAG}还闷在滞胀里。这个盘，我暂时绕着走。'],
    ['{GOLD} is sitting in the sweet spot — quietly one of the cleaner boards.', '{GOLD}正待在最舒服的区间——不声不响，却是更干净的盘面之一。'],
    ["The world isn't moving together today — some up, some down. Divergence everywhere.", '今天全球各走各的——有涨有跌，到处在分化。']
  ];
  var BREADTH = { down: [
      ["Almost everything's lower — {DOWN} of {TOTAL} markets down. That's macro, not bad luck.", '几乎全线走低——{TOTAL} 个市场里 {DOWN} 个在跌。这是宏观的事，不是运气差。'],
      ['{DOWN} of {TOTAL} markets lower. When it’s this broad, it’s the tide, not the boats.', '{TOTAL} 个市场里 {DOWN} 个在跌。跌得这么齐，是潮水的问题，不是哪条船的问题。']
    ], up: [
      ["Green nearly everywhere — {UP} of {TOTAL} markets up. Everyone's invited today.", '几乎全线飘红——{TOTAL} 个市场里 {UP} 个在涨。今天人人有份。'],
      ['{UP} of {TOTAL} markets higher. Broad gains — the healthy kind of rally.', '{TOTAL} 个里 {UP} 个在涨。普涨——健康的那种涨法。']
    ], split: [
      ["It's split out there — some up, some down. A stock-picker's day.", '今天分化——有涨有跌。适合挑着做的日子。'],
      ['Half up, half down. Today rewards picking, not predicting.', '一半涨一半跌。今天拼的是选股，不是猜方向。']
    ] };
  var MOVER = [
    ["The big mover today is {MOVER} — {MOVERDIR} {MOVERPCT}%. That's where the story is.", '今天动静最大的是{MOVER}——{MOVERDIR}了 {MOVERPCT}%。故事在那边。'],
    ['Keep half an eye on {MOVER} — {MOVERPCT}% is a real move, not noise.', '{MOVER}那边留半只眼——{MOVERPCT}% 是真动了，不是噪音。'],
    ["Today's outlier: {MOVER}, {MOVERDIR} {MOVERPCT}%. Outliers are where I look first.", '今天的异动是{MOVER}，{MOVERDIR}了 {MOVERPCT}%。有异动的地方，我先看。']
  ];
  var META = [
    ['The desk re-ran the whole world overnight. This is fresh as of {ASOF}.', '后台昨晚把全世界重算了一遍。这是 {ASOF} 的最新结果。'],
    ["I walked every board this morning. You're getting the honest read, not the pretty one.", '今早每个盘面我都过了一遍。给你的是实话，不是漂亮话。'],
    ['The engines cross-check each other before they talk to you. Less noise that way.', '各路引擎先互相对过账，才开口跟你说话。这样噪音少。'],
    ["I don't guess — everything I just said is measured, as of {ASOF}.", '我不猜行情——我刚说的每一句都是算出来的，截至 {ASOF}。'],
    ['Nine markets, one read. I did the reconciling so you don’t have to.', '九个市场，一个结论。对账的活我干了，你不用。']
  ];
  // The freshest "What changed" signal, quoted in the alert's own plain words.
  var ALERTP = [
    ['Freshest thing on the wire: “{ALERT}.” The details are just below.', '盘面上最新的一条：「{ALERT}」。详情就在下面。'],
    ['One thing changed recently — “{ALERT}.” Worth ten seconds of your time.', '最近有个变化——「{ALERT}」。值得花十秒看看。']
  ];
  // Crypto never closes — on a weekend/holiday it's the only board still printing.
  var CRYPTO = { on: [
      ["Stocks are shut, but Bitcoin never sleeps — and its risk board leans friendly right now. Watch it, don't chase it.", '股市关门了，可币圈从不打烊——比特币那边现在偏乐观。看看就好，别追。'],
      ["The only market open right now is crypto. Bitcoin's gauges read risk-on — fun to watch from the couch.", '现在唯一还开着门的是币圈。比特币的仪表偏“愿意冒险”——躺在沙发上看看挺好。']
    ], off: [
      ["Crypto's the only thing trading, and Bitcoin's board is defensive. Nothing out there needs you today.", '现在只有币圈在交易，而比特币那边偏防守。今天外面没什么需要你操心的。'],
      ["Bitcoin never closes, but right now its risk board says be careful. Watching is free.", '比特币从不休市，但它的风险盘现在写着“小心”。看看不要钱。']
    ] };
  var NUDGE = { on: [
      ['If you were waiting for a green light — this is about as close as it gets. Within reason.', '要是你一直在等绿灯——现在差不多就是了。别上头就行。'],
      ['A day you can lean in a little. Sensible size, though.', '今天可以往前多站半步。仓位还是得讲道理。'],
      ["Conditions this clean don't come often. Use them; don't abuse them.", '这么干净的窗口不常有。用它，别滥用它。'],
      ['The setup’s clean. Press a little — just don’t get greedy.', '形态很干净。可以加点力——别贪就行。']
    ], good: [
      ['Constructive out there. Lean in a touch — no heroics.', '外面偏暖。可以稍微前倾——别逞英雄。'],
      ['Room to be a little brave today. Keep a hand on the wheel.', '今天有胆子大一点的空间。但手别离方向盘。'],
      ["The wind's mostly at your back. Add to what's working; leave the rest.", '风大体是顺的。给跑得好的加点码，其余的先不动。'],
      ['Decent day. Add to what’s working, skip the rest.', '盘面不错。跑得好的加一点，其余的跳过。']
    ], mixed: [
      ["Nothing's screaming either way. Let the setups come to you.", '两边都没在喊你。让机会自己走过来。'],
      ['Mixed day — patience beats prediction.', '震荡市——耐心比预测值钱。'],
      ['No clear edge right now. Hold your best ideas, skip the rest.', '眼下没有明显的优势。攥住最好的想法，其余的先放放。'],
      ['Choppy. Trade less, watch more.', '震荡。多看少动。']
    ], careful: [
      ['Careful out there today. Keep some cash dry for better prices.', '今天外面小心点。留点现金，等更好的价格。'],
      ['Not a day for heroes. Small, patient, boring.', '今天别当英雄。小仓位，有耐心，无聊点没关系。'],
      ['Trim the edges, keep the core. Live to trade tomorrow.', '边角修一修，核心留着。留得青山在，明天接着打。'],
      ["If you're unsure, that IS the signal. Size down.", '要是心里没底，这本身就是信号。降点仓。'],
      ["Respect what the market's telling you — it says slow down.", '尊重盘面给的提示——它在让你慢下来。'],
      ['Tighten the stops, loosen the grip.', '止损收紧一点，心态放松一点。']
    ], off: [
      ['Defense first today. Protect the book; opportunities can wait.', '今天防守优先。先保住本金，机会等得起。'],
      ['A day to survive, not to swing. Sit tight.', '今天求生，不求胜。坐稳了。'],
      ['Cash is a position too. No shame in holding it today.', '空仓也是一种仓位。今天拿着现金，不丢人。'],
      ["Sometimes the best trade is no trade. This is one of those days.", '有时候最好的交易，就是不交易。今天就是这种日子。'],
      ["Don't try to catch the falling knife. Let it hit the floor first.", '别伸手去接飞刀。等它落地插稳了再说。'],
      ['On a day like this, doing nothing IS doing something. Wait.', '这种日子，什么都不做本身就是在做事。等。']
    ] };
  var CLOSE = [
    ["Anyway — that's the read. The desk is below whenever you're ready.", '好了——今天就说到这。看板都在下面，你随时开工。'],
    ['That’s the brief. Eyes open, size sensible.', '简报完毕。眼睛放亮，仓位放稳。'],
    ['Enough from me. Go make it a good one.', '我说完了。去吧，打得漂亮点。'],
    ['Alright, the floor’s yours — everything’s below.', '行，交给你了——都在下面。']
  ];

  /* ---- weekend & holiday material ----------------------------------------- */
  var WOPEN = { sat: [
      ["It's Saturday — no opening bell, no closing bell. Just us.", '周六啦——没有开盘钟，也没有收盘钟。就咱俩。'],
      ["Saturday at the desk. The market's off; I'm still around.", '周六还来看盘？市场休息了，我倒是一直都在。'],
      ["Weekend mode: the screens are resting, and that's healthy.", '周末模式：行情不动了，这是好事。']
    ], sun: [
      ['Sunday — one more quiet day before the bell rings again.', '周日了——再安静一天，明天就又开锣了。'],
      ["It's Sunday. A good day to think slow, before the week makes you think fast.", '周日，适合慢慢想的日子——下周有的是要你快快想的时候。'],
      ["Sunday's for the plan, not the P&L.", '周日适合做计划，别盯着盈亏看。']
    ] };
  var HOPEN = [   // a market-closed holiday, greeting already spoken earlier today
    ["Quiet day — the market's closed for the holiday.", '今天休市，盘面清清静静。'],
    ["Still the holiday — nothing's trading. Enjoy the quiet.", '还在放假，没什么可交易的。享受这份清净。']
  ];
  // The weekend nudge: compliments for doing the homework, and permission to stop.
  var WNUDGE = [
    ["Checking in on a weekend — that's the homework most people skip. Respect.", '大周末的还来做功课——这是多数人偷懒不做的部分。佩服。'],
    ['Markets are hard right now. Go get some sun — the charts will keep.', '这段行情不好做。出去晒晒太阳吧，图表跑不了。'],
    ["You've done the work this week. Now go do the living.", '这一周你已经够拼了。剩下的时间，留给生活。'],
    ['Review the week, jot down the plan, close the laptop. In that order.', '复个盘，写两行计划，然后合上电脑。就按这个顺序来。'],
    ["The best position this weekend is outside. I'll watch the rest.", '这个周末最好的仓位，是阳光底下。剩下的我来盯。'],
    ['Rest is part of the strategy. The traders who last all know it.', '休息也是策略的一部分。能在市场里走得远的人，都懂这个。'],
    ['Get some rest — the bell rings again soon enough, and I’ll be here first.', '好好休息——开盘钟很快会再响，到时候我肯定比你先到。']
  ];
  var HNUDGE = [
    ['Holidays are for living. The market will take your call when it reopens.', '假期就该有假期的样子。等开市了，行情随叫随到。'],
    ['Even the market knows when to stop. Take the cue.', '连市场都知道该歇就歇。你也别硬撑。']
  ];
  var WCLOSE = [
    ["Enjoy the weekend. I'll be here when the bell rings.", '周末愉快。开盘钟响的时候，我都在。'],
    ['Go on — the desk will keep. See you Monday.', '去吧，台子我看着。周一见。']
  ];

  /* ---- assemble the sequence: greeting + a few reads, tapering on repeat --- */
  var GREET = {
    morning: [['Good morning', '早上好'], ['Morning', '早啊'], ['Rise and shine', '起床啦'], ['Up early', '起得真早'], ['Morning to you', '早安']],
    afternoon: [['Good afternoon', '下午好'], ['Afternoon', '下午好啊'], ['Good to see you', '又见面了'], ['Midday, then', '中午好'], ['Back at it', '继续开工啦']],
    evening: [['Good evening', '晚上好'], ['Evening', '晚上好啊'], ['Good to see you', '又见面了'], ['Winding down', '忙了一天了吧']],
    late: [['You’re up late', '夜深了啊'], ['Burning the midnight oil', '又熬夜了'], ['Still at it', '还没歇呢'], ['Can’t sleep either', '你也睡不着啊']]
  };
  function greetingLine() {
    var H = d0.getHours(), tod = H < 5 ? 'late' : H < 12 ? 'morning' : H < 18 ? 'afternoon' : H < 23 ? 'evening' : 'late';
    var g = firstEver ? ['Welcome', '欢迎'] : draw('greet.' + tod, GREET[tod]);   // draw() → no repeat in a day
    return [name ? g[0] + ', ' + name : g[0], name ? g[1] + '，' + name : g[1]];
  }
  var lines = [];
  if (reload && C) {
    // A page REFRESH (same session) — one witty beat that acknowledges it, then straight to
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
  var text = function (p) { return zh ? p[1] : p[0]; };
  hdr.classList.add('greet-run');
  function finish() { greet.classList.remove('convo'); hdr.classList.remove('greet-run'); }   // slow CSS crossfade → brand

  if (reduced()) {
    // no typing/animation: show the greeting + one read, briefly, then hand to the brand
    var seq = [lines[0], lines[1] || lines[0]], si = 0;
    (function step() {
      var ln = seq[si]; greet.classList.toggle('convo', !ln.big); tx.textContent = text(ln.s);
      si++; if (si < seq.length) setTimeout(step, 2400); else setTimeout(finish, 2400);
    })();
    return;
  }

  var skip = false;
  function onSkip() { skip = true; }
  ['pointerdown', 'keydown', 'wheel', 'touchstart'].forEach(function (ev) {
    document.addEventListener(ev, onSkip, { passive: true, capture: true });
  });

  var li = 0;
  function playLine() {
    if (skip) return finish();
    var ln = lines[li];
    greet.classList.toggle('convo', !ln.big);
    var full = text(ln.s), i = 0;
    tx.style.opacity = '1';
    (function type() {
      if (skip) return finish();
      tx.textContent = full.slice(0, i);
      if (i <= full.length) {
        var ch = full.charAt(i - 1); i++;
        // pause at breath points in BOTH scripts (、； and full-width ？！ included)
        var d = /[\s，,、；;]/.test(ch) ? 90 : /[.。—？?！!…：]/.test(ch) ? 150 : 26;
        setTimeout(type, d);
      } else {
        var hold = ln.big ? 1150 : Math.min(2600, 1250 + full.length * 12);   // longer remarks land longer
        setTimeout(nextLine, hold);
      }
    })();
  }
  function nextLine() {
    if (skip) return finish();
    li++;
    if (li >= lines.length) { setTimeout(finish, 700); return; }   // last remark held, then dissolve
    tx.style.transition = 'opacity .34s ease'; tx.style.opacity = '0';   // soft fade between remarks
    setTimeout(playLine, 360);
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

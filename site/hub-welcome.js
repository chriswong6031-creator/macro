/* hub-welcome.js — the signed-in hub's opening moment.
 *
 * A name greeting, then a short spoken-aloud read of TODAY's markets in the voice of a
 * brilliant, casual friend who happens to run a hedge fund — a few remarks with pauses,
 * then a slow dissolve back into the MASTERMIND brand.
 *
 * No LLM. Every remark is assembled from the engine data already on the page
 * (#globe-data: per-region regime quadrant, index direction, risk read, breadth) plus
 * light per-visit memory. One idea has many phrasings; topics are mood-gated to the real
 * tape; nothing repeats within a day; repeat visits are recalled and get shorter, fresher
 * reads — so it feels like something that watches the world and remembers you, not a loop.
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

  /* ---- ever-signed-in-before? (greeting flavour) + visits today (recall) --- */
  var everKey = 'mm.hub.welcomed', firstEver = false;
  try { firstEver = !localStorage.getItem(everKey); localStorage.setItem(everKey, '1'); } catch (e) {}
  var d0 = new Date(), today = d0.getFullYear() + '-' + (d0.getMonth() + 1) + '-' + d0.getDate();
  var MEM; try { MEM = JSON.parse(localStorage.getItem('mm.hub.convo') || 'null'); } catch (e) {}
  if (!MEM || MEM.day !== today) MEM = { day: today, visits: 0, seen: [], mids: [] };
  if (!MEM.mids) MEM.mids = [];
  MEM.visits += 1; var visit = MEM.visits;
  function fresh(id) { return MEM.seen.indexOf(id) < 0; }
  function keep(id) { if (MEM.seen.indexOf(id) < 0) MEM.seen.push(id); }
  function save() { try { localStorage.setItem('mm.hub.convo', JSON.stringify(MEM)); } catch (e) {} }

  /* ---- today's market context, read straight off #globe-data -------------- */
  function ctx() {
    var el = document.getElementById('globe-data'); if (!el) return null;
    var d; try { d = JSON.parse(el.textContent); } catch (e) { return null; }
    if (!Array.isArray(d) || !d.length) return null;
    var by = {}; d.forEach(function (m) { by[m.cc] = m; });
    var us = by.US || d[0];
    var chg = d.filter(function (m) { return typeof m.index_chg_pct === 'number' && isFinite(m.index_chg_pct); });
    var up = chg.filter(function (m) { return m.index_chg_pct > 0.05; }).length;
    var down = chg.filter(function (m) { return m.index_chg_pct < -0.05; }).length;
    var stag = d.filter(function (m) { return m.quad === 'q3'; });
    var gold = d.filter(function (m) { return m.quad === 'q1'; });
    var mover = chg.slice().sort(function (a, b) { return Math.abs(b.index_chg_pct) - Math.abs(a.index_chg_pct); })[0] || us;
    var uc = (us && us.index_chg_pct) || 0;
    // NB: the calm q1 risk_text is "calm — low macro stress" — do NOT match bare "stress"
    // (it flagged every calm day risky). Key off the genuinely-elevated words only.
    var risky = /elevat|stagfl|scare|fragile|panic|high —/i.test((us && us.risk_text_en) || '');
    var mood;
    if ((us && us.quad === 'q4') || (risky && uc < -0.8) || down >= chg.length * 0.72) mood = 'off';
    else if ((us && us.quad === 'q3') || risky || uc < -0.4) mood = 'careful';
    else if (us && us.quad === 'q1' && uc > 0.3 && !risky) mood = 'on';
    else if (uc > 0.12 && !risky) mood = 'good';
    else mood = 'mixed';
    return { d: d, us: us, up: up, down: down, total: chg.length, stag: stag, gold: gold, mover: mover, uc: uc, risky: risky, mood: mood };
  }
  var C = ctx();

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
  var EN = {}, ZH = {};
  if (C) {
    var pct = Math.abs(C.uc).toFixed(1);
    var mpct = Math.abs(C.mover.index_chg_pct || 0).toFixed(1);
    var rd = C.us.rdir;
    var twEn = C.us.rtoward_en || (rd === 'improving' ? 'firmer ground' : 'a worse spot');
    var twZh = C.us.rtoward_zh || (rd === 'improving' ? '更稳的位置' : '更差的位置');
    EN = { PCT: pct, DOWN: C.down, UP: C.up, TOTAL: C.total, MOVER: cname(C.mover, 1), MOVERPCT: mpct,
      MOVERDIR: (C.mover.index_chg_pct || 0) >= 0 ? 'up' : 'down', STAG: C.stag.length ? cname(firstNonUS(C.stag), 1) : '', GOLD: C.gold.length ? cname(firstNonUS(C.gold), 1) : '', REGIME: regimeName(C.us, 1), TOWARD: twEn, ASOF: asof(1), V: visit };
    ZH = { PCT: pct, DOWN: C.down, UP: C.up, TOTAL: C.total, MOVER: cname(C.mover, 0), MOVERPCT: mpct,
      MOVERDIR: (C.mover.index_chg_pct || 0) >= 0 ? '涨' : '跌', STAG: C.stag.length ? cname(firstNonUS(C.stag), 0) : '', GOLD: C.gold.length ? cname(firstNonUS(C.gold), 0) : '', REGIME: regimeName(C.us, 0), TOWARD: twZh, ASOF: asof(0), V: visit };
  }
  function fill(s, map) { return s.replace(/\{(\w+)\}/g, function (_, k) { return map[k] != null ? map[k] : ''; }); }

  /* ---- the material. draw() returns a phrasing not used today, slots filled. */
  function draw(poolId, pool) {
    var cands = [], i;
    for (i = 0; i < pool.length; i++) if (fresh(poolId + i)) cands.push(i);
    if (!cands.length) for (i = 0; i < pool.length; i++) cands.push(i);   // all seen → allow reuse
    var idx = pick(cands); keep(poolId + idx);
    var v = pool[idx];
    return [fill(v[0], EN), fill(v[1], ZH)];
  }

  var dir = C ? (C.uc > 0.12 ? 'up' : C.uc < -0.12 ? 'down' : 'flat') : 'flat';
  var quad = (C && C.us && C.us.quad) || '';

  var OPEN = [
    ['Give me ten seconds before you dive in.', '先别急,让我说十秒钟。'],
    ['Quick read while you settle in.', '趁你还没开始,我先说两句。'],
    ["Alright — here's the lay of the land.", '好,先跟你说说今天的大局。'],
    ['Let me set the table for you.', '我先给你把桌子摆好。'],
    ['Two things before you get to work.', '开工之前,先说两件事。'],
    ["Before you touch anything — here's the temperature.", '动手之前——先跟你说说今天的温度。']
  ];
  var VISIT2 = [
    ['Back already? Twice today — I like the appetite.', '这么快又来了?今天第二回,有胃口,我喜欢。'],
    ["Round two. Something out there's got your eye.", '第二趟了。看来有东西勾着你。'],
    ['Twice in one day. Good — pay attention, it pays you back.', '一天两回。挺好——你盯着它,它就回报你。'],
    ["You're back. The tape's not going anywhere, but I'm glad you are.", '你回来了。盘面跑不掉,不过有你在,挺好。']
  ];
  var VISIT3 = [
    ["That's {V} times today. The market's got its hooks in you.", '今天第 {V} 回了。市场这是把你勾住了。'],
    ['{V} visits and counting. Locked in — that’s how it’s done.', '第 {V} 次了。够专注——就该这样。'],
    ["{V} times. You're not here to browse — so I'll be quick.", '第 {V} 次了。你不是来闲逛的——那我快点。'],
    ['You again — {V} today. I’ll skip the small talk.', '又是你——今天第 {V} 回。废话我省了。'],
    ["{V} in a day. Either you're worried or you're hunting. Either way, I'm here.", '一天 {V} 回。要么你在担心,要么你在猎。不管哪样,我都在。']
  ];
  var TAPE = { up: [
      ["Tape's got a bid today. Nothing wild — just green.", '今天盘面有买盘。没什么疯狂的,就是绿。'],
      ["It's a green one — the kind you don't have to fight.", '今天是绿的——那种不用硬扛的绿。'],
      ["Bit of lift out there. I'll take an easy up day.", '外面有点起色。轻松的上涨日,我照单全收。'],
      ['Buyers showed up today. Quiet, steady green.', '今天买家到场了。安静,稳稳的绿。'],
      ["Green on the screens, and it's holding. I like when it holds.", '屏幕上是绿的,而且守得住。守得住,我就喜欢。'],
      ["Up day, and nothing forced about it. That's the good kind.", '上涨日,一点都不勉强。这是好的那种。']
    ], down: [
      ["Tape's heavy today. Nothing broken — just heavy.", '今天盘面偏沉。没出什么事,就是沉。'],
      ["It's red out there. The kind of day you sit on your hands.", '外面一片红。这种日子,手别痒。'],
      ["Down day, thin bids. Don't go chasing anything.", '下跌日,买盘薄。什么都别追。'],
      ['Sellers have the pen today. Let them tire out.', '今天是卖方在写字。等他们累了再说。'],
      ["It's leaking lower — not a crash, just a slow bleed.", '一路往下渗——不是崩,是慢慢失血。'],
      ['Red across the screens. Days like this reward patience, not bravado.', '屏幕上一片红。这种日子奖励耐心,不奖励逞强。']
    ], flat: [
      ["Quiet tape. Everyone's waiting on something.", '盘面很静。大家都在等着什么。'],
      ["Flat and boring — which is honestly fine by me.", '又平又闷——说实话,我挺乐意。'],
      ['Not much doing today. Coiled, not dead.', '今天没什么大动静。是在盘,不是死。'],
      ["Sideways and patient. The market's holding its breath.", '横着,耐着。市场在屏着呼吸。']
    ] };
  // Regime beats are DIRECTION-first, never label-first: the same quad means opposite
  // things depending on whether we're firming into it or rolling out of it — and the
  // confirmed label LAGS the score, so a deteriorating "Goldilocks" is the trap. {REGIME}
  // = current quad, {TOWARD} = where the trajectory is dragging it (from #globe-data rdir).
  var REGD = [   // DETERIORATING — the label still says {REGIME}, but the trend is down
      ["We're still calling it {REGIME} — but it's rolling over. The label lags; the trend's the tell, and it's dragging toward {TOWARD}.", '还挂着{REGIME}的牌子——但它在翻。标签滞后,趋势才是真相,而它正被拖向{TOWARD}。'],
      ["Careful with the {REGIME} tag today — the score's deteriorating, edging toward {TOWARD}. Same word, opposite trade from a month ago.", '今天别太信{REGIME}这个标签——分数在恶化,正滑向{TOWARD}。同一个词,和一个月前反着做。'],
      ["{REGIME} on paper, but it's aging out — momentum's rolling toward {TOWARD}. I'd lean defensive early, not late.", '纸面上是{REGIME},但在老化——动能正倒向{TOWARD}。我会早点偏防守,别等晚了。'],
      ["The backdrop still reads {REGIME}, but it's cracking — {TOWARD} is pulling. Trust the change of rate, not the last print.", '背景还写着{REGIME},但在裂——{TOWARD}在拉。信变化率,别信最后一个读数。']
    ];
  var REGI = [   // IMPROVING — still {REGIME} on the print, but turning UP toward {TOWARD}
      ["Still {REGIME} on the label, but it's turning up — the score's climbing toward {TOWARD}. Early, but the direction's finally right.", '标签还是{REGIME},但在往上翻——分数正爬向{TOWARD}。早,但方向终于对了。'],
      ["{REGIME}'s the print, but the trend's improving — headed for {TOWARD}. This is the good kind of change: bad-to-better.", '读数是{REGIME},但趋势在改善——奔着{TOWARD}去。这是好的那种变化:由坏转好。'],
      ["Don't over-read the {REGIME} tag — it's thawing, momentum's toward {TOWARD}. Getting less bad is how bottoms start.", '别太当真{REGIME}这个标签——在解冻,动能朝着{TOWARD}。越来越不差,正是底部的开始。']
    ];
  var REGSG = [  // STABLE + good quad — genuinely holding
      ["Clean {REGIME}, and it's holding — growth without the heat. Enjoy it while the trend cooperates.", '干净的{REGIME},而且守得住——有增长不发烫。趋势配合的时候,好好享受。'],
      ["{REGIME}, steady — no cracks in the score yet. Rare, so don't waste it.", '{REGIME},很稳——分数还没裂。难得,别浪费。'],
      ["Backdrop's {REGIME} and it isn't going anywhere. The regime's your friend here.", '背景是{REGIME},而且稳着。这里,大局是你的朋友。']
    ];
  var REGSB = [  // STABLE + bad quad — stuck, no thaw
      ["Still stuck in {REGIME}, and it's not letting up. Nothing to force here.", '还困在{REGIME}里,而且没松口。这里没什么可硬来的。'],
      ["{REGIME}, and flat — no thaw in the score yet. Patience beats hope.", '{REGIME},而且平——分数还没解冻。耐心胜过指望。']
    ];
  var RISK = { calm: [
      ["Risk board's quiet. Stress readings low — rare, clean water.", '风险盘面很安静。压力读数低——难得的干净水域。'],
      ["Nothing's flashing red on the risk side. I'll take it.", '风险这边没有红灯在闪。我认。'],
      ['Under the hood, stress is low. The selling’s mood, not machinery.', '底下压力其实不高。今天的卖,是情绪,不是机器出问题。']
    ], hot: [
      ["Risk's lit up. I'd keep the size honest today.", '风险这边亮了。今天仓位放老实点。'],
      ['Stress gauges are climbing. Be a little careful out there.', '压力表在往上爬。外面小心点。'],
      ["The plumbing's tightening. That's the part worth watching.", '底层的管路在收紧。这才是值得盯的部分。']
    ] };
  var REGION = [
    ["China's the odd one out again — running its own cycle. The gap is the trade.", '中国又是那个异类——走自己的周期。这个差距,本身就是机会。'],
    ["{STAG} is boxed in stagflation. I'd leave that one alone for now.", '{STAG} 困在滞胀里。这个,我暂时不碰。'],
    ['{GOLD} is sitting pretty in Goldilocks — quietly one of the cleaner boards.', '{GOLD} 稳稳待在金发女孩区——悄悄地,是更干净的盘面之一。'],
    ["The world's not moving together today — some green, some red. Divergence everywhere.", '今天全球不同步——有绿有红。到处都是分化。']
  ];
  var BREADTH = { down: [
      ["Almost everything's red — {DOWN} of {TOTAL} boards down. Broad, not selective.", '几乎全红——{TOTAL} 个里 {DOWN} 个在跌。是普跌,不是挑着跌。'],
      ['{DOWN} of {TOTAL} markets lower. When it’s this broad, it’s macro, not stock-picking.', '{TOTAL} 个里 {DOWN} 个在跌。这么普遍,是宏观,不是选股。']
    ], up: [
      ["Green nearly across the board — {UP} of {TOTAL} up. Everyone's invited today.", '几乎全绿——{TOTAL} 个里 {UP} 个在涨。今天大家都有份。'],
      ['{UP} of {TOTAL} boards higher. Broad green — the healthy kind of rally.', '{TOTAL} 个里 {UP} 个在涨。普涨——是健康的那种涨。']
    ], split: [
      ["It's split out there — some up, some down. A stock-picker's tape.", '外面是分化的——有涨有跌。挑股票的盘。'],
      ['Half green, half red. Today rewards selection, not direction.', '一半绿一半红。今天奖励选股,不奖励押方向。']
    ] };
  var MOVER = [
    ["The big mover today is {MOVER} — {MOVERDIR} {MOVERPCT}%. That's where the story is.", '今天动静最大的是 {MOVER}——{MOVERDIR}{MOVERPCT}%。故事在那儿。'],
    ['Keep half an eye on {MOVER} — {MOVERPCT}% is a real move, not noise.', '{MOVER} 你留半只眼睛——{MOVERPCT}% 是真动了,不是噪音。'],
    ["Today's outlier is {MOVER}, at {MOVERPCT}%. Outliers are where I start looking.", '今天的异类是 {MOVER},{MOVERPCT}%。异类,是我开始找机会的地方。']
  ];
  var META = [
    ['Desk re-ran the whole world overnight. This is fresh as of {ASOF}.', '台子昨晚把整个世界重算了一遍。这是 {ASOF} 的最新读数。'],
    ["Walked every board this morning. That's the honest read, not the pretty one.", '今早每个盘面我都过了一遍。给你的是实话,不是好听话。'],
    ['The engines check each other before they talk to you. Less noise that way.', '引擎之间先互相核对,才跟你说话。这样噪音少。'],
    ["I don't guess — everything I just said is measured, as of {ASOF}.", '我不猜——我刚说的每一句,都是量出来的,截至 {ASOF}。'],
    ['Nine boards, one read. I did the reconciling so you don’t have to.', '九个盘面,一个结论。对账我做了,你不用。']
  ];
  var NUDGE = { on: [
      ['If you were waiting for a green light, this is about as close as it gets. Within reason.', '你要是在等绿灯,这差不多就是了。别过火。'],
      ['Feels fine to take on a little adventure today. Sensible size.', '今天可以带点冒险出门。仓位放得体面点。'],
      ["Green light, within reason. Days this clean don't come often.", '绿灯,别过火。这么干净的日子不常有。'],
      ['The setup’s clean. Press it a little — just don’t get greedy.', '形态很干净。可以稍微压一压——别贪就行。']
    ], good: [
      ['Constructive out there. Lean in a touch — no heroics.', '外面偏建设性。可以稍微前倾一点——别逞能。'],
      ['Room to be a little brave today. Keep a hand on the wheel.', '今天有空间胆子大一点。手别离方向盘。'],
      ["The wind's mostly at your back. Use it, don't abuse it.", '风大体上是顺的。用它,别滥用它。'],
      ['Decent tape. Add to what’s working, leave the rest.', '盘面不错。给跑得好的加码,其余的别碰。']
    ], mixed: [
      ["Nothing's screaming either way. Let the setups come to you.", '两边都没在喊。让机会自己走过来。'],
      ['Mixed tape — patience beats prediction today.', '盘面混着——今天耐心胜过预测。'],
      ['No clear edge right now. Sit on your best ideas, skip the rest.', '现在没有明显的优势。守住最好的想法,其余的跳过。'],
      ['Choppy. Trade less, watch more.', '震荡。少做,多看。']
    ], careful: [
      ['Careful out there today. Keep the powder dry.', '今天外面小心。子弹留着。'],
      ['Not a day to be a hero. Small, patient, boring.', '今天别逞英雄。小,耐心,无聊。'],
      ['Trim the edges, keep the core. Live to trade tomorrow.', '削掉边角,留住核心。留着,明天再打。'],
      ["If you're unsure, that's the signal. Size down.", '你要是没底,那本身就是信号。仓位缩。'],
      ['Respect the tape today — it’s telling you to slow down.', '今天尊重盘面——它在让你慢下来。'],
      ['Tighten the stops, loosen the grip. Let it breathe.', '把止损收紧,把手放松。让它喘口气。']
    ], off: [
      ['Risk-off tape. Protect the book first, opportunities second.', '避险盘。先护住本金,再谈机会。'],
      ['This is a day to survive, not to swing. Sit tight.', '今天是活下来的日子,不是挥拍的日子。坐稳。'],
      ['Cash is a position too. No shame in holding it today.', '现金也是一种仓位。今天拿着,不丢人。'],
      ["When it's like this, the best trade is often no trade.", '这种时候,最好的交易常常是不交易。'],
      ["Don't try to catch it. Let it find a floor first.", '别去接。等它先找到底再说。'],
      ['On a tape like this, doing nothing is doing something. Wait.', '这种盘,不动本身就是一种动作。等着。']
    ] };
  var CLOSE = [
    ["Anyway — that's the read. Desk's below whenever you are.", '行了——就这些。台子在下面,你随时。'],
    ['That’s the brief. Eyes open, size sensible.', '简报完毕。眼睛睁着,仓位得体。'],
    ['Enough from me. Go make it a good one.', '我就说到这。去,打漂亮点。'],
    ['Alright, the floor’s yours — everything’s below.', '好,交给你了——都在下面。']
  ];

  /* ---- assemble the sequence: greeting + a few reads, tapering on repeat --- */
  var GREET = {
    morning: [['Good morning', '早上好'], ['Morning', '早'], ['Rise and shine', '起来啦'], ['Up early', '起得早啊'], ['Morning to you', '早安']],
    afternoon: [['Good afternoon', '下午好'], ['Afternoon', '午安'], ['Good to see you', '又见面了'], ['Midday, then', '午间好'], ['Afternoon to you', '下午好啊']],
    evening: [['Good evening', '晚上好'], ['Evening', '晚安时分'], ['Good to see you', '又见面了'], ['Evening to you', '晚上好啊'], ['Winding down', '收工时分']],
    late: [['You’re up late', '夜深了'], ['Burning the midnight oil', '还没睡啊'], ['Still at it', '还在忙'], ['Can’t sleep either', '你也睡不着']]
  };
  function greetingLine() {
    var H = d0.getHours(), tod = H < 5 ? 'late' : H < 12 ? 'morning' : H < 18 ? 'afternoon' : H < 23 ? 'evening' : 'late';
    var g = firstEver ? ['Welcome', '欢迎'] : draw('greet.' + tod, GREET[tod]);   // draw() → no repeat in a day
    return [name ? g[0] + ', ' + name : g[0], name ? g[1] + '，' + name : g[1]];
  }
  var lines = [];
  lines.push({ big: true, s: greetingLine() });                       // the name (large)

  if (C) {
    // The regime TREND biases the day's advice, symmetrically — the whole point of this:
    //  • a good regime DETERIORATING is a slow headwind → one notch more cautious even on a
    //    green tape (don't let a lagging "Goldilocks" talk you into risk while it rolls over);
    //  • a bad regime IMPROVING toward a better quad is a tailwind → ease one notch (bad-to-
    //    better is when you lean in early). Direction, not just the last print.
    if (C.us.rdir === 'deteriorating' && (quad === 'q1' || quad === 'q2')) {
      C.mood = { on: 'good', good: 'mixed', mixed: 'careful', careful: 'off', off: 'off' }[C.mood] || C.mood;
    } else if (C.us.rdir === 'improving' && C.us.rtoward_en) {
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
      var rdir = C.us.rdir || 'stable', goodQ = (quad === 'q1' || quad === 'q2'), turning = (rdir === 'deteriorating' || rdir === 'improving');
      var rgm = rdir === 'deteriorating' ? ['regime.det', REGD] : rdir === 'improving' ? ['regime.imp', REGI] : goodQ ? ['regime.sg', REGSG] : ['regime.sb', REGSB];
      if (turning) mids.push(rgm);   // a regime that's TURNING is the headline — surface it first
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
        var d = (ch === ' ' || ch === '，' || ch === ',') ? 90 : (ch === '.' || ch === '。' || ch === '—' || ch === '?' || ch === '!') ? 150 : 26;
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

/* ═══════════════════════════════════════════════════════════════════════════
   Research Vault — client app (defer-loaded; DOMContentLoaded-wrapped).
   Hydrates from the SSR-baked #rv-catalog JSON, refreshes from the live API,
   and drives the feed / lanes / browse tree / facets / search / PDF viewer.

   Auth: reuses the site's Supabase Bearer helper (window.MDXAuth) — the same
   flow site/mm_brain.js uses — to call the gated /api/research/* routes.
   Read-state, saved, and resume-to-page are localStorage (swappable module).
   pdf.js is vendored same-origin (GFW: no CDN) and loaded via dynamic import.
   ═════════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (window.__rvApp) return; window.__rvApp = true;

  /* ── config ── */
  // Same-origin API base. This page ships from www/apex mastermind-x.com, whose
  // Caddy proxies /api/* -> macro-api (:8000). The global window.MM_API points at
  // app.* (the Next.js Terminal), which has NO /api/research/* route (404) — so
  // research calls must stay same-origin. Override via window.RV_API if ever split.
  var API = (window.RV_API || '').replace(/\/$/, '');
  var PDFJS_SRC = 'vendor/pdfjs/pdf.min.mjs';
  var PDFJS_WORKER = 'vendor/pdfjs/pdf.worker.min.mjs';
  var LS_STATE = 'rv_docstate_v1';   // { id: {saved, read_at, last_page} }
  var $ = function (id) { return document.getElementById(id); };
  var doc = document;

  /* ── i18n (mirrors the site l-en/l-zh idiom) ── */
  function zh() { return doc.documentElement.getAttribute('data-lang') === 'zh'; }
  function T(en, cn) { return zh() ? cn : en; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  /* ── SVG glyphs ── */
  var CAL_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>';
  var STAR_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6 4.6 2.3 7.4-6.3-4.6L5.7 21l2.3-7.4-6-4.6h7.6z"/></svg>';
  var CHEV_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';
  var VIEW_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>';
  var DL_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5M12 15V3"/></svg>';
  var BOOK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>';
  var LOCK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';

  var _MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  /* ── local doc-state module (localStorage; swappable for a server sync later) ── */
  var DocState = {
    _all: function () { try { return JSON.parse(localStorage.getItem(LS_STATE) || '{}') || {}; } catch (e) { return {}; } },
    _save: function (o) { try { localStorage.setItem(LS_STATE, JSON.stringify(o)); } catch (e) {} },
    get: function (id) { return this._all()[id] || {}; },
    isSaved: function (id) { return !!this.get(id).saved; },
    isRead: function (id) { return !!this.get(id).read_at; },
    lastPage: function (id) { return this.get(id).last_page || 1; },
    toggleSaved: function (id) { var o = this._all(); o[id] = o[id] || {}; o[id].saved = !o[id].saved; this._save(o); return !!o[id].saved; },
    markRead: function (id) { var o = this._all(); o[id] = o[id] || {}; if (!o[id].read_at) { o[id].read_at = new Date().toISOString(); this._save(o); } },
    setLastPage: function (id, p) { var o = this._all(); o[id] = o[id] || {}; o[id].last_page = p; this._save(o); }
  };

  /* ── catalog state ── */
  var ITEMS = [];            // normalized catalog items (see normItem)
  var LANE = 'latest';
  var FILT = { inst: '', side: '', theme: '', q: '' };
  var SEARCH_HITS = null;    // set of ids from the live search API, or null (no server search)
  // Teaser gate: reading the full PDFs is Pro-only; non-Pro see the latest few
  // summaries and an upgrade wall over the rest. Summaries are public (the catalog
  // API is unauth), so this is a MARKETING wall, not security — it fails OPEN to
  // the full list while the tier is unresolved (null). PDF viewing is server-gated.
  var USER_TIER = null;      // 'anon' | 'free' | 'insider' | 'pro' | null (unresolved)
  function feedUnlocked() { return USER_TIER === null || USER_TIER === 'pro'; }
  // Non-Pro summary allowance: Insider reads the latest 3, Free/anon the latest 1.
  function teaseCount() { return USER_TIER === 'insider' ? 3 : 1; }
  // Top Picks is a Pro-only lane; a resolved non-Pro tier is sent to the upgrade panel.
  function picksLocked() { return USER_TIER !== null && USER_TIER !== 'pro'; }

  function normItem(x) {
    x = x || {};
    var pub = x.published_at || '';
    var date = (pub.split('T')[0]) || '';
    return {
      id: x.id || '',
      inst: (x.institution || '').trim() || 'Unknown',
      logo: logoFor(x.institution),
      desk: x.desk || '',
      side: (x.side || 'independent').toLowerCase(),
      date: date,
      at: pub,
      month: date.slice(0, 7),
      pages: x.pages || 0,
      top: !!x.top_pick,
      needs: !!x.needs_metadata,
      title: x.title || '',
      points: Array.isArray(x.summary_points) ? x.summary_points : [],
      tags: Array.isArray(x.tags) ? x.tags : [],
      tickers: Array.isArray(x.tickers) ? x.tickers : []
    };
  }
  function logoFor(inst) {
    inst = (inst || '').trim();
    if (!inst || inst === 'Unknown') return '?';
    var parts = inst.split(/[\s.]+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  function thisWeekIso() {
    var d = new Date(); d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  }
  function isThisWeek(x) { return x.date && x.date >= thisWeekIso(); }

  /* side stamp */
  function stampLabel(side) { return side === 'buy' ? T('BUY', '看多') : (side === 'sell' ? T('SELL', '看空') : T('IND', '独立')); }
  function stampClass(side) { return side === 'buy' ? 'buy' : (side === 'sell' ? 'sell' : 'indep'); }
  function fmtDate(d) {
    if (!d) return T('date pending', '日期待定');
    var p = d.split('-');
    if (p.length < 3) return d;
    if (zh()) return p[0] + '年' + (+p[1]) + '月' + (+p[2]) + '日';
    return _MON[+p[1] - 1] + ' ' + (+p[2]) + ', ' + p[0];
  }
  // Publish time from published_at (the desk's source time), shown in UTC and
  // labeled — identical in SSR and hydrated views, and consistent with the UTC
  // date the tree / "this week" already use. A split US+China audience has no one
  // local tz, so UTC is the neutral, unambiguous default (no per-tz date drift).
  function fmtWhen(iso, dateOnly) {
    var hasT = iso && iso.indexOf('T') > -1;
    var d = (hasT ? iso.split('T')[0] : '') || dateOnly || '';
    var t = '';
    if (hasT) {
      var hm = iso.split('T')[1].slice(0, 5);
      if (/^\d\d:\d\d$/.test(hm)) t = ' · ' + hm + ' UTC';
    }
    return fmtDate(d) + t;
  }

  /* ── ticker dossier deep-link: the site routes tickers to the Terminal.
       (No same-origin /stocks/<T> dossier route exists; the search box in the
       nav resolves tickers, and the Terminal is the canonical dossier host.) ── */
  function tickerHref(tk) {
    tk = (tk || '').trim(); if (!tk) return '';
    // Only link plain equity-style symbols; skip rate/fx codes with spaces/dots.
    if (!/^[A-Z][A-Z0-9.\-]{0,7}$/.test(tk)) return '';
    return 'https://app.mastermind-x.com/terminal?sym=' + encodeURIComponent(tk);
  }

  /* ═══════════ hero counts (client-side, descriptive only) ═══════════ */
  function updateHero() {
    var wk = ITEMS.filter(isThisWeek);
    var newN = wk.length;
    var desks = {}; wk.forEach(function (x) { if (x.inst && x.inst !== 'Unknown') desks[x.inst] = 1; });
    var deskN = Object.keys(desks).length;
    // most-covered theme this week (falls back to all-time if none this week)
    var pool = wk.length ? wk : ITEMS;
    var tc = {}; pool.forEach(function (x) { x.tags.forEach(function (t) { tc[t] = (tc[t] || 0) + 1; }); });
    var topTheme = ''; var best = 0;
    Object.keys(tc).forEach(function (k) { if (tc[k] > best) { best = tc[k]; topTheme = k; } });

    $('fig-new').textContent = newN;
    $('fig-desks').textContent = deskN;
    $('fig-theme').textContent = topTheme || T('—', '—');
    $('fig-total').textContent = ITEMS.length;
    buildWeb();

    // verdict lead line
    var picks = ITEMS.filter(function (x) { return x.top; }).length;
    if (ITEMS.length) {
      $('v-en-lead').textContent = newN + ' new institutional report' + (newN === 1 ? '' : 's') + ' this week · ' + picks + ' highlighted · ' + deskN + ' desk' + (deskN === 1 ? '' : 's') + ' publishing.';
      $('v-zh-lead').textContent = '本周新增 ' + newN + ' 篇机构研报 · ' + picks + ' 篇精选 · ' + deskN + ' 家研究部门在发。';
    }
  }

  /* ═══════════ signature: THE DESK CONSTELLATION (neural web of desks) ═══════════
     One node per institution in the vault, placed on a golden-angle (phyllotaxis)
     spiral so the web stays even and un-crowded from a handful of desks to 40+.
     Nearest-desk strands weave the web; a spotlight cycles the roster one name at a
     time (held while a node is hovered); a signal mote glides between desks on each
     tick. Purely descriptive — who publishes into the vault, never a market call. */
  var SVGNS = 'http://www.w3.org/2000/svg';
  var WEB = { timer: null, cur: -1, hover: false, reduce: false, nodes: [], threads: [], pos: [] };

  function deskMono(name) {
    var parts = String(name || '').replace(/[.,]/g, ' ').split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase();
  }

  function buildWeb() {
    var gNodes = $('rvwNodes'), gThreads = $('rvwThreads'), gMotes = $('rvwMotes');
    if (!gNodes || !gThreads) return;

    // roster: institutions by report count, most-published first (→ nearer centre)
    var counts = {};
    ITEMS.forEach(function (x) { var n = x.inst; if (n && n !== 'Unknown') counts[n] = (counts[n] || 0) + 1; });
    var roster = Object.keys(counts).map(function (n) { return { name: n, count: counts[n] }; })
      .sort(function (a, b) { return b.count - a.count || a.name.localeCompare(b.name); });
    var N = roster.length;
    if ($('web-n')) $('web-n').textContent = N;

    if (WEB.timer) { clearInterval(WEB.timer); WEB.timer = null; }
    WEB.cur = -1; WEB.hover = false;
    WEB.reduce = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

    if (!N) {  // honest empty state — one quiet, unlit core (no fake desks)
      gThreads.innerHTML = ''; if (gMotes) gMotes.innerHTML = '';
      gNodes.innerHTML = '<circle cx="170" cy="95" r="4" fill="var(--rv)" opacity="0.32"/>';
      if ($('web-sname')) $('web-sname').textContent = T('Coming online…', '正在接入…');
      WEB.nodes = []; return;
    }

    // golden-angle spiral inside an ellipse (viewBox 340×190)
    var CX = 170, CY = 95, RX = 142, RY = 76, GOLD = 2.399963229728653;
    var pos = roster.map(function (d, i) {
      var t = Math.sqrt((i + 0.5) / N), a = i * GOLD;
      return { x: CX + Math.cos(a) * t * RX, y: CY + Math.sin(a) * t * RY,
               r: Math.max(3, Math.min(6.5, 3 + Math.sqrt(d.count))), name: d.name, count: d.count };
    });

    // strands: each desk → its K nearest desks — a peer-to-peer web (no star hub),
    // denser for a small roster so a handful of desks still reads as a web.
    var strands = [], seen = {}, K = N <= 12 ? 3 : 2;
    pos.forEach(function (p, i) {
      var near = pos.map(function (q, j) { return { j: j, dd: (q.x - p.x) * (q.x - p.x) + (q.y - p.y) * (q.y - p.y) }; })
        .filter(function (o) { return o.j !== i; }).sort(function (a, b) { return a.dd - b.dd; });
      for (var m = 0; m < Math.min(K, near.length); m++) {
        var a = Math.min(i, near[m].j), b = Math.max(i, near[m].j), key = a + '_' + b;
        if (!seen[key]) { seen[key] = 1; strands.push([a, b]); }
      }
    });

    var reduce = WEB.reduce, en = reduce ? '' : ' enter';
    var th = '';
    strands.forEach(function (s, idx) {
      var a = pos[s[0]], b = pos[s[1]];
      th += '<line class="thread web' + en + '" data-a="' + s[0] + '" data-b="' + s[1]
        + '" x1="' + a.x.toFixed(1) + '" y1="' + a.y.toFixed(1) + '" x2="' + b.x.toFixed(1) + '" y2="' + b.y.toFixed(1)
        + '" stroke-width="1" style="animation-delay:' + (idx * 0.025).toFixed(2) + 's"/>';
    });
    gThreads.innerHTML = th;

    // nodes: glow + dot + (on-spotlight) monogram, with an accessible <title>
    var nn = '';
    pos.forEach(function (p, i) {
      nn += '<g class="rv-web-node' + en + '" data-i="' + i + '" style="animation-delay:' + (i * 0.045).toFixed(2) + 's">'
        + '<title>' + esc(p.name) + (p.count ? ' · ' + p.count + (p.count === 1 ? ' report' : ' reports') : '') + '</title>'
        + '<circle class="glow" cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + (p.r * 3).toFixed(1) + '"/>'
        + '<circle class="dot" cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + p.r.toFixed(1) + '"/>'
        + '<text class="mono" x="' + p.x.toFixed(1) + '" y="' + p.y.toFixed(1) + '" dy="0.34em" font-size="'
        + (p.r * 1.18).toFixed(1) + '">' + esc(deskMono(p.name)) + '</text>'
        + '</g>';
    });
    gNodes.innerHTML = nn;
    if (gMotes) gMotes.innerHTML = '';

    WEB.pos = pos;
    WEB.nodes = Array.prototype.slice.call(gNodes.querySelectorAll('.rv-web-node'));
    WEB.threads = Array.prototype.slice.call(gThreads.querySelectorAll('.thread'));

    // hover holds a desk lit + names it; leaving resumes the cycle
    WEB.nodes.forEach(function (g, i) {
      g.addEventListener('mouseenter', function () { WEB.hover = true; lightDesk(i); });
      g.addEventListener('mouseleave', function () { WEB.hover = false; });
    });

    lightDesk(0);
    if (!reduce && N > 1) {
      WEB.timer = setInterval(function () {
        if (WEB.hover || (document.hidden)) return;
        lightDesk((WEB.cur + 1) % WEB.nodes.length);
      }, 2600);
    }
  }

  function lightDesk(i) {
    if (i < 0 || i >= WEB.nodes.length || i === WEB.cur) return;
    WEB.cur = i;
    WEB.nodes.forEach(function (g, j) { g.classList.toggle('on', j === i); });
    WEB.threads.forEach(function (t) {
      var lit = t.getAttribute('data-a') == i || t.getAttribute('data-b') == i;
      t.classList.toggle('lit', lit);
    });
    var sn = $('web-sname'), p = WEB.pos[i];
    if (sn && p) {
      sn.classList.add('swap');
      setTimeout(function () { if (WEB.cur === i) { sn.textContent = p.name; sn.classList.remove('swap'); } }, 175);
    }
    if (!WEB.reduce) fireMote(i);
  }

  /* a signal mote gliding from desk i to a neighbouring desk (SMIL animateMotion) */
  function fireMote(i) {
    var host = $('rvwMotes'); if (!host || !WEB.pos[i]) return;
    var strand = null;
    for (var k = 0; k < WEB.threads.length; k++) {
      var t = WEB.threads[k];
      if (t.classList.contains('web') && (t.getAttribute('data-a') == i || t.getAttribute('data-b') == i)) { strand = t; break; }
    }
    if (!strand) return;
    var p = WEB.pos[i];
    var x1 = +strand.getAttribute('x1'), y1 = +strand.getAttribute('y1');
    var x2 = +strand.getAttribute('x2'), y2 = +strand.getAttribute('y2');
    var fromA = Math.abs(x1 - p.x) < 0.7 && Math.abs(y1 - p.y) < 0.7;
    var sx = fromA ? x1 : x2, sy = fromA ? y1 : y2, ex = fromA ? x2 : x1, ey = fromA ? y2 : y1;
    var m = document.createElementNS(SVGNS, 'circle');
    m.setAttribute('class', 'mote'); m.setAttribute('r', '2.1');
    var mo = document.createElementNS(SVGNS, 'animateMotion');
    mo.setAttribute('dur', '0.95s'); mo.setAttribute('fill', 'freeze'); mo.setAttribute('calcMode', 'spline');
    mo.setAttribute('keyTimes', '0;1'); mo.setAttribute('keySplines', '0.4 0 0.2 1');
    mo.setAttribute('path', 'M' + sx.toFixed(1) + ',' + sy.toFixed(1) + ' L' + ex.toFixed(1) + ',' + ey.toFixed(1));
    m.appendChild(mo); host.appendChild(m);
    setTimeout(function () { if (m.parentNode) m.parentNode.removeChild(m); }, 1000);
  }

  /* ═══════════ browse tree: year → month → day → institution ═══════════ */
  function buildTree() {
    var byMonth = {};
    ITEMS.forEach(function (x) {
      if (!x.date) return;
      var p = x.date.split('-'); var mk = p[0] + '-' + p[1];
      byMonth[mk] = byMonth[mk] || { days: {}, n: 0 }; byMonth[mk].n++;
      byMonth[mk].days[x.date] = byMonth[mk].days[x.date] || []; byMonth[mk].days[x.date].push(x);
    });
    var moZh = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
    var mkeys = Object.keys(byMonth).sort().reverse();
    if (!mkeys.length) { $('tree').innerHTML = '<li style="padding:8px;color:var(--muted);font-size:12.5px">' + T('Nothing to browse yet.', '暂无可浏览内容。') + '</li>'; return; }
    var years = {}; mkeys.forEach(function (mk) { var y = mk.split('-')[0]; years[y] = (years[y] || 0) + byMonth[mk].n; });
    var html = '';
    Object.keys(years).sort().reverse().forEach(function (yr, yi) {
      html += '<li class="rv-node' + (yi === 0 ? ' open' : '') + '"><button class="rv-tw" data-toggle="1">' + caret() + '<span class="lbl">' + yr + '</span><span class="cn">' + years[yr] + '</span></button><ul class="rv-children">';
      mkeys.filter(function (mk) { return mk.split('-')[0] === yr; }).forEach(function (mk, mi) {
        var mp = mk.split('-');
        html += '<li class="rv-node' + (yi === 0 && mi === 0 ? ' open' : '') + '"><button class="rv-tw" data-toggle="1">' + caret()
          + '<span class="lbl"><span class="l-en">' + esc(_MON[+mp[1] - 1] + ' ' + mp[0]) + '</span><span class="l-zh">' + esc(mp[0] + '年' + moZh[+mp[1] - 1]) + '</span></span><span class="cn">' + byMonth[mk].n + '</span></button><ul class="rv-children">';
        Object.keys(byMonth[mk].days).sort().reverse().forEach(function (dk, di) {
          var dp = dk.split('-'); var insts = byMonth[mk].days[dk];
          html += '<li class="rv-node' + (yi === 0 && mi === 0 && di === 0 ? ' open' : '') + '"><button class="rv-tw" data-toggle="1">' + caret()
            + '<span class="lbl"><span class="l-en">' + esc(_MON[+dp[1] - 1] + ' ' + (+dp[2])) + '</span><span class="l-zh">' + esc((+dp[1]) + '月' + (+dp[2]) + '日') + '</span></span><span class="cn">' + insts.length + '</span></button><ul class="rv-children">';
          var seen = {};
          insts.forEach(function (x) {
            if (seen[x.inst]) return; seen[x.inst] = 1;
            html += '<li class="rv-leaf"><button class="rv-tw" data-inst="' + esc(x.inst) + '"><span class="dotinst"></span><span class="lbl">' + esc(x.inst) + '</span></button></li>';
          });
          html += '</ul></li>';
        });
        html += '</ul></li>';
      });
      html += '</ul></li>';
    });
    $('tree').innerHTML = html;
  }
  function caret() { return '<svg class="caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>'; }

  function pickTreeInst(inst) {
    FILT.inst = inst;
    doc.querySelectorAll('#tree .rv-tw').forEach(function (b) { b.classList.toggle('sel', b.getAttribute('data-inst') === inst); });
    syncFacetActive('inst', inst);
    ensureInstFacet(inst);
    closeDrawer(); renderFeed();
  }

  /* ═══════════ facets (institution list is data-driven) ═══════════ */
  function buildInstFacets() {
    var grp = doc.querySelector('.facet-grp[data-dim="inst"]');
    if (!grp) return;
    // keep the "All" button; rebuild the rest from the catalog institutions (top 6 by count)
    grp.querySelectorAll('.aff:not([data-v=""])').forEach(function (b) { b.remove(); });
    var counts = {}; ITEMS.forEach(function (x) { if (x.inst && x.inst !== 'Unknown') counts[x.inst] = (counts[x.inst] || 0) + 1; });
    Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).slice(0, 6).forEach(function (inst) {
      var b = doc.createElement('button'); b.className = 'aff'; b.setAttribute('data-f', 'inst'); b.setAttribute('data-v', inst); b.textContent = inst;
      grp.appendChild(b);
    });
    syncFacetActive('inst', FILT.inst);
  }
  function ensureInstFacet(inst) {
    var grp = doc.querySelector('.facet-grp[data-dim="inst"]'); if (!grp) return;
    if (inst && !grp.querySelector('.aff[data-v="' + cssEsc(inst) + '"]')) {
      var b = doc.createElement('button'); b.className = 'aff active'; b.setAttribute('data-f', 'inst'); b.setAttribute('data-v', inst); b.textContent = inst;
      grp.appendChild(b);
    }
    syncFacetActive('inst', inst);
  }
  function buildThemeFacets() {
    var grp = doc.querySelector('.facet-grp[data-dim="theme"]'); if (!grp) return;
    grp.querySelectorAll('.aff:not([data-v=""])').forEach(function (b) { b.remove(); });
    var counts = {}; ITEMS.forEach(function (x) { x.tags.forEach(function (t) { counts[t] = (counts[t] || 0) + 1; }); });
    Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).slice(0, 5).forEach(function (th) {
      var b = doc.createElement('button'); b.className = 'aff'; b.setAttribute('data-f', 'theme'); b.setAttribute('data-v', th); b.textContent = th;
      grp.appendChild(b);
    });
    syncFacetActive('theme', FILT.theme);
  }
  function cssEsc(s) { return String(s).replace(/["\\]/g, '\\$&'); }
  function syncFacetActive(dim, val) {
    doc.querySelectorAll('.aff[data-f="' + dim + '"]').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-v') === val); });
  }

  /* ═══════════ lanes ═══════════ */
  function setLane(lane) {
    LANE = lane;
    doc.querySelectorAll('.rv-lane').forEach(function (b) { var on = b.getAttribute('data-lane') === lane; b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); });
    $('picks-hd').style.display = lane === 'picks' ? 'flex' : 'none';
    renderFeed();
  }
  function laneMatch(x) {
    if (LANE === 'picks') return x.top;
    if (LANE === 'saved') return DocState.isSaved(x.id);
    return true;
  }

  /* ═══════════ feed ═══════════ */
  function matchItem(x) {
    if (!laneMatch(x)) return false;
    if (FILT.inst && x.inst !== FILT.inst) return false;
    if (FILT.side && x.side !== FILT.side) return false;
    if (FILT.theme && x.tags.indexOf(FILT.theme) < 0) return false;
    if (FILT.q) {
      // when the server search has resolved, restrict to its hit ids; otherwise
      // fall back to a client-side substring over the baked fields (instant).
      if (SEARCH_HITS) return SEARCH_HITS[x.id];
      var hay = (x.title + ' ' + x.inst + ' ' + x.desk + ' ' + x.points.join(' ') + ' ' + x.tags.join(' ') + ' ' + x.tickers.join(' ')).toLowerCase();
      if (hay.indexOf(FILT.q.toLowerCase()) < 0) return false;
    }
    return true;
  }
  function renderFeed() {
    var rows = ITEMS.filter(matchItem);
    var feed = $('feed');
    var picksGate = LANE === 'picks' && picksLocked();
    if (!ITEMS.length) {
      feed.innerHTML = emptyState(
        T('Institutional research is being onboarded', '机构研报正在接入'),
        T('New buy-side and sell-side desk reports arrive hourly — check back shortly.', '买方与卖方研究每小时更新 —— 请稍后再来查看。'));
    } else if (picksGate) {
      feed.innerHTML = picksUpgradePanel();          // Top Picks is Pro-only
    } else if (!rows.length) {
      var savedLane = LANE === 'saved';
      feed.innerHTML = emptyState(
        savedLane ? T('Nothing saved yet', '还没有收藏') : T('No reports match', '没有匹配的研报'),
        savedLane ? T('Tap the bookmark on any report to keep it here for later.', '点击任意报告上的书签，即可收藏到此处。')
          : T('Try clearing a filter or widening your search.', '试试清除筛选或放宽搜索条件。'));
    } else if (feedUnlocked()) {
      feed.innerHTML = rows.map(cardHTML).join('');
    } else {
      // non-Pro: the latest N summaries readable (Insider 3 / Free 1), then a wall
      var n = teaseCount();
      var html = rows.slice(0, n).map(cardHTML).join('');
      var locked = rows.slice(n);
      if (locked.length) html += lockedTeaser(locked);
      feed.innerHTML = html;
    }
    $('cnt-n').textContent = picksGate ? 0 : (feedUnlocked() ? rows.length : Math.min(teaseCount(), rows.length));
    $('cnt-t').textContent = ITEMS.filter(laneMatch).length;
    renderActiveChips();
  }
  function emptyState(h, p) {
    return '<div class="rv-empty glass">' + BOOK_SVG + '<h3>' + esc(h) + '</h3><p>' + esc(p) + '</p></div>';
  }
  // The non-Pro upgrade wall: a few blurred ghost cards behind a glass upgrade
  // card. Ghosts are decorative (aria-hidden, no data-id) so the feed click
  // handler can never open them, and pointer-events are killed in CSS.
  function lockedTeaser(locked) {
    var ghosts = locked.slice(0, 3).map(function (x) {
      var pts = (x.points || []).slice(0, 2).map(function (p) { return '<li>' + esc(p) + '</li>'; }).join('');
      return '<article class="rep glass" aria-hidden="true">'
        + '<div class="rep-top"><span class="rep-logo">' + esc(x.logo) + '</span>'
        + '<span class="rep-inst">' + esc(x.inst) + '</span>'
        + (x.desk ? '<span class="rep-sep">·</span><span class="rep-desk">' + esc(x.desk) + '</span>' : '')
        + '</div><h3>' + esc(x.title) + '</h3><ul class="rep-points">' + pts + '</ul></article>';
    }).join('');
    var n = locked.length;
    var head = zh() ? ('还有 ' + n + ' 篇机构研报') : (n + ' more institutional report' + (n === 1 ? '' : 's'));
    var body = USER_TIER === 'insider'
      ? T('You’re reading the latest three. Upgrade to Pro to open every desk and read the full PDFs.',
          '你正在阅读最新三篇。升级 Pro 即可查看全部机构研报并阅读 PDF 全文。')
      : T('You’re reading the latest report. Upgrade to Pro to open every desk and read the full PDFs.',
          '你正在阅读最新一篇。升级 Pro 即可查看全部机构研报并阅读 PDF 全文。');
    return '<div class="rv-lockwrap">'
      + '<div class="rv-lockghosts">' + ghosts + '</div>'
      + '<div class="rv-lockover glass">' + LOCK_SVG
      + '<h3>' + esc(head) + '</h3><p>' + esc(body) + '</p>'
      + '<a class="btn upgrade" href="plans.html">' + T('Upgrade to Pro', '升级 Pro') + '</a>'
      + '</div></div>';
  }
  // Top Picks lane for non-Pro: a full-panel upgrade prompt (no summaries shown).
  function picksUpgradePanel() {
    var head = T('Top Picks is a Pro feature', '精选研报为 Pro 专享');
    var body = T('Each week our desk highlights the strongest research. Upgrade to Pro to read every Top Pick and open the full PDFs.',
                 '我们每周精选论证最扎实的研报。升级 Pro 即可阅读全部精选并查看 PDF 全文。');
    return '<div class="rv-empty rv-gate glass">' + STAR_SVG
      + '<h3>' + esc(head) + '</h3><p>' + esc(body) + '</p>'
      + '<a class="btn upgrade" href="plans.html" style="margin-top:16px">' + T('Upgrade to Pro', '升级 Pro') + '</a>'
      + '</div>';
  }
  function cardHTML(x) {
    var pts = x.points, hasPts = pts.length > 0;
    var visible = pts.slice(0, 2), extra = pts.slice(2), ptsHtml;
    if (!hasPts) {
      ptsHtml = '<ul class="rep-points pend"><li>' + T('Summary pending — full report available to read.', '摘要生成中 —— 全文已可查看。') + '</li></ul>';
    } else {
      ptsHtml = '<ul class="rep-points">'
        + visible.map(function (p) { return '<li>' + esc(p) + '</li>'; }).join('')
        + extra.map(function (p) { return '<li class="extra">' + esc(p) + '</li>'; }).join('') + '</ul>';
    }
    var moreBtn = extra.length ? '<button class="rep-more" data-act="morepts">' + CHEV_SVG + '<span>' + T('+' + extra.length + ' more points', '再看 ' + extra.length + ' 点') + '</span></button>' : '';
    var deskBits = x.desk ? '<span class="rep-sep">·</span><span class="rep-desk">' + esc(x.desk) + '</span>'
      : (x.needs ? '<span class="rep-sep">·</span><span class="backfill">' + T('institution to be confirmed', '机构待确认') + '</span>' : '');
    var pinBadge = x.top ? '<span class="rep-pin">' + STAR_SVG + T('Highlighted', '精选') + '</span>' : '';
    var saved = DocState.isSaved(x.id), read = DocState.isRead(x.id);
    var tickerHtml = x.tickers.slice(0, 3).map(function (tk) {
      var href = tickerHref(tk);
      return href ? '<a class="rep-ticker" href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(tk) + '</a>' : '<span class="rep-ticker">' + esc(tk) + '</span>';
    }).join('');
    return '<article class="rep glass' + (x.top ? ' pick' : '') + (x.needs ? ' needs' : '') + (read ? ' read' : '') + '" data-id="' + esc(x.id) + '">'
      + '<div class="rep-top">'
        + '<span class="rep-logo">' + esc(x.logo) + '</span>'
        + '<span class="rep-unread" aria-hidden="true"></span>'
        + '<span class="rep-inst">' + esc(x.inst) + '</span>' + deskBits
        + '<span class="stamp ' + stampClass(x.side) + '"><span class="dt"></span>' + stampLabel(x.side) + '</span>' + pinBadge
        + '<button class="rep-savebtn' + (saved ? ' on' : '') + '" aria-pressed="' + (saved ? 'true' : 'false') + '" aria-label="' + T('Save report', '收藏报告') + '" data-act="save">' + BOOK_SVG + '</button>'
      + '</div>'
      + '<h3>' + esc(x.title) + '</h3>'
      + ptsHtml + moreBtn
      + '<div class="rep-foot"><div class="rep-meta">'
        + '<span class="rep-date">' + CAL_SVG + esc(fmtWhen(x.at, x.date)) + '</span>'
        + '<span class="rep-tags">' + x.tags.map(function (t) { return '<span class="rep-tag">' + esc(t) + '</span>'; }).join('') + tickerHtml + '</span></div>'
        + '<div class="rep-acts">'
          + '<button class="btn ghost" data-act="view">' + VIEW_SVG + T('View', '查看') + '</button>'
          + '<button class="btn primary" data-act="view">' + DL_SVG + T('Open', '打开') + '</button>'
        + '</div></div>'
      + '</article>';
  }

  /* active-filter chips */
  function labelFor(dim, val) {
    if (dim === 'side') return val === 'buy' ? T('Buy-side', '看多') : (val === 'sell' ? T('Sell-side', '看空') : T('Independent', '独立'));
    return val;
  }
  function renderActiveChips() {
    var host = $('active-chips'), chips = [];
    ['inst', 'side', 'theme'].forEach(function (dim) {
      if (FILT[dim]) chips.push('<span class="chiptag">' + esc(labelFor(dim, FILT[dim])) + '<button aria-label="' + T('Remove', '移除') + '" data-clear="' + dim + '">&times;</button></span>');
    });
    if (FILT.q) chips.push('<span class="chiptag">“' + esc(FILT.q) + '”<button aria-label="' + T('Remove', '移除') + '" data-clear="q">&times;</button></span>');
    if (chips.length) chips.push('<button class="rv-clear" data-clear="all">' + T('Clear all', '清除全部') + '</button>');
    host.innerHTML = chips.join('');
  }

  /* ═══════════ live search (debounced → /api/research/search) ═══════════ */
  var _searchTimer = null;
  function onSearchInput() {
    FILT.q = $('q').value.trim();
    SEARCH_HITS = null;              // fall back to instant client match while the server call is in flight
    renderFeed();
    clearTimeout(_searchTimer);
    if (!FILT.q) return;
    var q = FILT.q;
    _searchTimer = setTimeout(function () {
      var url = API + '/api/research/search?q=' + encodeURIComponent(q)
        + (FILT.inst ? '&institution=' + encodeURIComponent(FILT.inst) : '');
      fetch(url, { credentials: 'include' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          if (!j || FILT.q !== q) return;      // stale response
          var hits = {}; (j.items || []).forEach(function (it) { if (it && it.id) hits[it.id] = 1; });
          SEARCH_HITS = hits; renderFeed();
        })
        .catch(function () { /* keep the client-side fallback result */ });
    }, 280);
  }

  /* ═══════════ mobile browse drawer ═══════════ */
  function openDrawer() { $('rail').classList.add('drawer-open'); $('scrim').classList.add('on'); }
  function closeDrawer() { $('rail').classList.remove('drawer-open'); $('scrim').classList.remove('on'); }

  /* ═══════════════════════════════════════════════════════════════════════
     PDF VIEWER — auth-gated pdf.js render + quota-metered download.
     ═══════════════════════════════════════════════════════════════════════ */
  var _pdfLib = null, _pdfLoad = null;
  var V = { item: null, pdf: null, page: 1, pages: 0, zoom: 1.0, invert: false, renderTok: 0, lastFocus: null };

  function loadPdfLib() {
    if (_pdfLib) return Promise.resolve(_pdfLib);
    if (_pdfLoad) return _pdfLoad;
    // dynamic ESM import of the vendored, same-origin pdf.js (no CDN / GFW-safe)
    _pdfLoad = import(new URL(PDFJS_SRC, doc.baseURI).href).then(function (mod) {
      var lib = mod && (mod.pdfjsLib || mod);
      if (lib.GlobalWorkerOptions) lib.GlobalWorkerOptions.workerSrc = new URL(PDFJS_WORKER, doc.baseURI).href;
      _pdfLib = lib; return lib;
    });
    return _pdfLoad;
  }

  /* Supabase Bearer — the exact helper site/mm_brain.js uses. */
  function withAuth(h) {
    h = h || {};
    if (!(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(h);
    return window.MDXAuth.client().then(function (sb) { return sb.auth.getSession(); })
      .then(function (r) { var t = r && r.data && r.data.session && r.data.session.access_token; if (t) h['Authorization'] = 'Bearer ' + t; return h; })
      .catch(function () { return h; });
  }
  function isSignedIn() { return !!(window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user()); }

  // Resolve the viewer's tier (drives the feed teaser). Called when the session
  // resolves/changes via MDXAuth.onChange, so it never races auth-not-ready. Fails
  // OPEN to the full list on any error (summaries are public regardless).
  function setUserTier(t) { t = (t || 'free'); if (t === USER_TIER) return; USER_TIER = t; renderFeed(); }
  function resolveTier() {
    if (!isSignedIn()) { setUserTier('anon'); return; }
    withAuth().then(function (h) { return fetch(API + '/api/research/quota', { headers: h, credentials: 'include' }); })
      .then(function (r) { return (r && r.ok) ? r.json() : null; })
      .then(function (q) { setUserTier(q && q.tier ? String(q.tier).toLowerCase() : 'free'); })
      .catch(function () { setUserTier('free'); });
  }

  function openViewer(id) {
    var x = ITEMS.find(function (i) { return i.id === id; }); if (!x) return;
    V.item = x; V.zoom = 1.0; V.invert = false;
    V.page = DocState.lastPage(id) || 1;
    V.lastFocus = doc.activeElement;
    DocState.markRead(id);
    var card = doc.querySelector('.rep[data-id="' + cssEsc(id) + '"]'); if (card) card.classList.add('read');
    updateUnread();

    // header
    $('vh-logo').textContent = x.logo;
    $('vh-inst').textContent = x.inst;
    var dk = $('vh-desk'); dk.textContent = x.desk || '';
    $('vh-desk-sep').style.display = x.desk ? '' : 'none';
    $('vh-title').textContent = x.title;
    var st = $('vh-stamp'); st.className = 'stamp ' + stampClass(x.side); st.innerHTML = '<span class="dt"></span>' + stampLabel(x.side);
    buildRelated(x);

    // reset invert visual
    $('vstage').classList.remove('inverted');
    setInvertBtn(false);

    // open the overlay (scale+translate entry, scroll-lock, focus)
    var ov = $('overlay'); ov.classList.add('open'); ov.setAttribute('aria-hidden', 'false');
    doc.documentElement.classList.add('rv-lock');
    setTimeout(function () { $('vh-close').focus(); }, 60);

    // fetch quota (button UI) + start the auth-gated render
    refreshQuota();
    loadDocument(x);
  }
  function closeViewer() {
    var ov = $('overlay'); ov.classList.remove('open', 'fs'); ov.setAttribute('aria-hidden', 'true');
    setFsBtn(false);
    doc.documentElement.classList.remove('rv-lock');
    // release the pdf
    try { if (V.pdf) V.pdf.destroy(); } catch (e) {}
    V.pdf = null;
    if (V.lastFocus && V.lastFocus.focus) V.lastFocus.focus();
  }

  /* gate/message panel (shown in place of the canvas) */
  function showGate(kind) {
    var stage = $('vstage');
    var icon, h, p, cta = '';
    if (kind === 'anon') {
      icon = LOCK_SVG; h = T('Sign in to read', '登录后阅读');
      p = T('Viewing institutional research is for signed-in subscribers.', '查看机构研报为登录订阅用户专享。');
      cta = '<button class="btn primary" data-gate="signin">' + T('Sign in', '登录') + '</button>';
    } else if (kind === 'paid_required') {
      icon = STAR_SVG; h = T('Read the full report with Pro', '升级 Pro 阅读全文');
      p = T('Opening the full PDF is a Pro feature — Insider and free plans read the latest summaries.', '阅读 PDF 全文为 Pro 专享 —— Insider 与免费用户可阅读最新摘要。');
      cta = '<a class="btn upgrade" href="plans.html">' + T('Upgrade to Pro', '升级 Pro') + '</a>';
    } else if (kind === 'quota') {
      icon = LOCK_SVG; h = T('Daily limit reached', '今日已达上限');
      p = T('You have reached today’s access limit — it resets at 00:00 UTC.', '你已达今日访问上限 —— 00:00 UTC 重置。');
    } else if (kind === 'rate') {
      icon = LOCK_SVG; h = T('Too many requests', '请求过于频繁');
      p = T('Please slow down for a moment and try again.', '请稍候片刻后重试。');
    } else {
      icon = LOCK_SVG; h = T('Could not load this document', '无法加载该文档');
      p = T('Something went wrong fetching the report. Please try again.', '获取报告时出错，请重试。');
    }
    stage.innerHTML = '<div class="vgate">' + icon + '<h4>' + esc(h) + '</h4><p>' + esc(p) + '</p>' + cta + '</div>';
    var sb = stage.querySelector('[data-gate="signin"]');
    if (sb) sb.addEventListener('click', function () { if (window.MDXAuth && window.MDXAuth.signIn) window.MDXAuth.signIn(); else if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open(); });
    // pager off
    V.pages = 0; updatePager();
    $('vthumbs').innerHTML = '';
  }
  function showShimmer() {
    $('vstage').innerHTML = '<div class="vshim"><span class="sk" style="top:44px;width:52px;height:6px"></span>'
      + '<span class="sk" style="top:66px;width:70%;height:14px"></span><span class="sk" style="top:96px;width:40%"></span>'
      + '<span class="sk" style="top:140px"></span><span class="sk" style="top:162px"></span>'
      + '<span class="sk" style="top:184px;width:88%"></span><span class="sk" style="top:240px;height:120px;border-radius:6px"></span></div>';
  }

  function loadDocument(x) {
    if (!isSignedIn()) { showGate('anon'); return; }
    showShimmer();
    var tok = ++V.renderTok;
    withAuth().then(function (h) {
      h['Accept'] = 'application/pdf';
      return fetch(API + '/api/research/view/' + encodeURIComponent(x.id), { headers: h, credentials: 'include' });
    }).then(function (resp) {
      if (tok !== V.renderTok) return null;      // superseded (user navigated away)
      if (resp.status === 401) { showGate('anon'); return null; }
      if (resp.status === 402) { return resp.json().catch(function () { return {}; }).then(function (j) { showGate(j && j.quota_exhausted ? 'quota' : 'paid_required'); return null; }); }
      if (resp.status === 429) { showGate('rate'); return null; }
      if (!resp.ok) { showGate('error'); return null; }
      return resp.arrayBuffer();
    }).then(function (buf) {
      if (!buf || tok !== V.renderTok) return;
      return loadPdfLib().then(function (lib) {
        return lib.getDocument({ data: new Uint8Array(buf) }).promise;
      }).then(function (pdf) {
        if (tok !== V.renderTok) { try { pdf.destroy(); } catch (e) {} return; }
        V.pdf = pdf; V.pages = pdf.numPages;
        if (V.page > V.pages) V.page = 1;
        // clean stage → canvas host
        $('vstage').innerHTML = '<div class="vcanvas-wrap"><canvas id="vcanvas"></canvas></div>';
        renderPage(); buildThumbs(); updatePager();
      });
    }).catch(function () { if (tok === V.renderTok) showGate('error'); });
  }

  function renderPage() {
    if (!V.pdf) return;
    var tok = V.renderTok;
    V.pdf.getPage(V.page).then(function (page) {
      if (tok !== V.renderTok) return;
      var canvas = $('vcanvas'); if (!canvas) return;
      var stageW = $('vstage').clientWidth - 48;                 // minus padding
      var base = page.getViewport({ scale: 1 });
      var fit = Math.max(0.4, Math.min(3, (stageW / base.width)));
      var vp = page.getViewport({ scale: fit * V.zoom });
      var dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(vp.width * dpr); canvas.height = Math.floor(vp.height * dpr);
      canvas.style.width = Math.floor(vp.width) + 'px'; canvas.style.height = Math.floor(vp.height) + 'px';
      var ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      page.render({ canvasContext: ctx, viewport: vp });
    });
    DocState.setLastPage(V.item.id, V.page);
    updatePager();
  }
  function buildThumbs() {
    var host = $('vthumbs'); if (!host || !V.pdf) return;
    host.innerHTML = '';
    for (var i = 1; i <= V.pages; i++) {
      (function (n) {
        var btn = doc.createElement('button'); btn.className = 'vthumb' + (n === V.page ? ' on' : '');
        btn.setAttribute('aria-label', T('Page', '第') + ' ' + n);
        btn.setAttribute('data-page', n);
        btn.innerHTML = '<canvas></canvas><span class="tn">' + n + '</span>';
        host.appendChild(btn);
        V.pdf.getPage(n).then(function (page) {
          var c = btn.querySelector('canvas'); if (!c) return;
          var base = page.getViewport({ scale: 1 });
          var scale = 76 / base.width;
          var vp = page.getViewport({ scale: scale });
          c.width = Math.floor(vp.width); c.height = Math.floor(vp.height);
          page.render({ canvasContext: c.getContext('2d'), viewport: vp });
        }).catch(function () {});
      })(i);
    }
  }
  function updatePager() {
    var lbl = V.pages ? (V.page + ' / ' + V.pages) : '— / —';
    $('pg-ind').textContent = lbl;
    $('pg-prev').disabled = !V.pages || V.page <= 1;
    $('pg-next').disabled = !V.pages || V.page >= V.pages;
    doc.querySelectorAll('.vthumb').forEach(function (b) { b.classList.toggle('on', +b.getAttribute('data-page') === V.page); });
  }
  function gotoPage(n) { if (!V.pdf || n < 1 || n > V.pages) return; V.page = n; renderPage(); scrollThumb(); }
  function turnPage(d) { gotoPage(V.page + d); }
  function scrollThumb() { var t = doc.querySelector('.vthumb[data-page="' + V.page + '"]'); if (t) t.scrollIntoView({ block: 'nearest' }); }
  function zoomBy(d) { V.zoom = Math.max(0.7, Math.min(2.4, V.zoom + d * 0.15)); $('zoom-ind').textContent = Math.round(V.zoom * 100) + '%'; renderPage(); }
  function fitWidth() { V.zoom = 1.0; $('zoom-ind').textContent = '100%'; renderPage(); }
  function toggleInvert() { V.invert = !V.invert; $('vstage').classList.toggle('inverted', V.invert); setInvertBtn(V.invert); }
  function setInvertBtn(on) { var b = $('vh-invert'); b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); }
  function toggleFullscreen() { var on = $('overlay').classList.toggle('fs'); setFsBtn(on); if (V.pdf) renderPage(); }
  function setFsBtn(on) { var b = $('vh-fs'); b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); }

  function buildRelated(x) {
    var rel = ITEMS.filter(function (i) { return i.id !== x.id && i.inst === x.inst; });
    if (rel.length < 2) {
      var extra = ITEMS.filter(function (i) { return i.id !== x.id && i.inst !== x.inst && i.tags.some(function (t) { return x.tags.indexOf(t) >= 0; }); });
      rel = rel.concat(extra);
    }
    rel = rel.slice(0, 3);
    var host = $('vr-chips');
    if (!rel.length) { host.innerHTML = '<span class="vr-tk" style="padding:6px 2px">' + T('No related reports yet', '暂无相关报告') + '</span>'; return; }
    host.innerHTML = rel.map(function (r) {
      var tk = r.tickers[0] || r.tags[0] || '';
      return '<button class="vr-chip" data-open="' + esc(r.id) + '"><span class="vr-inst">' + esc(r.inst) + '</span><span class="vr-tk">' + esc(tk) + '</span></button>';
    }).join('');
  }

  /* ═══════════ quota + download ═══════════ */
  function showDlState(kind, q) {
    ['ok', 'max', 'free', 'anon'].forEach(function (k) {
      $('dl-state-' + k).style.display = (k === kind) ? 'flex' : 'none';
      var btn = $('dl-btn-' + k); if (btn) btn.style.display = (k === kind) ? 'inline-flex' : 'none';
    });
    if (kind === 'ok' && q) {
      var used = q.used || 0, limit = q.limit || 0, remain = (q.remaining != null ? q.remaining : Math.max(0, limit - used));
      $('dl-remain').textContent = remain;
      $('dl-limit-en').textContent = limit; $('dl-limit-zh').textContent = limit;
      $('dl-meter').style.width = (limit ? Math.round(used / limit * 100) : 0) + '%';
    }
  }
  function refreshQuota() {
    if (!isSignedIn()) { showDlState('anon'); return; }
    withAuth().then(function (h) { return fetch(API + '/api/research/quota', { headers: h, credentials: 'include' }); })
      .then(function (r) { return r.ok ? r.json() : (r.status === 401 ? { _anon: true } : null); })
      .then(function (q) {
        if (!q) { showDlState('free'); return; }
        if (q._anon) { showDlState('anon'); return; }
        var tier = q.tier || 'free', limit = q.limit || 0, remain = (q.remaining != null ? q.remaining : limit);
        if (!limit || tier === 'free') { showDlState('free'); return; }
        if (remain <= 0) { showDlState('max'); return; }
        showDlState('ok', q);
      })
      .catch(function () { showDlState('free'); });
  }
  function doDownload() {
    if (!V.item) return;
    var btn = $('dl-btn-ok'); if (btn.disabled) return; btn.disabled = true;
    withAuth().then(function (h) { return fetch(API + '/api/research/download/' + encodeURIComponent(V.item.id), { method: 'POST', headers: h, credentials: 'include' }); })
      .then(function (resp) {
        if (resp.status === 402) { return resp.json().catch(function () { return {}; }).then(function (j) { showDlState(j && j.quota_exhausted ? 'max' : 'free'); return null; }); }
        if (resp.status === 401) { showDlState('anon'); return null; }
        if (resp.status === 429) { return null; }
        if (!resp.ok) return null;
        return resp.blob().then(function (blob) {
          var url = URL.createObjectURL(blob);
          var a = doc.createElement('a'); a.href = url; a.download = (V.item.id || 'research') + '.pdf';
          doc.body.appendChild(a); a.click(); a.remove(); setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
        });
      })
      .catch(function () {})
      .then(function () { btn.disabled = false; refreshQuota(); });
  }

  /* ═══════════ unread count ═══════════ */
  function updateUnread() {
    var n = ITEMS.filter(function (x) { return !DocState.isRead(x.id); }).length;
    $('unread-n').textContent = n;
    $('badge-latest').textContent = ITEMS.length;
    $('badge-picks').textContent = ITEMS.filter(function (x) { return x.top; }).length;
    $('badge-saved').textContent = ITEMS.filter(function (x) { return DocState.isSaved(x.id); }).length;
  }

  /* ═══════════ hydrate + refresh ═══════════ */
  function ingest(catalog) {
    var items = (catalog && Array.isArray(catalog.items)) ? catalog.items : [];
    ITEMS = items.map(normItem);
    buildInstFacets(); buildThemeFacets();
    buildTree(); updateHero(); updateUnread(); renderFeed();
  }
  function hydrateFromBake() {
    var el = $('rv-catalog'); if (!el) return;
    try { ingest(JSON.parse(el.textContent || '{}')); } catch (e) { ingest({ items: [] }); }
  }
  function refreshFromApi() {
    fetch(API + '/api/research/catalog', { credentials: 'include' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && Array.isArray(j.items)) ingest(j); })
      .catch(function () { /* keep the baked snapshot */ });
  }

  /* ═══════════ language re-render (re-tint chrome + re-render feed) ═══════════ */
  function onLangChange() {
    var q = $('q'); q.placeholder = q.getAttribute('data-ph-' + (zh() ? 'zh' : 'en'));
    var vf = $('vh-find-in'); vf.placeholder = vf.getAttribute('data-ph-' + (zh() ? 'zh' : 'en'));
    buildTree(); updateHero(); renderFeed();
    if ($('overlay').classList.contains('open') && V.item) {
      $('vh-stamp').innerHTML = '<span class="dt"></span>' + stampLabel(V.item.side);
      buildRelated(V.item);
    }
  }

  /* ═══════════ wiring ═══════════ */
  function wire() {
    // lanes
    doc.querySelectorAll('.rv-lane').forEach(function (b) { b.addEventListener('click', function () { setLane(b.getAttribute('data-lane')); }); });
    // search
    $('q').addEventListener('input', onSearchInput);
    $('q').placeholder = $('q').getAttribute('data-ph-' + (zh() ? 'zh' : 'en'));
    $('vh-find-in').placeholder = $('vh-find-in').getAttribute('data-ph-' + (zh() ? 'zh' : 'en'));
    // facets (event-delegated so data-driven buttons work)
    $('facets').addEventListener('click', function (e) {
      var b = e.target.closest('.aff'); if (!b) return;
      var dim = b.getAttribute('data-f'), val = b.getAttribute('data-v');
      FILT[dim] = val; syncFacetActive(dim, val);
      if (dim === 'inst') doc.querySelectorAll('#tree .rv-tw').forEach(function (t) { t.classList.toggle('sel', val !== '' && t.getAttribute('data-inst') === val); });
      if (dim === 'inst' && FILT.q) onSearchInput();  // re-scope server search by institution
      renderFeed();
    });
    // active chips
    $('active-chips').addEventListener('click', function (e) {
      var b = e.target.closest('[data-clear]'); if (!b) return;
      var d = b.getAttribute('data-clear');
      if (d === 'all') { FILT = { inst: '', side: '', theme: '', q: '' }; $('q').value = ''; SEARCH_HITS = null;
        doc.querySelectorAll('.aff').forEach(function (x) { x.classList.toggle('active', x.getAttribute('data-v') === ''); });
        doc.querySelectorAll('#tree .rv-tw').forEach(function (x) { x.classList.remove('sel'); }); }
      else if (d === 'q') { FILT.q = ''; $('q').value = ''; SEARCH_HITS = null; }
      else { FILT[d] = ''; syncFacetActive(d, ''); if (d === 'inst') doc.querySelectorAll('#tree .rv-tw').forEach(function (x) { x.classList.remove('sel'); }); }
      renderFeed();
    });
    // browse tree
    $('tree').addEventListener('click', function (e) {
      var tog = e.target.closest('[data-toggle]');
      if (tog) { tog.closest('.rv-node').classList.toggle('open'); return; }
      var leaf = e.target.closest('[data-inst]');
      if (leaf) { pickTreeInst(leaf.getAttribute('data-inst')); }
    });
    // feed (event-delegated)
    $('feed').addEventListener('click', function (e) {
      var art = e.target.closest('.rep'); if (!art) return;
      var id = art.getAttribute('data-id');
      var more = e.target.closest('[data-act="morepts"]'); if (more) { art.classList.toggle('open-pts'); return; }
      var save = e.target.closest('[data-act="save"]');
      if (save) {
        var on = DocState.toggleSaved(id); save.classList.toggle('on', on); save.setAttribute('aria-pressed', on ? 'true' : 'false');
        $('badge-saved').textContent = ITEMS.filter(function (x) { return DocState.isSaved(x.id); }).length;
        if (LANE === 'saved') renderFeed();
        return;
      }
      if (e.target.closest('[data-act="view"]')) openViewer(id);
    });
    // drawer
    $('browse-btn').addEventListener('click', openDrawer);
    $('drawer-x').addEventListener('click', closeDrawer);
    $('scrim').addEventListener('click', closeDrawer);
    // viewer controls
    $('vh-close').addEventListener('click', closeViewer);
    $('vh-invert').addEventListener('click', toggleInvert);
    $('vh-fs').addEventListener('click', toggleFullscreen);
    $('pg-prev').addEventListener('click', function () { turnPage(-1); });
    $('pg-next').addEventListener('click', function () { turnPage(1); });
    $('zoom-in').addEventListener('click', function () { zoomBy(1); });
    $('zoom-out').addEventListener('click', function () { zoomBy(-1); });
    $('fit-w').addEventListener('click', fitWidth);
    $('dl-btn-ok').addEventListener('click', doDownload);
    $('dl-btn-anon').addEventListener('click', function () { if (window.MDXAuth && window.MDXAuth.signIn) window.MDXAuth.signIn(); else if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open(); });
    $('vrelated').addEventListener('click', function (e) { var b = e.target.closest('[data-open]'); if (b) openViewer(b.getAttribute('data-open')); });
    // in-document find (pdf.js find controller wiring kept minimal — see cut note in report)
    $('vh-find-in').addEventListener('keydown', function (e) { if (e.key === 'Enter') findInDoc($('vh-find-in').value.trim()); });
    // overlay click-out + keyboard (Esc / arrows / focus-trap)
    $('overlay').addEventListener('click', function (e) { if (e.target === this) closeViewer(); });
    doc.addEventListener('keydown', onKeydown);
    // language switch (theme.js flips [data-lang]; observe it)
    var mo = new MutationObserver(function () { onLangChange(); });
    mo.observe(doc.documentElement, { attributes: true, attributeFilter: ['data-lang'] });
    // re-render feed on auth resolve so the teaser + quota/gate reflect the real session
    if (window.MDXAuth && window.MDXAuth.onChange) window.MDXAuth.onChange(function () {
      resolveTier();   // sets USER_TIER → re-renders the feed (teaser for non-Pro)
      if ($('overlay').classList.contains('open')) { refreshQuota(); if (!V.pdf) loadDocument(V.item); }
    });
  }

  function onKeydown(e) {
    if (!$('overlay').classList.contains('open')) return;
    var inField = /^(INPUT|TEXTAREA)$/.test((e.target.tagName || ''));
    if (e.key === 'Escape') { closeViewer(); return; }
    if (!inField && e.key === 'ArrowRight') { turnPage(1); return; }
    if (!inField && e.key === 'ArrowLeft') { turnPage(-1); return; }
    if (e.key === 'Tab') {
      var f = Array.prototype.filter.call($('modal').querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])'),
        function (el) { return el.offsetParent !== null && !el.disabled; });
      if (!f.length) return; var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && doc.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && doc.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  /* in-document find — jump to the first page containing the query (text-layer scan). */
  function findInDoc(q) {
    if (!q || !V.pdf) return;
    var lc = q.toLowerCase(), n = 1;
    (function scan(p) {
      if (p > V.pages) return;
      V.pdf.getPage(p).then(function (page) { return page.getTextContent(); }).then(function (tc) {
        var text = tc.items.map(function (it) { return it.str; }).join(' ').toLowerCase();
        if (text.indexOf(lc) >= 0) { gotoPage(p); return; }
        scan(p + 1);
      }).catch(function () { scan(p + 1); });
    })(n);
  }

  /* ═══════════ boot ═══════════ */
  function boot() {
    wire();
    hydrateFromBake();   // instant paint from the SSR snapshot
    refreshFromApi();    // then hourly-fresh live catalog
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

/* ═══════════════════════════════════════════════════════════════════════════
   Research Vault — client app (defer-loaded; DOMContentLoaded-wrapped).
   Paints from the live API, keeps the SSR-baked #rv-catalog JSON as an explicit
   offline fallback, and drives the feed / lanes / browse tree / facets / search /
   PDF viewer.

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

  /* ── transfer progress ───────────────────────────────────────────────────
     Reports of a "broken" download button were a REPORTING bug, not a transfer
     bug: the server hands the whole PDF over in ~0.3s (R2 GET measured at
     0.1-0.3s for a 0.5-1.5MB report), but the origin is in SFO and the bytes
     still have to cross to the reader. `resp.blob()` / `resp.arrayBuffer()`
     resolve only after the LAST byte, so for those seconds the UI was
     indistinguishable from a dead click. The bytes were never the problem; the
     silence was. These helpers surface the transfer as it happens. */

  function fmtBytes(n) {
    if (typeof n !== 'number' || !isFinite(n) || n < 0) return '';
    return n < 1048576 ? (Math.round(n / 1024) + ' KB') : ((n / 1048576).toFixed(1) + ' MB');
  }

  /* Drain a Response to an ArrayBuffer, calling onProgress(frac, got, total).
     `frac` is -1 when the total is unknown (no Content-Length), so callers can
     fall back to a byte count rather than inventing a percentage. Degrades to
     the one-shot read where streams are unavailable — the download still works,
     it just has no progress to report. */
  function readWithProgress(resp, onProgress) {
    var total = parseInt(resp.headers.get('Content-Length') || '0', 10) || 0;
    if (!resp.body || typeof resp.body.getReader !== 'function') return resp.arrayBuffer();
    var reader = resp.body.getReader(), chunks = [], got = 0;
    return (function pump() {
      return reader.read().then(function (r) {
        if (r.done) {
          var out = new Uint8Array(got), off = 0;
          for (var i = 0; i < chunks.length; i++) { out.set(chunks[i], off); off += chunks[i].length; }
          return out.buffer;
        }
        chunks.push(r.value); got += r.value.length;
        try { onProgress(total ? (got / total) : -1, got, total); } catch (e) {}
        return pump();
      });
    })();
  }

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
  var TOTAL_COUNT = 0;       // full inventory count; the public bake carries only 3 items
  var CATALOG_SUMMARY = null;// whole-vault, public-safe aggregates (even for the 3-item preview)
  var CATALOG_PREVIEW = false;
  var CATALOG_SOURCE = 'loading'; // 'loading' | 'live' | 'snapshot'
  var CATALOG_REQ = 0;       // newest-request-wins guard for auth/bootstrap refresh races
  var CATALOG_ABORT = null;
  var LANE = 'latest';
  var FILT = { inst: '', side: '', theme: '', q: '' };
  var SEARCH_HITS = null;    // set of ids from the live search API, or null (no server search)
  // Teaser gate: reading full PDFs is Pro-only. Every non-Pro visitor sees the
  // same fixed latest-three preview, and the app starts locked while auth resolves
  // so there is never a flash of the full catalog.
  var USER_TIER = 'anon';    // 'anon' | 'free' | 'insider' (display: Essential) | 'pro'
  function feedUnlocked() { return USER_TIER === 'pro'; }
  function teaseCount() { return 3; }
  function previewItems() {
    var ready = ITEMS.filter(function (x) { return x.points.some(function (p) { return String(p || '').trim(); }); });
    var preview = ready.slice(0, teaseCount());
    var selected = {};
    preview.forEach(function (x) { selected[x.id] = 1; });
    if (preview.length < teaseCount()) {
      ITEMS.some(function (x) {
        if (!selected[x.id]) { preview.push(x); selected[x.id] = 1; }
        return preview.length >= teaseCount();
      });
    }
    return preview;
  }
  // Top Picks is a Pro-only lane.
  function picksLocked() { return USER_TIER !== 'pro'; }
  // Pager: reveal the (already-loaded) feed a page at a time. shownN resets
  // whenever the result set — lane + filters + search — changes (see renderFeed).
  var PAGE_SIZE = 18, shownN = 18, _feedSig = '';

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
      tickers: Array.isArray(x.tickers) ? x.tickers : [],
      slug: x.slug || ''        // research/<slug>.html SEO landing page
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
  function summaryNumber(key) {
    if (!CATALOG_SUMMARY || CATALOG_SUMMARY[key] === null || CATALOG_SUMMARY[key] === undefined) return null;
    var n = Number(CATALOG_SUMMARY[key]);
    return isFinite(n) && n >= 0 ? Math.floor(n) : null;
  }

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
    var derivedNewN = wk.length;
    var desks = {}; wk.forEach(function (x) { if (x.inst && x.inst !== 'Unknown') desks[x.inst] = 1; });
    var derivedDeskN = Object.keys(desks).length;
    // most-covered theme this week (falls back to all-time if none this week)
    var pool = wk.length ? wk : ITEMS;
    var tc = {}; pool.forEach(function (x) { x.tags.forEach(function (t) { tc[t] = (tc[t] || 0) + 1; }); });
    var derivedTheme = ''; var best = 0;
    Object.keys(tc).forEach(function (k) { if (tc[k] > best) { best = tc[k]; derivedTheme = k; } });

    // Anonymous/free clients receive only three report records. Never turn that
    // entitlement slice into a whole-vault claim: prefer the server's public-safe
    // aggregate block and stay neutral if an older API has not supplied it yet.
    var aggregateNewN = summaryNumber('new_this_week');
    var aggregateDeskN = summaryNumber('desks_this_week');
    var aggregatePicks = summaryNumber('highlighted');
    var newN = aggregateNewN !== null ? aggregateNewN : (CATALOG_PREVIEW ? null : derivedNewN);
    var deskN = aggregateDeskN !== null ? aggregateDeskN : (CATALOG_PREVIEW ? null : derivedDeskN);
    var picks = aggregatePicks !== null ? aggregatePicks : (CATALOG_PREVIEW ? null : ITEMS.filter(function (x) { return x.top; }).length);
    var summaryTheme = CATALOG_SUMMARY && typeof CATALOG_SUMMARY.most_covered_theme === 'string'
      ? CATALOG_SUMMARY.most_covered_theme.trim() : '';
    var topTheme = summaryTheme || (CATALOG_PREVIEW ? '' : derivedTheme);

    $('fig-new').textContent = newN === null ? '—' : newN;
    $('fig-desks').textContent = deskN === null ? '—' : deskN;
    $('fig-theme').textContent = topTheme || T('—', '—');
    $('fig-total').textContent = TOTAL_COUNT;
    buildWeb();

    // verdict lead line
    if (newN !== null && deskN !== null && picks !== null) {
      $('v-en-lead').textContent = newN + ' new institutional report' + (newN === 1 ? '' : 's') + ' this week · ' + picks + ' highlighted · ' + deskN + ' desk' + (deskN === 1 ? '' : 's') + ' publishing.';
      $('v-zh-lead').textContent = '本周新增 ' + newN + ' 篇机构研报 · ' + picks + ' 篇精选 · ' + deskN + ' 家研究部门在发。';
    } else if (TOTAL_COUNT || ITEMS.length) {
      $('v-en-lead').textContent = 'Latest preview loaded. Whole-vault weekly totals are temporarily unavailable.';
      $('v-zh-lead').textContent = '最新预览已载入，完整库的本周统计暂不可用。';
    } else {
      $('v-en-lead').textContent = 'No institutional reports are available yet.';
      $('v-zh-lead').textContent = '暂时还没有可用的机构研报。';
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
    var summaryHasRoster = !!(CATALOG_SUMMARY && Array.isArray(CATALOG_SUMMARY.institutions));
    var rosterUnknown = CATALOG_PREVIEW && !summaryHasRoster;
    var counts = {};
    if (!rosterUnknown && !summaryHasRoster) {
      ITEMS.forEach(function (x) { var n = x.inst; if (n && n !== 'Unknown') counts[n] = (counts[n] || 0) + 1; });
    }
    var roster = summaryHasRoster
      ? CATALOG_SUMMARY.institutions.map(function (x) {
          return { name: String(x && x.name || '').trim(), count: Math.max(0, Number(x && x.count) || 0) };
        }).filter(function (x) { return x.name && x.name !== 'Unknown'; })
      : Object.keys(counts).map(function (n) { return { name: n, count: counts[n] }; });
    roster.sort(function (a, b) { return b.count - a.count || a.name.localeCompare(b.name); });
    var N = roster.length;
    if ($('web-n')) $('web-n').textContent = rosterUnknown ? '—' : N;

    if (WEB.timer) { clearInterval(WEB.timer); WEB.timer = null; }
    WEB.cur = -1; WEB.hover = false;
    WEB.reduce = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

    if (!N) {  // honest empty state — one quiet, unlit core (no fake desks)
      gThreads.innerHTML = ''; if (gMotes) gMotes.innerHTML = '';
      gNodes.innerHTML = '<circle cx="170" cy="95" r="4" fill="var(--rv)" opacity="0.32"/>';
      if ($('web-sname')) $('web-sname').textContent = rosterUnknown
        ? T('Full directory temporarily unavailable', '完整名录暂不可用')
        : T('Coming online…', '正在接入…');
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
    // The public preview is anchored to the latest three catalog entries before
    // filters/search are applied. Otherwise a visitor could search for a locked
    // title and promote it into the visible allowance.
    var previewRows = feedUnlocked() ? [] : previewItems().filter(matchItem);
    var feed = $('feed');
    var picksGate = LANE === 'picks' && picksLocked();
    var pt = doc.querySelector('.rv-lane[data-lane="picks"]');
    if (pt) pt.classList.toggle('locked', picksLocked());   // small lock glyph on the tab
    // reset the pager whenever the result set (lane + filters + search) changes
    var sig = LANE + '|' + FILT.inst + '|' + FILT.side + '|' + FILT.theme + '|' + FILT.q;
    if (sig !== _feedSig) { _feedSig = sig; shownN = PAGE_SIZE; }
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
      // Pro: paged — show the first shownN, then a "Show more" button
      var pg = rows.slice(0, shownN).map(cardHTML).join('');
      if (rows.length > shownN) pg += moreButton(rows.length - shownN);
      feed.innerHTML = pg;
    } else {
      // Non-Pro: only the fixed latest three summaries can render. Locked cards
      // use generic skeleton copy so later report titles/summaries are not exposed.
      var html = previewRows.map(cardHTML).join('');
      var lockedN = Math.max(0, TOTAL_COUNT - teaseCount());
      if (lockedN) html += lockedTeaser(lockedN);
      feed.innerHTML = html || picksUpgradePanel();
    }
    $('cnt-n').textContent = picksGate ? 0 : (feedUnlocked() ? Math.min(shownN, rows.length) : previewRows.length);
    $('cnt-t').textContent = feedUnlocked() ? rows.length : TOTAL_COUNT;
    renderActiveChips();
  }
  function emptyState(h, p) {
    return '<div class="rv-empty glass">' + BOOK_SVG + '<h3>' + esc(h) + '</h3><p>' + esc(p) + '</p></div>';
  }
  // The non-Pro upgrade wall: a few blurred ghost cards behind a glass upgrade
  // card. Ghosts are decorative (aria-hidden, no data-id) so the feed click
  // handler can never open them, and pointer-events are killed in CSS.
  function lockedTeaser(n) {
    var ghosts = [0, 1, 2].map(function () {
      return '<article class="rep glass" aria-hidden="true">'
        + '<div class="rep-top"><span class="rep-logo">PRO</span>'
        + '<span class="rep-inst">' + T('Institutional desk', '机构研究台') + '</span>'
        + '</div><h3>' + T('Pro research report', 'Pro 研报') + '</h3>'
        + '<ul class="rep-points"><li>' + T('Full summary available with Pro.', '完整摘要为 Pro 专享。') + '</li></ul></article>';
    }).join('');
    var head = zh() ? ('还有 ' + n + ' 篇机构研报') : (n + ' more institutional report' + (n === 1 ? '' : 's'));
    var body = T('You’re previewing the latest three summaries. Upgrade to Pro to open every desk and read the full PDFs.',
                 '你正在预览最新三篇摘要。升级 Pro 即可查看全部机构研报并阅读 PDF 全文。');
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
  // "Show more" pager button; `remaining` is how many rows are still hidden.
  function moreButton(remaining) {
    var next = Math.min(remaining, PAGE_SIZE);
    return '<button class="rv-more" data-act="more">' + CHEV_SVG
      + '<span>' + T('Show ' + next + ' more', '再看 ' + next + ' 篇') + '</span>'
      + '<span class="rv-more-rem">' + T(remaining + ' left', '剩 ' + remaining) + '</span></button>';
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
      + '<h3>' + (x.slug && feedUnlocked()
          ? '<a class="rep-titlelink" href="research/' + esc(x.slug) + '.html" data-act="view">' + esc(x.title) + '</a>'
          : esc(x.title)) + '</h3>'
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
      withAuth().then(function (h) { return fetch(url, { headers: h, credentials: 'include' }); })
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
  /* Zoom is a MULTIPLIER on the fit-to-width scale, so 100% == fit width. A ladder
     rather than a fixed step: every stop is a round percentage and the low end
     stays usable (the old additive 0.15 step could never land back on 100% from a
     50% start, and floored at 70% — too tight to see a full page). */
  var ZOOM_STEPS = [0.25, 0.35, 0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.4];
  var ZOOM_DEFAULT = 0.5;   // opening zoom — a whole page in view, not fit-width

  var V = { item: null, pdf: null, page: 1, pages: 0, zoom: ZOOM_DEFAULT, invert: false, renderTok: 0, lastFocus: null,
            dling: false,
            // in-document find: hits are document-ordered; byPage indexes them for
            // painting; textIx caches the per-page search index (scan once per doc).
            find: { q: '', tok: 0, hits: [], byPage: {}, idx: -1 }, textIx: {} };

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

  /* Supabase Bearer — the exact helper site/mm_brain.js uses.
     When theme.js has not executed yet this resolves with NO Authorization header.
     The page now keeps its neutral loading shell up until a catalog response wins;
     wire()'s MDXAuth-onChange registration (with its 'load' fallback) re-issues the
     gated read once a Bearer is obtainable. Do not replace that with a polling loop. */
  function withAuth(h) {
    h = h || {};
    if (!(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(h);
    return window.MDXAuth.client().then(function (sb) { return sb.auth.getSession(); })
      .then(function (r) { var t = r && r.data && r.data.session && r.data.session.access_token; if (t) h['Authorization'] = 'Bearer ' + t; return h; })
      .catch(function () { return h; });
  }
  function isSignedIn() { return !!(window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user()); }

  // Resolve the viewer's tier (drives the feed teaser). Called when the session
  // resolves/changes via MDXAuth.onChange. Any error stays on the public preview.
  function setUserTier(t) {
    t = (t || 'free');
    if (t === USER_TIER) return;
    USER_TIER = t;
    if (USER_TIER === 'pro') refreshFromApi();
    else renderFeed();
  }
  function resolveTier() {
    if (!isSignedIn()) { setUserTier('anon'); return; }
    withAuth().then(function (h) { return fetch(API + '/api/research/quota', { headers: h, credentials: 'include' }); })
      .then(function (r) { return (r && r.ok) ? r.json() : null; })
      .then(function (q) { setUserTier(q && q.tier ? String(q.tier).toLowerCase() : 'free'); })
      .catch(function () { setUserTier('free'); });
  }

  function openViewer(id) {
    var x = ITEMS.find(function (i) { return i.id === id; }); if (!x) return;
    V.item = x; V.zoom = ZOOM_DEFAULT; V.invert = false;
    $('zoom-ind').textContent = Math.round(ZOOM_DEFAULT * 100) + '%';
    resetFind();                                  // a new document invalidates hits + the text index
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
    // release the pdf (bump the token + drop observers so any in-flight page
    // render/getPage resolves into a no-op instead of touching a destroyed doc)
    V.renderTok++; _teardownObservers();
    try { if (V.pdf) V.pdf.destroy(); } catch (e) {}
    V.pdf = null; V.pageEls = null;
    resetFind();          // drop hits + the cached page text of the document we just destroyed
    if (V.lastFocus && V.lastFocus.focus) V.lastFocus.focus();
  }

  /* gate/message panel (shown in place of the canvas) */
  function openLatestSignin() {
    if (window.MMOnboard && typeof window.MMOnboard.open === 'function') {
      window.MMOnboard.open('signin', {});
      return;
    }
    if (window.MDXAuth && typeof window.MDXAuth.open === 'function') {
      window.MDXAuth.open('signin');
      return;
    }
    location.href = '/?signin=1&ret=/research_vault.html';
  }
  function showGate(kind) {
    var stage = $('vstage');
    var icon, h, p, cta = '';
    if (kind === 'anon') {
      icon = LOCK_SVG; h = T('Sign in to read', '登录后阅读');
      p = T('Viewing institutional research is for signed-in subscribers.', '查看机构研报为登录订阅用户专享。');
      cta = '<button class="btn primary" data-gate="signin">' + T('Sign in', '登录') + '</button>';
    } else if (kind === 'paid_required') {
      icon = STAR_SVG; h = T('Read the full report with Pro', '升级 Pro 阅读全文');
      p = T('Opening the full PDF is a Pro feature — Essential and free plans read the latest summaries.', '阅读 PDF 全文为 Pro 专享 —— Essential 与免费用户可阅读最新摘要。');
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
    if (sb) sb.addEventListener('click', openLatestSignin);
    // pager off
    V.pages = 0; updatePager();
    $('vthumbs').innerHTML = '';
  }
  function showShimmer() {
    $('vstage').innerHTML = '<div class="vshim"><span class="sk" style="top:44px;width:52px;height:6px"></span>'
      + '<span class="sk" style="top:66px;width:70%;height:14px"></span><span class="sk" style="top:96px;width:40%"></span>'
      + '<span class="sk" style="top:140px"></span><span class="sk" style="top:162px"></span>'
      + '<span class="sk" style="top:184px;width:88%"></span><span class="sk" style="top:240px;height:120px;border-radius:6px"></span>'
      // Progress line under the skeleton. A skeleton alone says "something is
      // coming"; on a multi-megabyte report over a long link the reader also
      // needs to know it is MOVING. Inline styles for the same reason as the
      // button fill — this file ships ahead of the baked template.
      //
      // Anchored to the TOP of the page mock, and neither to a magic mid-page
      // offset nor to the bottom. .vshim is sized by aspect-ratio (1/1.32), so it
      // is ~739px tall inside a shorter scrollable .vstage: a bottom-anchored line
      // sits below the fold and a large top offset falls outside the paper on a
      // narrow viewport. The top edge is the one place always in view on first
      // paint. Colors are literal ink, not theme tokens — .vshim is a WHITE page
      // mock in both themes, so var(--muted) would be near-invisible on it in
      // dark mode; these match the skeleton's own #eef0f5 family.
      + '<div id="vshim-p" style="position:absolute;left:46px;right:46px;top:16px;display:flex;align-items:center;gap:10px;font-size:12px;color:#8a93a6">'
      + '<span style="flex:1;height:4px;border-radius:4px;overflow:hidden;background:#eef0f5">'
      + '<i id="vshim-bar" style="display:block;height:100%;width:0%;border-radius:4px;background:#b9c3d6;transition:width .25s ease"></i></span>'
      + '<span id="vshim-txt" style="font-variant-numeric:tabular-nums;white-space:nowrap"></span></div></div>';
    setStageProgress(null);
  }

  /* Transfer progress inside the viewer stage. Silent no-op once the stage has
     moved on (gate, error, or the rendered document replaced the shimmer). */
  function setStageProgress(frac, got) {
    var bar = $('vshim-bar'), txt = $('vshim-txt');
    if (!bar || !txt) return;
    if (frac == null) { txt.textContent = T('Fetching the report…', '正在获取报告…'); return; }
    if (frac < 0) { txt.textContent = fmtBytes(got); return; }   // no Content-Length
    bar.style.width = Math.round(frac * 100) + '%';
    txt.textContent = Math.round(frac * 100) + '%';
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
      return readWithProgress(resp, function (frac, got) {
        if (tok === V.renderTok) setStageProgress(frac, got);
      });
    }).then(function (buf) {
      if (!buf || tok !== V.renderTok) return;
      return loadPdfLib().then(function (lib) {
        return lib.getDocument({ data: new Uint8Array(buf) }).promise;
      }).then(function (pdf) {
        if (tok !== V.renderTok) { try { pdf.destroy(); } catch (e) {} return; }
        V.pdf = pdf; V.pages = pdf.numPages;
        if (V.page > V.pages || V.page < 1) V.page = 1;
        buildPageColumn(); buildThumbs(); updatePager();
      });
    }).catch(function () { if (tok === V.renderTok) showGate('error'); });
  }

  /* ── continuous-scroll page column ──────────────────────────────────────
     One <div.vpage> per page, each with its OWN <canvas>, stacked vertically in
     a scrollable column. Pages render lazily as they near the viewport (per-page
     canvases avoid the single-canvas "concurrent render" lock that could wedge
     the old click-to-turn viewer on page 1). The pager buttons + thumbnails now
     scroll to a page; the page indicator tracks whatever is in view. */
  function _teardownObservers() {
    if (V.io) { try { V.io.disconnect(); } catch (e) {} V.io = null; }
    if (V.spy) { try { V.spy.disconnect(); } catch (e) {} V.spy = null; }
  }
  function buildPageColumn() {
    _teardownObservers();
    V.pageEls = []; V.rendered = {}; V._vis = {};
    $('vstage').innerHTML = '<div class="vscroll" id="vscroll"></div>';
    var col = $('vscroll');
    for (var i = 1; i <= V.pages; i++) {
      var el = doc.createElement('div');
      el.className = 'vpage'; el.setAttribute('data-page', i);
      el.innerHTML = '<canvas></canvas>';
      col.appendChild(el); V.pageEls.push(el);
    }
    // Uniform-page assumption: size every placeholder from page 1's aspect at the
    // current fit×zoom (so the scrollbar is right immediately), then correct each
    // page to its own dimensions when it actually renders.
    V.pdf.getPage(1).then(function (p1) {
      var base = p1.getViewport({ scale: 1 });
      V.baseW = base.width; V.baseH = base.height;
      layoutColumn();
      if (V.page > 1) requestAnimationFrame(function () { scrollToPage(V.page, 'auto'); });
    });
  }
  function _computeFit() {
    var stageW = $('vstage').clientWidth - 48;                   // minus padding
    return Math.max(0.4, Math.min(3, stageW / (V.baseW || stageW)));
  }
  function layoutColumn() {
    if (!V.pageEls || !V.baseW) return;
    V.fitScale = _computeFit();
    var scale = V.fitScale * V.zoom;
    var w = Math.floor(V.baseW * scale), ratio = V.baseH / V.baseW;
    V.pageEls.forEach(function (el) {
      el.style.width = w + 'px';
      if (!el.classList.contains('rendered')) el.style.height = Math.floor(w * ratio) + 'px';
    });
    _spinObservers(scale);
  }
  function _spinObservers(scale) {
    _teardownObservers();
    var stage = $('vstage');
    // lazy render: draw a page (plus a generous margin) as it nears the viewport
    V.io = new IntersectionObserver(function (ents) {
      ents.forEach(function (e) { if (e.isIntersecting) renderPageInto(+e.target.getAttribute('data-page'), scale); });
    }, { root: stage, rootMargin: '500px 0px' });
    // page indicator: the page occupying the most of the viewport wins
    V.spy = new IntersectionObserver(function (ents) {
      ents.forEach(function (e) { V._vis[+e.target.getAttribute('data-page')] = e.isIntersecting ? e.intersectionRatio : 0; });
      var best = V.page, bestR = -1;
      Object.keys(V._vis).forEach(function (k) { if (V._vis[k] > bestR) { bestR = V._vis[k]; best = +k; } });
      if (best !== V.page) { V.page = best; updatePager(); scrollThumb(); if (V.item) DocState.setLastPage(V.item.id, V.page); }
    }, { root: stage, threshold: [0.1, 0.3, 0.6, 0.9] });
    V.pageEls.forEach(function (el) { V.io.observe(el); V.spy.observe(el); });
  }
  function renderPageInto(n, scale) {
    var el = V.pageEls[n - 1]; if (!el || !V.pdf) return;
    if (V.rendered[n] === scale) return;
    V.rendered[n] = scale;                                       // claim synchronously → no double render
    var tok = V.renderTok;
    V.pdf.getPage(n).then(function (page) {
      if (tok !== V.renderTok || !V.pdf) return;
      var canvas = el.querySelector('canvas'); if (!canvas) return;
      if (el._task) { try { el._task.cancel(); } catch (e) {} el._task = null; }
      var vp = page.getViewport({ scale: scale });
      var dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(vp.width * dpr); canvas.height = Math.floor(vp.height * dpr);
      canvas.style.width = Math.floor(vp.width) + 'px'; canvas.style.height = Math.floor(vp.height) + 'px';
      el.style.width = Math.floor(vp.width) + 'px'; el.style.height = Math.floor(vp.height) + 'px';
      el.classList.add('rendered');
      var ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var task = page.render({ canvasContext: ctx, viewport: vp }); el._task = task;
      task.promise.then(function () { el._task = null; }, function () { el._task = null; if (V.rendered[n] === scale) delete V.rendered[n]; });
    }).catch(function () { if (V.rendered[n] === scale) delete V.rendered[n]; });
  }
  // zoom / fit / fullscreen re-flow: resize every placeholder and re-render what's on screen
  function relayout() {
    if (!V.pdf || !V.pageEls) return;
    V.rendered = {};
    V.pageEls.forEach(function (el) { el.classList.remove('rendered'); if (el._task) { try { el._task.cancel(); } catch (e) {} el._task = null; } });
    layoutColumn();
    var scale = V.fitScale * V.zoom, sr = $('vstage').getBoundingClientRect();
    V.pageEls.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.bottom > sr.top - 500 && r.top < sr.bottom + 500) renderPageInto(+el.getAttribute('data-page'), scale);
    });
    repaintHighlights();   // hit rects are stored at scale 1 — re-project them at the new zoom
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
  function scrollToPage(n, behavior) {
    var el = V.pageEls && V.pageEls[n - 1], stage = $('vstage'); if (!el || !stage) return;
    var r = el.getBoundingClientRect(), sr = stage.getBoundingClientRect();
    var top = stage.scrollTop + (r.top - sr.top) - 16;
    stage.scrollTo({ top: top < 0 ? 0 : top, behavior: behavior || 'smooth' });
  }
  // Page turns land INSTANTLY (behavior 'auto'). A smooth scroll across a tall page
  // reads as a slow drift rather than a page turn, and it drags the page indicator
  // through every page it passes — real PDF viewers snap.
  function gotoPage(n) { if (!V.pdf || n < 1 || n > V.pages) return; V.page = n; updatePager(); scrollThumb(); scrollToPage(n, 'auto'); }
  function turnPage(d) { gotoPage(Math.min(V.pages, Math.max(1, V.page + d))); }
  function scrollThumb() { var t = doc.querySelector('.vthumb[data-page="' + V.page + '"]'); if (t) t.scrollIntoView({ block: 'nearest' }); }
  function setZoom(z) {
    var lo = ZOOM_STEPS[0], hi = ZOOM_STEPS[ZOOM_STEPS.length - 1];
    V.zoom = Math.max(lo, Math.min(hi, z));
    $('zoom-ind').textContent = Math.round(V.zoom * 100) + '%';
    relayout();
  }
  function zoomBy(d) {
    var i;
    if (d > 0) {
      for (i = 0; i < ZOOM_STEPS.length; i++) if (ZOOM_STEPS[i] > V.zoom + 1e-6) { setZoom(ZOOM_STEPS[i]); return; }
      setZoom(ZOOM_STEPS[ZOOM_STEPS.length - 1]); return;
    }
    for (i = ZOOM_STEPS.length - 1; i >= 0; i--) if (ZOOM_STEPS[i] < V.zoom - 1e-6) { setZoom(ZOOM_STEPS[i]); return; }
    setZoom(ZOOM_STEPS[0]);
  }
  function fitWidth() { setZoom(1.0); }
  function toggleInvert() { V.invert = !V.invert; $('vstage').classList.toggle('inverted', V.invert); setInvertBtn(V.invert); }
  function setInvertBtn(on) { var b = $('vh-invert'); b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); }
  function toggleFullscreen() { var on = $('overlay').classList.toggle('fs'); setFsBtn(on); if (V.pdf) setTimeout(relayout, 60); }
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
  /* The button IS the progress bar: a translucent fill sweeps across the control
     the reader is already looking at, and the label counts up. No new element and
     no new tokens — the question being answered ("is this working?") is about
     this button, so the answer belongs on it.

     We do NOT use `disabled` while busy: `.btn.primary:disabled` greys the
     control out, which reads as "unavailable" at exactly the moment we need it to
     read as "working". A guard flag blocks the double-click instead, and
     aria-busy/aria-disabled carry the state to assistive tech. */
  function setBtnBusy(btn, frac, got) {
    if (!btn) return;
    if (btn._rvLabel == null) btn._rvLabel = btn.innerHTML;
    if (frac === false) {                                  // finished — restore
      btn.innerHTML = btn._rvLabel; btn._rvLabel = null; btn._rvBg = null;
      btn.style.backgroundImage = ''; btn.style.backgroundRepeat = '';
      btn.style.backgroundSize = ''; btn.style.backgroundPosition = '';
      btn.removeAttribute('aria-busy'); btn.removeAttribute('aria-disabled');
      return;
    }
    var end = btn._rvLabel.indexOf('</svg>');
    var icon = end >= 0 ? btn._rvLabel.slice(0, end + 6) : '';
    var txt;
    if (frac == null) txt = T('Preparing…', '正在准备…');
    else if (frac < 0) txt = T('Downloading', '下载中') + ' ' + fmtBytes(got);   // no Content-Length
    else txt = T('Downloading', '下载中') + ' ' + Math.round(frac * 100) + '%';
    btn.innerHTML = icon + esc(txt);
    btn.setAttribute('aria-busy', 'true');
    btn.setAttribute('aria-disabled', 'true');
    // Inline so this works against the CURRENTLY BAKED page: this file is served
    // straight from site/ while the template needs a render lane to bake, so any
    // class we invented here would go live unstyled until the next render.
    //
    // LAYER over the button's own gradient, never replace it: `.btn.primary` sets
    // its brand gradient through the `background` SHORTHAND, so assigning
    // backgroundImage alone would erase it and leave a bare white bar. We read the
    // resolved gradient once and stack the fill in front of it, so this keeps
    // working if the button's palette is ever restyled.
    if (btn._rvBg == null) {
      var bg = '';
      try { bg = window.getComputedStyle(btn).backgroundImage || ''; } catch (e) {}
      btn._rvBg = (bg && bg !== 'none') ? bg : '';
    }
    var fill = 'linear-gradient(90deg,rgba(255,255,255,.28),rgba(255,255,255,.28))';
    btn.style.backgroundImage = btn._rvBg ? (fill + ',' + btn._rvBg) : fill;
    btn.style.backgroundRepeat = 'no-repeat,no-repeat';
    btn.style.backgroundPosition = 'left center,left center';
    btn.style.backgroundSize = ((frac > 0 ? frac : 0) * 100) + '% 100%,100% 100%';
  }

  /* Prefer the filename the server chose (a readable report title) over the
     opaque doc id. Same-origin, so Content-Disposition is readable. */
  function filenameFrom(resp, fallbackId) {
    try {
      var cd = resp.headers.get('Content-Disposition') || '';
      var m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
      if (m && m[1]) return decodeURIComponent(m[1].trim());
    } catch (e) {}
    return (fallbackId || 'research') + '.pdf';
  }

  function doDownload() {
    if (!V.item || V.dling) return;
    var btn = $('dl-btn-ok'), id = V.item.id;
    V.dling = true;
    setBtnBusy(btn, null);                                  // "Preparing…" until byte 1
    withAuth().then(function (h) { return fetch(API + '/api/research/download/' + encodeURIComponent(id), { method: 'POST', headers: h, credentials: 'include' }); })
      .then(function (resp) {
        if (resp.status === 402) { return resp.json().catch(function () { return {}; }).then(function (j) { showDlState(j && j.quota_exhausted ? 'max' : 'free'); return null; }); }
        if (resp.status === 401) { showDlState('anon'); return null; }
        if (resp.status === 429) { return null; }
        if (!resp.ok) return null;
        var name = filenameFrom(resp, id);
        return readWithProgress(resp, function (frac, got) { setBtnBusy(btn, frac, got); })
          .then(function (buf) {
            var url = URL.createObjectURL(new Blob([buf], { type: 'application/pdf' }));
            var a = doc.createElement('a'); a.href = url; a.download = name;
            doc.body.appendChild(a); a.click(); a.remove(); setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
          });
      })
      .catch(function () {})
      .then(function () { V.dling = false; setBtnBusy(btn, false); refreshQuota(); });
  }

  /* ═══════════ unread count ═══════════ */
  function updateUnread() {
    var n = ITEMS.filter(function (x) { return !DocState.isRead(x.id); }).length;
    $('unread-n').textContent = n;
    $('badge-latest').textContent = TOTAL_COUNT;
    var picks = summaryNumber('highlighted');
    $('badge-picks').textContent = picks !== null ? picks : (CATALOG_PREVIEW ? '—' : ITEMS.filter(function (x) { return x.top; }).length);
    $('badge-saved').textContent = ITEMS.filter(function (x) { return DocState.isSaved(x.id); }).length;
  }

  /* ═══════════ hydrate + refresh ═══════════ */
  function finishCatalogPaint(source) {
    CATALOG_SOURCE = source;
    doc.documentElement.classList.remove('rv-awaiting-live');
    if (window.__rvShellTimer) { clearTimeout(window.__rvShellTimer); window.__rvShellTimer = null; }
    var shell = $('feed-shell'); if (shell) shell.setAttribute('aria-busy', 'false');
    var en = $('rv-status-en'), cn = $('rv-status-zh');
    if (source === 'snapshot') {
      if (en) en.textContent = 'Saved snapshot · live update unavailable';
      if (cn) cn.textContent = '已保存快照 · 实时更新暂不可用';
    } else {
      if (en) en.textContent = 'This week · Updated hourly';
      if (cn) cn.textContent = '本周 · 每小时更新';
    }
  }
  function ingest(catalog, source) {
    var items = (catalog && Array.isArray(catalog.items)) ? catalog.items : [];
    ITEMS = items.map(normItem);
    CATALOG_SUMMARY = catalog && catalog.summary && typeof catalog.summary === 'object' ? catalog.summary : null;
    var aggregateTotal = summaryNumber('total');
    TOTAL_COUNT = Math.max(ITEMS.length, Number(catalog && catalog.count) || 0, aggregateTotal || 0);
    CATALOG_PREVIEW = !!(catalog && catalog.preview) || TOTAL_COUNT > ITEMS.length;
    buildInstFacets(); buildThemeFacets();
    buildTree(); updateHero(); updateUnread(); renderFeed();
    finishCatalogPaint(source || 'live');
    openDeepLink();
  }
  function hydrateFromBake() {
    var el = $('rv-catalog'); if (!el) return;
    try { ingest(JSON.parse(el.textContent || '{}'), 'snapshot'); return true; }
    catch (e) { ingest({ items: [] }, 'snapshot'); return false; }
  }
  function refreshFromApi() {
    var req = ++CATALOG_REQ;
    if (CATALOG_ABORT) { try { CATALOG_ABORT.abort(); } catch (e) {} }
    var ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    CATALOG_ABORT = ctrl;
    var timeout = null;
    var request = Promise.resolve().then(function () { return withAuth(); }).then(function (h) {
        var opts = { headers: h, credentials: 'include', cache: 'no-store' };
        if (ctrl) opts.signal = ctrl.signal;
        return fetch(API + '/api/research/catalog', opts);
      })
      .then(function (r) {
        if (req !== CATALOG_REQ) return null;
        if (!r.ok) throw new Error('catalog ' + r.status);
        return r.json();
      })
      .then(function (j) {
        if (req !== CATALOG_REQ) return false;
        if (!j || !Array.isArray(j.items)) throw new Error('invalid catalog payload');
        ingest(j, j.stale ? 'snapshot' : 'live');
        return true;
      });
    // Cover auth bootstrap as well as network/body time. AbortController alone
    // cannot settle a hung withAuth() promise, which could otherwise leave the
    // first-paint shell spinning until the independent bundle-failure timer.
    var deadline = new Promise(function (_resolve, reject) {
      timeout = setTimeout(function () {
        if (ctrl) ctrl.abort();
        reject(new Error('catalog timeout'));
      }, 10000);
    });
    return Promise.race([request, deadline])
      .catch(function () {
        if (req === CATALOG_REQ && CATALOG_SOURCE === 'loading') hydrateFromBake();
        return false;
      })
      .then(function (ok) {
        if (timeout) clearTimeout(timeout);
        if (req === CATALOG_REQ && CATALOG_ABORT === ctrl) CATALOG_ABORT = null;
        return ok;
      });
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
      var showMore = e.target.closest('[data-act="more"]');
      if (showMore) { shownN += PAGE_SIZE; renderFeed(); return; }   // reveal the next page
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
      var viewEl = e.target.closest('[data-act="view"]');
      if (viewEl) {
        // the title is a real <a href="research/<slug>.html"> for SEO/crawlers/
        // right-click; for a left-click with JS we open the in-app viewer instead.
        if (viewEl.tagName === 'A') e.preventDefault();
        openViewer(id);
      }
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
    $('vthumbs').addEventListener('click', function (e) { var b = e.target.closest('.vthumb'); if (b) gotoPage(+b.getAttribute('data-page')); });
    $('zoom-in').addEventListener('click', function () { zoomBy(1); });
    $('zoom-out').addEventListener('click', function () { zoomBy(-1); });
    $('fit-w').addEventListener('click', fitWidth);
    $('dl-btn-ok').addEventListener('click', doDownload);
    $('dl-btn-anon').addEventListener('click', openLatestSignin);
    $('vrelated').addEventListener('click', function (e) { var b = e.target.closest('[data-open]'); if (b) openViewer(b.getAttribute('data-open')); });
    // in-document find: live search as you type, Enter/Shift+Enter to step matches
    var _findTimer = null;
    $('vh-find-in').addEventListener('input', function () {
      var q = this.value;
      clearTimeout(_findTimer);
      _findTimer = setTimeout(function () { runFind(q); }, 180);
    });
    $('vh-find-in').addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      clearTimeout(_findTimer);
      var q = this.value;
      // Enter re-runs a changed query, otherwise it steps to the next/previous match
      if (q.trim() && q !== V.find.q) runFind(q);
      else stepHit(e.shiftKey ? -1 : 1);
    });
    $('vh-find-prev').addEventListener('click', function () { stepHit(-1); });
    $('vh-find-next').addEventListener('click', function () { stepHit(1); });
    // overlay click-out + keyboard (Esc / arrows / focus-trap)
    $('overlay').addEventListener('click', function (e) { if (e.target === this) closeViewer(); });
    doc.addEventListener('keydown', onKeydown);
    // language switch (theme.js flips [data-lang]; observe it)
    var mo = new MutationObserver(function () { onLangChange(); });
    mo.observe(doc.documentElement, { attributes: true, attributeFilter: ['data-lang'] });
    // re-render feed on auth resolve so the teaser + quota/gate reflect the real session
    function onAuthResolved() {
      resolveTier();   // sets USER_TIER → re-renders the feed (teaser for non-Pro)
      refreshFromApi(); // auth may change the catalog from the 3-item preview to full Pro
      if ($('overlay').classList.contains('open')) { refreshQuota(); if (!V.pdf) loadDocument(V.item); }
    }
    // window.MDXAuth is defined by theme.js. Since USER_TIER fails CLOSED ('anon'),
    // missing this registration pins EVERY viewer — Pro included — on the public
    // 3-summary preview forever, because nothing else ever calls resolveTier().
    // Both scripts ship deferred (lib.pages.optimize_assets_text adds `defer`), so
    // whichever tag comes first in the document wins; if theme.js has not executed
    // yet, register on 'load' instead — the same fallback shape site/mm_brain.js
    // boot() uses. MDXAuth.onChange replays the settled session, so a listener
    // registered late still receives it.
    if (window.MDXAuth && window.MDXAuth.onChange) window.MDXAuth.onChange(onAuthResolved);
    else window.addEventListener('load', function () {
      if (window.MDXAuth && window.MDXAuth.onChange) window.MDXAuth.onChange(onAuthResolved);
      // Ensure there is still an anonymous request if auth never initialized, and
      // redo the gated reads if it did. The newest-request guard safely collapses a
      // synchronous onChange replay with this load fallback.
      resolveTier();
      refreshFromApi();
    });
  }

  function onKeydown(e) {
    if (!$('overlay').classList.contains('open')) return;
    var inField = /^(INPUT|TEXTAREA)$/.test((e.target.tagName || ''));
    if (e.key === 'Escape') {
      // Escape with a live search clears the search first — closing the whole
      // document out from under someone who only wanted to drop the query is a
      // surprise (Preview/Books both dismiss the find bar first).
      if (V.find.q || (inField && e.target.id === 'vh-find-in' && e.target.value)) { resetFind(); return; }
      closeViewer(); return;
    }
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

  /* ═══════════ in-document find ═══════════
     A real find controller (Preview / Apple Books shape): every match in the
     document, a live count, next/prev step-through, and a highlight box drawn over
     the page.

     The pages are bare <canvas> (no pdf.js text layer), so match geometry is
     derived from getTextContent() item transforms: each hit's rectangles are stored
     in scale-1 viewport units and multiplied by the live zoom at paint time, so a
     zoom change never needs a re-scan. Per-page indexes are cached — a 60-page PDF
     is scanned once, not once per keystroke. */

  function resetFind() {
    V.find = { q: '', tok: 0, hits: [], byPage: {}, idx: -1 };
    V.textIx = {};
    clearHighlights();
    var i = $('vh-find-in'); if (i) i.value = '';
    updateFindUI();
  }
  function clearHighlights() {
    doc.querySelectorAll('.vhl-layer').forEach(function (l) { l.remove(); });
  }

  /* Per-page search index: a normalized string (lowercased, whitespace runs
     collapsed) plus a map back to the raw character origins, so a hit in the
     normalized text can be resolved to the exact text items it covers. */
  function pageIndex(p) {
    if (V.textIx[p]) return Promise.resolve(V.textIx[p]);
    if (!V.pdf) return Promise.reject(new Error('no document'));
    return V.pdf.getPage(p).then(function (page) {
      return page.getTextContent().then(function (tc) {
        var vp = page.getViewport({ scale: 1 });
        var raw = '', origin = [], prev = null;
        tc.items.forEach(function (it) {
          var s = it.str || '';
          // pdf.js emits one item per text run. A run usually carries its own
          // spaces, but a run boundary with a real horizontal gap (or a line end)
          // is a word break the concatenation would otherwise swallow — insert a
          // separator so a phrase query still matches across the boundary.
          if (prev && raw && !/\s$/.test(raw) && !/^\s/.test(s)) {
            var gap = it.transform[4] - (prev.transform[4] + (prev.width || 0));
            if (prev.hasEOL || gap > (prev.height || 10) * 0.18) { raw += ' '; origin.push(null); }
          }
          for (var c = 0; c < s.length; c++) { raw += s[c]; origin.push({ it: it, off: c }); }
          if (it.hasEOL && !/\s$/.test(raw)) { raw += '\n'; origin.push(null); }
          prev = it;
        });
        var norm = '', n2r = [], ws = true;
        for (var k = 0; k < raw.length; k++) {
          var ch = raw[k];
          if (/\s/.test(ch)) { if (!ws) { norm += ' '; n2r.push(k); ws = true; } }
          else { norm += ch.toLowerCase(); n2r.push(k); ws = false; }
        }
        var rec = { norm: norm, n2r: n2r, origin: origin, vp: vp };
        V.textIx[p] = rec; return rec;
      });
    });
  }

  /* Rectangles (scale-1 viewport units) covering normalized range [a, b). One rect
     per text item the hit spans; the sub-string slice is proportional within the
     item, which is what makes a mid-run match highlight only its own characters. */
  function rectsFor(rec, a, b) {
    var runs = [], k, o;
    for (k = a; k < b && k < rec.n2r.length; k++) {
      o = rec.origin[rec.n2r[k]];
      if (!o) continue;                                    // synthetic separator
      var last = runs[runs.length - 1];
      if (last && last.it === o.it && o.off === last.o2 + 1) last.o2 = o.off;
      else runs.push({ it: o.it, o1: o.off, o2: o.off });
    }
    var out = [];
    runs.forEach(function (r) {
      var it = r.it, s = it.str || '', len = s.length || 1;
      var tx = (_pdfLib && _pdfLib.Util)
        ? _pdfLib.Util.transform(rec.vp.transform, it.transform)
        : null;
      if (!tx) return;
      var fh = Math.sqrt(tx[1] * tx[1] + tx[3] * tx[3]) || Math.abs(tx[3]) || 10;
      var cw = (it.width || 0) / len;
      var x = tx[4] + cw * r.o1, w = cw * (r.o2 - r.o1 + 1);
      if (!(w > 0)) return;
      out.push({ x: x, y: tx[5] - fh, w: w, h: fh * 1.18 });
    });
    return out;
  }

  function paintHighlights(p) {
    var el = V.pageEls && V.pageEls[p - 1]; if (!el) return;
    var hits = V.find.byPage[p], layer = el.querySelector('.vhl-layer');
    if (!hits || !hits.length) { if (layer) layer.remove(); return; }
    if (!layer) { layer = doc.createElement('div'); layer.className = 'vhl-layer'; el.appendChild(layer); }
    var s = (V.fitScale || 1) * V.zoom, cur = V.find.hits[V.find.idx], html = '';
    hits.forEach(function (h) {
      var on = (h === cur) ? ' cur' : '';
      h.rects.forEach(function (r) {
        html += '<i class="vhl' + on + '" style="left:' + (r.x * s).toFixed(1) + 'px;top:' + (r.y * s).toFixed(1)
             + 'px;width:' + (r.w * s).toFixed(1) + 'px;height:' + (r.h * s).toFixed(1) + 'px"></i>';
      });
    });
    layer.innerHTML = html;
  }
  function repaintHighlights() {
    Object.keys(V.find.byPage).forEach(function (p) { paintHighlights(+p); });
  }

  function updateFindUI() {
    var box = $('vh-find-count'), prev = $('vh-find-prev'), next = $('vh-find-next');
    if (!box) return;
    var n = V.find.hits.length;
    if (!V.find.q) { box.textContent = ''; box.classList.remove('none'); }
    else if (!n) { box.textContent = T('No results', '无结果'); box.classList.add('none'); }
    else { box.textContent = (V.find.idx + 1) + ' / ' + n; box.classList.remove('none'); }
    if (prev) prev.disabled = !n;
    if (next) next.disabled = !n;
  }

  function scrollToHit(h) {
    var el = V.pageEls && V.pageEls[h.page - 1], stage = $('vstage');
    if (!el || !stage) return;
    var s = (V.fitScale || 1) * V.zoom, r = h.rects[0];
    var pr = el.getBoundingClientRect(), sr = stage.getBoundingClientRect();
    var y = pr.top - sr.top + (r ? r.y * s : 0);
    // park the hit ~35% down the stage rather than at the very top — the
    // surrounding lines are what make a match readable in context
    var top = stage.scrollTop + y - stage.clientHeight * 0.35;
    stage.scrollTo({ top: top < 0 ? 0 : top, behavior: 'auto' });
  }

  function gotoHit(i) {
    var n = V.find.hits.length; if (!n) return;
    V.find.idx = ((i % n) + n) % n;
    var h = V.find.hits[V.find.idx];
    if (V.page !== h.page) { V.page = h.page; updatePager(); scrollThumb(); }
    scrollToHit(h);
    repaintHighlights();
    updateFindUI();
  }
  function stepHit(d) { if (V.find.hits.length) gotoHit(V.find.idx + d); }

  function runFind(q) {
    var tok = ++V.find.tok;
    clearHighlights();
    V.find.q = q; V.find.hits = []; V.find.byPage = {}; V.find.idx = -1;
    var nq = (q || '').toLowerCase().replace(/\s+/g, ' ').trim();
    if (!nq || !V.pdf) { updateFindUI(); return; }
    var p = 1;
    (function step() {
      if (tok !== V.find.tok) return;                       // superseded by a newer query
      if (p > V.pages) { updateFindUI(); return; }
      var cur = p++;
      pageIndex(cur).then(function (rec) {
        if (tok !== V.find.tok) return;
        var from = 0, i;
        while ((i = rec.norm.indexOf(nq, from)) >= 0) {
          var hit = { page: cur, rects: rectsFor(rec, i, i + nq.length) };
          V.find.hits.push(hit);
          (V.find.byPage[cur] = V.find.byPage[cur] || []).push(hit);
          from = i + nq.length;
        }
        if (V.find.byPage[cur]) {
          paintHighlights(cur);
          if (V.find.idx < 0) gotoHit(0);                   // jump to the first hit as soon as it exists
        }
        updateFindUI();
        step();
      }).catch(function () { if (tok === V.find.tok) step(); });
    })();
  }

  /* deep link from a report landing page: research_vault.html?doc=<id> opens that
     report's viewer (Pro → PDF, non-Pro → the upgrade gate). This is the SEO
     funnel's landing → conversion hop. */
  var DEEP_LINK_OPENED = false;
  function openDeepLink() {
    if (DEEP_LINK_OPENED) return;
    try {
      var m = /[?&]doc=([^&]+)/.exec(location.search);
      if (!m) return;
      var id = decodeURIComponent(m[1]);
      if (ITEMS.some(function (x) { return x.id === id; })) { DEEP_LINK_OPENED = true; openViewer(id); }
    } catch (e) {}
  }

  /* ═══════════ boot ═══════════ */
  function boot() {
    var shell = $('feed-shell'); if (shell) shell.setAttribute('aria-busy', 'true');
    wire();
    // The baked catalog is deliberately a fallback only. It can lag the hourly API
    // by many hours, so painting it as current creates a false-data flash. Keep the
    // neutral shell until the newest live/authenticated request wins; on failure,
    // refreshFromApi() exposes the bake with an explicit saved-snapshot label.
    if (window.MDXAuth && window.MDXAuth.client) refreshFromApi();
    else if (doc.readyState === 'complete') refreshFromApi();
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

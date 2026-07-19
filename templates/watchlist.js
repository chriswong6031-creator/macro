/* watchlist.js — the Holdings Watchlist app.

   Architecture keystone: we persist the SELECTION (a list of ticker symbols),
   never the DATA. Every name/state/signal is re-resolved live from the nightly
   stockdata/index.json (+ optional per-ticker JSON) on each load, so a saved
   list can never go stale across the nightly rebuild. The list lives in a single
   versioned localStorage blob; an optional cloud adapter (watchstore.js) can later
   sync the SAME blob shape without touching this file's UI.

   Depends on stockdata.js (window.SD) and mtf.js (window.renderMTF). Exposes
   window.WL as the store seam watchstore.js plugs into. */
(function () {
  'use strict';

  var KEY = 'mdash.watchlist.v1';
  // states that mean "a low/buy is near" — the bottoming / buy-soon cohort the
  // user explicitly cares about (drives the accent border + header counter)
  var BUYSOON = { 'TURN SIGNALED': 1, 'FRESH BUY': 1, 'BOTTOM WATCH': 1 };
  // signal-sort priority: best setups first, risk last
  var STATE_RANK = {
    'FRESH BUY': 0, 'TURN SIGNALED': 1, 'BOTTOM WATCH': 2, 'RALLY ON': 3,
    'TOP WATCH': 4, 'ROLLING OVER': 5, 'COUNTERTREND BOUNCE': 6, 'DECLINE': 7
  };

  // ---- micro-i18n for the JS-rendered scaffolding -------------------------
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  var T = {
    en: {
      empty: 'Your watchlist is empty. Search above to add a holding — equity, ETF, commodity or crypto.',
      starters: 'Quick add:', removeA: 'Remove from watchlist',
      buysoonN: function (n) { return n + (n === 1 ? ' nearing a buy' : ' nearing a buy'); },
      ph: 'Add a holding… (e.g. AAPL, Energy, Gold, Bitcoin)',
      unavailable: 'temporarily unavailable', unavailMsg: 'not in tonight’s library — may return after the next nightly build',
      sortOrder: 'My order', sortAdded: 'Recently added', sortName: 'Name',
      sortSector: 'Sector', sortSignal: 'Signal', sortLabel: 'Sort',
      buysoonOnly: 'Buy-soon only', share: 'Export / import', copy: 'Copy share link',
      copied: 'Link copied', exportLbl: 'Your watchlist code', importLbl: 'Paste a code to import (merges)',
      importBtn: 'Import', imported: function (n) { return 'Imported ' + n + ' ticker' + (n === 1 ? '' : 's'); },
      importBad: 'Could not read that watchlist code', noStore: 'Your browser is blocking local storage (private mode?). This list will reset when you close the tab — use Export to save it.',
      asof: 'as of', added: 'added'
    },
    zh: {
      empty: '清单为空。在上方搜索以添加持仓——股票、ETF、大宗商品或加密货币。',
      starters: '快速添加：', removeA: '从清单移除',
      buysoonN: function (n) { return n + ' 接近买点'; },
      ph: '添加持仓…（例如 AAPL、Energy、Gold、Bitcoin）',
      unavailable: '暂不可用', unavailMsg: '不在今晚的标的库中——下次夜间构建后可能恢复',
      sortOrder: '我的顺序', sortAdded: '最近添加', sortName: '名称',
      sortSector: '板块', sortSignal: '信号', sortLabel: '排序',
      buysoonOnly: '仅看接近买点', share: '导出 / 导入', copy: '复制分享链接',
      copied: '链接已复制', exportLbl: '你的清单代码', importLbl: '粘贴代码以导入（合并）',
      importBtn: '导入', imported: function (n) { return '已导入 ' + n + ' 个标的'; },
      importBad: '无法读取该清单代码', noStore: '你的浏览器禁用了本地存储（无痕模式？）。关闭标签页后此清单将清空——请用“导出”保存。',
      asof: '数据截至', added: '添加于'
    }
  };
  function L(k) { return (T[lang()] || T.en)[k]; }

  // ---- tiny utilities -----------------------------------------------------
  function nowISO() { return new Date().toISOString(); }
  function debounce(fn, ms) {
    var h; return function () { var a = arguments, t = this;
      clearTimeout(h); h = setTimeout(function () { fn.apply(t, a); }, ms); };
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  // base64url over a UTF-8 JSON string (notes may be non-ASCII)
  function b64enc(str) {
    return btoa(unescape(encodeURIComponent(str)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function b64dec(s) {
    s = s.replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    return decodeURIComponent(escape(atob(s)));
  }

  // ---- the store: single versioned blob, in-memory mirror, safe persistence
  var storageOK = true;     // flips false on the first failed write (private mode/quota)
  var blob = defaultBlob();

  function defaultBlob() {
    return { v: 1, updated: nowISO(), items: [], order: [],
             settings: { sort: 'order', buySoonOnly: false } };
  }
  // tolerate older/partial shapes: default-fill rather than assume structure
  function migrate(raw) {
    if (!raw || typeof raw !== 'object') return defaultBlob();
    var b = defaultBlob();
    b.v = 1;
    b.updated = typeof raw.updated === 'string' ? raw.updated : nowISO();
    b.items = Array.isArray(raw.items) ? raw.items.filter(function (it) {
      return it && typeof it.t === 'string' && it.t;
    }).map(function (it) {
      return { t: it.t, added: typeof it.added === 'string' ? it.added : nowISO(),
               note: typeof it.note === 'string' ? it.note : '' };
    }) : [];
    var have = {}; b.items.forEach(function (it) { have[it.t] = 1; });
    b.order = (Array.isArray(raw.order) ? raw.order : []).filter(function (t) { return have[t]; });
    b.items.forEach(function (it) { if (b.order.indexOf(it.t) < 0) b.order.push(it.t); });
    if (raw.settings && typeof raw.settings === 'object') {
      b.settings.sort = raw.settings.sort || b.settings.sort;
      b.settings.buySoonOnly = !!raw.settings.buySoonOnly;
    }
    return b;
  }
  function readStorage() {
    try {
      var raw = localStorage.getItem(KEY);
      return raw ? migrate(JSON.parse(raw)) : defaultBlob();
    } catch (e) { return defaultBlob(); }
  }
  var persist = debounce(function () {
    try {
      localStorage.setItem(KEY, JSON.stringify(blob));
      if (!storageOK) { storageOK = true; hideBanner(); }
    } catch (e) {
      // quota / private mode: keep working in-memory but tell the user once
      storageOK = false; showBanner(L('noStore'));
    }
  }, 200);

  function touch() { blob.updated = nowISO(); persist(); }
  // canonical signature of the user-meaningful state — everything EXCEPT `updated`.
  // Lets a sync that changes nothing be a true no-op: without this, an identical
  // peer doc re-bumps `updated` + re-persists on every storage event, so two open
  // tabs ping-pong writes forever (the watchlist "spasm" — constant re-render +
  // re-fetch as each tab's write retriggers the other's storage handler).
  function stateSig(b) {
    var its = b.items.map(function (it) {
      return [it.t, it.added || '', it.note || ''];
    }).sort(function (a, c) { return a[0] < c[0] ? -1 : a[0] > c[0] ? 1 : 0; });
    return JSON.stringify([its, b.order || [], b.settings.sort, !!b.settings.buySoonOnly]);
  }
  function has(t) { return blob.items.some(function (it) { return it.t === t; }); }
  function add(t) {
    if (!t || has(t)) return false;
    blob.items.push({ t: t, added: nowISO(), note: '' });
    blob.order.push(t);
    touch(); return true;
  }
  function remove(t) {
    blob.items = blob.items.filter(function (it) { return it.t !== t; });
    blob.order = blob.order.filter(function (x) { return x !== t; });
    touch();
  }
  function setSetting(k, v) { blob.settings[k] = v; touch(); }

  // union by ticker (earliest `added`, keep non-empty note); newer `updated`
  // wins order/settings. Shared by import, cross-tab sync, and the cloud adapter.
  function mergeInto(other) {
    if (!other || !Array.isArray(other.items)) return 0;
    var before = blob.items.length, sigBefore = stateSig(blob), byT = {};
    blob.items.forEach(function (it) { byT[it.t] = it; });
    other.items.forEach(function (it) {
      if (!it || !it.t) return;
      var e = byT[it.t];
      if (!e) { byT[it.t] = { t: it.t, added: it.added || nowISO(), note: it.note || '' };
                blob.items.push(byT[it.t]); }
      else {
        if (it.added && (!e.added || it.added < e.added)) e.added = it.added;
        if (!e.note && it.note) e.note = it.note;
      }
    });
    var newer = (other.updated || '') > (blob.updated || '') ? other : blob;
    var order = (newer.order || []).filter(function (t) { return byT[t]; });
    blob.items.forEach(function (it) { if (order.indexOf(it.t) < 0) order.push(it.t); });
    blob.order = order;
    if (newer.settings) blob.settings = {
      sort: newer.settings.sort || blob.settings.sort,
      buySoonOnly: !!newer.settings.buySoonOnly
    };
    // Persist + bump `updated` ONLY when the user-meaningful state actually moved.
    // An identical peer doc (the common case for a cross-tab echo) leaves the
    // signature unchanged → no write → no storage event back to the other tab →
    // the ping-pong can't sustain. A genuinely different peer still converges in
    // one extra round (both adopt the union, then the next echo is a no-op).
    if (stateSig(blob) !== sigBefore) { blob.updated = nowISO(); persist(); }
    return blob.items.length - before;
  }

  // ---- DOM refs (populated on init) ---------------------------------------
  var idxBy = {}, listEl, countEl, sugg, q, observer, sel = -1, sItems = [];

  // ---- rendering ----------------------------------------------------------
  // ordered + filtered view of the watched items, resolved against the index
  function viewItems() {
    var sort = blob.settings.sort, only = blob.settings.buySoonOnly;
    var rows = blob.items.map(function (it) {
      var rec = idxBy[it.t] || null;          // null => dropped out of the library
      return { t: it.t, added: it.added, rec: rec,
               st: rec ? rec.st : null, n: rec ? rec.n : it.t, s: rec ? rec.s : '' };
    });
    if (only) rows = rows.filter(function (r) { return r.st && BUYSOON[r.st]; });
    var ord = blob.order;
    rows.sort(function (a, b) {
      if (sort === 'name') return a.n.localeCompare(b.n);
      if (sort === 'sector') return (a.s || '~').localeCompare(b.s || '~') || a.t.localeCompare(b.t);
      if (sort === 'added') return (b.added || '').localeCompare(a.added || '');
      if (sort === 'signal') {
        var ra = a.st in STATE_RANK ? STATE_RANK[a.st] : 99;
        var rb = b.st in STATE_RANK ? STATE_RANK[b.st] : 99;
        return ra - rb || a.t.localeCompare(b.t);
      }
      return ord.indexOf(a.t) - ord.indexOf(b.t);   // 'order'
    });
    return rows;
  }

  function buysoonCount() {
    var n = 0;
    blob.items.forEach(function (it) {
      var rec = idxBy[it.t]; if (rec && BUYSOON[rec.st]) n++;
    });
    return n;
  }

  function cardHTML(r) {
    var safe = esc(r.t);
    if (!r.rec) {
      // Tier-1 drop-out: never silently omit a watched ticker
      return '<div class="wl-card wl-gone" data-t="' + safe + '">' +
        '<div class="wl-top"><a class="wl-name" href="stock.html#' + encodeURIComponent(r.t) +
        '"><b>' + safe + '</b></a>' + rmBtn(r.t) + '</div>' +
        '<div class="wl-sig"><span class="state pill-stale">' + esc(L('unavailable')) +
        '</span><span class="muted wl-note">' + esc(L('unavailMsg')) + '</span></div></div>';
    }
    var stc = window.SD.stClass(r.st);
    var lbl = window.SD.label(r.st), act = window.SD.action(r.st);
    var soon = BUYSOON[r.st] ? ' wl-buysoon' : '';
    return '<div class="wl-card ' + stc + soon + '" data-t="' + safe + '">' +
      '<div class="wl-top">' +
        '<a class="wl-name" href="stock.html#' + encodeURIComponent(r.t) + '">' +
          '<b>' + safe + '</b> <span class="wl-cn muted">' + esc(r.n) + '</span></a>' +
        rmBtn(r.t) +
      '</div>' +
      '<div class="wl-sig">' +
        '<span class="state ' + stc + '">' + esc(lbl) + '</span>' +
        (act ? '<span class="wl-action muted">' + esc(act) + '</span>' : '') +
        (r.s ? '<span class="wl-sector muted">' + esc(r.s) + '</span>' : '') +
      '</div>' +
      '<div class="wl-enrich" data-enrich="' + safe + '"></div>' +
    '</div>';
  }
  function rmBtn(t) {
    return '<button class="wl-rm" data-rm="' + esc(t) + '" title="' + esc(L('removeA')) +
      '" aria-label="' + esc(L('removeA')) + '">✕</button>';
  }

  function render() {
    if (!listEl) return;
    // feed the Portfolio Factor Exposure panel the current holdings (factor_exposure.js)
    if (window.FX) window.FX.update(blob.items.map(function (it) { return it.t; }));
    var rows = viewItems();
    // header counter
    var n = buysoonCount();
    countEl.innerHTML = n ? '<span class="wl-soonpill">▲ ' + esc(L('buysoonN')(n)) + '</span>' : '';
    // empty state vs grid
    var empty = document.getElementById('wl_empty');
    if (!blob.items.length) {
      listEl.innerHTML = ''; empty.style.display = 'block'; renderStarters();
      document.getElementById('wl_controls').style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    document.getElementById('wl_controls').style.display = 'flex';
    listEl.innerHTML = rows.map(cardHTML).join('');
    // (re)observe enrich hosts for lazy detail loading
    wireEnrich();
  }

  // ---- lazy Tier-2 enrichment (entry cue + momentum strip) ----------------
  function wireEnrich() {
    if (observer) observer.disconnect();
    if (!('IntersectionObserver' in window)) {  // no IO: enrich everything now
      listEl.querySelectorAll('[data-enrich]').forEach(enrich); return;
    }
    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        observer.unobserve(e.target);
        var host = e.target.querySelector('[data-enrich]');  // the (zero-height) enrich slot
        if (host) enrich(host);
      });
    }, { rootMargin: '150px' });
    // observe the CARD (it has real height — the enrich slot is 0px until filled)
    listEl.querySelectorAll('.wl-card').forEach(function (c) { observer.observe(c); });
  }
  function enrich(el) {
    var t = el.getAttribute('data-enrich');
    window.SD.loadTicker(t).then(function (j) {
      el.__json = j;        // cache raw JSON so a language flip re-renders w/o refetch
      paintEnrich(el, j);
    });
  }
  function paintEnrich(el, j) {
    if (!j || !j.ladder) { el.innerHTML = ''; return; }
    var lad = j.ladder, e = lad.entry || {};
    var html = '';
    var summ = window.SD.lz(lad.summary_line, lad.summary_line_zh);
    if (summ) html += '<div class="wl-summary muted">' + esc(summ) + '</div>';
    if (e.urgency || e.text) {
      html += '<div class="wl-entry urgpill urg-' + esc(e.urgency || 'hold') + '">' +
        (e.tag ? '<span class="wl-etag">' + esc(e.tag) + '</span>' : '') +
        '<span>' + esc(window.SD.lz(e.text, e.text_zh)) + '</span></div>';
    }
    if (j.tech && j.tech.price != null) {
      var off = j.tech.off_52w_high_pct;
      html += '<div class="wl-px muted">' + esc('$' + j.tech.price) +
        (off != null ? ' · <span class="' + (off < 0 ? 'neg' : 'pos') + '">' +
          (off > 0 ? '+' : '') + off + '% ' + (lang() === 'zh' ? '距52周高' : 'off 52w high') + '</span>' : '') +
        (j.asof ? ' · ' + esc(L('asof')) + ' ' + esc(j.asof) : '') + '</div>';
    }
    html += '<div class="wl-mtf" data-mtf=\'' + esc(JSON.stringify(j.mtf || {})) + '\'></div>';
    el.innerHTML = html;
    var host = el.querySelector('.wl-mtf');
    if (host && window.renderMTF && j.mtf) { try { window.renderMTF(host, j.mtf); } catch (x) {} }
  }
  // re-derive enriched text/colors in the current language/theme without refetch
  function repaintEnriched() {
    if (!listEl) return;
    listEl.querySelectorAll('[data-enrich]').forEach(function (el) {
      if ('__json' in el) paintEnrich(el, el.__json);
    });
  }

  // ---- search-to-add (cloned from the stock analyzer) ---------------------
  function wireSearch(list) {
    q.placeholder = L('ph');
    q.addEventListener('input', function () {
      var v = q.value.trim().toLowerCase(); sel = -1;
      if (!v) { sugg.style.display = 'none'; return; }
      sItems = list.filter(function (x) {
        return x.t.toLowerCase().indexOf(v) === 0 ||
               x.n.toLowerCase().indexOf(v) >= 0 || x.s.toLowerCase().indexOf(v) >= 0;
      }).sort(function (a, b) {
        var ae = a.t.toLowerCase() === v ? -1 : 0, be = b.t.toLowerCase() === v ? -1 : 0;
        if (ae !== be) return ae - be;
        var ap = a.t.toLowerCase().indexOf(v) === 0 ? 0 : 1,
            bp = b.t.toLowerCase().indexOf(v) === 0 ? 0 : 1;
        return ap - bp || a.t.localeCompare(b.t);
      }).slice(0, 12);
      sugg.innerHTML = sItems.map(function (x, i) {
        var inList = has(x.t) ? ' ✓' : '';
        return '<div data-i="' + i + '"><b>' + esc(x.t) + '</b><small>' + esc(x.n) +
          (x.s ? ' · ' + esc(x.s) : '') + '</small><span class="muted wl-sst">' +
          esc(window.SD.label(x.st)) + inList + '</span></div>';
      }).join('');
      sugg.style.display = sItems.length ? 'block' : 'none';
    });
    q.addEventListener('keydown', function (e) {
      if (sugg.style.display === 'none') return;
      var divs = sugg.querySelectorAll('div');
      if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, divs.length - 1); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); e.preventDefault(); }
      else if (e.key === 'Enter') { pick(sel >= 0 ? sel : 0); e.preventDefault(); return; }
      else if (e.key === 'Escape') { sugg.style.display = 'none'; return; }
      divs.forEach(function (d, i) { d.classList.toggle('sel', i === sel); });
    });
    sugg.addEventListener('mousedown', function (e) {
      var d = e.target.closest('div[data-i]'); if (d) pick(+d.dataset.i);
    });
  }
  function pick(i) {
    var x = sItems[i]; if (!x) return;
    sugg.style.display = 'none'; q.value = '';
    if (add(x.t)) { render(); pushCloud(); }
  }

  // ---- view controls ------------------------------------------------------
  function wireControls() {
    var sortSel = document.getElementById('wl_sort');
    var only = document.getElementById('wl_buysoon');
    function syncLabels() {
      sortSel.options[0].text = L('sortOrder'); sortSel.options[1].text = L('sortAdded');
      sortSel.options[2].text = L('sortName'); sortSel.options[3].text = L('sortSector');
      sortSel.options[4].text = L('sortSignal');
      document.getElementById('wl_sortlbl').textContent = L('sortLabel');
      document.getElementById('wl_buysoonlbl').textContent = L('buysoonOnly');
    }
    syncLabels();
    sortSel.value = blob.settings.sort;
    only.checked = !!blob.settings.buySoonOnly;
    sortSel.addEventListener('change', function () { setSetting('sort', sortSel.value); render(); pushCloud(); });
    only.addEventListener('change', function () { setSetting('buySoonOnly', only.checked); render(); pushCloud(); });
    document.addEventListener('langchange', syncLabels);
  }

  // ---- export / import / share-link --------------------------------------
  function exportCode() { return b64enc(JSON.stringify(blob)); }
  function wireShare() {
    var ta = document.getElementById('wl_export');
    var imp = document.getElementById('wl_import');
    function refresh() { ta.value = exportCode(); }
    refresh();
    document.addEventListener('wl-changed', refresh);
    document.getElementById('wl_copylink').addEventListener('click', function () {
      var url = location.origin + location.pathname + '#wl=' + exportCode();
      var done = function () { toast(L('copied')); };
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, function () { ta.select(); });
      else { ta.value = url; ta.select(); document.execCommand && document.execCommand('copy'); refresh(); done(); }
    });
    document.getElementById('wl_importbtn').addEventListener('click', function () {
      importCode(imp.value.trim()); imp.value = '';
    });
  }
  function importCode(code) {
    if (!code) return;
    var other;
    try {
      var m = code.match(/#?wl=([^&]+)/);   // accept a full share URL or a bare code
      other = JSON.parse(b64dec(m ? m[1] : code));
    } catch (e) { toast(L('importBad'), true); return; }
    if (!other || typeof other !== 'object' || !Array.isArray(other.items)) { toast(L('importBad'), true); return; }
    var n = mergeInto(migrate(other));
    render(); pushCloud(); toast(L('imported')(n));
  }
  // a pasted share URL lands here on load — merge then strip the fragment
  function consumeShareHash() {
    var m = (location.hash || '').match(/^#wl=(.+)$/);
    if (!m) return;
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) {}
    importCode(m[1]);
  }

  // ---- empty-state starter chips (validated against the live index) -------
  function renderStarters() {
    var host = document.getElementById('wl_starters'); if (!host) return;
    var starters = (window.WL_STARTERS || []).filter(function (t) { return idxBy[t]; });
    if (!starters.length) { host.innerHTML = ''; return; }
    host.innerHTML = '<span class="muted">' + esc(L('starters')) + '</span> ' +
      starters.map(function (t) {
        return '<button class="wl-chip" data-add="' + esc(t) + '">' + esc(t) +
          ' <span class="muted">' + esc((idxBy[t] || {}).n || '') + '</span></button>';
      }).join('');
  }

  // ---- banners / toasts ---------------------------------------------------
  function showBanner(msg) {
    var b = document.getElementById('wl_banner'); if (!b) return;
    b.textContent = msg; b.style.display = 'block';
  }
  function hideBanner() { var b = document.getElementById('wl_banner'); if (b) b.style.display = 'none'; }
  var toastH;
  function toast(msg, bad) {
    var el = document.getElementById('wl_toast'); if (!el) return;
    el.textContent = msg; el.className = 'wl-toast' + (bad ? ' bad' : '') + ' show';
    clearTimeout(toastH); toastH = setTimeout(function () { el.className = 'wl-toast'; }, 2600);
  }

  // ---- cloud seam (watchstore.js attaches here; no-op when not configured) -------
  function pushCloud() {
    document.dispatchEvent(new CustomEvent('wl-changed'));
    if (window.WLCloud && window.WLCloud.push) window.WLCloud.push(blob);
  }

  // ---- cross-tab sync: another tab wrote -> reload + merge + render --------
  function onStorage(e) {
    if (e.key && e.key !== KEY) return;
    var sigBefore = stateSig(blob);
    mergeInto(readStorage());     // union, never blind-overwrite
    if (stateSig(blob) !== sigBefore) render();   // re-render only on a real peer change
  }

  // ---- public store API (the seam watchstore.js / cloud adapter plug into) -------
  window.WL = {
    getBlob: function () { return blob; },
    merge: function (other) { var n = mergeInto(migrate(other)); render(); return n; },
    replace: function (other) { blob = migrate(other); persist(); render(); },
    add: function (t) { if (add(t)) { render(); } },
    remove: function (t) { remove(t); render(); },
    render: render,
    onLocalChange: function (cb) { document.addEventListener('wl-changed', cb); }
  };

  // ---- init ---------------------------------------------------------------
  function init() {
    listEl = document.getElementById('wl_list');
    countEl = document.getElementById('wl_count');
    sugg = document.getElementById('wl_sugg');
    q = document.getElementById('wl_q');

    blob = readStorage();
    if (!storageProbe()) showBanner(L('noStore'));

    wireControls();
    wireShare();

    // event delegation: remove (✕) + starter chips
    document.addEventListener('click', function (e) {
      var rm = e.target.closest('[data-rm]');
      if (rm) { remove(rm.getAttribute('data-rm')); render(); pushCloud(); return; }
      var ad = e.target.closest('[data-add]');
      if (ad) { if (add(ad.getAttribute('data-add'))) { render(); pushCloud(); } }
    });

    window.addEventListener('storage', onStorage);
    document.addEventListener('themechange', repaintEnriched);
    document.addEventListener('langchange', function () { q.placeholder = L('ph'); render(); });

    // resolve the live universe, then first paint
    window.SD.loadIndex().then(function (r) {
      idxBy = r.byTicker;
      wireSearch(r.list);
      consumeShareHash();   // a #wl= link merges before first visible paint
      render();
    }).catch(function () { render(); });
  }

  // does setItem actually work? (Safari private mode throws on write, not read)
  function storageProbe() {
    try { localStorage.setItem(KEY + '.probe', '1'); localStorage.removeItem(KEY + '.probe');
      return true; } catch (e) { storageOK = false; return false; }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

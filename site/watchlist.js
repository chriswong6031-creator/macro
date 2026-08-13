/* watchlist.js — the Portfolio Intelligence workspace.

   Architecture keystone (unchanged since W0): we persist the SELECTION (a list of
   ticker symbols), never the DATA. Every name/state/signal is re-resolved live from
   the nightly stockdata index on each load, so a saved list can never go stale across
   the nightly rebuild. The list lives in a single versioned localStorage blob; the
   cloud adapter (watchstore.js) syncs the SAME blob shape without touching this file.

   W2 turns this file into the workspace CONTROLLER on top of that store:
     • two modes on one URL (Portfolio | Watchlists) driven by html[data-ws-mode]
     • the dense-table renderer + row drawer used by BOTH modes
     • the anonymous bulk-entry parser and the anonymous structure read (packet A9)
     • the header save-state chip (the Account Sync panel is deleted)
     • the Book Seam painter, published on window.WS for portfolio.js /
       watchlist_risk.js to feed — a signature drawn in ONE place

   Depends on stockdata.js (window.SD) and mtf.js (window.renderMTF), both of which
   are SIGNED-IN ONLY: the anonymous funnel shell boots without them and every read
   they would supply degrades to an honest blank or a lock shell, never a fake.
   Exposes window.WL as the store seam watchstore.js plugs into, and window.WS as the
   render seam the other workspace scripts plug into. */
(function () {
  'use strict';

  var KEY = 'mdash.watchlist.v1';

  /* ---- multi-list binding seam (W1a) ---------------------------------------
     `listId === null` is the ANONYMOUS / default binding: the storage key, the share
     fragment and every observable behaviour are byte-identical to the pre-W1a page.
     A non-null binding points the same blob machinery at that registered list's own
     cache `mdash.wl.<listId>.v1` — the exact key watchstore.js writes, in the exact
     same blob shape, so a rebind is a plain re-read. W2 is what finally drives it,
     through the list switcher in Watchlists mode. */
  var listId = null;
  var listName = '';

  function storageKey() { return listId ? ('mdash.wl.' + listId + '.v1') : KEY; }
  // share fragment: `#wl=` for the default binding (every link in the wild keeps
  // working); `#wl.<name>=` for a named list, so a scoped link can only ever be
  // consumed by the list it was exported from.
  function shareParam() { return listId ? ('wl.' + encodeURIComponent(listName || listId)) : 'wl'; }

  // states that mean "a low/buy is near" — kept for the signal sort ordering
  var STATE_RANK = {
    'FRESH BUY': 0, 'TURN SIGNALED': 1, 'BOTTOM WATCH': 2, 'RALLY ON': 3,
    'TOP WATCH': 4, 'ROLLING OVER': 5, 'COUNTERTREND BOUNCE': 6, 'DECLINE': 7
  };

  // ---- micro-i18n for the JS-rendered scaffolding -------------------------
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  function isZh() { return lang() === 'zh'; }
  var T = {
    en: {
      ph: 'Add a name…',
      noStore: 'Your browser is blocking local storage (private mode?). This list will reset when you close the tab.',
      importBad: 'Could not read that watchlist code',
      imported: function (n) { return 'Imported ' + n + ' ticker' + (n === 1 ? '' : 's'); },
      copied: 'Link copied',
      added: function (n) { return 'Added ' + n + ' name' + (n === 1 ? '' : 's'); },
      newList: 'New list', newListPrompt: 'Name this list',
      renameList: 'Rename this list', deleteList: 'Delete this list',
      deleteConfirm: function (n) { return 'Delete “' + n + '”? The names in it are removed from your account.'; },
      entryNone: 'No tickers found in that text. Try “AAPL, MSFT, NVDA”.',
      entryOne: 'Add at least two names — one name has no structure to read.',
      // ---- legacy render path (see the LEGACY block below) — verbatim from main
      empty: 'Your watchlist is empty. Search above to add a holding — equity, ETF, commodity or crypto.',
      starters: 'Quick add:', removeA: 'Remove from watchlist',
      buysoonN: function (n) { return n + ' nearing a buy'; },
      lgPh: 'Add a holding… (e.g. AAPL, Energy, Gold, Bitcoin)',
      unavailable: 'temporarily unavailable',
      unavailMsg: 'not in tonight’s library — may return after the next nightly build',
      sortOrder: 'My order', sortAdded: 'Recently added', sortName: 'Name',
      sortSector: 'Sector', sortSignal: 'Signal', sortLabel: 'Sort',
      buysoonOnly: 'Buy-soon only', asof: 'as of', lgAdded: 'added'
    },
    zh: {
      ph: '添加名称…',
      noStore: '你的浏览器禁用了本地存储（无痕模式？）。关闭标签页后此清单将清空。',
      importBad: '无法读取该清单代码',
      imported: function (n) { return '已导入 ' + n + ' 个标的'; },
      copied: '链接已复制',
      added: function (n) { return '已添加 ' + n + ' 只'; },
      newList: '新建列表', newListPrompt: '给这个列表起个名字',
      renameList: '重命名列表', deleteList: '删除这个列表',
      deleteConfirm: function (n) { return '删除「' + n + '」？其中的名称会从你的账户中移除。'; },
      entryNone: '没有从这段文字里识别出代码。试试「AAPL, MSFT, NVDA」。',
      entryOne: '至少输入两只 —— 一只票没有结构可读。',
      empty: '清单为空。在上方搜索以添加持仓——股票、ETF、大宗商品或加密货币。',
      starters: '快速添加：', removeA: '从清单移除',
      buysoonN: function (n) { return n + ' 接近买点'; },
      lgPh: '添加持仓…（例如 AAPL、Energy、Gold、Bitcoin）',
      unavailable: '暂不可用',
      unavailMsg: '不在今晚的标的库中——下次夜间构建后可能恢复',
      sortOrder: '我的顺序', sortAdded: '最近添加', sortName: '名称',
      sortSector: '板块', sortSignal: '信号', sortLabel: '排序',
      buysoonOnly: '仅看接近买点', asof: '数据截至', lgAdded: '添加于'
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
  /* bilingual span pair — mirrors the template's t() macro exactly. Copy is written
     as Chinese PRODUCT copy, never a translation of the English. */
  function te(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>';
  }
  function el(id) { return document.getElementById(id); }
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
  function group(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

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
      var raw = localStorage.getItem(storageKey());
      return raw ? migrate(JSON.parse(raw)) : defaultBlob();
    } catch (e) { return defaultBlob(); }
  }
  var persist = debounce(function () {
    try {
      localStorage.setItem(storageKey(), JSON.stringify(blob));
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
  // tabs ping-pong writes forever (the watchlist "spasm").
  // `listId` leads the signature so a REBIND counts as a real state change even when
  // the two lists happen to hold identical symbols. stateSig is an in-memory
  // comparison only (never persisted, never transmitted).
  function stateSig(b) {
    var its = b.items.map(function (it) {
      return [it.t, it.added || '', it.note || ''];
    }).sort(function (a, c) { return a[0] < c[0] ? -1 : a[0] > c[0] ? 1 : 0; });
    return JSON.stringify([listId, its, b.order || [], b.settings.sort, !!b.settings.buySoonOnly]);
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
    if (stateSig(blob) !== sigBefore) { blob.updated = nowISO(); persist(); }
    return blob.items.length - before;
  }

  /* ══════════════════════════════════════════════════════════════════════════
     LEGACY RENDER PATH — kept alive on purpose, and it is not dead code.

     `site/watchlist.html` is baked by the render lane; the plain-copy JS pairs go live
     on the VPS's 3-minute pull. Measured, the HTML lags its template by more than an
     hour while the JS is live in ~3 minutes, so there is a real window in which the OLD
     markup is served with THIS file. Under a workspace-only renderer that window is the
     #5463 P0 husk all over again — zero rows, no empty state, and no console error to
     notice it by.

     So the boot is non-destructive: every entry point below asks whether a workspace
     host (`#ws_modes`) is on the page, and falls through to the behaviour that shipped
     before W2 when it is not. This block is that behaviour, lifted from `origin/main`
     and namespaced `lg*` so the two renderers cannot collide.

     ONE KNOWN DELTA, so the claim above stays exact: these cards render WITHOUT the Risk
     Desk role badge (the `EXIT REVIEW` / `TAKE-PROFIT REVIEW` chips). That decoration
     came from `decorateCards`/`paintLanes` in watchlist_risk.js, which went with the
     braid block; the lane ENGINE behind it is untouched and still feeds the workspace
     drawer. Accepted, not restored: the gap is bounded by the same window this block
     exists for, and the badge is not part of the design that replaces it.

     This block is deletable the day site/watchlist.html is guaranteed no older than its
     scripts — not before.
     ══════════════════════════════════════════════════════════════════════════ */
  var BUYSOON = { 'TURN SIGNALED': 1, 'FRESH BUY': 1, 'BOTTOM WATCH': 1 };
  var listEl, countEl, observer;

  // ---- rendering ----------------------------------------------------------
  // ordered + filtered view of the watched items, resolved against the index
  function lgViewItems() {
    var sort = blob.settings.sort, only = blob.settings.buySoonOnly;
    var rows = blob.items.map(function (it) {
      var rec = idxBy[it.t] || null;          // null => dropped out of the library
      return { t: it.t, added: it.added, rec: rec,
               st: rec ? rec.st : null, n: rec ? rec.n : it.t, s: rec ? rec.s : '' };
    });
    // the active book is a VIEW over the same list — never a different list
    rows = rows.filter(function (r) { return inBook(r.t); });
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

  // counts the FILTERED set — the pill must agree with the cards on screen
  function lgBuysoonCount() {
    var n = 0;
    blob.items.forEach(function (it) {
      if (!inBook(it.t)) return;
      var rec = idxBy[it.t]; if (rec && BUYSOON[rec.st]) n++;
    });
    return n;
  }

  function lgCardHTML(r) {
    var safe = esc(r.t);
    if (!r.rec) {
      // Signed-out shell (stockdata.js is account-gated, so window.SD never
      // exists here): we cannot know coverage, so claim NOTHING — a bare card
      // with no state pill. "Dropped out of the library" below is only true
      // when a live index actually answered without this ticker.
      if (!window.SD) {
        return '<div class="wl-card wl-gone" data-t="' + safe + '">' +
          '<div class="wl-top"><a class="wl-name" href="stock.html#' + encodeURIComponent(r.t) +
          '"><b>' + safe + '</b></a>' + lgRmBtn(r.t) + '</div></div>';
      }
      // Tier-1 drop-out: never silently omit a watched ticker
      return '<div class="wl-card wl-gone" data-t="' + safe + '">' +
        '<div class="wl-top"><a class="wl-name" href="stock.html#' + encodeURIComponent(r.t) +
        '"><b>' + safe + '</b></a>' + lgRmBtn(r.t) + '</div>' +
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
        lgRmBtn(r.t) +
      '</div>' +
      '<div class="wl-sig">' +
        '<span class="state ' + stc + '">' + esc(lbl) + '</span>' +
        (act ? '<span class="wl-action muted">' + esc(act) + '</span>' : '') +
        (r.s ? '<span class="wl-sector muted">' + esc(r.s) + '</span>' : '') +
      '</div>' +
      '<div class="wl-enrich" data-enrich="' + safe + '"></div>' +
    '</div>';
  }
  function lgRmBtn(t) {
    return '<button class="wl-rm" data-rm="' + esc(t) + '" title="' + esc(L('removeA')) +
      '" aria-label="' + esc(L('removeA')) + '">✕</button>';
  }

  function lgRender() {
    if (!listEl) return;
    // Feed the factor panel the current holdings — MODELED names only. The factor
    // model is USD and carries no suffixed tickers, so a .HK/.SS/.TO name here would
    // corrupt every book statistic downstream (A3 law 3).
    if (window.FX) {
      var syms = blob.items.map(function (it) { return it.t; });
      window.FX.update(window.MB ? window.MB.modeledOnly(syms) : syms);
    }
    // the books strip reads the full list (membership is never filtered by the view)
    if (window.MB) window.MB.refresh(blob.items.map(function (it) { return it.t; }), null, null);
    var rows = lgViewItems();
    // header counter
    var n = lgBuysoonCount();
    countEl.innerHTML = n ? '<span class="wl-soonpill">▲ ' + esc(L('buysoonN')(n)) + '</span>' : '';
    // empty state vs grid
    var empty = document.getElementById('wl_empty');
    if (!blob.items.length) {
      listEl.innerHTML = ''; empty.style.display = 'block'; lgRenderStarters();
      document.getElementById('wl_controls').style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    document.getElementById('wl_controls').style.display = 'flex';
    if (!rows.length) {
      // the list is not empty — this BOOK is. Say which one, and what to do.
      listEl.innerHTML = '<p class="muted wl-bkempty">' + esc(lgBookEmptyMsg()) + '</p>';
      return;
    }
    listEl.innerHTML = rows.map(lgCardHTML).join('');
    // (re)observe enrich hosts for lazy detail loading
    lgWireEnrich();
  }
  function lgBookEmptyMsg() {
    var bk = activeBook();
    var meta = (window.MB && window.MB.BOOKS && window.MB.BOOKS[bk]) || null;
    var name = meta ? (lang() === 'zh' ? meta.zh : meta.en) : bk;
    return lang() === 'zh'
      ? '清单中还没有' + name + '名称——在上方搜索添加。'
      : 'No ' + name + ' names on your list yet — search above to add one.';
  }

  // ---- lazy Tier-2 enrichment (entry cue + momentum strip) ----------------
  function lgWireEnrich() {
    if (observer) observer.disconnect();
    if (!('IntersectionObserver' in window)) {  // no IO: enrich everything now
      listEl.querySelectorAll('[data-enrich]').forEach(lgEnrich); return;
    }
    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        observer.unobserve(e.target);
        var host = e.target.querySelector('[data-enrich]');  // the (zero-height) enrich slot
        if (host) lgEnrich(host);
      });
    }, { rootMargin: '150px' });
    // observe the CARD (it has real height — the enrich slot is 0px until filled)
    listEl.querySelectorAll('.wl-card').forEach(function (c) { observer.observe(c); });
  }
  function lgEnrich(el) {
    if (!window.SD || !window.SD.loadTicker) return;  // signed-out shell: slot stays empty
    var t = el.getAttribute('data-enrich');
    window.SD.loadTicker(t).then(function (j) {
      el.__json = j;        // cache raw JSON so a language flip re-renders w/o refetch
      lgPaintEnrich(el, j);
    });
  }
  function lgPaintEnrich(el, j) {
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
  function lgRepaintEnriched() {
    if (!listEl) return;
    listEl.querySelectorAll('[data-enrich]').forEach(function (el) {
      if ('__json' in el) lgPaintEnrich(el, el.__json);
    });
  }
  // ---- view controls ------------------------------------------------------
  function lgWireControls() {
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
  // ---- empty-state starter chips (validated against the live index) -------
  function lgRenderStarters() {
    var host = document.getElementById('wl_starters'); if (!host) return;
    var starters = (window.WL_STARTERS || []).filter(function (t) { return idxBy[t]; });
    if (!starters.length) { host.innerHTML = ''; return; }
    host.innerHTML = '<span class="muted">' + esc(L('starters')) + '</span> ' +
      starters.map(function (t) {
        return '<button class="wl-chip" data-add="' + esc(t) + '">' + esc(t) +
          ' <span class="muted">' + esc((idxBy[t] || {}).n || '') + '</span></button>';
      }).join('');
  }

  // ===========================================================================
  //  WORKSPACE PRIMITIVES — the pinned design's shared vocabulary, drawn once.
  //  Published on window.WS so portfolio.js and watchlist_risk.js compose them
  //  instead of re-inventing (and drifting from) the signature.
  // ===========================================================================

  /* Plain-word stage lexicon (DESIGN_NOTES §5.4). Stage is drawn by WEIGHT, never
     by hue, so it survives the zh direction flip and never collides with the
     --up/--down inks. */
  var STAGE = {
    early:      ['Early sign',   '初现'],
    confirming: ['Confirming',   '确认中'],
    confirmed:  ['Confirmed',    '已确认'],
    aging:      ['Losing steam', '转弱'],
    extended:   ['Running hot',  '过热'],
    /* zh RE-RULING (round 2): 已失效 is an ENGINE-VERDICT word — it says the read is
       invalid, which is an escalation a display tier may not make. 已破位 describes the
       BREAK itself, which is what the EN "Broke down" also does. The pair now says the
       same thing in both languages. */
    invalid:    ['Broke down',   '已破位'],
    none:       ['Not covered',  '未覆盖']
  };
  var STAGE_TIP = {
    early:      ['An early sign only. Most of these do not go on to confirm.', '只是初步迹象。大多数并不会走到确认。'],
    confirming: ['Building, not yet confirmed.', '正在形成，尚未确认。'],
    confirmed:  ['Confirmed and still holding.', '已确认，目前仍成立。'],
    aging:      ['Still up, but the push behind it is fading.', '仍在上行，但推动力正在减弱。'],
    extended:   ['Far above its own trend. Moves back to it can be sharp.', '已远离自身趋势线。回归时可能很急。'],
    invalid:    ['The read that held here has broken down.', '此前成立的判断已经走坏。'],
    none:       ['Funds, ETFs and names below the history floor are not in the nightly stock signal coverage. Nothing is inferred for them.',
                 '基金、ETF 以及历史不足的标的不在每晚的个股信号覆盖范围内。不会为它们推断任何判断。']
  };
  /* Engine state -> plain-word stage. This map only ever DE-ESCALATES: a state whose
     honest reading is "still falling" never becomes an up-word, and anything the map
     does not know becomes `none` (Not covered) rather than a guess. It is a fixed
     table, not a judgement made per render. */
  var STATE_STAGE = {
    'TURN SIGNALED': 'early',
    'COUNTERTREND BOUNCE': 'early',      // an UNCONFIRMED turn — deliberately not "confirming"
    'CONFIRMING TURN': 'confirming',
    'FRESH BUY': 'confirmed',
    'RALLY ON': 'confirmed',
    'TOP WATCH': 'extended',             // nearing a high / stretched
    'ROLLING OVER': 'aging',             // topping — the push behind it is fading
    'BOTTOM WATCH': 'invalid',           // still in a downtrend, merely near a low
    'DECLINE': 'invalid',
    'LIMITED': 'none'
  };
  function stageOf(state) {
    if (!state) return 'none';
    return STATE_STAGE[state] || 'none';
  }
  function stageCell(key) {
    var k = STAGE[key] ? key : 'none';
    var s = STAGE[k], tip = STAGE_TIP[k];
    return '<span class="stg s-' + k + '" data-tip-en="' + esc(tip[0]) +
      '" data-tip-zh="' + esc(tip[1]) + '"><i></i>' + te(esc(s[0]), esc(s[1])) + '</span>';
  }
  /* Day column. The quotes Worker is dormant, so every Day cell is an honest "—"
     with a Tier-2 cue — never a stale field dressed up as today's move. */
  var DAY_TIP_EN = "Live day change is not wired up yet, so we show nothing rather than a stale number. Everything else on this row is from last night's close.";
  var DAY_TIP_ZH = '当日涨跌尚未接入，因此这里留空，而不是给你一个过期的数字。本行其余数据均来自昨夜收盘。';
  function dayCell() {
    return '<span class="dash" data-tip-en="' + esc(DAY_TIP_EN) +
      '" data-tip-zh="' + esc(DAY_TIP_ZH) + '">—</span>';
  }
  function lockCell() {
    return '<span class="lockcell"><span class="lk"></span>' + te('Free account', '免费账户') + '</span>';
  }
  function dash(tipEn, tipZh) {
    if (!tipEn) return '<span class="dash">—</span>';
    return '<span class="dash" data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh || tipEn) + '">—</span>';
  }

  /* ★ THE BOOK SEAM ★  (DESIGN_NOTES §1)
     Two aligned rails under the book read. Top = share of MONEY (every position).
     Bottom = share of modeled RISK (only positions the model covers). Same width,
     same order. A position the risk model does not cover is hatched above and an
     empty outline below, and is left OUT of the risk denominator: the coverage
     disclosure is DRAWN, not merely written.

     cfg = { items:[{sym, money, risk|null, role}], cap:html, lockedRisk:bool }
     `lockedRisk` is the anonymous form (packet amendment A9): the money rail is
     real arithmetic on what the visitor entered, the risk rail is a lock shell —
     never a fabricated distribution. */
  /* SEGMENT CAP. One segment per position is the signature's whole idea, and it stops
     being legible — and stops fitting — long before a big list runs out. Each segment
     carries a 2px floor plus a 2px gap, so at 390px the rail overflows the PAGE past
     about 80 names: measured 86px of horizontal scroll at 100, which is the large-list
     law broken by the very device that is supposed to explain the book.

     So the rail draws the largest MAX_SEGS-1 positions and folds the rest into ONE
     tail segment. The tail is disclosed in the caption, never silent — a reader who
     counts segments and gets a different number than the table has been misled. The
     brackets and both denominators are computed over ALL items, before the fold, so
     capping changes what you can point at and never what the seam claims. */
  var MAX_SEGS = 24;

  function seam(host, cfg) {
    if (!host) return;
    if (!cfg || !cfg.items || cfg.items.length < 2) { host.innerHTML = ''; return; }
    var all = cfg.items, items = all, tail = null;
    if (all.length > MAX_SEGS) {
      var ranked = all.slice().sort(function (a, b) { return b.money - a.money; });
      var keep = ranked.slice(0, MAX_SEGS - 1);
      var rest = ranked.slice(MAX_SEGS - 1);
      var keepSet = {};
      keep.forEach(function (x) { keepSet[x.sym] = 1; });
      tail = { sym: '', n: rest.length, money: 0, risk: 0, anyUncovered: false };
      rest.forEach(function (x) {
        tail.money += x.money;
        if (x.risk == null) tail.anyUncovered = true; else tail.risk += x.risk;
      });
      if (tail.anyUncovered && tail.risk === 0) tail.risk = null;
      // keep the ORIGINAL order for the kept names, then the tail last
      items = all.filter(function (x) { return keepSet[x.sym]; });
      items.push({ sym: tail.n + ' smaller positions', money: tail.money,
                   risk: tail.risk, role: '', isTail: true, n: tail.n });
    }

    // denominators come from the FULL set, so the printed percentages are unchanged
    // by capping — the fold moves pixels, never arithmetic
    function total(key) {
      var tot = 0;
      all.forEach(function (it) { if (it[key] != null) tot += it[key]; });
      return tot;
    }
    function rail(key) {
      var tot = total(key);
      if (!(tot > 0)) return '<span class="seam-rail"></span>';
      var segs = items.map(function (it) {
        /* The hatch means ONE thing: this position is real money the risk model does
           not cover. It must never appear because the risk read as a whole is behind
           the account wall — that is a different claim, and it is the locked rail's
           to make. Without this guard every anonymous segment hatched, i.e. the page
           told the visitor their entire book was outside the model. */
        var uncovered = !cfg.lockedRisk && (it.risk == null);
        if (uncovered) {
          /* The name keeps its place in the order on BOTH rails: hatched on the money
             rail (it is real money), an empty outline on the risk rail (no risk figure
             exists, so none is invented). Both slots are sized by its money share so
             the two rails stay in register. */
          return '<span class="seam-seg ' + (key === 'risk' ? 'is-void' : 'is-uncovered') +
            '" style="flex:' + it.money + '" data-tip-en="' + esc(it.sym) +
            ' — real money, but outside the risk model. No risk share is claimed for it."' +
            ' data-tip-zh="' + esc(it.sym) + ' —— 是真实资金，但不在风险模型内。不会为它编造一个风险占比。"></span>';
        }
        var k = it.role === 'cluster' ? ' is-cluster' : it.role === 'ballast' ? ' is-ballast' : '';
        var p = (it[key] / tot * 100).toFixed(1);
        if (it.isTail) {
          return '<span class="seam-seg is-tail" style="flex:' + it[key] + '"' +
            ' data-tip-en="' + it.n + ' smaller positions, folded into one segment so the rail stays readable. ' +
              'Every one of them is in the table below."' +
            ' data-tip-zh="' + it.n + ' 只较小的持仓，合并为一段以保持这条轨道可读。它们全部都在下方的表格里。"></span>';
        }
        var qtyEn = key === 'risk' ? 'the modeled risk' : (cfg.topQtyEn || 'the money');
        var qtyZh = key === 'risk' ? '模型风险' : (cfg.topQtyZh || '资金');
        return '<span class="seam-seg' + k + '" style="flex:' + it[key] + '"' +
          ' data-tip-en="' + esc(it.sym) + ' — ' + p + '% of ' + qtyEn + '"' +
          ' data-tip-zh="' + esc(it.sym) + ' —— 占' + qtyZh + ' ' + p + '%"></span>';
      }).join('');
      return '<span class="seam-rail">' + segs + '</span>';
    }
    function clusterPct(key) {
      var tot = total(key), cl = 0;
      all.forEach(function (it) { if (it.role === 'cluster' && it[key] != null) cl += it[key]; });
      return tot > 0 ? cl / tot * 100 : 0;
    }
    function brk(pct, under, label) {
      return '<div class="seam-brk ' + (under ? 'is-under' : 'is-over') + '" style="--w:' +
        pct.toFixed(1) + '%"><span class="span"></span><b><span class="fig">' +
        Math.round(pct) + '%</span> ' + label + '</b></div>';
    }

    var mp = clusterPct('money');
    var html = '<div class="seam-grid">';
    if (mp > 0) html += '<span></span>' + brk(mp, false, cfg.topBracket || te('of the money', '的资金'));
    html += '<span class="seam-lbl">' + (cfg.topLabel || te('Money', '资金')) + '</span>' + rail('money');

    if (cfg.lockedRisk) {
      /* No factor read is delivered anonymously, so the risk rail is a locked slot
         and there is no bracket to draw — an absent distribution, not an invented one. */
      html += '<span></span><div class="seam-gap"></div>' +
        '<span class="seam-lbl">' + te('Risk', '风险') + '</span>' +
        '<span class="seam-rail is-locked"' +
        ' data-tip-en="How much of the book&#39;s RISK each name carries is a signed-in read — a free account turns this rail on."' +
        ' data-tip-zh="每只票各自扛下多少风险，是登录后才有的解读 —— 免费账户即可开启这条轨道。"></span>';
      html += '</div>';
    } else {
      var rp = clusterPct('risk');
      html += '<span></span><div class="seam-gap"><span class="over" style="--a:' +
        mp.toFixed(1) + '%;--d:' + (rp - mp).toFixed(1) + '%"></span></div>' +
        '<span class="seam-lbl">' + te('Risk', '风险') + '</span>' + rail('risk');
      if (rp > 0) html += '<span></span>' + brk(rp, true, te('of the risk', '的风险'));
      html += '</div>';
    }
    var cap = cfg.cap || '';
    if (tail) {
      cap += (cap ? ' ' : '') + te(
        'The rail draws your <b>' + (MAX_SEGS - 1) + ' largest</b> positions; the last segment is the other <b>' +
          tail.n + '</b>, folded together so it stays readable. Every percentage above is over all ' +
          all.length + '.',
        '这条轨道画出你最大的 <b>' + (MAX_SEGS - 1) + '</b> 笔持仓，最后一段是其余 <b>' + tail.n +
          '</b> 笔的合并。上面的百分比仍然是对全部 ' + all.length + ' 笔计算的。');
    }
    if (cap) html += '<p class="seam-cap">' + cap + '</p>';
    host.innerHTML = html;
  }

  // ---- book (market) filtering --------------------------------------------
  function activeBook() { return window.MB ? window.MB.getBook() : 'all'; }
  function inBook(t) { return window.MB ? window.MB.inActive(t) : true; }
  function bookLabel(b) {
    if (!window.MB || b === 'all') return isZh() ? '全部市场' : 'all books';
    return window.MB.bookName(b, isZh());
  }

  // ===========================================================================
  //  MODE SWITCH + SAVE-STATE CHIP
  // ===========================================================================
  var MODE_KEY = 'mdash.ws.mode.v1';
  var mode = 'portfolio';
  var PURPOSE = {
    portfolio:  ['What you hold, what changed, what it adds up to.', '你持有什么、有什么变化、加起来是什么。'],
    watchlists: ['The names you are watching, and what moved.', '你在盯的票，以及哪些发生了变化。']
  };

  function setMode(next, remember) {
    mode = (next === 'watchlists') ? 'watchlists' : 'portfolio';
    document.documentElement.setAttribute('data-ws-mode', mode);
    var modes = el('ws_modes');
    if (modes) {
      modes.querySelectorAll('.ws-mode').forEach(function (b) {
        b.setAttribute('aria-selected', String(b.getAttribute('data-go') === mode));
      });
    }
    var p = el('ws_purpose');
    if (p) p.innerHTML = te(PURPOSE[mode][0], PURPOSE[mode][1]);
    if (remember !== false) { try { localStorage.setItem(MODE_KEY, mode); } catch (e) {} }
    render();
  }

  /* The save-state chip is the ONLY disclosure of sync state on this page — the
     Account Sync panel is deleted. Four states, each literally true:
       saved   — written through to the account
       saving  — a write is in flight
       local   — anonymous; the list lives in this browser and nowhere else
       offline — the network is unreachable and changes are being kept locally */
  var CHIP = {
    saved:   ['is-saved',   'Saved', '已保存',
              'Saved to your Mastermind account. Your list and positions follow you to the Terminal.',
              '已保存到你的 Mastermind 账户。名单和持仓会同步到终端。'],
    saving:  ['is-saving',  'Saving…', '保存中…',
              'Writing your change through now. Nothing is blocked while it finishes.',
              '正在写入你的更改。写入期间页面照常可用。'],
    local:   ['is-local',   'Local to this browser', '仅存于本浏览器',
              'This list lives in this browser only. Save it to a free account and it follows you to any device.',
              '这份名单只存在这个浏览器里。保存到免费账户后，任何设备都能看到。'],
    offline: ['is-offline', 'Offline — changes kept locally', '离线 · 更改已存在本地',
              'We cannot reach the network right now. Your changes are kept on this device and written through when it comes back.',
              '当前无法连接网络。更改会先保存在本机，恢复后自动写入。']
  };
  var chipState = 'local';
  function setChip(state) {
    if (!CHIP[state]) return;
    chipState = state;
    paintChip();
  }
  function paintChip() {
    var host = el('ws_savechip'); if (!host) return;
    var c = CHIP[chipState];
    host.className = 'ws-chip ' + c[0];
    host.setAttribute('data-tip-en', c[3]);
    host.setAttribute('data-tip-zh', c[4]);
    host.innerHTML = '<i></i>' + te(esc(c[1]), esc(c[2]));
  }

  // ===========================================================================
  //  THE DENSE TABLE — one renderer, two column sets
  // ===========================================================================
  var idxBy = {};                 // ticker -> index record (signed-in only)
  var sort = { key: 'order', dir: 1 };
  var wlFilter = '';
  var openRows = {};              // ticker -> true while its drawer is open

  function idxRec(t) { return idxBy[t] || null; }
  function tickerName(t) { var r = idxRec(t); return r ? (r.n || '') : ''; }
  function tickerSt(t) { var r = idxRec(t); return r ? (r.st || null) : null; }
  function tickerSector(t) { var r = idxRec(t); return r ? (r.s || '') : ''; }

  /* Δ-since-visit — a dot and two plain words, no percentage theatre. Unchanged rows
     render BLANK, not "—": the list header states how many changed, so absence reads
     as "nothing happened here" and the changed names are the only ink in the column. */
  var DELTA = {};                 // ticker -> ['d-up'|'d-down'|'d-new', en, zh]
  var UP_STATES = { 'FRESH BUY': 1, 'TURN SIGNALED': 1, 'RALLY ON': 1, 'CONFIRMING TURN': 1 };
  function computeDeltas(stMap) {
    DELTA = {};
    if (!window.MB || !window.MB.seenDiffRows) return 0;
    var moved = window.MB.seenDiffRows(stMap);
    Object.keys(moved).forEach(function (t) {
      var m = moved[t];                       // {from, to}
      if (m.from == null) { DELTA[t] = ['d-new', 'New sign', '新信号']; return; }
      var wasUp = !!UP_STATES[m.from], nowUp = !!UP_STATES[m.to];
      if (nowUp && !wasUp) DELTA[t] = ['d-up', 'Turned up', '转强'];
      // 转弱 is the AGING stage word; reusing it here made a movement marker and a
      // stage read render identically in zh. 转跌 says "turned down", which is what
      // this marker means and what the EN says.
      else if (!nowUp && wasUp) DELTA[t] = ['d-down', 'Turned down', '转跌'];
      else DELTA[t] = ['d-new', 'Changed', '有变化'];
    });
    return Object.keys(DELTA).length;
  }

  /* Ordered + filtered view of the watched items.

     The old comparator called `order.indexOf()` INSIDE the sort, which is O(n) per
     comparison — O(n² log n) overall, and the reason a 100-name list stuttered on
     every keystroke. The position map below makes it a constant-time lookup. */
  function viewItems() {
    var pos = {};
    blob.order.forEach(function (t, i) { pos[t] = i; });
    var rows = blob.items.map(function (it, i) {
      return { t: it.t, added: it.added, n: tickerName(it.t) || it.t,
               s: tickerSector(it.t), st: tickerSt(it.t),
               pos: (pos[it.t] == null ? blob.order.length + i : pos[it.t]) };
    });
    rows = rows.filter(function (r) { return inBook(r.t); });
    if (wlFilter) {
      var v = wlFilter.toLowerCase();
      rows = rows.filter(function (r) {
        return r.t.toLowerCase().indexOf(v) >= 0 ||
               (r.n || '').toLowerCase().indexOf(v) >= 0 ||
               (r.s || '').toLowerCase().indexOf(v) >= 0;
      });
    }
    var k = sort.key, d = sort.dir;
    rows.sort(function (a, b) {
      var r = 0;
      if (k === 'sym') r = a.t.localeCompare(b.t);
      else if (k === 'name') r = a.n.localeCompare(b.n);
      else if (k === 'sector') r = (a.s || '~').localeCompare(b.s || '~');
      else if (k === 'added') r = (b.added || '').localeCompare(a.added || '');
      else if (k === 'signal') {
        var ra = a.st in STATE_RANK ? STATE_RANK[a.st] : 99;
        var rb = b.st in STATE_RANK ? STATE_RANK[b.st] : 99;
        r = ra - rb;
      } else r = a.pos - b.pos;                  // 'order'
      return (r || a.t.localeCompare(b.t)) * d;
    });
    return rows;
  }

  function th(key, label, numeric, sortable) {
    var cur = sort.key === key;
    return '<th' + (numeric ? ' class="num' + (sortable ? ' srt' : '') + '"' : (sortable ? ' class="srt"' : '')) +
      (sortable ? ' data-sort="' + key + '"' : '') +
      (cur ? ' aria-sort="' + (sort.dir > 0 ? 'ascending' : 'descending') + '"' : '') + '>' +
      label + (sortable ? '<span class="ar">' + (cur && sort.dir < 0 ? '▾' : '▴') + '</span>' : '') + '</th>';
  }

  var WL_HEAD =
    '<thead><tr>' +
      th('sym', te('Symbol', '代码'), false, true) +
      th('px', te('Last / day', '最新 / 当日'), true, false) +
      th('signal', te('Signal', '信号阶段'), false, true) +
      th('flags', te('Risk flags', '风险提示'), false, false) +
      th('evt', te('Next event', '下一个事件'), false, false) +
      th('sector', te('Sector / theme', '行业 / 主题'), false, true) +
      th('chg', te('Since your last visit', '自上次访问'), false, false) +
      '<th></th>' +
    '</tr></thead>';

  function wlRowHTML(r) {
    var signedIn = !!window.SD;
    var d = DELTA[r.t];
    var det = DETAIL[r.t];
    var px = det && det.tech && typeof det.tech.price === 'number'
      ? '<span class="fig">' + esc(fmtPx(det.tech.price, r.t)) + '</span>'
      : (signedIn ? '<span class="dash">—</span>' : dash(
          'Prices come with a free account. Nothing here is guessed for a signed-out visitor.',
          '价格需要免费账户。未登录时我们不会替你猜任何数字。'));
    var sig = signedIn ? stageCell(stageOf(r.st)) : lockCell();
    var flag = det && det.flag
      ? '<span class="flag ' + det.flag[0] + '">' + te(esc(det.flag[1]), esc(det.flag[2])) + '</span>'
      : '<span class="dash">—</span>';
    var evt = det && det.evt ? det.evt : '<span class="dash">—</span>';
    var sect = r.s ? '<span class="mut" style="font-size:12px">' + esc(r.s) + '</span>'
                   : '<span class="dash">—</span>';
    return '<tr data-t="' + esc(r.t) + '"' + (openRows[r.t] ? ' aria-expanded="true"' : '') + '>' +
      '<td class="c-sym"><b>' + esc(r.t) + '</b><span class="co">' + esc(r.n) + '</span></td>' +
      '<td class="c-val num">' + px + '<span class="w">' + dayCell() + '</span></td>' +
      '<td class="c-sig">' + sig + '</td>' +
      '<td class="c-att">' + flag + '</td>' +
      '<td class="c-evt">' + evt + '</td>' +
      '<td class="c-sect">' + sect + '</td>' +
      '<td class="c-chg">' + (d ? '<span class="delta ' + d[0] + '"><i></i>' + te(esc(d[1]), esc(d[2])) + '</span>' : '') + '</td>' +
      '<td class="c-exp"><button class="exp" type="button" data-exp="' + esc(r.t) + '" aria-label="' +
        (isZh() ? '详情' : 'Details') + '"><span class="car">⌄</span></button></td>' +
    '</tr>' + (openRows[r.t] ? drawerHTML(r, 8) : '');
  }

  function fmtPx(v, t) {
    var mkt = window.MB ? window.MB.marketOf(t) : 'us';
    var meta = (window.MB && window.MB.BOOKS[mkt]) || null;
    var ccy = meta && meta.ccy ? meta.ccy : '';
    var s = (Math.abs(v) >= 1000 ? group(Math.round(v)) : v.toFixed(2));
    return (ccy === 'USD' ? '$' : ccy ? ccy + ' ' : '') + s;
  }

  /* The row drawer. It is where the 390px demotions live (Day, Since entry, Risk
     share, Sector), and it is the only place a per-name detail is allowed to appear:
     the row itself stays scannable. One failed ticker degrades exactly THIS drawer. */
  function drawerHTML(r, span) {
    var det = DETAIL[r.t];
    var cells = [];
    cells.push('<div><span class="k">' + te('Day', '当日') + '</span>' + dayCell() + '</div>');
    if (r.s) cells.push('<div><span class="k">' + te('Sector / theme', '行业 / 主题') + '</span>' + esc(r.s) + '</div>');
    if (det && det.summary) {
      cells.push('<div style="grid-column:1/-1"><span class="k">' + te('Read', '解读') + '</span>' + esc(det.summary) + '</div>');
    } else if (window.SD && det === undefined) {
      cells.push('<div class="drw-honest">' + te('Loading this name&rsquo;s detail…', '正在读取该股详情…') + '</div>');
    } else if (!window.SD) {
      cells.push('<div class="drw-honest">' + te(
        'Per-name detail — the stage read, the next event, the momentum picture — comes with a free account.',
        '每只票的详情 —— 阶段判断、下一个事件、动能情况 —— 免费账户即可查看。') + '</div>');
    } else if (det === null) {
      cells.push('<div class="drw-honest">' + te(
        'We could not read this name from last night&rsquo;s build. The row stays — only its detail is missing.',
        '昨夜的构建里读不到这只票。这一行照常保留 —— 缺的只是它的详情。') + '</div>');
    }
    cells.push('<div class="drw-act">' +
      '<a href="stock.html?t=' + encodeURIComponent(r.t) + '">' + te('Open full page', '打开完整页面') + '</a>' +
      '<button class="drw-rm" type="button" data-rm="' + esc(r.t) + '">' +
        te('Remove from this list', '从此列表移除') + '</button></div>');
    return '<tr class="row-drawer"><td colspan="' + span + '"><div class="drw">' +
      cells.join('') + '</div></td></tr>';
  }

  // per-ticker detail, hydrated progressively; `null` = read and absent, `undefined` = not read yet
  var DETAIL = {};

  function renderWatchlist() {
    var host = el('tbl_wl'); if (!host) return;
    var rows = viewItems();
    var total = blob.items.filter(function (it) { return inBook(it.t); }).length;

    if (!blob.items.length) {
      host.innerHTML = '<tbody><tr><td><div class="tbl-empty">' + te(
        'This list is empty. Use the field above to add a name — equity, ETF, commodity or crypto.',
        '这个列表还是空的。用上方的输入框添加名称 —— 股票、ETF、大宗商品或加密货币。') +
        '</div></td></tr></tbody>';
    } else if (!rows.length) {
      host.innerHTML = '<tbody><tr><td><div class="tbl-empty">' + te(
        'No names match here yet.', '这里暂时没有匹配的名称。') + '</div></td></tr></tbody>';
    } else {
      host.innerHTML = WL_HEAD + '<tbody>' + rows.map(wlRowHTML).join('') + '</tbody>';
    }

    // scope disclosure — ALWAYS rendered, so a persisted book filter can never
    // silently shorten the list (packet §11)
    var scope = el('wl_scope');
    if (scope) {
      scope.innerHTML = (rows.length === blob.items.length)
        ? te('Showing <b>all ' + rows.length + '</b>', '显示 <b>全部 ' + rows.length + ' 只</b>')
        : te('Showing <b>' + rows.length + ' of ' + blob.items.length + '</b>',
             '显示 <b>' + blob.items.length + ' 只中的 ' + rows.length + ' 只</b>');
    }
    var rc = el('wl_rowcount');
    if (rc) rc.innerHTML = te(rows.length + (rows.length === 1 ? ' row' : ' rows'), rows.length + ' 行');

    var facts = el('wl_facts');
    if (facts) {
      var nChanged = 0;
      blob.items.forEach(function (it) { if (DELTA[it.t]) nChanged++; });
      var parts = ['<span><b class="fig">' + total + '</b> ' + te('names', '只') + '</span>'];
      if (nChanged) parts.push('<span class="sep">·</span><span><b class="fig">' + nChanged + '</b> ' +
        te('changed since your last visit', '自上次访问有变化') + '</span>');
      facts.innerHTML = parts.join('');
    }
    var name = el('wl_listname');
    if (name) name.textContent = listName || (isZh() ? '我的自选股' : 'My watchlist');
    hydrate(rows.map(function (r) { return r.t; }));
  }

  /* Progressive hydration. Names are fetched through SD's bounded-concurrency batcher,
     and each resolution repaints ONLY its own row — so one failed ticker degrades
     exactly one row and a 100-name list never blocks first paint. */
  function hydrate(tickers) {
    if (!window.SD || !window.SD.loadTickers) return;
    var want = tickers.filter(function (t) { return !(t in DETAIL); });
    if (!want.length) return;
    window.SD.loadTickers(want, function (t, j) {
      DETAIL[t] = j ? buildDetail(t, j) : null;
      repaintRow(t);
      if (window.WRI && window.WRI.noteJson && j) { try { window.WRI.noteJson(t, j); } catch (e) {} }
    });
  }
  function buildDetail(t, j) {
    var d = { tech: j.tech || null, summary: '', flag: null, evt: null, raw: j };
    var lad = j.ladder || {};
    if (lad.summary_line) d.summary = window.SD.lz(lad.summary_line, lad.summary_line_zh);
    // next event — dates dual-emit, and the ZH form drops .fig because "8月27日"
    // contains WORDS and mono numerals are for figures only
    var ev = j.next_event || (j.events && j.events[0]) || null;
    if (ev && ev.date) {
      var dt = parseISO(ev.date);
      var soon = dt ? Math.round((dt - Date.now()) / 86400000) : null;
      d.evt = '<span class="evt">' + te('Earnings', '财报') +
        ' <b class="fig l-en">' + esc(fmtDate(dt, false)) + '</b><b class="l-zh">' +
        esc(fmtDate(dt, true)) + '</b>' +
        (soon != null && soon >= 0 && soon <= 5
          ? ' <span class="soon">' + te('in ' + soon + (soon === 1 ? ' day' : ' days'), '还有 ' + soon + ' 天') + '</span>'
          : '') + '</span>';
      if (soon != null && soon >= 0 && soon <= 7) d.flag = ['f-warn', 'Reports this week', '本周财报'];
    }
    if (!d.flag && j.tech && typeof j.tech.off_52w_high_pct === 'number' && j.tech.off_52w_high_pct > -3) {
      d.flag = ['f-warn', 'Near its high', '接近高点'];
    }
    return d;
  }
  function parseISO(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ''));
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null;
  }
  var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fmtDate(ms, zh) {
    if (ms == null) return '—';
    var d = new Date(ms);
    return zh ? (d.getUTCMonth() + 1) + '月' + d.getUTCDate() + '日'
              : MON[d.getUTCMonth()] + ' ' + d.getUTCDate();
  }
  /* Repaint exactly one row. Batched into one animation frame so a 100-name
     hydration wave costs ONE layout, not one hundred. */
  var pendingRows = {}, rafQueued = false;
  function repaintRow(t) {
    pendingRows[t] = 1;
    if (rafQueued) return;
    rafQueued = true;
    var run = function () {
      rafQueued = false;
      var todo = Object.keys(pendingRows); pendingRows = {};
      todo.forEach(function (tk) {
        var row = document.querySelector('.hold tr[data-t="' + cssq(tk) + '"]');
        if (!row) return;
        var r = { t: tk, n: tickerName(tk) || tk, s: tickerSector(tk), st: tickerSt(tk) };
        if (row.closest('#tbl_wl')) {
          var frag = document.createElement('tbody');
          frag.innerHTML = wlRowHTML(r);
          var next = row.nextElementSibling;
          if (next && next.classList.contains('row-drawer')) next.remove();
          row.parentNode.replaceChild(frag.firstElementChild, row);
          while (frag.firstElementChild) row.parentNode.insertBefore(frag.firstElementChild, null);
        } else if (window.PF && window.PF.repaintRow) {
          window.PF.repaintRow(tk);
        }
      });
    };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
    else setTimeout(run, 16);
  }
  function cssq(s) { return String(s).replace(/["\\]/g, '\\$&'); }

  // ===========================================================================
  //  ANONYMOUS BULK ENTRY — paste a book, get a real structure read (packet A9)
  // ===========================================================================
  var wmode = 'equal';                    // equal | pct | usd | shares
  var ENTERED = null;                     // {mode, rows:[{t, size}]}

  /* Accepts the two documented shapes and the obvious variants:
       "AAPL, MSFT, NVDA"      -> names only
       "AAPL 20%, MSFT 15%"    -> name + size
       one per line, tabs, semicolons, "AAPL: 20%", "AAPL - 20"
     The weighting MODE is always stated explicitly by the control beside the box;
     a size typed without a mode is read under whatever that control says, never
     guessed. Returns {rows, bad} — `bad` is what we could not read, so the visitor
     is told rather than silently losing a line. */
  function parseBook(text) {
    var rows = [], bad = [], seen = {};
    String(text || '').split(/[\n\r;,\t]+/).forEach(function (chunk) {
      var raw = chunk.trim();
      if (!raw) return;
      /* Strip a leading bullet / index marker. `raw` is kept so a rejection can report
         the WHOLE line the visitor typed: stripping first and reporting the remainder
         blamed the wrong token — "600519 15%" lost its numeric code to the bullet rule
         and came back as bad=["15%"], which points the visitor at the one part of the
         line that was fine. This file's own law, stated at the `bad` contract. */
      var s = raw.replace(/^[-*\u2022]+\s+/, '').replace(/^\d{1,2}[.)]\s+/, '');
      /* A symbol is EITHER a letter-led ticker (AAPL, BRK-B, GC=F) OR a numeric code
         with a market suffix (0700.HK, 600519.SS, 9988.HK). The second form is not an
         edge case on a bilingual product — it is how every Hong Kong and mainland
         listing is written, and a letter-led-only rule silently rejected the entire
         book of any Chinese user who pasted one. `bad` catches the ambiguity that
         remains: a bare number is a size, never a ticker. */
      var m = /^([A-Za-z][A-Za-z0-9.\-=^]{0,11}|[0-9]{1,6}\.[A-Za-z]{1,3})\s*[:=\-]?\s*\$?\s*([0-9]*\.?[0-9]+)?\s*%?\s*$/.exec(s);
      if (!m) { bad.push(raw.slice(0, 32)); return; }
      var t = m[1].toUpperCase();
      if (seen[t]) return;
      seen[t] = 1;
      rows.push({ t: t, size: m[2] != null ? parseFloat(m[2]) : null });
    });
    return { rows: rows, bad: bad };
  }

  /* Turn the parsed rows into shares of the book. Equal mode ignores any sizes typed;
     every other mode uses them and falls back to equal for a row that gave none —
     which is disclosed in the book-read meta line, never silently.

     `unit` is the load-bearing field. Percent and Dollars describe MONEY. Share counts
     do NOT: without a price plane, 5000 shares of a $12 stock and 1 share of a $700k
     stock are one number each and the second is the larger position. Reading share
     counts as money produced "98% of the money sits in F" for a book whose largest
     holding by far was the BRK-A share it printed at 0.0%. Anonymously we have no
     prices, so `unit` stays 'shares' and every sentence downstream is required to
     speak share counts — the shares of the RAIL are still arithmetic, they are simply
     shares of a different quantity, and the page has to say which. */
  function weightsOf(parsed, m) {
    var rows = parsed.rows;
    var anySize = rows.some(function (r) { return r.size != null && r.size > 0; });
    // a price plane only exists for a signed-in session (stockdata.js); anonymously
    // Shares can never become money, so the unit follows the mode, not the wish
    var unit = (m === 'shares' && !window.SD) ? 'shares' : 'money';
    if (m === 'equal' || !anySize) {
      var w = 100 / rows.length;
      return { items: rows.map(function (r) { return { sym: r.t, money: w }; }),
               assumed: true, unit: 'money' };   // an equal split IS an equal split of money
    }
    var tot = 0;
    rows.forEach(function (r) { tot += (r.size != null && r.size > 0) ? r.size : 0; });
    var avg = tot / rows.filter(function (r) { return r.size != null && r.size > 0; }).length;
    var filled = rows.map(function (r) {
      return { sym: r.t, money: (r.size != null && r.size > 0) ? r.size : avg };
    });
    var sum = 0; filled.forEach(function (x) { sum += x.money; });
    filled.forEach(function (x) { x.money = sum > 0 ? x.money / sum * 100 : 0; });
    return { items: filled, unit: unit,
             assumed: !rows.every(function (r) { return r.size != null && r.size > 0; }) };
  }

  function runEntry() {
    var box = el('ws_entry_in'); if (!box) return;
    var err = el('ws_entry_err');
    var parsed = parseBook(box.value);
    if (err) err.textContent = '';
    if (!parsed.rows.length) { if (err) err.textContent = L('entryNone'); return; }
    if (parsed.rows.length < 2) { if (err) err.textContent = L('entryOne'); return; }
    var n = 0;
    parsed.rows.forEach(function (r) { if (add(r.t)) n++; });
    ENTERED = { mode: wmode, parsed: parsed };
    try { localStorage.setItem('mdash.ws.entry.v1', JSON.stringify({ mode: wmode, text: box.value })); } catch (e) {}
    pushCloud();
    render();
    if (n) toast(L('added')(n));
  }
  function restoreEntry() {
    // the analysis survives a refresh: the names are in the store already, and the
    // sizes the visitor typed are what make the money rail real
    try {
      var raw = JSON.parse(localStorage.getItem('mdash.ws.entry.v1') || 'null');
      if (!raw || !raw.text) return;
      wmode = raw.mode || 'equal';
      var box = el('ws_entry_in'); if (box) box.value = raw.text;
      var parsed = parseBook(raw.text);
      if (parsed.rows.length >= 2) ENTERED = { mode: wmode, parsed: parsed };
      paintWmode();
    } catch (e) {}
  }
  function paintWmode() {
    var host = el('ws_wmode'); if (!host) return;
    host.querySelectorAll('button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-w') === wmode));
    });
  }

  // ---- the anonymous structure read ---------------------------------------
  var WMODE_WORD = {
    equal:  ['Equal weighted', '等权重'],
    pct:    ['Weighted by percent', '按百分比加权'],
    usd:    ['Weighted by amount', '按金额加权'],
    shares: ['Weighted by share count', '按股数加权']
  };

  /* Real structure analysis from plain arithmetic plus the shell-reachable public
     facts (packet amendment A9). Everything factor-model-derived — effective bets,
     risk shares, stage reads — is a LOCK SHELL, never a number we do not have.
     "moves like about K bets" is reserved to the signed-in read: it is factor output. */
  function renderAnonBook() {
    var w = weightsOf(ENTERED.parsed, ENTERED.mode);
    var items = w.items.slice().sort(function (a, b) { return b.money - a.money; });
    var n = items.length;

    // market split — MB.marketOf is a pure suffix derivation and needs no account
    var byMkt = {}, mkts = [];
    items.forEach(function (x) {
      var m = window.MB ? window.MB.marketOf(x.sym) : 'us';
      if (!byMkt[m]) { byMkt[m] = { n: 0, money: 0 }; mkts.push(m); }
      byMkt[m].n++; byMkt[m].money += x.money;
    });
    mkts.sort(function (a, b) { return byMkt[b].money - byMkt[a].money; });

    // weight concentration — how much of the money the biggest few names carry
    var topN = Math.max(1, Math.min(3, Math.ceil(n / 4)));
    var topShare = 0; items.slice(0, topN).forEach(function (x) { topShare += x.money; });
    var topNames = items.slice(0, topN).map(function (x) { return x.sym; });
    var evenSpread = Math.round(100 / n);

    var meta = el('ws_book_meta');
    if (meta) {
      var parts = ['<span>' + te(n + ' names', n + ' 只') + '</span>',
                   '<span class="sep">·</span>',
                   '<span>' + te(WMODE_WORD[ENTERED.mode][0], WMODE_WORD[ENTERED.mode][1]) + '</span>'];
      if (w.assumed) parts.push('<span class="sep">·</span><span>' +
        te('No sizes given', '未提供仓位金额') + '</span>');
      meta.innerHTML = parts.join('');
    }
    var eyebrow = el('ws_book_eyebrow');
    if (eyebrow) eyebrow.innerHTML = te('This book', '这本账簿');
    var sub = el('ws_book_sub');
    if (sub) sub.innerHTML = w.assumed
      ? te('Equal weighted — you did not give sizes', '等权重 —— 你没有输入仓位大小')
      : te('Weighted the way you entered it', '按你输入的权重计算');

    /* The headline is a WEIGHT / MARKET concentration claim — plain arithmetic on
       what the visitor typed. It is deliberately NOT the effective-bets sentence. */
    /* UNIT LAW. `shares` mode has no price plane anonymously, so every sentence below
       speaks share COUNTS and the page says outright that money weights need prices.
       There is no phrasing in which a share count may be called money. */
    var shares = (w.unit === 'shares');
    var QTY = shares ? ['of the shares', '的股数'] : ['of the money', '的资金'];

    var say = el('ws_book_say');
    if (say) {
      if (topShare >= 55) {
        say.innerHTML = shares
          ? te('Most of these shares — <span class="fig">' + Math.round(topShare) +
                 '%</span> of the share count — are in <span class="fig">' + topN + '</span> ' +
                 (topN === 1 ? 'name' : 'names') + '.',
               '这些股数的大部分 —— 占总股数 <span class="fig">' + Math.round(topShare) +
                 '%</span> —— 集中在 <span class="fig">' + topN + '</span> 只票上。')
          : te('Most of this book — <span class="fig">' + Math.round(topShare) + '%</span> of the money — sits in <span class="fig">' + topN + '</span> ' + (topN === 1 ? 'name' : 'names') + '.',
               '这本账簿的大部分 —— <span class="fig">' + Math.round(topShare) + '%</span> 的资金 —— 压在 <span class="fig">' + topN + '</span> 只票上。');
      } else if (mkts.length === 1) {
        say.innerHTML = te(
          'All <span class="fig">' + n + '</span> of these trade in one market — ' + bookLabel(mkts[0]) + '.',
          '这 <span class="fig">' + n + '</span> 只全部在同一个市场交易 —— ' + bookLabel(mkts[0]) + '。');
      } else {
        say.innerHTML = te(
          'These <span class="fig">' + n + '</span> names are spread fairly evenly.',
          '这 <span class="fig">' + n + '</span> 只票的权重分布相对均匀。');
      }
    }
    var because = el('ws_book_because');
    if (because) {
      var lead = topNames.join(' · ');
      var mktLine = mkts.length === 1
        ? te('Every name here trades in the same market, so there is nothing here pulling the other way.',
             '这里的每只票都在同一个市场，因此没有任何一只在往另一个方向拉。')
        : te('They span <b>' + mkts.length + ' markets</b>: ' +
               mkts.map(function (m) { return bookLabel(m) + ' ' + Math.round(byMkt[m].money) + '%'; }).join(', ') + '.',
             '它们分布在 <b>' + mkts.length + ' 个市场</b>：' +
               mkts.map(function (m) { return bookLabel(m) + ' ' + Math.round(byMkt[m].money) + '%'; }).join('、') + '。');
      because.innerHTML = (shares
        ? te('The largest share counts are <b>' + esc(lead) + '</b>. An even split across ' + n +
               ' names would be ' + evenSpread + '% of the shares each. ',
             '股数最多的是 <b>' + esc(lead) + '</b>。' + n + ' 只票平均分配的话，每只占总股数 ' + evenSpread + '%。')
        : te('The biggest weights are <b>' + esc(lead) + '</b>. An even split across ' + n + ' names would be ' + evenSpread + '% each. ',
             '权重最大的是 <b>' + esc(lead) + '</b>。' + n + ' 只票平均分配的话，每只是 ' + evenSpread + '%。')) + mktLine;
    }
    var stance = el('ws_book_stance');
    if (stance) {
      stance.innerHTML = topShare >= 55
        ? te('Worth knowing before you add the next name.', '在加下一只票之前，值得先知道这件事。')
        : te('Nothing here needs a decision today.', '今天没有需要决定的事。');
    }

    // the seam: money rail REAL, risk rail LOCKED
    seam(el('ws_seam'), {
      items: items.map(function (x, i) {
        return { sym: x.sym, money: x.money, risk: 0, role: i < topN ? 'cluster' : '' };
      }).map(function (x) { return { sym: x.sym, money: x.money, risk: null, role: x.role }; }),
      lockedRisk: true,
      topLabel: shares ? te('Shares', '股数') : te('Money', '资金'),
      topBracket: shares ? te('of the shares', '的股数') : te('of the money', '的资金'),
      topQtyEn: shares ? 'the share count' : 'the money',
      topQtyZh: shares ? '总股数' : '资金',
      cap: shares
        ? te('The top line is your <b>share count</b>, exactly as you entered it — not money. ' +
               'Turning share counts into position sizes needs last night&rsquo;s prices, which come with a free account; ' +
               'so does the bottom line, how much of the book&rsquo;s <b>risk</b> each name actually carries.',
             '上面这条是你输入的 <b>股数</b>，不是金额。要把股数换算成仓位大小，需要昨夜的收盘价 —— ' +
               '免费账户即可获得；下面那条「每只票实际扛下多少 <b>风险</b>」也一样。')
        : te('The top line is your money, exactly as you entered it. The bottom line — how much of the book&rsquo;s <b>risk</b> each name actually carries — is the read a free account turns on, and it is almost never the same shape.',
             '上面这条是你的资金，完全按你输入的来。下面那条 —— 每只票实际扛下多少 <b>风险</b> —— 是免费账户才会开启的解读，而它几乎从不和上面同一个形状。')
    });

    var cov = el('ws_book_coverage');
    if (cov) {
      cov.innerHTML = '<span class="mark"></span><span>' + (shares
        ? te('These are share counts, read exactly as you typed them. <b>A share count is not a position size</b> — without prices we cannot tell which of these is your biggest holding, so nothing on this page claims one. We also do not know your cost basis, so nothing claims a gain or a loss.',
             '这些是股数，完全按你输入的读取。<b>股数不等于仓位大小</b> —— 没有价格，我们无法判断哪一只才是你最大的持仓，因此本页不会作此断言。我们也不知道你的成本价，所以不会给出任何盈亏。')
        : te('Sizes are read exactly as you typed them, and nothing is inferred from them. We do not know your cost basis, so nothing on this page claims a gain or a loss.',
             '仓位大小完全按你输入的读取，不会据此推断任何东西。我们不知道你的成本价，因此本页不会给出任何盈亏。')) + '</span>';
    }

    // the anonymous holdings table — weight only, no invented money
    renderAnonTable(items, w.unit);

    var head = el('ws_gate_head');
    if (head) head.innerHTML = te(
      'The stage read for each of these ' + n + ' names',
      '这 ' + n + ' 只票各自的阶段判断');
    var att = el('ws_sec_att');
    if (att) att.style.display = 'none';
    renderRiskCenter();
  }

  var ANON_HEAD =
    '<thead><tr>' +
      '<th>' + te('Symbol', '代码') + '</th>' +
      '<th class="num">' + te('Weight', '占比') + '</th>' +
      '<th class="num">' + te('Day', '当日') + '</th>' +
      '<th class="num">' + te('Since entry', '持有以来') + '</th>' +
      '<th>' + te('Signal', '信号阶段') + '</th>' +
      '<th class="num">' + te('Risk share', '风险占比') + '</th>' +
      '<th>' + te('Attention', '留意') + '</th>' +
      '<th>' + te('Next event', '下一个事件') + '</th>' +
      '<th></th>' +
    '</tr></thead>';

  function renderAnonTable(items, unit) {
    var host = el('tbl_pf'); if (!host) return;
    var filtered = items.filter(function (x) { return inBook(x.sym); });
    var q = (el('pf_q') && el('pf_q').value || '').trim().toLowerCase();
    if (q) filtered = filtered.filter(function (x) { return x.sym.toLowerCase().indexOf(q) >= 0; });
    var head = (unit === 'shares')
      ? ANON_HEAD.replace(te('Weight', '占比'), te('Share of shares', '股数占比'))
      : ANON_HEAD;
    host.innerHTML = head + '<tbody>' + filtered.map(function (x) {
      return '<tr data-t="' + esc(x.sym) + '">' +
        '<td class="c-sym"><b>' + esc(x.sym) + '</b><span class="co"></span></td>' +
        '<td class="c-val num"><span class="fig">' + x.money.toFixed(1) + '%</span></td>' +
        '<td class="c-day num">' + dayCell() + '</td>' +
        // a pasted list has no cost basis, so this is "—" with a cue, never a
        // fabricated 0.0%
        '<td class="c-since num">' + dash(
          'You pasted a list, so there is no entry price to measure from. Add positions with an entry price to see this.',
          '你贴的是一份名单，没有买入价可作基准。添加带买入价的持仓后即可显示。') + '</td>' +
        '<td class="c-sig">' + lockCell() + '</td>' +
        '<td class="c-rc num">' + dash(
          'How much of the book&#39;s risk this name carries is a signed-in read.',
          '这只票占本账簿多少风险，是登录后才有的解读。') + '</td>' +
        '<td class="c-att">' + dash() + '</td>' +
        '<td class="c-evt">' + dash(
          'Upcoming earnings and events come with a free account.',
          '即将到来的财报与事件，免费账户即可查看。') + '</td>' +
        '<td class="c-exp"></td>' +
      '</tr>';
    }).join('') + '</tbody>';

    var scope = el('pf_scope');
    if (scope) scope.innerHTML = paintScope(filtered.length, items.length);
    var rc = el('pf_rowcount');
    if (rc) rc.innerHTML = te(filtered.length + (filtered.length === 1 ? ' row' : ' rows'), filtered.length + ' 行');
    var sub = el('ws_hold_sub');
    if (sub) sub.innerHTML = te('The names you entered, as you entered them', '你输入的名单，原样呈现');
  }

  /* The disclosure line. It is load-bearing, not decoration: it is what stops a
     persisted book filter from silently shortening the list (packet §11), so it
     names the active book whenever one is active. */
  function paintScope(shown, total) {
    var bk = activeBook();
    if (bk === 'all' && shown === total) {
      return te('Showing <b>all ' + total + '</b> · all books', '显示 <b>全部 ' + total + ' 只</b> · 全部市场');
    }
    if (bk === 'all') {
      return te('Showing <b>' + shown + ' of ' + total + '</b>', '显示 <b>' + total + ' 只中的 ' + shown + ' 只</b>');
    }
    return te('Showing <b>' + shown + ' of ' + total + '</b> — ' + bookLabel(bk) + ' book',
              '显示 <b>' + total + ' 只中的 ' + shown + ' 只</b> —— ' + bookLabel(bk) + '账本');
  }

  // ===========================================================================
  //  RISK CENTER
  // ===========================================================================
  var rcTab = 'conc';
  /* The question each tab answers, in the words a reader would use. W2 shipped these
     as "being built" shells; W3 gives every one of them a real read, so the copy now
     serves the case that survives forever: a book too thin for that particular read.
     A tab with nothing to say says what it would say and why it cannot — it never
     shows an empty panel, and it never shows another tab's answer instead. */
  var RC_THIN = {
    conc: ['Concentration', '集中度',
           'Which single name carries the most of your risk.',
           '哪一只票扛下了你最多的风险。'],
    corr: ['Correlation', '相关性',
           'Which of your names actually move together, and how closely.',
           '你的哪些票其实同涨同跌，以及有多同步。'],
    fact: ['Factors &amp; macro', '因子与宏观',
           'The handful of forces — growth, rates, the dollar, oil — your book is really leaning on.',
           '你的账簿真正压在哪几股力量上 —— 成长、利率、美元、原油。'],
    strs: ['Stress', '压力情景',
           'What the same book looks like on the days the market falls, not on an average day.',
           '在市场下跌的那些日子里，同一本账簿是什么样 —— 而不是平均日。'],
    evt:  ['Events', '事件',
           'Every reporting date attached to your names, on one calendar.',
           '你名下每只票的财报日期，集中在一张日历上。'],
    weak: ['Weak links &amp; strengths', '弱点与支撑',
           'The position carrying more risk than its size, and the one pulling the other way.',
           '哪一笔仓位扛的风险超过了它的体量，以及哪一笔在往反方向拉。']
  };

  function renderRiskCenter() {
    var body = el('rc_body'); if (!body) return;
    var tabs = el('rc_tabs');
    if (tabs) tabs.querySelectorAll('.rc-tab').forEach(function (b) {
      b.setAttribute('aria-selected', String(b.getAttribute('data-rc') === rcTab));
    });

    renderLab();

    // anonymous: every rule-derived read is a lock shell with the free CTA
    if (!window.RiskCore || !window.SD) {
      body.innerHTML = '<div class="lockshell"><span class="lk">◇</span><span>' +
        '<b>' + te('Risk reads come with a free account', '风险解读需要免费账户') + '</b>' +
        te('Concentration, correlation, factor and stress reads are computed from the nightly model — they are not something we can honestly show without one.',
           '集中度、相关性、因子与压力情景都由每晚的模型算出 —— 没有账户，我们没法诚实地把它们显示出来。') +
        '<button class="cta" type="button" id="rc_cta">' +
        te('Create a free account', '创建免费账户') + '</button></span></div>';
      return;
    }
    var html = RISK.rcTabs && RISK.rcTabs[rcTab];
    if (!html && rcTab === 'conc') html = RISK.concHTML;   // pre-W3 publisher, mid-deploy
    if (html) { body.innerHTML = html; return; }
    var s = RC_THIN[rcTab] || RC_THIN.conc;
    body.innerHTML = '<p class="rc-soon"><b>' + te(s[0], s[1]) + '</b>' + te(s[2], s[3]) +
      '<br><span style="opacity:.7">' + te(
        'Add at least two positions the nightly model covers and this fills in.',
        '添加至少两笔每晚模型已覆盖的持仓，这里就会填充。') + '</span></p>';
  }

  /* The Scenario Lab shell is painted ONCE and then left alone. A hydration wave
     republishes the risk payload every time a name resolves, and re-rendering the
     form on each one would delete whatever the reader was in the middle of typing.
     The RESULT is cleared instead: it describes a book that has just changed, and a
     stale hypothetical presented as current is the one thing this panel must not do. */
  function renderLab() {
    var lab = el('rc_lab'); if (!lab) return;
    if (!lab.querySelector('#rc_lab_go')) {
      lab.innerHTML = RISK.labHTML || labFallback();
      paintPlaceholders();
      return;
    }
    var out = el('rc_lab_out');
    if (out && out.innerHTML) out.innerHTML = '';
  }

  /* The lab body when the publisher never spoke.
     `RISK.labHTML` comes from watchlist_risk.js, and that file is account-gated — it
     401s for a signed-out visitor and never executes, so `labHTML` is empty and the
     Scenario Lab rendered as an EMPTY BOX on the anonymous funnel surface. That is a
     regression against the pre-W3 page, which always printed a sentence here, and it
     breaks this Risk Center's own rule: a panel with nothing to say says what it would
     say and why it cannot. Signed-in-but-model-missing is covered on the publisher's
     side (`labUnavailableHTML`); this is the case where nothing publishes at all. */
  function labFallback() {
    var anon = !window.RiskCore || !window.SD;
    return '<p class="lab-say">' + te(
      'Name a position and a size, and this compares your book before and after — how many separate directions it would move in, how much of the risk that position would carry, and which of your names it would move with.',
      '输入一个代码和一个金额，这里会对比「加仓前」与「加仓后」的账簿 —— 会剩下几个独立方向、这笔仓位会扛下多少风险、以及它会和你的哪些持仓同步波动。') +
      '</p><p class="lab-note">' + (anon
      ? te('Those figures are computed from the nightly model, which comes with a free account.',
           '这些数字由每晚的模型算出，需要免费账户才能使用。')
      : te('Tonight&rsquo;s model has not loaded, so there is nothing to compare against yet.',
           '今晚的模型尚未载入，因此暂时无法进行对比。')) + '</p>';
  }
  function runLab() {
    var out = el('rc_lab_out'); if (!out) return;
    if (!window.WRI || !window.WRI.scenario) return;
    var t = el('rc_lab_t'), d = el('rc_lab_d');
    var dollars = d ? parseFloat(d.value) : NaN;
    try { out.innerHTML = window.WRI.scenario(t ? t.value : '', dollars); }
    catch (e) { out.innerHTML = ''; }
  }

  /* The risk publisher's landing pad. watchlist_risk.js computes; the workspace
     draws. Keeping the seam and the Risk Center reads in ONE file is what stops
     the signature from drifting between two renderers. */
  var RISK = { shares: null, concHTML: '', rcTabs: null, labHTML: '',
               seamItems: null, coverage: null, headline: null };
  function setRisk(payload) {
    RISK = payload || { shares: null, concHTML: '', rcTabs: null, labHTML: '',
                        seamItems: null, coverage: null, headline: null };
    if (mode === 'portfolio') renderRiskCenter();
  }

  // ===========================================================================
  //  RENDER
  // ===========================================================================
  function wsState() {
    if (window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user()) return 'signed';
    if (chipState === 'saved' || chipState === 'saving') return 'signed';
    if (window.SD) return 'signed';               // the gated shell only boots for a session
    return ENTERED ? 'anon-analyzed' : 'anon-empty';
  }

  /* THREE possible pages, and this file has to be correct on all of them.

       1. the W2 workspace  -> `#ws_modes` is present; render the workspace
       2. the PRE-W2 page   -> no `#ws_modes` but `#wl_list` is there; render the
                               legacy card grid, byte-for-byte what shipped before
       3. no page at all    -> the node unit shell; render nothing, throw nothing

     Case 2 is not hypothetical. site/watchlist.html is baked by the render lane and
     empirically lags its template by over an hour, while this file goes live on the
     VPS's 3-minute pull — so the old markup WILL be served with this script, and a
     workspace-only renderer turns that window into the #5463 husk. */
  function isWorkspace() {
    return typeof document !== 'undefined' && !!document.getElementById && !!el('ws_modes');
  }
  function isLegacyPage() {
    return typeof document !== 'undefined' && !!document.getElementById &&
      !el('ws_modes') && !!el('wl_list');
  }
  function hasUI() {
    return isWorkspace() || !!(typeof document !== 'undefined' && document.getElementById &&
      (el('tbl_pf') || el('tbl_wl')));
  }

  function render() {
    if (isLegacyPage()) { lgRender(); return; }
    if (!hasUI()) return;
    var state = wsState();
    document.documentElement.setAttribute('data-ws-state', state);

    // Feed the factor panel the current holdings — MODELED names only. The factor
    // model is USD and carries no suffixed tickers, so a .HK/.SS/.TO name here would
    // corrupt every book statistic downstream.
    if (window.FX) {
      var syms = blob.items.map(function (it) { return it.t; });
      window.FX.update(window.MB ? window.MB.modeledOnly(syms) : syms);
    }
    /* The books model is built from watchlist names UNION open positions. portfolio.js
       refreshes it with BOTH; this file only has the watchlist half, so calling it here
       while a book exists rebuilds the model with `rows = null`, drops every market the
       positions contributed, and `refresh()` then resets a persisted book filter to
       "all" because its market looks absent. Symptom: picking Crypto silently snapped
       back to all books. Only refresh here when nobody else can. */
    var pfHasRows = !!(window.PF && window.PF.count && window.PF.count() > 0);
    if (window.MB && window.MB.refresh && !pfHasRows) {
      window.MB.refresh(blob.items.map(function (it) { return it.t; }), null, null);
    }

    // mode-switch counts are what the user ACTUALLY has — an anonymous visitor has no
    // saved lists, so the count is ABSENT rather than borrowed
    var pfN = el('ws_modes') && el('ws_modes').querySelector('[data-count="pf"]');
    var wlN = el('ws_modes') && el('ws_modes').querySelector('[data-count="wl"]');
    if (pfN) pfN.textContent = (state === 'anon-empty') ? '' : String(pfCount());
    if (wlN) wlN.textContent = (state.indexOf('anon') === 0) ? '' : String(listsCount());

    if (mode === 'watchlists') { renderWatchlist(); return; }

    if (state === 'anon-analyzed' && ENTERED) { renderAnonBook(); return; }
    if (state === 'anon-empty') { renderStarters(); return; }
    // signed in: portfolio.js owns the holdings table + the book read; it repaints
    // on its own data events. Everything shared (scope line, risk center) is here.
    if (window.PF && window.PF.render) window.PF.render();
    renderRiskCenter();
  }
  function pfCount() {
    // an anonymous visitor has no saved positions, so the count is what they pasted;
    // signed in it is the book itself. Never a number borrowed from the other state.
    if (ENTERED && wsState() === 'anon-analyzed') return ENTERED.parsed.rows.length;
    if (window.PF && window.PF.count) return window.PF.count();
    return blob.items.length;
  }
  function listsCount() {
    if (window.WatchStore && window.WatchStore.lists && window.WatchStore.lists.all) {
      try { return window.WatchStore.lists.all().length || 1; } catch (e) {}
    }
    return 1;
  }

  // ---- ready-made starter lists (validated against the live index when we have one)
  function renderStarters() {
    var host = el('wl_starters'); if (!host) return;
    var starters = (window.WL_STARTERS || []);
    if (!starters.length) { host.innerHTML = ''; return; }
    host.innerHTML = starters.map(function (t) {
      var name = (idxBy[t] || {}).n || '';
      return '<button class="bookchip" type="button" data-add="' + esc(t) + '">' + esc(t) +
        (name ? '<span class="n">' + esc(name.slice(0, 18)) + '</span>' : '') + '</button>';
    }).join('');
  }

  // ---- search-to-add ------------------------------------------------------
  var sugg, q, sel = -1, sItems = [];
  function wireSearch(list) {
    if (!q || !sugg) return;
    var searchList = list, widened = false;

    function paint() {
      var v = q.value.trim().toLowerCase(); sel = -1;
      if (!v) { sugg.style.display = 'none'; return; }
      sItems = searchList.filter(function (x) {
        return x.t.toLowerCase().indexOf(v) === 0 ||
               (x.n || '').toLowerCase().indexOf(v) >= 0 ||
               (x.s || '').toLowerCase().indexOf(v) >= 0;
      }).sort(function (a, b) {
        var ae = a.t.toLowerCase() === v ? -1 : 0, be = b.t.toLowerCase() === v ? -1 : 0;
        if (ae !== be) return ae - be;
        var ap = a.t.toLowerCase().indexOf(v) === 0 ? 0 : 1,
            bp = b.t.toLowerCase().indexOf(v) === 0 ? 0 : 1;
        return ap - bp || a.t.localeCompare(b.t);
      }).slice(0, 12);
      // a suffixed query (".HK") or a miss widens the search to every market ONCE
      if ((!sItems.length || v.indexOf('.') >= 0) && !widened && window.SD.loadIndexes) {
        widened = true;
        window.SD.loadIndexes(['us', 'cn', 'hk', 'ca', 'intl']).then(function (r) {
          searchList = r.list; idxBy = r.byTicker; paint();
        });
      }
      sugg.innerHTML = sItems.map(function (x, i) {
        var inList = has(x.t) ? ' ✓' : '';
        return '<div data-i="' + i + '"><b>' + esc(x.t) + '</b>' +
          '<small>' + esc(x.n || '') + (x.s ? ' · ' + esc(x.s) : '') + '</small>' +
          '<span class="mut" style="font-size:11px">' + esc(inList) + '</span></div>';
      }).join('');
      sugg.style.display = sItems.length ? 'block' : 'none';
    }

    q.addEventListener('input', paint);
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

  // ---- list switcher (the W1a `lists` seam, finally driven) ----------------
  function listsAll() {
    if (window.WatchStore && window.WatchStore.lists && window.WatchStore.lists.all) {
      try { return window.WatchStore.lists.all(); } catch (e) {}
    }
    return [];
  }
  function paintListMenu() {
    var menu = el('wl_listmenu'); if (!menu) return;
    var rows = listsAll();
    var html = rows.map(function (r) {
      return '<button type="button" data-list="' + esc(r.id) + '" data-name="' + esc(r.name) + '"' +
        (r.id === (window.WLCloud && window.WLCloud.activeListId && window.WLCloud.activeListId())
          ? ' aria-current="true"' : '') + '>' + esc(r.name) + '</button>';
    }).join('');
    if (!rows.length) {
      html = '<button type="button" disabled>' + esc(isZh() ? '仅本浏览器' : 'This browser only') + '</button>';
    }
    menu.innerHTML = html + '<hr>' +
      '<button type="button" data-listact="new">' + esc(L('newList')) + '</button>' +
      (rows.length ? '<button type="button" data-listact="rename">' + esc(L('renameList')) + '</button>' +
                     '<button type="button" data-listact="delete">' + esc(L('deleteList')) + '</button>' : '');
  }
  function toggleListMenu(open) {
    var menu = el('wl_listmenu'), btn = el('wl_listpick');
    if (!menu || !btn) return;
    var next = open == null ? !menu.classList.contains('open') : open;
    if (next) paintListMenu();
    menu.classList.toggle('open', next);
    btn.setAttribute('aria-expanded', String(next));
  }
  function listAction(act) {
    var LS = window.WatchStore && window.WatchStore.lists;
    if (!LS) { toggleListMenu(false); return; }
    var cur = window.WLCloud && window.WLCloud.activeListId && window.WLCloud.activeListId();
    if (act === 'new') {
      var name = window.prompt(L('newListPrompt'), '');
      if (!name) { toggleListMenu(false); return; }
      LS.create(name).then(function (row) {
        if (row && row.id) return LS.setActive(row.id);
      }).then(function () { paintListMenu(); render(); });
    } else if (act === 'rename' && cur) {
      var nn = window.prompt(L('renameList'), listName || '');
      if (!nn) { toggleListMenu(false); return; }
      LS.rename(cur, nn).then(function () { listName = nn; paintListMenu(); render(); });
    } else if (act === 'delete' && cur) {
      if (!window.confirm(L('deleteConfirm')(listName || ''))) { toggleListMenu(false); return; }
      LS.remove(cur).then(function () { paintListMenu(); render(); });
    }
    toggleListMenu(false);
  }

  // ---- export / import / share-link --------------------------------------
  function exportCode() {
    if (!listId) return b64enc(JSON.stringify(blob));
    var b = {};
    Object.keys(blob).forEach(function (k) { b[k] = blob[k]; });
    b.list = listName || '';
    return b64enc(JSON.stringify(b));
  }
  function importCode(code) {
    if (!code) return;
    var other;
    try {
      var m = code.match(/#?wl(?:\.[^=]*)?=([^&]+)/);
      other = JSON.parse(b64dec(m ? m[1] : code));
    } catch (e) { toast(L('importBad'), true); return; }
    if (!other || typeof other !== 'object' || !Array.isArray(other.items)) { toast(L('importBad'), true); return; }
    var n = mergeInto(migrate(other));
    render(); pushCloud(); toast(L('imported')(n));
  }
  /* A pasted share URL lands here on load — merge into the CURRENTLY BOUND list, then
     strip the fragment (one shot per page load, so a later rebind can never re-consume
     it into a different list). A bare `#wl=` is unscoped; a `#wl.<name>=` link is
     scoped and is only consumed by the list of that name. */
  function consumeShareHash() {
    var h = location.hash || '';
    var m = h.match(/^#wl=(.+)$/);
    if (!m) {
      var scoped = h.match(/^#wl\.([^=]*)=(.+)$/);
      if (!scoped) return;
      var want = '';
      try { want = decodeURIComponent(scoped[1]); } catch (e) { want = scoped[1]; }
      if (want !== (listName || '')) return;   // not this list's link — leave it be
      m = [scoped[0], scoped[2]];
    }
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) {}
    importCode(m[1]);
  }

  // ---- banners / toasts ---------------------------------------------------
  function showBanner(msg) {
    var b = el('wl_banner'); if (!b) return;
    b.textContent = msg; b.style.display = 'block';
  }
  function hideBanner() { var b = el('wl_banner'); if (b) b.style.display = 'none'; }
  var toastH;
  function toast(msg, bad) {
    var host = el('wl_toast'); if (!host) return;
    host.textContent = msg; host.className = 'wl-toast' + (bad ? ' bad' : '') + ' show';
    clearTimeout(toastH); toastH = setTimeout(function () { host.className = 'wl-toast'; }, 2600);
  }

  // ---- cloud seam (watchstore.js attaches here; no-op when not configured) --
  function pushCloud() {
    document.dispatchEvent(new CustomEvent('wl-changed'));
    // The blob is pushed WITH its binding, so the diff can never be applied to a list
    // this blob did not come from.
    if (window.WLCloud && window.WLCloud.push) window.WLCloud.push(blob, listId);
  }

  // ---- cross-tab sync: another tab wrote -> reload + merge + render --------
  function onStorage(e) {
    if (e.key && e.key !== storageKey()) return;
    var sigBefore = stateSig(blob);
    mergeInto(readStorage());     // union, never blind-overwrite
    if (stateSig(blob) !== sigBefore) render();
  }

  // ---- placeholders (an attribute cannot hold the dual-emit spans, which is the
  //      same reason translated copy never goes in title=) --------------------
  function paintPlaceholders() {
    var zh = isZh();
    document.querySelectorAll('[data-ph-en]').forEach(function (n) {
      n.setAttribute('placeholder', n.getAttribute(zh ? 'data-ph-zh' : 'data-ph-en') || '');
    });
  }

  // ---- public store API (the seam watchstore.js / cloud adapter plug into) --
  window.WL = {
    getBlob: function () { return blob; },
    merge: function (other) { var n = mergeInto(migrate(other)); render(); return n; },
    replace: function (other) { blob = migrate(other); persist(); render(); },
    add: function (t) { if (add(t)) { render(); } },
    remove: function (t) { remove(t); render(); },
    render: render,
    onLocalChange: function (cb) { document.addEventListener('wl-changed', cb); },
    /* Rebind to a registered list (W1a seam). Re-reads from that list's own cache —
       it does NOT carry the previous list's blob across, which under a full-membership
       diff push would be a wipe of the list being switched to. */
    bindList: function (id, name) {
      var nextId = id || null;
      if (nextId === listId) { listName = nextId ? (name || listName) : ''; return listId; }
      listId = nextId;
      listName = nextId ? (name || '') : '';
      blob = readStorage();
      render();
      return listId;
    },
    listId: function () { return listId; },
    storageKey: storageKey,
    shareParam: shareParam
  };

  /* The workspace render seam. portfolio.js and watchlist_risk.js compose these
     instead of re-inventing the signature; nothing else may draw a seam or a stage
     mark. Present even in the anonymous shell — the pieces that need an account
     degrade individually, the vocabulary does not. */
  window.WS = {
    t: te, esc: esc, group: group, lang: lang, isZh: isZh,
    stageOf: stageOf, stageCell: stageCell, dayCell: dayCell, lockCell: lockCell, dash: dash,
    seam: seam, scopeLine: paintScope, bookLabel: bookLabel,
    drawerOpen: function (t) { return !!openRows[t]; },
    setRisk: setRisk,
    setChip: setChip,
    mode: function () { return mode; },
    toast: toast,
    render: render,
    hydrate: hydrate,
    detail: function (t) { return DETAIL[t]; },
    idxRec: idxRec, tickerName: tickerName, tickerSt: tickerSt
  };

  // ---- init ---------------------------------------------------------------
  function init() {
    sugg = el('wl_sugg');
    q = el('wl_q');
    listEl = el('wl_list');
    countEl = el('wl_count');

    blob = readStorage();
    if (!storageProbe()) showBanner(L('noStore'));

    // PRE-W2 markup: wire and render exactly what shipped before this wave, then stop.
    if (isLegacyPage()) { initLegacy(); return; }

    restoreEntry();
    paintPlaceholders();
    paintChip();

    var saved = 'portfolio';
    try { saved = localStorage.getItem(MODE_KEY) || 'portfolio'; } catch (e) {}
    setMode(saved, false);

    // ---- delegated wiring -------------------------------------------------
    var modes = el('ws_modes');
    if (modes) modes.addEventListener('click', function (e) {
      var b = e.target.closest('.ws-mode[data-go]'); if (!b) return;
      setMode(b.getAttribute('data-go'));
    });
    var wm = el('ws_wmode');
    if (wm) wm.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-w]'); if (!b) return;
      wmode = b.getAttribute('data-w'); paintWmode();
      if (ENTERED) runEntry();
    });
    var go = el('ws_entry_go');
    if (go) go.addEventListener('click', runEntry);
    var box = el('ws_entry_in');
    if (box) box.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') runEntry();
    });

    var tabs = el('rc_tabs');
    if (tabs) tabs.addEventListener('click', function (e) {
      var b = e.target.closest('.rc-tab[data-rc]'); if (!b) return;
      rcTab = b.getAttribute('data-rc'); renderRiskCenter();
    });

    /* Scenario Lab: delegated off the panel, because the form is painted by
       `renderLab` after this wiring runs and re-painted whenever the reader
       reopens the page in a new mode. Enter in either field runs it too — a
       two-field form where only the button works is a form people abandon. */
    var lab = el('rc_lab');
    if (lab) {
      lab.addEventListener('click', function (e) {
        if (e.target.closest('#rc_lab_go')) runLab();
      });
      lab.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        if (!e.target.closest('#rc_lab_t, #rc_lab_d')) return;
        e.preventDefault(); runLab();
      });
    }

    var wf = el('wl_filter');
    if (wf) wf.addEventListener('input', debounce(function () {
      wlFilter = wf.value.trim(); renderWatchlist();
    }, 120));
    var pq = el('pf_q');
    if (pq) pq.addEventListener('input', debounce(function () { render(); }, 120));

    var pick2 = el('wl_listpick');
    if (pick2) pick2.addEventListener('click', function (e) { e.stopPropagation(); toggleListMenu(); });
    var menu = el('wl_listmenu');
    if (menu) menu.addEventListener('click', function (e) {
      var act = e.target.closest('[data-listact]');
      if (act) { listAction(act.getAttribute('data-listact')); return; }
      var row = e.target.closest('[data-list]');
      if (!row) return;
      var id = row.getAttribute('data-list'), nm = row.getAttribute('data-name');
      toggleListMenu(false);
      if (window.WatchStore && window.WatchStore.lists && window.WatchStore.lists.setActive) {
        window.WatchStore.lists.setActive(id).then(function () {
          window.WL.bindList(id, nm);
        });
      } else { window.WL.bindList(id, nm); }
    });
    document.addEventListener('click', function () { toggleListMenu(false); });

    // event delegation: sort headers, row drawers, remove, starters, gate CTAs
    document.addEventListener('click', function (e) {
      var sortTh = e.target.closest('.hold th[data-sort]');
      if (sortTh) {
        var k = sortTh.getAttribute('data-sort');
        if (sort.key === k) sort.dir = -sort.dir; else { sort.key = k; sort.dir = 1; }
        render(); return;
      }
      var ex = e.target.closest('[data-exp]');
      if (ex) {
        var t = ex.getAttribute('data-exp');
        if (openRows[t]) delete openRows[t]; else openRows[t] = true;
        render(); return;
      }
      var rm = e.target.closest('[data-rm]');
      if (rm) { remove(rm.getAttribute('data-rm')); render(); pushCloud(); return; }
      var ad = e.target.closest('[data-add]');
      if (ad) { if (add(ad.getAttribute('data-add'))) { render(); pushCloud(); } return; }
      var cta = e.target.closest('#ws_gate_save, #rc_cta');
      if (cta) { if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signup'); return; }
      var si = e.target.closest('#ws_gate_signin');
      if (si) { if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signin'); return; }
      var an = e.target.closest('#wl_analyze');
      if (an) {
        // a watchlist has no position sizes, so analyzing it is an EQUAL-WEIGHTED
        // structure read — never a portfolio
        var syms = blob.items.filter(function (it) { return inBook(it.t); })
                             .map(function (it) { return it.t; });
        if (syms.length >= 2) {
          wmode = 'equal';
          ENTERED = { mode: 'equal', parsed: { rows: syms.map(function (s) { return { t: s, size: null }; }), bad: [] } };
          setMode('portfolio');
        }
        return;
      }
    });

    window.addEventListener('storage', onStorage);
    document.addEventListener('themechange', render);
    document.addEventListener('langchange', function () { paintPlaceholders(); paintChip(); render(); });
    document.addEventListener('bk-change', render);
    document.addEventListener('wl-list-change', function (e) {
      var id = e && e.detail && e.detail.listId;
      if (id) window.WL.bindList(id, listName);
    });
    // the store is the authority on the save state; the chip only paints it
    document.addEventListener('ws-save', function (e) {
      if (e && e.detail && e.detail.state) setChip(e.detail.state);
    });

    /* Resolve the live universe across every market the saved list actually touches.
       Signed-out shell: stockdata.js is account-gated (window.SD absent) — take the
       same path as an index failure and paint the workspace bare, which is exactly
       the anonymous funnel state. */
    if (!window.SD || !window.SD.loadIndexes) { render(); return; }
    var markets = { us: 1 };
    if (window.MB) blob.items.forEach(function (it) { markets[window.MB.marketOf(it.t)] = 1; });
    window.SD.loadIndexes(Object.keys(markets)).then(function (r) {
      idxBy = r.byTicker;
      wireSearch(r.list);
      consumeShareHash();   // a #wl= link merges before first visible paint
      publishSeenDiff();
      render();
    }).catch(function () { render(); });
  }


  /* The pre-W2 init, verbatim in behaviour: controls, share box, delegated add/remove,
     cross-tab sync, and the index resolve that feeds the card grid. Nothing in here
     touches a `#ws_*` id, so it is safe on markup that has never heard of the
     workspace. */
  function initLegacy() {
    lgWireControls();
    wireShare();

    document.addEventListener('click', function (e) {
      var rm = e.target.closest('[data-rm]');
      if (rm) { remove(rm.getAttribute('data-rm')); lgRender(); pushCloud(); return; }
      var ad = e.target.closest('[data-add]');
      if (ad) { if (add(ad.getAttribute('data-add'))) { lgRender(); pushCloud(); } }
    });

    window.addEventListener('storage', onStorage);
    document.addEventListener('themechange', lgRepaintEnriched);
    document.addEventListener('langchange', function () {
      if (q) q.placeholder = L('lgPh');
      lgRender();
    });
    document.addEventListener('bk-change', lgRender);

    if (!window.SD || !window.SD.loadIndexes) { lgRender(); return; }
    var markets = { us: 1 };
    if (window.MB) blob.items.forEach(function (it) { markets[window.MB.marketOf(it.t)] = 1; });
    window.SD.loadIndexes(Object.keys(markets)).then(function (r) {
      idxBy = r.byTicker;
      wireSearch(r.list);
      if (q) q.placeholder = L('lgPh');
      consumeShareHash();
      lgRender();
      publishSeenDiff();
    }).catch(function () { lgRender(); });
  }

  /* The export/import box only exists on the pre-W2 page. Guarded so the workspace,
     which does not carry it, never wires a null. */
  function wireShare() {
    var ta = el('wl_export'), imp = el('wl_import');
    var copy = el('wl_copylink'), impBtn = el('wl_importbtn');
    if (!ta || !imp || !copy || !impBtn) return;
    function refresh() { ta.value = exportCode(); }
    refresh();
    document.addEventListener('wl-changed', refresh);
    copy.addEventListener('click', function () {
      var url = location.origin + location.pathname + '#' + shareParam() + '=' + exportCode();
      var done = function () { toast(L('copied')); };
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, function () { ta.select(); });
      else { ta.value = url; ta.select(); document.execCommand && document.execCommand('copy'); refresh(); done(); }
    });
    impBtn.addEventListener('click', function () { importCode(imp.value.trim()); imp.value = ''; });
  }

  /* "N changed since your last visit" — computed over the FULL set, never the
     filtered view, and the new snapshot is written AFTER the diff so the count is
     always "since the last time you looked", not "since the last render". */
  function publishSeenDiff() {
    if (!window.MB || !window.MB.setFact) return;
    var stMap = {};
    blob.items.forEach(function (it) {
      var rec = idxBy[it.t];
      if (rec && rec.st) stMap[it.t] = rec.st;
    });
    var n = computeDeltas(stMap);
    window.MB.setFact('changed', n);
  }

  // does setItem actually work? (Safari private mode throws on write, not read)
  function storageProbe() {
    try { localStorage.setItem(storageKey() + '.probe', '1'); localStorage.removeItem(storageKey() + '.probe');
      return true; } catch (e) { storageOK = false; return false; }
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
  }

  /* Node-test surface for the multi-list binding seams (storage key, stateSig, share
     fragment) plus the W2 bulk-entry parser. `module` is undefined in the browser, so
     none of this exists at runtime on the site. */
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      consumeShareHash: consumeShareHash,
      exportCode: exportCode,
      stateSig: function () { return stateSig(blob); },
      parseBook: parseBook,
      weightsOf: weightsOf,
      stageOf: stageOf
    };
  }
})();

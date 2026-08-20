/* watchstore.js — Supabase relational sync for the Watchlist (replaces auth.js doc-blob path).

   Plugs into the same seams auth.js used:
     • window.WLCloud.push(blob)  — called by watchlist.js after every local change
     • window.WL.merge(blob)      — called here after pull to fold cloud rows in
     • window.MDXAuth.onChange    — auth events from theme.js shared session
     • window.getSupabaseClient() — shared Supabase client from theme.js

   W2: this module no longer OWNS any sync UI. The Account Sync panel is deleted and
   the header save-state chip is the page's only disclosure of where the list lives,
   so the store's job here is to publish the state and nothing else:
     • `ws-save` document event, detail.state ∈ saved | saving | local | offline
       (watchlist.js paints the chip; this file never touches its DOM)
     • sign-in / sign-out go through the global MDXAuth modal, wired by the page

   When there is no session (logged out, no config, SDK blocked):
     • All paths are dormant; localStorage-only behavior is unchanged.
     • window.WLCloud.push() is a no-op (safe: watchlist.js calls it unconditionally).
     • On pages without the wl_* elements the UI helpers are all inert via el() guards.

   W1 scope: ticker sync only. Notes / order / settings remain localStorage-only
   (the relational schema has no columns for them). The blob carries them; we do not
   try to sync them.

   W1a scope: REGISTERED MULTI-LIST. The store no longer has one implicit target.
     • `WatchStore.lists.*`   — create / rename / remove / refresh, owner-scoped.
     • `WatchStore.symbols.*` — every symbol op takes an explicit listId.
     • Per-list localStorage caches `mdash.wl.<listId>.v1`, in the SAME blob shape as
       the anonymous store, so a rebind is a plain re-read.
     • `mdash.watchlist.v1` stays the ANONYMOUS store with byte-identical semantics —
       signed-out visitors are untouched by this wave.
   Notes stay local by ruling: `watchlist_symbols` has no note column and this wave
   adds none. Server `position` is the order authority. */
(function () {
  'use strict';

  // ---- state -----------------------------------------------------------------
  var sb = null;           // shared Supabase client, set on auth
  var user = null;         // current auth user
  var lastAuthUid = undefined;  // dedup guard: undefined = never seen; null = signed-out
  var listsCache = [];     // [{id,name,position}] — last server read of the user's lists
  var wlId = null;         // ACTIVE (bound) list id — see resolveBoundList()
  var foldTargetId = null; // id of the list NAMED 'Watchlist' — resolved ON DEMAND by the fold
  /* Server-read membership, keyed by list id: { set:{sym:true}, order:[sym], maxPos:n }.
     This map is the ONLY delete authority in the module. It is written by symbolsFetch()
     (a real server read of that one list) and never by a localStorage cache — see the
     push-scoping contract at pushList(). `maxPos` is a monotonic high-water mark for
     `position`, so delete+add cycles never collide. */
  var cloud = {};
  var pullPending = false; // pull in progress
  var pullDoneAt = 0;      // epoch ms of last successful pull
  /* listId -> the ticker ARRAY captured at enqueue time, for lists that had not been
     read when their push fired. Per-list, like _pushTimers: a single global slot let a
     second unread list's push silently overwrite the first one's edit. Never holds a
     blob — see WLCloud.push for why a live object may not be read later. */
  var queuedPushes = {};
  var foldMarkerKey = 'mdash.watchstore.folded.v1'; // localStorage marker for one-time fold

  var SECTION = 'Watchlist';
  var LIST_NAME = 'Watchlist';   // the primary list's name; created if absent
  var CACHE_PREFIX = 'mdash.wl.';
  var CACHE_SUFFIX = '.v1';

  function nowISO() { return new Date().toISOString(); }

  // ---- i18n (verbatim from auth.js) ------------------------------------------
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  var T = {
    en: { signin: 'Sign in to sync', signout: 'Sign out', synced: 'Synced', syncing: 'Syncing…',
          local: 'Local only', offline: 'Offline — local only', finishing: 'Finishing sign-in…',
          hello: 'Signed in as' },
    zh: { signin: '登录以同步', signout: '退出登录', synced: '已同步', syncing: '同步中…',
          local: '仅本地', offline: '离线——仅本地', finishing: '正在完成登录…',
          hello: '已登录：' }
  };
  function L(k) { return (T[lang()] || T.en)[k]; }

  // ---- DOM helpers -----------------------------------------------------------
  function el(id) { return document.getElementById(id); }

  /* The four states the header chip can show, published as an event. The internal
     vocabulary keeps its old names (setPill is called from a dozen places) and maps
     ONCE, here, onto the four user-facing states — "finishing sign-in" is a write in
     flight from the reader's point of view, so it is `saving`, not a fifth word. */
  var CHIP_STATE = { synced: 'saved', syncing: 'saving', finishing: 'saving',
                     local: 'local', offline: 'offline' };
  var lastChip = null;
  function setPill(state) {
    var next = CHIP_STATE[state] || 'local';
    if (next !== lastChip) {
      lastChip = next;
      try {
        document.dispatchEvent(new CustomEvent('ws-save', { detail: { state: next } }));
      } catch (e) {}
    }
    lgPaintPill(state);
  }
  /* PRE-W2 pill. Inert on the workspace (the element does not exist there); on the old
     markup it is the ONLY sync disclosure, so it is painted verbatim as before. */
  function lgPaintPill(state) {
    var p = el('wl_syncpill'); if (!p) return;
    var map = { synced: L('synced'), syncing: L('syncing'), local: L('local'),
                offline: L('offline'), finishing: L('finishing') };
    p.textContent = map[state] || '';
    p.className = 'wl-pill wl-pill-' + (state === 'finishing' ? 'syncing' : state);
  }
  function showAccount(email) {
    if (el('wl_signin'))  el('wl_signin').style.display  = 'none';
    if (el('wl_authbox')) el('wl_authbox').style.display = 'none';
    if (el('wl_account')) el('wl_account').style.display = 'flex';
    if (el('wl_who'))     el('wl_who').textContent = L('hello') + ' ' + email;
  }
  function showSignedOut() {
    if (el('wl_account')) el('wl_account').style.display = 'none';
    if (el('wl_authbox')) el('wl_authbox').style.display = 'none';
    if (el('wl_signin'))  el('wl_signin').style.display  = 'inline-block';
    setPill('local');
  }
  function relabel() {
    if (el('wl_signin'))  el('wl_signin').textContent  = L('signin');
    if (el('wl_signout')) el('wl_signout').textContent = L('signout');
    if (user) showAccount(user.email || ''); else setPill('local');
  }

  // (the shared single-timer debounce() this module used is retired — the push is now
  //  debounced PER LIST at _schedulePush, so two lists cannot cancel each other.)

  // ---- safe logging (single warn per class; no user-visible output) ----------
  var warned = {};
  function warnOnce(key, msg) {
    if (warned[key]) return;
    warned[key] = true;
    console.warn('[watchstore] ' + msg);
  }

  // ---- status ----------------------------------------------------------------
  var portfolioOk = true;  // flips false on first RLS/permission error on portfolio ops

  function status() {
    if (!user || !sb) return 'local';
    if (wlId && cloud[wlId]) return 'cloud';
    return 'local';
  }

  // ---- per-list localStorage cache -------------------------------------------
  /* `mdash.wl.<listId>.v1` holds the SAME blob shape as the anonymous store
     (`mdash.watchlist.v1`), so binding watchlist.js to a registered list is a plain
     re-read of a different key — no second format, no translation layer.

     A cache is a RENDER HINT and a rebind source. It is NEVER a delete authority:
     `cloud[listId]` (a real server read) is the only input the push diff will delete
     from. That separation is what makes a stale cache of list A structurally unable to
     touch list B — the named regression this wave exists to prevent. */
  function cacheKey(listId) { return CACHE_PREFIX + listId + CACHE_SUFFIX; }

  function cacheRead(listId) {
    var empty = { v: 1, updated: '', items: [], order: [], settings: {} };
    if (!listId) return empty;
    try {
      var raw = localStorage.getItem(cacheKey(listId));
      if (!raw) return empty;
      var b = JSON.parse(raw);
      if (!b || typeof b !== 'object' || !Array.isArray(b.items)) return empty;
      return {
        v: 1,
        updated: b.updated || '',
        items: b.items.filter(function (it) { return it && it.t; }),
        order: Array.isArray(b.order) ? b.order : [],
        settings: (b.settings && typeof b.settings === 'object') ? b.settings : {}
      };
    } catch (e) { return empty; }
  }

  // signature of the user-meaningful state — everything EXCEPT `updated`, so an
  // identical re-write never fires a pointless storage event into the other tabs
  // (the same no-op discipline watchlist.js's stateSig enforces).
  function cacheSig(b) {
    var its = (b.items || []).map(function (it) {
      return [it.t, it.added || '', it.note || ''];
    }).sort(function (a, c) { return a[0] < c[0] ? -1 : a[0] > c[0] ? 1 : 0; });
    return JSON.stringify([its, b.order || [], b.settings || {}]);
  }

  /* Write the server membership of one list into its cache, PRESERVING the local
     item metadata (`added`, `note`) and settings already there — notes are local by
     ruling (no note column exists), so a sync must never erase them. */
  function cacheWrite(listId, symbols) {
    if (!listId) return false;
    var prev = cacheRead(listId);
    var byT = {};
    prev.items.forEach(function (it) { byT[it.t] = it; });
    var order = (symbols || []).slice();
    var next = {
      v: 1,
      updated: nowISO(),
      items: order.map(function (t) {
        var e = byT[t];
        return { t: t, added: (e && e.added) || nowISO(), note: (e && e.note) || '' };
      }),
      order: order,
      settings: prev.settings
    };
    if (cacheSig(next) === cacheSig(prev)) return false;   // no-op: do not re-persist
    try { localStorage.setItem(cacheKey(listId), JSON.stringify(next)); return true; }
    catch (e) { return false; }
  }

  function cacheClear(listId) {
    if (!listId) return;
    try { localStorage.removeItem(cacheKey(listId)); } catch (e) {}
  }

  // ---- registered list CRUD (owner-scoped; every query filters user_id) -------
  function _listsGuard() {
    if (!user || !sb) return Promise.reject(new Error('no-session'));
    return Promise.resolve();
  }
  function _rememberList(row) {
    if (!row) return row;
    for (var i = 0; i < listsCache.length; i++) {
      if (String(listsCache[i].id) === String(row.id)) { listsCache[i] = row; return row; }
    }
    listsCache.push(row);
    return row;
  }
  function _row(r) {
    return { id: r.id, name: r.name, position: r.position || 0, created_at: r.created_at || '' };
  }
  /* Ruling R1's branch 2 binds "the FIRST list by (position, created_at)", so that
     ordering is load-bearing for a RULING, not decoration. The query already asks for
     it; sorting again where it is consumed means a future refactor that drops an
     `.order()` cannot silently change which list a returning user is bound to. */
  function _byPositionThenCreated(a, b) {
    if ((a.position || 0) !== (b.position || 0)) return (a.position || 0) - (b.position || 0);
    var x = a.created_at || '', y = b.created_at || '';
    return x < y ? -1 : x > y ? 1 : 0;
  }
  // Postgres 23505 on the schema's unique (user_id, name) index — two tabs (or a tab
  // and the Terminal) racing the same create. Adopt the winner instead of failing.
  function _isDuplicateName(err) {
    if (!err) return false;
    return String(err.code || '') === '23505' ||
           /duplicate key|already exists/i.test(String(err.message || ''));
  }

  function listsAll() { return listsCache.slice(); }
  function listNameOf(listId) {
    if (!listId) return '';
    for (var i = 0; i < listsCache.length; i++) {
      if (String(listsCache[i].id) === String(listId)) return listsCache[i].name || '';
    }
    return '';
  }

  function listsFetch() {
    return _listsGuard().then(function () {
      return sb.from('watchlists')
        .select('id, name, position, created_at')
        .eq('user_id', user.id)
        .order('position')
        .order('created_at', { ascending: true });
    }).then(function (res) {
      if (res.error) throw res.error;
      listsCache = (res.data || []).filter(function (r) { return r && r.id; })
        .map(_row).sort(_byPositionThenCreated);
      return listsCache.slice();
    });
  }

  /* A bare `.limit(1)` with no ORDER BY is nondeterministic in Postgres even when a
     unique index makes a duplicate impossible today — and a nondeterministic bind is
     how two tabs end up pushing full-membership diffs at two different lists. The
     order is stated explicitly here for the same reason listsFetch sorts twice. */
  function _findListByName(name) {
    return sb.from('watchlists')
      .select('id, name, position, created_at')
      .eq('user_id', user.id)
      .eq('name', name)
      .order('position')
      .order('created_at', { ascending: true })
      .limit(1)
      .then(function (res) {
        if (res.error) throw res.error;
        var r = (res.data || [])[0];
        return r ? _rememberList(_row(r)) : null;
      });
  }

  function listCreate(name) {
    var nm = String(name == null ? '' : name).trim();
    if (!nm) return Promise.reject(new Error('empty-name'));
    return _listsGuard().then(function () {
      var pos = 0;
      listsCache.forEach(function (l) { if ((l.position || 0) >= pos) pos = (l.position || 0) + 1; });
      return sb.from('watchlists')
        .insert({ user_id: user.id, name: nm, position: pos })
        .select('id, name, position')
        .single();
    }).then(function (res) {
      if (res.error) {
        if (_isDuplicateName(res.error)) return _findListByName(nm);
        throw res.error;
      }
      return _rememberList(_row(res.data));
    });
  }

  function listRename(listId, name) {
    var nm = String(name == null ? '' : name).trim();
    if (!listId || !nm) return Promise.reject(new Error('bad-args'));
    return _listsGuard().then(function () {
      return sb.from('watchlists')
        .update({ name: nm })
        .eq('id', listId)
        .eq('user_id', user.id)
        .select('id, name, position')
        .single();
    }).then(function (res) {
      if (res.error) throw res.error;
      var row = _rememberList(_row(res.data));
      // Renaming AWAY from 'Watchlist' drops the cached fold target: a later fold
      // re-resolves (creating 'Watchlist' again if it is now absent) rather than
      // delivering into a list the user has renamed to something else. The BOUND list
      // is unaffected — a rename does not move the user off the list they are viewing.
      if (String(foldTargetId) === String(listId) && row.name !== LIST_NAME) foldTargetId = null;
      return row;
    });
  }

  /* Delete a list. `watchlist_symbols.watchlist_id` is ON DELETE CASCADE (Terminal
     0001_init.sql), so the rows go with it — we drop the local mirrors so nothing
     stale can be diffed against a list that no longer exists. */
  function listRemove(listId) {
    if (!listId) return Promise.reject(new Error('bad-args'));
    return _listsGuard().then(function () {
      return sb.from('watchlists').delete().eq('id', listId).eq('user_id', user.id);
    }).then(function (res) {
      if (res.error) throw res.error;
      cacheClear(listId);
      delete cloud[listId];
      _cancelPush(listId);
      listsCache = listsCache.filter(function (l) { return String(l.id) !== String(listId); });
      if (String(foldTargetId) === String(listId)) foldTargetId = null;
      if (String(wlId) === String(listId)) wlId = null;
      return { id: listId };
    });
  }

  function _createPrimary() {
    return listCreate(LIST_NAME).then(function (created) {
      if (!created || !created.id) throw new Error('list-create-failed');
      return created.id;
    });
  }
  function _namedPrimary() {
    for (var i = 0; i < listsCache.length; i++) {
      if (listsCache[i].name === LIST_NAME) return listsCache[i].id;
    }
    return null;
  }

  /* WHICH LIST THIS PAGE IS BOUND TO — Commissioning ruling R1 (2026-08-12), which
     supersedes the packet's bare "created if absent" for BINDING. The FOLD's
     create-if-absent is a separate question, resolved below.

       1. a list named exactly 'Watchlist' exists -> bind it
       2. else the user has >= 1 list            -> bind the FIRST by (position,
                                                    created_at) and CREATE NOTHING
       3. else (zero lists)                      -> create 'Watchlist' and bind it

     Branch 2 is the ruling's substance, and it is a deliberate non-creation. A
     Terminal-native account's only list is called 'Default'. Minting an empty
     'Watchlist' for it would (a) show this page an empty list on a fresh device until
     the W2 switcher ships, and (b) leave a spurious empty row in every such account's
     list picker once W1b makes lists server-backed. Binding the first list is exactly
     the pre-W1a behaviour for that cohort, and W2's switcher makes the choice explicit.

     PRECONDITION: listsFetch() has run — pull() always calls it first, and its ordering
     (`position`, then `created_at`) is what makes "first" well-defined here. */
  function resolveBoundList() {
    var named = _namedPrimary();
    if (named) return Promise.resolve(named);
    if (listsCache.length > 0) return Promise.resolve(listsCache[0].id);
    return _createPrimary();
  }

  /* WHERE THE ONE-SHOT FOLD DELIVERS — the list named 'Watchlist', created if absent.
     Unchanged by ruling R1, because this resolution only ever runs when the fold has
     content to deliver (see _foldLocalIntoCloud: the marker and empty-book checks come
     FIRST). Creating a list at that moment is on-demand, never spurious — which is
     exactly the distinction that lets branch 2 above create nothing. */
  function resolveFoldTarget() {
    var named = _namedPrimary();
    if (named) return Promise.resolve(named);
    // listsCache is populated by pull()'s listsFetch(); if it is genuinely empty we
    // still ask the server by name before minting a second one.
    if (listsCache.length > 0) return _createPrimary();
    return _findListByName(LIST_NAME).then(function (row) {
      return row ? row.id : _createPrimary();
    });
  }

  // ---- symbol ops, always targeted by an explicit list id --------------------
  function _cloudOf(listId) { return listId ? cloud[listId] : null; }
  function _nextPos(listId) {
    var c = _cloudOf(listId);
    return (c ? c.maxPos : -1) + 1;
  }
  function _noteInserted(listId, symbols) {
    var c = _cloudOf(listId);
    if (!c) return;
    symbols.forEach(function (t) {
      if (!c.set[t]) { c.set[t] = true; c.order.push(t); }
      c.maxPos += 1;
    });
    cacheWrite(listId, c.order.slice());
  }

  /* Read one list's rows from the server. This is the ONLY writer of cloud[listId],
     and therefore the only thing that can ever authorize a delete against that list. */
  function symbolsFetch(listId) {
    return _listsGuard().then(function () {
      if (!listId) throw new Error('no-list');
      return sb.from('watchlist_symbols')
        .select('symbol, position, created_at')
        .eq('watchlist_id', listId)
        .order('position');
    }).then(function (res) {
      if (res.error) throw res.error;
      var rows = (res.data || []).filter(function (r) { return r && r.symbol; });
      var set = {}, order = [], mx = -1;
      rows.forEach(function (r) {
        if (set[r.symbol]) return;
        set[r.symbol] = true;
        order.push(r.symbol);
        if ((r.position || 0) > mx) mx = r.position || 0;
      });
      cloud[listId] = { set: set, order: order, maxPos: mx };
      cacheWrite(listId, order.slice());
      return rows;
    });
  }

  /* READ-FIRST, matching pushList's refusal policy rather than opposing it. An unread
     list has no known membership, and `watchlist_symbols` carries NO unique index on
     (watchlist_id, symbol) — 0001_init.sql indexes watchlist_id alone — so a blind
     insert leaves a real duplicate row that only read-time dedupe hides. Reading first
     makes the dedupe authoritative instead of cosmetic. */
  function symbolAdd(listId, symbol) {
    var t = String(symbol == null ? '' : symbol).trim();
    if (!listId || !t) return Promise.reject(new Error('bad-args'));
    return _listsGuard().then(function () {
      if (_cloudOf(listId)) return _symbolInsert(listId, t);
      return symbolsFetch(listId).then(function () { return _symbolInsert(listId, t); });
    });
  }

  function _symbolInsert(listId, t) {
    var c = _cloudOf(listId);
    if (!c) return { symbol: t, skipped: true };     // unread -> refuse, never blind-insert
    if (c.set[t]) return { symbol: t, skipped: true };
    return sb.from('watchlist_symbols')
      .insert({ watchlist_id: listId, symbol: t, section: SECTION, position: _nextPos(listId) })
      .then(function (res) {
        if (res.error) throw res.error;
        _noteInserted(listId, [t]);
        return { symbol: t };
      });
  }

  function symbolRemove(listId, symbol) {
    var t = String(symbol == null ? '' : symbol).trim();
    if (!listId || !t) return Promise.reject(new Error('bad-args'));
    return _listsGuard().then(function () {
      return sb.from('watchlist_symbols')
        .delete()
        .eq('watchlist_id', listId)   // list-scoped: never a bare symbol match
        .in('symbol', [t]);
    }).then(function (res) {
      if (res.error) throw res.error;
      var c = _cloudOf(listId);
      if (c) {
        delete c.set[t];
        c.order = c.order.filter(function (x) { return x !== t; });
        cacheWrite(listId, c.order.slice());
      }
      return { symbol: t };
    });
  }

  // ---- pull: fetch cloud symbols and merge into WL --------------------------
  function pull() {
    if (!user || !sb) return Promise.resolve();
    if (pullPending) return Promise.resolve();
    pullPending = true;
    setPill('syncing');

    return listsFetch()
      .then(function () { return resolveBoundList(); })
      .then(function (id) {
        // No list switcher ships in this wave, so the bound list is whatever ruling R1
        // resolves. A later UI switches it via lists.setActive(); the FOLD is resolved
        // separately and on demand, so nothing here creates a list speculatively.
        if (!wlId) wlId = id;
        return symbolsFetch(wlId);
      })
      .then(function (rows) {
        var items = rows.map(function (r) {
          return { t: r.symbol, added: r.created_at, note: '' };
        });
        var symbols = rows.map(function (r) { return r.symbol; });

        /* Capture what the ANONYMOUS visitor accumulated locally BEFORE the cloud merge
           touches the blob (ruling R1.1). Under R1 the BOUND list and the FOLD target
           can be different rows — bound 'Default', folding into a newly created
           'Watchlist'. Folding the post-merge blob therefore planted the bound list's
           entire membership into a list the user never asked for. The fold delivers
           what the visitor accumulated, and nothing else.

           Taken BEFORE the bind below: bindList re-points the blob at the list cache,
           and capturing after that would fold the cloud membership, not the visitor's. */
        var localBeforeMerge = _tickersOf(
          (window.WL && window.WL.getBlob) ? window.WL.getBlob() : null);

        /* Bind the page to the list we just read, WITH its name. Leaving listId
           null after pull is why the selector kept saying "My watchlist" over the
           53-name default (W4 2026-08-15). Listeners run synchronously. */
        try {
          document.dispatchEvent(new CustomEvent('wl-list-change', {
            detail: { listId: wlId, name: listNameOf(wlId) }
          }));
        } catch (e) {}

        // Merge cloud rows into the local blob (union: cloud wins for membership)
        if (window.WL && window.WL.merge && items.length > 0) {
          window.WL.merge({ v: 1, updated: nowISO(), items: items, order: symbols, settings: {} });
        }

        return _foldLocalIntoCloud(localBeforeMerge);
      })
      .then(function () {
        // fold the anonymous local book into the user's own rows (one shot, on
        // success only). portfolio.js already listed on wl-auth, so tell it to
        // re-list once rows actually moved.
        var hadLocal = pfRead().rows.length > 0;
        return _foldLocalPortfolio().then(function () {
          if (hadLocal && !pfRead().rows.length) {
            try { document.dispatchEvent(new CustomEvent('pf-folded')); } catch (e) {}
          }
        });
      })
      .then(function () {
        pullDoneAt = Date.now();
        pullPending = false;
        setPill('synced');
        // flush any push that arrived before its list had been read
        _flushQueuedPushes();
      })
      .catch(function (err) {
        pullPending = false;
        setPill('offline');
        warnOnce('pull', 'pull failed: ' + (err && err.message || err));
      });
  }

  // ---- one-time fold: local tickers not in cloud -> insert -------------------
  /* Retargeted in W1a: the fold lands in the list NAMED 'Watchlist' (created if
     absent), not in "whatever list sorted first". Both shipped behaviours are kept
     verbatim: ONE shot per device via the marker, and the marker is NOT written on an
     empty local book (that would consume the one-shot before the visitor ever built a
     list) nor on an error (so a failed fold retries).

     ORDER IS LOAD-BEARING (ruling R1). The marker check and the empty-book check come
     BEFORE the target is resolved, so an account with nothing to fold never triggers
     the create-if-absent path. That is what makes creation here on-demand rather than
     spurious, and it is why resolveBoundList() above is free to create nothing. */
  function _foldLocalIntoCloud(localTickers) {
    // Only fold once per device (not per session) to avoid repeated inserts on
    // every sign-in after the ongoing diff-push is the real mechanism.
    var already = false;
    try { already = !!localStorage.getItem(foldMarkerKey); } catch (e) {}
    if (already) return Promise.resolve();
    if (!user || !sb) return Promise.resolve();

    // `localTickers` is the PRE-MERGE capture from pull(). It is a parameter and not a
    // re-read of window.WL precisely so this function cannot see the merged blob.
    var tickers = (localTickers || []).filter(function (t) { return !!t; });
    if (tickers.length === 0) {
      // Do NOT mark folded: local is empty (fresh device or signed-out-built list).
      // Marking here would permanently consume the one-shot fold before any items exist.
      // Nor resolve a target: there is nothing to deliver, so nothing to create.
      return Promise.resolve();
    }

    // There IS content to deliver — now resolve (and if necessary create) the target,
    // and diff against ITS server rows, never the bound list's.
    return resolveFoldTarget()
      .then(function (id) {
        foldTargetId = id;
        if (_cloudOf(id)) return _foldInsert(tickers);
        return symbolsFetch(id).then(function () { return _foldInsert(tickers); });
      })
      .catch(function (err) {
        warnOnce('fold', 'one-time fold failed: ' + (err && err.message || err));
      });
  }

  function _foldInsert(tickers) {
    // Dedupe base and insert target are BOTH the fold target — never the bound list.
    // Under R1 divergence those are different rows, and using the bound list for
    // either one plants (or suppresses) the wrong symbols.
    var c = _cloudOf(foldTargetId);
    if (!c) return Promise.resolve();

    var toInsert = tickers.filter(function (t) { return !c.set[t]; });
    if (toInsert.length === 0) { _markFolded(); return Promise.resolve(); }

    // Insert sequentially; use maxPos+1 to avoid collisions after delete+add cycles
    var base = _nextPos(foldTargetId);
    var rows = toInsert.map(function (t, i) {
      return { watchlist_id: foldTargetId, symbol: t, section: SECTION, position: base + i };
    });

    return sb.from('watchlist_symbols')
      .insert(rows)
      .then(function (res) {
        if (res.error) throw res.error;
        _noteInserted(foldTargetId, toInsert);
        _markFolded();
      })
      .catch(function (err) {
        warnOnce('fold', 'one-time fold failed: ' + (err && err.message || err));
        // Don't mark folded on error so we retry next session
      });
  }

  function _markFolded() {
    try { localStorage.setItem(foldMarkerKey, '1'); } catch (e) {}
  }

  // ---- push: full-membership diff, STRICTLY SCOPED TO ONE LIST ---------------
  /* This diff DELETES cloud rows that are absent locally, which is exactly why it is
     the most dangerous code in the module under multi-list. Four properties hold
     jointly, and the named regression test pins all four:

       1. The target `listId` is captured at ENQUEUE time and carried through the
          debounce as an argument. Before this wave `_doPush` read a module-global
          `wlId` at FIRE time, so a list switch during the 600ms window redirected a
          blob at the wrong list.
       2. Debounce timers are PER LIST, so a push to list B cannot cancel (and silently
          drop) a pending push to list A.
       3. The delete candidate set is derived ONLY from `cloud[listId]` — a real server
          read of THAT list. No localStorage cache, of any list, is ever a delete
          input; a list that has not been read is not diffed at all (it queues).
       4. Every delete carries `.eq('watchlist_id', listId)`, so even a poisoned symbol
          list cannot reach another list's rows.

     Property 3 is the load-bearing one: a stale cache of list A cannot delete rows of
     list B because a cache is not a delete authority in the first place. */
  var _pushTimers = {};

  function _tickersOf(blob) {
    var seen = {}, out = [];
    if (!blob || !Array.isArray(blob.items)) return out;
    blob.items.forEach(function (it) {
      if (!it || !it.t || seen[it.t]) return;
      seen[it.t] = 1;
      out.push(it.t);
    });
    return out;
  }

  function _cancelPush(listId) {
    if (_pushTimers[listId]) { clearTimeout(_pushTimers[listId]); delete _pushTimers[listId]; }
    delete queuedPushes[listId];
  }

  // `tickers` is already a captured array — never a live blob (see WLCloud.push).
  function _schedulePush(listId, tickers) {
    clearTimeout(_pushTimers[listId]);
    _pushTimers[listId] = setTimeout(function () {
      delete _pushTimers[listId];
      // Never diff against a list we have not read: queue it for the pull to flush.
      if (!_cloudOf(listId)) { queuedPushes[listId] = tickers; return; }
      _trackedPush(listId, tickers);
    }, 600);
  }

  /* Flush pushes that fired before their list had been read. Each entry carries the
     ticker set captured at ENQUEUE time under its OWN key, so nothing is re-targeted
     here — a set whose owner was unknown was refused at enqueue and can never appear. */
  function _flushQueuedPushes() {
    Object.keys(queuedPushes).forEach(function (id) {
      var tickers = queuedPushes[id];
      delete queuedPushes[id];
      if (!id || id === 'null' || id === 'undefined') return;   // defensive: never a null target
      if (_cloudOf(id)) _trackedPush(id, tickers);
    });
  }

  function pushList(listId, symbols) {
    if (!user || !sb || !listId) return Promise.resolve(null);
    var c = _cloudOf(listId);
    if (!c) return Promise.resolve(null);      // unread list -> no diff, no delete

    var localSet = {};
    (symbols || []).forEach(function (t) { if (t) localSet[t] = true; });

    // Missing in this list -> insert. Present in THIS LIST's server rows but absent
    // locally -> delete. Both sides are scoped to `listId` by construction.
    var toInsert = Object.keys(localSet).filter(function (t) { return !c.set[t]; });
    var toDelete = Object.keys(c.set).filter(function (t) { return !localSet[t]; });

    var ops = [];

    if (toInsert.length > 0) {
      var base = _nextPos(listId);
      var rows = toInsert.map(function (t, i) {
        return { watchlist_id: listId, symbol: t, section: SECTION, position: base + i };
      });
      ops.push(
        sb.from('watchlist_symbols').insert(rows).then(function (res) {
          if (res.error) throw res.error;
          _noteInserted(listId, toInsert);
        })
      );
    }

    if (toDelete.length > 0) {
      ops.push(
        sb.from('watchlist_symbols')
          .delete()
          .eq('watchlist_id', listId)
          .in('symbol', toDelete)
          .then(function (res) {
            if (res.error) throw res.error;
            toDelete.forEach(function (t) { delete c.set[t]; });
            c.order = c.order.filter(function (x) { return !!c.set[x]; });
            cacheWrite(listId, c.order.slice());
          })
      );
    }

    if (ops.length === 0) return Promise.resolve({ inserted: 0, deleted: 0 });

    setPill('syncing');
    return Promise.all(ops).then(function () {
      setPill('synced');
      return { inserted: toInsert.length, deleted: toDelete.length };
    }).catch(function (err) {
      setPill('offline');
      warnOnce('push', 'push failed: ' + (err && err.message || err));
      return null;
    });
  }

  /* Bind the store to a different list. Deliberately does NOT push: a switch must
     never carry the previous list's membership into the new one (that is the
     full-diff wipe in another costume). The caller rebinds its own local blob on the
     `wl-list-change` event. Nothing in W1a calls this — it is the seam W2 drives. */
  function setActiveList(listId) {
    if (!listId) return Promise.reject(new Error('bad-args'));
    // A pending push against the list we are leaving is NOT cancelled: it is already
    // bound to that list, so it is a real edit of it, not stale state. Cancelling here
    // silently discarded the user's last change to the list they switched away from.
    return symbolsFetch(listId).then(function (rows) {
      /* `wlId` is published ONLY here, in the same synchronous step as the event that
         tells watchlist.js to rebind — never up front. Assigning it before the fetch
         resolved opened a window in which WLCloud.push(blob) — a caller that names no
         list, i.e. today's page — resolved its target to the NEW list while the blob
         still held the OLD list's membership. The full-membership diff then deleted the
         new list's rows and inserted the old list's (measured: 3 sibling rows deleted
         plus a foreign insert). Listeners run synchronously on dispatch, so no push can
         interleave between the assignment and the rebind. */
      wlId = listId;
      try {
        document.dispatchEvent(new CustomEvent('wl-list-change', {
          detail: { listId: listId, name: listNameOf(listId) }
        }));
      } catch (e) {}
      return rows;
    });
  }

  // ---- public WLCloud seam (watchlist.js calls this unconditionally) ---------
  window.WLCloud = {
    // `listId` is optional: callers that know nothing about lists (today's page) get
    // the active list, resolved HERE at enqueue time rather than at fire time.
    push: function (blob, listId) {
      if (!user || !sb) return;
      var target = listId || wlId;
      /* The ticker SET is captured HERE, paired with the target it was captured for.
         The blob is a LIVE object: watchlist.js mutates it in place (mergeInto) and
         REASSIGNS it on a rebind, so reading it later — at debounce fire, or worse at
         pull-flush time — can apply one list's membership to another. Capturing at
         enqueue is what makes the pairing immutable. */
      var tickers = _tickersOf(blob);
      if (!target) {
        /* No list is bound yet (the sign-in pull window). A ticker set with no known
           owner can NEVER be safely applied, so it is refused outright rather than
           queued for whatever `wlId` later becomes — that queue-then-resolve shape is
           a full-membership diff aimed at an arbitrary list. Nothing durable is lost:
           the set still lives in localStorage, and the next edit (or the next pull's
           merge) syncs it against a list that is actually bound. */
        warnOnce('push-unbound', 'push before any list was bound — refused, not queued');
        return;
      }
      _schedulePush(target, tickers);
    },
    activeListId: function () { return wlId; }
  };

  // ---- refetch-on-focus (if >60s since last pull) ----------------------------
  /* A pull MERGES cloud rows into the local blob (union: cloud wins for membership).
     That is correct after a settled edit and WRONG inside a pending push window: a
     removal made moments ago is still only local, so the merge hands the row straight
     back and the user watches their deletion undo itself. Reproduced on a tab switch
     within the 600 ms push debounce; recorded as W2 scope on PR #5461.

     The fix is a READ-SIDE guard only — nothing in the push or fold paths is touched,
     which is what keeps ruling R1/R1.1 and the frozen push-scoping contract intact.
     While any push is scheduled or queued, the refetch DEFERS and re-arms instead of
     firing; the retry is bounded so a permanently stuck queue can never spin. */
  var PUSH_SETTLE_MS = 800, PUSH_SETTLE_TRIES = 6;
  /* Three states have to be counted, not two. The debounce timer is deleted the moment
     `pushList` is CALLED, but the DELETE it issues is still in flight for a round trip
     — and a pull landing inside that window merges the row straight back, which is the
     exact bug the deferral exists to stop, just one RTT later. `_pushInFlight` closes
     that hole; it is incremented at the call sites rather than inside pushList, so the
     frozen push path itself is untouched. */
  var _pushInFlight = 0;
  function _pushPendingWith(timers, queued, inFlight) {
    return Object.keys(timers || {}).length > 0 ||
           Object.keys(queued || {}).length > 0 ||
           (inFlight || 0) > 0;
  }
  function pushPending() { return _pushPendingWith(_pushTimers, queuedPushes, _pushInFlight); }
  // wraps a pushList call so the in-flight window is counted without editing pushList
  function _trackedPush(listId, tickers) {
    _pushInFlight++;
    var done = function (r) { _pushInFlight--; return r; };
    return pushList(listId, tickers).then(done, function (e) { done(); throw e; });
  }
  function pullWhenSettled(tries) {
    if (!user || !sb) return;
    if (pushPending()) {
      if (tries <= 0) return;    // still busy after ~5s: the next focus/edit will pull
      setTimeout(function () { pullWhenSettled(tries - 1); }, PUSH_SETTLE_MS);
      return;
    }
    pull();
  }
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && user && sb && (Date.now() - pullDoneAt > 60000)) {
      pullWhenSettled(PUSH_SETTLE_TRIES);
    }
  });

  // ---- local portfolio store (signed-out) ------------------------------------
  // The anonymous visitor gets a REAL book, not a locked panel: the same
  // WatchStore.portfolio.* API backed by localStorage. Rows never leave the device
  // except into the user's own Supabase rows on the one-shot fold (PRD-R7/UWP-R1);
  // nothing position-derived is ever logged.
  var PF_KEY = 'mdash.pf.v1';
  var pfFoldMarkerKey = 'mdash.watchstore.pf_folded.v1';
  var pfLocalSeq = 0;

  function pfRead() {
    try {
      var raw = localStorage.getItem(PF_KEY);
      if (!raw) return { v: 1, rows: [] };
      var b = JSON.parse(raw);
      if (!b || typeof b !== 'object' || !Array.isArray(b.rows)) return { v: 1, rows: [] };
      return { v: 1, rows: b.rows.filter(function (r) { return r && r.ticker; }) };
    } catch (e) { return { v: 1, rows: [] }; }
  }
  // signature of the user-meaningful state — the same no-op discipline the watchlist
  // blob uses, so an identical re-write never fires a pointless storage event.
  function pfSig(rows) {
    return JSON.stringify((rows || []).map(function (r) {
      return [r.id, r.ticker, r.shares, r.entry_price, r.entry_date, r.notes, r.status];
    }).sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; }));
  }
  function pfWrite(rows) {
    var cur = pfRead().rows;
    if (pfSig(cur) === pfSig(rows)) return true;   // no-op: do not re-persist
    try { localStorage.setItem(PF_KEY, JSON.stringify({ v: 1, rows: rows })); return true; }
    catch (e) { return false; }
  }
  function pfClear() {
    if (!pfRead().rows.length) return;
    try { localStorage.removeItem(PF_KEY); } catch (e) {}
  }
  function pfNumOrNull(v) {
    if (v === '' || v === undefined || v === null) return null;
    var n = Number(v);
    return isNaN(n) ? null : n;
  }
  function pfNormalize(pos, id) {
    return {
      id: id,
      ticker: pos.ticker,
      shares: pfNumOrNull(pos.shares),
      entry_price: pfNumOrNull(pos.entry_price),
      entry_date: pos.entry_date || null,
      notes: pos.notes || null,
      status: pos.status === 'closed' ? 'closed' : 'open'
    };
  }
  // dedupe identity for the fold: ticker + entry_date + shares (spec §5.5)
  function pfKey(r) {
    var sh = pfNumOrNull(r && r.shares);
    return [String((r && r.ticker) || '').toUpperCase(),
            (r && r.entry_date) || '', sh === null ? '' : String(sh)].join('|');
  }
  /* Which local rows still need inserting, given what the account already holds.
     PURE — this is the part of the fold worth pinning in a test: fold twice and the
     second pass must plan nothing, or a re-login duplicates the visitor's book. */
  function pfFoldPlan(localRows, cloudRows) {
    var have = {};
    (cloudRows || []).forEach(function (r) { have[pfKey(r)] = 1; });
    var seen = {};
    return (localRows || []).filter(function (r) {
      var k = pfKey(r);
      if (have[k] || seen[k]) return false;   // also de-dupes within the local batch
      seen[k] = 1;
      return true;
    });
  }

  function pfLocalList() { return Promise.resolve(pfRead().rows.slice()); }
  function pfLocalUpsert(pos) {
    var rows = pfRead().rows;
    if (pos.id) {
      for (var i = 0; i < rows.length; i++) {
        if (String(rows[i].id) === String(pos.id)) {
          rows[i] = pfNormalize(pos, rows[i].id);
          return Promise.resolve(pfWrite(rows) ? rows[i] : null);
        }
      }
    }
    var row = pfNormalize(pos, 'loc-' + Date.now() + '-' + (++pfLocalSeq));
    rows.push(row);
    return Promise.resolve(pfWrite(rows) ? row : null);
  }
  function pfLocalRemove(id) {
    var rows = pfRead().rows.filter(function (r) { return String(r.id) !== String(id); });
    return Promise.resolve(pfWrite(rows) ? { id: id } : null);
  }
  function pfLocalClose(id) {
    var rows = pfRead().rows;
    for (var i = 0; i < rows.length; i++) {
      if (String(rows[i].id) === String(id)) { rows[i].status = 'closed'; break; }
    }
    return Promise.resolve(pfWrite(rows) ? { id: id } : null);
  }

  // ---- one-shot fold: local rows -> the user's own Supabase rows -------------
  // Mirrors the watchlist fold exactly: marker only on SUCCESS, so a failed fold is
  // retried next session rather than silently dropping the visitor's book.
  function _foldLocalPortfolio() {
    if (!user || !sb) return Promise.resolve();
    var already = false;
    try { already = !!localStorage.getItem(pfFoldMarkerKey); } catch (e) {}
    if (already) return Promise.resolve();
    var local = pfRead().rows;
    // Do NOT mark folded on an empty local book — that would consume the one-shot
    // before the visitor ever built one (the watchlist fold's exact trap).
    if (!local.length) return Promise.resolve();

    return sb.from('portfolio_positions')
      .select('ticker, entry_date, shares')
      .eq('user_id', user.id)
      .then(function (res) {
        if (res.error) throw res.error;
        var toInsert = pfFoldPlan(local, res.data || []);
        if (!toInsert.length) { _markPfFolded(); pfClear(); return; }
        var rows = toInsert.map(function (r) {
          return {
            user_id: user.id, ticker: r.ticker, shares: pfNumOrNull(r.shares),
            entry_price: pfNumOrNull(r.entry_price), entry_date: r.entry_date || null,
            notes: r.notes || null, status: r.status === 'closed' ? 'closed' : 'open',
            updated_at: new Date().toISOString()
          };
        });
        return sb.from('portfolio_positions').insert(rows).then(function (ins) {
          if (ins.error) throw ins.error;
          _markPfFolded();
          pfClear();
        });
      })
      .catch(function (err) {
        // no marker -> retried next session. Message only; never row contents.
        warnOnce('pf-fold', 'portfolio fold failed: ' + (err && err.message || err));
      });
  }
  function _markPfFolded() {
    try { localStorage.setItem(pfFoldMarkerKey, '1'); } catch (e) {}
  }

  // ---- portfolio CRUD --------------------------------------------------------
  // Targets portfolio_positions when signed in; the localStorage book when signed out.
  // All cloud queries filter by user_id = session user.
  //
  // A1A authority law (research/market_os/…A1A_COMMISSIONING…md §10):
  //   anonymous     -> the local Portfolio is canonical
  //   authenticated -> the cloud Portfolio is canonical
  // A signed-in session is NEVER "local mode", even when the cloud read/write most
  // recently failed — `portfolioOk` is a diagnostic used for last-good bookkeeping and
  // the read-state banner, never a router to the anonymous local book. The old shape
  // (`_isLocalMode` including `!portfolioOk`) is exactly Turn 6's defect "authenticated
  // cloud-to-local fork": one failed read silently and PERMANENTLY rerouted every later
  // read AND write to the anonymous local book for the rest of the session — never
  // resolved, never disclosed, and never the visitor's own local data to begin with.

  var pfLastGoodCloud = null;   // {rows, at} — the last rows a CLOUD read actually returned
  // the current read-state answer, refreshed on every portfolioList() call
  var pfReadState = { authority: 'local', state: 'ready', last_good_at: null, warning: null };

  function _portfolioGuard() {
    if (!user || !sb) return Promise.reject(new Error('no-session'));
    return Promise.resolve();
  }
  // signed-out only. A degraded authenticated session is NOT local mode — see the law
  // above; it is 'cloud' authority in a 'degraded' or 'error' read_state instead.
  function _isLocalMode() { return !user; }
  /* A1A (review finding S6): `user` is set the instant onAuthUser sees a session, but
     the shared Supabase client resolves ASYNCHRONOUSLY afterward (`getClient().then
     (c => sb = c)`) — and portfolio.js's `onAuth()` runs off the FIRST 'wl-auth',
     dispatched BEFORE that resolves. In that window `user` is truthy and `sb` is not:
     `!user||!sb` used to read as "local mode" and a signed-in load briefly rendered
     the anonymous LOCAL book under a 'local' authority/chip. This is neither anonymous
     (there IS a user) nor ready cloud (no client yet) — a THIRD transitional state. */
  function _isCloudLoading() { return !!user && !sb; }

  function portfolioList() {
    if (_isCloudLoading()) {
      // never local rows, never an error banner for plain loading
      pfReadState = { authority: 'cloud', state: 'loading', last_good_at: null, warning: null };
      return Promise.resolve(null);
    }
    if (_isLocalMode()) {
      pfReadState = { authority: 'local', state: 'ready', last_good_at: null, warning: null };
      return pfLocalList();
    }
    return _portfolioGuard().then(function () {
      return sb.from('portfolio_positions')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at');
    }).then(function (res) {
      if (res.error) throw res.error;
      var rows = res.data || [];
      portfolioOk = true;
      pfLastGoodCloud = { rows: rows.slice(), at: nowISO() };
      pfReadState = { authority: 'cloud', state: 'ready', last_good_at: pfLastGoodCloud.at, warning: null };
      return rows;
    }).catch(function (err) {
      portfolioOk = false;
      warnOnce('portfolio-list', 'portfolio list failed: ' + (err && err.message || err));
      /* NEVER substitute the anonymous local Portfolio for a signed-in session's cloud
         read, and NEVER assert zero. Preserve last-good cloud rows (degraded, read-only)
         when we have them; otherwise resolve `null` — an explicit "we do not know",
         never an empty array standing in for a true zero. A durable authenticated
         offline outbox is a separate, later capability (A1A does not build one). */
      if (pfLastGoodCloud) {
        pfReadState = { authority: 'cloud', state: 'degraded',
                         last_good_at: pfLastGoodCloud.at, warning: 'cloud-unavailable' };
        return pfLastGoodCloud.rows.slice();
      }
      pfReadState = { authority: 'cloud', state: 'error', last_good_at: null, warning: 'cloud-unavailable' };
      return null;
    });
  }
  function portfolioReadState() { return pfReadState; }

  function portfolioUpsert(pos) {
    // pos: { ticker, shares, entry_price, entry_date, notes, status }
    // status must be 'open' or 'closed'
    // A1A (S6): a signed-in write during the cloud-loading window must never land in
    // the anonymous local book — reject cleanly; the caller must not claim Saved.
    if (_isCloudLoading()) return Promise.resolve(null);
    if (_isLocalMode()) return pfLocalUpsert(pos);
    return _portfolioGuard().then(function () {
      function toNumOrNull(v) {
        if (v === '' || v === undefined || v === null) return null;
        var n = Number(v);
        return isNaN(n) ? null : n;
      }
      var row = {
        user_id: user.id,
        ticker: pos.ticker,
        shares: toNumOrNull(pos.shares),
        entry_price: toNumOrNull(pos.entry_price),
        entry_date: pos.entry_date || null,
        notes: pos.notes || null,
        status: pos.status === 'closed' ? 'closed' : 'open',
        updated_at: new Date().toISOString()
      };
      if (pos.id) {
        return sb.from('portfolio_positions')
          .update(row)
          .eq('id', pos.id)
          .eq('user_id', user.id)
          .select()
          .single()
          .then(function (res) {
            if (res.error) throw res.error;
            return res.data;
          });
      }
      return sb.from('portfolio_positions')
        .insert(row)
        .select()
        .single()
        .then(function (res) {
          if (res.error) throw res.error;
          return res.data;
        });
    }).catch(function (err) {
      portfolioOk = false;
      warnOnce('portfolio-upsert', 'portfolio upsert failed: ' + (err && err.message || err));
      return null;
    });
  }

  function portfolioClose(id) {
    if (_isCloudLoading()) return Promise.resolve(null);
    if (_isLocalMode()) return pfLocalClose(id);
    return _portfolioGuard().then(function () {
      return sb.from('portfolio_positions')
        .update({ status: 'closed', updated_at: new Date().toISOString() })
        .eq('id', id)
        .eq('user_id', user.id)
        .select()
        .single()
        .then(function (res) {
          if (res.error) throw res.error;
          return res.data;
        });
    }).catch(function (err) {
      portfolioOk = false;
      warnOnce('portfolio-close', 'portfolio close failed: ' + (err && err.message || err));
      return null;
    });
  }

  function portfolioRemove(id) {
    if (_isCloudLoading()) return Promise.resolve(null);
    if (_isLocalMode()) return pfLocalRemove(id);
    return _portfolioGuard().then(function () {
      return sb.from('portfolio_positions')
        .delete()
        .eq('id', id)
        .eq('user_id', user.id)
        .then(function (res) {
          if (res.error) throw res.error;
          return { id: id };
        });
    }).catch(function (err) {
      portfolioOk = false;
      warnOnce('portfolio-remove', 'portfolio remove failed: ' + (err && err.message || err));
      return null;
    });
  }

  // ---- public API ------------------------------------------------------------
  window.WatchStore = {
    status: status,
    pull: pull,
    user: function () { return user; },
    portfolioOk: function () { return portfolioOk; },
    /* Registered multi-list seam (W1a). Signed-out callers get a rejected promise —
       the anonymous store is watchlist.js's `mdash.watchlist.v1` blob, untouched. */
    lists: {
      all: listsAll,                 // cached view, no network
      refresh: listsFetch,
      create: listCreate,
      rename: listRename,
      remove: listRemove,
      setActive: setActiveList,
      foldTargetId: function () { return foldTargetId; },
      activeId: function () { return wlId; },
      foldTargetName: function () { return LIST_NAME; },
      cacheKey: cacheKey,
      cached: cacheRead
    },
    symbols: {
      list: symbolsFetch,            // server read; also refreshes the list's cache
      add: symbolAdd,
      remove: symbolRemove,
      push: pushList                 // full-membership diff, scoped to one list
    },
    portfolio: {
      list: portfolioList,
      upsert: portfolioUpsert,
      close: portfolioClose,
      remove: portfolioRemove,
      // 'local' = the localStorage book — signed OUT only (A1A authority law, §10).
      isLocal: _isLocalMode,
      // {authority, state, last_good_at, warning} — refreshed by every list() call.
      // 'local' authority is always 'ready'; 'cloud' authority may be 'ready',
      // 'degraded' (last-good rows, read-only) or 'error' (no last-good; list()
      // resolved null). Private — never logged, published, or sent to analytics.
      readState: portfolioReadState
    }
  };

  // ---- auth reactions --------------------------------------------------------
  function onAuthUser(u) {
    // Dedup: TOKEN_REFRESHED, USER_UPDATED, INITIAL_SESSION all fire onAuthUser.
    // Only re-init when the effective uid actually changes (null = signed-out).
    var uid = (u && u.id) ? u.id : null;
    if (uid === lastAuthUid) return;
    lastAuthUid = uid;

    /* A1A (review finding B1 — cross-user private-holdings leak): the cached
       last-good cloud rows and read-state are PER-USER private data. Reset them on
       EVERY uid transition, sign-in and sign-out alike, before anything else below
       runs — otherwise a second user signing in on the same page session, whose own
       first cloud read then fails, would be served the FIRST user's cached
       "last-good" rows as their own degraded state. */
    pfLastGoodCloud = null;
    pfReadState = { authority: 'local', state: 'ready', last_good_at: null, warning: null };

    user = u || null;
    if (!user) {
      sb = null;
      wlId = null;
      foldTargetId = null;
      listsCache = [];
      // Drop every server-read membership: nothing may be diffed (or deleted) against
      // a set that belonged to the account that just signed out. The per-list
      // localStorage caches are left in place — they are that account's own optimistic
      // state on this device, and clearing them would discard unsynced local edits.
      cloud = {};
      Object.keys(_pushTimers).forEach(function (k) { clearTimeout(_pushTimers[k]); });
      _pushTimers = {};
      pullDoneAt = 0;
      queuedPushes = {};
      portfolioOk = true;
      try { sessionStorage.removeItem('wl_auth_reloaded'); } catch (e) { /* n/a */ }
      showSignedOut();
      document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: null } }));
      return;
    }
    // signed in: the write-through state is whatever the pull below resolves. Say
    // "saving" now rather than claiming "saved" before anything has been read.
    showAccount(user.email || '');
    setPill('finishing');
    // Signed in from the anonymous shell: the account-gated page scripts
    // (stockdata.js and the risk stack) were 401'd at load and an in-page auth
    // event cannot re-run <script> tags, so their signal lanes would stay dark
    // until a manual refresh. Reload ONCE with the session cookie in place;
    // the latch keeps a still-gated asset from ever looping the page.
    if (!window.SD) {
      try {
        if (!sessionStorage.getItem('wl_auth_reloaded')) {
          sessionStorage.setItem('wl_auth_reloaded', '1');
          location.reload();
          return;
        }
      } catch (e) { /* storage denied -> stay on the bare shell */ }
    }
    document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: user } }));
    // Resolve the shared Supabase client then kick off the initial pull
    var getClient = window.getSupabaseClient;
    if (!getClient) { setPill('offline'); warnOnce('no-client', 'getSupabaseClient not found'); return; }
    getClient().then(function (c) {
      sb = c;
      pull();
      /* A1A (review finding S6): the FIRST 'wl-auth' above fired before `sb`
         resolved, so portfolio.js's onAuth() ran during the cloud-loading window
         (`user` set, `sb` not yet) and could read nothing but the loading
         placeholder (see portfolioList's `_isCloudLoading()` branch). Re-fire now
         that `sb` is ready so the Portfolio re-reads the real cloud rows without
         any user interaction. */
      document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: user } }));
    }).catch(function (err) {
      setPill('offline');
      warnOnce('client', 'getSupabaseClient failed: ' + (err && err.message || err));
    });
  }

  // ---- init ------------------------------------------------------------------
  function init() {
    var CFG = window.SUPABASE_CFG;
    var enabled = CFG && CFG.url && CFG.anonKey;
    var chip = el('ws_savechip');      // the W2 workspace host
    var box  = el('wl_auth');          // the PRE-W2 Account Sync panel

    /* THREE pages, one file — and only two of them want a cloud session.

       W2 deleted the Account Sync panel, and with it the `if (!box) return;` guard that
       had been doing double duty: it also kept this module DORMANT on every page that
       merely loads it (committee.html loads watchstore.js and has never touched a list).
       Without it that page became a full cloud participant — MDXAuth wiring, a one-time
       reload it never asked for, and a reachable list-creation path. The guard is
       restored in its general form: no sync host of EITHER generation -> do nothing at
       all. No onChange, no reload, no pull, no fold. */
    if (!chip && !box) return;

    // Local-only unless BOTH the config is baked AND the shared client exists. The
    // chip still has to say so — a page that silently shows nothing about where the
    // list lives is exactly the husk this wave removed.
    if (!enabled || !window.MDXAuth || !window.MDXAuth.onChange) {
      if (box) box.style.display = 'none';
      setPill('local');
      return;
    }

    /* PRE-W2 markup (the render-lane lag window): the live page carries
       `#wl_auth` with an inline `display:none`, so failing to un-hide it here serves a
       page with no sync state, no sign-in CTA and no account row — the husk again, from
       the other direction. Restore the panel and its two buttons verbatim. */
    if (box) {
      box.style.display = 'flex';
      if (el('wl_signin')) {
        el('wl_signin').textContent = L('signin');
        el('wl_signin').style.display = 'inline-block';
        el('wl_signin').addEventListener('click', function () {
          if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signin');
        });
      }
      if (el('wl_signout')) {
        el('wl_signout').textContent = L('signout');
        el('wl_signout').addEventListener('click', function () {
          if (window.MDXAuth && window.MDXAuth.signOut) window.MDXAuth.signOut();
          else showSignedOut();
        });
      }
      if (el('wl_authbox')) el('wl_authbox').style.display = 'none';
      document.addEventListener('langchange', relabel);
    }

    showSignedOut();
    // Establish the signed-out baseline so lastAuthUid=null; a later real
    // sign-in (null→uid) still transitions correctly.
    lastAuthUid = null;

    /* Offline is a real, reachable state and the chip must be able to say it. The
       browser tells us directly; a signed-out visitor is unaffected because their list
       genuinely still lives in this browser either way. */
    window.addEventListener('offline', function () { if (user && sb) setPill('offline'); });
    window.addEventListener('online', function () { if (user && sb) pull(); });

    // If a session is already established before init (e.g. page reload while
    // signed in), show 'finishing' until onChange fires with the real user.
    if (window.MDXAuth.hasSession && window.MDXAuth.hasSession()) setPill('finishing');

    window.MDXAuth.onChange(function (u, evt) {
      // SDK blocked/failed to load (e.g. behind the GFW): settle to offline, not
      // a forever "Finishing sign-in…" pill.
      if (!u && evt === 'SDK_FAILED') { setPill('offline'); return; }
      onAuthUser(u);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  /* Node-test surface: the local book's pure helpers plus a dependency injector for
     the one-shot fold, so the "marker only on success" discipline can be pinned
     without a browser. `module` is undefined in the browser, so none of this exists
     at runtime on the site (the same guard risk_core.js / watchlist_risk.js use). */
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      pfKey: pfKey, pfFoldPlan: pfFoldPlan, pfRead: pfRead, pfWrite: pfWrite,
      foldLocalPortfolio: _foldLocalPortfolio,
      foldLocalIntoCloud: _foldLocalIntoCloud,
      portfolio: window.WatchStore.portfolio,
      lists: window.WatchStore.lists,
      symbols: window.WatchStore.symbols,
      pull: pull,
      pushList: pushList,
      resolveBoundList: resolveBoundList,
      resolveFoldTarget: resolveFoldTarget,
      cacheKey: cacheKey, cacheRead: cacheRead, cacheWrite: cacheWrite,
      tickersOf: _tickersOf,
      _setTestSession: function (u, client) { user = u; sb = client; },
      // A1A test seam (review B1): the real auth-transition reset logic, so the
      // cross-user last-good-cloud leak can be pinned against the actual function
      // rather than reconstructed by hand in a test.
      onAuthUser: onAuthUser,
      // W2: the read-side guard that keeps a focus refetch from reverting an edit
      // that is still only local (see tests/test_watchlist_workspace_js.py)
      _testHooks: {
        pushPendingWith: _pushPendingWith,
        inFlight: function () { return _pushInFlight; }
      },
      // seed the resolved-list state a real pull would have established
      _setTestLists: function (s) {
        if (!s) return;
        if ('lists' in s) listsCache = (s.lists || []).slice();
        if ('foldTargetId' in s) foldTargetId = s.foldTargetId;
        if ('activeId' in s) wlId = s.activeId;
        if ('cloud' in s) cloud = s.cloud || {};
      },
      _testState: function () {
        return { foldTargetId: foldTargetId, activeId: wlId,
                 lists: listsCache.slice(), cloud: cloud };
      }
    };
  }
})();

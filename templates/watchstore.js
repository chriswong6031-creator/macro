/* watchstore.js — Supabase relational sync for the Watchlist (replaces auth.js doc-blob path).

   Plugs into the same seams auth.js used:
     • window.WLCloud.push(blob)  — called by watchlist.js after every local change
     • window.WL.merge(blob)      — called here after pull to fold cloud rows in
     • window.MDXAuth.onChange    — auth events from theme.js shared session
     • window.getSupabaseClient() — shared Supabase client from theme.js

   Also owns the watchlist sync UI (formerly auth.js):
     • Bilingual sync pill (#wl_syncpill): synced/syncing/local/offline/finishing
     • Sign-in button (#wl_signin) → MDXAuth.open('signin')
     • Account row (#wl_account, #wl_who) with sign-out (#wl_signout)
     • #wl_auth panel show/hide; langchange relabeling

   When there is no session (logged out, no config, SDK blocked):
     • All paths are dormant; localStorage-only behavior is unchanged.
     • window.WLCloud.push() is a no-op (safe: watchlist.js calls it unconditionally).
     • On pages without the wl_* elements the UI helpers are all inert via el() guards.

   W1 scope: ticker sync only. Notes / order / settings remain localStorage-only
   (the relational schema has no columns for them). The blob carries them; we do not
   try to sync them. */
(function () {
  'use strict';

  // ---- state -----------------------------------------------------------------
  var sb = null;           // shared Supabase client, set on auth
  var user = null;         // current auth user
  var lastAuthUid = undefined;  // dedup guard: undefined = never seen; null = signed-out
  var wlId = null;         // resolved primary watchlist row id
  var cloudSet = null;     // Set of symbol strings last pulled/pushed (null = not yet pulled)
  var pullPending = false; // pull in progress
  var pullDoneAt = 0;      // epoch ms of last successful pull
  var queuedBlob = null;   // latest push blob queued before pull completed
  var foldMarkerKey = 'mdash.watchstore.folded.v1'; // localStorage marker for one-time fold

  var SECTION = 'Watchlist';
  var LIST_NAME = 'Watchlist';
  var maxPos = -1;  // monotonic high-water mark for position; avoids collisions after delete+add cycles

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

  function setPill(state) {
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

  // ---- debounce --------------------------------------------------------------
  function debounce(fn, ms) {
    var h;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(h);
      h = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

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
    if (cloudSet !== null) return 'cloud';
    return 'local';
  }

  // ---- resolve primary watchlist (auto-create if missing) --------------------
  function resolvePrimaryList() {
    return sb.from('watchlists')
      .select('id')
      .eq('user_id', user.id)
      .order('position')
      .order('created_at', { ascending: true })
      .limit(1)
      .then(function (res) {
        if (res.error) throw res.error;
        if (res.data && res.data.length > 0) {
          return res.data[0].id;
        }
        // Auto-create the first watchlist (Terminal idiom: position=0)
        return sb.from('watchlists')
          .insert({ user_id: user.id, name: LIST_NAME, position: 0 })
          .select('id')
          .single()
          .then(function (ins) {
            if (ins.error) throw ins.error;
            return ins.data.id;
          });
      });
  }

  // ---- pull: fetch cloud symbols and merge into WL --------------------------
  function pull() {
    if (!user || !sb) return Promise.resolve();
    if (pullPending) return Promise.resolve();
    pullPending = true;
    setPill('syncing');

    return resolvePrimaryList()
      .then(function (id) {
        wlId = id;
        return sb.from('watchlist_symbols')
          .select('symbol, position, created_at')
          .eq('watchlist_id', wlId)
          .order('position');
      })
      .then(function (res) {
        if (res.error) throw res.error;
        var rows = res.data || [];
        cloudSet = {};
        // rows are ordered by position; last row holds the current max (monotonic)
        maxPos = rows.length > 0 ? (rows[rows.length - 1].position || 0) : -1;
        var items = rows.map(function (r) {
          cloudSet[r.symbol] = true;
          return { t: r.symbol, added: r.created_at, note: '' };
        });
        var symbols = rows.map(function (r) { return r.symbol; });

        // Merge cloud rows into the local blob (union: cloud wins for membership)
        if (window.WL && window.WL.merge && items.length > 0) {
          window.WL.merge({ v: 1, updated: new Date().toISOString(), items: items, order: symbols, settings: {} });
        }

        return _foldLocalIntoCloud();
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
        // flush any push that arrived before pull finished
        if (queuedBlob) {
          var b = queuedBlob;
          queuedBlob = null;
          _doPush(b);
        }
      })
      .catch(function (err) {
        pullPending = false;
        setPill('offline');
        warnOnce('pull', 'pull failed: ' + (err && err.message || err));
      });
  }

  // ---- one-time fold: local tickers not in cloud -> insert -------------------
  function _foldLocalIntoCloud() {
    // Only fold once per device (not per session) to avoid repeated inserts on
    // every sign-in after the ongoing diff-push is the real mechanism.
    var already = false;
    try { already = !!localStorage.getItem(foldMarkerKey); } catch (e) {}
    if (already) return Promise.resolve();

    var blob = window.WL && window.WL.getBlob ? window.WL.getBlob() : null;
    if (!blob || !Array.isArray(blob.items) || blob.items.length === 0) {
      // Do NOT mark folded: local is empty (fresh device or signed-out-built list).
      // Marking here would permanently consume the one-shot fold before any items exist.
      return Promise.resolve();
    }

    var toInsert = blob.items.filter(function (it) { return it && it.t && !cloudSet[it.t]; });
    if (toInsert.length === 0) { _markFolded(); return Promise.resolve(); }

    // Insert sequentially; use maxPos+1 to avoid collisions after delete+add cycles
    var rows = toInsert.map(function (it, i) {
      return { watchlist_id: wlId, symbol: it.t, section: SECTION, position: maxPos + 1 + i };
    });

    return sb.from('watchlist_symbols')
      .insert(rows)
      .then(function (res) {
        if (res.error) throw res.error;
        toInsert.forEach(function (it) { cloudSet[it.t] = true; });
        maxPos += toInsert.length;
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

  // ---- push: diff blob.items vs cloudSet and apply deltas -------------------
  // Gate: pushes arriving before pull completes are queued; only the latest is kept.
  var _debouncedPush = debounce(function (blob) {
    // Still waiting for pull to finish: queue this blob (latest wins)
    if (cloudSet === null) {
      queuedBlob = blob;
      return;
    }
    _doPush(blob);
  }, 600);

  function _doPush(blob) {
    if (!user || !sb || !wlId) return;
    if (!blob || !Array.isArray(blob.items)) return;

    var localTickers = {};
    blob.items.forEach(function (it) { if (it && it.t) localTickers[it.t] = true; });

    var toInsert = [];
    var toDelete = [];

    // Missing in cloud -> insert
    Object.keys(localTickers).forEach(function (t) {
      if (!cloudSet[t]) toInsert.push(t);
    });

    // Present in cloud but absent from local blob -> delete
    Object.keys(cloudSet).forEach(function (t) {
      if (!localTickers[t]) toDelete.push(t);
    });

    var ops = [];

    if (toInsert.length > 0) {
      var rows = toInsert.map(function (t, i) {
        return { watchlist_id: wlId, symbol: t, section: SECTION, position: maxPos + 1 + i };
      });
      ops.push(
        sb.from('watchlist_symbols').insert(rows).then(function (res) {
          if (res.error) throw res.error;
          toInsert.forEach(function (t) { cloudSet[t] = true; });
          maxPos += toInsert.length;
        })
      );
    }

    if (toDelete.length > 0) {
      ops.push(
        sb.from('watchlist_symbols')
          .delete()
          .eq('watchlist_id', wlId)
          .in('symbol', toDelete)
          .then(function (res) {
            if (res.error) throw res.error;
            toDelete.forEach(function (t) { delete cloudSet[t]; });
          })
      );
    }

    if (ops.length === 0) return;

    setPill('syncing');
    Promise.all(ops).then(function () {
      setPill('synced');
    }).catch(function (err) {
      setPill('offline');
      warnOnce('push', 'push failed: ' + (err && err.message || err));
    });
  }

  // ---- public WLCloud seam (watchlist.js calls this unconditionally) ---------
  window.WLCloud = {
    push: function (blob) {
      if (!user || !sb) return;
      _debouncedPush(blob);
    }
  };

  // ---- refetch-on-focus (if >60s since last pull) ----------------------------
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && user && sb && (Date.now() - pullDoneAt > 60000)) {
      pull();
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
  // All cloud queries filter by user_id = session user. If RLS is not yet applied,
  // errors are caught and logged; status() reports 'local' so callers degrade.

  function _portfolioGuard() {
    if (!user || !sb) return Promise.reject(new Error('no-session'));
    if (!portfolioOk) return Promise.reject(new Error('portfolio-unavailable'));
    return Promise.resolve();
  }
  // signed-out (or a portfolio backend that has gone unavailable) -> the local book
  function _isLocalMode() { return !user || !sb || !portfolioOk; }

  function portfolioList() {
    if (_isLocalMode()) return pfLocalList();
    return _portfolioGuard().then(function () {
      return sb.from('portfolio_positions')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at');
    }).then(function (res) {
      if (res.error) throw res.error;
      return res.data || [];
    }).catch(function (err) {
      portfolioOk = false;
      warnOnce('portfolio-list', 'portfolio list failed: ' + (err && err.message || err));
      // backend unavailable -> fall back to the local book rather than showing nothing
      return pfLocalList();
    });
  }

  function portfolioUpsert(pos) {
    // pos: { ticker, shares, entry_price, entry_date, notes, status }
    // status must be 'open' or 'closed'
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
    portfolio: {
      list: portfolioList,
      upsert: portfolioUpsert,
      close: portfolioClose,
      remove: portfolioRemove,
      // 'local' = the localStorage book (signed out, or backend unavailable)
      isLocal: _isLocalMode
    }
  };

  // ---- auth reactions --------------------------------------------------------
  function onAuthUser(u) {
    // Dedup: TOKEN_REFRESHED, USER_UPDATED, INITIAL_SESSION all fire onAuthUser.
    // Only re-init when the effective uid actually changes (null = signed-out).
    var uid = (u && u.id) ? u.id : null;
    if (uid === lastAuthUid) return;
    lastAuthUid = uid;

    user = u || null;
    if (!user) {
      sb = null;
      wlId = null;
      cloudSet = null;
      maxPos = -1;
      pullDoneAt = 0;
      queuedBlob = null;
      portfolioOk = true;
      try { sessionStorage.removeItem('wl_auth_reloaded'); } catch (e) { /* n/a */ }
      showSignedOut();
      document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: null } }));
      return;
    }
    showAccount(user.email || '');
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
    }).catch(function (err) {
      setPill('offline');
      warnOnce('client', 'getSupabaseClient failed: ' + (err && err.message || err));
    });
  }

  // ---- init ------------------------------------------------------------------
  function init() {
    var CFG = window.SUPABASE_CFG;
    var enabled = CFG && CFG.url && CFG.anonKey;
    var box = el('wl_auth');

    // Local-only unless BOTH the config is baked AND the shared client exists.
    if (!enabled || !window.MDXAuth || !window.MDXAuth.onChange) {
      if (box) box.style.display = 'none';
      return;
    }
    if (!box) return;  // nothing to wire if the panel isn't on the page (e.g. committee.html)

    box.style.display = 'flex';
    relabel();

    // Wire sign-in button -> global modal
    var si = el('wl_signin');
    if (si) si.addEventListener('click', function () {
      if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signin');
    });

    // Wire sign-out button
    var so = el('wl_signout');
    if (so) so.addEventListener('click', function () {
      if (window.MDXAuth && window.MDXAuth.signOut) window.MDXAuth.signOut();
      else showSignedOut();  // UI also updates via the mdx-auth event
    });

    // The legacy magic-link box is retired — sign-in goes through the global modal
    if (el('wl_authbox')) el('wl_authbox').style.display = 'none';

    showSignedOut();
    // Establish the signed-out baseline so lastAuthUid=null; a later real
    // sign-in (null→uid) still transitions correctly.
    lastAuthUid = null;

    // Refetch on tab focus (already wired above for >60s gate)
    document.addEventListener('langchange', relabel);

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
      portfolio: window.WatchStore.portfolio,
      _setTestSession: function (u, client) { user = u; sb = client; }
    };
  }
})();

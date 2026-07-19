/* watchstore.js — Supabase relational sync for the Watchlist (replaces auth.js doc-blob path).

   Plugs into the same seams auth.js used:
     • window.WLCloud.push(blob)  — called by watchlist.js after every local change
     • window.WL.merge(blob)      — called here after pull to fold cloud rows in
     • window.MDXAuth.onChange    — auth events from theme.js shared session
     • window.getSupabaseClient() — shared Supabase client from theme.js

   When there is no session (logged out, no config, SDK blocked):
     • All paths are dormant; localStorage-only behavior is unchanged.
     • window.WLCloud.push() is a no-op (safe: watchlist.js calls it unconditionally).

   W1 scope: ticker sync only. Notes / order / settings remain localStorage-only
   (the relational schema has no columns for them). The blob carries them; we do not
   try to sync them. */
(function () {
  'use strict';

  // ---- state -----------------------------------------------------------------
  var sb = null;           // shared Supabase client, set on auth
  var user = null;         // current auth user
  var wlId = null;         // resolved primary watchlist row id
  var cloudSet = null;     // Set of symbol strings last pulled/pushed (null = not yet pulled)
  var pullPending = false; // pull in progress
  var pullDoneAt = 0;      // epoch ms of last successful pull
  var queuedBlob = null;   // latest push blob queued before pull completed
  var foldMarkerKey = 'mdash.watchstore.folded.v1'; // localStorage marker for one-time fold

  var SECTION = 'Watchlist';
  var LIST_NAME = 'Watchlist';

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

    return resolvePrimaryList()
      .then(function (id) {
        wlId = id;
        return sb.from('watchlist_symbols')
          .select('symbol, created_at')
          .eq('watchlist_id', wlId)
          .order('position');
      })
      .then(function (res) {
        if (res.error) throw res.error;
        var rows = res.data || [];
        cloudSet = {};
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
        pullDoneAt = Date.now();
        pullPending = false;
        // flush any push that arrived before pull finished
        if (queuedBlob) {
          var b = queuedBlob;
          queuedBlob = null;
          _doPush(b);
        }
      })
      .catch(function (err) {
        pullPending = false;
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
      _markFolded();
      return Promise.resolve();
    }

    var toInsert = blob.items.filter(function (it) { return it && it.t && !cloudSet[it.t]; });
    if (toInsert.length === 0) { _markFolded(); return Promise.resolve(); }

    // Insert sequentially to keep positions sane (position = current count + index)
    var basePosition = Object.keys(cloudSet).length;
    var rows = toInsert.map(function (it, i) {
      return { watchlist_id: wlId, symbol: it.t, section: SECTION, position: basePosition + i };
    });

    return sb.from('watchlist_symbols')
      .insert(rows)
      .then(function (res) {
        if (res.error) throw res.error;
        toInsert.forEach(function (it) { cloudSet[it.t] = true; });
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
      var basePos = Object.keys(cloudSet).length;
      var rows = toInsert.map(function (t, i) {
        return { watchlist_id: wlId, symbol: t, section: SECTION, position: basePos + i };
      });
      ops.push(
        sb.from('watchlist_symbols').insert(rows).then(function (res) {
          if (res.error) throw res.error;
          toInsert.forEach(function (t) { cloudSet[t] = true; });
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

    Promise.all(ops).catch(function (err) {
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

  // ---- portfolio CRUD --------------------------------------------------------
  // Targets portfolio_positions. All queries filter by user_id = session user.
  // If RLS is not yet applied, errors are caught and logged; status() reports 'local'
  // for portfolio so callers can degrade gracefully.

  function _portfolioGuard() {
    if (!user || !sb) return Promise.reject(new Error('no-session'));
    if (!portfolioOk) return Promise.reject(new Error('portfolio-unavailable'));
    return Promise.resolve();
  }

  function portfolioList() {
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
      return [];
    });
  }

  function portfolioUpsert(pos) {
    // pos: { ticker, shares, entry_price, entry_date, notes, status }
    // status must be 'open' or 'closed'
    return _portfolioGuard().then(function () {
      var row = {
        user_id: user.id,
        ticker: pos.ticker,
        shares: pos.shares,
        entry_price: pos.entry_price,
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

  // ---- public API ------------------------------------------------------------
  window.WatchStore = {
    status: status,
    pull: pull,
    portfolio: {
      list: portfolioList,
      upsert: portfolioUpsert,
      close: portfolioClose
    }
  };

  // ---- auth reactions --------------------------------------------------------
  function onAuthUser(u) {
    user = u || null;
    if (!user) {
      sb = null;
      wlId = null;
      cloudSet = null;
      pullDoneAt = 0;
      queuedBlob = null;
      portfolioOk = true;
      return;
    }
    // Resolve the shared Supabase client then kick off the initial pull
    var getClient = window.getSupabaseClient;
    if (!getClient) { warnOnce('no-client', 'getSupabaseClient not found'); return; }
    getClient().then(function (c) {
      sb = c;
      pull();
    }).catch(function (err) {
      warnOnce('client', 'getSupabaseClient failed: ' + (err && err.message || err));
    });
  }

  // ---- init ------------------------------------------------------------------
  function init() {
    var CFG = window.SUPABASE_CFG;
    var enabled = CFG && CFG.url && CFG.anonKey;
    if (!enabled) return;   // no config baked -> dormant; localStorage-only
    if (!window.MDXAuth || !window.MDXAuth.onChange) return;  // theme.js not ready

    window.MDXAuth.onChange(function (u, evt) {
      if (!u && evt === 'SDK_FAILED') return;  // SDK blocked (GFW/outage) -> stay dormant
      onAuthUser(u);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

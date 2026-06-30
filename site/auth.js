/* auth.js — OPTIONAL cloud sync for the Watchlist, via Supabase.

   Sign-in itself is owned by the GLOBAL account system in theme.js (the gear's
   account section + the frosted-glass modal): Google / email+password, one
   shared client with a permanent cookie session. This file is now just the
   watchlist's CLOUD-SYNC consumer of that session:
     • It reacts to the shared session via window.MDXAuth.onChange (no own SDK,
       no own client, no second storage — sessions can't diverge).
     • The "Sign in to sync" button opens the global modal (window.MDXAuth.open).
     • When signed in it pulls the user's cloud doc, WL.merge()s it into local,
       and pushes the merged blob back — same blob shape, so signing in is a
       non-destructive merge and signing out leaves a valid local list.

   Strictly additive + fail-soft: with no baked config (window.SUPABASE_CFG blank)
   or with theme.js absent, the auth UI hides and the page stays local-only —
   zero third-party calls for an anonymous visitor. Security: the anon key is
   PUBLIC by design; per-user isolation is enforced by RLS against the user's JWT
   (templates/watchlist_supabase.sql). The service_role key NEVER ships here. */
(function () {
  'use strict';

  var CFG = window.SUPABASE_CFG;
  var ENABLED = CFG && CFG.url && CFG.anonKey;
  var TABLE = 'watchlists';

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

  var sb = null, user = null, pushTimer = null;

  function el(id) { return document.getElementById(id); }
  function setPill(state) {
    var p = el('wl_syncpill'); if (!p) return;
    var map = { synced: L('synced'), syncing: L('syncing'), local: L('local'),
                offline: L('offline'), finishing: L('finishing') };
    p.textContent = map[state] || '';
    p.className = 'wl-pill wl-pill-' + (state === 'finishing' ? 'syncing' : state);
  }

  // The shared client lives in theme.js (cookie session, self-hosted SDK). We
  // never create our own — that would split the session across two stores.
  function getClient() {
    if (window.getSupabaseClient) return window.getSupabaseClient();
    return Promise.reject(new Error('no-shared-client'));
  }
  function ensureClientThenPull() {
    getClient().then(function (c) { sb = c; return pull(); })
      .catch(function () { setPill('offline'); });
  }

  // ---- sync ---------------------------------------------------------------
  function pull() {
    if (!user || !sb) return Promise.resolve();
    setPill('syncing');
    return sb.from(TABLE).select('doc').eq('user_id', user.id).maybeSingle()
      .then(function (res) {
        if (res.error) throw res.error;
        if (res.data && res.data.doc) window.WL.merge(res.data.doc);
        return push();
      }).then(function () { setPill('synced'); })
      .catch(function () { setPill('offline'); });
  }
  function push(blob) {
    if (!user || !sb) return Promise.resolve();
    blob = blob || window.WL.getBlob();
    setPill('syncing');
    return sb.from(TABLE).upsert(
      { user_id: user.id, doc: blob, updated_at: new Date().toISOString() },
      { onConflict: 'user_id' }
    ).then(function (res) {
      if (res.error) throw res.error;
      setPill('synced');
    }).catch(function () { setPill('offline'); });
  }
  window.WLCloud = {
    push: function () {
      if (!user) return;
      clearTimeout(pushTimer);
      pushTimer = setTimeout(function () { push(); }, 600);
    }
  };

  // ---- ui -----------------------------------------------------------------
  function showAccount(email) {
    if (el('wl_signin')) el('wl_signin').style.display = 'none';
    if (el('wl_authbox')) el('wl_authbox').style.display = 'none';
    if (el('wl_account')) el('wl_account').style.display = 'flex';
    if (el('wl_who')) el('wl_who').textContent = L('hello') + ' ' + email;
  }
  function showSignedOut() {
    if (el('wl_account')) el('wl_account').style.display = 'none';
    if (el('wl_authbox')) el('wl_authbox').style.display = 'none';
    if (el('wl_signin')) el('wl_signin').style.display = 'inline-block';
    setPill('local');
  }

  // ---- shared-session reactions ------------------------------------------
  function onAuthUser(u) {
    user = u || null;
    if (user) { showAccount(user.email || ''); ensureClientThenPull(); }
    else { sb = null; showSignedOut(); }
  }

  function wire() {
    var si = el('wl_signin');
    if (si) si.addEventListener('click', function () {
      if (window.MDXAuth && window.MDXAuth.open) window.MDXAuth.open('signin');
    });
    var so = el('wl_signout');
    if (so) so.addEventListener('click', function () {
      if (window.MDXAuth && window.MDXAuth.signOut) window.MDXAuth.signOut();
      else showSignedOut();   // (UI also updates via the mdx-auth event)
    });
    document.addEventListener('visibilitychange', function () { if (!document.hidden && user) pull(); });
    document.addEventListener('langchange', relabel);
  }

  function relabel() {
    if (el('wl_signin')) el('wl_signin').textContent = L('signin');
    if (el('wl_signout')) el('wl_signout').textContent = L('signout');
    if (user) showAccount(user.email || ''); else setPill('local');
  }

  function init() {
    var box = el('wl_auth');
    // Local-only unless BOTH the config is baked AND the shared client exists.
    if (!ENABLED || !window.MDXAuth || !window.MDXAuth.onChange) {
      if (box) box.style.display = 'none';
      return;
    }
    if (!box) return;            // nothing to wire if the panel isn't on the page
    box.style.display = 'flex';
    relabel(); wire(); showSignedOut();
    // the legacy magic-link box is retired — sign-in goes through the global modal
    if (el('wl_authbox')) el('wl_authbox').style.display = 'none';
    if (window.MDXAuth.hasSession && window.MDXAuth.hasSession()) setPill('finishing');
    window.MDXAuth.onChange(function (u, evt) {
      // SDK blocked/failed to load (e.g. behind the GFW): settle to offline, not a
      // forever "Finishing sign-in…" pill.
      if (!u && evt === 'SDK_FAILED') { setPill('offline'); return; }
      onAuthUser(u);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

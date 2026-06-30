/* auth.js — OPTIONAL cloud sync for the Watchlist, via Supabase (magic-link).

   Strictly additive and fail-soft:
   • If window.SUPABASE_CFG is absent/blank, the auth UI is hidden and the page
     stays a pure local-only watchlist — no SDK, no network call.
   • The Supabase JS SDK is loaded LAZILY — only on a sign-in click, when a magic
     link returns with tokens in the URL, or when a prior session is detected. An
     anonymous visitor makes ZERO third-party requests.
   • Sign-in is passwordless MAGIC LINK (free-tier-friendly: the default email
     can't be customized to a code, so we email a link the user clicks). On the
     free tier the project owner must add this site's origin to
     Supabase → Authentication → URL Configuration → Redirect URLs.
   • Security: the anon/publishable key is PUBLIC by design — per-user isolation
     is enforced by Row-Level-Security against the user's JWT (see
     templates/watchlist_supabase.sql). The service_role key NEVER ships here.

   Plugs into the store seam exposed by watchlist.js (window.WL): pull the cloud
   doc, WL.merge() it into local, push the merged blob back — same blob shape, so
   signing in is a non-destructive merge and signing out leaves a valid local list. */
(function () {
  'use strict';

  var CFG = window.SUPABASE_CFG;
  var ENABLED = CFG && CFG.url && CFG.anonKey;
  // Self-hosted (was a public JS CDN, blocked in mainland China). Vendored at
  // templates/supabase.js -> site/supabase.js; same dir as auth.js. Pinned 2.x.
  var SDK_URL = 'supabase.js';
  var TABLE = 'watchlists';

  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  var T = {
    en: { signin: 'Sign in to sync', email: 'you@email.com', sendlink: 'Email me a sign-in link',
          signout: 'Sign out', synced: 'Synced', syncing: 'Syncing…', local: 'Local only',
          offline: 'Offline — local only', finishing: 'Finishing sign-in…',
          sent: '📧 Check your email and click the link to finish signing in.',
          bad: 'Sign-in failed — try again', sdkfail: 'Could not load the sign-in library (offline?)',
          linkbad: 'That sign-in link expired or was already used — try again.', hello: 'Signed in as' },
    zh: { signin: '登录以同步', email: 'you@email.com', sendlink: '把登录链接发到我的邮箱',
          signout: '退出登录', synced: '已同步', syncing: '同步中…', local: '仅本地',
          offline: '离线——仅本地', finishing: '正在完成登录…',
          sent: '📧 请查收邮箱并点击链接以完成登录。',
          bad: '登录失败——请重试', sdkfail: '无法加载登录组件（离线？）',
          linkbad: '该登录链接已过期或已被使用——请重试。', hello: '已登录：' }
  };
  function L(k) { return (T[lang()] || T.en)[k]; }

  var sb = null, sdkLoading = null, user = null, pushTimer = null;

  function el(id) { return document.getElementById(id); }
  function setPill(state) {
    var p = el('wl_syncpill'); if (!p) return;
    var map = { synced: L('synced'), syncing: L('syncing'), local: L('local'),
                offline: L('offline'), finishing: L('finishing') };
    p.textContent = map[state] || '';
    p.className = 'wl-pill wl-pill-' + (state === 'finishing' ? 'syncing' : state);
  }

  function loadSDK() {
    if (window.supabase && window.supabase.createClient) return Promise.resolve();
    if (sdkLoading) return sdkLoading;
    sdkLoading = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = SDK_URL; s.async = true;
      s.onload = resolve; s.onerror = function () { reject(new Error('sdk')); };
      document.head.appendChild(s);
    });
    return sdkLoading;
  }
  function client() {
    if (sb) return sb;
    sb = window.supabase.createClient(CFG.url, CFG.anonKey, {
      // implicit flow returns tokens in the URL hash — robust for magic links
      // opened in a different browser/device than the request (no PKCE verifier
      // needed). detectSessionInUrl auto-consumes + strips the hash on return.
      auth: { persistSession: true, autoRefreshToken: true,
              detectSessionInUrl: true, flowType: 'implicit' }
    });
    sb.auth.onAuthStateChange(function (evt, session) { onAuth(evt, session); });
    return sb;
  }

  // a returning signed-in user has an sb-*-auth-token in localStorage
  function hasPersistedSession() {
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && /^sb-.*-auth-token$/.test(k)) return true;
      }
    } catch (e) {}
    return false;
  }
  // did we just land back from a magic link? (tokens or an auth error in the hash)
  function isAuthReturn() {
    var h = location.hash || '';
    return h.indexOf('access_token=') >= 0 || h.indexOf('error=') >= 0 ||
           h.indexOf('error_description=') >= 0;
  }

  // ---- sync ---------------------------------------------------------------
  function pull() {
    if (!user) return Promise.resolve();
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

  // ---- auth state ---------------------------------------------------------
  // supabase-js fires INITIAL_SESSION (null) right after createClient — that must
  // NOT reset the UI (it would clobber the email form mid-sign-in). Only an
  // explicit SIGNED_OUT returns to the signed-out view.
  function onAuth(evt, session) {
    user = session && session.user ? session.user : null;
    if (user) { showAccount(user.email || ''); pull(); return; }
    if (evt === 'SIGNED_OUT') { showSignedOut(); return; }
    setPill('local');   // INITIAL_SESSION/etc with no user: clear transient pill, leave UI
  }
  function showAccount(email) {
    el('wl_signin').style.display = 'none';
    el('wl_authbox').style.display = 'none';
    el('wl_account').style.display = 'flex';
    el('wl_who').textContent = L('hello') + ' ' + email;
  }
  function showSignedOut() {
    el('wl_account').style.display = 'none';
    el('wl_authbox').style.display = 'none';
    el('wl_signin').style.display = 'inline-block';
    setPill('local');
  }

  // ---- wiring -------------------------------------------------------------
  function wire() {
    el('wl_signin').addEventListener('click', function () {
      setPill('syncing');
      loadSDK().then(function () {
        client();
        el('wl_signin').style.display = 'none';
        el('wl_authbox').style.display = 'flex';
        el('wl_email').style.display = '';
        el('wl_send').style.display = '';
        el('wl_sent').style.display = 'none';
        el('wl_email').focus();
        setPill('local');
      }).catch(function () { setPill('offline'); toast(L('sdkfail'), true); });
    });

    el('wl_send').addEventListener('click', function () {
      var email = el('wl_email').value.trim();
      if (!email) return;
      el('wl_send').disabled = true;
      sb.auth.signInWithOtp({
        email: email,
        options: { shouldCreateUser: true, emailRedirectTo: location.origin + location.pathname }
      }).then(function (res) {
        el('wl_send').disabled = false;
        if (res.error) { toast(L('bad'), true); return; }
        // magic-link sent: collapse the form to a "check your email" message
        el('wl_email').style.display = 'none';
        el('wl_send').style.display = 'none';
        var m = el('wl_sent'); m.textContent = L('sent'); m.style.display = '';
      });
    });

    el('wl_signout').addEventListener('click', function () {
      if (sb) sb.auth.signOut();
      showSignedOut();
    });

    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && user) pull();
    });
    document.addEventListener('langchange', relabel);
  }

  function relabel() {
    el('wl_signin').textContent = L('signin');
    el('wl_send').textContent = L('sendlink');
    el('wl_signout').textContent = L('signout');
    el('wl_email').placeholder = L('email');
    var m = el('wl_sent'); if (m && m.style.display !== 'none') m.textContent = L('sent');
    if (user) showAccount(user.email || ''); else setPill('local');
  }

  function toast(msg, bad) {
    var t = el('wl_toast'); if (!t) return;
    t.textContent = msg; t.className = 'wl-toast' + (bad ? ' bad' : '') + ' show';
    setTimeout(function () { t.className = 'wl-toast'; }, 3000);
  }

  function init() {
    var box = el('wl_auth');
    if (!ENABLED) { if (box) box.style.display = 'none'; return; }
    box.style.display = 'flex';
    relabel(); wire(); setPill('local');
    // a magic link just returned, or a prior session exists -> load the SDK so
    // detectSessionInUrl consumes the hash / the session restores
    if (isAuthReturn()) {
      setPill('finishing');
      loadSDK().then(function () {
        client();
        if (location.hash.indexOf('error') >= 0) toast(L('linkbad'), true);
      }).catch(function () { setPill('offline'); });
    } else if (hasPersistedSession()) {
      loadSDK().then(function () { client().auth.getSession(); })
        .catch(function () { setPill('offline'); });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

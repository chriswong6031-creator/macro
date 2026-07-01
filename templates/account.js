/* account.js — the Mastermind user profile / account panel.

   ONE self-contained component shared verbatim by both properties, in two modes:
   • STANDALONE (app.mastermind-x.com) — mounts a 👤 avatar button into the nav
     controls (.mm-nav-ctrls) that opens a frosted-glass pop-up. Identity via the
     same-origin shared SSO cookie.
   • EMBED (macro.mastermind-x.com) — renders INTO the existing settings-gear (⚙)
     Account section (.settings-acct, built by theme.js), replacing its "coming
     soon" placeholder. Identity via the user's Supabase JS bearer token; the app
     API is called cross-origin. theme.js hands us the container via
     window.MMAccount.embed(el); we also self-detect it.

   It injects its own CSS (matched to the design tokens --panel/--line/--link/
   --popover-shadow, with vector-palette fallbacks) and talks ONLY to the
   privileged broker at <MM_API>/api/account/*. No secrets ever live here.

   Config (all optional — the rest is self-discovered from the API):
     window.MM_API        base URL of the app API ('' => same origin). macro sets this.
     window.SUPABASE_CFG  {url, anonKey} for Supabase JS. macro/app both learn it
                          from the API too, so no HTML hardcoding is required.

   Preference sync: when signed in, theme + language changes are saved to the
   account (Supabase user_metadata) and re-applied on load, so a user's look
   follows them to any device/site. Hooks the EXISTING theme.js toggles via the
   `themechange` / `langchange` document events. */
(function () {
  'use strict';

  var API = (window.MM_API || '').replace(/\/+$/, '');   // '' => same-origin (app)
  var SUPA = normSupa(window.SUPABASE_CFG);              // may be filled in from the API
  var SDK_URL = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js';

  var state = { acct: null, loaded: false };
  var _sb = null, _sbLoad = null, _hydrating = false, _prefTimer = null, _mounted = false, _macro = false;
  var _mode = null;                 // 'standalone' | 'embed'
  var _root = null;                 // the element whose innerHTML we render into
  var trigger = null, scrim = null, panel = null;

  // -------------------------------------------------------------- helpers ----
  function normSupa(c) {
    if (!c) return null;
    var url = c.url, key = c.anonKey || c.anon_key;
    return (url && key) ? { url: url, anonKey: key } : null;
  }
  function lang() { return document.documentElement.getAttribute('data-lang') || 'en'; }
  function curTheme() { return document.documentElement.getAttribute('data-theme') || 'dark'; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function E(id) { return document.getElementById(id); }
  function initials(a) {
    var s = (a.name || a.email || '').trim();
    if (!s) return '';
    if (s.indexOf('@') > -1) s = s.split('@')[0];
    var p = s.replace(/[._+-]+/g, ' ').split(/\s+/).filter(Boolean);
    var r = (p[0] || '').charAt(0) + (p.length > 1 ? (p[p.length - 1] || '').charAt(0) : '');
    return (r || s.charAt(0)).toUpperCase();
  }
  function fmtDate(s) {
    if (!s) return '—';
    try { return new Date(s).toLocaleDateString(lang() === 'zh' ? 'zh-CN' : undefined,
      { year: 'numeric', month: 'short', day: 'numeric' }); } catch (e) { return '—'; }
  }
  var PERSON = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" ' +
    'stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-3.6 3.6-6 8-6s8 2.4 8 6"/></svg>';

  // -------------------------------------------------------------- i18n -------
  var STR = {
    account: ['Account', '账户'], signed_in: ['Signed in', '已登录'],
    upgrade: ['Upgrade to Pro', '升级到 Pro'], soon: ['Coming soon', '即将推出'],
    pro_blurb: ['Deeper research, live alerts & more.', '更深度研究、实时提醒等。'],
    email: ['Email', '邮箱'], no_email: ['No email on file', '尚未绑定邮箱'],
    add_email: ['Add email', '添加邮箱'], change: ['Change', '修改'],
    save: ['Save', '保存'], cancel: ['Cancel', '取消'], saving: ['Saving…', '保存中…'],
    unverified: ['unverified', '未验证'],
    password: ['Password', '密码'], set_pw: ['Set / change password', '设置 / 修改密码'],
    new_pw: ['New password', '新密码'], confirm_pw: ['Confirm password', '确认密码'],
    prefs_synced: ['Theme & language are saved to your account — they follow you wherever you sign in.',
      '主题与语言已保存到账户，登录任意设备都会自动同步。'],
    notifications: ['Notifications', '通知'],
    notif_email: ['Email alerts', '邮件提醒'], notif_product: ['Product updates', '产品更新'],
    security: ['Security', '安全'], login_method: ['Login method', '登录方式'],
    member_since: ['Member since', '注册于'], last_signin: ['Last sign-in', '上次登录'],
    user_id: ['User ID', '用户 ID'], copy: ['Copy', '复制'], copied: ['Copied', '已复制'],
    sign_out: ['Sign out', '退出登录'], sign_out_all: ['Sign out everywhere', '退出所有设备'],
    danger: ['Danger zone', '危险区域'], delete_acct: ['Delete account', '删除账户'],
    delete_warn: ['This permanently deletes your account and data.', '这将永久删除你的账户及数据。'],
    delete_type: ['Type your email to confirm', '输入邮箱以确认'],
    delete_go: ['Delete permanently', '永久删除'],
    signin_title: ['Sign in to Mastermind', '登录 Mastermind'],
    signin_sub: ['Sync your watchlist, preferences & account across every Mastermind site.',
      '在所有 Mastermind 站点同步你的自选、偏好与账户。'],
    email_ph: ['you@email.com', 'you@email.com'],
    send_link: ['Email me a sign-in link', '把登录链接发到邮箱'],
    sending: ['Sending…', '发送中…'],
    link_sent: ['📧 Check your email and click the link to finish signing in.',
      '📧 请查收邮件并点击链接完成登录。'],
    pw_ok: ['Password updated.', '密码已更新。'],
    email_ok: ['Email updated.', '邮箱已更新。'],
    email_confirm: ['Confirmation link sent to your new email.', '确认链接已发送到你的新邮箱。'],
    pw_mismatch: ['Passwords don’t match.', '两次输入的密码不一致。'],
    pw_short: ['Use at least 8 characters.', '至少 8 个字符。'],
    err: ['Something went wrong — try again.', '出错了，请重试。'],
    guest_title: ['Access session', '访问会话'],
    guest_sub: ['You’re in with the site access password. Sign in with an account to manage email, password & preferences.',
      '你正通过站点访问密码登录。使用账户登录以管理邮箱、密码与偏好。'],
    close: ['Close', '关闭'], loading: ['Loading…', '加载中…']
  };
  function T(k) { var v = STR[k] || ['', '']; return v[lang() === 'zh' ? 1 : 0]; }

  // ---------------------------------------------------- Supabase JS ----------
  function hasPersisted() {
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (k && /^sb-.*-auth-token$/.test(k)) return true;
      }
    } catch (e) {}
    return false;
  }
  function loadSDK() {
    if (window.supabase && window.supabase.createClient) return Promise.resolve();
    if (_sbLoad) return _sbLoad;
    _sbLoad = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = SDK_URL; s.async = true;
      s.onload = res; s.onerror = function () { rej(new Error('sdk')); };
      document.head.appendChild(s);
    });
    return _sbLoad;
  }
  function sbClient() {
    if (_sb) return Promise.resolve(_sb);
    if (!SUPA) return Promise.resolve(null);
    return loadSDK().then(function () {
      _sb = window.supabase.createClient(SUPA.url, SUPA.anonKey, {
        auth: { persistSession: true, autoRefreshToken: true,
          detectSessionInUrl: true, flowType: 'implicit' }
      });
      return _sb;
    });
  }
  function getToken() {
    // macro rides the shared cookie (credentials:include) — never load the SDK there
    // (jsdelivr is GFW-blocked; the app broker reads the cookie directly).
    if (_macro || !SUPA || !hasPersisted()) return Promise.resolve(null);
    return sbClient().then(function (sb) { return sb ? sb.auth.getSession() : null; })
      .then(function (r) { var s = r && r.data && r.data.session; return s ? s.access_token : null; })
      .catch(function () { return null; });
  }

  // ------------------------------------------------------------- API ---------
  function api(path, opts) {
    opts = opts || {};
    return getToken().then(function (token) {
      var headers = {};
      if (opts.body) headers['Content-Type'] = 'application/json';
      if (token) headers['Authorization'] = 'Bearer ' + token;
      return fetch(API + path, {
        method: opts.method || 'GET', headers: headers, credentials: 'include',
        body: opts.body ? JSON.stringify(opts.body) : undefined
      });
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        return { ok: r.ok, status: r.status, data: j };
      });
    }).catch(function () { return { ok: false, status: 0, data: {} }; });
  }
  function load() {
    return api('/api/account').then(function (res) {
      var a = res.data || {};
      if (!SUPA && a.supabase) SUPA = normSupa(a.supabase);
      if (!a.authenticated && SUPA && hasPersisted()) {
        return api('/api/account').then(function (r2) { finishLoad(r2.data || a); });
      }
      finishLoad(a);
    });
  }
  function finishLoad(a) {
    state.acct = a; state.loaded = true;
    applyPrefs(a);
    if (_mode === 'standalone') paintTrigger();
    render();
  }

  // --------------------------------------------------- preference sync -------
  function applyPrefs(a) {
    if (!a || !a.authenticated || !a.prefs) return;
    _hydrating = true;
    try {
      if (a.prefs.theme && (a.prefs.theme === 'light' || a.prefs.theme === 'dark') &&
          a.prefs.theme !== curTheme() && window.setTheme) window.setTheme(a.prefs.theme);
      var lg = document.documentElement.getAttribute('data-lang') || 'en';
      if (a.prefs.lang && (a.prefs.lang === 'en' || a.prefs.lang === 'zh') &&
          a.prefs.lang !== lg && window.setLang) window.setLang(a.prefs.lang);
    } catch (e) {}
    _hydrating = false;
  }
  function persistPref(key, val) {
    if (_hydrating || !state.acct || !state.acct.authenticated) return;
    clearTimeout(_prefTimer);
    _prefTimer = setTimeout(function () {
      var body = {}; body[key] = val;
      api('/api/account/prefs', { method: 'POST', body: body });
    }, 500);
  }

  // -------------------------------------------------- section builders -------
  function planCardHTML() {
    return '<div class="mmacc-pro-card">' +
        '<div class="mmacc-pro-top"><span class="mmacc-pro-name">✨ Pro</span>' +
          '<span class="mmacc-soon">' + esc(T('soon')) + '</span></div>' +
        '<div class="mmacc-pro-blurb">' + esc(T('pro_blurb')) + '</div>' +
        '<button class="mmacc-btn mmacc-pro-btn" disabled>' + esc(T('upgrade')) + '</button>' +
      '</div>';
  }
  function emailGroupHTML(a) {
    var line = a.email
      ? esc(a.email) + (a.email_confirmed ? '' : ' <span class="mmacc-warn">· ' + esc(T('unverified')) + '</span>')
      : '<span class="mmacc-muted">' + esc(T('no_email')) + '</span>';
    return '<div class="mmacc-group">' +
        '<div class="mmacc-glabel">' + esc(T('email')) + '</div>' +
        '<div class="mmacc-line">' +
          '<span class="mmacc-line-v">' + line + '</span>' +
          '<button class="mmacc-mini" data-act="edit-email">' + esc(a.email ? T('change') : T('add_email')) + '</button>' +
        '</div>' +
        '<div class="mmacc-field" id="mmacc-email-field">' +
          '<input type="email" id="mmacc-email-in" class="mmacc-input" autocomplete="email" ' +
            'placeholder="' + esc(T('email_ph')) + '" value="' + esc(a.email || '') + '">' +
          '<div class="mmacc-msg" id="mmacc-email-msg"></div>' +
          '<div class="mmacc-btnrow">' +
            '<button class="mmacc-btn mmacc-ghost" data-act="cancel-email">' + esc(T('cancel')) + '</button>' +
            '<button class="mmacc-btn mmacc-primary" data-act="save-email">' + esc(T('save')) + '</button>' +
          '</div>' +
        '</div>' +
      '</div>';
  }
  function pwGroupHTML() {
    return '<div class="mmacc-group">' +
        '<div class="mmacc-glabel">' + esc(T('password')) + '</div>' +
        '<div class="mmacc-line">' +
          '<span class="mmacc-line-v mmacc-muted">••••••••</span>' +
          '<button class="mmacc-mini" data-act="edit-pw">' + esc(T('set_pw')) + '</button>' +
        '</div>' +
        '<div class="mmacc-field" id="mmacc-pw-field">' +
          '<input type="password" id="mmacc-pw-in" class="mmacc-input" autocomplete="new-password" ' +
            'placeholder="' + esc(T('new_pw')) + '">' +
          '<input type="password" id="mmacc-pw2-in" class="mmacc-input" autocomplete="new-password" ' +
            'placeholder="' + esc(T('confirm_pw')) + '">' +
          '<div class="mmacc-msg" id="mmacc-pw-msg"></div>' +
          '<div class="mmacc-btnrow">' +
            '<button class="mmacc-btn mmacc-ghost" data-act="cancel-pw">' + esc(T('cancel')) + '</button>' +
            '<button class="mmacc-btn mmacc-primary" data-act="save-pw">' + esc(T('save')) + '</button>' +
          '</div>' +
        '</div>' +
        '<div class="mmacc-hint">' + esc(T('prefs_synced')) + '</div>' +
      '</div>';
  }
  function notifRow(label) {
    return '<div class="mmacc-row mmacc-row-toggle"><span class="mmacc-k">' + esc(label) + '</span>' +
      '<span class="mmacc-switch" aria-disabled="true"></span></div>';
  }
  function notifGroupHTML() {
    return '<div class="mmacc-group">' +
        '<div class="mmacc-glabel">' + esc(T('notifications')) +
          ' <span class="mmacc-soon mmacc-soon-sm">' + esc(T('soon')) + '</span></div>' +
        notifRow(T('notif_email')) + notifRow(T('notif_product')) +
      '</div>';
  }
  function infoRow(k, v) {
    return '<div class="mmacc-row"><span class="mmacc-k">' + esc(k) + '</span>' +
      '<span class="mmacc-v">' + v + '</span></div>';
  }
  function securityGroupHTML(a) {
    var chips = (a.providers || []).map(function (p) {
      return '<span class="mmacc-chip">' + esc(p) + '</span>'; }).join('');
    return '<div class="mmacc-group">' +
        '<div class="mmacc-glabel">' + esc(T('security')) + '</div>' +
        infoRow(T('login_method'), '<span class="mmacc-chips">' + chips + '</span>') +
        infoRow(T('member_since'), esc(fmtDate(a.created_at))) +
        infoRow(T('last_signin'), esc(fmtDate(a.last_sign_in_at))) +
        '<div class="mmacc-row"><span class="mmacc-k">' + esc(T('user_id')) + '</span>' +
          '<button class="mmacc-mini" data-act="copy-id">' + esc(T('copy')) + '</button></div>' +
        '<div class="mmacc-btnrow mmacc-btnrow-wide">' +
          '<button class="mmacc-btn mmacc-ghost" data-act="signout">' + esc(T('sign_out')) + '</button>' +
          '<button class="mmacc-btn mmacc-ghost" data-act="signout-all">' + esc(T('sign_out_all')) + '</button>' +
        '</div>' +
      '</div>';
  }
  function dangerGroupHTML() {
    return '<div class="mmacc-group mmacc-danger">' +
        '<div class="mmacc-glabel mmacc-glabel-danger">' + esc(T('danger')) + '</div>' +
        '<div class="mmacc-line">' +
          '<span class="mmacc-line-v mmacc-muted">' + esc(T('delete_warn')) + '</span>' +
          '<button class="mmacc-mini mmacc-mini-danger" data-act="show-delete">' + esc(T('delete_acct')) + '</button>' +
        '</div>' +
        '<div class="mmacc-field" id="mmacc-del-field">' +
          '<input type="email" id="mmacc-del-in" class="mmacc-input" placeholder="' + esc(T('delete_type')) + '">' +
          '<div class="mmacc-msg" id="mmacc-del-msg"></div>' +
          '<div class="mmacc-btnrow">' +
            '<button class="mmacc-btn mmacc-ghost" data-act="cancel-delete">' + esc(T('cancel')) + '</button>' +
            '<button class="mmacc-btn mmacc-danger-btn" data-act="do-delete">' + esc(T('delete_go')) + '</button>' +
          '</div>' +
        '</div>' +
      '</div>';
  }
  function signinFormHTML() {
    return '<div class="mmacc-group mmacc-signin">' +
        '<div class="mmacc-signin-title">' + esc(T('signin_title')) + '</div>' +
        '<div class="mmacc-signin-sub">' + esc(T('signin_sub')) + '</div>' +
        '<input type="email" id="mmacc-signin-in" class="mmacc-input" autocomplete="email" ' +
          'placeholder="' + esc(T('email_ph')) + '">' +
        '<div class="mmacc-msg" id="mmacc-signin-msg"></div>' +
        '<button class="mmacc-btn mmacc-primary mmacc-block" data-act="send-link">' + esc(T('send_link')) + '</button>' +
      '</div>';
  }
  function guestNoteHTML() {
    return '<div class="mmacc-group">' +
        '<div class="mmacc-signin-title">' + esc(T('guest_title')) + '</div>' +
        '<div class="mmacc-signin-sub">' + esc(T('guest_sub')) + '</div>' +
      '</div>';
  }
  function bodySignedIn(a) {
    return planCardHTML() + emailGroupHTML(a) + pwGroupHTML() + notifGroupHTML() +
      securityGroupHTML(a) + dangerGroupHTML();
  }
  function bodySignedOut(a) {
    if (_macro) return guestNoteHTML();   // macro: sign-in lives in the ⚙ gear, not here
    return (SUPA || (a && a.supabase)) ? signinFormHTML() : guestNoteHTML();
  }

  // ------------------------------------------------- mode-specific shells ----
  function profileStripHTML(a, withClose) {
    var provLabel = a.provider_label || (a.providers || []).join(' · ') || 'Email';
    return '<div class="mmacc-head">' +
        '<div class="mmacc-ava">' + (initials(a) ? esc(initials(a)) : PERSON) + '</div>' +
        '<div class="mmacc-idbox">' +
          '<div class="mmacc-name">' + esc(a.name || a.email || T('account')) + '</div>' +
          '<div class="mmacc-sub">' + esc(T('signed_in')) + ' · ' + esc(provLabel) + '</div>' +
        '</div>' +
        '<span class="mmacc-plan-pill">' + esc(a.plan_label || 'Free') + '</span>' +
        (withClose ? '<button class="mmacc-x" data-act="close" aria-label="' + esc(T('close')) + '">✕</button>' : '') +
      '</div>';
  }
  function panelHTML(a) {
    a = a || {};
    if (!state.loaded) return '<div class="mmacc-body"><div class="mmacc-loading">' + esc(T('loading')) + '</div></div>';
    if (a.authenticated) {
      return profileStripHTML(a, true) + '<div class="mmacc-body">' + bodySignedIn(a) + '</div>';
    }
    return '<div class="mmacc-head mmacc-head-out">' +
        '<div class="mmacc-idbox"><div class="mmacc-name">' + esc(T('account')) + '</div></div>' +
        '<button class="mmacc-x" data-act="close" aria-label="' + esc(T('close')) + '">✕</button>' +
      '</div><div class="mmacc-body">' + bodySignedOut(a) + '</div>';
  }
  function embedHTML(a) {
    a = a || {};
    if (!state.loaded) return '<div class="mmacc-loading">' + esc(T('loading')) + '</div>';
    if (a.authenticated) return '<div class="mmacc-embed">' + profileStripHTML(a, false) + bodySignedIn(a) + '</div>';
    return '<div class="mmacc-embed">' + bodySignedOut(a) + '</div>';
  }
  function render() {
    if (!_root) return;
    _root.innerHTML = (_mode === 'embed') ? embedHTML(state.acct) : panelHTML(state.acct);
  }

  // ------------------------------------------------------------- actions -----
  function showField(id, show) { var f = E(id); if (f) f.classList.toggle('open', show !== false); }
  function setMsg(id, text, kind) {
    var m = E(id); if (!m) return;
    m.textContent = text || '';
    m.className = 'mmacc-msg' + (text ? ' show' : '') + (kind ? ' ' + kind : '');
  }
  function busy(btn, on, label) {
    if (!btn) return;
    if (on) { btn._t = btn.textContent; btn.disabled = true; if (label) btn.textContent = label; }
    else { btn.disabled = false; if (btn._t != null) btn.textContent = btn._t; }
  }
  function onSaveEmail(btn) {
    var v = (E('mmacc-email-in').value || '').trim();
    setMsg('mmacc-email-msg', ''); busy(btn, true, T('saving'));
    api('/api/account/email', { method: 'POST', body: { email: v } }).then(function (r) {
      busy(btn, false);
      if (r.ok && r.data.ok) {
        setMsg('mmacc-email-msg', r.data.confirmation_required ? T('email_confirm') : T('email_ok'), 'ok');
        setTimeout(load, 500);
      } else setMsg('mmacc-email-msg', r.data.error || T('err'), 'bad');
    });
  }
  function onSavePw(btn) {
    var p1 = E('mmacc-pw-in').value || '', p2 = E('mmacc-pw2-in').value || '';
    if (p1.length < 8) { setMsg('mmacc-pw-msg', T('pw_short'), 'bad'); return; }
    if (p1 !== p2) { setMsg('mmacc-pw-msg', T('pw_mismatch'), 'bad'); return; }
    setMsg('mmacc-pw-msg', ''); busy(btn, true, T('saving'));
    api('/api/account/password', { method: 'POST', body: { password: p1 } }).then(function (r) {
      busy(btn, false);
      if (r.ok && r.data.ok) {
        setMsg('mmacc-pw-msg', T('pw_ok'), 'ok');
        E('mmacc-pw-in').value = ''; E('mmacc-pw2-in').value = '';
        setTimeout(function () { showField('mmacc-pw-field', false); }, 1100);
      } else setMsg('mmacc-pw-msg', r.data.error || T('err'), 'bad');
    });
  }
  function onDelete(btn) {
    var v = (E('mmacc-del-in').value || '').trim();
    setMsg('mmacc-del-msg', ''); busy(btn, true, T('saving'));
    api('/api/account/delete', { method: 'POST', body: { confirm: v } }).then(function (r) {
      busy(btn, false);
      if (r.ok && r.data.ok) doSignOut();
      else setMsg('mmacc-del-msg', r.data.error || T('err'), 'bad');
    });
  }
  function onSendLink(btn) {
    var v = (E('mmacc-signin-in').value || '').trim();
    if (!v) return;
    setMsg('mmacc-signin-msg', ''); busy(btn, true, T('sending'));
    sbClient().then(function (sb) {
      if (!sb) throw new Error('no-supabase');
      return sb.auth.signInWithOtp({ email: v,
        options: { shouldCreateUser: true, emailRedirectTo: location.href.split('#')[0] } });
    }).then(function (res) {
      busy(btn, false);
      if (res && res.error) setMsg('mmacc-signin-msg', res.error.message || T('err'), 'bad');
      else setMsg('mmacc-signin-msg', T('link_sent'), 'ok');
    }).catch(function () { busy(btn, false); setMsg('mmacc-signin-msg', T('err'), 'bad'); });
  }
  function copyId() {
    var id = state.acct && state.acct.id; if (!id) return;
    var done = function () {
      var b = _root && _root.querySelector('[data-act="copy-id"]'); if (!b) return;
      var t = b.textContent; b.textContent = T('copied');
      setTimeout(function () { b.textContent = t; }, 1400);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(id).then(done, done); else done();
  }
  function clearSharedCookie() {
    try {
      var parts = location.hostname.split('.');
      var base = parts.length >= 2 ? parts.slice(-2).join('.') : location.hostname;
      document.cookie.split(';').forEach(function (c) {
        var name = c.split('=')[0].trim();
        if (/^sb-.*-auth-token(\.\d+)?$/.test(name)) {
          document.cookie = name + '=; Max-Age=0; path=/; domain=.' + base;
          document.cookie = name + '=; Max-Age=0; path=/';
        }
      });
    } catch (e) {}
  }
  function doSignOut() {
    if (_macro && window.MDXAuth && window.MDXAuth.signOut) {
      try { window.MDXAuth.signOut(); } catch (e) {}   // let the gear's auth own sign-out
      close(); return;
    }
    var fin = function () {
      clearSharedCookie();
      if (API === '') location.href = '/logout';   // app: also clears mm_session
      else location.reload();                        // macro: back to signed-out
    };
    if (SUPA && hasPersisted()) sbClient().then(function (sb) { return sb.auth.signOut(); }).then(fin, fin);
    else fin();
  }
  function doSignOutAll() {
    api('/api/account/signout-everywhere', { method: 'POST' }).then(doSignOut, doSignOut);
  }
  function onClick(e) {
    var b = e.target.closest('[data-act]'); if (!b) return;
    switch (b.getAttribute('data-act')) {
      case 'close': return close();
      case 'edit-email': showField('mmacc-email-field'); var ei = E('mmacc-email-in'); if (ei) ei.focus(); return;
      case 'cancel-email': showField('mmacc-email-field', false); setMsg('mmacc-email-msg', ''); return;
      case 'save-email': return onSaveEmail(b);
      case 'edit-pw': showField('mmacc-pw-field'); var pi = E('mmacc-pw-in'); if (pi) pi.focus(); return;
      case 'cancel-pw': showField('mmacc-pw-field', false); setMsg('mmacc-pw-msg', ''); return;
      case 'save-pw': return onSavePw(b);
      case 'copy-id': return copyId();
      case 'signout': return doSignOut();
      case 'signout-all': return doSignOutAll();
      case 'show-delete': showField('mmacc-del-field'); var di = E('mmacc-del-in'); if (di) di.focus(); return;
      case 'cancel-delete': showField('mmacc-del-field', false); setMsg('mmacc-del-msg', ''); return;
      case 'do-delete': return onDelete(b);
      case 'send-link': return onSendLink(b);
    }
  }

  // ----------------------------------------------------- standalone panel ----
  function paintTrigger() {
    if (!trigger) return;
    var a = state.acct || {};
    if (a.authenticated) {
      var ini = initials(a);
      trigger.innerHTML = ini ? esc(ini) : PERSON;
      trigger.classList.toggle('mmacc-trigger-ini', !!ini);
      trigger.classList.add('mmacc-trigger-on');
      trigger.setAttribute('aria-label', a.email || T('account'));
    } else {
      trigger.innerHTML = PERSON;
      trigger.classList.remove('mmacc-trigger-ini', 'mmacc-trigger-on');
      trigger.setAttribute('aria-label', T('account'));
    }
  }
  function open() {
    if (!state.loaded) { render(); load(); } else render();
    scrim.classList.add('open'); panel.classList.add('open');
    document.addEventListener('keydown', onEsc);
  }
  function close() {
    if (_mode !== 'standalone') return;
    scrim.classList.remove('open'); panel.classList.remove('open');
    document.removeEventListener('keydown', onEsc);
  }
  function onEsc(e) { if (e.key === 'Escape') close(); }

  // ----------------------------------------------------------- mounting ------
  function injectCSS() {
    if (document.getElementById('mmacc-css')) return;
    var st = document.createElement('style'); st.id = 'mmacc-css'; st.textContent = CSS;
    document.head.appendChild(st);
  }
  function wirePrefSync() {
    document.addEventListener('themechange', function (e) { persistPref('theme', e.detail || curTheme()); });
    document.addEventListener('langchange', function (e) {
      persistPref('lang', e.detail || lang());
      render();
    });
  }
  function mountStandalone() {
    if (_mounted) return;
    var host = document.querySelector('.mm-nav-ctrls, .nav-ctrls');
    if (!host) return;
    _mounted = true; _mode = 'standalone';
    injectCSS();
    trigger = document.createElement('button');
    trigger.type = 'button'; trigger.id = 'mmacc-trigger'; trigger.className = 'mmacc-trigger';
    trigger.setAttribute('aria-label', T('account')); trigger.innerHTML = PERSON;
    trigger.addEventListener('click', function (e) { e.stopPropagation(); panel.classList.contains('open') ? close() : open(); });
    host.appendChild(trigger);
    scrim = document.createElement('div'); scrim.className = 'mmacc-scrim';
    scrim.addEventListener('click', close);
    panel = document.createElement('div'); panel.className = 'mmacc';
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', T('account'));
    panel.addEventListener('click', onClick);
    document.body.appendChild(scrim); document.body.appendChild(panel);
    _root = panel;
    wirePrefSync();
    var warm = function () { load(); };
    if (window.requestIdleCallback) requestIdleCallback(warm, { timeout: 1500 }); else setTimeout(warm, 400);
  }
  function mountEmbed(el) {
    if (_mounted || !el) return;
    _mounted = true; _mode = 'embed'; _root = el;
    injectCSS();
    el.className = (el.className || '') + ' mmacc-embed-host';
    el.removeAttribute('style');
    el.addEventListener('click', onClick);
    // this section is live now — drop the "coming soon" badge theme.js rendered
    var soon = document.querySelector('#settings-modal .settings-sec-t .settings-soon');
    if (soon) soon.style.display = 'none';
    // widen the settings card into a scrollable sheet for the fuller account content
    if (!document.getElementById('mmacc-embed-css')) {
      var st = document.createElement('style'); st.id = 'mmacc-embed-css';
      st.textContent = '.settings-overlay .settings-card{max-height:90vh;overflow-y:auto;overscroll-behavior:contain}';
      document.head.appendChild(st);
    }
    render();
    wirePrefSync();
    // defer the (cross-origin) profile fetch until the gear is first opened
    var gear = document.getElementById('settings-open');
    var warm = function () { if (!state.loaded) load(); };
    if (gear) gear.addEventListener('click', warm);
    if (window.requestIdleCallback) requestIdleCallback(warm, { timeout: 4000 }); else setTimeout(warm, 1200);
  }
  // MACRO (macro.mastermind-x.com): the settings gear owns sign-in/out; we add a hidden
  // management panel opened from its signed-in row. Identity rides the shared cookie —
  // credentials:include on the cross-origin call to the app broker — so NO Supabase SDK
  // (jsdelivr) is ever loaded here (it's GFW-blocked). theme.js calls window.MMAccount.open().
  function mountMacro() {
    if (_mounted) return;
    _mounted = true; _mode = 'standalone'; _macro = true;
    injectCSS();
    scrim = document.createElement('div'); scrim.className = 'mmacc-scrim';
    scrim.addEventListener('click', close);
    panel = document.createElement('div'); panel.className = 'mmacc';
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', T('account'));
    panel.addEventListener('click', onClick);
    document.body.appendChild(scrim); document.body.appendChild(panel);
    _root = panel;
    wirePrefSync();
  }
  window.MMAccount = {
    embed: function (el) { try { mountEmbed(el); } catch (e) {} },   // legacy (old settings modal)
    open: function () { try { if (!_mounted) mountMacro(); open(); } catch (e) {} }
  };

  function boot() {
    if (_mounted) return;
    // MACRO: theme.js defines window.MDXAuth + the .nav-settings gear. Hook management there.
    if (window.MDXAuth || document.querySelector('.nav-settings, .settings-pop')) { mountMacro(); return; }
    // APP: standalone avatar in the nav controls.
    if (document.querySelector('.mm-nav-ctrls, .nav-ctrls')) { mountStandalone(); return; }
    setTimeout(function () {
      if (!_mounted && document.querySelector('.nav-ctrls, .mm-nav-ctrls')) mountStandalone();
    }, 3000);
  }

  // --------------------------------------------------------------- CSS -------
  var CSS =
  '.mmacc-trigger{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;padding:0;border-radius:50%;' +
    'border:1px solid var(--line,var(--grid));background:var(--panel2,var(--card));color:var(--muted,var(--ink-3));cursor:pointer;' +
    'font:600 12px/1 Inter,system-ui,sans-serif;flex:none;transition:border-color .16s,color .16s,transform .16s,box-shadow .16s;-webkit-tap-highlight-color:transparent}' +
  '.mmacc-trigger:hover{color:var(--text,var(--ink));border-color:var(--link,var(--blue));transform:translateY(-1px)}' +
  '.mmacc-trigger-on{color:#fff;border-color:transparent;background:linear-gradient(135deg,#3b82f6,#7c5cff);box-shadow:0 2px 10px -3px rgba(90,80,255,.6)}' +
  '.mmacc-trigger-ini{letter-spacing:.3px}' +
  '.mmacc-scrim{position:fixed;inset:0;z-index:100050;background:transparent;opacity:0;visibility:hidden;pointer-events:none;transition:opacity .22s ease,visibility 0s linear .22s}' +
  '.mmacc-scrim.open{opacity:1;visibility:visible;pointer-events:auto;background:color-mix(in srgb,var(--bg,#0f1115) 34%,transparent);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);transition:opacity .22s ease}' +
  '.mmacc{position:fixed;top:58px;right:14px;z-index:100060;width:min(374px,calc(100vw - 20px));max-height:min(84vh,720px);display:flex;flex-direction:column;overflow:hidden;color:var(--text,var(--ink));' +
    'background:var(--panel,var(--card));border:1px solid var(--line,var(--grid));border-radius:18px;box-shadow:var(--popover-shadow,0 18px 50px rgba(0,0,0,.5));' +
    'transform-origin:top right;transform:translateY(-8px) scale(.965);opacity:0;visibility:hidden;pointer-events:none;transition:opacity .19s ease,transform .24s cubic-bezier(.18,.9,.32,1.12),visibility 0s linear .24s}' +
  '.mmacc.open{opacity:1;transform:none;visibility:visible;pointer-events:auto;transition:opacity .19s ease,transform .24s cubic-bezier(.18,.9,.32,1.12)}' +
  '@supports ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){.mmacc{background:color-mix(in srgb,var(--panel,var(--card)) 80%,transparent);-webkit-backdrop-filter:blur(26px) saturate(1.5);backdrop-filter:blur(26px) saturate(1.5)}}' +
  '.mmacc-head{display:flex;align-items:center;gap:11px;padding:15px 15px 13px;border-bottom:1px solid var(--line,var(--grid));flex:none}' +
  '.mmacc-head-out{align-items:flex-start}' +
  '.mmacc-ava{width:40px;height:40px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font:700 15px/1 Inter,system-ui,sans-serif;color:#fff;letter-spacing:.3px;background:linear-gradient(135deg,#3b82f6,#7c5cff);box-shadow:0 3px 12px -4px rgba(90,80,255,.7)}' +
  '.mmacc-idbox{flex:1;min-width:0}' +
  '.mmacc-name{font-size:14px;font-weight:700;color:var(--text,var(--ink));white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
  '.mmacc-sub{font-size:11.5px;color:var(--muted,var(--ink-3));margin-top:2px;line-height:1.35}' +
  '.mmacc-plan-pill{flex:none;font-size:10.5px;font-weight:700;color:var(--muted,var(--ink-3));background:var(--panel2,var(--card));border:1px solid var(--line,var(--grid));border-radius:999px;padding:3px 9px;text-transform:uppercase;letter-spacing:.4px}' +
  '.mmacc-x{flex:none;width:26px;height:26px;border-radius:8px;border:1px solid var(--line,var(--grid));background:var(--panel2,var(--card));color:var(--muted,var(--ink-3));font-size:12px;cursor:pointer;line-height:1;transition:color .15s,border-color .15s}' +
  '.mmacc-x:hover{color:var(--text,var(--ink));border-color:var(--link,var(--blue))}' +
  '.mmacc-body{padding:13px 15px 16px;overflow-y:auto;overscroll-behavior:contain}' +
  '.mmacc-embed-host{background:transparent!important;border:0!important;padding:0!important;display:block!important}' +
  '.mmacc-embed .mmacc-head{padding:2px 0 12px}' +
  '.mmacc-group{padding:13px 0;border-top:1px solid color-mix(in srgb,var(--line,var(--grid)) 60%,transparent)}' +
  '.mmacc-body>.mmacc-group:first-child,.mmacc-embed>.mmacc-pro-card:first-child+.mmacc-group,.mmacc-embed>.mmacc-group:first-child{border-top:0}' +
  '.mmacc-body>.mmacc-pro-card:first-child,.mmacc-embed>.mmacc-pro-card:first-child{margin-top:4px}' +
  '.mmacc-glabel{font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:.7px;color:var(--muted,var(--ink-3));margin-bottom:9px;display:flex;align-items:center;gap:7px}' +
  '.mmacc-glabel-danger{color:color-mix(in srgb,var(--down,#e06464) 78%,var(--muted,#888))}' +
  '.mmacc-line{display:flex;align-items:center;gap:10px}' +
  '.mmacc-line-v{flex:1;min-width:0;font-size:13px;color:var(--text,var(--ink));word-break:break-word}' +
  '.mmacc-muted{color:var(--muted,var(--ink-3))}' +
  '.mmacc-warn{color:var(--warn,#e0a030);font-size:11px;font-weight:600}' +
  '.mmacc-mini{flex:none;font-size:12px;font-weight:600;color:var(--link,var(--blue));background:transparent;border:1px solid var(--line,var(--grid));border-radius:8px;padding:5px 11px;cursor:pointer;transition:border-color .15s,background .15s;font-family:inherit}' +
  '.mmacc-mini:hover{border-color:var(--link,var(--blue));background:color-mix(in srgb,var(--link,var(--blue)) 10%,transparent)}' +
  '.mmacc-mini-danger{color:var(--down,#e06464)}' +
  '.mmacc-mini-danger:hover{border-color:var(--down,#e06464);background:color-mix(in srgb,var(--down,#e06464) 10%,transparent)}' +
  '.mmacc-field{max-height:0;overflow:hidden;opacity:0;transition:max-height .28s ease,opacity .2s ease,margin .2s ease}' +
  '.mmacc-field.open{max-height:280px;opacity:1;margin-top:10px}' +
  '.mmacc-input{width:100%;box-sizing:border-box;padding:9px 12px;margin-bottom:8px;border-radius:10px;border:1px solid var(--line,var(--grid));background:var(--panel2,var(--card));color:var(--text,var(--ink));font-size:13.5px;outline:none;font-family:inherit;transition:border-color .15s,box-shadow .15s}' +
  '.mmacc-input:focus{border-color:var(--link,var(--blue));box-shadow:0 0 0 3px color-mix(in srgb,var(--link,var(--blue)) 22%,transparent)}' +
  '.mmacc-btnrow{display:flex;gap:8px;justify-content:flex-end}' +
  '.mmacc-btnrow-wide{margin-top:12px}' +
  '.mmacc-btn{font:600 12.5px/1 Inter,system-ui,sans-serif;padding:8px 14px;border-radius:9px;cursor:pointer;border:1px solid var(--line,var(--grid));transition:all .15s;flex:none}' +
  '.mmacc-btn:disabled{opacity:.55;cursor:default}' +
  '.mmacc-primary{background:var(--link,var(--blue));border-color:var(--link,var(--blue));color:#fff}' +
  '.mmacc-primary:hover:not(:disabled){filter:brightness(1.08);transform:translateY(-1px)}' +
  '.mmacc-ghost{background:var(--panel2,var(--card));color:var(--text,var(--ink))}' +
  '.mmacc-ghost:hover:not(:disabled){border-color:var(--link,var(--blue))}' +
  '.mmacc-block{width:100%;text-align:center;margin-top:4px}' +
  '.mmacc-danger-btn{background:var(--down,#e06464);border-color:var(--down,#e06464);color:#fff}' +
  '.mmacc-danger-btn:hover:not(:disabled){filter:brightness(1.06)}' +
  '.mmacc-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:5px 0;font-size:12.5px}' +
  '.mmacc-k{color:var(--muted,var(--ink-3))}' +
  '.mmacc-v{color:var(--text,var(--ink));text-align:right;word-break:break-word}' +
  '.mmacc-chips{display:inline-flex;flex-wrap:wrap;gap:5px;justify-content:flex-end}' +
  '.mmacc-chip{font-size:10.5px;font-weight:600;color:var(--text,var(--ink));background:var(--panel2,var(--card));border:1px solid var(--line,var(--grid));border-radius:6px;padding:2px 7px;text-transform:capitalize}' +
  '.mmacc-row-toggle{padding:7px 0}' +
  '.mmacc-switch{width:34px;height:20px;border-radius:999px;background:var(--panel2,var(--card));border:1px solid var(--line,var(--grid));position:relative;flex:none;opacity:.6}' +
  '.mmacc-switch::after{content:"";position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;background:var(--muted,var(--ink-3))}' +
  '.mmacc-soon{font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;color:var(--warn,#e0a030);background:color-mix(in srgb,var(--warn,#e0a030) 14%,transparent);border-radius:999px;padding:2px 7px}' +
  '.mmacc-soon-sm{padding:1px 6px;font-size:9px}' +
  '.mmacc-pro-card{background:linear-gradient(135deg,color-mix(in srgb,#7c5cff 12%,var(--panel2,var(--card))),color-mix(in srgb,#3b82f6 10%,var(--panel2,var(--card))));border:1px solid color-mix(in srgb,#7c5cff 30%,var(--line,var(--grid)));border-radius:13px;padding:12px 13px;margin-bottom:4px}' +
  '.mmacc-pro-top{display:flex;align-items:center;justify-content:space-between;gap:8px}' +
  '.mmacc-pro-name{font-size:14px;font-weight:800;color:var(--text,var(--ink))}' +
  '.mmacc-pro-blurb{font-size:11.5px;color:var(--muted,var(--ink-3));margin:6px 0 10px}' +
  '.mmacc-pro-btn{width:100%;background:linear-gradient(135deg,#3b82f6,#7c5cff);border:0;color:#fff}' +
  '.mmacc-pro-btn:disabled{opacity:.9;cursor:default;filter:saturate(.65) brightness(.94)}' +
  '.mmacc-hint{font-size:11px;color:var(--muted,var(--ink-3));line-height:1.5;margin-top:9px}' +
  '.mmacc-msg{font-size:11.5px;line-height:1.4;max-height:0;overflow:hidden;transition:max-height .2s ease;margin:0}' +
  '.mmacc-msg.show{max-height:60px;margin:0 0 8px}' +
  '.mmacc-msg.ok{color:var(--ok,#3da564)}' +
  '.mmacc-msg.bad{color:var(--down,#e06464)}' +
  '.mmacc-signin-title{font-size:15px;font-weight:800;color:var(--text,var(--ink))}' +
  '.mmacc-signin-sub{font-size:12px;color:var(--muted,var(--ink-3));line-height:1.5;margin:5px 0 12px}' +
  '.mmacc-loading{padding:26px;text-align:center;color:var(--muted,var(--ink-3))}' +
  '@media (max-width:560px){.mmacc{top:auto;bottom:0;left:0;right:0;width:100%;max-width:none;max-height:88vh;border-radius:18px 18px 0 0;transform-origin:bottom center;transform:translateY(16px)}.mmacc.open{transform:none}.mmacc-scrim.open{background:color-mix(in srgb,var(--bg,#0f1115) 52%,transparent)}}' +
  '@media (prefers-reduced-motion:reduce){.mmacc{transition:opacity .15s ease,visibility 0s linear .15s;transform:none}.mmacc.open{transform:none;transition:opacity .15s ease}.mmacc-field{transition:none}}';

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

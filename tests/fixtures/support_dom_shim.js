/* tests/fixtures/support_dom_shim.js — the smallest DOM /support.html's page JS touches.
 *
 * Used by tests/test_support_page_js.py to run the page's own inline <script>, unmodified,
 * under node. The point is the BEHAVIOUR a text assertion cannot reach: that firing submit
 * twice while a request is in flight produces exactly one POST, that an anonymous visitor
 * never touches the Supabase SDK, and that the success copy follows the API's `mail` flag.
 *
 * Deliberately NOT a browser. Two things this shim cannot model, and both are verified in
 * a real browser instead (see the PR's review-fixes section):
 *   - implicit submission (Enter in a text field) and keyboard activation of the focused
 *     button, which is what `btn.disabled` stops;
 *   - CSS, so `display` toggles are asserted through the html[data-mail] attribute the
 *     stylesheet keys on rather than through computed style.
 *
 * Unknown `#id` lookups mint a stub element on demand, so renaming a field does not
 * silently return null here and turn a real failure into a passing no-op.
 */
'use strict';

function el(tag) {
  var e = {
    tagName: tag,
    _attrs: {},
    _classes: {},
    _on: {},
    _cell: null,
    value: '',
    textContent: '',
    innerHTML: '',
    disabled: false,
    readOnly: false,
    options: null,
    getAttribute: function (k) { return (k in this._attrs) ? this._attrs[k] : null; },
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
    removeAttribute: function (k) { delete this._attrs[k]; },
    hasAttribute: function (k) { return k in this._attrs; },
    addEventListener: function (t, fn) { (this._on[t] = this._on[t] || []).push(fn); },
    fire: function (t, ev) {
      ev = ev || {};
      ev.type = t;
      ev.defaultPrevented = false;
      ev.preventDefault = function () { ev.defaultPrevented = true; };
      var fns = (this._on[t] || []).slice();
      for (var i = 0; i < fns.length; i++) fns[i](ev);
      return ev;
    },
    focus: function () { DOM.focused = this; },
    reset: function () { this.value = ''; DOM.wasReset = true; },
    closest: function () { return this._cell || (this._cell = el('div')); },
    querySelector: function (sel) {
      if (!this.options) return null;
      var m = /option\[value="([^"]*)"\]/.exec(sel);
      if (!m) return null;
      for (var i = 0; i < this.options.length; i++) {
        if (this.options[i].value === m[1]) return this.options[i];
      }
      return null;
    }
  };
  e.classList = {
    add: function (c) { e._classes[c] = true; },
    remove: function (c) { delete e._classes[c]; },
    toggle: function (c, on) { if (on) { e._classes[c] = true; } else { delete e._classes[c]; } },
    contains: function (c) { return !!e._classes[c]; }
  };
  return e;
}

function option(value, en, zh) {
  var o = el('option');
  o.value = value;
  o._attrs['data-en'] = en;
  o._attrs['data-zh'] = zh;
  return o;
}

var DOM = {
  nodes: {},
  fetches: [],
  authCalls: 0,
  hasSessionCalls: 0,
  focused: null,
  wasReset: false
};

/* Every option is plain JSON so the Python side can pass it through node -e / a temp file.
 *
 * opts:
 *   lang        'en' | 'zh'
 *   hp          honeypot element id, e.g. '#s-lx'   (read off the rendered page)
 *   auth        omitted         -> window.MDXAuth absent entirely
 *               {hasSession, token, clientDelayMs, clientHangs}
 *   fetchDelay  ms before each fetch settles (0 = a macrotask)
 *   status      HTTP status to answer with (default 200)
 *   fail_all    true -> every fetch REJECTS, the way an abort or a dead network does
 *   ticket_id / mail / sent   the fields of the 200 body
 */
function replyFor(opts) {
  if (opts.fail_all) return { status: 0 };
  var status = opts.status || 200;
  if (status !== 200) return { status: status, body: {} };
  var body = { ok: true, ticket_id: opts.ticket_id || '7f3a2b91-1111-4000-8000-000000000001' };
  if (opts.mail !== undefined && opts.mail !== null) body.mail = opts.mail;
  if (opts.sent) body.sent = opts.sent;
  return { status: 200, body: body };
}

function install(opts) {
  opts = opts || {};

  var html = el('html');
  html.setAttribute('data-auth', 'out');
  html.setAttribute('data-form', 'idle');
  if (opts.lang) html.setAttribute('data-lang', opts.lang);

  var topic = el('select');
  topic.value = 'billing';
  topic.options = [
    option('billing', 'Billing & payments', '账单与付款'),
    option('account', 'Account & sign-in', '账户与登录'),
    option('bug', 'Something is broken', '有功能坏了'),
    option('data', 'Question about the data', '数据相关问题'),
    option('feature', 'Idea for something new', '功能建议'),
    option('other', 'Something else', '其他')
  ];

  var subject = el('input');
  subject._attrs['data-ph-en'] = 'One line — what is this about?';
  subject._attrs['data-ph-zh'] = '一句话说明这是什么问题';
  var message = el('textarea');
  message._attrs['data-ph-en'] = 'Write it however you like.';
  message._attrs['data-ph-zh'] = '怎么写都可以。';

  DOM.nodes = {
    '#s-topic': topic,
    '#tk-form': el('form'),
    '#s-send': el('button'),
    '#s-email': el('input'),
    '#s-subject': subject,
    '#s-message': message,
    '#s-again': el('button')
  };
  DOM.nodes[opts.hp || '#s-lx'] = el('input');
  DOM.doneAddr = [el('b'), el('b'), el('b'), el('b')];

  var document_ = {
    _on: {},
    documentElement: html,
    addEventListener: function (t, fn) { (this._on[t] = this._on[t] || []).push(fn); },
    fire: function (t) {
      var fns = (this._on[t] || []).slice();
      for (var i = 0; i < fns.length; i++) fns[i]({ type: t });
    },
    querySelector: function (s) {
      if (s in DOM.nodes) return DOM.nodes[s];
      if (s.charAt(0) === '#') { DOM.nodes[s] = el('div'); return DOM.nodes[s]; }
      return null;
    },
    querySelectorAll: function (s) {
      if (s === '[data-ph-en]') return [subject, message];
      if (s === '.done-addr') return DOM.doneAddr;
      if (s === '.f.bad') return [];
      return [];
    }
  };

  var window_ = { MM_BRAIN_CFG: { api: '' }, AbortController: global.AbortController };

  if (opts.auth) {
    window_.MDXAuth = {
      hasSession: function () { DOM.hasSessionCalls++; return !!opts.auth.hasSession; },
      onChange: function () { /* the page paints auth from this; not under test here */ },
      client: function () {
        DOM.authCalls++;
        if (opts.auth.clientHangs) return new Promise(function () { /* never settles */ });
        var sb = {
          auth: {
            getSession: function () {
              return new Promise(function (res) {
                setTimeout(function () {
                  res({ data: { session: opts.auth.token ? { access_token: opts.auth.token } : null } });
                }, opts.auth.clientDelayMs || 0);
              });
            }
          }
        };
        return Promise.resolve(sb);
      }
    };
  }

  window_.fetch = function (url, init) {
    DOM.fetches.push({ url: url, init: init, headers: (init && init.headers) || {},
                       body: init && init.body ? JSON.parse(init.body) : null,
                       /* when the request was ISSUED — the auth cap is measured on this,
                          not on when the assertion happens to run */
                       t: Date.now() });
    var reply = replyFor(opts);
    return new Promise(function (res, rej) {
      var aborted = false;
      if (init && init.signal) {
        init.signal.addEventListener('abort', function () {
          aborted = true;
          var e = new Error('aborted'); e.name = 'AbortError'; rej(e);
        });
      }
      setTimeout(function () {
        if (aborted) return;
        /* status 0 stands for "the network failed" — a DNS miss, a reset, or the page's
           own AbortController firing. All of them reject, which is the path the error
           bar has to be reachable from. */
        if (!reply.status) { rej(new Error('network')); return; }
        res({ status: reply.status, ok: reply.status >= 200 && reply.status < 300,
              json: function () { return Promise.resolve(reply.body); } });
      }, opts.fetchDelay || 0);
    });
  };

  global.document = document_;
  global.window = window_;
  global.fetch = window_.fetch;
  global.MDXAuth = window_.MDXAuth;
  global.localStorage = { getItem: function () { return null; }, setItem: function () {} };
  DOM.document = document_;
  DOM.window = window_;
  DOM.html = html;
  return DOM;
}

module.exports = { install: install, DOM: DOM, el: el };

/* Mastermind Terminal overlay — first-party full-screen bridge.
   Maintained separately and bundled onto the emitted theme.js by site_assets.py;
   it can still load standalone in local/custom builds. The Terminal app remains
   isolated at app.mastermind-x.com; this code owns only the dashboard-side portal,
   loading state, animation, history and accessibility. */
(function () {
  'use strict';

  if (window.MDXTerminalOverlay) return;

  var state = {
    overlay: null,
    frame: null,
    loader: null,
    toast: null,
    slow: null,
    newTab: null,
    open: false,
    ready: false,
    booted: false,
    path: '',
    symbol: '',
    targetOrigin: 'https://app.mastermind-x.com',
    directUrl: 'https://app.mastermind-x.com/terminal',
    lastConfig: null,
    historyToken: '',
    historyActive: false,
    recyclePending: false,
    closeTimer: 0,
    readyTimer: 0,
    toastTimer: 0,
    slowTimer: 0,
    loadingStartedAt: 0,
    scrollY: 0,
    activeElement: null,
    bodyStyle: null,
    locked: []
  };
  var MIN_LOADER_MS = 1800;

  function isDashboardHost() {
    var h = location.hostname || '';
    if (h === 'mastermind-x.com' || h === 'www.mastermind-x.com') return true;
    return (h === 'localhost' || h === '127.0.0.1') && /^https?:$/.test(location.protocol);
  }

  function bilingual(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + zh + '</span>';
  }

  function injectStyles() {
    if (document.getElementById('mm-terminal-overlay-css')) return;
    var style = document.createElement('style');
    style.id = 'mm-terminal-overlay-css';
    style.textContent = [
      'html.mm-terminal-lock,html.mm-terminal-lock body{overscroll-behavior:none}',
      '#mm-terminal-overlay{--mmto-x:50vw;--mmto-y:18vh;position:fixed;inset:0;z-index:2147483000;',
        'visibility:hidden;pointer-events:none;isolation:isolate;overflow:hidden;background:#05070b;',
        'font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#f4f7ff}',
      '#mm-terminal-overlay.is-open,#mm-terminal-overlay.is-closing{visibility:visible;pointer-events:auto}',
      '#mm-terminal-overlay::before{content:"";position:absolute;inset:-25%;z-index:0;pointer-events:none;',
        'background:radial-gradient(circle at var(--mmto-x) var(--mmto-y),rgba(77,130,255,.23),transparent 23%),',
        'radial-gradient(circle at 82% 16%,rgba(129,92,246,.15),transparent 25%),#05070b;',
        'opacity:0;transform:scale(1.04);transition:opacity .32s ease,transform .62s cubic-bezier(.16,1,.3,1)}',
      '#mm-terminal-overlay.is-open::before{opacity:1;transform:none}',
      '#mm-terminal-overlay.is-closing::before{opacity:0;transform:scale(1.025)}',
      '.mmto-stage{position:absolute;inset:0;z-index:1;overflow:hidden;background:#07090e;',
        'opacity:0;transform:translate3d(0,14px,0) scale(.978);transform-origin:var(--mmto-x) var(--mmto-y);',
        'transition:opacity .22s ease,transform .56s cubic-bezier(.16,1,.3,1),clip-path .62s cubic-bezier(.16,1,.3,1)}',
      '#mm-terminal-overlay.is-open .mmto-stage{opacity:1;transform:none}',
      '#mm-terminal-overlay.is-closing .mmto-stage{opacity:0;transform:translate3d(0,8px,0) scale(.986)}',
      '@supports (clip-path:circle(10px at 10px 10px)){',
        '.mmto-stage{clip-path:circle(0 at var(--mmto-x) var(--mmto-y))}',
        '#mm-terminal-overlay.is-open .mmto-stage{clip-path:circle(150vmax at var(--mmto-x) var(--mmto-y))}',
        '#mm-terminal-overlay.is-closing .mmto-stage{clip-path:circle(0 at var(--mmto-x) var(--mmto-y))}',
      '}',
      '.mmto-frame{position:absolute;inset:0;width:100%;height:100%;border:0;background:#07090e;',
        'opacity:0;transform:scale(1.008);transition:opacity .28s ease,transform .48s cubic-bezier(.16,1,.3,1)}',
      '#mm-terminal-overlay.is-ready .mmto-frame{opacity:1;transform:none}',
      '.mmto-loader{position:absolute;inset:0;z-index:3;display:grid;place-items:center;overflow:hidden;',
        'background:linear-gradient(145deg,#080b12 0%,#05070b 58%,#080b14 100%);',
        'opacity:1;visibility:visible;transition:opacity .26s ease,visibility 0s linear .26s}',
      '#mm-terminal-overlay.is-ready .mmto-loader{opacity:0;visibility:hidden;pointer-events:none}',
      '.mmto-loader::before{content:"";position:absolute;width:min(70vw,760px);aspect-ratio:1;border-radius:50%;',
        'background:radial-gradient(circle,rgba(77,130,255,.13),rgba(77,130,255,.035) 36%,transparent 68%);',
        'animation:mmtoAura 3s ease-in-out infinite}',
      '.mmto-loader-inner{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;',
        'width:min(86vw,420px);text-align:center}',
      '.mmto-mark{position:relative;width:76px;height:76px;display:grid;place-items:center;margin-bottom:22px}',
      '.mmto-mark::before,.mmto-mark::after{content:"";position:absolute;border-radius:50%;border:1px solid rgba(112,153,255,.35)}',
      '.mmto-mark::before{inset:-9px;animation:mmtoOrbit 2.6s linear infinite}',
      '.mmto-mark::after{inset:4px;border-color:rgba(151,118,255,.38);animation:mmtoOrbit 2s linear infinite reverse}',
      '.mmto-mark svg{width:54px;height:54px;filter:drop-shadow(0 0 18px rgba(77,130,255,.42))}',
      '.mmto-loader-title{font-size:14px;font-weight:750;letter-spacing:.16em}',
      '.mmto-loader-sub{margin-top:9px;font-size:12px;color:#929bb0;letter-spacing:.02em}',
      '.mmto-progress{position:relative;width:min(72vw,280px);height:2px;margin-top:25px;overflow:hidden;',
        'border-radius:999px;background:rgba(143,158,190,.13)}',
      '.mmto-progress::after{content:"";position:absolute;inset:0;width:42%;border-radius:inherit;',
        'background:linear-gradient(90deg,transparent,#4d82ff 34%,#9a7cff 76%,transparent);',
        'animation:mmtoProgress 1.25s cubic-bezier(.4,0,.2,1) infinite}',
      '.mmto-slow{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;',
        'max-height:0;margin-top:0;opacity:0;overflow:hidden;transition:max-height .24s ease,margin .24s ease,opacity .24s ease}',
      '#mm-terminal-overlay.is-slow .mmto-slow{max-height:64px;margin-top:20px;opacity:1}',
      '.mmto-loader button,.mmto-loader a{height:36px;display:inline-flex;align-items:center;justify-content:center;',
        'padding:0 14px;border:1px solid rgba(119,143,196,.3);border-radius:10px;background:rgba(18,23,35,.78);',
        'color:#dbe4f7;text-decoration:none;font:650 12px/1 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;',
        'cursor:pointer;transition:background .16s ease,border-color .16s ease,transform .16s ease}',
      '.mmto-loader button:hover,.mmto-loader a:hover{background:rgba(38,50,76,.82);border-color:rgba(77,130,255,.55);transform:translateY(-1px)}',
      '.mmto-toast{position:absolute;z-index:5;top:max(14px,env(safe-area-inset-top));left:50%;',
        'display:flex;align-items:center;gap:9px;max-width:calc(100vw - 28px);padding:9px 13px 9px 10px;',
        'border:1px solid rgba(119,143,196,.3);border-radius:12px;background:rgba(10,14,23,.84);',
        '-webkit-backdrop-filter:blur(16px) saturate(1.2);backdrop-filter:blur(16px) saturate(1.2);',
        'box-shadow:0 14px 40px rgba(0,0,0,.26),inset 0 1px rgba(255,255,255,.04);',
        'color:#dce5f7;font-size:12px;white-space:nowrap;opacity:0;transform:translate(-50%,-14px) scale(.98);',
        'pointer-events:none;transition:opacity .2s ease,transform .34s cubic-bezier(.16,1,.3,1)}',
      '.mmto-toast.show{opacity:1;transform:translate(-50%,0) scale(1)}',
      '.mmto-toast-icon{width:24px;height:24px;display:grid;place-items:center;flex:none;border-radius:7px;',
        'background:linear-gradient(145deg,rgba(77,130,255,.3),rgba(135,94,246,.2));color:#9db8ff}',
      '.mmto-toast-icon svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:2}',
      '.mmto-toast kbd{margin-left:4px;padding:3px 6px;border:1px solid rgba(150,167,202,.28);border-bottom-color:rgba(150,167,202,.45);',
        'border-radius:5px;background:rgba(255,255,255,.055);color:#fff;font:650 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace}',
      '@keyframes mmtoProgress{0%{transform:translateX(-125%)}100%{transform:translateX(340%)}}',
      '@keyframes mmtoOrbit{to{transform:rotate(360deg)}}',
      '@keyframes mmtoAura{0%,100%{transform:scale(.92);opacity:.72}50%{transform:scale(1.05);opacity:1}}',
      '@media(max-width:700px){',
        '.mmto-stage{transform:translate3d(0,18px,0) scale(.965)}',
        '.mmto-toast{top:max(8px,env(safe-area-inset-top));font-size:11.5px;padding-right:10px}',
        '.mmto-loader-title{font-size:13px}.mmto-loader-sub{max-width:290px;line-height:1.45}',
      '}',
      '@media(prefers-reduced-motion:reduce){',
        '#mm-terminal-overlay::before,.mmto-stage,.mmto-frame,.mmto-loader,.mmto-toast,.mmto-slow{transition:none!important}',
        '.mmto-loader::before,.mmto-mark::before,.mmto-mark::after,.mmto-progress::after{animation:none!important}',
        '.mmto-progress::after{width:100%;opacity:.65}',
      '}'
    ].join('');
    document.head.appendChild(style);
  }

  function buildOverlay() {
    if (state.overlay) return state.overlay;
    if (!document.body) return null;
    injectStyles();

    var root = document.createElement('div');
    root.id = 'mm-terminal-overlay';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', 'Mastermind Terminal');
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML =
      '<div class="mmto-stage">' +
        '<iframe class="mmto-frame" title="Mastermind Terminal" allow="clipboard-read; clipboard-write; fullscreen" referrerpolicy="strict-origin-when-cross-origin"></iframe>' +
        '<div class="mmto-loader" role="status" aria-live="polite">' +
          '<div class="mmto-loader-inner">' +
            '<div class="mmto-mark" aria-hidden="true">' +
              '<svg viewBox="0 0 64 64"><defs><linearGradient id="mmto-g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#76a0ff"/><stop offset="1" stop-color="#9b78ff"/></linearGradient></defs>' +
                '<path d="M32 5 55 18.5v27L32 59 9 45.5v-27L32 5Z" fill="none" stroke="url(#mmto-g)" stroke-width="2"/>' +
                '<path d="m10.5 19.5 15.3 8.8m12.4 7.2 15.3 8.8M32 6.5v17.2m0 16.6v17.2m21.5-38-15.3 8.8m-12.4 7.2-15.3 8.8" fill="none" stroke="url(#mmto-g)" stroke-width="2" stroke-linecap="round"/>' +
                '<circle cx="32" cy="32" r="7.2" fill="#0b1020" stroke="url(#mmto-g)" stroke-width="2.4"/>' +
              '</svg>' +
            '</div>' +
            '<div class="mmto-loader-title">MASTERMIND TERMINAL</div>' +
            '<div class="mmto-loader-sub">' + bilingual('Opening your live market workspace…', '正在打开实时市场工作台…') + '</div>' +
            '<div class="mmto-progress" aria-hidden="true"></div>' +
            '<div class="mmto-slow">' +
              '<button type="button" class="mmto-back">' + bilingual('Back to Dashboard', '返回仪表盘') + '</button>' +
              '<a class="mmto-newtab" href="https://app.mastermind-x.com/terminal" target="_blank" rel="noopener">' + bilingual('Open separately', '单独打开') + '</a>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="mmto-toast" role="status" aria-live="polite">' +
          '<span class="mmto-toast-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg></span>' +
          '<span class="mmto-toast-copy">' + bilingual('Press <kbd>Esc</kbd> to return to Dashboard', '按 <kbd>Esc</kbd> 返回仪表盘') + '</span>' +
        '</div>' +
      '</div>';
    document.body.appendChild(root);

    state.overlay = root;
    state.frame = root.querySelector('.mmto-frame');
    state.loader = root.querySelector('.mmto-loader');
    state.toast = root.querySelector('.mmto-toast');
    state.slow = root.querySelector('.mmto-slow');
    state.newTab = root.querySelector('.mmto-newtab');

    root.querySelector('.mmto-back').addEventListener('click', requestClose);
    state.frame.addEventListener('load', function () {
      // The child bridge can post "ready" just before the iframe load event.
      // Never let the later load event regress that settled state back to a
      // permanent loader; explicit cross-route symbol switches clear ready first.
      if (!state.booted || state.ready) return;
      root.classList.remove('is-ready', 'is-slow');
      root.classList.add('is-loading');
      startSlowTimer();
    });
    return root;
  }

  function setLaunchOrigin(trigger) {
    var x = window.innerWidth * 0.5;
    var y = Math.min(window.innerHeight * 0.22, 180);
    if (trigger && trigger.getBoundingClientRect) {
      var r = trigger.getBoundingClientRect();
      if (r.width || r.height) {
        x = r.left + r.width / 2;
        y = r.top + r.height / 2;
      }
    }
    state.overlay.style.setProperty('--mmto-x', Math.round(x) + 'px');
    state.overlay.style.setProperty('--mmto-y', Math.round(y) + 'px');
  }

  function lockDashboard() {
    state.scrollY = window.scrollY || window.pageYOffset || 0;
    state.activeElement = document.activeElement;
    state.bodyStyle = {
      position: document.body.style.position,
      top: document.body.style.top,
      left: document.body.style.left,
      right: document.body.style.right,
      width: document.body.style.width,
      overflow: document.body.style.overflow
    };
    document.documentElement.classList.add('mm-terminal-lock');
    document.body.style.position = 'fixed';
    document.body.style.top = (-state.scrollY) + 'px';
    document.body.style.left = '0';
    document.body.style.right = '0';
    document.body.style.width = '100%';
    document.body.style.overflow = 'hidden';

    state.locked = [];
    Array.prototype.forEach.call(document.body.children, function (el) {
      if (el === state.overlay || el.tagName === 'SCRIPT') return;
      state.locked.push({
        el: el,
        inert: !!el.inert,
        aria: el.getAttribute('aria-hidden')
      });
      try { el.inert = true; } catch (e) {}
      el.setAttribute('aria-hidden', 'true');
    });
  }

  function unlockDashboard() {
    if (!state.bodyStyle) return;
    state.locked.forEach(function (rec) {
      try { rec.el.inert = rec.inert; } catch (e) {}
      if (rec.aria == null) rec.el.removeAttribute('aria-hidden');
      else rec.el.setAttribute('aria-hidden', rec.aria);
    });
    state.locked = [];
    document.body.style.position = state.bodyStyle.position;
    document.body.style.top = state.bodyStyle.top;
    document.body.style.left = state.bodyStyle.left;
    document.body.style.right = state.bodyStyle.right;
    document.body.style.width = state.bodyStyle.width;
    document.body.style.overflow = state.bodyStyle.overflow;
    document.documentElement.classList.remove('mm-terminal-lock');
    window.scrollTo(0, state.scrollY);
    state.bodyStyle = null;
    if (state.activeElement && state.activeElement.focus) {
      try { state.activeElement.focus({ preventScroll: true }); } catch (e) { try { state.activeElement.focus(); } catch (ignore) {} }
    }
  }

  function showToast() {
    if (!state.toast) return;
    clearTimeout(state.toastTimer);
    state.toast.classList.remove('show');
    void state.toast.offsetWidth;
    state.toast.classList.add('show');
    state.toastTimer = setTimeout(function () {
      if (state.toast) state.toast.classList.remove('show');
    }, 4300);
  }

  function startSlowTimer() {
    clearTimeout(state.slowTimer);
    state.slowTimer = setTimeout(function () {
      if (!state.ready && state.overlay) state.overlay.classList.add('is-slow');
    }, 9000);
  }

  function beginLoading(root) {
    clearTimeout(state.readyTimer);
    state.readyTimer = 0;
    state.ready = false;
    state.loadingStartedAt = Date.now();
    root.classList.remove('is-ready', 'is-slow');
    root.classList.add('is-loading');
    startSlowTimer();
  }

  function finishReady(data) {
    state.ready = true;
    state.path = data && data.path ? data.path : state.path;
    if (data && data.symbol) state.symbol = data.symbol;
    clearTimeout(state.slowTimer);
    if (!state.overlay) return;
    state.overlay.classList.remove('is-loading', 'is-slow');
    state.overlay.classList.add('is-ready');
    if (state.open) {
      setTimeout(function () {
        try { state.frame.focus(); } catch (e) {}
      }, 180);
    }
  }

  function markReady(data) {
    var elapsed = state.loadingStartedAt ? Date.now() - state.loadingStartedAt : MIN_LOADER_MS;
    var wait = Math.max(0, MIN_LOADER_MS - elapsed);
    clearTimeout(state.readyTimer);
    if (wait) {
      state.readyTimer = setTimeout(function () {
        state.readyTimer = 0;
        finishReady(data);
      }, wait);
      return;
    }
    finishReady(data);
  }

  function shouldRecycleFrame() {
    var compact = false;
    try {
      compact = !!(window.matchMedia && window.matchMedia('(max-width: 700px)').matches);
    } catch (e) {}
    var ua = navigator.userAgent || '';
    var touchMac = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return compact || /iPad|iPhone|iPod/.test(ua) || touchMac;
  }

  function recycleFrame() {
    state.recyclePending = false;
    clearTimeout(state.readyTimer);
    clearTimeout(state.slowTimer);
    state.readyTimer = 0;
    state.ready = false;
    state.booted = false;
    state.path = '';
    state.symbol = '';
    if (state.overlay) state.overlay.classList.remove('is-ready', 'is-loading', 'is-slow');
    if (!state.frame) return;
    // Mobile WebKit can keep the cross-origin iframe's composited surface black
    // after its fixed ancestor moves through visibility:hidden. Releasing the
    // hidden document makes the next launch paint a fresh surface; HTTP/browser
    // caches still make that second boot much faster than the first.
    try { state.frame.src = 'about:blank'; }
    catch (e) { state.frame.removeAttribute('src'); }
  }

  function pushOverlayHistory() {
    var base = history.state && typeof history.state === 'object'
      ? Object.assign({}, history.state) : {};
    state.historyToken = 'mmto-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);
    base.mmTerminalOverlay = state.historyToken;
    history.pushState(base, '', location.href);
    state.historyActive = true;
  }

  function openInternal(config, fromHistory) {
    if (!config || !config.url) return;
    if (!isDashboardHost()) {
      location.href = config.directUrl || config.url;
      return;
    }
    var root = buildOverlay();
    if (!root) {
      location.href = config.directUrl || config.url;
      return;
    }

    if (!state.open && state.recyclePending) recycleFrame();
    clearTimeout(state.closeTimer);
    state.lastConfig = config;
    state.symbol = config.symbol || '';
    state.targetOrigin = config.targetOrigin || new URL(config.url).origin;
    state.directUrl = config.directUrl || config.url;
    state.newTab.href = state.directUrl;
    setLaunchOrigin(config.trigger);

    if (!state.open) {
      state.open = true;
      root.setAttribute('aria-hidden', 'false');
      root.classList.remove('is-closing');
      void root.offsetWidth;
      root.classList.add('is-open');
      lockDashboard();
      if (!fromHistory) pushOverlayHistory();
      else state.historyActive = true;
    }

    showToast();

    if (!state.booted) {
      state.booted = true;
      beginLoading(root);
      state.frame.src = config.url;
      return;
    }

    if (state.path && state.path !== '/terminal') {
      beginLoading(root);
    }

    if (state.frame.contentWindow) {
      state.frame.contentWindow.postMessage({
        source: 'mastermind-dashboard',
        type: 'terminal:set-symbol',
        symbol: state.symbol
      }, state.targetOrigin);
    }
  }

  function performClose() {
    if (!state.open || !state.overlay) return;
    state.open = false;
    state.historyActive = false;
    state.recyclePending = shouldRecycleFrame();
    clearTimeout(state.toastTimer);
    clearTimeout(state.slowTimer);
    state.toast.classList.remove('show');
    state.overlay.classList.add('is-closing');
    state.overlay.classList.remove('is-open');
    state.overlay.setAttribute('aria-hidden', 'true');
    unlockDashboard();
    state.closeTimer = setTimeout(function () {
      if (!state.overlay || state.open) return;
      state.overlay.classList.remove('is-closing');
      if (state.recyclePending) recycleFrame();
    }, 650);
  }

  function requestClose() {
    if (!state.open) return;
    var hs = history.state;
    if (state.historyActive && hs && hs.mmTerminalOverlay === state.historyToken) {
      history.back();
      return;
    }
    performClose();
  }

  window.addEventListener('message', function (event) {
    if (!state.frame || event.source !== state.frame.contentWindow) return;
    if (event.origin !== state.targetOrigin) return;
    var data = event.data;
    if (!data || data.source !== 'mastermind-terminal') return;
    if (data.type === 'terminal:close') {
      requestClose();
      return;
    }
    if (data.type === 'terminal:ready' || data.type === 'terminal:symbol-ready') {
      markReady(data);
      return;
    }
    if (data.type === 'terminal:route') state.path = data.path || state.path;
  });

  window.addEventListener('keydown', function (event) {
    if (state.open && event.key === 'Escape') {
      event.preventDefault();
      requestClose();
    }
  });

  window.addEventListener('popstate', function (event) {
    var token = event.state && event.state.mmTerminalOverlay;
    if (state.open && token !== state.historyToken) {
      performClose();
      return;
    }
    if (!state.open && token && token === state.historyToken && state.lastConfig) {
      openInternal(state.lastConfig, true);
    }
  });

  window.MDXTerminalOverlay = {
    open: function (config) { openInternal(config, false); },
    close: requestClose,
    isOpen: function () { return state.open; }
  };

  try {
    window.dispatchEvent(new CustomEvent('mdx-terminal-overlay-ready'));
  } catch (e) {}
})();

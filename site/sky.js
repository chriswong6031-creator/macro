/* sky.js — index.html celestial day/night backdrop.
   A full-page fixed layer (#sky, z-index:-1) that paints ABOVE the ambient
   aurora (body::before) but BEHIND all page content:
     • light mode → a glowing sun parked on a time-of-day arc (east→west)
     • dark  mode → a breathing full-page starfield + a glowing moon
   Plays an entry animation on load and a rich cross-fade on theme toggle,
   both reduced-motion aware. Sets window.__skyDeck so theme.js skips its
   generic sitewide sunrise/sunset icon on this page (we do something richer). */
(function () {
  var sky = document.getElementById('sky');
  if (!sky) return;
  window.__skyDeck = true;

  var canvas = document.getElementById('sky-stars');
  var cx = canvas.getContext('2d');
  var sunEl = document.getElementById('sky-sun');
  var moonEl = document.getElementById('sky-moon');
  // --- orbital satellite (dark mode only) ----------------------------------
  var satEl = document.getElementById('sky-sat');
  // Big background satellite DISABLED — superseded by the globe's own mini-satellites.
  // Code kept intact; flip to true to bring it back.
  var SAT_ENABLED = false;
  var globeCanvas = document.querySelector('.gd-canvas');   // the rendered "earth"
  var satPhase = Math.PI;        // begin at the left of the globe, on the visible front arc
  var SAT_SPEED = 0.27;          // rad/s along the bright front sweep (left → right)
  var SAT_BACK = 2.35;           // angular speed-up behind the globe → a brief "off-screen" gap
  var SAT_COSI = 0.70;           // cos(orbit-plane tilt) — vertical squash of the ellipse (~46°)
  var mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  var motionOK = !mq.matches;
  var nowMs = function () { return (window.performance && performance.now) ? performance.now() : Date.now(); };

  if (!SAT_ENABLED && satEl) satEl.style.opacity = '0';   // hide once; frame() will skip placeSat
  var W = 0, H = 0, dpr = 1, stars = [];
  var raf = 0, running = false, lastT = 0;
  var starAlpha = 0, starTarget = 0;   // global star opacity (eased toward target)
  var entry = 1, entryTarget = 1;       // 0..1 "fly in from all directions" progress

  function theme() { return document.documentElement.getAttribute('data-theme') || 'dark'; }
  function cssv(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

  // --- time-of-day → celestial position (in viewport %) --------------------
  function frac(h, rise, set) { var f = (h - rise) / (set - rise); return f < 0 ? 0 : (f > 1 ? 1 : f); }
  function hourNow() { var d = new Date(); return d.getHours() + d.getMinutes() / 60; }
  // The sun/moon ride a SHALLOW arc kept high in the page (top band) so they sit
  // near the top and never collide with the globe below. East→west by time of day.
  // On a NARROW (mobile) viewport the body is large relative to the width, so the
  // arc is tightened and raised → the whole disc stays on-screen, never half-clipped
  // off the left/right edge and never reaching down into the globe.
  function arcPos(f) {
    var mob = window.innerWidth <= 560;
    var x0 = mob ? 26 : 14, xw = mob ? 48 : 72;     // mobile 26%→74% : keeps the disc on-screen
    var y0 = mob ? 13 : 20, ya = mob ? 3 : 6;       // mobile a touch higher + flatter
    return { x: x0 + xw * f, y: y0 - ya * Math.sin(Math.PI * f) };
  }
  function placeSun() {
    var p = arcPos(frac(hourNow(), 7, 19));         // daylight window 07:00–19:00
    sunEl.style.left = p.x.toFixed(2) + '%';
    sunEl.style.top = p.y.toFixed(2) + '%';
  }
  function placeMoon() {
    if (!moonEl) return;                             // page may opt out of the moon
    var nf = (((hourNow() - 19) + 24) % 24) / 12;   // night window 19:00→07:00 (12h)
    var p = arcPos(nf < 0 ? 0 : (nf > 1 ? 1 : nf));
    moonEl.style.left = p.x.toFixed(2) + '%';
    moonEl.style.top = p.y.toFixed(2) + '%';
  }

  // --- starfield -----------------------------------------------------------
  function build() {
    var n = Math.round(Math.min(280, Math.max(90, (W * H) / 7200)));
    stars = [];
    for (var i = 0; i < n; i++) {
      var ang = Math.random() * Math.PI * 2, far = 0.5 + Math.random() * 1.0;
      stars.push({
        x: Math.random(), y: Math.random(),
        r: 0.4 + Math.random() * 1.6,
        p: Math.random() * Math.PI * 2,                  // twinkle phase
        ox: Math.cos(ang) * far, oy: Math.sin(ang) * far, // entry offset → from all directions
        d: Math.random()                                  // entry stagger
      });
    }
  }
  function size() {
    dpr = Math.min(1.5, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = Math.floor(W * dpr); canvas.height = Math.floor(H * dpr);
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!stars.length) build();
    placeSun(); placeMoon();
  }

  function smooth(e) { return e <= 0 ? 0 : (e >= 1 ? 1 : e * e * (3 - 2 * e)); }

  function drawStars(t) {
    cx.clearRect(0, 0, W, H);
    if (starAlpha <= 0.003) return;
    var col = cssv('--text') || '#e8edf6';
    cx.fillStyle = col;
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var e = smooth((entry - s.d * 0.45) / 0.55);                 // staggered fly-in
      if (e <= 0) continue;
      var px = (s.x + s.ox * (1 - e)) * W;
      var py = (s.y + s.oy * (1 - e)) * H;
      var tw = motionOK ? (0.45 + 0.55 * Math.sin(t / 900 + s.p)) : 0.8;
      var a = starAlpha * e * (0.16 + 0.64 * tw) * Math.min(1, s.r / 1.4);
      if (a <= 0.004) continue;
      cx.globalAlpha = a;
      cx.beginPath();
      cx.arc(px, py, s.r, 0, 6.2832);
      cx.fill();
      if (s.r > 1.3) {                                             // sparkle cross on big stars
        cx.globalAlpha = a * 0.45;
        cx.fillRect(px - s.r * 2.6, py - 0.35, s.r * 5.2, 0.7);
        cx.fillRect(px - 0.35, py - s.r * 2.6, 0.7, s.r * 5.2);
      }
    }
    cx.globalAlpha = 1;
  }

  // --- satellite orbit -----------------------------------------------------
  // A tilted 3-D ellipse anchored to the LIVE globe rect, so the satellite truly
  // orbits the rendered earth (and tracks scroll). It sweeps left→right across the
  // bright near arc, then speeds up + fades as it rounds the far arc behind the
  // globe (a few seconds "off screen"), and re-enters from the left. Perspective is
  // faked with scale + opacity — the ring stays clear of the disc, so no z-fighting.
  function placeSat(dt) {
    if (!satEl) return;
    if (!SAT_ENABLED) { satEl.style.opacity = '0'; return; }   // disabled — keep it hidden
    if (theme() !== 'dark' || !globeCanvas) { satEl.style.opacity = '0'; return; }
    var r = globeCanvas.getBoundingClientRect();
    if (r.width < 4 || r.bottom <= 0 || r.top >= H) { satEl.style.opacity = '0'; return; }
    if (motionOK && dt) {
      var s0 = Math.sin(satPhase);
      satPhase -= SAT_SPEED * (s0 >= 0 ? 1 : SAT_BACK) * (dt / 1000);  // faster behind the globe
      if (satPhase < -Math.PI) satPhase += 6.283185307;               // wrap, keep continuous
    }
    var c = Math.cos(satPhase), s = Math.sin(satPhase);
    var gR = Math.min(r.width, r.height) * 0.34;     // matches globe-deck's fit radius
    var rho = gR * 1.5;                               // orbit radius — a ring just clear of the disc
    var lift = gR * 0.18;                             // raise the ellipse so the bright arc clears the disc top
    var x = r.left + r.width / 2 + rho * c;
    // near arc (s>0) rides OVER the globe — the lit sweep through the gap toward the
    // moon; the far arc (s<0) sinks below/behind the earth, where it fades out.
    var y = r.top + r.height / 2 - lift - rho * SAT_COSI * s;
    var scale = 1 + 0.30 * s;                         // nearer (front) → larger
    var bank = -c * 13;                               // gentle ±13° bank, level mid-sweep
    var op;                                           // full in front; fade only deep behind
    if (s >= -0.12) op = 1;
    else if (s <= -0.9) op = 0;
    else { var u = (s + 0.9) / 0.78; op = u * u * (3 - 2 * u); }
    var sa = starAlpha < 0 ? 0 : (starAlpha > 1 ? 1 : starAlpha);   // fade in/out with the night
    satEl.style.transform = 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px) translate(-50%,-50%) rotate(' + bank.toFixed(2) + 'deg) scale(' + scale.toFixed(3) + ')';
    satEl.style.opacity = (op * sa).toFixed(3);
  }

  var lastScrollT = -9999;   // timestamp of last scroll event (for scroll-skip)

  // --- scroll-coupled moon-set (dark mode only) --------------------------------
  // p = 0 at top, 1 when hero has scrolled 90vh past (scroll-driven, not time-driven).
  // The stylesheet centers the disc with transform:translate(-50%,-50%) on its left/top
  // anchor, so every inline transform written here MUST re-state that centering before
  // adding the scroll offset (an inline transform fully replaces the stylesheet one).
  var _moonP = -1;   // last applied p (skip writes when delta < 0.01)
  function _applyMoonScroll() {
    if (!moonEl) return;
    var dark = theme() === 'dark';
    if (!dark) {
      // light mode: ensure moon is invisible regardless of scroll
      if (_moonP !== 0) {
        _moonP = 0;
        moonEl.style.opacity = '0';
        moonEl.style.transform = 'translate(-50%,-50%)';
      }
      return;
    }
    var vH = window.innerHeight || 1;
    var p = Math.max(0, Math.min(1, window.scrollY / (vH * 0.9)));
    if (Math.abs(p - _moonP) < 0.01) return;   // skip write if barely changed
    _moonP = p;
    moonEl.style.opacity = (1 - p).toFixed(3);
    moonEl.style.transform = 'translate(-50%,-50%) translateY(' + (p * 90).toFixed(1) + 'px)';
    // also dim the star canvas (not in light mode — only the dark path reaches here)
    // We do this by adjusting globalAlpha of the canvas element itself rather than
    // patching starAlpha (which belongs to the rAF loop). Use canvas style opacity.
    // Fade canvas to ~35% alpha as p→1.
    canvas.style.opacity = (1 - p * 0.65).toFixed(3);
  }
  var _moonScrollRaf = 0;
  window.addEventListener('scroll', function () {
    lastScrollT = performance.now();
    if (_moonScrollRaf) return;
    _moonScrollRaf = requestAnimationFrame(function () {
      _moonScrollRaf = 0;
      _applyMoonScroll();
    });
  }, { passive: true });

  var lastDrawT = 0;         // timestamp of last drawStars call (for twinkle throttle)

  function frame(t) {
    if (!running) return;                 // ignore any stale/queued callback
    if (!lastT) lastT = t;
    var dt = Math.min(60, t - lastT); lastT = t;
    var ka = 1 - Math.pow(0.0015, dt / 1000);   // star opacity easing
    var ke = 1 - Math.pow(0.02, dt / 1000);     // entry easing (slower, more graceful)
    starAlpha += (starTarget - starAlpha) * ka;
    entry += (entryTarget - entry) * ke;

    // --- scroll skip: canvas is position:fixed; frozen stars during scroll are imperceptible ---
    var scrolling = (t - lastScrollT) < 120;
    // --- twinkle throttle: once animation has settled, cap redraws to ~30fps ---
    var settled = entry > 0.996 && Math.abs(starAlpha - starTarget) < 0.004;
    var throttled = settled && (t - lastDrawT) < 28;
    if (!scrolling && !throttled) {
      drawStars(t);
      lastDrawT = t;
    }
    if (SAT_ENABLED) placeSat(dt);

    if (!motionOK) { running = false; raf = 0; return; }   // static single frame
    var fullySettled = Math.abs(starAlpha - starTarget) < 0.004 && Math.abs(entry - entryTarget) < 0.004;
    if (starTarget === 0 && fullySettled) { running = false; raf = 0; cx.clearRect(0, 0, W, H); return; }
    raf = requestAnimationFrame(frame);
  }
  function run() { if (!running) { running = true; lastT = 0; if (raf) cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); } }

  // --- apply theme state (animate=false on the very first paint) -----------
  function apply(animate) {
    var dark = theme() === 'dark';
    placeSun(); placeMoon();
    sky.setAttribute('data-sky', dark ? 'night' : 'day');
    if (dark) {
      starTarget = 1;
      entryTarget = 1;
      if (animate && motionOK) entry = 0;     // replay the fly-in
      else entry = 1;
      // restore canvas opacity (may have been dimmed by scroll in a prior dark session)
      canvas.style.opacity = '';
      // re-apply scroll-based moon position for the current scroll offset
      _moonP = -1;   // force recalculate
      _applyMoonScroll();
    } else {
      starTarget = 0;                          // fade stars out (sun takes over)
      // Explicitly hide moon in light mode — the CSS data-sky contract should do this,
      // but we also zero it here to cover any timing gap before CSS takes over.
      if (moonEl) { moonEl.style.opacity = '0'; moonEl.style.transform = 'translate(-50%,-50%)'; }
      _moonP = 0;
      // restore canvas opacity (scroll may have dimmed it while in dark mode)
      canvas.style.opacity = '';
    }
    if (!motionOK) { starAlpha = starTarget; entry = 1; drawStars(nowMs()); }
    run();
  }

  // --- wiring --------------------------------------------------------------
  var rz;
  window.addEventListener('resize', function () {
    clearTimeout(rz);
    rz = setTimeout(function () { size(); drawStars(nowMs()); run(); }, 140);
  });
  document.addEventListener('themechange', function () { apply(true); });
  if (mq.addEventListener) mq.addEventListener('change', function (e) { motionOK = !e.matches; apply(false); });

  size();
  // The sun/moon start hidden (CSS default). Commit that initial state with a
  // forced reflow, then flip — so the rise + star fly-in reliably transition in
  // (independent of rAF timing / first-paint coalescing).
  void sky.offsetWidth;
  apply(true);
})();

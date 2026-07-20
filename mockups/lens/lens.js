/* ============================================================================
   LENS controller — one singleton popover for every explainer on the page.
   Desktop: hover-intent glass card (90ms open, 180ms close grace, the card
   itself is hoverable). Touch: tap-to-toggle; on phones (≤640px) the card
   becomes a bottom sheet with scrim + swipe-down dismiss. Keyboard: focus
   opens, Escape closes. Content comes from a .lens-src DOM block (rich tier)
   or data-tip-en/zh · data-lens-en/zh attributes (string tier).
   ============================================================================ */
(function () {
  'use strict';
  if (window.__lensInit) return; window.__lensInit = true;

  var OPEN_MS = 90, CLOSE_MS = 180;
  var SEL = '.lens-q, .lens-term, [data-lens], [data-lens-en], [data-tip-en]';
  var pop = null, scrim = null, curTrig = null;
  var openTimer = 0, closeTimer = 0;

  function isSheet () { return window.matchMedia('(max-width:640px)').matches; }
  function isOpen () { return !!(pop && pop.classList.contains('open')); }

  function ensure () {
    if (pop) return;
    scrim = document.createElement('div');
    scrim.className = 'lens-scrim';
    document.body.appendChild(scrim);
    scrim.addEventListener('click', hide);

    pop = document.createElement('div');
    pop.className = 'lens-pop';
    pop.id = 'lensPop';
    pop.setAttribute('role', 'tooltip');
    document.body.appendChild(pop);

    pop.addEventListener('pointerenter', function () { clearTimeout(closeTimer); });
    pop.addEventListener('pointerleave', scheduleClose);
    pop.addEventListener('click', function (e) {
      if (e.target.closest('.lens-x')) hide();
    });

    /* swipe-down dismiss on the sheet */
    var y0 = null, dy = 0;
    pop.addEventListener('touchstart', function (e) {
      if (!isSheet() || pop.scrollTop > 0) return;
      y0 = e.touches[0].clientY; dy = 0;
      pop.style.transition = 'none';
    }, { passive: true });
    pop.addEventListener('touchmove', function (e) {
      if (y0 == null) return;
      dy = Math.max(0, e.touches[0].clientY - y0);
      pop.style.transform = 'translateY(' + dy + 'px)';
    }, { passive: true });
    pop.addEventListener('touchend', function () {
      if (y0 == null) return;
      pop.style.transition = ''; pop.style.transform = '';
      if (dy > 64) hide();
      y0 = null;
    });
  }

  function contentFor (t) {
    var src = t.querySelector('.lens-src');
    if (!src && t.nextElementSibling && t.nextElementSibling.classList &&
        t.nextElementSibling.classList.contains('lens-src')) src = t.nextElementSibling;
    if (src) {
      return { kind: t.getAttribute('data-lens-kind') || src.getAttribute('data-lens-kind') || 'define',
               rich: src.innerHTML };
    }
    var en = t.getAttribute('data-lens-en') || t.getAttribute('data-tip-en');
    var zh = t.getAttribute('data-lens-zh') || t.getAttribute('data-tip-zh');
    if (en || zh) return { kind: t.getAttribute('data-lens-kind') || '', plain: { en: en || zh, zh: zh || en } };
    return null;
  }

  function show (t) {
    var c = contentFor(t);
    if (!c) return;
    ensure();
    clearTimeout(closeTimer);
    if (curTrig === t && isOpen()) return;
    if (curTrig) { curTrig.classList.remove('lens-on'); curTrig.removeAttribute('aria-describedby'); }
    curTrig = t;
    t.classList.add('lens-on');
    t.setAttribute('aria-describedby', 'lensPop');

    var chrome = '<div class="lens-grab"></div><button class="lens-x" type="button" aria-label="Close">✕</button>';
    if (c.rich) {
      pop.classList.remove('lens-plain');
      pop.innerHTML = chrome + c.rich;
    } else {
      pop.classList.add('lens-plain');
      pop.innerHTML = chrome + '<div class="lens-body"><span class="l-en"></span><span class="l-zh"></span></div>';
      pop.querySelector('.l-en').textContent = c.plain.en;
      pop.querySelector('.l-zh').textContent = c.plain.zh;
    }
    if (c.kind) pop.setAttribute('data-kind', c.kind); else pop.removeAttribute('data-kind');

    pop.classList.remove('open');            /* restart entrance + sheen */
    void pop.offsetWidth;
    pop.classList.add('open');

    if (isSheet()) {
      scrim.classList.add('open');
      document.documentElement.classList.add('lens-lock');
      return;
    }
    scrim.classList.remove('open');
    place(t);
  }

  function place (t) {
    var r = t.getBoundingClientRect();
    var pw = pop.offsetWidth, ph = pop.offsetHeight;
    var above = r.top - ph - 9 >= 8;
    var y = above ? r.top - ph - 9 : r.bottom + 9;
    if (!above && y + ph > window.innerHeight - 8) y = Math.max(8, window.innerHeight - ph - 8);
    var x = Math.round(Math.max(12, Math.min(r.left + r.width / 2 - pw / 2, window.innerWidth - pw - 12)));
    pop.style.left = x + 'px';
    pop.style.top = Math.round(y) + 'px';
    pop.style.transformOrigin = Math.round(r.left + r.width / 2 - x) + 'px ' + (above ? '100%' : '0%');
  }

  function hide () {
    clearTimeout(openTimer); clearTimeout(closeTimer);
    if (!pop) return;
    pop.classList.remove('open');
    scrim.classList.remove('open');
    document.documentElement.classList.remove('lens-lock');
    if (curTrig) { curTrig.classList.remove('lens-on'); curTrig.removeAttribute('aria-describedby'); curTrig = null; }
  }

  function scheduleClose () {
    clearTimeout(closeTimer);
    closeTimer = setTimeout(hide, CLOSE_MS);
  }

  /* hover intent (mouse only — touch goes through click) */
  document.addEventListener('pointerover', function (e) {
    if (e.pointerType && e.pointerType !== 'mouse') return;
    var t = e.target.closest && e.target.closest(SEL);
    if (!t) return;
    clearTimeout(closeTimer);
    if (curTrig === t && isOpen()) return;
    clearTimeout(openTimer);
    openTimer = setTimeout(function () { show(t); }, OPEN_MS);
  });
  document.addEventListener('pointerout', function (e) {
    if (e.pointerType && e.pointerType !== 'mouse') return;
    var t = e.target.closest && e.target.closest(SEL);
    if (!t) return;
    clearTimeout(openTimer);
    scheduleClose();
  });

  /* tap / click toggle; click-away closes */
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest(SEL);
    if (!t) {
      if (isOpen() && !e.target.closest('.lens-pop')) hide();
      return;
    }
    if (curTrig === t && isOpen()) hide(); else show(t);
  });

  /* keyboard */
  document.addEventListener('focusin', function (e) {
    var t = e.target.closest && e.target.closest(SEL);
    if (t) show(t);
  });
  document.addEventListener('focusout', function (e) {
    var t = e.target.closest && e.target.closest(SEL);
    if (t) scheduleClose();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isOpen()) hide();
  });

  /* scroll: the floating card follows its trigger; it hides only when the
     trigger leaves the viewport (the sheet is scroll-locked, so no-op there) */
  var scrollRaf = 0;
  window.addEventListener('scroll', function () {
    if (!isOpen() || isSheet() || !curTrig) return;
    if (scrollRaf) return;
    scrollRaf = requestAnimationFrame(function () {
      scrollRaf = 0;
      if (!isOpen() || !curTrig) return;
      var r = curTrig.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight) { hide(); return; }
      place(curTrig);
    });
  }, { passive: true });
})();

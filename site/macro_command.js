/* macro_command.js — Macro Command shell behaviour (F01 / Macro Command P1).
   No framework. No style injection: zero colour literals, zero
   `style.textContent` writes, zero created style elements (G9). The only
   style-adjacent DOM this file touches is class names and the `hidden`
   property. No section-swap animation of any kind (§6.2 item 5) — sections
   swap instantly in both themes, and there is no animation clock anywhere on
   this page.

   Hash grammar: `#<section>` or `#<section>/<subtab>` (§6.2 item 1). An
   unknown or empty section resolves to `overview`; an unknown sub-tab
   resolves to that section's first tab. */
(function () {
  'use strict';

  var shell = document.getElementById('mc-shell');
  if (!shell) return;

  var rail = document.getElementById('mc-rail');
  var content = document.getElementById('mc-content');
  var panels = Array.prototype.slice.call(content.querySelectorAll('[data-mc-panel]'));
  var railLinks = Array.prototype.slice.call(rail.querySelectorAll('[data-mc-section]'));
  var PENDING_TIMEOUT_MS = 8000;
  var fetchedSections = {};

  function panelById(id) {
    for (var i = 0; i < panels.length; i++) {
      if (panels[i].getAttribute('data-mc-panel') === id) return panels[i];
    }
    return null;
  }

  function railLinkById(id) {
    for (var i = 0; i < railLinks.length; i++) {
      if (railLinks[i].getAttribute('data-mc-section') === id) return railLinks[i];
    }
    return null;
  }

  /* ── hash grammar (two segments) — §6.2 item 1 ─────────────────────────── */
  function parseHash() {
    var raw = (location.hash || '').replace(/^#/, '');
    var parts = raw.split('/');
    var sectionId = parts[0] || '';
    var subtabId = parts[1] || '';
    if (!panelById(sectionId)) sectionId = 'overview';
    return { section: sectionId, subtab: subtabId };
  }

  /* ── section activation — §6.2 item 2 ──────────────────────────────────── */
  function activateSection(id, subtabId) {
    var target = panelById(id) || panelById('overview');
    if (!target) return;
    var resolvedId = target.getAttribute('data-mc-panel');

    panels.forEach(function (panel) {
      var isTarget = panel === target;
      panel.hidden = !isTarget;
    });
    railLinks.forEach(function (link) {
      var isCurrent = link.getAttribute('data-mc-section') === resolvedId;
      if (isCurrent) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
      link.classList.toggle('is-current', isCurrent);
    });

    activateSubtab(target, subtabId);
    maybeFetchFragment(target, resolvedId);

    var hash = '#' + resolvedId + (subtabId ? '/' + subtabId : '');
    if (location.hash !== hash) history.replaceState(null, '', hash);
    target.focus();
  }

  /* ── sub-tabs: real role="tablist", roving tabindex — §6.2 item 4 ─────── */
  function activateSubtab(panel, requestedId) {
    var tabs = Array.prototype.slice.call(panel.querySelectorAll('[data-mc-subtab]'));
    if (!tabs.length) return;
    var match = null;
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].getAttribute('data-mc-subtab') === requestedId) { match = tabs[i]; break; }
    }
    if (!match) match = tabs[0];
    tabs.forEach(function (tab) {
      var selected = tab === match;
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.setAttribute('tabindex', selected ? '0' : '-1');
    });
    var selectedId = match.getAttribute('data-mc-subtab');
    var bodies = Array.prototype.slice.call(panel.querySelectorAll('[data-mc-tabbody]'));
    bodies.forEach(function (body) {
      body.hidden = body.getAttribute('data-mc-tabbody') !== selectedId;
    });
  }

  function wireSubtabKeyboard(panel) {
    var tabs = Array.prototype.slice.call(panel.querySelectorAll('[data-mc-subtab]'));
    if (!tabs.length) return;
    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () {
        activateSubtab(panel, tab.getAttribute('data-mc-subtab'));
        var sectionId = panel.getAttribute('data-mc-panel');
        history.replaceState(null, '', '#' + sectionId + '/' + tab.getAttribute('data-mc-subtab'));
      });
      tab.addEventListener('keydown', function (ev) {
        var delta = 0;
        if (ev.key === 'ArrowRight') delta = 1;
        else if (ev.key === 'ArrowLeft') delta = -1;
        else if (ev.key === 'Home') delta = -index;
        else if (ev.key === 'End') delta = tabs.length - 1 - index;
        else return;
        ev.preventDefault();
        var next = tabs[(index + delta + tabs.length) % tabs.length];
        next.focus();
        next.click();
      });
    });
  }

  /* ── fragment fetch on first activation — §6.2 item 3 ──────────────────── */
  function maybeFetchFragment(panel, sectionId) {
    if (sectionId === 'overview' || fetchedSections[sectionId]) return;
    fetchedSections[sectionId] = true;
    var figure = panel.querySelector('[data-mc-figure]');
    if (!figure) return;
    var pending = figure.querySelector('[data-mc-pending]');
    var offers = Array.prototype.slice.call(figure.querySelectorAll('[data-mc-offer]'));
    if (pending) pending.hidden = false;
    offers.forEach(function (offer) { offer.hidden = true; });

    var settled = false;
    var timer = setTimeout(function () { fail(); }, PENDING_TIMEOUT_MS);

    function restoreOffer() {
      if (pending) pending.hidden = true;
      offers.forEach(function (offer) { offer.hidden = false; });
    }

    function fail() {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      restoreOffer();
      /* Fragments do not exist in P1 (§9 P1, R7): the fetch always degrades to
         the honest offer line, never a spinner that can spin forever. */
    }

    if (typeof fetch !== 'function') { fail(); return; }
    fetch('macro/fragments/' + sectionId + '.html')
      .then(function (resp) {
        if (settled) return;
        if (!resp.ok) { fail(); return; }
        return resp.text().then(function (text) {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          figure.innerHTML = text;
        });
      })
      .catch(function () { fail(); });
  }

  /* ── rail click/keyboard ────────────────────────────────────────────────── */
  railLinks.forEach(function (link) {
    link.addEventListener('click', function (ev) {
      ev.preventDefault();
      var id = link.getAttribute('data-mc-section');
      activateSection(id, '');
    });
  });

  window.addEventListener('hashchange', function () {
    var parsed = parseHash();
    activateSection(parsed.section, parsed.subtab);
  });

  panels.forEach(wireSubtabKeyboard);

  /* ── analyst control — §8, R8: existing sitewide entry points only ─────── */
  var analystBtn = document.querySelector('[data-mc-analyst]');
  if (analystBtn) {
    analystBtn.addEventListener('click', function () {
      var sectionId = 'overview';
      var current = content.querySelector('[data-mc-panel]:not([hidden])');
      if (current) sectionId = current.getAttribute('data-mc-panel');
      var railLink = railLinkById(sectionId);
      var label = railLink ? railLink.textContent.trim() : 'Macro Command';
      if (window.MMBrain && window.MMBrain.mounted) {
        if (typeof window.MMBrain.explain === 'function') window.MMBrain.explain(sectionId, label);
        else if (typeof window.MMBrain.open === 'function') window.MMBrain.open();
        return;
      }
      /* Not yet mounted: activate the sitewide launcher stub theme.js already
         renders on this page (`#mmb-boot`) — its own click handler owns the
         load-then-open flow. No new endpoint, no new query string. */
      var boot = document.getElementById('mmb-boot');
      if (boot) boot.click();
    });
  }

  /* ── boot ───────────────────────────────────────────────────────────────── */
  var initial = parseHash();
  activateSection(initial.section, initial.subtab);
})();

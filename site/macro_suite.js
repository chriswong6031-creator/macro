/* Macro & Monetary suite — shared page behaviour for all twelve workspaces.
 *
 * Deliberately small. The page is rendered SERVER-SIDE from an already
 * hash-validated snapshot, so this file never fetches, never computes a state,
 * and never writes a value into the document. It only moves the reader around:
 * tab selection, deep links, and the evidence drawer.
 *
 * Progressive enhancement is the contract. With JavaScript disabled every panel
 * stays visible and the evidence drawer is simply not opened — a reader still
 * sees the whole snapshot rather than a blank shell.
 */
(function () {
  'use strict';

  var PANEL_SELECTOR = '[data-mq-panel]';
  var TAB_SELECTOR = '[data-mq-tab]';

  var state = { tab: null, lastFocus: null, drawerOpen: false };
  var ui = {};

  function byId(id) { return document.getElementById(id); }
  function all(selector) { return Array.prototype.slice.call(document.querySelectorAll(selector)); }

  function setInert(node, on) {
    if (!node) return;
    if (on) { node.setAttribute('inert', ''); node.setAttribute('aria-hidden', 'true'); }
    else { node.removeAttribute('inert'); node.removeAttribute('aria-hidden'); }
  }

  // --- tabs ----------------------------------------------------------------

  function selectTab(name, options) {
    var opts = options || {};
    var panels = all(PANEL_SELECTOR);
    var tabs = all(TAB_SELECTOR);
    var known = tabs.some(function (tab) { return tab.getAttribute('data-mq-tab') === name; });
    if (!known) return false;

    state.tab = name;
    panels.forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-mq-panel') !== name;
    });
    tabs.forEach(function (tab) {
      var active = tab.getAttribute('data-mq-tab') === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.tabIndex = active ? 0 : -1;
    });
    if (opts.updateUrl !== false && window.history && window.history.replaceState) {
      try {
        var url = new URL(window.location.href);
        url.hash = name;
        window.history.replaceState(null, '', url);
      } catch (error) { /* a file:// or opaque origin cannot carry a URL object */ }
    }
    if (opts.focus) {
      var target = tabs.filter(function (tab) { return tab.getAttribute('data-mq-tab') === name; })[0];
      if (target) target.focus();
    }
    return true;
  }

  function wireTabs() {
    var tabs = all(TAB_SELECTOR);
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        selectTab(tab.getAttribute('data-mq-tab'));
      });
      tab.addEventListener('keydown', function (event) {
        var index = tabs.indexOf(tab);
        var next = null;
        if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length];
        else if (event.key === 'ArrowLeft') next = tabs[(index - 1 + tabs.length) % tabs.length];
        else if (event.key === 'Home') next = tabs[0];
        else if (event.key === 'End') next = tabs[tabs.length - 1];
        if (!next) return;
        event.preventDefault();
        selectTab(next.getAttribute('data-mq-tab'), { focus: true });
      });
    });
    var requested = (window.location.hash || '').replace('#', '');
    if (!requested || !selectTab(requested, { updateUrl: false })) {
      selectTab(tabs[0].getAttribute('data-mq-tab'), { updateUrl: false });
    }
    window.addEventListener('hashchange', function () {
      var name = (window.location.hash || '').replace('#', '');
      if (name) selectTab(name, { updateUrl: false });
    });
  }

  // --- evidence drawer -----------------------------------------------------

  function focusableInDrawer() {
    if (!ui.drawer) return [];
    return all('#mq-evidence-drawer button, #mq-evidence-drawer a[href], #mq-evidence-drawer summary')
      .filter(function (node) { return node.offsetParent !== null || node === ui.closeEvidence; });
  }

  function handleDrawerKeydown(event) {
    if (!state.drawerOpen) return;
    if (event.key === 'Escape') { event.preventDefault(); closeEvidence(); return; }
    if (event.key !== 'Tab') return;
    var nodes = focusableInDrawer();
    if (!nodes.length) return;
    var first = nodes[0];
    var last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function openEvidence() {
    if (!ui.drawer || state.drawerOpen) return;
    state.lastFocus = document.activeElement;
    state.drawerOpen = true;
    ui.drawer.hidden = false;
    ui.drawer.removeAttribute('inert');
    ui.drawer.removeAttribute('aria-hidden');
    ui.drawer.setAttribute('role', 'dialog');
    ui.drawer.setAttribute('aria-modal', 'true');
    // Two frames: the element must be laid out before the transform animates.
    window.requestAnimationFrame(function () { ui.drawer.classList.add('is-open'); });
    if (ui.scrim) ui.scrim.hidden = false;
    document.body.classList.add('mq-modal-open');
    setInert(ui.shell, true);
    setInert(ui.siteNav, true);
    if (ui.closeEvidence) ui.closeEvidence.focus();
  }

  function closeEvidence() {
    if (!ui.drawer || !state.drawerOpen) return;
    state.drawerOpen = false;
    ui.drawer.classList.remove('is-open');
    ui.drawer.hidden = true;
    ui.drawer.setAttribute('inert', '');
    ui.drawer.setAttribute('aria-hidden', 'true');
    ui.drawer.removeAttribute('role');
    ui.drawer.removeAttribute('aria-modal');
    if (ui.scrim) ui.scrim.hidden = true;
    document.body.classList.remove('mq-modal-open');
    setInert(ui.shell, false);
    setInert(ui.siteNav, false);
    if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus({ preventScroll: true });
  }

  // --- language-reactive attributes ---------------------------------------
  // Visible copy toggles through .l-en/.l-zh in CSS. ATTRIBUTES cannot, so the
  // few that carry text are re-read on the shared runtime's `langchange` event.

  function updateLocalizedAttributes() {
    var lang = document.documentElement.getAttribute('data-lang') === 'zh' ? 'zh' : 'en';
    all('[data-label-en]').forEach(function (node) {
      var text = node.getAttribute(lang === 'zh' ? 'data-label-zh' : 'data-label-en');
      if (text) node.setAttribute('aria-label', text);
    });
  }

  function init() {
    ui.shell = byId('mq-shell');
    ui.drawer = byId('mq-evidence-drawer');
    ui.scrim = byId('mq-scrim');
    ui.closeEvidence = byId('mq-close-evidence');
    ui.siteNav = document.querySelector('nav.site-nav');

    wireTabs();
    updateLocalizedAttributes();

    all('[data-mq-open-evidence]').forEach(function (button) {
      button.addEventListener('click', openEvidence);
    });
    if (ui.closeEvidence) ui.closeEvidence.addEventListener('click', closeEvidence);
    if (ui.scrim) ui.scrim.addEventListener('click', closeEvidence);
    document.addEventListener('keydown', handleDrawerKeydown);
    document.addEventListener('langchange', updateLocalizedAttributes);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Pure helpers, exposed for the node-based unit harness only.
  window.__MACRO_SUITE_TEST__ = { selectTab: selectTab, updateLocalizedAttributes: updateLocalizedAttributes };
}());

/* Semantic dashboard icon hydration.
   Converts legacy emoji text emitted by static templates and live renderers into
   the same flat outline language used by product navigation. */
(function () {
  "use strict";

  var specs = [
    ["\uD83C\uDDFA\uD83C\uDDF8", "dash-flag menu-icon-us", "US", "United States"],
    ["\uD83C\uDDE8\uD83C\uDDF3", "dash-flag menu-icon-cn", "CN", "China"],
    ["\uD83C\uDDED\uD83C\uDDF0", "dash-flag menu-icon-hk", "HK", "Hong Kong"],
    ["\uD83C\uDDE8\uD83C\uDDE6", "dash-flag menu-icon-ca", "CA", "Canada"],
    ["\uD83C\uDDEA\uD83C\uDDFA", "dash-flag dash-flag-code", "EU", "European Union"],
    ["\uD83C\uDDEF\uD83C\uDDF5", "dash-flag dash-flag-code", "JP", "Japan"],
    ["\uD83C\uDDEC\uD83C\uDDE7", "dash-flag dash-flag-code", "GB", "United Kingdom"],
    ["\uD83C\uDDE8\uD83C\uDDED", "dash-flag dash-flag-code", "CH", "Switzerland"],
    ["\uD83C\uDDE6\uD83C\uDDFA", "dash-flag dash-flag-code", "AU", "Australia"],
    ["\uD83C\uDDF0\uD83C\uDDF7", "dash-flag dash-flag-code", "KR", "South Korea"],
    ["\uD83C\uDDF9\uD83C\uDDFC", "dash-flag dash-flag-code", "TW", "Taiwan"],
    ["\uD83C\uDDEE\uD83C\uDDF3", "dash-flag dash-flag-code", "IN", "India"],
    ["\uD83C\uDDEA\uD83C\uDDF8", "dash-flag dash-flag-code", "ES", "Spain"],
    ["\uD83C\uDDEB\uD83C\uDDF7", "dash-flag dash-flag-code", "FR", "France"],
    ["\uD83C\uDDEE\uD83C\uDDF9", "dash-flag dash-flag-code", "IT", "Italy"],
    ["\uD83C\uDDF3\uD83C\uDDF1", "dash-flag dash-flag-code", "NL", "Netherlands"],
    ["\uD83C\uDDF8\uD83C\uDDEA", "dash-flag dash-flag-code", "SE", "Sweden"],
    ["\uD83D\uDD0E", "dash-icon dash-icon-search", "", "Search"],
    ["\u2600\uFE0F", "dash-icon dash-icon-sun", "", "Light theme"],
    ["\u2600", "dash-icon dash-icon-sun", "", "Light theme"],
    ["\uD83C\uDF19", "dash-icon dash-icon-moon", "", "Dark theme"],
    ["\u2630", "dash-icon dash-icon-table", "", "Table view"],
    ["\u2605", "dash-icon dash-icon-star dash-tone-warn", "", "Model selection"],
    ["\u2B50", "dash-icon dash-icon-star dash-tone-warn", "", "Standout"],
    ["\u2726", "dash-icon dash-icon-star dash-tone-info", "", "Standout"],
    ["\u2139\uFE0F", "dash-icon dash-icon-info dash-tone-info", "", "Information"],
    ["\u2139", "dash-icon dash-icon-info dash-tone-info", "", "Information"],
    ["\u26A0\uFE0F", "dash-icon submenu-icon-alert dash-tone-warn", "", "Warning"],
    ["\u26A0", "dash-icon submenu-icon-alert dash-tone-warn", "", "Warning"],
    ["\uD83D\uDEA8", "dash-icon submenu-icon-alert dash-tone-down", "", "Alert"],
    ["\uD83D\uDED1", "dash-icon dash-icon-prohibited dash-tone-down", "", "Stop"],
    ["\u26D4", "dash-icon dash-icon-prohibited dash-tone-down", "", "Blocked"],
    ["\uD83D\uDEAB", "dash-icon dash-icon-prohibited dash-tone-down", "", "Avoid"],
    ["\u26A1", "dash-icon submenu-icon-event dash-tone-warn", "", "Fresh signal"],
    ["\u2705", "dash-icon dash-icon-check dash-tone-up", "", "Confirmed"],
    ["\u2713", "dash-icon dash-icon-check dash-tone-up", "", "Confirmed"],
    ["\u2715", "dash-icon dash-icon-close", "", "Close"],
    ["\u2717", "dash-icon dash-icon-close dash-tone-down", "", "Failed"],
    ["\u270B", "dash-icon dash-icon-pause dash-tone-muted", "", "Hold"],
    ["\uD83D\uDDF2\uFE0F", "dash-icon dash-icon-finish dash-tone-muted", "", "Milestone"],
    ["\u2691", "dash-icon dash-icon-finish dash-tone-muted", "", "Milestone"],
    ["\uD83C\uDFC1", "dash-icon dash-icon-finish dash-tone-muted", "", "Already ran"],
    ["\uD83C\uDF31", "dash-icon dash-icon-ripening dash-tone-up", "", "Ripening"],
    ["\u23F3", "dash-icon research-icon-cycle-intelligence dash-tone-warn", "", "Waiting"],
    ["\u231B", "dash-icon research-icon-cycle-intelligence dash-tone-warn", "", "Waiting"],
    ["\u23F1\uFE0F", "dash-icon research-icon-measurement dash-tone-info", "", "Timing"],
    ["\u23F1", "dash-icon research-icon-measurement dash-tone-info", "", "Timing"],
    ["\uD83C\uDFAF", "dash-icon submenu-icon-radar dash-tone-info", "", "Entry"],
    ["\uD83C\uDFC3", "dash-icon submenu-icon-leader dash-tone-info", "", "Running"],
    ["\uD83C\uDF00", "dash-icon submenu-icon-rotation dash-tone-info", "", "Rotation"],
    ["\uD83D\uDD04", "dash-icon submenu-icon-rotation dash-tone-info", "", "Reversion"],
    ["\uD83C\uDF0A", "dash-icon submenu-icon-flow dash-tone-info", "", "Washout"],
    ["\uD83C\uDF0D", "dash-icon research-icon-global-cycles dash-tone-info", "", "Global"],
    ["\uD83C\uDF10", "dash-icon research-icon-global-cycles dash-tone-info", "", "Global"],
    ["\uD83C\uDF21\uFE0F", "dash-icon submenu-icon-heatmap dash-tone-warn", "", "Market heat"],
    ["\uD83C\uDF21", "dash-icon submenu-icon-heatmap dash-tone-warn", "", "Market heat"],
    ["\uD83D\uDD25", "dash-icon submenu-icon-heatmap dash-tone-down", "", "Market heat"],
    ["\uD83C\uDFDB\uFE0F", "dash-icon submenu-icon-policy", "", "Sector or policy"],
    ["\uD83C\uDFDB", "dash-icon submenu-icon-policy", "", "Sector or policy"],
    ["\uD83C\uDFE6", "dash-icon submenu-icon-policy", "", "Central bank"],
    ["\uD83D\uDCB8", "dash-icon research-icon-fund-flows dash-tone-info", "", "Fund flow"],
    ["\uD83D\uDCB0", "dash-icon dash-icon-profit dash-tone-warn", "", "Take profits"],
    ["\uD83D\uDC33", "dash-icon research-icon-fund-flows dash-tone-info", "", "Fund moves"],
    ["\uD83D\uDC41\uFE0F", "dash-icon research-icon-foresight dash-tone-info", "", "Watch"],
    ["\uD83D\uDC41", "dash-icon research-icon-foresight dash-tone-info", "", "Watch"],
    ["\uD83D\uDC64", "dash-icon dash-icon-person", "", "Insider"],
    ["\uD83D\uDCA7", "dash-icon dash-icon-drop dash-tone-info", "", "Liquidity"],
    ["\uD83D\uDCC8", "dash-icon submenu-icon-stocks dash-tone-up", "", "Uptrend"],
    ["\uD83D\uDCC9", "dash-icon submenu-icon-stocks dash-tone-down", "", "Downtrend"],
    ["\uD83D\uDCCA", "dash-icon submenu-icon-stocks dash-tone-info", "", "Track record"],
    ["\uD83D\uDCF0", "dash-icon submenu-icon-news", "", "News"],
    ["\uD83D\uDCC5", "dash-icon research-icon-factors-seasonality", "", "Calendar"],
    ["\uD83D\uDCCB", "dash-icon research-icon-reports", "", "Report"],
    ["\uD83D\uDD17", "dash-icon submenu-icon-confluence", "", "Confluence"],
    ["\uD83D\uDD14", "dash-icon submenu-icon-alert dash-tone-warn", "", "Alert"],
    ["\uD83D\uDD3B", "dash-icon submenu-icon-stocks dash-tone-down", "", "Falling"],
    ["\uD83D\uDEE1\uFE0F", "dash-icon dash-icon-shield dash-tone-info", "", "Defensive"],
    ["\uD83D\uDEE1", "dash-icon dash-icon-shield dash-tone-info", "", "Defensive"],
    ["\uD83E\uDDE0", "dash-icon submenu-icon-intelligence dash-tone-info", "", "Intelligence"],
    ["\uD83E\uDD16", "dash-icon submenu-icon-intelligence dash-tone-info", "", "AI brief"],
    ["\uD83E\uDDE9", "dash-icon research-icon-themes", "", "Theme group"],
    ["\uD83E\uDDEA", "dash-icon research-icon-signal-lab dash-tone-info", "", "Signal lab"],
    ["\uD83E\uDDED", "dash-icon dash-icon-compass dash-tone-info", "", "Sector rotation"],
    ["\uD83E\uDDFA", "dash-icon submenu-icon-baskets", "", "Thematic basket"],
    ["\uD83D\uDE80", "dash-icon research-icon-impulse dash-tone-up", "", "Aggressive"],
    ["\uD83D\uDEA6", "dash-icon submenu-icon-stage dash-tone-warn", "", "Gate"],
    ["\u2696\uFE0F", "dash-icon dash-icon-balance", "", "Balanced"],
    ["\u2696", "dash-icon dash-icon-balance", "", "Balanced"],
    ["\uD83C\uDF2B\uFE0F", "dash-icon research-icon-macro-weather dash-tone-muted", "", "Mixed"],
    ["\uD83C\uDF2B", "dash-icon research-icon-macro-weather dash-tone-muted", "", "Mixed"],
    ["\uD83D\uDFE2", "dash-icon dash-icon-dot dash-tone-up", "", "Positive"],
    ["\uD83D\uDD35", "dash-icon dash-icon-dot dash-tone-info", "", "Nearly ready"],
    ["\uD83D\uDFE0", "dash-icon dash-icon-dot dash-tone-warn", "", "Caution"],
    ["\uD83D\uDFE1", "dash-icon dash-icon-dot dash-tone-warn", "", "Setting up"],
    ["\uD83D\uDD34", "dash-icon dash-icon-dot dash-tone-down", "", "Negative"],
    ["\u26AA", "dash-icon dash-icon-dot dash-tone-muted", "", "Neutral"],
    ["\u25D0", "dash-icon dash-icon-dot dash-tone-muted", "", "Neutral"]
  ];

  var lookup = Object.create(null);
  specs.forEach(function (spec) { lookup[spec[0]] = spec; });
  var keys = specs.map(function (spec) { return spec[0]; }).sort(function (a, b) {
    return b.length - a.length;
  });
  var tokenRe = new RegExp(keys.map(function (key) {
    return key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("|"), "g");
  var blocked = /^(SCRIPT|STYLE|TEXTAREA|CODE|PRE|OPTION|SELECT|SVG)$/;
  var attrNames = ["data-tip-en", "data-tip-zh", "title"];

  function makeIcon(token) {
    var spec = lookup[token];
    var icon = document.createElement("span");
    icon.className = spec[1];
    icon.setAttribute("aria-hidden", "true");
    if (spec[2]) icon.setAttribute("data-code", spec[2]);
    return icon;
  }

  function labelText(value) {
    tokenRe.lastIndex = 0;
    return value.replace(tokenRe, function (token) {
      var label = lookup[token][3];
      return label ? label + " " : "";
    }).replace(/\s{2,}/g, " ").trim();
  }

  function decorateText(node) {
    var parent = node.parentElement;
    if (!parent || blocked.test(parent.tagName) || parent.closest(".dash-icon,.dash-flag")) return;
    var value = node.nodeValue || "";
    tokenRe.lastIndex = 0;
    if (!tokenRe.test(value)) return;
    tokenRe.lastIndex = 0;
    var frag = document.createDocumentFragment();
    var last = 0;
    value.replace(tokenRe, function (token, offset) {
      if (offset > last) frag.appendChild(document.createTextNode(value.slice(last, offset)));
      frag.appendChild(makeIcon(token));
      last = offset + token.length;
      return token;
    });
    if (last < value.length) frag.appendChild(document.createTextNode(value.slice(last)));

    var control = parent.closest("button,a");
    if (control && !control.getAttribute("aria-label") && labelText(value) === lookup[value.trim()]?.[3]) {
      control.setAttribute("aria-label", lookup[value.trim()][3]);
    }
    node.replaceWith(frag);
  }

  function decorate(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      decorateText(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE || blocked.test(root.tagName)) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(decorateText);
    root.querySelectorAll(attrNames.map(function (name) { return "[" + name + "]"; }).join(",")).forEach(function (el) {
      attrNames.forEach(function (name) {
        var value = el.getAttribute(name);
        if (value) el.setAttribute(name, labelText(value));
      });
    });
  }

  function start() {
    decorate(document.body);
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        if (record.type === "characterData") decorateText(record.target);
        record.addedNodes.forEach(decorate);
      });
    }).observe(document.body, { childList: true, characterData: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
}());

/* Canada Stock Dashboard V3.6 progressive composer. Strict no-op elsewhere.
   The asset is entitled-only (401 anonymous, served no-store), and the gate
   consults the auth backend per request — a transient 401/503 there used to
   strand an ENTITLED visitor on the legacy page until a manual reload
   (observed twice in the 2026-08-25 production acceptance). Bounded backoff
   retries cover that window; anonymous visitors still fail every attempt
   quietly and keep the designed legacy fallback. */
(function () {
  "use strict";
  if (!/(^|\/)canada_stocks\.html$/.test(location.pathname)) return;
  if (window.__mmCanadaStockV36Loader) return;
  window.__mmCanadaStockV36Loader = true;
  var attempt = 0;
  function inject() {
    attempt += 1;
    var script = document.createElement("script");
    script.src = "canada-stock-v36.js?v=20260823";
    script.async = false;
    script.onerror = function () {
      if (script.parentNode) script.parentNode.removeChild(script);
      if (attempt < 3 && !window.__mmCanadaStockV36) setTimeout(inject, 1500 * attempt);
    };
    (document.head || document.documentElement).appendChild(script);
  }
  inject();
}());

/* HK Stock Dashboard V3.7 follower composer. Strict no-op elsewhere. Same
   entitled-only, bounded-backoff retry shape as the Canada loader above
   (SOL-HK-V37-FOLLOWER architecture, research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md) —
   own IIFE guard flag, own retry guard on the composer's own idempotency flag,
   never shares state with the Canada loader. */
(function () {
  "use strict";
  if (!/(^|\/)hk_stocks\.html$/.test(location.pathname)) return;
  if (window.__mmHKStockV36Loader) return;
  window.__mmHKStockV36Loader = true;
  var attempt = 0;
  function inject() {
    attempt += 1;
    var script = document.createElement("script");
    script.src = "hk-stock-v36.js?v=20260825";
    script.async = false;
    script.onerror = function () {
      if (script.parentNode) script.parentNode.removeChild(script);
      if (attempt < 3 && !window.__mmHKStockV36) setTimeout(inject, 1500 * attempt);
    };
    (document.head || document.documentElement).appendChild(script);
  }
  inject();
}());

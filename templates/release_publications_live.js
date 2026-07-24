/* Progressive enhancement for Release Radar publication status.
 *
 * Polls the VPS-owned, display-only publication sidecar. It never changes the
 * nightly forecast, scorecard, or actual-value ledger.
 */
(function () {
  "use strict";
  if (window.__mmReleasePublicationLive) return;
  window.__mmReleasePublicationLive = true;

  var URL = "live/release_publications.json";
  var POLL_MS = 60000;
  var timer = null;

  function ensureBanner() {
    var panel = document.getElementById("release-radar") || document.getElementById("rr-inline");
    if (!panel) return null;
    var banner = document.getElementById("rr-live-publication");
    if (banner) return banner;
    banner = document.createElement("div");
    banner.id = "rr-live-publication";
    banner.hidden = true;
    banner.style.cssText =
      "margin:0 0 10px;padding:8px 10px;border:1px solid var(--line);" +
      "border-radius:9px;background:var(--panel2);font-size:11px;line-height:1.45";
    var anchor = panel.querySelector(".rr-subline");
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(banner, anchor.nextSibling);
    else panel.insertBefore(banner, panel.firstChild);
    return banner;
  }

  function render(payload) {
    var banner = ensureBanner();
    if (!banner) return;
    var today = new Date().toISOString().slice(0, 10);
    var pubs = (payload.publications || []).filter(function (row) {
      return row.date === today && row.status === "published";
    });
    var due = (payload.due || []).filter(function (row) { return row.date === today; });
    banner.textContent = "";
    if (pubs.length) {
      var strong = document.createElement("strong");
      strong.textContent = "Official publication detected · 官方数据已发布";
      banner.appendChild(strong);
      var detail = document.createElement("span");
      detail.textContent = " — " + pubs.map(function (row) { return row.type; }).join(", ") +
        ". Live display is updating; canonical actuals reconcile nightly.";
      banner.appendChild(detail);
      banner.style.borderColor = "color-mix(in srgb, var(--up) 45%, var(--line))";
      banner.hidden = false;
    } else if (due.length) {
      banner.textContent = "Watching official source · 正在监测官方发布源 — " +
        due.map(function (row) { return row.type + " " + row.time_et + " ET"; }).join(", ");
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  }

  function poll() {
    fetch(URL, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () { /* fail-open: nightly Release Radar stays intact */ });
  }

  function start() {
    poll();
    if (!timer) timer = window.setInterval(poll, POLL_MS);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

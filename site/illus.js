/* ilx / "Signal Ink" — reveal trigger (see lib/illus.py, templates/illus.css).
   Adds .ilx-in when a figure scrolls into view so the ink draws. On exit it removes
   .ilx-in ONLY if the figure is display-hidden (its dialog closed) — so dialog charts
   replay each time they open, while in-page charts animate once and stay drawn.
   No dependencies. Reduced-motion: the class is still added; the CSS parks everything
   at its final state. */
(function () {
  "use strict";
  if (!("IntersectionObserver" in window)) {
    // No observer support — just show everything drawn.
    document.querySelectorAll(".ilx").forEach(function (el) { el.classList.add("ilx-in"); });
    return;
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      var el = e.target;
      if (e.isIntersecting) {
        el.classList.add("ilx-in");
      } else if (el.offsetParent === null) {
        // Only reset when the element is display-hidden (offsetParent null ⇒ an
        // ancestor is display:none, i.e. the dialog closed). A merely scrolled-off
        // in-page chart keeps its drawn state.
        el.classList.remove("ilx-in");
      }
    });
  }, { threshold: 0.25 });

  function mount(root) {
    (root || document).querySelectorAll(".ilx:not([data-ilx-obs])").forEach(function (el) {
      el.setAttribute("data-ilx-obs", "1");
      io.observe(el);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { mount(document); });
  } else {
    mount(document);
  }

  // Charts injected into dialogs are already in the DOM at load but hidden
  // (display:none). The observer normally adds .ilx-in the moment the dialog opens
  // (display change ⇒ intersection change) and removes it on close, so reopening
  // replays the draw. reveal() is the reliability FALLBACK the page calls after
  // opening a dialog: it only touches figures the observer did NOT handle — never
  // restarting one that is already drawing (that would flicker mid-draw).
  function reveal(root) {
    var pending = [];
    (root || document).querySelectorAll(".ilx").forEach(function (el) {
      if (el.classList.contains("ilx-in")) return; // observer got it — drawing/drawn
      io.observe(el);                              // idempotent; keeps close-reset alive
      pending.push(el);
    });
    if (!pending.length) return;
    void pending[0].offsetWidth; // reflow so the class-add lands as a fresh transition
    requestAnimationFrame(function () {
      pending.forEach(function (el) {
        if (el.offsetParent !== null) { el.classList.add("ilx-in"); }
      });
    });
  }

  window.ilxMount = mount;
  window.ilxReveal = reveal;
})();

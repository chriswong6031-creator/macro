/* ==========================================================================
   GREY DEER CAPITAL — main.js
   Owns the shared chrome (nav + footer as injected components), scroll
   choreography, reveal-on-scroll, mobile menu, process cycle, and the
   inquiry form. Single source of truth: every page ships identical chrome.
   ========================================================================== */
(function () {
  "use strict";

  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* --- the antler mark, inline so chrome paints without an extra request --- */
  function mark(id) {
    return (
      '<svg class="brand__mark" viewBox="0 0 64 64" fill="none" aria-hidden="true">' +
      '<defs><linearGradient id="' + id + '" x1="32" y1="56" x2="32" y2="8" gradientUnits="userSpaceOnUse">' +
      '<stop offset="0" stop-color="#B8A283"/><stop offset=".45" stop-color="#D8C7AE"/>' +
      '<stop offset=".78" stop-color="#9BD8D0"/><stop offset="1" stop-color="#63B4AC"/></linearGradient></defs>' +
      '<g stroke="url(#' + id + ')" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M32 53 C31 44 28 37 22.5 30 C19 25.5 16.5 20 15 12.5"/>' +
      '<path d="M24.6 33 C21 31 17.5 30 12.5 29"/>' +
      '<path d="M19 23.2 C16.5 20 15 16.5 13.8 11.5"/>' +
      '<path d="M32 53 L32 33 C32 27 32 21 32 13.5"/>' +
      '<path d="M32 53 C33 44 36 37 41.5 30 C45 25.5 47.5 20 49 12.5"/>' +
      '<path d="M39.4 33 C43 31 46.5 30 51.5 29"/>' +
      '<path d="M45 23.2 C47.5 20 49 16.5 50.2 11.5"/></g>' +
      '<g fill="#9BD8D0"><circle cx="15" cy="12.5" r="1.7"/><circle cx="49" cy="12.5" r="1.7"/>' +
      '<circle cx="32" cy="13.5" r="1.7"/></g><circle cx="32" cy="54.6" r="2.1" fill="#C7B299"/></svg>'
    );
  }

  var LINKS = [
    { href: "index.html",        label: "Home",         page: "home" },
    { href: "approach.html",     label: "Approach",     page: "approach" },
    { href: "capabilities.html", label: "Capabilities", page: "capabilities" },
    { href: "research.html",     label: "Research",     page: "research" },
    { href: "about.html",        label: "About",        page: "about" },
    { href: "contact.html",      label: "Contact",      page: "contact" }
  ];

  function brand() {
    return (
      '<a class="brand" href="index.html" aria-label="Grey Deer Capital — home">' +
      mark("navAntler") +
      '<span class="brand__word"><b>Grey Deer</b> Capital' +
      '<span class="brand__sub">Active Investment Management</span></span></a>'
    );
  }

  function buildNav(current) {
    var items = LINKS.map(function (l) {
      var cur = l.page === current ? ' aria-current="page"' : "";
      return '<li><a href="' + l.href + '"' + cur + ">" + l.label + "</a></li>";
    }).join("");
    return (
      '<nav class="gd-nav" aria-label="Primary">' +
        '<div class="gd-nav__inner">' +
          brand() +
          '<ul class="nav-links" id="nav-links">' + items +
            '<li class="mobile-cta"><a class="btn btn--primary" href="contact.html">Request an introduction ' +
            '<span class="btn__arrow">&#8594;</span></a></li>' +
          "</ul>" +
          '<div class="nav-right">' +
            '<a class="btn btn--ghost nav-cta-desktop" href="contact.html">Inquire</a>' +
            '<button class="nav-toggle" aria-label="Menu" aria-expanded="false" aria-controls="nav-links"><span></span></button>' +
          "</div>" +
        "</div>" +
      "</nav>"
    );
  }

  function buildFooter() {
    var year = new Date().getFullYear();
    return (
      '<div class="container">' +
        '<div class="gd-footer__top">' +
          '<div class="gd-footer__brand">' + brand() +
            "<p>An active investment firm reading market regimes, capital flows, and rotation — " +
            "where signal-based intelligence meets disciplined human judgment.</p></div>" +
          '<div class="fcol"><h4>Firm</h4><ul>' +
            '<li><a href="approach.html">Approach</a></li>' +
            '<li><a href="capabilities.html">Capabilities</a></li>' +
            '<li><a href="research.html">Research &amp; Insights</a></li>' +
            '<li><a href="about.html">About</a></li></ul></div>' +
          '<div class="fcol"><h4>Capabilities</h4><ul>' +
            '<li><a href="capabilities.html#private-capital">Private Capital Management</a></li>' +
            '<li><a href="capabilities.html#institutional-research">Institutional Research</a></li>' +
            '<li><a href="capabilities.html#signal-research">AI Quant Signals</a></li>' +
            '<li><a href="capabilities.html#regime-research">Cycle &amp; Regime Research</a></li>' +
            '<li><a href="capabilities.html#rotation">Rotation &amp; Allocation</a></li></ul></div>' +
          '<div class="fcol"><h4>Connect</h4><ul>' +
            '<li><a href="contact.html">Contact &amp; inquiry</a></li>' +
            '<li><a href="https://mastermind-x.com" rel="noopener">mastermind&#8209;x.com &#8599;</a></li>' +
            '<li><a href="https://client.greydeercapital.com" rel="noopener">Client portal</a></li>' +
            '<li><a href="mailto:inquiries@greydeercapital.com">inquiries@greydeercapital.com</a></li></ul></div>' +
        "</div>" +
        '<div class="gd-footer__disc">' +
          "<p><strong style=\"color:var(--fog)\">Disclosures.</strong> Grey Deer Capital LLC is an active investment management firm. " +
          "The material on this website is provided for informational purposes only and does not constitute investment advice, " +
          "a recommendation, or an offer or solicitation to buy or sell any security or to participate in any investment strategy. " +
          "Nothing herein is tailored to the investment objectives of any specific person.</p>" +
          "<p>Investing involves risk, including the possible loss of principal. Past performance is not indicative of future results. " +
          "Any strategies, signals, models, or research described are illustrative of the firm's process and are subject to change without notice. " +
          "Certain services are available only to accredited investors, qualified purchasers, and institutional clients where appropriate and permitted by law. " +
          "This site does not constitute an offer in any jurisdiction where such an offer would be unlawful.</p>" +
        "</div>" +
        '<div class="gd-footer__bar">' +
          "<small>&copy; " + year + " Grey Deer Capital LLC. All rights reserved.</small>" +
          '<nav class="gd-footer__legal" aria-label="Legal">' +
            '<a href="legal.html#privacy">Privacy</a>' +
            '<a href="legal.html#terms">Terms</a>' +
            '<a href="legal.html#disclosures">Disclosures</a>' +
            '<a href="legal.html#form-adv">Form ADV</a>' +
          "</nav>" +
        "</div>" +
      "</div>"
    );
  }

  /* --- inject chrome ---------------------------------------------------- */
  function injectChrome() {
    var current = document.body.getAttribute("data-page") || "";
    var navRoot = document.getElementById("nav-root");
    var ftRoot = document.getElementById("footer-root");
    if (navRoot) navRoot.innerHTML = buildNav(current);
    if (ftRoot) { ftRoot.className = "gd-footer"; ftRoot.innerHTML = buildFooter(); }
    wireNav();
  }

  function wireNav() {
    var nav = document.querySelector(".gd-nav");
    var toggle = document.querySelector(".nav-toggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var open = document.body.classList.toggle("menu-open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
      document.querySelectorAll(".nav-links a").forEach(function (a) {
        a.addEventListener("click", function () {
          document.body.classList.remove("menu-open");
          toggle.setAttribute("aria-expanded", "false");
        });
      });
    }
    // stuck state
    if (nav) {
      var onScroll = function () {
        nav.classList.toggle("is-stuck", window.scrollY > 24);
      };
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    }
  }

  /* --- reveal on scroll ------------------------------------------------- */
  function initReveal() {
    var els = document.querySelectorAll("[data-reveal]");
    if (reduce || !("IntersectionObserver" in window)) {
      els.forEach(function (el) { el.classList.add("is-in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          var el = e.target;
          var d = el.getAttribute("data-reveal-delay");
          if (d) el.style.setProperty("--reveal-delay", d + "ms");
          el.classList.add("is-in");
          io.unobserve(el);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* --- process cycle: sync the orbit ring with the active step --------- */
  function initOrbit() {
    var orbit = document.querySelector("[data-orbit]");
    if (!orbit) return;
    var steps = Array.prototype.slice.call(orbit.querySelectorAll(".orbit-step"));
    var dots = Array.prototype.slice.call(document.querySelectorAll("[data-orbit-dot]"));
    var ring = document.querySelector("[data-orbit-ring]");
    var n = steps.length, active = 0, timer = null;

    function setActive(i) {
      active = (i + n) % n;
      steps.forEach(function (s, k) { s.classList.toggle("is-active", k === active); });
      dots.forEach(function (d, k) { d.classList.toggle("is-active", k === active); });
      if (ring) {
        var frac = active / n;
        var C = 2 * Math.PI * 46;
        ring.style.strokeDasharray = (C * 0.16) + " " + C;
        ring.style.strokeDashoffset = (-C * frac) + "";
      }
    }
    function cycle() { timer = setTimeout(function () { setActive(active + 1); cycle(); }, 2600); }

    steps.forEach(function (s, k) {
      s.addEventListener("mouseenter", function () { clearTimeout(timer); setActive(k); });
      s.addEventListener("mouseleave", function () { if (!reduce) cycle(); });
      s.addEventListener("focusin", function () { clearTimeout(timer); setActive(k); });
    });
    setActive(0);
    if (!reduce) cycle();
  }

  /* --- research filter -------------------------------------------------- */
  function initFilter() {
    var bar = document.querySelector("[data-filter]");
    if (!bar) return;
    var cards = Array.prototype.slice.call(document.querySelectorAll("[data-cat]"));
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      bar.querySelectorAll("button").forEach(function (x) { x.classList.remove("is-active"); });
      b.classList.add("is-active");
      var f = b.getAttribute("data-f");
      cards.forEach(function (c) {
        var show = f === "all" || c.getAttribute("data-cat") === f;
        c.style.display = show ? "" : "none";
      });
    });
  }

  /* --- inquiry form (client-side; no data leaves the browser) ---------- */
  function initForm() {
    var form = document.querySelector("[data-inquiry]");
    if (!form) return;
    var ok = form.querySelector(".form__ok");
    var err = form.querySelector(".form__err");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (err) err.style.display = "none";
      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }
      var btn = form.querySelector("[type=submit]");
      if (btn) { btn.disabled = true; btn.textContent = "Sending…"; }
      // Placeholder: wire to greydeercapital.com intake endpoint or CRM.
      setTimeout(function () {
        form.querySelectorAll("input, select, textarea").forEach(function (f) {
          if (f.type !== "submit" && f.type !== "checkbox") f.value = "";
        });
        if (btn) { btn.disabled = false; btn.innerHTML = 'Submit inquiry <span class="btn__arrow">&#8594;</span>'; }
        if (ok) { ok.style.display = "block"; ok.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" }); }
      }, 850);
    });
  }

  /* --- ambient concept ticker (hero marquee content) ------------------- */
  function initYearBits() {
    document.querySelectorAll("[data-year]").forEach(function (el) {
      el.textContent = new Date().getFullYear();
    });
  }

  function boot() {
    injectChrome();
    initReveal();
    initOrbit();
    initFilter();
    initForm();
    initYearBits();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else { boot(); }
})();

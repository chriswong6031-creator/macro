/* White House alert ticker — a Wall-Street-style scrolling tape pinned to the top
   of every page. Fully client-side and self-contained: it fetches wh_banner.json,
   and if there is a live (non-expired) alert it injects a glassy, continuously
   scrolling ticker showing the alert headline + the names most exposed (with their
   recent move). Click → the White House Watch report. Dismissible per alert-set.

   Degrade-silent: no file, no alerts, or any error → nothing renders. The page is
   never blocked (loaded `defer`), and all model-derived text is written via
   textContent (never innerHTML) so a headline can never inject markup.

   The injector sets data-root on this script tag to the site-root-relative prefix
   ("" at root, "../" one level deep) so fetch + links resolve from any page depth. */
(function () {
  "use strict";
  function boot() {
    var self =
      document.currentScript ||
      document.querySelector("script[data-whb]") ||
      (function () {
        var s = document.getElementsByTagName("script");
        for (var i = s.length - 1; i >= 0; i--) {
          if ((s[i].src || "").indexOf("wh_banner.js") !== -1) return s[i];
        }
        return null;
      })();
    var root = (self && self.getAttribute("data-root")) || "";
    if (root && root.slice(-1) !== "/") root += "/";

    fetch(root + "wh_banner.json", { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) { render(data, root); })
      .catch(function () {});
  }

  function render(data, root) {
    if (!data || !Array.isArray(data.alerts) || !data.alerts.length) return;
    var now = Date.now();
    var alerts = data.alerts.filter(function (a) {
      if (!a || !a.title) return false;
      var exp = a.expires_at ? Date.parse(a.expires_at) : NaN;
      return isNaN(exp) || now < exp; // defensive: server already prunes expired
    });
    if (!alerts.length) return;

    // Monotonic dismissal: remember the SET of dismissed ids and stay hidden only while
    // EVERY currently-live alert was already dismissed. A genuinely NEW alert re-opens the
    // bar; an unrelated alert merely EXPIRING (which shrinks the live set) must NOT.
    var dismissed = {};
    try {
      (localStorage.getItem("whb_dismissed") || "").split("|").forEach(function (id) {
        if (id) dismissed[id] = 1;
      });
    } catch (e) {}
    if (alerts.every(function (a) { return dismissed[a.id]; })) return;

    injectStyle();
    var reduce =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    var bar = el("div", "whb");
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "White House market alert");

    // pinned "breaking" label (does not scroll)
    var label = el("a", "whb-label");
    label.href = root + "whitehouse.html";
    label.appendChild(el("span", "whb-dot"));
    label.appendChild(txt("span", "whb-label-tx", "WHITE HOUSE ALERT"));
    bar.appendChild(label);

    var view = el("div", "whb-view");
    var track = el("div", "whb-track" + (reduce ? " whb-static" : ""));
    var run = buildRun(alerts, root);
    track.appendChild(run);
    if (!reduce) track.appendChild(buildRun(alerts, root)); // 2nd copy → seamless loop
    view.appendChild(track);
    bar.appendChild(view);

    var close = txt("button", "whb-x", "×");
    close.setAttribute("aria-label", "Dismiss");
    close.addEventListener("click", function (ev) {
      ev.stopPropagation();
      try {
        alerts.forEach(function (a) { dismissed[a.id] = 1; });
        localStorage.setItem("whb_dismissed", Object.keys(dismissed).sort().join("|"));
      } catch (e) {}
      bar.parentNode && bar.parentNode.removeChild(bar);
      document.documentElement.classList.remove("whb-on");
    });
    bar.appendChild(close);

    document.body.insertBefore(bar, document.body.firstChild);
    document.documentElement.classList.add("whb-on");

    // Scale scroll DURATION to content width so reading pace (~px/sec) stays constant
    // whether one alert or six are live — a fixed duration blurs a long tape past too fast.
    if (!reduce) {
      var firstRun = track.querySelector(".whb-run");
      var w = firstRun ? firstRun.getBoundingClientRect().width : 0;
      if (w > 0) track.style.animationDuration = Math.max(30, Math.round(w / 80)) + "s";
    }
  }

  // one pass of the tape: every alert as a clickable segment
  function buildRun(alerts, root) {
    var run = el("div", "whb-run");
    alerts.forEach(function (a, i) {
      var seg = el("a", "whb-seg");
      seg.href = root + "whitehouse.html#" + encodeURIComponent(a.id || "");
      seg.appendChild(el("span", "whb-pipe whb-tone-" + (a.tone || "neutral")));
      // bilingual title — the site's EN/中文 toggle flips html[data-lang]; the banner
      // carries its own whb-en/whb-zh display rules so it works on any page.
      var ttl = el("span", "whb-ttl");
      ttl.appendChild(txt("span", "whb-en", a.title));
      ttl.appendChild(txt("span", "whb-zh", a.title_zh || a.title));
      seg.appendChild(ttl);
      (a.tickers || []).slice(0, 6).forEach(function (t) {
        if (!t || !t.symbol) return;
        var chip = el("span", "whb-chip");
        chip.appendChild(
          txt("span", "whb-sym", t.symbol + (t.direction === "hurt" ? " ▾" : " ▴"))
        );
        if (t.chg_pct !== null && t.chg_pct !== undefined && !isNaN(t.chg_pct)) {
          var up = Number(t.chg_pct) >= 0;
          chip.appendChild(
            txt(
              "span",
              "whb-chg " + (up ? "up" : "dn"),
              (up ? "+" : "") + Number(t.chg_pct).toFixed(2) + "%"
            )
          );
        }
        seg.appendChild(chip);
      });
      run.appendChild(seg);
      if (i < alerts.length - 1) run.appendChild(txt("span", "whb-div", "◆"));
    });
    return run;
  }

  // --- tiny DOM helpers (textContent only — never innerHTML) ---
  function el(tag, cls) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  }
  function txt(tag, cls, text) {
    var n = el(tag, cls);
    n.textContent = text == null ? "" : String(text);
    return n;
  }

  function injectStyle() {
    if (document.getElementById("whb-style")) return;
    var css = [
      ".whb-on .whb{--whb-h:42px}",
      ".whb{position:relative;z-index:60;display:flex;align-items:stretch;height:42px;",
      "background:linear-gradient(90deg,rgba(20,30,55,.96),rgba(34,20,30,.96));",
      "color:#f4f6fb;border-bottom:1px solid rgba(255,255,255,.10);",
      "box-shadow:0 2px 14px rgba(0,0,0,.28);font:13px/1.4 -apple-system,'Segoe UI',Roboto,Helvetica,sans-serif;",
      "-webkit-backdrop-filter:saturate(1.3) blur(2px);backdrop-filter:saturate(1.3) blur(2px);overflow:hidden}",
      ".whb::before{content:'';position:absolute;left:0;right:0;top:0;height:2px;",
      "background:linear-gradient(90deg,#3d6fd6,#d9a441 50%,#d2455c)}",
      // breaking label
      ".whb-label{flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:0 16px;",
      "background:linear-gradient(90deg,#b8253c,#8f1d30);color:#fff;font-weight:800;",
      "letter-spacing:.07em;font-size:11px;text-transform:uppercase;text-decoration:none;",
      "box-shadow:6px 0 14px rgba(0,0,0,.30);position:relative;z-index:2;white-space:nowrap}",
      ".whb-label-tx{white-space:nowrap}",
      "@media(max-width:560px){.whb-label-tx{display:none}.whb-label{padding:0 12px}}",
      ".whb-dot{width:8px;height:8px;border-radius:50%;background:#ffd9d9;",
      "box-shadow:0 0 0 0 rgba(255,180,180,.8);animation:whb-pulse 1.6s infinite}",
      "@keyframes whb-pulse{0%{box-shadow:0 0 0 0 rgba(255,170,170,.7)}",
      "70%{box-shadow:0 0 0 8px rgba(255,170,170,0)}100%{box-shadow:0 0 0 0 rgba(255,170,170,0)}}",
      // scrolling viewport
      ".whb-view{flex:1 1 auto;overflow:hidden;position:relative;display:flex;align-items:center;",
      "-webkit-mask-image:linear-gradient(90deg,transparent,#000 28px,#000 calc(100% - 40px),transparent);",
      "mask-image:linear-gradient(90deg,transparent,#000 28px,#000 calc(100% - 40px),transparent)}",
      ".whb-track{display:flex;align-items:center;white-space:nowrap;will-change:transform;",
      "animation:whb-scroll 46s linear infinite}",
      ".whb-static{animation:none;overflow-x:auto;scrollbar-width:none}",
      ".whb-static::-webkit-scrollbar{display:none}",
      ".whb:hover .whb-track{animation-play-state:paused}",
      "@keyframes whb-scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}",
      ".whb-run{display:flex;align-items:center}",
      ".whb-seg{display:inline-flex;align-items:center;gap:10px;padding:0 20px;text-decoration:none;color:#eef1f8}",
      ".whb-seg:hover .whb-ttl{text-decoration:underline}",
      ".whb-pipe{width:3px;height:18px;border-radius:2px;background:#9aa4bf;flex:0 0 auto}",
      ".whb-tone-tailwind{background:#39c07d}.whb-tone-headwind{background:#ef5b6b}",
      ".whb-tone-mixed{background:#e3b341}.whb-tone-neutral{background:#9aa4bf}",
      ".whb-ttl{font-weight:650;color:#fff;letter-spacing:.01em}",
      // self-contained EN/中文 toggle (does not depend on the host page's theme.css)
      ".whb-zh{display:none}",
      'html[data-lang="zh"] .whb-en{display:none}',
      'html[data-lang="zh"] .whb-zh{display:inline}',
      ".whb-chip{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:7px;",
      "background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.10)}",
      ".whb-sym{font-weight:700;font-variant-numeric:tabular-nums;font-size:12px;color:#dfe5f2;letter-spacing:.02em}",
      ".whb-chg{font-variant-numeric:tabular-nums;font-size:11.5px;font-weight:700}",
      ".whb-chg.up{color:#54d495}.whb-chg.dn{color:#ff7a86}",
      ".whb-div{color:rgba(255,255,255,.28);padding:0 6px;font-size:9px}",
      ".whb-x{flex:0 0 auto;background:transparent;border:0;color:rgba(255,255,255,.6);",
      "font-size:21px;line-height:1;padding:0 14px;cursor:pointer;align-self:center}",
      ".whb-x:hover{color:#fff}",
      "@media print{.whb{display:none}}",
    ].join("");
    var st = document.createElement("style");
    st.id = "whb-style";
    st.textContent = css;
    document.head.appendChild(st);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

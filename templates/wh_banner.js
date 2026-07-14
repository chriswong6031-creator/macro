/* Market alert ticker — a Wall-Street-style scrolling tape pinned to the top of
   every page. Fully client-side and self-contained. It hosts TWO channels:

     • WHITE HOUSE ALERT (blue/red)  — fetched from wh_banner.json
         (built by scripts/build_whitehouse.py from the WH RSS + LLM brain).
     • RISK RADAR ALERT (orange)     — fetched from rr_banner.json
         (built by scripts/build_rr_banner.py; fires only at the radar's EXTREME,
          gate-confirmed "risk-off" band — the get-out-now tier, not every reading).

   When only one channel is live it renders exactly like a single tape. When BOTH
   are live the one 42px bar ALTERNATES between them — crossfading every ~9s, label
   + top-accent swapping with the active channel (pauses on hover).

   Degrade-silent: no file, no alerts, or any error → nothing renders. The page is
   never blocked (loaded `defer`), and all model-derived text is written via
   textContent (never innerHTML) so a headline can never inject markup.

   The injector sets data-root on this script tag to the site-root-relative prefix
   ("" at root, "../" one level deep) so fetch + links resolve from any page depth. */
(function () {
  "use strict";

  var ALT_MS = 9000; // dwell time per channel when both are live

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

    Promise.all([
      getJSON(root + "wh_banner.json"),
      getJSON(root + "rr_banner.json"),
    ]).then(function (res) {
      render(res[0], res[1], root);
    });
  }

  function getJSON(url) {
    return fetch(url, { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  function render(whData, rrData, root) {
    var reduce =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Build the candidate channels, each already filtered by its own dismissal.
    var channels = [];
    var wh = whChannel(whData, root, reduce);
    if (wh) channels.push(wh);
    var rr = rrChannel(rrData, root, reduce);
    if (rr) channels.push(rr);
    if (!channels.length) return;

    injectStyle();

    var bar = el("div", "whb");
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "Market alert");

    var stage = el("div", "whb-stage" + (channels.length > 1 ? " multi" : ""));
    var faces = channels.map(function (c) {
      var face = el("div", "whb-face whb-face-" + c.kind);
      face.appendChild(c.label);
      face.appendChild(c.view);
      stage.appendChild(face);
      return face;
    });
    bar.appendChild(stage);

    // One shared dismiss button — hides the whole bar and records every currently
    // live alert-id under its channel's key, so a genuinely NEW alert (or a new
    // radar state) re-opens the bar, but an old one merely expiring does not.
    var close = txt("button", "whb-x", "×");
    close.setAttribute("aria-label", "Dismiss");
    close.addEventListener("click", function (ev) {
      ev.stopPropagation();
      channels.forEach(function (c) { c.dismiss(); });
      bar.parentNode && bar.parentNode.removeChild(bar);
      document.documentElement.classList.remove("whb-on");
      if (close._whbResize) window.removeEventListener("resize", close._whbResize);
      if (bar._whbTimer) clearInterval(bar._whbTimer);
    });
    bar.appendChild(close);

    document.body.insertBefore(bar, document.body.firstChild);
    document.documentElement.classList.add("whb-on");

    // apply the first (or only) channel's accent, then start alternation if needed
    applyAccent(bar, channels[0]);
    faces[0].classList.add("is-active");
    if (channels.length > 1 && !reduce) startAlternation(bar, faces, channels);

    fullBleed(bar, close);
    scaleDurations(bar, reduce);
  }

  // ---------------------------------------------------------------------------
  // WHITE HOUSE channel — unchanged behaviour: a tape of the live WH alerts.
  // ---------------------------------------------------------------------------
  function whChannel(data, root, reduce) {
    if (!data || !Array.isArray(data.alerts) || !data.alerts.length) return null;
    var now = Date.now();
    var alerts = data.alerts.filter(function (a) {
      if (!a || !a.title) return false;
      var exp = a.expires_at ? Date.parse(a.expires_at) : NaN;
      return isNaN(exp) || now < exp; // defensive: server already prunes expired
    });
    if (!alerts.length) return null;

    // Monotonic dismissal: stay hidden only while EVERY currently-live alert was
    // already dismissed. A NEW alert re-opens; an old one expiring must not.
    var dismissed = readDismissed("whb_dismissed");
    if (alerts.every(function (a) { return dismissed[a.id]; })) return null;

    var label = el("a", "whb-label whb-label-wh");
    label.href = root + "whitehouse.html";
    label.appendChild(el("span", "whb-dot"));
    var lt = el("span", "whb-label-tx");
    lt.appendChild(txt("span", "whb-en", "WHITE HOUSE ALERT"));
    lt.appendChild(txt("span", "whb-zh", "白宫警报"));
    label.appendChild(lt);

    var view = el("div", "whb-view");
    var track = el("div", "whb-track" + (reduce ? " whb-static" : ""));
    track.appendChild(buildWhRun(alerts, root));
    if (!reduce) track.appendChild(buildWhRun(alerts, root)); // 2nd copy → seamless
    view.appendChild(track);

    return {
      kind: "wh",
      label: label,
      view: view,
      top: "linear-gradient(90deg,#3d6fd6,#d9a441 50%,#d2455c)",
      dismiss: function () {
        try {
          alerts.forEach(function (a) { dismissed[a.id] = 1; });
          localStorage.setItem(
            "whb_dismissed", Object.keys(dismissed).sort().join("|"));
        } catch (e) {}
      },
    };
  }

  // one pass of the WH tape: every alert as a clickable segment
  function buildWhRun(alerts, root) {
    var run = el("div", "whb-run");
    alerts.forEach(function (a, i) {
      var seg = el("a", "whb-seg");
      seg.href = root + "whitehouse.html#" + encodeURIComponent(a.id || "");
      seg.appendChild(el("span", "whb-pipe whb-tone-" + (a.tone || "neutral")));
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
            txt("span", "whb-chg " + (up ? "up" : "dn"),
              (up ? "+" : "") + Number(t.chg_pct).toFixed(2) + "%")
          );
        }
        seg.appendChild(chip);
      });
      run.appendChild(seg);
      if (i < alerts.length - 1) run.appendChild(txt("span", "whb-div", "◆"));
    });
    return run;
  }

  // ---------------------------------------------------------------------------
  // RISK RADAR channel — orange "get out" tape flashing WHY it amplified, how far
  // the market is projected to fall, and the odds (mirrors the Risk Radar card).
  // ---------------------------------------------------------------------------
  function rrChannel(data, root, reduce) {
    var a = data && data.alert;
    if (!a || !a.headline_en) return null;

    var dismissed = readDismissed("rrb_dismissed");
    if (a.id && dismissed[a.id]) return null;

    var label = el("a", "whb-label whb-label-rr");
    label.href = root + (a.href || "macro.html");
    label.appendChild(el("span", "whb-dot"));
    var lt = el("span", "whb-label-tx");
    lt.appendChild(txt("span", "whb-en", "RISK RADAR ALERT"));
    lt.appendChild(txt("span", "whb-zh", "风险雷达警报"));
    label.appendChild(lt);

    var view = el("div", "whb-view");
    var track = el("div", "whb-track" + (reduce ? " whb-static" : ""));
    track.appendChild(buildRrRun(a, root));
    if (!reduce) track.appendChild(buildRrRun(a, root)); // 2nd copy → seamless
    view.appendChild(track);

    return {
      kind: "rr",
      label: label,
      view: view,
      top: "linear-gradient(90deg,#f4b13a,#ec7a1e 55%,#d2455c)",
      warm: true, // warms the bar background while this channel is showing
      dismiss: function () {
        try {
          if (a.id) dismissed[a.id] = 1;
          localStorage.setItem(
            "rrb_dismissed", Object.keys(dismissed).sort().join("|"));
        } catch (e) {}
      },
    };
  }

  // one pass of the Risk-Radar tape: headline · why amplified · projected fall + odds
  function buildRrRun(a, root) {
    var run = el("div", "whb-run");
    var href = root + (a.href || "macro.html");

    // 1 — headline: dominant scare + score
    var s1 = el("a", "whb-seg");
    s1.href = href;
    s1.appendChild(el("span", "whb-pipe whb-tone-danger"));
    var ttl = el("span", "whb-ttl");
    ttl.appendChild(txt("span", "whb-en", "🛑 " + a.headline_en));
    ttl.appendChild(txt("span", "whb-zh", "🛑 " + (a.headline_zh || a.headline_en)));
    s1.appendChild(ttl);
    if (a.score != null) {
      var sc = el("span", "whb-chip");
      sc.appendChild(txt("span", "whb-sym", a.score + "/100"));
      s1.appendChild(sc);
    }
    run.appendChild(s1);
    run.appendChild(txt("span", "whb-div", "◆"));

    // 2 — WHY it was amplified: leading legs + co-firing threats + conjunction
    var s2 = el("a", "whb-seg");
    s2.href = href;
    s2.appendChild(rrTag("WHY AMPLIFIED", "为何放大"));
    (a.reasons || []).forEach(function (r) {
      var chip = el("span", "whb-chip");
      chip.appendChild(biTxt("whb-sym", r.en, r.zh));
      if (r.pctile != null) {
        chip.appendChild(txt("span", "whb-rr-p",
          r.pctile + "th" + (r.confirmed ? " ✓" : "")));
      }
      s2.appendChild(chip);
    });
    (a.amplifiers || []).forEach(function (m) {
      if (!m || !m.en) return;
      var chip = el("span", "whb-chip whb-amp");
      chip.appendChild(biTxt("whb-sym", m.en, m.zh));
      if (m.score != null) chip.appendChild(txt("span", "whb-rr-p", String(m.score)));
      s2.appendChild(chip);
    });
    if (a.conjunction_n && a.conjunction_n > 1) {
      var cj = el("span", "whb-chip whb-conj");
      cj.appendChild(biTxt("whb-sym",
        a.conjunction_n + " threats firing together",
        a.conjunction_n + " 项风险共振"));
      s2.appendChild(cj);
    }
    run.appendChild(s2);
    run.appendChild(txt("span", "whb-div", "◆"));

    // 3 — projected fall + odds (same numbers the Risk Radar card shows)
    var s3 = el("a", "whb-seg");
    s3.href = href;
    s3.appendChild(rrTag("PROJECTED", "预计"));
    var fall = el("span", "whb-chip whb-fall");
    fall.appendChild(biTxt("whb-sym", "≥5% pullback", "≥5% 回撤"));
    s3.appendChild(fall);
    if (a.odds_pct != null) {
      var big = el("span", "whb-rr-big");
      big.appendChild(txt("span", "whb-rr-pct", a.odds_pct + "%"));
      big.appendChild(biTxt("whb-rr-hz", "within 21 days", "21 日内"));
      s3.appendChild(big);
    }
    if (a.lift != null) {
      var lc = el("span", "whb-chip");
      var base = a.base_pct != null ? " " + a.base_pct + "%" : "";
      lc.appendChild(biTxt("whb-sym",
        a.lift + "× vs normal" + base, a.lift + "× 对比常态" + base));
      s3.appendChild(lc);
    }
    if (Array.isArray(a.ramp) && a.ramp.length) {
      var rc = el("span", "whb-chip whb-ramp");
      a.ramp.forEach(function (h, i) {
        if (i) rc.appendChild(txt("span", "whb-div", "·"));
        rc.appendChild(biTxt("whb-sym", h.h_en + " " + h.pct + "%",
          h.h_zh + " " + h.pct + "%"));
      });
      s3.appendChild(rc);
    }
    run.appendChild(s3);
    return run;
  }

  function rrTag(en, zh) {
    var k = el("span", "whb-rr-k");
    k.appendChild(biTxt("", en, zh));
    return k;
  }

  // ---------------------------------------------------------------------------
  // shared plumbing
  // ---------------------------------------------------------------------------
  function readDismissed(key) {
    var out = {};
    try {
      (localStorage.getItem(key) || "").split("|").forEach(function (id) {
        if (id) out[id] = 1;
      });
    } catch (e) {}
    return out;
  }

  function applyAccent(bar, ch) {
    bar.style.setProperty("--whb-top", ch.top);
    bar.classList.toggle("whb-warm", !!ch.warm);
  }

  function startAlternation(bar, faces, channels) {
    var idx = 0, paused = false;
    var timer = setInterval(function () {
      if (paused) return;
      faces[idx].classList.remove("is-active");
      idx = (idx + 1) % faces.length;
      faces[idx].classList.add("is-active");
      applyAccent(bar, channels[idx]);
    }, ALT_MS);
    bar._whbTimer = timer;
    bar.addEventListener("mouseenter", function () { paused = true; });
    bar.addEventListener("mouseleave", function () { paused = false; });
  }

  // Full-bleed: cancel whatever padding/margin the host <body> sets so the bar hugs
  // the very top and both edges — pages differ (0/18/24/28px tops, viewport gutters),
  // so read the resolved values and negate them; recompute on resize.
  function fullBleed(bar, close) {
    var onResize = function () {
      try {
        var cs = window.getComputedStyle(document.body);
        var v = function (p) { return parseFloat(cs[p]) || 0; };
        bar.style.marginTop = -(v("paddingTop") + v("marginTop")) + "px";
        bar.style.marginLeft = -(v("paddingLeft") + v("marginLeft")) + "px";
        bar.style.marginRight = -(v("paddingRight") + v("marginRight")) + "px";
      } catch (e) {}
    };
    onResize();
    window.addEventListener("resize", onResize);
    close._whbResize = onResize; // so dismissal can detach the listener
  }

  // Scale each tape's scroll DURATION to its content width so the reading pace
  // (~px/sec) stays constant whether one alert or six are live.
  function scaleDurations(bar, reduce) {
    if (reduce) return;
    var tracks = bar.querySelectorAll(".whb-track");
    for (var i = 0; i < tracks.length; i++) {
      var firstRun = tracks[i].querySelector(".whb-run");
      var w = firstRun ? firstRun.getBoundingClientRect().width : 0;
      if (w > 0) tracks[i].style.animationDuration = Math.max(30, Math.round(w / 80)) + "s";
    }
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
  // bilingual inline span: <span class=cls><span.whb-en>en</span><span.whb-zh>zh</span></span>
  function biTxt(cls, en, zh) {
    var n = el("span", cls);
    n.appendChild(txt("span", "whb-en", en));
    n.appendChild(txt("span", "whb-zh", zh == null ? en : zh));
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
      // warmer backdrop while the orange Risk-Radar channel is showing
      ".whb.whb-warm{background:linear-gradient(90deg,rgba(44,32,20,.96),rgba(48,24,22,.96))}",
      ".whb::before{content:'';position:absolute;left:0;right:0;top:0;height:2px;",
      "background:var(--whb-top,linear-gradient(90deg,#3d6fd6,#d9a441 50%,#d2455c))}",
      // stage holds one face per channel; when .multi they overlap and crossfade
      ".whb-stage{flex:1 1 auto;position:relative;display:flex;align-items:stretch;min-width:0;overflow:hidden}",
      ".whb-face{display:flex;align-items:stretch;flex:1 1 auto;min-width:0}",
      ".whb-stage.multi .whb-face{position:absolute;inset:0;opacity:0;transition:opacity .55s ease;pointer-events:none}",
      ".whb-stage.multi .whb-face.is-active{opacity:1;pointer-events:auto}",
      // breaking label (channel colour set by whb-label-wh / whb-label-rr)
      ".whb-label{flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:0 16px;",
      "color:#fff;font-weight:800;letter-spacing:.07em;font-size:11px;text-transform:uppercase;",
      "text-decoration:none;box-shadow:6px 0 14px rgba(0,0,0,.30);position:relative;z-index:2;white-space:nowrap}",
      ".whb-label-wh{background:linear-gradient(90deg,#b8253c,#8f1d30)}",
      ".whb-label-rr{background:linear-gradient(90deg,#e0791c,#b8560f)}",
      ".whb-label-tx{white-space:nowrap}",
      "@media(max-width:560px){.whb-label-tx{display:none}.whb-label{padding:0 12px}}",
      ".whb-dot{width:8px;height:8px;border-radius:50%;background:#ffe1d1;",
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
      /* zh 红涨绿跌: tailwind (bullish/positive flow) pipe swaps green→red; headwind (bearish) swaps red→green */
      'html[data-lang="zh"] .whb-tone-tailwind{background:#e05555}html[data-lang="zh"] .whb-tone-headwind{background:#39c07d}',
      ".whb-tone-danger{background:linear-gradient(180deg,#ffb13a,#ec5a1e)}",
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
      /* zh 红涨绿跌: price change up (bullish) swaps green→red; dn swaps red→green */
      'html[data-lang="zh"] .whb-chg.up{color:#ff7a86}html[data-lang="zh"] .whb-chg.dn{color:#54d495}',
      ".whb-div{color:rgba(255,255,255,.28);padding:0 6px;font-size:9px}",
      // --- Risk-Radar channel accents ---
      ".whb-rr-k{display:inline-flex;align-items:center;padding:2px 8px;border-radius:6px;",
      "font-size:9.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;",
      "color:#ffcf9a;background:rgba(236,122,30,.16);border:1px solid rgba(236,122,30,.42)}",
      ".whb-rr-p{font-variant-numeric:tabular-nums;font-size:11px;font-weight:800;color:#ffb066}",
      ".whb-amp{background:rgba(236,122,30,.10);border-color:rgba(236,122,30,.28)}",
      ".whb-conj{background:rgba(210,69,92,.14);border-color:rgba(210,69,92,.40)}",
      ".whb-conj .whb-sym{color:#ffb3bd}",
      ".whb-fall .whb-sym{color:#ffd9a3}",
      ".whb-rr-big{display:inline-flex;align-items:baseline;gap:6px}",
      ".whb-rr-pct{font-variant-numeric:tabular-nums;font-weight:800;font-size:17px;color:#ffb066;letter-spacing:.01em}",
      ".whb-rr-hz{font-size:10.5px;color:rgba(255,214,170,.85);font-weight:600}",
      ".whb-ramp .whb-sym{color:#e9c9a2;font-size:11px}",
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

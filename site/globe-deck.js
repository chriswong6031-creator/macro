/* AURORA — breathing macro-regime globe flight deck.
   A draggable d3-geoOrthographic globe on a single 2D canvas: each covered country
   breathes in its live regime color (read from theme.css --q1..--q4 so it flips
   EN<->中文 + dark/light for free), a real day/night terminator sweeps the planet,
   HK is a sonar marker, the Eurozone is one merged gold bloc, hover pops a bilingual
   data tooltip, and a sidebar clock shows each market's index + open/closed countdown
   with a sun/moon glyph. All ambient motion is gated behind prefers-reduced-motion.
   Vendored deps (UMD globals): d3 (d3-array + d3-geo), topojson.  No build step. */
(function () {
  "use strict";
  var d3 = window.d3, topojson = window.topojson;
  var stage = document.querySelector(".gd-stage");
  if (!stage || !d3 || !topojson) return;
  var canvas = stage.querySelector(".gd-canvas");
  var poster = stage.querySelector(".gd-poster");
  var tip = stage.querySelector(".gd-tip");
  var live = stage.querySelector("#gd-live");
  var ctx = canvas.getContext("2d");
  var DATA, byCC = {};
  try { DATA = JSON.parse(document.getElementById("globe-data").textContent); }
  catch (e) { return; }
  DATA.forEach(function (m) { byCC[m.cc] = m; });

  var motionOK = !window.matchMedia || !matchMedia("(prefers-reduced-motion: reduce)").matches;
  var isDark = function () { return document.documentElement.getAttribute("data-theme") !== "light"; };

  // ---- geometry ------------------------------------------------------------
  var land = null, graticule = d3.geoGraticule10(), sphere = { type: "Sphere" };
  var paint = [];   // {cc, feature, centroid, m}  covered countries + EZ bloc
  var hk = null;    // {m, lonlat}
  var posMap = {}, arcs = [];  // cc -> lonlat ; agreement great-circle pairs
  var ready = false;

  function buildGeometry(topo) {
    var geos = topo.objects.countries.geometries;
    var byId = {};
    geos.forEach(function (g) { byId[String(g.id)] = g; });
    land = topojson.merge(topo, geos);            // one land mass underlay
    DATA.forEach(function (m) {
      if (m.kind === "marker") { hk = { m: m, lonlat: m.marker_lonlat }; return; }
      var ids = (m.geo_ids || []).filter(function (id) { return byId[id]; });
      if (!ids.length) return;
      var feat;
      if (ids.length === 1) feat = topojson.feature(topo, byId[ids[0]]);
      else feat = { type: "Feature", geometry: topojson.merge(topo, ids.map(function (id) { return byId[id]; })) };
      paint.push({ cc: m.cc, feature: feat, centroid: d3.geoCentroid(feat), m: m });
    });
    posMap = {}; arcs = [];
    paint.forEach(function (p) { posMap[p.cc] = p.centroid; });
    if (hk) posMap[hk.m.cc] = hk.lonlat;
    DATA.forEach(function (m) {
      (m.agrees_with || []).forEach(function (cc) {
        if (m.cc < cc && posMap[m.cc] && posMap[cc]) arcs.push({ a: posMap[m.cc], b: posMap[cc], q: m.quad });
      });
    });
    ready = true;
  }

  // ---- palette (read live CSS vars; recolors on lang/theme change) ----------
  var PAL = {};
  var swatch = document.createElement("canvas"); swatch.width = swatch.height = 1;
  var sctx = swatch.getContext("2d");
  function norm(c) { try { sctx.fillStyle = "#000"; sctx.fillStyle = c; return sctx.fillStyle; } catch (e) { return c; } }
  function cssv(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function readPalette() {
    ["--q1", "--q2", "--q3", "--q4", "--panel", "--panel2", "--line", "--info",
     "--text", "--bg", "--up", "--down", "--muted"].forEach(function (n) {
      PAL[n] = norm(cssv(n) || "#888");
    });
  }
  // rgba helper: blend a hex/rgb color toward another by alpha
  function rgba(hex, a) {
    var c = norm(hex); // ensures rgb()/hex
    if (c[0] === "#") {
      var r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
      return "rgba(" + r + "," + g + "," + b + "," + a + ")";
    }
    return c.replace(/rgb\(([^)]+)\)/, "rgba($1," + a + ")");
  }
  function qcolor(q) { return PAL["--" + q] || PAL["--q1"]; }
  function toRGB(c) { c = norm(c); if (c[0] === "#") return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; var m = c.match(/(\d+\.?\d*)/g); return [+m[0], +m[1], +m[2]]; }
  function lerpColor(a, b, t) { var x = toRGB(a), y = toRGB(b); return "rgb(" + Math.round(x[0] + (y[0] - x[0]) * t) + "," + Math.round(x[1] + (y[1] - x[1]) * t) + "," + Math.round(x[2] + (y[2] - x[2]) * t) + ")"; }
  var sweep = null;  // {t0, dur, old:{cc:color}} — west->east recolor wipe on lang/theme change

  // ---- projection & sizing -------------------------------------------------
  var projection = d3.geoOrthographic().precision(0.4);
  var path = d3.geoPath(projection, ctx);
  var rot = [98, -38];      // [lambda, phi] — start centered on North America (98W, 38N)
  var fitScale = 240, scale = 240, W = 0, H = 0, R = 0, dpr = 1, lastClipR = -1;

  function size() {
    // collapse the canvas first so the grid cell can shrink to its true width,
    // THEN measure (otherwise a stale inline px width pins the layout wide on resize)
    canvas.style.width = "0px"; canvas.style.height = "0px";
    var rect = stage.getBoundingClientRect();
    W = Math.max(200, Math.floor(rect.width)); H = Math.max(240, Math.floor(rect.height));
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    R = Math.min(W, H) * 0.43;   // fit factor → the globe + 1.13x halo float clear of the
                                 // canvas rect at the DEFAULT zoom (0.43*1.13 = 0.486 < 0.5),
                                 // so it's never cut off by the canvas edge — bigger hero globe
    fitScale = R; scale = scale === 240 ? R : Math.min(R * 1.35, Math.max(R * 0.8, scale));
    apply();
    if (ready) render(performance.now());   // repaint + reposition islands on resize even when paused
  }
  function apply() { projection.rotate([rot[0], rot[1], 0]).scale(scale).translate([W / 2, H / 2]); clipHit(); }
  // Limit the canvas's TOUCH/click region to the visible globe disc (+ glow), centered.
  // clip-path clips hit-testing as well as painting, so swipes in the empty square
  // corners fall through to the page and scroll normally instead of spinning the globe
  // (the #1 mobile complaint). Radius tracks zoom; corners were always transparent, so
  // there's no visual change. Re-applied via apply() on every scale change.
  function clipHit() {
    var r = scale * 1.13 + 4;                 // sphere + atmosphere halo + a small touch margin
    if (Math.abs(r - lastClipR) < 0.5) return;
    lastClipR = r;
    var cp = "circle(" + r.toFixed(1) + "px at 50% 50%)";
    canvas.style.clipPath = cp; canvas.style.webkitClipPath = cp;
  }

  // ---- starfield (dark only, static) ---------------------------------------
  var stars = [];
  function buildStars() {
    stars = [];
    for (var i = 0; i < 110; i++) stars.push({ x: Math.random(), y: Math.random(), r: Math.random() * 1.1 + 0.3, p: Math.random() * 6.28 });
  }

  // ---- subsolar point for the terminator -----------------------------------
  function subsolar() {
    var now = new Date();
    var h = now.getUTCHours() + now.getUTCMinutes() / 60 + now.getUTCSeconds() / 3600;
    var lon = -15 * (h - 12);
    var doy = Math.floor((Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - Date.UTC(now.getUTCFullYear(), 0, 0)) / 864e5);
    var lat = -23.44 * Math.cos((2 * Math.PI / 365) * (doy + 10));
    return [lon, lat];
  }

  function hashPhase(s) { var h = 0; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 997; return (h / 997) * 6.283; }

  // ---- focus / selection state ---------------------------------------------
  var hovered = null, selected = null, t0 = performance.now(), lastInteract = t0;
  var velX = 0, velY = 0, dragging = false, flying = null;

  // ---- render --------------------------------------------------------------
  function render(t) {
    if (!ready) return;
    ctx.clearRect(0, 0, W, H);
    var cx = W / 2, cy = H / 2, dark = isDark();

    // starfield (dark)
    if (dark) {
      for (var i = 0; i < stars.length; i++) {
        var s = stars[i], tw = motionOK ? (0.5 + 0.5 * Math.sin(t / 900 + s.p)) : 0.7;
        ctx.globalAlpha = 0.05 + 0.5 * tw * (s.r / 1.4);
        ctx.fillStyle = PAL["--text"];
        ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.r, 0, 6.283); ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    // atmosphere rim-glow (outside the disc)
    var atmo = ctx.createRadialGradient(cx, cy, scale * 0.92, cx, cy, scale * 1.13);
    atmo.addColorStop(0, rgba(PAL["--info"], 0));
    atmo.addColorStop(0.55, rgba(PAL["--info"], dark ? 0.22 : 0.12));
    atmo.addColorStop(1, rgba(PAL["--info"], 0));
    ctx.fillStyle = atmo;
    ctx.beginPath(); ctx.arc(cx, cy, scale * 1.13, 0, 6.283); ctx.fill();

    // ocean sphere
    var oc = ctx.createRadialGradient(cx - scale * 0.3, cy - scale * 0.3, scale * 0.2, cx, cy, scale);
    oc.addColorStop(0, dark ? rgba(PAL["--panel2"], 1) : rgba(PAL["--panel2"], 1));
    oc.addColorStop(1, dark ? rgba(PAL["--bg"], 1) : rgba(PAL["--line"], 0.6));
    ctx.beginPath(); path(sphere); ctx.fillStyle = oc; ctx.fill();

    // graticule
    ctx.beginPath(); path(graticule); ctx.strokeStyle = rgba(PAL["--line"], dark ? 0.45 : 0.6); ctx.lineWidth = 0.5; ctx.stroke();

    // land underlay
    ctx.beginPath(); path(land); ctx.fillStyle = rgba(PAL["--muted"], dark ? 0.16 : 0.13); ctx.fill();
    ctx.strokeStyle = rgba(PAL["--line"], dark ? 0.5 : 0.55); ctx.lineWidth = 0.4; ctx.stroke();

    // covered country fills (breathing glow)
    var anyHover = hovered || selected;
    for (var k = 0; k < paint.length; k++) {
      var p = paint[k], q = qcolor(p.m.quad);
      if (sweep && sweep.old[p.cc] && posMap[p.cc]) {       // west->east recolor wipe
        var ln = (posMap[p.cc][0] + 180) / 360;
        var lp = Math.max(0, Math.min(1, ((t - sweep.t0) / sweep.dur - ln * 0.7) / 0.4));
        q = lerpColor(sweep.old[p.cc], qcolor(p.m.quad), lp);
      }
      var conf = p.m.confidence == null ? 0.4 : p.m.confidence;
      var amp = 0.16 + 0.34 * conf;
      var per = 4200 + 1800 * (1 - conf);
      var breath = motionOK ? (0.5 + 0.5 * Math.sin(t * 2 * Math.PI / per + hashPhase(p.cc))) : 0.5;
      var focus = (anyHover && (hovered === p.cc || selected === p.cc));
      var dim = (anyHover && !focus) ? 0.45 : 1;
      var glow = (focus ? 26 : 14) + amp * 22 * breath;
      // glow
      ctx.save();
      ctx.shadowColor = rgba(q, (focus ? 0.95 : 0.65) * dim);
      ctx.shadowBlur = glow;
      ctx.beginPath(); path(p.feature);
      ctx.fillStyle = rgba(q, (0.30 + 0.26 * (focus ? 1 : breath)) * dim);
      ctx.fill();
      ctx.restore();
      // crisp cap + stroke (steady, no shimmer)
      ctx.beginPath(); path(p.feature);
      ctx.fillStyle = rgba(q, (0.22 + (focus ? 0.18 : 0.10)) * dim);
      ctx.fill();
      ctx.strokeStyle = rgba(q, (focus ? 1 : 0.8) * dim); ctx.lineWidth = focus ? 1.4 : 1; ctx.stroke();
    }

    // terminator (night dim, never black)
    var ss = subsolar();
    var night = d3.geoCircle().radius(90).center([ss[0] + 180, -ss[1]])();
    ctx.beginPath(); path(night);
    ctx.fillStyle = rgba(PAL["--bg"], dark ? 0.34 : 0.16); ctx.fill();

    // city lights (night side, dark only)
    if (dark) {
      for (var ci = 0; ci < DATA.length; ci++) {
        var ll = posMap[DATA[ci].cc]; if (!ll || !onFront(ll) || d3.geoDistance(ll, ss) < Math.PI / 2) continue;
        var lxy = projection(ll); if (!lxy) continue;
        var tw2 = motionOK ? (0.5 + 0.5 * Math.sin(t / 650 + ci)) : 0.8;
        ctx.beginPath(); ctx.arc(lxy[0], lxy[1], 1.5, 0, 6.283);
        ctx.fillStyle = rgba(PAL["--warn"], 0.4 + 0.45 * tw2); ctx.fill();
      }
    }

    // confluence arcs (same-regime agreements)
    for (var ai = 0; ai < arcs.length; ai++) {
      var arc = arcs[ai], aq = qcolor(arc.q), interp = d3.geoInterpolate(arc.a, arc.b), pts = [];
      for (var s = 0; s <= 26; s++) pts.push(interp(s / 26));
      ctx.save();
      ctx.shadowColor = rgba(aq, 0.6); ctx.shadowBlur = 4;
      ctx.beginPath(); path({ type: "LineString", coordinates: pts });
      ctx.strokeStyle = rgba(aq, dark ? 0.42 : 0.48); ctx.lineWidth = 1.2; ctx.setLineDash([1, 5]); ctx.stroke(); ctx.setLineDash([]);
      ctx.restore();
      if (motionOK) {
        var fr = (t / 3000 + ai * 0.17) % 1, fp = interp(fr);
        if (onFront(fp)) { var pxy = projection(fp); if (pxy) { ctx.save(); ctx.shadowColor = rgba(aq, 0.9); ctx.shadowBlur = 6; ctx.beginPath(); ctx.arc(pxy[0], pxy[1], 2, 0, 6.283); ctx.fillStyle = rgba(aq, 1); ctx.fill(); ctx.restore(); } }
      }
    }

    // HK sonar marker
    if (hk) drawMarker(t, hk, cx, cy);

    // floating data-islands (DOM overlay): positioned, occluded + leader-drawn here,
    // replacing the old static canvas flag labels AND the market-clock sidebar
    positionIslands();
  }

  function visible(lonlat) {
    var c = d3.geoRotation([rot[0], rot[1], 0])(lonlat);  // not used; use distance test
    return true;
  }
  function onFront(lonlat) {
    var center = [-rot[0], -rot[1]];
    return d3.geoDistance(lonlat, center) < Math.PI / 2;
  }
  // feathered generalization of onFront(): 1 = dead-front, fading to 0 across the limb,
  // so islands dissolve through the edge instead of popping. Drives the --f occlusion var.
  var FEATHER = 0.30;
  function frontness(lonlat) {
    return Math.max(0, Math.min(1, (Math.PI / 2 - d3.geoDistance(lonlat, [-rot[0], -rot[1]])) / FEATHER));
  }

  function drawMarker(t, mk, cx, cy) {
    if (!onFront(mk.lonlat)) return;
    var xy = projection(mk.lonlat); if (!xy) return;
    var q = qcolor(mk.m.quad);
    // sonar rings
    if (motionOK) {
      for (var r = 0; r < 2; r++) {
        var ph = ((t / 2600 + r * 0.5) % 1);
        ctx.beginPath(); ctx.arc(xy[0], xy[1], 4 + ph * 26, 0, 6.283);
        ctx.strokeStyle = rgba(q, 0.5 * (1 - ph)); ctx.lineWidth = 1.4; ctx.stroke();
      }
    }
    ctx.save();
    ctx.shadowColor = rgba(q, 0.9); ctx.shadowBlur = 12;
    ctx.beginPath(); ctx.arc(xy[0], xy[1], 4.2, 0, 6.283); ctx.fillStyle = rgba(q, 0.95); ctx.fill();
    ctx.restore();
    // leader + label
    ctx.font = "700 10.5px Inter, sans-serif";
    var label = mk.m.flag + " HK";
    ctx.fillStyle = PAL["--text"];
    ctx.strokeStyle = rgba(PAL["--bg"], 0.9); ctx.lineWidth = 3; ctx.lineJoin = "round";
    ctx.strokeText(label, xy[0] + 8, xy[1] - 7); ctx.fillText(label, xy[0] + 8, xy[1] - 7);
  }

  function drawLabels() {
    ctx.font = "700 10px Inter, sans-serif"; ctx.textAlign = "center";
    for (var k = 0; k < paint.length; k++) {
      var p = paint[k]; if (!onFront(p.centroid)) continue;
      var xy = projection(p.centroid); if (!xy) continue;
      var tag = p.m.flag;
      ctx.strokeStyle = rgba(PAL["--bg"], 0.85); ctx.lineWidth = 3; ctx.lineJoin = "round";
      ctx.fillStyle = PAL["--text"];
      ctx.strokeText(tag, xy[0], xy[1] + 3); ctx.fillText(tag, xy[0], xy[1] + 3);
    }
    ctx.textAlign = "start";
  }

  // ---- frame loop ----------------------------------------------------------
  var raf = null;
  function frame(t) {
    if (sweep && t - sweep.t0 > sweep.dur + 500) sweep = null;
    var tgt = (hovering && !dragging) ? 0.5 : 1; spd += (tgt - spd) * 0.05;   // fade slowdown / fade speedup on hover
    if (flying) {
      var u = Math.min(1, (t - flying.t0) / flying.dur);
      var e = 1 - Math.pow(1 - u, 3);
      rot[0] = flying.a0 + (flying.a1 - flying.a0) * e;
      rot[1] = flying.b0 + (flying.b1 - flying.b0) * e;
      scale = flying.s0 + (flying.s1 - flying.s0) * e;
      apply();
      if (u >= 1) flying = null;
    } else if (dragging) {
      // handled by pointermove
    } else if (Math.abs(velX) > 0.02 || Math.abs(velY) > 0.02) {
      rot[0] += velX; rot[1] = clampLat(rot[1] + velY); velX *= 0.94; velY *= 0.94; apply();
    } else if (motionOK && !selected && (t - lastInteract) > 1500) {
      rot[0] += 0.12 * spd; apply();   // idle auto-rotate, eased to half-speed while hovered
    }
    render(t);
    raf = requestAnimationFrame(frame);
  }
  function clampLat(p) { return Math.max(-78, Math.min(78, p)); }

  // ---- interaction ---------------------------------------------------------
  var px = 0, py = 0, moved = 0, lastMoveT = 0;
  // hovering the globe EASES the idle auto-spin down to half speed (a smooth fade, not a
  // dead stop); it fades back to full when the pointer leaves. spd = smoothed multiplier.
  var hovering = false, spd = 1;
  stage.addEventListener("pointerenter", function (e) { if (e.pointerType !== "touch") hovering = true; });
  stage.addEventListener("pointerleave", function (e) { if (e.pointerType !== "touch") hovering = false; });
  canvas.addEventListener("pointerdown", function (e) {
    dragging = true; flying = null; velX = velY = 0; moved = 0;
    px = e.clientX; py = e.clientY; lastInteract = performance.now();
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", function (e) {
    // only a DRAG resets the idle timer + rotates; a bare hover never pops a tooltip
    // and never dead-stops the spin (the islands own all hover/press affordances)
    if (dragging) {
      lastInteract = performance.now();
      var k = 0.32 * (240 / scale);
      var dx = (e.clientX - px), dy = (e.clientY - py);
      rot[0] += dx * k; rot[1] = clampLat(rot[1] - dy * k);
      var nt = performance.now(), d = Math.max(8, nt - lastMoveT);
      velX = dx * k * (16 / d) * 0.6; velY = -dy * k * (16 / d) * 0.6; lastMoveT = nt;
      moved += Math.abs(dx) + Math.abs(dy); px = e.clientX; py = e.clientY; apply();
      hideTip();
    }
  });
  canvas.addEventListener("pointerup", function (e) {
    dragging = false;
    if (moved < 5) { clickAt(e.clientX, e.clientY); }     // a click, not a drag
  });
  canvas.addEventListener("pointerleave", function () { if (!dragging) { hovered = null; hideTip(); } });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault(); lastInteract = performance.now();
    scale = Math.max(fitScale * 0.8, Math.min(fitScale * 1.3, scale * (e.deltaY < 0 ? 1.08 : 0.93))); apply();
  }, { passive: false });

  function pick(cx, cy) {
    var r = canvas.getBoundingClientRect(); var x = cx - r.left, y = cy - r.top;
    var ll = projection.invert([x, y]); if (!ll) return null;
    if (!onFront(ll)) return null;
    // HK marker radius test
    if (hk && onFront(hk.lonlat)) { var hxy = projection(hk.lonlat); if (hxy && Math.hypot(hxy[0] - x, hxy[1] - y) < 13) return hk.m; }
    for (var k = 0; k < paint.length; k++) { if (d3.geoContains(paint[k].feature, ll)) return paint[k].m; }
    return null;
  }
  function hoverAt(cx, cy) {
    // while a country is selected the tooltip is PINNED (and interactive) — keep it
    // locked so moving the cursor toward its "Open dashboard" link doesn't swap it out
    if (selected) { canvas.style.cursor = "grab"; return; }
    var m = pick(cx, cy);
    hovered = m ? m.cc : null;
    canvas.style.cursor = m ? "pointer" : "grab";
    if (m) showTip(m, cx, cy); else hideTip();
  }
  function clickAt(cx, cy) {
    var m = pick(cx, cy);
    if (m) toggleSelect(m, cx, cy); else deselect();
  }
  // press an already-open market again to close it; otherwise open / switch
  function toggleSelect(m, cx, cy) { if (selected === m.cc) deselect(); else selectMarket(m, cx, cy); }
  function deselect() { selected = null; hovered = null; tip.classList.remove("pinned"); tip.hidden = true; syncRows(); if (live) live.textContent = ""; }
  function selectMarket(m, cx, cy) {
    selected = m.cc; hovered = null; lastInteract = performance.now();
    var ll = m.kind === "marker" ? m.marker_lonlat : (byCC[m.cc] && paintCentroid(m.cc)) || [0, 0];
    flying = { t0: performance.now(), dur: 700, a0: rot[0], b0: rot[1], a1: -ll[0], b1: clampLat(-ll[1]), s0: scale, s1: fitScale * 1.12 };
    showTip(m, cx || (W / 2 + stage.getBoundingClientRect().left), cy || (H / 2 + stage.getBoundingClientRect().top), true);
    syncRows();
    if (live) live.textContent = m.name_en + ": " + m.quad_name_en;
  }
  function paintCentroid(cc) { for (var k = 0; k < paint.length; k++) if (paint[k].cc === cc) return paint[k].centroid; return null; }

  // ---- tooltip -------------------------------------------------------------
  function bilingual(en, zh) { return '<span class="l-en">' + en + '</span><span class="l-zh">' + zh + '</span>'; }
  function bar(val, color) {
    var pos = Math.max(-1, Math.min(1, val || 0)); var pct = Math.abs(pos) * 50;
    var side = pos >= 0 ? "left:50%;width:" + pct + "%" : "right:50%;width:" + pct + "%";
    return '<span class="gd-bar"><i style="' + side + ';background:' + color + '"></i></span>';
  }
  function showTip(m, cx, cy, pinned) {
    var q = m.quad, up = (m.index_chg_pct || 0) >= 0;
    var risk = (m.recession != null || m.drawdown_risk != null)
      ? (m.recession != null ? bilingual("Recession " + m.recession + "/100", "衰退 " + m.recession + "/100") : "")
        + (m.drawdown_risk != null ? " · " + bilingual("drawdown " + m.drawdown_risk, "回撤 " + m.drawdown_risk) : "")
      : bilingual(m.risk_text_en, m.risk_text_zh);
    var conf = Math.round((m.confidence || 0) * 5), dots = "";
    for (var i = 0; i < 5; i++) dots += i < conf ? "●" : "○";
    var chgColor = up ? "var(--up)" : "var(--down)";
    tip.innerHTML =
      '<div class="gd-tip-h"><span class="gd-tip-flag">' + m.flag + '</span>' +
        '<span class="gd-tip-name">' + bilingual(m.name_en, m.name_zh) + '</span>' +
        '<span class="gd-chip ' + q + '">' + bilingual(m.quad_name_en, m.quad_name_zh) + '</span></div>' +
      '<div class="gd-tip-gi">' +
        '<div><span class="gd-tip-k">' + bilingual("Growth", "增长") + '</span>' + bar(m.growth, "var(--" + q + ")") + '<b>' + fmt(m.growth) + '</b></div>' +
        '<div><span class="gd-tip-k">' + bilingual("Inflation", "通胀") + '</span>' + bar(m.inflation, "var(--muted)") + '<b>' + fmt(m.inflation) + '</b></div>' +
      '</div>' +
      '<div class="gd-tip-row"><span class="gd-tip-k">' + bilingual("Risk", "风险") + '</span><span>' + risk + '</span></div>' +
      '<div class="gd-tip-row"><span class="gd-tip-k">' + bilingual("Confidence", "置信度") + '</span><span class="gd-dots">' + dots + '</span>' +
        (m.data_limited ? '<span class="gd-lim">' + bilingual("limited data", "数据有限") + '</span>' : '') + '</div>' +
      '<div class="gd-tip-idx"><span>' + bilingual(m.index_name_en, m.index_name_zh) + '</span>' +
        '<b>' + (m.index_price || "—") + '</b>' +
        '<span class="gd-chg" style="color:' + chgColor + '">' + (up ? "+" : "") + (m.index_chg_pct == null ? "" : m.index_chg_pct + "%") + '</span></div>' +
      '<div class="gd-tip-foot">' + bilingual("Descriptive regime read — not a forecast.", "描述性周期读数，非预测。") +
        (m.macro_asof ? ' · ' + bilingual("as of " + m.macro_asof, m.macro_asof) : '') + '</div>' +
      '<a class="gd-tip-go" href="' + m.href + '">' + bilingual("Open dashboard →", "打开看板 →") + '</a>';
    tip.hidden = false;
    tip.classList.toggle("pinned", !!pinned);
    // mobile: a pinned tooltip becomes a BOTTOM SHEET — always fully on-screen even
    // when the tap came from the sidebar far below the globe (no more half-off-screen).
    if (pinned && window.innerWidth <= 560) {
      tip.style.left = "10px"; tip.style.right = "10px"; tip.style.width = "auto";
      tip.style.top = "auto"; tip.style.bottom = "12px";
      return;
    }
    tip.style.right = ""; tip.style.bottom = ""; tip.style.width = "";  // clear any prior bottom-sheet
    var tw = tip.offsetWidth, th = tip.offsetHeight, pad = 10, x, y;
    if (pinned) {
      // a clicked country flies to the globe centre, so anchor the tooltip BESIDE
      // the centre (whichever side has room) rather than at the click point — which
      // may sit at the viewport edge and push the tooltip off-screen.
      var sr = stage.getBoundingClientRect(), gx = sr.left + W / 2, gy = sr.top + H / 2;
      x = gx + R * 0.55 + 14;
      if (x + tw > window.innerWidth - pad) x = gx - R * 0.55 - tw - 14;
      y = gy - th / 2;
    } else {
      x = cx + 14; y = cy + 14;
      if (x + tw > window.innerWidth - pad) x = cx - tw - 14;
      if (y + th > window.innerHeight - pad) y = cy - th - 14;
    }
    // hard clamp: the tooltip is ALWAYS fully on-screen (every edge, any size)
    x = Math.max(pad, Math.min(x, window.innerWidth - tw - pad));
    y = Math.max(pad, Math.min(y, window.innerHeight - th - pad));
    tip.style.left = x + "px"; tip.style.top = y + "px";
    tip.classList.toggle("pinned", !!pinned);
  }
  function hideTip() { if (selected) return; tip.hidden = true; }
  function fmt(v) { return v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2); }
  // ---- sidebar market clock ------------------------------------------------
  function localParts(tz) {
    var f = new Intl.DateTimeFormat("en-GB", { timeZone: tz, weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false });
    var o = {}; f.formatToParts(new Date()).forEach(function (p) { o[p.type] = p.value; });
    return { wd: o.weekday, min: (parseInt(o.hour, 10) % 24) * 60 + parseInt(o.minute, 10) };
  }
  function hm(s) { var a = s.split(":"); return parseInt(a[0], 10) * 60 + parseInt(a[1], 10); }
  function clockState(m) {
    var lp = localParts(m.tz);
    var weekend = (lp.wd === "Sat" || lp.wd === "Sun");
    var o = hm(m.open), c = hm(m.close), now = lp.min;
    var open = !weekend && now >= o && now < c;
    var lunch = false;
    if (open && m.lunch) { var ls = hm(m.lunch[0]), le = hm(m.lunch[1]); if (now >= ls && now < le) { open = false; lunch = true; } }
    // next boundary minutes
    var next, label_en, label_zh;
    if (open) { next = c - now; if (m.lunch) { var l0 = hm(m.lunch[0]); if (now < l0) next = l0 - now; } label_en = "closes in"; label_zh = "距休市"; }
    else if (lunch) { next = hm(m.lunch[1]) - now; label_en = "reopens in"; label_zh = "距续盘"; }
    else { // closed: minutes to next open (today or next weekday)
      var add = 0, day = lp.wd;
      if (!weekend && now < o) add = o - now;
      else { add = (24 * 60 - now) + o; var seq = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]; var di = seq.indexOf(day); var d2 = (di + 1) % 7; while (d2 === 0 || d2 === 6) { add += 24 * 60; d2 = (d2 + 1) % 7; } }
      next = add; label_en = "opens in"; label_zh = "距开盘";
    }
    // arc = fraction of the current span still remaining (full ring → empties toward the bell)
    var arc = 0;
    if (open) { var span = c - o; arc = span > 0 ? Math.max(0, Math.min(1, next / span)) : 0; }
    else if (lunch) { var sp = hm(m.lunch[1]) - hm(m.lunch[0]); arc = sp > 0 ? Math.max(0, Math.min(1, next / sp)) : 0; }
    return { open: open, lunch: lunch, next: next, label_en: label_en, label_zh: label_zh, frac: lp.min / 1440, arc: arc };
  }
  function dur(mins) { var h = Math.floor(mins / 60), m = Math.round(mins % 60); return (h ? h + "h " : "") + m + "m"; }
  function sunmoon(frac) {
    var day = frac > 0.27 && frac < 0.79;        // ~6:30–19:00 local
    var ax = 14 * Math.sin(Math.PI * Math.max(0, Math.min(1, (frac - 0.27) / 0.52)));
    var ay = day ? (8 - 8 * Math.sin(Math.PI * (frac - 0.27) / 0.52)) : 6;
    if (day) return '<svg viewBox="0 0 32 20" class="gd-sm"><circle cx="' + (16 + ax - 14) + '" cy="' + (4 + ay) + '" r="4" fill="var(--warn)"/></svg>';
    return '<svg viewBox="0 0 32 20" class="gd-sm"><path d="M' + (18) + ' 5a5 5 0 1 0 0 10 6 6 0 0 1 0-10z" fill="var(--muted)"/></svg>';
  }
  // ---- floating data-islands (replaces the whole market-clock sidebar) ------
  // One geo-anchored glass pebble per market. Rest = flag + open/closed semaphore +
  // signed %chg (+ live price on desktop). A depleting ring around the centroid dot
  // shows time-to-bell. Press → the existing regime popup. Front pebbles are crisp
  // jewels; back pebbles dim/blur and are reparented BELOW the canvas so the opaque
  // globe clips them. NO hover-expand (it shifted layout). Every datum that the
  // sidebar showed survives: %chg + price live on the pebble (live.js still patches
  // .nb-px/.nb-chg), session state in the semaphore + ring + the next-bell strip,
  // and the sr-only legend buttons remain the keyboard / no-JS spine.
  var islEls = {}, islFrontState = {}, islFront = null, islBack = null, rowEls = {};
  var ASIA = ["CN", "JP", "KR", "TW", "HK"], clusterEl = null, exploded = false;
  var RINGC = 2 * Math.PI * 9;
  function buildIslands() {
    islFront = stage.querySelector(".gd-isl-front");
    islBack = stage.querySelector(".gd-isl-back");
    if (!islFront || !islBack) return;
    DATA.forEach(function (m) {
      var up = (m.index_chg_pct || 0) >= 0;
      var el = document.createElement("div"); el.className = "gd-isl " + m.quad; el.setAttribute("data-cc", m.cc);
      var conf = m.confidence == null ? 0.4 : m.confidence;
      el.style.setProperty("--bd", (3.4 + 2.6 * (1 - conf)).toFixed(2) + "s");
      el.style.setProperty("--bdl", (-(hashPhase(m.cc) / 6.283 * 4)).toFixed(2) + "s");
      el.innerHTML =
        '<span class="glow"></span><span class="dot"></span>' +
        '<svg class="ring" viewBox="0 0 24 24" aria-hidden="true"><circle class="trk" cx="12" cy="12" r="9"></circle><circle class="arc" cx="12" cy="12" r="9"></circle></svg>' +
        '<button class="body" type="button" aria-label="' + (m.name_en || m.cc) + '">' +
        '<span class="isl-flag">' + m.flag + '</span>' +
        '<span class="isl-sem closed"></span>' +
        '<em class="isl-chg nb-chg ' + (up ? "up" : "down") + '" data-sym="' + (m.index_sym || "") + '">' + (up ? "+" : "") + (m.index_chg_pct == null ? "" : m.index_chg_pct + "%") + '</em>' +
        '<span class="isl-px nb-px" data-sym="' + (m.index_sym || "") + '" data-mkt="idx">' + (m.index_price || "—") + '</span>' +
        '</button>';
      el.querySelector(".body").addEventListener("click", function (ev) { ev.stopPropagation(); toggleSelect(m); });
      islFront.appendChild(el); islEls[m.cc] = el; rowEls[m.cc] = el; islFrontState[m.cc] = true;
    });
    // (Asia cluster chip retired — overlapping pebbles now fan out as leader-line
    //  "balloons" in positionIslands() so every market stays individually readable)
    updateClocks();
    setInterval(updateClocks, 1000);
    var utc = stage.parentNode.querySelector(".gd-utc");
    if (utc) { var tick = function () { utc.textContent = new Date().toISOString().slice(11, 16); }; tick(); setInterval(tick, 1000); }
  }
  function buildCluster() {
    clusterEl = document.createElement("div"); clusterEl.className = "gd-cluster";
    clusterEl.innerHTML = '<span class="cl-globe" aria-hidden="true">🌏</span>' + bilingual("Asia", "亚洲") + '<span class="cl-n"></span><span class="cl-dots" aria-hidden="true"></span>';
    clusterEl.addEventListener("click", function (e) { e.stopPropagation(); exploded = !exploded; });
    islFront.appendChild(clusterEl);
  }
  function positionIslands() {
    if (!islFront) return;
    var cx = W / 2, cy = H / 2, mob = W < 560;
    var off = mob ? 16 : 26;                          // how far the balloon floats off its dot
    var hw = mob ? 52 : 76, hh = 14, gapY = mob ? 8 : 10;  // body half-size + min vertical gap
    var padX = mob ? 14 : 12, topPad = 40;           // viewport clamp insets (extra margin on mobile)
    var lab = [];
    DATA.forEach(function (m) {
      var el = islEls[m.cc], ll = posMap[m.cc]; if (!el || !ll) return;
      var xy = projection(ll); if (!xy) return;
      var f = frontness(ll);
      var dx = xy[0] - cx, dy = xy[1] - cy, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
      el.style.setProperty("--x", xy[0].toFixed(1));
      el.style.setProperty("--y", xy[1].toFixed(1));
      el.style.setProperty("--f", f.toFixed(3));
      // hysteresis reparent across the limb so the opaque globe clips back-side pebbles
      var isF = islFrontState[m.cc];
      if (isF && f < 0.42) { islFrontState[m.cc] = false; islBack.appendChild(el); }
      else if (!isF && f > 0.58) { islFrontState[m.cc] = true; islFront.appendChild(el); }
      el.querySelector(".body").style.pointerEvents = f > 0.5 ? "auto" : "none";
      if (f > 0.5) {
        // front pebble: start the balloon a bit out along its radial, then declutter below
        lab.push({ el: el, m: m, ax: xy[0], ay: xy[1], bx: xy[0] + ux * off, by: xy[1] + uy * off });
      } else {
        // fading/back: just sit a touch off the dot, no leader, no declutter
        el.style.setProperty("--ox", (ux * off).toFixed(1));
        el.style.setProperty("--oy", (uy * off).toFixed(1));
      }
    });
    // fan overlapping balloons apart (mostly vertical → a readable column on strings)
    declutter(lab, hw * 2 * 0.72, hh * 2 + gapY);
    // commit positions (clamped to the viewport) + draw the leader "strings"
    for (var i = 0; i < lab.length; i++) {
      var p = lab[i];
      if (p.bx < hw + padX) p.bx = hw + padX; else if (p.bx > W - hw - padX) p.bx = W - hw - padX;
      if (p.by < topPad) p.by = topPad; else if (p.by > H - hh - padX) p.by = H - hh - padX;
      p.el.style.setProperty("--ox", (p.bx - p.ax).toFixed(1));
      p.el.style.setProperty("--oy", (p.by - p.ay).toFixed(1));
      var q = qcolor(p.m.quad);
      ctx.save(); ctx.beginPath(); ctx.moveTo(p.ax, p.ay); ctx.lineTo(p.bx, p.by);
      ctx.strokeStyle = rgba(q, 0.5); ctx.lineWidth = 1; ctx.shadowColor = rgba(q, 0.55); ctx.shadowBlur = 3; ctx.stroke(); ctx.restore();
    }
  }
  // greedy relaxation: separate overlapping label bodies, pushing mostly vertically so
  // a tight knot (East Asia) fans into a readable column of balloons-on-strings while
  // each dot stays pinned to its true country. minDX/minDY = required centre spacing.
  function declutter(lab, minDX, minDY) {
    if (lab.length < 2) return;
    for (var it = 0; it < 24; it++) {
      var any = false;
      for (var i = 0; i < lab.length; i++) {
        for (var j = i + 1; j < lab.length; j++) {
          var a = lab[i], b = lab[j], ddx = b.bx - a.bx, ddy = b.by - a.by;
          if (minDX - Math.abs(ddx) > 0 && minDY - Math.abs(ddy) > 0) {   // bodies overlap
            any = true;
            var push = (minDY - Math.abs(ddy)) / 2 + 0.5;
            if (ddy >= 0) { a.by -= push; b.by += push; } else { a.by += push; b.by -= push; }
          }
        }
      }
      if (!any) break;
    }
  }
  function updateClocks() {
    var soonest = null;
    DATA.forEach(function (m) {
      var el = islEls[m.cc]; if (!el) return;
      var st = clockState(m);
      var pre = (st.open && st.next <= 15) || (!st.open && !st.lunch && st.next <= 15);
      el.querySelector(".isl-sem").className = "isl-sem " + (st.open ? (pre ? "pre" : "open") : st.lunch ? "lunch" : pre ? "pre" : "closed");
      var arcEl = el.querySelector(".arc");
      if (arcEl) { var shown = st.open || st.lunch; arcEl.style.strokeDasharray = RINGC.toFixed(2); arcEl.style.strokeDashoffset = (RINGC * (1 - (shown ? st.arc : 0))).toFixed(2); arcEl.style.stroke = pre ? "var(--warn)" : "var(--qc)"; arcEl.style.opacity = shown ? "1" : "0"; }
      el.classList.toggle("sel", selected === m.cc);
      if (!soonest || st.next < soonest.next) soonest = { m: m, next: st.next, label_en: st.label_en, label_zh: st.label_zh };
    });
    var nb = stage.parentNode.querySelector(".gd-nextbell");
    if (nb && soonest) nb.innerHTML = bilingual("Next bell · " + soonest.m.index_name_en + " " + soonest.label_en + " " + dur(soonest.next),
                                                "下一响铃 · " + soonest.m.index_name_zh + " " + soonest.label_zh + " " + dur(soonest.next));
  }
  function syncRows() { Object.keys(islEls).forEach(function (cc) { islEls[cc].classList.toggle("sel", selected === cc); }); }

  // ---- recolor on lang/theme change ----------------------------------------
  function recolor() {
    var old = {};
    paint.forEach(function (p) { old[p.cc] = qcolor(p.m.quad); });
    readPalette(); buildStars();
    if (motionOK) sweep = { t0: performance.now(), dur: 700, old: old };
    else render(performance.now());
  }
  ["langchange", "themechange"].forEach(function (e) { document.addEventListener(e, recolor); });
  if (window.matchMedia) try { matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", function (e) { motionOK = !e.matches; if (motionOK && !raf) raf = requestAnimationFrame(frame); }); } catch (e) {}

  // ---- keyboard ------------------------------------------------------------
  canvas.addEventListener("keydown", function (e) {
    var k = e.key; lastInteract = performance.now();
    if (k === "ArrowLeft") rot[0] -= 8; else if (k === "ArrowRight") rot[0] += 8;
    else if (k === "ArrowUp") rot[1] = clampLat(rot[1] + 6); else if (k === "ArrowDown") rot[1] = clampLat(rot[1] - 6);
    else if (k === "+" || k === "=") scale = Math.min(fitScale * 1.3, scale * 1.1);
    else if (k === "-") scale = Math.max(fitScale * 0.8, scale * 0.9);
    else if (k === "Escape") { deselect(); }
    else return;
    e.preventDefault(); apply();
  });
  stage.querySelectorAll(".gd-leg").forEach(function (btn) {
    btn.addEventListener("click", function () { var m = byCC[btn.getAttribute("data-cc")]; if (m) toggleSelect(m); });
    btn.addEventListener("mouseenter", function () { hovered = btn.getAttribute("data-cc"); });
    btn.addEventListener("mouseleave", function () { if (!dragging) hovered = null; });
  });

  // ---- boot ----------------------------------------------------------------
  function boot(topo) {
    buildGeometry(topo); readPalette(); buildStars(); buildIslands(); size();
    // The islands are built lazily (after a topo fetch + idle callback), so live.js's
    // first poll already ran against an empty DOM — nudge it to patch the fresh
    // .nb-px/.nb-chg index nodes now instead of waiting a full poll interval.
    if (window.LiveQuotes && window.LiveQuotes.refresh) window.LiveQuotes.refresh();
    // motion toggle in the slim strip (WCAG 2.2.2 stop control)
    var mbtn = stage.parentNode.querySelector(".gd-motion");
    if (mbtn) {
      var setM = function () {
        mbtn.innerHTML = motionOK ? bilingual("⏸ Pause motion", "⏸ 暂停动效") : bilingual("▶ Resume motion", "▶ 恢复动效");
        mbtn.setAttribute("aria-pressed", motionOK ? "false" : "true");
      };
      setM();
      mbtn.addEventListener("click", function () { motionOK = !motionOK; setM(); if (motionOK && !raf) raf = requestAnimationFrame(frame); });
    }
    if (poster) poster.style.opacity = "0";
    canvas.style.opacity = "1";
    render(performance.now());
    if (motionOK) raf = requestAnimationFrame(frame);
  }
  function start() {
    fetch(canvas.getAttribute("data-topo") || "world-110m.json").then(function (r) { return r.json(); })
      .then(boot).catch(function (err) { if (window.console) console.warn("globe: topo load failed", err); });
  }
  var resizeT;
  window.addEventListener("resize", function () { clearTimeout(resizeT); resizeT = setTimeout(size, 150); });
  if ("requestIdleCallback" in window) requestIdleCallback(start, { timeout: 1200 }); else setTimeout(start, 200);
})();

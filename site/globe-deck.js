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
  var fitScale = 240, scale = 240, W = 0, H = 0, R = 0, dpr = 1;

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
    R = Math.min(W, H) * 0.43;   // leaves room for the 1.16x atmosphere halo (never clipped)
    fitScale = R; scale = scale === 240 ? R : Math.min(R * 2.2, Math.max(R * 0.8, scale));
    apply();
  }
  function apply() { projection.rotate([rot[0], rot[1], 0]).scale(scale).translate([W / 2, H / 2]); }

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
    var atmo = ctx.createRadialGradient(cx, cy, scale * 0.92, cx, cy, scale * 1.16);
    atmo.addColorStop(0, rgba(PAL["--info"], 0));
    atmo.addColorStop(0.55, rgba(PAL["--info"], dark ? 0.22 : 0.12));
    atmo.addColorStop(1, rgba(PAL["--info"], 0));
    ctx.fillStyle = atmo;
    ctx.beginPath(); ctx.arc(cx, cy, scale * 1.16, 0, 6.283); ctx.fill();

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

    // labels for covered markets
    drawLabels();
  }

  function visible(lonlat) {
    var c = d3.geoRotation([rot[0], rot[1], 0])(lonlat);  // not used; use distance test
    return true;
  }
  function onFront(lonlat) {
    var center = [-rot[0], -rot[1]];
    return d3.geoDistance(lonlat, center) < Math.PI / 2;
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
    } else if (motionOK && (t - lastInteract) > 4000) {
      rot[0] += 0.12; apply();   // idle auto-rotate
    }
    render(t);
    raf = requestAnimationFrame(frame);
  }
  function clampLat(p) { return Math.max(-78, Math.min(78, p)); }

  // ---- interaction ---------------------------------------------------------
  var px = 0, py = 0, moved = 0, lastMoveT = 0;
  canvas.addEventListener("pointerdown", function (e) {
    dragging = true; flying = null; velX = velY = 0; moved = 0;
    px = e.clientX; py = e.clientY; lastInteract = performance.now();
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", function (e) {
    lastInteract = performance.now();
    if (dragging) {
      var k = 0.32 * (240 / scale);
      var dx = (e.clientX - px), dy = (e.clientY - py);
      rot[0] += dx * k; rot[1] = clampLat(rot[1] - dy * k);
      var nt = performance.now(), d = Math.max(8, nt - lastMoveT);
      velX = dx * k * (16 / d) * 0.6; velY = -dy * k * (16 / d) * 0.6; lastMoveT = nt;
      moved += Math.abs(dx) + Math.abs(dy); px = e.clientX; py = e.clientY; apply();
      hideTip();
    } else {
      hoverAt(e.clientX, e.clientY);
    }
  });
  canvas.addEventListener("pointerup", function (e) {
    dragging = false;
    if (moved < 5) { clickAt(e.clientX, e.clientY); }     // a click, not a drag
  });
  canvas.addEventListener("pointerleave", function () { if (!dragging) { hovered = null; hideTip(); } });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault(); lastInteract = performance.now();
    scale = Math.max(fitScale * 0.8, Math.min(fitScale * 2.4, scale * (e.deltaY < 0 ? 1.08 : 0.93))); apply();
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
    var m = pick(cx, cy);
    hovered = m ? m.cc : null;
    canvas.style.cursor = m ? "pointer" : "grab";
    if (m) showTip(m, cx, cy); else if (!selected) hideTip();
  }
  function clickAt(cx, cy) {
    var m = pick(cx, cy);
    if (m) selectMarket(m, cx, cy); else { selected = null; hideTip(); syncRows(); }
  }
  function selectMarket(m, cx, cy) {
    selected = m.cc; lastInteract = performance.now();
    var ll = m.kind === "marker" ? m.marker_lonlat : (byCC[m.cc] && paintCentroid(m.cc)) || [0, 0];
    flying = { t0: performance.now(), dur: 700, a0: rot[0], b0: rot[1], a1: -ll[0], b1: clampLat(-ll[1]), s0: scale, s1: Math.min(fitScale * 1.5, fitScale * 1.22) };
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
    return { open: open, lunch: lunch, next: next, label_en: label_en, label_zh: label_zh, frac: lp.min / 1440 };
  }
  function dur(mins) { var h = Math.floor(mins / 60), m = Math.round(mins % 60); return (h ? h + "h " : "") + m + "m"; }
  function sunmoon(frac) {
    var day = frac > 0.27 && frac < 0.79;        // ~6:30–19:00 local
    var ax = 14 * Math.sin(Math.PI * Math.max(0, Math.min(1, (frac - 0.27) / 0.52)));
    var ay = day ? (8 - 8 * Math.sin(Math.PI * (frac - 0.27) / 0.52)) : 6;
    if (day) return '<svg viewBox="0 0 32 20" class="gd-sm"><circle cx="' + (16 + ax - 14) + '" cy="' + (4 + ay) + '" r="4" fill="var(--warn)"/></svg>';
    return '<svg viewBox="0 0 32 20" class="gd-sm"><path d="M' + (18) + ' 5a5 5 0 1 0 0 10 6 6 0 0 1 0-10z" fill="var(--muted)"/></svg>';
  }
  var rowEls = {};
  function buildSidebar() {
    var ul = stage.parentNode.querySelector(".gd-clock ul"); if (!ul) return;
    DATA.slice().forEach(function (m) {
      var li = document.createElement("li"); li.className = "gd-row"; li.tabIndex = 0; li.setAttribute("data-cc", m.cc);
      li.innerHTML =
        '<span class="gd-r-sm"></span>' +
        '<span class="gd-r-main"><span class="gd-r-idx">' + m.flag + ' ' + bilingual(m.index_name_en, m.index_name_zh) + '</span>' +
        '<span class="gd-r-px">' + (m.index_price || "—") + ' <em style="color:' + ((m.index_chg_pct || 0) >= 0 ? "var(--up)" : "var(--down)") + '">' + ((m.index_chg_pct || 0) >= 0 ? "+" : "") + (m.index_chg_pct == null ? "" : m.index_chg_pct + "%") + '</em></span></span>' +
        '<span class="gd-r-state"><span class="gd-r-dot"></span><span class="gd-r-txt"></span><span class="gd-r-cd"></span></span>';
      li.addEventListener("click", function () { selectMarket(m); });
      li.addEventListener("mouseenter", function () { hovered = m.cc; });
      li.addEventListener("mouseleave", function () { if (!dragging) hovered = null; });
      ul.appendChild(li); rowEls[m.cc] = li;
    });
    updateClocks();
    setInterval(updateClocks, 1000);
    var utc = stage.parentNode.querySelector(".gd-utc");
    if (utc) setInterval(function () { utc.textContent = new Date().toISOString().slice(11, 16); }, 1000);
  }
  function updateClocks() {
    DATA.forEach(function (m) {
      var li = rowEls[m.cc]; if (!li) return;
      var st = clockState(m);
      li.querySelector(".gd-r-sm").innerHTML = sunmoon(st.frac);
      var dot = li.querySelector(".gd-r-dot"); dot.className = "gd-r-dot " + (st.open ? "on" : st.lunch ? "lunch" : "off");
      li.querySelector(".gd-r-txt").innerHTML = st.open ? bilingual("Open", "交易中") : st.lunch ? bilingual("Lunch", "午休") : bilingual("Closed", "休市");
      li.querySelector(".gd-r-cd").innerHTML = '<span class="l-en">' + st.label_en + ' ' + dur(st.next) + '</span><span class="l-zh">' + st.label_zh + ' ' + dur(st.next) + '</span>';
      li.classList.toggle("sel", selected === m.cc);
    });
  }
  function syncRows() { Object.keys(rowEls).forEach(function (cc) { rowEls[cc].classList.toggle("sel", selected === cc); }); }

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
    else if (k === "+" || k === "=") scale = Math.min(fitScale * 2.4, scale * 1.1);
    else if (k === "-") scale = Math.max(fitScale * 0.8, scale * 0.9);
    else if (k === "Escape") { selected = null; hideTip(); syncRows(); }
    else return;
    e.preventDefault(); apply();
  });
  stage.querySelectorAll(".gd-leg").forEach(function (btn) {
    btn.addEventListener("click", function () { var m = byCC[btn.getAttribute("data-cc")]; if (m) selectMarket(m); });
    btn.addEventListener("mouseenter", function () { hovered = btn.getAttribute("data-cc"); });
    btn.addEventListener("mouseleave", function () { if (!dragging) hovered = null; });
  });

  // ---- boot ----------------------------------------------------------------
  function boot(topo) {
    buildGeometry(topo); readPalette(); buildStars(); buildSidebar(); size();
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

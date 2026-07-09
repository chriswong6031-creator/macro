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
     "--text", "--bg", "--up", "--down", "--muted", "--warn", "--orange"].forEach(function (n) {
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
    // soft top/bottom fade so the globe dissolves into the page near the subtitle (above) and the
    // next-bell strip (below) — when zoomed in it fades out gracefully instead of a hard clip line
    var fade = "linear-gradient(to bottom, transparent 0%, #000 8%, #000 92%, transparent 100%)";
    canvas.style.webkitMaskImage = fade; canvas.style.maskImage = fade;
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
    // sphere + atmosphere halo + satellite orbits + touch margin. Mobile keeps the ORIGINAL
    // 1.13 disc (orbits are lowered there to fit inside it, see drawSatellites) so the canvas
    // edge bands still fall OUTSIDE it and a swipe scrolls the page instead of spinning the globe.
    var r = (W < 560 ? scale * 1.13 : scale * 1.26) + 4;
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

  // ---- city lights (dark only): clustered, twinkling metro glow on the night side ---
  // A curated set of major world metros ([lon, lat, weight 1..3]). Each is precomputed
  // ONCE (buildCities) into a CLUSTER of scattered specks — a warm-white core plus
  // amber/orange satellites on a unit disc, each with its own twinkle phase + frequency
  // and a lively "flasher" minority. drawCityLights() then paints them ADDITIVELY
  // (globalCompositeOperation "lighter") so overlapping specks bloom into real
  // "Earth-at-night" hotspots. Lights only appear on the night side (fading in through
  // dusk via a soft terminator ramp), are limb-feathered by frontness(), scale with zoom,
  // thin out on mobile, and freeze under prefers-reduced-motion.
  var CITY_SEED = [
    // North America
    [-74.0, 40.7, 3], [-118.2, 34.0, 3], [-87.6, 41.9, 2], [-122.4, 37.8, 2], [-95.4, 29.8, 2],
    [-80.2, 25.8, 2], [-79.4, 43.7, 2], [-73.6, 45.5, 1], [-123.1, 49.3, 1], [-122.3, 47.6, 1],
    [-96.8, 32.8, 1], [-84.4, 33.7, 1], [-71.1, 42.4, 1], [-77.0, 38.9, 2], [-99.1, 19.4, 3],
    // South America
    [-58.4, -34.6, 2], [-46.6, -23.6, 3], [-43.2, -22.9, 2], [-70.7, -33.4, 1], [-77.0, -12.0, 1], [-74.1, 4.7, 1],
    // Europe
    [-0.13, 51.5, 3], [2.35, 48.9, 3], [13.4, 52.5, 2], [12.5, 41.9, 2], [9.2, 45.5, 2],
    [-3.7, 40.4, 2], [2.17, 41.4, 1], [4.9, 52.4, 1], [8.68, 50.1, 1], [37.6, 55.8, 3],
    [28.98, 41.0, 3], [30.5, 50.5, 1], [23.7, 37.98, 1], [-9.14, 38.7, 1], [18.07, 59.3, 1],
    [16.37, 48.2, 1], [21.0, 52.2, 1], [24.9, 60.2, 1], [12.57, 55.7, 1],
    // Africa
    [31.24, 30.05, 3], [3.38, 6.5, 2], [28.05, -26.2, 2], [36.82, -1.29, 1], [-7.6, 33.6, 1],
    [18.42, -33.9, 1], [15.3, -4.3, 1], [39.27, -6.8, 1],
    // Middle East
    [55.27, 25.2, 2], [46.72, 24.7, 2], [51.4, 35.7, 2], [34.78, 32.08, 1], [44.4, 33.3, 1], [50.0, 26.2, 1],
    // East Asia — the Pearl River Delta (Guangzhou + HK) and Shanghai are single anchors:
    // adjacent conurbations were merged out (Shenzhen→HK, Suzhou→Shanghai) so their halos
    // don't stack into an additive white blowout under the "lighter" composite.
    [139.7, 35.68, 3], [135.5, 34.7, 2], [126.98, 37.57, 3], [116.4, 39.9, 3], [121.47, 31.23, 3],
    [113.26, 23.13, 2], [114.17, 22.28, 3], [121.56, 25.03, 2],
    [104.07, 30.67, 2], [114.3, 30.6, 1], [108.9, 34.3, 1],
    // South & Southeast Asia
    [72.88, 19.08, 3], [77.2, 28.6, 3], [77.59, 12.97, 2], [88.36, 22.57, 2], [80.27, 13.08, 1],
    [78.47, 17.4, 1], [100.5, 13.75, 2], [103.82, 1.35, 3], [106.8, -6.2, 3], [120.98, 14.6, 2],
    [101.69, 3.14, 1], [106.7, 10.8, 2], [67.0, 24.86, 3], [90.4, 23.8, 2], [105.85, 21.03, 1],
    // Oceania
    [151.2, -33.87, 2], [144.96, -37.8, 2], [153.0, -27.5, 1], [115.86, -31.95, 1], [174.76, -36.85, 1]
  ];
  var cities = [], DUSK = 0.5;   // radians of dusk ramp past the terminator (lights swell in as a city rotates into night)
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function buildCities() {
    cities = [];
    for (var i = 0; i < CITY_SEED.length; i++) {
      var s = CITY_SEED[i], w = s[2];
      var n = (w === 3 ? 9 : w === 2 ? 6 : 3) + Math.round(rnd(0, 2));   // satellites, scaled to metro size
      var pts = [];
      // bright warm-white core at the cluster centre (gets a soft bloom)
      pts.push({ ox: rnd(-0.12, 0.12), oy: rnd(-0.12, 0.12), rr: 1.6, tone: 0, glow: true,
                 b: 0.72, a: 0.24, f: 2 * Math.PI / rnd(1500, 2600), ph: rnd(0, 6.28), i: 1 });
      for (var j = 0; j < n; j++) {
        var ang = rnd(0, 6.283), rad = Math.sqrt(Math.random());          // sqrt → even area fill across the disc
        var flash = Math.random() < 0.16;                                 // lively minority that truly flashes
        var tone = Math.random() < 0.14 ? 0 : (Math.random() < 0.78 ? 1 : 2);  // white / amber / orange
        pts.push({ ox: Math.cos(ang) * rad, oy: Math.sin(ang) * rad,
                   rr: rnd(0.5, 1.1), tone: tone, glow: false,
                   b: flash ? 0.5 : 0.72, a: flash ? 0.5 : 0.24,
                   f: 2 * Math.PI / (flash ? rnd(600, 1200) : rnd(1400, 2800)), ph: rnd(0, 6.28),
                   i: rnd(0.5, 0.95) });
      }
      cities.push({ ll: [s[0], s[1]], w: w, rad: (w === 3 ? 1.5 : w === 2 ? 1.05 : 0.7), pts: pts });
    }
  }
  function drawCityLights(t, ss) {
    if (!cities.length) return;
    var mob = W < 560;
    var warm = PAL["--warn"], hot = PAL["--orange"], core = lerpColor(warm, "#ffffff", 0.55);
    var spread = scale * (mob ? 0.011 : 0.014);       // cluster radius in px (tracks zoom)
    var baseDot = Math.max(0.7, scale * 0.0065);      // speck radius in px (tracks zoom)
    ctx.save();
    ctx.globalCompositeOperation = "lighter";         // additive → clusters bloom like real city glow
    for (var i = 0; i < cities.length; i++) {
      var C = cities[i];
      if (mob && C.w < 2) continue;                   // thin the field on small screens
      var ll = C.ll;
      if (!onFront(ll)) continue;                     // back hemisphere — hidden by the opaque disc
      var dist = d3.geoDistance(ll, ss);
      var nightF = (dist - Math.PI / 2) / DUSK; if (nightF <= 0) continue; if (nightF > 1) nightF = 1;
      var frontF = frontness(ll); if (frontF <= 0) continue;
      var xy = projection(ll); if (!xy) continue;
      var vis = nightF * frontF, cr = spread * C.rad;
      // diffuse airglow dome over big metros (skipped on mobile for perf)
      if (C.w >= 2 && !mob) {
        var hr = cr * 2.8, halo = ctx.createRadialGradient(xy[0], xy[1], 0, xy[0], xy[1], hr);
        halo.addColorStop(0, rgba(warm, 0.07 * vis * (C.w - 0.5)));
        halo.addColorStop(1, rgba(warm, 0));
        ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(xy[0], xy[1], hr, 0, 6.283); ctx.fill();
      }
      var pts = C.pts, nn = mob ? Math.min(pts.length, 4) : pts.length;
      for (var j = 0; j < nn; j++) {
        var p = pts[j];
        var tw = motionOK ? (p.b + p.a * Math.sin(t * p.f + p.ph)) : (p.b + p.a * 0.35);
        if (tw <= 0) continue;
        var a = vis * tw * p.i; if (a <= 0.008) continue; if (a > 0.66) a = 0.66;   // ceiling: additive "lighter" pile-ups saturate gracefully instead of clipping to white
        var col = p.tone === 0 ? core : (p.tone === 1 ? warm : hot);
        if (p.glow && !mob) { ctx.shadowColor = rgba(col, 0.85 * vis); ctx.shadowBlur = cr * 1.2; }
        ctx.beginPath();
        ctx.arc(xy[0] + p.ox * cr, xy[1] + p.oy * cr, baseDot * p.rr, 0, 6.283);
        ctx.fillStyle = rgba(col, a); ctx.fill();
        if (p.glow && !mob) ctx.shadowBlur = 0;
      }
    }
    ctx.restore();
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

    // city lights — clustered, twinkling metro glow on the night side (dark theme only)
    if (dark) drawCityLights(t, ss);

    // shipping lanes + ships riding the ocean surface
    drawSeaRoutes(t, dark);

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

    // air corridors + planes flying above the hemisphere (drawn last → top layer)
    drawAirRoutes(t, dark);

    // orbital tier: mini satellites on faint white dotted orbits, way up high
    drawSatellites(t, dark);

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

  // ---- world trade & flight network: ships at sea, planes in the sky --------
  // Hand-placed lon/lat waypoints tracing the great commercial shipping lanes and
  // great-circle air corridors between major hubs. Each route is densified ONCE
  // into a near-even great-circle polyline so its glyph rides it at a steady clip.
  // Ships hug the ocean surface; planes fly an elevated arc and drop a moving
  // shadow on the water — in an orthographic view, lifting a point radially out
  // from the globe's screen centre by (1+altitude) is EXACTLY correct, so the
  // aircraft genuinely floats above the hemisphere. Sea lines breathe cool azure
  // (--info), air corridors warm gold (--warn); both pulse + drift like contrails.
  var SEA_LANES = [
    { name: "trans-pacific",    ships: 2, dur: 72000,  wp: [[121.5, 31.2], [140, 34], [170, 40], [-175, 41], [-140, 38], [-122.4, 37.6]] },
    { name: "transpac-south",   ships: 1, dur: 78000,  wp: [[121.8, 31.0], [145, 30], [178, 27], [-150, 25], [-125, 31], [-118.3, 33.7]] },
    { name: "trans-atlantic",   ships: 2, dur: 52000,  wp: [[-73.9, 40.5], [-55, 42], [-30, 47], [-9, 49.5], [1.5, 50.4], [4.1, 52.0]] },
    { name: "asia-europe-suez", ships: 2, dur: 150000, wp: [[103.8, 1.2], [95, 5.5], [80, 5.5], [63, 11], [52, 12.6], [43.3, 12.6], [38, 20], [33.9, 27.7], [32.3, 31.3], [25, 34], [14.5, 37], [4, 38], [-5.6, 35.9], [-9.5, 40], [-6, 47], [1.4, 50.2]] },
    { name: "gulf-asia-oil",    ships: 1, dur: 124000, wp: [[56.4, 26.6], [59, 24], [66, 20], [74, 9], [82, 6], [95, 4], [103.8, 1.3], [110, 4], [114, 12], [117, 19], [120.5, 29], [122, 31]] },
    { name: "europe-southam",   ships: 1, dur: 82000,  wp: [[-9, 38], [-16, 30], [-22, 16], [-30, 2], [-35, -12], [-42, -22], [-43.2, -23.0]] },
    { name: "asia-australia",   ships: 1, dur: 86000,  wp: [[114.2, 22.3], [112, 8], [110, -2], [116, -9], [125, -12], [138, -18], [148, -25], [151.2, -33.9]] }
  ];
  var AIR_ROUTES = [
    { name: "jfk-lhr", planes: 1, dur: 26000, a: [-73.78, 40.64],  b: [-0.45, 51.47] },
    { name: "lax-hnd", planes: 1, dur: 40000, a: [-118.4, 33.94],  b: [139.78, 35.55] },
    { name: "lhr-sin", planes: 1, dur: 44000, a: [-0.45, 51.47],   b: [103.99, 1.36] },
    { name: "dxb-jfk", planes: 1, dur: 38000, a: [55.36, 25.25],   b: [-73.78, 40.64] },
    { name: "hkg-sfo", planes: 1, dur: 42000, a: [113.91, 22.31],  b: [-122.38, 37.62] },
    { name: "syd-lax", planes: 1, dur: 46000, a: [151.18, -33.95], b: [-118.4, 33.94] },
    { name: "fra-pvg", planes: 1, dur: 40000, a: [8.57, 50.03],    b: [121.8, 31.14] },
    { name: "gru-jnb", planes: 1, dur: 34000, a: [-46.47, -23.43], b: [28.24, -26.13] }
  ];
  var seaPaths = [], airPaths = [];
  var SHADE = "#0a0e16";   // fixed near-black for vessel/aircraft shadows (theme-independent)
  function densify(wp) {
    var pts = [], STEP = 0.05;                       // ~3° between great-circle samples
    for (var i = 0; i < wp.length - 1; i++) {
      var A = wp[i], B = wp[i + 1], n = Math.max(1, Math.round(d3.geoDistance(A, B) / STEP)), ip = d3.geoInterpolate(A, B);
      for (var j = 0; j < n; j++) pts.push(ip(j / n));
    }
    pts.push(wp[wp.length - 1]);
    return pts;
  }
  function buildRoutes() {
    seaPaths = SEA_LANES.map(function (L) { return { def: L, pts: densify(L.wp) }; });
    airPaths = AIR_ROUTES.map(function (R) { return { def: R, pts: densify([R.a, R.b]) }; });
    buildOrbits();
  }
  function routeSample(pts, u) {                      // position + a look-ahead point for heading
    var n = pts.length; if (n < 2) return { p: pts[0], ahead: pts[0] };
    var f = u * (n - 1), i = Math.max(0, Math.min(n - 2, Math.floor(f))), fr = f - i, ip = d3.geoInterpolate(pts[i], pts[i + 1]);
    return { p: ip(Math.max(0, Math.min(1, fr))), ahead: ip(Math.min(1, fr + 0.2)) };
  }
  function elev(s, cx, cy, alt) { return [cx + (s[0] - cx) * (1 + alt), cy + (s[1] - cy) * (1 + alt)]; }

  function shipPath(sz) {                             // top-down hull, bow toward +x
    ctx.beginPath();
    ctx.moveTo(1.25 * sz, 0); ctx.lineTo(0.55 * sz, 0.40 * sz); ctx.lineTo(-0.95 * sz, 0.40 * sz);
    ctx.lineTo(-1.05 * sz, 0); ctx.lineTo(-0.95 * sz, -0.40 * sz); ctx.lineTo(0.55 * sz, -0.40 * sz);
    ctx.closePath();
  }
  function planePath(sz) {                            // top-down airliner, nose toward +x
    ctx.beginPath();
    ctx.moveTo(1.05 * sz, 0);
    ctx.lineTo(0.18 * sz, 0.15 * sz); ctx.lineTo(-0.12 * sz, 0.15 * sz); ctx.lineTo(-0.18 * sz, 0.60 * sz);
    ctx.lineTo(-0.36 * sz, 0.60 * sz); ctx.lineTo(-0.34 * sz, 0.12 * sz); ctx.lineTo(-0.80 * sz, 0.10 * sz);
    ctx.lineTo(-0.95 * sz, 0.34 * sz); ctx.lineTo(-1.04 * sz, 0.32 * sz); ctx.lineTo(-1.0 * sz, 0);
    ctx.lineTo(-1.04 * sz, -0.32 * sz); ctx.lineTo(-0.95 * sz, -0.34 * sz); ctx.lineTo(-0.80 * sz, -0.10 * sz);
    ctx.lineTo(-0.34 * sz, -0.12 * sz); ctx.lineTo(-0.36 * sz, -0.60 * sz); ctx.lineTo(-0.18 * sz, -0.60 * sz);
    ctx.lineTo(-0.12 * sz, -0.15 * sz); ctx.lineTo(0.18 * sz, -0.15 * sz);
    ctx.closePath();
  }

  function drawSeaRoutes(t, dark) {
    if (!seaPaths.length) return;
    var sea = PAL["--info"], mob = W < 560, sz = Math.max(4.2, Math.min(8.5, scale * 0.023));
    for (var r = 0; r < seaPaths.length; r++) {
      var R = seaPaths[r], def = R.def, pts = R.pts, ph = r * 1.7;
      var breath = motionOK ? (0.5 + 0.5 * Math.sin(t / 2600 + ph)) : 0.7;
      // breathing dotted lane (d3 geoPath auto-clips to the visible hemisphere)
      ctx.save();
      ctx.beginPath(); path({ type: "LineString", coordinates: pts });
      ctx.strokeStyle = rgba(sea, (dark ? 0.64 : 0.62) * (0.6 + 0.4 * breath));
      ctx.lineWidth = 1.25; ctx.setLineDash([1.6, 5]);
      ctx.lineDashOffset = motionOK ? -(t / 100 + ph * 20) : 0;
      ctx.shadowColor = rgba(sea, 0.6 * breath); ctx.shadowBlur = 3 + 3.5 * breath;
      ctx.stroke(); ctx.setLineDash([]); ctx.restore();
      // ships riding the lane
      var nShip = mob ? 1 : (def.ships || 1);
      for (var k = 0; k < nShip; k++) {
        var u = motionOK ? ((t / def.dur + k / nShip + r * 0.13) % 1) : ((k / nShip + r * 0.13 + 0.4) % 1);
        var smp = routeSample(pts, u); if (!onFront(smp.p)) continue;
        var s = projection(smp.p); if (!s) continue;
        var sa = projection(smp.ahead), ang = sa ? Math.atan2(sa[1] - s[1], sa[0] - s[0]) : 0;
        drawShip(s[0], s[1], ang, sz, sea, frontness(smp.p), t, ph, dark);
      }
    }
  }
  function drawShip(x, y, ang, sz, glow, fr, t, ph, dark) {
    var wob = motionOK ? Math.sin(t / 700 + ph) * 0.05 : 0;
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang + wob);
    ctx.globalAlpha = Math.max(0.28, fr);
    // soft shadow on the water (grounds the hull) — always dark, so it reads on a light ocean too
    ctx.save(); ctx.globalAlpha *= dark ? 0.40 : 0.26; ctx.fillStyle = rgba(SHADE, 1);
    ctx.beginPath(); ctx.ellipse(-sz * 0.1, sz * 0.16, sz * 1.15, sz * 0.5, 0, 0, 6.283); ctx.fill(); ctx.restore();
    // wake — luminous foam fanning back from the stern (sea-coloured so it shows in both themes)
    var wl = sz * (3.0 + (motionOK ? 0.7 * (0.5 + 0.5 * Math.sin(t / 360 + ph)) : 0.3));
    var g = ctx.createLinearGradient(-sz, 0, -sz - wl, 0);
    g.addColorStop(0, rgba(glow, dark ? 0.55 : 0.5)); g.addColorStop(1, rgba(glow, 0));
    ctx.fillStyle = g; ctx.beginPath();
    ctx.moveTo(-sz * 0.9, sz * 0.30); ctx.lineTo(-sz - wl, sz * 0.60);
    ctx.lineTo(-sz - wl, -sz * 0.60); ctx.lineTo(-sz * 0.9, -sz * 0.30); ctx.closePath(); ctx.fill();
    // hull — near-white in BOTH themes (in light mode --text is dark → a heavy blob), with a
    // thin slate outline so the pale hull still reads crisply on a light ocean; glow only in dark
    ctx.shadowColor = rgba(glow, 0.85); ctx.shadowBlur = dark ? 7 : 0;
    shipPath(sz); ctx.fillStyle = dark ? rgba(PAL["--text"], 0.94) : "rgba(252,253,255,0.97)"; ctx.fill(); ctx.shadowBlur = 0;
    if (!dark) { shipPath(sz); ctx.strokeStyle = rgba(PAL["--muted"], 0.62); ctx.lineWidth = Math.max(0.5, sz * 0.1); ctx.stroke(); }
    // deckhouse + bow running light
    ctx.fillStyle = rgba(glow, dark ? 0.85 : 0.92); ctx.fillRect(-sz * 0.55, -sz * 0.22, sz * 0.5, sz * 0.44);
    ctx.fillStyle = rgba(PAL["--orange"], 0.95); ctx.beginPath(); ctx.arc(sz * 0.85, 0, sz * 0.16, 0, 6.283); ctx.fill();
    ctx.restore();
  }

  function drawAirRoutes(t, dark) {
    if (!airPaths.length) return;
    var air = PAL["--warn"], cx = W / 2, cy = H / 2, mob = W < 560;
    var MAXALT = mob ? 0.095 : 0.13, sz = Math.max(5.5, Math.min(11.5, scale * 0.032));
    for (var r = 0; r < airPaths.length; r++) {
      var R = airPaths[r], def = R.def, pts = R.pts, ph = r * 1.3, n = pts.length;
      var breath = motionOK ? (0.5 + 0.5 * Math.sin(t / 2500 + ph)) : 0.7;
      // elevated breathing dotted corridor: project each sample, lift radially, skip the far side
      ctx.save();
      ctx.strokeStyle = rgba(air, (dark ? 0.6 : 0.58) * (0.6 + 0.4 * breath));
      ctx.lineWidth = 1.25; ctx.setLineDash([1.6, 5]);
      ctx.lineDashOffset = motionOK ? -(t / 85 + ph * 20) : 0;
      ctx.shadowColor = rgba(air, 0.6 * breath); ctx.shadowBlur = 3.5 + 3.5 * breath;
      ctx.beginPath();
      var started = false, iStep = mob ? 2 : 1;   // coarser sampling on mobile halves the per-frame trig
      for (var i = 0; i < n; i += iStep) {
        var ll = pts[i];
        // onFront() is the real culler: orthographic projection() still returns coords for
        // back-hemisphere points (folded onto the disc), so it can't break the line by itself
        if (!onFront(ll)) { started = false; continue; }
        var sp = projection(ll); if (!sp) { started = false; continue; }
        var e = elev(sp, cx, cy, MAXALT * Math.sin(Math.PI * (i / (n - 1))));
        if (!started) { ctx.moveTo(e[0], e[1]); started = true; } else ctx.lineTo(e[0], e[1]);
      }
      ctx.stroke(); ctx.setLineDash([]); ctx.restore();
      // aircraft flying the corridor (elevated body + shadow on the water below)
      var nP = mob ? 1 : (def.planes || 1);
      for (var k = 0; k < nP; k++) {
        var u = motionOK ? ((t / def.dur + k / nP + r * 0.21) % 1) : ((k / nP + r * 0.21 + 0.35) % 1);
        var smp = routeSample(pts, u); if (!onFront(smp.p)) continue;
        var s = projection(smp.p); if (!s) continue;
        var alt = MAXALT * Math.sin(Math.PI * u), e2 = elev(s, cx, cy, alt);
        var sa = projection(smp.ahead), ea = sa ? elev(sa, cx, cy, alt) : null;
        var ang = ea ? Math.atan2(ea[1] - e2[1], ea[0] - e2[0]) : 0, fr = frontness(smp.p);
        drawPlaneShadow(s[0], s[1], ang, sz, fr, alt);
        // altitude stem: a faint line from the water shadow up to the aircraft — reads as height
        if (alt > 0.012) {
          ctx.save();
          ctx.strokeStyle = rgba(air, 0.28 * fr); ctx.lineWidth = 1; ctx.setLineDash([1, 2.5]);
          ctx.beginPath(); ctx.moveTo(s[0], s[1]); ctx.lineTo(e2[0], e2[1]); ctx.stroke();
          ctx.setLineDash([]); ctx.restore();
        }
        drawPlane(e2[0], e2[1], ang, sz, air, fr, t, ph, pts, u, MAXALT, cx, cy, dark);
      }
    }
  }
  function drawPlaneShadow(x, y, ang, sz, fr, alt) {
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
    ctx.globalAlpha = 0.30 * fr; ctx.fillStyle = rgba(SHADE, 1);
    planePath(sz * 0.9 * (1 - Math.min(0.4, alt * 2.2))); ctx.fill();
    ctx.restore();
  }
  function drawPlane(x, y, ang, sz, glow, fr, t, ph, pts, u, MAXALT, cx, cy, dark) {
    // contrail — a few elevated points trailing behind, fading out. Wrapped in its own
    // save/restore (self-contained, no state leak) and skipped on mobile to save per-frame trig.
    var segs = W < 560 ? 0 : 5, trail = dark ? PAL["--text"] : PAL["--muted"];   // softer trail in light mode
    if (segs) {
      ctx.save();
      var prev = null;
      for (var c = 1; c <= segs; c++) {
        var uu = u - c * 0.016; if (uu < 0) break;
        var sp = routeSample(pts, uu).p; if (!onFront(sp)) { prev = null; continue; }
        var ss = projection(sp); if (!ss) { prev = null; continue; }
        var e = elev(ss, cx, cy, MAXALT * Math.sin(Math.PI * uu));
        if (prev) {
          ctx.beginPath(); ctx.moveTo(prev[0], prev[1]); ctx.lineTo(e[0], e[1]);
          ctx.strokeStyle = rgba(trail, 0.18 * fr * (1 - c / segs)); ctx.lineWidth = 1.6 * (1 - c / (segs + 2)); ctx.stroke();
        }
        prev = e;
      }
      ctx.restore();
    }
    // body — near-white in BOTH themes (light-mode --text is dark → a heavy blob); in light mode a
    // thin slate outline keeps the pale fuselage crisp on the bright sky, and the warm glow is dropped
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
    ctx.globalAlpha = Math.max(0.35, fr);
    ctx.shadowColor = rgba(glow, 0.95); ctx.shadowBlur = dark ? 9 : 0;
    planePath(sz); ctx.fillStyle = dark ? rgba(PAL["--text"], 0.97) : "rgba(252,253,255,0.98)"; ctx.fill(); ctx.shadowBlur = 0;
    if (!dark) { planePath(sz); ctx.strokeStyle = rgba(PAL["--muted"], 0.62); ctx.lineWidth = Math.max(0.5, sz * 0.08); ctx.stroke(); }
    ctx.fillStyle = rgba(glow, 0.95); ctx.beginPath(); ctx.arc(sz * 0.55, 0, sz * 0.14, 0, 6.283); ctx.fill();
    ctx.restore();
  }

  // ---- orbital tier: mini satellites circling on faint white dotted orbits ---
  // Way above the air corridors (constant high altitude, a FULL great-circle ring
  // round the whole globe). Each ring is a closed orbit defined by inclination +
  // ascending-node longitude; points are projected then lifted radially by the same
  // (1+alt) orthographic identity used for planes — only far higher. Real occlusion:
  // a ring point hides only when it's on the FAR side AND projects inside the globe
  // silhouette, so the ring sweeps in front of the planet, round the limb, and
  // vanishes behind it. The orbit is drawn as faint white DOTS (per-dot alpha → free
  // occlusion + a soft edge-fade so high rings dissolve at the canvas rim, never hard-clip).
  var DEG = Math.PI / 180;
  var SATS = [
    { inc: 64, node: 20,   alt: 0.20,  dur: 16000, n: 1 },
    { inc: 50, node: 135,  alt: 0.185, dur: 19500, n: 1 },
    { inc: 36, node: -85,  alt: 0.225, dur: 14000, n: 1 },
    { inc: 70, node: 250,  alt: 0.195, dur: 21000, n: 1 }
  ];
  var orbitPaths = [];
  function orbitLL(incDeg, nodeDeg, phi) {            // a point on the orbital great circle
    var inc = incDeg * DEG;
    var la = Math.asin(Math.sin(inc) * Math.sin(phi)) / DEG;
    var lo = nodeDeg + Math.atan2(Math.cos(inc) * Math.sin(phi), Math.cos(phi)) / DEG;
    return [lo, la];
  }
  function buildOrbits() {
    orbitPaths = SATS.map(function (S) {
      var N = 92, pts = [];
      for (var i = 0; i < N; i++) pts.push(orbitLL(S.inc, S.node, i / N * 2 * Math.PI));
      return { def: S, pts: pts };
    });
  }
  function edgeFade(x, y) {                           // 0 at the canvas rim → 1 well inside it
    return Math.max(0, Math.min(1, Math.min(x, W - x, y, H - y) / 38));
  }
  function drawSatellites(t, dark) {
    if (!orbitPaths.length) return;
    var col = PAL["--text"], cx = W / 2, cy = H / 2, mob = W < 560;
    var list = mob ? orbitPaths.slice(0, 2) : orbitPaths;
    var altK = mob ? 0.7 : 1;                          // lower orbits on mobile so the ring stays inside the 1.13 clip (preserves page-scroll)
    var sz = Math.max(4.5, Math.min(10, scale * 0.026)), dotR = Math.max(0.8, scale * 0.0036);
    for (var r = 0; r < list.length; r++) {
      var O = list[r], def = O.def, pts = O.pts, n = pts.length, ph = r * 1.9, alt = def.alt * altK;
      var breath = motionOK ? (0.62 + 0.38 * Math.sin(t / 3000 + ph)) : 0.85;
      // faint dotted orbit ring (per-dot occlusion: near side always; far side only outside the disc)
      var iStep = mob ? 2 : 1;
      for (var i = 0; i < n; i += iStep) {
        var ll = pts[i], sp = projection(ll); if (!sp) continue;
        var ex = cx + (sp[0] - cx) * (1 + alt), ey = cy + (sp[1] - cy) * (1 + alt);
        var nf = onFront(ll);
        if (!nf && Math.hypot(ex - cx, ey - cy) <= scale + 1) continue;   // far side, hidden behind the disc
        var fade = edgeFade(ex, ey); if (fade <= 0) continue;
        var a = (dark ? 0.46 : 0.40) * breath * fade * (nf ? 1 : 0.66);
        ctx.beginPath(); ctx.arc(ex, ey, dotR, 0, 6.283); ctx.fillStyle = rgba(col, a); ctx.fill();
      }
      // satellites riding the ring
      var nS = mob ? 1 : (def.n || 1);
      for (var k = 0; k < nS; k++) {
        var u = motionOK ? ((t / def.dur + k / nS + r * 0.27) % 1) : ((k / nS + r * 0.27 + 0.2) % 1);
        var phi = u * 2 * Math.PI, p0 = orbitLL(def.inc, def.node, phi), s0 = projection(p0); if (!s0) continue;
        var sx = cx + (s0[0] - cx) * (1 + alt), sy = cy + (s0[1] - cy) * (1 + alt);
        var nf0 = onFront(p0);
        if (!nf0 && Math.hypot(sx - cx, sy - cy) <= scale + 1) continue;  // far side, behind the disc
        var sf = edgeFade(sx, sy); if (sf <= 0) continue;
        var p1 = orbitLL(def.inc, def.node, phi + 0.06), s1 = projection(p1);
        var ang = s1 ? Math.atan2((cy + (s1[1] - cy) * (1 + alt)) - sy, (cx + (s1[0] - cx) * (1 + alt)) - sx) : 0;
        drawSat(sx, sy, ang, sz, col, (nf0 ? 1 : 0.78) * sf, t, ph);
      }
    }
  }
  function drawSat(x, y, ang, sz, col, a, t, ph) {
    var tw = motionOK ? (0.72 + 0.28 * Math.sin(t / 420 + ph)) : 1;
    ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
    ctx.globalAlpha = Math.min(1, a);
    // solar-panel wings (perpendicular to travel) — wide blue arrays so the silhouette reads as a satellite
    var pw = sz * 0.52, pl = sz * 0.82;
    ctx.fillStyle = rgba(PAL["--info"], 0.85);
    ctx.fillRect(-pw / 2, -sz * 1.52, pw, pl);   // top wing
    ctx.fillRect(-pw / 2, sz * 0.70, pw, pl);    // bottom wing
    // cell-division spine on each panel (suggests a solar array)
    ctx.strokeStyle = rgba(col, 0.4); ctx.lineWidth = Math.max(0.4, sz * 0.06);
    ctx.beginPath();
    ctx.moveTo(0, -sz * 1.52); ctx.lineTo(0, -sz * 1.52 + pl);
    ctx.moveTo(0, sz * 0.70); ctx.lineTo(0, sz * 0.70 + pl);
    ctx.stroke();
    // strut + body (bright, glowing)
    ctx.strokeStyle = rgba(col, 0.65); ctx.lineWidth = Math.max(0.6, sz * 0.11);
    ctx.beginPath(); ctx.moveTo(0, -sz * 0.7); ctx.lineTo(0, sz * 0.7); ctx.stroke();
    ctx.shadowColor = rgba(col, 0.95 * tw); ctx.shadowBlur = 7;
    ctx.fillStyle = rgba(col, 0.97); ctx.beginPath(); ctx.arc(0, 0, sz * 0.44, 0, 6.283); ctx.fill();
    ctx.restore();
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
    var next;
    if (open) { next = c - now; if (m.lunch) { var l0 = hm(m.lunch[0]); if (now < l0) next = l0 - now; } }
    else if (lunch) { next = hm(m.lunch[1]) - now; }
    else { // closed: minutes to next open (today or next weekday)
      var add = 0, day = lp.wd;
      if (!weekend && now < o) add = o - now;
      else { add = (24 * 60 - now) + o; var seq = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]; var di = seq.indexOf(day); var d2 = (di + 1) % 7; while (d2 === 0 || d2 === 6) { add += 24 * 60; d2 = (d2 + 1) % 7; } }
      next = add;
    }
    // arc = fraction of the current span still remaining (full ring → empties toward the bell)
    var arc = 0;
    if (open) { var span = c - o; arc = span > 0 ? Math.max(0, Math.min(1, next / span)) : 0; }
    else if (lunch) { var sp = hm(m.lunch[1]) - hm(m.lunch[0]); arc = sp > 0 ? Math.max(0, Math.min(1, next / sp)) : 0; }
    return { open: open, lunch: lunch, next: next, frac: lp.min / 1440, arc: arc };
  }
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
    DATA.forEach(function (m) {
      var el = islEls[m.cc]; if (!el) return;
      var st = clockState(m);
      var pre = (st.open && st.next <= 15) || (!st.open && !st.lunch && st.next <= 15);
      el.querySelector(".isl-sem").className = "isl-sem " + (st.open ? (pre ? "pre" : "open") : st.lunch ? "lunch" : pre ? "pre" : "closed");
      var arcEl = el.querySelector(".arc");
      if (arcEl) { var shown = st.open || st.lunch; arcEl.style.strokeDasharray = RINGC.toFixed(2); arcEl.style.strokeDashoffset = (RINGC * (1 - (shown ? st.arc : 0))).toFixed(2); arcEl.style.stroke = pre ? "var(--warn)" : "var(--qc)"; arcEl.style.opacity = shown ? "1" : "0"; }
      el.classList.toggle("sel", selected === m.cc);
    });
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
    buildGeometry(topo); buildRoutes(); readPalette(); buildStars(); buildCities(); buildIslands(); size();
    // The islands are built lazily (after a topo fetch + idle callback), so live.js's
    // first poll already ran against an empty DOM — nudge it to patch the fresh
    // .nb-px/.nb-chg index nodes now instead of waiting a full poll interval.
    if (window.LiveQuotes && window.LiveQuotes.refresh) window.LiveQuotes.refresh();
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

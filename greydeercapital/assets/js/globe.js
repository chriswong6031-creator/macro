/* ==========================================================================
   GREY DEER CAPITAL — globe.js  (the signature artifact)
   An atmospheric d3-geoOrthographic planet: muted landmasses, a whisper of
   graticule, capital-flow arcs that travel warm (fawn) -> cool (glacial) and
   converge at glowing signal-nodes over the world's financial centers, and
   faint orbital signal paths. Slow auto-rotation; drag to spin with inertia.
   Reuses the vendored d3 + topojson stack. Gated on prefers-reduced-motion.
   ========================================================================== */
(function () {
  "use strict";
  var d3 = window.d3, topojson = window.topojson;
  var host = document.querySelector("[data-globe]");
  if (!host || !d3 || !topojson) return;

  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  var canvas = document.createElement("canvas");
  canvas.className = "gd-globe__canvas";
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label",
    "A slowly rotating globe tracing capital flows between the world's financial centers.");
  host.appendChild(canvas);
  var ctx = canvas.getContext("2d");

  /* --- palette (read tokens, fall back to literals) --------------------- */
  function cssv(n, f) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    return v || f;
  }
  var COL = {
    fawn:    cssv("--fawn", "#C7B299"),
    fawnHi:  cssv("--fawn-bright", "#E4D5BE"),
    glacial: cssv("--glacial", "#63B4AC"),
    glacHi:  cssv("--glacial-bright", "#9BD8D0"),
    fog:     cssv("--fog", "#97A4AD")
  };
  function rgb(hex) {
    hex = hex.replace("#", "");
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    return [parseInt(hex.slice(0,2),16), parseInt(hex.slice(2,4),16), parseInt(hex.slice(4,6),16)];
  }
  function lerp(a, b, t) {
    var x = rgb(a), y = rgb(b);
    return "rgb(" + Math.round(x[0]+(y[0]-x[0])*t) + "," + Math.round(x[1]+(y[1]-x[1])*t) + "," + Math.round(x[2]+(y[2]-x[2])*t) + ")";
  }

  /* --- geometry --------------------------------------------------------- */
  var projection = d3.geoOrthographic().precision(0.5);
  var path = d3.geoPath(projection, ctx);
  var graticule = d3.geoGraticule10();
  var sphere = { type: "Sphere" };
  var land = null, borders = null;
  var rot = [ -25, -14 ];   // start over the Atlantic, tilted north
  var W = 0, H = 0, R = 0, cx = 0, cy = 0, dpr = 1;

  /* the world's financial centers — nodes of the capital network */
  var CENTERS = [
    { id: "nyc", ll: [-74.0, 40.7],   w: 1.0 },
    { id: "sf",  ll: [-122.4, 37.77], w: 0.7 },
    { id: "tor", ll: [-79.4, 43.7],   w: 0.55 },
    { id: "spo", ll: [-46.63, -23.55],w: 0.5 },
    { id: "ldn", ll: [-0.13, 51.5],   w: 1.0 },
    { id: "fra", ll: [8.68, 50.1],    w: 0.6 },
    { id: "zur", ll: [8.54, 47.4],    w: 0.5 },
    { id: "dxb", ll: [55.27, 25.2],   w: 0.6 },
    { id: "mum", ll: [72.87, 19.07],  w: 0.55 },
    { id: "sgp", ll: [103.82, 1.35],  w: 0.7 },
    { id: "hkg", ll: [114.17, 22.32], w: 0.85 },
    { id: "sha", ll: [121.47, 31.23], w: 0.7 },
    { id: "tyo", ll: [139.69, 35.68], w: 0.8 },
    { id: "syd", ll: [151.2, -33.87], w: 0.5 }
  ];
  var C = {}; CENTERS.forEach(function (c) { C[c.id] = c.ll; });
  var LINKS = [
    ["nyc","ldn"], ["nyc","sf"], ["nyc","tor"], ["nyc","spo"],
    ["ldn","fra"], ["ldn","zur"], ["ldn","dxb"], ["ldn","hkg"],
    ["fra","zur"], ["dxb","mum"], ["mum","sgp"],
    ["hkg","sha"], ["hkg","tyo"], ["hkg","sgp"],
    ["sgp","syd"], ["tyo","sf"]
  ];
  // precompute great-circle samplers + a phase per link so pulses stagger
  var ARCS = LINKS.map(function (l, i) {
    return { a: C[l[0]], b: C[l[1]], interp: d3.geoInterpolate(C[l[0]], C[l[1]]), phase: (i * 0.137) % 1, speed: 0.06 + (i % 3) * 0.018 };
  });

  function visible(ll, center) { return d3.geoDistance(ll, center) < 1.5707; }

  /* --- sizing ----------------------------------------------------------- */
  function size() {
    var rect = host.getBoundingClientRect();
    W = Math.max(240, rect.width);
    H = Math.max(240, rect.height);
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    R = Math.min(W, H) * 0.44;
    cx = W / 2; cy = H / 2;
    projection.translate([cx, cy]).scale(R);
  }

  /* --- drawing ---------------------------------------------------------- */
  function drawSphere() {
    // atmosphere halo
    var halo = ctx.createRadialGradient(cx, cy, R * 0.86, cx, cy, R * 1.32);
    halo.addColorStop(0, "rgba(99,180,172,0.16)");
    halo.addColorStop(0.5, "rgba(99,180,172,0.05)");
    halo.addColorStop(1, "rgba(99,180,172,0)");
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.32, 0, 2 * Math.PI);
    ctx.fillStyle = halo; ctx.fill();
    // ocean sphere with soft top-left light
    var oc = ctx.createRadialGradient(cx - R * 0.35, cy - R * 0.4, R * 0.1, cx, cy, R);
    oc.addColorStop(0, "#17262a");
    oc.addColorStop(0.6, "#0f1a1d");
    oc.addColorStop(1, "#0a1012");
    ctx.beginPath(); path(sphere); ctx.fillStyle = oc; ctx.fill();
  }
  function drawGraticule() {
    ctx.beginPath(); path(graticule);
    ctx.strokeStyle = "rgba(151,164,173,0.06)"; ctx.lineWidth = 0.6; ctx.stroke();
  }
  function drawLand() {
    if (!land) return;
    ctx.beginPath(); path(land);
    var lg = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.35, R * 0.1, cx, cy, R);
    lg.addColorStop(0, "rgba(38,52,58,0.92)");
    lg.addColorStop(1, "rgba(24,34,38,0.86)");
    ctx.fillStyle = lg; ctx.fill();
    // fawn coastline whisper
    ctx.beginPath(); path(land);
    ctx.strokeStyle = "rgba(199,178,153,0.18)"; ctx.lineWidth = 0.6; ctx.stroke();
  }
  function drawArcs(time) {
    var center = [-rot[0], -rot[1]];
    ARCS.forEach(function (arc) {
      // static faint line, sampled across visible span
      var N = 44, prev = null, started = false;
      ctx.beginPath();
      for (var i = 0; i <= N; i++) {
        var ll = arc.interp(i / N);
        if (!visible(ll, center)) { started = false; continue; }
        var p = projection(ll);
        if (!started) { ctx.moveTo(p[0], p[1]); started = true; } else { ctx.lineTo(p[0], p[1]); }
      }
      ctx.strokeStyle = "rgba(146,164,173,0.10)"; ctx.lineWidth = 0.8; ctx.stroke();

      // travelling pulse (comet), warm -> cool along its journey
      var t = (arc.phase + time * arc.speed) % 1;
      var TAIL = 7;
      for (var k = 0; k < TAIL; k++) {
        var tt = t - k * 0.012;
        if (tt < 0 || tt > 1) continue;
        var ll2 = arc.interp(tt);
        if (!visible(ll2, center)) continue;
        var q = projection(ll2);
        var a = (1 - k / TAIL);
        var col = lerp(COL.fawn, COL.glacHi, tt);
        ctx.beginPath();
        ctx.arc(q[0], q[1], (k === 0 ? 2.1 : 1.5) * (0.6 + a * 0.6), 0, 2 * Math.PI);
        ctx.fillStyle = col.replace("rgb", "rgba").replace(")", "," + (0.14 + a * 0.7) + ")");
        if (k === 0) { ctx.shadowBlur = 10; ctx.shadowColor = COL.glacHi; }
        ctx.fill(); ctx.shadowBlur = 0;
      }
    });
  }
  function drawNodes(time) {
    var center = [-rot[0], -rot[1]];
    CENTERS.forEach(function (c, i) {
      if (!visible(c.ll, center)) return;
      var p = projection(c.ll);
      var pulse = 0.5 + 0.5 * Math.sin(time * 1.6 + i);
      // outer pulse ring
      ctx.beginPath();
      ctx.arc(p[0], p[1], 3 + c.w * 6 * (0.5 + pulse * 0.5), 0, 2 * Math.PI);
      ctx.strokeStyle = "rgba(99,180,172," + (0.05 + (1 - pulse) * 0.16) + ")";
      ctx.lineWidth = 1; ctx.stroke();
      // core
      ctx.beginPath();
      ctx.arc(p[0], p[1], 1.4 + c.w * 1.6, 0, 2 * Math.PI);
      ctx.fillStyle = COL.fawnHi;
      ctx.shadowBlur = 8; ctx.shadowColor = COL.fawn;
      ctx.fill(); ctx.shadowBlur = 0;
    });
  }
  function drawOrbits(time) {
    // two faint tilted orbital signal rings + a travelling node on each
    var rings = [ { r: R * 1.16, ry: 0.30, sp: 0.16, off: 0 }, { r: R * 1.24, ry: 0.20, sp: -0.11, off: 2 } ];
    rings.forEach(function (o) {
      ctx.save();
      ctx.translate(cx, cy); ctx.rotate(-0.36);
      ctx.beginPath();
      ctx.ellipse(0, 0, o.r, o.r * o.ry, 0, 0, 2 * Math.PI);
      ctx.strokeStyle = "rgba(151,164,173,0.07)"; ctx.lineWidth = 1; ctx.stroke();
      var ang = time * o.sp + o.off;
      var ox = Math.cos(ang) * o.r, oy = Math.sin(ang) * o.r * o.ry;
      ctx.beginPath(); ctx.arc(ox, oy, 1.8, 0, 2 * Math.PI);
      ctx.fillStyle = COL.glacHi; ctx.shadowBlur = 8; ctx.shadowColor = COL.glacial;
      ctx.fill(); ctx.shadowBlur = 0;
      ctx.restore();
    });
  }

  function render(time) {
    ctx.clearRect(0, 0, W, H);
    projection.rotate([rot[0], rot[1], 0]);
    drawOrbits(time);
    drawSphere();
    drawGraticule();
    drawLand();
    drawArcs(time);
    drawNodes(time);
  }

  /* --- interaction: drag to spin, inertia, auto-rotate ------------------ */
  var dragging = false, lastX = 0, lastY = 0, vx = 0, vy = 0, running = true;
  function onDown(e) {
    dragging = true; vx = vy = 0;
    lastX = (e.touches ? e.touches[0].clientX : e.clientX);
    lastY = (e.touches ? e.touches[0].clientY : e.clientY);
    canvas.style.cursor = "grabbing";
  }
  function onMove(e) {
    if (!dragging) return;
    var x = (e.touches ? e.touches[0].clientX : e.clientX);
    var y = (e.touches ? e.touches[0].clientY : e.clientY);
    var dx = x - lastX, dy = y - lastY;
    lastX = x; lastY = y;
    var k = 0.25;
    rot[0] += dx * k; rot[1] = Math.max(-72, Math.min(72, rot[1] - dy * k));
    vx = dx * k; vy = -dy * k;
    if (e.cancelable && Math.abs(dx) > Math.abs(dy)) e.preventDefault();
  }
  function onUp() { dragging = false; canvas.style.cursor = "grab"; }

  canvas.style.cursor = "grab";
  canvas.addEventListener("mousedown", onDown);
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  canvas.addEventListener("touchstart", onDown, { passive: true });
  canvas.addEventListener("touchmove", onMove, { passive: false });
  canvas.addEventListener("touchend", onUp);

  var t0 = null;
  function loop(ts) {
    if (t0 === null) t0 = ts;
    var time = (ts - t0) / 1000;
    if (!dragging) {
      // inertia decay + gentle auto-rotate
      rot[0] += vx; rot[1] = Math.max(-72, Math.min(72, rot[1] + vy));
      vx *= 0.94; vy *= 0.94;
      if (Math.abs(vx) < 0.02) vx = 0;
      if (Math.abs(vy) < 0.02) vy = 0;
      rot[0] += 0.045;   // slow drift westward
    }
    if (running) render(time);
    requestAnimationFrame(loop);
  }

  /* --- boot ------------------------------------------------------------- */
  function start() {
    size();
    if (reduce) { render(0.2); return; }   // one poised frame, no motion
    requestAnimationFrame(loop);
  }

  var resizeT;
  window.addEventListener("resize", function () {
    clearTimeout(resizeT);
    resizeT = setTimeout(function () { size(); if (reduce) render(0.2); }, 140);
  });
  // pause when scrolled far offscreen (perf)
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (es) { running = es[0].isIntersecting; })
      .observe(host);
  }

  fetch("assets/vendor/world-110m.json")
    .then(function (r) { return r.json(); })
    .then(function (topo) {
      land = topojson.merge(topo, topo.objects.countries.geometries);
      start();
    })
    .catch(function () { /* globe is decorative; the hero still stands without it */ start(); });
})();

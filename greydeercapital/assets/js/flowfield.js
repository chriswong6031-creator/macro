/* ==========================================================================
   GREY DEER CAPITAL — flowfield.js
   "Capital as water." A whisper-quiet flow field: particles drift along a
   smooth vector field (cheap layered-sine noise, no libs), leaving fawn +
   glacial current lines that fade like tide marks. Attaches to any
   [data-flow] element, sizes to it, pauses offscreen, honours reduced motion.
   ========================================================================== */
(function () {
  "use strict";
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hosts = document.querySelectorAll("[data-flow]");
  if (!hosts.length) return;

  function field(x, y, t) {
    // smooth divergence-free-ish angle from layered sines
    return Math.sin(x * 0.0016 + t * 0.10) * 1.7 +
           Math.cos(y * 0.0021 - t * 0.08) * 1.4 +
           Math.sin((x + y) * 0.0012 + t * 0.05) * 1.1;
  }

  function make(host) {
    var canvas = document.createElement("canvas");
    canvas.className = "gd-flow__canvas";
    canvas.setAttribute("aria-hidden", "true");
    host.appendChild(canvas);
    var ctx = canvas.getContext("2d");
    var W = 0, H = 0, dpr = 1, parts = [], running = true;

    var density = host.getAttribute("data-flow-density") === "high" ? 0.00018 : 0.00010;

    function size() {
      var r = host.getBoundingClientRect();
      W = Math.max(2, r.width); H = Math.max(2, r.height);
      dpr = Math.min(1.75, window.devicePixelRatio || 1);
      canvas.width = W * dpr; canvas.height = H * dpr;
      canvas.style.width = W + "px"; canvas.style.height = H + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var n = Math.min(320, Math.max(40, Math.floor(W * H * density)));
      parts = [];
      for (var i = 0; i < n; i++) parts.push(spawn());
      ctx.clearRect(0, 0, W, H);
    }
    function spawn() {
      return {
        x: Math.random() * W, y: Math.random() * H,
        life: 40 + Math.random() * 120,
        warm: Math.random() < 0.5
      };
    }

    var t = 0;
    function step() {
      t += 0.016;
      // fade prior frame toward transparent (tide-mark trails)
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "rgba(0,0,0,0.045)";
      ctx.fillRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i];
        var a = field(p.x, p.y, t);
        var nx = p.x + Math.cos(a) * 0.9;
        var ny = p.y + Math.sin(a) * 0.9;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y); ctx.lineTo(nx, ny);
        ctx.strokeStyle = p.warm ? "rgba(199,178,153,0.16)" : "rgba(99,180,172,0.16)";
        ctx.lineWidth = 0.8; ctx.stroke();
        p.x = nx; p.y = ny; p.life--;
        if (p.life <= 0 || p.x < -10 || p.x > W + 10 || p.y < -10 || p.y > H + 10) parts[i] = spawn();
      }
      if (running) requestAnimationFrame(step);
    }

    size();
    if (reduce) {
      // paint a few faint static strokes so it isn't blank, then stop
      ctx.globalCompositeOperation = "lighter";
      for (var s = 0; s < 60; s++) {
        var p = spawn(), a = field(p.x, p.y, 1.2);
        ctx.beginPath(); ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x + Math.cos(a) * 14, p.y + Math.sin(a) * 14);
        ctx.strokeStyle = p.warm ? "rgba(199,178,153,0.10)" : "rgba(99,180,172,0.10)";
        ctx.lineWidth = 0.8; ctx.stroke();
      }
      return;
    }
    requestAnimationFrame(step);

    var rt;
    window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(size, 160); });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        var vis = es[0].isIntersecting;
        if (vis && !running) { running = true; requestAnimationFrame(step); }
        running = vis;
      }).observe(host);
    }
  }

  hosts.forEach(make);
})();

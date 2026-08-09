/* /stocks/ market hub — instant search over the full coverage universe.
   The page it replaces shipped 1,544 DOM cards (887 KB) and filtered them by
   toggling style.display. This ships one compact array and renders only the
   rows on screen, so the same universe costs a fraction of the bytes and the
   filter is O(n) over numbers instead of O(n) over layout. */
(function () {
  "use strict";
  var ROWS = window.__HUB_ROWS || [];        // [t, name, sector, px, chg, stance, capBn, rvol, pos52]
  var SEC = window.__HUB_SEC || {};
  var ST = window.__HUB_STANCE || {};
  var T = 0, NM = 1, SC = 2, PX = 3, CH = 4, STK = 5, CAP = 6, RV = 7;

  var q = document.getElementById("q");
  var out = document.getElementById("rows");
  var meta = document.getElementById("res-meta");
  var moreBtn = document.getElementById("more");
  var resSec = document.getElementById("res");
  if (!q || !out) return;

  var state = { q: "", sec: "", st: "", dir: "", cap: "", sort: "cap", page: 1 };
  var PAGE = 25;
  var lower = ROWS.map(function (r) { return (r[T] + " " + r[NM]).toLowerCase(); });

  function match() {
    var needle = state.q.trim().toLowerCase();
    var hits = [];
    for (var i = 0; i < ROWS.length; i++) {
      var r = ROWS[i];
      if (state.sec && r[SC] !== state.sec) continue;
      if (state.st && r[STK] !== state.st) continue;
      if (state.dir === "up" && r[CH] <= 0) continue;
      if (state.dir === "dn" && r[CH] >= 0) continue;
      if (state.cap === "mega" && r[CAP] < 200) continue;
      if (state.cap === "large" && (r[CAP] < 10 || r[CAP] >= 200)) continue;
      if (state.cap === "mid" && r[CAP] >= 10) continue;
      if (needle) {
        var hay = lower[i];
        var p = hay.indexOf(needle);
        if (p < 0) continue;
        // exact ticker first, then ticker prefix, then name hit
        r.__s = r[T].toLowerCase() === needle ? 0
              : r[T].toLowerCase().indexOf(needle) === 0 ? 1
              : p === 0 ? 2 : 3;
      } else { r.__s = 0; }
      hits.push(r);
    }
    var by = state.sort;
    hits.sort(function (a, b) {
      if (needle && a.__s !== b.__s) return a.__s - b.__s;
      if (by === "chg") return b[CH] - a[CH];
      if (by === "chgd") return a[CH] - b[CH];
      if (by === "rvol") return b[RV] - a[RV];
      if (by === "az") return a[T] < b[T] ? -1 : 1;
      return b[CAP] - a[CAP];
    });
    return hits;
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function mark(text, needle) {
    if (!needle) return esc(text);
    var i = text.toLowerCase().indexOf(needle);
    if (i < 0) return esc(text);
    return esc(text.slice(0, i)) + "<mark>" + esc(text.slice(i, i + needle.length))
         + "</mark>" + esc(text.slice(i + needle.length));
  }

  var TONE = { uptrend: "up", recovering: "up", downtrend: "down",
               extended: "warn", topping: "warn", basing: "", aside: "" };

  function render() {
    var hits = match();
    var needle = state.q.trim().toLowerCase();
    var shown = Math.min(hits.length, state.page * PAGE);
    var html = "";
    for (var i = 0; i < shown; i++) {
      var r = hits[i];
      var sec = SEC[r[SC]] || [r[SC], r[SC]];
      var st = ST[r[STK]] || [r[STK], r[STK]];
      var up = r[CH] >= 0;
      html += '<a class="rrow" href="' + esc(r[T]) + '.html">'
        + '<span class="r-tk">' + mark(r[T], needle) + "</span>"
        + '<span class="r-nm">' + mark(r[NM], needle) + "</span>"
        + '<span class="r-sec"><span class="l-en">' + esc(sec[0]) + "</span>"
        + '<span class="l-zh">' + esc(sec[1]) + "</span></span>"
        + '<span class="r-px">$' + r[PX].toFixed(2) + "</span>"
        + '<span class="r-chg ' + (up ? "up" : "dn") + '">'
        + (up ? "+" : "") + r[CH].toFixed(2) + "%</span>"
        + '<span class="r-st t-' + (TONE[r[STK]] || "") + '">'
        + '<span class="l-en">' + esc(st[0]) + "</span>"
        + '<span class="l-zh">' + esc(st[1]) + "</span></span></a>";
    }
    if (!hits.length) {
      out.innerHTML = '<div class="empty"><b>'
        + '<span class="l-en">Nothing matches that</span>'
        + '<span class="l-zh">没有匹配结果</span></b>'
        + '<span class="l-en">Try a ticker (AAPL) or a company name — or clear a filter.</span>'
        + '<span class="l-zh">试试代码（AAPL）或公司名称 —— 或清除一个筛选条件。</span></div>';
    } else {
      out.innerHTML = html;
    }
    moreBtn.hidden = shown >= hits.length;
    moreBtn.textContent = "";
    if (!moreBtn.hidden) {
      moreBtn.innerHTML = '<span class="l-en">Show '
        + Math.min(PAGE, hits.length - shown) + " more of " + hits.length.toLocaleString()
        + "</span><span class=\"l-zh\">再显示 " + Math.min(PAGE, hits.length - shown)
        + " 只（共 " + hits.length.toLocaleString() + "）</span>";
    }
    meta.innerHTML = '<span class="l-en"><b>' + hits.length.toLocaleString()
      + "</b> of " + ROWS.length.toLocaleString() + " covered</span>"
      + '<span class="l-zh">覆盖 ' + ROWS.length.toLocaleString()
      + " 只中的 <b>" + hits.length.toLocaleString() + "</b> 只</span>";
    // The results block only earns its space once the reader has asked for it.
    var active = !!(needle || state.sec || state.st || state.dir || state.cap);
    resSec.hidden = !active;
  }

  var tmr;
  q.addEventListener("input", function () {
    clearTimeout(tmr);
    tmr = setTimeout(function () { state.q = q.value; state.page = 1; render(); }, 60);
  });
  q.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { q.value = ""; state.q = ""; state.page = 1; render(); }
    if (e.key === "Enter") {
      var first = out.querySelector("a.rrow");
      if (first) window.location.href = first.getAttribute("href");
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== q &&
        !/^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || "")) {
      e.preventDefault(); q.focus(); q.select();
    }
  });

  Array.prototype.forEach.call(document.querySelectorAll(".fchip"), function (b) {
    b.addEventListener("click", function () {
      var f = b.dataset.f, v = b.dataset.v;
      state[f] = (state[f] === v) ? "" : v;
      Array.prototype.forEach.call(
        document.querySelectorAll('.fchip[data-f="' + f + '"]'), function (o) {
          o.classList.toggle("on", (o.dataset.v || "") === (state[f] || ""));
        });
      state.page = 1; render();
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll(".sortbtn"), function (b) {
    b.addEventListener("click", function () {
      state.sort = b.dataset.s; state.page = 1;
      Array.prototype.forEach.call(document.querySelectorAll(".sortbtn"), function (o) {
        o.classList.toggle("on", o === b);
      });
      render();
    });
  });

  moreBtn.addEventListener("click", function () { state.page++; render(); });

  render();
})();

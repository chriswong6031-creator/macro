/* Divergence Radar panel (display-only) — federal contract spend vs price.
 *
 * Renders basketdata/radar.json (engine/radar.py): a "spotlight" of the off-diagonal
 * cases where federal contract obligations DISAGREE with the theme's 60-day relative
 * strength, plus a compact table of every covered theme. The radar stays SILENT on the
 * diagonal (spend and price agree -> no edge), so a quiet read is a feature, not a gap.
 * Self-contained + bilingual; hides itself when the JSON is absent.
 *
 *   renderDivergenceRadar({ base:'basketdata/', mount:'#divergence-radar' })
 */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function bi(en, zh) {
    var z = (zh == null || zh === "") ? en : zh;
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(z) + "</span>";
  }
  function fetchJSON(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }
  function usd(x) {
    if (x == null) return "—";
    var v = Math.abs(x);
    if (v >= 1e9) return "$" + (x / 1e9).toFixed(1) + "B";
    if (v >= 1e6) return "$" + Math.round(x / 1e6) + "M";
    return "$" + Math.round(x / 1e3) + "K";
  }
  function relpct(x) { return x == null ? "—" : (x > 0 ? "+" : "") + (x * 100).toFixed(0) + "%"; }

  var STATE = {
    POSITIVE_DIVERGENCE: { cls: "dr-pos", en: "Money ahead of price", zh: "资金领先价格", ico: "🟢" },
    NEGATIVE_DIVERGENCE: { cls: "dr-neg", en: "Price ahead of fundamentals", zh: "价格领先基本面", ico: "🟠" },
    CONFIRMED_UP: { cls: "dr-cup", en: "Confirmed up · priced", zh: "同步上行 · 已反映", ico: "✓" },
    CONFIRMED_DOWN: { cls: "dr-cdn", en: "Confirmed weak · priced", zh: "同步走弱 · 已反映", ico: "✓" },
    QUIET: { cls: "dr-quiet", en: "Quiet", zh: "平静", ico: "·" }
  };
  function st(s) { return STATE[s] || STATE.QUIET; }

  function spotlightCard(f) {
    var s = st(f.state), o = f.observable || {}, c = f.consensus || {};
    var cov = (o.covered || []).slice(0, 8).join(", ") + ((o.covered || []).length > 8 ? "…" : "");
    return '<div class="dr-card ' + s.cls + '">' +
      '<div class="dr-card-h"><span class="dr-badge ' + s.cls + '">' + s.ico + " " + bi(s.en, s.zh) + "</span>" +
      '<b class="dr-theme">' + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</b></div>" +
      '<div class="dr-note">' + bi(f.note, f.note_zh) + "</div>" +
      '<div class="dr-chips">' +
        '<span class="dr-chip">' + bi("fed spend", "联邦支出") + " <b>" + (o.accel == null ? "—" : o.accel.toFixed(2) + "×") + "</b> " +
          bi("YoY", "同比") + "</span>" +
        '<span class="dr-chip">' + bi("vs $ yr-ago", "对比去年") + " <b>" + usd(o.recent_3m_usd) + "</b> / " + usd(o.base_3m_usd) + "</span>" +
        '<span class="dr-chip">' + bi("price 60d", "价格60日") + " <b>" + relpct(c.rel_60d) + "</b></span>" +
        '<span class="dr-cov">' + esc(cov) + "</span>" +
      "</div></div>";
  }

  function tableRow(f) {
    var s = st(f.state), o = f.observable || {}, c = f.consensus || {};
    return "<tr>" +
      "<td>" + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</td>" +
      '<td class="dr-num"><b>' + (o.accel == null ? "—" : o.accel.toFixed(2) + "×") + "</b> <span class=\"dr-mut\">" + usd(o.recent_3m_usd) + "</span></td>" +
      '<td class="dr-num" style="color:' + (c.rel_60d > 0 ? "var(--up)" : c.rel_60d < 0 ? "var(--down)" : "var(--muted)") + '">' + relpct(c.rel_60d) + "</td>" +
      '<td><span class="dr-badge ' + s.cls + '">' + bi(s.en, s.zh) + "</span></td>" +
      "</tr>";
  }

  window.renderDivergenceRadar = function (opts) {
    opts = opts || {};
    var base = opts.base || "basketdata/";
    var mount = document.querySelector(opts.mount || "#divergence-radar");
    if (!mount) return;
    fetchJSON(base + "radar.json").then(function (d) {
      if (!d || !d.flags || !d.flags.length) { mount.style.display = "none"; return; }
      var cov = d.coverage || {};
      var divs = d.flags.filter(function (f) { return f.state.indexOf("DIVERGENCE") >= 0; });

      var spotlight;
      if (divs.length) {
        spotlight = '<div class="dr-spot">' + divs.map(spotlightCard).join("") + "</div>";
      } else {
        spotlight = '<div class="dr-calm">' + bi(
          "No active divergences — federal spend and price agree across the " + (cov.themes_covered || 0) + " covered themes. " +
            "The radar stays silent when there's no edge to read.",
          "暂无背离 —— 在 " + (cov.themes_covered || 0) + " 个覆盖主题中，联邦支出与价格一致。无可读边际时雷达保持沉默。") + "</div>";
      }

      var caveat = (d.caveats || []).length
        ? '<p class="dr-cav">' + bi(d.caveats[0], (d.caveats_zh || [])[0]) + "</p>" : "";

      mount.style.display = "";
      mount.innerHTML =
        '<h2 style="margin:0 0 2px"><span class="idx">★</span>🛰️ ' +
          bi("Divergence Radar", "背离雷达") +
          '<span class="sect-tag">' + bi("federal money vs price · variant edge", "联邦资金 vs 价格 · 变量边际") + "</span></h2>" +
        '<p class="sub">' + bi(
          "Where the government is actually spending vs what price already implies. Money rising while price lags = a long-lead watch; money cooling while price leads = narrative on fumes. Display-only context, not a trade trigger.",
          "政府实际支出 vs 价格已隐含的预期。资金上升而价格滞后＝前瞻观察；资金降温而价格领先＝叙事透支。仅供参考，非交易触发。") + "</p>" +
        spotlight +
        '<div class="dr-tblwrap"><table class="dr-tbl"><thead><tr>' +
          "<th>" + bi("Theme", "主题") + "</th>" +
          "<th>" + bi("Fed spend (YoY)", "联邦支出(同比)") + "</th>" +
          "<th>" + bi("Price 60d", "价格60日") + "</th>" +
          "<th>" + bi("Read", "解读") + "</th>" +
        "</tr></thead><tbody>" + d.flags.map(tableRow).join("") + "</tbody></table></div>" +
        caveat;
    });
  };
})();

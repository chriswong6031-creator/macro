/* Divergence Radar panel — federal activity vs price.
 *
 * Three public entry points:
 *   renderDivergenceRadar(opts)  compact shared panel (baskets.html + any embed)
 *   renderRadarFull(opts)        full page (radar.html)
 *   renderRadarLifecycle(opts)   legacy no-op guard (old rendered pages)
 *   renderTickerRadar(opts)      legacy no-op guard (old rendered pages)
 *
 * ALL new CSS injected via <style id="rp-styles"> using rp- prefix.
 * Zero dependence on old dr-* / rl-* page-inline styles.
 * Bilingual: bi(en,zh) dual-span pattern everywhere; NO translated title= attrs.
 */
(function () {
  "use strict";

  // ── Helpers ────────────────────────────────────────────────────────────────
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
    return fetch(url, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }
  function usd(x) {
    if (x == null) return "—";
    var v = Math.abs(x);
    if (v >= 1e9) return "$" + (x / 1e9).toFixed(1) + "B";
    if (v >= 1e6) return "$" + Math.round(x / 1e6) + "M";
    return "$" + Math.round(x / 1e3) + "K";
  }
  function relpct(x) {
    return x == null ? "—" : (x > 0 ? "+" : "") + (x * 100).toFixed(0) + "%";
  }

  // ── State / lifecycle maps ─────────────────────────────────────────────────
  var STATE = {
    POSITIVE_DIVERGENCE: { en: "Pos Divergence", zh: "正背离", ico: "◎", col: "var(--up)", bgCls: "rp-badge-pos", cardCls: "rp-card-pos" },
    NEGATIVE_DIVERGENCE: { en: "Neg Divergence", zh: "负背离", ico: "◎", col: "var(--down)", bgCls: "rp-badge-neg", cardCls: "rp-card-neg" },
    CONFIRMED_UP:        { en: "Conf Up",         zh: "确认上行", ico: "✓", col: "var(--up)",   bgCls: "rp-badge-cup", cardCls: "rp-card-cdn" },
    CONFIRMED_DOWN:      { en: "Conf Down",        zh: "确认走弱", ico: "✓", col: "var(--muted)",bgCls: "rp-badge-cdn", cardCls: "rp-card-cdn" },
    QUIET:               { en: "Quiet",            zh: "平静",    ico: "·", col: "var(--line)", bgCls: "rp-badge-quiet", cardCls: "rp-card-quiet" }
  };
  function st(s) { return STATE[s] || STATE.QUIET; }

  var LIFE = {
    emerging:   { en: "Emerging",       zh: "新兴",     c: "var(--up)" },
    forming:    { en: "Forming",        zh: "形成中",   c: "var(--up)" },
    confirming: { en: "Confirming",     zh: "确认中",   c: "var(--link)" },
    mature:     { en: "Mature",         zh: "成熟",     c: "var(--muted)" },
    fading:     { en: "Fading",         zh: "退潮",     c: "var(--down)" },
    quiet:      { en: "Quiet",          zh: "平静",     c: "var(--muted)" }
  };

  var LANES = [
    { key: "emerging",   en: "Emerging",   zh: "新兴" },
    { key: "forming",    en: "Forming",    zh: "形成中" },
    { key: "confirming", en: "Confirming", zh: "确认中" },
    { key: "mature",     en: "Mature",     zh: "成熟" },
    { key: "fading",     en: "Fading",     zh: "退潮" },
    { key: "quiet",      en: "Quiet",      zh: "平静" }
  ];

  // ── CSS injection (id-guarded, rp- prefix, injected once) ─────────────────
  function injectStyles() {
    if (document.getElementById("rp-styles")) return;
    var el = document.createElement("style");
    el.id = "rp-styles";
    el.textContent = [
      /* bilingual */
      "html[data-lang=zh] .l-en{display:none}",
      "html[data-lang=en] .l-zh{display:none}",
      /* band / overview wrapper */
      ".rp-band{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin-bottom:8px}",
      /* triage strip */
      ".rp-triage{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;min-height:28px}",
      ".rp-triage-title{font-size:13px;font-weight:700;display:flex;align-items:center;gap:5px;flex-shrink:0}",
      ".rp-sep{color:var(--line);flex-shrink:0}",
      ".rp-chip{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;border:1px solid;white-space:nowrap}",
      ".rp-chip-neg{background:color-mix(in srgb,var(--down) 12%,transparent);color:var(--down);border-color:color-mix(in srgb,var(--down) 30%,transparent)}",
      ".rp-chip-cdn{background:color-mix(in srgb,var(--muted) 12%,transparent);color:var(--muted);border-color:color-mix(in srgb,var(--muted) 30%,transparent)}",
      ".rp-chip-quiet{background:color-mix(in srgb,var(--muted) 8%,transparent);color:var(--muted);border-color:color-mix(in srgb,var(--muted) 20%,transparent)}",
      ".rp-chip-pos{background:color-mix(in srgb,var(--up) 12%,transparent);color:var(--up);border-color:color-mix(in srgb,var(--up) 30%,transparent)}",
      ".rp-chip-regime{background:color-mix(in srgb,var(--link) 12%,transparent);color:var(--link);border-color:color-mix(in srgb,var(--link) 28%,transparent)}",
      ".rp-chip-acct{background:color-mix(in srgb,var(--muted) 8%,transparent);color:var(--muted);border-color:color-mix(in srgb,var(--muted) 20%,transparent);font-weight:400}",
      ".rp-asof{color:var(--muted);font-size:11px;margin-left:auto}",
      /* delta strip */
      ".rp-delta{display:flex;flex-wrap:wrap;gap:5px;align-items:center;padding:6px 0 2px;font-size:11px}",
      ".rp-delta-lbl{color:var(--warn);font-weight:600;font-size:11px;white-space:nowrap}",
      ".rp-delta-new{background:color-mix(in srgb,var(--down) 15%,transparent);color:var(--down);border:1px solid color-mix(in srgb,var(--down) 35%,transparent);padding:2px 7px;border-radius:10px;font-size:11px}",
      ".rp-delta-res{background:color-mix(in srgb,var(--up) 12%,transparent);color:var(--up);border:1px solid color-mix(in srgb,var(--up) 30%,transparent);padding:2px 7px;border-radius:10px;font-size:11px}",
      ".rp-delta-flip{background:color-mix(in srgb,var(--warn) 12%,transparent);color:var(--warn);border:1px solid color-mix(in srgb,var(--warn) 30%,transparent);padding:2px 7px;border-radius:10px;font-size:11px}",
      /* scatter */
      ".rp-scatter-wrap{margin-top:8px;border-top:1px solid var(--line);padding-top:8px}",
      ".rp-scatter-lbl{font-size:10px;color:var(--muted);margin-bottom:4px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px}",
      ".rp-scatter-legend{display:flex;gap:10px}",
      ".rp-scatter-canvas{width:100%;height:80px}",
      /* lifecycle */
      ".rp-lifecycle{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin-bottom:8px}",
      ".rp-lifecycle-h{font-size:11px;font-weight:600;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em}",
      ".rp-pipe{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px}",
      ".rp-lane{flex:1;min-width:100px;border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:var(--panel2)}",
      ".rp-lane.rp-lane-empty-lane{opacity:.6}",
      ".rp-lane-h{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px;display:flex;align-items:center;justify-content:space-between}",
      ".rp-lane-cnt{color:var(--muted);font-weight:400}",
      ".rp-lchip{font-size:11px;padding:3px 6px;border-left:2px solid;border-radius:0 4px 4px 0;background:color-mix(in srgb,var(--panel) 60%,transparent);margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
      ".rp-lmore{font-size:10px;color:var(--link);cursor:pointer;padding:2px 6px;opacity:.8;border:none;background:none}",
      ".rp-lane-mt{color:var(--muted);font-size:11px;opacity:.5;padding:2px 0}",
      /* spotlight section */
      ".rp-spotlight{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin-bottom:8px}",
      ".rp-spot-h{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}",
      ".rp-spot-title{font-size:13px;font-weight:700}",
      ".rp-spot-cnt{font-size:11px;color:var(--muted)}",
      ".rp-spot-ctrl{margin-left:auto}",
      ".rp-spot-btn{font-size:11px;color:var(--link);background:none;border:none;cursor:pointer;padding:2px 6px}",
      ".rp-calm{font-size:12.5px;color:var(--muted);background:var(--panel2);border:1px dashed var(--line);border-radius:9px;padding:10px 12px;margin:6px 0}",
      /* cards grid */
      ".rp-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px;margin-bottom:8px}",
      ".rp-card{border:1px solid var(--line);border-radius:7px;padding:10px 12px;background:var(--panel2);border-top-width:2px}",
      ".rp-card-neg{border-top-color:var(--down)}",
      ".rp-card-pos{border-top-color:var(--up)}",
      ".rp-card-cdn{border-top-color:var(--muted)}",
      ".rp-card-quiet{border-top-color:var(--line)}",
      ".rp-card-hdr{display:flex;align-items:center;gap:6px;margin-bottom:6px;flex-wrap:wrap}",
      ".rp-badge{display:inline-flex;align-items:center;gap:3px;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;border:1px solid;white-space:nowrap}",
      ".rp-badge-neg{color:var(--down);background:color-mix(in srgb,var(--down) 12%,transparent);border-color:color-mix(in srgb,var(--down) 30%,transparent)}",
      ".rp-badge-pos{color:var(--up);background:color-mix(in srgb,var(--up) 12%,transparent);border-color:color-mix(in srgb,var(--up) 30%,transparent)}",
      ".rp-badge-cdn{color:var(--muted);background:color-mix(in srgb,var(--muted) 10%,transparent);border-color:color-mix(in srgb,var(--muted) 25%,transparent)}",
      ".rp-badge-cup{color:var(--up);background:color-mix(in srgb,var(--up) 8%,transparent);border-color:color-mix(in srgb,var(--up) 20%,transparent)}",
      ".rp-badge-quiet{color:var(--muted);background:transparent;border-color:var(--line)}",
      ".rp-card-name{font-weight:700;font-size:13px}",
      ".rp-edge-badge{margin-left:auto;font-weight:700;font-size:11px;padding:1px 7px;border-radius:7px}",
      ".rp-card-note{font-size:12px;color:var(--muted);margin-bottom:6px;line-height:1.4}",
      ".rp-srcs{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:5px}",
      ".rp-src-chip{font-size:10px;padding:1px 6px;border-radius:4px;border:1px solid;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}",
      ".rp-metrics{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:5px}",
      ".rp-metric{font-size:11px;color:var(--muted);padding:1px 6px;background:color-mix(in srgb,var(--muted) 8%,transparent);border-radius:4px;border:1px solid var(--line)}",
      ".rp-metric b{color:var(--text)}",
      ".rp-conf-row{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:5px}",
      ".rp-conf-chip{font-size:10px;padding:1px 5px;border-radius:4px;border:1px solid var(--line);color:var(--muted)}",
      ".rp-tickers{font-size:10px;color:var(--muted);font-family:ui-monospace,Menlo,monospace;line-height:1.6;margin-top:3px}",
      /* state strip dots */
      ".rp-strip{margin-top:5px;display:flex;gap:2px;align-items:center}",
      ".rp-strip-lbl{font-size:9px;color:var(--muted);margin-right:2px}",
      ".rp-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;opacity:.85}",
      /* news toggle */
      ".rp-news-btn{font-size:11px;color:var(--link);cursor:pointer;margin-top:5px;border:none;background:none;padding:0;display:inline-flex;align-items:center;gap:3px}",
      ".rp-news-body{display:none;margin-top:6px;border-top:1px solid var(--line);padding-top:6px}",
      ".rp-news-body.rp-open{display:block}",
      ".rp-hl{font-size:11px;margin-bottom:4px;line-height:1.4}",
      ".rp-hl-src{color:var(--muted);font-size:10px}",
      /* compact rows */
      ".rp-compact-h{font-size:11px;color:var(--muted);font-weight:600;margin:10px 0 4px;text-transform:uppercase;letter-spacing:.05em}",
      ".rp-compact-row{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:5px;cursor:pointer;border:1px solid transparent;font-size:12px}",
      ".rp-compact-row:hover{background:var(--panel2);border-color:var(--line)}",
      ".rp-compact-name{font-weight:600;min-width:120px;flex-shrink:0}",
      ".rp-compact-state{flex-shrink:0}",
      ".rp-compact-edge{font-weight:700;font-size:11px;font-family:ui-monospace,Menlo,monospace;flex-shrink:0;min-width:36px;text-align:right}",
      ".rp-compact-div{font-size:11px;font-family:ui-monospace,Menlo,monospace;color:var(--muted);flex-shrink:0;min-width:38px}",
      ".rp-compact-days{font-size:10px;color:var(--muted);flex-shrink:0;min-width:32px}",
      ".rp-compact-strip{display:flex;gap:2px;align-items:center;margin-left:auto;flex-shrink:0}",
      ".rp-compact-expand{display:none;background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:8px 10px;margin:0 8px 4px;font-size:12px}",
      ".rp-compact-expand.rp-open{display:block}",
      ".rp-show-ctrl{font-size:11px;color:var(--link);cursor:pointer;padding:4px 8px;margin-top:4px;display:inline-block;border:none;background:none}",
      /* tabs */
      ".rp-tabs-wrap{background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-bottom:8px}",
      ".rp-tabs-nav{display:flex;border-bottom:1px solid var(--line);background:var(--panel2);overflow-x:auto}",
      ".rp-tab-btn{padding:8px 14px;font-size:12px;font-weight:600;cursor:pointer;border:none;background:none;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;flex-shrink:0}",
      ".rp-tab-btn:hover{color:var(--text)}",
      ".rp-tab-btn.rp-active{color:var(--text);border-bottom-color:var(--link)}",
      ".rp-tab-body{display:none;padding:12px 14px}",
      ".rp-tab-body.rp-active{display:block}",
      /* all-themes table */
      ".rp-theme-ctrl{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:10px}",
      ".rp-fchip{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--muted)}",
      ".rp-fchip.rp-active{background:var(--panel2);color:var(--text);border-color:var(--muted)}",
      ".rp-tbl{width:100%;border-collapse:collapse;font-size:12px}",
      ".rp-tbl th{text-align:left;padding:5px 8px;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}",
      ".rp-tbl th:hover{color:var(--text)}",
      ".rp-tbl th .rp-sico{font-size:9px;margin-left:3px;opacity:.5}",
      ".rp-tbl th.rp-sorted .rp-sico{opacity:1}",
      ".rp-tbl td{padding:5px 8px;border-bottom:1px solid color-mix(in srgb,var(--line) 50%,transparent)}",
      ".rp-tbl tr:hover td{background:color-mix(in srgb,var(--panel2) 50%,transparent)}",
      ".rp-num{font-family:ui-monospace,Menlo,monospace;font-size:11.5px}",
      ".rp-strip-cell{display:flex;gap:2px;align-items:center}",
      ".rp-life-tag{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}",
      ".rp-quiet-tog{font-size:11px;color:var(--link);cursor:pointer;padding:2px 6px;border:none;background:none}",
      /* per-name tab */
      ".rp-name-ctrl{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}",
      ".rp-name-search{padding:4px 10px;border-radius:5px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font-size:12px;font-family:inherit;outline:none;width:180px}",
      ".rp-name-search:focus{border-color:var(--link)}",
      ".rp-name-sel{padding:4px 8px;border-radius:5px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font-size:12px;font-family:inherit;outline:none;cursor:pointer}",
      ".rp-name-row{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:5px;cursor:pointer;border:1px solid transparent;font-size:12px}",
      ".rp-name-row:hover{background:var(--panel2);border-color:var(--line)}",
      ".rp-name-ticker{font-family:ui-monospace,Menlo,monospace;font-weight:700;min-width:52px;flex-shrink:0}",
      ".rp-name-basket{font-size:10px;color:var(--muted);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".rp-name-edge{font-weight:700;font-size:11px;font-family:ui-monospace,Menlo,monospace;min-width:36px;text-align:right;flex-shrink:0}",
      ".rp-name-rs{font-size:11px;font-family:ui-monospace,Menlo,monospace;min-width:52px;text-align:right;flex-shrink:0}",
      ".rp-name-expand{display:none;background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:8px 10px;margin:0 8px 4px;font-size:12px}",
      ".rp-name-expand.rp-open{display:block}",
      ".rp-show-more{display:block;width:100%;text-align:center;padding:8px;font-size:12px;color:var(--link);cursor:pointer;border:1px solid var(--line);border-radius:5px;background:none;margin-top:8px}",
      /* accountability */
      ".rp-acct-note{font-size:11px;color:var(--muted);line-height:1.5;padding:8px;background:color-mix(in srgb,var(--warn) 8%,transparent);border:1px solid color-mix(in srgb,var(--warn) 25%,transparent);border-radius:5px;margin-bottom:8px}",
      ".rp-acct-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin-bottom:10px}",
      ".rp-acct-stat{background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:8px 10px}",
      ".rp-acct-val{font-size:18px;font-weight:700;font-family:ui-monospace,Menlo,monospace;color:var(--muted)}",
      ".rp-acct-lbl{font-size:10px;color:var(--muted);margin-top:1px;text-transform:uppercase;letter-spacing:.05em}",
      ".rp-horizon-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}",
      ".rp-horizon{background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:6px 10px;font-size:11px}",
      ".rp-horizon-h{font-weight:600;margin-bottom:2px;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}",
      /* narrative brain */
      ".rp-brain{margin-top:10px;padding:8px 10px;border:1px solid var(--line);border-radius:5px;background:color-mix(in srgb,var(--muted) 6%,transparent);font-size:11px;color:var(--muted)}",
      ".rp-brain-h{font-size:12px;font-weight:700;margin-bottom:6px;color:var(--text)}",
      ".rp-brain-degraded{display:flex;align-items:center;gap:6px}",
      ".rp-brain-rot{font-size:12px;color:var(--text);background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:7px 10px;margin-bottom:8px}",
      ".rp-brain-row{padding:5px 0;border-bottom:1px solid var(--line)}",
      ".rp-brain-badge{font-size:10px;font-weight:700;padding:1px 7px;border-radius:999px;border:1px solid var(--muted);margin-right:6px}",
      ".rp-brain-theme{font-size:12.5px;margin-right:6px}",
      ".rp-brain-why{font-size:11.5px;color:var(--text);line-height:1.5;margin-top:2px}",
      ".rp-cav{font-size:10.5px;color:var(--muted);margin:6px 0 0;line-height:1.45}",
      ".rp-mut{color:var(--muted)}",
      /* caveat */
      ".rp-cav-block{font-size:10.5px;color:var(--muted);margin-top:8px;line-height:1.45}",
      /* mobile */
      "@media(max-width:600px){",
      ".rp-cards{grid-template-columns:1fr}",
      ".rp-compact-name{min-width:90px}",
      ".rp-compact-days{display:none}",
      ".rp-compact-strip{display:none}",
      ".rp-compact-row{flex-wrap:wrap}",
      ".rp-tab-btn{padding:7px 10px;font-size:11px}",
      ".rp-name-search,.rp-name-sel{width:100%}",
      ".rp-tbl{font-size:11px}",
      ".rp-asof{display:none}",
      ".rp-triage{gap:5px}",
      "}",
      "@media(max-width:400px){",
      ".rp-compact-div{display:none}",
      ".rp-lane{min-width:80px}",
      "}"
    ].join("");
    (document.head || document.documentElement).appendChild(el);
  }

  // ── Edge color ─────────────────────────────────────────────────────────────
  function edgeColor(e) {
    return e >= 70 ? "var(--up)" : e >= 45 ? "var(--warn)" : "var(--muted)";
  }
  function edgeBadge(f) {
    if (f.edge_score == null) return "";
    var e = f.edge_score, col = edgeColor(e);
    return '<span class="rp-edge-badge" style="background:color-mix(in srgb,' + col + ' 15%,transparent);color:' + col + '">edge ' + e + "</span>";
  }

  // ── State strip dots ───────────────────────────────────────────────────────
  function dotColor(s) {
    return s === "NEGATIVE_DIVERGENCE" ? "var(--down)"
      : s === "POSITIVE_DIVERGENCE" ? "var(--up)"
      : s === "CONFIRMED_DOWN" ? "#5d6b7e"
      : s === "CONFIRMED_UP" ? "#3d7a5d"
      : "var(--line)";
  }
  function stripDots(strip) {
    if (!strip || !strip.length) return "";
    return strip.slice(-14).map(function (item) {
      var col = dotColor(item.s);
      return '<span class="rp-dot" style="background:' + col + '" title="' + esc(item.d) + " " + esc(item.s) + '"></span>';
    }).join("");
  }

  // ── Merge enrichment into base flags ──────────────────────────────────────
  function mergeEnrichment(flags, enriched, newsMap) {
    var eidx = {};
    ((enriched || {}).flags || []).forEach(function (ef) {
      if (ef.basket) eidx[ef.basket] = ef;
    });
    var baskets = (newsMap || {}).baskets || {};
    flags.forEach(function (f) {
      var ef = eidx[f.basket] || {};
      ["edge_score", "confirm", "regime", "decay", "drivers", "prev_state", "state_strip"].forEach(function (k) {
        if (ef[k] != null) f[k] = ef[k];
      });
      f._headlines = (baskets[f.basket] || {}).headlines || [];
    });
  }

  // ── Render triage strip HTML ───────────────────────────────────────────────
  function triageHTML(radar, enriched) {
    var cov = radar.coverage || {};
    var regime = (enriched || {}).regime || {};
    var ic = null; // filled by accountability data if present
    var states = { NEGATIVE_DIVERGENCE: 0, POSITIVE_DIVERGENCE: 0, CONFIRMED_DOWN: 0, CONFIRMED_UP: 0, QUIET: 0 };
    (radar.flags || []).forEach(function (f) { if (states[f.state] != null) states[f.state]++; });

    var h = '<div class="rp-triage">';
    h += '<div class="rp-triage-title"><span>🛰️</span>' + bi("Divergence Radar", "背离雷达") + "</div>";
    h += '<span class="rp-sep">·</span>';

    if (regime.quad_name) {
      h += '<span class="rp-chip rp-chip-regime">' + esc(regime.quad_name) + " ×" + (regime.mult || 1).toFixed(3) + "</span>";
    }

    if (states.NEGATIVE_DIVERGENCE > 0) {
      h += '<span class="rp-chip rp-chip-neg">◎ ' + states.NEGATIVE_DIVERGENCE + " " + bi("neg div", "负背离") + "</span>";
    }
    if (states.POSITIVE_DIVERGENCE > 0) {
      h += '<span class="rp-chip rp-chip-pos">◎ ' + states.POSITIVE_DIVERGENCE + " " + bi("pos div", "正背离") + "</span>";
    }
    if (states.CONFIRMED_DOWN > 0 || states.CONFIRMED_UP > 0) {
      var n = states.CONFIRMED_DOWN + states.CONFIRMED_UP;
      h += '<span class="rp-chip rp-chip-cdn">✓ ' + n + " " + bi("confirmed", "已确认") + "</span>";
    }
    h += '<span class="rp-chip rp-chip-quiet">· ' + states.QUIET + " " + bi("quiet", "平静") + "</span>";

    if (cov.themes_covered) {
      h += '<span class="rp-chip rp-chip-quiet">' + cov.themes_covered + " " + bi("themes", "主题");
      if (cov.members_with_data) h += " · " + cov.members_with_data + " " + bi("members", "成员");
      h += "</span>";
    }

    h += '<span class="rp-chip rp-chip-acct">' + bi("grading: 0 matured · accruing", "评级中: 0成熟 · 累积中") + "</span>";

    if (radar.as_of) {
      h += '<span class="rp-asof">' + esc(radar.as_of) + (radar.lag_months ? " · lag " + radar.lag_months + "mo" : "") + "</span>";
    }

    h += "</div>";
    return h;
  }

  // ── Render delta strip HTML ────────────────────────────────────────────────
  function deltaHTML(changes) {
    if (!changes) return "";
    var nd = changes.new_divergences || [];
    var res = changes.resolved || [];
    var fl = changes.flips || [];
    if (!nd.length && !res.length && !fl.length) return "";

    var h = '<div class="rp-delta">';
    h += '<span class="rp-delta-lbl">' + bi("Δ TODAY", "今日变化") + "</span>";
    nd.forEach(function (f) {
      h += '<span class="rp-delta-new">+ ' + bi(f.name, f.name_zh) + " " + bi("new", "新") + "</span>";
    });
    res.forEach(function (f) {
      h += '<span class="rp-delta-res">✓ ' + bi(f.name, f.name_zh) + " " + bi("resolved", "已消除") + "</span>";
    });
    fl.forEach(function (f) {
      h += '<span class="rp-delta-flip">⇄ ' + bi(f.name, f.name_zh) + "</span>";
    });
    h += "</div>";
    return h;
  }

  // ── Scatter canvas (radar.html full mode only) ─────────────────────────────
  function drawScatter(canvas, flags) {
    if (!canvas) return;
    var W = canvas.clientWidth || canvas.offsetWidth || 800;
    var H = 80;
    var dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.height = H + "px";
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    var xMin = -0.35, xMax = 0.82;
    function toX(v) { return 14 + ((v - xMin) / (xMax - xMin)) * (W - 28); }

    // zero line
    var cx = toX(0);
    ctx.fillStyle = "rgba(128,128,128,0.05)";
    ctx.fillRect(toX(-0.35), 0, cx - toX(-0.35), H - 14);
    ctx.strokeStyle = "rgba(128,128,128,0.2)";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(cx, 4); ctx.lineTo(cx, H - 16); ctx.stroke();
    ctx.setLineDash([]);

    // x-axis ticks
    ctx.fillStyle = "rgba(139,147,161,0.55)";
    ctx.font = "9px system-ui,sans-serif";
    ctx.textAlign = "center";
    [-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7].forEach(function (v) {
      var x = toX(v);
      ctx.fillText((v > 0 ? "+" : "") + (v * 100).toFixed(0) + "%", x, H - 2);
      ctx.fillStyle = "rgba(128,128,128,0.08)";
      ctx.fillRect(x, 0, 1, H - 14);
      ctx.fillStyle = "rgba(139,147,161,0.55)";
    });

    // groups by state
    var groups = { NEGATIVE_DIVERGENCE: [], POSITIVE_DIVERGENCE: [], CONFIRMED_DOWN: [], CONFIRMED_UP: [], QUIET: [] };
    flags.forEach(function (f) {
      var k = groups[f.state] ? f.state : "QUIET";
      groups[k].push(f);
    });

    // swim lane Y positions
    var yBands = { QUIET: 50, CONFIRMED_DOWN: 38, CONFIRMED_UP: 26, NEGATIVE_DIVERGENCE: 18, POSITIVE_DIVERGENCE: 10 };

    function drawGroup(grp, fillColor, strokeColor, yBase) {
      grp.sort(function (a, b) {
        var ar = (a.consensus && a.consensus.rel_60d) || 0;
        var br = (b.consensus && b.consensus.rel_60d) || 0;
        return ar - br;
      });
      grp.forEach(function (f, i) {
        var rel = (f.consensus && f.consensus.rel_60d != null) ? f.consensus.rel_60d : 0;
        var x = toX(rel);
        var edge = f.edge_score || 0;
        var r = Math.max(3.5, 3 + edge / 28);
        var yOff = (i % 5 - 2) * 3.5;
        ctx.beginPath();
        ctx.arc(x, yBase + yOff, r, 0, Math.PI * 2);
        ctx.fillStyle = fillColor;
        ctx.fill();
        if (strokeColor) { ctx.strokeStyle = strokeColor; ctx.lineWidth = 0.8; ctx.stroke(); }
      });
    }

    drawGroup(groups.QUIET, "rgba(60,70,90,0.5)", null, yBands.QUIET);
    drawGroup(groups.CONFIRMED_DOWN, "rgba(100,110,130,0.7)", "rgba(139,147,161,0.35)", yBands.CONFIRMED_DOWN);
    drawGroup(groups.CONFIRMED_UP, "rgba(50,130,90,0.6)", null, yBands.CONFIRMED_UP);
    drawGroup(groups.NEGATIVE_DIVERGENCE, "rgba(224,100,100,0.85)", "rgba(255,120,120,0.4)", yBands.NEGATIVE_DIVERGENCE);
    drawGroup(groups.POSITIVE_DIVERGENCE, "rgba(69,184,115,0.85)", "rgba(100,220,140,0.4)", yBands.POSITIVE_DIVERGENCE);

    // label top-4 neg/pos divergences by edge
    var topNeg = groups.NEGATIVE_DIVERGENCE.slice()
      .sort(function (a, b) { return (b.edge_score || 0) - (a.edge_score || 0); }).slice(0, 4);
    var topPos = groups.POSITIVE_DIVERGENCE.slice()
      .sort(function (a, b) { return (b.edge_score || 0) - (a.edge_score || 0); }).slice(0, 2);

    ctx.font = "bold 8.5px system-ui,sans-serif";
    ctx.textAlign = "center";
    topNeg.concat(topPos).forEach(function (f) {
      var rel = (f.consensus && f.consensus.rel_60d != null) ? f.consensus.rel_60d : 0;
      var x = toX(rel);
      var parts = (f.name || "").split(" ");
      var label = parts.length > 2 ? parts[0] + "-" + parts[parts.length - 1].slice(0, 4) : parts[0];
      ctx.fillStyle = f.state === "NEGATIVE_DIVERGENCE" ? "rgba(255,150,150,0.95)" : "rgba(130,220,160,0.95)";
      ctx.fillText(label, x, 8);
    });

    // lane labels
    ctx.font = "7.5px system-ui,sans-serif";
    ctx.textAlign = "left";
    ctx.fillStyle = "rgba(224,100,100,0.55)"; ctx.fillText("NEG", 2, yBands.NEGATIVE_DIVERGENCE + 3);
    ctx.fillStyle = "rgba(139,147,161,0.45)"; ctx.fillText("CDN", 2, yBands.CONFIRMED_DOWN + 3);
    ctx.fillStyle = "rgba(90,100,120,0.35)";  ctx.fillText("QT",  2, yBands.QUIET + 3);
  }

  // ── Lifecycle pipeline HTML ────────────────────────────────────────────────
  function lifecycleHTML(flags) {
    var h = '<div class="rp-pipe">';
    h += LANES.map(function (L, li) {
      var chips = flags.filter(function (f) { return f.lifecycle === L.key; });
      var linfo = LIFE[L.key] || LIFE.quiet;
      var isEmpty = !chips.length;
      var lh = '<div class="rp-lane' + (isEmpty ? " rp-lane-empty-lane" : "") + '" id="rp-lane-' + li + '">';
      lh += '<div class="rp-lane-h" style="color:' + linfo.c + '">' + bi(L.en, L.zh) + '<span class="rp-lane-cnt">' + chips.length + "</span></div>";
      if (!chips.length) {
        lh += '<div class="rp-lane-mt">—</div>';
      } else {
        var cap = 3;
        chips.slice(0, cap).forEach(function (f) {
          var s = st(f.state);
          lh += '<div class="rp-lchip" style="border-left-color:' + linfo.c + '" title="' + esc(f.name) + '">' + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</div>";
        });
        if (chips.length > cap) {
          var extra = chips.length - cap;
          lh += '<div id="rp-lane-ex-' + li + '" style="display:none">';
          chips.slice(cap).forEach(function (f) {
            lh += '<div class="rp-lchip" style="border-left-color:' + linfo.c + '">' + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</div>";
          });
          lh += "</div>";
          lh += '<button class="rp-lmore" onclick="(function(btn){var ex=document.getElementById(\'rp-lane-ex-' + li + '\');var open=ex.style.display!==\'none\';ex.style.display=open?\'none\':\'block\';btn.innerHTML=open?\'+' + extra + ' <span class=l-en>more</span><span class=l-zh>更多</span>\':"<span class=l-en>collapse</span><span class=l-zh>收起</span>"})(this)">+' + extra + " " + bi("more", "更多") + "</button>";
        }
      }
      lh += "</div>";
      return lh;
    }).join("");
    h += "</div>";
    return h;
  }

  // ── Source chips ──────────────────────────────────────────────────────────
  function srcChipsHTML(o) {
    var ss = (o || {}).sources || [];
    if (!ss.length) return "";
    var chips = ss.map(function (s) {
      var z = s.z == null ? 0 : s.z;
      var col = z > 0.2 ? "var(--up)" : z < -0.2 ? "var(--down)" : "var(--muted)";
      return '<span class="rp-src-chip" style="color:' + col + ';border-color:' + col + '">' +
        bi(s.label_en || s.name, s.label_zh || s.name) + " <b>" + (z > 0 ? "+" : "") + z.toFixed(1) + "</b></span>";
    });
    return '<div class="rp-srcs">' + chips.join("") + "</div>";
  }

  // ── Confirm chips ─────────────────────────────────────────────────────────
  function confirmChipsHTML(f) {
    var cf = f.confirm;
    if (!cf) return "";
    var legs = [];
    function leg(name, lg) {
      if (!lg || !lg.present) return;
      var d = lg.lean > 0 ? "▲" : lg.lean < 0 ? "▼" : "·";
      var col = lg.lean > 0 ? "var(--up)" : lg.lean < 0 ? "var(--down)" : "var(--muted)";
      legs.push('<span class="rp-conf-chip" style="color:' + col + ';border-color:' + col + '">' + name + " " + d + "</span>");
    }
    leg(bi("smart$", "聪明钱"), cf.alt);
    leg("ETF", cf.flows);
    leg(bi("options", "期权"), cf.options);
    if (cf.crowd && cf.crowd.penalty > 0) legs.push('<span class="rp-conf-chip" style="color:var(--warn)">' + bi("crowd", "拥挤") + " −" + cf.crowd.penalty + "</span>");
    if (f.regime && f.regime.mult != null) legs.push('<span class="rp-conf-chip rp-mut">' + bi("regime", "周期") + " ×" + f.regime.mult + "</span>");
    if (f.decay && f.decay.days_in_state > 1) legs.push('<span class="rp-conf-chip rp-mut">' + f.decay.days_in_state + bi("d", "天") + "</span>");
    return legs.length ? '<div class="rp-conf-row">' + legs.join("") + "</div>" : "";
  }

  // ── Full spotlight card ────────────────────────────────────────────────────
  function fullCard(f, i) {
    var s = st(f.state);
    var o = f.observable || {};
    var c = f.consensus || {};
    var edge = f.edge_score;
    var ecol = edgeColor(edge || 0);
    var tickers = (o.covered || []).slice(0, 8).join(" · ") + ((o.covered || []).length > 8 ? "…" : "");

    var newsHtml = "";
    var hs = f._headlines || [];
    if (hs.length) {
      var newsId = "rp-news-" + i;
      newsHtml = '<button class="rp-news-btn" onclick="(function(btn){var el=document.getElementById(\'' + newsId + '\');el.classList.toggle(\'rp-open\');btn.textContent=el.classList.contains(\'rp-open\')?\'📰 ▲\':\'📰 ' + hs.length + ' ▼\'})(this)">📰 ' + hs.length + " ▼</button>" +
        '<div class="rp-news-body" id="' + newsId + '">';
      hs.slice(0, 4).forEach(function (h) {
        var sent = h.sentiment === "pos" ? " ▲" : h.sentiment === "neg" ? " ▼" : "";
        newsHtml += '<div class="rp-hl"><a href="' + esc(/^https?:\/\//i.test(h.url || "") ? h.url : "#") + '" target="_blank" rel="noopener noreferrer" style="color:var(--link);text-decoration:none">' + esc(h.title || "") + "</a> " +
          '<span class="rp-hl-src">· ' + esc(h.source || "") + sent + "</span></div>";
      });
      newsHtml += "</div>";
    }

    var strip = '<div class="rp-strip"><span class="rp-strip-lbl">14d</span>' + stripDots(f.state_strip) + "</div>";

    return '<div class="rp-card ' + s.cardCls + '">' +
      '<div class="rp-card-hdr">' +
      '<span class="rp-badge ' + s.bgCls + '">' + s.ico + " " + bi(s.en, s.zh) + "</span>" +
      '<span class="rp-card-name">' + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</span>" +
      edgeBadge(f) + "</div>" +
      '<div class="rp-card-note">' + bi(f.note || "", f.note_zh || f.note || "") + "</div>" +
      srcChipsHTML(o) +
      '<div class="rp-metrics">' +
      '<span class="rp-metric">' + bi("spend", "支出") + " <b>" + (o.accel == null ? "—" : o.accel.toFixed(2) + "×") + "</b> " + bi("YoY", "同比") + "</span>" +
      (o.recent_3m_usd != null ? '<span class="rp-metric">' + bi("vs yr-ago", "对比去年") + " <b>" + usd(o.recent_3m_usd) + "</b>/" + usd(o.base_3m_usd) + "</span>" : "") +
      '<span class="rp-metric">' + bi("price 60d", "价格60日") + " <b>" + relpct(c.rel_60d) + "</b></span>" +
      "</div>" +
      confirmChipsHTML(f) +
      '<div class="rp-tickers">' + esc(tickers) + "</div>" +
      strip + newsHtml + "</div>";
  }

  // ── Compact row ────────────────────────────────────────────────────────────
  function compactRow(f, i, prefix) {
    var s = st(f.state);
    var edge = f.edge_score;
    var ecol = edgeColor(edge || 0);
    var expandId = (prefix || "rp-cexp") + "-" + i;
    var div = f.divergence;
    var days = f.decay && f.decay.days_in_state;
    var o = f.observable || {};
    var c = f.consensus || {};
    var tickers = (o.covered || []).slice(0, 10).join(" · ");

    var expandContent = '<div class="rp-card-note">' + bi(f.note || "", f.note_zh || f.note || "") + "</div>" +
      srcChipsHTML(o) +
      '<div class="rp-metrics" style="margin-top:4px">' +
      '<span class="rp-metric">' + bi("spend", "支出") + " <b>" + (o.accel == null ? "—" : o.accel.toFixed(2) + "×") + "</b></span>" +
      '<span class="rp-metric">' + bi("price 60d", "价格60日") + " <b>" + relpct(c.rel_60d) + "</b></span>" +
      "</div>" +
      '<div class="rp-tickers">' + esc(tickers) + "</div>";

    return '<div class="rp-compact-row" onclick="(function(el){var ex=document.getElementById(\'' + expandId + '\');if(ex)ex.classList.toggle(\'rp-open\')})(this)">' +
      '<span class="rp-compact-name">' + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</span>" +
      '<span class="rp-compact-state"><span class="rp-badge ' + s.bgCls + '">' + s.ico + " " + bi(s.en, s.zh) + "</span></span>" +
      '<span class="rp-compact-edge" style="color:' + ecol + '">' + (edge != null ? edge : "—") + "</span>" +
      '<span class="rp-compact-div">' + (div != null ? (div > 0 ? "+" : "") + div.toFixed(1) : "—") + "</span>" +
      '<span class="rp-compact-days">' + (days != null ? days + "d" : "—") + "</span>" +
      '<span class="rp-compact-strip">' + stripDots(f.state_strip) + "</span>" +
      "</div>" +
      '<div class="rp-compact-expand" id="' + expandId + '">' + expandContent + "</div>";
  }

  // ── Brain HTML ─────────────────────────────────────────────────────────────
  function brainHTML(b, compact) {
    if (!b) return "";
    var hasBrain = b.assessments && b.assessments.length;
    if (b.degraded_reason || !hasBrain) {
      var reason = b.degraded_reason || "no_assessments";
      return '<div class="rp-brain rp-brain-degraded"><span>🧠</span><span><b>' + bi("Narrative Brain", "叙事大脑") + "</b>" +
        (compact ? "" : ' <span class="rp-mut">· ' + bi("deterministic only — AI read unavailable", "仅确定性——AI解读不可用") + " (" + esc(reason) + ")</span>") +
        (compact ? ' <span class="rp-mut">· ' + bi("AI read unavailable", "AI解读不可用") + " (" + esc(reason) + ")</span>" : "") +
        "</span></div>";
    }
    var NBV = { ENTER: { en: "Enter", zh: "进入", c: "var(--up)" }, MONITOR: { en: "Monitor", zh: "观察", c: "var(--muted)" }, AVOID: { en: "Avoid", zh: "回避", c: "var(--down)" } };
    var rows = b.assessments.map(function (a) {
      var v = NBV[a.verdict] || NBV.MONITOR;
      return '<div class="rp-brain-row">' +
        '<span class="rp-brain-badge" style="color:' + v.c + ';border-color:' + v.c + '">' + bi(v.en, v.zh) + "</span>" +
        '<b class="rp-brain-theme">' + bi(a.name || a.basket, a.name_zh || a.name || a.basket) + "</b>" +
        '<span class="rp-mut">' + bi("durability", "持续力") + " " + (a.composite == null ? "—" : a.composite) + " · " + esc(a.confidence || "") + "</span>" +
        '<div class="rp-brain-why">' + bi(a.rationale || "", a.rationale_zh || a.rationale || "") + "</div>" +
        "</div>";
    }).join("");
    var rot = b.rotation && b.rotation.summary
      ? '<div class="rp-brain-rot">🔁 ' + bi(b.rotation.summary, b.rotation.summary_zh || b.rotation.summary) + "</div>" : "";
    return '<div class="rp-brain"><div class="rp-brain-h">🧠 ' + bi("Narrative Brain", "叙事大脑") +
      ' <span class="rp-mut">· ' + bi("AI durability read, graded later", "AI持续力解读，事后评分") + "</span></div>" +
      rot + rows +
      '<p class="rp-cav">' + bi(b.disclaimer || "", b.disclaimer || "") + "</p></div>";
  }

  // ── Theme table row ────────────────────────────────────────────────────────
  function themeRow(f) {
    var s = st(f.state);
    var o = f.observable || {};
    var c = f.consensus || {};
    var edge = f.edge_score;
    var ecol = edgeColor(edge || 0);
    var rel = c.rel_60d;
    var relCol = rel > 0 ? "var(--up)" : rel < 0 ? "var(--down)" : "var(--muted)";
    var accel = o.accel;
    var accelCol = accel > 1.5 ? "var(--up)" : accel > 0.5 ? "var(--warn)" : "var(--muted)";
    var l = LIFE[f.lifecycle];
    var days = f.decay && f.decay.days_in_state;

    return "<tr>" +
      "<td>" + bi(f.name || f.basket, f.name_zh || f.name || f.basket) +
      (l ? '<div class="rp-life-tag" style="color:' + l.c + '">' + bi(l.en, l.zh) + "</div>" : "") + "</td>" +
      '<td class="rp-num" style="color:' + accelCol + '">' + (accel != null ? accel.toFixed(2) + "×" : "—") + "</td>" +
      '<td class="rp-num" style="color:' + relCol + '">' + relpct(rel) + "</td>" +
      '<td class="rp-num" style="color:' + ecol + ';font-weight:700">' + (edge != null ? edge : "—") + "</td>" +
      '<td class="rp-num rp-mut">' + (days != null ? days + "d" : "—") + "</td>" +
      "<td><div class=\"rp-strip-cell\">" + stripDots(f.state_strip) + "</div></td>" +
      '<td><span class="rp-badge ' + s.bgCls + '">' + s.ico + " " + bi(s.en, s.zh) + "</span></td>" +
      "</tr>";
  }

  // ── Name row ───────────────────────────────────────────────────────────────
  function nameRow(t, i) {
    var s = st(t.state);
    var edge = t.edge_score;
    var ecol = edgeColor(edge || 0);
    var rs = t.rs_vs_spy_60d;
    var rsCol = rs > 0 ? "var(--up)" : rs < 0 ? "var(--down)" : "var(--muted)";
    var expandId = "rp-nexp-" + i;
    var note = t.note || "";

    return '<div class="rp-name-row" onclick="(function(){var el=document.getElementById(\'' + expandId + '\');if(el)el.classList.toggle(\'rp-open\')})()">' +
      '<span class="rp-name-ticker">' + esc(t.ticker) + "</span>" +
      '<span class="rp-badge ' + s.bgCls + '">' + s.ico + "</span>" +
      '<span class="rp-name-basket">' + esc(t.basket_name || t.basket) + "</span>" +
      '<span class="rp-name-edge" style="color:' + ecol + '">' + (edge != null ? edge : "—") + "</span>" +
      '<span class="rp-name-rs" style="color:' + rsCol + '">' + (rs != null ? (rs > 0 ? "+" : "") + rs.toFixed(1) + "%" : "—") + "</span>" +
      "</div>" +
      (note ? '<div class="rp-name-expand" id="' + expandId + '"><div class="rp-mut" style="font-size:11.5px">' + esc(note) + "</div>" +
        (t.within_basket_pct != null ? '<div class="rp-mut" style="font-size:10px;margin-top:3px">' + bi("basket pct", "篮子百分位") + " <b>" + (t.within_basket_pct * 100).toFixed(0) + "%</b></div>" : "") +
        '</div>' : "");
  }

  // ── Accountability tab HTML ────────────────────────────────────────────────
  function acctHTML(ic, track) {
    var nSnap = (ic || {}).n_snapshots || 0;
    var nMat = (ic || {}).n_matured || 0;
    var open = (track || {}).open || 0;
    var icAll = (ic || {}).ic_all;
    var hitRate = ((track || {}).overall || {}).hit_rate;
    var dirAcc = ((track || {}).overall || {}).dir_accuracy;
    var bh = (ic || {}).by_horizon || {};
    var h21 = bh["21"] || {};
    var h63 = bh["63"] || {};

    var h = '<div class="rp-acct-note"><b>🔍 ' + bi("Honest null", "诚实空值") + ":</b> " +
      bi("This radar has " + nSnap + " recorded snapshots and " + nMat + " matured predictions. Grading requires horizons to elapse (21d / 63d). " + open + " theses are open. No performance claim is possible yet — this section auto-populates as horizons mature.",
        "雷达已记录" + nSnap + "个快照，" + nMat + "个已成熟预测。评级需等待时间窗口到期（21天/63天）。" + open + "个论点仍在跟踪。目前无法做出任何表现声明——本节将在到期时自动填充。") + "</div>";

    h += '<div class="rp-acct-grid">';
    function stat(val, lblEn, lblZh) {
      return '<div class="rp-acct-stat"><div class="rp-acct-val">' + esc(val) + "</div><div class=\"rp-acct-lbl\">" + bi(lblEn, lblZh) + "</div></div>";
    }
    h += stat(nSnap, "Snapshots recorded", "已记录快照");
    h += stat(nMat, "Matured predictions", "已成熟预测");
    h += stat(open, "Open theses", "开放论点");
    h += stat(icAll != null ? icAll.toFixed(3) : "—", "IC (all)", "IC (全部)");
    h += stat(hitRate != null ? (hitRate * 100).toFixed(0) + "%" : "—", "Hit rate", "命中率");
    h += stat(dirAcc != null ? (dirAcc * 100).toFixed(0) + "%" : "—", "Dir accuracy", "方向准确率");
    h += "</div>";

    h += '<div class="rp-horizon-row">';
    function horizonBlock(hd, hdata) {
      var ic = hdata.ic_all != null ? hdata.ic_all.toFixed(3) : "—";
      var hr = ((hdata.by_bucket || {})["40-70"] || {}).hit_rate;
      var hrStr = hr != null ? (hr * 100).toFixed(0) + "%" : "—";
      var n = hdata.n_matured || 0;
      return '<div class="rp-horizon"><div class="rp-horizon-h">' + hd + "d " + bi("horizon", "期限") + "</div>" +
        '<span class="rp-mut">IC: ' + ic + " · " + bi("Hit rate", "命中率") + ": " + hrStr + " · n=" + n + " " + bi("matured", "成熟") + "</span></div>";
    }
    h += horizonBlock(21, h21);
    h += horizonBlock(63, h63);
    h += "</div>";

    return h;
  }

  // ══════════════════════════════════════════════════════════════════════════
  //   renderDivergenceRadar — COMPACT shared panel (baskets.html embed)
  // ══════════════════════════════════════════════════════════════════════════
  window.renderDivergenceRadar = function (opts) {
    // Guard: if full mode already rendered into same mount, skip
    if (window._rpFullRendered) return;
    opts = opts || {};
    var base = opts.base || "basketdata/";
    var mount = document.querySelector(opts.mount || "#divergence-radar");
    if (!mount) return;

    injectStyles();

    Promise.all([
      fetchJSON(base + "radar.json"),
      fetchJSON(base + "radar_enriched.json"),
      fetchJSON(base + "radar_news.json")
    ]).then(function (results) {
      var d = results[0], enriched = results[1], newsMap = results[2];
      if (!d || !d.flags || !d.flags.length) { mount.style.display = "none"; return; }
      mergeEnrichment(d.flags, enriched, newsMap);
      var changes = (enriched || {}).changes;
      var cov = d.coverage || {};

      var divs = d.flags.filter(function (f) { return (f.state || "").indexOf("DIVERGENCE") >= 0; });
      divs.sort(function (a, b) { return (b.edge_score || b.salience || 0) - (a.edge_score || a.salience || 0); });

      var h = "";

      // Triage + delta in a band
      h += '<div class="rp-band">';
      h += triageHTML(d, enriched);
      if (changes) h += deltaHTML(changes);
      h += "</div>";

      // Spotlight
      h += '<div class="rp-spotlight">';
      if (!divs.length) {
        h += '<div class="rp-calm">' + bi(
          "No active divergences — federal spend and price agree across the " + (cov.themes_covered || 0) + " covered themes.",
          "暂无背离 —— 在 " + (cov.themes_covered || 0) + " 个覆盖主题中，联邦支出与价格一致。") + "</div>";
      } else {
        var TOP = 3;
        var topDivs = divs.slice(0, TOP);
        var restDivs = divs.slice(TOP);

        h += '<div class="rp-spot-h"><span class="rp-spot-title">🎯 ' + bi("Active Divergences", "活跃背离") + "</span>" +
          '<span class="rp-spot-cnt">' + bi(divs.length + " ranked by edge", "按优势分排序 " + divs.length + " 个") + "</span></div>";

        h += '<div class="rp-cards">' + topDivs.map(function (f, i) { return fullCard(f, i); }).join("") + "</div>";

        if (restDivs.length) {
          h += '<div class="rp-compact-h">' + bi("All divergences", "全部背离") + "</div>";
          h += restDivs.map(function (f, i) { return compactRow(f, i, "rp-cexp-c"); }).join("");
          if (restDivs.length > 4) {
            h += '<button class="rp-show-ctrl" id="rp-show-all-c" onclick="(function(btn){var rows=document.querySelectorAll(\'[id^=rp-cexp-c-]\');var hidden=!document.getElementById(\'rp-cexp-c-4\').style.display||document.querySelectorAll(\'.rp-compact-row\')[4].style.display===\'none\';rows.forEach(function(r,i){var row=r.previousElementSibling;if(i>=4){r.style.display=\'\';if(row)row.style.display=\'\'}});btn.style.display=\'none\'})(this)">' +
              bi("Show all " + restDivs.length + " divergences", "显示全部" + restDivs.length + "个背离") + "</button>";
            // hide rows beyond index 3 by post-processing in next tick
            setTimeout(function () {
              var compactRows = mount.querySelectorAll("[id^='rp-cexp-c-']");
              compactRows.forEach(function (el, i) {
                if (i >= 4) {
                  el.style.display = "none";
                  var rowEl = el.previousElementSibling;
                  if (rowEl && rowEl.classList.contains("rp-compact-row")) rowEl.style.display = "none";
                }
              });
            }, 0);
          }
        }
      }
      h += "</div>";

      // All-themes table (compact)
      h += '<div class="rp-band">';
      h += '<div style="overflow-x:auto"><table class="rp-tbl"><thead><tr>' +
        "<th>" + bi("Theme", "主题") + "</th>" +
        "<th>" + bi("Spend YoY", "支出同比") + "</th>" +
        "<th>" + bi("Price 60d", "价格60日") + "</th>" +
        "<th>" + bi("Edge", "优势") + "</th>" +
        "<th>" + bi("Days", "天数") + "</th>" +
        "<th>" + bi("14d", "14日") + "</th>" +
        "<th>" + bi("State", "状态") + "</th>" +
        "</tr></thead><tbody>" +
        d.flags.filter(function (f) { return f.state !== "QUIET"; }).map(themeRow).join("") +
        "</tbody></table></div>";
      h += "</div>";

      // Caveat
      if ((d.caveats || []).length) {
        h += '<p class="rp-cav-block">' + bi(d.caveats[0], (d.caveats_zh || [])[0] || d.caveats[0]) + "</p>";
      }

      // Brain slot (filled async)
      h += '<div id="rp-brain-slot-c"></div>';

      mount.style.display = "";
      mount.innerHTML = h;

      // Fetch brain async
      fetchJSON(base + "narrative_brain.json").then(function (b) {
        var slot = mount.querySelector("#rp-brain-slot-c");
        if (slot) slot.innerHTML = brainHTML(b, true);
      });
    });
  };

  // ══════════════════════════════════════════════════════════════════════════
  //   renderRadarFull — FULL page (radar.html)
  // ══════════════════════════════════════════════════════════════════════════
  window.renderRadarFull = function (opts) {
    opts = opts || {};
    var base = opts.base || "basketdata/";
    var mount = document.querySelector(opts.mount || "#divergence-radar");
    if (!mount) return;

    injectStyles();
    window._rpFullRendered = true;

    // Full mode: per-name and accountability state
    var _allTickers = [];
    var _allFlags = [];
    var _themeFilter = "all";
    var _quietVisible = false;
    var _showAllDivs = false;
    var _sortCol = "edge", _sortAsc = false;
    var _nameVisible = 20;
    var _nameFiltered = [];
    var _mountId = "rp-full-" + Date.now();
    mount.setAttribute("data-rp-id", _mountId);

    function byId(id) { return mount.querySelector("#" + id); }

    Promise.all([
      fetchJSON(base + "radar.json"),
      fetchJSON(base + "radar_enriched.json"),
      fetchJSON(base + "radar_news.json"),
      fetchJSON(base + "radar_ticker.json"),
      fetchJSON(base + "radar_ic.json"),
      fetchJSON(base + "radar_track_record.json"),
      fetchJSON(base + "narrative_brain.json")
    ]).then(function (results) {
      var radar = results[0], enriched = results[1], newsMap = results[2];
      var tickers = results[3], ic = results[4], track = results[5], brain = results[6];

      if (!radar || !radar.flags || !radar.flags.length) { mount.style.display = "none"; return; }
      mergeEnrichment(radar.flags, enriched, newsMap);
      _allFlags = radar.flags;
      _allTickers = (tickers && tickers.tickers) || [];

      var changes = (enriched || {}).changes;
      var cov = radar.coverage || {};
      var divs = radar.flags.filter(function (f) { return (f.state || "").indexOf("DIVERGENCE") >= 0; });
      divs.sort(function (a, b) { return (b.edge_score || b.salience || 0) - (a.edge_score || a.salience || 0); });

      // Sort all tickers by edge desc for per-name tab
      _nameFiltered = _allTickers.slice().sort(function (a, b) { return (b.edge_score || 0) - (a.edge_score || 0); });

      var h = "";

      // ── LAYER 1: Overview band ────────────────────────────────────────────
      h += '<div class="rp-band">';
      h += triageHTML(radar, enriched);
      if (changes) h += deltaHTML(changes);

      // Scatter
      h += '<div class="rp-scatter-wrap">';
      h += '<div class="rp-scatter-lbl">';
      h += '<span class="rp-mut">' + bi("price 60d rel · all " + cov.themes_covered + " themes · dot size = edge score", "60日相对价格 · 全部" + cov.themes_covered + "主题 · 点大小 = 优势分") + "</span>";
      h += '<span class="rp-scatter-legend">';
      h += '<span style="color:var(--down)">● ' + bi("Neg Div", "负背离") + "</span>";
      h += '<span style="color:var(--muted)">● ' + bi("Conf Down", "确认走弱") + "</span>";
      h += '<span style="color:color-mix(in srgb,var(--muted) 40%,transparent)">● ' + bi("Quiet", "平静") + "</span>";
      h += "</span></div>";
      h += '<canvas class="rp-scatter-canvas" id="rp-scatter" height="80"></canvas>';
      h += "</div></div>"; // close scatter-wrap + band

      // ── LAYER 2: Lifecycle pipeline ───────────────────────────────────────
      h += '<div class="rp-lifecycle">';
      h += '<div class="rp-lifecycle-h">' + bi("Lifecycle Pipeline", "生命周期管线") + "</div>";
      h += lifecycleHTML(radar.flags);
      h += "</div>";

      // ── LAYER 2: Spotlight deck ───────────────────────────────────────────
      h += '<div class="rp-spotlight">';
      if (!divs.length) {
        h += '<div class="rp-calm">' + bi("No active divergences today.", "今日暂无背离。") + "</div>";
      } else {
        var TOP = 4;
        var topDivs = divs.slice(0, TOP);
        var restDivs = divs.slice(TOP);
        h += '<div class="rp-spot-h"><span class="rp-spot-title">🎯 ' + bi("Active Divergences", "活跃背离") + "</span>" +
          '<span class="rp-spot-cnt">' + bi(divs.length + " ranked by edge", "按优势分排序 " + divs.length + " 个") + "</span>" +
          '<div class="rp-spot-ctrl"><button class="rp-spot-btn" id="rp-goto-names">' +
          bi("filter per-name ↓", "筛选个股↓") + "</button></div></div>";

        h += '<div class="rp-cards">' + topDivs.map(function (f, i) { return fullCard(f, i); }).join("") + "</div>";

        if (restDivs.length) {
          h += '<div class="rp-compact-h">' + bi("All divergences", "全部背离") + "</div>";
          h += '<div id="rp-compact-rows">' + restDivs.map(function (f, i) { return compactRow(f, TOP + i, "rp-cexp-f"); }).join("") + "</div>";
          if (restDivs.length > 4) {
            h += '<button class="rp-show-ctrl" id="rp-show-all">' + bi("Show all " + restDivs.length + " divergences", "显示全部" + restDivs.length + "个背离") + "</button>";
          }
        }
      }
      h += "</div>"; // close spotlight

      // ── LAYER 3: Tabs ─────────────────────────────────────────────────────
      var tCount = _allTickers.length || 0;
      h += '<div class="rp-tabs-wrap">';
      h += '<div class="rp-tabs-nav">';
      h += '<button class="rp-tab-btn rp-active" id="rp-tbtn-themes">' + bi("All Themes", "全部主题") + "</button>";
      h += '<button class="rp-tab-btn" id="rp-tbtn-names">' + bi("Per-Name", "个股") + " (" + tCount + ")</button>";
      h += '<button class="rp-tab-btn" id="rp-tbtn-acct">' + bi("Accountability", "可信度") + "</button>";
      h += "</div>";

      // Tab: All Themes
      h += '<div class="rp-tab-body rp-active" id="rp-tab-themes">';
      h += '<div class="rp-theme-ctrl">';
      h += '<button class="rp-fchip rp-active" id="rp-fc-all">' + bi("All", "全部") + "</button>";
      h += '<button class="rp-fchip" id="rp-fc-div">' + bi("Divergences", "背离") + "</button>";
      h += '<button class="rp-fchip" id="rp-fc-conf">' + bi("Confirmed", "确认") + "</button>";
      h += '<button class="rp-fchip" id="rp-fc-quiet">' + bi("Quiet", "平静") + "</button>";
      h += '<button class="rp-quiet-tog" id="rp-quiet-tog">' + bi("show " + radar.flags.filter(function (f) { return f.state === "QUIET"; }).length + " quiet", "显示" + radar.flags.filter(function (f) { return f.state === "QUIET"; }).length + "个平静") + "</button>";
      h += "</div>";
      h += '<div style="overflow-x:auto"><table class="rp-tbl" id="rp-theme-tbl">';
      h += "<thead><tr>";
      var cols = [
        { id: "name", en: "Theme", zh: "主题" },
        { id: "accel", en: "Spend YoY", zh: "支出同比" },
        { id: "rel60", en: "Price 60d", zh: "价格60日" },
        { id: "edge", en: "Edge", zh: "优势" },
        { id: "days", en: "Days", zh: "天数" },
        { id: "strip", en: "14d Strip", zh: "14日", nosort: true },
        { id: "state", en: "State", zh: "状态", nosort: true }
      ];
      cols.forEach(function (col) {
        h += '<th' + (!col.nosort ? ' id="rp-th-' + col.id + '" data-col="' + col.id + '"' : "") + ">" + bi(col.en, col.zh) + (!col.nosort ? '<span class="rp-sico">↕</span>' : "") + "</th>";
      });
      h += "</tr></thead>";
      h += '<tbody id="rp-theme-tbody"></tbody>';
      h += "</table></div>";
      h += '<div id="rp-quiet-rows" style="display:none"></div>';
      h += "</div>"; // close tab-themes

      // Tab: Per-Name
      h += '<div class="rp-tab-body" id="rp-tab-names">';
      h += '<div class="rp-name-ctrl">';
      h += '<input class="rp-name-search" id="rp-name-q" placeholder="' + (document.documentElement.getAttribute("data-lang") === "zh" ? "搜索代码…" : "Search ticker…") + '">';
      h += '<select class="rp-name-sel" id="rp-name-state">';
      h += '<option value="all">' + bi("All states", "全部状态") + "</option>";
      h += '<option value="NEGATIVE_DIVERGENCE">' + bi("Neg Divergence", "负背离") + "</option>";
      h += '<option value="POSITIVE_DIVERGENCE">' + bi("Pos Divergence", "正背离") + "</option>";
      h += '<option value="CONFIRMED_DOWN">' + bi("Confirmed Down", "确认走弱") + "</option>";
      h += '<option value="QUIET">' + bi("Quiet", "平静") + "</option>";
      h += "</select>";
      h += '<select class="rp-name-sel" id="rp-name-basket"><option value="all">' + bi("All baskets", "全部篮子") + "</option></select>";
      h += "</div>";
      h += '<div id="rp-name-rows"></div>';
      h += '<button class="rp-show-more" id="rp-name-more">' + bi("Show 20 more", "再显示20个") + "</button>";
      h += "</div>"; // close tab-names

      // Tab: Accountability
      h += '<div class="rp-tab-body" id="rp-tab-acct">';
      h += acctHTML(ic, track);
      h += '<p style="font-size:10px;color:var(--muted);margin-top:8px;line-height:1.5">' +
        bi("Radar IC schema v1 · Track record schema v1 · Display-only context, no allocation signal.",
          "雷达IC架构v1 · 记录模式v1 · 仅供参考，不作为配置信号。") + "</p>";
      h += "</div>"; // close tab-acct

      h += "</div>"; // close tabs-wrap

      // Narrative Brain
      h += '<div id="rp-brain-slot"></div>';

      // Caveat
      if ((radar.caveats || []).length) {
        h += '<p class="rp-cav-block">' + bi(radar.caveats[0], (radar.caveats_zh || [])[0] || radar.caveats[0]) + "</p>";
      }

      mount.style.display = "";
      mount.innerHTML = h;

      // ── Post-render setup ────────────────────────────────────────────────
      // Scatter
      setTimeout(function () {
        var canvas = byId("rp-scatter");
        if (canvas) drawScatter(canvas, radar.flags);
      }, 0);

      // Brain
      if (brain) byId("rp-brain-slot").innerHTML = brainHTML(brain, false);

      // Theme table initial render
      populateThemesTable(_allFlags);

      // Per-name: populate basket dropdown
      var bmap = {};
      _allTickers.forEach(function (t) { if (t.basket && t.basket_name) bmap[t.basket] = t.basket_name; });
      var basketSel = byId("rp-name-basket");
      Object.keys(bmap).sort().forEach(function (k) {
        var opt = document.createElement("option");
        opt.value = k; opt.textContent = bmap[k];
        if (basketSel) basketSel.appendChild(opt);
      });
      renderNameRows();

      // "Show all" compact rows
      if (restDivs && restDivs.length > 4) {
        var compactExpands = mount.querySelectorAll("[id^='rp-cexp-f-']");
        compactExpands.forEach(function (el, i) {
          if (i >= 4) {
            el.style.display = "none";
            var rowEl = el.previousElementSibling;
            if (rowEl && rowEl.classList.contains("rp-compact-row")) rowEl.style.display = "none";
          }
        });
        var showAllBtn = byId("rp-show-all");
        if (showAllBtn) {
          showAllBtn.addEventListener("click", function () {
            _showAllDivs = !_showAllDivs;
            mount.querySelectorAll("[id^='rp-cexp-f-']").forEach(function (el, i) {
              if (i >= 4) {
                var rowEl = el.previousElementSibling;
                if (_showAllDivs) {
                  el.style.display = "";
                  if (rowEl) rowEl.style.display = "";
                } else {
                  el.style.display = "none";
                  if (rowEl) rowEl.style.display = "none";
                }
              }
            });
            showAllBtn.innerHTML = _showAllDivs
              ? bi("Collapse", "收起")
              : bi("Show all " + restDivs.length + " divergences", "显示全部" + restDivs.length + "个背离");
          });
        }
      }

      // Tab navigation
      function showTab(tabId, btnId) {
        ["themes", "names", "acct"].forEach(function (t) {
          var tb = byId("rp-tab-" + t);
          var bb = byId("rp-tbtn-" + t);
          if (tb) tb.classList.toggle("rp-active", "rp-tab-" + t === tabId);
          if (bb) bb.classList.toggle("rp-active", "rp-tbtn-" + t === btnId);
        });
      }

      var tbThemes = byId("rp-tbtn-themes");
      var tbNames = byId("rp-tbtn-names");
      var tbAcct = byId("rp-tbtn-acct");
      if (tbThemes) tbThemes.addEventListener("click", function () { showTab("rp-tab-themes", "rp-tbtn-themes"); });
      if (tbNames) tbNames.addEventListener("click", function () { showTab("rp-tab-names", "rp-tbtn-names"); });
      if (tbAcct) tbAcct.addEventListener("click", function () { showTab("rp-tab-acct", "rp-tbtn-acct"); });

      // "names ▸" from spotlight
      var gotoNames = byId("rp-goto-names");
      if (gotoNames) {
        gotoNames.addEventListener("click", function () {
          showTab("rp-tab-names", "rp-tbtn-names");
          var wrap = mount.querySelector(".rp-tabs-wrap");
          if (wrap) wrap.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }

      // Filter chips
      function setFilter(f, activeId) {
        _themeFilter = f;
        _quietVisible = f === "quiet";
        ["rp-fc-all", "rp-fc-div", "rp-fc-conf", "rp-fc-quiet"].forEach(function (id) {
          var el = byId(id);
          if (el) el.classList.toggle("rp-active", id === activeId);
        });
        populateThemesTable(_allFlags);
      }
      var fc_all = byId("rp-fc-all"); if (fc_all) fc_all.addEventListener("click", function () { setFilter("all", "rp-fc-all"); });
      var fc_div = byId("rp-fc-div"); if (fc_div) fc_div.addEventListener("click", function () { setFilter("div", "rp-fc-div"); });
      var fc_conf = byId("rp-fc-conf"); if (fc_conf) fc_conf.addEventListener("click", function () { setFilter("conf", "rp-fc-conf"); });
      var fc_quiet = byId("rp-fc-quiet"); if (fc_quiet) fc_quiet.addEventListener("click", function () { setFilter("quiet", "rp-fc-quiet"); });

      // Quiet toggle
      var qtog = byId("rp-quiet-tog");
      if (qtog) qtog.addEventListener("click", function () {
        _quietVisible = !_quietVisible;
        populateThemesTable(_allFlags);
      });

      // Sortable columns
      cols.forEach(function (col) {
        if (col.nosort) return;
        var th = byId("rp-th-" + col.id);
        if (!th) return;
        th.addEventListener("click", function () {
          if (_sortCol === col.id) { _sortAsc = !_sortAsc; } else { _sortCol = col.id; _sortAsc = false; }
          populateThemesTable(_allFlags);
        });
      });

      // Per-name search/filter
      var nameQ = byId("rp-name-q");
      var nameState = byId("rp-name-state");
      var nameBasket = byId("rp-name-basket");
      function doFilterNames() {
        var q = (nameQ ? nameQ.value || "" : "").toLowerCase();
        var stF = nameState ? nameState.value : "all";
        var bsF = nameBasket ? nameBasket.value : "all";
        _nameFiltered = _allTickers.filter(function (t) {
          if (q && !(t.ticker || "").toLowerCase().startsWith(q) && !(t.basket_name || "").toLowerCase().includes(q)) return false;
          if (stF !== "all" && t.state !== stF) return false;
          if (bsF !== "all" && t.basket !== bsF) return false;
          return true;
        }).sort(function (a, b) { return (b.edge_score || 0) - (a.edge_score || 0); });
        _nameVisible = 20;
        renderNameRows();
      }
      if (nameQ) nameQ.addEventListener("input", doFilterNames);
      if (nameState) nameState.addEventListener("change", doFilterNames);
      if (nameBasket) nameBasket.addEventListener("change", doFilterNames);

      // Show more names
      var nameMoreBtn = byId("rp-name-more");
      if (nameMoreBtn) nameMoreBtn.addEventListener("click", function () { _nameVisible += 20; renderNameRows(); });

    }); // end Promise.all

    // ── Theme table populate ────────────────────────────────────────────────
    function sortVal(f) {
      if (_sortCol === "name") return f.name || "";
      if (_sortCol === "accel") return (f.observable && f.observable.accel != null) ? f.observable.accel : -999;
      if (_sortCol === "rel60") return (f.consensus && f.consensus.rel_60d != null) ? f.consensus.rel_60d : -999;
      if (_sortCol === "edge") return f.edge_score || 0;
      if (_sortCol === "days") return (f.decay && f.decay.days_in_state) || 0;
      return 0;
    }

    function populateThemesTable(flags) {
      var tbody = mount.querySelector("#rp-theme-tbody");
      if (!tbody) return;
      var quietFlags = flags.filter(function (f) { return f.state === "QUIET"; });
      var nonQuiet = flags.filter(function (f) { return f.state !== "QUIET"; });

      var toShow;
      if (_themeFilter === "div") toShow = flags.filter(function (f) { return (f.state || "").indexOf("DIVERGENCE") >= 0; });
      else if (_themeFilter === "conf") toShow = flags.filter(function (f) { return (f.state || "").indexOf("CONFIRMED") >= 0; });
      else if (_themeFilter === "quiet") { toShow = quietFlags; _quietVisible = true; }
      else toShow = nonQuiet;

      toShow = toShow.slice().sort(function (a, b) {
        var va = sortVal(a), vb = sortVal(b);
        return _sortAsc ? (va > vb ? 1 : va < vb ? -1 : 0) : (va < vb ? 1 : va > vb ? -1 : 0);
      });

      tbody.innerHTML = toShow.map(themeRow).join("");

      // Quiet section
      var qSection = mount.querySelector("#rp-quiet-rows");
      var qtog = mount.querySelector("#rp-quiet-tog");
      if (_themeFilter === "all") {
        if (qtog) qtog.style.display = "";
        if (qSection) {
          if (_quietVisible) {
            var sortedQ = quietFlags.slice().sort(function (a, b) {
              var va = sortVal(a), vb = sortVal(b);
              return _sortAsc ? (va > vb ? 1 : va < vb ? -1 : 0) : (va < vb ? 1 : va > vb ? -1 : 0);
            });
            qSection.innerHTML = '<div style="overflow-x:auto"><table class="rp-tbl"><tbody>' +
              sortedQ.map(themeRow).join("") + "</tbody></table></div>";
            qSection.style.display = "";
            if (qtog) qtog.innerHTML = bi("hide " + quietFlags.length + " quiet", "隐藏" + quietFlags.length + "个平静");
          } else {
            qSection.style.display = "none";
            if (qtog) qtog.innerHTML = bi("show " + quietFlags.length + " quiet", "显示" + quietFlags.length + "个平静");
          }
        }
      } else {
        if (qtog) qtog.style.display = "none";
        if (qSection) qSection.style.display = "none";
      }

      // Update sort header icons
      mount.querySelectorAll(".rp-tbl th[data-col]").forEach(function (th) {
        th.classList.remove("rp-sorted");
        var ico = th.querySelector(".rp-sico");
        if (ico) ico.textContent = "↕";
      });
      var activeH = mount.querySelector('.rp-tbl th[data-col="' + _sortCol + '"]');
      if (activeH) {
        activeH.classList.add("rp-sorted");
        var ico = activeH.querySelector(".rp-sico");
        if (ico) ico.textContent = _sortAsc ? "↑" : "↓";
      }
    }

    // ── Per-name rows render ────────────────────────────────────────────────
    function renderNameRows() {
      var rowsEl = mount.querySelector("#rp-name-rows");
      if (!rowsEl) return;
      var shown = _nameFiltered.slice(0, _nameVisible);
      rowsEl.innerHTML = shown.map(function (t, i) { return nameRow(t, i); }).join("");
      var moreBtn = mount.querySelector("#rp-name-more");
      if (moreBtn) moreBtn.style.display = _nameFiltered.length > _nameVisible ? "" : "none";
    }

  }; // end renderRadarFull

  // ══════════════════════════════════════════════════════════════════════════
  //   Legacy no-op guards (old radar.html will call these; full mode takes over)
  // ══════════════════════════════════════════════════════════════════════════
  window.renderRadarLifecycle = function (opts) {
    // No-op: renderRadarFull handles lifecycle inline now.
    // Legacy radar.html pages that call this after renderRadarFull has mounted are safe.
  };

  window.renderTickerRadar = function (opts) {
    // No-op: per-name is handled inside the Per-Name tab of renderRadarFull.
    // Legacy pages that call this are safe.
  };

})();

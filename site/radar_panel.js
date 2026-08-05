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
  //   FULL PAGE (radar.html) — "mx-radar" redesign
  //   User-first doctrine: state + stance + plain line on the glance tier;
  //   mechanics/receipts demoted to hover + the Details section. Honest about
  //   the radar's own (negative) track record — this is watch-only context.
  //   Shares only pure text helpers with the compact embed (esc/bi/usd/relpct/
  //   st/mergeEnrichment); all visual markup below is rx- prefixed and self-
  //   contained so the baskets.html embed (renderDivergenceRadar) is untouched.
  // ══════════════════════════════════════════════════════════════════════════

  // Plain-word state map (Doctrine Law 2 — no DIVERGENCE / CONFIRMED enums on tier 1).
  // `tone` drives the ONE colour language on this page: green = activity ahead,
  // amber = price ahead, blue = the two agree, muted = nothing doing. Nothing else
  // on the page may spend colour, so a hue always means the same thing.
  var PLAIN = {
    POSITIVE_DIVERGENCE: { en: "Activity ahead of price", zh: "活动领先价格", short_en: "Activity leads", short_zh: "活动领先",
      stance_en: "Watch — don't chase", stance_zh: "观察 — 别追", tone: "up",
      gist_en: "The real work behind this theme is speeding up while price still trails.",
      gist_zh: "该主题背后的真实活动正在加速，而价格仍未跟上。" },
    NEGATIVE_DIVERGENCE: { en: "Price ahead of activity", zh: "价格领先活动", short_en: "Price leads", short_zh: "价格领先",
      stance_en: "Stand aside", stance_zh: "旁观", tone: "down",
      gist_en: "Price has run up while the real work behind it has slowed.",
      gist_zh: "价格已经上涨，而其背后的真实活动却在放缓。" },
    CONFIRMED_UP: { en: "Both rising", zh: "同步上行", short_en: "Both rising", short_zh: "同步上行",
      stance_en: "Already in the price", stance_zh: "已反映在价格", tone: "agree",
      gist_en: "Price and the real work behind it are rising together — real, but already paid for.",
      gist_zh: "价格与其背后的真实活动同步上行 —— 是真的，但已经付过钱了。" },
    CONFIRMED_DOWN: { en: "Both cooling", zh: "同步走弱", short_en: "Both cooling", short_zh: "同步走弱",
      stance_en: "Already in the price", stance_zh: "已反映在价格", tone: "agree",
      gist_en: "Price and the real work behind it are cooling together.",
      gist_zh: "价格与其背后的真实活动同步降温。" },
    BROKEN_LAGGARD: { en: "Falling behind", zh: "掉队", short_en: "Falling behind", short_zh: "掉队",
      stance_en: "Stand aside", stance_zh: "旁观", tone: "down",
      gist_en: "This name keeps losing ground to the theme it belongs to.",
      gist_zh: "该个股持续落后于其所属主题。" },
    QUIET: { en: "In line", zh: "平静", short_en: "In line", short_zh: "平静",
      stance_en: "Nothing to do", stance_zh: "无需操作", tone: "flat",
      gist_en: "Activity and price are moving together. Nothing to act on.",
      gist_zh: "活动与价格同步变动。无需操作。" }
  };
  function plain(state) { return PLAIN[state] || PLAIN.QUIET; }
  function toneCol(t) {
    return t === "up" ? "var(--up)" : t === "down" ? "var(--warn)" : t === "agree" ? "var(--info)" : "var(--muted)";
  }

  // Raw collector slugs → the words a person uses. The engine's own label_en still
  // carries vendor tags ("Gov contracts (Quiver)") and filing codes ("8-K material
  // events"); neither belongs in front of a reader, so this map wins and the
  // fallback strips any trailing "(vendor)" from an unmapped label.
  var SRC = {
    quiver_govcontract:     { en: "government contracts", zh: "政府合同" },
    usaspending:            { en: "federal contracts",    zh: "联邦合同" },
    usaspending_assistance: { en: "federal grants",       zh: "联邦补助" },
    congress_netbuy:        { en: "congress trading",     zh: "国会议员交易" },
    lobbying_ramp:          { en: "lobbying spend",       zh: "游说支出" },
    edgar_8k_velocity:      { en: "company filings",      zh: "公司公告" },
    fedreg_velocity:        { en: "new regulations",      zh: "新规发布" },
    news_velocity:          { en: "news coverage",        zh: "新闻报道" }
  };
  function srcName(s) {
    var m = SRC[s.name];
    if (m) return m;
    var en = String(s.label_en || s.name || "").replace(/\s*\([^)]*\)\s*$/, "").toLowerCase();
    return { en: en, zh: s.label_zh || en };
  }
  // Sources ranked by how hard they are pulling, strongest first.
  function rankedSources(o) {
    return (((o || {}).sources) || []).slice().sort(function (a, b) {
      return Math.abs(b.z || 0) - Math.abs(a.z || 0);
    });
  }
  function moveWord(z) {
    if (z >= 0.5) return { en: "picking up", zh: "升温", tone: "up" };
    if (z <= -0.5) return { en: "slowing", zh: "放缓", tone: "down" };
    return { en: "steady", zh: "平稳", tone: "flat" };
  }

  // ── Deep links ────────────────────────────────────────────────────────────
  // Theme name → its own detail page (site/basket/<id>.html, one per radar flag).
  // Ticker → stock.html#TICKER, the shape theme.js intercepts in the capture phase
  // and opens in the Terminal workspace. `?t=` is NOT intercepted — do not use it.
  function themeHref(basket) {
    return basket ? "basket/" + encodeURIComponent(basket) + ".html" : "";
  }
  function themeLink(f, cls) {
    var label = bi(f.name || f.basket, f.name_zh || f.name || f.basket);
    var href = themeHref(f.basket);
    if (!href) return '<span class="' + cls + '">' + label + "</span>";
    return '<a class="' + cls + ' rx-tlink" href="' + esc(href) + '">' + label + "</a>";
  }
  function tickerLink(t) {
    var tk = String(t || "").trim();
    if (!tk) return "";
    return '<a class="rx-tk" href="stock.html#' + encodeURIComponent(tk) + '">' + esc(tk) + "</a>";
  }
  // <option> renders text, not elements, so the bi() dual-span shows BOTH languages
  // glued together ("All reads全部解读"). Options carry their pair as data and get
  // repainted on the site's `langchange` event instead.
  function isZh() { return document.documentElement.getAttribute("data-lang") === "zh"; }
  function opt(value, en, zh) {
    return '<option value="' + esc(value) + '" data-l-en="' + esc(en) + '" data-l-zh="' + esc(zh) + '">' +
      esc(isZh() ? zh : en) + "</option>";
  }
  function repaintOptionLang(root) {
    var zh = isZh();
    (root || document).querySelectorAll("[data-l-en]").forEach(function (el) {
      el.textContent = el.getAttribute(zh ? "data-l-zh" : "data-l-en") || "";
    });
  }

  function tickerList(list, cap) {
    var arr = (list || []).filter(Boolean);
    if (!arr.length) return "";
    var shown = cap ? arr.slice(0, cap) : arr;
    var h = shown.map(tickerLink).join('<span class="rx-tk-sep">·</span>');
    var rest = arr.length - shown.length;
    if (rest > 0) h += '<span class="rx-tk-more">' + bi("+" + rest + " more", "另 " + rest + " 只") + "</span>";
    return h;
  }

  // ── Numbers that arrive with their meaning (Doctrine Law 3) ───────────────
  function pricePhrase(rel) {
    if (rel == null) return { en: "price is level with the market", zh: "价格与大盘持平" };
    var p = Math.round(Math.abs(rel) * 100);
    if (p < 2) return { en: "price is level with the market", zh: "价格与大盘持平" };
    return rel > 0
      ? { en: "price is " + p + "% ahead of the market", zh: "价格领先大盘 " + p + "%" }
      : { en: "price is " + p + "% behind the market", zh: "价格落后大盘 " + p + "%" };
  }
  function activityPhrase(accel) {
    if (accel == null) return { en: "is holding steady", zh: "保持平稳" };
    if (accel >= 1.15) return { en: "is speeding up", zh: "正在加速" };
    if (accel <= 0.9) return { en: "is slowing", zh: "正在放缓" };
    return { en: "is holding steady", zh: "保持平稳" };
  }
  // The card's one line, composed from the same primitives the engine used — the
  // engine's own note ships raw slugs, a ticker dump and "YoY", none of which
  // belong on the glance tier.
  function cardLine(f) {
    var o = f.observable || {}, c = f.consensus || {};
    var top = rankedSources(o).slice(0, 2).map(srcName);
    // "The work" carries the verb in every sentence below, so the source list is
    // always an aside and never has to agree with a verb of its own.
    var asideEn = top.length ? " — mostly " + top.map(function (s) { return s.en; }).join(" and ") + " — " : " ";
    var asideZh = top.length ? " —— 主要来自" + top.map(function (s) { return s.zh; }).join("、") + " —— " : "";
    var price = pricePhrase(c.rel_60d), act = activityPhrase(o.accel);
    var st = f.state;
    if (st === "POSITIVE_DIVERGENCE") {
      return bi("The work behind this theme" + asideEn + act.en + ", while " + price.en + " over 60 days.",
        "该主题背后的真实活动" + asideZh + act.zh + "，而" + price.zh + "（过去60天）。");
    }
    if (st === "NEGATIVE_DIVERGENCE") {
      return bi(price.en.charAt(0).toUpperCase() + price.en.slice(1) + " over 60 days, but the work behind it" +
        asideEn + act.en + ".",
        price.zh + "（过去60天），但其背后的真实活动" + asideZh + act.zh + "。");
    }
    if (st === "CONFIRMED_UP" || st === "CONFIRMED_DOWN") {
      var dir = st === "CONFIRMED_UP"
        ? { en: "are rising together", zh: "同步上行" }
        : { en: "are cooling together", zh: "同步走弱" };
      return bi("Price and the work behind it " + dir.en + " — " + price.en + " over 60 days.",
        "价格与其背后的真实活动" + dir.zh + " —— " + price.zh + "（过去60天）。");
    }
    return bi("The work and the price are moving together — " + price.en + " over 60 days.",
      "真实活动与价格同步变动 —— " + price.zh + "（过去60天）。");
  }

  // ── The gap meter — this page's signature ─────────────────────────────────
  // One rail, one centre tick ("in line"), two dots and the bar between them.
  // The BAR is the read: its length is how far the two have come apart and its
  // colour is which of them is in front. Drawn instead of named, so a card needs
  // no chip strip to say the same thing.
  //   real work: 1.0× (unchanged from a year ago) sits dead centre; the scale is
  //              logarithmic so 4× and 0.25× land on the ends.
  //   price:     level with the market sits dead centre; ±40% lands on the ends.
  // Both are clamped, and the exact figures live on the dots' hover (tier 2).
  function clampPos(x) { return Math.max(4, Math.min(96, x)); }
  function activityPos(accel) {
    if (accel == null) return null;
    var r = Math.log(Math.max(accel, 0.02)) / Math.log(4);
    return clampPos(50 + Math.max(-1, Math.min(1, r)) * 46);
  }
  function pricePos(rel) {
    if (rel == null) return null;
    return clampPos(50 + Math.max(-1, Math.min(1, rel / 0.4)) * 46);
  }
  // Each marker labels itself, on its own row, so two markers can never collide and
  // the meter needs no legend repeated under every card.
  function gapMeter(f) {
    var o = f.observable || {}, c = f.consensus || {};
    var a = activityPos(o.accel), p = pricePos(c.rel_60d);
    if (a == null || p == null) return "";
    var col = toneCol(plain(f.state).tone);
    var lo = Math.min(a, p), hi = Math.max(a, p);
    var accelTip = o.accel == null ? "—" : o.accel.toFixed(2) + "×";
    var relTip = c.rel_60d == null ? "—" : relpct(c.rel_60d);
    // A marker parked at either end would centre its label outside the card, so the
    // label anchors to the marker's near edge there instead of drifting off it.
    function lab(cls, pos, en, zh, tipEn, tipZh) {
      var anchor = pos < 16 ? "rx-meter-lab-l" : pos > 84 ? "rx-meter-lab-r" : "";
      return '<span class="rx-meter-lab ' + cls + " " + anchor + '" style="left:' + pos.toFixed(1) + '%" ' +
        'data-tip-en="' + esc(tipEn) + '" data-tip-zh="' + esc(tipZh) + '">' + bi(en, zh) + "</span>";
    }
    var workTipEn = "The real work behind this theme is running at " + accelTip + " the pace of a year ago.";
    var workTipZh = "该主题背后的真实活动，为一年前节奏的 " + accelTip + "。";
    var priceTipEn = "Price against the market over the last 60 days: " + relTip + ".";
    var priceTipZh = "过去60天价格相对大盘：" + relTip + "。";
    return '<div class="rx-meter" style="--mc:' + col + '">' +
      '<div class="rx-meter-row rx-meter-top">' + lab("rx-meter-lwork", a, "real work", "真实活动", workTipEn, workTipZh) + "</div>" +
      '<div class="rx-meter-rail">' +
        '<span class="rx-meter-zero"></span>' +
        '<span class="rx-meter-gap" style="left:' + lo.toFixed(1) + '%;width:' + (hi - lo).toFixed(1) + '%"></span>' +
        '<span class="rx-meter-dot rx-meter-work" style="left:' + a.toFixed(1) + '%" ' +
          'data-tip-en="' + esc(workTipEn) + '" data-tip-zh="' + esc(workTipZh) + '"></span>' +
        '<span class="rx-meter-dot rx-meter-price" style="left:' + p.toFixed(1) + '%" ' +
          'data-tip-en="' + esc(priceTipEn) + '" data-tip-zh="' + esc(priceTipZh) + '"></span>' +
      "</div>" +
      '<div class="rx-meter-row rx-meter-bot">' + lab("rx-meter-lprice", p, "price", "价格", priceTipEn, priceTipZh) + "</div>" +
    "</div>";
  }
  // What every meter on the page encodes, said ONCE, directly above the first one
  // (Law 4: a constant belongs in the header, not repeated under each card).
  function meterKey() {
    return '<p class="rx-key">' +
      bi("On every bar below, the centre line is normal: the hollow marker is how hard the real work is running, the solid one is how the price is doing against the market. The gap between them is the disagreement.",
         "下方每根标尺的中线代表常态：空心标记是真实活动的强度，实心标记是价格相对大盘的表现。两者之间的间距就是分歧本身。") + "</p>";
  }

  // 14-day state trail — categorical (state over time), the honest encoding.
  function trailRx(strip) {
    if (!strip || !strip.length) return "";
    var dots = strip.slice(-14).map(function (it) {
      return '<i style="background:' + toneCol(plain(it.s).tone) + '"></i>';
    }).join("");
    return '<span class="rx-trail">' + dots + "</span>";
  }

  // ── The one disclosure per card (tier 2 lives here) ───────────────────────
  // Native <details>: keyboard-accessible, no JS wiring, and it collapses the
  // per-source breakdown, the 14-day trail, the full member list and the
  // headlines into a single label instead of nine.
  function cardDetails(f) {
    var o = f.observable || {}, news = f._headlines || [];
    var srcs = rankedSources(o);
    var rows = srcs.map(function (s) {
      var n = srcName(s), m = moveWord(s.z || 0);
      return '<li><span class="rx-sname">' + bi(n.en, n.zh) + "</span>" +
        '<span class="rx-smove" style="--sc:' + toneCol(m.tone) + '">' + bi(m.en, m.zh) + "</span></li>";
    }).join("");
    var members = (o.covered || []);
    var trail = trailRx(f.state_strip);
    var heads = news.slice(0, 3).map(function (h) {
      return '<a class="rx-hl" href="' + esc(/^https?:\/\//i.test(h.url || "") ? h.url : "#") +
        '" target="_blank" rel="noopener noreferrer">' + esc(h.title || "") +
        ' <span class="rx-mut">· ' + esc(h.source || "") + "</span></a>";
    }).join("");
    if (!rows && !members.length && !trail && !heads) return "";
    return '<details class="rx-more"><summary>' + bi("What's behind this", "背后是什么") + "</summary>" +
      '<div class="rx-more-body">' +
        (rows ? '<ul class="rx-slist">' + rows + "</ul>" : "") +
        (trail ? '<div class="rx-more-row"><span class="rx-more-k">' + bi("Last 14 days", "过去14天") + "</span>" + trail + "</div>" : "") +
        (members.length ? '<div class="rx-more-row"><span class="rx-more-k">' + bi("Members", "成分股") + "</span>" +
          '<span class="rx-tks">' + tickerList(members) + "</span></div>" : "") +
        (heads ? '<div class="rx-more-row rx-more-news"><span class="rx-more-k">' + bi("In the news", "相关新闻") + "</span>" +
          "<span>" + heads + "</span></div>" : "") +
      "</div></details>";
  }

  // ── Hero honesty strip (one line; keys off the grader's verdict, never a
  //    hardcoded outcome — the full story lives in #rx-honesty below) ─────────
  function honestyStripEn(ic) {
    var s = ((ic || {}).verdict || {}).status;
    if (s === "leading") return "Modest evidence the calls have led. Watch-only. See the check ↓";
    if (s === "lagging") return "Evidence so far says the calls have lagged. Watch-only. See the check ↓";
    if (s === "null") return "Measured honestly: no proof either way yet. Watch-only. See the check ↓";
    return "Still measuring — the 3-month reads mature from mid-September. See the check ↓";
  }
  function honestyStripZh(ic) {
    var s = ((ic || {}).verdict || {}).status;
    if (s === "leading") return "初步证据显示解读有所领先。仅供观察。见下方核对 ↓";
    if (s === "lagging") return "目前证据显示解读偏滞后。仅供观察。见下方核对 ↓";
    if (s === "null") return "诚实测量：暂无任何方向的证据。仅供观察。见下方核对 ↓";
    return "仍在测量 —— 3 个月期解读自 9 月中旬起到期。见下方核对 ↓";
  }

  // ── Hero ──────────────────────────────────────────────────────────────────
  // The market backdrop, in words rather than the quad label. The internal name
  // ("Reflation · Q2") is a tier-2 receipt on the hover.
  var QUAD = {
    Goldilocks:     { en: "growth up, prices calm",           zh: "增长向上、物价温和" },
    Reflation:      { en: "growth and prices both rising",    zh: "增长与物价同步上行" },
    Stagflation:    { en: "prices rising, growth slowing",    zh: "物价上行、增长放缓" },
    "Growth scare": { en: "growth and prices both cooling",   zh: "增长与物价同步降温" }
  };
  function backdropChip(regime) {
    var q = (regime || {}).quad_name;
    if (!q) return "";
    var w = QUAD[q];
    var liq = regime.liquidity === "expanding" ? { en: "money loosening", zh: "资金面转松" }
      : regime.liquidity === "contracting" ? { en: "money tightening", zh: "资金面收紧" } : null;
    var en = (w ? w.en : q) + (liq ? ", " + liq.en : "");
    var zh = (w ? w.zh : q) + (liq ? "、" + liq.zh : "");
    var tip = q + (regime.quad ? " (" + regime.quad + ")" : "");
    return '<span class="rx-chip rx-chip-regime" data-tip-en="Market backdrop the read sits inside: ' + esc(tip) + '" ' +
      'data-tip-zh="解读所处的市场背景：' + esc(tip) + '">' + bi("Backdrop: " + en, "背景：" + zh) + "</span>";
  }

  function heroHTML(radar, enriched, ic) {
    var cov = radar.coverage || {};
    var regime = (enriched || {}).regime || {};
    var changes = (enriched || {}).changes || {};
    var flags = radar.flags || [];
    var pos = 0, neg = 0, rest = 0;
    flags.forEach(function (f) {
      if (f.state === "POSITIVE_DIVERGENCE") pos++;
      else if (f.state === "NEGATIVE_DIVERGENCE") neg++;
      else rest++;
    });
    var total = flags.length || 1;
    var divs = pos + neg;

    var toneCls = divs === 0 ? "rx-flat" : (pos > neg ? "rx-green" : (neg > pos * 2 ? "rx-amber" : "rx-mixed"));
    var headEn, headZh;
    if (divs === 0) {
      headEn = "Activity and price agree across all " + total + " themes today";
      headZh = "今日全部 " + total + " 个主题的活动与价格一致";
    } else {
      headEn = "Activity and price disagree on " + divs + " of " + total + " themes";
      headZh = "活动与价格在 " + total + " 个主题中的 " + divs + " 个上出现分歧";
    }
    var flipEn = pos + " where the real work is ahead, " + neg + " where price is ahead.";
    var flipZh = pos + " 个真实活动领先，" + neg + " 个价格领先。";

    // Stance (Law 1) — this radar is context-only with a weak track record, so the
    // honest whole-page stance is always "watch, don't chase".
    var stanceEn = pos > 0 ? "Watch — don't chase" : "Stand aside";
    var stanceZh = pos > 0 ? "观察 — 别追" : "旁观";

    function seg(n, col, en, zh) {
      if (!n) return "";
      return '<span class="rx-seg" style="flex:' + n + ';background:' + col + '" ' +
        'data-tip-en="' + n + " " + en + '" data-tip-zh="' + n + " " + zh + '"></span>';
    }
    var bar = '<div class="rx-comp">' +
      seg(pos, "var(--up)", "with the real work ahead", "真实活动领先") +
      seg(neg, "var(--warn)", "with price ahead", "价格领先") +
      seg(rest, "color-mix(in srgb,var(--muted) 30%,transparent)", "moving together", "同步变动") +
      "</div>";
    var legend = '<div class="rx-comp-legend">' +
      '<span><i style="background:var(--up)"></i>' + bi(pos + " real work ahead", pos + " 真实活动领先") + "</span>" +
      '<span><i style="background:var(--warn)"></i>' + bi(neg + " price ahead", neg + " 价格领先") + "</span>" +
      '<span><i style="background:color-mix(in srgb,var(--muted) 45%,transparent)"></i>' +
        bi(rest + " moving together", rest + " 同步变动") + "</span>" +
      "</div>";

    var word = divs === 0 ? bi("A quiet board", "看板平静") :
      (pos > neg ? bi("Mostly the real work running ahead", "多为真实活动领先")
                 : bi("Mostly price running ahead — be careful", "多为价格领先 —— 需谨慎"));

    var nd = (changes.new_divergences || []).length, rs = (changes.resolved || []).length, fl = (changes.flips || []).length;
    var deltaLine;
    if (nd + rs + fl === 0) {
      deltaLine = '<span class="rx-mut">' + bi("Nothing changed since yesterday", "较昨日无变化") + "</span>";
    } else {
      var parts = [];
      if (nd) parts.push('<b style="color:var(--warn)">' + bi(nd + " newly apart", nd + " 个新增分歧") + "</b>");
      if (rs) parts.push('<b style="color:var(--up)">' + bi(rs + " back in line", rs + " 个已回归一致") + "</b>");
      if (fl) parts.push('<b style="color:var(--info)">' + bi(fl + " changed sides", fl + " 个方向反转") + "</b>");
      deltaLine = parts.join(" · ");
    }

    var asof = radar.as_of ? '<span class="rx-asof" data-tip-en="Activity data reaches us about ' +
      (radar.lag_months || 3) + ' months behind the tape, so the read is deliberately slow." ' +
      'data-tip-zh="活动数据比行情滞后约' + (radar.lag_months || 3) + '个月，因此本解读本身就是慢的。">' +
      bi("Reading of " + esc(radar.as_of), "解读日期 " + esc(radar.as_of)) + "</span>" : "";

    return '<section class="rx-hero ' + toneCls + '">' +
      '<div class="rx-eyebrow">🛰️ ' + bi("DIVERGENCE RADAR", "背离雷达") +
        ' <span class="rx-eyebrow-sub">· ' + bi("what companies are doing vs what the market is paying", "企业实际在做什么 vs 市场在付什么价") + "</span></div>" +
      '<h1 class="rx-verdict">' + bi(headEn, headZh) + "</h1>" +
      '<p class="rx-flip">' + bi(flipEn, flipZh) + "</p>" +
      '<div class="rx-stance-row">' +
        '<span class="rx-stance rx-stance-' + (pos > 0 ? "watch" : "aside") + '">' + bi(stanceEn, stanceZh) + "</span>" +
        '<span class="rx-stance-note">' + bi("context, not a buy list", "仅供参考，非买入清单") + "</span>" +
      "</div>" +
      '<div class="rx-hero-row">' +
        '<div class="rx-score">' +
          '<div class="rx-score-top"><span class="rx-score-num">' + divs + '</span>' +
            '<div class="rx-score-lab"><span class="rx-score-cap">' + bi("themes disagree", "个主题出现分歧") + "</span>" +
            '<span class="rx-score-of">' + bi("of " + total + " we watch", "共观察 " + total + " 个") + "</span></div></div>" +
          '<div class="rx-score-word">' + word + "</div>" +
          bar + legend +
        "</div>" +
        '<div class="rx-ctx">' +
          '<div class="rx-ctx-row">' + backdropChip(regime) + asof + "</div>" +
          '<div class="rx-ctx-delta"><span class="rx-ctx-k">' + bi("Since yesterday", "较昨日") + "</span> " + deltaLine + "</div>" +
          '<a class="rx-ctx-honesty" href="#rx-honesty"><span class="rx-ctx-k">' + bi("Has this worked?", "这套解读有效吗？") + "</span> " +
            '<span class="rx-mut">' + bi(honestyStripEn(ic), honestyStripZh(ic)) + "</span></a>" +
        "</div>" +
      "</div>" +
    "</section>";
  }

  // ── Lead card: the single most watch-worthy read ──────────────────────────
  function leadHTML(f) {
    if (!f) return "";
    var p = plain(f.state), o = f.observable || {};
    return '<section class="rx-lead rx-reveal">' +
      '<div class="rx-lead-tag">⭐ ' + bi("Most worth watching today", "今日最值得关注") + "</div>" +
      '<div class="rx-lead-body">' +
        '<div class="rx-lead-main">' +
          '<div class="rx-lead-head">' +
            '<span class="rx-badge rx-badge-up">' + bi(p.short_en, p.short_zh) + "</span>" +
            themeLink(f, "rx-lead-name") +
          "</div>" +
          '<p class="rx-lead-gist">' + cardLine(f) + "</p>" +
          gapMeter(f) +
          ((o.covered || []).length ? '<div class="rx-tks rx-lead-tks">' + tickerList(o.covered, 8) + "</div>" : "") +
          cardDetails(f) +
        "</div>" +
        '<div class="rx-lead-side">' +
          '<span class="rx-stance rx-stance-watch">' + bi("Watch — don't chase", "观察 — 别追") + "</span>" +
          '<span class="rx-lead-side-note">' + bi("The work is running ahead of the price. If price follows, the board below picks it up on its own — there is nothing to front-run.",
            "活动跑在价格前面。若价格随后跟上，下方看板会自动反映 —— 无需抢跑。") + "</span>" +
        "</div>" +
      "</div>" +
    "</section>";
  }

  // ── Lane card ─────────────────────────────────────────────────────────────
  function laneCard(f, i) {
    var p = plain(f.state), o = f.observable || {};
    var col = toneCol(p.tone);
    return '<article class="rx-card rx-reveal" style="--cc:' + col + ';animation-delay:' + Math.min(i * 40, 320) + 'ms">' +
      '<div class="rx-card-top">' +
        '<span class="rx-badge" style="--bc:' + col + '">' + bi(p.short_en, p.short_zh) + "</span>" +
        themeLink(f, "rx-card-name") +
      "</div>" +
      '<p class="rx-card-gist">' + cardLine(f) + "</p>" +
      gapMeter(f) +
      '<div class="rx-card-foot">' +
        '<span class="rx-stance-mini rx-stance-' + (p.tone === "up" ? "watch" : p.tone === "agree" ? "priced" : p.tone === "flat" ? "none" : "aside") + '">' +
          bi(p.stance_en, p.stance_zh) + "</span>" +
        ((o.covered || []).length ? '<span class="rx-tks">' + tickerList(o.covered, 4) + "</span>" : "") +
      "</div>" +
      cardDetails(f) +
    "</article>";
  }

  // ── Board table row ───────────────────────────────────────────────────────
  function boardRow(f) {
    var p = plain(f.state), o = f.observable || {}, c = f.consensus || {};
    var col = toneCol(p.tone);
    var accel = o.accel;
    var accelStr = accel == null ? "—" : accel.toFixed(1) + "×";
    var accelCol = accel == null ? "var(--muted)" : accel >= 1.15 ? "var(--up)" : accel <= 0.9 ? "var(--warn)" : "var(--muted)";
    var rel = c.rel_60d;
    var relCol = rel > 0 ? "var(--up)" : rel < 0 ? "var(--down)" : "var(--muted)";
    return "<tr>" +
      '<td class="rx-t-name">' + themeLink(f, "rx-t-namelink") + "</td>" +
      '<td class="rx-num" style="color:' + accelCol + '">' + accelStr + "</td>" +
      '<td class="rx-num" style="color:' + relCol + '">' + relpct(rel) + "</td>" +
      "<td>" + trailRx(f.state_strip) + "</td>" +
      '<td><span class="rx-badge rx-badge-sm" style="--bc:' + col + '">' + bi(p.short_en, p.short_zh) + "</span></td>" +
      '<td class="rx-t-stance rx-mut">' + bi(p.stance_en, p.stance_zh) + "</td>" +
      "</tr>";
  }

  // ── Per-name row ──────────────────────────────────────────────────────────
  // The engine writes these notes with "basket", percentile ranks and a 0-100
  // score in them; none of that is reader language, so it is rewritten here.
  function plainNote(note) {
    if (!note) return "";
    return String(note)
      .replace(/\balt-data signal is cooling \((\d+)\/100\)/gi, "the real work behind it is slowing")
      .replace(/\balt-data\b/gi, "activity")
      .replace(/\((\d+)(?:st|nd|rd|th) pct(?: of members)?\)/gi, "")
      .replace(/\bbasket\b/gi, "theme")
      .replace(/\bvs SPY\b/gi, "vs the market")
      .replace(/\bthe unpriced member of a moving theme\b/gi, "the part of a moving theme the market has not paid for yet")
      .replace(/\bdistribution risk\b/gi, "a sign the move may be being sold into")
      .replace(/\s{2,}/g, " ")
      .replace(/\s+([,.;:])/g, "$1")
      .trim();
  }
  function nameRowRx(t, i) {
    var p = plain(t.state), col = toneCol(p.tone);
    var rs = t.rs_vs_spy_60d;
    var rsCol = rs > 0 ? "var(--up)" : rs < 0 ? "var(--down)" : "var(--muted)";
    var note = plainNote(t.note);
    var themeCell = t.basket
      ? '<a class="rx-nbasket rx-tlink" href="' + esc(themeHref(t.basket)) + '">' + esc(t.basket_name || t.basket) + "</a>"
      : '<span class="rx-nbasket">' + esc(t.basket_name || "") + "</span>";
    return '<div class="rx-nrow">' +
      tickerLink(t.ticker) +
      '<span class="rx-badge rx-badge-sm" style="--bc:' + col + '">' + bi(p.short_en, p.short_zh) + "</span>" +
      themeCell +
      '<span class="rx-nrs" style="color:' + rsCol + '" data-tip-en="Price vs the market over 60 days" ' +
        'data-tip-zh="60天内价格相对大盘">' + (rs != null ? (rs > 0 ? "+" : "") + rs.toFixed(0) + "%" : "—") + "</span>" +
      "</div>" +
      (note ? '<p class="rx-nnote">' + esc(note) + "</p>" : "");
  }

  // ── Honesty / track-record section (plain words; receipt on tier 2) ─────────
  // The worked/hasn't claim keys ONLY off ic.verdict — the grader's
  // pre-registered evidence gate (enough independent calls + an overlap-robust
  // test on the radar's actual claims). Everything else here is context.
  function honestyHTML(ic, track) {
    ic = ic || {}; track = track || {};
    var nSnap = ic.n_snapshots || 0;
    var open = track.open || 0;
    var verdict = ic.verdict || {};
    var status = verdict.status || "insufficient";
    var bh = ic.by_horizon || {};
    var h21 = bh["21"] || {};
    var ep21 = h21.episodes || {};
    var nEp = ep21.n_matured || 0;
    var epClaims = ep21.claims || {};
    var epBase = ep21.base_rate || {};
    var diag = h21.diagonal || {};
    var baseRate = (ic.base_rate || {}).p_up;

    var headEn, headZh, paraEn, paraZh, tone;
    if (status === "leading") {
      tone = "ok";
      headEn = "Has the radar's read paid off? The evidence says yes — modestly.";
      headZh = "雷达的解读有效吗？证据显示：有 —— 幅度温和。";
      paraEn = "Across the independent calls we can grade, the radar's divergence reads have leaned the right way more often than a coin weighted to this tape. Still context, not a signal — size nothing to it.";
      paraZh = "在可评分的独立解读中，雷达的背离读数方向正确的频率高于随行情加权的基准。但仍属参考而非信号 —— 不应据此下注。";
    } else if (status === "lagging") {
      tone = "warn";
      headEn = "Has the radar's read paid off? The evidence says no, so far.";
      headZh = "雷达的解读有效吗？目前证据显示：没有。";
      paraEn = "Across the independent calls we can grade, the radar's divergence reads have pointed the wrong way more often than this tape's own base rate. That is exactly why every read here is watch-only context, never a buy list.";
      paraZh = "在可评分的独立解读中，雷达的背离读数指错方向的频率高于行情自身的基准。正因如此，这里的每条解读都仅供观察，绝非买入清单。";
    } else if (status === "null") {
      tone = "wait";
      headEn = "Has the radar's read paid off? Measured honestly: no proof either way yet.";
      headZh = "雷达的解读有效吗？诚实测量的答案：暂无任何方向的证据。";
      paraEn = "We grade every call against how this specific tape treated everything we track — and so far the radar's divergence reads are statistically indistinguishable from that base rate. Watch-only context, never a buy list.";
      paraZh = "每条解读都对照同期行情对全部跟踪对象的基准来评分 —— 目前雷达的背离读数与该基准在统计上无法区分。仅供观察，绝非买入清单。";
    } else {
      tone = "wait";
      headEn = "Has the radar's read paid off? Too early to say.";
      headZh = "雷达的解读有效吗？现在下结论还太早。";
      paraEn = "Daily snapshots pile up fast, but they repeat the same open calls — what counts is independent calls, and those need their full windows to elapse. The radar's real test, its ~3-month watch theses, starts maturing from mid-September. Until then: watch-only context, never a buy list.";
      paraZh = "每日快照累积很快，但多为同一判断的重复记录 —— 真正算数的是独立解读，需等完整窗口到期。雷达真正的考验（约 3 个月期的观察论点）自 9 月中旬起陆续到期。在此之前：仅供观察，绝非买入清单。";
    }

    // Base-rate context line — the era's bar, printed so no cohort read can
    // masquerade as skill (or be indicted) against an imaginary 50/50 tape.
    var baseLine = "";
    if (baseRate != null) {
      var pct = Math.round(baseRate * 100);
      baseLine = '<p class="rx-h-base">' + bi(
        "The bar grades are read against: in this stretch only " + pct + "% of everything we track beat the market over the next month. A cohort only shows skill by beating that bar, not 50/50.",
        "评分对照的基准：本时段内，我们跟踪的对象中仅 " + pct + "% 在随后一个月跑赢大盘。只有超过这条线才算有效，而非超过五五开。") + "</p>";
    }

    // Claims vs already-priced split — the cohorts are different products.
    var splitLine = "";
    if (nEp >= 30 && epClaims.dir_accuracy != null) {
      var ca = Math.round(epClaims.dir_accuracy * 100);
      var cb = epClaims.base_dart != null ? Math.round(epClaims.base_dart * 100) : null;
      var da = diag.dir_accuracy != null ? Math.round(diag.dir_accuracy * 100) : null;
      splitLine = '<p class="rx-h-split">' + bi(
        "Split honestly: the radar's actual calls — the divergence reads — were right " + ca + "% of the time" + (cb != null ? " against a " + cb + "% bar" : "") + ". Panels marked “already priced” are context, not calls" + (da != null ? " — and that cohort kept only " + da + "% direction, which is why it now ranks near the bottom of the board, not the top" : "") + ".",
        "如实拆分：雷达真正的判断 —— 背离读数 —— 方向正确率 " + ca + "%" + (cb != null ? "（基准 " + cb + "%）" : "") + "。标注“已反映在价格中”的面板是背景参考而非判断" + (da != null ? " —— 该组仅 " + da + "% 方向正确，因此现已排在榜单底部而非顶部" : "") + "。") + "</p>";
    }

    function tile(v, en, zh) {
      return '<div class="rx-tile"><div class="rx-tile-v">' + esc(v) + '</div><div class="rx-tile-l">' + bi(en, zh) + "</div></div>";
    }

    // Tier-2 receipt: the technical numbers, signed AND legacy, with validity.
    var icAll = ic.ic_all, icSigned = ic.ic_all_signed;
    var hacC = (h21.ic_daily_hac_claims || {});
    var eras = (ic.era_breaks || []);
    var receipt = "Independent calls = contiguous flag episodes, graded at entry (n=" + nEp.toLocaleString() +
      " matured at 21d; " + (ic.n_matured || 0).toLocaleString() + " raw daily rows). " +
      "Signed rank-correlation (score × call direction vs forward return net of SPY): " +
      (icSigned == null ? "—" : icSigned.toFixed(2)) +
      "; unsigned legacy figure: " + (icAll == null ? "—" : icAll.toFixed(2)) +
      " (unsigned mixes bullish and bearish calls — kept for continuity only). " +
      "Overlap-robust test on the divergence calls: " +
      (hacC.t_hac != null ? "t=" + hacC.t_hac.toFixed(2) + " over " + (hacC.n || 0) + " daily cross-sections"
                          : "not yet valid (needs ≥ horizon-length run of daily cross-sections)") +
      ". Verdict gate: ≥" + (((verdict.gates || {}).min_claim_episodes) || 60) + " matured claim episodes AND |t| ≥ " +
      (((verdict.gates || {}).t_sig) || 2) + " on a non-degenerate window — status: " + status + ". " +
      "The seeded ~3-month theses (" + open + " open) grade separately at their own deadlines. " +
      (eras.length ? "Scoring construction changed " + eras[eras.length - 1].date + " (era " + eras[eras.length - 1].era + ") — cross-era pooling carries both constructions. " : "") +
      "Schema radar_ic.v2.";
    var receiptZh = "独立解读＝连续的标记片段，按入场日评分（21 日窗口已到期 n=" + nEp.toLocaleString() +
      "；每日原始行 " + (ic.n_matured || 0).toLocaleString() + "）。" +
      "带方向的秩相关（分数×判断方向 对 相对 SPY 的前瞻收益）：" + (icSigned == null ? "—" : icSigned.toFixed(2)) +
      "；旧口径（不带方向）：" + (icAll == null ? "—" : icAll.toFixed(2)) +
      "（不带方向会混淆多空判断 —— 仅为连续性保留）。" +
      "对背离判断的抗重叠检验：" +
      (hacC.t_hac != null ? "t=" + hacC.t_hac.toFixed(2) + "，基于 " + (hacC.n || 0) + " 个每日横截面"
                          : "尚未有效（需累积不少于窗口长度的每日横截面）") +
      "。判定门槛：已到期判断片段 ≥" + (((verdict.gates || {}).min_claim_episodes) || 60) + " 且非退化窗口上 |t| ≥ " +
      (((verdict.gates || {}).t_sig) || 2) + " —— 当前状态：" + status + "。" +
      "约 3 个月期的观察论点（" + open + " 条进行中）按各自截止日另行评分。" +
      (eras.length ? "评分构造已于 " + eras[eras.length - 1].date + " 调整（第 " + eras[eras.length - 1].era + " 代）—— 跨代合并统计含两种构造。" : "") +
      "架构 radar_ic.v2。";

    return '<section class="rx-honesty rx-honesty-' + tone + '" id="rx-honesty">' +
      '<div class="rx-h-head">' +
        '<span class="rx-h-eyebrow">' + bi("THE HONESTY CHECK", "诚实核对") + "</span>" +
        '<h2 class="rx-h-title">' + bi(headEn, headZh) + "</h2>" +
      "</div>" +
      '<p class="rx-h-para">' + bi(paraEn, paraZh) + "</p>" +
      baseLine +
      splitLine +
      '<div class="rx-tiles">' +
        tile(nSnap.toLocaleString(), "Daily readings recorded", "已记录每日读数") +
        tile(nEp.toLocaleString(), "Independent calls graded", "已评分独立解读") +
        tile(open.toLocaleString(), "3-month theses open", "3个月论点进行中") +
      "</div>" +
      '<details class="rx-receipt"><summary>' + bi("Show the technical receipt", "查看技术明细") + "</summary>" +
        "<p>" + bi(receipt, receiptZh) + "</p></details>" +
    "</section>";
  }

  // ── One merged footnote (Law 4: merge, never stack) ───────────────────────
  // The engine's own caveats name the vendor behind a feed and describe the
  // weighting in engine terms, so the page states the same three facts — what the
  // sources are, that coverage is uneven and never faked, and that the data is
  // lagged and context-only — in words, and keeps the engine's wording verbatim
  // one click away.
  function footNote(radar) {
    var lag = radar.lag_months || 3;
    var en = "Where this comes from: federal contracts and grants, congressional trading, lobbying spend, " +
      "company filings, new regulations and news coverage. Coverage differs from theme to theme — where a " +
      "source is missing it simply counts for less, and is never filled in. All of it reaches us about " +
      lag + " months behind the market, so this page is deliberately slow. Context only, never a trade signal.";
    var zh = "数据来源：联邦合同与补助、国会议员交易、游说支出、公司公告、新规发布与新闻报道。各主题的覆盖程度不同 —— " +
      "缺失的来源只会被降低权重，绝不会被虚构填充。所有数据都比市场行情滞后约 " + lag +
      " 个月，因此本页本就是慢的。仅供参考，绝非交易信号。";
    var raw = (radar.caveats || []).filter(Boolean);
    var rawZh = (radar.caveats_zh || []).filter(Boolean);
    var detail = raw.length
      ? '<details class="rx-foot-more"><summary>' + bi("The engine's own wording", "引擎原文") + "</summary>" +
        raw.map(function (c, i) { return "<p>" + bi(c, rawZh[i] || c) + "</p>"; }).join("") + "</details>"
      : "";
    return '<div class="rx-foot"><p>' + bi(en, zh) + "</p>" + detail + "</div>";
  }

  // ── The AI read ───────────────────────────────────────────────────────────
  // English terms the model reaches for that a reader would not.
  var AI_TERMS_EN = [
    [/\bprice relative strength\b/gi, "price against the market"],
    [/\brelative strength vs\.?\s*(?:SPY|the market)\b/gi, "performance against the market"],
    [/\brel(?:ative)? strength\b/gi, "performance against the market"],
    [/\bPOSITIVE_DIVERGENCE\b/g, "activity ahead of price"],
    [/\bNEGATIVE_DIVERGENCE\b/g, "price ahead of activity"],
    [/\bCONFIRMED_UP\b/g, "activity and price both rising"],
    [/\bCONFIRMED_DOWN\b/g, "activity and price both cooling"],
    [/\bBROKEN_LAGGARD\b/g, "falling behind its theme"],
    [/\bQUIET\b/g, "in line"],
    [/\b(?:radar state is|state is)\s*['"]?(\w+)['"]?\s*(?:lifecycle|stage)\b/gi, "this theme is $1"],
    [/\blifecycle\b/gi, "stage"],
    [/\ban ENTER\b/g, "a buy"], [/\bENTER\b/g, "buy"],
    [/\ba MONITOR\b/g, "a watch"], [/\bMONITOR\b/g, "watch"],
    [/\bAVOID\b/g, "avoid"],
    [/\b8-?K (?:material )?events?\b/gi, "company filings"],
    [/\b8-?K\b/gi, "company filings"],
    [/\bGov(?:ernment)? contracts?\b/g, "government contracts"],
    [/\bLobbying ramp\b/gi, "lobbying spend"],
    [/\bCongress(?:ional)? net-buys?\b/gi, "congress buying"],
    [/\bnet-buys?\b/gi, "buying"],
    [/[(（]\s*fused accel(?:eration)?[^)）]*[)）]/gi, ""],
    [/\bfused accel(?:eration)?\b/gi, "combined activity pickup"],
    [/\bbreadth of sources\b/gi, "range of sources"],
    [/\balt-data\b/gi, "activity data"],
    [/\bevidence pack\b/gi, "evidence"],
    [/\breal-activity\b/gi, "real activity"],
    [/\bz-scores?\b/gi, "reading"],
    [/\bsub-zero\b/gi, "negative"],
    [/\bSPY\b/g, "the market"]
  ];
  // The Chinese note needs its OWN list: running the English one over it leaves
  // half-translated hybrids ("company filings 重大事项"), and its punctuation is
  // full-width, which the ASCII bracket rules never touch.
  var AI_TERMS_ZH = [
    [/正向?背离|正背離/g, "背离（活动领先）"],
    [/负背离|負背離/g, "背离（价格领先）"],
    [/缺乏宽度|缺乏廣度|缺乏寬度/g, "覆盖面不足"],
    [/生命周期|生命週期/g, "阶段"],
    [/8-?K\s*(?:重要事件|重大事项|重大事項)?/g, "公司公告"],
    [/(?:Gov(?:ernment)?\s*)?[Cc]ontracts?|政府合同/g, "政府合同"],
    [/Congress(?:ional)?\s*(?:net-?buys?)?|国会净买入|國會淨買入/g, "国会议员交易"],
    [/Lobbying(?:\s*ramp)?|游说活动|遊說活動/g, "游说支出"],
    [/融合加速度?|融合加速/g, "综合活动强度"],
    [/另类数据|另類數據/g, "活动数据"],
    [/证据包|證據包/g, "证据"],
    [/相对强度|相對強度/g, "相对大盘表现"],
    [/z-?值|z\s*分数|Z\s*分數/g, "读数"],
    [/SPY/g, "大盘"],
    [/ENTER/g, "买入"], [/MONITOR/g, "观察"], [/AVOID/g, "回避"]
  ];

  // The model writes for an analyst: citation tags ([P3]), readings, state enums
  // and stage words. `rationale_plain` (engine/narrative_brain.py) is the durable
  // fix and wins whenever the night that wrote the file produced it; this is the
  // stopgap that keeps an older payload readable. The untouched original always
  // stays one click away as the technical note.
  function plainifyAI(text, zh) {
    if (!text) return "";
    var s = String(text);
    (zh ? AI_TERMS_ZH : AI_TERMS_EN).forEach(function (r) { s = s.replace(r[0], r[1]); });
    s = s
      // a bracket or bracketed clause that exists only to carry evidence, in both
      // ASCII and full-width punctuation
      .replace(/[(（][^()（）]*(?:\[P\d+[^\]]*\]|z\s*[=＝]?\s*[-+0-9.]|dir\s*[=＝])[^()（）]*[)）]/g, "")
      .replace(/\[\s*P\d+[^\]]*\]/g, "")
      .replace(/\[\s*[-+]?[0-9.]+\s*\]/g, "")
      .replace(/\bz\s*[=＝]?\s*[-+]?[0-9]*\.?[0-9]+/g, "")
      .replace(/\bdir\s*[=＝]\s*[-+]?[0-9]+/g, "")
      // machine precision reads as machine talk — two places is a number a person
      // would say out loud
      .replace(/([-+]?\d+\.\d{3,})/g, function (m) { return parseFloat(m).toFixed(2); })
      // whatever the removals left behind
      .replace(/[(（]\s*[,，;；、]*\s*[)）]/g, "")
      .replace(/[(（]\s*[,，]\s*/g, "(").replace(/\s*[,，]\s*[)）]/g, ")")
      .replace(/\s{2,}/g, " ");
    if (zh) {
      s = s.replace(/[，、]\s*(?=[，。；、])/g, "")
           .replace(/\s+(?=[，。；：、！？）])/g, "")
           .replace(/^[\s，。、；]+/, "");
    } else {
      // a preposition orphaned by a removed figure ("negative at, meaning…")
      s = s.replace(/\s+\b(?:at|of|to|by|from|near|around|only)\b\s*(?=[,.;:])/gi, "")
           .replace(/\s+([,.;:!?])/g, "$1")
           .replace(/,\s*,/g, ",")
           .replace(/\s{2,}/g, " ")
           // a substitution can land a lower-case word at the head of a sentence
           .replace(/(^|[.!?]\s+)([a-z])/g, function (m, pre, ch) { return pre + ch.toUpperCase(); });
    }
    return s.trim();
  }
  // Anything that still smells of the machine after laundering does NOT reach the
  // glance tier — the deterministic sentence below takes over and the model's own
  // words stay available, unedited, in the technical note.
  function aiResidue(s) {
    return !s || s.length < 24 ||
      /\[P\d|z\s*[=＝]|dir\s*[=＝]|_[A-Z]{2,}|[(（]\s*[)）]|\b8-?K\b/.test(s);
  }
  function verdictLine(verdict, zh) {
    if (verdict === "ENTER") {
      return zh ? "AI 认为此处的真实活动领先价格，且可能延续。详见下方完整说明。"
                : "The AI reads the work here as running ahead of the price, and thinks it may hold. Its reasoning is in the full note below.";
    }
    if (verdict === "AVOID") {
      return zh ? "AI 认为此处价格已跑在其背后的真实活动前面。详见下方完整说明。"
                : "The AI reads the move here as having run ahead of the work behind it. Its reasoning is in the full note below.";
    }
    return zh ? "AI 认为现在下结论还太早 —— 值得观察，但不值得追。详见下方完整说明。"
              : "The AI reads this as too early to call — worth watching, not worth chasing. Its reasoning is in the full note below.";
  }
  // Hand-rolled rather than a lookbehind split: a lookbehind regex LITERAL is a
  // parse-time SyntaxError on Safari below 16.4, which would blank the whole page
  // rather than degrade one paragraph.
  function firstSentences(s, n, zh) {
    if (!s) return "";
    var enders = zh ? "。！？" : ".!?";
    var out = "", kept = 0;
    for (var i = 0; i < s.length; i++) {
      out += s.charAt(i);
      if (enders.indexOf(s.charAt(i)) >= 0) {
        // a decimal point or an initial is not the end of a sentence
        var next = s.charAt(i + 1);
        if (!zh && next && next !== " " && next !== "\n") continue;
        if (++kept >= n) break;
      }
    }
    return out.trim();
  }
  function brainRx(b, flagIndex) {
    if (!b) return "";
    var has = b.assessments && b.assessments.length && !b.degraded_reason;
    if (!has) {
      return '<section class="rx-brain rx-brain-off">' +
        '<div class="rx-brain-head">🧠 ' + bi("The AI read", "AI 解读") + "</div>" +
        '<p class="rx-mut">' + bi("The AI read is unavailable right now — the rest of this page stands on its own.",
          "AI 解读暂不可用 —— 本页其余内容可独立使用。") + "</p></section>";
    }
    var V = {
      ENTER:   { en: "Worth a look", zh: "值得关注", c: "var(--up)" },
      MONITOR: { en: "Just watch",   zh: "仅作观察", c: "var(--muted)" },
      AVOID:   { en: "Steer clear",  zh: "回避",     c: "var(--warn)" }
    };
    var rows = b.assessments.map(function (a) {
      var v = V[a.verdict] || V.MONITOR;
      var flag = flagIndex[a.basket] || { basket: a.basket, name: a.name, name_zh: a.name_zh };
      var leadEn = firstSentences(a.rationale_plain || plainifyAI(a.rationale, false), 2, false);
      var leadZh = firstSentences(a.rationale_plain_zh || plainifyAI(a.rationale_zh || a.rationale, true), 2, true);
      if (aiResidue(leadEn)) leadEn = verdictLine(a.verdict, false);
      if (aiResidue(leadZh)) leadZh = verdictLine(a.verdict, true);
      var full = (a.rationale || "").trim(), fullZh = (a.rationale_zh || a.rationale || "").trim();
      return '<div class="rx-brain-row">' +
        '<div class="rx-brain-top">' +
          '<span class="rx-brain-badge" style="--bc:' + v.c + '">' + bi(v.en, v.zh) + "</span>" +
          themeLink(flag, "rx-brain-theme") +
        "</div>" +
        '<p class="rx-brain-why">' + bi(leadEn, leadZh) + "</p>" +
        (full ? '<details class="rx-brain-full"><summary>' + bi("The full technical note", "完整技术说明") +
          "</summary><p>" + bi(full, fullZh) + "</p>" +
          (a.dissent ? "<p><b>" + bi("The case against", "反方观点") + ":</b> " + bi(a.dissent, a.dissent) + "</p>" : "") +
          "</details>" : "") +
      "</div>";
    }).join("");
    var rot = (b.rotation && b.rotation.summary)
      ? '<div class="rx-brain-rot">🔁 ' + bi(b.rotation.summary, b.rotation.summary_zh || b.rotation.summary) + "</div>" : "";
    return '<section class="rx-brain">' +
      '<div class="rx-brain-head">🧠 ' + bi("The AI read", "AI 解读") +
        ' <span class="rx-mut">· ' + bi("odds, not a forecast — marked against the tape later", "是概率而非预测 —— 事后对照行情评分") + "</span></div>" +
      rot + rows +
      '<p class="rx-cav">' + bi(b.disclaimer || "", b.disclaimer || "") + "</p></section>";
  }

  // ── CSS for the full page (rx- prefix, id-guarded, injected once) ─────────
  function injectFullStyles() {
    if (document.getElementById("rx-styles")) return;
    var el = document.createElement("style");
    el.id = "rx-styles";
    el.textContent = [
      "html[data-lang=zh] .l-en{display:none}html[data-lang=en] .l-zh{display:none}",
      ".rx-wrap{max-width:1180px;margin:0 auto;padding:8px 16px 64px}",
      ".rx-mut{color:var(--muted)}",
      /* reveal animation (once, cheap) */
      "@keyframes rxReveal{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}",
      ".rx-reveal{animation:rxReveal .5s cubic-bezier(.2,.7,.3,1) both}",
      /* Every theme name is a door to that theme's page, so it carries a quiet
         dotted rule at rest — visible enough to invite the click without turning
         the page blue — and commits to a solid link underline on hover. */
      // `color:var(--text)`, never `color:inherit`: theme.js flips data-theme at
      // runtime and Chromium does not re-resolve an inherited colour on that
      // subtree, so an inherit here keeps the old theme's ink until a reload.
      ".rx-tlink{color:var(--text);text-decoration:none;border-bottom:1px dotted color-mix(in srgb,var(--muted) 60%,transparent);" +
        "transition:border-color .15s ease,color .15s ease}",
      ".rx-tlink:hover{color:var(--link);border-bottom:1px solid var(--link)}",
      ".rx-tlink:focus-visible,.rx-tk:focus-visible,.rx-more summary:focus-visible{outline:2px solid var(--link);outline-offset:2px;border-radius:3px}",
      ".rx-tk{font-family:var(--font-mono);font-size:11px;font-weight:700;color:var(--muted);text-decoration:none;padding:1px 2px;border-radius:3px}",
      ".rx-tk:hover{color:var(--link);background:color-mix(in srgb,var(--link) 12%,transparent)}",
      ".rx-tk-sep{color:var(--line);margin:0 1px;font-size:10px}",
      ".rx-tk-more{font-size:10.5px;color:var(--muted);margin-left:5px;opacity:.8}",
      ".rx-tks{display:inline-flex;flex-wrap:wrap;align-items:center;gap:1px;min-width:0}",
      /* ── HERO ── */
      ".rx-hero{position:relative;padding:26px 4px 20px;overflow:hidden}",
      ".rx-hero::before{content:'';position:absolute;inset:-40% -20% auto -20%;height:340px;z-index:0;pointer-events:none;" +
        "background:radial-gradient(60% 80% at 22% 0%,color-mix(in srgb, var(--hc,var(--warn)) 20%,transparent),transparent 70%);opacity:.5;filter:blur(6px)}",
      ".rx-hero>*{position:relative;z-index:1}",
      ".rx-green{--hc:var(--up)}.rx-amber{--hc:var(--warn)}.rx-mixed{--hc:var(--info)}.rx-flat{--hc:var(--muted)}",
      ".rx-eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--muted);margin-bottom:10px}",
      ".rx-eyebrow-sub{font-weight:600;letter-spacing:.02em;opacity:.8}",
      ".rx-verdict{font-size:clamp(23px,3.6vw,34px);font-weight:800;line-height:1.14;letter-spacing:-.02em;margin:0 0 6px;" +
        "-webkit-text-fill-color:transparent;background-clip:text;-webkit-background-clip:text;" +
        "background-image:linear-gradient(115deg,var(--text) 0%,color-mix(in srgb, var(--hc,var(--warn)) 70%,var(--text)) 62%,var(--hc,var(--warn)) 100%)}",
      ".rx-flip{font-size:13.5px;color:var(--muted);margin:0 0 14px;max-width:760px;line-height:1.5}",
      ".rx-stance-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:18px}",
      ".rx-stance{font-size:13px;font-weight:800;padding:5px 14px;border-radius:999px;border:1px solid;letter-spacing:.01em}",
      ".rx-stance-watch{color:var(--up);background:color-mix(in srgb,var(--up) 13%,transparent);border-color:color-mix(in srgb,var(--up) 34%,transparent)}",
      ".rx-stance-aside{color:var(--warn);background:color-mix(in srgb,var(--warn) 13%,transparent);border-color:color-mix(in srgb,var(--warn) 34%,transparent)}",
      ".rx-stance-note{font-size:12px;color:var(--muted)}",
      ".rx-hero-row{display:flex;gap:16px;flex-wrap:wrap;align-items:stretch}",
      /* score block (glass, glow keyed to hero color) */
      ".rx-score{flex:0 0 auto;min-width:290px;max-width:340px;padding:16px 18px 14px;border-radius:16px;" +
        "background:linear-gradient(150deg,var(--panel) 0%,color-mix(in srgb, var(--hc,var(--warn)) 6%,var(--panel)) 100%);" +
        "border:1px solid color-mix(in srgb, var(--hc,var(--warn)) 22%,var(--line));" +
        "box-shadow:0 0 44px -14px color-mix(in srgb, var(--hc,var(--warn)) 30%,transparent)}",
      ".rx-score-top{display:flex;align-items:center;gap:12px}",
      ".rx-score-num{font-size:58px;font-weight:900;line-height:.9;letter-spacing:-.04em;color:var(--hc,var(--warn));" +
        "text-shadow:0 0 44px color-mix(in srgb, var(--hc,var(--warn)) 40%,transparent);font-variant-numeric:tabular-nums}",
      ".rx-score-lab{display:flex;flex-direction:column;gap:2px}",
      ".rx-score-cap{font-size:12px;font-weight:800;color:var(--text);text-transform:uppercase;letter-spacing:.05em}",
      ".rx-score-of{font-size:11px;color:var(--muted)}",
      ".rx-score-word{font-size:13px;font-weight:700;color:var(--hc,var(--warn));margin:8px 0 10px}",
      ".rx-comp{display:flex;height:9px;border-radius:5px;overflow:hidden;gap:2px;background:transparent}",
      ".rx-seg{display:block;border-radius:3px;min-width:3px;transition:flex .6s cubic-bezier(.4,0,.2,1)}",
      ".rx-comp-legend{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:9px}",
      ".rx-comp-legend span{font-size:10.5px;color:var(--muted);display:inline-flex;align-items:center;gap:4px}",
      ".rx-comp-legend i,.rx-trail i{width:8px;height:8px;border-radius:2px;display:inline-block;flex-shrink:0}",
      /* context card */
      ".rx-ctx{flex:1;min-width:250px;display:flex;flex-direction:column;gap:10px;padding:14px 16px;" +
        "background:var(--panel);border:1px solid var(--line);border-radius:12px;font-size:12.5px;line-height:1.5}",
      ".rx-ctx-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}",
      ".rx-chip{font-size:11px;font-weight:600;padding:3px 10px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}",
      ".rx-chip-regime{color:var(--info);background:color-mix(in srgb,var(--info) 10%,transparent);border-color:color-mix(in srgb,var(--info) 28%,transparent)}",
      ".rx-asof{font-size:11px;color:var(--muted)}",
      ".rx-ctx-k{font-weight:700;color:var(--text)}",
      ".rx-ctx-delta{font-size:12px}",
      ".rx-ctx-honesty{display:block;font-size:12px;text-decoration:none;padding:8px 10px;border-radius:8px;" +
        "background:color-mix(in srgb,var(--warn) 8%,transparent);border:1px solid color-mix(in srgb,var(--warn) 22%,transparent)}",
      ".rx-ctx-honesty:hover{background:color-mix(in srgb,var(--warn) 13%,transparent)}",
      /* section scaffolding */
      ".rx-sec{margin-top:22px}",
      ".rx-sec-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:4px}",
      ".rx-sec-title{font-size:16px;font-weight:800;letter-spacing:-.01em;margin:0}",
      ".rx-sec-cnt{font-size:12px;color:var(--muted);font-weight:600}",
      ".rx-sec-sub{font-size:12.5px;color:var(--muted);margin:0 0 10px;max-width:760px;line-height:1.5}",
      /* ── the gap meter — this page's signature ──
         A 3px rail so the two 11px markers always dominate it, a centre tick for
         "unchanged / level with the market", and a tinted band spanning the two.
         The band IS the read: its width is the disagreement, its colour is which
         side is in front. Each marker carries its own label on its own row, so
         they cannot collide however far apart they sit. */
      ".rx-meter{margin:2px 0 12px;max-width:440px}",
      ".rx-meter-row{position:relative;height:13px}",
      ".rx-meter-lab{position:absolute;top:0;transform:translateX(-50%);font-size:9.5px;font-weight:700;" +
        "letter-spacing:.03em;white-space:nowrap;cursor:help}",
      ".rx-meter-lab-l{transform:translateX(-5px)}",
      ".rx-meter-lab-r{transform:translateX(calc(-100% + 5px))}",
      ".rx-meter-lwork,.rx-meter-lprice{color:var(--text);opacity:.82}",
      ".rx-meter-rail{position:relative;height:3px;border-radius:999px;background:color-mix(in srgb,var(--muted) 22%,transparent);margin:1px 0}",
      ".rx-meter-zero{position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:color-mix(in srgb,var(--muted) 60%,transparent)}",
      ".rx-meter-gap{position:absolute;top:0;bottom:0;border-radius:999px;background:var(--mc,var(--muted));opacity:.55;min-width:2px}",
      ".rx-meter-dot{position:absolute;top:50%;width:11px;height:11px;border-radius:50%;transform:translate(-50%,-50%);cursor:help;z-index:1}",
      ".rx-meter-work{background:var(--panel2);border:2.5px solid var(--text)}",
      ".rx-meter-price{background:var(--mc,var(--muted));border:2.5px solid var(--panel2)}",
      ".rx-key{font-size:11.5px;color:var(--muted);line-height:1.5;margin:0 0 12px;max-width:680px}",
      /* lead card */
      ".rx-lead{margin-top:20px;border-radius:16px;overflow:hidden;border:1px solid color-mix(in srgb,var(--up) 26%,var(--line));" +
        "background:linear-gradient(150deg,var(--panel) 0%,color-mix(in srgb,var(--up) 6%,var(--panel)) 100%);" +
        "box-shadow:0 0 40px -18px color-mix(in srgb,var(--up) 34%,transparent)}",
      ".rx-lead-tag{font-size:11px;font-weight:800;letter-spacing:.08em;color:var(--up);padding:12px 18px 0}",
      ".rx-lead-body{display:flex;gap:18px;padding:8px 18px 18px;flex-wrap:wrap}",
      ".rx-lead-main{flex:1;min-width:280px}",
      ".rx-lead-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}",
      ".rx-lead-name{font-size:21px;font-weight:800;margin:0;letter-spacing:-.01em;display:inline-block}",
      ".rx-lead-gist{font-size:14px;line-height:1.55;margin:0 0 12px;color:var(--text)}",
      ".rx-lead-tks{margin:2px 0 4px;gap:2px}",
      ".rx-lead-side{flex:0 0 230px;max-width:260px;display:flex;flex-direction:column;gap:9px;align-items:flex-start;" +
        "padding:14px;border-radius:12px;background:color-mix(in srgb,var(--up) 5%,var(--panel));border:1px solid color-mix(in srgb,var(--up) 16%,var(--line))}",
      ".rx-lead-side-note{font-size:11.5px;color:var(--muted);line-height:1.5}",
      /* cards */
      ".rx-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}",
      ".rx-card{position:relative;display:flex;flex-direction:column;border:1px solid var(--line);border-top:2px solid var(--cc,var(--line));border-radius:12px;" +
        "padding:13px 15px;background:var(--panel2);transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}",
      "@media(hover:hover){.rx-card:hover{transform:translateY(-3px);border-color:color-mix(in srgb, var(--cc,var(--line)) 40%,var(--line));" +
        "box-shadow:0 12px 30px -18px color-mix(in srgb, var(--cc,var(--line)) 60%,transparent)}}",
      ".rx-card-top{display:flex;align-items:center;gap:8px;margin-bottom:7px;flex-wrap:wrap}",
      ".rx-card-name{font-size:14.5px;font-weight:700;margin:0;letter-spacing:-.01em;display:inline-block}",
      ".rx-card-gist{font-size:12.5px;color:var(--muted);line-height:1.5;margin:0 0 10px}",
      ".rx-badge{font-size:10.5px;font-weight:700;padding:2px 9px;border-radius:999px;white-space:nowrap;" +
        "color:color-mix(in srgb, var(--bc,var(--muted)) 72%,var(--text));" +
        "background:color-mix(in srgb, var(--bc,var(--muted)) 13%,transparent);border:1px solid color-mix(in srgb, var(--bc,var(--muted)) 32%,transparent)}",
      ".rx-badge-up{--bc:var(--up)}",
      ".rx-badge-sm{font-size:10px;padding:1px 7px}",
      ".rx-card-foot{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:auto;padding-top:4px}",
      ".rx-stance-mini{font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;white-space:nowrap}",
      ".rx-stance-mini{color:color-mix(in srgb,var(--sm,var(--muted)) 72%,var(--text));background:color-mix(in srgb,var(--sm,var(--muted)) 12%,transparent)}",
      ".rx-stance-mini.rx-stance-watch{--sm:var(--up)}",
      ".rx-stance-mini.rx-stance-aside{--sm:var(--warn)}",
      ".rx-stance-mini.rx-stance-priced{--sm:var(--info)}",
      ".rx-stance-mini.rx-stance-none{--sm:var(--muted)}",
      ".rx-trail{display:inline-flex;gap:2px;align-items:center}",
      /* the one disclosure per card */
      ".rx-more{margin-top:9px;border-top:1px solid var(--line);padding-top:7px}",
      ".rx-more summary{font-size:11px;font-weight:600;color:var(--link);cursor:pointer;list-style:none;display:inline-flex;align-items:center;gap:4px}",
      ".rx-more summary::-webkit-details-marker{display:none}",
      ".rx-more summary::before{content:'+';font-weight:700;opacity:.7}",
      ".rx-more[open] summary::before{content:'\\2212'}",
      ".rx-more-body{margin-top:8px;display:flex;flex-direction:column;gap:7px}",
      ".rx-slist{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px}",
      ".rx-slist li{display:flex;align-items:baseline;justify-content:space-between;gap:10px;font-size:11.5px}",
      ".rx-sname{color:var(--text)}",
      ".rx-smove{color:var(--sc,var(--muted));font-weight:600;font-size:11px;white-space:nowrap}",
      ".rx-more-row{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;font-size:11.5px}",
      ".rx-more-k{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;font-weight:700;flex-shrink:0}",
      ".rx-more-news{flex-direction:column;align-items:flex-start;gap:4px}",
      ".rx-hl{display:block;color:var(--link);text-decoration:none;font-size:11.5px;line-height:1.5;margin-bottom:3px}",
      ".rx-hl:hover{text-decoration:underline}",
      ".rx-showmore{display:block;width:100%;text-align:center;margin-top:12px;padding:9px;font-size:12px;font-weight:600;" +
        "color:var(--link);background:var(--gbtn-bg,transparent);border:1px solid var(--line);border-radius:9px;cursor:pointer}",
      ".rx-showmore:hover{border-color:var(--muted)}",
      ".rx-calm{font-size:13px;color:var(--muted);background:var(--panel2);border:1px dashed var(--line);border-radius:11px;padding:16px 18px;text-align:center}",
      /* board (tabs + table) */
      ".rx-board{margin-top:26px;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}",
      ".rx-tabs{display:flex;border-bottom:1px solid var(--line);background:var(--panel2);overflow-x:auto}",
      ".rx-tab{padding:11px 18px;font-size:13px;font-weight:700;cursor:pointer;border:none;background:none;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap}",
      ".rx-tab:hover{color:var(--text)}",
      ".rx-tab.rx-on{color:var(--text);border-bottom-color:var(--hc,var(--info))}",
      ".rx-pane{display:none;padding:14px 16px}.rx-pane.rx-on{display:block}",
      ".rx-filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}",
      ".rx-fchip{padding:4px 12px;border-radius:999px;font-size:11.5px;font-weight:600;cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--muted)}",
      ".rx-fchip:hover{color:var(--text)}",
      ".rx-fchip.rx-on{background:var(--panel2);color:var(--text);border-color:var(--muted)}",
      ".rx-tbl{width:100%;border-collapse:collapse;font-size:12.5px}",
      ".rx-tbl th{text-align:left;padding:7px 10px;color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;" +
        "border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}",
      ".rx-tbl th:hover{color:var(--text)}",
      ".rx-tbl th .rx-so{font-size:9px;opacity:.4;margin-left:2px}",
      ".rx-tbl th.rx-sorted .rx-so{opacity:1}",
      ".rx-tbl td{padding:7px 10px;border-bottom:1px solid color-mix(in srgb,var(--line) 55%,transparent)}",
      ".rx-tbl tr:hover td{background:color-mix(in srgb,var(--panel2) 55%,transparent)}",
      ".rx-t-name{font-weight:600}",
      ".rx-num{font-family:var(--font-mono);font-size:11.5px;text-align:right}",
      ".rx-tbl th:nth-child(2),.rx-tbl th:nth-child(3){text-align:right}",
      ".rx-t-stance{font-size:11px}",
      /* per-name */
      ".rx-nctrl{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}",
      ".rx-nq,.rx-nsel{padding:6px 11px;border-radius:8px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font-size:12.5px;font-family:inherit;outline:none}",
      ".rx-nq{width:190px}.rx-nq:focus,.rx-nsel:focus{border-color:var(--link)}",
      ".rx-nrow{display:flex;align-items:center;gap:9px;padding:7px 9px;border-radius:7px;border:1px solid transparent;font-size:12.5px}",
      ".rx-nrow:hover{background:var(--panel2);border-color:var(--line)}",
      ".rx-nrow .rx-tk{font-size:12.5px;min-width:52px}",
      ".rx-nbasket{flex:1;min-width:0;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".rx-nrs{font-family:var(--font-mono);font-weight:700;min-width:44px;text-align:right;cursor:help}",
      ".rx-nnote{font-size:11.5px;color:var(--muted);line-height:1.5;margin:0 0 8px;padding:0 9px 0 61px}",
      /* honesty */
      ".rx-honesty{margin-top:28px;padding:20px 20px 16px;border-radius:14px;border:1px solid var(--line);background:var(--panel)}",
      ".rx-h-base,.rx-h-split{font-size:12.5px;line-height:1.55;color:var(--muted);margin:8px 0 0}",
      ".rx-h-split b{color:var(--text)}",
      ".rx-honesty-warn{border-color:color-mix(in srgb,var(--warn) 30%,var(--line));background:linear-gradient(160deg,var(--panel),color-mix(in srgb,var(--warn) 5%,var(--panel)))}",
      ".rx-honesty-ok{border-color:color-mix(in srgb,var(--up) 26%,var(--line))}",
      ".rx-h-eyebrow{font-size:10.5px;font-weight:800;letter-spacing:.14em;color:var(--warn)}",
      ".rx-honesty-ok .rx-h-eyebrow{color:var(--up)}.rx-honesty-wait .rx-h-eyebrow{color:var(--muted)}",
      ".rx-h-title{font-size:18px;font-weight:800;margin:4px 0 8px;letter-spacing:-.01em}",
      ".rx-h-para{font-size:13.5px;line-height:1.6;color:var(--text);margin:0 0 14px;max-width:820px}",
      ".rx-tiles{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}",
      ".rx-tile{flex:1;min-width:120px;padding:11px 13px;border-radius:10px;background:var(--panel2);border:1px solid var(--line)}",
      ".rx-tile-v{font-size:22px;font-weight:800;font-family:var(--font-mono);color:var(--text)}",
      ".rx-tile-l{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-top:2px}",
      ".rx-receipt{font-size:12px;color:var(--muted)}",
      ".rx-receipt summary{cursor:pointer;color:var(--link);font-weight:600}",
      ".rx-receipt p{margin:8px 0 0;line-height:1.55}",
      /* the AI read */
      ".rx-brain{margin-top:18px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:color-mix(in srgb,var(--info) 4%,var(--panel))}",
      ".rx-brain-off{background:var(--panel)}",
      ".rx-brain-head{font-size:14px;font-weight:800;margin-bottom:8px}",
      ".rx-brain-rot{font-size:12.5px;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:8px 11px;margin-bottom:9px;line-height:1.5}",
      ".rx-brain-row{padding:9px 0;border-bottom:1px solid var(--line)}",
      ".rx-brain-row:last-of-type{border-bottom:none}",
      ".rx-brain-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}",
      ".rx-brain-badge{font-size:10.5px;font-weight:800;padding:2px 9px;border-radius:999px;border:1px solid var(--bc,var(--muted));color:var(--bc,var(--muted))}",
      ".rx-brain-theme{font-size:13px;font-weight:700}",
      ".rx-brain-why{font-size:12.5px;color:var(--text);line-height:1.6;margin:6px 0 0}",
      ".rx-brain-full{margin-top:5px;font-size:11.5px;color:var(--muted)}",
      ".rx-brain-full summary{cursor:pointer;color:var(--link);font-weight:600}",
      ".rx-brain-full p{margin:7px 0 0;line-height:1.55}",
      ".rx-cav{font-size:10.5px;color:var(--muted);line-height:1.5;margin:10px 0 0}",
      /* footer caveat */
      ".rx-foot{font-size:11px;color:var(--muted);line-height:1.55;margin-top:20px;padding-top:14px;border-top:1px solid var(--line);max-width:900px}",
      ".rx-foot p{margin:0 0 6px}",
      ".rx-foot-more summary{cursor:pointer;color:var(--link);font-weight:600}",
      ".rx-foot-more p{margin:6px 0 0}",
      /* NOTE: no `[data-tip-en]{position:relative}` rule here. It used to sit at the
         end of this sheet and, being later at equal specificity, silently beat
         `position:absolute` on every tip-bearing element — which collapsed the meter
         markers to inline slivers. theme.css owns the trigger affordance (cursor) and
         the Lens popover positions itself from getBoundingClientRect against <body>,
         so the trigger never needs to be a containing block. */
      /* mobile */
      "@media(max-width:640px){",
      ".rx-hero{padding:18px 2px 14px}",
      ".rx-score{min-width:0;max-width:none;width:100%}",
      ".rx-lead-side{flex-basis:100%;max-width:none}",
      ".rx-cards{grid-template-columns:1fr}",
      ".rx-nq,.rx-nsel{width:100%}",
      ".rx-t-stance{display:none}",
      ".rx-nnote{padding-left:9px}",
      "}",
      /* reduced motion + coarse pointer: no reveal/lift churn */
      "@media(prefers-reduced-motion:reduce){.rx-reveal{animation:none}.rx-seg{transition:none}.rx-card{transition:none}}",
      "@media(pointer:coarse){.rx-card:hover{transform:none}}"
    ].join("");
    (document.head || document.documentElement).appendChild(el);
  }

  // ══════════════════════════════════════════════════════════════════════════
  //   renderRadarFull — FULL page entry (radar.html)
  // ══════════════════════════════════════════════════════════════════════════
  window.renderRadarFull = function (opts) {
    opts = opts || {};
    var base = opts.base || "basketdata/";
    var mount = document.querySelector(opts.mount || "#divergence-radar");
    if (!mount) return;
    injectFullStyles();
    window._rpFullRendered = true;

    var _allTickers = [], _allFlags = [];
    var _themeFilter = "all", _sortCol = "rel60", _sortAsc = false;
    var _nameVisible = 24, _nameFiltered = [];
    function byId(id) { return mount.querySelector("#" + id); }

    Promise.all([
      fetchJSON(base + "radar.json"),
      fetchJSON(base + "radar_enriched.json"),
      fetchJSON(base + "radar_news.json"),
      fetchJSON(base + "radar_ticker.json"),
      fetchJSON(base + "radar_ic.json"),
      fetchJSON(base + "radar_track_record.json"),
      fetchJSON(base + "narrative_brain.json")
    ]).then(function (r) {
      var radar = r[0], enriched = r[1], newsMap = r[2], tickers = r[3], ic = r[4], track = r[5], brain = r[6];
      if (!radar || !radar.flags || !radar.flags.length) {
        mount.innerHTML = '<div class="rx-calm">' + bi("The radar has no read to show right now.", "雷达暂无可显示的解读。") + "</div>";
        return;
      }
      mergeEnrichment(radar.flags, enriched, newsMap);
      _allFlags = radar.flags;
      _allTickers = (tickers && tickers.tickers) || [];

      var posDivs = radar.flags.filter(function (f) { return f.state === "POSITIVE_DIVERGENCE"; });
      var negDivs = radar.flags.filter(function (f) { return f.state === "NEGATIVE_DIVERGENCE"; });
      // Rank each lane by how stretched the divergence is (salience) — descriptive, not "edge".
      posDivs.sort(function (a, b) { return (b.salience || 0) - (a.salience || 0); });
      negDivs.sort(function (a, b) { return (b.salience || 0) - (a.salience || 0); });
      _nameFiltered = _allTickers.slice().sort(function (a, b) { return Math.abs(b.rs_vs_spy_60d || 0) - Math.abs(a.rs_vs_spy_60d || 0); });

      var h = '<div class="rx-wrap">';
      h += heroHTML(radar, enriched, ic);

      // The meter legend is a page-level constant: said once, above the first meter.
      if (posDivs.length || negDivs.length) h += meterKey();

      // Lead: top activity-ahead theme (the genuinely watch-worthy one)
      if (posDivs.length) h += leadHTML(posDivs[0]);

      // Lane: activity ahead of price (rest, if the lead took the first)
      var posRest = posDivs.slice(posDivs.length ? 1 : 0);
      if (posRest.length) {
        h += '<section class="rx-sec"><div class="rx-sec-head"><h2 class="rx-sec-title">🟢 ' + bi("More work running ahead of price", "更多真实活动领先价格") +
          '</h2><span class="rx-sec-cnt">' + posRest.length + "</span></div>" +
          '<p class="rx-sec-sub">' + bi("The work behind these themes is speeding up faster than the price. Watch for price to catch up — it may not.", "这些主题背后的真实活动比价格跑得更快。留意价格能否跟上 —— 也可能不会。") + "</p>" +
          '<div class="rx-cards">' + posRest.slice(0, 6).map(function (f, i) { return laneCard(f, i); }).join("") + "</div></section>";
      }

      // Lane: price ahead of activity
      h += '<section class="rx-sec"><div class="rx-sec-head"><h2 class="rx-sec-title">🟠 ' + bi("Price running ahead of the work", "价格领先真实活动") +
        '</h2><span class="rx-sec-cnt">' + negDivs.length + "</span></div>" +
        '<p class="rx-sec-sub">' + bi("Price has moved while the work behind it has slowed. These moves may be running on little — stand aside.", "价格已经上涨，而其背后的真实活动却在放缓。这些走势可能缺乏支撑 —— 旁观为宜。") + "</p>";
      if (!negDivs.length) {
        h += '<div class="rx-calm">' + bi("None today — where price has moved, the work behind it is keeping up.", "今日没有 —— 价格上涨之处，其背后的真实活动仍在跟上。") + "</div>";
      } else {
        var negTop = negDivs.slice(0, 6), negMore = negDivs.slice(6);
        h += '<div class="rx-cards" id="rx-neg-cards">' + negTop.map(function (f, i) { return laneCard(f, 100 + i); }).join("");
        h += negMore.map(function (f, i) { return laneCard(f, 200 + i); }).join("") + "</div>";
        if (negMore.length) {
          h += '<button class="rx-showmore" id="rx-neg-more" data-hidden="' + negMore.length + '">' +
            bi("Show " + negMore.length + " more", "再显示 " + negMore.length + " 个") + "</button>";
        }
      }
      h += "</section>";

      // Board (tabs: themes + stocks)
      var quietN = radar.flags.filter(function (f) { return f.state === "QUIET"; }).length;
      h += '<div class="rx-board rx-mixed">';
      h += '<div class="rx-tabs">' +
        '<button class="rx-tab rx-on" data-pane="themes">' + bi("All themes", "全部主题") + " (" + radar.flags.length + ")</button>" +
        '<button class="rx-tab" data-pane="stocks">' + bi("Stocks", "个股") + " (" + _allTickers.length + ")</button>" +
        "</div>";
      // themes pane
      h += '<div class="rx-pane rx-on" id="rx-pane-themes">';
      h += '<div class="rx-filters">' +
        '<button class="rx-fchip rx-on" data-f="all">' + bi("All", "全部") + "</button>" +
        '<button class="rx-fchip" data-f="pos">' + bi("Work ahead", "活动领先") + "</button>" +
        '<button class="rx-fchip" data-f="neg">' + bi("Price ahead", "价格领先") + "</button>" +
        '<button class="rx-fchip" data-f="conf">' + bi("Moving together", "同步变动") + "</button>" +
        '<button class="rx-fchip" data-f="quiet">' + bi("In line", "平静") + " (" + quietN + ")</button>" +
        "</div>";
      h += '<div style="overflow-x:auto"><table class="rx-tbl"><thead><tr>' +
        '<th data-col="name">' + bi("Theme", "主题") + '<span class="rx-so">↕</span></th>' +
        '<th data-col="accel" data-tip-en="How busy the real work is now against a year ago. 1.0× is unchanged, above is speeding up, below is slowing." data-tip-zh="真实活动相对一年前的忙碌程度。1.0× 为持平，高于为加速，低于为放缓。">' + bi("Work vs a year ago", "活动 vs 去年") + '<span class="rx-so">↕</span></th>' +
        '<th data-col="rel60" data-tip-en="How the theme has done against the market over the last 60 days." data-tip-zh="该主题过去60天相对大盘的表现。">' + bi("Price vs market", "价格 vs 大盘") + '<span class="rx-so">↕</span></th>' +
        '<th data-tip-en="The read on each of the last 14 days." data-tip-zh="过去14天每天的解读。">' + bi("Last 14 days", "过去14天") + "</th>" +
        '<th data-col="state">' + bi("Read", "解读") + '<span class="rx-so">↕</span></th>' +
        '<th>' + bi("What to do", "该怎么做") + "</th>" +
        '</tr></thead><tbody id="rx-tbody"></tbody></table></div>';
      h += "</div>";
      // stocks pane
      h += '<div class="rx-pane" id="rx-pane-stocks">';
      h += '<div class="rx-nctrl">' +
        '<input class="rx-nq" id="rx-nq" placeholder="' + (isZh() ? "搜索代码或主题…" : "Search a ticker or theme…") + '">' +
        '<select class="rx-nsel" id="rx-nstate" aria-label="' + (isZh() ? "按解读筛选" : "Filter by read") + '">' +
          opt("all", "All reads", "全部解读") +
          opt("POSITIVE_DIVERGENCE", "Work ahead of price", "活动领先价格") +
          opt("NEGATIVE_DIVERGENCE", "Price ahead of work", "价格领先活动") +
          opt("CONFIRMED_UP", "Both rising", "同步上行") +
          opt("CONFIRMED_DOWN", "Both cooling", "同步走弱") +
          opt("BROKEN_LAGGARD", "Falling behind", "掉队") +
          opt("QUIET", "In line", "平静") +
        "</select>" +
        '<select class="rx-nsel" id="rx-nbasket" aria-label="' + (isZh() ? "按主题筛选" : "Filter by theme") + '">' +
          opt("all", "All themes", "全部主题") + "</select>" +
        "</div>";
      h += '<div id="rx-nrows"></div>';
      h += '<button class="rx-showmore" id="rx-nmore">' + bi("Show more", "显示更多") + "</button>";
      h += "</div>";
      h += "</div>"; // board

      // Honesty + the AI read + footer. The AI read gets a basket→flag index so
      // its theme names can link to the same detail pages the cards link to.
      h += honestyHTML(ic, track);
      var flagIndex = {};
      radar.flags.forEach(function (f) { if (f.basket) flagIndex[f.basket] = f; });
      h += brainRx(brain, flagIndex);
      h += footNote(radar);

      h += "</div>"; // rx-wrap
      mount.innerHTML = h;

      // ── Wire interactions ──────────────────────────────────────────────────
      // Card / note disclosures are native <details> — no JS, keyboard-accessible
      // for free. Ticker and theme links are plain anchors: theme.js intercepts
      // stock.html#TICKER in the capture phase and opens the Terminal workspace.

      // tabs
      mount.querySelectorAll(".rx-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
          var pane = tab.getAttribute("data-pane");
          mount.querySelectorAll(".rx-tab").forEach(function (x) { x.classList.toggle("rx-on", x === tab); });
          mount.querySelectorAll(".rx-pane").forEach(function (x) { x.classList.toggle("rx-on", x.id === "rx-pane-" + pane); });
        });
      });

      // show-more (negative lane)
      var negMoreBtn = byId("rx-neg-more");
      if (negMoreBtn) {
        var negCards = mount.querySelectorAll("#rx-neg-cards .rx-card");
        negCards.forEach(function (c, i) { if (i >= 6) c.style.display = "none"; });
        negMoreBtn.addEventListener("click", function () {
          var hidden = negMoreBtn.getAttribute("data-hidden") === "0";
          negCards.forEach(function (c, i) { if (i >= 6) c.style.display = hidden ? "none" : ""; });
          negMoreBtn.setAttribute("data-hidden", hidden ? String(negCards.length - 6) : "0");
          negMoreBtn.innerHTML = hidden ? bi("Show " + (negCards.length - 6) + " more", "再显示 " + (negCards.length - 6) + " 个") : bi("Show fewer", "收起");
        });
      }

      // themes table
      function themeSortVal(f) {
        if (_sortCol === "name") return (f.name || "").toLowerCase();
        if (_sortCol === "accel") return (f.observable && f.observable.accel != null) ? f.observable.accel : -999;
        if (_sortCol === "rel60") return (f.consensus && f.consensus.rel_60d != null) ? f.consensus.rel_60d : -999;
        if (_sortCol === "state") return { POSITIVE_DIVERGENCE: 0, NEGATIVE_DIVERGENCE: 1, CONFIRMED_UP: 2, CONFIRMED_DOWN: 3, QUIET: 4 }[f.state] || 5;
        return 0;
      }
      function paintThemes() {
        var tbody = byId("rx-tbody");
        if (!tbody) return;
        var rows = _allFlags.filter(function (f) {
          if (_themeFilter === "pos") return f.state === "POSITIVE_DIVERGENCE";
          if (_themeFilter === "neg") return f.state === "NEGATIVE_DIVERGENCE";
          if (_themeFilter === "conf") return (f.state || "").indexOf("CONFIRMED") >= 0;
          if (_themeFilter === "quiet") return f.state === "QUIET";
          return f.state !== "QUIET"; // "all" hides quiet by default (21 in-line rows are noise)
        });
        rows = rows.slice().sort(function (a, b) {
          var va = themeSortVal(a), vb = themeSortVal(b);
          return _sortAsc ? (va > vb ? 1 : va < vb ? -1 : 0) : (va < vb ? 1 : va > vb ? -1 : 0);
        });
        tbody.innerHTML = rows.map(boardRow).join("");
        mount.querySelectorAll(".rx-tbl th[data-col]").forEach(function (th) {
          th.classList.toggle("rx-sorted", th.getAttribute("data-col") === _sortCol);
          var so = th.querySelector(".rx-so");
          if (so) so.textContent = th.getAttribute("data-col") === _sortCol ? (_sortAsc ? "↑" : "↓") : "↕";
        });
      }
      mount.querySelectorAll(".rx-fchip").forEach(function (chip) {
        chip.addEventListener("click", function () {
          _themeFilter = chip.getAttribute("data-f");
          mount.querySelectorAll(".rx-fchip").forEach(function (x) { x.classList.toggle("rx-on", x === chip); });
          paintThemes();
        });
      });
      mount.querySelectorAll(".rx-tbl th[data-col]").forEach(function (th) {
        th.addEventListener("click", function () {
          var col = th.getAttribute("data-col");
          if (_sortCol === col) _sortAsc = !_sortAsc; else { _sortCol = col; _sortAsc = col === "name"; }
          paintThemes();
        });
      });
      paintThemes();

      // stocks / per-name
      var bmap = {};
      _allTickers.forEach(function (t) { if (t.basket && t.basket_name) bmap[t.basket] = t.basket_name; });
      var bsel = byId("rx-nbasket");
      Object.keys(bmap).sort(function (a, b) { return bmap[a].localeCompare(bmap[b]); }).forEach(function (k) {
        var o = document.createElement("option"); o.value = k; o.textContent = bmap[k]; if (bsel) bsel.appendChild(o);
      });
      function paintNames() {
        var el = byId("rx-nrows");
        if (!el) return;
        el.innerHTML = _nameFiltered.slice(0, _nameVisible).map(function (t, i) { return nameRowRx(t, i); }).join("");
        var more = byId("rx-nmore");
        if (more) more.style.display = _nameFiltered.length > _nameVisible ? "" : "none";
      }
      function filterNames() {
        var q = (byId("rx-nq") ? byId("rx-nq").value || "" : "").toLowerCase();
        var stF = byId("rx-nstate") ? byId("rx-nstate").value : "all";
        var bsF = byId("rx-nbasket") ? byId("rx-nbasket").value : "all";
        _nameFiltered = _allTickers.filter(function (t) {
          if (q && !(t.ticker || "").toLowerCase().startsWith(q) && !(t.basket_name || "").toLowerCase().includes(q)) return false;
          if (stF !== "all" && t.state !== stF) return false;
          if (bsF !== "all" && t.basket !== bsF) return false;
          return true;
        }).sort(function (a, b) { return Math.abs(b.rs_vs_spy_60d || 0) - Math.abs(a.rs_vs_spy_60d || 0); });
        _nameVisible = 24;
        paintNames();
      }
      if (byId("rx-nq")) byId("rx-nq").addEventListener("input", filterNames);
      if (byId("rx-nstate")) byId("rx-nstate").addEventListener("change", filterNames);
      if (byId("rx-nbasket")) byId("rx-nbasket").addEventListener("change", filterNames);
      if (byId("rx-nmore")) byId("rx-nmore").addEventListener("click", function () { _nameVisible += 24; paintNames(); });
      paintNames();

      // Live language switch: the .l-en/.l-zh spans flip via CSS, but <option> text
      // has to be rewritten by hand.
      document.addEventListener("langchange", function () {
        repaintOptionLang(mount);
        var ph = byId("rx-nq");
        if (ph) ph.placeholder = isZh() ? "搜索代码或主题…" : "Search a ticker or theme…";
      });
    });
  }; // end renderRadarFull

  // Legacy no-op guards (old rendered pages call these; full mode handles it all now)
  window.renderRadarLifecycle = function () {};
  window.renderTickerRadar = function () {};

})();

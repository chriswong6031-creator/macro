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
  //   FULL PAGE (radar.html) — "mx-radar" redesign
  //   User-first doctrine: state + stance + plain line on the glance tier;
  //   mechanics/receipts demoted to hover + the Details section. Honest about
  //   the radar's own (negative) track record — this is watch-only context.
  //   Shares only pure text helpers with the compact embed (esc/bi/usd/relpct/
  //   st/mergeEnrichment); all visual markup below is rx- prefixed and self-
  //   contained so the baskets.html embed (renderDivergenceRadar) is untouched.
  // ══════════════════════════════════════════════════════════════════════════

  // Plain-word state map (Doctrine Law 2 — no DIVERGENCE / CONFIRMED enums on tier 1)
  var PLAIN = {
    POSITIVE_DIVERGENCE: { en: "Activity ahead of price", zh: "活动领先价格", short_en: "Activity leads", short_zh: "活动领先",
      stance_en: "Watch — don't chase", stance_zh: "观察 — 别追", tone: "up",
      gist_en: "Real work is accelerating faster than the tape. Watch for price to catch up — it may not.",
      gist_zh: "真实活动加速快于价格。留意价格能否跟上 —— 也可能不会。" },
    NEGATIVE_DIVERGENCE: { en: "Price ahead of activity", zh: "价格领先活动", short_en: "Price leads", short_zh: "价格领先",
      stance_en: "Stand aside", stance_zh: "旁观", tone: "down",
      gist_en: "The tape is leading; the real-activity engine underneath has cooled. The move may be running on fumes.",
      gist_zh: "价格在领先，而底层真实活动已降温。这波行情可能已是强弩之末。" },
    CONFIRMED_UP: { en: "Both rising", zh: "同步上行", short_en: "Both rising", short_zh: "同步上行",
      stance_en: "Already in the price", stance_zh: "已反映在价格", tone: "up",
      gist_en: "Activity and price agree and rise together — corroborated, but largely already priced.",
      gist_zh: "活动与价格同向上行 —— 已被印证，但大体已反映在价格中。" },
    CONFIRMED_DOWN: { en: "Both cooling", zh: "同步走弱", short_en: "Both cooling", short_zh: "同步走弱",
      stance_en: "Already in the price", stance_zh: "已反映在价格", tone: "down",
      gist_en: "Activity and price agree and fall together — corroborated weakness.",
      gist_zh: "活动与价格同向下行 —— 走弱已被印证。" },
    QUIET: { en: "In line", zh: "平静", short_en: "In line", short_zh: "平静",
      stance_en: "Nothing to do", stance_zh: "无需操作", tone: "flat",
      gist_en: "Real activity and price agree. No edge here — the read is already in the tape.",
      gist_zh: "真实活动与价格一致。此处无边际 —— 价格已经反映。" }
  };
  function plain(state) { return PLAIN[state] || PLAIN.QUIET; }
  function toneCol(t) { return t === "up" ? "var(--up)" : t === "down" ? "var(--warn)" : "var(--muted)"; }

  // Numbers with meaning (Doctrine Law 3)
  function accelPlain(accel, tone) {
    if (accel == null) return tone === "down" ? bi("activity cooling", "活动降温") : bi("activity rising", "活动上升");
    var x = accel.toFixed(1);
    if (accel >= 1.15) return bi("activity ~" + x + "× vs a year ago", "活动约为去年 " + x + " 倍");
    if (accel <= 0.9) return bi("activity cooling (~" + x + "× vs a year ago)", "活动降温（约为去年 " + x + " 倍）");
    return bi("activity roughly flat (~" + x + "× vs a year ago)", "活动基本持平（约为去年 " + x + " 倍）");
  }
  function relPlain(rel) {
    if (rel == null) return bi("price in line with market", "价格与大盘一致");
    var p = (rel > 0 ? "+" : "") + (rel * 100).toFixed(0) + "%";
    return bi("price " + p + " vs market (60d)", "价格相对大盘 " + p + "（60日）");
  }
  // Keep only the theme-specific first sentence of the engine note; the generic
  // tail ("The narrative may be running ahead…") is a per-card constant the
  // section sub + stance chip already carry (Doctrine Law 4 — no repeated constants).
  function oneSentence(s, zhSep) {
    if (!s) return s;
    var f = zhSep ? s.split("。")[0] : s.split(/\.\s+/)[0];
    if (!/[.!?。！？]$/.test(f)) f += zhSep ? "。" : ".";
    return f;
  }

  // Plain source chips — label only on tier 1; raw z-score demoted to hover.
  function srcChipsRx(o) {
    var ss = (o || {}).sources || [];
    if (!ss.length) return "";
    var chips = ss.slice(0, 4).map(function (s) {
      var z = s.z == null ? 0 : s.z;
      var col = z > 0.2 ? "var(--up)" : z < -0.2 ? "var(--down)" : "var(--muted)";
      var arr = z > 0.2 ? "▲" : z < -0.2 ? "▼" : "·";
      var tip = "z " + (z > 0 ? "+" : "") + z.toFixed(1);
      return '<span class="rx-src" style="--sc:' + col + '" data-tip-en="' + esc(tip) + '" data-tip-zh="' + esc(tip) +
        '">' + bi(s.label_en || s.name, s.label_zh || s.name) + ' <b>' + arr + '</b></span>';
    });
    return '<div class="rx-srcs">' + chips.join("") + "</div>";
  }

  // 14-day state trail — categorical (state over time), the honest encoding.
  function trailRx(strip) {
    if (!strip || !strip.length) return "";
    var dots = strip.slice(-14).map(function (it) {
      var t = plain(it.s).tone;
      var col = t === "up" ? "var(--up)" : t === "down" ? "var(--warn)" : it.s && it.s.indexOf("CONFIRM") >= 0 ? "var(--info)" : "var(--line)";
      return '<i style="background:' + col + '"></i>';
    }).join("");
    return '<span class="rx-trail" data-tip-en="Read over the last 14 days" data-tip-zh="过去14天的解读">' + dots + "</span>";
  }

  // ── Hero ──────────────────────────────────────────────────────────────────
  function heroHTML(radar, enriched) {
    var cov = radar.coverage || {};
    var regime = (enriched || {}).regime || {};
    var changes = (enriched || {}).changes || {};
    var flags = radar.flags || [];
    var pos = flags.filter(function (f) { return f.state === "POSITIVE_DIVERGENCE"; }).length;
    var neg = flags.filter(function (f) { return f.state === "NEGATIVE_DIVERGENCE"; }).length;
    var confU = flags.filter(function (f) { return f.state === "CONFIRMED_UP"; }).length;
    var confD = flags.filter(function (f) { return f.state === "CONFIRMED_DOWN"; }).length;
    var quiet = flags.filter(function (f) { return f.state === "QUIET"; }).length;
    var total = flags.length || 1;
    var divs = pos + neg;

    // Verdict tone: leans on which side of the disagreement dominates.
    var toneCls = divs === 0 ? "rx-flat" : (pos > neg ? "rx-green" : (neg > pos * 2 ? "rx-amber" : "rx-mixed"));
    var headEn, headZh;
    if (divs === 0) {
      headEn = "Real activity and price agree across all " + total + " themes today";
      headZh = "今日全部 " + total + " 个主题的真实活动与价格一致";
    } else {
      headEn = "Real activity and price disagree on " + divs + " of " + total + " themes";
      headZh = "真实活动与价格在 " + total + " 个主题中的 " + divs + " 个上出现背离";
    }
    var flipEn = pos + " with activity running ahead of price, " + neg + " with price running ahead of activity.";
    var flipZh = pos + " 个活动领先价格，" + neg + " 个价格领先活动。";

    // Stance (Doctrine Law 1) — this radar is context-only with a weak track record,
    // so the honest whole-page stance is always "watch, don't chase".
    var stanceEn = pos > 0 ? "Watch — don't chase" : "Stand aside";
    var stanceZh = pos > 0 ? "观察 — 别追" : "旁观";

    // Composition bar segments (descriptive, not a predictive score)
    function seg(n, col, en, zh) {
      if (!n) return "";
      return '<span class="rx-seg" style="flex:' + n + ';background:' + col + '" ' +
        'data-tip-en="' + n + " " + en + '" data-tip-zh="' + n + " " + zh + '"></span>';
    }
    var bar = '<div class="rx-comp">' +
      seg(pos, "var(--up)", "activity ahead of price", "活动领先价格") +
      seg(neg, "var(--warn)", "price ahead of activity", "价格领先活动") +
      seg(confU + confD, "var(--info)", "both agree", "同步") +
      seg(quiet, "color-mix(in srgb,var(--muted) 30%,transparent)", "in line", "平静") +
      "</div>";
    var legend = '<div class="rx-comp-legend">' +
      '<span><i style="background:var(--up)"></i>' + bi(pos + " activity-led", pos + " 活动领先") + "</span>" +
      '<span><i style="background:var(--warn)"></i>' + bi(neg + " price-led", neg + " 价格领先") + "</span>" +
      '<span><i style="background:var(--info)"></i>' + bi((confU + confD) + " agree", (confU + confD) + " 同步") + "</span>" +
      '<span><i style="background:color-mix(in srgb,var(--muted) 45%,transparent)"></i>' + bi(quiet + " in line", quiet + " 平静") + "</span>" +
      "</div>";

    var word = divs === 0 ? bi("Quiet board", "平静") :
      (pos > neg ? bi("Activity leading", "活动领先") : bi("Mostly price-led — caution", "多为价格领先 — 谨慎"));

    // Δ since yesterday
    var nd = (changes.new_divergences || []).length, rs = (changes.resolved || []).length, fl = (changes.flips || []).length;
    var deltaLine;
    if (nd + rs + fl === 0) {
      deltaLine = '<span class="rx-mut">' + bi("No changes since yesterday", "较昨日无变化") + "</span>";
    } else {
      var parts = [];
      if (nd) parts.push('<b style="color:var(--warn)">+' + nd + " " + bi("new", "新增") + "</b>");
      if (rs) parts.push('<b style="color:var(--up)">✓' + rs + " " + bi("cleared", "消除") + "</b>");
      if (fl) parts.push('<b style="color:var(--info)">⇄' + fl + " " + bi("flipped", "反转") + "</b>");
      deltaLine = parts.join(" · ");
    }

    var regimeChip = regime.quad_name
      ? '<span class="rx-chip rx-chip-regime" data-tip-en="Market regime the read sits inside" data-tip-zh="解读所处的市场周期">' +
        esc(regime.quad_name) + (regime.liquidity ? " · " + bi("liquidity " + regime.liquidity, "流动性" + (regime.liquidity === "expanding" ? "扩张" : "收缩")) : "") + "</span>"
      : "";

    var asof = radar.as_of ? '<span class="rx-asof">' + bi("as of ", "截至 ") + esc(radar.as_of) +
      (radar.lag_months ? " · " + bi("activity lags ~" + radar.lag_months + "mo", "活动滞后约" + radar.lag_months + "月") : "") + "</span>" : "";

    return '<section class="rx-hero ' + toneCls + '">' +
      '<div class="rx-eyebrow">🛰️ ' + bi("DIVERGENCE RADAR", "背离雷达") +
        ' <span class="rx-eyebrow-sub">· ' + bi("real activity vs price", "真实活动 vs 价格") + "</span></div>" +
      '<h1 class="rx-verdict">' + bi(headEn, headZh) + "</h1>" +
      '<p class="rx-flip">' + bi(flipEn, flipZh) + "</p>" +
      '<div class="rx-stance-row">' +
        '<span class="rx-stance rx-stance-' + (pos > 0 ? "watch" : "aside") + '">' + bi(stanceEn, stanceZh) + "</span>" +
        '<span class="rx-stance-note">' + bi("context, not a buy list", "仅供参考，非买入清单") + "</span>" +
      "</div>" +
      '<div class="rx-hero-row">' +
        '<div class="rx-score">' +
          '<div class="rx-score-top"><span class="rx-score-num">' + divs + '</span>' +
            '<div class="rx-score-lab"><span class="rx-score-cap">' + bi("divergences today", "今日背离") + "</span>" +
            '<span class="rx-score-of">' + bi("of " + total + " themes watched", "共观察 " + total + " 个主题") + "</span></div></div>" +
          '<div class="rx-score-word">' + word + "</div>" +
          bar + legend +
        "</div>" +
        '<div class="rx-ctx">' +
          '<div class="rx-ctx-row">' + regimeChip + asof + "</div>" +
          '<div class="rx-ctx-delta"><span class="rx-ctx-k">' + bi("Since yesterday", "较昨日") + "</span> " + deltaLine + "</div>" +
          '<a class="rx-ctx-honesty" href="#rx-honesty"><span class="rx-ctx-k">' + bi("Has this worked?", "这套解读有效吗？") + "</span> " +
            '<span class="rx-mut">' + bi("Not yet — these calls have lagged the market. Watch-only. See the check ↓", "尚未 —— 这些解读跑输大盘。仅供观察。见下方核对 ↓") + "</span></a>" +
        "</div>" +
      "</div>" +
    "</section>";
  }

  // ── Lead card: the single most watch-worthy read (top activity-ahead theme) ──
  function leadHTML(f) {
    if (!f) return "";
    var p = plain(f.state);
    var o = f.observable || {};
    var c = f.consensus || {};
    var tickers = (o.covered || []).slice(0, 6).join(" · ");
    return '<section class="rx-lead rx-reveal">' +
      '<div class="rx-lead-tag">⭐ ' + bi("Most watch-worthy today", "今日最值得关注") + "</div>" +
      '<div class="rx-lead-body">' +
        '<div class="rx-lead-main">' +
          '<div class="rx-lead-head">' +
            '<span class="rx-badge rx-badge-up">' + bi(p.short_en, p.short_zh) + "</span>" +
            '<h2 class="rx-lead-name">' + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</h2>" +
          "</div>" +
          '<p class="rx-lead-gist">' + bi(p.gist_en, p.gist_zh) + "</p>" +
          srcChipsRx(o) +
          '<div class="rx-metrics">' +
            '<span class="rx-metric rx-metric-up">' + accelPlain(o.accel, "up") + "</span>" +
            '<span class="rx-metric">' + relPlain(c.rel_60d) + "</span>" +
          "</div>" +
          (tickers ? '<div class="rx-tickers">' + bi("names: ", "成分：") + esc(tickers) + "</div>" : "") +
        "</div>" +
        '<div class="rx-lead-side">' +
          '<span class="rx-stance rx-stance-watch">' + bi("Watch — don't chase", "观察 — 别追") + "</span>" +
          '<span class="rx-lead-side-note">' + bi("Activity is leading. If the tape confirms, the board below upgrades on its own — no need to front-run it.", "活动在领先。若价格随后确认，下方看板会自动升级 —— 无需抢跑。") + "</span>" +
          trailRx(f.state_strip) +
        "</div>" +
      "</div>" +
    "</section>";
  }

  // ── Lane card (activity-ahead / price-ahead lanes) ──────────────────────────
  function laneCard(f, i) {
    var p = plain(f.state);
    var o = f.observable || {};
    var c = f.consensus || {};
    var col = toneCol(p.tone);
    var expandId = "rx-lx-" + i;
    var tickers = (o.covered || []).slice(0, 8).join(" · ");
    var news = f._headlines || [];
    var newsBtn = news.length
      ? '<button class="rx-mini" data-news="' + expandId + '">📰 ' + news.length + "</button>" : "";
    var newsBody = news.length
      ? '<div class="rx-news" id="' + expandId + '-news">' + news.slice(0, 3).map(function (h) {
          var sent = h.sentiment === "pos" ? "▲" : h.sentiment === "neg" ? "▼" : "";
          return '<a class="rx-hl" href="' + esc(/^https?:\/\//i.test(h.url || "") ? h.url : "#") + '" target="_blank" rel="noopener noreferrer">' +
            esc(h.title || "") + ' <span class="rx-mut">· ' + esc(h.source || "") + " " + sent + "</span></a>";
        }).join("") + "</div>" : "";

    return '<article class="rx-card rx-reveal" style="--cc:' + col + ';animation-delay:' + Math.min(i * 40, 320) + 'ms">' +
      '<div class="rx-card-top">' +
        '<span class="rx-badge" style="--bc:' + col + '">' + bi(p.short_en, p.short_zh) + "</span>" +
        '<h3 class="rx-card-name">' + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</h3>" +
      "</div>" +
      '<p class="rx-card-gist">' + bi(oneSentence(f.note) || p.gist_en, oneSentence(f.note_zh, true) || p.gist_zh) + "</p>" +
      srcChipsRx(o) +
      '<div class="rx-metrics">' +
        '<span class="rx-metric">' + accelPlain(o.accel, p.tone) + "</span>" +
        '<span class="rx-metric">' + relPlain(c.rel_60d) + "</span>" +
      "</div>" +
      '<div class="rx-card-foot">' +
        '<span class="rx-stance-mini rx-stance-' + (p.tone === "up" ? "watch" : "aside") + '">' + bi(p.stance_en, p.stance_zh) + "</span>" +
        trailRx(f.state_strip) +
        (news.length ? newsBtn : "") +
        (tickers ? '<button class="rx-mini" data-exp="' + expandId + '">' + bi("names", "成分") + "</button>" : "") +
      "</div>" +
      (tickers ? '<div class="rx-exp" id="' + expandId + '">' + esc(tickers) + "</div>" : "") +
      newsBody +
    "</article>";
  }

  // ── Board table row ─────────────────────────────────────────────────────────
  function boardRow(f) {
    var p = plain(f.state);
    var o = f.observable || {};
    var c = f.consensus || {};
    var col = toneCol(p.tone);
    var accel = o.accel;
    var accelStr = accel == null ? "—" : accel.toFixed(1) + "×";
    var accelCol = accel == null ? "var(--muted)" : accel >= 1.15 ? "var(--up)" : accel <= 0.9 ? "var(--warn)" : "var(--muted)";
    var rel = c.rel_60d;
    var relCol = rel > 0 ? "var(--up)" : rel < 0 ? "var(--down)" : "var(--muted)";
    return "<tr>" +
      "<td class=\"rx-t-name\">" + bi(f.name || f.basket, f.name_zh || f.name || f.basket) + "</td>" +
      '<td class="rx-num" style="color:' + accelCol + '">' + accelStr + "</td>" +
      '<td class="rx-num" style="color:' + relCol + '">' + relpct(rel) + "</td>" +
      '<td>' + trailRx(f.state_strip) + "</td>" +
      '<td><span class="rx-badge rx-badge-sm" style="--bc:' + col + '">' + bi(p.short_en, p.short_zh) + "</span></td>" +
      '<td class="rx-t-stance rx-mut">' + bi(p.stance_en, p.stance_zh) + "</td>" +
      "</tr>";
  }

  // ── Per-name row ────────────────────────────────────────────────────────────
  function nameRowRx(t, i) {
    var p = plain(t.state);
    var col = toneCol(p.tone);
    var rs = t.rs_vs_spy_60d;
    var rsCol = rs > 0 ? "var(--up)" : rs < 0 ? "var(--down)" : "var(--muted)";
    var eid = "rx-nm-" + i;
    var note = t.note || "";
    return '<div class="rx-nrow" data-nexp="' + eid + '">' +
      '<span class="rx-ntk">' + esc(t.ticker) + "</span>" +
      '<span class="rx-badge rx-badge-sm" style="--bc:' + col + '">' + bi(p.short_en, p.short_zh) + "</span>" +
      '<span class="rx-nbasket">' + esc(t.basket_name || t.basket || "") + "</span>" +
      '<span class="rx-nrs" style="color:' + rsCol + '">' + (rs != null ? (rs > 0 ? "+" : "") + rs.toFixed(0) + "%" : "—") + "</span>" +
      "</div>" +
      (note ? '<div class="rx-nexp" id="' + eid + '">' + esc(note) + "</div>" : "");
  }

  // ── Honesty / track-record section (plain words; receipt on tier 2) ─────────
  function honestyHTML(ic, track) {
    ic = ic || {}; track = track || {};
    var nSnap = ic.n_snapshots || 0, nMat = ic.n_matured || 0;
    var icAll = ic.ic_all;
    var open = track.open || 0;
    // Plain verdict from the sign of IC
    var worked = icAll == null ? null : icAll > 0.03;
    var headEn, headZh, paraEn, paraZh, tone;
    if (icAll == null || nMat < 30) {
      tone = "wait";
      headEn = "Has the radar's read paid off? Too early to say.";
      headZh = "雷达的解读有效吗？现在下结论还太早。";
      paraEn = "We are still grading past calls as their horizons elapse. Until then, treat every read here as watch-only context — never a buy list.";
      paraZh = "过去的解读仍在随时间窗口到期而评分。在此之前，请把这里的每条解读都当作仅供观察的参考 —— 绝非买入清单。";
    } else if (worked) {
      tone = "ok";
      headEn = "Has the radar's read paid off? Modestly, so far.";
      headZh = "雷达的解读有效吗？目前来看略有帮助。";
      paraEn = "Across the calls we can now grade, themes the radar flagged have leaned the right way more often than not. Still context, not a signal — size nothing to it.";
      paraZh = "在已可评分的解读中，雷达标记的主题多数时候方向正确。但仍属参考而非信号 —— 不应据此下注。";
    } else {
      tone = "warn";
      headEn = "Has the radar's read paid off? Not yet.";
      headZh = "雷达的解读有效吗？尚未。";
      paraEn = "Across " + nMat.toLocaleString() + " past calls we can now grade, the themes this radar flagged have tended to lag the market, not lead it — and the ones it rated highest did the worst. That is exactly why every read here is watch-only context, never a buy list.";
      paraZh = "在已可评分的 " + nMat.toLocaleString() + " 条解读中，雷达标记的主题往往跑输而非领先大盘 —— 其评分最高者表现最差。正因如此，这里的每条解读都仅供观察，绝非买入清单。";
    }

    function tile(v, en, zh) {
      return '<div class="rx-tile"><div class="rx-tile-v">' + esc(v) + '</div><div class="rx-tile-l">' + bi(en, zh) + "</div></div>";
    }
    var receipt = "Rank-correlation of the radar's edge score vs its 21-day forward return: " +
      (icAll == null ? "—" : icAll.toFixed(2)) + " (n=" + nMat.toLocaleString() + "). " +
      (icAll != null && icAll < 0 ? "Negative — higher scores mapped to weaker returns. " : "") +
      "90-day rolling: " + (ic.ic_rolling_90 == null ? "—" : ic.ic_rolling_90.toFixed(2)) + ". Schema radar_ic.v1.";
    var receiptZh = "雷达优势分与其21日前瞻收益的秩相关：" + (icAll == null ? "—" : icAll.toFixed(2)) +
      "（n=" + nMat.toLocaleString() + "）。" + (icAll != null && icAll < 0 ? "为负 —— 评分越高，收益越弱。" : "") +
      "90日滚动：" + (ic.ic_rolling_90 == null ? "—" : ic.ic_rolling_90.toFixed(2)) + "。架构 radar_ic.v1。";

    return '<section class="rx-honesty rx-honesty-' + tone + '" id="rx-honesty">' +
      '<div class="rx-h-head">' +
        '<span class="rx-h-eyebrow">' + bi("THE HONESTY CHECK", "诚实核对") + "</span>" +
        '<h2 class="rx-h-title">' + bi(headEn, headZh) + "</h2>" +
      "</div>" +
      '<p class="rx-h-para">' + bi(paraEn, paraZh) + "</p>" +
      '<div class="rx-tiles">' +
        tile(nSnap.toLocaleString(), "Reads recorded", "已记录解读") +
        tile(nMat.toLocaleString(), "Now graded", "已评分") +
        tile(open.toLocaleString(), "Still open", "仍在跟踪") +
      "</div>" +
      '<details class="rx-receipt"><summary>' + bi("Show the technical receipt", "查看技术明细") + "</summary>" +
        '<p>' + bi(receipt, receiptZh) + "</p></details>" +
    "</section>";
  }

  // ── Narrative brain (rx-styled; graceful degraded state) ────────────────────
  function brainRx(b) {
    if (!b) return "";
    var has = b.assessments && b.assessments.length && !b.degraded_reason;
    if (!has) {
      return '<section class="rx-brain rx-brain-off">' +
        '<div class="rx-brain-head">🧠 ' + bi("The AI read", "AI 解读") + "</div>" +
        '<p class="rx-mut">' + bi("The AI durability read is unavailable right now — the deterministic radar above stands on its own.",
          "AI 持续力解读暂不可用 —— 上方的确定性雷达可独立使用。") + "</p></section>";
    }
    var V = { ENTER: { en: "Lean in", zh: "偏多", c: "var(--up)" }, MONITOR: { en: "Just watch", zh: "观察", c: "var(--muted)" }, AVOID: { en: "Steer clear", zh: "回避", c: "var(--warn)" } };
    var rows = b.assessments.map(function (a) {
      var v = V[a.verdict] || V.MONITOR;
      return '<div class="rx-brain-row">' +
        '<span class="rx-brain-badge" style="--bc:' + v.c + '">' + bi(v.en, v.zh) + "</span>" +
        '<b>' + bi(a.name || a.basket, a.name_zh || a.name || a.basket) + "</b>" +
        '<p class="rx-brain-why">' + bi(a.rationale || "", a.rationale_zh || a.rationale || "") + "</p></div>";
    }).join("");
    var rot = (b.rotation && b.rotation.summary) ? '<div class="rx-brain-rot">🔁 ' + bi(b.rotation.summary, b.rotation.summary_zh || b.rotation.summary) + "</div>" : "";
    return '<section class="rx-brain">' +
      '<div class="rx-brain-head">🧠 ' + bi("The AI read", "AI 解读") +
        ' <span class="rx-mut">· ' + bi("odds, not a forecast — graded later", "是概率而非预测 —— 事后评分") + "</span></div>" +
      rot + rows +
      '<p class="rx-cav">' + bi(b.disclaimer || "", b.disclaimer || "") + "</p></section>";
  }

  // ── CSS for the full page (rx- prefix, id-guarded, injected once) ───────────
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
      /* ── HERO ── */
      ".rx-hero{position:relative;padding:26px 4px 20px;overflow:hidden}",
      ".rx-hero::before{content:'';position:absolute;inset:-40% -20% auto -20%;height:340px;z-index:0;pointer-events:none;" +
        "background:radial-gradient(60% 80% at 22% 0%,color-mix(in srgb,var(--hc,var(--warn)) 20%,transparent),transparent 70%);opacity:.5;filter:blur(6px)}",
      ".rx-hero>*{position:relative;z-index:1}",
      ".rx-green{--hc:var(--up)}.rx-amber{--hc:var(--warn)}.rx-mixed{--hc:var(--info)}.rx-flat{--hc:var(--muted)}",
      ".rx-eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--muted);margin-bottom:10px}",
      ".rx-eyebrow-sub{font-weight:600;letter-spacing:.02em;opacity:.8}",
      ".rx-verdict{font-size:clamp(23px,3.6vw,34px);font-weight:800;line-height:1.14;letter-spacing:-.02em;margin:0 0 6px;" +
        "-webkit-text-fill-color:transparent;background-clip:text;-webkit-background-clip:text;" +
        "background-image:linear-gradient(115deg,var(--text) 0%,color-mix(in srgb,var(--hc,var(--warn)) 70%,var(--text)) 62%,var(--hc,var(--warn)) 100%)}",
      ".rx-flip{font-size:13.5px;color:var(--muted);margin:0 0 14px;max-width:760px;line-height:1.5}",
      ".rx-stance-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:18px}",
      ".rx-stance{font-size:13px;font-weight:800;padding:5px 14px;border-radius:999px;border:1px solid;letter-spacing:.01em}",
      ".rx-stance-watch{color:var(--up);background:color-mix(in srgb,var(--up) 13%,transparent);border-color:color-mix(in srgb,var(--up) 34%,transparent)}",
      ".rx-stance-aside{color:var(--warn);background:color-mix(in srgb,var(--warn) 13%,transparent);border-color:color-mix(in srgb,var(--warn) 34%,transparent)}",
      ".rx-stance-note{font-size:12px;color:var(--muted)}",
      ".rx-hero-row{display:flex;gap:16px;flex-wrap:wrap;align-items:stretch}",
      /* score block (glass, glow keyed to hero color) */
      ".rx-score{flex:0 0 auto;min-width:290px;max-width:340px;padding:16px 18px 14px;border-radius:16px;" +
        "background:linear-gradient(150deg,var(--panel) 0%,color-mix(in srgb,var(--hc,var(--warn)) 6%,var(--panel)) 100%);" +
        "border:1px solid color-mix(in srgb,var(--hc,var(--warn)) 22%,var(--line));" +
        "box-shadow:0 0 44px -14px color-mix(in srgb,var(--hc,var(--warn)) 30%,transparent)}",
      ".rx-score-top{display:flex;align-items:center;gap:12px}",
      ".rx-score-num{font-size:58px;font-weight:900;line-height:.9;letter-spacing:-.04em;color:var(--hc,var(--warn));" +
        "text-shadow:0 0 44px color-mix(in srgb,var(--hc,var(--warn)) 40%,transparent);font-variant-numeric:tabular-nums}",
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
      ".rx-sec-sub{font-size:12.5px;color:var(--muted);margin:0 0 12px;max-width:760px;line-height:1.5}",
      /* lead card */
      ".rx-lead{margin-top:20px;border-radius:16px;overflow:hidden;border:1px solid color-mix(in srgb,var(--up) 26%,var(--line));" +
        "background:linear-gradient(150deg,var(--panel) 0%,color-mix(in srgb,var(--up) 6%,var(--panel)) 100%);" +
        "box-shadow:0 0 40px -18px color-mix(in srgb,var(--up) 34%,transparent)}",
      ".rx-lead-tag{font-size:11px;font-weight:800;letter-spacing:.08em;color:var(--up);padding:10px 18px 0}",
      ".rx-lead-body{display:flex;gap:18px;padding:8px 18px 18px;flex-wrap:wrap}",
      ".rx-lead-main{flex:1;min-width:280px}",
      ".rx-lead-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}",
      ".rx-lead-name{font-size:21px;font-weight:800;margin:0;letter-spacing:-.01em}",
      ".rx-lead-gist{font-size:14px;line-height:1.55;margin:0 0 10px;color:var(--text)}",
      ".rx-lead-side{flex:0 0 230px;max-width:260px;display:flex;flex-direction:column;gap:9px;" +
        "padding:14px;border-radius:12px;background:color-mix(in srgb,var(--up) 5%,var(--panel));border:1px solid color-mix(in srgb,var(--up) 16%,var(--line))}",
      ".rx-lead-side-note{font-size:11.5px;color:var(--muted);line-height:1.5}",
      /* cards */
      ".rx-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}",
      ".rx-card{position:relative;border:1px solid var(--line);border-top:2px solid var(--cc,var(--line));border-radius:12px;" +
        "padding:13px 15px;background:var(--panel2);transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease}",
      "@media(hover:hover){.rx-card:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--cc,var(--line)) 40%,var(--line));" +
        "box-shadow:0 12px 30px -18px color-mix(in srgb,var(--cc,var(--line)) 60%,transparent)}}",
      ".rx-card-top{display:flex;align-items:center;gap:8px;margin-bottom:7px;flex-wrap:wrap}",
      ".rx-card-name{font-size:14.5px;font-weight:700;margin:0;letter-spacing:-.01em}",
      ".rx-card-gist{font-size:12.5px;color:var(--muted);line-height:1.5;margin:0 0 8px}",
      ".rx-badge{font-size:10.5px;font-weight:700;padding:2px 9px;border-radius:999px;white-space:nowrap;" +
        "color:var(--bc,var(--muted));background:color-mix(in srgb,var(--bc,var(--muted)) 13%,transparent);border:1px solid color-mix(in srgb,var(--bc,var(--muted)) 32%,transparent)}",
      ".rx-badge-up{--bc:var(--up)}",
      ".rx-badge-sm{font-size:10px;padding:1px 7px}",
      ".rx-srcs{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px}",
      ".rx-src{font-size:10.5px;font-weight:600;padding:2px 8px;border-radius:6px;color:var(--sc,var(--muted));" +
        "background:color-mix(in srgb,var(--sc,var(--muted)) 9%,transparent);border:1px solid color-mix(in srgb,var(--sc,var(--muted)) 26%,transparent)}",
      ".rx-src b{font-size:9px}",
      ".rx-metrics{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:9px}",
      ".rx-metric{font-size:11.5px;color:var(--text);padding:3px 9px;border-radius:7px;background:color-mix(in srgb,var(--muted) 9%,transparent);border:1px solid var(--line)}",
      ".rx-metric-up{color:var(--up);background:color-mix(in srgb,var(--up) 10%,transparent);border-color:color-mix(in srgb,var(--up) 26%,transparent)}",
      ".rx-card-foot{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:2px}",
      ".rx-stance-mini{font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px}",
      ".rx-stance-mini.rx-stance-watch{color:var(--up);background:color-mix(in srgb,var(--up) 12%,transparent)}",
      ".rx-stance-mini.rx-stance-aside{color:var(--warn);background:color-mix(in srgb,var(--warn) 12%,transparent)}",
      ".rx-trail{display:inline-flex;gap:2px;align-items:center}",
      ".rx-tickers{font-size:10.5px;color:var(--muted);font-family:var(--font-mono);line-height:1.6;margin-top:6px}",
      ".rx-mini{font-size:11px;font-weight:600;color:var(--link);background:none;border:none;cursor:pointer;padding:2px 4px;margin-left:auto}",
      ".rx-mini~.rx-mini{margin-left:0}",
      ".rx-exp,.rx-news,.rx-nexp{display:none;margin-top:8px;padding-top:8px;border-top:1px solid var(--line);font-size:11px;color:var(--muted);font-family:var(--font-mono);line-height:1.6}",
      ".rx-exp.rx-open,.rx-news.rx-open,.rx-nexp.rx-open{display:block}",
      ".rx-hl{display:block;font-family:var(--font-ui);color:var(--link);text-decoration:none;font-size:11.5px;line-height:1.5;margin-bottom:4px}",
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
      ".rx-nrow{display:flex;align-items:center;gap:9px;padding:7px 9px;border-radius:7px;cursor:pointer;border:1px solid transparent;font-size:12.5px}",
      ".rx-nrow:hover{background:var(--panel2);border-color:var(--line)}",
      ".rx-ntk{font-family:var(--font-mono);font-weight:800;min-width:56px}",
      ".rx-nbasket{flex:1;min-width:0;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".rx-nrs{font-family:var(--font-mono);font-weight:700;min-width:44px;text-align:right}",
      /* honesty */
      ".rx-honesty{margin-top:28px;padding:20px 20px 16px;border-radius:14px;border:1px solid var(--line);background:var(--panel)}",
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
      /* brain */
      ".rx-brain{margin-top:18px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:color-mix(in srgb,var(--info) 4%,var(--panel))}",
      ".rx-brain-off{background:var(--panel)}",
      ".rx-brain-head{font-size:14px;font-weight:800;margin-bottom:8px}",
      ".rx-brain-rot{font-size:12.5px;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:8px 11px;margin-bottom:9px}",
      ".rx-brain-row{padding:8px 0;border-bottom:1px solid var(--line)}",
      ".rx-brain-badge{font-size:10.5px;font-weight:800;padding:2px 9px;border-radius:999px;border:1px solid var(--bc,var(--muted));color:var(--bc,var(--muted));margin-right:8px}",
      ".rx-brain-why{font-size:12px;color:var(--muted);line-height:1.55;margin:5px 0 0}",
      ".rx-cav{font-size:10.5px;color:var(--muted);line-height:1.5;margin:10px 0 0}",
      /* footer caveat */
      ".rx-foot{font-size:11px;color:var(--muted);line-height:1.55;margin-top:20px;padding-top:14px;border-top:1px solid var(--line);max-width:900px}",
      /* tooltips (reuse macro data-tip convention via title fallback: keep simple) */
      "[data-tip-en]{position:relative}",
      /* mobile */
      "@media(max-width:640px){",
      ".rx-hero{padding:18px 2px 14px}",
      ".rx-score{min-width:0;max-width:none;width:100%}",
      ".rx-lead-side{flex-basis:100%;max-width:none}",
      ".rx-cards{grid-template-columns:1fr}",
      ".rx-nq,.rx-nsel{width:100%}",
      ".rx-t-stance{display:none}",
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
      h += heroHTML(radar, enriched);

      // Lead: top activity-ahead theme (the genuinely watch-worthy one)
      if (posDivs.length) h += leadHTML(posDivs[0]);

      // Lane: activity ahead of price (rest, if the lead took the first)
      var posRest = posDivs.slice(posDivs.length ? 1 : 0);
      if (posRest.length) {
        h += '<section class="rx-sec"><div class="rx-sec-head"><h2 class="rx-sec-title">🟢 ' + bi("More activity ahead of price", "更多活动领先价格") +
          '</h2><span class="rx-sec-cnt">' + posRest.length + "</span></div>" +
          '<p class="rx-sec-sub">' + bi("Real work accelerating faster than the tape. Watch for price to catch up — it may not.", "真实活动加速快于价格。留意价格能否跟上 —— 也可能不会。") + "</p>" +
          '<div class="rx-cards">' + posRest.slice(0, 6).map(function (f, i) { return laneCard(f, i); }).join("") + "</div></section>";
      }

      // Lane: price ahead of activity
      h += '<section class="rx-sec"><div class="rx-sec-head"><h2 class="rx-sec-title">🟠 ' + bi("Price ahead of activity", "价格领先活动") +
        '</h2><span class="rx-sec-cnt">' + negDivs.length + "</span></div>" +
        '<p class="rx-sec-sub">' + bi("The tape is leading while the real-activity engine underneath has cooled. These moves may be running on fumes — stand aside.", "价格在领先，而底层真实活动已降温。这些走势可能已是强弩之末 —— 旁观为宜。") + "</p>";
      if (!negDivs.length) {
        h += '<div class="rx-calm">' + bi("None today — where price leads, real activity is keeping up.", "今日没有 —— 价格领先之处，真实活动仍在跟上。") + "</div>";
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
        '<button class="rx-fchip" data-f="pos">' + bi("Activity ahead", "活动领先") + "</button>" +
        '<button class="rx-fchip" data-f="neg">' + bi("Price ahead", "价格领先") + "</button>" +
        '<button class="rx-fchip" data-f="conf">' + bi("Both agree", "同步") + "</button>" +
        '<button class="rx-fchip" data-f="quiet">' + bi("In line", "平静") + " (" + quietN + ")</button>" +
        "</div>";
      h += '<div style="overflow-x:auto"><table class="rx-tbl"><thead><tr>' +
        '<th data-col="name">' + bi("Theme", "主题") + '<span class="rx-so">↕</span></th>' +
        '<th data-col="accel" data-tip-en="How fast real activity is moving vs a year ago — 1.0× is flat, above is speeding up, below is cooling" data-tip-zh="真实活动相对去年的变化速度 —— 1.0× 为持平，高于为加速，低于为降温">' + bi("Real activity", "真实活动") + '<span class="rx-so">↕</span></th>' +
        '<th data-col="rel60" data-tip-en="Theme price return vs the market over the last 60 days" data-tip-zh="主题价格相对大盘的60日收益">' + bi("Price vs mkt", "相对大盘") + '<span class="rx-so">↕</span></th>' +
        '<th>' + bi("14d", "14日") + "</th>" +
        '<th data-col="state">' + bi("Read", "解读") + '<span class="rx-so">↕</span></th>' +
        '<th>' + bi("Stance", "立场") + "</th>" +
        '</tr></thead><tbody id="rx-tbody"></tbody></table></div>';
      h += "</div>";
      // stocks pane
      h += '<div class="rx-pane" id="rx-pane-stocks">';
      h += '<div class="rx-nctrl">' +
        '<input class="rx-nq" id="rx-nq" placeholder="' + (document.documentElement.getAttribute("data-lang") === "zh" ? "搜索代码…" : "Search ticker…") + '">' +
        '<select class="rx-nsel" id="rx-nstate">' +
          '<option value="all">' + bi("All reads", "全部解读") + "</option>" +
          '<option value="POSITIVE_DIVERGENCE">' + bi("Activity ahead", "活动领先") + "</option>" +
          '<option value="NEGATIVE_DIVERGENCE">' + bi("Price ahead", "价格领先") + "</option>" +
          '<option value="CONFIRMED_UP">' + bi("Both rising", "同步上行") + "</option>" +
          '<option value="QUIET">' + bi("In line", "平静") + "</option>" +
        "</select>" +
        '<select class="rx-nsel" id="rx-nbasket"><option value="all">' + bi("All themes", "全部主题") + "</option></select>" +
        "</div>";
      h += '<div id="rx-nrows"></div>';
      h += '<button class="rx-showmore" id="rx-nmore">' + bi("Show more", "显示更多") + "</button>";
      h += "</div>";
      h += "</div>"; // board

      // Honesty + brain + footer
      h += honestyHTML(ic, track);
      h += brainRx(brain);
      var cav = (radar.caveats || [])[0];
      if (cav) h += '<p class="rx-foot">' + bi(cav, (radar.caveats_zh || [])[0] || cav) + "</p>";

      h += "</div>"; // rx-wrap
      mount.innerHTML = h;

      // ── Wire interactions ──────────────────────────────────────────────────
      // card expand / news toggles (event delegation)
      mount.addEventListener("click", function (e) {
        var t = e.target.closest("[data-exp],[data-news],[data-nexp]");
        if (!t) return;
        var id = t.getAttribute("data-exp") || t.getAttribute("data-news") || t.getAttribute("data-nexp");
        if (!id) return;
        var suffix = t.hasAttribute("data-news") ? "-news" : "";
        var el = byId(id + suffix) || byId(id);
        if (el) el.classList.toggle("rx-open");
      });

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
    });
  }; // end renderRadarFull

  // Legacy no-op guards (old rendered pages call these; full mode handles it all now)
  window.renderRadarLifecycle = function () {};
  window.renderTickerRadar = function () {};

})();

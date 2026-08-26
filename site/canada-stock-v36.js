/* Canada Stock Dashboard V3.7 — presentation-only composition.
   SOL-STOCK-DASH-V37-CA-FUNCTIONAL-COMPLETENESS-20260825

   This file owns no ranking, signal, quote, lifecycle, entitlement, or persistence
   semantics. It re-composes already-published Canada stock surfaces and reads the
   existing Canada thematic-basket and sector-pulse artifacts. If anything required
   is unavailable, the legacy page remains visible and functional. */
(function () {
  "use strict";

  var PATH_RE = /(^|\/)canada_stocks\.html$/;
  if (!PATH_RE.test(location.pathname) || window.__mmCanadaStockV36) return;
  window.__mmCanadaStockV36 = true;

  var FONT_UI = "var(--font-ui,-apple-system,BlinkMacSystemFont,Inter,\"Segoe UI\",Roboto,sans-serif)";
  var state = { source: "top", view: "grid", filter: null, themes: [], sectors: [], cards: [], rows: [] };
  var rowsByTicker = Object.create(null);
  var tableObserver = null;

  /* Owner-native Act-Now lane vocabulary (templates/canada.html.j2:854-996,
     `_ca_anlane(...)` title_en/title_zh). This is the single source for both
     collectSectors() (change 2) and the group-action band in openModal()
     (change 4) — never invent parallel lane vocabulary. */
  var LANE_DEFS = [
    { sel: "#anv2-buy", en: "Buy Now", zh: "立即买入", tone: "buy" },
    { sel: "#anv2-pull", en: "In Favour", zh: "看好", tone: "near" },
    { sel: "#anv2-bot", en: "Bottoming Watch", zh: "洗盘观察", tone: "wait" },
    { sel: "#anv2-red", en: "Reduce / Avoid", zh: "减仓 / 回避", tone: "avoid" }
  ];

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];
    });
  }
  function bi(en, zh) {
    return '<span class="l-en">' + esc(en) + '</span><span class="l-zh">' + esc(zh || en) + '</span>';
  }
  function dual(el) {
    if (!el) return { en: "", zh: "" };
    var en = qs(".l-en", el), zh = qs(".l-zh", el);
    return { en: (en ? en.textContent : el.textContent || "").trim(), zh: (zh ? zh.textContent : (en ? en.textContent : el.textContent || "")).trim() };
  }
  function ticker(value) { return String(value || "").trim().toUpperCase(); }
  function boardDate(raw) {
    if (!raw || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return { en: raw || "—", zh: raw || "—" };
    var p = raw.split("-").map(Number), d = new Date(Date.UTC(p[0], p[1] - 1, p[2], 12));
    return { en: new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(d), zh: p[0] + "年" + p[1] + "月" + p[2] + "日" };
  }
  function liveDate() {
    var d = new Date();
    return { en: new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(d), zh: d.getFullYear() + "年" + (d.getMonth() + 1) + "月" + d.getDate() + "日" };
  }

  function parseRows() {
    var el = qs("#stocktable-data");
    if (!el) return null;
    try {
      var payload = JSON.parse(el.textContent || "{}");
      state.rows = Array.isArray(payload.rows) ? payload.rows.slice() : [];
      state.rows.forEach(function (row) { if (row.ticker) rowsByTicker[ticker(row.ticker)] = row; });
      return payload;
    } catch (e) { return null; }
  }

  function collectCards() {
    var host = qs("#standouts .cards");
    if (!host) return [];
    var cards = qsa(".pvcard", host);
    cards.forEach(function (card, i) {
      /* V3 owns inventory visibility; legacy show-more state must not survive the move. */
      card.classList.remove("sm-hidden");
      card.hidden = false;
      card.style.removeProperty("display");
      card.classList.toggle("ca-v36-top-pick", i < 5);
      card.setAttribute("data-ca-v36-order", String(i + 1));
    });
    return cards;
  }

  function sectorMembers(name) {
    return new Set(state.rows.filter(function (r) { return r.sector === name; }).map(function (r) { return ticker(r.ticker); }));
  }
  function collectSectors() {
    var out = [], seen = Object.create(null);
    LANE_DEFS.forEach(function (def) {
      qsa(def.sel + " .anv2-row").forEach(function (node) {
        var link = qs(".anv2-name-link", node), name = dual(qs(".anv2-name", node));
        var href = link ? link.getAttribute("href") || "" : "", m = href.match(/sectors\/([^/.]+)\.html/i);
        var id = m ? ticker(m[1]) : name.en;
        if (!name.en || seen[id]) return;
        seen[id] = true;
        var members = sectorMembers(name.en), leaders = Array.from(members).slice(0, 3);
        out.push({ kind: "sector", rank: out.length + 1, id: id, name: name,
          stance: { en: def.en, zh: def.zh }, tone: def.tone, count: members.size,
          members: members, leaders: leaders, href: href });
      });
    });
    return out;
  }

  function tone(reco) {
    if (reco === "enter" || reco === "accumulate") return "buy";
    if (reco === "hold") return "near";
    if (reco === "trim") return "wait";
    return "avoid";
  }
  function stance(reco, th) {
    return { en: th.reco_en || ({enter:"Enter",accumulate:"Accumulate",hold:"Hold",trim:"Trim",avoid:"Avoid"}[reco] || reco || "Neutral"),
      zh: th.reco_zh || ({enter:"入场",accumulate:"加仓",hold:"持有",trim:"减仓",avoid:"回避"}[reco] || reco || "中性") };
  }
  function collectThemes(basketPayload, pulsePayload) {
    var ranked = pulsePayload && Array.isArray(pulsePayload.themes) ? pulsePayload.themes.slice() : [];
    if (!ranked.length) {
      var embedded = basketPayload && basketPayload.theme_intel || {};
      ranked = Array.isArray(embedded.themes) ? embedded.themes.slice() : [];
    }
    var basketMap = Object.create(null), baskets = basketPayload && basketPayload.baskets || [];
    if (Array.isArray(baskets)) baskets.forEach(function (b) { if (b && b.id) basketMap[b.id] = b; });
    else if (baskets && typeof baskets === "object") Object.keys(baskets).forEach(function (k) { basketMap[k] = baskets[k]; });
    /* Rank is owner-published by sector_pulse/theme_intel. The page never re-scores. */
    ranked.sort(function (a, b) { return (a.rank || 9999) - (b.rank || 9999); });
    return ranked.map(function (th, idx) {
      var basket = basketMap[th.id] || {};
      /* Current Canada basket artifacts publish member identity as `symbol`.
         `ticker` remains accepted for older/alternate regional producers. */
      var members = new Set((basket.members || []).map(function (m) { return ticker(typeof m === "string" ? m : (m.ticker || m.symbol)); }).filter(Boolean));
      var leaders = (((th.leadership || {}).top) || []).map(function (x) { return ticker(x.ticker || x.symbol || x.t); }).filter(Boolean).slice(0, 3);
      if (!leaders.length) leaders = Array.from(members).slice(0, 3);
      return { kind: "theme", rank: th.rank || idx + 1, id: th.id,
        name: { en: th.name || th.id, zh: th.name_zh || th.name || th.id },
        stance: stance(th.reco, th), tone: tone(th.reco), count: th.n_members != null ? th.n_members : members.size,
        members: members, leaders: leaders };
    });
  }

  function injectCss() {
    if (qs("#ca-v36-css")) return;
    var css = document.createElement("style");
    css.id = "ca-v36-css";
    css.textContent = [
      "body.page-canada.ca-v36-mounted{font-family:" + FONT_UI + ";background:var(--bg);color:var(--text)}",
      "body.page-canada.ca-v36-mounted>.panel{display:none!important}",
      ".ca-v36{width:min(1480px,calc(100% - 32px));margin:22px auto 44px;font-family:" + FONT_UI + ";font-size:16.2px;line-height:1.48}",
      ".ca-v36 *{box-sizing:border-box}.ca-v36 button,.ca-v36 input,.ca-v36 select{font-family:inherit}",
      ".ca-v36-head{display:flex;align-items:center;gap:12px;min-height:66px;margin-bottom:14px}.ca-v36-head h1{margin:0;font-size:31.5px;line-height:1.05;font-weight:650;letter-spacing:-.03em}.ca-v36-head-spacer{flex:1}",
      ".ca-v36-chip,.ca-v36-live{height:37px;display:inline-flex;align-items:center;gap:7px;padding:0 13px;border:1px solid var(--line);border-radius:999px;background:var(--panel);color:var(--muted);font-size:12px;font-weight:600;white-space:nowrap}.ca-v36-live-dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 9px color-mix(in srgb,var(--ok) 55%,transparent)}.ca-v36-live b{color:var(--ok)}",
      ".ca-v36-leading{display:flex;align-items:center;gap:8px;min-height:51px;margin-bottom:14px;padding:8px 11px 8px 14px;border:1px solid var(--line);border-radius:12px;background:color-mix(in srgb,var(--panel) 78%,transparent);box-shadow:var(--card-shadow)}.ca-v36-leading-k{color:var(--muted);font-size:11.2px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;white-space:nowrap}.ca-v36-leading-btn{height:35px;display:inline-flex;align-items:center;gap:7px;min-width:0;padding:0 11px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--text);font-size:13px;font-weight:600;cursor:pointer;transition:.15s ease}.ca-v36-leading-btn:hover{transform:translateY(-1px);border-color:color-mix(in srgb,var(--text) 30%,var(--line))}.ca-v36-leading-btn small{color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}.ca-v36-leading-fresh{margin-left:auto;color:var(--muted);font-size:12.2px;white-space:nowrap}",
      ".ca-v36-panel{margin-bottom:14px;border:1px solid var(--line);border-radius:13px;background:var(--panel);box-shadow:var(--card-shadow);overflow:hidden}.ca-v36-sec-hd{min-height:54px;display:flex;align-items:center;gap:10px;padding:0 15px;border-bottom:1px solid var(--line)}.ca-v36-sec-hd h2{margin:0;font-size:18px;font-weight:650;letter-spacing:-.012em}.ca-v36-sec-spacer{flex:1}.ca-v36-link{color:var(--ink-link,var(--link));font-size:13px;font-weight:600;text-decoration:none}.ca-v36-link:hover{text-decoration:underline}",
      ".ca-v36-lead-cols{display:grid;grid-template-columns:1fr 1fr}.ca-v36-lead-col+.ca-v36-lead-col{border-left:1px solid var(--line)}.ca-v36-lead-col-h{display:flex;justify-content:space-between;padding:11px 14px 10px;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}",
      ".ca-v36-lead-row{position:relative;width:100%;min-height:58px;display:grid;grid-template-columns:30px minmax(0,1fr) auto 34px;align-items:center;gap:9px;padding:10px 14px;border:0;border-top:1px solid color-mix(in srgb,var(--line) 72%,transparent);background:transparent;color:inherit;text-align:left;cursor:pointer;overflow:hidden;transition:.15s ease}.ca-v36-lead-row:after{content:\"\";position:absolute;left:0;bottom:0;width:var(--breadth,8%);height:1px;background:color-mix(in srgb,var(--link) 44%,transparent);opacity:.5}.ca-v36-lead-row:hover,.ca-v36-lead-row.is-active{background:color-mix(in srgb,var(--link) 6%,transparent)}.ca-v36-rank{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.5px}.ca-v36-lead-name{display:block;font-size:14.7px;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ca-v36-leaders{display:block;margin-top:3px;color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ca-v36-count{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.7px;text-align:right}",
      ".ca-v36-stance{height:24px;display:inline-flex;align-items:center;padding:0 9px;border:1px solid currentColor;border-radius:6px;font-size:10px;font-weight:750;text-transform:uppercase;white-space:nowrap}.ca-v36-stance.buy{color:var(--ink-up,var(--up))}.ca-v36-stance.near{color:var(--ink-link,var(--link))}.ca-v36-stance.wait{color:var(--ink-warn,var(--warn))}.ca-v36-stance.avoid{color:var(--ink-down,var(--down))}",
      ".ca-v36-expand-wrap{display:flex;justify-content:center;padding:9px 12px 11px;border-top:1px solid var(--line);background:color-mix(in srgb,var(--panel2) 32%,transparent)}.ca-v36-expand{height:35px;padding:0 14px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--text);font-size:12.5px;font-weight:650;cursor:pointer}.ca-v36-expand:hover{border-color:color-mix(in srgb,var(--text) 30%,var(--line));transform:translateY(-1px)}",
      ".ca-v36-controls{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.ca-v36-seg{display:inline-flex;gap:3px;padding:3px;border:1px solid var(--line);border-radius:9px;background:var(--panel2)}.ca-v36-seg button{height:36px;padding:0 14px;border:1px solid transparent;border-radius:7px;background:transparent;color:var(--muted);font-size:13.1px;font-weight:650;cursor:pointer}.ca-v36-seg button[aria-selected=true]{background:var(--panel);border-color:var(--line);color:var(--text);box-shadow:0 1px 4px rgba(0,0,0,.12)}.ca-v36-result{color:var(--muted);font-size:12px;white-space:nowrap}.ca-v36-filter{display:none;height:32px;align-items:center;padding:0 10px;border:1px solid color-mix(in srgb,var(--link) 35%,var(--line));border-radius:999px;background:color-mix(in srgb,var(--link) 7%,transparent);color:var(--text);font-size:12px;cursor:pointer}.ca-v36-filter.is-on{display:inline-flex}",
      ".ca-v36-card-grid[hidden]{display:none!important}.ca-v36-card-grid .pvcard[hidden]{display:none!important}" +
      ".ca-v36-card-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;padding:14px}.ca-v36-card-grid .pvcard{min-width:0;height:100%;font-family:" + FONT_UI + ";transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}.ca-v36-card-grid .pvcard:hover{transform:translateY(-2px)}.ca-v36-card-grid .sm-hidden{display:flex!important}.ca-v36-card-grid .pv-chart svg{height:82px!important}.ca-v36-card-grid .pv-bd{padding:14px 14px 12px!important}.ca-v36-card-grid .pv-tk{font-family:" + FONT_UI + "!important;font-size:16.7px!important;font-weight:700!important;letter-spacing:-.012em!important}.ca-v36-card-grid .pv-nm{font-family:" + FONT_UI + "!important;font-size:12.5px!important}.ca-v36-card-grid .pv-ind{font-size:11.1px!important}.ca-v36-card-grid .pv-edge{font-family:" + FONT_UI + "!important}.ca-v36-card-grid .pv-edn{font-size:16px!important}.ca-v36-card-grid .nb-px.pv-px{font-family:" + FONT_UI + "!important;font-size:15.8px!important;font-weight:750!important}.ca-v36-card-grid .nb-chg.pv-chg{font-family:" + FONT_UI + "!important;font-size:13.4px!important;font-weight:750!important}.ca-v36 .nb-chg.up,.ca-v36-table .nb-chg.up{color:var(--ok)!important}.ca-v36 .nb-chg.down,.ca-v36-table .nb-chg.down{color:var(--act)!important}.ca-v36-card-grid .pv-chip{font-size:10.8px!important}.ca-v36-card-grid .pv-life-w,.ca-v36-card-grid .pv-stl{font-size:11.1px!important}.ca-v36-card-grid .pv-zn{min-height:42px!important;font-size:11.6px!important}.ca-v36-card-grid .pv-znr,.ca-v36-card-grid .pv-znm{font-family:" + FONT_UI + "!important;font-size:11.8px!important}",
      ".ca-v36-card-grid .ca-v36-top-pick{border-color:color-mix(in srgb,var(--link) 20%,var(--line));box-shadow:0 0 0 1px color-mix(in srgb,var(--link) 8%,transparent),0 0 24px -16px color-mix(in srgb,var(--link) 42%,transparent),0 8px 24px -20px rgba(0,0,0,.55)}html[data-theme=light] .ca-v36-card-grid .ca-v36-top-pick{background:#fff;border-color:color-mix(in srgb,var(--link) 18%,var(--line));box-shadow:0 0 0 1px color-mix(in srgb,var(--link) 7%,transparent),0 10px 26px -22px color-mix(in srgb,var(--link) 30%,transparent)}.ca-v36-empty{grid-column:1/-1;padding:36px 16px;text-align:center;color:var(--muted);font-size:13px}.ca-v36-empty-switch{display:block;margin:10px auto 0;height:31px;padding:0 13px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--text);font-size:11.8px;font-weight:650;cursor:pointer}.ca-v36-empty-switch:hover{border-color:color-mix(in srgb,var(--text) 30%,var(--line));transform:translateY(-1px)}",
      ".ca-v36-table{padding:12px 14px 15px}.ca-v36-table[hidden]{display:none!important}.ca-v36-table #stocktable-wrap{display:block!important}.ca-v36-table .stf-row,.ca-v36-table .stf-controls{font-family:" + FONT_UI + "!important}.ca-v36-table :is(input,select,button){min-height:38px;font-size:12.8px!important}.ca-v36-table .st-table{font-family:" + FONT_UI + "!important;font-size:13.3px!important}.ca-v36-table .st-table th{font-size:11px!important;padding:11px 10px!important}.ca-v36-table .st-table td{padding:11px 10px!important}.ca-v36-table .st-table td:nth-child(2) b{font-family:" + FONT_UI + "!important;font-size:13.8px}.ca-v36-table-live{display:inline-flex;align-items:baseline;gap:8px;white-space:nowrap;font-family:" + FONT_UI + "}.ca-v36-table-live .nb-px{font-size:14.8px;font-weight:700}.ca-v36-table-live .nb-chg{font-size:12.7px;font-weight:750}.ca-v36-table tr.ca-v36-hidden{display:none!important}",
      ".ca-v36-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:11px 14px}.ca-v36-tools b{font-size:12.8px;margin-right:2px}.ca-v36-tool{height:37px;display:inline-flex;align-items:center;padding:0 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--muted);font-size:12.1px;font-weight:600;text-decoration:none}.ca-v36-tool:hover{color:var(--text);border-color:color-mix(in srgb,var(--text) 28%,var(--line));transform:translateY(-1px)}",
      /* Evidence & Record — the moved `.trk` chip keeps its own box (border/
         background/padding) from its page-level stylesheet; this only trims
         the outer wrapping and matches the ca-v36 font stack. */
      ".ca-v36-evidence-body{display:flex;justify-content:center;padding:13px 14px 15px;font-family:" + FONT_UI + "}.ca-v36-evidence-body .trk{margin:0;padding:9px 12px;font-family:" + FONT_UI + "}",
      /* Group-action band (change 4) — four owner lane groups above the two
         existing ranking panes inside the Expand-leadership modal. */
      ".ca-v36-modal-lanes{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.ca-v36-modal-lane{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel2)}.ca-v36-modal-lane-hd{padding:9px 10px;border-bottom:1px solid var(--line);border-top:2px solid currentColor;font-size:11.3px;font-weight:750;text-transform:uppercase;letter-spacing:.02em}.ca-v36-modal-lane-hd.buy{color:var(--ink-up,var(--up))}.ca-v36-modal-lane-hd.near{color:var(--ink-link,var(--link))}.ca-v36-modal-lane-hd.wait{color:var(--ink-warn,var(--warn))}.ca-v36-modal-lane-hd.avoid{color:var(--ink-down,var(--down))}.ca-v36-modal-lane-row{display:flex;flex-direction:column;gap:2px;padding:8px 10px;border-top:1px solid color-mix(in srgb,var(--line) 70%,transparent);cursor:pointer}.ca-v36-modal-lane-hd+.ca-v36-modal-lane-row{border-top:0}.ca-v36-modal-lane-row:not(.ca-v36-modal-lane-empty):hover{background:color-mix(in srgb,var(--link) 6%,transparent)}.ca-v36-modal-lane-row.ca-v36-modal-lane-empty{color:var(--muted);cursor:default;text-align:center}.ca-v36-modal-lane-name{font-size:12.6px;font-weight:650}.ca-v36-modal-lane-meta{color:var(--muted);font-size:10.8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".ca-v36-modal{position:fixed;inset:0;z-index:2147481000;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(4,7,12,.62);backdrop-filter:blur(8px)}.ca-v36-modal.is-open{display:flex}.ca-v36-modal-card{width:min(1180px,calc(100vw - 32px));max-height:min(820px,calc(100vh - 36px));display:flex;flex-direction:column;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:0 30px 90px rgba(0,0,0,.5);overflow:hidden}html[data-theme=light] .ca-v36-modal{background:rgba(50,64,90,.22)}html[data-theme=light] .ca-v36-modal-card{box-shadow:0 24px 70px rgba(20,32,64,.2)}.ca-v36-modal-hd{min-height:56px;display:flex;align-items:center;padding:0 15px;border-bottom:1px solid var(--line)}.ca-v36-modal-hd h3{margin:0;font-size:19px;font-weight:650}.ca-v36-modal-x{margin-left:auto;width:36px;height:36px;border:1px solid var(--line);border-radius:9px;background:var(--panel2);color:var(--text);font-size:21px;cursor:pointer}.ca-v36-modal-body{overflow:auto;padding:14px}.ca-v36-modal-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ca-v36-modal-pane{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel2)}.ca-v36-modal-pane h4{margin:0;padding:11px 12px;border-bottom:1px solid var(--line);font-size:13px}.ca-v36-modal-table{width:100%;border-collapse:collapse;font-size:12.8px}.ca-v36-modal-table th{padding:9px 10px;color:var(--muted);font-size:10.8px;text-align:left;border-bottom:1px solid var(--line)}.ca-v36-modal-table td{padding:10px;border-bottom:1px solid color-mix(in srgb,var(--line) 70%,transparent)}.ca-v36-modal-table tbody tr{cursor:pointer}.ca-v36-modal-table tbody tr:hover{background:color-mix(in srgb,var(--link) 6%,transparent)}.ca-v36-modal-table .num,.ca-v36-modal-table .leaders{color:var(--muted)}",
      "@media(max-width:1200px){.ca-v36-card-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.ca-v36-modal-lanes{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:900px){.ca-v36-head{flex-wrap:wrap}.ca-v36-head-spacer{display:none}.ca-v36-lead-cols,.ca-v36-modal-grid{grid-template-columns:1fr}.ca-v36-lead-col+.ca-v36-lead-col{border-left:0;border-top:1px solid var(--line)}.ca-v36-card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.ca-v36{width:min(100% - 20px,680px);margin-top:12px;font-size:15.8px}.ca-v36-head{gap:8px}.ca-v36-head h1{width:100%;font-size:27.5px}.ca-v36-leading{flex-wrap:wrap}.ca-v36-leading-k{width:100%}.ca-v36-leading-btn{flex:1;min-width:140px}.ca-v36-leading-fresh{width:100%;margin-left:0}.ca-v36-sec-hd{align-items:flex-start;flex-wrap:wrap;padding:11px 12px}.ca-v36-sec-hd h2{font-size:17px}.ca-v36-controls{width:100%}.ca-v36-card-grid{grid-template-columns:1fr;padding:10px;gap:10px}.ca-v36-card-grid .pv-tk{font-size:16.3px!important}.ca-v36-card-grid .nb-px.pv-px{font-size:15.5px!important}.ca-v36-card-grid .nb-chg.pv-chg{font-size:13.1px!important}.ca-v36-modal{padding:8px}.ca-v36-modal-card{width:100%;max-height:calc(100vh - 16px)}.ca-v36-modal-lanes{grid-template-columns:1fr}.ca-v36-evidence-body{padding:11px 10px 13px}}"
    ].join("\n");
    document.head.appendChild(css);
  }

  function leadRow(x, max) {
    var breadth = Math.max(8, Math.round(((x.count || 0) / Math.max(1, max)) * 100));
    return '<button class="ca-v36-lead-row" data-ca-lead-kind="' + x.kind + '" data-ca-lead-id="' + esc(x.id) + '" style="--breadth:' + breadth + '%"><span class="ca-v36-rank">' + String(x.rank).padStart(2, "0") + '</span><span><span class="ca-v36-lead-name">' + bi(x.name.en, x.name.zh) + '</span><span class="ca-v36-leaders">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + '</span></span><span class="ca-v36-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span><span class="ca-v36-count">' + (x.count || 0) + '</span></button>';
  }
  function leadColumn(items, kind) {
    var top = items.slice(0, 5), max = Math.max.apply(Math, [1].concat(top.map(function (x) { return x.count || 0; })));
    return '<div class="ca-v36-lead-col"><div class="ca-v36-lead-col-h"><span>' + (kind === "theme" ? bi("Themes", "主题") : bi("Sectors", "板块")) + '</span><span>' + (kind === "theme" ? bi("Names", "成分") : bi("Board", "榜单")) + '</span></div>' + (top.length ? top.map(function (x) { return leadRow(x, max); }).join("") : '<div class="ca-v36-empty">' + bi("Ranking unavailable", "排名暂不可用") + '</div>') + '</div>';
  }
  function renderLeadership() {
    var host = qs("#ca-v36-lead-cols");
    if (host) host.innerHTML = leadColumn(state.themes, "theme") + leadColumn(state.sectors, "sector");
    markLeadership();
  }
  function renderLeading() {
    var host = qs("#ca-v36-leading"); if (!host) return;
    var th = state.themes[0], sec = state.sectors[0], fresh = state.cards.filter(function (c) { return !!qs(".pv-mk-new", c); }).length;
    var html = '<span class="ca-v36-leading-k">' + bi("Leading now", "当前领先") + '</span>';
    if (th) html += '<button class="ca-v36-leading-btn" data-ca-lead-kind="theme" data-ca-lead-id="' + esc(th.id) + '"><small>' + bi("Theme", "主题") + '</small><span>' + bi(th.name.en, th.name.zh) + '</span></button>';
    if (sec) html += '<button class="ca-v36-leading-btn" data-ca-lead-kind="sector" data-ca-lead-id="' + esc(sec.id) + '"><small>' + bi("Sector", "板块") + '</small><span>' + bi(sec.name.en, sec.name.zh) + '</span></button>';
    if (fresh) html += '<span class="ca-v36-leading-fresh">' + bi(fresh + " fresh Prophet signal" + (fresh === 1 ? "" : "s"), "Prophet 新信号 " + fresh + " 条") + '</span>';
    host.innerHTML = html;
  }

  function itemForFilter() {
    if (!state.filter) return null;
    return (state.filter.kind === "theme" ? state.themes : state.sectors).find(function (x) { return x.id === state.filter.id; }) || null;
  }
  function sourceSet() { return state.source === "top" ? new Set(state.cards.slice(0, 5).map(function (c) { return ticker(c.getAttribute("data-ticker")); })) : null; }
  function allowed(tk) {
    var src = sourceSet(), item = itemForFilter();
    if (src && !src.has(tk)) return false;
    if (item && item.members && !item.members.has(tk)) return false;
    return true;
  }
  function markLeadership() {
    qsa("[data-ca-lead-kind][data-ca-lead-id]", qs("#ca-v36") || document).forEach(function (el) {
      el.classList.toggle("is-active", !!state.filter && el.getAttribute("data-ca-lead-kind") === state.filter.kind && el.getAttribute("data-ca-lead-id") === state.filter.id);
    });
  }
  /* Sol adversarial gate: a leadership filter must never silently switch
     the Top Picks / All Candidates population. When the active filter
     leaves zero Top Picks but All Candidates DOES have matches, invite the
     reader to switch deliberately instead of doing it for them. */
  function emptyStateHtml() {
    var item = itemForFilter();
    if (state.source === "top" && item && item.members) {
      var wouldAllShowMore = state.cards.some(function (card) { return item.members.has(ticker(card.getAttribute("data-ticker"))); });
      if (wouldAllShowMore) {
        return bi("No Top Picks in this group.", "该组别中暂无首选。") +
          ' <button class="ca-v36-empty-switch" type="button">' + bi("View All Candidates", "查看全部候选") + '</button>';
      }
    }
    return bi("No names match this leadership filter.", "当前领先筛选下暂无匹配个股。");
  }
  function applyFilter() {
    var shown = 0;
    state.cards.forEach(function (card) { var show = allowed(ticker(card.getAttribute("data-ticker"))); card.hidden = !show; if (show) shown++; });
    var empty = qs("#ca-v36-grid-empty");
    if (empty) { empty.hidden = shown !== 0; if (shown === 0) empty.innerHTML = emptyStateHtml(); }
    var result = qs("#ca-v36-result"); if (result) result.innerHTML = bi(shown + " shown · " + state.cards.length + " on board", "显示 " + shown + " 只 · 榜单共 " + state.cards.length + " 只");
    var pill = qs("#ca-v36-filter"), item = itemForFilter();
    if (pill) { pill.classList.toggle("is-on", !!item); pill.innerHTML = item ? bi(item.kind === "theme" ? "Theme" : "Sector", item.kind === "theme" ? "主题" : "板块") + ': ' + bi(item.name.en, item.name.zh) + ' ×' : ""; }
    markLeadership(); applyTableFilter();
  }

  function rowTicker(tr) {
    var direct = ticker(tr.getAttribute("data-ticker")); if (direct && rowsByTicker[direct]) return direct;
    var text = tr.textContent || "";
    for (var i = 0; i < state.rows.length; i++) { var tk = ticker(state.rows[i].ticker); if (tk && text.indexOf(tk) !== -1) return tk; }
    return "";
  }
  function priceColumn(table) {
    var heads = qsa("thead th", table);
    for (var i = 0; i < heads.length; i++) { var t = (heads[i].textContent || "").toLowerCase(); if (t.indexOf("price") !== -1 || t.indexOf("价格") !== -1) return i; }
    return -1;
  }
  function enhanceTableQuotes() {
    var table = qs("#stocktable-wrap table"); if (!table) return;
    var idx = priceColumn(table); if (idx < 0) return;
    qsa("tbody tr", table).forEach(function (tr) {
      var tk = rowTicker(tr), cell = qsa("td", tr)[idx]; if (!tk || !cell || qs(".ca-v36-table-live", cell)) return;
      var card = state.cards.find(function (c) { return ticker(c.getAttribute("data-ticker")) === tk; });
      var px = card ? qs(".nb-px[data-sym]", card) : null, ch = card ? qs(".nb-chg[data-sym]", card) : null;
      var p = px ? px.textContent.trim() : cell.textContent.trim(), c = ch ? ch.textContent.trim() : "—";
      var cls = ch && ch.classList.contains("up") ? " up" : (ch && ch.classList.contains("down") ? " down" : "");
      cell.innerHTML = '<span class="ca-v36-table-live"><span class="nb-px" data-sym="' + esc(tk) + '" data-mkt="ca">' + esc(p) + '</span><span class="nb-chg' + cls + '" data-sym="' + esc(tk) + '" data-mkt="ca">' + esc(c) + '</span></span>';
    });
  }
  function applyTableFilter() {
    var table = qs("#stocktable-wrap table"); if (!table) return;
    enhanceTableQuotes();
    qsa("tbody tr", table).forEach(function (tr) { var tk = rowTicker(tr); tr.classList.toggle("ca-v36-hidden", !!tk && !allowed(tk)); });
  }
  function observeTable() {
    var wrap = qs("#stocktable-wrap"); if (!wrap || tableObserver) return;
    tableObserver = new MutationObserver(function () { requestAnimationFrame(function () { enhanceTableQuotes(); applyTableFilter(); }); });
    tableObserver.observe(wrap, { childList: true, subtree: true }); enhanceTableQuotes(); applyTableFilter();
  }

  function setSource(value) {
    state.source = value === "all" ? "all" : "top";
    qsa("[data-ca-source]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-ca-source") === state.source)); });
    applyFilter();
  }
  function setView(value) {
    state.view = value === "table" ? "table" : "grid";
    try { localStorage.setItem("mdx_stocktable_ca_view", state.view); } catch (e) {}
    qsa("[data-ca-view]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-ca-view") === state.view)); });
    var grid = qs("#ca-v36-card-grid"), table = qs("#ca-v36-table"); if (grid) grid.hidden = state.view !== "grid"; if (table) table.hidden = state.view !== "table";
    if (state.view === "table") { enhanceTableQuotes(); applyTableFilter(); }
  }
  /* Sol adversarial gate: leadership activation sets the filter only — it
     must never force-switch the Top Picks / All Candidates population.
     applyFilter() (not setSource()) is what re-renders the grid here. */
  function activate(kind, id) {
    state.filter = { kind: kind, id: id }; applyFilter(); closeModal();
    var prophet = qs("#ca-v36-prophet"); if (prophet) prophet.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function modalRows(items) {
    return items.length ? items.map(function (x) { return '<tr tabindex="0" data-ca-modal-kind="' + x.kind + '" data-ca-modal-id="' + esc(x.id) + '"><td class="num">' + String(x.rank).padStart(2, "0") + '</td><td><b>' + bi(x.name.en, x.name.zh) + '</b></td><td><span class="ca-v36-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span></td><td class="leaders">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + '</td><td class="num">' + (x.count || 0) + '</td></tr>'; }).join("") : '<tr><td colspan="5">—</td></tr>';
  }
  function modalPane(items, title, count) {
    return '<div class="ca-v36-modal-pane"><h4>' + title + '</h4><table class="ca-v36-modal-table"><thead><tr><th>#</th><th>' + bi("Name", "名称") + '</th><th>' + bi("Stance", "状态") + '</th><th>' + bi("Leaders", "领先个股") + '</th><th>' + count + '</th></tr></thead><tbody>' + modalRows(items) + '</tbody></table></div>';
  }
  /* Group-action band (change 4). Sectors partition by lane 1:1 via `tone`,
     which is minted straight from LANE_DEFS in collectSectors() — never a
     second, independently-invented lane vocabulary. Rows carry the same
     data-ca-modal-kind/data-ca-modal-id pair modalRows() uses so the existing
     modal click/keydown delegation activates them with no new handler path. */
  function laneItemHtml(x) {
    return '<div class="ca-v36-modal-lane-row" tabindex="0" data-ca-modal-kind="' + x.kind + '" data-ca-modal-id="' + esc(x.id) + '">' +
      '<span class="ca-v36-modal-lane-name">' + bi(x.name.en, x.name.zh) + '</span>' +
      '<span class="ca-v36-modal-lane-meta">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + ' · ' + (x.count || 0) + '</span></div>';
  }
  function laneGroupHtml(lane) {
    var items = state.sectors.filter(function (x) { return x.tone === lane.tone; });
    var body = items.length ? items.map(laneItemHtml).join("") : '<div class="ca-v36-modal-lane-row ca-v36-modal-lane-empty">—</div>';
    return '<div class="ca-v36-modal-lane"><div class="ca-v36-modal-lane-hd ' + lane.tone + '">' + bi(lane.en, lane.zh) + '</div>' + body + '</div>';
  }
  function groupActionBandHtml() {
    return '<div class="ca-v36-modal-lanes">' + LANE_DEFS.map(laneGroupHtml).join("") + '</div>';
  }
  function openModal() {
    var modal = qs("#ca-v36-modal"); if (!modal) return;
    qs("#ca-v36-modal-body", modal).innerHTML = groupActionBandHtml() + '<div class="ca-v36-modal-grid">' + modalPane(state.themes, bi("Theme Leadership", "主题领先"), bi("Names", "成分")) + modalPane(state.sectors, bi("Sector Leadership", "板块领先"), bi("Board", "榜单")) + '</div>';
    modal.classList.add("is-open"); modal.setAttribute("aria-hidden", "false"); document.documentElement.style.overflow = "hidden";
  }
  function closeModal() { var modal = qs("#ca-v36-modal"); if (!modal) return; modal.classList.remove("is-open"); modal.setAttribute("aria-hidden", "true"); document.documentElement.style.overflow = ""; }

  function bind(root) {
    root.addEventListener("click", function (e) {
      var b = e.target.closest("[data-ca-source]"); if (b) return setSource(b.getAttribute("data-ca-source"));
      b = e.target.closest("[data-ca-view]"); if (b) return setView(b.getAttribute("data-ca-view"));
      b = e.target.closest("[data-ca-lead-kind][data-ca-lead-id]"); if (b) return activate(b.getAttribute("data-ca-lead-kind"), b.getAttribute("data-ca-lead-id"));
      if (e.target.closest("#ca-v36-filter")) { state.filter = null; return applyFilter(); }
      if (e.target.closest("#ca-v36-expand")) return openModal();
      if (e.target.closest(".ca-v36-empty-switch")) return setSource("all");
    });
  }

  /* Evidence & Record (change 3, restores Track Record). The legacy `.trk`
     wrapper (server-rendered by _track_record_dlg.html.j2, `#trd-btn` +
     `#trd-dlg`) is owner DOM the composer relocates — never rebuilt, never
     computed, never fetched. board_track is a conditional include, so `.trk`
     (or its `#trd-btn` button) can legitimately be absent; that degrades
     quietly to no section rather than a placeholder. */
  function evidenceTrk() {
    var trk = qs(".trk");
    return (trk && qs("#trd-btn", trk)) ? trk : null;
  }
  function evidenceSectionHtml() {
    return '<section class="ca-v36-panel" id="ca-v36-evidence"><div class="ca-v36-sec-hd"><h2>' + bi("Evidence & Record", "证据与往绩") + '</h2><span class="ca-v36-sec-spacer"></span><a class="ca-v36-link" href="measurement.html">' + bi("Methodology →", "方法论 →") + '</a></div><div class="ca-v36-evidence-body" id="ca-v36-evidence-body"></div></section>';
  }

  function buildShell(payload) {
    var nav = qs(".site-nav"), standouts = qs("#standouts"), tableWrap = qs("#stocktable-wrap");
    if (!nav || !standouts || !tableWrap || !state.cards.length) return false;
    injectCss();
    var trk = evidenceTrk();
    var bd = boardDate(payload.as_of || ""), ld = liveDate(), main = document.createElement("main");
    main.className = "ca-v36"; main.id = "ca-v36";
    main.innerHTML = '<header class="ca-v36-head"><h1>' + bi("Canada Stocks", "加拿大股票") + '</h1><span class="ca-v36-head-spacer"></span><span class="ca-v36-chip">' + bi("Screen · evidence accruing", "筛选 · 证据积累中") + '</span><span class="ca-v36-chip">' + bi("Board " + bd.en, "榜单 " + bd.zh) + '</span><span class="ca-v36-live"><span class="ca-v36-live-dot"></span><b>LIVE</b><span>·</span>' + bi(ld.en, ld.zh) + '</span></header>' +
      '<section class="ca-v36-leading" id="ca-v36-leading"></section>' +
      '<section class="ca-v36-panel" id="ca-v36-prophet"><div class="ca-v36-sec-hd"><h2>Prophet</h2><span class="ca-v36-result" id="ca-v36-result"></span><span class="ca-v36-sec-spacer"></span><div class="ca-v36-controls"><button class="ca-v36-filter" id="ca-v36-filter" type="button"></button><span class="ca-v36-seg"><button type="button" data-ca-source="top" aria-selected="true">' + bi("Top Picks", "首选") + '</button><button type="button" data-ca-source="all" aria-selected="false">' + bi("All Candidates", "全部候选") + '</button></span><span class="ca-v36-seg"><button type="button" data-ca-view="grid" aria-selected="true">' + bi("Grid", "卡片") + '</button><button type="button" data-ca-view="table" aria-selected="false">' + bi("Table", "表格") + '</button></span></div></div><div class="ca-v36-card-grid" id="ca-v36-card-grid"><div class="ca-v36-empty" id="ca-v36-grid-empty" hidden>' + bi("No names match this leadership filter.", "当前领先筛选下暂无匹配个股。") + '</div></div><div class="ca-v36-table" id="ca-v36-table" hidden></div></section>' +
      '<section class="ca-v36-panel"><div class="ca-v36-sec-hd"><h2>' + bi("Theme & Sector Leadership", "主题与板块领先") + '</h2><span class="ca-v36-sec-spacer"></span><a class="ca-v36-link" href="baskets_canada.html">' + bi("Thematic Baskets", "主题篮子") + ' ↗</a></div><div class="ca-v36-lead-cols" id="ca-v36-lead-cols"></div><div class="ca-v36-expand-wrap"><button class="ca-v36-expand" id="ca-v36-expand" type="button">' + bi("Expand leadership", "展开领先排名") + ' ↗</button></div></section>' +
      (trk ? evidenceSectionHtml() : '') +
      '<section class="ca-v36-panel"><div class="ca-v36-tools"><b>' + bi("Research tools", "研究工具") + '</b><a class="ca-v36-tool" href="baskets_canada.html">' + bi("Thematic Baskets", "主题篮子") + ' ↗</a><a class="ca-v36-tool" href="canada.html">' + bi("Canada Macro", "加拿大宏观") + ' ↗</a></div></section>';
    nav.insertAdjacentElement("afterend", main);
    var grid = qs("#ca-v36-card-grid", main), empty = qs("#ca-v36-grid-empty", grid);
    state.cards.forEach(function (card) { grid.insertBefore(card, empty); });
    qs("#ca-v36-table", main).appendChild(tableWrap);
    if (trk) qs("#ca-v36-evidence-body", main).appendChild(trk);

    var modal = document.createElement("div"); modal.className = "ca-v36-modal"; modal.id = "ca-v36-modal"; modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = '<div class="ca-v36-modal-card" role="dialog" aria-modal="true" aria-labelledby="ca-v36-modal-title"><div class="ca-v36-modal-hd"><h3 id="ca-v36-modal-title">' + bi("Theme & Sector Leadership", "主题与板块领先") + '</h3><button class="ca-v36-modal-x" type="button" data-ca-modal-close aria-label="Close">×</button></div><div class="ca-v36-modal-body" id="ca-v36-modal-body"></div></div>';
    document.body.appendChild(modal);
    modal.addEventListener("click", function (e) { if (e.target === modal || e.target.closest("[data-ca-modal-close]")) return closeModal(); var r = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]"); if (r) activate(r.getAttribute("data-ca-modal-kind"), r.getAttribute("data-ca-modal-id")); });
    modal.addEventListener("keydown", function (e) { var r = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]"); if (r && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(r.getAttribute("data-ca-modal-kind"), r.getAttribute("data-ca-modal-id")); } });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

    bind(main); document.body.classList.add("ca-v36-mounted"); renderLeadership(); renderLeading(); applyFilter();
    try { state.view = localStorage.getItem("mdx_stocktable_ca_view") === "table" ? "table" : "grid"; } catch (e) { state.view = "grid"; }
    setView(state.view); observeTable(); return true;
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) { if (!r.ok) throw new Error(url + " unavailable"); return r.json(); });
  }
  function start() {
    if (!document.body.classList.contains("page-canada")) return;
    var payload = parseRows(); if (!payload || !state.rows.length) return;
    state.cards = collectCards(); if (!state.cards.length) return;
    state.sectors = collectSectors();

    /* The old page stays visible during this bounded read. `sector_pulse_canada`
       is the current published theme rank/reco owner; baskets.json owns members.
       No client-side score or rank is computed. */
    var done = false, timer = setTimeout(function () { if (!done) { done = true; buildShell(payload); } }, 2500);
    Promise.all([
      getJson("canadabasketdata/baskets.json"),
      getJson("canadabasketdata/sector_pulse_canada.json").catch(function () { return null; })
    ]).then(function (parts) {
      if (done) return;
      done = true; clearTimeout(timer);
      state.themes = collectThemes(parts[0], parts[1]);
      buildShell(payload);
    }).catch(function () {
      if (!done) { done = true; clearTimeout(timer); buildShell(payload); }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}());

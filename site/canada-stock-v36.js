/* Canada Stock Dashboard V3.6 — presentation-only composition.
   SOL-STOCK-DASH-V36-CA-20260823

   This file owns no ranking, signal, quote, lifecycle, entitlement, or persistence
   semantics. It re-composes already-published Canada stock surfaces and reads the
   existing Canada thematic-basket artifact. If anything required is unavailable,
   the legacy page remains visible and functional. */
(function () {
  "use strict";

  var PATH_RE = /(^|\/)canada_stocks\.html$/;
  if (!PATH_RE.test(location.pathname) || window.__mmCanadaStockV36) return;
  window.__mmCanadaStockV36 = true;

  var FONT_UI = "var(--font-ui,-apple-system,BlinkMacSystemFont,Inter,\"Segoe UI\",Roboto,sans-serif)";
  var state = { source: "top", view: "grid", filter: null, themes: [], sectors: [], cards: [], rows: [] };
  var rowsByTicker = Object.create(null);
  var themeMembers = Object.create(null);
  var tableObserver = null;

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
  function fmtBoardDate(raw) {
    if (!raw || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return { en: raw || "—", zh: raw || "—" };
    var p = raw.split("-").map(Number);
    var d = new Date(Date.UTC(p[0], p[1] - 1, p[2], 12));
    return {
      en: new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(d),
      zh: p[0] + "年" + p[1] + "月" + p[2] + "日"
    };
  }
  function fmtLiveDate() {
    var d = new Date();
    return {
      en: new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(d),
      zh: d.getFullYear() + "年" + (d.getMonth() + 1) + "月" + d.getDate() + "日"
    };
  }
  function cleanTicker(value) { return String(value || "").trim().toUpperCase(); }
  function rowTickersForSector(sector) {
    return state.rows.filter(function (r) { return r.sector === sector; }).map(function (r) { return cleanTicker(r.ticker); });
  }

  function parseRows() {
    var el = qs("#stocktable-data");
    if (!el) return null;
    try {
      var payload = JSON.parse(el.textContent || "{}");
      state.rows = Array.isArray(payload.rows) ? payload.rows.slice() : [];
      state.rows.forEach(function (row) { if (row.ticker) rowsByTicker[cleanTicker(row.ticker)] = row; });
      return payload;
    } catch (e) { return null; }
  }

  function collectCards() {
    var host = qs("#standouts .cards");
    if (!host) return [];
    var cards = qsa(".pvcard", host);
    cards.forEach(function (card, i) {
      card.classList.toggle("ca-v36-top-pick", i < 5);
      card.setAttribute("data-ca-v36-order", String(i + 1));
    });
    return cards;
  }

  function collectSectors() {
    var laneDefs = [
      ["#anv2-buy", "Entry now", "现在入场", "buy"],
      ["#anv2-pull", "In favour", "看好", "near"],
      ["#anv2-bot", "Setting up", "形态形成中", "wait"],
      ["#anv2-red", "Reduce / avoid", "减仓 / 回避", "avoid"]
    ];
    var out = [], seen = Object.create(null);
    laneDefs.forEach(function (def) {
      qsa(def[0] + " .anv2-row").forEach(function (node) {
        var link = qs(".anv2-name-link", node);
        var name = dual(qs(".anv2-name", node));
        var href = link ? link.getAttribute("href") || "" : "";
        var m = href.match(/sectors\/([^/.]+)\.html/i);
        var ticker = m ? cleanTicker(m[1]) : "";
        var key = ticker || name.en;
        if (!name.en || seen[key]) return;
        seen[key] = true;
        var boardNames = rowTickersForSector(name.en);
        out.push({
          kind: "sector", rank: out.length + 1, id: key, name: name,
          stance: { en: def[1], zh: def[2] }, tone: def[3],
          count: boardNames.length, countLabel: { en: "Board", zh: "榜单" },
          leaders: boardNames.slice(0, 3), members: new Set(boardNames), href: href
        });
      });
    });
    return out;
  }

  function themeTone(reco) {
    if (reco === "enter" || reco === "accumulate") return "buy";
    if (reco === "hold") return "near";
    if (reco === "trim") return "wait";
    return "avoid";
  }
  function themeStance(reco) {
    var map = {
      enter: ["Enter", "入场"], accumulate: ["Accumulate", "加仓"],
      hold: ["Hold", "持有"], trim: ["Trim", "减仓"], avoid: ["Avoid", "回避"]
    };
    var v = map[reco] || [String(reco || "Neutral"), String(reco || "中性")];
    return { en: v[0], zh: v[1] };
  }
  function collectThemes(payload) {
    if (!payload) return [];
    var intel = payload.theme_intel || {};
    var themes = Array.isArray(intel.themes) ? intel.themes.slice() : [];
    var baskets = payload.baskets || [];
    var basketMap = Object.create(null);
    if (Array.isArray(baskets)) {
      baskets.forEach(function (b) { if (b && b.id) basketMap[b.id] = b; });
    } else if (baskets && typeof baskets === "object") {
      Object.keys(baskets).forEach(function (k) { basketMap[k] = baskets[k]; });
    }
    themes.sort(function (a, b) { return (a.rank || 9999) - (b.rank || 9999); });
    return themes.map(function (th, idx) {
      var basket = basketMap[th.id] || {};
      var members = (basket.members || []).map(function (m) { return cleanTicker(typeof m === "string" ? m : m.ticker); }).filter(Boolean);
      themeMembers[th.id] = new Set(members);
      var leaders = (((th.leadership || {}).top) || []).map(function (x) { return cleanTicker(x.ticker || x.symbol); }).filter(Boolean).slice(0, 3);
      if (!leaders.length) leaders = members.slice(0, 3);
      return {
        kind: "theme", rank: th.rank || idx + 1, id: th.id,
        name: { en: th.name || th.id, zh: th.name_zh || th.name || th.id },
        stance: themeStance(th.reco), tone: themeTone(th.reco),
        count: th.n_members != null ? th.n_members : members.length,
        countLabel: { en: "Names", zh: "成分" }, leaders: leaders,
        members: themeMembers[th.id], score: th.score
      };
    });
  }

  function injectCss() {
    if (qs("#ca-v36-css")) return;
    var style = document.createElement("style");
    style.id = "ca-v36-css";
    style.textContent = [
      "body.page-canada.ca-v36-mounted{font-family:" + FONT_UI + ";background:var(--bg);color:var(--text)}",
      "body.page-canada.ca-v36-mounted>.panel{display:none!important}",
      ".ca-v36{width:min(1480px,calc(100% - 32px));margin:22px auto 44px;font-family:" + FONT_UI + ";font-size:15.5px;line-height:1.45}",
      ".ca-v36 *{box-sizing:border-box}",
      ".ca-v36 button,.ca-v36 input,.ca-v36 select{font-family:inherit}",
      ".ca-v36-head{display:flex;align-items:center;gap:12px;min-height:64px;margin:0 0 14px}",
      ".ca-v36-head h1{margin:0;font-size:31px;line-height:1.05;font-weight:650;letter-spacing:-.03em}",
      ".ca-v36-head-spacer{flex:1}",
      ".ca-v36-chip,.ca-v36-live{height:36px;display:inline-flex;align-items:center;gap:7px;padding:0 12px;border:1px solid var(--line);border-radius:999px;background:var(--panel);color:var(--muted);font-size:11.5px;font-weight:600;white-space:nowrap}",
      ".ca-v36-live-dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 9px color-mix(in srgb,var(--ok) 55%,transparent)}",
      ".ca-v36-live b{color:var(--ok);font-weight:700}",
      ".ca-v36-leading{display:flex;align-items:center;gap:8px;min-height:50px;margin:0 0 14px;padding:8px 10px 8px 14px;border:1px solid var(--line);border-radius:12px;background:color-mix(in srgb,var(--panel) 78%,transparent);box-shadow:var(--card-shadow)}",
      ".ca-v36-leading-k{color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;white-space:nowrap}",
      ".ca-v36-leading-btn{height:34px;display:inline-flex;align-items:center;gap:7px;min-width:0;padding:0 11px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--text);font-size:12.8px;font-weight:600;cursor:pointer;transition:.15s ease}",
      ".ca-v36-leading-btn:hover{transform:translateY(-1px);border-color:color-mix(in srgb,var(--text) 30%,var(--line));background:var(--panel)}",
      ".ca-v36-leading-btn small{color:var(--muted);font-size:9.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}",
      ".ca-v36-leading-fresh{margin-left:auto;color:var(--muted);font-size:12px;white-space:nowrap}",
      ".ca-v36-leading-fresh b{color:var(--text);font-variant-numeric:tabular-nums}",
      ".ca-v36-panel{margin:0 0 14px;border:1px solid var(--line);border-radius:13px;background:var(--panel);box-shadow:var(--card-shadow);overflow:hidden}",
      ".ca-v36-sec-hd{min-height:52px;display:flex;align-items:center;gap:10px;padding:0 15px;border-bottom:1px solid var(--line)}",
      ".ca-v36-sec-hd h2{margin:0;font-size:18px;font-weight:650;letter-spacing:-.012em}",
      ".ca-v36-sec-spacer{flex:1}",
      ".ca-v36-link{color:var(--ink-link,var(--link));font-size:12.5px;font-weight:600;text-decoration:none}",
      ".ca-v36-link:hover{text-decoration:underline}",
      ".ca-v36-lead-cols{display:grid;grid-template-columns:1fr 1fr}",
      ".ca-v36-lead-col+ .ca-v36-lead-col{border-left:1px solid var(--line)}",
      ".ca-v36-lead-col-h{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;color:var(--muted);font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}",
      ".ca-v36-lead-row{position:relative;width:100%;min-height:58px;display:grid;grid-template-columns:30px minmax(0,1fr) auto 34px;align-items:center;gap:9px;padding:9px 14px;border:0;border-top:1px solid color-mix(in srgb,var(--line) 72%,transparent);background:transparent;color:inherit;text-align:left;cursor:pointer;overflow:hidden;transition:.15s ease}",
      ".ca-v36-lead-row:after{content:\"\";position:absolute;left:0;bottom:0;width:var(--breadth,8%);height:1px;background:color-mix(in srgb,var(--link) 44%,transparent);opacity:.5}",
      ".ca-v36-lead-row:hover,.ca-v36-lead-row.is-active{background:color-mix(in srgb,var(--link) 6%,transparent)}",
      ".ca-v36-rank{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11px}",
      ".ca-v36-lead-name{display:block;font-size:14.5px;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".ca-v36-leaders{display:block;margin-top:3px;color:var(--muted);font-size:10.8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".ca-v36-stance{height:23px;display:inline-flex;align-items:center;padding:0 8px;border:1px solid currentColor;border-radius:6px;font-size:9.5px;font-weight:750;text-transform:uppercase;white-space:nowrap}",
      ".ca-v36-stance.buy{color:var(--ink-up,var(--up))}.ca-v36-stance.near{color:var(--ink-link,var(--link))}.ca-v36-stance.wait{color:var(--ink-warn,var(--warn))}.ca-v36-stance.avoid{color:var(--ink-down,var(--down))}",
      ".ca-v36-count{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.5px;text-align:right}",
      ".ca-v36-expand-wrap{display:flex;justify-content:center;padding:9px 12px 11px;border-top:1px solid var(--line);background:color-mix(in srgb,var(--panel2) 32%,transparent)}",
      ".ca-v36-expand{height:35px;padding:0 14px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--text);font-size:12.5px;font-weight:650;cursor:pointer;transition:.15s ease}",
      ".ca-v36-expand:hover{transform:translateY(-1px);border-color:color-mix(in srgb,var(--text) 30%,var(--line))}",
      ".ca-v36-controls{display:flex;align-items:center;gap:7px;flex-wrap:wrap}",
      ".ca-v36-seg{display:inline-flex;gap:3px;padding:3px;border:1px solid var(--line);border-radius:9px;background:var(--panel2)}",
      ".ca-v36-seg button{height:34px;padding:0 13px;border:1px solid transparent;border-radius:7px;background:transparent;color:var(--muted);font-size:12.5px;font-weight:650;cursor:pointer;transition:.15s ease}",
      ".ca-v36-seg button[aria-selected=true]{background:var(--panel);border-color:var(--line);color:var(--text);box-shadow:0 1px 4px rgba(0,0,0,.12)}",
      ".ca-v36-result{color:var(--muted);font-size:12px;white-space:nowrap}",
      ".ca-v36-filter{display:none;height:30px;align-items:center;gap:6px;padding:0 9px;border:1px solid color-mix(in srgb,var(--link) 35%,var(--line));border-radius:999px;background:color-mix(in srgb,var(--link) 7%,transparent);color:var(--text);font-size:11.5px;cursor:pointer}",
      ".ca-v36-filter.is-on{display:inline-flex}",
      ".ca-v36-card-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;padding:14px}",
      ".ca-v36-card-grid .pvcard{min-width:0;height:100%;font-family:" + FONT_UI + ";transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}",
      ".ca-v36-card-grid .pvcard:hover{transform:translateY(-2px)}",
      ".ca-v36-card-grid .pv-tk{font-family:" + FONT_UI + "!important;font-size:16px!important;font-weight:700!important;letter-spacing:-.012em!important}",
      ".ca-v36-card-grid .pv-nm{font-family:" + FONT_UI + "!important;font-size:11.5px!important}",
      ".ca-v36-card-grid .pv-ind{font-size:10.5px!important}",
      ".ca-v36-card-grid .pv-edge{font-family:" + FONT_UI + "!important}",
      ".ca-v36-card-grid .pv-edn{font-size:14px!important}",
      ".ca-v36-card-grid .nb-px.pv-px{font-family:" + FONT_UI + "!important;font-size:14.5px!important;font-weight:750!important}",
      ".ca-v36-card-grid .nb-chg.pv-chg{font-family:" + FONT_UI + "!important;font-size:12.5px!important;font-weight:750!important}",
      ".ca-v36 .nb-chg.up,.ca-v36-table .nb-chg.up{color:var(--ok)!important}.ca-v36 .nb-chg.down,.ca-v36-table .nb-chg.down{color:var(--act)!important}",
      ".ca-v36-card-grid .pv-chip{font-size:10.5px!important}",
      ".ca-v36-card-grid .pv-life-w,.ca-v36-card-grid .pv-stl{font-size:10.5px!important}",
      ".ca-v36-card-grid .pv-zn{min-height:40px!important;font-size:11px!important}",
      ".ca-v36-card-grid .pv-znr,.ca-v36-card-grid .pv-znm{font-family:" + FONT_UI + "!important;font-size:11.5px!important}",
      ".ca-v36-card-grid .ca-v36-top-pick{border-color:color-mix(in srgb,var(--link) 20%,var(--line));box-shadow:0 0 0 1px color-mix(in srgb,var(--link) 8%,transparent),0 0 24px -16px color-mix(in srgb,var(--link) 42%,transparent),0 8px 24px -20px rgba(0,0,0,.55)}",
      ".ca-v36-card-grid .ca-v36-top-pick:after{content:\"\";position:absolute;inset:0;pointer-events:none;border-radius:inherit;box-shadow:inset 0 1px color-mix(in srgb,#fff 6%,transparent)}",
      "html[data-theme=light] .ca-v36-card-grid .ca-v36-top-pick{background:#fff;border-color:color-mix(in srgb,var(--link) 18%,var(--line));box-shadow:0 0 0 1px color-mix(in srgb,var(--link) 7%,transparent),0 10px 26px -22px color-mix(in srgb,var(--link) 30%,transparent)}",
      ".ca-v36-empty{grid-column:1/-1;padding:34px 16px;text-align:center;color:var(--muted);font-size:13px}",
      ".ca-v36-table{padding:12px 14px 15px}.ca-v36-table[hidden]{display:none!important}.ca-v36-table #stocktable-wrap{display:block!important}",
      ".ca-v36-table .stf-row,.ca-v36-table .stf-controls{font-family:" + FONT_UI + "!important}",
      ".ca-v36-table :is(input,select,button){min-height:36px;font-size:12.5px!important}",
      ".ca-v36-table .st-table{font-family:" + FONT_UI + "!important;font-size:13px!important}",
      ".ca-v36-table .st-table th{font-size:10.8px!important;padding:10px 10px!important}",
      ".ca-v36-table .st-table td{padding:10px 10px!important}",
      ".ca-v36-table .st-table td:nth-child(2) b{font-family:" + FONT_UI + "!important;font-size:13.5px}",
      ".ca-v36-table-live{display:inline-flex;align-items:baseline;gap:8px;white-space:nowrap;font-family:" + FONT_UI + "}",
      ".ca-v36-table-live .nb-px{font-size:13.5px;font-weight:700}.ca-v36-table-live .nb-chg{font-size:11.8px;font-weight:750}",
      ".ca-v36-table tr.ca-v36-hidden{display:none!important}",
      ".ca-v36-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:11px 14px}",
      ".ca-v36-tools b{font-size:12.5px;margin-right:2px}.ca-v36-tool{height:35px;display:inline-flex;align-items:center;padding:0 11px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--muted);font-size:11.8px;font-weight:600;text-decoration:none;transition:.15s ease}",
      ".ca-v36-tool:hover{color:var(--text);border-color:color-mix(in srgb,var(--text) 28%,var(--line));transform:translateY(-1px)}",
      ".ca-v36-modal{position:fixed;inset:0;z-index:2147481000;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(4,7,12,.62);backdrop-filter:blur(8px)}",
      ".ca-v36-modal.is-open{display:flex}.ca-v36-modal-card{width:min(1180px,calc(100vw - 32px));max-height:min(820px,calc(100vh - 36px));display:flex;flex-direction:column;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:0 30px 90px rgba(0,0,0,.5);overflow:hidden}",
      "html[data-theme=light] .ca-v36-modal{background:rgba(50,64,90,.22)}html[data-theme=light] .ca-v36-modal-card{box-shadow:0 24px 70px rgba(20,32,64,.2)}",
      ".ca-v36-modal-hd{min-height:56px;display:flex;align-items:center;gap:10px;padding:0 15px;border-bottom:1px solid var(--line)}.ca-v36-modal-hd h3{margin:0;font-size:19px;font-weight:650}.ca-v36-modal-x{margin-left:auto;width:36px;height:36px;border:1px solid var(--line);border-radius:9px;background:var(--panel2);color:var(--text);font-size:21px;cursor:pointer}",
      ".ca-v36-modal-body{overflow:auto;padding:14px}.ca-v36-modal-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ca-v36-modal-pane{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel2)}.ca-v36-modal-pane h4{margin:0;padding:11px 12px;border-bottom:1px solid var(--line);font-size:13px;font-weight:650}",
      ".ca-v36-modal-table{width:100%;border-collapse:collapse;font-size:12.5px}.ca-v36-modal-table th{padding:9px 10px;color:var(--muted);font-size:10px;text-align:left;border-bottom:1px solid var(--line)}.ca-v36-modal-table td{padding:10px;border-bottom:1px solid color-mix(in srgb,var(--line) 70%,transparent)}.ca-v36-modal-table tr:last-child td{border-bottom:0}.ca-v36-modal-table tbody tr{cursor:pointer}.ca-v36-modal-table tbody tr:hover{background:color-mix(in srgb,var(--link) 6%,transparent)}",
      ".ca-v36-modal-table .num{font-variant-numeric:tabular-nums;color:var(--muted)}.ca-v36-modal-table .leaders{color:var(--muted)}",
      "@media(max-width:1200px){.ca-v36-card-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}",
      "@media(max-width:900px){.ca-v36-head{flex-wrap:wrap}.ca-v36-head-spacer{display:none}.ca-v36-lead-cols,.ca-v36-modal-grid{grid-template-columns:1fr}.ca-v36-lead-col+.ca-v36-lead-col{border-left:0;border-top:1px solid var(--line)}.ca-v36-card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}",
      "@media(max-width:680px){.ca-v36{width:min(100% - 20px,680px);margin-top:12px;font-size:15px}.ca-v36-head{gap:8px}.ca-v36-head h1{width:100%;font-size:27px}.ca-v36-chip,.ca-v36-live{height:34px;font-size:10.8px}.ca-v36-leading{flex-wrap:wrap;gap:7px}.ca-v36-leading-k{width:100%}.ca-v36-leading-btn{flex:1;min-width:140px}.ca-v36-leading-fresh{width:100%;margin-left:0;padding-left:2px}.ca-v36-sec-hd{align-items:flex-start;flex-wrap:wrap;padding:11px 12px}.ca-v36-sec-hd h2{font-size:17px}.ca-v36-controls{width:100%}.ca-v36-card-grid{grid-template-columns:1fr;padding:10px;gap:10px}.ca-v36-card-grid .pv-tk{font-size:16.5px!important}.ca-v36-card-grid .nb-px.pv-px{font-size:15px!important}.ca-v36-card-grid .nb-chg.pv-chg{font-size:13px!important}.ca-v36-modal{padding:8px}.ca-v36-modal-card{width:100%;max-height:calc(100vh - 16px)}}"
    ].join("\n");
    document.head.appendChild(style);
  }

  function leadershipRow(item, maxCount) {
    var pct = Math.max(8, Math.round(((item.count || 0) / Math.max(1, maxCount)) * 100));
    var leaders = item.leaders.length ? item.leaders.join(" · ") : "—";
    return '<button class="ca-v36-lead-row" data-ca-lead-kind="' + item.kind + '" data-ca-lead-id="' + esc(item.id) + '" style="--breadth:' + pct + '%">' +
      '<span class="ca-v36-rank">' + String(item.rank).padStart(2, "0") + '</span>' +
      '<span><span class="ca-v36-lead-name">' + bi(item.name.en, item.name.zh) + '</span><span class="ca-v36-leaders">' + esc(leaders) + '</span></span>' +
      '<span class="ca-v36-stance ' + item.tone + '">' + bi(item.stance.en, item.stance.zh) + '</span>' +
      '<span class="ca-v36-count">' + (item.count || 0) + '</span></button>';
  }

  function leadershipColumn(items, kind) {
    var isTheme = kind === "theme";
    var top = items.slice(0, 5);
    var max = Math.max.apply(Math, [1].concat(top.map(function (x) { return x.count || 0; })));
    return '<div class="ca-v36-lead-col"><div class="ca-v36-lead-col-h"><span>' +
      (isTheme ? bi("Themes", "主题") : bi("Sectors", "板块")) + '</span><span>' +
      (isTheme ? bi("Names", "成分") : bi("Board", "榜单")) + '</span></div>' +
      (top.length ? top.map(function (x) { return leadershipRow(x, max); }).join("") : '<div class="ca-v36-empty">' + bi(isTheme ? "Theme ranking unavailable" : "Sector ranking unavailable", isTheme ? "主题排名暂不可用" : "板块排名暂不可用") + '</div>') + '</div>';
  }

  function renderLeadership() {
    var cols = qs("#ca-v36-lead-cols");
    if (!cols) return;
    cols.innerHTML = leadershipColumn(state.themes, "theme") + leadershipColumn(state.sectors, "sector");
    markActiveLeadership();
  }

  function renderLeadingNow() {
    var host = qs("#ca-v36-leading");
    if (!host) return;
    var th = state.themes[0], sec = state.sectors[0];
    var fresh = state.cards.filter(function (c) { return !!qs(".pv-mk-new", c); }).length;
    var html = '<span class="ca-v36-leading-k">' + bi("Leading now", "当前领先") + '</span>';
    if (th) html += '<button class="ca-v36-leading-btn" data-ca-lead-kind="theme" data-ca-lead-id="' + esc(th.id) + '"><small>' + bi("Theme", "主题") + '</small><span>' + bi(th.name.en, th.name.zh) + '</span></button>';
    if (sec) html += '<button class="ca-v36-leading-btn" data-ca-lead-kind="sector" data-ca-lead-id="' + esc(sec.id) + '"><small>' + bi("Sector", "板块") + '</small><span>' + bi(sec.name.en, sec.name.zh) + '</span></button>';
    html += '<span class="ca-v36-leading-fresh">' + (fresh ? bi(String(fresh) + " fresh Prophet signal" + (fresh === 1 ? "" : "s"), "Prophet 新信号 " + fresh + " 条") : bi("No fresh Prophet signals", "暂无 Prophet 新信号")) + '</span>';
    host.innerHTML = html;
  }

  function filterItem() {
    if (!state.filter) return null;
    var list = state.filter.kind === "theme" ? state.themes : state.sectors;
    return list.find(function (x) { return x.id === state.filter.id; }) || null;
  }
  function filterSet() {
    var item = filterItem();
    return item ? item.members : null;
  }
  function sourceSet() {
    if (state.source !== "top") return null;
    return new Set(state.cards.slice(0, 5).map(function (c) { return cleanTicker(c.getAttribute("data-ticker")); }));
  }
  function cardAllowed(ticker) {
    var sset = sourceSet(), fset = filterSet();
    if (sset && !sset.has(ticker)) return false;
    if (fset && !fset.has(ticker)) return false;
    return true;
  }

  function applyCardFilter() {
    var visible = 0;
    state.cards.forEach(function (card) {
      var ticker = cleanTicker(card.getAttribute("data-ticker"));
      var show = cardAllowed(ticker);
      card.hidden = !show;
      if (show) visible++;
    });
    var empty = qs("#ca-v36-grid-empty");
    if (empty) empty.hidden = visible !== 0;
    var result = qs("#ca-v36-result");
    if (result) result.innerHTML = bi(visible + " shown · " + state.cards.length + " on board", "显示 " + visible + " 只 · 榜单共 " + state.cards.length + " 只");
    var pill = qs("#ca-v36-filter");
    var item = filterItem();
    if (pill) {
      pill.classList.toggle("is-on", !!item);
      pill.innerHTML = item ? (bi(item.kind === "theme" ? "Theme" : "Sector", item.kind === "theme" ? "主题" : "板块") + ': ' + bi(item.name.en, item.name.zh) + ' ×') : "";
    }
    markActiveLeadership();
    applyTableFilter();
  }

  function markActiveLeadership() {
    qsa("[data-ca-lead-kind][data-ca-lead-id]", qs("#ca-v36") || document).forEach(function (el) {
      var on = state.filter && el.getAttribute("data-ca-lead-kind") === state.filter.kind && el.getAttribute("data-ca-lead-id") === state.filter.id;
      el.classList.toggle("is-active", !!on);
    });
  }

  function knownTickerFromRow(tr) {
    var direct = cleanTicker(tr.getAttribute("data-ticker"));
    if (direct && rowsByTicker[direct]) return direct;
    var text = tr.textContent || "";
    for (var i = 0; i < state.rows.length; i++) {
      var tk = cleanTicker(state.rows[i].ticker);
      if (tk && text.indexOf(tk) !== -1) return tk;
    }
    return "";
  }

  function tablePriceIndex(table) {
    var ths = qsa("thead th", table);
    for (var i = 0; i < ths.length; i++) {
      var text = (ths[i].textContent || "").toLowerCase();
      if (text.indexOf("price") !== -1 || text.indexOf("价格") !== -1) return i;
    }
    return -1;
  }

  function enhanceTableQuotes() {
    var table = qs("#stocktable-wrap table");
    if (!table) return;
    var idx = tablePriceIndex(table);
    if (idx < 0) return;
    qsa("tbody tr", table).forEach(function (tr) {
      var ticker = knownTickerFromRow(tr);
      if (!ticker) return;
      var cells = qsa("td", tr), cell = cells[idx];
      if (!cell || qs(".ca-v36-table-live", cell)) return;
      var card = state.cards.find(function (c) { return cleanTicker(c.getAttribute("data-ticker")) === ticker; });
      var px = card ? qs(".nb-px[data-sym]", card) : null;
      var ch = card ? qs(".nb-chg[data-sym]", card) : null;
      var initialPrice = px ? px.textContent.trim() : cell.textContent.trim();
      var initialChange = ch ? ch.textContent.trim() : "—";
      var cls = ch && ch.classList.contains("up") ? " up" : (ch && ch.classList.contains("down") ? " down" : "");
      cell.innerHTML = '<span class="ca-v36-table-live"><span class="nb-px" data-sym="' + esc(ticker) + '" data-mkt="ca">' + esc(initialPrice) + '</span><span class="nb-chg' + cls + '" data-sym="' + esc(ticker) + '" data-mkt="ca">' + esc(initialChange) + '</span></span>';
    });
  }

  function applyTableFilter() {
    var table = qs("#stocktable-wrap table");
    if (!table) return;
    enhanceTableQuotes();
    qsa("tbody tr", table).forEach(function (tr) {
      var ticker = knownTickerFromRow(tr);
      tr.classList.toggle("ca-v36-hidden", !!ticker && !cardAllowed(ticker));
    });
  }

  function observeTable() {
    var wrap = qs("#stocktable-wrap");
    if (!wrap || tableObserver) return;
    tableObserver = new MutationObserver(function () {
      requestAnimationFrame(function () { enhanceTableQuotes(); applyTableFilter(); });
    });
    tableObserver.observe(wrap, { childList: true, subtree: true });
    enhanceTableQuotes();
    applyTableFilter();
  }

  function setSource(source) {
    state.source = source === "all" ? "all" : "top";
    qsa("[data-ca-source]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-ca-source") === state.source)); });
    applyCardFilter();
  }
  function setView(view) {
    state.view = view === "table" ? "table" : "grid";
    try { localStorage.setItem("mdx_stocktable_ca_view", state.view); } catch (e) {}
    qsa("[data-ca-view]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-ca-view") === state.view)); });
    var grid = qs("#ca-v36-card-grid"), table = qs("#ca-v36-table");
    if (grid) grid.hidden = state.view !== "grid";
    if (table) table.hidden = state.view !== "table";
    if (state.view === "table") { enhanceTableQuotes(); applyTableFilter(); }
  }

  function activateLeadership(kind, id) {
    state.filter = { kind: kind, id: id };
    state.source = "all";
    setSource("all");
    closeModal();
    var prophet = qs("#ca-v36-prophet");
    if (prophet) prophet.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function modalRows(items) {
    if (!items.length) return '<tr><td colspan="5">—</td></tr>';
    return items.map(function (x) {
      return '<tr tabindex="0" data-ca-modal-kind="' + x.kind + '" data-ca-modal-id="' + esc(x.id) + '"><td class="num">' + String(x.rank).padStart(2, "0") + '</td><td><b>' + bi(x.name.en, x.name.zh) + '</b></td><td><span class="ca-v36-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span></td><td class="leaders">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + '</td><td class="num">' + (x.count || 0) + '</td></tr>';
    }).join("");
  }
  function modalPane(items, title, countHead) {
    return '<div class="ca-v36-modal-pane"><h4>' + title + '</h4><table class="ca-v36-modal-table"><thead><tr><th>#</th><th>' + bi("Name", "名称") + '</th><th>' + bi("Stance", "状态") + '</th><th>' + bi("Leaders", "领先个股") + '</th><th>' + countHead + '</th></tr></thead><tbody>' + modalRows(items) + '</tbody></table></div>';
  }
  function openModal() {
    var modal = qs("#ca-v36-modal");
    if (!modal) return;
    qs("#ca-v36-modal-body", modal).innerHTML = '<div class="ca-v36-modal-grid">' +
      modalPane(state.themes, bi("Theme Leadership", "主题领先"), bi("Names", "成分")) +
      modalPane(state.sectors, bi("Sector Leadership", "板块领先"), bi("Board", "榜单")) + '</div>';
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
    document.documentElement.style.overflow = "hidden";
  }
  function closeModal() {
    var modal = qs("#ca-v36-modal");
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
    document.documentElement.style.overflow = "";
  }

  function bind(root) {
    root.addEventListener("click", function (e) {
      var source = e.target.closest("[data-ca-source]");
      if (source) { setSource(source.getAttribute("data-ca-source")); return; }
      var view = e.target.closest("[data-ca-view]");
      if (view) { setView(view.getAttribute("data-ca-view")); return; }
      var lead = e.target.closest("[data-ca-lead-kind][data-ca-lead-id]");
      if (lead) { activateLeadership(lead.getAttribute("data-ca-lead-kind"), lead.getAttribute("data-ca-lead-id")); return; }
      if (e.target.closest("#ca-v36-filter")) { state.filter = null; applyCardFilter(); return; }
      if (e.target.closest("#ca-v36-expand")) { openModal(); return; }
    });
  }

  function buildShell(payload) {
    var nav = qs(".site-nav");
    var standouts = qs("#standouts");
    var tableWrap = qs("#stocktable-wrap");
    if (!nav || !standouts || !tableWrap || !state.cards.length) return false;

    injectCss();
    var boardDate = fmtBoardDate(payload.as_of || "");
    var liveDate = fmtLiveDate();
    var main = document.createElement("main");
    main.className = "ca-v36";
    main.id = "ca-v36";
    main.innerHTML =
      '<header class="ca-v36-head"><h1>' + bi("Canada Stocks", "加拿大股票") + '</h1><span class="ca-v36-head-spacer"></span>' +
        '<span class="ca-v36-chip">' + bi("Screen · evidence accruing", "筛选 · 证据积累中") + '</span>' +
        '<span class="ca-v36-chip">' + bi("Board " + boardDate.en, "榜单 " + boardDate.zh) + '</span>' +
        '<span class="ca-v36-live"><span class="ca-v36-live-dot"></span><b>LIVE</b><span>·</span>' + bi(liveDate.en, liveDate.zh) + '</span></header>' +
      '<section class="ca-v36-leading" id="ca-v36-leading"></section>' +
      '<section class="ca-v36-panel" id="ca-v36-leadership"><div class="ca-v36-sec-hd"><h2>' + bi("Theme & Sector Leadership", "主题与板块领先") + '</h2><span class="ca-v36-sec-spacer"></span><a class="ca-v36-link" href="baskets_canada.html">' + bi("Thematic Baskets", "主题篮子") + ' ↗</a></div><div class="ca-v36-lead-cols" id="ca-v36-lead-cols"></div><div class="ca-v36-expand-wrap"><button class="ca-v36-expand" id="ca-v36-expand" type="button">' + bi("Expand leadership", "展开领先排名") + ' ↗</button></div></section>' +
      '<section class="ca-v36-panel" id="ca-v36-prophet"><div class="ca-v36-sec-hd"><h2>Prophet</h2><span class="ca-v36-result" id="ca-v36-result"></span><span class="ca-v36-sec-spacer"></span><div class="ca-v36-controls"><button class="ca-v36-filter" id="ca-v36-filter" type="button"></button><span class="ca-v36-seg"><button type="button" data-ca-source="top" aria-selected="true">' + bi("Top Picks", "首选") + '</button><button type="button" data-ca-source="all" aria-selected="false">' + bi("All Candidates", "全部候选") + '</button></span><span class="ca-v36-seg"><button type="button" data-ca-view="grid" aria-selected="true">' + bi("Grid", "卡片") + '</button><button type="button" data-ca-view="table" aria-selected="false">' + bi("Table", "表格") + '</button></span></div></div><div class="ca-v36-card-grid" id="ca-v36-card-grid"><div class="ca-v36-empty" id="ca-v36-grid-empty" hidden>' + bi("No names match this leadership filter.", "当前领先筛选下暂无匹配个股。") + '</div></div><div class="ca-v36-table" id="ca-v36-table" hidden></div></section>' +
      '<section class="ca-v36-panel"><div class="ca-v36-tools"><b>' + bi("Research tools", "研究工具") + '</b><a class="ca-v36-tool" href="baskets_canada.html">' + bi("Thematic Baskets", "主题篮子") + ' ↗</a><a class="ca-v36-tool" href="canada.html">' + bi("Canada Macro", "加拿大宏观") + ' ↗</a></div></section>';

    nav.insertAdjacentElement("afterend", main);
    var grid = qs("#ca-v36-card-grid", main);
    state.cards.forEach(function (card) { grid.insertBefore(card, qs("#ca-v36-grid-empty", grid)); });
    qs("#ca-v36-table", main).appendChild(tableWrap);

    var modal = document.createElement("div");
    modal.className = "ca-v36-modal";
    modal.id = "ca-v36-modal";
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = '<div class="ca-v36-modal-card" role="dialog" aria-modal="true" aria-labelledby="ca-v36-modal-title"><div class="ca-v36-modal-hd"><h3 id="ca-v36-modal-title">' + bi("Theme & Sector Leadership", "主题与板块领先") + '</h3><button class="ca-v36-modal-x" type="button" data-ca-modal-close aria-label="Close">×</button></div><div class="ca-v36-modal-body" id="ca-v36-modal-body"></div></div>';
    document.body.appendChild(modal);
    modal.addEventListener("click", function (e) {
      if (e.target === modal || e.target.closest("[data-ca-modal-close]")) { closeModal(); return; }
      var row = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]");
      if (row) activateLeadership(row.getAttribute("data-ca-modal-kind"), row.getAttribute("data-ca-modal-id"));
    });
    modal.addEventListener("keydown", function (e) {
      var row = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]");
      if (row && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activateLeadership(row.getAttribute("data-ca-modal-kind"), row.getAttribute("data-ca-modal-id")); }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

    bind(main);
    document.body.classList.add("ca-v36-mounted");
    renderLeadership();
    renderLeadingNow();
    applyCardFilter();
    try { state.view = localStorage.getItem("mdx_stocktable_ca_view") === "table" ? "table" : "grid"; } catch (e) { state.view = "grid"; }
    setView(state.view);
    observeTable();
    return true;
  }

  function start() {
    if (!document.body.classList.contains("page-canada")) return;
    var payload = parseRows();
    if (!payload || !state.rows.length) return;
    state.cards = collectCards();
    if (!state.cards.length) return;
    state.sectors = collectSectors();

    var done = false;
    var timer = setTimeout(function () {
      if (done) return;
      done = true;
      buildShell(payload);
    }, 1200);
    fetch("canadabasketdata/baskets.json", { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error("theme artifact unavailable");
      return r.json();
    }).then(function (themes) {
      if (done) return;
      done = true;
      clearTimeout(timer);
      state.themes = collectThemes(themes);
      buildShell(payload);
    }).catch(function () {
      if (done) return;
      done = true;
      clearTimeout(timer);
      buildShell(payload);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}());

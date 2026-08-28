/* Canada Stock Dashboard V3.8 — presentation-only composition.
   stock-dashboard-v38-hk-ca-fable-20260826-sol-001 (V38-R2)
   Architecture: research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md
   + DEC:V38-ACTION-IS-NOT-LEADERSHIP. Law: ACTION TIMING ≠ TREND LEADERSHIP.

   V3.8 over V3.7: the owner-native What to Act On Now lanes render AT REST
   above Prophet (compact, max 3 rows per lane before View all); the
   presentation-minted sector rank (lane-traversal position) is DELETED —
   sectors carry no number because no canonical sector-rank owner
   exists; Themes keep the owner-published `themes[].rank` under an explicit
   "Theme rank" basis; counts render only where canonical membership is
   known (missing ≠ zero). Frozen and untouched: first-five Top Picks
   accepted projection, LIVE quote plane, Grid/Table XOR, Track Record,
   Terminal routes, the two artifact fetches.

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
  var state = { source: "top", view: "grid", filter: null, themes: [], sectors: [], cards: [], rows: [],
    /* V3.8 Act-Now panel presentation state (same contract as the HK
       composer): anLane = visible lane on the mobile segmented selector;
       anOpen = per-lane View-all expansion. Neither ever touches
       source/filter. hasThemeRank gates all theme-rank language (missing
       owner -> no number, no basis chip). Membership knowledge is PER
       GROUP (each item's members is a Set or null), never a global flag. */
    anLane: null, anOpen: {}, hasThemeRank: false };
  var rowsByTicker = Object.create(null);
  var tableObserver = null;

  /* Owner-native Act-Now lane vocabulary (templates/canada.html.j2:854-996,
     `_ca_anlane(...)` title_en/title_zh). This is the single source for both
     collectSectors() and the at-rest What to Act On Now panel (the one home
     for group action since V3.8) — never invent parallel lane vocabulary. */
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
  /* V3.8 (DEC:V38-ACTION-IS-NOT-LEADERSHIP): sectors carry NO rank — the
     V3.7 rank was lane-traversal position minted into a
     number, and no canonical Canada sector-rank owner exists. laneIdx is
     display order for the Act-Now lanes only, never a stat. */
  function collectSectors() {
    /* Membership knowledge is PER GROUP, not a page-global flag (adversarial
       review 2026-08-27, finding 1): the Act-Now lane taxonomy and the board
       rows' sector taxonomy are different vocabularies (lane "Communication
       Services" vs board "Communication"), so a group's membership is
       canonical ONLY when its exact name exists in the board's own sector
       vocabulary. A lane name outside that vocabulary keeps members/count
       null — unknown, never a false "0 · Prophet". */
    var sectorVocab = new Set(state.rows.map(function (r) { return r && r.sector; }).filter(Boolean));
    var out = [], seen = Object.create(null);
    LANE_DEFS.forEach(function (def) {
      qsa(def.sel + " .anv2-row").forEach(function (node) {
        var link = qs(".anv2-name-link", node), name = dual(qs(".anv2-name", node));
        var href = link ? link.getAttribute("href") || "" : "", m = href.match(/sectors\/([^/.]+)\.html/i);
        var id = m ? ticker(m[1]) : name.en;
        if (!name.en || seen[id]) return;
        seen[id] = true;
        var members = sectorVocab.has(name.en) ? sectorMembers(name.en) : null;
        out.push({ kind: "sector", rank: null, id: id, name: name,
          stance: { en: def.en, zh: def.zh }, tone: def.tone,
          count: members ? members.size : null,
          members: members, leaders: members ? Array.from(members).slice(0, 3) : [],
          href: href, laneIdx: out.length });
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
    /* Rank is owner-published by sector_pulse/theme_intel. The page never
       re-scores — and never MINTS: a theme the owner did not rank keeps
       rank null (the V3.7 positional fallback was sort position minted into
       a number; V3.8 law renders no number without an owner). */
    ranked.sort(function (a, b) { return (a.rank || 9999) - (b.rank || 9999); });
    var themes = ranked.map(function (th) {
      var basket = basketMap[th.id];
      /* Current Canada basket artifacts publish member identity as `symbol`.
         `ticker` remains accepted for older/alternate regional producers.
         A theme with no basket entry has UNKNOWN membership: members stays
         null (filter no-ops, count falls back to the owner's own n_members
         or is omitted) — an empty set here would render a false zero and
         falsely empty the board on activation. */
      var members = basket ? new Set((basket.members || []).map(function (m) { return ticker(typeof m === "string" ? m : (m.ticker || m.symbol)); }).filter(Boolean)) : null;
      var leaders = (((th.leadership || {}).top) || []).map(function (x) { return ticker(x.ticker || x.symbol || x.t); }).filter(Boolean).slice(0, 3);
      if (!leaders.length && members) leaders = Array.from(members).slice(0, 3);
      return { kind: "theme", rank: th.rank != null ? th.rank : null, id: th.id,
        name: { en: th.name || th.id, zh: th.name_zh || th.name || th.id },
        stance: stance(th.reco, th), tone: tone(th.reco),
        count: th.n_members != null ? th.n_members : (members ? members.size : null),
        members: members, leaders: leaders };
    });
    state.hasThemeRank = themes.some(function (x) { return x.rank != null; });
    return themes;
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
      /* V3.8: the standalone Leading Now strip is absorbed (§4). The fresh-
         Prophet-signals cue (owner .pv-mk-new markers) rides compactly in
         the Prophet header; the rank story lives in the labelled Leadership
         rows themselves. */
      ".ca-v36-fresh{color:var(--muted);font-size:12.2px;white-space:nowrap}",
      ".ca-v36-lead-basis{height:26px;display:inline-flex;align-items:center;padding:0 9px;border:1px solid var(--line);border-radius:999px;background:var(--panel2);color:var(--muted);font-size:11px;font-weight:650;white-space:nowrap}",
      /* What to Act On Now — compact at-rest action map (V3.8 §5), same
         grammar as the HK composer: four owner-native lanes, ≤3 rows per
         lane before View all, name-first rows with an optional Prophet
         count and the owner's group-research route only. */
      ".ca-v36-an-body{padding:10px 12px 11px}",
      ".ca-v36-an-seg{display:none;gap:6px;margin-bottom:10px}.ca-v36-an-seg button{flex:1;min-width:0;height:34px;display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:0 7px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--muted);font-size:11px;font-weight:700;cursor:pointer}.ca-v36-an-seg-t{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ca-v36-an-seg b{flex:none;font-variant-numeric:tabular-nums;font-weight:700}.ca-v36-an-seg button[aria-selected=true]{color:var(--text);border-color:color-mix(in srgb,var(--text) 30%,var(--line));background:var(--panel)}",
      ".ca-v36-an-lanes{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}",
      ".ca-v36-an-lane{border:1px solid var(--line);border-radius:11px;background:var(--panel2);overflow:hidden}",
      ".ca-v36-an-hd{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:8px 10px;border-bottom:1px solid var(--line);border-top:2px solid currentColor;font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.02em}.ca-v36-an-hd.buy{color:var(--ink-up,var(--up))}.ca-v36-an-hd.near{color:var(--ink-link,var(--link))}.ca-v36-an-hd.wait{color:var(--ink-warn,var(--warn))}.ca-v36-an-hd.avoid{color:var(--ink-down,var(--down))}.ca-v36-an-hd b{font-variant-numeric:tabular-nums;color:var(--muted);font-weight:700}",
      ".ca-v36-an-row-w{display:flex;align-items:stretch;border-top:1px solid color-mix(in srgb,var(--line) 70%,transparent)}.ca-v36-an-hd+.ca-v36-an-row-w{border-top:0}",
      ".ca-v36-an-row{flex:1;display:flex;min-width:0;align-items:center;justify-content:space-between;gap:8px;min-height:32px;padding:5px 10px;border:0;background:transparent;color:inherit;font-size:12.6px;font-weight:650;text-align:left;cursor:pointer}.ca-v36-an-row:hover:not(:disabled),.ca-v36-an-row.is-active{background:color-mix(in srgb,var(--link) 6%,transparent)}.ca-v36-an-row:disabled{cursor:default}.ca-v36-an-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ca-v36-an-n{flex:none;color:var(--muted);font-size:10.6px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}",
      ".ca-v36-an-go{flex:none;display:inline-flex;align-items:center;padding:0 9px;border-left:1px dashed color-mix(in srgb,var(--line) 80%,transparent);color:var(--muted);font-size:12px;text-decoration:none}.ca-v36-an-go:hover{color:var(--text);background:color-mix(in srgb,var(--link) 6%,transparent)}",
      ".ca-v36-an-empty{padding:12px 10px;color:var(--muted);font-size:12px;text-align:center}",
      ".ca-v36-an-more{display:block;width:100%;padding:7px 10px;border:0;border-top:1px dashed color-mix(in srgb,var(--line) 80%,transparent);background:transparent;color:var(--muted);font-size:11px;font-weight:650;cursor:pointer}.ca-v36-an-more:hover{color:var(--text)}",
      ".ca-v36-empty-go{display:inline-block;margin-top:10px;color:var(--ink-link,var(--link));font-size:12px;font-weight:600;text-decoration:none}.ca-v36-empty-go:hover{text-decoration:underline}",
      ".ca-v36-panel{margin-bottom:14px;border:1px solid var(--line);border-radius:13px;background:var(--panel);box-shadow:var(--card-shadow);overflow:hidden}.ca-v36-sec-hd{min-height:54px;display:flex;align-items:center;gap:10px;padding:0 15px;border-bottom:1px solid var(--line)}.ca-v36-sec-hd h2{margin:0;font-size:18px;font-weight:650;letter-spacing:-.012em}.ca-v36-sec-spacer{flex:1}.ca-v36-link{color:var(--ink-link,var(--link));font-size:13px;font-weight:600;text-decoration:none}.ca-v36-link:hover{text-decoration:underline}",
      ".ca-v36-lead-cols{display:block}.ca-v36-lead-col-h{display:flex;justify-content:space-between;padding:11px 14px 10px;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}",
      ".ca-v36-lead-row{position:relative;width:100%;min-height:58px;display:grid;grid-template-columns:30px minmax(0,1fr) auto 34px;align-items:center;gap:9px;padding:10px 14px;border:0;border-top:1px solid color-mix(in srgb,var(--line) 72%,transparent);background:transparent;color:inherit;text-align:left;cursor:pointer;overflow:hidden;transition:.15s ease}.ca-v36-lead-row:after{content:\"\";position:absolute;left:0;bottom:0;width:var(--breadth,8%);height:1px;background:color-mix(in srgb,var(--link) 44%,transparent);opacity:.5}.ca-v36-lead-row:hover:not(:disabled),.ca-v36-lead-row.is-active{background:color-mix(in srgb,var(--link) 6%,transparent)}.ca-v36-lead-row:disabled{cursor:default}.ca-v36-rank{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.5px}.ca-v36-lead-name{display:block;font-size:14.7px;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ca-v36-leaders{display:block;margin-top:3px;color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ca-v36-count{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.7px;text-align:right}",
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
      /* V3.8: the modal group-action band is gone — the at-rest What to Act
         On Now panel above Prophet is the one home for group action. */
      ".ca-v36-modal{position:fixed;inset:0;z-index:2147481000;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(4,7,12,.62);backdrop-filter:blur(8px)}.ca-v36-modal.is-open{display:flex}.ca-v36-modal-card{width:min(1180px,calc(100vw - 32px));max-height:min(820px,calc(100vh - 36px));display:flex;flex-direction:column;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:0 30px 90px rgba(0,0,0,.5);overflow:hidden}html[data-theme=light] .ca-v36-modal{background:rgba(50,64,90,.22)}html[data-theme=light] .ca-v36-modal-card{box-shadow:0 24px 70px rgba(20,32,64,.2)}.ca-v36-modal-hd{min-height:56px;display:flex;align-items:center;padding:0 15px;border-bottom:1px solid var(--line)}.ca-v36-modal-hd h3{margin:0;font-size:19px;font-weight:650}.ca-v36-modal-x{margin-left:auto;width:36px;height:36px;border:1px solid var(--line);border-radius:9px;background:var(--panel2);color:var(--text);font-size:21px;cursor:pointer}.ca-v36-modal-body{overflow:auto;padding:14px}.ca-v36-modal-pane{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel2)}.ca-v36-modal-pane h4{margin:0;padding:11px 12px;border-bottom:1px solid var(--line);font-size:13px}.ca-v36-modal-table{width:100%;border-collapse:collapse;font-size:12.8px}.ca-v36-modal-table th{padding:9px 10px;color:var(--muted);font-size:10.8px;text-align:left;border-bottom:1px solid var(--line)}.ca-v36-modal-table td{padding:10px;border-bottom:1px solid color-mix(in srgb,var(--line) 70%,transparent)}.ca-v36-modal-table tbody tr{cursor:pointer}.ca-v36-modal-table tbody tr:hover{background:color-mix(in srgb,var(--link) 6%,transparent)}.ca-v36-modal-table .num,.ca-v36-modal-table .leaders{color:var(--muted)}",
      /* Mobile Act-Now grammar (§5.5): one segmented lane selector, one lane
         body at a time, no stacked giant lane cards, no horizontal overflow. */
      "@media(max-width:1200px){.ca-v36-card-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.ca-v36-an-lanes{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:900px){.ca-v36-head{flex-wrap:wrap}.ca-v36-head-spacer{display:none}.ca-v36-card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.ca-v36{width:min(100% - 20px,680px);margin-top:12px;font-size:15.8px}.ca-v36-head{gap:8px}.ca-v36-head h1{width:100%;font-size:27.5px}.ca-v36-fresh{white-space:normal}.ca-v36-sec-hd{align-items:flex-start;flex-wrap:wrap;padding:11px 12px}.ca-v36-sec-hd h2{font-size:17px}.ca-v36-controls{width:100%}.ca-v36-an-seg{display:flex}.ca-v36-an-lanes{grid-template-columns:1fr}.ca-v36-an-lane{display:none}.ca-v36-an-lane.is-current{display:block}.ca-v36-card-grid{grid-template-columns:1fr;padding:10px;gap:10px}.ca-v36-card-grid .pv-tk{font-size:16.3px!important}.ca-v36-card-grid .nb-px.pv-px{font-size:15.5px!important}.ca-v36-card-grid .nb-chg.pv-chg{font-size:13.1px!important}.ca-v36-modal{padding:8px}.ca-v36-modal-card{width:100%;max-height:calc(100vh - 16px)}.ca-v36-evidence-body{padding:11px 10px 13px}}"
    ].join("\n");
    document.head.appendChild(css);
  }

  /* Leadership & Rotation (V3.8 §6 + §8.2.4, corrected per adversarial
     review 2026-08-27 finding 2): Canada's ONLY canonical leadership axis
     is the owner-published theme rank, so this surface renders THEMES ONLY
     — `Theme #N` under a visible "Theme rank" basis. There is no sector
     column: with no sector-rank owner, an action-ordered top-5 sector list
     would be §6.2's "numbering rows because they happen to be rendered
     first" with the digit removed. Sectors remain fully useful through
     What to Act On Now and their group pages. The action stance chip stays
     a SEPARATE field. Counts render "—" when membership is unknown, and
     the activation affordance (data-ca-lead-*) renders ONLY when canonical
     membership exists — an unknown-membership group must not offer a
     filter that would paint the full board as if it all matched (§10). */
  function leadRow(x, max) {
    var breadth = Math.max(8, Math.round(((x.count || 0) / Math.max(1, max)) * 100));
    var rankTxt = x.kind === "theme" && x.rank != null ? "Theme #" + x.rank : "—";
    var act = x.members != null ? ' data-ca-lead-kind="' + x.kind + '" data-ca-lead-id="' + esc(x.id) + '"' : ' disabled';
    return '<button class="ca-v36-lead-row" type="button"' + act + ' style="--breadth:' + breadth + '%"><span class="ca-v36-rank">' + esc(rankTxt) + '</span><span><span class="ca-v36-lead-name">' + bi(x.name.en, x.name.zh) + '</span><span class="ca-v36-leaders">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + '</span></span><span class="ca-v36-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span><span class="ca-v36-count">' + (x.count != null ? x.count : "—") + '</span></button>';
  }
  function renderLeadership() {
    var host = qs("#ca-v36-lead-cols");
    if (!host) return;
    var top = state.themes.slice(0, 5), max = Math.max.apply(Math, [1].concat(top.map(function (x) { return x.count || 0; })));
    host.innerHTML = '<div class="ca-v36-lead-col"><div class="ca-v36-lead-col-h"><span>' + bi("Themes", "主题") + (state.hasThemeRank ? ' <span class="ca-v36-lead-basis">' + bi("Theme rank", "主题排名") + '</span>' : '') + '</span><span>' + bi("Names", "成分") + '</span></div>' + (top.length ? top.map(function (x) { return leadRow(x, max); }).join("") : '<div class="ca-v36-empty">' + bi("Theme ranking unavailable", "主题排名暂不可用") + '</div>') + '</div>';
    markLeadership();
  }
  /* Fresh-signals cue (owner .pv-mk-new markers) — the surviving piece of
     the absorbed Leading Now strip, in the Prophet header where it belongs
     (it describes Prophet cards). Absent when zero, never a placeholder. */
  function renderFresh() {
    var host = qs("#ca-v36-fresh"); if (!host) return;
    var fresh = state.cards.filter(function (c) { return !!qs(".pv-mk-new", c); }).length;
    host.innerHTML = fresh ? bi(fresh + " fresh Prophet signal" + (fresh === 1 ? "" : "s"), "Prophet 新信号 " + fresh + " 条") : "";
    host.hidden = !fresh;
  }

  /* What to Act On Now (V3.8 §5) — at-rest action map above Prophet, same
     grammar as the HK composer. Rows carry the same data-ca-lead-kind/-id
     the leadership rows use (one activation path; population never touched)
     plus the owner's group-research route. Lane order is the ACTION owner's
     own DOM order via laneIdx — the theme/leadership axis never orders or
     gates the action surface. */
  var AN_AT_REST = 3;
  function anLaneItems(tone) {
    return state.sectors.filter(function (x) { return x.tone === tone; })
      .sort(function (a, b) { return (a.laneIdx || 0) - (b.laneIdx || 0); });
  }
  function anRowHtml(x) {
    var countHtml = x.count != null ? '<span class="ca-v36-an-n">' + x.count + ' · ' + bi("Prophet", "候选") + '</span>' : '';
    var go = x.href ? '<a class="ca-v36-an-go" href="' + esc(x.href) + '" aria-label="' + esc(x.name.en) + ' sector research">↗</a>' : '';
    /* Filter affordance ONLY under canonical membership (§10: membership
       missing → omit count/filter, keep the group-detail route) — an
       unknown-membership row is a research destination, not a filter that
       would no-op and paint the whole board as matching. */
    var act = x.members != null ? ' data-ca-lead-kind="sector" data-ca-lead-id="' + esc(x.id) + '"' : ' disabled';
    return '<div class="ca-v36-an-row-w"><button class="ca-v36-an-row" type="button"' + act + '><span class="ca-v36-an-name">' + bi(x.name.en, x.name.zh) + '</span>' + countHtml + '</button>' + go + '</div>';
  }
  function anLaneHtml(lane) {
    var items = anLaneItems(lane.tone), open = !!state.anOpen[lane.tone];
    var shown = open ? items : items.slice(0, AN_AT_REST);
    var body = shown.length ? shown.map(anRowHtml).join("") : '<div class="ca-v36-an-empty">—</div>';
    var more = items.length > AN_AT_REST
      ? '<button class="ca-v36-an-more" type="button" data-ca-an-view="' + esc(lane.tone) + '" aria-expanded="' + open + '">' +
        (open ? bi("Show fewer", "收起") : bi("View all " + items.length, "查看全部 " + items.length)) + '</button>'
      : '';
    var current = state.anLane === lane.tone ? " is-current" : "";
    return '<div class="ca-v36-an-lane' + current + '" data-ca-an-lane-body="' + esc(lane.tone) + '"><div class="ca-v36-an-hd ' + lane.tone + '"><span>' + bi(lane.en, lane.zh) + '</span><b>' + items.length + '</b></div>' + body + more + '</div>';
  }
  function renderActNow() {
    var host = qs("#ca-v36-an-body"); if (!host) return;
    if (state.anLane == null) {
      /* Elected ONLY while no lane has been chosen — a user who taps an
         empty lane keeps it and sees its truthful "—" body (HK adversarial
         review 2026-08-27, finding 1, baked in here from the start). */
      for (var i = 0; i < LANE_DEFS.length; i++) {
        if (anLaneItems(LANE_DEFS[i].tone).length) { state.anLane = LANE_DEFS[i].tone; break; }
      }
      if (state.anLane == null) state.anLane = LANE_DEFS[0].tone;
    }
    var seg = '<div class="ca-v36-an-seg" role="tablist">' + LANE_DEFS.map(function (lane) {
      return '<button type="button" role="tab" data-ca-an-lane="' + esc(lane.tone) + '" aria-selected="' + (state.anLane === lane.tone) + '"><span class="ca-v36-an-seg-t">' + bi(lane.en, lane.zh) + '</span><b>' + anLaneItems(lane.tone).length + '</b></button>';
    }).join("") + '</div>';
    host.innerHTML = seg + '<div class="ca-v36-an-lanes">' + LANE_DEFS.map(anLaneHtml).join("") + '</div>';
    markLeadership();
  }
  function setAnLane(tone) {
    /* Presentation-only: never mutates the Prophet selection/filter. */
    state.anLane = tone; renderActNow();
  }
  function toggleAnLane(tone) {
    state.anOpen[tone] = !state.anOpen[tone]; renderActNow();
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
    /* Known zero (§10): membership is canonical and the group genuinely has
       no names on the current board — quiet truthful copy, and the
       group-research route stays usable (never filter-miss language). */
    if (item && item.members && item.members.size === 0) {
      return bi("No current Prophet names in this group.", "该组别暂无 Prophet 候选。") +
        (item.href ? ' <a class="ca-v36-empty-go" href="' + esc(item.href) + '">' + bi("Open sector research ↗", "查看板块研究 ↗") + '</a>' : '');
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

  /* Expanded Leadership (V3.8, themes only — §8.2.4): the full owner-ranked
     theme table, `Theme #N` gated on state.hasThemeRank. No sector pane:
     no sector-rank owner means no sector leadership surface at any depth —
     sectors live in What to Act On Now and their group pages. Activation
     attributes render only under canonical membership (same §10 law as the
     at-rest rows). Counts render "—" when membership is unknown. */
  function modalRows(items, rk) {
    return items.length ? items.map(function (x) { var act = x.members != null ? ' tabindex="0" data-ca-modal-kind="' + x.kind + '" data-ca-modal-id="' + esc(x.id) + '"' : ''; return '<tr' + act + '>' + (rk ? '<td class="num">' + esc(x.rank != null ? "Theme #" + x.rank : "—") + '</td>' : '') + '<td><b>' + bi(x.name.en, x.name.zh) + '</b></td><td><span class="ca-v36-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span></td><td class="leaders">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + '</td><td class="num">' + (x.count != null ? x.count : "—") + '</td></tr>'; }).join("") : '<tr><td colspan="' + (rk ? 5 : 4) + '">—</td></tr>';
  }
  function modalPane(items, title, count, rk) {
    return '<div class="ca-v36-modal-pane"><h4>' + title + '</h4><table class="ca-v36-modal-table"><thead><tr>' + (rk ? '<th>' + bi("Rank", "排名") + '</th>' : '') + '<th>' + bi("Name", "名称") + '</th><th>' + bi("Action", "操作状态") + '</th><th>' + bi("Leaders", "领先个股") + '</th><th>' + count + '</th></tr></thead><tbody>' + modalRows(items, rk) + '</tbody></table></div>';
  }
  function openModal() {
    var modal = qs("#ca-v36-modal"); if (!modal) return;
    var rk = !!state.hasThemeRank;
    qs("#ca-v36-modal-body", modal).innerHTML =
      modalPane(state.themes, bi("Theme Leadership", "主题领先") + (rk ? ' <span class="ca-v36-lead-basis">' + bi("Theme rank", "主题排名") + '</span>' : ''), bi("Names", "成分"), rk);
    modal.classList.add("is-open"); modal.setAttribute("aria-hidden", "false"); document.documentElement.style.overflow = "hidden";
  }
  function closeModal() { var modal = qs("#ca-v36-modal"); if (!modal) return; modal.classList.remove("is-open"); modal.setAttribute("aria-hidden", "true"); document.documentElement.style.overflow = ""; }

  function bind(root) {
    root.addEventListener("click", function (e) {
      var b = e.target.closest("[data-ca-source]"); if (b) return setSource(b.getAttribute("data-ca-source"));
      b = e.target.closest("[data-ca-view]"); if (b) return setView(b.getAttribute("data-ca-view"));
      /* Act-Now presentation controls: distinct targets, never carry the
         lead-kind/-id pair, never touch source/filter. */
      b = e.target.closest("[data-ca-an-lane]"); if (b) return setAnLane(b.getAttribute("data-ca-an-lane"));
      b = e.target.closest("[data-ca-an-view]"); if (b) return toggleAnLane(b.getAttribute("data-ca-an-view"));
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
    /* V3.8 page grammar (§4): Market Header → What to Act On Now → Prophet →
       Leadership & Rotation → Evidence & Record → Research Tools. The
       Act-Now panel renders only when the owner's action lanes populated at
       least one sector (action owner missing → omit; never synthesize
       action from leadership rank). */
    var hasActNow = state.sectors.some(function (x) {
      return LANE_DEFS.some(function (lane) { return lane.tone === x.tone; });
    });
    main.innerHTML = '<header class="ca-v36-head"><h1>' + bi("Canada Stocks", "加拿大股票") + '</h1><span class="ca-v36-head-spacer"></span><span class="ca-v36-chip">' + bi("Screen · evidence accruing", "筛选 · 证据积累中") + '</span><span class="ca-v36-chip">' + bi("Board " + bd.en, "榜单 " + bd.zh) + '</span><span class="ca-v36-live"><span class="ca-v36-live-dot"></span><b>LIVE</b><span>·</span>' + bi(ld.en, ld.zh) + '</span></header>' +
      (hasActNow ? '<section class="ca-v36-panel" id="ca-v36-actnow"><div class="ca-v36-sec-hd"><h2>' + bi("What to Act On Now", "现在行动") + '</h2></div><div class="ca-v36-an-body" id="ca-v36-an-body"></div></section>' : '') +
      '<section class="ca-v36-panel" id="ca-v36-prophet"><div class="ca-v36-sec-hd"><h2>Prophet</h2><span class="ca-v36-result" id="ca-v36-result"></span><span class="ca-v36-fresh" id="ca-v36-fresh" hidden></span><span class="ca-v36-sec-spacer"></span><div class="ca-v36-controls"><button class="ca-v36-filter" id="ca-v36-filter" type="button"></button><span class="ca-v36-seg"><button type="button" data-ca-source="top" aria-selected="true">' + bi("Top Picks", "首选") + '</button><button type="button" data-ca-source="all" aria-selected="false">' + bi("All Candidates", "全部候选") + '</button></span><span class="ca-v36-seg"><button type="button" data-ca-view="grid" aria-selected="true">' + bi("Grid", "卡片") + '</button><button type="button" data-ca-view="table" aria-selected="false">' + bi("Table", "表格") + '</button></span></div></div><div class="ca-v36-card-grid" id="ca-v36-card-grid"><div class="ca-v36-empty" id="ca-v36-grid-empty" hidden>' + bi("No names match this leadership filter.", "当前领先筛选下暂无匹配个股。") + '</div></div><div class="ca-v36-table" id="ca-v36-table" hidden></div></section>' +
      '<section class="ca-v36-panel" id="ca-v36-leadership"><div class="ca-v36-sec-hd"><h2>' + bi("Leadership & Rotation", "领先与轮动") + '</h2><span class="ca-v36-sec-spacer"></span><a class="ca-v36-link" href="baskets_canada.html">' + bi("Thematic Baskets", "主题篮子") + ' ↗</a></div><div class="ca-v36-lead-cols" id="ca-v36-lead-cols"></div><div class="ca-v36-expand-wrap"><button class="ca-v36-expand" id="ca-v36-expand" type="button">' + bi("Expand leadership", "展开领先排名") + ' ↗</button></div></section>' +
      (trk ? evidenceSectionHtml() : '') +
      '<section class="ca-v36-panel"><div class="ca-v36-tools"><b>' + bi("Research tools", "研究工具") + '</b><a class="ca-v36-tool" href="baskets_canada.html">' + bi("Thematic Baskets", "主题篮子") + ' ↗</a><a class="ca-v36-tool" href="canada.html">' + bi("Canada Macro", "加拿大宏观") + ' ↗</a></div></section>';
    nav.insertAdjacentElement("afterend", main);
    var grid = qs("#ca-v36-card-grid", main), empty = qs("#ca-v36-grid-empty", grid);
    state.cards.forEach(function (card) { grid.insertBefore(card, empty); });
    qs("#ca-v36-table", main).appendChild(tableWrap);
    if (trk) qs("#ca-v36-evidence-body", main).appendChild(trk);

    var modal = document.createElement("div"); modal.className = "ca-v36-modal"; modal.id = "ca-v36-modal"; modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = '<div class="ca-v36-modal-card" role="dialog" aria-modal="true" aria-labelledby="ca-v36-modal-title"><div class="ca-v36-modal-hd"><h3 id="ca-v36-modal-title">' + bi("Leadership & Rotation", "领先与轮动") + '</h3><button class="ca-v36-modal-x" type="button" data-ca-modal-close aria-label="Close">×</button></div><div class="ca-v36-modal-body" id="ca-v36-modal-body"></div></div>';
    document.body.appendChild(modal);
    modal.addEventListener("click", function (e) { if (e.target === modal || e.target.closest("[data-ca-modal-close]")) return closeModal(); var r = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]"); if (r) activate(r.getAttribute("data-ca-modal-kind"), r.getAttribute("data-ca-modal-id")); });
    modal.addEventListener("keydown", function (e) { var r = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]"); if (r && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(r.getAttribute("data-ca-modal-kind"), r.getAttribute("data-ca-modal-id")); } });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

    bind(main); document.body.classList.add("ca-v36-mounted"); renderActNow(); renderLeadership(); renderFresh(); applyFilter();
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

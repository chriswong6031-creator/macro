/* HK Stock Dashboard V3.8 — presentation-only composition.
   stock-dashboard-v38-hk-ca-fable-20260826-sol-001 (V38-R1)
   Architecture: research/STOCK_DASHBOARD_V38_ACTION_LEADERSHIP_ARCHITECTURE.md
   + DEC:V38-ACTION-IS-NOT-LEADERSHIP. Law: ACTION TIMING ≠ TREND LEADERSHIP.

   V3.8 over V3.7: the owner-native What to Act On Now lanes render AT REST
   above Prophet (compact, max 3 rows per lane before View all); Leadership &
   Rotation below Prophet names its rank basis explicitly (RS vs HSI, the
   owner's own Sector Rotation rank) and keeps action stance as a separate
   field; a sector with no owner rank shows no number (lane traversal is
   never rank); Prophet-name counts render only where canonical membership is
   known (missing ≠ zero).

   This file owns no ranking, signal, quote, lifecycle, entitlement, or persistence
   semantics. It re-composes already-published HK stock surfaces (Prophet cards,
   Act-Now sector lanes, the Sector Rotation table, the Mainland Money southbound
   cards, the Track Record chip, and the specialist desk panels). Every input is
   harvested from DOM the server already rendered on this page — there is no
   network read anywhere in this file. If anything required is unavailable, the
   legacy page remains visible and functional (abort-to-legacy). */
(function () {
  "use strict";

  var PATH_RE = /(^|\/)hk_stocks\.html$/;
  if (!PATH_RE.test(location.pathname) || window.__mmHKStockV36) return;
  window.__mmHKStockV36 = true;

  var FONT_UI = "var(--font-ui,-apple-system,BlinkMacSystemFont,Inter,\"Segoe UI\",Roboto,sans-serif)";
  var state = { source: "top", view: "grid", filter: null, sectors: [], cards: [], rows: [], featuredCount: 0,
    /* V3.8 Act-Now panel presentation state: anLane = which lane body is
       visible on the mobile segmented selector; anOpen = per-lane View-all
       expansion. Neither ever touches source/filter — a lane change must not
       mutate the Prophet selection until a group is actually chosen. */
    anLane: null, anOpen: {}, membershipKnown: false };
  var rowsByTicker = Object.create(null);
  var tableObserver = null;

  /* Owner-native Act-Now lane vocabulary (templates/hk.html.j2:3416-3419,
     `_hk_anlane(...)` title_en/title_zh). Single source for both collectSectors()
     (sector stance) and the group-action band in openModal() — never invent a
     parallel lane vocabulary. Identical wording to Canada's LANE_DEFS because both
     markets share the same Act-Now UX grammar; the underlying sector population,
     rotation data and every other read below is HK-native and independently
     harvested. */
  var LANE_DEFS = [
    { sel: "#anv2-buy", en: "Buy Now", zh: "立即买入", tone: "buy" },
    { sel: "#anv2-pull", en: "In Favour", zh: "看好", tone: "near" },
    { sel: "#anv2-bot", en: "Bottoming Watch", zh: "洗盘观察", tone: "wait" },
    { sel: "#anv2-red", en: "Reduce / Avoid", zh: "减仓 / 回避", tone: "avoid" }
  ];

  /* On-demand disclosure targets for Research Tools (change 6). Only owner panels
     present in the served DOM get a toggle — a panel absent from this build gets
     no dead button. Never includes #sector-rotation (integrated into Leadership)
     or #act-now (compressed into the Expand modal's group-action band). */
  var TOOL_DEFS = [
    { sel: "#hk-velocity-desk", en: "Fast Movers", zh: "快速异动" },
    { sel: "#washout-watch", en: "Washout Watch", zh: "洗盘观察站" },
    { sel: "#mainland-money", en: "Mainland Money", zh: "内地资金" },
    { sel: "#hk-screener", en: "Screener", zh: "筛选器" }
  ];

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  /* firstN never delegates to a zero-start array slice call — sourceSet()
     below builds the Top Picks cohort from the owner's pv-featured flag,
     never from array position, and this helper keeps every other "first N"
     read (leaders, at-rest leadership rows) off that same pattern too, so a
     mutation cannot quietly reintroduce position-based selection anywhere
     in the file. */
  function firstN(arr, n) {
    var out = [];
    for (var i = 0; i < arr.length && i < n; i++) out.push(arr[i]);
    return out;
  }
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

  /* Grid population — every .pvcard the owner rendered inside #standouts. HK's
     card container is `.nbgrid` (Canada's is `.cards`); this selector is scoped
     to #standouts rather than the container class name so it survives that
     naming difference and still ignores unrelated .nbgrid instances elsewhere on
     the page (e.g. #hk-velocity-desk has its own). */
  function collectCards() {
    var host = qs("#standouts");
    if (!host) return [];
    var cards = qsa(".pvcard", host);
    cards.forEach(function (card, i) {
      /* V3.7 owns inventory visibility; legacy show-more/stage-filter state must
         not survive the move. */
      card.classList.remove("sm-hidden");
      card.hidden = false;
      card.style.removeProperty("display");
      card.setAttribute("data-hk-v37-order", String(i + 1));
    });
    return cards;
  }

  function sectorMembers(name) {
    return new Set(state.rows.filter(function (r) { return r.sector === name; }).map(function (r) { return ticker(r.ticker); }));
  }
  function sectorIdFromHref(href) {
    var m = String(href || "").match(/sectors\/([^/.]+)\.html/i);
    return m ? ticker(m[1]) : "";
  }
  /* Act-Now lane pass — every sector on the board sits in exactly one of the four
     lanes (verified: sector-rotation table row count == total anv2-name-link
     count in current build), but the merge below never assumes that holds. */
  function collectLaneSectors() {
    var out = [], seen = Object.create(null);
    LANE_DEFS.forEach(function (def) {
      qsa(def.sel + " .anv2-row").forEach(function (node) {
        var link = qs(".anv2-name-link", node), name = dual(qs(".anv2-name", node));
        var href = link ? link.getAttribute("href") || "" : "";
        var id = sectorIdFromHref(href) || name.en;
        if (!name.en || !id || seen[id]) return;
        seen[id] = true;
        out.push({ id: id, name: name, stance: { en: def.en, zh: def.zh }, tone: def.tone, href: href });
      });
    });
    return out;
  }
  /* Sector Rotation pass — the owner-published Rank + Cycle-state columns
     (templates/hk.html.j2 #sector-rotation `sortable` table). Rank and cycle
     state are read verbatim; nothing here is recomputed. */
  function collectRotationRanks() {
    var out = Object.create(null);
    qsa("#sector-rotation table.sortable tbody tr").forEach(function (tr) {
      var link = qs("td a", tr);
      var id = link ? sectorIdFromHref(link.getAttribute("href")) : "";
      if (!id) return;
      var cells = qsa("td", tr);
      var rankTxt = cells[1] ? cells[1].textContent.trim() : "";
      var rank = parseInt(rankTxt, 10);
      var cycleEl = cells.length ? qs(".lad", cells[cells.length - 1]) : null;
      out[id] = { rank: isNaN(rank) ? null : rank, cycleState: cycleEl ? dual(cycleEl) : null, name: link ? dual(link) : null };
    });
    return out;
  }
  /* Join law: prefer rotation rank for ordering when a sector appears in both
     (the common case); a sector present only in a lane keeps lane-traversal
     order and is appended after every ranked sector; a sector present only in
     rotation (no lane placement) renders with a neutral "—" stance rather than
     a fabricated recommendation. No client-side score or rank is computed:
     `rank` is the owner's own Sector Rotation number or stays null. V3.8 law
     (DEC:V38-ACTION-IS-NOT-LEADERSHIP): a null rank RENDERS as no rank —
     lane-traversal position is display order only and must never be minted
     into a rank number.

     Membership law: Prophet-name counts/filters are canonical only when the
     board rows actually publish a sector field. When no row carries one,
     members stays null (unknown), the count is omitted everywhere, and
     unknown must never render as zero. */
  function collectSectors() {
    var lanes = collectLaneSectors(), ranks = collectRotationRanks();
    var ranked = [], unranked = [], seenIds = Object.create(null);
    lanes.forEach(function (x) {
      seenIds[x.id] = true;
      var r = ranks[x.id];
      if (r && r.rank != null) {
        x.rank = r.rank; x.cycleState = r.cycleState;
        if (r.name && r.name.en) x.name = r.name;
        ranked.push(x);
      } else {
        x.rank = null;
        unranked.push(x);
      }
    });
    Object.keys(ranks).forEach(function (id) {
      if (seenIds[id]) return;
      var r = ranks[id];
      ranked.push({ id: id, name: r.name || { en: id, zh: id }, stance: { en: "—", zh: "—" }, tone: "none", rank: r.rank, cycleState: r.cycleState });
    });
    ranked.sort(function (a, b) { return (a.rank || 9999) - (b.rank || 9999); });
    var merged = ranked.concat(unranked);
    state.membershipKnown = state.rows.some(function (r) { return !!(r && r.sector); });
    merged.forEach(function (x) {
      x.kind = "sector";
      if (state.membershipKnown) {
        var members = sectorMembers(x.name.en);
        x.members = members; x.leaders = firstN(Array.from(members), 3); x.count = members.size;
      } else {
        x.members = null; x.leaders = []; x.count = null;
      }
    });
    return merged;
  }

  function injectCss() {
    if (qs("#hk-v37-css")) return;
    var css = document.createElement("style");
    css.id = "hk-v37-css";
    css.textContent = [
      /* HK has no `page-hk` body class on hk_stocks.html (templates/hk.html.j2
         only stamps `page-hk` when mode != 'stocks'), so the hide/reveal rules
         below key off `.hk-v37-mounted` alone rather than mirroring Canada's
         `body.page-canada.ca-v36-mounted` compound. templates/hk.html.j2 is out
         of this change's scope, so no body class can be added there.
         Second divergence from the Canada rule text: HK's legacy panels are
         children of a `.grid` wrapper (Canada's page has no such wrapper, so
         `body.page-canada.ca-v36-mounted>.panel` reaches them directly) — a
         direct-child `body>.panel` selector here would silently match nothing.
         Both rules use a descendant combinator instead so they reach the actual
         panel depth. */
      "body.hk-v37-mounted{font-family:" + FONT_UI + ";background:var(--bg);color:var(--text)}",
      "body.hk-v37-mounted .panel{display:none!important}",
      "body.hk-v37-mounted .panel.hk-v37-revealed{display:block!important}",
      ".hk-v37{width:min(1480px,calc(100% - 32px));margin:22px auto 44px;font-family:" + FONT_UI + ";font-size:16.2px;line-height:1.48}",
      ".hk-v37 *{box-sizing:border-box}.hk-v37 button,.hk-v37 input,.hk-v37 select{font-family:inherit}",
      ".hk-v37-head{display:flex;align-items:center;gap:12px;min-height:66px;margin-bottom:14px}.hk-v37-head h1{margin:0;font-size:31.5px;line-height:1.05;font-weight:650;letter-spacing:-.03em}.hk-v37-head-spacer{flex:1}",
      ".hk-v37-chip{height:37px;display:inline-flex;align-items:center;gap:7px;padding:0 13px;border:1px solid var(--line);border-radius:999px;background:var(--panel);color:var(--muted);font-size:12px;font-weight:600;white-space:nowrap}",
      /* V3.8: the standalone Leading Now strip is absorbed (§4). What remains
         of it: the sig-gated Southbound flow cue rides compactly in the
         Leadership & Rotation header (.hk-v37-flow), and the rank story moved
         into the explicitly-labelled Leadership rows themselves. */
      ".hk-v37-flow{color:var(--muted);font-size:12.2px;white-space:nowrap;max-width:38%;overflow:hidden;text-overflow:ellipsis}",
      ".hk-v37-lead-basis{height:26px;display:inline-flex;align-items:center;padding:0 9px;border:1px solid var(--line);border-radius:999px;background:var(--panel2);color:var(--muted);font-size:11px;font-weight:650;white-space:nowrap}",
      /* What to Act On Now — compact at-rest action map (V3.8 §5). Four
         owner-native lanes side by side, ≤3 group rows per lane before View
         all, name-first rows with an optional Prophet count only. Target ≤
         240px collapsed at 1440×900 — no performance/score/percentile/prose
         towers here, ever. */
      ".hk-v37-an-body{padding:10px 12px 11px}",
      ".hk-v37-an-seg{display:none;gap:6px;margin-bottom:10px}.hk-v37-an-seg button{flex:1;min-width:0;height:34px;display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:0 7px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--muted);font-size:11px;font-weight:700;cursor:pointer}.hk-v37-an-seg-t{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hk-v37-an-seg b{flex:none;font-variant-numeric:tabular-nums;font-weight:700}.hk-v37-an-seg button[aria-selected=true]{color:var(--text);border-color:color-mix(in srgb,var(--text) 30%,var(--line));background:var(--panel)}",
      ".hk-v37-an-lanes{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}",
      ".hk-v37-an-lane{border:1px solid var(--line);border-radius:11px;background:var(--panel2);overflow:hidden}",
      ".hk-v37-an-hd{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:8px 10px;border-bottom:1px solid var(--line);border-top:2px solid currentColor;font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.02em}.hk-v37-an-hd.buy{color:var(--ink-up,var(--up))}.hk-v37-an-hd.near{color:var(--ink-link,var(--link))}.hk-v37-an-hd.wait{color:var(--ink-warn,var(--warn))}.hk-v37-an-hd.avoid{color:var(--ink-down,var(--down))}.hk-v37-an-hd b{font-variant-numeric:tabular-nums;color:var(--muted);font-weight:700}",
      ".hk-v37-an-row{display:flex;width:100%;align-items:center;justify-content:space-between;gap:8px;min-height:32px;padding:5px 10px;border:0;border-top:1px solid color-mix(in srgb,var(--line) 70%,transparent);background:transparent;color:inherit;font-size:12.6px;font-weight:650;text-align:left;cursor:pointer}.hk-v37-an-hd+.hk-v37-an-row{border-top:0}.hk-v37-an-row:hover,.hk-v37-an-row.is-active{background:color-mix(in srgb,var(--link) 6%,transparent)}.hk-v37-an-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hk-v37-an-n{flex:none;color:var(--muted);font-size:10.6px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}",
      ".hk-v37-an-empty{padding:12px 10px;color:var(--muted);font-size:12px;text-align:center}",
      ".hk-v37-an-more{display:block;width:100%;padding:7px 10px;border:0;border-top:1px dashed color-mix(in srgb,var(--line) 80%,transparent);background:transparent;color:var(--muted);font-size:11px;font-weight:650;cursor:pointer}.hk-v37-an-more:hover{color:var(--text)}",
      ".hk-v37-panel{margin-bottom:14px;border:1px solid var(--line);border-radius:13px;background:var(--panel);box-shadow:var(--card-shadow);overflow:hidden}.hk-v37-sec-hd{min-height:54px;display:flex;align-items:center;gap:10px;padding:0 15px;border-bottom:1px solid var(--line)}.hk-v37-sec-hd h2{margin:0;font-size:18px;font-weight:650;letter-spacing:-.012em}.hk-v37-sec-spacer{flex:1}.hk-v37-link{color:var(--ink-link,var(--link));font-size:13px;font-weight:600;text-decoration:none}.hk-v37-link:hover{text-decoration:underline}",
      ".hk-v37-lead-list{padding:2px 0}.hk-v37-lead-list-h{display:flex;justify-content:space-between;padding:11px 14px 10px;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}",
      ".hk-v37-lead-row{position:relative;width:100%;min-height:58px;display:grid;grid-template-columns:30px minmax(0,1fr) auto 34px;align-items:center;gap:9px;padding:10px 14px;border:0;border-top:1px solid color-mix(in srgb,var(--line) 72%,transparent);background:transparent;color:inherit;text-align:left;cursor:pointer;overflow:hidden;transition:.15s ease}.hk-v37-lead-row:after{content:\"\";position:absolute;left:0;bottom:0;width:var(--breadth,8%);height:1px;background:color-mix(in srgb,var(--link) 44%,transparent);opacity:.5}.hk-v37-lead-row:hover,.hk-v37-lead-row.is-active{background:color-mix(in srgb,var(--link) 6%,transparent)}.hk-v37-rank{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.5px}.hk-v37-lead-name{display:block;font-size:14.7px;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hk-v37-leaders{display:inline-block;margin-top:3px;color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}.hk-v37-cycle{display:inline-block;margin-top:3px;color:var(--muted);font-size:11px;white-space:nowrap}.hk-v37-count{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.7px;text-align:right}",
      ".hk-v37-stance{height:24px;display:inline-flex;align-items:center;padding:0 9px;border:1px solid currentColor;border-radius:6px;font-size:10px;font-weight:750;text-transform:uppercase;white-space:nowrap}.hk-v37-stance.buy{color:var(--ink-up,var(--up))}.hk-v37-stance.near{color:var(--ink-link,var(--link))}.hk-v37-stance.wait{color:var(--ink-warn,var(--warn))}.hk-v37-stance.avoid{color:var(--ink-down,var(--down))}.hk-v37-stance.none{color:var(--muted)}",
      ".hk-v37-expand-wrap{display:flex;justify-content:center;padding:9px 12px 11px;border-top:1px solid var(--line);background:color-mix(in srgb,var(--panel2) 32%,transparent)}.hk-v37-expand{height:35px;padding:0 14px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--text);font-size:12.5px;font-weight:650;cursor:pointer}.hk-v37-expand:hover{border-color:color-mix(in srgb,var(--text) 30%,var(--line));transform:translateY(-1px)}",
      ".hk-v37-controls{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.hk-v37-seg{display:inline-flex;gap:3px;padding:3px;border:1px solid var(--line);border-radius:9px;background:var(--panel2)}.hk-v37-seg button{height:36px;padding:0 14px;border:1px solid transparent;border-radius:7px;background:transparent;color:var(--muted);font-size:13.1px;font-weight:650;cursor:pointer}.hk-v37-seg button[aria-selected=true]{background:var(--panel);border-color:var(--line);color:var(--text);box-shadow:0 1px 4px rgba(0,0,0,.12)}.hk-v37-result{color:var(--muted);font-size:12px;white-space:nowrap}.hk-v37-filter{display:none;height:32px;align-items:center;padding:0 10px;border:1px solid color-mix(in srgb,var(--link) 35%,var(--line));border-radius:999px;background:color-mix(in srgb,var(--link) 7%,transparent);color:var(--text);font-size:12px;cursor:pointer}.hk-v37-filter.is-on{display:inline-flex}",
      /* Grid/Table XOR overrides (same [hidden] trap as Canada — the UA sheet's
         [hidden]{display:none} loses to `.pvcard{display:flex}` and
         `.hk-v37-card-grid{display:grid}` unless scoped explicitly here). */
      ".hk-v37-card-grid[hidden]{display:none!important}.hk-v37-card-grid .pvcard[hidden]{display:none!important}" +
      /* theme.js's row-mode show-more (site/theme.js initShowMore, ~line 4842+)
         keeps a running `items` array of the original #standouts grid
         children captured at its own init — the exact .pvcard nodes
         collectCards() moves into this grid, not copies. Its window
         'resize' listener and ResizeObserver re-run render() on that array
         whenever the column count changes (or an inactive tab becomes
         visible), re-adding
         .sm-hidden (theme.css: display:none!important) to any card past its
         own page threshold — a one-shot classList.remove() at mount time
         does not un-wire that listener. Without this override, a resize (or
         a Table→Grid round trip that lets the observer fire) can silently
         delete moved cards from the composed grid while hk-v37-result's
         counter keeps counting them as shown. `.pvcard[hidden]` above still
         wins on a genuinely filtered-out card: two classes + one attribute
         (0,3,0) beats two classes (0,2,0), so this rule only rescues cards
         theme.js hid on its own initiative, never a card this composer's
         own Top Picks/leadership filter intentionally hid via `hidden`. */
      ".hk-v37-card-grid .sm-hidden{display:flex!important}" +
      ".hk-v37-card-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;padding:14px}.hk-v37-card-grid .pvcard{min-width:0;height:100%;font-family:" + FONT_UI + ";transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}.hk-v37-card-grid .pvcard:hover{transform:translateY(-2px)}.hk-v37-card-grid .pv-chart svg{height:82px!important}.hk-v37-card-grid .pv-bd{padding:14px 14px 12px!important}.hk-v37-card-grid .pv-tk{font-family:" + FONT_UI + "!important;font-size:16.7px!important;font-weight:700!important;letter-spacing:-.012em!important}.hk-v37-card-grid .pv-nm{font-family:" + FONT_UI + "!important;font-size:12.5px!important}.hk-v37-card-grid .pv-ind{font-size:11.1px!important}.hk-v37-card-grid .pv-edge{font-family:" + FONT_UI + "!important}.hk-v37-card-grid .pv-edn{font-size:16px!important}.hk-v37-card-grid .nb-px.pv-px{font-family:" + FONT_UI + "!important;font-size:15.8px!important;font-weight:750!important}.hk-v37-card-grid .nb-chg.pv-chg{font-family:" + FONT_UI + "!important;font-size:13.4px!important;font-weight:750!important}.hk-v37-card-grid .pv-chip{font-size:10.8px!important}.hk-v37-card-grid .pv-life-w,.hk-v37-card-grid .pv-stl{font-size:11.1px!important}.hk-v37-card-grid .pv-zn{min-height:42px!important;font-size:11.6px!important}.hk-v37-card-grid .pv-znr,.hk-v37-card-grid .pv-znm{font-family:" + FONT_UI + "!important;font-size:11.8px!important}",
      /* Selection halo — neutral/cool ring on the OWNER's own .pv-featured class
         (never a synthetic top-N marker; the owner already flags Featured on the
         card). Selection stays neutral; action (buy/near/wait/avoid) owns hue via
         the card's own .pv-* verb classes, untouched here. */
      ".hk-v37-card-grid .pvcard.pv-featured{border-color:color-mix(in srgb,var(--link) 20%,var(--line));box-shadow:0 0 0 1px color-mix(in srgb,var(--link) 8%,transparent),0 0 24px -16px color-mix(in srgb,var(--link) 42%,transparent),0 8px 24px -20px rgba(0,0,0,.55)}html[data-theme=light] .hk-v37-card-grid .pvcard.pv-featured{background:#fff;border-color:color-mix(in srgb,var(--link) 18%,var(--line));box-shadow:0 0 0 1px color-mix(in srgb,var(--link) 7%,transparent),0 10px 26px -22px color-mix(in srgb,var(--link) 30%,transparent)}.hk-v37-empty{grid-column:1/-1;padding:36px 16px;text-align:center;color:var(--muted);font-size:13px}.hk-v37-empty-switch{display:block;margin:10px auto 0;height:31px;padding:0 13px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--text);font-size:11.8px;font-weight:650;cursor:pointer}.hk-v37-empty-switch:hover{border-color:color-mix(in srgb,var(--text) 30%,var(--line));transform:translateY(-1px)}",
      /* Table pane. No live-quote enhancement — HK has no per-ticker live quote
         plane (the site-wide quote store carries zero HK symbols; the card's
         own nb-chg node is a server-baked "—"), so the table price column is
         left exactly as StockTable.js renders it. */
      ".hk-v37-table{padding:12px 14px 15px}.hk-v37-table[hidden]{display:none!important}.hk-v37-table #stocktable-wrap{display:block!important}.hk-v37-table .stf-row,.hk-v37-table .stf-controls{font-family:" + FONT_UI + "!important}.hk-v37-table :is(input,select,button){min-height:38px;font-size:12.8px!important}.hk-v37-table .st-table{font-family:" + FONT_UI + "!important;font-size:13.3px!important}.hk-v37-table .st-table th{font-size:11px!important;padding:11px 10px!important}.hk-v37-table .st-table td{padding:11px 10px!important}.hk-v37-table .st-table td:nth-child(2) b{font-family:" + FONT_UI + "!important;font-size:13.8px}.hk-v37-table tr.hk-v37-hidden{display:none!important}",
      ".hk-v37-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:11px 14px}.hk-v37-tools b{font-size:12.8px;margin-right:2px}.hk-v37-tool,.hk-v37-tool-toggle{height:37px;display:inline-flex;align-items:center;padding:0 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);color:var(--muted);font-size:12.1px;font-weight:600;text-decoration:none;cursor:pointer}.hk-v37-tool:hover,.hk-v37-tool-toggle:hover{color:var(--text);border-color:color-mix(in srgb,var(--text) 28%,var(--line));transform:translateY(-1px)}.hk-v37-tool-toggle[aria-pressed=true]{background:var(--panel);border-color:color-mix(in srgb,var(--link) 40%,var(--line));color:var(--text)}",
      /* Evidence & Record — the moved `.trd-wrap` chip + dialog keep their own box
         (border/background/padding) from _track_record_dlg.html.j2's own scoped
         stylesheet; this only trims the outer wrapping and matches the hk-v37
         font stack (font smoothing only, no restyle of the chip itself). */
      ".hk-v37-evidence-body{display:flex;flex-direction:column;align-items:center;gap:6px;padding:13px 14px 15px;font-family:" + FONT_UI + "}",
      /* V3.8: the modal group-action band is gone — the at-rest What to Act
         On Now panel above Prophet is the one home for group action (§13.1:
         group action must not be recoverable only through Expand leadership,
         and two homes would be duplication, not compression). */
      ".hk-v37-modal{position:fixed;inset:0;z-index:2147481000;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(4,7,12,.62);backdrop-filter:blur(8px)}.hk-v37-modal.is-open{display:flex}.hk-v37-modal-card{width:min(1180px,calc(100vw - 32px));max-height:min(820px,calc(100vh - 36px));display:flex;flex-direction:column;border:1px solid var(--line);border-radius:15px;background:var(--panel);box-shadow:0 30px 90px rgba(0,0,0,.5);overflow:hidden}html[data-theme=light] .hk-v37-modal{background:rgba(50,64,90,.22)}html[data-theme=light] .hk-v37-modal-card{box-shadow:0 24px 70px rgba(20,32,64,.2)}.hk-v37-modal-hd{min-height:56px;display:flex;align-items:center;padding:0 15px;border-bottom:1px solid var(--line)}.hk-v37-modal-hd h3{margin:0;font-size:19px;font-weight:650}.hk-v37-modal-x{margin-left:auto;width:36px;height:36px;border:1px solid var(--line);border-radius:9px;background:var(--panel2);color:var(--text);font-size:21px;cursor:pointer}.hk-v37-modal-body{overflow:auto;padding:14px}.hk-v37-modal-pane{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel2)}.hk-v37-modal-pane h4{margin:0;padding:11px 12px;border-bottom:1px solid var(--line);font-size:13px}.hk-v37-modal-table{width:100%;border-collapse:collapse;font-size:12.8px}.hk-v37-modal-table th{padding:9px 10px;color:var(--muted);font-size:10.8px;text-align:left;border-bottom:1px solid var(--line)}.hk-v37-modal-table td{padding:10px;border-bottom:1px solid color-mix(in srgb,var(--line) 70%,transparent)}.hk-v37-modal-table tbody tr{cursor:pointer}.hk-v37-modal-table tbody tr:hover{background:color-mix(in srgb,var(--link) 6%,transparent)}.hk-v37-modal-table .num,.hk-v37-modal-table .leaders{color:var(--muted)}",
      /* Southbound subband — three read-only bilingual rows, text only, no charts. */
      ".hk-v37-modal-sb{margin-top:14px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--panel2)}.hk-v37-modal-sb table{width:100%;border-collapse:collapse;font-size:12.6px}.hk-v37-modal-sb td{padding:9px 12px;border-top:1px solid color-mix(in srgb,var(--line) 70%,transparent);vertical-align:top}.hk-v37-modal-sb tr:first-child td{border-top:0}.hk-v37-sb-label{white-space:nowrap;color:var(--muted);font-weight:650;width:1%}",
      /* Mobile Act-Now grammar (§5.5): one horizontal segmented lane selector
         with every lane title+count, one lane body at a time beneath it, no
         four stacked giant lane cards, no horizontal overflow. */
      "@media(max-width:1200px){.hk-v37-card-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.hk-v37-an-lanes{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:900px){.hk-v37-head{flex-wrap:wrap}.hk-v37-head-spacer{display:none}.hk-v37-card-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.hk-v37{width:min(100% - 20px,680px);margin-top:12px;font-size:15.8px}.hk-v37-head{gap:8px}.hk-v37-head h1{width:100%;font-size:27.5px}.hk-v37-sec-hd{align-items:flex-start;flex-wrap:wrap;padding:11px 12px}.hk-v37-sec-hd h2{font-size:17px}.hk-v37-flow{width:100%;max-width:none;white-space:normal}.hk-v37-controls{width:100%}.hk-v37-an-seg{display:flex}.hk-v37-an-lanes{grid-template-columns:1fr}.hk-v37-an-lane{display:none}.hk-v37-an-lane.is-current{display:block}.hk-v37-card-grid{grid-template-columns:1fr;padding:10px;gap:10px}.hk-v37-card-grid .pv-tk{font-size:16.3px!important}.hk-v37-card-grid .nb-px.pv-px{font-size:15.5px!important}.hk-v37-card-grid .nb-chg.pv-chg{font-size:13.1px!important}.hk-v37-modal{padding:8px}.hk-v37-modal-card{width:100%;max-height:calc(100vh - 16px)}.hk-v37-evidence-body{padding:11px 10px 13px}}"
    ].join("\n");
    document.head.appendChild(css);
  }

  /* Leadership & Rotation row (V3.8 §6): the rank cell is `RS #N` — the
     owner's own Sector Rotation number under a visible basis label — and a
     sector the owner did not rank shows "—", never a minted number. The
     action stance chip stays a SEPARATE field: `RS #1 · Reduce / Avoid` is a
     legitimate, informative combination (trend strength vs entry timing),
     not a contradiction to be sorted away. The count cell is the current
     Prophet-name count and renders "—" when membership is unknown. */
  function leadRow(x, max) {
    var breadth = Math.max(8, Math.round(((x.count || 0) / Math.max(1, max)) * 100));
    var leadersTxt = x.leaders.length ? x.leaders.join(" · ") : "—";
    var cycleHtml = (x.cycleState && x.cycleState.en) ? ' <span class="hk-v37-cycle">· ' + bi(x.cycleState.en, x.cycleState.zh) + '</span>' : '';
    var rankTxt = x.rank != null ? "RS #" + x.rank : "—";
    return '<button class="hk-v37-lead-row" data-hk-lead-id="' + esc(x.id) + '" style="--breadth:' + breadth + '%"><span class="hk-v37-rank">' + esc(rankTxt) + '</span><span><span class="hk-v37-lead-name">' + bi(x.name.en, x.name.zh) + '</span><span class="hk-v37-leaders">' + esc(leadersTxt) + '</span>' + cycleHtml + '</span><span class="hk-v37-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span><span class="hk-v37-count">' + (x.count != null ? x.count : "—") + '</span></button>';
  }
  function renderLeadership() {
    var host = qs("#hk-v37-lead-list");
    if (!host) return;
    /* At rest: at most the top 5 owner-ranked sectors before expansion (§6.3). */
    var top = firstN(state.sectors, 5), max = Math.max.apply(Math, [1].concat(top.map(function (x) { return x.count || 0; })));
    host.innerHTML = '<div class="hk-v37-lead-list-h"><span>' + bi("Sectors", "板块") + '</span><span>' + bi("Prophet", "候选") + '</span></div>' +
      (top.length ? top.map(function (x) { return leadRow(x, max); }).join("") : '<div class="hk-v37-empty">' + bi("Ranking unavailable", "排名暂不可用") + '</div>');
    markLeadership();
  }
  /* Southbound flow cue — the FIRST .sbah-card inside #mainland-money (its
     Southbound flow card, first in DOM order). Gated on MATERIALITY, not
     mere node existence: the owner already computes a directional marker for
     this exact card — .sbah-sig carries sig-in (inflow) / sig-out (outflow) /
     sig-neu (templates/hk.html.j2:4698, `_sbsig`, "no strong tilt") — and
     sig-neu is precisely the non-material case the architecture forbids
     surfacing ("cue absent when stale, unavailable, or non-material"). A
     neutral card (or a card/sig node the owner didn't render at all) yields
     no cue and no placeholder; this must never become a permanent statistic.
     V3.8 home: the Leadership & Rotation header (§4 — a market-specific
     material cue may remain compactly in the Leadership header only when a
     canonical producer owns it); the standalone Leading Now strip is gone. */
  function southboundFirstRead() {
    var card = qs("#mainland-money .sbah-card");
    if (!card) return null;
    var sig = qs(".sbah-sig", card);
    if (!sig || sig.classList.contains("sig-neu")) return null;
    var read = qs(".sbah-read", card);
    if (!read) return null;
    var d = dual(read);
    return d.en ? d : null;
  }
  function renderFlowCue() {
    var host = qs("#hk-v37-flow"); if (!host) return;
    var sb = southboundFirstRead();
    host.innerHTML = sb ? bi(sb.en, sb.zh) : "";
    host.hidden = !sb;
  }

  /* What to Act On Now (V3.8 §5) — the restored high-frequency customer job,
     AT REST above Prophet. Sectors partition by lane 1:1 via `tone`, minted
     straight from LANE_DEFS in collectSectors() — never a second lane
     vocabulary. Row rows carry the same data-hk-lead-id the leadership rows
     use, so activation runs through the one existing delegation path
     (activate(): filter only — the Top Picks | All Candidates population is
     never touched). At rest each lane shows at most AN_AT_REST rows; the
     remainder is behind a per-lane View all toggle. A lane's Prophet count
     chip renders only when canonical membership is known — unknown
     membership must never render as 0. */
  var AN_AT_REST = 3;
  function anLaneItems(tone) {
    return state.sectors.filter(function (x) { return x.tone === tone; });
  }
  function anRowHtml(x) {
    var countHtml = x.count != null ? '<span class="hk-v37-an-n">' + x.count + ' · ' + bi("Prophet", "候选") + '</span>' : '';
    return '<button class="hk-v37-an-row" type="button" data-hk-lead-id="' + esc(x.id) + '"><span class="hk-v37-an-name">' + bi(x.name.en, x.name.zh) + '</span>' + countHtml + '</button>';
  }
  function anLaneHtml(lane) {
    var items = anLaneItems(lane.tone), open = !!state.anOpen[lane.tone];
    var shown = open ? items : firstN(items, AN_AT_REST);
    var body = shown.length ? shown.map(anRowHtml).join("") : '<div class="hk-v37-an-empty">—</div>';
    var more = items.length > AN_AT_REST
      ? '<button class="hk-v37-an-more" type="button" data-hk-an-view="' + esc(lane.tone) + '" aria-expanded="' + open + '">' +
        (open ? bi("Show fewer", "收起") : bi("View all " + items.length, "查看全部 " + items.length)) + '</button>'
      : '';
    var current = state.anLane === lane.tone ? " is-current" : "";
    return '<div class="hk-v37-an-lane' + current + '" data-hk-an-lane-body="' + esc(lane.tone) + '"><div class="hk-v37-an-hd ' + lane.tone + '"><span>' + bi(lane.en, lane.zh) + '</span><b>' + items.length + '</b></div>' + body + more + '</div>';
  }
  function renderActNow() {
    var host = qs("#hk-v37-an-body"); if (!host) return;
    if (state.anLane == null || !anLaneItems(state.anLane).length) {
      /* Mobile default lane: Buy Now when non-empty, else the next non-empty
         lane in the owner's own urgency order (§5.5). */
      for (var i = 0; i < LANE_DEFS.length; i++) {
        if (anLaneItems(LANE_DEFS[i].tone).length) { state.anLane = LANE_DEFS[i].tone; break; }
      }
      if (state.anLane == null) state.anLane = LANE_DEFS[0].tone;
    }
    /* The count rides as a separate fixed badge so a narrow segment button
       ellipsizes the title only — §5.5 requires every lane title AND count
       accessible from the selector. */
    var seg = '<div class="hk-v37-an-seg" role="tablist">' + LANE_DEFS.map(function (lane) {
      return '<button type="button" role="tab" data-hk-an-lane="' + esc(lane.tone) + '" aria-selected="' + (state.anLane === lane.tone) + '"><span class="hk-v37-an-seg-t">' + bi(lane.en, lane.zh) + '</span><b>' + anLaneItems(lane.tone).length + '</b></button>';
    }).join("") + '</div>';
    host.innerHTML = seg + '<div class="hk-v37-an-lanes">' + LANE_DEFS.map(anLaneHtml).join("") + '</div>';
    markLeadership();
  }
  function setAnLane(tone) {
    /* Presentation-only: switching the visible mobile lane must not mutate
       the Prophet selection/filter until a group row is actually chosen. */
    state.anLane = tone; renderActNow();
  }
  function toggleAnLane(tone) {
    state.anOpen[tone] = !state.anOpen[tone]; renderActNow();
  }

  function itemForFilter() {
    if (!state.filter) return null;
    return state.sectors.find(function (x) { return x.id === state.filter; }) || null;
  }
  /* Featured cohort — never a position slice. Top Picks is exactly the set of
     data-ticker values carried by cards the OWNER flagged pv-featured. */
  function sourceSet() {
    if (state.source !== "top") return null;
    return new Set(state.cards.filter(function (c) { return c.classList.contains("pv-featured"); }).map(function (c) { return ticker(c.getAttribute("data-ticker")); }));
  }
  function allowed(tk) {
    var src = sourceSet(), item = itemForFilter();
    if (src && !src.has(tk)) return false;
    if (item && item.members && !item.members.has(tk)) return false;
    return true;
  }
  function markLeadership() {
    qsa("[data-hk-lead-id]", qs("#hk-v37") || document).forEach(function (el) {
      el.classList.toggle("is-active", !!state.filter && el.getAttribute("data-hk-lead-id") === state.filter);
    });
  }
  /* Sol adversarial gate (same law as Canada V3.7): a leadership filter must
     never silently switch the Top Picks / All Candidates population. When the
     active filter leaves zero Top Picks but All Candidates DOES have matches,
     invite the reader to switch deliberately instead of doing it for them.
     A second, distinct empty state covers the zero-featured-cards case: if this
     build has no Featured names at all, Top Picks stays selectable but always
     shows an explicit "no featured names" state — never falls back to All
     Candidates on its own. */
  function emptyStateHtml() {
    if (state.source === "top" && state.featuredCount === 0) {
      return bi("No featured names right now.", "当前暂无精选个股。");
    }
    var item = itemForFilter();
    if (state.source === "top" && item && item.members) {
      var wouldAllShowMore = state.cards.some(function (card) { return item.members.has(ticker(card.getAttribute("data-ticker"))); });
      if (wouldAllShowMore) {
        return bi("No Top Picks in this group.", "该组别中暂无首选。") +
          ' <button class="hk-v37-empty-switch" type="button">' + bi("View All Candidates", "查看全部候选") + '</button>';
      }
    }
    return bi("No names match this leadership filter.", "当前领先筛选下暂无匹配个股。");
  }
  function applyFilter() {
    var shown = 0;
    state.cards.forEach(function (card) { var show = allowed(ticker(card.getAttribute("data-ticker"))); card.hidden = !show; if (show) shown++; });
    var empty = qs("#hk-v37-grid-empty");
    if (empty) { empty.hidden = shown !== 0; if (shown === 0) empty.innerHTML = emptyStateHtml(); }
    var result = qs("#hk-v37-result"); if (result) result.innerHTML = bi(shown + " shown · " + state.cards.length + " on board", "显示 " + shown + " 只 · 榜单共 " + state.cards.length + " 只");
    var pill = qs("#hk-v37-filter"), item = itemForFilter();
    if (pill) { pill.classList.toggle("is-on", !!item); pill.innerHTML = item ? bi("Sector", "板块") + ': ' + bi(item.name.en, item.name.zh) + ' ×' : ""; }
    markLeadership(); applyTableFilter();
  }

  function rowTicker(tr) {
    var direct = ticker(tr.getAttribute("data-ticker")); if (direct && rowsByTicker[direct]) return direct;
    var text = tr.textContent || "";
    for (var i = 0; i < state.rows.length; i++) { var tk = ticker(state.rows[i].ticker); if (tk && text.indexOf(tk) !== -1) return tk; }
    return "";
  }
  /* No live-quote enhancement here (constitution: HK has no canonical live
     quote plane) — applyTableFilter only toggles row visibility, it never
     rewrites cell content. */
  function applyTableFilter() {
    var table = qs("#stocktable-wrap table"); if (!table) return;
    qsa("tbody tr", table).forEach(function (tr) { var tk = rowTicker(tr); tr.classList.toggle("hk-v37-hidden", !!tk && !allowed(tk)); });
  }
  function observeTable() {
    var wrap = qs("#stocktable-wrap"); if (!wrap || tableObserver) return;
    tableObserver = new MutationObserver(function () { requestAnimationFrame(applyTableFilter); });
    tableObserver.observe(wrap, { childList: true, subtree: true }); applyTableFilter();
  }

  function setSource(value) {
    state.source = value === "all" ? "all" : "top";
    qsa("[data-hk-source]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-hk-source") === state.source)); });
    applyFilter();
  }
  function setView(value) {
    state.view = value === "table" ? "table" : "grid";
    try { localStorage.setItem("mdx_stocktable_hk_view", state.view); } catch (e) {}
    qsa("[data-hk-view]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-hk-view") === state.view)); });
    var grid = qs("#hk-v37-card-grid"), table = qs("#hk-v37-table"); if (grid) grid.hidden = state.view !== "grid"; if (table) table.hidden = state.view !== "table";
    if (state.view === "table") applyTableFilter();
  }
  /* Sol adversarial gate: leadership activation sets the filter only — it must
     never force-switch the Top Picks / All Candidates population. applyFilter()
     (not setSource()) is what re-renders the grid here. */
  function activate(id) {
    state.filter = id; applyFilter(); closeModal();
    var prophet = qs("#hk-v37-prophet"); if (prophet) prophet.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* Expanded Leadership rows: same axis law as leadRow() — `RS #N` only from
     the owner's own rank (null renders "—", never a minted number), stance a
     separate chip, count "—" when membership is unknown. */
  function modalRows(items) {
    return items.length ? items.map(function (x) { return '<tr tabindex="0" data-hk-modal-id="' + esc(x.id) + '"><td class="num">' + esc(x.rank != null ? "RS #" + x.rank : "—") + '</td><td><b>' + bi(x.name.en, x.name.zh) + '</b></td><td><span class="hk-v37-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span></td><td>' + (x.cycleState && x.cycleState.en ? bi(x.cycleState.en, x.cycleState.zh) : "—") + '</td><td class="leaders">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + '</td><td class="num">' + (x.count != null ? x.count : "—") + '</td></tr>'; }).join("") : '<tr><td colspan="6">—</td></tr>';
  }
  function modalPaneHtml() {
    return '<div class="hk-v37-modal-pane"><h4>' + bi("Leadership & Rotation", "领先与轮动") + ' <span class="hk-v37-lead-basis">' + bi("Relative strength vs HSI", "相对恒生指数") + '</span></h4><table class="hk-v37-modal-table"><thead><tr><th>' + bi("Rank", "排名") + '</th><th>' + bi("Name", "名称") + '</th><th>' + bi("Action", "操作状态") + '</th><th>' + bi("Cycle state", "周期状态") + '</th><th>' + bi("Leaders", "领先个股") + '</th><th>' + bi("Prophet", "候选") + '</th></tr></thead><tbody>' + modalRows(state.sectors) + '</tbody></table></div>';
  }
  /* Southbound subband (INTEGRATE_COMPRESS) — the three .sbah-read sentences
     from #mainland-money's cards (Southbound flow / Flow vs price / A/H
     premium), read-only, text only, no charts. Rendered only for cards that
     exist; zero cards -> omit the subband entirely. The subband itself is
     titled "Mainland flow"/"内地资金"; each row keeps its own owner-native
     label (the card's .sbah-t text, e.g. "Southbound flow") so three distinct
     reads stay distinguishable under one heading. */
  function southboundSubbandHtml() {
    var cards = qsa("#mainland-money .sbah-card");
    if (!cards.length) return "";
    var rows = cards.map(function (card) {
      var read = qs(".sbah-read", card); if (!read) return "";
      var r = dual(read); if (!r.en) return "";
      var l = dual(qs(".sbah-t", card));
      return '<tr><td class="hk-v37-sb-label">' + bi(l.en || "Mainland flow", l.zh || "内地资金") + '</td><td>' + bi(r.en, r.zh) + '</td></tr>';
    }).join("");
    if (!rows) return "";
    return '<div class="hk-v37-modal-sb"><h4>' + bi("Mainland flow", "内地资金") + '</h4><table><tbody>' + rows + '</tbody></table></div>';
  }
  function openModal() {
    var modal = qs("#hk-v37-modal"); if (!modal) return;
    qs("#hk-v37-modal-body", modal).innerHTML = modalPaneHtml() + southboundSubbandHtml();
    modal.classList.add("is-open"); modal.setAttribute("aria-hidden", "false"); document.documentElement.style.overflow = "hidden";
  }
  /* activate() calls closeModal() unconditionally (leadership rows are
     clickable both in the page and inside the modal), so this must be a
     no-op when the modal was never open — otherwise every plain leadership
     click clears document.documentElement.style.overflow regardless of
     whether anything set it. */
  function closeModal() {
    var modal = qs("#hk-v37-modal");
    if (!modal || !modal.classList.contains("is-open")) return;
    modal.classList.remove("is-open"); modal.setAttribute("aria-hidden", "true"); document.documentElement.style.overflow = "";
  }

  function bind(root) {
    root.addEventListener("click", function (e) {
      var b = e.target.closest("[data-hk-source]"); if (b) return setSource(b.getAttribute("data-hk-source"));
      b = e.target.closest("[data-hk-view]"); if (b) return setView(b.getAttribute("data-hk-view"));
      /* Act-Now presentation controls come BEFORE the data-hk-lead-id row
         handler only in the sense that they are distinct targets — the
         segment/View-all buttons never carry data-hk-lead-id, and neither
         handler touches source/filter. */
      b = e.target.closest("[data-hk-an-lane]"); if (b) return setAnLane(b.getAttribute("data-hk-an-lane"));
      b = e.target.closest("[data-hk-an-view]"); if (b) return toggleAnLane(b.getAttribute("data-hk-an-view"));
      b = e.target.closest("[data-hk-lead-id]"); if (b) return activate(b.getAttribute("data-hk-lead-id"));
      if (e.target.closest("#hk-v37-filter")) { state.filter = null; return applyFilter(); }
      if (e.target.closest("#hk-v37-expand")) return openModal();
      if (e.target.closest(".hk-v37-empty-switch")) return setSource("all");
      b = e.target.closest("[data-hk-tool]"); if (b) return toggleTool(b.getAttribute("data-hk-tool"));
    });
  }

  /* Evidence & Record (change 5, restores Track Record). HK ships the shared
     _track_record_dlg.html.j2 component WITHOUT Canada's wrapping `.trk` div —
     #track-record directly holds two SIBLING `.trd-wrap` elements: a `<span>`
     around #trd-btn and a `<div style="display:contents">` around #trd-dlg
     (verified: site/hk_stocks.html:3765). Moving only the first `.trd-wrap`
     match (Canada's `.trk` idiom applied literally) would strand the dialog
     inside the hidden legacy panel, where `display:none` on the ancestor
     suppresses the fixed-position dialog too — clicking "Track record" would
     do nothing. Both `.trd-wrap` siblings are moved together, in DOM order;
     never rebuilt, never recomputed, never fetched by this file (the dialog
     fetches its own ledger via its own data-url). */
  function evidenceWraps() {
    var host = qs("#track-record");
    if (!host || !qs("#trd-btn", host)) return [];
    return qsa(".trd-wrap", host);
  }
  function evidenceSectionHtml() {
    return '<section class="hk-v37-panel" id="hk-v37-evidence"><div class="hk-v37-sec-hd"><h2>' + bi("Evidence & Record", "证据与往绩") + '</h2><span class="hk-v37-sec-spacer"></span><a class="hk-v37-link" href="measurement.html">' + bi("Methodology →", "方法论 →") + '</a></div><div class="hk-v37-evidence-body" id="hk-v37-evidence-body"></div></section>';
  }

  /* Research Tools (change 6) — one plain destination link plus on-demand
     disclosure toggles for the owner's own live specialist panels, unhidden IN
     PLACE below the composer (the composer main is inserted right after
     .site-nav, so every #hk-velocity-desk / #washout-watch / #mainland-money /
     #hk-screener panel already sits further down the document and just needs
     its display restored). Only one panel revealed at a time; a second click
     on its own toggle re-hides it. */
  function toggleTool(sel) {
    var target = qs(sel); if (!target) return;
    var wasRevealed = target.classList.contains("hk-v37-revealed");
    qsa(".panel.hk-v37-revealed").forEach(function (p) { p.classList.remove("hk-v37-revealed"); });
    qsa("[data-hk-tool]").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
    if (!wasRevealed) {
      target.classList.add("hk-v37-revealed");
      var btn = qs('[data-hk-tool="' + sel + '"]'); if (btn) btn.setAttribute("aria-pressed", "true");
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  function researchToolsHtml() {
    var toggles = TOOL_DEFS.filter(function (def) { return !!qs(def.sel); }).map(function (def) {
      return '<button class="hk-v37-tool-toggle" type="button" data-hk-tool="' + esc(def.sel) + '" aria-pressed="false">' + bi(def.en, def.zh) + '</button>';
    }).join("");
    return '<section class="hk-v37-panel"><div class="hk-v37-tools"><b>' + bi("Research tools", "研究工具") + '</b><a class="hk-v37-tool" href="hk.html">' + bi("HK Macro", "港股宏观") + ' ↗</a>' + toggles + '</div></section>';
  }

  function buildShell(payload) {
    var nav = qs(".site-nav"), standouts = qs("#standouts"), tableWrap = qs("#stocktable-wrap");
    if (!nav || !standouts || !tableWrap || !state.cards.length) return false;
    injectCss();
    var wraps = evidenceWraps();
    var bd = boardDate(payload.as_of || ""), main = document.createElement("main");
    main.className = "hk-v37"; main.id = "hk-v37";
    /* V3.8 page grammar (§4): Market Header → What to Act On Now → Prophet →
       Leadership & Rotation → Evidence & Record → Research Tools. The Act-Now
       panel renders only when the owner's action lanes actually populated at
       least one sector (action owner missing → omit, never synthesize action
       from leadership rank). */
    var hasActNow = state.sectors.some(function (x) {
      return LANE_DEFS.some(function (lane) { return lane.tone === x.tone; });
    });
    main.innerHTML = '<header class="hk-v37-head"><h1>' + bi("Hong Kong Stocks", "港股") + '</h1><span class="hk-v37-head-spacer"></span><span class="hk-v37-chip">' + bi("Board " + bd.en, "榜单 " + bd.zh) + '</span></header>' +
      (hasActNow ? '<section class="hk-v37-panel" id="hk-v37-actnow"><div class="hk-v37-sec-hd"><h2>' + bi("What to Act On Now", "现在行动") + '</h2></div><div class="hk-v37-an-body" id="hk-v37-an-body"></div></section>' : '') +
      '<section class="hk-v37-panel" id="hk-v37-prophet"><div class="hk-v37-sec-hd"><h2>Prophet</h2><span class="hk-v37-result" id="hk-v37-result"></span><span class="hk-v37-sec-spacer"></span><div class="hk-v37-controls"><button class="hk-v37-filter" id="hk-v37-filter" type="button"></button><span class="hk-v37-seg"><button type="button" data-hk-source="top" aria-selected="true">' + bi("Top Picks", "首选") + '</button><button type="button" data-hk-source="all" aria-selected="false">' + bi("All Candidates", "全部候选") + '</button></span><span class="hk-v37-seg"><button type="button" data-hk-view="grid" aria-selected="true">' + bi("Grid", "卡片") + '</button><button type="button" data-hk-view="table" aria-selected="false">' + bi("Table", "表格") + '</button></span></div></div><div class="hk-v37-card-grid" id="hk-v37-card-grid"><div class="hk-v37-empty" id="hk-v37-grid-empty" hidden>' + bi("No names match this leadership filter.", "当前领先筛选下暂无匹配个股。") + '</div></div><div class="hk-v37-table" id="hk-v37-table" hidden></div></section>' +
      '<section class="hk-v37-panel" id="hk-v37-leadership"><div class="hk-v37-sec-hd"><h2>' + bi("Leadership & Rotation", "领先与轮动") + '</h2><span class="hk-v37-lead-basis">' + bi("Relative strength vs HSI", "相对恒生指数") + '</span><span class="hk-v37-sec-spacer"></span><span class="hk-v37-flow" id="hk-v37-flow" hidden></span></div><div class="hk-v37-lead-list" id="hk-v37-lead-list"></div><div class="hk-v37-expand-wrap"><button class="hk-v37-expand" id="hk-v37-expand" type="button">' + bi("Expand leadership", "展开领先排名") + ' ↗</button></div></section>' +
      (wraps.length ? evidenceSectionHtml() : '') +
      researchToolsHtml();
    nav.insertAdjacentElement("afterend", main);
    var grid = qs("#hk-v37-card-grid", main), empty = qs("#hk-v37-grid-empty", grid);
    state.cards.forEach(function (card) { grid.insertBefore(card, empty); });
    qs("#hk-v37-table", main).appendChild(tableWrap);
    if (wraps.length) { var evBody = qs("#hk-v37-evidence-body", main); wraps.forEach(function (w) { evBody.appendChild(w); }); }

    var modal = document.createElement("div"); modal.className = "hk-v37-modal"; modal.id = "hk-v37-modal"; modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = '<div class="hk-v37-modal-card" role="dialog" aria-modal="true" aria-labelledby="hk-v37-modal-title"><div class="hk-v37-modal-hd"><h3 id="hk-v37-modal-title">' + bi("Leadership & Rotation", "领先与轮动") + '</h3><button class="hk-v37-modal-x" type="button" data-hk-modal-close aria-label="Close">×</button></div><div class="hk-v37-modal-body" id="hk-v37-modal-body"></div></div>';
    document.body.appendChild(modal);
    modal.addEventListener("click", function (e) { if (e.target === modal || e.target.closest("[data-hk-modal-close]")) return closeModal(); var r = e.target.closest("[data-hk-modal-id]"); if (r) activate(r.getAttribute("data-hk-modal-id")); });
    modal.addEventListener("keydown", function (e) { var r = e.target.closest("[data-hk-modal-id]"); if (r && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(r.getAttribute("data-hk-modal-id")); } });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

    bind(main); document.body.classList.add("hk-v37-mounted"); renderActNow(); renderLeadership(); renderFlowCue();
    /* setSource (not a bare applyFilter()) so the Top Picks / All Candidates
       segment buttons' aria-selected reflects the computed default — the
       markup above hard-codes Top Picks as selected, which is wrong on a
       zero-featured-cards build where state.source was already set to "all"
       in start(). */
    setSource(state.source);
    try { state.view = localStorage.getItem("mdx_stocktable_hk_view") === "table" ? "table" : "grid"; } catch (e) { state.view = "grid"; }
    setView(state.view); observeTable(); return true;
  }

  /* Abort-to-legacy: bail before any DOM mutation unless every load-bearing
     owner surface exists. Zero network reads anywhere in this file — every
     input above is harvested synchronously from DOM the server already
     rendered, so there is no async race to arbitrate (unlike Canada, which
     awaits two basket/pulse JSON reads). */
  function start() {
    var nav = qs(".site-nav"), standouts = qs("#standouts"), tableWrap = qs("#stocktable-wrap");
    if (!nav || !standouts || !tableWrap) return;
    var payload = parseRows(); if (!payload || !state.rows.length) return;
    state.cards = collectCards(); if (!state.cards.length) return;
    state.featuredCount = state.cards.filter(function (c) { return c.classList.contains("pv-featured"); }).length;
    state.source = state.featuredCount > 0 ? "top" : "all";
    state.sectors = collectSectors();
    buildShell(payload);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}());

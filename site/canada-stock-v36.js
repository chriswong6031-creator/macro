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
   semantics. The server-rendered page owns the canonical shell and every owner
   surface; this file binds interactions in place and reads the existing Canada
   thematic-basket and sector-pulse artifacts as optional enhancement only. */
(function () {
  "use strict";

  var PATH_RE = /(^|\/)canada_stocks\.html$/;
  if (!PATH_RE.test(location.pathname) || window.__mmCanadaStockV36) return;
  window.__mmCanadaStockV36 = true;

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
      /* Presentation markers only: owner order and membership stay untouched. */
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
  function watchPopulation() {
    var grid = qs("#standouts .watch-strip .watch-grid");
    return grid ? qsa("a[href]", grid).length : null;
  }
  function applyFilter() {
    var shown = 0;
    state.cards.forEach(function (card) { var show = allowed(ticker(card.getAttribute("data-ticker"))); card.hidden = !show; if (show) shown++; });
    var empty = qs("#ca-v36-grid-empty");
    if (empty) { empty.hidden = shown !== 0; if (shown === 0) empty.innerHTML = emptyStateHtml(); }
    var board = state.cards.length, result = qs("#ca-v36-result"), watch = watchPopulation();
    if (result) {
      result.innerHTML = watch === null
        ? bi(shown + " cards shown · " + board + " board names · watch unavailable", "显示 " + shown + " 张卡片 · 榜单 " + board + " 只 · 观察名单暂不可用")
        : bi(shown + " cards shown · " + (board + watch) + " current names (" + board + " board + " + watch + " watch)", "显示 " + shown + " 张卡片 · 当前共 " + (board + watch) + " 只（榜单 " + board + " + 观察 " + watch + "）");
    }
    var pill = qs("#ca-v36-filter"), item = itemForFilter();
    if (pill) { pill.hidden = !item; pill.classList.toggle("is-on", !!item); pill.innerHTML = item ? bi(item.kind === "theme" ? "Theme" : "Sector", item.kind === "theme" ? "主题" : "板块") + ': ' + bi(item.name.en, item.name.zh) + ' ×' : ""; }
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
    var board = qs("#standouts");
    if (window.StockTable && typeof window.StockTable._setView === "function") window.StockTable._setView(state.view);
    else if (board) board.classList.toggle("st-table-mode", state.view === "table");
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

  function buildShell(payload) {
    var main = qs("#ca-v36"), modal = qs("#ca-v36-modal");
    if (!main) return false;
    if (main.getAttribute("data-ca-enhanced") !== "true") {
      main.setAttribute("data-ca-enhanced", "true");
      bind(main);
      if (modal) {
        modal.addEventListener("click", function (e) { if (e.target === modal || e.target.closest("[data-ca-modal-close]")) return closeModal(); var r = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]"); if (r) activate(r.getAttribute("data-ca-modal-kind"), r.getAttribute("data-ca-modal-id")); });
        modal.addEventListener("keydown", function (e) { var r = e.target.closest("[data-ca-modal-kind][data-ca-modal-id]"); if (r && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(r.getAttribute("data-ca-modal-kind"), r.getAttribute("data-ca-modal-id")); } });
      }
      document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });
    }
    renderLeadership(); renderFresh(); applyFilter();
    try { state.view = localStorage.getItem("mdx_stocktable_ca_view") === "table" ? "table" : "grid"; } catch (e) { state.view = "grid"; }
    setView(state.view); observeTable(); return true;
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) { if (!r.ok) throw new Error(url + " unavailable"); return r.json(); });
  }
  function start() {
    if (!document.body.classList.contains("page-canada")) return;
    var payload = parseRows() || { rows: [], as_of: "" };
    state.cards = collectCards();
    state.sectors = collectSectors();
    buildShell(payload);

    /* The canonical product is already painted and bound. `sector_pulse_canada`
       is the current published theme rank/reco owner; baskets.json owns members.
       Either optional source may fail without changing shell admission. */
    Promise.all([
      getJson("canadabasketdata/baskets.json").catch(function () { return null; }),
      getJson("canadabasketdata/sector_pulse_canada.json").catch(function () { return null; })
    ]).then(function (parts) {
      state.themes = collectThemes(parts[0], parts[1]);
      renderLeadership();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}());

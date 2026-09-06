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
    anLane: null, anDefault: null, anOpen: {}, anMedia: null,
    anHistoryBound: false, hasThemeRank: false };
  var rowsByTicker = Object.create(null);
  var tableObserver = null;
  var quoteObserver = null;

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
  function quotePlaneState(nodes) {
    var list = Array.prototype.slice.call(nodes || []);
    if (!list.length) return { state: "unavailable", detail: "" };
    var accepted = { "1": "live", delayed: "delayed", stale: "stale", closed: "closed" };
    var prefix = {
      live: /^live · /,
      delayed: /^≥\d+-min delayed · /,
      stale: /^stale · /,
      closed: /^market closed · /
    };
    var first = null;
    for (var i = 0; i < list.length; i++) {
      var raw = list[i] && list[i].getAttribute ? list[i].getAttribute("data-live") : null;
      var stateName = accepted[raw];
      var detail = list[i] && list[i].getAttribute ? String(list[i].getAttribute("title") || "").trim() : "";
      if (!stateName || !prefix[stateName].test(detail)) return { state: "unavailable", detail: "" };
      if (first && first.state !== stateName) return { state: "unavailable", detail: "" };
      if (!first) first = { state: stateName, detail: detail };
    }
    return first || { state: "unavailable", detail: "" };
  }
  function quoteStatusCopy(receipt) {
    if (!receipt || receipt.state === "unavailable") {
      return { en: "Quotes unavailable · awaiting confirmation", zh: "报价暂不可用 · 等待确认" };
    }
    var bits = receipt.detail.split(" · "), basis = bits.slice(1).join(" · ");
    var lead = receipt.state === "live" ? { en: "LIVE", zh: "实时" }
      : receipt.state === "delayed" ? { en: bits[0].toUpperCase(), zh: bits[0] + " · 延迟" }
      : receipt.state === "stale" ? { en: "STALE", zh: "陈旧" }
      : { en: "MARKET CLOSED", zh: "市场已收盘" };
    return { en: lead.en + (basis ? " · " + basis : ""), zh: lead.zh + (basis ? " · " + basis : "") };
  }
  function renderQuoteStatus() {
    var host = qs("#ca-v36-quote-status");
    if (!host) return;
    var receipt = quotePlaneState(qsa('#ca-v36-card-grid .nb-px[data-sym][data-mkt="ca"]'));
    var copy = quoteStatusCopy(receipt);
    host.setAttribute("data-quote-state", receipt.state);
    host.innerHTML = '<span class="ca-v36-quote-dot" aria-hidden="true"></span><b>' + bi(copy.en, copy.zh) + '</b>';
  }
  function observeQuoteStatus() {
    var owner = qs("#ca-v36-card-grid");
    renderQuoteStatus();
    if (!owner || quoteObserver || !window.MutationObserver) return;
    quoteObserver = new MutationObserver(function (mutations) {
      if (mutations.some(function (mutation) { return mutation.type === "attributes"; })) renderQuoteStatus();
    });
    quoteObserver.observe(owner, { subtree: true, attributes: true, attributeFilter: ["data-live", "title"] });
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

  /* What to Act On Now is server-owned. The enhancer may change only the
     selector state, lane visibility, focus, and the active lane's in-place
     expansion. It never creates, moves, clones, filters, or reorders rows. */
  function actionHost() { return qs("#ca-v36-an-body"); }
  function actionTabs() {
    var host = actionHost();
    return host ? qsa("[data-ca-an-lane]", host) : [];
  }
  function actionLanes() {
    var host = actionHost();
    return host ? qsa("[data-ca-an-lane-body]", host) : [];
  }
  function toneFromActionHash() {
    var id = location.hash ? location.hash.slice(1) : "";
    var lane = actionLanes().find(function (node) { return node.id === id; });
    return lane ? lane.getAttribute("data-ca-an-lane-body") : null;
  }
  function laneIdForTone(tone) {
    var tab = actionTabs().find(function (node) { return node.getAttribute("data-ca-an-lane") === tone; });
    var href = tab && tab.getAttribute("href");
    return href && /^#[A-Za-z][A-Za-z0-9_.:-]*$/.test(href) ? href.slice(1) : null;
  }
  function writeActionHash(tone, mode) {
    var laneId = laneIdForTone(tone), next = laneId ? "#" + laneId : "";
    if (!next || location.hash === next) return;
    if (mode === "replace") history.replaceState(null, "", next);
    else history.pushState(null, "", next);
  }
  function syncActNow(focusTone) {
    var host = actionHost(); if (!host) return;
    var mobile = window.matchMedia("(max-width: 680px)").matches;
    host.setAttribute("data-active-lane", state.anLane || "");
    var seg = qs(".ca-v36-an-seg", host);
    if (seg) {
      if (mobile) { seg.setAttribute("role", "tablist"); seg.setAttribute("aria-label", "What to Act On Now lanes"); }
      else { seg.removeAttribute("role"); seg.removeAttribute("aria-label"); }
    }
    actionTabs().forEach(function (tab) {
      var tone = tab.getAttribute("data-ca-an-lane"), active = tone === state.anLane;
      var laneId = laneIdForTone(tone);
      if (mobile) {
        tab.id = "ca-v36-an-tab-" + tone;
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-controls", laneId);
        tab.setAttribute("aria-selected", active ? "true" : "false");
        tab.setAttribute("tabindex", active ? "0" : "-1");
      } else {
        tab.removeAttribute("id");
        tab.removeAttribute("role");
        tab.removeAttribute("aria-controls");
        tab.removeAttribute("aria-selected");
        tab.removeAttribute("tabindex");
      }
      if (active && focusTone === tone) tab.focus();
    });
    actionLanes().forEach(function (lane) {
      var tone = lane.getAttribute("data-ca-an-lane-body"), active = tone === state.anLane;
      lane.classList.toggle("is-current", active);
      if (mobile) {
        lane.setAttribute("role", "tabpanel");
        lane.setAttribute("aria-labelledby", "ca-v36-an-tab-" + tone);
        lane.hidden = !active;
      } else {
        lane.removeAttribute("role");
        lane.removeAttribute("aria-labelledby");
        lane.hidden = false;
      }
    });
  }
  function adoptActNow() {
    var host = actionHost(), tabs = actionTabs();
    var selected = tabs.find(function (tab) { return tab.getAttribute("data-ca-an-default") === "true"; });
    if (!host || !tabs.length) return;
    state.anDefault = selected ? selected.getAttribute("data-ca-an-lane") : tabs[0].getAttribute("data-ca-an-lane");
    state.anLane = toneFromActionHash() || state.anDefault;
    host.classList.add("is-enhanced");
    if (/^#anv2-/.test(location.hash) && !toneFromActionHash()) writeActionHash(state.anDefault, "replace");
    if (!state.anMedia) {
      state.anMedia = window.matchMedia("(max-width: 680px)");
      var resizeActionMode = function () { syncActNow(); };
      if (state.anMedia.addEventListener) state.anMedia.addEventListener("change", resizeActionMode);
      else if (state.anMedia.addListener) state.anMedia.addListener(resizeActionMode);
    }
    if (!state.anHistoryBound) {
      window.addEventListener("hashchange", reconcileActionLocation);
      window.addEventListener("popstate", reconcileActionLocation);
      state.anHistoryBound = true;
    }
    syncActNow();
  }
  function reconcileActionLocation() {
    var tone = toneFromActionHash() || state.anDefault;
    if (!tone) return;
    if (/^#anv2-/.test(location.hash) && !toneFromActionHash()) writeActionHash(tone, "replace");
    state.anLane = tone;
    var focused = document.activeElement && document.activeElement.closest &&
      document.activeElement.closest("[data-ca-an-lane]");
    syncActNow(focused || /^#anv2-/.test(location.hash) ? tone : null);
  }
  function setAnLane(tone, focus, historyMode) {
    /* Presentation-only: never mutates the Prophet selection/filter. */
    if (!actionTabs().some(function (tab) { return tab.getAttribute("data-ca-an-lane") === tone; })) return;
    state.anLane = tone;
    syncActNow(focus ? tone : null);
    if (historyMode !== false) writeActionHash(tone, historyMode === "replace" ? "replace" : "push");
  }
  function toggleAnLane(tone) {
    var lane = actionLanes().find(function (node) { return node.getAttribute("data-ca-an-lane-body") === tone; });
    if (!lane) return;
    var list = qs(".ca-v36-an-list", lane), button = qs("[data-ca-an-view]", lane);
    if (!list || !button) return;
    var open = list.classList.contains("is-collapsed");
    list.classList.toggle("is-collapsed", !open);
    button.setAttribute("aria-expanded", open ? "true" : "false");
    state.anOpen[tone] = open;
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
  function boardPopulation() {
    var owner = qs("#ca-v36-card-grid");
    if (!owner) return null;
    var raw = owner.getAttribute("data-owner-population");
    raw = raw === null ? "" : String(raw).trim();
    return /^\d+$/.test(raw) ? Number(raw) : null;
  }
  function watchPopulation() {
    var owner = qs("#ca-v36-card-grid");
    if (!owner) return null;
    var raw = owner.getAttribute("data-owner-watch-population");
    raw = raw === null ? "" : String(raw).trim();
    return /^\d+$/.test(raw) ? Number(raw) : null;
  }
  function uniquePopulation() {
    var owner = qs("#ca-v36-card-grid");
    if (!owner) return null;
    var raw = owner.getAttribute("data-owner-unique-population");
    raw = raw === null ? "" : String(raw).trim();
    return /^\d+$/.test(raw) ? Number(raw) : null;
  }
  function populationCopy(shown, board, watch, unique) {
    if (board === null) {
      return watch === null
        ? bi(shown + " actionable cards shown · stage board unavailable · watch unavailable", "显示 " + shown + " 张可操作卡片 · 阶段榜单暂不可用 · 观察名单暂不可用")
        : bi(shown + " actionable cards shown · stage board unavailable · " + watch + " watch names", "显示 " + shown + " 张可操作卡片 · 阶段榜单暂不可用 · 观察 " + watch + " 只");
    }
    if (watch === null) return bi(shown + " actionable cards shown · " + board + " stage-board names · watch unavailable", "显示 " + shown + " 张可操作卡片 · 阶段榜单 " + board + " 只 · 观察名单暂不可用");
    return unique === null
      ? bi(shown + " actionable cards shown · " + board + " stage-board names · " + watch + " watch names · unique total unavailable", "显示 " + shown + " 张可操作卡片 · 阶段榜单 " + board + " 只 · 观察 " + watch + " 只 · 去重总数暂不可用")
      : bi(shown + " actionable cards shown · " + unique + " current names (" + board + " stage board + " + watch + " watch)", "显示 " + shown + " 张可操作卡片 · 当前共 " + unique + " 只（阶段榜单 " + board + " + 观察 " + watch + "）");
  }
  function applyFilter() {
    var shown = 0;
    state.cards.forEach(function (card) {
      var show = allowed(ticker(card.getAttribute("data-ticker")));
      card.classList.remove("sm-hidden", "sm-reveal");
      card.style.animationDelay = "";
      card.hidden = !show;
      if (show) shown++;
    });
    var empty = qs("#ca-v36-grid-empty");
    if (empty) { empty.hidden = shown !== 0; if (shown === 0) empty.innerHTML = emptyStateHtml(); }
    var board = boardPopulation(), result = qs("#ca-v36-result"), watch = watchPopulation(), unique = uniquePopulation();
    if (result) result.innerHTML = populationCopy(shown, board, watch, unique);
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
    var prophet = qs("#ca-v36-prophet");
    if (prophet) prophet.setAttribute("data-active-source", state.source);
    qsa("[data-ca-source]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-ca-source") === state.source)); });
    applyFilter();
  }
  function adoptView(value) {
    state.view = value === "table" ? "table" : "grid";
    if (state.view === "table") { enhanceTableQuotes(); applyTableFilter(); }
  }
  function setView(value) {
    value = value === "table" ? "table" : "grid";
    if (window.StockTable && typeof window.StockTable._setView === "function") return window.StockTable._setView(value);
    adoptView(value);
    try { localStorage.setItem("mdx_stocktable_ca_view", state.view); } catch (e) {}
    qsa("[data-ca-view]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-ca-view") === state.view)); });
    var board = qs("#standouts");
    if (board) board.classList.toggle("st-table-mode", state.view === "table");
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
    root.addEventListener("stocktable:ca-view", function (e) {
      adoptView(e.detail && e.detail.view);
    });
    root.addEventListener("click", function (e) {
      var b = e.target.closest("[data-ca-source]"); if (b) return setSource(b.getAttribute("data-ca-source"));
      /* Act-Now presentation controls: distinct targets, never carry the
         lead-kind/-id pair, never touch source/filter. */
      b = e.target.closest("[data-ca-an-lane]"); if (b) { e.preventDefault(); return setAnLane(b.getAttribute("data-ca-an-lane")); }
      b = e.target.closest("[data-ca-an-view]"); if (b) { e.preventDefault(); setAnLane(b.getAttribute("data-ca-an-view")); return toggleAnLane(b.getAttribute("data-ca-an-view")); }
      b = e.target.closest("[data-ca-lead-kind][data-ca-lead-id]"); if (b) return activate(b.getAttribute("data-ca-lead-kind"), b.getAttribute("data-ca-lead-id"));
      if (e.target.closest("#ca-v36-filter")) { state.filter = null; return applyFilter(); }
      if (e.target.closest("#ca-v36-expand")) return openModal();
      if (e.target.closest(".ca-v36-empty-switch")) return setSource("all");
    });
    root.addEventListener("keydown", function (e) {
      var tab = e.target.closest("[data-ca-an-lane]");
      if (!tab) return;
      var tabs = actionTabs(), index = tabs.indexOf(tab), next = index;
      if (e.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (e.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = tabs.length - 1;
      else if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      setAnLane(tabs[next].getAttribute("data-ca-an-lane"), true);
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
    adoptActNow(); renderLeadership(); renderFresh(); applyFilter(); observeQuoteStatus();
    var selectedView = qs("[data-ca-view][aria-selected='true']", main);
    adoptView(selectedView && selectedView.getAttribute("data-ca-view"));
    observeTable(); return true;
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) { if (!r.ok) throw new Error(url + " unavailable"); return r.json(); });
  }
  function start() {
    if (!document.body.classList.contains("page-canada")) return;
    var payload = parseRows() || { rows: [], as_of: "" };
    state.cards = collectCards();
    var prophet = qs("#ca-v36-prophet");
    var initialSource = prophet && prophet.getAttribute("data-initial-source");
    state.source = initialSource === "all" ? "all" : "top";
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

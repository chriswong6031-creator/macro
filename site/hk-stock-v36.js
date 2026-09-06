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
   semantics. The server-rendered page owns the canonical shell and every HK owner
   surface. This file only binds interactions and enriches typed slots in place;
   every input is harvested synchronously from the already-rendered DOM. */
(function () {
  "use strict";

  var PATH_RE = /(^|\/)hk_stocks\.html$/;
  if (!PATH_RE.test(location.pathname) || window.__mmHKStockV36) return;
  window.__mmHKStockV36 = true;

  var state = { source: "top", view: "grid", filter: null, sectors: [], cards: [], rows: [], featuredCount: 0,
    /* V3.8 Act-Now panel presentation state: anLane = which lane body is
       visible on the mobile segmented selector; anOpen = per-lane View-all
       expansion. Neither ever touches source/filter — a lane change must not
       mutate the Prophet selection until a group is actually chosen. */
    anLane: null, anDefault: null, anOpen: {}, anMedia: null,
    anHistoryBound: false, membershipKnown: false };
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
      /* Presentation marker only: owner order and membership stay untouched. */
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
        /* laneIdx preserves the ACTION owner's own row order inside each
           lane — the at-rest action map renders in this order, never in
           rotation-rank order (Action ≠ Leadership: the rank axis must not
           gate or order the action surface). */
        out.push({ id: id, name: name, stance: { en: def.en, zh: def.zh }, tone: def.tone, href: href, laneIdx: out.length });
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
     board rows publish this exact sector in their own vocabulary. A different
     sector elsewhere on the page does not prove this group's membership;
     unknown stays null and must never render as zero. */
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
    /* §10 rank-owner-missing law: when NO sector carries an owner rank, every
       piece of rank language (the RS basis chips, the modal Rank column)
       must disappear too — a basis label over a traversal-ordered list would
       be rank language without a rank owner. */
    state.hasRankOwner = merged.some(function (x) { return x.rank != null; });
    var sectorVocab = new Set(state.rows.map(function (r) { return r && r.sector; }).filter(Boolean));
    state.membershipKnown = sectorVocab.size > 0;
    merged.forEach(function (x) {
      x.kind = "sector";
      if (sectorVocab.has(x.name.en)) {
        var members = sectorMembers(x.name.en);
        x.members = members; x.leaders = firstN(Array.from(members), 3); x.count = members.size;
      } else {
        x.members = null; x.leaders = []; x.count = null;
      }
    });
    return merged;
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
    var basis = qs("#hk-v37-lead-basis");
    if (basis) basis.hidden = !state.hasRankOwner;
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

  /* What to Act On Now is server-owned. The enhancer may change only the
     selector state, lane visibility, focus, and the active lane's in-place
     expansion. It never creates, moves, clones, filters, or reorders rows. */
  function actionHost() { return qs("#hk-v37-an-body"); }
  function actionTabs() {
    var host = actionHost();
    return host ? qsa("[data-hk-an-lane]", host) : [];
  }
  function actionLanes() {
    var host = actionHost();
    return host ? qsa("[data-hk-an-lane-body]", host) : [];
  }
  function toneFromActionHash() {
    var id = location.hash ? location.hash.slice(1) : "";
    var lane = actionLanes().find(function (node) { return node.id === id; });
    return lane ? lane.getAttribute("data-hk-an-lane-body") : null;
  }
  function laneIdForTone(tone) {
    var tab = actionTabs().find(function (node) { return node.getAttribute("data-hk-an-lane") === tone; });
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
    var seg = qs(".hk-v37-an-seg", host);
    if (seg) {
      if (mobile) { seg.setAttribute("role", "tablist"); seg.setAttribute("aria-label", "What to Act On Now lanes"); }
      else { seg.removeAttribute("role"); seg.removeAttribute("aria-label"); }
    }
    actionTabs().forEach(function (tab) {
      var tone = tab.getAttribute("data-hk-an-lane"), active = tone === state.anLane;
      var laneId = laneIdForTone(tone);
      if (mobile) {
        tab.id = "hk-v37-an-tab-" + tone;
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
      var tone = lane.getAttribute("data-hk-an-lane-body"), active = tone === state.anLane;
      lane.classList.toggle("is-current", active);
      if (mobile) {
        lane.setAttribute("role", "tabpanel");
        lane.setAttribute("aria-labelledby", "hk-v37-an-tab-" + tone);
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
    var selected = tabs.find(function (tab) { return tab.getAttribute("data-hk-an-default") === "true"; });
    if (!host || !tabs.length) return;
    state.anDefault = selected ? selected.getAttribute("data-hk-an-lane") : tabs[0].getAttribute("data-hk-an-lane");
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
      document.activeElement.closest("[data-hk-an-lane]");
    syncActNow(focused || /^#anv2-/.test(location.hash) ? tone : null);
  }
  function setAnLane(tone, focus, historyMode) {
    /* Presentation-only: switching the visible mobile lane must not mutate
       the Prophet selection/filter until a group is actually chosen. */
    if (!actionTabs().some(function (tab) { return tab.getAttribute("data-hk-an-lane") === tone; })) return;
    state.anLane = tone;
    syncActNow(focus ? tone : null);
    if (historyMode !== false) writeActionHash(tone, historyMode === "replace" ? "replace" : "push");
  }
  function toggleAnLane(tone) {
    var lane = actionLanes().find(function (node) { return node.getAttribute("data-hk-an-lane-body") === tone; });
    if (!lane) return;
    var list = qs(".hk-v37-an-list", lane), button = qs("[data-hk-an-view]", lane);
    if (!list || !button) return;
    var open = list.classList.contains("is-collapsed");
    list.classList.toggle("is-collapsed", !open);
    button.setAttribute("aria-expanded", open ? "true" : "false");
    state.anOpen[tone] = open;
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
    /* Known zero (§10): membership is canonical and the group genuinely has
       no names on the current board — a quiet truthful state, not filter-miss
       language, and the group-research route stays usable. */
    if (item && item.members && item.members.size === 0) {
      return bi("No current Prophet names in this group.", "该组别暂无 Prophet 候选。") +
        (item.href ? ' <a class="hk-v37-empty-go" href="' + esc(item.href) + '">' + bi("Open sector research ↗", "查看板块研究 ↗") + '</a>' : '');
    }
    return bi("No names match this leadership filter.", "当前领先筛选下暂无匹配个股。");
  }
  function ownerPopulation() {
    var owner = qs("#hk-owner-population-proof");
    if (!owner) return null;
    var raw = owner.getAttribute("data-owner-board-population");
    raw = raw === null ? "" : String(raw).trim();
    return /^\d+$/.test(raw) ? Number(raw) : null;
  }
  function watchPopulation() {
    var owner = qs("#hk-owner-population-proof");
    if (!owner) return null;
    var raw = owner.getAttribute("data-owner-watch-population");
    raw = raw === null ? "" : String(raw).trim();
    return /^\d+$/.test(raw) ? Number(raw) : null;
  }
  function uniquePopulation() {
    var owner = qs("#hk-owner-population-proof");
    if (!owner) return null;
    var raw = owner.getAttribute("data-owner-unique-population");
    raw = raw === null ? "" : String(raw).trim();
    return /^\d+$/.test(raw) ? Number(raw) : null;
  }
  function populationCopy(shown, total, watch, unique) {
    if (total === null) {
      return watch === null
        ? bi(shown + " actionable cards shown · stage board unavailable · watch unavailable", "显示 " + shown + " 张可操作卡片 · 阶段榜单暂不可用 · 观察名单暂不可用")
        : bi(shown + " actionable cards shown · stage board unavailable · " + watch + " watch names", "显示 " + shown + " 张可操作卡片 · 阶段榜单暂不可用 · 观察 " + watch + " 只");
    }
    if (watch === null) return bi(shown + " actionable cards shown · " + total + " stage-board names · watch unavailable", "显示 " + shown + " 张可操作卡片 · 阶段榜单 " + total + " 只 · 观察名单暂不可用");
    return unique === null
      ? bi(shown + " actionable cards shown · " + total + " stage-board names · " + watch + " watch names · unique total unavailable", "显示 " + shown + " 张可操作卡片 · 阶段榜单 " + total + " 只 · 观察 " + watch + " 只 · 去重总数暂不可用")
      : bi(shown + " actionable cards shown · " + unique + " current names (" + total + " stage board + " + watch + " watch)", "显示 " + shown + " 张可操作卡片 · 当前共 " + unique + " 只（阶段榜单 " + total + " + 观察 " + watch + "）");
  }
  function applyFilter() {
    var shown = 0;
    state.cards.forEach(function (card) {
      /* The canonical owner grid has one visibility controller. Heal stale
         generic-showmore classes before assigning the selected manifest so a
         resize or legacy init cannot conceal an otherwise-selected card. */
      card.classList.remove("sm-hidden", "sm-reveal");
      card.style.removeProperty("animation-delay");
      var show = allowed(ticker(card.getAttribute("data-ticker")));
      card.hidden = !show;
      if (show) shown++;
    });
    var empty = qs("#hk-v37-grid-empty");
    if (empty) { empty.hidden = shown !== 0; if (shown === 0) empty.innerHTML = emptyStateHtml(); }
    var total = ownerPopulation();
    var result = qs("#hk-v37-result"), watch = watchPopulation(), unique = uniquePopulation();
    if (result) result.innerHTML = populationCopy(shown, total, watch, unique);
    var pill = qs("#hk-v37-filter"), item = itemForFilter();
    if (pill) { pill.hidden = !item; pill.classList.toggle("is-on", !!item); pill.innerHTML = item ? bi("Sector", "板块") + ': ' + bi(item.name.en, item.name.zh) + ' ×' : ""; }
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
    var prophet = qs("#hk-v37-prophet");
    if (prophet) prophet.setAttribute("data-active-source", state.source);
    qsa("[data-hk-source]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-hk-source") === state.source)); });
    applyFilter();
  }
  function adoptView(value) {
    state.view = value === "table" ? "table" : "grid";
    if (state.view === "table") applyTableFilter();
  }
  function setView(value) {
    value = value === "table" ? "table" : "grid";
    if (window.StockTable && typeof window.StockTable._setView === "function") return window.StockTable._setView(value);
    adoptView(value);
    try { localStorage.setItem("mdx_stocktable_hk_view", state.view); } catch (e) {}
    qsa("[data-hk-view]").forEach(function (b) { b.setAttribute("aria-selected", String(b.getAttribute("data-hk-view") === state.view)); });
    var board = qs("#standouts");
    if (board) board.classList.toggle("st-table-mode", state.view === "table");
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
  function modalRows(items, rk) {
    return items.length ? items.map(function (x) { return '<tr tabindex="0" data-hk-modal-id="' + esc(x.id) + '">' + (rk ? '<td class="num">' + esc(x.rank != null ? "RS #" + x.rank : "—") + '</td>' : '') + '<td><b>' + bi(x.name.en, x.name.zh) + '</b></td><td><span class="hk-v37-stance ' + x.tone + '">' + bi(x.stance.en, x.stance.zh) + '</span></td><td>' + (x.cycleState && x.cycleState.en ? bi(x.cycleState.en, x.cycleState.zh) : "—") + '</td><td class="leaders">' + esc(x.leaders.length ? x.leaders.join(" · ") : "—") + '</td><td class="num">' + (x.count != null ? x.count : "—") + '</td></tr>'; }).join("") : '<tr><td colspan="' + (rk ? 6 : 5) + '">—</td></tr>';
  }
  function modalPaneHtml() {
    /* Rank column + basis chip render ONLY under an owner rank (§10). */
    var rk = !!state.hasRankOwner;
    return '<div class="hk-v37-modal-pane"><h4>' + bi("Leadership & Rotation", "领先与轮动") + (rk ? ' <span class="hk-v37-lead-basis">' + bi("Relative strength vs HSI", "相对恒生指数") + '</span>' : '') + '</h4><table class="hk-v37-modal-table"><thead><tr>' + (rk ? '<th>' + bi("Rank", "排名") + '</th>' : '') + '<th>' + bi("Name", "名称") + '</th><th>' + bi("Action", "操作状态") + '</th><th>' + bi("Cycle state", "周期状态") + '</th><th>' + bi("Leaders", "领先个股") + '</th><th>' + bi("Prophet", "候选") + '</th></tr></thead><tbody>' + modalRows(state.sectors, rk) + '</tbody></table></div>';
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
    root.addEventListener("stocktable:hk-view", function (e) {
      adoptView(e.detail && e.detail.view);
    });
    root.addEventListener("click", function (e) {
      var b = e.target.closest("[data-hk-source]"); if (b) return setSource(b.getAttribute("data-hk-source"));
      /* Act-Now presentation controls come BEFORE the data-hk-lead-id row
         handler only in the sense that they are distinct targets — the
         segment/View-all buttons never carry data-hk-lead-id, and neither
         handler touches source/filter. */
      b = e.target.closest("[data-hk-an-lane]"); if (b) { e.preventDefault(); return setAnLane(b.getAttribute("data-hk-an-lane")); }
      b = e.target.closest("[data-hk-an-view]"); if (b) { e.preventDefault(); setAnLane(b.getAttribute("data-hk-an-view")); return toggleAnLane(b.getAttribute("data-hk-an-view")); }
      b = e.target.closest("[data-hk-lead-id]"); if (b) return activate(b.getAttribute("data-hk-lead-id"));
      if (e.target.closest("#hk-v37-filter")) { state.filter = null; return applyFilter(); }
      if (e.target.closest("#hk-v37-expand")) return openModal();
      if (e.target.closest(".hk-v37-empty-switch")) return setSource("all");
    });
    root.addEventListener("keydown", function (e) {
      var tab = e.target.closest("[data-hk-an-lane]");
      if (!tab) return;
      var tabs = actionTabs(), index = tabs.indexOf(tab), next = index;
      if (e.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (e.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = tabs.length - 1;
      else if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      setAnLane(tabs[next].getAttribute("data-hk-an-lane"), true);
    });
  }

  function buildShell(payload) {
    var main = qs("#hk-v37"), modal = qs("#hk-v37-modal");
    if (!main) return false;
    if (main.getAttribute("data-hk-enhanced") !== "true") {
      main.setAttribute("data-hk-enhanced", "true");
      bind(main);
      if (modal) {
        modal.addEventListener("click", function (e) { if (e.target === modal || e.target.closest("[data-hk-modal-close]")) return closeModal(); var r = e.target.closest("[data-hk-modal-id]"); if (r) activate(r.getAttribute("data-hk-modal-id")); });
        modal.addEventListener("keydown", function (e) { var r = e.target.closest("[data-hk-modal-id]"); if (r && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); activate(r.getAttribute("data-hk-modal-id")); } });
      }
      document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });
    }
    adoptActNow(); renderLeadership(); renderFlowCue();
    setSource(state.source);
    var selectedView = qs("[data-hk-view][aria-selected='true']", main);
    adoptView(selectedView && selectedView.getAttribute("data-hk-view"));
    observeTable(); return true;
  }

  /* Bind the server-owned shell even when rows/cards are empty or malformed.
     Zero network reads anywhere in this file: enhancement cannot gate paint. */
  function start() {
    if (!qs("#hk-v37")) return;
    var payload = parseRows() || { rows: [], as_of: "" };
    state.cards = collectCards();
    state.featuredCount = state.cards.filter(function (c) { return c.classList.contains("pv-featured"); }).length;
    var prophet = qs("#hk-v37-prophet");
    var initialSource = prophet && prophet.getAttribute("data-initial-source");
    state.source = initialSource === "top" ? "top" : "all";
    state.sectors = collectSectors();
    buildShell(payload);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}());

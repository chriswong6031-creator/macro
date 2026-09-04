/* F02-X1 — Official sanctions geography desk.
   Paired byte-for-byte with site/sanctions_geography.js.

   Reads two artifacts and invents nothing:
     * sanctions-geography-data.json — the frozen projection
       (mastermind.sanctions_geography.v1), owned by the source lane;
     * world-110m.json — the existing tracked Natural Earth boundary asset.

   Vendored UMD globals: d3 (d3-array + d3-geo) and topojson-client. No build
   step, no new dependency, no second country authority: every boundary this
   file paints is keyed by the projection's own geo_id against the topology's
   own numeric geometry ids.

   THIS FILE AUTHORS NO STYLE. Every visual decision lives in
   sanctions_geography.css; here we only set classes and data-attributes, plus
   the genuinely data-dependent viewBox geometry. That is the design-system
   law and it is also what keeps this file out of the runtime-injection ledger.

   Honesty rules encoded below, not merely documented:
     * a count is "distinct entries with at least one published address whose
       country field names this boundary" — never a location, never a headcount;
     * ADDED / REMOVED come only from an explicit official delta action; the
       absence of a delta is never read as a removal;
     * a published country with no boundary, and a boundary id the topology does
       not carry, are both registered off-map rather than folded into a
       neighbour or silently dropped;
     * a failed load degrades to a named state that says what still works. */

(function () {
  "use strict";

  var d3 = window.d3;
  var topojson = window.topojson;

  var DATA_URL = "sanctions-geography-data.json";
  var TOPO_URL = "world-110m.json";

  /* Fixed, human-readable breaks. A quantile ramp would re-scale itself every
     night and make two visits incomparable; printed breaks can be checked by
     eye against the table. */
  var BREAKS = [1, 10, 50, 200, 1000];

  /* Browser pass 1 measured a 6,104px page: 40 change cards and a 60-tile
     off-map grid drowned the map and the table. A briefing shows the head of
     each register and COUNTS the rest — the full list is the artifact, which
     the provenance section names. */
  var MAX_ENTRY_ROWS = 12;
  var MAX_CHANGE_ROWS = 8;
  var MAX_OFFMAP_TILES = 12;

  var root = document.querySelector("[data-sg-root]");
  if (!root) { return; }

  var ui = {
    figures: root.querySelector("[data-sg-figures]"),
    prov: root.querySelector("[data-sg-prov]"),
    map: root.querySelector("[data-sg-map]"),
    mapSkel: root.querySelector("[data-sg-mapskel]"),
    asof: root.querySelector("[data-sg-asof]"),
    legend: root.querySelector("[data-sg-legend]"),
    tbody: root.querySelector("[data-sg-tbody]"),
    tableBox: root.querySelector("[data-sg-tablebox]"),
    search: root.querySelector("[data-sg-search]"),
    sort: root.querySelector("[data-sg-sort]"),
    entries: root.querySelector("[data-sg-entries]"),
    entriesHead: root.querySelector("[data-sg-entries-head]"),
    changes: root.querySelector("[data-sg-changes]"),
    coverage: root.querySelector("[data-sg-coverage]"),
    offmap: root.querySelector("[data-sg-offmap]"),
    source: root.querySelector("[data-sg-source]"),
    banner: root.querySelector("[data-sg-banner]")
  };

  var model = {
    projection: null,
    byGeo: {},          /* geo_id -> country row */
    entriesByGeo: {},   /* geo_id -> [entry]     */
    drawableIds: null,
    selected: null
  };

  /* ---------------- tiny DOM helpers (no markup strings with tags) --------- */

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }

  /* The house bilingual mechanism: emit BOTH languages, let html[data-lang]
     choose. Never pick a language in JS — a reader can flip mid-session. */
  function bi(parent, en, zh, cls) {
    var e = el("span", "l-en" + (cls ? " " + cls : ""), en);
    var z = el("span", "l-zh" + (cls ? " " + cls : ""), zh);
    parent.appendChild(e);
    parent.appendChild(z);
    return parent;
  }

  function clear(node) {
    if (!node) { return; }
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  function num(value) {
    var n = Number(value);
    if (!isFinite(n)) { return "—"; }
    return n.toLocaleString("en-US");
  }

  function shortHash(value) {
    var s = String(value || "");
    var bare = s.indexOf(":") >= 0 ? s.slice(s.indexOf(":") + 1) : s;
    return bare ? bare.slice(0, 12) : "—";
  }

  function stepFor(count) {
    var n = Number(count) || 0;
    if (n < BREAKS[0]) { return 0; }
    var step = 1;
    for (var i = 1; i < BREAKS.length; i += 1) {
      if (n >= BREAKS[i]) { step = i + 1; }
    }
    return step;
  }

  /* ---------------- degraded + empty states ------------------------------- */

  function banner(kind, titleEn, titleZh, bodyEn, bodyZh, code) {
    if (!ui.banner) { return; }
    clear(ui.banner);
    var box = el("div", "sg-degraded" + (kind === "stale" ? " sg-degraded--stale" : ""));
    box.setAttribute("role", kind === "stale" ? "status" : "alert");
    var body = el("div");
    var t = el("strong", "sg-degraded-t");
    bi(t, titleEn, titleZh);
    body.appendChild(t);
    var p = el("div");
    bi(p, bodyEn, bodyZh);
    body.appendChild(p);
    if (code) {
      var c = el("code", null, code);
      body.appendChild(c);
    }
    box.appendChild(body);
    ui.banner.appendChild(box);
  }

  /* A state code is a receipt, not copy: mono, muted, adjacent to the plain
     sentence it evidences. This is the compliant form of "states printed". */
  function code(target, value) {
    var c = el("code", "sg-mono sg-unres", value);
    target.appendChild(document.createTextNode(" "));
    target.appendChild(c);
    return c;
  }

  function emptyState(target, titleEn, titleZh, whyEn, whyZh) {
    clear(target);
    var wrap = el("div", "sg-empty");
    var t = el("strong", "sg-empty-t");
    bi(t, titleEn, titleZh);
    wrap.appendChild(t);
    var why = el("span", "sg-empty-why");
    bi(why, whyEn, whyZh);
    wrap.appendChild(why);
    target.appendChild(wrap);
  }

  /* ---------------- the read (headline figures) --------------------------- */

  function renderFigures(p) {
    if (!ui.figures) { return; }
    var s = p.summary || {};
    clear(ui.figures);

    function fig(labelEn, labelZh, value, meanEn, meanZh) {
      var box = el("div", "sg-fig");
      var k = el("span", "sg-fig-k");
      bi(k, labelEn, labelZh);
      box.appendChild(k);
      box.appendChild(el("span", "sg-fig-v tnum", value));
      var m = el("span", "sg-fig-m");
      bi(m, meanEn, meanZh);
      box.appendChild(m);
      ui.figures.appendChild(box);
    }

    fig("Listed entries", "名单条目", num(s.current_entries),
        "People, companies and vessels on the current list.",
        "当前名单上的个人、公司与船舶。");
    fig("With a published address", "载有公开地址",
        num(s.entries_with_published_addresses),
        "Only these can appear anywhere on the map.",
        "只有这些条目才可能出现在地图上。");
    fig("Boundaries named", "涉及边界", num(s.resolved_countries),
        "Countries named by at least one published address.",
        "至少被一条公开地址提及的国家/地区。");
    fig("Recent official changes", "近期官方变更", num(s.recent_official_changes),
        "Additions and removals published by OFAC in its own delta files.",
        "由 OFAC 官方增量文件发布的新增与移除。");
  }

  /* ---------------- provenance rail (the signature device) ---------------- */

  /* One freshness stamp for the page — the canonical .dtp-asof, filled from the
     official publication clock rather than from build time. */
  function renderAsOf(p) {
    if (!ui.asof) { return; }
    var published = (p.freshness && p.freshness.published_at) ||
      (p.source && p.source.current && p.source.current.published_at) || "";
    clear(ui.asof);
    bi(ui.asof,
      "As of " + String(published).slice(0, 10) + " — the official publication date",
      "数据截至 " + String(published).slice(0, 10) + " — 官方发布日期");
  }

  function renderProvenance(p) {
    if (!ui.prov) { return; }
    var src = (p.source && p.source.current) || {};
    var health = String(src.source_health || p.source_state || "").toUpperCase();
    clear(ui.prov);

    ui.prov.className = "sg-prov " + (
      health === "CURRENT" ? "sg-prov--ok"
        : (health === "STALE" ? "sg-prov--warn" : "sg-prov--bad")
    );

    function pair(labelEn, labelZh, value, cls) {
      var span = el("span", cls || null);
      var lbl = el("span");
      bi(lbl, labelEn + " ", labelZh + " ");
      span.appendChild(lbl);
      span.appendChild(el("b", null, value));
      ui.prov.appendChild(span);
    }

    pair("file", "文件", src.source_name || "—");
    pair("published", "发布", (p.freshness && p.freshness.published_at) || src.published_at || "—");
    pair("bytes", "字节", num(src.actual_bytes));
    pair("sha256", "sha256", shortHash(src.raw_sha256), "sg-hash");
    pair("parser", "解析器", src.parser_revision || p.parser_revision || "—");
    pair("projection", "投影", shortHash(p.projection_id), "sg-hash");
  }

  /* ---------------- map --------------------------------------------------- */

  function renderMap(p, topo) {
    if (!ui.map || !d3 || !topojson || !topo) { return; }

    var collection = topo.objects && topo.objects.countries;
    if (!collection) { return; }
    var geo = topojson.feature(topo, collection);
    var features = geo.features || [];

    model.drawableIds = {};
    features.forEach(function (f) { model.drawableIds[String(f.id)] = true; });

    var width = 960;
    var height = 460;
    var proj = d3.geoNaturalEarth1().fitSize([width, height], geo);
    var path = d3.geoPath(proj);

    ui.map.setAttribute("viewBox", "0 0 " + width + " " + height);
    ui.map.setAttribute("preserveAspectRatio", "xMidYMid meet");
    clear(ui.map);

    var NS = "http://www.w3.org/2000/svg";

    features.forEach(function (f) {
      var d = path(f);
      if (!d) { return; }
      var id = String(f.id);
      var row = model.byGeo[id];
      var count = row ? Number(row.entries) || 0 : 0;
      var name = row ? row.country : ((f.properties && f.properties.name) || id);

      var node = document.createElementNS(NS, "path");
      node.setAttribute("d", d);
      node.setAttribute("class", "sg-geo" + (count > 0 ? " is-pick" : ""));
      node.setAttribute("data-geo-id", id);
      node.setAttribute("data-count", String(count));
      node.setAttribute("data-step", String(stepFor(count)));
      if (count > 0) {
        node.setAttribute("tabindex", "0");
        node.setAttribute("role", "button");
        node.setAttribute("aria-label",
          name + ": " + num(count) + " listed entries with a published address here");
        node.addEventListener("click", function () { select(id); });
        node.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(id); }
        });
      }
      var title = document.createElementNS(NS, "title");
      title.textContent = name + " · " + num(count);
      node.appendChild(title);
      ui.map.appendChild(node);
    });

    if (ui.mapSkel && ui.mapSkel.parentNode) {
      ui.mapSkel.parentNode.removeChild(ui.mapSkel);
    }
    ui.map.removeAttribute("hidden");
    renderLegend();
  }

  function renderLegend() {
    if (!ui.legend) { return; }
    clear(ui.legend);
    var lead = el("span");
    bi(lead, "Entries with a published address here", "在此载有公开地址的条目数");
    ui.legend.appendChild(lead);

    var ramp = el("span", "sg-ramp");
    for (var i = 0; i < BREAKS.length; i += 1) { ramp.appendChild(el("i")); }
    ui.legend.appendChild(ramp);

    var scale = el("span", "sg-mono");
    var labels = [];
    for (var j = 0; j < BREAKS.length; j += 1) {
      labels.push(j === BREAKS.length - 1
        ? num(BREAKS[j]) + "+"
        : num(BREAKS[j]) + "–" + num(BREAKS[j + 1] - 1));
    }
    scale.textContent = labels.join("  ·  ");
    ui.legend.appendChild(scale);

    var off = el("span");
    off.appendChild(el("i", "sg-legend-hatch"));
    var offTxt = el("span");
    bi(offTxt, " off-map — registered below", " 无法上图 — 见下方登记");
    off.appendChild(offTxt);
    ui.legend.appendChild(off);
  }

  /* ---------------- country table ----------------------------------------- */

  function visibleRows() {
    var q = (ui.search && ui.search.value ? ui.search.value : "").trim().toLowerCase();
    var rows = (model.projection.countries || []).slice();
    if (q) {
      rows = rows.filter(function (r) {
        if (String(r.country || "").toLowerCase().indexOf(q) >= 0) { return true; }
        return (r.programs || []).some(function (pr) {
          return String(pr.program || "").toLowerCase().indexOf(q) >= 0;
        });
      });
    }
    var mode = ui.sort && ui.sort.value ? ui.sort.value : "entries";
    rows.sort(function (a, b) {
      if (mode === "name") { return String(a.country).localeCompare(String(b.country)); }
      if (mode === "changed") {
        return ((b.added || 0) + (b.removed || 0)) - ((a.added || 0) + (a.removed || 0));
      }
      return (Number(b.entries) || 0) - (Number(a.entries) || 0);
    });
    return rows;
  }

  function renderTable() {
    if (!ui.tbody) { return; }
    var rows = visibleRows();
    clear(ui.tbody);

    if (!rows.length) {
      /* NO_RESULTS — the frozen empty-query state. A filter that matches nothing
         says so and says why; it never synthesises a fact to fill the box. */
      var tr = el("tr");
      var td = el("td");
      td.setAttribute("colspan", "5");
      var host = el("div");
      td.appendChild(host);
      tr.appendChild(td);
      ui.tbody.appendChild(tr);
      emptyState(host,
        "No boundary matches that filter",
        "没有符合该筛选的边界",
        "Nothing in the current list names a country or program matching your text. Clear the filter to see all boundaries again.",
        "当前名单中没有任何国家或项目与该文字匹配。清除筛选即可重新查看全部边界。");
      /* The closed state vocabulary stays visible, but as a machine receipt in
         mono beside the plain sentence — never inside it. */
      code(host, "NO_RESULTS");
      return;
    }

    rows.forEach(function (r) {
      var id = String(r.geo_id);
      var tr = el("tr");
      tr.setAttribute("tabindex", "0");
      tr.setAttribute("data-geo-id", id);
      if (model.selected === id) { tr.className = "is-on"; }

      tr.appendChild(el("td", null, r.country));
      tr.appendChild(el("td", "sg-r", num(r.entries)));
      tr.appendChild(el("td", "sg-r", num(r.published_addresses)));

      var delta = el("td", "sg-r");
      var added = Number(r.added) || 0;
      var removed = Number(r.removed) || 0;
      delta.textContent = (added || removed) ? ("+" + added + " / −" + removed) : "—";
      tr.appendChild(delta);

      var progs = (r.programs || []).slice(0, 2).map(function (pr) { return pr.program; });
      var extra = Math.max(0, (r.programs || []).length - progs.length);
      var td = el("td", "sg-mono");
      td.textContent = progs.join(", ") + (extra ? "  +" + extra : "");
      tr.appendChild(td);

      tr.addEventListener("click", function () { select(id); });
      tr.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(id); }
      });
      ui.tbody.appendChild(tr);
    });
  }

  /* ---------------- selection + entry detail ------------------------------ */

  function select(geoId) {
    model.selected = (model.selected === geoId) ? null : geoId;
    var paths = ui.map ? ui.map.querySelectorAll(".sg-geo") : [];
    Array.prototype.forEach.call(paths, function (node) {
      var on = model.selected && node.getAttribute("data-geo-id") === model.selected;
      node.classList.toggle("is-on", !!on);
      if (on) { node.setAttribute("aria-pressed", "true"); }
      else if (node.hasAttribute("aria-pressed")) { node.setAttribute("aria-pressed", "false"); }
    });
    var trs = ui.tbody ? ui.tbody.querySelectorAll("tr") : [];
    Array.prototype.forEach.call(trs, function (tr) {
      tr.classList.toggle("is-on", !!model.selected && tr.getAttribute("data-geo-id") === model.selected);
    });
    renderEntries();
  }

  function chip(parent, cls, en, zh) {
    var c = el("span", "sg-chip " + cls);
    bi(c, en, zh);
    parent.appendChild(c);
  }

  function entryCard(entry, geoId) {
    var box = el("div", "sg-entry");
    box.appendChild(el("div", "sg-entry-n", entry.name));

    var uid = el("div", "sg-entry-uid");
    uid.textContent = "OFAC UID " + entry.uid + " · " + (entry.entity_type || "—");
    box.appendChild(uid);

    var states = entry.states || (entry.state ? [entry.state] : []);
    var chips = el("div");
    (entry.programs || []).slice(0, 4).forEach(function (pr) {
      chip(chips, "sg-chip--prog", String(pr), String(pr));
    });
    states.forEach(function (st) {
      if (st === "ADDED") { chip(chips, "sg-chip--added", "Added by official delta", "官方增量新增"); }
      else if (st === "REMOVED") { chip(chips, "sg-chip--removed", "Removed by official delta", "官方增量移除"); }
      else if (st === "SOURCE_CORRECTED") { chip(chips, "sg-chip--corrected", "Source corrected", "来源已更正"); }
    });
    if (entry.identity_resolved === false) {
      chip(chips, "sg-chip--unres", "Identity unresolved", "身份未解析");
    }
    box.appendChild(chips);

    var dl = el("dl", "sg-kv");
    (entry.addresses || []).slice(0, 4).forEach(function (a) {
      var dt = el("dt");
      bi(dt, "Published address", "公开地址");
      dl.appendChild(dt);
      var dd = el("dd");
      dd.textContent = a.published_address || a.published_country || "—";
      if (a.state === "GEO_UNRESOLVED" || !a.geo_id) {
        var mark = el("span", "sg-chip sg-chip--unres");
        bi(mark, "Could not be placed", "无法定位边界");
        dd.appendChild(document.createTextNode(" "));
        dd.appendChild(mark);
        code(dd, "GEO_UNRESOLVED");
      } else if (geoId && String(a.geo_id) === String(geoId)) {
        var here = el("span", "sg-unres sg-mono");
        here.textContent = " ← this boundary";
        dd.appendChild(here);
      }
      dl.appendChild(dd);
    });
    var dtf = el("dt");
    bi(dtf, "Source fingerprint", "来源指纹");
    dl.appendChild(dtf);
    var ddf = el("dd", "sg-mono");
    ddf.textContent = shortHash(entry.source_fingerprint);
    dl.appendChild(ddf);
    box.appendChild(dl);
    return box;
  }

  function renderEntries() {
    if (!ui.entries) { return; }
    clear(ui.entries);
    if (ui.entriesHead) {
      clear(ui.entriesHead);
      var row = model.selected ? model.byGeo[model.selected] : null;
      if (row) {
        bi(ui.entriesHead,
           row.country + " — " + num(row.entries) + " listed entries",
           row.country + " — " + num(row.entries) + " 条名单条目");
      } else {
        bi(ui.entriesHead, "Selected boundary", "所选边界");
      }
    }

    if (!model.selected) {
      emptyState(ui.entries,
        "No boundary selected",
        "尚未选择边界",
        "Choose a country on the map or in the table to read the entries whose published address names it.",
        "在地图或表格中选择一个国家/地区，即可查看其公开地址所指向的条目。");
      return;
    }

    var list = model.entriesByGeo[model.selected] || [];
    if (!list.length) {
      emptyState(ui.entries,
        "Nothing to show for this boundary",
        "该边界暂无可显示内容",
        "The projection counts this boundary but carries no entry detail for it in this build.",
        "本次构建中，该边界有计数但没有可展示的条目明细。");
      return;
    }
    list.slice(0, MAX_ENTRY_ROWS).forEach(function (e) {
      ui.entries.appendChild(entryCard(e, model.selected));
    });
    if (list.length > MAX_ENTRY_ROWS) {
      var more = el("div", "sg-fig-m");
      bi(more,
        "Showing " + MAX_ENTRY_ROWS + " of " + num(list.length) + " entries for this boundary.",
        "共 " + num(list.length) + " 条，此处显示前 " + MAX_ENTRY_ROWS + " 条。");
      ui.entries.appendChild(more);
    }
  }

  function renderChanges(p) {
    if (!ui.changes) { return; }
    clear(ui.changes);
    var list = (p.changes || []).slice();
    if (!list.length) {
      emptyState(ui.changes,
        "No official change in this window",
        "该窗口内没有官方变更",
        "OFAC published no add or remove action in the delta files covered by this build. That is a quiet period, not a gap in the record.",
        "在本次构建覆盖的增量文件中，OFAC 未发布任何新增或移除。这是平静期，而非记录缺失。");
      return;
    }
    list.slice(0, MAX_CHANGE_ROWS).forEach(function (c) {
      var box = el("div", "sg-crow");
      box.appendChild(el("div", "sg-crow-n", c.name));
      var meta = el("div", "sg-crow-m");
      meta.textContent = (c.published_at || "").slice(0, 10) + " · UID " + c.uid;
      box.appendChild(meta);
      var chips = el("div", "sg-crow-s");
      /* The state comes from the official delta's own action field. Nothing
         here infers a removal from an absence. */
      if (c.state === "ADDED" || c.action === "add") {
        chip(chips, "sg-chip--added", "Added", "新增");
      } else if (c.state === "REMOVED" || c.action === "remove") {
        chip(chips, "sg-chip--removed", "Removed", "移除");
      } else if (c.state === "SOURCE_CORRECTED") {
        chip(chips, "sg-chip--corrected", "Source corrected", "来源已更正");
      }
      (c.programs || []).slice(0, 2).forEach(function (pr) {
        chip(chips, "sg-chip--prog", String(pr), String(pr));
      });
      box.appendChild(chips);
      ui.changes.appendChild(box);
    });
    if (list.length > MAX_CHANGE_ROWS) {
      var more = el("div", "sg-more");
      bi(more,
        "Showing the " + MAX_CHANGE_ROWS + " most recent of " + num(list.length) +
          " official changes in this window. Every one of them is in the artifact named below.",
        "本窗口共 " + num(list.length) + " 项官方变更，此处显示最近 " + MAX_CHANGE_ROWS +
          " 项。全部变更均见下方所列数据文件。");
      ui.changes.appendChild(more);
    }
  }

  /* ---------------- coverage / off-map register --------------------------- */

  function renderCoverage(p) {
    if (!ui.coverage) { return; }
    var s = p.summary || {};
    clear(ui.coverage);

    function item(valueEn, labelEn, labelZh) {
      var box = el("div", "sg-cov-item");
      box.appendChild(el("b", "sg-mono", valueEn));
      var lbl = el("div", "sg-fig-m");
      bi(lbl, labelEn, labelZh);
      box.appendChild(lbl);
      ui.coverage.appendChild(box);
    }

    item(num(s.geo_resolved_addresses),
      "Published addresses matched to a boundary.",
      "已匹配到边界的公开地址。");
    item(num(s.geo_unresolved_addresses),
      "Published addresses we could not place — kept as GEO_UNRESOLVED, never folded into a neighbour.",
      "无法定位的公开地址 — 保留为 GEO_UNRESOLVED，绝不并入邻国。");
    item(num(s.published_addresses),
      "Published address records read from the official file.",
      "自官方文件读取的公开地址记录总数。");

    if (!ui.offmap) { return; }
    clear(ui.offmap);

    var offmap = (p.unresolved_geography || []).slice().sort(function (a, b) {
      return (Number(b.published_addresses) || 0) - (Number(a.published_addresses) || 0);
    });

    /* A boundary id the projection resolved but the 110m topology does not
       carry is just as off-map as an unresolved name — and it would otherwise
       be invisible, because it is counted but never painted. */
    var undrawable = [];
    if (model.drawableIds) {
      (p.countries || []).forEach(function (r) {
        if (!model.drawableIds[String(r.geo_id)]) {
          undrawable.push({ published_country: r.country, published_addresses: r.published_addresses });
        }
      });
    }

    var all = offmap.concat(undrawable);
    if (!all.length) {
      emptyState(ui.offmap,
        "Every published country reached the map",
        "所有公开国家均已上图",
        "This build placed every published address country on a boundary. That is unusual; re-check it rather than assuming it.",
        "本次构建将所有公开地址国家都定位到了边界上。这种情况并不常见，请复核而非直接采信。");
      return;
    }
    all.slice(0, MAX_OFFMAP_TILES).forEach(function (u) {
      var box = el("div", "sg-cov-item");
      box.appendChild(el("b", "sg-mono", num(u.published_addresses)));
      var name = el("div", "sg-fig-m");
      var raw = String(u.published_country === undefined ? "" : u.published_country);
      if (!raw.trim() || raw === "(blank)") {
        /* The projection's own token for "the address names no country at all".
           It is reproduced as a receipt, never replaced — but a reader cannot
           read a parser token, so the plain meaning leads. */
        bi(name, "Address names no country", "地址未填写国家");
        code(name, raw.trim() ? raw : "(blank)");
      } else {
        name.textContent = raw;
      }
      box.appendChild(name);
      ui.offmap.appendChild(box);
    });
    if (all.length > MAX_OFFMAP_TILES) {
      var rest = all.slice(MAX_OFFMAP_TILES).reduce(function (acc, u) {
        return acc + (Number(u.published_addresses) || 0);
      }, 0);
      var more = el("div", "sg-more");
      bi(more,
        (all.length - MAX_OFFMAP_TILES) + " further published places, covering " +
          num(rest) + " more addresses, are also off the map and stay unresolved.",
        "另有 " + (all.length - MAX_OFFMAP_TILES) + " 个公开地点（共 " + num(rest) +
          " 条地址）同样无法上图，保持未解析状态。");
      ui.offmap.appendChild(more);
    }
  }

  /* ---------------- source receipt ---------------------------------------- */

  function renderSource(p) {
    if (!ui.source) { return; }
    clear(ui.source);
    var src = p.source || {};

    function row(rec, kindEn, kindZh) {
      var box = el("div", "sg-src-row");
      var head = el("div");
      var strong = el("strong");
      strong.textContent = rec.source_name || rec.source_key || "—";
      head.appendChild(strong);
      var kind = el("span", "sg-mono");
      kind.textContent = "  ";
      head.appendChild(kind);
      bi(head, " " + kindEn, " " + kindZh);
      box.appendChild(head);

      var dl = el("dl", "sg-kv");
      function kv(labelEn, labelZh, value, mono) {
        var dt = el("dt");
        bi(dt, labelEn, labelZh);
        dl.appendChild(dt);
        dl.appendChild(el("dd", mono ? "sg-mono" : null, value));
      }
      kv("Official URL", "官方地址", rec.source_url || "—");
      kv("Published", "发布时间", rec.published_at || "—", true);
      kv("Acquired", "获取时间", rec.acquired_at || "—", true);
      kv("Bytes", "字节数", num(rec.actual_bytes), true);
      kv("SHA-256", "SHA-256", rec.raw_sha256 || "—", true);
      kv("Schema", "模式", rec.schema_revision || "—");
      kv("Rights", "权利声明", rec.rights || "—");
      if (rec.delta_relation) { kv("Delta relation", "增量关系", rec.delta_relation, true); }
      box.appendChild(dl);
      ui.source.appendChild(box);
    }

    if (src.current) { row(src.current, "current membership file", "当前名单文件"); }
    (src.schemas || []).forEach(function (rec) { row(rec, "schema", "模式文件"); });
    (src.deltas || []).slice(0, 6).forEach(function (rec) { row(rec, "official delta", "官方增量"); });

    var b = p.boundary || {};
    if (b.asset) {
      var box = el("div", "sg-src-row");
      var head = el("strong", null, b.asset);
      box.appendChild(head);
      var dl = el("dl", "sg-kv");
      var dt = el("dt");
      bi(dt, "Boundary rights", "边界数据权利");
      dl.appendChild(dt);
      dl.appendChild(el("dd", null, b.rights || "—"));
      var dt2 = el("dt");
      bi(dt2, "SHA-256", "SHA-256");
      dl.appendChild(dt2);
      dl.appendChild(el("dd", "sg-mono", b.raw_sha256 || "—"));
      box.appendChild(dl);
      ui.source.appendChild(box);
    }

    var m = p.method || {};
    var method = el("div", "sg-src-row");
    var mt = el("div");
    bi(mt,
      "Geography basis: " + (m.geography_basis || "published_address_country_only") +
      ". Membership authority: the current full snapshot. Model output authority: " +
      (m.model_output_authority || "NONE") + ".",
      "地理依据：" + (m.geography_basis || "published_address_country_only") +
      "。名单归属以当前完整快照为准。模型输出权限：" + (m.model_output_authority || "NONE") + "。");
    method.appendChild(mt);
    ui.source.appendChild(method);
  }

  /* ---------------- source health ----------------------------------------- */

  function renderHealth(p) {
    var state = String(p.source_state || "").toUpperCase();
    var fresh = p.freshness || {};
    if (state === "UNAVAILABLE") {
      banner("bad",
        "The official file could not be reached for this build",
        "本次构建无法访问官方文件",
        "Every figure below is the last accepted projection, kept deliberately rather than replaced with an empty success. Counts, boundaries and the source receipt are still readable; only the freshness is not.",
        "以下所有数字来自最近一次已接受的投影，我们刻意保留而非以空结果覆盖。计数、边界与来源凭证仍可查阅，仅时效性无法保证。",
        "UNAVAILABLE");
      return;
    }
    if (state === "PARSER_SHAPE_CHANGED") {
      banner("bad",
        "The official file no longer matches the parser this page was built against",
        "官方文件结构与本页解析器不再匹配",
        "The last accepted projection is shown unchanged. Nothing here has been re-derived from the new shape, and no count should be treated as current until the parser is reconciled.",
        "此处显示最近一次已接受的投影，未做任何改动。新结构下未重新推导任何数据；在解析器完成校准前，不应将任何计数视为当前值。",
        "PARSER_SHAPE_CHANGED");
      return;
    }
    if (state === "STALE" || String(fresh.stale_state || "").toUpperCase() === "STALE") {
      var after = fresh.stale_after || "";
      if (!after || new Date(after).getTime() <= Date.now()) {
        banner("stale",
          "This read is behind the official publication clock",
          "此读数已落后于官方发布时间",
          "The list itself has not been re-acquired since the published date on the receipt. Treat the counts as of that date, not as of today.",
          "自凭证所载发布日期以来，名单未再次获取。请按该日期而非今日理解这些计数。",
          "STALE");
      }
    }
  }

  /* ---------------- boot -------------------------------------------------- */

  function index(p) {
    model.byGeo = {};
    (p.countries || []).forEach(function (r) { model.byGeo[String(r.geo_id)] = r; });

    model.entriesByGeo = {};
    (p.entries || []).forEach(function (e) {
      var seen = {};
      (e.addresses || []).forEach(function (a) {
        if (!a.geo_id || a.state === "GEO_UNRESOLVED") { return; }
        var id = String(a.geo_id);
        if (seen[id]) { return; }
        seen[id] = true;
        if (!model.entriesByGeo[id]) { model.entriesByGeo[id] = []; }
        model.entriesByGeo[id].push(e);
      });
    });
  }

  /* Form controls cannot carry the dual-emit .l-en/.l-zh spans the rest of the
     page uses — an <option> holds text only, and a placeholder is an attribute.
     These are the two places where the language must be chosen in script rather
     than in CSS, so they follow the house data-label-en/zh attribute idiom and
     re-apply on theme.js's `langchange` event, never only at boot. */
  function applyLang() {
    var zh = document.documentElement.getAttribute("data-lang") === "zh";
    if (ui.search) {
      var ph = ui.search.getAttribute(zh ? "data-ph-zh" : "data-ph-en");
      if (ph) { ui.search.setAttribute("placeholder", ph); }
    }
    if (ui.sort) {
      Array.prototype.forEach.call(ui.sort.options, function (opt) {
        var label = opt.getAttribute(zh ? "data-label-zh" : "data-label-en");
        if (label) { opt.textContent = label; }
      });
    }
  }

  function wire() {
    if (ui.search) { ui.search.addEventListener("input", renderTable); }
    if (ui.sort) { ui.sort.addEventListener("change", renderTable); }
    applyLang();
    document.addEventListener("langchange", applyLang);
  }

  function fail(reason) {
    banner("bad",
      "The sanctions projection could not be loaded",
      "无法载入制裁投影数据",
      "The page frame, the method note and the source contract below still describe exactly what this desk reads. Reload to try the artifact again.",
      "页面框架、方法说明与下方来源约定仍完整描述本页所读取的内容。请重新载入以再次尝试。",
      String(reason || "load failed"));
    if (ui.tbody) {
      clear(ui.tbody);
    }
    if (ui.entries) {
      emptyState(ui.entries, "Nothing loaded", "未载入数据",
        "The projection artifact did not load, so there is no entry detail to show.",
        "投影数据未能载入，因此没有可显示的条目明细。");
    }
  }

  function getJSON(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) { throw new Error(url + " → HTTP " + r.status); }
      return r.json();
    });
  }

  function boot() {
    Promise.all([getJSON(DATA_URL), getJSON(TOPO_URL)]).then(function (out) {
      var p = out[0];
      model.projection = p;
      root.setAttribute("data-source-state", String(p.source_state || ""));
      index(p);
      renderFigures(p);
      renderAsOf(p);
      renderProvenance(p);
      renderMap(p, out[1]);
      renderTable();
      renderEntries();
      renderChanges(p);
      renderCoverage(p);
      renderSource(p);
      renderHealth(p);
      wire();
    }).catch(function (err) {
      fail(err && err.message ? err.message : err);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}());

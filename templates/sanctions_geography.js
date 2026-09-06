/* F02-X1 — Official sanctions geography desk.
   Copied byte-for-byte to site/sanctions-geography.js by the builder's ASSET_MAP
   (underscored template source, hyphenated site output).

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
     * ADDED_SINCE_PREVIOUS / REMOVED_SINCE_PREVIOUS come only from an explicit official delta action; the
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
    view: root.querySelector("[data-sg-view]"),
    program: root.querySelector("[data-sg-program]"),
    type: root.querySelector("[data-sg-type]"),
    change: root.querySelector("[data-sg-change]"),
    list: root.querySelector("[data-sg-list]"),
    filters: root.querySelector("[data-sg-filters]"),
    thead: root.querySelector("[data-sg-thead]"),
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
    byGeo: {},          /* geo_id -> country row        */
    entriesByGeo: {},   /* geo_id -> [entry]            */
    typesByGeo: {},     /* geo_id -> {entity_type:true} */
    shardStatus: {},    /* geo_id -> loading|ready|error */
    shardErrors: {},
    shardPromises: {},
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

  /* A delta may legally carry a correction with no entity-level name. Printing
     an empty heading loses the one identifier that IS always present, so the
     published UID becomes the visible name rather than a blank row. */
  function displayName(record, target) {
    var name = record && record.name ? String(record.name).trim() : "";
    if (name) {
      target.textContent = name;
      return target;
    }
    return bi(target,
      "OFAC UID " + (record && record.uid !== undefined ? record.uid : "—"),
      "OFAC 编号 " + (record && record.uid !== undefined ? record.uid : "—"));
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
    var health = String(p.source_state || src.source_health || "").toUpperCase();
    clear(ui.prov);

    ui.prov.className = "sg-prov " + (
      health === "CURRENT" ? "sg-prov--ok"
        : (health === "SOURCE_STALE" ? "sg-prov--warn" : "sg-prov--bad")
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
    features.forEach(function (f) {
      if (f.id !== undefined && f.id !== null && String(f.id)) {
        model.drawableIds[String(f.id)] = true;
      }
    });

    var width = 960;
    var height = 460;
    var proj = d3.geoNaturalEarth1().fitSize([width, height], geo);
    var path = d3.geoPath(proj);

    ui.map.setAttribute("viewBox", "0 0 " + width + " " + height);
    ui.map.setAttribute("preserveAspectRatio", "xMidYMid meet");
    clear(ui.map);

    var NS = "http://www.w3.org/2000/svg";
    var defs = document.createElementNS(NS, "defs");
    var pattern = document.createElementNS(NS, "pattern");
    pattern.setAttribute("id", "sg-identityless-pattern");
    pattern.setAttribute("width", "6");
    pattern.setAttribute("height", "6");
    pattern.setAttribute("patternUnits", "userSpaceOnUse");
    var patternBg = document.createElementNS(NS, "rect");
    patternBg.setAttribute("class", "sg-identityless-pattern-bg");
    patternBg.setAttribute("width", "6");
    patternBg.setAttribute("height", "6");
    var patternLine = document.createElementNS(NS, "path");
    patternLine.setAttribute("class", "sg-identityless-pattern-line");
    patternLine.setAttribute("d", "M-1,1 L1,-1 M0,6 L6,0 M5,7 L7,5");
    pattern.appendChild(patternBg);
    pattern.appendChild(patternLine);
    defs.appendChild(pattern);
    ui.map.appendChild(defs);

    features.forEach(function (f) {
      var d = path(f);
      if (!d) { return; }
      var hasCanonicalId = f.id !== undefined && f.id !== null && String(f.id);
      var id = hasCanonicalId ? String(f.id) : "";
      var row = model.byGeo[id];
      var count = row ? Number(row.entries) || 0 : 0;
      var name = row ? row.country : ((f.properties && f.properties.name) || id);

      var node = document.createElementNS(NS, "path");
      node.setAttribute("d", d);
      node.setAttribute("class", "sg-geo" + (!hasCanonicalId ? " is-identityless" : "") +
        (count > 0 ? " is-pick" : ""));
      if (hasCanonicalId) {
        node.setAttribute("data-geo-id", id);
        node.setAttribute("data-count", String(count));
        node.setAttribute("data-step", String(stepFor(count)));
      } else {
        node.setAttribute("data-step", "identityless");
      }
      if (count > 0) {
        node.setAttribute("tabindex", "0");
        node.setAttribute("aria-disabled", "false");
        node.setAttribute("role", "button");
        node.setAttribute("data-name-en", name + ": " + num(count) +
          " listed entries with a published address here");
        node.setAttribute("data-name-zh", name + "：" + num(count) +
          " 条名单记录在此有公开地址");
        node.addEventListener("click", function () {
          if (node.classList.contains("is-off")) { return; }
          select(id);
        });
        node.addEventListener("keydown", function (ev) {
          if (ev.key !== "Enter" && ev.key !== " ") { return; }
          ev.preventDefault();
          if (node.classList.contains("is-off")) { return; }
          select(id);
        });
      }
      var title = document.createElementNS(NS, "title");
      title.textContent = hasCanonicalId
        ? name + " · " + num(count)
        : name + " · geometry identity unavailable; see off-map register";
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

  /* ---------------- country table + structured filters -------------------

     Four filters beyond free text, each answering a question the register can
     actually support, and none inferring anything the projection does not say:

       view     — resolved boundaries (paintable) vs published places we could
                  not place at all. These are two different registers, so they
                  are a view switch rather than a filter on one list.
       program  — a boundary is kept when the projection lists that program for
                  it. The option list is the union the artifact itself carries.
       type     — derived from the entries indexed under the boundary, never
                  from a name or an address string.
       change   — an explicit official add/remove in this window, or none.

     When the view has no meaning for a control, the control is DISABLED rather
     than silently ignored, so the UI never claims a filter it is not applying.
  */

  function fillSelect(select, values, labeller) {
    if (!select) { return; }
    while (select.options.length > 1) { select.remove(1); }
    values.forEach(function (value) {
      var opt = document.createElement("option");
      opt.value = value;
      var pair = labeller(value);
      opt.setAttribute("data-label-en", pair[0]);
      opt.setAttribute("data-label-zh", pair[1]);
      opt.textContent = pair[0];
      select.appendChild(opt);
    });
  }

  var TYPE_ZH = { Individual: "个人", Entity: "实体", Vessel: "船舶", Aircraft: "航空器" };

  function populateFilters(p) {
    var boundariesPerProgram = {};
    (p.countries || []).forEach(function (r) {
      (r.programs || []).forEach(function (pr) {
        var key = String(pr.program || "");
        if (!key) { return; }
        boundariesPerProgram[key] = (boundariesPerProgram[key] || 0) + 1;
      });
    });
    var programs = Object.keys(boundariesPerProgram).sort();
    fillSelect(ui.program, programs, function (value) {
      var n = boundariesPerProgram[value];
      return [value + " (" + n + ")", value + "（" + n + "）"];
    });

    var types = {};
    (p.countries || []).forEach(function (country) {
      (country.entry_types || []).forEach(function (entryType) {
        if (entryType) { types[String(entryType)] = true; }
      });
    });
    fillSelect(ui.type, Object.keys(types).sort(), function (value) {
      return [value, TYPE_ZH[value] || value];
    });
  }

  function currentView() {
    return (ui.view && ui.view.value) === "unresolved" ? "unresolved" : "resolved";
  }

  function syncControls() {
    var resolved = currentView() === "resolved";
    [ui.program, ui.type, ui.change].forEach(function (control) {
      if (!control) { return; }
      control.disabled = !resolved;
      control.setAttribute("aria-disabled", resolved ? "false" : "true");
    });
  }

  function matchesText(haystack, q) {
    return !q || haystack.toLowerCase().indexOf(q) >= 0;
  }

  function unresolvedRows() {
    var p = model.projection;
    var rows = (p.unresolved_geography || []).map(function (u) {
      return { place: u.published_country, addresses: u.published_addresses, reason: "unplaced" };
    });
    if (model.drawableIds) {
      (p.countries || []).forEach(function (r) {
        if (!model.drawableIds[String(r.geo_id)]) {
          rows.push({ place: r.country, addresses: r.published_addresses, reason: "nogeometry" });
        }
      });
    }
    return rows;
  }

  function visibleRows() {
    var q = (ui.search && ui.search.value ? ui.search.value : "").trim().toLowerCase();
    var mode = ui.sort && ui.sort.value ? ui.sort.value : "entries";

    if (currentView() === "unresolved") {
      var off = unresolvedRows().filter(function (r) {
        return matchesText(String(r.place || ""), q);
      });
      off.sort(function (a, b) {
        if (mode === "name") { return String(a.place).localeCompare(String(b.place)); }
        return (Number(b.addresses) || 0) - (Number(a.addresses) || 0);
      });
      return off;
    }

    var program = ui.program && !ui.program.disabled ? ui.program.value : "";
    var type = ui.type && !ui.type.disabled ? ui.type.value : "";
    var change = ui.change && !ui.change.disabled ? ui.change.value : "";

    var rows = (model.projection.countries || []).filter(function (r) {
      var text = String(r.country || "") + " " + (r.programs || []).map(function (pr) {
        return pr.program;
      }).join(" ");
      if (!matchesText(text, q)) { return false; }
      if (program && !(r.programs || []).some(function (pr) { return pr.program === program; })) {
        return false;
      }
      if (type) {
        var seen = model.typesByGeo[String(r.geo_id)];
        if (!seen || !seen[type]) { return false; }
      }
      if (change) {
        var moved = (Number(r.added) || 0) + (Number(r.removed) || 0) > 0;
        if (change === "changed" && !moved) { return false; }
        if (change === "unchanged" && moved) { return false; }
      }
      return true;
    });

    rows.sort(function (a, b) {
      if (mode === "name") { return String(a.country).localeCompare(String(b.country)); }
      if (mode === "changed") {
        return ((b.added || 0) + (b.removed || 0)) - ((a.added || 0) + (a.removed || 0));
      }
      return (Number(b.entries) || 0) - (Number(a.entries) || 0);
    });
    return rows;
  }

  function renderHead() {
    if (!ui.thead) { return; }
    clear(ui.thead);
    var tr = el("tr");
    function th(en, zh, right) {
      var cell = el("th", right ? "sg-r" : null);
      cell.setAttribute("scope", "col");
      bi(cell, en, zh);
      tr.appendChild(cell);
    }
    if (currentView() === "unresolved") {
      th("Published place", "公开地点");
      th("Addresses", "地址", true);
      th("Why it is off the map", "无法上图的原因");
    } else {
      th("Boundary", "边界");
      th("Entries", "条目", true);
      th("Addresses", "地址", true);
      th("Added / removed", "新增 / 移除", true);
      th("Programs", "项目");
    }
    ui.thead.appendChild(tr);
  }

  /* The map is a view of the same filtered register as the table. Leaving every
     boundary lit while the table shows twelve rows would make the map contradict
     the list beside it — and a selection that the filter has excluded is a claim
     about a row the reader can no longer see, so it is cleared. */
  function syncMap(rows) {
    if (!ui.map) { return; }
    var unresolvedView = currentView() === "unresolved";
    var visible = {};
    if (!unresolvedView) {
      rows.forEach(function (r) { visible[String(r.geo_id)] = true; });
    }
    var total = (model.projection.countries || []).length;
    var filtered = unresolvedView || rows.length !== total;
    var nodes = ui.map.querySelectorAll(".sg-geo");
    Array.prototype.forEach.call(nodes, function (node) {
      var id = node.getAttribute("data-geo-id");
      var named = !!model.byGeo[id];
      var off = filtered && named && !visible[id];
      node.classList.toggle("is-off", !!off);
      /* `pointer-events:none` only takes the mouse away. A filtered-out boundary
         that keeps tabindex=0 and its Enter/Space handler is still reachable and
         still selectable by keyboard — the filter would apply to one input device
         and not the other. Focusability and the exposed state move together. */
      if (!node.classList.contains("is-pick")) { return; }
      node.setAttribute("tabindex", off ? "-1" : "0");
      node.setAttribute("aria-disabled", off ? "true" : "false");
    });
    if (model.selected && !visible[model.selected]) {
      model.selected = null;
      Array.prototype.forEach.call(nodes, function (node) {
        node.classList.remove("is-on");
        if (node.hasAttribute("aria-pressed")) { node.setAttribute("aria-pressed", "false"); }
      });
      renderEntries();
    }
  }

  function renderTable() {
    if (!ui.tbody) { return; }
    syncControls();
    renderHead();
    var unresolvedView = currentView() === "unresolved";
    var columns = unresolvedView ? 3 : 5;
    var rows = visibleRows();
    syncMap(rows);
    clear(ui.tbody);

    if (!rows.length) {
      /* NO_RESULTS — the frozen empty-query state. A filter that matches nothing
         says so and says why; it never synthesises a fact to fill the box. */
      var tr = el("tr");
      var td = el("td");
      td.setAttribute("colspan", String(columns));
      var host = el("div");
      td.appendChild(host);
      tr.appendChild(td);
      ui.tbody.appendChild(tr);
      emptyState(host,
        "No row matches these filters",
        "没有符合当前筛选的记录",
        "Nothing in the current register matches every filter you have set. Widen one of them to see rows again.",
        "当前登记册中没有同时满足所有筛选条件的记录。放宽其中一项即可重新看到内容。");
      code(host, "NO_RESULTS");
      return;
    }

    if (unresolvedView) {
      rows.forEach(function (r) {
        var tr2 = el("tr");
        var place = el("td");
        var raw = String(r.place === undefined ? "" : r.place);
        if (!raw.trim() || raw === "(blank)") {
          bi(place, "Address names no country", "地址未填写国家");
          code(place, raw.trim() ? raw : "(blank)");
        } else {
          place.textContent = raw;
        }
        tr2.appendChild(place);
        tr2.appendChild(el("td", "sg-r", num(r.addresses)));
        var why = el("td", "sg-unres");
        if (r.reason === "nogeometry") {
          bi(why, "Counted, but this boundary is not in the 110m map",
                  "已计数，但 110m 地图中没有该边界");
        } else {
          bi(why, "No boundary matched this published country",
                  "该公开国家未匹配到任何边界");
        }
        tr2.appendChild(why);
        ui.tbody.appendChild(tr2);
      });
      return;
    }

    rows.forEach(function (r) {
      var id = String(r.geo_id);
      var tr3 = el("tr");
      tr3.setAttribute("tabindex", "0");
      tr3.setAttribute("data-geo-id", id);
      if (model.selected === id) { tr3.className = "is-on"; }

      tr3.appendChild(el("td", null, r.country));
      tr3.appendChild(el("td", "sg-r", num(r.entries)));
      tr3.appendChild(el("td", "sg-r", num(r.published_addresses)));

      var delta = el("td", "sg-r");
      var added = Number(r.added) || 0;
      var removed = Number(r.removed) || 0;
      delta.textContent = (added || removed) ? ("+" + added + " / \u2212" + removed) : "—";
      tr3.appendChild(delta);

      var progs = (r.programs || []).slice(0, 2).map(function (pr) { return pr.program; });
      var extra = Math.max(0, (r.programs || []).length - progs.length);
      var td2 = el("td", "sg-mono");
      td2.textContent = progs.join(", ") + (extra ? "  +" + extra : "");
      tr3.appendChild(td2);

      tr3.addEventListener("click", function () { select(id); });
      tr3.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(id); }
      });
      ui.tbody.appendChild(tr3);
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
    if (model.selected) {
      loadSelectedEntries(model.selected).catch(function () {
        /* The loader records and renders its own typed detail failure. */
      });
    }
  }

  function chip(parent, cls, en, zh) {
    var c = el("span", "sg-chip " + cls);
    bi(c, en, zh);
    parent.appendChild(c);
  }

  function entryCard(entry, geoId) {
    var box = el("div", "sg-entry");
    box.appendChild(displayName(entry, el("div", "sg-entry-n")));

    var uid = el("div", "sg-entry-uid");
    uid.textContent = "OFAC UID " + entry.uid + " · " + (entry.entity_type || "—");
    box.appendChild(uid);

    var states = entry.states || (entry.state ? [entry.state] : []);
    var chips = el("div");
    (entry.programs || []).slice(0, 4).forEach(function (pr) {
      chip(chips, "sg-chip--prog", String(pr), String(pr));
    });
    states.forEach(function (st) {
      if (st === "ADDED_SINCE_PREVIOUS") { chip(chips, "sg-chip--added", "Added by official delta", "官方增量新增"); }
      else if (st === "REMOVED_SINCE_PREVIOUS") { chip(chips, "sg-chip--removed", "Removed by official delta", "官方增量移除"); }
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
      if (a.state === "GEOGRAPHY_UNRESOLVED" || !a.geo_id) {
        var mark = el("span", "sg-chip sg-chip--unres");
        bi(mark, "Could not be placed", "无法定位边界");
        dd.appendChild(document.createTextNode(" "));
        dd.appendChild(mark);
        code(dd, "GEOGRAPHY_UNRESOLVED");
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

    var status = model.shardStatus[model.selected];
    if (!status || status === "loading") {
      emptyState(ui.entries,
        "Loading entry detail",
        "正在载入条目明细",
        "The boundary register is ready. Its projection-bound detail shard is loading on demand.",
        "边界登记册已就绪；与该投影绑定的明细分片正在按需载入。");
      return;
    }
    if (status === "error") {
      emptyState(ui.entries,
        "Entry detail could not be verified",
        "无法验证条目明细",
        "The boundary count remains readable, but its detail shard was missing, malformed, stale, or failed its SHA-256 check.",
        "边界计数仍可读取，但其明细分片缺失、格式错误、已过期或未通过 SHA-256 校验。");
      code(ui.entries, "PARSER_SHAPE_CHANGED / ENTRY_SHARD");
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
      box.appendChild(displayName(c, el("div", "sg-crow-n")));
      var meta = el("div", "sg-crow-m");
      meta.textContent = (c.published_at || "").slice(0, 10) + " · UID " + c.uid;
      box.appendChild(meta);
      var chips = el("div", "sg-crow-s");
      /* The state comes from the official delta's own action field. Nothing
         here infers a removal from an absence. */
      if (c.state === "ADDED_SINCE_PREVIOUS" || c.action === "add") {
        chip(chips, "sg-chip--added", "Added", "新增");
      } else if (c.state === "REMOVED_SINCE_PREVIOUS" || c.action === "remove") {
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
      "Published addresses we could not place — kept as GEOGRAPHY_UNRESOLVED, never folded into a neighbour.",
      "无法定位的公开地址 — 保留为 GEOGRAPHY_UNRESOLVED，绝不并入邻国。");
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
      if (rec.catalog_size_match === false) {
        kv("Catalog byte verification", "目录字节校验", "SIZE_MISMATCH / SHA-256 unavailable", true);
      }
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
    if (state === "SOURCE_UNAVAILABLE") {
      banner("bad",
        "The official file could not be reached for this build",
        "本次构建无法访问官方文件",
        "Every figure below is the last accepted projection, kept deliberately rather than replaced with an empty success. Counts, boundaries and the source receipt are still readable; only the freshness is not.",
        "以下所有数字来自最近一次已接受的投影，我们刻意保留而非以空结果覆盖。计数、边界与来源凭证仍可查阅，仅时效性无法保证。",
        "SOURCE_UNAVAILABLE");
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
    /* The deterministic artifact carries source_state=CURRENT plus a
       freshness.stale_after deadline: staleness is a fact about the CLOCK, so
       it is derived from that deadline whenever it has passed, and an explicit
       SOURCE_STALE label is still honoured on its own. */
    var after = fresh.stale_after || "";
    var deadlinePassed = !!after && new Date(after).getTime() <= Date.now();
    var labelled = state === "SOURCE_STALE" ||
      String(fresh.stale_state || "").toUpperCase() === "SOURCE_STALE";
    if (labelled || deadlinePassed) {
      {
        banner("stale",
          "This read is behind the official publication clock",
          "此读数已落后于官方发布时间",
          "The list itself has not been re-acquired since the published date on the receipt. Treat the counts as of that date, not as of today.",
          "自凭证所载发布日期以来，名单未再次获取。请按该日期而非今日理解这些计数。",
          "SOURCE_STALE");
      }
    }
  }

  /* ---------------- boot -------------------------------------------------- */

  function index(p) {
    model.byGeo = {};
    (p.countries || []).forEach(function (r) { model.byGeo[String(r.geo_id)] = r; });

    model.entriesByGeo = {};
    model.typesByGeo = {};
    model.shardStatus = {};
    model.shardErrors = {};
    model.shardPromises = {};
    (p.countries || []).forEach(function (country) {
      var id = String(country.geo_id);
      model.typesByGeo[id] = {};
      (country.entry_types || []).forEach(function (entryType) {
        model.typesByGeo[id][String(entryType)] = true;
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
    [ui.list, ui.view, ui.program, ui.type, ui.change, ui.sort].forEach(function (select) {
      if (!select) { return; }
      Array.prototype.forEach.call(select.options, function (opt) {
        var label = opt.getAttribute(zh ? "data-label-zh" : "data-label-en");
        if (label) { opt.textContent = label; }
      });
    });
    /* An accessible name left in English is still an untranslated string — it is
       simply one only a screen-reader user hears. */
    [ui.search, ui.list, ui.view, ui.program, ui.type, ui.change, ui.sort, ui.filters]
      .forEach(function (control) {
        if (!control) { return; }
        var name = control.getAttribute(zh ? "data-aria-zh" : "data-aria-en");
        if (name) { control.setAttribute("aria-label", name); }
      });
    updateMapAccessibleNames(zh);
  }

  function updateMapAccessibleNames(zh) {
    if (!ui.map) { return; }
    var nodes = ui.map.querySelectorAll(".sg-geo.is-pick");
    Array.prototype.forEach.call(nodes, function (node) {
      var name = node.getAttribute(zh ? "data-name-zh" : "data-name-en");
      if (name) { node.setAttribute("aria-label", name); }
    });
  }

  function wire() {
    if (ui.search) { ui.search.addEventListener("input", renderTable); }
    [ui.view, ui.program, ui.type, ui.change, ui.sort].forEach(function (control) {
      if (control) { control.addEventListener("change", renderTable); }
    });
    applyLang();
    document.addEventListener("langchange", function () { applyLang(); renderTable(); });
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

  function sha256Hex(buffer) {
    if (!window.crypto || !window.crypto.subtle) {
      return Promise.reject(new Error("Web Crypto unavailable; shard verification refused"));
    }
    return window.crypto.subtle.digest("SHA-256", buffer).then(function (digest) {
      return Array.prototype.map.call(new Uint8Array(digest), function (byte) {
        return byte.toString(16).padStart(2, "0");
      }).join("");
    });
  }

  function loadSelectedEntries(geoId) {
    var id = String(geoId || "");
    if (!/^[0-9]{3}$/.test(id)) {
      return Promise.reject(new Error("non-canonical shard identity"));
    }
    if (model.shardStatus[id] === "ready") {
      return Promise.resolve(model.entriesByGeo[id] || []);
    }
    if (model.shardStatus[id] === "loading" && model.shardPromises[id]) {
      return model.shardPromises[id];
    }
    var manifest = model.projection && model.projection.entry_shards;
    var record = manifest && manifest.by_geo && manifest.by_geo[id];
    var expectedPath = "sanctions-geography-entries/" + id + ".json";
    if (!record || record.path !== expectedPath ||
        !/^[0-9a-f]{64}$/.test(String(record.sha256 || "")) ||
        !Number.isInteger(record.bytes) || record.bytes <= 0 ||
        !Number.isInteger(record.entries) || record.entries < 0) {
      model.shardStatus[id] = "error";
      model.shardErrors[id] = "manifest mismatch";
      renderEntries();
      return Promise.reject(new Error("entry shard is absent from the canonical manifest"));
    }
    var url = new URL(record.path, window.location.href);
    if (url.origin !== window.location.origin) {
      model.shardStatus[id] = "error";
      model.shardErrors[id] = "cross-origin path refused";
      renderEntries();
      return Promise.reject(new Error("entry shard must be same-origin"));
    }

    model.shardStatus[id] = "loading";
    renderEntries();
    var request = fetch(url.href, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) { throw new Error(record.path + " → HTTP " + response.status); }
        return response.arrayBuffer();
      })
      .then(function (buffer) {
        if (buffer.byteLength !== record.bytes) {
          throw new Error("entry shard byte count mismatch");
        }
        return sha256Hex(buffer).then(function (actualHash) {
          if (actualHash !== record.sha256) { throw new Error("entry shard SHA-256 mismatch"); }
          var payload;
          try {
            payload = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(buffer));
          } catch (error) {
            throw new Error("entry shard JSON is malformed");
          }
          if (!payload || payload.schema_version !== model.projection.schema_version ||
              payload.parser_revision !== model.projection.parser_revision ||
              payload.projection_id !== model.projection.projection_id ||
              payload.source_identity !== model.projection.source_identity ||
              payload.geo_id !== id || !Array.isArray(payload.entries) ||
              payload.entries.length !== record.entries) {
            throw new Error("entry shard identity is stale or malformed");
          }
          model.entriesByGeo[id] = payload.entries;
          model.shardStatus[id] = "ready";
          delete model.shardErrors[id];
          if (model.selected === id) { renderEntries(); }
          return payload.entries;
        });
      })
      .catch(function (error) {
        model.shardStatus[id] = "error";
        model.shardErrors[id] = String(error && error.message ? error.message : error);
        if (model.selected === id) { renderEntries(); }
        throw error;
      });
    model.shardPromises[id] = request;
    return request;
  }

  /* Reproducible behavioral contract seam. The committed Node probe supplies a
     minimal DOM and opts in before this file loads; normal browsers never set
     the flag, never receive the seam, and continue directly to boot(). */
  if (window.__SANCTIONS_GEOGRAPHY_TEST__ === true) {
    window.__sanctionsGeographyBehavior = {
      applyLang: applyLang,
      getSelected: function () { return model.selected; },
      getShardStatus: function (geoId) { return model.shardStatus[String(geoId)]; },
      loadSelectedEntries: loadSelectedEntries,
      setProjection: function (p) { model.projection = p; index(p); },
      setSelected: function (geoId) { model.selected = geoId; },
      syncMap: syncMap
    };
    return;
  }

  function mapDegraded(reason) {
    if (ui.mapSkel) {
      clear(ui.mapSkel);
      ui.mapSkel.removeAttribute("hidden");
      ui.mapSkel.setAttribute("data-sg-map-degraded", "true");
      var note = document.createElement("p");
      note.className = "sg-map-degraded-note";
      note.setAttribute("data-i18n-en", "The boundary map could not be drawn — the register below is complete.");
      note.setAttribute("data-i18n-zh", "边界地图无法绘制 — 下方登记册完整。");
      note.textContent = "The boundary map could not be drawn — the register below is complete.";
      ui.mapSkel.appendChild(note);
      applyLang();
    }
    if (ui.map) { ui.map.setAttribute("hidden", "hidden"); }
    if (window.console && window.console.warn) {
      window.console.warn("sanctions-geography: boundary map degraded", reason);
    }
  }

  function boot() {
    var dataReady = getJSON(DATA_URL).then(function (p) {
      model.projection = p;
      root.setAttribute("data-source-state", String(p.source_state || ""));
      index(p);
      renderFigures(p);
      renderAsOf(p);
      renderProvenance(p);
      populateFilters(p);
      applyLang();
      renderTable();
      renderEntries();
      renderChanges(p);
      renderCoverage(p);
      renderSource(p);
      renderHealth(p);
      wire();
      return p;
    }).catch(function (err) {
      fail(err && err.message ? err.message : err);
      throw err;
    });

    dataReady.then(function (p) {
      getJSON(TOPO_URL).then(function (topo) {
        renderMap(p, topo);
      }).catch(function (err) {
        mapDegraded(err && err.message ? err.message : err);
      });
    }, function () {
      /* dataReady already failed and reported via fail(); the map never mounts. */
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}());

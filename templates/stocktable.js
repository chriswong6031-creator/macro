/**
 * stocktable.js — market-generic dense-table module for standout boards.
 *
 * Usage: include this file, then call StockTable.init(config) where config = {
 *   dataId:     'stocktable-data',    // id of <script type="application/json"> element
 *   containerId:'stocktable-wrap',    // id of mount container element
 *   market:     'cn',                 // localStorage namespace key (e.g. 'cn', 'us', 'hk')
 *   linkPattern: 'china_lookup.html#{ticker}', // row link template
 *   columns:    [...],                // column schema array (see below)
 *   stageFilter: true,                // show stage filter row
 * }
 *
 * Column schema entry: { key, labelEn, labelZh, default, sortable, right, fmt, tip }
 *   key:     field key on row object (dot-notation not supported)
 *   default: true = shown by default; false = hidden by default
 *   right:   true = right-align numeric
 *   fmt:     optional function(val, row) => string/HTML for cell content
 *   tip:     { en, zh } tooltip text (no title= attribute — uses data-tip-en/zh)
 *
 * Performance target: <50ms render for 160 rows on a 2020 laptop (single reflow,
 * DocumentFragment, no layout thrash).
 *
 * No external dependencies. <25KB minified. Bilingual via l-en/l-zh spans convention.
 */
(function (global) {
  'use strict';

  /* ── constants ───────────────────────────────────────────────────────── */
  // v2 prefix: v1 persisted 15-column defaults that overflowed the viewport and
  // the chooser was unreachable, so stale v1 state is deliberately abandoned.
  var LS_PREFIX = 'mdx_stocktable2_';
  var FRESH_DAYS = 2;  // days_since_signal <= 2 → show NEW dot

  /* ── helpers ─────────────────────────────────────────────────────────── */
  function bi(en, zh) {
    return '<span class="l-en">' + en + '</span><span class="l-zh">' + (zh || en) + '</span>';
  }

  // Active UI language. <option> elements and input placeholders cannot carry the
  // dual l-en/l-zh spans (CSS can't restyle inside them), so the filter row renders
  // in ONE language and relabels itself on theme.js's 'langchange' event.
  function curLang() {
    return document.documentElement.getAttribute('data-lang') === 'zh' ? 'zh' : 'en';
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                    .replace(/"/g,'&quot;');
  }

  function fmtNum(v, digits) {
    if (v == null || v === '') return '—';
    var n = parseFloat(v);
    if (isNaN(n)) return '—';
    return n.toFixed(digits == null ? 2 : digits);
  }

  function fmtPct(v, digits) {
    if (v == null || v === '') return '—';
    var n = parseFloat(v);
    if (isNaN(n)) return '—';
    var s = (n >= 0 ? '+' : '') + n.toFixed(digits == null ? 1 : digits) + '%';
    return '<span class="' + (n >= 0 ? 'st-pos' : 'st-neg') + '">' + esc(s) + '</span>';
  }

  function macdGlyph(d, d2, d3) {
    // Each arg: positive / negative / null
    function glyph(v) {
      if (v == null) return '<span class="st-muted">·</span>';
      return v > 0 ? '<span class="st-pos">▲</span>' : '<span class="st-neg">▼</span>';
    }
    return glyph(d) + glyph(d2) + glyph(d3);
  }

  function readLs(key) {
    try { return localStorage.getItem(key); } catch(e) { return null; }
  }
  function writeLs(key, val) {
    try { localStorage.setItem(key, val); } catch(e) {}
  }
  function readLsJson(key, def) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : def; }
    catch(e) { return def; }
  }
  function writeLsJson(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch(e) {}
  }

  /* ── sort state ────────────────────────────────────────────────────────── */
  // 3-state: 'asc' / 'desc' / null (system order)
  function nextSortState(cur) {
    if (cur === null) return 'asc';
    if (cur === 'asc') return 'desc';
    return null;
  }

  /* ── main module ─────────────────────────────────────────────────────── */
  function init(cfg) {
    var dataEl = document.getElementById(cfg.dataId);
    if (!dataEl) return;
    var payload;
    try { payload = JSON.parse(dataEl.textContent || dataEl.innerHTML); }
    catch(e) { console.warn('StockTable: JSON parse failed', e); return; }

    var container = document.getElementById(cfg.containerId);
    if (!container) return;

    var market = cfg.market || 'cn';
    var lsView   = LS_PREFIX + market + '_view';       // 'grid' or 'table'
    var lsCols   = LS_PREFIX + market + '_cols';       // JSON array of visible col keys
    var lsOrder  = LS_PREFIX + market + '_order';      // JSON array of col keys (order)

    var allRows = (payload.rows || []).slice();  // master copy in system order
    var columns = cfg.columns || [];             // column schema

    /* ── persisted column state ───────────────────────────────────────── */
    var defaultVisible  = columns.filter(function(c){ return c.default !== false; }).map(function(c){ return c.key; });
    var defaultOrder    = columns.map(function(c){ return c.key; });

    var visibleCols  = readLsJson(lsCols,  defaultVisible);
    var colOrder     = readLsJson(lsOrder, defaultOrder);

    // Merge: new columns in schema not in persisted order → append
    defaultOrder.forEach(function(k) {
      if (colOrder.indexOf(k) === -1) colOrder.push(k);
    });
    // Remove cols that no longer exist in schema
    colOrder = colOrder.filter(function(k){ return columns.some(function(c){ return c.key === k; }); });
    visibleCols = visibleCols.filter(function(k){ return columns.some(function(c){ return c.key === k; }); });

    /* ── filter state ─────────────────────────────────────────────────── */
    var filters = { stage: 'all', zone: 'all', tier: 'all', sector: 'all',
                    theme: '', capBucket: 'all', freshOnly: false };

    // Per-value display labels for filter options (cfg.optionLabels =
    // { filterName: { VALUE: [en, zh] } }), raw value as fallback. Declared
    // BEFORE the skeleton build below — _buildFilterRow reads these at call time.
    var optionLabels = cfg.optionLabels || {};
    var FILTER_TITLES = { stage: ['All stages','全部阶段'], zone: ['All zones','全部区域'],
                          tier: ['All tiers','全部级别'], sector: ['All sectors','全部板块'],
                          capBucket: ['All sizes','全部市值'] };
    var SEARCH_PH = cfg.searchPlaceholder || ['Search name or theme…','搜索名称或主题…'];

    /* ── sort state ───────────────────────────────────────────────────── */
    var sortKey   = null;  // null = system order
    var sortDir   = null;  // 'asc' / 'desc' / null

    /* ── build skeleton ───────────────────────────────────────────────── */
    container.innerHTML = '';
    container.style.position = 'relative';

    // ── filter row ──
    var frow = document.createElement('div');
    frow.className = 'st-frow';
    frow.innerHTML = _buildFilterRow(allRows, payload);
    container.appendChild(frow);

    // ── column chooser panel ──
    // Anchored between the filter row and the table (NOT after the table): the
    // panel is absolutely positioned at the top of this zero-height wrapper, so
    // it must sit here to drop down next to the "Columns" button — appended after
    // the table it opened thousands of pixels below the fold, i.e. invisibly.
    var chooserWrap = document.createElement('div');
    chooserWrap.className = 'st-chooser-wrap st-chooser-hidden';
    chooserWrap.innerHTML = _buildChooser(columns, colOrder, visibleCols, market);
    container.appendChild(chooserWrap);

    // ── table wrapper ──
    var tableWrap = document.createElement('div');
    tableWrap.className = 'st-table-wrap';

    var table = document.createElement('table');
    table.className = 'st-table';

    var thead = document.createElement('thead');
    var tbody = document.createElement('tbody');
    table.appendChild(thead);
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    container.appendChild(tableWrap);

    // ── render header ──
    renderHeader();

    // ── render rows ──
    renderRows();

    // ── bind filter events ──
    bindFilters();

    // ── bind chooser events ──
    bindChooser();

    /* ── render functions ──────────────────────────────────────────────── */

    function orderedCols() {
      return colOrder
        .map(function(k){ return columns.find(function(c){ return c.key === k; }); })
        .filter(function(c){ return c && visibleCols.indexOf(c.key) !== -1; });
    }

    function renderHeader() {
      thead.innerHTML = '';
      var tr = document.createElement('tr');
      // first-col sticky placeholder
      orderedCols().forEach(function(col, idx) {
        var th = document.createElement('th');
        if (idx === 0) th.className = 'st-sticky-col';
        if (col.cls) th.className += (th.className ? ' ' : '') + col.cls;
        if (col.sortable !== false) {
          th.className += (th.className ? ' ' : '') + 'st-sortable';
          th.setAttribute('data-key', col.key);
        }
        // sort arrow
        var arrow = '';
        if (sortKey === col.key) {
          arrow = ' <span class="st-sarrow">' + (sortDir === 'asc' ? '▲' : '▼') + '</span>';
        } else {
          arrow = ' <span class="st-sarrow st-sarrow-idle">▼</span>';
        }
        var tipHtml = '';
        if (col.tip) {
          tipHtml = '<span class="st-th-tip" data-tip-en="' + esc(col.tip.en) + '" data-tip-zh="' + esc(col.tip.zh || col.tip.en) + '">?</span>';
        }
        th.innerHTML = bi(col.labelEn, col.labelZh) + arrow + tipHtml;
        if (col.sortable !== false) {
          th.addEventListener('click', function() {
            var k = th.getAttribute('data-key');
            if (sortKey === k) {
              sortDir = nextSortState(sortDir);
              if (sortDir === null) sortKey = null;
            } else {
              sortKey = k;
              sortDir = 'asc';
            }
            renderHeader();
            renderRows();
          });
        }
        tr.appendChild(th);
      });
      thead.appendChild(tr);
    }

    function applyFilters(rows) {
      return rows.filter(function(r) {
        if (filters.stage !== 'all' && (r.stage || 'ALL') !== filters.stage) return false;
        if (filters.zone !== 'all' && (r.zone || '') !== filters.zone) return false;
        if (filters.tier !== 'all' && (r.tier || '') !== filters.tier) return false;
        if (filters.sector !== 'all' && (r.sector || '') !== filters.sector) return false;
        if (filters.capBucket !== 'all' && (r.cap_bucket || 'unknown') !== filters.capBucket) return false;
        if (filters.freshOnly && !(r.days_since_signal != null && r.days_since_signal <= FRESH_DAYS)) return false;
        if (filters.theme) {
          var th = filters.theme.toLowerCase();
          var themeVal = ((r.narrative && r.narrative.theme) || '').toLowerCase();
          var themeZh  = ((r.narrative && r.narrative.theme_zh) || '').toLowerCase();
          var nm = (r.name || '').toLowerCase();
          if (themeVal.indexOf(th) === -1 && themeZh.indexOf(th) === -1 && nm.indexOf(th) === -1) return false;
        }
        return true;
      });
    }

    function sortRows(rows) {
      if (!sortKey || !sortDir) return rows;
      var col = columns.find(function(c){ return c.key === sortKey; });
      if (!col) return rows;
      var factor = sortDir === 'asc' ? 1 : -1;
      return rows.slice().sort(function(a, b) {
        var av = a[sortKey], bv = b[sortKey];
        // nulls last in both directions
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        // numeric if both are numbers
        var an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return factor * (an - bn);
        return factor * String(av).localeCompare(String(bv));
      });
    }

    function renderRows() {
      var t0 = performance.now();
      var rows = applyFilters(allRows);
      rows = sortRows(rows);

      var cols = orderedCols();
      var frag = document.createDocumentFragment();

      rows.forEach(function(row) {
        var tr = document.createElement('tr');

        // stage/zone accent class
        var stg = row.stage || row._stage || '';
        var zone = row.zone || '';
        if (stg === 'ENTRY') tr.classList.add('st-row-entry');
        else if (stg === 'RAN_LATE') tr.classList.add('st-row-ran');
        else if (stg === 'RIPENING') {
          if (zone === 'READY') tr.classList.add('st-row-ready');
          else if (zone === 'FALLING') tr.classList.add('st-row-falling');
          else tr.classList.add('st-row-basing');
        } else if (stg === 'KNIFE') tr.classList.add('st-row-falling');

        cols.forEach(function(col, idx) {
          var td = document.createElement('td');
          if (col.right) td.className = 'st-r';
          if (idx === 0) td.className = (td.className ? td.className + ' ' : '') + 'st-sticky-col';
          if (col.cls) td.className = (td.className ? td.className + ' ' : '') + col.cls;

          var val = row[col.key];
          var html;
          if (col.fmt) {
            html = col.fmt(val, row);
          } else if (val == null || val === '') {
            html = '<span class="st-muted">—</span>';
          } else {
            html = esc(String(val));
          }
          td.innerHTML = html;

          // row click (first col only — whole row is clickable)
          if (idx === 0 && cfg.linkPattern) {
            var link = cfg.linkPattern.replace('{ticker}', esc(row.ticker || ''));
            tr.style.cursor = 'pointer';
            tr.addEventListener('click', function(e) {
              if (!e.target.closest('a')) window.location.href = link;
            });
          }
          tr.appendChild(td);
        });
        frag.appendChild(tr);
      });

      tbody.innerHTML = '';
      tbody.appendChild(frag);

      var t1 = performance.now();
      // report perf to console (dev aid — removed in prod builds)
      if (global.__stDebug) console.log('StockTable render', rows.length, 'rows in', (t1-t0).toFixed(1), 'ms');

      // update count chips
      _updateCountChips(allRows, rows);
    }

    /* ── filter row builder ──────────────────────────────────────────────── */
    // <option> text is single-language (spans don't work inside <option>),
    // stored as data-en/data-zh and swapped in place on 'langchange'.

    function _optPair(name, value) {
      var m = optionLabels[name];
      var pair = m && m[value];
      if (pair) return [pair[0] || value, pair[1] || pair[0] || value];
      return [value, value];
    }

    function _buildFilterRow(rows, payload) {
      var zhNow = curLang() === 'zh';
      // Collect unique values
      var stages   = _uniq(rows.map(function(r){ return r.stage || r._stage || ''; }).filter(Boolean));
      var zones    = _uniq(rows.map(function(r){ return r.zone || ''; }).filter(Boolean));
      var tiers    = _uniq(rows.map(function(r){ return r.tier || ''; }).filter(Boolean));
      var sectors  = _uniq(rows.map(function(r){ return r.sector || ''; }).filter(Boolean)).sort();
      var capBkts  = ['large','mid','small'].filter(function(cb){
        return rows.some(function(r){ return (r.cap_bucket||'') === cb; }); });

      function sel(name, opts) {
        var title = FILTER_TITLES[name] || [name, name];
        var html = '<select class="st-filter-sel" data-filter="' + name + '" aria-label="' + esc(title[0]) + '">';
        html += '<option value="all" data-en="' + esc(title[0]) + '" data-zh="' + esc(title[1]) + '">' +
                esc(zhNow ? title[1] : title[0]) + '</option>';
        opts.forEach(function(o) {
          if (!o) return;
          var p = _optPair(name, o);
          html += '<option value="' + esc(o) + '" data-en="' + esc(p[0]) + '" data-zh="' + esc(p[1]) + '">' +
                  esc(zhNow ? p[1] : p[0]) + '</option>';
        });
        html += '</select>';
        return html;
      }

      var stageOpts = ['ENTRY','RAN_LATE','RIPENING','KNIFE'].filter(function(s){ return stages.indexOf(s) !== -1; });
      var zoneOpts  = ['READY','BASING','FALLING'].filter(function(z){ return zones.indexOf(z) !== -1; });
      var tierOpts  = ['PRIME','CONFIRMED','CONFIRMING','APPROACHING','FIRST SPARK']
                      .filter(function(t){ return tiers.indexOf(t) !== -1 || rows.some(function(r){ return (r.tier||'') === t; }); });

      var html = '<div class="st-filters">';
      if (stageOpts.length > 0) html += sel('stage', stageOpts);
      if (zoneOpts.length > 0) html += sel('zone', zoneOpts);
      var tierList = tierOpts.length > 0 ? tierOpts : tiers;
      if (tierList.length > 0) html += sel('tier', tierList);
      html += sel('sector', sectors);
      if (capBkts.length > 0) html += sel('capBucket', capBkts);
      html += '<input class="st-filter-txt" type="text" data-filter="theme" placeholder="' +
              esc(zhNow ? SEARCH_PH[1] : SEARCH_PH[0]) + '" style="min-width:120px">';
      html += '<label class="st-filter-chk"><input type="checkbox" data-filter="freshOnly"> ';
      html += bi('Fresh only (≤2d)', '仅新信号(≤2天)') + '</label>';

      // system-order reset (shown when user has sorted)
      html += '<button class="st-reset-btn" id="st-reset-order" style="display:none">';
      html += bi('Reset order', '恢复默认排序') + '</button>';

      // column chooser toggle
      html += '<button class="st-col-btn" id="st-col-btn">';
      html += bi('Columns', '列设置') + ' ☰</button>';

      html += '</div>';
      return html;
    }

    // Swap <option> text + search placeholder to the active language in place
    // (values, selection and all bound listeners untouched).
    function _relabelFilters() {
      var zhNow = curLang() === 'zh';
      frow.querySelectorAll('option[data-en]').forEach(function(o) {
        o.textContent = zhNow ? (o.getAttribute('data-zh') || o.getAttribute('data-en'))
                              : o.getAttribute('data-en');
      });
      var txt = frow.querySelector('.st-filter-txt');
      if (txt) txt.placeholder = zhNow ? SEARCH_PH[1] : SEARCH_PH[0];
    }
    document.addEventListener('langchange', _relabelFilters);

    function _updateCountChips(allR, filteredR) {
      var counts = { ENTRY:0, RAN_LATE:0, RIPENING:0, KNIFE:0 };
      filteredR.forEach(function(r){
        var s = r.stage || r._stage || '';
        var z = r.zone || '';
        if (s === 'RIPENING' && z === 'FALLING') { counts.KNIFE++; }
        else if (counts[s] !== undefined) counts[s]++;
      });
      var chipEl = document.getElementById('st-count-chips');
      if (chipEl) {
        var html = '';
        if (counts.ENTRY > 0)    html += '<span class="st-chip st-chip-entry">' + bi('ENTRY', '入场') + ' ' + counts.ENTRY + '</span>';
        if (counts.RAN_LATE > 0) html += '<span class="st-chip st-chip-ran">' + bi('RAN / LATE', '信号已过') + ' ' + counts.RAN_LATE + '</span>';
        if (counts.RIPENING > 0) html += '<span class="st-chip st-chip-rip">' + bi('RIPENING', '蓄势中') + ' ' + counts.RIPENING + '</span>';
        if (counts.KNIFE > 0)    html += '<span class="st-chip st-chip-knife">' + bi('KNIFE', '下跌中') + ' ' + counts.KNIFE + '</span>';
        chipEl.innerHTML = html;
      }
      // reset-order button visibility
      var resetBtn = document.getElementById('st-reset-order');
      if (resetBtn) resetBtn.style.display = (sortKey ? '' : 'none');
    }

    /* ── filter event binding ────────────────────────────────────────────── */
    function bindFilters() {
      frow.querySelectorAll('.st-filter-sel').forEach(function(sel) {
        sel.addEventListener('change', function() {
          filters[sel.getAttribute('data-filter')] = sel.value;
          renderRows();
        });
      });
      var txtEl = frow.querySelector('.st-filter-txt');
      if (txtEl) {
        txtEl.addEventListener('input', function() {
          filters.theme = txtEl.value.trim();
          renderRows();
        });
      }
      var chkEl = frow.querySelector('input[data-filter="freshOnly"]');
      if (chkEl) {
        chkEl.addEventListener('change', function() {
          filters.freshOnly = chkEl.checked;
          renderRows();
        });
      }
      // reset order button
      frow.addEventListener('click', function(e) {
        if (e.target.closest('#st-reset-order')) {
          sortKey = null; sortDir = null;
          renderHeader(); renderRows();
        }
        if (e.target.closest('#st-col-btn')) {
          chooserWrap.classList.toggle('st-chooser-hidden');
        }
      });
    }

    /* ── column chooser ────────────────────────────────────────────────── */
    function _buildChooser(cols, order, visible, mkt) {
      var html = '<div class="st-chooser">';
      html += '<div class="st-chooser-hdr">' +
              bi('Column chooser', '列选择') +
              '<span class="st-chooser-note">' + bi('saved to this browser', '保存在本浏览器') + '</span>' +
              '<button class="st-chooser-close" id="st-chooser-close">×</button>' +
              '</div>';
      html += '<div class="st-chooser-list" id="st-chooser-list">';
      order.forEach(function(k, idx) {
        var col = cols.find(function(c){ return c.key === k; });
        if (!col) return;
        var chk = visible.indexOf(k) !== -1;
        // carry the column's display class so columns force-hidden on mobile
        // (.st-hide-sm) also hide their chooser checkbox there — no dead toggles
        html += '<div class="st-chooser-row' + (col.cls ? ' ' + esc(col.cls) : '') + '" draggable="true" data-key="' + esc(k) + '">';
        html += '<span class="st-drag-handle">☰</span>';
        html += '<label><input type="checkbox" class="st-col-chk" data-key="' + esc(k) + '"' +
                (chk ? ' checked' : '') + '> ' +
                bi(col.labelEn, col.labelZh) + '</label>';
        html += '</div>';
      });
      html += '</div>';
      html += '<div class="st-chooser-footer">';
      html += '<button class="st-chooser-reset" id="st-chooser-reset">' + bi('Reset to default', '恢复默认') + '</button>';
      html += '</div>';
      html += '</div>';
      return html;
    }

    function bindChooser() {
      chooserWrap.addEventListener('change', function(e) {
        if (e.target.classList.contains('st-col-chk')) {
          var k = e.target.getAttribute('data-key');
          if (e.target.checked) {
            if (visibleCols.indexOf(k) === -1) visibleCols.push(k);
          } else {
            visibleCols = visibleCols.filter(function(x){ return x !== k; });
          }
          writeLsJson(lsCols, visibleCols);
          renderHeader(); renderRows();
        }
      });
      // close button
      chooserWrap.addEventListener('click', function(e) {
        if (e.target.id === 'st-chooser-close') {
          chooserWrap.classList.add('st-chooser-hidden');
        }
        if (e.target.id === 'st-chooser-reset') {
          visibleCols = defaultVisible.slice();
          colOrder = defaultOrder.slice();
          writeLsJson(lsCols, visibleCols);
          writeLsJson(lsOrder, colOrder);
          _rebuildChooser();
          renderHeader(); renderRows();
        }
      });
      // drag-to-reorder
      _bindDrag(chooserWrap.querySelector('#st-chooser-list'));
    }

    function _rebuildChooser() {
      chooserWrap.innerHTML = _buildChooser(columns, colOrder, visibleCols, market);
      bindChooser();
    }

    function _bindDrag(list) {
      if (!list) return;
      var dragged = null;
      list.addEventListener('dragstart', function(e) {
        dragged = e.target.closest('[data-key]');
        if (dragged) { e.dataTransfer.effectAllowed = 'move'; dragged.classList.add('st-dragging'); }
      });
      list.addEventListener('dragend', function() {
        if (dragged) dragged.classList.remove('st-dragging');
        dragged = null;
      });
      list.addEventListener('dragover', function(e) {
        e.preventDefault(); e.dataTransfer.dropEffect = 'move';
        var target = e.target.closest('[data-key]');
        if (target && dragged && target !== dragged) {
          var kids = Array.from(list.children);
          var di = kids.indexOf(dragged), ti = kids.indexOf(target);
          if (di !== -1 && ti !== -1) {
            if (di < ti) list.insertBefore(dragged, target.nextSibling);
            else list.insertBefore(dragged, target);
          }
        }
      });
      list.addEventListener('drop', function(e) {
        e.preventDefault();
        // read new order from DOM
        var newOrder = Array.from(list.querySelectorAll('[data-key]'))
                           .map(function(el){ return el.getAttribute('data-key'); });
        // merge: keep keys in new order, append any missing
        colOrder = newOrder.filter(function(k){ return colOrder.indexOf(k) !== -1; });
        defaultOrder.forEach(function(k){ if (colOrder.indexOf(k) === -1) colOrder.push(k); });
        writeLsJson(lsOrder, colOrder);
        renderHeader(); renderRows();
      });
    }

    /* ── utility ──────────────────────────────────────────────────────── */
    function _uniq(arr) {
      var seen = {};
      return arr.filter(function(v){ if (seen[v]) return false; seen[v] = true; return true; });
    }
  }

  /* ── exports ─────────────────────────────────────────────────────────── */
  global.StockTable = { init: init, _macdGlyph: macdGlyph, _fmtPct: fmtPct, _fmtNum: fmtNum, _bi: bi, _esc: esc };

})(typeof window !== 'undefined' ? window : this);

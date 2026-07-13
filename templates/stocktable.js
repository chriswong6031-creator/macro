/**
 * stocktable.js v3 — market-generic dense-table module for standout boards.
 *
 * v3 changes: custom filter toolbar (.stf-bar) and column chooser (.stf-chooser)
 * replace all native <select> elements and plain checkboxes. CSS is injected once
 * into document.head via <style id="stf-css">. Component classes use the .stf-*
 * namespace. Dropdowns are fully keyboard-navigable (Arrow/Enter/Escape/Home/End)
 * with ARIA listbox semantics. Fresh-only chip auto-hides when no row has
 * days_since_signal data. Lane filter added for US-market bottoming/continuation lanes.
 *
 * Usage: include this file, then call StockTable.init(config) where config = {
 *   dataId:     'stocktable-data',    // id of <script type="application/json"> element
 *   containerId:'stocktable-wrap',    // id of mount container element
 *   market:     'cn',                 // localStorage namespace key (e.g. 'cn', 'us', 'hk')
 *   linkPattern: 'china_lookup.html#{ticker}', // row link template
 *   columns:    [...],                // column schema array (see below)
 *   stageFilter: true,                // show stage filter row
 *   searchPlaceholder: ['Search…','搜索…'], // override search input placeholder
 *   optionLabels: { filterName: { VALUE: [en, zh] } }, // display labels for filter values
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
 * No external dependencies. Bilingual via l-en/l-zh spans convention.
 */
(function (global) {
  'use strict';

  /* ── constants ───────────────────────────────────────────────────────── */
  // v2 prefix: v1 persisted 15-column defaults that overflowed the viewport and
  // the chooser was unreachable, so stale v1 state is deliberately abandoned.
  var LS_PREFIX = 'mdx_stocktable2_';
  var FRESH_DAYS = 2;  // days_since_signal <= 2 → show NEW dot

  // Static SVG fragments for the toolbar + chooser. Module scope on purpose:
  // init() consumes them during the synchronous skeleton build, so any
  // function-scoped `var` declared later in init() would be hoisted-undefined
  // at that point (the exact bug class fixed after the v3 rewrite).
  var SVG_SEARCH  = '<svg class="stf-ico-search" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="7" cy="7" r="4.6"/><path d="m10.6 10.6 3 3"/></svg>';
  var SVG_CHEV    = '<svg class="stf-chev" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="m4 6 4 4 4-4"/></svg>';
  var SVG_TICK    = '<svg class="stf-tick" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.4"><path d="m3 8.5 3.2 3L13 5"/></svg>';
  var SVG_TICK_LG = '<svg class="stf-tick" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.6"><path d="m3 8.5 3.2 3L13 5"/></svg>';
  var SVG_COLS    = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="1.5" y="2.5" width="13" height="11" rx="2"/><path d="M6.2 2.5v11M10.8 2.5v11"/></svg>';
  var SVG_GRIP = '<svg class="stf-grip" viewBox="0 0 10 14" fill="currentColor">' +
    '<circle cx="2.5" cy="2" r="1.3"/><circle cx="7.5" cy="2" r="1.3"/>' +
    '<circle cx="2.5" cy="7" r="1.3"/><circle cx="7.5" cy="7" r="1.3"/>' +
    '<circle cx="2.5" cy="12" r="1.3"/><circle cx="7.5" cy="12" r="1.3"/></svg>';
  var SVG_CHK = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="m3 8.5 3.2 3L13 5"/></svg>';

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

  /* ── filter label map ────────────────────────────────────────────────── */
  var FILTER_LABELS = {
    stage:     ['Stage',  '阶段'],
    zone:      ['Zone',   '区域'],
    tier:      ['Tier',   '级别'],
    sector:    ['Sector', '板块'],
    capBucket: ['Size',   '市值'],
    lane:      ['Lane',   '通道']
  };

  /* ── CSS injection ───────────────────────────────────────────────────── */
  function _injectCss() {
    if (document.getElementById('stf-css')) return;
    var style = document.createElement('style');
    style.id = 'stf-css';
    style.textContent = [
      /* toolbar container */
      '.stf-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:10px 0 12px;padding:10px;background:color-mix(in srgb, var(--panel2) 46%, transparent);border:1px solid var(--line);border-radius:12px;}',
      /* search box */
      '.stf-search{position:relative;flex:1 1 190px;min-width:150px;max-width:290px;}',
      '.stf-search svg.stf-ico-search{position:absolute;left:10px;top:50%;transform:translateY(-50%);width:13px;height:13px;color:var(--muted);pointer-events:none;}',
      '.stf-search input{width:100%;box-sizing:border-box;height:32px;padding:0 28px 0 30px;font:inherit;font-size:12.5px;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:8px;outline:none;transition:border-color .15s, box-shadow .15s;}',
      '.stf-search input::placeholder{color:var(--muted);opacity:.75;}',
      '.stf-search input:hover{border-color:color-mix(in srgb, var(--muted) 40%, var(--line));}',
      '.stf-search input:focus{border-color:var(--link);box-shadow:0 0 0 3px color-mix(in srgb, var(--link) 16%, transparent);}',
      '.stf-search .stf-clear{position:absolute;right:6px;top:50%;transform:translateY(-50%);display:none;align-items:center;justify-content:center;width:18px;height:18px;border:none;border-radius:50%;background:color-mix(in srgb, var(--muted) 18%, transparent);color:var(--muted);font-size:11px;line-height:1;cursor:pointer;padding:0;}',
      '.stf-search .stf-clear:hover{background:color-mix(in srgb, var(--muted) 30%, transparent);color:var(--text);}',
      '.stf-search.stf-has-value .stf-clear{display:inline-flex;}',
      /* dropdown trigger */
      '.stf-dd{position:relative;}',
      '.stf-dd-btn{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 9px 0 11px;font:inherit;font-size:12.5px;cursor:pointer;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;transition:border-color .15s, background .15s, box-shadow .15s;}',
      '.stf-dd-btn:hover{border-color:color-mix(in srgb, var(--muted) 40%, var(--line));background:color-mix(in srgb, var(--panel2) 60%, var(--panel));}',
      '.stf-dd-lab{color:var(--muted);font-weight:500;font-size:12px;}',
      '.stf-dd-val{font-weight:650;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}',
      '.stf-dd-btn svg.stf-chev{width:11px;height:11px;color:var(--muted);flex:none;transition:transform .18s cubic-bezier(.16,1,.3,1);}',
      '.stf-dd.stf-open .stf-dd-btn{border-color:var(--link);box-shadow:0 0 0 3px color-mix(in srgb, var(--link) 16%, transparent);}',
      '.stf-dd.stf-open svg.stf-chev{transform:rotate(180deg);}',
      '.stf-dd.stf-active .stf-dd-btn{border-color:color-mix(in srgb, var(--link) 45%, var(--line));background:color-mix(in srgb, var(--link) 9%, var(--panel));}',
      '.stf-dd.stf-active .stf-dd-val{color:var(--link);}',
      /* dropdown menu (glass) */
      '.stf-menu{position:absolute;top:calc(100% + 6px);left:0;z-index:60;min-width:210px;max-height:320px;overflow-y:auto;padding:5px;background:var(--glass-bg, var(--panel));-webkit-backdrop-filter:var(--glass-blur, none);backdrop-filter:var(--glass-blur, none);border:1px solid var(--glass-brd, var(--line));border-radius:11px;box-shadow:var(--glass-shadow, 0 12px 32px rgba(0,0,0,.3));animation:stf-pop .14s cubic-bezier(.16,1,.3,1);transform-origin:top left;}',
      '.stf-menu.stf-menu-right{left:auto;right:0;transform-origin:top right;}',
      '@keyframes stf-pop{from{opacity:0;transform:translateY(-5px) scale(.985);}to{opacity:1;transform:none;}}',
      '.stf-opt{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:7px;font-size:12.5px;color:var(--text);cursor:pointer;user-select:none;}',
      '.stf-opt:hover,.stf-opt.stf-kb{background:color-mix(in srgb, var(--link) 10%, transparent);}',
      '.stf-opt .stf-tick{width:14px;height:14px;flex:none;color:var(--link);visibility:hidden;}',
      '.stf-opt[aria-selected="true"]{font-weight:650;}',
      '.stf-opt[aria-selected="true"] .stf-tick{visibility:visible;}',
      '.stf-opt .stf-olab{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}',
      '.stf-cnt{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;}',
      '.stf-sep{height:1px;background:var(--line);margin:4px 8px;}',
      /* toggle chip (Fresh only) */
      '.stf-chipbtn{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 12px;font:inherit;font-size:12.5px;font-weight:550;cursor:pointer;background:var(--panel);color:var(--muted);border:1px solid var(--line);border-radius:999px;transition:border-color .15s, background .15s, color .15s;}',
      '.stf-chipbtn:hover{border-color:color-mix(in srgb, var(--muted) 40%, var(--line));}',
      '.stf-chipbtn svg.stf-tick{width:12px;height:12px;display:none;}',
      '.stf-chipbtn[aria-pressed="true"]{color:var(--up);background:color-mix(in srgb, var(--up) 11%, var(--panel));border-color:color-mix(in srgb, var(--up) 42%, var(--line));font-weight:650;}',
      '.stf-chipbtn[aria-pressed="true"] svg.stf-tick{display:block;}',
      /* right cluster */
      '.stf-spacer{flex:1 0 0;}',
      '.stf-ghost{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 11px;font:inherit;font-size:12px;font-weight:600;cursor:pointer;background:transparent;color:var(--muted);border:1px dashed color-mix(in srgb, var(--muted) 40%, var(--line));border-radius:8px;transition:color .15s, border-color .15s;}',
      '.stf-ghost:hover{color:var(--text);border-color:var(--muted);}',
      '.stf-colbtn{display:inline-flex;align-items:center;gap:7px;height:32px;padding:0 11px;font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;transition:border-color .15s, background .15s, box-shadow .15s;}',
      '.stf-colbtn:hover{border-color:color-mix(in srgb, var(--muted) 40%, var(--line));background:color-mix(in srgb, var(--panel2) 60%, var(--panel));}',
      '.stf-colbtn svg{width:13px;height:13px;color:var(--muted);}',
      '.stf-colbtn .stf-badge{font-size:10.5px;font-weight:700;color:var(--muted);background:color-mix(in srgb, var(--muted) 14%, transparent);padding:1px 7px;border-radius:999px;font-variant-numeric:tabular-nums;}',
      '.stf-colbtn.stf-open-btn{border-color:var(--link);box-shadow:0 0 0 3px color-mix(in srgb, var(--link) 16%, transparent);}',
      /* column chooser panel (glass) */
      '.st-chooser-wrap{position:relative;}',
      '.st-chooser-hidden .stf-chooser{display:none;}',
      '.stf-chooser{position:absolute;top:6px;right:0;z-index:60;width:270px;background:var(--glass-bg, var(--panel));-webkit-backdrop-filter:var(--glass-blur, none);backdrop-filter:var(--glass-blur, none);border:1px solid var(--glass-brd, var(--line));border-radius:12px;box-shadow:var(--glass-shadow, 0 12px 32px rgba(0,0,0,.3));overflow:hidden;animation:stf-pop .14s cubic-bezier(.16,1,.3,1);transform-origin:top right;}',
      '.stf-ch-hdr{padding:11px 13px 9px;border-bottom:1px solid var(--line);}',
      '.stf-ch-title{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;}',
      '.stf-ch-close{margin-left:auto;width:20px;height:20px;display:inline-flex;align-items:center;justify-content:center;border:none;border-radius:6px;background:transparent;cursor:pointer;color:var(--muted);font-size:14px;line-height:1;padding:0;}',
      '.stf-ch-close:hover{background:color-mix(in srgb, var(--muted) 15%, transparent);color:var(--text);}',
      '.stf-ch-sub{font-size:11px;color:var(--muted);margin-top:3px;}',
      '.stf-ch-list{max-height:330px;overflow-y:auto;padding:6px;}',
      '.stf-ch-list::-webkit-scrollbar{width:8px;}',
      '.stf-ch-list::-webkit-scrollbar-thumb{background:color-mix(in srgb, var(--muted) 28%, transparent);border-radius:8px;border:2px solid transparent;background-clip:content-box;}',
      '.stf-ch-row{display:flex;align-items:center;gap:9px;padding:7px 8px;border-radius:8px;font-size:12.5px;cursor:grab;user-select:none;}',
      '.stf-ch-row:hover{background:color-mix(in srgb, var(--link) 8%, transparent);}',
      '.stf-ch-row.stf-dragging{opacity:.9;background:var(--panel);box-shadow:0 8px 22px rgba(0,0,0,.28);cursor:grabbing;}',
      '.stf-grip{color:color-mix(in srgb, var(--muted) 65%, transparent);flex:none;width:10px;height:14px;}',
      '.stf-ch-row label{display:flex;align-items:center;gap:9px;flex:1;cursor:inherit;min-width:0;}',
      '.stf-ch-row .stf-collab{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}',
      /* custom checkbox */
      '.stf-cb{position:relative;width:16px;height:16px;flex:none;}',
      '.stf-cb input{position:absolute;inset:0;opacity:0;margin:0;cursor:pointer;}',
      '.stf-cb .stf-box{position:absolute;inset:0;border-radius:5px;border:1.5px solid color-mix(in srgb, var(--muted) 55%, var(--line));background:var(--panel);transition:background .13s, border-color .13s;display:flex;align-items:center;justify-content:center;pointer-events:none;}',
      '.stf-cb .stf-box svg{width:10px;height:10px;color:#fff;stroke-width:3;transform:scale(0);transition:transform .13s cubic-bezier(.2,1.4,.5,1);}',
      '.stf-cb input:checked + .stf-box{background:var(--link);border-color:var(--link);}',
      '.stf-cb input:checked + .stf-box svg{transform:scale(1);}',
      '.stf-cb input:focus-visible + .stf-box{box-shadow:0 0 0 3px color-mix(in srgb, var(--link) 20%, transparent);}',
      '.stf-ch-foot{display:flex;align-items:center;padding:9px 13px;border-top:1px solid var(--line);}',
      '.stf-ch-reset{font:inherit;font-size:11.5px;font-weight:600;cursor:pointer;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:7px;padding:5px 10px;}',
      '.stf-ch-reset:hover{color:var(--text);border-color:var(--muted);}',
      '.stf-ch-note{margin-left:auto;font-size:10.5px;color:var(--muted);}',
      /* Feature 2: ticker anchor in table — inherits row color, dotted underline on hover */
      '.stf-tkr{color:inherit;text-decoration:none;border-bottom:1px dotted transparent;}',
      '.stf-tkr:hover{color:var(--link);border-bottom-color:var(--link);}',
      /* Feature 1: column resize — fixed-layout override (scoped to avoid .st-table host CSS) */
      'table.st-fixed-layout{table-layout:fixed;}',
      /* Feature 1: resize handle on th — th needs position:relative for handle */
      'thead th{position:relative;}',
      '.stf-rsz{position:absolute;right:-4px;top:0;width:8px;height:100%;cursor:col-resize;z-index:3;display:flex;align-items:center;justify-content:center;}',
      '.stf-rsz::after{content:"";display:block;width:2px;height:60%;background:var(--link);border-radius:1px;opacity:0;transition:opacity .15s;}',
      '.stf-rsz:hover::after,.stf-rsz.stf-rsz-active::after{opacity:1;}',
      '@media (pointer:coarse){.stf-rsz{width:14px;right:-7px;}}',
      /* focus rings */
      '.stf-dd-btn:focus-visible,.stf-chipbtn:focus-visible,.stf-colbtn:focus-visible,.stf-ghost:focus-visible,.stf-ch-reset:focus-visible,.stf-ch-close:focus-visible,.stf-clear:focus-visible{outline:2px solid var(--link);outline-offset:2px;}',
      /* reduced motion */
      '@media (prefers-reduced-motion: reduce){.stf-menu,.stf-chooser{animation:none;}.stf-dd-btn svg.stf-chev,.stf-cb .stf-box,.stf-cb .stf-box svg{transition:none;}}',
      /* mobile */
      '@media (max-width:680px){.stf-bar{padding:8px;gap:6px;}.stf-search{flex-basis:100%;max-width:none;}.stf-dd-btn,.stf-chipbtn,.stf-colbtn,.stf-ghost{height:30px;font-size:12px;}.stf-menu{min-width:180px;}.stf-ch-row.st-hide-sm{display:none;}}',
      /* mobile dropdown label/value toggle */
      '.stf-dd:not(.stf-active) .stf-dd-val{display:none;} .stf-dd.stf-active .stf-dd-lab{display:none;}'
    ].join('\n');
    document.head.appendChild(style);
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
    var lsWidths = LS_PREFIX + market + '_widths';     // Feature 1: {colKey: px}

    // Feature 1: colgroup element (shared reference; rebuilt by _syncColgroup).
    var colgroup = null;
    // Feature 1: stored column widths from localStorage (or empty object).
    var colWidths = readLsJson(lsWidths, {});
    // Feature 1: mobile breakpoint — disable custom widths at ≤680px (display:none
    // on hidden cells combined with table-layout:fixed misaligns by column index).
    var _mq680 = window.matchMedia('(max-width:680px)');
    var _isMobile = _mq680.matches;
    function _onMqChange(e) {
      _isMobile = e.matches;
      if (_isMobile) {
        // remove fixed layout so mobile uses auto
        table.classList.remove('st-fixed-layout');
        if (colgroup) { colgroup.parentNode && table.removeChild(colgroup); colgroup = null; }
      } else {
        // re-apply stored widths if any exist
        _syncColgroup();
      }
    }
    // older MediaQueryList implementations expose addListener only
    if (_mq680.addEventListener) _mq680.addEventListener('change', _onMqChange);
    else if (_mq680.addListener) _mq680.addListener(_onMqChange);

    _injectCss();

    var allRows = (payload.rows || []).slice();  // master copy in system order
    var columns = cfg.columns || [];             // column schema

    // Feature 3: rankFn — compute _rank for every row at parse time.
    // cfg.rankFn(row) -> number|null; errors per-row are caught and yield null.
    if (typeof cfg.rankFn === 'function') {
      allRows.forEach(function(row) {
        try { row._rank = cfg.rankFn(row); }
        catch(e) { row._rank = null; }
      });
    }

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
                    theme: '', capBucket: 'all', lane: 'all', freshOnly: false };

    // Per-value display labels for filter options (cfg.optionLabels =
    // { filterName: { VALUE: [en, zh] } }), raw value as fallback. Declared
    // BEFORE the skeleton build below — _buildFilterRow reads these at call time.
    var optionLabels = cfg.optionLabels || {};
    var FILTER_TITLES = { stage: ['All stages','全部阶段'], zone: ['All zones','全部区域'],
                          tier: ['All tiers','全部级别'], sector: ['All sectors','全部板块'],
                          capBucket: ['All sizes','全部市值'], lane: ['All lanes','全部通道'] };
    var SEARCH_PH = cfg.searchPlaceholder || ['Search name or theme…','搜索名称或主题…'];

    /* ── sort state ───────────────────────────────────────────────────── */
    // Feature 3: if rankFn is provided, initial sort is _rank desc.
    var sortKey   = (typeof cfg.rankFn === 'function') ? '_rank' : null;
    var sortDir   = (typeof cfg.rankFn === 'function') ? 'desc'  : null;

    /* ── build skeleton ───────────────────────────────────────────────── */
    container.innerHTML = '';
    container.style.position = 'relative';

    // Live dropdown DOM references, keyed by filter name. Declared BEFORE the
    // skeleton build below — _buildFilterRow populates it at call time.
    var _ddNodes = {};

    // ── filter row ──
    var frow = document.createElement('div');
    frow.className = 'st-frow';
    container.appendChild(frow);
    // _buildFilterRow populates frow directly and wires all event handlers

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

    // ── build filter toolbar (also wires all filter events) ──
    _buildFilterRow(allRows, payload);

    // ── render header ──
    renderHeader();

    // ── render rows ──
    renderRows();

    // ── bind chooser events ──
    bindChooser();

    /* ── render functions ──────────────────────────────────────────────── */

    function orderedCols() {
      return colOrder
        .map(function(k){ return columns.find(function(c){ return c.key === k; }); })
        .filter(function(c){ return c && visibleCols.indexOf(c.key) !== -1; });
    }

    /* ── Feature 1: colgroup width management ─────────────────────────── */
    // _syncColgroup: rebuild or update the <colgroup> based on current colWidths.
    // Called after renderHeader (when th elements exist for snapshot) and after
    // column chooser changes. Must run after the DOM is updated.
    function _syncColgroup() {
      if (_isMobile) return;
      var cols = orderedCols();
      var hasAny = cols.some(function(c){ return colWidths[c.key] != null; });
      if (!hasAny) {
        // No custom widths — remove fixed layout and colgroup entirely.
        table.classList.remove('st-fixed-layout');
        if (colgroup && colgroup.parentNode) table.removeChild(colgroup);
        colgroup = null;
        return;
      }
      // Snapshot current th widths for columns without a stored width, so the
      // table doesn't jump when we switch to fixed layout.
      var ths = thead.querySelectorAll('tr:first-child th');
      cols.forEach(function(c, i) {
        if (colWidths[c.key] == null && ths[i]) {
          colWidths[c.key] = ths[i].offsetWidth || ths[i].getBoundingClientRect().width;
        }
      });
      // Build or rebuild colgroup.
      if (!colgroup) {
        colgroup = document.createElement('colgroup');
        table.insertBefore(colgroup, table.firstChild);
      }
      colgroup.innerHTML = '';
      cols.forEach(function(c) {
        var col = document.createElement('col');
        var w = colWidths[c.key];
        if (w != null) col.style.width = w + 'px';
        colgroup.appendChild(col);
      });
      table.classList.add('st-fixed-layout');
    }

    // _applyColWidth: set a single column's width during a drag.
    function _applyColWidth(colKey, px) {
      if (_isMobile) return;
      px = Math.max(36, px);
      colWidths[colKey] = px;
      // Ensure we're in fixed layout with a colgroup.
      if (!colgroup || !colgroup.parentNode) {
        // Trigger a full snapshot + build.
        _syncColgroup();
      }
      // Update the specific <col> element.
      var cols = orderedCols();
      var idx = -1;
      for (var i = 0; i < cols.length; i++) { if (cols[i].key === colKey) { idx = i; break; } }
      if (colgroup && idx !== -1) {
        var colEls = colgroup.querySelectorAll('col');
        if (colEls[idx]) colEls[idx].style.width = px + 'px';
      }
      writeLsJson(lsWidths, colWidths);
    }

    // _clearColWidth: remove a column's stored width; if none remain, exit fixed layout.
    function _clearColWidth(colKey) {
      delete colWidths[colKey];
      writeLsJson(lsWidths, colWidths);
      _syncColgroup();
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

        // Feature 1: sort click handler — dragged flag prevents a resize drag
        // from triggering a sort cycle (the flag is set by the resize handler).
        if (col.sortable !== false) {
          th.addEventListener('click', function(e) {
            if (th._rszDragged) { th._rszDragged = false; return; }
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

        // Feature 1: resize handle.
        var handle = document.createElement('div');
        handle.className = 'stf-rsz';
        handle.setAttribute('aria-hidden', 'true');
        th.appendChild(handle);

        // Pointer events: capture pointer to receive moves even outside the element.
        // Drag liveness is tracked with an own flag (not hasPointerCapture): capture
        // can be unavailable (synthetic/emulated pointers throw NotFoundError) and the
        // drag must still work — capture only widens the move-tracking area.
        var startX = 0, startW = 0, dragging = false;
        handle.addEventListener('pointerdown', function(e) {
          if (_isMobile) return;
          e.stopPropagation(); // prevent sort
          e.preventDefault();
          try { handle.setPointerCapture(e.pointerId); } catch (err) {}
          handle.classList.add('stf-rsz-active');
          startX = e.clientX;
          // Snapshot current width: use colWidths if set, else th.offsetWidth.
          startW = colWidths[col.key] != null ? colWidths[col.key] : th.offsetWidth;
          dragging = true;
          th._rszDragged = false;
        });
        handle.addEventListener('pointermove', function(e) {
          if (!dragging) return;
          var delta = e.clientX - startX;
          if (Math.abs(delta) > 3) th._rszDragged = true;
          _applyColWidth(col.key, startW + delta);
        });
        handle.addEventListener('pointerup', function(e) {
          dragging = false;
          handle.classList.remove('stf-rsz-active');
          try { handle.releasePointerCapture(e.pointerId); } catch (err) {}
        });
        handle.addEventListener('pointercancel', function(e) {
          dragging = false;
          handle.classList.remove('stf-rsz-active');
        });
        // A zero-movement click on the handle must not bubble into the th sort cycle.
        handle.addEventListener('click', function(e) { e.stopPropagation(); });
        // Double-click: clear this column's stored width.
        handle.addEventListener('dblclick', function(e) {
          e.stopPropagation();
          _clearColWidth(col.key);
        });

        tr.appendChild(th);
      });
      thead.appendChild(tr);
      // Feature 1: (re)apply colgroup after header DOM is settled.
      _syncColgroup();
    }

    function applyFilters(rows) {
      return rows.filter(function(r) {
        if (filters.stage !== 'all' && (r.stage || 'ALL') !== filters.stage) return false;
        if (filters.zone !== 'all' && (r.zone || '') !== filters.zone) return false;
        if (filters.tier !== 'all' && (r.tier || '') !== filters.tier) return false;
        if (filters.sector !== 'all' && (r.sector || '') !== filters.sector) return false;
        if (filters.capBucket !== 'all' && (r.cap_bucket || 'unknown') !== filters.capBucket) return false;
        if (filters.lane !== 'all' && (r.lane || '') !== filters.lane) return false;
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
      // Feature 3: allow sorting by raw row fields (e.g. _rank) even when no
      // column schema entry exists — col lookup failure no longer bails out.
      var factor = sortDir === 'asc' ? 1 : -1;
      return rows.slice().sort(function(a, b) {
        var av = a[sortKey], bv = b[sortKey];
        // nulls/undefined sort LAST regardless of direction
        var anull = (av == null), bnull = (bv == null);
        if (anull && bnull) return 0;
        if (anull) return 1;
        if (bnull) return -1;
        // numeric if both parse
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

          // Feature 2: wrap ticker column content in <a class="stf-tkr"> so
          // theme.js Terminal capture-phase intercept applies naturally.
          if (col.key === 'ticker' && cfg.linkPattern) {
            var tkrLink = cfg.linkPattern.replace('{ticker}', esc(row.ticker || ''));
            html = '<a class="stf-tkr" href="' + tkrLink + '">' + html + '</a>';
          }
          td.innerHTML = html;

          // row click (first col only — whole row is clickable)
          if (idx === 0 && cfg.linkPattern) {
            var link = cfg.linkPattern.replace('{ticker}', esc(row.ticker || ''));
            tr.style.cursor = 'pointer';
            tr.addEventListener('click', function(e) {
              // Feature 2: let .stf-tkr anchor and modified clicks pass through
              // to the browser / theme.js Terminal intercept naturally.
              if (e.target.closest('a')) return;
              var T = window.MDXTerminal;
              window.location.href = (T && T.on && T.on()) ? T.url(row.ticker || '') : link;
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

    // Prettify raw slug when no optionLabels entry: capitalize + underscores→spaces.
    function _prettify(s) {
      return String(s).replace(/_/g, ' ').replace(/^./, function(c){ return c.toUpperCase(); });
    }

    // Return [en, zh] display pair for a filter option value.
    function _optPair(name, value) {
      var m = optionLabels[name];
      var pair = m && m[value];
      if (pair) return [pair[0] || _prettify(value), pair[1] || pair[0] || _prettify(value)];
      var p = _prettify(value);
      return [p, p];
    }

    // Build per-filter value counts from allRows (used in dropdown menus).
    function _buildCounts(rows) {
      var counts = {};
      rows.forEach(function(r) {
        function inc(name, val) {
          if (!counts[name]) counts[name] = {};
          counts[name][val] = (counts[name][val] || 0) + 1;
        }
        inc('stage',     r.stage || r._stage || '');
        inc('zone',      r.zone || '');
        inc('tier',      r.tier || '');
        inc('sector',    r.sector || '');
        inc('capBucket', r.cap_bucket || 'unknown');
        inc('lane',      r.lane || '');
      });
      return counts;
    }

    function _buildFilterRow(rows, payload) {
      // Collect unique values
      var stages   = _uniq(rows.map(function(r){ return r.stage || r._stage || ''; }).filter(Boolean));
      var zones    = _uniq(rows.map(function(r){ return r.zone || ''; }).filter(Boolean));
      var tiers    = _uniq(rows.map(function(r){ return r.tier || ''; }).filter(Boolean));
      var sectors  = _uniq(rows.map(function(r){ return r.sector || ''; }).filter(Boolean)).sort();
      var capBkts  = ['large','mid','small'].filter(function(cb){
        return rows.some(function(r){ return (r.cap_bucket||'') === cb; }); });
      var lanes    = _uniq(rows.map(function(r){ return r.lane || ''; }).filter(Boolean));

      var stageOpts = ['ENTRY','RAN_LATE','RIPENING','KNIFE'].filter(function(s){ return stages.indexOf(s) !== -1; });
      var zoneOpts  = ['READY','BASING','FALLING'].filter(function(z){ return zones.indexOf(z) !== -1; });
      var tierOpts  = ['PRIME','CONFIRMED','CONFIRMING','APPROACHING','FIRST SPARK']
                      .filter(function(t){ return tiers.indexOf(t) !== -1; });
      var tierList  = tierOpts.length > 0 ? tierOpts : tiers;

      var valueCounts = _buildCounts(rows);
      var hasFresh = rows.some(function(r){ return r.days_since_signal != null; });

      // Build visible badge: N visible / M total cols
      var visN = visibleCols.filter(function(k){ return columns.some(function(c){ return c.key === k; }); }).length;
      var colM = columns.length;

      // toolbar root
      var bar = document.createElement('div');
      bar.className = 'stf-bar';

      // ── search ──
      var searchSpan = document.createElement('span');
      searchSpan.className = 'stf-search';
      searchSpan.innerHTML = SVG_SEARCH +
        '<input type="text" placeholder="' + esc(SEARCH_PH[0]) + '">' +
        '<button class="stf-clear" tabindex="-1" aria-label="Clear search">✕</button>';
      bar.appendChild(searchSpan);

      // ── dropdown filters ──
      function _makeDD(name, opts) {
        if (!opts || opts.length === 0) return null;
        var label = FILTER_LABELS[name] || [name, name];
        var title = FILTER_TITLES[name] || ['All', '全部'];
        var dd = document.createElement('span');
        dd.className = 'stf-dd';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'stf-dd-btn';
        btn.setAttribute('aria-haspopup', 'listbox');
        btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML =
          '<span class="stf-dd-lab">' + bi(label[0], label[1]) + '</span>' +
          '<span class="stf-dd-val">' + bi('All', '全部') + '</span>' +
          SVG_CHEV;
        dd.appendChild(btn);

        // Build menu
        var menu = document.createElement('div');
        menu.className = 'stf-menu';
        menu.setAttribute('role', 'listbox');
        menu.style.display = 'none';

        // "All" option
        var allOpt = document.createElement('div');
        allOpt.className = 'stf-opt';
        allOpt.setAttribute('role', 'option');
        allOpt.setAttribute('aria-selected', 'true');
        allOpt.setAttribute('data-value', 'all');
        var allCount = rows.length;
        allOpt.innerHTML = SVG_TICK +
          '<span class="stf-olab">' + bi(title[0], title[1]) + '</span>' +
          '<span class="stf-cnt">' + allCount + '</span>';
        menu.appendChild(allOpt);

        var sep = document.createElement('div');
        sep.className = 'stf-sep';
        menu.appendChild(sep);

        opts.forEach(function(val) {
          var pair = _optPair(name, val);
          var opt = document.createElement('div');
          opt.className = 'stf-opt';
          opt.setAttribute('role', 'option');
          opt.setAttribute('aria-selected', 'false');
          opt.setAttribute('data-value', val);
          var cnt = (valueCounts[name] && valueCounts[name][val]) || 0;
          opt.innerHTML = SVG_TICK +
            '<span class="stf-olab">' + bi(esc(pair[0]), esc(pair[1])) + '</span>' +
            '<span class="stf-cnt">' + cnt + '</span>';
          menu.appendChild(opt);
        });

        dd.appendChild(menu);
        _ddNodes[name] = { dd: dd, btn: btn, menu: menu, valSpan: btn.querySelector('.stf-dd-val') };
        return dd;
      }

      if (stageOpts.length > 0) { var ddStage = _makeDD('stage', stageOpts); if (ddStage) bar.appendChild(ddStage); }
      if (zoneOpts.length > 0)  { var ddZone  = _makeDD('zone', zoneOpts);   if (ddZone)  bar.appendChild(ddZone); }
      if (tierList.length > 0)  { var ddTier  = _makeDD('tier', tierList);   if (ddTier)  bar.appendChild(ddTier); }
      { var ddSect = _makeDD('sector', sectors); if (ddSect) bar.appendChild(ddSect); }
      if (capBkts.length > 0)   { var ddCap   = _makeDD('capBucket', capBkts); if (ddCap) bar.appendChild(ddCap); }
      if (lanes.length > 0)     { var ddLane  = _makeDD('lane', lanes);       if (ddLane) bar.appendChild(ddLane); }

      // ── fresh chip ──
      var chipBtn = null;
      if (hasFresh) {
        chipBtn = document.createElement('button');
        chipBtn.type = 'button';
        chipBtn.className = 'stf-chipbtn';
        chipBtn.setAttribute('aria-pressed', 'false');
        chipBtn.innerHTML = SVG_TICK_LG + bi('Fresh only', '仅新信号') + ' <span style="opacity:.6;font-weight:500">≤2d</span>';
        bar.appendChild(chipBtn);
      }

      // ── clear filters ──
      var clearBtn = document.createElement('button');
      clearBtn.type = 'button';
      clearBtn.className = 'stf-ghost';
      clearBtn.style.display = 'none';
      clearBtn.innerHTML = '✕ ' + bi('Clear filters', '清除筛选');
      bar.appendChild(clearBtn);

      // ── spacer ──
      var spacer = document.createElement('span');
      spacer.className = 'stf-spacer';
      bar.appendChild(spacer);

      // ── reset order ──
      var resetBtn = document.createElement('button');
      resetBtn.type = 'button';
      resetBtn.id = 'st-reset-order';
      resetBtn.className = 'stf-ghost';
      resetBtn.style.display = 'none';
      resetBtn.innerHTML = '↺ ' + bi('Reset order', '恢复默认排序');
      bar.appendChild(resetBtn);

      // ── columns button ──
      var colBtn = document.createElement('button');
      colBtn.type = 'button';
      colBtn.id = 'st-col-btn';
      colBtn.className = 'stf-colbtn';
      colBtn.innerHTML = SVG_COLS + bi('Columns', '列设置') +
        ' <span class="stf-badge" id="stf-col-badge">' + visN + '/' + colM + '</span>';
      bar.appendChild(colBtn);

      // Replace frow's content
      frow.innerHTML = '';
      frow.appendChild(bar);

      // ── bind all events ──
      _bindFilterRow(bar, searchSpan, chipBtn, clearBtn, colBtn);
    }

    // Returns true when any filter is non-default.
    function _anyFilterActive() {
      return filters.stage !== 'all' || filters.zone !== 'all' || filters.tier !== 'all' ||
             filters.sector !== 'all' || filters.capBucket !== 'all' || filters.lane !== 'all' ||
             filters.theme !== '' || filters.freshOnly;
    }

    // Update the clear-filters button visibility.
    function _syncClearBtn() {
      var btn = frow.querySelector('.stf-ghost:not(#st-reset-order)');
      if (btn) btn.style.display = _anyFilterActive() ? '' : 'none';
    }

    // Close all open dropdowns except optionally one.
    function _closeAllDDs(except) {
      Object.keys(_ddNodes).forEach(function(name) {
        var n = _ddNodes[name];
        if (n.dd === except) return;
        n.dd.classList.remove('stf-open');
        n.btn.setAttribute('aria-expanded', 'false');
        n.menu.style.display = 'none';
      });
    }

    // Open a dropdown menu and focus management.
    function _openDD(name) {
      var n = _ddNodes[name];
      if (!n) return;
      _closeAllDDs(n.dd);
      n.dd.classList.add('stf-open');
      n.btn.setAttribute('aria-expanded', 'true');
      n.menu.style.display = '';
      // viewport clamp: if right edge overflows, flip to right-aligned
      var rect = n.menu.getBoundingClientRect();
      if (rect.right > window.innerWidth - 8) {
        n.menu.classList.add('stf-menu-right');
      } else {
        n.menu.classList.remove('stf-menu-right');
      }
      // focus first/selected item
      var sel = n.menu.querySelector('[aria-selected="true"]') || n.menu.querySelector('.stf-opt');
      if (sel) sel.focus();
    }

    function _closeDD(name) {
      var n = _ddNodes[name];
      if (!n) return;
      n.dd.classList.remove('stf-open');
      n.btn.setAttribute('aria-expanded', 'false');
      n.menu.style.display = 'none';
    }

    // Select a value in a dropdown.
    function _selectDDValue(name, value) {
      var n = _ddNodes[name];
      if (!n) return;
      filters[name] = value;
      // update aria-selected on options
      n.menu.querySelectorAll('.stf-opt').forEach(function(opt) {
        var v = opt.getAttribute('data-value');
        opt.setAttribute('aria-selected', v === value ? 'true' : 'false');
      });
      // update button value span
      if (value === 'all') {
        n.valSpan.innerHTML = bi('All', '全部');
        n.dd.classList.remove('stf-active');
      } else {
        var pair = _optPair(name, value);
        n.valSpan.innerHTML = bi(esc(pair[0]), esc(pair[1]));
        n.dd.classList.add('stf-active');
      }
      _closeDD(name);
      n.btn.focus();
      _syncClearBtn();
      renderRows();
    }

    // Keyboard navigation inside a menu.
    function _ddKeyNav(e, name) {
      var n = _ddNodes[name];
      if (!n) return;
      var opts = Array.from(n.menu.querySelectorAll('.stf-opt'));
      var kb   = n.menu.querySelector('.stf-kb');
      var idx  = kb ? opts.indexOf(kb) : -1;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (kb) kb.classList.remove('stf-kb');
        var next = opts[idx + 1] || opts[0];
        next.classList.add('stf-kb'); next.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (kb) kb.classList.remove('stf-kb');
        var prev = opts[idx - 1] || opts[opts.length - 1];
        prev.classList.add('stf-kb'); prev.focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        if (kb) kb.classList.remove('stf-kb');
        opts[0].classList.add('stf-kb'); opts[0].focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        if (kb) kb.classList.remove('stf-kb');
        opts[opts.length - 1].classList.add('stf-kb'); opts[opts.length - 1].focus();
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        var target = kb || opts.find(function(o){ return o === document.activeElement; });
        if (target) _selectDDValue(name, target.getAttribute('data-value'));
      } else if (e.key === 'Escape') {
        e.preventDefault();
        _closeDD(name); n.btn.focus();
      }
    }

    function _bindFilterRow(bar, searchSpan, chipBtn, clearBtn, colBtn) {
      var input = searchSpan.querySelector('input');
      var clearX = searchSpan.querySelector('.stf-clear');

      // search input
      input.addEventListener('input', function() {
        filters.theme = input.value.trim();
        searchSpan.classList.toggle('stf-has-value', input.value.length > 0);
        _syncClearBtn();
        renderRows();
      });
      clearX.addEventListener('click', function() {
        input.value = '';
        filters.theme = '';
        searchSpan.classList.remove('stf-has-value');
        _syncClearBtn();
        renderRows();
        input.focus();
      });

      // dropdowns
      Object.keys(_ddNodes).forEach(function(name) {
        var n = _ddNodes[name];
        // toggle on button click
        n.btn.addEventListener('click', function(e) {
          e.stopPropagation();
          if (n.dd.classList.contains('stf-open')) {
            _closeDD(name);
          } else {
            _openDD(name);
          }
        });
        // keyboard on button
        n.btn.addEventListener('keydown', function(e) {
          if (e.key === 'ArrowDown' || e.key === 'Enter') {
            e.preventDefault();
            _openDD(name);
          } else if (e.key === 'Escape') {
            _closeDD(name);
          }
        });
        // option click
        n.menu.addEventListener('click', function(e) {
          var opt = e.target.closest('.stf-opt');
          if (opt) _selectDDValue(name, opt.getAttribute('data-value'));
        });
        // keyboard in menu
        n.menu.addEventListener('keydown', function(e) { _ddKeyNav(e, name); });
      });

      // click-outside closes all menus
      document.addEventListener('mousedown', function(e) {
        var insideAny = Object.keys(_ddNodes).some(function(name) {
          return _ddNodes[name].dd.contains(e.target);
        });
        if (!insideAny) _closeAllDDs(null);
      });

      // fresh chip
      if (chipBtn) {
        chipBtn.addEventListener('click', function() {
          filters.freshOnly = !filters.freshOnly;
          chipBtn.setAttribute('aria-pressed', filters.freshOnly ? 'true' : 'false');
          _syncClearBtn();
          renderRows();
        });
      }

      // clear-all filters
      clearBtn.addEventListener('click', function() {
        // reset all dropdown filters
        Object.keys(_ddNodes).forEach(function(name) {
          _selectDDValue(name, 'all');
        });
        // reset search
        input.value = '';
        filters.theme = '';
        searchSpan.classList.remove('stf-has-value');
        // reset fresh chip
        filters.freshOnly = false;
        if (chipBtn) chipBtn.setAttribute('aria-pressed', 'false');
        clearBtn.style.display = 'none';
        renderRows();
      });

      // reset order
      bar.addEventListener('click', function(e) {
        if (e.target.closest('#st-reset-order')) {
          sortKey = null; sortDir = null;
          renderHeader(); renderRows();
        }
        if (e.target.closest('#st-col-btn')) {
          chooserWrap.classList.toggle('st-chooser-hidden');
          colBtn.classList.toggle('stf-open-btn', !chooserWrap.classList.contains('st-chooser-hidden'));
        }
      });
    }

    // langchange: swap search placeholder only (dropdown labels are bi() dual-span)
    document.addEventListener('langchange', function() {
      var inp = frow.querySelector('.stf-search input');
      if (!inp) return;
      var zh = curLang() === 'zh';
      inp.placeholder = zh ? SEARCH_PH[1] : SEARCH_PH[0];
    });

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

    /* ── column chooser ────────────────────────────────────────────────── */

    function _chooserSubLine() {
      var n = visibleCols.filter(function(k){ return columns.some(function(c){ return c.key === k; }); }).length;
      var m = columns.length;
      return bi(n + ' of ' + m + ' shown · drag to reorder',
                '显示 ' + n + '/' + m + ' 列 · 拖动排序');
    }

    function _buildChooser(cols, order, visible, mkt) {
      var html = '<div class="stf-chooser">';
      html += '<div class="stf-ch-hdr">';
      html += '<div class="stf-ch-title">' + bi('Table columns', '表格列') +
              '<button class="stf-ch-close" id="st-chooser-close" aria-label="Close">✕</button></div>';
      html += '<div class="stf-ch-sub">' + _chooserSubLine() + '</div>';
      html += '</div>';
      html += '<div class="stf-ch-list" id="st-chooser-list">';
      order.forEach(function(k) {
        var col = cols.find(function(c){ return c.key === k; });
        if (!col) return;
        var chk = visible.indexOf(k) !== -1;
        // carry column's display class (.st-hide-sm) so mobile-hidden cols
        // also hide their chooser row — no dead toggles
        html += '<div class="stf-ch-row' + (col.cls ? ' ' + esc(col.cls) : '') +
                '" draggable="true" data-key="' + esc(k) + '">';
        html += SVG_GRIP;
        html += '<label>';
        html += '<span class="stf-cb">' +
                '<input type="checkbox" class="st-col-chk" data-key="' + esc(k) + '"' +
                (chk ? ' checked' : '') + '>' +
                '<span class="stf-box">' + SVG_CHK + '</span>' +
                '</span>';
        html += '<span class="stf-collab">' + bi(col.labelEn, col.labelZh) + '</span>';
        html += '</label>';
        html += '</div>';
      });
      html += '</div>';
      html += '<div class="stf-ch-foot">';
      html += '<button class="stf-ch-reset" id="st-chooser-reset">' + bi('Reset to default', '恢复默认') + '</button>';
      html += '<span class="stf-ch-note">' + bi('saved to this browser', '保存在本浏览器') + '</span>';
      html += '</div>';
      html += '</div>';
      return html;
    }

    // Update badge and sub-line counts after chooser changes.
    function _updateChooserCounts() {
      var n = visibleCols.filter(function(k){ return columns.some(function(c){ return c.key === k; }); }).length;
      var m = columns.length;
      var badge = document.getElementById('stf-col-badge');
      if (badge) badge.textContent = n + '/' + m;
      var sub = chooserWrap.querySelector('.stf-ch-sub');
      if (sub) sub.innerHTML = _chooserSubLine();
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
          _updateChooserCounts();
          renderHeader(); renderRows();
        }
      });
      // close button
      chooserWrap.addEventListener('click', function(e) {
        if (e.target.closest('#st-chooser-close')) {
          chooserWrap.classList.add('st-chooser-hidden');
          var colBtn = document.getElementById('st-col-btn');
          if (colBtn) colBtn.classList.remove('stf-open-btn');
        }
        if (e.target.closest('#st-chooser-reset')) {
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
      _updateChooserCounts();
      bindChooser();
    }

    function _bindDrag(list) {
      if (!list) return;
      var dragged = null;
      list.addEventListener('dragstart', function(e) {
        dragged = e.target.closest('[data-key]');
        if (dragged) { e.dataTransfer.effectAllowed = 'move'; dragged.classList.add('stf-dragging'); }
      });
      list.addEventListener('dragend', function() {
        if (dragged) dragged.classList.remove('stf-dragging');
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

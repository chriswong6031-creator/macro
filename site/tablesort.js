/* Make the dashboard's data tables behave like a screener: click any column
   header to sort, and tables long enough to scroll get a live filter box.

   Zero-config: it auto-enhances every real data table on the page and SKIPS the
   little tables that live inside hover tooltips (.tip). Numeric columns are
   detected automatically; cells whose visible text isn't a clean number (heat
   bars, badges) carry an explicit data-sort key. Self-contained, no deps. */
(function () {
  function txt(cell) {
    if (cell.dataset && cell.dataset.sort !== undefined) return cell.dataset.sort;
    return (cell.textContent || '').trim();
  }
  // parse a number out of "+3.2%", "1,240", "12.5×", "—" → number | null
  function num(s) {
    if (s == null) return null;
    s = String(s).replace(/−/g, '-');
    var m = s.replace(/[,%×$\s ]/g, '').replace(/[^0-9.+\-eE]/g, '');
    if (m === '' || m === '+' || m === '-' || m === '.') return null;
    var n = parseFloat(m);
    return isFinite(n) ? n : null;
  }
  function headerRow(table) {
    // a real <thead> wins; otherwise the first tbody row is the header (legacy tables)
    return (table.tHead && table.tHead.rows[0]) || (table.tBodies[0] && table.tBodies[0].rows[0]);
  }
  function dataRows(table) {
    var body = table.tBodies[0];
    if (!body) return [];
    var rows = Array.prototype.slice.call(body.rows);
    return table.tHead ? rows : rows.slice(1); // <thead> → every tbody row is data; else row 0 is the header
  }
  function isNumericCol(rows, i) {
    var seen = 0;
    for (var k = 0; k < rows.length; k++) {
      var c = rows[k].cells[i];
      if (!c) continue;
      var v = txt(c);
      if (v === '' || v === '—' || v === '-' || v === 'n/a') continue; // blanks ok
      if (num(v) === null) return false;
      seen++;
    }
    return seen > 0;
  }

  function sortBy(table, i, dir) {
    var body = table.tBodies[0];
    var rows = dataRows(table);
    var numeric = isNumericCol(rows, i);
    rows.sort(function (a, b) {
      var ca = a.cells[i], cb = b.cells[i];
      var va = ca ? txt(ca) : '', vb = cb ? txt(cb) : '';
      if (numeric) {
        var na = num(va), nb = num(vb);
        if (na === null) na = -Infinity;
        if (nb === null) nb = -Infinity;
        return dir * (na - nb);
      }
      return dir * va.localeCompare(vb, undefined, { numeric: true, sensitivity: 'base' });
    });
    rows.forEach(function (r) { body.appendChild(r); }); // header stays at index 0
  }

  function enhance(table) {
    var header = headerRow(table);
    if (!header) return;
    var rows = dataRows(table);

    Array.prototype.forEach.call(header.cells, function (th, i) {
      th.classList.add('th-sort');
      var arrow = document.createElement('span');
      arrow.className = 'sarrow';
      arrow.textContent = '↕';
      var help = th.querySelector('.help');
      if (help) th.insertBefore(arrow, help); else th.appendChild(arrow);

      th.addEventListener('click', function (e) {
        if (e.target.closest('.help')) return; // let tooltips be tooltips
        var cur = th.getAttribute('data-dir');
        var dir = cur ? (cur === 'desc' ? 1 : -1)
                      : (isNumericCol(rows, i) ? -1 : 1); // numeric → high-first
        Array.prototype.forEach.call(header.cells, function (o) {
          o.removeAttribute('data-dir'); o.classList.remove('sorted');
          var a = o.querySelector('.sarrow'); if (a) a.textContent = '↕';
        });
        th.setAttribute('data-dir', dir === -1 ? 'desc' : 'asc');
        th.classList.add('sorted');
        arrow.textContent = dir === -1 ? '↓' : '↑';
        sortBy(table, i, dir);
      });
    });

    // long tables get a live filter box
    if (rows.length >= 12) addFilter(table);
  }

  function addFilter(table) {
    var rows = dataRows(table);
    var wrap = document.createElement('div');
    wrap.className = 'tbl-filter';
    var input = document.createElement('input');
    input.type = 'search';
    input.placeholder = 'Filter…';
    input.setAttribute('aria-label', 'Filter table rows');
    var cnt = document.createElement('span');
    cnt.className = 'cnt';
    wrap.appendChild(input); wrap.appendChild(cnt);
    // if the table is inside a horizontal-scroll wrapper (theme.js wrapTables), put the
    // filter ABOVE the wrapper so it stays fixed while the table scrolls sideways
    var anchor = (table.parentNode && table.parentNode.classList.contains('tbl-scroll'))
      ? table.parentNode : table;
    anchor.parentNode.insertBefore(wrap, anchor);

    function apply() {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (r) {
        var hit = !q || (r.textContent || '').toLowerCase().indexOf(q) !== -1;
        r.style.display = hit ? '' : 'none';
        if (hit) shown++;
      });
      cnt.textContent = q ? (shown + ' / ' + rows.length) : '';
    }
    input.addEventListener('input', apply);
  }

  function initAll() {
    Array.prototype.forEach.call(document.querySelectorAll('table'), function (t) {
      if (t.closest('.tip')) return;           // skip tooltip tables
      if (t.classList && t.classList.contains('sb-table')) return; // self-managed screener (own sort/toggle)
      if (dataRows(t).length < 2) return;       // nothing to sort
      enhance(t);
    });
  }
  // run now if the DOM is already parsed (script added late / bfcache), else wait
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAll);
  else initAll();
})();

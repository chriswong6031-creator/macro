/* portfolio_import.js — pure A1B Portfolio paste/review contract.

   This module performs no persistence, network, DOM, logging, analytics, Watchlist,
   or temporary-basket work. It turns one line per holding into a reviewable draft
   whose RFC4122 row UUIDs are assigned before any write begins and survive review
   edits, retry reconciliation, cloud persistence, and local-to-cloud fold.

   Accepted grammar (one nonblank line per holding):
     TICKER
     TICKER SHARES
     TICKER SHARES ENTRY_PRICE
     TICKER SHARES ENTRY_PRICE YYYY-MM-DD

   Duplicate tickers are legal lots. Canonical idempotency is row-id based, never
   ticker based. Malformed rows are returned as visible errors and never disappear.
   The API is node-exported behind the house `typeof module` guard so every law can
   be pinned without a browser. */
(function () {
  'use strict';

  var NUMERIC = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  var TICKER = /^[A-Z0-9][A-Z0-9._^=:\/-]{0,127}$/;
  var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

  function own(obj, key) { return Object.prototype.hasOwnProperty.call(obj || {}, key); }

  function isUuid(value) { return typeof value === 'string' && UUID.test(value); }

  function randomUuid() {
    var cryptoObj = typeof crypto !== 'undefined' ? crypto : null;
    if (cryptoObj && typeof cryptoObj.randomUUID === 'function') return cryptoObj.randomUUID();
    if (!cryptoObj || typeof cryptoObj.getRandomValues !== 'function') {
      throw new Error('secure-random-unavailable');
    }
    var bytes = new Uint8Array(16);
    cryptoObj.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    var hex = Array.prototype.map.call(bytes, function (b) {
      return (b + 0x100).toString(16).slice(1);
    }).join('');
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16),
            hex.slice(16, 20), hex.slice(20)].join('-');
  }

  function normalizeTicker(value) {
    var ticker = typeof value === 'string' ? value.trim().toUpperCase() : '';
    return ticker && TICKER.test(ticker) ? ticker : null;
  }

  function numericOrError(value, blankIsNull) {
    if (value === null || value === undefined || (blankIsNull && String(value).trim() === '')) {
      return { ok: true, value: null };
    }
    var raw = String(value).trim();
    if (!NUMERIC.test(raw)) return { ok: false, value: null };
    var parsed = Number(raw);
    return isFinite(parsed) ? { ok: true, value: parsed } : { ok: false, value: null };
  }

  function isRealDate(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    var p = value.split('-').map(Number), year = p[0], month = p[1], day = p[2];
    if (year < 1 || month < 1 || month > 12 || day < 1) return false;
    var leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
    var days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return day <= days[month - 1];
  }

  function coverageOf(ticker, opts) {
    if (!opts || typeof opts.isCovered !== 'function') return 'unknown';
    try {
      var answer = opts.isCovered(ticker);
      return answer === true ? 'covered' : (answer === false ? 'uncovered' : 'unknown');
    } catch (e) { return 'unknown'; }
  }

  function semantic(row) {
    return {
      id: row.id,
      ticker: row.ticker,
      shares: row.shares == null ? null : Number(row.shares),
      entry_price: row.entry_price == null ? null : Number(row.entry_price),
      entry_date: row.entry_date || null,
      notes: row.notes == null || row.notes === '' ? null : String(row.notes),
      status: row.status === 'closed' ? 'closed' : 'open'
    };
  }

  function semanticKey(row, includeId) {
    var s = semantic(row);
    var out = [s.ticker, s.shares, s.entry_price, s.entry_date, s.notes, s.status];
    if (includeId) out.unshift(s.id);
    return JSON.stringify(out);
  }

  function sameSemantic(a, b) { return semanticKey(a, true) === semanticKey(b, true); }

  function annotate(rows) {
    var byTicker = {}, byLot = {};
    (rows || []).forEach(function (row) {
      (byTicker[row.ticker] = byTicker[row.ticker] || []).push(row.id);
      var key = semanticKey(row, false);
      (byLot[key] = byLot[key] || []).push(row.id);
    });
    return (rows || []).map(function (row) {
      var warnings = [];
      if (byTicker[row.ticker].length > 1) warnings.push('duplicate_ticker');
      if (byLot[semanticKey(row, false)].length > 1) warnings.push('exact_duplicate');
      var out = semantic(row);
      out.line = row.line == null ? null : row.line;
      out.coverage = row.coverage || 'unknown';
      out.warnings = warnings;
      return out;
    });
  }

  function lineError(line, raw, code) {
    return { line: line, raw: raw, code: code };
  }

  function unsupportedCode(raw, fields) {
    if (raw.indexOf('%') >= 0) return 'unsupported_percentage';
    if (raw.indexOf('$') >= 0) return 'unsupported_dollar_allocation';
    if (/\b(?:target|weight|allocation)\s*[:=]/i.test(raw)) return 'unsupported_target_allocation';
    if (fields.length && /^(?:CASH|CASH:.*)$/i.test(fields[0])) return 'unsupported_cash';
    return null;
  }

  function parse(text, opts) {
    opts = opts || {};
    var idFactory = typeof opts.idFactory === 'function' ? opts.idFactory : randomUuid;
    var rows = [], errors = [], lines = String(text == null ? '' : text).split(/\r?\n/);
    lines.forEach(function (source, index) {
      var raw = source.trim(), line = index + 1;
      if (!raw) return;
      var fields = raw.split(/\s+/), unsupported = unsupportedCode(raw, fields);
      if (unsupported) { errors.push(lineError(line, source, unsupported)); return; }
      if (fields.length > 4) { errors.push(lineError(line, source, 'too_many_fields')); return; }

      var ticker = normalizeTicker(fields[0]);
      if (!ticker) { errors.push(lineError(line, source, 'invalid_ticker')); return; }
      var shares = fields.length >= 2 ? numericOrError(fields[1], false) : { ok: true, value: null };
      if (!shares.ok) { errors.push(lineError(line, source, 'invalid_shares')); return; }
      var price = fields.length >= 3 ? numericOrError(fields[2], false) : { ok: true, value: null };
      if (!price.ok) { errors.push(lineError(line, source, 'invalid_price')); return; }
      var date = fields.length >= 4 ? fields[3] : null;
      if (date !== null && !isRealDate(date)) {
        errors.push(lineError(line, source, 'invalid_date')); return;
      }

      var id;
      try { id = idFactory(); } catch (e) {
        errors.push(lineError(line, source, 'uuid_unavailable')); return;
      }
      if (!isUuid(id)) { errors.push(lineError(line, source, 'invalid_uuid')); return; }
      rows.push({
        id: id, ticker: ticker, shares: shares.value, entry_price: price.value,
        entry_date: date, notes: null, status: 'open', line: line,
        coverage: coverageOf(ticker, opts), warnings: []
      });
    });
    return { rows: annotate(rows), errors: errors, line_count: lines.length };
  }

  function edit(rows, id, patch, opts) {
    var found = false, errors = [], next = (rows || []).map(function (row) {
      if (row.id !== id) return row;
      found = true;
      var out = semantic(row);
      out.line = row.line; out.coverage = row.coverage; out.warnings = row.warnings || [];
      if (own(patch, 'ticker')) {
        var ticker = normalizeTicker(patch.ticker);
        if (!ticker) errors.push({ code: 'invalid_ticker', id: id }); else out.ticker = ticker;
      }
      if (own(patch, 'shares')) {
        var shares = numericOrError(patch.shares, true);
        if (!shares.ok) errors.push({ code: 'invalid_shares', id: id }); else out.shares = shares.value;
      }
      if (own(patch, 'entry_price')) {
        var price = numericOrError(patch.entry_price, true);
        if (!price.ok) errors.push({ code: 'invalid_price', id: id }); else out.entry_price = price.value;
      }
      if (own(patch, 'entry_date')) {
        var date = patch.entry_date == null ? '' : String(patch.entry_date).trim();
        if (date && !isRealDate(date)) errors.push({ code: 'invalid_date', id: id });
        else out.entry_date = date || null;
      }
      out.coverage = coverageOf(out.ticker, opts);
      return out;
    });
    if (!found) errors.push({ code: 'row_not_found', id: id });
    return errors.length ? { ok: false, rows: rows.slice(), errors: errors }
                         : { ok: true, rows: annotate(next), errors: [] };
  }

  function remove(rows, id) {
    var next = (rows || []).filter(function (row) { return row.id !== id; });
    return { ok: next.length !== (rows || []).length, rows: annotate(next) };
  }

  function validate(rows) {
    if (!Array.isArray(rows) || !rows.length) return { ok: false, code: 'empty_batch' };
    var ids = {};
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i] || {}, ticker = normalizeTicker(row.ticker);
      if (!isUuid(row.id)) return { ok: false, code: 'invalid_uuid', index: i };
      if (ids[row.id]) return { ok: false, code: 'duplicate_uuid', index: i };
      ids[row.id] = true;
      if (!ticker || ticker !== row.ticker) return { ok: false, code: 'invalid_ticker', index: i };
      if (row.shares != null && (typeof row.shares !== 'number' || !isFinite(row.shares))) {
        return { ok: false, code: 'invalid_shares', index: i };
      }
      if (row.entry_price != null && (typeof row.entry_price !== 'number' || !isFinite(row.entry_price))) {
        return { ok: false, code: 'invalid_price', index: i };
      }
      if (row.entry_date != null && !isRealDate(row.entry_date)) {
        return { ok: false, code: 'invalid_date', index: i };
      }
      if (row.status !== 'open' || (row.notes !== null && row.notes !== undefined && row.notes !== '')) {
        return { ok: false, code: 'unsupported_semantics', index: i };
      }
      if (own(row, 'user_id')) return { ok: false, code: 'caller_owner_forbidden', index: i };
    }
    return { ok: true, code: null };
  }

  function fingerprint(rows) {
    var check = validate(rows);
    if (!check.ok) return null;
    return JSON.stringify(rows.map(function (row) { return semantic(row); }));
  }

  var API = {
    parse: parse,
    edit: edit,
    remove: remove,
    validate: validate,
    fingerprint: fingerprint,
    semantic: semantic,
    sameSemantic: sameSemantic,
    isUuid: isUuid,
    isRealDate: isRealDate,
    normalizeTicker: normalizeTicker,
    randomUuid: randomUuid
  };
  if (typeof window !== 'undefined') window.PortfolioImport = API;
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
})();

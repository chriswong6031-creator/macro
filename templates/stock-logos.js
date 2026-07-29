/* stock-logos.js — lazy company marks for the global stock search.
 *
 * The adapter paints a deterministic local monogram first, then asks Logo.dev
 * for a mark only after the result is visible. A publishable image-CDN token
 * may be supplied by the page as window.MMX_LOGO_DEV_TOKEN. With no token (or
 * after any image error) the monogram remains the complete, unbroken UI.
 */
(function (root) {
  'use strict';

  var doc = root.document || null;
  var entries = [];
  var observer = null;
  var nodeEntries = typeof root.WeakMap === 'function' ? new root.WeakMap() : null;
  var STYLE_ID = 'mmx-stock-logo-css';
  var COUNTRY_FLAGS = {
    US: '🇺🇸', USA: '🇺🇸', UNITEDSTATES: '🇺🇸',
    CA: '🇨🇦', CANADA: '🇨🇦',
    HK: '🇭🇰', HONGKONG: '🇭🇰',
    CN: '🇨🇳', CHINA: '🇨🇳',
    GB: '🇬🇧', UK: '🇬🇧', UNITEDKINGDOM: '🇬🇧',
    DE: '🇩🇪', GERMANY: '🇩🇪', FR: '🇫🇷', FRANCE: '🇫🇷',
    IT: '🇮🇹', ITALY: '🇮🇹', NL: '🇳🇱', NETHERLANDS: '🇳🇱',
    CH: '🇨🇭', SWITZERLAND: '🇨🇭',
    SE: '🇸🇪', SWEDEN: '🇸🇪', NO: '🇳🇴', NORWAY: '🇳🇴',
    DK: '🇩🇰', DENMARK: '🇩🇰', FI: '🇫🇮', FINLAND: '🇫🇮',
    AU: '🇦🇺', AUSTRALIA: '🇦🇺', NZ: '🇳🇿', NEWZEALAND: '🇳🇿',
    JP: '🇯🇵', JAPAN: '🇯🇵', KR: '🇰🇷', SOUTHKOREA: '🇰🇷',
    SG: '🇸🇬', SINGAPORE: '🇸🇬', IN: '🇮🇳', INDIA: '🇮🇳',
    ID: '🇮🇩', INDONESIA: '🇮🇩', BR: '🇧🇷', BRAZIL: '🇧🇷',
    MX: '🇲🇽', MEXICO: '🇲🇽', ZA: '🇿🇦', SOUTHAFRICA: '🇿🇦',
    TW: '🇹🇼', TAIWAN: '🇹🇼'
  };
  var SUFFIX_FLAGS = {
    L: '🇬🇧', DE: '🇩🇪', F: '🇩🇪', PA: '🇫🇷', MI: '🇮🇹',
    AS: '🇳🇱', SW: '🇨🇭', ST: '🇸🇪', OL: '🇳🇴', CO: '🇩🇰',
    HE: '🇫🇮', AX: '🇦🇺', NZ: '🇳🇿', T: '🇯🇵', KS: '🇰🇷',
    KQ: '🇰🇷', SI: '🇸🇬', NS: '🇮🇳', BO: '🇮🇳', JK: '🇮🇩',
    SA: '🇧🇷', MX: '🇲🇽', JO: '🇿🇦', TW: '🇹🇼', TWO: '🇹🇼',
    TO: '🇨🇦', V: '🇨🇦', HK: '🇭🇰', SS: '🇨🇳', SZ: '🇨🇳'
  };
  var INTERNATIONAL_SUFFIXES = {
    L: 1, DE: 1, F: 1, PA: 1, MI: 1, AS: 1, SW: 1, ST: 1,
    OL: 1, CO: 1, HE: 1, AX: 1, NZ: 1, T: 1, KS: 1, KQ: 1,
    SI: 1, NS: 1, BO: 1, JK: 1, SA: 1, MX: 1, JO: 1, TW: 1,
    TWO: 1
  };

  function text(value) {
    return value === undefined || value === null ? '' : String(value).trim();
  }

  function compactKey(value) {
    return text(value).toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  function marketKey(market) {
    var key = compactKey(market);
    if (/^(US|USA|UNITEDSTATES|NYSE|NASDAQ|AMEX)$/.test(key)) return 'US';
    if (/^(CA|CANADA|TSX|TSXV|TORONTO)$/.test(key)) return 'CA';
    if (/^(HK|HONGKONG|HKG|HKEX)$/.test(key)) return 'HK';
    if (/^(CN|CHINA|ASHARE|ASHARES|SSE|SZSE|SHANGHAI|SHENZHEN)$/.test(key)) return 'CN';
    if (/^(INTL|INTERNATIONAL|GLOBAL|WORLD)$/.test(key)) return 'INTL';
    return key;
  }

  function suffixOf(ticker) {
    var match = /\.([A-Z]{1,4})$/.exec(ticker);
    return match ? match[1] : '';
  }

  function normalizeTicker(ticker, market) {
    var value = text(ticker).toUpperCase().replace(/\s+/g, '');
    var mk = marketKey(market);
    var colon = /^([A-Z]+):(.+)$/.exec(value);

    if (colon) {
      var exchange = colon[1], symbol = colon[2];
      if (/^(NYSE|NASDAQ|AMEX|US)$/.test(exchange)) value = symbol;
      else if (/^(TSX|TSE)$/.test(exchange)) value = symbol.replace(/\.(TO|TSE)$/, '') + '.TO';
      else if (exchange === 'TSXV') value = symbol.replace(/\.V$/, '') + '.V';
      else if (/^(HKEX|HKG)$/.test(exchange)) value = symbol.replace(/\.HK$/, '') + '.HK';
      else if (/^(SSE|SHA|SHH)$/.test(exchange)) value = symbol.replace(/\.(SS|SH)$/, '') + '.SS';
      else if (/^(SZSE|SHE)$/.test(exchange)) value = symbol.replace(/\.SZ$/, '') + '.SZ';
      else if (/^(LSE|LON)$/.test(exchange)) value = symbol.replace(/\.(L|LN)$/, '') + '.L';
      else value = symbol;
    }

    value = value
      .replace(/\.TSE$/, '.TO')
      .replace(/\.LN$/, '.L')
      .replace(/\.JP$/, '.T')
      .replace(/\.AU$/, '.AX')
      .replace(/\.SH$/, '.SS');

    if (mk === 'US') {
      value = value.replace(/\.(US|NYSE|NASDAQ|AMEX)$/, '');
    } else if (mk === 'CA' && !/\.(TO|V)$/.test(value)) {
      value += '.TO';
    } else if (mk === 'HK') {
      value = value.replace(/\.HK$/, '');
      if (/^\d{1,4}$/.test(value)) value = ('0000' + value).slice(-4);
      value += '.HK';
    } else if (mk === 'CN' && !/\.(SS|SZ|BJ)$/.test(value)) {
      if (/^\d{6}$/.test(value)) {
        value += /^[569]/.test(value) ? '.SS' : (/^[48]/.test(value) ? '.BJ' : '.SZ');
      }
    }
    return value;
  }

  function recordValue(record, names) {
    var i;
    record = record || {};
    for (i = 0; i < names.length; i += 1) {
      if (text(record[names[i]])) return text(record[names[i]]);
    }
    return '';
  }

  function canonicalRecord(record) {
    var ticker = recordValue(record, ['ticker', 'symbol', 't']);
    var name = recordValue(record, ['name', 'companyName', 'company', 'n']);
    var market = recordValue(record, ['market', 'mk', '_mk']);
    var country = recordValue(record, ['country', 'countryCode', 'cc']);
    var flag = recordValue(record, ['flag', 'fl', '_fl']);
    return {
      ticker: normalizeTicker(ticker, market),
      originalTicker: ticker,
      name: name,
      market: market,
      country: country,
      flag: flag
    };
  }

  function sourceFor(record) {
    var item = canonicalRecord(record);
    var mk = marketKey(item.market);
    var suffix = suffixOf(item.ticker);
    var ambiguousIntl = mk === 'INTL' && !INTERNATIONAL_SUFFIXES[suffix];
    var ambiguousChina = mk === 'CN' && suffix === 'BJ';

    if ((ambiguousIntl || ambiguousChina) && item.name) {
      return { kind: 'name', value: item.name, ticker: item.ticker };
    }
    if (item.ticker) return { kind: 'ticker', value: item.ticker, ticker: item.ticker };
    if (item.name) return { kind: 'name', value: item.name, ticker: '' };
    return null;
  }

  function theme() {
    if (!doc || !doc.documentElement) return 'light';
    return text(doc.documentElement.getAttribute('data-theme')).toLowerCase() === 'dark'
      ? 'dark' : 'light';
  }

  function encodePathValue(value) {
    return encodeURIComponent(String(value)).replace(/[!'()*]/g, function (char) {
      return '%' + char.charCodeAt(0).toString(16).toUpperCase();
    });
  }

  function buildUrl(record, requestedTheme) {
    var token = text(root.MMX_LOGO_DEV_TOKEN);
    var source = sourceFor(record);
    var query;
    if (!token || !source) return '';
    query = new root.URLSearchParams();
    query.set('token', token);
    query.set('theme', requestedTheme === 'dark' ? 'dark' : 'light');
    query.set('size', '64');
    query.set('format', 'png');
    query.set('retina', 'true');
    return 'https://img.logo.dev/' + source.kind + '/' +
      encodePathValue(source.value) + '?' + query.toString();
  }

  function flagFor(record) {
    var item = canonicalRecord(record);
    var explicit = text(item.flag);
    var country = compactKey(item.country);
    var mk = marketKey(item.market);
    var suffix = suffixOf(item.ticker);
    if (explicit) return explicit;
    if (COUNTRY_FLAGS[country]) return COUNTRY_FLAGS[country];
    if (COUNTRY_FLAGS[mk]) return COUNTRY_FLAGS[mk];
    if (SUFFIX_FLAGS[suffix]) return SUFFIX_FLAGS[suffix];
    return '🌐';
  }

  function monogramFor(record) {
    var item = canonicalRecord(record);
    var ticker = item.ticker.replace(/\.[A-Z]{1,4}$/, '').replace(/[^0-9A-Z]/g, '');
    var words = item.name.match(/[A-Za-z0-9]+/g) || [];
    var mark = '';
    if (words.length > 1) mark = words[0].charAt(0) + words[1].charAt(0);
    else if (words.length === 1) mark = words[0].slice(0, 2);
    else mark = ticker.slice(0, 2);
    return (mark || '•').toUpperCase();
  }

  function labelFor(record) {
    var item = canonicalRecord(record);
    return (item.name || item.originalTicker || item.ticker || 'Company') + ' logo';
  }

  function installStyles(ownerDocument) {
    var d = ownerDocument || doc;
    var style;
    if (!d || !d.createElement || (d.getElementById && d.getElementById(STYLE_ID))) return;
    style = d.createElement('style');
    style.id = STYLE_ID;
    style.textContent = [
      '.mmx-stock-logo{--mmx-logo-size:30px;position:relative;display:inline-grid;',
      'place-items:center;width:var(--mmx-logo-size);height:var(--mmx-logo-size);',
      'min-width:var(--mmx-logo-size);border-radius:7px;isolation:isolate}',
      '.mmx-stock-logo__image,.mmx-stock-logo__fallback{grid-area:1/1;width:100%;',
      'height:100%;box-sizing:border-box;border-radius:inherit}',
      '.mmx-stock-logo__image{display:none;object-fit:contain;background:var(--panel,#fff)}',
      '.mmx-stock-logo__fallback{display:grid;place-items:center;border:1px solid var(--line,#d7dce5);',
      'color:var(--text,#263247);background:var(--panel2,#eef1f5);font:700 10px/1 system-ui,sans-serif;',
      'letter-spacing:.02em}',
      '.mmx-stock-logo__flag{position:absolute;right:-3px;bottom:-3px;z-index:2;display:grid;',
      'place-items:center;width:14px;height:14px;border-radius:50%;background:var(--panel,#fff);',
      'box-shadow:0 0 0 1.5px var(--panel,#fff);font-size:9px;line-height:1}',
      '.mmx-stock-logo[data-logo-state="loaded"] .mmx-stock-logo__image{display:block}',
      '.mmx-stock-logo[data-logo-state="loaded"] .mmx-stock-logo__fallback{display:none}'
    ].join('');
    (d.head || d.documentElement).appendChild(style);
  }

  function isVisible(node) {
    var rect;
    if (!node || !node.isConnected) return false;
    if (doc && doc.visibilityState === 'hidden') return false;
    if (!node.getBoundingClientRect) return true;
    rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 &&
      rect.bottom >= 0 && rect.right >= 0 &&
      rect.top <= (root.innerHeight || 0) &&
      rect.left <= (root.innerWidth || 0);
  }

  function paintFallback(entry) {
    entry.wrapper.setAttribute('data-logo-state', 'fallback');
    entry.image.style.display = 'none';
    entry.fallback.style.display = 'grid';
  }

  function requestImage(entry, force) {
    var nextTheme = theme();
    var url;
    if (!entry || !entry.wrapper.isConnected) return;
    if (!force && entry.started) return;
    url = buildUrl(entry.record, nextTheme);
    if (!url) {
      paintFallback(entry);
      return;
    }
    entry.started = true;
    entry.activeTheme = nextTheme;
    paintFallback(entry);
    entry.image.onload = function () {
      if (entry.image.getAttribute('src') !== url) return;
      entry.wrapper.setAttribute('data-logo-state', 'loaded');
      entry.image.style.display = 'block';
      entry.fallback.style.display = 'none';
    };
    entry.image.onerror = function () {
      if (entry.image.getAttribute('src') !== url) return;
      entry.image.removeAttribute('src');
      paintFallback(entry);
    };
    entry.image.setAttribute('src', url);
  }

  function entryForNode(node) {
    return nodeEntries ? nodeEntries.get(node) : node.__mmxStockLogoEntry;
  }

  function rememberNode(node, entry) {
    if (nodeEntries) nodeEntries.set(node, entry);
    else node.__mmxStockLogoEntry = entry;
  }

  function ensureObserver() {
    if (observer || typeof root.IntersectionObserver !== 'function') return observer;
    observer = new root.IntersectionObserver(function (changes) {
      changes.forEach(function (change) {
        var entry = entryForNode(change.target);
        if (!entry || (!change.isIntersecting && !(change.intersectionRatio > 0))) return;
        observer.unobserve(change.target);
        requestImage(entry, false);
      });
    }, { rootMargin: '0px' });
    return observer;
  }

  function queueVisibleLoad(entry) {
    var io;
    if (!text(root.MMX_LOGO_DEV_TOKEN)) return;
    io = ensureObserver();
    if (io) {
      rememberNode(entry.wrapper, entry);
      io.observe(entry.wrapper);
      return;
    }
    (root.requestAnimationFrame || function (callback) { root.setTimeout(callback, 0); })(
      function () { if (isVisible(entry.wrapper)) requestImage(entry, false); }
    );
  }

  function create(record, options) {
    var d = options && options.document || doc;
    var wrapper, image, fallback, flag, entry, item;
    if (!d || !d.createElement) return null;
    installStyles(d);
    item = canonicalRecord(record);
    wrapper = d.createElement('span');
    wrapper.className = 'mmx-stock-logo';
    wrapper.setAttribute('data-logo-state', 'fallback');
    wrapper.setAttribute('data-logo-ticker', item.ticker);
    wrapper.setAttribute('role', 'img');
    wrapper.setAttribute('aria-label', labelFor(record));
    if ((options && options.size) || (record && record.size)) {
      wrapper.style.setProperty(
        '--mmx-logo-size',
        String(options && options.size || record.size) + 'px'
      );
    }

    image = d.createElement('img');
    image.className = 'mmx-stock-logo__image';
    image.alt = labelFor(record);
    image.decoding = 'async';

    fallback = d.createElement('span');
    fallback.className = 'mmx-stock-logo__fallback';
    fallback.setAttribute('aria-hidden', 'true');
    fallback.textContent = monogramFor(record);

    flag = d.createElement('span');
    flag.className = 'mmx-stock-logo__flag';
    flag.setAttribute('aria-hidden', 'true');
    flag.textContent = flagFor(record);

    wrapper.appendChild(image);
    wrapper.appendChild(fallback);
    wrapper.appendChild(flag);
    entry = { wrapper: wrapper, image: image, fallback: fallback, record: record || {}, started: false, activeTheme: '' };
    entries.push(entry);
    queueVisibleLoad(entry);
    return wrapper;
  }

  function render(container, record, options) {
    var logo;
    if (!container || !container.appendChild) return null;
    logo = create(record, options);
    if (!logo) return null;
    while (container.firstChild) container.removeChild(container.firstChild);
    container.appendChild(logo);
    return logo;
  }

  function datasetRecord(node) {
    var data = node.dataset || {};
    return {
      ticker: data.ticker || data.symbol || data.t || '',
      name: data.name || data.company || data.n || '',
      market: data.market || data.mk || '',
      country: data.country || data.countryCode || '',
      flag: data.flag || ''
    };
  }

  function enhance(scope, selector) {
    var base = scope || doc;
    var query = selector || '[data-stock-logo]';
    var nodes;
    if (!base || !base.querySelectorAll) return [];
    nodes = Array.prototype.slice.call(base.querySelectorAll(query));
    return nodes.map(function (node) {
      return render(node, datasetRecord(node), {
        document: node.ownerDocument,
        size: node.getAttribute('data-logo-size') || ''
      });
    });
  }

  function refreshTheme() {
    var nextTheme = theme();
    entries = entries.filter(function (entry) { return entry.wrapper && entry.wrapper.isConnected; });
    entries.forEach(function (entry) {
      if (entry.started && entry.activeTheme !== nextTheme) requestImage(entry, true);
    });
  }

  function createAttribution(ownerDocument) {
    var d = ownerDocument || doc;
    var link;
    if (!d || !d.createElement) return null;
    link = d.createElement('a');
    link.className = 'mmx-stock-logo-attribution';
    link.href = 'https://www.logo.dev/';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Logos provided by Logo.dev';
    return link;
  }

  if (doc && doc.addEventListener) doc.addEventListener('themechange', refreshTheme);
  if (doc && doc.documentElement && typeof root.MutationObserver === 'function') {
    new root.MutationObserver(refreshTheme).observe(doc.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme']
    });
  }

  var api = {
    normalizeTicker: normalizeTicker,
    sourceFor: sourceFor,
    buildUrl: buildUrl,
    flagFor: flagFor,
    monogramFor: monogramFor,
    create: create,
    render: render,
    enhance: enhance,
    refreshTheme: refreshTheme,
    createAttribution: createAttribution
  };
  root.MMXStockLogo = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
}(typeof window !== 'undefined' ? window : globalThis));

/* Preview seeds for the W2 visual gate.

   Every crop is shot through the page's own JS against REAL nightly artifacts
   (site/stockdata/*.json + factor_betas.json). These helpers only put a BOOK in
   localStorage — the same store a real visitor's book lives in — and, for the
   anonymous matrix, remove the four account-gated scripts before they run so the
   page boots exactly the way it boots behind the wall (401 -> script never executes).
   Nothing here fabricates a figure. */
window.__W2 = {
  book: function () {
    localStorage.setItem('mdash.pf.v1', JSON.stringify({ v: 1, rows: [
      { id: 'loc-1',  ticker: 'NVDA',  shares: 176, entry_price: 118.40, entry_date: '2025-11-04', status: 'open' },
      { id: 'loc-2',  ticker: 'MSFT',  shares: 49,  entry_price: 402.10, entry_date: '2025-09-12', status: 'open' },
      { id: 'loc-3',  ticker: 'AAPL',  shares: 96,  entry_price: 198.55, entry_date: '2025-06-20', status: 'open' },
      { id: 'loc-4',  ticker: 'AVGO',  shares: 64,  entry_price: 151.20, entry_date: '2026-01-15', status: 'open' },
      { id: 'loc-5',  ticker: 'GOOGL', shares: 78,  entry_price: 162.90, entry_date: '2025-08-01', status: 'open' },
      { id: 'loc-6',  ticker: 'AMZN',  shares: 71,  entry_price: 181.30, entry_date: '2025-10-09', status: 'open' },
      { id: 'loc-7',  ticker: 'TSM',   shares: 60,  entry_price: 171.05, entry_date: '2025-12-02', status: 'open' },
      { id: 'loc-8',  ticker: 'LLY',   shares: 14,  entry_price: 812.40, entry_date: '2026-02-18', status: 'open' },
      { id: 'loc-9',  ticker: 'XOM',   shares: 88,  entry_price: 108.75, entry_date: '2025-07-14', status: 'open' },
      { id: 'loc-10', ticker: 'GLD',   shares: 36,  entry_price: 242.10, entry_date: '2025-05-22', status: 'open' },
      { id: 'loc-11', ticker: 'TLT',   shares: 88,  entry_price: 86.40,  entry_date: '2025-04-30', status: 'open' },
      { id: 'loc-12', ticker: 'IBIT',  shares: 150, entry_price: 48.20,  entry_date: '2026-03-11', status: 'open' }
    ] }));
  },
  /* A genuinely multi-market book. `marketOf` is a pure SUFFIX derivation, so a book
     of US-listed names — IBIT included, which is a US-listed ETF — has exactly one
     market and the chips correctly stay away. Testing the filter needs real suffixes. */
  bookmix: function () {
    window.__W2.book();
    var b = JSON.parse(localStorage.getItem('mdash.pf.v1'));
    b.rows.push({ id: 'loc-13', ticker: '0700.HK', shares: 400, entry_price: 388.20,
                  entry_date: '2025-10-02', status: 'open' });
    b.rows.push({ id: 'loc-14', ticker: '9988.HK', shares: 500, entry_price: 92.10,
                  entry_date: '2026-01-08', status: 'open' });
    b.rows.push({ id: 'loc-15', ticker: 'SHOP.TO', shares: 120, entry_price: 148.65,
                  entry_date: '2025-12-19', status: 'open' });
    localStorage.setItem('mdash.pf.v1', JSON.stringify(b));
  },
  // 55 real AI-infrastructure names — the pinned mockup's own watchlist cohort
  WL55: ['NVDA','AMD','AVGO','TSM','ASML','AMAT','LRCX','KLAC','MU','MRVL','ARM','SMCI',
         'DELL','ANET','CIEN','CRDO','ALAB','VRT','ETN','PWR','NVT','MOD','GEV','VST',
         'CEG','NRG','TLN','OKLO','SMR','NNE','PLTR','SNOW','MDB','DDOG','NET','CRWD',
         'ORCL','MSFT','GOOGL','META','AMZN','CRM','NOW','IBM','QCOM','INTC','TXN','ADI',
         'ONTO','NVMI','AEIS','UCTT','ACLS','CLS','FN'],
  list: function (syms) {
    localStorage.setItem('mdash.watchlist.v1', JSON.stringify({
      v: 1, updated: new Date().toISOString(),
      items: syms.map(function (t) { return { t: t, added: '2026-07-01T00:00:00Z', note: '' }; }),
      order: syms.slice(), settings: { sort: 'order', buySoonOnly: false }
    }));
  },
  // a prior snapshot so "changed since your last visit" has something true to say
  seen: function (syms) {
    var prev = {};
    syms.forEach(function (t, i) { prev[t] = (i % 7 === 2) ? 'DECLINE' : 'RALLY ON'; });
    localStorage.setItem('mdash.wl.seen.v1', JSON.stringify(prev));
  },
  entry: function (text, mode) {
    localStorage.setItem('mdash.ws.entry.v1', JSON.stringify({ mode: mode || 'equal', text: text }));
  },
  mode: function (m) { localStorage.setItem('mdash.ws.mode.v1', m); },
  book_filter: function (b) { localStorage.setItem('mdash.book.v1', b); },
  clear: function () {
    ['mdash.pf.v1','mdash.watchlist.v1','mdash.ws.entry.v1','mdash.ws.mode.v1',
     'mdash.book.v1','mdash.wl.seen.v1'].forEach(function (k) { localStorage.removeItem(k); });
  }
};

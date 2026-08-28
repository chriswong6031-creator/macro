---
key: TERMINAL-QUOTE-DEMAND-SILENT-SLICE
claim: >
  Terminal's `/api/quote?syms=` enforced its 200-symbol batch cap with a bare
  `slice(0, MAX_BATCH)` — no 413, no truncation flag, no remainder — so a caller
  received a response shaped exactly like a complete one and had no way to learn its
  later symbols were never requested. Nothing else in the product makes 200 the
  list-size boundary: canonical watchlist operations permit 500 (terminal/lib/
  watchlists.ts MAX_BATCH = 500) and a composite row expands into SEVERAL quote
  symbols, so "200 rows" is not even "200 quote symbols". MEASURED on the shell's real
  demand shape — active + 16 movers + a 300-row watchlist = 317 distinct symbols —
  117 of the 317 were never requested at all. The ordering made it worse than a simple
  tail loss: TerminalShell built the flat array as [active, ...watchlist, ...movers],
  so the 16-symbol MOVERS STRIP sat behind 300 watchlist rows and lost its live plane
  ENTIRELY, not partially. Affected rows silently fell back to manifest EOD for as long
  as the list stayed that size, with nothing on screen attributing it to list POSITION
  rather than to market support. PortfolioView carried the identical unchunked send.
falsifier: >
  Any of: `/api/quote` returning an explicit truncation signal that its callers act on;
  a caller that plans its batch under the cap (terminal/lib/quoteDemand.ts does this
  now, so on current master the 117 is 0); the watchlist batch limit in
  terminal/lib/watchlists.ts dropping to <= the route cap so overshoot is unreachable;
  or a measurement on the real demand shape showing full coverage while the route still
  slices silently. Re-running lib/__tests__/quoteDemand.test.ts "BEFORE" case against a
  changed demand-assembly order would also move the 117.
so_what: >
  Two things a future session should carry. (1) When a route caps a batch, the cap is
  not the defect — enforcing it in SILENCE is. A short map indistinguishable from a
  complete one converts a bounded-load decision into permanent invisible data loss, and
  it survives review precisely because every individual piece looks correct. Make the
  cap speak (`truncated: {requested, served, omitted[]}`) even when the in-product
  caller is expected never to trip it. (2) When demand exceeds a transport bound, fix it
  at the DEMAND layer, not by raising the bound: raising 200 -> 500 would have moved the
  boundary while tripling one poll's provider fan-out (the hub chunks at 100, Tencent at
  30) and pushing the GET toward URL limits. Priority-plus-rotation gives full coverage
  at IDENTICAL request volume — see DEC:TERMINAL-QUOTE-DEMAND-IS-PLANNED-NOT-CAPPED.
  Also: measure the real assembly ORDER before assuming a truncation loses "the tail".
  Here it silently killed a headline UI strip that no one would have thought to check.
kind: landmine
verified_at: 2026-08-19
verified_by: >
  Pre-fix code: terminal/app/api/quote/route.ts (MAX_BATCH = 200; the batch branch's
  `.slice(0, chartCadence ? MAX_CHART_BATCH : MAX_BATCH)` with no truncation reporting)
  and terminal/components/TerminalShell.tsx `quoteSyms` useMemo building
  [active, ...watchlist legs, ...movers.slice(0,16)] as one flat deduped array;
  terminal/lib/watchlists.ts MAX_BATCH = 500 for the conflicting list bound;
  terminal/components/PortfolioView.tsx sending `quoteSymbols(positions).sort().join(",")`
  whole. The 117/317 and the total movers loss are ASSERTED, not estimated, in
  terminal/lib/__tests__/quoteDemand.test.ts describe "the measurement, on the shell's
  real demand shape" (BEFORE case). Reproduced end-to-end in a real browser against a
  real 300-symbol watchlist by terminal/e2e/quote-demand-coverage.spec.ts, which fails
  with "symbol #201 (ZTEST0200) must be covered" when the flat silent slice is restored.
  Shipped in mastermind-terminal PR #429.
scope: [terminal]
confidence: verified
---

## Detail

The defect is a good example of a class that unit review does not catch: every component was
individually defensible. A 200-symbol cap on an upstream fan-out is correct engineering. A
watchlist limit of 500 is a reasonable product bound. Expanding a composite into its legs is
required for the row to be correct at all. The bug lives only in the *seam* — the point where a
demand set larger than the transport bound met a transport that discarded the excess without
saying so.

Three details are worth keeping.

**"200 rows" was never the real boundary.** Because composites expand, the number of quote symbols
is unbounded above the row count, so a user could cross the cap with well under 200 visible rows.
Any future reasoning of the form "our lists are small enough" has to be done in SYMBOLS, after
expansion, including the movers strip and the active symbol — not in rows.

**The loss was position-dependent, which is why it reads as a data problem.** A user whose row sat
at index 250 saw "Historical" on a name whose market was perfectly well supported, next to rows that
were live. Every available explanation on screen (market coverage, provider outage, symbol support)
was wrong, and the true cause — where the row happened to sit in an array — was not representable in
the UI at all.

**The miss-counter interaction is the subtle part, and it is why rotation is safe.** TerminalShell
evicts a previously-good quote after 3 consecutive null polls. Under rotation a symbol is simply
absent from the polls it sits out rather than returning null, so its eviction window stretches to 3
full cycles instead of ~18s. That is strictly *less* flap-prone, never more — but only because the
counter is driven by the keys the response actually carries. A future change that counted misses
against the REQUESTED set instead would invert this and start evicting every rotating symbol.

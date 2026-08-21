---
key: BASKET-OHLCV-STORE-SELF-MAINTAINS
question: >
  A ticker leaves the basket OHLCV fetch universe when an index reconstitution drops it from
  the nightly-repulled finviz screener. Today nothing refetches it, so its parquet freezes on
  disk forever while engine/stage_analysis.build_universe() — which globs the store — keeps
  classifying it as a live name. What is the retirement contract: keep fetching it, or mark
  it inactive?
answer: >
  BOTH, split by whether an exit is RESOLVED. The deep store SELF-MAINTAINS: every ticker
  already on disk stays in the fetch universe (`--store`), so leaving an index can no longer
  freeze a file. The ONLY lawful way out of the fetch universe is a resolved exit row in
  config/delisted_symbols.yml, which `_resolve_universe` subtracts from every DERIVED leg
  (membership, finviz, store) while still honouring an operator's explicit --tickers. A
  resolved exit is additionally stamped `retired` by build_universe() and forced
  `stage_current=False`, so it keeps no current authority — disclosure, never deletion.
rationale: >
  The two dispositions have opposite cures and were being conflated into one silent freeze.
  A vendor probe of the 2026-07-10 drop-out cluster returned a CURRENT tape for 10 of 10
  sampled names (ARWR/AXSM/BBIO/BE/AAOI/ALDX/BARK/BOOM/ACNT/AHR), so those tapes were never
  dead — merely unrequested; the cure is to request them, and it is self-healing within one
  nightly. Only ~13 of the 179 orphans carried even a HINT of a genuine exit, so making
  "dropped by an index" mean "retired" would have retired ~166 live companies. Conversely a
  security that stopped existing can never return, and requesting it nightly forever parks a
  permanent entry in the missing-symbol warning — the fatigue argument config/delisted_symbols.yml
  already makes. Resolution stays a CURATED act with SEC receipts (#4622 protocol: NASDAQ
  directory absence + Form 25/25-NSE); the census only surfaces the queue, it never infers an
  exit from a vendor null, because a vendor says "possibly delisted" about live securities too.
  Monotonic growth of the store leg is bounded by that ledger acting as the drain, and the
  census names the undrained tail so it stays visible rather than accumulating silently.
alternatives:
  - option: Keep fetching everything on disk, with no exit-ledger subtraction
    why_not: >
      Requests dead symbols nightly forever. config/delisted_symbols.yml exists precisely to
      stop that: a permanently-on warning is one nobody reads when the next real outage lands.
  - option: Retire any name that leaves the fetch universe (mark its file inactive)
    why_not: >
      Falsified by measurement. 179 orphans, but a live probe found 10/10 of the sampled
      2026-07-10 cluster still trading and only ~13 with any exit hint — this would have
      retired ~166 live companies on an index-membership accident.
  - option: Infer retirement automatically from a vendor returning no data
    why_not: >
      Yahoo says "possibly delisted" about live securities whose symbol merely changed
      (TCNNF, actually an uplisting to NYSE:TRLV), and static vendor metadata outlives real
      delistings (#4616). A HINT is not resolution; the ledger's protocol requires receipts.
  - option: Drop retired tickers from build_universe() entirely
    why_not: >
      Fail-dark. The ledger's own contract is that a delisting is DISCLOSED, not disappeared —
      the store keeps its history and the page keeps its deep links (CSP-R1). Dropping the key
      blanks a browseable name instead of labelling it.
  - option: Parameterise the census from the fetch call's own arguments
    why_not: >
      The #776 lesson. A census tied to the fetch's argv goes blind at exactly the moment the
      fetch loses a universe — the failure it exists to catch. The maintained filters are
      DECLARED in-module (MAINTAINED_FINVIZ_FILTERS) and resolved independently.
evidence:
  - "2026-08-20 store census: 2,782 parquet files, 183 stale, 179 outside `membership ∪ finviz(idx_ndx, idx_rut)`; 2,599/2,599 fresh files inside the universe and 0 orphans fresh — separation is exact, not approximate"
  - "Stale-date histogram: 2026-07-10 -> 110 files, 2026-07-21 -> 35, 2026-06-29 -> 9 — a reconstitution drop-out, far too clustered for simultaneous delistings"
  - "Live yfinance probe 2026-08-20: ARWR/AXSM/BBIO/BE/AAOI/ALDX/BARK/BOOM/ACNT/AHR all returned a tape through 2026-08-20 while their store files sat frozen at 2026-07-10; TMHC/SILA/AVNS returned nothing (genuine tape ends)"
  - "Real fetch, ARWR/AXSM/BBIO: 2026-07-10 -> 2026-08-20, +26/+26/+26 rows — the freeze is fully recoverable by requesting the name"
  - "_resolve_universe([], finviz, True, True) = 2,781 vs 2,602 without --store: exactly the 179 orphans re-enter, and the one resolved exit (AVB) stays out"
  - "scripts/fetch_basket_ohlcv.py::_resolve_universe / _store_tickers / MAINTAINED_FINVIZ_FILTERS"
  - "engine/stage_analysis.py::build_universe — `retired` stamp; build_context_feed forces stage_current=False"
  - "tests/test_basket_ohlcv_freshness.py, tests/test_stage_analysis.py (retirement + drift block)"
affects:
  - "scripts/fetch_basket_ohlcv.py"
  - "scripts/collect.py"
  - "engine/stage_analysis.py"
  - "config/delisted_symbols.yml"
confidence: high
reversibility: easy
decided_by: session claude/basket-ohlcv-universe-drift
decided_at: 2026-08-20
---

## Why this is the upstream cure, not more containment

Wave 8 (`research/STAGE_OBSERVATION_TRUTH_WAVE8.md`) already stops a frozen name from
carrying current authority, via the target Stage week and the `stage_current` admission
boundary. That is containment: the bad data still arrives, and the boundary refuses it.

This decision stops the bad data being produced. The two are complementary and both stay —
containment is what protects the product on the night a collector breaks for a reason nobody
predicted, and no upstream fix retires that need.

## The three dispositions, and why they are kept apart

The census now reports every file in the store under exactly one of:

| Disposition | Meaning | Cure |
|---|---|---|
| `stale` | sponsored by an active membership row or a declared index universe, and lagging | an OUTAGE — a broken pull. Alarm. |
| `unsponsored` | on disk, lagging, claimed by no membership row and no declared index | `--store` keeps fetching it, so a live tape self-heals by the next nightly; what persists has a STOPPED tape and needs re-sponsorship or an exit row |
| `retired` | a resolved exit row exists | disclosed with its receipt, excluded from every alarm at any lag |

They are separate because their cures are opposite, and because collapsing them is what
produced the failure: the old census asked only the 702 active members, so on a store of
2,782 files holding 183 stale ones it reported `n_stale: 1`.

`status` stays bound to the sponsored plane on purpose. The genuinely-stopped tail of
`unsponsored` can only be cleared by curating exit rows, and a top-line status that stays red
until someone does is a status nobody reads — the same warning-fatigue argument the exit
ledger makes about never requesting a dead symbol forever. Orphans get their own annotation
and their own counts instead.

## The AVB shape — why freshness alone cannot classify

AvalonBay was acquired 2026-08-17 and already had a well-formed exit row in
`config/delisted_symbols.yml` on 2026-08-20. Its store tip read 2026-08-19 — ONE session
behind the max, under the staleness threshold — because the vendor flat-forwards a dead
symbol as 0-volume repeats of its last real close (2026-08-14). Nothing read the ledger, so
it was days from becoming BLD's permanent unexplained red line for the second time.

Two consequences are now pinned by test:

1. A resolved exit is disclosed at ANY lag, and never reaches an alarm bucket.
2. The census reports the true `last_session` next to the store tip, so padding reads as
   padding instead of being trusted as trading.

The same padding is why `stage_current` is forced False for a retired name rather than left
to the week comparison: flat-forwarding can push a dead symbol's completed week up to the
target week, and a mid-week delisting has a matching completed week anyway. On the week test
alone, both shapes read as current — a company that no longer exists ranking beside live ones.

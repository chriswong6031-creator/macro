---
key: A-GLOBBED-STORE-NEVER-FORGETS-A-TICKER
claim: >
  A consumer that builds its universe by globbing a per-ticker store keeps classifying every
  file ever written, forever — so when the PRODUCER's universe silently shrinks, the two
  disagree permanently and nothing in either half reports it.
falsifier: >
  Compare producer and consumer universes directly. If
  `set(p.stem for p in (data_dir/"baskets/ohlcv").glob("*.parquet"))` equals
  `scripts.fetch_basket_ohlcv._resolve_universe([], _finviz_tickers(["idx_ndx","idx_rut"]), True, False)`
  then producer and consumer agree and the claim is refuted. On 2026-08-20 they differed by
  179 names, all of them stale.
so_what: >
  When auditing any glob-built universe, never audit the two halves separately — the defect
  lives in the DIFFERENCE and is invisible from inside either one. The producer looks healthy
  (it fetched everything it was asked for), the consumer looks healthy (it classified
  everything on disk), and the freshness tripwire between them can be green while a sixth of
  the store is frozen. Ask what the producer no longer maintains that the consumer still reads.
kind: architecture
verified_at: 2026-08-20
verified_by: >
  scripts/fetch_basket_ohlcv.py::_resolve_universe vs engine/stage_analysis.py::build_universe
  (`for p in ohlcv_dir.glob("*.parquet"): _add(p.stem, "ohlcv")`); measured 2,782 store files
  vs a 2,603-name fetch universe, 179 orphans, 179/179 stale and 0/179 fresh
scope:
  - "macro"
  - "scripts/fetch_basket_ohlcv.py"
  - "engine/stage_analysis.py"
  - "data/baskets/ohlcv/**"
confidence: verified
---

## The shape, stated generally

Producer maintains universe **P**. Consumer reads store **S** by glob. Every write puts a name
into S; nothing ever removes one. So S grows to `S ⊇ ∪(P over all time)`, and the live defect
set is `S \ P_today` — names the consumer still treats as live and the producer no longer
refreshes.

That set is invisible from either side:

- The producer reports success: it fetched every name it was asked for.
- The consumer reports success: it classified every file it found.
- A freshness tripwire censusing a SUBSET of P (here: 702 active members out of 2,603) reports
  on names that are, by construction, the ones still being maintained.

The store-wide aggregate `as_of` is no help either — it is a max over the store, so one fresh
file certifies the whole set. Only the explicit set difference finds it.

## Why the separation was so clean, and why that is the tell

Measured 2026-08-20: 2,599 of 2,599 fresh files were inside the fetch universe, and 179 of 183
stale files were outside it — with **zero** orphans fresh. A near-perfect partition between
"in the producer's universe" and "current" is not a coincidence to be explained away; it is
the signature of this defect. Genuine delistings scatter across dates and sit inside the
maintained set (the 4 stale-and-inside names were exactly that: one real delisting, one broken
pull, two ordinary one-session jitter). A 110-file cluster on a single date is a membership
event, not a market event.

## The corroborating probe

A live vendor probe distinguishes the two hypotheses in one call, and should be run before
attributing a cluster to delistings: fetch a recent window for a sample of the frozen names.
On 2026-08-20, 10 of 10 sampled names from the 2026-07-10 cluster returned a tape through the
current session while their store files sat 29 sessions behind — the tapes were never dead,
merely unrequested.

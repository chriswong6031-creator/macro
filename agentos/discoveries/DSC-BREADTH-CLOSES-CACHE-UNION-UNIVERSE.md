---
key: BREADTH-CLOSES-CACHE-UNION-UNIVERSE
claim: >
  data/breadth/_closes_cache.parquet is column-append-only (collectors/breadth.py:390
  `fresh.combine_first(cached)`, documented at :208-210 as a deliberate
  survivorship-honest archive) — a roster removal never drops that ticker's column, it
  just stops refreshing it. `compute()` (:580 `out["n_members"] = valid.sum(axis=1)`)
  counts every column in that UNION frame that has a price on the date, not the
  roster-intersected set. So the nightly breadth tail is recomputed against a universe
  that can exceed the CURRENT roster size whenever a just-removed name still has recent
  prices. Measured on the 2026-08-19 RDDT/VMRK-for-AVB/EQR S&P 500 swap:
  _closes_cache.parquet grew 510->512 columns (RDDT, VMRK added; AVB, EQR RETAINED, not
  dropped), while data/breadth/constituents.parquet stayed at 503 rows (a 2-for-2
  swap). `engine.neuralweb.market_memory_breadth_observation`'s priced-member-coverage
  bound (:80 `_MIN_PRICED_COVERAGE = 0.90`, enforced against an upper bound of 1.0 at
  :898) assumes `n_members <= len(constituents)` — an assumption the union universe
  does not honor the moment a removed name still prices on the tip date.
falsifier: >
  A roster removal whose name keeps pricing on/after the swap date that does NOT
  breach the coverage<=1.0 bound. Concretely: pick any future S&P 500 removal, confirm
  the removed ticker's column in data/breadth/_closes_cache.parquet still carries a
  price for at least one session on or after the roster's effective swap date, and
  recompute priced_member_coverage = tip-day n_members / len(constituents.parquet) for
  that session. If that ratio is <= 1.0 the claim is false — the union-universe
  mechanism either was not the cause, or something already intersects the count
  against current membership before this bound sees it.
so_what: >
  Before (or as part of) any future roster swap lands, the breadth collector or the
  projector must stop treating `n_members` as "priced AND currently a member" when it
  is really just "priced, ever a member since the cache existed". Two independently
  correct designs are colliding: collectors/breadth.py:208-210 deliberately never
  prunes history (survivorship-honest replay/backtest archive,
  research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md), while
  market_memory_breadth_observation.py:80,898 deliberately bounds priced-member
  coverage at <=1.0 as a sane-input gate. Neither is wrong on its own, but nothing
  reconciles them: the fix belongs on the READ side (collectors/breadth.py's
  `compute()` should count `valid & is-current-member`, or the projector should
  compute coverage against the roster-intersected universe) — never by widening the
  bound, which would just let a real data corruption (a duplicated column, a stale
  roster read) through silently. A second, independent PR (#5941) landed a fixture
  detach fix for the same symptom (test_market_memory_breadth_observation.py /
  test_market_memory_breadth_store.py half-freezing their inputs); that fix keeps the
  tests from breaking on this mechanism again, but does not touch the collector, so
  the production bound stays live and will trip again on the next roster swap where
  the removed name still prices past the swap date, exactly as it did here.
kind: architecture
verified_at: 2026-08-19
verified_by: >
  collectors/breadth.py:390 (`merged = fresh.combine_first(cached)` inside
  `_merge_refreshed`), :208-210 (`disclose_stale_constituent_columns` docstring naming
  the union-preserving combine_first a deliberate feature, citing
  research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md), :505 (`out =
  {"breadth": self.compute(closes)}` — compute() runs on the merged/union frame, not a
  roster-filtered one), :580 (`out["n_members"] = valid.sum(axis=1)` over that whole
  frame); engine/neuralweb/market_memory_breadth_observation.py:80
  (`_MIN_PRICED_COVERAGE = 0.90`) and :898 (`if not _MIN_PRICED_COVERAGE <=
  priced_member_coverage <= 1.0`); measured directly via `git cat-file blob
  93ab221b81dd:data/breadth/_closes_cache.parquet` (510 cols) vs `git cat-file blob
  6396879978b8:data/breadth/_closes_cache.parquet` (512 cols, new columns {RDDT,
  VMRK}, AVB and EQR both still present) and live
  data/breadth/_closes_cache.parquet: AVB last priced 2026-08-14, EQR last priced
  2026-08-17, cache tip 2026-08-18, constituents.parquet at 503 rows throughout.
scope:
  - macro
  - data/breadth/_closes_cache.parquet
  - collectors/breadth.py
  - engine/neuralweb/market_memory_breadth_observation.py
  - engine/neuralweb/market_memory_actual_output_store.py
confidence: verified
---

## Why this stayed invisible until now

The union-preserving cache and the <=1.0 coverage bound were each built for a good
reason, on different sides of the same store, by work that never had to reason about
the other. `disclose_stale_constituent_columns` (collectors/breadth.py:205-225) already
watches for the ADJACENT failure mode — a CURRENT member whose column silently stops
refreshing (CWEN-A class) — but it only classifies names still IN `members_symbols`;
a name that just left the roster is invisible to it by construction ("a name Wikipedia
already dropped is correctly gone — no disclosure owed there", :215). Nothing sits on
the other side of that boundary watching a JUST-REMOVED name that is still fresh.

It surfaced now only because two conditions lined up for the first time since the
coverage bound shipped: a roster swap (RDDT/VMRK for AVB/EQR, effective 2026-08-19 —
see the SEC 8-Ks for the EQR/AVB "Vivmark Residential" merger closing 2026-08-17,
classified in data/special_situations/classify_cache/0001193125-26-354068.json) landed
while BOTH removed names still had prices inside the coverage-relevant window (AVB
through 08-14, EQR through 08-17 — both after the observation module's own frozen
fixture session of 2026-08-07). A swap where the outgoing names had already gone stale
weeks earlier would not have tripped this at all — coverage would sit comfortably
under 1.0 because the stale columns' most-recent-price dates fall outside whatever
window the reader cares about.

Two full-CI test files (tests/test_market_memory_breadth_observation.py,
tests/test_market_memory_breadth_store.py) were reading the frozen breadth tail
against the LIVE constituents roster — an accidental half-freeze that made the drift
visible as 26 test failures rather than a silent production wobble. #5941 fixed that
specific symptom by freezing both inputs together from one committed era; it
deliberately does not touch the collector or the bound, because the real fix is a
roster-intersection at read time and that belongs to whoever owns
`collectors/breadth.py` next, with nightly's own data/ writes as the only legitimate
path to change what the store contains.

Related: the same union-vs-current-membership shape that
[[DSC-HK-DEEP-PANEL-SPLICES-ADJUSTMENT-VINTAGES]] describes for the HK deep panel — an
archive-honest collector store and a downstream reader that assumes something the
store never promised. Also related at the architecture level:
[[DSC-MERGE-GATE-IS-GATED-ON-MOVING-DATA]] — this finding is one concrete instance of
the broader class that DSC names: a merge-gate job asserting against a committed data
tree the nightly rewrites out from under it.

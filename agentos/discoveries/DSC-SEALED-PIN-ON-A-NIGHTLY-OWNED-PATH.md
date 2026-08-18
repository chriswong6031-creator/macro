---
key: SEALED-PIN-ON-A-NIGHTLY-OWNED-PATH
claim: >
  `scripts/stock_identity_build_w1a1.py` seals `data/baskets/ohlcv/B.parquet` with an
  EXACT digest (`B_SOURCE_PREFIX_SHA256`, hashing each OHLCV value as `float(v).hex()`),
  but that path is rewritten by the nightly `data: daily collection` lane, and the lane is
  not BIT-REPRODUCIBLE over history. Measured on origin/main 2026-08-18 against the
  registration commit 6d04e9b3100a: inside the sealed prefix (`index <= 2026-08-13`) the
  row count is still exactly 3172 and the max date still 2026-08-13, yet 2,373 rows
  from 2014-01-02 through 2026-02-25 have different open/high/low/close — by a relative
  ratio of 0.9999991 to 1.0000007, i.e. ~1e-7, float rounding rather than an economic
  restatement (116 distinct ratios; values from 2026-02-26 onward are bit-identical).
  One volume cell also changed, at 2026-08-13.
falsifier: >
  A rewrite of that path whose pre-ASOF OHLCV values are bit-identical to the previous
  revision, or a `ci.yml` run on a main descendant in which `ci-pack-3` /
  `trial-budgets: stock-identity atlas guards` is green without the registration having
  been changed. Reproduce with:
  `git show 6d04e9b3100a:data/baskets/ohlcv/B.parquet` vs `git show origin/main:…`,
  slice `index <= 2026-08-13` on both, and diff the five OHLCV columns.
so_what: >
  The guard is behaving CORRECTLY — an exact digest over a non-bit-reproducible producer
  must eventually trip, and this one did. The failure text names only a hash
  (`B source logical prefix differs from registration: a77fdc41…`), which reads as "someone
  edited a curated file" and sends a diagnosing session hunting for an edit that does not
  exist. Two wrong diagnoses are easy to reach and both were reached and discarded here:
  it is NOT append-intolerance (`_validate_b_source` slices `index <= ASOF` BEFORE hashing,
  so appends cannot break it, and the row/date receipt check confirms 3172 rows survived),
  and it is NOT a price restatement (the deltas are ~1e-7, not a split or dividend
  re-adjustment).
  Consequence: fleet-blocking. Red on main's own workflow_dispatch baseline 32100795267
  with no PR involved, and on independent heads #5851/#5852/#5853; `ci-gate` requires every
  pack green. It bites authority-changing PRs hardest — sibling-head attribution does not
  excuse those, so they need a GREEN `ci.yml` on a main descendant, which cannot exist while
  this stands.
  Do NOT simply re-stamp the digest: that re-arms the same trap for the next rewrite. The
  adjudication belongs to Stock Identity and is a choice between making the pin
  tolerance-aware (hash rounded values, or compare within an epsilon), snapshotting the
  sealed plane into a namespace the nightly cannot write, or making the producer
  bit-reproducible.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  scripts/stock_identity_build_w1a1.py:86 (B_SOURCE_RELATIVE_PATH), :140
  (B_SOURCE_PREFIX_SHA256), :204-222 (_ohlcv_prefix_sha256 — `float(v).hex()` per value),
  :493-505 (_validate_b_source — slices `index <= ASOF` before hashing);
  tests/test_stock_identity_atlas.py:1391-1401;
  `git log … -- data/baskets/ohlcv/B.parquet` → 93ab221b81dd + 59ccb9c774c8
  ("data: daily collection 2026-08-18", 2026-08-17) over 6d04e9b3100a (#5632);
  `git log … -- scripts/stock_identity_build_w1a1.py` → 214b0bf39689 (#5660);
  direct parquet diff of the two blobs (3172 vs 3172 prefix rows; 2373 changed OHLC rows,
  ratio range 0.9999991367..1.0000006843, last changed 2026-02-25, first unchanged
  2026-02-26); main baseline 32100795267 ci-pack-3 log naming
  test_b_source_is_exactly_the_registered_curated_plane as the single failure.
scope: [macro]
confidence: verified
---

## Detail

Both programs are individually reasonable. Stock Identity W1-A1 needs a frozen source so
its sealed fingerprint/state/episode artifacts are reproducible, and it correctly wrote the
validator to be append-tolerant. The nightly owns `data/baskets/ohlcv/` and refreshes every
basket constituent each session. What neither side accounted for is that the refresh is not
bit-stable over HISTORY: re-deriving an adjusted series reproduces the same numbers to ~7
significant figures, not to the last bit, and an exact digest cannot tell that apart from
tampering.

The sharp boundary is the useful clue for whoever picks this up: everything on or before
2026-02-25 moved, everything from 2026-02-26 on is bit-identical. That is the shape of an
adjustment factor applied to pre-event history being recomputed slightly differently, not
of a wholesale re-fetch.

The general shape is worth carrying beyond this ticker: **an exact byte/value digest is
only safe over an artifact whose producer is bit-reproducible, or over a path no scheduled
lane writes.** Before sealing, check `git log -- <path>` for producer commits
(`data: daily collection`, `render:`, `engine-render:`); if any appear, either snapshot the
artifact into the sealing program's own namespace or give the digest an explicit tolerance.

Found while shipping [[BOARD-RECOMMIT-IS-NOT-A-BOARD-ADVANCE]] (PR #5852), whose merged
head cannot obtain the green-descendant proof its authority-changing status requires until
this is adjudicated.

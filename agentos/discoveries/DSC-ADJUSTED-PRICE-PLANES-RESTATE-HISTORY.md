---
key: ADJUSTED-PRICE-PLANES-RESTATE-HISTORY
claim: >
  A total-return ADJUSTED price plane restates its entire history on every
  dividend, so no digest of its historical values is durable — not even one
  deliberately scoped to a frozen prefix. data/baskets/ohlcv is adjusted
  (`auto_adjust=True`, per data/stock_identity/ohlcv/manifest.json). Measured
  2026-08-18 on B.parquet against the first nightly after PR #5660 registered
  B_SOURCE_PREFIX_SHA256: within the sealed 2014-01-02..2026-08-13 window,
  2373 of 3172 rows moved on ALL FOUR price columns, by up to 8.633e-07
  relative. Row count (3172) and index.max() were unchanged, so the shape
  asserts passed and only the digest fired. Volume moved on exactly one row,
  the ASOF session itself (10,621,100 -> 10,625,700, +0.043%) — a same-day
  consolidated-tape finalization. Both changes are economically meaningless and
  byte-fatal. A tolerance cannot rescue a hash: quantizing only moves the
  rounding cliff, and rounding to 10, 9, 8, 7, 6, 5 and even 4 significant
  figures still left the two versions unequal, because with 3172x4 values some
  always straddle a boundary.
falsifier: >
  Re-run `python -m pytest tests/test_stock_identity_atlas.py -q` against a
  checkout whose data/baskets/ohlcv/B.parquet predates a dividend and observe
  `_ohlcv_prefix_sha256` on the <=ASOF slice equal to the value computed after
  one. Or show the diff is confined to appended rows:
  `python3 -c "import pandas as pd; o=pd.read_parquet('old.parquet'); n=pd.read_parquet('new.parquet'); a=pd.Timestamp('2026-08-13'); print((o.loc[o.index<=a]!=n.loc[n.index<=a]).sum())"`
  — a durable prefix requires all zeros. Fix shipped in
  scripts/stock_identity_build_w1a1.py:_validate_b_source.
so_what: >
  Never pin a byte/hash receipt to a path a scheduled lane writes, and never
  assume a nightly only APPENDS — an adjusted plane rewrites backwards. Check
  BOTH `git log -- <path>` for producer commits AND the plane's adjustment mode
  before sealing. The correct fix is an immutable snapshot committed under the
  owning program's namespace, NOT a re-stamp of the constant (which blesses
  whatever the lane last wrote, destroying the signal the guard exists to
  raise) and NOT a tolerance (impossible for a digest). Here the pre-nightly
  prefix still reproduced the registered hash byte-for-byte, so sealing it left
  the registration untouched and blessed nothing. Note the program-owned plane
  was NOT a legal home: registration §1 gates it to names absent from both
  curated planes, and the builder explicitly prohibits a duplicate
  data/stock_identity/ohlcv/B.parquet — so the snapshot lives outside the plane
  map entirely.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  Reproduced the fleet-blocking red locally on a full checkout (`worktree_sparse
  add data`): tests/test_stock_identity_atlas.py 1 failed / 93 passed, failing
  `test_b_source_is_exactly_the_registered_curated_plane` with actual
  a77fdc41... vs registered 6d8988fc.... Diffed B.parquet at 6d04e9b3100a (the
  #5632 seed) against origin/main. Confirmed the pin-era <=ASOF slice hashes to
  6d8988fc... exactly, sealed it to
  data/stock_identity/w1a1/ohlcv/b_source_prefix.parquet, verified the parquet
  round-trip preserves float64 bit-for-bit, and re-ran the whole CI step
  (`stock-identity atlas guards`, 7 files): 249 passed. Shipped by PR #5865.
scope:
  - macro
  - scripts/stock_identity_build_w1a1.py
  - data/baskets/ohlcv
  - engine/stock_identity/plane.py
confidence: verified
---

Found while repairing the 2026-08-18 fleet-wide main red. PR #5863 diagnosed the
collision correctly (a sealed pin on a nightly-written path) and correctly
declined to guess a fix from outside Stock Identity. This record adds the part
that decides WHICH fix: the plane is adjusted, so the breakage is not a one-off
collision but a guarantee, and the two obvious repairs are both wrong.

The `ohlcv` leaf in the sealed path is load-bearing rather than cosmetic: the
zero-authority sweep in `tests/test_stock_identity_atlas.py` exempts OHLCV
directories because raw price bars carry no authority columns, and this artifact
is exactly such a frame. It is not registered in `PLANE_DIRS`, so it does not
compete in the §1 precedence order.

The second red on main that day, `unrun-government-revenue`, looked like the
same class and was NOT — see [[NIGHTLY-LANE-ORDER-DECIDES-LEDGER-COMPLETENESS]].

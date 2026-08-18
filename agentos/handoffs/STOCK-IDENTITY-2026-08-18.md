---
workstream: "WS:STOCK-IDENTITY"
session: claude/stock-identity-b-prefix-receipt
model: opus
ended_because: complete
prs: [5865]
decisions: ["DEC:SI-REGISTERED-B-PREFIX-IS-A-FROZEN-SNAPSHOT"]
discoveries: ["DSC:BASKET-OHLCV-REWRITES-HISTORY-NIGHTLY"]
mission: >
  Heal the fleet-wide red on the `stock-identity atlas guards` CI step
  (test_b_source_is_exactly_the_registered_curated_plane), inherited from main by
  every open PR, without re-stamping a receipt that is structurally unstable.
state_before: >
  B_SOURCE_PREFIX_SHA256 in scripts/stock_identity_build_w1a1.py pinned an exact
  sha256 over the OHLCV prefix (2014-01-02..2026-08-13, 3172 rows) of the LIVE
  data/baskets/ohlcv/B.parquet. That file is rewritten every collection night, so
  the pin had been red on main since the 2026-08-17 21:01 collection. No lane was
  claimed: `gh pr list --search stock_identity_build_w1a1` and
  `--search B_SOURCE_PREFIX_SHA256` both returned empty, and no PR carried
  label:main-red-repair.
changed:
  - path: data/stock_identity/source/b_registered_prefix_v1.parquet
    what: >
      NEW immutable snapshot of the registered prefix, extracted from seed commit
      6d04e9b3. file sha256 d401e217…; its _ohlcv_prefix_sha256 is 6d8988fc…,
      identical to the pre-existing registered pin.
  - path: data/stock_identity/source/b_registered_prefix_v1.json
    what: >
      Provenance sidecar, doubling as the store's zero-authority manifest
      (schema stock_identity.registered_prefix_manifest.v1).
  - path: scripts/stock_identity_build_w1a1.py
    what: >
      Added B_SNAPSHOT_* constants and the B_LIVE_PRICE_REL_TOL=1e-5 /
      B_LIVE_VOLUME_REL_TOL=1e-2 bands; split _validate_b_source into
      _load_registered_b_prefix (exact receipts against the immutable snapshot) and
      _validate_live_b_plane_tracks_registration (tolerance tripwire on the live
      plane). B_SOURCE_PREFIX_SHA256 itself is UNCHANGED.
  - path: tests/test_stock_identity_atlas.py
    what: >
      Added SNAPSHOT_READY gate, a snapshot-immutability test, a tripwire test
      (tolerates 5e-7 scaling, raises on a 1% close move), the _RAW_PRICE_DIRS
      named exemption, and a coverage test requiring every exempted raw-price
      parquet to have a zero-authority manifest.
verified:
  - claim: The exact CI step that was red is green on the rebased tree.
    command: >
      python3 -m pytest tests/test_stock_identity_partition.py
      tests/test_stock_identity_fingerprint.py
      tests/test_stock_identity_state_episodes.py tests/test_stock_identity_atlas.py
      tests/test_audit_reused_tickers.py tests/test_stock_identity_replay.py
      tests/test_stock_identity_replay_leak.py -q
    result: 252 passed
  - claim: The seed commit reproduces the registered digest exactly, so nothing is re-stamped.
    command: >
      _ohlcv_prefix_sha256 over `git show
      6d04e9b3100af7afaf834ceb2c9c307a48808f0b:data/baskets/ohlcv/B.parquet`
      prefix, compared with B_SOURCE_PREFIX_SHA256
    result: both 6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db
  - claim: The live plane is rewritten nightly, so an exact pin on it cannot hold.
    command: >
      same digest over commits 59ccb9c774c8 and 93ab221b81dd (2026-08-17 21:01 and
      21:21), plus grep of scripts/fetch_basket_ohlcv.py:369,450
    result: >
      2f4d9467… then a77fdc41… — two different digests 21 minutes apart;
      yf.download(auto_adjust=True) + new.combine_first(prior) confirmed
  - claim: Quantize-then-hash would still break, so it is not a safe alternative.
    command: >
      counted value flips between consecutive nightly versions under
      np.round(v, dp) for dp in (2,3,4,6)
    result: "2dp=1 flip on BOTH night pairs; 3dp=16/24; 4dp=236/243; 6dp=8673/9161"
  - claim: The tolerance band separates vendor noise from a real revision by ~2400x.
    command: >
      max relative price delta snapshot-vs-live, compared with one cent at the
      plane's minimum price
    result: "noise 8.63e-07 vs 2.08e-03 at min price 4.81; band 1e-5 sits between"
  - claim: The new authority coverage test actually bites.
    command: >
      removed the sidecar, then set authority.can_rank true, re-running
      pytest -k raw_price_parquet_is_covered each time
    result: FAILED in both cases; 104 passed once restored
  - claim: B_SOURCE_PREFIX_SHA256 is the only exact digest pinned on this plane repo-wide.
    command: >
      grep -rn "baskets/ohlcv" over engine/ scripts/ tests/ filtered for
      sha/digest/hash, plus grep of the r2_delivery_macro_* census fixtures
    result: no other pin; all remaining references are readers
  - claim: AgentOS records are schema-valid.
    command: python3 scripts/agentos.py validate
    result: 0 errors (10 pre-existing phantom-owns-path warnings, none new)
unverified:
  - claim: The tripwire will stay green across future collection nights.
    what_would_verify: >
      Re-run the atlas guards after the next `data: daily collection` commit
      touching data/baskets/ohlcv/B.parquet and confirm the max relative delta
      stays under 1e-5. Only three collection commits exist for this file so far
      (2026-08-14 seed, 2026-08-17 x2), so the 8.63e-07 noise ceiling rests on two
      night-pairs, not a long series.
  - claim: Other baskets behave like B.
    what_would_verify: >
      The same per-night digest comparison on other tickers. AAPL and A were
      reported with the same shape in the incident brief but were not
      independently re-measured in this session.
unresolved:
  - >
    The vendor churn ceiling (8.63e-07) is measured from two night-pairs on one
    ticker. If a future night exceeds 1e-5 without a real corporate action, the
    band is too tight and should be re-derived from a longer series rather than
    widened reflexively.
next_actions:
  - >
    None for this red. If the tripwire ever fires, do NOT widen the band as a
    reflex: first check whether the live plane took a genuine corporate action or
    restatement (a split shows as a single constant ratio across all rows; vendor
    churn shows as thousands of distinct near-1.0 per-row factors).
  - >
    W2 (PR #5643) is still in flight and is removing the prohibited duplicate
    data/stock_identity/ohlcv/B.parquet plane. That is unrelated to this snapshot,
    which lives under data/stock_identity/source/ and is a registration input.
do_not_redo:
  - >
    Do NOT re-stamp B_SOURCE_PREFIX_SHA256 to a fresh value. It moved twice in 21
    minutes on 2026-08-17; a re-stamp is red again the next collection night.
  - >
    Do NOT "fix" scripts/fetch_basket_ohlcv.py to stop re-deriving history. The
    re-adjustment is vendor-side (yfinance auto_adjust) and legitimate; the full
    re-download is also what purges prior vendor garbage via _scrub_placeholder_prices.
  - >
    Do NOT replace the exact digest with a quantized/rounded hash. Measured: 2 dp
    still flips a value on both consecutive night pairs.
  - >
    Do NOT add authority_* columns to the snapshot parquet. _ohlcv_prefix_sha256
    hard-requires exactly [open, high, low, close, volume]; extra columns break the
    registration. The block rides on the sidecar manifest.
  - >
    Do NOT move the snapshot to data/stock_identity/ohlcv/B.parquet. The builder
    hard-fails on that path as a prohibited duplicate B plane.
danger_areas:
  - >
    data/baskets/ohlcv/*.parquet is NOT append-only. Any exact hash pinned on
    anything under it is a guaranteed nightly fleet red.
  - >
    data/stock_identity/ is swept by TestZeroAuthority via DATA.rglob: any new JSON
    or parquet added there must carry an all-false authority block, or (for raw
    price history) a covering manifest plus a _RAW_PRICE_DIRS entry.
  - >
    The tests are skipif-gated on file existence (PREREQUISITE_READY /
    SNAPSHOT_READY), so in a sparse worktree without data/ they SKIP rather than
    fail. A green local run in a sparse tree proves nothing about this surface —
    run `python3 scripts/worktree_sparse.py add data` first.
---

## The one-line version

`data/baskets/ohlcv/*.parquet` is not an append-only tape. The nightly collector
re-downloads full history and the vendor re-derives its cumulative adjustment
factor, so an exact digest pinned on any file under that directory is a
guaranteed fleet red on the next collection night.

The registered W1-A1 B prefix now lives in immutable program-owned storage, whose
digest is byte-identical to the original registration — so the receipt is stable
by construction rather than by luck, and nothing registered was re-stamped. The
live plane is still watched, by a tolerance band rather than an equality check.

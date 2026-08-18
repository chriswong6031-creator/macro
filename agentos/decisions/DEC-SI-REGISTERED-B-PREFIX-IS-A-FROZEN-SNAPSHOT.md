---
key: SI-REGISTERED-B-PREFIX-IS-A-FROZEN-SNAPSHOT
question: >
  The W1-A1 registered B price prefix was pinned by exact sha256 against the live
  data/baskets/ohlcv/B.parquet, which the nightly collector rewrites. Do we make the
  receipt precision-tolerant, make the collector deterministic, or move the registered
  prefix off the live plane entirely?
answer: >
  Move it off the live plane. The registered 2014-01-02..2026-08-13 prefix is frozen as
  an immutable program-owned snapshot at data/stock_identity/source/
  b_registered_prefix_v1.parquet, extracted from the seed commit 6d04e9b3, and the
  builder consumes THAT. The exact digest B_SOURCE_PREFIX_SHA256 is unchanged
  (6d8988fc…) and is now enforced against the snapshot, which nothing rewrites. The
  live plane keeps a revision tripwire: same session set, price moves within 1e-5
  relative, volume within 1e-2, else SystemExit demanding re-adjudication.
rationale: >
  Establishing WHICH failure this is came first, because the two obvious fixes are
  correct in mutually exclusive worlds. It is not a repo reproducibility bug: the
  rewrite is vendor-side (yfinance auto_adjust recomputing a cumulative dividend
  factor at ~7 significant digits), so "make the collector deterministic" would mean
  freezing vendor output — which IS the snapshot, arrived at by a longer road.
  And a precision-tolerant hash was falsified by measurement, not by argument:
  rounding to 2 dp before hashing still flips 1 of 12688 values on BOTH consecutive
  night pairs (3 dp: 16-24; 4 dp: 236-243), because a ~1 ULP move near a rounding
  boundary crosses it. That trades a certain nightly red for a flaky one — strictly
  worse to diagnose. Freezing the input is the only option that makes the receipt
  stable BY CONSTRUCTION rather than by luck, and it is also the honest one: a
  registration should name the bytes it was computed on, not whatever the vendor
  last returned. Because the seed commit still reproduces the registered digest
  exactly, this relocation re-stamps NOTHING — no registered constant, no sealed
  receipt, no generated output moves — which is what distinguishes it from the
  re-stamp the same red would otherwise have invited. The live plane is not
  abandoned: the tripwire still fires on a real revision, with a ~2400x separation
  between the 8.63e-07 vendor noise floor and a one-cent revision at 2.08e-03.
alternatives:
  - option: Re-stamp B_SOURCE_PREFIX_SHA256 to the current value
    why_not: >
      Buys one day. The digest moved twice in 21 minutes on 2026-08-17 (2f4d9467 at
      21:01, a77fdc41 at 21:21); the value quoted in the incident brief was already
      stale before any fix could land, so the re-stamp would have been born red. It
      also blesses whatever the vendor last returned as "the registration".
  - option: Quantize the frame (round to fixed dp) before hashing, then re-stamp once
    why_not: >
      Measured to be unstable — 2 dp still flips 1 of 12688 values per night, 4 dp
      flips ~240 — so it converts a deterministic nightly red into an intermittent
      one. A quantized hash is still exact equality, just on a coarser grid, and the
      grid has boundaries that ULP-scale drift crosses.
  - option: Make the collector deterministic and keep the exact hash
    why_not: >
      The non-determinism is not ours. yfinance auto_adjust=True returns a
      recomputed cumulative adjustment factor each night; we control neither its
      precision nor its revisions. Pinning vendor output would require freezing a
      snapshot — this decision, reached less directly.
  - option: Drop the receipt / downgrade it to a warning
    why_not: >
      The plane is promotion-bearing (W1-A1 percentiles were computed against it).
      Losing the ability to detect a real revision to a registered input is the one
      outcome worse than a noisy receipt.
evidence:
  - "scripts/fetch_basket_ohlcv.py:369,450 — yf.download(auto_adjust=True) + new.combine_first(prior)"
  - "prefix digest of seed 6d04e9b3 == 6d8988fc… == the registered pin (so the relocation re-stamps nothing)"
  - "digests at the two 2026-08-17 collection commits: 59ccb9c7 -> 2f4d9467…, 93ab221b -> a77fdc41…"
  - "per-night churn 8852-9492 of 12688 values, max 8.63e-07 relative; within-row OHLC ratio spread 4.44e-16"
  - "quantization flip counts vs night pairs: 2dp=1, 3dp=16/24, 4dp=236/243, 6dp=8673/9161"
  - "snapshot vs live HEAD: index identical, price max_rel 8.63e-07, volume 1 of 3172 changed (ASOF bar, +4.33e-04)"
  - "band separation: one cent at the plane minimum price 4.81 = 2.08e-03, ~2400x the noise floor"
  - "PR #5860"
affects:
  - "WS:STOCK-IDENTITY"
  - scripts/stock_identity_build_w1a1.py
  - data/stock_identity/source/
  - tests/test_stock_identity_atlas.py
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
---

Scope note: the snapshot deliberately does NOT live at
`data/stock_identity/ohlcv/B.parquet`. That path is a prohibited duplicate program-owned
B *plane* — the builder hard-fails on its existence, and W2 (PR #5643) is in flight to
remove it. This artifact is a sealed registration INPUT, not a plane: it is not
resolvable by `symbol_path`, it is not in `W1A1_REGISTERED_OUTPUT_PATHS` (it is an input,
not a generated output), and it sits alongside the program's other frozen inputs under
`data/stock_identity/`.

Rests on [[DSC-BASKET-OHLCV-REWRITES-HISTORY-NIGHTLY]].

---
key: SEALED-INPUTS-ARE-FROZEN-NOT-REPINNED
question: >
  When a sealed result pins an exact digest over an input file that a nightly lane
  rewrites, what replaces the broken pin — a re-stamped digest, a quantized hash, or
  something else? And what may the live-file check then assert?
answer: >
  Freeze the input. Recover the exact prefix the sealed run consumed from the SEED
  COMMIT (`git show <seed>:<path>`), commit it as an immutable program-owned snapshot,
  and have the sealed build read THAT. Because the seed prefix reproduces the registered
  digest exactly, this RE-ANCHORS the receipt rather than re-stamping it: the constant,
  its mirrors and every sealed receipt naming it stay byte-true and go unedited. The
  live file is then checked by a tripwire on INVARIANTS, never on bytes — and the
  tripwire must band the UNIFORMITY of the vendor's rescale, never its LEVEL, because
  `auto_adjust=True` rescales all elapsed history on every future dividend (~2.4e-3,
  ~240x the noise floor) while leaving every return, drawdown and gap identical. A
  uniform rescale cannot move a conclusion; only a change in RELATIVE prices can.
  Corporate actions stay covered on a separate channel: split adjustment rescales share
  counts, so settled volume must match exactly.
rationale: >
  A re-stamp blesses whatever the vendor last returned and re-reds the same evening; it
  also requires editing sealed outputs the builder refuses to overwrite. Banding the
  LEVEL is the subtler trap and the one a literal reading of "tolerance-aware" leads to:
  it survives the noise that caused tonight's red but fires on the next ORDINARY
  dividend, reproducing the same fleet red on a slower clock — a fix whose failure is
  scheduled rather than avoided. Freezing additionally restores a property the drift had
  silently broken: a sealed result whose inputs move nightly cannot reproduce its own
  sealed outputs, so the seal was already nominal before CI noticed.
alternatives:
  - option: Re-stamp B_SOURCE_PREFIX_SHA256 to the current digest
    why_not: Guaranteed to re-red on the next collection night (the digest moved twice in 21 minutes), and requires editing sealed A1 receipts the builder's REFUSING guard exists to protect.
  - option: Quantize prices to a coarse grid, then hash (keep an equality check)
    why_not: Rounding flips whenever a value sits within the drift of a boundary, so expected flips ~ N*2d/g; with N~9,500 price cells and d~8.6e-07, holding flip risk under 1% needs a relative granularity ~1.6 — absurd. A band has no boundary to flap across; a hash does.
  - option: Tolerance band on the price LEVEL (|ratio-1| <= ~1e-6), the literal brief
    why_not: Fires on the next routine Barrick dividend (~2.4e-3, ~240x the band) and measures a quantity no A1 conclusion depends on. Superseded in favour of the uniformity band before merge.
  - option: Delete or skip the check
    why_not: Forfeits the only detector of a genuine historical revision to the sealed evidence window.
evidence: >
  PR #5868 (this decision's implementing change); fleet red on origin/main from
  2026-08-18T04:02Z, run 32100795267 job 95601375518 ci-pack-3 ->
  `SystemExit: B source logical prefix differs from registration: a77fdc41...`.
  scripts/fetch_basket_ohlcv.py:369 (`yf.download(start=2014-01-01, auto_adjust=True)`)
  and :450 (`merged = new.combine_first(prior)`, new wins) are the rewrite mechanism.
  Three digests in one night: seed 6d8988fc (commit 6d04e9b3, container dc126c36) ->
  2f4d9467 (59ccb9c7, 04:02Z) -> a77fdc41 (93ab221b, 04:23Z); 2,214 then 2,341 of 3,172
  prefix rows moved. Measured seed->live over the 3,172-row prefix: O/H/L/C move by one
  per-row float64 factor coherent across the four columns to 4.4e-16; residual against
  the window median <= 8.63e-07; settled volume byte-identical on all 3,171 rows, with
  only the ASOF bar moving (10,621,100 -> 10,625,700, 4.33e-04) as its tape consolidated.
  Frozen snapshot data/stock_identity/sources/w1a1_b_ohlcv_prefix_v0.parquet (sha256
  ba200fe4..., logical digest 6d8988fc... unchanged). Adversarial review could not
  construct a return-changing revision that passes; it did find that a machine-epsilon
  coherence band sits BELOW the vendor's float32 print grid (~6e-8), so the band ships
  at 1e-6.
affects:
  - WS:STOCK-IDENTITY
  - scripts/stock_identity_build_w1a1.py
  - data/stock_identity/sources/**
  - research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
review_by: 2026-11-18
---

## Scope note

This records the general shape, not a Stock-Identity-only fix. Any program pinning a
hash over an artifact a nightly lane rewrites inherits the same defect; the standing
guidance is in the registration's §A1.3a and in the generalization below.

**Before pinning any hash of a data artifact, ask who rewrites the file and on what
cadence** — `git log` it across two collection nights first. When a producer is not
bit-reproducible, pin the *invariants that survive its arithmetic*, not its bytes. And
when replacing an equality check with a tolerance, ask what **routine future event**
moves the quantity, not merely what noise moves it: a band calibrated only against
noise is a red with a due date.

The prohibition in registration §A1.3 against a program-owned B *plane* stands
unamended — the snapshot is not a plane (it is absent from `PLANE_DIRS`,
`primary_planes()` cannot select it, no lane writes to it, it carries no authority), and
`data/stock_identity/ohlcv/B.parquet` remains prohibited and asserted absent.

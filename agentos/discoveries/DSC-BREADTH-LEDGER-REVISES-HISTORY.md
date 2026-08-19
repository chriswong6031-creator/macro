---
key: BREADTH-LEDGER-REVISES-HISTORY
claim: >
  data/breadth/breadth.parquet is NOT append-only in content: the nightly
  revises already-written historical rows. n_members for session 2026-08-07
  read 502 in the 2026-08-10-era blob (commit 448cfacc0957) and 504 in the
  2026-08-19 tree — same session, rewritten later. Any test fixture built by
  truncating the live ledger at a frozen date ("the append-only prefix is
  stable") silently mutates under its own test.
falsifier: >
  A diff of frozen-date slices across two nightly commits showing byte-stable
  historical rows over a multi-week window — i.e. loc[:D] of breadth.parquet
  identical between commits for all D older than a session — would confine
  this to a one-off backfill rather than standing behavior.
so_what: >
  Never derive a "frozen" fixture from a live ledger by truncation, even for
  ledgers advertised as append-only — commit the captured bytes. This is what
  broke market-memory-contract fleet-wide on 2026-08-19 (frozen numerator 504
  over live denominator 503 = coverage 1.0020 > 1.0 bound) and it was healed
  by committing an era-consistent byte-pinned pair from ONE nightly commit
  (tests/fixtures/market_memory/, PR #5941). If another suite freezes a slice
  of any nightly-advanced parquet by date-truncation, it carries the same
  latent red.
kind: architecture
verified_at: 2026-08-19
verified_by: >
  git show 448cfacc0957:data/breadth/breadth.parquet -> loc['2026-08-07']
  n_members = 502 (tip session of that collection); origin/main tip of
  2026-08-19 -> loc['2026-08-07'] n_members = 504. Constituents count 503 in
  both eras' constituents.parquet, so the frozen-numerator/live-denominator
  ratio only crossed the 1.0 bound when the numerator's history was revised.
scope:
  - macro
  - data/breadth/breadth.parquet
  - tests/test_market_memory_breadth_observation.py
  - tests/test_market_memory_breadth_store.py
confidence: verified
---

## The trap shape

A test author sees an append-only ledger, freezes `frame.loc[:FROZEN_DATE]`
at authoring time, and asserts the slice is detached from the nightly tip.
Two independent movements broke that assumption at once here:

1. the nightly **revised historical rows** inside the frozen window
   (502 → 504 for the same session, eleven days apart), and
2. the live denominator it was compared against moved with the S&P
   reconstitution (504 → 503).

Either alone was survivable; together they pushed a ratio over a hard bound
in a merge-gate job, on main, with no pull request involved.

## The fix shape (do this, not a constant re-pin)

Capture BOTH sides of any ratio/consistency assertion from the SAME
historical commit and commit the bytes as fixtures
(`tests/fixtures/market_memory/breadth_through_2026-08-07.parquet` +
`constituents_2026-08-07.parquet`, both from commit `448cfacc0957`).
Era-consistency becomes structural: the pair can only advance together, and
the default fixture path stops reading `data/` entirely — which is also what
turns the suite from `gate: data` shaped to `gate: code` shaped
(`DSC:MERGE-GATE-IS-GATED-ON-MOVING-DATA`).

---
key: CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE
question: >
  For the remaining class-C China Intelligence snapshots (broker 金股, per-name
  margin, block trades, buybacks), should history grow in-place via
  collectors/_drip keep-last, or as separate keep-first first_seen stores?
answer: >
  Separate hist files. Display snapshots stay latest-window overwrites.
  Evidence is keep-FIRST on identity (the china_trade_detail dialect), with
  immutable first_seen, atomic tmp+replace, and abort-if-unreadable. Broker
  historical months are stored only with known_at UNKNOWN. report_rc stays
  the in-place keep-first fix from PR #5614 — it had no snapshot/hist split
  to preserve.
rationale: >
  The mission forbids reconstructing history from current snapshots and
  forbids a revised vendor payload from silently rewriting prior evidence.
  _drip.append_snapshot is keep-LAST per session date and has no first_seen
  — that is the right contract for a complete daily pool (zt_pool) and the
  wrong contract for evidence. holder_counts keep-LASTs values (later notice
  corrects) while restoring first_seen; that correction semantic is honest
  for a restated quarterly disclosure and dishonest for a sell-side pick or
  a block print, where the first vintage is the observation. china_trade_detail
  already implements keep-first + first_seen + atomic write; the shared helper
  collectors/_first_seen_store.py is that write path extracted, not a new
  dialect. Separate files keep every existing snapshot consumer byte-stable.
  Stamping a historical broker month at month-start would assert Mastermind
  knew the list before it collected it.
alternatives:
  - option: Convert each snapshot file in-place via _drip.append_snapshot
    why_not: >
      keep-LAST rewrites payload; no first_seen; consumers that read the
      whole file as "today" would see a multi-date history unless every
      reader grew a latest_snapshot() call. The mission required no broken
      snapshot consumer.
  - option: holder_counts keep-last-values + restore first_seen
    why_not: >
      A later vendor revision would replace the first evidence vintage.
      The mutation bar is "revised vendor payload cannot silently rewrite
      prior evidence."
  - option: Seed hist stores from the current snapshots at first_seen=now
    why_not: >
      Looks like a backfill of claimed PIT evidence. Prospective-only:
      hist files are created on the first live refresh after this change.
evidence:
  - "collectors/china_trade_detail.py write_rows keep-first + first_seen"
  - "collectors/china_holder_counts.py _restore_first_seen + _atomic_write + abort-on-unreadable"
  - "collectors/_drip.py append_snapshot is keep-last, no first_seen"
  - "research/cn_prophet_audit/CN_INTEL_DATA_READINESS_MATRIX_2026-08-14.md §2 broker ruling"
  - "PR #5614 report_rc in-place keep-first (do not redo)"
  - "tests/test_cn_intel_pit_accrual.py mutation battery"
affects: ["WS:CN-LIMIT-ALPHA", "collectors/tushare_broker.py", "collectors/tushare_margin.py", "collectors/china_block_trades.py", "collectors/china_buyback.py"]
confidence: high
reversibility: easy
decided_by: session
decided_at: 2026-08-15
---

## Grounds

Post-P-B2 accrual hardening (WS:CN-LIMIT-ALPHA). Display snapshots remain the
latest-window files every existing consumer already reads. Evidence studies
must read the hist file and filter PIT-eligible rows (broker: `pit_eligible`;
the others: `first_seen` is the collection clock).

## What would reopen this

A vendor that restates a row as a correction of the same event (holder_counts
notice semantics) would justify keep-last-values for that family only. A
consumer that cannot tolerate a second file would justify growing history
in-place behind `latest_snapshot()`, but that is a consumer change, not an
evidence-store change.

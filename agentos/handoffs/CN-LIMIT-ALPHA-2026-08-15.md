---
workstream: WS:CN-LIMIT-ALPHA
session: cursor/cn-intel-pit-accrual-a9f2
model: opus
ended_because: complete
mission: >
  Post-P-B2 China Intelligence PIT accrual hardening: convert the remaining
  carrier-independent class-C snapshot feeds (broker 金股, per-name margin,
  block trades, buybacks) into prospective append-only keep-first evidence
  stores. report_rc already fixed by #5614 — verify, do not redo. Display
  only; zero scoring or Prophet authority.
state_before: >
  P-B2 shipped (#5615). report_rc overwrite defect healed on main (#5614,
  2026-08-14 17:29:28Z). broker.parquet / margin.parquet /
  china_block_trades/detail.parquet / china_buyback/buyback.parquet were
  still latest-window overwrites (matrix class C).
changed:
  - {path: collectors/_first_seen_store.py, what: "extracted china_trade_detail keep-first + holder_counts first_seen/atomic/abort-on-unreadable write path"}
  - {path: collectors/tushare_broker.py, what: "broker_hist.parquet keyed (month, ticker, broker); known_at only when vendor month == Asia/Shanghai collection month; snapshot unchanged"}
  - {path: collectors/tushare_margin.py, what: "margin_hist.parquet keyed (ticker, trade_date); snapshot unchanged; fin_pctile stays snapshot-only"}
  - {path: collectors/china_block_trades.py, what: "events.parquet keyed (ticker, event_date); event_date ≠ first_seen; dateless rows dropped; snapshot unchanged"}
  - {path: collectors/china_buyback.py, what: "buyback_hist.parquet keyed (ticker, event_date, plan_key); vendor 公告日期 is event_date never known_at; snapshot unchanged"}
  - {path: tests/test_cn_intel_pit_accrual.py, what: "mutation battery — day-2 preserve, first_seen immutability, payload keep-first, snapshot roll, no fabricated dates, no broker month-start PIT, no row multiply"}
  - {path: research/cn_prophet_audit/CN_INTEL_DATA_READINESS_MATRIX_2026-08-14.md, what: "§3 report_rc marked fixed; §4 rows updated; §6 evidence-start table + remaining P-C gates"}
  - {path: agentos/decisions/DEC-CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE.md, what: "separate hist + keep-first dialect; rejected in-place _drip and snapshot seeding"}
  - {path: agentos/workstreams/WS-CN-LIMIT-ALPHA.md, what: "wave P-B2-ACCRUAL done; next_action is persistence-robust certification then P-C gates"}
verified:
  - {claim: "report_rc already accrues keep-first on main; not redone", command: "git log --all --oneline --grep=5614; python3 -m pytest tests/test_tushare.py::test_report_rc_accrues_across_windows -q", result: "1e3b16dd2aa on main; test green"}
  - {claim: "14/14 new mutation tests green plus related collector/extras regressions", command: "python3 -m pytest tests/test_cn_intel_pit_accrual.py tests/test_tushare.py tests/test_china_holder_counts_collector.py tests/test_china_special_situations.py -q", result: "80+14 passed in this session (tushare vendor/auth cases deselected only where marked)"}
  - {claim: "agentos records valid", command: "python3 scripts/agentos.py validate", result: "0 errors, 9 pre-existing warnings (none on this workstream)"}
unverified:
  - {claim: "exact live evidence-start timestamps for the four new hist files", what_would_verify: "after the first asia-close collect that writes each hist parquet, record min(first_seen) per store — the files do not exist until that run"}
unresolved:
  - "P-C remains gated on chips-distribution + auction/minutes accrual lanes and the full-A spine authority decision."
next_actions:
  - "Persistence-robust certification design under a fresh prereg (P-B2 reopen path for MA200/QB/VZ and indeterminate DD cells)."
  - "P-C only when its data gates open. Do not charter it from this wave."
  - "Do not score broker/margin/block/buyback/report_rc. Do not add them to Prophet."
do_not_redo:
  - "Never cite/restore withdrawn W1-W3 artifacts (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT)."
  - "Never redo the report_rc overwrite fix (#5614)."
  - "Never stamp historical broker 金股 months as PIT-known; known_at is UNKNOWN unless vendor month equals the collection calendar month."
  - "Never turn a vendor event_date or plan_start into known_at."
  - "Never reconstruct evidence from current snapshots."
  - "Never seed the new hist stores from the pre-existing snapshots and call that PIT."
danger_areas:
  - "asia-close must actually run the four collectors for hist files to appear. A token-dark tushare night leaves broker_hist and margin_hist uncreated; that is an empty start, not a backfill invitation."
  - "china_margin_detail (akshare drip) is a different source from tushare margin_hist. Do not join them as one tape."
  - "Session worktrees are sparse: do not write into omitted data/ trees."
prs: [5730]
decisions: [DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE]
discoveries: [DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT]
---

## §0 State

Accrual hardening for the four remaining class-C carrier-independent China
Intelligence snapshots is implemented. Display files are unchanged.
`report_rc` was already lawful on main (#5614) and was not touched.

Evidence-start floor for the four new stores is 2026-08-15. The exact
timestamp per store is `min(first_seen)` after the first live collect that
creates the file. No hist parquet is committed in this change.

## §1 What is left

1. Persistence-robust certification design (fresh prereg) — the P-B2 reopen
   path. Not this wave.
2. P-C when chips-distribution and/or the minute/auction plane actually run,
   plus the operator-owned full-A spine decision.
3. Record live `min(first_seen)` on each new hist file after the first
   asia-close write.

## §2 Danger areas

A dark tushare token leaves broker_hist and margin_hist uncreated. That is
not permission to seed from `broker.parquet` / `margin.parquet`.

## §3 Not in scope

Scoring, Prophet wiring, opportunity_score/conviction, P-B/P-D comparisons,
and any historical PIT backfill.

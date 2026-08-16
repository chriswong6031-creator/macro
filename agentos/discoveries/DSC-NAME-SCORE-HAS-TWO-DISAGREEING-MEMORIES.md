---
key: NAME-SCORE-HAS-TWO-DISAGREEING-MEMORIES
claim: >
  RESOLVED 2026-08-14: the published name_score (snapshots.jsonl conviction.potential.score)
  and the nightly store (data/name_score/us_calls.parquet, column score) were ONE quantity
  under TWO DATE KEYS, not two quantities. The store append stamped
  pd.Timestamp.utcnow().date() at append time; the nightly's library band runs after
  00:00 UTC, so session D's calls landed under calendar date D+1 (and weekend lanes
  minted Sat/Sun stamps — 11 weekend dates in the store). Joining board(D) to
  store(D+1 CALENDAR) gives close-level match 1.000 on all 20 snapshot dates and score
  match 1.000 on nightly-only dates (0.92-0.97 where a sibling lane's append won the
  keep-FIRST collision). The 22-29% same-date agreement was adjacent-session score
  autocorrelation. The PR-1b offset sweep missed this because it swept SESSION offsets
  while the store is keyed by wall-clock CALENDAR dates.
falsifier: >
  MET (the "documented transform" arm): store(D+1 calendar) ≡ published(D), level match
  1.000, all 20 overlapping snapshot dates, measured 2026-08-14. Forward falsifier for
  the fix: any post-2026-08-17 session where a (date,ticker) join of snapshots.jsonl
  conviction.potential.score against us_calls.parquet score on the SAME date key shows
  <100% agreement on rows the same nightly admitted (thin-lane keep-FIRST collisions
  excluded and disclosed).
so_what: >
  Fixed forward in the producer: build_stock_library.py now stamps the US append with
  the board's own session date (alpha_asof — the same value wide["as_of"] publishes and
  snapshot_today() keys the fossil on) via _name_score_asof(); HK/CA/INTL got the same
  session-anchor fix (CN already had it). Pinned by tests/test_name_score.py
  (test_us_store_stamp_wired_to_session_asof + producer-relationship test). Historical
  rows are NOT rewritten (honest history): every store date <= 2026-08-15 keeps
  wall-clock keys — store(X) holds session-(X-1)'s calls — so any historical join must
  apply the +1-calendar transform. Consumers reading only the store (rank-IC in
  prophet_miss_audit, name_score_grader.grade) gain one session of forward-window
  tightness at the transition; the fusion arena's G2 races the PUBLISHED value and is
  unaffected. Transition: the 2026-08-14 stamp is MIXED (1,695 session-08-13 rows from
  a thin-lane append + session-08-14 rows admitted around them); first fully clean
  session-keyed stamp = 2026-08-17. Side-finding, separate defect: stamps since
  2026-08-10 are THIN (~1,695 names vs ~2,925, a strict subset — the missing
  source-group/breadth-cache signature from 2026-07-25 is back on weekday nightlies).
kind: landmine
verified_at: 2026-08-14
verified_by: >
  Root-cause fingerprint 2026-08-14: (date,ticker) join of snapshots.jsonl potential
  vs us_calls.parquet at calendar offsets -3..+3 — offset +1 gives level_match 1.000 on
  every one of the 20 snapshot dates (score 1.000 on nightly-only dates); store carries
  11 weekend stamps (wall-clock proof); producer sites build_stock_library.py
  _name_score_asof + append at market="US" (was utcnow at the 4367-region),
  build_{hk,canada,intl}_library.py siblings, china builder already session-anchored.
  Original 22-29% same-date receipts: research/prophet_fusion/PR1B_BASELINE_RACE.md
  §12.2 (+ 2026-08-14 addendum).
scope: [macro]
confidence: verified
---

## Detail

The board's published conviction.potential.score and the store's row are produced by the
SAME run of scripts/build_stock_library.py from the same rec (`_pot["call"]["score"]` is
the displayed score). The divergence was purely in the date key: the store append used
the render host's UTC calendar date at append time (~00:30-02:30 UTC → session+1;
weekend lanes → Sat/Sun stamps), while grade_us_board.snapshot_today() fossilizes the
board under its own `as_of` (session date). Keep-FIRST dedupe then let whichever lane
hit a calendar date first own that stamp — thin weekend/weekly universes (~1,695 names,
missing breadth-cache signature) occasionally beat the full nightly (~2,925).

Fix (fix-forward, 2026-08-14): all four non-CN builders stamp the append with their
board/alpha session anchor; utcnow survives only as a loudly-warned fallback when the
anchor is missing/corrupt. Historical store rows keep their wall-clock keys — apply
store(X) = session-(X-1) when joining history. "name_score" claims on PRE-fix store
dates must still name their source.

Adversarial-review hardening (same PR, opus red-team on the first head):

- **INTL's alpha carries NO as_of key on any code path** — a plain
  `(alpha or {}).get("as_of")` anchor is ALWAYS None there (and the same dead
  expression pre-exists at two other INTL sites). The INTL stamp resolves from the
  library tip instead (`_intl_session_asof`: alpha as_of if it ever appears → max
  per-rec asof → wall-clock marked unkeyed), with a behavioral test.
- **`session_keyed` column (nullable boolean) on every row written from the cutover**:
  True = session-keyed date, False = wall-clock fallback, null = pre-cutover era.
  This is the partition marker for BOTH transition costs: (a) the 2026-08-14 mixed
  stamp, and (b) the forward-fill convention break — wall-clock-era weekday rows
  filled TWO sessions after the call (stamp D+1, fill = next bar), session-keyed rows
  fill ONE session after; do not compare forward metrics (rank-IC, hit rates) across
  the cutover without partitioning on this column.
- **grade()'s PIT stamp-gap detector is now trailing-window cadenced**
  (`_GAP_DOW_WINDOW=15`): the store's history contains 11 weekend stamps, so an
  all-history weekday set would have flagged every post-cutover weekend as a gap
  forever and saturated `stamp_gap_dates[:14]` within ~4 weeks, hiding any real
  missed nightly.
- **Zero-row appends are now visible at the write site** (grader logs
  admitted/submitted delta), and a resolved-but-stale session anchor (>5 days behind
  the host clock — a frozen alpha.json would make every nightly dedupe into the stale
  session and land 0 rows, a failure mode wall-clock stamping could not have) emits a
  `::warning` annotation from `_name_score_asof`.
- **Accrual cadence drops ~7/wk → ~5/wk by design**: the weekend stamps the store
  used to accrue were duplicate echoes of Friday's calls under new date keys, not
  independent observations.
- **The `_MAX_BAR_LAG_DAYS=7` dead-feed gate ran one real day TIGHTER than its
  documented NYSE-closure derivation under wall-clock stamping**; session stamping
  restores the documented calibration (a feed frozen exactly 7 calendar days behind
  the session is now admitted). Noted at the constant.

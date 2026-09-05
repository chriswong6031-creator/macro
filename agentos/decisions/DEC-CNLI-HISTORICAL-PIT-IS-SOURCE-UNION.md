---
key: CNLI-HISTORICAL-PIT-IS-SOURCE-UNION
question: >
  The exact plane's `pit_universe` stage quarantined every `bak_basic` PIT row
  whose ticker is absent from the CURRENT `stock_basic` snapshot, and quarantine
  must be zero for a unit to be terminal — so `stage=complete` was unreachable.
  Is the current `stock_basic` snapshot the authority on historical A-share
  membership, such that a security it no longer publishes was not in the
  historical universe?
answer: >
  No. Current `stock_basic` is a lifecycle/reference WITNESS, not exhaustive
  historical membership authority. Historical PIT construction is
  source-UNION, not current-snapshot intersection. The invariant requiring every
  historical `bak_basic` row to exist in the current `stock_basic` snapshot is
  removed. A valid `bak_basic` PIT observation may introduce a vendor listing key
  carrying `current_stock_basic_witness_missing=true`.

  That observation alone grants NO trading/event authority and NO
  canonical-identity authority. Authority is graded:

  * A complete same-session positive-volume daily observation PLUS the required
    exact legal-limit/session evidence proves historical trading even when
    current `stock_basic` omits the security. Such a security MUST NOT be
    silently removed from the historical exact universe.
  * A PIT-observed row WITHOUT authority-grade trading evidence remains
    source-accounted but non-event-eligible. "Never listed" may not be inferred
    unless an explicit lifecycle source establishes that stronger state.

  PIT-only listing keys propagate into required downstream historical source
  acquisition, including `name_history`, so the same survivorship filter is not
  recreated one stage later. Data OS/GMI remains the canonical identity owner; no
  historical CN-Limit identity master is created.

  Completeness stays fail-closed for malformed or conflicting keys, incomplete
  source responses, unresolved source contradictions, positive-volume rows
  without required exact legal-band evidence, and any unknown disposition.
  Current-snapshot omission rate is recorded as TELEMETRY, never as an exclusion
  threshold.
rationale: >
  The witness is a CURRENT snapshot being used to classify HISTORICAL sessions.
  Intersecting against it is a survivorship filter with the sign of the error
  pointing one way: any security the vendor later stops publishing becomes
  unclassifiable on every past date it actually traded. The measured instance is
  `300114.SZ` 中航电测 — a security demonstrably trading on 2024-01-02 (eps 0.17,
  44,237 holders) that the current snapshot no longer carries because the 中航
  group consolidated. Excluding it would silently shrink the historical exact
  universe and bias every downstream denominator — eligibility rates, targets,
  access classes — in favour of survivors. That is the precise defect the whole
  exact plane exists to avoid, so the failure had to be repaired at the semantic
  layer rather than by relaxing the quarantine gate.

  The repair is narrow because the architecture was already union-shaped
  everywhere downstream: `_eligible_tickers_with_pit` already returns
  `lifecycle | pit`; `_instrument_scope_maps` already folds landed PIT tickers
  into `known_a`; `event_eligible` is already
  `positive_volume & source_limits_present`, which IS the graded trading
  authority this ruling requires, so a PIT-only row without trading evidence is
  non-event-eligible by construction.

  The intersection was encoded at THREE layers, not one: the classifier at the
  entry point (`normalise_bak_basic`), the PIT lifecycle reconciliation
  (`_pit_lifecycle_reconciliation`), and the daily security coverage builder
  (`build_daily_security_coverage`), where a landed PIT row that never traded
  becomes `eligible` with no daily row and falls into `unexplained_missing_n`.
  The latter two are both TERMS IN THE COMPLETENESS MANIFEST'S OWN `complete`
  CONJUNCTION, so repairing only the classifier would have moved the identical
  failure two stages later and presented it as a new defect. This is why the
  ruling's instruction not to recreate the same survivorship filter one stage
  later had to be read as an inventory requirement rather than a caution.

  Fail-closed is preserved exactly where it carries information: an unparseable
  key and a non-A identity stay quarantined, because those are unknown
  dispositions rather than known-and-absent ones. Omission rate is telemetry
  because a threshold on it would smuggle the same survivorship filter back in
  as a tunable.
alternatives:
  - option: Relax the `quarantined_unknown == 0` gate so the unit can go terminal
    why_not: >
      Fail-open, and it discards the distinction between "known and absent from a
      non-authoritative witness" and "genuinely unknown". The program already
      refused the identical shape for the `trade_cal` exact-range check.
  - option: Exclude witness-missing rows as a named `known_excluded` family
    why_not: >
      Encodes the survivorship filter as policy. It would silently drop
      `300114.SZ`, a security that provably traded that session, from the
      historical exact universe.
  - option: Infer "never listed" for zero-share rows such as `603361.SS`
    why_not: >
      A stronger state than the evidence supports. TuShare returns ZERO
      `stock_basic` rows for list_status G on every exchange, so no
      approved-unlisted source exists to establish it. Absence of shares is not a
      lifecycle source.
  - option: Build a CN-Limit historical identity master to back-fill the witness
    why_not: >
      Duplicates the canonical identity plane Data OS/GMI owns and creates a
      second authority for the same fact. Explicitly forbidden by this ruling.
  - option: Widen the reconciliation to accept every PIT/lifecycle difference
    why_not: >
      Over-wide. Only the pit-not-in-lifecycle direction was ruled on. A
      lifecycle-eligible security missing from the PIT witness, and a PIT row
      whose master lifecycle window contradicts the observed trade date, remain
      unresolved source contradictions and stay blocking.
evidence:
  - "DSC:CNLI-BAK-BASIC-PIT-ROWS-ABSENT-FROM-STOCK-BASIC-WITNESS — the measurement that forced the escalation."
  - "Canary run 32950379014 (mode=canary, max_requests=12, 2024-01-02): bak_basic unit status failed, reason quarantined_unknown_source_rows, 5344 = 5342 + 0 + 2."
  - "Retained quarantine payload store://source_row_classification/quarantined_unknown/bak_basic/year=2024/month=01/part.parquet names 300114.SZ and 603361.SS, both classification_source bak_basic_absent_from_stock_basic_A_witness."
  - "Vendor coverage, not a stale refresh: 5,889 raw source_stock_basic rows (L 5,550 / D 338; G and P partitions empty) and 6,136 identity aliases in generation ref-20260826T002451670234Z-1b644e5d5e2c, zero matches for either code."
  - "collectors/china_tushare_spine.py:4093 `_eligible_tickers_with_pit` already returns `lifecycle | pit`; :3945 `event_eligible = positive_volume & source_limits_present`; :2010 `_instrument_scope_maps` folds landed PIT tickers into known_a — the downstream plane was already source-union."
  - "research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:113-115 named the universe as `lifecycle ∪ PIT` while the collector could only mint from the lifecycle master, which is the contradiction this decision resolves."
affects:
  - WS:CN-LIMIT-ALPHA
  - collectors/china_tushare_spine.py
  - research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md
  - research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-26
---

# The PIT witness outruns the lifecycle witness, and that is legal

Sol return-gate 10 under `DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`, ruling the
escalation raised by `DSC:CNLI-BAK-BASIC-PIT-ROWS-ABSENT-FROM-STOCK-BASIC-WITNESS`.

Reversibility is `costly` rather than `easy` because the decision sets what the
eligible A-share universe IS, and therefore the denominator of every eligibility
rate, target and access class computed on the exact plane. Reversing it after any
downstream measurement is frozen would invalidate that measurement, not merely
change a flag.

Two execution constraints ride with the ruling and are not separable from it:
the clean 1992 calendar/reference generation is REUSED rather than rebuilt
(`DSC:CNLI-MAINLAND-CALENDAR-EPOCH-1992-JOINT-COMPLETE`), and the failed
`bak_basic` terminal unit is discarded for a fresh attempt rather than repaired
in place — the same hazard recorded in
`DSC:CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS`.

`BULK_HISTORICAL_BACKFILL_READY` stays `False`. Only a clean terminal canary plus
independent review may commission the separate technical bulk-readiness
promotion, and no DEP-ID-ELIG or downstream CN-Limit feature work may begin
before DEP-EXACT closes.

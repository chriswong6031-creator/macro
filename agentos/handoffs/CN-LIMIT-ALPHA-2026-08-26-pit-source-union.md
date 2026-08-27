---
workstream: WS:CN-LIMIT-ALPHA
session: claude/cn-limit-pit-source-union
model: fable
ended_because: blocked
mission: >
  Execute Sol return-gate 10: replace the current-snapshot intersection at the
  exact plane's pit_universe stage with source-union semantics, prove
  replay-invariance, then start a fresh PIT/exact attempt and drive one bounded
  canary to stage=complete through name_history and all five daily endpoints.
state_before: >
  Epoch frozen and live on main (mainland-joint-complete-v1 / 1992-01-01,
  19df24573e72) with the trade_cal plane cleanly rebuilt to 66/66 terminal units
  and 7,807 sessions. The zero-date sentinel fix merged (003e6b988f6f). The
  acceptance canary was blocked at pit_universe: bak_basic 20240102 measured
  5,344 = 5,342 + 0 + 2, quarantine must be zero for a terminal unit, and
  collect_spine stops at that stage, so stage=complete was unreachable. Both
  quarantined rows were classified bak_basic_absent_from_stock_basic_A_witness.
changed:
  - {path: agentos/decisions/DEC-CNLI-HISTORICAL-PIT-IS-SOURCE-UNION.md, what: "Sol's ruling recorded: historical PIT construction is source-union, never current-snapshot intersection; graded trading/identity authority; PIT-only propagation into name_history; omission rate as telemetry."}
  - {path: research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md, what: "The clause that named the universe as lifecycle-union-PIT while blocking on every post-2016 difference now states the source-union law and which differences still block."}
  - {path: research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md, what: "Its survivorship-and-universe-honesty section now says how that law is enforced at the collector; its completeness criterion follows the same split."}
  - {path: agentos/workstreams/WS-CN-LIMIT-ALPHA.md, what: "DEP-EXACT wave next_action carries the ruling and the three-layer finding."}
verified:
  - claim: The survivorship filter was encoded at THREE layers, not one
    command: "Traced the completeness manifest's `complete` conjunction term by term in collectors/china_tushare_spine.py"
    result: >
      CONFIRMED. :4913-4921 conjoins BULK_HISTORICAL_BACKFILL_READY,
      reference_ready, endpoints_complete, pit_lifecycle["complete"],
      coverage_receipt["complete"], canonical_event_substrate["ready"] and
      lifecycle["complete"]. Three terms carry the filter — the row classifier
      via endpoints_complete (quarantine must be zero), :4103
      _pit_lifecycle_reconciliation whose complete requires len(extra_in_pit)==0
      i.e. pit subset-of lifecycle, and :4851 coverage_receipt["complete"] which
      requires unexplained_missing_observations==0 while :4234 computes
      eligible = _eligible_tickers_with_pit(...) and missing = eligible - actual,
      so a landed PIT row that never traded becomes an unexplained coverage gap.
      Fixing only the classifier moves the failure two stages later.
  - claim: Two further conjunction terms need no change
    command: "Read collectors/china_tushare_spine.py:4352-4401 and :4811-4830"
    result: >
      PASS. _lifecycle_edge_reconciliation guards its before-list/after-delist
      checks with `if ticker in lifecycle.index`, so a master-absent ticker is
      skipped, and pit_list_date_mismatch compares a PIT row's own list_date to
      its own trade_date with no master involved (and skips null list_date).
      canonical_event_substrate derives from the daily tape, so a PIT-only
      never-traded row is simply absent from the join.
  - claim: The rest of the plane was already source-union and needs proof, not change
    command: "Read collectors/china_tushare_spine.py:2010, :2428, :3945, :4093"
    result: >
      PASS. _eligible_tickers_with_pit already returns lifecycle | pit;
      _instrument_scope_maps already folds landed PIT tickers into known_a, so
      name_history and the five daily endpoints inherit propagation;
      event_eligible = positive_volume & source_limits_present already IS the
      ruling's graded trading-authority test, so a PIT row without trading
      evidence is non-event-eligible by construction.
  - claim: A new derived column cannot break a strict schema assertion
    command: "grep KEY_COLUMNS / ENDPOINT_FIELDS / expected_columns in collectors/china_tushare_spine.py"
    result: >
      PASS. KEY_COLUMNS['bak_basic'] is only ['trade_date','ticker'], and the
      exact-column check at :2196 validates the RAW vendor response frame against
      requested fields, not the derived landed frame.
  - claim: The fresh-attempt surgery preserves the calendar and the reference generation
    command: "python3 scratchpad/pit_fresh_attempt.py (report-only dry run)"
    result: >
      PASS. Plan drops exactly the failed bak_basic unit plus bak_basic/,
      source_row_classification/quarantined_unknown/bak_basic/,
      receipts/requests/bak_basic/ and the derived completeness_manifest.json,
      while preserving trade_cal 66, stock_basic 12, fund_basic 3, bse_mapping 1
      and all 53 reference parquet files. The script refuses --apply without an
      existing backup and asserts no preserved plane is in its own plan.
  - claim: The failed unit wrote its landed partition despite being marked failed
    command: "Inventory of the private store's bak_basic plane"
    result: >
      CONFIRMED — bak_basic/year=2024/month=01/part.parquet exists at 441,196
      bytes for a unit whose status is `failed`. This is the same
      ledger-diverges-from-artifacts hazard recorded in
      DSC:CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS and is why the
      ruling's fresh-attempt instruction is not cosmetic.
  - claim: The ci-authority/codex/merge-queue-pilot red on PR 6486 is by design
    command: "gh api repos/.../check-runs/98364660853"
    result: >
      PASS — context_reason `inactive_base_context` for base context
      codex/merge-queue-pilot, which this PR does not target. The binding
      ci-authority/main check passed with reason `ordinary_change`.
unresolved:
  - >
    The implementation (C1-C6) and its tests (T1-T9) were commissioned to a
    routed builder against the frozen spec and had not landed when this handoff
    was written. The spec lives in the session scratchpad, not in the repo; if it
    is lost, it is reconstructible from DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION
    plus the three-layer finding above.
  - >
    Whether the two measured rows split as expected once the change lands:
    300114.SZ should become a landed, witness-missing, EVENT-ELIGIBLE row (it
    traded that session), while 603361.SS should become landed, witness-missing
    and NON-event-eligible with no daily observation. That is the ruling's graded
    authority working, and it is the first thing to read off the fresh canary.
unverified:
  - >
    name_history and all five daily endpoints have STILL never executed against
    the vendor. Every claim about their behaviour is code-reading, not
    measurement, until a canary reaches them.
  - >
    Whether the current-snapshot omission rate stays near 2 rows per session or
    rises on older dates. Only ONE session (2024-01-02) has ever been collected.
    The witness is a CURRENT snapshot classifying HISTORICAL sessions, so the
    rate can only worsen as the campaign reaches back; it is now telemetry and
    will be measurable per unit rather than fatal.
next_actions: >
  1. Land C1-C6 + T1-T9 on claude/cn-limit-pit-source-union, update PR 6486's
     body, arm merge-on-green, and own it to merged.
  2. Back up the private store, then run scratchpad/pit_fresh_attempt.py --apply
     to discard the failed bak_basic unit. Reuse the clean 1992 calendar and the
     existing reference generation; never re-collect identity.
  3. Drive bounded canary windows (mode=canary, max_requests=12, one-day window)
     to stage=complete through pit_universe, name_history and all five daily
     endpoints. Expected shape: pit 1 + name <=5 + daily 5 = <=11 against the cap
     of 12.
  4. Only then: a SEPARATE technical-readiness PR for the bulk gate, gated on a
     clean terminal canary AND independent review. Then the resumable range
     campaign, then close DEP-EXACT on the sanitized completeness manifest.
do_not_redo:
  - >
    Do NOT relax the quarantined_unknown == 0 gate in _unit_done. The ruling
    makes these rows stop BEING quarantined; it does not make quarantine stop
    mattering.
  - >
    Do NOT widen the ruling to missing_in_pit (lifecycle-eligible but absent from
    the PIT witness). Sol ruled only on the current-snapshot direction. That case
    still blocks, deliberately.
  - >
    Do NOT put a threshold on the omission rate. It is telemetry. A threshold
    would reintroduce the survivorship filter as a tunable.
  - >
    Do NOT re-derive the epoch or re-run the census. Frozen at 1992-01-01,
    definition mainland-joint-complete-v1, merged at 19df24573e72.
  - >
    Do NOT build a historical CN-Limit identity master. Data OS/GMI stays the
    canonical identity owner; identity is rule-derived via canonical_identity.
  - >
    Do NOT promote BULK_HISTORICAL_BACKFILL_READY or dispatch mode=backfill in
    this PR. That promotion is a separate, reviewed change.
  - >
    Do NOT spawn a second blast-radius audit. Two attempts returned only an
    orienting sentence (25 then 53 tool calls, 259k tokens total, nothing
    delivered). The decisive question — which manifest conjunction terms break —
    was four greps in the main loop.
danger_areas:
  - >
    The filter reappears wherever a CURRENT reference artifact is used to
    classify a HISTORICAL observation. Three sites are fixed here; any new
    consumer that joins the PIT plane against the security master is a candidate
    fourth. The tell is a check whose failure mode is "the vendor no longer
    publishes it", not "the data disagrees".
  - >
    A landed PIT row is source-accounted but carries NO trading or identity
    authority. Anything that treats pit_universe membership as proof a security
    traded, or as an identity attestation, is wrong and reintroduces the defect
    from the other side.
  - >
    Backups of the private store hold superseded eras and must never be promoted:
    ~/.local/share/macro-dashboard/china_tushare_spine.prerebuild-20260826 is the
    OLD 1991-anchored trade_cal plane.
  - >
    SOURCE_ROW_CAPS['stk_limit'] is 5800 and the cap test is `>=`, while the
    A-share universe measured 5,344 on 2024-01-02 and grows a few hundred names a
    year. The 2024 canary has roughly 450 rows of headroom, but a whole-market
    stk_limit call on a recent session will eventually land at the documented
    maximum, and the collector then refuses the unit rather than blessing a
    truncated response. That refusal is correct — it is the same fail-closed
    reasoning as the trade_cal exact-range check — but it means the range
    campaign will hit an endpoint-specific wall on recent dates that the 2024
    canary cannot reveal. Do NOT respond by raising the constant: the cap is the
    vendor's documented per-call maximum, so raising it would bless truncation.
    The cap_fallback path (switch the whole requested interval to the
    ticker-range campaign) is the designed answer, and it is unproven.
---

# Removing a survivorship filter that was written in three places

Sol's return-gate 10 ruling arrived as a semantic correction: the current
`stock_basic` snapshot is a witness, not authority on historical membership, so
historical PIT construction is source-union rather than current-snapshot
intersection. Recorded as `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`.

The instruction that turned out to matter most was "do not recreate the same
survivorship filter one stage later". It was literally descriptive. The filter
was encoded at the row classifier, at the PIT/lifecycle reconciliation, and at
the daily coverage expectation — and the latter two are both terms in the
completeness manifest's own `complete` conjunction, so each would have blocked
DEP-EXACT on its own while presenting as a fresh, unrelated defect.

One scoping judgment was taken inside the ruling rather than assumed silently:
`extra_in_pit` conflated a ticker absent from the master entirely (legal under
the ruling, now telemetry) with a ticker whose master lifecycle window
contradicts the observed trade date (an unresolved source contradiction, still
blocking). The same discipline applies to coverage — only the witness-missing
class stops counting as an unexplained gap.

Predecessor: `agentos/handoffs/CN-LIMIT-ALPHA-2026-08-26-pit-universe-witness-gate.md`.

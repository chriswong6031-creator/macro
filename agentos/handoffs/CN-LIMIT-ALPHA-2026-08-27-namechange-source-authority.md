---
workstream: WS:CN-LIMIT-ALPHA
session: claude/cn-limit-namechange-source-authority
model: fable
ended_because: blocked
mission: >
  Execute Sol return-gate 10B: replace external-witness-as-completeness in the
  name-history plane with deterministic row disposition, add the replay and
  negative proofs Sol required by name, amend the completeness manifest, then
  continue the acceptance canary inside the unchanged <=12 request envelope.
state_before: >
  Return-gate 10 shipped and proven live (PR #6486, squash a636c7bcefdb):
  bak_basic 20240102 went from failed to complete at 5344 = 5344 + 0 + 0 with
  witness_missing_row_count 2. The stk_limit zero-pre_close sentinel shipped
  (PR #6494, squash fab40e11940c). The canary was then blocked at name_history:
  namechange reached 9 of 10 attempted year-units terminal and 1999:19991231
  failed at 193 = 192 + 0 + 1 on a single row, 000991.SZ, a well-formed A-share
  code absent from the current 5,888-row security master. build_completeness_
  manifest requires every year from NAME_HISTORY_START_YEAR = 1990, so one
  unclassifiable row in one year blocked the whole manifest and every
  downstream wave behind DEP-EXACT.
changed:
  - {path: agentos/decisions/DEC-CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY.md, what: "Sol's 10B ruling recorded: a valid namechange row is itself sufficient source evidence; three-way deterministic disposition; NAMECHANGE_ONLY is terminal source completeness with zero PIT/trading/event/identity/rank/score authority; no era special case and no rate threshold; manifest complete requires deterministic reconciliation, not 100% corroboration."}
  - {path: collectors/china_tushare_spine.py, what: "N1-N6 and N9: the compound witness branch split three ways with an explicit _is_a_share_identity scope gate, the source_disposition column, the two fail-closed conditions that did not previously exist (contradictory lifecycle interval, same-day conflicting names), namechange_only unit telemetry, the renamed failure reason, and the manifest name_history reconciliation_law plus store-wide telemetry."}
  - {path: tests/test_china_tushare_spine.py, what: "T1-T11 appended (11 new) including the REPLAY and NEGATIVE proofs Sol required by name; two pre-existing tests amended because they encoded the overturned law. 100 -> 111 passing."}
  - {path: contracts/cn_tushare_a_share_spine_manifest.v1.schema.json, what: "Extended for the two new manifest telemetry keys. additionalProperties:false untouched."}
  - {path: research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md, what: "Carries the 10B law; the endpoint table row that said 'orphans block' now states what actually blocks."}
  - {path: research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md, what: "Survivorship section extended to the name-history plane; the manifest criterion's stale 'zero name-orphan counts' replaced with deterministic reconciliation."}
  - {path: agentos/decisions/DEC-CNLI-HISTORICAL-PIT-IS-SOURCE-UNION.md, what: "Deferred S4 correction from #6486: its rationale said the intersection sat at two layers. It was three, and two of them were terms in the manifest's own complete conjunction."}
  - {path: agentos/discoveries/DSC-CNLI-PRE-PIT-NAMECHANGE-ORPHANS-HAVE-NO-WITNESS.md, what: "Marked RULED, with the two framings Sol explicitly refused (era exception, rate-as-threshold) recorded as superseded."}
  - {path: agentos/workstreams/WS-CN-LIMIT-ALPHA.md, what: "DEP-EXACT next_action carries 10 shipped/proven, 10B ruled, the three execution findings, and Sol's bulk-readiness clarification."}
verified:
  - claim: name_history is a LEAF, so unlike the PIT case there is no second-stage filter to repair
    command: >
      grep -rn "name_history" --include="*.py" across the repo excluding tests.
      The only reader of the store partitions is _name_history_receipts (:4652)
      and the artifact-receipt resolver (:1015). build_canonical_event_substrate
      reads daily+stk_limit; build_daily_security_coverage reads master+daily+PIT;
      _all_known_a_tickers reads instrument_classification+PIT. No engine/ or
      scripts/ consumer exists at all.
  - claim: TWO of the four fail-closed conditions Sol required to be PRESERVED did not exist and had to be BUILT
    command: >
      grep for effective_from/effective_to in the collector showed no interval
      validation anywhere in normalise_name_history. KEY_COLUMNS["name_history"]
      includes `name`, so two rows sharing (ticker, effective_from) with
      different names do not trip _duplicates. The single compound witness
      condition had been masking both.
  - claim: 111 tests pass and 11 of 13 fail against the unmodified collector
    command: >
      python3 -m pytest tests/test_china_tushare_spine.py -> 111 passed.
      Falsification: origin/main's collector restored by file copy (never git
      stash -- the stack is shared repo-wide), the 11 new plus 2 amended tests
      re-run -> 11 failed, 2 passed.
  - claim: the 2 that pass either way still pin something, and are kept deliberately
    command: >
      T5 (B-share known_out_of_scope) is a pure regression guard proving the
      exclusion path survived the N1 split -- it must pass both sides by
      construction. T8 (re-announcement is not a conflict) is a SCOPE guard on
      N4: mutating the conflict predicate from "more than one distinct name" to
      a group-size check makes T8 fail, so it is falsifiable against a plausible
      mis-implementation even though origin/main has no conflict check to fail
      against.
  - claim: known_a membership was doing double duty as the only A-share scope filter
    command: >
      canonical_identity("500999.SH") parses to a valid SSE identity with
      _is_a_share_identity False and no B-share exclusion family, so before the
      explicit gate was added it was excluded only by absence from known_a.
      Pinned by T4.
do_not_redo:
  - Do NOT reintroduce any external-witness requirement for a namechange row to EXIST. Sol 10B removed it; existence and authority are granted separately.
  - Do NOT special-case pre-2016, and do NOT use the witness-missing rate as an admission threshold. Sol refused BOTH by name. The 0.09% measurement is descriptive only and carries no admission authority.
  - Do NOT relax the quarantined_unknown == 0 gate in _unit_done.
  - Do NOT raise a SOURCE_ROW_CAPS constant and do NOT change CANARY_MAX_REQUESTS. Sol ordered plainly that the cap must not be changed to make the canary fit. Run more windows instead.
  - Do NOT set BULK_HISTORICAL_BACKFILL_READY here; it needs its own reviewed technical PR.
  - Do NOT make the conflict check raise. It quarantines by design: a raise leaves the rows with no disposition and kills a 35-year run instead of blocking one year-unit.
  - Do NOT let name_history feed _all_known_a_tickers. T10 pins this; it is the inversion that would let a name assertion mint universe membership.
danger_areas:
  - >
    ORDERING inside normalise_name_history is load-bearing. The known_out /
    B-share exclusion check must run BEFORE the new _is_a_share_identity gate,
    or 900901.SH quarantines despite having good official code-family
    provenance and blocks its unit. T5 pins the ordering.
  - >
    The manifest telemetry now FAILS CLOSED on a partition lacking
    source_disposition. That is deliberate: name_history_row_count counts such
    rows in the denominator, so skipping them would silently DILUTE the rate.
    It also means the 9 pre-ruling partitions must be discarded (see next_action)
    before a manifest can be built.
  - >
    A canary window that stops short is the resumable envelope working, not a
    wedge. NAMECHANGE_MAX_PER_RUN = 5 is a PER-RUN cap and collect_name_history
    iterates NAME_HISTORY_START_YEAR..end.year, so a 2018 canary needs 29
    year-units and therefore ~6 windows.
  - >
    The row cap is ALREADY BINDING on recent sessions: stk_limit returned
    >=5,800 rows for a 2024 session against a 6,000 cap that daily/daily_basic
    cleared only narrowly. The ticker-range campaign is REQUIRED for recent
    dates, not an optimisation.
unresolved:
  - >
    Nothing is blocked on Sol. Gate 1 (the pre-2016 namechange orphan question)
    was ANSWERED by return-gate 10B and is closed.
  - >
    Open on execution only: the 29-year name_history re-collection and the
    remaining daily endpoints (stk_limit re-run after its sentinel fix,
    suspend_d and stock_st, which have never executed against the vendor).
unverified:
  - >
    stk_limit, suspend_d and stock_st have never reached a terminal unit against
    the live vendor. stk_limit's zero-pre_close defect is fixed in code and unit
    tested but its FIRST clean live run has not happened.
  - >
    The 10B collector changes are proven by 111 unit tests and a falsification
    pass, NOT yet against the live vendor. No canary window has run under them.
  - >
    The witness-missing RATE across the full 1990-2018 epoch is unknown. Only 10
    year-units were ever attempted and only 1999 carried an orphan; years
    2000-2018 are unattempted, so the governing rate is not measured.
next_actions:
  - >
    BLOCKED ON THE SHIP CHAIN ONLY -- no Sol gate is open. On merge: (1) discard
    the pre-ruling name_history plane with the scratchpad discard script (10
    partitions, 1 classification dir, 59 parquet files in other planes untouched;
    a backup is written and must never be promoted) because those 9 terminal
    partitions predate the disposition column and would otherwise leave a
    mixed-schema plane -- the same fresh-attempt pattern Sol ordered in gate 10
    and the hazard in DSC:CNLI-REPAIRED-SPINE-LEDGER-DIVERGES-FROM-ARTIFACTS;
    (2) drive ~6 bounded canary windows on 2018-01-02 at the unchanged
    max_requests=12 until every expected unit is terminal -- 29 namechange
    year-units plus stk_limit, suspend_d and stock_st, which have never executed;
    (3) then the SEPARATE reviewed technical readiness PR. Per Sol 10B that PR
    does NOT require the canary to have exercised the ticker-range campaign,
    because that capability is held behind the same flag; exact-head canary plus
    range-shard ADVERSARIAL TESTS may justify it, and the first post-promotion
    bounded range execution is its production proof. DEP-EXACT stays open until
    the complete range campaign and the sanitized completeness manifest. No
    DEP-ID-ELIG or downstream CN-Limit feature work before that.
---

# Existence and authority are granted separately

Sol return-gate 10B completes what return-gate 10 started. Gate 10 replaced the
current-snapshot intersection with a source-union built on a corroborating PIT
witness. That witness begins 2016-01-01, so every earlier `namechange` row fell
straight back to the current snapshot as sole authority — the exact condition
gate 10 rejected, reached through the gap in its own mechanism.

Sol closed the gap by removing the dependency on a witness altogether rather
than by extending the witness backwards, which is the stronger repair: the
program no longer needs a corroborating plane to exist in order to record what
the vendor said.

The implementation was small because `name_history` is a leaf. The expensive
part of gate 10 was that the same filter sat at three layers, two of them terms
in the completeness manifest's own `complete` conjunction, so a partial fix
resurfaced two stages later as an apparently new defect. Nothing reads the
name-history partitions but their own receipt builder, so there is no equivalent
here — and that is precisely why the negative proof matters. "No consumer today"
is the kind of fact that changes silently, and the one change that would matter
is a name-history row feeding back into the known-A set, which would let a
namechange-only observation bootstrap itself into the PIT membership authority
the ruling denies it. `T10` pins that inversion directly.

The surprise was that two of the four fail-closed conditions Sol told us to
preserve did not exist. The single compound witness condition had been standing
in for them, so lifting it without building them would have converted a
fail-closed plane into a fail-open one while appearing to do the opposite. That
is worth remembering as a general shape: when one broad guard is removed, audit
what it was incidentally covering before assuming the narrower guards beneath it
are real.

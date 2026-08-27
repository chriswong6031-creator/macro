---
key: CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY
question: >
  `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION` made a `bak_basic` PIT observation
  the corroborating witness for a security the current `stock_basic` snapshot
  omits, and ordered PIT-only listing keys propagated into downstream acquisition
  including `name_history`. That propagation only reaches back to
  `PIT_UNIVERSE_START = 2016-01-01`. A pre-2016 `namechange` row therefore has no
  PIT partition to be propagated from, so the current snapshot is again the sole
  authority — the exact condition the previous ruling rejected. Does a valid
  `namechange` row require an external witness in order to EXIST in the
  name-history plane?
answer: >
  No. A valid `namechange` row is itself sufficient source evidence that TuShare
  asserted that historical listing-key/name observation. It requires no
  contemporary `stock_basic`, `bak_basic`, PIT or other external witness merely
  to exist in the name-history plane.

  The external-witness-as-completeness requirement is REPLACED with deterministic
  row disposition. Every source row receives exactly one of:

  * externally corroborated; or
  * valid namechange-only source observation (`NAMECHANGE_ONLY`); or
  * explicit conflict / quarantine.

  `NAMECHANGE_ONLY` counts as TERMINAL SOURCE COMPLETENESS and grants ZERO PIT
  membership, positive-volume trading, exact-event, canonical-identity, rank or
  score authority.

  Pre-2016 is NOT special-cased, and the observed witness-missing percentage is
  NOT an admission threshold. The rule applies row by row across the frozen
  epoch, and the witness-missing rate is reported as TELEMETRY.

  Malformed keys, contradictory lifecycle intervals, incomplete responses and
  unresolved source conflicts remain FAIL-CLOSED.

  The completeness manifest is amended so `complete` requires all source rows
  deterministically reconciled with zero unresolved conflicts — NOT 100% external
  corroboration.
rationale: >
  The previous ruling's PRINCIPLE — a current snapshot is not authority on
  historical membership — reached this case exactly. Its MECHANISM did not,
  because the PIT witness begins in 2016 and the affected rows are older. Sol
  resolved the gap by removing the dependency on any witness rather than by
  extending the witness, which is the stronger repair: it stops the program
  needing a corroborating plane to exist at all in order to record what the
  vendor said.

  The critical structural fact is that name-history is a LEAF. Verified against
  the merged tree: `build_canonical_event_substrate` reads only the `daily` and
  `stk_limit` partitions; `build_daily_security_coverage` reads only the security
  master, `daily`, and the PIT partitions; `_all_known_a_tickers` reads only
  `instrument_classification.parquet` and the PIT partitions. Nothing anywhere
  reads `store/name_history` except its own receipt builder. So admitting these
  rows creates NO new blocking condition one stage later — materially unlike the
  PIT case, where the same filter sat at three layers and two of them were terms
  in the manifest's own `complete` conjunction.

  That leaf property is also what makes the zero-authority clause cheap to
  enforce rather than merely asserted, and it is pinned by a negative-proof test
  that a namechange-only ticker never enters `_all_known_a_tickers`. Without that
  pin the rule could invert: a name-history row feeding back into the known-A set
  would let a namechange-only observation bootstrap itself into the very PIT
  membership authority this decision denies it.

  Two of the four fail-closed conditions Sol required to be PRESERVED did not
  exist and had to be BUILT. `normalise_name_history` carried no lifecycle
  interval validation at all, and because `KEY_COLUMNS["name_history"]` includes
  `name`, two rows asserting DIFFERENT names effective the same day for the same
  ticker did not trip the duplicate-key check — they both landed. The
  single compound witness condition had been masking both gaps, so removing it
  without building them would have converted a fail-closed plane into a
  fail-open one while appearing to preserve fail-closed behaviour.
alternatives:
  - option: Extend the PIT witness backwards before 2016 to corroborate old rows
    why_not: >
      No pre-2016 point-in-time source exists to extend it with. It would also
      keep the architecture dependent on a corroborating plane existing, which is
      the dependency this ruling removes.
  - option: Admit pre-2016 namechange rows as an era-scoped exception
    why_not: >
      Explicitly refused by Sol. An era exception is a survivorship filter with a
      date attached; it would still reject an unwitnessed 2019 row on the same
      bad reasoning, and it hard-codes a vendor coverage boundary into program
      law.
  - option: Admit rows while the witness-missing rate stays under a threshold
    why_not: >
      Explicitly refused by Sol. A threshold smuggles the same filter back as a
      tunable and makes a row's disposition depend on its neighbours rather than
      on its own evidence. The rate is telemetry only.
  - option: Relax the `quarantined_unknown == 0` gate so the unit goes terminal
    why_not: >
      Fail-open, and it destroys the distinction between a decided disposition
      and an unknown one. Refused for the identical shape in the PIT ruling.
  - option: Land namechange-only rows into the known-A universe as well
    why_not: >
      That is precisely the authority the ruling withholds. It would let a name
      assertion mint universe membership, inverting the graded-authority model.
evidence:
  - "DSC:CNLI-PRE-PIT-NAMECHANGE-ORPHANS-HAVE-NO-WITNESS — the measurement that forced the escalation."
  - "Canary run 33026983388 (mode=canary, max_requests=12, 2018-01-02): namechange reached 9 of 10 attempted units terminal; 1999:19991231 failed with reason namechange_orphans_absent_from_A_universe_witness at 193 = 192 + 0 + 1."
  - "The single quarantined row is 000991.SZ 通海高科 (start_date 19990101, change_reason 其他), classification_source namechange_absent_from_A_universe_witness; absent from the current 5,888-row security master while neighbouring 000900-000913 are present, so vendor coverage rather than a suffix-format artefact."
  - "Leaf verification on merged main fab40e11940c: grep for the name_history store path returns only its own receipt builder; build_canonical_event_substrate reads daily+stk_limit, build_daily_security_coverage reads master+daily+PIT, _all_known_a_tickers reads instrument_classification+PIT."
  - "collectors/china_tushare_spine.py normalise_name_history carried no effective_from/effective_to interval check, and KEY_COLUMNS['name_history'] includes `name`, so same-day conflicting names did not trip _duplicates — both fail-closed conditions had to be built rather than preserved."
affects:
  - WS:CN-LIMIT-ALPHA
  - collectors/china_tushare_spine.py
  - contracts/cn_tushare_a_share_spine_manifest.v1.schema.json
  - research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md
  - research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-27
---

# A vendor assertion is evidence of the assertion

Sol return-gate 10B under `DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION`, ruling the
escalation raised by `DSC:CNLI-PRE-PIT-NAMECHANGE-ORPHANS-HAVE-NO-WITNESS`.

Sibling and immediate predecessor: `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`.
Read the two together — this one is not a broadening of that one but its
completion, replacing "corroborate against a different plane" with "the source
row is its own evidence, and authority is granted separately from existence".

Reversibility is `costly` for the same reason as its predecessor: the decision
sets what the historical name-history plane CONTAINS, and any downstream
measurement frozen against that plane would be invalidated rather than merely
re-flagged by a reversal.

Two proofs ride with the ruling and are not separable from it. The REPLAY proof
shows that removing an external witness cannot delete a valid historical
name-history observation — only its disposition label changes. The NEGATIVE proof
shows that a namechange-only row cannot enter an exact eligible/event population
without independent qualifying evidence, and specifically that it never enters
`_all_known_a_tickers`.

`BULK_HISTORICAL_BACKFILL_READY` stays `False`. Under this gate Sol further ruled
that a clean acceptance canary is NOT required to exercise the ticker-range
campaign, because that capability is deliberately held behind the same flag:
exact-head canary plus range-shard adversarial tests may justify the separate
technical readiness PR, and the first post-promotion bounded range execution is
its production proof. DEP-EXACT remains open until the complete range campaign
and the sanitized completeness manifest. No DEP-ID-ELIG or downstream CN-Limit
feature work may begin before DEP-EXACT genuinely closes.

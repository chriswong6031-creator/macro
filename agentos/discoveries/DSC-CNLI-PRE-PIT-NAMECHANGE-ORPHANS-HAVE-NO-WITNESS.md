---
key: CNLI-PRE-PIT-NAMECHANGE-ORPHANS-HAVE-NO-WITNESS
claim: >
  Individual pre-2016 `namechange` rows name securities that the current
  `stock_basic` witness no longer publishes and that NO point-in-time witness can
  corroborate, so those units cannot reach terminal. The condition is RARE, not
  era-wide: of ten attempted year-units, 1990-1998 ALL reached terminal with ZERO
  quarantine (935 rows landed), and only 1999 failed, on exactly ONE row of 193 —
  1 orphan in 1,128 rows across ten years (0.09%), with 19 later years still
  unattempted. The mechanism is that the `bak_basic` PIT universe only begins at
  `PIT_UNIVERSE_START = 2016-01-01`.
  Measured 2026-08-27 on canary run 33026983388: the `1999:19991231` unit failed
  with reason `namechange_orphans_absent_from_A_universe_witness`, source_row_count
  193 = landed 192 + known_excluded 0 + quarantined 1. The quarantined row is
  `000991.SZ` 通海高科 (start_date 19990101, change_reason 其他), classified
  `namechange_absent_from_A_universe_witness`. `000991.SZ` is absent from the
  current 5,888-row security master; the master's ticker convention is confirmed
  `.SZ`/`.SS`/`.BJ` and neighbouring codes 000900-000913 ARE present, so this is
  genuine vendor coverage rather than a suffix-format artefact.
falsifier: >
  Re-run one bounded canary window covering a pre-2016 namechange year and read
  the unit, then search the current reference generation for the code:
  `python3 -c "import pathlib,sys; sys.path.insert(0,'.');
  from collectors import china_tushare_spine as sp;
  S=pathlib.Path.home()/'.local/share/macro-dashboard/china_tushare_spine';
  g=sp._current_reference_generation(S);
  m=sp._read_parquet_strict(sp._reference_derived_path(S,'security_master.parquet',g));
  print(len(m), '000991.SZ' in set(m.ticker.astype(str)))"`.
  Falsified if the code IS present in a fresh master (meaning the gap was a stale
  or partial reference refresh), or if every pre-2016 namechange year reaches a
  terminal unit with zero quarantine (meaning 1999 was an isolated case rather
  than a systemic era problem).
so_what: >
  This is the SAME survivorship shape that
  `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION` was minted to remove, reaching an era
  where that decision's MECHANISM does not exist. The decision made a PIT
  observation the corroborating witness for a security the current snapshot
  omits, and ordered PIT-only listing keys propagated into downstream acquisition
  including `name_history` precisely so the filter would not reappear one stage
  later. That propagation works — but only from 2016 onward. A 1999 namechange
  row has no PIT partition to be propagated from, so the current snapshot is once
  again the sole authority, which is exactly the condition the decision rejected.

  It is NOT, however, obviously covered by that decision, and must not be treated
  as such without an explicit ruling. The decision's fail-closed clause keeps
  "any unknown disposition" blocking, and a pre-2016 security with no current
  witness AND no PIT witness has no independent corroboration of any kind — which
  is materially weaker evidence than the `300114.SZ` case, where a same-session
  `bak_basic` observation existed. Admitting these rows on identity-derivation
  alone would let `name_history` land rows for securities nothing in the store
  can witness; refusing them leaves the affected years permanently non-terminal.
  `build_completeness_manifest` requires EVERY year from
  `NAME_HISTORY_START_YEAR = 1990` to `end.year`, so even a 0.09% orphan rate is
  fatal to completeness — one unclassifiable row in one year blocks the whole
  manifest. Scope any ruling to the RATE, not to the era: this is a handful of
  individual securities with no witness of any kind, NOT a systemic failure of
  pre-2016 name history, and 1990-1998 prove the era is otherwise clean.

  Consequence for sequencing: the acceptance canary CANNOT reach a terminal state
  on any window while this stands, independently of the `stk_limit` defect
  (`DSC:CNLI-STK-LIMIT-ZERO-PRE-CLOSE-SENTINEL`), because the manifest's expected
  namechange units always reach back to 1990 regardless of how recent the
  requested session is. Choosing an earlier canary date reduces the number of
  namechange years but never removes the pre-2016 ones.
scope:
  - macro
  - collectors/china_tushare_spine.py
  - WS:CN-LIMIT-ALPHA
kind: constraint
confidence: verified
verified_at: 2026-08-27
verified_by: >
  Canary run 33026983388 (mode=canary, max_requests=12, 2018-01-02, ref
  claude/cn-limit-pit-source-union): namechange reached 9 of 10 attempted units
  terminal, with `1999:19991231` failed / reason
  namechange_orphans_absent_from_A_universe_witness at 193 = 192 + 0 + 1. The
  retained payload at
  source_row_classification/quarantined_unknown/namechange/year=1999/month=12/part.parquet
  names 000991.SZ with classification_source
  namechange_absent_from_A_universe_witness. The current reference generation's
  security_master.parquet holds 5,888 rows with suffixes {.SZ 3084, .SS 2461,
  .BJ 343} and contains no 000991 entry, while 000900-000913 are present.
---

# The ruling's mechanism runs out before its principle does

Found driving the acceptance canary ordered by
`DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`. `name_history` had never executed
against the live vendor before this session, so a filter written into the
collector months ago fired for the first time here.

The principle behind the source-union decision — a current snapshot is not
authority on historical membership — applies to this row exactly as it applied to
`300114.SZ`. The mechanism does not: there is no pre-2016 point-in-time witness
to corroborate it, so admitting the row would rest on identity derivation alone.
That gap is an authority question rather than an implementation defect, and it is
returned to Sol rather than decided here, per the standing instruction not to
widen a ruling to a dependency it did not address.

Sibling: `DSC:CNLI-BAK-BASIC-PIT-ROWS-ABSENT-FROM-STOCK-BASIC-WITNESS`, the
post-2016 case that produced the decision.

## RULED — see `DEC:CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY` (2026-08-27)

Sol answered the escalation by removing the witness dependency entirely rather
than extending the witness backwards. A valid `namechange` row is now its own
sufficient source evidence; it lands as `NAMECHANGE_ONLY` with zero PIT,
trading, exact-event, canonical-identity, rank or score authority.

Two framings in this record were superseded by that ruling and are retained only
as the reasoning that led to it. Sol explicitly refused BOTH an era-scoped
exception and any use of the measured rate as an admission threshold, so the
closing advice here to "scope any ruling to the RATE, not to the era" was
answered by scoping it to NEITHER — the rule applies row by row, and the rate is
telemetry. The 0.09% measurement stands as a factual observation of how rare the
condition is; it carries no admission authority.

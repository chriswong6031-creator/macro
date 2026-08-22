---
workstream: WS:CHINA-ALPHA-INTELLIGENCE
session: claude/p1-r3a-crash-consistent-exception-fence
model: fable
ended_because: complete
mission: >
  P1-R3A, commissioned by Sol 2026-08-22 as REQUEST_CHANGES on #6242 with no
  rollback: once a P1-relevant malformed source observation has been excluded
  from canonical filings.parquet, its coverage exception must ALREADY be
  durable. Frozen ordering invariant: durable coverage exception -> canonical
  filtered filing-store commit; never filtered commit -> process-local handoff
  -> durable exception later. Amend P1-R3; do not invent P1-R4.
state_before: >
  #6242 (squash 4e9735088638) shipped the durable, company-scoped
  coverage-exception ledger and Sol accepted every one of its semantics: the
  obsfp1 evidence-key law, the canonical-identity firewall, exact-only
  reconciliation, no expiry of unresolved exceptions, globally-clean runs
  advancing last_success_utc while scoped exceptions stay open, the strict
  unreadable visits.parquet hub read, and the common-path render/live product
  proof. One blocker remained. The ledger became durable only inside
  china_visits.refresh() — AFTER china_filings.write_filings() had already
  committed a filtered canonical store that omitted the observation — bridged
  only by the process-local LAST_KEY_INTEGRITY["excluded_rows"] handoff. A
  hard kill in that window (the asia lane runs under one) erased the
  observation from EVERY durable store at once: absent from filings.parquet by
  construction, never written to coverage_exceptions.parquet, and aged out of
  CNInfo's 3-day re-pull (_NIGHTLY_LOOKBACK_DAYS == 3) within days. That is
  the P1-R3 forgetfulness mode again, one layer down.
changed:
  - path: collectors/china_visits.py
    what: >
      Adds persist_boundary_exceptions(malformed_rows, key_anomaly_fn,
      now_utc=None) -> receipt — the SINGLE entry point china_filings calls to
      make an observation durable before its commit. It reuses the existing
      law rather than exporting it: _is_p1_relevant_exclusion,
      _exception_fields, read_coverage_exceptions_strict, upsert_exceptions,
      _atomic_write, _exceptions_path. Contract: never raises (a raise here
      would sink the C0 asia lane through china_filings); returns
      {ok, n_relevant, n_new, n_reaffirmed, fingerprints, detail};
      `fingerprints` is populated ONLY after the durable write succeeds, so an
      unwritten exception can never suppress refresh()'s own harvest; returns
      immediately on empty/irrelevant input WITHOUT reading or writing, so a
      zero-exception night never creates the ledger file and "ledger absent"
      keeps meaning "normal empty state". refresh() now (a) reads
      boundary_persist_ok / boundary_fingerprints off the same-run
      china_filings outcome, (b) no longer harvests excluded_rows at all, (c)
      skips any visits_candidate observation whose fingerprint the boundary
      already made durable in this invocation, and (d) adds a refused fence as
      a GLOBAL upstream_degraded cause. The health receipt's
      coverage_exceptions block gains boundary_persist_ok.
  - path: collectors/china_filings.py
    what: >
      _commit_filings(df, path) extracted as a NAMED SEAM for the canonical
      commit, so the ordering invariant is observable by a mutation test
      instead of merely argued. _fence_coverage_exceptions(malformed) is the
      thin china_filings half — lazy-imports china_visits and calls
      persist_boundary_exceptions; an import failure or an unexpected raise
      both synthesize ok:False. write_filings() calls the fence immediately
      before _commit_filings() and RETURNS 0 without committing when it
      refuses, leaving filings.parquet byte-identical; LAST_KEY_INTEGRITY
      (and _zero_key_integrity) gain boundary_persist_ok and
      boundary_fingerprints. fetch() appends a typed errors[] entry on a
      refused fence — fail-soft, never a raise — placed AFTER
      `transport_ok = not errors` so a fence refusal can never masquerade as a
      transport failure.
  - path: tests/test_china_visits_collector.py
    what: >
      +445 lines. TestP1R3ACrashConsistencyFence carries Sol's ten
      discriminating tests in order (item1 --only china_filings; item2
      simulated hard stop + a later separate process; item3 ledger-write
      failure leaves filings.parquet byte-identical, item3b that refusal
      degrades the plane end to end; item4 one observation per source
      occurrence; item5 repeated occurrence -> one row, deterministic count;
      item6 malformed non-visit stays outside P1, item6b a blank title is
      harvested fail-closed; item7 a later well-keyed filing resolves to its
      real announcementId; item8 no fingerprint reaches any canonical
      identity; item9 P1-R1 ordering + cninfo concurrency end to end; item10
      the ordering mutation guard, item10b the common path stays free).
      TestPersistBoundaryExceptionsUnit pins the entry point's own contract.
  - path: tests/test_china_filings_collector.py
    what: >
      The LAST_KEY_INTEGRITY canonical-shape pin grows the two new keys. This
      is a deliberate shape change, not a relaxation — the pin exists so a
      consumer-visible shape can never drift silently.
  - path: scripts/agentos.py
    what: >
      UNRELATED MAIN-RED HEAL, carried here because `agentos validate` is a
      hard-gating CI step and this PR touches agentos/. HANDOFF_MODEL gains
      "sol": commit 3810cbf252ba landed the store's first Sol-authored handoff
      with model: sol, which the enum rejected, so validate exited 1 on main.
      Sol is the AI CEO seat, not a Claude/Codex model tier — forcing that
      record into one of the existing values would falsify its provenance, so
      the enum was widened rather than the record rewritten.
  - path: agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md
    what: >
      The p1r3 wave entry gains the P1-R3A crash-consistency completion (an
      amendment, deliberately NOT a p1r4 wave). The stale aggregate
      next_action was rewritten on Sol's instruction: its "P1 DONE / one open
      question" prose named a question #6229 had already closed and read as
      the cold-start frontier. It now states P1 = PARTIAL (normal path
      PROVEN_LIVE, malformed-evidence lifecycle BUILT_NOT_PROVEN) and names
      the single permitted next action.
  - path: agentos/decisions/DEC-CHINA-COVERAGE-EXCEPTION-LEDGER.md
    what: >
      New "Amended by P1-R3A" section: the ordering invariant, what is
      retained unchanged, and four rejected alternatives (a write-ahead
      journal, inverting P1-R1 to run refresh first, duplicating the
      fingerprint law in china_filings, and letting the fence fail open).
  - path: agentos/discoveries/DSC-CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-FORGETFULNESS.md
    what: >
      New "P1-R3A — a THIRD mode" section with its own falsifier. The
      generalizable lesson: a durable repair for a forgetting bug is not
      durable until the write that CAUSES the forgetting is ordered behind it.
verified:
  - claim: The three mutations Sol's tests exist to kill are actually killed.
    command: >
      Each mutation was applied to the real source, the suite re-run, then
      reverted. (A) canonical commit moved BEFORE the fence -> 2 failed
      (item3, item10). (B) same-invocation dedup guard replaced with
      `if False:` -> 1 failed (item4). (C) `boundary["ok"] = True` forced after
      the fence -> 2 failed (item3, item3b). Command:
      `python3 -m pytest tests/test_china_visits_collector.py -q -k P1R3A`.
  - claim: No regression in the China planes, in either collection order.
    command: >
      `python3 -m pytest tests/test_china_visits_collector.py
      tests/test_china_filings_collector.py tests/test_china_intel_hub_visits.py
      tests/test_china_intel_visits_render.py tests/test_china_intel_hub.py -q`
      -> 317 passed; the same five files in reversed order -> 317 passed.
      Module globals this code ASSIGNS to (LAST_RUN_OUTCOME,
      LAST_KEY_INTEGRITY) are not restored by monkeypatch.setattr, so order
      independence is a real property here, not a formality.
  - claim: The other consumers of these two collectors are unaffected.
    command: >
      `python3 -m pytest tests/test_china_special_situations_filings_migration.py
      tests/test_china_special_situations_truth_wave1.py
      tests/test_nightly_timings.py -q` -> 106 passed.
      tests/test_dataos_security_master.py fails 22/errors 70 in this
      worktree, but IDENTICALLY with collectors/china_filings.py and
      collectors/china_visits.py checked out from origin/main — a sparse-
      checkout artifact (data/reference/security_master.parquet is not on
      disk), not this diff.
  - claim: The agentos heal is real and the store validates.
    command: >
      `python3 scripts/agentos.py validate` exited 1 before the change (naming
      only agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-22-FLAGSHIP-
      INTELLIGENCE-FANOUT.md, committed at 3810cbf252ba and untouched by this
      session) and exits 0 after — 542 records, 0 errors, 27 warnings.
  - claim: transport_ok is still measured before any key-integrity error.
    command: >
      `grep -n "transport_ok = not errors" collectors/china_filings.py` -> 925;
      write_filings() is called at 927 and the new fence errors[] entry is
      appended at 973. Had the order been the reverse, a malformed-key-only
      run would masquerade as a transport failure and re-create the P1-R2
      plane-global blackout this wave family exists to remove.
unverified:
  - claim: >
      The fence behaves correctly against a real malformed CNInfo row in
      production.
    why: >
      Production has never produced one (54,078 accrued rows, zero malformed
      keys ever) and the commission forbids manufacturing malformed
      production input. The branch is proven by hostile fixtures and mutation
      tests only. This is the same evidentiary basis Sol accepted for P1-R2
      and P1-R3.
unresolved:
  - what: >
      The unreadable-accrued-store path does NOT persist the exception.
    detail: >
      write_filings() aborts on `_read_filings_strict() is None` BEFORE the
      fence, so a malformed observation seen on a night when filings.parquet
      is corrupt is not written to the ledger. The frozen invariant still
      holds — nothing commits on that path, so no filtered store forgets
      anything — and the plane is loudly source_failure meanwhile, refusing
      absence authority for every name. But if the store stays unreadable
      past the 3-day re-pull window, that observation is forgotten. Adding a
      second persistence site would weaken the single-fence property item10
      pins, so it was deliberately not done. Sol's call.
  - what: >
      A china_visits import failure blocks the canonical filings commit even
      when NO malformed row is P1-relevant.
    detail: >
      On the import-failure path the fence cannot measure P1 relevance, so it
      refuses. Requirement 3 read literally demands this, and erring toward
      not-forgetting is the right side; the blast radius is bounded because
      the fence is unreachable unless a malformed row exists at all. Named
      rather than silently softened.
  - what: >
      Unbounded per-company suppression (carried forward from P1-R3, unchanged).
    detail: >
      An open exception suppresses clean negative authority for its company
      with no expiry, TTL, prune, or operator lever. The realistic trigger is
      a CNInfo republish with a drifted publish_ts/adjunct_url/adjunct_type,
      which breaks the fingerprint permanently. An operator retirement path
      would be additive and would not violate the no-fuzzy-match law. Sol has
      this open from the #6242 report.
next_actions:
  - >
      The FIRST natural asia-close with HEALTHY CNInfo transport records the
      seven acceptance items: checkout contains the final repair;
      china_filings -> china_visits same-cycle order; clean source transport;
      known key-integrity accounting; balanced candidate accounting; readable
      exception ledger; clean zero-exception normal path; correct production
      dossier. As of 2026-08-22 production health.json reads
      upstream_degraded from a real `sse: HTTP 504 from CNInfo` with
      last_success_utc 2026-08-21T09:29:55Z — a 504 run is valid failure-state
      evidence but is NOT the clean-path acceptance receipt. Wait for a
      healthy night; never manufacture malformed production input.
do_not_redo:
  - >
      Do not re-add the LAST_KEY_INTEGRITY["excluded_rows"] harvest to
      china_visits.refresh(). The boundary already persisted those rows AND
      reported their fingerprints; re-harvesting double-counts every one of
      them. item4 kills it.
  - >
      Do not move the fence below _commit_filings(), and do not inline
      _commit_filings back into write_filings(). The seam exists so the
      ordering is observable; item10 records the real call order.
  - >
      Do not make the fence fail open. "Warn loudly and commit anyway" is
      exactly the defect: a filtered store that forgets what it filtered.
      item3/item3b kill it.
  - >
      Do not duplicate the fingerprint/upsert law inside china_filings. Two
      copies are free to drift, and P1-R2's whole contribution was making one
      predicate serve both boundaries. The commission forbids it explicitly.
  - >
      Do not add a second ledger, a retry database, a write-ahead journal, or
      a generic transaction framework. One ledger:
      data/china_visits/coverage_exceptions.parquet.
  - >
      Do not start L0, P1B, P2, R1 or R2. Still closed.
danger_areas:
  - >
      NEVER call monkeypatch.undo() in tests/test_china_visits_collector.py.
      pytest injects ONE shared monkeypatch object per test function, so
      undo() also reverts the file's autouse config.data_dir redirect. Measured
      this session: a later refresh() then wrote health.json into the REAL
      data/ of this sparse worktree — an unredirected write, which in a sparse
      checkout TRUNCATES the committed artifact. Recovery was `rm` the stray
      file then `git sparse-checkout reapply` to restore the SKIP_WORKTREE bit
      (deleting the file alone leaves git reporting ` D`). Both former undo()
      sites now use a one-shot failure closure and monkeypatch.setitem/delattr
      instead.
  - >
      The fence is INERT until a malformed P1-relevant row appears, which has
      never happened in production. That is what makes failing closed
      affordable — and also what makes this branch impossible to prove by
      watching production. Any future change here must keep the first-line
      early return: without it, every normal night pays a ledger read on the
      C0 asia lane where the render budget is law.
  - >
      A fence refusal means filings.parquet did not advance AT ALL that night
      — not just for the malformed row. That is intended (the alternative is
      forgetting), but it makes the ledger's writability a dependency of the
      whole China filings tape. If CNInfo ever starts emitting malformed ids
      at volume, revisit DEC:CHINA-COVERAGE-EXCEPTION-LEDGER §"What would
      reopen this" before this fence, not after.
prs: [6242]
decisions: ["DEC:CHINA-COVERAGE-EXCEPTION-LEDGER", "DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION"]
discoveries: ["DSC:CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-FORGETFULNESS",
              "DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP"]
---

# P1-R3A — crash consistency at the china_filings write boundary

## The one-sentence version

P1-R3 made the coverage exception durable; P1-R3A makes it durable **first**,
because a memory written after the write that causes the forgetting is not a
memory that survives a crash.

## Why this is an amendment and not a new defect

Sol's review found the third instance of one failure family, not a new one. The
family is: *an exclusion is only as true as the place it is remembered.*

- **P1-R2** remembered it in a counter — typed and counted, but per-run and
  plane-global, so it either latched forever or aged out silently.
- **P1-R3** remembered it in a durable ledger — but wrote that ledger after the
  canonical store had already committed without the observation.
- **P1-R3A** orders the memory ahead of the forgetting, and refuses the
  forgetting when the memory cannot be written.

Each repair was correct about the thing it repaired. Each left the next layer
at its inherited default. That is worth carrying forward as a review habit:
after fixing *what* is remembered, ask *when*, and then ask *in what order*.

## What a reader should check first

`collectors/china_filings.py` `write_filings()` — the fence block sits
immediately above `_commit_filings(final, path)` and nothing may come between
them. `collectors/china_visits.py` `persist_boundary_exceptions()` — the single
reused entry point. `tests/test_china_visits_collector.py`
`TestP1R3ACrashConsistencyFence::test_item10_mutation_committing_before_the_exception_is_killed`
— the guard that keeps the order from silently inverting again.

---
workstream: WS:CHINA-ALPHA-INTELLIGENCE
session: claude/p1-r3-coverage-exception-ledger
model: fable
ended_because: complete
mission: >
  P1-R3, commissioned by Sol 2026-08-22 after accepting #6229 with no rollback.
  Make a malformed institutional-visit observation remain truthfully remembered
  until deterministically reconciled, while limiting negative-authority
  suppression to the companies whose evidence is actually incomplete whenever
  scope is knowable. Supersede ONLY #6229's global/per-run exclusion-health
  semantics and its lack of durable excluded-observation memory.
state_before: >
  #6229 (squash c11b16500c15) had made malformed-announcementId exclusions
  typed and counted at both write boundaries, but left the exclusion's LIFETIME
  and SCOPE at their inherited defaults — per-run, and plane-global — because
  its commission was bounded to the two collector files. Those defaults fail in
  opposite directions depending only on where the malformed row sits, and the
  two places are jointly exhaustive, so the semantics could not be right for any
  malformed visit row at all. Production had never exercised either branch:
  54,078 accrued filings rows, zero malformed keys ever.
changed:
  - path: collectors/china_visits.py
    what: >
      Owner of the new durable coverage-exception plane. Adds the versioned
      observation-fingerprint law (_FINGERPRINT_VERSION "obsfp1",
      _FINGERPRINT_FIELDS, _fp_norm, observation_fingerprint,
      is_observation_fingerprint), the ledger store
      (_EXCEPTION_COLUMNS, _exceptions_path, load_coverage_exceptions,
      read_coverage_exceptions_strict), the P1-relevance filter
      (_is_p1_relevant_exclusion), the pure upsert and deterministic
      reconciliation (upsert_exceptions, reconcile_exceptions,
      is_unscoped_sec_code), and rewires refresh()'s cause composition so typed
      key exclusions are no longer a plane-global degradation. write_visits()
      gains the canonical-identity firewall and now returns -1 for a REFUSED
      append, distinct from "0 net-new".
  - path: collectors/china_filings.py
    what: >
      Carries the excluded malformed rows themselves (LAST_KEY_INTEGRITY gains
      excluded_rows) so china_visits can harvest them without china_filings ever
      importing china_visits, and adds two typed booleans to LAST_RUN_OUTCOME
      (transport_ok, key_integrity_known) so china_visits can separate a
      TRANSPORT degradation from a key-integrity condition instead of
      string-sniffing errors[]. `ok` semantics unchanged for every other consumer.
  - path: engine/china_intel_hub.py
    what: >
      _load_visits_context() loads the ledger and returns exception_codes /
      unscoped_exceptions / exceptions_readable, and now reads visits.parquet
      STRICTLY so a present-but-unreadable tape fails closed instead of
      rendering measured_no_event for every company. _visit_block() suppresses
      measured_no_event per company (or plane-wide when scope is unknowable)
      via the existing "not_yet_available" state plus a structured
      coverage_exception projection — no new top-level state enum.
  - path: templates/china_intel.html.j2
    what: >
      K2c institutional-visits block gains the not_yet_available branch
      (company-scope and plane-scope copy) and an incompleteness line rendered
      AFTER the visit rows when a company has both positive evidence and an open
      exception. Bilingual, plain words, no falsifier/refutation vocabulary.
  - path: tests/test_china_visits_collector.py
    what: >
      All 12 hostile items' collector half, the fingerprint law, the NaN
      robustness suite, the upsert/reconcile laws, and both D1 regressions.
  - path: tests/test_china_filings_collector.py
    what: excluded_rows carriage, transport_ok/key_integrity_known, isolation fixture.
  - path: tests/test_china_intel_hub_visits.py
    what: >
      Hub half of items 1/2/4/9/10, the backward-compatibility test proving a
      pre-P1-R3 visit_ctx never blocks measured_no_event, and hub-level
      NaN/NaT/pd.NA scoping tests.
  - path: tests/test_china_intel_visits_render.py
    what: rare-state copy assertions, both scopes, and the rows-plus-exception case.
  - path: agentos/discoveries/DSC-CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-FORGETFULNESS.md
    what: new discovery recording the repair-induced lifecycle defect (verified).
  - path: agentos/decisions/DEC-CHINA-COVERAGE-EXCEPTION-LEDGER.md
    what: new decision recording the durable scoped answer and eight rejected alternatives.
  - path: agentos/decisions/DEC-CHINA-KEY-INTEGRITY-TYPED-EXCLUSION.md
    what: >
      body-only amendment — re-affirms the four retained laws, records the one
      deliberate reversal (malformed-key conditions may now advance clean
      last_success_utc) and the lifting of the hub-edit prohibition.
  - path: agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md
    what: p1r3 wave added; p1r2 marked superseded-in-part (implementation retained).
verified:
  - claim: >
      D1 LATCH is real on the merged bytes — one pre-existing unkeyed
      institutional_visit row degrades the whole plane on every subsequent run
      and the plane never starts.
    command: >
      python3 scratchpad/probe_p1r2_defects.py (loads
      `git show c11b16500c15:collectors/china_{filings,visits}.py` into
      sys.modules under their real dotted names; lib.config.data_dir redirected
      to a tmp dir)
    result: >
      nights 1-5 each `status=upstream_degraded n_excluded=1
      coverage_start=None last_success_utc=None`.
  - claim: >
      D2 AGING FORGETFULNESS is real — a boundary-excluded observation is
      forgotten once it ages out of the 3-day re-pull window and the plane
      returns clean `ok`.
    command: same script, second scenario
    result: >
      night 1 upstream_degraded; nights 2-5 `status=ok n_excluded=0
      coverage_start='2026-08-22' health='ok'`; final candidate_accounting
      {'eligible': 1, 'represented_downstream': 1, 'typed_exclusions': 0,
      'exclusions_by_type': {}}; 0 visits rows for the excluded company and no
      on-disk artifact naming it.
  - claim: >
      That end state makes the DOSSIER assert a clean measured absence about a
      company whose visit filing was in fact observed.
    command: >
      python3 scratchpad/probe_p1r2_hub_half.py (loads
      `git show c11b16500c15:engine/china_intel_hub.py` the same way and calls
      _visit_block with health ok / coverage_start stamped / zero rows)
    result: >
      Company A -> state 'measured_no_event', detail 'no institutional-visit
      filing observed for this name since coverage start'; Company B -> 'ok'
      n_total=1.
  - claim: The Agent OS records are schema-valid and the validator really parses them.
    command: >
      python3 scripts/agentos.py validate; then a deliberate `kind:
      NOT_A_REAL_KIND` injection into the new DSC, re-run, revert
    result: >
      0 errors / 26 pre-existing warnings clean; the injection produced exactly
      1 error naming the new file (`[bad-enum]`), proving the 0 is not vacuous;
      reverted and re-validated to 0.
  - claim: >
      The new rare-state product surface renders correctly on desktop and
      mobile and leaks no internals.
    command: >
      python3 scratchpad/p1r3_render_fixture.py (renders the REAL template via
      scripts.build_china_intel._env against a fixture cmd_full) then
      scratchpad/pwvenv/bin/python scratchpad/p1r3_shoot.py
    result: >
      All six copy receipts PRESENT (both EN and ZH, both scopes, the
      rows-plus-exception line, and the untouched measured-null control); all
      nine negative assertions ABSENT — not_yet_available, coverage_exception,
      obsfp1, observation_fingerprint, upstream_degraded, announcementId,
      falsifier, 证伪, refuted. Crops written at 1092x254 (desktop, 2x) and
      371x619 (mobile, 3x).
  - claim: >
      The new ledger file will actually persist across nightly runs — it is not
      gitignored and the lane that owns it stages new files under data/ broadly.
    command: >
      git ls-tree origin/main -- data/china_visits/;
      git check-ignore -v data/china_visits/coverage_exceptions.parquet;
      grep -n "git add" .github/workflows/asia-close.yml
    result: >
      data/china_visits/ is tracked (visits.parquet, coverage.json, health.json,
      china_visits_summary.parquet); the ledger path is NOT ignored;
      asia-close.yml stages `git add data/` at lines 310 and 842, and daily.yml
      carries no china_visits unstage rule.
  - claim: >
      Blast radius is narrow — outside its own tests the visit plane has three
      readers, and no store-inventory guard enumerates data/china_visits/.
    command: >
      grep -rln "china_visits" scripts/ engine/ config/ .github/ lib/ app/;
      grep -rln "rglob(\"*.parquet\")|known_stores|expected_stores" scripts/ tests/ engine/ config/
    result: >
      scripts/collect.py (registry), engine/china_intel_hub.py (dossier),
      .github/ci/legacy-jobs.yml (test wiring). No inventory guard matches the
      new path.
  - claim: >
      Five correctness defects existed in the build and were fixed before merge.
    command: code review of the working diff plus an independent pytest run
    result: >
      (1) `x or ""` cannot normalize NaN (NaN is truthy) — a NaN sec_code became
      the literal 'nan', so an exception with no usable company identifier read
      as scoped to a nonexistent company, defeating requirement 4; pd.NA raised
      outright. (2) reconcile_exceptions counted ROWS not DISTINCT ids, so one
      announcement appearing twice left the exception open forever — D1's
      unexitable-latch shape one layer down. (3) A refused write_visits()
      returned 0 like "nothing to do", so the firewall could fire and the run
      still stamped coverage_start and reported ok. (4) An unreadable
      visits.parquet rendered measured_no_event for every company (pre-existing;
      load_visits swallows read errors by contract). (5) An unreadable ledger
      rendered as `stale` "source has not refreshed recently" — false on the
      facts and collapsing two of the four categories the commission requires to
      be distinguishable. All five verified present in the tree after fixing.
unverified:
  - claim: >
      The whole build is green in ONE pytest process across the six owning test
      files, and order-independent.
    what_would_verify: >
      python3 -m pytest tests/test_china_visits_collector.py
      tests/test_china_filings_collector.py tests/test_china_intel_hub_visits.py
      tests/test_china_intel_visits_render.py tests/test_china_intel_hub.py
      tests/test_gh_annotation_line_start.py -q  in a SINGLE process, plus one
      reverse-file-order run. A per-file green does not prove it: two tests were
      observed passing alone and failing in combination, the signature of a
      module global that monkeypatch cannot restore.
  - claim: >
      The malformed branch behaves correctly against real CNInfo data.
    what_would_verify: >
      It cannot be verified today and the commission forbids manufacturing the
      input: production has 54,078 accrued rows and ZERO malformed keys ever, so
      the branch has never fired. Hostile fixtures and mutation tests are the
      proof standard Sol set for it.
unresolved:
  - >
      Deployment/no-regression proof is owed on the first natural Asia-close
      containing this wave: checkout contains the merge; china_filings ->
      china_visits same-cycle order holds; normal well-keyed collection
      succeeds; candidate accounting balances; the persistent
      coverage-exception plane reads successfully; no normal-path regression;
      the dossier still renders the normal P1 product.
  - >
      A company that carries BOTH its own scoped exception AND a plane-wide
      unscoped condition reports only the company-scoped sentence. Both block
      the clean absence, so no authority is mis-stated, but the broader
      condition is not surfaced for that name. Deliberate (the specific sentence
      is more actionable); revisit if plane-wide conditions ever become common.
next_actions:
  - >
      Return the PR to Sol for adversarial review (the commission's stop
      condition). Do not start L0, P1B, P2, R1 or R2 from this seat.
  - >
      On the first natural Asia-close containing the merge, collect the
      deployment receipt listed under `unresolved` above.
  - >
      If that run shows coverage_exceptions.parquet being rewritten on nights
      where nothing changed, confirm the write guard (`if n_new_exc or
      n_reaffirmed_exc or n_resolved_exc`) is holding — parquet bytes are not
      byte-stable, so an unconditional nightly write would churn a data diff
      forever.
do_not_redo:
  - >
      Do NOT re-litigate whether #6229 was wrong. It was RIGHT about the
      mechanism and Sol retained it with no rollback; only its temporal and
      scope semantics are superseded. The shared key_anomaly() predicate, the
      no-synthetic-ID law, the strict unreadable-store ABORT and the mechanical
      candidate accounting are all still binding.
  - >
      Do NOT mint a fallback/composite canonical announcementId. Rejected twice
      now, in DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION and again here. The
      observation fingerprint is NOT that: it keys a coverage-exception evidence
      row only, is firewalled in code from reaching announcement_id, and is
      derived from fields that deliberately EXCLUDE the natural key.
  - >
      Do NOT append keyless rows to filings.parquet "so they are visible" —
      unbounded growth across the 3-day re-pull, settled in P1-R2.
  - >
      Do NOT add a new top-level health/dossier state enum for coverage
      incompleteness. The commission forbids it, and the hub routes on literal
      state strings so an unrecognized state falls through to measured_no_event
      — the exact silent conversion being repaired.
  - >
      Do NOT suppress negative authority plane-globally whenever any exception
      is open. It looks conservative but it simply reproduces the D1 latch under
      a new name. Plane-global is reserved for a genuinely unbounded scope: no
      usable sec_code, or an unreadable ledger.
  - >
      Do NOT fuzzy-match during reconciliation. A wrong match writes a real
      announcementId onto the wrong observation and closes the coverage
      exception with a lie — worse than leaving it open.
  - >
      Do NOT "fix" a ledger-unreadable test by relaxing its expectation to
      `stale`. That was defect (5); the branch order is the bug.
danger_areas:
  - >
      `x or ""` is unsafe on anything that survives a parquet round-trip: NaN is
      TRUTHY, so `float('nan') or ""` is nan and `str(...)` makes the literal
      'nan'; pd.NA RAISES TypeError on truth-testing. Use _fp_norm() /
      is_unscoped_sec_code(). This laundered an UNKNOWN identity into a fake
      known one — the same shape as the P1-R2 `or _zero_key_integrity()` bug.
  - >
      Module globals that the code ASSIGNS to (LAST_RUN_OUTCOME,
      LAST_KEY_INTEGRITY) are NOT restored by monkeypatch.setattr. Tests that
      touch them pass alone and fail in combination; running the owning suites
      in SEPARATE pytest commands hides it. Always verify in ONE process.
  - >
      _visit_block()'s no-rows branch ORDER is load-bearing product semantics,
      not style. Whichever branch fires first is the sentence the user reads,
      and the commission requires four categories to stay distinguishable.
  - >
      engine/china_intel_hub.py routes on LITERAL state strings. Any new state
      name falls through to measured_no_event, converting a degraded read into a
      clean absence. This is why the projection rides the existing
      not_yet_available value.
  - >
      load_visits() swallows read errors by contract and returns an empty frame.
      Never use it where an absence claim depends on the read; use the strict
      reader. The hub call site was changed for exactly this reason;
      load_visits() itself was deliberately left alone because other callers
      rely on its forgiving contract.
  - >
      This is a SPARSE worktree: data/, site/, mockups/, verify_shots/ are not
      checked out. Never `git add -A` an unexpected data/ or site/ diff, and
      never run the full pytest suite here (~1,700 artifact failures). Opt in
      with `python3 scripts/worktree_sparse.py add <dir>` before touching one.
decisions: ["DEC:CHINA-COVERAGE-EXCEPTION-LEDGER", "DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION"]
discoveries: ["DSC:CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-FORGETFULNESS",
              "DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP"]
---

## Why this wave existed at all

P1-R2 closed a real hole and closed it correctly. What it could not answer,
because its commission was deliberately bounded to the two write boundaries, is
how long an exclusion is TRUE for and over WHOM it suppresses. An exclusion that
is only COUNTED is not REMEMBERED: its truth has to outlive both the process
that observed it and the upstream window that re-supplied it, or the instrument
silently changes meaning as time passes. That is how a repair for a silent drop
produced two new silent lies — one that never stops talking (the latch) and one
that stops talking too soon (the forgetfulness).

The generalizable rule, and the reason this is worth reading before touching any
absence-authority plane in this repo: compute a degradation signal over the DELTA
you actually processed, never over an accrued store you re-read every night; and
scope negative-authority suppression to the entities whose evidence is actually
incomplete whenever scope is knowable. A plane-global refusal is honest only when
the affected identity genuinely cannot be bounded.

## How the defects were proven

Neither defect could be demonstrated from the working tree, because a builder was
editing those same files concurrently. Both were instead proven against the exact
merged bytes by reading each module from `git show <merge-sha>:<path>` and
exec'ing it into a module registered in `sys.modules` under its real dotted name
— which also makes china_visits' lazy `from collectors import china_filings`
resolve to the same merged bytes rather than to the tree. That technique is worth
reusing: it gives a first-hand behavioural receipt for code that is not, and need
not be, checked out.

## Test-evidence caveat for whoever reads the PR

Two tests were observed passing alone and failing in a combined run. Some of that
observation was made against a tree that was still being edited, so the combined
result is the only one that counts. Do not accept per-file greens as proof of
this build; the module-global leak described under `danger_areas` is invisible to
them by construction.

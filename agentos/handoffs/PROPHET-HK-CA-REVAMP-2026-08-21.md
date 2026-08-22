---
workstream: WS:PROPHET-HK-CA-REVAMP
session: prophet-shadow-contract (continuation of fable-handoff-hk-canada-prophet; branch claude/prophet-shadow-contract)
model: fable
ended_because: complete
mission: >
  LEDGER-ERA owed-session production settlement (four frozen legs per CEO Sol's
  2026-08-20 directive), then — on a clean receipt — open and land the
  SHADOW-CONTRACT wave (zero-authority rank/discovery challenger substrate,
  packet §9) without a further permission cycle.
state_before: >
  LEDGER-ERA merged 273883182d9b but unsettled (workflow-green is not
  settlement). Shadow substrate did not exist; packet §9 + two DEC precedents
  (paired-row conditions, own-column-family) governed its design.
changed:
  - path: agentos/workstreams/WS-PROPHET-HK-CA-REVAMP.md
    what: >
      ledger-era -> done with the full population-reconciled settlement
      receipt (every denominator difference accounted: 436 = 400 legacy + 36
      current; 36 = 18 filled-unmatured + 18 not-yet-fill-eligible); sentinel
      persistence follow-up diarized for ≈2026-08-26; shadow-contract ->
      in_progress with the frozen-contract state.
  - path: research/PROPHET_SHADOW_CONTRACT_V1.md
    what: >
      NEW — frozen storage+isolation contract for the HK/CA challenger
      substrate. Frozen only AFTER an Opus adversarial pre-implementation
      review FAILED the draft (5 merge-blocking: HK isolation-by-ordering was
      factually false; K1 vacuous at the CA call site; lane-gated no-op kills;
      unbounded schema-union in a public repo; incumbent_rank re-derivation).
      K-suite K1-K14 + positive-control / non-vacuity / static-fence standing
      clauses. Post-review clarifications block records n1/n2/n4 + the M4
      Lane-B key widening (security_ref_raw joined the key).
  - path: engine/board_shadow.py
    what: >
      NEW — market-parameterized {HK,CA} shadow writer: Lane A rank pairs +
      Lane B discovery stores under data/prophet_shadow/, schema allowlists +
      outcome/authority denylist that OUTRANKS the allowlist at the write
      seam, lane gates mirroring board_ledger (fail-closed), normalizer bound
      to board_ledger._definition_or_none by object identity, incumbent_rank
      read back from the board parquet (never re-derived), prospectivity
      triple-refusal (asof / wall-clock settle / behind-the-head),
      first_seen_at true-min carry, identity canonical_ref + raw-ref
      collision counting, deep-copy at entry, empty challenger registry with
      registry_state log lines, fail-soft into builds.
  - path: scripts/build_canada.py
    what: one fail-soft write_shadow call after the board-ledger block (downstream of the artifact write).
  - path: scripts/build_hk_library.py
    what: >
      one fail-soft write_shadow call BELOW the hk_standouts.json write —
      deliberately NOT at the append_board site, which sits ~189 lines
      upstream of publication with the published list objects mutable in
      scope (review finding F1).
  - path: tests/test_board_shadow.py
    what: >
      NEW — 40 tests: K1-K14 kills with positive-control arms (forcing
      off-lane collapses 19/36 of the original suite — controls are real),
      non-vacuity asserts, cross-store validator, repo-wide K6 static reader
      fence with per-file pinned token-form allowlist, write-surface fence
      (all writes confined to data/prophet_shadow/).
  - path: .github/ci/legacy-jobs.yml
    what: >
      new merge-gated `board-shadow-substrate` job (gate: code); PLUS
      engine/board_shadow.py added to unrun-picks-boards' curated
      scope-exclusive paths (the #6093-class closure red the post-build
      review caught live).
  - path: agentos/decisions/DEC-PROPHET-HKCA-SHADOW-IS-A-SEPARATELY-KEYED-LANE.md
    what: NEW — design decision record (sidecar stores vs paired row), with the compensating cross-store invariant.
verified:
  - claim: LEDGER-ERA settlement PASSED, all four legs, on production truth
    command: >
      artifacts + parquet pulled from origin/main (commits baf4cf7c9291 /
      5ba8447ca827, both merge-descendants; VPS checkout e34f091309a
      contains both); scorecard('CA') run against production parquet bytes;
      era-empty annotation read off engine job 96640561705; full receipt in
      the workstream ledger-era wave entry
    result: >
      era purity exact both markets; prior_record==raw legacy pools (400 CA /
      359 HK); scorecard metrics_scope=current_definition +
      historical_context{legacy_rows=400, counts_source=raw_ledger}; CA
      era-empty warning fired TRUTHFULLY (era genuinely all-unmatured)
  - claim: two-round adversarial review with EXECUTED mutation kills
    command: >
      round 1 (pre-implementation) FAILED the draft contract; round 2
      (post-build) hand-applied every K1-K14 mutation and ran the named
      tests — verdict MERGE-BLOCKED with 1 blocker + 6 major, all fixed in
      a755263c7c09 and each previously-escaping mutation re-executed to a
      FAIL; the one remaining gap (verbatim K3 named mutation) was executed
      by the commissioning session directly: 2 failed under mutation,
      40 passed after revert
    result: every kill fires; positive controls real; final suite 40 passed
  - claim: zero authority — no production reader, no artifact byte changed
    command: >
      grep -rn prophet_shadow over engine/scripts/app/admin/templates (only
      the module + 10 audited pre-existing unrelated substring hits);
      git diff --stat 2560a2ef..dca6e874 = exactly the 5 owned files
    result: confirmed by reviewer with executed leak probes
unverified:
  - claim: CA era-empty sentinel self-clears once 08-19 rows mature at 5d
    what_would_verify: >
      On/after ≈2026-08-26, the CA engine job of daily.yml no longer emits
      board-ledger-era-empty. If it persists once gradable current-era rows
      exist, that IS the defect it exists to catch — investigate, never
      silence (diarized in the workstream next_action).
unresolved:
  - >
    K1's rendered-page identity legs (canada.html / hk.html bytes) are not
    exercised by tests (sparse trees; all kills use tmp fixtures). The
    write-surface fence + K6 static fence + the CA e2e byte-identity leg are
    the compensating controls. A full-checkout integration test remains an
    option before any challenger PROMOTION wave.
next_actions:
  - "DONE: PR #6178 merged fc5282f438fb7a9566ff650961fc6ea0381e7019 (2026-08-21T11:36Z, sweeper on concluded-green); origin/main bytes verified identical over all 9 owned files."
  - "≈2026-08-26: sentinel persistence check (workstream ledger-era next_action)."
  - Next lawful waves per graph: hk-discovery, ca-intel (both depend only on shadow-contract); ca-pit is also unblocked (depends on ledger-era).
do_not_redo:
  - All LEDGER-ERA and CA-TRUTH do_not_redo entries (PROPHET-HK-CA-REVAMP-2026-08-20.md) remain binding.
  - Do not re-run the K1-K14 executed-mutation suite — executed and recorded on heads dca6e874/a755263c (round-2 review + commissioning session).
  - Do not move the HK write_shadow call back beside append_board (F1 — upstream of publication is a contract breach even if bytes match).
  - Do not "fix" canada_standouts.json to carry board_track — the artifact has NEVER carried it (single-write-site ordering, CA-TRUTH design); the scorecard's consumers are the rendered page + ca_track_ledger.json.
  - Do not narrow _LANE_B_KEY back to (session_date, security_ref, challenger_definition) — keep-first then destroys collision rows (M4).
danger_areas:
  - >
    The K6 fence's per-file token-form allowlist must be tended: a NEW
    legitimate use of the literal prophet_shadow anywhere outside
    engine/board_shadow.py requires an explicit reviewed allowlist entry, and
    bare occurrence COUNTS were proven maskable (net-zero swap) — never
    regress to counts.
  - >
    The denylist-outranks-allowlist property lives in _apply_write_seam's
    effective-schema filter; a refactor that reindexes against the raw schema
    re-opens the reviewed-one-line hole (FAMILY_REGISTRY minting size_/gate_
    columns that are denylisted yet written).
  - >
    Registry is EMPTY at merge by design; registry_state log lines are the
    only liveness signal until a challenger registers. Wire the stores into
    surface-freshness vocabulary in the wave that registers the first
    challenger — not before.
prs: [6178]
---

# Session narrative (cold-stranger summary)

Settlement strictly before construction: the LEDGER-ERA receipt was proven on
production bytes across both canonical lanes, with the run-color trap named
(the real CA bake concluded 'cancelled' from one late unrelated job while every
settlement job succeeded; the DST-twin run concluded 'success' building
nothing). One locus correction: the receipt spec expected board_track inside
canada_standouts.json, but the artifact has never carried it in any era — the
in-memory attach happens after the single write site; substance was verified
against the production parquet instead, and the correction is recorded so the
wrong expectation dies here.

The shadow substrate then ran the full loop twice over: contract drafted →
Opus review FAILED it (the draft's central isolation argument was factually
wrong for HK) → contract rebuilt and frozen → Sonnet build → Opus post-build
review MERGE-BLOCKED it (a live CI closure red plus five kills that did not
kill) → fixes → every previously-escaping mutation re-executed to a FAIL. The
wave's lesson, twice paid: a kill is only as real as the mutation someone
actually ran.

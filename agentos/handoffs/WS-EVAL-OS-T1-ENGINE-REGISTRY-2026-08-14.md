---
workstream: WS:EVAL-OS-T1-ENGINE-REGISTRY
session: claude/eval-os-w3-output-class (W3 addendum; W2 record below is claude/eval-os-t1-engine-registry-v2)
model: fable
ended_because: complete

mission: >
  Resume the parked T1 engine-registry branch per the CEO continuation directive
  2026-08-14: recover the parked work onto current main, close blockers B1/B2/B3 and
  majors M1-M4, give T1 its own isolated CI job (CEO ruling), keep the derivation
  trustworthy on current main, enumerate the curated output_class set without filling it,
  and ship as armed PR(s).

state_before: >
  claude/eval-os-t1-engine-registry parked 2026-08-12 at 352d537438b (3 substantive
  commits, no PR) with an honest continuation handoff: 378 engines derived, 67/67
  selftest, but a test forbade the guard's own fail-closed annotation (B1), a malformed
  qledger store read as zero desk rows (B2), the T1 CI steps sat at the front of the
  always-on neural-web job masking nine sibling suites (B3), two tests asserted live
  synapse.yml contents with a meta-test that could not see the real call shapes (M1),
  the ledger waterfall hopped cross-program (M2), the path heuristic's disclosure said
  filename (M3), and fail-closed existed only behind a --strict nothing ran (M4).
  The repo clone was shallow (boundary 2026-08-11).

changed:
  - path: engine/intelligence_registry.py
    what: "Ledger waterfall rule 4 restricted to same-owner_program hops with a (producer, owner_program)-keyed index — measured 6 of 7 live cross-program hops wrong or unearned; evidence enum renamed weak_path_heuristic; every filename-wording disclosure corrected; churn figures re-measured on full history."
  - path: scripts/build_intelligence_registry.py
    what: "_load_qledger counts unparseable lines (B2) and names them in unreadable_inputs; DATA_PLANE_INPUTS + input_plane() implement the plane jurisdiction as mechanism (a decorative first version was caught by its own mutation control); unparseable synapse/overlay/qual_ladder fail closed with named summaries, never tracebacks."
  - path: scripts/check_intelligence_registry.py
    what: "Blindness exit policy by plane (DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE): PR-plane blind exits 1 unconditionally in both output modes, data-plane (claims.jsonl) always represented and reds under --strict; C-1 rows now also print as plain stdout lines; selftest grew 67 -> 84 controls; write_fixture_root factored as the single fixture source; SynapseUnavailable sentinel replaces the bare-SystemExit key."
  - path: tests/test_check_intelligence_registry.py
    what: "B1 fixed (three-channel annotation budget, blindness budgeted at one); M1 fixed (live-content tests rebuilt on fixture roots); the meta-test is AST-based over the real call shapes (subprocess _run, build(REPO), guard.main/bare main, import aliases, direct subprocess.run of either CLI) with a 16-entry justified allowlist, set-equality both directions, and canned-source controls per evasive shape."
  - path: tests/test_intelligence_registry.py
    what: "Live-parseability and live-non-emptiness assertions moved to fixtures; corpus-append immunity re-encoded as a fixture pair (valid append invisible / malformed append flips INCOMPLETE); a healed corpus is pinned silent-and-green."
  - path: .github/ci/legacy-jobs.yml
    what: "The two T1 steps left the front of neural-web (restored byte-exact to main); new isolated intelligence-registry job (guard selftest + plain guard run + both pytest suites) — CEO ruling 2026-08-14; 188 jobs measured pre-add with zero exact-duplicate run signatures, so nothing could be safely consolidated."
  - path: config/house_law_checks.yml
    what: "Both T1 law entries re-wired to the isolated job; FAIL CLOSED known_limit records the plane cut and the deferred nightly-side --strict (owner T7); post-rebase the whole file was rebuilt as pristine-main + the two T1 entries after a keep-both conflict resolution was caught truncating main's ops.nightly_liveness entry."
  - path: research/MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md
    what: "T1 amended into T1a/T1b/T1c with the two 2026-08-14 rulings (isolated job; plane-split fail-closed) and honest churn figures."
  - path: research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md
    what: "The historical parking record landed verbatim under a COMPLETED banner naming what closed it."
  - path: agentos/decisions/DEC-EVAL-OS-BLINDNESS-EXITS-BY-PLANE.md
    what: "The jurisdiction decision: which blindness reds the PR lane and why."
  - path: agentos/workstreams/WS-EVAL-OS-T1-ENGINE-REGISTRY.md
    what: "Workstream record with waves, do_not_redo, landmines."

verified:
  - claim: "Guard selftest passes with every added control."
    command: "python3 scripts/check_intelligence_registry.py --selftest"
    result: "selftest: PASS (84/84), rc 0 (was 67/67 at park)."
  - claim: "Live derivation unchanged in size and clean: 378 engines, 0 structural violations, inputs complete."
    command: "python3 scripts/check_intelligence_registry.py"
    result: "intelligence registry: 378 engines, 0 structural violation(s), 212 content finding(s), inputs=complete — rc 0. Findings 222 -> 212: six engines lost an unearned cross-program ledger and four display-authority engines left the output_class-required set with it."
  - claim: "Both suites green on the rebased tree."
    command: "python3 -m pytest tests/test_intelligence_registry.py tests/test_check_intelligence_registry.py -q"
    result: "196 passed (165 at park)."
  - claim: "All 12 CI packs validate with the new isolated job; trigger closure, workflow YAML and the house-law registry are green."
    command: "for n in 0..11: python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index N --pack-count 12 --validate-only; python3 scripts/check_ci_trigger_closure.py; python3 scripts/check_workflow_yaml.py; python3 scripts/check_house_law_registry.py"
    result: "12/12 rc 0; closure OK; 86 workflow files OK; house-law rc 0 after the post-rebase registry rebuild."
  - claim: "The jurisdiction split is mechanism, not documentation — independently spot-checked by the orchestrator on top of the builder's 14/14 control battery."
    command: "Re-classify claims.jsonl as PR-plane (DATA_PLANE_INPUTS = frozenset()), pytest -k 'plane or jurisdiction or data'"
    result: "1 failed immediately; byte-identical restore -> 5/5 green."
  - claim: "T1 tests are clean under the append-only assertion law (P2, merged #5534)."
    command: "python3 scripts/check_append_only_assertions.py --selftest; python3 scripts/check_append_only_assertions.py"
    result: "Selftest OK; zero findings on tests/test_intelligence_registry.py and tests/test_check_intelligence_registry.py."
  - claim: "The branch's true change set touches only T1-owned + wiring files, with zero sibling deletions."
    command: "git diff --stat $(git merge-base origin/main HEAD) HEAD; git diff --diff-filter=D --name-only $(git merge-base origin/main HEAD) HEAD"
    result: "11 files, +6664/-8, no deleted files. (Raw diff vs origin/main tip shows wire-lane noise only because the shared clone's origin/main advances every few minutes.)"

unverified: []
# Post-merge addendum (same session, 2026-08-14 ~18:20Z): both previously-unverified claims
# are now VERIFIED — (1) ci-pack-7, the pack carrying the intelligence-registry job, PASSED
# on PR #5620's own proof run 31799422492 (the job's two steps green on the merge ref);
# (2) the PR merged as d13259abc51c at 17:31:13Z and every T1 file on origin/main is
# byte-identical to the branch head (git diff --quiet per file), with the job present in
# main's manifest. The agentos-validate merge-ref claim is subsumed: the PR merged through
# the sweep with no agentos red raised against it.

unresolved:
  - "PERMANENT VINTAGE RED, do not chase: merged PR #5620's head run 31799422492 keeps ci-pack-8 red forever — the dag-conformance drift (govrev pytest lane, introduced #5516, declared in config/dag.yml by #5655 only AFTER this merge). The run's checkout is the frozen merge commit (base 007eea93c053, pre-heal), so `gh run rerun --failed` re-executes the pre-heal vintage and cannot green; the diff's own proof is ci-pack-7 green on that same run. Any tooling that keys off the merged head's check state must treat this by the base-side exclusion, not by rerun."
  - "Claim-store corruption alerts everywhere and gates nowhere until a nightly-era lane passes --strict (deliberate cost of the plane cut; owner: T7 wave; recorded in the guard docstring, house-law known_limit and DEC)."
  - "output_class curation: 109 engines are required_but_uncurated (86 display-authority gate-trippers, 12 engine_input, 6 user_ranking, 5 gate_size). The set is derivable on demand (build() then filter output_class_reason == 'required_but_uncurated') — deliberately NOT committed as a list. Needs a bounded adjudication session (W3)."
  - "The engine-level authority roll-up is a MAX and overstates authority for low-tier siblings in the 32 mixed-tier cells — standing disclosure, consumers must read artifacts[].artifact_authority per-artifact."

next_actions:
  - "Sweeper merges the armed PR; then confirm the intelligence-registry job ran green on the merge (gh run view on the merge SHA's ci run)."
  - "W3: hand the 109-engine output_class set to a curation session; fill config/intelligence_registry_overlay.yml rows with citations, never mechanically."
  - "T7 wave: wire the guard's --strict into a nightly-era lane so data-plane corruption gates where the data-plane actor lives."

do_not_redo:
  - "Do not commit a generated registry or add a --check/equality/drift mode — two parked rounds did, both were scheduled fleet-wide reds; synapse.yml measured ~70 commits/14d on FULL history 2026-08-14."
  - "Do not re-fold T1 steps into neural-web at either end — run_ci_pack returns on the first non-zero step (CEO ruling: isolated job)."
  - "Do not restore the cross-program rule-4 hop (6 of 7 live hops wrong: engine/run.py::engine-fix had adopted hk-canada's ca_board.parquet) or tighten rule 1 to basename (5 of 35 true positives live in directory components)."
  - "Do not make claims.jsonl corruption red the PR lane without --strict — DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE; the reviewer reproduced one truncated line redding the job for every PR."
  - "Do not fill output_class mechanically; a wrong metric contract is worse than a disclosed null."
  - "Do not resolve keep-both YAML conflicts on config/house_law_checks.yml with a line filter — it truncated main's ops.nightly_liveness entry here; rebuild as pristine-main + own entries and prove parsed-form equality per main entry instead."

danger_areas:
  - "The AST meta-test freezes live-invoking call shapes with a 16-entry allowlist — new tests that run the guard/builder live must take --root fixtures or join the allowlist with a justification."
  - "config/house_law_checks.yml and .github/ci/legacy-jobs.yml are append-collision magnets (four sibling PRs in two days); the doc is GENERATED — resolve the yml, then check_house_law_registry --emit-docs, never hand-merge the doc."
  - "engine/neuralweb/synapse.py 2k2 (scored_path_surfaces value validation) is a values-only hard gate in the always-on synapse validator — reviewed and kept; requiring the key on all artifacts would change every open PR."
  - "The shared clone's origin/main ref advances every few minutes under the wire lanes — diff sanity must run against the merge-base, and any keep-both rebase resolution must be re-proven against pristine main afterward."

prs: [5620]
decisions:
  - "DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE"
---

## Cold-start orientation

Read `research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md` (now carrying its COMPLETED
banner) for the three-round history that produced the parked design, then the PR body for
the one-PR-instead-of-three justification (the workflow-yaml fence couples new test files
to legacy-jobs wiring per-PR; stacked PRs get zero CI here; a pack is one check, so partial
enforcement deadlocks). The single most important structural fact: the registry is a
DERIVED ON-DEMAND VIEW — nothing generated is committed, and both the guard and the tests
are built so that a legitimate nightly append or sibling synapse PR can never red them.

---

# W3 ADDENDUM (2026-08-14, session claude/eval-os-w3-output-class) — output_class adjudication

Same-day amendment per house rule (suffixed handoff filenames are dropped by latest-wins
ranking). Everything above this banner is the W2 fix-wave record, unchanged.

## What W3 did

Recomputed the required set on current main: exactly 109 required_but_uncurated
(86 display / 12 engine_input / 6 user_ranking / 5 gate_size — zero delta vs the W2
checkpoint). Adjudicated 107 into `config/intelligence_registry_overlay.yml`; left 2
deliberate nulls. `OUTPUT_CLASS_MISSING` 109 → 2; total content findings 212 → 105;
`AUTHORITY_WITHOUT_EVIDENCE` unchanged at 21 (different axis, untouched).

Final distribution: 59 descriptive / 21 predictive / 15 classification_state /
7 detection_event / 3 ranking / 2 salience. By authority — gate_size: 3 descriptive
certify-gates + fit_cycle_hazard predictive + basket_washout classification_state;
user_ranking: 3 ranking boards + regime-vector classification_state + spine descriptive +
signal_quality detection_event; engine_input: 8 predictive (6 qledger desks + 2 cycle
projections) + 4 descriptive recorders.

## Method + provenance (the judgement chain)

1. 12 sonnet evidence harvesters — producer write paths, live `data/` rows, consumers,
   governing prereg/charter docs → structured packets (scratch only, never committed).
2. Main-loop (Fable) adjudication of all 109 from evidence; personal code reads on 100%
   of gate_size + user_ranking producers.
3. 4 adversarial opus reviewers over 52 rows: 100% of the three authority strata, every
   flagged ambiguity, all three unresolved candidates, plus a stratified sample.
   Outcomes: 7 class flips accepted, 1 unresolved refuted, 2 unresolved confirmed,
   ~18 rationale evidence defects fixed before shipping. Zero flips in gate_size/
   user_ranking; every flip was evidence-driven, not taste.

## The judgement laws that emerged (bind future waves)

- **Authority is not semantics.** Where an output is consumed (gate/rank surfaces) never
  decides what it asserts. The regime vector holds user_ranking authority and is still a
  classification; the certify-gates hold gate_size authority and are still descriptive.
- **Origination decides recorder-vs-originator.** A cell whose producer computes/asserts
  the state/claim during its own execution carries that species (build_foresight,
  mag7_regime, the desks). A cell that transcribes a value computed by a different
  module's execution and adds grading/archival is the accountability recorder →
  descriptive (china_radar_ledger, china_standout_track, name_score_grader,
  btc_impulse/btc_regime ledgers, china_regime_store, board_ledger, both grade_us_board
  lanes). The predictive/detection record it grades belongs to the originating cell —
  which, if display-only today, earns its contract when it trips the gate.
- **Register-then-grade family rule (R4).** For forward-ruler ledgers: fire asserted
  in-cell + graded at a declared ruler → predictive; fire asserted elsewhere →
  descriptive; detection_event ONLY where a curated real-event ground truth exists
  (a precision/recall contract on self-defined arithmetic is uncomputable — that is what
  flipped btc_impulse and would have been wrong on oracle had tape_onset not carried
  confirm/false-positive accrual against declared conditions).
- **Validation gates are descriptive as a family.** Their verdicts assert measured
  historical evidence against preregistered bars, re-derivable by reconciliation; none
  reads its own prior output (no latching — verified per gate in review R1). The
  forward-return statistics inside them are the SUBJECT being reconciled, not claims
  being graded forward — say this explicitly to scorecard builders, or catalog §2's
  "no forward-return metric on descriptive" reads as a contradiction. intl_phase0's
  descriptive contract must re-derive `weight_cap` (live-applied continuous magnitude),
  not just verdict labels.
- **Substrate cells take the family species only when the family is homogeneous.**
  reflexes.py → detection_event (every reflex is a tripwire detector by constitution);
  qledger.py → descriptive (its desks span species, so no single family class is honest).
- **Same-schema siblings get the same class.** The cycle trio (CN/US/country) unified to
  predictive once review R2 proved the CN cell is promise-graded identically to its
  siblings (5,081 stamps on disk) and the restrictive CN grader is additive — its "can
  never earn" clauses withhold authority, not the assertion.

## The two deliberate nulls (CEO attention)

1. `engine/neuralweb/cortex.py::neural-web` — genuine two-species cell: shadow-tier LLM
   committee memo (generative; the cell's derived ledger, external consumer
   mastermind:context) + shadow-tier direction-0 attention stream (salience). No single
   metric contract is honest. Needs a CEO architectural ruling (split identity, or rank
   one artifact's species as the cell contract). Repair first regardless of ruling:
   `scripts/grade_cortex_attention.py` routes on falsifier TEXT substrings and coerces
   direction 0 to a LONG bet (`int(direction or 1)`) — the salience half cannot be
   evaluated honestly until that grader is fixed.
2. `engine/options_structure.py::momoedge` — declared structural schema is UNBUILT
   (schema+validator only, zero file I/O, no producer, no data; synapse notes say
   "Package D builder is future scope"). Curate when the producer ships.

## verified (W3 claims, each with its command)

- claim: "Recomputed required set is 109 and matches the W2 checkpoint."
  command: "build() then filter output_class_reason == 'required_but_uncurated'"
  result: "109 (86/12/6/5 by authority)."
- claim: "Overlay parses, obeys the four-key law, and clears exactly the curated findings."
  command: "python3 scripts/check_intelligence_registry.py"
  result: "378 engines, 0 structural violation(s), 105 content finding(s), inputs=complete; OUTPUT_CLASS_MISSING=2 (the two deliberate nulls)."
- claim: "Guard selftest and both suites green with the filled overlay."
  command: "python3 scripts/check_intelligence_registry.py --selftest; python3 -m pytest tests/test_intelligence_registry.py tests/test_check_intelligence_registry.py -q"
  result: "selftest PASS 84/84; 199 passed (196 at W2 + 3 new W3 acceptance controls)."
- claim: "Removing a curated row restores its finding; an eighth class and a blank rationale are refused."
  command: "pytest -k 'clears_the_missing_finding or eighth_output_class or blank_output_class'"
  result: "3 passed (new tests, fixture-based — no live invocation, no AST-allowlist entry needed)."

## unresolved (W3)

- "cortex + options_structure nulls above (deliberate; CEO checkpoint items)."
- "T7 metric-binding warning, cross-cutting: the qledger desks' 'hit' is a NON-REFUTATION
  endpoint whose no-skill null sits far above one-half (engine/desk_scorer.py:293-296;
  measured null ~0.816 for master_brain, dir_accuracy 0.571 vs hit_rate 0.857; two desks
  sit below coin-flip directionally while showing 0.52-0.70 hit rates). T7 must bind
  dir_accuracy or placebo-netted rates as the predictive ruler for desks — never the bare
  hit_rate field."
- "Executability gaps recorded, classes unaffected: policy_intent 0 scored rows;
  demand_chain nothing matures before ~Dec 2026; china_radar n_resolved=0;
  china_standout_track rank-IC reset by definition bump; name_score_grader grade() has
  no production caller (live mirror diverged in engine/prophet_miss_audit.py);
  intraday_flow stance null on all rows, legs L3-L5 unpopulated."
- "Registry hygiene observed in passing (NOT touched, per the W3 scope fence):
  39 of 64 '# --- N consumers ---' headers in config/synapse.yml disagree with their
  lists; scripts/audit_grading_closure.py maps each artifact to exactly ONE grader and
  omits grade_promises for china_sector_cycles (this mis-informed the harvest);
  engine/metabolism/memory.py's declared flat ledger path is stale (code writes per-lobe
  dirs); engine/basket_turn_cohort.py:592-596 writes registered:true without checking
  register_batch()'s per-claim status; config/reflexes.yml:131 declares graded:true for
  commodity_shock with no implementing grader."

## do_not_redo (W3 additions)

- "Do not classify a recorder cell by the species of the signal it records — the
  origination law above; re-litigating it requires new evidence that the cell itself
  asserts the claim."
- "Do not give a detection_event contract to any ledger graded only at a forward-return
  ruler with no curated event ground truth — the precision/recall contract is
  uncomputable (btc_impulse lesson)."
- "Do not cite consumer COUNTS from synapse.yml section headers (39/64 stale) and do not
  cite desk hit_rate as a skill number anywhere user-facing or rationale-facing."

prs: [5620, 5679]

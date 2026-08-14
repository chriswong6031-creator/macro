---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: prophet-fusion-pr1a (same worktree as PR-0, branch claude/prophet-fusion-pr1a)
model: fable
ended_because: ci_handoff
prs:
  - "#5593"
mission: >
  PR-1a of the fusion program: root-cause and fix the stalled US Context Vector
  accrual, ship the §13 telemetry columns, the canonical evidence-family registry
  (families.yml), and the arena harness skeleton with the frozen O1-O6 rulers and
  §9 validation law — all zero-authority, nothing touching Prophet's live rank path.
state_before: >
  PR-0 (#5593) merged 2026-08-14T10:03Z. Context-vector store had 4 stamped days
  (07-31, 08-05/06/07), nothing since — the nightly board ran while the store's
  fail-soft writer silently threw every night from 08-08.
changed:
  - path: engine/neuralweb/context_api.py
    what: "_regime_dim merge path (both sources current) now emits SCALARS ONLY —
      the history row's committed 29-field shape + 2 provenance extras
      (history_as_of, live_quad); it was emitting dict-valued regime__live/
      regime__history, the root cause of every failed append since 08-08"
  - path: engine/us_context_vector.py
    what: generalized object-column NaN→None sweep; runtime containment quarantine
      (unclassified non-scalar columns dropped from the stamp with a line-start
      ::warning, one column can no longer kill the night); loud line-start
      ::warning on append failure and on a quiet nightly append; §13 telemetry
      columns (16 new, zero authority); §13.7 buy-lane reconciliation receipt
  - path: engine/confluence_tiers.py + engine/signal_gate.py
    what: stoch_ob/stoch_bear/macd_bear + per-leg null-state surfaced onto the gate
      verdict (macd_bear NaN fail-open disclosed, not masked); gate DECISION
      byte-identity pinned by sha256 goldens taken from pre-edit HEAD
  - path: scripts/grade_us_prophet_candidates.py
    what: nightly staleness tripwire — ::warning when newest stamp trails as-of >2 sessions
  - path: scripts/build_stock_library.py
    what: wiring for the telemetry loads (read-off only)
  - path: research/prophet_fusion/families.yml + tests/test_prophet_fusion_families.py
    what: the canonical registry — 8 families / 54 members / 180 store columns homed
      exactly once; pit_status/coverage_floor/max_staleness/availability_field per
      member; forbidden_composites with decompose_to; authority all-false; 54 tests,
      34/34 mutation catches
  - path: scripts/prophet_fusion_arena.py + scripts/prophet_fusion_labels.py + tests
    what: arena harness skeleton — label builder (O1/O2/O3/O5; entry+confidence
      DEFERRED markers, never proxied), date-grouped walk-forward folds with
      purge/embargo + §9.2 minimum-usable-fold REFUSAL, PIT/contamination refusals
      (snapshot_not_pit, forward_only, forbidden composites, unregistered columns),
      fold-scoped normalizer, coverage accounting with null≠zero, dummy challenger
      end-to-end selftest; 82 tests, 4 live mutation receipts
  - path: tests/test_us_prophet_grades.py
    what: zero-authority fence allowlist gains scripts/prophet_fusion_labels.py with
      the read-only-outcome-consumer rationale (anti-fork law is why it imports the
      reader); fence meaning unchanged, any other new importer still fails by name
  - path: .github/ci/legacy-jobs.yml
    what: five new suites registered (two appended to the picks-boards step, three
      in a new fusion step in the same job) — audit_unrun_tests exit 0
  - path: data/us_prophet_rank/README.md
    what: new columns + the regime__basis boundary documented
verified:
  - claim: root cause reproduced empirically, not inferred
    command: run the real _regime_dim for today against tracked regime stores
    result: "merge path returned value={'history':{...},'live':{...}} — the dict columns"
  - claim: the producer can append a genuinely new nightly PIT row again
    command: scratchpad e2e_proof.py — scratch copy of the committed 2026-08 part,
      COLLECT_LANE=nightly, real context_frame, stamp 2026-08-14
    result: "new stamp landed (3 rows); 7,759 prior rows × 180 cols value-identical;
      34 regime__* columns all scalar; rerun keep-first idempotent (0 new); repo
      data/ untouched"
  - claim: the full PR-1a test set is green
    command: python3 -m pytest <9 suites> -q
    result: "285 passed (post-review-fix rerun)"
  - claim: gate decisions byte-identical after the veto-leg surfacing
    command: mutation receipt — flip stoch_bear comparison, 3 tests red; restore, green
    result: goldens predate the edit (recorded from git show HEAD)
  - claim: CI suite registration complete
    command: python3 scripts/audit_unrun_tests.py
    result: exit 0 (stale-baseline warnings pre-existing, unrelated)
  - claim: independent adversarial review ran before handoff, blockers resolved
    command: opus reviewer over the staged diff (10-attack list + receipts spot-check)
    result: "1 BLOCKER + 4 MAJOR + 7 ADVISORY; B1 (sue_z planned/wired vise) fixed by
      de-listing sue_z from planned_columns; M1 (three silent no-advance paths) fixed
      with line-start ::warnings incl. the caller-side wrap in build_stock_library;
      M2 (fence rationale unbacked) fixed with a label_only_stores declaration +
      TestLabelOnlyStores red-on-rot test; M3 fixed as a STORE-SCOPED
      data/us_prophet_rank/disclosed_gaps.json (deviation from the reviewer's literal
      board-file fix, reasoned in the file's purpose field: board gradeable:false
      semantics would wrongly discard the valid 08-12/13 outcomes); M4 (hub/attention
      outage indistinguishable from off-hub) fixed with outage ::warnings + honest
      comment; goldens independently reproduced 16/16 by the reviewer; post-fix:
      285 tests green, selftest ok, unrun audit exit 0"
unverified:
  - claim: tonight's real nightly stamps a fresh date with the fixed producer
    what_would_verify: "the first post-merge daily.yml run; the us-context-vector-stale
      warning stays silent and a new stamp_date appears — check the morning after"
  - claim: CI packs green on the full diff
    what_would_verify: PR checks concluding (merge-on-green armed)
unresolved:
  - "catalyst_class / psq_stage / day3_mark_class SKIPPED — no same-night per-ticker
    producer exists for any of them (carried-columns law: no schema that lies);
    building a producer is its own adjudication"
  - "gex_state shipped as gex_confirm_verdict — engine/gex_state.py is a different
    live vocabulary; one name over three vocabularies would split cohorts"
  - "live-ONLY regime path still returns the kitchen-sink dict (cannot fire while the
    history parquet is tracked; runtime containment quarantines it loudly if it ever
    does)"
  - "insider panel (2026q1 stall) and short-interest PIT dim chipped as separate
    repairs (task chips created this session); families.yml marks both honestly"
  - "Review advisories filed for PR-1b (fix-or-file per reviewer): A1 MDD ruler
    substitution receipt (emit outcome_columns + mdd_basis); A3 _safe_out_dir refuses
    only data/&site/; A4 dummy stamping not structurally enforced; A5 disclosed_gaps
    per-entry fail-open on missing gradeable; A7 planned-vs-real checks vacuous in
    sparse worktrees; registry coverage-decay invisibility (add wired_from dating and
    home the 18 new columns — the structural B1 fix); min_train/min_test kwargs
    exposed despite frozen-law comment"
next_actions:
  - "Verify the first post-merge nightly stamps a fresh context-vector date (§13.0
    closure); then flip w1 to done"
  - "PR-1b: baseline race on frames 2-3, counterfactual_replay-labelled,
    non-promotion-bearing, §8.7 power table beside it — NOT in this session"
  - "PR-1b input (harness builder finding): the registry's 180 store columns
    intersect retro_grades.parquet in only 2 columns (alpha, tier_cascade) — the C1
    feature space on the only deep frame is two columns until the store accrues"
do_not_redo:
  - "Do not re-diagnose the accrual stall — root cause is pinned by test
    (dict-valued regime merge) and the fix is mutation-receipted"
  - "Do not backfill the Aug 8-13 store hole — same-night values only; the hole is
    honest history (store law: no retroactive backfill)"
  - "Do not add a catch-all pytest collector — every suite is named by design;
    register new suites in legacy-jobs.yml steps"
danger_areas:
  - "The zero-authority fence allowlist now has 5 entries — any further importer of
    us_prophet_grades needs its own adjudicated allowlist entry with rationale"
  - "regime__basis flips recomputed_history→pit_live at the 08-14 boundary while
    values stay the history row's — documented in the store README; era-aware
    consumers stratify on it"
  - "The arena selftest's synthetic metrics are fixture properties — never quote
    them as findings (stamped dummy:true, non_promotion_bearing:true)"
---

Cold-stranger summary: the store stalled because a context-dimension producer began
emitting nested dicts the parquet schema-union could not absorb, and the writer's
fail-soft caught the explosion silently every night. The fix makes the producer
scalar-only, makes the boundary quarantine unknown non-scalars loudly, and makes
silence itself alarm (quiet-append + staleness warnings). Everything else in PR-1a
is measurement scaffolding under the frozen masterplan law — zero authority anywhere.

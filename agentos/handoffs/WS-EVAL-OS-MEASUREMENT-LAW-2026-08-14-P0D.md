---
workstream: WS:EVAL-OS-MEASUREMENT-LAW
session: claude/eval-os-p0d-matched-control
model: fable
ended_because: ci_handoff

mission: >
  Execute the CEO's P0d ruling on DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG:
  turn dormant matched-control support into a prospective, explicit,
  family-appropriate evidence contract — census before design, preregistered
  contract, three-state classification, registration-frozen controls, write-once
  control evidence clock, coverage-gated fail-closed promotion, no manufactured
  controls, no rewritten history, no data-conditioned evaluation.

state_before: >
  P0a/P0b/P0c-1/P1 merged; P0c-2 (#5584), P3 (#5577), P2 (#5534) and the sitrep
  (#5582) armed and in flight (all four merged during this session). Zero of
  46,695 claims carried a control; every control_only verdict ever published was
  the bench fallback until P0c-1 nulled it; emit_ladder_states hardcoded
  control_only=True for every family; the control-leg design question was open
  (sitrep §11).

changed:
  - path: research/EVAL_OS_P0D_CONTROL_CENSUS.md
    what: "Phase D0 derived census: every live family's control feasibility measured (stock_desk 95% / demand_chain 100% / altdata* 89% / intel_hub 72% / thematic_desk 0%); three silent defects recorded (intel_hub's dead ETF-into-GICS-map wiring, membership.parquet's dual sector vocabulary, the gate's controlled-subset-onto-full-cohort Wilson projection); classification with per-family rationale and named re-classification paths."
  - path: research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md
    what: "Phase D1 contract C1-C9, registered before implementation; amended once post-review, visibly, strengthening only (min(date,row) coverage; date-granularity cohort boundary; clock stamped with the triggering claim's own timestamp)."
  - path: engine/qledger.py
    what: "FAMILY_CONTROL_POLICY governed table + accessor; sector_gics_etf alias normalisation; sector_of_ticker (membership.parquet); control_leg_is_valid; write-once per-family control evidence clock (data/qledger/control_evidence_clock_start/) with the registrar-level hook in register/register_batch; matched_control_check (fail-closed C5.1 gate: clock -> coverage=min(date,row)>=0.95 -> >=25 controlled dates -> direction-correct Wilson on controlled rows only, refusing CLOCK_LEGACY); promotion_check_dispatch + _apply_policy_label; emit_ladder_states dispatches by policy and enumerates required families from day one."
  - path: scripts/grade_qledger.py
    what: "Readiness dispatches by policy; matched rows publish bench stats only under benchmark_baseline_* keys; readiness families = qual_ladder UNION required; per-basis parity for bi-market required families; not_applicable never 'approaching'."
  - path: tests/test_qledger_control_policy.py
    what: "48 tests, 18 mutation-backed adversarial controls incl. registrar->gate end-to-end with mixed batch ordering."
  - path: tests/test_w6_readiness_monitor.py
    what: "Seeds moved to the explicit clock — after P0c-1+P0c-2+P0d an unstamped legacy seed can never cross the gate, so the first-cross alert tests were unreachable-by-construction (they had been failing on main since P0c-1 merged; the suite runs in NO ci pack, so nothing reddened)."
  - path: config/qual_ladder.yml
    what: "Header CONFIRMER gate description now names the policy dispatch instead of a blanket 'vs matched control'."
  - path: research/MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md
    what: "Recon line corrected: control-capable substrate, no live claim ever carried one, prospective evidence begins when controlled claims register; L2 predictive contract policy-aware."
  - path: research/MASTERMIND_EVALUATION_STANDARDS.md
    what: "§5.1 restated: benchmark = universal baseline, matched control = stricter second basis per the governed classification; §12 checklist row policy-aware."
  - path: agentos/discoveries/DSC-CONTROL-VOCABULARY-MISMATCH-KILLED-EVERY-WIRED-CONTROL.md
    what: "Landmine record: the one producer that wired controls fed ETF tickers to a GICS-name map; the universe file speaks two vocabularies; normalise + count refusals."

verified:
  - claim: "Zero controls in the live store at session start (nightly-moving; the finding, not the count, is the invariant)."
    command: "python3 -c \"import json;c=[json.loads(l) for l in open('data/qledger/claims.jsonl') if l.strip() and not l.startswith('#')];print(len(c), sum(1 for x in c if x.get('control')))\""
    result: "46,695 claims, 0 with a control; 59,929 grade rows, 0 with control_ret (2026-08-14)."
  - claim: "The matched gate refuses at 10% row coverage even when every date has one controlled row."
    command: "PYTHONPATH=. python3 <scratchpad>/repro_coverage.py (reviewer's repro, re-run post-fix)"
    result: "control_coverage=0.1 (min of date 1.0, row 0.1), ELIGIBLE False, reason names both ratios."
  - claim: "Registration order cannot move the coverage denominator; a batch is never excluded from the cohort it started."
    command: "PYTHONPATH=. python3 <scratchpad>/repro_order.py"
    result: "cohort_rows=5 controlled=2 coverage=0.4 for BOTH orderings (was 1 vs 4, coverage 1.0 both)."
  - claim: "18 mutation controls each fail their named test and restore byte-identically."
    command: "Builder rounds 0+1 mutation tables; spot-verified independently by opus reviewer (3 mutations re-applied)"
    result: "All 18 caught; sha256 of engine/qledger.py re-confirmed after each restore."
  - claim: "Full qledger suite family green post-rebase onto main containing #5577+#5584."
    command: "python3 -m pytest tests/test_qledger.py tests/test_qledger_horizon_clock.py tests/test_qledger_control_policy.py tests/test_qledger_desk_adapter.py tests/test_qledger_evidence_clock.py -q"
    result: "306 passed (includes #5584's four legacy-authority tests running against the new dispatch)."
  - claim: "Live-store dispatch is sane and mints nothing: zero eligible=True anywhere; #5584's rule reaches benchmark families through the dispatch."
    command: "python3 -c 'from engine import qledger as q; ...promotion_check_dispatch...' over radar/stock_desk/demand_chain/us_importance_v0/intel_hub at 21/63"
    result: "radar@21 benchmark LEGACY_NOT_AUTHORITY_ELIGIBLE n=27; stock_desk/demand_chain matched_control not-begun; us_importance_v0 not_applicable; intel_hub benchmark ACCRUING n=13."
  - claim: "w6 + grade_qledger suites green after the seed heal."
    command: "python3 -m pytest tests/test_w6_readiness_monitor.py tests/test_grade_qledger.py -q"
    result: "49 passed."
  - claim: "No clock files ship; no data/ writes in the diff."
    command: "git diff --stat origin/main HEAD | grep data/ ; ls data/qledger/control_evidence_clock_start/ 2>&1"
    result: "No data/ paths in the diff; directory does not exist."

unverified:
  - claim: "stock_desk's first real nightly registration starts the control evidence clock with a valid GICS-derived control."
    what_would_verify: "After this PR merges, the morning after the next nightly: read data/qledger/control_evidence_clock_start/stock_desk.json on main; confirm its control is a sector ETF and its timestamp equals the triggering claim's own registration stamp."
  - claim: "The admin Experiments tab renders the new benchmark_baseline_*/evidence_basis fields without layout breakage."
    what_would_verify: "Open the Experiments tab after the first nightly writes the new readiness payload; the reviewer verified experiments_registry only reads keys that still exist, not the rendering."

unresolved:
  - "tests/test_w6_readiness_monitor.py and tests/test_grade_qledger.py run in NO ci pack (named nowhere in .github/ci/legacy-jobs.yml or ci.yml) — dark suites; the w6 one had been failing on main since P0c-1 merged (05:44Z) with zero CI signal. Chipped."
  - "Reviewer finding 4: a DECLARED control that cannot be priced produces no grade row (rule 5) and so leaves the cohort denominator entirely — an unpriceable control currently IMPROVES reported coverage vs no control. Low reachability (sector SPDRs all price); needs maturity-aware accounting. Chipped with the demand_chain wiring."
  - "Reviewer finding 9 / contract C2.3-C2.4: sector_gics_etf/sector_of_ticker have no production caller yet; demand_chain's adapter call (engine/demand_ledger.py, merged in #5577) passes no sector_of, and wiring it through membership.parquet WITHOUT the alias normalisation would half-null exactly as census D0-2 describes. Chipped."
  - "Main was fleet-red at session end (packs 0/7/8/9/11 + ci-gate on run 31782771758, other lanes' fires; #5606 healing pack-11 already merged; fresh baseline run 31795408835 in flight). Not this lane's fires; nothing absorbed per the P0d scope fence."

next_actions:
  - "Confirm this PR's merge; then the morning after the next nightly, read data/qledger/control_evidence_clock_start/ on main and record stock_desk's real clock start (or its honest absence) — the same protocol as P3's evidence clocks."
  - "Post-merge chip: wire demand_chain's sector_of via qledger.sector_of_ticker + sector_gics_etf (alias-normalised, refusals counted per C2.4) in engine/demand_ledger.py's _register_qledger_claims; include reviewer finding 4's unpriceable-control accounting."
  - "Post-merge chip: name tests/test_w6_readiness_monitor.py and tests/test_grade_qledger.py in a legacy-jobs.yml run step (they are dark today)."
  - "When a registration-time sector source covers >=95% of intel_hub's real flow (today 72%), re-classify via the governed table edit + pinning test + evidence, per census §5."

do_not_redo:
  - "Do NOT wire control_for_sector() into every producer (sitrep §11 recommendation-1 shape). Refuted by measurement: self-cancelling for radar/policy/thematic_desk (subjects ARE theme proxies); under-covering for intel_hub (72%) and altdata* (89%). Census §6."
  - "Do NOT derive a family's control policy from row contents ('rows carry controls, so evaluate on controls') — that is the data-conditioned evaluation the ruling forbids; policy comes from FAMILY_CONTROL_POLICY only (contract C1.4, pinned by test)."
  - "Do NOT 'fix' a required family's missing-control refusal by restoring any bench fallback; and do NOT pre-create control_evidence_clock_start files — a hand-written timestamp is the retrospective stamping the design forbids (C3.1/C9)."
  - "Do NOT compute control coverage over the controlled subset or over date clusters alone — min(date, row) over the ISSUED cohort, both disclosed (C4, amended post-review; one controlled row per date bought coverage 1.0 before the amendment)."
  - "Do NOT compare the cohort boundary at instant granularity — the clock is stamped with the triggering claim's own timestamp and membership compares UTC DATES; instant comparison excluded the clock's own batch and made the denominator order-dependent."

danger_areas:
  - "engine/qledger.py remains a many-lane file: this session's round-1 rebase DROPPED #5584's freshly-merged hunks silently (the builder resolved a conflict wholesale and reported the file 'untouched by main'); caught only by grepping for the sibling's constant before push. ALWAYS grep for a just-merged sibling's identifiers in the file after any rebase that replays large qledger.py commits — git diff --stat vs origin/main shows nothing when the drop is inside a modified file."
  - "tests seeded through make_claim WITHOUT horizon_unit are legacy-clock seeds; after P0c-2 they can never produce eligible=True at GRADED, so any alert/promotion test built on them is unreachable-by-construction. Seed the explicit clock (horizon_unit + the clock_version/horizon_unit/clock_market triple on grade rows)."
  - "Dark test suites: a file not named in a legacy-jobs.yml run step runs NOWHERE in CI — it can fail on main for days with zero signal (w6 monitor did exactly that since 05:44Z). Grep the manifest before trusting 'green locally' as fleet state."

prs: [5471, 5519, 5534, 5559, 5563, 5572, 5573, 5577, 5582, 5584]
discoveries:
  - DSC:CONTROL-VOCABULARY-MISMATCH-KILLED-EVERY-WIRED-CONTROL
---

## Cold-start orientation for the next Eval-OS session

The matched-control question is now a governed contract, not an open design
question. Read `research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md` (the law),
`research/EVAL_OS_P0D_CONTROL_CENSUS.md` (why each family is classified as it
is), then this handoff's `do_not_redo`.

The single most important thing to know: **matched-control evidence still does
not exist, and that is the honest state.** The classification says only
stock_desk and demand_chain OWE controls; the clock artifacts under
`data/qledger/control_evidence_clock_start/` are written by the registrar the
first time a prospective, control-carrying claim registers — stock_desk's can
start with the first nightly after this PR merges (#5577's sector wiring is
live), demand_chain's only after its sector_of wiring chip lands. No session
may create those files by hand. A required family can never promote on its
benchmark numbers; a benchmark family can never be described as
matched-control evaluated; and the words for the two must never share an
unlabelled sentence.

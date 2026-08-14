---
workstream: WS:EVAL-OS-MEASUREMENT-LAW
session: >
  claude/evalos-sitrep-wave2 (original record) · ADDENDUM #5609
  claude/eval-os-p0d-matched-control (the P0d contract session, folded in from a
  wrongly-named sibling file — see the FILENAME REPAIR note in the body) ·
  ADDENDUM-FOLLOWUP #5665 claude/eval-os-p0d-control-wiring (the two chipped
  P0d follow-ups: demand_chain's control wiring and reviewer finding 4)
model: opus
ended_because: ci_handoff

mission: >
  Deliver the CEO's 2026-08-13 measurement-law wave: close P0a, ship P0b (own-ruler
  grading), P0c-1 (direction-correct control hits) and P0c-2 (legacy may not originate
  authority), start P3 forward-only prospective registration for three desks, leave P1/P2
  armed untouched, disarm and replace the stale #5512 situation report.
  ADDENDUM #5609 (P0d): execute the CEO's ruling on
  DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG — matched control becomes a
  preregistered, prospective, per-family evidence contract
  (research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md), never an ambient code path.

state_before: >
  P0a parked after 5 build/verify rounds on a market-resolver blocker that later proved to
  be a malformed test of my own. #5512/#5519/#5534 armed and blocked behind a red main.
  No engine registered claims at its declared horizon; horizon_d carried no unit;
  in_scope_horizons could never reach 12 family-horizon pairs; promotion arithmetic was
  direction-blind.
  ADDENDUM #5609 (P0d): zero of 46,695 claims carried a control; emit_ladder_states
  hardcoded control_only=True for every family; the control-leg design question was open
  (sitrep §11).

changed:
  - path: research/EVAL_OS_SITREP_2026-08-14.md
    what: "Replacement situation report. Withdraws the 08-12 'one-line fix' diagnosis, records the six-round market-ruler history, the legacy/explicit discontinuity, P0b/P0c rulings, the zero-candidate P3 result, and raises the control-leg decision to the CEO."
  - path: agentos/discoveries/DSC-NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG.md
    what: "Dead-code discovery: the matched-control promotion arm has never run on live data; every control_only verdict was the bench fallback mislabelled."
  - path: agentos/workstreams/WS-EVAL-OS-MEASUREMENT-LAW.md
    what: "Workstream record with the five waves, landmines, and the do_not_redo list."
  - path: engine/qledger.py
    what: "Via PRs #5559/#5563/#5572/#5573: explicit horizon_unit contract, one resolver, market dispatch with agree-or-refuse, own-ruler grading <=63, direction-correct control_only."
  - path: engine/qledger_desk_adapter.py
    what: "Via PR #5577: forward-only translator + gate for stock_desk/thematic_desk/demand_chain."
  - path: engine/qledger_evidence_clock.py
    what: "Via PR #5577: write-once per-family evidence-clock start writer."
  - path: research/EVAL_OS_P0D_CONTROL_CENSUS.md
    what: "ADDENDUM #5609 — Phase D0 derived census: every live family's control feasibility measured (stock_desk 95% / demand_chain 100% / altdata* 89% / intel_hub 72% / thematic_desk 0%); three silent defects recorded (intel_hub's dead ETF-into-GICS-map wiring, membership.parquet's dual sector vocabulary, the gate's controlled-subset-onto-full-cohort Wilson projection); classification with per-family rationale and named re-classification paths."
  - path: research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md
    what: "ADDENDUM #5609 — Phase D1 contract C1-C9, registered before implementation; amended once post-review, visibly, strengthening only (min(date,row) coverage; date-granularity cohort boundary; clock stamped with the triggering claim's own timestamp)."
  - path: engine/qledger.py
    what: "ADDENDUM #5609 — FAMILY_CONTROL_POLICY governed table + accessor; sector_gics_etf alias normalisation; sector_of_ticker (membership.parquet); control_leg_is_valid; write-once per-family control evidence clock (data/qledger/control_evidence_clock_start/) with the registrar-level hook in register/register_batch; matched_control_check (fail-closed C5.1 gate: clock -> coverage=min(date,row)>=0.95 -> >=25 controlled dates -> direction-correct Wilson on controlled rows only, refusing CLOCK_LEGACY); promotion_check_dispatch + _apply_policy_label; emit_ladder_states dispatches by policy and enumerates required families from day one."
  - path: scripts/grade_qledger.py
    what: "ADDENDUM #5609 — Readiness dispatches by policy; matched rows publish bench stats only under benchmark_baseline_* keys; readiness families = qual_ladder UNION required; per-basis parity for bi-market required families; not_applicable never 'approaching'."
  - path: tests/test_qledger_control_policy.py
    what: "ADDENDUM #5609 — 48 tests, 18 mutation-backed adversarial controls incl. registrar->gate end-to-end with mixed batch ordering."
  - path: tests/test_w6_readiness_monitor.py
    what: "ADDENDUM #5609 — Seeds moved to the explicit clock: after P0c-1+P0c-2+P0d an unstamped legacy seed can never cross the gate, so the first-cross alert tests were unreachable-by-construction (they had been failing on main since P0c-1 merged; the suite runs in NO ci pack, so nothing reddened)."
  - path: config/qual_ladder.yml
    what: "ADDENDUM #5609 — Header CONFIRMER gate description now names the policy dispatch instead of a blanket 'vs matched control'."
  - path: research/MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md
    what: "ADDENDUM #5609 — Recon line corrected: control-capable substrate, no live claim ever carried one, prospective evidence begins when controlled claims register; L2 predictive contract policy-aware."
  - path: research/MASTERMIND_EVALUATION_STANDARDS.md
    what: "ADDENDUM #5609 — §5.1 restated: benchmark = universal baseline, matched control = stricter second basis per the governed classification; §12 checklist row policy-aware."
  - path: agentos/discoveries/DSC-CONTROL-VOCABULARY-MISMATCH-KILLED-EVERY-WIRED-CONTROL.md
    what: "ADDENDUM #5609 — Landmine record: the one producer that wired controls fed ETF tickers to a GICS-name map; the universe file speaks two vocabularies; normalise + count refusals."
  - path: engine/demand_ledger.py
    what: "ADDENDUM-FOLLOWUP — _register_qledger_claims passes sector_of=qledger.membership_gics_sector_of(root), so demand_chain (matched_control_required) finally registers CONTROLLED claims and its C3.1 clock can start. Passing no resolver registered every claim uncontrolled forever."
  - path: engine/qledger.py
    what: "ADDENDUM-FOLLOWUP — gics_sector_name (raw vocabulary -> canonical GICS NAME, alias-normalised) + membership_gics_sector_of (the C2.3 construction, returns the NAME because make_claim resolves control_for_sector itself); eight COHORT_ROWLESS_* classes + _cohort_rowless_class mirroring grade_claim step for step; matched_control_check gains today= and counts control-refused claims into the coverage denominator (C4.4); PromotionResult/as_dict gain n_control_refused_rows/_dates/cohort_rowless."
  - path: engine/qledger_desk_adapter.py
    what: "ADDENDUM-FOLLOWUP — C2.4 refusal accounting: every candidate classified into n_control_valid/n_control_missing with the cause split (sector_absent | vocabulary_unmapped | control_equals_subject_or_bench | no_sector_source), read off the CLAIM rather than a duck-typed resolver protocol; one bare-print ::warning per run for a matched_control_required family with missing controls, carrying the split and a sample of offending vocabulary values."
  - path: scripts/grade_qledger.py
    what: "ADDENDUM-FOLLOWUP — the three control-refusal fields published on the nightly readiness row beside n_cohort_rows."
  - path: research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md
    what: "ADDENDUM-FOLLOWUP — governed amendment: C4.4 added (maturity-aware accounting of rowless cohort members; only control_leg_refused enters the denominator), C2.4 implementation note (demand_chain wired), C7 controls 9-14, amendment log at the head. Strengthening only."
  - path: agentos/discoveries/DSC-SUFFIXED-HANDOFF-IS-INVISIBLE.md
    what: "ADDENDUM-FOLLOWUP — landmine record: a handoff filename with anything after the date is dropped by the compiler as older_handoff, so a second same-day session's record is invisible in compiled state."
  - path: agentos/handoffs/WS-EVAL-OS-MEASUREMENT-LAW-2026-08-14.md
    what: "ADDENDUM-FOLLOWUP — this file: the orphaned -P0D sibling folded in and deleted, so the workstream's newest state actually reaches a cold-start session."

verified:
  - claim: "P0a's negative controls remain green on MERGED main (the CEO's condition for closing P0a)."
    command: "python3 -c \"import sys;sys.path.insert(0,'.');import engine.qledger as q;print(q.resolve_claim_market({'desk':'china_news','claim_family':'china_news','scope':{'type':'entity','key':'0700.HK'},'bench':'2800.HK'}), q._ticker_market('^HSI'), q._ticker_market('600519.SS', provenance=q.MARKET_US), q._ticker_market('AAPL', provenance=q.MARKET_CN)[0])\" (run on origin/main)"
    result: "('HK','') ('HK','') ('CN','') None — hard suffix wins, index enumerated, inferred arm still refuses."
  - claim: "P0b is live on main and no ruler above 63 can enter the live grader."
    command: "python3 -c \"import sys;sys.path.insert(0,'.');import engine.qledger as q;print(q.in_scope_horizons(30), q.in_scope_horizons(126), q.GRADE_HORIZONS)\" (run on origin/main)"
    result: "[5, 21, 30] [5, 21, 63] (5, 21, 63) — own ruler included at 30, refused at 126, constant untouched."
  - claim: "No live qledger claim has ever carried a control leg."
    command: "Count over origin/main data/qledger/{claims,grades}.jsonl for claim['control'] and grade['control_ret']"
    result: "0 of 46,630 claims; 0 of 59,929 grade rows; 59,929 have bench_ret. Direction mix +1:6353 / -1:6508 / 0:33769."
  - claim: "P0b's ceiling is mutation-gated, not merely asserted."
    command: "Replace `if horizon_d <= ceiling and horizon_d not in hs:` with `if horizon_d not in hs:`, then pytest tests/test_qledger_horizon_clock.py -q"
    result: "21 failed (incl. 126 -> [5,21,63]); restored byte-identically, 385 passed."
  - claim: "P0c-1's direction rule is mutation-gated."
    command: "Replace `if direction * raw_control_excess > 0:` with `if raw_control_excess > 0:`, then pytest tests/test_qledger.py tests/test_qledger_horizon_clock.py -q"
    result: "test_p0c1_mirrored_bullish_and_bearish_produce_the_same_control_only_hit_rate failed; restored, 183 passed."
  - claim: "P3's forward-only gate is mutation-gated."
    command: "Replace `if window.fill_date <= today:` with `if False:`, then pytest tests/test_qledger_desk_adapter.py tests/test_qledger_evidence_clock.py -q"
    result: "4 failed; restored, 38 passed."
  - claim: "P3 registers zero claims today for all three families, by design."
    command: "Builder dry run against the committed desk stores (dry_run=True, throwaway temp store)"
    result: "stock_desk 703 rows -> 0 candidates; thematic_desk 259 -> 0; demand_chain 55 -> 0. All refuse as retrospective/no-call/region-excluded."
  - claim: "ADDENDUM #5609 — Zero controls in the live store at P0d session start (nightly-moving; the finding, not the count, is the invariant)."
    command: "python3 -c \"import json;c=[json.loads(l) for l in open('data/qledger/claims.jsonl') if l.strip() and not l.startswith('#')];print(len(c), sum(1 for x in c if x.get('control')))\""
    result: "46,695 claims, 0 with a control; 59,929 grade rows, 0 with control_ret (2026-08-14)."
  - claim: "ADDENDUM #5609 — The matched gate refuses at 10% row coverage even when every date has one controlled row."
    command: "PYTHONPATH=. python3 <scratchpad>/repro_coverage.py (reviewer's repro, re-run post-fix)"
    result: "control_coverage=0.1 (min of date 1.0, row 0.1), ELIGIBLE False, reason names both ratios."
  - claim: "ADDENDUM #5609 — Registration order cannot move the coverage denominator; a batch is never excluded from the cohort it started."
    command: "PYTHONPATH=. python3 <scratchpad>/repro_order.py"
    result: "cohort_rows=5 controlled=2 coverage=0.4 for BOTH orderings (was 1 vs 4, coverage 1.0 both)."
  - claim: "ADDENDUM #5609 — 18 mutation controls each fail their named test and restore byte-identically."
    command: "Builder rounds 0+1 mutation tables; spot-verified independently by opus reviewer (3 mutations re-applied)"
    result: "All 18 caught; sha256 of engine/qledger.py re-confirmed after each restore."
  - claim: "ADDENDUM #5609 — Full qledger suite family green post-rebase onto main containing #5577+#5584."
    command: "python3 -m pytest tests/test_qledger.py tests/test_qledger_horizon_clock.py tests/test_qledger_control_policy.py tests/test_qledger_desk_adapter.py tests/test_qledger_evidence_clock.py -q"
    result: "306 passed (includes #5584's four legacy-authority tests running against the new dispatch)."
  - claim: "ADDENDUM #5609 — Live-store dispatch is sane and mints nothing: zero eligible=True anywhere; #5584's rule reaches benchmark families through the dispatch."
    command: "python3 -c 'from engine import qledger as q; ...promotion_check_dispatch...' over radar/stock_desk/demand_chain/us_importance_v0/intel_hub at 21/63"
    result: "radar@21 benchmark LEGACY_NOT_AUTHORITY_ELIGIBLE n=27; stock_desk/demand_chain matched_control not-begun; us_importance_v0 not_applicable; intel_hub benchmark ACCRUING n=13."
  - claim: "ADDENDUM #5609 — w6 + grade_qledger suites green after the seed heal."
    command: "python3 -m pytest tests/test_w6_readiness_monitor.py tests/test_grade_qledger.py -q"
    result: "49 passed."
  - claim: "ADDENDUM #5609 — No clock files ship; no data/ writes in the P0d diff."
    command: "git diff --stat origin/main HEAD | grep data/ ; ls data/qledger/control_evidence_clock_start/ 2>&1"
    result: "No data/ paths in the diff; directory does not exist."

  - claim: "ADDENDUM-FOLLOWUP — All 50 distinct demand_chain subjects resolve to a GICS sector ETF through the wired construction, reproducing census §3's 100%."
    command: "Probe over the COMMITTED blobs (git cat-file -p origin/main:data/demand_chain/theses.jsonl and :data/universe/membership.parquet into a scratch root), resolving each falsifier.check.subject_ticker through qledger.membership_gics_sector_of"
    result: "50/50 resolved, 0 sector_absent, 0 vocabulary_unmapped; XLK 15 / XLI 14 / XLU 10 / XLV 6 / XLB 3 / XLE 1 / XLF 1; no control equals its subject or SPY. Across the file's 2,898 distinct tickers, 988 (34.1%) carry a Yahoo-vocabulary value that would register control=None without the alias normalisation."
  - claim: "ADDENDUM-FOLLOWUP — The wiring puts a real control on the STORED claim row and starts the C3.1 clock; dry_run does neither."
    command: "register_prospective against a temp root with a synthetic membership mixing both vocabularies, then re-read claims.jsonl and data/qledger/control_evidence_clock_start/demand_chain.json from disk"
    result: "NVDA sector='Information Technology' control='XLK' (Yahoo 'Technology' normalised), JNJ -> XLV ('Healthcare'), unknown vocabulary and off-index ticker both control=None and counted; clock stamped with the triggering claim's own registration timestamp. dry_run: same split, clock still None."
  - claim: "ADDENDUM-FOLLOWUP — 13 adversarial controls each fail their named test and restore byte-identically."
    command: "scratchpad mutate.py harness: apply -> pytest the named test -> restore -> sha256sum the four source files"
    result: "13/13 caught (incl. denominator revert -> test_f4_declaring_an_unpriceable_control_cannot_beat_declaring_none; classify-all-rowless-as-refused; primary-leg attribution; in_scope_horizons removal; empty-cohort early return). sha256 identical before/after for all four files."
  - claim: "ADDENDUM-FOLLOWUP — The qledger suite family is green with the follow-up, and no existing test was modified."
    command: "python3 -m pytest tests/test_qledger_control_policy.py tests/test_qledger_desk_adapter.py tests/test_qledger.py tests/test_qledger_horizon_clock.py tests/test_qledger_evidence_clock.py tests/test_grade_qledger.py -q"
    result: "340 passed (control_policy 59 (+12), desk_adapter 37 (+7), qledger 48, horizon_clock 172, evidence_clock 8, grade_qledger 16). test_gh_annotation_line_start.py 4 passed. Both test files are append-only in the diff."
  - claim: "ADDENDUM-FOLLOWUP — The orphaned -P0D handoff was invisible to the compiler, and the fold-in repairs it."
    command: "python3 scripts/agentos.py compile-context --workstream WS:EVAL-OS-MEASUREMENT-LAW (before and after)"
    result: "Before: excluded {kind: handoff, key: ...-2026-08-14-P0D, reason: 'older_handoff (latest: ...-2026-08-14)'} and the bundle served the PRE-P0d record. After: 0 exclusions, the P0d state present in the served excerpt. validate: 56 records, 0 errors."
  - claim: "ADDENDUM-FOLLOWUP — tests/test_communique_diff.py's 10 local failures are a SPARSE-tree artifact, not a main break or a lane regression."
    command: "python3 -m pytest tests/test_communique_diff.py -q here; then the same file against a clean extract of origin/main (git archive origin/main tests engine scripts config lib)"
    result: "10 failed / 5 passed identically in both; engine/communique_diff.py reads data/china_official/phrase_book.yml, which a sparse worktree omits, so rows come back []. Main's own baseline has that pack green — do not chase it."

unverified:
  - claim: "P0c-2 (legacy may not originate authority) meets its acceptance bar."
    what_would_verify: "Its builder's mutation controls, then an orchestrator re-run of both: (a) legacy-only family eligible again -> a test must fail; (b) legacy N + explicit N summed for the threshold -> a test must fail."
  - claim: "The first nightly actually writes evidence_clock_start files for the three families."
    what_would_verify: "After #5577 merges, read data/qledger/evidence_clock_start/ on main the morning after the next nightly."
  - claim: "P2 (#5534) has no genuine defect behind its unrun-government-revenue-grader red."
    what_would_verify: "Read the ci-pack-3 job log for that step; confirm whether the govrev grader is failing on the merge ref for a reason unrelated to #5534's diff."
  - claim: "ADDENDUM #5609 — stock_desk's first real nightly registration starts the control evidence clock with a valid GICS-derived control."
    what_would_verify: "After #5609 merges, the morning after the next nightly: read data/qledger/control_evidence_clock_start/stock_desk.json on main; confirm its control is a sector ETF and its timestamp equals the triggering claim's own registration stamp."
  - claim: "ADDENDUM #5609 — The admin Experiments tab renders the new benchmark_baseline_*/evidence_basis fields without layout breakage."
    what_would_verify: "Open the Experiments tab after the first nightly writes the new readiness payload; the reviewer verified experiments_registry only reads keys that still exist, not the rendering."

unresolved:
  - "[SUPERSEDED by #5609] The control leg (DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG) — CEO decision requested in sitrep §11: wire control_for_sector() at registration, or stop claiming a control arm. RESOLVED: the CEO's P0d ruling is executed as research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md; universal wiring was REFUTED by the census (see do_not_redo)."
  - "engine/source_registry.py is a second horizon implementation on a live grading path; its while loop is unbounded where the clock's walkers fail closed."
  - "Two aggregations outside qledger pool across clock bases (source_registry hit_rate, report_importance_duel::_slice_stats). Single-basis today; fuse is the first night new claims mature."
  - "The claim-side clock_market stamp is write-only — nothing reads it, so its stated 'a suffix-table change becomes visible' guarantee is not implemented."
  - "ADDENDUM #5609 — tests/test_w6_readiness_monitor.py and tests/test_grade_qledger.py run in NO ci pack (named nowhere in .github/ci/legacy-jobs.yml or ci.yml) — dark suites; the w6 one had been failing on main since P0c-1 merged (05:44Z) with zero CI signal. Chipped."
  - "ADDENDUM #5609 — Reviewer finding 4: a DECLARED control that cannot be priced produces no grade row (rule 5) and so leaves the cohort denominator entirely — an unpriceable control currently IMPROVES reported coverage vs no control. Low reachability (sector SPDRs all price); needs maturity-aware accounting. Chipped with the demand_chain wiring."
  - "ADDENDUM #5609 — Reviewer finding 9 / contract C2.3-C2.4: sector_gics_etf/sector_of_ticker have no production caller yet; demand_chain's adapter call (engine/demand_ledger.py, merged in #5577) passes no sector_of, and wiring it through membership.parquet WITHOUT the alias normalisation would half-null exactly as census D0-2 describes. Chipped."
  - "ADDENDUM #5609 — Main was fleet-red at that session's end (packs 0/7/8/9/11 + ci-gate on run 31782771758, other lanes' fires; #5606 healing pack-11 already merged; fresh baseline run 31795408835 in flight). Not this lane's fires; nothing absorbed per the P0d scope fence."

next_actions:
  - "ADDENDUM-FOLLOWUP — The morning after the first nightly that follows this merge, read data/qledger/control_evidence_clock_start/demand_chain.json on main: demand_chain's control leg is now wired, so its clock should start with a sector-ETF control, or the run's ::warning should name why it did not (sector_absent / vocabulary_unmapped counts). Record whichever happened — the honest absence is a result."
  - "ADDENDUM-FOLLOWUP — Watch the first nightly ::warning for demand_chain-qledger-control-missing. A non-zero vocabulary_unmapped there means a producer is feeding RAW vocabulary somewhere (the D0-1 shape); sector_absent means membership.parquet does not carry the subject."
  - "ADDENDUM #5609 — The morning after the next nightly, read data/qledger/control_evidence_clock_start/ AND data/qledger/evidence_clock_start/ on main; record stock_desk's real control-clock start (or its honest absence) and the three P3 evidence-clock starts. No session may write those files by hand."
  - "ADDENDUM #5609 — Post-merge chip: wire demand_chain's sector_of via qledger.sector_of_ticker + sector_gics_etf (alias-normalised, refusals counted per C2.4) in engine/demand_ledger.py's _register_qledger_claims; include reviewer finding 4's unpriceable-control accounting."
  - "ADDENDUM #5609 — Post-merge chip: name tests/test_w6_readiness_monitor.py and tests/test_grade_qledger.py in a legacy-jobs.yml run step (they are dark today)."
  - "ADDENDUM #5609 — When a registration-time sector source covers >=95% of intel_hub's real flow (today 72%), re-classify via the governed table edit + pinning test + evidence, per census §5."
  - "T1 resumes in a FRESH session from research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md — deliberately not restarted here."
  - "[DONE #5609] Take the CEO's ruling on the control leg (sitrep §11) and open the follow-up PR it implies. — executed as the P0d census + preregistered contract; do NOT re-open the design question, read the contract."
  - "[DONE] Confirm #5534, #5577 and the P0c-2 PR merged; capture their merge SHAs. — all merged during the P0d session."

do_not_redo:
  - "ADDENDUM-FOLLOWUP — Do NOT have a `sector_of` resolver return an ETF ticker. make_claim resolves control_for_sector(sector) ITSELF, so a resolver handing back 'XLK' feeds an ETF into a GICS-NAME map — census D0-1 in reverse. Resolvers return the canonical GICS sector NAME; the invariant control_for_sector(gics_sector_name(v)) == sector_gics_etf(v) is pinned by test."
  - "ADDENDUM-FOLLOWUP — Do NOT count a rowless cohort claim into the coverage denominator unless its DECLARED control refused the shared window. not_yet_matured is a young claim, primary_leg_refused is the subject's data gap (ungradeable on any basis), horizon_out_of_scope can never grade there — counting any of them manufactures a coverage failure out of an unrelated fact (C4.4)."
  - "ADDENDUM-FOLLOWUP — Do NOT write a suffixed handoff file (<WS-KEY>-<date>-<anything>.md). It is dropped by the compiler as older_handoff and never reaches a reader; amend the dated file in place. DSC:SUFFIXED-HANDOFF-IS-INVISIBLE."
  - "ADDENDUM-FOLLOWUP — Do NOT chase tests/test_communique_diff.py's 10 failures in a session worktree, and do NOT 'fix' them: they are the sparse-checkout artifact (the module reads data/china_official/), identical on a clean extract of main, and green in main's own CI."
  - "ADDENDUM #5609 — Do NOT wire control_for_sector() into every producer (sitrep §11 recommendation-1 shape). Refuted by measurement: self-cancelling for radar/policy/thematic_desk (subjects ARE theme proxies); under-covering for intel_hub (72%) and altdata* (89%). Census §6."
  - "ADDENDUM #5609 — Do NOT derive a family's control policy from row contents ('rows carry controls, so evaluate on controls') — that is the data-conditioned evaluation the ruling forbids; policy comes from FAMILY_CONTROL_POLICY only (contract C1.4, pinned by test)."
  - "ADDENDUM #5609 — Do NOT 'fix' a required family's missing-control refusal by restoring any bench fallback; and do NOT pre-create control_evidence_clock_start files — a hand-written timestamp is the retrospective stamping the design forbids (C3.1/C9)."
  - "ADDENDUM #5609 — Do NOT compute control coverage over the controlled subset or over date clusters alone — min(date, row) over the ISSUED cohort, both disclosed (C4, amended post-review; one controlled row per date bought coverage 1.0 before the amendment)."
  - "ADDENDUM #5609 — Do NOT compare the cohort boundary at instant granularity — the clock is stamped with the triggering claim's own timestamp and membership compares UTC DATES; instant comparison excluded the clock's own batch and made the denominator order-dependent."
  - "The horizon defect is NOT a one-line in_scope_horizons fix. That was the 08-12 diagnosis and it was wrong about the cause. Superseded report: PR #5512, closed."
  - "Do not register retrospective claims for the three desks. claude/eval-os-t9-adoption tried it; 3/3 adversarial reviewers refused it."
  - "Do not add a `backfilled` flag as a compromise — nothing reads it."
  - "Do not extend GRADE_HORIZONS above 63 (LH-U6)."
  - "Do not resolve a claim's market from shape alone or provenance alone."
  - "Do not 'fix' the 17 graded cells that now read None after #5573 by restoring the bench fallback. None is the honest state when no control leg exists."
danger_areas:
  - "ADDENDUM-FOLLOWUP — A sparse session worktree makes whole suites fail VACUOUSLY: test_communique_diff.py (10/15) and test_build_demand.py fail here purely because data/ is absent, and a guard that reads data/ or site/ can equally pass vacuously. Reproduce a suspected 'main break' against a clean extract (git archive origin/main <trees> | tar -x -C <tmp>) before attributing it, and check whether the subject module reads an omitted tree."
  - "ADDENDUM-FOLLOWUP — Never `git stash` in a shared session worktree. The stash stack is repo-global and other sessions' entries sit in it; a builder here ran `git stash push -u` to isolate a test and swept a concurrent session's uncommitted contract/handoff edits along with its own. Nothing was lost, but the correct move is a diff against origin/main, never a stash."
  - "engine/qledger.py is edited by many lanes at once. Four PRs in this wave touched it in different functions; every one needed a rebase onto post-merge main. ALWAYS `git diff --stat origin/main HEAD` before opening a PR — a builder that branched pre-merge will silently show a sibling's files as DELETED, and merging that reverts their work. This nearly shipped: P0b's first diff showed P1's test file at -431 lines."
  - "Never reuse a worktree that has a live agent in it. Checking out another ref under a running builder detaches its HEAD; caught and restored here with nothing lost, but only because the builder had not committed yet."
  - "New test files must be named by a `run:` step in .github/ci/legacy-jobs.yml or the workflow-yaml fence reds the PR. P3's two suites shipped dark and were caught by that fence, not by review."
  - "data/qledger/*.jsonl are append-only nightly stores. Any test assertion over their contents is illegal if appending a row can falsify it."
  - "ADDENDUM #5609 — engine/qledger.py remains a many-lane file: the P0d session's round-1 rebase DROPPED #5584's freshly-merged hunks silently (the builder resolved a conflict wholesale and reported the file 'untouched by main'); caught only by grepping for the sibling's constant before push. ALWAYS grep for a just-merged sibling's identifiers in the file after any rebase that replays large qledger.py commits — git diff --stat vs origin/main shows nothing when the drop is inside a modified file."
  - "ADDENDUM #5609 — tests seeded through make_claim WITHOUT horizon_unit are legacy-clock seeds; after P0c-2 they can never produce eligible=True at GRADED, so any alert/promotion test built on them is unreachable-by-construction. Seed the explicit clock (horizon_unit + the clock_version/horizon_unit/clock_market triple on grade rows)."
  - "ADDENDUM #5609 — Dark test suites: a file not named in a legacy-jobs.yml run step runs NOWHERE in CI — it can fail on main for days with zero signal (w6 monitor did exactly that since 05:44Z). Grep the manifest before trusting 'green locally' as fleet state."

prs: [5471, 5512, 5519, 5534, 5559, 5563, 5572, 5573, 5577, 5582, 5584, 5609, 5617, 5665]
discoveries:
  - DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG
  - DSC:CONTROL-VOCABULARY-MISMATCH-KILLED-EVERY-WIRED-CONTROL
  - DSC:SUFFIXED-HANDOFF-IS-INVISIBLE
---

## Cold-start orientation for the next Eval-OS session

Read, in order: `research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md` (the law that now governs
every control-leg question), `research/EVAL_OS_P0D_CONTROL_CENSUS.md` (why each family is
classified as it is), `research/EVAL_OS_SITREP_2026-08-14.md` (what the wave found and what
it withdrew), `research/EVAL_OS_P0A_HORIZON_CLOCK.md` (the clock contract and its disclosed
residuals), then this handoff's `do_not_redo`.

The single most important thing to know: **matched-control evidence still does not exist,
and that is the honest state.** The classification says only `stock_desk` and
`demand_chain` OWE controls; the clock artifacts under
`data/qledger/control_evidence_clock_start/` are written by the registrar the first time a
prospective, control-carrying claim registers — stock_desk's can start with the first
nightly after #5609 merges (#5577's sector wiring is live), demand_chain's only after its
`sector_of` wiring lands. No session may create those files by hand. A required family can
never promote on its benchmark numbers; a benchmark family can never be described as
matched-control evaluated; and the words for the two must never share an unlabelled
sentence.

The earlier half of this record (PRs #5471-#5584) is the measurement-law wave that made
that contract possible: the evidence clock for P3's forward-only registration has also not
started, and the number that matters there is the first
`data/qledger/evidence_clock_start/<family>.json` written by a real nightly — again, never
by hand, because doing so is precisely the retrospective stamping the whole design exists
to prevent.

## FILENAME REPAIR — why two sessions share one record

The P0d session wrote its handoff as
`agentos/handoffs/WS-EVAL-OS-MEASUREMENT-LAW-2026-08-14-P0D.md`. That filename is invisible
to the compiler: `scripts/agentos.py` ranks handoffs with
`HANDOFF_DATE_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})$")`, anchored at the END of the stem,
and `handoff_rank` returns `("", stem)` when it does not match — so the suffixed file sorted
BELOW this one and `compile-context` dropped it with
`older_handoff (latest: WS-EVAL-OS-MEASUREMENT-LAW-2026-08-14)`. Measured before the repair:
a cold-start bundle for this workstream served the PRE-P0d record, whose `next_actions` still
said "take the CEO's ruling on the control leg and open the follow-up PR it implies" — the
P0d contract, its `do_not_redo` list and its danger areas were on disk and unreachable. The
schema agrees: `agentos/schema/handoff.schema.yml` declares
`file: agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md`, with no suffix form.

The repair is the protocol a second same-day session should have followed in the first
place: the P0d record is folded into this file as `ADDENDUM #5609`-prefixed entries — every
field preserved, nothing overwritten — and the suffixed sibling is deleted. A third session
on the same day amends this file the same way. It never creates a suffixed sibling. The
finding is minted as `DSC:SUFFIXED-HANDOFF-IS-INVISIBLE`, because it is a property of the
Agent OS plane rather than of this workstream.

One budget note for whoever amends next: the compiled excerpt is clipped at
`EXCERPT_HANDOFF = 1600` characters over `mission + state_before + next_actions +
do_not_redo + danger_areas + unresolved`, in that order. Two sessions' worth of prose in
the first two fields evicts the fields a cold start actually needs, so addenda to `mission`
and `state_before` are deliberately one sentence each here, and live items lead
`next_actions` while `[DONE]` ones sit at the bottom.

## ADDENDUM-FOLLOWUP — the two chipped P0d items (session `claude/eval-os-p0d-control-wiring`)

Both of #5609's chipped follow-ups are closed in one change, and the contract is amended
for the second one as a governed act (C4.4 + C7 controls 9-14 + an amendment log).

**`demand_chain` now registers CONTROLLED claims.** Its adapter call passed no `sector_of`,
so a family classified `matched_control_required` was registering claims that could never
carry matched-control evidence, and its C3.1 clock could never start. The wiring is the
census's own construction — membership lookup, then the explicit alias normalisation,
returning the canonical GICS sector **NAME** because `make_claim` resolves the ETF itself.
Refusals are counted per C2.4 and a required family with any missing control now says so in
the nightly log.

**An unpriceable control no longer beats no control.** `grade_claim` rule 5 refuses the
whole grade row when a declared control cannot price the shared window, and the gate counted
its cohort from grade rows — so those claims left the coverage denominator, and declaring a
broken control reported BETTER coverage than declaring none. Rowless cohort claims are now
classified against `grade_claim`'s own steps, and only `control_leg_refused` rejoins the
denominator. The distinction that makes it attributable: subject+bench maturity is checked
FIRST, because `grade_claim` puts the control in the same maturity leg list, where an
unpriceable control is indistinguishable from a young claim.

What a next session should NOT conclude from this: matched-control evidence still does not
exist. Both required families are wired now; neither has registered a controlled claim yet.
The clock files remain the only thing allowed to say when that changes.

## ADDENDUM-SHIP (claude/eval-os-p0d-followup, 2026-08-14 ~18:00Z)

The two chipped P0d follow-ups shipped. Provenance: the control-wiring branch
(`claude/eval-os-p0d-control-wiring`, ADDENDUM-FOLLOWUP above) was adopted
VERBATIM per the parallel-commission law (build = first claim; this session =
second = reviewer). An independent Opus adversarial review (13 checks, 5
mutation controls re-applied and restored sha-identically) confirmed the gate
arithmetic and found two disclosure-tier defects, both fixed in
`fix(qledger): P0d review defects 1+2`:

- **D1 — `vocabulary_unmapped` was unreachable in production.** The composed
  resolver collapsed both refusal causes to None, so an unmapped vocabulary
  value counted as `sector_absent` and the `::warning`'s offending-value sample
  never populated (the exact D0-1/D0-2 attribution the counter exists for). Fix:
  optional `raw_sector_of` twin threaded to the CLASSIFIER only (never
  make_claim, never the claim row); controls 13/14 re-pinned through the
  production pair; the end-to-end test that had pinned the mislabel now asserts
  the true split.
- **D2 — a CLOSED window with an unpriceable subject read `not_yet_matured`.**
  Calendar test now precedes the leg probe, so `primary_leg_refused` is
  reachable for the common delisted/never-collected case and C4.4's own table is
  true. Plus: `COHORT_ROWLESS_OTHER_BASIS` gained its missing pinning test; C9's
  duplicated clause repaired (editorial).

F3 (the dark suites) was superseded en route: main now runs
`tests/test_grade_qledger.py` + `tests/test_w6_readiness_monitor.py` inside the
qledger P3 step (extended by a sibling with the same rationale; baseline entries
pruned). This ship instead wired `tests/test_prophet_overtime_horizon_reconciliation.py`
(#5540 merged it dark during the backlog drain; 23 passed; the always-on unrun
guard was red on main for it — same defect class, same fix pattern).

Verified at the ship head (all commands re-run post-rebuild onto post-#5609
main): qledger family + annotation guard **383 passed**; `test_demand_ledger.py`
9 passed; `agentos.py validate` 0 errors; `run_ci_pack --validate-only` 0;
`audit_unrun_tests` 0. Sibling-identifier grep after the replay: #5584's
constant ×5, follow-up identifiers ×11 — nothing dropped.

**Evidence clocks at ship time (git ls-tree origin/main, post-#5609):**
`data/qledger/control_evidence_clock_start/` does not exist; no P3
`evidence_clock_start/` files exist either. Honest state: zero matched-control
evidence anywhere. stock_desk's control clock can first start on the first
nightly after #5609's merge (TODAY's nightly); demand_chain's on the first
nightly after THIS PR merges. Nothing was pre-created.

Main-heal context this ship absorbed (for the next archaeologist): #5609 sat
merge-blocked most of 2026-08-14 behind a fleet-red main — the full census and
resolution receipts live in PRs #5616/#5622 (closed, superseded), #5657/#5658
(closed, superseded by the fleet's convergent heals incl. #5655), and the
merged #5617/#5618/#5623/#5629/#5645/#5648-lineage. The `validated_tag` machine
token joined `check_validated_claims.py`'s structural-mask family via that
convergence.

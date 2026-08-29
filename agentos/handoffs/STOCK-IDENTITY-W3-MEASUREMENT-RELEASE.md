---
workstream: WS:STOCK-IDENTITY
session: fable-coo/si-w3a-ruler-v1-20260829
model: fable
ended_because: complete
mission: >
  W3A slice of the Stock Identity W3 Measurement Release under
  SI-FABLE-COO-PROGRAM-20260828: build the executable expert-independent episode
  localization ruler, its nulls/controls, the Channel-A model constitution, and
  execute the one-time PR-3 constant seal on SI-SEALED-CAL-P1 — with zero
  confirmatory fit, zero routing authority, and every Sol ruling implemented
  verbatim. This file is the R1-designated stable return path for the W3
  Measurement Release; W3B and W3S sections will extend it on their own returns.
state_before: >
  Main 2b5473da carried the accepted #6529 records carrier (freeze, masterplan,
  W3 plan + R1). No ruler/estimability/dead-control/constitution module existed.
  PR-3 constants did not exist (pending sentinel law). Sol had ruled the program
  CONTINUE W3 with W3A first, W3B dependency-held, W3S sequenced post-milestone.
changed:
  - {path: engine/stock_identity/ruler.py, what: "Localization ruler: closed metric/composite contract, unconditional block with zero-fire universe rows, availability-based recall denominator (Sol five-point CONFIRMATION-1 law), per-(episode_type,grain) C-LOC-D rank stratum, strictly-forward MAE, per-episode-session flooding."}
  - {path: engine/stock_identity/ruler_nulls.py, what: "Count/dwell-matched random-fire null; D3b cadence-phase null (shared K + <=4-session same-weekday snap, typed UNESTIMABLE refusal, phase/snap/distortion stats); same-anchor equal-proximity control; machine-readable cadence-control coverage roll-up for W3B."}
  - {path: engine/stock_identity/model_constitution.py, what: "Channel-A capacity budget: declared feature subset, additive/monotone form, exact p_eff counting, p_eff <= floor(N_train_names/10) per fold; no fit code."}
  - {path: scripts/stock_identity_calibration_replay.py, what: "Bounded calibration-fire substrate act (Sol 7-point closed law): drawn-roster-only, frozen 126td cutoff enforced at output level with drop counters + ::warning, typed blockers, sampled-run refusal, provenance receipt with censored-share fields."}
  - {path: scripts/stock_identity_calibrate_w3.py, what: "One-time constant-setting act: Sol-ruled A2/B1 rule forms, fail-closed BLOCKED_DEGENERATE_CALIBRATION, roster-coverage hash gate, masked dry-run, TrialLedger grid/look-budget registration, hash-chained seal receipt incl. ruler implementation byte-hashes."}
  - {path: data/stock_identity/ruler/ruler_spec_v1.json, what: "SEALED 2026-08-29T03:37:58Z: recall_floor=0.05, lambda_fs=0.00027929738756017066, full receipt (roster 2609c8ac, manifest e6b85fd8, W2 registry 1d3902f3, provenance 2ee5d712, ruler.py 42905b81, ruler_nulls.py cd572714, spec 43bb66b0->fda9b825, sealed receipt hash a599ea14)."}
  - {path: data/trial_ledger.jsonl, what: "7 lines appended pre-execution under family stock_identity_w3_ruler_calibration: 6 diagnostic-grid rows (+/-20% for both constants; the receipt's trial_ledger_effective_n=6 counts these) plus 1 declared_budget row (fit-read look budget 3). The seal commit message's '6 rows' undercounts by the budget row — corrected here; the receipt itself is accurate."}
  - {path: research/stock_identity/W3_RULER_REGISTRATION.md, what: "Rule texts + full hash histories, review/repair record (5 adversarial rounds), sealed receipt (section 5) + status-string caveat, null-coverage disclosure, interface deviations for the W3B author."}
  - {path: research/stock_identity/W3_CHANNEL_A_MODEL_CONSTITUTION.md, what: "Frozen Channel-A model constitution registration (with JSON mirror under data/stock_identity/ruler/)."}
  - {path: .github/ci/legacy-jobs.yml, what: "Four W3A test suites appended to the existing stock-identity atlas guards step (house pattern; global-invalidator cost accepted on PR #6638)."}
  - {path: agentos/workstreams/WS-STOCK-IDENTITY.md, what: "W3A marked done-on-merge with pr 6638; artifacts extended."}
verified:
  - claim: All targeted suites green in the sealed state, both pre/post-seal branches preserved
    command: "python3 -m pytest tests/test_stock_identity_ruler.py tests/test_stock_identity_ruler_nulls.py tests/test_stock_identity_model_constitution.py tests/test_stock_identity_w3_calibration.py tests/test_stock_identity_atlas.py tests/test_stock_identity_fingerprint.py tests/test_stock_identity_partition.py tests/test_stock_identity_replay.py tests/test_stock_identity_replay_leak.py tests/test_stock_identity_state_episodes.py tests/test_gh_annotation_line_start.py -q"
    result: "PASS — 0 failures post-seal (172 new W3A tests among them after the state-aware repair added four); pre-seal invariants remain mutation-killable via pending-variant fixtures."
  - claim: The one-time seal ran exactly once on the full lawful substrate under the fail-closed gate
    command: "python3 scripts/stock_identity_calibrate_w3.py --substrate-dir <substrate_759>  # after scripts/stock_identity_calibration_replay.py --manifest data/stock_identity/ruler/calibration_replay_manifest_v1.json"
    result: "PASS — substrate 759/759 drawn names replayed (429,289 events, 8 zero-fire observations, 2,692 post-cutoff events guard-dropped with ::warning, censored share of eligible 3.04% receipted); numerator/denominator finite and >0; constants sealed with the full hash chain; a second invocation refuses. Cold-stranger note: the substrate and its provenance receipt are scratch-resident by the manifest's declared storage law, so the event/zero-fire/censored counts and substrate_provenance_hash are receipt-bound to the sealing session, not reproducible from committed bytes; the four committed hash anchors (roster, replay manifest, W2 registry set, implementation bytes) and the sealed values' internal arithmetic ARE independently reproducible and were reproduced by the milestone reviewer."
  - claim: Step-6B acceptance — both graded composites compute on the sealed spec
    command: "python3 scripts/stock_identity_build_ruler.py --pilot --include-nulls --output-dir <tmp>"
    result: "PASS — composites: computed, pr3_pending: false, 50 cells, spec_hash a599ea14 (receipt-inclusive)."
  - claim: Sealed implementation bytes match the receipt (voiding clause enforceable)
    command: "shasum -a 256 engine/stock_identity/ruler.py engine/stock_identity/ruler_nulls.py"
    result: "PASS — 42905b81... / cd572714... equal the receipt's ruler_implementation_sha256; also asserted by a live test."
  - claim: Protected paths and sealed W1/W2 artifacts untouched
    command: "git diff --stat origin/main...HEAD -- engine/entry_signal.py engine/signal_gate.py engine/confluence_tiers.py engine/signal_quality.py 'engine/prophet_*.py' engine/stock_personality.py engine/oracle/personality_context.py scripts/build_stock_library.py engine/entry_radar data/stock_identity/partition data/stock_identity/amendments data/stock_identity/expert_events data/stock_identity/constants"
    result: "PASS — empty."
unverified:
  - claim: Exact-head hosted CI green on the final PR head
    what_would_verify: "The PR #6638 ci.yml/fences run on the final head concluding green on all binding checks (legacy-jobs edit forces the full suite)."
  - claim: Sol accepts the W3A milestone
    what_would_verify: "Sol RULING/ACCEPTED on the program thread after the milestone RESULT; merge of #6638 is Sol's. RESOLVED 2026-08-29: Sol ruled REQUEST_REPAIR, not accepted — see the 'Milestone status' section below and the fail-closed repair packet (Slack C0BSBM78V1N)."
unresolved:
  - "Null #6 cadence control is PARTIAL by Sol ruling: 92/285 pilot groups controlled (5.3% of rows); dark groups are typed and barred from cadence-controlled/cross-grain inference; W3B/W5 must consume cadence_control_coverage_v1 and abstain where the control is required but unavailable — the power/ABSTAIN law owns the consequence."
  - "Point 3(a)'s date dimension of source-era reconstructibility is unenforceable from existing registry receipts (no per-date era field exists; none was invented per Sol's fail-closed law). POST-REPAIR (Sol REQUEST_REPAIR, Slack C0BSBM78V1N, 2026-08-29 census): null-bound R/B rows now fail closed to UNESTIMABLE unconditionally, regardless of the other sub-checks (spec receipt, producer store, identity, bars coverage) — the date axis for those families is unestablishable from any committed artifact in this tree, not merely absent. Recorded as a data limitation."
  - "The sealed receipt's status string 'declared_pending_sol_rule_review' predates Sol's rule-form ruling; the sealed forms ARE the ruled A2/B1 (registration section 5.1). The receipt is immutable; the caveat lives in the registration and a pinning test."
  - "The W2 replay machinery's own registry work-file stages into a hardcoded foreign session scratchpad path (module constant outside this carrier's owned files); provenance hashes bind the substrate regardless. Cosmetic follow-up for a W2-owned pass."
  - "_identity_resolvable carries a today-unreachable fail-open default (hygiene.check_symbol always sets the key); flagged for a fail-closed default in a future W3B-adjacent pass."
next_actions:
  - "RESOLVED 2026-08-29: Sol ruled REQUEST_REPAIR (Slack C0BSBM78V1N) rather than accept/merge — the fail-closed repair (null-bound R/B rows type UNESTIMABLE unconditionally) plus the date-evidence census are recorded in registration §6.13/§6.14 and this file's 'Milestone status' section."
  - "Sol: rule on the re-seal boundary now that the repair is in place — whether/when a corrective seal should follow, and its shape. Not decided by this repair."
  - "On acceptance: SI-W3B-ESTIMABILITY-V1 unlocks against the frozen support/coverage + cadence-control-coverage schemas (consume absence as outcome-independent estimability input)."
  - "SI-W3S-DEAD-CONTROL-V1 starts post-milestone per Sol's Terra-avenue ruling: extend config/delisted_symbols.yml to >=5 rows under its own SEC evidence protocol with a mechanical preregistered selection rule, and extend the existing Polygon dead-name collector to persist o/h/l/v (owner inventory packet in the program thread, 2026-08-28)."
  - "W3 Measurement Release closes only when Sol accepts W3A + W3B + W3S status together (freeze gate)."
do_not_redo:
  - "Do not re-run or re-derive the PR-3 constants: the seal is one-time; any change to ruler.py/ruler_nulls.py/the rule implementations voids it (receipt hashes are the guard)."
  - "Do not tune null #6 to recover coverage (Sol CONFIRMATION-2: no wider snap, no per-fire K)."
  - "Do not read pilot-derived constant previews as receipts (design-tier; voided in registration 4.4/6.9)."
  - "Do not fall back to fired-on recall denominators anywhere (Sol CONFIRMATION-1; regression-guarded)."
danger_areas:
  - "The sealed spec + ledger rows are law: a naive 'cleanup' or regeneration of data/stock_identity/ruler/ruler_spec_v1.json or the stock_identity_w3_ruler_calibration ledger family destroys the one-time evidence."
  - "legacy-jobs.yml edit = global CI invalidator: the PR's hosted run executes the full suite; never run the full suite locally in a sparse tree."
  - "State-dependent tests: pre-seal invariants live on pending-variant fixtures; do not 'fix' them by deleting either branch."
prs: [6638]
decisions: []
discoveries: []
---

# W3A milestone return — SI-W3A-RULER-V1 (2026-08-29)

Return path fixed by plan amendment R1 section 3. This body records the W3A return;
W3B and W3S append their own sections on their returns rather than minting
date-variant files.

## The sealed substrate read is a NEAR-NULL on localization signal (lead finding)

Printed first per house law (nulls printed, never hidden). Both halves of the
sealed PR-3 read are nulls or near-nulls, and the second is derivable from the
sealed receipt alone:

- recall_floor: the calibration population's P25(recall_at_tier) quantized to
  0.0 — the sealed 0.05 is ENTIRELY the preregistered substantive clamp and
  carries zero information from the 759-name substrate.
- lambda_fs: because false_start_rate is bounded in [0,1], the sealed rule
  implies median(recall_at_tier x zone_precision) = lambda_fs x P75(fsr)
  <= 2.793e-4. The median lawful sealed-calibration grading cell carries
  essentially ZERO localized recall x precision, and the resulting C-LOC-R
  penalty term is bounded at ~0.028% of the reward term's full scale —
  numerically inert.

Reading: W3A is an infrastructure/measurement capability release whose first
sealed read says the preserved expert families, measured on the frozen ruler
over the sealed calibration partition, show near-zero median episode
localization. Under the epistemics law this blocks nothing at display tier
(the gauntlet applies at promotion, not construction) and the constants are
lawfully sealed — but no reader of this milestone may mistake "the ruler is
executable and the composites compute" for "the substrate showed localization
signal." It did not, at the median. Whether tails/cells above the floor carry
signal is exactly the question the held W3B estimability census and the frozen
Q1 read exist to answer lawfully; nothing here prejudges them in either
direction.

## Milestone status: NOT ACCEPTED — Sol REQUEST_REPAIR 2026-08-29

**This milestone, as sealed above, is NOT accepted.** Sol ruled the W3A
milestone REQUEST_REPAIR (Slack C0BSBM78V1N, 2026-08-29), superseding the
"unverified: Sol accepts the W3A milestone" line below with an actual
answer: no, not as sealed.

(a) **The defect.** `_family_spec_receipted()` substituted
`bool(entry.spec_hash)` — a generic, non-empty structural receipt check —
for CONFIRMATION-1 point 3(a)'s actual requirement: DATE-SPECIFIC
source/era reconstructibility proof for a null-bound R/B family. That
substituted predicate fed the sealed calibration population.

(b) **The census result.** A completed evidence census (commissioning
session, 2026-08-29) proved NO committed artifact anywhere in this tree
records date-specific source/era coverage for ANY of the 14 null-bound R/B
families the sealed predicate had been treating as eligible: 11 NO, 3
PARTIAL (a producer store exists but no committed artifact records that
store's date coverage), 0 YES. The only committed date axis in the tree is
the instrument-scoped OHLCV price-plane manifest, which says nothing about
any family's source/era coverage. Full census: registration document §6.14.

(c) **The fail-closed repair.** `_episode_family_availability_state`'s
terminal grant now returns `"UNESTIMABLE"` unconditionally for every
null-bound R/B row — such a row can never reach `FAMILY_ELIGIBLE_STATE`,
regardless of how many other sub-checks it passes. A family with a REAL
(non-null) `family_first_available` bound is unaffected — eligibility still
exists via that unchanged path. Measured impact on the committed pilot
cohort: 4,368 of 4,372 previously-`ELIGIBLE` rows now type `UNESTIMABLE`
(registration §6.14).

(d) **Sealed artifacts preserved as the rejected-attempt record.** Per the
repair commission's fences, `data/stock_identity/ruler/ruler_spec_v1.json`,
`data/stock_identity/ruler/channel_a_constitution_v1.json`,
`data/stock_identity/ruler/calibration_replay_manifest_v1.json`,
`data/trial_ledger.jsonl`, `engine/stock_identity/ruler_nulls.py`, and both
calibration scripts are BYTE-UNTOUCHED by the repair — no second seal, no
re-derivation of constants. The sealed receipt's `ruler_implementation_
sha256.ruler_py` pin (`42905b81...`) now deliberately disagrees with the
current, repaired `ruler.py` bytes; that disagreement is itself the
receipt's voiding proof, pinned by a live test.

(e) **Corrective re-seal awaits Sol's explicit boundary ruling.** This repair
makes NO second seal and does not decide when or whether one should follow;
that decision, and the shape of the re-seal act if one is warranted, is
Sol's to rule on next.

(f) **Pilot-cohort calibration degeneracy under the repaired predicate
(2026-08-29 adversarial review F2).** With `recall_at_tier_distribution`'s
defined-cell count dropped to 2/50 (both exactly `0.0`), the pilot cohort's
calibration is DEGENERATE under the repaired predicate: `compute_lambda_fs`
raises `BlockedDegenerateCalibrationError` (numerator
`median(recall × zone_precision) = 0.0`; denominator `0.6481978771972514`;
`n_lawful_population = 50`) and `compute_recall_floor` returns the bare
preregistered `0.05` clamp carrying no sample information; composites fail
closed (`c_loc_r`/`c_loc_d` `NaN`, `gate_reason` `recall_at_tier_nan` on
48/50 cells). This is measured on the PILOT cohort, NOT the guard-truncated
sealed-calibration substrate (b)-(d) above describe — indicative, not proof,
of what a corrective re-seal on the current substrate would produce — and it
signals that such a re-seal may itself terminate in
`BLOCKED_DEGENERATE_CALIBRATION` rather than a fresh seal. Full detail:
registration document §6.14.1. This is the fact Sol's re-seal-boundary
ruling in (e) needs before ruling, not a decision on its own.

## What exists now

The frozen localization ruler is executable end to end on real pilot data: closed
per-fire metrics, the two graded composites (constants sealed), the unconditional
attribution/flooding block with explicit zero-fire and no-coverage rows, three
null/control generators with published coverage states, the Channel-A model
constitution (capacity budget enforced per training fold, no fit code anywhere),
and the calibration substrate + one-time seal machinery with its receipts. All
authority axes are false everywhere; no rank/best/route column exists in any
output; Q1 remains unopened.

## Constants (sealed once, 2026-08-29T03:37:58Z)

recall_floor = 0.05 (Sol A2: max(quantize05(P25 on the lawful sealed-calibration
grading population), 0.05); the preregistered substantive minimum governs — the
population P25 quantized to 0.0). lambda_fs = 0.00027929738756017066 (Sol B1:
median(recall_at_tier x zone_precision) / P75(false_start_rate), exact quotient,
fail-closed gate passed with numerator 0 < n and denominator 0 < d both finite).
Diagnostic +/-20% variants and the fit-read look budget (3) were TrialLedger-
registered before execution. The blind arm was not opened; exemplars and pilot
contributed nothing to the constants.

## Review chain

Five adversarial Opus review rounds on this carrier: initial REPAIR-BEFORE-SEAL
(4 blockers, 11 majors — all closed), two repair-verification rounds, then
SEAL-PATH-CLEAN and SEAL-GATE-CLEAN on the exact pre-seal code, each with
mutation-tested guards. Sol rulings ts 1787935177 (rule forms, denominator law,
D3b) and ts 1787967972 (availability null convention, coverage law) implemented
verbatim and re-reviewed. Full evidence trail in the program thread and the
registration document.

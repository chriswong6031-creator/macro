---
workstream: WS:CN-LIMIT-ALPHA
session: cn-limit-precursor-discrimination-fae306 (Claude, P-B2 orchestrating session)
model: fable
ended_because: complete
mission: >
  P-B2 — the preregistered matched-control comparison arm P-B §9 reserved: which
  frozen footprints discriminate a future first tolerant board (H=10/H=5) from
  matched at-risk non-boarders. Plus: Agent OS reconciliation, China Intelligence
  data-readiness/PIT matrix, program-home amendment, post-P-B2 run order.
state_before: >
  WS record stale (status blocked; P-A1 marked awaiting_ci despite merging 08-12;
  P-B absent; no handoff existed). On main: W-P0 #5364, P-A1 #5438, P-B #5521,
  range-shards #5523 all merged; STOP-SHIP (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT)
  in force as a citation/restoration ban; P-B receipts winners-only with the
  comparison arm reserved as ore.
changed:
  - {path: agentos/workstreams/WS-CN-LIMIT-ALPHA.md, what: "reconciled to true state: active; W-P0/P-A1/P-B/P-B2 done; P-A2 accrual-gated; P-C data-gated; P-D last; do_not_redo + landmines carry the STOP-SHIP and the new placebo-confound law"}
  - {path: research/cn_prophet_audit/CN_INTEL_DATA_READINESS_MATRIX_2026-08-14.md, what: "new — PIT classes A-D per China producer; broker 金股 + report_rc + LHB rulings hand-verified"}
  - {path: research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md, what: "new — frozen BEFORE outcomes (commit 355f7a5e81c4), adversarially red-teamed pre-freeze (4 blockers + 11 majors incorporated)"}
  - {path: research/cn_prophet_audit/pb2_precursor_discrimination.py, what: "new — deterministic instrument; imports W-P0 + P-B by sha pin; 17 paired check/probe battery + amendment control"}
  - {path: research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_2026-08-14.md, what: "new — frozen receipt; verdict NO DISCRIMINATOR at the preregistered bar; 3 amendments + 4 reading notes declared"}
  - {path: research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_2026-08-14.json, what: "new — frozen numbers (3.8MB)"}
  - {path: research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md, what: "P-B2 wave row added then finalized with the shipped verdict"}
  - {path: agentos/discoveries/DSC-CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT.md, what: "new — the load-bearing discovery from the placebo calibration failure, mechanism corrected by the round-2 review (persistent-state alignment, not established name fixed effects)"}
verified:
  - {claim: "two consecutive full runs byte-identical (JSON + MD)", command: "cmp scratchpad/run1.{json,md} vs repo receipts after RUN2", result: "identical; sha256 97a11b77… / ab57aa3d…"}
  - {claim: "17/17 checks + 17/17 mutation probes + amendment control green", command: "TZ=UTC python3 research/cn_prophet_audit/pb2_precursor_discrimination.py (receipt §11)", result: "all detected; RUN1 wall time 667s"}
  - {claim: "frozen instruments byte-untouched", command: "git diff --stat HEAD -- washout_onset_w1.py pb_case_decomposition.py", result: "empty"}
  - {claim: "agentos records valid", command: "python3 scripts/agentos.py validate", result: "0 errors (pre-existing WS-STOCK-IDENTITY warnings only)"}
  - {claim: "broker 金股 latest-month-only; report_rc overwrite defect; LHB append-only", command: "sed/grep collectors/tushare_broker.py, tushare_forecast.py:120-140, china_lhb.py:40,231-246", result: "as stated in the matrix"}
unverified:
  - {claim: "the DD-family SUGGESTIVE structure is state-timing information rather than persistence-alignment artifact", what_would_verify: "the DSC's falsifier: a persistence-robust certification design (within-name transition contrasts or persistence-preserving permutation calibration) under a fresh prereg"}
unresolved:
  - "None blocking: round-2 review findings were applied as receipt amendment A4 inside this PR before merge; the DD-cell indeterminacy is recorded as the DSC's open falsifier, owned by the next wave."
next_actions:
  - "Prospective/PIT evidence-accrual hardening for orthogonal China Intelligence families (broker 金股 first-seen store; report_rc fix rides its chip — already started by the operator; per-name margin/block-trades/buybacks accrual)."
  - "Persistence-robust certification design — within-name state-transition contrasts or persistence-preserving permutation calibration — the reopen path for P-B2's placebo-clean MA200/QB/VZ structure and its indeterminate DD cells; needs its own preregistration."
  - "P-C when its data gates open (chips/auction/minute accrual + quota/authority decisions; full-A spine double-gate stays an operator decision)."
  - "Full-A exact-plane re-measurement per the reopen chain; then P-D pre-registered ablation arena (incremental over Prophet AND the carrier AND name propensity)."
  - "No self-promotion: the P-B2 verdict returns to the commissioning session; no production scoring change from P-B2."
do_not_redo:
  - "Never cite/restore withdrawn W1-W3 artifacts (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT)."
  - "Never read P-B winners-only numbers as selection skill; P-B2 is the comparison arm."
  - "Never quote a cross-sectional lift/z on a PERSISTENT-state feature on this panel as state-timing information — the shift-placebo cannot certify it and P-B2's DD cells are placebo-reproducible (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT). Non-persistent footprints' machinery measured calibrated (0.69% placebo rejections)."
  - "Never stamp historical broker 金股 months as PIT-known; prospective first-seen only."
  - "Never re-shop P-B2 gates/floors/strata post-hoc — deviations are numbered amendments in the receipt or they do not exist (A1-A3, R1-R4 exist)."
danger_areas:
  - "P-B2's permutation is DIAGNOSTIC ONLY (~10x episode design effect); gates read CGM two-way z. The placebo battery FAILED on main but the round-2 dissection shows the failure is DD-family persistence alignment (25/26 rejections, one-signed), not a symmetric SE failure — treat DD-family z as uncertifiable and non-DD z as measured-calibrated, and note the SUGGESTIVE bar inside a failed family is at least as uncalibrated."
  - "All P-B2 verdicts are within-session cross-sectional; nulls are silent on market-timing/regime forms of the same families (instrument verdicts ≠ market verdicts)."
  - "chinext10 is DESCRIPTIVE_ONLY by construction (zero HOLDOUT rows forever); star failed the FIT floor as the prereg predicted."
  - "Session worktrees are sparse: materialize data/ (worktree_sparse.py add data) before any panel run."
prs: [5615]
discoveries: [DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT]
---

Incident log: the opus builder hit an API session limit after RUN1 concluded
(17/17 green) while RUN2 ran; RUN2's process completed independently and the
orchestrating session completed the determinism proof (cmp), the gate audit, and
all interpretation in the main loop. The placebo battery that decided the headline
was itself the pre-freeze review round's repair of a vacuous calibration check —
it did its job against the study's own headline, which is what it is for.

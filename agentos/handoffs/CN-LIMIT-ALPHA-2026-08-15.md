---
workstream: WS:CN-LIMIT-ALPHA
session: cursor/cn-pb3-prereg-ee9b
model: local
ended_because: complete
mission: >
  Apply P-B3 prereg pre-outcome amendments A1–A8 from the independent
  adversarial review. Do not run the certification. Do not merge. Do
  not arm merge-on-green. Stop once A1–A8 are in the prereg text and
  pushed to PR #5729.
state_before: >
  P-B3 prereg frozen (PR #5729, freeze commit 6419ca5ed5744d562b7c22093b52065502f802f3).
  Independent adversarial review returned FREEZE AMEND
  (research/cn_prophet_audit/PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md).
  A-primary / B-corroborative was not reopened. No P-B3 instrument or
  outcome existed.
changed:
  - {path: research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md, what: "A1–A8 written in as numbered pre-outcome amendments (§16); A-primary / B-corroborative unchanged; no runner or outcome"}
  - {path: research/cn_prophet_audit/PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md, what: "amendments-applied tick list added so a cheap re-review can check each A#"}
  - {path: agentos/workstreams/WS-CN-LIMIT-ALPHA.md, what: "P-B3 next_action: A1–A8 landed; cheap re-review next; P-D occupancy-as-timing leak closed"}
  - {path: research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md, what: "P-B3 row notes A1–A8 applied; P-D row splits TIMING vs occupancy covariate vs CARRIER_SERIES"}
  - {path: agentos/handoffs/CN-LIMIT-ALPHA-2026-08-15.md, what: "this file — amend-session handoff replacing the freeze-only next_actions"}
verified:
  - {claim: "no study runner or result JSON added", command: "git diff --name-only origin/main...HEAD", result: "prereg + review + agentos/program-home pointers only; no pb3_*.py"}
  - {claim: "A-primary / B-corroborative DEC left untouched", command: "git diff --stat HEAD -- agentos/decisions/DEC-CN-PB3-A-PRIMARY-B-CORROBORATIVE.md", result: "empty"}
  - {claim: "P-B2 instruments still byte-untouched", command: "git diff --stat HEAD -- research/cn_prophet_audit/washout_onset_w1.py research/cn_prophet_audit/pb_case_decomposition.py research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md research/cn_prophet_audit/pb2_precursor_discrimination.py", result: "empty on those paths"}
  - {claim: "agentos records valid", command: "python3 scripts/agentos.py validate", result: "0 errors"}
unverified:
  - {claim: "cheap re-review will accept A1–A8 as written", what_would_verify: "an independent pass ticking the review-file A1–A8 table against the amended prereg clauses"}
  - {claim: "the 20 in-scope cells will meet A's transition floors on DD", what_would_verify: "the later P-B3 run's honest-N table; INSUFFICIENT SUPPORT is a pre-registered outcome, not a defect"}
  - {claim: "exact live evidence-start timestamps for the four new hist files", what_would_verify: "after the first asia-close collect that writes each hist parquet, record min(first_seen) per store — the files do not exist until that run"}
unresolved:
  - "P-B3 certification is still not run. Cheap re-review of the amended prereg is the next act. P-D is not opened."
  - "P-C remains gated on chips-distribution + auction/minutes accrual lanes and the full-A spine authority decision."
next_actions:
  - "Cheap independent re-review of the amended prereg, ticking A1–A8 in PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md against the prereg clauses. Do not run the study in the re-review session."
  - "After re-review accepts, a later session implements the instrument and runs P-B3 against the amended frozen prereg. Do not auto-roll from re-review into the run."
  - "Do not open P-D from the certification session. TIMING-stamped cells are timing-family inputs; occupancy-stamped cells are named covariates only; CARRIER_SERIES is not incremental to the washout carrier. NULL is recorded and not re-shopped."
  - "P-B2-ACCRUAL shipped on main (#5730). Record live min(first_seen) after the first asia-close write. Do not score broker/margin/block/buyback/report_rc. Do not add them to Prophet. Do not seed hist from snapshots."
  - "P-C only when its data gates open. Do not charter it from this wave."
do_not_redo:
  - "Do not rerun P-B2 or move its gates. P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR."
  - "Do not reuse S in {250, 500, 1000} feature shifting as a P-B3 certification null (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT)."
  - "Do not restore or cite withdrawn W1-W3 artifacts (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT)."
  - "Do not read P-B winners-only numbers as selection skill."
  - "Do not shop the §2 cell list, §5.2 edge map, or §10 headline table after outcomes."
  - "Do not add a study runner or a result file to the freeze/amend PR."
  - "Do not reopen A-primary / B-corroborative (DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE)."
  - "Never redo the report_rc overwrite fix (#5614)."
  - "Never stamp historical broker 金股 months as PIT-known; known_at is UNKNOWN unless vendor month equals the collection calendar month."
  - "Never turn a vendor event_date or plan_start into known_at."
  - "Never reconstruct evidence from current snapshots or seed the new hist stores from pre-existing snapshots and call that PIT."
danger_areas:
  - "Calling an occupancy stamp 'timing' is the misread this prereg exists to prevent. Only §10 TIMING may use that word."
  - "A later session that flips MA200 to onset-under, or DD to exit, because the primary edge is null, has shopped the edge. That result does not exist."
  - "Session worktrees are sparse: materialize data/ before any later panel run. This amend session must not write into data/ or site/."
  - "P-B2's permutation remains diagnostic-only and anticonservative; do not import it as a P-B3 gate."
  - "G6B is cross-name path assignment, not F minus p_i. Residual-fill that only preserves TRUE lengths is forbidden."
  - "asia-close must actually run the four collectors for hist files to appear. A token-dark tushare night leaves broker_hist and margin_hist uncreated; that is an empty start, not a backfill invitation."
  - "china_margin_detail (akshare drip) is a different source from tushare margin_hist. Do not join them as one tape."
prs: [5729, 5730]
decisions: [DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE, DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE]
discoveries: [DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT]
---

Amend session only. A1–A8 are in
`research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md` §16.
No certification numbers exist. Cheap re-review is the next act.

## Folded from #5730 (cn-intel PIT hist, already on main)

Shipped on main as `576ce39009` (PR #5730, session
`cursor/cn-intel-pit-accrual-a9f2`). Accrual hardening for the four remaining
class-C carrier-independent China Intelligence snapshots is implemented.
Display files are unchanged. `report_rc` was already lawful on main (#5614)
and was not touched.

Evidence-start floor for the four new stores is 2026-08-15. The exact
timestamp per store is `min(first_seen)` after the first live collect that
creates the file. No hist parquet is committed in that change.

Do not redo: never stamp historical broker 金股 months as PIT-known; never
turn a vendor event_date or plan_start into known_at; never reconstruct
evidence from current snapshots; never seed the new hist stores from the
pre-existing snapshots and call that PIT. A dark tushare token leaves
`broker_hist` and `margin_hist` uncreated — that is an empty start, not a
backfill invitation. `china_margin_detail` (akshare drip) is a different
source from tushare `margin_hist`. Decision:
`DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE`.

---
workstream: WS:CN-LIMIT-ALPHA
session: cursor/cn-pb3-prereg-ee9b
model: local
ended_because: complete
mission: >
  Freeze the P-B3 persistence-robust certification preregistration only.
  Do not run the study. Do not read new outcomes. Do not compute a new
  result table. Stop once the prereg PR exists, before independent
  adversarial review and before any later certification session.
state_before: >
  P-B2 shipped (PR #5615): NO DISCRIMINATOR at the preregistered bar;
  DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT recorded; WS next_action
  named a persistence-robust certification under a fresh prereg as the
  reopen path for placebo-clean MA200/QB/VZ and indeterminate DD cells.
  No P-B3 prereg existed.
changed:
  - {path: research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md, what: "new — P-B3 prereg frozen before any instrument or outcome; A primary, B corroborative; 20-cell scope; joint disposition and P-D implication frozen"}
  - {path: agentos/decisions/DEC-CN-PB3-A-PRIMARY-B-CORROBORATIVE.md, what: "new — records the A-primary / B-corroborative assignment and the rejected alternatives"}
  - {path: agentos/workstreams/WS-CN-LIMIT-ALPHA.md, what: "P-B3 wave added as in_progress (prereg freeze); next_action points at independent review then a later run"}
  - {path: research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md, what: "P-B3 row added as prereg-frozen, run not started"}
verified:
  - {claim: "P-B2 instruments still byte-untouched", command: "git diff --stat HEAD -- research/cn_prophet_audit/washout_onset_w1.py research/cn_prophet_audit/pb_case_decomposition.py research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md research/cn_prophet_audit/pb2_precursor_discrimination.py", result: "empty on those paths"}
  - {claim: "W-P0 / P-B / P-B2-prereg sha prefixes match the pins written into the P-B3 prereg §3", command: "python3 -c \"from pathlib import Path; import hashlib; [print(p, hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]) for p in ['research/cn_prophet_audit/washout_onset_w1.py','research/cn_prophet_audit/pb_case_decomposition.py','research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md']]\"", result: "11ac61de71f0f595 / f42b0566beb60bec / 043a85d69f76ea86"}
  - {claim: "this PR adds no study runner and no result JSON", command: "git diff --name-only origin/main...HEAD", result: "prereg + agentos/program-home pointers only"}
  - {claim: "agentos records valid", command: "python3 scripts/agentos.py validate", result: "0 errors on the new records"}
unverified:
  - {claim: "the 20 in-scope cells will meet A's transition floors on DD", what_would_verify: "the later P-B3 run's honest-N table; INSUFFICIENT SUPPORT is a pre-registered outcome, not a defect"}
  - {claim: "independent adversarial review will pass this prereg without a design change", what_would_verify: "the review session's written blockers, if any, incorporated as numbered pre-outcome amendments"}
unresolved:
  - "P-B3 is freeze-only. Certification is a later session after independent adversarial review. P-D is not opened."
next_actions:
  - "Independent adversarial review of PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md (this PR). Do not run the study in the review session."
  - "After review passes, a later session implements the instrument and runs P-B3 against the frozen prereg. Do not auto-roll from review into the run."
  - "Do not open P-D from the certification session. CERTIFIED STRUCTURE is an eligible P-D input only; NULL is recorded and not re-shopped."
  - "Orthogonal PIT accrual (broker 金股 first-seen; report_rc; per-name margin/block-trades/buybacks) remains a parallel next_action of the workstream, not of this freeze."
do_not_redo:
  - "Do not rerun P-B2 or move its gates. P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR."
  - "Do not reuse S in {250, 500, 1000} feature shifting as a P-B3 certification null (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT)."
  - "Do not restore or cite withdrawn W1-W3 artifacts (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT)."
  - "Do not read P-B winners-only numbers as selection skill."
  - "Do not shop the §2 cell list, §5.2 edge map, or §10 headline table after outcomes."
  - "Do not add a study runner or a result file to the freeze PR."
danger_areas:
  - "Calling an occupancy stamp 'timing' is the misread this prereg exists to prevent. Only §10 TIMING may use that word."
  - "A later session that flips MA200 to onset-under, or DD to exit, because the primary edge is null, has shopped the edge. That result does not exist."
  - "Session worktrees are sparse: materialize data/ before any later panel run. This freeze session must not write into data/ or site/."
  - "P-B2's permutation remains diagnostic-only and anticonservative; do not import it as a P-B3 gate."
prs: []
decisions: [DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE]
discoveries: [DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT]
---

Freeze session only. The commit hash of
`research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md`
is the freeze proof once review passes. No certification numbers exist yet.

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

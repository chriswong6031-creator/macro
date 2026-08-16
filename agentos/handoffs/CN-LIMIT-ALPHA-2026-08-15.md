---
workstream: WS:CN-LIMIT-ALPHA
session: cursor/cn-pb3-prereg-ee9b
model: local
ended_because: complete
mission: >
  Implement and run exactly the frozen P-B3 persistence-robust certification.
  Do not shop gates. Do not rewrite P-B2. Do not open P-D. Stop after
  certification.
state_before: >
  P-B3 prereg frozen and A1–A8 amended (PR #5729). Independent re-review
  accepted (FREEZE STANDS). No official P-B3 receipts existed. First full
  panel run completed 20 cells then died before write (empty P-B2
  FKEYS_ORDER; one §11 probe undetected).
changed:
  - {path: research/cn_prophet_audit/pb3_persistence_robust_cert.py, what: "P-B3 runner (A primary, B corroborative, §11/§12 battery); A9–A11 instrument heals"}
  - {path: tests/test_pb3_persistence_robust_cert.py, what: "35 tests that can fail: headlines, spells, probes, pins"}
  - {path: research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.md, what: "official receipt — NULL=12, UNINFORMATIVE=8"}
  - {path: research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.json, what: "machine receipt; verify 19/19"}
  - {path: agentos/discoveries/DSC-CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE.md, what: "no certified timing or occupancy on the frozen 20"}
  - {path: agentos/workstreams/WS-CN-LIMIT-ALPHA.md, what: "P-B3 wave done; P-D stays todo with no P-B3 input"}
  - {path: research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md, what: "P-B3 row: shipped verdict"}
  - {path: agentos/handoffs/CN-LIMIT-ALPHA-2026-08-15.md, what: "this file — certification-session handoff"}
verified:
  - {claim: "headline tally is NULL=12, UNINFORMATIVE=8", command: "python3 -c \"import json; print(json.load(open('research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.json'))['headline_tally'])\"", result: "{'NULL': 12, 'UNINFORMATIVE': 8}"}
  - {claim: "verify battery 19/19 checks and 19/19 probes", command: "python3 -c \"import json; print(json.load(open('research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.json'))['verify']['summary'])\"", result: "all_passed True, all_probes_detected True, 19/19"}
  - {claim: "P-B2 preservation sentence is verbatim in the MD", command: "rg -n \"P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR\" research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.md", result: "line 5, exact sentence"}
  - {claim: "no CERTIFIED TIMING or CERTIFIED OCCUPANCY headline", command: "rg -n \"CERTIFIED TIMING|CERTIFIED OCCUPANCY\" research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.md", result: "only in the implication prose; §5 table has neither as a cell headline"}
  - {claim: "P-D not opened and has no inputs", command: "python3 -c \"import json; d=json.load(open('research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.json'))['pd_implication']; print(d['timing_family_inputs'], d['occupancy_covariates_only'], d['do_not_open_pd_this_session'])\"", result: "[] [] True"}
  - {claim: "prereg pin prefix still 75fb38e1e6b5aefe", command: "python3 -c \"import hashlib; from pathlib import Path; print(hashlib.sha256(Path('research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md').read_bytes()).hexdigest()[:16])\"", result: "75fb38e1e6b5aefe"}
  - {claim: "unit tests pass", command: "python3 -m pytest tests/test_pb3_persistence_robust_cert.py -q", result: "35 passed"}
  - {claim: "agentos records valid", command: "python3 scripts/agentos.py validate", result: "0 errors"}
unverified:
  - {claim: "a second independent TZ=UTC re-run is byte-identical", what_would_verify: "re-run the official command and diff the JSON headline_tally, verify.summary, and per-cell A/B statuses"}
unresolved:
  - "P-D remains todo and has no P-B3 input. Do not open it from this construction."
  - "MA200/QB A=CERTIFIED_TIMING + B=NULL is UNINFORMATIVE / A_B_CONTRADICT, not a rescue path."
next_actions:
  - "Do not open P-D. Do not re-shop a placebo. Do not rewrite P-B3 gates."
  - "Land PR #5729 (receipts + knowledge plane) through the house ship chain. P-B3 is research-display; no production score and no Prophet / china_board_rank change."
  - "Orthogonal PIT accrual (broker 金股 first-seen; report_rc; per-name margin/block-trades/buybacks) remains a parallel next_action of the workstream, not of P-D."
do_not_redo:
  - "Do not rerun P-B2 or move its gates. P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR."
  - "Do not rerun P-B3 or shop its gates, floors, strata, cells, or headlines (DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE)."
  - "Do not reuse S in {250, 500, 1000} feature shifting as a certification null (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT)."
  - "Do not restore or cite withdrawn W1-W3 artifacts (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT)."
  - "Do not read P-B winners-only numbers as selection skill."
  - "Do not flip MA200 to onset or DD to exit because the primary edge contradicted B."
  - "Do not quote occupancy as timing. Only a §10 CERTIFIED TIMING row may use that word; this run has none."
danger_areas:
  - "Calling an occupancy stamp 'timing' is the misread this prereg exists to prevent. This run has no occupancy stamp either."
  - "A later session that treats A_B_CONTRADICT as 'almost certified' has shopped the headline table."
  - "Session worktrees are sparse: materialize data/ before any later panel run. Do not write into an omitted data/ or site/ tree."
  - "P-B2's permutation remains diagnostic-only and anticonservative; do not import it as a P-B3 gate."
prs: [5729]
decisions: [DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE]
discoveries: [DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT, DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE]
---

P-B3 certification is done. Freeze hash `6419ca5ed5744d562b7c22093b52065502f802f3`.
Prereg sha256 prefix `75fb38e1e6b5aefe`. Run head `b473cad20da08a274a3c7914b2edec1827433783`.
Verdict: **NULL=12, UNINFORMATIVE=8**. P-D is not opened.

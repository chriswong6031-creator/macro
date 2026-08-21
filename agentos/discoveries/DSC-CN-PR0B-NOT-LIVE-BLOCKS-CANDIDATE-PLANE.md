---
key: CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE
claim: >
  China Alpha Intelligence PR-0B (single-compute v4 Intelligence telemetry into
  the canonical candidate plane) is commissioned but not executed: the
  architecture chain (#5953, #5933, #5943, #5955) all MERGED 2026-08-19
  16:05-18:13Z — superseding the R6 packet's "open/nonmergeable" snapshot —
  but engine/china_prophet_shadow.py contains zero intel_ fields and no real
  candidate rows carry the intel_ anatomy, so the PR-0B seam is not live and
  every CN-Limit candidate-plane runtime edit remains blocked.
falsifier: >
  grep "intel_" engine/china_prophet_shadow.py returning the telemetry family,
  plus the newest data/china_prophet_rank/candidates.parquet rows carrying the
  complete intel_ anatomy with explicit unavailable reasons under one served
  definition (PR-0B's acceptance), or WS:CHINA-ALPHA-INTELLIGENCE marking
  PR-0B PROVEN_LIVE — any of these retires this blocker.
so_what: >
  CN-Limit waves I1A-T1..T4 (candidate anatomy) may not start, and no session
  may edit the candidate writer for CN-Limit purposes, until PR-0B is
  PROVEN_LIVE on real asia-close rows — merged is not live. DEP-CAI's
  remaining work is executing the already-commissioned PR-0B
  (research/china_alpha_intelligence/commissions/PR-0B_v4_telemetry.md) inside
  the China Alpha program, not rebasing the architecture chain, which is done.
kind: constraint
verified_at: 2026-08-19
verified_by: "gh api graphql (PRs 5953/5933/5943/5955 all MERGED 2026-08-19); grep -c 'intel_' engine/china_prophet_shadow.py → 0 at origin/main ccdb62402eb6"
scope:
  - macro
  - engine/china_prophet_shadow.py
  - data/china_prophet_rank/
  - research/cn_limit/
confidence: verified
---

The R6 wave DEP-CAI was written as BLOCKED_OPEN_PRS; as of 2026-08-19 18:13Z
the open-PR half is resolved and the wave's live gate is PR-0B execution +
proof. This is a state reconciliation, not a scope change: the CN-Limit-side
stop condition ("blocked until PR-0B is PROVEN_LIVE, not merely merged")
stands unchanged.

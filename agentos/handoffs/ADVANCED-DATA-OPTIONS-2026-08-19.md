---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad1c0-options-source-recovery
model: fable
ended_because: complete
mission: >
  Sol finalization handoff, two jobs: (A) reconcile the accepted AD-1 implementation
  (#5872) against fresh main and merge under conditional authority; (B) AD-1C0 — root-
  cause the options-chain accrual outage and make its failure states production-
  diagnostic in one separate source PR, held for Sol review.
state_before: >
  #5872 head 96c9f391 (sibling-rebased), mergeable but UNSTABLE; chains store frozen at
  2026-08-13 with run_status polygon_gex_accrual "empty" and no cause; AD-2 closed.
changed:
  - path: config/r2_delivery_plane_classification.v1.json (+ 2 census tsv fixtures)
    what: ON #5872 — restored the synapse.yml census rows the sibling rebase dropped (commit 3ba1ba8f; tier-gate green again).
  - path: collectors/base.py
    what: ON AD-1C0 branch — safe_exc_text/redact_secrets hardening at the retry-log site and FetchResult.error (query params, bearer/header shapes, basic-auth netloc, JSON-body reprs).
  - path: collectors/polygon_options.py
    what: per-symbol failure-reason census (frozen code set + universe_resolution_failed), (df, census) snapshot contract, deterministic mixed-class auth short-circuit probe.
  - path: scripts/build_polygon_gex.py
    what: SOURCE_HEALTH_FLOOR 0.90, health-receipt sidecar (data/polygon_gex_health/), first-writer QUALITY rule per DEC:AD1C0-FIRST-WRITER-QUALITY-RULE, universe fail-closed gates, atomic verified write-ahead chain writes.
  - path: scripts/audit_options_accrual.py
    what: receipt-aware health surfacing (sees receipt-only failed sessions; warns on unknown states).
  - path: tests/test_polygon_gex.py (6 -> 107 tests) + tests/test_audit_options_accrual.py (21 -> 30)
    what: full decision matrices; every adversarial-review attack converted into a suite test; flip-verified.
verified:
  - claim: root cause is a vendor entitlement regression, not domain/parser/context
    command: "live differential census — both domains x {stock snapshot, AAPL/SPY chain snapshot, news} with the same key; production adapter path on a 2-symbol sample; nightly collect job log"
    result: chains 403 NOT_AUTHORIZED on BOTH domains, stock/news 200 on BOTH; adapter fails at chain() before parse; nightly identical (see DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION)
  - claim: AD-1C0 focused suites green on the final head af68979d3462
    command: "pytest tests/test_polygon_gex.py tests/test_polygon_gex_session_stamps.py tests/test_options_session_guards.py tests/test_audit_options_accrual.py tests/test_gh_annotation_line_start.py -q; plus 10 adjacent-adapter suites; run_ci_pack --validate-only"
    result: 243 passed / 21 sparse-skips; 237 passed adjacent; manifest validates (194 jobs)
  - claim: four adversarial review rounds concluded with every blocker/major closed and flip-verified
    command: "opus reviewer rounds 1-4 (flip harness on git-archive scratch copies)"
    result: round-1 FAIL 3 blockers/6 majors/8 minors -> repaired; round-2 residuals -> repaired; round-3 W1 -> repaired; round-4 W1 CLOSED, final 2 minors (C1/C2) repaired with self-flip proof
unverified:
  - claim: live >=0.90 coverage capture (AD-1C0 charter item 12)
    what_would_verify: vendor entitlement restoration (owner action) + the next scheduled nightly's census reporting coverage >= 0.90
  - claim: "#5872 merged"
    what_would_verify: fresh symbol-directory snapshot (first nightly under #5936's collector fix) clears the VMRK drift red on main; then a fresh #5872 push over healed main concludes green and merges
unresolved:
  - "#5872 waits ONLY on main: pack-2/#5941 healed, pack-4/#5939 healed (merged 08:53Z by this session), pack-7/VMRK clears at the first nightly collection under the fixed symbol-directory collector (~2026-08-20T05:00Z). Sequencing receipt on the PR."
  - "Workstream wave rows for AD-1 (awaiting merge) and AD-1C0 (in Sol review) intentionally NOT updated in this PR — the wave state rides #5872's branch and updating it here would manufacture a cross-PR conflict; add both rows in a docs commit after the two PRs merge."
  - "Vendor entitlement restoration + key hygiene are operator actions, communicated out-of-band with receipts."
next_actions:
  - Sol adversarial review of the AD-1C0 source PR (NOT merged, NOT armed by this session).
  - After tonight's snapshot lands and a main baseline proves green - fresh push on #5872, merge on concluded green, AD-1 = BUILT_NOT_PROVEN.
  - After entitlement restoration - two consecutive lawful scheduled captures (S and D) >= 0.90 coverage, no diagnostic bypass, then AD-1 production acceptance.
do_not_redo:
  - The domain-migration hypothesis (falsified: both domains answer identically for this key).
  - A lib/ticker_aliases entry for VMRK (new listing, not a rename — a wrong entry stores another company's tape; see the #5872 debug packets).
  - Re-probing the vendor with the full 375-name collector while the entitlement is down (the census probe set + short-circuit exist for this).
danger_areas:
  - The chains store's missing sessions 2026-08-14/17/18 are PERMANENT (PIT OI); any backfill attempt violates the historical-gap law.
  - data/polygon_gex_health/ is nightly-written runtime state — never commit receipts from a PR; never nest it inside data/polygon_gex/ (pinned stray-files invariant).
  - status literals in accrue() are consumed by collect.py/run_status; new information rides NEW fields (health/census), never re-meaninged literals.
---

## Summary

Phase A: #5872's rebase-dropped census re-stamp healed (3ba1ba8f); remaining reds proven
main-inherited with named heals — two landed (one merged by this session), the third is
data-staleness that only tonight's nightly can clear. Phase B: AD-1C0 shipped end-to-end
on claude/ad1c0-options-source-recovery through four adversarial review rounds (17 initial
findings + 9 residuals + W1 + C1/C2, every one repaired and flip-verified; 3,307 insertions,
zero data/ diffs, same 6-file scope throughout). Root cause of the outage is recorded as
DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION; the replacement write law as
DEC:AD1C0-FIRST-WRITER-QUALITY-RULE. The PR is held unmerged for Sol per the finalization
handoff §13.

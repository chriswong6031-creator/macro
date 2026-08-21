---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad1c01-capture-lease
model: fable
ended_because: blocked
mission: >
  Sol AD-1C0.1 handoff: (A) source-clock adjudication + conditional timing PR held
  for Sol; (B) credential/vendor incident closure (operator-external, recorded);
  (C) production commissioning (blocked on B). Plus the authority record ordered
  after #5974 merged against its hold.
state_before: >
  #5872 merged (661ad5d2, BUILT_NOT_PROVEN); #5974 merged against its hold
  (d5ebb5d9); chain store frozen at 2026-08-13; entitlement 403 on both domains;
  AD-1C0 census machinery live in production (2026-08-19 receipt: aborted_early,
  auth_or_entitlement_failure 5/5).
changed:
  - path: agentos/decisions/DEC-SOL-HOLD-IS-A-MERGE-BARRIER.md (+ CLAUDE.md/AGENTS.md amendment)
    what: merged separately as #6056 (a9bfe324) — holds bind every merge path; authority never transfers across PRs.
  - path: scripts/build_polygon_gex.py
    what: ON PR #6080 (HELD DRAFT) — bounded capture lease (expected_last_session prong + 03:00-ET-next-day endpoint) + same-book OI proof (ticker-preferred join, symmetric float32 grid, overlap floor) replaces the same-ET-day predicate; new skip literals skipped_outside_lease / skipped_vintage_mismatch / skipped_unverifiable_vintage. AMENDED per Sol review 4989933857 (2026-08-21) — the lease now gates EVERY non-forced write via a single PRE-FETCH gate (first writes included; explicit --date old-session refused; zero vendor calls outside the lease); overlap floor hardened to min(stored, max(20, ceil(0.25*stored))); receipts persist lease + vintage_proof audit dicts incl. oi_mismatch_count.
  - path: tests/test_polygon_gex.py
    what: Sol §4 time-boundary matrix (14 cases) + 7 boundary-review repair tests; amendment round adds the 7-case first-write matrix, the _NoFetchClient zero-call proof, floor regressions (4-contract and 1,000-contract books), and receipt-audit cases a-d; 142 total in the file.
verified:
  - claim: the same-ET-day rule refuses lawful production repairs
    command: "scripted census — daily.yml crons + et_gate; gh run view 32077948964 collect job 21:07->00:08 ET; run_status checked_at samples 18:20 ET..00:42 ET; accrual position scripts/collect.py:842 after the membership rebuild at :823"
    result: normal nightly crosses midnight ET while the resolved session stays the prior NYSE session; Option A rejected (dependency + queue-driven drift); Option B ruled (DEC:AD1C01-CAPTURE-LEASE-REPLACES-SAME-DAY)
  - claim: the lease boundary is sound and the proof repairs bite
    command: "opus boundary review (DST 2026-2028, 02:59/03:00 edge, holiday-adjacent, early-close, naive instants) + builder self-flip (4 flips)"
    result: every clock attack held; F1 major + 5 minors repaired; each flip fails a named test; pytest tests/test_polygon_gex.py -q = 123 passed
  - claim: Sol review 4989933857's four amendments are load-bearing (first-write lease, pre-fetch refusal, real overlap floor, receipt provenance)
    command: "python3 -m pytest tests/test_polygon_gex.py -q (142 passed) + per-amendment flip-verification (each amendment reverted alone fails 1-16 named tests, e.g. TestAD1C01FirstWriteLease, TestAD1C01NoFetchOutsideLease, TestAD1C01OverlapFloorIsAMinimum, TestAD1C01ReceiptAudit)"
    result: all four amendments implemented at commit 662342a0ece6; reverting any one fails named tests; suite green
  - claim: Job B external closure is NOT done (recorded, not litigated)
    command: "secret-safe probe 2026-08-20T08:09Z + gh api runs/32077948964/logs -i + actions/secrets listing"
    result: option chain 403 NOT_AUTHORIZED (stock 200, same key); exposed run logs still HTTP 200; no POLYGON_API_KEY/MASSIVE_API_KEY in Actions secrets
unverified:
  - claim: production captures S and D
    what_would_verify: operator closes Job B (rotation, log deletion, secret registration, entitlement restoration) then two consecutive healthy scheduled captures under the merged lease
unresolved:
  - "PR #6080 held as DRAFT for Sol (no arming, hold comment posted) — release condition: Sol PASS."
  - "Jobs B/C: BLOCKED_EXTERNAL. Operator actions per Sol §5; needs_ceo licensing question stands (by_when 2026-08-21)."
next_actions:
  - Sol adversarial review of PR #6080; on PASS, Sol/operator releases the hold and the normal merge chain runs.
  - Operator closes Job B; then production commissioning per Sol §6-7 (two lawful scheduled captures, no bypass) and AD-1 end-to-end acceptance to PROVEN_LIVE.
do_not_redo:
  - The source-clock census (measured window, dependency chain, calendar edges — in this handoff's verified block and DEC evidence).
  - The Option A vs B adjudication (ruled; reversal requires new evidence about the membership dependency or a dedicated capture lane).
  - Broad vendor probing while the chain endpoint is 403 (one bounded secret-safe probe per status check is enough).
danger_areas:
  - The lease governs EVERY non-forced write (Sol review 4989933857, 2026-08-21): a first write outside the lawful lease is refused BEFORE any vendor fetch and the hole stays missing; only --force overrides, visibly receipted with lease.valid=false.
  - skipped_wrong_day is retired from new writes but must remain readable in old receipts.
  - Never arm or un-draft #6080 without Sol's release — DEC:SOL-HOLD-IS-A-MERGE-BARRIER.
---

## Summary

Job A complete: the clock law is ruled and implemented on held PR #6080 with the full
Sol time-boundary matrix; the boundary survived a dedicated adversarial pass. The
authority incident is durably recorded (#6056). Jobs B and C are BLOCKED_EXTERNAL on
operator/vendor actions, with the checklist states probed and recorded.

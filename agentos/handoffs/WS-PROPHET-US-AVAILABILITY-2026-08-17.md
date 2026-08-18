---
workstream: WS:PROPHET-US-AVAILABILITY
session: worktree-prophet-outage-triage-fix-6c8949 (W3 outage response; peer session prophet-picks-update-da8222 owned the recovery dispatch)
model: fable
ended_because: complete
mission: >
  Force-majeure directive 2026-08-17: all five Prophet boards frozen (US 08-13,
  CN 08-14, HK 08-12, CA 08-11, INTL). Triage to fresh picks ASAP, then a
  durable fix so the degradation class cannot recur.
state_before: >
  Ruleset ci-recovery-bootstrap-freeze-2026-08-15 rejecting all main pushes
  since 08-15 (deleted by operator ~23:40Z); collect_tail unschedulable on the
  orphaned theta-m1 label, holding run 31977372592 alive 25h and pending
  32077948964 with zero jobs; prophet-rescue red-by-design refusing to dispatch
  past the alive hostage; nightly-liveness green (in-flight INDETERMINATE has
  no age cap; weekend flattening hides a missed Friday); single macstudio
  runner saturated by the new 13F census lane.
changed:
  - path: "runners API (no repo file; receipted on issue #5742)"
    what: "Interim infra: theta-m1 label → mac-builder-3 (23:47Z, KEPT). macstudio label → mac-builder-4 (23:54Z) — REVERTED-AND-HARMFUL, removed 00:44Z: mac-builder-4 is the merge-control runner and merge-on-green's non-cone sparse 3-path checkout shares _work/macro/macro, so dispatch 32081969617's engine died 2.5min at pip install (requirements.txt absent). Do NOT re-apply; see postmortem §Triage(2) + follow-up 7. macstudio label → mac-builder-light (00:5xZ, KEPT) after read-only workspace verification (sparseCheckout=false, requirements.txt present, full tree) — pool back to two verified hosts."
  - path: ".github/workflows/daily.yml"
    what: "collect_tail runs-on theta-m1 → macstudio, with the re-pin rule for the m1-theta canary."
  - path: "scripts/check_nightly_liveness.py"
    what: "IN_FLIGHT_MAX_AGE=14h wedge breach, STALE_GRACE=10h weekend-hole closure, new selftest vectors."
  - path: ".github/workflows/nightly-liveness.yml"
    what: "Third daily look at 20:00Z bounding wedge-detection latency to ~6h."
  - path: "scripts/prophet_rescue.py"
    what: "§0.4a wedge amendment: wedged_run classifier (6h/3h floors, fail-closed), alarm-path fetch_run_jobs, dispatch-through-wedge wiring."
  - path: "tests/test_nightly_liveness.py"
    what: "Wedge/grace/blindness vectors; strand pin re-worded for the deliberate grace overlap."
  - path: "tests/test_prophet_rescue.py"
    what: "§0.4a-amendment battery (proven wedge dispatches; every unproven input refuses; budget/floor bind through); URL census admits the jobs read."
  - path: "CLAUDE.md"
    what: "'No branch protection' annotated externally-violable; ruleset check first on push failures; freezes owe DEC + expiry."
  - path: "AGENTS.md"
    what: "Same annotation as CLAUDE.md (both law files move in lockstep)."
  - path: "config/dag.yml"
    what: "W11 witness provenance comment updated for the unpin."
  - path: "research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md"
    what: "New: full incident record, detection matrix, rejected fixes, follow-ups."
  - path: "agentos/"
    what: "DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP, DSC:RULESET-FREEZE-BLINDS-EVERY-BUILD-INSTRUMENT, DEC:PROPHET-NIGHTLY-WEDGE-HARDENING, WS W3 wave + landmines, this handoff."
verified:
  - claim: "Every lockstep suite for the changed files is green."
    command: "TZ=UTC python3 -m pytest tests/test_prophet_rescue.py tests/test_nightly_liveness.py tests/test_daily_et_gate.py tests/test_workflow_file_size.py -q"
    result: "142 passed."
  - claim: "The liveness guard's synthetic incident battery passes with the new wedge + grace vectors."
    command: "TZ=UTC python3 scripts/check_nightly_liveness.py --selftest"
    result: "nightly-liveness selftest: PASS, rc 0."
  - claim: "The daily.yml DAG and timings instrumentation pins hold through the collect_tail unpin."
    command: "TZ=UTC python3 -m pytest tests/test_dag_conformance.py tests/test_nightly_timings.py -q"
    result: "90 passed."
  - claim: "The theta-m1 restore took and the hostage began draining; the mac-builder-4 macstudio add was later reverted as harmful."
    command: "gh api repos/{owner}/{repo}/actions/runners --jq '.runners[]|[.name,(.labels|map(.name)|join(\"/\"))]'; gh run view 31977372592 --json jobs"
    result: "mac-builder-3 carries theta-m1 (kept); collect_tail in_progress on mac-builder-3 at ~23:54Z after 17.7h queued. mac-builder-4 read back self-hosted/macOS/ARM64/parked/merge-control after the 00:44Z DELETE (revert receipt: engine job 95550650855 failed 2.5min in the sparse workspace)."
  - claim: "The push freeze is gone."
    command: "gh api repos/{owner}/{repo}/rulesets"
    result: "[] — verified independently by both sessions."
unverified:
  - "Second-slot recovery dispatch conclusion + five-board live freshness (first dispatch 32081969617 FAILED in mac-builder-4's sparse workspace — the reverted label regression; peer re-dispatched after the 00:44Z de-label; owned to completion before this session stops)"
  - "Whether debris run 32077948964 fully re-bakes session 08-17 and double-appends forward-ledger rows (audit chipped)"
unresolved:
  - "Operator asks on #5742: cancel debris run 32077948964 once recovery is green; rule on 13F census cadence (30-min crons × 180m cap on the nightly's runner); M1 host revival owns the collect_tail re-pin."
  - "Per-market board freshness is still unguarded (CA froze 08-11 with zero noise; US source_asof is the only graded stamp) — chipped follow-up."
  - "close-pass.yml POOL model still names retired mac-builder-1/2 (tests/test_close_pass_lane.py) — chipped follow-up."
next_actions:
  - "Merge the hardening PR; watch its CI to conclusion (merge-on-green armed)."
  - "Verify all five Prophet boards live: site/prophet/index.json source_asof > 2026-08-13 on main AND us/china/canada/hk/intl_stocks.html serving fresh picks."
  - "Fold the hostage + freeze classes into W2's fire-drill list."
do_not_redo:
  - "Do not cancel runs 31977372592 / 32077948964 from a session — operator-only (gh_quota_guard shape 6); the ask is filed on #5742."
  - "Do not flip cancel-in-progress on daily.yml cron groups or add a wall-clock stand-down to et_gate — rejected with reasons in DEC:PROPHET-NIGHTLY-WEDGE-HARDENING (double-run-never-zero-run law)."
  - "Do not re-diagnose the outage from run conclusions (DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET) or re-hunt a GitHub platform incident — both halves were self-inflicted and receipted."
  - "Do not strip the theta-m1 label from mac-builder-3 as cleanup — it is the interim schedulability for any straggler reference until the unpin is everywhere."
danger_areas:
  - "If 32077948964 fully re-bakes session 08-17, forward ledgers may carry duplicate rows — audit before trusting 08-17 cohort counts."
  - "13F census lane (30-min crons, 180m cap, macstudio) remains a standing starvation source until its owners re-cut cadence or runner budget."
  - "NEVER give mac-builder-4 (merge-control) a build label while lanes share _work/macro/macro: merge-on-green's non-cone sparse 3-path checkout persists in the workspace and a build job landing there dies at pip install in minutes (engine 95550650855, 00:20Z). Postmortem follow-up 7 owns the isolation fix."
---

## Narrative

Full mechanism chain, timeline, detection matrix, and the deliberately-rejected
fixes: `research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md`. Discoveries:
`DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP` (scheduling half),
`DSC:RULESET-FREEZE-BLINDS-EVERY-BUILD-INSTRUMENT` (publish half, credit to the
peer session). Decision + thresholds: `DEC:PROPHET-NIGHTLY-WEDGE-HARDENING`.
Ownership split receipts live in the #5742 thread; the two sessions verified
each other's runner/ruleset reads independently.

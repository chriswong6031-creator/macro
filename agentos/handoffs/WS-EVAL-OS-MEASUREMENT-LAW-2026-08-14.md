---
workstream: WS:EVAL-OS-MEASUREMENT-LAW
session: claude/evalos-sitrep-wave2
model: opus
ended_because: ci_handoff

mission: >
  Deliver the CEO's 2026-08-13 measurement-law wave: close P0a, ship P0b (own-ruler
  grading), P0c-1 (direction-correct control hits) and P0c-2 (legacy may not originate
  authority), start P3 forward-only prospective registration for three desks, leave P1/P2
  armed untouched, disarm and replace the stale #5512 situation report.

state_before: >
  P0a parked after 5 build/verify rounds on a market-resolver blocker that later proved to
  be a malformed test of my own. #5512/#5519/#5534 armed and blocked behind a red main.
  No engine registered claims at its declared horizon; horizon_d carried no unit;
  in_scope_horizons could never reach 12 family-horizon pairs; promotion arithmetic was
  direction-blind.

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

unverified:
  - claim: "P0c-2 (legacy may not originate authority) meets its acceptance bar."
    what_would_verify: "Its builder's mutation controls, then an orchestrator re-run of both: (a) legacy-only family eligible again -> a test must fail; (b) legacy N + explicit N summed for the threshold -> a test must fail."
  - claim: "The first nightly actually writes evidence_clock_start files for the three families."
    what_would_verify: "After #5577 merges, read data/qledger/evidence_clock_start/ on main the morning after the next nightly."
  - claim: "P2 (#5534) has no genuine defect behind its unrun-government-revenue-grader red."
    what_would_verify: "Read the ci-pack-3 job log for that step; confirm whether the govrev grader is failing on the merge ref for a reason unrelated to #5534's diff."

unresolved:
  - "The control leg (DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG) — CEO decision requested in sitrep §11: wire control_for_sector() at registration, or stop claiming a control arm."
  - "engine/source_registry.py is a second horizon implementation on a live grading path; its while loop is unbounded where the clock's walkers fail closed."
  - "Two aggregations outside qledger pool across clock bases (source_registry hit_rate, report_importance_duel::_slice_stats). Single-basis today; fuse is the first night new claims mature."
  - "The claim-side clock_market stamp is write-only — nothing reads it, so its stated 'a suffix-table change becomes visible' guarantee is not implemented."

next_actions:
  - "Confirm #5534, #5577 and the P0c-2 PR merged; capture their merge SHAs."
  - "The morning after the next nightly, read data/qledger/evidence_clock_start/*.json and record the three real evidence-clock start timestamps — this is the deliverable the CEO asked for and it did not exist at this session's end."
  - "Take the CEO's ruling on the control leg (sitrep §11) and open the follow-up PR it implies."
  - "T1 resumes in a FRESH session from research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md — deliberately not restarted here."

do_not_redo:
  - "The horizon defect is NOT a one-line in_scope_horizons fix. That was the 08-12 diagnosis and it was wrong about the cause. Superseded report: PR #5512, closed."
  - "Do not register retrospective claims for the three desks. claude/eval-os-t9-adoption tried it; 3/3 adversarial reviewers refused it."
  - "Do not add a `backfilled` flag as a compromise — nothing reads it."
  - "Do not extend GRADE_HORIZONS above 63 (LH-U6)."
  - "Do not resolve a claim's market from shape alone or provenance alone."
  - "Do not 'fix' the 17 graded cells that now read None after #5573 by restoring the bench fallback. None is the honest state when no control leg exists."

danger_areas:
  - "engine/qledger.py is edited by many lanes at once. Four PRs in this wave touched it in different functions; every one needed a rebase onto post-merge main. ALWAYS `git diff --stat origin/main HEAD` before opening a PR — a builder that branched pre-merge will silently show a sibling's files as DELETED, and merging that reverts their work. This nearly shipped: P0b's first diff showed P1's test file at -431 lines."
  - "Never reuse a worktree that has a live agent in it. Checking out another ref under a running builder detaches its HEAD; caught and restored here with nothing lost, but only because the builder had not committed yet."
  - "New test files must be named by a `run:` step in .github/ci/legacy-jobs.yml or the workflow-yaml fence reds the PR. P3's two suites shipped dark and were caught by that fence, not by review."
  - "data/qledger/*.jsonl are append-only nightly stores. Any test assertion over their contents is illegal if appending a row can falsify it."

prs: [5471, 5512, 5519, 5534, 5559, 5563, 5572, 5573, 5577]
discoveries:
  - DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG
---

## Cold-start orientation for the next Eval-OS session

Read, in order: `research/EVAL_OS_SITREP_2026-08-14.md` (what the wave found and what it
withdrew), `research/EVAL_OS_P0A_HORIZON_CLOCK.md` (the clock contract and its disclosed
residuals), then this handoff's `do_not_redo`.

The single most important thing to know: **the evidence clock has not started.** P3 is
built and correct, and it registers zero claims today because every row in the desk stores
predates the programme. The number that matters is the first
`data/qledger/evidence_clock_start/<family>.json` written by a real nightly — and no
session may create that file by hand, because doing so is precisely the retrospective
stamping the whole design exists to prevent.

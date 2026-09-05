---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad1t1-t1-incremental-cadence (worktree thetadata-canonical-options-source-da82b6)
model: fable
ended_because: complete
mission: >
  AD-1T1 (Sol handoff 2026-08-22): extend the one-session T1 writer into the
  canonical full-universe daily incremental maintainer; retire the whole-year
  DAILY refresh + unconditional KeepAlive; writer exclusion; daily
  source-health receipt; benchmark-frozen concurrency; finite periodic
  launchd daily lane (NOT installed); return PR #6267 to Sol UNMERGED.
state_before: >
  AD-1T0 merged (a45ac6f58e63): producer on the canonical ThetaData store,
  honest INSUFFICIENT_COVERAGE at 39/375 — the T1 spine refreshed only a
  48-root list by re-downloading the whole current year nightly (~4-5 h for
  48 roots, two chained passes 20:10Z→~01:10Z). Sol ruled the ~19 h
  full-universe estimate indicts that whole-year re-pull design, not vendor
  throughput. No lock file on the store; _manifest.json full-replaced by the
  backfill (its universe_pass_complete guard INERT); zero topup tests.
changed:
  - {path: scripts/topup_thetadata_day.py, what: "--daily incremental mode (ensure law EOD[S]/Greeks[S]/OI[S]/OI[D]; S-panel healthy receipt; 65-min deadline; flock; failure taxonomy incl. fetch_failed superset + date_unresolved; run-context freeze; tmp rename + sweep; workers default 4 frozen from ladder) + --roots @universe catch-up"}
  - {path: scripts/backfill_thetadata_eod.py, what: "flock in main(); store-agreement refusal vs resolve_thetadata_store() (fresh-install exception); _write_manifest read-modify-write preserving daily_refresh, corrupt-read fail-open"}
  - {path: "scripts/launchd/theta_daily_refresh.sh + com.macro.thetadata-daily.plist", what: "new finite periodic daily lane, fires 13:20/14:30/16:00/18:00 PT, RunAtLoad, no KeepAlive — NOT installed on m1 (Sol §23)"}
  - {path: "scripts/launchd/theta_backfill_keepalive.sh + com.macro.thetadata-backfill.plist", what: DELETED — whole-year daily refresh retired from the repo estate}
  - {path: scripts/launchd/theta_staleness_sentinel.sh, what: "daily_refresh.D staleness-anchor ALERT (threshold 20:00 ET — the only value the existing 06:15/18:30 PT fires can satisfy) + fail-closed on calendar-eval failure"}
  - {path: "scripts/publish_r2.py + .gitignore", what: "_writer.lock and .tmp-suffixed files excluded from R2 + git"}
  - {path: research/THETADATA_OPS_RUNBOOK.md, what: "transition procedure (ops-tree byte refresh, bootout+pkill, bootstrap, TZ/no-sleep asserts, installed_live_status: NOT_INSTALLED), @universe catch-up, ONE_OFF_CLOSURES maintenance, anchor semantics"}
  - {path: ops/LIVE_FLOW_RUNBOOK.md, what: lane rows corrected (backfill retired, daily NOT_INSTALLED)}
  - {path: .github/ci/legacy-jobs.yml, what: three new test suites + import-closure paths wired into flow-surface (contract-delta clean)}
  - {path: research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md, what: frozen spec through R3 + §F ladder freeze (W=4)}
  - {path: research/ADVANCED_DATA_OPTIONS_AD1T1_THETADATA_INCREMENTAL_T1_CADENCE_HANDOFF_2026-08-22.md, what: Sol handoff committed as repo-resident authority}
  - {path: agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md, what: AD-1T1/AD-1T2 wave rows + stale next_action corrected}
  - {path: agentos/discoveries/DSC-THETADATA-19H-ESTIMATE-WAS-THE-WHOLE-YEAR-DESIGN.md, what: Sol §22 discovery minted}
  - {path: "tests/test_topup_thetadata_legacy.py + test_topup_thetadata_daily.py + test_topup_thetadata_scheduler.py", what: "152 tests (final) — characterization-first legacy pin + full §H hostile families + reviewer-round regression pins + §K/K6 amendment families"}
  - {path: "scripts/topup_thetadata_day.py (amendment round)", what: "Sol B1: AD-ready healthy split (s_panel_* observational; ad_ready_* gates healthy; OI[D]-absent => partial, inverted test) + OI[D] frontier via collectors.thetadata.snapshot_open_interest wrapper (no pre-filter — guard enforced at _merge_day's exact-date write; dedup after column selection; missing-OI column => fetch_failed; oi_D_source stamped only on actual vendor attempt)"}
  - {path: "scripts/backfill_thetadata_eod.py (amendment round)", what: "Sol B2: resolver exception in store-agreement check fails CLOSED (exit 1, zero mutations — own_store/_store_dir() computed only after a clean resolver return); None stays the fresh-install exception"}
  - {path: "scripts/launchd/theta_staleness_sentinel.sh (amendment round)", what: "Sol B3: anchor validates health — after 20:00 ET session day, ALERT unless D==session_date AND status==healthy AND forced exactly false; verdict gains daily_refresh_status/forced"}
  - {path: "research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md (§K/§K6)", what: "Sol B4 deadline contradiction repaired in place (65 min); §K binding amendment spec; §K2 wrapper adjudication; §K6 targeted-review adjudication; §D dead S-panel law + stale 22:00 ET repaired in place"}
verified:
  - {claim: "one-day full-universe refresh fits the evening envelope at every worker count — the 19h figure was the whole-year design", command: "ssh m1 plane-python /tmp/ad1t1-bench/ad1t1_bench.py --configs 1,2,4,6 (quiet window 00:30-00:34Z)", result: "24-root wall 122.9/56.3/28.5/20.9s at W=1/2/4/6; stratum-corrected 378-root projections 25.8/12.6/6.0/4.6 min; 0 errors in 312 calls; no knee; Terminal RSS fell 941->799MB"}
  - {claim: "new suite green across hash seeds", command: "pytest tests/test_topup_thetadata_{legacy,daily,scheduler}.py (PYTHONHASHSEED=1/42/987654321/20260822/13337 across rounds)", result: "133 passed (final); 108/128 at earlier rounds; plus 177 neighbor tests green"}
  - {claim: "engine and collectors byte-unchanged", command: "git diff --stat origin/main...HEAD -- engine/ collectors/", result: empty}
  - {claim: "contract-delta clean on the final wiring", command: "python3 scripts/check_contract_delta.py --base af7f4af9a86c", result: "0 introduced, 0 inherited"}
  - {claim: "canonical store untouched by the benchmark", command: "ssh m1 stat -f %m .../thetadata_eod before/after + find -newer marker", result: "mtime 1785404097 unchanged; find empty"}
  - {claim: "main-red heal landed (unrelated inherited red)", command: "gh pr view 6263 --json mergedAt", result: "MERGED 2026-08-22T21:50:19Z as 930d1546648b"}
  - {claim: "opus adversarial review round closed", command: "reviewer verify-pass on head c8e17e69d716 + micro-round fe0d6a5647d7", result: "12 findings all repaired and regression-pinned; verify verdict SHIP; residual N1/N3 closed, N2 documented, N4 spec-fixed"}
  - {claim: "Sol B1-B4 amendment round implemented + targeted-reviewed", command: "pytest the three topup suites, PYTHONHASHSEED=42 and 987654321", result: "152 passed both seeds; targeted opus pass verdict NO BLOCKER, 2 MAJOR (backfill mkdir-before-refusal; wrapper missing dedup) + 3 NOTEs repaired and regression-pinned in e8fc7c19d9fb; NOTE-4 (sentinel fire inside last rung's window) reported to Sol, not repaired"}
unverified:
  - {claim: "OI[D] same-evening availability (the F1 unknown)", what_would_verify: "first post-merge scheduled session's receipt oi_D_roots (Sol §19); the collector converts the v3 current-day-wildcard 400 to an empty frame and no live session was available this weekend"}
  - {claim: "production wall time at full-universe scale under the real scheduler", what_would_verify: "first scheduled session's daily_refresh.elapsed_sec"}
  - {claim: "final CI conclusion on the ship head", what_would_verify: "gh pr checks 6267 after packs conclude — reported in the PR's Sol packet comment"}
unresolved:
  - "RESOLVED by Sol review 5001472540 (2026-08-23): the S-panel healthy split was REJECTED in favor of the AD-ready law (healthy requires OI[D]; implemented as §K1); the fetch_failed superset was ACCEPTED/ratified. Remaining open: Sol acceptance of the B1-B4 amendment round itself (review of the new head)."
  - "NOTE-4 for Sol's install decision: the sentinel's 18:30 PT fire lands inside the 18:00 PT rung's 65-min window — a self-healing night can page once at 18:30 PT."
  - "Reported, not repaired (out of §I scope): ops/launchd/com.macro.thetadata-r2sync.plist prose still describes the retired 48-root lane, and full-universe daily refresh grows the nightly R2 delta ~3x (~5 GB vs ~1.7 GB) once r2sync is healed (it is currently broken — separate chip)."
  - "Live m1 ops trees are stale/detached: collectors/thetadata.py on m1 predates the #5942 NA-parse fixes — the transition's mandatory ops-tree byte refresh fixes this, but until Sol accepts and the transition runs, the CURRENT whole-year lane keeps writing with the old parser."
next_actions:
  - "Sol: re-review PR #6267 (DRAFT, HOLD-FOR-SOL) at the post-amendment head — B1-B4 implemented per §K/§K6, targeted-reviewed (no blocker, 2 MAJOR repaired), rebased onto fresh main; rule on NOTE-4 fire spacing at install time."
  - "On acceptance: execute the runbook §3a transition on m1 (ops-tree byte refresh -> bootout com.macro.thetadata-backfill + pkill orphans + verify -> bootstrap com.macro.thetadata-daily -> TZ/no-sleep asserts). NOT done this wave (Sol §23)."
  - "§19 production proof: two consecutive normal scheduled sessions (the first also answers the OI[D] F1 unknown); then the read-only AD producer diagnostic on the store host; then AD-1T2 (restore theta-m1 workflow; commission AD-1 end to end)."
do_not_redo:
  - "Do not re-benchmark under backfill load — the retiring loop holds the Terminal 20:10Z->~01:10Z nightly; quiet-window numbers (this handoff) are the selection evidence."
  - "Do not use expected_last_session() for the daily gate — its 17:00 ET settle buffer returns the WRONG D between 16:10 and 17:00 (pinned by test)."
  - "Do not gate healthy on OI[D] — same-evening availability is unmeasured; the S-panel split is the Sol-flagged design."
  - "Do not resurrect the current-year-unmark trick or scale REFRESH_ROOTS — catch-up is `--roots @universe --date` (3-tier ensure); history is the explicit backfill."
  - "Do not name any store tmp file *.parquet — store readers glob it (reviewer F9; tmp is now {YYYY}.parquet.tmp, swept at startup)."
  - "Do not move the staleness-anchor threshold above 21:30 ET — the sentinel's existing fires land 09:15/21:30 ET; anything later is dead code (reviewer F1)."
danger_areas:
  - "_manifest.json has TWO writers — both only under the shared flock; a lock-refused run must never touch it (its record is the writer_locked JSON log line + exit code)."
  - "The levels-seal pre-open caller depends on the legacy --roots exit-code triple and non-fatal-failure shape; --daily exits 0 on lock refusal BY DESIGN — do not 'fix' either direction."
  - "m1 ops worktrees are detached hand-patched clones — repo merges do NOT reach them; every install goes through the runbook's byte-refresh step."
  - "backfill_thetadata_eod refuses when resolve_thetadata_store() disagrees with its checkout-relative store dir — that refusal is the second-store guard, not a bug."
prs: [6267, 6263]
decisions: []
discoveries: ["DSC:THETADATA-19H-ESTIMATE-WAS-THE-WHOLE-YEAR-DESIGN"]
---

AD-1T1 delivery handoff. Cold-stranger path: read the committed Sol handoff,
then spec R3+§F (both in research/), then PR #6267's description and Sol
packet comment. The PR is PARKED / HOLD-FOR-SOL — never arm merge-on-green
on it; release condition is an explicit Sol acceptance.

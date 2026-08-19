# Prophet US Availability Hardening — masterplan + runbook (2026-08-14)

Owner: main-loop adjudication (Fable), commissioned after the 2026-08-11/12/13 outage.
Program home: `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` (this doc is the
availability annex). Delivery PR: branch `claude/prophet-us-availability-hardening`.
Sibling lane (detection, discovered mid-design and reconciled): **PR #5487**
`claude/nightly-liveness-watchdog` — landing separately; this plan builds the RESPONSE
and RESILIENCE layers on top and deliberately does not duplicate it.

## §0 ACCEPTANCE GATES (not done unless)

1. `scripts/prophet_rescue.py` exists, stdlib-only imports (plus `lib.nyse_calendar`),
   with a **pure decision core** `decide(state) -> actions` — no network, no clock reads
   inside; every behavioral gate below is pinned by a unit test on `decide()`.
2. Freshness verdicts key on **`source_asof`** and the **newest `recorded_at` plan
   cohort** — NEVER top-level `asof`/`recorded_at` (wall-clock stamps;
   `scripts/build_prophet.py:2100` warns exactly this). A fixture with
   `asof == today, source_asof == 3 sessions ago` MUST alarm.
3. Session math = `lib.nyse_calendar.expected_last_session()` / `sessions_behind()` —
   no third calendar implementation. Sat/Sun quiet after a Friday bake; Monday-holiday
   Tuesday expects Friday. Fixture-pinned.
4. Dispatch-safety invariants, each MUTATION-PINNED (flip guard → named test reds):
   a. NEVER dispatch while any daily.yml run is `queued`/`in_progress`.
   b. Budget: ≥2 `workflow_dispatch` daily.yml runs created since 21:00Z (any actor) →
      alert-only.
   c. NO cancel code path anywhere in the new files.
   d. GitHub API read failure → no dispatch (fail toward alert, never blind dispatch).
5. The rescue lane never writes to the repo, `data/`, `site/`, or `ledger.jsonl`. Its
   only mutations: workflow dispatch, issue upsert/comment (`prophet-outage` label),
   best-effort ops webhook (heartbeat.yml's existing secret names), and `::error`/
   `::notice` annotations (bare `print`, line-start, `flush=True`).
6. `.github/workflows/prophet-rescue.yml`: GitHub-hosted `ubuntu-latest` (never
   self-hosted — fate-sharing with the Mac Studio is the failure being fixed), crons
   `40 23 * * *` + `40 0-13 * * *`, `workflow_dispatch`, permissions exactly
   `{contents: read, actions: write, issues: write}`, concurrency
   `prophet-rescue` / `cancel-in-progress: false`, sparse checkout. Exit 0 on
   healthy/wait; nonzero only when it alerted or dispatched.
7. BOTH `prophet-rescue.yml` AND `nightly-liveness.yml` added to `PROTECTED_LANES` in
   `.claude/hooks/gh_quota_guard.py`, pinned in the hook's test suite (a watchdog a
   fleet session can cancel is not a watchdog).
8. Zero *colliding* hunks with PR #5487 (AMENDED after adjudication): the original
   gate said "don't touch legacy-jobs.yml at all"; the builder registered the suite
   there because that dark-guards job is the established home for importlib
   path-literal suites the import-derived auditor cannot see. Adjudicated ACCEPTED
   after verifying disjointness (#5487 hunks at legacy-jobs:~2100 / ci.yml:~1336;
   ours at ~6919 / ~3887 — merges clean). Still binding: no NEW CI job, no
   `config/house_law_checks.yml` edit, no dag-conformance hunk.
9. This PR does not touch `.github/workflows/daily.yml` or `scripts/build_prophet.py`
   (zero risk to the next bake; first-run-bomb law).
10. launchd backstop ships as INSTALLER + wrapper mirroring the canonical GC pattern
    (`scripts/install_worktree_gc_launchd.sh` / `scripts/worktree_gc_launchd.py` —
    wrapper re-extracts from `origin/main` each run), StartCalendarInterval ~19:10 and
    ~05:10 local, host-only additions (runner-volume disk headroom ≥80 GB, macOS
    notification on alarm). NOT auto-installed — operator runs the installer once.
11. Docs: this file; AGENTS.md + CLAUDE.md recovery-etiquette delta (§6), inside
    existing daily-lane sections.
12. New test files green locally AND the registered CI job's exact pytest line re-run
    green before push; daily.yml verified untouched via git status.

## §1 Incident record (what actually happened — receipts in PR body)

| Night (22:30Z cron) | Outcome | Root cause |
|---|---|---|
| 08-10 (Mon) | Bake ran; 25 plans recorded_at=08-10 | healthy (last good night) |
| 08-11 (Tue) | **Never ran** — cron produced no run; 4 dispatches queued jobless forever | #5362 pushed daily.yml 507,987→515,780 B over GitHub's silent ~512 KB processing cap 57 min before the cron. Healed #5416 (revert + `tests/test_workflow_file_size.py`), #5431 diet (465,841 B now vs 487,000 budget) |
| 08-12 daytime | 6 recovery dispatches killed in 21 s–11 min | Rogue **codex** session force-cancelling (receipt `POST /actions/runs/31583415065/force-cancel`; transcript `rollout-2026-08-11T04-10-51-…`, still active 08-13). Claude-side fence landed #5488; codex prose-bound only; **operator arbitration outstanding** |
| 08-12 night | Bake 31649984834 fired 23:11Z (41 min late = normal band 27–90), Prophet checkpoint 03:28Z (**25 plans recorded_at=08-12, asof→08-12**); run flipped `cancelled` 06:32Z in a tail job | Tail-job kill at 7h20m, unattributed; **Prophet had already delivered hours earlier.** Run-conclusion ≠ artifact truth |
| 08-13 pre-market | Retry 31671422158: 13 h, `publish` green, asof→08-13, **0 plans originated** (`source_mixed_vintage: true`, `gate_go: false`); 2 jobs failed | Job failures = **disk-full on `actions-runner-2`** (`No space left on device`, 14:29Z; cleared, 313 GB free now). Zero-origination = correct vintage-gate behavior for a mid-day bake |
| 08-13 night | Run 31753425298 in flight (23:20Z start; `collect` ~3 h envelope normal) | — |

GitHub platform: **zero Actions incidents in the window** (githubstatus history). The
outage was self-inflicted three independent ways. Serve paths verified healthy 02:1xZ
08-14: VPS `/api/status` site.commit 13 min old; public R2 `prophet/index.json`
matches main (source_asof 08-12, 25× recorded_at 08-12 plans).

User-visible cohorts on main: …08-10: 25 · **08-11: 0** · 08-12: 25 (landed 23:28 ET,
after that trading day) · **08-13: 0 pending tonight's bake**.

## §2 Why every existing sensor missed it (and what #5487 already fixes)

- `index.json.asof` is `date.today()` at bake time — self-refreshes even when data
  freezes; the honest field (`source_asof`) had zero readers repo-wide.
- `heartbeat.yml`/`scripts/healthcheck.py`: 96 h budget (weekend-safe by design), no
  prophet witness, runs on the same self-hosted pool it watches.
- VPS `freshness_sentinel.py`: `PROPHET_MAX_SESSIONS_BEHIND=1` is correct and cannot
  tighten — ~24 h designed blindness between close and bake.
- `check_dead_cron` (metabolism immune): only sees run records that exist; a no-fire
  night creates none. A killed bake and a never-fired bake leave the same trace.
- **PR #5487 (`scripts/check_nightly_liveness.py`) closes the detection gap**: A
  run-created (strand, ~hours), B run-concluded, C source_asof advanced —
  NYSE-calendar-anchored, GitHub-hosted, blind→INDETERMINATE. It is detection-only:
  red checks, no response.

## §3 Architecture — division of labor

**Detect** = #5487 nightly-liveness (A/B/C, red check) + rescue-side additive coverage
#5487 lacks: `SERVE_SPLIT_R2`/`SERVE_SPLIT_VPS` (main fresh, edge stale) and
`NO_COHORT` (source_asof fresh, zero plans for the expected session while intake
eligible > 0 — the mixed-vintage wedge; alert-only, dispatch can't fix code).

**Respond** = `scripts/prophet_rescue.py` (this PR): snapshot {main index.json via
contents-API raw, public R2, VPS /api/status, daily.yml runs (1 REST call)} → pure
`decide()` → verdicts HEALTHY / WAIT / STRAND / STALE / NO_COHORT / SERVE_SPLIT_* /
API_DARK. On STRAND/STALE (+newest run cancelled/timed_out): re-dispatch daily.yml
under §0.4 gates, receipt to the outage issue. Deadline ladder UTC: no-fire callable
from 01:40Z (cron fires 22:30Z +27–90 min; never call no-fire before ~00:20Z);
completion 09:40Z; hard-alarm floor 13:40Z. Cancels become self-defeating: every kill
re-armed ≤1 h later, receipted publicly.

**Survive** = GitHub-hosted lane (survives Mac Studio death) + launchd host lane
(survives GitHub scheduler death; disk-headroom + local notification; §0.10) +
PROTECTED_LANES for both watchdog workflows.

**Red-team amendments (2026-08-14 adversarial review, all adopted):** (B1) an
in-flight run past the stale deadline still blocks dispatch but must ALERT — an
age-unbounded quiet WAIT reproduces both real incident shapes (13 h hung run;
jobless-queued zombie); (M2) HEALTHY requires `data_current`, else WAIT; (M3) the
dispatch budget counts ATTEMPTS via machine-token receipts on the outage issue
(max of run-records and receipts) so a failed/ineffective POST cannot retry
unbounded; (M4) the VPS serve-split VERDICT is dropped — `checks.site.commit_time`
is main's newest-commit stamp, not a pull-loop stamp, and back-tested at our own
wake times it false-fires on 5% of wakes (7/149, max quiet gap 107 min); the
commit_time is still printed as receipt context, and a real pull-heartbeat stamp
on `/api/status` is a follow-up in the VPS app; (M5) alert receipts and ops pushes
de-duplicate on unchanged verdict-sets (annotations + red run remain every wake);
(M6) run rows with unparseable `created_at`/`status` count as in-flight (dispatch-
safe direction) and are noted as parse anomalies. Live probe receipt: the
`created=>=` server-side filter on the runs endpoint works (175 all-time dispatch
runs vs 0 since 2026-08-13T21:00Z vs 1 since 2026-08-12T21:00Z — the known 05:45Z
recovery), so budget filtering cannot silently become all-time.

**Second-bake idempotence (the M7 premise, receipted):** a rescue dispatch can put
a second bake on a session whose first bake partially ran — this exact two-bake
shape already happened WITHOUT the rescue lane on 2026-08-12→13: the 23:11Z
schedule bake (run 31649984834) delivered its Prophet checkpoint (f9140631d37,
25 plans recorded_at=08-12) and was killed in a tail job; the operator-side 05:45Z
dispatch (run 31671422158) then re-ran the full nightly over the same window and
produced NO duplicate plans and no ledger double-advance (index.json carries the
origination-idempotence fences live: `intake.reorigination_blocked: 2`,
`duplicate_id_blocked: 43`; cohort census after both bakes: 08-12 = 25, exactly
once). Residual risk is scoped to non-Prophet sub-ledgers of the nightly, where
the same two-bake precedent ran clean; the rescue lane adds no NEW shape beyond
what manual recovery already does, under a tighter budget (≤2/night, never over a
live run).

## §4 Deliberately out of scope

- No daily.yml / build_prophet.py edits (§0.9).
- **No Aug-11 backfill** *(this scoping is SUPERSEDED as standing policy 2026-08-18 —
  `DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT`; force majeure now backfills by
  default and a missing origination event no longer refuses. Kept as the record of what
  this PR did and why, at the time)*: no origination event executed that night, and the 08-11/08-12
  bars were never collected — there is no bake-time board to replay. The backfill
  charter (#5305, `research/PROPHET_OUTAGE_BACKFILL_2026_08.md`) authorizes replaying a
  real refused-origination event only; a later-reconstructed board is the contaminated-
  input class #5289 refused. Product-surface gap disclosure via
  `origination_disclosure` would require build_prophet changes → operator-gated
  follow-up chip.
- No duplication of #5487 detection; no new CI job; no cancel authority anywhere; no
  third staleness calendar (healthcheck's divergent `_sessions_stale` → follow-up chip).

## §5 Test matrix (decide() fixtures)

healthy weekday · Sat/Sun quiet after Fri bake · Monday-holiday Tuesday · asof-fresh/
source_asof-stale alarm · no-fire STRAND at 01:40Z and NOT at 00:10Z · run in_progress
→ WAIT no-dispatch · newest cancelled + stale → dispatch · budget ≥2 → alert-only ·
API error → no dispatch · NO_COHORT alert-only · serve-split R2 · serve-split VPS ·
two wakes one budget (idempotence) · mutation pins for §0.4a–d.

## §6 Recovery etiquette (law delta for AGENTS.md + CLAUDE.md daily-lane sections)

The rescue lane is the ONLY auto-redispatcher of daily.yml. A session that believes the
nightly needs a manual dispatch must first read the open `prophet-outage` issue (the
rescue receipts live there) and must never dispatch while a daily run is queued or in
progress. Cancelling production lanes stays hook-denied (#5488) and prose-forbidden for
every fleet.

## §7 Rollout + runbook

Merge → sweeper; first scheduled wake covers the same night it merges (hourly :40).
Manual probe: `gh workflow run prophet-rescue.yml`, read the run summary.
Stale-morning triage order: `prophet-outage` issue → newest daily run + conclusion →
`source_asof` on main vs R2 → runner disk (`df -h`) → daily.yml bytes vs 487,000.
Operator escalations that remain open: codex-session arbitration (six receipted kills);
no codex-side technical enforcement exists; org-level protections worth considering.

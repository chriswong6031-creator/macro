# OPS HANDOFF — 2026-08-06 emergency session (account switch)

Written ~20:4xZ by the emergency-triage session. Everything below is
self-contained: a fresh session on ANY account can execute it. Read
`research/NIGHTLY_RESILIENCE_AND_LIVE_TRANSITION_MASTERPLAN_2026-08-06.md`
for the full program; this file is only the live baton.

## Ground truth (verified, not inferred)

- The 6-day stale US board = daily.yml `engine` hard-cancelled at ~205m vs a
  200m cap on 08-05 AND 08-06 (different hosts). **Healed: #4741** (cap 240).
- "Total GitHub traffic jam" = **GitHub Actions major outage** (platform-side,
  incident opened 18:46Z). Repo is public → NOT a minutes/billing issue; a
  plan upgrade buys nothing. Self-hosted runners kept working throughout.
- Main's ci-pack-2 was genuinely red (4 causes). **Healed: #4752** (merged).
  ci-pack-0 proved green on the partial 19:24Z run; packs 1/3 outage-cancelled,
  unproven — the post-recovery proof run covers them.
- M1 disk: was 28Gi free — **now 118Gi** (TM local snapshots purged ~75G by
  operator sudo; runner-1 .git gc'd 29G→14G; theta store 60G moved to SSD).
- Sweeper (`merge-on-green.yml`) is HEALTHY — it was correctly blocking on
  genuine reds, then starved by the outage. No repo fix needed.

## BATON 1 — Nightly run → boards live (highest priority)

- Run **31127471922** (workflow_dispatch on main, created 20:15Z) is the
  post-close rerun with the fixed caps. It was `pending` behind the cancelled
  pre-close run 31126815311's `if: always()` cleanup at handoff time.
- Watch: `gh run view 31127471922 -R mastermindx-market-intelligence/macro` every ~10
  min (NEVER `gh run watch` at default interval; quota law: --interval 60+).
- Timeline if healthy: collect ~3h → engine ≤4h (cap 240) → "commit engine
  outputs" → VPS pulls main within 3 min → boards live.
- On SUCCESS verify live: `https://www.mastermind-x.com/us_stocks.html` shows
  fresh Prophet picks (was frozen at 2026-07-31) and `china.html` bake stamp
  is current. That closes the operator's #1 ask.
- On FAILURE: get failing JOB+STEP (`--json jobs`), compare against
  `docs/`-committed knowledge: collect data-source reds are survivable
  (engine runs `if: always()`); only an engine kill or commit failure costs
  the night. Fix, re-dispatch: `gh workflow run daily.yml --ref main`.
- The 23:28Z scheduled nightly queues behind whatever is running
  (concurrency `pipeline-daily`, no cancel) and is a SECOND shot — it
  inherits the fixed caps. If both die, diagnose before any third dispatch.

## BATON 2 — collect_tail tonight = SSD theta store's first live run

- Theta store now lives at `/Volumes/STORAGE/macro-data/thetadata_eod` on the
  M1 (ssh alias `m1`), reached via per-tier symlinks at
  `~/flow-ops-wt/data/thetadata_eod/{eod,oi,greeks}`. Resolver verified;
  writers (thetadata-backfill, thetadata-r2sync, theme-options-witness)
  restarted; swap is git-invisible (`.git/info/exclude` entries added).
- After tonight's `collect_tail` job AND one options-witness cycle conclude
  green: `ssh m1 'rm -rf /Users/chriswong/flow-ops-wt/data/thetadata_eod/{eod,oi,greeks}.OLD'`
  → frees ~60G more (internal disk then ~178Gi free).
- If the SSD unmounts, symlinks dangle → resolver returns None → honest-null
  degradation (designed). Rollback: remove symlinks, `mv X.OLD X` back.

## BATON 3 — PR drain (56 armed PRs) once GitHub recovers

1. Confirm recovery: `curl -s https://www.githubstatus.com/api/v2/components.json`
   → Actions `operational`.
2. Dispatch the proof: `gh workflow run ci.yml --ref main` → wait for GREEN
   (30–34 min). Main now carries #4741+#4743+#4752 and should pass; this run
   also satisfies the sweeper's integration-baseline circuit breaker.
3. Refresh armed PRs in batches of ~8 (NEVER all at once — a 28-PR refresh
   starved the runner pool this morning):
   `gh api -X PUT repos/mastermindx-market-intelligence/macro/pulls/<N>/update-branch`
   Skip any that 422 with a real conflict (they need manual rebase).
4. The sweeper (cron every ~10 min) merges as heads green. Do not merge
   mid-flight by hand; `--admin` only for docs-only/spurious-Workers-X/wedge.
5. **OPERATOR-ONLY — do not resolve:** #4512 (rail design contradiction;
   checks clean, genuine content conflict) and #4622 (FISV/MRSH ticker key
   migration — a data migration, ~67 qledger refs).

## BATON 4 — parallel chip sessions in flight (they own their PRs)

- W1 VPS freshness sentinel · W2 85%-of-cap alarm · W3 build_news GDELT
  de-rate · W6 CBOE/SEC/tushare forensics · vanna 5-session date-anchor
  (ledger-affecting). W2+W3 both touch daily.yml — the second to land may
  need a trivial rebase. Commission gates are in each chip's prompt.

## BATON 5 — queued work, not started

- **Prophet US pick backfill Jul 31→Aug 6** (operator-approved as
  approximate). Constraints: forward-ledger commit law is per-FILE; nightly
  is the sole advancer; backfilled rows need marked provenance (do NOT
  rewrite forward ledgers silently — a marked-provenance side lane or an
  era-annotated append, decided in its own session).
- M1 leftovers: `macOS Install Data` 12G is SIP-locked (use Software Update
  UI or recovery mode, operator, whenever); Time Machine currently DISABLED
  by design — operator must either reattach a destination or accept no TM;
  optional second-pass `git gc --aggressive` on runner-1 (14G→~5G).
- China board "offline": unresolved what the operator SEES. If locked/empty
  panels → auth-session outage class (negative-auth-cache → logout). If old
  dates → tushare dark since 07-27 (W6 owns). Live-quote plane and page
  serving verified healthy at 20:1xZ. Ask the operator which it is.

## Standing cautions for the successor session

- GitHub REST quota is ONE shared bucket; hooks fail closed when it empties.
  No `gh run watch` under `--interval 60`, no `--paginate` on check runs,
  no gh loops sleeping <90s. Preflight `gh api rate_limit`.
- ci-pack-N indices are not stable job ids — compare JOB+STEP names.
- CI tests the MERGE REF (head+main at run start), not the branch head.
- The M1 and the Studio share the username/paths — identify a machine by
  runner agentName, never by path.

## ADDENDUM 2026-08-07 08:2xZ — the third dead nightly was HOST OVERLOAD, not caps

Run 31127471922: collect killed AT the new 240m cap (00:06→04:06Z on
mac-builder-5), engine killed AT its 240m cap (04:10→08:10Z, same host). Same
host ran collect in 172m cold two nights earlier — the caps were sufficient;
the HOST was not. At 08:16Z the Studio's load average was **79** with ~493
claude-related processes: the five parallel chip build-sessions (and their
Opus subagents running pytest) shared the box with the runner all night.

**Law for the successor: the CI host is not a fleet host during a render
window.** Before any daily re-dispatch or tonight's 23:28Z schedule:
1. `uptime` on the Studio — do not dispatch above ~load 8.
2. Let the chip sessions conclude (or the operator pauses them); they are the
   load.
3. Prophet picks are the ONLY stale surface left (engine-render scope=all
   healed the rest to 2026-08-06 data). One clean daily run closes it — and
   pulling Aug-6 EOD remains correct any time before Aug-7's close.
4. Longer-term fix belongs to the masterplan's W5: pin `macstudio` nightly
   jobs to the M1 pair during fleet-heavy periods, or reserve the Studio
   spare for CI only.

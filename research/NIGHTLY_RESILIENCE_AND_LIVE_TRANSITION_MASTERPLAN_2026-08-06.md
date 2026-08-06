# Nightly Resilience & Live-Transition Masterplan

**Date:** 2026-08-06 (commissioned by the operator during the stale-board emergency)
**Status:** Part A = actionable program; Part B = trajectory ruling on top of the
already-ratified live architecture
**Extends:** `research/LIVE_INTRADAY_DASHBOARD_MASTERPLAN_2026-07-29.md` (ratified —
this doc does NOT re-adjudicate it), `research/LIVE_DATA_ARCHITECTURE.md`,
`docs/VPS_LIVE_ORCHESTRATION.md`
**Does not create:** a second forecast engine, a second forward ledger, a SPA
rewrite, or any change to the epistemics laws (display vs authority tiers,
nightly as sole forward-ledger advancer, LLM never originates signals).

---

## §0 ACCEPTANCE GATES (Part A — "never again")

Part A is **not done unless**:

1. **A stale live board alerts a human within 26h, from OUTSIDE GitHub.** A
   sentinel that lives in GitHub Actions is blind to the two outages that
   actually happened (GitHub Actions major outage 2026-08-06; six failed
   nightlies that concluded "red" into a channel nobody watched). The gate is:
   kill the nightly for one simulated day → an alert demonstrably fires.
2. **Timeout creep is visible before a kill night.** Any daily.yml job crossing
   85% of its `timeout-minutes` emits a `::warning` (line-start, bare print —
   the repo's annotation law) AND a row in a timings ledger. Gate: the ledger
   exists, has ≥1 night of rows, and a synthetic 86% run trips the warning.
3. **The M1 host has ≥100 GiB free and the theta store lives on the SSD**, per
   the ranked migration plan (snapshots → installer → git gc → per-tier
   symlinks). Gate: `df` screenshot + one clean `collect_tail` night after the
   move + `flow-ops-wt` git status clean.
4. **A cold-spare failover is a runbook, not an improvisation.** Gate: the
   spare-activation steps (label add/remove, what cannot fail over — theta-m1)
   are in `docs/`, and every timeout cap that assumes a warm cache states the
   cold-pace number (collect and engine now do; audit the rest).

## Part A — Never-again nightly

### A1 What actually broke (measured, Aug 2026 — three independent causes)

| Cause | Evidence | Blast radius |
|---|---|---|
| **engine timeout creep**: 200m cap, killed at ~205m two nights straight on two different hosts (mac-builder-5 then -1) | runs 31056495943, 31067383446 | no `commit engine outputs` → boards frozen Jul 31→Aug 6; Prophet pick gap |
| **GitHub Actions platform outage** (hosted runners not acquiring) | sweeper zero-step FAILUREs 17:15Z/18:41Z; main proof run queued 25m+; githubstatus: major_outage 18:46Z | PR proving, merging, pages deploy ALL dead at once — read as "total traffic jam"; 56 armed PRs stuck |
| **M1 disk: TM local snapshots pinning ~80 GiB** against an unreachable backup destination (+ theta store growth, + 29G git bloat in runner-1) | cache purge freed 8 MiB for 1.9 GB deleted; du-vs-df gap | ENOSPC hard-down 08-05; 28 GiB headroom = one bad night from repeat |

Secondary, real but non-fatal: CBOE options-chain whole-family session gaps
(worsening nightly), SEC CS_TERMS compile failure, tushare plane dark since
07-27 — the pipeline degraded to honest-null as designed (`engine` has
`if: always()`), and #4731 split collect's checkpoint so a capital-structure
failure cannot cost the night's market data.

Already shipped during the emergency: collect cap 185→240 under the cold-spare
law (#4731), engine cap 200→240 (#4741), cache purges, ranked SSD plan.

### A2 Workstreams (ranked by outage-hours prevented per unit effort)

**W1 — External freshness sentinel (the dead-man switch).** A cron on the VPS
(not GitHub) fetches the live pages' own bake stamps (`us_stocks.html`,
`china.html`, hub) and the R2 `massive_stock_day` publish time; if anything
exceeds its freshness budget (26h bake / per-plane budgets), it emails/pushes
the operator and writes a visible banner state the site itself can surface.
The 6-day gap happened because "red run in a channel nobody watches" is
indistinguishable from silence. Silence must become impossible: the check
lives on infrastructure that fails independently of GitHub. (The existing R2
freshness tripwire inside `engine` is the right idea in the wrong place — it
only fires when the nightly RUNS.)

**W2 — Runtime budget telemetry + 85% trend alarm.** Every cap raise in
daily.yml's history (70→120→150→200→240 engine; 40→120 tech_lab;
100→150→185→240 collect) followed dead nights, never preceded them. Add a
tiny per-band timing ledger (job start/end per named band, committed nightly or
pushed to R2) + a guard that `::warning`s at >85% of cap. Caps then get raised
from trend data BEFORE a kill night. This is ~30 lines of shell in the jobs +
one reader script.

**W3 — Workload trims.** build_news GDELT de-rate first (~26–29m of 429
backoff inside the engine critical path even on green nights — cache/de-rate
or move into the parallel builders band, per the engine comment's own "next
lever"). Then re-measure; do not inherit step-cost labels (tech_lab law).

**W4 — Disk program on the M1.** Execute the ranked plan (operator sudo
required for ranks 0/3): TM snapshots ~80G → `tmutil disable` decision →
macOS Install Data 12G → `git gc` runner-1's 29G `.git` → theta store 60G to
`/Volumes/STORAGE` via per-tier symlinks (no repo PR needed — the resolver
follows symlinks). Explicitly REJECTED: relocating runner `_work` to the SSD
(case-sensitive HFS+ under a git checkout; USB unmount kills all jobs; only
~28G marginal after the gc). Ratify the Worktree GC (#4563) on the Studio —
the disarmed guard is a slow outage, already proven once at 223 worktrees.

**W5 — Runner fleet redundancy.** The label failover WORKED (mac-builder-5
took collect cold). Codify it: spare-activation runbook; keep `macstudio` on
one Studio spare permanently (operator choice 2026-08-05, make it standing);
the only non-failoverable job is `collect_tail` (theta store is M1-local —
after W4 the store is on a portable SSD, which *creates* the option of
re-homing it if the M1 dies). Cloud/VPS runners: NOT for the mac-bound engine
band (data locality, cost); OPTIONAL as a burst lane for Linux-tolerant jobs —
but note the 2026-08-06 lesson cuts the other way: our self-hosted fleet was
the thing that KEPT working while GitHub's own hosted pool died. The
resilience buy is a second *alerting* path, not a second compute pool.

**W6 — Data-source forensics lane.** CBOE whole-family gaps (backfill +
root-cause the growing session misses), SEC CS_TERMS, tushare token (#4676).
These are display-tier data outages — they never block the build (epistemics
law) but each one quietly narrows confluence inputs
([[dead-shared-input-caps-the-confluence-count]] class).

### A3 Explicit non-goals for Part A

No nightly rewrite, no orchestrator swap, no new CI system. The nightly's
problem was budgets, disk, and observability — not its existence. Part B owns
its gradual dissolution.

## Part B — The breathing dashboard (trajectory, extending the ratified plan)

### B1 What is already ratified (unchanged)

The 07-29 masterplan rules: hybrid product — committed HTML shell + always-on
live data plane + browser hydrators on high-change islands + same-origin
API/SSE as the stable contract; canonical vintages/scores/ledgers stay
single-writer nightly. A SPA rewrite is explicitly not the remedy. This doc
does not reopen any of that.

### B2 The trajectory ruling (what "supersede the nightly" actually means)

The end-state is NOT "the nightly, but every 5 minutes." It is a **cadence
split along the authority boundary** the repo already enforces:

- **Display tier → continuous.** Every fact whose useful life is minutes
  (quotes, breadth, flow, live signal *readings*) migrates island-by-island
  onto the VPS live plane per the ratified architecture. Each island that
  migrates is REMOVED from the render path, so the nightly's engine band
  shrinks monotonically — the creep that killed Aug 2–6 reverses
  structurally instead of being re-budgeted forever.
- **Authority tier → stays batch, gets small.** Forward-ledger advancement,
  grading, calibration, vintages, promotion gates remain a nightly
  single-writer checkpoint (epistemics law). Freed of page rendering and news
  sweeps, that job trends toward a <60m data-and-ledgers run that fits any
  runner, cold or warm.
- **The site becomes reader, not artifact.** Pages progressively read the
  JSON/SSE plane; the committed-HTML shell remains the resilience floor
  (VPS 3-min pull), exactly as ratified. When GitHub is down, the shell
  serves; when the VPS plane is down, the shell's last bake + honest
  staleness banners serve (W1's sentinel state doubles as the banner input).

### B3 Migration waves

- **W0 (now):** Part A hardening. Prerequisite for everything — a live system
  built on an unobserved substrate inherits the blindness.
- **W-B1:** finish the ratified Phase 1 islands; every migrated island deletes
  its render-path twin (measured engine-minutes reclaimed per island — report
  in the PR body).
- **W-B2:** collectors decompose from the 1×3h `collect` monolith into
  per-source jobs on their own cadences (5–60 min, idempotent, R2-versioned).
  `config/dag.yml` is already the dependency spine — the change is trigger
  granularity, not topology.
- **W-B3:** signal services — the incremental recompute path for display-tier
  signals on data arrival (VPS or a small dedicated compute box), publishing
  to the same plane contract. The nightly re-derives the same signals as the
  authority checkpoint; divergence between the two is itself a monitored
  signal (free integrity check).
- **W-B4:** nightly is now grading + vintages + heavy backfills only. Retire
  the 240m caps; the cold-spare law becomes trivial to satisfy.

### B4 Infrastructure posture

Current fleet (M1 + Studio + 4 Linux render boxes + VPS + R2) is sufficient
through W-B2 once W4 lands. Decision points, deferred until measured need:
one dedicated compute VPS for signal services at W-B3 (sized after W-B2 tells
us the per-cadence compute cost); real-time quote upgrade per the Polygon
websocket seam doc. GitHub plan upgrades buy nothing for the failure modes we
actually had (public repo = free hosted minutes; the outage was GitHub's, not
a quota).

### B5 Falsifiers / kill criteria

- If W1's sentinel produces >2 false-positive pages in a month, the freshness
  budgets are wrong — fix budgets, don't mute the sentinel.
- If an island migration does NOT reduce engine minutes (twin not deleted),
  the migration is cargo cult — stop and audit before the next island.
- If the authority/display split ever requires the live plane to advance a
  forward ledger, Part B has drifted into violating the epistemics law — halt
  and re-adjudicate.

# VPS live orchestration

## Decision

Use a hybrid ownership model:

| Work | Primary owner | Recovery / reconciliation |
|---|---|---|
| Official publication detection | VPS, ~1 minute | Nightly source/vintage retrieval |
| Display quote snapshot | VPS, ~1 minute | Manual GitHub workflow |
| Live overlay / US risk state | VPS, staggered ~2 minutes | Manual GitHub workflow |
| China risk state | VPS, staggered ~2 minutes in HK window | Manual GitHub workflow |
| Full-universe quotes + US/HK basket pulse | VPS, ~5 minutes | Manual GitHub workflow |
| Intraday bars + flow pulse | VPS, hourly, low priority | Manual GitHub workflow |
| S&P 500 heatmap price splice | VPS, ~10 minutes in US window | Nightly static heatmap |
| Canonical daily source pulls and corrections | Mac/PC nightly | Rerun nightly |
| Regime-pointer stale repair | Mac light runner, once at 14:05 UTC after cutover | Manual dispatch |
| Forward ledgers, grading, calibration, research | Mac/PC nightly | Rerun nightly |
| Full engine and static-site render | Mac/PC nightly | Render workflow |
| Historical/bulk backfills and LLM-heavy jobs | Mac/PC | Explicit operator run |
| BTC/commodity state-transition sentinels (current canonical JSONL writers) | Mac/PC for now | Refactor to VPS sidecar before moving |
| White House/LLM sentinel and qledger registration | Mac/PC for now | Keep its single canonical writer |

One artifact has one scheduled writer. The old Actions workflows retain
`workflow_dispatch`, but their schedules are skipped only when the repository
variable `VPS_LIVE_PRIMARY=true` is set after the VPS soak.

The vector, commodity and White House sentinels are intentionally not lifted
unchanged: today they update canonical event/claim files and sometimes invoke an
LLM. Moving those processes verbatim would create a second ledger writer. Their
future VPS form should emit an ephemeral detection sidecar first; the nightly lane
can fold that sidecar into the canonical event/claim stream exactly once.

## Why the nightly pull stays

The VPS live plane is an ephemeral, fast view. It does not replace the nightly
canonical run because official series are revised, market closes are adjusted,
vendor snapshots can have bad prints, and the forward ledgers must be advanced
exactly once per session. Nightly therefore:

1. re-pulls canonical official/vendor sources;
2. captures revisions and final/adjusted closes;
3. reconciles the live sidecars;
4. advances ledgers and grades forecasts;
5. recomputes the full engine and site.

The first migration reduces live-runner queueing and commit/deploy churn. It does
not intentionally remove the nightly correctness pass. Later, collector-level
telemetry can justify skipping a redundant network fetch, but reconciliation and
ledger advancement still remain.

The old intraday workflow also carried a canonical regime-pointer self-heal.
Because that is not an ephemeral display artifact, it is not moved to the VPS.
After cutover, `regime-self-heal.yml` retains one daily pass on
`macstudio-light`; this replaces dozens of intraday opportunities with one
bounded reconciliation run while preserving single-writer ownership.

## Measured VPS capacity (2026-07-24)

Production was inspected before this design:

- 2 vCPU, 3.8 GiB RAM, about 2.7 GiB available;
- 77 GiB disk, about 38 GiB free;
- load average about 0.41 / 0.27 / 0.23;
- the existing five-minute risk build briefly used roughly 90–95% of both CPUs,
  then returned to idle;
- the risk-state market-driver pass took about nine seconds;
- `/opt/macro` and `/opt/terminal` already consume about 25 GiB combined.

Conclusion: the current 2-vCPU plan can run the live plane if jobs are serialized,
offset and resource-capped. It has low average load but little burst headroom. The
planned 4-vCPU tier is the preferred steady state and should be comfortable for
these short/network-heavy tasks. Bulk backfills, full renders and LLM-heavy work
stay off the VPS regardless of tier.

## Runtime layout

```
/opt/macro                         code + canonical checked-out inputs
/opt/macro/site/live               per-process staging only
/var/lib/macro-live/public/live    atomically published `/live/*` artifacts
/var/lib/macro-live/public/marketdata  live heatmap overlay
/var/lib/macro-live/state          locks, fingerprints, lane status, full quote cache
/var/lib/macro-live/data/intraday  mutable VPS-only hourly bars
```

Caddy serves external files from `/var/lib/macro-live/public` with `no-store`;
the sibling state/data directories are not web-addressable. Existence matchers
fall back to the last `/opt/macro/site.served` copy during installation or an
individual artifact cold start, so merging the route cannot create a live-data 404.
Only the reviewed `/live/quotes.json` snapshot is public. Other `/live/*` files
and the heatmap pass the existing registration and entitlement checks before
Caddy selects an external file; the live plane does not widen the static-access
boundary.
`/marketdata/sp500_heatmap.json` is the one exact legacy path overlaid from the
same live store. Everything else continues to come from `/opt/macro/site.served`.

## Lanes and resource controls

- `macro-live-fast.timer`: every ~60 seconds. Publication watcher runs first.
  Overlay and risk state alternate minutes instead of competing. Resource ceiling:
  180% CPU and 1.5 GiB memory.
- `macro-live-snapshot.timer`: every ~5 minutes. Full quote pull followed by both
  basket pulses on weekdays (the full equity universe does not poll all weekend).
  Lower priority, 90% CPU and 1 GiB memory.
- `macro-live-bars.timer`: hourly at `:37` during 13:00–21:00 UTC weekdays.
  Lowest priority, 90% CPU and 1.25 GiB memory.
- `macro-live-prophet.timer`: every ~5 minutes at `:03/5` during 13:00–21:59 UTC
  weekdays; the pass itself stands down outside 09:25–16:25 America/New_York on the
  Eastern clock (and on NYSE holidays) via `engine/prophet_live/live_states.in_window`,
  so one schedule covers both DST regimes. Lowest priority tier, 60% CPU and 512 MiB
  memory — measured 2026-07-30 at ~0.5 CPU-seconds and ~95 MB peak RSS per pass
  against a production-shaped 1,742-name pack and the real 2,025-symbol quote
  snapshot. It reads `state/quotes_full.json` and `public/live/quotes.json` off disk
  (no network for quotes), publishes the state map and event spool to R2, and writes
  `public/live/prophet_live.json` by atomic rename. That file is **gated**: it is not
  in the reviewed public `/live/*` list, so it passes registration + entitlement
  before Caddy serves it. Requires `R2_*` in `/etc/macro-live.env` and `boto3` in the
  venv; without them the pass reads the public mirror and publishes nothing.
  `.github/workflows/prophet-live.yml` is the self-disabling backstop for this lane.
  Stand-down without touching a unit: set `PROPHET_LIVE_NO_PUBLISH=1` in
  `/etc/macro-live.env` — the timer keeps ticking and nothing is written to R2 or to
  the served copy. `systemctl disable --now macro-live-prophet.timer` is the harder
  stop; note that a later commit which changes either unit file re-arms it.

Systemd will not start a second instance of an active oneshot service. The Python
lane locks also coalesce manual/timer overlap. Every browser artifact is JSON
validated and copied through a same-directory temporary file before `replace()`.

## Publication semantics

`scripts.watch_release_publications` polls official Fed, BLS, BEA and DOL endpoints
only inside a small window around a scheduled release. It publishes an ET-aware
event lifecycle (`scheduled`, `watching`, `awaiting_publication`, `published`,
`published_unparsed`, or `verification_delayed`) to
`live/release_publications.json` and preserves source health/fingerprints under
the external state directory.

The FOMC adapter resolves the deterministic official statement URL and extracts
the target range, action, vote and dissent preference without an LLM. Exact-date
official adapters also parse headline/core CPI, PPI, payrolls/unemployment,
GDP, headline/core PCE and initial claims. BLS uses the release-specific Atom
feeds; BEA uses an exact RSS item followed by its permanent release page; DOL
uses the exact dated claims entry in the ETA releases listing because the
per-release URL is a PDF. Every verified packet carries normalized metric IDs,
period, units, bilingual display copy and its official URL.

Ordinary publication sources use a six-hour fast polling window. FOMC uses a
24-hour fast window so a same-evening deploy or overnight process restart still
recovers the official statement. Conditional 304 responses are retried without
validators when a parser-backed event still lacks verified facts, and one shared
BEA RSS response fans out to independent GDP and PCE event IDs.
Every unresolved result family remains in lifecycle/heartbeat output for seven
days and an unparsed receipt is retried every 15 minutes. A parser miss is always
`published_unparsed`, never a green `published` row. It remains unhealthy and
retained until deterministic parsing recovers.

The browser selects Release Radar by date: every selectable event card on that
date shares the active state, and clicking GDP/PCE/claims in succession does not
fake-refresh an unchanged date panel. Simultaneous lifecycle rows render as
independent outcome cards while the hero, next-action card and Radar banner show
aggregate verified/extracting/awaiting counts.

The watcher publishes schedule coverage for every supported family. The external
dead-man fails when that coverage is incomplete, preventing a hard-coded annual
table from silently fabricating or omitting next-year release dates. Official
schedule synchronization is still a planned Phase 1 dependency; the alarm makes
the remaining maintenance requirement explicit and operationally visible.

This sidecar is public because it contains only official agency facts, provenance
and operational lifecycle—not proprietary signals, rankings, portfolios or user
data. Caddy serves it from the external live store with `Cache-Control: no-store`.
The nightly ALFRED/official retrieval remains the sole canonical vintage,
scoreboard and forward-ledger writer.

The public `/api/status` check reports lifecycle counts and publication lag. The
external heartbeat becomes unhealthy when a v2 event remains unverified for more
than two minutes after its scheduled time, when an official publication remains
`published_unparsed`, or when an event falls beyond its type-specific watch
window (six hours normally, 24 hours for FOMC). This prevents a
fresh-but-semantically-empty file from looking operationally healthy.

## Deployment and cutover

1. Merge and let `macro-update` install the new Caddy configuration.
2. On the VPS, run `bash /opt/macro/app/deploy/live-setup.sh`.
3. Add vendor keys to `/etc/macro-live.env` (mode `0600`).
4. Observe `/api/status`, `systemctl list-timers`, and lane journals for at least
   one full US session and one HK session.
5. Confirm `/live/orchestrator_status.json` is current and browser paths are
   served from the external store.
   `python scripts/check_vps_live_health.py` must also pass; after cutover the
   GitHub-hosted `vps-live-heartbeat` workflow runs this dead-man every ten minutes.
6. Set repository variable `VPS_LIVE_PRIMARY=true`.
7. Keep the old workflows available for manual recovery. If the VPS goes stale,
   set the variable false before dispatching or simply use manual dispatch, which
   is always allowed by the workflow guards.

The installer does not remove the legacy VPS cron writer until the fast lane
passes its smoke test and all replacement timers are enabled. To roll back the
VPS itself, run:

```bash
sudo bash /opt/macro/app/deploy/live-rollback.sh
```

The rollback disables the three timers, restores the legacy five-minute cron
entry if needed, and moves the external public tree to a timestamped backup.
Caddy then falls back to the last `site.served` artifacts immediately. Private
state and data are retained for diagnosis. Set `VPS_LIVE_PRIMARY=false` (or delete
the variable) as a separate control-plane step to resume scheduled Actions jobs.

Do not run both scheduled writers after cutover. A dead-man failover may be added,
but it must first check VPS freshness and acquire ownership before writing.

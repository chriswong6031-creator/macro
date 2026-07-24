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
`/marketdata/sp500_heatmap.json` is the one exact legacy path overlaid from the
same live store. Everything else continues to come from `/opt/macro/site.served`.

## Lanes and resource controls

- `macro-live-fast.timer`: every ~60 seconds. Publication watcher runs first.
  Overlay and risk state alternate minutes instead of competing. Resource ceiling:
  180% CPU and 1.5 GiB memory.
- `macro-live-snapshot.timer`: every ~5 minutes. Full quote pull followed by both
  basket pulses. Lower priority, 90% CPU and 1 GiB memory.
- `macro-live-bars.timer`: hourly at `:37` during 13:00–21:00 UTC weekdays.
  Lowest priority, 90% CPU and 1.25 GiB memory.

Systemd will not start a second instance of an active oneshot service. The Python
lane locks also coalesce manual/timer overlap. Every browser artifact is JSON
validated and copied through a same-directory temporary file before `replace()`.

## Publication semantics

`scripts.watch_release_publications` polls official BLS, BEA and DOL endpoints only
inside a small window around a scheduled release. It publishes detection metadata
to `live/release_publications.json` and preserves source health/fingerprints under
the external state directory.

The sidecar is display-only and explicitly reports `data_ready=false`: detection
does not fabricate or score an actual value. When a direct live-data entitlement
arrives, its adapter can attach parsed values to this sidecar. The nightly
ALFRED/official retrieval remains the only canonical actual/scoreboard writer.

## Deployment and cutover

1. Merge and let `macro-update` install the new Caddy configuration.
2. On the VPS, run `bash /opt/macro/app/deploy/live-setup.sh`.
3. Add vendor keys to `/etc/macro-live.env` (mode `0600`).
4. Observe `/api/status`, `systemctl list-timers`, and lane journals for at least
   one full US session and one HK session.
5. Confirm `/live/orchestrator_status.json` is current and browser paths are
   served from the external store.
6. Set repository variable `VPS_LIVE_PRIMARY=true`.
7. Keep the old workflows available for manual recovery. If the VPS goes stale,
   set the variable false before dispatching or simply use manual dispatch, which
   is always allowed by the workflow guards.

Do not run both scheduled writers after cutover. A dead-man failover may be added,
but it must first check VPS freshness and acquire ownership before writing.

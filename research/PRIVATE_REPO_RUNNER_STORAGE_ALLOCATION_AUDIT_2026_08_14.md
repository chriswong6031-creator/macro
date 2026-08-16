# Private repo + runner fleet + storage allocation audit

**Assessment date:** 2026-08-14 (live refresh through 2026-08-15 02:54Z)

**Repository:** `mastermindx-market-intelligence/macro`

**Status:** READ-FIRST COMPLETE — no repository visibility, runner routing, service,
filesystem, or hardware change was made by this audit.

This report supersedes the physical-runner mapping in
`research/NIGHTLY_COMPUTE_ALLOCATION_AUDIT_2026_08_13.md`. That audit inferred host
identity from names. Direct `.runner` metadata and hardware inspection now prove that
`mac-builder-1` and `mac-builder-2` belong to the M1 Max Studio, while the current
`mac-builder-3` registration belongs to the M2 Ultra Studio. The M1 still has an old
local `mac-builder-3` configuration, but that registration no longer exists in GitHub.

## A. Executive verdict

1. **Keep the repository public for now.** At the measured six-day rate, making it
   private before moving CI would expose approximately **$15,294–$15,594/month** of
   GitHub-hosted Linux runner charges, depending on how much of the organization’s
   50,000-minute Enterprise allowance remains available.
2. **CI is the bill.** The repository used **519,805 hosted Linux minutes** from
   August 9–14. Sampling attributes roughly 95–98% to `ci.yml`; artifact/cache storage
   was only 32.98 GB-hours and is economically immaterial beside compute.
3. **The owned PC is the first CI target.** Its 24 CPU cores, four healthy Linux
   runners, and 884 GiB of free WSL storage are enough for a staged three-pack CI
   canary while reserving one slot for render. Do not add runners until WSL’s current
   ~32 GiB memory ceiling is raised and measured.
4. **The M1 is not quietly underused; its runner fleet is dead.** Three configured
   services have no listener process. Runner logs prove an August 13 `No space left on
   device` crash, and the services did not recover after space returned.
5. **The M2 really carries production.** It currently runs `daily.collect`,
   `daily.engine`, Technical Lab, Asia close, closing bell, the default render, merge
   control, and the `macstudio-light` live lanes. Those 75–180 minute jobs explain the
   nighttime fan ramp.
6. **Nightly is not the M2 storage leak.** All four M2 runner installations total
   about **25.1 GiB**. Agent worktrees total about **604 GiB**, including 119 physical
   `.claude` worktrees born on August 14. That is the dominant infrastructure footprint
   and the monotonic-growth mechanism.
7. **Protect the M2.** Its target role should be interactive/control/high-memory and
   break-glass production, not routine CI, render, nightly, and disposable checkout
   storage simultaneously.
8. **Use the existing drives before buying.** One 1 TB T7 has ~394 GB free but is
   ExFAT and holds a personal archive; the other T7 has ~559 GB free, fast HFS+
   small-file performance, and a production Theta/data role. The 512 GB drive was not
   attached. Reallocate and format deliberately; do not commandeer durable data disks.
9. **Private migration must be a sequence, not a visibility toggle.** Repair M1,
   isolate PC CI, prove render/nightly canaries, provision private Git authentication
   for the VPS deploy path, make Pages visibility explicit, then change visibility.
10. **Hardware verdict: `BUY NOTHING`.** Existing compute and raw external capacity
    are sufficient. The binding failures are routing, service recovery, WSL allocation,
    filesystem choice, and workspace lifecycle.

## B. Physical fleet map

### B.1 Proven machine identity

| Physical machine | Direct evidence | Available resources observed | Current role |
|---|---|---|---|
| M2 Ultra Mac Studio | `system_profiler`: Mac Studio `Mac14,14`, Apple M2 Ultra, 24 cores, 192 GB, macOS 26.5; host `Mac-Studio.ts.net` | 2 TB internal; only ~232–255 GiB free during the census | Operator workstation plus four active runner processes; most macOS production |
| M1 Max Mac Studio | SSH `m1`; `system_profiler`: Mac Studio `Mac13,1`, Apple M1 Max, 10 cores, 32 GB, macOS 15.6.1 | ~168 GiB internal free after the incident; external T7 `/Volumes/STORAGE` ~559 GB free | Three configured but dead runner services; Theta/durable data host |
| Intel PC | SSH `winpc-wsl`; Intel Core Ultra 9 285K, 24 logical CPUs, Linux WSL2 | WSL currently exposes ~31 GiB RAM; ext4 has ~884 GB free; D: ~1.8 TB free; C: ~359 GB free | Four active Linux runner processes, presently `render-linux` |

Names are not identity. The proof chain was GitHub runner ID → local `.runner`
`agentName`/`workFolder` → service definition → listener PID → hardware inventory on
that host.

### B.2 Runner census

Status is the live GitHub registry at 2026-08-15 02:54Z. “Recent job” is supported by
the Actions jobs API or the nightly timing ledger, not inferred from a label.

| Runner | Physical machine | OS | Routing labels | Runner dir → work dir | Online / busy | Recent jobs | Intended/current role |
|---|---|---|---|---|---|---|---|
| `mac-builder-1` (id 25) | M1 Max | macOS ARM64 | `macstudio,codex,theta-m1` | `~/actions-runner-1` → `_work` | offline / no | collect, capital structure, engine and nightly tails through Aug 13 | M1 nightly/host-private slot; repair |
| `mac-builder-2` (id 26) | M1 Max | macOS ARM64 | `macstudio,codex,theta-m1` | `~/actions-runner-2` → `_work` | offline / no | collect, factor series, collect-tail and engine through Aug 13 | M1 nightly/host-private slot; repair |
| `mac-builder-3` (old local id 27) | M1 Max | macOS ARM64 | local stale config | `~/actions-runner-3` → `_work` | **not registered / no** | historical government-revenue/nightly work | Stale local identity; must be renamed if re-registered |
| `mac-builder-light` (id 28) | M2 Ultra | macOS ARM64 | `render-heavy` | `~/actions-runner-4` → `_work` | online / busy | `render` (95.2m on latest completed run) | Default full render |
| `mac-builder-4` (id 29) | M2 Ultra | macOS ARM64 | `parked,merge-control` | `~/actions-runner` → `_work` | online / idle | `merge-on-green` sweep, 0.75m latest | Merge control |
| `mac-builder-5` (id 30) | M2 Ultra | macOS ARM64 | `macstudio,parked` | `~/actions-runner-2` → `_work` | online / idle | collect, engine, Asia close, closing bell, Technical Lab | Main M2 nightly slot; `parked` does not prevent routing |
| `mac-builder-3` (id 35) | M2 Ultra | macOS ARM64 | `macstudio-light` | `~/actions-runner-3` → `_work` | online / idle | research ingest, government-revenue-live, marketing publish | Frequent light/live macOS lanes |
| `pc-render-1` (id 31) | PC/WSL | Linux x64 | `render-linux` | `/home/longr/actions-runner` → `_work` | online / busy | `engine-render` | Linux render/compute |
| `pc-render-2` (id 32) | PC/WSL | Linux x64 | `render-linux` | `/home/longr/actions-runner-2` → `_work` | online / idle | recent `engine-render` | Linux render/compute |
| `pc-render-3` (id 33) | PC/WSL | Linux x64 | `render-linux` | `/home/longr/actions-runner-3` → `_work` | online / idle | recent `engine-render` | Linux render/compute |
| `pc-render-4` (id 34) | PC/WSL | Linux x64 | `render-linux` | `/home/longr/actions-runner-4` → `_work` | online / idle | render-pool reserve | Linux render/compute |

### B.3 Service and workspace findings

- **M2:** four listener processes and four LaunchAgents. All are `RunAtLoad=true` and
  were loaded. Each installation has a distinct runner root and `_work`; there is no
  shared workspace. All use runner version 2.336.0.
- **M1:** three `.runner` configurations and three `RunAtLoad=true` LaunchAgents, but
  zero listener processes. Service stdout repeats
  `System.IO.IOException: No space left on device` while opening `_diag` logs on
  August 13. The disk later recovered to ~168 GiB free, but `RunAtLoad` without a
  crash-restart policy left the fleet dead. The local third identity collides by name
  with the newer M2 registration and no longer exists in GitHub.
- **PC:** four distinct roots and `_work` directories; four listener processes; four
  systemd units are active and enabled across reboot. WSL shows only ~31 GiB available
  RAM despite 64 GB physical RAM. Four concurrent jobs is the proven ceiling today;
  more is a hypothesis, not capacity.
- **Label drift:** `parked` is documentary, not a negative constraint;
  `mac-builder-5` still matches every `[self-hosted,macstudio]` job. `macstudio` spans
  physical generations when the M1 is healthy. `mac-builder-*` therefore cannot be
  used as an allocation or incident boundary.

## C. GitHub-hosted spend exposure

### C.1 Current rules, verified from GitHub

- Public repositories can use standard GitHub-hosted runners without metered compute
  charges. Private repositories consume the account’s included Actions allowance and
  then incur metered overage. GitHub Enterprise Cloud includes **50,000 standard
  runner minutes/month and 50 GB of Actions artifact storage**. See GitHub’s
  [included usage table](https://docs.github.com/en/enterprise-cloud@latest/billing/reference/product-usage-included)
  and [Actions billing model](https://docs.github.com/en/enterprise-cloud@latest/billing/concepts/product-billing/github-actions).
- The current Linux 2-core standard-runner rate is **$0.006/minute**; jobs are rounded
  up to the next whole minute. See
  [Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing).
- Self-hosted Actions compute is not metered by GitHub; the operator pays for the
  machine, electricity, storage, maintenance, and isolation. See
  [self-hosted runners](https://docs.github.com/en/enterprise-cloud@latest/actions/concepts/runners/self-hosted-runners).
- Artifact storage is metered in GB-hours after included storage. Caches are repository
  scoped and have a default 10 GB repository limit; current repository cache inventory
  is 322 entries / 10.78 GB and organization inventory is 522 / 26.89 GB. This is a
  retention concern, but it is not the current cost driver.
- Enterprise-hosted concurrency is 500 total jobs and 50 macOS jobs. Self-hosted limits
  include 1,500 registrations per five minutes, 10,000 runners per group, a five-day
  job execution limit, and a 24-hour queue limit. None is a near-term fleet limit; the
  local four-slot PC and service reliability bind first. See
  [Actions limits](https://docs.github.com/en/actions/reference/limits).
- The repository’s Pages configuration is a workflow-built mirror at
  `https://mastermindx-market-intelligence.github.io/macro/`, sourced from `main`, with
  no CNAME. Enterprise Cloud supports Pages from private repositories, but site
  visibility must be selected explicitly and can differ by enterprise policy. The
  primary `mastermind-x.com` VPS/EdgeOne path must also receive private-repository Git
  authentication before the visibility flip. See GitHub’s
  [Pages visibility documentation](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site).

### C.2 Measured usage and private projection

The organization billing API begins this repository’s ledger on August 9, after its
organization transfer. July contains no `macro` usage record, and the former user
billing endpoint is not available to this account. Therefore a genuine 30-day billed
history is **not recoverable** from the current billing ledger. The projection below is
an explicitly linear six-day run-rate, not a fictional 30-day observation.

The repository Actions endpoint does preserve run counts: **19,841 runs over the last
seven complete UTC days** (August 8–14) and **42,136 over 30 complete days** (July
16–August 14). Run count is not billable minutes—matrix size and runtime vary sharply—so
the older count is reported as activity context, not multiplied by a made-up average.
For the exact six billing days, the repository endpoint reports 17,797 runs including
GitHub-generated workflows; the 86 checked-in workflow files account for 17,725.

| UTC day | Hosted Linux minutes | Public gross value | Public net charge |
|---|---:|---:|---:|
| Aug 9 | 11,888 | $71.33 | $0.00 |
| Aug 10 | 46,698 | $280.19 | $0.00 |
| Aug 11 | 130,478 | $782.87 | $0.00 |
| Aug 12 | 131,121 | $786.73 | $0.00 |
| Aug 13 | 76,429 | $458.57 | $0.00 |
| Aug 14 | 123,191 | $739.15 | $0.00 |
| **Six reported days** | **519,805** | **$3,118.83** | **$0.00** |

The checked-in workflow files produced 17,725 runs over those same six days. Linear
projection from the authoritative billed-minute ledger:

```text
519,805 / 6 * 30 = 2,599,025 Linux minutes/month
full Enterprise allowance available: (2,599,025 - 50,000) * $0.006 = $15,294.15
allowance consumed elsewhere:          2,599,025            * $0.006 = $15,594.15
```

This range excludes taxes and future churn, and assumes Linux standard runners at the
current rate. It is the appropriate order-of-magnitude exposure for the visibility
decision. At the 02:54Z audit snapshot, the next billing-ledger item already recorded
15,419 minutes for August 15, so the high run-rate had not stopped at the boundary.

### C.3 Cost-driver decomposition

| Workflow | Six-day runs | Current compute | Runtime evidence | Spend importance |
|---|---:|---|---|---|
| `merge-on-green` | 7,371 | M2 self-hosted | short sweeps | no hosted compute charge |
| `fences` | 3,219 | hosted Linux | sampled mean 5.5 billed job-min/run equivalent; median run wall 4.18m | tail |
| `ci` | 3,195 | hosted Linux | sampled 60 runs: mean ~159 billed job-min/run, median 239.5, p95 355; 8.4 hosted jobs/run mean | **~508k sampled-estimate minutes; dominant** |
| `integration-baseline` | 536 | hosted Linux | median wall 1.29m, p95 19.98m | small |
| `earnings-public-wire` | 277 | hosted Linux | median wall 7.62m, p95 28.95m | small |
| remaining hosted workflows | long tail | hosted Linux | individually low volume or short | small in aggregate |

The CI sample estimate is within ~2.2% of the exact six-day organization billing total,
even before other hosted lanes are added. It is sampling, not an allocation ledger, so
the correct conclusion is **roughly 95–98% CI**, not a fake exact percentage. Moving one
nightly job does not solve private Actions cost; moving trusted CI packs does.

## D. Nightly/render and workflow-routing map

### D.1 Complete routing census

A parser census of all **86 active local `.github/workflows/*.yml` files** found 126
declared jobs. Reusable-workflow indirection and conditional jobs are counted as source
declarations; a workflow can appear in more than one class.

| Current runner class | Job declarations | Workflow files | Physical resolution now |
|---|---:|---:|---|
| GitHub-hosted (`ubuntu-latest`) | 54 | 35 | GitHub |
| `[self-hosted,macstudio]` | 49 | 33 | M2 `mac-builder-5` only while M1 is dead |
| `[self-hosted,macstudio-light]` | 17 | 17 | M2 `mac-builder-3` |
| `render-heavy` | 1 | 1 | M2 `mac-builder-light` |
| `merge-control` | 1 | 1 | M2 `mac-builder-4` |
| `codex` | 1 | 1 | no eligible live runner (`mac-builder-1/2` offline) |
| `theta-m1` | 1 | 1 | no eligible live runner (`mac-builder-1/2` offline) |
| `render-linux` | 1 | 1 | PC pool |
| reusable `daily` government-revenue job | 1 | 1 | resolves through `macstudio-light` |

Hosted workflow files: `btc-live`, `buffer-channels`, `ci-main-heartbeat`, `ci`,
`closing-bell`, `company-intelligence`, `cycle-calibration`,
`daily-engine-setup-retry`, `daily`, `deploy-analytics`, `earnings-evidence-graph`,
`earnings-public-wire`, `earnings-story-packets`, `earnings-story-press-stage`,
`fences`, `geo-enrich`, `integration-baseline`, `live-quotes`,
`marketing-copy-dryrun`, `marketing-earnings-wire`, `marketing-hot-tape`,
`marketing-media-backfill`, `marketing-press-wire`, `marketing-x-intel`,
`metabolism-immune`, `nightly-backstop`, `nightly-liveness`, `pages`,
`press-publish`, `prophet-live`, `prophet-rescue`, `public-render`,
`research-triage`, `vps-live-heartbeat`, and `weekly`.

`macstudio` workflow files: `asia-close`, `backfill`, `brain-eval`, `close-pass`,
`closing-bell`, `cortex-retry`, `daily`, `earlyclose`, `edgar_flow_ops`, `factor_ops`,
`heartbeat`, `intl_etf`, `key-pool-probe` (default; hosted is a manual option),
`metabolism-adjudicate`, `metabolism-agenda`, `metabolism-audit`, `metabolism-build`,
`metabolism-cycle`, `metabolism-dream`, `metabolism-gc`, `metabolism-heartbeat`,
`metabolism-merge`, `metabolism-propose`, `metabolism-verify`, `seo-director`,
`signal-foundry`, `smart-money-13f-bulk-reconcile`, `smart-money-13f-census`,
`smart-money-filings`, `special-sits-backfill`, `tushare-spine-backfill`,
`validate-leading-legs`, and `weekly`.

`macstudio-light` workflow files: `attested-history-aapl-seed`,
`attested-history-operator`, `capital-share-count-r2-concurrency`,
`capital-share-count-r2-conformance`, `commodity-sentinel`, `deploy-api-secrets`,
`filing-forensics-sec`, `government-revenue-live`, `intraday-fastpath`, `intraday`,
`live-breadth`, `marketing-publish`, `regime-self-heal`, `research-ingest`, `sentinel`,
`smart-money-13f-r2-conformance`, and `whitehouse-sentinel`.

The remaining singleton classes are `render.yml` (`render-heavy` default, with manual
`macstudio`/`render-linux` options), `merge-on-green.yml` (`merge-control`),
`codex-research.yml` (`codex`), `daily.yml` collect-tail (`theta-m1`), and
`engine-render.yml` (`render-linux` default, manual alternate label accepted). GitHub
also displays generated Dependency Graph/CodeQL entries that are not additional local
workflow files.

### D.2 Major-workflow decision table

Wall runtime includes queue/cancellation time where only run timestamps were available;
it is labeled separately from billed job-minutes.

| Workflow | Trigger / typical jobs | Median / p95 recent wall | Current physical host | macOS or host-private need | Linux migration | Risk |
|---|---|---:|---|---|---|---|
| `ci.yml` | PR + manual; plan, matrix packs, gate; mean 8.4 hosted jobs/run in sample | 20.43m / 47.58m | GitHub Linux | No macOS requirement: it already passes/fails on Ubuntu. Some packs may touch protected fixtures/secrets and must be classified before persistent self-hosting. | Yes, strongest PC candidate | Medium: persistent runner and untrusted-PR isolation |
| `fences.yml` | PR; four hosted jobs | 4.18m / 10.13m | GitHub Linux | No macOS; deliberately short control gates | Yes, but savings small | Low technically; keep hosted first for independent fail-open control |
| `daily.yml` | 22:30Z + 23:30Z DST pair + manual; ~19 major jobs plus many steps/tails | daily run wall 32.41m median / 440.47m p95 distorted by queue/cancels; critical collect/engine below | mostly M2; M1-specific tail now queues | Host-private Theta/data and many secrets; not one portable unit | Split only after per-job canaries | High |
| `render.yml` | push/coalesced + manual; one heavy render | latest successes 95.2–118.5m | M2 `mac-builder-light` | No proven macOS-only dependency; workflow already accepts a runner input | PC same-SHA canary first | Medium-high: published tree parity |
| `engine-render.yml` | push/coalesced + manual; fence/capability jobs + engine render | recent successful render jobs 96.1–122.2m | PC `pc-render-*` | Proven Linux | Already correctly placed | Low |
| `closing-bell.yml` | 20:05/21:05Z weekdays; production job + hosted publish | recent M2 job ~109.4m | M2 `mac-builder-5` | Secrets/data publication; macOS not proven necessary | Possible after non-publishing Linux canary | High |
| `asia-close.yml` | 06:00–11:15Z seven backstops; gated production chain | timing ledger median 81.9m / p95 83.2m; latest ~89.7m | M2 `mac-builder-5`; M1 handled earlier nights | Data/secrets and publication; no proven macOS binary need | M1 first, PC only after parity | High |
| `pages.yml` | workflow/manual deployment | short hosted deployment control | GitHub Linux | GitHub Pages credentials/environment | Keep hosted | Low cost, high deployment significance |
| `merge-on-green.yml` | workflow events + every 10m; one sweep | latest 0.75m; 7,371 six-day runs | M2 `mac-builder-4` | GitHub API credentials; no heavy compute | Could be hosted or isolated control, but not a cost lever | Medium authority, low compute |
| backfills / scheduled macOS families | manual or periodic; usually one job | heterogeneous | M2 through `macstudio`/`macstudio-light` | Frequently secrets, local stores, or production writes | Classify individually | Medium-high |

### D.3 What actually happens at night

| Work | Recent measured runtime | Physical assignment proved | Approximate window / burden |
|---|---:|---|---|
| `daily.collect` | timing median **152.1m**, p95 180m; latest full 162.6m | M2 `mac-builder-5` on latest; historical M1 `builder-1/2` | starts after the 22:30/23:30Z gate; mostly network collection |
| `daily.collect_tail` | median **101.4m**, p95 109.5m | only M1 `builder-1/2` through Aug 13; now no eligible live `theta-m1` | overlaps/continues after collect; currently outage-prone |
| `daily.engine` | median **155.7m**, p95 189.7m; latest full 136m | latest M2 `builder-5`; earlier M1 `builder-1/2` | follows collect; mixed restore, compute, build, publish |
| Technical Lab | median **75.2m**, p95 78.7m | M2 `builder-5` latest and most recent nights | post-engine tail |
| other daily tails | active-map 1.6m; capital 20.8m; factor-series 6.0m; oracle 10.6m; standout 23.4m; scan 9.1m | mixture of M2 `builder-5` and M1 `builder-1/2` before outage; current failover concentrates on M2 | parallel tails after gates |
| default `render` | recent **95.2, 104.5, 118.5m** successes | M2 `mac-builder-light` | push-triggered; can overlap nightly |
| `engine-render` | recent **96.1–122.2m** successes | PC `pc-render-1/2/3` | push-triggered Linux compute |
| Asia close | median **81.9m**, latest ~89.7m | latest M2 `builder-5`; M1 `builder-1` on Aug 12 | scheduled 06:00–11:15Z backstop series |
| closing bell | latest heavy execution ~**109.4m** | M2 `builder-5` | 20:05/21:05Z weekdays |

**Fan verdict:** yes, the operator hears real workload. Long collect, engine, Technical
Lab, Asia, closing-bell and render jobs can overlap across the M2’s separate runner
processes. The earlier audit was correct that collectors are often network-bound, so
fan noise is not proof that every minute is CPU-saturated; render/build tails still
create sustained compute and filesystem activity.

**Storage verdict:** no, nightly does not explain the 604 GiB checkout footprint. M2
runner roots are ~25.1 GiB total. Worktree creation—119 new `.claude` roots on August
14 alone—is the order-of-magnitude larger growth source.

**M1 verdict:** it is genuinely idle now: zero listener processes and three failed
services, not an online pool waiting without assignments. It did receive collect,
engine and tail work until the ENOSPC failure.

## E. Storage root cause

### E.1 Measured M2 infrastructure footprint

The internal data volume was ~88% used with ~232–255 GiB free during the census.
Personal browser environments and iCloud copies are intentionally separated from the
infrastructure decision.

| Path/class | Size / count | Owner or writer | Grows nightly? | Safety / regeneration |
|---|---:|---|---|---|
| Macro `.claude/worktrees` | **494.8 GiB**, 190 physical dirs; 119 born Aug 14 | Claude/agent sessions | No: grows per session, including overnight agents | Potentially reclaimable only with liveness + dirty + unique-commit + PR proofs; full regeneration is a checkout, unique work is not regenerable |
| Macro `.codex/worktrees` | **60.4 GiB**, 18 dirs | Codex sessions | per session | Same proof gate; never age-only delete |
| Macro `.codex-worktrees` | **39.9 GiB**, 19 dirs | legacy Codex sessions | per session | Same proof gate |
| `~/.codex/worktrees` | **9.0 GiB**, 22 dirs/husks, four full registered | Codex sessions | per session | Same proof gate; metadata husks separately classified |
| **All above worktree roots** | **~604 GiB** | agent fleet | **primary monotonic source** | Sparse-by-default and proof-bound GC, not bulk removal |
| shared Macro Git object store | **~41.7 GiB**: 1.58 GiB loose + 40.09 GiB in 9,407 packs | all worktrees/Git operations | grows with fetch/commits | Weekly maintenance only with no active writers; current `garbage: 0` means no blind purge |
| M2 runner installations | **~25.1 GiB** total | four Actions runners | active jobs change `_work`/`_temp` nightly | Do not remove active state; checkouts and temp regenerable only between drained jobs |
| `actions-runner-3/_work` | ~9.27 GiB (`macro` ~8.84 GiB) | M2 light runner | yes | reusable checkout; bounded cleanup after drain |
| `actions-runner-4/_work` | ~10.08 GiB (`macro` ~7.35 GiB; `_temp` ~2.36 GiB) | M2 render runner | yes | active render temp at census; never delete by mtime while job active |
| M2 runner `_diag` | largest observed ~691 MiB in one root | runner services | yes | compress/rotate after incident window |
| `~/Library/Caches` | **56.7 GiB**, ~2.21m files | apps/tooling | not primarily nightly | GoLogin alone ~47.3 GiB: explicitly preserve; other caches can use per-tool quotas |
| `~/.cache` | **3.0 GiB** | Codex runtimes + runner venvs | occasional | ~1.4 GiB of `mm-venv` environments are workflow dependencies; not generic trash |
| `~/Library/Developer` | **14.1 GiB**; CoreSimulator 8.4, Xcode 5.7 | Apple dev tooling | no evidence of nightly growth | not root cause; preserve unless separately audited |
| `~/.codex` sessions | sessions **39.5 GiB**, archived 5.36 GiB, SQLite/log DB 1.99 GiB | Codex | per interaction | archive/compress by lifecycle; preserve handoff/final/recovery evidence |
| `~/mlx` | **38.0 GiB**, ~1.38m files | ML tooling/data | unproven | inventory by owner before policy; not nightly runner proof |
| `~/macro-live` | **14.3 GiB** | live clone/runtime | production activity | preserve; separate deploy lifecycle |

Other large home consumers are not the runner remedy: `~/Library/Containers` is
~139.8 GiB (WeChat ~138 GiB) and Application Support contains large AdsPower/Google/
GoLogin state. Mobile Documents/iCloud is already under a separate operator cleanup.
No standalone `node_modules`, Actions tool-cache, Xcode DerivedData, or temporary
render root was large enough to alter the ranking; copies nested inside worktrees and
runner roots are already included in those parent totals.

### E.2 Why the worktrees dominate

- The Macro root totals ~648 GiB, almost fully explained by ~604 GiB session worktrees
  plus ~41.7 GiB of shared Git objects.
- A full checkout is currently ~4.2 GiB. The repository’s shipped sparse profile is
  ~0.35–0.57 GiB. More than 100 full worktrees persist and many current births still
  bypass or predate the sparse path.
- There are 287 registered worktrees repo-wide: 104 full and 85 sparse under
  `.claude`, plus full/legacy populations in the Codex and other roots.
- The August 14 `.claude` births alone imply roughly 500 GiB/day if allowed to remain
  full. No sensible disk purchase outruns an unbounded creation rate.
- PC runner roots total ~67 GiB but sit on a filesystem with ~884 GB free. M1 runner
  roots total only ~4 GiB. This reinforces that the pressure is M2 session churn, not
  an inherent requirement of Actions.

## F. Existing-drive verdict

Benchmarks were bounded, non-destructive 512 MiB tests. Their temporary files were
removed and absence verified. Results are a current-load snapshot, not an endurance
or thermal soak.

| Drive | Identity / connection / filesystem | Capacity state | Bounded benchmark | Role verdict |
|---|---|---|---|---|
| 1 TB SSD #1 on M2 | Samsung Portable SSD T7, serial ending `B07728J`; USB 10 Gb/s; SMART verified at device; TRIM not exposed over the USB bridge; MBR/ExFAT, 128 KiB allocation blocks; `/Volumes/Worktrees` | ~605.8 GB used / 394.3 GB free; actually holds ~559 GiB of personal archive, not current scratch | seq write 140.6 MB/s, read 692.8; 4K random read 2,867 IOPS, write 1,923; create 495 small files/s | Adequate for large disposable artifacts/temp **after** archive disposition. ExFAT is poor for Git/runner semantics and small-file work; reformat/partition APFS before worktrees. Not durable source of truth as-is. |
| 1 TB SSD #2 on M1 | Samsung Portable SSD T7, serial ending `A02592E`; USB 10 Gb/s; case-sensitive journaled HFS+; `/Volumes/STORAGE`; device reports verified, while `diskutil` SMART/TRIM are not exposed through the bridge | ~559.2 GB free; ~200 GiB visible durable Theta/production data | seq write 335.4 MB/s, read 884.7; random read 24,091 IOPS, write 3,249; create 13,716 small files/s | Technically strong for workspaces, but already a durable data plane. Keep Theta/durable data isolated; use only a separate quota/volume with backup and explicit ownership. |
| 512 GB SSD | not attached to M2 or reachable M1 | unknown | **not benchmarked** | Best candidate for dedicated M1 runner scratch, but only after attachment, identity/health check, APFS formatting decision, and benchmark. No capacity claim until then. |

An additional 5 TB “Game Drive” was attached to the M2 with ~442 GB free, but it is
not one of the declared SSDs and was not proven solid-state. It is excluded from the
SSD capacity claim.

**Can the nominal 2.5 TB solve the immediate problem?** Yes in raw capacity, but not
by simply pointing Git at whatever is mounted. One T7 is occupied and formatted
poorly for small-file work, one is a production data disk, and 512 GB is unverified.
The immediate solution is: stop unbounded full-checkout creation, safely harvest
completed trees, then commission one APFS scratch volume with a quota. Storage without
lifecycle would only defer the next full disk.

## G. Recommended target architecture

### G.1 Machine assignment

| Node | Target assignment | Explicitly not assigned |
|---|---|---|
| **M2 Ultra** | Interactive/executive work, high-memory specialist jobs, merge/control plane, one documented break-glass macOS production slot | Routine CI, default render, default nightly, or unbounded full worktrees on internal SSD |
| **M1 Max** | Primary macOS/host-private nightly worker; Theta-dependent collect-tail; network-bound collect; selected macOS live lanes; two heavy slots plus one light/control slot after repair | Three concurrent long CPU-heavy jobs; disposable state on the Theta durable volume |
| **PC** | Trusted Linux CI packs, generic builds, existing engine-render, later same-SHA render and Linux-compatible nightly tails | Untrusted fork PR code on a persistent runner; more than four concurrent jobs until RAM allocation and contention are measured |
| **External SSD scratch** | APFS runner `_work`, session worktrees, build/temp/cache under quotas | Sole copy of durable Theta/data, dirty worktrees, or recovery state |

### G.2 CI

Move the expensive `ci-pack` matrix to the PC **after** the private-repo preparation
and a trusted-branch canary. CI already runs on Linux, so platform compatibility is
proven. The meaningful risk is security and persistence: a self-hosted runner executes
repository code on a long-lived machine. Scope the runner group to this repository,
use a dedicated low-privilege OS user, exclude public forks/untrusted actors, issue
per-job credentials, and clean the disposable workspace after each job.

Keep `ci-plan`, `ci-gate`, and `fences` hosted initially. They are short, provide an
independent control path during fleet outages, and are not the cost center. Retain a
manual hosted fallback for CI packs.

**PC concurrency:** begin with **three CI slots and one render-reserved slot** using the
four proven runner processes. Do not run more than four yet: WSL exposes ~31 GiB RAM.
Before expansion, raise the WSL cap toward physical 64 GB, reserve at least 8 CPU cores
and 16 GB for Windows/GPU/host stability, and measure per-pack RSS/CPU/I/O. A later cap
of roughly six workers is plausible, not approved; evidence must decide it.

### G.3 Nightly

Do not move `daily.yml` as a monolith. Its network-bound collector gains reliability
from a dedicated always-on host, not from M2 silicon. Restore M1 service first, then:

- keep Theta/host-private `collect_tail` on M1;
- canary network-bound `collect` on M1, where it historically ran;
- keep secrets and mounted stores explicit per job;
- canary Linux-proven compute tails on PC one at a time;
- retain the M2 label as break-glass fallback until seven clean nights prove each move.

Do not place every tail on M1. Two heavy + one light slot is the safe initial envelope
for a 10-core/32 GB machine. Serialize durable publication and Git pushes exactly as
the current workflow contracts require.

### G.4 Render

`engine-render` already proves the PC can execute the Linux render engine, but its
96–122m runtime is not a same-workload comparison with the default 95–118m `render`.
Run `render.yml` on the existing manual `render-linux` input against the **same SHA**,
with publication disabled. Accept only if the output manifest/hash parity passes and
p95 wall time is no worse than 1.25× M2 over at least five representative renders.
Then make PC default and retain M2 manual fallback. M1 is a worse first render target:
it has 32 GB, hosts private nightly state, and would create a new contention domain.

### G.5 Storage lifecycle

The lifecycle is stateful and fail-closed:

```text
task starts → sparse workspace created → work executes → PR/handoff/HEAD receipt lands
→ liveness + content proofs classify it → disposable checkout is removed
→ audit ledger remains
```

| Class | Policy | Retention / quota | Proof required before removal |
|---|---|---|---|
| Completed clean worktree | sparse by default; harvest continuously | eligible 48h after merged or remote-represented proof; daily cap 200 | no lock, no process CWD, clean index, no unique commit, exact merged PR or remote/`origin/main` representation |
| Open clean worktree | preserve while active; optional checkout eviction | alert at 7d; removal only with remote branch + open-PR policy explicitly armed | same liveness/content proof; branch/PR survives |
| Dirty/dead session | quarantine and notify owner | alert 7d; operator adjudication at 30d; **never auto-delete** | manual recovery/commit/discard decision |
| Locked/recovery | preserve | no automatic expiry; quarterly review | explicit unlock and operator action |
| Runner `_work` | one reusable checkout per runner, clean between jobs; drain service before deep cleanup | inactive repos 7d; per-runner working cap 25 GiB M1/M2, 50 GiB PC | runner idle, no Worker/listener child holding run, durable outputs published |
| Runner `_temp` | run-scoped | successful run 24h; failed run 72h | run concluded; no active run ID/PID references path |
| Build output | publish durable artifact, delete local copy | success 24h; failed diagnostic 7d | checksum/URI receipt or declared disposable |
| Package caches | protected venv allowlist + LRU | 50 GiB/30d per Mac host; 100 GiB/30d PC; alert at 80% quota | never evict active interpreter/venv; rebuild command documented |
| Shared `.git` | maintenance, not deletion | weekly, or pack count >2,000; one writer window | no active fetch/commit/worktree mutation; `git fsck`/maintenance receipt |
| Runner logs | compress and rotate | 14d normal, 30d failed incident, 1 GiB/runner | preserve final error, job/run id and service transition |
| Codex/Claude session evidence | archive/compress final/handoff/recovery receipts | hot 30d, compressed 90d; database compaction via supported tooling | do not delete active session rows or sole recovery transcript |

**Pressure telemetry:** sample free bytes, free inodes, worktree-root size, runner-root
size and daily delta every 15 minutes. Warn at 70% used; critical at 80%; refuse new
full/data-heavy work at **85% used or <200 GiB free, whichever fires first**; emergency
at 90% or <100 GiB free. Sparse code-only tasks may continue below the hard gate if
their projected need fits. The M2 was already ~88% used, so full checkouts should be
refused now. Every GC application remains report-first, explicitly armed, capped, and
ledgered. No path is removed solely because its name or mtime looks old.

## H. Migration waves

| Wave | Change | Acceptance evidence | Rollback |
|---|---|---|---|
| **A — observe** | This audit only; freeze visibility/routing/deletion | fleet map, billing ledger, workflow census, disk/drive receipts captured | none; no runtime mutation |
| **B — repair workers and scratch** | Attach/identify 512 GB SSD; provision APFS scratch if healthy; re-register M1 with unique host names/labels; add crash restart + disk guards; split PC labels; raise WSL cap only after config review | M1 runners survive reboot and 24h soak; distinct `_work`; one `theta-m1` no-op/canary; PC still runs engine-render; disk telemetry green | restore prior service files/labels and runner roots; M2 remains current production route |
| **C — low-risk CI canary** | Route one trusted `ci-pack` shard to dedicated PC CI label via manual/branch gate; no fork PRs or production secrets | same-SHA result parity with hosted; 100 green jobs; clean post-job workspace; no host-state access | select hosted runner input/label; disable PC CI service |
| **D — capacity validation** | Run three PC CI slots while reserving one render slot | seven days: queue p95 <5m, runtime p95 ≤1.25× hosted, CPU <85% sustained, no swap/OOM, bounded disk, render SLA intact | reduce to one canary or hosted fallback |
| **E — expensive CI migration** | Move remaining trusted CI packs to PC; keep plan/gate/fences and explicit pack fallback hosted | seven-day hosted Linux burn down >90%; all required checks green; outage drill uses hosted fallback | flip pack matrix routing back to hosted |
| **F — render/nightly redistribution** | Same-SHA non-publishing PC render canary; restore M1 collect-tail; move collect and one Linux-compatible tail only after individual canaries | render hash/manifest parity and p95 gate; seven clean nightlies; exact publication/ledger receipts; M2 load and disk delta fall | runner input/label returns each job to M2 independently |
| **G — private cutover** | Provision VPS deploy key/GitHub App; audit secrets, collaborator/fork policy and runner groups; choose Pages visibility; set budgets/alerts; then change repo visibility | intended topology green; `macro-update` private fetch proof; Pages decision recorded; production health reports private merge SHA or descendant; cost telemetry matches model | restore public visibility and hosted routes; preserve old deploy credential until cutover proof |
| **H — retire routine M2 load** | after 14–30 day soak, remove routine production labels from M2 and enforce quotas/GC | M1/PC SLOs hold; M2 free-space trend bounded; break-glass drill succeeds | restore labels/service from versioned config |

No wave changes research/ledger authority, nightly’s sole forward-advancement law,
render publication contracts, merge gates, or production correctness without its own
explicit parity evidence.

## I. Hardware verdict

### BUY NOTHING

The PC already has the right CPU and ample disk for a three-slot CI canary plus a
reserved render slot. The M1 is adequate for the network-bound and host-private macOS
nightly work it previously ran; its outage is a service/disk-guard defect, not a compute
shortfall. The owned SSDs have enough raw capacity for bounded scratch, although the
best 512 GB candidate still needs attachment and proof. Finally, approximately 604 GiB
of M2 session worktrees is a lifecycle problem that new storage would merely conceal.

Reopen hardware procurement only if 30 days of post-migration telemetry proves one of:

- PC queue p95 remains >15m after WSL tuning and safe concurrency expansion;
- five-night engine/render p95 violates the 1.25× target while CPU is demonstrably
  saturated;
- the measured active scratch working set exceeds 80% of the commissioned SSD quota
  despite sparse-by-default and proof-bound GC; or
- drive health/endurance testing rejects the existing SSDs.

## J. Immediate next action

**Commission Wave B only: repair and uniquely re-identify the M1 runner fleet, attach
and benchmark the 512 GB SSD, and provision it as bounded APFS runner scratch if it
passes—without changing any production workflow route.**

Acceptance is concrete: the M1 has three uniquely named registrations, distinct work
roots, crash-restarting services that survive a reboot, free-space guards, one successful
`theta-m1` canary, and 24 hours of online/disk telemetry. This restores missing capacity
and creates a safe landing zone while leaving M2 production behavior untouched. Only
then commission the one-pack PC CI canary.

---

### Audit receipts and limits

Evidence sources: GitHub repository/Actions/billing/Pages APIs; all 86 workflow files at
fresh `origin/main`; jobs API for recent runs; `data/ops/nightly_timings/*.jsonl` read
from Git; local `system_profiler`, `diskutil`, `df`, `du`, process and LaunchAgent
inspection on M2; SSH inspection of M1 and PC; runner `.runner`, service status and
diagnostic logs; bounded drive benchmarks. The read snapshot moved during the audit as
normal production ran; tables name their cutoff. No process was stopped, no queue was
cancelled, no file tree was deleted, no runner was re-registered, and no workflow was
rerouted.

Limitations: July/30-day repository billing history is unavailable after the organization
transfer, so the monthly figure is a stated six-day linear projection. The 512 GB SSD
was absent. Runtime p95s based on run timestamps include queue/cancellation effects unless
otherwise stated. The M2 T7 and M1 T7 benchmarks are short synthetic checks, not endurance
certification.

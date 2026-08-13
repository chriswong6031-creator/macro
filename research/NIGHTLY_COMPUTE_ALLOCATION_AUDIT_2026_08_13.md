# Nightly compute & allocation audit — why the bake takes 5½ hours, and what to do about it

**Commissioned:** operator, 2026-08-13 (~01:45Z), after the 2026-08-11/12 two-night
Prophet outage: *"Its insane that our entire build takes 5 hours … are we able to
break down collect and engine so that they run faster? … need to design an efficient
allocation system, and assess if we need to buy external compute … PR backlog is
also moving to self-hosted, that will run in parallel with collect and engine."*

**Method:** no re-runs, no benchmarks — everything below is read from instruments
that already exist: the W2 nightly-timings ledger (`data/ops/nightly_timings/*.jsonl`,
read via `scripts/nightly_timings_report.py`), the last real bake's job graph
(run 31440972065), the runner registry (`gh api …/actions/runners`), and the
orchestration source (`scripts/collect.py`, `daily.yml`).

---

## §0 Direct answers

1. **Can collect and engine be broken down? Yes — and the biggest cut is already
   designed-for in the code.** `collect` is 148m of which **137m is the
   `collectors` band, and the attribution shows it is ~sequential wall-clock**:
   `scripts/collect.py` has a serial phase and a host-grouped concurrent phase, and
   **all eight of the heaviest sources sit in the serial phase** (§2.1). Registering
   them in `_CONCURRENT_HOSTS` — the exact "next collect cut" the code's own comment
   invites — collapses the band by ~60–80 minutes with no new hardware. `engine` is
   126m of which the Prophet picks are a **3-minute band** at the end of a ~67-minute
   intra-job path; a picks fast-lane job takes them off the monolith entirely (§3.2).
2. **Are they on the M1 Studio and the PC already? Half.** The nightly (collect,
   engine, every daily.yml job) runs ONLY on the Mac Studio (`macstudio` label —
   an M2 Ultra, 24 cores / 192 GB, hosting six runner processes). The PC
   (4 × `render-linux` Linux runners) runs **PR CI packs + fences only** (Wave 1,
   #5465, 2026-08-12). The nightly never touches the PC; the PC never touches the
   nightly. GitHub-hosted `ubuntu-latest` (free — the repo is public) carries only
   the sweeper and the new watchdogs.
3. **Do we need to buy compute? Not now.** The nightly is **network-bound, not
   CPU-bound**: 137 of its 322 critical-path minutes are HTTP pulls across ~125
   sources, mostly serial, while the M2 Ultra idles (load ~10 on 24 cores mid-bake
   tonight). Buying compute before parallelizing the orchestration buys nothing.
   §6 defines the three measured triggers that would change this verdict.
4. **PR-CI contention with the nightly?** Structurally separated by machine today
   (packs on the PC, nightly on the Mac). The real pressure point is the PC's own
   queue depth — ~18 ci runs in a partial 24h window × up to 12 packs each on 4
   slots (§5). The lever is pack overflow to free GitHub-hosted runners, not the Mac.
5. **Single-shot fragility** — the third leg of the operator's complaint — was fixed
   this session, before this audit: liveness watchdog (#5487), cancel-protection
   (#5488), CN-style backstop re-fire (#5492).

---

## §1 Measured inventory

**Hardware.** One Apple **M2 Ultra Mac Studio** (24 cores, 192 GB) + one Linux
**PC** (4 registered runners). Load on the Studio mid-collect tonight: ~10.5/24.

| runner | machine | labels | role |
|---|---|---|---|
| mac-builder-1 | Studio | `macstudio,codex,theta-m1` | nightly + render pool slot |
| mac-builder-2 | Studio | `macstudio,codex,theta-m1` | nightly + render pool slot |
| mac-builder-5 | Studio | `macstudio,parked` | pool slot (label still matches `macstudio` jobs) |
| mac-builder-3 | Studio | `macstudio-light` | live lanes (fastpath/sentinels) |
| mac-builder-light | Studio | `render-heavy` | heavy render sibling |
| mac-builder-4 | Studio | `merge-control,parked` | merge-on-green local half |
| pc-render-1..4 | PC | `render-linux` | **ci packs + fences (Wave 1)** |

Six runner processes share the one Studio. `parked` is advisory only — GitHub
routes on positive label match, so mac-builder-5 still takes `macstudio` jobs.

**Who runs where:** `daily.yml` (19 jobs), `render.yml`, `engine-render.yml`,
`closing-bell.yml`, `asia-close.yml` → `macstudio`. ci packs/fences →
`render-linux`. merge-on-green sweeper, nightly-liveness, nightly-backstop →
GitHub-hosted (free, public repo).

## §2 Where the 5½ hours go (last real bake, run 31440972065, +W2 medians over 6 nights)

Critical path: `et_gate 0.1m → collect 162.6m → [gov-rev 11.4m gap] → engine 136.0m
→ tails` — picks land ≈ **T+241m**; full run concludes ≈ T+325m (5h25m).

### §2.1 collect = the collectors band, and the collectors are serial

W2 medians: startup 5.7m · **collectors 137.1m** · market-commit-push 1.9m ·
r2-publish 1.0m. Attribution (W-L1): band 148.1m = **attributed 118.8m + residue
29.3m** — the sum ≈ wall-clock, i.e. the band is a sequential decomposition, not
an overlapped one.

Top sources, all verified **serial-phase** (`_CONCURRENT_HOSTS` registers none of
them; checked against `scripts/collect.py:49`):

| source | median | distinct host? |
|---|---|---|
| massive_stock_day | **35.8m** | yes — Massive API |
| finnhub_altdata | 10.7m | yes |
| wiki_pageviews | 9.2m | yes — Wikimedia |
| edgar_8k / sec_capital_structure | 7.8m / 8.0m | already in the `sec` group ceiling |
| usaspending_awards | 6.8m | host group already exists (`usaspending`) |
| polygon_news | 4.9m | yes |
| stock_fundamentals | 3.2m | yes |
| stocktwits / fred / eia / geo_revenue | ~2m each | yes |

`scripts/collect.py:626` already implements the right architecture — serial phase,
then host-grouped parallel phase ("GROUPS run in PARALLEL (distinct hosts)…
wall-clock collapses from the serial sum to the slowest single host-group") — and
its own log line says it exists to provide "the EVIDENCE for safely targeting the
next collect cut." The evidence is in. The heavy movers were never registered.

### §2.2 engine = a monolith whose Prophet step is 3 minutes

W2 medians: startup 0.1m · **restores-preamble 26.4m** · **engine-core 37.8m** ·
**prophet 3.0m** · builders-parallel 25.4m · tail-desks 29.4m · commit-publish 5.2m.

Two facts matter:

- **The picks cost 3 minutes** and sit ~67m into a 136m job that starts 174m into
  the run. Everything upstream of them on the critical path is either data they
  don't need or work that could run beside them.
- **restores-preamble is 26m of copying** — a dozen R2/cache restores (attention,
  odds-desk OHLCV, four breadth caches, CN/HK per-name stores, intraday cache…)
  paid in full before any compute. Any job split must NOT clone this preamble
  wholesale into each child (the 14k-file checkout alone has been observed at
  3s–14.5m); children restore only what they read, sparse-checkout thin.

### §2.3 The tail is already decomposed

oracle_offrender (10m), tech_lab_offrender (75m), standout_audit_us (22m),
us_scan_tier (8.6m), us_prophet_ledgers (3.3m — grading telemetry, not picks) all
hang off `engine` as separate jobs. The monolith problem is specifically
`collect` and `engine` themselves.

## §3 The decomposition plan

Ordered by leverage per unit of risk. Each phase is one PR-sized change with its
own rollback; none grows `daily.yml` toward the 512KB cliff without the
extraction diet (`tests/test_workflow_file_size.py` guards).

### P0-a — register the serial movers in `_CONCURRENT_HOSTS` (code-only, no workflow change)

Add host groups: `massive`, `finnhub`, `wikimedia`, `polygon_news`→`polygon`,
`stock_fundamentals` (its host), `stocktwits`, `fred`, and fold
`usaspending_awards`+`subawards` into the existing `usaspending` group. Serial
rump drops by ~70m; collectors band → **max(serial rump ≈ 45–55m, slowest group =
massive 36m) + overlap ≈ 55–70m** (from 137m). Risks: per-host rate ceilings
(the grouping idiom already handles this — one task per host, serial within);
same-file write collisions (the existing rule: distinct sources never share
files). Verification: W2 band + attribution before/after, one night.

### P0-b — the picks fast lane (answers the operator's "prophet render separate from collect")

New `us_picks` job: `needs: [et_gate, collect]`, thin sparse checkout, restore
ONLY the price store + the board's inputs, run the board builder (US scope) +
`build_prophet` + publish `site/prophet` + R2 index. Estimated ~20–30m of work →
**picks at ≈ T+3h05m today → ≈ T+1h25m** (post-P0-a collect) without waiting for
gov-rev, engine restores, or engine-core. `engine` keeps running `build_prophet`
this first release (idempotent second write, fast-lane wins on freshness) so the
fast lane can soak without being load-bearing — first-run-bomb law applies.
Ledger law unchanged: nightly remains the sole forward-ledger advancer; the fast
lane inherits `COLLECT_LANE=nightly` semantics ONLY for the plan/index artifacts,
never the grading ledgers (those stay in `us_prophet_ledgers`).

### P0-c — price-checkpoint inside collect (enables everything downstream to start earlier)

Sequence the price-bearing sources (massive_stock_day, yahoo) FIRST in the
concurrent pool and commit/push the price store as soon as they land (~T+40m),
before the long-tail sources finish. `us_picks` then keys on that checkpoint
(repository_dispatch or a split `collect_prices` job) → **picks ≈ T+70m ≈ 23:40Z
≈ 7:40pm ET**, vs ~02:30Z today. This is the deep cut; it needs the
market-commit-push step's conflict discipline extended to a mid-band commit.

### P1 — pre-close collect lane (move ~40–60m off the night entirely)

A 20:00Z lane collecting the sources that don't depend on the close or the
~18:15-ET FINRA post: wiki_pageviews, usaspending*, federal_register, fred, eia,
worldbank, jodi, bis, uncertainty, edgar filings (already-published), etc.
The 22:30Z bake then re-runs only close-dependent sources. Cuts the serial rump
P0-a leaves. (The et_gate anchor exists for FINRA CNMSshvol — most of the long
tail never needed it.)

### P2 — engine decomposition (only if still needed after P0/P1)

Candidates, in order: split `builders-parallel` + `tail-desks` into sibling jobs
against a committed engine-core checkpoint (saves ~30–50m of wall inside engine);
diet the 26m restore preamble per child (restore-what-you-read); profile
engine-core's 38m for internal parallelism (it is compute — the one place more
cores could matter, and it already has 20 idle ones).

## §4 What tonight's incident chain adds (context for the reader)

The 5½-hour monolith was survivable while it fired reliably. 2026-08-11/12 showed
the failure shape: one cron (DST pair, et_gate keeps one), one machine, one
5h25m chain with the picks at hour 4 — and a killed run indistinguishable from a
never-fired one. Now shipped: detection ≤9.5h (#5487), production-lane cancel
denial (#5488), backstop re-fire at 01:00/03:30/06:00Z (#5492), close-pass
provisional board actually green (#5495). This audit is the throughput half of
the same program: the shorter and more decomposed the chain, the less any single
loss costs.

## §5 PR-CI × nightly allocation

**Today:** structurally clean — packs/fences on the PC, nightly/renders on the
Studio, sweeper+watchdogs on free GitHub-hosted. The two workloads do not share
hardware, so "packs running in parallel with collect and engine" costs the
nightly nothing.

**The pressure point is the PC's own queue.** Partial last-24h window: ci ×18 +
fences ×18; each ci run fans out up to 12 packs; 4 slots. At ~8–15m/pack that is
several hours of queue depth on a busy day, and Wave 2 ("registry
pending-migration") will add more. Levers, cheapest first:

1. **Overflow to GitHub-hosted** — the repo is public; `ubuntu-latest` is free
   and ~20-concurrent. `ci-plan` already emits the pack matrix, so routing pack
   subsets by label (e.g. packs 0–7 → `render-linux`, 8–11 → `ubuntu-latest`) is
   a planner change, not new infra. Self-hosted stays for data/-dependent packs.
2. **More runner processes on the PC** — only if its cores are actually idle at
   queue time (packs are pytest, CPU-bound; measure before adding).
3. **A second cheap Linux box** — only after (1) is exhausted; see §6 triggers.

**Allocation rules to codify** (small PR to CLAUDE/AGENTS + labels):
nightly window 22:30–04:30Z = Studio priority for `daily`; render lanes coalesce
(already law); packs never take `macstudio`; watchdogs/sweeper never take
self-hosted (already true — keep it pinned by test, `test_workflow_is_off_the_self_hosted_pool`
is the pattern).

## §6 External compute: verdict NO, with tripwires

The nightly's bottleneck is sequential network I/O; the Studio has idle cores all
night; the PC's queue has a free-tier overflow lever untouched. Spend money when
a measured trigger fires, not before:

1. **Collectors band still >90m** (W2 median, 5 nights) after P0-a+P0-c land —
   i.e. the residual is genuinely vendor-rate-limited → consider paying vendors
   for rate, not GitHub for compute (it's the vendor ceiling that binds).
2. **Pack queue p50 wait >15m over a week** after ubuntu overflow is enabled →
   second Linux box (~one-time cost, no cloud recurring).
3. **engine-core >60m sustained** after P2 profiling → that is the one genuinely
   CPU-bound candidate; a Linux compute node (or the PC off-hours) could take
   engine-core only if profiling shows parallelizable structure.

## §7 Implementation guardrails

- Every workflow edit passes `tests/test_workflow_file_size.py` (487KB budget) —
  extract shell to `scripts/ci/`, never grow the file.
- DAG conformance (`scripts/check_dag_conformance.py`) owns the lane-drift story;
  new jobs declare their scope unions.
- P0-b soaks behind the engine's existing build_prophet for ≥3 nights
  (first-run-bomb law) before the engine step is removed.
- W2 timings bands are the acceptance instrument for every phase: each PR states
  its expected band delta and the follow-up verifies it against the ledger.
- No phase may regress the ledger laws: nightly = sole forward-ledger advancer;
  intraday/fast lanes write display artifacts + R2 only.

---
*Fixed-this-session, referenced above: #5487 (liveness watchdog), #5488 (cancel
denial), #5492 (backstop), #5494 (handoff repeal), #5495 (close-pass green).
Instruments read: run 31440972065; `data/ops/nightly_timings/{collect,engine}.jsonl`
via `nightly_timings_report.py --nights 6 --bands --sources`; runner registry
2026-08-13 01:45Z; `scripts/collect.py` @ `_CONCURRENT_HOSTS`/`main`.*

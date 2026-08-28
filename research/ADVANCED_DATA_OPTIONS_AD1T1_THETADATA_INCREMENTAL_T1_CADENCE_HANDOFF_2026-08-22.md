# SOL HANDOFF — AD-1T1
## Full-Universe Incremental ThetaData T1 Cadence

**Program:** `WS:ADVANCED-DATA-OPTIONS`  
**Wave:** `AD-1T1`  
**Repository:** `mastermindx-market-intelligence/macro`  
**Chairman source authority:** `DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA`  
**Prior wave:** AD-1T0 / PR #6253 / merge `a45ac6f58e630b5c07ffa67cb65d5032be9800da`  
**Current AD-1 maturity:** `BUILT_NOT_PROVEN`  
**AD-2:** CLOSED  
**Merge authority:** NONE — return the completed PR to Sol unmerged.

---

# 0. Executive ruling

AD-1T0 **passes Sol review**. Do not reopen it.

The cutover did the load-bearing work correctly: ThetaData is canonical; the AD producer no longer consumes Polygon/Massive options truth; `engine/options_intel_brief.py` stayed byte/behavior unchanged; `intel_brief_heuristic/v1.2` stayed frozen; `Q_flow` stayed absent; legacy Polygon GEX was removed rather than source-mixed; and the 375-name universe was not shrunk to manufacture a green board.

The real board is honestly `INSUFFICIENT_COVERAGE` because the canonical T1 store currently has only 39/375 AD names current.

The source-cadence defect is now the whole problem.

Current measured truth:

```text
AD universe                       375
roots with current T1 data         39
source coverage                  10.4%
required source coverage          90%
current daily refresh list        48 roots
frozen/stale roots               ~333
```

The 48-root limit is **not an inherent ThetaData throughput limit**. The current launchd wrapper obtains freshness by removing the current-year completion mark and rerunning the HISTORICAL BACKFILL primitive. That re-downloads the whole current year. The cited ~19 h full-universe extrapolation is therefore a property of the wrong maintenance algorithm, not measured one-day ThetaData capacity.

The repo already has the right substrate: `scripts/topup_thetadata_day.py` pulls one session and atomically merges that session into the existing year parquet.

AD-1T1 turns that bounded single-session substrate into the canonical full-universe daily T1 maintenance path.

---

# 1. Observable mission

After AD-1T1, the existing single ThetaData T1 store on the store-bearing M1 automatically maintains the canonical options universe with a bounded **one-session incremental refresh**, such that a normal market-day run can produce a machine-verifiable lawful S/D source pair with at least 90% AD-universe coverage without rerunning whole-year backfills.

This wave creates the **source capability**. It does not yet make AD-1 `PROVEN_LIVE`; production workflow routing is AD-1T2.

---

# 2. Why this matters

AD-1 intelligence is already built. It is withheld because current source breadth is 10.4%.

Do not fix that by lowering 0.90, shrinking the universe, pretending stale roots are current, copying the 60GB store, creating another options store, reintroducing Polygon options, turning on Q_flow, or publishing the 39-name diagnostic board as production.

The needed capability is: **market-wide current ThetaData truth every session**.

---

# 3. Authority / precedence

1. `DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA`
2. `research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md`
3. `contracts/options/OPTIONS_INTEL_BRIEF_V1.md`
4. `agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md`
5. Existing ThetaData owners:
   - `collectors/thetadata.py`
   - `engine/thetadata_store.py`
   - `scripts/backfill_thetadata_eod.py`
   - `scripts/topup_thetadata_day.py`
   - `research/THETADATA_OPS_RUNBOOK.md`

If current `main` lands a newer overlapping source law, stop and reconcile it. Do not overwrite it from this packet.

---

# 4. Sol archaeology already completed — do not redo broadly

## 4.1 Whole-year nightly refresh is the wrong primitive

`scripts/launchd/theta_backfill_keepalive.sh` hard-codes `REFRESH_ROOTS` and removes the current year from `_backfill_state.json`, forcing `backfill_thetadata_eod` to redownload the whole current year.

Do not scale this to 375 names.

Retire the current-year-unmark trick from DAILY maintenance. Historical backfill remains an explicit historical/resumable tool.

## 4.2 Existing incremental writer

`topup_thetadata_day.py` already:

- pulls one requested session;
- uses the canonical ThetaData collector;
- merges target-date rows into `{tier}/{ROOT}/{YYYY}.parquet`;
- removes only the prior copy of that exact date;
- preserves every other date;
- writes atomically;
- refuses to race a visible historical backfill;
- is used by the levels-seal path via `--roots --date`.

Extend this writer. Do not create another T1 writer.

## 4.3 One-day request topology

Current collector methods:

```text
bulk_eod(root, *, one day)
bulk_open_interest(root, *, one day)
bulk_greeks(root, *, one day)
```

For a one-day pull, EOD and OI are one short wildcard window; Greeks is one required one-day wildcard request. `order=3` does not create three Greek endpoint requests. The Terminal ceiling is 8 concurrent requests; the repo convention already leaves headroom with a maximum working budget of 6.

Benchmark root-level concurrency before freezing it.

## 4.4 Correct source clock

Do not use the same calendar date for all three tiers.

For a post-close run on current NYSE session `D`:

```text
S = previous NYSE session before D

ensure EOD[S]
ensure Greeks[S]
ensure OI[S]     # baseline, normally already present after steady state
ensure OI[D]     # settles S
```

ThetaData's same-session EOD/Greeks are not reliably available on S evening; the existing pre-open top-up was created for that reason. OI[D] is the morning print representing EOD S positions and is exactly the `chain_next` evidence AD requires.

No EOD[D] or Greeks[D] is needed merely to settle S.

Bootstrap: fetch OI[S] if absent. Steady state normally needs EOD[S] + Greeks[S] + OI[D].

Do not manufacture historical gaps.

## 4.5 Frozen-engine gap safety is already correct

Sol verified `Q_skew`: the engine only forms skew changes across **calendar-consecutive NYSE sessions**.

A stale July observation followed by a new August observation therefore yields `Q_skew=None`, not a fake one-day skew move. The next consecutive fresh session restores the leg.

Do not change the engine to bridge missing sessions.

## 4.6 Current launchd semantics are wrong for a finite daily batch

The current backfill plist uses unconditional `KeepAlive=true`, while the wrapper is a finite job. That matches the observed back-to-back refresh behavior.

The canonical daily maintainer must be a finite periodic task. It must not continuously respawn successful whole-year passes.

## 4.7 Runner/R2 is NOT this wave

Current runner truth: `theta-m1` is carried by `mac-builder-3`, which is not the store-bearing M1. R2 sync has a separate known defect.

Do not absorb those into AD-1T1.

AD-1T1 proves the canonical store cadence on the store host. AD-1T2 will restore the product workflow to the store host and commission AD-1 end to end.

---

# 5. Fable orchestration law

Fable is COO/integrator, not the mechanical worker.

Fable owns the concurrency ruling, scheduler transition ruling, integration, review adjudication, production-source acceptance, and durable state.

Delegate:

```text
ROUTE:census    -> one-day vendor benchmark + current-lane census
ROUTE:analysis  -> source clock / writer-race / failure-mode review
ROUTE:build     -> incremental writer + scheduler + health projection
ROUTE:review    -> adversarial PIT/concurrency/launchd review
ROUTE:debug     -> only attributable CI/live defects
```

Use isolated worktrees for writers. Every worker returns `STATUS / RESULT / EVIDENCE / GAPS / DEVIATIONS`.

Do not burn Fable main context on repetitive pulls, timing math, test authoring, log tailing, or simple plist edits.

---

# 6. Commission A — benchmark before choosing concurrency

Read-only benchmark. No canonical-store writes.

Use a stratified root sample: dense index ETFs, mega-caps, sector/industry ETFs, moderate single names, lower-density AD names.

Benchmark the exact steady-state pattern on a recent fully available S/D:

```text
EOD[S]
Greeks[S]
OI[D]
```

and separately the bootstrap extra `OI[S]`.

Measure root-worker counts:

```text
1
2
4
6
```

Never exceed 6.

Keep tier calls sequential within each root unless evidence proves a safer alternative, so the root-worker cap is also the approximate active-request cap.

Return:

```text
sample
contract-row distribution
per-tier latency
per-root latency
wall time per worker count
timeouts/retries/failures
terminal health before/after
projected full-universe runtime
```

Do not add `max_dte` or `strike_range` filters. That would change source semantics.

Fable selects production concurrency from evidence, not intuition.

---

# 7. Canonical incremental daily mode

Extend the existing T1 writer with a stable market-wide daily mode. Exact CLI/function names are implementation detail.

## Universe

Reuse the existing canonical T1 universe resolver. Do not fork another hard-coded list.

T1 remains:

```text
current options/GEX universe
UNION existing ETF anchors
UNION existing index roots
```

AD coverage is still measured against its canonical current universe.

## Session gate

Normal scheduled mode derives D/S using the canonical NYSE calendar and gates on America/New_York market time.

Normal source mutation occurs only:

```text
on a real NYSE session
after 16:10 ET
```

Do not hard-code a UTC offset that breaks on DST.

A weekday holiday is a clean no-op.

## Tier ensure law

For each target root:

```text
ensure EOD[S]
ensure Greeks[S]
ensure OI[S]
ensure OI[D]
```

If the exact session/tier rows are already present and complete, skip them. If absent, fetch that one session and merge it. Never repull January→August to obtain one day.

A same-session correction may replace only that session's rows using the existing exact-date replacement semantics.

## Greeks

Keep the canonical T1 full Greek-store semantics. Do not downgrade the store to an AD-only first-order schema merely because AD currently consumes only IV/delta/underlying_price.

## Store

One canonical store only. Never create an AD-specific T1 store or copy T1 into `polygon_gex`.

---

# 8. Writer exclusion

The historical backfill and incremental writer must not concurrently mutate the same year parquet.

Use one crash-safe local writer exclusion mechanism for the canonical T1 store. A filesystem advisory lock is acceptable.

Prove:

```text
daily vs daily cannot race
daily vs historical backfill cannot race
process death releases ownership
lock refusal mutates no parquet
lock refusal is visible/machine-readable
no stale file can wedge the source forever
```

This is local writer coordination, not a new queue/lifecycle plane.

---

# 9. Partial failure / atomicity

One root may fail without destroying other roots' successful current data.

One tier failure may not make a root look complete.

Per root, distinguish at least:

```text
complete
partial
failed
already_present
vendor_empty
terminal_unreachable
timeout_or_stream_failure
writer_locked
```

Keep existing atomic per-tier writes. Do not construct a giant cross-universe in-memory transaction.

---

# 10. Daily source-health receipt

Reuse an existing ThetaData store/quality authority; do not invent a new lifecycle store.

Preferred homes are the existing T1 `_manifest.json` daily-refresh section and/or existing ThetaData accrual/staleness audit.

The machine-readable daily result must logically preserve:

```text
source=thetadata
mode=incremental_daily
S
D
started_at
finished_at
elapsed_sec
worker_count

t1_universe_count
ad_universe_count

eod_S_roots
greeks_S_roots
oi_S_roots
oi_D_roots

complete_t1_roots
complete_ad_roots
ad_coverage_pct

status=healthy|partial|failed

failure_counts_by_reason
bounded failure examples
terminal_health
forced=false
```

AD-source `healthy` requires:

```text
complete_ad_roots / ad_universe_count >= 0.90
```

`complete_ad_roots` is the intersection needed to lawfully build the S/D panel, not “has a year parquet.”

Do not hard-code 375.

If `_manifest.json` is extended, historical-backfill manifest rewrites must preserve the daily section.

---

# 11. Retire whole-year DAILY refresh

After the new mode exists, the active daily lane must no longer:

```text
unmark current year for 48 roots
rerun full current-year backfill
continuously respawn under unconditional KeepAlive=true
```

Historical backfill remains an explicit resumable operation.

There must be exactly one active scheduled daily T1 maintainer.

Fable may either repurpose the current launchd label cleanly or install a clearly named daily-refresh label and boot out the old daily keepalive. It is forbidden to leave both active.

Record the final owner in the runbook and Agent OS.

---

# 12. Scheduler

The daily maintainer is a finite periodic task, not a continuously alive daemon.

Market gate:

```text
real NYSE session
after 16:10 America/New_York
```

This remains after the RTH live-flow polling window.

Successful completion must not cause another full refresh 60 seconds later.

On non-session: clean no-op.

On reboot/wake: it may run if the lawful post-close gate is open and today's required pair is incomplete, but it must not launch a historical catch-up sweep.

Historical catch-up remains explicit.

---

# 13. Preserve the existing levels-seal caller

`ops/launchd/levels_seal_preopen.sh` uses:

```text
python -m scripts.topup_thetadata_day --roots ... --date ...
```

That existing bounded mode must remain compatible.

The market-wide daily mode is additive to the writer contract, not a breaking replacement.

---

# 14. Do not prematurely narrow source data

ThetaData supports DTE/strike filters.

Do not use them in AD-1T1 for speed.

T1 is a shared canonical source and AD itself uses 0DTE, 7–60 DTE skew/IV, 60–120 DTE term structure, and far-DTE buckets.

If full-chain one-day incremental cannot fit the cadence at safe concurrency, return the measured bottleneck to Sol. Do not hide it by dropping contracts or roots.

---

# 15. Performance acceptance

The goal is not merely “less than 19 h.”

The market-wide source should be ready before the authoritative evening product build.

Target envelope:

```text
start after 16:10 ET
finish comfortably before 18:30 ET
```

Report p50/p95/max root duration, full-run duration, retries/failures, and terminal health.

Production concurrency must not induce Terminal stalls/starvation.

---

# 16. Required hostile tests

Clock:
- normal Monday/Tuesday;
- Friday→Monday;
- market holiday;
- DST regime;
- before/after 16:10 ET;
- delayed invocation;
- same-session rerun.

Pair:
- OI[S] already present;
- bootstrap OI[S] absent;
- EOD[S]/Greeks[S]/OI[D] independently absent;
- D EOD absent must not block settlement;
- stale July + fresh August must not create non-consecutive Q_skew.

Writer:
- two daily invocations;
- daily vs historical backfill;
- process death under lock;
- one-root failure;
- one-tier failure;
- no unrelated date removed.

Universe:
- add/drop symbol;
- root with no options;
- denominator follows canonical owner.

Scheduler:
- successful finite run does not respawn every minute;
- failure/retry cannot hammer forever;
- only one active daily maintainer.

Compatibility:
- existing levels-seal `--roots --date` behavior survives.

---

# 17. Implementation sequence

1. Fresh-main collision check.
2. ROUTE:census benchmark.
3. Fable freezes concurrency + scheduler transition.
4. Builder implements incremental mode + writer exclusion + health receipt.
5. Builder retires whole-year daily refresh behavior.
6. Builder wires exactly one finite periodic daily lane.
7. Focused/neighbor tests.
8. One adversarial source/PIT/concurrency/launchd review.
9. Repair only proven findings.
10. Current-head CI/fences.
11. Return PR to Sol.

Do not start AD-1T2.

---

# 18. Pre-merge Sol packet

Return the PR **unmerged** with:

```text
AD-1T1 VERDICT: READY_FOR_SOL_REVIEW / BLOCKED

PR:
base:
head:

CURRENT MAIN / COLLISIONS

ROUTED COMMISSIONS
census:
analysis:
build:
review:
debug if used:

BENCHMARK
sample:
worker=1:
worker=2:
worker=4:
worker=6:
selected_workers:
selection_reason:
projected_full_universe:

SOURCE CLOCK
D:
S:
EOD_S:
Greeks_S:
OI_S:
OI_D:
non_session_behavior:

WRITER
canonical_store:
shared_lock:
historical_backfill_coexistence:
same_date_replacement:
atomicity:
partial_failure_behavior:

SCHEDULER
old_whole_year_daily_refresh_retired:
active_daily_label:
trigger:
market_time_gate:
keepalive_behavior:
installed_live_status:

SOURCE HEALTH
t1_universe:
ad_universe:
complete_root_definition:
healthy_threshold:
receipt_owner:

TESTS
focused:
neighbors:
flip/mutation:
adversarial:

CI
ci:
fences:
other:

AUTHORITY
engine_options_intel_brief_changed: NO
v1.2_changed: NO
Q_flow: ABSENT
legacy_polygon_options_consumed: 0
new_store_or_collector: NO

FINAL MATURITY
AD-1:
AD-1T1:
AD-1T2:
AD-2:

STOP
PR remains unmerged.
AD-1T2 not started.
AD-2 not started.
```

---

# 19. Post-merge production proof — not authorized yet

After Sol accepts/merges AD-1T1, production commissioning will require **two consecutive normal scheduled sessions**.

The first proves full-universe breadth. The second creates a current calendar-consecutive pair so Q_skew can lawfully return where source evidence qualifies.

Each must prove:

```text
normal scheduled invocation
no diagnostic bypass
no whole-year refresh
complete_ad_roots / universe >= 0.90
healthy receipt
no terminal stall
no writer race
```

After the second source session, run a read-only AD producer diagnostic on the store-bearing host:

```text
source_coverage_pct >= 0.90
board_state not STALE_SOURCE
board_state not INSUFFICIENT_COVERAGE unless an independent new cause exists
lawful S/D
zero Polygon options inputs
receipt closure intact
```

AD-1 still remains `BUILT_NOT_PROVEN` until AD-1T2 restores the real consumer/product workflow.

---

# 20. Non-goals

Do not:

- modify `engine/options_intel_brief.py`;
- change v1.2;
- activate Q_flow;
- rebuild GEX;
- alter Prophet authority;
- alter the AD UI;
- lower 0.90;
- shrink the universe;
- cosmetically backfill missing Jul/Aug sessions;
- repair R2 sync;
- re-pin/register the M1 GitHub runner;
- move/copy the 60GB store;
- create another store;
- launch a second Terminal;
- redesign Terminal intraday;
- start AD-2;
- add DTE/strike filters without a new Sol ruling.

---

# 21. Next wave after this — AD-1T2

Once the T1 source cadence is production-proven:

> **AD-1T2 — Restore the store-bearing M1 to the existing `theta-m1` product workflow and commission AD-1 end to end.**

Preferred direction: restore the existing store host into the existing workflow topology. Do not make the currently broken R2 sync a prerequisite unless new evidence proves it is necessary.

Do not start T2 in this PR.

---

# 22. Durable state

Correct the stale top-level workstream next action that still says to execute AD-1T0.

During this PR the truthful wave state is:

```text
AD-1      BUILT_NOT_PROVEN
AD-1T0    done
AD-1T1    in_progress / PR
AD-1T2    not started
AD-2      not started
```

Record this discovery:

> The ~19 h full-universe estimate is a property of the whole-year re-pull daily-maintenance design, not measured one-day ThetaData source throughput.

Do not claim the one-day path meets cadence until the benchmark proves it.

---

# 23. Stop

When the bounded AD-1T1 PR is green and reviewed:

**STOP AND RETURN TO SOL.**

Do not merge.

Do not install an unreviewed production scheduler.

Do not start AD-1T2.

Do not start AD-2.

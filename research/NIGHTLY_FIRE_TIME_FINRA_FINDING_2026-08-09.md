# The nightly's fire time is not FINRA-bound — and it should not move

**Date:** 2026-08-09
**Question:** `daily.yml` schedules the entire multi-hour ledger-advancing nightly at
`cron: "30 22 * * *"` specifically to land after the ~6pm-ET FINRA CNMSshvol post. Per-source
attribution (#5135) measured that collector at **1.3 s**. Can `finra_short_volume` (and the two
cboe adapters) move to their own small post-6pm cadence so the nightly can fire earlier?

**Answer: no — and the premise contains a measurement error.** FINRA is a *soft, self-healing*
constraint that never bound the schedule. The schedule is bound by a **17:00 ET structural
floor**, and the nightly's real start time is set by **~59 min of GitHub dispatch lag** plus
**runner contention**, not by the cron. A separate FINRA lane would buy zero latency while adding
a workflow, a `data/` write path outside the sole ledger advancer, and a join contract.

The reclaimable latency was real, but it was in a different place: **`closing-bell.yml` rendered
twice every trading day**, burning a median **85.0 min** of the two-warm-Mac pool inside the exact
window the nightly fires into. That is fixed in the same PR as this finding.

---

## §1 What was measured

All figures below are measurements from this repo's own telemetry and the GitHub API on
2026-08-09, not estimates.

### 1.1 `finra_short_volume` costs 1.3 s — and is self-healing

From `data/run_status.json` (the read-only input the W-L1 attribution copies into the timings
ledger), 183 of 186 sources carry `elapsed_sec`:

| source | elapsed_sec |
|---|---|
| `finra_short_volume` | **1.3** |
| `cboe_gex` | 10.9 |
| `cboe_putcall` | 4.7 |
| `finra_ats_transparency` | 1.0 |
| `finra_otc_nonats` | 0.9 |

For scale, the top of the same table is `massive_stock_day` 1310.8 s and
`tape_flow_etf-history` 1236.9 s; the timed sum is 173.9 min.

**The cost was never the point — but neither was the availability.** `collectors/finra_short_volume.py`:

* `LOOKBACK_DAYS = 30` — every run re-fetches a 30-calendar-day rolling window of business days.
* `if ts in have and i >= 2: continue` — the newest **2** sessions are always re-fetched (FINRA restates).
* A 404 (holiday *or not-yet-posted*) is `skipped += 1; continue` — **not** a failure. Only an
  unreachable CDN on the first fetch raises.
* `stale_after_days = 4`.

So a nightly that fires before the CNMSshvol post loses **one session of recency**, which the very
next run repairs — the missed date is still inside the 30-day window and not in `have`. The
freshness contract already tolerates 4 days.

### 1.2 Nothing ledger-advancing consumes it

| consumer | role |
|---|---|
| `engine/short_volume.py` | "CONTEXT confirmer… **never** folded into any scored alpha factor" (its own docstring) |
| `engine/stock_fundamentals.py:217` | stock-page `signal_map()` |
| `engine/ownership_event_wire.py:908` | freshness axis; its own label already reads **"typically T+1 lag"**, degrades to `"unavailable"` |
| `scripts/build_darkpool_desk.py` | desk display |
| `scripts/build_smart_money.py:1023` | signal map |
| `scripts/sec_ftd_phase0.py` | research control store |

`engine/signal_frontier_docket.py:419` records SLF-012 as KILLED — "off-exchange-only with
non-stationary denominator — structurally biased as standalone."

**No forward ledger needs it in-run.** Brief item 3 (sole-advancer safety) and item 2 (join/wait
contract) are therefore both satisfiable — a separate cadence *could* be built safely. §2 is why
it should not be.

### 1.3 The two cboe adapters do NOT share the constraint — theirs is stricter

`collectors/cboe.py` fetches the CBOE `delayed_quotes` **LIVE snapshot**. There is no dated
archive:

> "A chain snapshot is unrecoverable after tonight (delayed_quotes serves the LIVE snapshot only),
> so the cost asymmetry is extreme: 5 idle minutes on a bad night versus a permanent hole."

The file carries an `_ABSENT_SESSIONS` registry of exactly those permanent holes ("a missed session
cannot be honestly backfilled… never fabricate a row"). This is the **inverse** of FINRA's dated
flat file. `cboe_gex` / `cboe_putcall` are the *last* sources that should move to a cadence that
might miss a session, and they argue for firing later, never earlier.

### 1.4 The real floor is 17:00 ET, and it is structural

`lib/nyse_calendar.py:36`:

```python
_CLOSE_PLUS_SETTLE = time(17, 0)
```

`expected_last_session()` returns the **prior** session until 17:00 ET. `closing-bell.yml` documents
this explicitly as why it cannot use the standard `--heal` freshness gate at 16:05 ET and must fall
back to a bare `is_session()` check. Any nightly firing before 17:00 ET builds against a store that
is not yet *expected* to hold today's bar.

**This is the binding availability constraint the brief asked for — and it is 90 minutes earlier
than the FINRA post, so FINRA was never the latest one.**

### 1.5 The cron is not when the nightly starts (median lag 59.1 min)

`gh run list --workflow daily.yml`, `schedule` events only, against the 22:30Z cron:

| run created (UTC) | lag vs 22:30Z |
|---|---|
| 2026-07-29T23:29:42Z | 59.7 min |
| 2026-07-30T23:32:43Z | 62.7 |
| 2026-07-31T23:29:06Z | 59.1 |
| 2026-08-01T23:28:01Z | 58.0 |
| 2026-08-02T23:28:40Z | 58.7 |
| 2026-08-03T23:35:08Z | 65.1 |
| 2026-08-04T23:32:21Z | 62.4 |
| 2026-08-05T23:28:38Z | 58.6 |
| 2026-08-07T01:36:07Z | 186.1 |
| 2026-08-07T23:05:18Z | 35.3 |
| 2026-08-08T22:57:06Z | 27.1 |

**Median 59.1 min (n=11).** The 18:30 ET nominal fire creates its run at **~19:29 ET** — about
**89 minutes** after the FINRA post, not the 30 the comment claimed.

Queueing is on top of that. Run `30960328285` (schedule, created 2026-08-04T23:32:21Z) reports
`run_started_at = 2026-08-05T03:33:16Z` — **4h01m** waiting for a runner.

### 1.6 The pool is two warm Macs

Live `gh api repos/:owner/:repo/actions/runners`, filtered to the `macstudio` label that
`runs-on: [self-hosted, macstudio]` requires:

| runner | labels | note |
|---|---|---|
| `mac-builder-1` | self-hosted, macOS, ARM64, **macstudio**, codex, theta-m1 | warm |
| `mac-builder-2` | self-hosted, macOS, ARM64, **macstudio**, codex, theta-m1 | warm |
| `mac-builder-5` | self-hosted, macOS, ARM64, **macstudio**, parked | cold spare |

`mac-builder-3` is `macstudio-light` — a **different label**, which `[self-hosted, macstudio]`
does not match. Effective warm capacity for the nightly and the render lanes is **2**.

> Aside for the masterplan: `BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md:234` says "the 5-host mac
> pool is idle exactly when the breathing…". The label census above says the number that matters
> for `[self-hosted, macstudio]` is 2 warm + 1 parked. Worth correcting when that section is next
> touched; not changed here.

---

## §2 Why the cron does not move

Stack the measurements:

```
16:00 ET  US close
17:00 ET  ── HARD FLOOR ── _CLOSE_PLUS_SETTLE; before this, expected_last_session() = prior session
17:55 ET  closing-bell (Build A) intended finish (16:05 + 109 min measured)
18:00 ET  FINRA CNMSshvol post  ← SOFT: self-healing, 1.3 s, no ledger consumer
18:30 ET  daily.yml cron (nominal)
19:29 ET  daily.yml run actually created (median +59.1 min dispatch lag)
```

Between the 17:00 ET floor and the 18:30 ET nominal fire there are **90 nominal minutes**. Every
one of them is inside the dispatch-lag band (27–186 min observed, median 59.1). Moving the cron
earlier therefore:

1. **Buys no reliable latency** — the lag dominates the move by roughly 2:1 at the median.
2. **Spends the settle margin** — 17:30 ET nominal would put the fast-dispatch tail (27 min) at
   17:57 ET, only 57 minutes above a floor that silently degrades to yesterday's session rather
   than failing loudly.
3. **Moves the nightly *into* contention**, not out of it — see §3.

And detaching FINRA specifically buys **1.3 seconds**, because the constraint it was blamed for
is availability, and the availability floor that actually binds (17:00 ET) is an hour earlier and
belongs to the price store.

**This closes the standing assumption.** The "safe-earliest is ~18:15 ET" note in `daily.yml` was
derived from the FINRA post; the real safe-earliest is derived from `_CLOSE_PLUS_SETTLE` and the
render lane's occupancy.

### DST (the November flip) — and what this means for PR #5035

**`daily.yml` is not touched by this PR.** Open PR **#5035** ("fix(daily): DST-proof the 18:30-ET
nightly anchor — cron pair + fail-open `et_gate`") already owns that file and rewrites the same
schedule comment block; it is armed `merge-on-green` and currently `merge-blocked` on pack reds.
Editing that comment here would have been a conflicting regeneration of a better-scoped lane, so the
correction is filed here instead of applied there.

**#5035's fix stands; its rationale needs one amendment.** Its gate is a *regime match* (which cron
fired vs. the current America/New_York UTC offset), explicitly **not** a wall-clock window — chosen
so "a real firing queued for hours behind a long run still runs". That design is exactly right and
is **robust to the 59.1-min dispatch lag measured in §1.5**, which would have broken a wall-clock
gate. Nothing in this finding argues against merging it.

What the measurements do change is the **severity** it is sold on. #5035 describes the flip as
landing "inside the FINRA race window"; with §1.1 and §1.5:

* 17:30 EST still clears the 17:00 ET structural floor — no correctness break in the price store.
* +59.1 min median lag → actual start ~18:29 EST, *after* the post, most nights.
* Only the fast-dispatch tail (27 min observed) lands 17:57 EST and misses that evening's file —
  which the collector self-heals the next night.

So the flip is a **recency nick on a display-tier confirmer, not a data-integrity break**. #5035's
own body already reaches the same conclusion mechanically ("self-heals via the 30-day lookback on
the *next* run"); the amendment is that this makes it a **P2 tidiness fix, not a P0 race**, and its
"safe-earliest is ~18:15 ET" premise should be restated against `_CLOSE_PLUS_SETTLE` (17:00 ET)
rather than the FINRA post. That is a body/comment edit for that lane's owner, not a reason to hold
it.

Separately: this finding does **not** propose moving the cron in either direction, so it introduces
no DST exposure of its own.

---

## §3 What the latency actually was: closing-bell rendered twice, every trading day

Brief item 5 asked about collisions on the `macstudio` pool. There is one, and it was a live defect.

**Root cause.** `closing-bell.yml`'s session-day guard dedups the summer DST cron line with:

```python
if st.get('as_of') == et.isoformat():   # "2026-08-07T23:11:28Z" == "2026-08-07"
    sys.exit(5)
```

The stamp writer 300 lines below emits `as_of` as a full ISO **timestamp** and the bare date as a
sibling key, `session`. The comparison is **False on every run the lane has ever made**.

**Not a race.** `concurrency: pipeline-closingbell` already serializes the pair. On 2026-08-05 the
sibling ended `22:49:07Z`; the duplicate's job started `22:49:08Z`, checked out at `22:49:13Z` and
pulled main at `22:49:21Z` — it **held the fresh stamp** — and its guard still returned *proceed*
at `22:50:24Z`, then rendered 93 more minutes and committed. Only the field name was wrong.

**Measured duplicate `closingbell` job wall-time** (job-level, excludes queue and the `publish` job):

| date | duplicate job | minutes |
|---|---|---|
| 2026-07-31 | 22:35:40Z → 23:56:25Z | 80.8 |
| 2026-08-03 | 22:42:53Z → 00:07:55Z | 85.0 |
| 2026-08-04 | 22:50:38Z → 00:18:03Z | 87.4 |
| 2026-08-05 | 22:49:08Z → 00:22:28Z | 93.3 |
| 2026-08-07 | 22:09:58Z → 23:14:18Z | 64.3 |

**Median 85.0 min (n=5), range 64.3–93.3.** Observed on 7/7 sampled trading days (07-30, 07-31,
08-03, 08-04, 08-05, 08-07 — two runs each).

**Where it lands is the point.** The duplicate occupies one of two warm Macs from ~22:10–22:50Z to
~23:14–00:22Z. `daily.yml`'s cron fires at **22:30Z** and its run is created at a median
**23:29Z** — dead centre. Roughly **7.1 Mac-hours per week** were being spent re-rendering a board
that had just been rendered, in the window the nightly needs a runner.

**Fixed** in this PR: the guard reads `session`. Pinned by
`tests/test_closingbell_dedup_contract.py`, which executes the workflow's *real* writer heredoc and
evaluates the guard's *real* comparison expression against it — plus a negative control that
re-runs the same expression with `as_of` substituted back in and asserts it goes False, so the test
demonstrably sees the defect it exists to catch.

### What this does *not* claim

Freeing 85 min of pool capacity in the contended window is not the same as proving the nightly
starts 85 min earlier. The 4h01m queue wait on 2026-08-04 is not fully explained by the duplicate
(which ended 00:18Z). **The honest next step is measurement, not a claim**: `data/ops/nightly_timings/`
now carries per-job `start`/`end`, so the delta is directly readable from the ledger after a week of
post-fix nights. No further schedule change should be proposed before that read.

---

## §4 Answers to the brief, itemised

1. **Other hard availability floors?** Yes — and it is *earlier* than FINRA:
   `_CLOSE_PLUS_SETTLE = 17:00 ET` in `lib/nyse_calendar.py`, governing the price store via
   `expected_last_session()`. The cboe delayed-chain family (§1.3) has a *stricter* shape than
   FINRA (unbackfillable), and OPRA OI is a documented t−1 contract (`engine/thetadata_store.py`:
   published ~06:30 ET for the *previous* day), so it constrains nothing here.
2. **Downstream consumers / same-run need?** Six consumers, all display/context tier; none
   ledger-advancing (§1.2). A separate cadence would need no join/wait contract — it would simply
   buy nothing.
3. **Sole-advancer law intact?** Nothing was split, so `daily.yml` remains the sole advancer. The
   `closing-bell.yml` fix touches only its skip guard; that lane's `COLLECT_LANE`-unset,
   discard-`data/` contract is unchanged.
4. **DST correct in both regimes?** No cron is changed by this PR, so no DST risk is introduced.
   `daily.yml`'s flip is owned by open PR #5035, whose regime-match gate is robust to the dispatch
   lag measured here; §2 re-characterises its severity with measurement rather than contradicting
   it. The closing-bell fix makes that lane's DST *pair* behave as its own comment always claimed —
   exactly one render per trading day in **both** regimes, and structurally so: winter's
   wrong-season line skips on a pure clock bound (`< 16:02 ET`), summer's on the now-working
   session dedup. Neither depends on a dated calendar reminder.
5. **Pool collisions?** Yes — §3. Two warm Macs, not five (§1.6).

## §5 Provenance

* Per-source timings: `data/run_status.json`, ranked via `scripts/nightly_timings_report.py --sources`
  plumbing added in #5135.
* Job/band timings: `data/ops/nightly_timings/*.jsonl`.
* Run creation, start and job step timings: GitHub Actions API (`gh run list`, `.../runs/<id>/jobs`).
* Runner labels: `gh api repos/:owner/:repo/actions/runners`.

# Adjudication — HK washout_watch vs the cycle ladder's BOTTOM WATCH cohort

**Date:** 2026-08-05 · **Scope:** `engine/hk_washout_watch.py` selection rule, display-tier only
**Status:** MEASURED — awaiting operator ratification. Nothing shipped; no lane membership changed.
**Receipts:** `research/hk_washout_coverage/washout_coverage_packet.py` → `washout_coverage_results.json`

---

## §0 — The decision being asked for

The HK board's cycle ladder marks some names **BOTTOM WATCH** (display label `NEARING A LOW`).
Half of that cohort appears in **no lane of the board at all** — not buy, watch, laggards,
leaders, ran, vetoed, or washout_watch. The operator is asked to rule on one question:

> **Should `engine/hk_washout_watch.py` admit a ladder BOTTOM WATCH name as a washout
> candidate on the strength of its ladder label alone?**

Recommendation is in §5 (**Option B**, one-line change, display-tier, +1.9 rows/night).
Two further defects found along the way (§3.1, §3.3) are reported but **not** proposed for
this ruling — they widen the lane much further and deserve their own decision.

---

## §1 — Verdict

**It is a coverage gap, not a deliberate selection.**

The organ was *designed* to catch exactly these names and cannot. Its candidacy test has three
routes in (`_is_washout_candidate`, `engine/hk_washout_watch.py:393`), and the one written to
catch deep-decline names — `dist_200dma <= -12%` — **has never been able to fire in production**.
Across 166 published washout rows on 10 board dates, `dist_200dma` is non-null on **zero** of them.

That is not a threshold judgement. It is a **key-name mismatch** — and the value the code wants
is sitting right next to the key it asks for:

- `scripts/build_hk_library.py:1195` derives `dist_200dma` from `rec["tech"]["ma200"]`.
- **Nothing writes `ma200`.** The producer is `engine.stock_technicals.snapshot()`
  (`engine/stock_technicals.py:238`), and it emits the 200-day distance under the name
  **`pct_vs_200dma`** — plus a `above200` boolean. Verified empirically on 9926.HK:
  `snapshot()` returns `pct_vs_200dma = -15.8`, and `"ma200" in snap` is `False`.
- `engine/hk_washout_watch.py:414` and `:619` are the *only* readers of `tech["ma200"]` in the
  repo. They read a key no producer emits, next to one that holds the answer.

⚠️ **The obvious one-line fix is a trap.** `pct_vs_200dma` is a **percent**
(`(px/ref - 1.0) * 100.0`, `engine/stock_technicals.py:229`); `PCT_BELOW_200DMA_THRESH` is a
**fraction** (`-0.12`). Swapping the key without dividing by 100 makes the test
`-15.8 <= -0.12` — true for *any* name more than **0.12%** below its 200-day line, i.e. nearly
every name below trend. That is a 100× over-admission wearing the costume of a typo fix.
Anyone implementing §4 Option C must convert units and re-measure the admission count.

Had the criterion worked, it would have admitted **12 of the 19 invisible name-days (63%)** on
its own — including RUSAL at **30% below** its 200-day line. The exclusion is a consequence of a
dead criterion, not a choice anyone made.

Corroborating that nobody intended this exclusion: the module docstring states the organ
"operates on the FULL entry list so washout candidates with confluence are VISIBLE even when the
main board is dark," and the test suite carries `test_deep_below_200dma_is_candidate` — the
authors believed the criterion worked.

---

## §2 — Receipts

Measured over the 10 most recent committed board snapshots (2026-07-23 … 2026-08-05).
RSI is recomputed from `data/hk_stocks/<ticker>.parquet` with the builder's own
`engine.stock_technicals.snapshot()`, truncated to each snapshot's `as_of`.

**On the obvious objection** — the parquet is today's file, so reconstructing a past date
assumes the series was not later restated or backfilled. That assumption is not taken on
faith: the script replays every published `washout_watch` row at its own board date and
**reproduces the published RSI on 166 of 166**, across all 10 dates. A restated series would
break that agreement. The reconstruction is empirically sound for these names, and the script
prints a loud failure if it ever stops being so.

### 2.1 The task's 2026-08-04 observation is confirmed exactly

| Ticker | Name | RSI (08-04) | In any lane? |
|---|---|---|---|
| 9868.HK | XPeng | **38** | washout_watch |
| 2382.HK | Sunny Optical | 46 | — none — |
| 9926.HK | Akeso | 47 | — none — |
| 0486.HK | RUSAL | 41 | — none — |
| 1347.HK | Hua Hong Semiconductor | 42 | — none — |

### 2.2 It is not a one-day artifact

| Metric (10 board dates) | Value |
|---|---|
| BOTTOM WATCH name-days | 38 |
| …invisible in every lane | **19 (50.0%)** |
| washout_watch name-days | 166 |
| …labelled `NEARING A HIGH` | **70 (42.2%)** |
| …labelled `NEARING A LOW` | **17 (10.2%)** |
| rows carrying a non-null `dist_200dma` | **0 of 166** |

The cohort churns nightly (per-day invisibility ranges 0/2 to 5/8), so any single-date receipt
expires. The 50% figure is the stable one.

### 2.3 The lane does not currently mean what its name says

On 2026-08-05 the **washout** lane was 11/16 `NEARING A HIGH` and 1/16 `NEARING A LOW`; four rows
were `chase_risk` at RSI 73–77. Over 10 dates it is 42% names near highs, 10% names near lows.
Admission is dominated by `SB_ACCUM` (southbound accumulation, `accum_z >= 0.3` — 10 of 16 rows
on 08-05), a low bar that names at highs clear easily. **Whatever dilution concern applies to
this proposal already exists in the lane, pointing the other way.**

---

## §3 — Root cause

### 3.1 The dead criterion (§1) — `dist_200dma` never populated

Also silently disables `_above_200_by` at `scripts/build_hk_library.py:2205`, which is
`None` for every name and flows into `build_hk_core_rows(above_200_by=...)`.

### 3.2 The band misalignment — candidacy stops where the reclaim signal starts

With `dist_200dma` dead and `NEARING A LOW` containing none of the label keywords the code
looks for (`DECLINE`, `FALL`, `DOWNTREND`, `BEAR`), candidacy for these names rests entirely on
`RSI <= 40` (`RSI_OVERSOLD`) or the `cycle_blocked` flag. But the confluence signal that would
admit them, `RSI_RECLAIM`, fires on `30 <= RSI <= 50`.

**The 10-point band (40, 50] can earn a confluence signal but can never be allowed to.**

Every one of the four invisible names on 08-04 sits in that band — 46, 47, 41, 42 — while the one
visible name (XPeng, 38) is below it. Across all 10 dates, **18 of 19** invisible name-days fall
inside the reclaim zone. These names are not failing for want of a signal; they are refused at
the door before the signal is consulted.

This is not inference. `engine/stock_score.py:219` defines
`_CYCLE_BLOCK_STATES = {"DECLINE", "ROLLING OVER", "TOP WATCH"}` — **BOTTOM WATCH is not a
member**, so the ladder's BOTTOM WATCH state never sets `cycle_blocked` by itself. The state
that the board calls "nearing a low" is, by construction, not one the block-list recognises.

(A name can still be `cycle_blocked` for an unrelated reason — 1347.HK entered the lane on
08-05 via `_overextended`, trading 30% *above* its 200-day line. That is the lane admitting a
name for being stretched, not washed out.)

### 3.3 The tests pass because the fixture supplies what production never does

`tests/test_hk_washout_watch.py:153` (`test_deep_below_200dma_is_candidate`) constructs a
synthetic entry with `dist_200dma=-0.15` and asserts candidacy. It passes. Production sets that
field to `None` on 100% of names. The suite is green and the criterion is 100% dark — the same
shape as the SEC-HEADER validator postmortem: **a step whose fixtures are the only thing
vouching for it.**

---

## §4 — What full ladder-cohort coverage would cost

| | Option A — align RSI candidacy 40 → 50 | **Option B — admit on the ladder label** | Option C — revive `dist_200dma` |
|---|---|---|---|
| Change | `RSI_OVERSOLD` 40 → 50 | add `NEARING A LOW` / BOTTOM WATCH to `_is_washout_candidate` | read `pct_vs_200dma` **÷ 100**, restoring the −12% route |
| New candidates (08-05) | **+44** | **+2** | **+44** |
| Lane size | 16 → **60 (38% of the board)** | 16 → **18** | 16 → **up to 60** |
| Mean lane size / night | — | **16.6 → 18.5 (+1.9)** | — |
| Rescues the cohort? | yes, incidentally | **18 of 19 name-days** | 12 of 19 name-days |
| Collateral | 29 `BOTTOMING` + 10 `UNCONFIRMED TURN` + 2 `UPTREND` | none — targets the cohort exactly | 49 names clear −12%; only **2** are `NEARING A LOW` (19 `BOTTOMING`, 10 `BUY ZONE`, 9 `UNCONFIRMED TURN`, 5 `NEARING A HIGH`, 4 `UPTREND`) |

**Option A is a bad trade**: it buys 2 BOTTOM WATCH names at the cost of 44 new rows, and destroys
what the lane means.

**Option C is the honest repair of §3.1, and it is not cheap.** It is small in *code* — the value
already exists as `pct_vs_200dma` — but 49 of 156 names clear the −12% line today, so it admits
**44 new candidates, the same magnitude as Option A**. Only 2 of those 49 are `NEARING A LOW`:
the −12% route selects on price alone, independent of the ladder, so it is a different organ from
the one this ruling is about. It also carries the 100× unit trap from §1 — the un-converted form
admits **98 of 156 names (63% of the board)**. Worth doing, on its own evidence, in its own PR.

**Dilution under Option B:** the lane's `NEARING A LOW` share rises from 10.2% to roughly 20%,
against a 42% `NEARING A HIGH` share. The proposal moves the lane *toward* its name, not away.

---

## §5 — Recommendation

**Adopt Option B**, display-tier only, as a one-line addition to `_is_washout_candidate`: treat
the ladder's BOTTOM WATCH state as a fourth candidacy route, alongside the existing three.

Why this one:

1. **It is the smallest change that closes the gap** — +1.9 rows/night, targeted at the exact
   cohort, no collateral admissions.
2. **It changes nothing but visibility.** Candidacy only earns a name the right to be *scored*;
   `_assign_state` still requires ≥1 real confluence signal, so a BOTTOM WATCH name with no
   evidence still does not appear. It is not a buy claim, it does not touch rank, size, or gate,
   and `display_only: True` already governs every row.
3. **It respects the standing kills.** The three washout rows in `DO_NOT_REBUILD.md` kill
   *signal* constructions (washout × turn as an entry seed, buyback-floor washout,
   MCO-washout as a radar leg). The MCO row explicitly preserves display homes. Per the house
   epistemics law, display-tier detection ships freely; the gauntlet binds only at promotion to
   authority. This proposal claims no authority.
4. **It does not duplicate #4631.** That PR's `basing` shelf routes BOTTOM WATCH rows *within the
   cascade-eligible buy pool*, and its own code comment records it as "measured empty on all 14
   committed snapshots" precisely because the pool is cascade-gated. It cannot reach names that
   never enter the pool. The two are complementary: #4631 gives the state a home *inside* the
   board; this gives it a home *outside*.

**Disclose, don't hide:** 1 of 19 invisible name-days (0669.HK at RSI 53, 19% *above* its 200-day
line) would still not appear — it earns no confluence signal. That is the correct outcome, not a
shortfall: the organ requires evidence, and there was none.

**Also worth the operator's eye:** two names carried `NEARING A LOW` while trading *above* their
200-day line (1347.HK +24.7%, 0669.HK +19.3%). The ladder is a cycle read, not a price-vs-MA
read, so this is not necessarily wrong — but it is the kind of divergence the basing shelf's copy
("still falling, but working on a base") does not describe, and it is worth a look.

### Not in this ruling

§3.1 (dead `dist_200dma`) and §3.3 (vacuous test) are real defects and should be fixed, but
repairing §3.1 widens the lane on a different axis and by an unmeasured amount. Recommend a
separate adjudication rather than smuggling it in behind this one. Whatever is decided, §3.3
should be fixed with it — a test that pins a field production never sets is not a guard.

---

## §6 — Constraints honored

- **No buy-lane membership change.** Nothing in this packet touches `hk_cascade_eligible`,
  `hk_entry_ok`, or the staged pool — era-break territory per #4470's law, untouched.
- **washout_watch not widened.** No engine change was made. This packet is measurement and a
  recommendation; membership is unchanged pending ratification.
- **Governance checked.** `research/DO_NOT_REBUILD.md` (all three washout rows read; see §5.3),
  `docs/ACTIVE_BUILD_MAP.md`
  (no open lane owns `engine/hk_washout_watch.py`; #4605 is theme-tape baskets, #4473 is the
  HK vetoed/ran anchor, #4393 is China Prophet), and an open-PR search for `washout_watch`
  returned empty.

## §7 — Reproduce

```bash
python3 research/hk_washout_coverage/washout_coverage_packet.py
```

Reads committed snapshots from git history and `data/hk_stocks/`; writes
`washout_coverage_results.json`. Self-validates the RSI recompute against published values and
prints a loud failure if it disagrees. Computes nothing, writes no ledger, touches no board.

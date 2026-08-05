# Adjudication — HK washout_watch vs the cycle ladder's BOTTOM WATCH cohort

**Date:** 2026-08-05 · **Scope:** `engine/hk_washout_watch.py` selection rule, display-tier only
**Status:** MEASURED — awaiting operator ratification. Nothing shipped; no lane membership changed.
**Receipts:** `research/hk_washout_coverage/washout_coverage_packet.py` → `washout_coverage_results.json`

---

## §0 — The decision being asked for

The HK board's cycle ladder marks some names **BOTTOM WATCH** (display label `NEARING A LOW`).
Half of that cohort reaches **none of the board's curated lanes** — not buy, watch, laggards,
leaders, ran, vetoed, or washout_watch. The operator is asked to rule on one question:

> **Should `engine/hk_washout_watch.py` admit a ladder BOTTOM WATCH name as a washout
> candidate on the strength of its ladder label alone?**

**Scope of the word "invisible" in this packet:** absent from the curated lanes, *not* absent
from the page. `templates/hk.html.j2:4602` renders `hk_scoreboard.modes.all` as the Global-risk
screener — "the full HK list" — so all 156 names, these included, are on the surface with their
data. What the cohort lacks is a lane that says anything about the state the ladder just
assigned it. That is the gap; it is a real one, and it is narrower than "these names vanish."

Recommendation is in §5 (**Option B**, one-line change, display-tier, +2.1 rows/night).

Two further defects surfaced along the way and are reported but **not** proposed here: a
candidacy criterion that has never been able to fire (§3.1 — repairing it is Option C, which
admits 44 names and belongs in its own ruling), and the test that let it stay dark (§3.3).

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
- The three readers of `tech["ma200"]` in the repo — `scripts/build_hk_library.py:1195` and
  `engine/hk_washout_watch.py:414`, `:619` — all read a key no producer emits, sitting next to
  one that holds the answer.

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
| …already in `washout_watch` | 17 |
| …in some other lane, but not `washout_watch` | 2 |
| …in **no** curated lane | **19 (50.0%)** |
| **Option B's lane delta** (cohort not already in `washout_watch`) | **21** |
| washout_watch name-days | 166 |
| …labelled `NEARING A HIGH` | **70 (42.2%)** |
| …labelled `NEARING A LOW` | **17 (10.2%)** |
| rows carrying a non-null `dist_200dma` | **0 of 166** |

**The two denominators are different and it matters.** 19 is the coverage gap being adjudicated.
**21** is what Option B costs, because it admits *every* cohort name as a candidate — including
the 2 name-days (0285.HK, 2026-07-24 and 07-27) that were visible in `laggards` but not in
`washout_watch`. The lanes overlap; 62 of the 166 washout rows also sit in another lane. Costing
this change at 19 would understate it.

The cohort churns nightly (per-day gap ranges 0/2 to 5/8), so any single-date receipt expires.
The 50% figure is the stable one.

### 2.3 The lane does not currently mean what its name says

On 2026-08-05 the **washout** lane was 11/16 `NEARING A HIGH` and 1/16 `NEARING A LOW`; four rows
were `chase_risk` at RSI 73–77. Over 10 dates it is 42% names near highs, 10% names near lows.
Admission is dominated by `SB_ACCUM` (southbound accumulation, `accum_z >= 0.3` — 10 of 16 rows
on 08-05), a low bar that names at highs clear easily. **Whatever dilution concern applies to
this proposal already exists in the lane, pointing the other way.**

---

## §3 — Root cause

### 3.1 The dead criterion — `dist_200dma` never populated

Diagnosed in §1: the builder asks for `tech["ma200"]`, which nothing emits, while the producer
publishes the same quantity as `pct_vs_200dma` in percent units.

The blast radius is wider than this one organ. The same `None` silently disables `_above_200_by`
at `scripts/build_hk_library.py:2205` — `None` for every name — which flows into
`build_hk_core_rows(above_200_by=...)`. Anything downstream reading "is this name above its
200-day line" from that snapshot has been reading a null for as long as the key has been wrong.

### 3.2 The band misalignment — candidacy stops where the reclaim signal starts

With `dist_200dma` dead and `NEARING A LOW` containing none of the label keywords the code
looks for (`DECLINE`, `FALL`, `DOWNTREND`, `BEAR`), candidacy for these names rests entirely on
`RSI <= 40` (`RSI_OVERSOLD`) or the `cycle_blocked` flag. But the confluence signal that would
admit them, `RSI_RECLAIM`, fires on `30 <= RSI <= 50`.

**The 10-point band (40, 50] can earn a confluence signal but is never asked for one** — unless
some *unrelated* route lets the name in anyway (`cycle_blocked`, or a `DOWNTREND` label, the one
ladder value that happens to match a candidacy keyword).

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
| Lane size (08-05) | 16 → **60 (38% of the board)** | 16 → **18** | 16 → **33 … 60** |
| Mean lane size / night | — | **16.6 → 18.7 (+2.1)** | — |
| Rescues the cohort? | yes, incidentally | **≥18 of 19** (lower bound, see below) | 12 of 19 name-days |
| Collateral | 29 `BOTTOMING` + 10 `UNCONFIRMED TURN` + 2 `UPTREND` + 1 `BUY ZONE` | none — targets the cohort exactly | 49 names clear −12%; only **2** are `NEARING A LOW` (19 `BOTTOMING`, 10 `BUY ZONE`, 9 `UNCONFIRMED TURN`, 5 `NEARING A HIGH`, 4 `UPTREND`) |

**On Option C's lane range.** 44 names become *candidates*; how many *render* depends on
confluence. 17 of them clear the ≥1 bar on the RSI organ alone (they sit in the reclaim band),
so the lane goes to **at least 33**; the rest render if any of the five other organs fires, with
60 as the ceiling. The honest figure is a range, not a point.

**Option A is a bad trade**: it buys 2 BOTTOM WATCH names at the cost of 44 new rows, and destroys
what the lane means.

**Option C is the honest repair of §3.1, and it is not cheap.** It is small in *code* — the value
already exists as `pct_vs_200dma` — but 49 of 156 names clear the −12% line today, so it admits
**44 new candidates, the same magnitude as Option A**. Only 2 of those 49 are `NEARING A LOW`:
the −12% route selects on price alone, independent of the ladder, so it is a different organ from
the one this ruling is about. It also carries the 100× unit trap from §1 — the un-converted form
admits **98 of 156 names (63% of the board)**. Worth doing, on its own evidence, in its own PR.

**Dilution under Option B:** the lane's `NEARING A LOW` share rises from 10.2% to about **20%**
(`(17+21)/(166+21)`), against a 42% `NEARING A HIGH` share. The proposal moves the lane *toward*
its name, not away.

---

## §5 — Recommendation

**Adopt Option B**, display-tier only, as a one-line addition to `_is_washout_candidate`: treat
the ladder's BOTTOM WATCH state as a fourth candidacy route, alongside the existing three.

Why this one:

1. **It is the smallest change that closes the gap** — +2.1 rows/night, targeted at the exact
   cohort, no collateral admissions.
2. **It makes no buy claim.** Candidacy only earns a name the right to be *scored*;
   `_assign_state` still requires ≥1 real confluence signal, so a BOTTOM WATCH name with no
   evidence still does not appear. It does not touch rank, size, or gate, and
   `display_only: True` already governs every row.
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

### ⚠️ The one thing this ruling must decide besides visibility: the forward ledger

**Option B is not display-only in its effects, and an earlier draft of this packet wrongly said
it was.** `engine/hk_washout_watch.py:776` calls `stamp_ledger()` on *every* row `compute()`
returns, appending to `data/hk_impulse/washout_watch_ledger.jsonl` — a **tracked, committed**
file (343 rows, 18 dates, 2026-07-10 … 08-05, 0 graded so far). Admitting the cohort changes
**which names accrue into the organ's own forward record**, i.e. the population its future track
record will be measured on.

The row schema (`engine/hk_washout_watch.py:175-192`) carries **no era, rule-version, or
admission-reason field**, so once mixed, the pre- and post-change admission regimes cannot be
separated except by date. That is the standing era-break shape: an admission-rule change
mid-ledger with nothing stamped to mark it.

**This needs an explicit decision, not an assumption.** The options, cheapest first:

- **Stamp an era field** on new rows (e.g. `admission: "ladder_label"` vs `"legacy"`) and leave
  history intact — preserves gradeability on both sides, and is the one I'd recommend.
- **Break the ledger** at the change date and grade the two regimes separately.
- **Admit for display but not for the ledger** — cleanest epistemically, but it means the newly
  visible names never accrue evidence, which defeats the point of surfacing them.

Ratifying Option B without picking one silently chooses the third-worst outcome: a mixed ledger
that looks continuous and isn't.

### What "≥18 of 19" does and does not mean

The rescue figure is measured on the **RSI organ alone** — 18 of the 19 gap name-days sit in the
reclaim band, so they render on that signal by itself. It is a **lower bound**, not a count: the
other five organs (`SB_ACCUM`, `ADR_GAP_UP`, `BEAR_EXHAUST`, `BUYBACK`, `NARRATIVE`) can only add.

An earlier draft claimed the 19th name (0669.HK, 07-28, RSI 53) "would still not appear — it
earns no confluence signal." **That claim was wrong and is withdrawn.** It was never measured:
0669.HK carries `SB_ACCUM` in the committed 08-05 lane, and `SB_ACCUM` fires at the low bar of
`accum_z >= 0.3` — the signal behind 10 of 16 rows that night. Historical per-date southbound
state is not reconstructable from committed artifacts, so whether it fired for 0669.HK on 07-28
is **unknown**, not "no".

For the current board the full six-organ measurement is in the receipts: all three cohort names
on 2026-08-05 clear the bar, the two gap names (9926.HK, 0345.HK) each on `RSI_RECLAIM`.

**Also worth the operator's eye:** two names carried `NEARING A LOW` while trading *above* their
200-day line — 1347.HK at +24.7% and 0669.HK at +19.3%, each measured on the date it held that
label (08-04 and 07-28 respectively). The ladder is a cycle read, not a price-vs-MA read, so this
is not necessarily wrong — but it is the kind of divergence the basing shelf's copy ("still
falling, but working on a base") does not describe, and it is worth a look.

### Not in this ruling

§3.1 (dead `dist_200dma`) and §3.3 (vacuous test) are real defects and should be fixed — but
§3.1 is Option C, and §4 measures it at **+44 candidates**, the same magnitude as Option A.
It selects on price alone and reaches a mostly different population (only 2 of its 49 names are
`NEARING A LOW`). That is a separate organ with a separate cost, and it carries the 100× unit
trap; it deserves its own PR and its own ruling rather than being smuggled in behind this one.
Whatever is decided there, §3.3 should be fixed with it — a test that pins a field production
never sets is not a guard, and it will keep the repaired criterion honest.

---

## §6 — Constraints honored

- **No buy-lane membership change.** Nothing in this packet touches `hk_cascade_eligible`,
  `hk_entry_ok`, or the staged pool — era-break territory per #4470's law, untouched.
- **washout_watch not widened.** No engine change was made. This packet is measurement and a
  recommendation; membership is unchanged pending ratification.
- **Forward ledger untouched.** `data/hk_impulse/washout_watch_ledger.jsonl` is unchanged by
  this PR — the measurement script never calls `stamp_ledger()` and writes only under
  `research/`. The ledger *consequence* of adopting Option B is disclosed in §5 as a decision
  the operator must make, not a side effect taken on their behalf.
- **Governance checked.** `research/DO_NOT_REBUILD.md` — all three washout rows read; they kill
  signal constructions, not display homes (§5, point 3). `docs/ACTIVE_BUILD_MAP.md` — no open
  lane owns `engine/hk_washout_watch.py` (#4605 is theme-tape baskets, #4473 is the HK
  vetoed/ran anchor, #4393 is China Prophet). An open-PR search for `washout_watch` returned
  empty.
- **On the W-E sibling.** `ACTIVE_BUILD_MAP.md:29` lists **#4609** ("basing shelf for BOTTOM
  WATCH…") as an open lane on this exact topic. It is **not** open — `gh` reports it MERGED at
  2026-08-05T14:03:29Z, as is its HK port #4631 (merged mid-session, `79a13db838a`). The build
  map row is stale, not a live collision. Verify state with `gh` rather than the map alone.

## §7 — Reproduce

```bash
python3 research/hk_washout_coverage/washout_coverage_packet.py
```

Reads committed snapshots from git history and `data/hk_stocks/`; writes
`washout_coverage_results.json`. Self-validates the RSI recompute against published values and
prints a loud failure if it disagrees. Computes nothing, writes no ledger, touches no board.

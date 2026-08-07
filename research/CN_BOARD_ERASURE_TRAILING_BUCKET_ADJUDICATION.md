# CN Prophet board — a published pick can be UN-published by the trailing bucket

**Date:** 2026-08-07 · **Trigger:** operator, "We had 300363 yesterday on China Prophet board.
But today its suddenly gone." · **Status:** measured; fix HANDED to the in-flight session-anchor
program (see §6), no competing gate change proposed here.

---

## §0 What happened, in one paragraph

`300363.SZ` 博腾股份 was the **#1 name on the 2026-08-05 board** — prophet 90.32, `featured`,
`partial` entry, buy zone 16.52–17.60 (operator screenshot and the committed artifact agree).
On the 2026-08-06 board it was **absent from all seven lanes** with no departure notice. On
2026-08-07 it closed **20.44, +20.02%** — the ChiNext limit-up cap. The pick itself was never
lost: the keep-first PIT ledger holds it and grades it independently of the live board (§3).
What was lost was the operator's line of sight on a live pick, for one session, silently.

---

## §1 Receipts

| | 2026-08-05 board | 2026-08-06 board |
|---|---|---|
| lane | `buy` / featured | — absent from all 7 lanes — |
| `score_rank` | **1** | — |
| prophet score | 90.32 (signal 1.0, entry 0.9, runway 0.94, reversal 1.0) | — |
| signal | `eligible: True`, T2/shallow, `ticks: 0` | `eligible: False`, no tier |
| gate reason | — | `buy blocked by filter: counter-trend, no 200-reclaim/hold` |

Reproduced by replaying `engine.signal_gate.gate()` on the same price parquet truncated at each
date, **on `3b19189d17d` — the revision that actually built those two boards**:

```
as-of 2026-08-04   eligible=True   tier=T2   ticks=0    buyable=True
as-of 2026-08-05   eligible=True   tier=T2   ticks=0    buyable=True
as-of 2026-08-06   eligible=False  tier=None ticks=11   buyable=False
```

Price: 08-04 **+13.58%** → 17.73 · 08-05 −0.73% → 17.60 · 08-06 −3.24% → 17.03 ·
08-07 **+20.02%** → 20.44. The −3.24% bar is *not* what removed it (§2).

---

## §2 Mechanism — bucket COMPLETION, not bin phase

`confluence_tiers._to_daily()` stamps each timeframe bucket's value onto the daily bar equal to
that bucket's **known-date** (its last session). The trailing bucket is **incomplete**, so its
known-date advances every session while the bucket stays open:

```
3D bucket 2026-08-04 → known 2026-08-05     (run of 08-05)
3D bucket 2026-08-04 → known 2026-08-06     (run of 08-06)   ← same bucket, pointer moved
```

The 2D cross event stays pinned to its own (closed) bucket at 08-05, but `recent3_d` at the
08-05 bar now forward-fills from the **previous** 3D known-date (08-03, `False`) instead of its
own bucket (`True`). The T2 conjunction `mb2_d & recent3_d & confirm3 & rsi_ok`
(`confluence_tiers.py:467`) therefore **un-fires on a bar that already printed**. The last
surviving T2 event falls back to **2026-06-16** — 19 2D-ticks against `FRESH_TICKS = 2` — the
tier clears, and the only remaining signal is the 3D master marker of 06-23, which is a *block*.
That is why it left `watch` too, not just the featured shelf.

**The underlying signal never changed.** The 3D StochRSI cross-up on that bucket reads
`xup=True, recent3=True` in **both** runs. Only the daily-grid annotation moved. Counterfactual
on a stable bucket grid: 2D ticks since the cross = 1 ≤ 2 and `recent3` = True → **T2 still
ACTIVE on 08-06**; the name would have stayed on the board.

### §2.1 The anchor repair does NOT close this

PRs **#4732 / #4799** (era `abs-session-2026-08-06`, merged 2026-08-07 00:11 and 00:17 — *after*
the 08-06 board was built at 08-06 06:06) re-anchored the 2D/3D grid to the absolute session
calendar. That fixed bin **PHASE** — the grid no longer moves with loaded history depth. It did
not change bucket **COMPLETION**: verified directly on 300363.SZ under the new anchor, the
trailing bucket's known-date still advances 08-05 → 08-06, and `_to_daily` is unchanged.

Census on `origin/main` **after both PRs**, full CN universe (1,850 names), trailing 12 sessions:

> **86 erasure events across 78 names.** Lumpy by date (48 on 07-24, 17 on 07-28, 10 on 07-30,
> then 1–4/session) — consistent with a trailing bucket rolling over and de-annotating many
> names at once.

**These are two distinct invariance properties.** The suites #4800 is wiring test invariance to
*loaded history depth*. Nothing yet tests invariance to *bucket completion* — that a bar's
annotation, once printed, never changes. That is the gap.

---

## §3 The record was NOT lost — this is bookkeeping-safe

`data/china_standout_track/board.parquet` is keep-first PIT on `(date, ticker,
board_definition)` and holds the pick in full:

```
date 2026-08-05 · ticker 300363.SZ · board_rank 1 · board_definition cn_prophet_v2
lane featured · prophet_score 90.32 · tier T2 · entry_status partial · level 17.6
fill_basis t1_hl2 · fwd_mfe_5/10/21 = null (not yet matured)
```

`china_standout_track.grade()` matures rows straight off that store and never consults the live
board, so **an erased name still grades**. Verified across the whole transition: of the 8 names
that left the 08-05 buy shelf, **8/8 are in the PIT ledger**. Nothing needs backfilling.

### §3.1 The honest record of that shelf

Full 08-05 `cn_prophet_v2` buy shelf, n=17, on the ledger's own basis (fill = 08-06 HL2
`t1_hl2`, mark = 08-07 close) — winners and losers together, so this is not an
incomplete-history artifact:

| cohort | n | mean | median | win | best |
|---|---|---|---|---|---|
| whole shelf | 17 | +1.99% | +0.58% | 71% | +17.61% |
| **left the board** | 8 | +2.48% | **−0.14%** | 50% | **+17.61%** (300363) |
| stayed | 9 | +1.56% | +1.15% | 89% | +4.35% |

**300363 on the house fill basis = +17.61%** (17.38 → 20.44), not +20.02% — the +20.02% is the
raw session change from the 08-06 close, which no rule fills at.

**Do not read "departures beat stayers" out of this.** The departure cohort's *median* is
negative and its win rate is 50% vs 89%; the mean is carried entirely by one name. n=8 on a
single transition decides nothing in either direction.

---

## §4 Blast radius on the transition in question

Measured on `3b19189d17d` (the revision that built those boards), 08-05 → 08-06:

- 288 board names → 245. **85 left entirely**, including **8 of the 17 buy-lane names**.
- Of the 42 that lost buyability: **40 aged out normally** — event date UNCHANGED, tick count
  simply advanced past `FRESH_TICKS`. That is the shelf working as designed.
- **2 were erased**: `300363.SZ` and `300059.SZ` 东方财富 (rank 33, prophet 79.50), both from
  the buy shelf. 300059 went on to −0.15% — the erasure is not systematically costly, which is
  precisely why it needs a detector rather than an anecdote.

Discriminator (use this, not the tick count):

```
event(D') <  event(D)   → ERASED    — a past event un-fired      (defect)
event(D') == event(D)   → AGED OUT  — tick counter advanced      (by design)
```

---

## §5 What shipped here

`scripts/research/cn_board_erasure_census.py` — full-universe census implementing the §4
discriminator, market-calendar correct (`session_anchor.market_for_ticker`; a bare
`_tf_bars(c, n)` defaults to the **US** calendar and buckets A-shares on the wrong grid
entirely — that mistake makes the census measure nothing). Emits a line-start
`::warning title=cn-board-erasure::` so a nightly wiring cannot fail silently.

Zero authority: reads price parquets, ranks/gates/sizes nothing.

---

## §6 Handoff — the fix belongs to the session-anchor program

An active fleet-wide lane already owns this surface (#4833, #4800, #4799, #4756, #4754, era
`abs-session-2026-08-06`). **No competing gate change is proposed here.** The residual defect
and the two candidate repairs, for that program to adjudicate:

1. **Latch (preferred).** Persist the daily-grid leg annotations PIT, so a bar's value is
   written once — when that bar *was* the trailing bar, computed from data ≤ that bar — and is
   immutable thereafter. No lookahead (the latched value used only data available at the bar)
   and no repaint. Cost: a small per-ticker PIT store; makes the engine stateful, so the store
   must be committed like the other PIT stores here.
2. **Complete-buckets-only.** Annotate from closed buckets only. Eliminates repaint outright but
   delays every signal by up to n−1 sessions, forfeiting the same-day firing the shelf is built
   on. Admission-tier — needs the gauntlet and a shadow race.

Either way this is a **gate** change: it alters which names are admitted on which bars, so it
promotes through a parallel shadow definition against live, per the existing R-slate /
`cn_prophet_v2_shadow` pattern — not a direct flip.

**Test the program is missing:** bucket-completion invariance — for a fixed history, the
annotation of bar *d* must be identical whether the series ends at *d* or at *d+k*. Sibling of
the history-depth invariance suites #4800 is wiring, and not implied by them.

---

## §7 Fences

- Display/record tier only. Nothing here ranks, gates or sizes.
- The +20.02% is a raw session change; the executable house number is **+17.61%** (§3.1).
- Cohort statistics in §3.1 are n=17 on one transition — descriptive, not evidence about the
  departure rule in either direction.
- `data/china_prophet_rank/candidates.parquet` @ `stamp_date 2026-08-05` records 300363 as
  `not_raw_eligible, score 44.07, rank 367`, contradicting both the published board and the
  grading ledger (7 control names from the same shelf match that store byte-for-byte). Keep-first
  cannot protect a key never written, so a late/backfilled write can land a post-erasure verdict
  under an old date and stick. **Reconstruct what a board showed from the rendered
  `site/factordata/china_standouts.json` at the commit, never from the rank store.** Not
  adjudicated here — flagged for the store's owner.

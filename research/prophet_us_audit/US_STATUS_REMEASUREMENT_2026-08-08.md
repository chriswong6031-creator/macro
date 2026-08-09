# Prophet US — entry-status re-measurement (the ladder's evidence loop) — 2026-08-08

**Charter:** `PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.6 — the US answer to CN §2.3,
run over the US board's own graded episodes. Sibling receipts:
`CN_US_PROPHET_PARITY_ANATOMY_2026-08-07.md`, `ENTRY_LATENESS_FORENSIC_2026-08-07.md`.

**Tier: ops telemetry. ZERO AUTHORITY.** Nothing in this file changes a rank, a gate, a size
or a board. The A2 entry-value constants are revised by an operator reading a table, and this
is the table. Instrument: `research/prophet_us_audit/status_remeasurement.py` →
`status_remeasurement_results.json`; the same code ships as the nightly
`entry_status_scorecard` block, so the receipt and the nightly cannot disagree about what a
loser rate is.

## Headline

**The CN ordering is not reproduced by the US record — and the horizon where the patience
thesis makes its claim has no US data at all.**

On the admitted (buy) lane at H=5, with every cell above the 20-mark floor:

- `bounce_wait` — **54.9% loser rate** (95% Wilson 47.0–62.6%), median excess **−0.96%**
  (n=153). CN measured 6.9%.
- `buy_now` — **39.0% loser rate** (95% Wilson 29.8–49.0%), median excess **+1.05%** (n=95).
  CN measured 30.0%.

That is the v1 constants' ordering read backwards: the status those constants scored **1.0**
is the worst non-thin cell in the window, and the status they scored **0.7** is the best. The
spread is not subtle (15.9 points of loser rate, 2.0 points of median excess), neither cell
is thin, and the two intervals do not overlap.

**Ruling (§6.6):** the A2 entry leg ships **status-neutral** — one flat value across the five
admissible statuses. An unreproduced ordering does not get to keep its ranks. An ordering may
be re-introduced only at the ladder's chartered horizon, with n≥50 per cell, sign-stable
across two half-splits, on era-stamped `anticipation-v1` episodes.

**Read the two cells' windows before reading their gap.** `bounce_wait` is a **late-window
cohort**: it has zero buy-lane episodes before **2026-07-17** and 205 after it, over 8 board
dates, while `buy_now` spans all 18 dates from 2026-06-18. The two rates are therefore
measured over different tape, which is a confound the gap alone cannot survive — see
*What this does NOT establish* §6. The nightly block prints `as_of_first`/`as_of_last` on
every cell so this is visible at a glance rather than reconstructed.

**And the null that matters more than either number:** `bounce_wait` has **zero graded marks
at H=21**, in every lane, out of 345 episodes. The patience case is "these names take time" —
so the horizon that would test it is exactly the one carrying no observations. H=63 has never
matured for any status. This table cannot yet speak to the claim the constants encode; what
it can say is that at 5 and 10 sessions the US board's `bounce_wait` rows have not behaved
like CN's.

## What was measured

| | |
|---|---|
| Source | `data/us_board_ledger/retro_grades.parquet` (US board retro grade ledger) |
| Ruler | `engine.grading.forward_metrics` via `scripts/grade_us_board.py` — next-bar fill, positional session horizons, excess vs SPY. **Nothing regraded here** |
| Status | `entry_status` = `entry_signal.assess()["status"]` snapshotted on the board-admission day, not re-derived |
| Episodes | 3,313; **2,816 carry a status (85.0%)** — an episode with no status is excluded, never bucketed |
| Window | 23 board dates, **2026-06-15 → 2026-07-30** |
| Horizons present | 5, 10, 21 sessions. **H=63: zero matured marks** |
| Lanes | buy 1,939 · watch 883 · laggards 446 · leaders 45 — **never pooled** |
| loser | `excess_spy <= 0` — a flat mark counts as a loss (CN §2.3 convention, kept verbatim so the two tables are comparable) |
| thin | fewer than 20 graded marks; marked `*` and read as **directional only** |

Status population: hold 465 · extended 413 · await_confluence 398 · buy_soon 355 ·
bounce_wait 345 · partial 202 · wait_pullback 184 · blocked 178 · buy_now 129 · watch 73 ·
topping 61 · exit 13.

## Buy lane — the admitted cohort, the one the map governs

| entry status | H=5 n | H=10 n | H=21 n | H=5 loser | H=10 loser | H=21 loser | H=5 med excess | H=10 med excess | H=21 med excess |
|---|---|---|---|---|---|---|---|---|---|
| `bounce_wait` | 153 | 52 | — | 54.9% | 65.4% | — | -0.96% | -2.74% | — |
| `wait_pullback` | 72 | 33 | 17* | 52.8% | 42.4% | 52.9% | -0.23% | +0.72% | -0.49% |
| `hold` | 255 | 67 | 36 | 51.0% | 37.3% | 61.1% | -0.10% | +1.47% | -1.44% |
| `extended` | 64 | 18* | 3* | 56.2% | 50.0% | 33.3% | -0.86% | +0.25% | +0.84% |
| `buy_now` | 95 | 18* | 3* | 39.0% | 61.1% | 0.0% | +1.05% | -3.26% | +13.64% |
| `partial` | 148 | 38 | 5* | 52.0% | 42.1% | 60.0% | -0.29% | +0.82% | -0.65% |
| `buy_soon` | 113 | 33 | 15* | 47.8% | 33.3% | 46.7% | +0.12% | +2.53% | +0.50% |
| `await_confluence` | 99 | 92 | 38 | 46.5% | 37.0% | 44.7% | +0.30% | +1.67% | +1.42% |
| `blocked` | 7* | 5* | — | 57.1% | 60.0% | — | -1.77% | -6.59% | — |
| `topping` | 5* | 1* | — | 60.0% | 0.0% | — | -1.07% | +1.81% | — |
| `watch` | 11* | 1* | — | 36.4% | 100.0% | — | +0.75% | -3.79% | — |

`*` = thin (< 20 marks), directional only. `—` = no matured mark.

Read at H=10 the picture changes shape but not direction: `bounce_wait` goes to **65.4%**
(n=52, still above the floor) while `buy_now`'s 61.1% sits on **n=18** and is thin. The one
cell that holds up across both horizons at real n is `await_confluence` (46.5% / 37.0% on
n=99 / n=92) — a status the v1 constants scored 0.45 and neither the US nor the CN ordering
paid much attention to. It is also the widest-window cell in the table (2026-06-30 → 07-30
at H=5), which is part of why it holds up.

## Watch lane — the pre-admission population

| entry status | H=5 n | H=10 n | H=21 n | H=5 loser | H=10 loser | H=21 loser | H=5 med excess | H=10 med excess | H=21 med excess |
|---|---|---|---|---|---|---|---|---|---|
| `bounce_wait` | 76 | 34 | — | 55.3% | 55.9% | — | -0.92% | -0.61% | — |
| `wait_pullback` | 26 | 10* | 5* | 57.7% | 30.0% | 60.0% | -0.98% | +3.27% | -1.63% |
| `hold` | 46 | 22 | 11* | 60.9% | 40.9% | 81.8% | -0.93% | +1.66% | -3.26% |
| `extended` | 70 | 41 | 12* | 48.6% | 26.8% | 50.0% | +0.20% | +3.07% | -0.15% |
| `buy_now` | 5* | 4* | 1* | 60.0% | 75.0% | 0.0% | -0.54% | -5.54% | +22.24% |
| `partial` | 7* | 4* | — | 57.1% | 0.0% | — | -0.12% | +2.10% | — |
| `buy_soon` | 77 | 47 | 26 | 50.6% | 38.3% | 42.3% | -0.06% | +2.16% | +1.06% |
| `await_confluence` | 75 | 47 | 15* | 56.0% | 25.5% | 26.7% | -0.92% | +3.40% | +1.41% |
| `blocked` | 82 | 30 | 18* | 52.4% | 33.3% | 50.0% | -0.25% | +2.90% | +0.48% |
| `exit` | 6* | 1* | — | 50.0% | 0.0% | — | +0.26% | +2.65% | — |
| `topping` | 11* | 3* | — | 72.7% | 33.3% | — | -3.99% | +2.77% | — |
| `watch` | 30 | 17* | 8* | 46.7% | 29.4% | 12.5% | +0.66% | +4.09% | +11.47% |

The watch lane repeats the buy lane's `bounce_wait` reading (55.3% / 55.9% on n=76 / n=34) on
an independently selected population. That the two lanes agree is the strongest thing this
receipt has: it is the same status behaving the same way twice, not one cohort's accident.

**laggards and leaders lanes** are in `status_remeasurement_results.json` in full. Every
non-`extended` cell in them is thin; the leaders lane has 45 episodes at H=5 only and reads
85–100% loser across every status, which is a statement about the lane, not the statuses.

## Side by side with the CN measurement that shipped the v1 constants

| entry status | CN loser rate (H=10, n=257, CSI300-rel) | US buy lane (H=5) | US buy lane (H=10) |
|---|---|---|---|
| `bounce_wait` | 6.9% | 54.9% (n=153) | 65.4% (n=52) |
| `wait_pullback` | 7.7% | 52.8% (n=72) | 42.4% (n=33) |
| `hold` | 19.4% | 51.0% (n=255) | 37.3% (n=67) |
| `extended` | 29.8% | 56.2% (n=64) | 50.0% (n=18*) |
| `buy_now` | 30.0% | 39.0% (n=95) | 61.1% (n=18*) |
| `partial` | 41.4% | 52.0% (n=148) | 42.1% (n=38) |
| `buy_soon` | 46.7% | 47.8% (n=113) | 33.3% (n=33) |

These are **not the same measurement**: different market, different benchmark, different
selection upstream, and CN's column is H=10 against a US column that is strongest at H=5.
The comparison is here because those CN numbers were the stated basis for the v1 US
constants that this measurement retired — not because the two columns are interchangeable.

## What this does NOT establish

1. **Same status name, different upstream animal.** US `bounce_wait` is assigned by the
   COUNTERTREND BOUNCE demotion (`engine/entry_signal.py:185`) to names inside a downtrend.
   CN's `bounce_wait` cohort is fed by a weekly ripening shelf and a theme-timing channel the
   US board does not have (parity anatomy, 2026-08-07). Two boards can hand the same label to
   two different populations, and this table cannot tell them apart.
2. **The window is one regime.** Six weeks, 23 board dates, one market. A loser rate near 50%
   across nearly every status at H=5 is the tell: at five sessions this ledger is mostly
   measuring the tape, not the status.
3. **The patience horizon is empty.** Zero `bounce_wait` marks at H=21 and zero marks of any
   status at H=63. The claim "these names need time" is untested here, not answered.
4. **The anticipation era contributes nothing yet.** Every episode predates the §6.2 selection
   change, and the ledger's last date is 2026-07-30 (the nightly freeze; heal in flight). The
   rows that would test the new selection do not exist.
5. **It is not a mandate to revert the map.** Operator ruling §6.0 is that the new selection
   ships live while the legacy shadow ledger accrues; this block is display-tier with zero
   authority and is an input to that comparison, not a substitute for it.
6. **The status cohorts do not share a window.** Statuses entered the buy lane on different
   dates, so a rate compared across two of them can be a comparison of two stretches of
   tape. Buy-lane episode spans: `bounce_wait` **2026-07-17 → 07-30 (8 dates, 0 episodes
   before 07-17)**, `await_confluence` 2026-06-30 → 07-30 (14), and `hold` / `buy_now` /
   `buy_soon` / `partial` / `wait_pullback` / `extended` 2026-06-18 → 07-30 (14–18). The
   headline gap is between the narrowest cohort in the table and one of the widest. This
   does not restore the CN ordering — it means the US record has not cleanly tested it
   either way, which is the same reason the leg ships neutral. Per-cell `as_of_first` /
   `as_of_last` in the nightly block is the standing disclosure; the re-introduction bar's
   two-half-split condition is what would close it.

## What would make the reading trustworthy

- `bounce_wait` marks at **H=21 and H=63** — the horizons the thesis actually claims.
- Anticipation-era rows (`selection_era: anticipation-v1-2026-08-08`) accruing beside the
  legacy shadow ledger, so the status cohorts can be read within one selection regime instead
  of across two.
- **Overlapping windows.** Enough dates that `bounce_wait` and the statuses it is compared
  against are measured over the same tape, and enough of them to split the window in half and
  check the sign twice.
- A second regime. Six weeks that includes no meaningful drawdown cannot separate "this
  status is early" from "this tape rewarded chasing".

Until then the leg stays neutral and the nightly `entry_status_scorecard` block prints these
cells every night with their n, their Wilson bounds, their marked date ranges, their thin
labels and their nulls — so the ladder stops being a Chinese measurement wearing an American
map and becomes a series someone can watch move, against a re-introduction bar that was
written down before the numbers arrived.

## Provenance

- Instrument: `research/prophet_us_audit/status_remeasurement.py` (reads only; recomputes
  nothing) → `research/prophet_us_audit/status_remeasurement_results.json`.
- Shared implementation: `engine/us_entry_status_remeasure.py`, published nightly as
  `entry_status_scorecard` in the miss-audit artifact by `engine/prophet_miss_audit.py`.
- CN comparison column: `research/cn_prophet_audit/v1_loser_audit_results.json` (2026-08-04),
  `v2_featured_gate_retro.by_entry_status`, n=257 matured CN episodes.
- **Charter deviation, stated:** §6.6 named the W7 full-population store
  (`data/us_prophet_rank`) as the source. Measured 2026-08-08, it cannot answer the question —
  its `grades/` subtree has never been written (zero forward marks; the miss-audit forward log
  records `priority_score_available: false` on every row to date) and its `candidates/` store
  carries no entry-status column, only the already-mapped, non-injective `prophet_entry` leg,
  on the buy lane only (~2% of rows). Reading a mapped value to re-derive the map is circular.
  The board ledger is also the closer CN parity match: CN §2.3 measured board **admissions**,
  not a full-population context store. When a sibling lane stamps `entry_signal.status` into
  the W7 candidates store, that store becomes a second and wider read of the same question —
  not a replacement for this one.

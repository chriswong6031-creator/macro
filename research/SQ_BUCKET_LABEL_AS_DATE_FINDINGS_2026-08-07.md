# The 3D bucket LABEL is not the bucket's AS-OF — open findings, 2026-08-07

Status: **open, not repaired.** Written while healing `tests/test_hk_board_ui.py` on a red
`origin/main` (PR "hk board: adjudicate the 9961.HK guard"). None of the repairs below are
in that PR, deliberately — see §4.

Charter: `research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md` (R-SQ1…R-SQ7),
era `sq-abs-session-2026-08-06`.

---

## 1. The shape

`engine/signal_quality._tf_grid` aggregates a daily series into N-session buckets:

```python
agg = (... .groupby(...).agg(close=("v", "last"),
                             open_date=("d", "first"), last_session=("d", "last")))
labels = pd.DatetimeIndex(agg["open_date"])
```

A bucket's **value** is its LAST close, so the bar's information is as-of
`last_session`. Its **label** is `open_date`, which R-SQ2 chose on purpose so a §7 marker
date is always a real traded bar of the series (the retired `resample("3B")` label was a
synthetic left edge that could land on a holiday).

Both choices are right. The defect is in the **consumers that read the label as if it were
the as-of date.** `_tf_grid` already returns `last_session` for exactly this purpose, and
`confirmation_date` already uses it correctly (`signal_quality.py:519-523`).

**This is NOT an R-SQ2 regression.** `git log -S` puts the weekly-join line at the module's
original commit (#530), and the retired 3B label sat ~2 sessions BEFORE the close it
carried too (measured 0941.HK: mean 1.87 sessions, 89% at ≥ 2). The join has always been
label-anchored. R-SQ2 only removed a truncation artifact that had been masking it at
certain as-of dates — see §3.

---

## 2. The sites, measured

Measured on `data/hk_search/closes_deep.parquet`, 157 names, series cut at 2026-07-31.

| # | Site | `signal_quality.py` | Disagreement label-join vs last-session-join | Reaches |
|---|---|---|---|---|
| A | `asof` published on every verdict | `:580` `str(idx[-1].date())` | **156 / 157 names backdated by 1 session.** ZERO names publish the tape's actual last session (2026-07-31); all 156 publish 2026-07-30. | every consumer that reads `asof` as data freshness |
| B | weekly leg `w_bull` | `:185` | **3.77 % of all bars** (8 871 / 235 317); flips published `weekly_bull` on **28 / 157** names at this as-of | `cb`, `cs` → the whole §7 marker stream; `weekly_bull` is a GATE (`hk_board_rank.py:582,760`, `us_board_rank.py:1178`, `prophet_doors.py:543`) |
| C | `rising2_on3` (2D→3D) | `:224` | **19.76 % mean, 21.52 % max** — the largest | `early` → `early_markers` (display-only advance warning) |
| D | `above200` (200-MA join) | `:187` | **0.30 % mean, 0.65 % max** | `above200` verdict; `_confirm_legs` reclaim leg |
| E | `fresh_breach_mask` consumer | `scripts/research/dump_breakdown_events.py:653` | mask determined by the bucket's LAST close, event fired at its OPEN label — up to 2 sessions early | breakdown event tape (genuine look-ahead) |

Not affected: the high/low band (`:236-240`, cut on `grid3.bucket` so label and value share
an as-of by construction) and `confirmation_date` (`:519-523`, already resolves through
`_bucket_last_session`).

### A is the operator-flagged item

R-SQ2's charter argues there is "no systematic freshness-window shift", but that argument
is made over `_ticks_since` / `_bars_since` only. `asof` is a third field reading the same
index and it was not covered. On this panel the shift is not partial — it is total.

### B is what emptied the HK leaders strip

`weekly_bull is True` is half the leaders admission gate. With the last-session join,
0941.HK and 9618.HK re-enter the strip, `leaders` / `ran` / `vetoed` all fill their caps
(15/15, 12/12, 12/12 — from 14/15, 3/12, 12/12), and every G1 witness lands in a lane.
Pinned as an executable known-defect in
`tests/test_hk_board_ui.py::test_no_cohort_member_currently_reaches_the_leaders_strip`,
which is written to FAIL when the repair lands.

---

## 3. Two traps that cost time here

**The old module is not a witness.** "Run the pre-era module, see if it agrees" is invalid:
its answer is a coin flip on the caller's slice phase. Same series, same cut, dropping one
leading row —

```
0941.HK cut=2026-07-31                  OLD last label 2026-07-31  w_bull=True
0941.HK cut=2026-07-31 drop 1 leading   OLD last label 2026-07-29  w_bull=False
0941.HK cut=2026-07-31 drop 2 leading   OLD last label 2026-07-30  w_bull=False
```

At this particular cut the final `3B` bin was a degenerate 1-session bin landing on Friday
07-31, which accidentally picked up the current week. That is the phase-dependence
R-SQ1/R-SQ2 exist to remove, not a semantic to restore.

**One as-of date is not a measurement.** The two joins can only differ when a Friday falls
in `(open_label, last_session]`, so the effect concentrates on Friday-terminating panels
and the DIRECTION is not systematic. Across all bars of all 157 names the split is
last-join-only-True 4 541 vs open-join-only-True 4 330 (ratio 1.05, symmetric). At
as-of 2026-07-31 the repair adds 13 names and removes 0; at as-of 2026-07-03 the identical
repair would have REMOVED 7. Report both directions across several as-of dates.

---

## 4. Why none of this shipped with the HK heal

The repair direction is right and has a strong precedent: `engine/canon.py:370,444` — the
golden oracle `golden_gate` pins 1:1 to the Terminal's `compute_signals` — already labels
buckets by `last["d"]` and joins the weekly on it, with the comment "leak-free (prior
CLOSED week)". `signal_quality` is the one that diverges.

It is nonetheless a **semantic revision, not a defect repair**, because R-SQ6 pins
`_confirm_legs` / `_buy_filter` semantics as "byte-identical", and `w_bull` feeds
`_confirm_legs`. Shipping it inside a CI heal would smuggle a charter-scoped change past
the discipline the charter asks for. What it owes:

1. **Fix B, C and D together, or none.** Fixing only `w_bull` leaves `_confirm_legs`
   (`:315`) reading `above200` at the bucket's open and `w_bull` at its close — two as-of
   dates in one boolean. A consistent stale frame beats a mixed one.
2. **Bump `ANCHOR_ERA`** (`signal_quality.py:56`, R-SQ3) so every artifact, brain leaf,
   `marker_integrity` cutover and ledger row can cohort correctly.
3. **Committed blast-radius report** (R-SQ4), as `reports/sq_anchor_blast_radius.md` was
   for the previous redraw. Measured so far on HK alone: 107/157 marker LISTS change,
   80/157 marker identities, 90/157 marker qualities; 0 markers change on or after
   `track_record.SQ_ANCHOR_ERA_FLOOR = "2026-08-06"`, so the ledger survives — by luck of
   the floor date, not by design. **US / CN / CA are unmeasured.**
4. **Disclose the new live-bar repaint channel.** Under the label join a bucket's join key
   is fixed when the bucket opens; under the last-session join `last_session` advances as
   the bucket fills, so a live bar's `w_bull` can flip mid-bucket. Closed buckets stay
   stable and the live 3D bar already repaints its close/macd/k/d, so this is acceptable —
   but it is a new repaint surface on a published field and `engine/provisional_replay.py`
   should be checked against it.
5. **Fix the stale docstring** at `:173` ("The W-FRI weekly leg … is deliberately
   untouched (R-SQ6)").

**Leak-free either way.** Both joins are safe; the repair is merely less conservative.
`.shift(1)` means each W-FRI bin carries the PRIOR week's value, so the newest weekly close
a bar can see closed strictly before its own last session — verified exhaustively over
82 252 buckets (worst-case margin 7 calendar days, never 0) plus 8 adversarial synthetic
calendars (zero-session weeks, 25 % random holidays, a 3-week gap, intraday stamps).

## 5. Nit found in passing

`early = (sb & b1os & rising2_on3 & (wbull | b1os) & ...)` (`:225`) — `b1os` is already a
conjunct, so `(wbull | b1os)` is identically `True` and `wbull` is dead in this expression.
Pre-existing; it is why `early_markers` moved on 0/157 names under the repair.

# Prophet US entry-lateness forensic — 2026-08-07

**Charter:** operator escalation 2026-08-07 ("picks give entries much too late; the stock has
already begun its run; we need to get closer to the actual bottom"). Measurement only — no gate,
rank, or engine change follows from this file. Measured by an Opus review lane commissioned by
the ANTICIPATION program session; bases and caveats preserved verbatim. Sibling receipt:
`CN_US_PROPHET_PARITY_ANATOMY_2026-08-07.md`.

**Scope:** 96 plans in `site/prophet/plans/` with `_signal_date >= 2026-06-01`; 78 priced
(`data/yahoo/` 41 + `data/baskets/ohlcv/` fallback 37 — sources verified identical, close-ratio
median 1.000000, std ≤7.6e-08). 18 plans unpriced (no series in either store), listed in the
lane transcript.

## 1. The four measured lateness sources

### (a) Signal timing — picks fire after the move has started

| metric | value |
|---|---|
| median pre-signal run-up (close vs min close, 10 sessions ending at signal) | **+6.34%** |
| p75 / p90 / max | +11.72% / +16.57% / +29.24% |
| fraction with run-up ≥ 5% | **66.7% (52/78)** |
| fraction ≥ 10% | 32.1% |
| median fwd10 from signal close | +3.04% (n=50) |
| "could have waited" — 10d low after signal ≤ entry×0.97 | **76.0% (38/50)** full windows |
| 10d low below entry at all | **100% (50/50)** |
| median max drawdown vs entry within 10d | −4.30% |

Run-up bucket vs fwd10 is **monotone decreasing** — lateness costs return directly
(directional only, n=8–17 per bucket, no test statistic):

| pre-signal run-up | n | median fwd10 |
|---|---|---|
| < 3% | 8 | **+6.85%** |
| 3–5% | 10 | +1.75% |
| 5–10% | 17 | +2.48% |
| ≥ 10% | 15 | +1.82% |

Month split (truncation-bias check): June "could have waited" 91% (n=11), July 72% (n=39) —
the number is not carried by one month. August picks unmeasurable (windows too young).

### (b) Entry placement — the published entry sits ABOVE the signal close

| placement (n=78) | median | frac above signal close |
|---|---|---|
| `entry` vs signal-date close | **+2.72%** | 78.2% |
| `trigger` vs signal-date close | +3.81% | 91.0% |
| `entry` vs the 10d low | **+10.07%** | 50% ≥ +10% |

Measured against the signal close instead of `entry`, the ≤−3% drawdown rate halves
(76% → 36%): **roughly half the "should have waited" gap is created by the entry level
itself, not the signal timing.**

### (c) Publication lag — signal_date is not when the pick was served

Git-add date of each plan file vs `_signal_date` (n=96, all resolved):
**median 5d, p75 11d, max 57d; 72% ≥ 3d.** Price moved a median **+3.03%** over the lag;
50% moved ≥ +3% before publication. Worst: CCS 57d, AMPH 54d, EXC 46d, VIRT 41d, APPF/PATH 35d.

Bookkeeping incoherence on the board: `signal_asof` is a board-level CONSTANT (all 69 buy rows
carry the same value), and GPCR's `days_since_signal` moved 48 → 43 → 41 within ~2h on 08-07
for a fixed signal.

### (d) Repaint — fired events are erased by the trailing bucket

4/5 dissected names (SKY, VSEC, XPEL, NGVT) read `eligible=True` on the 2026-08-05
truncated/live basis and `eligible=False` for that same row once 08-06 data lands. XPEL is the
costly case: live basis fired at 50.29 (+18.50% off the 10d low); the surviving history shows
47.68 (+11.58%) — understating the chase by ~7pp. **Backtests over surviving history are
therefore optimistic about live earliness.** Same defect class as CN #4877 ("a published pick
can be un-published by the trailing bucket"); the CN-side PIT-latch fix
(`fix(confluence): PIT latch so a fired T2 event can never be un-fired`) sits on branch
`claude/missing-300363-china-prophet-8702fa`, unmerged as of this receipt.

## 2. The five named picks (GPCR, SKY, VSEC, XPEL, NGVT)

None has a Prophet plan — they are ranks 0–4 of the `buy[]` lane on the 08-06 board.
`tier_stream` on both bases (full-series = completed buckets; truncated = live/provisional —
they disagree, per `engine/confluence_tiers.py:565-575`):

| name | first eligible (full) | tier | % off 10d low | first eligible (live) | % off 10d low |
|---|---|---|---|---|---|
| GPCR | 2026-08-06 | T2 | +11.13% | 2026-08-06 | +11.13% |
| SKY | 2026-08-06 | T1 | +14.96% | 2026-08-05 | +14.51% |
| VSEC | 2026-08-06 | T1 | +21.88% | 2026-08-05 | +16.63% |
| XPEL | 2026-08-06 | T1 | +11.58% | 2026-08-05 | +18.50% |
| NGVT | 2026-08-06 | T1 | +10.19% | 2026-08-05 | +9.86% |

All five were tier-null on **every** session 07-24 → 08-04. Median distance off the 10d low at
first eligibility: **+11.6% (full) / +14.5% (live)**. Do not quote these dates without stating
the basis.

## 3. Vintage served, 2026-08-01 → 08-07 (63 commits of us_standouts.json)

`as_of` pinned at **2026-07-31 from 07-31T20:35 through 08-07T21:02**; advanced only at the
08-08T04:14 commit (`3cbef39a6`). SKY/VSEC/XPEL/NGVT first appear only in that unfrozen
commit — **their late signals are model lateness, not freeze lateness. GPCR is the exception:**
ranked #1 on the frozen 07-31 board from 08-07T17:37 (and #42 at 15:54, `state=FRESH BUY`,
`days_since_signal≈41`).

**Freshness reporting lied during the freeze:** at `2dfebf35d` (08-06T16:36) the staleness
block read `price_through=2026-08-06, age_days=0, delayed=false` while `as_of` was 07-31 —
keyed on prices, not the factor vintage. For ~29h the board served 7-day-old factor rankings
labelled "0 days old, not delayed". Recovered at `da891cd8f` via the added `inputs.board_asof`
(the W1-B fail-closed heal, #4933). Mixed-vintage prices on the frozen board: PI shown 151.36
vs true 171.91 (**+13.58% stale**), `members_at_through: 428/3033`.

## 4. ASTS — the operator's "recommended around July 31"

**Never a Prophet plan** (no plan file ever, zero ledger rows, `git log -S ASTS` on the ledger
empty). It appeared in `buy[]` twice, both times non-actionable:

| when | board as_of | rank | state | entry_signal | shown price | live context |
|---|---|---|---|---|---|---|
| 07-30 (2 commits) | 07-29/07-30 | #7–8 | TOP WATCH | `extended` | 58.44 | pre-run |
| 08-04 (2 commits) | **07-31 frozen** | #36–46 | COUNTERTREND BOUNCE | `bounce_wait` | 58.98 | **live 70.31 — 16.1% stale** |

Removed from the lane the same day both times. The board SAW ASTS before the run (07-30,
rank #7) and classified it `extended` — a non-admissible status — then re-saw it mid-run at a
16%-stale price. The loss was **status classification + freeze**, not the not_topped veto.
Actual closes: 07-29 53.03 · 07-30 58.44 · 07-31 58.98 · 08-03 63.52 · 08-04 70.31.

## 5. Caveats (binding on any reuse of these numbers)

1. fwd10/full-window stats exist for 50/78 picks (signals ≤ ~07-23); June/July only.
2. Run-up-bucket table has no significance test; treat as directional.
3. Full-series vs truncated tier bases disagree on 4/5 names; both reported.
4. Board vintage read from committed artifacts, not from what the VPS served (3-min pull ≈
   equal, not independently probed).
5. Plans' `entry` semantics: entry = asof close by construction (`engine/prophet_bridge.py`);
   the +2.72% gap vs signal close is the signal→origination staleness, same defect as (c).

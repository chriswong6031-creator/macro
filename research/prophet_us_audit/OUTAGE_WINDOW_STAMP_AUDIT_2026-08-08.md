# Outage-window stamp audit — 2026-08-03..08-08

**Operator question (2026-08-08):** *"incorrect dates being recorded for golden oracle and
Prophet for the few days our lights went out — need this fixed so our forward ledger can
maintain correct dates and prices."*

**Answer, measured: the forward ledger carries NO outage-caused mis-stamp — 0 of 27 rows
have a `signal_date` inside the window. The dates are not run-date-stamped. What IS wrong
is a naming collision that predates the outage: every stamped date on these surfaces is the
3D bucket's OPEN label, and three surfaces read it as the date the signal was knowable —
which is the bucket's CLOSE, a uniform 2 sessions later. On the 25 markers in the window
that gap moves the price basis by 2.23% on average and 27.22% at the tail.**

Reproduce: `python3 research/prophet_us_audit/outage_window_stamp_audit.py --json <path>`.
Machine-readable result: `OUTAGE_WINDOW_STAMP_AUDIT_2026-08-08.json`.

Outage shape: `daily.yml` collect job dead 2026-08-03..08-06; artifacts frozen at as_of
07-31 through 08-07; unfreeze commit `3cbef39a6` at 2026-08-08T04:14Z.

---

## 0. Method, and what "true date" means here

A 3D bucket's **value** is its LAST close, so the signal it carries is knowable when that
session closes. Its **label** is its OPEN date — chosen deliberately (R-SQ2) so a marker
date is always a real traded bar. Both fields are correct; reading one as the other is the
defect, and it is the same shape
`research/SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md` documents for `asof`, `w_bull`
and `rising2_on3`.

- **stamped date** — what the artifact publishes (`markers[].date`, plan `_signal_date`,
  ledger `signal_date`).
- **true date** — the last daily session in that marker's own bucket
  (`engine.signal_quality.marker_last_session`), i.e. the close that produced the signal.
- **drift** — sessions between the two, on the NYSE reference calendar.
- **price basis** — the close on each date. This is the number that decides whether an
  entry, exit or forward return is measured from a bar the signal did not yet exist on.

Markers are additionally **truncation-replayed**: the tape is cut at each candidate session
and `analyze` re-run, so the report states the first session a run could actually have seen
the marker rather than inferring it.

---

## 1. Golden Oracle markers — 25 stamped in window, 25 with drift

Every marker in the window is stamped **2026-08-05** and became knowable at the close of
**2026-08-07**: they all sit in the one 3D bucket `[08-05, 08-06, 08-07]`. Drift is
therefore uniform at **2 sessions**, not a distribution.

| | |
|---|---|
| markers stamped in window | 25 (17 `sell`, 5 `buy`, 3 `cut`) |
| drift = 2 sessions | 25 / 25 |
| drift = 0 | 0 |
| nulls (true date underivable) | 0 |
| published `asof` on all 25 files | `2026-08-05` (the bucket LABEL, not the tape's last session `2026-08-07`) |
| price move, stamped basis → true basis | mean **−1.42%**, median −0.63% |
| absolute move | mean **2.23%**, median 1.17%, max **27.22%** |

**Truncation replay — the stamps are NOT run-date artifacts.** Cutting each tape and
re-running `analyze` reproduces the same `2026-08-05` label from a run on 08-05 (15 names),
08-06 (6) or 08-07 (4). No marker's label moves with the date of the run that evaluated it,
which is the specific failure the outage could have caused and did not. The 15 names
visible from an 08-05 run were visible on a bucket that had not closed — the provisional
surface the ANTICIPATION forensic already records — but their label is stable either way.

### Full table (all 25 rows; drift = 2 sessions on every one)

| ticker | type | quality | stamped | true | drift | close @ stamped | close @ true | move |
|---|---|---|---|---|---|---|---|---|
| ATO | sell | — | 2026-08-05 | 2026-08-07 | 2 | 172.20 | 170.19 | −1.17% |
| BNY | sell | — | 2026-08-05 | 2026-08-07 | 2 | 158.74 | 157.61 | −0.71% |
| CASY | cut | — | 2026-08-05 | 2026-08-07 | 2 | 852.86 | 833.95 | −2.22% |
| CB | sell | — | 2026-08-05 | 2026-08-07 | 2 | 352.54 | 350.31 | −0.63% |
| DUK | sell | — | 2026-08-05 | 2026-08-07 | 2 | 123.34 | 124.85 | +1.22% |
| EOG | sell | — | 2026-08-05 | 2026-08-07 | 2 | 134.23 | 134.74 | +0.38% |
| ES | sell | — | 2026-08-05 | 2026-08-07 | 2 | 72.47 | 72.33 | −0.19% |
| ETN | buy | pending | 2026-08-05 | 2026-08-07 | 2 | 446.18 | 448.68 | +0.56% |
| F | cut | — | 2026-08-05 | 2026-08-07 | 2 | 14.13 | 13.98 | −1.06% |
| GOOG | buy | pending | 2026-08-05 | 2026-08-07 | 2 | 360.13 | 353.47 | −1.85% |
| KMB | sell | — | 2026-08-05 | 2026-08-07 | 2 | 112.37 | 109.68 | −2.39% |
| KVUE | sell | — | 2026-08-05 | 2026-08-07 | 2 | 19.67 | 19.23 | −2.24% |
| LYV | sell | — | 2026-08-05 | 2026-08-07 | 2 | 183.52 | 180.66 | −1.56% |
| NEE | sell | — | 2026-08-05 | 2026-08-07 | 2 | 85.91 | 84.65 | −1.47% |
| NVDA | buy | block | 2026-08-05 | 2026-08-07 | 2 | 219.22 | 223.96 | +2.16% |
| O | sell | — | 2026-08-05 | 2026-08-07 | 2 | 62.70 | 62.51 | −0.30% |
| PG | cut | — | 2026-08-05 | 2026-08-07 | 2 | 146.80 | 145.79 | −0.69% |
| PM | sell | — | 2026-08-05 | 2026-08-07 | 2 | 188.93 | 189.57 | +0.34% |
| SPGI | sell | — | 2026-08-05 | 2026-08-07 | 2 | 410.03 | 408.19 | −0.45% |
| STLD | buy | pending | 2026-08-05 | 2026-08-07 | 2 | 265.96 | 262.45 | −1.32% |
| **TTD** | **sell** | — | 2026-08-05 | 2026-08-07 | 2 | **18.96** | **13.80** | **−27.22%** |
| VTR | sell | — | 2026-08-05 | 2026-08-07 | 2 | 92.53 | 93.36 | +0.90% |
| WBD | buy | pending | 2026-08-05 | 2026-08-07 | 2 | 25.97 | 26.78 | +3.12% |
| WELL | sell | — | 2026-08-05 | 2026-08-07 | 2 | 237.25 | 236.92 | −0.14% |
| WM | sell | — | 2026-08-05 | 2026-08-07 | 2 | 224.31 | 227.68 | +1.50% |

**TTD is why this matters and it is a real move, not a data artifact.** Closes run
18.30 → 19.34 → 18.96 → 17.67 → **13.80** on volume 21.8M → 16.4M → 92.0M → 132.9M, with
the high (18.995 → 14.57) and low (17.39 → 12.83) tracking the close down — a price event,
not a split or dividend re-adjustment. A `sell` read at the stamped date books the exit at
18.96; the signal was only knowable at 13.80. Everything downstream that measures from the
marker date inherits that 27% overstatement.

### The three surfaces, on one marker (NVDA, the operator's example)

| surface | date shown | what it actually is |
|---|---|---|
| chart marker (`site/chart.js` `mapMarkers`) | 2026-08-05 | bucket OPEN label |
| Golden Oracle panel state | Aug 7 | bucket CLOSE — the knowability date |
| buy-filter verdict | still open | confirmation window has NOT printed |

The panel's "Aug 7" was never wrong — it had no field to name. Note the third row
specifically: NVDA's `quality` reads `block` with `reasons` `["veto: bearish divergence",
"pending confirmation"]`, and `confirmation_date` returns null. The block has **not**
cleared; "Aug 7" is the bucket close, not a clearance date.

---

## 2. Prophet plans — 10 stamped in window, 8 with no derivable truth

| | |
|---|---|
| plans with `_signal_date` in window | 10 (8 at 2026-08-05, 2 at 2026-08-03) |
| index `asof` | 2026-08-08 (rebuilt post-unfreeze) |
| drift = 2 sessions | 1 (NVDA) |
| drift = −1 session | 1 (GE) |
| **true date underivable — printed, not hidden** | **8** |

| ticker | plan id | stamped | own last buy marker | true | drift | close @ stamped | close @ true | move |
|---|---|---|---|---|---|---|---|---|
| NVDA | NVDA-BULL-20260805 | 2026-08-05 | 2026-08-05 | 2026-08-07 | +2 | 219.22 | 223.96 | +2.16% |
| GE | GE-BULL-20260805 | 2026-08-05 | 2026-07-31 | 2026-08-04 | **−1** | 381.22 | 377.28 | −1.03% |
| VSEC | VSEC-BULL-20260805 | 2026-08-05 | null | null | null | null | null | null |
| ROIV | ROIV-BULL-20260805 | 2026-08-05 | null | null | null | null | null | null |
| XPEL | XPEL-BULL-20260805 | 2026-08-05 | null | null | null | null | null | null |
| SOUN | SOUN-BULL-20260805 | 2026-08-05 | null | null | null | null | null | null |
| CTS | CTS-BULL-20260805 | 2026-08-05 | null | null | null | null | null | null |
| UAL | UAL-BULL-20260805 | 2026-08-05 | null | null | null | null | null | null |
| SOFI | SOFI-BULL-20260803 | 2026-08-03 | null | null | null | null | null | null |
| MDB | MDB-BULL-20260803 | 2026-08-03 | null | null | null | null | null | null |

The 8 nulls are **coverage, not failure**: those tickers have no `site/signals/<T>.json`
because they are outside the 240-name US deep-history universe the marker engine runs on.
Their plan dates cannot be checked against a marker that does not exist, and the audit
prints that rather than scoring them as clean.

**GE's −1 is the tell, and it is not an outage artifact.** A plan's `_signal_date` is not
the signal's date at all: `engine/prophet_bridge.py:1996` sets
`signal_date = anchor if anchor else standouts_asof` — the **us_standouts board's as_of**.
GE's own last buy marker fired 2026-07-31 (knowable 08-04), yet the plan claims 08-05,
because that is when the board ran. A board-level constant is being published as a
per-name signal date, which is the same defect the board's `signal_asof` carries
(`engine/us_board_rank.py:516-522`, and see §5).

---

## 3. Prophet forward ledger — clean for the outage, standing drift elsewhere

| | |
|---|---|
| rows total | 27 |
| **rows with `signal_date` inside 2026-08-03..08-08** | **0** |
| rows with ANY date (signal/entry/close) in window | 7 |
| rows needing an outage correction | **0** |

**No ledger row was mis-stamped by the blackout.** The 7 rows that touch the window touch
it through `close_date` / `asof` — outcome resolution dates, which are correctly the dates
the outcome was determined — not through `signal_date`.

Widening past the window to all 27 rows, the same OPEN-label semantic is present but
pre-existing:

| finding | rows |
|---|---|
| `signal_date` resolves to a bucket label; true date is **2 sessions later** | 7 (QCOM, UBER, EXC, SYK, SYY, MSFT, PLTR) |
| `signal_date` is **not a bucket label of that ticker at all** | 2 (QCOM 2026-07-09, MS 2026-07-09) |
| no local tape (outside the deep universe) — unresolvable, printed | 18 |

The 2 non-label rows are the §2 board-as_of path landing on a date that is not any 3D
bucket open for that name. Calendar gaps on the 7 are 2, 4 or 5 days — all exactly 2
sessions once weekends and the 07-04 holiday are removed.

---

## 4. Proposed correction — nothing to rewrite today

**No ledger rewrite is proposed, and none is needed for the outage.** In-place ledger
edits are refused here on principle as well as on evidence: nightly is the sole advancer of
forward ledgers, and a migration merged beside a concurrent nightly has already been
observed to revert silently.

Were a correction warranted later — for the standing 2-session semantic in §3, which is a
separate ruling from this outage question — the append-only form is the one to use: emit
new `prophet.ledger.correction/v1` rows carrying `{corrects_id, field, old_value,
new_value, basis, corrected_at}` and leave the original rows untouched, so the record of
what was published survives alongside the repair. That is a follow-up for the main session
to rule on, not a change this PR makes.

What this PR does instead is make the distinction **nameable at the source**: every
published marker now carries `signal_date` (the bucket close — knowability),
`confirmed_date` (when the buy-filter label became knowable; null while pending) and
`recorded_at` (the run that first published it) alongside the unchanged `date`. With
`recorded_at` in place, publication lag — `recorded_at` minus `signal_date` — becomes
measurable going forward, so a future outage leaves evidence in the artifact instead of
only in the workflow logs.

---

## 5. Not fixed here, and why

The plan/board date path (§2) is **not** touched by this PR. `_signal_date` originates in
`engine/prophet_bridge.py` and the board's `signal_asof` in `engine/us_board_rank.py`; both
files are claimed by in-flight sibling PRs (#4977 `anticipation-a1-patience-admission`,
#4976 `anticipation-a2-patience-rank`), and `signal_asof`/`signal_age` are shared with
`engine/hk_board_rank.py`, so re-pointing them is a cross-board semantic change owing its
own blast-radius report. It is recorded here as measured evidence for whoever rules on it.

Once a marker carries `signal_date`, the board has a per-name date to stamp instead of its
own `as_of`, and the plan has a real signal date to inherit — the §2 and §3 drift then
closes at the source rather than being patched per surface.

# W5 S10 Phase-0 Pre-Registration — Margin-Inflection Reclaim

*2026-07-06 · Setup-Species program (research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md §4 S10,
§7 W5+) · registered BEFORE first run (this file's merge commit precedes the report; the
prereg is immutable once committed — results are added to `W5_S10_REPORT.md` only).*

## Species under test

**S10 v1.0** — Margin-Inflection Reclaim. Horizon class **positional** (frozen at
registration; promotion keys on **`clean15_126`** — +15% before −5% within 126 trading days.
`clean8_21` and the descriptive horizon ladder print as **context only**, never the verdict).

**Mechanism story (registered, from the registry):** when a company's gross/operating margin
**direction** changes — the *first* quarterly improvement after ≥2 quarters of deterioration —
*while the name is already in a washout state and price has begun to reclaim off the washout
low*, the margin turn signals a fundamental mean-reversion that a purely technical washout does
not. S10 keys on margin **DIRECTION change, not level** (buying cheap-but-still-declining
margins is a named rejection rule). It is a **safety-net stratifier** (does the fundamental turn
improve terminal-state quality?), never a return-alpha overlay.

## Nearest dead neighbours (§1.6 — naming them is mandatory before any compute)

| dead idea (§1.6) | why S10 is mechanically different |
|---|---|
| **Raw washout depth as a boost (H1)** — "works only through the cohort lens" (WAVE1 §2, BOTTOM_CONFIDENCE P2) | S10 uses washout only as a **binary arming context**, never as a continuous depth boost. Its trigger is an orthogonal **fundamental** margin-direction change. Guarded by **K4** below: if the advantage is explained by S10 fires simply being *deeper* washouts, it is re-derived H1 and does not promote. |
| **Timing as return-alpha / board-level MAE reducer (#812)** (§1.6 ENGINE_FIX) | S10's verdict is the **terminal-state partition** (stop-out / dead-money / cushion), returns printed as context only. No sizing, no rank-for-return. |
| **Shallow-dip preference — shallow side LOSES (0/8 promote)** (§1.6 WAVE6 §3) | S10 keys on the **margin turn**, independent of dip depth; depth is a control (K4), not the signal. |

## Data (all existing; no new fetches)

- **Fundamentals:** `data/edgar/statements_quarterly.parquet` (git-tracked, in-tree; 54,853
  ticker-quarters, 1,331 tickers, FY2009–2027, 0-failure backfill 2026-07-03). Columns used:
  `ticker, fiscal_year, fiscal_quarter, period_end, filed, revenue, gross_profit, op_income`.
  **PIT discipline:** a quarter is knowable only on/after its `filed` date (never `period_end`).
- **Prices:** `<data-host>/breadth/_closes_deep.parquet` ∪ `_closes_delisted.parquet`
  (dividend-adjusted daily closes, deep history + recovered delisted names). **These are the
  Mac-local deep-history store — untracked, present only on the canonical data host, NOT in
  worktrees; the run reads from the data host** (see Ops note below).
- **PIT membership:** `<data-host>/breadth/sp1500_pit_membership.parquet` — for per-date
  survivor-price coverage stamping (§1.2 survivorship honesty), not a hard gate.
- **Washout state:** `engine/coiled.py::washout_ctx(close_series_sliced_to_date)` → `bool|None`
  (True iff the series capitulated ≥15% from its 126-bar prior high within the last 91 bars;
  needs ≥308 bars). Computed dynamically per (ticker, date); there is no washout parquet cache.
- **Sectors (archetype scope + financials exclusion):** `equity_factors._names_sectors('broad')`
  → `{ticker: (company_name, GICS_sector)}`. **Current** GICS applied to history (non-PIT) — a
  disclosed limitation carried into the report's leak-audit.
- **Grading:** `engine/grading.py::terminal_state(close, signal_date, liftoff_mult, liftoff_horizon)`
  with the masterplan constants (STOP 0.95, CUSHION 1.05, LIFTOFF_15 1.15, HORIZON_126 126).
  Fills honour §1.2: entry = the **next bar strictly after** the signal date (`same_bar=False`).

## Universe & scope (measured 2026-07-06)

- **EDGAR ∩ priced US names: 1,317** (99% of EDGAR tickers are priced).
- **HARD EXCLUSIONS (registry-mandated + margin-semantics):** GICS **Financials (209)** —
  "EDGAR ratio unreliability" per the record — and **Real Estate / REITs (100)** — margin
  concept ill-defined. → **Primary universe = 1,008 non-financial, non-REIT names.**
- **Archetype cells (soft stratification, NOT a hard gate — hard gates are banned):** the
  hypothesised-supportive cells consumer + industrial + retail ≈ Industrials 228 + Consumer
  Discretionary 168 + Consumer Staples 61 ≈ **457 names** are reported as the primary
  interest cell; the full non-financial 1,008 is reported alongside as context. `distressed`
  flagged (not excluded) per the record.
- **Era:** 2010-01 → the last date with a full 126-trading-day forward window available. A fire
  requires ≥4 PIT-known consecutive quarters (for the direction predicate) + ≥308 price bars
  (for washout) + 126 forward bars (for grading).

## Construction (FIXED except the registered 2-variant grid)

**Margin & the direction-change predicate.** For a ticker's PIT-ordered quarters (by
`period_end`, restricted to rows with `filed ≤ eval-date`, `revenue > 0`, finite margin), take
four consecutive quarters q0→q1→q2→q3 and define the **margin turn at q3** iff:

```
m(q1) − m(q0) < 0   AND   m(q2) − m(q1) < 0      (≥2 quarters of deterioration)
AND m(q3) − m(q2) > 0                            (the first improvement)
```

where `m(·)` is the margin under test. No threshold is searched (strict sign predicate).

**Washout arming.** `washout_ctx(close ≤ eval-date)` is True at the eval date.

**Price reclaim (fixed, no search).** `close_t ≥ 1.05 × min(close over the trailing 63 trading
days)` — price has bounced ≥5% off its recent washout trough.

**Fire timing (PIT-clean, one fire per (ticker, turn-quarter)).** For each ticker and each
margin-turn quarter q3, the fire date is the **first trading day `d ≥ filed(q3)`, within a
63-trading-day window after `filed(q3)`, on which BOTH washout-arming AND price-reclaim hold.**
If they never co-occur in the window → **no fire**. Entry fill = the next bar strictly after `d`.
This guarantees `filed(q3) ≤ d` (no look-ahead), enforced as **K5**.

**Comparator / incumbent (for the §1.3 flip test).** The **disjoint** set of washout+reclaim
events built with the *identical* construction (same universe, era, 63-day window, next-bar fill)
but where the same-quarter margin is **NOT** turning — `m(q3) − m(q2) ≤ 0` with q2 present
(margin flat/deteriorating). This isolates the **marginal** safety-net value of the fundamental
margin-turn over being in washout+reclaim alone. The **unconditional raw-bar base rate** (all
eligible name-days, no arming) is also printed for the wait-cost law.

## Registered config grid (trial-ledger family `s10_margin_inflection`)

| trial | margin under test `m(·)` | everything else |
|---|---|---|
| 1 | **gross margin** = `gross_profit / revenue` | fixed as above |
| 2 | **operating margin** = `op_income / revenue` | fixed as above |

**m = 2** (matches the registry `trial_count: 2`). Registered to `engine/trial_ledger`
(`log_declared_budget` / `register_trials`, family `s10_margin_inflection`) **before first
run**; the BH-FDR `m` is taken from the ledger so it cannot be understated. No other knob is
searched; any post-hoc variation is a **new** §8-recorded trial.

## Primary verdict metric (registered)

Per-fire **terminal-state partition at `clean15_126`** (positional class), for S10 fires vs the
comparator, each with a **Wilson lower bound**:

- **stop-out rate** (STOPPED — −5% before +5%): *lower is better*
- **dead-money rate** (DEAD_MONEY): *lower is better*
- **cushion incidence** (CUSHIONED or better — hit +5% before −5%): *higher is better*
- clean-liftoff rate (CLEAN_LIFTOFF — hit +15% before −5%): reported

**Flip criterion (§1.3, recorded in `ledger_binding.flip_criteria`):** S10 **matches-or-beats**
the comparator on **stop-out AND dead-money AND cushion incidence** (Wilson LB, episode-clustered
n floor). Forward returns are printed as **context**, never the verdict. **No deflated-Sharpe** —
S10 is a proportion species, and §1.2(5) restricts DSR to legitimate return-series legs.

## Statistical controls (§1.2 — the measurement law)

1. **Trial ledger** registered before first run (family `s10_margin_inflection`, budget 2).
2. **Episode-clustered p-value on every axis pp-spread — clustered by CALENDAR TIME, not ticker.**
   Block bootstrap over **calendar-time blocks ≥ 126 trading days** (≥ the longest forward
   window). *Rationale (lethal-gotcha guard):* washout fires cluster into a handful of
   market-wide episodes (2011, 2015-16, 2018, 2020, 2022); a ticker-only cluster CI is
   anti-conservative on a regime-limited panel — the **effective N is months, not fires**.
   **Effective-n = # distinct 126-day time-episodes with fires** is printed beside every rate.
3. **Benjamini–Hochberg** across the wave's full registered family (`m` from the ledger);
   promotion additionally requires **q ≤ 0.10** on the primary stop-out-spread p-values.
4. **≥5pp** spread, **n ≥ 300 per side**, **both temporal halves sign-stable**, **per-name
   majority** (>50% of contributing names individually show the improvement; no single name or
   episode drives it — the S13-K3 concentration analogue).
5. **Wait-cost law:** the arming wait (washout-onset → fire date) and its **entry premium vs the
   raw-bar baseline** printed beside every rate — the confirmation wait is never assumed free.
6. **Survivorship, honestly bounded:** per-date PIT member-price coverage % + a `survivor_priced`
   stamp; delisted names recovered via `_closes_delisted`; catastrophic losers absent from the
   store restated as an **optimism bound** in the report.

## Pre-registered kill / verdict criteria (checked in order)

- **K1 — no marginal safety-net value → NO-GO.** If S10 does **not** beat the comparator on
  stop-out rate (Wilson LB, ≥5pp, q ≤ 0.10 after BH) at `clean15_126` for **both** margin
  variants → species closed in §8; registry → `validation_status: falsified` (a **de-escalation**,
  landable without owner ratification).
- **K2 — underpowered → HOLD (not a kill).** If `n < 300` on either side for a variant →
  **UNDERPOWERED-HOLD**: remain `phase0`, accrue, re-read at a later monthly review. Low n is
  **not** a falsification.
- **K3 — sign instability → no flip.** If the stop-out improvement flips sign across the two
  temporal halves → not sign-stable → remain `phase0` (display-candidate at best).
- **K4 — depth confound (the §1.6 H1 tuition) → no independent value.** Stratify fires by
  washout depth (capitulation drawdown magnitude). If the margin-turn advantage vanishes after
  controlling for depth (S10 fires merely being deeper washouts than the comparator) → the signal
  is re-derived raw-washout-depth → **does not promote**. Report depth distributions of both
  sides and depth-matched rates.
- **K5 — leak sanity → halt, not a verdict.** Every fire must satisfy `filed(q3) ≤ fire-date` and
  `entry-fill-date > fire-date`. Any violation is a construction bug (the harness asserts and
  halts).

## What this phase-0 does NOT do

No gate/threshold search beyond the 2-variant grid (banned). No promotion by decree — a passing
phase-0 leaves S10 at `validation_status: phase0` with the evidence attached; the
`phase0 → accruing` advance is **proposed for the owner to ratify** (house law: *LLMs may only
de-escalate — never originate escalations; all promotions pass human review*). No board wiring,
no sizing. Promotion past display runs the §1.3 ladder (display chip → ledger → graded bonus →
gate weight) separately, and gate-weight additionally needs board-level receipts (§1.3, the #812
lesson).

## Report contract (`research/species/W5_S10_REPORT.md`)

Per-variant primary table (both sides, Wilson LB); the full both-class horizon grid
(`clean15_126` primary + `clean8_21` + descriptive ladder as context); episode-clustered
p-values with effective-n; BH-FDR family correction; K1–K5 verdicts; the depth-balance table
(K4); the wait-cost table; coverage / survivorship lines; a **leak-audit** section (fill rule =
next-bar; PIT `filed`-date mapping; sector-map non-PIT disclosure; every forward-looking element
enumerated); and the §8 status row (`date | wave | verdict | PR# | artifacts`). Registry updates
land **only** as proposed changes for owner ratification (or a self-landed `falsified` on a K1
NO-GO); `trial_count` unchanged (the grid is within the registered budget).

---

### In plain English

We already know that just being in a deep sell-off ("washout") doesn't tell you whether a stock
is a safe bottom or a falling knife — and that *how deep* the dip is doesn't help either (we paid
that tuition). S10 asks a different question: **when a beaten-down company's profit margins stop
getting worse and tick up for the first time in a while, and the price has started to bounce, is
that a safer place to step in?** We measure "safer" only as *did it avoid a fresh −5% stop-out /
avoid dead money / reach a +5% cushion* over the next ~6 months — never as "did it make money."
We compare margin-is-turning names against otherwise-identical washout-bounce names where margins
are still sliding. Crucially, we count **time episodes, not individual fires**, because these
setups bunch up in a few market-wide sell-offs — so the honest sample is far smaller than a raw
count suggests, and we refuse to let a single crash or a single stock carry the result. If the
margin-turn adds nothing once we control for how deep the washout was, it fails. Nothing gets
promoted automatically — a pass just earns S10 the right to be proposed to the owner for the next
rung.

### Ops note (run environment)

The deep price panel (`_closes_deep.parquet` / `_closes_delisted.parquet`) is a Mac-local store
present only on the **canonical data host** (the primary checkout's `data/breadth/`), not in git
worktrees. The harness is built in the worktree but **run against the data host** (point the
price loader at the host `data/breadth/`, or run from the host with a read-only data mount).
EDGAR fundamentals, PIT membership, and sector maps are in-tree. The run **reads** host data and
**writes** results only into the worktree's `research/species/` — it never mutates the host's git
state.

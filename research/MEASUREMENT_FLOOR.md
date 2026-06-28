# Institutional measurement floor — Phase 0 (shipped)

The institutional-gap diagnosis (`research/INSTITUTIONAL_ROADMAP.md`) was blunt: we are
institutional in *discipline* but not in *data breadth / survivorship*, and the keystone
is not a fancier model — it is the ability to **tell the truth about our own live score**.
This ships that floor. Two pieces, both impossible to overfit because they are *measurement*,
not fitted models.

## 1. Incremental IC — how much of our edge is real vs repackaged factors (immediate result)

`engine/validation.cross_sectional_resid` + `incremental_ic` neutralize a signal's
cross-section against the style factors we already own (market beta, size proxy, 12-1
momentum, low-vol) and re-measure the rank-IC. `scripts/measure_incremental_ic.py` runs it
on the deep panel (110 survivor mega-caps, 1962→2026, monthly) and writes
`data/strategies/incremental_ic.json` + `reports/incremental-ic.md`.

**Result (raw IC → incremental IC, HAC-t):**

| signal | h | raw IC | incremental IC | survives | read |
|---|--:|--:|--:|--:|---|
| `mom_12_1` | 21d | 0.0345 (t 3.8) | **0.0259 (t 3.3)** | 0.75 | genuine independent info |
| `mom_12_1` | 63d | 0.0420 (t 3.0) | **0.0325 (t 2.7)** | 0.77 | genuine independent info |
| `fip_continuity` | 21d | 0.0103 (t 1.4) | **−0.0025 (t −0.4)** | −0.24 | **collapses → was just momentum** |
| `near_52w_high` | 21d | −0.0155 | −0.0352 | — | anti-predictive here |

The point: only **12-1 momentum carries information beyond the factors we already own**
(~75% survives, still HAC-significant). `fip_continuity`'s raw IC was *entirely repackaged
momentum* — neutralization collapses it to ~0. Ranking on **incremental** IC, not raw IC, is
the institutional honesty upgrade; even this number is a survivor-only optimistic bound, so
the trustworthy content is the *relative collapse*.

## 2. Forward shadow book — the realized audit of the live score (the keystone)

The traded score had **never** been graded on returns that hadn't happened yet (in-sample
and even walk-forward backtests overstate). `engine/shadow_book.py`:

- `snapshot(date, recs)` — freezes `(date, ticker, score, percentile, regime)` at build time,
  append-only + idempotent. Wired into `scripts/build_stock_library.py` (additive) and
  `scripts/snapshot_shadow_book.py`.
- `mature(asof, closes)` — joins **only horizons that have FULLY elapsed** (the h-th trading
  bar after the snapshot exists and ≤ asof) to realized forward returns. The elapsed-horizon
  guard is the whole point — a not-yet-closed horizon is never graded (unit-tested).
- `grade(matured)` — rolling forward rank-IC + IC-IR + HAC-t per horizon. Run nightly by
  `scripts/mature_shadow_book.py` → `site/shadow/audit.json`.

**Honest status:** seeded with 156 frozen scores for 2026-06-18; **0 matured** (no horizon
has elapsed yet). The book accrues going forward and produces its first realized number in
~1–3 months. **Expected result, stated up front:** given the committed factor scorecard
(composite IC ≈ 0, only `payout` survives FDR, all on the optimistic survivor bound), the
forward book will most likely show the cross-sectional score's realized forward IC ≈ 0. **That
is the institutional win, not a loss** — for the first time the system will *know*, from live
forward tape, whether its traded score carries realized cross-sectional alpha, instead of
sizing on a number nothing has ever graded.

## 3. Persistent trial ledger (program-wide multiple-testing memory)

`data/trial_ledger.jsonl` is now **stood up** (the canonical `DEFAULT_PATH` was previously
never written). `measure_incremental_ic.py` logs its grid there at generation, so the
Deflated-Sharpe gate can deflate by a real program-wide N instead of a caller-asserted
literal. Migrating the remaining ~47 literal-`n_trials=` callers is the documented follow-up.

## What this does NOT do (honest scope)

It does not mint alpha and does not fix survivorship (Phase 1: recover the 492 CIK-resolvable
dead-name *fundamentals* from EDGAR; prices remain the free-data wall). The diagnosis's
portfolio-optimizer ambition was deliberately **cut** — the verifiers showed a Ledoit-Wolf
min-var on ~0-IC signals just fits estimation error (`engine/risk_sizing.py` already reasoned
this). The institutional move here is de-biasing and honest measurement, which is the only
foundation on which a real signal — if one ever clears the incremental-IC + forward-book bars —
can be trusted.

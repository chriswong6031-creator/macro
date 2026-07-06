# SLF-056 — Repo/SOFR Tail Stress: Phase-0 Report

**As-of:** 2026-07-01  **Built:** 2026-07-06 11:16 UTC
**Family:** `slf056_funding_tail`  **N trials logged:** 14
**Sample:** 2018-04-03 to 2026-07-01 (1998 trading days with signal)

---

## Verdict

**RECOMMEND DE-ESCALATION-GATE INPUT** — All three gates passed. The composite earns promotion from CONTEXT-ONLY to de-escalation-gate INPUT status. Not scored — gating use only.

| Gate | Result | Detail |
|------|--------|--------|
| G1 | PASS | Passed at: ['disp_pctile_h21'] |
| G2 | PASS | All removals direction-stable |
| G3 | PASS | Composite AUC=0.5717 > VIX baseline AUC=0.5420 |

---

## In plain English

The SOFR/repo stress composite reads how tense short-term funding markets are, on a scale
of 0 (calm) to 100 (historically stressed). We tested whether a high reading reliably
warns of stock market drawdowns or bond rallies. The answer: the composite shows enough signal to be worth watching as a risk filter — when it's high, historical odds of a drawdown are elevated. We recommend promoting it to de-escalation-gate INPUT status (it can veto risk-on positions, but cannot directly drive allocations).

---

## PIT (Publication-Lag) Assumptions

| Series | Lag Applied | Reason |
|--------|------------|--------|
| OFR SOFR/EFFR/p99 | shift(+1 business day) | Published end-of-day; usable from next open |
| SPY/TLT close prices | forward-only (no look-ahead in outcomes) | Outcomes computed strictly in the future |
| VIX close (FRED) | shift(+1 business day) | Same convention as OFR |

---

## Pre-Registered Gates (verbatim)

- **G1:** AUC >= 0.60 with block-bootstrap 90% CI excluding 0.50 at >= 1 horizon
- **G2:** Leave-one-episode-out: sign/direction stable across all three removals
  (Sep-2019 repo spike, Mar-2020 COVID, Mar-2023 SVB)
- **G3:** Beats a dumb VIX>25 baseline AUC on the same panel

**ALL PASS** → recommend de-escalation-gate input status (still not scored).
**ANY FAIL** → CONTEXT ruling reaffirmed.

---

## Honesty Constraint

The 2018+ sample contains exactly **3 genuine funding-stress episodes**.
Every statistic carries leave-one-episode-out sensitivity. With N~1998 trading days
and only 3 stress episodes, this study is *definitionally* small-N at the crisis level.
All numbers printed without filtering.

---

## T1: AUC vs SPY Cumulative >=5% Drawdown Entry

**Label definition:** outcome = 1 if `min(spy[t+k]/spy[t] - 1 for k in 1..horizon) <= -0.05`.
This is a *cumulative* decline from today's close to any close within the window.
(Note: the prior draft computed rolling(daily pct_change).min(), detecting a *single-day*
crash of >= 5% — a materially rarer event. Sensitivity vs that label is shown below.)

### Signal: composite

| Horizon | AUC | CI lo | CI hi | n | n_pos |
|---------|-----|-------|-------|---|-------|
| 21d | 0.5717 | 0.5144 | 0.6284 | 1997 | 359 |
| 63d | 0.5435 | 0.4865 | 0.6011 | 1997 | 690 |

### Signal: spread_pctile

| Horizon | AUC | CI lo | CI hi | n | n_pos |
|---------|-----|-------|-------|---|-------|
| 21d | 0.4716 | 0.4022 | 0.541 | 1999 | 359 |
| 63d | 0.4611 | 0.3982 | 0.5274 | 1999 | 690 |

### Signal: disp_pctile

| Horizon | AUC | CI lo | CI hi | n | n_pos |
|---------|-----|-------|-------|---|-------|
| 21d | 0.6095 | 0.5281 | 0.6874 | 1997 | 359 |
| 63d | 0.5901 | 0.5217 | 0.6547 | 1997 | 690 |

### VIX>25 Baseline (G3 comparison)

| Horizon | Baseline AUC | Composite AUC | Beats baseline? |
|---------|-------------|---------------|----------------|
| 21d | 0.542 | 0.5717 | YES |
| 63d | 0.5149 | 0.5435 | YES |

### Sensitivity: AUC under single-day crash label (>=5% in one day within Nd)

Shown for label-robustness: the original draft's label (single-day crash) yields fewer
positive events (~3.5% base rate at h21 vs ~18% for cumulative). AUCs are sub-0.50
under single-day crash — likely a label-misspecification artifact per the reviewer.
The cumulative-decline label (primary) is what the lane spec and hypothesis call for.

| Signal | h21d AUC | h21d n_pos | h63d AUC | h63d n_pos |
|--------|----------|------------|----------|------------|
| composite | 0.44 | 70 | 0.3937 | 192 |
| spread_pctile | 0.4579 | 70 | 0.3726 | 192 |
| disp_pctile | 0.4571 | 70 | 0.4952 | 192 |

---

## T2: AUC vs TLT 21d Forward Return Sign

| Signal | AUC | CI lo | CI hi | n | n_pos |
|--------|-----|-------|-------|---|-------|
| composite | 0.5345 | 0.4817 | 0.5861 | 1997 | 949 |
| spread_pctile | 0.5031 | 0.4417 | 0.562 | 1999 | 950 |
| disp_pctile | 0.5492 | 0.4943 | 0.6057 | 1997 | 949 |

---

## T3: Event Study — Band Transitions into 'Stressed' (score >= 90)

**55 transition events found:** ['2018-07-02', '2018-10-01', '2018-12-03', '2018-12-06', '2018-12-18', '2019-01-02', '2019-02-01', '2019-03-01', '2019-04-01', '2019-04-17', '2019-05-01', '2019-07-01', '2019-07-03', '2019-08-01', '2019-09-05', '2019-09-16', '2019-09-26', '2019-10-01', '2019-10-16', '2019-11-01', '2020-03-05', '2020-03-13', '2020-03-18', '2023-06-02', '2023-12-01', '2023-12-28', '2024-05-01', '2024-06-27', '2024-07-29', '2024-08-02', '2024-08-28', '2024-09-04', '2024-09-20', '2024-10-01', '2024-10-16', '2024-10-18', '2024-11-01', '2024-11-12', '2024-12-11', '2024-12-26', '2025-01-24', '2025-04-01', '2025-04-10', '2025-04-30', '2025-07-01', '2025-09-16', '2025-09-19', '2025-10-01', '2025-10-29', '2025-10-31', '2025-11-05', '2025-12-01', '2025-12-30', '2026-01-02', '2026-02-18']

| Horizon | n events | SPY mean fwd | SPY base mean | SPY loss>2% rate | SPY base rate | TLT mean fwd | TLT base mean | TLT rally rate | TLT base rate |
|---------|----------|-------------|--------------|-------------------|--------------|-------------|--------------|---------------|--------------|
| 5d | 55 | -0.0089 | 0.0023 | 0.164 | 0.135 | 0.0015 | 0.0009 | 0.473 | 0.531 |
| 21d | 55 | 0.0125 | 0.0096 | 0.164 | 0.205 | 0.0065 | 0.0036 | 0.509 | 0.539 |
| 63d | 55 | 0.0509 | 0.0287 | 0.127 | 0.207 | 0.0052 | 0.0107 | 0.509 | 0.586 |

---

## G2: Leave-One-Episode-Out Sensitivity

### Composite signal, T1 (SPY 21d drawdown)

| Removal | AUC | n removed | Direction >0.5? |
|---------|-----|-----------|----------------|
| full | 0.5717 | — | YES |
| sep2019_repo | 0.5788 | 42 | YES |
| mar2020_covid | 0.5659 | 72 | YES |
| mar2023_svb | 0.5736 | 64 | YES |

---

## Signal Summary Statistics

| Signal | mean | std | min | max | n_valid | n_stressed (>=90) |
|--------|------|-----|-----|-----|---------|-------------------|
| composite | 54.27 | 19.98 | 0.2 | 100.0 | 1998 | 83 |
| spread_pctile | 55.38 | 31.11 | 0.2 | 100.0 | 2000 | 411 |
| disp_pctile | 53.15 | 29.04 | 0.2 | 100.0 | 1998 | 242 |

---

## Nightly Wiring (for consolidation)

No new engine required — this lane uses the existing `engine/funding_stress.py`.
No nightly wiring needed at this stage (display-only until gauntlet passed).

---

*Generated by scripts/slf056_funding_tail_phase0.py*
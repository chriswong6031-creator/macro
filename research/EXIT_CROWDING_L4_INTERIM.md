# EXIT-CROWD L4 — ETF-flow rolloff — PRE-FDR INTERIM

**Status: PRE-FDR INTERIM — verdict ACCRUE.** This is the L4-only interim leg of the
ratified pre-registration (F3: L4 runs at ratification, PRE-FDR interim). No verdict
language stronger than ACCRUE/interim is used, and no BH q-values are printed, until the
16-trial FDR family completes (L1–L3 await the thetadata universe pass).

- **Registration:** [EXIT_CROWDING_PHASE0_PREREG.md](EXIT_CROWDING_PHASE0_PREREG.md) (RATIFIED 2026-07-04, rulings F1–F5).
- **Runner:** `scripts/run_exit_crowding_phase0.py --leg L4` (roadmap P4.4a).
- **Output artifact:** `data/options_exit/exit_crowd_l4_interim.json`.
- **Leg:** L4 — ETF-flow rolloff (institutional trim). **1–5 day lag on every cell** (O6-v: no lead claim tighter than the holdings-snapshot reporting cadence).
- **Outcome currency:** the LIVE `engine.sector_signals.STATE_BASE_RATES["SELL"]` dict, read at run time and stamped: `exc63 = -1.24%`, `hit = 40%`, `n = 169` (calibrated on the 11 SPDR sector ETFs 1998–2026). Compared via the B2 machinery from `scripts/oracle_gauntlet_p3.py`, carrying its **"informative only — different universe granularities"** cross-granularity caveat.

---

## In plain English

L4 asks: when institutional ETF flow rolls off a group we hold (flow turns net-negative
while the group's price is still flat or rising — the "A4 divergence tell"), does that lead
a drawdown at a 1–5 day lag? The honest answer today is **we cannot tell yet**, and the
reason is data depth, exactly as the pre-registration's discovery step warned. The flow
source only has about **three months of history, all in 2026**, and it has **no holdings
data at all for the 11 sector ETFs** the base rate is built on. So there is no way to run
the pre-registered era split, and any single number from this window is uninterpretable.
The verdict is therefore **ACCRUE** — register it, come back when history accrues — not a
pass and not a kill.

---

## 1. CRITICAL DISCOVERY — how much flow history actually exists

The L4 primitive is `engine.theme_flow_rollup.theme_flow(region='us')`, which computes from
dated ETF-holdings snapshots under `data/etf_holdings/<ETF>/<YYYY-MM-DD>.parquet`. The
runner recomputes flow **point-in-time** at each historical date (only snapshots dated
`<= as_of` are exposed; no future snapshot is ever read).

| Fact | Value |
|---|---|
| ETFs with dated snapshots | **30** |
| Union of snapshot dates | **66 dates, 2026-03-31 → 2026-07-02** (~3 months) |
| Deepest single ETF | BETZ — 65 snapshots (2026-03-31 → 2026-07-02) |
| **Sector-ETF (XLB…XLY) holdings present** | **NONE** (all 11 absent) |
| Persisted historical `flow_score` series on disk | **None** — `theme_flow` only ever reads the LATEST snapshot; there is no stored time-series |

**Consequences (all binding, none relaxed):**

1. **No era split is computable.** The prereg's primary window is **2018→** with mandatory
   eras **2018-19 / 2020-22 / 2023→**. All flow history lands in a single ~3-month slice of
   the **2023→** era. The 2018-19 and 2020-22 eras have **zero** data. A claim alive in a
   single era is dead (era-consistency, prereg §8.4) — so nothing can be gated.
2. **No sector-ETF holdings** means the PRIMARY-lane outcome currency (the sector-ETF SELL
   base rate) cannot be matched to a *sector-ETF's own* flow. Flow is only available for the
   thematic/industry baskets; the theme→sector mapping (§3 below) is the bridge, and it is
   lossy.
3. **The "n" is autocorrelated, not independent.** Raw fires recur on consecutive days and
   many themes map to one sector ETF, so overlapping 21-day windows on the same sector ETF
   are counted repeatedly. The runner stamps the distinct `(date × sector-ETF)` window count
   as the true independence ceiling.

**No history was fabricated and the pre-registration was not relaxed to manufacture n.**

---

## 2. Interim numbers (single ~3-month 2026 window — NOT interpretable)

Fire = `divergence == True` OR `flow_score` crossing below 0 (t-1 ≥ 0, t < 0) with coverage
≥ 0.10, per held-theme per session (prereg §2.2 L4).

| Cell | Raw fires (matured) | Distinct fire dates | Distinct (date×sector) windows | Fire-cond. excess mean | Δ vs SELL base rate (−1.24%) | Eras covered | Powered for gate |
|---|---|---|---|---|---|---|---|
| **21d PRIMARY** | 136 | 40 | 87 | **+5.68%** | +6.92 (WRONG sign for exhaustion) | `2023->` only | **NO** |
| 63d secondary | 0 | 0 | 0 | — (unmatured) | — | — | NO |
| 5d robust | 194 | — | 120 | — | — | `2023->` only | NO |

- **Total fires detected across 65 eval dates: 392.**
- Even the distinct-sector-window count (87 @21d) sits above the raw house floor of 60,
  yet the cell is **NOT powered**: `single_era=True` (only `2023->` has data) forces ACCRUE
  regardless — the mandatory era split cannot be run.
- The 21d mean is **positive** (sector *outperformance* after a flow-rolloff fire) — the
  **opposite** sign to the exhaustion hypothesis. **This is NOT a refutation.** On a single
  ~3-month 2026 window with autocorrelated overlapping windows and a lossy theme→sector
  bridge, the sign is uninterpretable.
- The **63d secondary horizon does not mature at all**: fires cluster near the end of the
  window, so no fire has 63 forward sector-ETF trading days *within the flow window's span
  of relevance* — reported as `n=0`, not imputed.

**Placebo (§5 + F1 PRIMARY lane):** same-sector leg-not-fired matched held theme-days,
regime+duration matched, 200 draws, `exclusion_zone = 10`. Ran (not insufficient) with ~101
candidate non-event days, but it inherits the same single-era / autocorrelation defect and
is reported for completeness only.

---

## 3. Theme → sector mapping (operationalized, stamped, and flagged LOSSY — OPEN ITEM)

The PRIMARY lane needs a GICS-sector home for each thematic basket (to compare against the
sector-ETF SELL base rate). Operationalized from the basket `category` field →
`CATEGORY_TO_SECTOR_ETF` (in the runner). **Two loss channels are flagged, not silently
resolved:**

1. **Coverage loss:** only **17 of 46** themes map to a sector ETF; **29 themes are
   unmapped** (their `category` has no clean GICS home, e.g. cross-cutting thematic labels).
2. **Straddle loss:** mapped categories that span >1 GICS sector are collapsed to one ETF —
   e.g. `AI & Technology → XLK` (drops Communication Services / XLC); `Energy & Power → XLE`
   (drops Utilities / XLU). Affected themes: mag7, ai_infra, ai_software, quantum_computing,
   power_grid, energy_complex, data_center_power, nuclear_power.

**OPEN ITEM:** the correct fix is a **per-member GICS rollup** of each basket's holdings
(sum member weights into their true GICS sectors) rather than a category→ETF shortcut. That
is a future amendment; it is flagged here rather than chosen silently.

---

## 4. What is NOT in this run (by design)

- **L1–L3 are stubs that hard-fail.** They read only `data/thetadata_eod/_manifest.json`
  (currently `n_roots=0, updated_at=null`) and raise BLOCKED (R8 / prereg §8.11). This runner
  **never reads `data/thetadata_eod/` mid-backfill.**
- **SECONDARY board-roster lane not run.** F1 makes the board `buy[]` roster a watermarked
  SECONDARY tag that never gates; the board ledger has only **3 rows** (2026-06-30 →
  2026-07-02), so it is not run here.
- **No FDR.** BH q-values print only when the 16-trial family (L1–L4 × eras) completes.
- **No wiring into any engine.** Display-only per house law (China subsector-gate
  falsification is binding); a pass would earn display annotations only, never a hard gate.

---

## 5. Verdict — ACCRUE

**ACCRUE.** Single-era (2023→ only), autocorrelated overlapping windows, no sector-ETF flow,
and a lossy theme→sector bridge mean no cell can be gated — this is ACCRUE by construction,
exactly as the prereg discovery step anticipated. Registered as `exit_crowding_phase0` in
`data/experiments/registry_seed.json`.

**Come back when:** ≥ 2 eras have flow data **AND** distinct `(date × sector-ETF)` windows at
21d ≥ 60 **AND** the L1–L3 sub-family completes the 16-trial FDR family (then BH q-values
print once for the whole family). ETF-holdings history depth is the binding accrual;
sector-ETF holdings coverage would additionally remove the theme→sector lossy-mapping open
item.

The house prediction (exit side validates before the buy side) is **neither confirmed nor
refuted** by this interim — there is simply not enough history yet to test it.

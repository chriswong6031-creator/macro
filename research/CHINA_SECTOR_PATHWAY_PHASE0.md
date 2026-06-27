# China Sector Pathway — Phase 0 Evidence Gate

Run: `python -m scripts.china_sector_pathway_phase0` (reuses `engine/china_sector_index.py`,
the SAME data layer the live engine uses → research == production).

**Question.** For the four GS-style sectors the user tracks on the Bloomberg terminal —
Banks (`GSXACHBA`), Consumption (`GSXACCON`), Real Estate (`GSXACNRE`), Auto (`GSXACNAU`) —
which China-specific drivers actually **lead** the sector's major tops & bottoms robustly
enough to put in a forward-looking pathway, and which merely coincide?

**Data.** Authoritative domestic sector indices = Shenwan (申万) L1 (`collectors/china_sectors.py`),
deep history: Real-Estate/Consumption from **1999-12**, Banks/Auto from **2014-02**. Consumption
= equal-weight composite of food&bev + appliances + retail + consumer-services + beauty +
textiles + light-mfg. Drivers (leak-free, monthly, macro publication-lagged 1m): credit impulse
(YoY of trailing-12m TSF), TSF YoY, M1/M2 YoY & M1−M2 gap, PMI, CPI, PPI, margin balance ROC &
%-of-float, QVIX, southbound 3m net, whole-A breadth, plus per-sector RS / distance-from-200d /
drawdown-from-1y-high.

**Method (house discipline).** Forward-return Spearman rank-IC at 3m & 6m; train(pre-2020)/
test(2020+) split with a SIGN-stability requirement out of sample; circular-permutation p-value
(preserves driver autocorrelation); Benjamini-Hochberg FWER (q=0.10) across the whole
152-test sector×driver×horizon family; plus an event study of each driver's own-history
percentile at the detected (≥25% zigzag) tops vs bottoms.

---

## Verdict

**No single driver clears the strict bar (IC≥0.15 + sign-stable + BH-survive). 0 of 152 tests
fully eligible; 73 sign-stable; 1 BH-survivor.** The lone BH-survivor — Auto southbound-net
(6m IC +0.43, p<0.001) — **fails sign-stability** (train −0.16, test +0.49): it is a
post-2020 Stock-Connect-era artifact, not a stable lead. **So the pathway engine must be
CONDITIONAL / display-only — no point forecast, no single-driver alpha.** This matches the
house findings on breakevens, vol-shock, and defensive-rotation: noisy monthly China-sector
data over ~12–18y does not support a switch.

### What IS robust — the two findings we ship

**1. The top/bottom STATE SIGNATURE (the "reasons"), consistent across all four sectors.**
Median own-history percentile at detected turns:

| leg | at BOTTOMS | at TOPS | reading |
|---|---|---|---|
| distance from 200-DMA | 0.02–0.17 | 0.75–0.95 | price vs trend |
| drawdown from 1y high | 0.05–0.20 | 0.76–0.91 | depth |
| 3m / 6m return | 0.04–0.25 | 0.74–0.94 | momentum |
| whole-A breadth %>200d | 0.16–0.19 | 0.72–0.81 | participation |
| margin % of float | low | 0.77–0.79 | crowding/leverage |

→ Bottoms = **capitulation/washout** (price below trend, deep drawdown, breadth collapsed,
deleveraged). Tops = **euphoria/crowding** (extended, crowded margin, broad euphoric breadth,
hot momentum). Descriptive (full-sample percentiles), labeled as such — but it is exactly the
"patterns & reasons for troughs and tops" the user asked for, and it is stable.

**2. A coherent, theory-backed, sign-stable lead CLUSTER** (modest IC, individually below FWER,
but directionally consistent and economically sensible — used only to *condition* a forward
tilt, never as alpha):

| driver | sign | where it's sign-stable | economic read |
|---|---|---|---|
| credit impulse / TSF YoY | **+** | Consumption (TSF 6m IC +0.25, p=0.006), Auto, Banks | China credit cycle leads risk appetite ~1–2 quarters |
| PPI YoY | **−** | Consumption (3m −0.25, p=0.025), Auto (−0.23), Banks | falling PPI → input-cost relief / forward margin tailwind |
| drawdown & dist-from-200d | **−** | RE, Banks, Consumption | mean-reversion: deeper washout → higher forward returns |
| PMI (Real Estate only) | **−** | RE (3m −0.18, p=0.008) | RE is counter-cyclical: bottoms in weak macro as stimulus arrives |

Counter-intuitive note: **M1−M2 gap reads NEGATIVE** to forward sector returns (sign-stable in
several) — i.e. it peaks coincident-to-late with cycle tops here, so it is treated as a
regime/coincident gauge, NOT an early lead.

---

## Design that follows from the evidence

`engine/china_sector_pathway.py` (display-only, gated by `engine/china_sector_pathway_backtest.py`):

1. **Cycle-turn map** — the zigzag major tops/bottoms per sector, and where price sits today on
   the washout↔euphoria axis. Robust; directly answers the "reasons" question.
2. **Conditional pathway tilt** — a simple, UN-tuned composite of the sign-stable cluster (credit
   accel +, PPI falling +, drawdown extreme +, breadth washed +) → a 0–100 forward-setup score,
   reported as an **empirical conditional probability** ("when the setup looked like today, the
   N-month forward return was positive X% of the time vs Y% base rate", Wilson CI, n) — the
   `fx_regime_radar` pattern. Conditioning, not a switch; honest CIs; no weight-fitting on returns.
3. **Driver attribution** — which signature legs are active now (the human-readable "reasons").

**CI gate (`china_sector_pathway_backtest.py`)** fails if (a) the washout/euphoria signature legs
stop separating bottoms from tops with the expected sign, or (b) any shipped cluster leg flips
its full-sample IC sign — forcing a human review before stale relationships reach the page.

**Detected major turns (sanity, ≥25% zigzag):** Banks T2021-02 (core-asset peak) → B2022-10;
Consumption T2021-02 (baijiu peak) → B2022-10 → T2023-02 (reopening) → B2024-09; Auto T2021-12
(NEV peak) → B2022-04 → B2024-02; RE many (high-vol). All line up with the real cycle.

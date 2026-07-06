# W2-031 CISA KEV Vendor-Exposure Shock — Phase-0

**Family:** `w2031_kev_vendor_shock`
**Date:** 2026-07-06
**Status:** Wave-2 spike S1 — off-render, no collector, no wiring
**Verdict:** NULL — gate(s) failed: G1, G3 — no confirmer proposed; display only

---

> **In plain English:** When a cybersecurity agency publishes a known-exploited
> vulnerability against a publicly-traded software vendor, does that vendor's
> stock underperform over the next 5 or 21 trading days? This script fetches
> every such entry from CISA's catalog (2021-present), maps them to tickers,
> and runs an event study with beta-adjusted returns. The pre-registered honest
> prior is that the effect is likely small or undetectable — academic research
> on breach disclosures finds modest, transient dips that often disappear after
> multiple-testing corrections. The goal is to determine whether this belongs
> as a display signal for the special-situations desk.

---

## 1. Pre-registered design

**Pre-registered direction:** NEGATIVE abnormal returns after KEV exposure.

**Honest prior (printed before results):** Breach-event literature finds small
and transient effects (typically −0.5% to −2% over 5–20d windows), often not
significant after multiple-testing correction. Expected home: event-context
DISPLAY for the special-situations desk, not a scored allocation signal.
Prior probability of clearing all three gates: LOW.

### Variants (logged to trial ledger at generation, before computation)

| Variant | Filter | Horizon | Description |
|---------|--------|---------|-------------|
| V1 | all entries | 5d | All KEV entries for mapped public vendors |
| V1 | all entries | 21d | All KEV entries for mapped public vendors |
| V2 | ransomware only | 5d | Entries with knownRansomwareCampaignUse = 'Known' |
| V2 | ransomware only | 21d | Same, 21d |
| V3 | cluster events | 5d | >=2 entries same vendor within 5 trading days |
| V3 | cluster events | 21d | Same, 21d |
| V4 | due pressure | 21d | Top-decile weeks by open due-dates within 14 cal days |

### Gates (all must pass for confirmer candidacy)

- **G1:** V1 21d mean abnormal return NEGATIVE with |t_HAC| >= 2.0 AND BH-FDR q <= 0.10
  across the 7-cell family (V1×2 + V2×2 + V3×2 + V4×1 — V4 is 21d-only).
- **G2:** Split-half same-sign: 2021-11..2024-02 vs 2024-03..2026-07 for V1 21d mean.
- **G3:** Survives excluding Microsoft entries (largest vendor concentration).

### PIT assumptions

- `dateAdded` in the CISA KEV catalog is the date CISA published the entry — same-day public.
- Entry triggered at CLOSE of `dateAdded + 1 trading day` (conservative; ensures public
  access before entry price is used).
- Beta estimated from trailing 252 trading days OLS (min 120), using IGV (iShares Expanded
  Tech-Software ETF) as benchmark — all mapped vendors are software/security sector.
- Vendor corporate actions: VMware mapped to VMW valid through 2023-10-30 (Broadcom
  acquisition close); Citrix/CTXS valid through 2022-09-08 (privatization); SolarWinds/SWI
  valid through early 2024 (Silver Lake take-private); ARM valid from 2023-09-14 (IPO).
- Only vendors publicly listed on `dateAdded` contribute events.

---

## 2. Data and coverage

| Metric | Value |
|--------|-------|
| KEV catalog total entries | 1631 |
| Events for mapped public vendors (post corporate-action filter) | 931 |
| Mapping coverage | 57.1% of total entries |
| Events with valid beta (≥120d history) | 722 |
| Events with valid 5d abnormal return | 719 |
| Events with valid 21d abnormal return | 712 |
| Benchmark | IGV (yahoo), 2021-07-06 to 2026-07-02 |

**Variant event counts:**

| Variant | N |
|---------|---|
| V1 all | 931 (base set) |
| V2 ransomware | 185 |
| V3 cluster | 190 |
| V4 due pressure | 188 |

**Top vendors by event count:**

| Vendor | Events |
|--------|--------|
| Microsoft                      |  378 |
| Cisco                          |   93 |
| Apple                          |   93 |
| Adobe                          |   79 |
| Google                         |   72 |
| Oracle                         |   44 |
| Fortinet                       |   26 |
| Synacor                        |   18 |
| VMware                         |   18 |
| Palo Alto Networks             |   15 |
| SAP                            |   14 |
| Atlassian                      |   13 |
| Qualcomm                       |   12 |
| NETGEAR                        |    8 |
| Progress                       |    8 |

---

## 3. Results

All means expressed as percentage abnormal return (vendor cumulative − beta × benchmark cumulative).

| Variant | N | Mean AR | t_HAC | p_HAC |
|---------|---|---------|-------|-------|
| V1  5d  all | 719 | +0.905% | +1.74 | 0.0818 |
| V1 21d  all | 712 | +1.737% | +1.34 | 0.1793 |
| V2  5d  ransomware | 132 | +1.149% | +1.19 | 0.2354 |
| V2 21d  ransomware | 131 | +3.361% | +1.28 | 0.1996 |
| V3  5d  cluster | 188 | +1.139% | +1.21 | 0.2266 |
| V3 21d  cluster | 187 | -0.098% | -0.04 | 0.9701 |
| V4 21d  due pressure | 179 | +1.791% | +1.85 | 0.0639 |

---

## 4. Gate evaluation

### G1 — Direction + significance + FDR

V1 21d: mean = +1.737%, t_HAC = +1.34

BH-FDR across 7-cell family (α = 0.10):

| Cell | p | q (BH) | Decision |
|------|---|--------|----------|
| V1_21d       | 0.1793 | 0.2746 | retain |
| V1_5d        | 0.0818 | 0.2746 | retain |
| V2_21d       | 0.1996 | 0.2746 | retain |
| V2_5d        | 0.2354 | 0.2746 | retain |
| V3_21d       | 0.9701 | 0.9701 | retain |
| V3_5d        | 0.2266 | 0.2746 | retain |
| V4_21d       | 0.0639 | 0.2746 | retain |

**G1: FAIL**

### G2 — Split-half same-sign

| Period | N | Mean AR | t_HAC |
|--------|---|---------|-------|
| Early 2021-11..2024-02 | 485 | +1.880% | +0.96 |
| Late  2024-03..2026-07 | 227 | +1.615% | +1.25 |

**G2: PASS**

### G3 — Survives ex-Microsoft

Microsoft contributes 378 events in catalog (294 with valid 21d AR = 41.3% of 21d observations).

Ex-MSFT: n = 418, mean = +1.291%, t_HAC = +1.09

**G3: FAIL**

---

## 5. Verdict

**NULL — gate(s) failed: G1, G3 — no confirmer proposed; display only**

| Gate | Result |
|------|--------|
| G1 direction + |t_HAC|>=2 + BH-FDR q<=0.10 | FAIL |
| G2 split-half same-sign | PASS |
| G3 survives ex-MSFT | FAIL |

One or more gates failed. NULL printed. No collector build proposed. The signal may be deployed as event-context DISPLAY (informational flagging) for the special-situations desk without allocation or ranking influence. The null is consistent with the pre-registered honest prior.

---

## 6. Limitations and honest caveats

- **Microsoft concentration:** Microsoft contributes 378 of the mapped-public events.
  Results with and without Microsoft are both reported in Gate G3.
- **Sector beta only:** We use a single software-sector benchmark (IGV). Individual vendor
  betas vary; a stock-specific factor model would produce cleaner abnormal returns.
- **No intraday resolution:** Entry at next-day close may miss same-day price moves if
  KEV additions become known before market close.
- **Price availability:** Vendors without price data in massive_stock_day or yahoo are
  excluded. All public vendors in the map (Cisco/SAP/Juniper/F5/NETGEAR/Ubiquiti/SolarWinds/
  Progress) are present in the massive store; small-cap or truly delisted tickers account for
  the beta-coverage drop (722/931 = 78% beta coverage).
- **Calendar-time NW:** t-stats are computed on date-collapsed means (calendar-time portfolio
  method) to handle overlapping 21d windows and same-date events. n_events counts raw events;
  the NW degrees of freedom are the number of distinct entry_dates.
- **V4 not point-in-time:** The top-decile threshold for V4 (due-pressure weeks) uses the
  full-sample quantile over 2021-2026. A live version would require an expanding-window or
  trailing quantile. V4 results are descriptive only.
- **Ransomware sub-sample is small:** V2 events (185) may have insufficient
  power for reliable inference.
- **Cluster definition is heuristic:** The 5-trading-day cluster window is pre-registered
  but not empirically optimized.
- **This is a spike:** No collector wired, no nightly pipeline, no production scoring.

---

*Generated by `scripts/w2031_kev_vendor_shock_phase0.py` — wave-2 spike S1.*
*Not a validated signal. Nulls printed honestly.*

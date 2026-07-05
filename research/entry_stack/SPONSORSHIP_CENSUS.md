# Sponsorship Census — Oracle Panel Depth + Stock Mapping

**Filed:** 2026-07-05  
**Lane:** B0/B2 (Amendment 1 §C3, RUL-16)  
**Purpose:** Verify the history-depth split the amendment records; document stock-to-sector/subsector
mapping coverage; establish the sponsorship-state connector as display-only.

---

## 1. Oracle Panel Census

### 1.1  `data/oracle/panel_s.parquet` — Sector panel (11 nodes)

| Field | Value |
|---|---|
| Shape | 67,014 rows × 24 columns |
| Index | MultiIndex[node, date] |
| Nodes | 11 SPDR sector ETFs |
| Date range | **1998-12-22 → 2026-07-01** (~27.5 years) |

**Nodes:**

| Node | First date | Last date | Rows |
|---|---|---|---|
| XLB | 1998-12-22 | 2026-07-01 | 6,922 |
| XLC | 2018-06-19 | 2026-07-01 | 2,019 |
| XLE | 1998-12-22 | 2026-07-01 | 6,922 |
| XLF | 1998-12-22 | 2026-07-01 | 6,922 |
| XLI | 1998-12-22 | 2026-07-01 | 6,922 |
| XLK | 1998-12-22 | 2026-07-01 | 6,922 |
| XLP | 1998-12-22 | 2026-07-01 | 6,922 |
| XLRE | 2015-10-08 | 2026-07-01 | 2,697 |
| XLU | 1998-12-22 | 2026-07-01 | 6,922 |
| XLV | 1998-12-22 | 2026-07-01 | 6,922 |
| XLY | 1998-12-22 | 2026-07-01 | 6,922 |

**Velocity / Acceleration column non-null rates (sector panel):**

| Column | Non-null % | Null count |
|---|---|---|
| vel_1w | 99.92% | 55 |
| vel_1m | 99.66% | 231 |
| vel_3m | 98.97% | 693 |
| accel | 98.97% | 693 |
| accel_z | 97.60% | 1,606 |

**Census verdict (sector arm):** CONFIRMED. The amendment's claim is correct: vel/accel columns
on `panel_s` run **1998-12-22 → present with >97% non-null across all five columns**. The 9 original
sector ETFs (ex-XLC, ex-XLRE) start 1998-12-22; XLC launched 2018-06-19, XLRE launched 2015-10-08.
The sector arm has **full-history depth** for the W1/W2 stratification study as stated.

---

### 1.2  `data/oracle/panel_m.parquet` — Subsector panel (354 nodes)

| Field | Value |
|---|---|
| Shape | 443,916 rows × 24 columns |
| Index | MultiIndex[node, date] |
| Node count | **354** subsector nodes |
| Date range | **2021-07-06 → 2026-07-02** (~5 years) |

Node taxonomy (full list of 354 nodes omitted for brevity; categories include AI sub-verticals,
automation, biotech, clean energy, commodities, consumer, crypto, cybersecurity, defense, digital
entertainment, e-commerce, fintech, hardware, healthcare, housing, industrials, IoT, longevity,
materials, quantum, real estate, robotics, semiconductors, smart home, social, software, space,
telecom, transportation, wearables, and US sector overlay nodes).

**Velocity / Acceleration column non-null rates (subsector panel):**

| Column | Non-null % | Null count |
|---|---|---|
| vel_1w | 94.77% | 23,207 |
| vel_1m | 93.50% | 28,871 |
| vel_3m | 90.15% | 43,739 |
| accel | 90.15% | 43,739 |
| accel_z | 83.53% | 73,121 |

**Census verdict (subsector arm):** CONFIRMED. The amendment's claim is correct: `panel_m` starts
**2021-07-06** — the genuine "2021+" bound applies to all subsector velocity/acceleration data. Lower
non-null rates than the sector panel reflect the subsector panel's broader taxonomy (new nodes added
mid-history, shorter constituent histories). The subsector arm runs 2021+ only, as recorded.

---

## 2. Stock-to-Sector / Subsector Mapping

### 2.1  Approach — reuse existing repo stores

No new taxonomy was built. Three existing repo stores are reused in priority order:

1. **GICS breadth constituents** (`data/breadth/constituents.parquet`,
   `data/midcap_breadth/constituents.parquet`, `data/smallcap_breadth/constituents.parquet`) —
   S&P 500 + S&P 400 + S&P 600 Wikipedia-scraped members with GICS sector column.
   These are the most comprehensive and canonical GICS assignments in the repo.
   
   GICS → panel_s ETF mapping:
   - Materials → XLB
   - Communication Services → XLC
   - Energy → XLE
   - Financials → XLF
   - Industrials → XLI
   - Information Technology → XLK
   - Consumer Staples → XLP
   - Real Estate → XLRE
   - Utilities → XLU
   - Health Care → XLV
   - Consumer Discretionary → XLY

2. **Sector holdings ETFs** (`data/sector_holdings/*.parquet`) — current SPDR ETF constituent
   lists (XLB/XLC/XLE/XLF/XLI/XLK/XLP/XLRE/XLU/XLV/XLY). Used as a supplemental source
   for tickers not appearing in the breadth constituent files (large-caps that may have been
   omitted from the Wikipedia scrape).

3. **Theme baskets membership** (`data/baskets/membership.json`) — curated US theme baskets
   whose basket names appear as nodes in `panel_m`. Used for subsector (panel_m) lookup only.

### 2.2  Coverage statistics against the US board (signal_gate.json universe: 1,722 names)

| Mapping | Tickers mapped | Share of US board |
|---|---|---|
| Sector (panel_s arm) | 1,489 | **86.5%** |
| Subsector (panel_m arm) | 665 | **38.6%** |
| Either sector or subsector | 1,579 | **91.7%** |
| **Unmapped (sponsorship_state = unavailable)** | **143** | **8.3%** |

**Unmapped names (143):** These are primarily ADRs (BABA, BIDU, BEKE, BILI), ETFs (QQQ, BITB),
futures/FX symbols (BTC-USD, BZ=F), and small/micro-cap names not present in the S&P 1500
constituents or any curated basket. Their `sponsorship_state` is stamped `unavailable`.

### 2.3  Precedence rule for sponsorship lookup

Per the amendment §C3 frozen definition: sponsorship is looked up at the **latest completed date**
in the relevant panel. When a name is present in both a sector node and a subsector node, the sector
lookup provides the `sector_arm` state and the subsector lookup provides the `subsector_arm` state.
The top-level `sponsorship_state` field uses the **sector arm** (deeper history, more reliable),
falling back to `subsector_arm` if sector is unmapped, then `unavailable` if neither maps.

---

## 3. Frozen Sponsorship Definition

Per Amendment §C3 — unchanged, display-only, no tuning:

```
sponsorship_state := f(vel_sign, accel_sign) at latest completed panel date

  vel > 0  AND accel > 0  → "tailwind"
  vel < 0  AND accel < 0  → "headwind"
  mixed signs              → "neutral"
  latest panel row older than 5 trading days → "stale"
  name unmapped from any panel node         → "unavailable"
```

**vel** = `vel_1m` (primary; 1-month velocity, broadest signal-to-noise of the three horizons);  
**accel** = `accel` (signed acceleration of vel_1m).

Rationale for vel_1m: vel_1w is noisy; vel_3m is slow. vel_1m matches the 21d primary horizon
per RUL-13. Both vel_1m and accel must be non-null; if either is null, state degrades to `stale`.

---

## 4. Deviations from Amendment Spec

None. The amendment states "velocity sign + acceleration sign at the latest completed date →
tailwind / neutral / headwind / stale / unavailable." This is implemented exactly.

The 5-trading-day staleness threshold is evaluated against `computed_at` (today) vs the latest
date index in the panel. No smoothing, no threshold tuning.

---

## 5. Implementation Files

| File | Role |
|---|---|
| `engine/neuralweb/bottom_sensors.py` | Sponsorship connector added (functions `_load_oracle_panel`, `_sponsorship_state`; called in `_build_row`) |
| `engine/neuralweb/sector_map.py` | New file: builds and caches the stock→sector/subsector mapping from existing repo stores |
| `tests/test_bottom_sensors.py` | Sponsorship tests added (class `TestSponsorshipState`) |
| `research/entry_stack/SPONSORSHIP_CENSUS.md` | This document |

**Note:** `data/trial_ledger.jsonl` is NOT touched. The `esx_sponsorship` family is consumed only
when the W2 study runs. This PR ships the display connector only.

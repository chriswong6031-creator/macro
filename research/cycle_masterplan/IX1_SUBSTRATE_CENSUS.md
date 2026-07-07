# IX-1 Substrate Census — index-level hazard panel v0

**Built:** 2026-07-07 00:27 UTC
**Artifact:** `data/hazard/panel_index_v0.parquet` (producer `scripts/build_index_hazard_panel.py`)
**Turn epoch stamp:** `price_c4414dcb` — identical detector config to the member panel's primary stamp (close_price basis, detector v2).

SUBSTRATE ONLY — no trial, no preregistration, no truth-registry writes in this wave. The member panel `data/hazard/panel_price_c4414dcb.parquet` and its epoch are untouched. Event counts below are **pre-2024 (the embargo)** unless stated.

## Configuration choices (frozen facts for the future § registration)

| Choice | Value | Why |
|--------|-------|-----|
| ZigZag threshold | 14% for ALL index entities | Member builder uses TURN_DETECTOR_DEFAULTS: 14% us_sector, 14% country, 18% cn_sector. SPY takes the us_sector value per the substrate spec; blocs are detected at 14% in the member panel too (country family) — no divergence. |
| Detection basis | `close_price` (split-adj, div-UNadj), detector v2 | D4_SUBSTRATE §1 contract, same as member panel. |
| Month grid | 1995-01 → asof month-ends | Member builder convention. |
| rs_63d benchmark | ACWX → EFA fallback (effective: **EFA**) | SPY-vs-SPY is degenerate (identically 0), so us_market uses the world ex-US chain; blocs keep the member country-family chain. EFA's own rs_63d rows are therefore degenerate-0 (same property as EFA's country rows in the member panel). |
| k=6 age blend | us_market family = {SPY} only | Singleton family ⇒ family median = own median ⇒ blend degenerates to the own-median. Bloc family pools 7 entities. |
| sync_family source | `data/leadlag/sync_gauge.json` families.us_sector (SPY) / families.country (blocs) at the row month | Gauge country membership already excludes blocs (ruling A14). Exact month-key join. |
| Breadth/dispersion cross-section | Member panel us_sector members (SPY rows); country members EXCLUDING the 7 blocs (bloc rows) | Constituents only; matches gauge membership. Thresholds per FT-4: late = pos_osc≥70, early = ≤30, dispersion = std/100. |

## Rows per entity

| Entity | Family | Rows | Date span | Rows pre-2024 |
|--------|--------|------|-----------|---------------|
| AAXJ | bloc | 210 | 2009-01-31 → 2026-06-30 | 180 |
| EEM | bloc | 266 | 2004-05-31 → 2026-06-30 | 236 |
| EFA | bloc | 294 | 2002-01-31 → 2026-06-30 | 264 |
| ILF | bloc | 289 | 2002-06-30 → 2026-06-30 | 259 |
| SPY | us_market | 335 | 1998-08-31 → 2026-06-30 | 305 |
| VGK | bloc | 241 | 2006-06-30 → 2026-06-30 | 211 |
| VPL | bloc | 241 | 2006-06-30 → 2026-06-30 | 211 |
| VXUS | bloc | 179 | 2011-08-31 → 2026-06-30 | 149 |

## Event counts per entity × direction (pre-2024 embargo)

| Entity | Direction | Rows | y1 | y3 | y6 | Censored |
|--------|-----------|------|----|----|----|----------|
| AAXJ | up | 128 | 61 | 77 | 90 | 0 |
| AAXJ | down | 52 | 33 | 39 | 43 | 0 |
| EEM | up | 171 | 69 | 91 | 114 | 0 |
| EEM | down | 65 | 45 | 53 | 57 | 0 |
| EFA | up | 208 | 56 | 75 | 99 | 0 |
| EFA | down | 56 | 37 | 50 | 56 | 0 |
| ILF | up | 186 | 79 | 113 | 140 | 0 |
| ILF | down | 73 | 61 | 70 | 73 | 0 |
| SPY | up | 270 | 65 | 83 | 107 | 0 |
| SPY | down | 35 | 23 | 28 | 32 | 0 |
| VGK | up | 160 | 53 | 69 | 89 | 0 |
| VGK | down | 51 | 36 | 47 | 51 | 0 |
| VPL | up | 164 | 45 | 61 | 80 | 0 |
| VPL | down | 47 | 27 | 37 | 44 | 0 |
| VXUS | up | 115 | 37 | 45 | 57 | 0 |
| VXUS | down | 34 | 20 | 27 | 33 | 0 |

## Turn-count reality check (confirmed ZigZag turns per entity)

| Entity | Confirmed turns (all) | Peaks | Troughs | Confirmed pre-2024 |
|--------|----------------------|-------|---------|--------------------|
| AAXJ | 38 | 19 | 19 | 35 |
| EEM | 53 | 26 | 27 | 50 |
| EFA | 38 | 19 | 19 | 36 |
| ILF | 85 | 42 | 43 | 81 |
| SPY | 37 | 18 | 19 | 35 |
| VGK | 39 | 19 | 20 | 37 |
| VPL | 29 | 14 | 15 | 27 |
| VXUS | 19 | 9 | 10 | 17 |

## Covariate coverage (non-null share of rows)

| Covariate | us_market | bloc | all |
|-----------|-----------|------|-----|
| sync_family | 96.1% | 100.0% | 99.4% |
| phase_breadth_late | 96.4% | 100.0% | 99.4% |
| phase_breadth_early | 96.4% | 100.0% | 99.4% |
| pos_dispersion | 96.4% | 100.0% | 99.4% |

## Per-index KM estimability (age-pooled, pre-2024 rows)

`engine/index_km.py` age-pooled P(y_h=1 | entity, direction); entity-level estimate requires ≥30 rows per direction, else family-pooled fallback. 90% Wilson CIs.

| Entity | Direction | n | y3 events | P(y3) | 90% CI | Source |
|--------|-----------|---|-----------|-------|--------|--------|
| AAXJ | up | 128 | 77 | 0.602 | [0.529, 0.670] | entity |
| AAXJ | down | 52 | 39 | 0.750 | [0.641, 0.835] | entity |
| EEM | up | 171 | 91 | 0.532 | [0.469, 0.594] | entity |
| EEM | down | 65 | 53 | 0.815 | [0.724, 0.881] | entity |
| EFA | up | 208 | 75 | 0.361 | [0.308, 0.417] | entity |
| EFA | down | 56 | 50 | 0.893 | [0.806, 0.944] | entity |
| ILF | up | 186 | 113 | 0.608 | [0.547, 0.664] | entity |
| ILF | down | 73 | 70 | 0.959 | [0.902, 0.983] | entity |
| SPY | up | 270 | 83 | 0.307 | [0.263, 0.355] | entity |
| SPY | down | 35 | 28 | 0.800 | [0.669, 0.888] | entity |
| VGK | up | 160 | 69 | 0.431 | [0.369, 0.496] | entity |
| VGK | down | 51 | 47 | 0.922 | [0.836, 0.964] | entity |
| VPL | up | 164 | 61 | 0.372 | [0.312, 0.436] | entity |
| VPL | down | 47 | 37 | 0.787 | [0.675, 0.868] | entity |
| VXUS | up | 115 | 45 | 0.391 | [0.320, 0.468] | entity |
| VXUS | down | 34 | 27 | 0.794 | [0.661, 0.884] | entity |

## Verdict — what an IX-1 gate can realistically freeze

- SPY has 35 confirmed turns pre-2024 (17 peaks / 18 troughs). Pre-2024 SPY person-period rows: 270 up / 35 down. Every distinct turn contributes MANY correlated rows (one per month of the leg), so the effective sample is the TURN count, not the row count — a per-SPY age-STRATIFIED KM (per-bucket λ) is NOT estimable with honest CIs.
- Age-POOLED per-entity P(y_h | direction) IS estimable for SPY and the longer blocs at h=3/6 (see table above: entity-source cells), but with wide Wilson CIs; the family-pooled fallback covers the short-history blocs (VXUS starts 2011).
- Any IX-1 trial gate should therefore (a) test covariate INFORMATION (likelihood ratio / Brier vs the age-pooled KM baseline), not per-bucket hazard shape; (b) use turn-count-aware effective n (the member panel's rho_hat machinery, ruling A2); (c) treat us_market as a single-entity family — no cross-sectional pooling exists at index level for SPY.
- SPY covariate coverage starts 1999-08 (breadth/dispersion: first us_sector member-panel month) / 1999-09 (sync_family: first gauge month); earlier index rows carry NaN covariates, so any covariate trial effectively starts there. Bloc rows are fully covered (blocs list after the country members).

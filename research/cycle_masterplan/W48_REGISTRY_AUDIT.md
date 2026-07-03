# W4.8 Registry Audit — Cycle Intelligence Masterplan

**Date:** 2026-07-03  
**Wave:** W4.8 (Experiments-registry registration for every accruing measurement)  
**Ruling:** N4 — accruing measurements register in the admin Experiments tracker with come-back dates; epoch bumps auto-re-stamp them.

---

## 1 · Audit Findings

### Summary

| Status | Count | Action |
|---|---|---|
| **Missing** | 9 | Add entries for W2.4 graders (3 graders × 3 engines) |
| **Stale come-back dates** | 1 | Fix cycle-pit-backfill-w23 from text-based to date |
| **Path epoch renames** | 0 | All existing paths resolve (price_c4414dcb verified) |

### Missing Entries (9 total)

All 9 missing entries are the W2.4 promise-graders — they were shipped in PR #992 (2026-07-02) but never registered in the admin Experiments tracker:

#### W2.4 Sector Cycles Graders (3)
- **sector-cycles-turn-pr** — Turn Precision/Recall vs independent realized-extrema truth
  - track_json: `data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01 (~6 months for stable monthly re-grades)
  
- **sector-cycles-cone-coverage** — Cone coverage vs 0.80 nominal rate
  - track_json: `data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01
  
- **sector-cycles-reliability** — Directional Brier skill vs base rate
  - track_json: `data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01

#### W2.4 Country Cycles Graders (3)
- **country-cycles-turn-pr** — Turn Precision/Recall
  - track_json: `data/country_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01
  
- **country-cycles-cone-coverage** — Cone coverage
  - track_json: `data/country_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01
  
- **country-cycles-reliability** — Directional Brier skill
  - track_json: `data/country_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01

#### W2.4 China Sector Cycles Graders (3)
- **china-sector-cycles-turn-pr** — Turn Precision/Recall
  - track_json: `data/china_sector_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01
  
- **china-sector-cycles-cone-coverage** — Cone coverage
  - track_json: `data/china_sector_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01
  
- **china-sector-cycles-reliability** — Directional Brier skill
  - track_json: `data/china_sector_cycles/scorecards/promises_price_v1_zz14_v0.json`
  - come_back_on: 2027-01-01

### Stale Come-Back Dates (1 total)

**cycle-pit-backfill-w23**
- Current: `on_W2.4_grader_launch` (text-based, not a date)
- Fix to: `2027-05-01` (when n_rows ≥ 250 trading days and market-state PIT accrual matures; no time-based retirement for backfill itself)
- Rationale: Backfill is consumed by W2.4 graders; re-running on basis/epoch bumps is automatic via scripts/backfill_forward_logs.py (D2 §3). The come-back is advisory only (marking when to re-audit the artifact).

### Path Verification (All Passing)

✓ All 9 W2.4 grader track_json paths exist and resolve:
- `data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json` — ✓ exists (1913 lines)
- `data/country_cycles/scorecards/promises_price_v1_zz14_v0.json` — ✓ exists (1627 lines)
- `data/china_sector_cycles/scorecards/promises_price_v1_zz14_v0.json` — ✓ exists (1399 lines)

✓ Epoch renames verified: price_c4414dcb used in W2.2; all scorecard paths use the price_v1 schema (the canonical label for price-basis tapes).

✓ All W4.3 hazard entries point at valid paths:
- `data/cycle_ontology/hazard_model_price_c4414dcb.json` — ✓ exists (fitted logistic + isotonic recalibration)

✓ W4.5 market-state PIT path:
- `data/regime/market_state_history.parquet` — ✓ exists (created 2026-07-03, ready for append)

---

## 2 · Before/After Summary

### Registry Entry Count

| Aspect | Before | After | Δ |
|---|---|---|---|
| Total cycle-program entries | 5 | 14 | +9 |
| W2.4 grader entries | 0 | 9 | +9 |
| Stale text-based dates | 1 | 0 | −1 |
| Paths that DON'T resolve | 0 | 0 | 0 |

### Entries by Status

**Before:**
- accruing: cycle-pit-backfill-w23, country-fx-driven-turns, market-state-pit
- registered: country-fx-driven-turns
- proven: (none)

**After:**
- accruing: cycle-pit-backfill-w23, 9× W2.4 graders, country-fx-driven-turns, market-state-pit, 4× W4.3 hazard
- registered: country-fx-driven-turns
- proven: (none)

---

## 3 · Implementation Notes

### Come-Back Date Rationale

**W2.4 graders (2027-01-01)**
- Shipped: 2026-07-02
- Cadence: Monthly (re-run on each build, but verdict stability needs ≥6 calendar months of updates)
- Maturation: "LIVE cohort" needs n_eff ≥ 40 per cell (ruling A6, doctrine #8); monthly graders hit this in ~4–6 months
- Horizon: Come-back = 7 months out = start of 2027

**cycle-pit-backfill-w23 (2027-05-01)**
- Shipped: 2026-07-02
- Type: Historical backfill (not forward accruing)
- Trigger: Re-run on W2.2 basis bumps or D5 ZigZag-parameter bumps via `engine_fingerprint` check (automatic)
- Advisory date: ~1 year post-launch (aligns with market-state PIT maturity gate)

---

## 4 · Acceptance Criteria

- [ ] All 9 W2.4 grader entries added to data/experiments/registry_seed.json
- [ ] cycle-pit-backfill-w23 come_back_on changed from `on_W2.4_grader_launch` → `2027-05-01`
- [ ] JSON validates: `python3 -c "import json; json.load(open('data/experiments/registry_seed.json'))"`
- [ ] All track_json paths resolve: `for path in [entry['track_json'] for entry in ...: os.path.exists(path)`
- [ ] PR merges squash (W4.8 is mechanical, ruling N4 applied)
- [ ] No new entries ship with come_back_on in the past (as of 2026-07-03, all ≥2027-01-01)

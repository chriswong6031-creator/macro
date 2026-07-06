# Signal Lab Frontier Docket — Port + Fable Adjudication (L0)

**Lane:** feat/slf-frontier-port-adjudication  
**Date:** 2026-07-06  
**Status:** COMPLETE — 11 killed, 9 authorized (7 build / 1 probe / 1 pilot). No signal promoted.

---

## In plain English

Codex wrote a research backlog of 60 signal ideas ("the frontier docket") and ran an automated admission screen to decide which were worth a real empirical test. The screen said 23 were ready. Fable then checked every one of those 23 against what's already built, already tested, or already ruled out. Eleven turned out to be mirages — duplicates, feeds that stopped publishing, or ideas already killed in prior programs. Nine survived with real work attached. This port brings that entire work into the main codebase, adds Fable's verdicts as a visible column on the Signal Lab page, and corrects the docket where Codex's self-assessed data fields were wrong.

---

## Pre-registered gates

This lane is a port/adjudication layer, not an empirical harness. There are no rank-IC or HAC gates. The pre-registered deliverables were:

| Gate | Status |
|---|---|
| No `generated_utc` in `phase0_summary()` / frontier JSON keys | PASS — removed; timestamp is now only in research/ script outputs |
| All `*_zh` fields non-empty and not identical to EN for docket rows | PASS — `page_frontier_rows()` supplies bilingual labels |
| Integer suffix compare replaces lexicographic id compare | PASS — `_id_suffix()` function, tested |
| `FABLE_VERDICTS` covers exactly 23 original advance ids | PASS — 23 entries: 11 KILL + 1 ROUTE + 1 ACCRUE + 1 QUEUED + 7 BUILD + 1 PROBE + 1 PILOT |
| Fable ruling chip column on frontier panel (EN/ZH) | PASS — chip column rendered, ZH labels confirmed |
| Docket corrections applied (SLF-050 blocked, SLF-059 first_gate rewrite, SLF-012 note, SLF-006 tail struck, history_years fixes) | PASS — all 9 corrections applied |
| `screen_candidates()` determinism | PASS — test passes |
| No `ic`/`dsr` result keys in `frontier_rows` | PASS |
| `tests/test_signal_lab.py` — all 20 tests green | PASS |
| `scripts/check_validated_claims.py` | PASS — no forbidden "validated" claims |

---

## Verdict counts (post-correction)

Codex's original screen on 60 candidates: 23 advance_to_fable. After docket corrections:

| Verdict | Count | Notes |
|---|---|---|
| advance_to_fable | 19 | Dropped from 23: SLF-036/048/052 (history_years 1y → no ≥5y sample gate) |
| local_phase0_ready | 33 | Did not meet score ≥10.0 threshold |
| data_contract_first | 6 | Paid/external-heavy data required; SLF-050 (data_state=blocked, score 9.3 ≥ 6.5) routes here, NOT to graveyard_now |
| watchlist_or_reject | 1 | Score < 5.0 |
| graveyard_now | 1 | SLF-020 (prior_killed_level prior — Skew term-structure kink already killed; not SLF-050) |
| **Total** | **60** | |

## Fable adjudication of the 23 original advance candidates

### KILLED (11 — duplicates, prior kills, dead feeds, ruling-blocked)

| ID | Candidate | Reason |
|---|---|---|
| SLF-005 | Overnight/intraday tug-of-war | Ruling-blocked (Signal Commons EI P1.3); data also fails: massive_stock_day is 5y rolling, unadjusted opens |
| SLF-007 | COT exhaustion matrix | Cross-asset matrix illegal per Signal Commons R3; single-ingredient COT already in esx_pos_reset + capitulation gauge |
| SLF-010 | Lottery/MAX anti-chase | Prior kill (China MAX NO-GO); US lottery penalty already live in engine/stock_score.py; F3 anti-chase is the production gate |
| SLF-012 | FINRA short-volume stress | Already live (engine/short_volume.py); off-exchange-only, non-stationary denominator |
| SLF-025 | Opportunistic insider cluster | ESX A2 ran this 2026-07-05: unconditional strata adverse, opportunistic filter null/adverse |
| SLF-027 | Net issuance / dilution shock | net_issuance is existing signal_factory leg; edgar_dilution live; investment factor FDR-killed |
| SLF-034 | 8-K item taxonomy surprise | eightk_velocity already a factor leg; Special Situations desk runs 16-category taxonomy nightly |
| SLF-035 | Guidance revision language | engine/guidance_gap.py (Foresight T3) already built; store has 9 rows across 7 tickers |
| SLF-039 | Inventory build vs sales slowdown | Inventory annual-only at 55% coverage; quarterly impossible; Sloan accruals FDR-killed |
| SLF-050 | China northbound impulse | Feed dead 2024-08 (NORTHBOUND_FROZEN in engine/flow_velocity.py); timing IC ≈ dead |
| SLF-059 | EIA petroleum surprise | No free PIT consensus; EIA already display-only by ruling; 38y carry phase-0 wrong-signed |

### AUTHORIZED (9)

| Lane | ID | Verdict | Description |
|---|---|---|---|
| L2 | SLF-006 | BUILD | Event-study of existing treasury_supply.absorption_z (681 auctions, 2016→2026) |
| L4 | SLF-051 | BUILD | Market-level China margin ROC impulse, de-escalation framing, leave-one-cycle-out |
| L5 | SLF-001 | BUILD | New SEC FTD collector + panel + 21/63d rank-IC phase-0 with pre-registered confounds |
| L6 | SLF-055 | BUILD | New NY Fed primary-dealer collector + inventory/fails z confirmer |
| L7 | SLF-048 | BUILD | Wikipedia attention backfill 2015-07→now + wiki_attention_phase0 |
| L1 | SLF-053 | BUILD | Execute H3 as pre-registered (HK/Canada program); 25-pair A/H panel |
| L3 | SLF-056 | BUILD | AUC/event phase-0 of existing funding_stress composite; leave-one-episode-out |
| L8 | SLF-052 | PROBE | Data probe only: zt_pool backfill attempt; NO signal test |
| L9 | SLF-031 | PILOT | Feasibility pilot: 20-ticker lazy-prices spike + design doc |

### ROUTED (1): SLF-026 → ESX Amendment 2 reserve docket
### ACCRUING (1): SLF-036 → come back ≥2027-01-15 (PIT store began 2026-06-16)
### QUEUED (1): SLF-038 → factor-family pairlet budget

---

## PIT discipline

This lane contains no backtest. All data_state, pit, and history_years fields in the docket are registrations only. The Fable adjudication applied the following PIT checks:

- **SLF-050**: northbound net-buy column null since 2024-08-19 (NORTHBOUND_FROZEN verified in engine/flow_velocity.py). data_state corrected ready→blocked.
- **SLF-036**: equity_revisions store began 2026-06-16 (~12 daily snapshots); history_years corrected 5→1 (no PIT history to backtest).
- **SLF-048**: 126d on disk; API serves 2015-07→ but collector history is the PIT constraint; history_years corrected 9→1.
- **SLF-052**: ~5 dates on disk; history_years corrected 8→1.
- **SLF-001**: history_years corrected 16→22 (SEC FTD available from 2004).
- **SLF-012**: history_years corrected 8→16.
- **SLF-055**: history_years corrected 25→28.
- **SLF-005/010**: history_years corrected from stated values to 5 (massive_stock_day is rolling 5y, unadjusted opens).

---

## Files changed

| File | Action |
|---|---|
| `engine/signal_frontier_docket.py` | Created (ported from Codex) + all Step 2/3 fixes applied |
| `engine/signal_lab.py` | Import added; FRONTIER list (10 hand rows) + _frontier_row helper; build_scorecard extended with frontier_rows + frontier_phase0_summary |
| `templates/signal_lab.html.j2` | Frontier panel + Fable ruling chip column; CSS for chip styles |
| `scripts/signal_lab_frontier_phase0.py` | Created (ported from Codex) + timestamp moved to script outputs only |
| `research/SIGNAL_LAB_FRONTIER_2026-07-06.md` | Copied from Codex |
| `research/SIGNAL_LAB_FRONTIER_PHASE0_2026-07-06.md` | Regenerated (post-correction counts) |
| `research/signal_lab_frontier_phase0_2026-07-06.json` | Regenerated |
| `research/SIGNAL_LAB_FRONTIER_FABLE_ADJUDICATION_2026-07-06.md` | Copied from /tmp verbatim |
| `site/signal_lab.html` | Regenerated |
| `site/factordata/signal_lab.json` | Regenerated (no drifting timestamp in frontier keys) |
| `tests/test_signal_lab.py` | 11 new tests added (total 20, all green) |

---

## What was NOT done (honest scope)

- The 9 authorized build lanes (L1-L9) are separate work; no data was collected, no harness was run, no trial_ledger entries were appended. The frontier docket is the pre-empirical registration, not the harness.
- `site/signal_lab.html` was NOT copied from the Codex tree (it is stale there). It was regenerated fresh from the corrected engine.
- `site/factordata/signal_lab.json` was NOT copied from Codex; regenerated.

---

## Nightly wiring (for consolidation)

`build_signal_lab_page` is already wired at line 2956 of `scripts/build_site.py`. No new wiring required; the engine import and build_scorecard extension are the only changes to the render path.

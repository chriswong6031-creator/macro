# NW Cross-Asset Depth — R5 Wave-2 Masterplan

**Status:** ACTIVE. A **wave increment to the R5 macro-context rail** (`research/NW_MACRO_CONTEXT_RAIL_MASTERPLAN_BY_FABLE.md`, merged #1635) — not a new rail. Adds ONE display-only context source (cross-asset flows) that R5 left on the floor.
**Method:** Repo census (2026-07-08) → this plan (Claude/Opus main loop) → Sonnet build → Opus/main-loop review → same-day squash-merge. Model lanes per CLAUDE.md §Model routing: Sonnet builds every PR; main loop plans/reviews/merges.
**Authored:** 2026-07-08.

---

## §0. Problem (census-verified)

`scripts/build_crossasset.py` already computes the full cross-asset regime read — via `engine.cross_asset_trend.snapshot()` (keys: `regime, breadth, trend, ratios, carry, correlation, note, favored`) plus `engine.cross_asset.leadlag_snapshot()` (HAC+FDR lead/lag), `engine.global_liquidity.snapshot()`, `engine.funding_stress.snapshot()`, and the forex dollar-factor transmission rows. **All of it is rendered to `site/crossasset.html` and then discarded**: `data/crossasset/latest.json` persists only 5 flat keys (`date, regime, breadth, favored, correlation.verdict`). The R5 rail's world_state lobes read forex/transmission/bonds/commodity/regime — **never `data/crossasset` or the cross-asset engine** (grep-verified against the merged R5 branch). Result: Neural Web is blind to the numeric correlation-concentration/absorption ratio, TSMOM trend-breadth rows, intermarket ratios (copper/gold, stocks/gold, oil/gold), cross-asset carry, HAC+FDR lead/lag, global-CB-liquidity and funding-stress reads — the exact "are markets one bet, and who's moving first" signals the operator asked for.

## §1. Rulings

- **RUL-CA-1 (display/context only — inherits R5 A0/A1):** every R6 artifact carries `display_only: true`; no scoring, no rank, no veto, no hard gate, no sizing, no hedge ratios, no `favored`→buy-list. This is enforced by the validation record — cite in the module docstrings: `reports/cross-asset-phase0.md` (TSMOM beats a permutation null but FAILS the deflated-Sharpe gate and does not beat EW buy&hold after cost — regime read only), `reports/cross-asset-leadlag-phase0.md` (stable links are lag-1 timezone transmission, NOT durable prophecy — a context edge, never a hedge ratio), `reports/cross-asset-confirm-phase0.md` (near-zero incremental partial-IC in the modern half — a tension detector, not a crash forecast).
- **RUL-CA-2 (additive persistence, byte-safe):** extend `data/crossasset/latest.json` with ONE new `flows` sub-block. The existing 5 keys (`date, regime, breadth, favored, correlation`) stay byte-compatible — `scripts/build_vector.py`'s hub card reads them and must not break.
- **RUL-CA-3 (single-writer, RUL-P10):** `scripts/build_crossasset.py` remains the SOLE writer of `data/crossasset/latest.json` (already committed by `git add data/`). No new write path.
- **RUL-CA-4 (no new FDR family):** R6 opens ZERO conditioning studies. Any future "does cross-asset breadth/absorption condition signal reliability" question uses R5's reserved `fdr_family='macro_context'` with its own prereg + basis-split reporting (docketed §6, not built).
- **RUL-CA-5 (labels not claims):** the lobe ingests labels (`correlation=concentrated`, `breadth=0.3`, `absorption_pctile=0.7`, `leadlag_verdict=lag1_timezone`) and never emits a claim about future returns.

## §2. Build plan (ONE branch `feat/nw-crossasset-depth`, one squash PR)

- **PR-1 — persist + register.** Extend `build_crossasset.py::main()` to add a `flows` block to `data/crossasset/latest.json` (fields §3), fail-open per source (each sub-snapshot already wrapped in try/except → None). Add ISO `asof`. Register `crossasset-latest` in `config/synapse.yml` (tier: display, horizon_role: context, owner_program: macro-context-rail, asof_field: date, consumers: [engine/neuralweb/world_state.py, scripts/build_vector.py]) — count 260→261; bump `tests/test_signal_bus_doc.py` + regen SIGNAL_BUS.md. Run `check_synapse_reads.py` (declare every real reader) + `check_dag_conformance.py`.
- **PR-2 — wire to Neural Web (display-only).**
  - `engine/neuralweb/world_state.py`: new `cross_asset_flows` lobe following the **`_compose_factor_weather` fail-open pattern** (composer owns try/except, returns null-shape + registers a gap on failure, `_law.display_only` always). Fields §3.2. Wire in the assembly block + `sources[...]=asof`.
  - `engine/neuralweb/mastermind_context.py`: add a compact `cross_asset` sub-block to `_summarize_macro_weather` output (`{regime, correlation_concentration, absorption_pctile, intermarket_top[:3], breadth, leadlag_verdict}`) within the ≤12KB RUL-M8 budget.
  - `engine/neuralweb/ask_brain.py`: extend the R5 fx/rates/commodity `_classify_question` branch pattern to also catch `cross[- ]?asset|correlation|absorption|breadth|copper|intermarket|carry|lead[- ]?lag` (seeds `[read_world_state]` — no new tool). Skip terms the existing branch already matches.
  - Authority test wall: extend `tests/test_macro_context_authority.py` — `cross_asset_flows` lobe `display_only is True`, `assert_no_authority == []`, no Article-2 keys, world_state builds with the crossasset source missing (per-lobe gap), macro_weather still <200KB with the new sub-block, no-new-names (macro ETFs/futures roots only).
- **PR-3 (light, optional in same branch) — operator surface.** Add a "Cross-Asset Flows" row to `site/macro_context.html` (Macro Weather Station) via `scripts/build_macro_context.py` + `templates/macro_context.html.j2`: regime, correlation-concentration, absorption pctile, TSMOM breadth, top intermarket ratios, lead/lag verdict — with the display-only disclaimer. If it risks CI churn (title-i18n/nav-gap/template-site-sync), defer to a follow-up and ship PR-1+PR-2 only; note the defer in the status log.

## §3. Schema

### 3.1 `data/crossasset/latest.json` new `flows` block (additive)
```
"asof": "<iso>",                         # NEW ISO stamp (keep "date" display string)
"flows": {
  "schema": "crossasset_flows.v1",
  "display_only": true,
  "correlation": {"verdict": "concentrated", "absorption_pctile": 0.7, "n_markets": N},   # numeric, from snapshot.correlation
  "breadth": 0.3,                          # TSMOM breadth
  "trend_top": [{"asset","trend","z"} ...][:6],   # from snapshot.trend
  "intermarket": [{"pair":"copper_gold","ratio":..,"trend":".."} ...],   # from snapshot.ratios
  "carry": {..compact..},                  # from snapshot.carry
  "leadlag": {"verdict": "lag1_timezone|null", "links": [{"src","dst","lag","fdr_q"} ...][:6]},  # honest null when None
  "global_liquidity": {..compact..|null},  # from global_liquidity.snapshot
  "funding_stress": {..compact..|null},    # from funding_stress.snapshot
  "note": "display-only regime read; TSMOM fails DSR (cross-asset-phase0), lead/lag=lag-1 timezone (cross-asset-leadlag-phase0) — not a strategy/hedge-ratio"
}
```
Every sub-field is None/[] when its source snapshot is absent (fail-open); no field is fabricated.

### 3.2 world_state `cross_asset_flows` lobe
`{asof, source:"data/crossasset/latest.json", regime, breadth, correlation:{verdict,absorption_pctile,n_markets}, intermarket[:4], carry_summary, leadlag:{verdict,n_links}, global_liquidity_dir, funding_state, display_only:true, stale}` + gap on missing file.

## §4. Tests
- `test_crossasset_flows_persisted` — build_crossasset writes the `flows` block; the 5 legacy keys byte-unchanged.
- `test_crossasset_flows_failopen` — missing sub-snapshots → None sub-fields, no crash.
- world_state: `cross_asset_flows` present on real data; absent-file → per-lobe gap, other lobes unaffected.
- authority wall (see PR-2).
- `test_signal_bus_doc` count 261; `check_synapse_reads` rc=0; `check_dag_conformance` clean.

## §5. Scope fences (does NOT)
- No score/rank/gate/veto/sizing anywhere; absorption is NOT a risk-off gate; lead/lag is NOT a hedge ratio; `favored` is NOT a buy list.
- No new FDR family, no conditioning study, no "which signals work when" claim (that's §6, prereg-gated).
- No rebuild of the cross-asset page's validation; no recompute of the CONTESTED TSMOM verdict.
- No touching Article-2 surfaces (`alert_triage, board_ordering, top_setups, attention_queue, push_floor`).
- No breaking the existing `data/crossasset/latest.json` 5-key contract (build_vector hub card).

## §6. Docket (recorded, NOT built)
- **Cross-Asset Conditioning study:** "does correlation-concentration / absorption / breadth / fast-family lead-lag condition forward signal reliability beyond existing regime/drawdown gauges?" → registered under `fdr_family='macro_context'`, episode-clustered, basis-split, nulls printed, ≥60d pit_live accrual. Unblocked only after this wave + accrual. (Mirrors R5 §9 Atlas discipline.)

---

## §7. Wave-3 — Cross-Asset Utility (2026-07-18, Fable main-loop adjudication)

**Status:** ACTIVE build wave. Operator directive: make the cross-asset/forex layer genuinely useful — richer features, deeper NW integration, consumption by other engines' calculations, and a doctrine-compliant page revamp. Census 2026-07-18 (6-lane + opus-verified) is the evidence base.

### §7.1 Rulings

- **CA-W3-R1 (calculation-tier = shadow + confluence, never instant authority).** "Used in calculations" is granted through the house's proven lawful forms, not by voiding RUL-CA-1: (a) context/confluence attaches to non-Article-2 engines (free at display tier); (b) a **shadow escalator** mirroring CGL-R4 mechanics exactly (see §7.3); (c) pit_live accrual feeding the §6 conditioning study. RUL-CA-1's evidence base (three phase-0 nulls) still stands; overturning it without new graded evidence would be laundering. Promotion of the shadow lane to live radar authority requires **≥30 graded shadow rows + do-no-harm vs incumbent**, earliest review **2026-10-17** (shared RSR-R2 clock), and an explicit operator ruling.
- **CA-W3-R2 (escalator construction).** The shadow pressure gauge is the **continuous absorption percentile** (Kritzman-Page one-bet fragility, `absorption_pctile_5y`) — a single continuous gauge, deliberately NOT a K-of-N flip-count (RSR-R6a/b killed the count-conjunction class). Escalation condition mirrors CGL verbatim: `pressure ≥ 0.90 AND incumbent ≥ watch → shadow = incumbent + 1 band` (capped at risk-off; never a new origin scare). US market only in W3; intl extension needs its own wave.
- **CA-W3-R3 (accrual is free; nulls print).** `data/crossasset/history.jsonl` (nightly-lane-gated, single writer build_crossasset per RUL-CA-3) accrues the pit_live rows the §6 study requires. Building accrual is never blocked by the display-only status (house epistemics: a null never blocks building or accrual).
- **CA-W3-R4 (flows.v2 additive).** `flows` schema bumps to `crossasset_flows.v2`, strictly additive over v1; the 5 legacy top-level keys stay byte-compatible (RUL-CA-2 unchanged). New: correlation numerics + weekly absorption spark, compact `confirm`, compact `dollar`, enriched `leadlag`, liquidity impulse, `regime` inside flows.
- **CA-W3-R5 (trend universe globalizes; concentration universe frozen).** Trend board adds EFA / EEM / TLT legs (display regime read; breadth renormalizes by n). The 6-market **concentration** universe is FROZEN — its 5y absorption percentile history defines the shadow pressure gauge; membership churn would silently reset the ruler.
- **CA-W3-R6 (page port to doctrine).** crossasset.html is rebuilt under DESIGN_DOCTRINE: stance on every panel, plain words at rest, all statistics (HAC t, FDR q, DSR, permutation p) demoted to Tier-2 receipts. Honesty survives translation: the TSMOM/lead-lag/confirm nulls are stated in plain words on Tier 1 with technical receipts on hover.

### §7.2 Build map (one branch, one squash PR, source-only)

W3-A build_crossasset flows.v2 + history + hero composition · W3-B `engine/crossasset_shadow.py` + forward log · W3-C NW/consumer wiring (confluence node `macro:cross_asset_flows`, world_state/mastermind additive fields, fx_dollar stress read, build_site US-radar context attach beside the CGL chip, vector hub one-bet line) · W3-D template rebuild · W3-E registration/reconciliation (synapse entries + consumers, SIGNAL_BUS regen, conformance + authority walls).

### §7.3 Shadow lane spec

Module `engine/crossasset_shadow.py`, invoked from build_crossasset (runs post-`engine.run` same-night; COLLECT_LANE=nightly in the engine job). Artifact `data/crossasset_shadow/latest.json` `{asof, pressure_pctile, incumbent_state, shadow_state, escalated, display_only: true}`. Forward log `data/risk_radar/forward_log_crossasset.jsonl`, appended ONLY when the US audit ledger lane is armed (`engine/risk_radar_audit.ledger_lane_armed`), row schema mirroring CGL contagion rows (graded on the same ≥5%-drawdown h5/h10/h21 ruler). Fail-open everywhere; a missing radar state or absorption read logs a warning and writes nothing.

### §7.4 Scope fences (Wave-3 does NOT)

- No Article-2 surface reads any W3 output (`alert_triage, board_ordering, top_setups, attention_queue, push_floor`); alert_triage's pre-existing `cross_asset` read (pre-R6 leaf via regime/latest.json) is untouched.
- No conditioning study runs (RUL-CA-4 stands; §6 docket unchanged); no recompute of any phase-0 verdict.
- No change to the concentration market set, thresholds, or the incumbent US radar calibration; the shadow lane changes ZERO live states.
- No new FX radar leg (RRI-S2 NO-GO respected — incumbent one-sided depreciation legs stand).
- No positioning fusion (COT stays context-tier per Signal Commons).

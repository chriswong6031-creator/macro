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

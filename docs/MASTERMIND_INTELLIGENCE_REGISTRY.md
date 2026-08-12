# Mastermind Intelligence Registry

> GENERATED — do not edit. Regenerate with `python3 scripts/build_intelligence_registry.py`.
> Source of record: `data/intelligence_registry.json`. Curated overlay: `config/intelligence_registry_overlay.yml`.

One row per intelligence **engine** — the unit of account the Evaluation OS scorecard (T7), the CEO view (T8) and tier routing (T12) all hang on.

## Unit of account

`engine = (producer, owner_program) from config/synapse.yml`, id `{producer}::{owner_program}`.

**378 engines** over **642 synapse artifacts** (7 cells excluded as `not_an_engine`). The partition is total and disjoint: every artifact belongs to exactly one engine, which is the invariant `scripts/check_intelligence_registry.py` enforces.

### What this unit gets wrong

1. **32 of 378 engines mix artifact tiers**, so the engine-level `authority` roll-up (a MAX) OVERSTATES authority for the low-tier siblings inside those cells. Understatement is the dangerous direction — C-2 is an understatement defect — but this is a real inaccuracy. **A consumer acting per-artifact must read `artifacts[].artifact_authority`, never the engine roll-up.**
2. **244 of 378 engines are singletons.** For those rows "engine" is really "artifact"; the registry is artifact-shaped at the tail.
3. **It does not answer "which code do I fix".** A producer spanning several programs yields several engines, so a code-level regression in one file surfaces as several independent rows. `owner_program_span` makes those visible.

## Distributions

| Dimension | Value | Engines |
|---|---|---|
| authority | `display` | 355 |
| authority | `engine_input` | 12 |
| authority | `user_ranking` | 6 |
| authority | `gate_size` | 5 |
| graded_by_design | no — not yet | 195 |
| graded_by_design | yes | 112 |
| graded_by_design | no — descriptive | 71 |
| validation_state | `phase0` | 376 |
| validation_state | `validated` | 1 |
| validation_state | `accruing` | 1 |
| ledger waterfall rule | 1 | 38 |
| ledger waterfall rule | 2 | 1 |
| ledger waterfall rule | 3 | 65 |
| ledger waterfall rule | 4 | 8 |
| ledger waterfall rule | 5 | 266 |

## Content findings (law `epistemics.engine_authority_evidence`, warn-tier)

| Code | Engines |
|---|---|
| `AUTHORITY_WITHOUT_EVIDENCE` | 21 |
| `OUTPUT_CLASS_MISSING` | 88 |
| `SCORED_PATH_SURFACES_INCOMPLETE` | 45 |

These are PRE-EXISTING CONDITIONS of the corpus, not regressions any PR author caused. That is why the owning law is warn-tier and exits non-zero only under `--strict`.

### C-1 — authority above `display` with no evidence pointer

| Engine | Authority | Heal |
|---|---|---|
| `engine/ai_desk.py::qualitative-intelligence` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `ai-desk-theses` |
| `engine/china_radar_ledger.py::china-alpha` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `china-radar-ledger` |
| `engine/china_sector_cycles.py::china-alpha` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `china-sector-cycles-forward-log` |
| `engine/china_standout_track.py::china-alpha` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `china-board-ledger` |
| `engine/demand_ledger.py::qualitative-intelligence` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `demand-chain-theses` |
| `engine/name_score_grader.py::china-alpha` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `name-score-calls` |
| `engine/policy_intent_desk.py::qualitative-intelligence` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `policy-intent-theses` |
| `engine/run.py::engine-fix` | `user_ranking` | add `qual_ladder_ref` to `config/synapse.yml` for `regime-latest` |
| `engine/spine.py::qualitative-intelligence` | `user_ranking` | add `qual_ladder_ref` to `config/synapse.yml` for `spine-predictions` |
| `engine/stock_desk.py::qualitative-intelligence` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `stock-desk-theses` |
| `engine/thematic_desk.py::qualitative-intelligence` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `thematic-desk-theses` |
| `engine/track_record.py::setup-species` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `signal-archive-track-record` |
| `scripts/backtest_vol_overlay.py::options-alpha` | `gate_size` | add `qual_ladder_ref` to `config/synapse.yml` for `vol-regime-basket-overlay-gate` |
| `scripts/build_baskets.py::sector-pulse` | `user_ranking` | add `qual_ladder_ref` to `config/synapse.yml` for `site-baskets-json` |
| `scripts/build_china_library.py::china-alpha` | `user_ranking` | add `qual_ladder_ref` to `config/synapse.yml` for `site-china-standouts` |
| `scripts/build_sector_cycles.py::cycle-intelligence` | `engine_input` | add `qual_ladder_ref` to `config/synapse.yml` for `sector-cycles-forward-log` |
| `scripts/build_signal_quality.py::setup-species` | `user_ranking` | add `qual_ladder_ref` to `config/synapse.yml` for `signal-archive-mtf` |
| `scripts/build_stock_library.py::us-stocks-prebreakout` | `user_ranking` | add `qual_ladder_ref` to `config/synapse.yml` for `site-signal-gate` |
| `scripts/calibrate_vector.py::btc-vector` | `gate_size` | add `qual_ladder_ref` to `config/synapse.yml` for `vector-calibration` |
| `scripts/fit_cycle_hazard.py::cycle-intelligence` | `gate_size` | add `qual_ladder_ref` to `config/synapse.yml` for `hazard-model` |
| `scripts/validate_vol_regime.py::options-alpha` | `gate_size` | add `qual_ladder_ref` to `config/synapse.yml` for `vol-regime-gate` |

The prescribed heal fills `qual_ladder_ref` in `config/synapse.yml` — it repairs the canonical source rather than papering over the gap in a side file.

## Excluded cells

| Engine id | Source | Reason |
|---|---|---|
| `::options-intelligence-program` | derived | derived: empty producer token — no code advances this artifact |
| `<HAND_MAINTAINED>::neural-web` | derived | derived: placeholder producer token '<HAND_MAINTAINED>' — not a repo module |
| `<MANUAL>::ird` | derived | derived: placeholder producer token '<MANUAL>' — not a repo module |
| `<MANUAL>::macro-release-intel` | derived | derived: placeholder producer token '<MANUAL>' — not a repo module |
| `<MASTERMIND_EXTERNAL>::mastermind-feedback-contract` | derived | derived: placeholder producer token '<MASTERMIND_EXTERNAL>' — not a repo module |
| `<RESEARCH_FACTORY_INGEST>::research-factory` | derived | derived: placeholder producer token '<RESEARCH_FACTORY_INGEST>' — not a repo module |
| `<RESEARCH_FACTORY_MONITOR>::research-factory` | derived | derived: placeholder producer token '<RESEARCH_FACTORY_MONITOR>' — not a repo module |

## Engines above `display` authority

| Engine | Authority | Rule | Ledger | Graded by design | Evidence |
|---|---|---|---|---|---|
| `engine/ai_desk.py::qualitative-intelligence` | `engine_input` | c | `data/ai_desk/theses.jsonl` | yes | **null** |
| `engine/altdata_ledger.py::qualitative-intelligence` | `engine_input` | c | `engine/altdata_ledger.py` | yes | altdata.action, altdata.signal_score |
| `engine/china_radar_ledger.py::china-alpha` | `engine_input` | c | `data/china_radar/ledger.parquet` | yes | **null** |
| `engine/china_sector_cycles.py::china-alpha` | `engine_input` | c | `data/china_sector_cycles/forward_log.parquet` | yes | **null** |
| `engine/china_standout_track.py::china-alpha` | `engine_input` | c | `data/china_standout_track/board.parquet` | yes | **null** |
| `engine/demand_ledger.py::qualitative-intelligence` | `engine_input` | c | `engine/demand_ledger.py` | yes | **null** |
| `engine/name_score_grader.py::china-alpha` | `engine_input` | c | `data/name_score/us_calls.parquet` | yes | **null** |
| `engine/policy_intent_desk.py::qualitative-intelligence` | `engine_input` | c | `data/policy_intent/theses.jsonl` | yes | **null** |
| `engine/run.py::engine-fix` | `user_ranking` | b | `data/board_ledger/ca_board.parquet` | yes | **null** |
| `engine/spine.py::qualitative-intelligence` | `user_ranking` | b | `data/spine/predictions.parquet` | yes | **null** |
| `engine/stock_desk.py::qualitative-intelligence` | `engine_input` | c | `data/stock_desk/theses.jsonl` | yes | **null** |
| `engine/thematic_desk.py::qualitative-intelligence` | `engine_input` | c | `data/thematic_desk/theses.jsonl` | yes | **null** |
| `engine/track_record.py::setup-species` | `engine_input` | c | `data/signal_archive/track_record.parquet` | yes | **null** |
| `scripts/backtest_vol_overlay.py::options-alpha` | `gate_size` | a | `data/vol_regime/basket_overlay_gate.json` | yes | **null** |
| `scripts/build_basket_washout_state.py::blocked-entry-override` | `gate_size` | a | `site/factordata/basket_washout_state.json` | yes | research/RECLAIM_VETO_CONDITIONAL_PREREG.md |
| `scripts/build_baskets.py::sector-pulse` | `user_ranking` | b | `none` | no — not yet | **null** |
| `scripts/build_china_library.py::china-alpha` | `user_ranking` | b | `site/factordata/cn_track_ledger.json` | yes | **null** |
| `scripts/build_sector_cycles.py::cycle-intelligence` | `engine_input` | c | `data/sector_cycles/forward_log.parquet` | yes | **null** |
| `scripts/build_signal_quality.py::setup-species` | `user_ranking` | b | `none` | no — not yet | **null** |
| `scripts/build_stock_library.py::us-stocks-prebreakout` | `user_ranking` | b | `data/us_board_ledger/retro_grades.parquet` | yes | **null** |
| `scripts/calibrate_vector.py::btc-vector` | `gate_size` | a | `data/vector/calibration.json` | yes | **null** |
| `scripts/fit_cycle_hazard.py::cycle-intelligence` | `gate_size` | a | `data/hazard/model_price_c4414dcb.json` | yes | **null** |
| `scripts/validate_vol_regime.py::options-alpha` | `gate_size` | a | `data/vol_regime/gate.json` | yes | **null** |

## Field provenance

| Field | Derived from | Curated? |
|---|---|---|
| `engine_id`, `producer`, `owner_program`, `owner_program_span` | `config/synapse.yml` cell key | no |
| `artifacts`, `consumers` | `config/synapse.yml` | no |
| `authority`, `authority_evidence` | `tier` + `scored_path_surfaces` + one consumer hop | no |
| `evidence_ref` | `qual_ladder_ref` | no |
| `ledger`, `ledger_evidence` | ledger-module glob, AST desk scan, tier, consumer hop | no |
| `declared_horizon` | `horizon_role` + qledger `horizon_d` | no |
| `graded_by_design` | `ledger` + all-infrastructure test | overlay may make ONE transition |
| `validation_state` | `data/species/registry.json` | overlay may ratify terminal states only |
| `output_class` | — (no canonical source encodes it) | yes, required only when the evaluation gate trips |
| `not_an_engine` | placeholder/frozen producers | yes, for judgment exclusions |

`authority` and `evidence_ref` are deliberately NOT curated. `_REQUIRED_ARTIFACT_KEYS` (`engine/neuralweb/synapse.py:52`) is a required-key set, not an exact-key set, so a hand-typed `authority:` key in `synapse.yml` would land as unenforced free text next to the already-unenforced `scored_path_surfaces` — reproducing the exact defect class C-1 and C-2 are instances of, one field later.

## Volatile fields and the split drift law

`data/qledger/claims.jsonl` is append-only and `data/species/registry.json` moves independently of any PR. A byte-equality gate over fields sourced from them would be a scheduled red — the first nightly row written to a currently-empty desk would flip a field and red every open PR. So the HARD law (`governance.intelligence_registry_integrity`) compares the STRUCTURAL PROJECTION (this file with the volatile paths stripped), and a stale corpus snapshot is a warn-tier content finding instead.

Volatile paths, declared in `meta.volatile_fields` so the projection is self-describing:

- `declared_horizon.horizon_d`
- `ledger_evidence.corpus_rows`
- `ledger_evidence.corpus_checked`
- `validation_state`
- `validation_state_evidence`

Corpus read on the last regeneration: species=True (n=27), qledger=True (n_desks=13).


# NW Macro Context Rail (R5) — Masterplan (by Fable)

**Ratified:** 2026-07-06
**Status:** ACTIVE program. Charters rail R5 (macro context intake & memory) — a new §2-class rail entry under the docket taxonomy; the docket remains the taxonomy authority.
**Method:** Codex integration paper (`research/NEURAL_WEB_MACRO_CONTEXT_INTEGRATION_FOR_CLAUDE.md`, 2026-07-06) → 8-lane repo census (Sonnet, file-level evidence, against origin/main e0e9f71cc6) → program draft (Fable) → 3-lens Opus red-team (house-law/feasibility; epistemics/PIT-leak; build-executability — all APPROVE_WITH_EDITS) → this ratified revision (Fable adjudication). §0.5 prints what the red-team falsified in the draft, per house law.
**Context:** Fable access ends ~2026-07-08. This program locks full implementation specs so every wave is executable by Opus/Sonnet without frontier design input.

---

## §0. Census corrections to the Codex paper (printed per house law)

The 8-lane census verified the paper's core finding — macro artifacts are not first-class Neural Web context — and corrected six claims:

1. **STALE (deploy):** "`site/neuralwebdata/mastermind_context.json` is not committed/published" — it IS git-tracked at origin/main (landed in #1567, 2026-07-05 22:56 PDT, single commit, 165 KB), and `scripts/build_nw_mastermind_context.py:75-76` already writes the site copy itself. The live 404 root cause is different: (a) the VPS 3-minute update cron (`app/deploy/update.sh` → rsync to `site.served/`) is demonstrably not propagating (Caddy origin 404s with `eo-cache-status: MISS` hours after merge — ops issue, needs a manual `macro-update` run and log check on the droplet), and (b) structurally, neither `render.yml` nor `engine-render.yml` invokes `build_nw_mastermind_context` — the file freezes between nightlies and express-lane renders cannot rescue it. No smoke check exists for the URL class.
2. **NAMING (taxonomy):** the paper calls the proposed additions "lobes." Under the docket taxonomy (`NW_FUTURE_LOBES_DOCKET` §1: LOBE = own objective/FDR/falsifiers; RAIL = serves every lobe; WAVE = increment to existing), none of these qualify as LOBEs — `rates_transmission`, `fx_dollar`, `rates_credit`, `commodity_context` are built display-only *leaves* (RATE_INFLATION_TRANSMISSION.md: all legs failed purged-CV; FOREX_DASHBOARD.md: display seams per DISPLAY_VS_SCORING_MANIFEST; BOND_HEALTH_DASHBOARD.md: built + calibrated). This program is therefore chartered as a **RAIL — R5, macro context intake & memory**. The term "lobe" below refers exclusively to world_state blackboard sections and bridge summarizer blocks, never to docket LOBEs. The two-lobe concurrency cap (a LOBE cap; rails exempt — R1+R3 were chartered alongside L1+L3) is untouched.
3. **STALE (spine):** "3,841 of 287,929 rows have regime stamps; qledger nulls need a backfill" understates the substrate problem: the four rich stamps (`vol_regime`, `fused_risk_label`, `risk_radar_state`, `rate_pressure`) live in `data/regime/regime_vector.parquet` which has **2 rows** (2026-07-01, -02) — deep backfill of those requires re-running the regime-vector computation, not a join. `rate_pressure` is null even in the two existing rows (upstream defect). BUT deep **quad** histories exist and are joinable, in four separate per-market parquets: `data/regime/regime_history.parquet` (US-only, 1971→), `data/china_regime/regime_history.parquet` (1997→), `data/hk_regime/regime_history.parquet` (1986→), `data/canada_regime/regime_history.parquet` (1979→). `engine/qledger.py:backfill_regime_stamps()` (line 414) exists for the qledger gap and yields rows as regime_vector grows (near-term yield ≈ 2 dates).
4. **EXISTS ALREADY (history):** `scripts/archive_signals.py` already appends nightly flattened snapshots to `data/signal_archive/{us_regime,forex,bond_health,commodity,china_regime,hk_regime,canada_regime}.parquet` (started 2026-06). The MANIFEST is missing `transmission` and `market_state` entries. R5 extends this mechanism instead of inventing a parallel store.
5. **EXISTS ALREADY (world_state factor lobe):** world_state already carries `factor_weather` and `options_weather` lobes and an `alerts` summary; intelligence divergences already feed contradiction pair-e. The paper's `factor_weather_v2` is reshaped to an in-place enrichment of the existing lobe, never a new "v2" name (which reads as a kernel-promotion and is prohibited before the 2026-10-01 FDR batch).
6. **BRIDGE POSTURE:** the Mastermind bridge is dark-shipped (`MASTERMIND_NW_CONTEXT=OFF`, arming = 5 consecutive clean builds, come-back 2026-07-19). R5 adds bridge *content* (a compact `macro_weather` summarizer) but changes nothing about arming, candidate scope, or the five authority booleans (all false).

## §0.5 Red-team corrections to the draft (printed per house law)

The 3-lens Opus red-team (2026-07-06) returned APPROVE_WITH_EDITS ×3 and falsified the following draft claims; all are fixed in this revision:

1. **UNBUILDABLE (registry):** the draft's synapse entry template omitted three validator-REQUIRED fields — `owner_program`, `format`, `freshness_sla_hours` (`engine/neuralweb/synapse.py:50-52`); CI would hard-fail. §4.1 now states the full template.
2. **SOLE-ADVANCER VIOLATION (transitions):** `transitions.jsonl` was append-only but not idempotent — a routine nightly re-run would duplicate transition rows. §6.1 now mandates same-asof replacement semantics on re-run, with a test.
3. **DEFEATED A DOCUMENTED INVARIANT (own-market quads):** the draft's historical helper would have filled `quad_hard_label` with HK/China/Canada national quads, reversing query.py:159's "US primary on all lanes; HK/CA/CN own-market regime null by design" and poisoning the OR-matched `regime=` filter with four incompatible quad taxonomies. Fixed: `quad_hard_label` stays US-primary everywhere; new `market` + `own_market_quad` columns carry national labels (§6.2/§6.3).
4. **MIS-ROUTED MARKET INFERENCE (qledger):** "market inferred from ledger" fails for qledger, which mixes US entities with China A-shares (600030.SS, 300024.SZ, …) in one ledger; and the draft's worry about track_record HK/CN rows was misdirected — track_record is verified all-US. Fixed: routing is by (ledger, symbol-suffix): `.SS`/`.SZ` → CN, `.HK` → HK (§6.3).
5. **FORWARD LEAK (min-asof):** stamping the composite snapshot with the MIN of source asofs let a Jul-04 spine row bind to a snapshot secretly containing Jul-05 FX labels. The draft's "PIT-safe by construction" claim was FALSE. Fixed: the join-key asof is the MAX of present source asofs; `oldest_component_asof` is kept as a staleness diagnostic (§6.1).
6. **HIDDEN SCORE (recession band):** `recession_risk_band = low/<10, mid/10-25, high/>25` hand-set a threshold on an ambiguous source (nyfed_prob=16.0 % vs bonds' incompatible 3.93 float) and destroyed the underlying value at write time. Fixed: the label ingests transmission's existing categorical `yield_curve.recession.risk` verbatim; no new banding anywhere in the v1 vocabulary (§6.1).
7. **WRONG DEFAULT (stamp basis):** "default None = both bases" would let the future Atlas silently pool recomputed-history labels (fabricated in 2026 from revised vintages) with pit_live labels. Fixed: `regime=`-filtered queries default to `stamp_basis='pit_live'`; recomputed rows are opt-in; the Atlas registration mandates basis-split reporting (§6.2/§9). RUL-M7 now cites the concrete precedent module `engine/vintage_stamp.py`.
8. **UNDECLARED CI GATE (dag.yml):** the draft added steps to daily.yml/engine-render.yml/render.yml without mentioning `config/dag.yml`; `scripts/check_dag_conformance.py` (hard CI gate) reds on undeclared lane drift. Every workflow-touching PR now updates dag.yml in the same commit and runs the checker locally (§4.3, §6.1, §8.1).
9. **REPRODUCED MergeError (dtype):** `merge_asof` on the spine's string `as_of` against DatetimeIndex history parquets raises MergeError (reproduced on pandas 3.0.3). §6.2/§6.3 now specify: `reset_index()` the history parquets, convert both keys via `pd.to_datetime`, sort, join backward, restore string.
10. **WOULD-RED TEST (fixture):** `test_world_state.py:312` asserts `non_contra_gaps == []` against a `_full_tree` fixture that writes none of the six new sources — "suite green untouched" was impossible. PR-B extends `_full_tree` (§5.5).
11. **WRONG EXEMPLAR (composer pattern):** `_compose_regime()` is a pure transform; the fail-open try/except + gaps live in the assembly block or in `_compose_factor_weather`-style composers. §5.3 now cites the correct siblings.
12. **INVISIBLE NODES (committee page):** `committee.html.j2:639` hard-whitelists `SHOW_TYPES = {engine, regime, sector}` and only rescues edge-nodes for confirms/contradicts — the draft's macro nodes and headwind/tailwind edges would silently not render. PR-D now edits the page (§7.1).
13. **STAGE-GATE CONTRADICTION:** PR-A registered producers that don't exist until PR-C/PR-E, contradicting the producer-existence validator. Registrations now live in the PRs that create their producers; acceptance gates are **branch-final** (stage commits may be red in isolation; the single squash PR is the CI unit) (§2).
14. **REDUNDANT FIX DROPPED:** the draft's `build_site.py` copy step duplicated a write the bridge builder already performs; the load-bearing fix is the engine-render.yml step + smoke probes (§4.3).
15. Minor corrections folded in: RUL-M5 restated per RUL-P10's actual law (blanket `git add data/` is not gated by the registry); RUL-M9/§9 unified on the adapter-helper form for historical stamps (the draft was self-contradictory); "4 orphan test files" → 5 (+ admin panel test into the existing job; all 163 tests verified green today); `scope_type='macro'` is pre-declared vocabulary being populated for the first time, not a new enum value; §0 #3 four-parquet phrasing; ask-brain macro branch scoped to terms the existing regime branch does NOT already catch, seeds `[read_world_state]` only; archive_signals keeps `date` keys for forex/commodity by design (continuity); track_record's reconstructed rows (`first_seen_asof≈2026-06-29`, date match rate 0.0002) gate pit_live stamping (§6.2); bridge macro-level tickers ruled admissible with a no-new-names test extension (§5.4).

---

## §1. Program-level rulings (Fable)

- **RUL-M1 (rail, not lobe):** R5 is a rail: labels, memory, provenance, display. It owns no objective function, no FDR family of its own, no falsifiers about market behavior — only falsifiers about its own data integrity (staleness, hash mismatch, coverage). Anything that *tests a macro hypothesis* leaves this program and enters the standard prereg gauntlet (RUL-M6, §9).
- **RUL-M2 (authority position):** every R5 artifact sits at A0/A1 on the ladder. All new world_state lobes carry `display_only: true`; all new graph edges are display-only structurally; the bridge summarizer inherits the all-false authority block. No R5 output may name, touch, or condition any Article-2 surface (`alert_triage, board_ordering, top_setups, attention_queue, push_floor`). A test wall (§5.5) asserts this against built artifacts.
- **RUL-M3 (labels before claims):** R5 ingests *labels* (usd_trend=up, china_quad=Q3, curve=bull_flattener, bond cycle_phase=late). It never emits a *claim*. The Codex paper's six hypotheses are docketed (§9); none are activated here.
- **RUL-M4 (compact state, single source):** world_state lobes carry distilled top-N fields with `asof` + `source` + `stale`, never raw page payloads. Where an artifact duplicates a `regime/latest.json` subkey (transmission's `yield_curve` block), the lobe reads ONE declared source and says which. §5.3/§6.1 field lists are the build contract.
- **RUL-M5 (commit paths, RUL-P10 compliance):** every new write path declares one of (a) explicit `.gitignore` entry, (b) git-committed named single-writer, or (c) R2 artifact. All four R5 paths are (b): `data/macro_snapshots/{ledger.parquet, latest.json, transitions.jsonl}` (single writer `scripts/build_macro_snapshot.py`, nightly) and `data/macro_context/latest.json` (single writer `scripts/build_macro_context.py`). Note the blanket `git add data/` is NOT gated by the synapse registry — the declaration, not the registry row, is the safety property.
- **RUL-M6 (forking-paths law honored by deferral):** R5 builds the *query surface* for macro-conditioned questions but runs **zero** conditioning studies. The first Macro Conditioning Atlas run is docketed (§9) as a REGISTERED descriptive batch with a declared budget in a flat `fdr_family='macro_context'` and mandated basis-split reporting. The macro page's headwind matrix and deltas lobe are label censuses, not statistics over the outcome tape — they do not contaminate preregs (red-team lens 2 concurrence).
- **RUL-M7 (honest stamp basis):** historical stamps derived from the regime_history parquets are recomputed-from-revised-data, not point-in-time vintages. Every stamped row carries `regime_stamp_basis ∈ {pit_live, recomputed_history}` (governing both regime stamps and the `macro_context_id` stamp). `regime=`-filtered spine queries default to `stamp_basis='pit_live'`; recomputed rows are opt-in via `stamp_basis='any'|'recomputed_history'`. This extends the vintage discipline of `engine/vintage_stamp.py` (R3) to labels. Reconstructed ledgers gate pit_live via `first_seen_asof` (§6.2).
- **RUL-M8 (bridge payload budget):** `mastermind_context.json` has a CI-enforced 200 KB cap and ships ~165 KB. R5 adds ONE bridge lobe (`macro_weather`), budgeted ≤ 12 KB serialized. Macro-level asset/sector tickers (index/sector ETFs, futures roots: XLK, QQQ, SPY, GC=F, TLT, FXI, …) are admissible in it as macro-level records, not candidate names; the authority test extends the no-new-names invariant (§5.4).
- **RUL-M9 (render budget):** nightly additions: `build_macro_snapshot` (seconds; placed BEFORE `build_spine_index`), `build_macro_context` page (seconds), two `archive_signals` MANIFEST rows (seconds), the qledger stamp wrapper (seconds). Historical quad stamps are a deterministic build-time adapter helper inside `build_spine_index` (reads four history parquets — sub-second joins), NOT a manual script; there is no one-time state anywhere.
- **RUL-M10 (model lanes):** Sonnet builds every PR; Opus reviews PR-B (authority surface), PR-C (PIT surface), and the final diff; Fable plans, adjudicates, merges. No Fable subagents.

---

## §2. Wave plan

| Wave | PR | What | Model lane | Risk |
|---|---|---|---|---|
| W0 | PR-0 | This masterplan + Codex paper committed to research/ | Fable + Opus red-team | — |
| W1 | PR-A | Bus + deploy hygiene: 10 synapse registrations (existing producers only), `engine-render.yml` bridge step + dag.yml, healthcheck live-route probes, `_build_lobe_manifest` parquet stale-flag fix, ci.yml `neural-web-core` job wiring the 5 orphan NW test files (+ admin test into existing job) | Sonnet build, Opus spot-review | LOW |
| W1 | PR-B | world_state macro lobes (6 new + 1 enriched) + `_law.py` + date normalizer + bridge `macro_weather` summarizer + authority test wall + `_full_tree` fixture extension | Sonnet build, **Opus review** | MED — authority surface |
| W2 | PR-C | Macro snapshot registry (ledger/latest/transitions + `macro_context_id`, its 3 synapse entries, daily.yml step before build_spine_index + dag.yml) + spine: `adapt_macro_context`, `market`/`own_market_quad`/basis columns, stamp-join, qledger wrapper + market routing, `rate_pressure` fix-or-print, historical quad adapter helper | Sonnet build, **Opus review** | HIGH — PIT surface |
| W2 | PR-D | Confluence macro nodes/edges + committee.html.j2 render support + ask-brain macro routing + tests | Sonnet | LOW |
| W3 | PR-E | Macro Weather Station page (+ its synapse entry, render.yml + dag.yml) + transmission SEO-head fix + ISO `asof` in forex/commodity producers + archive_signals MANIFEST rows | Sonnet | LOW |
| W3 | PR-F | VPS propagation check (run `macro-update`, read log), live smoke of neuralwebdata routes post-deploy | ops (orchestrator) | LOW |

**Merge/gate law:** all PRs land on ONE branch (`feat/nw-macro-context`) as sequential stages; ONE squash-merge PR. Acceptance gates are **branch-final**: stage commits may be red in isolation (e.g. a synapse entry before its consumer); the final squashed state is the CI unit. SIGNAL_BUS.md is regenerated once, in the final state, with the artifact-count test updated 157 → 171 (10 in PR-A + 3 in PR-C + 1 in PR-E). Synapse registrations live in the PR that creates their producer (validator's producer-existence check).

---

## §3. Architecture: the R5 rail in one picture

```
producers (existing, unchanged):
  build_transmission → data/transmission/latest.json
  build_forex        → data/forex/latest.json          (+ new iso asof field, PR-E)
  build_bonds        → data/bonds/bond_health.json
  build_commodities  → data/commodity/latest.json      (+ new iso asof field, PR-E)
  china/hk/canada_run→ data/{china,hk,canada}_regime/latest.json
  engine.run         → data/regime/latest.json (incl. regime_vector, cross_asset_confirm)
  build_briefing     → site/intelligence/briefing.json
  build_factor_series→ site/factordata/factor_series.json

R5 rail (new; nightly order: producers → build_macro_snapshot → build_spine_index → … → build_world_state → bridge):
  scripts/build_macro_snapshot.py
    ├─ data/macro_snapshots/latest.json      — compact composite of ~22 frozen labels,
    │    keyed by macro_context_id = sha256[:16] of canonical label payload
    ├─ data/macro_snapshots/ledger.parquet   — one row per day per (domain, field); same-asof replace
    └─ data/macro_snapshots/transitions.jsonl — label flips vs prior ledger day; same-asof replace

consumers (extended):
  engine/neuralweb/world_state.py     ← 6 new compact lobes + enriched factor_weather
  engine/neuralweb/mastermind_context ← 1 new macro_weather summarizer (≤12KB)
  engine/neuralweb/query.py           ← adapt_macro_context rows (scope_type='macro'),
                                        macro_context_id/asof, market, own_market_quad,
                                        regime_stamp_basis columns + pit_live-default filter
  engine/neuralweb/confluence.py      ← macro nodes + headwind/tailwind/diverge edges
  templates/committee.html.j2         ← render support for macro nodes/edges
  engine/neuralweb/ask_brain.py       ← fx/rates/commodity terms → world_state lobes
  site/macro_context.html             ← Macro Weather Station (bilingual, static)
```

Every arrow into Neural Web is a *read*; every new artifact is display/context tier. The kernel becomes the eventual beneficiary — once spine rows carry macro stamps, kernel cells can extend `regime_bucket` vocabulary in the kernel's own program after the 2026-10-01 FDR batch. R5 does not touch the kernel.

---

## §4. PR-A spec — bus + deploy hygiene

### 4.1 Synapse registrations (10 entries — existing producers only)

Field template for every entry (sample `regime-latest`, synapse.yml:44-73, as the shape reference): `path`, `format` (json), `producer`, `owner_program: macro-context-rail`, `cadence`, `storage: git`, `asof_field`, `freshness_sla_hours` (30 for daily-engine; 40 for asia-close), `schema: implicit`, `tier: display`, `horizon_role: context`, `weights: none`, `scored_path_surfaces: []`, `consumers: [engine/neuralweb/world_state.py]` (plus `scripts/build_macro_snapshot.py` once PR-C lands — added in PR-C), `external_consumers: []`, `notes` naming the producer file:line.

| artifact_id | path | producer | cadence | asof_field |
|---|---|---|---|---|
| `forex-latest` | data/forex/latest.json | scripts/build_forex.py | daily-engine | `date` (→ `asof` in PR-E, note anticipates) |
| `transmission-latest` | data/transmission/latest.json | scripts/build_transmission.py | daily-engine | `asof` |
| `bond-health` | data/bonds/bond_health.json | scripts/build_bonds.py | daily-engine | `as_of` |
| `commodity-latest` | data/commodity/latest.json | scripts/build_commodities.py | daily-engine | `date` (→ `asof` in PR-E) |
| `china-regime-latest` | data/china_regime/latest.json | engine/china_run.py | asia-close | `date` |
| `hk-regime-latest` | data/hk_regime/latest.json | engine/hk_run.py | asia-close | `date` |
| `canada-regime-latest` | data/canada_regime/latest.json | engine/canada_run.py | daily-engine | `date` |
| `site-intelligence-briefing` | site/intelligence/briefing.json | scripts/build_briefing.py | daily-engine | `as_of` |
| `site-factor-series` | site/factordata/factor_series.json | scripts/build_factor_series.py | daily-engine | `as_of` |
| `site-alerts-triage` | site/factordata/alerts_triage.json | scripts/build_site.py | daily-engine | `asof` |

`canada-regime-latest` carries `known_extra_writers: [scripts/build_vector.py]` + notes (build_canada invoked from build_vector — census).

### 4.2 SIGNAL_BUS + count test

Regenerated once at branch-final state (`python -m scripts.gen_signal_bus_doc`); `tests/test_signal_bus_doc.py` count 157 → 171 with changelog comment.

### 4.3 Deploy fixes

1. `.github/workflows/engine-render.yml` — add the `build_nw_mastermind_context` step after `build_world_state` (line ~146), same `if: always()` non-fatal shape as daily.yml:958-965. **Update `config/dag.yml` lanes block in the same commit; run `python3 scripts/check_dag_conformance.py --verbose` locally.** (The builder already writes the site copy itself — no build_site.py change needed; the draft's copy step was redundant and is dropped.)
2. `scripts/healthcheck.py` — add a `live_routes` probe (`mastermind_context.json`, `bottom_sensors.json`, `confluence_graph.json`, `kernel_families.json` under `https://mastermind-x.com/neuralwebdata/`), 404 → warning output; callable standalone for W3 PR-F.
3. `engine/neuralweb/mastermind_context.py:_build_lobe_manifest` — parquet stale-flag fix: skip `json.loads` for `.parquet` paths (asof=None, stale=None, noted) so `options-entry-state` stops reporting perma-stale.

### 4.4 CI wiring

New ci.yml job `neural-web-core` (path-gated on `engine/neuralweb/**` + the test files): `tests/test_mastermind_context.py tests/test_confluence.py tests/test_spine_query.py tests/test_ask_brain.py tests/test_world_state.py -q` (all 163 tests verified green on origin/main today — red-team lens 1). Add `tests/test_admin_neural_web.py` to the existing `neural-web` job. Deps: `pytest pandas numpy pyarrow pyyaml jinja2`.

Acceptance (branch-final): validator clean; SIGNAL_BUS byte-fresh; count test green; dag-conformance green; new ci jobs green; parquet manifest row no longer stale-true.

---

## §5. PR-B spec — world_state lobes + bridge summarizer + law helper

### 5.1 `engine/neuralweb/_law.py` (new, ~40 lines)

`display_only(d: dict) -> dict` — sets `d["display_only"] = True`, returns d. `assert_no_authority(payload: dict) -> list[str]` — walks a payload; violations = any of the five authority booleans true, any non-empty `scored_path_surfaces`. Used by the new composers and the §5.5 test wall; existing call sites migrate opportunistically.

### 5.2 `engine/neuralweb/_dates.py`

`to_iso(s) -> str|None`: ISO passthrough, `"Jul 05, 2026"` display strings, None-safe. Unit-tested on the four observed formats (ISO date, display string, ISO datetime, None).

### 5.3 world_state composers

Pattern (per red-team correction): follow **`_compose_factor_weather` / `_compose_options_weather`** — composer owns its internal try/except, returns a null-shaped dict + registers a gap on failure, sets `display_only=True` always (via `_law.display_only`). The assembly block (world_state.py:723-763 region) wires each lobe and registers `sources[path] = asof`. `_compose_regime()` is a pure transform and is NOT the fail-open exemplar.

New lobes (blackboard keys):

1. **`rates_transmission`** ← `data/transmission/latest.json`: `asof, scored_status, calibrated, state, headwinds[*].{asset,verdict,net}, tailwinds[*].{asset,verdict,net}, yield_curve.{regime.key, regime.label, recession.risk, recession.ntfs, shape.slope_2s10s}` + `yield_curve_source: "transmission"` note + law fields.
2. **`fx_dollar`** ← `data/forex/latest.json`: `asof (to_iso), regime, risk, favored, dollar_desk.{lean, real_rate_regime, usd_valuation, trend, fed_path_lean, liquidity_dir}, transmission.{usd_dir, headwind_for, tailwind_for, unstable}, regime_radar.{dominant, active}` + law fields.
3. **`rates_credit`** ← `data/bonds/bond_health.json`: `as_of, health_score, health_label, cycle_phase, recession_risk, drawdown_risk, alarms, verdict_en, fed_path.{policy_rate, implied_bp_12m, implied_cuts_12m}, bond_compass.{duration, curve_trade}, bond_cross_asset.verdict_en, drivers_for` + law fields.
4. **`global_regimes`** ← three regional latest.json + already-composed regime lobe: per-market `{market, date, quad, quad_name, cycle_tag, liquidity_overlay, pending_quad, confidence, stale}` for us/china/hk (+`risk_state, peg_state`)/canada + `dispersion_note` (count of distinct quads — a census of labels) + law fields.
5. **`commodity_context`** ← `data/commodity/latest.json` (0.9 KB): `asof (to_iso), regime, favored, assets[*].{label, trend, action, conviction}` + law fields.
6. **`intelligence`** ← `site/intelligence/briefing.json`: `as_of, n_universe, n_priority, n_actionable, n_divergences, macro_context.{regime, posture, fed_stance}, top_actionable: priority_queue[:5].{ticker, priority, lean, read}` + law fields.
7. **`macro_deltas`** ← `data/macro_snapshots/transitions.jsonl` (last 14 days): `[{asof, domain, field, from, to}]` capped 20 + `n_transitions_14d` + law fields. Missing file = gap (build-order independence).
8. **`factor_weather` (enriched in place)** ← add `rotation: {leader, leader_label, leader_ret20_pct, leader_held_days, recent_flips[:3]}` and `horizon_flags` from `site/factordata/factor_series.json`; every existing key byte-compatible.

### 5.4 Bridge summarizer

`_summarize_macro_weather(repo) -> (dict, gap|None)`: registered as `macro_weather` in `LOBE_SUMMARIZERS`; `_LOBE_TO_ARTIFACT_IDS["macro_weather"] = ["macro-snapshots-latest"]`. Reads world_state.json + `data/macro_snapshots/latest.json`; **returns a gap when the snapshot file is absent** (so `has_rich_summary` is never patched onto a stale/absent manifest row — red-team lens 1 finding 6). Distills: `{asof, macro_context_id, us/china/hk/canada quads, fx: {regime, usd_trend, headwind_for[:5], tailwind_for[:5]}, rates: {yield_curve_regime, recession_risk, transmission_headwinds[:5], transmission_tailwinds[:3]}, credit: {health_label, cycle_phase}, commodity: {regime, favored}, deltas_14d[:10], contradiction_note, display_only: true}` ≤ 12 KB. Macro-level tickers (sector ETFs/futures roots) are admissible per RUL-M8.

### 5.5 Authority test wall

`tests/test_macro_context_authority.py` (hermetic, `_build_minimal_tree` pattern): every new lobe `display_only is True`; `assert_no_authority` = [] on both built artifacts; five bridge booleans false; no lobe contains Article-2 surface keys; world_state builds with EVERY new source individually missing (per-lobe gap, others unaffected); `to_iso` format coverage; **no-new-names extension**: no single-name symbol outside the bottom-sensors/candidate intake union appears in `macro_weather` (macro ETFs/futures whitelisted). **PR-B also extends `tests/test_world_state.py::_full_tree`** to write the six new source files so `non_contra_gaps == []` (line 312) stays green; acceptance is "green after fixture extension," not "untouched."

Acceptance (branch-final): existing world_state keys byte-compatible; new lobes present on real data; bridge < 200 KB with macro_weather; authority wall green; Opus review sign-off.

---

## §6. PR-C spec — macro snapshot registry + spine stamps (PIT surface — Opus review mandatory)

### 6.1 `scripts/build_macro_snapshot.py` (new, single-writer)

Reads (fail-open per source): regime/latest.json (quad, quad_name, transition_state, regime_vector block, cross_asset_confirm.to_brain, vol_regime.regime, risk_radar.state), market_state/latest.json (verdict), forex, transmission, bond_health, commodity, china/hk/canada regime latest files, dispersion regime.json.

**v1 label vocabulary (frozen; extending bumps schema minor):** us_quad, us_transition_state, us_fused_risk, us_vol_regime, us_risk_radar, us_rate_pressure, market_state_verdict, yield_curve_regime, recession_risk (transmission's categorical `yield_curve.recession.risk` VERBATIM — no re-banding, no thresholds, source named in the module docstring), usd_trend, usd_regime, fx_risk, real_rate_regime, fx_liquidity_dir, bond_health_label, bond_cycle_phase, commodity_regime, commodity_favored, china_quad, hk_quad, hk_risk_state, canada_quad, dispersion_state, cross_asset_verdict. All values are strings/enums taken verbatim from sources; NO derived numerics, NO banding.

Emits:
1. `latest.json`: `{schema: "macro_snapshot.v1", asof, oldest_component_asof, macro_context_id, labels: {domain: {field: value}}, sources: {path: asof}, gaps: [...], display_only: true}`. **`asof` = MAX over present source asofs** (the PIT join key — no spine row dated before the newest component can bind to this snapshot); `oldest_component_asof` = MIN (staleness diagnostic only). `macro_context_id = sha256(canonical_json(labels, sort_keys, ensure_ascii))[:16]`.
2. `ledger.parquet`: one row per (asof, domain, field, value, source_asof, macro_context_id); **same-asof replace** on re-run (idempotent).
3. `transitions.jsonl`: field flips vs the prior ledger asof; **same-asof replace on re-run** — before appending, existing rows with today's asof are dropped and re-derived, so a nightly retry is a no-op (red-team blocking fix). First run emits nothing (printed as a note).

daily.yml registration: resilient non-fatal step **immediately BEFORE `build spine index` (daily.yml:697 region)** so the spine adapter and stamp-join see today's ledger, and world_state's deltas lobe (line ~946) sees today's transitions. **dag.yml updated in the same commit; conformance checker run locally.** The three synapse entries (`macro-snapshots-latest` w/ `external_consumers: [mastermind:context]`, `macro-snapshots-ledger` format parquet tier infrastructure, `macro-transitions` format jsonl) ship in THIS PR (producer-existence law).

### 6.2 Spine columns + adapter + stamp-join

`engine/neuralweb/query.py`:
- COLUMNS += `macro_context_id`, `macro_context_asof`, `market` (str|None: US/CN/HK/CA), `own_market_quad` (str|None), `regime_stamp_basis` (str|None); `_ensure_columns` injects None defaults (read-time compatibility with the existing parquet). **`quad_hard_label` remains US-primary on all lanes per the query.py:159 invariant — own-market quads NEVER enter it.**
- `adapt_macro_context(root)` (adapt_options_entry pattern): one row per (asof, domain) from ledger.parquet: `signal_id="macro_context:{asof}:{domain}"`, `ledger="macro_context"` (added to LEDGER_ENUM at query.py:190), `engine="macro_context"`, `family=domain`, `symbol=domain`, `scope_type="macro"` (pre-declared vocabulary at query.py:139, populated for the first time), `direction=0`, `outcome_graded=False`, `is_context=True`, `horizon=0`, `regime_stamp_basis='pit_live'`, us_* stamps from that day's labels.
- **Stamp-join** in `build_index()` after union: rows with null `macro_context_id` and as_of ≥ ledger start get a backward carry-forward join against the ledger's daily (asof → macro_context_id). **Dtype law (red-team reproduced MergeError): convert both keys with `pd.to_datetime`, sort both frames by key, `merge_asof(direction='backward')`, restore string as_of after.** Basis rule: the joined stamp is `pit_live` only when the row is a live observation — where the source ledger carries a reconstruction timestamp (`track_record.first_seen_asof`), pit_live requires `first_seen_asof ≤ snapshot.asof`; otherwise the stamp is written with `regime_stamp_basis='recomputed_history'`. Rows before the ledger's first day stay None (count printed in build gaps).
- `query()`: `macro_context_id=` and `scope_type=` filters; **`regime=` filtering applies `stamp_basis='pit_live'` by default** — `stamp_basis='any'` or `'recomputed_history'` opt in (default protects the future Atlas from pooling fabricated labels; existing pit_live-stamped rows behave identically).

### 6.3 qledger + rate_pressure + historical quads

1. **qledger nightly backfill:** new `scripts/backfill_regime_stamps.py` (thin wrapper calling `engine.qledger.backfill_regime_stamps()` — the module has NO CLI; the draft's `python -m engine.qledger` form is dead). Resilient daily.yml step after the regime_vector append + dag.yml row. Near-term yield ≈ claims with asof ≥ 2026-07-01 only (regime_vector coverage); printed honestly in the step log. Market guard: stamps only rows whose market is US (see routing below) — China A-share claims are not stamped with US-only vector labels beyond the documented US-primary backdrop convention (which `quad_hard_label` already encodes); `own_market_quad` for non-US claims comes from the historical helper.
2. **Market routing:** `market` column derived per (ledger, symbol): board_hk → HK, board_ca → CA, board_cn → CN, track_record/spine/options_entry → US (track_record verified all-US by census), qledger → by symbol suffix (`.SS`/`.SZ` → CN, `.HK` → HK, else US), macro_context → None.
3. **Historical quad helper** `_stamp_historical_quads(df)` (deterministic, build-time, inside build_index): fills `quad_hard_label` where null from the **US** history parquet (backward merge_asof on as_of, dtype law above, `reset_index()` on the DatetimeIndex parquets first) for ALL rows with `regime_stamp_basis='recomputed_history'`; fills `own_market_quad` from the matching national history parquet for rows with market ∈ {CN, HK, CA} (same basis flag). Rows outside a parquet's range stay null.
4. **rate_pressure defect:** builder investigates `engine/regime_vector.py` STAMP_COLUMNS population (None in both rows). Wiring bug ≤ ~20 lines → fix + test; otherwise print as a known upstream gap in the PR body + §11.

### 6.4 Tests

Hermetic per house pattern: snapshot — label freeze (unknown label rejected), hash stability across key order, same-day re-run idempotency for BOTH ledger and transitions (re-run appends zero new transition rows), first-run-no-transitions, transition detection, missing-source gap honesty, **max-asof join-key law (a snapshot embedding a newer component never binds to an older row)**; adapter — column mapping, scope_type='macro', LEDGER_ENUM membership; stamp-join — dtype conversion, carry-forward correctness, pre-ledger rows None, **anti-leak: row as_of < snapshot asof never matches**, first_seen_asof gating; market routing — suffix inference incl. qledger A-shares; historical helper — US-only quad_hard_label, own_market_quad per market, basis flags, out-of-range null; query — pit_live default on regime=, opt-in bases.

Acceptance (branch-final): spine builds with new columns + macro rows on real data; anti-leak tests green; gap counts printed; Opus review confirms: no forward-dated join, transitions idempotent, single-writer, RUL-M7 basis discipline, quad_hard_label US-primary preserved.

---

## §7. PR-D spec — confluence edges + ask-brain routing

### 7.1 Confluence + committee page

`engine/neuralweb/confluence.py`: new node type `macro` (subtype per domain incl. global_regime:{us,china,hk,canada}, dispersion). New display-only edges via existing `_edge()`: `headwind`/`tailwind` (macro:rates_transmission → sector:<ETF>; macro:fx_dollar → asset groups), `contradicts` (macro:fx_dollar/rates_credit → regime:<current> when cross_asset_confirm.to_brain.verdict == 'diverge'), global-regime edges only to complexes already in the graph. Edge metadata: existing fields + note naming source lobe + asof.

**`templates/committee.html.j2` (red-team finding — nodes would be invisible without this):** add `macro: true` to `SHOW_TYPES` (line 639); extend the edge-node inclusion condition (line 644, currently confirms/contradicts only) and the edge-draw styling (line 753-755) to cover `headwind`/`tailwind`.

### 7.2 Ask-brain

`_classify_question`: new branch BEFORE the generic regime branch, scoped to terms the regime branch does NOT already catch (it already matches bare `macro|regime|quad`): pattern `\b(dollar|usd|fx|forex|yield curve|real rates?|bonds?|credit|treasur\w+|commodit\w+|gold|copper|oil|transmission|headwind|tailwind)\b` → budget 3, seeds `["read_world_state"]` (the macro lobes live inside world_state; `read_artifact` seeding dropped as redundant). Bare "macro"/"quad" questions keep their existing routing (no behavior change to covered inputs). Tests: new-term routing, fixture world_state with macro lobes answered with citations, advice patterns still refuse, existing classifier tests untouched.

Acceptance (branch-final): graph builds with macro nodes/edges on real data; macro nodes RENDER on committee.html (SHOW_TYPES + styling verified in the built page); ask-brain tests green.

---

## §8. PR-E spec — Macro Weather Station page + producer hygiene

### 8.1 Page

`scripts/build_macro_context.py` + `templates/macro_context.html.j2` (base: `bonds.html.j2` — _seo_head/_plotly_head/_vector_polish/_navlinks includes, local `t()` macro, all CSS inline, `data-tip-en/zh` never `title=`). Server-rendered from world_state + snapshot ledger + transitions (zero runtime fetch): current label board grouped by domain with EN/ZH chips (engine/i18n LEX via `td()`) + stale badges; headwind/tailwind matrix; last-30 transition timeline; contradiction census strip; Neural Web footnote (`macro_context_id`, display-only disclaimer, committee.html link). Hub contract `data/macro_context/latest.json` `{asof, macro_context_id, n_transitions_14d, headline_en/zh}` + its synapse entry (this PR — producer law). Nav: Research mega-menu, Cycles & Cross-Asset column, `{{ t('Macro Weather','宏观气象台') }}`. render.yml: `brun macro_context …` in the parallel block + path triggers + **dag.yml update + local conformance run**. daily.yml: resilient step after `build_macro_snapshot`. Local CI guards before commit: check_title_i18n, check_nav_gap, check_nav_mega, check_inline_js, check_site_js.

### 8.2 Producer hygiene (minimal, non-breaking)

1. `build_forex.py` + `build_commodities.py`: ADD ISO `"asof"` to latest.json (keep `date` display strings); synapse `asof_field` flipped to `asof` in the same commit. (Census: no consumer does strict key iteration; additive is safe.)
2. `templates/transmission.html.j2`: add the missing `_seo_head.html.j2` include (bonds.html.j2 pattern).
3. `scripts/archive_signals.py` MANIFEST += `("transmission", "transmission/latest.json", "asof")`, `("market_state", "market_state/latest.json", "asof")`. Forex/commodity MANIFEST rows keep their `date` keys **by design** (archive continuity — flipping the key would change the archived value format mid-series).

Acceptance (branch-final): page renders locally with real data, bilingual toggle works, five CI guards pass, forex/commodity latest.json carry both date + asof, archive rows verified by a local archive_signals run.

---

## §9. Docket entries (recorded, NOT built by this program)

1. **Macro Conditioning Atlas (descriptive batch, registered):** first "signal family × macro label" descriptive tables over the stamped spine. Requires: flat `fdr_family='macro_context'` registration with declared budget = cells examined, episode-clustered dispersion, nulls printed, **mandatory basis-split reporting (pit_live vs recomputed_history, never pooled in a headline number)**, and `derived_from_surface` contamination stamps on any later promotion prereg. Unblock: PR-C shipped + ≥60 days of pit_live snapshot accrual.
2. **regime_vector historical backfill:** re-run vol/fused/risk_radar/rate_pressure computation over history (PIT hazards: VIX/VRP/liquidity inputs must be vintage-checked; charter with R3 discipline). Unblocks pre-Jul-1 qledger stamps and rich-label conditioning.
3. **Kernel macro buckets:** kernel program's decision, post 2026-10-01 FDR batch, consuming R5 stamps.
4. **Codex paper hypotheses 1–6:** each needs universe/horizon/direction/falsifier/n-floor/OOS split per NW_RAILS §3.3 before any run.
5. **L6 fence:** nothing in R5 is per-name macro fingerprinting; L6 stays gated on its own Phase-0. R5's stamps may make that Phase-0 cheaper; that is the only relationship.

## §10. What this program does NOT do (scope fences)

- No new scores, composites, meters, or bands — the v1 vocabulary is verbatim source labels only; the one draft band (recession_risk) was killed by the red-team and replaced with the source categorical.
- No behavior change to any Article-2 surface; no consumer added to any scoring seam in DISPLAY_VS_SCORING_MANIFEST.
- No kernel changes; no new FDR families opened (`macro_context` reserved in §9, opened only by the Atlas registration).
- No Mastermind arming/authority change; bridge stays dark per its §1.7.
- No macro hypothesis testing, no conditioning tables, no "which signals work when" claims.
- No new LLM surfaces; ask-brain changes are routing-only within the read-tool whitelist.
- No touching `engine/conditions.py` / `playbook.py` MRS scoring seams; no reversal of the `quad_hard_label` US-primary invariant.

## §11. Status log

- 2026-07-06: Codex paper received; 8-lane census complete; draft written; 3-lens Opus red-team returned APPROVE_WITH_EDITS ×3 (7 BLOCKING, 11 EDIT, 10 NOTE — all adjudicated and folded into §0.5); program ratified; build waves dispatched (Sonnet builders, Opus reviewers, single branch `feat/nw-macro-context`).

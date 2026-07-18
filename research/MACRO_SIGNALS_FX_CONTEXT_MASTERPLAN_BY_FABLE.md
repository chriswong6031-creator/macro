# Macro Signals × FX Context Bus — masterplan (MSX)

Status: RATIFIED design, 2026-07-18 (Fable main-loop adjudication).
Scope: (1) make the forex intelligence layer a first-class machine-readable context
bus consumed across the Neural Web and sibling engines; (2) expand + fully revamp
`macro_signals.html` per `docs/DESIGN_DOCTRINE.md`.
Ships as two same-day source-only PRs: **MSX-1** (FX context bus) → **MSX-2**
(macro_signals revamp). Come-back = first nightly after merge populates the new
latest.json keys; page fx section fail-opens until then.

## 0. Findings that drove the design (8-lane census, 2026-07-18)

- `macro_signals.html` renders from the SAME vm as macro.html (`build_site.py:4327`)
  but uses ~15% of it; zero FX content; Plotly-only page left after #2823; Tier-3
  raw-data idiom (z-tables, "LORO 1985+", no stances) — every DESIGN_DOCTRINE law
  violated on a nav-linked surface.
- The forex engine family is deep (dollar desk 7 legs + smile decomp, 6-scenario
  stress radar WITH Wilson-CI conditional base rates, strength meter, kinematics,
  CNH basis, per-pair narratives, bilingual state-change alert stream) but most of
  it DEAD-ENDS at forex.html. `data/forex/latest.json` forwards only word-level
  summaries.
- **LIVE BUG:** `scripts/build_forex.py _desk_latest()` omits `smile_decomp`, but
  `scripts/build_intl.py:281` and `engine/flow_regime.py:1536` read
  `dollar_desk.smile_decomp` → both consumers silently null since IRD-R10 shipped.
- NW wiring exists but is shallow: `world_state._compose_fx_dollar` (R5 lobe),
  `confluence.py` `macro:fx_dollar` node + contradicts edges, `mastermind_context`
  FX block, `master_brain` state['forex'] with coincident `_tape_note`.
- FX already feeds ONE authority path: `cross_asset_confirm` fx-caution vote →
  `risk_state` cross_asset leg (weight 0.3). **MSX does not touch it** (no new
  authority without gauntlet; double-count hazard).
- Ratified consumption patterns to reuse: W3-C4b sector chip (`build_site.py:2858`),
  CGL post-transform radar attach (`build_china.py:902`), hk_context_chips fail-open
  chip schema, group_context passport, master_brain `_tape_family` annotation.

## 1. Epistemics ruling (MSX-R1)

The operator's ask — "display-only isn't right, it should be used in calculations" —
is granted **at the context/confluence tier**, which house law already permits
freely: engines may READ fx context keys as supporting evidence, display attaches,
and confluence inputs. It is **not** granted at the authority tier: nothing in MSX
adds an FX term to any rank/size/gate/score. The bridge to authority is built
instead: lane-gated forward logs (§4) accrue PIT rows so a future prereg gauntlet
can promote specific keys with evidence. INTL-43 stands (no per-pair conviction
clears DSR); the honesty bars in `forex_dollar.py` stand. The macro_signals page
lead is rewritten from "nothing here feeds anything" (now false) to plain-word
truth: "these readings feed the system's context layer; none of them alone drives
a buy/sell call."

## 2. MSX-1 — the FX context bus (engine + NW + consumers)

### 2.1 `data/forex/latest.json` enrichment (additive-only; producer `build_forex.py`)

- `dollar_desk.smile_decomp` — **bug fix**: forward the full smile_decomp dict
  (regime, regime_60d, residual_20d_z, beta, r2, safety_bid_today, gaps,
  display_only). Unblocks build_intl + flow_regime.
- `strength` — strength_meter output {horizons:{1w,1m,3m:[{ccy,ccy_zh,strength,
  vs_usd_pct,em}]}, default, order} (today display-only dead-end).
- `regime_radar.scenarios` — per-scenario receipt list {key, name_en, name_zh,
  intensity, active, illustrative, prob:{status, p_cond, base_rate, wilson_lo,
  wilson_hi, n_raw, n_eff, N}} (today only intensity/active/dominant forwarded —
  consumers never see the empirical receipts).
- `pairs.<KEY>` gains: headline/head_zh, sub/sub_zh (narratives), shock_state,
  cycle_position; USDCNH additionally cnh_basis_bps, cnh_basis_state.
- `state_changes` — NEW block, the "changes of this data" contract. For each of
  {smile_regime, lean, risk, fed_path_lean, liquidity_dir, trend, triple_red,
  cnh_basis_state, regime_radar_dominant}:
  `{current, prev, changed_on, days_in_state}`. Series-derivable keys compute from
  the `_dollar` frame; scalar leans use a tiny state ledger
  `data/forex/state_history.jsonl` (append gated on
  `engine.ledger_lane.nightly_advance_enabled()`, keep-first by date; off-lane
  renders read-only → days_in_state degrades to null, never blocks).
- `schema_note`: additive-only warning string for future editors.

### 2.2 Neural Web deepening

- `world_state._compose_fx_dollar` forwards: smile_decomp.regime + safety_bid_today,
  triple_red, state_changes, regime_radar dominant + top-scenario receipt, strength
  extremes (top/bottom currency, 1m). Still `_display_only(...)`.
- `confluence.py` `macro:fx_dollar` node payload gains state_changes summary +
  stress-scenario dominant (label field only; no new edge semantics this wave).
- `mastermind_context` / `master_brain` FX blocks gain state_changes + dominant
  scenario + strength extremes, each with `_lead_lag: "coincident"` `_tape_note`
  (pattern 5) so the LLM brief can NARRATE but never escalate them.
- `config/synapse.yml` forex-latest entry: consumers list + notes updated (same
  artifact/path — no new organ minted; update-not-duplicate).

### 2.3 Sibling-engine consumers (all fail-open, display/context tier)

- **China/HK radars** (CGL pattern, post-`market_state_snapshot` attach):
  `rd["fx_context"] = {cnh_basis_bps, cnh_basis_state, usd_dir,
  wrecking_ball_intensity, as_of, stale}` in build_china + build_hk; surfaced as a
  Tier-2 row inside the existing radar dialog (plain words: "Offshore yuan
  pressure: none / building / heavy").
- **lib/forex_link.py** gains `dollar_lean()`, `state_changes()`, `stress_radar()`
  helpers so commodities/bonds/crossasset builders can read the bus without
  re-parsing latest.json.
- **forex_alerts** gains desk-level event types (additive): smile-regime flip,
  triple_red onset/clear, stress-scenario activation. Events flow into the existing
  alerts.jsonl → forex.html timeline; the SAME events become the "what changed"
  strip on macro_signals (MSX-2).
- Explicit NON-changes: `cross_asset_confirm` untouched (authority path);
  `risk_radar_intl` composite legs untouched; regime axes untouched.

### 2.4 §4 Shadow accrual (promotion bridge, not promotion)

`data/forex/context_forward_log.jsonl` — one row per nightly per key for
{triple_red, cnh_stress, carry_unwind, dollar_wrecking_ball, smile_regime}:
`{asof, key, state, intensity_pct, graded: null}` — gated on
`nightly_advance_enabled()`, keep-first by (asof,key). No grader in MSX (rows must
mature ≥21 sessions first); grading + prereg (`research/FX_CONTEXT_<KEY>_PREREG.md`,
HINCL2 format, registry_seed declaration BEFORE stats) is the come-back around
2026-08-15. Until then the log is inert accrual.

## 3. MSX-2 — macro_signals.html revamp

Positioning: **"the full signal board"** — every gauge behind macro.html, now with
state + plain-word stance per panel, technicals demoted to hover, plus the new FX
section. macro_context.html remains the label/weather narrative page (no overlap:
gauges vs labels); the two get cross-links (today they are mutually undiscoverable).

Structure (one hero + 5 sections, mx5 glass/aurora idiom, NO Plotly):

1. **Hero** — one glance strip: regime dials (growth/inflation as needle gauges),
  fear/greed dial, VIX state, market-state tint driving the aurora (`.au-yellow`/
  `.au-red`), ONE stance sentence.
2. **Growth & the cycle** — business cycle phase + recession signal in plain words
  (receipts → hover), nowcast/conditions tiles as `.sig` atoms.
3. **Money & liquidity** — net-liquidity + credit/breadth converted to inline SVG
  sparklines (bcspark-style; Plotly include dropped — last Plotly page retired,
  1.15MB gz saved), each with a stance line.
4. **Mood & positioning** — fear/greed dial + top drivers as bars (full leg table
  → collapsible detail), fear↔euphoria merged as secondary row, crowd-meter rows
  with plain verdicts, VIX SVG.
5. **Currencies & the dollar** (NEW) — dollar desk card (smile regime plain-worded
  + lean + confirmation count), strength meter mini-bars, stress-radar chips w/
  intensity (receipts → hover), CNH basis, triple-red flag, headwind/tailwind
  chips, "what changed" strip from forex_alerts events, link → forex.html.
  All fail-open pre-first-nightly.
6. **Commodities tape** — restyled, kept.

Laws applied: stance vocabulary on every panel; banned-vocab sweep (no "LORO",
"z-score", "diffusion", raw n= on Tier 1); numbers arrive with meaning; one as-of
per panel; bilingual dual-span; `--num` token defined locally (今 leaks); title
stays plain text (RCDATA); "validated" never used. macro_signals.json sidecar
gains the fx block + state_changes (it is the Brain-facing mirror of the bus).

Verification: MACRO_DUMP_VM + `render_macro_fast` harness against production-shaped
data; browser-verify EN/ZH × dark/light; both PRs same-day squash-merge.

## 4. Rulings log

- MSX-R1 (§1): context-tier consumption granted, authority-tier deferred to
  gauntlet; forward logs are the bridge. No cross_asset_confirm changes.
- MSX-R2: enrich the EXISTING forex-latest artifact/lobe; do NOT mint a parallel
  organ (duplicate-path CI hard-fail; update-not-duplicate law).
- MSX-R3: macro.html itself untouched in this program (no vm-bleed risk; FX alerts
  reach glance tier via the china radar dialog + macro_signals hero, not macro.html).
- MSX-R4: Plotly retired from macro_signals (last page); charts become inline SVG.
- MSX-R5: state_changes ledger + context forward log are nightly-lane-gated
  (family: `engine/ledger_lane.py`); off-lane renders never write.

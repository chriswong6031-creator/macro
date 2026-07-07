# Tech Internals — Codex "tech_archetype + shock_fit" Adjudication

**Date:** 2026-07-07 · **Adjudicator:** Fable (main loop) · **Verification:** 6 census lanes (Sonnet) + 1 adversarial red-team (Opus)
**Subject:** External Codex memo proposing a `tech_archetype` + `shock_fit` engine (exposure tags, 12-type shock classifier, `tech_internal_rotation_state.json`, Nasdaq Internals panel, shock→shelter map into Neural Web). Follows the operator's AAPL/NFLX/SPOT "Tech is not one XLK blob" thread.
**Governance:** intake adjudication under `research/DO_NOT_REBUILD.md` authority + `research/ORACLE_ROTATION_TM_CODEX_ADJUDICATION.md` precedent (#1750). "No Codex for Oracle" respected — this is Fable-adjudicated intake; any build is Sonnet/Haiku under Fable. ETM registry query returned no prior matching rows.

---

## 0. Headline verdict

The memo's *observation* is right and already half-owned by the house: the Oracle Tier-S backbone maps **both** `ai_compute` and `software` to the same XLK ticker (`engine/oracle/graph.py:142-150`) — at sector resolution, Tech genuinely is one blob. The memo's *mechanism* mostly collapses on inspection, from both ends at once (the red-team's framing, confirmed): **the parts backed by real data are duplicates, and the genuinely novel parts are the illegal ones** (hand-inferred narrative labels, LLM-classified shock types, a laundered directional shelter map).

What survives is a thin, honest, display-only slice: a **curated group-level tech-archetype taxonomy over the existing Nasdaq substrate**, a **deterministic descriptive roll-up artifact** (`nasdaq_internals.json`), a **small panel extension** on the existing Nasdaq tab, and a **context-tier synapse registration** so Neural Web can *see* Tech's internal economy without anyone claiming it predicts anything.

Also noted: the memo's own fact-check corrected the operator's premise — on 2026-07-06 AAPL (+1.3%) did not rally *against* the tape (NDX +1.1%); the honest read is relative rotation *within* a rising index. That is exactly the kind of within-index read the surviving build makes visible, and exactly why it ships descriptive.

## 1. Component verdicts

| # | Codex component | Verdict | Ruling |
|---|---|---|---|
| C1 | Per-ticker exposure tags (10 keys) | **BUILD-MODIFIED** — group-level only; per-ticker multi-label table **DEFERRED** | TI-R2 |
| C2 | 12-type shock-vector classifier | **REJECT-REDUNDANT** (deterministic half) + **FORBIDDEN** (narrative half) | TI-R1 |
| C3 | `tech_internal_rotation_state.json` | **BUILD-LITE** — descriptive roll-up over existing primitives, renamed `nasdaq_internals.json` | TI-R3 |
| C4 | Nasdaq Internals dashboard panel | **BUILD-SMALL** — extend the existing Nasdaq tab; "AAPL-defensive" naming **KILLED** | TI-R4 |
| C5 | Shock→shelter beneficiary/casualty map into NW | **KILLED** as specified; residue = context-tier synapse registration of the C3 artifact | TI-R5 |

## 2. Rulings

### TI-R1 — No parallel shock classifier. `market_drivers.snapshot()` is canonical.
`engine/market_drivers.py:57-171` already runs the deterministic cross-asset shock-attribution engine: 9 fingerprint drivers (`fed_repricing, real_rate_shock, usd_shock, credit_stress, liquidity_impulse, china_stimulus, oil_shock, ai_semis, crypto_liquidity`), a canonical daily `snapshot()` read (verdict/primary/direction/confidence/ranked scores, `market_drivers.py:439-452`), append-logged to `data/regime/market_drivers_log.parquet`. Building a second 12-class vocabulary next to it is the classic re-vocabulary duplicate. Crosswalk (printed once, here):

| Codex regime | Existing coverage |
|---|---|
| AI compute boom / AI capex unwind | `ai_semis` ± projection (partial: doesn't split datacenter-AI from generic semis — the C3 roll-up is where that split becomes visible, descriptively) |
| Real-rate shock | `real_rate_shock` + `regime_vector.rate_pressure` (live, more granular) |
| Credit/liquidity shock | `credit_stress` + `liquidity_impulse` (live, MORE granular than Codex's single bucket) |
| Oil/inflation shock | `oil_shock` + `regime_one` inflation flag (live) |
| China/Taiwan supply-chain | `china_stimulus` is demand-side only; supply-chain variant has no deterministic price basis today |
| Soft-landing risk-on | composite of `liquidity_impulse+` / rate `relief` / quad — exists unnamed; naming it adds nothing calibrated |
| Trade/tariff, regulatory/antitrust, cyber threat, edge-AI device upgrade, consumer squeeze | **No deterministic fingerprint.** Text/narrative only (`news_vector` themes, `whitehouse_brain` LLM gate — context-only) |

The five narrative-only types may **never** be classified into a calibrated key by an LLM (house epistemics law; `cortex.py` A7 ORIGINATE ban). If a deterministic fingerprint for any of them is ever wanted (e.g. consumer squeeze via an XLY/XLP leg), that is a `market_drivers` program change with its own review — not this program.

### TI-R2 — Archetype taxonomy: group-level, curated, display-only. No per-ticker multi-label table.
The house already runs curated taxonomies as first-class citizens (46 thematic baskets with per-ticker rationale strings; the Oracle `rotation_groups.json` hand-named backbone reconciled against the data-derived cluster map; the 8 Nasdaq amalgamations). A **static, PR-reviewed, versioned grouping config is a taxonomy, not an originated signal** — the red-team's R-SP15 extension to "no curated mapping anywhere" would retroactively outlaw the basket system. R-SP15/epistemics bite at *runtime LLM origination* and at *labels that carry claims*; neither applies to a reviewed config whose fields assert membership only.

Constraints that DO bind, and how the build satisfies them:
- **No synonym keys (R-SP2).** `rate_duration`, `buyback_quality`, `index_liquidity` already exist as computed axes (`stock_fundamentals.rate_sensitive`, `capital_allocation` buyback fields, `stock_personality.passive_index_magnet`). The taxonomy does NOT re-key them; where relevant it references the existing keys.
- **Group level, not per-ticker.** Curation is epistemically weakest per-ticker (multi-label judgment calls per name; `china_supply_chain` outright unbuildable without revenue-geography data we don't ingest). The taxonomy defines **archetype groups as curated member sets over the existing Nasdaq-100 substrate** (`data/baskets_nasdaq/membership.json` — additive third partition `archetype_groups`, tolerant-reader safe): `ai_compute_supply` (semis/memory/semicap/networking-for-DC), `ai_capex_spenders` (hyperscalers), `edge_device` (AAPL/QCOM-style device+on-device-AI), `software_enterprise`, `cyber`, `digital_services_media` (ad/subscription platforms), `megacap_quality` (the existing megacap-anchors cut). Each group carries a one-line rationale, like every basket.
- **Per-ticker multi-label exposure table: DEFERRED** (registered in DO_NOT_REBUILD §4). Revive only with a fundamentals-derived deterministic basis (e.g. revenue-geography ingestion) and its own adjudication.

### TI-R3 — `nasdaq_internals.json`: deterministic, descriptive, neutral-named. Turn Desk non-duplication guard.
One new thin engine (`engine/nasdaq_internals.py`) composing EXISTING primitives (member prices / rs-vs-QQQ already computed for the Nasdaq confluence desk) into per-archetype-group rotation vectors: {rs_20d/rs_60d vs QQQ, accel, breadth-above-50dma, member dispersion, n}. Plus: **equal-weight-composite vs QQQ spread** (computed from member prices — no new collector required; QQEW ticker decision deferred, §4) and **group-vs-group divergence rows** (e.g. `ai_compute_supply` accel vs `edge_device` accel) printed as *descriptive gaps with z-scores*, never as forecasts.

Hard constraints, by construction:
- **Forecast-language ban** (Oracle constitution §III): no field named `shelter`, `rising`, `beneficiary`, `front_run`, or any banned-implication key. States are descriptive (`leading/improving/weakening/lagging`, gap z-scores).
- **Turn Desk non-duplication** (#1750 killed `schedule.v1` for exactly this): the artifact carries **no onset, episode, routing, or lead-lag fields**. Those belong to Oracle. This is a within-Nasdaq stock-group state read on a different substrate (Nasdaq-100 members vs Tier-S sector ETFs).
- **No Oracle map fork.** The Oracle `rotation_groups.json` backbone is untouched; the adjudication doc records the crosswalk (`ai_compute_supply` ≈ Oracle `ai_compute` at stock resolution). Extending Oracle's backbone with edge/cyber/media complexes is a **separate Oracle-governed reviewed change** — flagged as a come-back, not smuggled.
- **Membership-vintage watermark** inline in the artifact and on the panel (current Nasdaq-100 membership; historical composition approximated — Tier-M discipline).
- **Null-honest**: missing inputs → explicit nulls, prior payload kept, never raise.
- **2-day hysteresis** on any categorical group state (repaint discipline).

### TI-R4 — Panel: extend the existing Nasdaq tab. "AAPL-defensive" naming killed.
`subsectors.html` already ships a live Nasdaq-100 tab (12 sub-industries + 8 amalgamations, QQQ-benchmarked, nightly-scored). C4 lands there: an archetype-group strip reading the C3 artifact, an EW-vs-QQQ breadth chip, and a compact group-RS comparison. Bilingual; no translated text in `title=` attributes; the word "validated" nowhere. The group holding AAPL is **`megacap_quality`** — any "defensive" label or claim inherits the full `DEFENSIVE_ROTATION.md` falsification burden (its V4/V6 variants already FAILED OOS) and is not asserted.

### TI-R5 — Shock→shelter map: KILLED. Residue: context-tier visibility.
"Classify the active shock and map it to archetype beneficiaries/casualties" is a **laundered directional call** — the moment it reaches any board ordering or brain prompt as beneficiary/casualty, it is an escalation built on claims the house has already measured as dead: rotation continuation NULL both directions (Oracle constitution §IV), front-running rotation = coin-flip everywhere tested, defensive-rotation lead FAILED OOS. KILLED as specified; row appended to DO_NOT_REBUILD §1.

The legal residue ships: the C3 artifact registers in `config/synapse.yml` as `tier: display`, `horizon_role: context`, `external_consumers: [mastermind:context]` (auto-manifest, zero-code path). Neural Web and `master_brain` thereby *see* the tech-internal state exactly the way they see `rotation_directive.json` — context that may temper, never direct. No beneficiary field exists to launder.

### TI-R6 — Any conditional claim goes through the funnel.
"Archetype-group × `market_drivers` regime conditional performance" is a legitimate future *question*. It enters as a pre-registered phase-0 through the research-factory funnel with HLZ trial accounting and dumb-baseline controls (minimum: "today's state = yesterday's state" and "group state = sign(QQQ)"), on the forward ledger the C3 artifact starts accruing at merge. Until a registered pass: descriptive, display-only, nulls printed. Era law applies (no era-pooled inference across 2010; this substrate is effectively 2021+ anyway).

### TI-R7 — Search-width note.
The Codex memo tested nothing (it is a design memo, not a backtest); no trial-ledger entries accrue. The 12-regime list is recorded here as vocabulary only. Any future study on archetype groups must register its own width.

## 3. What was already ours (for the record, per the anti-duplication authority)
- Shock attribution: `market_drivers` 9 fingerprints + canonical `snapshot()` (§TI-R1 crosswalk).
- Tech-internal group taxonomy at basket-node level: Oracle `rotation_groups.json` `ai_compute` (12 nodes) + `software` (18 nodes); 268-subsector RRG (`subsector_rotation.py`) with `aiedge`, `iotedgedevices`, `cybersecurity*`, `socialadvertising`, `aiadssearch`, `semismemory`… nodes live.
- Nasdaq internals surface: `subsectors.html` Nasdaq tab + 8 amalgamations + Index-Leadership Nasdaq row on `sector_central.html`.
- Rate/buyback/index-weight axes: `stock_fundamentals.rate_sensitive`, `capital_allocation` buyback metrics, `stock_personality.passive_index_magnet`, `dna_class rate_duration_sensitive / china_crypto_proxy`.
- NW rotation context: `rotation_directive.json` → `master_brain.py:990-1012`; factor_weather world_state lobe pattern.

## 4. Build docket (authorized) + come-backs

**PR-A (this PR):** adjudication doc + DO_NOT_REBUILD rows.
**PR-B:** `archetype_groups` partition in `data/baskets_nasdaq/membership.json` + `engine/nasdaq_internals.py` + nightly step (additive, end-of-lane, trivial compute) + `site/marketdata/nasdaq_internals.json` + synapse registration (218→219 pin, SIGNAL_BUS regen, dag.yml) + tests (schema, null-honesty, banned-words, hysteresis).
**PR-C:** Nasdaq tab panel extension (archetype strip, EW-vs-QQQ chip, group comparison), bilingual.

Come-backs:
- **2026-09-15** — ~60 obs of `nasdaq_internals.json` accrued: decide whether to pre-register the archetype×regime phase-0 (TI-R6) via the factory funnel.
- **2026-08-01** — QQEW collector decision (tradable EW series vs computed composite; one-line add if wanted).
- **Unscheduled (Oracle-governed)** — whether Oracle's `rotation_groups.json` backbone gains edge/cyber/media complexes; requires an Oracle reviewed-change, not this program.

## 5. Sources
Census + red-team transcripts: workflow `wf_df2de5a4-d9a` (6 Sonnet lanes + 1 Opus red-team, 2026-07-07). Precedents: `ORACLE_ROTATION_TM_CODEX_ADJUDICATION.md` (#1750), `ORACLE_CONSTITUTION.md`, `SECTOR_ROTATION_ALERTS_PROBLEM_AUDIT_FOR_FABLE.md`, `DEFENSIVE_ROTATION.md`, `STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md` (R-SP2/R-SP15), `DO_NOT_REBUILD.md`.

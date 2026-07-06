# Neural Web → Mastermind Bridge — Fable Ruling & Build Program

Date: 2026-07-05 (Rev 2, post red-team)
Adjudicator: Fable (main loop)
Basis: Codex study `research/NEURAL_WEB_MASTERMIND_LINKING_STUDY.md` (2026-07-05) + 4-lane recon census of both repos (Macro worktree @ origin/main; Mastermind @ master 477af10) + 2-lens Opus red-team (both APPROVE_WITH_FIXES, no fatal objections; fixes folded in below).
Status: RATIFIED. Wave 1 (Macro) + Wave 2 (Mastermind) authorized as context-only, dark-shipped.

## 1. Executive ruling

APPROVE the two-layer bridge, context-only at birth, with these corrections to the Codex study:

1. **Artifact home is `site/neuralwebdata/mastermind_context.json`** (public NW data product, git-committed nightly), canonical copy at `data/neuralweb/mastermind_context.json`, plus a machine-plane copy in `site/feeds/` on R2. The study's preferred `site/feeds/`-only home is rejected as primary: `site/feeds/` is gitignored/R2-only and is in neither Mastermind's git sparse-checkout set (`_SPARSE_PATHS`, macro_refresh.py:77) nor its `_R2_DIRS` (:86). `site/` IS in the sparse set and `site/neuralwebdata` is git-tracked (verified), so the chosen home gives **zero-touch transport**: the artifact materializes in `vendor/macro_src/site/neuralwebdata/` on the bot's next `macro_refresh.refresh()` with no Mastermind sync changes.
2. **The bridge is registry-driven and self-extending** (§3). New Neural Web lobes reach Mastermind's awareness with a one-line `synapse.yml` tag; a rich summary is one registered summarizer function on the Macro side; the Mastermind side never changes per-lobe.
3. **`regime_frame` is not touched.** `world_state.regime` is a strict subset distillation of `data/regime/latest.json` (`_compose_regime`, world_state.py:162-189, pure `reg.get()` — no recomputation); the bot's `budget()` needs fields the subset lacks. NW market synthesis rides as one advisory `market_view` plane; convergence of the two world models is a separate future wave, if ever.
4. **Kernel `armed` re-labeling is mandatory.** `kernel_families.json` `armed=true` means "enough history to display", NOT FDR-cleared. The bridge emits `display_armed` plus `fdr_cleared` (membership in `kernel_decisions.survivors[]`, currently empty; first batch due 2026-10-01) and carries the standing law string. Raw `armed` never crosses the bridge.
5. **Cortex prose stays out of seat prompts.** The memo rides the artifact for operator/UI use; `seat_prompt_block()` excludes it, and W2 carries a sentinel test proving memo text can never appear in seat-prompt output. `/api/ask` is never called by Mastermind builds.
6. **No names beyond the candidate universe cross into prompts — CI-enforced on BOTH blocks.** `candidate_context` covers only tickers already on Mastermind-facing surfaces (§3.1 scope rule). `book_context` is counts and macro-level contradiction records only, and W1 carries a test asserting no bottom-sensors symbol outside the intake union appears anywhere in the serialized `book_context` (red-team: graph thesis/episode labels could someday embed a name; the invariant must not be summarizer-honor-system).
7. **Dark ship (red-team reversal of Rev 1).** `MASTERMIND_NW_CONTEXT` defaults **OFF**. Rev 1's default-ON reasoning leaned on `MASTERMIND_COMMITTEE=1`, but committee is admissible lit because it is structurally subtract-only (de-escalate only); prompt prose into PM/Strategist seats is bidirectional influence, and every prose-adjacent feature (flagship judgment, gate officer, macro risk, risk officer, posture decider) shipped dark. The reader, runlog audit rows, and shadow-input accrual run from day one regardless of the flag (posture-decider W-E.2 discipline); only prompt/plane injection is gated. **Pre-registered arming condition:** after ≥5 consecutive builds with `nw_context status=present` (fresh, no reader errors) in the runlog, the operator may set `MASTERMIND_NW_CONTEXT=1` without further Fable review — this ruling IS the review for the prompt-text-only promotion. Come-back 2026-07-19.

## 2. Answers to the operator's three questions

**Q: What infrastructure layer do we need, and is it build-once or continually upgraded as lobes expand?**
Build-once, two-sided: a Macro-side compiler (`engine/neuralweb/mastermind_context.py`) that assembles one compact, versioned, authority-stamped contract artifact from committed NW outputs, and a Mastermind-side single reader (`brain/neural_web_context.py`) behind the existing advisory-plane and prompt-section patterns. Per-lobe maintenance collapses to: (a) tag the lobe's artifact in `config/synapse.yml` with `mastermind:context` → it appears automatically in the bridge's lobe manifest (existence, asof, staleness, tier, authority) with zero code change; (b) optionally register one summarizer function for a rich distillation. Mastermind renders known lobes richly and unknown lobes generically; it needs no change when a lobe is added.

**Q: Is the regime/market state Mastermind pulls from Macro already embedded in Neural Web, or independent?**
Embedded, not independent. `world_state.json['regime']` is derived by `_compose_regime()` reading the very `data/regime/latest.json` that Mastermind's `regime_frame.py` reads — a strict-subset distillation (17 of 60+ keys), plus `risk_radar_raw` verbatim. There is no second regime model and no divergence risk beyond staleness. Therefore the bridge does NOT replace `regime_frame` (money-path reader, needs full file); it adds NW's *synthesis* (verdict, radar, contradictions, breadth, vol, rotation, data-health) as advisory context.

**Q: Do all signal engines need to talk to Neural Web first, with Mastermind consuming NW's synthesis?**
For market-level synthesis: that is already the architecture (engines → world_state/spine/graph → NW), and the bridge makes Mastermind consume it. For candidate-level intake (us_standouts, altdata, radar): keep the direct reads — they are the bot's registered anchor contracts and NW does not (and must not) originate candidates. Target state: **market synthesis flows engines → NW → bridge → Mastermind; candidate feeds stay direct; NW adds per-candidate context (bottom sensors, options context, graph conflicts) on top of the direct feeds.** No big-bang rewiring.

## 3. Bridge architecture

### 3.1 Macro-side compiler

`engine/neuralweb/mastermind_context.py`, thin CLI `scripts/build_nw_mastermind_context.py` (resilient: exit 0 + `::warning::` on any error).

Two-tier lobe model:

- **Auto-manifest (zero-touch tier):** the compiler scans `config/synapse.yml` for artifacts whose `external_consumers` include `mastermind:context` and emits a generic envelope per artifact: `{artifact_id, path, asof, stale (vs freshness_sla_hours), tier, horizon_role, storage, has_rich_summary}`. Tagging an artifact is the entire cost of making a new lobe visible to Mastermind. W1 seeds the tag on the initial lobe sources (world-state, kernel families/decisions, confluence graph, bottom sensors, options entry state+gate, cortex memo) so the manifest is non-empty at birth and the mechanism is proven.
- **Registered summarizers (rich tier):** an ordered in-module registry `LOBE_SUMMARIZERS: {lobe_name: (source paths, summarize_fn)}`. At birth: `market` (world_state distill), `reliability` (kernel families + decisions + re-labeling per §1.4), `contradictions` (graph contradiction_summary + records), `bottom_sensors` (global state counts + candidate rows), `options_entry` (gate status + candidate rows), `cortex` (memo verbatim + probation), each independently try/except-wrapped → lobe-level `gap_notes`, never a fatal.

Artifact shape: `schema: neural_web_mastermind_context.v1`, `as_of`, `generated_utc`, `is_context_only: true`, `authority` block (all five booleans false), per-lobe `freshness`, `lobes{}` (rich summaries), `lobe_manifest[]` (auto tier), `candidate_context{TICKER}` (bottom row, options row, graph_conflicts, kernel caveat, `allowed_behavior: annotate_only`), `book_context` (top contradictions, decaying families, counts-only bottom summary — no ticker lists), `gap_notes[]`, `source_artifacts[]`, plus the standard neuralweb envelope fields (`schema_version, produced_by, produced_at, inputs_hash, tier`).

**Candidate universe (red-team size fix).** Raw union of the three intake surfaces is ~334 tickers today (standouts 55 named + altdata 55 + radar 273) — too fat. Scope rule: `candidate_context` = ALL tickers named on `us_standouts` (buy/watch/laggards) ∪ `altdata/mastermind` (signals/broken_signals), plus `radar_ticker` tickers ONLY where actionable NW context exists (bottom_state ≠ WATCH or trigger_tier non-null or an options row exists). Rows are sparse (null fields omitted). Hard row cap 250 with `gap_notes` entry on truncation. Budget: hard test cap 200 KB; expected ~60–120 KB.

### 3.2 Publication & transport

- Written to `data/neuralweb/mastermind_context.json` (canonical, git) and `site/neuralwebdata/mastermind_context.json` (public copy, git) by the builder.
- `daily.yml` step "build mastermind context (NW bridge)" slots AFTER "build world state (neural-web W1)" and BEFORE "commit engine outputs" (`git add data/ site/` stages both copies). `if: always()`, non-fatal.
- `build_feeds.py` gains a copy block → `site/feeds/nw_mastermind_context.json` on the public R2 machine plane (feeds dir already in `publish_r2 --dirs`).
- Mastermind transport: none needed. Existing `refresh()` sparse checkout of `site` materializes the file. `site/feeds` R2 sync deliberately NOT added to the bot.

Public exposure ruling: acceptable. Every field derives from artifacts already public (`site/neuralwebdata/*` committed and served; `world_state.json` already on the public R2 feeds bucket; regime/verdict rendered on public pages; options per-ticker fields are display metrics already surfaced on the Options Hub). The artifact carries `is_context_only` and all-false authority.

### 3.3 Mastermind-side reader & integration

`brain/neural_web_context.py` — the single reader:

- Reads only `vendor/macro/site/neuralwebdata/mastermind_context.json`. Validates `schema`, `is_context_only`, `as_of`; reader-internal staleness (age > 4 calendar days → treated as absent-stale). NOT added to `macro_refresh._ANCHOR_DEFS` — an advisory artifact must not be able to mark the whole macro vendor stale.
- Fail-soft everywhere: absent/malformed/stale → stable empty context + audit row; never raises into a build. Never imports Macro engine modules.
- API: `context()`, `candidate(ticker)`, `market_plane()`, `seat_prompt_block(tickers)` (excludes cortex prose — sentinel-tested), `audit_row()`.

Integration points (all additive; red-team construction notes folded in):

1. `brain/market_view.py`: `neural_web` appended to the END of `PLANE_ORDER` **with the paired assignment** `planes['neural_web'] = _adapt_neural_web(...)` in the assembly block — `ordered_planes = {k: planes[k] for k in PLANE_ORDER}` (market_view.py:1125) KeyErrors on every call otherwise. `_adapt_neural_web()` MUST pass `validated=False` to `_plane_record` (or use `_absent_record`): the tilt guard is `status`-based, not `_VALIDATED_PLANES`-based, so omitting it would let the plane sign the tilt — W2 carries an acceptance test that a present+fresh NW plane has `status='advisory'` and never appears in tilt contributors. The `neural_web_out` kwarg threads through BOTH `build()` (market_view.py:1208) and `view()`, and is passed at the phase2 call site (`build('us', write=True)`, phase2.py:278) — otherwise the plane ships as a dead kwarg (the W-I planes are absent in production today for exactly this reason). Update `tests/test_market_view.py:85` (exact PLANE_ORDER equality). `posture_decider` is inert to the new plane (hardcoded `_D_PLANE_NAMES` allowlist; unknown names → None) — verified, and it is added to the reviewer grep list for the record.
2. `bot/phase2.py`: fetch context once per run (flag-independent); `runlog` perception row (`status=present|absent|stale, asof, age_days`); pass `neural_web_out` into `build()`; add optional `nw_context` key to shadow-input rows (absent-safe — loop-maintenance replays must not crash).
3. `brain/pm_conviction.py`: **no new top-level payload key** (the payload JSON is hard-truncated at 9,000 chars — pm_conviction.py:439 — and `tests/test_pm_conviction.py:141` asserts final-key order; a new key risks silent mid-JSON truncation and a broken test). Instead, `_build_prompt()` lazily calls `neural_web_context.seat_prompt_block(...)` and appends a bounded TEXT section (≤ ~1,200 chars) after the E2.5 posture block, following the exact E2.5 lazy-render precedent, headed "NEURAL WEB CONTEXT (context-only, not validated for sizing)". Candidate lines only for names already in the payload's candidate set.
4. `brain/strategist.py`: payload key `neural_web_context` is safe there (`json.dumps(payload)` has no cap; verify no strategist key-order test breaks).

Flag: `MASTERMIND_NW_CONTEXT`, **default OFF** (dark ship per §1.7; reader/audit/shadow always-on; prompt + plane injection gated; pre-registered arming condition; come-back 2026-07-19).

Not wired into (reviewer grep list): `portfolio/risk_sizing.apply`, `brain/regime_frame.budget`, `portfolio/sleeves.enforce_book_caps`, `portfolio/firm_exposure.clamp_book`, `portfolio/cluster_config.load`, `portfolio/position_log.*`, `brain/ledger.close`, `detectors.d5_dead_capital`, `brain/risk_officer`, `brain/macro_risk`, `brain/posture_decider` (inert by allowlist; listed for the record), intake scoring (`_LOADERS`/`_SIMPLE_SOURCES` untouched — NW is not an intake source and cannot add candidates or score).

### 3.4 Registry & CI (Macro)

- `config/synapse.yml`: new entries `neuralweb-mastermind-context` (data path) and `site-neuralweb-mastermind-context` (site path), tier `display`, `horizon_role: context`, producer `scripts/build_nw_mastermind_context.py`. **Role clarity:** the two bridge artifacts themselves carry `external_consumers: [mastermind:anchor]` (the bot reads them directly); the `mastermind:context` role string is the enrollment tag placed on OTHER lobes' artifacts to pull them into the auto-manifest. (`external_consumers` strings have no enum validation — both roles pass `check_synapse_registry.py`; verified.) The builder module is added to `consumers:` of every artifact it reads (world_state, kernel_families, kernel_decisions, confluence-graph, bottom-sensors, options-entry state/gate, cortex memo, us_standouts, altdata mastermind, radar_ticker) to keep the read-gate clean.
- `docs/SIGNAL_BUS.md` regenerated via `python -m scripts.gen_signal_bus_doc` (never hand-edited).
- Tests (W1): artifact schema + authority-all-false + envelope stamp (note: existing `test_neuralweb_envelope.py` is hermetic and does NOT cover new artifacts — the bridge needs its own envelope assertions); gap_notes (not fake neutrals) when inputs missing; 200 KB size cap on a real-data build; candidate scope rule of §3.1; **book_context no-new-names** (no bottom-sensors symbol outside the intake union appears in serialized book_context); `fdr_cleared` false while `survivors[]` empty; no LLM calls in the builder.
- Tests (W2): reader fail-soft (absent/malformed/stale → empty context, no raise); market_view plane advisory-only + tilt-exclusion acceptance test; PLANE_ORDER/planes pairing; **seat_prompt_block cortex-prose sentinel test**; prompt section byte-absent when flag OFF; shadow-input key absent-safe on replay.

## 4. Authority & epistemics (standing law for this bridge)

- Every field is context-only at birth. Authority booleans all false. Promotions (shrink-only) require: pre-registered shadow definitions, accrued shadow evidence, Fable review, registry come-back date. Never add a candidate, never raise size, never loosen a cap, never act on cortex prose.
- Kernel: nothing behavior-facing before the 2026-10-01 FDR batch, and then only `survivors[]` cells (standing law travels inside the artifact).
- Staleness only shrinks: stale/absent context disappears from prompts and planes; it can never make a book more aggressive. (Verified: `_net_posture_tilt` counts only `status=='validated'` planes; absent/None-direction planes cannot create or lower a disagreement.)
- Shadow accrual starts at birth (runlog perception rows + `nw_context` in shadow inputs), flag-independent. The would-have-blocked/shrunk policy replay is a later, pre-registered wave.

## 5. Build waves

- **W1 (Macro, this PR):** compiler + CLI + feeds copy + daily.yml step + synapse registration (incl. seed `mastermind:context` tags) + SIGNAL_BUS regen + tests + this doc + the Codex study committed for the record. Zero Mastermind behavior.
- **W2 (Mastermind, local worktree → master):** reader + market_view plane (paired edits + kwarg threading) + phase2 audit/shadow key + PM lazy text block + strategist payload key + tests + masterplan wave entry with come-back 2026-07-19 (arming review per §1.7). Ordering: merges only after W1 lands on macro main.
- **W3 (review):** Opus red-team of both diffs (money-path grep incl. posture_decider, staleness behavior, prompt scope, CI gates, named-test updates) — FIX_THEN_MERGE.
- **W-next (deferred):** dashboard UI panel; shrink-only promotion gauntlet off the shadow ledger; world-model convergence study; `mastermind:context` tagging sweep of additional lobes.

## 6. Open-questions adjudication (Codex study §Open Questions)

1. Artifact home: `site/neuralwebdata/` (public data product) + `data/neuralweb/` canonical + feeds/R2 machine copy. 2. No new sync plumbing; git sparse `site` carries it; `site/feeds` stays off the bot. 3. Phase 2 = prompts + advisory plane + audit/shadow; UI panel deferred. 4. Bridge emits a pre-summarized `market` lobe; the bot adapter consumes it directly. 5. Candidate context restricted per §3.1 scope rule; bottom_sensors globals are counts-only. 6. Live flow stays terminal-only. 7. Promotion metrics deferred to the promotion wave; accrual starts now. 8. Public exposure acceptable (all-public derivations, context-only stamps). 9. Yes — synapse/SIGNAL_BUS registration lands in W1 before the reader (W2). 10. Prompt sections ship with payload-shape + absent-degradation + sentinel tests (house pattern); no full-prompt snapshot gate exists today.

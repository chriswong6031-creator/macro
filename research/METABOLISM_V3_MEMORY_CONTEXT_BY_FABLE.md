# Metabolism v3 — Memory & Context Intelligence (the reliability substrate)

**Program owner:** Fable (main-loop orchestrator). **Status:** chartered 2026-07-10. **Tier:** display-only / INERT (no scored surface, no live effect; the whole Metabolism remains paused pending the operator arming checklist). **Parent:** `METABOLISM_V2_MASTERPLAN_BY_FABLE.md` (#2100) — this refines §3 "The orchestrator brain — prompt + memory," the operator-flagged crux.

---

## 0. Why this exists — the operator's ask

> "Conduct further revamping and upgrading to increase intelligence to a higher level.
> • upgrade the memory and context-aware mechanisms and systems to improve LLM reliability
> • provide necessary context so they are able to best perform their loops and self-improving loops."

The Metabolism v2 built the *machinery* of a self-improving loop (SENSE→PROPOSE→ADJUDICATE→BUILD→VERIFY→LEARN). But a loop is only as reliable as the memory it recalls and the context it reasons over. An audit of the shipped v2 brain (`orchestrator_brain.py`, `memory.py`) found the recall/context layer is the weakest link — it defeats the very anti-repetition it was built to provide. This program hardens it.

## 1. The diagnosis (audit of the shipped v2 brain, 2026-07-10)

Seven concrete reliability gaps, each mapped to the Fable-mode commitment it violates:

| # | Gap (observed in code) | Fable-mode principle violated |
|---|---|---|
| G1 | **Lesson recall is a chronological byte-tail** — `orchestrator_brain._load_recent_lessons` and `memory.load_recent_lessons` both take the last N bytes of `lessons.jsonl`. A construction that FAILED 40 cycles ago scrolls off the tail and gets re-proposed. The one job of the lessons ledger ("PROPOSE stops repeating dead constructions") is defeated by its own recall path. | C3 update-before-retry; §3.1 buy information by discrimination not volume |
| G2 | **No provenance/freshness on any context block** — organism-state, case-law, lessons carry no machine-readable `as_of`/staleness. A loop reasoning on a 5-day-stale `organism_state.json` gets no signal it is stale. | C1 evidence over plausibility; §3.8 verify freshness |
| G3 | **No anti-repetition index** — `lessons.jsonl` has a `construction` field but nothing fingerprints/indexes it into a deterministic "tried-before → receipt" lookup for ADJUDICATE. | C3 update-before-retry |
| G4 | **Trajectory computed but not surfaced** — `trajectory.py` derives per-lobe slope / fitness-delta / regime, but is **not wired into the prompt**. R-V2-1 explicitly asks the mind to reason over "trajectory slope, biggest strategic gap"; it currently cannot see either. | §4.1 constraint provenance; R-V2-1 |
| G5 | **Crude truncation defeats relevance** — byte-caps do `encoded[:cap]`, so the *most* relevant ruling/lesson can be chopped because it sorted late. | §3.1 discrimination not volume |
| G6 | **Doctrine is prose, not a checkable scaffold** — fable-mode is injected as text ("predict before the probe") but no structured receipt makes predict→falsify→positive-control auditable; and nothing checks the loop's output references (lobe/sensor/ruling ids) actually exist → hallucinated references reach the docket. | pre-send gate; §3.4 positive-control; §3.5 absence bounds |
| G7 | **Two divergent prompt paths** — `dream.py` builds its own prompt; only `agenda.py` uses `_build_orchestrator_system`. §3/R-V2-1 require the brain be shared by "organism_state pass, agenda, dream" for a consistent persona. | consistency |

None of these is a signal-path change. All fixes are **deterministic** (the LLM only reasons over what the deterministic layer surfaces) — they widen and sharpen the context, never originate a signal. R-AUT-1 / NW-ART1 are untouched.

## 2. Rulings (R-V3-1 … R-V3-6)

**R-V3-1 — Provenance is mandatory on every context block.** Every block the brain assembles is wrapped with `{source, as_of, age, is_stale, sla_days}` by a deterministic `engine/metabolism/provenance.py`, and the prompt opens with a CONTEXT FRESHNESS header so the loop *sees* what is stale before reasoning on it. Per-source SLAs live in `config/metabolism_context_sla.yml`, which **joins the IMMUTABLE set** (R-V2-8: the mind cannot loosen its own freshness alarms). A stale-but-present block is still shown (never silently dropped) — it is shown *flagged*.

**R-V3-2 — Memory recall is relevance-ranked, not chronological.** `engine/metabolism/recall.py` scores each lesson by `(lobe match, construction-token overlap, verdict weight, recency tiebreak)` and returns the top-K within the byte budget. **FAIL verdicts are surfaced preferentially** — they are the anti-repetition signal, and the whole point is that they must survive recall. Boring-baseline (§4.2): deterministic token-overlap (BM25-lite), **no embeddings / no vector DB** — the lessons corpus is small, and a deterministic scorer is runner-safe, reproducible, and needs no key. This kills both byte-tail duplicates (G1).

**R-V3-3 — Anti-repetition FLAGS with a receipt; it never silently auto-rejects.** A deterministic construction-fingerprint (from `recall.fingerprint_construction`) lets ADJUDICATE surface a prior-FAIL receipt when a new proposal matches a dead construction. Per house law (`context-accrual-fundamental-goal`, gauntlet-is-not-a-build-gate, `factor-kill-interaction-followup`): **"a kill closes the specific construction tested, not the search space."** So the guard is *informational* — it prints the prior receipt and requires the proposal to state what is materially different; it does **not** hard-block. Hard-blocking on a fingerprint match would ossify the search and is forbidden.

**R-V3-4 — Trajectory + strategic gap are first-class prompt context.** `engine/metabolism/strategic.py` wraps `trajectory.py` (slope, fitness-delta, regime, compounding-vs-stagnating classification) into a TRAJECTORY block, and computes a cross-lobe STRATEGIC GAP rollup (which lobes stagnate; where the biggest opportunity is). Deterministic; closes R-V2-1's explicit ask (G4). No LLM.

**R-V3-5 — The reasoning scaffold operationalizes the pre-send gate, and grounding is machine-checked.** (a) A structured reasoning-receipt schema — `{fork, prediction, cheapest_falsifier, falsifier_result, positive_control, claims:[{claim, source}]}` — turns the fable-mode pre-send gate from prose into an artifact the loop fills. (b) `engine/metabolism/grounding.py` (deterministic, no LLM) checks every `lobe_id` / `sensor` / `ruling_id` the loop's output references actually exists in `synapse.yml` / `ruling_graph.yml`; ungrounded references are flagged in the digest (display-tier). Catches hallucinated references before the docket (G6). The schema doc joins the IMMUTABLE set.

**R-V3-6 — One prompt path, relevance-aware packing.** `dream.py` is migrated onto `_build_orchestrator_system` (G7). Truncation becomes relevance-aware: keep the highest-scored items whole and drop the lowest — never chop the top item mid-way (G5). This is the single integration PR that touches the hot `orchestrator_brain.py`; it lands last and single-threaded to avoid a merge-race on that file.

**Inherited fences (restated, binding):** everything is `is_context_only=True` / `display_only=True`; every new module is NEVER-RAISE (returns a safe fallback, never crashes a loop pass); no module reads `~/` (runner TCC/FS-isolation); no deterministic screen calls an LLM; new IMMUTABLE configs join the grader-manifest + self-mod fence (`check_self_mod_fence.py`, `check_grader_manifest.py`); the whole program stays paused behind `AUTONOMY_PAUSED`.

## 3. Wave docket (all INERT; each wave = build → independent-Opus-review → fix → merge)

Merge-race-safe by construction: the two substrate waves are **new files only** (zero collision with each other or with `main`), so they build in parallel; the hot-file integration lands last and alone.

### W1 — Memory substrate (reliability core) — new files, parallel-safe
- `engine/metabolism/provenance.py` — `stamp_context(blocks)`, `render_freshness_header(stamped)` (R-V3-1).
- `config/metabolism_context_sla.yml` — per-source staleness SLA (IMMUTABLE).
- `engine/metabolism/recall.py` — `recall_lessons(lobe, construction_terms, sensors, byte_budget)`, `fingerprint_construction(text)` (R-V3-2).
- `tests/test_metabolism_v3_memory.py`.

### W2 — Context substrate (loop performance) — new files, parallel-safe
- `engine/metabolism/strategic.py` — `build_trajectory_block(lobe)`, `build_strategic_gap(organism_state)` (R-V3-4).
- `engine/metabolism/grounding.py` — `validate_grounding(payload)` → ungrounded-reference list (R-V3-5b).
- `docs/METABOLISM_REASONING_RECEIPT.md` — the pre-send-gate receipt schema (R-V3-5a).
- `tests/test_metabolism_v3_context.py`.

### W3 — Integration + fences — the single writer of the hot brain file, lands last
- Wire provenance/recall/strategic/grounding into `_build_orchestrator_system`; replace the byte-tail `_load_recent_lessons` with `recall.recall_lessons`; add FRESHNESS + TRAJECTORY + STRATEGIC-GAP blocks; relevance-aware packing (R-V3-6).
- Migrate `dream.py` onto the unified brain.
- Anti-repetition FLAG in `adjudicate.py` (R-V3-3), informational only.
- Register `config/metabolism_context_sla.yml` + the receipt schema into `check_self_mod_fence.py` + grader manifest; add CI + `tests/test_metabolism_v3_integration.py`.

## 4. Verification bar (every wave)
Bare `pytest` (never piped — a pipe swallows the exit code) on the wave's tests **and** the full existing metabolism suite (`tests/test_metabolism*.py`) green before merge. Each new module carries a NEVER-RAISE test (inject a corrupt/missing artifact → returns the safe fallback, does not raise). W3 additionally: `check_self_mod_fence.py` selftest passes with the new IMMUTABLE entries; the count-pin in `tests/test_signal_bus_doc.py` unaffected (no synapse artifact registered — these are engine helpers, not producers).

## 5. Non-goals / explicit kills (anti-duplication registry)
- **No vector DB / embeddings** (R-V3-2) — deterministic token-overlap is the boring baseline that wins; revisit only if the lessons corpus exceeds ~10⁴ rows (it will not for years).
- **No hard-block on fingerprint match** (R-V3-3) — forbidden by the search-space house law; the guard flags, the operator/loop justifies.
- **No LLM in any deterministic screen** — provenance, recall scoring, grounding, and the anti-repetition index are all pure functions. The LLM only reasons over their output.
- **No new scored surface, no synapse producer, no live effect** — display-tier engine helpers only.

## 6. Clocks
No accrual clock — this is infrastructure, live the moment the Metabolism is armed. First real exercise = the first armed cycle after the operator completes the v2 arming checklist. Retro-check at that point: does the freshness header fire on a deliberately-staled artifact; does recall surface a seeded prior-FAIL for a re-attempted construction; does grounding flag a seeded bogus `lobe_id`.

*Related: `METABOLISM_V2_MASTERPLAN_BY_FABLE.md`, `autonomic-loop-metabolism-program` (memory), `context-accrual-fundamental-goal` (memory), the vendored `config/fable_mode_core.md`.*

# Metabolism V9 — The Attention Economy (lobe prioritization under scarce tokens)

**Author:** Fable (main loop), operator-directed 2026-07-12
**Status:** BUILD (operator order — this is not a loop-authored proposal)
**Prior art:** V2 (orchestrator mind), V4 (multi-lobe propose), V6 (lobe genesis), V8 (meta-learning prior)

## 0. Problem

The metabolism treats every lobe as equally deserving of its scarce resources.
The three binding scarcities today:

1. **Agenda slots** — `max_docket_size` (5) items per cycle across the whole organism.
2. **PROPOSE Opus calls** — `--all-lobes` runs one full lobe-brain call per
   loop-managed lobe. V6 genesis grows this roster; spend grows linearly with
   lobe count regardless of how much each lobe matters.
3. **BUILD session slots** — 3 OAuth keys × `max_window_sessions_per_key` (5)
   per dispatch window. Grants are dispatched in adjudication order, not by
   how much the lobe matters to Neural Web success.

Nothing in the loop knows that `world-state` (the core NW context feeder read
by Mastermind every day) matters more than a weekly ancillary display lobe.
The operator's directive: the orchestrator must assess and prioritize lobes by
their criticality to Neural Web success — heavier focus on lobes that provide
critical context/data to NW and crucial engines, deprioritizing ancillary,
less-frequent-run support — **at the orchestrator's discretion**, because token
budgets are finite.

## 1. Design — two layers, discretion bounded by floors

Mirrors the house pattern already ratified in AGENDA (LLM ranks, code enforces
floors) and DREAM (LLM writes prior, deterministic de-rank applies it).

### Layer 1 — deterministic criticality evidence (code, no LLM)

`engine/metabolism/criticality.py` profiles **every** lobe in
`config/lobe_charters.yml` from existing sources of truth only:

| Evidence | Source |
|---|---|
| `nw_core` (artifact backs a registered NW summarizer; `market_data` flag if it backs a `_MARKET_DATA_LOBES` summarizer) | imported from `engine.neuralweb.mastermind_context._LOBE_TO_ARTIFACT_IDS` / `_MARKET_DATA_LOBES` — no hand copy |
| `nw_context` / `nw_anchor` / `nw_vendored` | `external_consumers` tags in `config/synapse.yml` |
| `consumer_fanout` (count of `consumers` + `external_consumers`) | `config/synapse.yml` |
| `cadence`, `freshness_sla_hours` | `config/synapse.yml` |
| `tier`, `lifecycle_state`, `information_domain`, `loop_managed` | `config/lobe_charters.yml` |

Deterministic **structural band** (transparent rule ladder, first match wins):

- **CRITICAL** — `nw_core` (summarizer source) or `nw_anchor`: the artifacts
  that *are* the NW context packet.
- **HIGH** — `mastermind:context` tagged (auto-manifest NW feeder), OR
  `consumer_fanout >= 4`, OR tier `scored`/`confirmer`.
- **STANDARD** — daily-cadence active lobes not matching above.
- **ANCILLARY** — everything else (weekly/ad-hoc cadence, low fanout, no NW
  tags) — the "ancillary support to less frequent runs" class.

Writes `data/metabolism/lobe_criticality.json`
(schema `metabolism.criticality.v1`, display-tier authority block).
This is **evidence, not the decision**.

### Layer 2 — discretionary attention allocation (orchestrator LLM)

`engine/metabolism/attention.py` — a stateless Opus pass (new role key
`attention` in `config/metabolism_roles.yml`) reads the criticality evidence +
organism_state + fitness cards + open insight-bus rows and assigns each lobe an
**attention band**: `FOCUS` / `STANDARD` / `MAINTENANCE` / `DORMANT`, each with
a one-line rationale. This is where the operator-granted discretion lives: the
LLM may promote a structurally-ANCILLARY lobe whose fitness is cratering, or
ease off a CRITICAL lobe that is healthy and needs no work this cycle.

**Deterministic guardrails, enforced in code after every LLM call** (mirror of
the agenda severity floor):

- **G1 criticality floor** — structural CRITICAL may never sit below STANDARD;
  structural HIGH may never be DORMANT. `floored: true` recorded when applied.
- **G2 focus scarcity** — at most `max_focus_lobes` (config, default 8) in
  FOCUS; overflow demoted to STANDARD in structural-band order (CRITICAL kept
  first). Focus only means something if it is scarce.
- **G3 urgent-fix supremacy** — attention never suppresses the severity floor.
  A high-severity insight row targeting a DORMANT lobe still forces URGENT_FIX
  in the agenda, and exempts that lobe from the PROPOSE skip that cycle.
- **G4 degraded honesty** — no provider / parse failure → allocation is the
  pure structural mapping (CRITICAL→FOCUS, HIGH→STANDARD, STANDARD→STANDARD,
  ANCILLARY→MAINTENANCE) with `degraded_reason` set. The loop never stalls on
  the allocator.
- **G5 cap asymmetry** — attention only scales resources DOWN within the
  IMMUTABLE `metabolism_budget.yml` caps. It can never raise a cap, add a
  session, or grow a docket beyond `max_docket_size`.

Writes `data/metabolism/attention_allocation.json`
(schema `metabolism.attention.v1`) and appends one row per cycle to
`data/metabolism/attention_history.jsonl` (append-only; DREAM meta-learning
input, auditability).

### Band → resource mapping (`config/metabolism_attention.yml`, operator policy)

| Band | `docket_share` (× per-lobe `max_docket_size`) | PROPOSE call | BUILD dispatch priority |
|---|---|---|---|
| FOCUS | 1.0 (→ 5) | full | 0 (first) |
| STANDARD | 0.6 (→ 3) | full | 1 |
| MAINTENANCE | 0.2 (→ 1) | reduced | 2 |
| DORMANT | 0.0 | **skipped** (journaled `attention_skip`; G3 exemption → 1-slot fix docket) | 3 |

The DORMANT skip is the principal token saver: PROPOSE spends one full Opus
lobe-brain call per lobe per cycle; a skipped lobe costs zero.

## 2. Enforcement wiring (where attention actually bites)

| Site | Change |
|---|---|
| `.github/workflows/metabolism-agenda.yml` | Step 3.7 (after scout, before agenda): build criticality then attention — best-effort `|| echo degraded (continuing)` like the sibling steps; artifacts committed by the existing `git add data/metabolism` |
| `engine/metabolism/orchestrator_brain.py` | new Part 5h `## Attention Allocation (lobe focus map)` — compact render (focus list, maintenance/dormant lists, counts), byte-capped 1200, tolerant of absence |
| `engine/metabolism/agenda.py` | deterministic post-pass `_apply_attention_ordering` after severity floor + prior de-rank: stable-sort items within each bucket by attention weight (forced-floor items pinned first); at the `max_docket_size` trim, lower-attention regular items are dropped first |
| `scripts/metabolism_propose.py` | `_effective_docket_size(lobe)` = max(1, floor(cap × docket_share)) for non-DORMANT; DORMANT → journaled skip unless G3 exemption (then docket=1). `til` first-position backward-compat unchanged |
| `.github/workflows/metabolism-build.yml` + `attention.rank_cycle_ids` | the scheduled BUILD lane processes ONE docket per run; the pick among open `metabolism/propose-*` branches is the binding scarcity point and is now attention-ranked: newest cycle date first (stale dockets never shadow today's work), then dispatch priority (FOCUS first), then the pre-V9 lexicographic tie-break; falls back to the pre-V9 pick on any error |
| `scripts/metabolism_build.py` | in-lane proposal sort by band dispatch priority (defense-in-depth — production dockets are single-lobe today, so this becomes live only if a multi-lobe docket shape ever ships); within a band, adjudication order preserved (no starvation — attention orders, never drops) |

## 3. Rulings

- **R-V9-1 (resource-lever-only).** Attention allocates *loop* resources
  (tokens, docket slots, session order) only. It carries the standard
  display-tier authority block and may never touch a market-facing surface:
  no rank, gate, size, escalation, board ordering, or mastermind arming.
- **R-V9-2 (two-layer law).** Deterministic criticality evidence (code) +
  discretionary allocation (LLM), with discretion bounded by G1/G2. Evidence
  derives from `synapse.yml`, `lobe_charters.yml`, and imported
  `mastermind_context` constants only — no second source of truth.
- **R-V9-3 (urgent-fix supremacy).** No attention state may suppress the
  deterministic severity floor or block an URGENT_FIX. DORMANT is a stance on
  *improvement* spend, not on repair.
- **R-V9-4 (cap asymmetry).** Attention scales down within IMMUTABLE caps;
  it can never scale anything up past `metabolism_budget.yml`.
- **R-V9-5 (focus scarcity).** `max_focus_lobes` bounds the FOCUS band;
  deterministic overflow demotion.
- **R-V9-6 (degraded honesty).** Allocator failure → structural mapping +
  `degraded_reason`; the loop proceeds. Never-raise throughout.
- **R-V9-7 (visibility law).** Every DORMANT skip is journaled
  (`attention_skip`), never silent; allocations append to an immutable
  history ledger.
- **R-V9-8 (policy immutability).** `config/metabolism_attention.yml` is
  operator policy — loop-authored PRs may not modify it (mirror R-V2-8);
  changes require a T2 operator tap.
- **R-V9-9 (no starvation).** Attention may reorder BUILD dispatch but never
  drop a granted proposal; within a band, adjudication order is preserved.
  The live enforcement point is the scheduled BUILD workflow's pick among
  open propose branches (`attention.rank_cycle_ids`); newest cycle date
  always dominates attention so a stale FOCUS docket cannot shadow today's
  work. `config/metabolism_attention.yml` is fenced in
  `scripts/check_self_mod_fence.py` IMMUTABLE_PATTERNS (R-V9-8 is
  structural, not honor-system).
- **R-V9-10 (attention ≠ lifecycle).** DORMANT is a per-cycle resource
  stance, not a roster state. Lifecycle transitions remain the exclusive
  authority of the V6 lifecycle/genesis machinery.

## 4. Schemas

`data/metabolism/lobe_criticality.json` — `metabolism.criticality.v1`:

```json
{
  "schema": "metabolism.criticality.v1",
  "as_of": "YYYY-MM-DD",
  "generated_by": "metabolism_criticality",
  "lobes": {
    "<lobe_id>": {
      "structural_band": "CRITICAL|HIGH|STANDARD|ANCILLARY",
      "nw_core": false, "market_data": false,
      "nw_context": false, "nw_anchor": false, "nw_vendored": false,
      "consumer_fanout": 0, "cadence": "daily|weekly|...|null",
      "freshness_sla_hours": null, "tier": "display",
      "information_domain": "context", "loop_managed": false,
      "lifecycle_state": "active"
    }
  },
  "counts": {"CRITICAL": 0, "HIGH": 0, "STANDARD": 0, "ANCILLARY": 0},
  "authority": { "is_context_only": true, "...": "standard display-tier block" }
}
```

`data/metabolism/attention_allocation.json` — `metabolism.attention.v1`:

```json
{
  "schema": "metabolism.attention.v1",
  "cycle_id": "…", "as_of": "YYYY-MM-DD",
  "generated_by": "metabolism_attention",
  "provider": "oauth|anthropic|null", "degraded_reason": null,
  "allocations": {
    "<lobe_id>": {
      "band": "FOCUS|STANDARD|MAINTENANCE|DORMANT",
      "weight": 1.0,
      "structural_band": "CRITICAL",
      "llm_band": "FOCUS", "floored": false,
      "rationale": "one line citing evidence"
    }
  },
  "focus_lobes": ["…"],
  "authority": { "is_context_only": true, "...": "standard display-tier block" }
}
```

## 5. Waves

- **W1 (this build):** criticality.py + attention.py + config policy +
  roles entry + orchestrator_brain Part 5h + agenda ordering + propose
  scaling/skip + build dispatch ordering + agenda-workflow step + tests +
  ci.yml whitelist rows.
- **W2 (deferred, needs accrual):** DREAM reads `attention_history.jsonl` vs
  realized VERIFY deltas — did FOCUS lobes actually compound faster? Emit a
  calibration note into the preference prior. Come-back: 2026-08-15.
- **W3 (deferred):** admin panel card rendering the current focus map.

## 6. Explicit non-goals

- No change to `metabolism_budget.yml` (IMMUTABLE; untouched).
- No lifecycle authority (R-V9-10).
- No market-facing surface — nothing here renders to the site.
- No genesis-throughput change: newborns land STANDARD by default until the
  allocator has evidence (structural band computes on charter registration).

# Eval OS A1 — evidence-provider mapping and derived status contract

**Operation:** `eval-os-a1-evidence-view-20260828-sol-001`  
**Workstream:** `WS:EVAL-OS-EVIDENCE-VIEW`  
**Census head:** `3ed822213caa096b8665b21ce9c3c3f5c860064f`  
**Authority:** `research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md`

This is the required pre-code mapping for A1. It records which existing owner may answer
which part of the evidence view and freezes the smallest derived `evidence_status`
contract. It creates no registry, measurement store, promotion service, score, or authority.

## 1. Exact T1 census

`python3 scripts/build_intelligence_registry.py --json` at the census head produced 380
canonical engine cells and seven exclusions. All 645 Synapse artifacts were mapped.

| T1 field | Current census |
|---|---:|
| `output_class = null` | 273 |
| `classification_state` | 15 |
| `descriptive` | 59 |
| `detection_event` | 7 |
| `predictive` | 21 |
| `ranking` | 3 |
| `salience` | 2 |
| `generative` | 0 |
| `graded_by_design = yes` | 100 |
| `graded_by_design = no — descriptive` | 75 |
| `graded_by_design = no — not yet` | 205 |
| `validation_state = validated` | 1 |
| `validation_state = accruing` | 1 |
| `validation_state = phase0` | 378 |
| `validation_state = falsified/retired` | 0 |

The 273 null classes comprise 271 display-only cells where a class is not required and two
evaluation-gate cells whose class is still `required_but_uncurated`:

- `engine/neuralweb/cortex.py::neural-web`
- `engine/options_structure.py::momoedge`

These nulls remain JSON `null`. A1 never guesses a class to make the view look complete.

## 2. Existing providers and legal read seams

| Question A1 answers | Canonical owner/read seam | Fields A1 may derive | Fields A1 may not invent |
|---|---|---|---|
| Which engine/output exists? | T1 `scripts.build_intelligence_registry.build()` / `engine.intelligence_registry.build_registry()` | engine identity, class and rationale, authority, ledger binding, gradeability semantics, declared horizon, lifecycle state/evidence, evidence refs | a second engine row or curated class |
| Can the current output be trusted operationally? | T4 `scripts.build_output_health.build_with_registry()` / `engine.output_health` | worst health, blindness, assessment/reason codes, dependency bounds | performance, evidence strength, promotion |
| What does a qledger-bound forward record lawfully say? | `engine.qledger.load_claims()`, `load_grades()`, `claim_window()`, and `scripts.grade_qledger.compute_promotion_readiness()` | per-family/horizon honest N, maturity, explicit clock basis, evidence basis, coverage, refusal reasons and projected readiness | pooled mixed-basis figures, a new grade, or promotion authority |
| Has a P3 adapter family's forward clock begun? | `engine.qledger_evidence_clock.read_start()` | first accepted prospective registration, declared horizon value/unit, triggering Git SHA | a seeded/backdated clock or a substitute timestamp |
| Is matched-control evidence applicable and live? | `engine.qledger.family_control_policy()` and `read_control_clock_start()` through the existing readiness result | governed basis, clock-start/coverage/refusal evidence | policy inferred from row availability or a benchmark fallback |
| Is an owner-native engine validated, accruing, falsified, retired, or intentionally ungraded? | T1's derived `validation_state`, `validation_state_evidence`, `graded_by_design`, `graded_by_design_source`, `ledger`, and `evidence_ref` | the existing owner's lifecycle/semantic disposition and provenance | generic win-rate/return metrics for an owner with no standard read adapter |

The overlay stays four-key-only. A1 reads the full T1 row already returned in memory; it does
not add evidence fields to `config/intelligence_registry_overlay.yml`.

## 3. Provider selection by output class

`output_class` selects the legal metric vocabulary; it is not a provider router. Provider
selection starts from the T1 engine's concrete ledger/lifecycle binding. The class then limits
what A1 is allowed to display.

| T1 output class | Legal evidence vocabulary | A1 provider rule |
|---|---|---|
| `predictive` | declared-ruler prospective outcomes, honest independent-date N, benchmark or governed matched-control basis, coverage and maturity | Use qledger only for a concrete direct/adapter family binding; otherwise show T1 owner-native lifecycle/ledger refs and explicit unavailable metric fields. |
| `ranking` | rank IC, monotonicity and top-minus-bottom spread at the owner's ruler | Owner-native lifecycle/ledger refs only until that owner exposes a standard reader. Never substitute qledger hit rate. |
| `classification_state` | transition lag, state stability and conditional forward distribution | Owner-native lifecycle/ledger refs only. Never label self-defined-state accuracy as validation. |
| `detection_event` | precision/recall against the owner's curated event truth and false positives per unit time | Owner-native lifecycle/ledger refs only. Never substitute directional returns. |
| `descriptive` | reconciliation, reproducibility and freshness | Use T1 gradeability semantics plus T4 health. Forward-return fields stay absent. A descriptive class alone does not prove `Ungraded by design`; T1 must carry the semantic evidence. |
| `salience` | realised-magnitude rank/coverage; no directional hit rate | Use qledger only for a concrete binding and preserve `evidence_basis=not_applicable`; otherwise owner-native refs. |
| `generative` | the existing response-eval owner and frozen benchmark, when a concrete T1 binding exists | No current T1 row uses this class. Absence of a binding is `Accruing`, never a model-generated grade. |
| `null` | no metric contract | Preserve null. T1 semantic evidence may still prove `Ungraded by design`; otherwise the engine remains `Accruing` or `Degraded` with a named class gap. |

### 3.1 Concrete qledger binding

A1 recognizes no hand-authored engine list. A qledger family is concrete only when one of these
existing-owner relations resolves:

1. T1 supplies `ledger_evidence.desk` for `ledger = qledger:<desk>`; or
2. a T1 owner-native ledger's directory name exactly equals one of
   `engine.qledger_desk_adapter.known_families()`.

The second relation joins the existing P3 translator owner to its T1 source ledger without
copying its three-family table. At the census head it resolves `stock_desk`, `thematic_desk`,
and `demand_chain`. A family not reached by either rule remains owner-native; A1 does not infer a
binding from producer names, owner-program names, performance fields, or approximate text.

## 4. Derived `evidence_status` contract

Every canonical T1 engine receives exactly one display disposition from this closed vocabulary:

`Validated` · `Accruing` · `Ungraded by design` · `Degraded` · `Disproven`

The result is a read-only projection. It carries ordered reason codes and owner references, not a
numeric evidence score. The deterministic precedence is:

1. **Disproven** — T1's owner-native lifecycle is terminal `falsified` or `retired`, with its
   species/DNR evidence retained. A1 does not create the terminal decision.
2. **Degraded** — no terminal disproval exists, and T4 reports `degraded`, `stale`, or
   `unavailable`; any output is blind (`assessment_status=could_not_look`); or a required
   provider could not be read. Blindness is named separately from a definite unhealthy verdict.
3. **Validated** — the output class is non-null, T1's owner-native lifecycle says `validated`,
   and no health/provider/basis blocker above applies. Qledger `ready=true` is supporting
   measurement only and can never originate this status.
4. **Ungraded by design** — T1 says `graded_by_design = no — descriptive` and carries a non-empty
   derived/curated semantic source. A descriptive class by itself, a missing ledger, a null class,
   or zero rows is insufficient.
5. **Accruing** — every other honest nonterminal state: `phase0`/`accruing`, null or unsupported
   output class, zero/immature sample, unresolved ruler/control, no clock start, legacy-only
   authority evidence, or a mixed explicit basis that refuses a pooled verdict.

This precedence makes a currently broken validated engine display `Degraded`, preserves a
terminal owner decision as `Disproven`, and cannot launder an incomplete record into
`Ungraded by design`.

## 5. Per-engine evidence payload

The derived payload is minimal and nullable:

| Field | Meaning |
|---|---|
| `evidence_status` | one label from the closed vocabulary |
| `evidence_reason_codes` | ordered machine-readable reasons for the disposition |
| `evidence_refs` | T1 evidence refs, bound species/DNR refs, ledger ref, and qledger clock/provider refs where present |
| `evidence_provider` | `t1_owner_native` or `qledger`, concrete binding, and read status |
| `evidence_ruler` | T1 declared horizon plus qledger declared horizon value/unit/market when available; nulls stay null |
| `evidence_basis` | named qledger evidence/clock basis, excluded bases and `pooling_refused`; never a blended basis |
| `evidence_maturity` | T1 lifecycle plus qledger honest N/needed/projected date at each lawful rung when available |
| `evidence_coverage` | owner-provided cohort/control coverage and rowless/refusal census when applicable |

Unsupported owner-native metrics remain null with a reason. A1 never opens an arbitrary file and
guesses its schema from the filename.

## 6. CEO ordering

The global view always emits all five bands in this evidence order, including empty bands:

1. `Validated`
2. `Accruing`
3. `Ungraded by design`
4. `Degraded`
5. `Disproven`

Within a band engines sort by stable `engine_id`. Cross-class sample sizes and performance are not
comparable, so they never determine global order. There is no per-engine rank number or magic
score; the status bands and their reasons are the ordering contract.

## 7. Required refusal cases

- An empty `Validated` band is emitted with count zero.
- A null `output_class` remains null in panel and detail responses.
- Legacy plus explicit evidence and incompatible explicit bases are never pooled. A mixed
  explicit parent verdict stays `Accruing`; individually named per-basis evidence may be shown.
- Zero rows, an unstarted clock, or an immature ruler stays `Accruing` with the actual owner
  reason; zero is never read as failure or validation.
- T4 blindness/degradation produces `Degraded` without changing the underlying owner evidence.
- `Ungraded by design` requires T1 semantic evidence.
- `Disproven` requires an existing terminal owner state and retains its evidence reference.

## 8. No-persistence proof target

A1 may extend only the existing in-process Intelligence OS cache and existing GET payloads. It
must not create `data/*evidence*`, `site/*score*`, a database/table, a generated registry/view, or
any write path. Tests must snapshot the fixture tree before and after both list and detail reads.

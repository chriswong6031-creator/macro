# Entity/Thesis/Mechanism Registry

Schema: `neuralweb.entity_thesis_mechanism.v1`
Artifact: `data/neuralweb/entity_thesis_mechanism_registry.json`
Builder: `scripts/build_entity_thesis_mechanism_registry.py`
CI guard: `scripts/check_entity_thesis_registry.py` (codes ETM-C1..C7)
Handoff: `research/fable_exit/05_ENTITY_THESIS_MECHANISM_REGISTRY_HANDOFF.md`
Signal Bus tier: `infrastructure` — SLA 30 h, `horizon_role: context`

---

## In plain English

The repo has many strong local ID systems (entity resolver, species registry,
research factory candidates, governance events, qledger claims, trial ledger).
They do not talk to each other.

The Entity/Thesis/Mechanism Registry is a **typed, display-only crosswalk** that
answers one question:

> Is this ticker, thesis, mechanism, claim, species, trial family, governance
> event, or PR the same idea wearing different clothes?

It does not replace any of those systems. It does not gate, rank, score, or size
anything. It is a connective substrate: an inspectable graph that reduces
duplicate research, hidden thesis concentration, and planning overhead.

---

## What the registry is

The registry is a JSON artifact built deterministically each nightly run. Every
row is a typed record that links IDs from existing local systems to a common
registry ID. The registry ID is in a namespaced format (see table below); the
local system IDs are never renamed.

**Authority block** (enforced by the builder, not overridable):

```json
{
  "role": "display_only",
  "can_gate": false,
  "can_rank": false,
  "can_size": false,
  "allowed_actions": ["display", "explain", "dedup_context"],
  "forbidden_actions": ["score", "size", "originate", "gate", "rank", "promote"]
}
```

---

## Artifact location and schema

| Field | Value |
|---|---|
| Output path | `data/neuralweb/entity_thesis_mechanism_registry.json` |
| Schema | `neuralweb.entity_thesis_mechanism.v1` |
| Top-level field `as_of` | Date of most recent nightly run |
| Top-level field `authority` | Authority block (display_only) |
| Top-level field `rows` | List of typed crosswalk records |
| Top-level field `conflicts` | List of provenance conflict notes |
| Top-level field `possible_duplicates` | Token-overlap suggestions (context only) |

No `site/` copy in v1 (ETM-R8).

---

## Namespace grammar

Every `registry_id` follows a strict prefix:

| Prefix | Example | Meaning |
|---|---|---|
| `entity:` | `entity:US:NVDA` | Public market entity (market:ticker). |
| `thesis:` | `thesis:ai_infra` | Human-readable thesis family. |
| `mechanism:` | `mechanism:A15_WASHOUT_OPP_OUT_2NODE` | Mechanism-level research idea. |
| `species:` | `species:S1@1.0` | Species registry row plus version. |
| `rf:` | `rf:rf-20260706-adopt-a15_washout_opp_out_2node` | Research Factory candidate. |
| `gov:` | `gov:a3f1b2c4d5e6f7a8` | Governance event (16-char hex). |
| `claim:` | `claim:a3f1b2c4d5e6f7a8` | Qledger claim (16-char hex). Reserved. |

Rule: local system IDs are never renamed. The registry maps them.

---

## Row types

| `registry_type` | Meaning |
|---|---|
| `entity` | A public market entity with ticker/alias provenance. |
| `thesis` | A named thesis family; may link multiple entities and mechanisms. |
| `mechanism` | An ID-bearing research mechanism (spec_ref or candidate_id provenance). |
| `species_link` | A link to a species registry row; carries lifecycle context (field values copied as-is from the source). |
| `claim_cluster` | **Reserved — never emitted in v1.** Cluster of qledger claims (v1.1 candidate). |

---

## Fable rulings (ETM-R1..R8)

**ETM-R1** — Crosswalk only; display_only role enforced. Local IDs are preserved
and never renamed. The registry has no authority to gate, rank, score, or
promote candidates.

**ETM-R2** — `registry_type` is an enum: `entity`, `thesis`, `mechanism`,
`species_link`, `claim_cluster`. `claim_cluster` is reserved for v1.1 and never
emitted by the v1 builder.

**ETM-R3** — Human-curated `thesis` rows are legal, but only with both
`source_refs` (at least one real path) and `curated_by` populated. Rows missing
either are skipped and a conflict is recorded. Source: `config/entity_thesis_mechanism_registry.yml`.

**ETM-R4** — Mechanism identity requires an explicit shared key:
`spec_ref`, `candidate_id`, `species_id`, trial family, or a curated alias that
cites a PR or ruling. Token-overlap output (`possible_duplicates`) is
suggestion-only and never merges two mechanisms automatically.

**ETM-R5** — No private Mastermind `thesis_id` values in the public JSON output.

**ETM-R6** — `engine/entity_resolver.py` wins all entity-identity disputes.
Disagreements are printed to the `conflicts` field and never silently resolved.

**ETM-R7** — Output is deterministic; `generated_utc` is the only
nondeterministic field.

**ETM-R8** — No `site/` copy in v1. The artifact is `data/` only.

---

## Non-goals

The following are explicitly out of scope for v1:

- No embeddings or fuzzy-vector identity.
- No new score of any kind.
- No ranking.
- No position sizing.
- No lobe charter.
- No new thesis authority.
- No qledger semantic changes.
- No replacement of Signal Bus (`docs/SIGNAL_BUS.md`).
- No forced universal primary key across all systems.
- No invented links when source IDs are absent.

---

## Query usage

The builder has a `--query` mode for interactive lookup:

```bash
python -m scripts.build_entity_thesis_mechanism_registry --query "washout opp out"
```

This tokenizes the query, scores rows by token overlap against `registry_id`,
`mechanism_id`, `spec_ref`, and `notes`, and prints ranked matches with full
provenance.

**V1 success test (from handoff):**

A proposal says:
> Test washout-outside-opportunity as a new Oracle reversion compound and
> entry-stack setup.

The registry responds:

```text
Mechanism match: A15_WASHOUT_OPP_OUT_2NODE.
Prior RF status: paper.
Related PR: #1629.
Related trial family: existing Oracle/RF source.
Allowed next step: inspect paper clock or scoped follow-up.
Forbidden: treat as net-new family without citing prior mechanism.
```

---

## CI guard

`scripts/check_entity_thesis_registry.py` exits 1 on any violation.

| Code | Check |
|---|---|
| ETM-C1 | Schema field present and equals `neuralweb.entity_thesis_mechanism.v1`. |
| ETM-C2 | Top-level `authority` block matches the canonical `AUTHORITY_BLOCK` constant; `is_context_only` is `true`; every row `authority` is `"display_only"`; no row contains any of the forbidden authority-bearing keys `can_gate`, `can_rank`, `can_size`, `score`, `rank`, `weight`. Note: `size` is not forbidden — thesis rows legitimately carry group member-count `size` from the reflexivity source. |
| ETM-C3 | Namespace grammar: every row's `registry_id` matches the pattern for its `registry_type`; `registry_type` is a known value; the reserved type `claim_cluster` is never emitted. |
| ETM-C4 | Edge provenance: every edge has `source.path` and `source.detail` populated; every edge endpoint is resolvable (present in `rows`, in `trial_families`, or matches the `gov:` / `rf:` namespace pattern or experiment-ref prefix). |
| ETM-C5 | Suggestion-only law: every `possible_duplicates` entry must have `basis == "token_overlap_suggestion_only"`, must carry `suggestion_only: true`, and must not contain any of the forbidden merge-directive keys `auto_merge`, `merge`, `canonical`, `resolved`. |
| ETM-C6 | Counts consistency: `counts.rows_by_type` and `counts.edges_by_kind` must equal the values recomputed from the live `rows` and `edges` arrays. |
| ETM-C7 | Referential integrity (only for source files present on disk): species_link `species_id@version` must exist in `data/species/registry.json`; mechanism `candidate_ids` must exist in `data/research_factory/candidates.jsonl`; `gov:<event_id>` edge targets must resolve in `data/neuralweb/governance.jsonl`. |

**Follow-up candidates (not yet enforced):** edge `source.path` file-existence
resolution on disk; experiment-ref (`species-<id>`) existence in
`data/experiments/registry_seed.json`; governance `target` word-boundary matching.

---

## Curated config

Human-curated thesis rows live in `config/entity_thesis_mechanism_registry.yml`.
Rows missing `source_refs` or `curated_by` are skipped with a conflict note
(ETM-R3). This file is the only place curated thesis rows may be introduced; the
builder does not accept inline thesis labels.

---

## Further reading

- `research/fable_exit/05_ENTITY_THESIS_MECHANISM_REGISTRY_HANDOFF.md` — full
  specification, sample rows, and freeze decisions (vendored copy).
- `engine/neuralweb/entity_thesis_mechanism_registry.py` — module docstring
  contains the full ruling set ETM-R1..R8 and namespace pattern constants.
- `config/entity_thesis_mechanism_registry.yml` — curated thesis and mechanism rows.
- `docs/SIGNAL_BUS.md` — artifact topology (separate concern from conceptual
  lineage).

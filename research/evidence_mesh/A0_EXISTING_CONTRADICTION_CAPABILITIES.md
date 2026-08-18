# A0 — Existing contradiction capabilities

**Commission:** MASTERMIND GROK-A0  
**Question 5:** which existing contradiction system can be reused?

**Verdict:** reuse **several**, each inside its grain. Do **not** build a general Evidence Mesh contradiction store. None of the existing systems share a `contradiction_id`, a subject identity, or a PIT replay of pair state.

---

## 1. Inventory (what already fires)

| System | File / contract | Grain | What “contradiction” means | Persist? | Authority | Reuse as Mesh? |
|---|---|---|---|---|---|---|
| Theme Graph evidence coexistence | `contracts/theme_graph/evidence.v1` + edges README | Two receipts about one edge | Contradictory **and** corroborating rows coexist; nothing nets; consumer must say which receipt it trusts | Yes (append-only parquet) | display; all authority booleans false | **Reuse the law**, not the parquet, for any Mesh fact that is a dated receipt |
| FIF revision lineage | packet `revisions[]` + raw `revision_of` | Two occurrences of one logical metric/period | Typed restatement / amendment / withdrawn — not a “who is right” score | Yes (immutable occurrences) | context_only | **Reuse for filing facts** |
| Earnings correction | `company_event` state `corrected`; `correction_status`; new generation | Same `event_id` | New document/generation; identity stable | Yes | context_only | **Reuse for event identity** |
| GovRev issuance corrections + suppressions | two v1 config manifests | Exact issued row / source identity | Reviewed quarantine or do-not-backfill | Yes (config + ledger stays) | reviewed policy | **Reuse for “we issued a false row”** |
| GovRev source revisions | `action_revised` / `action_corrected` / `action_retracted` | Same native action, new event | Official restatement; A→B→A = 3 events | Yes | context | **Reuse for award revisions** |
| GovRev workspace same-id conflict | workspace projector | Same `event_id`, different payload | **Drop**, not last-write-wins | Projection | display | Pattern only |
| BioCatalyst change-tape lineage | `correction_lineage`; `correction_assessed=false` | Earlier recorded value | Which tape row supersedes which; **assess_correction forbidden** | Yes | source_fact / display | **Reuse for registry diffs**; do not add a materiality judge |
| BioCatalyst operational `revision_of` | operational_store | Corrigible kinds | New record; predecessor stays | Yes (prod root off-repo) | operational | Pattern |
| QLedger falsifier loop | `engine/qledger_falsifier.py` | One `claim_id` after `check_by` | `FALSIFIER_TRIPPED` / `CONFIRMED` / `UNVERIFIABLE` | Yes, parallel jsonl | display / TIL honesty; not a signal | **Reuse for forward claims only** |
| QLedger metric-validity | `engine/qledger_validity.py` | `claim_family` | Reader-side illegal aggregates (pooled signed excess, off-horizon verdicts) | CI / report | reporting, not accrual | Eval law, not Mesh facts |
| Eval OS T1 findings | intelligence registry | `engine_id` | `AUTHORITY_WITHOUT_EVIDENCE`, class missing | in-memory | reports, mutates none | Engine hygiene |
| Eval OS T4 plane precedence | output_health | `(engine_id, artifact_id)` | Reader vs producer vs self-health | on-demand | reports | Health, not truth |
| NW W4 pair detector | `engine/neuralweb/contradictions.py` | Typed bus pair (9 pairs a–i) | Label/direction opposition; flip-aware label-lag | No ledger (recompute) | `display_only`; severity `note`/`tension`; **no winner** (TOP3-M2) | **Reuse as display annotator of Mesh-joined signal artifacts**. Not a fact contradiction store |
| Factor contradictions | `factor_contradictions.py` | `(date, ticker)` | borrowed_strength | Intended jsonl; **ABSENT** this checkout | display; `note` only | Per-name display sibling |
| Options contradictions tool | cortex `_tool_list_options_contradictions` | ephemeral | buy-lane vs options state | No | de-escalate only | Tool, not store |
| Chat contradiction corpus | `ops/MASTERMIND_RESPONSE_LOG_RUNBOOK.md` | assistant reply | system_error / market_divergence / unclear | response-eval | de-escalate; MNZ-R5 no winner | **Not market evidence** |
| Board contradictions | `scripts/check_board_contradictions.py` | rendered standouts row | FRESH vs stale, sort order, reflexivity n_eff | CI fail | publish gate | **UI invariant**, not a thesis |
| Signal-gate pair coherence | house law | two copies of one board reading | must match | CI | display-coherence | Sibling of board guard |
| Evidence Clock precedence | EC-R3 | competing clocks on one subject | demote attention, do not resolve truth | snapshot | display_only | **Reuse for review routing**, not facts |
| TXI structured falsifiers | `engine/transmission_chains.py` | one chain episode | `failed` / `expired` / `arm_veto` | episodes jsonl | display_only; instrument verdict | **Reuse for chain windows**; never as market refutation (front-facing ban #3821) |
| TIL thesis tripwires | theme_thesis ledger | thesis_id | ARMED / FIRED / DATA_MISSING | jsonl | shadow | Theme theses, not Mesh facts |
| Recipient graph conflicts | GovRev graph | UEI/issuer path | `overrides` / `conflicts` / `blocks` | graph JSON | reviewed | Identity conflicts, typed |
| China market_state `contradictions_count` | CN-SYS | compose | separate sibling | snapshot | display | Do not join to W4 |
| `dt_contra_state` | DannyTrades | chip | name collision; states permanently `neutral` after H4 fail | snapshot | n/a | Ignore |

---

## 2. What can be reused, by Mesh job

| Mesh job | Reuse this | Do not reuse this |
|---|---|---|
| Two dated receipts disagree about one edge/fact | Theme Graph coexistence law | NW W4 (wrong grain); qledger falsifier (predictions) |
| A filing restated a number | FIF `revision_of` + packet hops | Board contradictions |
| An earnings print was amended | Earnings `corrected` + new generation | Chronicle replace-by-id as a general pattern (degraded-cannot-clobber is local) |
| An award action was revised | GovRev new event_id + action_corrected | Last-write-wins |
| We published a false candidate | Issuance corrections + suppressions | Deleting ledger lines |
| A trial registry field changed | BioCatalyst change fact + tape lineage | Materiality / protocol-change assertion (explicitly false on the fact) |
| A forward claim failed | QLedger falsifier | NW W4 |
| Two **signals** on the bus disagree | NW W4 display annotator | Promoting the record past display (China falsification precedent) |
| Two clocks compete for operator attention | Evidence Clock EC-R3 | Treating demotion as a truth verdict |
| A rendered board is internally incoherent | Board contradiction CI | Market-thesis language |
| A chain’s declared window failed | TXI falsifier / failed / expired | Front-facing “thesis refuted” |
| The assistant contradicted a calibrated tool | Chat corpus | Any market join |

---

## 3. Hard laws already on contradiction surfaces

- NW W4: display-only; fail-open; severity ∈ {`note`, `tension`}; `critical` reserved for alerts and **forbidden** here. No winner field.
- Theme Graph: consumer names the trusted receipt; the store will not choose.
- BioCatalyst change fact: `protocol_change_asserted=false`, `materiality_assessed=false`.
- BioCatalyst tape: `assess_correction` forbidden.
- QLedger falsifier: context-only, not a signal; independent of `grades.hit`.
- TXI: `failed` is user-facing “Halted”; full verdict vocabulary lives on Calibration Lab, not the chain card.
- Chat: model may only de-escalate; calibrated tools are source of truth.
- Evidence clock: cannot promote, retire, or mutate any source system.

A Mesh contradiction object that picks a winner, raises Article-2, or writes “refuted” on a user surface would violate more than one of these at once.

---

## 4. Gaps (why a new general store is the wrong fill)

1. No shared `contradiction_id` across systems (CODE VERIFIED: each module defines its own record locally).
2. NW W4 has **no** evidence IDs, no `known_at`, no ledger, no PIT. Pairs are re-detected each nightly.
3. Factor jsonl is absent on this checkout — even the one append-only NW ledger is not live here.
4. Synapse/masterplan pair-count docs are stale (6 or 7 vs 9 pairs in code).
5. QLedger falsifier coverage is historically thin (accountability 1.6% at last regen; evidence-clock still treats global coverage as blocked).
6. Chat, board, CN, and DT “contra” names are siblings, not a family.

Filling those gaps with a universal contradiction graph would **duplicate** Theme Graph coexistence, FIF lineage, GovRev revisions, and BioCatalyst facts under a new owner. That is the thing this commission forbids.

---

## 5. Recommended Mesh stance

The Mesh **joins** native objects. If two joined refs disagree:

1. If they are receipts → apply Theme Graph coexistence (both stay; consumer declares trust).
2. If they are revisions of one identity → apply the owner’s lineage (`revision_of`, `corrected`, `action_corrected`, `generation_id`).
3. If they are signals → optionally **display** a W4-style `note`/`tension` with `display_only=true` and no winner.
4. If they are forward claims → qledger falsifier only.
5. If they are operator clocks → evidence clock precedence only.

No fifth engine.

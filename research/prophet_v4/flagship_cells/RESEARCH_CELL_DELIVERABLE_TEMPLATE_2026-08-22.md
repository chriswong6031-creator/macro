# Prophet Flagship Research Cell — Standard Deliverable / Return Template

**Purpose:** required output shape for MAS-117..MAS-124 research cells.  
**Read with:** `RESEARCH_CELL_EXECUTION_CONSTITUTION_2026-08-22.md`, `PROPHET_FLAGSHIP_CELL_HARDENING_INDEX_2026-08-22.md`, and the cell-specific dedicated handoff.  
**Authority:** template only. It creates no implementation authority.

A fresh Sol may add domain-specific sections, but it should not omit a required section without an explicit `NOT_APPLICABLE — <reason>` ruling.

---

# 0. Research return metadata

```text
Cell:
Linear issue:
Session owner/model:
Claim comment ID/link:
Started at:
Completed at:
Skillpack repo/SHA/version:
Macro main SHA at claim:
Macro main SHA at closeout:
Canonical owner workstream(s):
Open/recent owner PRs inspected:
Research artifact path:
Agent OS handoff path:
Mutation authority held: RESEARCH ONLY | <explicit separate authority if any>
```

## 0.1 Claim-time disagreement ledger

| Topic | Dated handoff said | Current canonical owner/main says | Ruling used | Material to mission? |
|---|---|---|---|---|

A blank table requires the sentence: `No material disagreement found after current-main reconciliation.`

---

# 1. Executive thesis

Maximum roughly one page.

Answer:

- What should Mastermind build or learn?
- Why does it matter to the flagship Prophet thesis?
- What did archaeology materially change from the incoming handoff?
- What is the single strongest recommendation?
- What should **not** be built?
- What is blocked on data/estimability/rights/owner sequencing?

Do not write a component inventory here.

---

# 2. Chairman intent reconstruction

## 2.1 User job

> The Chairman/researcher should be able to...

## 2.2 Machine/intelligence job

> Mastermind should be able to infer/structure...

## 2.3 Moat

> Over time the system uniquely accumulates...

## 2.4 10/10 end-state

Write one concrete end-to-end example with real-data-style values/states.

## 2.5 Intent invariants

List 5–15 statements that must remain true even if implementation method changes.

Example form:

- `Strong thesis + closed entry must remain a coherent valid state.`
- `Missing options coverage must not become low crowding.`

## 2.6 Explicit anti-goals

State what this cell must never become.

---

# 3. Current capability ledger

Use only these states:

`PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, `BROKEN`, `SPEC_ONLY`, `NOT_BUILT`, `REJECTED_BY_DESIGN`.

| Capability | State | Canonical owner | Producer/store | Consumer | Production evidence | Gap / why not next state |
|---|---|---|---|---|---|---|

Rules:

- A live collector with no consumer is not `PROVEN_LIVE` end-to-end.
- Fixture proof is not production proof.
- An accepted architecture doc is `SPEC_ONLY` until built.
- If a capability is intentionally forbidden, use `REJECTED_BY_DESIGN` rather than `NOT_BUILT`.

---

# 4. Producer → consumer / system archaeology

Diagram the current real chain:

```text
source
→ acquisition/producer
→ identity/clock normalization
→ canonical store/contract
→ transform/compiler
→ machine API/projection
→ user product
→ outcome/evaluation
```

Then document every broken/dark/ambiguous seam.

| Seam | Current implementation | Health | Clock | Identity | Correction | Rights | Consumer consequence |
|---|---|---|---|---|---|---|---|

---

# 5. Ownership / reuse / supersession matrix

| Needed capability | Existing owner/system | Reuse as-is? | Extend? | Version/supersede? | New owner gap? | Why |
|---|---|---|---|---|---|---|

Allowed rulings:

- `REUSE_AS_IS`
- `EXTEND_OWNER`
- `ADAPTER_ONLY`
- `VERSION_AND_SUPERSEDE`
- `DEFER_TO_OWNER`
- `REJECT_DUPLICATE`
- `GENUINE_OWNER_GAP`

If `GENUINE_OWNER_GAP` is claimed, explain why no current owner can lawfully own it.

---

# 6. External / primary-source / competitor research

For each important external capability:

| Source/product/method | Primary job-to-be-done | Useful workflow/idea | What Mastermind can independently reproduce | Data/rights dependency | What NOT to copy |
|---|---|---|---|---|---|

Prioritize primary sources and technical methodologies.

Separate:

- market/product benchmark;
- methodological evidence;
- data source feasibility;
- community anecdote.

Do not use competitor marketing copy as empirical proof.

---

# 7. Architecture recommendation

## 7.1 Canonical owner topology

State which program owns each part.

## 7.2 New or extended contracts

For each proposed contract:

```text
contract name / candidate version:
owner:
subject grain:
identity:
producer:
consumer(s):
fields / semantic questions:
source evidence references:
authority at birth:
rights tier:
versioning rule:
```

## 7.3 No-rebuild boundaries

Name the specific existing systems that must not be duplicated.

## 7.4 Dependencies

Separate:

- hard implementation prerequisite;
- research dependency;
- optional future enhancement;
- current active-owner collision.

---

# 8. Identity / time / null / correction contract

## 8.1 Identity

```text
primary subject:
canonical identity owner:
company vs security grain:
epoch/ticker-reuse behavior:
multiple share-class behavior:
event/theme/relationship identity where applicable:
```

## 8.2 Clocks

Fill every applicable clock:

| Clock | Meaning | Source | Required? | Historical replay rule |
|---|---|---|---|---|
| economic/source event | | | | |
| source available / known-at | | | | |
| captured-at | | | | |
| computed/belief time | | | | |
| corrected/superseded time | | | | |
| first tradable time/session | | | | |
| evaluation start | | | | |

## 8.3 Null / missingness states

At minimum adjudicate:

| State | Meaning | Can become numeric zero? | User-facing wording | Model treatment |
|---|---|---|---|---|
| NOT_APPLICABLE | | | | |
| NOT_COVERED | | | | |
| SOURCE_UNAVAILABLE | | | | |
| STALE | | | | |
| RIGHTS_BLOCKED | | | | |
| IDENTITY_UNRESOLVED | | | | |
| INSUFFICIENT_HISTORY | | | | |
| UNESTIMABLE | | | | |
| ACCRUING | | | | |
| MEASURED_NEUTRAL/ZERO | | | | |

## 8.4 Corrections

Describe:

- append new belief vs overwrite;
- supersession/annulment/retirement;
- how PIT replay preserves the old known state;
- what downstream vector/UI changes after correction.

---

# 9. Method taxonomy

Every proposed output belongs in exactly one primary method class.

| Output | Deterministic | Statistical | Model-generated | Sample/coverage | Authority at birth | Why this method |
|---|---|---|---|---|---|---|

For statistical methods state:

- target/estimand;
- N/effective N;
- clustering/dependence;
- baseline/control;
- validation split;
- confidence/uncertainty representation.

For model-generated methods state:

- source evidence/span requirements;
- model/version identity;
- deterministic validation/admission;
- unsupported/refusal behavior.

---

# 10. Buildability and estimability ledger

| Proposed capability | Data exists? | Rights usable? | PIT adequate? | Coverage | N/effective N | Technically buildable now? | Scientifically estimable now? | Useful context now? | Ruling |
|---|---|---|---|---|---|---|---|---|---|

Allowed rulings:

- `BUILDABLE_NOW`
- `RESEARCH_NOW_BUILD_AFTER_<dependency>`
- `CONTEXT_ONLY`
- `ACCRUE`
- `UNESTIMABLE`
- `REJECT_DUPLICATE`
- `REJECT_LEAKAGE`
- `REJECT_NO_INCREMENTAL_VALUE`
- `DEFER`

Do not use “AI can estimate it” to turn an unestimable construct into `BUILDABLE_NOW`.

---

# 11. Experience architecture

Produce at least the cell-specific minimum number of reference compositions from the dedicated handoff.

For each:

```text
State name:
Real-data-style facts:
What the machine knows:
What is missing:
What the user sees in 5 seconds:
What is in drill-down:
What is explicitly NOT claimed:
What actionability says:
Receipts/counterevidence:
```

Mandatory universal compositions if applicable:

1. strong positive/useful state;
2. contradictory/counterexample state;
3. missing/degraded/unestimable state;
4. strong thesis + unavailable entry state.

---

# 12. Failure-state matrix

| Failure/degraded state | How detected | Machine behavior | User behavior/copy | Can downstream rank consume? | Recovery/correction path |
|---|---|---|---|---|---|

Cover at least:

- wrong identity/ticker reuse;
- stale source;
- source correction;
- missing coverage;
- rights block;
- dependent/duplicate evidence;
- conflicting evidence;
- insufficient N;
- model unsupported output;
- producer updated/consumer stale;
- current snapshot accidentally used historically;
- sister-session/owner collision;
- strong intelligence but closed/chased entry.

---

# 13. Falsification and evaluation plan

## 13.1 Primary hypothesis / capability claim

Write a statement that can be false.

## 13.2 Boring baseline

What simple baseline must the proposal beat?

## 13.3 Negative controls / placebos

List exact controls.

## 13.4 Leakage tests

List exact temporal/identity/outcome leak tests.

## 13.5 Coverage / estimability gates

State minimum acceptable N/coverage or explicit abstention rule.

## 13.6 Primary metrics

Freeze before confirmatory read.

## 13.7 Secondary diagnostics

Keep separate from primary claim.

## 13.8 Forward promotion plan

Map to current Eval OS / Conditional Fusion law.

## 13.9 Kill conditions

List what evidence causes `REJECT`, not merely “iterate.”

---

# 14. Cross-cell interface check

Complete every row.

| Sibling cell | What I consume from it | What I provide to it | What I explicitly do NOT own |
|---|---|---|---|
| A Theme | | | |
| B Incorporation | | | |
| C Catalyst | | | |
| D Species/Analogues | | | |
| E Fragility/Crowding | | | |
| F Translation | | | |
| G Eval/VOI | | | |
| H Experience | | | |

Then answer:

- Did I accidentally duplicate a sibling's semantic owner?
- Did I invent a fact because a downstream cell wants it?
- Did I make a downstream result a required upstream input, creating circularity?

---

# 15. Future bounded implementation waves

At most 3–5.

For each wave use this exact mini-handoff:

## Wave `<CELL>-W# — <name>`

**Observable mission:**  
**Why it matters:**  
**Canonical owner:**  
**Prerequisites:**  
**Pickup/current SHA:** to be re-resolved at commission time  
**Exact repo/scope/paths:**  
**Explicit non-goals:**  
**User/machine journey:**  
**Data/contract/identity:**  
**Clocks:**  
**Null/correction behavior:**  
**Method:** deterministic | statistical | model-generated | mixed with exact boundary  
**Failure/degraded states:**  
**Ordered implementation sequence:**  
**Acceptance tests:**  
**Real production/browser/machine proof owed:**  
**Stop condition:**  
**Continuation handoff required:**  

The research deliverable does not authorize these waves.

---

# 16. Sequencing / dependency recommendation

Provide a table:

| Wave/capability | Can research now? | Can implement now? | Blocking owner/gate | Can run parallel with | Must not overlap with |
|---|---|---|---|---|---|

Explicitly distinguish:

- “research complete”;
- “implementation-ready architecture”;
- “implementation authorized”;
- “built”;
- “production proven”;
- “accepted/promoted.”

---

# 17. CEO decision docket

Only include decisions that truly require Sol/Chairman authority.

For each:

```text
Decision:
Why operator cannot decide:
Option A:
Option B:
Recommended ruling:
What becomes possible after ruling:
What remains forbidden:
```

An empty docket is valid and preferable to manufactured CEO gates.

---

# 18. Explicit non-goals / do-not-redo

Copy forward the dedicated handoff's do-not-redo laws and add any new ones discovered during archaeology.

For each important rejection, record **why** so a future session does not reopen it from scratch.

---

# 19. Misconstruction self-test

Answer YES/NO with one-line evidence.

| Test | YES/NO | Evidence |
|---|---|---|
| Created/designed a second canonical store? | | |
| Created/designed a second ranker/evaluator/graph? | | |
| Treated missing as neutral/zero? | | |
| Used today's state as historical PIT truth? | | |
| Leaked future correction/outcome? | | |
| Treated model judgment as deterministic fact? | | |
| Claimed causality from correlation? | | |
| Counted dependent observations as independent confluence? | | |
| Let intelligence bypass deterministic availability? | | |
| Improved precision by becoming too late without disclosure? | | |
| Called a PR/CI/spec “live” without production proof? | | |
| Broadened into an active sibling workstream? | | |

Any YES requires correction or an explicit CEO return point before closeout.

---

# 20. Final ruling

Choose exactly one primary disposition for the **cell research mission**:

- `ARCHITECTURE_ACCEPTED — OWNER-ROUTED WAVES PROPOSED`
- `PARTIAL — MORE RESEARCH REQUIRED`
- `DEFERRED — DEPENDENCY/ESTIMABILITY`
- `SUPERSEDED BY EXISTING CANONICAL PROGRAM`
- `REJECTED BY DESIGN`

Then state what the ruling does **not** authorize.

---

# 21. Continuation handoff

End with a cold-stranger recovery block:

```text
Current main SHA:
Research branch/PR:
Linear issue state:
Artifacts added/changed:
Most important discoveries:
Accepted/rejected hypotheses:
Current owner collisions:
Unverified claims:
Outstanding production/evaluation proofs:
Exact next Sol action:
Exact next owner action if Sol approves:
Do-not-redo:
Danger areas:
```

Also update the correct Agent OS workstream/decision/discovery/handoff records according to current ownership law. Do not create another lifecycle store.

---

# 22. Closeout sentence

Finish the research artifact with this meaning, adapted to the cell:

> **This research defines what should be built and how it can lose. It does not claim the capability is built, production-proven, predictive, promoted or actionable until those separate gates are actually satisfied.**

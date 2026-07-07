# Fable Succession Operating System

**Status: OPERATING LAW**
Ratified: 2026-07-06 by Fable (main loop) with operator amendment.
Supersedes: [research/fable_exit/03_FABLE_SUCCESSION_BENCH_AND_ADJUDICATION_PACK_HANDOFF.md](fable_exit/03_FABLE_SUCCESSION_BENCH_AND_ADJUDICATION_PACK_HANDOFF.md) (archived, same day).
Where that doc and this doc conflict, this doc wins.

---

## In Plain English

**When Fable isn't available, who decides what?**

Opus and the operator run the shop. For ordinary decisions — sending a candidate to paper, deferring a study, rejecting a duplicate — Opus or the operator can decide, using an adjudication packet as the evidence record. A short list of consequential decisions (new lobe charters, authority promotions, scored-path changes) still require a completed packet plus an adversarial panel of at least two independent Opus reviewers plus explicit operator sign-off; they are harder, not impossible. Three things — LLM-originated signals/scores/gates, trial-budget laundering, and deletion of negative history — are definitional violations that no one may approve, ever, for any reason. Nothing waits forever for a model that isn't coming back.

---

## (C) The Operator Amendment

The Codex handoff proposed two things Fable overruled:

1. **Codex proposed**: Opus may only recommend, never decide.
   **Operator ruling**: "Opus has proven strong enough in many cases; we will still have Opus when Fable is not available; the bench must not slow everything down." Fable ratified. Opus is a full decision authority at Tier 0 and Tier 1.

2. **Codex proposed**: A fixed nondelegable list that blocks those decisions indefinitely without a "frozen successor rule."
   **Operator ruling**: Nothing is parked forever. Those consequential decisions become Tier 2 — harder (adversarial panel + operator sign-off), not impossible. Three narrow invariants are genuinely never-approvable, but that is a different category from "needs Fable and Fable is gone."

Fable ratified both amendments. They are encoded in RUL-SUCC-2, RUL-SUCC-3, and RUL-SUCC-4 below.

---

## (D) The Frozen Ruling Set

### RUL-SUCC-1 — Bench Chartered

Review competence, decision authority, and implementation ownership are separate powers. Finding a defect, deciding an outcome, and building a spec are three different things. Opus may find a statistics defect. Sonnet may implement a frozen spec. The operator may decide a scoped outcome. None of those powers automatically authorizes a new lobe, FDR family, public/private boundary change, or scored-path behavior change.

*Ratified from Codex unchanged.*

---

### RUL-SUCC-2 — Tier Ladder

A three-tier decision ladder replaces the binary delegable/nondelegable split. The tiers are defined in section (E) below. Nothing is parked forever: at Tier 2, operator + adversarial panel fully replaces Fable. The old concept of "block until a frozen successor rule exists" is retired.

*[AMENDS Codex]*

---

### RUL-SUCC-3 — Opus Authority

Opus is a decision authority at Tier 0 and Tier 1, not merely advisory. An Opus decision at these tiers is a valid transition; the packet is the audit artifact. Opus review findings remain advisory only where the packet itself classifies the decision as Tier 2, meaning the decision is above the tier where Opus acts alone.

*[AMENDS Codex "Opus Can Recommend"]*

---

### RUL-SUCC-4 — Invariants (Never-Approvable)

Three classes are never approvable by this bench, by any actor, by any process:

1. **Article-1 amendment / A7 origination** — no LLM-originated signal, score, rank, or gate on a scored path, ever. `AuthorityLevel.A7_ORIGINATE` is permanently refused by `constitution.grant()` unconditionally. This is not a governance decision; it is a definitional property of the system.
2. **Trial-budget laundering** — no packet may approve additional trials retroactively, split a family to hide aggregate budget, or reframe a rejected family as a new one to restart the budget clock.
3. **Deletion of negative or null history** — no packet may authorize removing kill evidence, null results, or deferred records from any ledger, registry, or research doc.

These are not decisions. They are violations. Refuse with citation to this ruling.

---

### RUL-SUCC-5 — Speed Law

Tier 0 is the default and adds zero new process — the record is the ordinary PR / research-doc trail. Packets at Tier 1 and Tier 2 are auto-built by `scripts/build_adjudication_packet.py`, not hand-assembled by the adjudicator. A packet undecided for 14 days auto-flags for operator escalation (the `escalation.stale_after_days` field). The bench lives entirely off the render path; nothing here touches nightly or `daily.yml`.

---

### RUL-SUCC-6 — Packet Schema

`neuralweb.adjudication_packet.v1` is ratified with amendments to the Codex draft:

- Top-level `tier` field (values: `0`, `1`, `2`).
- `decision` block replaces `operator_decision`: fields are `{outcome, decided_by: opus|operator, actor_ref, rationale, decided_on}`.
- `review.panel[]` entries have shape `{reviewer_ref, stance: refute, verdict: refuted|stands, rationale}`.
- `escalation` block: `{opened_on, stale_after_days: 14, escalated: bool}`.

Packet completeness is enforced per tier by `scripts/check_adjudication_packet.py` against `config/adjudication_rubrics.yml`. Incomplete packets are hard blocks.

---

### RUL-SUCC-7 — RF Actor Law Amendment

`engine/research_factory/state.py` gains a `MODEL_ADJUDICATORS` actor class containing `{"opus"}`. Model adjudicators may enter the human-gate target states (`paper`, `deferred`, `rejected`, `scoped_build`, `retired` — as defined in `_HUMAN_GATE_TARGETS`) ONLY when the transition row carries both `actor_ref` and `packet_ref` (a resolved adjudication packet id). Script actors (`SCRIPT_ACTORS = frozenset({"script", "codex", "sonnet"})`) remain barred unconditionally from human-gate states — that law does not change.

Rationale: the operator gates on human judgment. A model adjudicator at Tier 0/1 is a legitimate human-gate actor when it leaves a machine-checkable audit artifact. Missing `packet_ref` → transition refused, same as missing `actor_ref` for a human.

---

### RUL-SUCC-8 — Golden Case Law

The ten golden examples in section (H) are canonical case law. `research/adjudication_examples/` is normative; future adjudicators cite examples by file when pattern-matching decisions. The examples are training data for the bench, not constraints on outcomes.

---

### RUL-SUCC-9 — Ruling Index

A machine-readable ruling index at `data/neuralweb/ruling_index.json`, built by `scripts/build_ruling_index.py` sweeping `research/` for ruling IDs (pattern: `RUL-[A-Z]+-[0-9]+`), is chartered. Packet `case_law.ruling_hits` cite from this index. The index is descriptive tooling — it never overrides source doc text. If the index and a source doc disagree, the source doc wins.

---

### RUL-SUCC-10 — Authority Evidence Floor

Any packet touching authority must carry all of the following or it is incomplete (hard block):

- Constitution article citation (Article 1, 2, or 3 from `engine/neuralweb/constitution.py`'s `ARTICLES` dict).
- Current `AuthorityLevel` ceiling and requested ceiling (e.g., `A1_EXPLAIN` → `A2_ATTEND`).
- The actual Article-3 numbers: `n`, `n_events`, Wilson lower-bound lift vs 1.25 threshold, and `evidence_asof` staleness check — sourced from the grant path, not estimated.
- A case-law scan confirming no prior kill or block on this authority path.

Missing any of these → incomplete packet, hard block, return for evidence.

---

### RUL-SUCC-11 — Privacy Evidence Floor

Any packet touching privacy must carry all of the following or it is incomplete (hard block):

- `privacy_class` (one of: `public_research`, `public_context`, `host_private`, `mastermind_private`).
- Enumerated public paths touched.
- Field-level enumeration of new or changed fields (not path-level only).
- Proof that the five Mastermind context authority booleans in `engine/neuralweb/mastermind_context.py` are unchanged (or a Tier-2 packet explicitly covering the change).

---

### RUL-SUCC-12 — W0 Scope

This wave ships: this doc + `config/adjudication_rubrics.yml` + `scripts/build_adjudication_packet.py` + `scripts/check_adjudication_packet.py` + `research/adjudication_examples/` seed files + `data/neuralweb/adjudication_queue.json` stub + the RF actor amendment to `engine/research_factory/state.py`. No `ci.yml` change in W0 (dag-conformance drift risk). CI wiring is queued W1. Local `pytest` is the gate for the new tests until then.

---

## (E) The Tier Ladder

| Tier | Name | Decider | Record | Trigger Classes |
|---|---|---|---|---|
| **0** | ROUTINE | Opus alone OR operator alone | Ordinary PR / research-doc trail; RF transitions additionally need minimal packet with `packet_ref` when actor is `opus` (RUL-SUCC-7) | RF paper/defer/reject with clean case-law scan; doc-only merges; display-only changes; taxonomy calls with clear precedent; "send to review"; "return for missing evidence" |
| **1** | CONSEQUENTIAL | Opus OR operator, WITH completed packet passing `check_adjudication_packet.py`; packet logged in `data/neuralweb/adjudication_queue.json` | Packet file + queue entry | `scoped_build`; retire; new FDR family within an existing program; come-back-clock moves >90 days; taxonomy calls without precedent; cross-program ownership calls; ops-budget additions that stay inside render budget |
| **2** | CONSTITUTIONAL | Full packet + adversarial panel of >=2 independent Opus reviewers instructed to REFUTE + explicit operator sign-off recorded in packet | Full packet + panel verdicts + operator sign-off timestamp | New lobe charter; exception to two-lobe cap; authority promotion above A2; ANY scored-path behavior change; FDR family creation/split crossing programs; qledger grading semantics; held-book/fill schema; public/private boundary changes; public write endpoint; Mastermind trading authority; cortex budget increase; Article 2/3 amendments |
| **INV** | INVARIANTS | No actor, no process | N/A — refuse with RUL-SUCC-4 citation | A7 origination / Article-1 amendment; trial-budget laundering; deletion of negative/null history |

---

## (F) Answers to the Nine Codex Freeze Questions

**Q1. Is operator allowed to replace Fable for ordinary paper/defer/reject/scoped_build decisions?**
Yes, unconditionally. Operator has always had this authority in `HUMAN_ACTORS`. The bench adds a packet requirement at Tier 1 to protect the operator from hidden implications, but the authority itself is not new.

**Q2. Which decision classes are nondelegable?**
None are permanently blocked. The old nondelegable list is now Tier 2 — harder (adversarial panel + operator sign-off), not impossible. The three invariants in RUL-SUCC-4 are never-approvable, but that is a different concept from nondelegable: they are definitional violations.

**Q3. Can Opus ever author final decisions, or only findings?**
Opus is a full decision authority at Tier 0 and Tier 1 (RUL-SUCC-3). At Tier 2, Opus reviewers participate as the adversarial panel, but the final sign-off is operator. Opus findings remain advisory only when the packet classifies the decision above Opus's tier.

**Q4. What fields make an adjudication packet complete?**
Completeness is tier-dependent and enforced by `scripts/check_adjudication_packet.py` against `config/adjudication_rubrics.yml`. Minimum for all tiers: `schema`, `packet_id`, `tier`, `request.*`, `scope.*`, `case_law.*`, `decision.*`. Tier 1 machine-enforcement = required fields present + case-law scan performed (HB-7); declaring review lenses and logging Opus findings is recommended practice, enforced only at tier 2 via the panel (HB-2). Tier 2 additionally requires `review.panel[]` with >=2 entries with `stance: refute` (not `approve`) and all verdicts resolved. Omitting `tier` while a known decision_class is present is a hard block (HB-13).

**Q5. What is the minimum evidence for a packet touching authority?**
See RUL-SUCC-10: constitution article citation, current + requested `AuthorityLevel`, actual Article-3 numbers (n, n_events, Wilson lower bound vs 1.25 threshold, staleness), and case-law scan. Missing any → hard block.

**Q6. What is the minimum evidence for a packet touching private data?**
See RUL-SUCC-11: `privacy_class`, enumerated public paths, field-level enumeration of new/changed fields, and proof that the five Mastermind context authority booleans are unchanged. Missing any → hard block.

**Q7. What packet failures are hard blockers?**
Incomplete packets per tier rubric (HB-8); missing `tier` field for a known class (HB-13); authority evidence floor violations (HB-11, RUL-SUCC-10) — now machine-enforced; privacy evidence floor violations (HB-12, RUL-SUCC-11) — now machine-enforced; HB-2 requires panel entries with `stance: refute` (not `approve`); any invariant class (HB-4, RUL-SUCC-4); missing `packet_ref` on a model-adjudicator RF transition (RUL-SUCC-7) — also validated by `scripts/research_factory_decide.py` against the live queue before any disk write; packet stale >14 days without escalation flag (W-1).

**Q8. Which golden examples are canonical?**
All ten in section (H) are canonical, ratified by RUL-SUCC-8.

**Q9. What happens when an item is nondelegable after Fable is gone: park forever, operator override, or external review?**
Operator override with an adversarial panel — never park forever. That is the operator amendment ratified by Fable. The old nondelegable list becomes Tier 2. Nothing waits indefinitely for a model that is not coming back. The three invariants are a different category: they are refused, not parked.

---

## (G) Review Lenses

Every Tier 1 and Tier 2 packet declares which lenses were applied:

| Lens | Questions |
|---|---|
| Case law | Has this been ruled on, killed, deferred, or scoped elsewhere? Cite the ruling ID or example file. |
| Authority | Does it affect Article 2 surfaces, A3/A4/A5/A6, or LLM authority ceilings? Provide the Article-3 numbers. |
| Privacy | Can any field leak held-book, fill, private note, path, key, or account behavior? Enumerate fields. |
| Statistics | Is there a frozen family, declared budget, no lookahead, and a printed null branch? Check trial-budget arithmetic. |
| Build feasibility | Are paths, writers, dependencies, and test surfaces realistic? Does it fit off the render path? |
| Collision | Is an active PR already building this? Check `data/neuralweb/adjudication_queue.json` and open PRs. |
| Ownership | Which program owns it? Is it crossing QI/Mastermind/Oracle/Neural Web program boundaries? |
| Ops budget | Does it add render/nightly time or off-path compute beyond the standing budget? |

---

## (H) Golden Examples (RUL-SUCC-8)

These are the canonical case-law examples. Future adjudicators cite them by file under `research/adjudication_examples/`.

| Example | Why It Matters |
|---|---|
| Research Factory Batch A A15 paper + duplicate kills (#1629) | paper vs rejected decisions and challenger role |
| Three-Lobes zero-charter adjudication (#1673) | attractive lobe ideas decompose into rails/waves/studies |
| Final-3 reshape/kill/defer rulings (#1695) | partial adoption, killed overreach, deferred conditioning |
| R-ORTH rail-not-lobe ruling (#1739/#1748/#1768) | taxonomy discipline |
| Research Factory Cortex Batch B (#1731) | factory infrastructure still needs judgment |
| Factor dark scaffold activation floor (#1598 family) | explicit activation after event floors |
| Mastermind bridge dark-ship/context-only (#1567/#1680) | cross-repo context with no authority |
| Cycle Pattern truth/null status (#1773) | nulls and statuses as active memory |
| L6-P0 macro transmission pass/failed axes (#1693) | pass reopens charter question without auto-chartering |
| Operator exposure / grading (#1702/#1669) | operator-action evidence accrual without promotion |

---

## (I) Operating Procedure for a Future Opus Adjudicator Session

1. **Load this doc** (`research/FABLE_SUCCESSION_OPERATING_SYSTEM.md`) and the `fable-mode` skill at session start. Do not begin adjudicating without them.
2. **Classify the ask** against the tier table in section (E) using `config/adjudication_rubrics.yml` as the decision reference. If in doubt, escalate the tier, not reduce it.
3. **Check for invariants first** (RUL-SUCC-4). If the ask is in any invariant class, refuse immediately with citation. Do not build a packet.
4. **Tier 0**: Decide and record in the PR description or research doc. If the actor is `opus` and the transition is an RF human-gate state, call `scripts/research_factory_decide.py` with `--actor opus --actor-ref <session_ref> --packet-ref <packet_id>`.
5. **Tier 1**: Run `scripts/build_adjudication_packet.py` to generate the packet skeleton. Complete all required fields per `config/adjudication_rubrics.yml`. Apply all relevant lenses. Run `scripts/check_adjudication_packet.py` — it must pass. Record the decision in `decision.*` and append the packet to `data/neuralweb/adjudication_queue.json`.
6. **Tier 2**: Build the packet as in step 5. Spawn >=2 independent Opus reviewer sessions with the explicit instruction: "Your stance is REFUTE. Find every reason this packet should not be approved. Do not play devil's advocate — actually look for disqualifying defects." Record all `review.panel[]` entries with verdicts. Present the full packet to the operator for explicit sign-off. Record `decided_by: operator` and `decided_on` timestamp.
7. **Invariant**: Refuse with citation to RUL-SUCC-4. Do not route to a panel. Do not escalate for operator approval. Record the refusal in the PR/doc.

---

## (J) V1 Success Test

Scenario: a future session says:

```text
Promote cycle-pattern turn hazard into a board rank conditioner.
```

Correct packet outcome:

```text
Tier: 2 (CONSTITUTIONAL — scored-path behavior change, authority promotion above A2)
Required case law: CPI truth schema, cycle-pattern authority guard, constitution A2/A3 articles.
Required Article-3 numbers: n, n_events, Wilson lower bound vs 1.25, evidence_asof.
Allowed outcomes today: defer / Opus stats review / define shadow metric with no board ranking.
Blocked outcome: direct board-rank conditioning.
Panel requirement: >=2 independent Opus reviewers instructed to REFUTE.
```

This scenario is encoded as a test fixture in `tests/test_adjudication_packet.py`.

---

## (K) W1+ Queue

Items queued for after W0 ships:

- **CI wiring**: add `scripts/check_adjudication_packet.py` and `scripts/build_ruling_index.py` to `ci.yml` with dag-conformance care (W1).
- **Backfill — first 10 packets**: held-book/fill reverse bridge; ruling graph v1 seed; active build collision map; global evidence clock; private/public boundary audit; macro context rail #1635; options signed tape #1763; RF LLM-auth hardening follow-up (from #1731); entry-stack decline geometry follow-up (#1777/#1778); post-Fable new-lobe-charter request template.
- **Operator console**: admin tab surface for `data/neuralweb/adjudication_queue.json` (queue view, stale flags, decision log).
- **Periodic ruling-index rebuild**: cron or nightly hook to re-run `scripts/build_ruling_index.py` and commit if changed.

---

## (L) Non-Goals (Verbatim from Codex)

- No autonomous approval outside the tier law.
- No model-confidence-based decisions.
- No LLM changing gates.
- No codegen lane.
- No bypass of Research Factory state law.
- No retroactive replacement of Fable's existing rulings.

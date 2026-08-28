# Macro Context Index — Sol CEO Completion Masterplan

## Provenance and authority

- **Approval:** Chairman approved end-to-end CXI completion on **2026-08-28**.
- **Program operation key:** `macro-context-index-completion-20260828-sol-001`
- **Workstream:** `WS:MACRO-CONTEXT-INDEX`
- **Author of record:** Sol (CEO). This file is the durable repository copy of Sol's
  frozen completion architecture, persisted by the commissioned Fable COO per Sol's
  durable-record requirement (carrier thread, 2026-08-28). The Slack Canvas
  (`F0BTD6WF51P`) and carrier thread remain **transport only**; this file is the
  durable architecture record. Canonical truth planes are unchanged: Executive OS for
  runtime lifecycle, Agent OS for organizational workstreams/decisions/handoffs,
  GitHub for implementation/evidence, and current accepted repository authority for
  architecture. Slack/Canvas prose is never self-authorizing.
- **Current Sol Skillpack pin:** Mastermind protected `master`
  `e2092cb6235519ac7f50fb3aa50ec1c1a6f627c0`, schema `mastermind.sol_skillpack.v1`,
  v1.0.0, bootstrap major 1.
- **Macro pickup base observed by Sol immediately before handoff:**
  `24ccea3fe482ab97c415db387f272b34c4852ed3`. Workers re-pin fresh `origin/main`
  before editing and before push.
- **COO routing:** Fable principal. Sustained cross-repository,
  architecture/authority-sensitive program. Fable may delegate bounded engineering
  after each boundary is frozen; mechanical tiers only for low-ambiguity
  fixture/migration work. Sol remains CEO architecture/adjudication/final acceptance.

## Precedence vs. the prior CXI adjudication

`research/MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md` (CXI-R1..R23a, plus
Amendments 1–2) remains the ruling record for the CXI rulings it minted. Precedence
is exact:

1. **This masterplan's Architecture freeze and C0→C8 completion program supersede**
   the adjudication's build program (§4) and any wave sequencing implied there.
   Where the two conflict on *what to build next, in what order, and with what
   acceptance gates*, this document governs.
2. **The CXI-R rulings themselves stay binding** (e.g. CXI-R4 status enum, CXI-R9
   semantic-lane gate, CXI-R14 private-excerpt ban, CXI-R16 cross-repo eval
   contract, CXI-R17a/b/c grading semantics, CXI-R19 advisory status, CXI-R23/R23a
   chat-context fencing) except where a clause of the Architecture freeze below
   explicitly restates or narrows them — the freeze clause then governs. In
   particular, CXI-R9 is reaffirmed: embeddings enter only by Sol adjudication on a
   documented paraphrase miss class; C3 names the entry point.
3. **CXI-R19 (advisory status) is unchanged by this document.** The "advisory"
   label is removed only at C8, after C3 + C5 + C6 + C7 acceptance by Sol.
4. Benchmark gold amendments remain governed by the append-only amendment protocol
   in `research/context_index/README.md`; this masterplan's C0 commissions such a
   pass, it does not replace the protocol.

## Chairman mandate

Complete CXI until governed project-context retrieval is genuinely reliable,
current-source safe, used across Macro/Terminal/Mastermind-Portfolio, and no longer
merely advisory.

## Outcome

The primary machine job is: given a new research/engineering/governance task,
recover the smallest correct current context packet across Macro, Terminal and
Mastermind/Portfolio, preserve authority and conflict semantics, and force exact
current authoritative sources to be opened before high-authority action where
required.

The completion outcome is not "green benchmark code." It is a real operator/agent
workflow where CXI saves rediscovery time **without** becoming a second source of
truth or laundering stale/retrieved text into authority.

## Current capability ledger (as frozen 2026-08-28)

| Capability | Current state | CEO ruling |
|---|---|---|
| Multi-project config / per-project SQLite views | BUILT_NOT_PROVEN | Existing canonical CXI plane; extend, never replace |
| Macro search/open/recent/explain/status + `context_packet.v1` | PARTIAL | Functional, benchmark/adoption gates red |
| Agent OS corpus | BUILT_NOT_PROVEN | Already landed through Agent OS Phase 3 / PR #5561; stale CXI W2 TODO must be corrected, not rebuilt |
| Authority/status/conflict preservation | PARTIAL | Contracts exist; relevance and current-source behavior need hardening |
| Honest no-answer/abstention | BROKEN | v5 negative-control family 0/10; threshold tuning already rejected |
| Terminal private corpus | BUILT_NOT_PROVEN | Corpus exists; no current full benchmark/use proof |
| Mastermind/Portfolio private corpus | BUILT_NOT_PROVEN | Same |
| Operator Brain shared-plane `context_search/context_open` | BUILT_NOT_PROVEN | Tool exists for allowlisted operator sessions; usage proof absent |
| Mandatory preflight | NOT_BUILT | Correctly held until promotion/A-B gates pass |
| Current-source exact open | BROKEN/PARTIAL | CLI may return indexed cached chunk before current source; fix before reliance |
| Freshness/self-heal | PARTIAL | stale flag exists; ratified on-demand self-heal not yet proven as operating behavior |
| Retrieval quality/adoption telemetry | PARTIAL | corpus health exists; retrieval/use/open-compliance telemetry incomplete |

## Known benchmark state (as frozen 2026-08-28)

Latest committed attestation is still v5 from 2026-07-20: shared-only 76 rows, 43
pass, global Recall@10 56.6%, adjudication replay 57.1%, governance-labelled
"precision" 70%, comprehension 100%, negative controls 0/10, private block not
evaluated. Treat this as historical evidence, not current health.

At least CTX-067 and CTX-069 are stale negative-control gold today: CXI now exists
and `config/context_index.yml` exists. The evaluator also calls governance-family
row pass-rate "precision"; this must be repaired or formally redefined before any
honest promotion claim.

## Architecture freeze

1. **One retrieval plane.** `config/context_index.yml` + `engine/context_index/**`
   + derived project SQLite views remain canonical CXI implementation. No new
   vector truth store, memory system, semantic registry, Agent OS DB, knowledge
   wiki or RAG write store.
2. **Agent OS is a corpus, not a second retriever.** Workstreams/handoffs remain
   temporal A4; decisions/discoveries remain A3; generated Agent OS rollup stays
   excluded.
3. **Relevance before authority.** Relevance decides whether a source is eligible;
   authority decides which relevant source governs. Higher authority may not
   compensate for near-zero topical relevance.
4. **Deterministic relevance before embeddings.** First mechanism: exact
   path/symbol/phrase, field-aware coverage, stopword-safe query coverage and
   IDF/rarity discrimination for abstention. Embeddings enter only if a current
   benchmark leaves a qualifying paraphrase miss class under CXI-R9.
5. **Current source is action truth.** Search/packet excerpts are discovery.
   `context_open` for action/high-authority use must resolve the configured project
   and read the current repository source, with moved/deleted/stale/conflict
   behavior named explicitly.
6. **Freshness is operational.** Every project carries indexed SHA vs current repo
   SHA. Stale index may be searched only with visible degradation; on-demand
   incremental self-heal belongs to the existing index, not a new daemon/database.
   Failed repair stays stale.
7. **Conflicts survive.** Return relevant current/stale, active/killed/superseded
   sides; authority/currentness route interpretation. Never silently delete the
   losing side.
8. **One root resolver.** Build/query/eval/consumers use the config
   loader/root_env contract; no separate hardcoded Terminal/Mastermind path maps.
9. **Open-before-act is enforced in existing session/agent law.** Do not invent an
   action ledger. Where relied-upon preflight becomes mandatory, the existing
   tool/session transcript must prove the authoritative sources were opened before
   mutation/adjudication.
10. **Telemetry is aggregate and privacy-safe.** Consumer/project scope, latency,
    stale/no-answer/conflict/error state, search→open compliance and A/B
    token/tool-call deltas. No query-text warehouse, no private corpus text/path
    leak, no new lifecycle store.
11. **CXI remains context-only.** Never feed signal rank/size/gate/allocation/NW
    authority paths.

## Completion program

### C0 — Benchmark Truth Recovery

**Mission:** make the measurement contract true before changing retrieval.

Audit all 104 benchmark rows against current sources across all three repos.
Re-adjudicate every negative control. Correct stale gold with append-only amendment
receipts. Repair the governance metric so "precision" is actual precision or
rename/freeze it by explicit ruling; report governance recall separately. Add
explicit no-answer accuracy. Rebuild current indexes and append fresh shared +
private baselines with exact repo/index SHAs.

**Acceptance:** 104/104 source-audited; private failures never counted as pass; old
result history untouched; no retrieval algorithm change.

### C1 — Deterministic relevance + abstention

**Mission:** fix the red matrix without benchmark-row hacks.

Implement exact identifier/path/phrase retrieval and deterministic query/source
discrimination. Add field-aware and IDF/rarity evidence sufficient to reject
irrelevant domain-vocabulary matches. Prevent authority promotion from turning
weakly relevant A0/A1 rows into false top results.

**Required comparison:** before/after on frozen C0 gold, with per-row reason and
mutation tests. Threshold-only retuning is forbidden.

**Exit:** hard-negative/no-answer accuracy >=90%; no governance/adjudication
regression; material lift in global/replay recall.

### C2 — Current-source and freshness safety

**Mission:** make "search then open before acting" actually trustworthy.

Unify root resolution through config. Make `context_open` resolve exact project +
current source instead of returning cached SQLite text as source authority. Add
stale/moved/deleted/symlink/ambiguous locator behavior. Implement/prove
existing-plane on-demand incremental SHA self-heal; corrupt state -> clean rebuild
or explicit degraded state.

**Exit:** adversarial stale/current/conflict tests green; current source always
wins action read; no cross-project/path leakage.

### C3 — Promotion benchmark

Run full current 104-row shared+private eval on fresh indexes.

**Promotion gates:** global Recall@10 >=90%; adjudication replay >=90%; true
governance A0/A1 precision >=95%; negative-control accuracy >=90%; p50
lexical/structured <2s; default packet <=6k tokens, hard <=8k; zero private
leakage; stale SHA always visible.

If deterministic work fails only on a documented paraphrase family, Sol adjudicates
CXI-R9 semantic-lane entry. Do not self-authorize embeddings.

### C4 — Agent OS integration proof

Correct `WS-MACRO-CONTEXT-INDEX` stale W2. Prove real `agentos.py compile-context`
named-workstream and free-text resolution on a freshly built index. Test ambiguity,
absent/stale index, superseded decision, fresh handoff, expired/stale discovery and
budget degradation. Agent OS content remains governed by Agent OS; search only
votes for identity and never injects unwalked content.

### C5 — Three-repository usefulness proof

Run a representative real task set in Macro, Terminal and Mastermind/Portfolio.
Each task must demonstrate query -> cited packet -> current authoritative open ->
correct action boundary. Include placement/collision, code-location, contract,
governance and honest-null cases. No fixture-only proof.

Measure wrong-source, stale-source, no-answer and conflict behavior by repo.

### C6 — Production/operator consumers

Prove operator Brain shared-plane consumer on a current host/index under the
existing allowlist fence. Establish agent/preflight consumer only after C3. Add
governed use from Terminal and Mastermind/Portfolio tooling through the same CXI
library/CLI contract where useful; do not expose private planes to public Brain.

Mandatory preflight, if promoted, applies only to the task classes the evidence
supports and retains exact-source-open requirement.

### C7 — A/B value proof

Run paired real repo-grounded tasks: current/manual exploration vs CXI-first.
Measure median input tokens, broad exploratory reads/tool calls, correctness,
time-to-authoritative-source, stale/conflict catches and user/operator usefulness.

**Value gate:** >=30% median input reduction or equivalent tool-call reduction AND
>=50% fewer broad exploratory reads, with no correctness degradation.

If A/B fails, diagnose routing/chunking/packing/relevance. Do not broaden corpus
reflexively.

### C8 — Promotion + durable closeout

Only after C3 + C5 + C6 + C7: remove the "advisory" house-law label and ratify
relied-upon preflight scope. Update Agent OS workstream/decision/discovery/handoff,
benchmark artifacts, canonical masterplan and operator documentation. Record
production receipts and exact maintenance procedure.

Terminate project watcher/session only after Sol final acceptance. A future
independent wave gets a new operation key/carrier.

## Failure-state law

- Stale index: explicit stale; cannot masquerade as current action evidence.
- Missing private checkout/DB: NOT-EVALUATED/DEGRADED, never PASS.
- No relevant source: honest null, not "best available" filler.
- Current and stale sources conflict: return both + currentness/authority framing.
- Canonical source disappeared/moved: open fails explicitly and search locator is
  treated stale.
- Same benchmark question changed meaning: amend gold with receipt, never rewrite
  history silently.
- Privacy tripwire or traversal/symlink escape: fail closed.
- New competing CXI carrier/path collision: stop and reconcile; never rename into a
  second implementation.
- Worker requires architecture/scope change: `DECISION_REQUEST` to Sol on the
  program carrier thread.

## Operator handoff and evidence contract

Every wave is one independently useful capability and returns: exact base/head SHA;
branch/PR; changed files; tests/mutations; benchmark deltas; real proof;
privacy/failure receipts; discovered conflicts; durable Agent OS updates
owed/completed; and exact next wave recommendation.

A PR/CI green is not acceptance. Sol reviews immutable head against the mission and
either issues `CONTINUE`, `RULING`, `STOP`, or a bounded repair.

## Dialogue / watcher contract for this program

This program's Slack carrier is **transport/attention only**. It does not own
execution state. The assigned Fable COO ACKs the exact program operation on the
parent thread with session identity, claimed wave, branch, fresh base SHA, PR if
any, collision result, and watcher/wait capability. All `PROGRESS`, `BLOCKED`,
`DECISION_REQUEST`, `RESULT` and Sol replies stay on that same thread for the
current wave. After every nonterminal return, the COO enters its available
exact-thread watcher/wait, or returns `BLOCKED: WATCH_UNAVAILABLE` rather than
disappear. Sol's temporary hourly condition watch is transport continuity only, not
lifecycle truth, and both sides terminate watchers on accepted terminal completion.

## First wave: C0

Start with **C0 Benchmark Truth Recovery**. Do not touch retrieval ranking yet.
Stop after C0 PR/evidence is ready and return to Sol on the carrier thread. Sol
will adversarially review the immutable head and then issue the next bounded wave.

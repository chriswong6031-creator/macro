# Agentic Quant Research Factory — Assessment for Fable

**Status:** Research study and implementation assessment.  
**Prepared:** 2026-07-06.  
**Audience:** Fable main loop.  
**Source prompt:** Attached Ruuj write-up on agentic AI for quantitative trading systems.  
**Scope:** Translate the write-up into Macro Dashboard / Neural Web implementation decisions. Do not re-propose machinery already adjudicated in `NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`.

---

## 0. Executive Verdict

The useful lesson from the write-up is not "AI should trade." It is:

> A serious agentic quant system is a throughput engine wrapped in hard research governance: structured hypotheses, implementation discipline, adversarial challenge, multiple-testing control, human review, and live decay monitoring.

Macro Dashboard already has much of the statistical and governance substrate:

- Oracle brainstorm packs, inbox ingestion, screening, gauntlets, OOS/placebo paths.
- Neural Web cortex, hypothesis metabolism, machine registry, research queue, constitution, governance ledger, and A2 probation.
- Trial Ledger, DSR, BH-FDR, bootstrap-effective-T, HAC t-stats, calibration utilities.
- Alpha grammar and overlap map from `nw-quant-synthesis`.
- Claude model routing and pinned `builder` / `reviewer` subagents.

The missing build is therefore **not** another alpha engine. The missing build is an explicit **Research Factory Orchestrator** that makes the existing pieces behave like one audited institutional pipeline.

Fable should assess a new program with this narrow charter:

1. Create one canonical state machine for machine/human research candidates.
2. Add mandatory Challenger packets before any human-review queue.
3. Add candidate-level paper/live monitoring and decay/retirement rules.
4. Keep LLMs out of executable evaluation and scored/sizing authority.
5. Use Claude subagents as workflow roles, but keep durable state in repo ledgers, not in a Claude account.

Recommended first ruling:

> BUILD W0-W3 as a display-only research-factory coordination layer. DEFER arbitrary Claude code generation. REJECT any design that lets an LLM originate live signals, adjust gates, edit validators, or promote scored/sizing outputs.

---

## 1. How To Read The Ruuj Write-Up

The write-up should be treated as an architecture prompt, not as a fact-checked source of fund-specific claims. The fund headline claims are not necessary for our decision. The transferable architecture is:

- **Throughput problem:** human researchers can rigorously test only a small number of hypotheses; an agentic funnel can generate and pre-filter more.
- **Three-layer design:** orchestrator, specialist agents, human gate.
- **State machine:** every hypothesis has a status and transition reason.
- **Specialist roles:** idea generator, implementer, evaluator, challenger.
- **Challenger:** adversarial critique is separate from numeric evaluation.
- **Statistical discipline:** block bootstrap / DSR, multiple-comparison correction, high t-stat thresholds, walk-forward validation.
- **Monitoring layer:** signal health, performance health, data health, and human escalation.

Those are mostly aligned with our house laws. The difference is that our implementation must respect stronger constraints:

- LLMs may not originate live signals, scores, or escalations.
- Everything is display-only until gauntleted.
- Nightly is the sole advancer of forward ledgers.
- Heavy compute stays off the render path.
- Fable adjudicates; spawned agents use explicit model routing.

The article's most useful missing phrase for us is **"research candidate throughput," not "autonomous trading."**

---

## 2. Current Repo Inventory

### 2.1 Already Built: Research Substrate

Neural Web build-out is no longer a blank slate. The masterplan records:

- W2 spine federation and `spine_index.parquet`.
- W3 reliability kernel estimates and quarterly FDR decision machinery.
- W4 confluence graph and contradictions.
- W7a constitution and governance ledger.
- W7b cortex on shadow probation.
- W7b hypothesis metabolism: server-side `registered_at`, hard-wired `fdr_family='cortex'`, weekly budget, strict post-registration evaluator.
- W8a operator HQ and W8b committee / ask-the-brain surfaces.

Relevant files:

- `engine/neuralweb/cortex.py`
- `engine/neuralweb/metabolism.py`
- `scripts/evaluate_cortex_hypotheses.py`
- `scripts/grade_cortex_attention.py`
- `engine/neuralweb/research_queue.py`
- `engine/neuralweb/constitution.py`
- `config/dag.yml`
- `config/synapse.yml`

### 2.2 Already Built: High-Volume Brainstorm Intake

Oracle already has the most mature external-brainstorm loop:

- `scripts/oracle_brainstorm_pack.py` emits a self-contained prompt pack with live "already explored" context.
- `research/oracle_inbox/*.json` holds raw scratch outputs.
- `scripts/oracle_ingest_brainstorm.py` parses, dedups, validates grammar, flags scale errors, and writes a scratch registry.
- `scripts/oracle_screen.py` screens pending specs.
- `scripts/oracle_gauntlet_compound.py` handles survivors via OOS/placebo.

This is close to the article's "idea agent" stage, but it is domain-specific and not a general research-factory state machine.

### 2.3 Already Built: Statistical Guardrails

The repo already has the math layer the write-up asks for:

- `engine/trial_ledger.py`: counts trials at generation, not only after survivor selection.
- `engine/validation.py`: DSR, bootstrap effective-T, BH-FDR, HAC/Newey-West, block-bootstrap CI, calibration, incremental IC.
- `engine/promotion_gate.py`: propose-not-deploy champion/challenger style gate.
- `scripts/research/compile_alpha_candidates.py`: ledger-first alpha candidate scoring.
- `tests/test_alpha_grammar.py`: PIT spike tests, BH-FDR wiring, DSR effective-T wiring.

Important nuance: the older `SELF_IMPROVING_AI_SUITE.md` says trial accounting was only about 10% complete at the time. That is stale in direction: several hard pieces have since landed. But its warnings remain valid for any new autonomous code-generation surface.

### 2.4 Already Built: Claude Role Routing

The repo already contains model-pinned subagent profiles:

- `.claude/agents/builder.md` -> Sonnet, mechanical build/doc/test work.
- `.claude/agents/reviewer.md` -> Opus, adversarial review/stat/math/code critique.

`CLAUDE.md` also states:

- Fable is the main loop only.
- Fable must not be spawned.
- Sonnet builds.
- Opus reviews.
- Every fan-out must explicitly route model/agent type.

Therefore, we do not need a new conceptual "Claude account brain." We need repo-native orchestration that can call the existing Claude profiles when a human/Fable session chooses to run a batch.

---

## 3. Gap Map Against The Article

| Article component | Repo status | Gap |
|---|---|---|
| Orchestrator state machine | Partial | Cortex has metabolism and Oracle has inbox/registry, but no cross-domain candidate lifecycle ledger. |
| Idea agent | Partial | Oracle prompt packs and cortex hypothesis inbox exist; no general typed proposal schema across Oracle / alpha grammar / cortex / human ideas. |
| Implementer | Partial and risky | Builder subagent exists; alpha grammar avoids codegen; no safe arbitrary strategy-code lane. |
| Evaluator | Strong | Existing screeners, gauntlets, validation primitives, Trial Ledger, FDR, DSR. Needs common adapter. |
| Challenger | Weak | Reviewer subagent exists, but no mandatory structured challenge artifact per candidate. |
| Human gate | Strong doctrine, weak queue | House law requires it; no unified review packet queue for Fable/operator. |
| Monitoring layer | Partial | Cortex attention grading, probation, kernel clocks, qledger ledgers exist; no candidate-level signal-health/paper-monitor standard. |
| Decay/retirement | Partial | Species/experiments registries and falsifiers exist; no universal research-candidate retirement engine. |
| Cost/identity boundary | Partial | Model routing exists; agentic execution identity boundary remains a blocker for codegen. |

Conclusion: The missing layer is an **orchestration and audit layer**, not another evaluator.

---

## 4. The Core Design: `research_factory`

### 4.1 Definition

`research_factory` is a cross-domain orchestration layer over existing engines. It does not invent trades. It does not score stocks. It does not alter board ordering. It tracks candidate research objects through a fixed lifecycle.

It owns:

- candidate identity;
- candidate state;
- transition reasons;
- source artifacts;
- challenge packets;
- human review packets;
- paper-monitor metadata;
- retirement decisions.

It delegates:

- Oracle compound validation to Oracle.
- Alpha grammar scoring to the alpha grammar runner.
- Cortex hypothesis registration/evaluation to metabolism/evaluator.
- Statistical tests to `engine.validation`.
- Trial accounting to `engine.trial_ledger`.
- Human/Fable adjudication to the main loop.

### 4.2 State Machine

Recommended canonical states:

| State | Meaning | Allowed next states |
|---|---|---|
| `proposed` | Raw idea/spec entered the factory. | `schema_rejected`, `deduped`, `registered` |
| `schema_rejected` | Invalid shape, missing mechanism, impossible data, illegal authority. | terminal |
| `deduped` | Duplicate of existing candidate/spec/species. | terminal |
| `registered` | Candidate has stable id and trial family. | `implemented`, `screened`, `awaiting_data`, `retired` |
| `implemented` | Candidate has executable DSL/spec/code reference. | `screened`, `implementation_rejected` |
| `implementation_rejected` | Leak, illegal data, code unsafe, DSL invalid. | terminal |
| `screened` | First numeric pass run. | `challenged`, `numeric_rejected`, `awaiting_data` |
| `numeric_rejected` | Failed deterministic floor. | terminal |
| `challenged` | Challenger packet completed. | `human_review`, `challenge_rejected` |
| `challenge_rejected` | Adversarial review found blocker. | terminal |
| `human_review` | Fable/operator packet ready. | `paper`, `deferred`, `rejected` |
| `paper` | Candidate accrues live/paper evidence display-only. | `promote_eligible`, `paper_rejected`, `retired` |
| `promote_eligible` | Numeric + challenge + paper evidence sufficient for separate program ruling. | `deferred`, `scoped_build`, `rejected` |
| `retired` | Edge decayed or no longer worth budget. | terminal |

Fable should be strict: no direct transition from `screened` to `paper`, no direct transition from `proposed` to `implemented` for arbitrary code, and no transition to scored/sizing surfaces inside this program.

### 4.3 Candidate Schema

Suggested JSONL row for `data/research_factory/candidates.jsonl`:

```json
{
  "schema": "research_factory.candidate.v1",
  "candidate_id": "rf-2026-07-06-oracle-washout-flow-001",
  "created_at": "2026-07-06T00:00:00Z",
  "source": "oracle_brainstorm|cortex|alpha_grammar|human|external_report",
  "domain": "oracle|neuralweb|entry|factor|macro|options|china|us_stocks",
  "status": "proposed",
  "hypothesis": "specific falsifiable statement",
  "mechanism": "why this could exist economically or mechanically",
  "expected_failure_modes": ["crowding", "regime flip", "data delay"],
  "decay_conditions": ["edge disappears if fire rate falls below X", "fails in risk_off holdout"],
  "falsifiers": ["if post-entry MAE exceeds expected band", "if placebo beats real timing"],
  "claim_shape": "oracle_compound|cortex_hypothesis|alpha_formula|species|code_candidate",
  "spec_ref": "path or inline id",
  "implementation_ref": null,
  "trial_family": "rf.oracle.reversion.2026w28",
  "evaluation_plan": {
    "primary_metric": "ret_exit|hit_rate|rank_ic|stop_out_rate|dsr",
    "horizon_d": 21,
    "min_n": 100,
    "fdr_scope": "family"
  },
  "artifacts": {},
  "transition_log": [
    {
      "at": "2026-07-06T00:00:00Z",
      "from": null,
      "to": "proposed",
      "reason": "ingested from external article implementation study",
      "actor": "codex"
    }
  ]
}
```

### 4.4 Transition Log

State transitions must be append-only:

`data/research_factory/transitions.jsonl`

Each transition should carry:

- `candidate_id`
- `from`
- `to`
- `reason_code`
- `reason_text`
- `actor`
- `artifact_refs`
- `as_of`

This matters more than elegance. The article is right that a high-throughput research machine becomes unmanageable unless every reject and promotion has a reason.

---

## 5. Mandatory Challenger Packets

### 5.1 Why This Is The Highest-Value New Piece

The repo already has numeric tests. What it lacks as a universal requirement is a separate adversarial artifact before human review.

The Challenger should not approve a signal. It should try to kill it.

This is different from:

- `research_queue.py`, which ranks expected value.
- `evaluate_cortex_hypotheses.py`, which applies pre-committed gates.
- `promotion_gate.py`, which checks supplied numeric gates.
- Opus code review in PRs, which reviews implementation diffs.

The Challenger packet is candidate-level epistemic opposition.

### 5.2 Challenger Schema

Suggested output:

```json
{
  "schema": "research_factory.challenge.v1",
  "candidate_id": "rf-...",
  "challenger_model": "reviewer",
  "challenged_at": "2026-07-06T00:00:00Z",
  "recommendation": "REJECT|REVIEW|PASS_TO_HUMAN",
  "blockers": [
    {
      "severity": "blocker|major|minor",
      "category": "lookahead|survivorship|overfit|cost|regime|mechanism|implementation|data|authority",
      "finding": "specific concern",
      "evidence_ref": "artifact path / metric / file line"
    }
  ],
  "non_blocking_concerns": [],
  "best_counterargument": "strongest reason this is fake or not useful",
  "minimum_fix_to_reconsider": "what would need to change",
  "human_review_question": "specific question Fable/operator must decide"
}
```

Do not include LLM-authored confidence scores. Repo doctrine already rejects fake precision from LLMs. Use categorical recommendations and concrete blockers.

### 5.3 Challenger Checklist

Every candidate packet should attack:

1. **Specificity:** is this a testable hypothesis or just a theme?
2. **Mechanism:** is there a reason it could persist?
3. **Decay:** did the proposer specify when it stops working?
4. **Lookahead:** can the implementation see data unavailable at t?
5. **Survivorship:** are dead/removed names excluded?
6. **Same-bar fill:** does the entry assume impossible execution?
7. **Multiple testing:** was the full generated grid counted?
8. **OOS/placebo:** does real timing beat randomized timing?
9. **Regime:** does it only work in one benign slice?
10. **Cost/capacity:** does turnover or liquidity erase it?
11. **Duplicate witness:** is it just an existing signal variant?
12. **Authority:** would any output violate Article 1/2 or a prior Fable ruling?

### 5.4 Routing

Use existing Claude profiles:

- `builder` / Sonnet can draft mechanical challenger packets for low-risk specs if the source artifacts are simple.
- `reviewer` / Opus should handle anything entering `human_review`.
- Fable main loop adjudicates final routing.

Fable should explicitly forbid `fable` subagent spawning. The main loop is Fable; fan-outs are model-pinned.

---

## 6. Implementation Strategy By Candidate Type

### 6.1 Oracle Compounds

Oracle already has the strongest high-volume pathway. `research_factory` should not replace it.

Flow:

1. `proposed`: candidate comes from `oracle_brainstorm_pack` output or human spec.
2. `registered`: spec is normalized into Oracle compound JSON.
3. `implemented`: Oracle DSL validation succeeds.
4. `screened`: `oracle_screen` / `oracle_reversion_screen` result attached.
5. `challenged`: Challenger packet attacks scale bugs, recent-only columns, n floors, regime dependence, already-tested basins.
6. `human_review`: only if numeric gates and Challenger pass.
7. `paper`: only after Fable/operator accepts a display-only trial.

Key point: no LLM codegen. Oracle remains grammar-first.

### 6.2 Alpha Grammar Candidates

Alpha grammar is research-side and unregistered until a family survives gates. `research_factory` should track families and top candidates, not individual formula noise unless the family produces survivors.

Flow:

1. `proposed`: alpha family idea.
2. `registered`: Trial Ledger budget declared/logged before enumeration.
3. `implemented`: formula AST / primitive set exists.
4. `screened`: `compile_alpha_candidates` output.
5. `challenged`: review survivorship caveat, PIT law, candidate cap, DSR/FDR, clustering.
6. `human_review`: if any family-level survivor is worth a fresh program.

Do not let the factory turn `net_new_info_score` into a board score. Fable already ruled overlap metadata is cluster metadata only.

### 6.3 Cortex Hypotheses

Cortex already has metabolism. The factory should wrap it only at the review/orchestration level.

Flow:

1. Cortex proposes via `stake_hypothesis`.
2. `metabolism.register_hypothesis()` applies server-side timestamp, budget, `fdr_family='cortex'`, min-n clamp.
3. `evaluate_cortex_hypotheses.py` grades strictly post-registration.
4. `research_factory_challenge` attacks passed/interesting rows before human review.
5. Fable decides whether a passed row becomes a new scoped build or remains paper/context.

Do not raise the weekly cortex budget just to imitate the article's "hundreds of ideas." Our current `3/week` is a feature, not a weakness, until the full Challenger and monitor loop exists.

### 6.4 Human / External Research Ideas

This is where the new system helps most. Today, external reports turn into ad hoc memos and Fable rulings. The factory should give them a path:

1. Extract candidate specs.
2. Dedup against `NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md` duplicate registry and existing species/registry.
3. Categorize as:
   - already built;
   - rejected by house law;
   - needs data;
   - buildable as display-only;
   - needs separate risk acceptance.
4. Only build display-only items with explicit gates.

This will make future "what can we learn from this?" tasks faster and less repetitive.

---

## 7. Production Monitoring Layer

The article's monitoring section is underdeveloped but important. For us, monitoring should be candidate-specific and authority-aware.

### 7.1 Paper Monitor Schema

Suggested artifact:

`data/research_factory/paper_monitor.jsonl`

Fields:

```json
{
  "schema": "research_factory.paper_monitor.v1",
  "candidate_id": "rf-...",
  "as_of": "2026-07-06",
  "paper_status": "warmup|operating|human_review|retire",
  "expected_fire_rate_pm": 12,
  "observed_fire_rate_pm": 8,
  "expected_metric": {"name": "hit_rate_21d", "value": 0.58},
  "observed_metric": {"name": "hit_rate_21d", "value": 0.51, "n": 42},
  "drawdown_or_mae_flag": false,
  "data_health_flags": [],
  "decay_flags": [],
  "action": "continue|review|retire",
  "note": "display-only; no scored-path authority"
}
```

### 7.2 What To Monitor

For every candidate in `paper`:

- **Signal health:** fire frequency, stale/noisy input rate, long/short/flat distribution when applicable.
- **Performance health:** hit rate, MFE/MAE, rank IC, stop-out rate, or whatever the pre-registered metric was.
- **Data health:** missing input frequency, collection delay, symbol mapping breaks, date alignment.
- **Decay health:** whether the candidate's own decay conditions are triggering.
- **Authority health:** whether any consumer is accidentally reading the artifact.

### 7.3 Retirement

Retirement should be symmetric with promotion. A candidate can retire because:

- paper metric breaches pre-declared decay floor;
- data becomes unreliable;
- the candidate duplicates a better surviving family;
- sample never accrues;
- regime support disappears;
- Fable rejects future compute budget;
- human operator no longer wants the family.

Retirement writes a transition. It does not delete history.

---

## 8. Claude Account / Subagent Decision

### 8.1 Do We Need A Dedicated Claude Account?

No, not as the system of record.

The durable system should live in:

- repo files;
- JSONL ledgers;
- Git history;
- GitHub Actions / local scripts;
- admin/committee surfaces;
- explicit Fable rulings.

A Claude account/chat should never be the memory, database, or state machine. Chat context is too fragile and non-auditable.

### 8.2 Do We Need Claude Subagents?

Yes, but only as execution roles.

Use the existing pattern:

- Fable main loop: planning, adjudication, rulings, merges, final synthesis.
- `builder` / Sonnet: code, tests, doc drafts, mechanical transforms.
- `reviewer` / Opus: adversarial challenge, statistical review, red-team.
- Haiku: trivial extraction/formatting if needed.

For this program:

| Role | Model/profile | Writes? | Purpose |
|---|---|---|---|
| Orchestrator | Fable main loop | yes, via human-controlled PRs | Chooses batch, adjudicates, final rulings. |
| Idea extractor | Sonnet or Haiku | no durable writes unless through script output | Turns reports/prompt packs into candidate JSON. |
| Spec normalizer | Sonnet builder | yes, scratch/spec only | Converts ideas into legal DSL/spec schemas. |
| Evaluator | deterministic Python | yes to artifacts | Runs screeners/gauntlets; no LLM judgment. |
| Challenger | Opus reviewer | writes challenge JSON | Attacks candidate before human review. |
| Human gate | Fable/operator | writes rulings | Accepts, rejects, or scopes new work. |

### 8.3 Service Key vs Claude Account

For scheduled automation, prefer an API/service key path over a headless personal Claude OAuth flow. The older self-improving suite already made the right point: user OAuth is fragile for CI and hard to reason about operationally.

But W0-W3 can be built without new scheduled LLM calls. The first version can be operator/Fable-invoked:

1. Generate candidate batch in a Codex/Claude session.
2. Save candidates to inbox.
3. Run deterministic scripts.
4. Run reviewer subagent for Challenger packets.
5. Fable adjudicates.

Only after that loop proves useful should we schedule recurring LLM use.

---

## 9. What To Reject

Fable should reject these shapes up front:

1. **Autonomous live trading.** Out of scope and violates house law.
2. **LLM-authored confidence scores.** Use calibrated code metrics, not model vibes.
3. **LLM-generated arbitrary strategy code in v1.** DSL/spec-first only.
4. **Any agent that edits `engine/validation.py`, gates, red-team prompts, or vault logic.** Human/Fable only.
5. **Any output that affects board rank/size/alert priority.** Display-only until separate gauntlet/ruling.
6. **Utility router / meta-router with sizing.** Already rejected by Fable in `NW_QUANT_SYNTHESIS`.
7. **A fused "AlphaGPT score."** This repeats the forbidden composite shape.
8. **Raising cortex proposal volume before the challenge/monitor layer exists.** Throughput without gates is false-positive manufacture.
9. **Treating external social posts as verified facts.** Extract architecture, then test inside our system.
10. **Using Claude chat memory as a research ledger.** Durable state belongs in repo artifacts.

---

## 10. Proposed Program For Fable

### W0 — Program Ruling And Boundary

Deliverable:

- `research/RESEARCH_FACTORY_PROGRAM_BY_FABLE.md`

Rulings to include:

- Build coordination layer only.
- Candidate lifecycle is display-only/context.
- No codegen lane in W0-W3.
- Challenger packet mandatory before human review.
- Human/Fable gate mandatory before paper.
- Existing engines remain owners of evaluation.
- Artifacts live in `data/research_factory/` and are registered in `config/synapse.yml` only when they become durable bus citizens.

Exit gate:

- Fable signs off on state vocabulary, authority boundary, and first candidate domains.

### W1 — Candidate Ledger And Ingest

Files:

- `engine/research_factory/__init__.py`
- `engine/research_factory/state.py`
- `engine/research_factory/schema.py`
- `scripts/research_factory_ingest.py`
- `tests/test_research_factory_state.py`

Functionality:

- Append-only candidate ledger.
- Transition helper with allowed-state enforcement.
- Dedup by candidate spec hash.
- Source adapters for:
  - Oracle inbox JSON;
  - cortex `hypothesis_inbox.jsonl`;
  - alpha grammar family summaries;
  - manual JSON proposals.

No LLM required.

Exit gate:

- Unit tests prove invalid transitions are rejected.
- First dry-run batch ingests at least one candidate from Oracle or manual JSON.

### W2 — Deterministic Runner Adapters

Files:

- `engine/research_factory/adapters/oracle.py`
- `engine/research_factory/adapters/cortex.py`
- `engine/research_factory/adapters/alpha_grammar.py`
- `scripts/research_factory_run.py`
- `tests/test_research_factory_adapters.py`

Functionality:

- Read a candidate.
- Route to the existing domain evaluator.
- Attach artifact refs.
- Transition candidate to `screened`, `numeric_rejected`, `awaiting_data`, or `implementation_rejected`.

Important:

- Adapter does not duplicate the underlying evaluator.
- Adapter only records the result and transition reason.

Exit gate:

- Tests use fixtures/mocks, not heavy data.
- Real command can list what it would run in `--dry-run`.

### W3 — Challenger Packet

Files:

- `engine/research_factory/challenge.py`
- `scripts/research_factory_challenge_pack.py`
- `research/research_factory/CHALLENGER_PROMPT.md`
- `tests/test_research_factory_challenge.py`

Functionality:

- Build a JSON challenge input packet.
- Validate a reviewer response against schema.
- Transition candidate based on `REJECT|REVIEW|PASS_TO_HUMAN`.

The script can be manual in v1:

1. It prints/saves the challenge packet.
2. Fable runs reviewer subagent.
3. Reviewer output is saved as JSON.
4. Script validates and records transition.

Exit gate:

- At least one old Oracle candidate and one cortex candidate can generate a challenge packet.
- Bad reviewer JSON fails validation and does not transition.

### W4 — Human Review Queue

Files:

- `engine/research_factory/review_queue.py`
- `scripts/build_research_factory_review_queue.py`
- optional admin panel after artifact shape stabilizes.

Functionality:

- Collect `human_review` candidates.
- Display:
  - hypothesis;
  - mechanism;
  - metrics summary;
  - Challenger blockers;
  - exact question for Fable/operator;
  - allowed decisions.

Allowed decisions:

- `paper`
- `deferred`
- `rejected`
- `scoped_build`

Exit gate:

- Review queue is generated as JSON/Markdown.
- No consumer treats it as scored-path input.

### W5 — Paper Monitor And Retirement

Files:

- `engine/research_factory/monitor.py`
- `scripts/research_factory_monitor.py`
- `tests/test_research_factory_monitor.py`

Functionality:

- Track paper candidates.
- Compute expected vs observed metrics when data exists.
- Emit decay flags.
- Recommend `continue|review|retire`.
- Transition only to `human_review` or `retired`; never to production.

Exit gate:

- Monitor supports warmup and absent-data states.
- Retirement leaves history intact.

### W6 — Optional Automation

Only after W1-W5 prove useful:

- Add scheduled candidate extraction from selected prompt packs.
- Add scheduled Challenger batch for candidates that clear numeric screens.
- Add cost telemetry.
- Add identity-bound PR-only codegen lane only if separately risk-accepted.

Fable should treat W6 as a new program, not the default continuation.

---

## 11. First Practical Batch

The first batch should not be broad. Use one path where the repo is already strong:

### Batch A: Oracle Reversion Candidate Factory

Why:

- Oracle brainstorm grammar is mature.
- The screen/gauntlet path already exists.
- We can validate orchestration without new alpha logic.

Batch:

1. Run `scripts/oracle_brainstorm_pack.py --reversion --explore`.
2. Generate or import 20-50 specs.
3. Ingest with `oracle_ingest_brainstorm`.
4. Route survivors through `research_factory`.
5. Challenge only the top 5 numeric survivors.
6. Fable reviews the packets.

Success criteria:

- The factory records every drop reason.
- Challenger kills at least some attractive numeric mirages.
- Human review packets are faster to adjudicate than raw screen output.

### Batch B: Cortex Hypothesis Review

Why:

- Cortex metabolism already tracks registered proposals.
- The missing link is Fable-readable challenge/human-review packets.

Batch:

1. Read existing/due machine registry rows.
2. Build challenge packets for any passed/interesting rows.
3. Fable decides whether any should become scoped builds.

Success criteria:

- No change to cortex budget.
- No promotion.
- Better visibility into what the cortex is actually proposing.

---

## 12. Risk Register

| Risk | Why it matters | Mitigation |
|---|---|---|
| False-positive throughput | More ideas create more mirages. | Trial Ledger, DSR, BH-FDR, Challenger, human gate. |
| LLM authority creep | Agent starts "recommending" instead of proposing. | Schema names candidates as research only; no scored-path consumers. |
| Codegen leak | Generated code can accidentally look ahead. | No arbitrary codegen in W1-W5; DSL-first. |
| Validator tampering | An agent can make the gate easier. | Validators/gates human-owned; codegen lane deferred pending identity boundary. |
| Duplicate research churn | External reports recycle old ideas. | Dedup against species, machine registry, Fable duplicate registry. |
| Review bottleneck | Human gate becomes overloaded. | Research queue + Challenger should reduce volume reaching Fable. |
| Chat-state fragility | Claude account memory is not auditable. | Repo JSONL/Git artifacts are source of truth. |
| Render-path pressure | Heavy research slows nightly site. | Off-path scripts; register only small artifacts; R2/Mac-local for large replay data. |
| Subagent token burn | Frontier model fan-outs get expensive. | Use `.claude/agents` model pins; Fable never spawned. |
| Premature automation | Scheduling before loop is proven creates noise. | Manual/Fable-invoked v1; W6 separately adjudicated. |

---

## 13. Fable Decision Checklist

Fable should answer these before implementation:

1. Is the program name `research_factory`, or should it live under `neuralweb/research_factory`?
2. Which domains are allowed in W1: Oracle only, or Oracle + Cortex + alpha grammar?
3. Should candidate ledgers be git-tracked from day one, or kept under scratch until W2?
4. What is the minimum Challenger packet needed for human review?
5. Does W1 register artifacts in `config/synapse.yml`, or wait until W3?
6. Should `research_queue.py` feed the factory, or should the factory feed the queue?
7. What is the first live batch: Oracle reversion or cortex machine registry?
8. What is the exact human-review decision vocabulary?
9. Are paper-monitor artifacts admin-only or committee-page visible?
10. What line must not be crossed before a separate risk-accepted codegen program?

Recommended answers:

1. Use `engine/research_factory/`, not Neural Web-only, because Oracle and alpha grammar are first-class inputs.
2. W1 supports Oracle + manual JSON; W2 adds Cortex + alpha grammar adapters.
3. Git-track small ledgers only after schema stabilizes; use scratch for first dry-run.
4. Require categorical recommendation plus blocker list; no LLM confidence score.
5. Wait until W3 to register durable artifacts.
6. The factory should read the queue as one source, but not be governed by it.
7. Oracle reversion first.
8. `paper`, `deferred`, `rejected`, `scoped_build`.
9. Admin-only first.
10. No arbitrary codegen, no validator/gate edits, no scored/sizing influence.

---

## 14. Proposed Fable Ruling Text

Fable can adapt this:

> RULING: Build a repo-native Research Factory orchestration layer. The article's useful insight is throughput with discipline, not autonomous trading. Existing Oracle, Neural Web, alpha grammar, Trial Ledger, and validation systems remain the evaluators. The new program owns candidate state, transition reasons, challenge packets, human-review packets, and paper-monitor/retirement metadata. Everything is display-only/context until separately gauntleted. LLMs may propose and challenge, but may not originate live signals, alter validators, set scored/sizing outputs, or bypass the human gate. W1-W3 are approved for candidate ledger, adapter dry-runs, and Challenger packets. Arbitrary Claude code generation is deferred pending a separate identity-bound PR-only sandbox program.

---

## 15. Bottom Line

We should not copy the article's demos. We should absorb its operating model:

- many more ideas;
- narrower agent roles;
- explicit state;
- adversarial review;
- honest multiple-testing accounting;
- human gate;
- paper monitoring;
- retirement.

Macro Dashboard has enough substrate to build this now, but only if Fable keeps the first version boring: ledger, adapter, Challenger, review queue, monitor. The danger is trying to build "AlphaGPT" before the factory has enough audit rails. The opportunity is that most of the hard math and governance already exist; the missing piece is making them one coherent research assembly line.

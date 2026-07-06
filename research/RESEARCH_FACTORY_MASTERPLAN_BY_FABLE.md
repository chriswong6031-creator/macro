# Research Factory — Masterplan (by Fable)

**Status:** RATIFIED charter — W0 of the Research Factory program.
**Date:** 2026-07-06.
**Source study:** `research/AGENTIC_RESEARCH_FACTORY_FOR_FABLE.md` (Codex, 2026-07-06) — an implementation assessment of an external write-up on agentic quant research systems.
**Adjudication basis:** 6-lane repo census + 4-lens adversarial critique (design red-team, improvement architect, ops/CI, external research incl. SR 11-7 practice and 2025-26 agentic-quant literature), run 2026-07-06 under ultracode.
**Owner of record:** Fable main loop (adjudication); Sonnet builders; Opus reviewers.

---

## 0. Status log

- 2026-07-06 — W0 charter ratified (this doc). Census verified the study's inventory; four blocker-class corrections adjudicated into rulings RF-1..RF-16 below. Wave plan W1–W7 approved for build.
- 2026-07-06 — A1 amendment (W1 review): RF-5 re-arm gate scoped to respin registration; clock resurfacing ruled mechanical. Helper-invariant sentence in §4 aligned with the ledger.py split.
- 2026-07-06 — A2 amendment (W7): `domain_registry` source + `--adopt-oracle` ingest mode for RF-2 pointer adoption of existing domain-homed compounds (adoption ≠ duplication; dedup rule 1 waived only for the explicitly declared spec_ref).

---

## 1. Verdict

The Codex study's core diagnosis is CONFIRMED: the missing build is not another evaluator — it is a cross-domain **orchestration and audit layer** over the evaluators we already have (Oracle screens/gauntlets, cortex metabolism, alpha grammar runner, Trial Ledger, `engine/validation.py`, `engine/promotion_gate.py`). The factory owns candidate identity, state, transition reasons, challenge packets, review packets, paper-monitor metadata, and retirement. It evaluates nothing, scores nothing, and touches no board.

Four of the study's design decisions do NOT survive contact with the code and are overruled here (see §2). The corrected design is below; the study remains the narrative companion, this charter is the law.

**Authority ceiling (binding):** the factory operates at constitution rungs **A0–A2 only** (observe / explain / attend — `engine/neuralweb/constitution.py`). Challenge packets are A1-EXPLAIN artifacts. The review queue is A2-ATTEND. Article 1 (origination ban) is the hard ceiling: no factory output — LLM or script — may originate a signal, trade, escalation, or claim. `grant_authority()` refuses A7 unconditionally; the factory inherits that refusal by construction.

---

## 2. What the census overturned (evidence base)

Verified against the live worktree at `origin/main` (2026-07-06):

1. **`claim_shape` collision (blocker).** The study's candidate schema uses `claim_shape: oracle_compound|cortex_hypothesis|...`, colliding with metabolism's `CLAIM_SHAPES = {lead_lag, conditional_regime, entry_quality, sector_conditional}` which routes `evaluate_cortex_hypotheses.py` PATH A/B. A factory-authored value would silently fail registration or mis-route the evaluator. → RF-3.
2. **Display-only was doctrine, not mechanism (blocker).** `ci.yml` has NO paths glob for `scripts/research_factory*.py`, `data/research_factory/**`, or `tests/test_research_factory*.py` — a W1 PR as the study scoped it would merge silent-green with zero CI. The synapse read-gate only has teeth for artifacts *registered* in `synapse.yml`; the study deferred registration to W3, i.e. the boundary was unenforced during the exact window the ledgers first exist. → RF-11.
3. **Second-source-of-truth drift (blocker).** Oracle compounds (`exploratory/screened/accruing/promoted/refuted/blocked_missing_column`), cortex machine registry (`registered/budget-rejected/invalid/passed/failed/insufficient-n/retired`), and species (`phase0/accruing/validated/retired/falsified`) each already own a lifecycle vocabulary, advanced by their own nightly writers. A persisted factory copy WILL diverge. → RF-2.
4. **Challenger auto-transition violates Article 1 (blocker).** The study lets the Opus reviewer's `REJECT|PASS_TO_HUMAN` recommendation drive the `challenged → challenge_rejected|human_review` fork — an LLM originating a terminal kill or an escalation. → RF-5/RF-7.
5. **There is no single Oracle evaluator.** `oracle_screen.py` (63d excess, WRITES a counted trial-ledger row) and `oracle_reversion_screen.py` (absolute WR/MFE/MAE, 6-leg gauntlet built in, READ-ONLY) are non-overlapping tracks with different frozen rulers. The study routed everything through one. → RF-13.
6. **Phantom states.** `awaiting_data` is referenced but never defined; `deferred`/`scoped_build` are decisions with no state row; `implemented` is a no-op for both v1 domains (the spec IS the grammar) whose only real occupant would be the deferred codegen lane. → RF-4.
7. **Live-loop reality check.** `machine_registry.jsonl`, `hypothesis_inbox.jsonl`, and `turn_desk_ledger.jsonl` do not exist on disk yet (zero cortex registrations to date; turn desk awaits its first nightly). All adapters MUST be absent-file-safe, and the first batch is Oracle-only.
8. **Stale numbers.** Trial accounting is no longer "~10% complete": `data/trial_ledger.jsonl` is live across 20+ families; the remaining gap is the literal-`n_trials=` path in `deflated_sharpe` (ratcheted by `tests/test_no_literal_ntrials.py`). Experiments seed = 112 entries (not ~106). Engine-job cap = 120 min (render budget law still applies to the render path).

---

## 3. Rulings (RF-1 .. RF-16) — the law of this program

- **RF-1 — Charter.** Build `engine/research_factory/` (cross-domain, NOT under `neuralweb/`) as a repo-native orchestration layer. It owns candidate identity/state/transitions/challenges/review packets/monitor metadata/retirement. It delegates ALL evaluation to existing engines. Everything it emits is display-only context; ceiling A0–A2. `paper` = display-only accrual = SHADOW-equivalent on the staged-autonomy ladder (`SELF_IMPROVING_AI_SUITE.md` §5); `promote_eligible` = "eligible to PROPOSE a separate program ruling" — explicitly NOT an autonomy rung and NOT a gauntlet registration.
- **RF-2 — Projection law.** For candidates homed in an authoritative registry (Oracle compounds registry, machine registry, species registry), the factory persists ONLY `spec_ref` (the domain id) plus factory-orchestration state. Domain status is re-read and PROJECTED at read time via a fixed mapping (Oracle: `screened→screened`, `accruing→paper`, `promoted→promote_eligible`, `refuted→numeric_rejected`, `blocked_missing_column→awaiting_data`); it is never copied into a persisted factory field. On conflict the domain registry wins, always.
- **RF-3 — Naming.** The factory taxonomy field is **`candidate_type`** (`oracle_compound|cortex_hypothesis|alpha_family|species|external_idea`). `claim_shape` is RESERVED for the metabolism enum, copied verbatim from the metabolism-issued row when present, never invented by the factory.
- **RF-4 — State machine.** Exactly the 15 states of §4, all defined, no phantoms. `implemented`/`implementation_rejected` are dropped (grammar validation is part of ingest; failures are `schema_rejected` with `reason_code='grammar_invalid'`). `awaiting_data` and `deferred` are first-class non-terminal states with a mandatory `come_back_on`. `scoped_build` is terminal-to-factory and must reference a new `*_BY_FABLE.md` program doc.
- **RF-5 — Actor law.** Transitions are classed. Mechanical (actor=`script`, or `codex|sonnet` at ingest): `→proposed`, `→schema_rejected`, `→deduped`, `→registered`, `→awaiting_data`, `→screened` (engine artifact required), `→numeric_rejected` (deterministic engine floor + kill_evidence), `→challenged` (packet exists), `challenged→human_review` (unconditional — every challenged candidate enters the queue), `paper→human_review` (monitor decay flag), `paper→promote_eligible` (promotion_gate verdict). Human-gate (actor ∈ {`fable`,`operator`} with session/PR ref, REQUIRED): `→paper`, `→deferred`, `→rejected`, `→scoped_build`, `→retired`, and the registration of any respin candidate (`lineage.respin_of` set) — that is where kill-requeue and challenger-fix re-arms re-spend trials (RF-10/RF-15). Clock resurfacing (`deferred→human_review`, `awaiting_data→registered|screened`) is mechanical A2 attention-routing; counted screens remain gated by the operator-explicit `--count` at the runner (RF-13). The transition helper enforces this allowlist; violations raise.
- **RF-6 — Trial accounting.** Every candidate carries `trial_accounting` = `{mode: 'rf_family'|'cortex_shared'|'oracle_screen'|'read_only', family: str|null}`. `rf_family` names MUST match `^rf\.[a-z_]+\.[a-z0-9_]+$`, be <40 chars, never equal an existing production family, and be declared via `TrialLedger.log_declared_budget()`/`log_grid()` BEFORE any screening run — the `screened` transition REFUSES otherwise. Cortex candidates create NO new family (read the shared `'cortex'` family). Oracle 63d candidates are counted by `oracle_screen`'s own ledger write; the factory must never re-screen an already-screened compound (keep-first + params_hash; grammar-version bumps are counted intentionally). All DSR calls go through a ledger handle or `with_declared_budget()` — the literal `n_trials=` path is forbidden (ratchet-enforced). DSR deflates one candidate's grid; BH-FDR runs ONCE per screening batch per domain — never per-candidate.
- **RF-7 — Challenger law.** The challenger is ADVISORY-ONLY. Its output never selects a branch: every challenged candidate flows to `human_review` with the packet attached; kills are human-authored. Two layers: (a) **mechanical probes** (deterministic, pre-computed, no LLM): label-permutation/timing-placebo robustness flag (`input_insensitive`), structural near-dup score (largest-common-subtree over the grammar tree → `near_dup_review` flag), mechanism↔spec alignment check (`mechanism_spec_mismatch` flag), existing gauntlet leg verdicts attached as evidence; (b) **Opus reviewer packet** (spawned as `agentType='reviewer'`, never bare model, per the routing guard): outcome-blind prompting — the reviewer critiques mechanism and construction, is explicitly FORBIDDEN from asserting known realized outcomes for named tickers/periods (`parametric_lookahead` is a blocker category it must self-police and flag), receives aggregate metrics + leg verdicts but no per-fire outcome narrative. Categorical findings only — LLM-authored confidence scores are forbidden. Reviewer write scope: `data/research_factory/challenges/` ONLY.
- **RF-8 — Ledger law.** `candidates.jsonl`, `transitions.jsonl`, `challenges/*.json`, `review/*.json|.md`, `health.jsonl`, `paper_monitor.jsonl` all live in `data/research_factory/` and are git-tracked from the FIRST row (explicit `.gitignore` negation pattern; bulk/replay parquet is the only gitignore'd class). `transitions.jsonl` is append-only and is the audit history. `paper_monitor.jsonl` and `health.jsonl` are FORWARD LEDGERS: advanced only by the nightly engine job; intraday/manual invocations run `--dry-run` and write nothing under `data/`. Keep-first per `(candidate_id, as_of)`.
- **RF-9 — Clock law.** No bespoke clocks. Every candidate entering `paper`/`deferred`/`awaiting_data` gets an entry in `data/experiments/registry_seed.json` (kind `track_record`/`phase0`/`data_collection` as appropriate) with `come_back_on`, `hook='track_record'`, and `track_json` pointing at the factory's per-candidate artifact — the admin Experiments console overlay then refreshes it each build. Paper entries stamp regime-at-entry (reuse `regime/latest.json` + the reversion screener's `risk_on/risk_off` + `vix_pctile` tags) so decay review is regime-aware (`launched_hot` context flag). `expected_half_life_d` is declared at human review with a per-domain default prior (reversion ≈ 250 trading days), operator-overridable, recorded with `defaulted: true|false`.
- **RF-10 — Kill-scrutiny symmetry.** Every kill transition (`numeric_rejected`, `rejected`, `retired`) carries a `kill_evidence` block: `{n_at_kill, regime_split, mde_at_n (when computable), kill_class}` with `kill_class ∈ {falsified, underpowered_accruing, regime_change_suspect, duplicate, decayed, budget_withdrawn}`. `underpowered_accruing` and `regime_change_suspect` kills write a requeue pointer (mirror `data/oracle/reversion_kill_requeue.jsonl`, requeue at 2× n_at_kill); the re-arm is an explicit human decision, never automatic, because each re-screen is a new counted trial. Retirement writes a transition; history is never deleted.
- **RF-11 — Authority mechanism (not doctrine).** Ships in W1, not later: (a) required top-level field `"authority": "display_only"` on every factory artifact row; (b) `scripts/check_research_factory_authority.py` — a `check_validated_claims.py`-pattern grep gate that fails CI if any module on the Article-2 perimeter (`synapse.yml meta.article2_surfaces`: alert_triage, board_ordering, top_setups, attention_queue, push_floor) reads `data/research_factory/` or imports `engine.research_factory`; (c) `ci.yml` paths globs for `scripts/research_factory*.py`, `data/research_factory/**`, `tests/test_research_factory*.py` (engine/** already covers the package); (d) `synapse.yml` registration of the three durable ledgers at W1 with `tier: display`, `horizon_role: context`, `scored_path_surfaces: []` — registration is what arms the existing read-gate. (This does not conflict with FR-12: these are orchestration ledgers, not signal families. Any signal family the factory surfaces remains synapse-unregistered until it survives its own gates.)
- **RF-12 — Governance events.** Human-gate transitions and challenger completions append to `data/neuralweb/governance.jsonl` via the existing `governance.append_event()` signature, with `event_type` prefixed `research_factory_*` and `article: null` explicitly, so factory decisions are never mistaken for Article-3 authority grants.
- **RF-13 — Domain seams (binding).**
  - **Oracle:** ingest seam is `oracle_ingest_brainstorm.py` scratch-registry OUTPUT (never raw inbox JSON — inbox is gitignored scratch); mechanism text is captured from the original inbox JSON before the 8-field strip. The runner FORKS by track: reversion → `oracle_reversion_screen.screen_compound(gauntlet=True)` (read-only); 63d → `oracle_screen` (counted) then `oracle_gauntlet_compound`. Default factory mode is READ-ONLY observer of existing artifacts; invoking a counting screen requires explicit `--count` plus RF-6 satisfied. `promotion_queue.json` is read as screened-evidence; `search_width_at_scan` MUST appear in every Oracle review packet. The scratch registry is never committed to the live compounds registry by the factory.
  - **Cortex:** the factory NEVER registers, never writes `machine_registry.jsonl`, never bypasses the 3/week metabolism chokepoint. `source='cortex'` rows must carry the metabolism-issued id as `spec_ref` with registration timestamp ≥ metabolism's `registered_at`. The three-layer self-grading exclusion (`cortex_attention` refs) is re-checked before attaching any firings evidence. One-night cross-job lag (engine job reads prior night's cortex commit) is accepted and documented.
  - **Alpha grammar:** adapter reads `data/research/alpha_candidates.parquet` (BH-FDR survivors, `fdr_reject==True`) + `alpha_clusters.json`; tracks families and survivors, not formula noise. `net_new_info` stays cluster metadata — never a rank input (FR-1/FR-6 inherited).
  - **External/human:** `scripts/research_factory_report_pack.py` (modeled on `oracle_brainstorm_pack.py`) emits an operator-invoked extraction prompt pack with dedup context BAKED IN (species names, machine-registry hypotheses, trial families, and the NW_QUANT_SYNTHESIS §3 duplicate table as TEXT). The factory never auto-invokes any pack. LLM extraction output lands in an inbox; only the deterministic ingest script writes ledger rows.
  - **research_queue:** read `data/neuralweb/research_queue.json` (`high_ev_build_now` + operator-nominated) as an input; never recompute or replace its ranking.
- **RF-14 — Dedup law.** Deterministic-first, at ingest, in fixed order: (1) `data/oracle/compounds/registry.jsonl` (canonical rule-hash via `oracle_ingest_brainstorm._canonical`), (2) `data/species/registry.json` via `species_registry.load()`, (3) `data/neuralweb/machine_registry.jsonl` (absent-safe), (4) trial-ledger family strings. The NW_QUANT_SYNTHESIS §3 duplicate table is prose — it is embedded as TEXT in extraction/challenger prompts (satisfying FR-2 at the layer where it is usable) and never machine-parsed. Structural near-dup (common-subtree) produces a `near_dup_review` FLAG feeding the challenger — not an auto-reject (low-n real edges must not be silently killed; see memory: kills get scrutinized).
- **RF-15 — Respin law.** Lineage fields `respin_of`/`superseded_by` + `refinement_generation` live in the candidate schema from W1. Hard cap: **2** challenge→fix→re-screen cycles per lineage, cross-domain; generation 3 forces terminal `rejected`. A respin reuses the parent's trial family unless the entry-rule column set changes (that is the "material change" line), in which case it declares a new `rf.*` family citing the parent. Every re-screen is a new counted trial. This is the anti-p-hacking rail the 2025-26 agentic-alpha literature shows is always missing.
- **RF-16 — Rejected shapes (standing).** Inherited from the study §9 and prior rulings, all still binding: no autonomous trading; no LLM confidence scores; no arbitrary LLM codegen in this program (a codegen lane is a SEPARATE future program requiring an OS/identity-level boundary — contents:read PR-only runner + branch protection + CODEOWNERS on validators — per `SELF_IMPROVING_AI_SUITE.md` §0); no agent edits to `engine/validation.py`/gates/challenger prompts as part of factory operation; no factory influence on board rank/size/alert priority; no utility router; no fused "factory score" (review queue ranks by category bins + single declared metrics only); no cortex budget raise; no treating external posts as fact; no chat-state as ledger.

---

## 4. State machine v2 (canonical)

| State | Terminal | Entry actor class | Mandatory fields on entry | Allowed next |
|---|---|---|---|---|
| `proposed` | no | ingest (`script`/`codex`/`sonnet`) | source, candidate_type, hypothesis, mechanism | `schema_rejected`, `deduped`, `registered` |
| `schema_rejected` | yes | script | reason_code (`invalid_shape`,`grammar_invalid`,`mechanism_missing`,`illegal_authority`,`impossible_data`) | — |
| `deduped` | yes | script | matched entity id in reason | — |
| `registered` | no | script | candidate_id, trial_accounting, evaluation_plan (read back from domain gate) | `screened`, `awaiting_data`, `rejected` |
| `awaiting_data` | no | script | come_back_on + experiments-seed entry | `registered`, `screened`, `retired` |
| `screened` | no | script (engine artifact required) | artifact_refs (screen output / projection) | `challenged`, `numeric_rejected`, `awaiting_data` |
| `numeric_rejected` | yes* | script (deterministic floor) | kill_evidence | — (*requeue pointer for `underpowered_accruing`/`regime_change_suspect`) |
| `challenged` | no | script (packet exists) | challenge packet ref (probes + reviewer JSON) | `human_review` (unconditional) |
| `human_review` | no | script | review packet ref | `paper`, `deferred`, `rejected`, `scoped_build` |
| `paper` | no | **human** | seed entry, regime-at-entry, expected_half_life_d | `promote_eligible`, `human_review`, `retired` |
| `deferred` | no | **human** | come_back_on + seed entry | `human_review`, `retired` |
| `promote_eligible` | no | script (promotion_gate verdict) | promotion_gate artifact | `deferred`, `scoped_build`, `rejected` |
| `scoped_build` | yes | **human** | new program doc ref + governance event | — |
| `rejected` | yes | **human** | kill_evidence (+ respin lineage if applicable) | — |
| `retired` | yes | **human** | kill_evidence | — |

The transition helper (`engine/research_factory/state.py`) enforces: allowed-pair matrix, actor-class allowlist, mandatory-field presence, monotonic `as_of`, and the respin human-gate; the on-disk append-only discipline lives in `ledger.py`. Anything else raises `IllegalTransition`.

---

## 5. Schemas v1 (all rows carry `"authority": "display_only"`)

### 5.1 `research_factory.candidate.v1` — `data/research_factory/candidates.jsonl`

```json
{
  "schema": "research_factory.candidate.v1",
  "authority": "display_only",
  "candidate_id": "rf-20260706-oracle-washout_flow-001",
  "created_at": "2026-07-06T00:00:00Z",
  "source": "oracle_brainstorm|cortex|alpha_grammar|human|external_report|research_queue|domain_registry",
  "candidate_type": "oracle_compound|cortex_hypothesis|alpha_family|species|external_idea",
  "domain": "oracle|neuralweb|entry|factor|macro|options|china|us_stocks",
  "status": "proposed",
  "hypothesis": "specific falsifiable statement",
  "mechanism": "why this could persist (captured pre-strip for oracle inbox specs)",
  "claim_shape": null,
  "spec_ref": "domain id (oracle compound_id / metabolism id / alpha family) or inline path",
  "expected_failure_modes": [],
  "decay_conditions": [],
  "falsifiers": [],
  "trial_accounting": {"mode": "read_only", "family": null, "declared_at": null},
  "evaluation_plan": {"primary_metric": "<read back from frozen domain gate>", "horizon_d": 21, "min_n": 25, "fdr_scope": "batch", "expected_half_life_d": null, "defaulted": true},
  "lineage": {"respin_of": null, "superseded_by": null, "refinement_generation": 0},
  "flags": [],
  "artifacts": {},
  "transition_log": []
}
```

Notes: `evaluation_plan` is a READ-BACK of the domain's frozen gate (reversion: WR primary / asym / ret_exit; metabolism clamps min_n to ≥25; oracle 63d floors are the promotion-scan constants) — a candidate-authored divergence is a schema warning, not an instruction to the evaluator. `flags` carries probe outputs (`near_dup_review`, `mechanism_spec_mismatch`, `input_insensitive`, `recent_only_columns`, `scale_flagged`, `launched_hot`).

### 5.2 `research_factory.transition.v1` — `data/research_factory/transitions.jsonl` (append-only)

```json
{"schema": "research_factory.transition.v1", "authority": "display_only",
 "candidate_id": "rf-...", "from": "challenged", "to": "human_review",
 "reason_code": "challenge_packet_complete", "reason_text": "...",
 "actor": "script|codex|sonnet|fable|operator", "actor_ref": "session/PR ref (required for human actors)",
 "kill_evidence": null, "artifact_refs": [], "as_of": "2026-07-06T00:00:00Z"}
```

### 5.3 `research_factory.challenge.v1` — `data/research_factory/challenges/<candidate_id>.json`

```json
{
  "schema": "research_factory.challenge.v1",
  "authority": "display_only",
  "candidate_id": "rf-...",
  "challenged_at": "2026-07-06T00:00:00Z",
  "mechanical_probes": {
    "input_insensitive": false,
    "near_dup": {"score": 0.0, "nearest": null},
    "mechanism_spec_mismatch": false,
    "gauntlet_legs": []
  },
  "reviewer": {
    "agent_type": "reviewer",
    "recommendation": "ADVISORY_REJECT|ADVISORY_REVIEW|ADVISORY_PASS",
    "blockers": [{"severity": "blocker|major|minor", "category": "lookahead|parametric_lookahead|survivorship|overfit|cost|regime|mechanism|implementation|data|authority|duplicate", "finding": "...", "evidence_ref": "..."}],
    "non_blocking_concerns": [],
    "best_counterargument": "...",
    "minimum_fix_to_reconsider": null,
    "falsifier_spec": null,
    "human_review_question": "the exact question Fable/operator must decide"
  }
}
```

No confidence scores. `recommendation` is ADVISORY_* by name so no reader mistakes it for a gate. `falsifier_spec` (when emitted) must be compatible with `engine/falsifier_tripwires.py` so the paper monitor can grade the reviewer's specific ex-ante objection at maturity.

### 5.4 `research_factory.paper_monitor.v1` — `data/research_factory/paper_monitor.jsonl` (forward ledger, nightly-only)

```json
{"schema": "research_factory.paper_monitor.v1", "authority": "display_only",
 "candidate_id": "rf-...", "as_of": "2026-07-06",
 "paper_status": "warmup|operating|review|retire_recommended",
 "expected_metric": {"name": "<frozen domain gate metric>", "value": 0.58, "source": "domain_gate"},
 "observed_metric": {"name": "...", "value": 0.51, "n": 42},
 "expected_fire_rate_pm": "not_applicable",
 "observed_fire_rate_pm": null,
 "regime_at_entry": {"regime": "risk_on", "vix_pctile": 34, "launched_hot": false},
 "falsifier_ref": null, "falsifier_verdict": null,
 "data_health_flags": [], "decay_flags": [],
 "action": "continue|review|retire_recommended",
 "note": "display-only; no scored-path authority"}
```

`expected_*` fields are populated from the domain's frozen gate at registration — never authored. `not_applicable` sentinel, never a phantom null baseline. The monitor recommends; retirement is human-authored (RF-5).

### 5.5 `research_factory.health.v1` — `data/research_factory/health.jsonl` (forward ledger, nightly-only)

Funnel counts per state, kill-reason histogram by `reason_code`/`kill_class`, challenger advisory distribution vs human decisions (rubber-stamp detector), median dwell days per state, respin-generation histogram, per-source acceptance rates. Computed solely from `transitions.jsonl` + `candidates.jsonl`.

---

## 6. Waves

Each wave = one PR, branched off fresh `origin/main`, built by a Sonnet `builder` agent, adversarially reviewed by an Opus `reviewer` agent (must return APPROVE), same-day squash-merged. Tests are fixture-based (no heavy data), absent-file-safe. Pure-stdlib for `engine/research_factory/` core (match `trial_ledger.py`'s rule).

### W1 (PR-2) — Engine core + the authority mechanism
- `engine/research_factory/__init__.py`, `schema.py` (validators for §5 schemas incl. required `authority` field, `rf.*` family regex, actor-class table), `state.py` (transition helper enforcing §4), `ledger.py` (append-only JSONL read/write, keep-first helpers).
- `scripts/check_research_factory_authority.py` + wiring into `ci.yml` (new job or alongside synapse-read-gate).
- `ci.yml` paths globs: `scripts/research_factory*.py`, `data/research_factory/**`, `tests/test_research_factory*.py`.
- `config/synapse.yml`: register `candidates.jsonl`, `transitions.jsonl`, `paper_monitor.jsonl` (`tier: display`, `horizon_role: context`, `scored_path_surfaces: []`, `cadence: manual` until W6 flips monitor to nightly). Coordinate same-day merge (synapse/dag drift law).
- `.gitignore`: broad exclude `data/research_factory/*` + explicit negations for the six durable artifacts.
- `tests/test_research_factory_state.py`, `tests/test_research_factory_schema.py`: invalid transitions rejected; actor-law violations rejected (no `script` actor into `paper`/`rejected`/`retired`/`scoped_build`/`deferred`); `screened` refused without trial accounting; schema round-trips.
- Exit gate: full pytest green locally; authority guard demonstrably fails on a planted violation in a test fixture.

### W2 (PR-3) — Ingest, dedup, health
- `scripts/research_factory_ingest.py`: sources = manual JSON proposals, oracle scratch-registry output (+ mechanism capture from original inbox), `research_queue.json` (`high_ev_build_now` + `--nominate`). Deterministic dedup per RF-14; structural near-dup flag; mechanism↔spec alignment flag; `rf.*` family declaration hook.
- `scripts/build_research_factory_health.py` (manual now, nightly at W6).
- `tests/test_research_factory_ingest.py` with fixtures for each source + dedup collisions.
- Exit gate: dry-run ingest of ≥1 manual and ≥1 oracle fixture; every drop has a recorded reason.

### W3 (PR-4) — Domain runner adapters
- `engine/research_factory/adapter_oracle.py` (two-track fork per RF-13; read-only default; `--count` explicit; promotion-queue read; `search_width_at_scan` capture), `adapter_cortex.py` (pointer/projection only; absent-file-safe; self-grading exclusion re-check), `adapter_alpha_grammar.py` (parquet survivors read).
- `scripts/research_factory_run.py` with `--dry-run` listing planned actions.
- `tests/test_research_factory_adapters.py` (mocked evaluators; projection mapping tests; refuse-rescreen test).
- Exit gate: dry-run lists correct routing for fixtures of all three domains; no adapter duplicates an evaluator.

### W4 (PR-5) — Challenger + external intake
- `engine/research_factory/probes.py` (mechanical layer per RF-7a), `challenge.py` (packet build + reviewer-JSON validation + RF-7 transition wiring).
- `scripts/research_factory_challenge_pack.py` (emits packet; operator/Fable runs the reviewer agent; validates response JSON; bad JSON does not transition).
- `research/research_factory/CHALLENGER_PROMPT.md` (lens-structured: PIT/lookahead, statistics, mechanism/decay, cost/capacity/duplicate, authority; outcome-blind instructions; NW_QUANT_SYNTHESIS §3 table embedded as text).
- `scripts/research_factory_report_pack.py` (external-report extraction pack per RF-13).
- `tests/test_research_factory_challenge.py`.
- Exit gate: packet generated for ≥1 real Oracle candidate; malformed reviewer JSON rejected without transition.

### W5 (PR-6) — Review queue + decision recorder
- `engine/research_factory/review_queue.py` + `scripts/build_research_factory_review_queue.py`: JSON + Markdown packets — hypothesis, mechanism, frozen-gate metrics, probe flags, reviewer blockers, `search_width_at_scan` (Oracle), crowding context (`crowds_with` — per-candidate context, never a composite rank), the exact decision question, allowed decisions.
- `scripts/research_factory_decide.py`: records human decisions → transitions (actor law enforced), governance `research_factory_gate` events (`article: null`), experiments-seed entries for `paper`/`deferred`.
- `tests/test_research_factory_review.py`.
- Exit gate: queue builds from fixture ledger; decisions round-trip; seed entry written for a `paper` decision.

### W6 (PR-7) — Paper monitor + retirement + nightly wiring
- `engine/research_factory/monitor.py` + `scripts/research_factory_monitor.py` (`--dry-run` default off-nightly; forward-ledger discipline per RF-8; regime-at-entry stamping; falsifier grading via `falsifier_tripwires` when `falsifier_ref` present; decay flags; `retire_recommended` routing to human review; requeue pointers per RF-10). Health builder goes nightly here too.
- `daily.yml` engine-job step AFTER `build_nw_mastermind_context`, non-fatal `|| echo '::warning::...'` pattern; `config/dag.yml` lane entry in the SAME PR; NOT in `render.yml`; one-night cortex lag documented in module docstring.
- `tests/test_research_factory_monitor.py` (warmup, absent-data, keep-first, dry-run writes nothing).
- Exit gate: dag-conformance green; monitor handles all absent upstream files; retirement leaves history intact.

### W7 (PR-8) — Batch A: Oracle reversion, read-only
- Ingest existing Oracle registry compounds + promotion-queue rows (READ-ONLY: no new counted trials in batch 1); run probes; generate challenge packets for the top ≤5 numeric survivors; Opus reviewer packets; Fable adjudicates each via `research_factory_decide.py`; commit first real ledger rows + health snapshot; update §0 status log with PR numbers.
- Success criteria (from the study, kept): every drop has a reason; the challenger kills at least one attractive numeric mirage OR documents why none died; review packets adjudicate faster than raw screen output; zero writes to any domain registry.
- Batch B (cortex) is DEFERRED until `machine_registry.jsonl` has real rows — there is nothing to wrap today.

### Deferred (separate future programs, each needing its own ruling)
- W-CODEGEN: arbitrary strategy codegen behind an OS/identity boundary (contents:read PR-only runner, branch protection, CODEOWNERS on `engine/validation.py` and gates).
- W-AUTO: scheduled LLM extraction/challenge batches + cost telemetry — only after Batch A proves the loop and only via service-key (not user-OAuth) identity.
- Committee-page visibility for paper metrics (admin-only until then; if ever surfaced, extend `check_validated_claims.py` SCAN_GLOBS to those templates).

---

## 7. Risk register (delta over the study §12)

| Risk | Mitigation now in law |
|---|---|
| LLM authority creep via categorical recommendation | RF-5/RF-7: advisory-only, unconditional flow to human queue, actor allowlist enforced in code |
| Silent-green CI on factory paths | RF-11c: paths globs land in W1 with the first code |
| Two sources of truth for status | RF-2 projection law; on conflict domain registry wins |
| Trial-ledger pollution / double counting | RF-6 family regex + refusal gate; cortex shared family; oracle counted-by-screen |
| Respin p-hacking loop | RF-15 generation cap 2 + counted re-screens |
| Kill laundering (regime-change read as falsification) | RF-10 kill_evidence + kill_class + human-armed requeue |
| Parallel clock drift | RF-9 experiments-seed as the only clock |
| Reviewer memorized-outcome leakage | RF-7 outcome-blind prompt + `parametric_lookahead` category + mechanical probes pre-computed |
| Governance ledger poisoning | RF-12 `research_factory_*` event types, `article: null` |
| Rubber-stamp human gate | §5.5 health ledger tracks advisory-vs-decision divergence |

---

## 8. Answers of record (supersedes study §13)

1. Name/home: `engine/research_factory/`, charter at `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`. 2. W1 domains: Oracle + manual JSON; cortex + alpha grammar adapters in W3 (cortex batch deferred until registrations exist). 3. Git-track from first row (reverses the study). 4. Challenger minimum: mechanical probes + advisory reviewer packet, categorical only. 5. Synapse registration at W1 (reverses the study; registration IS the enforcement). 6. Factory reads the queue as input, never governed by it. 7. First batch: Oracle reversion, read-only. 8. Decision vocabulary: `paper|deferred|rejected|scoped_build`. 9. Paper-monitor artifacts admin-only. 10. Lines that must not be crossed before a separate risk-accepted program: arbitrary codegen; validator/gate edits; scored/sizing influence; scheduled autonomous LLM invocation.

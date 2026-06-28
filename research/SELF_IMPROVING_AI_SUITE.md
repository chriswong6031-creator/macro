# Self-Improving AI Suite — Institutional Blueprint

*Status: design (2026-06-21). Builds on the 4-phase "close the loop" plan. Produced via a recon → research → design → adversarial-red-team workflow and amended against the red-team findings. Display-only doctrine preserved; capital actions keep a human boundary.*

---

## 0. Honest verdict (read this first)

The dashboard is **~80% of a self-managing (MAPE-K) loop on the plumbing** (MONITOR / EXECUTE) but **~10% on the one axis that makes autonomous discovery safe — honest trial accounting.** Until that lands, an autonomous discover-and-tune loop with feedback is *structurally a p-hacking machine with a green light.*

Two structural facts the red-team verified change the sequencing:

1. **`deflated_sharpe` today takes a literal `n_trials`** (`engine/validation.py:132`). Honest multiple-testing accounting is a *convention every script must remember*, not an enforced invariant. This must become an enforced contract before any discovery merges.
2. **The nightly job runs with `contents: write` and pushes straight to `main`** (`.github/workflows/daily.yml:8`). So "Opus is mechanically denied write access to the evaluator" is **currently false** — an in-process Python allowlist is defeatable by any bug or prompt-injection. The boundary must be OS/identity-level (separate `contents:read` PR-only runner + branch protection + CODEOWNERS), not code.

**The realistic payoff** is better **capital-efficiency and drawdown control**, *not* new return-alpha. The alpha audit already found residual-momentum IC DSR-fails and entry-timing has negative return-correlation. The evolutionary loop is honestly only pointed at the drawdown/MAE **entry-ordering** objective where edge demonstrably exists. Expecting it to discover return-alpha repeats the exact trap the audit exposed.

---

## 1. Autonomy doctrine

Autonomy is **earned per-signal by a deterministic, fail-closed gate, tiered to materiality** (SR 11-7 proportionality) — never asserted. The gate earns autonomy *only because it is strictly harder to game than a rubber-stamp*: pre-registration with logged knowledge-cutoff, CPCV on a symmetric purge, Deflated Sharpe deflated by an honest effective-N from a persistent Trial Ledger, PBO via CSCV, BH/Romano-Wolf at the ~3.0 t-stat bar, Minimum-Regime-Performance with non-overlapping-episode counts, a deterministic non-LLM leakage battery, post-cutoff LIVE confirmation, and an Opus red-team veto whose recall is measured.

**The human boundary sits at four seams** (two forced by the red-team):

1. Any **scored/sizing axis** or Mastermind buy gate.
2. Any change to the **evaluator** (`validation.py` / calibrate harness), the **Holdout Vault**, the **gate config**, or the **red-team prompt** — Opus is denied via OS/identity controls, not a Python allowlist.
3. The **ANALYZE/PLAN judgment for Tier-1** promotions.
4. Any promotion touching a **`site/*.json` feed the sibling Mastermind consumes** as a capital lens.

Everything below — MONITOR, EXECUTE, and PLAN for display-only-and-unconsumed legs — is automated, behind a **synchronous pre-write** source-health/drift gate that blocks a bad promotion *at write-time* rather than alerting the next morning.

**"Zero human intervention" is not achievable or advisable for a financial system.** The defensible claim is: *"zero human intervention for display-only research surfaces that no capital system consumes, behind a deterministic gate, with a named human owner who re-attests the validation standard."*

---

## 2. Where Opus / Claude OAuth plugs in

Mechanism (verified): the LLM layer is already **provider-agnostic** (`config.yml:1990` documents the one-line swap to `claude-opus-4-8` + `ANTHROPIC_API_KEY`). All five LLM engines (`master_brain`, `ai_desk`, `policy_intent_desk`, `catalyst_stock`, `catalyst_tone`) instantiate `anthropic.Anthropic(...)` directly and are gated + degrade-never-raise. **Use a service-account `ANTHROPIC_API_KEY`, not a headless OAuth token** — a user OAuth token cannot refresh in CI and will silently die on expiry.

| Site | Opus role | What it does | Hard guardrail |
|---|---|---|---|
| `desk_scorer.py` CoVe pre-screen (P2) | **judge** (cheap; Haiku/DeepSeek, not Opus) | Grades narrative coherence / economic plausibility for *non-computable* judgments only, position-swapped + ensembled | Never scores anything computable — the backtest is truth. Noisy soft-score, never sizing, never the gate. |
| `scripts/promote.py`, after the numeric gate (P4) | **adversarial reviewer** (veto-only) | Separate Opus instance hunts lookahead/leakage/survivorship/PIT/metric-gaming; structured veto with line-level evidence | A **deterministic non-LLM leakage battery runs and blocks first**; Opus is a *supplement*; its leak-recall is measured via planted leaks and published. Veto-only. Its prompt is human-write-only. |
| `engine/evolve/generator.py` (P5) | **code generator** (depth) | Authors candidate signal transforms as diffs to fenced `EVOLVE-BLOCK` regions, seeded by the MAP-Elites archive + a pre-registered rationale | Runs on a separate `contents:read` PR-only runner in a gVisor sandbox (default-deny egress, writable-path allowlist); **every** enumerated candidate logged to the Trial Ledger at *generation*; blind to the vault; forbidden from return-alpha. |
| `engine/meta_optimizer.py` (P6) | **meta-optimizer** | Weekly: reads the calibration dashboard and *proposes* the next lever (retire leg X, explore niche Y, test conviction floor Z) | A proposal never self-applies — it becomes a challenger through the full P4 gate. Retirements clear a *symmetric* bar. Excluded from optimizing any evaluator/challenger/gate artifact. |
| `scripts/research_run.py` (**deferred** post-v1) | **autonomous researcher** | Bounded multi-step investigations; writes analysis as diffs, runs in sandbox, reflects, emits a cited findings doc | Hard orchestration-layer budget (aborts at ceiling; **fail-closed if telemetry unavailable**); durable checkpointing; findings are claims, candidates face the gate. |

---

## 3. The upgraded phase suite

Build in **strict dependency order**. P1–P4 + P8 *is the real deliverable* for a financial system.

### P1 — Shared falsifiable eval-loop (`desk_scorer`) · effort M
Extract `ai_desk_scorer.py` → `engine/desk_scorer.py` with a pluggable predicate registry; point `master_brain`, `policy_intent_desk`, `catalyst_stock` at it. Each emits `{subject, lean, conviction, horizon, falsifier.check, check_by, entry_levels, info_cutoff}` and reads a **regime-broken-down** `track_record` back. *(Note: `altdata_brain.py` does not exist here — the alt-data scored axis lives in `engine/altdata_models`.)*
**Gate:** plumbing; `track_record` stays context-only. **Kill-switch:** per-brain `config.enabled`; degrade-never-raise.

### P3 — Trial Ledger + Holdout Vault + honest-N · **HARD BLOCKING PREREQUISITE** · effort M–L (~300 LOC, real research)
Change `deflated_sharpe`'s **contract** to forbid a caller-supplied `n_trials` and require a ledger handle + signal-family id; compute effective-N inside `validation.py` from append-only `data/trial_ledger.jsonl`. Effective-N is fail-closed: correlation-collapse may only ever *raise* the haircut, hard floor `effective-N ≥ sqrt(literal-N)`. **Count trials at GENERATION** (incl. DeepSeek breadth fan-out + in-context enumerations), not at backtest. Vault reads are **irreversible + content-hashed**; a failed read permanently retires the hypothesis id; every prior peek counts into effective-N. Pre-registration required before any backtest. Log model knowledge-cutoff per signal.
**Files:** `engine/trial_ledger.py`, `engine/validation.py` (signature change + block-effective-T correction), `data/trial_ledger.jsonl`, `data/vault/` (read-only mount), `scripts/promote.py`, `tests/test_no_literal_ntrials.py` (**CI fails build if any script passes a literal `n_trials`**).
**Why first:** without this, the discovery loop is a p-hacking machine. Prove it by re-running 2–3 phase0 scripts through the ledger and showing DSR drops materially.

### P2 — Reflection + calibration + drift bus (read-only, parallel to P3) · effort L
CoVe entailment gate (each LLM claim must be entailed by a computed field or dropped); 3-channel drift bus (input PSI/KS, rolling-IC, calibration-ECE) with **ADWIN + Page-Hinkley** concept-drift detectors; Platt/isotonic recalibration (reuse `brier_reliability`/`platt_fit`); surfaced on `site/calibration.html`. **Add an out-of-band frozen benchmark canary** scored by code that does *not* change with calibration, plus a meta-behavior monitor (promotion rate, conviction-flip rate) — because the drift detector and regime tagger share an upstream with the signals they grade.
**Gate:** drift ALARM is a circuit breaker, not an auto-action — recalibration is *proposed*, not auto-applied.

### P4 — CPCV/PBO champion-challenger harness + synchronous pre-write gate · effort L
Build **CPCV on the symmetric purge already proven in `engine/meta_label.py:_train_events`** — NOT on `validation.py:purged_folds` (trailing-edge embargo only → would silently leak the test fold's left boundary). Add PBO via CSCV; Minimum-Regime-Performance **with an explicit non-overlapping-episode count** (single-episode cell = automatic FLAG, not PASS; regime labels version-pinned); BH + Romano-Wolf at the ~3.0 t-stat bar. Promotion = versioned-calibration swap. **Critical:** a **synchronous pre-write gate inside `scripts/promote.py`** (before `git add site/`) that reads `run_status.json` source-health + the drift bus and *refuses* the swap if degraded — because `heartbeat.yml` runs 16h later with `contents:read` and cannot freeze an already-shipped promotion.

### P8 — Registry + identity boundary + real cost telemetry · co-requisite of P4 (front-load a slice FIRST) · effort L
1. **Identity boundary** (the real "mechanically denied"): a separate `contents:read` PR-only discovery workflow; branch protection + CODEOWNERS on `validation.py` / vault / gate-config / red-team-prompt; vault + ledger on a token-unwritable mount.
2. **Real cost telemetry**: close the verified gap (`admin/ai_cost.py:3` logs *no* token counts) by reading `resp.usage` into `data/llm_usage.jsonl` + OTel-GenAI spans; a **hard orchestration-layer budget** (running USD/call counter; job aborts at ceiling; **fail-closed if telemetry missing**).
3. **Registry**: each model = `{id, tier, current_version, challenger, promotion_history, validator_signoff, model_cutoff_date, mastermind_consumed}`; v1 uses a simple versioned-blob + `current_version.txt` (defer the alias import-refactor); a dependency map of which `site/*.json` feed Mastermind, auto-escalating those promotions to Tier-1.
**This is where the staged-autonomy ladder lives.**

### P5 — Opus evolutionary signal discovery (sandboxed, PR-only) · **NEW CAPABILITY CLASS** · effort XL
AlphaEvolve/OpenEvolve loop: Opus (depth) + DeepSeek (breadth) author diffs to `EVOLVE-BLOCK` regions, scored by the existing backtest + the P4 gate, kept in a **MAP-Elites** archive binned by regime/sector/horizon/turnover/drawdown. **Pointed exclusively at machine-gradeable drawdown/MAE entry-ordering objectives — forbidden from return-alpha.** Split: P5a (loop + numeric gate, red-team OFF), P5b (red-team veto ON), P5c (deferred). Runs as an **isolated weekly workflow**, decoupled from the 40–70min nightly job. The novelty objective is *forbidden from rewarding de-correlation that would feed a lower effective-N* (closes the self-eval gaming vector). **Candidate for deferral — stopping after P4 already yields a governed, honest system.**

### P6 — Opus meta-optimizer + autonomous researcher (diagnostic layer first) · effort L
`meta_optimizer.py` reads dashboards → `tuning_proposals.jsonl` `[PROPOSED]`, each becoming a challenger through the full P4 gate. **v1 = diagnostic/proposal layer only.** Prompt-optimization (OPRO/GEPA) and the autonomous researcher are **deferred** (highest cost-to-value; the prompt-optimizer specifically must never touch the red-team/gate-config prompts — the exact independence the gate-replaces-human argument depends on).

### P7 — Regime-scoped memory + soft leg weights (last) · effort M
Reflexion lesson memory scoped to regime (expires on regime flip) + a mandatory complete negative-result log. Optional Thompson-sampling soft weights **only on P4-gated legs, bounded ±[0.8,1.2], disabled by default**. Regime-label version pinned in lineage; its stability is a monitored drift channel. Deferred until the live ledger holds ≥50 legs + a 6-month track record.

---

## 4. Cross-cutting institutional systems

- **Trial Ledger with fail-closed effective-N** — append-only, counted at generation; a `deflated_sharpe` whose signature forbids a literal `n_trials`; a global alpha/FDR budget across all phases; a periodic **re-deflation** job that re-scores already-promoted signals against the grown ledger-N.
- **Holdout Vault (irreversible, content-hashed)** — sealed final window; each read writes a permanent signed record; a failed read permanently retires the id; every peek counts into effective-N (closes the re-seal "restart-the-clock" hole).
- **Identity/permission boundary (OS-level)** — separate `contents:read` PR-only runner; branch protection + CODEOWNERS on the evaluator/vault/gate-config.
- **Deterministic leakage battery + measured red-team recall** — label-shift +1 ablation, future-data zeroing, planted-leak CI canary; run *before* the Opus reviewer; Opus leak-recall published.
- **Sandboxed PR-only execution path** — gVisor/runsc + seccomp + iptables default-deny egress + writable-path allowlist; objective-integrity floors + perturbed CPCV fold boundaries defend the gate's own metric definitions.
- **Synchronous pre-write promotion gate** — refuses any calibration swap on degraded sources / drift ALARM, before publish.
- **Real cost telemetry + hard budget kill** — `resp.usage` logged; running USD counter aborts at ceiling; loops refuse to start if telemetry unavailable.
- **Cross-repo capital seam contract** — version-pin every `site/*.json` Mastermind consumes; a registry dependency map auto-escalates consumed-feed promotions to Tier-1; Mastermind quarantines newly-autonomous legs until human-acknowledged.
- **Knowledge-cutoff as a first-class leakage axis** — pre-cutoff "confirmation" is the model *recalling* memorized anomalies, not predicting; suggestive-only, cannot graduate past SHADOW.

---

## 5. Autonomy-safety framework

**Staged-autonomy ladder** (per-model, recorded in the registry; a model *never* starts above SHADOW):
1. **SHADOW** — emits to `data/evolve/` only, scored, not surfaced; all trials counted; pre-cutoff "confirmation" can never leave this rung.
2. **CANARY (display-only)** — surfaced as unscored context after **5 consecutive green LIVE-ledger windows** (post-cutoff evidence).
3. **AUTO-PROMOTE-WITHIN-BOUNDS** — a display-only-AND-Mastermind-unconsumed leg that cleared the gate + **20 green live windows** + explicit human review may self-promote to a scored context leg within bounded weight ranges.
4. **FULL-AUTO** — only specific low-risk task classes (additive panels, doc edits, non-sizing non-consumed recalibration).

**Circuit breakers:** concept-drift ALARM → conviction drop; synchronous pre-write block on degraded sources; hard budget abort (fail-closed if no telemetry); spend spike >2.5× warn / >5× halt; sandbox wall-clock/CPU/mem kill; irreversible vault read; post-promotion live-ledger degradation → automatic version rollback; broad-outage (≥8 sources) → freeze promotions; out-of-band frozen benchmark + meta-behavior monitor alarming independently of self-reported metrics.

---

## 6. Priority path

**First move (single highest-leverage):** change `engine/validation.py:deflated_sharpe`'s contract to **forbid a caller-supplied `n_trials`** and require a Trial Ledger handle, and land a CI test that fails the build if any script passes a literal `n_trials`. This converts the honest-N doctrine from a convention into an enforced invariant — the precondition the entire autonomy argument rests on.

**Then:** P1 (shared `desk_scorer`, low-risk) → P3 (Trial Ledger + irreversible vault + honest-N, **hard blocking**) with P2 (read-only drift/calibration telemetry) in parallel → the P8 slice delivering **real cost telemetry + the OS-level PR-only identity boundary BEFORE any agent exists** → P4 (CPCV on the symmetric purge + synchronous pre-write gate).

**STOP AND OPERATE HERE.** This is a governed, honest, auditable champion-challenger system with no code-writing agent and no new execution surface. Only after it runs stably with **20–30 decided outcomes** in the ledger, *separately risk-accept* P5 (sandboxed, PR-only, red-team OFF first, drawdown/MAE only), then P6 diagnostic layer, then P7 with Thompson disabled by default. **Stopping after P4 is not a failure — it is probably the correct answer.**

---

## 7. Hard truths to accept

- "Zero human intervention" → stop claiming it; the honest scope is display-only-and-unconsumed surfaces behind the gate, with a named owner re-attesting the standard.
- You are ~80% there on plumbing, ~10% on honest trial accounting. Until P3 lands with the enforced signature change, the system is structurally a p-hacking machine and P5/P6 must not exist even in shadow.
- P5/P6 are a **separate, separately-risk-accepted program**, not phases of the same project — they introduce the first code-writing, code-executing, self-promoting agent into a repo that has none today.
- Pre-registration by an LLM that memorized the anomaly literature is *recall, not an independent prior*. The only real defense is **post-cutoff live confirmation** — genuine discovery is therefore slow.
- The gate cannot make alpha appear where there is none. Point the loop at drawdown/MAE/entry-ordering, where edge exists.
- The most dangerous gap is environmental, not statistical: the nightly job pushes straight to `main` with write access. Fix the identity boundary before P5, full stop.
- The capital seam you most need to control lives in a repo this design cannot touch (the sibling Mastermind, no git remote) — a cross-repo coordination cost, the thing most likely to silently rot.

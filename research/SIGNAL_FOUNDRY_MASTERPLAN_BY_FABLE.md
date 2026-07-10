# The Signal Foundry — autonomous signal brainstorming & testing loop (masterplan, by Fable)

**Status:** ratified 2026-07-10 · build program active · scheduled lane ships DARK (operator arms)
**Program owner:** Fable (main loop) · **Surfaces:** `engine/signal_foundry/`, `data/signal_foundry/`, Foundry section of `site/signal_lab.html`
**Companions:** `research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md` (metabolism — separate program, separate files), CHF (`config/causal_llm.yml` lane — the legal precedent this mirrors)

## 1. Mission

The dashboard's signal pipeline is bottlenecked at exactly one place: **every** step from idea → frontier docket → phase-0 harness → report → Signal Lab registry is hand-done. The frontier docket (60 SLF candidates) and the registry (65 rows) are static Python. The Foundry closes the loop *mechanically* while keeping every constitutional line intact:

> **machine proposes → deterministic screen admits → frozen harness tests → results display → human promotes.**

The endgame is the standing directive ([[context-accrual-fundamental-goal]]): amass tested trader context. More constructions tested per week, nulls printed and retained as confluence inputs, kills logged as construction-specific — at near-zero marginal human cost.

## 2. Constitutional compliance (read first)

| Standing law / ruling | How the Foundry complies |
|---|---|
| **Article 1 / A7 ORIGINATE ban** — no LLM may originate a signal, score, or escalation | Foundry output is **proposal/test/display tier only**. Nothing it produces is wired to any rank/size/gate/score. Promotion to any authority tier requires human (Fable/operator) adjudication **plus** the standard gauntlet. The Foundry cannot write to `engine/` — it writes only `data/signal_foundry/**`. |
| **Gauntlet = promotion gate, not build gate** | Foundry candidates ship display-tier freely; nulls never block accrual; the gauntlet applies only at human promotion. |
| **Machine trials = own FDR family** (cortex hypothesis-metabolism ruling) | All Foundry runs log to trial-ledger family `signal_foundry`; BH-FDR is computed **within** that family only. Machine volume can never raise the discovery bar for human programs. |
| **as_of strictly after registration** | Backtest battery is screening-tier (same as CHF batteries). The **forward ledger** — the only evidence admissible at promotion — accrues exclusively on data dated after the spec's `registered_at`. True OOS by construction. |
| **W-AUTO deferral + CHF-R8 (OAuth-only scheduled identity)** | The scheduled brainstorm lane ships **dark**: `auto_loop: false` in `config/signal_foundry.yml` AND `SIGNAL_FOUNDRY_PAUSED` fail-closed (unset ⇒ paused; only the exact string `false` arms). Scheduled LLM calls are OAuth-only (`CLAUDE_CODE_OAUTH_TOKEN`), mirroring `scripts/run_causal_brainstorm.py`. Operator arms by ruling. |
| **R-AUT-1 two-key pattern** | An LLM proposal is filed **only if** the deterministic screen (dedup + DO_NOT_REBUILD blocklist + data-contract gates) independently admits it. LLM grant alone admits nothing. |
| **No agent edits to validation/gates** (research-factory ruling) | The LLM emits **declarative specs**, never harness code. The battery (`engine/signal_foundry/harness.py`) is frozen, human-reviewed code on top of `engine/validation.py`. The machine picks inputs; it can never touch the ruler. |
| **RF-16 — no LLM numeric confidence** | Foundry surfaces show measured statistics only; no LLM-asserted confidence numbers anywhere. |
| **No "validated" vocabulary** (CI: `scripts/check_validated_claims.py`) | Foundry verdict grammar: `pass_candidate / null / era_specific / unstable / insufficient_power / insufficient_history / data_missing / forbidden / error`. Never "validated". |
| **Nightly = sole advancer of forward ledgers** | Forward accrual runs as a nightly engine-job step. The weekly Foundry workflow (brainstorm + harness) is off-render and commits only `data/signal_foundry/**`. |
| **DT-R14 / time-preserving nulls** | Panel constructions use within-date demeaning + episode-label permutation; effective N counted in calendar months, never ticker-rows. |

## 3. Architecture — six stages

```
SEED (deterministic)      harvest structured seeds: causal_mechanisms.jsonl (screened_candidate
  │                       edges), causal_frontier.json rankings, surprise queue, research-factory
  │                       alpha_family candidates, Signal Lab killed rows (construction-specific
  │                       kills = open search space), stale frontier entries.
  ▼
BRAINSTORM (LLM, weekly)  three-model chain (mirrors run_causal_brainstorm.py):
  │                       generator=sonnet proposes SF-xxx candidates from seeds + the data
  │                       inventory manifest; skeptic=opus red-teams (novelty, identification,
  │                       data reality, confound); compiler=haiku emits strict JSON.
  ▼
SCREEN (deterministic)    7-gate screen (ported from signal_frontier_docket.screen_candidate) +
  │                       dedup vs REGISTRY/CANDIDATES/prior SF ids (construction hash) +
  │                       DO_NOT_REBUILD blocklist (config/signal_foundry_blocklist.yml) +
  │                       tracked-data-only contract. Two-key: LLM grant AND screen admit.
  ▼
SPEC (pre-registration)   admitted candidates become frozen declarative specs with
  │                       PRE-REGISTERED gates; spec is logged to trial ledger
  │                       (family=signal_foundry) BEFORE any run. registered_at stamped.
  ▼
RUN (frozen harness)      engine/signal_foundry/harness.py executes the standard battery
  │                       (NW HAC t, split-half, era split, block bootstrap, time-shift +
  │                       negative-lag placebos, permutation nulls, DSR with live family
  │                       n_trials, cost-aware backtest vs declared baseline). Weekly cap.
  ▼
FILE + ACCRUE (display)   results → data/signal_foundry/results/<id>.json → Foundry section of
                          signal_lab.html. pass_candidates enter the PROMOTION DOCKET (human-
                          only). Forward ledger accrues nightly on as_of > registered_at.
```

## 4. The spec schema (what the LLM is allowed to say)

```json
{
  "id": "SF-0001", "name": "...", "name_zh": "...",
  "market": "US macro", "thesis": "...", "mechanism": "...",
  "seed_provenance": {"source": "causal_mechanisms.jsonl", "ref": "<edge id>"},
  "data": [{"path": "data/archive/BAMLH0A0HYM2.parquet", "column": "value", "pit": "proxy"}],
  "feature": {"pipeline": [["zscore", {"window": 252}], ["lag", {"n": 1}]]},
  "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
  "universe": "single_series",
  "baseline": "buy_and_hold",
  "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
  "horizon_role": "swing", "registered_at": "2026-07-10"
}
```

- `feature.pipeline` draws only from the **whitelisted transform vocabulary** (`engine/signal_foundry/transforms.py`): zscore, pctile_rank, diff, pct_change, sma, ema, ratio, spread, lag, sign, clip, rolling_corr, rolling_vol, drawdown — every transform causal by construction (past-only windows), property-tested for no-lookahead.
- `data[].path` must be a **tracked** store (gitignored/runner-local stores are refused — [[untracked-store-absent-in-worktree]]).
- `target.kind` ∈ {excess_return, absolute_return, drawdown_onset, forward_vol} — each with a fixed, frozen scoring recipe.
- Gates are pre-registered and immutable once filed; the harness refuses a spec whose gates changed after registration (hash check).

## 5. Rulings (SF-R series)

- **SF-R1** — Foundry is proposal/test/display tier only. No Foundry artifact may be read by any scoring/ranking/gating code path. Promotion = human adjudication + gauntlet, never automatic.
- **SF-R2** — The LLM emits specs, never code. The battery is frozen; changes to `engine/signal_foundry/harness.py`, `transforms.py`, or gate semantics require a human-authored PR.
- **SF-R3** — `signal_foundry` is its own trial-ledger family and its own BH-FDR family. Foundry volume never tightens (or loosens) any human program's bar.
- **SF-R4** — Pre-registration: spec + gates logged to the trial ledger before first run; forward-ledger evidence only on `as_of > registered_at`; forward evidence is the only admissible basis at promotion.
- **SF-R5** — Ships dark. `SIGNAL_FOUNDRY_PAUSED` fail-closed (unset ⇒ paused) AND `auto_loop: false`. Scheduled identity = OAuth-only. Operator arming is a logged ruling. In-session manual runs by Fable/operator are legal at any time (existing research practice).
- **SF-R6** — Budgets (config, enforced in code): ≤ 5 filed candidates/week from brainstorm; ≤ 10 harness runs/week; wall-clock cap 30 min/run job; USD/token caps on the LLM chain. Idempotent per ISO-week (re-runs no-op).
- **SF-R7** — Two-key admission: deterministic screen (dedup, blocklist, data contract, sample ≥ 5y, baseline named) must independently admit every LLM proposal. Screen code is deterministic and LLM-free.
- **SF-R8** — Dedup by construction hash (family + feature pipeline + target + horizon) against REGISTRY, frontier CANDIDATES, all prior SF specs, and DO_NOT_REBUILD entries. A kill closes the construction tested; a *different* construction on the same theme is admissible (house law) unless the blocklist forbids the theme outright.
- **SF-R9** — Verdict grammar is closed (`pass_candidate | null | era_specific | unstable | insufficient_power | insufficient_history | data_missing | forbidden | error`). Nulls are retained as confluence inputs and stay on the page; the graveyard is content, not embarrassment.
- **SF-R10** — Write fence: the Foundry writes only `data/signal_foundry/**` (plus its rendered section via the normal site builder). It never edits `engine/`, `config/`, `scripts/`, workflows, or any ledger it does not own. Narrow commits only.
- **SF-R11** — Panel specs use time-preserving nulls (within-date demeaning, episode-label permutation, effective-N in months) per DT-R14 case law.
- **SF-R12** — No LLM numeric confidence on any Foundry surface; only harness-measured statistics are displayed.

## 6. Deliverables & PR map

| PR | Contents |
|---|---|
| **PR-B (this PR)** | `engine/signal_foundry/` (spec, transforms, harness, screen, seeds, results), `config/signal_foundry.yml`, `config/signal_foundry_blocklist.yml`, tests, this masterplan |
| **PR-A (parallel)** | Signal Lab v2 page revamp (independent of Foundry) |
| **PR-C** | `scripts/run_signal_foundry_brainstorm.py` + `.github/workflows/signal-foundry.yml` (dark) |
| **PR-D** | Foundry section on signal_lab.html + nightly forward-accrual step + synapse/SIGNAL_BUS registration |
| **PR-E** | First cohort: seeds → screen → specs → harness runs → committed results |

## 7. Clocks

- **2026-07-24** — first operator review: cohort quality, screen precision (share of LLM proposals rejected by the screen), harness runtime. Decide whether to arm the scheduled lane.
- **2026-08-15** — first promotion-docket read: any pass_candidate with ≥ 20 forward sessions.
- **2026-10-15** — program review: candidates/week throughput, null/pass mix, whether the Foundry feeds the research factory `alpha_family` track formally.

## 8. What the Foundry is NOT

- Not a trader, not a sizer, not an escalator — display tier, permanently, absent human promotion.
- Not a second metabolism: it shares no files with `engine/metabolism/**` or `engine/neuralweb/capability_broker.py`; it reuses *patterns* (kill-switch, budget, journal, two-key), not their code paths, to stay collision-free with the active metabolism program.
- Not a replacement for hand-built phase-0 research: deep, bespoke constructions (regime interactions, event studies with hand-cleaned data) remain human work. The Foundry industrializes the *simple-construction* search space.

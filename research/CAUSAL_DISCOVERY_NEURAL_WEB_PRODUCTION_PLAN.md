# Causal Discovery, Factor-Mirage Defense, and LLM Brainstorming for Neural Web

Status: research handoff and production design

Audience: Neural Web, Oracle, Fable, Claude, future implementation agents

Date: 2026-07-09

Source prompt: X post by `@RitOnchain`, `https://x.com/RitOnchain/status/2074773045236142180`, linking to X Article `https://x.com/i/article/2070742959113592832`; full article later provided locally as `/Users/chriswong/Downloads/Untitled.rtf`.

Retrieval note: the first pass could not access the X Article body because it was gated behind X's JS/API surface in this environment. The second pass used the user-provided RTF article body plus primary papers and current repo contracts.

Core external references:

- Campbell R. Harvey, Yan Liu, Heqing Zhu, "... and the Cross-Section of Expected Returns", NBER Working Paper 20592, 2014: https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
- Campbell R. Harvey and Yan Liu, "False (and Missed) Discoveries in Financial Economics", Journal of Finance version: https://people.duke.edu/~charvey/Research/Published_Papers/P143_False_and_missed.pdf
- Marcos Lopez de Prado and Vincent Zoonekynd, "Why Has Factor Investing Failed?: The Role of Specification Errors", SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4697929
- Marcos Lopez de Prado and Vincent Zoonekynd, "Causality and Factor Investing: A Primer", CFA Institute RPC, 2025: https://rpc.cfainstitute.org/research/foundation/2025/causality-factor-investing
- Xun Zheng, Bryon Aragam, Pradeep Ravikumar, Eric P. Xing, "DAGs with NO TEARS: Continuous Optimization for Structure Learning", NeurIPS 2018: https://arxiv.org/abs/1803.01422
- Yue Yu, Jie Chen, Tian Gao, Mo Yu, "DAG-GNN: DAG Structure Learning with Graph Neural Networks", ICML 2019: https://proceedings.mlr.press/v97/yu19a.html
- Agathe Sadeghi, Achintya Gopal, Mohammad Fesanghary, "Causal Discovery in Financial Markets: A Framework for Nonstationary Time-Series Data", arXiv:2312.17375: https://arxiv.org/html/2312.17375v2
- Ruijie Tang, "Trading with Time Series Causal Discovery: An Empirical Study", arXiv:2408.15846: https://arxiv.org/abs/2408.15846
- Jonas Peters, Peter Buhlmann, Nicolai Meinshausen, "Causal Inference by using Invariant Prediction", JRSS-B, 2016: https://academic.oup.com/jrsssb/article-abstract/78/5/947/7040653

Repo anchors:

- `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
- `config/synapse.yml`
- `docs/SIGNAL_BUS.md`
- `engine/neuralweb/cortex.py`
- `engine/neuralweb/metabolism.py`
- `scripts/evaluate_cortex_hypotheses.py`
- `scripts/oracle_brainstorm_pack.py`
- `engine/oracle/compounds.py`

---

## 0. Executive Ruling

The linked idea is directionally right but incomplete.

Correct:

- The old "find factor, show t-stat, ship" workflow is structurally broken.
- Factor-zoo multiple testing means ordinary t > 2 evidence is too weak.
- Causal structure matters because many apparent factors are confounders, colliders, mediators, duplicated exposures, or downstream price-action echoes.
- LLMs can multiply idea throughput if they are forced into a declarative hypothesis grammar and audited against already-tested ground.

Insufficient:

- Causal discovery is not a magic alpha machine. Financial data are nonstationary, autocorrelated, reflexive, regime-fractured, and full of hidden common drivers.
- A discovered DAG edge is not a signal. It is a candidate explanation that must survive invariance, lag, placebo, post-registration, and FDR tests.
- LLM-generated causal stories are useful only as proposal material. They cannot create authority.

Repo ruling:

Build this as a first-class Neural Web epistemic lobe:

```text
neuralweb.causal_hypothesis_factory.v1
```

This should live under Neural Web / Cortex / Research Factory, not inside Oracle alone.

Oracle should consume it for rotation-specific compound generation. Signal Lab and entry-intelligence systems should consume it for equity / risk / timing hypotheses. Cortex should supervise, explain, register, and grade the candidates through existing metabolism. The lobe should start `shadow`, publish candidates and nulls, and never originate trades or escalate alerts.

Best short version:

```text
LLMs brainstorm causal mechanisms.
Code converts mechanisms into pre-registered tests.
Causal discovery ranks candidate relationships, not trades.
Neural Web owns the evidence memory and promotion ladder.
Oracle/Signal Lab own domain-specific screens.
No candidate touches money-path surfaces until it survives post-registration and FDR.
```

### 0.1 Full-Article Reassessment

The actual article is stronger than the indexed preview. It is not just a causal-discovery slogan; it walks through SCMs, DAG assumptions, NOTEARS, DAG-GNN, a mutual-information speed path, a low-rank approximation path, a synthetic NOTEARS / LoRAM implementation, benchmark-style tables, a failure-mode section, and a 10-week roadmap.

The ruling still stands, but it gets sharper:

- Adopt the direction.
- Do not adopt the article's authority level.
- Do not make this a portfolio-construction engine first.
- Build it as an anti-mirage, hypothesis-production, and causal-audit lobe.

What the article gets right:

- It correctly attacks the factor-zoo workflow: mining many factors and celebrating t > 2 is not evidence discipline.
- It correctly says factor portfolios can look diversified while sharing one hidden parent.
- It correctly highlights structural priors, bootstrap edge stability, regime checks, and natural experiments.
- The NOTEARS skeleton is useful as a teaching prototype and maybe as a first small-universe engine.
- Its "hard truth" section is directionally honest about unobserved confounders, faithfulness failures, optimization limits, sample-size needs, and the intervention gap.

What we should downgrade:

- The article uses "what causes returns" too confidently. In our system, observational DAGs produce `causal_support`, not causal truth.
- The performance tables and firm-adoption claims should be treated as unverified unless separately sourced. A quick public-source check corroborated NOTEARS and DAG-GNN as real methods, but did not corroborate the article's proprietary D.E. Shaw claim, the named He et al. factor benchmark table, the Lorch regime-stability percentages, or the LoRAM / CMIN labels as stated.
- DAG-GNN is mis-framed in the article as a Zhu et al. 2023 method; the canonical DAG-GNN paper is Yu, Chen, Gao, and Yu, ICML 2019.
- The CMIN paragraph looks like a rough mutual-information shortcut rather than a clearly established production standard under that name. It may map loosely to temporal mutual-information causal discovery work, but we should not inherit the label blindly.
- The LoRAM section is useful as a low-rank engineering idea, but the article does not establish it as a peer-accepted causal-discovery standard. Treat it as an experimental accelerator.
- "5-10 macro variables" is far too thin for our Neural Web. Hidden parents in markets include liquidity plumbing, options/dealer pressure, positioning, buyback windows, earnings revisions, policy reaction functions, capital structure, fiscal/procurement flows, FX, credit, and crowding.
- A weekly full-DAG refresh can create graph churn. For most targets, we should separate daily edge monitoring from slower graph re-estimation and quarterly FDR review.

The upgraded interpretation:

```text
The article is a good spark for a causal anti-mirage lab.
It is not enough to justify direct factor selection.
Neural Web should convert it into a governed causal hypothesis factory.
```

### 0.2 What Changes After Reading the Full Article

My first-pass design already pointed to `neuralweb.causal_hypothesis_factory.v1`. Reading the full article strengthens that decision, but changes the implementation emphasis.

Earlier emphasis:

```text
LLM brainstorms mechanisms -> causal discovery ranks candidates -> metabolism tests.
```

Reassessed emphasis:

```text
Article code becomes sandbox/demo material.
Production value comes from the guardrails around it:
feature inventory, edge scouts, confounder audits, mechanism cards,
post-registration tests, null memory, invariance checks, and retirement.
```

The full article makes the strongest case for three concrete submodules:

| Submodule | What it borrows from article | Our upgrade |
| --- | --- | --- |
| Edge Scout | NOTEARS, DAG-GNN, mutual-information, low-rank search | ensemble edge candidates only; never direct trade authority |
| Mechanism Compiler | SCM/DAG framing and causal-parent language | LLM-generated mechanism cards with confounders, colliders, falsifiers, and environment splits |
| Anti-Mirage Auditor | factor zoo, proxy/double-counting examples | hidden-parent, duplicate-exposure, and over-control audits across all lobes |

The article's own roadmap ends at a portfolio system. Our roadmap should end at a governed Neural Web memory layer that can eventually feed portfolio decisions after evidence accrues.

### 0.3 Article Roadmap vs. Macro Dashboard Roadmap

| Article recommendation | Reassessment for Neural Web |
| --- | --- |
| Assemble 20-30 factors and 5-10 macro variables | Too narrow. Start from repo-native feature inventory across world state, Oracle, Signal Lab, liquidity, FX, rates, context organs, options, attention, and entity state. |
| Implement NOTEARS in weeks 3-4 | Fine for sandbox; production must wrap it in leakage checks, time-split controls, missingness policy, bootstrap stability, and impossible-edge masks. |
| Identify factors as causal vs. spurious | Too binary. Emit `direct_parent_candidate`, `descendant_proxy`, `shared_parent_suspect`, `collider_risk`, `unstable_edge`, and `unknown`. |
| Use >70% bootstrap edge stability | Useful floor, but not enough. Add regime invariance, lag consistency, negative controls, natural-experiment alignment, and post-registration outcome grading. |
| Build a causal factor portfolio in weeks 7-8 | Too fast for this repo. Phase 1 should only suppress confidence, flag redundancy, and propose experiments. Portfolio use waits for confirmer/scored status. |
| Schedule weekly DAG re-estimation | Split cadence: daily drift monitors, weekly brainstorm packs, monthly small-universe edge refresh, quarterly FDR/null review. |
| Dashboard factors as causal/spurious | Dashboard should show maturity and doubt: support, concerns, falsifiers, edge stability, latest break, and whether any consumer is allowed to use it. |

### 0.4 Production Interpretation of the Article's Algorithms

Use the article's algorithm menu as a search committee, not as a ladder of truth.

| Article method | Keep? | Production role |
| --- | --- | --- |
| NOTEARS | Yes | First small-universe baseline for cross-sectional / feature-level causal DAG prototypes. |
| NOTEARS with priors | Yes | More important than raw NOTEARS; encode time ordering, sink/source constraints, impossible edges, and domain tiers. |
| DAG-GNN | Later | Research-only nonlinear edge scout; useful after we have stable smaller DAGs and enough observations. |
| CMIN / mutual information shortcut | Reframe | Use as cheap dependence/edge-screening prefilter, not causal proof. |
| LoRAM / low-rank adjacency | Reframe | Treat as experimental speed path for large panels; compare against simpler sparse models before trusting it. |
| Bootstrap stability | Yes | Required but insufficient. |
| Synthetic data benchmark | Yes | Required harness, but never evidence that a live financial edge works. |

Best production build sequence:

1. Feature inventory and causal tiering.
2. Synthetic DAG harness to test our own implementation.
3. Small-universe NOTEARS with priors on 10-30 variables per target family.
4. Negative-control and placebo edge library.
5. LLM mechanism-card generator.
6. Compiler from mechanism card to Cortex metabolism claim.
7. Quarterly FDR/null review.

Do not start with DAG-GNN or a large low-rank graph. Start with boring, inspectable, falsifiable edges.

---

## 1. Assessment of the Source Idea

### 1.1 What the Harvey Factor-Zoo Warning Means for Us

Harvey, Liu, and Zhu catalogue hundreds of published return factors and argue that ordinary significance thresholds become misleading when many factors have been tried. Their conclusion is not merely "use a higher t-stat." The deeper message is:

- every idea needs a trial budget,
- every family needs multiple-testing discipline,
- hidden failed attempts must be assumed,
- correlation-only discoveries should be treated as suspect,
- publication and model-selection processes are part of the data-generating process.

The paper's implication for Macro Dashboard:

Our current house law is already aligned. `config/synapse.yml` has a tier vocabulary; Cortex metabolism hard-wires FDR family and post-registration filters; Oracle brainstorm packs print known nulls and force a grammar. The missing upgrade is to make causal mechanism search a first-class, automated idea source rather than a human-only brainstorm.

### 1.2 What Causal Discovery Adds

Causal discovery tries to recover directed relationships or plausible parent sets from observational / time-series data using conditional independence, score search, functional causal models, invariance, or time-lag assumptions.

In finance, the useful outputs are not "X causes Y, go trade." The useful outputs are:

- a candidate parent set for a target outcome,
- a candidate lag structure,
- a list of variables that may be confounders, mediators, colliders, or proxies,
- a set of relationships that appear stable or unstable across regimes,
- a set of suspicious relationships that disappear under correct conditioning,
- an idea queue for forward tests.

The linked framework's strongest contribution is the mental shift:

```text
do not ask only "does this feature predict?"
ask "what mechanism would make this feature move the target, what would break it,
and is the relationship invariant under the regimes where it should hold?"
```

### 1.3 Where the Idea Can Go Wrong

Causal discovery in markets has five failure modes we must make explicit:

1. Hidden common drivers

   Many features are children of the same unobserved variable: liquidity, risk appetite, index flows, dealer hedging, macro surprise, ETF rebalance, or earnings revision. A graph may draw a direct edge where the real cause is missing.

2. Collider conditioning

   Conditioning on downstream variables can flip signs. A "clean" regression that controls for too much can manufacture a factor mirage.

3. Regime nonstationarity

   An edge can exist in high-vol deleveraging and vanish in low-vol carry. Global tests can hide local causality; local tests can overfit regimes.

4. Time aggregation

   Daily, weekly, and monthly bars can tell different stories. A same-day edge can be a lagged edge sampled badly.

5. Reflexivity and crowding

   Once a causal-looking relationship is traded, the relationship changes. That is not a minor caveat; it is the market.

Therefore, the lobe must not publish "causal truth." It should publish `causal_support`, `causal_concerns`, and `test_plan`.

---

## 2. Which Lobe?

### 2.1 Primary Owner

Primary owner:

```text
Neural Web: Causal Hypothesis Factory / Causal Discovery Lobe
```

This is an epistemic lobe. It exists to improve how Neural Web decides which claims deserve attention, testing, distrust, or retirement.

It should not be called an alpha lobe. It does not create buy signals. It creates better candidate experiments.

### 2.2 Why Not Oracle Only

Oracle is the rotation lobe. It owns sector/theme/subsector episodes, compounds, Time Machine memory, and rotation-specific rules.

Causal discovery is broader:

- factor-mirage audits across all engines,
- equity entry-quality hypotheses,
- exit/trim causal failure modes,
- macro transmission relationships,
- liquidity plumbing effects,
- context-organ effects,
- confluence independence and hidden-common-driver detection,
- LLM hypothesis metabolism.

Oracle should be one of the best consumers, not the owner.

### 2.3 How It Connects to Existing Organs

| System | Role in this plan |
| --- | --- |
| Cortex | Reads world state/spine/graph, proposes hypotheses, writes memo, stakes claims through metabolism |
| Metabolism | Server-side registration, budget, `fdr_family`, post-registration accountability |
| Evaluator | Grades only against pre-committed gates, strict post-registration rows |
| Oracle | Converts rotation causal ideas into compound specs and screens them |
| Signal Lab | Uses causal candidates to form one-construct-per-family screens |
| Measurement Hub | Shows nulls, maturity, retirement, FDR results |
| Context organs | Provide causal variables: liquidity, exposure, capital wall, fiscal tape, FX, rates |
| Committee View | Shows causal candidates and why they are still shadow |

---

## 3. Upgrade the Idea Significantly

The paper/source idea seems to be:

```text
Use causal discovery to filter factor signals and avoid factor-zoo false positives.
```

We should upgrade it to:

```text
Use causal discovery plus LLM mechanism generation plus pre-registered metabolism
to build an automated hypothesis factory that produces, rejects, remembers, and
retires causal signal candidates across the whole Neural Web.
```

### 3.1 Ensemble Causal Discovery, Not One DAG

Use multiple lenses and require agreement/disagreement to be explicit:

| Method family | Use | Failure mode |
| --- | --- | --- |
| Lagged Granger / sparse VAR | cheap lead-lag scout | linear, unstable, confounded |
| PCMCI-style conditional independence | time-series parent search | sensitive to test choice and autocorrelation |
| CD-NOTS / nonstationary time-series discovery | better fit for financial nonstationarity | computationally heavier |
| Invariant causal prediction | regime-stability screen | depends on useful environment splits |
| Domain-prior DAG templates | prevents impossible edges | can encode human bias |
| Negative controls | leakage and spurious-edge defense | only as good as controls chosen |

Output should be an ensemble edge record:

```json
{
  "edge_id": "liq_quality:stress_expansion->entry_stopout:h21",
  "source": "liquidity_quality",
  "target": "entry_stopout",
  "lag_days": [1, 5, 21],
  "support": {
    "granger": "weak",
    "conditional_independence": "medium",
    "invariance": "strong_in_low_rrp_env",
    "domain_prior": "strong"
  },
  "concerns": ["hidden_common_driver:risk_appetite", "regime_specific"],
  "status": "candidate_only"
}
```

### 3.2 Separate Mechanism From Measurement

Every candidate needs two artifacts:

1. Mechanism card

   Plain causal story, expected direction, why it should exist, when it should not exist, likely confounders, likely colliders, and falsifiers.

2. Test spec

   Exact target, horizon, eligible universe, pre-committed metric, min n, environment splits, null controls, and promotion family.

No mechanism without a test. No test without a mechanism.

### 3.3 Build a Collider and Confounder Auditor

This is the largest improvement over naive causal discovery.

For every candidate, the lobe should classify variables as:

- cause candidate,
- target,
- confounder,
- mediator,
- collider,
- proxy,
- lagged outcome echo,
- forbidden future information,
- redundant sibling of another feature.

Examples:

- If `risk_off` causes both `credit_spread_widening` and `sector_underperformance`, controlling for `credit_spread` might remove the causal channel rather than clean noise.
- If `entry_board_rank` is downstream of multiple signals, conditioning on it may create collider bias.
- If `price_momentum` and `relative_strength` are siblings of the same price process, treating them as independent confirmations is false confluence.

This should feed Neural Web's confluence graph. The graph should mark:

```text
confirming independent evidence
confirming duplicate exposure
contradicting evidence
same hidden parent suspected
collider risk
mediator risk
```

### 3.4 Treat Causal Discovery as Candidate Triage

Bad path:

```text
run causal discovery -> edge found -> add signal
```

Good path:

```text
run causal discovery -> edge found -> register hypothesis -> wait -> grade -> FDR -> shadow survivor -> domain gauntlet -> maybe promote
```

The lobe's first production value is reducing bad ideas and focusing expensive tests, not creating immediate new act-tier signals.

### 3.5 Use Invariance as the Main Financial Reality Check

The strongest causal criterion for our use is not "edge appears in one full-sample DAG." It is:

```text
The relationship holds in the environments where the mechanism says it should hold,
and breaks or weakens in the environments where the mechanism says it should not hold.
```

Environment splits to use:

- high vol / low vol,
- expanding / contracting liquidity,
- benign-expansion / stress-expansion / neutral-hollow liquidity quality,
- rates-up / rates-down,
- dollar-up / dollar-down,
- credit-spread widening / tightening,
- early-cycle / late-cycle / recession-risk,
- sector leadership / sector repair / sector distribution,
- pre-earnings / post-earnings,
- high-crowding / low-crowding,
- high-options-gamma / low-options-gamma,
- China policy-on / policy-off,
- RRP buffer ample / exhausted,
- TGA rebuild / drawdown.

### 3.6 Create a Null Library

Every failed causal candidate is valuable if remembered.

The lobe should write:

```text
data/neuralweb/causal_nulls.jsonl
```

Null rows should include:

- mechanism family,
- tested edge,
- failed reason,
- sample windows,
- environments,
- p/FDR outcome,
- whether it was collider-contaminated,
- whether it was a duplicate exposure,
- whether it had insufficient n,
- "do not re-propose" text for LLM prompts.

This directly extends the successful Oracle brainstorm-pack pattern.

---

## 4. Production Architecture

### 4.1 New Artifacts

Add these as `shadow` or `infrastructure` artifacts in `config/synapse.yml`:

| Artifact | Path | Tier | Producer |
| --- | --- | --- | --- |
| causal-feature-inventory | `data/neuralweb/causal_feature_inventory.json` | infrastructure | `engine/neuralweb/causal_inventory.py` |
| causal-edge-candidates | `data/neuralweb/causal_edges.jsonl` | shadow | `engine/neuralweb/causal_discovery.py` |
| causal-mechanism-cards | `data/neuralweb/causal_mechanisms.jsonl` | shadow | `scripts/run_causal_brainstorm.py` |
| causal-hypothesis-queue | `data/neuralweb/causal_hypothesis_queue.jsonl` | shadow | `engine/neuralweb/causal_compiler.py` |
| causal-null-library | `data/neuralweb/causal_nulls.jsonl` | infrastructure | evaluator / adjudicator |
| causal-brainstorm-runs | `data/neuralweb/causal_brainstorm_runs.jsonl` | infrastructure | `scripts/run_causal_brainstorm.py` |
| causal-lobe-state | `data/neuralweb/causal_lobe_state.json` | shadow | `engine/neuralweb/causal_state.py` |
| site causal view | `site/neuralwebdata/causal_lobe_state.json` | display | site build copy |

### 4.2 Feature Inventory

The feature inventory is the lobe's map of what can be reasoned about.

Each feature should carry:

```json
{
  "feature_id": "regime.liquidity_quality.label",
  "path": "data/regime/latest.json",
  "producer": "engine/regime.py",
  "cadence": "daily-engine",
  "asof_field": "asof",
  "entity_scope": "macro",
  "time_grain": "daily",
  "min_lag_days": 1,
  "known_latency": "H41 weekly lag handled upstream",
  "family": "liquidity",
  "allowed_roles": ["candidate_cause", "conditioner", "environment_split"],
  "forbidden_roles": ["same_day_target"],
  "collider_risk": "medium",
  "notes": "Use quality label, not only expanding/contracting overlay."
}
```

Initial sources:

- `data/neuralweb/world_state.json`
- `data/neuralweb/spine_index.parquet`
- `data/neuralweb/kernel_estimates.parquet`
- `data/neuralweb/confluence_graph.json`
- `data/regime/latest.json`
- `data/regime/regime_history.parquet`
- `data/breadth/breadth.parquet`
- Oracle panel columns
- liquidity quality and plumbing artifacts
- rates/FX/credit context
- options/flow context where data provenance is strong
- exposure/capital/fiscal context organs as they come online

### 4.3 Causal Discovery Engine

The first implementation should be narrow and cheap:

```text
engine/neuralweb/causal_discovery.py
```

Inputs:

- a target family,
- a universe,
- candidate feature set,
- allowed lags,
- environment split definitions,
- null controls.

Outputs:

- edge candidates,
- stability/invariance scores,
- concern tags,
- recommended test specs.

Start with four target families:

1. Entry quality

   Target: forward excess return, stop-out, max adverse excursion, entry delay benefit.

2. Exit / trim

   Target: drawdown after signal, failed breakout, thesis deterioration, post-entry risk escalation.

3. Rotation

   Target: Oracle episode success, sector repair, leadership handoff, washout recovery.

4. Risk / de-escalation

   Target: market-state downgrade, risk-radar escalation, volatility expansion, breadth break.

### 4.4 LLM Brainstorm Runner

Create:

```text
scripts/run_causal_brainstorm.py
```

Do not let LLMs write free-form strategy memos into the queue. Force a JSON schema:

```json
{
  "mechanism_id": "liq_stress_entry_fragility_v1",
  "family": "liquidity_entry_quality",
  "claim": "Stress-expansion liquidity improves raw entry odds less than benign-expansion liquidity and increases stop-out risk when RRP buffer is exhausted.",
  "causal_graph": {
    "cause": "liquidity_quality.label",
    "target": "entry_quality.stopout_h21",
    "mediators": ["credit_spread", "breadth_repair"],
    "confounders": ["market_risk_appetite", "rate_trend"],
    "colliders_to_avoid": ["board_rank", "final_verdict"]
  },
  "falsifiers": [
    "No effect in low-RRP environments.",
    "Effect disappears when tested only post-registration.",
    "Benign/stress split has same stopout profile."
  ],
  "test_spec": {
    "claim_shape": "conditional_regime",
    "horizon_d": 21,
    "metric": "stopout_rate_delta",
    "threshold": -0.05,
    "min_n": 25,
    "environment": "rrp_exhausted"
  },
  "source_edges": ["causal_edges:..."],
  "status": "llm_proposed_shadow"
}
```

LLM roles:

| Role | Model class | Output |
| --- | --- | --- |
| Mechanism generator | cheap | many candidate mechanisms |
| Domain mechanic | cheap / mid | translate into finance mechanism |
| Skeptic | stronger | confounder/collider/falsifier list |
| Grammar compiler | cheap | JSON spec only |
| Deduper | cheap | compare against null library and registry |
| Judge | stronger | approve only specs with clean mechanism/test match |

Important: the generator's job is diversity, not correctness. Correctness belongs to deterministic tests and stronger review.

### 4.5 Compiler to Existing Metabolism

Use existing `engine/neuralweb/metabolism.py` for first version, because it already enforces:

- server-side `registered_at`,
- weekly budget,
- hard-wired `fdr_family`,
- pre-committed gate,
- TrialLedger accounting,
- governance events,
- no self-grading.

But extend it only if needed:

```text
registered_by = "causal_lobe"
machine_causal or cortex as the trial family
```

[W0 editorial token-break: the raw `fdr_family` assignment syntax on the second
line above was removed so the H1 ruling-graph guard does not read this PROPOSAL
as a family declaration. The machine_causal family was NOT adopted — see
CHF-R2/CHF-R3 in `research/CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md`.]

Conservative first choice:

- keep `fdr_family = cortex` initially,
- keep the budget small,
- use causal lobe only as a feeder to `stake_hypothesis`.

Future upgrade:

- add a separate machine family `causal_hypothesis_factory`,
- budget by mechanism family,
- still share a global machine-discovery FDR ceiling.

### 4.6 Evaluation

Extend `scripts/evaluate_cortex_hypotheses.py` or create a sibling only if the shape set grows too large.

New claim shapes to add eventually:

```text
causal_edge
invariance_split
collider_audit
mediator_test
negative_control
entry_quality
exit_fragility
rotation_transfer
```

Non-negotiable gates:

- strict post-registration data only,
- no same-day target leakage,
- no model-supplied min n below house floor,
- no self-reference,
- no post-hoc metric switching,
- all LLM volume charged to one machine FDR family,
- every null goes into the null library.

---

## 5. Automated LLM Brainstorming Loop

### 5.1 Daily / Weekly Cadence

Daily cheap scan:

```text
1. Refresh causal feature inventory.
2. Build small target panels for approved target families.
3. Run cheap causal screens for lagged relationships.
4. Compare against existing nulls and registered hypotheses.
5. Emit candidate edges, not hypotheses.
```

Weekly brainstorm:

```text
1. Build prompt pack from live inventory, causal edges, null library, registry, trial ledger.
2. Ask cheap models for 50-200 mechanisms across distinct families.
3. Deduplicate.
4. Run skeptic pass for collider/confounder/falsifier defects.
5. Compile top candidates into JSON mechanism cards.
6. Register only 1-3 best candidates through metabolism.
7. Archive all non-registered candidates with reason.
```

Quarterly:

```text
1. Run FDR batch over matured machine-causal hypotheses.
2. Promote survivors only to shadow/confirmer queues.
3. Retire repeated null basins.
4. Update prompt-pack "do not re-propose" section.
```

### 5.2 Prompt Pack Shape

The prompt pack should be generated, like `scripts/oracle_brainstorm_pack.py`, not hand maintained.

Sections:

- role and authority boundary,
- allowed output schema,
- feature inventory summary,
- target families,
- current causal edge candidates,
- already registered hypotheses,
- known nulls,
- known live regions,
- collider/confounder warnings,
- coverage floor,
- forbidden outputs,
- exact JSON response format.

The key line should be:

```text
You propose candidate mechanisms and test specs. You do not score, rank, trade,
or claim proof. Everything you propose is shadow and must pass post-registration tests.
```

### 5.3 Why LLMs Are Useful Here

LLMs are bad at statistical authority but good at:

- mechanism diversity,
- analogical transfer across domains,
- naming hidden confounders,
- spotting collider risks in a story,
- turning an abstract graph into a testable hypothesis,
- generating falsifiers,
- translating null-library lessons into prompt constraints,
- compressing a large feature dictionary into plausible mechanism families.

This is exactly the safe LLM role: propose, challenge, compile, explain. Code grades.

---

## 6. High-Value Signal Families to Brainstorm First

### 6.1 Factor Mirage / Collider Audit

Goal:

Find existing composites where we may be controlling for downstream variables, double-counting sibling variables, or treating one hidden bet as multiple confirmations.

Targets:

- board rank,
- top setups,
- market state,
- risk radar,
- sector central calls,
- committee provenance rows.

Candidate questions:

- Is `final_verdict` a collider between price action and fundamentals?
- Does controlling for volatility remove the risk channel we are trying to measure?
- Are momentum, RS, and trend all children of the same price process?
- Does a "confirmation" edge in confluence actually represent independent information?

Output:

```text
causal_confluence_quality: independent | duplicate | hidden_parent_suspected | collider_risk
```

This belongs in Neural Web's confluence graph, not in a trading signal.

### 6.2 Entry-Quality Causality

Goal:

Improve whether existing buy/setup windows should be trusted, delayed, or reduced.

Targets:

- 21d/63d forward excess,
- stop-out,
- max adverse excursion,
- entry delay benefit,
- gap-down risk,
- failed breakout.

Candidate causes:

- liquidity quality,
- breadth repair,
- credit spreads,
- options gamma,
- darkpool/flow context,
- insider power,
- sector sponsorship,
- fiscal/contract implementation,
- capital-wall risk,
- FX/rates stress.

This is likely the fastest ROI because it improves existing entry decisions without originating new buys.

### 6.3 Exit and Trim Fragility

Goal:

Find causes of post-entry deterioration before price breaks fully.

Candidate mechanisms:

- sponsorship fades while price holds,
- liquidity quality shifts from benign to stress,
- options support disappears,
- peer causal graph turns negative,
- capital-wall stress rises,
- fiscal implementation disappoints,
- crowding unwinds,
- sector leadership transfers away.

Output should feed Exit & Trim Intelligence, not raw sell calls.

### 6.4 Rotation Transfer and Oracle

Goal:

Let causal discovery propose better Oracle compounds.

Candidate mechanisms:

- outflow from one complex causes inflow to a specific opposite complex with lag,
- washout plus active flow stress causes repair,
- sector personality changes lag macro regime changes,
- liquidity stress changes which washouts are buyable,
- breadth repair mediates the relation between flow and return.

Implementation:

- causal lobe emits mechanism cards,
- Oracle compiler translates approved rotation cards into `engine/oracle/compounds.py` grammar,
- `scripts.oracle_ingest_brainstorm` or Oracle screen handles evaluation.

### 6.5 Macro Transmission

Goal:

Connect macro context organs to asset-level outcomes without pretending one macro number is a universal buy/sell signal.

Candidate mechanisms:

- dollar strength -> non-US revenue margin pressure -> stock fragility,
- rate-vol shock -> long-duration equity drawdown risk,
- TGA rebuild -> reserve drain -> small-cap liquidity pressure,
- fiscal obligations -> recipient/backlog support -> sector sponsorship,
- refinancing wall -> equity issuance risk -> failed rebound.

This is where the context organs become decision-useful.

### 6.6 Null Mining

Goal:

Find ideas that should be forbidden or de-emphasized.

Examples:

- "healthy participation" as primary entry condition,
- late acceleration chasing,
- pooled washout variants already beaten by existing state,
- confluence edges that are only duplicated price momentum,
- LLM narrative strength that follows price rather than leads it.

The lobe should celebrate high-quality nulls. They reduce future waste.

---

## 7. Production Roadmap

### Phase 0: This Memo

Done by this artifact:

- source assessment,
- lobe ruling,
- architecture,
- production plan,
- first signal families.

### Phase 1: Causal Feature Inventory

Build:

```text
engine/neuralweb/causal_inventory.py
scripts/build_causal_inventory.py
tests/test_causal_inventory.py
```

Output:

```text
data/neuralweb/causal_feature_inventory.json
```

Acceptance:

- reads only registered or explicitly allowed artifacts,
- stamps cadence, asof, lag, scope, allowed role,
- flags forbidden same-day target use,
- no LLM involved.

### Phase 2: Causal Edge Scout

Build:

```text
engine/neuralweb/causal_discovery.py
scripts/build_causal_edges.py
tests/test_causal_discovery.py
```

Start simple:

- lagged correlations,
- sparse Granger,
- negative lag placebo,
- block bootstrap,
- environment stability,
- feature-role constraints.

Do not start with huge PC/CD-NOTS across the whole repo. Start with target-family panels.

Output:

```text
data/neuralweb/causal_edges.jsonl
```

Acceptance:

- deterministic,
- leak-free,
- prints null controls,
- no edge has authority.

### Phase 3: Brainstorm Pack and Mechanism Cards

Build:

```text
scripts/causal_brainstorm_pack.py
scripts/run_causal_brainstorm.py
engine/neuralweb/causal_schema.py
tests/test_causal_brainstorm_schema.py
```

Initial mode:

- pack generation only,
- optional manual paste to LLM,
- schema checks,
- no auto-registration.

Later mode:

- automated cheap-model generation,
- stronger-model critique,
- JSON-only result,
- top 1-3 passed to metabolism.

### Phase 4: Metabolism Integration

Extend current `stake_hypothesis` flow:

- allow `registered_by = causal_lobe`,
- keep server-side timestamp,
- keep budget,
- keep FDR family,
- write governance event,
- write null-library entry on failure.

Acceptance:

- a candidate cannot grade on pre-registration rows,
- LLM cannot lower min n,
- LLM cannot choose a private FDR family,
- LLM cannot reference cortex_attention as evidence,
- all write surfaces are shadow.

### Phase 5: Dashboard / Operator Surface

Add to admin Neural Web tab or Committee View:

- causal lobe heartbeat,
- new candidate edges,
- registered hypotheses,
- matured results,
- null library,
- collider warnings,
- graph of "independent vs duplicate confluence."

Keep UI copy compressed. This is an operator console, not a landing page.

### Phase 6: Authority

Do not grant authority early.

Possible future authority after evidence:

| Authority | Possible action | Gate |
| --- | --- | --- |
| A1 explain | show causal mechanism cards | immediate |
| A2 attend | prioritize candidate review | after attention earn-in |
| A3 de-escalate | warn that confluence is duplicate/collider-risk | after track record |
| A4 require confirmation | add "needs independent confirmation" badge | after proven no-harm |
| A5 retire | auto-retire repeated null basin from prompts | after governance approval |
| A7 originate | never |

---

## 8. Implementation Sketch

### 8.1 Minimal Directory Shape

```text
engine/neuralweb/causal_inventory.py
engine/neuralweb/causal_discovery.py
engine/neuralweb/causal_schema.py
engine/neuralweb/causal_state.py
scripts/build_causal_inventory.py
scripts/build_causal_edges.py
scripts/causal_brainstorm_pack.py
scripts/run_causal_brainstorm.py
tests/test_causal_inventory.py
tests/test_causal_discovery.py
tests/test_causal_brainstorm_schema.py
```

### 8.2 First Schema Vocabulary

Mechanism families:

```text
liquidity_transmission
macro_transmission
rotation_transfer
entry_quality
exit_fragility
confluence_independence
factor_mirage
context_organ
oracle_compound
null_mining
```

Variable roles:

```text
candidate_cause
target
conditioner
environment_split
confounder
mediator
collider
proxy
lagged_outcome_echo
negative_control
forbidden_future
```

Edge status:

```text
screened_candidate
llm_mechanism_proposed
registered
accruing
insufficient_n
failed
null_library
passed_shadow
queued_fdr
retired
```

### 8.3 First Targets

Start with targets already likely available through spine/qledger or existing ledgers:

```text
forward_excess_21d
forward_excess_63d
max_adverse_excursion_21d
stopout_21d
entry_delay_benefit_5d
risk_escalation_10d
sector_episode_success_63d
oracle_compound_effect_63d
```

### 8.4 Tests

Hermetic tests:

- future value does not change past feature,
- negative lag placebo is marked suspicious,
- same feature cannot be both target and cause,
- collider variables cannot be used as ordinary controls without warning,
- generated prompt includes null library,
- generated prompt includes already registered hypotheses,
- LLM output with prose wrapper is rejected,
- LLM output with missing falsifier is rejected,
- low-min-n proposal is clamped or rejected,
- self-reference is rejected,
- edge candidate never changes money-path artifact.

---

## 9. The Best First 10 Hypotheses to Generate

These are not recommendations. They are candidate research directions for the lobe to compile and test.

1. Liquidity quality, not liquidity direction, conditions entry quality

   `benign-expansion` should improve entry holdability more than `stress-expansion`, even when both have positive net liquidity direction.

2. RRP exhaustion changes liquidity transmission

   When RRP buffer is exhausted, TGA/RRP mechanical support has less marginal cushion and entry failures should be more sensitive to credit/rate shocks.

3. Duplicate confluence penalty

   Setups where all confirming evidence is price-derived should underperform setups with at least one independent non-price sponsor.

4. Sponsorship before repair

   Sector or stock repair after washout works better when flow/sponsorship stress is already being absorbed, not merely when breadth looks healthy.

5. Late acceleration is a causal warning, not confirmation

   If the proposed cause is already downstream of price acceleration, it should predict worse entry quality.

6. Macro transmission fingerprints are sector-specific

   Rate-vol, dollar, credit, and liquidity shocks should have different lagged transmission by sector personality; pooled macro effects should be weak.

7. Capital-wall fragility explains failed rebounds

   Rebound candidates with near-term refinancing pressure should have higher failure/trim risk even when technical repair is present.

8. Fiscal implementation beats fiscal narrative

   Government theme names should gain sponsorship only when solicitations/awards/obligations are moving, not when policy headlines alone appear.

9. Options support is a mediator, not always an independent cause

   Dealer/gamma context may mediate crowding and volatility effects; treating it as independent confluence may overstate confidence.

10. News/LLM narrative strength often follows price

   Narrative strength should be tested as a lagged cause versus price echo, with negative controls and post-registration windows.

---

## 10. Final Ruling

The idea is worth building, but only if we make it more disciplined than the article pitch.

Do not build:

```text
causal DAG -> alpha score -> trade
```

Build:

```text
causal discovery + LLM mechanism factory + repo grammar compiler
-> pre-registered hypothesis metabolism
-> post-registration evidence
-> FDR/null library
-> shadow/confirmer/scored ladder
-> Neural Web decision packets
```

The lobe should become Neural Web's "idea immune system": it finds possible causes, identifies fake confluence, catches factor mirages, generates falsifiers, remembers nulls, and turns LLM creativity into auditable experiments.

That is the production-grade version of the paper's idea.

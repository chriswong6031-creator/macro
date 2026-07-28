# Prophet Trade Memory Masterplan

Date: 2026-07-28
Status: W0/W1 implementation
Owner: Prophet department inside the existing Neural Web roster
Authority: research/context only

## Executive ruling

Build **Prophet Trade Memory as a department inside Prophet**, not as a new roster
lobe. Keep the existing Long-Hold Winner Autopsy, Context Lobe, Causal Lab, Codex
Research case lane, and Prophet forward ledger. They are different organs with
different responsibilities:

| Component | Keep? | Responsibility | What it must not become |
|---|---:|---|---|
| Prophet forward ledger | yes | immutable record of what Prophet said and what happened | an editable story store |
| Prophet Trade Memory | new department | private operator episodes, per-pick autopsies, analogue retrieval, pattern accrual | a direct scoring/ranking engine |
| Long-Hold Winner Autopsy | yes | historical breakaway census, controls, and long-hold fingerprints | the personal trade journal |
| Codex Research cases | yes | deep research reports on selected historical episodes | runtime canonical memory |
| Context Lobe | yes | current/PIT context aggregation for a ticker/date | episodic outcome memory |
| Causal Lab / Research Factory | yes | falsification, preregistration, null retention, authority earn-in | an LLM opinion board |
| “Thesis lobe” | no | already superseded by Long-Hold departments | a duplicate per-stock thesis store |

No existing lobe is deleted in this wave. Merging them would erase important
firewalls: current context is not an episode; a historical winner census is not an
operator trade; an LLM explanation is not causal evidence; and a research case is not
a calibrated live signal.

## What was actually live before this work

### Prophet accountability

The deterministic US attribution pipeline and cross-market governor were live. The
committed US ledger contained a large matured cohort, but the governor mostly exposed
coverage/freshness and did not consume causal lessons.

The pick-autopsy implementation existed in
`engine/metabolism/standout_auditor.py`, but it was not a functioning production
memory:

1. no daily workflow called `run_pick_autopsies`;
2. the armed path passed `model_caller=None` into a helper that immediately returned
   an empty list, so it could never call a real model;
3. `prophet.fable_enabled` was false;
4. selection would repeatedly choose the same extremes instead of accruing new IDs;
5. the admin reader looked for top-level fields even though the writer nested them
   under `llm`, so verdicts and lessons would render blank;
6. the v1 prompt asked for one root-cause paragraph, not a traceable first/second/third
   order causal map.

The cohort postmortem organ was also armed only through Metabolism and remains
separate from Trade Memory. It is useful for process-health review, not as the
canonical episode store.

### Historical winners

Winner Autopsy was real and useful: the current panel held thousands of episodes
across hundreds of tickers, with explicit durable-winner, clean-hold, blow-off,
failed, and unmatured outcomes. Codex Research cases were also active. Their design
correctly treats census first and case narratives second, reducing selection-on-the-
dependent-variable errors.

These assets answer “what did historical breakaway winners look like?” They do not
answer “what trade did the operator take, what was knowable at entry, and what did
Prophet learn after the exit?”

### Context and causal infrastructure

The Context Snapshot API already provides point-in-time personality, archetype,
regime, sector, factor, attention, insider, short-interest, options, and spine
dimensions. Trade Memory reuses it. Building a parallel RAG/knowledge base would
violate the canonical-source law and introduce hindsight leakage.

Causal Lab currently contains mostly insufficient-power/null results. That is a
healthy reason to preserve it: a memory system that only remembers winners will
manufacture confidence. Causal Lab is the destination for repeated measurable
hypotheses, not the place to store personal trades.

## Research synthesis

The design borrows four durable ideas from agent-memory research:

1. **Episodic reflection can improve future behavior** when a reflection is stored and
   retrieved on later tasks (Reflexion, 2023).
2. **Observation, planning, and reflection all matter**; a raw transcript alone is not
   sufficient (Generative Agents, 2023).
3. **Memory needs tiers** rather than an unbounded prompt: raw episodes, compact
   reflections, and higher-level beliefs have different retention/read paths (MemGPT,
   2023).
4. **Facts, experiences, summaries, and evolving beliefs should be separate and
   traceable** (Hindsight, 2025).

Newer evaluation work adds the caution that matters most in finance: agents can store
confidently wrong diagnoses, reflection quality is often the bottleneck, and memory can
cause forgetting or negative transfer. Therefore the system must measure whether a
retrieved lesson actually improves a later prospective decision, not whether the prose
sounds insightful.

Performance attribution research supports a deterministic first pass. A trade return
should be decomposed descriptively into market, sector, and stock-specific residual
before narrative explanation. Event-study inference also needs clustered-event
controls: ten healthcare winners during one rotation are not ten independent proofs.

Sources:

- Reflexion: https://arxiv.org/abs/2303.11366
- Generative Agents: https://arxiv.org/abs/2304.03442
- MemGPT: https://arxiv.org/abs/2310.08560
- Hindsight: https://arxiv.org/abs/2512.12818
- Long-term memory evaluation: https://aclanthology.org/2025.findings-acl.1014/
- Honest Lying / false self-diagnosis: https://arxiv.org/abs/2605.29463
- BenchTrace reflection evaluation: https://arxiv.org/abs/2605.29225
- Brinson performance attribution: https://www.tandfonline.com/doi/abs/10.2469/faj.v42.n4.39
- Market/industry/firm decomposition: https://www.nber.org/system/files/working_papers/w7144/w7144.pdf
- Clustered event-study inference: https://academic.oup.com/rfs/article-abstract/23/11/3996/1605665
- Sector order flow and rotation: https://www.nber.org/papers/w16534

## Canonical memory model

### 1. Episode facts

`prophet.trade_episode/v1` is immutable trade evidence:

- source: operator, Prophet, or historical replay;
- ticker, market, side;
- entry/exit dates and optional prices;
- outcome: open, win, loss, flat;
- thesis written at entry;
- observed result written after exit;
- optional link to the Prophet pick.

Position size, account value, share count, and dollar P&L are deliberately excluded.
They are not needed to understand mechanism and should not widen the privacy surface.

Operator episodes live in owner-scoped Supabase rows with RLS. Prophet episodes
continue in the public forward ledger. No personal episode is committed to this public
repository.

### 2. Deterministic evidence packet

Before any LLM call, `prophet.trade_evidence/v1` freezes:

- stock return and path MFE/MAE;
- market return;
- sector proxy return;
- sector-minus-market, stock-minus-sector, and stock-minus-market residuals;
- point-in-time Context Snapshot at entry;
- explicit missing-data markers;
- operator text labelled as a claim until corroborated.

Arithmetic attribution is descriptive, not causal. That sentence is carried in every
packet.

### 3. Structured autopsy

`prophet.trade_autopsy/v1` contains:

- a short summary and closed mitigation verdict;
- a causal chain with order 1/2/3;
- layer: macro regime, market rotation, sector, company alpha, catalyst, entry timing,
  path risk, or counterfactual;
- evidence state: corroborated, contradicted, claimed, or unknown;
- timing state: known at entry, emerged after, hindsight only, or unknown;
- counterfactual and evidence references;
- alternate explanations and missing evidence;
- a process lesson;
- measurable signal hypotheses.

Every hypothesis is stamped `research_only` and `direct_authority=false`.

### 4. Pattern belief

An autopsy is an episode-level reflection, not a rule. The derived pattern view groups
measurable hypotheses and counts:

- winning support;
- loss/flat contradictions;
- distinct episodes;
- distinct entry-month clusters.

The first routing threshold is intentionally strict and modest: three winning
supports, at least one contradiction, five total episodes, and three time clusters.
Passing it means only `ready_for_prereg`, never “true” or “live.” Research Factory
must specify the feature and study; Causal Lab must retain nulls and test alternatives;
the existing gauntlet remains the only path toward authority.

The private derived view combines hypotheses from owner episodes with Prophet's
canonical matured-pick autopsies during each rebuild. It does not copy personal rows
into git and does not duplicate Prophet episodes into a second store.

### 5. Retrieval and prospective evaluation (next wave)

Retrieval should be structured first, semantic second:

- market/regime;
- sector and sector-relative state;
- company archetype;
- catalyst type;
- setup/entry state;
- causal mechanism;
- outcome/path shape.

For each future Prophet decision, freeze the retrieved analogue packet before the
outcome. Compare against a no-memory baseline:

- analogue precision;
- diagnosis accuracy;
- winner-detection lift;
- loser-avoidance lift;
- calibration;
- false transfer rate;
- lesson usefulness after independent review.

The memory is successful only if prospective decisions improve. More fluent autopsies
are not a success metric.

## The JNJ example: why traceability matters

The operator’s proposed mechanism contains several plausible layers:

1. over-owned technology rolled over;
2. a washed-out healthcare sector attracted defensive inflows;
3. JNJ outperformed the healthcare proxy and siblings;
4. a company catalyst (OTTAVA) strengthened the rerating;
5. the combined confluence made a mega-cap especially attractive to institutions.

The system should test each leg separately, including oil/inflation timing, fund-flow
evidence, healthcare-versus-staples relative performance, JNJ-versus-XLV residual,
sibling controls, and whether the catalyst was knowable at entry.

It must also catch a factual trap: Band-Aid and Listerine moved to Kenvue when Johnson
& Johnson completed the Consumer Health separation in 2023. Those brands cannot be
used as a current JNJ cash-flow mechanism. By contrast, the July 2026 FDA authorization
of OTTAVA is a real JNJ MedTech catalyst, but if it occurred after the trade entry it
belongs in `emerged_after`, not `known_at_entry`.

This is exactly why operator prose is stored as a claim and never silently converted
into a fact.

Official sources:

- JNJ/Kenvue separation: https://www.jnj.com/media-center/press-releases/johnson-johnson-announces-updated-financials-and-2023-guidance-following-completion-of-the-kenvue-separation
- Kenvue brand portfolio: https://www.jnj.com/media-center/press-releases/johnson-johnson-announces-kenvue-as-the-name-for-planned-new-consumer-health-company
- OTTAVA authorization: https://www.jnj.com/media-center/press-releases/johnson-johnson-receives-fda-market-authorization-in-the-u-s-for-its-ottava-robotic-surgical-system

## Implemented in W0/W1

- owner-private Supabase schema and RLS for episodes/patterns;
- authenticated Prophet admin intake and private history view;
- deterministic return/sector/market/PIT evidence builder;
- structured autopsy contract and deliberation-model runner;
- research-only repetition gate and private pattern view;
- joint pattern accrual across private operator episodes and canonical Prophet picks;
- daily private operator-review step;
- real daily Prophet pick-autopsy caller;
- production LLM waterfall for the formerly unwired armed path;
- skip-already-reviewed accrual;
- v2 first/second/third-order causal output;
- admin nested-field reader repair;
- Fable deliberation enabled under the existing daily token cap;
- public-repo privacy boundary (no personal snapshots).

## Follow-on waves

### W2 — stronger controls

- sibling basket and sector breadth controls;
- factor residuals (size/value/quality/momentum/low-vol) in addition to SPY/sector;
- event-date clustering and rotation-episode IDs;
- entry-time news/catalyst receipts;
- automated factual-claim verification with source URLs;
- import/update/close flows for open episodes.

### W3 — analogue retrieval

- hybrid structured + semantic retrieval;
- “why similar / why different” counterfactual packet;
- prospective frozen retrieval ledger;
- no-memory baseline and negative-transfer monitor.

### W4 — research promotion

- route `ready_for_prereg` candidates into Research Factory;
- auto-create Causal Lab mechanism cards only as inert drafts;
- test across eras, markets, sectors, and clustered episodes;
- retain nulls, contradictions, and failed lessons permanently;
- authority proposal only after existing calibration and gauntlet laws.

## Non-negotiable kill rules

- no new roster lobe or slot;
- no personal trade facts in git, site JSON, logs, or public R2;
- no position size or dollar P&L collection;
- no LLM numeric confidence;
- no LLM-originated signal, rank, score, sizing, gate, suppression, or escalation;
- no rule learned from a single winner;
- no winner-only training set;
- no use of post-entry facts as entry evidence;
- no second manually maintained knowledge base parallel to canonical stores;
- no deletion of nulls or contradicting episodes;
- no merge of Context, Long-Hold, Causal Lab, and Trade Memory into one authority blob.

# Options Alpha / Intraday Options Intelligence Recovery — OA-0 Architecture Freeze

**Date:** 2026-08-27  
**Authority:** Chairman-approved architecture; written-spec review gate still required before implementation planning or commissioning  
**Operation key:** `oa0-architecture-freeze-20260827-sol-001`  
**Carrier:** `sol/oa0-options-alpha-architecture-freeze-20260827`  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@af43f356f4f7f34cb3514d1d1099b50444af8487`, `mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1` compatible  
**Macro action-time base:** `ef6a099c86fa2f32d1f7e6a73c3cf284daffa3bc`  
**Terminal architecture pin:** `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`

## 0. Status and scope

This document freezes the architecture for recovering Options Alpha from a display-only shadow/readiness surface into a real options-intelligence product and prospective learning system.

It is **records/source law only**. This architecture does not itself:

- arm or restart any options collector, launchd unit, scheduler, model, scorer, alert, or execution path;
- change `flow_score.yml` from `scoring.enabled: false`;
- promote any options family to rank, gate, size, issue, portfolio, Neural Web, Prophet, or trading authority;
- merge, rewrite, or delete existing episode/campaign/outcome ledgers;
- create a second live-flow store, second ThetaData Terminal instance, second campaign lifecycle, second issue desk, or second options truth plane;
- declare MomoEdge parity or superiority;
- call a merged implementation production-proven.

Implementation remains blocked until the Chairman reviews this written spec and explicitly approves transition to the implementation-planning stage.

---

## 1. Outcome being pursued

### Primary user job

A serious trader or researcher opens Options Alpha during the session and should be able to answer, within seconds:

1. **What meaningful options campaign is forming now?**
2. **Why does it matter, based on measured evidence rather than a magic score?**
3. **Is the options activity leading the underlying, chasing it, hedging it, or contradicted by other evidence?**
4. **What did settled EOD options structure say before this intraday event became knowable?**
5. **What evidence is still missing or only becomes knowable later?**
6. **What has historically happened after comparable events, at the registered horizon, with sample size and calibration stated?**
7. **If the evidence eventually earns promotion, what exact option/lifecycle is actionable through the existing operator review path?**

### Machine/intelligence job

The machine must convert canonical options observations into a replayable sequence:

```text
trade + NBBO observation
→ deterministic event truth
→ exact-contract campaign evolution
→ point-in-time settled EOD context
→ research candidate or abstention
→ prospective outcomes
→ calibrated statistical evidence
→ separately promoted signal authority
→ existing operator Issue Desk / lifecycle
```

The system must preserve exact identity, clocks, source vintages, corrections, missingness, and authority at every step.

### Moat

The durable moat is not a proprietary-looking 0–100 number. It is the combination of:

- first-party licensed trade+NBBO observations;
- immutable event/campaign histories;
- exact point-in-time EOD options context;
- prospective outcome accrual;
- transparent calibration by DTE/construction/era;
- exact-option NBBO lifecycle outcomes;
- a product that makes evidence changes and contradictions immediately useful;
- a learning loop that improves only through forward evidence rather than retrospective score tuning.

### 10/10 end state

Options Alpha becomes a first-class live research/signaling desk that can discover unusual campaigns, explain the evidence, show what was knowable at decision time, abstain honestly, learn prospectively, graduate only statistically earned families, and ultimately hand a complete exact-option research plan into the existing Issue Desk without creating parallel authority or lifecycle systems.

---

## 2. Current canonical capability ledger

The dead-looking Terminal surface understates the current estate.

| Capability | State | Canonical evidence / interpretation |
|---|---|---|
| ThetaData canonical options source/data plane | `PROVEN_LIVE` | `DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA` names ThetaData for EOD chains, OI, Greeks/IV, trade+NBBO, and Terminal intraday; AD-1T1 separately supplies current production evidence for the T1 source spine. |
| Full-universe ThetaData T1 incremental cadence | `PROVEN_LIVE` | `WS:ADVANCED-DATA-OPTIONS` records AD-1T1 proof on two consecutive normal sessions and source coverage `0.9467 >= 0.90`. |
| AD-1 EOD Options Intelligence Brief implementation | `BUILT_NOT_PROVEN` end-to-end | Producer is merged; canonical source blocker was solved by AD-1T1; product consumer/acceptance remains AD-1T2. |
| Live flow event production | `PARTIAL` as a product dependency | Existing `com.mastermind.liveflow` M1/R2 plane and Macro `live_flow` code are the source to extend; the architecture authorizes no second collector. Current separate Intraday Flow P0 workstream still carries its own production-proof status. |
| Durable Flow ML population | `PROVEN_LIVE` accrual / `DARK_OR_DISCONNECTED` scoring | `data/flow_signals/gate.json` at the action-time base records `69,041` rows, `25` sessions, `scored:false`, `status:building_history`, and zero scored rows. |
| FS-3 flow-score preregistration | `SPEC_ONLY` (ratified research source law) | `research/OPTIONS_ALPHA_FLOW_SCORE_AMENDMENT.md` is Fable-ratified and separates the unsigned event-quality target from future signed direction. Ratified architecture is not runtime proof. |
| FS-4 model/trainer implementation | `BUILT_NOT_PROVEN` / pre-gate | `scripts/ops_train_flow_score.py`, `lib/flow_score.py`, and `config/flow_score.yml` exist. The configured feature list expects measured quote-rule inputs that the durable live-event ledger does not currently preserve completely. |
| Options signal episode evidence | `PARTIAL` | Current committed campaign checkpoint binds `5,263` immutable episodes and the v1 contract preserves exact PIT identity with zero authority. The committed file proves evidence exists; it is not by itself proof that every producer/consumer is currently live. |
| Options campaign revision/outcome evidence | `PARTIAL` | Current committed checkpoint binds `5,041` campaign records and `17,136` campaign outcome rows; `training_eligible:false` and all authority booleans false. Runtime liveness is not inferred solely from the committed checkpoint. |
| Exact option P&L on episode outcomes | `NOT_BUILT` in v1 | `options.signal_episode_outcome/v1` intentionally declares option outcomes unavailable because no executable NBBO quote path is attached. |
| Options Alpha Terminal primary surface | `DARK_OR_DISCONNECTED` from the useful evidence estate | It consumes `options.prophet_shadow/v1`, a projection intentionally forbidden from inventing direction, probability, contract, or lifecycle. |
| Current Terminal heuristic Flow Score | `BUILT_NOT_PROVEN` as a presentation heuristic / `REJECTED_BY_DESIGN` as alpha probability | `terminal/lib/flowScore.ts` is a deterministic fixed-weight attention heuristic. This architecture does not infer production proof from source code, and the heuristic must not compete semantically with governed Macro calibration. |
| Operator Issue Desk | `BUILT_NOT_PROVEN` as the intended operator boundary | Existing `options.issue_desk/v1` implementation owns operator research-plan records and prevents automatic rank/gate/size/trade authority. OA-0 does not claim production acceptance without a separate receipt. |
| MomoEdge completion benchmark | `SPEC_ONLY` (registered research ruler) | Catch-up and surpass are frozen prospectively in `research/momoedge/MOMOEDGE_COMPLETION_BENCHMARK_PREREG_2026-08-11.md`; registration is not completion evidence. |

### Key organizational disagreement repaired by this architecture

`WS:ADVANCED-DATA-OPTIONS` correctly marks AD-1T1 `PROVEN_LIVE` and says AD-1T2 is next, but its bottom-level `next_action` still instructs a fresh session to execute AD-1T1. That stale projection is corrected to AD-1T2 in this records carrier so future sessions do not repeat solved infrastructure.

---

## 3. Canonical ownership freeze

### 3.1 `options-intelligence` owns upstream market intelligence

The project-level `options-intelligence` program remains the canonical home for Macro options flow, structure, exposure, dislocation, EOD intelligence, upstream evidence semantics, and product-facing intelligence artifacts.

This OA-0 architecture **does not create a second options-intelligence program**.

### 3.2 `options-alpha` remains the research/evaluation program

The existing `options-alpha` program remains the research-program owner for:

- hypotheses;
- preregistration;
- feature science;
- cohort design;
- prospective calibration;
- model/challenger evidence;
- promotion evidence and negative results.

It does not become the execution system, portfolio sizer, or raw data plane.

### 3.3 Terminal owns the interactive product composition

The `mastermind-terminal` repository owns the responsive Options Alpha user journey, interaction patterns, visual hierarchy, product-state rendering, and the distinction between attention, research evidence, calibrated probability, and operator issue states.

Terminal must consume upstream contracts; it must not manufacture upstream alpha semantics in browser code.

### 3.4 Existing episode/campaign owners remain canonical

`options.signal_episode/v1` and `options.signal_campaign/v2` remain the durable point-in-time evidence and campaign owners. OA-0 creates no second campaign database and no second episode lifecycle.

### 3.5 Existing Issue Desk remains the operator-issuance boundary

A promoted research signal may eventually propose an exact option research plan to `options.issue_desk/v1`. OA-0 creates no second issuance queue or trade manager.

### 3.6 Existing live-flow source plane remains the only intraday source plane

This architecture extends the currently accepted ThetaData/live-flow path. It does not adjudicate a new host/runtime ownership label and does not authorize a duplicate collector. Any action-time implementation must inherit the current `com.mastermind.liveflow` / M1 / R2 and Terminal consumer boundaries then in force.

---

## 4. Chosen architecture

Three approaches were considered.

### A. Terminal-first heuristic fusion — rejected

Terminal could combine the current Tape, GEX, IV, OI, flow, and heuristic `flowScore.ts` into a larger 0–100 signal.

**Rejected because:** it would be fast to render but would create another uncalibrated score, duplicate upstream semantics, violate the separation between salience and predictive authority, and risk `DNR:KILL-FUSED-COMPOSITE` / `DNR:KILL-POSITIONING-FUSION` violations.

### B. Canonical campaign + calibration architecture — selected

Reuse the existing event, episode, campaign, EOD, outcome, and Issue Desk owners. Add missing microstructure truth, then compose a new zero-authority Options Alpha research-candidate view that can accrue outcomes and eventually consume separately promoted statistical families.

**Selected because:** it preserves the estate, creates a real learning flywheel, supports an immediately useful product before probability promotion, and cleanly separates observation, research candidacy, calibration, signal authority, and operator issue.

### C. Prophet-only options fusion — rejected as the primary product

Options evidence could flow only into the Prophet US conditional-fusion arena.

**Rejected because:** Prophet is a legitimate future consumer, but making it the only consumer would shrink Options Alpha into a confirmer of equity plans instead of building the standalone options intelligence product the Chairman requested. Any Prophet use remains governed by Prophet's own conditional-fusion law and does not replace Options Alpha.

---

## 5. Canonical data and intelligence flow

```text
ThetaData / licensed OPRA
        │
        ├──────── intraday trade + NBBO ────────┐
        │                                        │
        │                                 settled EOD options
        │                                        │
        ▼                                        ▼
existing live-flow event truth             AD / ThetaData spine
(event identity, premium,                  (OI, ΔOI facts, IV,
contract, DTE, clocks)                     skew, term, GEX context)
        │                                        │
        ▼                                        │
measured microstructure                         │
(NBBO execution location,                       │
spread, sizes, coverage)                        │
        │                                        │
        ├───────────────┬────────────────────────┘
        │               │
        ▼               ▼
Flow ML population   existing episode/campaign spine
        │               │
        └───────┬───────┘
                ▼
      options.alpha_candidate_feed/v1
   derived view; no new lifecycle or truth DB
                │
        ┌───────┴─────────┐
        ▼                 ▼
     ABSTAIN       RESEARCH CANDIDATE
                          │
                   prospective outcomes
                          │
                   registered calibration
                          │
                 separately promoted family
                          │
                    CALIBRATED SIGNAL
                          │
                    existing Issue Desk
                          │
                 exact-option lifecycle/outcome
```

### Core law

**Attention ≠ research candidate ≠ calibrated probability ≠ promoted signal ≠ operator issue ≠ trade.**

The product must preserve those distinctions visibly and contractually.

---

## 6. Observation truth and microstructure contract

### 6.1 What is missing today

The preregistered Macro Flow ML feature set expects event-time features such as:

- `at_ask_share`;
- `at_bid_share`;
- `aggression_share`;
- `vol_gt_oi_ratio`;
- related event-time execution/microstructure context.

The current durable Flow ML live-event ledger does not preserve all of those measured fields. The trainer can fill absent fields with NaNs; therefore merely running FS-4 harder could create a technically complete but information-starved model.

Separately, current Chain Heat maps soft `side` values into synthetic ask-share values (`~buy → 0.80`, `~sell → 0.20`, `mixed → 0.50`). That mapping may remain as clearly labeled legacy display behavior, but **it is not measured NBBO truth and may not be consumed as Alpha training truth or calibrated signal evidence**.

### 6.2 Required measured microstructure

The existing trade+NBBO path should expose a versioned event-time `microstructure` block with at least:

- observation coverage: number/percent of premium with a valid contemporaneous NBBO;
- premium-weighted execution-location shares: `at_ask`, `at_bid`, `inside`, `outside`;
- spread statistics in dollars and percent;
- bid/ask sizes where supplied by the licensed source;
- trade/quote age or exact source timestamp relationship;
- condition / exchange evidence internally when rights and schemas permit;
- deterministic derived measures such as `aggression_balance = at_ask_share - at_bid_share`;
- explicit unknown/null when coverage is insufficient.

No field may be named as buyer identity, institutional intent, opening intent, or directional conviction unless the measurement actually establishes it.

### 6.3 `volume > prior OI` language

`vol_gt_prior_oi` means exactly what it says: current-session volume exceeded known prior OI. It may be called an **opening-pressure proxy** or **volume exceeds prior OI**. It is not proof that current trades opened new positions.

Actual opening confirmation is a later settled-OI observation and must remain a later evidence update.

### 6.4 Event-stage versioning

Preferred OA-1 path: add backward-compatible optional microstructure fields inside the existing live event object while preserving the outer `live_flow.event_stage/v1` decision/availability receipt shape and stable event identity.

**Entrance gate:** a complete consumer census must prove no current v1 consumer hard-enumerates the nested event shape in a way that rejects the additive fields. If such a consumer exists, OA-1 must introduce a reviewed `live_flow.event_stage/v2` rather than weakening the consumer or silently changing v1 semantics.

### 6.5 Flow ML ledger versioning

`data/flow_signals/ledger.parquet` remains the existing single-writer population. New microstructure columns are additive. Historical rows remain null unless an independently lawful historical tape reconstruction can populate a separately identified cohort; no later data may be backfilled into old live-feed rows as if known at event time.

---

## 7. Existing episode and campaign contracts remain frozen

### 7.1 `options.signal_episode/v1`

Do not mutate v1 merely to make OA-1 convenient.

Its constraints are valuable history protection:

- stable episode identity;
- `event_time <= observed_at <= decision_at <= available_at`;
- exact NYSE-session anchoring;
- durable source artifact and OI vintage rules;
- soft flow-side semantics;
- zero authority;
- option outcome unavailable.

OA-1 candidate composition may bind the source event's newer microstructure evidence to the existing `source_event_id` / `episode_id` without rewriting the v1 episode row.

If research later proves microstructure must become part of the immutable episode itself, that is a separate `options.signal_episode/v2` design with explicit consumer migration. It is not an OA-1 shortcut.

### 7.2 `options.signal_campaign/v2`

The existing exact-contract/session campaign remains canonical. It already retains campaign revisions and outcome coverage while granting zero score/select/issue/trade authority.

OA-0 does not mint a second campaign identity to represent multi-strike or multi-expiry behavior. Ticker-wide campaign composition starts as a **derived read** over canonical exact-contract campaign revisions.

If prospective research later proves a persistent cross-contract campaign identity is necessary for learning, the change must extend the existing campaign owner through a separately reviewed contract version.

---

## 8. New derived candidate view

### 8.1 Contract identity

Introduce a derived product contract:

```text
options.alpha_candidate_feed/v1
```

This is a regenerable read/view artifact, not a new truth store, queue, lifecycle database, or execution ledger.

### 8.2 Candidate identity

A candidate's stable identity is derived from:

- candidate schema/version;
- formation-policy version;
- the canonical campaign revision that first satisfies the frozen research-formation rule.

The exact formation threshold is **not** chosen by OA-0 based on retrospective outcome performance. OA-1C must preregister the deterministic threshold/logic before prospective candidate outcomes are read.

### 8.3 Candidate states

The feed supports at least:

- `research_candidate`;
- `abstain` / no candidate;
- `stale` / degraded evidence;
- later `calibration_available` metadata when a family passes its own gate.

A research candidate is allowed to describe observed evidence families such as:

- call-side ask aggression;
- put-side ask aggression;
- contested/mixed execution;
- unusually large premium;
- repeated exact-contract activity;
- multi-contract recurrence;
- volatility demand context;
- structural alignment or contradiction.

It may not state a calibrated bullish/bearish probability unless a separately preregistered signed/right-conditioned family has earned that authority.

### 8.4 Candidate payload principles

A candidate should include:

- stable candidate/campaign/event IDs;
- ticker and exact campaign contracts;
- event/decision/available/published clocks;
- formation-policy version and evidence digest;
- intraday microstructure evidence with coverage;
- price response since campaign onset as descriptive evidence;
- settled EOD context available at decision time;
- later post-decision confirmations as separately clocked updates;
- contradictions;
- explicit missingness;
- calibration status, sample N, registered horizon and probability only when lawfully available;
- authority object showing no automatic trade authority;
- provenance receipts for every evidence family.

### 8.5 No silent fallback to `options.prophet_shadow/v1`

The existing shadow projection remains historical/research/readiness evidence during migration. Once the candidate feed is proven as the Options Alpha primary product path, the Terminal must not silently fall back to the old shadow projection and make a broken new feed look healthy.

A new-feed failure renders a truthful degraded state.

---

## 9. Clock, point-in-time, null and correction law

### 9.1 Candidate clock order

For an intraday candidate:

```text
event_time <= observed_at <= decision_at <= available_at <= published_at
```

A candidate may only cite an evidence leg as **formation evidence** if that leg's own availability time is no later than the candidate decision/availability contract permits.

### 9.2 Settled EOD context

If an NVDA candidate forms Tuesday at 11:05 ET:

- Monday's already-settled OI/IV/skew/GEX evidence may be used if its source receipt was available before the Tuesday candidate decision;
- Tuesday's OI that settles after the close may **not** be retroactively inserted into the Tuesday 11:05 formation evidence;
- Tuesday-settled OI may later appear as a separate post-decision update: `confirmed`, `failed_to_confirm`, `unavailable`, etc., with its own availability clock.

### 9.3 Null law

Missing is not zero. Uncovered is not neutral. Unavailable EOD context is not a weak positive or weak negative. Insufficient NBBO coverage cannot produce a synthetic aggression percentage.

### 9.4 Correction law

Corrections never rewrite the original decision receipt or candidate formation rationale in place. A correction/newly available fact is an append-only or versioned update with its own source identity and clock. Any statistical label joins against the frozen decision-time version.

### 9.5 Freshness law

A fresh wrapper/build time can never make stale source evidence fresh. User-visible freshness is derived from source clocks and coverage, not publication time alone.

---

## 10. EOD evidence composition

The OA-1 candidate view may compose settled EOD evidence from the canonical ThetaData/AD spine, subject to exact availability and source receipts.

Evidence families should remain independently visible:

### Positioning/structure

- OI counts and concentration;
- matched-contract day-over-day OI change as descriptive fact;
- walls / gamma flip / GEX context with existing assumption labels;
- expiry topology.

### Volatility

- ATM IV;
- IV rank/history;
- skew level/change;
- term structure;
- realized-vol/IV context or VRP when its owner contract permits;
- expected move.

### Intraday

- premium magnitude;
- measured NBBO execution location;
- recurrence/persistence;
- exact-contract / strike / expiry topology;
- price response / lead-vs-chase descriptives.

### Context

- lawful market/regime context;
- catalyst/event facts when available under their owners;
- explicit evidence gaps.

**No generic weighted confluence score is authorized by this composition.** Under current `DNR:KILL-POSITIONING-FUSION`, a new Options Alpha predictive score/ranker may not fuse OI/GEX/other positioning keys merely because the features are available or preregistered. The first OA families therefore do not gain new predictive positioning inputs from this architecture. Existing ratified families keep only the exact feature authority they already possess. Any future OA family that wants to add EOD positioning/structure keys to a predictive score requires an explicit DNR scope adjudication/amendment **before** the test, not just an ordinary model preregistration.

---

## 11. Statistical and model authority

### 11.1 Existing FS family is preserved

The Fable-ratified S-FLOWML family remains a useful event-quality/meta-label research family. Its current target is intentionally unsigned: it estimates an underlying outcome as registered, not "this call means stock up" or "this put means stock down."

OA-0 does not silently repurpose that target or widen its registered features with new EOD positioning keys.

### 11.2 FS-5 remains required

The existing FS-4 implementation does not earn authority merely because code exists. Before any Macro calibrated score becomes a product probability:

- measured event-time microstructure features must be correctly populated;
- registered population/cohort rules must hold;
- deferred FS-5 CV/gauntlet requirements must be executed honestly;
- required sample floors and calibration tests must pass;
- the promotion decision must be separately adjudicated;
- the promotion review must explicitly check current `DNR:KILL-FUSED-COMPOSITE` applicability. The existing FS registration is research source law, not by itself a live-authority exception. If the current DNR scope is ambiguous for a trained calibrated probability, an explicit DNR adjudication is a promotion prerequisite rather than something an implementation worker may infer.

`config/flow_score.yml` remains `scoring.enabled: false` until that process is satisfied.

### 11.3 Future signed/right-conditioned family

A legendary Options Alpha product eventually needs a separate right-conditioned directional family. That family must be preregistered after the necessary labels and quote truth exist.

It must not:

- reuse the unsigned FS score under a new label;
- assume call-buy = stock-up or put-buy = stock-down without grading;
- use the suspended tick-rule Theta tape as directional authority;
- revive a killed DOI/skew/charm thesis by renaming it;
- add positioning-fusion features without the explicit DNR scope ruling required by §10;
- convert LLM narrative into signal authority.

A signed family may be promoted only through its own prospective/OOS gate and exact declared horizon.

### 11.4 LLM role

An LLM may:

- summarize measured evidence;
- explain what changed;
- identify explicit contradictions already present in structured evidence;
- generate human-readable descriptions with source receipts.

It may not:

- originate a candidate from prose alone;
- change candidate state;
- create a numeric probability/confidence;
- rank, gate, size, issue, or escalate a candidate;
- override deterministic/statistical abstention.

---

## 12. Product experience architecture

### 12.1 Five-second hierarchy

The primary Options Alpha screen should answer in this order:

1. **Is the live evidence plane healthy?**
2. **What research candidates are forming now?**
3. **Why now?**
4. **What supports and contradicts the candidate?**
5. **What is historically calibrated, and what is still accruing?**
6. **What exact evidence/clocks can be inspected?**

Readiness plumbing should not dominate the entire screen.

### 12.2 Header / health strip

Compact, glance-tier health should include:

- intraday source age;
- measured NBBO coverage;
- current/last settled EOD session;
- count of live candidates;
- calibration state;
- stale/degraded reason when applicable.

### 12.3 Candidate stream

A representative card should feel like:

```text
NVDA · Research Candidate · Formed 10:43 ET
Call-side campaign across 4 contracts · 2 expiries · $8.4M · 31m persistence
Execution: 74% premium at ask · 9% at bid · 17% inside · median spread 4.2%
Price response: +0.18σ since onset — descriptive, not a direction claim
Settled structure: OI change context · IV rank 42 · skew firming · above gamma flip
Contradiction: front IV elevated relative to realized vol
Learning: signed probability not promoted · comparable outcomes N=...
Clocks: event ... · decision ... · available ...
```

The exact copy is a later design task; the semantics above are frozen.

### 12.4 Campaign detail

Selecting a card opens:

- exact event timeline;
- strike and expiry map;
- cumulative premium and recurrence;
- measured NBBO aggression evolution;
- underlying-price response;
- settled OI/IV/skew/GEX evidence;
- later confirmations clearly separated from decision-time evidence;
- contradictions;
- registered outcome history / calibration when available;
- receipts and clocks.

### 12.5 Research & Calibration secondary panel

Current readiness, forward-ledger, calibration, withheld-trajectory, and research-gate material remains available but moves behind the primary live research workflow.

### 12.6 Empty state

A healthy empty state is informative:

> No research candidate has formed yet. Live tape healthy. 27 campaigns observed; none crossed the frozen formation rule.

Zero candidates is a valid result.

### 12.7 Degraded state

Examples:

- "Live tape stale — new candidate formation paused. Existing candidates shown with last-good source clocks."
- "NBBO coverage insufficient — magnitude and contract topology available; execution-location evidence withheld."
- "Settled EOD context unavailable — no structure-alignment claim can be formed."

### 12.8 Responsive/bilingual acceptance

Every primary state must be designed and production-proven at the same minimum breakpoint family used by the MomoEdge completion benchmark:

- 390×844;
- 768×1024;
- 1440×900;
- English and Chinese;
- no hidden freshness disclosure, clipped primary action, inaccessible lifecycle state, or horizontal overflow.

### 12.9 Initial placement vs future information architecture

The first vertical should reuse the existing Options/Prophet/Options Alpha mount rather than widen OA-1 into a full navigation rewrite. Once the real candidate stream is proven useful, a dedicated first-class signaling destination may be evaluated as a separate experience decision.

---

## 13. Attention heuristic vs calibrated probability

Terminal currently carries a fixed-weight `flowScore.ts`. OA-0 freezes the semantic split:

### `Attention` / `Salience`

- deterministic presentation heuristic;
- useful for ordering what deserves visual attention on Tape/Flow surfaces;
- not probability;
- not alpha;
- not promoted signal authority;
- never used to claim historical edge.

### `Calibrated Outcome Probability`

- Macro-owned statistical output;
- only exists when the relevant registered family passes its prospective gate **and** any required current DNR authority adjudication;
- carries model/family/version, horizon, cohort, N, calibration status and receipts;
- never silently falls back to the heuristic.

The two must not both be labeled "Flow Score."

---

## 14. Failure-state and safety matrix

| Failure | Required behavior |
|---|---|
| Live-flow source stale | Pause new candidate formation; retain last-good candidates as stale; never refresh via wrapper clock. |
| NBBO coverage too low | Withhold aggression fields; show magnitude/topology only; no synthetic `0.80/0.20` substitution. |
| EOD context missing/stale | Mark unavailable; do not assert alignment/contradiction that depends on it. |
| EOD evidence becomes known later | Add as post-decision update; never rewrite formation evidence. |
| Model missing/not deployable | Probability null; research candidate may remain useful. |
| Zero candidates | Healthy abstention state, not error. |
| Candidate feed fails after migration | Explicit degraded state; no silent fallback to old shadow feed. |
| Existing campaign/episode ledger corrupt or prefix changes | Fail closed; do not create a replacement ledger. |
| Source disagreement | Preserve owner-specific evidence and escalate for reconciliation; no majority-vote truth. |
| LLM unavailable | Structured candidate remains fully functional; explanation can degrade independently. |
| Exact option quote missing | Exact-option return/lifecycle cell remains unavailable; no mid/EOD/underlying substitute. |

---

## 15. DO NOT REBUILD / house-law compliance

This architecture was reviewed against current `research/DO_NOT_REBUILD.md` at the action-time base.

### Binding DNRs

- **`DNR:KILL-LLM-ORIGINATION`** — satisfied: LLMs explain only; no origination/score/escalation.
- **`DNR:KILL-FUSED-COMPOSITE`** — satisfied at OA-0: no generic blended alpha score is introduced. OA-2 promotion must explicitly adjudicate current scope for any trained calibrated probability rather than inferring an exception.
- **`DNR:KILL-POSITIONING-FUSION`** — satisfied: OI/GEX/skew context remains separately visible; no new Options Alpha predictive score/ranker receives positioning keys under this architecture. Any future test that would fuse them requires an explicit DNR scope ruling before testing.
- **`DNR:HOLD-THETA-TAPE`** — satisfied: suspended tick-rule direction is not used as directional authority. Measured trade-vs-NBBO execution location is treated as deterministic microstructure evidence, not tick-rule sign authority.
- **`DNR:KILL-DOI-FAMILY`** — satisfied: the killed DOI signal family is not revived. Matched-contract OI change may be displayed as native descriptive context; it carries no new OA score/rank/gate weight unless a future explicit adjudication changes that scope.
- **`DNR:KILL-SKEW-DECELERATION`** — satisfied: skew level/change may be displayed as context; the unsupported skew-deceleration bullish thesis is not reintroduced.
- **`DNR:KILL-CHARM-NARRATIVES`** — satisfied: OA-0 does not create signed-charm directional narratives.
- **`DNR:KILL-OFFHORIZON-VERDICTS`** — satisfied: statistical verdicts remain bound to preregistered horizon roles.
- **`DNR:KILL-DIRECTIONAL-SHORTING`** — OA-0 grants no generalized short-side authority and does not reuse the killed L1 short lobe. Any future bearish/right-conditioned options family requires its own lawful preregistration and cannot inherit authority from the killed construction.
- **`DNR:KILL-OPTIONS-CONTEXT-AUDIT-OWNER-EVICTION`** — satisfied: no owner/window eviction or parallel context-audit store is proposed.

### No-rebuild boundaries

Do not create:

- another ThetaData Terminal instance;
- another live-flow poller/store;
- another event identity;
- another campaign ledger;
- another outcome ledger for the same logical unit;
- another Issue Desk;
- another rank/gate/sizing control plane;
- another generic options "super score";
- a retrospective replacement for missing point-in-time NBBO.

---

## 16. MomoEdge benchmark role

`research/momoedge/MOMOEDGE_COMPLETION_BENCHMARK_PREREG_2026-08-11.md` remains the frozen non-post-hoc competitor ruler.

OA-0 uses competitor research for jobs-to-be-done, not proprietary code/corpora/branding.

### Catch-up remains a workflow claim

Feature parity alone is not completion. Catch-up still requires live production workflow, cadence truth, exact-option lifecycle/return readiness, bilingual/mobile acceptance, and honest authority.

### Surpass remains a prospective outcome claim

No retrospective win-rate or marketing comparison can prove superiority. Surpass still requires the registered common exact-option NBBO basis, minimum covered sessions/outcomes, and the frozen statistical comparison.

---

## 17. Ordered implementation waves after written-spec approval

This section freezes dependencies and boundaries, **not** an implementation task plan. The detailed implementation plan is created only after the Chairman approves this written spec.

### AD-1T2 — complete the EOD consumer path

Owner: `WS:ADVANCED-DATA-OPTIONS`.

Mission: restore the store-bearing M1 to the actual theta-m1 product workflow and production-prove AD-1 end to end, including a lawful exact availability clock usable by later PIT composition.

AD-1T2 is a dependency for OA-1C's EOD confluence. It is not a reason to delay independent microstructure contract work if paths/authority are disjoint.

### OA-1T-Macro — measured live microstructure

Mission: measured trade+NBBO microstructure reaches the existing live event path and durable Flow ML population without a second collector or synthetic ask-share substitution.

Stop condition: one untouched RTH event carries exact source clocks, measured NBBO coverage/execution-location evidence, stable existing event identity, and a durable record on the real path.

### OA-1T-Terminal — immediate Tape evidence value

Mission: Terminal exposes the measured aggression/spread evidence from the existing Flow path and renames the old heuristic from Flow Score to Attention/Salience semantics.

Entrance collision gate: reconcile any active PR touching the shared Flow resolver/stream path, including Terminal PR #422 while it remains open.

### OA-1C-Macro — research-candidate composer

Mission: publish `options.alpha_candidate_feed/v1` as a derived, zero-authority view composing canonical campaign, measured microstructure, and only point-in-time lawful settled EOD evidence.

Formation policy must be preregistered before prospective candidate outcomes are read.

### OA-1C-Terminal — Options Alpha becomes alive

Mission: the Options Alpha primary lane becomes the candidate stream/detail experience, with healthy empty/degraded states and Research & Calibration secondary material.

### OA-2 — FS-5 completion

Mission: execute the existing preregistered flow-event model gauntlet using correctly populated event-time features. Preserve the existing unsigned event-quality target and do not widen it with new positioning-fusion features. Any live probability promotion remains separately adjudicated under current DNR law.

### OA-3 — exact-option NBBO outcome/lifecycle

Mission: add a separately versioned option-outcome contract under the existing episode/lifecycle owner, using exact ask-to-bid NBBO rules and no mid/EOD/underlying substitution.

### OA-4 — signed/right-conditioned research family

Mission: preregister and test a separate directional family using lawful event-time evidence and exact registered horizons. Promotion only through its own prospective/OOS gate, with any required DNR scope ruling obtained before a prohibited feature/test is attempted.

### OA-5 — existing Issue Desk integration

Mission: promoted options signals can produce complete operator-review proposals for the existing Issue Desk, with exact contract, quote, trigger/invalidation, targets, lifecycle, evidence digest and falsifier where the evidence warrants them.

No automatic brokerage authority is granted.

---

## 18. First independently useful production milestone

Options Alpha is considered **alive** when all of the following are simultaneously true on one real untouched RTH event/campaign:

1. Canonical ThetaData trade+NBBO enters the existing live-flow path.
2. Measured NBBO microstructure is durably preserved; no synthetic ask-share stands in for it.
3. The event resolves to existing episode/campaign identity rather than a new lifecycle.
4. Only EOD evidence that was genuinely available at decision time is composed as formation evidence.
5. A `research_candidate` or explicit abstention is produced through `options.alpha_candidate_feed/v1`.
6. The deployed Terminal displays the candidate with exact clocks, evidence, contradictions, missingness and calibration status.
7. The candidate automatically enters the existing prospective outcome-learning path.
8. A no-candidate day renders a healthy informative abstention state.
9. Desktop/tablet/phone, EN/ZH, and stale/degraded cases are browser-proven.
10. No rank/gate/size/trade authority was smuggled in through a heuristic or LLM.

Green CI, a merged schema, a populated fixture, or a screenshot of a static card does not satisfy this milestone.

---

## 19. Acceptance standard for later promotion

Long-form program completion requires all four layers:

### Truth

- current licensed inputs;
- exact clocks and vintages;
- correction-safe evidence;
- source coverage/freshness;
- no synthetic replacement for missing NBBO.

### Intelligence

- structured event/campaign facts;
- independent EOD context families;
- transparent candidate formation;
- prospectively calibrated models where earned and lawful under current DNR scope;
- exact-option outcomes.

### Product

- coherent live candidate workflow;
- healthy abstention/degraded states;
- actionable evidence detail;
- responsive bilingual experience;
- existing operator Issue Desk handoff.

### Learning

- prospective candidate denominator;
- immutable outcomes;
- model/calibration monitoring;
- instrumentation showing whether candidates improve research/discovery/decision quality;
- MomoEdge catch-up/surpass gates evaluated only on their frozen basis.

---

## 20. Current collisions and held work

At the architecture-freeze action time:

- no `oa0` or `options-alpha` implementation branch was found in Macro;
- no competing OA-0 carrier was adopted;
- Macro PR #6546 modifies Agent OS parser/schema semantics for typed waits but does not own this business architecture. This records carrier does not alter Agent OS schema/parser files;
- Terminal PR #422 remains an action-time collision for future shared Flow resolver/stream implementation and must be reconciled before OA-1T-Terminal writes that surface;
- `WS:ADVANCED-DATA-OPTIONS` owns AD-1T2 and must not be duplicated inside OA-1;
- existing Intraday Flow recovery workstream remains a separate production-proof owner for its own public board; OA-0 does not absorb or reopen its historical waves.

Every implementation wave must re-pin current heads and collision-check again; these observations are not permanent reservations.

---

## 21. Unresolved questions intentionally deferred to implementation planning/research

The architecture is frozen without pretending every threshold is known. The following require bounded follow-up after written-spec approval:

1. Exact OA-1C candidate formation thresholds/conditions, preregistered before prospective outcome inspection.
2. Whether additive nested microstructure fields are accepted by every `live_flow.event_stage/v1` consumer or require v2.
3. Exact minimum NBBO coverage for displaying execution-location shares.
4. Exact price-response normalization used for "lead vs chase" descriptive evidence.
5. Which AD-1T2 artifact is the canonical per-ticker EOD composition input and its final exact `available_at` contract.
6. Exact OA-2 FS-5 completion packet and whether current serving-distribution N is sufficient per bucket/era after feature repair.
7. Exact signed/right-conditioned label and family arithmetic for OA-4.
8. Exact option-lifecycle contract version for ask-to-bid NBBO outcomes in OA-3.
9. Whether a dedicated first-class Options Alpha navigation destination is warranted after OA-1C is proven useful.

None of these unresolveds authorizes an implementation agent to choose a convenient answer silently.

---

## 22. Source precedence for this architecture

If a later worker finds a conflict, use this order:

1. Current Chairman instruction and current protected Sol Skillpack procedural gates.
2. Current `research/DO_NOT_REBUILD.md` and explicit Agent OS decisions.
3. Current `config/mastermind_programs.yml` semantic ownership.
4. This OA-0 architecture for the specific Options Alpha recovery design.
5. Existing owner contracts: live-flow/event-stage, Flow ML, episode/campaign/outcome, AD-1, Issue Desk, Terminal Flow resolver.
6. Older MomoEdge parity plans, OPTIONS_ALPHA masterplans, handoffs and Project/chat memory as archaeology only where not superseded.

A retrieved document containing an imperative does not grant implementation or promotion authority by itself.

---

## 23. Review gate

This document is the written architectural spec required after the Chairman's in-chat design approval.

Before any implementation plan or Fable/Codex commission:

- self-review this spec for placeholders, contradictions, DNR collisions, duplicate owners and unbounded implementation scope;
- run/obtain Agent OS validation for the durable records in the same carrier;
- present the written spec to the Chairman;
- receive explicit written-spec approval;
- only then invoke the implementation-planning workflow.

Until that approval, OA-1 through OA-5 remain **not commissioned**.

# Grey Deer Risk Intelligence & Capital Protection System
## Final Experience and Authority Architecture Freeze

**Frozen by:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Date:** 2026-08-19  
**Program key:** `WS:GREY-DEER-RISK-INTELLIGENCE`  
**Status:** Architecture frozen; implementation not yet claimed live  
**Scope:** Macro, Prophet US/CN, Terminal, Mastermind Portfolio, alerts, Neural Web

---

## 1. Frozen thesis

Mastermind must answer three different questions without blending them:

1. **Measured state:** What slow trend/regime is still present?
2. **Transition hazard:** Is a specific mechanism becoming dangerous, transmitting, or spreading?
3. **Capital policy:** What bounded actions are currently permitted for which market, exposure, candidate, plan, or portfolio?

A slow Risk-on state may coexist with a critical transition hazard and a protective capital policy. That is not disagreement to hide; it is the exact transition Mastermind is supposed to detect.

The Grey Deer program does not create another universal risk score. It composes existing market organs into a canonical, provenance-backed `risk_envelope.v1` and lets only separately registered, separately promoted, scope-bounded reflexes carry action authority.

---

## 2. Final semantic model

### 2.1 Orthogonal states

The product carries five independent state dimensions:

- `measured_state`: `RISK_ON | MIXED | RISK_OFF` plus the existing slow score.
- `hazard_stage`: `NONE | FRAGILE | ARMED | TRIGGERING | TRANSMITTING | BREAKDOWN | CONTAGION | RESOLVED | EXPIRED`.
- `repair_state`: `NONE | IMPULSE | BROADENING | CONFIRMED | FAILED`.
- `data_state`: `FRESH | PARTIAL | DEGRADED | STALE | UNKNOWN`.
- `coherence_state`: `ALIGNED | MIXED | CONTRADICTORY`.

`repair_state`, `data_state`, and `coherence_state` are not severity levels. A market can be `BREAKDOWN + REPAIR_IMPULSE + FRESH + MIXED`.

### 2.2 Capital-posture summary

The user-facing summary is:

- `NORMAL`
- `SELECTIVE`
- `PROTECTIVE`
- `DEFENSIVE_ONLY`
- `NO_NEW_RISK`
- `EMERGENCY`

This is a display projection of active policies. It owns no authority. Every actual action remains traceable to one registered policy rule.

---

## 3. Canonical ownership

### Macro repository

Owns market observations, hazard experts, risk episodes, the settled/live Risk Envelope, Prophet market-eligibility sidecars, public dashboard projection, and engine-originated alerts.

### Prophet

Owns raw candidate discovery, rank, entry availability, plans, lifecycle, and outcome cohorts. Market risk may restrict actionability after rank; it may not rewrite the raw rank or erase the counterfactual candidate.

### Terminal

Owns interactive presentation, workspace state, alerts, and user controls. It mirrors the Risk Envelope and never recomputes market risk.

### Mastermind Portfolio

Owns positions, book mandates, user authority, sizing, settlement, and paper execution. It consumes the Risk Envelope and combines it with book-specific state. It must not independently recreate market truth.

### Neural Web / LLMs

May explain, compare, retrieve, challenge, and de-escalate. They may not originate hazards, numeric probabilities, escalations, policies, gates, sizes, or exits.

---

## 4. Canonical topology

```text
Existing domain organs
  Market State / Risk Radar / Anticipation / Velocity / Transmission
  Market Drivers / Leadership Crack / Breadth / Correlation / Credit
  FX-Carry / Intl Contagion / PBOC / Live Tape / Prophet Board Health
                     │
                     ▼
         engine/risk_envelope.py  (pure composer)
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
site/riskdata/              site/live/
risk_envelope.json          risk_envelope.json
settled canonical           live provisional
projection                  no durable writes
        │                         │
        └────────────┬────────────┘
                     ▼
 Macro UI / Prophet sidecar / Alerts / Terminal / Portfolio / Neural Web
                     │
                     ▼
 Scoped registered reflexes only
                     │
        Chronicle transitions + QLedger/Evaluation OS grading
```

### Durable-history ruling

- **Chronicle** owns settled cross-domain state-transition history.
- **Reflex Registry** owns bounded trigger-to-action firing ledgers.
- **Evaluation OS / QLedger** owns grading.
- **Signal Episode Atlas** remains the per-name technical-event memory system; it is not repurposed into a market-wide risk lifecycle store.
- The Risk Envelope itself owns no new forward ledger.

---

## 5. Final `risk_envelope.v1` contract

### 5.1 Canonical paths

- Settled public and cross-repository contract: `site/riskdata/risk_envelope.json`
- Live provisional contract: `site/live/risk_envelope.json`
- Pure composer: `engine/risk_envelope.py`
- Settled producer: `scripts/build_risk_envelope.py`
- Live producer: `scripts/build_live_risk_envelope.py`

The live and settled builders must call the same pure composer. The live path may supply fresher observations but may not fork the state or policy logic.

### 5.2 Contract skeleton

```json
{
  "schema": "mastermind.risk_envelope/v1",
  "definition_id": "grey-deer-v1-2026-08-19",
  "market": "US",
  "revision": "settled|live_provisional|corrected",
  "bundle_id": "content-addressed-serving-bundle",
  "source_session": "2026-08-19",
  "as_of": "2026-08-19T19:45:00Z",
  "observed_at": "2026-08-19T19:46:00Z",
  "produced_at": "2026-08-19T19:46:08Z",
  "stale_after": "2026-08-19T20:05:00Z",

  "measured_state": {
    "source_artifact": "market-state",
    "verdict": "RISK_ON",
    "score": 77,
    "role": "slow_confirmed_trend",
    "as_of": "2026-08-17"
  },

  "hazard_summary": {
    "stage": "TRANSMITTING",
    "primary_episode_id": "re:us:duration-growth:2026-08-13:1",
    "active_episode_count": 2,
    "stage_since": "2026-08-18T14:05:00Z",
    "display_only": true
  },

  "episodes": [],
  "policies": [],

  "policy_summary": {
    "posture": "PROTECTIVE",
    "active_policy_ids": [],
    "display_only": true
  },

  "data_state": "FRESH",
  "coherence": {},
  "coverage": {},
  "freshness": {},
  "correction": null,
  "provenance": {},

  "authority": {
    "envelope_may_rank": false,
    "envelope_may_gate": false,
    "envelope_may_size": false,
    "envelope_may_execute": false,
    "policy_actions_require_individual_authority": true
  }
}
```

### 5.3 Episode identity

`episode_id = re:<market>:<origin_complex>:<first_qualified_session>:<generation>`

- `origin_complex` is a frozen vocabulary such as `duration-growth`, `credit-funding`, `fx-carry`, `china-liquidity`, or `commodity-inflation`.
- Multiple experts attach to one episode.
- Definition changes mint a new episode lineage; history is not restamped.
- An episode may re-arm only after a recorded terminal state and a new qualifying trigger.

### 5.4 Episode fields

Each episode carries:

- family/species;
- stage and stage timestamps;
- issue/validity horizon;
- evidence, contradiction, exposure, transmission, and invalidation receipts;
- per-source clocks and quality;
- forecast only when promoted;
- repair state and remaining repair conditions;
- authority booleans for advisory, new-entry, sizing, active-plan review, and execution.

### 5.5 Policy fields

Each policy carries:

- `policy_id`, `rule_id`, `rule_version`;
- source expert and episode;
- authority basis (`earned`, `temporary_operator_safety`, or `emergency_user_opt_in`);
- market, asset, candidate, lifecycle, and exposure predicates;
- one subtract-only action;
- start, expiry, kill switch, and reversal condition;
- exact affected names/plans and counterfactual references;
- promotion record and evidence receipts.

No envelope-wide threshold may manufacture a policy.

---

## 6. Bounded policy vocabulary

### New candidates

- `ELIGIBLE`
- `NO_CHASE`
- `REDUCE_SUGGESTED_SIZE`
- `SUPPRESS_NEW_ENTRY`
- `NO_NEW_LONG_RISK`

### Existing plans or recommendations

- `OBSERVE`
- `NO_ADD`
- `PROTECTION_REVIEW`
- `EXIT_REVIEW`

### Portfolio control

- `GROSS_CAP`
- `BLOCK_NET_NEW_EXPOSURE`
- `EMERGENCY_REDUCTION`

`AUTO_EXIT` is not part of Grey Deer v1. Any future automatic held-position exit requires a separate Chairman-approved, user-opt-in, forward-only gauntlet.

### Composition law

Policies are never averaged or weighted. Every applicable rule is evaluated independently. Consumers enforce the logical intersection of separately authorized subtract-only constraints and print every rule ID. A repair rule may lift only the rule it owns; it cannot reset unrelated protection.

---

## 7. Exact product compositions

### `NONE / NORMAL`

- Hero: slow state, “No active transition hazard,” normal capital posture.
- No siren.
- Prophet raw and actionable views match.
- Method and freshness remain visible but collapsed.

### `FRAGILE`

- Copy: “Trend remains intact, but internal leadership/breadth/liquidity is fragile. No breakdown has started.”
- Amber fragility strip, no flashing animation.
- Prophet remains eligible unless a separately authorized no-chase rule applies.
- One transition alert per episode, then material-change only.

### `ARMED`

- Copy names the trigger approaching, the vulnerable exposure, and the invalidation.
- Orange Protective Watch.
- No broad block by default.
- Scoped `NO_CHASE` or size reduction only when the matching rule has authority.

### `TRIGGERING`

- First qualifying tick: visible “pending escalation” badge; no silent debounce.
- Confirmation: Protective alert and explicit affected-exposure list.
- New-entry restrictions only inside authorized scopes.

### `TRANSMITTING`

- Copy: “The trigger is now damaging the expected exposure.”
- Red protective strip and transmission timeline.
- Prophet shows actionable, risk-suppressed, and all-ranked views separately.
- Active exposed plans receive `NO_ADD` or review state if authorized.

### `BREAKDOWN`

- Site-wide siren on transition, then static red banner.
- Board-level loss breadth and simultaneous invalidations shown.
- New exposed entries suppressed under named rules.
- “No candidate clears current risk and entry rules” is a valid result.

### `CONTAGION`

- World page shows origin, market-clock propagation, and current frontier.
- Every affected regional page consumes the same episode ID.
- No generic world score is created.

### `REPAIR_IMPULSE`

- Purple/blue repair banner, never green.
- Copy: “A support/reversal impulse has appeared; protection remains.”
- No automatic re-entry or policy removal.

### `REPAIR_BROADENING`

- Show which repair conditions have cleared and which remain.
- Still no unrestricted actionability.

### `REPAIR_CONFIRMED`

Requires:

- no trigger expert remains `TRIGGERING+`;
- no contagion count is rising;
- affected board/cohort is no longer in breakdown for two settled sessions;
- critical sources are fresh;
- policy-specific invalidators have cleared.

Restrictions lift only for the policy that owns the repair. Every candidate still re-enters through fresh Prophet availability.

### `REPAIR_FAILED`

- Return to prior hazard state without minting a new episode unless a genuinely new trigger appears.
- Alert once with the failed repair receipt.

### `EXPIRED / FALSE ALARM`

- Warning closes with realized outcome, protection cost, and classification.
- It is not deleted or silently relabeled.
- The public track record includes it.

### `DEGRADED / STALE / UNKNOWN`

- No “all clear,” “receding,” or green confidence language.
- Active policies remain until their own expiry; missing data cannot lift them.
- With no active policy, behavior does not invent a new gate, but assertive action copy is demoted and the protection read is visibly unavailable.

### `CONTRADICTORY`

- Split-view composition: slow state, hazard evidence, and contradictions shown together.
- No averaging into a neutral middle score.

---

## 8. Prophet market-eligibility architecture

### 8.1 Raw board remains canonical

The raw US/CN board, board definition, raw rank, visible population, and track-record cohort remain unchanged.

### 8.2 Sidecar

Schema: `prophet.market_eligibility/v1`

Suggested paths:

- `site/factordata/us_prophet_market_eligibility.json`
- `site/factordata/china_prophet_market_eligibility.json`

The sidecar binds to:

- exact raw-board SHA;
- board definition and source session;
- Risk Envelope bundle ID;
- policy definition/version;
- one row per raw candidate with every policy disposition.

### 8.3 No silent deletion

A suppressed candidate remains visible in All Ranked and in the counterfactual ledger. The card states:

- raw rank;
- original lane;
- actionability state;
- hazard/exposure match;
- policy rule and expiry;
- what would restore eligibility.

### 8.4 Plan origination

`build_prophet.py` joins the sidecar after canonical admission and rank. It records one disposition for every admitted candidate:

- originated;
- suppressed by named policy;
- duplicate/open-plan blocked;
- validation failed;
- data unavailable.

The intake must remain lossless and auditable.

### 8.5 Active plans

Grey Deer v1 may emit `NO_ADD`, `PROTECTION_REVIEW`, or `EXIT_REVIEW`. It may not auto-close an active recommendation.

### 8.6 Re-entry

A prior candidate is not restored merely because the market bounces. Re-entry requires:

1. the owning episode reaches `REPAIR_CONFIRMED`;
2. the owning policy is explicitly lifted;
3. the candidate’s own current entry availability is valid;
4. its name-level invalidation has not fired;
5. critical evidence is fresh;
6. a new plan ID/lifecycle is minted when the prior plan was terminal.

---

## 9. Cross-repository authority matrix

| Capability | Macro UI | Prophet | Alerts | Terminal | Mastermind Portfolio | LLM |
|---|---|---|---|---|---|---|
| Display evidence/state | Yes | Yes | Yes | Yes | Yes | Explain only |
| Advisory transition warning | Yes | Chip/context | Push | Yes | Context | Explain/de-escalate |
| New-entry restriction | Display | Individually promoted rule only | Notify | Display | May mirror | No |
| Suggested-size reduction | Display | Individually promoted rule only | Notify | Display | Local adapter may apply | No |
| Active-plan review | Display | Individually promoted rule + name invalidation | Notify | Display | Review workflow | No |
| Gross cap | Display | No | Notify | Display | Promoted rule + local mandate | No |
| Held-position execution | No | No | No | No | User-opt-in portfolio control only | No |
| Auto-exit | Not in v1 | Not in v1 | Not in v1 | Not in v1 | Separate future gauntlet | Never |

---

## 10. Promotion gates

All thresholds are frozen before the replay results are inspected.

### Detection/advisory authority

1. **Temporal integrity:** all required inputs pass event/availability/observation clocks; no hidden revised-data fallback.
2. **Sample:** at least 30 effective independent episodes, at least 12 adverse outcomes, at least three eras, and a real post-2020 cell. Otherwise `UNDERPOWERED`.
3. **OOS discrimination:** held-out average precision at least 1.25× prevalence with 90% block-bootstrap lower bound above 1.0×; Brier skill > 0 in both split halves.
4. **Calibration:** slope 0.7–1.3 and no material probability-bin inversion.
5. **Stability:** same economic sign in both halves and no leave-one-crisis-out reversal.
6. **Lead claim:** median lead ≥ one full session and 25th-percentile lead > 0. Otherwise label the expert coincident.
7. **False alarms:** no more than two non-event critical episodes per quarter in held-out data.
8. **Operational coverage:** at least 80% of declared critical inputs and no silent source substitution.

### New-entry policy authority

All advisory gates plus:

1. at least 40 effective policy decisions and 12 adverse outcomes;
2. at least one calendar quarter or 60 sessions of prospective shadow operation;
3. 5% expected-shortfall or maximum-drawdown improvement of at least 15% in both halves;
4. 90% block-bootstrap lower bound on downside improvement above zero;
5. downside avoided / upside forgone ≥ 1.33 in both halves;
6. at least 70% of avoided losses inside the declared exposure scope;
7. false suppressions and time-in-protection within the preregistered budget;
8. Fable adversarial review, Sol acceptance, and Chairman approval.

### Size authority

Requires new-entry authority plus at least 20 prospective firings, a positive lower confidence bound on expected-shortfall improvement, and an explicit turnover/churn budget.

### Active-plan review authority

Requires promoted market policy, candidate vulnerability, and a name-specific invalidation or deterioration receipt.

### Automatic exit authority

Not eligible in v1.

---

## 11. Temporary operator-safety policy

A temporary rule may be used before statistical promotion only when clearly labeled `temporary_operator_safety`.

The first proposed activation is China new-entry protection for high-beta, long-duration, memory, semiconductor, and technology candidates during the current breakdown/contagion episode.

It must:

- preserve raw rank and all counterfactual candidates;
- suppress only new actionability and assertive buy alerts;
- make no automatic held-position exit;
- display exact scope and reason;
- expire at the earliest of ten China trading sessions, two settled sessions after `REPAIR_CONFIRMED`, Chairman revocation, or its fixed expiry timestamp;
- require a new decision ID for renewal;
- never de-escalate because data went stale.

This architecture freeze does not claim that the temporary policy has already been deployed.

---

## 12. Legacy migration and no-rebuild boundaries

### Preserve and reuse

- Market State as slow measured state.
- Risk Radar as a calibrated hazard expert.
- Anticipation/Velocity as conditional left-tail and risk-cone experts.
- Market Drivers as canonical observed shock attribution.
- Transmission chains and stock macro sensitivity.
- Leadership Crack and deterioration/contagion organs.
- Chronicle, Market Memory, Reflex Registry, QLedger/Evaluation OS, Synapse.
- Prophet rankers, candidate episodes, availability, plans, and board ledgers.
- Terminal ingest/presentation and Mastermind portfolio control.

### Freeze as legacy compatibility, do not extend

- Macro `engine/risk_state.py` fused composite/sizing path.
- Portfolio `brain/macro_risk.py` independent fixed-weight market fusion.
- Portfolio `brain/market_view.py` as an independent market-consensus authority.
- Portfolio `brain/posture_decider.py` current eight-plane fused posture; do not arm it.
- Terminal `market_risk/v1` as the long-term contract.

### Migrate, then retire authority

- Macro legacy risk output may remain visible for comparison but may not own Grey Deer policy.
- Mastermind retains book-specific dwell, mandates, exposure, and execution, while replacing its market-input fusion with the canonical envelope.
- Terminal keeps a one-release compatibility adapter, then reads `risk_envelope.v1` directly.
- LLM numeric roll-down/crash probability fields are ignored by every authoritative consumer.

---

## 13. Build waves

### GD-0 — Durable architecture and workstream

Mission: land this freeze, AgentOS records, program map amendment, Synapse placeholder contract, and collision map. No behavior change.

### GD-1 — Current-event point-in-time replay

Mission: reconstruct August 1 onward at lawful clocks; replay every existing organ; identify first useful precursor, first defensible alert, and first defensible new-entry restriction.

### GD-2 — Settled Risk Envelope + tri-answer Macro hero

Mission: one settled artifact drives a real user composition showing measured state, hazard, and capital posture. No policy authority yet.

### GD-3 — Live provisional envelope

Mission: live/VPS path updates the hazard panel with first-tick pending escalation, confirmed transition, freshness, and correction behavior. No live durable writes.

### GD-4 — China truth repair

Mission: repair CN/HK forward-ledger advancement, add official PBOC liquidity composition, and add China Prophet board health. User sees a board-wide breakdown rather than isolated cards.

### GD-5 — First hazard challengers

Mission: ship long-end duration shock and crowded-winner liquidation as shadow experts with preregistered ledgers and current-event replay receipts.

### GD-6 — Prophet market-eligibility sidecar, shadow

Mission: every raw US/CN candidate receives a counterfactual risk disposition; no candidate is actually suppressed.

### GD-7 — Time-boxed China new-entry protection

Mission: activate the temporary operator rule, visibly suppressing only scoped new entries and alerts while preserving raw rank and counterfactual grading.

### GD-8 — Alert Center and Terminal

Mission: transition-only site/Discord/push notifications and a Terminal mirror of the same envelope. Terminal computes nothing.

### GD-9 — Mastermind Portfolio adapter and shadow parity

Mission: consume the envelope, compare against legacy `macro_risk`, `market_view`, `posture_decider`, and `derisk`, and publish a parity/conflict report with zero book changes.

### GD-10 — Portfolio cutover and active-plan review

Mission: one source of market truth; local portfolio adapter applies only promoted policy plus book state. Add no-add/protection-review/exit-review; no auto-exit.

### GD-11 — Promotion scorecard and learning

Mission: grade detection, policy, false alarms, opportunity cost, repair, alert latency, Prophet board utility, and portfolio utility through existing Evaluation OS.

---

## 14. Production acceptance

A wave is not complete on green CI alone.

Required production proofs include:

- real source session through the actual producer, publisher, CDN/VPS, browser, Terminal, and Portfolio consumer;
- exact bundle ID and source timestamps visible;
- 390×844, 768×900, and desktop browser proof in EN/ZH and dark/light where supported;
- stale feed, behind-live-feed, missing critical source, correction/retraction, conflicting episodes, no-candidate, and failed-repair states;
- raw Prophet board hash and order unchanged;
- every suppressed candidate still visible and graded counterfactually;
- live policy transition within SLA, with no silent fallback green;
- Terminal and Portfolio prove they consumed, not recomputed, the envelope;
- kill-switch and rollback proof;
- current-event replay before/after product proof.

---

## 15. Architecture decisions to record

- `DEC:RISK-STATE-HAZARD-POLICY-SEPARATION`
- `DEC:RISK-ENVELOPE-IS-CANONICAL-DERIVED-PROJECTION`
- `DEC:RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES`
- `DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR`
- `DEC:REPAIR-IS-ORTHOGONAL-AND-FIRST-CLASS`
- `DEC:PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK`
- `DEC:SCOPED-REFLEX-CONSTRAINTS-NOT-FUSED-SHIELD`
- `DEC:AUTO-EXIT-NOT-IN-GREY-DEER-V1`

---

## 16. Final acceptance question

The program is complete only when a real user can see the transition before or as it begins, understand why, see which exposures are affected, observe Mastermind suppress or review the correct actions, retain the raw evidence and counterfactual, and later see whether the warning and protection were right.

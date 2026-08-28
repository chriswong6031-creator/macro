# Fable Program Command Packet — Grey Deer Risk Intelligence & Capital Protection

**Commissioning authority:** Chairman Chris → Sol architecture freeze → Fable COO execution
**Program:** `WS:GREY-DEER-RISK-INTELLIGENCE`
**Date:** 2026-08-19
**Status:** EXECUTION-READY AFTER GD-0 DURABLE LANDING. Architecture is frozen; this packet hardens execution and does not reopen the product thesis.
**Repositories:** `mastermindx-market-intelligence/macro`, `mastermindx-market-intelligence/mastermind-terminal`, `mastermindx-market-intelligence/Mastermind`
**Principal orchestrator:** Fable
**Primary research offload:** Grok 4.6
**Final acceptance:** Sol; Chairman required at the explicitly named authority gates

---

# 0. Observable program mission

Build one coherent capital-protection nervous system for Mastermind-X that can:

1. preserve the slow measured market state without pretending it answers imminent-turn risk;
2. detect and describe market fragility, activation, transmission, breakdown, contagion, and repair at the correct clock;
3. project that truth identically into Macro, Prophet, Terminal, alerts, Neural Web, and Mastermind Portfolio;
4. withhold or constrain *new* risk only through explicit, scope-bounded, counterfactual-preserving policies;
5. later earn stronger sizing or active-plan authority through point-in-time replay and prospective grading;
6. never create a second event store, signal bus, market-data plane, Prophet ranker, portfolio truth engine, or opaque universal risk score.

**Program completion is not “risk_envelope.json exists.”** Completion means a real market event passes from a real source through the production path to a visible user state and an authorized machine consumer, with exact source clocks, policy receipts, counterfactuals, correction behavior, and forward outcomes.

---

# 1. Why this matters

The incident exposed a company-level product failure rather than a cosmetic dashboard error. Slow Market State could remain green while leadership was broken, long-end rates were stressing duration assets, volatility was accelerating, high-beta technology was being liquidated, China risk warnings were stale or poorly aged, and defensive rotation was already visible. Individual organs existed, but the product had no canonical semantic separation between “trend still intact,” “turn hazard is rising,” and “what users/Prophet should do.”

The program protects two promises simultaneously:

- **Intelligence promise:** Mastermind should hear the predator before a visibly calm tape becomes a cliff.
- **Capital-protection promise:** when a hazard becomes sufficiently real, Mastermind must stop presenting exposed new ideas as independently green merely because the name-level selector has not yet invalidated them.

The program must improve both *anticipation* and *reaction*. Early-warning research that never changes a user or machine capability is incomplete. A protective gate that fires only after the selloff is also incomplete.

---

# 2. Authority and document precedence

When documents conflict, Fable must apply this order:

1. **Chairman instructions for this program.**
2. **`GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md`.** This is the product/system/authority freeze.
3. **This command packet.** It hardens sequencing, scope, operator routing, stop conditions, and acceptance; it may not change the architecture freeze.
4. **`research/DO_NOT_REBUILD.md` and durable AgentOS decisions.** Existing explicit kills remain binding unless the Grey Deer freeze explicitly superseded the conflicting construction.
5. **Prophet V4 architecture freeze and regional Prophet decisions.** Grey Deer may affect actionability only after canonical rank/admission; it never rewrites rank or population.
6. **Live Entry Radar frozen research contract and AgentOS workstream.** Radar remains an independent expert/event producer and owns its paths.
7. **Canonical semantic/system registries:** `config/mastermind_programs.yml`, `config/synapse.yml`, `docs/SIGNAL_BUS.md`, `config/lobe_charters.yml`, `config/reflexes.yml`, Chronicle and QLedger/Evaluation contracts.
8. **Current merged source code and production evidence.** Source code wins over stale prose about what is implemented; production proof wins over comments about what should be running.
9. **Older risk masterplans** such as `research/RISK_LAYER_DESIGN.md`, Contagion Sensing, Portfolio Risk Desk, and legacy Market-Risk Bridge docs. These are substrate/evidence only where they conflict with the Grey Deer freeze.

### Binding supersession ruling

Older designs that fused many risk dimensions into one score or independently recomputed market truth inside Portfolio are **not** templates for Grey Deer. Their useful sensors and operational lessons are reused. Their universal-fusion authority is not.

---

# 3. Verified current-state snapshot Fable must start from

This packet was hardened against the live repository state on 2026-08-19. Fable must still re-run the delta check at branch creation because the repo is moving rapidly.

## 3.1 Macro repository

### Preserve as canonical or substrate

- `engine/market_state.py` / `data/market_state/latest.json`: slow measured state; display role.
- `engine/risk_radar.py` plus international radar family: horizon-specific warning substrate and forward logs.
- `engine/anticipation.py` and `engine/velocity.py`: existing conditional-tail/velocity substrate; do not rebuild.
- Rates Command / Transmission / Treasury-auction and PBOC collectors: mechanism evidence.
- Leadership Crack, deterioration/contagion organs, breadth, rotation, market drivers, options/volatility context.
- `engine/chronicle/*`: existing event and forward-state history system.
- `config/reflexes.yml`: existing bounded deterministic trigger→action registry.
- QLedger / Evaluation OS: existing grading and promotion substrate.
- `config/synapse.yml`: canonical artifact registry.

### Freeze as legacy compatibility during migration

- `engine/risk_state.py`: useful sensor fusion and historical consumer contract, but **no new legs, weights, consumers, or strategic authority**. Grey Deer does not feed its fused score into the new envelope.

### Current live-adjacent PRs that Grey Deer must not collide with

- **#5925** — Entry Radar ProbeSet→live-pack transport repair. Owns `engine/entry_radar/live_pack.py` and its tests. It still owes production proof.
- **#5929** — Entry Radar W4.1 confirmed-lane + spool-envelope transport correction. Owns Radar transport/reconciler paths and explicitly leaves Prophet protected paths clean.
- **#5928** — Prophet Operator Lab read-only API. All authority booleans false; do not turn Lab into a Grey Deer consumer in its current PR.
- **#5737 / #5931 / #5940** — Radar/Prophet Lab reference-design and integrity work. Do not restyle or co-opt these reference surfaces in a Grey Deer PR.

### Current CI/control-plane movement

- **#5954** is actively changing `.github/ci/legacy-jobs.yml` and `scripts/run_ci_pack.py` to classify code-vs-data merge gates.
- **#5948** is changing the backfill workflow push path.
- The CI reliability incident measured main green only ~44% across the recent sample because many merge-gate jobs are coupled to moving data. This is a coordination constraint, not permission for Grey Deer to admin-merge over red main.

**Hard collision rule:** no Grey Deer PR may touch `.github/ci/legacy-jobs.yml` until #5954 is resolved and the branch is rebased. If a Grey Deer test needs CI registration before then, stop and wait/rebase rather than hand-edit the moving manifest.

## 3.2 Terminal repository

Existing `ingest/pull_macro_risk.py` produces a trimmed display-only `market_risk/v1` from the old live/nightly market-state contract. Grey Deer supersedes this *consumer contract* later with a mirror of `risk_envelope/v1`; do not add a second Terminal market-risk recomputation.

Current open Terminal PRs are unrelated to Grey Deer but can collide in generic e2e files. Prefer dedicated Grey Deer test files (for example `e2e/risk-envelope.spec.ts`) rather than editing broad `responsive.spec.ts` unless unavoidable.

## 3.3 Mastermind Portfolio repository

Existing market-risk machinery includes:

- `brain/macro_risk.py` — local fused risk state, dwell and gross-cap helpers;
- `brain/market_view.py` — one multi-plane market view, mostly read-only/advisory;
- `brain/posture_decider.py` — shadow posture object, default off;
- `bot/derisk.py` — fast deterministic tripwire and subtract-only queued-target/legacy cutter paths.

Grey Deer does not delete these early. It first creates a shadow consumer of Macro’s canonical envelope and measures parity/differences. The later cutover retires **market-truth origination** from Portfolio while preserving book-specific exposure, mandates, dwell, constraints and settlement.

Open Executive OS PRs in Mastermind own governance/authority files. Grey Deer Portfolio waves must not edit Executive OS authority maps, worker/scheduler infrastructure or protected executive paths.

---

# 4. Capability ledger at execution start

| Capability | State | Execution ruling |
|---|---|---|
| Slow U.S. measured trend | PROVEN_LIVE | Preserve and relabel semantically |
| Existing Anticipation + velocity | PROVEN_LIVE | Reuse as substrate; replay at PIT clocks |
| U.S. imminent hazard detection | PARTIAL | Existing observations, insufficient canonical episode/policy architecture |
| Leadership Crack | PROVEN_LIVE / DISCONNECTED | Reuse; no separate replacement |
| Rates/Transmission | PROVEN_LIVE / DISPLAY-DOMINANT | Reuse; connect to named hazard episodes |
| Treasury auction results | PROVEN_LIVE | Context/substrate; true WI tail gap remains |
| PBOC OMO tape | PROVEN_LIVE / DISCONNECTED | Build typed liquidity-composition consumer, not a directional shortcut |
| China/HK risk forward learning | BROKEN/STALE in observed incident | Repair liveness before trusting de-escalation |
| Global deterioration cascade | LIVE but incident-insufficient | Keep; add fresh live transmission context, not fake predictive authority |
| Prophet US raw rank/admission | PROVEN_LIVE | Frozen owner; Grey Deer acts after it |
| Prophet CN rank/admission | PROVEN_LIVE under CN V4 | Frozen owner; Grey Deer acts after it |
| Prophet board-wide market eligibility | NOT_BUILT | New sidecar, counterfactual preserving |
| Board-wide live health | NOT_BUILT | Add as observation, never rank feedback |
| Canonical risk envelope | NOT_BUILT | Primary Grey Deer production contract |
| Terminal envelope mirror | NOT_BUILT | Replace old bridge after Macro settles |
| Portfolio envelope consumer | NOT_BUILT | Shadow first, cutover later |
| Repair intelligence | NOT_BUILT as canonical state | First-class Grey Deer state |
| Automatic market-risk exits | REJECTED_BY_DESIGN for V1 | Do not implement |

---

# 5. Non-negotiable architecture laws

Fable must reject a PR before code review if it violates any of these:

1. **Three answers remain separate:** measured state, transition hazard, capital policy.
2. **No universal Grey Deer score.** No weighted `risk=83` construction is allowed in scored/authority paths.
3. **No fused shield/meta-router.** Policy objects are individually scoped and independently authorized.
4. **No LLM origination.** LLMs may explain, challenge, retrieve and de-escalate; never originate hazard state, probability, escalation, gate, size or exit.
5. **No Prophet rank/population mutation.** Raw rank/admission stays canonical and counterfactual-preserved.
6. **No browser authority.** Hazard/policy/eligibility are computed server-side; browser renders only.
7. **No second event store.** Settled transitions extend Chronicle; reflex actions use Reflex Registry; outcomes use Evaluation OS/QLedger.
8. **No second market-data plane.** Consume existing collectors/live quote owner.
9. **No Portfolio market-truth fork.** Portfolio eventually consumes the envelope and owns only book-specific decisions.
10. **No stale calm vote.** Missing/stale critical evidence may shrink confidence or set unknown; it may not make the system safer.
11. **Forecasts expire.** A 21-session forecast cannot remain “current” on day 30 without a new issuance identity.
12. **Repair is orthogonal.** `repair=IMPULSE` does not repaint hazard to green.
13. **Credit calm is contradiction/classification context, not a veto on equity-duration hazard.**
14. **Cash/no-new-risk is a valid product result.** Do not manufacture defensive recommendations.
15. **Automatic held-position exit is not in Grey Deer V1.**
16. **One useful capability per PR.** A foundation-only wave is insufficient unless its direct consumer ships in the same PR or the wave is explicitly records/research-only.
17. **Production proof beats CI.** Real source → real artifact → real served consumer → browser/machine receipt.

---

# 6. Complete user journey

## 6.1 Normal market

User opens Macro. The hero shows:

- measured trend and slow score;
- `Transition hazard: None` only when required coverage is fresh enough to justify NONE;
- `Capital posture: Normal` as a display summary of zero active policies.

Prophet shows its normal raw board. Terminal mirrors the same state. Portfolio sees no Grey Deer constraint.

## 6.2 Fragility before the index breaks

A structural organ such as leadership, breadth, duration sensitivity or correlation identifies fragility while the slow state is still Risk-on.

User sees:

> Measured trend: Risk-on 77  
> Transition hazard: Fragile — technology leadership is internally broken  
> Capital posture: Selective — no market gate active

No buy is automatically blocked simply because fragility exists. The product names what is vulnerable and what would arm the next stage.

## 6.3 Trigger activation

A named trigger family activates on a lawful live clock. The first live observation may show `TRIGGERING — pending confirmation` while the settled state remains unchanged.

User sees:

- mechanism;
- first observed time;
- affected exposures;
- whether this is display-only, shadow forecast or policy-authorized;
- exact stale/live status.

No score is silently blended downward.

## 6.4 Transmission/breakdown

The active mechanism begins damaging the expected exposures. The page moves to `TRANSMITTING` or `BREAKDOWN` with a persistent hazard banner.

If a scoped policy is active, Prophet cards in that scope move to a clearly separate **Withheld for market risk** lane. Their raw Prophet rank remains printed.

If no policy has earned/been temporarily granted authority, the UI warns loudly but does not pretend a gate exists.

## 6.5 Contagion

Cross-market damage propagates by market clock. The user sees where it started, which markets have confirmed, which remain unconfirmed, and the freshness of each regional state.

An immature forward ledger cannot erase obvious live price contagion; it can only prevent an *anticipatory lead claim*.

## 6.6 Repair

An issuer buyback, policy action or sharp rebound can create `repair=IMPULSE` while hazard remains `BREAKDOWN/CONTAGION`.

The user sees:

> Repair attempt underway — not yet all clear.

As repair broadens, the drawer shows which conditions have recovered and which have not. A policy lifts only when its own frozen lift contract is met.

## 6.7 Stale or broken data

If a critical source is stale or missing:

- `data_state` changes visibly;
- hazard stage becomes `null` if it is no longer knowable; **null is not NONE**;
- the product may carry the last settled observation as `carried`, but cannot call it current;
- de-escalation is blocked when the policy contract requires fresh evidence;
- no new “all clear” push may be sent.

## 6.8 Forecast expiry

When a horizon matures, the forecast is closed and graded. The product prints whether it hit, missed or remained unresolved and records false-alarm/upside-forgone cost. A renewed forecast receives a new issuance identity.

---

# 7. Machine journey

The canonical machine flow is:

```text
source observation
  → existing collector/store/live market-data owner
  → deterministic primitive / existing expert
  → named Grey Deer episode evidence
  → pure risk-envelope composer
  → settled or live-provisional served bundle
  → optional scoped policy sidecar
  → user surface + Terminal + Portfolio + Neural Web
  → Chronicle/reflex/evaluation receipts
```

### Authority location

- Observations and descriptive hazard stage: Macro.
- Probabilities: only a promoted expert model.
- Prophet new-entry actionability: Prophet-side consumer of a registered Grey Deer policy sidecar.
- Portfolio gross/settlement: Portfolio, using user/book authority.
- LLM: no machine authority.

---

# 8. Data, clocks, nulls and corrections

## 8.1 Required clocks

Every evidence record must preserve, where applicable:

- `event_time`
- `measurement_end`
- `available_at`
- `observed_at`
- `effective_session`
- `settled_at`
- `produced_at`
- `stale_after`

Build time may never stand in for first-knowable time.

## 8.2 Basis vocabulary

Use explicit basis:

- `live`
- `delayed`
- `settled`
- `release`
- `revised`
- `carried`

Historical statistical work uses release/first-known data, not latest-revised history.

## 8.3 Null law

- `null` = unknown/unavailable/not lawfully computable.
- `0` = measured numeric zero.
- `NONE` hazard = fresh evidence says no active hazard.
- `null` hazard = system cannot lawfully decide.

No default maps a missing family to benign.

## 8.4 Live versus settled

`site/live/risk_envelope.json` is provisional and may change during the session. It must use the same pure composer as settled state but may use fresher allowed inputs.

Intraday lanes:

- may publish site/live state;
- may emit ephemeral alerts/pending-escalation;
- may not advance Chronicle forward history, QLedger, Radar forward logs or other durable nightly ledgers.

Settled lane:

- owns episode stage transitions that enter durable history;
- advances applicable forward ledgers;
- grades matured forecasts/actions.

## 8.5 Corrections

A source correction never silently rewrites the fact that Mastermind previously displayed or acted on an earlier version.

Correction must produce:

- `revision=corrected`;
- `correction_of_bundle_id` or equivalent reference;
- source correction receipt;
- corrected current projection;
- Chronicle correction/retraction event where applicable;
- policy review if the correction invalidates an active policy basis.

Raw source/forward evidence remains immutable according to its owner’s correction law.

## 8.6 Forecast aging

Every forecast carries:

- `issued_at`
- `valid_from`
- `valid_until`
- `horizon_role`
- `episode_id`
- `construction_version`

After `valid_until`, it cannot remain displayed as current. It is graded/expired, and a renewed forecast gets a new issuance record.

---

# 9. Method taxonomy

Every calculation must declare one method class.

## Deterministic observation

Examples:

- leadership state is BROKEN;
- long yield rose X bp over Y interval;
- board median return is −Z%;
- 80% of candidates are below −3%;
- defensive sectors have positive residual return while exposed sectors are negative;
- an official PBOC operation occurred.

May ship descriptively immediately when clocks and sources are honest.

## Deterministic episode logic

Frozen, transparent state transition rules over existing source-native observations. Display/advisory at birth. No probability claim.

## Statistical/model-generated

Examples:

- probability of ≥5% residual drawdown within 3 sessions;
- survival hazard of breakdown onset;
- conditional expected shortfall;
- change-point probability.

Starts shadow, is point-in-time replayed, and requires the promotion gauntlet before user conviction or action authority.

## LLM-generated

May:

- summarize evidence;
- explain contradictions;
- retrieve source context;
- propose hypotheses to the research queue;
- challenge a proposed escalation.

May not emit a field that a policy, ranker, alert escalation, sizer or executor treats as authority.

---

# 10. Exact wave DAG

```text
GD-0A Durable program landing
   ├──────────────┬───────────────────────────────┐
   │              │                               │
   ▼              ▼                               ▼
GD-1A prereg   GD-2 settled envelope          GD-4A CN ledger truth
   │              │                               │
   ▼              ▼                               ├──► GD-4B CN board health
GD-1B replay   GD-3 live envelope                  └──► GD-4C PBOC liquidity read
   │              │
   ├──────┬───────┘
   ▼      ▼
GD-5A Duration expert shadow
GD-5B Crowded-winner expert shadow
GD-5C Repair expert shadow

GD-2 + Prophet contract ──► GD-6A US eligibility sidecar shadow
GD-2 + GD-4B ────────────► GD-6B CN eligibility sidecar shadow
GD-6B + Chairman gate ───► GD-7A CN temporary-policy dark build/activation

GD-3 ────────────────────► GD-8A Macro alerts
GD-3 ────────────────────► GD-8B Terminal mirror
GD-3 ────────────────────► GD-9A Portfolio shadow adapter
GD-9A + prospective proof + Sol/Chairman ──► GD-10 Portfolio truth cutover

All shadow/policy waves ──► GD-11 promotion scorecard / learning
```

GD-1 research runs in parallel with GD-2/GD-4 because the user-facing semantic repair and source-liveness repair do not require pretending a new predictive model has already been validated.

---

# 11. Wave execution packets

## GD-0A — Durable architecture landing

### Observable mission

Make Grey Deer a first-class canonical program so every later worker can discover the freeze, decisions, ownership, no-rebuild boundaries and exact next wave without relying on this chat.

### Why it matters

Without GD-0A, every builder will rediscover the system and one of them will eventually create another fused score, parallel ledger or Prophet mutation.

### Repository and scope

**Macro only.** Proposed paths:

- `research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md`
- `research/grey_deer/GREY_DEER_EXECUTION_INDEX_2026-08-19.md`
- `agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md`
- eight `agentos/decisions/DEC-*.md` records from the freeze
- `agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-19.md`
- `config/mastermind_programs.yml` program/relationship registration
- generated `docs/MASTERMIND_SYSTEM_MAP.md`

### Non-goals

No engine, scripts, collectors, templates, site, data, workflow, CI manifest, Signal Bus or Prophet edits.

### Implementation sequence

1. Rebase current main.
2. Search open PRs for every owned path; stop on same-file collision.
3. Commit the architecture freeze byte-for-byte from Sol’s pack.
4. Mint the AgentOS workstream and eight decisions.
5. Register the durable program in `config/mastermind_programs.yml` with Macro as market-truth owner, Terminal as presentation consumer, Portfolio as downstream control-plane consumer.
6. Regenerate system map with the canonical generator.
7. Validate AgentOS and semantic-system-map tests.
8. Return PR to Sol; no self-merge if any wording would narrow or expand authority.

### Acceptance

- AgentOS validator 0 errors.
- System-map generator check clean.
- No runtime paths changed.
- Search for `Grey Deer` returns one canonical program, not multiple program identities.
- Every decision key is unique and compiler-visible.
- Existing risk systems are listed as relationships/substrate, not silently reowned.

### Production proof

Not applicable; records-only wave. Proof is merged canonical discoverability from fresh main.

### Stop condition

Stop if the system map requires inventing a second owner or if an existing program registration already claims the exact Grey Deer role. Return the collision to Sol for ruling rather than forking.

### Continuation

Dispatch GD-1A to Grok; dispatch GD-2 and GD-4A archaeology/build planning to bounded operators.

---

## GD-1A — Event replay preregistration and source-clock census

### Observable mission

Freeze the August incident’s event species, source clocks, outcomes, baselines and missing-data rules **before** reading outcome-bearing columns.

### Owner

Grok 4.6, Fable reviewing scope; Sol approves any change to GD-H1..H8.

### Scope

Research-only under `research/grey_deer/gd1/`. No production code.

### Inputs

All current/historical artifacts and source histories for US rates/vol/equities/credit, Korea/Japan/Taiwan/HK/CN, Treasury auctions, PBOC operations, Prophet boards, and known company/policy events.

### Required deliverables

- source/clock ledger;
- preregistration with GD-H1..H8;
- availability/rights matrix;
- PIT leak audit and permissible substitute table;
- manifest of exact code/input SHAs.

### Null behavior

Unknown first-known timestamp = `BLOCKED_FOR_LEAD_CLAIM`; the row may still participate in descriptive settled reconstruction if its settled date is reliable.

### Acceptance

The prereg artifact is hash-pinned before GD-1B opens forward outcomes.

### Stop condition

No approximate intraday reconstruction from EOD data.

---

## GD-1B — Existing-organ replay and customer counterfactual

### Observable mission

Answer exactly what Mastermind knew, when it knew it, what message was defensible, and what *new-entry* protection would have changed customer outcomes.

### Methods

- truncate-and-recompute existing engines;
- release-basis macro data;
- actual intraday only for intraday claims;
- date/session blocked uncertainty;
- no post-hoc threshold tuning.

### Outputs

- organ-by-organ replay;
- event timeline;
- causal-hypothesis ledger;
- Prophet US/CN board counterfactual;
- false-alarm/upside-forgone estimates;
- exact construction recommendations or nulls;
- explicit killed/refuted hypotheses.

### Acceptance

Independent adversarial reviewer must attempt to explain every claimed lead as hindsight, wrong clock, revised-data leakage or correlated duplicate evidence.

### Stop condition

Any missing source required for a lead claim becomes a named gap, not synthetic evidence.

---

## GD-2 — Settled Risk Envelope + three-answer Macro hero

### Observable mission

After a real settled market session, the production Macro page shows the slow measured state, current hazard state and capital-posture summary as separate truths with full receipts.

### Repository

Macro.

### Scope candidate

- new `engine/risk_envelope.py` pure composer;
- `scripts/build_risk_envelope.py`;
- schema/contract under existing contract conventions;
- `site/riskdata/risk_envelope.json`;
- Synapse registration and generated Signal Bus;
- minimal server/render integration into `macro.html`/regional page composition;
- dedicated tests and reference/mockup if house design law requires one.

### Inputs at V0

Consume existing source-native states only. Do **not** calculate a new weighted risk number. V0 hazard stage may be descriptive/unpromoted and may remain `null` when the evidence cannot lawfully determine it.

### Important V0 rule

`hazard_stage=null` is legal and means “not knowable with current coverage.” `hazard_stage=NONE` requires fresh required coverage and an explicit no-active-hazard result. Never map null to NONE.

### Complete user journey

The user sees the three rows, opens the hazard drawer, sees evidence/contradictions/freshness/invalidation, and can tell whether any policy is actually active.

### Failure states

- slow state fresh, hazard data stale;
- hazard fresh, slow state carried;
- contradictory organs;
- missing critical source;
- source correction;
- no active policy;
- historical forecast expired.

### Acceptance tests

- source order cannot change output;
- same inputs produce byte-stable semantic output;
- LLM fields cannot alter state;
- stale/missing cannot cast calm;
- null ≠ zero and null ≠ NONE;
- top-level authority booleans all false;
- existing Market State value is preserved exactly;
- legacy risk_state score cannot enter arithmetic;
- no policy can appear without an individually registered policy object;
- EN/ZH and dark/light rendering parity;
- 390/768/1440 with no horizontal overflow.

### Production proof

Real settled source session → generated envelope → live website → browser screenshot and DOM receipt showing source session, bundle id, measured state and hazard/data state.

### Stop condition

Stop if implementing this requires changing Prophet, Entry Radar, Portfolio or Terminal in the same PR. This PR owns the Macro product capability only.

---

## GD-3 — Live provisional envelope and pending escalation

### Observable mission

During market hours, a fresher price-sensitive hazard observation becomes visible without waiting for nightly, while settled truth and durable ledgers remain intact.

### Scope

- `scripts/build_live_risk_envelope.py` or current live-service equivalent;
- existing live publisher/VPS plane;
- `site/live/risk_envelope.json`;
- browser live-over-settled comparison;
- same composer as GD-2.

### Clock law

Live path may only use evidence whose first-known clock is valid at the live observation. It never writes durable forward ledgers.

### Debounce/pending law

Same-tick escalation is visible as a pending badge; authoritative live stage change follows the frozen persistence contract. De-escalation must never be faster than escalation merely because one source disappeared.

### Acceptance

- stale live cannot overwrite newer settled;
- future-dated live refused;
- same tick displays pending escalation;
- confirmation after required persistence;
- a live source outage results in DEGRADED/UNKNOWN, not Risk-on;
- nightly close settles/clears the provisional lineage correctly.

### Production proof

Real VPS/live source changes the served file and browser within the target cadence. Measure event_time→observed_at→produced_at→browser_seen_at.

### Stop condition

No second quote stream or scheduler.

---

## GD-4A — China/HK forward-ledger truth repair

### Observable mission

On a settled Asia session, CN/HK risk forward logs and their heartbeat advance exactly once with settled data and no intraday duplication.

### Why first

A stale risk ledger can make every derived cascade and track record confidently wrong.

### Scope

Inspect and repair the actual lane gate only after reproducing it. The earlier probable `COLLECT_LANE=nightly` versus Asia-lane mismatch is a hypothesis until reproduced.

### Acceptance

- settled Asia run advances the current date once;
- rerun is idempotent;
- intraday/preview run cannot append;
- ledger-stall heartbeat fires on deliberate block;
- cascade reads the fresh row;
- scorecard freshness turns current;
- no history rewrite.

### Production proof

Real Asia-close run on production substrate; committed/served artifacts show current session and one new forward row.

### Stop condition

If the freeze is not caused by the hypothesized lane gate, do not patch the env var blindly. Return root cause.

---

## GD-4B — China Prophet board-health observation

### Observable mission

During the live China session, the board tells the user whether losses are isolated or market-wide.

### Scope

Extend the existing live Prophet artifact with board-level observations only:

- median return;
- positive share;
- shares below −2/−3/−5%;
- featured median;
- high-beta/defensive splits where existing typed classification is available;
- simultaneous invalidations;
- sector concentration;
- `normal|stress|breakdown` **display state**, not ranking authority.

### Circularity firewall

Board-health output cannot feed the raw Prophet score/rank/admission. It can later act as transmission confirmation in Grey Deer.

### Acceptance

Mutation test: changing board_health cannot change candidate rank, Prophet score, board population or entry status.

### Production proof

Real live China board shows an aggregate state and exact underlying member-return counts.

---

## GD-4C — PBOC liquidity-composition read

### Observable mission

The China risk drawer can distinguish “no 7-day operation because liquidity is ample” from “net drain with funding stress” and “medium-term rollover/support.”

### Inputs

Existing official PBOC OMO bulletin collector plus funding rates/CGB/CNH/market response already owned elsewhere.

### Output

Typed display/context state with:

- tool;
- tenor;
- gross injection;
- maturities;
- net by tenor bucket;
- funding response;
- FX/rates response;
- equity transmission;
- interpretation = `DEMAND_QUIET | SHORT_TENOR_DRAIN | TOOL_MIGRATION | MEDIUM_TERM_ROLLOVER | ACUTE_SUPPORT | UNKNOWN`.

### No authority

No direct risk score/rank/gate.

### Acceptance

Zero 7-day operation with low funding rates must not be labeled tightening by construction.

---

## GD-5A — Long-End Duration Shock expert, shadow

### Observable mission

Produce a point-in-time shadow estimate of whether long-end repricing is increasing 1–3 session residual drawdown hazard for duration-sensitive equities.

### Research owner

Grok primary; Fable owns prereg/adjudication; implementation worker only after frozen construction.

### Candidate inputs

Long-end yield level/velocity/acceleration, real yield, MOVE, curve, Treasury auction receipts/tail if lawfully measured, oil/breakevens, corporate supply, duration-cohort response.

### Primary outcome

High-duration cohort residual drawdown ≥3%/≥5% at 1d/3d.

### Authority

Shadow only at birth.

### Acceptance

Turn-3 promotion gauntlet; no user probability until cleared.

---

## GD-5B — Crowded-Winner Liquidation expert, shadow

### Observable mission

Detect the “prior winners/AI-memory/high-beta liquidation” species separately from classic loser-reversal momentum crashes.

### Inputs

Leadership Crack, cohort drawdown breadth, high-beta/low-vol spreads, residual returns, concentration, extension/crowding, volatility acceleration and correlation.

### Primary outcomes

Cohort median residual drawdown, breadth below thresholds, downside-correlation spike.

### Authority

Shadow only.

### Killer

Do not reuse `momentum_crash_gate.py` semantics and call the job done; it models a different species.

---

## GD-5C — Repair/Re-entry expert, shadow

### Observable mission

Distinguish issuer-specific bounce/short-covering from broad repair and failed repair.

### State outputs

`NONE | IMPULSE | BROADENING | CONFIRMED | FAILED`.

### Inputs

Trigger deceleration, vol/correlation deceleration, breadth, exposed-cohort residuals, credit, retests, policy/issuer support.

### Hard rule

One buyback or green future can create IMPULSE; never CONFIRMED.

---

## GD-6A — U.S. Prophet market-eligibility sidecar, shadow

### Observable mission

For every U.S. candidate, publish what Grey Deer *would* do without changing what Prophet did.

### Contract

`prophet.market_eligibility/v1`, board-hash/source-session bound.

### Actions

`ELIGIBLE | NO_CHASE | REDUCE_SUGGESTED_SIZE | SUPPRESS_NEW_ENTRY | NO_NEW_LONG_RISK`

### Shadow behavior

User/production actionability unchanged. Counterfactual begins accruing from first settled publication.

### Acceptance

- raw board bytes/hash unchanged;
- rank/order/population unchanged;
- sidecar fails closed on board hash/session mismatch;
- every row has original rank/lane and policy reason;
- unknown vulnerability never defaults to low-risk;
- no client join can invent eligibility.

---

## GD-6B — China Prophet market-eligibility sidecar, shadow

Same contract as GD-6A, but consumes China-specific hazard and GD-4B board health. It remains shadow until the separate GD-7 authority act.

### Acceptance

Include a replay of the current incident showing every deeply negative candidate’s raw rank plus hypothetical policy disposition. No population rewrite.

---

## GD-7A — Temporary China new-entry protection

### Observable mission

When Chairman explicitly activates the temporary safety rule, China Prophet stops presenting exposed *new* entries as actionable while preserving raw ranking, all candidates and counterfactual history.

### Authority basis

`temporary_operator_safety`, not “validated model.”

### Permitted scope

High-beta / long-duration / memory / semiconductor / technology-momentum / declared high-volatility exposures, only where the sidecar can establish the exposure.

### Permitted actions

- NO_CHASE
- REDUCE_SUGGESTED_SIZE
- SUPPRESS_NEW_ENTRY
- NO_NEW_LONG_RISK

### Forbidden

- rank mutation;
- candidate deletion;
- active-plan automatic exit;
- blanket “all China stocks” block without the declared scope;
- defensive recommendation manufacture.

### Expiry

Hard maximum ten China sessions. Renewal is a new explicit operator/Chairman act. Expiry never rewrites the history of what was withheld.

### Stale-at-expiry behavior

Do not silently label the market Normal. The policy authority expires according to its grant; the UI moves to `REVIEW_REQUIRED / DATA_DEGRADED`. Underlying Prophet behavior resumes only according to the explicit policy expiry contract—Fable must not invent an automatic extension. If the Chairman wants continued protection, mint a new bounded grant before expiry.

### Repair lift

Early lift requires `repair=CONFIRMED`, two settled sessions, fresh critical evidence and candidate requalification under Prophet’s own availability rules.

### Production proof

A real candidate that raw Prophet admits remains visible in All Ranked but is absent from Actionable Now and appears in Withheld for Market Risk, with exact policy and episode IDs.

---

## GD-8A — Macro alert integration

### Observable mission

A Grey Deer stage/policy/repair transition reaches the existing Alert Command Center and notification rail once, with plain-language scope and receipts.

### No second alert center

Reuse existing alert triage and notification transport/dedup.

### Alert types

- triggering pending;
- transmitting/breakdown;
- contagion;
- policy activated/lifted;
- repair impulse/confirmed/failed;
- data degraded;
- forecast expired/graded.

### Acceptance

No alert priority is described as probability. Dedup and correction semantics are tested.

---

## GD-8B — Terminal Risk Envelope mirror

### Observable mission

Terminal shows the same Grey Deer bundle as Macro with no local re-derivation.

### Repository

`mastermind-terminal` only.

### Migration

Replace/retire `market_risk/v1` consumer use after the new bridge proves parity. Do not delete the old bridge in the first PR unless all consumers are migrated and tested.

### Contract

Mirror the served Macro envelope, trim only presentation fields if necessary, preserve:

- definition/bundle/source-session identity;
- measured state;
- hazard/repair/data/coherence;
- policies and authority labels;
- freshness.

### Acceptance

- same bundle ID visible in Macro and Terminal;
- stale envelope cannot be displayed as current;
- no Terminal arithmetic changes hazard or policy;
- dedicated e2e across 390/820/1440 or the repo’s accepted breakpoints.

---

## GD-9A — Portfolio envelope adapter, shadow

### Observable mission

Mastermind Portfolio computes a complete shadow comparison: “what the current local market-risk stack says” versus “what the canonical Grey Deer envelope says,” with **zero book behavior change**.

### Repository

Mastermind Portfolio.

### Inputs

Exact served/vendored Grey Deer bundle; no reaching into Macro internals.

### Output

A versioned shadow adapter containing:

- envelope bundle identity;
- mapped portfolio market context;
- old local risk state;
- differences;
- hypothetical gross/no-add effects;
- data/freshness status.

### Forbidden

- arming `posture_decider` as a shortcut;
- using LLM `probability_rolldown`;
- changing pending targets or held positions;
- editing Executive OS authority maps.

### Acceptance

Incident replays plus prospective shadow show exact differences and no book mutation.

---

## GD-10 — Portfolio market-truth cutover

### Observable mission

Portfolio stops originating firm-wide market truth and instead uses the Grey Deer envelope for market state while retaining book-specific exposure, mandates, dwell and execution.

### Preconditions

- GD-9 prospective shadow sufficient to explain discrepancies;
- exact stale/absent behavior accepted;
- incident replays pass;
- rollback proven;
- Sol acceptance;
- Chairman approval because this changes actual decision-bearing portfolio constraints.

### Required behavior

Envelope absent/stale cannot loosen risk. Portfolio enters `UNKNOWN_PROTECTIVE`: no new automatic loosening/add, no automatic liquidation, operator-visible alert.

### No deletion-first

Legacy local market-risk modules remain available behind compatibility/rollback until post-cutover observation proves the new path.

---

## GD-11 — Promotion scorecard and learning loop

### Observable mission

Every hazard, forecast, policy and repair call has a live track record that answers whether Grey Deer protects capital without becoming a permanent false-alarm machine.

### Metrics

- calibration/Brier/log loss where probabilistic;
- precision-recall;
- lead time;
- false critical alerts per quarter;
- days in unnecessary protection;
- expected shortfall / max-drawdown improvement;
- losing candidates withheld;
- winners withheld;
- upside forgone;
- downside avoided;
- repair false starts;
- policy churn;
- coverage and stale-source rate.

### Product

Internal/operator scorecard first. Public marketing claims require a separate claim-governance review.

---

# 12. Promotion thresholds frozen for execution

## Detection/advisory

All required:

- 100% PIT/source-availability compliance on evaluated rows;
- ≥30 independent episodes, ≥12 adverse outcomes;
- ≥3 eras including post-2020;
- OOS average precision ≥1.25× event prevalence with 90% lower bound above prevalence;
- positive Brier skill in both split halves for probability models;
- calibration slope 0.70–1.30;
- expected sign/order survives split-half and leave-one-crisis-out;
- “anticipatory” label requires median lead ≥1 session and 25th percentile lead >0;
- ≤2 non-event critical episodes/quarter;
- ≥80% required-source coverage at firing time.

## New-entry authority

Additionally:

- ≥40 effective policy decisions;
- ≥12 adverse outcomes in declared scope;
- ≥60 local-market sessions or one quarter prospective shadow;
- ≥15% expected-shortfall or max-drawdown improvement in both halves;
- 90% lower bound above zero improvement;
- downside avoided / upside forgone ≥1.33;
- ≥70% adverse-candidate coverage;
- no material deterioration outside declared scope;
- Fable adversarial review;
- Sol acceptance;
- Chairman approval.

## Size authority

New-entry gate plus ≥20 prospective size-policy firings, acceptable churn and no persistent underinvestment trap.

## Active-plan review

Promoted market hazard + declared vulnerability + name-level evidence. `EXIT_REVIEW` additionally requires name-specific invalidation.

## Automatic exit

Not eligible in Grey Deer V1.

---

# 13. Operator routing matrix

Fable remains the orchestration owner. Workers receive bounded missions only.

| Work | Preferred route | Why |
|---|---|---|
| Program reconciliation, scope conflicts, cross-repo sequencing | **Fable** | Requires complete architecture and authority context |
| Event reconstruction, source archaeology, data-rights census, academic/primary-source research | **Grok 4.6** | Large-context evidence work; zero need to spend Fable on mechanical retrieval |
| Architecture-sensitive implementation spanning several existing owners | Fable-directed Opus/strong builder | Must preserve frozen contracts |
| Pure deterministic composer/schema/tests after contract freeze | Codex/Claude bounded builder | Concrete, testable wave |
| UI implementation against approved reference composition | Dedicated UI-capable builder, reviewed by Fable | Browser proof required |
| Registry/doc regeneration, fixtures, repetitive parity tests | Mechanical agent | Low ambiguity |
| Independent adversarial PR review | Different frontier worker from implementer + Fable final | Avoid self-review laundering |
| Final intent acceptance | **Sol** | Product/system authority |
| Temporary/earned capital authority activation | **Chairman where specified** | Explicit capital-protection authority boundary |

### Worker prompt law

No worker gets “build Grey Deer.” Each gets one wave or subwave with exact inputs, outputs, owners, non-goals, clocks, failure behavior, tests and stop condition.

---

# 14. PR-by-PR review questions Fable must ask

For every Grey Deer PR:

1. What user or machine capability exists now that did not before?
2. Can the primary persona complete the intended task end to end?
3. Did the PR preserve measured-state/hazard/policy separation?
4. Did any display-only observation quietly gain gate/size authority?
5. Did any null become a zero, NONE or calm vote?
6. Are all clocks first-known/PIT honest?
7. Did the worker create a new truth store, event store, queue, market-data plane, ranker or portfolio market model?
8. Did the PR mutate Prophet rank/population or hide counterfactual candidates?
9. Is every action tied to a registered policy ID rather than a generic risk state?
10. Does stale data fail toward honesty/caution rather than green?
11. Is repair independently represented?
12. Are claims at the declared horizon only?
13. Are production URLs/served bundles and browser/machine consumers proven?
14. Are correction and rollback demonstrated?
15. Is a spec being called shipped?
16. Did CI pass only because a test used a sparse/missing data tree?
17. Did the PR touch a currently owned/colliding path from another workstream?
18. What discovery/decision/handoff must be recorded before merge?

A technically excellent PR that fails one of the architecture questions is rejected.

---

# 15. Current open-PR collision and sequencing matrix

| Existing PR | Grey Deer implication | Fable action |
|---|---|---|
| Macro #5925 Entry Radar pack repair | Owns `engine/entry_radar/live_pack.py`; still owes prod proof | No GD edits to that file; consume after merge/acceptance |
| Macro #5929 Radar W4.1 transport | Owns confirmed-lane/spool transport/reconciler | No GD edits; live envelope may later consume accepted Radar outputs |
| Macro #5928 Prophet Lab API | Read-only lab, all authority false | Do not add Grey Deer behavior inside this PR |
| Macro #5737/#5931/#5940 reference work | UI/integrity programs | Do not restyle or adopt as Grey Deer canonical UX without separate reference review |
| Macro #5954 CI gate classification | Moving `.github/ci/legacy-jobs.yml` and CI loader | Grey Deer does not touch CI manifest until resolved/rebased |
| Macro #5948 backfill push fix | Moving backfill workflow | Do not touch backfill; no need for Grey Deer |
| Macro #5953 China Alpha canonical research | AgentOS/research activity in China program | Separate filenames; rebase AgentOS records cleanly; do not absorb the program |
| Terminal #418/#419 | Company intelligence / generic responsive e2e movement | Use dedicated Grey Deer e2e file, avoid broad shared tests where possible |
| Mastermind #72/#66/#84 | Executive governance and harness | GD Portfolio waves must not touch executive authority/worker paths |

### CI grant warning

The CI-control-plane program has a specific operator grant for its own waves. **Grey Deer does not inherit that grant.** Do not admin-merge a Grey Deer authority-changing PR over red main merely because #5954 or #5938 describes an exception elsewhere.

---

# 16. Exact acceptance matrix by PR class

| Wave | PR type | “Done” evidence | Must NOT be called done by |
|---|---|---|---|
| GD-0A | records/semantic registry | merged, discoverable canonical program + decisions | local files only |
| GD-1A | research prereg | hash pinned before outcome access | prose after seeing results |
| GD-1B | research replay | reproducible PIT timeline + adversarial review | one anecdotal chart |
| GD-2 | Macro vertical slice | settled source → envelope → real browser | JSON generation only |
| GD-3 | live vertical slice | real live source → served live envelope → browser latency receipt | unit tests / cron comment |
| GD-4A | operational truth repair | real Asia-close ledger advances once | fixture-only append |
| GD-4B | CN product observation | real live board aggregate visible | helper function only |
| GD-4C | China liquidity context | real PBOC bulletin→typed interpretation surface | operation parser only |
| GD-5* | statistical shadow | PIT replay + forward accrual begins | in-sample fit |
| GD-6* | Prophet shadow sidecar | raw board identical + sidecar/counterfactual accrues | mock sidecar |
| GD-7 | authority | real admitted candidate is visibly withheld, counterfactual retained | config flag exists |
| GD-8A | alert vertical | real transition produces one deduped alert | message builder unit test |
| GD-8B | Terminal vertical | same Macro bundle ID visible in Terminal | local copied JSON |
| GD-9A | Portfolio shadow | real envelope consumed, zero book mutation, diff receipt | adapter unit test |
| GD-10 | Portfolio authority | real canonical envelope controls book policy + rollback proven | shadow comparison |
| GD-11 | learning | matured outcomes and policy utility visible | schema with empty rows |

---

# 17. Program-level failure states

Fable must design/test these explicitly, not as exceptions discovered later:

- live feed behind settled;
- settled behind market session;
- one hazard expert stale, others fresh;
- all fast experts unavailable;
- corrected source invalidates prior stage;
- Chronicle append fails;
- Reflex firing persists but QLedger grade fails;
- policy sidecar references wrong board hash;
- board regenerated after sidecar;
- Prophet candidate missing vulnerability classification;
- risk says breakdown but credit says calm;
- slow state Risk-on while hazard Breakdown;
- repair impulse during continuing selloff;
- repair confirmation then immediate failure;
- temporary policy expires while data is stale;
- Terminal mirror stale while Macro is current;
- Portfolio envelope unavailable;
- regional market on holiday while global contagion is live;
- PBOC zero operation during ample liquidity;
- policy/issuer support creates a single-name bounce only;
- forecast horizon matures without outcome data;
- source rights prohibit storing the needed historical field.

Each state needs a deterministic user/machine behavior, not a generic `try/except`.

---

# 18. Exact next actions for Fable

## First action — GD-0A

Create one records/semantic-registry PR that lands the Grey Deer freeze, workstream, decisions, handoff, semantic-program registration and generated system map. Do not touch runtime or CI paths.

## Parallel action — dispatch Grok GD-1A

Give Grok the hardened replay packet. Require a prereg hash before any outcome-bearing replay and force a return of `BLOCKED` for unprovable intraday clocks.

## Parallel action — prepare GD-2/GD-4 archaeology only

Fable may assign bounded scouts to:

- enumerate exact producer/consumer paths for the settled envelope vertical;
- reproduce China/HK ledger freeze;
- identify the exact existing live publisher/VPS seam.

Scouts may not implement until GD-0A is merged and Fable reconciles their findings against the freeze.

## Do not start yet

- no Grey Deer policy authority;
- no Prophet sidecar live behavior;
- no Portfolio cutover;
- no new model training;
- no automatic exits;
- no old risk score re-weighting.

---

# 19. Required continuation handoff from Fable

At the end of each accepted PR, Fable writes/updates the workstream and a handoff containing:

- merged PR and merge SHA;
- current main SHA;
- capability now proven live;
- exact production receipt/URL/bundle ID where applicable;
- source/session freshness;
- unresolved gaps;
- decisions/discoveries minted;
- path ownership/collisions for next wave;
- exact next authorized PR;
- explicit “do not start” boundary.

No session ends with “next: continue Grey Deer.” It names the one next observable capability.

---

# 20. Fable stop condition for the entire program

Fable must escalate to Sol rather than continue if any of the following becomes necessary:

- changing the three-answer product thesis;
- introducing an opaque composite or fused shield;
- changing Prophet raw ranking/admission semantics;
- allowing an LLM to originate authority;
- creating a second lifecycle or event store;
- giving Macro actual portfolio execution power;
- giving Portfolio independent market-truth origination after cutover;
- adding automatic exits to V1;
- lowering the Turn-3 promotion gates;
- using revised data to rescue a failed predictive result;
- expanding temporary safety authority beyond its explicit Chairman grant.

Those are CEO/Chairman architecture decisions, not implementation details.

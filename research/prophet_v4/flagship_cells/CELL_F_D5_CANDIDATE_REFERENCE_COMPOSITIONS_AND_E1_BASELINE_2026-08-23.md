# Cell F — candidate-level D5 reference compositions and deterministic E1 baseline

**Status:** NORMATIVE RESEARCH AMENDMENT for MAS-122 / Cell F; records/research only  
**PR:** #6275  
**Runtime state:** `prophet.intelligence_vector/v1` remains `SPEC_ONLY`; canonical `prophet.candidate_episode/v1` B1 does not yet exist  
**Authority:** no runtime, ranking, availability, sizing, origination, Fusion, Context Vector, or execution mutation is authorized by this document

This amendment makes the frozen Cell F semantics executable as research examples without pretending that a canonical V4 episode exists. It also freezes the deterministic **E1 baseline recommendation** that later V4-E1 implementation must reconcile with the canonical V4 architecture and the accepted Conditional Fusion registry.

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

Every `REF-F-*` identifier below is a research-only label. It is **not** an `episode_id`, cannot be written to a runtime episode store, cannot satisfy D5's required `episode_ref`, and cannot be used as a surrogate lifecycle key. Once B1 exists, implementation tests may reproduce the same semantic shapes against owner-issued canonical episodes.

---

## 1. Cross-cutting laws exercised by every composition

1. **B1 identity first.** Runtime D5 starts from an owner-issued canonical `prophet.candidate_episode/v1`. A ticker/date row, Context Vector row, fixture, Lab row, or Entry Radar `mastermind.live_entry_episode.v1` is not a substitute.
2. **No Context Vector mutation.** Context Vector may be referenced as the existing PIT historical/research substrate. D5 adds no columns and does not widen `engine/us_context_vector.py`.
3. **An unbuilt adapter emits no family envelope.** Adapter readiness may be disclosed outside `evidence_families[]`; it is not episode evidence. Once an adapter exists, lawful per-episode absence can be represented by the normal D5 applicability/coverage/freshness/rights/identity axes and typed `ABSENT` observations.
4. **Root count is not independence.** `evidence_roots[]` records provenance. `economic_dependence_groups[]` records known/common economic information. Distinct documents or providers do not become multiple votes merely because their source IDs differ.
5. **Measured neutral is evidence that measurement happened.** It is distinct from missing, `NOT_COVERED`, `NOT_APPLICABLE`, `RIGHTS_BLOCKED`, stale, producer-degraded, or an absent adapter.
6. **Decision-time belief is immutable.** Later corrections/reversals create linked later projection receipts; they never rewrite the observations admissible at the original decision cut.
7. **D5 has no rank authority.** Only an explicit binding to an accepted Conditional Fusion member/version can make an owner-native observation eligible for deterministic E1 consumption. D5 family presence, semantic heads, explanation facts, provider counts, root counts, dependence-group counts, quality metadata, or coverage ratios never become votes by themselves.
8. **Availability remains a hard orthogonal plane.** Strong intelligence can order research inside the lane that B4 determines; it cannot make `ENTRY_OPEN`, waive chase/invalidation, or cross an availability barrier.

---

# 2. Candidate-level research reference compositions

## REF-F-01 — high genuinely independent confluence

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-01`  
**Question tested:** Can several strong observations coexist without D5 itself counting “three confirmations”?

Illustrative decision-cut state:

- `earnings.event`: applicable, covered, current, rights-allowed, identity-resolved, decision-admissible; owner records an upward guidance/revision fact under a stable event workspace.
- `capital_structure.event`: applicable, covered, current, rights-allowed, identity-resolved, decision-admissible; owner records a distinct balance-sheet/financing fact whose economic cause is not the earnings release.
- `options.eod_positioning`: applicable, covered, current, rights-allowed, identity-resolved, decision-admissible; owner records a covered-session positioning state under its native method.
- three distinct source roots are present **and**, only after economic review, three distinct dependence groups are recorded because the observations arise from genuinely separate underlying information.
- each family may carry zero or more explicit `fusion_bindings[]`; only accepted bound members can later enter E1.

Expected D5 behavior:

- preserve all three owner-native observations and their lineage;
- expose the separate dependence groups;
- do **not** emit `evidence_count=3`, “three votes,” “confidence=high,” or any combined score;
- semantic heads may group the evidence for research display but do not aggregate it.

Expected E1 behavior later:

- if all three observations are explicitly bound to accepted Fusion members, E1 may transform those **registered member values** under the accepted deterministic Fusion/E1 method and anti-double-count budgets;
- the fact that three D5 envelopes exist is not itself an input.

---

## REF-F-02 — fake confluence collapses to one common ancestor

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-02`  
**Question tested:** Do multiple documents that restate one event become fake confirmation?

Illustrative decision-cut state:

- an earnings release, associated 8-K exhibit, and conference-call transcript are three source objects;
- the specialist owner proves all three principally encode the **same quarterly result/guidance shock**;
- D5 therefore records three `evidence_roots[]` for provenance but one shared `economic_dependence_group` for the underlying shock;
- any separate transcript-derived owner fact must identify a genuinely distinct method/object before it can escape that common group.

Expected D5 behavior:

- preserve all roots and exact source references;
- expose the common ancestor/dependence grouping;
- never translate “three documents” into three independent confirmations.

Expected E1 behavior later:

- the accepted Fusion registry's one-column/one-family and anti-double-count budget remains controlling;
- duplicated restatements cannot gain weight by entering through separate D5 roots or semantic heads.

---

## REF-F-03 — strong evidence coexists with fragility/crowding

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-03`  
**Question tested:** Can a candidate remain attractive on some evidence while simultaneously carrying a material risk/crowding state?

Illustrative decision-cut state:

- `earnings.event`: strong favorable owner-native event/revision observation, admissible and current;
- `capital_structure.event`: no adverse current event and/or a favorable owner-native liquidity/capacity observation where the source contract actually supports it;
- `options.eod_positioning`: covered and current, but the owner-native state indicates unusually crowded/fragile positioning rather than confirmation;
- any market/fragility observation enters only if its specialist owner has an implemented adapter and accepted Fusion registration; D5 does not invent a generic “risk score.”

Expected D5 behavior:

- preserve favorable and adverse observations side by side;
- do not subtract one from another or issue a net conviction value;
- keep family-native trajectory and quality semantics separate.

Expected E1 behavior later:

- accepted Fusion members may make deterministic capped contributions in their registered directions;
- the anti-double-count budget and frozen deterministic method—not D5—determine how competing eligible contributions affect raw/conservative priority;
- no favorable intelligence can waive B4 availability.

---

## REF-F-04 — missing, not covered, and absent adapter are three different states

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-04`  
**Question tested:** Can the system stay honest when coverage is sparse?

Illustrative decision-cut state:

- `earnings.event`: implemented adapter; applicable, covered, current, measured;
- `options.eod_positioning`: implemented adapter; applicable but `coverage.state=NOT_COVERED`; observation is `ABSENT` with the owner-native typed reason;
- `theme.theme_state`: canonical specialist contract/adapter is not yet built for D5 at this point, therefore **no Theme family envelope exists at all**;
- another implemented family may be `NOT_APPLICABLE` only when the source owner can positively establish non-applicability.

Expected D5 behavior:

- never create a Theme placeholder with `ACCRUING`, null score, or zero contribution inside `evidence_families[]`;
- never convert Options `NOT_COVERED` to neutral/zero;
- disclose lawful coverage/readiness separately.

Expected E1 behavior later:

- only measured/current/admissible registered members are eligible;
- `NOT_COVERED` and absent adapters **abstain rather than cast zero votes**;
- `NOT_APPLICABLE` is excluded from the relevant coverage denominator when the accepted member contract says the row is outside its population;
- coverage is disclosed and can force a degraded/`PRIORITY ACCRUING` basis; higher coverage is never positive alpha by itself.

---

## REF-F-05 — correction/reversal after the decision cut

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-05`  
**Question tested:** Does a later correction silently improve or worsen the historical decision-time vector?

Illustrative sequence:

1. At decision cut T0, the source owner publishes/captures version `V1`; it is decision-admissible and is the observation D5 knew.
2. At T1 > T0, the owner publishes a correction/reversal `V2` that changes the current interpretation.
3. The original D5 projection remains immutable and points to `V1` in `decision_version_ref_ids[]`.
4. A later correction-aware D5 assembly creates a **new content-addressed projection receipt**, links `V2` through `later_correction_ref_ids[]`, and preserves the original T0 observation unchanged.

Expected E1 behavior later:

- same-tape replay/ranking at T0 may consume only the T0-admissible registered member derived from `V1`;
- `V2` cannot leak backward into T0 rank;
- a current research/audit view may show the reversal beside the historical decision belief without rewriting it.

---

## REF-F-06 — rights block a potentially useful observation

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-06`  
**Question tested:** Does “we can see it” accidentally become “we can rank/render it”?

Illustrative decision-cut state:

- specialist source object exists and would otherwise be relevant;
- owner rights profile resolves `rights.state=BLOCKED` for the intended D5 use, or the necessary permission is `UNKNOWN` and therefore not safely usable;
- prohibited value/body is not serialized into D5 and hidden later; the observation is `ABSENT` with `RIGHTS_BLOCKED` where the implemented adapter contract permits that status;
- `source_ref.render_policy` independently controls whether any allowed reference/body can be displayed.

Expected D5 behavior:

- preserve the typed rights refusal without leaking the blocked content;
- do not infer a negative/neutral signal from the refusal.

Expected E1 behavior later:

- no rank contribution exists from the blocked/unknown-rights value;
- rights availability does not become a ranking feature.

---

## REF-F-07 — measured neutral is not missing

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-07`  
**Question tested:** Can a source say “I measured this and found neutral/no event” without being confused with darkness?

Illustrative decision-cut state:

- `options.eod_positioning`: implemented, applicable, covered, current, rights-allowed, identity-resolved;
- the specialist owner actually computed the covered session and its contract returns an explicit native neutral / `NO_SIGNAL` state;
- or an event-sparse registered member positively establishes “no qualifying event in the defined window” under its measured-negative semantics.

Expected D5 behavior:

- record the owner measurement as measured neutral/measured negative according to that owner's exact contract;
- coverage counts the family as measured where the owner contract says the producer answered;
- do not encode neutral simply because a row/value is absent.

Expected E1 behavior later:

- an accepted Fusion member may map its **explicit measured neutral** to its deterministic neutral contribution when that mapping is part of the registered method;
- this is the only lawful “neutral/zero-like” case—it arises from positive measurement, not missingness.

---

## REF-F-08 — strong intelligence while deterministic entry is unavailable

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

**Research candidate:** `REF-F-08`  
**Question tested:** Can very strong intelligence remain visible without reopening a closed/invalid trade?

Illustrative state:

- D5 has several current, admissible, rights-safe observations that would be eligible for accepted Fusion members;
- B4 independently determines `availability_state=RAN_DONT_CHASE`, `WAIT_PULLBACK`, `INVALIDATED`, or `UNAVAILABLE_DATA` rather than `ENTRY_OPEN`.

Expected D5 behavior:

- evidence remains available for research/context;
- D5 has no `entry_open_delta`, gate override, or sizing authority.

Expected E1 behavior later:

- E1 may order the candidate **only inside the availability lane B4 assigned** (or keep it visible in All Candidates / degraded views as product law requires);
- intelligence cannot move the candidate into `ENTRY_OPEN`, bypass a chase threshold, or waive missing required availability inputs;
- an extremely high deterministic priority in a non-entry lane remains a research priority, not permission to buy.

---

# 3. Deterministic V4-E1 baseline recommendation

## 3.1 Owner boundary

E1 is the deterministic **ordering projection**. D5 is the evidence read-model. Conditional Fusion owns the cross-family member registry, anti-double-count grouping, and rank machinery. B4 owns deterministic availability.

Therefore the E1 implementation must preserve this direction:

```text
canonical B1 episode
  → B4 deterministic availability lane
  → D5 owner-grounded decision-time evidence
  → explicit accepted Fusion member bindings only
  → deterministic E1 transform under accepted Fusion/E1 method
  → order inside the already-determined availability lane
```

There is no reverse edge from E1 rank/priority, D5 evidence strength, or Fusion output into `ENTRY_OPEN`.

## 3.2 Exact D5 eligibility gate for deterministic E1

A D5 observation is **not** rank-eligible merely because it exists. For E1 to consume it, all of the following must hold:

1. the runtime D5 projection is keyed to a real owner-issued canonical `prophet.candidate_episode/v1` and the exact decision cut;
2. the specialist contract and D5 adapter are implemented—an unbuilt adapter contributes no family envelope and therefore nothing to E1;
3. `decision_admissibility=ADMISSIBLE`; `RESEARCH_ONLY_RECONSTRUCTION`, `AFTER_DECISION_CUT`, and `UNVERIFIABLE` cannot affect the production decision-time rank;
4. subject/identity binding is resolved to the grain required by the accepted member contract; guessed/ambiguous/unresolved bindings abstain;
5. rights permit the rank use under the source-owner profile; `BLOCKED` or unresolved/unknown permission cannot contribute;
6. freshness satisfies the registered member's currentness rule; stale evidence is excluded from current scoring by default rather than decayed by Cell F;
7. coverage/applicability says the owner actually answered for the row under its contract. Missing, `NOT_COVERED`, producer-degraded, or unavailable observations abstain; genuine `NOT_APPLICABLE` does not become a negative vote;
8. the exact observation/method has an explicit `fusion_binding` to an **accepted Conditional Fusion member + registry/version**. Empty `fusion_bindings[]` means display/research context only;
9. correction handling uses the decision-version object that was admissible at that cut; later corrections never leak backward;
10. all anti-feedback/prohibited-input guards pass: board rank, lane, featured state, manual action, plan state, outcome label, and other downstream consequences are absent from the input.

## 3.3 Deterministic transform after eligibility

The frozen V4 baseline remains:

> **accepted registered member values → same-tape cross-sectional percentile/normalization defined by the accepted Fusion/E1 method → capped contribution inside the registered Fusion anti-double-count family budget → raw priority + conservative priority → rank inside the B4 availability lane by conservative priority, then freshness, then deterministic ticker tie-break.**

Implementation must use the accepted registry's exact member directions, transforms, coverage floors, strata/era rules, and caps. Cell F does **not** invent replacement weights or a second ranker.

The two priority views have different disclosure jobs:

- **raw priority** reports the deterministic combination of the eligible registered contributions actually available for the candidate under the accepted method;
- **conservative priority** is the E1/Fusion method's coverage/uncertainty-aware ordering value. Missing members **abstain**; they are not filled with zero. If the accepted method cannot support a defensible comparable conservative value at sparse coverage, the product publishes a degraded/`PRIORITY ACCRUING` basis rather than fake precision.

Coverage is always published separately. A higher coverage ratio/band is **not itself positive evidence** and cannot raise priority merely because more sources answered.

Measured neutral is different: when an accepted member contract positively measured the row and defines a neutral value, that explicit measured-neutral value may produce the registered neutral contribution. That is not missing-value imputation.

## 3.4 What E1 may consume from D5/Fusion

E1 may deterministically consume only:

- owner-native observations or deterministic derivatives already admitted by their specialist contract;
- the exact registered feature/member value named by an explicit D5 `fusion_binding` or equivalent canonical Fusion join;
- member-native missingness/coverage/applicability/freshness metadata **only for eligibility, abstention, conservative-basis disclosure, and the accepted method's coverage law**;
- accepted registry direction, transform, family budget/cap, era/strata, PIT and staleness rules;
- decision-cut provenance needed to prove the value was lawful at that time.

E1 does **not** treat D5 as a score producer.

## 3.5 What cannot influence rank without separate promotion/authority

The following remain incapable of influencing production ordering merely by appearing in D5:

- D5 `evidence_family_id` presence or number of populated families;
- semantic heads or number of semantic heads;
- source/provider/root counts;
- `economic_dependence_groups[]` counts or an inferred “independence score”;
- explanation facts, prose summaries, citations, or model-generated narrative;
- quality/confidence metadata unless a specific specialist-derived variable is separately admitted as an accepted Fusion member under forward evidence;
- coverage ratio/band as positive alpha;
- an unbuilt adapter or an absent family placeholder;
- stale, after-cut, reconstructed-only, unverifiable, rights-blocked, ambiguous-identity, or not-covered evidence;
- Context Vector rank/board outputs and any downstream board consequence;
- manual actions, featured status, plan status, or outcome labels;
- any new specialist family that has not obtained an explicit accepted Fusion member binding;
- LLM/model outputs at birth; they remain context until point-in-time replay and forward promotion earn a narrowly defined authority;
- learned E3 LambdaMART, E4 router/multi-head, or E5 temporal-graph challenger outputs. They stay shadow-only until the E6 promotion gauntlet separately accepts them.

Adding a new Fusion member, changing a member transform/direction/cap, or granting a statistical/model output rank authority is **not a Cell F documentation tweak**. It is a Conditional Fusion/Evaluation promotion operation with same-tape replay, forward evidence, era/versioning, and the applicable DNR/owner gates.

## 3.6 Availability and E1 ordering

B4 determines the availability lane before E1 orders it. E1 may not compare candidates by silently pretending availability is another intelligence feature.

- `ENTRY_OPEN` candidates may be ordered against other `ENTRY_OPEN` candidates.
- `APPROACHING_ENTRY`, `WAIT_PULLBACK`, `RAN_DONT_CHASE`, invalidated/expired, and other product lanes retain their own ordering/projection semantics.
- `UNAVAILABLE_DATA` is never green; strong intelligence cannot waive its missing required availability input.
- an E1 priority value is a research-ordering value, not trade permission, probability, expected return, or sizing advice.

---

# 4. Learned-ranking boundary

E1 exists deliberately before learned ranking so Mastermind has a transparent, reproducible baseline and same-tape comparator.

The later sequence remains:

```text
E1 deterministic baseline
  → E3 listwise challenger (shadow)
  → E4 conditional router / multi-head challenger (shadow)
  → E5 temporal heterogeneous graph challenger (shadow)
  → E6 forward promotion gauntlet
  → only then any separately accepted production authority
```

No learned system gets production ordering authority because its offline metric is better, because its explanation sounds convincing, or because D5 has richer evidence. Promotion requires the V4/Evaluation OS forward gauntlet and a new accepted era/authority ruling.

---

# 5. Stop law

This document is research/architecture only. It does not implement B1, D5, E1, a Fusion registry change, any rank transform, Context Vector mutation, ThemeState, Earnings adapter, availability logic, or product ordering.

Exact continuation remains:

`V4 A1 acceptance/adoption → canonical V4-B1 candidate episode → Cell F Earnings thin adapter`

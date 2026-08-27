# K3-E Opportunity Evidence Vector — contract freeze — 2026-08-25

Status: **CANDIDATE FREEZE; DRAFT / HOLD-FOR-SOL; NO STORE BUILT; NO CONSUMER ARMED**

This is the canonical **Alpha Intelligence K3-E** return packet: one typed, closed
Opportunity Evidence Vector contract plus its semantic validator and golden/hostile
fixture proofs. It lets a future OpportunityCase (K5) or Market OS consumer understand
an opportunity **without a fused score**: what is observed, what is inferred, what the
market appears to reflect, the strongest unresolved fact, failed/unavailable gates, the
next observable, and Entry Availability — each independently visible.

This is NOT the similarly named **K3E Expectation ↔ Market Dynamics child-program**
(`research/alpha_intelligence/expectation_market_dynamics/`,
`DEC:K3E-EXPECTATION-MARKET-DYNAMICS-FREEZE`). Neither object renames, replaces, or
duplicates the other; that program's own handoff already fences the two
("Treating K3E-0 as canonical K3-E would overwrite the existing Opportunity Evidence
Vector semantics" — `agentos/handoffs/ALPHA-INTELLIGENCE-INTEGRATION-2026-08-23-k3e0.md`).

## 1. Authority and current-state reconciliation

Protected Mastermind Skillpack loaded atomically from exact
`mastermindx-market-intelligence/Mastermind` protected `master` commit
`51f9942733b86e550bb9169d2a43462bd28e774f` (`docs/sol_skills/INDEX.md` schema
`mastermind.sol_skillpack.v1`, version `1.0.0`, minimum bootstrap major `1`;
`COLD_START.md` from the same commit). Macro canonical base fresh-pinned at
`origin/main` = `2c20168df5d9e711825f7fca5983b4bbab69711d` — identical to Sol's
census pin; the base did not move between commission and pin.

Full open-PR / worktree / path-collision census (this session, 25 open PRs
enumerated, 238-line worktree list, remote-branch sweep): **path surface CLEAR.**
No open PR, live worktree, or remote branch touches
`research/opportunity_evidence/**`, `research/evidence_mesh/**`,
`contracts/evidence_foundation/**`, the WS record, or its handoffs; no file matching
`*opportunity*vector*` exists anywhere on pinned main; no `sol/mas-*`/`fable/*`
parallel carrier is open on `WS:ALPHA-INTELLIGENCE-INTEGRATION`. The K3E-0
child-program carrier PR #6333 is CLOSED (its content landed via other merged work)
and shares no file with this packet.

Program state consumed (not assumed):

- **K1 Evidence Foundation v1.0.0 is ACCEPTED / DONE** at exact head
  `b7b861a288491ba776dda0087b6153c346e9aabc`, merge
  `696afbb57483577770ac48c57f7eeafd5344cf17` (PR #6319). K3-E consumes its
  vocabulary and changes nothing in it.
- **C0 §4.1 ruled E0 ACCEPTED with conditions on K3-E and the lane READY to
  commission in parallel with K1** (`research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md`).
  Every §4.1 ruling is disposed in §5 below.
- **Market OS B1A has since STARTED and landed** (Chairman-dispatched 2026-08-24):
  `contracts/market_os/security_state.v1.schema.json` + `engine/security_state.py`
  are live on main. Its `legs.opportunity_context` ships with
  `market_incorporation = {"ref": null, "state": "NOT_COVERED"}` and
  `dislocation = {"ref": null, "state": "NOT_COVERED"}`
  (`engine/security_state.py:969-994`) — the precise typed gap this contract's
  object is positioned to fill for a future, separately authorized wave. K3-E
  supersedes the K1-era landmine prose that called the B1 job "bounded future":
  that prose described 2026-08-23 state; B1A is now on main and this packet
  neither modifies nor extends it.
- K2-B proceeds on its own carrier; no file overlap with this packet.

## 2. What this object is — and is not

The Opportunity Evidence Vector is a **typed VIEW/JOIN projection over canonical
owner outputs** for one subject at one decision time (`asof` = t0, always taken from
an existing PIT object, never optimized after outcomes). It is:

- **Not a store.** No `data/opportunity_vector/`, no `engine/opportunity_*` producer,
  no synapse row, no index, no warehouse, no payload copy. The composer
  (`lib/opportunity_evidence.compose_vector`) is pure in-memory over caller-supplied
  owner reads and persists nothing (test-enforced source scan).
- **Not consumed or written by Prophet or Radar.** `permitted_consumers` is a closed
  enum {research_session, opportunity_case_k5, market_os_security_state_view,
  operator_display}; Prophet ranking/gating and Radar detection are not members and
  cannot be added within v1. Entry Availability is a verbatim owner READ under
  `DEC:PROPHET-LAB-B5A-RECUT`'s read/filter/join/decorate-only verbs.
- **Not a score.** No numeric aggregate exists on the wire beyond denominator counts.
  The authority envelope is the exact K1 all-false set including `can_open_entry`.
  Any aggregate prints its denominator receipt and dominant degradation.
- **Not an origination surface for any LLM.** `provenance_class` has no LLM member;
  no LLM may originate facts, ranks, scores, probabilities, gates, or the
  opportunity itself, anywhere in this contract.

Residual terms are **read from canonical owners, never re-derived**: the DRL seam
(`engine.price_pressure.ledger.read_ledger`; DRL = Dislocation & Recovery Lobe,
`engine/price_pressure/`) and `engine/residual_alpha.py` — two different
residualizations, never interchangeable, never merged.

## 3. Frozen contract surface

Contract version `1.0.0`:

- `contracts/opportunity_evidence/vector.v1.schema.json` — closed
  `opportunity_evidence.vector.v1` wire (subject, **reference-bound** decision
  clock, typed slots, the seven projection legs, separate economic-cause hypothesis
  object, denominator receipt, dominant degradation, all-false authority,
  deterministic content hash).
  The decision clock carries `{value, grain, t0_source, t0_mode, t0_evidence_ref}`:
  `t0_evidence_ref` is an immutable owner-backed PIT reference in K1 `reference.v1`
  EvidenceRef shape (`owner_store`, `native_identity`, `native_digest`, plus a known
  minting clock), and `t0_mode` ∈ {`live`, `retrospective_research`} — K1
  `replay.mode` vocabulary, with per-source permission pinned in the registry
  (`lawful_t0_modes`). The retired free-string `t0_source_object` and its
  `caller_named_pit_object` source are **structurally unrepresentable**
  (test-pinned). **How strong "authenticated" is depends on the source, and this
  packet never claims it uniformly:** the four registry-pinned sources are
  validation-checkable (`owner_store` and clock class are compared against pins) and
  may claim `live`; the generic `owner_pit_reference` declares its own store and
  clock, so it is an accountability receipt rather than a verification and is capped
  at `retrospective_research` (§7.4 item A, §8.8). Nothing here reads an owner's
  bytes — this contract holds no owner I/O by design.
- `contracts/opportunity_evidence/slot_registry.v1.json` — the executable
  family-mapping receipt: every admissible construct with owner, read seam, K1 clock
  bindings over unrenamed native fields, object class, and exactly one of
  {governed_family (family, member pinned to `research/prophet_fusion/families.yml`),
  research_only, candidate_new_family → K5/Eval OS}; plus the unowned axes, the
  forbidden constructs, and the fusion `FORBIDDEN_INPUTS` fence.
- `lib/opportunity_evidence.py` — combined structural + semantic fail-closed
  validator (stable `K3E_R###` rule codes) and the deterministic in-memory composer.
  Public validation loads only the repository contract files (no caller-supplied
  vocabulary seam, mirroring K1).
- `tests/fixtures/opportunity_evidence/` — golden + hostile packet with exact
  byte/SHA-256 manifest receipts.
- `tests/test_opportunity_evidence_vector_contract.py` — executable proofs,
  including the mutation-kill matrix (§6).
- `.github/ci/legacy-jobs.yml` — one binding step in the existing `signal-contract`
  lane (the same lane and pattern K1 and K2-B used; no new workflow or job).

## 4. Typed slot semantics and K1 reconciliation

Each slot freezes at least
`{construct, state, asof, known_at, value_or_null, coverage_flag}` and materializes
additionally: registry-pinned `family_binding`, K1 `object_class`, an owner pointer
(`owner_ref`, optionally carrying a K1 `efr_` EvidenceRef id), `derivation`
(`owner_read` | `deterministic_join` — deterministic composition may **choose and
route** typed owner outputs by frozen rules; it never computes new values;
every v1 registry construct pins `owner_read`, and `deterministic_join` is a
reserved member for future routed constructs, unused in v1),
`provenance_class`, K1-exact `missingness`, `basis` (peer-basis disclosure where
required), `variation_receipt` (flow constructs), and explicit
inclusion/exclusion with typed reasons.

**No fifth PIT vocabulary is minted.** The reconciliation with accepted K1
EvidenceRef/EvidenceBlock vocabulary is literal and test-enforced:

| K3-E surface | K1 vocabulary reused | Enforcement |
|---|---|---|
| `asof` / `known_at` clock classes | the exact seven K1 clock classes over unrenamed owner-native fields (`world_valid`…`review_due`); registry pins class + native field per construct | enum-equality test against `reference.v1.schema.json`; `K3E_R006` pins per-slot |
| `missingness` | K1 `{state, reason, zero_substituted:false}` with the identical closed reason enum | enum-equality test; `K3E_R005` |
| `object_class` | K1's five classes; an `instrument_state` is never a market verdict | `K3E_R011` leg-membership law |
| availability `state` | typed states {observed, modeled, missing, stale, rights_blocked, conflicted, unsupported, identity_unresolved, unknown} — the commissioned six adverse states plus observed/modeled/unknown; each adverse state crosswalks to a K1 reason (stale→stale, rights_blocked→rights_blocked, identity_unresolved→unresolved_identity, unsupported→unsupported, missing→{not_available_for_date, source_missing, not_applicable, explicit_none, quarantined, reconstructed_not_operational_pit}); `conflicted` crosswalks to the K1 block-level conflict state | schema conditionals + `K3E_R005`; none of these states ever becomes zero or neutral |
| aggregates | denominator receipt + dominant degradation, inherited from the K1 block law; counts are the only lawful aggregate arithmetic; dominant severity is the strict order conflicted > corrected > identity_unresolved > rights_blocked > missing > unsupported > unknown > stale > partial_coverage | `K3E_R015`; schema has no other numeric aggregate field; `value_or_null` is typed flat-scalar with a payload key fence so no score/weight/rank structure can ride inside a value |
| free text | every prose field (`coverage_flag.note`, `set_because`, gate `reason`, `fact`, `exclusion_reason`) is length-capped and DISPLAY-ONLY by consumer law: no consumer may parse values, scores, ranks, sizes, or entry directives out of free text | schema maxLength caps + description law; typed payloads carry every machine-readable fact |
| decision-time origin | `t0_evidence_ref` reuses `reference.v1`'s `owner_store`, `native_identity` (same `propertyNames`/`maxProperties`), and `nativeDigest` shapes field-for-field; `t0_mode` reuses `replay.mode`'s two decision-lawful members; the minting clock reuses this contract's K1-reconciled `clockValue` narrowed to the three minting classes | literal shape-equality test against `reference.v1.schema.json`; `K3E_R021` authenticates every reference against the registry `t0_sources` pins |
| authority | the exact K1 all-false envelope incl. `can_open_entry` | schema consts |
| identity | owner-native subject identity; cross-owner joins lawful only via owner-approved bridges (Earnings `company_identity.v1` PIT alias / Data OS master); a nominal ticker match is not proof | `K3E_R010`; the forbidden symbol-directory + `cik_map` route stays forbidden |

The seven authenticated-MO projection legs are separate required top-level objects —
`observed`, `inferred` (labeled `owner_derived_system_belief`), `market_reflection`
(I1–I7 typed incorporation states; I7 persistence is structurally `ex_post_excluded`
in any t0 vector), `strongest_unresolved_fact`, `failed_or_unavailable_gates`,
`next_observable`, `entry_availability` — none derivable only by unpacking another,
none hideable behind a composite.

## 5. Binding-law disposition

| Law | Disposition in this contract | Evidence |
|---|---|---|
| C0 §4.1 r1 — dislocation decomposition lawful; pin per-term emission; forbid reconstituted scalar in one sentence | **SATISFIED.** Registry `decomposition_groups.dislocation.law`: "emits named per-term components only and may never be reconstituted into one scalar…"; `K3E_R004` kills sums and forbidden constructs; `ret_raw` is the only lawful identity total | registry; `hostile_disloc_reconstitution` |
| C0 §4.1 r2 — impairment axis has NO owner; never attribute to DRL | **SATISFIED.** `unowned_axes.company_impairment_attribution` states the vacancy with the re-run receipt (grep for `impair` over DRL masterplan + `engine/price_pressure/*.py` exits 1); DRL rows carry only residual-shock + filing-COVERAGE constructs; `K3E_R017` kills impairment-claiming constructs | registry; `hostile_impairment_axis` |
| C0 §4.1 r3 — cite `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` incl. its retune clause | **SATISFIED.** Cited by key in the registry with the clause ("do not re-propose by re-tuning z/volume/horizon/peer-basis/label taxonomy") and the coverage-blocked-not-null analyst-revision reopener | registry decomposition kills |
| C0 §4.1 r4 — vector = view over `data/us_prophet_rank/candidates/`; neither Radar nor Prophet consumes; residuals imported never re-derived; two-object split; typed slot schema; W5 score-search prohibition | **SATISFIED.** §2 above; `K3E_R008` (re-derivation), `K3E_R009` + separate `economic_cause_hypothesis` object (two-object split, never computed from ε), closed `permitted_consumers`, registry Radar note pinning the W5 contamination law (`DNR:KILL-OUTCOME-AUDITION`, PR-0 §18 A2.5) | schema; registry; hostiles R008/R009/R011 |
| C0 §4.1 r5 — ETF-flow state from observed artifact variation, default stale | **SATISFIED.** `variation_required` + `K3E_R012`; the SPY `so_mn` five-week-constant defect is the hostile | `hostile_flow_nominal` |
| C0 §4.1 r6 — fusion-family map; one-column-one-family; candidate new families route K5/Eval OS | **SATISFIED.** §6 below; the map is executable (registry ↔ `families.yml` join test), not asserted | registry; `K3E_R002/R003` |
| E0 cite-don't-fork repair (E0 missed these citations) | **SATISFIED.** `DNR:KILL-FUSED-COMPOSITE` cited in the registry kills; #5901 (Capital Structure Intelligence V2) cited on `capital_structure_supply`; #5872 (AD-1 options intelligence) cited on `options_state` | registry notes |
| MO K3 rider — seven legs independently visible; no composite hides them; aggregates print denominator + dominant degradation | **SATISFIED.** Seven required projection objects; no composite field exists on the wire; `denominator` + `dominant_degradation` required | schema; `K3E_R014/R015` |
| MO cross-program invariants (denominator; durable failure states; idempotent version-bound objects; reconciliation; probability receipts; partial ≠ complete) | **SATISFIED** for the surface this contract owns: typed refusal/exclusion states persist on the wire; `compilation_state=complete` is illegal with any adverse count (`K3E_R005`); composition is deterministic and content-hashed (`K3E_R020`); no probability field exists in v1 (nothing to receipt — adding one requires v2 plus derivation/calibration receipts) | schema; determinism test |
| Instrument verdicts are not market verdicts (operator 2026-08-09) | **SATISFIED.** `instrument_state` slots may be referenced only from `failed_or_unavailable_gates`; the gold/real-rate dual-read golden fixes the shape (chain FAILED in gates; tape-side observed slots lead `market_reflection`) | `golden_dual_read`; `K3E_R011` |
| 13F / ownership laws (45d; WA-R2/NEXTL-U13 never a positive input) | **SATISFIED.** `known_at = accepted_at` inclusion law (`K3E_R007`); registry note pins crowding-hazard-only; 13F is additionally a cross-owner join (55% of positions unmapped) so an unbridged subject types it `identity_unresolved` | `hostile_lookahead`; `hostile_identity_launder` |
| Prospective expectation accrual (SRC-A1) | **SATISFIED as one OPTIONAL evidence family.** `optional_family: true`; goldens prove vectors are valid with and without it — it is never a prerequisite | `golden_optional_expectation` |
| Epistemics: display-tier ships freely; gauntlet is a promotion gate | **PRESERVED.** Everything here is display/research tier with zero authority; any promotion of any slot family to rank/gate/size runs through K5 / Eval OS by its own commission | registry `candidate_new_family` routing |
| **Sol item 1 — decision-time origin must be authenticated, not trusted from a string** | **SATISFIED.** `caller_named_pit_object` and the free-string `t0_source_object` are deleted from the wire (unrepresentable, not merely discouraged). Every t0 now carries an immutable owner-backed `t0_evidence_ref` in K1 EvidenceRef shape; `K3E_R021` checks it against the registry `t0_sources` pins (owner store, minting clock class, mandatory digest for the generic source, native-identity key grammar) and fails closed on a `live` t0 whose object was minted past that source's lag budget | `t0_sources` registry section; `K3E_R021`; `hostile_retrospective_t0` + 10 programmatic S-1 proofs |
| **Sol item 2 — denominator integrity: public validation must recompute EVERY mandatory denominator** | **SATISFIED.** All five (`$.denominator`, observed, inferred, `market_reflection`, `failed_or_unavailable_gates`) are recomputed by `validate_vector` under frozen included/excluded semantics that the composer shares, so a composed vector can never disagree with the recomputation judging it. **Modeled market-reflection evidence counts as INCLUDED** — it is not silently excluded for not being observed — and gate entries count `failed`/`unavailable` as included with `not_evaluated` excluded | `K3E_R015`; `hostile_denominator_tamper`; the five-way independent tamper sweep |
| **Sol item A (2026-08-26) — the generic t0 path may not claim operational PIT** | **SATISFIED.** `owner_pit_reference` is an accountability receipt, not a validation-time verification, so the registry restricts it to `lawful_t0_modes: ["retrospective_research"]` and `K3E_R021` fails a generic+`live` vector closed. Its `max_recording_lag_days` is `null` by construction — the budget is consulted only in `live` — which is a second, independent fence: re-opening `live` by widening the mode list alone still fails closed on the missing budget. The four registry-pinned sources keep `live` because validation actually checks their `owner_store` and clock class | registry `lawful_t0_modes`; `hostile_generic_live_t0` (`K3E_R021`); 6 programmatic A-item proofs |
| **Sol item 3 — Entry Availability ownership: admission ≠ actionability** | **SATISFIED.** The legs are re-cut to `entry_signal` (reads ONLY `prophet_entry_signal` = `engine.entry_signal.assess` → `prophet.board_read/v1` `entry_signal.status`, registry `entry_role: actionability`) and `radar_probe_coverage` (typed `probe_coverage_state_not_trade_entry` on the wire). `prophet_board_lane` (lane / buyable / eligible) is re-classed `entry_role: admission_context`, owns **no** leg, and may not be referenced from any leg at all. When the actionability surface is unavailable the leg stays explicitly `missing`/`unknown` — never inferred from admission | schema `verdict_class` consts; registry `entry_role`; `K3E_R011`; `hostile_admission_as_entry` + 8 programmatic S-3 proofs |

## 6. Family-mapping receipt (executable)

The governed-family law is `research/prophet_fusion/families.yml`
(`prophet_fusion.families.v1` — "one column, one family"; where prose and that file
disagree, that file governs). K3-E **re-homes nothing**: a governed slot binds to an
existing (family, member) pair that must exist there verbatim, and the test suite
asserts the join on every run. `engine/us_prophet_fusion.py`'s `FORBIDDEN_INPUTS`
(composite/score columns) are fenced from every slot.

| Construct | Binding |
|---|---|
| `residual_alpha_momentum` | governed — `F2_MOMENTUM_EXTENSION` / `residual_alpha` |
| `estimate_revisions` | governed — `F4_CATALYST_EVENT` / `analyst_revisions` |
| `eightk_recency` | governed — `F4_CATALYST_EVENT` / `eightk_recency` |
| `sue_surprise` | governed — `F4_CATALYST_EVENT` / `sue_surprise` |
| `short_interest` | governed — `F5_FLOW_POSITIONING` / `short_interest` |
| `insider_activity` | governed — `F5_FLOW_POSITIONING` / `insider_panel` |
| `smart_money_13f` | governed — `F5_FLOW_POSITIONING` / `smart_money_13f` |
| `options_state` | governed — `F5_FLOW_POSITIONING` / `options_state` |
| `turnover_liquidity` | governed — `F5_FLOW_POSITIONING` / `turnover_liquidity` |
| `theme_membership` | governed — `F3_THEME_STRUCTURE` / `theme_membership` |
| `attention_views` | governed — `F8_ATTENTION_CROWDING` / `attention` |
| `forensics_scalars` | governed — `F7_QUALITY_FUNDAMENTAL` / `forensics_scalars` |
| `capital_structure_supply` | governed — `F7_QUALITY_FUNDAMENTAL` / `capital_structure` |
| `disloc.<term>.<window>` group | research_only (windowed attribution has NO producer today — owner gap §8; per-term law binding) |
| `drl_resid_shock`, `drl_filing_coverage`, `drl_event_state` | research_only (DRL display ledger; all-false authority) |
| `macro_chain_state` | research_only (instrument state; dual-read law) |
| `prospective_expectation_src_a1` | research_only, `optional_family` |
| `coverage_count` | research_only (NEGLECTED is not yet a data state) |
| `prophet_entry_signal` | research_only owner read — `entry_role: actionability`; THE canonical live actionability surface, sole lawful feed of the `entry_availability.entry_signal` leg |
| `radar_probe_admission` | research_only owner read — `entry_role: probe_coverage`; probe/coverage state only, never a trade-entry verdict |
| `prophet_board_lane` | research_only owner read — `entry_role: admission_context`; admission (lane / buyable / eligible), owns **no** leg and is referenceable from none |
| `etf_flow_shares_outstanding` | **candidate_new_family → K5 / Eval OS gauntlet**; no authority here |

## 7. Mutation / adversarial proof matrix

Every commissioned mutation class dies by a named rule with a fixture or programmatic
mutation asserting the exact code:

| Commissioned kill | Rule | Proof |
|---|---|---|
| Hidden scalar reconstruction | `K3E_R004` (+R001) | `hostile_composite_scalar`, `hostile_disloc_reconstitution` |
| Missing → neutral | `K3E_R005` | `hostile_missing_neutral` + zero-substitution mutation |
| Owner clock collapse | `K3E_R006` | `hostile_clock_collapse` |
| One column → multiple governed families | `K3E_R002/R003` | `hostile_double_family` + registry hygiene + families.yml join |
| Residual re-derivation | `K3E_R008` | `hostile_residual_rederived` |
| Statistical evidence as economic cause | `K3E_R009` | `hostile_cause_from_epsilon` |
| Unvalidated cross-owner identity | `K3E_R010` | `hostile_identity_launder` |
| Prophet/Radar authority leakage | `K3E_R011` + closed consumer enum + all-false envelope | `hostile_authority_leak` + consumer mutation |
| Board admission passed off as an entry verdict | `K3E_R011` | `hostile_admission_as_entry` |
| Retrospective t0 claiming operational PIT | `K3E_R021` | `hostile_retrospective_t0` |
| Unverifiable generic t0 claiming operational PIT | `K3E_R021` | `hostile_generic_live_t0` |
| Denominator tampering (either mandatory aggregate) | `K3E_R015` | `hostile_denominator_tamper` |
| Outcome audition / look-ahead | `K3E_R007` + no outcome field on the closed wire | `hostile_lookahead` + I7 structural exclusion |
| LLM origination | schema (no LLM provenance member exists) | `hostile_llm_provenance` |

Flow-label honesty (`K3E_R012`), impairment-axis claims (`K3E_R017`), receipt
consistency (`K3E_R015`), and content-hash integrity (`K3E_R020`) are additionally
killed as listed in the test suite.

### 7.1 Independent red-team disposition (opus adversarial review, 2026-08-25)

An independent opus red-team attacked the first candidate across six lines
(laundering holes, false packet claims, vocabulary drift, fixture honesty,
validator soundness, registry correctness) and returned 3 BLOCKERs, 6 MAJORs,
5 MINORs. Every finding was adjudicated and the artifact repaired before this
packet was finalized:

| Finding | Repair |
|---|---|
| B1 — `value_or_null` untyped: a fused score/weights/rank/`buy` payload validated clean | `value_or_null` is now typed (scalar or flat one-level object of scalar leaves, key grammar + 16-key cap) and `K3E_R004` fences forbidden payload keys (score/weight/rank/buy/size/composite/entry/…); dislocation terms must be plain numbers; free-text fields are length-capped and display-only by consumer law |
| B2 — look-ahead comparison truncated to day grain: an intraday `known_at` 14.5h after t0 was included | full-instant comparison when both grains are datetime; mixed-grain same-day stays ambiguous-excluded; new intraday mutation kill |
| B3 — reconstruction detector defeated by float noise / string / dict values | relative tolerance; number-typing kills string/dict evasion structurally; near-sum kill added |
| M4 — `unsupported`/`unknown` omitted from dominant-degradation severity (adverse slots could read "none") | strict severity order now includes both; false code comment removed; mutation kill added |
| M5 — `entry_availability` could claim `read` over a missing owner slot; gates leg unvalidated | leg state must mirror the owner slot's state; a gate owned by this library/"computed" fires `K3E_R011` |
| M6 — Prophet board admission leaked into the `inferred` evidence leg | `entry_owner_read` registry law: entry-owner slots live ONLY in `entry_availability`; presence in observed/inferred/market_reflection refs is refused |
| M7 — `modeled` laundered to `observed` in market-reflection legs | `modeled` survives projection (leg enum + mapping fixed); goldens regenerated |
| M8 — `short_interest.known_at` pinned to the collector's capture `asof` instead of the estate's canonical `knowable_date` (8th NYSE session after settlement, `lib/finra_knowable.py`) | registry re-pinned to `knowable_date`/knowable with the PIT-law citation; goldens updated — the commissioned owner-clock-collapse class had landed in our own registry and is now the exemplar of why the kill exists |
| M9 — placeholder receipts | filled (§10) |
| MINORs | `compilation_state` re-cited to K1's `recipe_compilation_receipt.v1` vocabulary (materialized in `security_state.v1`) with an equality test; `grain`'s single additive `unknown` member declared and drift-pinned; hostile docstring honesty fixed; `deterministic_join` documented as reserved-unused in v1; `drl_event_state.known_at` re-classed `belief_or_build` (session-derived evaluation clock); the IMXI receipt citation had already been repaired pre-review |

### 7.2 Sol REQUEST_CHANGES disposition (2026-08-25, held head `ac2be650a360`)

Sol accepted the architecture in principle and returned three required repairs.
All three were repaired **on this same carrier** (PR #6417) — no redesign, no
second carrier:

| Sol item | What was wrong | Repair + named mutation receipts |
|---|---|---|
| **1. Authenticate decision-time origin** | `caller_named_pit_object` + a free-string `t0_source_object` let a caller assert t0 with an unverifiable label — the decision clock was trusted, not proven | Both deleted from the wire. `t0_evidence_ref` (K1 `reference.v1` EvidenceRef shape) + `t0_mode` (K1 `replay.mode`) are now required; the registry `t0_sources` section pins owner store, minting clock class, digest requirement, and a per-source recording-lag budget; `K3E_R021` enforces all of it fail-closed. Receipts: `hostile_retrospective_t0` (`K3E_R021`), `test_s1_retired_free_string_t0_object_is_no_longer_expressible`, `test_s1_t0_evidence_ref_reuses_k1_evidence_ref_field_semantics`, `test_s1_mutation_retrospective_t0_claiming_live_fires_r021`, `test_s1_same_lag_is_lawful_once_declared_retrospective`, `test_s1_mutation_wrong_owner_store_for_named_t0_source_fires_r021`, `test_s1_mutation_generic_owner_reference_without_digest_fires_r021`, `test_s1_mutation_unpinned_t0_source_fires_r021`, `test_s1_native_identity_key_grammar_is_enforced_semantically` (the structural checker implements no `propertyNames`, so without this the schema keyword would be decorative), `test_s1_missing_t0_evidence_ref_fails_closed`, `test_s1_every_schema_t0_source_has_a_registry_pin` |
| **2. Close denominator integrity** | Only the slot-derived denominators were recomputed; `market_reflection` and `failed_or_unavailable_gates` were taken from the wire on trust, and modeled evidence risked being counted as excluded | Both are now recomputed by public validation under frozen, documented inclusion semantics that the composer shares. Modeled market-reflection legs are **included**; gate `not_evaluated` is excluded while `failed`/`unavailable` are included. Receipts: `hostile_denominator_tamper` (`K3E_R015`), `test_s2_public_validation_recomputes_every_mandatory_denominator` (independent five-way tamper sweep), `test_s2_modeled_market_reflection_evidence_counts_as_included`, `test_s2_dropping_a_modeled_leg_from_the_numerator_fires_r015`, `test_s2_gate_denominator_semantics_are_frozen_and_recomputed` |
| **3. Correct Entry Availability ownership** | The leg read `prophet_board_lane` (lane / buyable / eligible) — board ADMISSION — as if it were an entry verdict, and Radar probe admission was not typed as coverage | Legs re-cut to `entry_signal` / `radar_probe_coverage` with `verdict_class` consts on the wire. New registry construct `prophet_entry_signal` (`entry_role: actionability`) reads the canonical live surface `engine.entry_signal.assess` → `prophet.board_read/v1` `entry_signal.status`; `prophet_board_lane` becomes `admission_context`, owning no leg and referenceable from none; unavailable ⇒ explicitly `missing`/`unknown`. Receipts: `hostile_admission_as_entry` (`K3E_R011`), `test_s3_registry_binds_exactly_one_actionability_owner`, `test_s3_actionability_owner_names_the_canonical_live_surface`, `test_s3_mutation_board_admission_cannot_satisfy_the_entry_leg_fires_r011`, `test_s3_admission_context_may_not_be_referenced_from_any_leg`, `test_s3_entry_leg_stays_explicitly_unknown_when_owner_is_unavailable`, `test_s3_radar_leg_is_typed_probe_coverage_never_a_trade_verdict`, `test_s3_dangling_refs_are_caught_in_the_recut_entry_legs`, `test_s3_authority_envelope_still_denies_entry_after_the_recut` |

One defect was found by this repair wave itself and is disclosed rather than
quietly fixed: the leg-membership pass (`K3E_R014`) still addressed the retired
leg keys after the re-cut, which would have left **both** entry legs unpoliced
for dangling refs while every other test passed. It is fixed and pinned by
`test_s3_dangling_refs_are_caught_in_the_recut_entry_legs`.

### 7.3 SECOND red-team wave on the Sol repair (2026-08-25) — 2 BLOCKERs, 6 MAJORs

The first repair was then attacked by an independent opus red-team, which
returned **STATUS: FAIL** with 2 BLOCKERs and 6 MAJORs. Its central judgment was
that **items 2 and 3 were satisfied in vocabulary but not in substance** — the
repair had added the right words and left the enforcement reachable around.
Every finding was independently reproduced by the commissioning session before
being repaired (no finding was accepted on the reviewer's word), and every
exploit was re-run against the fix:

| # | Finding | Why it mattered | Repair + proof |
|---|---|---|---|
| **B1** | A slot NAMED `prophet_entry_signal` could carry board admission's payload **and** board admission's own `owner_ref`, then satisfy the Entry Availability leg — zero findings. The two constructs share `family_binding`, `derivation`, and clock classes, so only the name differed, and no check read the registry's `owner`/`artifact`/`reader` pins. **Sol item 3 was defeated by a costume.** | The `hostile_admission_as_entry` fixture only caught the naive form (`slot_refs: ["prophet_board_lane"]`) | Every registry-known slot's `owner_ref` (owner/artifact/reader) **and** `object_class` must now equal its registry pin (`K3E_R008`). `test_rt2_blocker1_admission_payload_wearing_the_actionability_name_fires_r008` |
| **B2** | The `market_reflection` leg SET was attacker-controlled, so recomputing its denominator proved nothing. Three forgeries all recomputed "consistently" and validated clean: ref-less legs declaring themselves `observed`; deleting the five adverse legs so 2/7 coverage reported as **2/2 = 100 % market reflection**; duplicating the one observed leg. **Sol item 2 was defeated.** | The old binding was gated on `if len(refs) != 1: continue`, so any leg without exactly one ref was unchecked | The seven I1–I7 legs must appear **exactly once, in order**, and a leg with no resolvable backing slot may only be `missing`/`unknown` — never `observed`/`modeled`/`partial` (`K3E_R015`). Three parametrized proofs in `test_rt2_blocker2_market_reflection_leg_set_cannot_be_forged` |
| **M3** | `owner_pit_reference` pins `owner_store: null` and `recorded_clock_class: null`, so the registry's claim that "an arbitrary caller-named identifier is no longer expressible" was **false for the source three of four goldens use** | An overclaim to Sol about the strength of item 1 | Claim corrected in the registry with an explicit HONEST BOUNDARY note: this source is an **accountability receipt, not a verification** — the digest is falsifiable by anyone who fetches the object, but nothing here proves the object exists. Verifying it needs an owner-read seam this contract deliberately does not have |
| **M4** | `generated_at` was unauthenticated and the composer defaulted it to t0, so a vector could claim it was generated **before the evidence it cites existed** — the shipped FPI golden did exactly that (generated `2026-08-10`, citing an object minted `2026-08-18`) | A self-inconsistent shipped artifact | `K3E_R021` now enforces `generated_at >= recorded_clock`; the composer defaults to the later of the two. `test_rt2_major4_*` (mutation + all-goldens invariant) |
| **M5** | The anti-hindsight lag was **day-truncated** (`.date()`), re-opening the day-grain blindness the first red-team closed for slot clocks: a ~1.9999-day lag measured as exactly 1 day and slipped under a 1-day budget | The fence Sol's item 1 exists to create | Both sides compared as instants. `test_rt2_major5_lag_is_measured_as_an_instant_not_a_truncated_day` |
| **M6** | `validate_vector` **raised** `TypeError` on a non-string clock value, violating its documented never-raises contract — a fail-closed caller got an exception instead of a finding | Fail-closed callers cannot fail closed on a crash | Non-string clocks return `None` and surface a finding. `test_rt2_major6_validate_vector_never_raises_on_hostile_clock` |
| **M7** | No check compared a slot's `object_class` to its registry pin, so relabeling `instrument_state` → `derived_view` walked a slot past the dual-read fence | Instrument verdicts could re-enter the evidence legs | Covered by the same B1 registry-pin enforcement. `test_rt2_major7_object_class_relabel_to_escape_a_fence_fires_r008` |
| **M8** | The `entry_role` fence covered observed/inferred/market_reflection only, so entry-owner reads laundered into `strongest_unresolved_fact` — a leg the **composer** already refused to put them in (validator/composer drift) | Entry state re-entering the evidence surface | Fence extended to `strongest_unresolved_fact`; validator and composer now agree. `test_rt2_major8_*` (parametrized over all three entry roles) |
| **m9** | §7 cited "I7 structural exclusion" as a look-ahead proof, but the I7 leg could simply be **deleted** from the wire | A false claim in this packet | Closed by the B2 fixed-leg-set rule. `test_rt2_minor9_deleting_the_i7_leg_is_refused` |
| **m10** | Anchored patterns used `re.search`, and Python's `$` matches before a trailing newline (unlike ECMA-262), so `"IMXI\n"` satisfied K1's explicitly newline-free `^[^\r\n]+$` | K1 shape reuse was weaker than claimed | Anchored patterns now match end-to-end. `test_rt2_minor10_anchored_patterns_reject_a_trailing_newline` |
| **m11** | Two `K3E_R021` pins failed **open** on registry drift: a missing lag budget disabled the retrospective fence, a missing `digest_required` dropped the digest | A fail-closed rule that fails open | Both default to the strict reading. `test_rt2_minor11_registry_pins_fail_closed_*` |
| **m12** | The self-named-gate fence matched only two spellings, so `"self"`, `"internal"`, `"this rule"` passed as canonical gate owners | Authority leak via prose | Fence broadened. `test_rt2_minor12_self_named_gate_owners_are_refused` |
| **n14** | `assert "radar" not in entry` was **vacuous** — the recut key is `radar_probe_coverage`, so it could never fail | A test that could not detect the regression it named | Replaced with an exact key-set assertion |

Suite: **111 passed** (re-run on the current head; the count was 100 when this
wave concluded). Two reviewer NO-FINDING areas are recorded as verified
rather than assumed: fixture honesty (all 21 fixtures match `manifest.json` on
`sha256` and `bytes`; both real digests independently confirmed with `shasum`;
the one illustrative digest is disclosed, not passed off as real) and the
completeness of the mandatory-denominator inventory.

**Reviewer gaps carried forward, not silently closed:** the second
`propertyNames` site (`value_or_null`, partially covered by the payload-key
fence) was not probed; whether `prophet.board_read/v1` `entry_signal.status` is
the *correct* canonical actionability surface is an owner question the reviewer
could not settle and this session asserts only from the two string pins in
`engine/prophet_board_read.py`; and K1 EvidenceRef fields beyond the three
compared field-for-field were not audited for load-bearing omissions.

### 7.4 Sol REQUEST_CHANGES disposition (2026-08-26, held head `2d9b72c61325`)

Sol ruled **§§7.2–7.3 PASS for items 2 and 3** (no redesign) and returned two
remaining blockers, both repaired on this same carrier:

| Sol item | What was wrong | Repair + named receipts |
|---|---|---|
| **A. Generic t0 assurance** | §7.3 M3 corrected the registry's overclaim about `owner_pit_reference` by DISCLOSING that it is an accountability receipt rather than a verification — but left it free to claim `t0_mode: "live"`, i.e. operational point-in-time. Sol's point is that a disclosure is not a constraint: the store, the minting clock class and the bytes behind the digest are all caller-declared for this source, so a live claim there is the caller vouching for the caller. **Two shipped goldens were making exactly that claim** (`golden_dual_read` on a zero-lag committed case study; `golden_optional_expectation` on an uncommitted store with an illustrative digest), and `golden_dual_read` carried a comment asserting the object "provably existed at t0" — which validation cannot know | The boundary is now enforced, not narrated. Registry gains `lawful_t0_modes` per source; `owner_pit_reference` is `["retrospective_research"]` and `K3E_R021` fails a generic+live vector closed. Its `max_recording_lag_days` is `null` **by construction** (the budget is consulted only in `live`), which is a second independent fence — widening the mode list alone still fails closed on the missing budget, so re-opening `live` requires deliberately minting one. Both goldens now declare `retrospective_research`. Receipts: `hostile_generic_live_t0` (fires exactly `K3E_R021`), `test_a1_generic_source_may_not_claim_live_t0`, `test_a1_the_defect_is_the_claim_not_the_lag` (the fixture has ZERO recording lag, so it clears every budget in the registry — proving the kill is the assurance claim and not the lag law renamed), `test_a2_registry_restricts_the_generic_source_and_keeps_the_pinned_four_live_capable`, `test_a2_pinned_source_still_validates_live` (guards against over-correcting), `test_a3_a_missing_lawful_modes_pin_denies_live_rather_than_granting_it`, `test_a3_reopening_live_on_the_generic_source_needs_more_than_one_list_edit`, `test_a4_no_durable_artifact_calls_the_generic_path_fully_authenticated` |
| **B. Receipt truth** | This packet and the handoff claimed contract-delta `0 introduced, 0 inherited`. The exact hosted result on the held head was **`0 introduced, 4 inherited`** — the "0 inherited" half was never true, and stating it erased four real main-side findings from the record | Corrected in §10 below, in the DEC, and in the handoff, with the four named and attributed to their owning lane. They are **not** healed here (§10) |

**Scope note.** Item A restricts an assurance CLAIM; it adds no owner I/O, no
producer, and no second truth plane. The generic path still cannot be verified
at validation time — that remains the named gap in §8.8, and this repair is
precisely the decision not to let an unverifiable path claim otherwise.

**One judgment call, disclosed rather than smuggled.** Auditing for item A's
reconciliation leg surfaced a *sibling* overclaim of the same class, about the
four pinned sources rather than the generic one: the schema's `native_digest`
description said their "owner_store/clock pins **authenticate the pointer**."
They do not. Those pins constrain what a caller may DECLARE — validation compares
the declared store and clock class against the registry — but nothing proves the
referenced object exists, because no source on this wire is checked by reading
the owner's bytes. The wording is corrected to say exactly that. This is a
description-only change with **zero behavior change**, and the four pinned
sources keep `live` (pinned by `test_a2_pinned_source_still_validates_live`,
which exists to stop an over-correction). Flagged here because "preserve
everything else" could reasonably be read to exclude it — trivially reversible if
you consider it out of scope, but leaving a claim I now believe is false, in the
same file, in the same round where you struck its twin, seemed the worse error.

**Two proofs run rather than assumed** (the wave-2 lesson that vocabulary is not
substance): the 17 hostiles were re-swept directly through `validate_vector`
outside the suite's own assertions, and the new guard was checked by
*reintroducing the shipped defect* — flipping `golden_dual_read` back to
`t0_mode: "live"` fails 3 tests, so the guard detects the thing it is named for
rather than merely passing.

## 8. Remaining owner gaps (named, not papered over)

1. **Windowed dislocation attribution has no producer.** The 5-layer per-window
   pack (E0 census #6 "NOT ASSEMBLED") is contract-typed here but unowned; slots
   carry typed missingness until an owner wave is separately commissioned.
2. **The impairment axis is unowned** (restated §5). This contract types the
   vacancy; it does not fill it.
3. **Factor residual is structurally absent** (`factor__absent` 100% on the
   2026-08-17 stamp): `disloc.ret_fac.*` stays typed-missing; no parallel factor
   residual may be invented (E0 Q8).
4. **Prophet entry state per name — the OWNER is now named; COVERAGE remains the
   gap.** Sol's item-3 ruling closed the ownership half of the former Track-C
   question (Q9): the canonical actionability surface is
   `engine.entry_signal.assess` projected as `prophet.board_read/v1`
   `entry_signal.status`, registered here as `prophet_entry_signal`. What remains
   open is coverage, not ownership — that surface exists only for subjects the
   stock library / Prophet plans actually cover, and the board's own
   `prophet_entry`/`prophet_signal` columns are empty. For an uncovered subject the
   leg types `missing`/`unknown` and **never** infers a verdict from board
   admission. Measuring that coverage is a separate commission; no vector claims it.
5. **Radar's live spool has zero envelopes ever written** (armed-not-producing as
   of 2026-08-20): `radar_probe_admission` is typed-missing in current-state
   vectors until the lane produces.
6. **NEGLECTED is not a data state** before the 2026-06 revisions/attention births
   (E0 Q6); lifecycle staging stays outside this wire.
7. **No licensed consensus history before 2026-06-16**; `estimate_revisions` is
   typed `not_available_for_date` there, never backfilled.
8. **The generic t0 path cannot be verified at validation time, and is now
   capped rather than trusted.** `owner_pit_reference` declares its own
   `owner_store`, its own minting clock class, and a digest over bytes this
   contract never reads — it holds no owner imports and no I/O by design. So it
   is an accountability receipt (a falsifiable commitment anyone who fetches the
   object can check) and not a verification, and per Sol item A it may claim only
   `t0_mode: "retrospective_research"`. Closing the gap for real means either
   pinning more owner stores in `t0_sources` or giving the validator an
   owner-read seam; the latter is a producer decision outside this contract's
   authority. Until then, **no artifact here describes the generic path as fully
   authenticated**, and a t0 that must be checkable belongs on one of the four
   pinned sources.

## 9. The exact capability this contract unlocks

Market OS `security_state.v1` today ships `legs.opportunity_context` with
`market_incorporation.ref = null / NOT_COVERED` and `dislocation.ref = null /
NOT_COVERED`, and K1 recipe outputs already flow into its `evidence` leg. This
freeze supplies the **one canonical typed object those null refs can later point
to** — and the vocabulary a K5 OpportunityCase composes — so a consumer can answer
"what does the estate actually know about this opportunity, on which clocks, with
which gaps" without any fused score. Wiring any consumer (B-wave on
`security_state.v1`, K5 OpportunityCase) remains a separately authorized commission;
this packet arms nothing.

## 10. Validation commands and receipts

```bash
python3 -m json.tool contracts/opportunity_evidence/vector.v1.schema.json
python3 -m json.tool contracts/opportunity_evidence/slot_registry.v1.json
python3 -m compileall -q lib/opportunity_evidence.py tests/test_opportunity_evidence_vector_contract.py
python3 -m pytest -q tests/test_opportunity_evidence_vector_contract.py
python3 scripts/check_contract_delta.py --base origin/main
python3 scripts/agentos.py validate
```

Receipts (exact, this candidate):

- Contract suite: **111 passed** (post-Sol-2026-08-26 candidate; includes all ten
  commissioned mutation kills, the 19 red-team repair proofs, the 22 Sol
  REQUEST_CHANGES proofs of §7.2, the 16 second-red-team regression proofs of
  §7.3, the 8 item-A assurance-ceiling proof functions of §7.4 (11 cases with parametrization), the families.yml join,
  both K1 enum-equality pins, the K1 EvidenceRef shape-equality pin, the
  security_state compilation-state pin, the grain-delta pin, determinism
  round-trips, and the no-store scans)
- Fixture packet: 4 goldens + **17** hostiles + manifest, every hostile
  independently re-validated to fire its commissioned code and every golden to
  validate clean (verified by direct `validate_vector` sweep, not only via the
  suite's own assertions); all 21 fixtures match `manifest.json` on `sha256` and
  `bytes`
- **Contract-delta — corrected on Sol REQUEST_CHANGES 2026-08-26 item B.** This
  section previously claimed `0 introduced, 0 inherited`. The second half was
  never true. The exact HOSTED result on held head `2d9b72c6132518` was
  **`0 introduced, 4 inherited`** (base `fe84261a206e`), gate **PASS** — the gate
  is differential and keys only on the introduced count, which is precisely what
  made the wrong half easy to round off. The four inherited findings are
  **main-side, separate-lane debt that this carrier neither caused nor healed**:
  jobs `conviction-profile` and `unrun-picks-boards` each missing
  `engine/company_intelligence/qa_exchange.py` and
  `engine/company_intelligence/qa_reconstruction.py` from their declared `paths:`
  (2 jobs × 2 files). The gate names this disposition itself — "already uncovered
  on this PR's base — pre-existing, not introduced by this PR; heal separately" —
  and on a held PR, widening another job's `paths:` from this carrier would be
  both scope creep and a hold violation. **Main has since closed all four on its
  own** in `ad36de0f6aa3` (PR #6451, merged 2026-08-26T07:26:39Z) — separate lane,
  exactly as the gate directed.
  - Consequently the repaired branch, refreshed onto `origin/main` so the local
    gate tests what hosted CI tests, measures **`0 introduced, 0 inherited`
    (base `2cb581c6fa69`)**. That is the same figure this section wrongly claimed
    before, and it is recorded here only with the reason it is now true: the
    branch contains main's heal. Nothing in K3-E changed, no finding was
    suppressed, and no `paths:` were widened from this carrier.
  - **Both numbers are receipts and neither replaces the other**, because a
    contract-delta result is a fact about one (head, base) pair, not about a PR.
    A receipt that omits its head and base cannot be checked, and a receipt that
    reports only the introduced count — the half that decides the gate — is a
    summary. The authoritative hosted figure for the final head is in PR #6417's
    conversation with its run id
- Agent OS validate: 0 errors (710 records; inherited repository warnings only)
- Registry ↔ families.yml join: asserted inside the suite on every run
- Carrier: PR #6417 (DRAFT / HOLD-FOR-SOL from its first revision)
- Exact held head + concluded hosted CI/fences run ids: recorded in the PR #6417
  conversation at park time (they cannot live in this committed file without
  moving the head they describe)

## 11. Explicit non-goals (verbatim scope fence)

No physical Opportunity Evidence store; no universal evidence warehouse; no new
identity/event/residual/graph/Prophet/Radar/Entry plane; no composite Opportunity
Score; no rank/size/trade/recommendation; no K3-D implementation; no K5
OpportunityCase; no Market OS UI; no second issuer/product expansion; no model
tuning. This PR merges nothing and starts no dependent wave.

## 12. Exact acceptance request to Sol

> Sol, this is the K3-E re-park answering your REQUEST_CHANGES on held head
> `2d9b72c6132518`, which ruled §§7.2–7.3 PASS for items 2 and 3 and returned two
> remaining blockers. Both are repaired on PR #6417 only — no redesign, no second
> carrier, and items 2 and 3 are untouched apart from the receipt correction.
>
> **Item A (generic t0 assurance):** `owner_pit_reference` is now capped, not just
> annotated. The registry carries `lawful_t0_modes` per source; the generic source
> is `["retrospective_research"]` and `K3E_R021` fails a generic+`live` vector
> closed. Its `max_recording_lag_days` is `null` **by construction** — the budget
> is only ever consulted in `live` — which is a second, independent fence: widening
> the mode list alone still fails closed on the missing budget, so re-opening
> `live` requires deliberately minting one. The commissioned mutation
> `hostile_generic_live_t0` carries a maximally clean reference (known 64-hex
> digest, known minting clock, **zero** recording lag, which clears every budget in
> the registry) and still dies on `K3E_R021` — the kill is the assurance claim, not
> the lag law renamed. Reconciled across schema, registry, freeze §5/§7/§8.8/§10,
> and the DEC: no durable artifact now calls the generic path fully authenticated,
> and a test asserts that. **Two shipped goldens had in fact been claiming
> operational PIT on that path** — `golden_dual_read` and
> `golden_optional_expectation`, the latter over an uncommitted store with an
> illustrative digest — and both now declare `retrospective_research`. This adds no
> owner I/O, no producer, and no second truth plane; the unverifiability itself
> stays a named gap (§8.8).
>
> **Item B (receipt truth):** corrected. The exact hosted result on the held head
> was `0 introduced, **4 inherited**` (base `fe84261a206e`), not `0/0`. The four
> are `conviction-profile` and `unrun-picks-boards` each missing
> `engine/company_intelligence/qa_exchange.py` and `qa_reconstruction.py` from
> their declared `paths:` — **main-side separate-lane debt, not healed here**, per
> the gate's own "heal separately" instruction and the hold. Corrected in freeze
> §10, the DEC, and the handoff, each receipt now naming its head and base.
>
> One thing you should know rather than discover: main has since closed all four
> itself in `ad36de0f6aa3` (PR #6451), so the repaired branch — refreshed onto
> `origin/main` so the local gate tests what hosted CI tests — now measures
> `0 introduced, **0 inherited**` (base `2cb581c6fa69`). That is the same figure
> you just ruled false, and §10 records it only alongside the held-head `0/4` and
> the reason it changed: the branch contains main's heal. Nothing in K3-E changed,
> no finding was suppressed, and no `paths:` were widened from this carrier. I did
> not overwrite the `0/4` receipt with the new one — a contract-delta result is a
> fact about one (head, base) pair, not about a PR, so both are recorded.
>
> **Item 1 (authenticate decision-time origin), as accepted:** `caller_named_pit_object` and the
> free-string `t0_source_object` are deleted from the wire — structurally
> unrepresentable, test-pinned. Every t0 now binds to an immutable owner-backed
> `t0_evidence_ref` reusing K1 `reference.v1` EvidenceRef semantics field-for-field
> (`owner_store`, `native_identity`, `native_digest`) plus a known minting clock,
> authenticated against a new registry `t0_sources` section by `K3E_R021`; a
> hostile retrospective-t0 fixture fails closed, and the same lag is lawful only
> once the vector visibly declares `t0_mode: retrospective_research`.
>
> **Item 2 (denominator integrity):** public validation now recomputes **all five**
> mandatory denominators, including `market_reflection` and
> `failed_or_unavailable_gates`, under frozen included/excluded semantics the
> composer shares. Modeled market-reflection evidence counts as INCLUDED, never
> silently excluded for not being observed; independent tamper mutations cover
> every denominator.
>
> **Item 3 (Entry Availability ownership):** legs re-cut to `entry_signal` and
> `radar_probe_coverage` with `verdict_class` consts on the wire. The entry leg
> reads only the canonical live actionability surface — `engine.entry_signal.assess`
> → `prophet.board_read/v1` `entry_signal.status` — via the new
> `prophet_entry_signal` construct; `prophet_board_lane` (lane / buyable / eligible)
> is re-classed `admission_context`, owns no leg, and may not be referenced from
> any leg; an unavailable owner leaves the leg explicitly `missing`/`unknown`. Radar
> probe availability is typed probe/coverage state, never a trade-entry verdict.
>
> Receipts: **111 passed**; 4 goldens clean and **17** hostiles each firing their
> commissioned code on an independent re-validation sweep (the new
> `hostile_generic_live_t0` fires exactly `K3E_R021`); all 21 fixtures match the
> manifest on `sha256` and `bytes`; Agent OS validate 0 errors; contract-delta as
> corrected under item B above. Schema, registry, validator/composer,
> goldens/hostiles, freeze §5/§7/§8/§10/§12, DEC, WS and handoff are all updated.
> Two things are disclosed rather than quietly fixed: the earlier self-found
> leg-membership defect (§7.2), and the fact that item A's defect was **live in
> two shipped goldens of mine**, not merely latent in the schema — §7.4 records
> that, including the `golden_dual_read` comment which asserted the referenced
> object "provably existed at t0", something validation has no way to know.
> The exact re-parked head and its concluded hosted CI/fences run ids are in PR
> #6417's conversation.
>
> Please rule ACCEPT or return exact amendments. No downstream wave has started:
> this authorizes no producer, no consumer wiring, no store, no K3-D, no K5, no
> Market OS UI, no ranker, gate, or score.

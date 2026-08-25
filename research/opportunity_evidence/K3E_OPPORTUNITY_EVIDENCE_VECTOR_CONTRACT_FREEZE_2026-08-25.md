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
  `opportunity_evidence.vector.v1` wire (subject, decision clock with t0-source
  discipline, typed slots, the seven projection legs, separate economic-cause
  hypothesis object, denominator receipt, dominant degradation, all-false authority,
  deterministic content hash).
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
route** typed owner outputs by frozen rules; it never computes new values),
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
| aggregates | denominator receipt + dominant degradation, inherited from the K1 block law; counts are the only lawful aggregate arithmetic | `K3E_R015`; schema has no other numeric aggregate field |
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
| `prophet_board_lane`, `radar_probe_admission` | research_only owner reads (entry-availability leg; zero-authority projection verbs) |
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
| Outcome audition / look-ahead | `K3E_R007` + no outcome field on the closed wire | `hostile_lookahead` + I7 structural exclusion |
| LLM origination | schema (no LLM provenance member exists) | `hostile_llm_provenance` |

Flow-label honesty (`K3E_R012`), impairment-axis claims (`K3E_R017`), receipt
consistency (`K3E_R015`), and content-hash integrity (`K3E_R020`) are additionally
killed as listed in the test suite.

## 8. Remaining owner gaps (named, not papered over)

1. **Windowed dislocation attribution has no producer.** The 5-layer per-window
   pack (E0 census #6 "NOT ASSEMBLED") is contract-typed here but unowned; slots
   carry typed missingness until an owner wave is separately commissioned.
2. **The impairment axis is unowned** (restated §5). This contract types the
   vacancy; it does not fill it.
3. **Factor residual is structurally absent** (`factor__absent` 100% on the
   2026-08-17 stamp): `disloc.ret_fac.*` stays typed-missing; no parallel factor
   residual may be invented (E0 Q8).
4. **Prophet entry state per name is an unclosed Track-C question** (Q9): the
   board's `prophet_entry`/`prophet_signal` columns are empty while entry state may
   live in `engine/entry_signal` dossiers; the entry-availability leg types this
   `unknown`, never "no entry state".
5. **Radar's live spool has zero envelopes ever written** (armed-not-producing as
   of 2026-08-20): `radar_probe_admission` is typed-missing in current-state
   vectors until the lane produces.
6. **NEGLECTED is not a data state** before the 2026-06 revisions/attention births
   (E0 Q6); lifecycle staging stays outside this wire.
7. **No licensed consensus history before 2026-06-16**; `estimate_revisions` is
   typed `not_available_for_date` there, never backfilled.

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

- Contract suite: {{PYTEST_RECEIPT}}
- Contract-delta vs pinned main: {{CONTRACT_DELTA_RECEIPT}}
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

> Sol, review K3-E Opportunity Evidence Vector v1.0.0 as a contract-only freeze.
> Protected Skillpack was loaded from Mastermind `51f9942733b86e`; Macro was pinned
> at `2c20168df5d9` (your census pin, unmoved); the collision census is CLEAR. The
> contract is a typed view/join over canonical owners — no store, no score, no
> Prophet/Radar consumption, residuals owner-read only, impairment axis explicitly
> unowned, per-term dislocation emission with the reconstitution kill executable,
> ETF-flow states variation-derived, every slot mapped to exactly one governed
> fusion family / research_only / candidate_new_family (families.yml join
> test-enforced), and the seven MO legs independently visible with denominator +
> dominant-degradation receipts. All ten commissioned mutation classes die by named
> rule codes with fixture receipts. The carrier is PR #6417, DRAFT / HOLD-FOR-SOL
> from its first revision; the exact held head and its concluded hosted check run
> ids are pinned in that PR's conversation. Please rule ACCEPT or return exact
> amendments. This packet does not authorize or begin K3-D, K5, any consumer
> wiring, any store, or any promotion.

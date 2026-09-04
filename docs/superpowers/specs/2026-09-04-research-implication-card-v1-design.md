# Research Implication Card v1 — Frozen Design

Date: 2026-09-04
Operation: marketontology-f10-implication-cards-v1-20260904-sol-001
Canonical issue: mastermindx-market-intelligence/macro#6822
Exact carrier: Slack C0BSBM78V1N/1788511463.994279
Source base: feec1fe60c4eb00fb5211636fe389a56974ef3fa

## Outcome

Project already-committed estimator result artifacts into one deterministic, closed, read-only contract. Render the validated card objects inside the existing Measurement page and write the same objects to a JSON projection. The feature is research context only and cannot run studies, edit results, rank opportunities, or grant trading authority.

## Non-goals and protected owners

- Do not change engine/synthetic_control.py or engine/seasonality/event_study.py.
- Do not change any study runner, result artifact, ledger, registry, evaluation owner, signal owner, promotion owner, or deployment route.
- Do not run a new study or recompute estimator statistics.
- Do not create a ResearchStudy Workbench, experiment plane, evaluation plane, signal plane, promotion plane, database, scheduler, queue, notebook, save state, or model-prose layer.
- Do not infer a p-value, confidence interval, standard error, effective sample size, cutoff, donor/control identity, conclusion, ordered effect path, or implication that the owner artifact does not explicitly supply.
- Do not grant forecast, ranking, gating, sizing, execution, or trading authority.

## Data flow

1. A family-specific adapter verifies the immutable digest of each required committed source artifact.
2. The adapter selects one explicitly frozen result identity and performs family-specific shape and semantic checks.
3. The adapter emits one card with schema mastermind.research_implication_card/v1.
4. The shared validator rejects unknown keys, wrong types, inconsistent content identity, invalid quality states, missing typed-null reasons, and any true authority flag.
5. scripts/build_measurement.py consumes only validated cards.
6. The Measurement template receives those same card dictionaries.
7. site/measurementdata/research_implication_cards.json contains the same ordered card list as the research_implications member of site/measurementdata/measurement_data.js.

No generic estimator output is coerced into a cross-family pseudo-statistic. Synthetic-control and event-study parsing stay separate until both produce the closed card contract.

## Closed card contract

Every card has exactly these top-level fields:

- schema: literal mastermind.research_implication_card/v1
- card_id: ric_ followed by a lowercase SHA-256 hex digest
- adapter_version: family adapter version string
- method_family: stable family code
- study_run_id: stable owner study/run identity
- selected_result_id: stable owner result path within the artifact
- question: LocalizedText
- estimand: LocalizedText
- method_revision: immutable revision identifier
- code_identity: non-empty list of SourceArtifact objects for estimator/generator code
- population: typed object describing the owner-defined analysis population
- sample_n: integer or null
- effective_n: integer or null
- cutoff: ISO date or null
- outputs: ordered list of TypedMetric objects
- uncertainty: ordered list of typed uncertainty objects
- diagnostics: ordered list of typed diagnostic objects
- placebos_or_counterexamples: ordered list of typed diagnostic objects
- ordered_effect_path: an owner-supplied ordered path object or null
- evidence_tier: stable owner tier string
- quality: one of COMPLETE, DIAGNOSTIC_ONLY, ARTIFACT_INCOMPLETE, ARTIFACT_MISSING, DIAGNOSTIC_FAILED, or STALE
- limitations: ordered non-empty list of LocalizedText
- exclusions: ordered list of typed exclusion objects
- missingness: ordered list of typed missing-input objects
- null_reasons: ordered list of typed null-reason objects
- source_artifacts: non-empty list of SourceArtifact objects
- authority: the exact five-boolean authority object defined below

LocalizedText has exactly en and zh non-empty strings. SourceArtifact has exactly role, path, sha256, as_of, as_of_reason, and rights. A path is repository-relative, sha256 is a lowercase 64-character digest, as_of is an ISO date or null, and rights is a stable rights/availability code. A null as_of requires a non-empty localized as_of_reason; a dated receipt requires as_of_reason=null.

Typed metrics and diagnostics carry a stable code, LocalizedText label, typed value, explicit unit, and source locator. A null value is allowed only when null_reasons includes a matching field code. Missing is never encoded as zero, false, neutral, or an empty success state.

The authority object has exactly these keys, all literal false:

- forecast_authority
- ranking_authority
- gating_authority
- sizing_authority
- trading_authority

The validator rejects any additional authority key and any true value.

## Deterministic content identity

card_id is ric_ plus SHA-256 over canonical JSON containing exactly:

- adapter_version
- method_family
- study_run_id
- result_artifact_path
- verified_result_artifact_sha256
- selected_result_id

Canonical JSON uses UTF-8, lexicographically sorted keys, no insignificant whitespace, and ensure_ascii=false. Replaying identical bytes and selection produces the same ID. A mutation of the result artifact changes its verified digest and therefore changes the card ID. Digest mismatch against the frozen receipt is a typed adapter failure, never a silently accepted new study result.

Card list ordering is a fixed adapter configuration order, not a score or ranking. No card includes rank, score, recommendation, confidence badge, action, position, or trade fields.

## Frozen real card: synthetic control

- Result artifact: data/experiments/synthetic_control_phase0_results.json
- Expected digest: f759bdd72de5370e597459dc0630bb1f880e8a38be9b8882a1c75f54872af1e2
- Generator: scripts/synthetic_control_phase0.py
- Generator digest: bc6479968fd71bc541fdec6b1a1337a1ded9b51c0eb5cdcd1664961bc6f3ab11
- Estimator: engine/synthetic_control.py
- Estimator digest: 31583485f88ebd6c779787a2c0ea5cec68037669460dbb896ea3b83fd7a49a65
- Report: research/SYNTHETIC_CONTROL_PHASE0.md
- Report digest: a8d2e0023279ca241788b589af55bcedbe07117485cb3918a50d0e395a9ac587
- Frozen selection: sp_pure_adds/sc_nnls/0_5
- Panel cutoff: 2026-07-02
- Run date: 2026-08-06

The card preserves the selected CAR, monthly Newey-West t statistic, placebo mean, placebo standard deviation, empirical placebo p-value, and PC gate outcomes exactly as recorded. It does not synthesize a confidence interval or effective N. Quality is DIAGNOSTIC_FAILED because PC-2 fails. Evidence tier is DIAGNOSTIC. This card cannot be displayed as complete or positive.

## Frozen real card: event study

- Result artifact: data/experiments/hincl2_event_study_results.json
- Expected digest: f415b2c4cf9b12fbc8e4dd9e3a30a51c736c93f4ffbc3f818392b4796ea81139
- Generator: scripts/hincl2_event_study.py
- Generator digest: f3c6b5db4aef6c11c4e8105a163bd20ca750de98b56a16052eacd49fa0f9151d
- Preregistration: research/HINCL2_PREREG.md
- Preregistration digest: cd2dbe01981e7f256f79aadac23a2952517bc71810121c05c9517ca324a5ce06
- Report: reports/hincl2-phase0.md
- Report digest: e7391bcabb1a81856ccf3309f611c37c8a7ecc8292cda7a602051bfabfcdfa99
- Frozen selection: announce/h20
- Panel cutoff: 2026-07-03
- Roster hash: b0816afacd9537fac58c193f511ec919bccda4fc58a5921bd1096221fa35b148
- HSI hash: 184cbdcf2437c9d8de172535cd87515b020708c9c441406391faa4aa895a1e45

The card preserves the Stock Connect inclusion announce-anchor +20-day result, event N, independent episode K, HAC result, the three owner interval quantiles, DSR, BH-FDR, panel coverage, exclusions, and the owner-provided ordered event curve. sample_n is the recorded event count. effective_n is the recorded episode_k, because this artifact explicitly names the distinct-episode count. The ordered path is permitted only because the artifact supplies ordered horizons. Its closed object also carries the owner's EXPLORATORY_NON_GATED status, the selected horizon, localized sample basis and comparison note, and a localized accessible name. The chart must distinguish the event-weighted full-window curve from the episode-clustered headline rather than inviting a same-estimator comparison.

Quality is ARTIFACT_INCOMPLETE. The generator depended on a gitignored absolute hk_stocks_ext input whose immutable digest and rights receipt are absent. Outputs remain visible, while completion and decision implication are refused. Language stays descriptive and does not call the observation a causal treatment effect.

## Error and typed-incomplete behavior

- A missing result artifact produces an ARTIFACT_MISSING card only when the adapter can preserve a stable study identity and typed missingness without inventing outputs; otherwise it raises a contract error.
- A digest mismatch raises a contract error containing the path, expected digest, and observed digest.
- A malformed or missing selected result raises a contract error; it never falls back to a neighboring result.
- A missing statistic stays null and carries a null-reason code.
- A missing input receipt appears in missingness and forces ARTIFACT_INCOMPLETE.
- A failed required diagnostic forces DIAGNOSTIC_FAILED even when an output magnitude looks favorable.
- Staleness is not inferred from wall-clock time during the build. STALE is accepted only when supplied by an owner policy or an explicit test fixture.

## Existing Measurement product integration

The section title is Research Implications. Its permanent stance is “Research context — do not use as a trading signal” with equivalent ZH copy. Filters are non-ranking controls for method family, evidence tier, and quality state. Stable card-unique anchors use method_family + study_run_id + selected_result_id so deep links survive a result-artifact digest change without colliding across cards.

The collapsed card shows method, question, cutoff, evidence tier, quality, and a small set of owner metrics. Expandable details expose outputs, uncertainty, diagnostics, exclusions, limitations, missingness, counterexamples/placebos, ordered path when present, and artifact receipts. There is no edit, rerun, save, promote, score, rank, size, or trade affordance.

Dark treatment is a restrained command-center instrument panel: luminance depth, calm separators, and sparing semantic status accents. Light treatment is a research workspace: white sheets on a cool canvas, hairline borders, disciplined shadows, and no dark-theme glow transplant. Both share the same information architecture, semantics, density, ordering, interaction, and data contract.

Required evidence matrix is dark/light × EN/ZH × desktop 1440/mobile 390. Details must work with keyboard and touch. The page must not acquire horizontal scrolling at 390 pixels. The ordered-path visualization must preserve exact owner horizons and values; it is absent when ordered_effect_path is null.

## Verification gates

- Focused adapter tests prove real synthetic-control and event-study cards.
- Hostile tests prove digest mismatch, selected-result drift, missing-vs-zero, sample_n/effective_n separation, failed-diagnostic dominance, all-false authority, closed keys, deterministic replay, and mutation-sensitive identity.
- Builder tests prove the human and machine projections consume the same cards and IDs.
- UI tests prove the non-ranking filters, stable anchors, stance, localization, state treatments, details semantics, exact formatted value projection for every metric, outer-quantile interval rendering, typed receipt-date nulls, and absence of prohibited controls.
- Headless browser evidence proves complete, diagnostic-only, incomplete/missing, failed-diagnostic, and stale fixture states in both themes, both languages, and both viewports.
- Repository design-system, runtime-style-injection, visual-evidence, template/site-sync, and focused pytest checks pass from the exact branch head.

## Delivery boundary

Delivery stops at one exact-head Draft/HOLD pull request. No merge-on-green label, auto-merge, merge, deploy, release, route claim, or production proof is authorized. The hold names Sol as release authority and remains in force until an explicit exact-carrier Sol release condition is satisfied.

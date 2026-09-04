# Research Implication Card v1 Implementation Plan

> Execution owner: the started F10-X1 Codex task. Follow strict test-driven development and stop at an exact-head Draft/HOLD pull request.

Goal: expose real synthetic-control and event-study research outputs as deterministic, non-authoritative implication cards on the existing Measurement page and in a same-contract JSON projection.

Architecture: two strict family adapters verify committed source receipts and map one frozen result each into a single closed card schema. A common validator enforces typed missingness, content identity, quality dominance, and literal false authority. The existing Measurement builder injects the validated objects into both HTML and machine outputs. The existing template renders compact progressive-disclosure cards without creating a new route or study-control surface.

Design authority: docs/superpowers/specs/2026-09-04-research-implication-card-v1-design.md, issue #6822, and the exact Slack contract freeze. Protected estimator, runner, result, ledger, registry, promotion, and deployment owners remain read-only.

## Task 1: Contract tests and strict family adapters

Files:

- Create engine/research_implication_card.py
- Create tests/test_research_implication_card.py
- Create tests/fixtures/research_implication_card files only when a hostile case cannot be expressed with a temporary copy
- Read only data/experiments/synthetic_control_phase0_results.json
- Read only data/experiments/hincl2_event_study_results.json
- Read only the frozen code/report/prereg sources named in the design

Step 1: add the first failing real-artifact tests.

The synthetic test loads the committed artifact through the public adapter and asserts the exact schema, selection, digest-derived ID, cutoff, selected CAR, monthly Newey-West t, placebo statistics, DIAGNOSTIC evidence tier, DIAGNOSTIC_FAILED quality, PC-2 failure, null effective_n with a matching null reason, and all-five false authority object.

The event-study test loads the committed artifact and asserts selection announce/h20, cutoff, event sample_n 282, effective_n 74, exact HAC/CI90/DSR/BH-FDR values, ordered owner curve, ARTIFACT_INCOMPLETE quality, typed missing external input digest/rights receipts, descriptive language, and all-five false authority object.

Step 2: run the focused test and observe RED because engine.research_implication_card does not exist.

Command:

    python3 -m pytest tests/test_research_implication_card.py -q

Expected failure: import error for the new module. Any unrelated collection failure is investigated before production code is written.

Step 3: implement the minimum contract foundation and synthetic adapter.

Add constants for the card schema, envelope schema, quality states, exact authority keys, frozen paths/digests, and adapter versions. Add CardContractError, sha256_file, canonical identity serialization, compute_card_id, validate_card, and adapt_synthetic_control. Read JSON without modifying it. Require exact frozen digests and exact result path. Preserve artifact scalars without rounding in the contract. Represent every unavailable field with null plus a typed reason.

Step 4: run the synthetic test and observe GREEN while the event test remains RED for missing implementation.

Command:

    python3 -m pytest tests/test_research_implication_card.py -q -k synthetic

Step 5: implement the minimum HINCL2 event-study adapter.

Require the exact frozen result, generator, prereg, and report digests. Select only announce/h20. Preserve event N and episode K separately. Copy the ordered event curve in artifact order and reject duplicated or non-monotonic horizons. Preserve missing external input receipt as typed missingness and force ARTIFACT_INCOMPLETE. Do not use causal-treatment phrasing.

Step 6: run both real-card tests and observe GREEN.

Command:

    python3 -m pytest tests/test_research_implication_card.py -q -k 'synthetic or event'

Step 7: add hostile failing tests before broadening the implementation.

Add tests for:

- deterministic replay produces byte-identical cards and IDs;
- a copied result artifact with one mutated byte is rejected by the frozen adapter and produces a different ID through the pure identity function;
- selected-result drift never falls back to another family, method, or horizon;
- missing statistics do not become zero;
- synthetic monthly count is not exposed as effective_n;
- event sample_n and episode effective_n remain distinct;
- failed required diagnostics dominate favorable-looking output magnitude;
- absent external input receipts force ARTIFACT_INCOMPLETE;
- any true authority flag is rejected;
- extra top-level or authority keys are rejected;
- ordered path is rejected when horizons are duplicated, unordered, or not owner supplied;
- forbidden rank, score, recommendation, position, or trade fields are rejected;
- stable ordering is fixed adapter configuration, not metric magnitude.

Step 8: run the hostile tests and confirm RED for each newly introduced mutation.

Command:

    python3 -m pytest tests/test_research_implication_card.py -q

Step 9: add only the validation required to make the hostile tests GREEN.

Keep per-family extraction separate. validate_card must enforce exact keys and types, recompute card_id, verify null reasons, enforce quality constraints, and reject true/unknown authority. build_research_implication_cards returns a deterministic envelope with the cards in configured method order and no wall-clock timestamp.

Step 10: run the entire adapter test file and record the passing count.

Command:

    python3 -m pytest tests/test_research_implication_card.py -q

## Task 2: Measurement builder and same-contract projection

Files:

- Modify scripts/build_measurement.py
- Modify tests/test_build_measurement_hubv2.py or add one narrow builder test file
- Create generated site/measurementdata/research_implication_cards.json
- Modify generated site/measurementdata/measurement_data.js

Step 1: add a failing builder parity test.

The test invokes the smallest supported builder seam in a temporary output directory and asserts:

- research_implications is the validated envelope from Task 1;
- the JSON projection contains the exact same ordered card dictionaries;
- measurement_data.js embeds the exact same ordered card dictionaries;
- the card IDs and scalar values are unchanged across both projections;
- no wall-clock timestamp or data-dependent ranking changes deterministic bytes.

Step 2: run the builder parity test and observe RED because the builder does not emit the card envelope or JSON file.

Command:

    python3 -m pytest tests/test_research_implication_card.py tests/test_build_measurement_hubv2.py -q -k 'implication or research'

Step 3: add the minimal builder integration.

Import build_research_implication_cards from engine.research_implication_card. Build once per builder run. Pass the same Python object to the Jinja context and measurement-data payload. Write the separate JSON projection with deterministic key ordering and UTF-8. Do not reparse, enrich, summarize, rank, or translate values in the builder.

Step 4: regenerate the Measurement outputs with the repository builder.

Command:

    python3 scripts/build_measurement.py

Step 5: rerun builder parity and focused adapter tests until GREEN.

Command:

    python3 -m pytest tests/test_research_implication_card.py tests/test_build_measurement_hubv2.py -q -k 'implication or research'

## Task 3: Measurement card composition and UI semantics

Files owned by the requested visual collaborator after ADAPTER_FREEZE:

- Modify templates/measurement.html.j2
- Modify narrow UI/browser tests
- Modify generated site/measurement.html
- Create or modify visual evidence receipts under the existing repository convention

The adapter owner must first post ADAPTER_FREEZE on the exact Slack carrier with the schema, sample payload path, exact branch/head, and validation command. The visual collaborator must then post its own ACK, watcher disposition, fresh collision result, and separate START. Until that happens, these paths remain unwritten by the collaborator.

Step 1: add failing template/UI tests for the frozen semantics.

The tests render contract fixtures for COMPLETE, DIAGNOSTIC_ONLY, ARTIFACT_INCOMPLETE, ARTIFACT_MISSING, DIAGNOSTIC_FAILED, and STALE. They assert the Research Implications section, permanent non-trading stance, method/tier/state filters, stable card_id anchors, EN/ZH copy, details disclosure, owner metrics, missingness and null-reason display, ordered-path presence only when supplied, and no edit/run/save/promote/rank/score/size/trade controls.

Step 2: run the narrow UI tests and observe RED because the section is absent.

Step 3: implement the minimum semantic DOM and design-system-compliant presentation.

Use the existing Measurement route, token system, language mechanism, and component grammar. Add no new token root and no opaque runtime stylesheet. Keep card ordering fixed. Make filters disclosure/navigation tools rather than ranking controls.

Dark treatment: instrument-calm depth, restrained status accents, low-glare surfaces, and quiet separators.

Light treatment: white research sheets on cool canvas, hairline edges, disciplined shadow, and legible semantic states without copied glow.

At 390 pixels, card summary, filters, receipts, and details reflow without page-level horizontal scrolling or a scroll-trapped help/details region. Details work by keyboard and touch. The event path uses only exact owner horizons and values. Cards without an ordered path render no chart shell.

Step 4: regenerate site/measurement.html and rerun UI tests until GREEN.

Step 5: produce headless browser evidence for the complete proof matrix.

Capture dark/light × EN/ZH × 1440/390 for fixtures covering COMPLETE, DIAGNOSTIC_ONLY, incomplete/missing, DIAGNOSTIC_FAILED, and STALE. Confirm visible state identity, filter operation, detail expansion, focus behavior, and document.scrollWidth <= viewport width at 390. Use headless browser tooling only; do not use native UI control.

## Task 4: Integration and repository gates

Files:

- All files in Tasks 1–3
- Narrow committed visual evidence receipt files required by repository checks

Step 1: inspect the diff for protected-path or generated-artifact mistakes.

Commands:

    git status --short
    git diff --check
    git diff --name-only
    git diff -- engine/synthetic_control.py engine/seasonality/event_study.py scripts/hincl2_event_study.py scripts/synthetic_control_phase0.py data/experiments

Expected: no protected file diff.

Step 2: run focused Python and template tests.

Command:

    python3 -m pytest tests/test_research_implication_card.py tests/test_build_measurement_hubv2.py tests/test_build_measurement_evidence_gap.py tests/test_public_chrome.py -q

Step 3: run design and generated-site gates.

Commands:

    python3 scripts/check_design_system.py --mode enforce-added
    python3 scripts/check_runtime_style_injection.py
    python3 scripts/check_ui_visual_evidence.py
    python3 scripts/check_template_site_sync.py

If sparse-checkout guards require additional generated trees, opt into only the named tree before rerunning. Do not run the repository-wide test suite from a sparse worktree.

Step 4: verify deterministic regeneration.

Run the Measurement builder twice and prove the tracked output diff is unchanged after the second run.

Commands:

    python3 scripts/build_measurement.py
    git diff --exit-code -- site/measurement.html site/measurementdata/measurement_data.js site/measurementdata/research_implication_cards.json

The second command is run only after staging or an equivalent before/after digest comparison that distinguishes intended generated changes from nondeterministic drift.

Step 5: request a code review using the repository review skill and fix every verified blocker or major issue. Re-run the affected gates after every fix.

## Task 5: Exact-head Draft/HOLD delivery

Step 1: fresh-read the exact Slack carrier and current GitHub issue. Stop with a typed no-effect hold if STOP, supersession, collision, or path ownership changed.

Step 2: fetch origin/main and reconcile all source movement against the frozen paths. Do not reset, rebase, force, or take over another writer. Integrate only collision-clear non-overlapping movement under repository law.

Step 3: run final verification from the exact candidate head and record command outputs.

Step 4: commit only the frozen-path implementation and evidence. Use a descriptive commit message.

Step 5: push the exact branch after another carrier read and open one Draft pull request linked to #6822. The PR title/body must say HOLD-FOR-SOL, name Sol as release authority, state the exact release condition, list protected no-edit paths, list real card quality states, and state that no merge/deploy/release/production effect is authorized.

Step 6: verify the remote head SHA, tree, changed paths, Draft state, absence of merge-on-green, and null native auto-merge. Run and monitor binding CI. Resolve genuine failures without changing scope.

Step 7: place the non-author Opus/Claude review request on the exact immutable PR head. Require findings keyed to immutable head/tree/path identities and the statistical, contract, authority, and visual gates in the frozen request.

Step 8: resolve verified review findings, rerun final checks, update the exact head, and obtain a clean final review. Any head movement invalidates the previous review.

Step 9: post the exact-head Draft/HOLD receipt on Slack after a fresh carrier read. Include PR, head, tree, checks, visual evidence, reviewer verdict, clean worktree proof, auto-merge null, label absence, effect NONE for merge/deploy/release/production, and the Sol-controlled release condition.

Step 10: stop shipping. Do not mark ready, arm auto-merge, merge, deploy, release, or claim live production state.

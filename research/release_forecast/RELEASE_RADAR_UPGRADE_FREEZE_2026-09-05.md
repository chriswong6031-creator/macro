# Release Radar — robustness and accuracy upgrade freeze

Date: 2026-09-05. Owner: CEO Sol under current explicit Chairman continuation.
Records operation: `release-radar-upgrade-freeze-20260905-sol-001`.
Parent: `WS:RATES-INFLATION-COMMAND`; no new workstream or runtime lifecycle.
Status: **records-only proposal / HOLD-FOR-SOL; no implementation or production acceptance**.
Protected procedure: `Mastermind@0d9cf2f58f9a6a1fe895d5d199abc18735201e24`, compatible Skillpack 1.0.1 / bootstrap-major 1.
Investigation pin: `macro@f69302500c0067e5c7f087a79cbaafe523720fd1`.
Records authoring base: `macro@22c10fc9956791d7c68456a3cb53d70ac388cf28`.

## 1. Outcome, value and architecture choice

The researcher must be able to answer: what will the official release report; what moved this forecast; which components and sources support it; what remains unknown; and how has this exact method performed at this lead time? The machine consumer must receive the same forecast identity, target, cutoff, missingness and evidence scope. The product should support comparison and release preparation, not make a green confidence bar stand in for evidence.

The defensible capability is a correction-safe, time-aligned corpus of forecasts, input receipts, official outcomes and component errors, combined with an understandable research workflow. Model complexity, more input columns, and basket weights summing to one are not sufficient moats or accuracy evidence. Learning must identify which sources and transformations actually improve matched out-of-sample forecasting.

Three approaches were considered. A cosmetic relabel-only patch leaves machine semantics and selected-model disagreement unresolved. A one-shot model rewrite entangles target corrections, weighting, uncertainty, UI and ownership, making causal attribution of improvement impossible. The chosen approach is an incremental extension of the existing release family: truthful diagnostics first, separately versioned uncertainty/target/horizon changes next, then economically faithful challengers and empirical promotion.

Preserve the existing MRI forecast family, official adapters, event calendar, release ledger, model registry, scoring/correction owners and publication path. Executive OS owns lifecycle, Agent OS organizational memory, GitHub implementation/evidence, Linear selective visibility and Slack transport. No second release laboratory, calendar, collector, forecast store, score ledger, queue, scheduler or publication owner is authorized.

## 2. Source-backed diagnosis and uncertainty

The current artifact at the investigation pin is `data/release_forecast/latest.json`, blob `01bc339e00f8ca4bff574593bb1571e0cdb8f9f0`. Its methodology labels the legacy cross-vintage target experimental, withholds accuracy claims, reports zero clean forward CPI champion observations and says Street consensus is unavailable. Shadow evidence is a separate lane, not transferable champion validation. Read the exact model/target/horizon cohort before interpreting any count.

### CPI and PPI do not share a residual denominator

`engine/release_components_cpi.py::compute_confidence_v2` weights absolute standardized-feature contributions. The audited CPI champion contributions are energy +0.091486, shelter -0.001378, persistence +0.081062 and pipeline -0.000527 percentage points. Persistence therefore accounts for `0.081062 / 0.174453`, approximately 46.47% of absolute attribution. This is not missing-data share. The attribution excludes the fitted intercept and is not a decomposition of a separate blended forecast. A baseline must not be reconstructed as exact from rounded values.

PPI's artifact has five populated declared features but `components`, `confidence_v2` and `confidence_components_v2` are null. `engine/release_targets_v11.py` explicitly omits block attribution. Its separate coverage flags are 1.0, 0.8 and 0.2; `engine/release_provenance.py` can derive coverage from equal feature counts and approximate freshness from present-leg classifications. Those fields do not measure economic basket coverage or zero unexplained forecast risk.

The Chairman's screenshot renders PPI 80/20/0 despite that null attribution. The exact deployed frontend fallback must still be inspected in the real checkout: the research mockup is not proof of current production JavaScript. This is a verified backend/display discrepancy with a bounded unresolved renderer location, not permission to invent source evidence.

CPI bridge prior-driven basket share, its basket accounting residual, model persistence attribution and realized forecast errors are four distinct quantities. A prior can fill unmodeled basket weight so the accounting sum closes without supplying new economic information. Never normalize these different denominators into one confidence bar.

### Confidence, target and clock semantics

The legacy confidence calculation ranks historical band widths and multiplies by input completeness. It is not a probability of being correct. CPI's attribution-quality heuristic is a different statistic again. The point/interval/model attribution shown across tabs must refer to the same selected forecast or be explicitly identified as separate comparisons.

The PPI snapshot is dated 2026-09-04 for a 2026-09-10 release but carries `cutoff_label=T-1`. That label cannot establish the actual information cutoff. Build time, observation period, official publication availability, first-seen time and decision cutoff must remain distinct. Date-only evidence must not be upgraded to an invented timestamp. A newly generated file must not launder stale inputs into fresh evidence.

`research/release_forecast/PREREG_COHERENT_RIDGE_V1.md` freezes an exact T-1 complete-case CPI candidate. Its absence at an earlier horizon is not by itself a pipeline defect. Show a source-backed eligibility reason when available, otherwise unknown. Reconstructed same-release-vintage targets and verified official first-print targets remain separate evidence classes; no retrospective result may become a genuine forward trial.

`engine/release_combined.py` currently adds champion error variance to between-model point dispersion, with missing champion scale treated as zero. Agreement can therefore produce a zero-width band without observed error-scale evidence. That behavior follows the existing combination specification. Repair requires an explicit method/distribution-version amendment and cohort separation, not an unannounced change to the historical combined_v1 contract.

## 3. Frozen first vertical: A1 diagnostic truth

The complete operator contract is [Macro #6868](https://github.com/mastermindx-market-intelligence/macro/issues/6868), operation `release-radar-a1-diagnostic-truth-20260905-sol-001`. The single capacity/continuity root is [Slack C0BSBM78V1N/1788590913.182019](https://mastermindxgroup.slack.com/archives/C0BSBM78V1N/p1788590913182019).

A1 is **SPEC_ONLY / PRE_START / WAITING_CAPACITY / needs_placement** at this record. Preferred avenue: CTO Sol on an eligible Codex engineering surface. The mission is bounded Python/Jinja/executed-JavaScript semantics and real browser integration; principal Fable capacity is not required to reconstruct the architecture. A discovered issue or delivered message is not receiver assignment or START.

A1 implements a pure diagnostic adapter in the existing forecast family, its additive producer projection, and the actual Release Radar consumer together. It separates feature availability, vintage quality, verified freshness, basket/prior coverage, standardized attribution and empirical performance. Missing attribution remains unavailable; all-zero contributions have an undefined attribution denominator. The blend can expose recorded model weights/points, not fabricated economic components. Keep the present primary-forecast selection policy.

The overview should clearly identify the selected forecast, `% month-on-month, seasonally adjusted`, actual cutoff precision, experimental status and uncertainty evidence. Contribution and benchmark differences use percentage points. The nominal p10-p90 interval is 80%; p25-p75 is 50%. Missing, nonfinite or reversed bands are unavailable in presentation, not repaired by inventing endpoints. Uncalibrated intervals must not be described as validated.

Every numerical forecast, weight, input, benchmark, target transformation, interval calculation, score-eligibility decision, ledger row and authority flag stays unchanged in A1. Preserve legacy fields for compatibility; add explicit diagnostic semantics rather than feeding presentation quality back into models. Claims remains benchmark-only; no trade/rank/size/gate promotion or invented consensus.

Required negative tests cover PPI null attribution, CPI's real denominator, blend/champion identity switches, missing baseline, all-zero contributions, bad numbers including booleans/NaN/infinities, unknown cutoff, unmatched evidence lanes and benchmark-only states. Remove only the additive diagnostic subtree and require deep equality of the original output before/after. Execute JavaScript and the real producer path; do not rely only on template substring checks.

Browser proof uses the canonical site builder and the actual card at 1440, 768 and 390 widths, dark/light and EN/ZH, including failure states. No manually spliced generated page. Local proof and production proof must be separately labeled. The worker returns one Draft/HOLD PR, exact head/tree, changed-path census, CI/security, numeric-invariance and browser receipts, and a durable continuation; no Ready, merge, deploy or self-assigned A2.

## 4. Accuracy roadmap and promotion law

A2 admits a separately versioned missing-error-scale repair with nullable consumers. Keep the point available while refusing unsupported probabilistic quantiles. Existing valid-scale numerical outputs should remain invariant, but old and amended distribution cohorts must not be silently pooled. A previous local source-excerpt candidate was rechecked in this continuation: baseline 15 failed/4 passed, candidate 19 passed, and 1,000 seeded valid-scale cases preserved all original numerical and receipt values. These are narrow local implementation experiments, not full-repository CI, approved statistical method, deployment or accuracy proof. Full input-contract and consumer integration testing is still required.

B extends existing coherent target owners and registers separate T-14, T-7 and T-1 information sets and eligibility rules. Specify exact official target, rounding, seasonal adjustment, source-vintage clocks, train-only transformations and failure behavior before outcomes are examined. Do not unfreeze the current T-1 candidate or reuse historical target reconstruction as forward evidence.

C develops a CPI component challenger. Priorities are versioned official weights and seasonal conventions, a genuine services-ex-shelter construction, publication-safe energy proxies and separate asking-rent versus continuing-rent dynamics. Existing bridge disclosures of source-scope mismatch require economic repair, not stronger confidence labels. Every source addition needs lawful access, usable historical availability and a matched incremental-value test.

D develops an explicit PPI goods/services/trade-margin/construction challenger. Current broad PPI lags may contain services information indirectly; they do not constitute an independently explained component forecast. Where leading information is unavailable, preserve an explicit persistence prior and uncertainty. Never claim complete economic coverage because five declared regressors are populated.

E compares matched model/target/horizon cohorts using MAE, RMSE, signed bias, a preregistered tolerance event, nominal 50/80% coverage, width and a proper interval score. Count independent economic releases rather than repeated updates. Keep benchmark source/cutoff identity; a blend containing an external nowcast is not independent evidence of proprietary superiority over it. Analyze correlated errors and regime failures, preserve failed attempts, and separate diagnostic historical replay from genuinely prospective evaluation.

Thresholds, minimum samples, loss functions, calibration windows, tolerances and multiple-testing/selection rules must be frozen in the relevant candidate preregistration before outcome-driven selection. This roadmap does not invent a promotion approval or override existing frozen kill criteria. A model can remain experimental, be withheld or be rejected; no display outcome is required to become a trade signal.

F proves reliability and usefulness through a real official release: canonical collection -> time-aligned target receipt -> frozen forecast/scoring -> visible product and machine consumers. Exercise corrections, stale inputs, unavailable sources, publication failure and rollback. Track whether the workflow improves research and whether added information improves forecasts; a green CI or attractive screen proves neither on its own.

## 5. Current ownership and continuation gates

Original F1 remains `ric-f1-release-event-20260828-sol-001`, MAS-204, [Slack C0BSBM78V1N/1787975946.019219](https://mastermindxgroup.slack.com/archives/C0BSBM78V1N/p1787975946019219). The complete carrier had no later worker START after Aug-29 CONTINUE/watch when re-read. Historical effect=NONE is not a fresh local effect reconciliation. Preserve original native task `01a04bde-8ce8-7903-ae91-6c38c63ac4cf`, its worktree and carrier. A read-only host/continuity reconciliation request was posted at `1788591023.176999`; it does not authorize rebind, replacement, cleanup or wider F1 scope. A1 shared-producer edits wait for that owner boundary.

Open Draft/HOLD #6685 shares `templates/dashboard.html.j2` and `site/macro.html`. The fetched template patch around reported head `6d7b0dfcb2d8d2a7e6a677b10e36ce517a494494` changes Grey Deer imports, hero placement, Risk Detail and overlay comments, not the Release Radar functions. This narrows the collision to shared-file/integration ownership; it is not an exact-current integrated-candidate or owner-release proof. Re-read actual heads/hunks and prove compatibility before A1 edits; do not merge or repair #6685 here.

#6593 remains the sole existing RIC workstream-record repair, actual observed head `0e07a15f0f44aa388706cb18c92f4b1702bc2fcc`. Do not edit `agentos/workstreams/WS-RATES-INFLATION-COMMAND.md` in this records carrier or A1. This record covers the Release Radar subset only and does not re-adjudicate other RIC F2/F3/dependent operations.

The A1 placement request is delivered, but no concrete receiver, START or accepted reciprocal continuation is asserted. This CEO Chat surface exposes no native Task/Automation/condition-watch create action or registered exact-carrier waiter. Slack reminders/scheduled messages are not that capability. Existing Capacity/Operator-Continuity must establish the actual route or return a typed blocker; no duplicate watcher/control plane and no implied background work.

Linear MAS-187 selectively projects #6868 and its root without creating another issue. GitHub, Slack and Linear writes now have successful receipts; the earlier Chat-only report's read-only limitation is superseded as a current capability statement, while its historical local experiment remains non-production evidence.

## 6. Source and supersession boundary

Apply current protected Skillpack and universal dialogue/routing law, `research/DO_NOT_REBUILD.md`, `DEC:RIC-CANONICAL-COMPOSITION-BOUNDARIES`, and the accepted RIC recovery freeze. This proposal adds the A1 product-truth boundary and future research sequence; it does not replace event/target/model owners or amend any frozen numerical method. #6868 contains the executable A1 handoff. Independent statistical waves require their own admitted preregistration, delivery, tests and acceptance.

Primary implementation evidence is pinned in `engine/release_components_cpi.py`, `engine/release_provenance.py`, `engine/release_targets_v11.py`, `engine/release_combined.py`, `scripts/build_release_forecast.py`, `data/release_forecast/latest.json`, `data/release_forecast/scoreboard.json` and `research/release_forecast/PREREG_COHERENT_RIDGE_V1.md`. Re-read these at the then-current protected/default branches before action. No accuracy promise in this document is a substitute for measured evidence.

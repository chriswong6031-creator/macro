# Characteristic Market Time × Signal Grain — W0 Adversarial Review Amendment

**Date:** 2026-09-03
**Workstream:** `WS:TEMPORAL-GRAIN-INTELLIGENCE`
**W0 carrier:** Macro PR #6790
**Exact reviewed pre-amendment head:** `d9ce56f4b276dbd11f6e2220ea187fea6898117e`
**Protected procedure pin:** `mastermindx-market-intelligence/Mastermind@793e75639911f21dae9c90a77c3a5dbf4b37cbb0`
**Review verdict on pre-amendment head:** `REQUEST_CHANGES — one scientific blocker`
**Capability:** records-only `SPEC_ONLY`; production and signal authority remain zero

---

## 1. Why this amendment exists

Adversarial review found one material defect in the otherwise bounded W0 package:

> The frozen W1 plan can prove chart identity, indicator parity, history/phase stability and
> mechanical sensitivity to G/A/K/D perturbations, but it cannot legitimately conclude that
> `FILTER_MEMORY` or `SESSION_GRAMMAR` explains the **usefulness** Chris observed using only
> indicator-shape, cross-count, total-variation and signal-density diagnostics.

Those diagnostics say how the indicator changes. They do not say whether entries/localized turns,
adverse excursion or false starts improve. Calling them mechanism proof for usefulness would narrow
the Chairman’s scientific question to an implementation-smoothness study and create a false-positive
completion path.

This amendment repairs that defect by separating:

1. **W1A — exact reproduction + mechanical artifact attack, with no outcome read;**
2. **W1B — separately preregistered usefulness-mechanism diagnosis, only after W1A survives.**

The split is scientific sequencing, not bureaucracy. It prevents outcome leakage before parity while
preserving the actual user job.

## 2. Authority and precedence

This amendment is a narrow, higher-precedence correction to these W0 files in PR #6790:

- `research/signal_engine/temporal_scale/CHARACTERISTIC_MARKET_TIME_SIGNAL_GRAIN_ARCHITECTURE_FREEZE_2026-09-03.md`
- `docs/superpowers/specs/2026-09-03-characteristic-market-time-signal-grain-design.md`
- `docs/superpowers/plans/2026-09-03-temporal-grain-gakd-artifact-attack-r1.md`

It supersedes only clauses that:

- let the no-outcome W1 artifact harness return `FILTER_MEMORY`, `SESSION_GRAMMAR`, or `MIXED` as a
  usefulness-mechanism classification;
- call cross/turn timestamps, total variation, phase displacement or signal density an “effect”
  sufficient for that conclusion;
- allow W2 structure-scale work to begin directly after the mechanical artifact attack without a
  frozen usefulness read;
- omit `tests/test_temporal_scale_chart_export.py` from the top-level W1A file map.

All other architecture, G/A/K/D, ownership, identity, rights, no-rebuild, zero-authority, parity,
TrialLedger and Stock Identity contamination laws remain controlling.

## 3. Corrected sequence

### W1A — exact chart reproduction and mechanical artifact attack

**Operation:** `temporal-grain-gakd-artifact-attack-r1-20260903-sol-001`

**Mission:** Given exact chart recipes and rights-safe/local exports, prove or refute exact
TradingView indicator parity and determine whether the motivating construction is mechanically
stable under history, anchor/session, bar-grain, kernel-memory and data-plane perturbations—without
reading future returns, troughs, adverse excursion, trade outcomes or portfolio performance.

W1A may answer:

- Is the instrument/feed/session/adjustment/roll identity complete?
- Are actual bar opens/closes and clipped bars faithfully represented?
- Does the canonical Python indicator match the exported TradingView vector after warm-up?
- Is the result invariant to irrelevant leading-history changes?
- Does the indicator path depend on one arbitrary phase?
- Do fixed-bar and memory-matched variants produce materially different indicator geometry?
- Do semantic-session and arbitrary-phase constructions differ mechanically?
- Are missing/no-trade/activity-time differences disclosed?

W1A may **not** answer:

- which construction is better at locating useful turns;
- whether one construction reduces adverse excursion or false entries;
- whether the effect has economic value;
- whether the phenomenon generalizes;
- whether a structure-derived scale predicts signal usefulness.

### W1B — preregistered usefulness-mechanism diagnosis

**Future operation:** `temporal-grain-usefulness-mechanism-r1-20260903-sol-001`

W1B is not commissioned by W0. It requires all of:

1. W1A exact parity `PASS` for at least one motivating chart;
2. W1A status `MECHANICALLY_SURVIVES` rather than `ARTIFACT`/`UNRESOLVED_DATA`;
3. immutable W1A recipes, exports, grid and result hashes;
4. a fresh Sol `CONTINUE` after reviewing W1A;
5. a separately committed preregistration before any usefulness outcome is read.

The W1B preregistration must freeze:

- the exact primary persona task being graded;
- localization and risk-utility rulers separately;
- real/traded-time horizons and path/episode normalization;
- signal-frequency and overlap/effective-N controls;
- the complete fixed-bar, memory-matched and anchor/session contrast grid;
- inferential versus descriptive metrics;
- selection/multiplicity controls and the look budget in existing TrialLedger/Evaluation OS;
- deterministic decision rules for `FILTER_MEMORY`, `SESSION_GRAMMAR`, `MIXED`, `ARTIFACT`, or
  `UNRESOLVED_DATA`;
- the fact that WMT and the motivating silver instrument remain selected discovery examples, so W1B
  can diagnose those observations but cannot establish cross-instrument generalization.

Trade economics remain deferred until localization and risk utility survive.

### W2 — outcome-blind structure-scale derivation

W2 begins only after W1B leaves a real usefulness phenomenon to explain and Sol explicitly
continues. It freezes an outcome-blind market-scale band and abstention law before exposing the
structure-to-kernel relationship to any validation outcome.

### W3 — untouched confirmation

Only W3 may test generalization on a mechanically selected, instrument-disjoint confirmation set.

## 4. Corrected W1A result contract

The no-outcome W1A contract remains:

```text
schema_version = mastermind.temporal_artifact_attack.v1
```

but its result field is corrected from a final usefulness `classification` to:

```json
{
  "mechanical_status": "ARTIFACT|UNRESOLVED_DATA|MECHANICALLY_SURVIVES",
  "final_mechanism_classification": null,
  "mechanical_receipts": [],
  "authority": {
    "may_rank": false,
    "may_gate": false,
    "may_size": false,
    "may_trade": false,
    "may_modify_prophet": false
  }
}
```

W1A must reject a non-null `final_mechanism_classification`.

### Deterministic W1A status law

Apply in this order:

1. incomplete chart identity, unresolved feed/session/roll/rights, or no comparable indicator rows
   → `UNRESOLVED_DATA`;
2. parity failure, timestamp/bar-construction failure or history-truncation failure → `ARTIFACT`;
3. the motivating indicator path exists only on one arbitrary phase and not on its semantic-session
   construction → `ARTIFACT`;
4. otherwise → `MECHANICALLY_SURVIVES`.

`MECHANICALLY_SURVIVES` means only that a properly identified, parity-matched phenomenon remains
available for a preregistered usefulness test. It is not evidence that the signal helps a user.

## 5. Corrected W1A diagnostics

The following remain valid, but their claims are mechanical only:

- evaluable/finite bar counts;
- warm-up loss;
- missing, empty and clipped-bar prevalence;
- cross/turn count and timestamps;
- indicator total variation;
- fixed-bar versus memory-matched path distance;
- semantic-session versus arbitrary-phase path distance;
- timestamp displacement;
- event density per traded session;
- sensitivity to implementation and D-plane identity.

Allowed receipt language:

```text
fixed-bar indicator geometry converges under memory matching
semantic-session indicator path is more phase-stable than arbitrary anchors
one arbitrary anchor uniquely creates the observed indicator path
```

Forbidden W1A receipt language:

```text
filter memory explains better entries
session grammar improves localization
this configuration has edge
this timeframe is optimal
```

## 6. Existing evaluation owner and no-duplicate ruling

Repository archaeology found no landed general-purpose localization-ruler module that W1B can
simply import. The current house timing standard lives in
`scripts/research/ptt_w1_timing_regrade.py` and its copied descendants. It defines the established
methodological ancestors—MAE, low proximity, trough timing, per-name-first aggregation, random-day
nulls and month-cluster inference. Stock Identity’s generalized localization ruler remains a future
wave, not a currently callable owner.

Consequences:

- W1A creates no outcome evaluator at all.
- W1B must perform a fresh owner/collision read when preregistered.
- W1B may implement only a bounded research adapter for the frozen intraday/real-time ruler if no
  canonical reusable owner has landed by then.
- That adapter is not a second Evaluation OS, qledger, event store or promotion authority; its look
  budget and results register through existing TrialLedger/Evaluation OS.
- W1B may not import a whole historical research runner merely to inherit hidden constants or data
  assumptions.
- If the generalized Stock Identity ruler lands before W1B, W1B must reuse its lawful concepts or
  callable owner rather than compete with it.

## 7. Corrected W1A implementation file map

The top-level plan file map is corrected to include the chart-export test already required by Task 3
and by the final path ceiling:

```text
tests/test_temporal_scale_chart_export.py
```

The complete W1A test set is therefore:

```text
tests/test_temporal_scale_contracts.py
tests/test_temporal_scale_chart_export.py
tests/test_temporal_scale_kernel_memory.py
tests/test_temporal_scale_session_bars.py
tests/test_temporal_scale_parity.py
tests/test_temporal_scale_artifact_attack.py
```

No outcome/localization test belongs in W1A.

## 8. Corrected acceptance and stop conditions

### W1A acceptance

W1A is acceptable only when:

- exact input identity/hashes are printed;
- synthetic contract/session/kernel/parity tests pass;
- the Pine probe compiles;
- at least one exact motivating chart reaches parity or returns a typed independent blocker;
- WMT and silver are reported independently;
- the frozen mechanical grid is registered before diagnostics;
- no outcome/return/trade/portfolio module or data is read;
- `final_mechanism_classification` is null;
- every authority field is false;
- raw restricted data remains outside Git;
- exact-head CI, path ceiling and review pass.

### W1A stop

Stop at `ARTIFACT` or `UNRESOLVED_DATA` for the affected motivating chart. Do not escalate to W1B
merely because another proxy/feed/instrument is available.

### W1B acceptance

W1B’s future preregistration and result must prove that any claimed `FILTER_MEMORY`,
`SESSION_GRAMMAR` or `MIXED` classification follows **localization or risk utility**, not merely
indicator shape. W1B still creates no generalization or production authority.

## 9. Review consequence

With this amendment incorporated into the workstream and continuation records, the pre-amendment
scientific blocker is closed at the architecture level. W0 may be accepted only after exact-head CI
and a fresh review confirm that every downstream instruction treats this amendment as controlling.

No empirical work, worker START, runtime Job, Slack dialogue, market-data collection, trial outcome,
product behavior or signal authority is created by this amendment.

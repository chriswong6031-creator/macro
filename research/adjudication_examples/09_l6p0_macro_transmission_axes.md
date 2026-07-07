# L6-P0 Macro Transmission — Pass Reopens Charter Question Without Auto-Chartering

**Source:** PR #1693 (W-C of the Three-Lobes program). Primary docs: `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md` §7, `research/macro_tx/L6_PHASE0_PREREG.md`. **Status:** canonical (RUL-SUCC-8).

## What was asked

The docket entry L6 (Macro & Policy Transmission Fingerprints) was gated on a Phase-0 study demonstrating that hostile macro conditions at fire date separate forward outcomes strongly and stably enough OOS to beat the noisy-sector precedent (`sector_rate_inflation` / canon shadow, demoted for split-sample forward-IC instability; cf. NWP-U20 and GAP-U5, both deferred on this precedent). PR #1693 ran the study and reported results. The question was: what does a PASS on one axis mean?

## What was decided (the holding)

- **A1 rates_shock PASS:** the rates shock axis (20-BD change in 10y yield >= +1.5 sigma AND >= +25bp) produced a sign-stable hostile-vs-benign delta with episode-clustered CI excluding 0 in both OOS halves, surviving BH q=0.10 across 4 primary h21 cells after stratified drawdown control. This is PASS per the prereg's verdict criteria (RUL-C4g).
- **A2 usd_shock FAIL, A3 credit_shock FAIL, A4 fin_conditions FAIL:** all three remaining axes failed at h21 on the pre-registered criteria; nulls printed per cell. L6 stays gated on these axes.
- **A1 PASS re-opens the L6 charter question at the docket — NOT an automatic charter:** the two-lobe cap remains binding (cap exceptions previously killed per GAP-U3); a separate masterplan + prereg is still required even for the passing axis. No live flag, chip, world_state key, kernel cell, or per-name output ships from this study regardless of outcome.
- **Conditions C1-C4 for charter consideration:** Fable recorded four conditions that must be addressed in any future charter packet: C1 (the cap must be freed or waived via T2 panel + operator); C2 (a per-axis mechanism must be drafted explaining why rates_shock separates outcomes — the study is descriptive, not mechanistic); C3 (a replication in the modern cohort sensitivity tape, when available); C4 (the L6 charter must carry a drawdown-covariate note explaining that hostile macro periods are correlated with market drawdowns, and the stratification approach in the prereg is the required mitigation).
- **Episode-clustered CI is mandatory:** the cluster unit is the contiguous hostile macro WINDOW, never the individual fire, because fires across all sectors on the same macro dates are one draw, not hundreds. The Opus stats review confirmed the bootstrap multiplicity bug fix (CIs widened ~24% after fixing) and endorsed the floored-excursion indicator relabeling.
- **`derived_from_surface: null` (first registered question):** this study is itself a contamination surface; any later prereg on this tape carries `derived_from_surface: macro_tx_phase0_v1`. The `macro_tx` family budget (12 cells) is now consumed.
- **Opus stats review was mandatory:** per RUL-C4 and the prereg, Opus stats review was required before the report merged. The review caught a bootstrap multiplicity bug (CIs widened ~24%), required the endpoint to be relabeled as floored-excursion indicator, and required the family composition to be printed. The report merges only after PASS-UPHELD on the revised statistics.
- **No composite macro score:** per RUL-C4a, no composite macro-hostility score is formed anywhere. Each axis reads out separately.

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| A1 PASS recorded, charter question re-opened | send_to_review (gate-clearing study) | **T0** (ROUTINE) | Opus alone |
| A2/A3/A4 FAIL printed | null result record | **T0** (ROUTINE) | Opus alone |
| Future L6 charter (if pursued) | new_lobe_charter | **T2** (CONSTITUTIONAL) | Full packet + panel (>=2 Opus refuters) + operator |
| `macro_tx` FDR family (12 cells) registered | new FDR family | **T1** (CONSEQUENTIAL, was pre-approved in Three-Lobes adjudication) | Pre-approved; no new packet |
| Mandatory Opus stats review of bootstrap fix | stats review of running study | **T0** (ROUTINE) | Opus alone |

A study pass is T0 (send to review; record the gate-clearing result). The charter, if ever pursued, is T2 — a new lobe charter is always T2 (Constitutional) under the bench. The pre-approved `macro_tx` family registration from the Three-Lobes adjudication does not need a new packet — that T1 decision was already made in PR #1673.

## Lenses that did the work

- **Statistics:** the dominant lens. Episode-clustering on the hostile macro WINDOW is the key design choice — it prevents counting 50 sector fires during one rates-shock episode as 50 independent draws when they are one macro draw. The Opus review caught the bootstrap multiplicity bug that inflated CIs before fixing; this is a case where the mandatory Opus stats review materially changed the verdict's reliability.
- **Case law:** RUL-C4 (per-axis, never fused; drawdown covariate control mandatory; beat-the-noisy-sector-precedent operationalized). The noisy-sector precedent (split-sample forward-IC instability on `sector_rate_inflation`) is the explicit prior: A1 must be sign-stable in BOTH OOS halves to differentiate from that prior.
- **Authority:** a PASS is descriptive; it re-opens a question, it does not grant authority. The study carries no live flag, chip, or kernel cell regardless of outcome. The authority ladder for L6 remains: PASS here -> charter question re-opened -> T2 packet + panel + operator for new lobe -> constitutional promotion path.
- **Build feasibility:** the sensitivity tape (`data/replay/replay_boarded.parquet`) is Mac-local and absent from git checkouts by design; the report prints "sensitivity tape absent on this host" rather than failing.

## Citable holding

A gate-clearing study PASS re-opens the charter question at the docket and is recorded as a T0 decision; it does not auto-charter a new lobe, does not grant any authority, and does not supersede the two-lobe cap; the charter, if pursued, requires a Tier 2 packet with adversarial panel review and operator sign-off.

## Ruling IDs

RUL-C4 (L6-P0 legal shape), RUL-C11 (macro_tx FDR family), conditions C1-C4 (charter pre-conditions recorded); RUL-SUCC-2 (Tier ladder — charter is always T2)

# Dislocation Intelligence — Cross-Issuer Panel P0 preregistration

**Version:** P0 / 2026-08-20  
**Authority:** research/display only  
**Parent:** Alpha Intelligence Expansion K3-E → K4-F/G → K5/K6  
**Proof exclusion:** Endeavour Silver / EXK / EDR and every issuer used to design P0

## Mission

Test whether adverse-event evidence plus relative confirmation distinguishes temporary mispricing from justified impairment across issuers, without creating a new residual engine, score, ranker, grader, event store or Prophet gate.

## Blind three-seat law

### Extractor

May read official issuer releases, SEC filings, exact event identity and calendars. May not read price/volume stores, charts, outcomes, winner/failure casebooks or EXK replay results.

### Freeze gate

Before any price join: canonical-sort the manifest; hash every source; calculate `manifest_sha256`; register all trials; commit manifest and prereg. Any post-outcome correction mints P0.v2 and voids the affected claim.

### Runner

Reads the sealed manifest and canonical price/counterfactual stores. Cannot change event fields.

### Adjudicator

Receives results only after byte-identical reruns and automated leakage/boundary reports.

## Primary panel

- U.S. and Canadian common equities/ADRs.
- Event public dates 2016-01-01 through 2025-12-31.
- Confirmatory era 2022-01-01 through 2025-12-31; 2016–2021 development/descriptive only.
- Endeavour and all design-used issuers excluded.
- Metals/mining locked as external validation until the non-mining core is adjudicated.
- At least 126 populated pre-event sessions plus five-session embargo.
- Primary share-price floor $5; pre-event 20-session median dollar volume ≥$2M.
- Delisted/censored names retained where prices exist; all refusals printed.
- Prespecified $2–$5 share-price sensitivity is descriptive only.

### Honest-N floors

- ≥120 economic episode origins;
- ≥80 issuers;
- ≥40 event-date clusters;
- ≥15 origins per primary temporary-event family;
- ≥40 modern-era origins;
- no issuer >3 origins or 5% of weight;
- no event-date cluster >10% of weight.

A floor failure yields `INSUFFICIENT_N`.

## Event families

Temporary families:

1. `PHYSICAL_MECHANICAL_INTERRUPTION`
2. `EXTERNAL_HUMAN_INTERRUPTION`
3. `CYBER_OR_IT_INTERRUPTION`
4. `WEATHER_OR_PHYSICAL_DISASTER`
5. `TEMPORARY_EXPECTATION_RESET`

Controls:

- `STRUCTURAL_IMPAIRMENT`
- `MACRO_OR_INDUSTRY_WIDE`
- `RESOLVED_BEFORE_DISCLOSURE`
- `NO_EVENT_RELATIVE_BREAKOUT`

One economic episode may have many public transitions. Only the first qualifying adverse transition is an origin for N; later pulses, mitigation, resolution and correction stay linked and visible.

## Required t0 evidence

Every origin sources occurrence/public clocks, venue-specific first-tradable date, affected scope, duration state, explicit recoverability evidence, asset integrity, quantified impact, balance-sheet/financing risk, mitigation state, disclosure lag, control locus, completeness/rights/reconstruction state, literal evidence spans and source SHA-256.

`intent_orchestration` is always `UNKNOWN` and excluded. No LLM probability, sentiment score or model confidence is legal.

## Clock and fill law

- SEC events use acceptance timestamp; issuer releases use first-party publication time.
- Date-only sources are refused from primary inference.
- Pre-open/intraday disclosure uses that session's close; after-close uses next session's close.
- Confirmation at close t enters at close t+1.
- No nearest-date substitution, forward fill or fake intraday replay.

## Counterfactuals

Print separately:

1. `matched_k`: equal-weight top-k pre-event correlated donors.
2. `sc_nnls`: non-negative simplex synthetic control.

Frozen inputs: 120-session pre-window; five-session embargo; ±21-session donor-event exclusion; ≥90% coverage; $2M dollar-volume floor; donor/treated volatility ratio 0.5–2.0; no same issuer, cross-listing or affected linked entity as donor.

`matched_k` defines relative-confirmation. `sc_nnls` estimates outcomes. Estimator disagreement is printed, never fused.

## Frozen arms

| arm | rule |
|---|---|
| P0-H0 | first public tradable close |
| P0-H1 | H0 restricted to recoverable-at-t0 |
| P0-H2 | next close after strict 10-session treated/matched-k relative high within 60 sessions |
| P0-H3 | next close after strict 20-session relative high within 60 sessions |
| P0-H4 | recoverable-at-t0 plus H3 |
| P0-H1B | new unresolved adverse information plus recoverability; exploratory |
| P0-H4B | H1B plus H3; exploratory |

No H3 signal within 60 sessions is cash/abstention with zero policy return. No stop, parameter optimization or alternate hold is part of P0.

## Sole primary claim

Across all sealed origins, paired **P0-H4 policy return minus P0-H1 policy return at 40 sessions** is positive after 50 basis points round-trip cost.

- H1: synthetic-control CAR from H1 entry through entry+40.
- H4: synthetic-control CAR from H4 entry through entry+40.
- H4 no-entry: zero cash return.
- Refused/ungradable origin: excluded with named reason, never zero.

Secondary non-gating endpoints: 20/60-session differences, MFE, MAE, time-to-positive, time-underwater, H2 versus H3, signal incidence, time-to-confirmation, 25/100-bp sensitivities and event-family/impairment/disclosure-lag/liquidity strata.

## Inference

Economic episode is the unit. Cluster/resample by issuer and event date. Report date-clustered bootstrap CIs plus house HAC/BH-FDR/DSR. Register every arm × horizon trial before execution. Preserve era split. Interpret levels against matched placebos, not zero. No pooled claim may be carried by one era, family or issuer.

## Falsifiers

Hold/kill P0 if:

1. H4−H1 40-session paired CI includes zero.
2. H4 does not improve return or MAE after abstentions/costs.
3. Generic no-event breakouts perform comparably.
4. Result disappears in 2022–2025.
5. One family/issuer/date cluster carries it.
6. `matched_k` and `sc_nnls` materially disagree without improved placebo dispersion.
7. Structural controls perform as well as temporary cases.
8. Attrition/survivorship sensitivity reverses sign.
9. Honest-N floors fail.

A failed P0 kills the tested entry construction, not event attribution or OpportunityCase context.

## Authority boundary and stop

P0 cannot feed Prophet, Radar, Fusion, Entry Availability, sizing or candidate population; create an Opportunity Score; retune DRL; create a second event store; or let dossier prose enter ranking.

Stop after blinded manifest freeze, source audit, canonical reruns, placebo/control packet, adversarial review and Sol adjudication. Do not build a live model or user surface.

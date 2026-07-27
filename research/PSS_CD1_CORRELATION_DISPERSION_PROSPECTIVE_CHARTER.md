# PSS-CD1 prospective charter — correlation-one crowding hazard

Status: **FROZEN BEFORE THE FIRST ELIGIBLE ACTION** (2026-07-27).

Canonical identifier: **PSS-CD1**
(`pss_cd1_correlation_dispersion_prospective`).

## 0. Claim

SR3 showed that a majority of peers advancing together after systemic stress is
not durable-absorption evidence. CD1 asks a narrower prospective question:
inside future RH1 hazards, is the dangerous subset the one in which sector
returns have collapsed onto one common factor while cross-sectional dispersion
is unusually low?

First order: high common-factor share says recent returns contain little
name-specific information. Second order: low dispersion says the rally offers
few natural winners to absorb reallocations when beta turns. Third order:
similar factor exposure and entry timestamps can synchronize exits, deepening
drawdown and tails. Unlike SR3, this does not count how many peers are positive;
it measures the geometry of their return covariance and dispersion.

## 1. Exact construction

The machine source of truth is
`data/personality_timing/crowding_hazard_manifest_v1.json`.

The only source is a future PSS-RH1 `relief_hazard` action B. Historical
SR3/RH1-shaped events are ineligible. Using at least 15 frozen same-sector
ex-self peers:

- build ten daily simple returns ending at B;
- population-standardize each peer column;
- define `pc1_share` as the leading squared singular value divided by the sum
  of all squared singular values; and
- define `dispersion_5` as the cross-sectional median absolute deviation of
  peer five-session simple returns.

For each metric, reproduce the same calculation on the 126 completed metric
sessions ending at B-1. At least 63 valid observations are required. Freeze the
prior 80th percentile of `pc1_share` and prior 20th percentile of
`dispersion_5`.

- **crowding_hazard:** PC1 share is at or above q80 and dispersion is at or
  below q20.
- **uncrowded_control:** PC1 share is below q80 and dispersion is above q20.
- **mixed_diagnostic:** exactly one extreme is present; excluded from primary
  inference.

The action remains B close. Current-B data are lawful because CD1 is a
same-close hazard descriptor, never an earlier call.

## 2. Prospective firewall and ruler

B must be strictly later than 2026-07-24. The ledger launches empty. Nightly
alone may enroll and grade; events are keep-first. No alternate PCA window,
dispersion estimator, quantile, AND/OR rule, or mixed-label reuse may be tried
on accrued outcomes.

Outcomes start at B+1 and mature at B+63. MAE63 and tail10 are primary;
proximity/W5/called/tdt and +8% rebound before the original RH1 reference breach
are support.

## 3. One-read decision law

The only formal read requires at least 250 matured primary rows, 125 unique
names, 50 rows per primary label, 12 action months spanning 365 days, and 20
informative exact strata. The tape keeps the first primary name-month and
matches sector × action month × RH1 anchor-severity band × RH1 delay band.

Equal-weight strata use 10,000 within-stratum permutations (seed 20260812) and
a 5,000-draw three-month moving-block diagnostic interval (seed 20260813).
Positive harm is control MAE minus hazard MAE, hazard tail minus control tail,
control W5 minus hazard W5, and control rebound-first minus hazard
rebound-first. Qualification requires clean positive MAE and tail harm, positive
support, independent early/late and leave-one-sector-out signs, and no sector
above 25% of hazard rows. Any failure kills CD1.

## 4. Authority

CD1 has no entry, rank, size, gate, alert, display, or auto-promotion authority.
Passing would only authorize a separately frozen hazard-intervention shadow.
It may not be described as a validated top, sell rule, or crowding gate before
that second trial succeeds.

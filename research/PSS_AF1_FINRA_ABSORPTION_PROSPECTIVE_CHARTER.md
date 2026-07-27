# PSS-AF1 prospective charter — FINRA flow-backed absorption witness

Status: **FROZEN BEFORE THE FIRST ELIGIBLE ACTION** (2026-07-27).

Canonical identifier: **PSS-AF1**
(`pss_af1_finra_absorption_witness_prospective`).

## 0. Claim and data honesty

AF1 is the most orthogonal follow-on, but also the easiest to overstate. FINRA
daily short-sale volume records short-marked transactions. It is not short
interest, net inventory, aggressor direction, or proof of bearish intent;
market-making and hedging contribute heavily. Raw short ratio and raw
off-exchange share are therefore forbidden as standalone directional signals.

The narrower claim is challenge-response: among future CR1 resilient leaders
with comparable FINRA-reported activity, does price leadership that survives
unusually high *own-history* short-marked activity have lower subsequent risk
than equally resilient leadership without that witness?

First order: the subject has already passed a real sector pullback rather than a
synthetic price pattern. Second order: elevated own-normal short-marked activity
shows that the hold did not occur simply because reported transactional
pressure disappeared. Third order: if leadership persists while both activity
and short marking are high, liquidity may be transferring inventory without
price concession. If the label fails, the correct conclusion is that daily
short marking does not identify durable absorption.

## 1. Exact construction

The machine source of truth is
`data/personality_timing/flow_absorption_manifest_v1.json`.

The only source rows are future PSS-CR1 `resilient_leader` events. Let the CR1
challenge be S through C. Require exact FINRA rows on:

- the 20 subject trading sessions immediately before S; and
- all three challenge sessions S:C.

From the 20-session baseline, compute the volume-weighted short ratio for every
overlapping three-session window (18 values) and freeze their linear 75th
percentile. The challenge ratio is `sum(short_vol)/sum(total_vol)` across S:C.
Activity is mean FINRA total volume across S:C, compared with the baseline
20-session median.

- **flow_witness:** challenge ratio is at or above the frozen q75 and challenge
  activity is at or above the baseline median.
- **leader_flow_control:** challenge ratio is below q75 with the same
  above-median activity requirement.
- **low_activity_diagnostic:** challenge activity is below the median.
- **missing_flow_diagnostic:** any exact-date baseline or challenge row is
  absent.

The activity restriction gives treatment and control the same minimum
transactional relevance. The action is C close; AF1 does not backdate the
challenge or originate a trade.

## 2. Source binding

The FINRA panel covered 795 of 799 frozen RH1 names at registration, over 42
sessions from 2026-05-26 through 2026-07-24. Four symbols were unavailable:
BF-B, BRK-B, FI, and MOG-A. Missing coverage is an honest exclusion, not an
imputed zero.

Runtime binds a stable canonical 51,960-row panel prefix through 2026-07-21.
The newest sessions are deliberately outside the immutable prefix because the
collector may lawfully restate them. Quiver off-exchange history and delayed
ATS venue totals are excluded: their venue mix and publication lag would add a
second, structurally biased hypothesis to this one-configuration test.

## 3. Prospective firewall and ruler

The source CR1 action C must be strictly later than 2026-07-24. Historical
paths cannot be reconstructed. Nightly alone advances the empty-at-launch,
keep-first ledger. No ratio threshold, baseline, activity floor, off-exchange
overlay, or missing-data rule may change after outcomes accrue.

Outcomes begin at C+1 and mature at C+63. MAE63 and tail10 are primary;
proximity/W5/called/tdt and +8% rebound before the original RH1 frozen reference
breach are support.

## 4. One-read decision law and authority

The sole read requires 150 matured primary rows, 100 unique names, 40 rows per
primary label, 12 action months spanning 365 days, and 12 informative exact
strata. The first primary name-month is matched by sector × action month × RH1
anchor-severity band × RH1 delay band. Inference uses 10,000 within-stratum
permutations (seed 20260814) and a 5,000-draw three-month block diagnostic
interval (seed 20260815).

Positive benefit is witness MAE minus control MAE, control tail minus witness
tail, witness W5 minus control W5, and witness rebound-first minus control
rebound-first. Qualification requires clean MAE and tail benefit, positive
support, positive early/late and leave-one-sector-out signs, and no sector above
25% of witness rows. Any failure kills AF1.

AF1 is operator research only: no entry, rank, size, gate, alert, user display,
or promotion. A pass would authorize only a separately preregistered
intervention shadow. “Flow-backed” must never be shortened to “institutional
buying,” “short squeeze,” or “confirmed absorption.”

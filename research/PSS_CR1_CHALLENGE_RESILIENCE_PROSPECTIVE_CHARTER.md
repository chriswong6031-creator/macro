# PSS-CR1 prospective charter — challenge-resilient leadership

Status: **FROZEN BEFORE THE FIRST ELIGIBLE ACTION** (2026-07-27).

Canonical identifier: **PSS-CR1**
(`pss_cr1_challenge_resilience_prospective`).

## 0. Why this is a different species

F1–F4 and SR1–SR3 tried to infer terminal supply from the shape of a decline or
from contemporaneous confirmation. RH1 lawfully retains SR3's adverse sign only
as a prospective synchronized-relief hazard. CR1 does not make the rally
broader, retime SR3, or call a bottom. It waits for the environment to administer
a new test: the first sufficiently adverse same-sector pullback after an RH1
action. Only information visible at the completed challenge close is used.

First order: genuine demand should preserve relative leadership when common beta
turns down. Second order: a pullback forces weak tactical holders to reveal
themselves; a subject that stays above its frozen recovery level while peers
fall is less dependent on the original relief impulse. Third order: persistent
relative strength during the challenge can attract capital rotating out of
weaker peers, making subsequent supply less correlated. The falsifier is equally
clear: if top-quartile challenge leadership has no tail or drawdown advantage,
the apparent resilience is merely another safe-late price description.

## 1. Exact construction

The machine source of truth is
`data/personality_timing/challenge_resilience_manifest_v1.json`.

The only source rows are future `relief_hazard` events from the hash-bound
PSS-RH1 ledger. Let the RH1 action be **B**. Historical SR3/RH1-shaped paths are
ineligible.

For the frozen same-sector, ex-self peer set:

- require at least 15 valid peers;
- at B, freeze the shifted prior-126-session 20th percentile of the
  cross-sectional median three-session peer return, with at least 63 valid
  metric sessions;
- search challenge completions C from B+5 through B+20;
- at each C, compute the median peer return `close[C]/close[C-3]-1`; and
- select the first C whose value is negative and at or below the frozen
  percentile. The challenge window is C-2 through C and the action is C close.

A primary path must have no subject intraday breach below the original RH1
reference low minus 0.50 frozen ATR from B+1 through C, and every subject close
during C-2:C must remain at least 0.50 ATR above that reference low.

The subject is a **resilient_leader** only when both are true:

1. its three-session return ranks at or above the 75th percentile of the
   subject-plus-valid-peer cross-section; and
2. it beats the peer median by at least `0.50 × anchor ATR / B close`.

An otherwise identical primary path failing either test is the
**challenged_control**. A path that receives the same peer challenge but loses
the frozen recovery is `failed_hold_diagnostic` and cannot enter inference.

## 2. Prospective firewall and ruler

The source action B and derived action C must both be strictly later than
2026-07-24. The ledger launches with zero events. Nightly is the sole advancer;
rows are keep-first; non-nightly runs cannot scan, append, or grade. No
historical path, retimed challenge, alternate quantile, rank cutoff, relative
return floor, window, or control may be imported after outcomes are observed.

Outcomes begin after C and mature after 63 later sessions: MAE63 and tail10 are
primary; ±31-session proximity/W5/called/tdt and +8% rebound before breach of the
original RH1 frozen low are support. Action-day values never enter forward MAE.

## 3. One-read decision law

No interim outcome analysis is permitted. The sole formal read requires at
least 300 matured primary rows, 150 unique names, 75 rows per primary label,
12 action months spanning 365 calendar days, and 20 exact informative strata.

Inference keeps the first primary action per name-month and matches sector ×
action month × RH1 anchor-severity band × RH1 delay band. Equal-weight stratum
effects use a 10,000-draw within-stratum one-sided permutation test (seed
20260810) and a 5,000-draw three-month moving-block diagnostic interval (seed
20260811).

Positive benefit is pre-defined as leader MAE minus control MAE, control tail
rate minus leader tail rate, leader W5 minus control W5, and leader rebound-first
minus control rebound-first. Qualification requires permutation and block-CI
clean MAE and tail benefit, positive support metrics, positive MAE/tail signs in
early and late halves and every leave-one-sector-out run, and no sector above
25% of leader rows. Any failure kills this exact construction.

## 4. Authority

CR1 is operator research only. It cannot enter, rank, size, gate, alert, display
per-ticker state, or promote itself. Qualification would authorize only a
separate preregistered shadow asking whether CR1 should release or soften an
otherwise active RH1 hazard. It would not validate a bottom or a buy signal.

# D4-01b Stage 0 — deep-discount block reversion falsifier
## Family: `cn_supply_absorption` (REVIVE-AMENDED re-entry; staged)

*Lane: D4-01b Stage 0. Prereg source (frozen at dispatch):*
*`research/SIGNAL_LAB_FRONTIER_DAY4_FABLE_ADJUDICATION_2026-07-08.md` §"D4-01
reassessment" → "Registered re-entry design (D4-01b, staged)". Display-tier study
output — not a production signal; this lane originates no signal keys.*

---

## 0. Frozen pre-registration (gates BEFORE results)

All of the following was frozen in the harness docstring and committed BEFORE any
outcome was computed (see the two-commit receipt in the PR: commit 1 = harness +
this section with results pending; commit 2 = results).

- **Events**: mrtj block-tape rows 2013-01-01+, `premium_ratio <= -0.15`
  (RAW RATIO units, hard-asserted; F5-01 pass-rate + variant-count divergence at
  -0.1, -0.15, -0.2 asserted before any event is accepted);
  episode dedup: 31-calendar-day refractory per ticker (AM-S0-2);
  coverage via `.SH -> .SS` into `data/china_stocks_raw`.
- **Anchoring (AM-S0-1)**: t = first session strictly after block date; path =
  [t, t+10] close-to-close; entry = t+11 (registered family entry);
  forward = 21 sessions from entry (no overlap with the path window).
- **Contrast**: strictly within signal-date. Control pool excludes any ticker with
  ANY tape row in [d-45, d+50] calendar days (AM-S0-4; lookahead leg
  = estimand definition covering the measurement window, flagged as non-tradable).
  Covariates (path, ln 60-bar vol, ln 60-bar median close×volume) (AM-S0-3);
  continuous calipers at 0.5 × per-date cross-sectional SD on ALL THREE
  (AM-S0-5), nearest-3 deterministic, NO relaxation, zero-candidate events
  excluded (rate printed), dates with pool < 100 dropped.
- **Estimands**: per-date long-short m_d; EW mean over dates = DECISIVE; n_d-weighted
  mean printed separately, never conflated (the merged run's undisclosed estimand
  switch is the named failure mode). Newey-West lag 31 (horizon-matched, AM-S0-6).
- **Regimes**: mandatory split at 2023-08-27 (减持新规) by block date;
  pooled full-sample printed NON-decisive only.
- **Minimum-N floor (pre-registered)**: >= 300 matched events AND
  >= 100 distinct signal dates per regime cell; below floor = UNPOWERED,
  no verdict either way.
- **Gate**: cell ALIVE iff floor met AND mean_EW > 0 AND |t_NW| >= 2.0 AND
  BH q <= 0.1 across the powered regime cells. >= 1 powered cell alive ->
  Stage 1 proceeds. No powered cell alive -> **FAMILY CLOSES**. Both cells
  unpowered -> no verdict, lane returns to bench.
- **Stage 1 (pre-declared, runs ONLY if Stage 0 alive)**: flow-intensity DiD;
  treatment intensity = `amt_wan` / event-date free-float recomputed from the price
  store; not-absorbed counterfactual = printed blocks that gave back the print
  (never absence-of-print); decisive term = within-date interaction vs the same
  path split among no-supply names; E1 windows = labeled non-decisive ITT leg only.

---

## RESULTS PENDING

This freeze commit intentionally contains no results. The harness runs next;
results land in the following commit.

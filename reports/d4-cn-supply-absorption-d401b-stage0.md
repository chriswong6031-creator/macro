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

## 1. Store verification (canonical host data plane)

| Check | Value |
|---|---|
| Tape store | `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/china_block_tape` (env `CHINA_BLOCK_TAPE_STORE`; worktrees do not carry the untracked store) |
| mrtj partitions / rows | 22 files / 175,509 rows (2005-01-04..2026-07-06) |
| Duplicate (date,ticker) rows | 0 (asserted 0) |
| Unit assertion | `premium_ratio` RAW ratio: identity vs `cross_price/close - 1` verified; 0 rows <= -15 in raw units; median -0.0399 |
| Known-ticker load check | `000001.SZ` present, 8,894 rows (store resolution proven) |
| Price store | `data/china_stocks_raw`, 1,587 tickers, close+volume |

## 2. Event set (verification-law prints)

| Check | Value |
|---|---|
| Usable rows (2013+) | 165,025 |
| Variant `premium_ratio <= -0.10` | 40,082 rows = 24.29% |
| Variant `premium_ratio <= -0.15` | 13,836 rows = 8.38% |
| Variant `premium_ratio <= -0.20` | 5,692 rows = 3.45% |
| Frozen filter (<= -0.15) pass rate | 13,836/165,025 = 8.38% (F5-01 expectation ~8% — consistent) |
| Variant divergence | monotone 40,082 > 13,836 > 5,692 — asserted |
| Episode dedup (AM-S0-2) | 13,836 -> 7,061 episode-start events |
| Covered after .SH->.SS | 2,334/7,061 = 33.1% |
| Matched events (post caliper) | 1,991 over 1,193 dates |
| Exclusions | invalid covariates/fwd: 90; zero in-caliper candidates: 253; thin-pool dates: 0 |

**Match quality (achieved, not asserted):** |Δpath| mean 1.29pp / median 0.98pp; |Δln vol| mean 0.055; |Δln size| mean 0.143. Event [t,t+10] path mean +0.32pp vs pool mean +1.05pp (descriptive).

## 3. Stage-0 results (gated cells + non-decisive prints)

| Cell | n events | n dates | floor | EW mean | t_NW (EW) | p | BH q | NW-w mean | t_NW (NW-w) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| pre_gui (2013..2023-08-26) | 1,270 | 794 | met | +1.078pp | 1.912 | 0.0559 | 0.077 | +0.750pp | 1.374 | dead |
| post_gui (2023-08-27+) | 721 | 399 | met | +1.136pp | 1.771 | 0.0766 | 0.077 | +1.118pp | 1.639 | dead |
| pooled (NON-decisive) | 1,991 | 1,193 | — | +1.097pp | 2.558 | 0.0105 | — | +0.883pp | 2.06 | — |

Decisive estimand: EW per-date series, NW lag 31. The pooled row exists only
because the prereg mandates printing it as non-decisive (减持新规 changed window-
selection meaning; pooled-regime estimates are not interpretable).

### 3b. Post-freeze sensitivity — overlap-matched NW lag (NON-GATED, zero gate weight)

**Transparency note: this block was added AFTER the gated results above were seen,
and it does not (and cannot) change the frozen verdict.** Motivation: the freeze
set the HAC lag at 31 observations on the premise that the matched per-date series
is near-daily; the realized series is not (matched dates cover roughly one in
three trading days pre-规), so lag-31-in-observation-space over-covers the true
31-trading-day forward-window overlap and widens the SE — conservative in the KILL
direction. The frozen gate stands per prereg discipline; the overlap-matched read
below is for the adjudication record and any future re-registration. Trials
ledger-logged.

| Cell | overlap-matched lag | EW mean | t_NW | p | NW-w mean | t_NW | p |
|---|---|---|---|---|---|---|---|
| pre_gui (2013..2023-08-26) | 17 | +1.078pp | 1.931 | 0.0535 | +0.750pp | 1.425 | 0.1541 |
| post_gui (2023-08-27+) | 18 | +1.136pp | 1.592 | 0.1114 | +1.118pp | 1.514 | 0.1299 |
| pooled (NON-decisive) | 18 | +1.097pp | 2.496 | 0.0126 | +0.883pp | 2.044 | 0.0409 |

## 4. Gate outcome

**No powered regime cell is ALIVE at the frozen ruler. Per the pre-registered
rule, family `cn_supply_absorption` CLOSES.**

The honest shape of this null, stated plainly rather than rounded to zero:
both regime cells are POSITIVE and nearly identical (+1.078pp pre_gui (2013..2023-08-26),
+1.136pp post_gui (2023-08-27+), EW per 21 sessions), both carry BH q = 0.077/0.077
(<= 0.1), and both fail the conjunctive |t_NW| >= 2.0 leg by a modest margin
(t = 1.912 / 1.771). The pooled read — pre-declared NON-decisive because
减持新规 changed window-selection meaning — clears the naive bar (t = 2.558). This is
a close-call null at a deliberately strict pre-registered ruler, not evidence of
a zero or negative premium. Per house law the kill is construction-specific:
what dies is THIS family's Stage-0 claim (a post-path-window 21d reversion
premium clearing |t| >= 2.0 per regime under within-date continuous-caliper
matching). Direction and magnitude are retained as confluence context only.

Consequence per the staged design: Stage 1's budget was conditional on a
Stage-0 ALIVE, so the flow-intensity DiD is NOT run and the family closes.
Re-entry requires a fresh operator-ratified prereg (the post-规 cell roughly
doubles by ~2028 on accrual alone; a longer-horizon or higher-power estimand
would need its own registration) and a DO_NOT_REBUILD-aware adjudication.

This is a pre-registered falsifier outcome, not an exploratory read: the gate,
floors, calipers, estimand choice, and regime split were all frozen before any
outcome was computed.

## 5. Stage 1 status

NOT RUN. The Stage-1 flow-intensity DiD (pre-declared above) runs only on a
Stage-0 ALIVE outcome. Nothing in the Stage-1 design was touched by outcomes.

---

*Report generated by `scripts/d4_cn_supply_absorption_d401b_stage0.py` on
2026-07-08. Store: `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/china_block_tape` (canonical host; env override).
Prices: `data/china_stocks_raw` (.SH->.SS normalized). Trial-ledger rows for the
full Stage-0 cell grid were logged AT GENERATION (family `cn_supply_absorption`) and the
ledger file restored per the intraday data/-discard law; delta in the PR body.
Display-tier study output; no production signal; per house law this text makes no
promotion claims.*

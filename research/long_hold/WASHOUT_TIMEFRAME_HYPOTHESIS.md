# Long-Hold Thesis Layer — PROPOSAL: Washout-Timeframe (technical) feature family

**Status:** PROPOSAL — **NOT LOCKED, NOT RUNNABLE YET.** Opus red-team (2026-07-06) returned CHANGES-NEEDED with three structural blockers (§0). Locking is blocked pending (a) W1 dead-name/price-history maturation and (b) a Fable **masterplan-tier** ruling on multiple feature families vs the same label. This file is preserved as a queued hypothesis + its red-team, not as a live pre-registration.
**Program:** Long-Hold Thesis Layer (`research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`)
**Relationship to W1:** COMPANION to `research/long_hold/OBJECTIVE.md`. W1's frozen feature family (§5) is entirely *fundamental*; that prereg directs new features to a new file (this one). This proposes a *technical* family predicting the SAME `missed_hold` vs `tactical_only` label, reusing W1's labels/ruler/cohorts/split/firewall — **with the deviations the red-team forced (they are NOT verbatim reuses; see §0, M2/N2).**
**FDR family:** `long_hold`; this would register a sub-family `long_hold.washout_tf` — **pending the §0-B3 masterplan ruling on whether a second family vs `missed_hold` is admissible at all.**

---

## 0. Red-team findings — why this is not lockable (Opus, 2026-07-06)

**BLOCKER B1 — the honest cohort cannot support monthly-timeframe features.** Monthly StochRSI (`confluence.py` STOCH_RSI_LEN=14) needs ~34 completed monthly bars (~3 trading years) before its first non-NaN value. The only honest 252d cohort is 2021-07-06 → 2021-10-25 (OBJECTIVE §8) before the 1,165-day Massive gap; of ~3,331 fires there, ~2,750 are Massive-only (entitled only from 2021-07 → ~0–3 monthly bars → `insufficient_history`) and only **~207** have ≥34 monthly bars — *before* name×regime ±10d dedup and the missed_hold/tactical_only split. The monthly features near-certainly fail the n≥25 episode-cluster floor → the study **DEFERS** (per OBJECTIVE §8's survivorship-deferral routing) before it can KILL or SURVIVE. This is a data reality, not a design fix; it means the hypothesis is worth *recording* now but cannot be *run* honestly until W1 PR-G dead-name prices + longer history land.

**BLOCKER B2 — the LH-R1 CI firewall does not enforce feature-circularity.** `check_synapse_reads.py` matches artifact *output paths* (`data/research/long_hold_*`), not feature computation. Washout features are computed from *price* — the same stores the entry harness reads. The CI test ("`entry_strata_phase0.py` never reads `long_hold_*`") passes trivially even if identical monthly-washout code sat on both sides. So the earlier claim "same ingredient, opposite side of the wall, CI-enforceable" is **downgraded/retracted**: the wall guards the label output, not feature reuse. Admitting the operator's own entry vocabulary (washout) as a hold-label predictor therefore needs an explicit ruling, not a CI assertion.

**BLOCKER B3 — masterplan-tier decision required (multiple families + restriction-of-range).** Registering a second 10-hypothesis family against `missed_hold` after W1's family is locked is a garden-of-forking-paths expansion; a self-scoped cross-family flag is insufficient control. It requires a masterplan amendment pre-committing (a) how many families may test `missed_hold`, and (b) a program-wide BH correction across all of them. Compounding it: the fire population is *already* selected on washout being present (the entry stack conditions on it), so these features suffer **restriction-of-range** — the honest test may need a broader population than entry-stack fires, which is itself a masterplan design question. This is Fable's call at the program tier, not a W0-tier self-authorization.

**MAJORS folded into the body below:** M1 monthly/weekly bars must read `.shift(1)` (prior fully-closed bar) or the "completed-bar PIT" claim is false (§3). M2 binary washout flags need Fisher/χ², NOT Mann-Whitney U (degenerate on 0/1) — a real deviation from OBJECTIVE §6.4 (§4). M3 depth features (#5/#6) have a survivorship **sign-flip** risk (missing dead-name traps censor the failures) → any positive depth result on survivor-only data is `direction-untrustworthy-survivorship` and routes to DEFERRED, never SURVIVE (§8). M4 the fire tape's fire-date column is **`date`**, not `fire_date` (§3). N1 the interaction is an allowed single logical AND only if it carries NO fitted cutoff (family m=10). N2 two-sided depth features must spend two-sided alpha (95th/5th), another §6.4 deviation.

**Bottom line:** conceptually sound, but (B1) data-blocked into deferral, (B2) firewall claim retracted, (B3) needs a Fable masterplan amendment. Fixes below make it an HONEST record; they do not make it lockable.

---

## 1. The question (operator-originated)

Does the **completeness / timeframe** of the washout at entry carry information about which tactical wins become multi-year compounders vs the ones that merely bounce and fade? Intuition: a *monthly-timeframe* capitulation (deep, rare, "complete washout" = cycle bottom) more likely begins a durable new cycle (→ `missed_hold`) than a shallow *daily* wobble (→ `tactical_only`). Counter-hypothesis (must be allowed to win): depth alone may mark **structural decline** (falling knife → `cheap_trap`), i.e. timeframe-depth predicts the *wrong* outcome. This is the *technical* analog of W1's *fundamental* kill-test — same `tactical_only` null.

## 2. Reused from `OBJECTIVE.md` (with the §0 deviations)

Labels, 252d/126d ruler, tactical-win = `clean15_126`, honest cohorts + survivorship stamps, temporal split (fit ≤2019 / OOS 2020–2023), the n≥25 episode-cluster floor + cluster-robust CIs, the survivorship-deferral routing, and the wrong-ruler firewall (output path `data/research/long_hold_*`, `horizon_role: hold_thesis`, never an entry surface). **NOT verbatim:** the reshuffle-null test statistic (§4, M2/N2) and the firewall-enforcement claim (§0-B2).

## 3. Population + PIT (corrected)

- Source: `data/research/gate_fires_baskets.parquet`, fire-date column is **`date`** (M4), key `(ticker, date)`; tactical-win + 252d-matured subset; honest cohorts.
- **Per-name** (not the sector/subsector Oracle panel): every feature from the name's own price series (`data/yahoo` primary; Massive post-2021-07), resampled to weekly (`W-FRI`) and monthly (`ME`) bars.
- **PIT law (corrected):** weekly/monthly features read the **prior fully-closed bar** via `.shift(1)` (M1) — the partial current week/month at a mid-period `date` is excluded. `stoch_rsi_kd` (`research/signal_engine/confluence.py`) on the resampled series. A name lacking the max lookback (≥34 monthly bars for the monthly features) → `insufficient_history` (retained for coverage accounting). **Per-feature honest-OOS coverage MUST be tabled in any run** (B1) and a feature below the OBJECTIVE §5 20% coverage floor is dropped-and-documented.

## 4. Proposed FROZEN family `long_hold.washout_tf` (9 marginals + 1 interaction = m=10)

Per-name, PIT at `date`, each with a pre-registered direction. Test statistic per feature TYPE (M2, a deviation from §6.4 that must be stated): **continuous → Mann-Whitney U; binary → Fisher exact / χ²**.

| # | Feature | Type | Definition (prior-closed bar) | Pred. sign vs `missed_hold` |
|---|---|---|---|---|
| 1 | `stochrsi_m_k` | cont | monthly %K, `.shift(1)` | − (more oversold) |
| 2 | `washout_m_active` | bin | monthly %K<20 on ≥2 of last 3 closed monthly bars | + |
| 3 | `washout_w_active` | bin | weekly %K<20 on ≥2 of last 3 closed weekly bars | + |
| 4 | `mtf_washout_count` | ord | # of {2D/3D, weekly, monthly} washed at fire (0–3) | + |
| 5 | `pct_below_200dma` | cont | (close−SMA200)/SMA200 | **two-sided** (durable bottom vs falling knife) |
| 6 | `drawdown_from_52wk_high` | cont | close/52wk-high − 1 | **two-sided** |
| 7 | `ma200_slope_up` | bin | SMA200 20-bar slope ≥ 0 (turning up) | + (disambiguates #5/#6) |
| 8 | `vel_3m_turn` | bin | 3-mo return rising vs 1-mo-prior | + |
| 9 | `base_length_days` | cont | trading days since 52wk high (**left-censoring stamp** N4) | + |
| 10 | `deep_and_turning` | bin | `washout_m_active AND ma200_slope_up` — single logical AND, **no fitted cutoff** (N1) | + |

Reshuffle null per feature (seed 42): one-sided in the predicted direction for signed features; **two-sided (95th/5th)** for #5/#6 (N2). BH-FDR q=0.10 over m=**10**.

## 5. FDR + the B3 gate

BH within `long_hold.washout_tf` (m=10). **This family may not be run until the §0-B3 masterplan amendment pre-commits the total number of families vs `missed_hold` and a program-wide BH correction.** Any within-family pass that would not survive the program-level (fundamental + technical) correction is stamped `program_fdr_marginal=True`.

## 6. Kill criterion + deferral

Same three gates on the honest OOS split; a null KILLS the washout-timeframe thesis (timeframe predicts only the bounce, not the hold) — a valid, loud, publishable finding. **But per B1 the expected first outcome is DEFERRED** (honest-OOS n-floor unmet) → routed to W1 PR-G dead-name spike; W3-analog machinery stays suspended.

## 7. What a PASS would mean

The completeness of the entry washout carries durable-hold information the fundamental family misses → the operator's intuition validated → a *hold-thesis* durable-bottom signal family becomes buildable (W3-analog, gated + firewalled, on a 126/252d clock, via a forward-accrual + earned-authority path mirroring the reversion promotion track). It does NOT license ranking entries (opposite side of the wall) nor a live claim without forward accrual.

## 8. Honest expectations

- **Most likely first outcome: DEFERRED**, not a verdict (B1) — worth recording now (locks design before dead-name prices land) but not runnable honestly until the data matures.
- **Direction genuinely uncertain** for depth (#5/#6): "deeper" cuts both ways. #7/#10 are the pre-registered attempt to resolve it. Be prepared for the honest finding that *raw depth predicts `cheap_trap`* — which would say the operator's "complete washout" intuition needs the *turn-confirmation*, not the depth.
- **Survivorship sign-flip (M3):** among survivors, deep-washout → compounder can be an artifact (the deep-washout failures are the censored dead names). Any positive depth result on pre-2021/survivor-only data is `direction-untrustworthy-survivorship` and routes to DEFERRED, never SURVIVE.

---

*PROPOSAL — records a queued hypothesis + its red-team. Not a locked pre-registration. Requires a Fable masterplan amendment (B3) and W1 data maturation (B1) before it could be locked and run.*

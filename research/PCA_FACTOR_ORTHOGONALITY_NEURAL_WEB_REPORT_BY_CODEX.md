# PCA Factor Orthogonality Research and Neural Web Implementation Report

Prepared by Codex, 2026-07-06.

> **ADJUDICATION NOTE (2026-07-06):** This report was adjudicated in
> `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`.
> The OOS-decay finding in §2.7 was demoted to a small-sample noise artifact:
> within-window null calibration shows a null median of ~0.47 at n=21, versus
> the observed rolling median of 0.5425 (oos_pctile_vs_null median = 0.66 —
> only modestly above chance). §13.5 health bands are replaced by
> null-calibrated bands per RUL-ORTH-8.

Status: research synthesis plus implementation handoff. Additive document only. No scoring, sizing, or execution authority is granted here.

Audience: Fable adjudication, Claude/Sonnet build lanes, Neural Web governance.

Primary source: MIT OCW 18.642 Fall 2024 Lecture 9, "Principal Component Analysis in Finance," guest lecture by Stefan Andreev, whose official MIT slides list prior roles at Morgan Stanley Fixed Income, Citadel Global Fixed Income, and Two Sigma Fixed Income Relative Value.

Local companion artifacts:

- `scripts/research/treasury_pca_diagnostics.py`
- `research/pca_factor_orthogonality/treasury_pca_diagnostics.json`
- `research/pca_factor_orthogonality/treasury_pca_rolling_summary.csv`

---

## 0. Executive Ruling

The useful finding is not "build PCA." The repo already has yield-curve PCA in `engine/yield_curve.py` and documents it in `research/YIELD_CURVE_ENGINE.md`. The useful finding is more institutional:

> Neural Web needs a shared covariance / orthogonality rail that tells every lobe when its evidence is genuinely independent, when it is just a renamed market-mode exposure, and when previously independent factors have become unstable out of sample.

Recommended build:

1. Create a new shared rail: **R-ORTH Covariance and Orthogonality Rail**.
2. Upgrade the existing yield-curve engine with rolling PCA stability, eigenvalue separation, and out-of-sample projection health.
3. Upgrade Dispersion / Selection-Regime Intelligence from simple dispersion/correlation state into eigen-concentration and effective-bets state.
4. Upgrade Factor Intelligence so factor exposures are residualized and de-duplicated before they are allowed to condition committee trust.
5. Add a lobe-level "independent witness" passport so the Neural Web committee can distinguish seven genuinely orthogonal witnesses from seven correlated copies of the same macro bet.
6. Queue, but do not immediately build, a future **Residual Relative-Value Intelligence** lobe. It should be chartered only if R1 replay proves that PC-neutral residual dislocations have persistent forward edge after costs and false-discovery controls.

Do not recommend:

- A new raw yield-curve PCA lobe. That would duplicate an existing engine.
- Massive leverage or PC2/PC3 portfolio trading in production. The lecture's institutional mechanics are useful for measurement; direct leverage is not appropriate without the Liquidity & Execution lobe proving capacity, turnover, financing, and unwind risk.
- PCA as a directional alpha oracle. PCA is unsupervised. It finds structure, not causality.
- Counting factor or lobe badges as diversification. Diversification must be measured through common-mode exposure, residual exposure, and effective independent bets.

The best "supercharge" is not more signals. It is **honest independence accounting**.

---

## 1. Boundaries: What Is Already Built

This report intentionally avoids re-recommending built systems unless the recommendation is an upgrade.

Already built or already chartered:

| Area | Current substrate | This report's treatment |
|---|---|---|
| Yield-curve PCA | `engine/yield_curve.py`, `research/YIELD_CURVE_ENGINE.md`, `data/regime/latest.json["yield_curve"]` | Upgrade with rolling stability and OOS orthogonality diagnostics. Do not rebuild. |
| Neural Web core brain | `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`, `docs/SIGNAL_BUS.md`, active Neural Web artifacts | Add a rail that feeds context and trust annotations. Do not redesign the core. |
| Dispersion lobe | `engine/dispersion.py`, `data/dispersion/regime.json`, `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` | Upgrade the lobe with eigen-concentration and effective-bets metrics. |
| Factor Intelligence | `research/factor_intelligence/NEURAL_WEB_INTEGRATION_DOCKET_FOR_FABLE.md`, factor panels, `factor_intelligence_state` registry | Upgrade from factor context to residual factor context. |
| Final-3 lobe plan | Exit & Trim, Dispersion, Liquidity & Execution selected in `research/NW_FINAL3_LOBE_UPGRADE_PLAN_FOR_CLAUDE_BY_CODEX.md` | Feed those lobes with orthogonality, crowding, leverage, and friction state. |
| Prior quant-fund alpha study | `research/QUANT_FUND_NEURAL_WEB_ALPHA_STUDY.md` | Narrow this report to covariance, PCA, residualization, and trust accounting. |

The build should be additive, display/shadow first, and authority-laddered. Nothing here should move allocation until the existing Neural Web gate discipline proves that it deserves authority.

---

## 2. The Video: What the Citadel / Two Sigma Lecture Actually Teaches

### 2.1 Source and credibility

The user-described video is MIT OCW 18.642 Lecture 9, "Principal Component Analysis in Finance." It is an 83-minute lecture by Stefan Andreev. The MIT slide deck identifies him as a Harvard PhD in Chemical Physics, formerly at Morgan Stanley Fixed Income, Citadel Global Fixed Income, and Two Sigma Fixed Income Relative Value.

Source links:

- MIT OCW lecture page: https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/resources/18642-lecture-9-version-2_mp4/
- MIT slides: https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/mit18_642_f24_lec09.pdf
- MIT transcript: https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/1W7E-UsRG0zyYe1J1vHunh3QNejR5wd7v_transcript.pdf

### 2.2 PCA is structure extraction, not alpha

The lecture's most important discipline is that PCA is unsupervised. It has no outcome variable. It does not prove why a return happened and it does not prove that a factor will pay.

For Neural Web this means:

- PCA belongs first in measurement, trust, de-duplication, and residualization.
- PCA can create research targets, but those targets must go through R1 replay and FDR controls.
- PCA should not become a direct "PC says buy" signal.

This distinction matters because the repo has already killed or clamped many attractive-looking but non-robust factor and rate legs. PCA should respect that culture.

### 2.3 Use changes/returns, not prices/levels

The lecture emphasizes using changes or returns in finance. For rates, that means daily yield changes, not yield levels. For equities, that means returns or residual returns, not prices.

Repo implication:

- The existing `engine/yield_curve.py` does the right thing by decomposing daily curve changes.
- R-ORTH should use lagged return/change matrices and point-in-time artifact alignment.
- Any lobe-level PCA must use frozen, timestamped input matrices, not current labels applied backward.

### 2.4 Demeaning, normalization, and windows are hyperparameters

PCA is sensitive to preprocessing:

- Demeaning is required.
- Volatility normalization changes what PCA means.
- Window length changes factor shape.
- Exponential weighting versus equal weighting changes responsiveness.
- Intraday data can add noise unless the system is explicitly high-frequency.

Repo implication:

R-ORTH should publish more than one lens:

| Lens | Why |
|---|---|
| Raw covariance PCA | Captures where actual variance and risk concentrate. |
| Correlation PCA | Captures co-movement after equalizing series volatility. |
| Shrunk covariance PCA | Reduces sample-noise overreaction. |
| Rolling 6m/1y/2y/5y windows | Separates tactical regime from structural regime. |
| OOS frozen-projection health | Tests whether in-sample orthogonality survives. |

No single PCA setting should be allowed to become a hidden authority source.

### 2.5 Treasury curves really are low-dimensional

The lecture's canonical fixed-income result is the Litterman-Scheinkman decomposition:

- PC1: Level.
- PC2: Slope.
- PC3: Curvature.

In the lecture example, one dominant level factor explains roughly 85-90% of US Treasury yield-change variance, with the first three PCs explaining nearly all usable curve movement.

Local repo replication is directionally consistent:

| Local run | PC1 | PC2 | PC3 | First 3 PCs | Effective dimension |
|---|---:|---:|---:|---:|---:|
| Latest 5y FRED curve changes, 2021-06-16 to 2026-07-01 | 82.28% | 9.70% | 4.27% | 96.25% | 1.45 |
| Latest 2y FRED curve changes, 2024-06-25 to 2026-07-01 | 84.02% | 9.58% | 2.65% | 96.25% | 1.40 |
| Dashboard `latest.json` yield-curve PCA | about 82.44% | about 9.49% | about 4.39% | about 96.32% | not reported there |

The exact PC1 share is lower than a clean "90%" lecture shorthand, but the conclusion survives: the curve has many maturities but few independent modes.

### 2.6 Lower PCs need leverage to matter

The lecture is blunt about institutional reality: PC2/PC3 market-neutral portfolios can be interesting because they are hedged against PC1, but they have lower variance per unit notional. To make them economically meaningful, desks scale them with leverage.

Using the local latest 5y eigen shares as a rough volatility-scaling diagnostic:

- PC2 has about 11.8% of PC1's variance share. Matching PC1 volatility would require roughly `sqrt(0.8228 / 0.0970) = 2.9x` notional.
- PC3 has about 5.2% of PC1's variance share. Matching PC1 volatility would require roughly `sqrt(0.8228 / 0.0427) = 4.4x` notional.

That is not a trading recommendation. It is a governance warning:

> Orthogonal bets are often smaller, more levered, more friction-sensitive, and more vulnerable to unwind/liquidity stress than the broad market mode.

This connects directly to the already selected Liquidity & Execution Realism lobe.

### 2.7 Out-of-sample orthogonality is the real test

In-sample PCs are orthogonal by construction. The hard question is whether next-period data projected onto frozen PCs remains near-orthogonal.

The local diagnostic script projects the next 21 trading days of curve changes onto frozen first-three PCs. Across rolling 2y windows:

- Median next-21d max absolute off-diagonal PC correlation: 0.5425.
- Latest available rolling value: 0.4859.
- Minimum: 0.0768.
- Maximum: 0.9806.

This is not proof that the PCA is useless. Twenty-one-day correlations are noisy. But it does show why Neural Web should not assume "orthogonal in-sample" equals "independent live." OOS orthogonality decay should be a first-class model-health field.

### 2.8 Eigenvalue separation tells you when PCA is trustworthy

The lecture warns that PCA can obfuscate when eigenvalues are not cleanly separated. The local curve diagnostic shows:

- Latest 5y PC1/PC2 eigenvalue gap: large enough to trust the level mode.
- Latest 5y PC3/PC4 gap: about 1.95, much less separated.
- Rolling 2y PC3/PC4 gap median: about 2.06, with a minimum near 1.13.

Practical conclusion:

- PC1 is usually a robust risk mode.
- PC2 is often useful.
- PC3 curvature is meaningful but should carry a stability tag.
- PC4+ should be treated as noise unless a specific market and sample prove otherwise.

### 2.9 Regime shifts matter

The lecture explicitly discusses post-COVID instability and the need to handle regime shifts. Local snapshots show that the curve's PC1 share and effective dimension move materially:

| Snapshot window end | PC1 | PC2 | PC3 | First 3 PCs | Effective dimension |
|---|---:|---:|---:|---:|---:|
| 2019-12-31 | 81.85% | 7.82% | 4.61% | 94.28% | 1.47 |
| 2020-03-16 | 80.90% | 9.45% | 5.09% | 95.45% | 1.50 |
| 2020-04-30 | 79.69% | 10.68% | 5.44% | 95.81% | 1.54 |
| 2021-12-31 | 77.00% | 11.42% | 6.90% | 95.32% | 1.64 |
| 2022-06-30 | 78.11% | 11.91% | 5.23% | 95.25% | 1.59 |
| 2023-10-31 | 80.92% | 10.04% | 5.19% | 96.15% | 1.50 |
| 2026-07-06 nearest local data | 84.02% | 9.58% | 2.65% | 96.25% | 1.40 |

The curve remained low-dimensional, but the relative importance of slope/curvature changed. That is the regime signal.

---

## 3. Adjacent Research: What Else Matters

### 3.1 Litterman and Scheinkman: the fixed-income root

Litterman and Scheinkman's "Common Factors Affecting Bond Returns" is the classic source for the level/slope/curvature result. Its practical contribution is not only naming three factors; it proves that a high-dimensional bond universe can be summarized with a small number of dominant movements.

Neural Web use:

- Keep Treasury PCA as a compact macro-risk map.
- Use it to explain whether the tape is being driven by level shocks, slope shocks, or curvature shocks.
- Do not overfit maturity-specific stories unless the residual after the first three PCs is large and stable.

Source: https://math.nyu.edu/faculty/avellane/Litterman1991.pdf

### 3.2 Diebold-Li: model-based cousin to PCA

Diebold and Li's yield-curve forecasting framework uses Nelson-Siegel factors that map naturally to level, slope, and curvature. This is not the same as PCA, but it reinforces the same intuition: the curve is low-dimensional and those dimensions can be used for forecasting and state estimation.

Neural Web use:

- Treat PCA and Nelson-Siegel as complementary curve-state lenses.
- PCA is purely empirical; Nelson-Siegel is more structured and maturity-aware.
- A future curve upgrade can compare PCA factors against Nelson-Siegel factors to detect when empirical PCs stop matching economically interpretable shapes.

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=461369

### 3.3 Random matrix theory: covariance matrices are noisy

Laloux, Cizeau, Potters, and Bouchaud show that empirical financial correlation matrices contain a large amount of noise. This is deadly for naive PCA because small eigenvalues and unstable eigenvectors can look like tradable discoveries.

Neural Web use:

- Add noise-band / eigenvalue-separation warnings.
- Treat PC4+ as presumed noise unless proved otherwise.
- Prefer shrunk or cleaned covariance for lobe overlap measurement.
- Avoid exposing small-PC "signals" to committee authority.

Source: https://www.cfm.com/wp-content/uploads/2022/12/234-1999-random-matrix-theory-and-financial-correlations.pdf

### 3.4 Ledoit-Wolf shrinkage: sample covariance is not enough

Ledoit-Wolf covariance shrinkage is a portfolio-risk staple because raw sample covariance is unstable, especially when the number of assets or signals is large relative to history length.

Neural Web use:

- R-ORTH should compute sample covariance for transparency but rely on shrunk covariance for governance metrics where feasible.
- The report should publish sensitivity: raw covariance, correlation PCA, and shrinkage PCA should broadly agree before a warning is escalated.

Source: https://www.ledoit.net/honey.pdf

### 3.5 Avellaneda-Lee: residuals are where PCA becomes alpha research

Avellaneda and Lee's statistical arbitrage work uses PCA or ETF factors to strip common components and study residual mean reversion. The key lesson is two-sided:

- Yes, PCA residuals can define relative-value research targets.
- No, this remains permanently live; performance decays, crowding matters, and crisis liquidity can overwhelm the model.

Neural Web use:

- Residual portfolios should enter as R1 research experiments first.
- Any future Residual Relative-Value lobe must prove edge after costs, liquidity, regime, and FDR.
- Residualization should be broadly useful even if residual alpha is not.

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1153505

### 3.6 Meucci: diversification means effective independent bets

Meucci's diversification work reframes portfolio breadth as the effective number of uncorrelated bets, not the count of names or sleeves. This is exactly the Neural Web committee problem.

Neural Web use:

- Replace "7 lobes fired" with "effective independent lobe evidence = 2.4" where appropriate.
- Use entropy or participation-ratio style metrics to communicate concentration.
- Make committee trust conditional on independence, not just count.

Sources:

- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1358533
- https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2276632

### 3.7 Dispersion research: selection opportunity is regime-dependent

Active return opportunity depends partly on cross-sectional dispersion and idiosyncratic risk. The repo already has a Dispersion / Selection-Regime lobe, but PCA adds a deeper version of the same thought:

- High dispersion with low dominant market-mode share supports selection.
- High dispersion with one dominant eigenmode can still be a macro tape in disguise.
- Low dispersion plus high PC1 share means individual signal apparent diversity may be fake.

Neural Web use:

- Upgrade `data/dispersion/regime.json` with `dominant_pc_share`, `effective_dimension`, and eigen-loadings by sector/style.
- Keep gross sizing clamped until `DISP-GATE-1` and any follow-on eigen-dispersion gate pass.

Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1266225

### 3.8 Fed basis-trade research: leverage makes market-neutral fragile

Recent Federal Reserve notes on Treasury cash-futures basis trades and hedge-fund Treasury exposures show that market-neutral relative-value trades can become systemic when they are levered, crowded, and forced to unwind. This is directly relevant to the lecture's "PC2/PC3 needs leverage" lesson.

Neural Web use:

- Treat leverage-adjusted volatility, financing, turnover, and liquidation risk as first-class fields.
- Any residual/relative-value research target must attach a Liquidity & Execution passport before earning authority.
- "Market-neutral" cannot be equated with "low-risk."

Sources:

- https://www.federalreserve.gov/econres/notes/feds-notes/quantifying-treasury-cash-futures-basis-trades-20240308.html
- https://www.federalreserve.gov/econres/notes/feds-notes/decomposing-hedge-funds-u-s-treasury-exposures-20260622.html

---

## 4. Local Evidence From This Repo

### 4.1 Existing yield-curve PCA

`engine/yield_curve.py` already computes a Litterman-Scheinkman style PCA over:

- 3m
- 6m
- 1y
- 2y
- 3y
- 5y
- 7y
- 10y
- 30y

It uses daily yield changes, a 1260-day approximate 5y window, and emits level/slope/curvature loadings into the dashboard-wide yield-curve state.

This is already the right substrate. The missing institutional layer is not the PCA itself; it is trust diagnostics:

- Rolling stability.
- Eigenvalue separation.
- Out-of-sample projection stability.
- Effective curve-bet count.
- Leverage/friction interpretation.

### 4.2 Current curve state

The companion diagnostic script, using local FRED parquet history under `data/fred`, finds:

| Metric | Latest 5y |
|---|---:|
| Window | 2021-06-16 to 2026-07-01 |
| PC1 level share | 82.28% |
| PC2 slope share | 9.70% |
| PC3 curvature share | 4.27% |
| First three PCs | 96.25% |
| Effective dimension, participation ratio | 1.45 |
| PC1/PC2 eigenvalue gap | about 8.49 |
| PC3/PC4 eigenvalue gap | about 1.95 |

Interpretation:

- The level mode is dominant.
- The first three PCs are enough to describe most curve movement.
- The curve is not nine independent bets.
- Curvature exists but needs a stability tag because the PC3/PC4 gap is not huge.
- The current curve environment is even more concentrated than the 2021/2022 windows.

### 4.3 Current dispersion state

`data/dispersion/regime.json` currently reports, as of 2026-07-06:

- `state = lean_in`
- `dispersion_pctile = 0.8`
- `avg_corr = 0.07`
- `gross_mult_live = 1.0`
- `shadow_gross_mult = 1.2`
- Display-only / no measured edge / clamp discipline remains active.

This is exactly where PCA helps. A dispersion percentile and average correlation can say "selection might matter." Eigen-concentration can answer the harder question:

> Is selection genuinely broad, or is the whole universe moving along one hidden axis?

### 4.4 Existing candidate-set effective breadth

`scripts/build_stock_board_v2.py` already contains similarity-based concentration logic via participation-ratio style breadth. That means the repo already understands that count is not breadth.

R-ORTH should generalize this from candidate lists to:

- Lobe evidence vectors.
- Factor exposures.
- Board/universe returns.
- Macro/rates/factor states.
- Committee "independent witnesses."

### 4.5 Existing Factor Intelligence

Factor Intelligence is already being framed correctly as context and de-escalation, not a stock picker. PCA should strengthen that framing by asking:

- Is a name's apparent signal just borrowed from a dominant factor PC?
- Is a factor leader stable or just the current market-mode loading?
- Does a lobe still contribute after market, sector, style, and rate PCs are removed?

The upgrade is residual factor context, not factor alpha resurrection.

---

## 5. Adopt, Modify, Reject

| Finding | Decision | Neural Web translation |
|---|---|---|
| PCA on yield changes finds level/slope/curvature | Adopt | Already built; upgrade with health/stability fields. |
| Dominant PC explains most Treasury variance | Adopt | Use as concentration and market-mode warning. |
| PC2/PC3 portfolios can be market-neutral | Modify | Use as residual research targets; no production leverage without gates. |
| Scale lower-PC portfolios with leverage | Modify heavily | Convert into leverage/friction/capacity passport fields. |
| In-sample PCs are uncorrelated | Reject as sufficient | Require OOS projection health before treating evidence as independent. |
| PCA works better when eigenvalues are separated | Adopt | Publish eigenvalue gaps and noise warnings. |
| Daily data can be cleaner than intraday for non-HFT | Adopt | Keep Neural Web rail daily/end-of-day first. |
| PCA can improve equity market-neutral construction | Modify | Use to de-duplicate factor/lobe evidence and queue residual studies. |
| Illiquid/difficult data can contain opportunity | Modify | Treat as research queue plus liquidity realism, not alpha shortcut. |
| PC4+ or tiny eigenmodes are tradable | Reject by default | Presume noise unless R1 proves otherwise. |
| Factor/lobe count equals diversification | Reject | Replace with effective independent-bets metrics. |

---

## 6. Implementation Recommendation 1: R-ORTH Covariance and Orthogonality Rail

### 6.1 Why a rail, not a lobe

Under the repo's lobe taxonomy, a lobe owns an objective, FDR family, falsifiers, and eventual decision authority. A rail serves all lobes.

PCA/covariance/orthogonality should be a rail first because it should not originate a trade. It should answer:

- Are the lobes saying independent things?
- What common modes are dominating the tape?
- Which signals are residual after common exposures?
- When is a model's in-sample independence unstable out of sample?
- How many effective independent bets does the committee really have?

Suggested name: **R-ORTH Covariance and Orthogonality Rail**.

### 6.2 Objective

R-ORTH provides a shared, point-in-time covariance and residualization state for Neural Web:

1. Common-mode measurement.
2. Lobe de-duplication.
3. Effective independent evidence count.
4. Residual exposure/passport.
5. OOS orthogonality decay warnings.
6. Leverage/friction annotations for low-variance residual bets.

It does not:

- Generate buy/sell recommendations.
- Override a lobe.
- Move sizing.
- Declare alpha.
- Promote a PCA factor without replay.

### 6.3 Proposed files

| File | Purpose |
|---|---|
| `engine/neuralweb/covariance_spine.py` | Core covariance, PCA, residualization, and independence utilities. |
| `scripts/build_covariance_spine.py` | Materializes daily/shadow R-ORTH artifact. |
| `data/neuralweb/covariance_spine.json` | Current compact JSON state for Neural Web, admin UI, and Ask. |
| `data/neuralweb/covariance_spine.parquet` | Historical panel for replay and diagnostics. |
| `research/pca_factor_orthogonality/R_ORTH_PREREG.md` | Display/shadow preregistration and falsifiers. |
| `docs/SIGNAL_BUS.md` | Register `covariance-spine` artifact once built. |
| `site/neuralweb/covariance_spine.json` | Optional static mirror for UI. |

### 6.4 Inputs

Start with artifacts already in the repo:

| Input | Use |
|---|---|
| `data/neuralweb/spine_index.parquet` | Candidate/lobe time series substrate if available. |
| `data/neuralweb/kernel_estimates.parquet` | Lobe/signal effect estimates and uncertainty. |
| `data/neuralweb/confluence_graph.json` | Existing committee confluence structure. |
| `data/neuralweb/factor_intelligence_state.json` | Factor context and exposure state. |
| `data/dispersion/regime.json` | Dispersion state and gross clamp context. |
| `data/regime/latest.json["yield_curve"]` | Rates PCA and curve regime state. |
| `site/factordata/factor_series.json` | Factor returns for residualization. |
| Board/candidate score matrices | Effective breadth and hidden concentration. |

R-ORTH should support missing-input degradation. If a source is absent, the artifact should show `missing_inputs` and lower confidence rather than fail the whole Neural Web build.

### 6.5 Methods

Minimum viable R-ORTH:

1. Align point-in-time daily matrices.
2. Use lagged returns/changes only.
3. Demean each window.
4. Compute covariance PCA and correlation PCA.
5. Compute shrunk covariance where feasible.
6. Compute eigenvalue gaps and effective dimension.
7. Project next-period data onto frozen PCs for OOS orthogonality health.
8. Residualize lobe vectors against common market/sector/style/rate PCs.
9. Report independent evidence count to committee.
10. Emit display-only warnings.

Core formulas:

```text
effective_dimension_pr = (sum(lambda_i) ^ 2) / sum(lambda_i ^ 2)

residual_vector = y - X * inv(X'X) * X' * y

vol_match_notional_multiplier_i = sqrt(lambda_target / lambda_i)

oos_pc_corr = corr(next_period_returns * frozen_eigenvectors)
```

### 6.6 Output schema sketch

```json
{
  "schema": "neuralweb.covariance_spine.v1",
  "as_of": "2026-07-06",
  "display_only": true,
  "authority": "context",
  "source_artifacts": {
    "yield_curve": "data/regime/latest.json#yield_curve",
    "dispersion": "data/dispersion/regime.json",
    "factor_intelligence": "data/neuralweb/factor_intelligence_state.json"
  },
  "blocks": {
    "rates": {
      "window_days": 1260,
      "dominant_pc_share": 0.8228,
      "first3_share": 0.9625,
      "effective_dimension_pr": 1.45,
      "pc3_to_pc4_gap": 1.95,
      "oos_orthogonality_health": "caution"
    },
    "dispersion": {
      "dominant_equity_mode_share": null,
      "effective_universe_bets": null,
      "state": "needs_build"
    },
    "lobes": {
      "effective_independent_lobes": null,
      "overlap_clusters": [],
      "highest_overlap_pairs": []
    }
  },
  "committee_annotations": [
    {
      "type": "concentration_warning",
      "severity": "info",
      "text": "Rates block is low-dimensional; do not count maturity nodes as independent macro witnesses."
    }
  ],
  "allowed_actions": ["display", "explain", "de_escalation_research_only"],
  "forbidden_actions": ["score", "size", "originate_trade"]
}
```

### 6.7 Committee behavior

R-ORTH should add fields like:

- `raw_lobe_count`
- `effective_independent_lobes`
- `dominant_overlap_cluster`
- `shared_market_mode_share`
- `residual_support_score`
- `same_bet_warning`

Example:

```text
Raw: Oracle, Entry, Factor, Dispersion, Options, Short Avoid, Liquidity all agree.
R-ORTH: effective independent witnesses = 2.3 because Entry, Factor, and Options are mostly the same high-beta/high-momentum residual exposure.
Committee action: keep confluence visible, but do not upgrade conviction as if seven independent witnesses fired.
```

This is the Neural Web supercharge. It makes the committee harder to fool.

---

## 7. Implementation Recommendation 2: Upgrade Existing Yield-Curve PCA

### 7.1 Current state

The existing curve engine already emits:

- Level/slope/curvature PCA.
- Variance explained.
- Loadings.
- Curve regime and signal families.
- Display-only discipline.

### 7.2 Missing upgrade

Add a "PCA health" sub-block:

| Field | Why |
|---|---|
| `window_set` | 6m/1y/2y/5y comparison. |
| `pc_loading_turnover` | Detect sudden factor-shape changes. |
| `eigenvalue_gaps` | Detect noisy PC boundaries. |
| `effective_dimension_pr` | Communicate how many independent curve bets exist. |
| `oos_max_abs_pc_corr_21d` | Test live orthogonality decay. |
| `vol_match_multipliers` | Show how levered lower PCs must be to matter. |
| `curvature_stability_tag` | Prevent over-reading unstable butterflies. |
| `regime_snapshot_label` | Compare current covariance state to COVID, 2022 hiking cycle, 2023 bear steepener, etc. |

### 7.3 Build path

1. Fold safe parts of `scripts/research/treasury_pca_diagnostics.py` into `engine/yield_curve.py` or a helper module.
2. Preserve current output contract.
3. Add optional `shape.pca_health`.
4. Add tests that assert:
   - Output exists with enough data.
   - Existing `shape.pca` fields do not drift.
   - Missing maturities degrade cleanly.
   - PC signs are stable.
5. Keep all fields context/display-only.

### 7.4 Why this is high value

Rates touch almost every macro interpretation. A static "level/slope/curvature explains X%" read is useful. A rolling stability read is better:

- It tells Oracle whether rate context is structurally normal or shifting.
- It tells Factor Intelligence when duration/value/growth narratives may be unstable.
- It tells Liquidity & Execution when "market-neutral" curve trades require unrealistic leverage.
- It gives Ask/Cortex a compact reason for why curve commentary should be cautious.

---

## 8. Implementation Recommendation 3: Upgrade Dispersion / Selection-Regime Intelligence

### 8.1 Current state

The current dispersion artifact already answers:

- Is cross-sectional dispersion elevated?
- Is average correlation low?
- Should selection be leaned into in shadow?
- Is live gross still clamped?

This is good. PCA can make it institutional.

### 8.2 Add eigen-dispersion

Add fields:

| Field | Definition |
|---|---|
| `dominant_equity_pc_share` | Share of universe return variance explained by PC1. |
| `effective_universe_bets_pr` | Participation-ratio breadth of eigen spectrum. |
| `sector_pc_loadings` | Which sectors dominate PC1/PC2. |
| `style_pc_loadings` | Whether the hidden mode is value/growth, size, quality, duration, beta, etc. |
| `residual_dispersion_pctile` | Dispersion after removing market/sector/style PCs. |
| `selection_regime_quality` | `macro_mode`, `mixed`, `residual_selection`, or `unstable`. |
| `oos_dispersion_health` | Whether residual dispersion was stable next window. |

### 8.3 Why average correlation is not enough

Average correlation can be low while one hidden mode still dominates part of the universe. Conversely, average correlation can be elevated but residual dispersion can still be meaningful in specific sectors or styles.

Eigen-dispersion answers:

- Is the tape one market bet?
- Are there multiple independent sector/style bets?
- Is idiosyncratic selection actually available?
- Does a high-dispersion state have usable residual breadth?

### 8.4 Gate discipline

This should remain display/shadow until a follow-on gate passes:

Suggested prereg family: `DISP-EIGEN-1`.

Candidate pass tests:

1. `residual_dispersion_pctile` predicts larger cross-sectional spread of forward residual returns.
2. `effective_universe_bets_pr` predicts better realized selection payoff for existing entry/Oracle fires.
3. `dominant_equity_pc_share` flags periods when confluence should be de-duplicated.
4. Lift survives sector, beta, volatility, and liquidity controls.
5. Results survive rolling windows and false-discovery control.

No live gross multiplier should move from this upgrade alone.

---

## 9. Implementation Recommendation 4: Upgrade Factor Intelligence With Residual Context

### 9.1 Current state

Factor Intelligence is already correctly framed as:

- Per-name context.
- De-escalation.
- Borrowed-strength detection.
- Style-regime state.
- Not a stock picker.

### 9.2 Missing PCA/residual layer

Add residual factor coordinates:

| Field | Meaning |
|---|---|
| `market_residual_score` | Name signal after removing broad market PC. |
| `sector_residual_score` | Name signal after removing sector mode. |
| `style_residual_score` | Name signal after removing style factor modes. |
| `borrowed_pc_exposure` | Share of apparent signal explained by common factor PCs. |
| `factor_independent_support` | Factor support remaining after common-mode removal. |
| `factor_overlap_cluster` | Which factor/lobe cluster the name belongs to. |

### 9.3 Committee use

Factor Intelligence should be allowed to say:

- "This name's entry signal is mostly borrowed from the current momentum/duration PC."
- "This name has residual support after market/sector/style removal."
- "This factor panel adds no independent witness; do not count it twice."
- "This factor panel contradicts the entry signal on a residual basis."

This is more valuable than trying to resurrect a broad factor composite.

---

## 10. Implementation Recommendation 5: Lobe Orthogonality Passport

### 10.1 Problem

Neural Web can become overconfident when many lobes fire from the same underlying exposure. Example:

- Oracle likes a rotation.
- Entry likes the chart.
- Factor Intelligence likes style leadership.
- Options flow likes the same high-beta names.
- Dispersion says selection is possible.

That can be five witnesses or one crowded factor bet wearing five badges.

### 10.2 Passport fields

Every lobe output should receive:

| Field | Meaning |
|---|---|
| `common_mode_exposure` | Correlation/loading to market PC1 or relevant block PC1. |
| `sector_mode_exposure` | Loading to sector PC. |
| `style_mode_exposure` | Loading to style/factor PC. |
| `rates_mode_exposure` | Loading to rate level/slope/curvature where relevant. |
| `residual_contribution` | Portion not explained by known common modes. |
| `nearest_lobe_cluster` | Which lobe evidence it duplicates. |
| `independence_weight` | 0 to 1 contribution to effective witness count. |
| `oos_stability` | Whether this independence survived frozen projection. |

### 10.3 Authority ladder

Phase 0: Display only.

Phase 1: De-escalation annotation only:

- "Do not count this as independent confirmation."
- "Treat confluence as crowded."
- "Ask for residual evidence."

Phase 2: Committee trust conditioner:

- Reduce confluence boost when effective independent witnesses are low.
- Increase review priority when independence is high and residual evidence is clean.

Phase 3: Only after replay:

- Permit bounded influence on committee confidence.
- Still no direct origination.

---

## 11. Implementation Recommendation 6: Residual Relative-Value Research Queue

### 11.1 Do not build the lobe yet

The lecture's portfolio construction section naturally tempts a new lobe: PC-neutral relative-value trades. That lobe should not be built immediately.

Reason:

- The repo already has multiple live or planned lobes.
- PCA residual alpha is fragile and crowdable.
- Lower-PC trades often require leverage.
- A residual signal can look beautiful in-sample and collapse after costs.

### 11.2 What to build first

Build an R1 research queue:

| Experiment | Target | Null |
|---|---|---|
| `RORTH-RV-CURVE-1` | PC-neutral Treasury curve residuals mean revert over 5-20d. | Residual z-score has no forward edge net of cost/carry. |
| `RORTH-RV-SECTOR-1` | Sector-neutral equity residuals improve entry quality. | Residual signal adds no lift after existing Entry/Oracle evidence. |
| `RORTH-RV-FACTOR-1` | Factor-PC residual support improves hold/trim decisions. | Residual support does not improve forward drawdown or exit timing. |
| `RORTH-RV-DISP-1` | Eigen-dispersion predicts selection payoff. | Existing dispersion percentile fully explains outcome. |

### 11.3 Future lobe charter, if proven

If the queue passes, charter:

**Residual Relative-Value Intelligence**

Objective:

> Identify when a candidate, sector, curve point, or factor sleeve is mispriced relative to its common-mode exposure, and estimate whether the residual dislocation has favorable forward reversion or continuation after costs.

Allowed authority at first:

- Research context.
- De-escalation.
- Watchlist formation.
- No sizing.
- No standalone buy/sell.

FDR family:

- `residual_rv`

Falsifiers:

- Edge disappears after sector/style/rates residualization.
- Edge disappears after transaction costs and liquidity screens.
- Edge exists only in crisis windows.
- Edge is explained by existing Oracle/Entry/Factor lobes.
- Residual score increases crowding or drawdown without forward return lift.

---

## 12. Implementation Recommendation 7: Leverage and Friction Passport

### 12.1 Why this belongs here

The lecture's lower-PC portfolio idea is inseparable from leverage. The Fed basis-trade research shows why leverage, financing, and unwind risk are not footnotes.

Neural Web should not say "market-neutral" as shorthand for safe.

### 12.2 Fields to add through Liquidity & Execution

| Field | Meaning |
|---|---|
| `vol_match_leverage_required` | Notional multiplier needed to match benchmark volatility. |
| `turnover_to_edge_ratio` | Expected turnover/friction relative to forecast edge. |
| `capacity_score` | Whether realistic size can be held/exited. |
| `liquidity_unwind_risk` | Spread/volume/crowding stress flag. |
| `financing_sensitivity` | Whether cash/repo/funding costs can erase edge. |
| `crowded_rv_warning` | Whether the trade resembles known crowded RV structures. |

### 12.3 Committee use

The committee should be able to say:

- "This looks orthogonal, but the leverage required to matter is too high."
- "This residual signal is clean, but liquidity passport fails."
- "This curve/sector trade is market-neutral in beta terms but not neutral to funding stress."

This directly supports the already selected Liquidity & Execution Realism lobe.

---

## 13. Validation Gauntlet

R-ORTH should not graduate on visual appeal. It needs falsifiable gates.

### 13.1 Data hygiene

Required:

- Point-in-time inputs.
- Lagged feature availability.
- No same-day label leakage.
- Corporate action and universe drift controls where equities are used.
- Complete missing-data policy.
- Separate train/replay/test windows.

### 13.2 PCA stability tests

Required:

- Rolling window sensitivity: 6m, 1y, 2y, 5y.
- Raw covariance versus correlation PCA.
- Sample covariance versus shrinkage PCA.
- Eigenvalue gap report.
- Loading turnover report.
- PC sign/orientation stability.
- OOS frozen projection health.
- Crisis leave-one-out.

### 13.3 Orthogonality tests

Required:

- In-sample PC correlation: sanity check only.
- OOS PC correlation: real health check.
- Lobe residual correlation after common-mode removal.
- Effective independent lobe count.
- Permutation/null distribution for effective breadth.

### 13.4 Alpha research tests

Required before any future residual lobe:

- Pre-registered target, horizon, and null.
- Net-of-cost return.
- Capacity and liquidity filters.
- Rolling regime split.
- Crisis exclusion and crisis-only diagnostics.
- FDR family assignment.
- Comparison against existing Oracle/Entry/Factor evidence.
- Incremental lift, not standalone beauty.

### 13.5 Suggested health bands

Initial display-only bands:

| Metric | Healthy | Caution | Red |
|---|---:|---:|---:|
| PC1/PC2 eigenvalue gap | `> 4` | `2-4` | `< 2` |
| PC3/PC4 eigenvalue gap | `> 2.5` | `1.5-2.5` | `< 1.5` |
| OOS max abs PC corr, 21d | `< 0.25` | `0.25-0.50` | `> 0.50` |
| PC1 loading turnover, 1m | `< 0.005` | `0.005-0.02` | `> 0.02` |
| Effective lobe witnesses | `>= 3` | `2-3` | `< 2` |

These are starting bands, not final authority thresholds. They should be calibrated by replay.

---

## 14. Build Sequence

### PR 1: Research prereg and signal-bus contract

Deliver:

- `research/pca_factor_orthogonality/R_ORTH_PREREG.md`
- Schema stub for `data/neuralweb/covariance_spine.json`
- `docs/SIGNAL_BUS.md` registration draft
- No authority beyond display/context

Exit criteria:

- Fable agrees R-ORTH is a rail, not a lobe.
- Existing yield-curve PCA is acknowledged as built substrate.
- No duplicate factor-alpha recommendation sneaks in.

### PR 2: Yield-curve PCA health upgrade

Deliver:

- `shape.pca_health` fields in yield-curve output.
- Rolling 2y/5y diagnostics.
- Eigenvalue gaps.
- Effective dimension.
- OOS frozen projection health.
- Tests for missing data and output compatibility.

Exit criteria:

- `transmission.html` and `latest.json` still build.
- Existing PCA fields remain backward-compatible.
- Health fields are visibly context-only.

### PR 3: R-ORTH MVP artifact

Deliver:

- `engine/neuralweb/covariance_spine.py`
- `scripts/build_covariance_spine.py`
- `data/neuralweb/covariance_spine.json`
- Compact block-level rates/factor/dispersion/lobe overlap state.

Exit criteria:

- Artifact builds with partial inputs.
- Missing inputs degrade explicitly.
- No lobe reads it for authority.

### PR 4: Committee/admin UI integration

Deliver:

- `effective_independent_lobes`
- `same_bet_warning`
- `dominant_overlap_cluster`
- `residual_support_summary`

Exit criteria:

- UI shows independence annotations without adding in-app tutorial text.
- No layout regression on mobile.
- Ask/Cortex can explain a warning.

### PR 5: Dispersion eigen upgrade

Deliver:

- Equity-universe eigen-concentration.
- Residual dispersion.
- Effective universe bets.
- Sector/style PC loadings.
- `DISP-EIGEN-1` prereg.

Exit criteria:

- Existing `gross_mult_live` remains clamped.
- Display state distinguishes high dispersion from residual selection opportunity.

### PR 6: Residual research queue

Deliver:

- R1 experiment definitions.
- Frozen residualization method.
- Net-of-cost and liquidity protocol.
- Initial null reports.

Exit criteria:

- Only if lift survives, draft future Residual Relative-Value lobe charter.

---

## 15. Highest-Value Implementation Details

### 15.1 Use block-specific covariance

Do not throw every series into one covariance matrix first. Build blocks:

| Block | Matrix |
|---|---|
| Rates | Daily yield changes across maturities. |
| Equity universe | Daily residual returns across board universe / S&P 1500. |
| Sectors | Sector ETF returns or sector residuals. |
| Styles/factors | Factor return series. |
| Lobes | Daily lobe fire/intensity vectors or effect estimates. |
| Options/flow | Lagged flow features, only after leakage controls. |

Then add a top-level summary that explains cross-block relationships.

### 15.2 Publish loadings carefully

Loadings are explanatory, but they can be over-read. UI/API should show:

- Top positive loadings.
- Top negative loadings.
- Stability tag.
- Window.
- Whether covariance or correlation PCA.

Do not show tiny PC4+ loadings as if they are meaningful.

### 15.3 Residualize known exposures before lobe comparison

When comparing lobes, remove obvious common drivers:

1. Market beta.
2. Sector mode.
3. Style/factor mode.
4. Rates mode where relevant.
5. Volatility/liquidity mode if available.

Then ask what remains.

### 15.4 Separate "risk concentration" from "alpha opportunity"

High PC1 share means concentration. It does not automatically mean bad returns.

Low effective dimension means fewer independent bets. It does not automatically mean sell.

Residual dispersion means selection opportunity may exist. It does not prove the existing selector can harvest it.

Every artifact should keep those distinctions explicit.

### 15.5 Use PCA to reduce duplicate confidence

The first live use should be conservative:

- De-duplicate confidence.
- Add caution warnings.
- Explain hidden common exposures.
- Improve review prioritization.

This is safer than immediately trying to create trades.

---

## 16. Fable Adjudication Questions

1. Should R-ORTH be accepted as a rail rather than a lobe?
2. Should `covariance_spine.json` be registered in `docs/SIGNAL_BUS.md` as context-only?
3. Should yield-curve PCA health be added to `engine/yield_curve.py` or kept in a separate helper module?
4. Which artifact should own lobe fire/intensity history for residualization?
5. Should effective independent witnesses be visible on committee/admin surfaces before any replay lift is proven?
6. Should `DISP-EIGEN-1` be a direct extension of `DISP-GATE-1` or a separate gate?
7. What is the minimum evidence needed before drafting a Residual Relative-Value lobe charter?

---

## 17. Final Recommendation

Build the R-ORTH Covariance and Orthogonality Rail.

Upgrade yield-curve PCA, Dispersion, Factor Intelligence, Committee confluence, and Liquidity & Execution around it.

Do not build a new PCA trading lobe yet.

The research from the MIT/Citadel/Two Sigma lecture and adjacent literature is powerful because it teaches how to find independent risk modes, hedge common exposure, and construct residual bets. But Neural Web's highest-value use is more foundational:

> Make the system know when evidence is truly independent.

That will supercharge every lobe more than adding another standalone signal.

---

## 18. Source Index

Primary video and course materials:

- MIT OCW 18.642 Lecture 9, "Principal Component Analysis in Finance": https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/resources/18642-lecture-9-version-2_mp4/
- MIT Lecture 9 slides: https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/mit18_642_f24_lec09.pdf
- MIT Lecture 9 transcript: https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/1W7E-UsRG0zyYe1J1vHunh3QNejR5wd7v_transcript.pdf

Research and adjacent references:

- Litterman and Scheinkman, "Common Factors Affecting Bond Returns": https://math.nyu.edu/faculty/avellane/Litterman1991.pdf
- Diebold and Li, "Forecasting the Term Structure of Government Bond Yields": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=461369
- Laloux, Cizeau, Potters, Bouchaud, "Random Matrix Theory and Financial Correlations": https://www.cfm.com/wp-content/uploads/2022/12/234-1999-random-matrix-theory-and-financial-correlations.pdf
- Ledoit and Wolf, "Honey, I Shrunk the Sample Covariance Matrix": https://www.ledoit.net/honey.pdf
- Avellaneda and Lee, "Statistical Arbitrage in the U.S. Equities Market": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1153505
- Meucci, "Managing Diversification": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1358533
- Deguest, Meucci, Santangelo, "Risk Budgeting and Diversification Based on Optimized Uncorrelated Factors": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2276632
- Gorman, Sapra, Weigand, "The implications of cross-sectional dispersion for active portfolio management": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1266225
- Federal Reserve, "Quantifying Treasury Cash-Futures Basis Trades": https://www.federalreserve.gov/econres/notes/feds-notes/quantifying-treasury-cash-futures-basis-trades-20240308.html
- Federal Reserve, "Decomposing Hedge Funds' U.S. Treasury Exposures": https://www.federalreserve.gov/econres/notes/feds-notes/decomposing-hedge-funds-u-s-treasury-exposures-20260622.html

Repo-local evidence:

- `engine/yield_curve.py`
- `research/YIELD_CURVE_ENGINE.md`
- `data/regime/latest.json`
- `engine/dispersion.py`
- `data/dispersion/regime.json`
- `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
- `research/NW_FINAL3_LOBE_UPGRADE_PLAN_FOR_CLAUDE_BY_CODEX.md`
- `research/factor_intelligence/NEURAL_WEB_INTEGRATION_DOCKET_FOR_FABLE.md`
- `scripts/build_stock_board_v2.py`
- `scripts/research/treasury_pca_diagnostics.py`
- `research/pca_factor_orthogonality/treasury_pca_diagnostics.json`

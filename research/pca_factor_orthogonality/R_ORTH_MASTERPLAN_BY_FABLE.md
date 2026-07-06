# R-ORTH Covariance & Orthogonality Rail — Adjudicated Masterplan

Prepared by Fable, 2026-07-06. Adjudicates `research/PCA_FACTOR_ORTHOGONALITY_NEURAL_WEB_REPORT_BY_CODEX.md` (Codex, same day).

Status: RATIFIED masterplan. Display-only program; no scoring, sizing, or execution authority is granted anywhere in this document.

> **In plain English:** Codex watched an MIT lecture by a former Citadel/Two Sigma quant and concluded the Neural Web's biggest missing piece is not another signal — it is a shared "independence meter" that tells the committee when five lobes agreeing is five real witnesses versus one crowded bet wearing five badges. We agree, with amendments: Codex's headline warning that PCA orthogonality "decays out of sample" turned out to be mostly small-sample noise (an Opus review reproduced it from pure sampling error), and more of the proposed machinery already exists in this repo than Codex realized. What we build is narrower and more honest: health diagnostics on the existing yield-curve PCA, eigen-breadth on the existing dispersion lens, and a new covariance spine that measures — with printed nulls and coverage caveats — how many independent things the Neural Web is actually saying.

---

## 0. Executive ruling

Codex's core ruling is **ADOPTED**: build a rail, not a lobe. No new PCA trading lobe. The rail's job is honest independence accounting.

Three material **AMENDMENTS** from adjudication evidence:

1. **The OOS-orthogonality-decay headline is a noise artifact, not evidence.** Opus review (2026-07-06) reproduced the diagnostic exactly, then constructed the null: at n=21, the max-|off-diagonal| PC correlation statistic has a finite-sample floor of ~0.40–0.71 depending on null construction; a contiguous 21-day slice drawn from *inside* the training window — where decay is impossible by construction — already yields a median of **0.477** against the observed 0.5425. Consequence: every OOS-orthogonality metric this program ships MUST be reported as a percentile against its within-window null, never as a raw threshold. Codex report §13.5 health bands are **REJECTED as written** and replaced (see §4).
2. **Scope is narrowed to the genuine gap.** The census found five existing orthogonality systems Codex's report under-weighted: `engine/reflexivity.py` (participation-ratio breadth over board candidates), `engine/foresight_enb.py` (ENB over 18 themes), `engine/factor_orthogonal.py` (Löwdin factor decorrelation), `engine/factor_exposure.py` (Gram-Schmidt marginal betas), `engine/cross_asset.py` (absorption ratio). The non-duplicative gap is exactly: **live lobe-to-lobe evidence covariance, committee effective-witness accounting, and a cross-block concentration summary**. R-ORTH computes only those; it READS the existing systems' outputs for its cross-block summary and never recomputes them.
3. **The lobe block ships honest-but-sparse.** `spine_index.parquet` engine-day density since 2024 is thin (most engines < 15 active days; only `track_record` is dense). Correlation-based lobe independence is measurable today for only a subset of engine pairs. The artifact prints coverage (`n_lobes_total`, `n_lobes_measurable`, per-pair floors) and emits nulls where density is insufficient — nulls are printed, not hidden. The field accrues value as spine density accrues.

---

## 1. Rulings

**RUL-ORTH-1 (rail, not lobe).** R-ORTH is a rail: `tier: infrastructure` (JSON state) / `tier: display` (any rendered surface), `horizon_role: context`, `owner_program: nw-rails`, `scored_path_surfaces: []`. It never originates a trade, never gates, never ranks, never moves sizing. Answers Codex Q1: YES.

**RUL-ORTH-2 (registration).** `data/neuralweb/covariance_spine.json` (+ compact history parquet) is registered in `config/synapse.yml` as context-only, with `docs/SIGNAL_BUS.md` regenerated via `scripts/gen_signal_bus_doc`. Storage: git (data/neuralweb/ is git-tracked by design). Answers Codex Q2: YES.

**RUL-ORTH-3 (pca_health placement).** Yield-curve PCA health lives **inline** in `engine/yield_curve.py` as an additive optional sub-block `shape["pca"]["pca_health"]`, computed in `pca_decomposition()`. Rationale: no consumer reads into `pca` sub-keys for logic today (census-verified), so the change is purely additive; the module's "never fatal, additive" law carries over. The heavy 45-year rolling harness stays in `scripts/research/treasury_pca_diagnostics.py` (research path). Inline compute is bounded: current-window eigen stats + one comparison window + a small block-resample null (~200 draws on 9×9 matrices — milliseconds). Answers Codex Q3.

**RUL-ORTH-4 (lobe evidence substrate).** `data/neuralweb/spine_index.parquet` is the sole lobe fire/intensity substrate. R-ORTH derives per-engine evidence vectors from it (engine-week direction-weighted fire aggregation to maximize density); no new fire ledger is created. Answers Codex Q4.

**RUL-ORTH-5 (visibility before replay).** Effective-witness fields ARE visible on committee/admin surfaces immediately, as display-only descriptive context with an explicit "descriptive — not gauntleted" label, consistent with the confluence display law (`display_only=true` on every edge). NO trust conditioning, confluence boost/penalty, or committee behavior change until an R1 replay shows lift. Phase ladder: §5. Answers Codex Q5: YES with label.

**RUL-ORTH-6 (DISP-EIGEN-1).** Separate prereg family, NOT an extension of DISP-GATE-1 — but its gate activation is **DEFERRED** until DISP-GATE-1's basis non-stationarity blocker (34.8% expanding-vs-trailing flip rate) is resolved, since any percentile-typed eigen field inherits the same trap. Descriptive eigen fields (`dominant_equity_pc_share`, `effective_universe_bets_pr`, sector loadings) ship now on a **fixed trailing-252d basis only** — no expanding-window percentiles. `gross_mult_live` stays 1.0 regardless. Answers Codex Q6.

**RUL-ORTH-7 (Residual RV lobe bar).** Charter is drafted only if ALL FOUR `RORTH-RV-*` experiments (registered in the prereg, runs deferred) show net-of-cost lift that (a) survives the flat `replay` FDR family, (b) is incremental to existing Oracle/Entry/Factor evidence, and (c) persists outside crisis windows. Until then: no lobe, no build. Answers Codex Q7.

**RUL-ORTH-8 (null-calibration law).** Any orthogonality/stability/decay metric published by this program must carry its within-window null (contiguous-block resample, ≥200 draws) and be displayed as a percentile vs that null. Raw-threshold health bands on small-sample correlation statistics are illegal in this program.

**RUL-ORTH-9 (no recomputation).** Board-candidate breadth stays in `reflexivity.py`; theme ENB stays in `foresight_enb.py`; alpha-candidate overlap stays in `alpha_overlap.py`; factor decorrelation stays in `factor_orthogonal.py`. R-ORTH reads their outputs (declared consumers) for its cross-block summary. Any future consolidation is a separate adjudication.

**RUL-ORTH-10 (leverage/friction).** Only `vol_match_multipliers` (√(λ₁/λᵢ)) ship now, inside `pca_health` and the rates block, as a governance annotation ("orthogonal curve bets need ~3–4× notional to matter"). The full leverage/friction/capacity passport belongs to the Liquidity & Execution lobe program and is NOT built here.

**RUL-ORTH-11 (deterministic annotations).** All committee annotations (`same_bet_warning`, `dominant_overlap_cluster`, concentration warnings) are generated by deterministic rules in the engine. LLM surfaces (Ask/cortex) may quote and explain them; they may never originate or escalate them. Consistent with the LLM de-escalation-only house law.

**RUL-ORTH-12 (factor residual layer deferred).** Codex §9's per-name residual factor coordinates are DEFERRED: the substrate is weak (factor series history ~3y, annual fundamentals, zero FDR survivors) and `borrowed_strength`/`alibi_share_20d` already covers the borrowed-signal question. The factor block in the covariance spine is limited to correlation-PCA over the existing L/S factor return series with an explicit 3y-history caveat.

---

## 2. Evidence base

- **Codex report + local replication:** PC1 82.28% / first-3 96.25% / effective dimension 1.45 on the latest 5y Treasury window — reproduced exactly by Opus review; numbers are trustworthy. Curve-concentration framing ADOPTED.
- **Opus adversarial review (2026-07-06):** leakage CLEAN (PIT-correct rolling/frozen projection); reproducibility FULL; **[major]** OOS metric conflates sampling noise with decay (see Amendment 1); **[minor]** `np.nanmax` silently masks degenerate projection pairs; **[minor]** silent 1981 sample truncation (inner-join on DGS3MO inception) undocumented; **[minor]** `latest_2y` and `snapshots_2y["2026-07-06"]` are byte-identical duplicates. PR-1 fixes all four in the harness and re-runs it.
- **Census, duplication lane:** existing machinery inventory (see Amendment 2). Genuine gaps confirmed: (i) live lobe-to-lobe signal covariance, (ii) cross-lobe IC correlation over gauntlet history, (iii) incremental information of a new lobe vs the registered set, (iv) portfolio-of-lobes effective breadth.
- **Census, NW core lane:** registration recipe verified (synapse.yml required keys, dag-conformance, SIGNAL_BUS byte-freshness, read-gate consumer declarations, LH-R1 exemption via `horizon_role: context`). Confluence today applies **no independence adjustment** — `confirms` lift is a raw co-fire mean difference. That is the committee gap R-ORTH fills descriptively.
- **Census, spine density:** 18 engines all-time; since 2024 only `track_record` is dense (638 active days); most others < 15. Drives Amendment 3.
- **Census, dispersion lane:** DISP-GATE-1 = DEFER (basis non-stationarity 34.8% flip rate; lean_out cohort concentrated in one SPY tercile). Drives RUL-ORTH-6.
- **Census, pipeline lane:** insertion point = engine job NW serial chain (after `build_kernel_estimates`, before `build_confluence_graph`); non-fatal step pattern; blanket `git add data/ site/` covers new artifacts; `config/dag.yml` entry required or dag-conformance hard-fails.

---

## 3. Build waves

Routing law: Sonnet builds, Opus reviews, Fable (main loop) adjudicates and merges. Each PR: builder implements + tests locally → Opus review → fixes → Fable pushes/merges same-day. All work display-only.

### PR-1 — Research record + hardened diagnostics (this branch)
- Commit Codex report + masterplan (this doc) + `R_ORTH_PREREG.md`.
- Fix `scripts/research/treasury_pca_diagnostics.py` per Opus review: add within-window contiguous-block null for the OOS statistic (report observed value AND null median/p90 AND percentile), guard degenerate `nanmax` pairs, document the 1981 truncation in the JSON method block, drop the duplicate snapshot. Re-run; commit refreshed JSON/CSV.
- Exit: script reruns clean; JSON carries the null block; no render-path wiring.

### PR-2 — Yield-curve `pca_health` (engine lane)
- `engine/yield_curve.py`: additive `shape["pca"]["pca_health"]` = `{eigenvalue_gaps, effective_dimension_pr, pc1_loading_turnover_vs_2y, oos_null: {observed, null_median, null_p90, pctile_vs_null}, vol_match_multipliers, curvature_stability_tag, window_set}`. Never fatal; None on insufficient data.
- Tests: extend `tests/test_yield_curve.py` — presence, ranges, backward-compat of existing `pca` keys, graceful degradation, JSON-serializable.
- Exit: existing PCA fields byte-stable; `transmission.html` + `latest.json` build unchanged; all fields context-only.

### PR-3 — Covariance spine MVP (rail lane)
- `engine/neuralweb/covariance_spine.py`: blocks = `rates` (reads `latest.json#yield_curve` incl. pca_health when present), `factors` (correlation PCA over `site/factordata/factor_series.json` L/S series; 3y caveat field), `dispersion` (reads `data/dispersion/regime.json`; eigen fields when PR-5 lands), `cross_asset` (reads absorption ratio artifact if exposed; else omitted with `missing_inputs`), `lobes` (spine-derived engine-week evidence vectors → pairwise correlation with min-floor 30 shared weeks + co-fire Jaccard with min 10 events → greedy |ρ|>0.6 clusters → `effective_independent_lobes` participation ratio over measurable subset + circular-shift null → coverage stats).
- `scripts/build_covariance_spine.py` → `data/neuralweb/covariance_spine.json` + `site/neuralwebdata/covariance_spine.json` + append `data/neuralweb/covariance_spine_history.parquet` (one summary row/day). Missing-input degradation with explicit `missing_inputs` list; never fatal.
- Registration: 2 entries in `config/synapse.yml`, `config/dag.yml` entry, `daily.yml` non-fatal step after `build_kernel_estimates`, regenerate `docs/SIGNAL_BUS.md`.
- Tests: `tests/test_covariance_spine.py` — schema, degradation, determinism, no-authority fields (`display_only: true`, `allowed_actions`/`forbidden_actions` mirror), floors honored.
- Exit: builds with partial inputs; CI registry/dag/read-gate/signal-bus green; no lobe reads it for authority.

### PR-4 — Committee + admin display integration
- `engine/neuralweb/confluence.py`: read `covariance_spine.json` (declared consumer); embed top-level display block in `confluence_graph.json`: `{effective_independent_lobes, n_lobes_measurable, same_bet_warning, dominant_overlap_cluster, descriptive_not_gauntleted: true}`.
- `templates/committee.html.j2`: 6th `.nw-chip` (Independent witnesses) + conditional `.plain-eng` caveat block; bilingual dual-span; no translated `title=`.
- `admin/neural_web.py` + `admin/static/app.js`: additive `independence_note` / `co_fire_cluster` on lobe detail + observatory cards.
- Exit: no mobile layout regression; Ask can explain the warning via `read_artifact` (no whitelist change needed — census-verified); chip renders "—" honestly when unmeasurable.

### PR-5 — Dispersion eigen upgrade (descriptive only)
- `engine/dispersion.py`: additive fields on fixed trailing-252d basis — `dominant_equity_pc_share`, `effective_universe_bets_pr`, `sector_pc_loadings` (top-5 |loading| sectors on PC1/PC2), `residual_dispersion` (CSD after removing top-3 PCs) — via SVD on the T×N return panel (cheap for T=252).
- `research/dispersion/DISP_EIGEN_1_PREREG.md`: gate family registered, activation DEFERRED pending DISP-GATE-1 basis fix; candidate tests as in Codex §8.4 restated with null-calibration law.
- Exit: `gross_mult_live` untouched (invariant test extended); regime.json passthrough verified.

Parallelization: PR-2 ∥ PR-5 (disjoint files) after PR-1; PR-3 after PR-2 merges (reads pca_health); PR-4 after PR-3.

## 4. Health bands (replacing Codex §13.5)

| Metric | Display rule |
|---|---|
| OOS max-abs PC corr (21d) | Show observed + within-window null median/p90 + percentile; "elevated" only above null p90 |
| Eigenvalue gaps (PC1/2, PC3/4) | Descriptive; curvature_stability_tag = "unstable" when PC3/PC4 gap < 1.5 (matches observed rolling min ≈ 1.13) |
| PC1 loading turnover | Descriptive trend only; no bands until 6 months of history accrue |
| Effective independent lobes | Always shown WITH `n_lobes_measurable`/`n_lobes_total`; never as a bare count |

Bands may be promoted to advisory only after ≥6 months of accrued spine history and an R1 replay.

## 5. Authority ladder

- **Phase 0 (this program):** display + explain only. All artifacts carry `display_only: true`, `forbidden_actions: ["score","size","originate_trade","gate","rank"]`.
- **Phase 1 (needs: 3 months accrual + operator review):** de-escalation annotations on committee surfaces ("do not count as independent confirmation").
- **Phase 2 (needs: R1 replay lift, flat `replay` FDR family):** bounded committee trust conditioning.
- **Phase 3:** never origination — permanently.

## 6. Come-back clocks

- 2026-10-06: spine density re-check — is `n_lobes_measurable` ≥ 6? If not, evaluate weekly-aggregation or endorsement-panel substrate.
- 2026-10-06: DISP-GATE-1 basis-fix status → unblock DISP-EIGEN-1 gate activation decision.
- 2027-01-06: Phase-1 de-escalation annotation review (3 months of covariance_spine history).
- RORTH-RV-* runs: on-demand, only via R1 replay registration; no clock.

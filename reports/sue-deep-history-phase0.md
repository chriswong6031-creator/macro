# SUE deep-history re-validation — Phase-0 follow-up

**VERDICT: SUE's scored edge is a SHALLOW-WINDOW ARTIFACT.** A deep 2011→2026 re-validation
(survivorship-**optimistic**) collapses the cross-sectional IC to ~zero. **Recommend demoting
SUE from `scored`** and reviewing the `factors.html` production leg.

> **Update — now shipped at the DATA level.** The demotion is done (SUE → `display`), and the
> whole factor zoo's `ic_scorecard.json` is now regenerated on this deep panel via
> `scripts/factor_ic_scorecard.py --deep` (`engine.equity_factors._closes("deep")`): span
> 2011-2026, 60 quarters, ~1,154 names. SUE no longer surfaces as an FDR survivor in the live
> panel (IC ≈ 0); the lone, marginal, survivorship-biased survivor is now `payout` (q 0.072) —
> shown, not promoted. FINRA short-interest is dropped from the deep panel (no point-in-time
> history). So `factors.html` / `signal_lab.html` are honest at the data level, not just in prose.

`DATA_SIGNAL_EXPANSION_2026.md #5` called the deep + PIT-survivorship re-validation "the
honest follow-up." This run did it: `scripts/sue_deep_phase0.py` backfilled max-history
adjusted closes for the 1,317-name EPS universe (1,313 fetched, 1,113 with >10y →
`data/edgar/sue_deep_closes.parquet`) and re-ran the SUE rank-IC / IC-IR / HAC-t /
quintile-L/S over 2011-2026 with the SAME `engine.sue.sue_cross_section` + `rank_ic` /
`ic_summary` the production scorecard uses. The only thing that changed is the price window.

## The result — the edge disappears with depth

| window | quarters | names/q | mean IC | IC-IR(ann) | HAC t | hit | L/S Sharpe |
|---|--:|--:|--:|--:|--:|--:|--:|
| shallow 2023-2025 (production `ic_scorecard.json`) | 11 | ~842 | 0.0380 | 1.24 | 2.85 | 0.82 | 1.45 |
| **deep 2011-2026 (this run)** | 61 | ~1039 | **0.0005** | **0.016** | **0.061** | 0.517 | **0.094** |

Over 15 years SUE's IC is **indistinguishable from zero** (HAC t 0.06), the quintile L/S
Sharpe is ~0, and the hit-rate is a coin flip. The 2023-2025 sub-window (the source of the
production IC 0.038) sits INSIDE this deep window, so the full-period null means SUE
"worked" only in that recent ~2.5y stretch — textbook post-publication PEAD decay
(McLean-Pontiff).

## Why this is a STRONG (not weak) negative

The deep panel is **survivorship-biased TOWARD an edge** — yahoo serves only currently-listed
tickers, so delisted names are absent. Survivorship bias *inflates* apparent factor returns,
yet even with that thumb on the scale the IC is ~0. A clean, delisting-recovered panel would,
if anything, look worse. So the null is robust to the one bias that runs in SUE's favour.

## Caveats (honest)
- Survivorship-biased universe (optimistic) — strengthens, not weakens, the negative.
- Identical SUE construction + validation primitives as production; only the window changed
  (2.5y → 15y). So this is a like-for-like deepening, not a different test.
- Cached: `data/edgar/sue_deep_closes.parquet` (re-runs instant); verdict
  `data/edgar/sue_deep_phase0.json`.

## Recommendation (operator decision)

**Demote SUE `scored` → `display`/`confirmer` on `signal_lab`, and stop scoring it on
`factors.html`** until a clean deep panel says otherwise. This is a production + tested-
invariant change (`test_sue_is_a_scored_positive_fdr_survivor` asserts SUE is the scored
win), so it is **flagged for the operator** rather than flipped unilaterally in this PR; the
SUE row's prose carries the caveat in the interim. If kept, frame SUE explicitly as a
recent-regime signal, not a validated standalone alpha.

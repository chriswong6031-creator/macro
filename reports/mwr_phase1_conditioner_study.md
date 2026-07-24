# MWR phase-1 — mechanism panel + conditioner study

Universe: 1630 US names with full 2014→2026 history (≥4 signals each); 27,647 signals pooled. Uplift = median signal fwd63 − the name's OWN all-days median fwd63 (base-rate removed per name).

## H-M — does the edge live on secular-uptrend personalities?

Spearman rank-corr(uplift, trend-persistence) = **+0.066** (n=1630).

| trend tercile | names | median uplift | mean uplift |
|---|---|---|---|
| chop/decline | 547 | -0.59% | -0.08% |
| mid | 541 | +0.03% | +0.14% |
| strong trend | 542 | +0.58% | +0.56% |

Reference uplifts: MAG7-EW **+5.74%** · MCD -0.03% · COST -2.91%

## H-C — the accelerating-tightening conditioner (operator's 2022 narrative)

| regime at signal | signals | median excess fwd63 |
|---|---|---|
| cutting | 5993 | +2.44% |
| flat | 10388 | -1.05% |
| hike_accel | 6059 | -1.02% |
| hike_decel | 5207 | +1.98% |

hike_accel − rest, median-excess difference: point -1.61%, 95% month-cluster CI [-5.08%, +1.61%] (includes 0).

Applied to the MAG7 census: veto removes ['2018-05-04', '2022-03-18', '2022-06-24', '2022-11-11'] — and nothing else.

## Haircut fix — max-statistic family null (replaces Bonferroni ×5)

S1-A median excess +5.1% vs family max-stat null: **p = 0.143** (was 0.048 raw / 0.238 Bonferroni — the ×5 was over-conservative; this is the honest family-wise number).

# Flow Observatory W5 — descriptive method evaluation + threshold calibration

`prereg: research/flow_observatory/W5_PREREG.md` · `seed: 20260903` · `wall_time_s: 54.6` · `generated_at: 2026-09-03T18:36:14.036836+00:00`

Report only — no method/threshold/engine change was applied by this run. Selection is reserved for the Fable principal against the frozen §5 decision rule.

## Candidates
- **M0** — incumbent slope_z (#3561)
- **M1** — winsorized slope_z
- **M2** — median/MAD location-scale
- **M3** — causal percentile -> probit

## Lens: themes (n_entities=22, n_sessions=306)

### Metric 1 — state distribution (share of sessions, pooled)
| state | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| above norm, rising | 0.244 | 0.239 | 0.204 | 0.131 |
| above norm, cooling | 0.078 | 0.079 | 0.138 | 0.191 |
| near its norm | 0.322 | 0.318 | 0.374 | 0.398 |
| below norm, worsening | 0.243 | 0.248 | 0.180 | 0.132 |
| below norm, easing | 0.112 | 0.116 | 0.104 | 0.148 |
| degeneracy alarm | False | False | False | False |

### Metric 2 — one-day flip rate
| | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| pooled | 0.1865 | 0.1852 | 0.6833 | 0.6712 |
| per-entity median | 0.1769 | 0.1769 | 0.6798 | 0.6696 |

### Metric 3 — persistence (median non-neutral run length, sessions)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 3.0 | 3.0 | 2.0 | 2.0 |

### Metric 4 — outlier sensitivity (max|Δv| on a +/-5σ spike fixture)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 1.008 | 0.7145 | 4.764 | 3.3792 |

### Metric 5 — quiet-series behavior (max|v| on a 60-session near-zero-variance fixture)
| | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| max\|v\| | 0.0685 | 0.0635 | 0.1822 | 2.4118 |
| alarm | False | False | False | True |

### Metric 6 — coverage sensitivity (themes only; 20% member drop, 100 draws, median |Δv|)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 0.1461 | 0.1451 | 0.1187 | 0.1211 |

_themes evaluated: 22_

### Metric 7 — revision sensitivity (median |Δv|, fallback ±10% std, 40 draws)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 0.0196 | 0.02 | 0.0625 | 0.0559 |

### Metric 8 — concordance vs M0 (pooled median Spearman rho)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 1.0 | 0.9944 | 0.1858 | 0.1842 |

### §4 threshold sweep — M0 grid winner-by-objective
Winner: tau=0.75 beta=30 — main-window neutral_share=0.549 flip_rate=0.1645 in_reach=0.1438 out_reach=0.3072
Held-out (60 sessions) at the winning (tau,beta): neutral_share=0.6333 flip_rate=0.1356
Incumbent (tau=0.5, beta=25): main-window neutral_share=0.3529 flip_rate=0.1711

## Lens: names (n_entities=1520, n_sessions=306)

### Metric 1 — state distribution (share of sessions, pooled)
| state | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| above norm, rising | 0.275 | 0.272 | 0.187 | 0.140 |
| above norm, cooling | 0.107 | 0.106 | 0.132 | 0.168 |
| near its norm | 0.308 | 0.310 | 0.384 | 0.403 |
| below norm, worsening | 0.220 | 0.222 | 0.179 | 0.133 |
| below norm, easing | 0.089 | 0.091 | 0.118 | 0.157 |
| degeneracy alarm | False | False | False | False |

### Metric 2 — one-day flip rate
| | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| pooled | 0.172 | 0.174 | 0.6529 | 0.6465 |
| per-entity median | 0.1698 | 0.1698 | 0.6529 | 0.6468 |

### Metric 3 — persistence (median non-neutral run length, sessions)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 4.0 | 4.0 | 2.0 | 2.0 |

### Metric 4 — outlier sensitivity (max|Δv| on a +/-5σ spike fixture)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 1.1068 | 0.9192 | 5.0813 | 0.2642 |

### Metric 5 — quiet-series behavior (max|v| on a 60-session near-zero-variance fixture)
| | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| max\|v\| | 0.0923 | 0.0943 | 0.1294 | 1.9808 |
| alarm | False | False | False | True |

### Metric 7 — revision sensitivity (median |Δv|, fallback ±10% std, 40 draws)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 0.0214 | 0.0221 | 0.0703 | 0.0616 |

### Metric 8 — concordance vs M0 (pooled median Spearman rho)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 1.0 | 0.9937 | 0.1774 | 0.1752 |

### §4 threshold sweep — M0 grid winner-by-objective
Winner: tau=0.3 beta=15 — main-window neutral_share=0.6078 flip_rate=0.0921 in_reach=0.281 out_reach=0.1111
Held-out (60 sessions) at the winning (tau,beta): neutral_share=0.45 flip_rate=0.0847
Incumbent (tau=0.5, beta=25): main-window neutral_share=0.9216 flip_rate=0.0658

## Lens: southbound (n_entities=1, n_sessions=2706)

### Metric 1 — state distribution (share of sessions, pooled)
| state | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| above norm, rising | 0.307 | 0.310 | 0.260 | 0.176 |
| above norm, cooling | 0.126 | 0.127 | 0.091 | 0.162 |
| near its norm | 0.158 | 0.147 | 0.347 | 0.356 |
| below norm, worsening | 0.281 | 0.285 | 0.199 | 0.166 |
| below norm, easing | 0.128 | 0.131 | 0.103 | 0.140 |
| degeneracy alarm | False | False | False | False |

### Metric 2 — one-day flip rate
| | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| pooled | 0.1072 | 0.1052 | 0.5223 | 0.527 |
| per-entity median | 0.1072 | 0.1052 | 0.5223 | 0.527 |

### Metric 3 — persistence (median non-neutral run length, sessions)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 7.0 | 8.5 | 2.0 | 2.0 |

### Metric 4 — outlier sensitivity (max|Δv| on a +/-5σ spike fixture)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 1.1015 | 0.6387 | 5.8345 | 3.2035 |

### Metric 5 — quiet-series behavior (max|v| on a 60-session near-zero-variance fixture)
| | M0 | M1 | M2 | M3 |
|---|---|---|---|---|
| max\|v\| | 0.3749 | 0.3917 | 0.4073 | 2.4118 |
| alarm | False | False | False | True |

### Metric 7 — revision sensitivity (median |Δv|, fallback ±10% std, 40 draws)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 0.0086 | 0.0101 | 0.0363 | 0.0219 |

### Metric 8 — concordance vs M0 (pooled median Spearman rho)
| M0 | M1 | M2 | M3 |
|---|---|---|---|
| 1.0 | None | None | None |

### §4 threshold sweep — M0 grid winner-by-objective
Winner: tau=1.0 beta=None — main-window neutral_share=0.3123 flip_rate=0.0732 in_reach=0.3831 out_reach=0.3046
Held-out (60 sessions) at the winning (tau,beta): neutral_share=0.35 flip_rate=0.1017
Incumbent (tau=0.5, beta=None): main-window neutral_share=0.1562 flip_rate=0.0757

## §5 decision-rule condition table (facts only — no selection made here)

### themes
| challenger | (a) outlier/quiet improve >=30% | (b) flip rate not worse >10% | (c) concordance >=0.8 | (d) no degeneracy | ALL CONDITIONS MET |
|---|---|---|---|---|---|
| M1 | False | True | True | True | False |
| M2 | False | False | False | True | False |
| M3 | False | False | False | True | False |

### names
| challenger | (a) outlier/quiet improve >=30% | (b) flip rate not worse >10% | (c) concordance >=0.8 | (d) no degeneracy | ALL CONDITIONS MET |
|---|---|---|---|---|---|
| M1 | False | True | True | True | False |
| M2 | False | False | False | True | False |
| M3 | True | False | False | True | False |

### southbound
| challenger | (a) outlier/quiet improve >=30% | (b) flip rate not worse >10% | (c) concordance >=0.8 | (d) no degeneracy | ALL CONDITIONS MET |
|---|---|---|---|---|---|
| M1 | True | True | None | True | True |
| M2 | False | False | None | True | False |
| M3 | False | False | None | True | False |

## Deviations / interpretive notes

- M3's frozen formula ('v_t = 2x(percentile_rank-0.5) mapped via probit') is mathematically undefined for rank<0.5 if read literally (norm.ppf's domain is (0,1); 2x(rank-0.5) ranges (-1,1)). Implemented as v_t = norm_ppf(rank) directly -- the only reading under which the construction is defined for all sessions. Flagging for principal confirmation before any production use.
- M3 has no vol/scale denominator, so 'floored identically' (§2) has no literal referent there; interpreted as no-op for M3.
- M2's '0.25x expanding floor applied to the MAD scale' is implemented by reusing the SAME expanding-std reference series M0 already computes (rather than a separately-computed expanding MAD), since 1.4826*MAD approximates std for a roughly-normal series and this keeps the floor construction identical to M0's own.
- Sec 4 says to sweep thresholds 'for the winning method (and M0 if it wins)', but the harness does not select a winner (reserved to the principal per §5). The full (tau,beta) grid was computed for ALL FOUR candidates on every lens -- a strict superset of 'the winning method', so this cannot bias which method the sweep favors.
- Sec 4's breadth-tilt sweep is written for the sector-breadth gauge (themes-native). Generalized: themes and names lenses each sweep (tau,beta) jointly over their own cross-sectional breadth-tilt state; southbound (n=1, no cross-section) sweeps tau only against its own entity state series, with beta reported not applicable.
- Metric 7's ledger check found data/flow_observatory/observations.parquet not yet materialized in this tree and no separate desk-revision-magnitude ledger for flow_hist/southbound raw inputs, so the frozen fallback applies: perturbation magnitude = +/-10% of each entity's own series std.
- Metric 6 (coverage sensitivity) is themes-lens only per the frozen metric text ('themes lens, 100 draws') -- not computed for names or southbound, where the concept of dropping 'members' does not apply.
- Metric 8 (concordance) is frozen as 'rank correlation of THEME orderings' -- generalized here to the names lens too (an analogous cross-sectional rank correlation across ~1,500 names), reported as its own number rather than folded into a single cross-lens figure. Southbound (n_entities=1) has no cross-section to rank at all, so concordance -- and therefore Sec 5 condition (c) -- is reported as not-applicable there rather than a silent False that would veto every southbound challenger regardless of its actual behavior.
- Metric 7 (revision sensitivity) on the names lens (~1,500 scored tickers) seeded-subsamples to 250 entities before drawing perturbations -- a pure performance measure (running the frozen fallback on every name at full draw count measured at several minutes; batching the compute, see the metric's own docstring, brought this down but the entity count is still capped so the harness stays inside its <10min budget). The pooled median over 250*40 name/draw pairs is reported as the names-lens figure; themes (22) and southbound (1) use their full entity pool.

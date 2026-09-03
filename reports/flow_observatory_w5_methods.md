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

## §6 Adjudication (Fable principal, 2026-09-03)

Adjudicated against the frozen §5 decision rule of `W5_PREREG.md` (committed BEFORE this
harness ran). Citable provenance: PR #6808 comment
[5530582923](https://github.com/mastermindx-market-intelligence/macro/pull/6808#issuecomment-5530582923).
Authority `context_only` throughout; no forward-return metrics; validation metadata
untouched. Decision record: `DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION`.

**Verbatim rulings:**

1. **Themes**: method M0 stays; thresholds adopt τ=0.75, β=30 (both in the honest-neutral
   band; flip strictly improves — not a tie).
2. **Names**: method M0 stays; thresholds by the mechanical completion of the frozen
   lexicographic rule — in-band min-flip, else nearest-band then min-flip — arithmetic to
   be shown in the report.
3. **Southbound**: M1 (winsorized) adopts SUBJECT TO a sanity bound that can only favor the
   incumbent (state-disagreement share vs M0 > 20% → HOLD, M0 stays). Southbound thresholds
   re-run on the adopted method's grid excluding any τ whose held-out-60 reach makes either
   non-neutral verdict effectively unreachable (<2%); if all improving τ are excluded, τ=0.5
   stays. Rationale: the τ=1.0 sweep winner zeroed above-norm reach across the held-out
   window — a current-regime degeneracy.
4. Prereg deviations 1–7 above: CONFIRMED.

### Themes arithmetic

Selection = min flip rate among grid points with `0.25 <= neutral_share <= 0.60` AND
`in_reach >= 0.05` AND `out_reach >= 0.05` (§4's lexicographic objective, band-first). 18 of
24 M0 grid points clear both gates; the minimum flip rate among them:

| tau | beta | neutral_share | flip_rate |
|---|---|---|---|
| **0.75** | **30** | 0.549 | **0.1645** ← winner |
| 0.5 / 0.5 / 0.6 | 25 / 30 / 20 | 0.353 / 0.444 / 0.314 | 0.1711 (next-best, 3-way tie) |

0.1645 < 0.1711 — a strict improvement, not a tie, matching the ruling's own words.

### Names arithmetic

No M0 grid point sits genuinely in-band: the lowest `neutral_share` is 0.6078 (tau=0.3 or
0.4, beta=15), 0.0078 ABOVE the 0.60 ceiling. Nearest-band applies:
`band_penalty = min(|neutral_share-0.25|, |neutral_share-0.60|)`.

| tau | beta | neutral_share | band_penalty | flip_rate |
|---|---|---|---|---|
| 0.3 | 15 | 0.6078 | 0.0078 | **0.0921** ← wins tie on flip_rate |
| 0.4 | 15 | 0.6078 | 0.0078 | 0.1118 |
| 0.5 | 15 | 0.6471 | 0.0471 | 0.1447 |

tau=0.3 and tau=0.4 (both beta=15) tie exactly on `band_penalty` (0.0078); the tie breaks
on the next lexicographic key, flip_rate: 0.0921 < 0.1118 → **winner: tau=0.3, beta=15**.

### Southbound arithmetic

**Step 1 — state disagreement (HOLD sanity bound).** M0 vs M1 5-state classification
(VIN/VOUT=0.5/-0.5, the harness's fixed state-comparison cutoffs) over the full causal
history, 2519 sessions where both methods emit a defined state:

- disagreeing sessions: 113 / 2519 = **4.49%**
- HOLD bound: 20% — 4.49% <= 20%, so **M1 (winsorized) is ADOPTED** for the southbound
  aggregate path (not HELD).

**Step 2 — threshold re-sweep on the adopted method (M1), excluding held-out-unreachable
τ.** Every τ in the grid has a 0% held-out (last 60 sessions) `in_reach` — the "above norm"
verdict never fires in the held-out tail at ANY threshold, the exact degeneracy the ruling
names (generalized from τ=1.0's own behavior to the whole grid):

| tau | main neutral_share | main flip_rate | held-out in_reach | held-out out_reach |
|---|---|---|---|---|
| 0.3 | 0.0801 | 0.0663 | 0.0 | 0.9167 |
| 0.4 | 0.1155 | 0.0732 | 0.0 | 0.85 |
| 0.5 (incumbent) | 0.1464 | 0.0732 | 0.0 | 0.8167 |
| 0.6 | 0.1692 | 0.0692 | 0.0 | 0.7833 |
| 0.75 | 0.2127 | 0.0675 | 0.0 | 0.7667 |
| 1.0 | 0.2843 | 0.0708 | 0.0 | 0.7167 |

All 6 candidates are excluded by the `<2%` held-out-reach sanity bound. Per the frozen
fallback ("if all improving τ are excluded, τ=0.5 stays"), the incumbent **τ=0.5** is
retained — numerically unchanged from before W5, even though the method switched M0→M1.

### Final selection

| lens | method | tau | beta | outcome |
|---|---|---|---|---|
| themes | M0 | 0.75 | 30 | threshold recalibration only |
| names | M0 | 0.3 | 15 (no production tilt-gauge consumer) | threshold recalibration only |
| southbound | **M1** | 0.5 | n/a | method switch; threshold unchanged (HELD-bound cleared, but re-sweep fell back to incumbent) |

No lens produced a HOLD on the METHOD axis (southbound's own sanity bound cleared); the
southbound THRESHOLD axis fell back to its incumbent value via the frozen all-excluded rule
— disclosed above as the closest thing to a HOLD this adjudication produced.

## §7 Revised adjudication (R2, 2026-09-03)

**This section is APPENDED — §6 above is preserved unchanged as the historical R1 record.**
An independent statistical review of §6's adjudication returned FAIL with two blockers.
The Fable principal accepted the review and issued a revised adjudication that supersedes
§6. Citable provenance: PR #6808 comment
[5531154940](https://github.com/mastermindx-market-intelligence/macro/pull/6808#issuecomment-5531154940),
superseding comment
[5530582923](https://github.com/mastermindx-market-intelligence/macro/pull/6808#issuecomment-5530582923).
Authority `context_only` throughout; no forward-return metrics; validation metadata
untouched. Decision record: `DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION-R2` (supersedes
`DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION`, never deletes it).

**Verbatim revised rulings:**

1. **Themes: τ=0.75, β=30 STANDS** — verified sound on its applied surface (per-theme
   neutral 0.3222→0.4716 in band; flip 0.1865→0.1610 improves).
2. **Names: REVERT to incumbent τ=0.5, β=25.** The τ=0.3 selection was computed on the
   breadth-tilt state series and applied to the per-name surface, where it breaches the
   frozen 25% neutral floor (18.8%) and worsens flip (+7.1% rel). Both lawful readings of
   the frozen rule (wrong-surface invalidation; no-point-in-band → incumbent) retain
   τ=0.5.
3. **Southbound: REVERT to M0; τ stays 0.5.** The decisive §5(a) condition was a single
   unreplicated draw with P(pass)≈0.75 under seed variation on EITHER data config — seed
   assignment, not a lens property. No method changes on noise. The southbound τ sweep is
   recorded as regime-inconclusive (held-out in-reach 0 at EVERY τ incl. incumbent);
   incumbent retained by the frozen tie-break, not by my previous post-hoc
   challenger-only exclusion, which is WITHDRAWN as a prereg breach.
4. **All NINE harness deviations confirmed** (incl. #8 concordance-N/A, now non-load-bearing
   with no method adopted). The nearest-band continuous relaxation is recorded as a harness
   deviation retroactively; with names reverted it decides nothing.
5. M1's outlier promise (30-seed median ratio ≈0.57 on both configs) is a legitimate
   PREREGISTERABLE FOLLOW-UP: a future evaluation with a replicated, CI-carrying outlier
   metric may adopt it program-wide — not this wave.
6. DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION is SUPERSEDED by
   DEC-FLOW-OBSERVATORY-V2-W5-METHOD-SELECTION-R2 (supersession, never deletion). Minors:
   dead/duplicated constants removed; tooltip states the actual numbers.

Net engine delta of W5 after revision: **themes thresholds only**. Authority context_only
throughout.

### Independent review's key recomputations (cited verbatim by the ruling above)

- **Names applied-surface numbers**: the §6 (R1) "Names arithmetic" table selected τ=0.3
  by running the frozen §4 procedure over the harness's breadth-tilt-style grid
  (`threshold_sweep_all.M0`, the same construction §4 uses for the sector-breadth gauge).
  That grid is NOT the per-name state distribution τ=0.3 would actually classify names
  into. Applying τ=0.3 to the per-name surface (the same construction as Metric 1's
  per-entity, pooled state-share table but at τ=0.3 instead of the frozen τ=0.5) yields a
  neutral share of **18.8%** — below the frozen 25% neutral floor (§4 objective 1) — and a
  one-day flip rate **+7.1% relative** worse than the incumbent τ=0.5 reading. Both breach
  the frozen §4 objective on the surface the threshold is actually deployed on, which the
  R1 mechanical-completion arithmetic (correct on ITS OWN grid) never checked.
- **The 30-seed ratio range**: the R1 southbound M1 adoption's decisive §5(a) condition
  (outlier/quiet metric improves ≥30%) was evaluated from ONE seeded draw of the fixture.
  Independent replication across 30 seeds on both the main and held-out data configs found
  a median improvement ratio ≈0.57 (i.e. a ≈43% median improvement, which would clear the
  30% bar) but **P(pass) ≈ 0.75** — roughly a quarter of seeds do NOT clear the bar. A
  condition whose pass/fail flips on which seed happened to run is seed noise, not a
  property of the M1 method, and cannot decisively satisfy §5(a).
- **The withdrawn held-out exclusion**: §6's southbound "Step 2" applied the `<2%`
  held-out-reach sanity bound only to the M1 grid (the method §6 had just adopted),
  treating the M0 grid as out of scope. That is a post-hoc, challenger-only application of
  a bound the frozen §4/§5 text does not restrict to one candidate — WITHDRAWN as a prereg
  breach. With southbound's method reverted to M0, the frozen tie-break (ties or
  all-candidates-excluded → incumbent τ=0.5, β=25) is what actually retains τ=0.5, not the
  narrower M1-only exclusion §6 relied on.

### Revised final selection

| lens | method | tau | beta | outcome |
|---|---|---|---|---|
| themes | M0 | 0.75 | 30 | threshold recalibration only (unchanged from §6) |
| names | M0 | 0.5 | 25 | **reverted** — R1's 0.3/15 wrong-surface selection withdrawn |
| southbound | M0 | 0.5 | n/a | **reverted** — R1's M1 method adoption withdrawn |

Net W5 engine delta: **themes thresholds only** (τ=0.75, β=30). Names and southbound are
numerically and methodologically unchanged from pre-W5.

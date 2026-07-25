# PTT-W1 — persistence-of-fit: audition vs structure vs class vs global

Pre-registered ruler: script header (committed pre-run; measurement amendment log A1/A2 disclosed there — both pre-outcome). Universe: 1300 eligible names (ALL 6 tools ≥3 FIT + ≥3 TEST signals); 331 names excluded by eligibility; 2758 files scanned; load failures: 0. Signals pooled (TEST): 109,974. Split: FIT ≤ 2020-06-30 · TEST ≥ 2020-07-01 (sub-split ≥ 2021-01-01). Uplift = median signal fwd63 − own-half all-days median fwd63 (%). Random floor = strict mean of all 6 tools (a name missing any 2021+ tool value drops from the 2021+ random floor — no partial averages).

Eligibility tilt (disclosed): included median trend 0.52 / vol 36% vs excluded 0.55 / 41%. Charter-exhibit names excluded: PG, NVDA.

## A. Arms — panel median TEST uplift (name-level primary)

| arm | tool policy | median OOS uplift | 95% CI (month-cluster) | median 2021+ | CI 2021+ |
|---|---|---|---|---|---|
| (a) W1a audition-tailored (6-way IS best) | per name | -0.29% | [-2.11, +1.60] | +0.13% | [-1.66, +1.93] |
| (a′) W1b-pure structure (derived rung, S) | per name | +0.26% | [-1.80, +2.65] | +0.80% | [-1.25, +2.81] |
| (a″) W1b-hybrid (derived rung, 2-way family) | per name | +0.04% | [-1.96, +1.97] | +0.53% | [-1.38, +2.33] |
| (b) global one-size | per name | -0.83% | [-3.05, +1.67] | +0.01% | [-2.11, +2.58] |
| (c) class-best (vol×trend cells) | per name | -0.83% | [-3.05, +1.67] | +0.01% | [-2.11, +2.58] |
| (d) random floor | mean of 6 tools | -0.03% | [-1.83, +1.95] | +0.32% | [-1.37, +2.19] |

Global one-size tool selected in FIT: **S2W**. W1a FIT selections: M2W 328, S2W 302, M1W 216, S3D 162, M3D 154, S1W 138. Class-cell tools: v0xt0→S2W, v0xt1→S2W, v0xt2→S2W, v1xt0→S2W, v1xt1→S2W, v1xt2→S2W, v2xt0→S2W, v2xt1→S2W, v2xt2→S2W.

## B. Pairwise differences (decision block; name-level medians, month-cluster 95% CI)

| comparison | point | 95% CI | reads |
|---|---|---|---|
| (a) tailored − (b) global | +0.54% | [-0.73, +1.42] | includes 0 |
| (a) tailored − (c) class | +0.54% | [-0.73, +1.42] | includes 0 |
| (c) class − (b) global | +0.00% | [+0.00, +0.00] | includes 0 |
| (a′) W1b-pure − (a) W1a | +0.55% | [-0.32, +1.60] | includes 0 |
| (a″) W1b-hybrid − (a) W1a | +0.33% | [-0.24, +0.86] | includes 0 |
| (a′) W1b-pure − (b) global | +1.09% | [-0.32, +2.51] | includes 0 |
| (a″) W1b-hybrid − (b) global | +0.87% | [-0.44, +1.79] | includes 0 |
| (a) − (d) random floor | -0.26% | [-0.79, +0.11] | includes 0 |
| (a′) − (d) random floor | +0.30% | [-0.50, +1.15] | includes 0 |
| (a″) − (d) random floor | +0.08% | [-0.55, +0.45] | includes 0 |
| (c) − (d) random floor | -0.80% | [-1.75, +0.34] | includes 0 |
| (b) − (d) random floor | -0.80% | [-1.75, +0.34] | includes 0 |

Pooled signal-level robustness (phase-1 house form) — per-arm pooled median excess (CI): w1a -0.20% [-2.00, +1.67] · w1b_pure +0.33% [-1.60, +2.53] · w1b_hyb +0.08% [-1.78, +2.00] · global -0.81% [-3.14, +1.50] · class -0.81% [-3.14, +1.50]. Diffs: W1a−global [-0.33, +1.74]; W1b-pure−global [-0.18, +2.78].

## C. Is IS tool-fit persistent at the name level?

- Per-name Spearman(FIT tool ranks, TEST tool ranks): median **-0.029**; 49% of names positive (n=1300; 0 = no persistence; Spearman over 6 tool ranks is coarse by construction — read with the top-2 fraction).
- FIT-best tool lands in TEST top-2: **33.2%** (chance = 33.3%).

## D. W1b structure measurement (bars-only, reversion-by-scale)

Rung-map distribution (measured names, n=1300): 1W 46%, 3D 31%, 2W 23%; unmeasurable → 1W fallback: 0 names. Non-degeneracy gate (≤90% single-rung share): PASSED. no_reversion flag (all ρ>0): 78 names (6.0%).
Panel median ρ by rung: 3D -0.043 · 1W -0.073 · 2W -0.010.

| name | ρ3D | ρ1W | ρ2W | derived rung | W1b-pure OOS | W1a tool | W1a OOS | best OOS tool (hindsight) |
|---|---|---|---|---|---|---|---|---|
| MCD | +0.025 | -0.106 | -0.046 | 1W | +3.54% | M2W | -0.07% | M3D +5.57% |
| JNJ | -0.067 | -0.015 | -0.036 | 3D | +1.42% | S1W | +2.79% | S2W +2.91% |
| KO | -0.048 | -0.073 | -0.145 | 2W | +4.06% | M2W | -0.20% | S2W +4.06% |
| PEP | -0.032 | -0.090 | -0.184 | 2W | -0.17% | M2W | +0.72% | S1W +1.97% |
| WMT | -0.091 | -0.168 | -0.002 | 1W | -1.17% | M3D | -1.13% | M1W +2.37% |
| COST | -0.029 | -0.105 | -0.064 | 1W | +1.05% | M1W | -0.57% | S3D +1.26% |
| TSLA | +0.056 | -0.002 | +0.084 | 1W | -5.27% | S2W | +10.57% | S2W +10.57% |
| AAPL | -0.068 | -0.048 | +0.150 | 3D | +2.40% | S3D | +2.40% | M2W +7.43% |
| MSFT | -0.077 | -0.123 | -0.090 | 1W | -1.52% | S2W | -1.82% | M2W +6.82% |

## E. Stationarity (befriendability) stratification

| stationarity_fit tercile (mean |Δρ| FIT sub-halves) | names | W1b-pure median OOS | W1a median OOS | rung subA==subB |
|---|---|---|---|---|
| stationary | 434 | +0.34% | -0.11% | 44% |
| mid | 433 | +0.51% | +0.05% | 21% |
| shape-shifter | 433 | +0.05% | -1.08% | 17% |

no_reversion names (n=78): W1b-pure median OOS +1.46% vs panel +0.26% (structural 'washouts continue' class — codex flag).

(stationarity_full — FIT vs TEST drift — is emitted to the panel parquet as a codex column only; it uses test bars and never stratifies a decision metric here. Names with unmeasured drift: 0.)

## F. Archetype PIT lens (secondary; covered subset only)

Coverage: 134 of 1300 panel names carry an archetype at 2020-06-30; 118 sit in classes with ≥8 names.
On that subset: archetype-class arm median OOS -0.75% vs global -0.86% (Δ +0.11%) vs W1a -0.88% (Δarch−W1a +0.13%). Class tools: cyclical→M2W, financial→S2W, mixed→M2W, rate_sensitive→M1W, speculative_unprofitable→M1W. Descriptive (no CI — subset too small for month-cluster power; disclosed).

## G. fwd126 descriptive — low-vol tercile only (registered secondary; no decision reads this)

Low-vol tercile (434 names): pooled median excess fwd126 — W1b-pure +0.34% vs global -0.93%.

## H. Pre-stated readings → verdict

Ruler (header, pinned): tailored>class>global ⇒ per-name altitude; class>global≈tailored ⇒ class altitude; tailored≤random ⇒ tool tailoring is noise. W1b>W1a ⇒ structure-fitting becomes the engine; W1b≥class ⇒ engine seat. Adjudication lands in the charter §6 (research/PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md).

## I. Limitations (standing)

- Survivor tape: data/baskets/ohlcv holds today's listings; per-name own-baseline netting removes level bias but not composition bias.
- 2W bars are anchor-A; anchor-phase fragility is a known MWR limitation, not re-tested here.
- FIT-tail fwd63 spills ≤63td past the split (selection material only; TEST grading unaffected).
- ρ at 2W rests on ~170 FIT bars (se≈0.08); the stationarity sub-halves have only ~84 2W returns each (se≈0.11) — the stationarity_fit column conflates true drift with that estimation noise; terciles are relative reads.
- Eligibility (≥3+≥3 on ALL 6 tools) tilts the panel — see header disclosure; M@2W is the binding rung.
- fwd63/fwd126 are the registered horizons; nothing else was read.

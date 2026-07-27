# PSS-SR2 — persistent ex-self peer diffusion

The construction and decision law were committed before forward outcomes in `research/PSS_SR2_PEER_DIFFUSION_PREREG.md`. Positive effects always mean SR2 is better than the disjoint geometry control.

SR2 is research/display-only. Historical qualification could authorize only a prospective frozen shadow, never entry, rank, size, gate, or alert authority.

## Construction audit

- Anchor: subject fresh prior-60-close low during ≥15% ex-self sector new-low breadth at a shifted trailing-q80 extreme.
- Formation: four sessions; frozen prior-only ATR14, reference intraday low, and ex-self peer-breadth peak.
- Path: first +1 ATR rebound, then the first tested-low geometry no later than 40 sessions after formation.
- Treatment: all three peer-breadth sessions ending at the retest stay at or below half the formation peak.
- Control: identical complete name-price path without persistent peer contraction. The subject is absent from its own peer breadth.
- Inference: keep-first name-month; exact sector × month × anchor-severity × delay strata; within-stratum permutation primary.

## Coverage and outcomes

### DEV

| group | paths | names | names ≥3 | MAE63 | W5 | called | tail≤−10 | rebound8 first | unresolved | delay | close/ref |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sr2 | 1,739 | 725 | 298 | -7.64% | +42.4% | +15.9% | +38.2% | +34.1% | +0.3% | +8.0td | +0.73 ATR |
| geometry_control | 938 | 573 | 83 | -7.84% | +43.7% | +22.7% | +39.1% | +39.1% | +0.3% | +7.0td | +0.62 ATR |
| transient_control | 200 | 175 | 2 | -9.51% | +33.6% | +23.8% | +46.4% | +32.3% | +0.9% | +7.0td | +0.88 ATR |

#### SR2 minus geometry-control stratified effects

| metric | effect | 95% 3-month-block CI | permutation p | informative strata | retained events |
|---|---:|---:|---:|---:|---:|
| mae | -2.14 | [-3.32, -1.25] | 0.9995 | 69 | 1,051 |
| tail10 | -6.97 | [-13.45, -0.17] | 0.9795 | 69 | 1,051 |
| w5 | -14.73 | [-22.25, -7.89] | 1.0000 | 69 | 1,051 |
| called | -9.06 | [-13.18, -1.53] | 0.9960 | 69 | 1,051 |
| rebound8_first | -16.42 | [-31.23, -10.61] | 1.0000 | 69 | 1,051 |

### VAL

| group | paths | names | names ≥3 | MAE63 | W5 | called | tail≤−10 | rebound8 first | unresolved | delay | close/ref |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sr2 | 1,001 | 557 | 102 | -5.54% | +44.0% | +15.4% | +26.4% | +40.2% | +0.7% | +11.0td | +0.75 ATR |
| geometry_control | 840 | 533 | 54 | -6.37% | +48.2% | +21.1% | +30.8% | +29.2% | +0.0% | +6.0td | +0.64 ATR |
| transient_control | 201 | 180 | 1 | -6.45% | +43.9% | +23.9% | +32.9% | +35.2% | +0.0% | +5.0td | +0.71 ATR |

#### SR2 minus geometry-control stratified effects

| metric | effect | 95% 3-month-block CI | permutation p | informative strata | retained events |
|---|---:|---:|---:|---:|---:|
| mae | -2.80 | [-4.32, -1.22] | 0.9990 | 55 | 723 |
| tail10 | -12.68 | [-20.55, -5.33] | 0.9990 | 55 | 723 |
| w5 | -18.78 | [-25.03, -10.99] | 1.0000 | 55 | 723 |
| called | -3.77 | [-10.13, +0.77] | 0.8581 | 55 | 723 |
| rebound8_first | -16.78 | [-24.25, -11.17] | 1.0000 | 55 | 723 |

### FWD

| group | paths | names | names ≥3 | MAE63 | W5 | called | tail≤−10 | rebound8 first | unresolved | delay | close/ref |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sr2 | 846 | 546 | 58 | -8.58% | +34.3% | +17.3% | +43.6% | +36.4% | +0.1% | +10.5td | +0.79 ATR |
| geometry_control | 482 | 375 | 12 | -8.20% | +40.3% | +23.3% | +41.5% | +36.0% | +0.1% | +10.0td | +0.62 ATR |
| transient_control | 106 | 99 | 1 | -8.85% | +34.8% | +17.7% | +46.5% | +38.7% | +0.0% | +7.0td | +0.79 ATR |

#### SR2 minus geometry-control stratified effects

| metric | effect | 95% 3-month-block CI | permutation p | informative strata | retained events |
|---|---:|---:|---:|---:|---:|
| mae | -0.54 | [-3.87, +1.40] | 0.6957 | 37 | 469 |
| tail10 | +0.43 | [-10.67, +9.40] | 0.4493 | 37 | 469 |
| w5 | -13.18 | [-34.64, +3.52] | 0.9975 | 37 | 469 |
| called | -6.91 | [-18.03, +6.14] | 0.9415 | 37 | 469 |
| rebound8_first | -1.97 | [-21.93, +12.97] | 0.6612 | 37 | 469 |

## Frozen-geometry confound audit

| era | group | peer peak | delay | retest low/ref | action close/ref | next-open gap |
|---|---|---:|---:|---:|---:|---:|
| DEV | sr2 | +0.372 | +8.0td | +0.44 ATR | +0.74 ATR | -0.00% |
| DEV | geometry_control | +0.300 | +6.0td | +0.33 ATR | +0.65 ATR | +0.26% |
| VAL | sr2 | +0.288 | +9.0td | +0.43 ATR | +0.76 ATR | +0.07% |
| VAL | geometry_control | +0.251 | +6.0td | +0.32 ATR | +0.63 ATR | +0.13% |
| FWD | sr2 | +0.315 | +9.0td | +0.43 ATR | +0.79 ATR | +0.10% |
| FWD | geometry_control | +0.258 | +9.0td | +0.31 ATR | +0.63 ATR | +0.00% |

The absolute per-name summaries above are descriptive. The frozen sector/month/severity/delay-stratified effects are the verdict statistics; their opposite sign shows that the small pooled MAE difference is calendar/composition, not peer-diffusion edge.

## Frozen decision law

| check | pass | evidence |
|---|:---:|---|
| DEV mae clears | NO | effect=-2.14, CI=[-3.32,-1.25], p=0.9995 |
| DEV tail10 clears | NO | effect=-6.97, CI=[-13.45,-0.17], p=0.9795 |
| DEV timing and rebound-first improve | NO | W5=-14.73, called=-9.06, rebound8=-16.42 |
| VAL mae clears | NO | effect=-2.80, CI=[-4.32,-1.22], p=0.9990 |
| VAL tail10 clears | NO | effect=-12.68, CI=[-20.55,-5.33], p=0.9990 |
| VAL timing and rebound-first improve | NO | W5=-18.78, called=-3.77, rebound8=-16.78 |
| Coverage and informative-strata floor | YES | names=791, names≥3=659, strata={'DEV': 69, 'VAL': 55} |
| H1 conditional share at least 10pp below Sep–Nov | YES | H1=56.8%, Sep–Nov=68.9%, gap=12.1pp |
| DEV no SR1 safe-late distance confound | YES | stratified treatment-control=+0.03 ATR |
| VAL no SR1 safe-late distance confound | YES | stratified treatment-control=+0.00 ATR |
| Sector robustness and ≤25% concentration | NO | DEV-mae min=-2.40, DEV-tail10 min=-8.71, VAL-mae min=-3.46, VAL-tail10 min=-16.00, max share=20.1% |
| No FWD primary reversal | NO | MAE=-0.54, tail=+0.43 |

**Verdict: KILLED**.

## Containment, confounds, and topology

- H1-2022 opportunity / treatment density: 225.5 / 128.2 per month; treatment share 56.8%.
- Sep–Nov 2022 opportunity / treatment density: 133.0 / 91.7 per month; treatment share 68.9%.
- Next-open gap median / 95th percentile: +0.02% / +1.90%.

Treatment paths by sector:

- Financials: 722
- Information Technology: 512
- Industrials: 477
- Consumer Discretionary: 441
- Health Care: 413
- Real Estate: 238
- Materials: 209
- Consumer Staples: 194
- Energy: 172
- Utilities: 105
- Communication Services: 103

## Exclusion and path census

- `eligible`: 799 names
- `missing_sector_map`: 501 names

Aggregate counters:

- `anchors`: 9,231
- `complete_paths`: 5,846
- `treatments`: 3,586
- `controls`: 2,260
- `no_retest`: 2,689
- `no_rebound`: 552
- `transient_controls`: 507
- `incomplete_outcome`: 144

## Interpretation

At least one frozen requirement failed. This exact SR2 construction is not usable and cannot be rescued by changing the breadth ratio, persistence, or retest windows after outcomes. Mechanistically, peer recovery while the subject alone retests its low identifies an idiosyncratic laggard, not terminal systemic supply: the cross-sectional divergence has the opposite sign from the hypothesis.

Inference: 2,000 within-stratum permutations (base seed 20260804); 1,000 circular 3-month moving-block bootstraps (base seed 20260805).

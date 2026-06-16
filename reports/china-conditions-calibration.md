# China drawdown & slowdown risk — Phase-0 calibration

Index: **000001.SS** (Shanghai Composite, deepest A-share history) · as-of 2026-06-15 · independent ≥20% bear episodes (true sample size): **4**

**Verdict:** NO forward-drawdown edge — A-shares mean-revert; keep display-only, history-anchor the bands.

## Slowdown gauge
- History-anchored band edges (low / elevated / high): **26 / 45** · current reading **39.3**
- Spearman(gauge, forward 3m max-drawdown): **0.076** (≈0 ⇒ no monotone link; split-half H1 0.1 / H2 -0.128 ⇒ unstable sign)

| Band | n | median fwd 3m return | median fwd 3m max-DD |
|---|---:|---:|---:|
| low | 1627 | 1.1% | -5.2% |
| elevated | 1625 | -0.8% | -5.7% |
| high | 1646 | 1.9% | -4.5% |

_Flat / non-monotone across bands — higher stress does not precede deeper drawdowns; if anything it is mildly contrarian-bullish (mean reversion)._

## Drawdown-risk gauge
- History-anchored band edges (low / elevated / high): **50 / 75** · current reading **38.6**
- Spearman(gauge, forward 3m max-drawdown): **-0.108** (≈0 ⇒ no monotone link; split-half H1 -0.059 / H2 -0.182 ⇒ unstable sign)

| Band | n | median fwd 3m return | median fwd 3m max-DD |
|---|---:|---:|---:|
| low | 2622 | 0.0% | -5.1% |
| elevated | 1259 | 0.8% | -5.7% |
| high | 785 | -0.8% | -7.0% |

_Flat / non-monotone across bands — higher stress does not precede deeper drawdowns; if anything it is mildly contrarian-bullish (mean reversion)._

## What changes
- Bands are **re-anchored to the gauge's own historical distribution** (terciles for the raw slowdown score; percentile cutoffs for the already-percentiled drawdown gauge), so a 'high' reading means high *versus China's own record*, not an arbitrary number.
- The measured per-band forward conditional is attached to the snapshot and surfaced on the panel, so the page states the honest non-relationship.
- **Invariant preserved:** both gauges remain strictly DISPLAY-ONLY — never scored into china_axes / china_regime / china_playbook. Calibration grounds the *labels*, not a trade signal.

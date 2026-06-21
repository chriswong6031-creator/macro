# Composite validation — does the decorrelated composite earn the right to drive selection?

**Verdict: NO-GO.** Composite stays CONTEXT-ONLY — never drives selection or sizing.

- composite does NOT reliably beat momentum-alone (incremental IC mean -0.00907, HAC-t -0.795)
- composite IC-IR not significant net of FDR (HAC-t 0.227, q_fdr 0.8867)
- net-of-cost long-short spread not significant

Span 2011-03-31..2025-12-31 · 60 quarterly rebalances · forward 63d · ~110 names · leak-free, point-in-time · net of 20.0bps/side.

| signal | mean IC | IC-IR | IC-IR ann | t_HAC | q_FDR | net Sharpe (ann) | spread t_HAC | DSR |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| momentum | 0.0128 | 0.088 | 0.177 | 0.708 | 0.8867 | 0.119 | 0.45 | 0.3468 |
| fundamentals | 0.0022 | 0.02 | 0.039 | 0.143 | 0.8867 | -0.24 | -0.812 | 0.0375 |
| composite | 0.0037 | 0.029 | 0.058 | 0.227 | 0.8867 | -0.284 | -1.082 | 0.0234 |

**Incremental IC (composite − momentum):** mean -0.00907, HAC-t -0.795, n 60. By the Fundamental Law, a composite only beats its best leg when the added legs carry INDEPENDENT positive edge; a non-positive incremental t means the fundamental legs dilute rather than add.

> Breadth limited to the ~114 locally-cached large-caps (the wide deep panel is an offline CI artifact) — a CONSERVATIVE read (mega-caps are hardest to rank). Yahoo prices are survivorship-biased (delisted absent → optimistic). The committed 14y factor scorecard (~1154 names) is the wider companion: it already shows the fundamental composite IC ≈ 0.
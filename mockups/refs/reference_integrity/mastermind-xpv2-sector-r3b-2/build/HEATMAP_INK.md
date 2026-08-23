# B2-03 — heatmap readable-ink audit

Binding measurement of the candidate-owned `.hm-t` heatmap (views/money.html `#heatmap-scorecard`). Method, shadow-exclusion rule, and opacity-compositing note are documented in `heatmap_ink_audit.py`'s module docstring.

| metric | value |
|---|---|
| leaves measured | **504** |
| bin-tile cells (`.sym`/`.pc`) | 440 |
| sector-header cells (`.hm-sechd`/`.agg`) | 64 |
| sub-4.5:1 failures | **0** |
| parser-suspect (ratio==1.00) | 0 |
| excluded as unmeasurable | **0** (forbidden by COMMISSION.md B2-03) |
| substrate-fallback cells used | **0** |

[heatmap-ink] RESULT: ALL GREEN — 504 leaves measured, 0 failing 4.5:1, 0 excluded as unmeasurable, 0 substrate fallbacks used

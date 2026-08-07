# Pick-lab session-anchor blast radius

**Era:** `pl-abs-session-2026-08-06` · **boundary date:** 2026-08-06 · measured 2026-08-06 on the committed nightly panels (HK = deep search panel, the production cache-miss path).

The d2 grid (all regions) and the HK 3-session `d3_macd_xup_bars` site moved from
loader-phased `resample("nB")` bins to `session_anchor.session_positions // n`.
Old→new flip = any d2 scalar changed beyond EWM-memory scale (rel 1e-6).
Snapshot rows are keep-first and never retro-edited: pre-era rows keep a null
`pl_anchor_era`; the column fences the cohorts (R-SQ8 family).

| region | names | d2 any-flip | old k=1/k=2 flips (defect) | new k=1/2/3 flips |
|---|---:|---:|---:|---|
| US (asof 2026-08-05) | 238 | 238 (100%) | 238 / 0 | 0 / 0 / 0 |
| CN (asof 2026-08-06) | 1794 | 1761 (98%) | 1761 / 0 | 0 / 0 / 0 |
| HK (asof 2026-08-06) | 160 | 157 (98%) | 0 / 157 | 0 / 0 / 0 |

**Per-field d2 flip counts:** US: macd=238, macd_xup_bars=79, kd_xup_bars=48, from_os=23, ob=4 · CN: macd=1761, macd_xup_bars=316, kd_xup_bars=205, from_os=44, ob=15 · HK: macd=157, macd_xup_bars=81, kd_xup_bars=111, from_os=4, ob=32

**HK d3 site (live gate input — hklab_1d_blastoff reads `.isna()`):** 69/160 values move, 8 cross null↔non-null (0027.HK, 0268.HK, 1109.HK, 1347.HK, 2150.HK, 2628.HK, 2888.HK, 9999.HK); new-geometry k=1 leading-drop flips: 0.

A 0 in one old-k column beside a full-panel re-draw is the parity artifact (the panel's first row closed a complete bin at that k), not absence of the defect — the production HK panel is the rolling breadth cache, whose start creeps forward every refresh, re-phasing the old bins build-to-build.

The one-time re-draw is the cost of removing the loader-phase dependence (R-SQ4 pattern). No registered candidate book gates on d2_* (candidates.py reads d1_*; registry.py's only d2 knob is None) — repaired BEFORE any d2-gated book registers. The HK d3 change is disclosed above; `sessions_since_23d_cross` / `ret_since_23d_cross` derive from the repaired fields and inherit the fix.

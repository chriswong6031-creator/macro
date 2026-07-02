# Display-vs-Scoring Manifest

**Purpose:** Every seam where international/global data touches position-sizing or de-risk
logic ("scoring") versus surfaces that are badge/chart-only ("display"). This prevents
"integrated" from silently meaning "rendered."

**Machine copy:** `data/intl_bridge/manifest.json` — tested by `tests/test_manifest_seams.py`.
A CI failure on that test means a seam listed here no longer exists in the tree.

**Verified against:** `origin/main` as of 2026-07-02 (commit f086903f).

---

## Scoring seams (change size, gates, or de-risk logic)

| Seam | File | Symbol | Line | Notes |
|---|---|---|---|---|
| `conditions._macro_risk_legs` | `engine/conditions.py` | `_macro_risk_legs` | 851 | Single source for all 5 MRS legs; C2 intl-sleeve wires here in W2 |
| `conditions.macro_risk_series` | `engine/conditions.py` | `macro_risk_series` | 884 | Daily MRS [0,1]; consumed by playbook.py:547 |
| `conditions.sector_macro_beta` | `engine/conditions.py` | `sector_macro_beta` | 910 | Per-sector risk sensitivity; consumed at playbook.py:592 |
| `playbook.macro_risk_series × sector_macro_beta` | `engine/playbook.py` | `macro_risk_series` | 547 | Where MRS × beta computes macro_drag for sector scoring |
| `stock_score._edge_weights` calm master-switch | `engine/stock_score.py` | `_edge_weights` | 125 | Mom weight 0.28 calm → 0.04 stress; validated IC ±0.03 |
| `stock_score._axis_tailwind` | `engine/stock_score.py` | `_axis_tailwind` | 835 | Sector+thematic tailwind axis (weight 0.10); C6/C7 wire here if validated |
| `stock_score.conviction_profile` ctx | `engine/stock_score.py` | `conviction_profile` | 1160 | Accepts `risk_overlay` (subtract-only, line 1218) + `regime.calm` (line 1170) |
| `name_score._tailwind` bounded [0.85, 1.15] | `engine/name_score.py` | `_tailwind` | 139 | Per-name buy-readiness multiplier; C1 China global-beta wires here in W2 |
| `risk_radar_intl` post-`can_force` | `engine/risk_radar_intl.py` | `snapshot` | 316 | Display-only until can_force matures; `_radar_override_intl` at market_state_cn:153 already wired for sleeve sizing |
| `market_state_cn._radar_override_intl` | `engine/market_state_cn.py` | `_radar_override_intl` | 153 | CN external-driver radar → market_state ceiling; validated 2.07× lift |

---

## Display seams (badge/chart only — never change size or gates)

| Seam | File | Symbol | Line | Notes |
|---|---|---|---|---|
| `market_state.py` all markets | `engine/market_state.py` | `score` | 3 | Docstring: "DISPLAY-ONLY synthesis … never scores, sizes, or feeds any axis / regime / macro_risk" |
| `china_radar.py` | `engine/china_radar.py` | `scan` | 379 | "DISPLAY/CONTEXT-ONLY · NO VALIDATED EDGE" per docstring |
| `regime_snap_veto.py` | `engine/regime_snap_veto.py` | `is_context_only` | 121 | INTL-41: vetoes nothing; US-RORO-only inputs; is_context_only=True |
| `hk_global_beta.py` | `engine/hk_global_beta.py` | `compute_global_betas` | 65 | Currently display/context (per-name risk exposure); C1 would promote to scoring |
| `forex_dollar.py` dollar desk | `engine/forex_dollar.py` | `dollar_desk` | 324 | Broad-dollar lean written to display JSON only; INTL-45; C4b promotion path |
| `forex_regime.py` | `engine/forex_regime.py` | `_sub_intensity` | 136 | 6 FX scenarios; 60-trial family all fail DSR; no pair-level equity gating ever |

---

## Seam notes vs masterplan ADJ-5

The masterplan (ADJ-5) listed `china_name_score._tailwind` as a scoring seam. On
`origin/main` this module is a 13-line back-compat shim that re-exports from
`engine/name_score.py`. The canonical tailwind function is `engine/name_score._tailwind`
(line 139), where the bounded [0.85, 1.15] multiplier lives. The manifest reflects
the actual on-disk location.

The masterplan referenced `conviction_profile` ctx carrying `risk_overlay` and
`regime.calm` — both confirmed at `engine/stock_score.py` lines 1218 and 1170
respectively. The "China board entry gate" mentioned in ADJ-5 is handled through the
`market_state_cn._radar_override_intl` seam (display-gated) and is not a separate
scoring seam independent of the risk_radar_intl path.

---

## Governance

- Every W2+ wire names its target seam from this manifest before PR opens.
- The manifest test (`tests/test_manifest_seams.py`) runs in CI and fails if any
  listed (file, symbol) pair cannot be found in the tree.
- To add a seam: update `data/intl_bridge/manifest.json` AND this doc in the same PR.

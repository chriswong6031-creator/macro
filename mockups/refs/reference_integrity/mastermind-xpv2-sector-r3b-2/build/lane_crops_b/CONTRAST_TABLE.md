# XPV2-SC-R3B.2 — contrast audit gate table

Generated from `contrast_audit.json` (`contrast_audit.py`, run against the frozen
candidate `MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`, sha256
`ea2e09b812d1435103e491973ae01d2c4fca63c3a29186023f40f137fc10aba8`). Walks every
rendered text leaf across 6 views x 2 themes x 2 languages and computes the WCAG
2.x contrast ratio against the COMPOSITED painted background stack.

## Gate — reference-authored, flat-surface cells

| Metric | Value |
|---|---|
| Total text cells measured | 16188 |
| Scored (reference-authored, flat surface) | 15388 |
| AA failures | **0** |
| Parser-suspect (ratio==1.00, excluded from the gate) | 0 |
| Sub-10px cells (gated, `under_ramp`) | 0 |

Gate result: **PASS — 0 AA failures**

## Recorded, NOT gated (out of this check's scope)

| Scope | Count | Note |
|---|---|---|
| `producer_verbatim_fragment` below AA | 75 | the `sc_flows` verbatim production fragment (byte-identical under a sha256 receipt) — real, measured contrast debt, owned upstream/R3C, never rewritten in this reference (Sol FINAL CONTINUATION HANDOFF §6). |
| `unmeasurable_shadowed_colour_field` | 440 | the ~440 shadowed `.hm-t` glyphs over the data-driven heatmap colour field — UNMEASURED by the flat-surface method (Sol §4); reported, never scored, never converted to PASS or FAIL. |

## Commissioned named cells

| Probe | Theme/Lang | Size/Weight | Ratio | Result |
|---|---|---|---|---|
| action state — Buy now / 立即买入 | dark/en | 11px w700 | 5.58:1 | PASS |
| action state — Buy now / 立即买入 | dark/zh | 11px w700 | 4.79:1 | PASS |
| action state — Buy now / 立即买入 | light/en | 11px w700 | 4.98:1 | PASS |
| action state — Buy now / 立即买入 | light/zh | 11px w700 | 4.59:1 | PASS |
| action state — Entry now / 现可入场 | dark/en | 11px w700 | 5.58:1 | PASS |
| action state — Entry now / 现可入场 | dark/zh | 11px w700 | 4.79:1 | PASS |
| action state — Entry now / 现可入场 | light/en | 11px w700 | 4.98:1 | PASS |
| action state — Entry now / 现可入场 | light/zh | 11px w700 | 4.59:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/en | 10px w600 | 5.57:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/en | 10px w700 | 6.86:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/en | 10px w700 | 6.86:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/en | 10px w700 | 6.86:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/zh | 10px w600 | 5.57:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/zh | 10px w700 | 5.79:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/zh | 10px w700 | 5.79:1 | PASS |
| board column — 20d vs market / 20日对比市场 | dark/zh | 10px w700 | 5.79:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/en | 10px w600 | 5.43:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/en | 10px w700 | 6.29:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/en | 10px w700 | 6.29:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/en | 10px w700 | 6.29:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/zh | 10px w600 | 5.43:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/zh | 10px w700 | 5.82:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/zh | 10px w700 | 5.82:1 | PASS |
| board column — 20d vs market / 20日对比市场 | light/zh | 10px w700 | 5.82:1 | PASS |
| risk state — Risk appetite / 风险偏好 | dark/en | 10px w700 | 5.39:1 | PASS |
| risk state — Risk appetite / 风险偏好 | dark/zh | 11px w700 | 4.97:1 | PASS |
| risk state — Risk appetite / 风险偏好 | dark/zh | 10px w700 | 5.39:1 | PASS |
| risk state — Risk appetite / 风险偏好 | light/en | 10px w700 | 5.14:1 | PASS |
| risk state — Risk appetite / 风险偏好 | light/zh | 11px w700 | 4.95:1 | PASS |
| risk state — Risk appetite / 风险偏好 | light/zh | 10px w700 | 5.14:1 | PASS |
| track record — Still measuring / 测量中 | dark/en | 10px w700 | 7.59:1 | PASS |
| track record — Still measuring / 测量中 | dark/zh | 10px w700 | 7.59:1 | PASS |
| track record — Still measuring / 测量中 | light/en | 10px w700 | 6.33:1 | PASS |
| track record — Still measuring / 测量中 | light/zh | 10px w700 | 6.33:1 | PASS |

Reproduce: `<playwright-python> contrast_audit.py`


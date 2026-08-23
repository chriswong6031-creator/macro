# R3B.2 contrast receipt

Freshly measured from `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`
with `build/contrast_audit.py`: six views x dark/light x EN/ZH.

| gate | result |
|---|---:|
| text cells measured | **16,188** |
| reference-authored flat-surface cells scored | **15,388** |
| AA failures | **0** |
| sub-10px cells | **0** |
| parser-suspect 1.00 ratios | **0** |

## Commissioned named cells

| semantic | dark EN | dark ZH | light EN | light ZH |
|---|---:|---:|---:|---:|
| Buy now / 立即买入 | 5.58:1 | 4.79:1 | 4.98:1 | 4.59:1 |
| Entry now / 现可入场 | 5.58:1 | 4.79:1 | 4.98:1 | 4.59:1 |
| 20d vs market / 20日对比市场 shared header | 5.57:1 | 5.57:1 | 5.43:1 | 5.43:1 |
| Still measuring / 测量中 | 7.59:1 | 7.59:1 | 6.33:1 | 6.33:1 |

The mobile inline 20-day labels were also enumerated by the named probe and
measured above 5.79:1 in every dark-language cell and above 5.82:1 in every
light-language cell.

## Recorded without false promotion

- 75 producer-verbatim `sc_flows` cells measure 2.24:1–4.45:1 and remain an
  upstream/R3C dependency; reference bytes are receipt-bound and were not edited.
- 440 shadowed glyph cells over the data-driven heatmap colour field remain
  **UNMEASURED** by the flat-surface method. They are not counted as PASS or FAIL.

Machine backing: `contrast_audit.json`.

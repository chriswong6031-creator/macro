# Calibration v2.1 + Evidence Schema v1 + Phase 0

**Status:** v2.1 hardening PASS. Evidence Schema **1.0 frozen**. Phase 0 complete. Stopped. No Phase 1 deep capture.

**Primary reviewer:** GPT-5.6 Sol Extra High

## Gate

| Item | Result |
|---|---|
| Evidence Schema v1 | **PASS** (frozen `schema_version: "1.0"`) |
| Board dossier validator | **PASS** |
| Detail dossier validator | **PASS** |
| Phase 0 validator | **PASS** |
| Secret scan | **PASS** |
| Referential integrity | **PASS** |
| Artifact hashes | **PASS** |
| Validator mutation tests | **PASS** (13/13) |

## Runs

| Run | ID | SHA at collection |
|---|---|---|
| v2 calibration (Sol-reviewed) | — | `e5431db19e69902d8b93fbb60d12c9085e5f8ecc` |
| v2.1 hardening | `20260816T171140Z-e5431db1` | `e5431db19e69902d8b93fbb60d12c9085e5f8ecc` |
| Phase 0 topology | `20260816T172029Z-e5431db1` | `e5431db19e69902d8b93fbb60d12c9085e5f8ecc` |

Collector version in run manifests is the full 40-character SHA at run time (v2 head). This commit is the v2.1 + Phase 0 evidence commit on top of that SHA.

## What v2.1 changed (no full Prophet recapture)

- Generic committed architecture under `ux-evidence/_tools`, `_schema`, `_config`.
- Selector contract: expected cardinality 1 does not silently pick `.first`.
- Cycle targeting: `details.sv-deep` / `details.sv-deep > summary`.
- Verified `I.detail.cycle`: `details.sv-deep.open === true` → canonical `CYCLE_EXPANDED_1440x1000.png`.
- Detail sections rematerialized. `S.detail.identity` is the `.topline` (71px), `S.detail.decision` is `#sv-decision` (292px). The old 2.8-viewport `S.hero`/`#result` binding is gone.
- Chart controls (`1D`/`3D`/`1W`/`1M`/EMA/RSI/Stoch/MACD/Stoch RSI/Full screen/Alerts/Ask Mastermind/Cycle) now have unique selectors; tested IDs resolve.
- Capture fidelity vs product layout split. 390 detail overflow (scrollWidth 401) is product layout, not a capture fail.
- Artifact manifests + compact errors (`raw/logs/` for Playwright dumps).
- Fail-closed `validate_dossier.py` with mutation tests.

## Phase 0

See `00-product-map/REVIEW_START_HERE.md` and `00-product-map/VALIDATION.md`.

Do not treat “151 families” and “88 sampled instances” as the same count.

## Still missing / do not treat as captured

- Keyboard traversal
- Verified chart tooltip/crosshair (`I.detail.chart_hover` remains FAILED)
- Ahead/behind/closed/empty/gated board badges
- `#prophet-live` visible panel (section found, height 0)
- Deep five-width / interaction audit of non-Prophet pages
- Independent parity for `stockdata/ONTO.json` (still UNVERIFIED / gated)

## Stop

No Phase 1. No redesign. Waiting for Sol to choose the deep-audit order from Phase 0 topology.

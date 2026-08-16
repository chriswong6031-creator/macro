# REVIEW START HERE

**Schema:** 1.0 (frozen)
**v2.1 run:** `20260816T171140Z-e5431db1`
**Phase 0 run:** `20260816T172029Z-e5431db1`
**Collection SHA:** `e5431db19e69902d8b93fbb60d12c9085e5f8ecc`

## Validation

| Target | Result |
|---|---|
| Prophet Board | PASS |
| ONTO Detail | PASS |
| Phase 0 product map | PASS |
| Mutation tests | PASS (13/13) |
| Secret scan | PASS |

## What was collected

1. **v2.1 hardened Prophet dossiers** — `pages/us-stocks-prophet-board/`, `pages/stock-detail/`
   - Cycle disclosure verified (`CYCLE_EXPANDED`)
   - Section geometry corrected
   - Stable control IDs resolve
2. **Phase 0 product topology** — `00-product-map/`
   - 151 route families / 88 sampled instances / 87 surfaces
   - 1440 + 390 defaults only

## What was not collected

- Phase 1 deep dossiers
- Full five-width sets outside Prophet calibration
- Every tooltip/tab/filter/chart hover
- Every generated `site/stocks/*` instance

## Where to look

| Need | Path |
|---|---|
| This note | `ux-evidence/REVIEW_START_HERE.md` |
| Calibration / honesty | `ux-evidence/CALIBRATION.md` |
| Phase 0 entry | `ux-evidence/00-product-map/REVIEW_START_HERE.md` |
| Route inventory | `ux-evidence/00-product-map/product-route-inventory.md` |
| Capabilities | `ux-evidence/00-product-map/capability-map-draft.md` |
| Workflows | `ux-evidence/00-product-map/workflow-map-draft.md` |
| Topology facts | `ux-evidence/00-product-map/topology-observations.md` |
| Raw logs | `ux-evidence/**/raw/` |
| Review ZIP builder | `python3 ux-evidence/_tools/build_review_pack.py --run-id <id>` |

Key unresolved / failed evidence: chart tooltip still FAILED; `#prophet-live` height 0; `stockdata/ONTO.json` UNVERIFIED.

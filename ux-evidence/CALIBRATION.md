# Calibration + Phase 0.1

**Status:** Prophet/page evidence PASS. Phase 0 raw crawl kept. Phase 0 semantic topology was rejected by Sol and repaired as Phase 0.1. Topology schema is **1.1-candidate** (not frozen). No Phase 1.

## Gates

| Item | Result |
|---|---|
| Page Evidence Contract | **1.0 KEEP** |
| Prophet Board validator | **PASS** |
| Prophet Detail validator | **PASS** |
| Phase 0 raw screenshots | **KEPT** under `00-product-map/screenshots/` |
| Phase 0 first semantic topology | **REJECTED** — archived at `00-product-map/prior-runs/20260816T172029Z-e5431db1/` |
| Product Topology Contract | **1.1-candidate** (reopened; not frozen) |
| Topology machine gate | **PASS** |
| Topology semantic gate | **PENDING SOL REVIEW** |

## Runs

| Run | ID | SHA | dirty |
|---|---|---|---|
| v2.1 hardening | `20260816T171140Z-e5431db1` | `e5431db1…` | true (superseded constraint) |
| Phase 0 crawl | `20260816T172029Z-e5431db1` | `e5431db1…` | true (superseded) |
| Phase 0.1 tooling | — | `931bb3c67a82f86f47a808e50874395b3ffbebbf` | committed first |
| Phase 0.1 canonical topology | `20260816T181752Z-931bb3c6` | `931bb3c67a82f86f47a808e50874395b3ffbebbf` | **false** |

## Stop

No Phase 1. No redesign. Waiting for Sol Extra High semantic review of topology 1.1-candidate.

# Mastermind-X UX evidence

Evidence Schema **v1.0** (frozen). Collector is configuration-driven.

```
ux-evidence/_tools/     collect_page.py, collect_product_map.py,
                        validate_dossier.py, build_review_pack.py, pw_lib.py
ux-evidence/_schema/    JSON schemas
ux-evidence/_config/    page + route configuration
ux-evidence/pages/      deep dossiers (Prophet calibration)
ux-evidence/00-product-map/   Phase 0 topology
```

Validate:

```
python3 ux-evidence/_tools/validate_dossier.py
python3 ux-evidence/_tools/test_validate_dossier.py
```

Start at `REVIEW_START_HERE.md` and `CALIBRATION.md`.

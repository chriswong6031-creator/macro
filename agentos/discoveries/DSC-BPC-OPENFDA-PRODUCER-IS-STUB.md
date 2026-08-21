---
key: BPC-OPENFDA-PRODUCER-IS-STUB
claim: >
  config/biocatalyst_sources.yml names collectors.biocatalyst.openfda_regulatory
  as the openfda producer, but that module does not exist; collectors/biocatalyst/
  contains only CT.gov modules plus drugs_at_fda.py.
falsifier: >
  ls collectors/biocatalyst/ from origin/main shows a file implementing
  collectors.biocatalyst.openfda_regulatory, or importlib.import_module of that
  dotted path succeeds.
so_what: >
  Do not schedule device/CDRH or openFDA work as "turn on the existing producer."
  A device pack is net-new. Legacy collectors/openfda.py is a non-biocatalyst
  display adapter and must not be reused as the biocatalyst producer.
kind: dead_code
verified_at: 2026-08-18
verified_by: >
  ls collectors/biocatalyst/ = __init__.py clinicaltrials_discovery.py
  clinicaltrials_fixed_cohort.py clinicaltrials_history.py clinicaltrials_v2.py
  drugs_at_fda.py; rg openfda_regulatory collectors/ = no matches
scope:
  - macro
  - biocatalyst
  - "config/biocatalyst_sources.yml"
  - "collectors/biocatalyst/"
confidence: verified
---

## Notes

YAML still records the intended owner. That is a rights/registry stub, not an
implementation. drugs_at_fda.py is the opposite case: implemented and dark.

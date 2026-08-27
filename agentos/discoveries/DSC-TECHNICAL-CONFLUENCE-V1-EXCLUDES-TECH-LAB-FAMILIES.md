---
key: TECHNICAL-CONFLUENCE-V1-EXCLUDES-TECH-LAB-FAMILIES
claim: >
  At macro@463bb3b4b708a4748fc65a04250366ca94205186, the production descriptive confluence miner intentionally
  enumerates only legacy combo families and excludes challenger/new Technical Lab
  families; the promised role-grammar Combo v2 is not implemented in that file.
falsifier: >
  Inspect engine/tech_confluence.py on the cited commit: remove or disprove the
  LEGACY_COMBO_FAMILIES gate, show build_leg_defs consuming dependency_family/role
  grammar across the full catalog, and identify the implemented Combo-v2 path.
so_what: >
  Future sessions must treat the current screener as an incumbent benchmark rather
  than evidence that Mastermind already uses the full technical estate. They must not
  simply add more legs to Combo v1 and call the Technical Opportunity mission complete.
kind: architecture
verified_at: 2026-08-27
verified_by: "macro@463bb3b4b708a4748fc65a04250366ca94205186: engine/tech_confluence.py LEGACY_COMBO_FAMILIES and build_leg_defs"
scope:
  - macro
  - engine/tech_confluence.py
  - engine/tech_catalog.py
  - WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE
confidence: verified
---

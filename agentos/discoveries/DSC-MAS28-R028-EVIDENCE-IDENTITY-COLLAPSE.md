---
key: MAS28-R028-EVIDENCE-IDENTITY-COLLAPSE
claim: >
  At Macro base 6a1795192cc06c1ea8c9004a33b9e4bec62831c9 and ruleset digest
  41d5634a6ca6d4bbd993e728b73d839260452b24c891e556c59da52a184a1859,
  R028 declared PER_TARGET cardinality at the fixed SNAPSHOT:LINEAR location but
  omitted target identity from evidence. Distinct MAS targets sharing issue type,
  portfolio mode, and target role therefore canonicalized to one unique finding.
falsifier: >
  Run `git show 6a1795192cc06c1ea8c9004a33b9e4bec62831c9:config/pr_linkage_rules.v1.json`
  and reconstruct the R028 finding key for two different MAS target IDs with the same
  issue_type, portfolio_mode, and target_role. The claim is false if the target changes
  any canonical finding field, evidence byte, or location byte before the W0R amendment,
  or if findings are not deduplicated by their semantic key.
so_what: >
  Any future PER_TARGET finding must carry its exact target identity in a canonical
  field that participates in uniqueness. W1 must not resume from the earlier digest;
  schemas, goldens, observations, and renderers must require the existing `target`
  ATOM on every R028 finding.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  Read config/pr_linkage_rules.v1.json at 6a1795192cc06c1ea8c9004a33b9e4bec62831c9:
  R028 location_policy cardinality PER_TARGET, fixed SNAPSHOT:LINEAR location, and
  evidence_keys [issue_type, portfolio_mode, target_role]; compare the canonical
  unique-finding reduction in the same manifest and architecture sections 9.2/16.1.
scope:
  - macro
  - MAS-28
  - Macro PR #6328
confidence: verified
---

## Reconciliation

W0R repairs the landmine by adding the already-frozen `target` ATOM to R028. The rule remains
PER_TARGET, its location remains `SNAPSHOT:LINEAR`, and the contract remains 46 rules, 44
evidence keys, 20 execution routes, and REPORT_ONLY enforcement.

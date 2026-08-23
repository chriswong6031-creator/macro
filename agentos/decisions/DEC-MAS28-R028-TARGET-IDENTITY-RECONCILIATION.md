---
key: MAS28-R028-TARGET-IDENTITY-RECONCILIATION
question: >
  How must the canonical MAS-28 V1 contract represent R028 when its location policy
  and cardinality are fixed as one finding per Linear target, but the frozen evidence
  object does not identify which target produced the finding?
answer: >
  Preserve R028 as PER_TARGET at SNAPSHOT:LINEAR and add the existing evidence key
  `target` to R028. The value is an ATOM containing the exact normalized MAS-n issue
  identity. Preserve the other 45 rules, all 44 evidence keys, all 20 execution routes,
  the canonical grammar, and REPORT_ONLY authority. W1 must consume the reconciled
  ruleset only after this W0R merges.
rationale: >
  Finding uniqueness includes code, rule, fixed location, and canonical evidence. Two
  different Linear targets with identical issue_type, portfolio_mode, and target_role
  therefore produced the same R028 finding bytes and collapsed, contradicting the
  declared PER_TARGET cardinality. The vocabulary already freezes `target` as ATOM for
  R056, so reusing it closes identity without adding a rule, key, schema family, truth
  store, location form, or execution route.
alternatives:
  - option: Change R028 to ONE_AGGREGATE
    why_not: >
      It discards the frozen per-target semantics and makes remediation unable to name
      which exact MAS issue has the incompatible role/type tuple.
  - option: Encode the target in the finding location
    why_not: >
      SNAPSHOT:LINEAR is already the closed location grammar for R028. Adding dynamic
      location suffixes would widen the location vocabulary and every downstream schema.
  - option: Add a new evidence key such as issue_id
    why_not: >
      `target` already has the exact ATOM semantics required. A synonym would widen the
      44-key vocabulary and create two machine names for one identity.
  - option: Let W1 retain duplicate R028 rows outside the semantic finding key
    why_not: >
      That would make implementation behavior contradict the canonical report schema and
      hide the defect behind a second, non-source-law uniqueness mechanism.
supersedes:
  - DEC:MAS28-PR-LINKAGE-VALIDATOR-V1-REPORT-ONLY
evidence:
  - "Macro 6a1795192cc06c1ea8c9004a33b9e4bec62831c9 / ruleset digest 41d5634a6ca6d4bbd993e728b73d839260452b24c891e556c59da52a184a1859"
  - "Reconciled ruleset digest 2e97ad7acd0aec77ef18dbd76a1b3f2bbf8b7d4585e938498615de1917aa71aa / architecture SHA-256 9c57ad499fa34ee32f0ffeb9f2f5928f0515dba1609f984e5a20ce6576e7f75e"
  - "config/pr_linkage_rules.v1.json — R028 PER_TARGET location policy, fixed SNAPSHOT:LINEAR location, evidence without target"
  - "research/MASTERMIND_PR_LINKAGE_VALIDATOR_V1_ARCHITECTURE_FREEZE_2026-08-23.md sections 9.2 and 16.1"
  - "Open Macro PR #6328 independent review discovered the collision before W1 merge"
affects:
  - WS:AGENT-OS
  - MAS-28
  - config/pr_linkage_rules.v1.json
  - research/MASTERMIND_PR_LINKAGE_VALIDATOR_V1_ARCHITECTURE_FREEZE_2026-08-23.md
  - .github/pull_request_template.md
  - .github/PULL_REQUEST_TEMPLATE/design_migration.md
  - Macro PR #6328
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

## Carried-forward law

This is a record-wide successor because Agent OS decisions are superseded, never partially
patched. Every unrelated conclusion from the prior decision remains in force: the six-field
grammar and receipt-bounded alias epoch are canonical; the validator is a zero-network,
zero-mutation observer; semantic findings are REPORT_ONLY; and no branch-protection, merge,
comment, repair, Linear mutation, control-plane, House-Law, or workflow authority is added.

## Sequencing consequence

W0R must merge before W1 resumes. W1 must update its manifest/schema/golden expectations to
the new exact ruleset digest and emit `target` for every R028 row, then rerun the independent
hostile/property/mutation/purity review. The other repositories need only marker propagation
in bounded authoring-template carriers; they do not receive a second manifest or validator.

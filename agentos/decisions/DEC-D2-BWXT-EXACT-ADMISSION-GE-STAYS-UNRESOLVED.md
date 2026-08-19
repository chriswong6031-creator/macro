---
key: D2-BWXT-EXACT-ADMISSION-GE-STAYS-UNRESOLVED
question: >
  Which of the D2 pilot recipient identities may enter the reviewed recipient
  graph (defense21-v1), and on what evidence standard — specifically BWXT's
  eight observed UEIs and GE's five exact-name recipient records?
answer: >
  Admit exactly five BWXT chains (WJYVCPD5HKK7, C4L1VT236AA1, SMJQJGD5JEJ3,
  UMBKD2WKD8N5, PZDQCRZW7GJ3): each has SEC Ex.21 100%-ownership lines across
  FY2023/FY2024/FY2025, an exact USAspending registered-name match to the Ex.21
  entity, and a fetched-and-receipted USAspending recipient-children record
  listing the UEI under BWX TECHNOLOGIES, INC. (CMT4S6G76QB5). Refuse three:
  MMACD85DT5D5 (BWXT Ordnance Tennessee — live parent field says L3HARRIS on a
  2026-02-26 action vs the 2025-11-10 Indenture guarantor list: explicit
  evidence_conflict, displayed, not resolved), PM7HBL2KDX46 and URJ3CAC3MSH8
  (Indenture guarantor status is affiliation evidence, not an ownership
  percentage — asserting wholly_owned/1.0 from it would repeat the GDLS
  overclaim defect retained in #5424). GE stays entirely out of the graph:
  the registrant is still legally General Electric Company (CIK 40545,
  formerNames empty; "GE Aerospace" is a trade name per the 2024-04-02 8-K),
  at least five distinct UEIs display the exact name "GENERAL ELECTRIC
  COMPANY", and no SAM linkage to CIK 40545 was obtainable — so
  issuer_attribution stays not_asserted with the separation boundary shown
  from 8-K evidence.
rationale: >
  The D2 evidence standard requires exact identifier → exact legal entity →
  filing-backed ownership → central:* with no fuzzy-name bridging. The five
  admitted chains meet every hop with three independent sources agreeing on
  the identical registered string plus a parent-plane receipt; the three
  refusals each fail exactly one hop and the honest product state is a
  visible gap or conflict, not a softened admission. Name equality is
  punctuation/case-normalized across sources and is a HUMAN admission call
  recorded in the spec — the projector itself performs no name joins.
alternatives:
  - option: Admit the Indenture-guarantor entities as wholly_owned/1.0
    why_not: >
      A guarantor list proves affiliation, not an ownership percentage; this is
      the same overclaim class as #5424's GM/GDLS wholly_owned/1.0 JV defect.
  - option: Resolve GE via the largest "GENERAL ELECTRIC COMPANY" UEI
    why_not: >
      Exact string identity is necessary but never sufficient — five distinct
      UEIs share that exact name and none is SAM-verified to CIK 40545; the
      separation makes name-based attribution actively dangerous.
evidence:
  - data/government_revenue/recipient_entity_graph.json (defense21-v1, digest 93171ba0e6f7…)
  - research/defense_intelligence/D2_IDENTITY_ATLAS_EXECUTION_SPEC.md §2/§4
  - PR 5932 review trail (two-round opus adversarial review)
reversibility: >
  Revert PR 5932 to restore defense19-v1; the refusals are re-openable by a
  later reviewed manifest with better evidence (SAM entity registration,
  post-acquisition Ex.21).
---

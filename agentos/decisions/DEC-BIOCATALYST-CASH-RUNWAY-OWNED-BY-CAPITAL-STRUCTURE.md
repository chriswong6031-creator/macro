---
key: BIOCATALYST-CASH-RUNWAY-OWNED-BY-CAPITAL-STRUCTURE
question: >
  Who owns biotech cash/runway truth for BioCatalyst surfaces — given that
  cash_runway is a named non-capability of capital_structure today, the BC-C2
  adapter explicitly refuses it, and the parity ledger's Burn/Runway job
  cannot exist until someone owns the computation?
answer: >
  SOL RULING (P1-0R, 2026-08-20). FIF owns canonical PIT accounting facts
  (cash, burn inputs, filing-derived observations). Capital Structure owns
  the derived financing-survival / cash-runway projection computed from those
  facts. BioCatalyst consumes the projection through a bounded read; it must
  not create a BioCatalyst-local runway calculation. No implementation is
  authorized by this record.
rationale: >
  Runway is a derived financial projection over PIT accounting facts, and
  both halves already have owning planes: FIF is the accounting-facts plane,
  and Capital Structure is the derived-financing-computation plane (dilution,
  financing survival). A BioCatalyst-local computation would duplicate both —
  a second accounting-facts reader and a second projection engine — and would
  drift from the canonical one the first time either plane's methodology
  moved. The P1-0 capability ledger recorded exactly this gap (row 15,
  SPEC_ONLY — runway a named non-capability of capital_structure; the §4
  Burn/Runway job's missing edge was an owner-plane decision): the blocked
  state was correct, and the unblock is this ownership assignment, not a
  local workaround. The dossier and radar surfaces get runway context the same way
  they get identity: consumed with provenance from the owning plane.
alternatives:
  - option: BioCatalyst computes runway locally from raw observations
    why_not: >
      Duplicates FIF's accounting-facts reading and Capital Structure's
      projection authority; two runway numbers on one product is a
      credibility bug, and the local copy would carry no plane provenance.
  - option: FIF owns the projection end-to-end
    why_not: >
      FIF is the facts plane; financing-survival projection is judgment-laden
      derived computation of exactly the class Capital Structure already owns
      (dilution/financing mechanics). Splitting facts from projection keeps
      each plane's contract testable.
  - option: Leave ownership unassigned until a Burn/Runway job is actually built
    why_not: >
      The unassigned state is what P1-0 measured: the parity job is
      unbuildable and every future session re-litigates the same question.
      Freezing ownership now costs one record and prevents a local-compute
      shortcut under delivery pressure.
evidence:
  - "Sol P1-0R authority-closure directive, 2026-08-20 §4"
  - "research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md §3 row 15 (SPEC_ONLY, runway a named non-capability of capital_structure) and §4 Burn/Runway job, §11.4 (question as returned to Sol; both now carry the ownership-resolved wording post-P1-0R)"
  - "cash_runway named non-capability of capital_structure; BC-C2 adapter refuses it (P1-0 census, architecture doc §4 Burn/Runway row)"
affects:
  - "biocatalyst"
  - "WS:BIOCATALYST-CORE-PRODUCT"
  - "engine/biocatalyst/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Grounds

This closes §11.4 of the P1-0 recharter. The commissioning order for the
Capital Structure runway projection itself is a separate act on that plane's
workstreams; nothing here schedules it. Until the projection exists,
BioCatalyst surfaces show a typed absent/not-yet-available state rather than
a locally computed number.

## What would reopen this

A Sol/Chairman ruling restructuring the FIF / Capital Structure plane split
itself. BioCatalyst delivery pressure is explicitly not grounds to reopen.

# Theme-Parity Ratchet + Presentation-Layer Convergence — Implementation Amendment 1

**Status:** BINDING implementation clarification to the Chairman-approved architecture.

**Parent:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md`

**Approval receipt:** `research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_APPROVAL_2026-08-27.md`

This amendment resolves two internal implementation contradictions discovered during the required implementation-plan self-review. It does not alter the Chairman-approved product thesis, theme art directions, Canada→HK sequencing, or no-rebuild boundaries.

---

## A1. Existing page-evidence plane is the only visual-evidence manifest authority

The approved architecture says this program must not create a second evidence plane and must use the existing page-evidence harness conventions. Therefore any implementation-plan text proposing a new independent UI-evidence manifest schema or a new parallel evidence root as an authority is superseded.

Canonical evidence producer:

- `scripts/capture_page_evidence.py`
- manifest schema `mastermind.p0_evidence.v2`
- documentation `docs/product_experience/PAGE_EVIDENCE_HARNESS.md`

The TP-0 visual-evidence gate may validate whether an existing harness manifest contains the required route/theme/locale/viewport evidence and whether referenced screenshot content-addresses exist or have been materialized into the committed migration evidence packet. It may add a small **receipt/index file only if required to map a PR diff to an existing harness manifest**; such a receipt may contain paths/identities but may not redefine screenshot cells, provenance, capture semantics, or state truth.

The gate must not mint `mastermind.ui_visual_evidence.*`, another screenshot lifecycle, another page identity scheme, or another capture manifest.

---

## A2. Registry compliance is post-proof truth, so the compliance flip follows production proof

The architecture correctly requires that a route earns `design_system.compliant: true` only after real production/browser proof. A pre-merge implementation PR cannot possess post-merge production proof of its own shipped bytes. Therefore the earlier phrase that the registry update belongs in the "same implementation PR" is operationally inconsistent with the stronger proof law and is superseded by this sequence:

```text
implementation PR
→ exact-head CI + independent design/functional review
→ merge/deploy
→ real production proof
→ records/registry closeout PR flips compliant:true
```

The closeout PR must name:

- the implementation PR and merge SHA;
- the accepted evidence manifest/path;
- production proof receipts;
- the governed template/region + shared stylesheet region;
- any residuals.

If production proof fails, the route remains non-compliant and the implementation is repaired. A registry projection must never pre-declare visual acceptance merely to make one PR self-contained.

This two-carrier sequence is **not** a duplicate lifecycle: GitHub implementation/evidence truth remains GitHub, page compliance remains the existing canonical product page registry, and production acceptance remains the program's existing research/Agent OS closeout practice.

---

## A3. Plan precedence

For TP-0/TP-1/TP-2 implementation, precedence is:

1. higher design doctrine / Master Product Design System / Design Migration Factory where applicable;
2. Chairman-approved parent architecture;
3. this implementation amendment for the two questions above;
4. final implementation plans;
5. earlier draft-plan wording where non-conflicting.

Any worker encountering a conflict must follow this amendment rather than recreating a second evidence schema or pre-flipping registry compliance.

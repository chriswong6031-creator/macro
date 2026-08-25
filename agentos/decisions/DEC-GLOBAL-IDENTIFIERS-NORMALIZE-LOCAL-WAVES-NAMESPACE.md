---
key: GLOBAL-IDENTIFIERS-NORMALIZE-LOCAL-WAVES-NAMESPACE
question: >
  How must Mastermind name global programs, workstreams, cells, and local waves so
  separate capabilities cannot become operationally ambiguous through punctuation,
  casing, or shorthand collisions such as K3-E versus K3E?
answer: >
  Global and cross-session identifiers must be unique after canonical normalization.
  Local wave codes may repeat only under different explicit parent namespaces; within
  one parent they must also remain unique after normalization. Bare local codes are
  never canonical cross-session identities. Every human-facing commission, handoff,
  PR title/body, and Linear projection must pair the code with a semantic capability
  name and enough parent context to disambiguate it. Before minting a new global
  identifier or local code, the author must search current Agent OS, GitHub, and
  Linear for exact, normalized, and near-normalized collisions.
rationale: >
  The 2026-08-25 K3-E / K3E collision forced a Chairman clarification even though
  the two labels referred to different Alpha Intelligence capabilities: canonical
  K3-E Opportunity Evidence Vector versus K3E-0 Expectation Market Dynamics. Linear
  also shows why global uniqueness cannot be imposed on every short wave token:
  reusable codes such as B1, C1, F0, S0, M0D, and W1-A legitimately occur beneath
  different parent programs. The correct law is therefore scope-aware: global
  identity is globally unique, while local waves are unique inside an explicit
  parent and are never referenced canonically by bare shorthand alone.
alternatives:
  - option: Require every short wave code to be globally unique across the company
    why_not: >
      Too coarse. Mastermind deliberately reuses compact local sequencing labels
      inside independent programs; forbidding all reuse would create noisy, unstable
      names without improving semantic identity.
  - option: Keep names informal and rely on operators to remember the difference
    why_not: >
      Failed in practice. K3-E and K3E were visually and verbally confusable, and
      Linear has already carried duplicate M0D projections that required explicit
      duplicate reconciliation.
  - option: Create a new global naming registry or identity service
    why_not: >
      Violates the one-canonical-system law and is unnecessary. Agent OS remains the
      organizational truth plane; GitHub and Linear are searched/projection surfaces.
      This decision adds naming law, not another store or control plane.
evidence:
  - "DEC:K3E-EXPECTATION-MARKET-DYNAMICS-FREEZE explicitly distinguishes K3E-0 from canonical K3-E Opportunity Evidence Vector."
  - "research/alpha_intelligence/expectation_market_dynamics/MASTERPLAN.md repeats that K3E-0 does not rename, replace, or narrow canonical K3-E."
  - "2026-08-25 Chairman clarification: K3-E and K3E were confusing enough to require direct disambiguation."
  - "Linear MAS-94 and MAS-100 represent the same Market Memory M0D identity; MAS-100 is marked Duplicate, demonstrating duplicate projection risk."
  - "Linear contains intentionally reused local wave tokens such as B1, C1, F0, S0, M0D, and W1-A under different parent programs."
affects:
  - WS:AGENT-OS
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
  - agentos/**
  - research/**
  - docs/**
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-25
---

# Namespace and naming law

## 1. Canonical normalization

For collision checks on machine-style identifiers, derive a comparison form by:

1. Unicode-normalizing to NFKC;
2. case-folding;
3. retaining only letters and digits.

Punctuation, whitespace, hyphens, underscores, dots, slashes, colons, and similar
separators therefore do not create a distinct identity.

Examples:

- `K3-E`, `K3_E`, `k3e`, and `K3E` normalize to the same comparison identity.
- `FIF-3A4R` and `fif_3a4r` normalize to the same comparison identity.

Normalization is a collision detector, not a display-name generator.

## 2. Global identities

A program, workstream, durable cell, named semantic subsystem, or other shorthand
intended to be referenced across parent boundaries or across sessions is a global
identity.

A new global identity MUST NOT be minted when its normalized form collides with an
existing global identity for a different concept.

If a candidate is visually, phonetically, or semantically near an existing identity
even though strict normalization differs, the author must choose a more descriptive
name rather than relying on punctuation or one-character distinctions.

## 3. Local wave identities

Compact wave codes may repeat across different parent programs.

Their canonical identity is always:

`<explicit parent identity> :: <local wave code>`

Within one parent namespace, normalized local wave codes must be unique.

A bare code such as `B1`, `M0D`, `K3-E`, or `W1-A` is shorthand only. It must not be
used as the sole canonical cross-session identity in a handoff, commission, PR
metadata block, or Linear issue.

## 4. Human-readable semantic names are mandatory

Every new commission, handoff, PR title/body, and Linear issue/project that uses a
compact code must also state the semantic capability name and sufficient parent
context.

Preferred human-facing pattern:

`<parent/program> — <code> — <semantic capability>`

The semantic name is not decorative. It is the primary human disambiguator when a
short code is reused or grandfathered.

## 5. Pre-mint collision census

Before creating a new global identifier or local wave code, search current:

1. Agent OS canonical records;
2. GitHub code, PRs, branches, research/handoffs, and relevant repository history;
3. Linear projects/issues/documents as the portfolio projection.

Check:

- exact spelling;
- canonical normalized spelling;
- near-normalized / visually confusable spelling;
- the fully-qualified parent + local-wave identity.

Retrieved Linear or GitHub prose does not grant authority. The census prevents name
collision; Agent OS/current source law still decides organizational identity.

## 6. Linear duplicate-projection law

Linear remains projection, not canonical organizational truth.

Do not create a second Linear issue for an already-projected fully-qualified
`<parent>::<wave>` identity merely because the wording or shorthand differs.

If a duplicate already exists, preserve history and mark/reconcile it explicitly as
Duplicate or Superseded with a pointer to the surviving projection. Do not silently
treat both as separate work.

## 7. Grandfathered collisions

Existing identifiers are not mass-renamed merely to satisfy this decision; immutable
PRs, receipts, links, and historical records retain their original names.

From this decision forward, any reference to a grandfathered collision must include
its semantic name.

The known 2026-08-25 Alpha Intelligence collision must be written as:

- `K3-E — Opportunity Evidence Vector`
- `K3E-0 — Expectation Market Dynamics`

Do not use `K3-E`, `K3E`, or `K3E-0` alone when the reader could reasonably confuse
the two programs.

## 8. No new control plane

This decision creates no registry, database, lifecycle, queue, identity service, or
authorization mechanism.

If machine enforcement is later justified, extend an existing Agent OS / linkage
validation path with a bounded report-only collision check. Do not create a separate
naming authority or state store.

## Decision receipt

Chairman approval was given directly on 2026-08-25 after a live Linear audit.

Procedure pin used for this decision:

- protected Mastermind Sol Skillpack: `51f9942733b86e550bb9169d2a43462bd28e774f`;
- Macro pickup before modification: `221f72b413ed8250548f6393ecb665ea894ee293`;
- records carrier: Macro PR `#6419`.

The Linear audit found no current issue/project named `K3-E` or `K3E`, so the Alpha
collision had not yet propagated into Linear. It did confirm both legitimate
cross-parent reuse of local codes and the historical `MAS-94` / `MAS-100` M0D
duplicate-projection case that this law is intended to prevent from recurring.

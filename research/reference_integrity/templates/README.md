# RIG artifact templates — how to run a Reference Integrity cycle

Law: `research/REFERENCE_INTEGRITY_GATE_V1.md`. Checker:
`python3 scripts/check_reference_integrity.py --evaluate <reference-id>`.
Founding worked example: `research/reference_integrity/prophet-board-5514-original/`.

A session commissioning a redesign of an existing customer-facing surface runs this
cycle **before** the Design Migration Factory may treat the result as canonical:

1. **Scope** (RIG §2). Full / lightweight / not-RIG. When in doubt: removal or
   relocation of any existing user capability, or any information-hierarchy change,
   means Full.
2. **Continuity first, if anything came before** (RIG §13 — V1.1). A cycle that follows a
   `REVISE`/`REJECT` starts by accounting for the last one. Declare the chain in
   `manifest.yml: lineage.predecessors` (ordered oldest → nearest; every non-approved set
   on the same `surface.route` must appear, or `undeclared-predecessor` fires), then
   **derive** the closure set rather than writing it from memory:
   `python3 scripts/check_reference_integrity.py --mandate <reference-id>` prints
   `CONTINUITY_TEMPLATE.yml` pre-filled with every open predecessor item —
   `disposition: <REQUIRED>`, the predecessor's own note as context — for
   `research/reference_integrity/<reference-id>/continuity.yml`. Give each item exactly one
   of `RESOLVED_BY_CHANGE` / `CARRIED_BLOCK` / `OVERRIDDEN` / `SUPERSEDED`. A
   `CARRIED_BLOCK` is legal and honest; it blocks approval and keeps the debt visible to
   the next cycle. This gate is armed at `draft`, so it fails before any critic is spawned.
3. **Baseline first, design second** (RIG §4/§9). Copy `BASELINE_TEMPLATE.yml` →
   `research/reference_integrity/<reference-id>/baseline.yml`. Capture production
   screenshots (committed under `mockups/refs/reference_integrity/<reference-id>/`),
   cite source paths + SHA, inventory capabilities with file:line evidence, and pull
   the design lineage (operator rulings, `DNR:` keys, component comments, rejected
   variants). The designer reads this BEFORE designing.
4. **Proposal ledger** (`PROPOSAL_TEMPLATE.yml`): freeze the proposed artifact by SHA;
   disposition EVERY baseline capability id; fill the user-task matrix, authority
   delta, and information-economics audit. `BLOCKED_DATA` — not `REMOVE` — for
   anything the data contract can't serve yet.
5. **Dual review, quarantined** (RIG §6). Spawn two independent Opus reviewers with
   the prompts in `CRITIC_A_PRODUCT_REGRESSION.md` / `CRITIC_B_VISUAL_TASTE.md`.
   Pass 1 inputs exclude the designer's rationale; freeze findings; reveal rationale;
   record pass-2 amendments. Receipts → `reviews/*.yml` (`REVIEW_TEMPLATE.yml`).
6. **Verdict packet** (`VERDICT_TEMPLATE.yml`): the design authority answers all
   eight forced questions, resolves every blocker by id, and issues
   APPROVE_REFERENCE / APPROVE_WITH_CONDITIONS / REVISE / REJECT.
7. **Approval receipt** (`APPROVAL_TEMPLATE.yml`) only on approval; flip manifest
   `status: approved`. Now — and only now — may a migration packet cite
   `RIG-RECEIPT: <reference-id>` and a registry row flip compliant on it.

Run `python3 scripts/check_reference_integrity.py` (repo mode) before every commit of
the artifact set; it refuses illegal states rather than judging taste.

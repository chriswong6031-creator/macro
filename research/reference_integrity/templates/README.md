# RIG artifact templates — how to run a Reference Integrity cycle

Law: `research/REFERENCE_INTEGRITY_GATE_V1.md`. Checker:
`python3 scripts/check_reference_integrity.py --evaluate <reference-id>`.
Founding worked example: `research/reference_integrity/prophet-board-5514-original/`.

A session commissioning a redesign of an existing customer-facing surface runs this
cycle **before** the Design Migration Factory may treat the result as canonical:

1. **Scope** (RIG §2). Full / lightweight / not-RIG. When in doubt: removal or
   relocation of any existing user capability, or any information-hierarchy change,
   means Full.
2. **Baseline first, design second** (RIG §4/§9). Copy `BASELINE_TEMPLATE.yml` →
   `research/reference_integrity/<reference-id>/baseline.yml`. Capture production
   screenshots (committed under `mockups/refs/reference_integrity/<reference-id>/`),
   cite source paths + SHA, inventory capabilities with file:line evidence, and pull
   the design lineage (operator rulings, `DNR:` keys, component comments, rejected
   variants). The designer reads this BEFORE designing.
3. **Proposal ledger** (`PROPOSAL_TEMPLATE.yml`): freeze the proposed artifact by SHA;
   disposition EVERY baseline capability id; fill the user-task matrix, authority
   delta, and information-economics audit. `BLOCKED_DATA` — not `REMOVE` — for
   anything the data contract can't serve yet.
4. **Dual review, quarantined** (RIG §6). Spawn two independent Opus reviewers with
   the prompts in `CRITIC_A_PRODUCT_REGRESSION.md` / `CRITIC_B_VISUAL_TASTE.md`.
   Pass 1 inputs exclude the designer's rationale; freeze findings; reveal rationale;
   record pass-2 amendments. Receipts → `reviews/*.yml` (`REVIEW_TEMPLATE.yml`).
5. **Verdict packet** (`VERDICT_TEMPLATE.yml`): the design authority answers all
   eight forced questions, resolves every blocker by id, and issues
   APPROVE_REFERENCE / APPROVE_WITH_CONDITIONS / REVISE / REJECT.
6. **Approval receipt** (`APPROVAL_TEMPLATE.yml`) only on approval; flip manifest
   `status: approved`. Now — and only now — may a migration packet cite
   `RIG-RECEIPT: <reference-id>` and a registry row flip compliant on it.

Run `python3 scripts/check_reference_integrity.py` (repo mode) before every commit of
the artifact set; it refuses illegal states rather than judging taste.

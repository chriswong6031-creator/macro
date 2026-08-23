---
key: MAS28-AUTHORING-GRAMMAR-DRIFT
claim: >
  The three repository authoring surfaces do not currently teach one MAS-28 V1
  grammar: Macro #6135 and Mastermind's lowercase template teach the older alias
  family, MAS-6 still exposes untracked_refused as an author mode, and Terminal has
  no default template at its current default head.
falsifier: >
  Run git show against the exact merged template/blob receipts for Macro, Mastermind
  and Terminal, then create one real new draft in each repository and inspect its
  prepopulated body. The claim is falsified when all three contain the canonical
  grammar, the intended file wins, MAS-6 no longer exposes untracked_refused as
  author input, and the cutover config binds the exact receipts without a clock.
so_what: >
  Future validators and authoring repairs must retain pre-cutover compatibility for
  exactly four named aliases, reject them after the repository's exact cutover
  receipt, reconcile Macro #6135 in place, test Mastermind's case-colliding template
  precedence and add Terminal's missing surface without inventing ownership.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  Protected default-branch/template reads, current Linear MAS-6/MAS-28 commission,
  and GitHub PR #6135 inspection at head 96fb7a35bb17fbcc7b462610bfbf59072ebbc218
scope:
  - macro
  - Mastermind
  - mastermind-terminal
  - MAS-6
  - MAS-28
confidence: verified
---

## Exact observed drift

- Canonical Chairman grammar uses `creates_workstream`, `implementation`, `proof`,
  `proof-required`, `deploy`, `architecture_candidate`, and `records-only`.
- Open Macro #6135 and the merged Mastermind lowercase template use
  `workstream_creation`, `runtime`, `production-proof`, and
  `production-proof-required`.
- Macro's selectable `.github/PULL_REQUEST_TEMPLATE/design_migration.md` has no six-field
  block, so a default-only repair would still leave design PRs outside V1 authoring.
- MAS-6 is otherwise V1-like but lists `untracked_refused`, which the controlling
  commission reserves as validator output.
- Mastermind also has an uppercase generic `.github/PULL_REQUEST_TEMPLATE.md`; current bytes
  alone do not prove which case-colliding surface GitHub uses for a real new draft.
- Terminal `449439c690e93ba968185499af4041c2f512b659` has no default PR template.

This is authoring drift, not evidence that historical PRs were invalid. Exact cutover receipts
separate legacy input from new defects, and calibration must retain real legacy shapes rather
than manufacturing a clean backlog.

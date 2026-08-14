---
key: EVAL-OS-BLINDNESS-EXITS-BY-PLANE
question: >
  When the intelligence-registry guard cannot read an input, should the run exit non-zero
  in the PR CI lane — and does the answer depend on which input went dark?
answer: >
  Yes, by plane. Blindness on any PR-PLANE input — config/synapse.yml (NOT CHECKED path),
  config/intelligence_registry_overlay.yml, config/qual_ladder.yml, data/species/registry.json,
  the Article-2 module import, or any producer source file — exits 1 unconditionally, in both
  plain and --json modes, with no flag. Blindness on the sole DATA-PLANE input,
  data/qledger/claims.jsonl (nightly append-only; partial parse failures counted per line), is
  always REPRESENTED — `inputs=INCOMPLETE (...)` on the summary line naming the store and
  counts, the single budgeted COULD-NOT-LOOK ::warning, `unreadable_inputs` in --json — but
  exits non-zero only under --strict.
rationale: >
  M4 of the T1 continuation handoff showed "fail-closed" was a mode nothing ran: CI omitted
  --strict, so a blind run exited 0 and the property was documentation, not enforcement. The
  first fix (exit 1 on ANY blindness) failed adversarial review: one truncated line in the
  46,000-line nightly claims store would red the isolated T1 job for every PR in the fleet —
  a store no PR author can touch gating PRs is how a lane gets routed around. The cut follows
  actor jurisdiction: a PR can break config, code, and adjudicated stores, so their
  unreadability is a tree defect the PR lane must red on; only the nightly writer can corrupt
  claims.jsonl, so its corruption alerts loudly in every run and gates in the strict lane the
  nightly/T7 era owns. "Failing to look must never render as 0 violations" is satisfied by
  REPRESENTATION on every path — the summary line can never read clean while blind.
alternatives:
  - option: exit 1 on any blindness, uniformly
    why_not: >
      Reproduced by the reviewer: one malformed line in the nightly store reds the T1 job for
      every open PR until the store is healed — a fleet-wide red on a defect no PR caused,
      violating the same law (assertions whose truth a nightly append can change) the wave
      existed to close.
  - option: keep fail-closed behind --strict only (the parked design)
    why_not: >
      That is exactly M4: CI never passes --strict, so a run blind on species/qual_ladder/
      producer source exits 0 and the enforced property is fictional. A PR that breaks a
      config input would merge green.
  - option: exit 0 always, rely on the annotation channel
    why_not: >
      Fails "failing to look must never render as 0 violations" in its enforcement half —
      structural violations exit 1, so an exit-0 blind run is indistinguishable from a clean
      run to anything consuming exit codes.
evidence:
  - "Reviewer reproduction: 1 truncated line appended to a COPY of data/qledger/claims.jsonl -> guard rc 1 + 2 pytest failures (T1_REVIEW.md F-2)"
  - "data/species/registry.json full history: 17 commits, every one an adjudication PR (last #4358 2026-08-03) — PR-plane, measured on the unshallowed clone 2026-08-14"
  - "data/qledger/claims.jsonl is the only nightly-appended input of the six (writer: nightly qledger lanes)"
  - "scripts/check_intelligence_registry.py exit matrix + selftest controls: PR-plane blind -> rc 1 no flag; data-plane-only blind -> rc 0 plain + rc 1 --strict; both mutation-gated"
affects:
  - "WS:EVAL-OS-T1-ENGINE-REGISTRY"
  - qualitative-intelligence
  - scripts/check_intelligence_registry.py
  - scripts/build_intelligence_registry.py
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-14
---

The nightly-side enforcement (running the guard with --strict in the nightly lane, so
data-plane corruption gates where the data-plane actor lives) is deliberately deferred with a
named owner: the T7 scorecard wave. Until then the data-plane teeth are the always-on
INCOMPLETE summary + the budgeted COULD-NOT-LOOK annotation in every PR run.

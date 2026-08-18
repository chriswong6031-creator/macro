---
key: GOVREV-CANDIDATE-PROOF-GATE-ARMED
question: >
  `.github/workflows/government-revenue-live.yml:540` sets
  `GOVREV_CANDIDATE_PROOF_FATAL: "0"`, so the lane's own proof step downgrades a real
  test failure to a warning and publishes anyway — which is why a projection its own
  suite fails got published. Should the gate be armed, and what would it have caught?
answer: >
  YES — arm it: `GOVREV_CANDIDATE_PROOF_FATAL: "1"`. The gate was born disarmed
  deliberately (PR #5516) with an explicit, written arming precondition, and that
  precondition is now MET: all three hand-typed GRAPH-VINTAGE constants the author named
  are derived. Honest scope limit, stated because it matters: arming would NOT have
  caught the 2026-08-18 incident. The govrev fold published at 04:15:52Z against a tree
  that was coherent at that moment; the divergence was created 6 minutes LATER at
  04:21:53Z when the second collection pass clobbered the spine. No gate sited before a
  publish can see a corruption introduced after it. What arming does catch is the
  different and real class the step was built for: a projection that cannot pass its own
  suites at the instant it is about to publish, failed loudly at the source and attributed
  to the commit that caused it, instead of surfacing days later on an unrelated pull
  request.
rationale: >
  The disarm was a sequencing argument, not a policy. The introducing commit
  (7986eba64ae5 / #5516, "ci(govrev): make the candidate projection prove itself before it
  publishes") states it verbatim: the suites "still carry hand-typed GRAPH-VINTAGE
  constants (`reviewed_issuer_company_count == 19`, `mapping_needed == 21`, a literal
  19-ticker list). Those detonate on a CORRECT republish, so a fatal gate today would
  convert a random-PR ambush into a BLOCKED NIGHTLY — strictly worse. Flip
  GOVREV_CANDIDATE_PROOF_FATAL to `1` once those constants are derived the way
  `canonical_frozen_at()` and `canonical_candidate_census()` already are."

  All three are now derived, verified by reading the current assertions:
  `reviewed_issuer_company_count` is asserted `== len(...)`
  (tests/test_government_revenue_candidates.py:295); `mapping_needed` is asserted
  `== len(canonical_requested_issuer_tickers())` (:265 and
  tests/test_government_revenue_candidate_projection.py:715); the 19-ticker list is
  asserted against `list(canonical_requested_issuer_tickers())` (:271). The surviving
  `== 19` / `== 21` occurrences are explanatory COMMENTS, and
  `canonical_frozen_at()` / `canonical_candidate_census()` /
  `canonical_mapping_backlog_states()` are imported and used across all three files. The
  one remaining integer literal, `mapping_needed == 2`
  (test_government_revenue_candidates.py:614), asserts against a synthetic in-test
  `_payload()`/`_graph()` fixture, not the live graph vintage, so a correct republish
  cannot detonate it.

  Arming costs no render budget and its blast radius is narrower than "every publish":
  the step is gated on `publish == 'yes'`, then early-exits when the four candidate
  artifacts are unchanged this run, and the pytest-unavailable path `exit 0`s
  UNCONDITIONALLY without consulting the flag. So arming cannot turn a quiet night or a
  tooling gap into a blocked nightly — it blocks on exactly one condition, candidate
  artifacts changed AND the suites genuinely fail, and only the exit code changes. It is
  also the only lane that actually runs them on an
  ordinary candidate-publishing night — the `.github/ci/legacy-jobs.yml` copies
  (`unrun-government-revenue`, `unrun-government-revenue-candidate-projection`) are
  `if: ${{ false }}` and fire only under a full-suite trigger. So today a govrev publish
  is proven by nothing that can stop it.

  Failure mode if a spurious red does appear: govrev does not publish that night and says
  so loudly with an `::error` annotation at the source. That is strictly better than the
  status quo, which publishes an unproven projection silently and lets a stranger's PR
  inherit the red days later. The named detonation risk is retired; the residual risk is
  ordinary.
alternatives:
  - option: Leave it "0" and rely on the warning
    why_not: >
      The warning is the status quo that allowed an unproven projection to publish. The
      step's own summary line already calls this out: it exists to make the break visible,
      but visibility without refusal did not stop the publish.
  - option: Arm it only for a subset of the three suites
    why_not: >
      The env var is a single switch over one pytest invocation; splitting it would need a
      second step and a second gate for no measured benefit. All three suites now derive
      their vintage constants, so none is the weak link.
  - option: Wait until the push-path lost update is fixed, then arm
    why_not: >
      Independent concerns. The lost update is fixed in daily.yml's rebase resolution
      (DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD); this gate proves the projection
      at publish time. Arming does not depend on that work and delaying buys nothing.
  - option: Arm it AND claim it would have prevented the 2026-08-18 incident
    why_not: >
      False. Timeline refutes it: the fold published at 04:15:52Z (5214d0b20a17) against a
      then-coherent tree; the clobbering pass committed at 04:21:53Z (93ab221b81dd). The
      gate is sited before the publish and cannot see a later corruption. Claiming
      otherwise would mis-set expectations about what is now protected.
evidence:
  - ".github/workflows/government-revenue-live.yml:517-540 — the disarm and its written arming precondition"
  - ".github/workflows/government-revenue-live.yml:579-605 — the pytest invocation and the FATAL branch"
  - "git log -S GOVREV_CANDIDATE_PROOF_FATAL --all -- .github/workflows/government-revenue-live.yml → 7986eba64ae5 and squash-merge 2615cacace1e (#5516); value was born \"0\", never armed then disarmed"
  - "tests/test_government_revenue_candidates.py:265,271,295 — mapping_needed, ticker list, reviewed_issuer_company_count all derived"
  - "tests/test_government_revenue_candidate_projection.py:39,43,712,715 — FROZEN_AT / CANONICAL_CENSUS / mapping_backlog derived"
  - "tests/test_government_revenue_candidate_fixture.py:18,134,207-213 — canonical_frozen_at, canonical_mapping_backlog_states derived"
  - ".github/ci/legacy-jobs.yml unrun-government-revenue and unrun-government-revenue-candidate-projection are if: ${{ false }} — this lane is the only ordinary-night runner of these suites"
  - "Timeline: 5214d0b20a17 govrev fold 04:15:52Z; 93ab221b81dd second collection pass 04:21:53Z — corruption postdates the publish"
  - "DSC:GOVREV-DOUBLE-COLLECT-PUBLISHED-NOTHING-X-THEIRS-DROPPED-IT"
affects:
  - .github/workflows/government-revenue-live.yml
  - tests/test_government_revenue_candidates.py
  - tests/test_government_revenue_candidate_projection.py
  - tests/test_government_revenue_candidate_fixture.py
confidence: high
reversibility: easy
decided_by: session claude/govrev-event-identity-adjudication
decided_at: 2026-08-18
---

## Detail

### What arming does and does not buy

Catches: a candidate projection that fails `tests/test_government_revenue_candidates.py`,
`tests/test_government_revenue_candidate_projection.py`, or
`tests/test_government_revenue_candidate_fixture.py` at the moment it is about to be
committed and published — refused at the source, minutes after minting, attributed to the
run that caused it.

Does not catch: any corruption introduced AFTER the publish step. That is exactly the
2026-08-18 shape, and it is why this decision ships alongside — not instead of — the
push-path work named in `DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD`. Two different
holes; arming this gate closes one of them.

### Reverting

One-character revert of the env value. If a spurious red blocks a nightly, set it back to
"0" in a same-day PR, record why, and fix the underlying assertion — do not leave it
disarmed silently, and do not re-derive a new precondition without writing it down the way
#5516 did.

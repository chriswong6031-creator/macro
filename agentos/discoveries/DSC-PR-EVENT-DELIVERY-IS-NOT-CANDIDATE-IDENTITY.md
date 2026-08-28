---
key: PR-EVENT-DELIVERY-IS-NOT-CANDIDATE-IDENTITY
claim: >
  PR #6223 proved two independent ways that pull-request event metadata can be
  causally stale while the candidate is unchanged: active ci-authority/main run
  32590096081 rejected exact head 725f9867 because the event base SHA no longer
  equalled the live tip of the same main ref, and delayed closed-event run
  32590097404 arrived after reopened semantic run 32590096269 and cancelled that
  newer proof through their shared concurrency group before ci-plan executed.
falsifier: >
  Run `gh run view 32590096081 --repo
  mastermindx-market-intelligence/macro --log` plus `gh run view 32590096269
  --repo mastermindx-market-intelligence/macro --json conclusion,jobs` and show
  either that the authority rejection involved a changed subject head, head
  repository, base repository, base ref, author, actor permission, or
  changed-file inventory rather than same-ref base advancement, or that run
  32590096269 reached ci-plan and was not concurrency-cancelled by the delayed
  closed-event run 32590097404.
so_what: >
  CI authority must bind candidate identity and target base ref while retaining
  event and observed base SHAs as provenance; exact integration composition stays
  with semantic CI's synthetic-merge parent proof. A closed lifecycle event must
  not trigger semantic CI or share its concurrency slot, because event delivery
  order is not a cancellation protocol and cancel-in-progress cannot protect a
  pending proof from same-group replacement.
kind: landmine
verified_at: 2026-08-22
verified_by: >
  `gh run view 32590096081 --repo mastermindx-market-intelligence/macro
  --log` records event base 2a728891, observed trusted main 0ea350fb, exact
  subject 725f9867, and reason event_head_base_or_author_drift; `gh run view
  32590096269 --repo mastermindx-market-intelligence/macro --json conclusion,jobs`
  records cancelled ci-plan/contract-delta/packs; `gh run view 32590097404
  --repo mastermindx-market-intelligence/macro --json event,createdAt,jobs`
  identifies the delayed closed-event sibling that superseded it.
scope:
  - macro
  - ci-merge-control-plane
  - "scripts/ci_authority.py"
  - ".github/workflows/ci.yml"
confidence: verified
---

## Boundary

This does not make a mutable base tip irrelevant. The event base SHA and each
observed live base SHA remain diagnostic provenance, and semantic CI continues to
bind its exact tested merge to parent 1 as the tested base and parent 2 as the
subject head. The discovery is narrower: base-tip equality is not candidate
authority, and lifecycle event order is not a safe implicit cancellation channel.

The changed-file API also has no atomic snapshot token. When a same-ref base move
is observed across pagination, candidate authority must reacquire the bounded
inventory once and require the second enumeration to be bracketed by one stable
live base SHA; a head/ref/repository/author/count mutation or a second base move
still fails closed. An unobservable platform-level ABA window remains a GitHub
API residual, not a claim that the controller has an atomic snapshot.

# Options Issue Desk R6.2-A — frozen transport and authority contract

Status: private operator-research transport only. This document registers no alpha
claim, performance study, rank change, or automated execution authority.

## Scope

`options.issue_desk/v1` may snapshot active BULL Macro plans in their existing source
order and present display-only Options Prophet, vol-regime, and optional GEX context.
It cannot alter Macro plan ordering, admission, rank, gate, sizing, U-CHAIN, H+60
episode ownership, or brokerage state. All five authority flags remain false.

## Immutable lifecycle

`PENDING_REVIEW -> ISSUED | REJECTED` is terminal in v1. A stable proposal ID is
derived from the Macro plan ID. A source update can create a higher revision only while
the plan remains pending; stale revisions are unreviewable and a terminal plan cannot
reopen without a genuinely new Macro plan ID. GET exposes the latest revision only.

The private 0700 state directory contains fsync'd, flock-protected, append-only JSONL
proposal and decision ledgers (0600). They are never mirrored to Git, public R2, site,
or Supabase. Exact proposal, decision, event, and root `available_at` clocks are frozen;
the root availability clock bounds every returned child receipt.

## Approval law

Only a verified operator may approve. Approval needs an attested underlying BULL geometry,
CALL OCC/right/strike/expiry/quantity, contemporaneous ordered NBBO, spread and quote
provenance, fractional risk receipt, and portfolio-fit receipt. The issue cap is four
new plans in the rolling three real NYSE sessions. Active issued plans also reject a
duplicate symbol, a third sleeve member, or a second correlation-cluster member.

Risk uses fractions only: `allocation_weight <= 0.25`, nonnegative
`loss_at_stop_weight <= allocation_weight`, and `cash_after_weight` must reconcile to
one minus active allocation after issuance. The decision freezes portfolio state before
and after. This is an operator-issued research plan, never a brokerage order, fill, or
managed position.

## Transport fixture

The test transport fixture uses synthetic LMT values: reference 582.74, trigger 595,
stop/invalidation 525, no-chase 610, T1 700, T2 750, minimum hold 30 days; a Sep-18
600-call at 16.50 coherent NBBO. It is solely a byte-preservation test, not a
recommendation.

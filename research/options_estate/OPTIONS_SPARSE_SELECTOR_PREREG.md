# Sparse exact-option selector — activation preregistration

Status: **draft registered, selector inactive, zero prospective candidates**

Machine receipt:
`research/options_estate/sparse_selector_preregistration_receipt_v1.json`

Receipt SHA-256:
`49d0fa742383e86d8907fec60e47d733788d8879e394d85c8e6a6ac0d3f1a878`

Frozen MomoEdge benchmark digest:
`20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42`

The benchmark registration is bound as a full-file receipt, not only as a
parsed-object digest: 25,677 bytes, SHA-256
`a093804a2394ad5deff01181d2680eea64fa208f7f1d7e0a013c9cce3d806a63`,
registered at `2026-08-11T14:30:19Z` from baseline commit
`e1100ee158a8b18576bbc6130276ef6f8becd373`. The first `origin/main` commit
containing the exact benchmark digest is
`c46daec89ce2f25bdff85200eaf29f6de3e1572e` at
`2026-08-11T15:47:06Z`, so `2026-08-11T15:47:06Z` is the effective benchmark
freeze. The candidate, decision, evidence, source-campaign, and complete
selector-rule digests are all recorded separately.

## What is registered

This slice freezes the smallest honest prerequisite for a future sparse
exact-option selector. It does not activate one.

At registration, the only committed campaign file is the eight-row
`options.signal_campaign/v1` retrospective ledger frozen in the MomoEdge
benchmark. Its exact SHA-256 is
`db326f5c772ab417c43b8579ad50abb0434916922bda3a13c2da5b8303813910`.
All eight rows predate the benchmark registration floor, carry
`evidence_phase=retrospective_discovery`, abstain, are training-ineligible, and
have every authority flag false. Version 1 is permanently ineligible for the
prospective denominator.

The activation manifest therefore has:

- zero prospective candidates;
- zero decisions;
- zero abstain decisions;
- zero proposals;
- zero silent drops; and
- one global `NO_PROSPECTIVE_CANDIDATES` abstention.

Empty-set reconciliation is recorded as a vacuous one-to-one match, but is
explicitly **not** a covered-session receipt and does not satisfy the frozen
`SP_SPARSE_ABSTENTION` gate.

## Frozen future denominator rule

A later governed implementation may admit only
`options.signal_campaign/v2` rows first observed after both the selector freeze
and the benchmark freeze. The selector boundary is preregistered at
`2026-08-12T13:30:00Z`, the next NYSE session open after the final campaign-v2
and W1A context dependencies landed on `origin/main` and the integrated
selector rule was finalized. The exact selector rule digest must itself reach
`origin/main` before that boundary. Its first-main commit cannot be
self-referenced by these same content-identified bytes, so those two audit
fields remain honestly null in the premerge receipt. If the hosting
precondition misses the boundary, this version stays in global abstention and a
new version with a later NYSE boundary is required. It may not backdate or
reinterpret any row as prospective.

The campaign-v2 source contract uses the same `2026-08-12T13:30:00Z` forward
boundary. Every source row before it is retrospective and permanently excluded
from this selector cohort; every legacy v1 row remains ineligible forever.

Observation time cannot make an old row prospective. A candidate must have
`formed_at == members[-1].available_at`, and both immutable source clocks must
be at or after both effective freezes. The selector observation must then be
causal and no earlier than those source clocks. A campaign formed before either
freeze remains ineligible even if it is first observed days later.

For each stable campaign id, the first prospectively observed revision freezes
one candidate. A content-addressed candidate manifest must be immutable and
durable before any decision. Later arrivals wait for the next manifest cycle;
same-identity/same-bytes replay is idempotent and a conflicting duplicate fails
closed. Candidate order is fixed by `(candidate_available_at, candidate_id)`.

Every manifested candidate must receive exactly one decision by the next
selector cycle:

- `abstain`; or
- `propose`, meaning only a private research-review proposal, never an issued
  plan, pick, alert, position, or order.

There is no score, rank, quota, or forced fill. Zero proposals is valid. No
NYSE session may have more than three proposals; otherwise-complete candidates
beyond the deterministic cap abstain with `SESSION_PROPOSAL_CAP_REACHED`.

Proposal clocks use `decision_event_at <= decision_available_at`. Both clocks
must fall in the same `America/New_York` RTH window under the existing
`nyse_session_window_recurring_schedule/v1` implementation, with market open
inclusive and market close exclusive. The implementation includes its recurring
13:00 ET early closes. Non-session, unresolved, cross-session, premarket, and
post-close proposals abstain with `DECISION_OUTSIDE_NYSE_RTH`. The cap bucket is
that exact session date; proposals are evaluated in fixed
`(candidate_available_at, candidate_id)` order and the fourth and later passing
candidates abstain. The exact calendar implementation bytes are receipted.

## Required truth receipts

A proposal requires the campaign's exact ticker, right, expiration, strike, and
canonical strike key. Every shared field must equal the mark and lifecycle
identity exactly. The mark and lifecycle must also match exactly on root,
right, expiry, strike, millistrike, and 21-character OCC symbol. Fuzzy ticker
matching or deriving a missing OCC identity is forbidden.

All four evidence families must validate before a proposal:

1. exact `options.signal_campaign/v2` row and source-prefix receipt;
2. durable `options.market_memory_context_receipt_head/v1` plus its exact
   reference set. Campaign v2 binds through its exact final-member source row to
   the existing episode-owner `options.market_memory_context_reference/v1`:
   source-prefix bytes, row number, row SHA, episode id, event time,
   `available_at`, campaign `formed_at`, and exact contract group must all join.
   The query must use the reviewed SPY `{subject_id, instrument_id}` from the
   receipted canary config, the episode `event_time`, exact `available_at`,
   `mode=operational_pit`, and no fallback;
   `exact_requested_as_of_context_absent` abstains;
3. host-private `prophet.option_mark_observation/v1` content pointer, exact
   stable plan identity, admitted mark row, and no NBBO/execution inference; and
4. host-private `prophet.option_shadow_lifecycle_event/v1` and
   `prophet.option_shadow_lifecycle_state/v1`. The exact merged #5355 event
   schema and validator implementation bytes are receipted. State is bound by
   its real fields: `activation` and `lifecycle_head` event pointers,
   `ledger_cursor`, `mark_cursor`, `enrollments`, `terminals`, and
   `latest_marks`. The head must reach the activation root without a cycle;
   activation payload boundaries, the canonical-ledger prefix, mark ancestry,
   enrollment event, exact plan/contract, and drift state must validate. An open
   enrollment with no terminal is required to propose; an existing terminal
   abstains.

Missing, stale, unavailable, mismatched, drifted, broken-chain, or
authority-bearing evidence abstains with a frozen reason-code vector. A public
current-marks payload cannot replace the private mark chain. An underlying
return, EOD mark, trade-paired midpoint, or reconstructed quote cannot create
option P&L or execution evidence.

The durable mark prerequisite from #5350, Market Memory receipt path from #5353,
and lifecycle contract from #5355 are merged zero-authority inputs. The live
lifecycle has an activation head but no durable enrollment because the observed
BA quote was stale, so it contributes no eligible proposal. Campaign-v2 #5362
is merged at `d8e290032710d84e538c32af0d58358a16407c88`. This registration binds its
final `origin/main` schema as 7,177 bytes / SHA-256
`65ce2f0fe1cb16dfca58949a85562645be4a41eb454b5ce243c16011c8a251a3`
and runtime as 46,774 bytes / SHA-256
`f5d0a83c7fd35ee219aad448cef7384df98e1ee04b87d36ae631b0d273e4310c`.
The W1A crash-safe context path is merged as #5373 at
`6e2c3f5e0ce3bd94eb00e0fad8fee353ae905aa7`; this registration rebinds the
context-reference validator to its final 45,021 bytes / SHA-256
`7d3b410f6997a29299728b1f806956781803a89053f0cf8e016c315c3c296f82`.
Any dependency drift forces abstention. The current activation snapshot still
has no prospective candidate, no decision, and no authority; the only valid
output remains global abstention.

## Required falsifiers before activation

A future selector implementation must prove all of the following on its exact
head before it may emit a covered-session manifest:

- late arrivals cannot enter an already frozen manifest;
- reordered inputs produce identical manifests and decisions;
- same-byte duplicates are idempotent and conflicting duplicates fail;
- missing or extra decisions fail one-to-one reconciliation;
- a retrospective or digest-mismatched row can never enter the denominator;
- a pre-freeze `formed_at` or final-member `available_at` can never be cured by
  delayed observation;
- campaign v2 cannot use a campaign-v1 context owner or detach from its exact
  final episode owner/query;
- every missing options, Konseki, mark, or lifecycle receipt abstains;
- exact-contract or stable-plan identity drift abstains;
- zero-candidate and all-fail sessions emit zero proposals;
- more than three evidence-complete candidates produce exactly three proposals
  and reason-coded cap abstentions in the exact NYSE RTH session bucket,
  including early-close and close-boundary cases, with no score or quota; and
- every authority, public-output, Prophet, Neural Web, training, execution,
  trade, return, and completion-claim flag stays false.

Any candidate, decision, lifecycle, quote, or metric rule change creates a new
version and a new forward cohort. This registration cannot be reinterpreted in
place.

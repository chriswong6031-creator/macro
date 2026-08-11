# Sparse exact-option selector — activation preregistration

Status: **registered, selector inactive, zero prospective candidates**

Machine receipt:
`research/options_estate/sparse_selector_preregistration_receipt_v1.json`

Receipt SHA-256:
`79e8d1b135a6d528b34b5a57d3bbd1be68ff15015fc4b071f4ad368ec698033b`

Frozen MomoEdge benchmark digest:
`20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42`

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
and the benchmark freeze. The effective selector freeze is the later of the
registration clock and the first `origin/main` commit containing the exact rule
digest. Version 1 rows remain ineligible forever.

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

## Required truth receipts

A proposal requires the campaign's exact ticker, right, expiration, strike, and
canonical strike key. Every shared field must equal the mark and lifecycle
identity exactly. The mark and lifecycle must also match exactly on root,
right, expiry, strike, millistrike, and 21-character OCC symbol. Fuzzy ticker
matching or deriving a missing OCC identity is forbidden.

All four evidence families must validate before a proposal:

1. exact `options.signal_campaign/v2` row and source-prefix receipt;
2. durable `options.market_memory_context_receipt_head/v1` plus its exact
   reference set for `{subject_id, instrument_id, event_time, available_at,
   mode=operational_pit}`; `exact_requested_as_of_context_absent` abstains;
3. host-private `prophet.option_mark_observation/v1` content pointer, exact
   stable plan identity, admitted mark row, and no NBBO/execution inference; and
4. host-private `prophet.option_shadow_lifecycle_event/v1` pointer, validated
   lifecycle head, activation boundary, canonical-ledger receipt, mark-chain
   pointer, stable plan identity, and a prior durable enrollment or terminal.

Missing, stale, unavailable, mismatched, drifted, broken-chain, or
authority-bearing evidence abstains with a frozen reason-code vector. A public
current-marks payload cannot replace the private mark chain. An underlying
return, EOD mark, trade-paired midpoint, or reconstructed quote cannot create
option P&L or execution evidence.

At registration, the durable mark prerequisite from #5350 and the durable
Market Memory receipt path from #5353 were available as zero-authority inputs.
The #5355 lifecycle and #5362 campaign-v2 work were not yet merged and therefore
were not treated as live evidence. Their schema names are preregistered only as
future fail-closed requirements; absence means abstention, never fallback.

## Required falsifiers before activation

A future selector implementation must prove all of the following on its exact
head before it may emit a covered-session manifest:

- late arrivals cannot enter an already frozen manifest;
- reordered inputs produce identical manifests and decisions;
- same-byte duplicates are idempotent and conflicting duplicates fail;
- missing or extra decisions fail one-to-one reconciliation;
- a retrospective or digest-mismatched row can never enter the denominator;
- every missing options, Konseki, mark, or lifecycle receipt abstains;
- exact-contract or stable-plan identity drift abstains;
- zero-candidate and all-fail sessions emit zero proposals;
- more than three evidence-complete candidates produce exactly three proposals
  and reason-coded cap abstentions, with no score or quota; and
- every authority, public-output, Prophet, Neural Web, training, execution,
  trade, return, and completion-claim flag stays false.

Any candidate, decision, lifecycle, quote, or metric rule change creates a new
version and a new forward cohort. This registration cannot be reinterpreted in
place.

---
key: MARKET-OS-A1B-ACCEPTED-IN-PRODUCTION
question: >
  Has Market OS A1B — Portfolio Fast Start Import — satisfied its frozen production
  acceptance law so that the wave may be marked done and A2-A6 may become eligible
  for separate bounded commissions?
answer: >
  Yes. Sol accepts A1B in production. The merged A1B implementation on PR #6335
  was previously accepted at exact semantic head
  2bf5d335e5adf742486e0c2aca50b0765617da2d and landed as squash
  dd66f934e35a4629281656e854c6cc028dbd66d7. Its anonymous production vertical
  already passed. Operation market-os-a1b-auth-accept-20260826-sol-001 now proves
  the remaining authenticated journey on the designated disposable TEST identity:
  three reviewed temporary rows with stable RFC4122 identities, one live Save through
  the owner-scoped product path, authoritative Macro reread from 13 to 16 rows,
  independent Terminal conformance at 16 rows, unchanged four-Watchlist membership,
  exact removal of the three temporary rows through the authenticated product UI,
  immediate restoration to 13 rows in Macro and Terminal, and a delayed restoration
  reread with no temporary residue. A1B is DONE / PROVEN_LIVE. This ruling does not
  automatically start A2-A6.
rationale: >
  A1B completion required real authenticated canonical persistence rather than merge,
  deployment, CI, or anonymous localStorage proof. The production return exercises the
  exact remaining falsifier: paste and review three temporary holdings including a legal
  duplicate lot and nullable fields; preserve stable UUID identity; Save exactly once;
  observe the live Macro product acknowledge success only after its canonical portfolio
  changed; independently observe the same three rows in Terminal; prove Watchlists did
  not move; remove only the temporary identity set through the authenticated product UI;
  and re-read both products immediately and after a reconciliation window. Macro and
  Terminal both returned to the 13-row baseline and the four Watchlist membership seals
  were unchanged. No direct database write, service-role credential, administrator
  bypass, second persistence path, blind retry, Chairman real-book substitution, schema
  change, Terminal code change, or A2-A6 work occurred. The reported same-page Portfolio
  mode-tab badge remained at 13 while the authoritative body/table and Terminal correctly
  showed 16; because canonical persisted state, authoritative reread, cross-product
  conformance, cleanup, and fresh reread were all correct, that observation is a
  nonblocking presentation-state lag defect rather than an A1B persistence or truth
  failure. It remains visible for a separate bounded UI-consistency follow-up.
alternatives:
  - option: Keep A1B BUILT_NOT_PROVEN because the same-page mode badge briefly showed 13
    why_not: >
      The stale badge was not the authoritative Portfolio state: the canonical Macro
      body/table and Terminal both showed the exact 16-row post-write state, cleanup
      restored both products to 13, and fresh delayed rereads were internally
      consistent. Treating a transient secondary badge lag as failed canonical
      persistence would collapse UI polish into the production truth gate.
  - option: Repeat the authenticated production vertical for more evidence
    why_not: >
      The commissioned vertical passed and cleanup was exact. Repeating production
      mutation would add risk without resolving a remaining acceptance falsifier.
  - option: Start A2-A6 in the same operation
    why_not: >
      A1B acceptance and downstream implementation are separate operations. Each
      A2-A6 capability still requires its own current-state census, bounded commission,
      implementation carrier, and production proof.
evidence:
  - "Macro PR #6335 — A1B implementation; Sol FINAL REVIEW PASS comment 5417266507"
  - "A1B accepted implementation head 2bf5d335e5adf742486e0c2aca50b0765617da2d"
  - "A1B squash merge dd66f934e35a4629281656e854c6cc028dbd66d7"
  - "agentos/handoffs/MARKET-OS-2026-08-26-a1b-merged-deployed.md — merge/deploy and anonymous production receipt"
  - "operation market-os-a1b-auth-accept-20260826-sol-001 — authenticated production acceptance return reviewed by Sol"
  - "Authenticated baseline/restoration counts: Macro 13 -> 16 -> 13; Terminal 13 -> 16 -> 13"
  - "Authenticated Watchlist counts remained 55 / 24 / 53 / 2 with stable membership seals through write and cleanup"
affects: ["WS:MARKET-OS", "A1B", "A2-A6"]
confidence: high
reversibility: costly
decided_by: sol
decided_at: 2026-08-26
supersedes:
  - "WS:MARKET-OS A1B BUILT_NOT_PROVEN / PRODUCTION_WRITE_AUTH_REQUIRED continuation as of 854c2764e8756c8ebc6640796bf98e724e2479b7"
  - "Any still-open records projection, including PR #6504, that describes A1B as BUILT_NOT_PROVEN after this accepted production receipt"
---

## Capability delta

Before this ruling, A1B was merged and deployed but only the anonymous localStorage
path had real production proof. The authenticated canonical `portfolio_positions`
write/reread path remained unproven and therefore A1B was `BUILT_NOT_PROVEN`.

After this ruling, a designated disposable authenticated TEST identity completed the
real production fast-start journey through Macro, canonical owner-scoped persistence,
and Terminal, with legal duplicate-lot preservation, no Watchlist mutation, exact
cleanup, and immediate plus delayed restoration. A1B is `PROVEN_LIVE / DONE`.

## Nonblocking residue

During the transient same-page post-save state, the small Portfolio mode-tab badge
remained at the pre-write count `13` while the authoritative Portfolio body/table and
Terminal correctly reflected `16`. Fresh reread reconciled the badge after cleanup.
This is a separate UI-consistency defect. It does not reopen A1B production truth or
authority, but it should be repaired in a bounded follow-up so every visible count
refreshes from the same authoritative post-save state.

## What this ruling does not make true

- A2-A6 are not implemented or started by this decision.
- No CSV/broker import, persistent sizing-assumption workflow, My Market rail,
  universal add, or Watchlist workspace expansion is implied.
- No Terminal implementation change occurred during A1B acceptance.
- No service-role/direct-DB acceptance path is authorized by this proof.
- The designated TEST account's private identity, session, row UUIDs, and private
  fixture values are not durable acceptance metadata.

## Continuation law

A2-A6 are now dependency-eligible, but Sol must commission one independently useful
vertical at a time against fresh current Macro/Terminal truth. The transient Portfolio
mode-tab badge lag is a separate bounded follow-up and may proceed independently if it
remains path/authority-disjoint from the selected next Market OS wave.

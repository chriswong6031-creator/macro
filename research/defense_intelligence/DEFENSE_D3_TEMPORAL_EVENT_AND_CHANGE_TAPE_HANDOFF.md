# D3 — Temporal event v3 and Change Tape vertical

**Wave:** D3  
**Depends on:** D2 returned.  
**Status:** written, unauthorized. Bounded event families only — **no broad source expansion**.

## Observable mission

Four flows hit a bounded temporal contract and a user-visible Change Tape with exact before/after and distinct clocks:

1. **Award/action** — already live: P00032 obligation (L1).
2. **Opportunity amendment** — today typed `SOURCE_UNAVAILABLE` (L3). D3 may wire the event contract and UI for an amendment **if** a SAM rail is already collecting on main; it may **not** start a new collector program. If the rail is still down, ship the typed failure on the Tape, not fake notices.
3. **Budget/program change** — today `PROJECTION_MISSING` (L4). Same rule: contract + UI, no P-1 parser unless a separately scoped collection PR already landed on main.
4. **Correction** — live sibling `reported_obligation_balance_changed` on HC101319C0006 (`govws-70d45adde3342d5eca8f8014`) and deobligation `govws-aa6f1867ab7cae18de92e16c` (L2).

## Why it matters

Users currently see May actions titled like new news because `known_at` was labeled official in places and late discovery is easy to hide. D3 freezes clocks and invalidation.

## Authority precedence

GovRev owns award/action/opportunity/budget **facts**. Display only. No ranker.

## Verified current state

See `D0R_GRAPH_AND_CONTRACT_FREEZE.md` F3 and `D0R_RUNTIME_LINEAGES.md`. `known_at.semantic` must not be `"official"`. `is_late_discovery` already exists — D1/D3 must display it, not recompute it.

## Exact scope / files

- Workspace projector / event schema used by `government_procurement_workspace.v2`
- Change Tape row builder in `templates/government_revenue.html.j2` (`workspaceTitle`, inspector clocks)
- Action-version parquet readers already in engine (no new store)
- Tests around late discovery, negative amounts, before/after nulls

## Explicit non-goals

- No new SAM/P-1/FMS/GAO collectors inside D3.
- No cap raise “because we want more history” unless the contract versions.
- No frontend clock arithmetic.
- No #5424.

## User journey

1. Filter Change Tape to IRDM: see P00032 with **two clocks** and late chip.
2. Open balance-changed sibling: before/after obligation, not a second “new award”.
3. Open N0002415C2114 deobligation: minus sign, no forced ticker.
4. Opportunities/Budget: either a real amendment/PE line with source URL **or** the typed failure from D1.

## Data / time / null / correction

Clocks: `action_date` / `effective_at`, `known_at`/`first_seen_at`, `generated_at`, `as_of`. `source_published_at` remains a named gap — do not fill it with `known_at`. Invalidation = successor event id, never overwrite receipts.

## Failure states

`STALE`, `PARTIAL`, `SOURCE_UNAVAILABLE`, `PROJECTION_MISSING`, late discovery, correction successor.

## Ordered steps

1. Inventory which rails are actually collecting on main the day D3 starts.
2. Version only the event fields the Tape will show.
3. Inspector: before/after table + clock table.
4. Tests: P00032 late; deobligation negative; balance-changed not titled as new obligation.
5. Production entitled screenshots vs `d1-change-tape-rescued.html`.

## Rollback

Revert projector/UI PR. Keep v2 workspace bytes.

## Stop condition

The four families are either proven on the Tape or honestly typed-failed. Stop. Return, then D4.

## Continuation

Name which of the four were real events vs typed failures so D5 does not “fix” them by scraping.

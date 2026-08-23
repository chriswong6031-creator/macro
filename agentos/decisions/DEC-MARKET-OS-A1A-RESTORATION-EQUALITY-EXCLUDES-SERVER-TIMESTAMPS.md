---
key: MARKET-OS-A1A-RESTORATION-EQUALITY-EXCLUDES-SERVER-TIMESTAMPS
question: >
  Must an A1A test-account restoration reproduce the original created_at and
  updated_at values before the sealed canonical Portfolio rows may be evacuated
  and later restored?
answer: >
  No. For A1A test restoration only, created_at and updated_at are excluded from
  restoration equality because production owns both as server-generated metadata.
  Exact restoration still requires the same row ids, authenticated owner, ticker,
  shares, entry price, entry date, notes, status, row count, open and closed counts,
  duplicate multiplicity, unchanged Watchlists, and Macro-Terminal canonical
  agreement. The authoritative ordered row-id sequence is sealed and compared as a
  separate invariant so regenerated timestamps cannot silently reorder the book.
rationale: >
  PR #6257 proved fail-closed that the existing authenticated owner-scoped path
  preserves an explicitly supplied row id and every tested semantic field while
  production rewrites created_at and updated_at. Requiring byte-equivalent server
  timestamps made the authorized cleanup postcondition unattainable even though the
  ownership and semantic record could be restored exactly. Excluding only those two
  server-owned fields makes the test-account restoration contract executable without
  weakening their product or database semantics, inventing a privileged API, or
  broadening restoration authority. A separate ordered-id seal preserves the user-visible
  book-order invariant that timestamp regeneration might otherwise conceal.
alternatives:
  - option: Add a privileged restoration API or service-role path that can preserve timestamps
    why_not: >
      A1A is a production acceptance program, not authority to create a new persistence
      mechanism or bypass ordinary owner-scoped RLS. The existing authenticated path is
      sufficient once server timestamps are correctly classified as metadata.
  - option: Continue requiring created_at and updated_at equality
    why_not: >
      The bounded production proof in PR #6257 showed that production rewrites both
      fields. Keeping that requirement would knowingly authorize an evacuation whose
      exact cleanup condition cannot be met.
  - option: Exclude row identity, ownership, order, or other semantic fields as well
    why_not: >
      Those fields define the user's canonical Portfolio and its multiplicity. Excluding
      any of them would convert a narrow metadata correction into a weaker product-truth
      contract and could hide ownership, duplication, sizing, status, or ordering drift.
evidence:
  - "PR #6257 preserves agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-blocker.md: the authenticated owner-scoped insert preserved the explicit id and semantic fields but production rewrote created_at and updated_at only."
  - "The same #6257 packet proves the temporary probe was exactly deleted, both products returned to the sealed 13-row Portfolio fingerprint, and both independent Watchlist seals remained unchanged."
  - "Sol ruling 2026-08-22 selected Path 2 and limited the exception to A1A restoration equality, with a mandatory new temporary-row proof before any canonical deletion."
  - "Mastermind protected Skillpack 1.0.0 at e1101eb2c1f17d801d480ded497b3fc1bb0ef18b requires unexpected work and canonical identities to be identified and preserved rather than reset, overwritten, or replaced by a second truth store."
affects:
  - "WS:MARKET-OS"
  - "A1A"
  - "agentos/handoffs/MARKET-OS-2026-08-22-a1a-restoration-blocker.md"
  - "portfolio_positions restoration acceptance"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-22
---

## Semantic-v2 equality

`portfolio_fixture_semantic_v2` compares every restored row on:

- row id and authenticated owner;
- ticker, shares, entry price, entry date, notes, and status;
- total row count, open and closed counts, and duplicate multiplicity;
- unchanged Watchlist membership and population seals; and
- Macro-Terminal canonical agreement.

The authoritative ordered row-id sequence is sealed independently and must reproduce
exactly. A matching multiset with a changed ordered-id sequence is a restoration failure.

Only `created_at` and `updated_at` are omitted from equality, and only for this bounded
A1A restoration operation. They remain production-owned metadata with unchanged product
and database semantics. The restore writer must omit them and let production generate
them; a changed value in either field is expected rather than a failure.

## Authorized restoration path

Restoration may use only the already-proven authenticated owner-scoped Supabase client
under ordinary RLS. It may supply the sealed original ids and semantic fields. It may not
use a service role, admin path, product API addition, schema change, new persistence
mechanism, or timestamp-preservation attempt.

Before any canonical row is deleted, one new controlled temporary row must pass the full
create, semantic-v2 seal, exact-receipt delete, same-id semantic restore without timestamp
inputs, Macro-Terminal conformance, expected timestamp-difference, permanent cleanup, and
baseline-integrity sequence. A changed id, semantic field, owner, multiplicity, Watchlist
state, or unexplained product order fails the proof.

## Authority boundary

This decision does not authorize canonical Portfolio evacuation. After the temporary-row
proof and fresh 13-row semantic-v2, ordered-id, and Watchlist seals pass, execution returns
to Sol for new action-time destructive authorization. Scene 9 remains prohibited and A1B
remains blocked.

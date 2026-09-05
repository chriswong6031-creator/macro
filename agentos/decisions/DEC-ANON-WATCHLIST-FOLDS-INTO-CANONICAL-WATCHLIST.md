---
key: ANON-WATCHLIST-FOLDS-INTO-CANONICAL-WATCHLIST
question: >
  Where does anonymous personal state (the pre-account local Watchlist) go after signup?
answer: >
  The anonymous local Watchlist folds idempotently into the existing canonical
  watchlists/watchlist_symbols plane after verified account creation. Fold is a set
  union; canonical server membership is the delete authority; no folded event or "saved"
  UI state may precede the canonical readback acknowledgement. The fold never creates a
  second cloud store and never writes Portfolio exposure.
rationale: >
  The local list is pre-account intent, and canonical account Watchlist truth already
  exists with a settled separate-truth ruling
  (DEC:MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE lineage).
  Preserving the visitor's list through signup is the entire promise of "Save My
  Market"; losing it or parking it in a parallel store would either break the promise or
  mint a second truth plane. Portfolio is ownership, Watchlist is attention — folding
  attention into portfolio_positions would corrupt risk calculations.
alternatives:
  - option: Keep the anonymous list in localStorage after signup, merged only at read time
    why_not: >
      Read-time merge makes membership device-local and unqueryable; retention and
      activation measurement need canonical membership, and cross-device return would
      silently show different lists.
  - option: Create a dedicated "saved insights" cloud table for folded anonymous state
    why_not: >
      Explicitly rejected by the no-rebuild census — a second saved-state store parallel
      to Watchlists is a second truth plane requiring perpetual reconciliation.
  - option: Discard the anonymous list at signup
    why_not: >
      Destroys the personal act that motivated registration; the journey's conversion
      mechanism is preservation of personally meaningful state.
evidence:
  - research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md §5.3 (fold conflict/partial-failure state law), §8 (no-rebuild boundary)
  - agentos/decisions/DEC-MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE.md (separate-truth ruling this composes with)
  - supabase/migrations/0004_analytics.sql and existing watchlists/watchlist_symbols schema (canonical plane already live)
affects:
  - "WS:COMMERCIAL-ACTIVATION"
  - "WS:MARKET-OS"
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-09-04
---

Ratified by direct Chairman grant to session claude/mmx-commercial-activation-03fe73 on
2026-09-04. Fold implementation is CA1B scope; CA1A only measures the anonymous side
(storage=local events) and must not implement any fold.

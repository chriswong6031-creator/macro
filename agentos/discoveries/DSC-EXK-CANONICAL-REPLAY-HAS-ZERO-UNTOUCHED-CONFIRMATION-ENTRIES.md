---
key: EXK-CANONICAL-REPLAY-HAS-ZERO-UNTOUCHED-CONFIRMATION-ENTRIES
claim: >
  At the Turn-4 replay pin, the canonical common EXK/SIL adjusted-close tape
  spans only 2023-01-03 through 2026-08-05 (900 sessions), and H2, H3, H4 and
  H4B have zero untouched entered episode origins.
falsifier: >
  gh run view 32350307307 --repo mastermindx-market-intelligence/macro --log
  | grep -E 'first_common_session|last_common_session|confirmatory_episode_n';
  a common start before 2023-01-03, end after 2026-08-05, or any H2/H3/H4/H4B
  confirmatory_episode_n above zero disproves this claim.
so_what: >
  Positive EXK confirmation-arm medians remain design-touched description and
  cannot support a trading claim or promotion. Stop tuning EXK and obtain the
  next proof from a price-blind, untouched cross-issuer panel.
kind: constraint
verified_at: 2026-08-20
verified_by: "gh run view 32350307307 --repo mastermindx-market-intelligence/macro --log; PR #6057"
scope: [macro, alpha-intelligence, WS:ALPHA-INTELLIGENCE-INTEGRATION]
confidence: verified
---

## Evidence detail

- EXK Parquet SHA-256: `c1a19bc98e6caecd0d2edf89747084863d422d70891a9bbf58e7d9ea1ce1fcd9`.
- SIL Parquet SHA-256: `39750160b985733e471749d46abe0f2767fa958faff68f0a27816020706aec39`.
- Replay v1.2 output SHA-256: `aa2a11691be2f982f368a17562fd4dcf81397cc1072dfbbf3abd68e0479eb9ff`.
- PR #6057 closed unmerged after two byte-identical runs.
- Nine economic episode origins precede the common-store start; the August 2026
  blockade follows its end. Six origins are measurable and five are design-touched.
- The sole untouched origin, October 2023 Guanacevi, enters H0/H1 but produces no
  H2/H3/H4/H4B signal within the frozen 60-session wait.

## Additional case-level discovery

The 2025 Terronera steel-delay episode generated an H3 entry and then
underperformed SIL by approximately 31% at 40 sessions and 22% at 60 sessions.
A 20-session relative breakout is therefore not a sufficient recovery condition,
even inside a recoverable event label.
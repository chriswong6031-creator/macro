---
key: EXK-CANONICAL-REPLAY-HAS-ZERO-UNTOUCHED-CONFIRMATION-ENTRIES
finding: >
  At the Turn-4 replay pin, the canonical common EXK/SIL adjusted-close tape
  spans only 2023-01-03 through 2026-08-05 (900 sessions), and no canonical
  SLV file exists. Nine economic episode origins are before the common-store
  start and the August 2026 blockade is after the common-store end. Six origins
  are measurable, five design-touched. The sole untouched origin (October 2023
  Guanacevi) produces H0/H1 entries but no H2/H3/H4/H4B signal within the frozen
  60-session wait. Therefore untouched confirmation-arm entered N is zero.
evidence:
  - "EXK parquet sha256 c1a19bc98e6caecd0d2edf89747084863d422d70891a9bbf58e7d9ea1ce1fcd9"
  - "SIL parquet sha256 39750160b985733e471749d46abe0f2767fa958faff68f0a27816020706aec39"
  - "replay v1.2 output sha256 aa2a11691be2f982f368a17562fd4dcf81397cc1072dfbbf3abd68e0479eb9ff"
  - "PR #6057 closed unmerged after two byte-identical runs"
impact: >
  Positive H2/H3/H4 descriptive medians cannot support a trading claim or
  promotion. The full 2016-2026 EXK hypothesis is not testable on the current
  canonical benchmark tape. EXK must stop being tuned and the next proof must
  use a blind cross-issuer panel.
falsifier: >
  A canonical, provenance-compatible benchmark history that lawfully covers the
  full event era could complete the frozen EXK replay, but it would not increase
  untouched N for rules designed from EXK. Only new untouched issuers can answer
  the promotion question.
confidence: high
discovered_by: sol
discovered_at: 2026-08-20
---

## Additional case-level discovery

The 2025 Terronera steel-delay episode generated an H3 entry and then
underperformed SIL by approximately 31% at 40 sessions and 22% at 60 sessions.
A 20-session relative breakout is therefore not a sufficient recovery condition,
even inside a recoverable event label.

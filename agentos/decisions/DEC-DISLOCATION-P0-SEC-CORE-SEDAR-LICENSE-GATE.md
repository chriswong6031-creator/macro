---
key: DISLOCATION-P0-SEC-CORE-SEDAR-LICENSE-GATE
question: >
  Which official-source universe should Cross-Issuer Dislocation P0 use after
  Turn 5 proved broad SEC candidate capacity but found that automated use of the
  public SEDAR+ website is rights-restricted?
answer: >
  P0.1 confirmatory extraction uses SEC-reporting issuers with exact 8-K or 6-K
  filing and document receipts. Native Canadian SEDAR+ issuers remain part of the
  product vision but are excluded from confirmatory automated extraction until a
  licensed SEDAR+ Data Distribution Service or equivalent first-party feed passes
  rights, clock, identity, correction and retention review.
rationale: >
  SEC Submissions, archive documents and full-text search provide lawful,
  programmable source discovery and exact filing identity across domestic and
  foreign private issuers. Turn 5's price-blind census established ample candidate
  capacity for all P0 event families. The public SEDAR+ terms prohibit automated
  scraping and database construction, while the CSA offers a Data Distribution
  Service for continuous-disclosure documents. Expanding P0 through prohibited
  automation would make the evidence rights-unsafe and noncanonical.
alternatives:
  - option: Scrape the public SEDAR+ search and document pages
    why_not: Violates stated automated-access and database-construction restrictions.
  - option: Drop all foreign issuers from P0
    why_not: SEC 6-K lawfully covers many foreign private issuers and preserves an international bridge.
  - option: Permit manual native Canadian cases in confirmatory P0
    why_not: Creates inconsistent selection coverage and operator-discretion bias.
evidence:
  - "PR #6061 source census sha256 2afc9a1ad3893703b4b0aac662b44420317ba979035787992d277ec4745064ac"
  - "PR #6062 FTS capacity sha256 24d691251c0f2bedb1d15d283bdd33df938f5e81030d116b23318b40cdacbe35"
  - "SEC EDGAR API documentation"
  - "Official SEDAR+ Terms of Use and Data Distribution Service FAQ"
affects:
  - research/dislocation_intelligence/
  - engine/fundamental_forensics/
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
review_by: 2026-11-20
---

## Reversal condition

A signed SEDAR+ Data Distribution Service or equivalent licensed first-party
agreement followed by a successful audit of exact clocks, correction history,
identity, rights-safe retention and replayability.
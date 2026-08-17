---
key: PROPHET-V4-THEIA-SOURCE-RIGHTS
question: >
  The Chairman's remembered "S&P theme dashboard" source is Theia Insights (TIIC
  taxonomy; Theme Watch Indices; the classification behind S&P's Thematics
  Dashboard). May Prophet V4 / the GMI theme graph ingest, mirror, or benchmark
  against it — and what is the default theme-classification source while no
  license exists?
answer: >
  Default ruling: build the Mastermind theme/micro-theme classification ORIGINALLY
  from lawful first-party, public, and already-licensed sources (Finviz local plane
  stays rights-gated internal per GMI W3A; curated baskets; filings; first-party
  computation). Theia/S&P materials are competitor-methodology research ONLY:
  no scraping, no constituent/taxonomy copying, no redistribution, no ingestion of
  TIIC/TWI data in any form absent a signed license. Public aggregate pages may be
  read manually for benchmark orientation under their terms, and nothing from them
  enters stores, features, or user surfaces. A licensed TIIC/TWI feed is recorded
  as a PROCUREMENT OPTION for the Chairman (it would supply an external
  classification/control benchmark and daily theme performance across 200+ themes);
  if purchased, it enters as a provider-classification membership source under the
  graph's rights gates — it does not replace the canonical graph.
rationale: >
  Masterplan law 21 (rights before use) and §12.4: a publicly visible dashboard
  grants no right to copy taxonomies, constituents, or histories. Repo archaeology
  at fc0557bb0873 found NO adapter/ingestion code, and found that GMI W3A already
  PREPARED the procurement question without deciding it:
  research/theme_graph/W3A_SOURCE_RIGHTS_AND_PROCUREMENT.md §5 enumerates what a
  Theia license must include to be worth routing into GMI (Level-4/5 taxonomy,
  company-theme exposure weights, PIT vintages, issuer-grain identity, provenance
  labeling), and config/theme_sources.yml carries a commented-out theia entry with
  rights_class unresolved ("commercial license required"). This DEC supplies the
  missing DEFAULT so builders are never ambiguous while the buy/no-buy stays open:
  original lawful build proceeds now; W3A §5 remains the canonical license
  requirements list for the Chairman's procurement option. W3A's plane pattern
  (local source planes kept separate, probation mapping, rights gates) means a
  later license slots in as one more provider plane without rework.
alternatives:
  - option: License TIIC/TWI now and make it the canonical classification
    why_not: >
      Spend decision belongs to the Chairman; making an external vendor the
      CANONICAL truth also violates the no-graph-fork law's spirit — canonical
      identity must survive vendor churn. If licensed, it enters as a provider
      membership source, not as the graph spine.
  - option: Scrape the public S&P/Theia dashboards into stores
    why_not: >
      Violates law 21 and the sites' terms; poisons every downstream artifact with
      unlicensed data; DNR-class offense under the fleet's rights-fail-closed rule.
  - option: Do nothing until procurement is decided
    why_not: >
      Blocks V4-D1..D5 on a purchase that may never happen; the estate already has
      lawful theme planes (W3A) to extend.
evidence:
  - "grep -riE 'theia|tiic' at fc0557bb0873: no adapter/ingestion code; matches are research memos + a commented-out registry stub only"
  - "research/theme_graph/W3A_SOURCE_RIGHTS_AND_PROCUREMENT.md §5: procurement question list prepared, explicitly not decided ('W3 does not depend on Theia')"
  - "config/theme_sources.yml ~L49-52: theia entry commented out, rights_class: unresolved, auth_class: licensed"
  - "PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md §12.4, §5 law 21"
  - "GMI W3A precedent: PR #5718 rights-gated local theme plane, probation mapping (WS:GMI-THEME-GRAPH)"
affects:
  - WS:PROPHET-US-V4-RECOVERY
  - WS:GMI-THEME-GRAPH
  - research/prophet_v4/SOURCE_RIGHTS_AND_COVERAGE_REGISTRY.md
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-17
review_by: 2026-10-01
---

Supersedes nothing; first rights ruling on this source. If the Chairman purchases a
TIIC/TWI license, append the license scope here and update
`research/prophet_v4/SOURCE_RIGHTS_AND_COVERAGE_REGISTRY.md` — do not silently widen
ingestion. The V4-D1 census re-verifies this ruling against the estate at its own SHA.

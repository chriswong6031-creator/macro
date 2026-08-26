---
key: SRC-A1-FISCAL-ANCHOR-IS-ON-THE-PAYLOAD
claim: >
  The fiscal period end SRC-A1 needs to tell a rollover from an analyst
  revision is already present on the exact provider payload the collector
  fetches — Yahoo's earningsTrend module returns a per-item `endDate` — but
  yfinance's public earnings_estimate / revenue_estimate DataFrame accessors
  discard every item-level key except `period`, which is why period_end is
  100% null in the accrued artifact. A second, capture-free discriminator also
  already exists in the collected data: the `year_ago` observation is a
  reported actual, so on a quarterly rollover the whole block shifts one slot.
falsifier: >
  Read yfinance's Analysis._get_periodic_df (site-packages/yfinance/scrapers/
  analysis.py, ~lines 30-50): if it lifts any item-level key besides
  `item['period']`, the discard claim is wrong. For the anchor's existence,
  fetch one ticker's raw earningsTrend items and check for an `endDate` key —
  its absence on a name that has estimates refutes availability. For the
  alternative discriminator, check that `year_ago` is populated in
  data/revisions/expectation_observations.parquet; measured 2026-08-26 it is
  non-null on 1,568/1,596 EPS and 1,583/1,596 revenue rows.
so_what: >
  A future session must NOT conclude that fiscal rollover is undischargeable
  from the free estate, and must not escalate it as a vendor or authority gate,
  nor guess a fiscal mapping, nor build a cross-source join to an EDGAR or
  earnings-date owner to obtain it. Capturing the provider's own `endDate`
  verbatim into `period_end` is pure conformance with the frozen schema, which
  already reserves that field and forbids only GUESSED mapping. Two caveats
  bind the build: no public accessor exposes `endDate`, so capture reaches a
  private attribute and must degrade to typed UNAVAILABLE rather than guessing
  when the field is absent; and `endDate` presence is verified on one issuer
  only, so coverage across ADRs, recent IPOs and thin small caps is unmeasured.
kind: architecture
verified_at: 2026-08-26
verified_by: >
  yfinance Analysis._get_periodic_df at
  ~/.cache/mm-venv-mac-builder-3/lib/python3.12/site-packages/yfinance/
  scrapers/analysis.py:30-50 lifts only item['period'] and unpacks only the
  earningsEstimate/revenueEstimate sub-dict; identical in yfinance 1.5.1 at
  mm-venv-mac-builder-light, so it is not a version artifact. One live AAPL
  call (yfinance 1.6.0) showed raw earningsTrend item keys
  ['earningsEstimate','endDate','epsRevisions','epsTrend','growth','maxAge',
  'period','revenueEstimate'] with endDate 0q=2026-09-30, +1q=2026-12-31,
  0y=2026-09-30, +1y=2027-09-30 — matching AAPL's September fiscal year end,
  so it is the true fiscal period end rather than a calendar approximation.
  Collector nulls hardcoded at collectors/equity_revisions.py:246-248; lineage
  key lacks any fiscal field at :290.
scope:
  - "collectors/equity_revisions.py"
  - "data/revisions/expectation_observations.parquet"
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
confidence: verified
---

Because `endDate` sits at the trend-item level rather than inside the metric
sub-dict, ONE captured anchor serves both EPS and revenue for the same horizon.

Weaker candidates evaluated and rejected as rollover discriminators: `growth`
moves on ordinary revisions and so does not discriminate; the horizon label SET
is invariant at {0q, +1q, 0y, +1y} because the accessor slices the first four
items, so it can never signal a rollover; and `provider_payload_hash` changes
on any revision at all.

In-repo fiscal owners exist but are NOT the right source here and should not be
joined for this purpose: `collectors/edgar_eps.py` writes historical SEC period
ends to `data/edgar/eps_quarterly.parquet` (it pins the calendar but never names
the prospective 0q), and `collectors/equity_earnings.py` writes a next REPORT
date to `data/earnings/earnings.parquet` (a report date is not a period end).
Both would add mapping risk that the in-payload anchor does not carry.

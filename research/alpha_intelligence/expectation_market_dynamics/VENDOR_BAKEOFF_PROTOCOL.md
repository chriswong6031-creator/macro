# VEND-0 Institutional Estimates Vendor Bake-Off Protocol

## 1. Decision to support

Determine whether an institutional estimates source materially improves the
PIT expectation primitive over the free prospective collector, at acceptable
rights, cost and operational risk. The result may be `NO QUALIFIED VENDOR` or
`SAMPLE_REQUIRED`; a recommendation from marketing pages alone is forbidden.

## 2. Candidate classes

Evaluate credible products in at least these classes where access can be
lawfully obtained:

- institutional consensus/detail: FactSet Estimates, LSEG I/B/E/S, S&P Capital
  IQ Estimates;
- API-first financial datasets with PIT/revision claims: Intrinio, Financial
  Modeling Prep, Finnhub or comparable products;
- current/free reference: yfinance as the cost floor, never assumed to be a
  licensed historical-vintage substitute.

Vendor names are candidates, not endorsements. Availability, fields, terms and
pricing must be verified current from primary vendor materials and, for the
shortlist, a real sample/export/API response.

## 3. Common sample

Every vendor receives the same request:

- issuers: AAPL, MSFT, NVDA, MRNA, GOOG and GOOGL, plus two thin-coverage US
  issuers selected before payload inspection;
- metrics: EPS and revenue;
- horizons: all provided forward quarters and fiscal years;
- time span: maximum PIT/revision history available for a fixed recent 24-month
  window, plus current snapshot;
- fields: mean, median, high, low, contributor/analyst count, contributor detail
  where licensed, fiscal period, currency/unit, source timestamps, revision
  timestamps, actuals link and correction history;
- events: at least two known fiscal rollovers and one negative-EPS interval;
- delivery: raw sample plus schema/dictionary and terms governing storage,
  derived data, display, model training, audits and cancellation retention.

The request is immutable once the first payload is inspected. If a vendor will
not supply the sample or verifiable field-level documentation, record
`SAMPLE_NOT_OBTAINED`; do not interpolate a score.

## 4. Evidence packet per vendor

```text
vendor/product/version
access date and commercial contact/channel
sample request hash
payload hash and bytes (inside approved secure boundary)
field dictionary/version
coverage receipt by issuer/metric/horizon/date
PIT and revision demonstration
timestamp semantics
population/contributor semantics
correction behavior
identity behavior
rate limits/SLA
delivery and backfill mechanics
license/redistribution/derived-data/training/retention rights
security and audit requirements
price and minimum commitment
integration estimate
failure/degradation observations
```

Do not commit licensed sample bytes or confidential pricing/terms unless the
repository is explicitly approved for them. Commit redacted hashes, field-level
receipts and the secure evidence location/classification instead.

## 5. Scoring dimensions

The bake-off uses a predeclared decision matrix, not a product score exported to
runtime:

| Dimension | Weight | Hard gate? |
|---|---:|---|
| Demonstrated PIT vintage and revision fidelity | 25 | yes |
| EPS/revenue horizon and fiscal-period fidelity | 15 | yes |
| Population/contributor transparency | 10 | no |
| Timestamp/correction/identity semantics | 10 | yes |
| Coverage on common sample | 10 | no |
| Storage, derived-data, audit and model-use rights | 15 | yes |
| Operational delivery, rate limit and SLA | 5 | no |
| Integration complexity | 5 | no |
| Total cost/minimum commitment | 5 | no |

A failed hard gate is shown independently and cannot be hidden by the weighted
total. Scores compare procurement fitness only; they confer no analytical or
trading authority.

## 6. Return states

- `QUALIFIED_FOR_COMMERCIAL_REVIEW`: real sample and rights pass; Chairman or
  authorized commercial owner decides procurement.
- `CONDITIONAL`: material evidence or rights question remains.
- `NO_QUALIFIED_VENDOR`: all sampled candidates fail hard gates.
- `SAMPLE_REQUIRED`: public reconnaissance completed but no sufficient real
  samples; no winner declared.

VEND-0 is complete only with a receipt for every candidate and a defensible
return state. It never signs a contract or sends confidential material without
separate authority.

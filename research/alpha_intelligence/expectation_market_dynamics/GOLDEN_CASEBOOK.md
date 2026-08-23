# K3E-0 Golden and Adversarial Casebook

The casebook is fixed before advanced tuning. Cases test architecture and
failure honesty; they are not a hand-selected promotion sample.

| Case | Why it exists | Required behavior |
|---|---|---|
| AAPL liquid mega-cap | Dense coverage, multi-horizon consensus, options availability | Full decomposition; no assumption that density equals truth |
| MSFT steady revisions | Smooth path baseline | Persistence/EWMA should be hard to beat |
| NVDA 2023-style rapid repricing | Fast expectation and price changes | No look-ahead reconstruction; if PIT vintages are absent, historical model case is `UNESTIMABLE` |
| MRNA post-pandemic | Violent fiscal/horizon and sign changes | Negative/zero-crossing safe math; no percentage nonsense |
| GOOG/GOOGL | Multiple share classes for one issuer | Identity and response legs preserve share class; no silent ticker collapse |
| Thin small-cap coverage | Sparse panel and stale horizons | `PANEL_TOO_THIN`/`INSUFFICIENT_VINTAGES`, not confident phase |
| Negative EPS issuer | Denominator crosses zero | Absolute/unit-aware changes or abstention |
| Fiscal year rollover | `currentYear`/`nextYear` labels move across periods | Raw labels preserved; mapping transition explicit; no fake revision |
| Earnings observation with date-only availability | Intraday clock unknown | Conservative lawful session; same-day gap/intraday legs unestimable |
| 429/401 source response | Collection unavailable | Durable failed attempt; no all-null success row |
| Same payload rerun | Idempotency | No duplicate observation |
| Provider correction | Later values change without a new fiscal target | Append superseding observation; earlier as-known-at bytes remain |
| Baseline conflict | Near EPS rises, far revenue falls | Independent axes and `CONTESTED`; no scalar sign |
| Residual conflict | Raw price rises but peer/factor residual is null/negative | Lead with dual read |
| No options chain | Optional channel absent | Options leg `UNESTIMABLE`; other legs remain partial, visibly incomplete |
| Corporate action/halt | Return window contaminated | Affected horizon excluded with explicit reason |
| Vendor disagreement | Two vendors report different consensus/populations | Preserve both populations and clocks; no naive average |

## Acceptance assertions

Every implementation wave must include deterministic tests for the cases within
its scope. Historical cases without authentic PIT data test abstention and
clock behavior; they cannot be filled with later snapshots. A golden case does
not count as production proof and cannot substitute for a prospective holdout.

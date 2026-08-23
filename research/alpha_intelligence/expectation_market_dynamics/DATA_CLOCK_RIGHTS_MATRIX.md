# Data, Clock, And Rights Matrix

| plane | native object | primary time fields to preserve | correction behavior | rights / degradation law |
|---|---|---|---|---|
| expectation observations | provider-native revision / estimate records | provider-issued-at, source-available-at, collected-at, known-at, superseded-at | append / supersede only; no hindsight overwrite | `UNLICENSED`, `UNAVAILABLE`, `STALE`, `LOW_COVERAGE` are lawful outputs |
| event facts | owner-native event / workspace objects | event time, publication / acceptance time, first tradable implication where owner defines it | owner-native correction lineage only | K3E cannot widen event rights |
| financial semantics | FIF packets / revisions / statements | cutoff, filing acceptance, packet generation, known-at | owner-native packet and revision lineage | if not production admitted, surface that limit honestly |
| raw price path | canonical market data owners | trade / close timestamps, corporate-action adjustment basis | vendor-native revisions only | no synthetic intraday reconstruction here |
| residual path | existing residual owners | residual as-of, window definition, universe version | owner-native recompute lineage only | do not recompute or widen authority |
| options uncertainty | existing options owners | quote / surface times, source coverage, maturity basis | owner-native refresh / expiry only | uncovered names fail closed for options outputs |
| identity joins | current identity owners | identity version / validity windows where present | owner-native alias / mapping updates only | no guessed joins |

## K3E clock law

1. Every emitted K3E object carries both the owner-native observation clocks and
   the K3E composition time.
2. `known_at` is required for any historical replay or backtest consumer.
3. If owner clocks cannot support point-in-time honesty, the K3E emission is
   typed absent or degraded; it is not inferred from current state.
4. Fiscal-period clocks and market-session clocks remain separate. A fiscal
   rollover, earnings date movement, or calendar-year mapping correction is a
   lineage event, not a license to rewrite old expectation history.
5. Provider-issued time, provider-available time, collector-observed time, and
   system-known time must not be collapsed unless the source truly cannot
   distinguish them; when collapsed, the emitted object prints that limitation.
6. Rights limitations are part of the result. If analyst/provider-native detail
   is visible to a vendor sample but not licensed for storage or redistribution,
   K3E records the blocked capability rather than inventing a coarser synthetic
   substitute.

## Correction and deletion law

- Corrections supersede prior records; they do not mutate historical as-known
  values in place.
- Deleted or withdrawn source records remain as withdrawn observations where
  rights allow, with withdrawal clocks; otherwise the gap is `RIGHTS_BLOCKED`.
- A current provider snapshot may seed current state only. It may not be spread
  backward to create fake historical analyst coverage, estimate dispersion, or
  revision chronology.

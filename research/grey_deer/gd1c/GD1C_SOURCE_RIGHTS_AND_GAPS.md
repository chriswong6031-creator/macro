# GD-1C source rights, membership integrity, and named gaps

**Workstream:** `WS:GREY-DEER-RISK-INTELLIGENCE`
**Preregistration freeze:** `fce7bfeb8c925748ed92b54a7b19901c3a9f35c1`
**Primary lane:** `pit_membership` — **BLOCKED**
**Secondary lane:** `def_current_cf` — completed, counterfactual only

## Load-bearing primary gap

The repository cannot establish point-in-time membership for the
`leadership_crack.v1` cohort over 2016-01-04..2026-07-31.

- `data/baskets/membership.json` first enters tracked git history at
  `29721d07084c0332e1c2b5387a32addc1863c395` on 2026-06-14.
- The four current Leadership Crack baskets were curated in 2026. Their member
  rows carry retrospective `added` dates, mostly 2023-05-09, but no
  `available_at`, `observed_at`, vendor-constituent receipt, or versioned
  membership artifact from those dates.
- A retrospective `added` field is a backtest convention, not proof that the
  member was known, eligible, or in the named cohort at that historical clock.
- The file contains no versioned membership lineage for 2016–2022. The
  historical git blobs begin roughly six weeks before the design-era cutoff,
  not at the start of the ten-year sample.

Therefore the PRIMARY lane has zero guessed rows. Both GD-H1 and GD-H2 return
`BLOCKED`. This result is not cured by a large current-member price panel.

## Secondary input inventory

The content-addressed file inventory, row spans, columns, byte sizes, and SHA-256
digests are in `GD1C_RECONSTRUCTION_MANIFEST.json`.

| Source | Observed local coverage | Clock / rights treatment | Lawful GD-1C use |
|---|---|---|---|
| `data/baskets/membership.json` | Current union: 42 active names across four baskets | Current curated file; no PIT membership receipt | `def_current_cf` only |
| `data/baskets/ohlcv/<ticker>.parquet` | Older names generally 2014 onward; recent IPOs begin at their available history | Internal committed EOD vendor store; no per-row `available_at` | Current-definition truncated price replay, secondary only |
| `data/yahoo/SPY.parquet` | 1993 onward | Internal committed EOD vendor store; no per-row first-known clock | Benchmark and realized variance in secondary lane |
| `data/fred/DGS10.parquet` | 1962 onward, column `us10y` | Latest-revised daily file; no `published_at` / ALFRED vintage | Secondary rate counterfactual only |
| `data/fred/DGS30.parquet` | 1977 onward, column `us30y` | Latest-revised daily file; no `published_at` / ALFRED vintage | Secondary rate counterfactual only |
| `data/fred/VIXCLS.parquet` | 1990 onward, column `vix_close` | Latest-revised local FRED file; no `published_at` | Baseline/secondary description only |

No external redistribution or live-action right is inferred from local
possession of these files.

## Panel-integrity disclosure

The secondary lane is intentionally the current definition, not a cleaned-up
historical index:

- it uses the 42 names active in the 2026 current membership file across all
  historical dates where each name has prices;
- it consequently contains survivorship and theme-definition hindsight;
- recent IPOs have no pre-IPO rows, so member coverage varies materially over
  time;
- current `leadership_crack.v1` computes the carnage-share denominator from the
  current fresh-member count. Before recent IPOs exist, their missing drawdowns
  do not count as carnage while the denominator remains current-definition
  sized. GD-1C preserves that behavior because the commission requires the
  current definition; it does not call it historically correct.

These are reasons to keep the lane labeled `def_current_cf`, not reasons to
silently redesign the organ after outcome access.

## Additional temporal gaps

1. **Nominal rates:** DGS10/DGS30 have no first-available vintage clock in this
   checkout. Even with PIT membership, GD-H1 would fail 100% temporal-integrity
   promotion treatment until a lawful vintage source is supplied.
2. **Real yield:** `DFII10` exists locally but is likewise a latest-revised FRED
   file without a first-known vintage. Per prereg, the real-yield leg stays
   `UNAVAILABLE`; it does not block the secondary nominal test.
3. **VIX baseline:** `VIXCLS` is usable only as a secondary baseline here. The
   frozen H2 challenger itself uses SPY close-to-close realized-variance
   acceleration.
4. **Price availability clocks:** committed EOD files establish local content
   and coverage, not historical ingestion time. No intraday or anticipatory
   same-session claim is made.

## Minimum lawful substitute completed

GD-1C ran the current `leadership_crack.v1` code on truncated prices with the
current active-member union, wrote per-row code/input identities, and labeled
every numerical row `def_current_cf`. It also labeled rates
`latest_revised_no_available_at_secondary_only`.

This is the minimum lawful substitute named by the commission. It may challenge
or contextualize a construction, but it cannot:

- turn the primary verdict from `BLOCKED` into `PASS` or `FAIL`;
- be pooled with hypothetical PIT rows;
- claim the organ emitted those historical states;
- reopen GD-5; or
- grant market, Prophet, Portfolio, alert, rank, sizing, gate, or execution
  authority.

## What would unblock a future primary test

The minimum new evidence is a date-effective, first-known membership history
for the four cohort keys (including additions, removals, renames, delistings,
and the source clock for each change), plus lawful first-available nominal-rate
vintages. A present-day constituent list with backdated labels is not enough.

Any substitute membership construction changes the sample definition and
requires Fable approval plus a new preregistration version before outcomes are
reopened.

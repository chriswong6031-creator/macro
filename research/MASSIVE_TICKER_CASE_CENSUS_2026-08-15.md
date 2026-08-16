# Massive/Polygon vendor-ticker case census — 2026-08-15

## Verdict

Massive/Polygon ticker case is identity. The sweep found four class-(a) paths
where a case fold or case-insensitive filesystem could merge securities before a
durable result. All four are fixed in this change. One class-(b) full-market
snapshot join remains deliberately runtime-only. The remaining hits are safe
because they operate on a house-canonical/request ticker, validate shape/status
only, or now fail closed before a mixed-case vendor identity reaches an
uppercase-only marketing plane.

The measured collision families used as acceptance cases are:

| Vendor ticker | Security/price regime observed 2026-08-15 |
|---|---|
| `TPC` | Tutor Perini, about 94.67 |
| `TpC` | separate security, about 16.98 |
| `BCPC` | Balchem, about 177.14 |
| `BCpC` | Brunswick notes, about 23.9999 |

The reference behavior is case-exact matching with only the established
dot-to-dash universe spelling conversion. The source discovery supplied with PR
#5746 (`DSC-MASSIVE-TICKER-CASE-IS-IDENTITY`) was used as the audit baseline;
this census does not depend on that open PR being merged.

## Scope and method

The census covered `collectors/`, `engine/`, and `scripts/` and combined:

1. searches for `.upper()`, `.lower()`, `.casefold()`, pandas string folds, and
   ticker/symbol canonicalizers near Massive/Polygon clients and response fields;
2. searches for `ticker`, `symbol`, and parquet/JSON path construction near the
   Massive stock-day and Polygon fetch paths;
3. source tracing from vendor response -> key/path -> join -> persisted output;
4. a read-only inspection of the existing macOS `data/massive_stock_day` mirror;
5. case-pair tests using `TPC`/`TpC` and `BCPC`/`BCpC`.

No relevant `.casefold()` call was found. Lowercasing hits in the provider paths
were status, sentiment, URL/domain, or display slug operations unless explicitly
listed below.

## Classification

Definitions:

- **(a) durable collision:** identity can be merged in a persisted data artifact,
  cache/feed that is later published, or durable artifact key/path.
- **(b) ephemeral collision:** a runtime/in-memory map can alias identities, but
  the state is short-lived and is not an authoritative historical artifact.
- **(c) safe:** the folded value is already a house-canonical/request field, the
  fold is only a predicate/status/display operation, or mixed-case vendor input is
  explicitly rejected before the uppercase-only plane.

### Class (a): fixed

| Location | Pre-change collision | Durable consequence | Resolution |
|---|---|---|---|
| `collectors/massive_stock_day.py::_ticker_path` | The exact vendor ticker was used as `<ticker>.parquet`, but default macOS APFS folds `TPC.parquet` and `TpC.parquet` to one pathname. Per-day group writes then deduplicated the shared file by date, last row wins. | R2-canonical `data/massive_stock_day` history silently represented the last case variant written. | Preserve every all-uppercase legacy path. Mixed-case identities now use `__case_v1/<UTF-8-hex>.parquet`, so the complete path is distinct even on APFS. Collector counts/state scans and R2-recursive consumers include both layouts. |
| `collectors/polygon_news.py::parse_sentiment` | `insight.ticker.upper() == requested_ticker.upper()` counted `TpC` insight rows as `TPC` (and `BCpC` as `BCPC`). | Append-only `data/polygon/news_sentiment.parquet` could carry another security's article counts/sentiment under the requested ticker. | Compare the vendor identity case-exact after whitespace and dot-to-dash normalization only. |
| `engine/financial_news.py::_polygon_news` (now `_polygon_articles`) | Polygon article tickers were uppercased before lookup against case-exact insight keys. Mixed keys either collapsed or failed the insight lookup. | The financial-news feed/cache and its `by_ticker` index could mis-tag or lose per-security sentiment. | Normalize both Polygon ticker arrays and insight keys with the case-exact vendor key; tests prove four distinct `by_ticker` entries. |
| `engine/marketing/hot_tape_pack.py::{store_universe,scan_ticker}` | Massive parquet stems and worker tickers were uppercased before the candidate and record dictionaries were built. On a case-sensitive host, `TPC` and `TpC` were still last-row-wins in the pack. | `data/marketing/hot_tape_pack.json` silently held one security under the other's key/price. | Decode the APFS-safe Massive path and retain exact case through task, record, and durable pack keys. The pack test pins all four measured prices independently. |

The marketing quote/render plane is intentionally an uppercase house-symbol
universe. `engine/marketing/attention_source.py`,
`engine/marketing/movers_source.py`, and `scripts/hot_tape_radar.py` now reject a
mixed-case pack key at that boundary instead of relabeling it. Thus a `TpC` pack
record cannot become a `TPC` candidate, quote request, card, path, or R2 media key.
This is an explicit eligibility guard, not a case-insensitive join.

### Class (b): runtime-only

| Location | Why collision-capable | Why class (b) |
|---|---|---|
| `engine/live_breadth.py::canonical_symbol` + `scripts/live_breadth_poller.py::fetch_full_market` | The full-market Polygon snapshot is folded to the uppercase breadth-cache convention before insertion into `last_by_symbol`; two vendor case variants can overwrite in that process. | It is a short-lived display-only snapshot join against the fixed S&P 1500 breadth membership, and `site/live/` is an ignored, replace-in-place runtime overlay rather than a historical/security artifact. It should be split in a future breadth-contract revision if mixed-case names become eligible members. |

### Class (c): safe or query-bound

| Location/group | Classification reason |
|---|---|
| `collectors/massive_flatfiles.py` stock-day parsing | The vendor `ticker` column remains exact. The transient cache filename is date plus a hash of requested local underlyings, not a response ticker. |
| `collectors/polygon_options.py` | Underlying identity is the requested house ticker; Polygon's `strike_ticker` is retained exact. Durable partitions are date-based, not response-ticker filenames. |
| `scripts/build_polygon_universe.py` and `scripts/build_sp500_heatmap.py::refresh_caps` | Each request is issued for one house/local constituent and the checkpoint/reference row is keyed by that request. The response is not used to invent or fold a cross-sectional vendor key. |
| `scripts/build_polygon_intraday.py` | Output filenames come from the local chart universe/request. `.upper()` is only the explicit `--only` filter predicate; aggregate responses contain bars, not a cross-sectional response ticker. |
| `scripts/backfill_polygon_news_counts.py` | `.upper()` applies to an operator-supplied CLI ticker list. The response join is owned by the now case-exact `parse_sentiment`. |
| `engine/live_quotes.py` | `parse_polygon_snapshot` keys quotes by the exact vendor `row['ticker']`. Uppercasing is confined to US-route eligibility and response status strings. |
| `engine/options_universe.py` and Polygon GEX/chain builders | Symbols come from house config/basket membership and are request keys. Date/summary artifact names are constructed from those canonical local symbols, not a vendor response ticker. |
| `engine/theme_graph/capability.py::Substrate` | The uppercase set is an in-memory availability check over the legacy top-level house stores. The mixed-case Massive lane is nested and is not admitted to that uppercase theme-graph contract. No ticker-named artifact is written. |
| `engine/ticker_shape.py` | Uppercase is used to validate allowed characters/shape; the function returns the original stripped ticker, so it does not rewrite a join key. |
| Other `.upper()`/`.lower()` hits in `engine/financial_news.py`, Massive entitlement probes, and Polygon scripts | They belong to other providers, request/config values, API status, sentiment enum, timespan, URL/domain, or display text—not a Massive/Polygon response-ticker join or durable ticker name. |

## Artifact compatibility

All existing all-uppercase paths remain byte-for-byte compatible:

```text
data/massive_stock_day/TPC.parquet
data/massive_stock_day/BCPC.parquet
```

Mixed-case identities use a versioned nested lane:

```text
data/massive_stock_day/__case_v1/547043.parquet   # TpC
data/massive_stock_day/__case_v1/42437043.parquet # BCpC
```

The hex token is UTF-8 bytes, not a lowercased symbol or a hash, so it is
reversible and collision-free. The R2 publisher already uses `rglob('*')`, and
the R2 restore already maps arbitrary nested keys and creates parent
directories. `.gitignore` explicitly covers the new parquet lane.

Legacy consumers that only scan `data/massive_stock_day/*.parquet` keep their
existing uppercase universe and cannot mistake an encoded token for a ticker.
The durable Hot Tape pack is the consumer that opts into, decodes, and preserves
the mixed-case lane. Other direct lookups remain compatible for uppercase names;
`collectors.massive_stock_day.load_ticker()` resolves both layouts.

## Existing-store migration: rebuild, never rename

The existing Mac mirror is already contaminated. A read-only inspection on
2026-08-15 found only `TPC.parquet` and `BCPC.parquet`; there were no distinct
`TpC.parquet`/`BCpC.parquet` files. The mirror tip was 2026-07-02, with:

| Existing file | Tip close | Identity indicated by the price regime |
|---|---:|---|
| `TPC.parquet` | 17.90 | `TpC`, not Tutor Perini |
| `BCPC.parquet` | 24.10 | `BCpC`, not Balchem |

That is the predicted APFS last-row-wins failure. A parquet contains no ticker
column, and the collector deduplicates to one row per date, so a merged file has
discarded the losing security's rows. Renaming or copying it would merely create
two identically wrong histories.

Required operational repair for R2:

1. Keep the current R2 objects as rollback evidence; do not mutate them in place.
2. Replay the raw Massive `us_stocks_sip/day_aggs_v1` daily files across every
   retained session, filtering tickers case-exact.
3. Build each collision family in a temporary tree using the new path resolver:
   `TPC.parquet` plus `__case_v1/547043.parquet`, and `BCPC.parquet` plus
   `__case_v1/42437043.parquet`.
4. Verify independent date coverage, row counts, and sampled closes against the
   raw daily rows. At minimum, the 2026-08-15 acceptance prices must land in the
   correct identities and must not appear in their siblings.
5. Publish the rebuilt files through the normal guarded R2 path, advancing the R2
   manifest only after every object upload succeeds. Then restore to a default-
   APFS Mac and rerun the two-security tests before treating the store as repaired.
6. Repeat for every additional case-collision family discovered in raw vendor
   payloads; do not assume the two measured families are exhaustive.

This code change prevents new merges and documents the repair. It does **not**
claim the existing R2 historical objects have already been rebuilt.

## Acceptance tests

- `tests/test_massive_stock_day_fence.py`: APFS-casefold path inequality for both
  measured families and independent same-date parquet writes/reads.
- `tests/test_altdata_expansion.py`: case-exact Polygon sentiment selection.
- `tests/test_financial_news.py`: four distinct Polygon tags, sentiment keys, and
  `by_ticker` entries.
- `tests/test_marketing_hot_tape_pack.py`: four durable pack keys with the four
  measured prices.
- `tests/test_marketing_supply_feeds.py` and
  `tests/test_marketing_hot_tape_radar.py`: mixed-case vendor identities fail
  closed at uppercase-only marketing/quote boundaries instead of being aliased.

# BioCatalyst SNAPSHOT-ONBOARD A — corpus and contract freeze

**Status:** implementation freeze for Macro issue #6374

**Commission:** `WS:BPC-JV-RECON` composing with `WS:BIOCATALYST-CORE-PRODUCT`

**Claim-time protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@4d323d03e4151449a4b76abfdfefca1d56825fde` (`mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1`)

**Fresh Macro implementation base:** `6af1ccd17c0a00840e6eb29f627387b1ccd30b1f`

**Final pre-PR rebase base:** `f884a5ee1ebeda155f0b77f622f14ccffccf8ab9`

**Authority correction:** [Chairman input ruling on #6374](https://github.com/mastermindx-market-intelligence/macro/issues/6374#issuecomment-5403214136)

This receipt freezes the smallest lawful vertical: finite licensed bytes become immutable private source artifacts, deterministic normalized historical catalyst records, one entitlement-gated read projection, and one in-place BioCatalyst Historical Event History consumer. It is not a general BPC warehouse, live source registration, company-event replacement, security master, prediction surface, or authority expansion.

## 1. Authorized entrance corpus

The Chairman ruling supersedes the issue's stale W1–W4 entrance-gate wording. Parenthesized local/File Library filename suffixes are collision labels, not chronological evidence. The nine-sheet W4 payload is the canonical complete workbook; W1 is neither needed nor sought. W2/W3 are archaeology only.

| Admitted family | Local filename | Bytes | SHA-256 |
|---|---|---:|---|
| canonical W4 workbook | `BioPharmCatalyst_Tables.xlsx` | 353,040 | `946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535` |
| company reconciliation input | `BioPharmCatalyst_All_Companies_Sorted_By_Ticker.csv` | 86,364 | `a08afff0430c06138997f6b8a3e28fee63bb742eecdb4ea936c8bea99f225ee0` |
| Historical FDA | `biopharmcatalyst_historical_fda_all_verified_2009_2026.csv` | 5,630,777 | `f3852d34aad9b65d95e31db807f9509cfb84770eb91998533cb3687cea3d9002` |
| M&A inventory only | `biopharmcatalyst_mergers_acquisitions.csv` | 268,490 | `aa33b6dea553b982b32621a3ee759d20283c25b1e6d267289f6e7d38e5afb3fd` |
| hedge-fund inventory only | `biopharmcatalyst_hedge_funds.csv` | 63,192 | `fbb968bae5f4f5f6a33f21ee6c02db4450f26cf19aa765ae6e2a6e7212164640` |

Local filesystem creation/mtime clocks are observations of local availability, not source publication clocks: workbook `2026-08-17T00:51:14-07:00`; company CSV `2026-08-17T01:20:42-07:00`; Historical FDA `2026-08-17T00:55:47-07:00`; M&A `2026-08-17T00:56:31-07:00`; hedge funds `2026-08-17T00:56:23-07:00`. W4's File Library creation clock is separately recorded as `2026-08-16T08:38:14Z`. Neither clock may be backdated into event time.

### 1.1 W4 ordered worksheet census

The logical hashes cover canonical JSON of each worksheet's used-range address, values and formulas after parser load. The normalized hash additionally applies Unicode NFKC, strips a leading BOM, maps NBSP to space, collapses Unicode whitespace, trims strings, canonicalizes negative zero, serializes dates as ISO, and sorts object keys.

| # | Sheet | Range | Rows × columns | Exact logical SHA-256 | Normalized logical SHA-256 |
|---:|---|---|---:|---|---|
| 1 | Device Catalysts | `A1:L12` | 12 × 12 | `d08c572a9963d4ecd7657946f89af3f7e780e546002ad8b3660aa45706db8b56` | `a7dd8ab33a0591bd30ae0c8983130b58589f47df04457d736c9b407442986f69` |
| 2 | Device Pipeline | `A1:R840` | 840 × 18 | `c5b6111f4f56750f2de49ce917d6fb1ef859dd0e13d62f8918610d677fd9909a` | `58a20a65acef01e49582b93f9d0abb70587090829c2050bb2141e17f96d5de39` |
| 3 | PDUFA Calendar | `A1:J79` | 79 × 10 | `27d80a5ba797516d30451b748dbf2468d708e303977549e2921c01b6d6f8acc0` | `94cbb9f0add2b1d180b117dc4eac57335a45568afdd8c1bd23d8a0a0350f201a` |
| 4 | Device History | `A1:I667` | 667 × 9 | `3575c1d9e60169e564ee687b0126029e314fbd1536c4d17cef1b7fe6916d7446` | `a9b6ca986c4e6294cacc28e850bffd3bf83743c78a8a1c3d5dc7f9dd53da28a5` |
| 5 | IPO Calendar | `A1:G408` | 408 × 7 | `fa5dc0df8e0a55464af5f90388eec987ea958cf357190ebe65582522c88024f4` | `193d2a1aa620424e8132f93e0f1bd091dd1d1745b383ab3214186a6d091b76cf` |
| 6 | JPM26 Conference | `A1:L238` | 238 × 12 | `22ebf4369f6c099318c56a055e82e8d3841475aec309e206b552e37615dfe707` | `2bf288de635a3c3cef79c9d12da185ffa51bd743f0ded0435f3a600290cfc384` |
| 7 | Catalyst Impact | `A1:X125` | 125 × 24 | `bb0904b9e3857e5cac05db8391f3a9d31f29a91d7814c9f288ae98fa75df0d93` | `dfeb3c4424861ce37fed6b0155c1a18d16859e7bf0968af00df023fc3307710a` |
| 8 | Conferences | `A1:P151` | 151 × 16 | `a3a18dc013b722751b9684ce6e9902357d0236520c45b848002ce0c98f26b8ed` | `4aeee5e0f54fa794ce874f66c318c45e8c7723d5067020c1d43b488a99cb1bdf` |
| 9 | Earnings Calendar | `A1:M505` | 505 × 13 | `6278bc1b0af16ad6ef6ed6906846b01345762a78f6a8cecfaca664473861b20f` | `479a566bdb7602656fd15e02ab8be84755b31ce59f99a5accc05076d274d3ede` |

### 1.2 CSV logical census

| Family | Parsed rows including header | Columns | Exact logical SHA-256 | Normalized logical SHA-256 |
|---|---:|---:|---|---|
| All Companies | 135 | 13 | `338776c704e7f015b1e5e2977039b4e5ad5dca8e0d96bd565ce234cb1b3f7975` | `7e01e6db76ccb184b6866b23554f069c2728db5ef8c102fc324fc29a9b56a8fd` |
| Historical FDA | 15,701 | 13 | `d5527f3bf395bc49a9f6f22202634da674da272341961cbe3d00541eb0dd599d` | `3253eb5d55e9d9f92b91dbf364a86c045733d32ed2706289e6b27b89f1cb4827` |
| M&A | 1,434 | 13 | `14868abf8a6819feff0b614f7a9bc4debed428160008d74ae97aad27533f1ef8` | `5641de9b467eca46c19dff91c811ca1c829342454b223dfa4941e4f5eda58b16` |
| Hedge funds | 595 | 9 | `54a3338da49fd26be572370cab87a666863816f96f466b4b9d3e9ea1adde6e90` | `9588ee72f64dadf4a200e587d7b10d4a7a6fea9650b650559e0a2b7595d69e9e` |

### 1.3 Predecessor archaeology

Available six-sheet W2 (`df1890bcfa7578525249b09968d9395d16a6e732e4bdacaf20ef7e0bd5fba55c`) and eight-sheet W3 (`5b1f9535fc0e2f6e1f7b468907e6493edf3a954cdf7f9ab0dd075df7879a5e49`) compare to their successors as `ADDITIVE_SHEET_EXPORT_IDENTICAL_COMMON_CONTENT`. Every common sheet has identical dimensions and exact/normalized logical hashes. Raw XLSX package bytes differ. W2/W3 are not admitted production inputs, are not temporal vintages, and do not make W1 necessary.

## 2. Owner-plane ruling

- **Private source truth:** reuse `engine/biocatalyst/storage.py` and the dedicated `BIOCATALYST_R2_*` bucket. Immutable content-addressed keys are `biopharmcatalyst_jv_snapshot/raw/<sha256>/<safe-name>`, `.../normalized/<normalized-sha256>/events.jsonl`, and `.../manifests/<manifest-sha256>.json`. No raw byte, object key, private locator, BPC URL, or full licensed corpus enters git or the API.
- **Read projection:** one content-addressed, pointer-bound materialization under the existing `BIOCATALYST_PUBLIC_ROOT/historical_events/`. This is a subscriber read projection, not another source/object/event store. Promotion changes `current.json` last and retains the prior generation if a build/source attempt fails.
- **Identity:** read `data/reference/vendor_aliases.parquet` through `VendorAliasTable` using event date and existing vendor rows; read `security_master.parquet` through `IssuerMaster`. A symbol is evidence, never identity. Ambiguous, stale and unmatched cases remain typed. Current-only issuer relations are labeled current-only and never backdated.
- **Event ownership:** source-projection ids are deterministic `bpcjv_event_<sha256-prefix>` values over source family and normalized fact payload. Exact repeated exports therefore collapse to one event while the first deterministic source ordinal remains traceable; divergent collisions fail closed. These are not fiscal `evt_…` ids and are not canonical universal event identities. The row carries distinct event date, `source_available_at` (unknown unless source states it), and `observed_at`/capture clocks, preserving the `company_event.v1` lifecycle/publication discipline.
- **Rights:** `licensed_finite_snapshot`, facts/context/explain only. No scrape, continuous feed, probability, score, rank, alpha, trade stance, Prophet authority, or product likelihood.

## 3. First normalized families

1. Historical FDA: all structurally valid date-keyed rows after deterministic missing-index repair. Raw bytes remain unchanged. The repaired flag and original source ordinal are retained; BPC/company URLs are excluded. BPC prose is bounded to a concise licensed description for the entitled projection and cannot be used as model authority.
2. Device History: date-keyed device events with source-native device, indication, stage, event date, price-at-catalyst and price movement when structurally valid.
3. Device Pipeline: only date-bearing rows whose Catalyst Date parses as a historical/event date; current Price, 30-day move, market cap, volume, valuation, open/previous close and Options are excluded.

PDUFA, IPO, conference, earnings, Catalyst Impact, M&A and hedge-fund data remain inventoried but unprojected in this wave. All Companies is reconciliation evidence only.

## 4. Product-safe event contract

Every event has: source-projection id; source family/ordinal; licensed source/capture label; event date and precision; event family/stage; ticker/company lexical evidence; typed company/security identity state; source-native asset/device and indication labels; bounded factual description; optional price-at-event and movement only when source semantics make them event-clock fields; normalization/repair state; explicit unsafe/unavailable field names; and context-only authority.

Forbidden recursively from the public DTO: raw rows/bytes, SHA/hash/manifest receipts, private object keys/paths/locators, source URLs, BPC chrome, current/export-time Price/30-day change/market cap/volume/ADV/relative volume/open/previous close, options IV/OI/strike/bid/ask/last/expected move/current Options flags, company descriptions, M&A rows and hedge-fund rows.

The API returns typed `ready`, `empty`, `partial`, or `unavailable` state, corpus/family denominators, deterministic descending `(event_date, event_id)` order, query-bound opaque cursor, and exact filter echoes. Source unavailability may serve the last fully validated generation; it never advances the pointer.

## 5. Proof gates

The implementation must fail closed on missing file, byte mismatch, malformed workbook/header/row, unexpected left-shift count, duplicate event id, identity ambiguity, invalid date precision, poison leakage, rights refusal, pointer/hash mismatch, invalid filter/cursor and entitlement failure. Rebuilding from the same five bytes and same identity artifacts must be byte-identical. Mutation tests must flip common-sheet equality, left-shift repair classification and poison leakage. A real admitted event and a real repaired row must trace source ordinal → normalized artifact → identity state → API → browser row without recording licensed payload in git.

### 5.1 Exact-corpus fixed-point receipt

The check-by-default operator path was run twice against the five admitted files and the current `origin/main` Data OS `security_master.parquet` / `vendor_aliases.parquet` bytes. Both runs produced byte-identical safe summaries and the same local content-addressed projection:

- generation: `bpcjv_gen_755d98c85beb38603dacefcc`
- normalized JSONL SHA-256: `6a750dbf64b294ef111bdd0100630c69c1b298c8600287708b176247af2a712b`
- normalized JSONL bytes: `25,420,416`
- projection manifest SHA-256: `32b8230174a1b2251d255aefe8366058d1ac381ad5a3d3129e23dc5915eb7d63`
- current pointer SHA-256: `105bec99a9ee70d85ae68f6f1d93a7312c5313949f6bbf642516dafc585ced39`
- source rows / normalized historical events: `17,205 / 16,384`
- identity resolved / explicitly unresolved: `4,067 / 12,317`
- exact duplicate source projections collapsed: `409`
- normalized families: Historical FDA `15,295`; Device History `661`; capture-date-bounded Device Pipeline history `428`
- forward-due Device Pipeline rows excluded from the historical projection: `12` (retained in the `839`-row source-family denominator)
- licensed-description URL tokens deterministically replaced before projection: `24`; the closed runtime validator independently rejects any surviving URL/private locator value
- deterministic missing-index repairs: `4,404` of `15,700` Historical FDA source rows

The proof used a disposable local projection root. It did not upload private bytes, advance a production pointer, deploy, or print any raw row/private object locator.

### 5.2 Production-shaped real-Chrome receipt

Standard Chrome loaded the exact rendered branch assets against the real local generation above, the branch historical-event API with controlled `site_full` entitlement, and a controlled lawful-empty CT.gov Radar response. This is branch acceptance only, not deployed production acceptance.

- desktop `1600 × 1111`: dark/EN, light/EN, light/ZH and dark/ZH each rendered 50 of 16,384 events with zero document, history-panel or card overflow/escape;
- mobile `433 × 937`: dark/EN, light/EN, light/ZH and dark/ZH each retained the same zero-overflow geometry, single-column filters and localized labels/placeholders;
- combined real filter (`FATE`, regulatory, `2026-08-14` through `2026-08-14`, stage `Phase 2`, asset `FT819`) returned exactly one event;
- repaired trace: `historical_fda` source ordinal `13,899` → `bpcjv_event_6a0106b9b4c5642fee3ebb9b` → resolved Data OS identity → API → expanded EN/ZH row, visibly labeled `missing_row_index_unshifted` / deterministically repaired;
- unresolved trace: the real Lantheus query returned 18 events and the expanded product row visibly rendered `Identity unresolved` / `身份未解析`;
- the latest event date visible on the unfiltered history page was `2026-08-14`, before the `2026-08-17` capture; no future-due Device Pipeline row entered the historical projection;
- page-origin Chrome console warnings/errors: zero. Two `LavaMoatPlugin: using unlocked runtime` warnings were emitted solely by `chrome-extension://` origins and excluded from the page-origin verdict.

The controlled browser server and projection were local/disposable. No authenticated production session, private source object, deployment path or production pointer was modified.

Protected non-goals remain unchanged: no edits to `config/biocatalyst_sources.yml`, `config/biocatalyst_launch_slo_manifest.yml`, CT.gov cohort/cadence/soak, runtime registry, continuous BPC access, P1-2, M&A/ownership/options/alerts/Prophet, deployment, or self-merge.

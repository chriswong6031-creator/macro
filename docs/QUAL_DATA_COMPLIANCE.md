# Qualitative-Intelligence Program — Data Compliance Boundary

*Policy document. Audience: operator/maintainer. Grounding: `research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md` §D10 and `research/QUALITATIVE_INTELLIGENCE_MASTERPLAN.md` §8. Effective: 2026-07-02.*

---

## 1. Public-Source-Only Inventory

All qualitative-intelligence data entering the Mastermind Dashboard qualitative program is drawn exclusively from the following source categories. Legal character is noted for each.

### 1.1 US Regulatory Filings

| Source | Access | Legal character |
|---|---|---|
| SEC EDGAR full-text (8-K, 10-K, 10-Q, XBRL) | Free, keyless API; ~10 req/s fair-access limit | **Public regulatory disclosure.** EDGAR is a congressionally mandated public-access system. No MNPI: all content is simultaneously released to the market via the SEC's EDGAR notification system. Declared User-Agent + rate-limit compliance required. |
| SEC `company_tickers.json` (entity resolver) | Free, keyless | Same — public administrative data. |

### 1.2 Event and News Aggregates

| Source | Access | Legal character |
|---|---|---|
| GDELT 2.0 DOC API / GKG / BigQuery | Free (BigQuery egress only); 1 req / 5 s pacing enforced | **Aggregated published-news metadata.** GDELT re-processes publicly-accessible global news; no underlying article body is stored or re-served. Robots-respecting; no auth required. |
| Benzinga / Tiingo / Marketaux / Finnhub / Alpha Vantage wire feeds | Free / freemium tiers | **Published wire news.** ToS-compliant usage; redistribution limits honored (no raw-feed re-publication). Ticker-tagged headlines only — no article bodies re-stored. |
| White House RSS (`content:encoded`) | Public RSS feed | **Official executive-branch publication.** All items publicly released; timezone normalization (America/New_York) applied per `whitehouse_feed.py`. |

### 1.3 Congressional and Institutional Disclosures

| Source | Access | Legal character |
|---|---|---|
| Quiver Quantitative — Congress trades | Paid subscription | **Public disclosure data.** Derived from STOCK Act mandatory filings (House and Senate financial disclosures), themselves public records. Quiver's value is aggregation and normalization, not proprietary information. |
| Quiver — 13F Smart Money / Insider Form-4 | Paid subscription | **Public disclosure data.** SEC 13F and Form-4 are mandatory public filings; lag ≥45 days post-quarter-end for 13F, 2-business-day reporting window for Form-4. No MNPI: the relevant trades are stale by the time of disclosure. |
| Polygon / Finnhub market data | Polygon STANDARD (15-min delayed); Finnhub free tier | **Aggregated public-market data.** Delayed pricing only; no real-time order-book data. |

### 1.4 China Official Policy Corpora

| Source | Access | Legal character |
|---|---|---|
| gov.cn (State Council readouts) | Public HTML; browser UA required per VPS collector | **Official government publication.** Verbatim policy language, publicly issued. Impersonal aggregate — no personal data. |
| PBOC (archive ~6,089 records) | Public HTML | Same. |
| NDRC, CSRC, Politburo readouts | Public HTML | Same. |
| People's Daily front-page layout | Public HTML; prominence ordering only (no paywall) | Same. |
| Xinhua RSS / readouts | Public RSS | Same. |
| CNInfo (巨潮) — full-text filings, inquiry letters | Public portal; throttle enforced | **Public regulatory disclosure.** A-share and H-share companies are required to publish full-text filings here; SSE/SZSE/HKEX portals similarly. No MNPI from these sources: simultaneous market release. |

### 1.5 China Alternative Attention Data

| Source | Access | Legal character |
|---|---|---|
| akshare CN wires (Eastmoney / Futu / THS) | Free via akshare | **Published domestic news aggregates.** Tier-2 retail-oriented wires; no access credentials required. |
| THS (同花顺) concept-board membership / attention scores | Free via akshare | **Aggregated public-market data** (concept-board membership is public; attention scores are derived from on-platform public traffic). No personal data; aggregate index only. |
| Baidu Index | Public web query | **Aggregate search-volume index.** Baidu Index is an impersonal aggregate (query counts, not individual queries). No personal data collected or stored. |
| CCTV lianbo (央视联播) broadcast metadata | Public broadcast; order-preserved scrape via `ak.news_cctv` | **Published public broadcast.** Topic ordering and headline presence/absence only — no private communications. Backfill reaches to 2016-02 per probe [P4]. |
| GDELT `sourcelang` divergence (onshore-zh vs offshore-en) | See §1.2 | Same as GDELT above; tone series by language-subset only. |

---

## 2. Exclusions as Deliberate Policy

The following source categories are **scope boundaries, not oversights or budget constraints.** They are excluded because the supervision burden or legal exposure is incompatible with a solo-operator shop regardless of cost.

### 2.1 Expert Networks (US)

Expert networks (GLG, Third Bridge, AlphaSights, Guidepoint, AlphaSense expert-call tier, Tegus) are excluded.

The operative risk is MNPI exposure via the conduit pattern established in *United States v. Martoma* (SAC Capital, 2014): an expert engaged through a network passes information about a clinical trial that was simultaneously a material nonpublic fact. The network intermediary did not eliminate the MNPI character; it merely provided the conduit. A solo shop cannot carry the compliance overhead required to (a) vet every expert for MNPI proximity, (b) maintain a restricted-list regime that walls off trading around any expert session, and (c) document the basis for concluding each conversation fell below the MNPI threshold. Large-fund compliance teams exist precisely because this burden is non-trivial. For Mastermind, the risk/capacity equation is disqualifying regardless of the information's potential value.

### 2.2 Expert Networks (China) — Hard Legal Line

China expert networks (Capvision / 凯盛融英, and any equivalent) are excluded regardless of budget.

This is not a cost or capacity decision — it is a hard legal no-go. In March 2023, Chinese authorities raided Capvision's offices and subsequently detained staff; Bain & Company's Shanghai office was raided the same month; Mintz Group was fined USD 1.5 million and had staff detained. The legal basis is the expanded Anti-Espionage Law (反间谍法, amended 2023), under which gathering economic or corporate intelligence for a foreign party can constitute espionage. Unlike the US expert-network question (MNPI, manageable with process), the China question is criminal exposure for the information collector under Chinese law, with no compliance process that adequately mitigates it for a small foreign operator. This exclusion is permanent at current law.

### 2.3 Card and Transaction Panels

Consumer card/transaction data panels (Yipit, Earnest Research, Consumer Edge, Bloomberg Second Measure, and equivalents) are excluded.

These panels aggregate individual payment transactions. The data originates from bank partnerships or card-network agreements; the downstream compliance burden includes verifying that each data vendor's underlying consent framework is intact, that individual transaction records are appropriately anonymized at the cell level, and that the aggregate product does not permit re-identification. The supervisory overhead for a solo shop is not proportionate. The alternative — inferring revenue velocity from public government statistics (express-parcel volumes, electricity consumption, freight indices) — is preferred for any physical-activity nowcasting.

### 2.4 Web-Scrape Panels Adverse to ToS

Any systematic scraping operation that (a) requires authentication bypass, (b) is conducted at a scale or frequency explicitly prohibited in the site's robots.txt or Terms of Service, or (c) stores and redistributes copyrighted article bodies in bulk is excluded.

Concretely: Seeking Alpha / Motley Fool bulk transcript scraping, any platform that requires login to access full content, and social-media firehose access without a platform API agreement. Headline metadata from public RSS or publicly-indexed pages does not fall in this category.

---

## 3. The Mosaic Principle — Centralization Changes Convenience, Not Legal Character

The corroboration engine (`qbus` event-key / `echo_stats`) joins EDGAR filings, GDELT news events, Congressional trade disclosures, 13F filings, and Baidu attention data on a shared entity-resolved key. This centralization makes cross-source corroboration structurally automatic where it was previously invisible across siloed desks.

**The legal character of the aggregated output is unchanged from the legal character of its components:** every input is publicly released simultaneously to all market participants. Centralization changes convenience — it makes the join possible — not the MNPI status of the underlying information. The mosaic doctrine (see *SEC v. Bausch & Lomb*, 1977; Merrill Lynch No-Action Letter, 1974) holds that an analyst who assembles non-material public pieces into a material conclusion engages in legitimate analysis. The program's corroboration engine falls within this framework because no input is non-public.

**Standing rule:** If any future data source proposed for addition to the entity-resolved store could carry non-public material information (whether by scope, timing advantage, or information-conduit theory), it must not enter the store without:

1. A written compliance review recorded as a dated entry in §5 (Change Log) of this document, and
2. An explicit determination that the source meets the simultaneous-public-release standard or falls within a recognized safe harbor.

This standing rule applies to any new expert-network product, private-data partnership, or real-time exchange feed contemplated in future roadmap waves.

---

## 4. Operational Rules

### 4.1 SEC EDGAR

- Declared User-Agent set to a library-style identifier (not a browser UA) per EDGAR fair-access policy.
- Request rate: ≤10 req/s; backoff on HTTP 429.
- Point-in-time discipline: backtest entry anchored to `date_filed + 1 business day` (the `EDGAR same-day-close` leak, corrected per [P2] / W0 brief #10). Same-day trading on an 8-K filing is not legitimate in backtesting — the fix must remain in the codebase.

### 4.2 GDELT

- API pacing: 1 request per 5 seconds. Do not batch-burst.
- No raw article-body storage. GDELT provides metadata (title, URL, domain, seendate, tone score) — only these fields are retained.
- `sourcelang` field used to segment onshore-zh vs offshore-en populations for the divergence index; no individual-source tracking.

### 4.3 robots.txt and ToS Compliance

- All collectors check `robots.txt` before crawling. If a target explicitly disallows the collector's path, the collector skips and logs a warning.
- No scraping behind authentication walls.
- CN official corpora (gov.cn / PBOC / NDRC / CSRC): browser UA required for anti-bot bypass per VPS collector; leaf-directory targeting for NDRC to avoid broad crawl. Crawl depth and pacing are calibrated to avoid triggering rate-limit or IP blocks. Hash-based body-diff snapshots (sha256) stored, not full article bodies re-published.

### 4.4 China PIPL / DSL Posture

- The program collects **impersonal aggregate indices only** from Chinese sources: concept-board membership counts, attention aggregate scores, broadcast topic counts, search-volume indices. No personal data (names, IDs, transaction records, communication content) is collected, stored, or transmitted.
- The DSL (Data Security Law, 2021) "important data" classification applies to data that, in aggregate, could affect national security or public interest. The program's outputs (price-level indices, sector-rotation signals, policy-phrase occurrence counts) are not within this classification.
- Cross-border transmission of CN data: only impersonal, aggregated, market-derived indices are transmitted to the VPS (hosted outside mainland China). This is consistent with current DSL guidance for financial market research data that does not identify individuals or constitute "important data."

### 4.5 LLM Extraction

- LLM extraction (`qual_extraction.v1` contract) runs only on publicly-released text for which the program already holds a legitimate access right (EDGAR 8-K full text; White House RSS `content:encoded`; official Chinese policy corpora fetched under §4.3).
- Extraction outputs are labeled `machine_derived_context: true` in every artifact. They are not represented as verified facts; they are one analytical interpretation of publicly-available text.
- Model drift protocol: version-pinned `model_id` in config; a frozen 50-text anchor set is re-scored on any model change with a `field_agree_rate ≥ 0.85` gate before deployment.
- Transcript ingestion (earnings calls): transcripts from FMP or equivalent require a paid subscription; ToS redistribution restrictions apply. Full-text bodies must not be re-published. Extracted fields (tone, guidance delta, hedging density) may be stored as derived outputs.

---

## 5. Change Log

*This section is the compliance ledger. All material changes to source scope, exclusions, or operational rules are recorded here as dated entries.*

| Date | Entry | Author |
|---|---|---|
| 2026-07-02 | Initial document created per D10 (`research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md`) and `research/QUALITATIVE_INTELLIGENCE_MASTERPLAN.md` §8. Inventories §1–§4 established. Expert-network exclusions codified (US MNPI; China hard legal line). Mosaic standing rule established. | dashboard-bot / Claude Opus 4.8 |

---

*References: `research/QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md` (D10, §4 wave plan W7); `research/QUALITATIVE_INTELLIGENCE_MASTERPLAN.md` (§8 institutional-grade acquisition, §9 hub-and-spoke architecture). Legal precedents cited for informational context only; this document does not constitute legal advice.*

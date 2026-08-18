# B0 — Source and rights registry

**Lane:** GROK-B0 · **Date:** 2026-08-18 · **Pin:** `3d12412e561e`
**Scope:** official/primary sources for *active/discretionary funds and specialist managers*. Third-party aggregators are listed only as collision/rights hazards.
**Authority:** NONE. No capture is authorized by this table.

Claim tags: **PRIMARY SOURCE VERIFIED** · **CODE VERIFIED** · **INFERRED** · **UNKNOWN**.

---

## How to read a row

- **Adopt** = already collected or the lawful next source for an existing owner.
- **Candidate** = official, rights-plausible, not yet a house owner (or only partial).
- **Do not ingest** = aggregator / ToS / duplicate of an official feed.
- **Stopped** = a live Sol/DEC stop applies.

Redistribution column is **not legal advice**. It is the strongest statement this session can make from a public page or from code comments. A capture build still needs a source-rights verdict (PASS-0 §8).

---

## 1. Official US filings (manager books)

| Source | Complex / fund | Active / passive / systematic | Specialist? | Cadence | Shares / weights / SO / AUM | Explicit trades | Excludes create/redeem? | History | Rights / redistribution | Machine-readable | Clock / delay | Survivorship | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SEC EDGAR 13F-HR / 13F-HR/A / 13F-NT per CIK (`data.sec.gov/submissions`, `www.sec.gov/Archives`) | Filing manager (CIK). Not a strategy share class. | Mixed — the form does not say. Classification is house work. | No | Quarterly, ≤45 calendar days after quarter-end (weekends/holidays roll) | Shares + $ value of **13(f) securities only**. No SO, no AUM, no cash, no shorts, no non-13(f). | No | N/A (not an ETF) | Per-CIK as long as the filer exists on EDGAR | US government public records. SEC fair-access UA + contact email required. Not a substitute for the filing (SEC dataset disclaimer). | XML info table; JSON submissions index | `accepted_at` (Eastern) is the public clock; `period_end` is the book date. **Never score on period_end.** | Dead/closed advisers remain on EDGAR; the *roster* creates survivorship if you only keep today's names | **ADOPT** — curated desk + universal census already own this. CODE VERIFIED |
| SEC DERA Form 13F data sets | All filers in the quarter | Mixed | No | Quarterly extract of as-filed XML. Post-2024: prior three months after Feb/May/Aug/Nov | Same as 13F (flattened) | No | N/A | **July 2013 – May 2026** advertised this session (PRIMARY SOURCE VERIFIED https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets). 2013-Q2 zip is anomalously small (1.87 MB) — treat as incomplete. | Public dataset; disclaimer: filer-provided, extraction errors possible, not a substitute for filings. March 2024 refresh rewrote history into 2023 file format. | ZIP of TSV/structured tables | Published *after* the 13F due date; filings after 17:30 ET last business day of the extract window slip to the next zip | Includes whatever was filed; does not resurrect non-filers | **ADOPT as historical/reconcile source for tier 1–2.** Already the census's bulk path. Do **not** confuse with `submissions.zip` (FF-1 STOP). |
| SEC official list of 13(f) securities | Universe of reportable CUSIPs | N/A | N/A | Quarterly PDF | CUSIP list only | No | N/A | Quarterly PDFs on sec.gov | Public | PDF (ICE sells a structured feed — paid, not needed) | Same quarter as 13F | List membership changes | **CANDIDATE** for CUSIP eligibility, not for holdings |
| SEC N-PORT / N-PORT/A | Registered funds (ETFs, mutual funds) — the *fund*, not the adviser 13F | Active and passive registered funds | Some | Monthly to the SEC; **public quarterly, ~60 day lag** (CODE VERIFIED house comment in `collectors/holdings.py`) | Holdings with shares; embedded monthly create/redeem at fund level | No (flow, not tickets) | Create/redeem is *in* the filing, not excluded | Backfillable on EDGAR for any registered fund | Public EDGAR | XML | Quarter public + ~60d | Liquidated funds remain on EDGAR | **CANDIDATE** as the official quarterly validation of ETF holdings and the only official create/redeem series. House already forbids it as a live signal. |
| SEC N-CSR / N-CSRS | Same registered funds | Mixed | Some | Semi-annual | Full holdings (often more complete than 13F) | No | No | EDGAR history | Public | HTML/XML mixed | ~60d after period | Same | **CANDIDATE** for rare/specialist funds with no daily website file |
| Schedule 13D / 13D-A / 13G / 13G-A | Beneficial owner ≥5% | Active (13D) vs passive/ordinary-course (13G) | Activist, sometimes | Event-driven. 13D window is **5 business days** post-Feb-2024 (CODE VERIFIED `research/INTELLIGENCE_HUB_V2_RESEARCH.md`) | Shares + %; not a full book | No | N/A | EDGAR | Public | HTML/XML | `date_filed` | Issuers that drop below 5% leave the tape | **ADOPT** existing beneficial-ownership / special-sits path. 13G custodian ≠ conviction. |
| Form 4 / 4/A | Officers, directors, 10% holders | Insider, not a fund | No | Event, 2 business days | Shares traded | Yes (transaction codes) | N/A | EDGAR + Quiver overlay | Public | XML | Transaction date vs filing date | People leave the insider roster | **ADOPT** as a *separate axis* on the ownership wire. Never fuse with 13F. |
| Form ADV | RIA census (CRD) | Discloses strategy in free text | Sometimes | Annual + amendments | AUM ranges, no holdings | No | N/A | IAPD | Public | IAPD HTML / SEC investment adviser datasets | Filing date | Closed advisers remain | **CANDIDATE** for manager-complex identity (legal name, related persons), not for Q_i |

**Stopped, do not route around:** SEC `submissions.zip` bulk archive (~1.45 GiB, 2026-08-18 canary). FF-1P2 STOP #5898. That object is **issuer submissions**, not 13F information tables. B does not need it for 13F.

---

## 2. Official / sponsor ETF and active-ETF holdings (daily or better)

| Source | Adviser / funds | Style | Specialist | Cadence | Shares / wt / SO / AUM | Trade feed | Create/redeem excluded? | History | Rights | Format | Clock | Survivorship | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ARK `assets.ark-funds.com/.../ARK_*_HOLDINGS.csv` | ARK Investment Management — ARKK, ARKW already configured; ARKG/ARKQ/ARKF/ARKX exist at same CDN pattern (INFERRED from URL shape, not all fetched this session) | Concentrated discretionary active / thematic | Disruptive innovation | **Daily** holdings. Separate **trade-notification emails** (https://www.ark-funds.com/ark-trade-notifications) — PRIMARY SOURCE VERIFIED page exists | Shares, market value, weights, CUSIP, company | **Yes** (email); website file is EOD holdings, not tickets | Holdings file is positions, not create/redeem. Flow-normalize with SO. | Current-day file. History = what we snapshot. Wayback irregular. | ARK Terms page (`ark-invest.com/terms`) was Cloudflare-blocked this session. **UNKNOWN redistribution.** Treat as sponsor website ToS until Legal/Data OS reads it. Informational-use language on the trade-email page. | CSV | T+0 EOD | Closed/converted funds disappear from the current URL | **ADOPT** ARKK/ARKW. Candidate to add remaining ARK active ETFs into `holdings.watchlist`, not into `etf_holdings` (collector comment forbids duplicating ARK there). |
| State Street / SPDR daily XLSX | SSGA — ~20 configured | Mostly passive sector / thematic | Mixed | Daily current-only | Shares Held (VERIFIED in collector docstring) | No | No | No dated URL; no Wayback relied on | Sponsor site; scraping ToS UNKNOWN | XLSX | T+0 / T+1 | Current product list only | **ADOPT** forward. Cannot backfill. |
| Invesco cache API | Invesco — QQQ + others; `idType=cusip` | Passive + some active | Mixed | API `interval=monthly`, latest only | Holdings array | No | No | Latest | Sponsor API; ToS UNKNOWN | JSON | Monthly-ish | Current | **ADOPT** forward. |
| Global X dated CSV | Global X / Mirae — 21 configured | Thematic, mostly rules/index | Themes | Daily dated URL | Shares, weights | No | No | CDN floor ~2026-04-09 (CODE VERIFIED recon) | Sponsor CDN; ToS UNKNOWN | CSV | Dated in URL | Dead products 404 | **ADOPT** + backfill. Gold-standard dated URL. |
| Roundhill Filepoint master CSV | Roundhill — ~10 configured of ~51 in the master | Active / options-income / thematic | Options overlays common | Daily dated master | Shares; filter `Account` | No | No | Backfillable to 2024 | Sponsor; soft-404 (HTTP 200 + SPA) | CSV | URL date ≠ internal `Date` | Closed accounts drop out of master | **ADOPT**. Skip swap/option-income tickers already excluded. |
| Amplify Firestore | Amplify — 3 configured | Thematic / active | Mixed | Daily dated docs | Shares | No | No | ~10.5 months / 180 docs | Uses sponsor's **public** Firebase web key (`AMPLIFY_FIREBASE_KEY`). Not a secret in the intelligence sense; still a vendor key. | JSON | Per-doc date | Dropped funds vanish | **ADOPT**. |
| VanEck / Sprott / First Trust / ETC / Defiance / Bitwise / Procure | Various; configured | Mix of index thematic + a few active (Sprott GBUG/METL flagged `active: true`) | Sector / commodity / crypto-infra | Current-only pages | Usually shares | No | No | None | Sponsor HTML; ToS UNKNOWN | XLSX / HTML / JSON / data-URI | T+0 | Current list | **ADOPT** forward only. |
| iShares / BlackRock product AJAX | iShares | Mostly index | Broad + thematic | Daily theoretically | Shares | No | No | Current | **Consent / Akamai wall** — house marks BLOCKED | CSV behind wall | — | — | **NOT VIABLE** without headless + ToS review. |
| Schwab | Schwab ETFs | Index | Broad | Daily theoretically | Shares | No | No | Current | Same wall | — | — | — | **NOT VIABLE** free. |
| Vanguard | Vanguard ETFs | Broad index | Broad | — | — | No | — | — | **No reliable free daily holdings feed** (CODE VERIFIED collector) | — | — | — | **NOT SUPPORTED**. Use N-PORT quarterly. |
| ProShares `accounts.profunds.com/etfdata/psdlyhld.csv` | ProShares / Direxion-class leveraged & alt | Leveraged / inverse / overlay | Yes | One keyless CSV, all ~168 funds | Shares/contracts | No | No | Forward trivial; backfill Wayback only. Bonus `historical_nav.csv` = multi-year SO + AUM | Sponsor; ToS UNKNOWN | CSV | Daily current | Current list | **CANDIDATE** (recon already wrote this). High value for SO/AUM history and for class 8 (levered/inverse). |
| N-PORT (repeat) | Any registered ETF | All | All | Quarterly public | Shares + create/redeem | No | Create/redeem included | Deep EDGAR | Public | XML | ~60d | Includes liquidations | **CANDIDATE** universal fallback. |

---

## 3. Official-adjacent identity and flow

| Source | What it is | Status |
|---|---|---|
| SEC Form 13F FAQ | Filing mechanics, 13(f) list, confidentiality | **PRIMARY SOURCE** for how the form lies. https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f |
| EDGAR APIs / accessing-edgar-data | Fair-access UA, rate | Already coded |
| ETF shares outstanding / AUM | Needed for ΔQ_active. Not in 13F. Sources: sponsor sites, N-PORT, ProShares historical_nav, some ETF hubs | **PARTIAL.** House currently **proxies SO from the sum (or median) of overlapping position shares**, not from true fund SO. See intent matrix. |
| IBKR shortable FTP | Borrow fee + available shares, ~15 min | **ADOPT** existing collector. Snapshot-only. Rights: IBKR public FTP; redistribution UNKNOWN. |
| FINRA short interest / short volume | Already collected | Separate axis; do not fuse |
| Quiver Quant Trader API | Congress, insider, contracts, sometimes 13F-change products | **Vendor.** Paid. ToS forbids treating it as primary 13F. House already has official 13F. Do not add Quiver 13F as a second book. |

---

## 4. Third-party aggregators — do not make them canonical

| Source | Why it exists | Why B must not own it as truth |
|---|---|---|
| WhaleWisdom, Dataroma, 13F.info, Fintel, WhaleWisdom clones | Convenient UI over EDGAR | Derivative of public 13F; ToS typically bar redistribution; they add entity resolution that we would then be unable to audit; they silently drop amendments / confidential omissions |
| Bloomberg / FactSet / Refinitiv ownership | Institutional gold standard | Paid, redistribution forbidden, not on the free-data constraint |
| WRDS 13F | Academic cleaned 13F | Subscription; good for research replication, not a production owner |

If a future research bench needs a cleaned historical 13F panel, **parse SEC DERA zips ourselves** (already the census design) rather than licensing an aggregator.

---

## 5. China / HK official-ish sources (prior art only)

Listed so B does not reinvent clocks that CN already solved, and so #5822 can be reconciled.

| Source | Clock | Reuse for US B? |
|---|---|---|
| HKEX southbound holdings | Daily official CCASS-like disclose | Pattern: daily official holder file. US has no analogue except 13F quarterly. |
| Exchange top-10 / holder counts | Periodic CN filings | Pattern: float-holder changes as an independent family |
| Dragon Tiger (LHB) | Next-day named seats | **Do not port.** US has no equivalent lawful public tape. |
| Public-fund quarterly reports (CN) | Faster than US 13F in some cases | Pattern only |

---

## 6. Rights risks that would block a capture PR

1. **Sponsor website ToS unread** for ARK (Cloudflare this session), SSGA, Invesco, Global X, Roundhill, VanEck, Sprott, First Trust, ProShares. Forward collection already happens. A *new* capture or public redistribution of raw sponsor files needs a Data OS rights pass.
2. **iShares/Schwab headless bypass** of a consent wall is a rights and ToS problem, not an engineering problem. Leave blocked.
3. **Quiver / Amplify Firebase key** — vendor keys; do not scrape around them.
4. **SEC public data is not a license to misrepresent it as real-time or complete.** Confidential treatment, late 13F-NT, and the $100M threshold are structural holes.
5. **CUSIP** is licensed (CUSIP Global Services). House already name-matches and hides unresolved lines. Do not buy a CUSIP master in this program unless Data OS separately decides.
6. **FF-1 STOP** is not a 13F rights issue; it is a bulk-archive size stop. Do not "solve" 13F history by downloading `submissions.zip`.

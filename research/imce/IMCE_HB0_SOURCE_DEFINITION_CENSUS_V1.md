# IMCE-HB-0 — Homebuilder Source/Definition Census Freeze (V1)
## Wave A3 of WS:CYCLE-PATTERN-ISSUER-MECHANISM — records-only, stop-before-fitting

**Status:** `records_only`. No model, estimate, correlation, regression, outcome statistic, return computation, or "quick look" at any outcome appears anywhere in this document. Definition and census only, per freeze §13 wave A3.
**Commissioned by:** Fable, per `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` §13 A3, after Sol's release of PR #6127 (merged 2026-08-21T03:55Z, `ec44ae7d1659`).
**Revision history:** V1 initial draft (2026-08-21, PR #6148, draft); this revision applies Fable's Opus red-team adjudication (4 blockers, 17 majors, 8 minors, 1 nit) in full — see inline `[B#]`/`[M#]`/`[m#]`/`[n1]` tags at each applied point. The verified-spine items (all six roster CIK/SIC/FYEs; the 6-cell/`imce_hist_v0`/q=0.10 budget; DHI/PHM/NVR original denominator formulas; the NRS archive; the clause-(q) fence; gap-1 honesty) are unchanged.
**Binding spec (verbatim, do not redesign):** freeze §13 A3 — *"fixed roster, denominator crosswalk, fiscal→calendar re-key, structural-break ledger, frozen block list, cell budget confirmation. Stop before any fitting."* Plus §7.2 conditions (1)–(5) and the §8 [G8-M6] vintage rider, both restated inline at point of use below.
**This document satisfies:** freeze §7.2 CONDITIONAL_GO conditions (1)–(5) for the homebuilder family, and the contract's (`research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`) §2 Homebuilders eligibility items (a)/(b)/survivorship/epoch-clock/vintage riders. It does not itself register anything — registration (`declared_budget` trial-ledger rows) is IMCE-03 (wave A4), separately authorized.
**Authority:** None. No rank, gate, size, screener, or trade authority is created, implied, or reserved. All authority remains false at birth per freeze D9.
**Date:** 2026-08-21 (census date; roster and status facts below are frozen as of this date and this document's cited retrievals).
**Retrieval window:** all web/SEC citations in this document were retrieved 2026-08-21 (session date), via WebSearch, direct `curl` against `data.sec.gov` and `www.sec.gov/Archives/edgar/` with a declared User-Agent (`Macro Dashboard IMCE-HB0 Research <daniela33777555@gmail.com>`, well under the 10 req/s SEC EDGAR rate limit), and WebFetch. Every factual claim below carries an inline citation with URL and the 2026-08-21 retrieval date; no fact is asserted without one.
**Ownership note [M17]:** this record does not touch `agentos/`. The wave-boundary `WS-CYCLE-PATTERN-ISSUER-MECHANISM` state update and any handoff record for this wave are owned by the commissioning (Fable) session's closure PR, not by this packet — consistent with OUT-OF-SCOPE in the original commission.

**Stop-before-fitting attestation:** this document contains issuer-reported, publicly disclosed metric *definitions* (e.g., "cancellation rate = cancellations ÷ gross orders") and, where necessary to establish a definition or a structural break, individual issuer-reported point values with their own citation. No value in this document was computed, aggregated, averaged, correlated, or regressed by this session. No forward-return, drawdown, Brier, or any outcome/target statistic appears anywhere below. No cross-issuer mean, pooled rate, or trend line is presented.

---

# 1. Fixed roster

Per freeze §7.2 and G4 census verdict ("Keep DHI/PHM/KBH/TOL; LEN adjusted; NVR outlier" — freeze §10), the frozen roster is **six named issuers**, each carrying a differentiated treatment role. CIK, exchange, SIC code, fiscal-year-end, and filer category below are pulled directly from each issuer's SEC EDGAR `submissions` JSON (`data.sec.gov/submissions/CIK##########.json`), retrieved 2026-08-21 with a declared User-Agent per D7/§8 (`SEC_EDGAR`, GO, 10 req/s).

| Issuer | Ticker | CIK | Exchange | SIC | State of inc. | Fiscal year end | Filer category | Roster role (frozen) |
|---|---|---|---|---|---|---|---|---|
| D.R. Horton, Inc. | DHI | 0000882184 | NYSE | 1531 Operative Builders | DE | Sep 30 | Large accelerated filer | Core stratum member |
| PulteGroup, Inc. | PHM | 0000822416 | NYSE | 1531 Operative Builders | MI | Dec 31 | Large accelerated filer | Core stratum member |
| Toll Brothers, Inc. | TOL | 0000794170 | NYSE | 1531 Operative Builders | DE | Oct 31 | Large accelerated filer | Core stratum member |
| KB Home | KBH | 0000795266 | NYSE | 1531 Operative Builders | DE | Nov 30 | Large accelerated filer | Core stratum member |
| Lennar Corporation | LEN (+ LEN-B) | 0000920760 | NYSE | 1520 General Bldg Contractors–Residential Bldgs | DE | Nov 30 | Large accelerated filer | **Adjusted** — excluded from cancellation-rate cells only (§3); Millrose structural-break flag (§5) |
| NVR, Inc. | NVR | 0000906163 | NYSE | 1531 Operative Builders | VA | Dec 31 | Large accelerated filer | **Mechanism outlier — SEPARATE STRATUM, frozen now [M11].** Never pooled to raise n. No transfer test exists in this record; a transfer test is a future registered cell requiring its own amendment through A4 (§7.2 condition 2). |

**Sources (retrieved 2026-08-21):**
- DHI: `https://data.sec.gov/submissions/CIK0000882184.json` — name "HORTON D R INC /DE/", tickers ["DHI"], exchanges ["NYSE"], sic 1531, fiscalYearEnd "0930", stateOfIncorporation "DE", category "Large accelerated filer".
- PHM: `https://data.sec.gov/submissions/CIK0000822416.json` — "PULTEGROUP INC/MI/", ["PHM"], ["NYSE"], 1531, "1231", "MI".
- TOL: `https://data.sec.gov/submissions/CIK0000794170.json` — "Toll Brothers, Inc.", ["TOL"], ["NYSE"], 1531, "1031", "DE".
- KBH: `https://data.sec.gov/submissions/CIK0000795266.json` — "KB HOME", ["KBH"], ["NYSE"], 1531, "1130", "DE".
- LEN: `https://data.sec.gov/submissions/CIK0000920760.json` — "LENNAR CORP /NEW/", ["LEN","LEN-B"], ["NYSE","NYSE"], 1520, "1130", "DE".
- NVR: `https://data.sec.gov/submissions/CIK0000906163.json` — "NVR INC", ["NVR"], ["NYSE"], 1531, "1231", "VA".

**NVR outlier basis [freeze §7.2 condition 2; corrected per M10]:** NVR's own FY2025 Form 10-K states: *"We generally do not engage in land development (see discussion below of our land development activities). Instead, we typically acquire finished building lots from various third-party land developers pursuant to fixed price lot purchase agreements ('LPAs') that require deposits that may be forfeited if we fail to perform under the LPAs. The deposits required under the LPAs are in the form of cash or letters of credit in varying amounts and typically range up to 10% of the aggregate purchase price of the finished lots."* [NVR, Inc. Form 10-K for FY2025, `nvr-20251231.htm`, accession 0000906163-26-000018, https://www.sec.gov/Archives/edgar/data/906163/000090616326000018/nvr-20251231.htm, retrieved 2026-08-21] The prior draft's "~100%-option" and Medium/umbrex citations are **struck** — NVR's own filing explicitly says "generally," not "always" or "100%," and cross-references its own (separately disclosed) land-development activities, so this is a strong-majority option-lot model, not a categorical one. This — not a computed statistic of any kind — is the mechanism basis for the frozen stratification rule restated below [M11].

**LEN adjustment basis [freeze §7.2 condition 1]:** restated verbatim from the freeze — LEN "is excluded from cancellation-rate cells (no press-release cancellation rate; era-correlated missingness by construction) and carries a Feb-2025 Millrose break flag." This session's own search of Lennar's 2025 quarterly press releases found average-sales-price and backlog-unit/dollar tables but no cancellation-rate line item — consistent with, and evidentially supportive of, the freeze's finding. See §5 for the exact Millrose spin-off date and §6b for which of the 6 registered cells the exclusion actually binds.

---

# 2. Survivorship census [freeze §7.2 condition 5 / contract survivorship condition; G8-B4]

**Standing rule restated (binding, not re-derived):** "the roster is a 2026-survivor roster over a window containing the 2006–2011 sector mortality event, and the ported Stock Identity episode substrate is itself survivor-stamped (W1 census 'survivor-only stamped')." IMCE-HB-0 must produce a named census of delisted/bankrupt/acquired homebuilders for the study window with an explicit inclusion decision; **until this lands, every homebuilder cell readout carries a mandatory survivorship-bias disclosure, and no cohort mean is quoted without it.**

**Study window:** 2006–2026, matching the frozen historical block list (§6) and bracketing the 2006–2011 event.

## 2a-0. Population rule [B2, RULING]

**Population = every U.S. SEC-registrant homebuilder (SIC 1531 Operative Builders or SIC 1520 General Building Contractors–Residential Buildings) that had LISTED COMMON EQUITY on a U.S. exchange at any point during 2006–2026.** A private or subsidiary homebuilder that never had its own listed common equity is **not a sample member** under this rule — it is retained instead as an explicitly-typed **context row** (§2a-iii): "no listed equity; never a sample member." This is a population-definition ruling, not a re-derivation of the standing rule; it operationalizes "named census... explicit inclusion decision" into a testable membership test.

Three exhaustive dispositions follow from this population rule for every name found:

- **(i) Structurally invisible** — had listed common equity; the disposition leaves no surviving public security of its own, AND it is not absorbed into one of the six current roster members' own consolidated entity (§2a-i).
- **(ii) Absorbed into a roster member's own series** [B1, NEW disposition category] — had listed common equity; the surviving consolidated entity today sits inside one of the six roster CIKs, so its pre-merger history is technically present (buried, unflagged) inside a roster member's own reported series rather than simply absent (§2a-ii).
- **(iii) Context row** — never had listed common equity of its own; retained by name for the mortality-event record but never a sample member under the population rule (§2a-iii).

## 2a-i. Structurally invisible (had listed equity; no absorption into the current roster)

| # | Name | Event type | Date(s) | Disposition | Reason |
|---|---|---|---|---|---|
| 1 | Technical Olympic USA, Inc. (TOUSA) — brands incl. Engle Homes, Newmark Homes | Chapter 11 bankruptcy, then liquidation to creditors | Filed 2008-01-29; "second public builder to file for bankruptcy protection and the largest one to date"; stock delisted after losing ~98% of market value | **EXCLUDE from panel; INCLUDE in mortality census.** | No continuous post-emergence public security; no successor. Among sample members (listed-equity names), this is the **earliest-dated structurally-invisible event** in the window. |
| 2 | Orleans Homebuilders, Inc. | Chapter 11 → equity cancelled → reorganized privately | Filed 2010-03-01 (D. Del.); plan confirmed Dec 2010; reorganization completed 2011-02-14; equity cancelled, "no recovery for current equity holders," control to three former debtholders (Strategic Value Partners, Anchorage Illiquid Opportunities Offshore Master, Bank of America distressed-debt desk) | **EXCLUDE; INCLUDE in mortality census.** | Textbook equity-wipeout — the panel-relevant security is permanently dead even though the operating business continued privately. |
| 3 | California Coastal Communities, Inc. (NASDAQ: CALC) | Chapter 11 → equity extinguished → reorganized privately | Filed **2009-10-27**; plan converted $56M of senior term loan to equity, "provided no recovery for current equity holders"; emerged **2011-03-01** | **EXCLUDE; INCLUDE in mortality census.** | Same equity-wipeout structure as Orleans, roughly contemporaneous — a second, independently-sourced instance of the 2009–2011 recovery-era equity-wipeout pattern. |
| 4 | Dominion Homes, Inc. (OTC: DHOM) | Going-private buyout | Deal at $0.65/share; completed **2008-06-11** after shareholder approval 2008-05-30; new owners Angelo Gordon & Co., Silver Point Capital, and BRC Properties Inc. (chairman/CEO's holding company) | **EXCLUDE; INCLUDE in mortality census.** | Equity extinguished at the 2008-06-11 buyout — this is the panel-relevant event. (Distinct from a later, unrelated 2014 transaction in which PulteGroup acquired Dominion's — by then privately-held — homebuilding operations/signage as an asset deal; that later event does not revive or re-list any security and does not create a §2a-ii "absorbed into a roster member's own series" disposition, because there was no listed security left to absorb — flagged as a nuance, not a re-disposition.) |
| 5 | Brookfield Homes Corp. → Brookfield Residential Properties Inc. (NYSE/TSX: BHS→BRP) | Going-private squeeze-out by majority owner | Brookfield Asset Management closed the going-private transaction **2015-03-13**; BRP delisted from TSX and suspended from NYSE trading **2015-03-16** | **EXCLUDE; INCLUDE in mortality census.** | A majority-owner squeeze-out, not distress — recorded because the name still disappears from a name-keyed roster, which is the exact mechanism the standing rule warns about even absent financial distress. |
| 6 | Standard Pacific Corp. (NYSE: SPF) and The Ryland Group, Inc. (NYSE: RYL) | Merger of equals → CalAtlantic Group, Inc. | Announced 2015-06-14; closed **2015-10-01** | **EXCLUDE both legacy tickers; the successor CalAtlantic is itself later absorbed — see §2a-ii row 3.** | Not distress — a voluntary combination of two survivors of the 2006–2011 event; both names vanish from any name-keyed roster. |
| 7 | UCP, Inc. (NYSE: UCP) | Acquired by Century Communities, Inc. (not a roster member) | Announced 2017-04-11; shareholder-approved 2017-08-01; **completed 2017-08-04** (~$356M aggregate transaction value incl. ~$149M assumed debt) | **EXCLUDE; INCLUDE in mortality census.** | Absorbed into a NON-roster acquirer (Century Communities). See its own 2013 IPO in the entry-side census, §2e — UCP is a full round-trip case (public 2013 → absorbed 2017). |
| 8 | William Lyon Homes (NYSE: WLH) | Acquired by Taylor Morrison Home Corporation (not a roster member) | Deal closed **2020-02-06**; ~$2.5B total consideration ($2.50 cash + 0.800 TMHC shares per WLH share) | **EXCLUDE; INCLUDE in mortality census.** | Absorbed into a NON-roster acquirer. WLH itself is a **triple-event** name inside the study window: Ch11 filed 2011-12-19 → emerged 2012-02-25 (equity wiped) → re-IPO'd 2013-05-21 (entry-side census, §2e) → acquired by Taylor Morrison 2020-02-06 (this row). The full arc is preserved here rather than collapsed to one line. |
| 9 | AV Homes, Inc. (NASDAQ: AVHI; formerly Avatar Holdings, CIK 0000039677) | Acquired by Taylor Morrison Home Corporation (not a roster member) | Agreement 2018-06-07 at $21.50/share (~$963M incl. debt); **completed 2018-10-02** | **EXCLUDE; INCLUDE in mortality census — sharpest full-mortality-window-survivor case.** | AVHI (as Avatar Holdings/AV Homes) was continuously listed through the ENTIRE 2006–2011 event and for a further seven years, only to disappear by acquisition in 2018 — the clearest illustration in this census that a name surviving the sector's defining mortality event is still invisible to a fixed 2026-survivor roster. |
| 10 | The New Home Company Inc. (NYSE: NWHM) | Taken private by funds managed by Apollo Global Management | Agreement 2021-07-22/26 at $9.00/share (~$338M enterprise value); tender offer **completed 2021-09-08** | **EXCLUDE; INCLUDE in mortality census.** | A second full round-trip case: IPO'd 2014-01-30 (entry-side census, §2e), taken private 2021-09-08 (this row) — entered and exited entirely within the study window, invisible to both endpoints of a 2026-only roster. |
| 11 | M.D.C. Holdings, Inc. (NYSE: MDC, "Richmond American Homes") | Acquired by Sekisui House, Ltd. (foreign, not a roster member) | **Completed 2024-04-19**; $63.00/share cash, ~$4.9B equity value | **EXCLUDE; INCLUDE in mortality census.** | Public throughout the full 2006–2026 window (~18 continuous years) before disappearing to M&A — parallel case to AV Homes but even longer-lived. |
| 12 | WCI Communities, Inc. (bankruptcy phase only — see §2a-ii row 2 for its post-2017 disposition) | Chapter 11 bankruptcy → private → re-IPO | Filed 2008-08-04; emerged 2009-09-03; re-IPO'd 2013-06 (NYSE: WCIC, ~$91M raised) | **EXCLUDE the pre-2017 WCI security from panel construction; the pre-2013 gap (2008–2013) is the structurally-invisible episode this row records.** | Any panel built 2009–2013 would show WCI as simply absent; this is the "dead, revived" half of its arc. Its post-2013 public phase ends in absorption — tracked at §2a-ii row 2, not duplicated here. |

## 2a-ii. Absorbed into a roster member's own series [B1, new category]

These names had their own listed common equity, and today their post-merger history is folded — unflagged, by default — inside a current roster member's own reported financial series. This is a *different* survivorship failure mode from §2a-i: the acquired name is not simply absent from the panel, it is silently **present but disguised** as part of the acquirer's own continuous time series, unless the structural-break flag below is honored.

| # | Name | Absorbed into | Date | Consequence |
|---|---|---|---|---|
| 1 | Centex Corporation (NYSE: CTX, CIK 0000018532) | **PulteGroup (PHM)** | Merger agreement 2009-04-07; **completed 2009-08-18**; 0.975 PHM shares per CTX share, stock-for-stock, ~$3.1B incl. ~$1.8B net debt | See §5 structural-break ledger — PHM's own pre-/post-2009-08-18 reported series is not scale-comparable without an explicit epoch flag. |
| 2 | WCI Communities, Inc. (post-2013 public phase; NYSE: WCIC) | **Lennar (LEN)** | **Completed 2017-02-10**; ~$643M, $23.50/share | See §5 — LEN's Florida/luxury segment composition changes at this date. |
| 3 | CalAtlantic Group, Inc. (successor to Standard Pacific + Ryland, CIK 0000878560) | **Lennar (LEN)** | Merger agreement 2017-10-30; **completed 2018-02-12** | See §5 — the largest single scale-step-change in LEN's history inside the study window. |

## 2a-iii. Context rows — no listed common equity, never sample members [B2, RULING]

| # | Name | Event | Date | Public-equity status |
|---|---|---|---|---|
| 1 | Kara Homes, Inc. | Chapter 11 bankruptcy | Filed **2006-10-05**, District of New Jersey; 7th-largest NJ builder, ~$300M owed to 1,000+ creditors | Private (founder-owned); never listed. **This is the earliest-dated event in the FULL census (context or sample) — corrects the prior draft's mis-claim that Levitt and Sons was earliest [m5].** Among SAMPLE MEMBERS only, the earliest structurally-invisible event remains TOUSA (2008-01-29, §2a-i row 1). |
| 2 | Levitt and Sons, LLC | Chapter 11 bankruptcy (subsidiary of Levitt Corporation, NYSE: LEV) | Filed 2007-11-09, Fort Lauderdale; "the housing downturn's first public builder casualty" | Subsidiary of a publicly traded parent; never itself listed. Levitt Corp itself continued in a different business line and is out of scope. |
| 3 | Neumann Homes, Inc. | Chapter 11 bankruptcy | Filed **2007-11-01**, N.D. Illinois; 4th-largest Chicago-area builder | Private; never listed. |
| 4 | Kimball Hill, Inc. (Kimball Hill Homes) | Chapter 11 bankruptcy → liquidation (no reorganization) | Filed 2008-04-23; shutdown/liquidation announced 2008-12-03 | Private/family-held (Hill family); filed some SEC reports only because of outstanding public debt, never public equity. |

## 2a-iv. Boundary case (neither disposition, noted only)

| # | Name | Note |
|---|---|---|
| 1 | Comstock Homebuilding Companies, Inc. → Comstock Holding Companies, Inc. (2012) → Comstock Holdings, Inc. (Nasdaq: CHCI) | Near-collapse (FY2008 net loss $17M on revenue down 82.5% YoY) but survived, then exited homebuilding for real-estate asset management. Neither died nor stayed a homebuilder — excluded from both §2a-i/ii/iii and the panel; recorded as a typed non-fit rather than silently dropped. |

## 2b. Sources (retrieved 2026-08-21)

- TOUSA: https://hbsdealer.com/news/tousa-files-bankruptcy; https://www.multihousingnews.com/homebuilder-tousa-files-for-bankruptcy/; SEC EDGAR TOUSA 10-K (CIK 1046578), https://www.sec.gov/Archives/edgar/data/1046578/000095014408006390/g14602e10vk.htm.
- Orleans Homebuilders: https://www.inquirer.com/philly/business/20100302_Orleans_builders_files_for_bankruptcy_protection.html; https://news.bloomberglaw.com/bankruptcy-law/court-confirms-orleans-homebuilders-incs-chapter-11-plan-will-emerge-by-year-end; https://news.bloomberglaw.com/bankruptcy-law/orleans-homebuilders-inc-completes-reorganization-emerges-from-chapter-11; SEC EDGAR 8-K exhibit, https://www.sec.gov/Archives/edgar/data/38570/000114420410030271/v186563_ex99-1.htm.
- California Coastal Communities: https://www.prnewswire.com/news-releases/california-coastal-communities-exits-bankruptcy-117229913.html; https://www.prnewswire.com/news-releases/california-coastal-communities-files-consensual-plan-of-reorganization-to-exit-from-bankruptcy-112241514.html.
- Dominion Homes: https://www.builderonline.com/land/dominion-homes-goes-private-gets-new-lease-on-life_o; https://www.globenewswire.com/news-release/2008/06/11/379759/9044/en/Dominion-Homes-Completes-Merger-Transaction.html; PulteGroup-Dominion 2014 asset context, https://eu.columbusceo.com/story/business/2014/08/26/after-sale-homebuilder-pulte-signs/22930261007/.
- Brookfield Homes/Residential: https://www.torys.com/work/2014/12/brookfield-asset-management-closes-going-private-transaction-of-brookfield-residential; https://www.brookfieldresidential.com/press-releases-events-and-webcasts-landing/brookfield-asset-management-closes-going-private-transaction-of-brookfield-residential; SEC EDGAR Brookfield Homes 425, https://www.sec.gov/Archives/edgar/data/0001202157/000095012310091396/o65548e425.htm.
- Standard Pacific / Ryland / CalAtlantic: https://www.prnewswire.com/news-releases/standard-pacific-corp-and-the-ryland-group-inc-merge-to-create-calatlantic-group-inc-americas-fourth-largest-homebuilding-company-300152033.html; SEC EDGAR Ryland 425, CIK 85974, https://www.sec.gov/Archives/edgar/data/85974/000119312515274344/d76125d425.htm; SEC EDGAR Standard Pacific 10-K (CIK 878560), https://www.sec.gov/Archives/edgar/data/878560/000119312505037614/d10k.htm.
- CalAtlantic → Lennar: https://www.prnewswire.com/news-releases/lennar-completes-strategic-combination-with-calatlantic-300597384.html; https://www.housingwire.com/articles/42514-lennar-completes-calatlantic-merger/; SEC EDGAR CalAtlantic DEFA14A, https://www.sec.gov/Archives/edgar/data/0000878560/000119312517325283/d481039ddefa14a.htm.
- UCP → Century Communities: https://www.businesswire.com/news/home/20170804005433/en/Century-Communities-Completes-Business-Combination-UCP; https://www.constructiondive.com/news/century-communities-ucp-to-merge-in-336m-deal/440433/; SEC EDGAR UCP 10-K/A (CIK 1572684), https://www.sec.gov/Archives/edgar/data/0001572684/000090514817000506/efc17-300_10ka.htm.
- William Lyon Homes → Taylor Morrison: https://newsroom.taylormorrison.com/2020-02-06-Taylor-Morrison-Announces-Close-of-William-Lyon-Homes-Acquisition-with-Unwavering-Commitment-to-Smart-Growth; SEC EDGAR Taylor Morrison 8-K, https://www.sec.gov/Archives/edgar/data/1562476/000119312520026379/d851617dex991.htm; WLH bankruptcy/emergence, https://www.sec.gov/Archives/edgar/data/0001095996/000144530514001123/wlh-12312013x10k.htm.
- AV Homes / Avatar Holdings: https://newsroom.taylormorrison.com/2018-06-07-Taylor-Morrison-Announces-Agreement-to-Acquire-AV-Homes-at-21-50-Per-Share; https://newsroom.taylormorrison.com/2018-10-02-Taylor-Morrison-Announces-Close-of-AV-Homes-Acquisition-with-Clear-Vision-for-Growth-in-Top-Housing-Markets; SEC EDGAR AV Homes 8-K (CIK 39677), https://www.sec.gov/Archives/edgar/data/0000039677/000119312518186150/d603093dex991.htm.
- The New Home Company → Apollo: https://www.globenewswire.com/news-release/2021/09/08/2293476/0/en/The-New-Home-Company-and-Apollo-Announce-Completion-of-the-Acquisition-of-The-New-Home-Company-by-Funds-Managed-by-Affiliates-of-Apollo.html; SEC EDGAR NWHM 8-K, https://www.sec.gov/Archives/edgar/data/1574596/000119312521267372/d211443dex991.htm.
- MDC Holdings → Sekisui House: https://www.prnewswire.com/news-releases/sekisui-house-completes-acquisition-of-mdc-holdings-expanding-us-business-by-strengthening-the-delivery-of-high-quality-detached-homes-across-16-states-302122083.html.
- WCI Communities (both phases): https://www.npr.org/2008/08/05/93293367/luxury-home-builder-wci-files-for-bankruptcy; https://www.businessobserverfl.com/news/2014/jun/20/wci-bankrupt-builder-100/; https://www.prnewswire.com/news-releases/lennar-completes-acquisition-of-wci-communities-300405585.html.
- Centex → PulteGroup: SEC EDGAR PulteGroup 8-K/425 filings, https://www.sec.gov/Archives/edgar/data/18532/000095012309016312/c52036ae425.htm and https://www.sec.gov/Archives/edgar/data/0000822416/000119312509222939/dex991.htm.
- Kara Homes: https://www.builderonline.com/land/from-making-bank-to-bankruptcy_o; https://www.govinfo.gov/content/pkg/USCOURTS-njb-3_06-bk-19626/pdf/USCOURTS-njb-3_06-bk-19626-1.pdf.
- Levitt and Sons: https://www.builderonline.com/land/levitt-and-sons-declares-bankruptcy_o; https://www.npr.org/2008/02/27/44117288/levitt-bankruptcy-leaves-homeowners-in-the-cold.
- Neumann Homes: https://www.law360.com/articles/39101/chicago-s-neumann-homes-files-for-bankruptcy; https://www.chicagobusiness.com/article/20071101/CRED03/200026989/neumann-homes-files-for-chapter-11.
- Kimball Hill: https://www.builderonline.com/money/kimball-hill-files-chapter-11_o; https://www.law360.com/articles/78795/citing-downturn-kimball-hill-opts-for-liquidation; SEC EDGAR Kimball Hill S-4/A (CIK 1357090), https://www.sec.gov/Archives/edgar/data/1357090/000110465906030705/a06-6471_1s4a.htm.
- Comstock: https://www.builderonline.com/land/comstock-close-to-bankruptcy_o; SEC EDGAR Comstock 10-Q FY2008 (CIK 1299969), https://www.sec.gov/Archives/edgar/data/0001299969/000119312508178461/d10q.htm.

## 2c. Standing consequence (restated, corrected [m4])

Until/unless the names above are actually incorporated into a panel construction (which this census does not do — it is a naming and dispositioning exercise only), **every homebuilder cell readout carries a mandatory survivorship-bias disclosure, and no cohort mean is quoted without it.** Corrected framing: this census counts **12 structurally-invisible sample-member events** (§2a-i), **3 absorbed-into-roster events** (§2a-ii, silently present but disguised inside PHM's or LEN's own series unless flagged), **4 context rows** with no listed equity ever (§2a-iii), and **1 boundary non-fit** (§2a-iv) — none of which appear as distinct names in a fixed 2026-survivor roster of DHI/PHM/TOL/KBH/LEN/NVR. The prior draft's claim that these events "postdate the roster's six surviving names" was incoherent (events do not postdate names) and is struck.

**Disclosure is widened to two distinct bias types [B4]:** (i) **mortality bias** — the dead/absorbed names above, which a 2026-survivor roster cannot see at all; and (ii) **roster-selection bias** — even among issuers that survived to 2026 with listed equity intact, the six-name roster is itself a further *subset* chosen pre-outcome (§2d), not the full surviving population. Both must be disclosed together; a disclosure naming only mortality bias while implying the six-name roster is "the survivors" is incomplete.

The census additionally notes, per freeze §7.2(5), that "the ported Stock Identity episode substrate is itself survivor-stamped (W1 census 'survivor-only stamped')" — the identity substrate this program composes against inherits the same bias one layer down; this document does not audit that substrate independently (separate owner, freeze §3), and the compounding is named as a gap (§8, gap 6).

## 2d. Listed survivors excluded from the roster [B4, RULING]

The six-name roster (§1) is a **subset** of the full population of SIC 1531/1520 issuers with continuously listed common equity spanning the 2006–2011 event and still trading in 2026 — not the complete surviving population. The following are listed, continuously public (or near-continuously) survivors that are **not** in the frozen roster, three of them (HOV, BZH) having lived through the near-death experience of 2008–2011 without a bankruptcy filing:

| Issuer | Ticker | CIK | Exchange | FYE | Note |
|---|---|---|---|---|---|
| Hovnanian Enterprises, Inc. | HOV | 0000357294 | NYSE (+OTC/Nasdaq preferred classes) | Oct 31 | Continuous public history across the entire 2006–2026 window; came close to covenant breach/restructuring in the GFC bust without filing Chapter 11. |
| Beazer Homes USA, Inc. | BZH | 0000915840 | NYSE | Sep 30 | Continuous public history across the entire window, including a 2007-era accounting/mortgage-practices scandal, without a bankruptcy filing — the other "near-death survivor" whose omission most distorts a cohort mean drawn only from the six roster names. |
| M/I Homes, Inc. | MHO | 0000799292 | NYSE | Dec 31 | Continuous public history across the window; mid-cap peer, not in roster. |
| Meritage Homes Corp. | MTH | 0000833079 | NYSE | Dec 31 | Continuous public history across the window; mid-cap peer, not in roster. |
| Taylor Morrison Home Corp. | TMHC | 0001562476 | NYSE | Dec 31 | Public since 2013-04-10 (entry-side census, §2e); the frequent NON-roster acquirer in §2a-i/ii (WLH, AV Homes). |
| Tri Pointe Homes, Inc. | TPH | 0001561680 | NYSE | Dec 31 | Public since 2013-01-31 (entry-side census, §2e); not in roster. |

**RULING:** the roster stays frozen at six (the freeze-era pilot roster, §1) — this document does not expand it. §2d exists so that the mandatory disclosure (§2c) is understood to cover **roster-selection bias in addition to mortality bias**: a reader must not infer from "the roster survived" that "the roster is representative of survivors," since HOV and BZH in particular are the closest same-era comparables to the six roster names that were left out.

**Sources (retrieved 2026-08-21):** `https://data.sec.gov/submissions/CIK0000357294.json` (HOV — name "HOVNANIAN ENTERPRISES INC", tickers ["HOV","HOVVB","HOVNP"], exchanges ["NYSE","OTC","Nasdaq"], sic 1531, fiscalYearEnd "1031"); `https://data.sec.gov/submissions/CIK0000915840.json` (BZH — "BEAZER HOMES USA INC", ["BZH"], ["NYSE"], 1531, "0930"); `https://data.sec.gov/submissions/CIK0000799292.json` (MHO — "M/I HOMES, INC.", ["MHO"], ["NYSE"], 1531, "1231"); `https://data.sec.gov/submissions/CIK0000833079.json` (MTH — "Meritage Homes CORP", ["MTH"], ["NYSE"], 1531, "1231"); `https://data.sec.gov/submissions/CIK0001562476.json` (TMHC — "Taylor Morrison Home Corp", ["TMHC"], ["NYSE"], 1531, "1231"); `https://www.sec.gov/edgar/browse/?CIK=0001561680` (TPH — CIK confirmed via SEC EDGAR browse page; the `submissions` JSON for this CIK returned an empty tickers/exchanges array in this session's fetch, so ticker/exchange are corroborated instead via stocktitan.net/overview/TPH/ and the company's own 10-year-IPO-anniversary release, both retrieved 2026-08-21 — flagged as a minor data-completeness note, not a disposition uncertainty, since the CIK and SIC/FYE fields did resolve).

## 2e. Entry-side (left-truncation) census — survivorship's mirror [m7]

A roster or panel anchored at any date BEFORE these issuers went public would show them as simply absent — the same invisibility mechanism as §2a, running in the opposite temporal direction (left-truncation rather than right-censoring/attrition). Recorded for completeness, not for inclusion in the frozen six-name roster.

| Issuer | Ticker | Entry event | Date | Detail |
|---|---|---|---|---|
| Tri Pointe Homes, Inc. | TPH | IPO (NYSE) | **2013-01-31** | Priced at $17.00/share, $232.7M raised; "the first homebuilder to go public since 2004." [globenewswire.com/en/news-release/2023/02/28/2616805, retrieved 2026-08-21] |
| Taylor Morrison Home Corp. | TMHC | IPO (NYSE) | **2013-04-10** (priced 2013-04-09 at $22.00, high end of range) | $629M raised, 28.6M shares. [nasdaq.com/articles/taylor-morrison-prices-upsized-ipo-22-high-end-range-2013-04-09, retrieved 2026-08-21] |
| William Lyon Homes | WLH | Re-IPO (NYSE) after 2011–2012 Chapter 11 | **2013-05-21** | $25.00/share, 10,005,000 Class A shares — 15 months after emerging from bankruptcy (§2a-i row 8). [ocbj.com/news/2013/may/16/shares-william-lyon-homes-rise-after-ipo, retrieved 2026-08-21] |
| UCP, Inc. | UCP | IPO (NYSE) | Priced **2013-07-17**; began trading 2013-07-18; **completed 2013-07-23** | $15.00/share, 7,750,000 shares; spun out of PICO Holdings (§2a-i row 7 records its 2017 exit). [businesswire.com/news/home/20130717006407, retrieved 2026-08-21] |
| LGI Homes, Inc. | LGIH | IPO (NASDAQ) | Priced **2013-11-07**; offering closed **2013-11-13** | $11.00/share; not in roster. [investor.lgihomes.com/news-releases/news-release-details/lgi-homes-inc-announces-pricing-initial-public-offering, retrieved 2026-08-21] |
| Century Communities, Inc. | CCS | IPO (NYSE) | **2014-06-18** | $23.00/share, 4.48M shares, ~$109.8M raised; became the acquirer of UCP in 2017 (§2a-i row 7). [seekingalpha.com/article/2269923, retrieved 2026-08-21] |
| The New Home Company Inc. | NWHM | IPO (NYSE) | **2014-01-30** | $11.00/share, 8,984,375 shares; the same name exits via Apollo take-private 2021-09-08 (§2a-i row 10) — a full round-trip inside the study window. [SEC EDGAR 424B4, https://www.sec.gov/Archives/edgar/data/0001574596/000119312514033183/d570159d424b4.htm, retrieved 2026-08-21] |
| Dream Finders Homes, Inc. | DFH | IPO (NASDAQ) | Priced ~2021-01-21; **completed 2021-01-25** | $13.00/share, ~$125M raised. [nasdaq.com/articles/florida-based-homebuilder-dream-finders-homes-prices-ipo-within-the-range-at-13-2021-01, retrieved 2026-08-21] |
| Landsea Homes Corporation | LSEA | SPAC business combination (NASDAQ) | Closed **2021-01-07**; trading began 2021-01-08 | LF Capital Acquisition Corp. renamed Landsea Homes Corporation. [globenewswire.com/news-release/2021/01/07/2155240, retrieved 2026-08-21] |
| United Homes Group, Inc. | UHG | Business combination (NASDAQ) | Closed **2023-03-30** | Great Southern Homes became a publicly-traded builder brand under UHG. [businesswire.com/news/home/20230513005016, retrieved 2026-08-21] |
| Smith Douglas Homes Corp. | SDHC | IPO (NYSE) | Priced 2024-01-10; trading began **2024-01-11** | $21.00/share (high end of range), ~$162M raised. [bloomberg.com/news/articles/2024-01-11/homebuilder-s-strong-debut-brings-needed-win-in-tepid-us-ipo-market-for-2024, retrieved 2026-08-21] |

**Two names appear on both the entry-side census and §2a as full round-trips within the study window: The New Home Company (IPO 2014-01-30 → taken private 2021-09-08) and William Lyon Homes (re-IPO 2013-05-21 → acquired 2020-02-06, itself following an earlier 2011–2012 Chapter 11).** Neither round-trip is visible to any single-date roster snapshot, which is the structural point this sub-census exists to make.

---

# 3. Denominator crosswalk [freeze §7.2 condition 4]

**Standing rule restated (binding):** "One canonical cancellation-rate denominator per issuer is frozen with a printed conversion; a mandatory alternate-convention sensitivity re-run is required; a result that flips under the alternate convention is not a pass." This document freezes the conversion and registers the alternate-convention sensitivity plan. **It computes no re-run** — that is fitting, out of scope by the FROZEN SPEC.

## 3a. As-reported denominator convention by issuer (all primary-EDGAR-sourced)

| Issuer | As-reported cancellation-rate convention | Formula (as disclosed, exact quote) | Illustrative reported value (own citation) |
|---|---|---|---|
| DHI | Gross-orders convention (single) | *"Cancellation rate represents the number of cancelled sales orders divided by gross sales orders."* | Three months ended 2026-06-30: 20% (vs. 17% in the year-earlier quarter). [D.R. Horton Form 10-Q for the period ended June 30, 2026, `dhi-20260630.htm`, accession 0000882184-26-000096, https://www.sec.gov/Archives/edgar/data/882184/000088218426000096/dhi-20260630.htm, retrieved 2026-08-21] |
| PHM | Gross-orders convention (single) | *"Cancellation rates (canceled orders for the period divided by gross new orders for the period)"* | *"...were 13% for both the three and six months ended June 30, 2026, and 15% and 14% for the three and six months ended June 30, 2025, respectively."* [M3, exact quote] [PulteGroup Form 10-Q for the period ended June 30, 2026, `phm-20260630.htm`, accession 0000822416-26-000036, https://www.sec.gov/Archives/edgar/data/822416/000082241626000036/phm-20260630.htm, retrieved 2026-08-21] |
| TOL | **Dual convention** — TOL discloses both a beginning-backlog basis and a signed-contracts basis in the same exhibit | *"Quarterly Cancellations as a Percentage of Beginning-Quarter Backlog"*; *"Quarterly Cancellations as a Percentage of Signed Contracts in Quarter"* | Q3 FY2026 (three months ended 2026-07-31): **2.6%** beginning-backlog basis vs. **5.4%** signed-contracts basis (prior year: 3.2% / 7.5%) — implied ratio 5.4/2.6 ≈ **2.08**. [M2, exact figures] [Toll Brothers Form 8-K Exhibit 99.1, `tol-7312026x8kexh991.htm`, accession 0000794170-26-000096, https://www.sec.gov/Archives/edgar/data/794170/000079417026000096/tol-7312026x8kexh991.htm, retrieved 2026-08-21] |
| KBH | Gross-orders convention (single; verified against primary EDGAR filing) | *"Cancellation rate represents the total number of contracts for new homes cancelled during a period divided by the total (gross) orders for new homes generated during the same period."* | Three months ended 2026-05-31: 12% (vs. 16% in the year-earlier quarter). [KB Home Form 10-Q for the period ended May 31, 2026, `kbh-20260531.htm`, accession 0000795266-26-000063, https://www.sec.gov/Archives/edgar/data/795266/000079526626000063/kbh-20260531.htm, retrieved 2026-08-21] |
| LEN | **No press-release cancellation-rate line item in the current disclosure format — frozen exclusion per freeze §7.2 condition 1.** | N/A | This session's review of Lennar's Q1–Q4 FY2025 earnings press releases found average-sales-price and backlog unit/dollar tables but no cancellation-rate figure, consistent with the frozen finding. Historical LEN 8-K exhibits (e.g. Q4 2022) did carry a cancellation-rate figure ("26% in Q4 2022 compared to 12% the prior year" per a third-party summary of the LEN 8-K, retrieved 2026-08-21) — the disclosure itself is era-correlated, exactly the missingness pattern the frozen exclusion names. |
| NVR | **Dual convention [M1, corrected]** — NVR discloses BOTH a gross-sales-basis figure AND an opening-backlog-basis figure in the same paragraph of its own 10-K | *"Our cancellation rate was approximately 17%, 14% and 13% in 2025, 2024, and 2023, respectively, calculated as the total of all cancellations during the period as a percentage of gross sales during the same period. During the four quarters of each of 2025, 2024, and 2023, approximately 6%, 5% and 4% of a reporting quarter's opening backlog, respectively, cancelled during the quarter."* | FY2025: 17% (gross-sales basis) vs. ~6% (opening-backlog basis, quarterly average). [NVR, Inc. Form 10-K for FY2025, `nvr-20251231.htm`, accession 0000906163-26-000018, https://www.sec.gov/Archives/edgar/data/906163/000090616326000018/nvr-20251231.htm, retrieved 2026-08-21] |

## 3b. Canonical denominator selection and printed conversion

**Canonical denominator selected per issuer (one per issuer, per the standing rule — not one per family):**

- DHI, PHM, KBH: canonical = **gross orders in the period** (single convention, verified primary-source).
- TOL: canonical = **gross signed contracts in the period** (its own "signed contracts" basis), chosen for cross-issuer comparability with the gross-orders convention. TOL's alternate basis (beginning-of-period backlog) is registered as an alternate-convention sensitivity leg (§3c), not discarded.
- NVR: canonical = **gross sales in the period** (its primary-quoted figure, e.g. 17%/14%/13% for FY2025/24/23) — the same convention family as DHI/PHM/KBH. NVR's opening-backlog-basis figure (6%/5%/4%) is registered as its own alternate-convention sensitivity leg (§3c) — **NVR is no longer treated as single-convention** [M1].
- LEN: no canonical denominator is frozen — the cell class itself is excluded (§7.2 condition 1).

**Printed conversion (definitional, not computed on any data):**

```
cancellation_rate_backlog_basis  = cancellations_in_period / beginning_backlog_units
cancellation_rate_orders_basis   = cancellations_in_period / gross_orders_in_period
```

These two ratios share the same numerator but different denominators (a stock measured at period-start vs. a flow measured during the period), so they are **not** algebraically convertible by a fixed multiplicative factor — the conversion factor `beginning_backlog_units / gross_orders_in_period` is itself a ratio that varies by issuer, quarter, and cycle phase (regime-dependent: it compresses when orders surge relative to backlog and expands when orders fall relative to backlog). TOL's own Q3 FY2026 pair (2.6% / 5.4%, §3a) gives one directly-observed instance of this ratio (≈2.08) — printed as an illustration of the relationship, **not** as a fitted or estimated conversion factor for any other period, issuer, or cell.

## 3c. Registered alternate-convention sensitivity plan (plan only — compute nothing)

Per the standing rule: "a mandatory alternate-convention sensitivity re-run is required; a result that flips under the alternate convention is not a pass." This document registers the plan; it performs none of it now.

- **Primary convention (registered):** gross-orders basis, applied to DHI/PHM/KBH/NVR; signed-contracts basis for TOL (LEN excluded per §7.2(1)).
- **Alternate convention — per-issuer availability enumerated NOW [M13]:**

| Issuer | Alternate (backlog-basis) leg available? | Basis |
|---|---|---|
| NVR | **YES** — disclosed directly (§3a/M1) | NVR's own 10-K quotes both bases in one paragraph. |
| TOL | **YES** — disclosed directly (§3a/M2) | TOL's own 8-K exhibit quotes both bases side by side. |
| DHI | **NO** — checked against `dhi-20260630.htm`; no "opening backlog" or "beginning backlog" cancellation phrasing found in this session's full-text search of the filing. | Primary-source negative check, retrieved 2026-08-21. |
| PHM | **NO** — checked against `phm-20260630.htm`; same negative result. | Primary-source negative check, retrieved 2026-08-21. |
| KBH | **NO** — checked against `kbh-20260531.htm`; the filing discloses only the gross-orders basis (§3a quote); no backlog-basis figure found. | Primary-source negative check, retrieved 2026-08-21. |
| LEN | N/A — excluded from the cancellation-rate cell class entirely (§7.2(1)). | — |

**Pre-declared abstention rule [M13]:** an issuer without a disclosed or derivable backlog-basis figure is **excluded BY NAME from the sensitivity re-run**, and the re-run is interpreted over the covered subset only — currently **{NVR, TOL}**. A future filing by DHI, PHM, or KBH that discloses a backlog-basis figure would add that issuer to the covered subset at that point; this document does not assume or forecast such a disclosure.

- **Sensitivity test (registered, not run):** any future promotion-adjacent cell computed under the primary convention, over the {NVR, TOL} covered subset, must be re-run under the alternate convention on the same population and fold structure; a sign flip or promotion-conjunction failure under the alternate convention is a fail — no partial credit.
- **Frozen now, pre-outcome:** the conventions, the covered-subset enumeration, and the re-run requirement are frozen in this document, before any outcome access, satisfying contract §2(b) [A17].

---

# 4. Fiscal→calendar re-key [freeze §7.2 condition 3]

**Standing rule restated (binding):** "Episodes are re-keyed on calendar month; the fiscal→calendar crosswalk is frozen pre-outcome; no re-key is permitted after outcome access" [contract §2(a), A17]. Fiscal year-ends span **September 30 (DHI) → December 31 (PHM, NVR)**.

## 4a. Per-issuer fiscal quarter → calendar month crosswalk (unchanged from prior draft, re-verified)

| Issuer | FYE | Fiscal Q1 ends | Fiscal Q2 ends | Fiscal Q3 ends | Fiscal Q4 ends |
|---|---|---|---|---|---|
| DHI | Sep 30 | Dec 31 | Mar 31 | Jun 30 | Sep 30 |
| PHM | Dec 31 | Mar 31 | Jun 30 | Sep 30 | Dec 31 |
| TOL | Oct 31 | Jan 31 | Apr 30 | Jul 31 | Oct 31 |
| KBH | Nov 30 | Feb 28/29 | May 31 | Aug 31 | Nov 30 |
| LEN | Nov 30 | Feb 28/29 | May 31 | Aug 31 | Nov 30 |
| NVR | Dec 31 | Mar 31 | Jun 30 | Sep 30 | Dec 31 |

Cross-checked against actual filing dates: DHI 10-Q `dhi-20260630.htm` (Q3 ends Jun 30); PHM 10-Q `phm-20260630.htm` (Q2 ends Jun 30); TOL 8-K `tol-7312026x8kexh991.htm` (Q3 ends Jul 31); KBH 10-Q `kbh-20260531.htm` (Q2 ends May 31); NVR 10-K `nvr-20251231.htm` (Q4/FY ends Dec 31) — all retrieved 2026-08-21.

## 4b. Two separate keys, frozen for two separate purposes [B3, RULING — corrects the prior draft]

The prior draft used a single "calendar month of fiscal quarter-end" key and asserted it "makes cross-issuer comparison possible at all." **That claim was false and is struck.** Under a pure month-key, the six issuers land on **three mutually disjoint month grids**: DHI/PHM/NVR on {Mar, Jun, Sep, Dec}; TOL on {Jan, Apr, Jul, Oct}; KBH/LEN on {Feb, May, Aug, Nov}. TOL in particular shares its quarter-end month with **no other roster issuer, ever** — the month-key cannot pool TOL with anything.

**RULING (frozen now, in this wave):**

1. **Dating key = calendar month of the fiscal quarter-end date** (contract §2(a) wording). This is **this record's own operationalization** of the contract's bare "calendar month" phrase, not a form of words the contract itself specifies at this level of detail — flagged explicitly as this document's frozen choice, not a contract-mandated algorithm [m2]. It remains the correct key for *dating* an individual episode (e.g., "DHI's fiscal Q1 FY2026, ending 2025-12-31, dates to calendar December 2025").
2. **Pooling key (NEW) = calendar quarter by majority-month.** Each issuer's fiscal quarter is assigned to whichever calendar quarter contains **at least 2 of its 3 constituent months**. This is registered here, frozen, for the first time — it did not exist in the prior draft.

### Per-issuer fiscal-quarter → calendar-quarter mapping (majority-month rule)

| Issuer | Fiscal Q1 → | Fiscal Q2 → | Fiscal Q3 → | Fiscal Q4 → |
|---|---|---|---|---|
| DHI (Oct/Nov/Dec, Jan/Feb/Mar, Apr/May/Jun, Jul/Aug/Sep) | CQ4 (3/3 months) | CQ1 (3/3) | CQ2 (3/3) | CQ3 (3/3) |
| PHM (calendar-aligned) | CQ1 | CQ2 | CQ3 | CQ4 |
| TOL (Nov/Dec/Jan, Feb/Mar/Apr, May/Jun/Jul, Aug/Sep/Oct) | CQ4 (Nov+Dec, 2/3) | CQ1 (Feb+Mar, 2/3) | CQ2 (May+Jun, 2/3) | CQ3 (Aug+Sep, 2/3) |
| KBH (Dec/Jan/Feb, Mar/Apr/May, Jun/Jul/Aug, Sep/Oct/Nov) | CQ1 (Jan+Feb, 2/3) | CQ2 (Apr+May, 2/3) | CQ3 (Jul+Aug, 2/3) | CQ4 (Oct+Nov, 2/3) |
| LEN (same fiscal calendar as KBH) | CQ1 | CQ2 | CQ3 | CQ4 |
| NVR (calendar-aligned) | CQ1 | CQ2 | CQ3 | CQ4 |

### Coverage matrix — verified, printed [B3]

| | CQ1 (Jan–Mar) | CQ2 (Apr–Jun) | CQ3 (Jul–Sep) | CQ4 (Oct–Dec) |
|---|---|---|---|---|
| DHI | Fiscal Q2 | Fiscal Q3 | Fiscal Q4 | Fiscal Q1 |
| PHM | Fiscal Q1 | Fiscal Q2 | Fiscal Q3 | Fiscal Q4 |
| TOL | Fiscal Q2 | Fiscal Q3 | Fiscal Q4 | Fiscal Q1 |
| KBH | Fiscal Q1 | Fiscal Q2 | Fiscal Q3 | Fiscal Q4 |
| LEN | Fiscal Q1 | Fiscal Q2 | Fiscal Q3 | Fiscal Q4 |
| NVR | Fiscal Q1 | Fiscal Q2 | Fiscal Q3 | Fiscal Q4 |

**Verified [B3]: under the majority-month rule, all six issuers land on all four calendar quarters with zero collisions** — every issuer contributes exactly one of its four fiscal quarters to each of the four calendar quarters. This holds generally for any fixed FYE offset (a constant offset produces a fixed cyclic permutation of {CQ1..CQ4}, which is always a bijection), not merely as a coincidence of this specific roster. This is the key that actually enables cross-issuer pooling; the dating key (item 1 above) does not and was never claimed to after this correction.

Both keys are frozen now, pre-outcome, per the standing rule; no re-key of either is permitted after outcome access.

---

# 5. Structural-break ledger

Dated, per-issuer break entries, each typed with its consequence for cell membership. No entry implies an outcome judgment.

## 5a. Issuer-level breaks

| Issuer | Break | Date | Type | Consequence for cell membership |
|---|---|---|---|---|
| LEN | Spin-off of Millrose Properties, Inc. | **Completed 2025-02-07** | Business-model structural break (asset composition) | **Frozen break flag per freeze §7.2 condition 1.** No LEN episode may cross this date without a registered cross-epoch transfer test (contract §2, epoch-clock rule [G8-M2]). |
| LEN | Acquisition of WCI Communities, Inc. | Completed **2017-02-10** | M&A / consolidated-entity composition change | LEN's Florida/luxury segment composition changes; any LEN episode spanning this date mixes pre-/post-acquisition footprints. |
| LEN | Acquisition of CalAtlantic Group, Inc. | **Completed 2018-02-12** | M&A / scale-step-change (made LEN the largest U.S. homebuilder by revenue) | Largest single structural break in LEN's history in-window; requires an explicit epoch flag, not silent pooling. |
| **PHM** | **Acquisition of Centex Corporation [B1, NEW row]** | Agreement 2009-04-07; **completed 2009-08-18**; 0.975 PHM shares per CTX share, stock-for-stock, ~$3.1B incl. ~$1.8B net debt | M&A / scale-step-change | **Same consequence type as LEN/CalAtlantic** — a name that today reads as one continuous "PHM" series is actually two combined pre-2009 issuers (Pulte Homes and Centex Corp, CIK 18532). No PHM episode may cross 2009-08-18 without a registered cross-epoch transfer test; pre-merger Pulte-only history and pre-merger Centex history are non-comparable to post-merger PHM without an explicit flag. |
| DHI | Acquisition of a 75% majority stake in Forestar Group, Inc. | Agreement 2017-06-29; **effective 2017-10-05** | Business-segment addition (consolidated land-development subsidiary) | DHI's land-pipeline mechanism fields change composition after this date; flagged, not adjusted for. |
| All six | ASC 606 (revenue recognition) adoption | Effective for fiscal years beginning after 2017-12-15 | Reporting-convention change (fleet-wide) | Per-issuer adoption quarter is a **mechanical, not individually confirmed** consequence of each issuer's FYE (gap 2, §8). |
| Standard Pacific / Ryland (pre-roster, relevant to §2 substrate) | Merger into CalAtlantic Group | Closed **2015-10-01** | M&A / identity change | Not a roster member; any historical context panel drawing on pre-2015 SPF/RYL data must treat the merger as a hard break. |

## 5b. Source-level break sub-ledger [M8, NEW]

Structural breaks are not confined to issuers — a macro/context SOURCE can itself change construction mid-series, which is a distinct risk from ordinary revision (§7).

| Source | Break | Date | Type | Consequence |
|---|---|---|---|---|
| Freddie Mac Primary Mortgage Market Survey (PMMS) | Methodology change: survey-of-lenders → applications submitted to Freddie Mac's Loan Product Advisor (LPA); fees/points and the 5/1 ARM series **discontinued** | **2022-11-17** | Construction break (data-generating process changed, not merely a value revision) | Falls inside frozen block 6 (2022–2023 rate shock, §6a). **PMMS re-verdict [§7d]: vintage-clean (each weekly print is final and archived) BUT CONSTRUCTION-BROKEN at 2022-11-17** — any cell pooling PMMS observations across this date is pooling two different measurement instruments under one series name, distinct from and in addition to the ordinary vintage/revision question. [Freddie Mac Economic & Housing Research Note, https://www.freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf, retrieved 2026-08-21; corroborated by National Mortgage Professional, https://nationalmortgageprofessional.com/news/freddie-mac-updates-its-mortgage-rate-survey, retrieved 2026-08-21] |

---

# 6. Frozen block list + cell budget confirmation

## 6a. Frozen block list (verbatim from **contract §3 [A8]** — citation corrected [M6]; restated, not redesigned)

**Citation fix [M6]:** the literal seven-block list is frozen in `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` **§3, "Frozen historical block list [A8]"** — NOT in the architecture freeze's own §3 (which is the Owner/port matrix, a different table entirely). The prior draft mis-cited this as "freeze §3/A8"; corrected here and nowhere else in this document did the error recur.

**Evidence-column ruling [M4]:** blocks may **NOT** be defined or dated by cancellation rates — cancellation rate is itself `M_t`, the mechanism vector the trial conditions on, so using it as "defining evidence" for a block boundary is circular (the thing being measured cannot also certify when it happened). The evidence column below is retitled **"Illustrative context (not block-defining)"** and blocks 6 and 7's prior cancellation-rate citations are swapped for macro-series items. A rigorous macro-series evidence pass at each block *boundary* (not merely somewhere inside the block) is registered as an open item required before A4 (§8, gap 11) — this document's citations remain illustrative, not a boundary-dating exercise.

| # | Block | Boundary dates (frozen, per contract §3 [A8]) | Illustrative context (not block-defining) |
|---|---|---|---|
| 1 | GFC bust | 2006–2009 | NAHB Housing Market Index "hit its all-time low of 8 in January 2009, as housing starts dropped to a post-WWII low of around 0.5 million." [https://eyeonhousing.org/2020/01/a-decade-of-home-building-the-long-recovery-of-the-2010s/, retrieved 2026-08-21] Census §2 names 12 structurally-invisible/context-row events inside or overlapping this window (TOUSA, Kara Homes, Neumann Homes, Kimball Hill, Levitt and Sons among the earliest). |
| 2 | GFC recovery / land-light era | 2010–2013 | Orleans Homebuilders' Chapter 11 (filed 2010-03-01) and California Coastal Communities' (filed 2009-10-27, emerged 2011-03-01) both fall inside this block; "recovery... at a steady-but-very-slow pace" [same URL as above]. |
| 3 | 2013 taper (partial) | **No explicit start/end boundary is minted by this document — see [M5] below.** | "An almost one percentage point increase in the 30-year fixed mortgage rate between May and September of 2013" following Fed Chair Bernanke's tapering remarks; "the Housing Market Index (HMI) briefly fell below 50" the following year. [https://www.stlouisfed.org/on-the-economy/2017/march/housing-markets-face-taper-tantrum-moment, retrieved 2026-08-21 — **this is a Federal Reserve Bank of St. Louis BLOG post, not the FRED data-serving platform itself; clause (q)'s DO_NOT_INGEST binds the FRED data estate specifically and is untouched by citing this page's prose for a general historical fact [n1].**] |
| 4 | 2014–2019 grind, including the 2018 air pocket | 2014–2019 | "The homebuilder-tracking exchange traded fund SPDR S&P Homebuilders XHB was down around 25 percent since the start of 2018" on rate-hike pressure; builder sentiment fell "eight points to 60 in November [2018], marking the worst readout since August 2016." [https://www.benzinga.com/media/18/11/12724161/homebuilder-stocks-sanchez-gordon-tackle-rising-interest-rates-technical-suppor, retrieved 2026-08-21] Contains DHI's Forestar acquisition (2017-10-05), PHM's Centex integration anniversary period, LEN's WCI (2017-02-10) and CalAtlantic (2018-02-12) acquisitions, and fleet-wide ASC 606 adoption (§5). |
| 5 | 2020–2021 pandemic boom | 2020–2021 | "Thirty-year fixed rate mortgage rates dropped to an historic low of 2.7 percent in December 2020"; "building permits for new privately owned housing units have soared to levels last seen in 2007." [https://libertystreeteconomics.newyorkfed.org/2021/09/the-housing-boom-and-the-decline-in-mortgage-rates/, retrieved 2026-08-21] |
| 6 | 2022–2023 rate shock | 2022–2023 | **[M4: swapped to macro-series evidence]** Freddie Mac's own PMMS reported the 30-year fixed rate crossing 7% in 2022 for the first time in over two decades. [Freddie Mac, "Mortgage Rates Surpass Seven Percent," https://freddiemac.gcs-web.com/news-releases/news-release-details/mortgage-rates-surpass-seven-percent, retrieved 2026-08-21] The PMMS itself underwent a construction break at 2022-11-17 inside this block (§5b) — a second, source-level illustration of this block's disruption character, distinct from any issuer's cancellation rate. |
| 7 | 2024–2026 affordability/incentive era | 2024–2026 | **[M4: swapped to macro-series evidence]** PMMS reported the 30-year fixed rate at 6.65% as of 2026-08-20, still materially above the pre-2022 2.7%–4% range — consistent with a persistent-elevated-rate, incentive-dependent regime rather than a return to the prior era. [https://www.freddiemac.com/pmms, retrieved 2026-08-21] MDC Holdings' acquisition by Sekisui House (completed 2024-04-19, §2a-i) and LEN's Millrose spin-off (completed 2025-02-07, §5a) both fall inside this block. |

## 6b. Cell budget confirmation

Per contract §1 (A5/A6) and §9a: **6 historical cells in one BH partition `imce_hist_v0` at q=0.10**, statuses predetermined `underpowered_accruing`. This census confirms the cell budget against the contract and creates no new cells:

| Trial family | Cells | LEN membership [M12, NEW column] | Contract citation |
|---|---|---|---|
| `rf.cycle_pattern.imce_phase_v0` | 3 (3 state targets × pooled homebuilder stratum × contrast [M vs family/age prior]) | **Not excluded by name** — but insofar as any of the D5 phase states this family targets (`order_softness`, `completed_inventory_build`, `incentive_support`, `pace_recovery`) draws cancellation-rate as an `M_t` input feature, LEN's cancellation-rate exclusion (§7.2 condition 1) applies to that FEATURE within this cell's mechanism-vector construction, not to LEN's membership in the cell as a whole. The contract does not itself scope "cancellation-rate cells" to a named subset of the 6 — this document treats the exclusion as feature-level and universal across all 6 cells pending confirmation (flagged, §8). | contract §1, A5 |
| `rf.cycle_pattern.imce_sync_v0` | 2 (targets {`next_local_state_1rp`, `forward_63d_drawdown_tail`} × contrast [M+R vs M]) | Same feature-level treatment as above. | contract §1, A5 |
| `rf.cycle_pattern.imce_risk_v0` | 1 (`forward_63d_drawdown_tail` × [M vs family/stratum prior]) | Same feature-level treatment as above. | contract §1, A5 |
| **Total** | **6**, BH-FDR q=0.10 over the union as one partition `imce_hist_v0` | LEN is a roster member in all 6 cells at the ISSUER level; its exclusion binds at the cancellation-rate FEATURE level within `M_t` construction for whichever cells use that feature — this is this document's best-effort reading, not a contract-confirmed scoping (gap, §8). | contract §1, A6; §9a |

Honest historical blocks: **5–7** (freeze §7.2, §9a) — matches the 7-entry block list in §6a. **Floor and come-back date are two different quantities [m1, corrected]:** the promotion floor is `n_effective_blocks ≥ 40` (contract §8 item 5); the projected **come-back YEAR** at the census accrual rate is **~2145** (contract §9a/§13) — the prior draft's "(floor ~2145...)" parenthetical conflated the two into one number and is corrected here. Max reachable ladder rung on history: `REGISTERED`→`REPLAYED`, estimation-only, **never `DISPLAY`, never `PROMOTE_ELIGIBLE`.** **No new cell is created, proposed, or implied by this document.**

---

# 7. Per-source vintage audit [freeze §8 rider, G8-M6]

**Standing rule restated (binding):** "IMCE-HB-0 must add a per-source vintage audit for every GO macro/homebuilder source; any leg without retrievable vintages is declared `revision_optimistic` in the contract's `pit_class` and disclosed in every readout using it."

**Token discipline [M7, RULING]:** this document does **not** mint new `pit_class` tokens — doing so would repeat, one level down, the exact vocabulary-fragmentation defect that A2 (the CPI truth-contract audit, freeze §13) exists to fix. Only the ONE registered contract token, **`revision_optimistic`**, is used as an actual `pit_class` value below, and only where it genuinely applies. Every other verdict below is expressed as **prose** ("vintage-clean via filing immutability," "partially vintage-mitigated," etc.) — description, not a proposed schema token. The three prose phrases this document uses are registered as a **candidate vocabulary decision for A4** (§8, gap 10), not adopted here.

## 7a. SEC_EDGAR — GO (prose: vintage-clean via filing immutability)

SEC EDGAR filings are filed once and not retroactively edited in place; a correction requires an explicit, separately dated amendment or a new, separately timestamped 8-K. This session directly retrieved the `submissions` JSON for all six roster issuers and directly fetched primary 10-K/10-Q/8-K documents for DHI, PHM, TOL, KBH, and NVR (§1, §3, §5). **Verdict: retrievable vintages exist by construction — every historical filing is its own permanent, dated vintage.**

## 7b. CENSUS_NRS (New Residential Sales) — GO (prose: partially vintage-mitigated)

Restated from freeze §8: "Census NRS in particular is revised for three subsequent months plus annual benchmarking (its own historical-release archive partially mitigates)." This session located and confirms the archive:

- Historic seasonally adjusted data back to January 1999: `https://www.census.gov/construction/nrs/historical_data/` [retrieved 2026-08-21].
- Historic Releases (archived monthly release PDFs, one per original release): `https://www.census.gov/construction/nrs/data/releases.html` [retrieved 2026-08-21].
- Revisions methodology page: `https://www.census.gov/construction/nrs/data/revisions.html` [URL confirmed present, retrieved 2026-08-21; full text not independently re-fetched].

**Verdict:** each monthly NRS figure has a retrievable **as-first-published** value via the archived release PDF, distinct from the current (revised) value. Not a full ALFRED-style vintage matrix, but a genuine point-in-time snapshot mechanism — matching the freeze's own "partially mitigates" characterization exactly. **This is prose, not the `revision_optimistic` token** — NRS is explicitly NOT that token per the freeze's own framing.

## 7c. DHI_IR and PEER_BUILDER_IR — GO (prose: vintage-clean via filing immutability)

Issuer investor-relations press releases relevant to this family are, for all six roster issuers, filed as exhibits to Form 8-K on EDGAR (confirmed directly throughout §2, §3, §5). The same immutability argument as §7a applies. **Verdict: DHI_IR and PEER_BUILDER_IR (PHM/TOL/KBH/LEN/NVR IR disclosures, to the extent they are also SEC exhibits) are vintage-clean via EDGAR filing immutability** — for these six issuers, "IR" and "EDGAR" are the same underlying artifact. Non-8-K IR-site-only content (investor-day slides, non-filed transcripts) is **not** covered by this verdict (gap 4, §8).

## 7d. UNDERLYING_MACRO_OWNERS — audited legs; leg-selection gap disclosed

**Gap disclosed up front:** neither the freeze nor the contract enumerates the exact `UNDERLYING_MACRO_OWNERS` legs by name. This document audits the three legs most obviously load-bearing for a homebuilder mechanism/context vector — mortgage rate, housing starts/permits, and house-price index — as the best-available reading of the frozen intent. **Exact leg-list confirmation against the G6 worker packet is required before A4** (gap 1, §8).

| Candidate leg | Underlying agency owner (not FRED) | Vintage mechanism found | Verdict |
|---|---|---|---|
| Mortgage rate | Freddie Mac, Primary Mortgage Market Survey (PMMS) | Weekly published rate is a survey/application-data result, archived at `https://www.freddiemac.com/pmms/pmms_archives` back to 1971 [retrieved 2026-08-21] | **GO (candidate leg — not yet confirmed against the G6 packet [M9, added here — this qualifier was missing from the prior draft's PMMS row]).** Prose: vintage-clean, no revision of the published print. **BUT construction-broken at 2022-11-17 (§5b, M8)** — a source-level structural break distinct from and in addition to the vintage question; any cell pooling PMMS across that date must flag it. |
| Housing starts / permits | U.S. Census Bureau, New Residential Construction (NRC) | Own "Historic Releases" archive of past monthly release PDFs at `https://www.census.gov/construction/nrc/data/releases.html` [retrieved 2026-08-21], structurally parallel to NRS's (§7b); the underlying series is Census-collected, not FRED-collected — FRED's `HOUST`/`PERMIT` are republications of this same Census source | **GO (candidate leg — not yet confirmed against the G6 packet).** Prose: partially vintage-mitigated, same basis as NRS. |
| House-price index | Federal Housing Finance Agency (FHFA), House Price Index | FHFA publishes dated quarterly/monthly PDF reports, but this session found no dedicated systematic historical-vintage archive page comparable to Census's `nrs/data/releases.html`; FHFA's index is revised with each new dataset, including a documented methodology change with the 2012Q2 data release that "impacts the all transactions index (HOFHOPI) at the state and national level for the full history of the series (back to 1975Q1)" [**citation corrected [M16]** — Joseph M. Silverstein, "House Price Indexes: Methodology and Revisions," Federal Reserve Bank of Philadelphia research paper, https://www.philadelphiafed.org/-/media/frbp/assets/economy/reports/research-rap/2014/house-price-indexes.pdf, retrieved 2026-08-21; the prior draft's citation to `fhfa.gov/media/32126` was wrong — that document is FHFA's own February 2010 revisions paper and predates the 2012Q2 event it was cited to support] | **GO (candidate leg — not yet confirmed against the G6 packet), `pit_class = revision_optimistic`** — the ONE genuine use of the registered token in this document. Direction of the verdict is unchanged by the citation fix; only the supporting source is corrected. |

**Disclosure obligation restated:** any future readout using the FHFA HPI leg must carry its `revision_optimistic` disclosure. All three legs — mortgage rate, starts/permits, HPI — carry the same "(candidate leg — not yet confirmed against the G6 packet)" qualifier [M9]; none is presented as settled procurement.

---

# 8. Gaps (typed, renumbered)

1. **G6 worker packet not locatable.** The full 22-row source-rights verdict table is "preserved in the handoff record" (freeze §8/§10) but was not found in this session's accessible files. §7d's leg selection (mortgage rate, housing starts/permits, HPI) is this session's own reading, not a citation to an authoritative leg list — must be confirmed before A4.
2. **ASC 606 per-issuer adoption quarter not individually confirmed** against each of the six issuers' own 10-K adoption disclosures (only NVR, M/I Homes, and Green Brick Partners were directly confirmed, and the latter two are not roster members).
3. **Kimball Hill Homes' precise legal/registrant status is incompletely resolved** (private with some public-debt SEC filings; sufficient for the §2a-iii context-row disposition, not for deeper identity work).
4. **Non-EDGAR IR-site-only content's archival permanence not separately verified.**
5. **Study window pre-2006 casualties excluded by construction** (e.g., U.S. Home Corp, acquired by **Lennar** in 2000 [corrected — the prior draft's §2/§1 framing mis-associated this pre-window fact with "DHI/US Home-era," a wording error now fixed; U.S. Home was never a DHI transaction], and Crossmann Communities, acquired by Beazer Homes in 2002). Flagged as out-of-window by design.
6. **Stock Identity episode substrate's own survivor-stamping was not independently audited** — separate owner, out of scope.
7. **FHFA HPI vintage mechanism may be understated** given the time available in this pass.
8. **NRC's status as an authorized `UNDERLYING_MACRO_OWNERS` leg is unconfirmed**, not merely its vintage properties — see gap 1.
9. **ρ (the DEFF correlation parameter) is NOT frozen in HB-0 [M14, NEW].** Contract §3's DEFF rule (A9) requires `n_effective_blocks` to be derived via a design-effect estimator using a correlation parameter ρ "frozen pre-outcome and fit on train folds only" — this document does not set, estimate, or bound ρ for any cell. **Typed REQUIRED-BEFORE-A4, reserved to the Sol/Fable A4-gate adjudication** — Sol's authorization of this wave explicitly reserves final statistical-unit/power questions to that later adjudication. Until ρ is frozen, `n_effective_blocks` cannot be computed for any cell, and ρ remains a live analyst degree of freedom — which is itself a reason outcome access must wait for A4, not merely a documentation gap.
10. **`pit_class` vocabulary not registered [M7, NEW].** This document proposes three prose verdicts ("vintage-clean via filing immutability," "partially vintage-mitigated," "vintage-clean, no revision") as descriptions, not as adopted schema tokens — only `revision_optimistic` is a registered token and only the FHFA HPI leg carries it. Whether these three prose distinctions should become registered tokens (and if so, under what names) is an A4 vocabulary decision, explicitly deferred rather than decided unilaterally here.
11. **Macro-series evidence at each block BOUNDARY is required before A4 [M4, NEW].** This document's block-evidence column (§6a) is illustrative context, not a rigorous boundary-dating exercise — cancellation-rate-based "defining evidence" was struck as circular (M4) for blocks 6–7, but no block's boundary DATE in this document was itself re-derived from a macro series either; a systematic macro-series dating pass across all 7 boundaries is open A4 work.
12. **The "2013 taper (partial)" block's exact start/end boundary dates are not given in the contract, and this document does not mint them [M5, NEW].** The contract's frozen block list (§3 [A8]) names this block by label only, without the explicit date-range the other six blocks carry. Minting a specific "2013" boundary here — as the prior draft did — would violate contract §3's effective-block-count/no-overlap law [A9], which requires blocks to have crisp, non-overlapping, pre-registered boundaries before they can be used in any independence-counting computation; a casually-minted boundary in a census document is not that registration. The exact boundary-date determination is left as an open A4 item.

**Inherited-defect notes (not corrected by this document, since it may not redesign the freeze):**
- **[m8]** Freeze §7.2's own heading says "under four conditions" but then enumerates conditions (1)–(5) — a freeze-side miscount. This document inherits and restates all five numbered conditions as written; the "four" in the freeze's prose is not fixed here, since fixing it would be redesigning the freeze, not censusing under it.

---

# 9. No-fitting / no-new-procurement / no-new-scope proof

- No forward return, drawdown, Brier score, calibration statistic, p-value, correlation, or regression appears anywhere in this document.
- No cross-issuer mean, pooled cancellation rate, or trend line was computed; every numeric value cited is an issuer's or agency's own reported figure, cited to its own primary source, presented as a definitional/structural-break illustration.
- No `data/` write, no trial-ledger row, no `declared_budget` entry, no engine/scripts/config/site/.github/test/agentos edit. This packet's only change is the one owned file: `research/imce/IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md`.
- **No new source was purchased, licensed, or proposed for purchase [M9, corrected].** Every source discussed is EITHER already GO-dispositioned by the freeze's G6 pass at the CATEGORY level (SEC_EDGAR, CENSUS_NRS, DHI_IR/PEER_BUILDER_IR, UNDERLYING_MACRO_OWNERS) OR — for all three specific `UNDERLYING_MACRO_OWNERS` legs this document audits (mortgage rate/PMMS, housing starts-permits/NRC, HPI/FHFA, alike) — presented as an unconfirmed candidate leg requiring the commissioning session's confirmation against the G6 packet (§7d, gap 1). The prior draft's phrasing implied PMMS/mortgage-rate was already-settled while only NRC/FHFA carried the candidate-leg qualifier; that asymmetry is corrected — all three legs carry it equally.
- No cell was created, renamed, or resized. §6b confirms the frozen 6-cell budget against the contract; it proposes none.

---

# Appendix — Full source index (all retrieved 2026-08-21)

**SEC EDGAR — company records:**
- https://data.sec.gov/submissions/CIK0000882184.json (DHI) · CIK0000822416.json (PHM) · CIK0000794170.json (TOL) · CIK0000795266.json (KBH) · CIK0000920760.json (LEN) · CIK0000906163.json (NVR) · CIK0000357294.json (HOV) · CIK0000915840.json (BZH) · CIK0000799292.json (MHO) · CIK0000833079.json (MTH) · CIK0001562476.json (TMHC)

**SEC EDGAR — primary filings fetched and quoted directly:**
- https://www.sec.gov/Archives/edgar/data/882184/000088218426000096/dhi-20260630.htm
- https://www.sec.gov/Archives/edgar/data/822416/000082241626000036/phm-20260630.htm
- https://www.sec.gov/Archives/edgar/data/794170/000079417026000096/tol-7312026x8kexh991.htm
- https://www.sec.gov/Archives/edgar/data/795266/000079526626000063/kbh-20260531.htm
- https://www.sec.gov/Archives/edgar/data/906163/000090616326000018/nvr-20251231.htm

**SEC EDGAR — issuer-specific historical filings/exhibits cited inline:** see §2b, §5.

**Census Bureau:**
- https://www.census.gov/construction/nrs/historical_data/
- https://www.census.gov/construction/nrs/data/releases.html
- https://www.census.gov/construction/nrs/data/revisions.html
- https://www.census.gov/construction/nrc/data/releases.html

**FHFA:**
- https://www.fhfa.gov/data/hpi
- https://www.philadelphiafed.org/-/media/frbp/assets/economy/reports/research-rap/2014/house-price-indexes.pdf (replaces the prior draft's incorrect `fhfa.gov/media/32126` citation for the 2012Q2 claim [M16])

**Freddie Mac:**
- https://www.freddiemac.com/pmms/pmms_archives
- https://freddiemac.gcs-web.com/news-releases/news-release-details/mortgage-rates-surpass-seven-percent
- https://www.freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf (PMMS 2022-11-17 methodology-change note, §5b/M8)
- https://www.freddiemac.com/pmms

**Issuer IR / press-release / news / court-record sources:** see inline citations, §2b, §2d, §2e, §6a.

---

**End of IMCE-HB-0 (revised). This document authorizes nothing beyond itself. No cell, model, score, or outcome computation has started. The next authorized act on this family is either (a) the commissioning session's confirmation of the §8 gaps, or (b) wave A4 (IMCE-03 preregistration finalization / `declared_budget` rows), separately authorized and not performed here.**

# Special Situations Digest — Recon Findings

*Publisher: **Clark Square Capital** · weekly, every Sunday (issues #1–19, Feb 8 – Jun 14 2026; free #1–9, Pro #10–19, $149/yr). Based on a full programmatic capture of all 4,471 situations via the public data host `situations-database.pages.dev` — index + 19 per-issue detail files, processed deterministically.*

## 0. Executive summary — the answers

- **Are they just reading EDGAR? — NO.** SEC EDGAR is only **17.9%** of sourced situations (802 of 4,471). The feed is genuinely multi-jurisdiction: Japan TDnet/EDINET 7.3% (327), UK RNS/LSE 3.7% (164), HK HKEX 2.4% (106), Korea DART 1.7% (78), Canada SEDAR+ 1.2% (54), plus News media 7.6% and Newswire 6.1%, all sitting under a 51.0% "Other/IR/exchange-or-data-platform" bucket. **The US is only 45.1% of situations (2,018) — the non-US majority (55%) is the whole point of the product.** EDGAR alone would miss ~82% of the catalog and 100% of the international book.

- **Manual or automated? — Heavy automation + LLM-assisted writing + light editorial curation (inference).** The shape of the data is a structured pipeline, not hand-keying: per-issue detail JSON keyed by id; USD-normalized market cap and EV strings; GICS-style industry tagging; a stable 16-field schema; and ~88-word summaries that *consistently* cross-map foreign filings to their US analogues ("the Japanese equivalent of a US 13D"). That cross-mapping pattern at scale is an LLM prompt template, not 4,471 individual authorial decisions. The deterministic parts (category, metrics, schema) look rule-driven; the prose looks model-generated against a fixed skeleton; the taxonomy evolution (coarse early buckets later split) reads like a human editor refining the schema over 19 issues. *Stated as inference from data structure, not confirmed.*

- **Can we build it? Build vs subscribe? — Build, US-first.** The US slice (2,018 situations) is highly reproducible: EDGAR event-forms map cleanly to the mature taxonomy (see D2), and we already hold the enrichment data (fundamentals, 13F, insider, prices). The **international 55% is the real moat** — multi-regulator ingest in Japanese/Korean/Chinese is expensive and is exactly what a subscription buys you. Recommendation: **build US-first, study-not-copy the schema/taxonomy, and integrate into baskets / GEX / radar / Mastermind** (an integration edge a standalone newsletter cannot match). Subscribe only if/when international coverage becomes a hard requirement before we're ready to build the Japan lane.

- **Does it need LLM writing? — Yes, but only for the 88-word summary.** Categorization, metrics, and the schema are deterministic (form-type routing + fundamentals join). The single LLM touchpoint is the prose paragraph — one batched Haiku/DeepSeek call per situation against a fixed five-part skeleton.

- **Market-cap floor? — They have none.** Smallest ~$0.002M; 820 situations are sub-$50M, including nano-caps. This is a deliberate coverage choice. **We must make our own floor decision** (a floor materially cuts volume and noise but forfeits the micro/nano special-situations niche).

## A. Census

### A1 — Situations by category (all 4,471)

| Category | Count | % |
|---|--:|--:|
| Acquisitions | 637 | 14.2% |
| Activist Campaigns | 626 | 14.0% |
| Restructuring | 547 | 12.2% |
| M&A / Divestitures | 435 | 9.7% |
| Strategic Reviews | 399 | 8.9% |
| Divestitures | 325 | 7.3% |
| Other Situations | 270 | 6.0% |
| Tender Offers | 203 | 4.5% |
| Going-Private | 169 | 3.8% |
| Capital Returns | 166 | 3.7% |
| Spin-Offs | 160 | 3.6% |
| Other | 141 | 3.2% |
| Rights Offerings | 117 | 2.6% |
| Delistings | 77 | 1.7% |
| SPACs | 55 | 1.2% |
| Liquidations | 39 | 0.9% |
| Issuer Tenders | 26 | 0.6% |
| Deal Terminations | 25 | 0.6% |
| Management Changes | 11 | 0.2% |
| Insolvency | 9 | 0.2% |
| Going-Private & Tender Offers | 8 | 0.2% |
| Restructuring & Busted M&A | 8 | 0.2% |
| Domicile Changes | 4 | 0.1% |
| Relistings | 4 | 0.1% |
| Litigation Outcomes | 2 | 0.0% |
| Demutualizations | 2 | 0.0% |
| New SpinCos | 2 | 0.0% |
| Delistings & Relistings | 2 | 0.0% |
| Insider Buying | 2 | 0.0% |

### A2 — By country (top 25) · US share = 45.1%

| Country | Count | % |
|---|--:|--:|
| US | 2018 | 45.1% |
| JP | 562 | 12.6% |
| UK | 325 | 7.3% |
| CA | 231 | 5.2% |
| HK | 185 | 4.1% |
| IN | 183 | 4.1% |
| AU | 179 | 4.0% |
| KR | 122 | 2.7% |
| SE | 86 | 1.9% |
| CN | 68 | 1.5% |
| IT | 53 | 1.2% |
| UN | 50 | 1.1% |
| DE | 48 | 1.1% |
| NO | 45 | 1.0% |
| SG | 41 | 0.9% |
| FI | 29 | 0.6% |
| FR | 26 | 0.6% |
| BR | 19 | 0.4% |
| NZ | 19 | 0.4% |
| CH | 14 | 0.3% |
| PH | 14 | 0.3% |
| MY | 13 | 0.3% |
| NL | 12 | 0.3% |
| ZA | 11 | 0.2% |
| IL | 9 | 0.2% |

*Total distinct countries: 64 (per their own canonical list; an additional ~50 records carry an "UN"/blank unattributed code).*

### A3 — Market-cap distribution ($M, n=3805)

- smallest: $0.0017M · p10: $12.0M · median: $588.0M · p90: $20500.0M · largest: $4500000.0M

| Band | Count | % |
|---|--:|--:|
| <$50M | 820 | 21.6% |
| $50M-$250M | 687 | 18.1% |
| $250M-$1B | 674 | 17.7% |
| $1B-$10B | 1001 | 26.3% |
| $10B-$50B | 413 | 10.9% |
| >$50B | 210 | 5.5% |

**No market-cap floor** — 820 situations (<$50M) incl. nano-caps.

### A4 — By industry (detail `ind` field; coverage ~24%)

| Industry/Sector | Count |
|---|--:|
| Biotechnology | 73 |
| Capital Markets | 49 |
| Metals and Mining | 43 |
| Chemicals | 26 |
| Software | 26 |
| Banks | 23 |
| Asset Management | 23 |
| Specialty Retail | 22 |
| Real Estate Management and Development | 21 |
| Industrial Materials | 21 |
| Software - Application | 19 |
| Banks - Regional | 19 |
| Pharmaceuticals | 18 |
| Oil, Gas and Consumable Fuels | 17 |
| Electronic Equipment, Instruments and Components | 14 |
| Electrical Equipment | 13 |
| Food Products | 13 |
| Machinery | 13 |
| Construction and Engineering | 13 |
| Drug Manufacturers - Specialty & Generic | 13 |

### Taxonomy evolution (category × issue range)

| Category | n | first issue | last issue | #issues used |
|---|--:|--:|--:|--:|
| Acquisitions | 637 | 7 | 19 | 13 |
| Activist Campaigns | 626 | 1 | 19 | 19 |
| Restructuring | 547 | 1 | 19 | 18 |
| M&A / Divestitures | 435 | 1 | 6 | 6 |
| Strategic Reviews | 399 | 1 | 19 | 19 |
| Divestitures | 325 | 7 | 19 | 13 |
| Other Situations | 270 | 1 | 9 | 8 |
| Tender Offers | 203 | 8 | 19 | 12 |
| Going-Private | 169 | 8 | 19 | 12 |
| Capital Returns | 166 | 7 | 19 | 12 |
| Spin-Offs | 160 | 7 | 19 | 13 |
| Other | 141 | 10 | 19 | 10 |
| Rights Offerings | 117 | 9 | 19 | 11 |
| Delistings | 77 | 8 | 19 | 12 |
| SPACs | 55 | 17 | 19 | 3 |
| Liquidations | 39 | 7 | 19 | 12 |
| Issuer Tenders | 26 | 7 | 13 | 6 |
| Deal Terminations | 25 | 15 | 18 | 4 |
| Management Changes | 11 | 1 | 3 | 3 |
| Insolvency | 9 | 19 | 19 | 1 |
| Going-Private & Tender Offers | 8 | 7 | 7 | 1 |
| Restructuring & Busted M&A | 8 | 7 | 7 | 1 |
| Domicile Changes | 4 | 19 | 19 | 1 |
| Relistings | 4 | 9 | 9 | 1 |
| Litigation Outcomes | 2 | 19 | 19 | 1 |
| Demutualizations | 2 | 15 | 15 | 1 |
| New SpinCos | 2 | 9 | 9 | 1 |
| Delistings & Relistings | 2 | 7 | 7 | 1 |
| Insider Buying | 2 | 7 | 7 | 1 |

## B. Taxonomy

### Mature category table

| Category | 1-line definition | Trigger event | Boundary note | Typical filing by region |
|---|---|---|---|---|
| **Acquisitions** | A company announces it is *buying* another entity (majority or controlling stake, asset package, or full merger where the covered company is the acquirer). | Definitive agreement, MOU, or shareholder/regulatory approval milestone on an inbound acquisition; EGM approval of equity-transfer resolutions (e.g., APT Electronics 83.58% EGM vote). | NOT a Tender Offer (acquirer goes direct to target shareholders, bypassing the target board); NOT a Divestiture (seller side of the same deal is filed under Divestiture). Double-counting: each deal has at most one Acquisitions entry (acquirer) and at most one Divestitures entry (seller); they are NOT the same record. | US: 8-K + Schedule 14A or merger proxy (DEF 14A); CA: SEDAR+ arrangement circular; AU: ASX scheme booklet; HK: HKEX circular; JP: TDnet material-fact notice; KR: DART merger report; CN: cninfo major-restructuring disclosure; EU: ad-hoc Pflichtmitteilung. |
| **Activist Campaigns** | An external shareholder publicly discloses a stake and/or agenda aimed at changing corporate strategy, capital allocation, board composition, or ownership structure. | 5%-threshold large-shareholding filing with stated activist or investment purpose; subsequent stake increases or public letters (e.g., Murakami group 10.77% filing seeking dividends/buybacks; AVI 7.18% reserving board-change rights). | NOT Capital Returns (management-initiated buybacks or dividends); NOT Strategic Reviews (board-initiated, not shareholder-pushed). An activist filing that *also* triggers a formal strategic review creates two entries. | US: SC 13D or 13D/A; JP: EDINET large-shareholding report; KR: DART large-holding report (purpose = "influence over management control"); UK: Rule 8.3 disclosure; EU: transparency notification; CA: early-warning report (NI 62-103). |
| **Strategic Reviews** | The board or a special committee formally announces an evaluation of strategic alternatives — sale, spin-off, recapitalization, asset sale, or wind-down — without yet naming a specific transaction. | Board resolution and public disclosure initiating a "review of strategic alternatives"; special-committee formation; interim-CEO mandate explicitly covering sale-or-wind-down options (e.g., ARCpoint 90-day mandate; Barnes & Noble Education going-concern + board-initiated review). | NOT Activist Campaigns (shareholder-pushed); NOT Restructuring (operational/financial distress restructuring already underway without a sale mandate); once a definitive transaction is announced, the situation migrates to Acquisitions, Divestitures, Spin-Offs, or Going-Private. | US: 8-K + press release; SEC filings referencing going-concern (10-Q/10-K); CA: SEDAR+ news release; UK: RNS regulatory announcement; other markets: exchange-filing equivalents. |
| **Restructuring** | A company undertakes an operational or balance-sheet restructuring — debt renegotiation, convertible-note redemption, arrangement proceedings, segment wind-down — that is distinct from a full liquidation, formal insolvency, or completed divestiture. | Court or regulatory approval of an arrangement plan; convertible-note redemption/conversion notice; announced operational restructuring with cost targets; "w restrukturyzacji" regulatory designation (e.g., Adiuvo Investments appeal dismissal; AEIS $136.7M convert redemption). | NOT Insolvency (formal court-supervised winding-up petition or Chapter 11/administration filed); NOT Liquidation (assets are being distributed and the entity ceases); NOT Divestiture (discrete asset sale is the primary event). A busted M&A that forces restructuring is captured here (legacy "Restructuring & Busted M&A" label). | US: 8-K (redemption notice, RSA announcement); IT: emarketstorage.it material event; PL: gpw.pl regulatory filing; JP: TDnet; UK: RNS; other: exchange material-event filing. |
| **Divestitures** | A company announces the *sale* of a subsidiary, business unit, property, or asset portfolio to a third party, where the covered company is the *seller*. | Definitive purchase agreement, signing of heads of terms, or shareholder vote on a substantial asset sale (e.g., Aterian asset sale to Trademark Global at $18M; Changshu Fengfan 60% stake sale; DigiCo LAX1/LAX2 sale). | NOT Acquisitions (buyer perspective); the same transaction appears in Divestitures for the seller and Acquisitions for the buyer — no double-counting within a single company record. A full company sale where the covered company is acquired appears in Acquisitions or Going-Private, not Divestitures. | US: 8-K + proxy (if shareholder vote required per DGCL §271); CN: cninfo restructuring disclosure; HK: HKEX circular; JP: TDnet material notice; CA: SEDAR+; AU: ASX announcement. |
| **Going-Private** | A publicly listed company is taken private through a merger, scheme of arrangement, or tender offer backed by a financial sponsor or controlling shareholder, with the explicit intent to delist the target. | Definitive merger/arrangement agreement with a PE sponsor or controlling party; scheme document issued; special-meeting vote scheduled (e.g., Avanos Medical AIP $25/sh; Blackline Safety Francisco Partners C$9+CVR; Animalcare Group Charterhouse scheme). | NOT Tender Offers (going-private specifically removes the public listing; a tender offer that does not delist sits in Tender Offers); NOT Acquisitions (acquirer-side entry for the same deal). A mandatory squeeze-out following a tender that crosses the compulsory-acquisition threshold stays in Going-Private (e.g., Gaumont Seydoux squeeze-out). | US: SC TO-T + DEF 14A; CA: SEDAR+ arrangement circular; UK: Rule 2.7 firm offer announcement (Takeover Code); AU: scheme of arrangement booklet; FR: OPR filing with AMF; HK: HKEX take-private circular. |
| **Tender Offers** | A third-party bidder makes a formal offer directly to shareholders at a stated price to acquire a block of shares — typically triggering regulatory disclosure obligations — where delisting is NOT the primary stated intent. | Filing of draft or final tender offer document; bidder crossing a statutory threshold that triggers a mandatory offer (e.g., SEBI Takeover Code Regulations 3/4; Austrian Takeover Act §25a); record date set for Letter of Offer (e.g., Accord Synergy mandatory open offer; Raiffeisen/Addiko 50.42% acceptance; Glenstone firm offer for AIRE). | NOT Going-Private (same mechanism but listed status preserved or not addressed); NOT Acquisitions (acquirer negotiates with the board, not directly with shareholders); NOT Issuer Tenders (the company buys its own shares). Mandatory open offers triggered by crossing a threshold (India SEBI, Austria, France AMF) live here. | US: SC TO-T; IN: SEBI open-offer DLOF; AT: OÖ Takeover Act filing; UK: Rule 2.7 + offer document (Takeover Code); FR: AMF offre publique; DE: BaFin Angebotsunterlage; AU: ASX bidder's statement. |
| **Spin-Offs** | A parent company separates a subsidiary or division into a standalone publicly traded entity by distributing shares to existing shareholders, or by a subsidiary IPO where the parent retains a majority stake. | Board approval of a demerger/spin distribution; prospectus filing for a subsidiary IPO (parent retains control); record date and ex-dividend date set for the distribution (e.g., ADHC GlucoGuard July 31 ex-date; ABF Primark demerger CFO appointment; CR Power New Energy Shenzhen IPO prospectus). | NOT New SpinCos (entry from the newly independent entity's perspective post-completion); NOT Divestitures (full sale to a third party with no share distribution to parent shareholders). A subsidiary IPO where the parent sells down to below majority is a Divestiture + Spin-Off. | US: Form 10 (new registrant) + 8-K distribution announcement; CN: A-share IPO prospectus (cninfo/CSRC); UK: RNS demerger circular; HK: HKEX listing application; CA: SEDAR+ information circular; AU: ASX prospectus. |
| **Capital Returns** | A company announces a buyback, special dividend, or other one-time capital distribution that is management-initiated and does not involve a change of control or a shareholder making the offer. | Board declaration of special dividend (ex-date/record date set); board authorization of an open-market or accelerated share-repurchase program; structured related-party buyback agreement signed (e.g., Acushnet $52.5M Magnus buyback; CR Mixc RMB0.341 special dividend; Cyient INR1,125 self-tender buyback). | NOT Issuer Tenders (company formally launches a tender offer to its own shareholders at a fixed price with a set acceptance period — distinct mechanism); NOT Rights Offerings (capital raising, not distribution); NOT Activist Campaigns (activist-demanded buybacks). | US: 8-K (item 8.01 repurchase, item 8.01 dividend); IN: BSE/NSE buyback record-date notice; HK: HKEX dividend announcement; JP: TDnet buyback notice; CA: SEDAR+ normal-course issuer bid notice. |
| **Rights Offerings** | A company raises equity capital by offering existing shareholders the right to subscribe to new shares, typically at a discount, on a pro-rata basis. | Dispatch of rights documents; record date for eligibility; General Meeting vote for conditional tranches (e.g., Beonic renounceable pro-rata rights; AIB $55M public rights offering; CleanTech Lithium multi-tranche conditional placing with July 1 vote). | NOT Capital Returns (rights offerings dilute, not distribute); NOT Issuer Tenders (company is buying, not selling shares); NOT SPACs (SPAC trust redemptions are a different mechanism). Placings, subscriptions, and retail offers attached to a rights offering are part of the same entry. | US: Form S-1 or S-3 + 8-K; UK: RNS prospectus + circular (FCA-approved); AU: ASX prospectus (renounceable entitlement offer); CA: SEDAR+ prospectus (NI 41-101); SG: SGX offer information statement. |
| **Delistings** | A company faces involuntary removal from an exchange (bid-price deficiency, financial standards failure) or executes a voluntary delisting unrelated to a going-private transaction. | Nasdaq/NYSE/ASX/exchange deficiency notice or delisting determination letter; reverse-split proxy to cure bid-price deficiency; final trading-day announcement; mandatory delisting period clock start (e.g., Curis reverse-split DEF 14A; Genprex Nasdaq delisting determination; Guoxin Culture final six-day delisting window). | NOT Going-Private (controlled PE buyout that also removes listing); NOT Insolvency (court-ordered suspension following Chapter 11/administration — captured in Insolvency); NOT Relistings (covered company is re-entering an exchange). Exchange-transfer to OTC following deficiency lives here. | US: Nasdaq/NYSE deficiency letter + 8-K (item 3.01); CN: Shanghai/Shenzhen mandatory delisting announcement (cninfo); UK: AIM delisting RNS; AU: ASX trading halt notice; KR: DART delisting notice. |
| **SPACs** | A blank-check company (SPAC) discloses, amends, or advances a business combination with a private operating company, or a private company is being brought public via a SPAC merger. | S-4 or S-4/A registration statement filing; definitive proxy statement; business combination agreement announcement; trust extension vote (e.g., Black Hawk/Vesicor S-4 amendment; CEPO/BSTR proxy materials; Aditxt/Ignite Copley carve-out combination). | NOT Acquisitions (traditional M&A where both parties are public); NOT Going-Private (reverse — private company going public, not public going private); NOT IPOs (SPAC mechanism specifically). A SPAC whose target was already public is unusual — still SPAC if the SPAC vehicle drives the transaction. | US: SEC S-4, DEFM14A, 8-K; SEC Form 15-12B (trust extension). Non-US SPACs rare but use local listing-authority filings. |
| **Liquidations** | A company or fund initiates an orderly wind-down of assets with the explicit intent to distribute proceeds to shareholders/unitholders and cease to exist as an operating entity. | Board or fund manager approval of a plan of voluntary liquidation; final trading date set for a fund delisting and asset distribution; stockholder vote scheduled on liquidation plan (e.g., BTG DIV REAL June 16 trading halt; FREVS voluntary-liquidation board approval + Fall 2026 vote; MMTC ministry-directed exit roadmap). | NOT Insolvency (court-supervised compulsory winding-up petition or Chapter 11, where there is no board-controlled plan); NOT Restructuring (liability renegotiation without an intent to distribute and cease operations); NOT Delistings (exchange-rule violation delisting where the company continues to operate). | US: 8-K (plan of liquidation) + DEF 14A (shareholder vote); BR: B3 material fact (fato relevante); IN: BSE/NSE disclosure; AU: ASX announcement. |
| **Issuer Tenders** | The company itself launches a formal tender offer to its own shareholders at a fixed price with a defined acceptance window, as a mechanism to retire shares or preferred securities at scale — distinct from an open-market repurchase. | SEC SC TO-I filing (US); formal offer document with stated offer price, acceptance period, and pro-rata mechanics (e.g., Eaton Vance preferred tender at $24,500 vs $25,000 liquidation preference; Haier Smart Home D-Share cancellation buyback; Cyient INR1,125 tender route under SEBI). | NOT Capital Returns (open-market or board-authorized repurchase without a formal tender process); NOT Going-Private (company is buying its own stock, not being acquired). The key distinguisher is the formal offer document with stated price and acceptance window. | US: SC TO-I + Schedule 14D-9; IN: SEBI buyback tender route (record date + acceptance window); HK: Hong Kong Share Buy-backs Code offer; DE: formal German tender pursuant to BaFin. |
| **Insolvency** | A company files for court-supervised insolvency proceedings (Chapter 11, administration, judicial management, winding-up petition, scheme of arrangement under insolvency statute) where the outcome — reorganization or liquidation — is determined by a court or insolvency practitioner. | Chapter 11 petition filed; winding-up petition hearing scheduled; judicial manager application; Singapore IRDA scheme application (e.g., GoHealth Chapter 11 + Nasdaq delisting determination; China Water winding-up adjournment; Hatten Land IRDA scheme sanction hearing). | NOT Restructuring (out-of-court debt renegotiation or arrangement without a court filing); NOT Liquidation (board-controlled voluntary wind-down not driven by creditor petition). A Chapter 11 that converts to Chapter 7 liquidation migrates to Liquidation only at conversion. | US: PACER (Bankruptcy court petition); HK: High Court winding-up petition; SG: SGX judicial management notice + court filing; UK: Companies House administration notice; JP: Tokyo District Court civil rehabilitation; IN: NCLT insolvency petition (IBC). |
| **Deal Terminations** | A previously announced transaction (acquisition, merger, going-private, asset sale, or equity financing facility) is terminated before closing, removing the deal-price floor and resetting the catalyst set. | Mutual termination agreement; break-fee payment; regulatory block (FTC/DOJ/ACCC) that causes abandonment; one party walking away citing failure to agree on terms (e.g., American Eagle terminates Pacific Booker bid; Shengbang terminates Woco acquisition; DNA X terminates Chardan $500M equity line). | NOT Restructuring (a busted deal that leads to operational restructuring is Deal Termination first, then Restructuring if operational changes follow); NOT Activist Campaigns (activist withdrawal is not a Deal Termination). The covered company can be either the acquirer or the target. | US: 8-K (material definitive agreement termination, item 1.02); CN: cninfo major-restructuring termination announcement; CA: SEDAR+ material change report; UK: Rule 2.8 announcement (no intention to bid); JP: TDnet cancellation notice. |

---

### B1. Resolved ambiguous-pair rules

**Acquisition vs Tender Offer vs Going-Private**

- **Acquisition**: the acquirer negotiates a definitive agreement with the *target board*. The board recommends, and shareholders vote on a merger/plan of arrangement. The covered company can be the acquirer or the target; it is filed under Acquisitions from the *acquirer's* perspective. The same deal appears as a Divestiture from the seller/target perspective only when the covered company is the seller.
- **Tender Offer**: the bidder bypasses board negotiation and goes *directly to shareholders* with a formal offer at a stated price and acceptance period. Mandatory open offers triggered by crossing a statutory threshold (SEBI 25%, Austrian 25%, French AMF, UK Rule 9) live here even when the intent is full control. Preserve as Tender Offer as long as the public listing is not the primary stated objective.
- **Going-Private**: the listed status is explicitly targeted for removal. The mechanism may be a scheme of arrangement, a merger, or a squeeze-out following a tender — the distinguishing feature is the announced intent to delist. A Tender Offer that crosses the compulsory-acquisition threshold and triggers a squeeze-out migrates to Going-Private at that point. Gaumont's court-ordered mandatory squeeze-out is Going-Private; Raiffeisen's offer for Addiko (no delisting announced) is Tender Offer.

**Divestiture vs Acquisition (buyer vs seller — no double-counting)**

A single M&A transaction generates *at most* two situation records: one Divestiture record for the selling company and one Acquisitions record for the buying company, *only if both companies are separately covered in the digest*. The records are not duplicates — they are distinct covered companies at different stages of the same transaction. If only one side is covered, only one record exists. Never file both categories for the same company on the same transaction.

**Spin-Off vs New SpinCo**

- **Spin-Off**: filed from the *parent* company's perspective, covering the separation announcement, record date, ex-dividend date, prospectus filing, and distribution mechanics. The parent is the covered company.
- **New SpinCo**: filed from the *newly independent entity's* perspective after it begins trading as a standalone. First Tracks Biotherapeutics (TRAX) and Versigent (VNT) are New SpinCos; AnaptysBio and Aptiv are Spin-Offs. The two categories can coexist for the same transaction across different covered-company records. A SpinCo that begins trading but has no meaningful post-separation catalyst yet may be omitted until a discrete event occurs.

**Restructuring vs Liquidation vs Insolvency vs Delisting**

Apply in descending order of severity:
1. If a court has accepted a petition or the company has filed for statutory insolvency protection → **Insolvency**.
2. If the board has approved (or shareholders will vote on) a voluntary wind-down with asset distribution and entity cessation → **Liquidation**.
3. If the company is renegotiating liabilities, executing operational resets, or navigating arrangement proceedings without a court insolvency petition and without a full asset-distribution plan → **Restructuring**.
4. If the primary event is a stock-exchange compliance failure (bid-price deficiency, financial-standards notice, forced delisting) and the company remains operationally intact → **Delisting**. GoHealth sits in Insolvency (Chapter 11 filed) even though Nasdaq also issued a delisting determination — the insolvency filing is the primary event.

**Issuer Tender vs Capital Return vs Rights Offering**

- **Capital Return**: board-authorized open-market repurchase or declared dividend; no formal offer document, no stated acceptance window, no fixed price per share as a tender.
- **Issuer Tender**: the company files a formal tender offer (SC TO-I or equivalent) at a specific stated price with a defined acceptance window and pro-rata proration mechanics. The Cyient INR1,125 buyback executed "through the tender offer route" under SEBI regulations is an Issuer Tender despite also being a capital return in economic terms — the regulatory mechanism determines the category. The Acushnet VWAP-based buyback with Magnus (no fixed price, no acceptance window) is Capital Return.
- **Rights Offering**: the company *raises* new equity from existing shareholders; cash flows into the company. Issuer Tender and Capital Return flow *out*. A simultaneous rights offering and capital return (rare) generates two records.

**Strategic Review vs Other**

- **Strategic Review**: the board or a special committee has explicitly announced it is evaluating alternatives with a defined mandate (sale, spin-off, recapitalization, wind-down), even if no transaction has been named. Cardiff Oncology's executive separation during a stated strategic review is still Strategic Review. ARCpoint's 90-day interim-CEO mandate to recommend a path is Strategic Review.
- **Other**: residual catch-all for events that are situation-relevant but do not fit a named category — poison-pill adoptions, convertible-note financings without a restructuring context, receivership appointments at the *shareholder* level (not company level), and other corporate governance events. Aldebaran's shareholder rights plan is Other; China Tianrui's receiver appointment over a *shareholder's* block (not the company itself) is Other.

**Deal Terminations vs Restructuring & Busted M&A**

"Restructuring & Busted M&A" is a deprecated early-issue label. In the mature taxonomy: when a deal terminates and the *primary news is the termination itself* (floor removed, break fee, regulatory block), file as **Deal Termination**. If the termination triggers a subsequent operational or financial restructuring of the company (e.g., New Fortress Energy RSA after deal collapse), file an *additional* Restructuring record for that company once the restructuring is announced — the two records are sequential, not merged. LENSAR/Alcon (FTC block → termination fee → standalone review) is Deal Termination; New Ingevity after completing the Industrial Specialties sale and resetting as a two-division company is Restructuring (the legacy "Restructuring & Busted M&A" label applied because the sale was the mechanism of the restructuring plan, not a true terminated deal).

---

### B2. Taxonomy evolution

The digest launched in issues 1–6 with three coarse buckets — **"M&A / Divestitures"** (435 records, issues 1–6), **"Other Situations"** (270 records, issues 1–9), and oversized **"Restructuring"** — that collapsed distinct situation types into single labels for speed of production; from issue 7 onward these were split into Acquisitions, Divestitures, Capital Returns, Spin-Offs, Liquidations, Tender Offers, Going-Private, and Rights Offerings, with SPACs added in issue 17 as that market segment revived. For a clone, the correct approach is to **adopt the mature 16-category set as the canonical schema** and maintain a `legacy_label` alias map (`"M&A / Divestitures" → ["Acquisitions", "Divestitures"]`; `"Other Situations" → ["Other", "Activist Campaigns", "Strategic Reviews", "Capital Returns"]`; `"Going-Private & Tender Offers" → ["Going-Private", "Tender Offers"]`; `"Restructuring & Busted M&A" → ["Restructuring", "Deal Terminations"]`; `"Delistings & Relistings" → ["Delistings", "Relistings"]`) so that historical records from issues 1–6 can be queried consistently without re-categorization.

## C. Per-situation schema

| Field | Coverage | Meaning |
|---|--:|---|
| `c` | 100.0% | company name |
| `t` | 99.6% | ticker (exchange-suffixed, e.g. ARX.TO, 2551.HK) |
| `co` | 99.8% | country code (ISO-2) |
| `cat` | 100.0% | category |
| `i` | 100.0% | issue number |
| `mc` | 85.1% | market cap (USD-normalized string) |
| `ev` | 80.4% | enterprise value (USD string) |
| `sec` | 25.6% | sector (index, sparse) |
| `hk` | 99.9% | headline (one-line) |
| `px` | 62.9% | share price (native currency, e.g. 'CAD 31.76') |
| `ind` | 23.9% | GICS-style industry (detail) |
| `m` | 48.4% | valuation metrics string |
| `biz` | 97.5% | 1-sentence business description |
| `s` | 99.9% | full prose analysis (the summary) |
| `u` | 99.7% | source URL (primary document/citation) |

**Valuation metrics in `m`:** EV/Sales (1777), EV/GP (1620), Fwd P/E (1611), EV/EBITDA (1404), Fwd EV/EBITDA (77), NTM P/E (3), NTM EV/EBITDA (2)

**Note on our existing data:** We already hold most of these fields natively. EDGAR fundamentals give us market cap / EV / the valuation-metric inputs (so `mc`, `ev`, `m` are derivable from data we ingest); our 13F and insider feeds and price history cover `t`/`px` and feed the activist/insider categories; GICS mapping covers `sec`/`ind`. Worth flagging that `ind` (23.9%) and `sec` (25.6%) are **sparse in their data too** — industry/sector tagging is not a coverage gap unique to us, and we can do better than they do by joining our own GICS table. The only field with no existing analogue is the LLM-written `s` summary.

## D. Source attribution

| Source bucket | Count | % |
|---|--:|--:|
| Other/IR/exchange | 2282 | 51.0% |
| SEC EDGAR | 802 | 17.9% |
| News media | 340 | 7.6% |
| Japan TDnet/EDINET | 327 | 7.3% |
| Newswire | 273 | 6.1% |
| UK RNS / LSE | 164 | 3.7% |
| HK HKEX | 106 | 2.4% |
| Korea DART/KIND | 78 | 1.7% |
| Canada SEDAR+ | 54 | 1.2% |
| India BSE/NSE | 15 | 0.3% |
| none | 15 | 0.3% |
| Australia ASX | 8 | 0.2% |
| EU regulators/OAM | 6 | 0.1% |
| badurl | 1 | 0.0% |

### Top 30 source hosts

| Host | Count |
|---|--:|
| sec.gov | 801 |
| disclosure2.edinet-fsa.go.jp | 191 |
| stocktitan.net | 187 |
| investegate.co.uk | 158 |
| tradingview.com | 147 |
| globenewswire.com | 146 |
| release.tdnet.info | 126 |
| finance.yahoo.com | 111 |
| www1.hkexnews.hk | 105 |
| ad-hoc-news.de | 83 |
| dart.fss.or.kr | 76 |
| cdn-api.markitdigital.com | 73 |
| theglobeandmail.com | 71 |
| static.cninfo.com.cn | 64 |
| marketscreener.com | 61 |
| prnewswire.com | 57 |
| sedarplus.ca | 54 |
| simplywall.st | 51 |
| morningstar.com | 47 |
| businesswire.com | 45 |
| view.news.eu.nasdaq.com | 41 |
| scanx.trade | 38 |
| app.tikr.com | 37 |
| tipranks.com | 35 |
| financialreports.eu | 35 |
| whalesbook.com | 28 |
| minichart.com.sg | 27 |
| emarketstorage.it | 25 |
| news.google.com | 23 |
| markets.businessinsider.com | 23 |

### US vs non-US source mix

- **US:** Other/IR/exchange 946, SEC EDGAR 736, Newswire 164, News media 156, none 6, UK RNS / LSE 5
- **non-US:** Other/IR/exchange 1336, Japan TDnet/EDINET 327, News media 184, UK RNS / LSE 159, Newswire 109, HK HKEX 106, Korea DART/KIND 78, SEC EDGAR 66

**Interpretation.** The single `u` URL is a **primary-document-when-available, else a data-platform citation**: when a regulator filing exists (sec.gov, edinet, tdnet, hkexnews, dart, sedarplus, cninfo) it is cited directly, but when the situation came from news or the metrics needed a price/valuation source, `u` points at a data platform (tradingview, finance.yahoo, simplywall.st, morningstar, tikr, tipranks, markitdigital) — which is what inflates the 51% "Other/IR/exchange" bucket. **Regulators dominate by region**, each market routed to its own feed: EDGAR for the US, EDINET/TDnet for Japan, RNS for the UK, HKEX for Hong Kong, DART for Korea, SEDAR+ for Canada, cninfo for China, ad-hoc-news for Germany. Critically, **SEC EDGAR alone misses ~82% of situations and effectively 100% of the non-US majority** (only 66 non-US records trace to EDGAR, almost all cross-listed FPIs filing 6-Ks). Any clone that ingests EDGAR only is structurally a US product — which is exactly why our recommendation is US-first with international as a deliberate later phase.

### D2. EDGAR-form -> category mapping (for our classifier)

| SEC EDGAR Form / 8-K Item | -> Special Situations Category | Notes / Conditions |
|---|---|---|
| **SC 13D** | Activist Campaigns | Schedule 13D = >5% beneficial ownership with intent to influence. Primary activist trigger. Check Item 4 (Purpose of Transaction) for explicit change-of-control/board/strategic language. Passive filers use 13G; a 13D filing is the bright-line activist signal. |
| **SC 13D/A** (amendment) | Activist Campaigns (escalation) | Amendments signal campaign progression: increased stake, updated demands, letter to board, proxy threat. Sequence of 13D/As maps to campaign lifecycle. Late amendments sometimes precede a tender or merger announcement — watch for pivot to SC TO-T. |
| **SC 13G -> 13D conversion** | Activist Campaigns | When a previously passive 13G holder re-files as 13D, this is the single cleanest activist-entry signal in EDGAR. Flag the delta: same filer, same issuer, form type flip. No false-positive risk from passive index funds. |
| **DEF 14A** (proxy, activist context) | Activist Campaigns | Definitive proxy with a dissident slate (competing director nominees, shareholder proposals). Distinguish from routine annual DEF 14A by scanning for "contested," "dissident," "withhold," or a second proponent. ISS/Glass Lewis mention also flags contested proxies. |
| **DEFC14A / PREC14A** | Activist Campaigns | Contested proxy statement filed by a dissident (non-management) soliciting party. Near-certain activist signal; management counter-filing is DEFA14A/DEFR14A. |
| **DEFM14A / PREM14A** | Acquisitions; Going-Private; Tender Offers | Merger proxy / preliminary merger proxy. If target is public and acquirer is a third party: Acquisitions. If acquirer is the company itself or a PE sponsor taking the company private: Going-Private. Cross-check consideration type (cash vs. stock). |
| **SC TO-T** | Tender Offers | Third-party tender offer (acquirer filing). Cash or cash+stock for target shares. Distinguish from Going-Private: if acquirer is unaffiliated strategic or financial buyer, use Tender Offers. If acquirer is a controlling shareholder or management-led buyout, pivot to Going-Private. |
| **SC TO-I** | Issuer Tenders; Capital Returns | Issuer self-tender (company buying back its own shares). Maps to Issuer Tenders category. If framed as a fixed-price or Dutch-auction buyback (not a going-private squeeze-out), treat as Capital Returns sub-type. Going-Private squeeze-outs by the issuer use SC 13E-3 concurrently. |
| **SC 14D-9** | Tender Offers (target response) | Target's solicitation/recommendation statement. Always paired with an SC TO-T. Signals the deal is live and target board has formally responded. Useful for tracking deal stage (recommend / oppose / explore alternatives). |
| **SC 13E-3** | Going-Private | Rule 13e-3 transaction: going-private by an affiliate. Near-certain Going-Private signal. Often filed alongside DEFM14A or SC TO-T. Controlling-shareholder buyouts, MBOs, and PE take-privates all trigger 13E-3. |
| **8-K Item 1.01** (material definitive agreement) | Acquisitions; Divestitures; Spin-Offs; Strategic Reviews | Broadest M&A trigger. Subclassify by reading the agreement type named in the filing: "Merger Agreement" -> Acquisitions; "Purchase Agreement" where company is seller -> Divestitures; "Separation Agreement" / "Distribution Agreement" -> Spin-Offs. Item 1.01 alone does not determine category — prose parsing required. |
| **8-K Item 2.01** (completion of acquisition/disposition) | Acquisitions (closed); Divestitures (closed) | Deal-close signal. Pair with prior Item 1.01 to confirm category. Item 2.01 = deal completed; update existing situation record's stage from "announced" to "closed" rather than creating a new situation. |
| **8-K Item 1.03** (bankruptcy/receivership) | Restructuring; Liquidations | Chapter 11 filing = Restructuring (reorganization intent). Chapter 7 = Liquidations. Also covers receivership and assignment for benefit of creditors. Check Item 1.03 description for "reorganization" vs. "liquidation" keyword to split. |
| **8-K Item 3.01** (notice of delisting / failure to satisfy listing rule) | Delistings | Exchange notification of non-compliance or delisting determination. Also watch for Item 3.02 (unregistered sales) as secondary signal. Form 25 (below) is the actual delisting instrument; 3.01 is the precursor notice. |
| **Form 25** (notification of delisting) | Delistings | Exchange-filed form that effectuates delisting. Definitive delisting signal. Distinguish voluntary delistings (company-initiated, often precedes Going-Private completion) from involuntary (exchange-initiated for non-compliance, ties to Restructuring or Liquidations). |
| **Form 15** (deregistration / suspension of reporting) | Delistings; Going-Private | Filed when a company suspends Exchange Act reporting (fewer than 300 holders or fewer than 500 holders with <$10M assets). Often the final administrative step after a Going-Private transaction completes. Can also appear in small-company voluntary delistings. |
| **Form 10** (registration of a class of securities) | Spin-Offs; New SpinCos | SpinCo registers its shares prior to distribution to parent shareholders. One of the cleanest Spin-Off signals. Also used by newly independent companies post-carve-out. S-11 (REITs) and S-1 (IPOs) should be distinguished from Form 10 (spin-offs specifically). |
| **S-1 / S-11** (IPO registration) | SPACs (if blank-check); else out-of-scope for special situations | Pure IPO S-1s are generally out of scope. Exception: blank-check company S-1 = SPAC formation. Flag S-1s where "blank check company" or "business combination" appears in the business description. |
| **S-4** (business combination registration) | Acquisitions; Going-Private; Spin-Offs | S-4 registers shares issued as merger consideration (stock deals). Also used for SPAC de-SPAC mergers (SPAC + target = S-4/proxy combo). De-SPAC S-4s with a named target = SPACs category. Pure stock-for-stock strategic mergers = Acquisitions. |
| **424B (prospectus supplement, rights context)** | Rights Offerings | 424B3 or 424B5 filed in connection with a rights offering registration (Form F-3/S-3 with rights offering disclosure). Confirm by checking for "rights offering," "subscription price," and "oversubscription privilege" language. Standalone 424B for shelf takedowns is out of scope. |
| **DEF 14A** (routine annual meeting, merger vote) | [See sub-cases above] | Routine annual DEF 14A with only standard director/compensation/auditor proposals = not a special situation. Flag only when it contains: (a) merger vote item, (b) contested director election, (c) going-private vote, (d) spin-off or asset sale ratification. |
| **6-K** (foreign private issuer current report) | [Category depends on content] | Foreign private issuers file 6-K instead of 8-K. Content is heterogeneous. Scan 6-K exhibit or text for M&A/tender/restructuring language. Treat as equivalent to the 8-K item it mimics. Many cross-listed Canadian, Israeli, and UK companies file 6-Ks; also used by Japanese ADR issuers. |
| **SC TO-T/A, SC 13E-3/A, DEFM14A/A** (amendments) | [Same as base form] | Amendments update deal terms, extend expiration dates, or respond to SEC comments. Track amendment sequences to monitor deal stage progression. A withdrawn SC TO-T/A or "Amendment No. X — Termination" maps to Deal Terminations. |
| **8-K Item 5.02** (departure/appointment of officers/directors) | Management Changes | CEO/CFO departure or appointment. Standalone = Management Changes (small category, 11 cases in dataset). When concurrent with an activist campaign or strategic review, treat as a sub-signal of those categories rather than a separate situation. |
| **8-K Item 8.01 / press release exhibits** | Strategic Reviews; Deal Terminations | Companies announcing "strategic alternatives review" or deal terminations typically file an 8-K with a press release as Exhibit 99.1. No dedicated Item number exists for these; classifier must parse Exhibit 99.1 text. |

---

### D3. International equivalents

| Regulator / Feed | Filing Type | -> Special Situations Category | Notes |
|---|---|---|---|
| **Japan TDnet / EDINET** | Large-shareholding report (大量保有報告書, 5% threshold) | Activist Campaigns | Equivalent to SC 13D/13G. Passive holders file "pure investment" purpose; activists file "exercise of shareholder rights." Purpose-code flip = activist conversion signal, mirroring the 13G->13D pattern. |
| **Japan TDnet** | Tender offer notification (公開買付届出書, TOB) | Tender Offers; Going-Private | Mandatory TOB for acquisitions above thresholds (>1/3 stake). MBO/affiliate TOBs = Going-Private. Third-party strategic = Tender Offers. Japan has no SC 13E-3 equivalent; Going-Private intent inferred from acquirer identity + TOB filing. |
| **Japan TDnet** | Merger/absorption announcement (吸収合併) | Acquisitions | Filed as a TDnet disclosure. Often accompanied by an EDINET registration. |
| **Japan TDnet** | Business restructuring / spin-off (会社分割) | Spin-Offs; Divestitures | Company split (Kaisha Bunkatsu) = Spin-Offs if shares distributed to shareholders; asset transfer = Divestitures. |
| **UK RNS (Regulatory News Service)** | Rule 2.7 announcement (firm intention to make an offer) | Acquisitions; Tender Offers; Going-Private | Under the UK Takeover Code, Rule 2.7 = firm bid announcement. The single clearest UK M&A trigger. Acquirer identity (strategic vs. PE) and target status (public vs. controlled) determine sub-category. |
| **UK RNS** | TR-1 (major shareholding notification, DTR 5) | Activist Campaigns | Equivalent to SC 13D/13G. Threshold crossings at 5%, 10%, 15%... Purpose disclosure less granular than US; activist intent inferred from filer identity (known activist funds) and follow-on RNS activity. |
| **UK RNS** | Possible offer announcement (Rule 2.4) | Strategic Reviews | Pre-Rule 2.7 "possible offer" disclosure. Company is in play but no firm bid yet. Maps to Strategic Reviews while the process runs. |
| **UK RNS** | Scheme of arrangement circular | Going-Private; Acquisitions | UK takeovers frequently use schemes rather than tender offers. Scheme circular = equivalent to DEFM14A. Court sanction hearing = deal-close signal. |
| **Canada SEDAR+** | Early Warning Report (EWR, NI 62-103) | Activist Campaigns | Required at 10% threshold (vs. US 5%). Purpose disclosure required; "to influence management" language = activist. Alberta filers use Alternative Monthly Report (AMR). Equivalent to SC 13D. |
| **Canada SEDAR+** | Take-Over Bid Circular (NI 62-104) | Tender Offers; Going-Private | Formal takeover bid document. Issuer bid (company buying own shares) = Issuer Tenders / Capital Returns. Third-party bid = Tender Offers. Insider/affiliate bid = Going-Private. |
| **Canada SEDAR+** | Plan of Arrangement circular | Acquisitions; Going-Private | Court-approved arrangement = Canadian equivalent of a merger proxy. Very common structure for Canadian M&A. |
| **HK HKEX** | SDI (substantial shareholder disclosure, SFO s.336) | Activist Campaigns | 5% threshold filing. Less commonly used as activist signal than in US/UK; HKEX market structure has more controlling shareholders. Monitor for stake builds by known activist funds (Oasis, Elliott HK). |
| **HK HKEX** | Privatisation announcement / Rule 3.5 (merger by absorption) | Going-Private | HK Code on Takeovers Rule 3.5 = mandatory general offer triggered by crossing 30% threshold. Privatisation by controlling shareholder is the dominant Going-Private structure in HK. |
| **HK HKEX** | Voluntary general offer / Mandatory general offer | Tender Offers; Going-Private | VGO by a third party = Tender Offers. MGO triggered by crossing 30% = typically Going-Private when acquirer is a controlling shareholder; Acquisitions when acquirer is unaffiliated. |
| **Korea DART** | Large-scale shareholding report (주식대량보유상황보고서, 5% threshold) | Activist Campaigns | Equivalent to SC 13D/13G. Korea has an active domestic activist ecosystem (KCGI, Align Partners, Flashlight). Purpose field distinguishes passive from activist intent. |
| **Korea DART** | Tender offer registration (공개매수신고서) | Tender Offers; Going-Private | Required for acquisitions above thresholds. Structure similar to Japan TOB. |
| **Korea DART** | Business combination report (합병보고서) | Acquisitions | Filed with DART for mergers. Often paired with a shareholder meeting notice. |
| **EU ad-hoc / OAM (Officially Appointed Mechanism)** | Ad-hoc disclosure (MAR Article 17) | Acquisitions; Strategic Reviews; Restructuring | EU Market Abuse Regulation requires immediate disclosure of inside information. German ad-hoc (DGAP/EQS), Italian eMarketstorage, and pan-EU OAM feeds all carry these. Scan for "merger," "takeover," "restructuring," "insolvency" keywords. |
| **EU / Germany** | Major shareholding notification (WpHG §33, 3%/5%/10%... thresholds) | Activist Campaigns | Lower 3% initial threshold than US. Multiple threshold levels create a step-by-step stake-build picture. Filer purpose is disclosed less explicitly than US 13D; activist identity inference from fund name required. |
| **EU / Germany** | Voluntary public takeover offer (WpÜG) | Tender Offers; Going-Private | BaFin-regulated. Offer document = equivalent to SC TO-T. Squeeze-out (§327a AktG) after 95% threshold = definitive Going-Private. |
| **Australia ASX** | Substantial holder notice (Form 603/604/605, 5% threshold) | Activist Campaigns | Equivalent to SC 13D/13G. Low activist frequency vs. US/UK but growing (Tanarra, Sandon, L1 Capital). Purpose disclosure less structured; activist intent inferred from filer history. |
| **Australia ASX** | Bidder's statement (Corporations Act s.636) | Tender Offers; Going-Private | Off-market takeover bid document. Equivalent to SC TO-T. Scheme of arrangement (s.411) is the alternative structure for agreed deals. |
| **Australia ASX** | Target's statement (s.638) | Tender Offers (target response) | Equivalent to SC 14D-9. Board recommendation (accept/reject/wait) disclosed here. |
| **India BSE/NSE** | Offer to acquire shares (SEBI SAST Reg. 13/14, 25% threshold) | Tender Offers; Going-Private | SEBI Substantial Acquisition of Shares and Takeovers Regulations. Open offer triggered at 25% or incremental 5% above 25%. Promoter-group acquisitions above threshold = Going-Private pathway. |

---

### D4. Categories with NO clean filing trigger

The following categories are systematically under-represented or entirely absent from structured regulatory filings. They are detected primarily from press releases, news wires, earnings call transcripts, and IR website announcements — sources that require a separate ingest pipeline from EDGAR/SEDAR/TDnet.

| Category | Why no clean EDGAR form exists | Detection approach |
|---|---|---|
| **Strategic Reviews** | A board resolving to "explore strategic alternatives" has no SEC filing obligation. The announcement is typically a press release issued voluntarily. EDGAR will only contain a subsequent 8-K with Exhibit 99.1 (press release). There is no form type that captures the initiation event. | Monitor 8-K Exhibit 99.1 text for the phrase "strategic alternatives," "strategic review," or "evaluate all options." Newswire (PRN/GlobeNewswire/BusinessWire) ingest catches these faster than EDGAR. Also watch for DEF 14A with an investment banker retention disclosure as a secondary signal. |
| **Capital Returns** | Share buyback programs and special dividends are disclosed via 8-K Item 8.01 press releases or, for buyback authorizations, sometimes 8-K Item 5.02/8.01 — but there is no dedicated form. Dutch-auction self-tenders file SC TO-I (covered above), but open-market buyback authorizations and special dividend declarations have no trigger form. | Parse 8-K Exhibit 99.1 for "buyback," "repurchase program," "special dividend," "return of capital," and dollar amount. Also scan DEF 14A for shareholder vote on buyback authorization. SC TO-I covers the structured tender subset. |
| **Restructuring** | Operational restructurings (plant closures, workforce reductions, segment exits) not involving bankruptcy have no EDGAR filing requirement. Chapter 11 filings trigger 8-K Item 1.03 (covered in D2), but the far more common "out-of-court restructuring" — new financing, covenant waiver, liability management exchange — is disclosed via press release only. | 8-K Item 1.03 = bankruptcy subset. For out-of-court: parse 8-K Item 8.01 and Exhibit 99.1 for "restructuring," "cost reduction," "headcount reduction," "facility closure," "liability management," "exchange offer." S-4 filings for debt exchanges also signal distressed restructurings. |
| **Divestitures** (small / non-material) | Material divestitures (>10% of assets) trigger 8-K Item 2.01 on close and sometimes Item 1.01 on signing. But below the materiality threshold, asset sales are not reportable and will only appear in press releases or quarterly filings. The full Divestitures category in the dataset spans both material and sub-threshold transactions. | 8-K Item 1.01 + Item 2.01 cover material disposals (covered in D2). Sub-threshold: ingest PRN/BusinessWire for "divest," "sell," "dispose of," "agreement to sell [unit/division/asset]." Also scan 10-Q/10-K "subsequent events" notes for smaller transactions. |
| **Deal Terminations** | When an announced deal is terminated, the company typically files an 8-K Item 8.01 with a press release, or sometimes Item 1.02 (termination of a material definitive agreement). There is no dedicated EDGAR form for deal terminations. The terminated SC TO-T or DEFM14A is amended to reflect withdrawal, but the amendment itself does not carry a standardized "terminated" field. | Watch for 8-K Item 1.02 (termination of a material definitive agreement) as the most structured trigger. Also monitor amendments to previously flagged SC TO-T, DEFM14A, or SC 13E-3 for "withdrawal," "terminated," "abandoned," or "mutual agreement to terminate" language. Breakup fee disclosure in Exhibit 99.1 is a confirmatory secondary signal. |
| **Activist Campaigns** (early/informal stage) | The formal activist trigger is SC 13D (covered in D2), but many campaigns begin with private letters, public open letters posted to fund websites, or media coverage before the 5% ownership threshold is crossed. These sub-threshold campaigns have no EDGAR footprint. | For sub-5% activists: ingest newswire and financial news for known activist fund names (Elliott, Starboard, Third Point, Sachem Head, etc.) paired with a target company name. Some activists file 13D immediately at or just above 5%; others accumulate near the threshold before filing. SC 13D/A amendment sequences after initial filing are fully trackable in EDGAR. |
| **Management Changes** (routine) | While 8-K Item 5.02 covers executive departures and appointments, the small Management Changes category in the dataset (11 cases) reflects only those changes that are themselves the special situation — typically forced CEO exits in the context of an activist campaign or scandal. Routine management changes are out of scope. | Flag Item 5.02 filings only when co-occurring with an active SC 13D, a pending strategic review, or a Restructuring situation already in the pipeline. Standalone Item 5.02 = not a special situation. |
| **Other / catch-all** | By definition, the "Other" category (141 cases in dataset) captures situations that do not fit the mature taxonomy. These often include domicile changes, regulatory-driven forced sales, government interventions, and novel structures. No single EDGAR form maps to this bucket. | The "Other" category is best populated by a residual classifier: situations flagged by newswire/press-release ingest that contain special-situation language but do not match any of the D2 form-type rules. Treat as a human-review queue rather than an automated output. |

**Practical implication for classifier architecture:** The EDGAR form-to-category mapping in D2 provides high-precision triggers for approximately 60-65% of the mature US categories by volume (Activist Campaigns, Acquisitions, Tender Offers, Going-Private, Spin-Offs, Rights Offerings, Delistings, Issuer Tenders are all cleanly form-triggered). The remaining 35-40% — led by Strategic Reviews (the second-largest stable category at 399 situations) and a large portion of Restructuring and Divestitures — require a parallel press-release/newswire ingest pipeline with keyword extraction. A production classifier should therefore run two parallel ingestion lanes: (1) EDGAR form-type routing per D2, and (2) a text classifier over 8-K Exhibit 99.1 and newswire feeds for the form-absent categories, with the two lanes merged and de-duplicated by company-date key.

## E. Prose & house style

### Length & Structure

**Measured word counts (all 4,471):**
- Prose summary: **median 88 words** (p25 50, p75 117; min 3, max 267) — the bulk fall ~50–120 words
- Business descriptor: median ~16 words — always a single headline-style sentence

**Mandatory two-part structure:**
1. **HEADLINE** (1 sentence, ~15 words): a scannable business-event descriptor (e.g., "Court-approved Delaware redomicile creates June 11-12 settlement gap")
2. **SUMMARY** (1 paragraph, ~50–120 words, median 88): detailed narrative combining event facts, mechanics, and investment implications

### Summary Skeleton (Ordered Components)

Across all categories, summaries follow a consistent five-element sequence:

1. **Who acted / What was filed** — entity, ticker, event type, date (e.g., "Amaero Ltd (3DA.AX) received Federal Court of Australia approval for share and option schemes of arrangement to re-domicile…")
2. **Exact terms** — stake %, share price, implied equity value, premium %, deal consideration, tick-box dates (closing window, record date, vote date). Stated as declarative fact, never hedged (e.g., "Terms provide for C$9.00 in cash at closing plus one CVR of up to C$0.50 per share")
3. **Board recommendation / advisor** — explicitly named (e.g., "ARC board unanimously recommends the transaction… RBC Dominion Securities Inc. is serving as advisor")
4. **Mechanics & structural notes** — collateral pledges, overhang ownership splits, guarantee exposure, contingent claims, regulatory hurdles, compliance clocks (e.g., "Daol AM has pledged 106,948 shares, representing 2.61% of total outstanding shares, as collateral… this formal management control declaration allows the bloc to push for board influence")
5. **Closing: Why it matters / What to watch / Risk-arb angle** — investment implication, catalyst clarity, spread modeling instruction (e.g., "The July 22 vote provides a hard catalyst for an all-cash take-private where Delaware appraisal rights remain available to dissenting holders")

### Tone

**Neutral-reportorial with restrained analytical judgment.** The digest does not cheerlead or argue thesis; it reports fact and surfaces *the* lever for investors to model.

**Evidence phrase:** "The July 22 vote is a binary catalyst" (comparative: cold, technical, not "blockbuster milestone" or "a major opportunity")

Other tonal markers:
- "This filing is the Japanese equivalent of a US 13D" — matter-of-fact equivalency
- "The agreement includes a $37.5 million company termination fee and is expected to close in the second half of 2026" — serial facts, no commentary
- Rare analytical verb: "signals," "creates," "points to" — all passive observation, never "we believe" or "should"

### Distinctive Habit: Foreign-Filing-to-US-Equivalent Mapping

**Pattern:** When a non-US jurisdiction files a disclosure, summaries explicitly map it to a US analogue to anchor understanding for a US-centric audience.

**Examples:**
- "The filing is the Japanese equivalent of a US 13D with an activist agenda focused on capital returns" (AD Works)
- "This filing is the Japanese equivalent of a US 13D with a public agenda and creates a new activist vector" (Aoyama Zaisan)
- "The filing purpose is declared as 'influence over management control,' the Korean regulatory equivalent of a 13D activist declaration" (Aroot)

**Why it's useful for a classifier:**
- Signals **situational familiarity** — the writer assumes a US-educated readership unfamiliar with Japanese TDnet or Korean DART disclosure rules
- **Reduces friction** for cross-border deal modelers who need instant translation of "what does this filing *mean* for US arbitrage?"
- **Avoids jargon traps** — naming the US equivalent proves the writer understands both systems, not just translating foreign terms robotically
- **Enables one-pass reading** — reader does not need external lookup to classify the situation

### Calibration Guidance for LLM Summary Generation

**Target specifications:**
1. **Length:** 85–110 words per summary paragraph (measure after prose lock-in; hard floor ~70, hard ceiling ~130)
2. **Always include:**
   - Named entity, ticker, jurisdiction, market cap / EV (if available)
   - Exact deal price, share consideration, or implied value; dates (vote, record, close window)
   - Named advisor / board stance (yes/no recommendation required)
   - One structural note (collateral, overhang, guarantee, contingency, regulatory clock)
   - Closing implication sentence: catalyst clarity, spread modeling instruction, or risk angle
3. **Tone to mimic:**
   - Zero first-person voice ("we," "I think")
   - Serial fact statements, not narrative connectives ("and," "then" = OK; "thus," "moreover" = rare)
   - Passive constructions on judgment ("creates," "signals," "points to") — never active persuasion
   - Restrained vocab: "binary," "catalyst," "overhang," "mechanics," "arbitrage" — all measured adjectives, no drama
4. **Foreign-filing requirement:**
   - If the event involves a non-US disclosure or filing type unfamiliar to most US investors (Japanese 13D equivalent, French AMF mandatory offer, Chinese delisting, Korean regulatory declaration), ALWAYS include a parenthetical equivalency clause on first reference
   - Format: "(the [Jurisdiction] regulatory equivalent of a US [Analogue])" or "[Filing Type] — the [Jurisdiction] equivalent of a US 13D"
5. **Headline (HEADLINE field):**
   - 14–18 words
   - One commercial fact (price/stake/vote) + one date or mechanism
   - Never a question; never a "teaser"
   - Examples: "Buys Biocare for $950M cash, adding $90M revenue"; "Court-approved Delaware redomicile creates June 11-12 settlement gap"

### Cadence, publisher & access

- **Publisher:** Clark Square Capital (@specsitsdigest). Disclaimer: *"All information sourced from public filings and disclosures."*
- **Cadence:** weekly, **every Sunday**. The 19 issues span **Feb 8 → Jun 14, 2026**, exactly 7 days apart.
- **Filing→publish lag:** within the same week — each issue is that week's activity (e.g. #9 = "week of Mar 30–Apr 5"). The digest is **days-fresh, not real-time** → our EDGAR-driven build can be near-real-time, a genuine edge.
- **Access tiers:** issues #1–9 free, #10–19 Pro ($149/yr; 14-day trial). #9 is the public sample.
- **Issue layout:** grouped by category; each situation is a scannable card (company · ticker/exchange/sector · category badge · valuation metrics · summary).

| Issue | Date (Sun) | Situations | #Cats | Note |
|--:|---|--:|--:|---|
| 19 | Jun 14 | 366 | 17 | |
| 18 | Jun 7 | 439 | 15 | |
| 17 | May 31 | 311 | 15 | **SPACs added (10)**; 28 countries that week |
| 16 | May 24 | 262 | 14 | |
| 15 | May 17 | 539 | 15 | largest issue |
| 10–14 | Apr 12 – May 10 | 145–161 | 12–14 | |
| 9 | Apr 6 | 255 | — | free sample |
| 8 | Mar 29 | 121 | 14 | |
| 7 | Mar 22 | 85 | 13 | **fine taxonomy begins (6→13 cats)** |
| 1–6 | Feb 8 – Mar 15 | 139–385 | 5–6 | coarse era (M&A / Restructuring / Activist) |

_Per-issue counts corroborate the archive's by-issue distribution (±a few, from multi-category tagging)._

## F. What this means for our build (recommendation)

A US-first special-situations desk is highly feasible on our existing macro-dashboard infrastructure, and it slots naturally next to `engine/ipo_radar.py` / the divergence radar as another event-driven leaf. Recommended phasing:

**Phase 1 — US-only, fully reproducible (the MVP).**
- **Collector:** EDGAR event-form poller over the D2 form set (SC 13D/13D/A, SC TO-T/TO-I, SC 13E-3, SC 14D-9, DEFM14A/PREM14A, DEFC14A/PREC14A, Form 10/15/25, S-4, 424B5, and 8-K Items 1.01/1.02/1.03/2.01/3.01/5.02/8.01 with Exhibit 99.1). Add the D4 second lane: a keyword classifier over 8-K Exhibit 99.1 + newswire for the form-absent categories (Strategic Reviews, Capital Returns, out-of-court Restructuring, Deal Terminations) — without this lane we miss the #2 stable category entirely.
- **Classifier:** deterministic form-type → mature-taxonomy routing per D2, with the legacy_label alias map from B2 baked in.
- **Enrichment:** join our existing fundamentals / 13F / insider / price feeds to fill `mc`, `ev`, `m`, `px`, `sec`/`ind` (we already hold all of these — no new vendor needed).
- **Writer:** exactly ONE batched Haiku/DeepSeek call per situation against the E skeleton (HEADLINE + 85–110-word five-part summary). This is the only LLM cost, and it batches cleanly — consistent with our model-tier-routing standing rule.
- **Surface:** a desk modeled on `engine/ipo_radar.py`, cross-linked into baskets (theme exposure), GEX (single-name event vol), the divergence radar, and emitted to Mastermind as a context lens (events as catalysts, never sizing alone).

**Phase 2 — UK RNS + Canada SEDAR+.** Both are English-language and structurally close to EDGAR (Rule 2.7 / scheme circulars; Early Warning Reports / Plan-of-Arrangement circulars per D3). This adds UK (325) + CA (231) ≈ 556 situations, ~12% of the catalog, at modest marginal cost since the classifier and writer already exist.

**Phase 3 — Japan (EDINET/TDnet).** Japan is **562 situations — the single biggest non-US bloc, larger than UK+CA combined.** This is where the moat is, but it needs Japanese-language ingest + the purpose-code-flip activist detector (the 大量保有 13G→13D analogue). High value, highest build cost; treat as a deliberate investment, not a quick add.

**The integration edge:** unlike a standalone newsletter, a desk wired into baskets/GEX/radar/Mastermind turns each situation into a *modelable catalyst inside an existing position framework* — event spread on a name we already track, theme-basket exposure to a take-private, dealer-gamma context around a tender expiry. That cross-surface value is something a subscription product structurally cannot deliver.

**Open decisions for you:**
1. **Market-cap floor?** They run with none (820 sub-$50M situations, nano-caps included). A floor (say $250M) roughly halves volume and cuts noise/data-quality risk but forfeits the micro-cap special-situations niche. Decision needed before we size the collector.
2. **International scope for v2?** Is the value proposition US-only (then we ship Phase 1 and stop), or is cross-border arbitrage the actual goal (then Phase 3 Japan is the real deliverable and we should plan for the language pipeline up front)?
3. **Cadence — real-time vs weekly digest?** EDGAR supports near-real-time event detection; the source product is a periodic digest (19 issues over ~4 months). Real-time fits our dashboard's daily-build cadence and the Mastermind catalyst use; a weekly digest is cheaper on LLM spend and editorial review.

## G. Open questions / surprises

- **Japan is the #2 country (562, 12.6%) — bigger than UK + Canada combined.** The international book is not an afterthought; it is dominated by a single non-English, non-EDGAR jurisdiction. This is both the moat and the hardest part to clone.
- **The US is a minority (45.1%).** The headline finding: this is fundamentally a multi-jurisdiction product, and an EDGAR-only clone is structurally a different (smaller) product than the source.
- **The taxonomy evolved across issues.** 29 raw labels collapse to ~16 mature categories; early coarse buckets ("M&A / Divestitures" issues 1–6, "Other Situations" issues 1–9) were later split. A clone should adopt the mature schema with a `legacy_label` alias map (B2) rather than trying to re-derive history.
- **No status/stage field.** Deal stage (announced / vote-scheduled / definitive / terminated / completed) lives only inside the headline + prose, not as structured data. If we want spread/lifecycle tracking, we must add a stage field they don't have — a genuine improvement opportunity.
- **Sectors/industries are sparse even in their data** (`sec` 25.6%, `ind` 23.9%). Industry tagging is a known weak spot we can beat by joining our own GICS table.
- **Data-quality leaks.** The `px` field carries native-currency strings (e.g., 'CAD 31.76') and prices appear to have landed in the sector field in some records — evidence of an imperfect automated parse, consistent with the "heavy automation" inference.
- **A $4,500,000M (~$4.5T) market-cap outlier** sits at the top of the distribution — almost certainly a parse artifact (mis-scaled units or a currency/multiplier error), not a real mega-cap special situation. We should add a sanity-bound on `mc` ingestion.
- **The `u` source URL is single-valued and mixed-quality** — primary regulator doc when one exists, else a data-platform citation (tradingview/yahoo/simplywall.st) — which is why the "Other 51%" bucket is so large. A clone should store the regulator filing and the metrics-citation as *separate* fields rather than collapsing both into one `u`.
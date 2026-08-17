# D0R Workstream B — Benchmark reset and workflow matrix

**Status:** research packet. No trials purchased. No proprietary UI, copy, or API copied.  
**Effort split:** GovCon CRM/bidder tools ≤10%. Remainder is investor research workflow, defense-domain intelligence, and defense-investor distribution.  
**Live substrate to beat:** entitled Government Revenue is a 500-row USAspending award-change tape (2026-08-13 cut) with locked Candidate Radar, missing budget graph, and unavailable SAM. It is not an investor desk yet.

## B1. GovTribe ruling

**Verdict: REJECT as north star. ADOPT_JOB only for a short list of procurement-entity distinctions. DEFER capture/CRM/proposal/teaming.**

GovTribe, HigherGov, and Deltek GovWin are built for business-development users whose job is “win the next bid.” Their objects (pursuits, teaming, proposal status, NAICS coverage, opportunity pipelines) are the wrong economic unit for a public-markets product. The Chairman’s review already closed this. D0R does not reopen it.

Keep, as *distinctions* not as a product clone:

| Distinction | Why an investor still needs it | Mastermind today | Upgrade |
|---|---|---|---|
| Notice vs award vs IDV vs order vs modification | A SAM notice is not revenue; a ceiling is not funded backlog; P00032 is a funding action, not a new franchise | Award-change tape exists; SAM rail `unavailable`; IDV artifacts built not entitled-proven | Honest object types on every row |
| First-seen vs action_date | Live IRDM row is a May 12, 2026 obligation first seen Aug 12 (`is_late_discovery`) | Clock exists in JSON; title often hides lateness | Surface both clocks; never call first-seen “official” |
| Recipient legal entity vs listed issuer | UEI → LLC → parent → ticker is the only legal join | defense19-v1 path proven on IRDM | Atlas consumes this; no second graph |

Do not: buy a GovTribe trial for D0R; rebuild capture CRM; count bidder alerts as investor parity; imitate their visual language.

## B2–B5. Workflow matrix

Generic rows (“search”, “AI”, “graphs”) are forbidden. Each row is one complete job.

### Investor research products

| product/source | persona | entry point | exact user job | interaction sequence | data needed | output shape | evidence behavior | persistence/alerts | likely hidden engine | Mastermind current state | Mastermind-native upgrade | verdict | V3 surface/wave |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AlphaSense | long-only PM / analyst | keyword or company | Find every disclosure this quarter that mentions a named program or “fixed-price” and land on the exact sentence | Query → ranked snippets with document date → open native PDF/HTML at highlight → save to workspace | Filings, transcripts, IR decks, licensed broker (if paid) | Cited passage + doc + date + company | Snippet must click through to source page/byte range; “AI answer” without cite is failure | Watchlist + saved search | Lexical + semantic retrieval over licensed corpus; company synsets | Ask Mastermind / CXI reads product artifacts, not a filing index; Earnings/SEC planes exist separately | Route defense questions into the existing filing/transcript owners with program-synonym packs; do not mint an AlphaSense clone | ADOPT_JOB | Command Center search + Company dossier / D4–D6 |
| AlphaSense | analyst | company | Ask “what did management say about Sentinel margin last three calls?” and get dated quotes | Question → quote cards with call date → open transcript | Transcript corpus + speaker tags | Quote + timestamp + call | Each quote has a source URL; null if the word never appears | Optional alert on next call | Transcript chunk index | Quartr-like job belongs to Earnings plane | Consume Earnings/transcript store; defense lobe supplies program vocabulary only | ADAPT | Company Defense Dossier / D4 |
| BamSEC | filing analyst | ticker | Walk 10-K exhibit 21 / backlog footnote / contract-type mix without downloading the whole archive | Ticker → filing list → section nav → table extract | EDGAR + rendered HTML + as-reported tables | Filing tree + table | Table cells retain accession + period | None required | EDGAR crawler + HTML outline | SEC/XBRL owner exists; GovRev does not show backlog footnotes | Dossier “company truth” panel is a view over SEC plane, not a new parser | ADAPT | Company Defense Dossier / D4 |
| BamSEC | forensic | two tickers | Compare this year’s backlog footnote to last year’s same footnote | Two accessions → side-by-side tables | As-reported tables + period | Diff table | Both vintages labeled; no silent restatement mix | None | Table alignment | Not in GovRev | PIT table compare is an Earnings/SEC job; defense supplies which footnote to open | ADAPT | Reporting wave / D4 |
| Quartr | event-driven | earnings calendar | Open the slides and transcript the morning of print and clip the backlog/guidance sentences | Calendar → event → slides + transcript + audio | IR materials + calendar | Event packet | Original IR URL retained | Calendar reminders | IR crawler | Earnings Event Intelligence owner | Defense calendar is a *filter* on that owner (A&D prints, supplementals) | ADAPT | Reporting Wave / D4 |
| Koyfin | PM | ticker vs peers | See consensus sales/EPS revision after a program charge vs sector | Ticker → estimates → revisions → peer tape | Licensed estimates + prices | Sparkline + revision table | Vendor vintage on every number; null if no license | Alerts on estimate moves | FactSet/S&P/Visible Alpha class feed | Estimates live in owner plane or are absent — do not scrape | If licensed, join to defense events; if not, print null | ADAPT / DEFER (license) | Backlog/Revenue/Cash Cockpit / D4 |
| Koyfin | PM | valuation tab | Place LMT vs NOC on EV/EBITDA and FCF yield with the same last-close | Peer set → multiples | Prices + fundamentals | Peer matrix | Close timestamp + source | None | Market-data vendor | Price/valuation owners exist | Defense peer set is archetype-aware (shipyard ≠ sensor) | ADAPT | Company dossier / D4 |
| TIKR | generalist | ticker | Pull 10 years of segment sales and a cap table without Excel | Ticker → financials → segments | Filings + vendor fundamentals | Spreadsheet-like | Period labels; restated vs as-reported toggle | None | Fundamentals vendor | Same as Koyfin | Consume; do not rebuild | ADAPT | Company dossier / D4 |
| Bloomberg/FactSet (publicly described jobs only) | institutional | terminal | Run a custom peer relative return around an FMS notice | Event date → abnormal return vs custom peer | PIT prices + event time | Event study strip | PIT prices only; no revised history masquerading as live | Monitor | PIT price store | Prices/options owned elsewhere | Defense supplies the event; market plane supplies the tape | ADAPT | Dislocation Lab / D3–D7 |

### Defense-domain products

| product/source | persona | entry point | exact user job | interaction sequence | data needed | output shape | evidence behavior | persistence/alerts | likely hidden engine | Mastermind current state | Mastermind-native upgrade | verdict | V3 surface/wave |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Janes | program analyst | platform name | Answer “who is the prime and what is IOC/FOC status of SM-6?” from a curated ontology | Search platform → program card → variants → operators | Licensed Jane’s Fighting Ships / Defence Equipment | Program card | Jane’s as licensed cite, never scraped into public pages | Saved platforms | Human+curated ontology | No program graph; `major_program` null on IRDM award | LICENSE or RESEARCH_ONLY until rights reviewed; D5 program cards may *cite* not ingest | LICENSE / RESEARCH_ONLY | Program dossier / D5 |
| Aviation Week / Fleet Discovery | fleet analyst | aircraft MDS | Count operational F-35A by operator and block | Fleet query → inventory table | Licensed fleet | Installed-base table | Operator + MDS + count + as-of | Fleet watch | Serial/inventory DB | Not built | Same rights gate as Janes; sustainment themes need installed-base, not award dollars | LICENSE / DEFER | Fleet/sustainment theme / D8+ |
| Govini Ark | IB analyst | part or CAGE | Trace a second-tier supplier into a program BOM | Part → BOM → program → primes | Licensed supplier graph | Graph view | Every edge sourced | None | Entity resolution + BOM | Identity Atlas is issuer/legal, not BOM | Do not clone Ark. D8+ supplier edges only where official/licensed | DEFER / REJECT clone | Industrial Bottleneck Atlas / D8 |
| DoD Comptroller P-1/R-1 (official) | budget analyst | PE / line item | See whether a PE requested, authorized, and enacted, then who might produce it | Budget book → PE → request vs enacted → contractor mentions | Official budget PDFs/tables | PE timeline | Official URL + FY | None | PDF/table parse | **PROJECTION_MISSING** live (entitled Budget tab 0) | BUILD official P-1/R-1 graph; this is the highest-leverage missing rail on the current page | ADOPT_JOB | Budget cockpit / D1 then D5 |
| GAO weapons / protests | risk analyst | program or docket | Open the latest Nunn-McCurdy or bid-protest decision and link it to the issuer | Docket → PDF → program → issuer | GAO.gov | Finding card | Docket id + PDF | Alert on new decision | Docket crawler | Not built | BUILD public GAO as adverse-event source | ADOPT_JOB | Dislocation Lab / D8 |
| DSCA FMS (official) | export analyst | country or system | Distinguish “Congressional notification” from “implemented LOA / funded” | Notice list → case → status | DSCA/State | FMS case card | Notification ≠ sale | Watch by country | Official tables | Not built | BUILD with stage labels; never treat 36(b) as revenue | ADOPT_JOB | FMS theme / D5–D6 |

### Defense-investor / sector distribution

| product/source | persona | entry point | exact user job | interaction sequence | data needed | output shape | evidence behavior | persistence/alerts | likely hidden engine | Mastermind current state | Mastermind-native upgrade | verdict | V3 surface/wave |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Industrial Base Alpha / similar sector DBs | specialist fund | theme page | Get a living roster of munitions names with “what changed this week” | Theme → roster → weekly delta | Mix of public + editorial | Roster + delta | Editorial vs official tagged | Newsletter | Human editorial | Theme Intelligence owner exists; defense theme war rooms do not | ADOPT_JOB as *distribution pattern* (theme roster + weekly delta), content must be our artifacts | ADOPT_JOB | Theme War Room / D6 |
| Sixth Domain / defense-tech editorial | growth investor | company | See whether a private name is a vendor on a named program | Article → program mention → company | Journalism | Narrative | Cite article; not a fact store | None | Editorial | Not a source of record | RESEARCH_ONLY; never ingest as graph truth | RESEARCH_ONLY | — |
| Prime IR “book-to-bill / funded backlog” slides | PM | event | Reconcile a DoD award headline with the next backlog bridge | Award event → next print → backlog walk | IR slides + award tape | Divergence card | Both clocks | Alert on print | Manual | Government vs company truth monitor is spec; not live | ADOPT_JOB | Gov vs Company monitor / D4 |
| Sell-side A&D primer (public excerpts only) | generalist | PDF | Learn which names are shipyard vs munitions vs sensor in one sitting | Primer → archetype map | Public primer | Archetype map | Cite; no copy of paid text | None | Human | This taxonomy packet | ADOPT_JOB as architecture, not a content scrape | ADOPT_JOB | Archetype router / D0R→D2 |

## Ruling summary

| Verdict | What it means for D1–D4 |
|---|---|
| ADOPT_JOB | Investor must be able to do this job on Mastermind using *our* owners (GovRev tape, SEC, earnings, prices, official budgets/GAO/FMS). |
| ADAPT | Job exists in another plane; defense adds vocabulary, peer sets, and joins — no second store. |
| LICENSE | Janes/Aviation Week/Govini-class ontologies stay behind a rights review; D0R does not scrape them. |
| DEFER | Supplier BOM graphs, expert networks, licensed estimates until a named license exists. |
| REJECT | GovCon CRM, proposal, teaming, bidder pipeline, and any “defense score.” |

**First three jobs the current entitled page fails and D1 may rescue without new sources:** (1) Candidate Radar rehydrate after site_full 200; (2) honest budget-missing state (typed failure only — not a P-1 collector); (3) stop membership copy on an already-entitled filmstrip. Those are product-rescue, not benchmark clones.

## B6. Reproducible evidence receipts (2026-08-17)

Classification: **OBSERVED** = this session or the entitled 2026-08-17 census hit the live surface. **MARKETING** = vendor public page / commonly described job, not a paid trial. **OFFICIAL** = `.gov` page fetched or API probed. No proprietary UI was copied.

| Row | Date | URL / artifact | Class | What was actually seen | What was not seen |
|---|---|---|---|---|---|
| Live GovRev desk | 2026-08-17T04:39Z | `https://www.mastermind-x.com/government_revenue.html` | OBSERVED | entitled Changes 500; Radar overlay lock; Budget 0; SAM 0 | paid competitor products |
| USAspending transactions API | 2026-08-17 | `https://api.usaspending.gov/api/v2/transactions/` | OFFICIAL | GET returns **405 Method Not Allowed** (POST-only endpoint is live). P00032 previously POSTed in the golden lineage | bulk download completeness |
| DoD Comptroller P-1/R-1 | 2026-08-17 | `https://comptroller.defense.gov/Budget-Materials/` | OFFICIAL | FY2027 War Budget Materials page lists P-1, P-1R, R-1 PDFs | parsed PE graph (ours is missing) |
| SAM.gov | 2026-08-17 | HEAD `latest.json` `freshness.opportunities.status=unavailable` | OBSERVED (our rail) | typed unavailable; 0 records_visible | SAM public search UI this session |
| DSCA 36(b) | — | `https://www.dsca.mil/` (public notices; not fetched this close) | MARKETING/OFFICIAL unverified this close | job exists as Congressional notification | stage≠sale not re-probed 2026-08-17 |
| GAO | — | `https://www.gao.gov/` | OFFICIAL home (not a specific docket this close) | public docket/PDF job | Nunn-McCurdy PDF bytes this close |
| AlphaSense / BamSEC / Quartr / Koyfin / TIKR | — | public marketing sites | MARKETING | investor jobs in B2 are **job descriptions**, not inspected paid UX | any licensed corpus, screenshot, or API |
| Janes / Aviation Week / Govini | — | vendor sites | MARKETING | LICENSE/DEFER stands | paid ontology |
| Bloomberg/FactSet | — | publicly described terminal jobs | MARKETING | event-study job only | any terminal function copied |

**Gate 3 close rule:** GovTribe remains REJECT as north star. Rows above are enough to reproduce the *jobs* and the *live substrate failure*, not to claim we used those products.


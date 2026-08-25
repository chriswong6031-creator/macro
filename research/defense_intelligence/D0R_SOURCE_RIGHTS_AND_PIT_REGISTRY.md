# D0R Workstream E — Source, rights, history, and point-in-time registry

No source is labeled **available** unless this session verified the current public interface or the live GovRev artifact. Licensed vendors are **RESEARCH_ONLY / LICENSE** until a contract exists. Do not scrape ToS-blocked sites.

Prioritization: investor information gain (identity, first-known, program/theme, financial transmission, capacity, adverse, market incorporation, forward eval) — not page parity.

## Registry

| Source | Official page | Owner | Native IDs | Rights / retention | Auth / cost | History / PIT | Cadence / latency | Corrections | Volume / scope | Parser | SLO / failure | V3 unlock | Rec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USAspending awards + transactions | https://api.usaspending.gov | Treasury/DoD reporting | `award_id`, PIID, `action_date`, UEI | Public; retain receipts + sha | none | action_date official; first-seen is ours | monthly completeness; days–weeks lag | new action versions | high US | JSON API | fail → tape stale | award spine | **BUILD** (exists) |
| SAM.gov opportunities | https://sam.gov | GSA | notice id | Public with ToS; no bulk abuse | API key | amendment history if collected | hours–days | amendments | high | JSON | live **unavailable** | notice tape | **BUILD** (fix rail) |
| DoD contract announcements | https://www.defense.gov/News/Contracts/ | OSD PA | date + contractor name | Public news, not a ledger | none | publication date ≠ obligation | daily | rare | low | HTML | miss ≠ no award | press join | **ADAPT** join-only |
| DoD Comptroller P-1/R-1 | https://comptroller.war.gov (host migrated 2026-08-24 census: comptroller.defense.gov now 403s, no redirect — DSC:DOD-COMPTROLLER-HOST-MIGRATED-TO-WAR-GOV) | OSD | PE, BA, FY | Public PDFs | none | FY vintage | annual + supp | errata | medium | PDF/table | live **missing graph** | budget graph | **BUILD** (D6-A in flight) |
| Appropriations / NDAA / supp | congress.gov | Congress | bill, PL | Public | none | enacted date | event | amendments | medium | HTML | CR = delay state | funding durability | **BUILD** |
| IDVs/orders/subawards | USAspending | Treasury | parent_award, subaward_id | Public | none | action dates | monthly | new rows | high | JSON | HEAD artifacts unproven live | vehicle graph | **ADAPT** existing |
| DLA/DIBBS | DLA | DLA | NSN | Public operational | none | order dates | intra-day | n/a | high | HTML | noisy | bottleneck | **DEFER** |
| SBIR/STTR | sbir.gov | SBA/DoD | award id | Public | none | award year | monthly | n/a | medium | CSV | module dark | theme | **DEFER** (dark code) |
| DIU/AFWERX/OTA | diu.mil / announcements | services | notice | Public PR | none | pub date | event | n/a | low | HTML | prototype≠P&P | autonomy | **RESEARCH_ONLY** |
| GAO weapons / bid protest | gao.gov | GAO | docket, report no. | Public | none | release date | event | revisions | medium | PDF | must cite PDF | adverse | **BUILD** |
| DOT&E annual | dote.osd.mil | DOT&E | program | Public PDF | none | FY | annual | n/a | low | PDF | lag | test risk | **BUILD** |
| DoD/service IG | dodig.mil | IG | report | Public | none | release | event | n/a | low | PDF | | adverse | **ADAPT** |
| CRS | crsreports.congress.gov | CRS | R-number | Public | none | date | event | updates | low | PDF | | primer | **RESEARCH_ONLY** |
| Nunn-McCurdy / SAR | various DoD | OSD A&S | program | Partial public | none | FY | annual | restated | low | PDF | incomplete | program risk | **ADAPT** |
| DSCA 36(b) FMS | dsca.mil | DSCA/State | transmittal | Public | none | notification date | event | not a sale | medium | HTML | stage labels required | export | **BUILD** |
| NATO / SIPRI spend | nato.int / sipri.org | NATO/SIPRI | country-year | Public stats | none | year | annual | revisions | low | tables | not a price | NATO theme | **RESEARCH_ONLY** |
| Allied budgets | national MoD | states | FY | Public, language | none | FY | annual | | medium | PDF | FX | archetype 11 | **ADAPT** per country |
| Export control / OFAC | state/treasury | USG | license/entity | Public lists | none | list date | event | additions | low | HTML | | structural legal | **ADAPT** |
| Janes | janes.com | Jane’s | platform | **Licensed** | paid | vendor vintage | vendor | vendor | high | API | no scrape | program ontology | **LICENSE** |
| Aviation Week Fleet | aviationweek.com | Informa | MDS/serial | **Licensed** | paid | vendor | vendor | vendor | high | API | no scrape | fleet | **LICENSE** |
| Govini Ark | govini.com | Govini | CAGE/part | **Licensed** | paid | vendor | vendor | vendor | high | API | no scrape | BOM | **DEFER** |
| SEC EDGAR/XBRL | sec.gov | SEC | accession | Public | none | accepted_at | intra-day | restatements | high | existing plane | **do not fork** | company truth | **ADAPT** |
| Earnings/slides/transcripts | IR + existing plane | company | event_id | Public IR | none | event time | event | corrigenda | medium | existing | **do not fork** | divergence | **ADAPT** |
| Estimates | vendor | vendor | period | **Licensed** | paid | vendor PIT or none | daily | revisions | medium | vendor | null if unlicensed | cockpit | **LICENSE / DEFER** |
| Prices / options / GEX | existing owners | market | ticker, session | licensed/internal | internal | PIT only if store says so | session | corporate actions | high | existing | **do not fork** | dislocation | **ADAPT** |
| Identity / 13F / insider | existing | SEC | CUSIP | Public | none | filing date | quarterly | amendments | high | existing | | crowding | **ADAPT** |
| Job postings | vendors / public | various | site | ToS | paid/free | post date | daily | deletions | high | vendor | noisy | capacity | **DEFER** |
| Imagery/logistics | vendors | vendors | AOI | **Licensed / sensitive** | paid | capture time | daily | n/a | high | vendor | rights+OPSEC | bottleneck | **REJECT** unless licensed |
| Patents | USPTO | USPTO | patent no. | Public | none | grant date | weekly | n/a | high | XML | weak cash-flow | research | **DEFER** |
| Lobbying | LDA / OpenSecrets | Senate | registrant | Public | none | filing | quarterly | n/a | medium | XML | context only | durability | **RESEARCH_ONLY** |
| Media / GPR | vendors | vendors | — | licensed | paid | stamp | intra-day | n/a | high | NLP | attention not cash | attention | **DEFER** |

## Launch order (information gain)

1. USAspending action spine (already live; entitled 500 proven).  
2. Honest SAM rail or keep `SOURCE_UNAVAILABLE`.  
3. Official P-1/R-1 graph (page is broken without it).  
4. DSCA FMS stages.  
5. GAO/DOT&E adverse packets.  
6. Joins to SEC/earnings/prices — never copies.  
7. Licensed ontologies only after a named contract.

## Failure behavior (product)

Print the typed state already used in A: `CURRENT` / `PARTIAL` / `STALE` / `EMPTY_VALID` / `SOURCE_UNAVAILABLE` / `PROJECTION_MISSING` / `SIGN_IN_REQUIRED` / `RIGHTS_BLOCKED`. Never coerce 0+unavailable into empty-valid.

## E2. Verification receipts (this close)

`verified_at` = 2026-08-17 unless noted. “Public; retain receipts” is not enough — each BUILD row now names the interface actually probed.

| Source | verified_at | Interface probed | Auth / limits observed | History / PIT | Corrections | Rights |
|---|---|---|---|---|---|---|
| USAspending transactions | 2026-08-17 | GET `https://api.usaspending.gov/api/v2/transactions/` → **405** (POST-only). Prior D0R POST for award `306425727` returned P00032. | none; public JSON; rate unknown this close | `action_date` official; our `known_at` is collector | new action ids / versions; do not overwrite receipts | Public API ToS; we retain sha + receipt id |
| USAspending award page | lineage | award `CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-` / numeric 306425727 | none | action_date 2026-05-12 | P00032 vs balance-changed sibling both kept | Public |
| SAM.gov | 2026-08-17 | **Our** `latest.json` `freshness.opportunities.status=unavailable`, `records_visible=0`, `observed_at=null` | live product: SOURCE_UNAVAILABLE | amendment history **not** collected | n/a | Public SAM exists; **our rail is down** — do not claim SAM access |
| DoD Comptroller P-1/R-1 | 2026-08-17 | GET `https://comptroller.defense.gov/Budget-Materials/` 200; FY2027 P-1 and R-1 listed | none | FY vintage on the exhibit | errata via replacement PDFs | Public. **Our graph absent** = PROJECTION_MISSING |
| DoD Comptroller P-1/R-1 (re-census) | 2026-08-24 | `comptroller.defense.gov` now **403** (AkamaiGHost, no redirect); live host `comptroller.war.gov` serves Budget-Materials + FY2027 exhibits: `FY2027_p1.pdf` 200 (2,796,050 B, sha256 `b8d52482…d0a6`), `FY2027_r1.pdf` 200 (3,127,023 B, sha256 `1aa8846e…7882a`), last-modified 2026-04-03. Documents self-identify publisher as "Office of the Under Secretary of War (Comptroller)" | none | FY2027 President's Budget is the current cycle | errata via replacement PDFs (none visible for FY2027 P-1/R-1 at census) | Public. D6-A activation in flight (PR #6377); DSC:DOD-COMPTROLLER-HOST-MIGRATED-TO-WAR-GOV |
| SEC EDGAR | 2026-08-17 | Boeing 8-K `ba-20251208.htm` (CIK 12927); Spirit 8-K `tm2532915d1_8k.htm` (CIK 1364885) — acquisition completed 2025-12-08 | none | `accepted` / Date of Report | 8-K is a point filing | Public. Consume via SEC owner |
| DSCA 36(b) | not re-fetched this close | registry URL only | — | notification date ≠ LOA | — | **UNVERIFIED this close** — keep BUILD intent, do not claim current HTML schema |
| GAO | not a specific docket this close | gao.gov | — | release date | revisions | **UNVERIFIED docket** this close |
| Janes / Aviation Week / Govini / estimates | — | not inspected | paid | vendor vintage | vendor | **LICENSE / not available** |

Auth for **our** paid APIs (not the government sources): cookie JSON `government-revenue-data/{workspace,latest,candidates}.json` 200 after `site_full`; cookie-only `/api/government-revenue/*` **401 missing bearer**; bearer from `MDXAuth` unlocks the same APIs. Limits: workspace 500-cap; candidates `limit` paging (`MAX_PAGES=4` in `government-revenue-candidate-radar.js`).

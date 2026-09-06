# MARKET ONTOLOGY — Half-B rights, source and upstream-gate docket (2026-09-06)

## 0. Header

- **Operation:** Market Ontology Half-B, wave B3, packet B-F09-7.
- **Record type:** records-only; no product/runtime effect.
- **Row denominators:** 20 packet rows = 20/130 = 15.4% of the F00C ledger. 18 of the 20 are family F09-CAPITAL-MATERIALS = 18/29 = 62.1% of F09 rows. 2 of the 20 (MO-PAID-035, MO-PAID-037) are family F07-VALUATION-SCENARIO = 2/5 = 40% of F07 rows. This packet covers 5 of the ledger's 7 BLOCKED_RIGHTS rows (MO-DELTA-020, MO-PAID-061, MO-DELTA-028, MO-DELTA-030, MO-PAID-041); the other 2 BLOCKED_RIGHTS rows are outside this packet's row list (see §7).
- **Method:** read-only inspection of the F00C ledger + named engine modules; no crawl, no new source.
- **Authority note:** this docket commissions nothing. It records a terminal disposition and a gate. No line in it schedules, budgets or authorises a build.

## 1. Terminal disposition

All twenty rows listed in this docket are recorded `DOCKETED_TERMINAL_HALF_B` in the F00C ledger's `next_bounded_child` column. No engineering wave in Half-B, or any wave after it, may open these rows on its own initiative: each is blocked on a named party outside engineering — a Chairman/commercial contract decision (gate family A, 15 rows), an upstream internal owner review by the K1 Evidence Foundation owner (gate family B, 3 rows), or an upstream acceptance decision already standing at the K2-C carrier, PR #6498 (gate family C, 2 rows). Four rows (MO-DELTA-026, MO-DELTA-030, MO-PAID-041, MO-PAID-030) carry a compound gate across two of these families and are recorded once, under their primary family, with the second gate named in the row body.

## 2. Gate family A — commercial rights (party: Chairman / commercial contract authority)

15 rows are blocked on a licensed commercial data source or a sovereign/rating licensing decision that only the Chairman or a delegated commercial contract authority can open.

### MO-DELTA-020
- **Blocked on (verbatim from the ledger):** `licensed deal-flow feed (pair)` + `licensed deal-flow data required, none under contract`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `context_only`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one issuer's deal record as context on the existing capital-structure page; no scoring.

### MO-PAID-061
- **Blocked on (verbatim from the ledger):** `licensed deal-flow feed (Dealogic/Refinitiv-class)`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `context_only`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: bookrunner/coupon/tenor/greenshoe columns for ONE issuer in scripts/compile_capital_structure_events.py, correction chain preserved.

### MO-DELTA-024
- **Blocked on (verbatim from the ledger):** `ECM depth (pair)` + `IPO pricing history not sourced`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `research_only`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one IPO's pricing path as depth, reusing ipo_radar.aftermarket_basket() as a primitive.

### MO-PAID-065
- **Blocked on (verbatim from the ledger):** `pricing-precedent/float/lockup/greenshoe/aftermarket product + per-deal pricing-history source`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `research_only`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one IPO shows lockup/greenshoe terms + aftermarket path (the row's own acceptance_test).

### MO-DELTA-025
- **Blocked on (verbatim from the ledger):** `comparison depth (pair)` + `bond-terms coverage extent UNVERIFIED`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `display-only context (assumed)` -- the word "assumed" is carried forward; the ceiling is itself unverified
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one issuer vs peer set comparison, display-only.
- **Row-accounting repair (charter 10.3), also written into the ledger col 14:** ROW-ACCOUNTING REPAIR (charter 10.3): the available quantity is ETF-held par, not issuer debt outstanding, and must never be summed with issuer debt outstanding; the theme registry is a theme/name matcher, not a canonical issuer join

### MO-PAID-066
- **Blocked on (verbatim from the ledger):** `per-issuer bond-terms data source, then a comparison layer`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `display-only context (assumed)`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one issuer's bond shows coupon/spread/tenor vs peer set; keep-FIRST append to data/corp_bonds/forward_log.jsonl preserved.
- **Row-accounting repair (charter 10.3), also written into the ledger col 14:** ROW-ACCOUNTING REPAIR (charter 10.3): the available quantity is ETF-held par, not issuer debt outstanding, and must never be summed with issuer debt outstanding; the theme registry is a theme/name matcher, not a canonical issuer join

### MO-DELTA-026
- **Blocked on (verbatim from the ledger):** `rating-agency licensing + ingestion source; K1 store`
- **Who can open it:** Chairman / commercial contract authority (rating licensing) AND K1 Evidence Foundation owner (store)
- **Authority ceiling if it opens (verbatim):** `evidence_navigation_only`
- **First bounded slice on the day it opens:** ON BOTH GATES OPEN: one rating action navigable as evidence, never as a score.

### MO-DELTA-027
- **Blocked on (verbatim from the ledger):** `Material Flow Map (pair)`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `context_only`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one commodity's layer map as context.

### MO-PAID-040
- **Blocked on (verbatim from the ledger):** `cross-layer decomposition (raw->chokepoint->refining->fabrication->distribution->end-market) and its data source`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `display-only LEAF, never feeds scoring`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one commodity documents a >=3-layer sourced chain.

### MO-DELTA-028
- **Blocked on (verbatim from the ledger):** `entire chokepoint monitoring; AIS-class licensed data`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `context_only if built`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one chokepoint's transit context; no causal claim.

### MO-DELTA-030
- **Blocked on (verbatim from the ledger):** `physical-vs-financial signals (pair)`
- **Who can open it:** Chairman / commercial contract authority, THEN Evaluation OS gauntlet
- **Authority ceiling if it opens (verbatim):** `research_only; no promotion path until Eval OS gauntlet`
- **First bounded slice on the day it opens:** ON BOTH GATES: research-only display. Carries no signal authority absent prospective validation.

### MO-PAID-041
- **Blocked on (verbatim from the ledger):** `physical-vs-financial materials signal; physical-flow data unlicensed`
- **Who can open it:** Chairman / commercial contract authority, THEN Evaluation OS gauntlet
- **Authority ceiling if it opens (verbatim):** `research_only; F09 do_not_redo: no physical-financial arbitrage signal authority absent prospective validation`
- **First bounded slice on the day it opens:** ON BOTH GATES: research-only display. Carries no signal authority absent prospective validation.

### MO-PAID-030
- **Blocked on (verbatim from the ledger):** `sovereign-entity master + institutional->sovereign classification; K2-C acceptance precondition`
- **Who can open it:** Chairman / commercial contract authority (sovereign source) AND K2-C carrier
- **Authority ceiling if it opens (verbatim):** `pre-authority`
- **First bounded slice on the day it opens:** ON BOTH GATES: >=1 sovereign fund mapped to holdings via a named lawful source, as a classification read over accepted K2-C output -- never a sovereign entity master (F09 do_not_redo).

### MO-PAID-035
- **Blocked on (verbatim from the ledger):** `consensus-estimate source (verified negative) + production issuer service`
- **Who can open it:** Chairman / commercial contract authority (consensus licensing)
- **Authority ceiling if it opens (verbatim):** `research_display_only; FIF do_not_redo bars second financial-truth store`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: DCF/comps over ONE non-fixture issuer with rights-cleared consensus input.

### MO-PAID-037
- **Blocked on (verbatim from the ledger):** `triple dependency 022+026+035`
- **Who can open it:** closes only after MO-DELTA-022, MO-DELTA-026 and MO-PAID-035 open
- **Authority ceiling if it opens (verbatim):** `research_display_only`
- **First bounded slice on the day it opens:** NONE. No independent slice exists; this row cannot be sliced before its three dependencies.


## 3. Gate family B — upstream internal owner review (party: K1 Evidence Foundation owner, physical-store review)

3 rows are blocked on the K1 Evidence Foundation owner's physical-store review, which is frozen pending a fresh review and is not this packet's decision to resolve.

### MO-PAID-069
- **Blocked on (verbatim from the ledger):** `K1 physical store + a Source Library UI reading it`
- **Who can open it:** K1 Evidence Foundation owner
- **Authority ceiling if it opens (verbatim):** `evidence_navigation_only, no truth-store authority by design`
- **First bounded slice on the day it opens:** ON GATE OPEN: one filing browsable through a resolved K1 store.

### MO-PAID-019
- **Blocked on (verbatim from the ledger):** `unified capital-markets tape journey joining event/term/registration/share-count streams`
- **Who can open it:** K1 Evidence Foundation owner (physical-store review)
- **Authority ceiling if it opens (verbatim):** `display-only/context; no alpha/trade authority`
- **First bounded slice on the day it opens:** ON GATE OPEN: one issuer page shows >=2 module streams with visible correction lineage.
- **Row-accounting repair (charter 10.3), also written into the ledger col 14:** ROW-ACCOUNTING REPAIR (charter 10.3): capital-structure identity is cusip6/isin/name prefix-then-name first-registry-match; it is not a canonical issuer join

### MO-PAID-029
- **Blocked on (verbatim from the ledger):** `K1 Evidence Foundation physical store: frozen at INTEGRATED AUTHENTICATED-RIDER CANDIDATE / PHYSICAL STORE REFUSED / FRESH REVIEW PENDING (K1 freeze doc L3)`
- **Who can open it:** K1 Evidence Foundation owner
- **Authority ceiling if it opens (verbatim):** `display-only, hold_thesis`
- **First bounded slice on the day it opens:** ON GATE OPEN: a cap-table surface reads >=1 EvidenceBlock.
- **Row-accounting repair (charter 10.3), also written into the ledger col 14:** ROW-ACCOUNTING REPAIR (charter 10.3): capital-structure identity is cusip6/isin/name prefix-then-name first-registry-match; it is not a canonical issuer join


## 4. Gate family C — upstream acceptance (party: the standing K2-C carrier, PR #6498 — acceptance only; never recommission K2-C or K3-D/PR #6533)

2 rows are blocked on the standing K2-C carrier's acceptance decision. This docket does not recommission K2-C or K3-D; it only records that these two rows open on K2-C's acceptance, whenever that lands.

### MO-DELTA-022
- **Blocked on (verbatim from the ledger):** `valuation-bridge depth (pair)`
- **Who can open it:** K2-C carrier (PR #6498) acceptance
- **Authority ceiling if it opens (verbatim):** `research_display_only`
- **First bounded slice on the day it opens:** ON GATE OPEN: one issuer's ownership-to-capital bridge as depth on an existing page.

### MO-PAID-063
- **Blocked on (verbatim from the ledger):** `valuation bridge; compound dependency: K2-C acceptance + capital-structure facts`
- **Who can open it:** K2-C carrier + capital-structure owner
- **Authority ceiling if it opens (verbatim):** `research_display_only`
- **First bounded slice on the day it opens:** ON GATE OPEN: one issuer bridge reading accepted K2-C output; no new store.


## 5. What a customer can see today vs what stays absent — plain words, EN + ZH

**Family A (commercial rights) — EN:** Today you can see the public filing record for these companies and the market prices around them. What we do not show is the private deal terms and shipment tracking that sit behind paid data agreements we have not signed — so those sections stay empty rather than estimated.

**Family A — ZH:** 目前你可以看到这些公司的公开申报记录，以及围绕它们的市场价格。我们没有展示的是需要付费数据协议才能取得的私下交易条款与货运追踪；这些协议我们尚未签署，因此相关部分留空，而不是用推估值填补。

**Family B (upstream owner review) — EN:** Today you can open the underlying documents one at a time from the pages that cite them. What is not ready is a single library where every document, and each correction to it, can be browsed in one place — that library is still under review, so we do not claim it exists.

**Family B — ZH:** 目前你可以从引用文件的页面逐份打开原始文件。尚未就绪的是一个可以在同一处浏览所有文件及其每一次更正的资料库；该资料库仍在审议中，因此我们不会声称它已经存在。

**Family C (upstream acceptance) — EN:** Today you can see who is reported to own a company through public ownership filings. What we do not yet show is how those owners connect to a company's full capital picture, because the step that links them has not been accepted yet.

**Family C — ZH:** 目前你可以透过公开的持股申报，看到谁被报告为公司的持有人。我们尚未展示的是这些持有人如何与公司的完整资本结构相连，因为串接这一步尚未获得接受。

This copy is prescriptive text for a future surface. This packet ships no surface, so no page, nav entry or theme treatment is created here; the consuming packet owes the dark and light art directions and the EN/ZH x 1440/390 evidence matrix.


## 6. Row-accounting repair (charter 10.3)

Four F09 rows in the ledger (MO-DELTA-025, MO-PAID-066, MO-PAID-019, MO-PAID-029) carry a row-accounting repair, written verbatim into their `adjudication_notes` column in this packet:

- **MO-DELTA-025 / MO-PAID-066:** "ROW-ACCOUNTING REPAIR (charter 10.3): the available quantity is ETF-held par, not issuer debt outstanding, and must never be summed with issuer debt outstanding; the theme registry is a theme/name matcher, not a canonical issuer join." Evidence: `engine/credit_momentum.py:1406-1427` — the ETF holdings frame's only quantity is `par_value`, summed per fund into `"par": grp["par_value"].sum()`; that is held par, and nothing in the module reads issuer debt outstanding. `engine/credit_momentum.py:278-285` — `_load_issuer_registry` loads `data/corp_bonds/issuer_themes.json` and returns `{"themes": {}}` on failure — a theme registry, not an issuer join. `engine/credit_momentum.py:1-3` — module docstring: DISPLAY-TIER / NOT VALIDATED, authority all-false, accruing forward. `agentos/handoffs/MARKET-ONTOLOGY-F00-CONTINUITY-PRINCIPAL-RECONCILIATION-2026-09-05.md:303-305` — identity = cusip6/isin/name, prefix-then-name, first registry match; population = ETF-held par, not issuer outstanding.
- **MO-PAID-019 / MO-PAID-029:** "ROW-ACCOUNTING REPAIR (charter 10.3): capital-structure identity is cusip6/isin/name prefix-then-name first-registry-match; it is not a canonical issuer join." Evidence: `agentos/handoffs/MARKET-ONTOLOGY-F00-META-CEO-CONTINUITY-PRODUCT-RESET-2026-09-05.md:333-334` — the charter 10.3 sentence itself.

Plainly: held par is labelled held par and is never summed with issuer debt outstanding; theme/name matching is never described as a canonical issuer join.

## 7. What this docket does NOT cover

- The 2 remaining ledger `BLOCKED_RIGHTS` rows outside this packet's row list are not touched here.
- Any public substitute for a licensed source: if a future session finds one, it is added here as a one-line proposal to open a gate — never as a build, never as a schedule, against any of the twenty rows above.

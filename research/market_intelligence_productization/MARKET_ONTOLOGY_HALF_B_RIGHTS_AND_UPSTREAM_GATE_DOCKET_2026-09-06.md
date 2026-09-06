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
- **Blocked on (verbatim from the ledger):** `rating-agency licensing + ingestion source; K1 store` + `rating-agency (Moody's/S&P) licensing not confirmed (UNVERIFIED)`
- **Who can open it:** Chairman / commercial contract authority (rating licensing) AND K1 Evidence Foundation owner (store)
- **Authority ceiling if it opens (verbatim):** `evidence_navigation_only`
- **First bounded slice on the day it opens:** ON BOTH GATES OPEN: one rating action navigable as evidence, never as a score.

### MO-DELTA-027
- **Blocked on (verbatim from the ledger):** `Material Flow Map (pair)` + `cross-commodity/cross-layer physical-flow source not identified (UNVERIFIED)`
- **Who can open it:** Chairman / commercial contract authority
- **Authority ceiling if it opens (verbatim):** `context_only`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: one commodity's layer map as context.

### MO-PAID-040
- **Blocked on (verbatim from the ledger):** `cross-layer decomposition (raw->chokepoint->refining->fabrication->distribution->end-market) and its data source` + `EIA public covered for oil; metals/ag/semis supply-chain source UNVERIFIED`
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
- **Blocked on (verbatim from the ledger):** `sovereign-entity master + institutional->sovereign classification; K2-C acceptance precondition` + `SWFs mostly do NOT file 13F; no licensed sovereign-ownership source in repo (UNVERIFIED whether any contract exists)`
- **Who can open it:** Chairman / commercial contract authority (sovereign source) AND K2-C carrier
- **Authority ceiling if it opens (verbatim):** `pre-authority`
- **First bounded slice on the day it opens:** ON BOTH GATES: >=1 sovereign fund mapped to holdings via a named lawful source, as a classification read over accepted K2-C output -- never a sovereign entity master (F09 do_not_redo).

### MO-PAID-035
- **Blocked on (verbatim from the ledger):** `consensus-estimate source (verified negative) + production issuer service`
- **Who can open it:** Chairman / commercial contract authority (consensus licensing)
- **Authority ceiling if it opens (verbatim):** `research_display_only; FIF do_not_redo bars second financial-truth store`
- **First bounded slice on the day it opens:** ON GATE OPEN ONLY: DCF/comps over ONE non-fixture issuer with rights-cleared consensus input.
- **Valuation-source ruling:** DEC:F07-VALUATION-SOURCE-IS-SEC-COMPANYFACTS-V1 (lands with macro#6903) rules that V1 valuation may use only SEC companyfacts reported fundamentals as input; no consensus estimate, price target or analyst rating is used or displayed until a licensed consensus source is contracted, which is exactly the gate this row records. Code fact, checkable today: `engine/stock_fundamentals.py:1815` — the module's own comment states consensus ratings and price targets remain unwired.

### MO-PAID-037
- **Blocked on (verbatim from the ledger):** `triple dependency 022+026+035`
- **Who can open it:** Chairman / commercial contract authority, via its own dependency chain -- closes only after MO-PAID-022, MO-PAID-026 and MO-PAID-035 open (all F07-VALUATION-SCENARIO; not the F09 rows of the same numeric suffix, which this docket files separately under gate families C and A)
- **Authority ceiling if it opens (verbatim):** `research_display_only`
- **First bounded slice on the day it opens:** NONE. No independent slice exists; this row cannot be sliced before its three dependencies.
- **Valuation-source ruling:** same DEC:F07-VALUATION-SOURCE-IS-SEC-COMPANYFACTS-V1 (lands with macro#6903) governs this row's own dependency MO-PAID-035; the same code fact, `engine/stock_fundamentals.py:1815`, is why a rights-cleared consensus source is still absent today.


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


**Family A -- row by row (EN):**
1. Private placement/deal-flow record for one type of new-issue deal: today, only the public filing; absent, the bookrunner-level deal record.
2. Bookrunner, coupon, tenor and greenshoe detail on new-issue deals: today, the headline terms already public; absent, the underwriter-desk detail.
3. Depth on one company's IPO pricing path: today, the public IPO announcement; absent, the full pricing-history path.
4. Float, lock-up, greenshoe and aftermarket detail on one deal: today, the listing price; absent, the deal's full pricing precedent.
5. Comparing one bond's terms against its peers: today, aggregate fund-level exposure; absent, a per-issuer bond-terms comparison.
6. The underlying per-issuer bond-terms source itself: today, the same aggregate exposure view; absent, per-bond coupon/spread/tenor detail.
7. A rating action shown as evidence: today, nothing rating-specific; absent, the rating action itself (this row also needs an internal library review before it can open).
8. One commodity's full flow map: today, price and signal context; absent, the map from raw material to end market.
9. A multi-step chain for metals, agriculture or semiconductors: today, that chain for oil only; absent, the same depth for the other commodities.
10. Vessel-transit monitoring at one chokepoint: today, nothing; absent, the transit context itself.
11. Any physical-versus-financial materials signal: today, nothing; absent, the signal, and even once it exists it stays research-only until independently tested.
12. The same physical-versus-financial signal at the materials level: today, nothing; absent, the signal, with the same never-a-trading-signal-until-tested limit.
13. A sovereign fund mapped to its holdings: today, public ownership filings where they exist; absent, the sovereign classification layer (this row also needs an internal acceptance step before it can open).
14. Analyst-style valuation built on real estimates: today, the filed financial statements; absent, the estimate figures a valuation needs.
15. Bull/base/bear scenarios over a real valuation: today, nothing; absent, the scenario view, which cannot exist before the three items above land.


**Family A --- 逐行说明（ZH）：**
1. 一类新发行交易的私下交易记录：目前只有公开申报；缺少的是承销商层级的交易记录。
2. 新发行交易的承销商、票息、期限与超额配售细节：目前已有公开的主要条款；缺少的是承销台账层面的细节。
3. 一家公司IPO定价路径的深度信息：目前有公开的IPO公告；缺少的是完整的定价历程。
4. 一笔交易的流通量、锁定期、超额配售与上市后表现细节：目前有上市价格；缺少的是该交易的完整定价先例。
5. 将一只债券条款与同类比较：目前只有基金层面的汇总持仓；缺少的是逐发行人债券条款比较。
6. 逐发行人债券条款数据源本身：目前是同样的汇总持仓视图；缺少的是逐笔票息/利差/期限细节。
7. 作为证据展示的一次评级行动：目前没有任何与评级相关的内容；缺少的是评级行动本身（此行还需先完成一项内部资料库审查才能开启）。
8. 一种商品的完整流向图：目前有价格与信号背景；缺少的是从原材料到终端市场的完整地图。
9. 金属、农产品或半导体的多层级链条：目前只有原油具备这一深度；缺少的是其他商品的同等深度。
10. 一个关键航运节点的船舶通行监测：目前没有；缺少的是通行背景本身。
11. 任何物理与金融对比信号：目前没有；缺少的是该信号，而且即便建成也要等独立检验后才不再只是研究用途。
12. 同一层面在原材料上的物理与金融对比信号：目前没有；缺少的是该信号，同样在检验前绝不作为交易信号。
13. 将一家主权基金对应到其持仓：目前有已申报的公开持股信息（若存在）；缺少的是主权基金分类层（此行还需先完成一项内部接受步骤才能开启）。
14. 建立在真实预估之上的分析师式估值：目前有已申报的财务报表；缺少的是估值所需的预估数字。
15. 基于真实估值的乐观/基准/悲观情景：目前没有；缺少的是情景视图，且必须等以上三项先落地才能存在。


**Family B -- row by row (EN):**
16. Every document and its corrections browsable in one place: today, documents open one at a time from the pages that cite them; absent, the single library view.
17. One issuer page joining two or more data streams: today, single-stream views only; absent, the joined page with visible correction lineage.
18. A cap-table view backed by a reviewed evidence record: today, nothing; absent, the reviewed record itself.

**Family C -- row by row (EN):**
19. How a reported owner connects to a company's full capital picture: today, who is reported to own shares through public filings; absent, the connection step.
20. A full ownership-to-valuation bridge for one company: today, the same public ownership view; absent, the bridge that turns it into a valuation read.


**Family B --- 逐行说明（ZH）：**
16. 所有文件及其更正可在同一处浏览：目前文件需从引用它们的页面逐份打开；缺少的是统一的资料库视图。
17. 一个发行人页面串联两条或以上数据流：目前只有单一数据流视图；缺少的是带有可见更正脉络的合并页面。
18. 由经审议证据支持的资本结构表视图：目前没有；缺少的是经审议的证据记录本身。

**Family C --- 逐行说明（ZH）：**
19. 已申报的持有人如何与公司完整资本结构相连：目前有透过公开申报得知的持股人身份；缺少的是连接这一步。
20. 一家公司完整的持股到估值链路：目前有同样的公开持股视图；缺少的是把它转化为估值判读的桥梁。


This copy is prescriptive text for a future surface. This packet ships no surface, so no page, nav entry or theme treatment is created here; the consuming packet owes the dark and light art directions and the EN/ZH x 1440/390 evidence matrix.


## 6. Row-accounting repair (charter 10.3)

Four F09 rows in the ledger (MO-DELTA-025, MO-PAID-066, MO-PAID-019, MO-PAID-029) each carry two additions to their `adjudication_notes` column: the charter 10.3 repair text quoted below, written verbatim, and -- appended after it -- a separate plain-language repair statement (paraphrased, not verbatim) added in this round:

- **MO-DELTA-025 / MO-PAID-066:** "ROW-ACCOUNTING REPAIR (charter 10.3): the available quantity is ETF-held par, not issuer debt outstanding, and must never be summed with issuer debt outstanding; the theme registry is a theme/name matcher, not a canonical issuer join." Evidence: `engine/credit_momentum.py:1406-1427` — the ETF holdings frame's only quantity is `par_value`, summed per fund into `"par": grp["par_value"].sum()`; that is held par, and nothing in the module reads issuer debt outstanding. `engine/credit_momentum.py:278-285` — `_load_issuer_registry` loads `data/corp_bonds/issuer_themes.json` and returns `{"themes": {}}` on failure — a theme registry, not an issuer join. `engine/credit_momentum.py:1-3` — module docstring: DISPLAY-TIER / NOT VALIDATED, authority all-false, accruing forward. `agentos/handoffs/MARKET-ONTOLOGY-F00-CONTINUITY-PRINCIPAL-RECONCILIATION-2026-09-05.md:303-305` — identity = cusip6/isin/name, prefix-then-name, first registry match; population = ETF-held par, not issuer outstanding.
- **MO-PAID-019 / MO-PAID-029:** "ROW-ACCOUNTING REPAIR (charter 10.3): capital-structure identity is cusip6/isin/name prefix-then-name first-registry-match; it is not a canonical issuer join." Evidence: `agentos/handoffs/MARKET-ONTOLOGY-F00-META-CEO-CONTINUITY-PRODUCT-RESET-2026-09-05.md:333-334` — the charter 10.3 sentence itself.

Plainly: held par is labelled held par and is never summed with issuer debt outstanding; theme/name matching is never described as a canonical issuer join.

**Plain-language repair statement, MO-DELTA-025 / MO-PAID-066 (what a reader would see, what was wrong, what the record now requires):** A bond-fund page shows one number next to each bond, labelled as an amount a fund holds. That label could be misread as the company's own total debt, which it is not — it is only what one fund holds. This record now requires that number to stay labelled as fund holdings only, and never be added together with, or shown as, the company's total debt. This packet is records-only and changes no page; a future surface build is required to apply this requirement on screen.

**Plain-language repair statement, MO-PAID-019 / MO-PAID-029 (what a reader would see, what was wrong, what the record now requires):** A capital-structure page groups filings under one company name. That grouping could be read as a guaranteed, one-to-one match to a single legal company, which it is not — it is a name-and-code match that can occasionally catch a different, similarly named company. This record now requires that grouping to be described as a name-and-code match, never as a guaranteed single-company identification. This packet is records-only and changes no page; a future surface build is required to apply this requirement on screen.

## 7. What this docket does NOT cover

- The 2 remaining ledger `BLOCKED_RIGHTS` rows outside this packet's row list are not touched here.
- Any public substitute for a licensed source: if a future session finds one, it is added here as a one-line proposal to open a gate — never as a build, never as a schedule, against any of the twenty rows above.

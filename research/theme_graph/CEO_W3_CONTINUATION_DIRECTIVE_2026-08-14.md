# CEO continuation directive — GMI Theme Graph W3 re-charter (received 2026-08-14)

> Provenance: delivered verbatim by the CEO/operator lane as the session handoff for the
> W3 wave, 2026-08-14. Committed unedited per the program's directive-provenance
> precedent (`SOURCE_CONTINUATION_DIRECTIVE_2026-08-11.md`). Adjudication and the
> resulting charter amendments live in
> `research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §11 (2026-08-14 entry);
> this file is the source record and is never edited after commit.

---

HANDOFF — GMI Theme Graph W3
Dual-Market Local Theme Intelligence → ThemeState → Selection Cohort Intelligence
CEO continuation directive — supersedes the prior W3 handoff

Continue the existing Global Market Intelligence / GMI Theme Graph program.
Do not create a parallel theme system, a new theme lobe, a second knowledge graph, or a separate "U.S. theme project."

A deeper operator review after W2 exposed a major product opportunity and a corresponding gap in the existing W3 charter:

Mastermind must be able to recognize when multiple independently qualified stocks are not isolated signals but members of the same emerging semantic neighborhood; explain the exact local subthemes connecting them; measure whether the cohort itself is broadening, concentrating, emerging, or fading; and eventually allow the authorized stock-selection engines to investigate still-early graph neighbors.

This must work symmetrically for:

* China, using the full trustworthy 同花顺 / THS concept universe and existing China basket/theme machinery; and
* United States, using the much richer local thematic taxonomy we already partially possess through Finviz, Mastermind baskets, theme discovery/emergence/fingerprint organs, and future corroborating sources.

The target product is not "a better list of baskets."
The target architecture is:

stock signals → PIT-valid local theme membership → semantic neighborhood overlap → ThemeState → cohort interpretation → graph relationships → consequence history → later, separately validated neighbor discovery / re-ranking

GMI remains constitutionally separated from stock-selection authority throughout.

## 0. CURRENT PROGRAM STATE — VERIFY BEFORE WRITING CODE

Do not trust conversational memory.
Begin by reading current `origin/main`, current project records, current contracts, current Synapse state, and current CI.

Canonical program chain presently includes:

* W0 — PR #5326: GMI Theme Graph phase-0 adjudication/masterplan — shipped.
* W1a — PR #5337: THS PIT cadence + U.S. membership PIT + freshness tripwire — shipped.
* W1b — PR #5343: bitemporal semantic spine, nodes/edges/evidence, CN crosswalk family, seeder protections, CN limit-rule registry — shipped.
* W2 — PR #5402: exposure-decomposition R1 probe — merged and concluded. GitHub currently reports #5402 merged.
* W3: existing masterplan currently says ThemeState + consequence grading over the crosswalked universe. That scope is superseded by this CEO amendment and must be corrected in the canonical program record before implementation.

Mandatory first reads:

1. `research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
2. `contracts/theme_graph/README.md`
3. `research/theme_graph/THEME_ORGAN_DISPOSITION_SWEEP.md`
4. `research/theme_graph/W2_EXPOSURE_AXES_PREREG.md`
5. W2 probe artifacts and verdict under `research/theme_graph/w2_probe/`
6. Market Memory production-record precedent around #5346
7. current Prophet / China Prophet integration and authority contracts
8. current `config/synapse.yml`
9. current `config/dag.yml`
10. current theme-related source families, builders and PIT stores
11. current Finviz theme machinery described below

Current tree/state outranks anything in this handoff if they conflict.
Do not silently resolve a conflict. Record it and adjudicate it.

## 1. WHY THIS AMENDMENT EXISTS

The operator noticed a concrete China example:
`china_stocks.html` was independently surfacing numerous lithium-related securities, yet the actionable board did not visibly recognize the selections as a coherent lithium/battery thematic cluster.

This is not fundamentally a "missing lithium basket" problem.
Mastermind already has a curated China Battery & Lithium basket, while THS additionally carries much more granular concepts such as:

* 锂电池概念
* 盐湖提锂
* 固态电池
* 钠离子电池
* 动力电池回收
* 宁德时代概念
* related energy-storage / EV / metals concepts

The architectural problem is:
security-level selection and theme-level semantic structure are not yet joined deeply enough.

The desired result is something structurally like:

5 of 12 independently qualified names occupy the same local semantic neighborhood.
Shared or adjacent concepts include 锂电池概念, 盐湖提锂 and 固态电池.
Participation is broadening across multiple independent members rather than one leader carrying the move.
Therefore the board is revealing a cohort-level phenomenon rather than five unrelated technical setups.

The language above is illustrative. W3 must earn any state terminology empirically.
The architecture itself is the ruling.

## 2. EXTERNAL RESEARCH ADJUDICATION — WHAT WE LEARNED

This section is architectural input, not authority to clone a vendor.

### 2.1 Theia proves semantic granularity and market-factor granularity are different planes

Current Theia Insights documentation describes TIIC as a five-level taxonomy covering:

* 10 sectors
* 23 industries
* 80 sub-industries
* 245 major themes
* 3,200+ micro themes
* 50,000+ public companies

and says company exposures are updated monthly while microtheme taxonomy updates quarterly.

Theia's Level-5 examples are genuinely microscopic business concepts. For Thales, examples include missile-defense systems, C4ISR, military engineering, AI in cybersecurity, cloud security and other narrow activities; Uber likewise decomposes into last-mile delivery, freight brokerage, ride-hailing, restaurant delivery and related microthemes.

But Theia's Thematic Factor Model is a much smaller measurement plane: it publicly describes 200+ thematic factors, updated daily.
Its Theme Watch product likewise tracks 200+ themes, not 3,200 distinct market factors.

CEO architectural inference

Do not interpret "Theia has 3,200 microthemes" as "Mastermind needs 3,200 daily baskets."
The correct abstraction is:

large semantic ontology
→ medium measurable theme universe
→ small strategic/canonical ontology

Therefore GMI must support microthemes that exist only as semantic graph nodes with evidence and memberships.
A node does not need:

* its own tradable basket,
* its own factor,
* its own lifecycle state,
* its own page,
* or its own stock-selection authority

merely because it exists semantically.
This distinction is now program law.

### 2.2 Theia also confirms that one company belongs to many themes

TIIC explicitly models one-to-many business exposure.
Its public Uber example assigns different Level-4 exposure percentages to ride-hailing, freight/cargo logistics, delivery, mobile apps, e-commerce, AI, EVs, data analytics and others.

That is important because Mastermind must never collapse a company to one theme label.
Correct object:
`company → many local theme memberships / exposure claims`
not:
`company → sector → one theme`

The graph must preserve overlap.

### 2.3 Concept2Universe validates the "idea → explainable company universe" architecture

Theia's Concept2Universe product publicly describes converting an arbitrary concept into:

* a custom taxonomy,
* an explainable universe of relevant companies,
* dynamic updates,
* and evidence,

including companies beyond obvious names.

That supports the long-term GMI direction:
graph neighborhoods can reveal companies the operator did not manually associate with a theme.

It does not authorize GMI to recommend those companies.
That final selection remains the incumbent Prophet / discovery authority's job.

### 2.4 S&P's public thematic work validates separating semantic exposure from price behavior

The June 2026 S&P Thematics Dashboard states that it works with roughly 250 Theia Major Themes. It also says each theme basket represents the top 30 stocks selected using a metric combining:

1. the stock's exposure to the theme; and
2. its excess-return correlation with the theme's return.

This is extremely relevant to W2.
W2 independently concluded that semantic/economic exposure and trading behavior must not be treated as the same measurement.
The external evidence therefore reinforces—not replaces—the W2 ruling.

Do not copy S&P's portfolio methodology.
Use it only as confirmation that these are legitimately separate dimensions.

### 2.5 S&P Atlas gives another example of multi-dimensional theme relevance

The current S&P Atlas methodology uses Theia's Concept2Universe workflow and separates:

* Thematic Exposure Score;
* Aggregate Concept Relatedness Score;
* underlying market-capitalization information;

and classifies sufficiently high-exposure companies as "core."

Again:
do not copy the formula or thresholds.
The architectural lesson is merely that:

membership/relevance,
economic exposure,
market behavior, and
portfolio construction

are different objects.
GMI must keep them separate.

### 2.6 S&P Kensho is relevant as a corroborating ecosystem taxonomy

S&P describes its Kensho New Economy indices as using NLP over large amounts of regulatory filings and public information to identify companies involved in emerging economies. It explicitly emphasizes capturing not only obvious leaders but the ecosystem supporting an industry.
Its New Economy Subsector indices are intended to provide precise exposures to individual emerging industries.
For example, its public Robotics index description includes companies developing robots and supply-chain companies providing specialized products and services.

This supports W4's existing SUPPLIES / ENABLES direction.
It does not justify inventing those edges in W3.

## 3. FINVIZ RESEARCH RESULT — U.S. GRANULARITY IS ALREADY MUCH CLOSER THAN THE OLD GMI CENSUS IMPLIED

The operator supplied a fresh extraction of Finviz's themes map.
It contains:

* 40 top-level themes
* 268 subthemes
* 2,339 theme-member listings
* 924 unique tickers

with deliberate cross-theme overlap.

The extraction is materially more granular than our 49 curated Mastermind U.S. baskets.

Examples:

Artificial Intelligence
Finviz subdivides AI into Compute, Cloud, Models, Data, Enterprise, Networking, Security, Edge, Robotics, Applications, Ads & Search, Energy and AGI.

Electric Vehicles
EV decomposes into:

* Manufacturers
* Batteries
* Charging
* Chips
* Suppliers
* Self-Driving
* Fleets

with separate member sets.

Commodities Metals
Metals decomposes into:

* Gold
* Silver
* Precious
* Industrial
* Battery
* Rare Earth
* Recycling

and the Battery subtheme contains names such as ALB, SQM, LAC, SGML, MP and others.

Defense & Aerospace
Defense contains separate Drones, Missiles, SpaceTech, CyberDefense, Weapons, Aviation and Manufacturing/Supply-Chain cohorts.

This is almost exactly the local semantic resolution the new Selection Cohort architecture needs.

## 4. IMPORTANT REPO FINDING — FINVIZ IS ALREADY AN ACTIVE ORGAN

Do not build another Finviz collector.

Current `main` already contains:

* `scripts/fetch_finviz_themes.py`
* `engine/themes_heatmap.py`
* `scripts/build_themes_heatmap.py`
* `data/themes_heatmap/themes_tree.json`
* PIT subsector performance history
* PIT tree history
* a Finviz theme heatmap build
* downstream subsector/rotation consumers.

The current collector understands the source as:
theme → subsector → members
and fetches performance for subsectors and member tickers over multiple horizons. It also has append-only PIT archival of subsector performance and theme-tree changes.

However, structural tree refresh remains effectively manual/controlled. The current collector says the committed structure is the source of record and does not simply re-pull it during normal runs.

Existing GMI documentation is therefore stale on this point

The W1a theme-organ disposition sweep still describes the Finviz extraction as a one-shot 2026-06-27 artifact with "zero builder."
That no longer matches current main, which has the active collector and PIT archive machinery above.

W3A must amend the disposition sweep before consuming this organ.
Do not let stale governance prose dictate current architecture.

## 5. FINVIZ TREE DRIFT / PARSER RECONCILIATION MUST BE EXPLICIT

The repo's older June 27 Finviz extraction records:

* 40 themes
* 268 subsectors
* 941 unique tickers
* 2,356 memberships.

The operator's newer extraction records:

* 40 themes
* 268 subthemes
* 924 unique tickers
* 2,339 memberships.

Do not immediately interpret the difference as true source membership turnover.

It may be:

* source changes;
* parser differences;
* ticker normalization differences;
* delistings/renames;
* classification changes;
* source-page changes;
* or extraction error.

W3A must reproduce the current Finviz source independently, compare all three views:

1. current committed tree;
2. operator-supplied extraction;
3. newly receipted live extraction;

and generate a full reconciliation:

* theme keys gained/lost;
* subtheme keys gained/lost/renamed;
* ticker memberships gained/lost;
* identity-normalization differences;
* actual source changes vs parser artifacts.

No tree mutation before that reconciliation passes review.

## 6. CEO RULING — THE U.S. NEEDS THE SAME LOCAL-THEME PLANE AS CHINA

The old mental model was roughly:

U.S.
→ 49 curated baskets
→ 18 canonical Foresight themes

China
→ 237+ THS baskets/concepts
→ selected crosswalks
→ 18 canonical themes.

That is too asymmetric.

The new architecture is:

Plane 1 — Local semantic universe

China
Full trustworthy THS and other legitimate local theme/concept nodes.
A THS concept does not need a global Foresight mapping to exist.
Examples:
`THS:锂电池概念`
`THS:盐湖提锂`
`THS:固态电池`
may all remain independent legitimate local concepts.

United States
Full trustworthy U.S. local taxonomy sourced from existing owner systems.
Initial source families include:

* Mastermind's 49 curated baskets;
* Finviz's theme/subtheme/member structure;
* existing theme discovery outputs;
* `theme_emergence`;
* `theme_fingerprint`;
* lawful narrative-emergence candidate evidence;
* other already-rowed theme organs;
* future source-labeled institutional corroboration.

A U.S. local theme does not need to map to one of the 18 canonical themes.
Examples might include:

* AI Agents
* AI Software
* Quantum Hardware
* Missile Defense
* Data-Center Cooling
* Battery Metals
* Gold
* Silver
* InsurTech
* Last-Mile Delivery
* Identity Security
* Industrial Machine Vision

provided the concept has lawful provenance.

## 7. PLANE 2 — MEASURABLE LOCAL THEMES

Not every semantic node gets market-state computation.
This is a critical design distinction.

A local semantic node may remain:
semantic-only
if it lacks sufficient:

* member breadth;
* clean security identity;
* point-in-time membership;
* price coverage;
* historical depth;
* coherent market exposure;
* trustworthy owner inputs.

A stronger theme may become:
measurement-eligible
and receive nightly ThemeState.

Do not hard-code an arbitrary target count.
External evidence suggests the likely order of magnitude is a few hundred measurable themes—Finviz currently has 268 subthemes, while Theia/S&P operate at roughly 245–250 major themes and Theia maintains 200+ thematic factors—but this is an architectural clue, not an acceptance quota.

The data decides eligibility.
Do not engineer toward "exactly 250."

## 8. PLANE 3 — CANONICAL CROSS-MARKET THEMES

The 18 existing Foresight themes remain the canonical strategic vocabulary until their owner legitimately expands it.

Local nodes may map to canonical nodes where evidence supports the relationship.

Examples:
local semiconductor concepts
→ canonical AI Semiconductors
local robotics concepts
→ canonical Robotics & Automation

but:
local Gold
→ may remain local/global-basket context without a canonical Foresight theme

and:
local AI Agent Applications
→ may remain a legitimate local theme if the canonical ontology has no correct parent.

Null canonical mapping is not an error.
Never create a fake canonical mapping merely because a downstream UI wants one.

## 9. PLANE 4 — MICROTHEME SEMANTIC GRAPH

The architecture must be capable of growing beyond the current measurable theme plane.

Long-term GMI should support hundreds or thousands of narrow concepts such as:

* C4ISR
* Missile Defense Systems
* AI in Cybersecurity
* Last-Mile Delivery
* Freight Brokerage
* Solid-State Battery Materials
* battery recycling
* memory interface chips
* satellite communications
* launch infrastructure
* advanced packaging
* optical interconnects
* etc.

These may exist as semantic graph nodes with evidence even if they have:

* only three companies;
* no reliable aggregate return;
* no ThemeState;
* no dedicated product page.

This is how Mastermind reaches Theia-like semantic granularity without building 3,200 pseudo-indices.

## 10. NO PARALLEL KNOWLEDGE STORE

Do not create:
`data/us_theme_taxonomy_v2.json`
as a second manually curated truth store unless an existing contract explicitly requires it.

GMI already has:

* graph nodes;
* graph edges;
* evidence;
* crosswalk machinery;
* source membership documents.

Use and extend those additive contracts.
Any convenient "registry" used for rendering/query must be a derived view, not an independent authority.

`DNR:KILL-PARALLEL-KNOWLEDGE-BASE` continues to bind.

## 11. SOURCE CLAIMS MUST REMAIN SOURCE CLAIMS

Finviz saying:
`ALB ∈ EV / Batteries`
does not mean GMI itself asserts:
ALB is economically 80% battery exposure.

Those are different claims.

Likewise:
S&P/Kensho membership, Theia exposure, Mastermind curated membership, filing evidence and price beta are different evidence classes.

Preserve source provenance.
A company may have multiple supporting or conflicting claims.
Do not silently consensus-average them.

## 12. WEIGHTINGS — DO NOT INVENT WHAT WE DO NOT HAVE

The operator specifically raised that Finviz provides memberships but not Theia-style exposure percentages.
That is not a W3 blocker.

Keep four concepts separate:

A. Semantic membership
Question: Does this company legitimately participate in this concept?
Example source: Finviz membership, THS concept membership, curated Mastermind basket.
May be binary or source-native.

B. Economic / business exposure
Question: How much of what the company actually does belongs to this theme?
This is what Theia's public TIIC examples quantify.
Mastermind W2 concluded that our current economic axis is an honest null.
It remains null.
Do not derive economic exposure from:

* number of theme memberships;
* market cap;
* price correlation;
* keyword count;
* Finviz membership;
* LLM judgement.

If Mastermind later licenses Theia or builds proper segment/product ingestion, route it through the existing company-exposure owner contract.

C. Trading exposure
Question: How much does this security actually trade with the theme?
W2 established that `trading_beta.v0` is interpretable only with important constraints.
When used:

* retain the W2 decomposition into correlation + relative-volatility ratio;
* never sell raw beta as "co-movement";
* retain the CN quarterly-horizon failure;
* reconstruction-era limitations remain explicit.

D. Basket portfolio weight
Question: How much weight does a member receive in a constructed price basket?
This is a construction decision, not semantic truth.
Do not confuse it with economic exposure.
Equal-weight may be a valid measurement construction where already established by owner machinery, but it must be labeled as such.

## 13. OPTIONAL THEIA PROCUREMENT — EVALUATE, DO NOT BLOCK W3

Theia could materially accelerate the economic/semantic exposure plane.
But public pages do not expose a complete downloadable matrix of all 3,200+ microthemes × all companies × historical exposure weights.
Concept2Universe and TIIC are commercial products.
Therefore W3 must not depend on obtaining them.

Create a short procurement/data-evaluation note answering:

If Theia were licensed, do we receive:

* Level-4 and Level-5 taxonomy?
* company-theme exposure weights?
* historical vintages / point-in-time availability?
* security/company identifiers?
* evidence/provenance fields?
* update cadence?
* redistribution/display rights for Mastermind customers?
* model-derived vs directly sourced field labels?
* API/bulk delivery?
* geographic coverage?
* public/private company split?
* licensing limitations on derived models and user-facing outputs?

If commercially attractive, recommend acquisition.
If not, GMI continues with native/external-source evidence.
Vendor dependency is never required for GMI correctness.

## 14. S&P / KENSHO USE — CORROBORATION, NOT SECRET SCRAPED TRUTH

S&P/Kensho can be valuable for:

* definitions of emerging industries;
* public constituent evidence where lawfully available;
* ecosystem/supply-chain context;
* independent corroboration of membership;
* taxonomy comparisons.

Do not assume broad redistribution rights.
S&P Atlas documentation explicitly states daily constituent/index data are available via subscription.
If systematic use beyond public research is desired, perform a data-rights/procurement review.
Do not build a production dependency on an undocumented public download route.

## 15. FINVIZ DATA-RIGHTS / SOURCE-RISK GATE

Current Mastermind already consumes Finviz theme data operationally, but W3A is expanding its strategic importance.

Before making vendor-derived membership a central user-facing GMI truth plane:

1. inventory exactly what is already consumed;
2. document source path and authentication class;
3. review Finviz's current official export/API availability;
4. determine whether our use is internal analysis, derived display, or redistribution;
5. escalate unclear commercial-use/redistribution rights rather than guessing.

Finviz currently advertises export/API access as an Elite capability, while its FAQ also notes restrictions around selling raw historical data.
Do not extrapolate that statement into a legal conclusion about theme membership.

The correct implementation rule is:
rights status must be explicit, not assumed.
If redistribution is uncertain, source-derived membership can remain internal evidence until resolved.

## 16. W3 IS NOW SPLIT INTO THREE SUB-WAVES

The original single W3 scope is too large after this amendment.
Amend the roadmap (the split below is about PR granularity; the session-chain half of the
2026-08-14 citation was repealed 2026-09-01 — `DEC:SESSION-LENGTH-IS-NOT-A-COST-CONTROL`):

W3A — Local Taxonomy & PIT Membership Plane — THIS NEXT SESSION
W3B — Dual-Market Local + Canonical ThemeState
W3C — Selection Cohort Read + Consequence Grading

One sub-wave per PR — a single session may carry more than one of them.
Do not combine all three into one mega-PR.
W1 already proved that splitting a wave into `W1a/W1b` is the right pattern when a prerequisite emerges.

## 17. W3A — EXACT SCOPE

Objective
Turn the disparate legitimate theme sources we already possess into a governed, source-labeled, PIT-safe Local Theme Plane for both China and the U.S.

W3A is primarily taxonomy/provenance/data-contract infrastructure.
W3A does not build full ThemeState yet.

## 18. W3A DELIVERABLE 1 — UPDATE CANONICAL PROGRAM LAW FIRST

Before production code:
Amend `research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` to record:

* Local Semantic Plane
* Measurable Local Theme Plane
* Canonical Cross-Market Plane
* Microtheme Semantic Plane
* Selection Cohort architecture
* U.S./CN symmetry
* W3 split into A/B/C
* external research adjudication
* Finviz current-state correction
* economic/trading/membership separation
* no 3,200-basket requirement
* future neighbor-discovery authority boundary

Append to §11 rather than rewriting prior historical decisions.
Do not erase the old W3 wording without recording that the CEO superseded it and why.

## 19. W3A DELIVERABLE 2 — RE-CENSUS THE THEME ORGAN ROSTER

The W1a disposition sweep is now stale in at least the Finviz row.
Re-run the census against current main.

For every relevant theme organ, classify:

* CONSUME
* EXTEND W3A
* EXTEND W3B
* EXTEND W3C
* FENCE-OFF
* DORMANT

Specifically verify current state of:

* `scripts/fetch_finviz_themes.py`
* `engine/themes_heatmap.py`
* `build_themes_heatmap`
* `subsector_rotation`
* `theme_scoring`
* `theme_discovery`
* `theme_emergence`
* `theme_fingerprint`
* `narrative_emergence`
* `group_pulse`
* `group_flow`
* `us_basket_turn`
* `china_basket_turn`
* THS collectors/baskets
* company-theme exposure package
* qledger/graders
* any theme machinery added since 2026-08-11

Update the disposition sweep with evidence.

## 20. W3A DELIVERABLE 3 — FINVIZ SOURCE RECONCILIATION

Reproduce the current Finviz theme structure through a receipted extraction.

Compare:
A. Existing repo tree — `data/themes_heatmap/themes_tree.json`
B. Old committed extraction — `finviz_themes/finviz_themes_map.*`
C. Operator's newer extraction — If not available in the fresh session, either ask the operator for it or independently reproduce the current public map; do not invent its contents from this handoff.
D. Fresh W3A extraction

Generate machine-readable diff:

* themes
* subthemes
* descriptions
* member tickers
* counts
* source keys
* identity normalization
* renamed themes
* membership additions/removals
* duplicate/alias handling

Every delta receives a disposition:

* genuine source change;
* parser bug;
* security-identity migration;
* source-key rename;
* unverifiable.

No "looks close enough."

## 21. W3A DELIVERABLE 4 — FINVIZ STRUCTURE REFRESH CONTRACT

The source hierarchy needs an operationally robust refresh contract similar in spirit to the THS cadence work.

Requirements:

* complete-or-fail extraction;
* raw/source receipt;
* retrieval timestamp;
* source schema/shape fingerprint;
* counts before promotion;
* content hash;
* source URL/class;
* parser version;
* identity-resolution report;
* previous-tree diff;
* append-only PIT membership/history;
* atomic promotion;
* no partial taxonomy replacing a complete taxonomy;
* no silent shrink;
* anomaly threshold/interlock;
* failed refresh leaves previous production tree unchanged.

Do not assume a fixed cadence until source stability and rights are reviewed.
If weekly is appropriate, justify it with evidence.
If manual/receipted remains the correct choice, justify that instead.

## 22. W3A DELIVERABLE 5 — PIT MEMBERSHIP SEMANTICS

For every local theme source we use, preserve:

* what the source claimed;
* when the evidence was observed;
* when Mastermind learned it;
* when membership became valid if source provides that information;
* when it ceased to be valid if known;
* reconstruction vs observed era.

Never rewrite today's membership backward through history.
A 2026 Finviz tree does not prove NVDA belonged to exactly the same subtheme in 2021.
G0.2 binds.

## 23. W3A DELIVERABLE 6 — U.S. LOCAL THEME NODES

Represent current legitimate U.S. local themes in the existing Theme Graph architecture.

Initial strong candidate grain:
Finviz subtheme, not only top-level Finviz theme.

Why:

* top-level 40 is too coarse for cohort interpretation;
* 268 subthemes is near the externally observed "major-theme" order of magnitude;
* the operator's moat depends on distinctions such as:
   * Defense → Missiles vs Drones vs CyberDefense
   * EV → Batteries vs Charging vs Chips
   * AI → Compute vs Models vs Applications vs Energy
   * Metals → Battery vs Gold vs Silver vs Rare Earth

But:
Finviz is a source family, not the ontology owner.
Node IDs must not imply universal truth.
Preserve `source_family` and source-local identity.

## 24. W3A DELIVERABLE 7 — MASTERMIND CURATED BASKETS REMAIN FIRST-CLASS

Do not delete/rewrite the 49 curated U.S. baskets.
Do not replace them with Finviz.

They serve a different role:

* curated Mastermind economic/trading sleeves;
* existing historical owner machinery;
* existing product surfaces;
* existing basket analytics.

Instead, reconcile relationships:

Mastermind basket ↔ local Finviz subthemes ↔ canonical themes ↔ future microtheme nodes

Relations must be evidence-backed.
No string-overlap auto-promotion.
Candidate mappings may be proposed mechanically but require the appropriate curation rule.

## 25. W3A DELIVERABLE 8 — CHINA LOCAL THEME PLANE

China receives the same architectural treatment.
The Local Theme Plane includes trustworthy THS concepts regardless of canonical mapping.

The existing canonical crosswalk covers only a subset of THS concepts; W1b intentionally left many concepts unmapped rather than minting fake global vocabulary.
Preserve that ruling.

Examples like:
`锂电池概念`
can receive local identity and eventually Local ThemeState even if no canonical "Lithium" global theme exists.

Do not require the global ontology to become huge just to make China useful.

## 26. W3A DELIVERABLE 9 — SOURCE-GRANULARITY METADATA

Every local theme node must carry enough metadata to know its grain.

At minimum conceptually preserve:

* source family
* source-local ID
* market/region
* source label
* local granularity/type
* source parent reference if one exists
* valid/belief times
* evidence refs
* coverage
* rights/reuse classification
* whether it currently has sufficient measurement substrate

Do not invent `PARENT_OF` graph edges if W4 still owns that edge class.
Source hierarchy may remain metadata until W4 legitimately materializes graph hierarchy edges.

## 27. W3A DELIVERABLE 10 — INTERNAL CAPABILITY CLASSIFICATION

A node needs an internal machine-readable capability status so downstream systems know what they may ask of it.
Do not make these user-facing product labels without design review.

Conceptual statuses:

SEMANTIC_ONLY — We know what the theme/concept is and which evidence links companies to it, but it lacks valid aggregate measurement.
MEASUREMENT_CANDIDATE — Potentially enough data exists; W3B must test eligibility.
MEASURABLE — W3B has established valid ThemeState construction.
CANONICAL_MAPPED — It has a legitimate cross-market canonical mapping in addition to its local identity.

These are capabilities, not market states.
Do not confuse them with:
BROADENING / WATCH / etc.

## 28. W3A DELIVERABLE 11 — THEME COVERAGE GAP MECHANISM

Build or formalize an internal coverage diagnostic.

Cases:

Case A — Multiple independently selected stocks repeatedly share evidence but GMI has no existing local concept capable of representing them.
Case B — Existing theme discovery repeatedly finds a coherent cluster not represented in the local taxonomy.
Case C — Several local concepts repeatedly move together and may need a higher-level semantic parent.
Case D — A canonical theme is too broad to explain repeated cohort structure.

Output:
taxonomy proposal / coverage gap
not:
new production theme

LLM involvement is allowed only under G0.6:

* propose name/merge/split;
* cite evidence;
* no automatic acceptance;
* no score;
* no stock signal;
* human/operator curation required.

## 29. W3A DELIVERABLE 12 — EXTERNAL CORROBORATION REGISTRY

Do not ingest S&P/Theia as unquestioned truth.

Create a lawful evidence class capable of recording:

* source provider;
* source taxonomy/theme;
* company identity;
* claim type;
* observed date;
* source document/page;
* license/use status;
* whether evidence is direct membership, exposure, ecosystem role, or description.

Possible future providers:

* S&P Kensho
* S&P Atlas
* Theia, if licensed
* other reputable thematic classifications
* issuer filings
* index holdings
* ETF holdings
* existing curated definitions

Source disagreement must survive.

## 30. W3A ACCEPTANCE TESTS

W3A is not done without hostile tests.

A. Finviz partial-tree failure — Simulate source returning only half the themes. Expected: refresh refuses promotion; prior canonical snapshot remains byte-identical.
B. Membership shrink trap — A parser error suddenly removes 40%+ of memberships. Expected: interlock; receipt records finding; no production mutation.
C. Rename without identity loss — A source renames a subtheme but members/evidence indicate continuity. Expected: source identity handling does not silently create fake historical break.
D. Real membership removal — One ticker disappears from one subtheme while remaining in another. Expected: only relevant membership closes; company and other theme memberships survive.
E. Security rename — Ticker changes but security/company identity persists. Expected: graph identity follows the security master doctrine.
F. Company participates in many themes — One company legitimately belongs to ≥5 local themes. Expected: no forced single-label classification.
G. Local-only U.S. theme — A valid U.S. local theme has no canonical mapping. Expected: node survives; memberships survive; canonical ref null; no error.
H. Local-only China theme — Same test using an unmapped THS concept.
I. Semantic-only microtheme — A concept has four verified companies but insufficient measurement substrate. Expected: semantic graph exists; no ThemeState fabricated.
J. Source disagreement — Finviz says member, another source says absent/weak. Expected: evidence coexistence; no silent resolution.
K. PIT lookahead — Membership learned on date T+5 must not appear in an as-known-at-T cohort.
L. Rights gate — A source marked internal-only / rights-unresolved may not be emitted into a public artifact unless an explicit allowed derived-display contract exists.
M. No new authority — All GMI authority booleans remain false.

## 31. W3A STOP CONDITION

W3A ends when:

1. canonical program law is amended;
2. theme-organ disposition sweep is current;
3. Finviz structure source is reconciled and receipted;
4. U.S. Local Theme Plane exists lawfully;
5. China local unmapped concepts are formally supported by the same architecture;
6. source provenance/PIT semantics are enforced;
7. semantic-vs-measurable capability split exists;
8. coverage-gap mechanism exists;
9. tests/guards/adversarial review pass;
10. PR is armed / merged per house law;
11. continuation handoff for W3B is emitted.

Do not begin ThemeState production inside W3A.

## 32-38. W3B — PRE-CHARTERED NEXT WAVE (summary preserved verbatim below)

### 32. W3B objective
Determine which Local Theme nodes support defensible ThemeState and begin nightly PIT accrual. W3B must not simply run state over every semantic node.

### 33. W3B — MEASUREMENT ELIGIBILITY
Before minting a ThemeState, assess at minimum: live member count; historical member availability; price coverage; PIT membership depth; security identity integrity; missing-data rate; concentration; effective breadth; source freshness; survivorship treatment; source/reconstruction era; whether the theme is so broad or heterogeneous that aggregate price state becomes meaningless. Do not set thresholds because they "sound reasonable." Preregister them or derive/bake them from history using the house pattern. Coverage-floor abstention must exist.

### 34. W3B — THEME STATE LEGS
ThemeState remains a collection of named legs, not one fused strength score. Candidate existing-owner legs include: breadth/participation; member-turn participation; leadership concentration; leadership renewal; internal dispersion/coherence; price/cycle state; existing basket-turn state; crowding/hazard where entitled; attention where measurement-grade; flow where owner-approved; extension/too-hot texture; revisions/hiring/trade/other existing TIL legs where semantically appropriate. GMI assembles. It does not recompute owner statistics. No "Theme Score 83."

### 35. W3B — W2 CONSTRAINTS BIND
W2's nulls and caveats are mandatory. PR #5402 concluded: CN dense attention vs trading beta are distinct where cleanly measurable; trading beta is usable at monthly grain on reconstruction-era membership BUT CN fails the longer quarterly stability test; raw beta must not be sold as co-movement; economic exposure remains blocked/null; most U.S. attention remains blocked on ingestion; LHB is refused as an attention source. No W3B implementation may "fix" those findings by redefining them.

### 36. W3B — DUAL PLANE OUTPUT
For a mapped concept: local state survives independently. Example: `US:Finviz:Commodities Metals/Battery` may have Local ThemeState. If legitimately mapped upward: canonical parent may also have Canonical ThemeState. The canonical state must not destroy or overwrite local distinctions. This is essential for explanations such as: broader critical-minerals theme is stable, but the Battery Metals local branch is the one broadening.

### 37. W3B — CONSEQUENCE LEDGER PREP
Theme-state transitions begin PIT accrual. W3B must coordinate with: TIL grading machinery; placebo tape; qledger; Market Memory contract boundaries. No duplicate score ledger. Every future performance claim must follow R-TIL-6: excess over placebo, not raw hit rate.

### 38. W3B ACCEPTANCE FIXTURES
At minimum: China lithium local-theme state; unmapped THS concept; Finviz local U.S. theme; U.S. theme with canonical parent; sparse four-name semantic-only concept; overly broad incoherent theme that abstains; stale source; member concentration; reconstruction-era state; observed-era state; no-state honest null.

## 39-49. W3C — SELECTION COHORT READ (pre-charter preserved verbatim below)

### 39. W3C scope
After W3B exists, build the post-selection semantic join. Initial stock-selection consumers: China Prophet / `china_stocks.html` / What to Act On Now; U.S. Prophet / U.S. actionable stock board; other authorized incumbent selection artifacts only if separately rowed. GMI consumes the already-finalized selection set. It does not participate upstream.

### 40. W3C — INPUT CONTRACT
Input should identify: source artifact ID; source schema/version; market; source as-of; source selection timestamp; selected instrument IDs; source ordering; source selection reason/version where allowed. GMI must preserve the exact input selection.

### 41. W3C — COHORT COMPUTATION
Given an already-selected set: (1) resolve permanent identity; (2) join each security to PIT-valid Local Theme memberships; (3) attach current Local ThemeState where available; (4) attach canonical relationships where legitimate; (5) calculate descriptive overlap; (6) preserve overlapping subthemes; (7) emit graph-neighborhood context; (8) record honest null if nothing meaningful overlaps. Do not flatten `ALB → Lithium` if evidence actually says `ALB → EV/Batteries`, `ALB → Renewable/Materials`, `ALB → Metals/Battery`. That overlap is the product.

### 42. W3C — PROPOSED ARTIFACT SHAPE
Do not treat this exact field list as immutable before codebase review, but preserve the semantics.

```text
mastermind.selection_cohort_read.v1

source_artifact_id
source_schema
source_asof
computed_at
market

selected_instruments[]
n_selected

local_theme_hits[]:
    local_theme_id
    source_family
    selected_member_ids[]
    n_selected_members
    selected_fraction
    theme_member_count
    state_ref
    evidence_refs[]
    coverage
    era

canonical_theme_refs[]

neighborhoods[]:
    member_ids[]
    local_theme_ids[]
    evidence_refs[]

honest_null_reason

authority:
    can_rank=false
    can_size=false
    can_gate=false
    can_originate_signal=false
    can_add_candidates=false
    can_escalate=false
```

No `score`. No `priority`. No `rank`.

### 43. COHORT "EMERGENCE" IS NOT FREE
Raw overlap is descriptive. The phrase "cohort emergence" is a stronger instrument claim. Do not user-surface it merely because `5 / 12` names share a theme. Preregister an episode definition and grade it. Possible ingredients for research: independent selected-member count; fraction of selected board; breadth transition; member-turn count; leadership concentration; prior-state change; coverage. But: do not fuse these into one score. Episode rules may be deterministic conjunctions/thresholds if preregistered and justified.

### 44. SELECTION COHORT CONSEQUENCE QUESTIONS
Internally grade at least these hypotheses separately:
H1 — Selections clustered in one semantic neighborhood outperform isolated selections.
H2 — A cluster with broad member participation differs from a cluster carried by one leader.
H3 — A local-theme transition appears before more graph-neighbor securities independently qualify.
H4 — Multi-subtheme overlap is more informative than coarse top-level theme overlap.
H5 — Theme-state context improves post-selection explanation even if it does not improve returns.
H5 matters. GMI can be valuable as truthful explanation even if no ranking edge exists.

### 45. FUTURE EARLY-NEIGHBOR DISCOVERY — NOT AUTHORIZED IN W3
Strategic target: selected names → semantic neighborhood → remaining verified neighbors → incumbent stock engine tests those neighbors → some later independently qualify.
Allowed in W3C: enumerate internal neighborhood members; distinguish currently selected vs not selected; log whether non-selected neighbors later qualify; grade the phenomenon.
Not allowed: insert a neighbor into Prophet; change board ordering; raise readiness score; manufacture a candidate; say "buy the laggard."

### 46. FUTURE RE-RANKING EXPERIMENT
Only after sufficient evidence: test whether theme context improves decisions among already eligible securities. Possible future gauntlet: baseline eligible set vs eligible set + theme-context re-ranking. Requirements: preregistration; PIT; no lookahead; matched control; source selection preserved; true forward outcomes; sufficient N; separate U.S./CN results; null accepted. Authority remains with Prophet/CN-alpha owner. GMI never receives stock-selection authority.

### 47. REQUIRED CHINA ACCEPTANCE EXAMPLE
Construct or use real PIT-valid data where an already-selected China board contains several names connected to: 锂电池概念; 盐湖提锂; 固态电池; 动力电池回收. Expected: overlapping memberships survive; local themes survive without canonical mapping; source board selection unchanged; raw overlap readable; no invented global "Lithium" theme; no recommendation of unselected neighbors; ThemeState displayed only where measurement-eligible; honest-null otherwise.

### 48. REQUIRED U.S. ACCEPTANCE EXAMPLE
Construct or use PIT-valid data where several independently selected U.S. names overlap a specific local neighborhood. Good candidate fixture families: Battery/critical materials (Finviz currently places ALB/SQM/LAC and peers in multiple battery/materials contexts); Defense (a selected set of NOC/LMT/RTX/LHX/AVAV could overlap across missile defense, drones, cyberdefense, aviation and secure supply-chain subthemes rather than merely "Defense"); AI (an independently selected group may cluster specifically in Compute + Networking + Data Center rather than generic "AI"). Expected: same guarantees as China.

### 49. CROSS-MARKET FUTURE EXPERIENCE
Long-term GMI should be able to answer: "China's battery-metal cohort is broadening while the analogous U.S.-listed battery-materials cohort is still early" or "U.S. missile-defense and drone names are activating together, while the China defense local themes are not showing the same participation." This requires local planes first. Do not force the cross-market comparison before W4 TRANSLATES_TO relationships are evidence-backed.

## 50. W4 RELATIONSHIP — DO NOT SCOPE-GROW W3
W4 remains the richer graph-edge wave: SUPPLIES, ENABLES, CATALYST_OF, TRANSLATES_TO, PARENT_OF. This is where Mastermind moves from "these stocks share a theme" toward "these stocks sit at different points of the same causal/economic chain." Example future explanations: AI demand → data-center buildout → optical interconnects → power/cooling → grid equipment; battery demand → lithium extraction → refining → cathodes/materials → cells → recycling. W3 does not fabricate these chains.

## 51. W5 RELATIONSHIP
W5 remains the sensorium extension through owner systems. China: limit-up ecology by local theme; board-aware speculation cohorts; attention; participant/flow context; authorized minute-grain theme momentum if attestation allows. United States: ETF/fund-flow context; options witnesses where entitled; crowding; revisions; hiring; trade-flow/physical fingerprints; other owner legs. Again: named legs, not score soup.

## 52. W6 RELATIONSHIP — PRODUCT SURFACES
Only after trustworthy artifacts exist. Possible W6 destinations: Stock board ("5/12 selections share a battery-materials neighborhood"); Cohort drawer (shared local concepts; selected members; breadth state; leadership state; evidence; what changed); Theme page (local ThemeState; canonical relation; selected members tonight; non-selected graph members as context, not recommendations); Neural Web / chat (Why are so many picks lithium-related? Are these independent signals or one thematic trade? Which exact subthemes connect these names? Is participation broadening? Is one leader carrying the theme? Which related names have not independently qualified yet? Is the same theme active in another market? What happened after similar historical cohort structures?). This is the strategic product moat.

## 53. COMPETITIVE POSITIONING — BUILD THE DIFFERENTIATION, DO NOT COPY FEATURES
Theia is strong at: what businesses do, and what thematic factors explain stock returns. S&P/Kensho is strong at: systematically finding companies involved in emerging industries and supporting ecosystems. Mastermind's opportunity is to combine: what a company does + which local themes it belongs to + how its stock actually trades with those themes + what the theme's internal state is tonight + which independent security signals are clustering within that theme + how themes connect through graph edges + how similar historical graph/cohort episodes resolved. The closed loop is the moat. Not the mere possession of a taxonomy.

## 54. DATA-SCALE TARGET — NO VANITY COUNTS
Do not set acceptance criteria such as: 3,200 microthemes; 300 baskets; 250 factors. Instead report: semantic node count; measurement-eligible count; measurable count; canonical-mapped count; coverage by selected-security universe; price coverage; PIT depth; source diversity; member concentration; source freshness. A smaller truthful ontology beats a fake 3,200-node clone.

## 55. MANDATORY ADVERSARIAL REVIEW QUESTIONS
The reviewer must explicitly challenge:
1. Are we mistaking vendor taxonomy for truth?
2. Are we laundering present membership backward into history?
3. Did any parser-induced shrink look like real taxonomy change?
4. Did we duplicate an existing theme owner?
5. Did we invent weights from binary membership?
6. Did semantic membership leak into stock ranking?
7. Did a broad generic theme overwhelm more informative local structure?
8. Did we force canonical mapping?
9. Are user-facing claims backed by enough historical episodes?
10. Are vendor rights / redistribution assumptions explicit?
11. Could the same output be produced if every theme were random?
12. Does the honest-null path genuinely fire?
13. Does GMI-on/off preserve source board selection byte-identically?
14. Are "selected-cluster" findings independent of any theme score that used the same stock-selection signal?
15. Are reconstruction-era memberships excluded from promotion evidence where required?

## 56. REQUIRED W3A RETURN TO OPERATOR
At the end of W3A, return a concise operator report containing:
A. Verdict — PASS / PARTIAL / BLOCKED
B. Taxonomy census — For U.S. and China separately: local semantic nodes; memberships; unique securities; canonical-mapped nodes; semantic-only nodes; measurement candidates; provenance/source families.
C. Finviz reconciliation — Old vs operator extraction vs fresh source.
D. Coverage audit — What fraction of: U.S. Prophet universe; U.S. selected board; China Prophet universe; China selected board can be attached to at least one meaningful local theme?
E. Rights/provenance status — Which source families can be: internal-only; derived-display; directly surfaced; unresolved.
F. Residue — Only genuine unresolved blockers.
G. W3B continuation handoff.
Do not roll automatically into W3B in the same session.

## 57. UPDATED MASTER ROADMAP
W0 ✅ Architecture / adjudication
W1a ✅ Membership PIT infrastructure
W1b ✅ Semantic spine
W2 ✅ Exposure decomposition / R1 research
W3A — NEXT — Dual-market Local Theme Plane (U.S. taxonomy expansion; China local-theme formalization; Finviz PIT/source reconciliation; provenance/rights; semantic vs measurable capability)
W3B — Dual-market ThemeState (measurement eligibility; named state legs; local + canonical state; consequence accrual)
W3C — Selection Cohort Intelligence (post-selection semantic clustering; cohort episodes; consequence grading; zero-authority proofs)
W4 — Richer Semantic/Causal Edges (SUPPLIES; ENABLES; CATALYST_OF; TRANSLATES_TO; PARENT_OF)
W5 — Theme Sensorium (CN speculation ecology; attention/flow/participant context; U.S. flow/options/other owner legs; optional entitled intraday context)
W6 — Surfaces + Chat (stock-board cohort annotations; graph bands; local/canonical theme details; "what changed"; THEMES packet; Neural Web explanations)
W7+ — Research and authority-gated experiments (theme-informed re-ranking; early-neighbor discovery; analog episodes; cross-market transmission; advanced microtheme expansion; licensed economic-exposure sources if approved)

## 58. NORTH-STAR PRODUCT EXAMPLE — CHINA
Not: "Lithium basket is up 3.2%."
Instead: "Five of tonight's independently qualified A-share names occupy overlapping battery-materials neighborhoods. The strongest overlap is across lithium batteries, upstream lithium extraction and solid-state battery concepts. Participation has broadened from the prior session, and the move is no longer being carried by one member. Several other verified members of this neighborhood have not independently reached valid entry status."
The final sentence is context, not a recommendation.

## 59. NORTH-STAR PRODUCT EXAMPLE — UNITED STATES
Not: "AI is bullish."
Instead: "Six of tonight's independently qualified U.S. names cluster in the AI infrastructure branch rather than generic AI. Their shared neighborhood concentrates in compute acceleration, high-speed networking and data-center infrastructure. Application-layer AI names are not showing the same participation. This looks like a narrower infrastructure cohort, not a broad AI-market move."
Again: state first, specificity preserved, no forced stock recommendation.

## 60. FINAL CEO RULING
GMI is not a theme screener.
GMI is the semantic connective tissue between Mastermind's independent intelligence organs.
The system should eventually understand: what companies do; what local themes they belong to; what those themes are doing now; which themes overlap; which stocks are independently firing inside them; how the themes connect economically; which other members inhabit the neighborhood; and what historically followed similar states.
The authorized security-selection engines remain responsible for deciding whether any security belongs on an actionable board.
Do not compromise that separation.
That combination—deep semantic graph + temporal theme state + independent security signals + consequence memory—is the intended moat.

## 61. START INSTRUCTION
Begin W3A by:
1. retrieving current canonical GMI state;
2. verifying the actual current Finviz/theme organ state against this handoff;
3. amending the canonical GMI masterplan with this CEO ruling;
4. re-censusing the theme-organ disposition map;
5. reproducing/reconciling the Finviz structure;
6. writing the W3A implementation/prereg plan;
7. subjecting that plan to adversarial review before mutating production taxonomy or graph stores.

Do not begin by adding 200 baskets.
Do not begin by importing the operator's JSON wholesale.
Do not begin by inventing theme weights.
Do not begin by building UI.
First make the knowledge plane truthful. Then make it measurable. Then attach it to selections.

# D0 — Mechanism vocabulary crosswalk (draft)

**Status:** draft map of words that already mean different objects. Not a new ontology.  
**Do not ship this as a schema.** A later wave may freeze a small expandable list; the 2026-08-16 earnings architecture §3 is the default starting list.  
**SHA:** `3d12412e561ef77c0a9618c9d9b18871d7344209`.

---

## 0. Crosswalk law

1. Same English word, different owner → keep both strings and cite the owner. Do not alias them into one enum.
2. A reserved GMI edge type is not a live fact.
3. Group Reads closed vocab is **agreement-form**, not role.
4. “Read-through” is not a field name in `group_earnings.py`. The live object is `sympathy` plus the rest of the earnings pulse.
5. Numerical fields on a mechanism observation (architecture) are classification transparency, not return probabilities.

---

## 1. Word → current homes

| Word | Home A | Home B | Home C | Do not treat as |
|---|---|---|---|---|
| theme | TIL lifecycle / thesis | GMI `theme:*` node | Finviz/THS `ltheme:*` | a trade, a basket, a supplier set |
| basket / group | GR US curated membership | GMI `MEMBER_OF` dst | `group_context.py` buy-board “group” | interchangeable |
| peer | GR basket member | Bio `trial_peer_set` (NCT list) | EI architecture “target peer universe” | commercial competitor |
| customer | **no live Graph-1 node** | GovRev “customer concentration” = agency HHI | Demand Desk spender cohort | awarding agency; 8-K counterparty |
| supplier | reserved GMI `SUPPLIES` | GR `supply_agreement` (undirected form) | Defense D8+ spec | who supplies whom |
| beneficiary | TIL `theme_pathways` | Demand Desk beneficiary baskets | GMI `BENEFITS_FROM` reserved | a buy list (TI-R5) |
| loser | TIL pathway avoid-shaped evidence | — | — | a short call |
| bottleneck | Foresight physical nowcast | GMI `BOTTLENECK_OF` reserved | Defense D10 atlas (spec) | a ticker rank |
| chain | TXI YAML hop sequence | Demand Desk spender→beneficiary list | CSP contagion hop | the same state machine |
| transmission | `policy-transmission-intelligence` | GMI W4 “transmission context” (unbuilt) | CSP spillover | firm read-through |
| contagion | CSP / `engine/contagion.py` | Korea 2026 residual hop | Defense E45 Challenger (research) | customer transfer |
| read-through | GR group sympathy (live) | EI registry leftover `owns` wording | architecture `earnings_readthrough_hypothesis/v1` | a score |
| relationship | GR 8-K agreement type | GovRev ownership edge | Bio ontology rel | customer/supplier |
| mechanism | EI architecture §3 ontology | TXI node test | CHF cause_family | an alpha factor |
| catalyst | Bio event clocks | GovRev award_change | GMI `CATALYST_OF` reserved | a Prophet member |
| sympathy | GR `sympathy.ratio` | winner-case prose (“AI sympathy”) | — | causal transfer |
| residual | Graph 3 (architecture) | factor residual / PSS-F3 (killed standalone) | — | Graph 1 |
| pathway | TIL `theme_pathways` | `mechanism_pathways.json` (CHF surprise source) | — | a live economic path |
| incorporation | architecture `earnings_market_incorporation/v1` | TXI `expressed` | GR 5-session drift | “the stock went up” |
| hypothesis | CHF ticket / frontier cell | architecture read-through hypothesis | TXI `tier: hypothesis` | a signal |
| identity | Stock Identity `central:TICKER` | GMI `co:<market>:<SYM>[#epoch]` | GovRev UEI→legal→issuer | a theme |

---

## 2. Closed enumerations (do not extend here)

### 2.1 GMI edge types (`theme_graph.edges.v1`)

`MEMBER_OF`, `EXPRESSES`, `SAME_AS`, `TRANSLATES_TO`, `PARENT_OF`, `RELATED`, `SUPPLIES`, `ENABLES`, `BOTTLENECK_OF`, `BENEFITS_FROM`, `CATALYST_OF`, `TRACKS`, `HEDGES`.

Live today: `MEMBER_OF`, `EXPRESSES`, `TRACKS`.  
`RELATED` is the flatten-word. Prefer a typed edge or no edge.

`source_class`: `curated`, `scrape`, `filing`, `co_movement`, `llm_proposed_ratified`.  
`co_movement` on a Graph-1 type is a collapse. `llm_proposed_ratified` requires ≥1 dated evidence ref.

### 2.2 Group Reads outsider agreement types

`merger_related`, `financing`, `license`, `collaboration`, `supply_agreement`, `purchase_agreement`, `disclosed_agreement`.

None of: Customer, Supplier, Partner, Competitor.

Tape states: `confirming`, `active_divergent`, `quiet`, `unavailable`. These are **Graph 3** states on a **Graph-1-candidate** edge.

### 2.3 GovRev ownership

`issuer_legal_entity`, `wholly_owned`. Live on defense19-v1.  
Proposed expansion stays in the unreviewed loader path.

### 2.4 Bio ontology fixture relationship types

`asset_has_indication`, `organization_owns_asset_indication`, `trial_studies_asset_indication`, `trial_has_endpoint`.

Sponsor: `direct_issuer`, `parent_of_subsidiary_sponsor`.

### 2.5 TXI episode states

`dormant`, `arming`, `propagating`, `expressed`, `failed` (user label “Halted”), `expired`.

Front-facing falsifier/refutation register is banned (#3821).

### 2.6 CHF frontier cell states

`unexplored`, `accruing`, `screened`, `null_basin`, `killed`.

---

## 3. Earnings mechanism ontology (architecture default)

Copy of `research/EARNINGS_NEURAL_GRAPH_READTHROUGH_AND_CATALYST_ARCHITECTURE_2026-08-16.md` §3, kept here so EP does not mint a parallel list.

**Demand:** end-market acceleration/slowdown; customer budget; bookings/backlog; unit/volume; utilization; geographic demand; product adoption.

**Pricing and margin:** pricing power; promotions; mix; input costs; freight; labor; currency; warranty; supply constraints; productivity.

**Competitive structure:** share gain/loss; competitor entry/exit; product superiority/shortfall; customer wins/losses; capacity expansion; consolidation.

**Capital and financing:** capex; buyback/dividend; debt; liquidity; dilution; M&A; strategic investment.

**Regulatory and policy:** tariffs; reimbursement; procurement; export controls; tax; environmental; approval/licensing.

**Company-specific / nontransferable:** one-off accounting; litigation; restructuring; isolated execution; tax item; acquisition integration; idiosyncratic outage.

A company-specific classification must **drop** peer-transfer priority. This is the lawful home of “relationship existed but company-specific offset dominated.”

---

## 4. Directional logic already written (do not re-derive)

Architecture §4.4, condensed:

| Source mechanism | Same-end-market producers | Suppliers | Customers | Competitors |
|---|---|---|---|---|
| Broad demand acceleration | + operating | + only if category matches | ambiguous (volume vs input price) | + industry unless share capture stated |
| Share gain | n/a (announcer +) | + to announcer’s suppliers | n/a | − named loser; broad industry weak |
| Input cost increase | mixed | + upstream | − margin unless pricing power | weak if hedges differ |
| Inventory correction | mixed | − near-term | + if destock ends | depends on channel |
| Capex acceleration | n/a | + named equipment / power / cooling | n/a | + demand or − spend pressure |

These are **hypothesis templates**, not results.

---

## 5. Bottleneck vocabulary (see companion casebook)

Proposed EP research states — **not** live enums, **not** GMI edge types:

`NORMAL`, `TIGHTENING`, `BINDING`, `RELIEVING`, `EXCESS_CAPACITY`, `INSUFFICIENT_EVIDENCE`.

Map onto existing words:

| EP research state | Nearest live object |
|---|---|
| NORMAL | foresight numeric_band not tight; no GMI `BOTTLENECK_OF` |
| TIGHTENING | foresight legs 1–4 rising together; HBM 13D-style language accel |
| BINDING | sold-out / allocation language + capacity-full; named constraint (CoWoS, HBM, SRM) |
| RELIEVING | capacity adds guided; destock end |
| EXCESS_CAPACITY | US Silica Northern White; post-boom lithium; inventory/sales up |
| INSUFFICIENT_EVIDENCE | default; missing counterparties; reserved-null axes; Bio with no reviewed partnership |

Do not write these states onto `theme_graph.edges.v1` in this lane.

---

## 6. Recommended freeze (later DEC, not this PR)

1. Keep GMI edge enum as Graph-1/2 types.
2. Keep GR agreement vocab as form-only.
3. Adopt earnings architecture §3 as the mechanism list for any read-through hypothesis.
4. Add one field `company_specificity` already specified — high values suppress Graph-1 fan-out.
5. Do not add `RELATED`, `peer`, `read_through`, or `customer` as GMI edge types.
6. If a word is needed that already lives in two homes, the hypothesis record cites **both ids**, it does not mint a third.

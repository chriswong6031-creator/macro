# Master Product Information Architecture — V1

**Program:** Operation Institutionalize, Handoff B deliverable 2 of 3
**Status:** Proposed architecture for Sol approval. Nothing here changes production until the approval decisions in §10 are made.
**Companions:** `research/PRODUCT_EXPERIENCE_CENSUS_2026-08.md` (evidence), `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` (reference pages).
**Binding constraints honored throughout:** the two-header-family law (CLAUDE.md §Navigation source-of-truth — all changes are inventory/grouping edits inside the shared family sources, never a third header); `DNR:KILL-PROPHET-POP-MERGE` (graded Prophet board population never merged with trigger-lane setups except presentation-tier); `DNR:KILL-FUSED-COMPOSITE` (no blended conviction number on any surface); `DNR:KILL-PUBLIC-INTERNALS` (public surfaces never serve repo internals); operator ruling #3821 (falsifier/refutation language never front-facing); user-first design doctrine (`docs/DESIGN_DOCTRINE.md`) word budgets and tier system.

---

## 1. The ruling in one paragraph

The product converges on **six user jobs** — Today, Discover, Analyze, Monitor, Research, Portfolio — exactly as the CEO masterplan directs (`00` §5). Markets (US / China / Hong Kong / Canada / International / Other assets) stop being the top-level organizing principle and become a **dimension inside each job**: menu subgroups now, a persistent market scope later. Every existing URL keeps working; V1 is a regroup of the navigation inventory (`templates/_navlinks.html.j2`) plus five reference pages, not a routing migration. Internal system names come off the navigation; product names go on. Prophet — the flagship — becomes findable by name.

## 2. Why jobs-primary with markets-inside (and not the reverse)

The current market-first nav forces every visit through "which country?" before "what am I trying to do?" — but the census shows the actual jobs (find opportunities, monitor my names, understand this stock) are identical across markets, while the current structure scatters one job across eight menus and buries the flagship. The ZH-audience counterargument (China-first users live on the China surfaces) is real but is answered by the market dimension inside each job (China columns/subgroups, and later a sticky market scope), not by keeping the market-first shell that defeats the job model for everyone. Red-team pressure on this ruling and the answers are recorded in §11.

## 3. The six jobs — what each contains

### Today — "what changed, what needs attention"
Home: `start.html` (exists; becomes the Archetype-A command center — contract in §6). The signed-in default landing and the "See it live" anonymous target.

### Discover — "find my next opportunity"
Opportunity boards and idea sources, market-scoped:
- **Prophet & stock boards:** `us_stocks.html` (Prophet board home), `china_stocks.html`, `hk_stocks.html`, `canada_stocks.html`, `intl_stocks.html`
- **Screeners & signals:** `confluence_screener.html` (rename: "Screener"), `stage_analysis.html`, `winner_health.html`, `leader_radar.html`, `stock_seasonality.html`
- **Themes & narratives:** `state_of_themes.html`, `baskets.html` + per-market baskets (`baskets_china_ths.html`, `baskets_hk.html`, `baskets_canada.html`, `baskets_intl.html`), `narrative_radar.html`
- **Situations & turns:** `special_situations.html` (US) / `china_special_situations.html`, `radar.html` / `china_radar.html` (Divergence Radar), `smart_money.html`
- **Strategies & allocation:** `strategies.html`, `china_strategies.html`, `commodity_strategies.html`, `allocation.html`, `allocation_hk.html`, `allocation_canada.html`

### Analyze — "understand this instrument / sector / structure"
- **Companies:** `stocks/<TICKER>.html` dossiers, `stocks/index.html`, `stocks/earnings/` (Earnings Wire), `fundamental_forensics.html`, `capital_structure.html`
- **Sectors & groups:** `sector_central.html`, `sector_central_china.html`, subsector confluence anchors, sector/subsector/rotation long-tail families, heatmaps (`market_heatmap.html`, `china_heatmap.html`, `hk_heatmap.html`, `canada_heatmap.html`)
- **Market structure & flow:** `options.html` (macro options desk), `darkpool.html`, `market_structure.html`, `intraday_flow.html`, `flow_velocity.html`, `etfs.html` (Fund Flows)

### Monitor — "maintain my attention loop"
`watchlist.html` (see §7 duality ruling), `alerts.html` (Alert Center), `news.html`, `china_news.html`.

### Research — "deep context, regime, and the record"
- **Macro & regime:** `macro.html`, `china.html`, `hk.html`, `canada.html`, `intl.html`, country pages (JP/KR/EA/UK/IN), `macro_context.html` (Macro Weather), `bonds.html`, `forex.html`, `commodities.html`, `spr.html`
- **Cycles:** `cycle.html`, `sector_cycles.html`, `sector_cycles_china.html`, `country_cycles.html`
- **Intelligence desks:** `china_intel.html` (Intelligence Hub), `china_mechanics.html`, `policy_watch.html`, `china_policy_watch.html`, `china_altdata.html`, `alt_data.html`, government revenue, BioCatalyst
- **Reports & record:** `reports.html`, `research_vault.html`, `foresight.html`, `market_memory.html`, `neural_web.html` (label ruling §5), `us_track_record.html` (public proof), `methodology.html`, `measurement.html` (Calibration Lab, below-fold verdicts per #3821)

### Portfolio — "my holdings and decisions"
Terminal `/portfolio` is the home. Macro-side allocation/strategy pages stay in Discover (house models ≠ user portfolio). This group may render as a direct link to the Terminal until a Macro-side portfolio surface earns its place.

Counts after regroup: 6 top-level items (was 7 market menus + mega-menu), with market subgroups inside Discover/Analyze/Research. No route is orphaned: every nav-reachable page above retains a home; pages NOT listed in primary nav remain reachable via their job page's secondary links, directory pages, and search — deliberate de-emphasis, not deletion (`03` §6 P3 treatment).

**Per-menu budget (red-team amendment — re-parenting is not reducing).** Each job menu renders at most **8 primary items** (plus market subheads); everything else in that job moves behind one final "All <job> →" item pointing at a directory page (Research gets `research_index.html`; Discover's long tail lists on the boards themselves). Without this, Research (~35 destinations) would simply become the new mega-menu. Primary-item selection is part of the Phase N0 PR and is reviewed as a design decision, not an inventory dump. The census-indicted internal names that survive as product names (Neural Web, Market Memory) are the §5 naming decisions — a parent-label change alone does not discharge them.

**macro.html demotion, reconciled.** Placing the macro dashboards under Research follows the CEO scheme, but macro.html is also the estate's main anonymous SEO entry (census §7.1 break 2). Three compensations make the demotion safe: (1) "Macro & Regime" is the Research menu's *first* subgroup, with US Macro as its first primary item; (2) Today's market-state rows link to it on every visit — the daily path is Today → macro, not menu-hunting; (3) the F.2 nav rule in the design packet puts Plans + Sign-in on macro.html itself, so search arrivals get a funnel entrance regardless of menu position.

## 4. Route mapping and transition plan (URLs preserved)

**Phase N0 — nav regroup (one PR, no URL changes).** Edit `templates/_navlinks.html.j2` group structure to the §3 model, EN+ZH labels, both nav families' inventories untouched in mechanism (same partial, same `nav_prefix` handling, same responsive machinery in `navigation-refresh.css`/`nav_market.js`). Caveats: `nav_market.js` is on the Caddyfile immutable list — any behavior change there needs the render re-stamp path, so N0 should avoid touching it (grouping lives in the template partial). The anonymous `_public_nav` family is already job-shaped for its audience and does not change in N0.

**Phase N1 — reference pages** (design packet): `start.html` (Today), `us_stocks.html` (Prophet board), Prophet detail (new surface), `plans.html`, `stocks/<TICKER>.html` (dossier). URLs unchanged; Prophet detail is additive.

**Phase N2 — routing evolution:** `/today` alias → `start.html` (post design-partner validation); **`/prophet/<TICKER>.html` per-name detail pages** (amended to match the design packet §C after red-team reconciliation — ticker-canonical, episode JSON underneath; PR-4 in the packet's sequence, gated on Sol's §J decisions rather than design partners, since Handoff D's launch review needs the surface); Terminal routed `/account` page (census §7 finding 4). Aliases and additions only; nothing breaks. The SEO estate (`stocks/`, sector/subsector families) never moves.

## 5. Naming and vocabulary ruling

Customer-facing layer speaks market language; internal names demote to methodology/provenance (doctrine `02` §3). Nav label changes proposed (route slugs unchanged):

| Current label | Proposed | Rationale |
|---|---|---|
| Signal Board (`confluence_screener`) | **Screener** | job word, not mechanism word |
| Capital Flow Velocity | **Money Flow (CN)** | plain |
| Mastermind Portfolio (`watchlist.html`) | **Watchlist** — *pending §7 verification of what the page actually shows* | a watchlist page must say watchlist; if it in fact shows the house model portfolio, it belongs in Research as **Model Portfolio** |
| Neural Web (`neural_web.html`) | **DECISION REQUIRED (Sol):** keep as brand vs rename to a plain label (e.g. "Signal Network") | it is simultaneously an internal architecture name and the customer chat brand; not adjudicable at this desk |
| Mastermind Bot | **DECISION REQUIRED (Sol):** productize the name (e.g. "Mastermind AI") | external cross-domain product; brand call |
| Filing Forensics, Macro Weather, Earnings Wire, Research Vault, Smart Money | keep | already product-language and distinctive |

Prophet stage vocabulary on all user surfaces follows `04` §3 exactly: EARLY / CONFIRMING / CONFIRMED / AGING / EXTENDED / INVALIDATED — with doctrine-compliant plain-word glosses on Tier 1 (e.g. EARLY ⇒ "early sign — watch, don't chase") and no blended confidence number anywhere (`DNR:KILL-FUSED-COMPOSITE` and `04` §5 agree). Falsifier/refutation words never appear on cycle/user surfaces (#3821): projection windows, "read being updated" chips, and "what we're watching" phrasing only; full verdicts stay on the Calibration Lab below the fold.

## 6. The "Today" contract (`start.html`, Archetype A)

Primary question: **"What changed, and what deserves my attention now?"** Hard contract (budgets are doctrine Tier-1 law):

1. **Market state strip** — one row per followed market: regime word + one plain clause + as-of. Links → Research macro pages. No charts here.
2. **Needs attention** — top 3–5 items ordered by a stated non-scored precedence rule (design packet §A: watched-name stage transitions → other watchlist triggers → off-watchlist stage transitions → risk-condition changes; recency within class; no numeric blending — the `DNR:KILL-FUSED-COMPOSITE`-compliant form). Each: name, what changed (≤14 words), stance verb from the doctrine vocabulary, link. Empty state must say why ("quiet tape — nothing crossed a threshold since Friday's close").
3. **Prophet today** — a labelled *today's changes* slice (new / advanced / entered Confirmed) computed from the board's canonical stage field, plus up to 3 preview cards per the tier contract (`04` §8: anonymous 1, Free 3, paid full board link). The board link quotes the canonical total; this module never recounts. Cards use the signal-card contract from the design packet.
4. **Your watchlist** — registered: change summaries; anonymous: purpose-built explanation of what a watchlist does + one-click start (Shape C, `01` §6 — never a bare sign-in error).
5. **Risk & calendar** — current risk conditions in plain words + next 3 events that matter.
6. Nothing else above the fold. Every module links deeper; no module is a miniature of another page.

First useful answer visible without scrolling at 1440×900 and within one swipe at 390w.

## 7. Cross-product shell: what lives in Macro vs Terminal

| Concern | Home | Notes |
|---|---|---|
| Landing, plans, marketing, support/legal | Macro (public family) | unchanged |
| Today, Discover boards, Analyze dossiers, Research | Macro (product family) | static-baked shells + tier-split payloads (`TIER_PREVIEW_PATTERN`) |
| Live charting workspace, options desk, scripts | Terminal | Archetype F |
| Sign-up, sign-in, onboarding sheet | Terminal (today) | seam hardening in census §7; onboarding entry from Macro CTAs must survive a cold anonymous hit |
| Account/billing UI | Terminal | **needs a routed `/account` page** (currently a drawer; no linkable URL) — implementation PR in packet §8 |
| Entitlement authority | macro-api `/api/me` | already single-authority; do not duplicate |
| Watchlist persistence | **one API, two renderers** | Terminal owns state; Macro watchlist page reads the same store. Today's `watchlist.html` vs `/portfolio` duality resolves by verifying what `watchlist.html` actually renders (V1 open item — census §7), then either rebinding it to user watchlist state or relabeling it Model Portfolio under Research |
| AI chat (brain) | Macro serves `mm_brain.js` + `/api/brain/*`; Terminal embeds | unchanged (CXI-R23 boundary: product artifacts only) |

## 8. P0 route list (launch path, concrete)

| # | Surface | Route today | Gap |
|---|---|---|---|
| 1 | Landing | `/index.html` | polish only |
| 2 | Today | `/start.html` | reference rebuild (packet §2) |
| 3 | Macro dashboard | `/macro.html` | conformance pass later; not a reference page |
| 4 | Prophet board | `/us_stocks.html` | reference rebuild (packet §3) |
| 5 | Prophet detail | — (partials only; cards deep-link to `stock.html#<T>`, broken live) | **new surface** (packet §4) |
| 6 | Company dossier | `/stocks/<TICKER>.html` **and** `stock.html#<T>` — two competing surfaces | reference pass + canonicalization (packet §6): the static dossier `stocks/<TICKER>.html` is canonical (deep-linkable, SEO, builder-owned); `stock.html` either redirects per-ticker or becomes the dossier's interactive analyzer tab — never a second competing detail page |
| 7 | Terminal core | `app.mastermind-x.com/terminal` | own lane |
| 8 | Plans | `/plans.html` | reference rebuild (packet §5) |
| 9 | Sign-in/up | Terminal `?signin=1|signup=1` | cold-visitor seam verification |
| 10 | Onboarding | Terminal sheet | entry hardening |
| 11 | Account/billing | Terminal drawer | routed page needed |
| 12 | Watchlist | `/watchlist.html` + `/portfolio` | duality ruling (§7) |
| 13 | Paywall interstitials | `tier_preview.*` + Terminal gates | Handoff A implementation waves |
| 14 | Public proof | `/us_track_record.html` | data payload public-prefix fix (Handoff A); content per `04` §7 |
| 15 | Support/legal | `/support.html`, `/privacy.html`, `/terms.html`, `/disclaimer.html`, `/methodology.html` | presence audit only |

## 9. Mobile navigation

The shared family's existing responsive machinery stays; the job regroup *reduces* top-level width (7+mega → 6). Rules: job chips render as an overflow-safe row; market subgroups become section headers inside the sheet; Today is always first and is the mobile brand-tap target; no hover-only affordances (doctrine: hover is supplementary). Terminal mobile nav already derives from its single `TOP` source and is unaffected.

## 10. Decisions required (Sol / Chairman)

1. **Approve the six-job regroup** (§3) as the primary navigation model — or amend groups/membership.
2. **Neural Web naming** (§5) — brand vs plain label.
3. **Mastermind Bot naming** (§5).
4. **`watchlist.html` identity** (§7) — user watchlist vs house model portfolio (determines its job home and label).
5. **Founding-Pro presentation** on the plans reference page — one paid tier vs Essential-monthly visible (already reserved to Chairman in `01` §13; the plans reference design in the packet carries both variants).
6. **Prophet named-entry placement** — Discover menu item "Prophet" pointing at the board (recommended) vs holding until the detail surface ships.

## 11. Red-team record

Independent Opus red-team pass, 2026-08-11/12 (full record: design packet §K). Findings that changed THIS document, with resolutions:

- **"The regroup re-parents; it does not reduce — Research becomes the new mega-menu."** Accepted. §3 now carries a per-menu budget (≤8 primary items + "All <job> →" directory) and the primary-item selection is a reviewed design decision in the N0 PR. The reviewer's underlying point stands as a caution: job labels alone do not discharge the census's findings about internal-name destinations — those are the §5 naming decisions.
- **"macro.html — P0 #3 and the main anonymous SEO entry — is demoted into Research without reconciliation."** Accepted. §3 now records the three compensations (Research-menu lead position, Today's daily-path linkage, and the packet's F.2 rule putting Plans/Sign-in on every product page so search arrivals get a funnel entrance).
- **"Phase N2's `/prophet/<id>` contradicts the packet's `/prophet/<TICKER>.html`."** Accepted; §4 amended to the ticker-canonical scheme with the episode-JSON substrate named.
- **"Today's 'Needs attention' is an unspecified cross-source composite (`DNR:KILL-FUSED-COMPOSITE` exposure) and its Prophet counts are a second count vocabulary."** Accepted; §6 modules 2–3 respecified (stated precedence rule; labelled slice quoting the canonical total).
- The six-job model itself and the markets-inside-jobs ruling survived review: "Nothing here requires abandoning the six-job model or the count ladder."

Standing dissents: none — every accepted finding was integrated; no finding was rejected.

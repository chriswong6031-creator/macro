# Product Experience Census — 2026-08

**Program:** Operation Institutionalize, Handoff B (Fable/Opus Product Experience Census)
**Status:** Census + diagnosis. No production code changes ride this PR.
**Authority:** Fable main loop (adjudication + synthesis); Opus designer lane (live P0 diagnosis); two bounded sonnet census lanes (estate + design-system inventory). Per `06_EXECUTION_DOCKET_AND_MODEL_ASSIGNMENT.md` §3, no model approved its own critical work — an independent Opus red-team pass reviewed this document set before ship.
**Siblings:** Handoff A (access/entitlement truth census, Codex) → `research/PRODUCT_ACCESS_ENTITLEMENT_TRUTH_CENSUS_2026-08.md`; Handoff C (page registry + screenshot harness, Codex) → `research/PRODUCT_PAGE_CENSUS_2026-08.md` + `data/product_experience/page_registry.json`; Handoff D (Prophet launch readiness, Opus) → `research/US_PROPHET_COMMERCIAL_LAUNCH_READINESS_2026-08.md`. This census deliberately does NOT duplicate their ground: access enforcement truth belongs to A, the machine-readable registry and screenshot corpus belong to C, Prophet signal quality belongs to D.
**Companion deliverables (this PR):** `research/MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md`, `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md`.

Evidence discipline: claims below cite template/config/commit evidence or live-browser observation (marked **[live]**). Inference is marked as such. Live observations were taken anonymously against production `https://www.mastermind-x.com` on 2026-08-11/12.

---

## 1. Current navigation map

Two global header families exist (STANDING law, CLAUDE.md §Navigation source-of-truth) and this census found no third family — the constraint held.

### 1.1 Authenticated/product family (`templates/_navlinks.html.j2`, 112 consuming templates)

Top-level structure is **market-first**, not job-first:

| Menu | Contents (abridged) |
|---|---|
| **United States** | Macro Dashboard (`macro.html`), Stock Dashboard (`us_stocks.html`), Intraday Flow, Stage Analysis, Winner Health, Sector Intelligence, Subsector Confluence, Strategies, News, Alert Center, Options & Market Structure ▸ (options, darkpool, market_structure, leader_radar) |
| **China** | Macro (`china.html`), Stocks, Sector Intelligence, Subsector Confluence, Heatmap, Strategies, News, Research ▸ (9 more: Intelligence Hub, Market Mechanics, THS Baskets, Flow Velocity, Alt Data, Policy Watch, Divergence Radar, Special Situations, Narrative Radar) |
| **Hong Kong** | hk, hk_stocks, hk_heatmap, flow_velocity, baskets_hk, allocation_hk |
| **Canada** | canada, canada_stocks, canada_heatmap, baskets_canada, allocation_canada |
| **International** | intl, country dashboards ▸ (JP/KR/EA/UK/IN), intl_stocks, baskets_intl |
| **Other Assets** | Commodities ▸, Forex, Bonds |
| **Research** (mega menu) | ~20 items across 3 columns + rail: Intelligence Hub, Mastermind Portfolio (`watchlist.html`), Mastermind Bot (external), Reports, Research Vault, Earnings Wire, Filing Forensics, Neural Web, Market Memory, Foresight, Theme Tracker, Divergence Radar, Stock Seasonality, Signal Board, Smart Money, Fund Flows, Cycle Intelligence, Macro Weather, + rail (Policy Watch, GovRev, Alt Data, Special Situations, BioCatalyst, Capital Structure, Global Cycles ▸) |

Structural reads:

- **The nav is an org chart of the engine estate, not a map of user jobs.** Measured two ways (stated separately — red-team hygiene): the template inventory (`_navlinks.html.j2`) carries ~60 menu items across 7 menus, the Research mega-menu alone ~26; the live rendered nav (which adds sub-flyouts and repeated entries) resolves to 111 links / 85 unique destinations **[live]**. A new user must already know what "Filing Forensics", "Neural Web", or "Signal Board" mean to choose them. This is the exact failure mode the CEO doctrine names (`00` §5): internal architecture as the customer's cognitive burden.
- **The same job is scattered across menus.** Finding opportunities lives in at least 8 places (per-market stock dashboards, Signal Board, Theme Tracker, Divergence Radar ×2, Special Situations ×2, Narrative Radar, Leader Radar, Stage Analysis, Winner Health). Monitoring lives in 3 (Alert Center, watchlist, Intraday Flow). Nothing tells the user which one answers their question.
- **Internal vocabulary leads user-facing labels**: "Neural Web", "Market Memory", "Signal Board", "Capital Flow Velocity", "Mastermind Bot" are engine/program names surfaced as primary navigation. (Vocabulary ruling in the companion IA doc §5.)
- **Prophet — the flagship commercial surface — does not appear in the navigation by name.** It is embedded inside `us_stocks.html` (partials `_prophet_card.html.j2`, `_prophet_receipts.html.j2`). A stranger cannot find the product's flagship from the nav.

### 1.2 Anonymous/corporate family (`templates/_public_nav.html.j2`, 4 consuming templates)

Platform ▾ (`products/index.html` + 3 product marketing pages), Research ▾ (research_vault, stocks index, earnings), Resources ▾ (tools, learn, blog, support), Pricing (`plans.html`), Log in / Start free → `app.mastermind-x.com/terminal?signin=1|signup=1` (cross-repo). Small, bounded, deliberately separate — this family is healthy and stays (design-system lane classification: KEEP, narrow scope).

### 1.3 Terminal family (`charting-app` `components/AppNav.tsx`, origin/master)

Single `TOP` array: Chart (`/terminal`), Analysis, Discover, Options, Scripts, Portfolio, Alerts, + AI/Copilot pane trigger. Already job-shaped. `MobileNav.tsx` derives from the same source — one inventory, two renderings (the pattern Macro's IA should copy).

### 1.4 Cross-product seams (evidence)

- Sign-in/up and billing UI live in the **Terminal**; entitlement authority (`/api/me`) is macro-api hosted under `www.mastermind-x.com` (`terminal/app/api/billing/gateway.ts:20`). One authority, correct direction.
- Macro → Terminal: nav CTAs (`?signin=1|signup=1`), Mastermind Bot external link, product marketing pages. Terminal → Macro: "create free account" (`LoginFormLegacy.tsx:60`), embedded stock-dossier chart frames (`next.config.ts` CSP allows framing `mastermind-x.com/stocks/<TICKER>.html`), `mm_brain.js` chat widget.
- **Watchlist duality:** Macro `watchlist.html` ("Mastermind Portfolio") and Terminal `/portfolio` are two different surfaces claiming the same job. (Reconciliation ruling: IA doc §7.)

## 2. Page-family map

From the rendered estate (1,306 HTML files in the last complete build; counts are evidence from that build, families confirmed current in templates/builders):

| Family | Count | Nature |
|---|---|---|
| Flagship hand-authored pages (top-level `*.html`) | 166 | dashboards, desks, labs, reports |
| `rotation/` + `rotation_china/` | 501 | generated per-pair rotation pages |
| `subsector/` + `subsector_china/` + `subsector_russell/` + `subsector_nasdaq/` | 473 | generated subsector pages |
| `basket/` + `basket_china/` + `basket_intl/` + `basket_canada/` + `basket_hk/` | 115 | generated basket detail |
| `sectors/` | 51 | generated sector pages |
| `stocks/` (ticker dossiers + earnings wire) | large, generated (outside the 1,306 build snapshot's denominator — absent from that stale build) | free SEO estate (`build_ticker_pages.py`) |

Denominator note (red-team hygiene): the 1,306-file build snapshot sums the five families above (166+501+473+115+51); the `stocks/` family is additional and was absent from that snapshot, so the hand-authored share below is stated against the snapshot, and the true generated share is higher once `stocks/` is counted.

Read: **~13% of the snapshot estate is hand-authored; ~87%+ is generated long-tail.** The launch problem is therefore concentrated: the P0 journey touches ≤ 20 hand-authored surfaces plus two generated families (ticker dossiers, basket/subsector detail as drill-downs). The long tail needs archetype-templated coherence (Handoff C's registry + the migration factory in `03`), never hand-polish.

**Duplicate/overlapping surfaces found:** (a) **two stock-detail surfaces** — the static SEO dossiers `stocks/<TICKER>.html` (`ticker.html.j2`, `build_ticker_pages.py`) and the client-rendered analyzer `stock.html#<TICKER>` ("Stock analyzer — cycle & momentum"), which is what Prophet cards actually link to and which is currently broken in production (§6); (b) **two watchlist/portfolio surfaces** — `watchlist.html` ("Mastermind Portfolio") and Terminal `/portfolio`; (c) **three signup UIs** across two origins (§7.1); (d) parallel per-market action-board partials (§3.3). Canonicalization rulings for (a) and (b) are in the IA doc.

## 3. Shared-system inventory (design-system lane, adjudicated)

### 3.1 What is strong and canonical (KEEP / EXTEND)

| System | State | Adjudication |
|---|---|---|
| `templates/theme.css` core tokens — surface (`--bg/--panel/--panel2`), text (`--text/--muted`), WCAG ink layer (`--ink-*`), direction (`--up/--down` with full zh 红涨绿跌 flip incl. light×zh double-flip), health (`--warn/--act/--ok`, deliberately direction-independent), glass/popover families | Mature, contrast-audited | **KEEP** — this is the visual foundation the CEO doctrine asks us to reuse; do not create a parallel system |
| LENS tooltip system (`data-tip-en/zh`, `data-tip-rc-*` receipts; `theme.js`) | Live on 65 templates | **KEEP** — this IS the Tier-2 hover home. (Doctrine text still cites `.act-pop-src`, a retired name that never shipped — doc fix chip filed) |
| `.dtp` self-labeling tape idiom (`theme.css:1729-1794`) | Canonical but only 3 adopters | **EXTEND** — rollout, not redesign |
| `lib/illus.py` + `illus.css/js` SSR chart illustrations | Operator-mandated for ALL display charting; 9/247 templates comply | **EXTEND** — largest doctrine-compliance gap found |
| Tier-preview pattern (`docs/TIER_PREVIEW_PATTERN.md` + `tier_preview.css`: `.mx-tier-gate/.mx-tier-blurred/.mx-tier-hidden`) | Well-specified, server-enforced split, 2 desks gated so far | **KEEP** — this is the paywall UI the access ruling (`01` §6 Shape B) standardizes on; extension is Handoff A's implementation-wave territory |
| `templates/_icons.html.j2` monoline icon set | Self-described "testing ground", 8 adopters | **EXTEND** — promote base CSS to theme.css per its own header note |
| `_public_nav` family + `landing.css` | Bounded to 4 marketing pages | **KEEP (narrow)** — but `landing.css` defines a competing `:root` token set bridged by aliases; MIGRATE it onto theme.css tokens during the plans-page reference build |
| Terminal token discipline (`--r/--r-md/--r-lg/--r-pill` radius scale, `--t/--ease` motion pair, CSS-patch protocol: shared files orchestrator-owned, builders append scoped patches only) | Doctrine-locked | **KEEP** — and Macro should adopt the CSS-patch governance idea during migration |

### 3.2 What is missing at the token level (the fragmentation engine)

`theme.css` has **no spacing scale, no radius scale, no type ramp, no motion scale, no chart-series palette, no confidence/freshness token families** (freshness exists only as the `.dtp` component). Consequences measured by the census lane:

- 141 top-level `.html.j2` templates carry inline `<style>` blocks (of 216 top-level; 255 including subdirectories — denominators re-verified by the red team); `dashboard.html.j2` alone carries ~474KB of inline CSS (and, buried inside it, a complete 10-step type ramp scoped to `body.page-macro` — a ready-made ramp to promote site-wide, with the extraction cautions in the design packet PR-0).
- ~4,800 hex color literals in templates outside theme.css; worst live product surfaces: `dashboard.html.j2` (431), `measurement.html.j2` (154), `sector_central.html.j2` (82), `leader_radar.html.j2` (71), `tech_lab.html.j2` (68), `committee.html.j2` (61).
- 49 distinct border-radius values — a continuous spectrum where a 4-step scale should be.
- 55 distinct font-family declarations; token usage dominates but parallel page-local font tokens (`--sc-num`, `--wri-mono`, `--fig`) and raw literals bypass `--font-ui`.

### 3.3 Duplicated systems (MIGRATE / CONSOLIDATE targets)

- **9+ independent card systems**, zero inheritance between them: theme.css `.card`/`.mtf-card`/`.rip-card`/`.aibrief-card`; `landing.css` (`.matrix-card`, `.pcard`, …); `macro-desk.css` (a specificity-based reskin over 5 basket/allocation pages); `biocatalyst.css` (`.bci-*`, with its own fourth token root `--bci-*`); `capital_structure.css` (`.cs-*`); `fundamental_forensics.css` (`.ff-*`); `stock_seasonality.css` (`.sx-*`); `chat.css` (`.glass-card`); `market_memory.css` (`.mm-*`); `navigation-refresh.css` (`.fan-card`).
- **~100 distinct `*asof*` class variants** — the as-of stamp has been reinvented per page ~100 times. Only `.dtp-asof` is tied to a shared component.
- **82 distinct `*empty*` class variants** — every page invents its own empty state; none carry a mandatory "why" line. (Terminal's `.fin-empty` + `.fin-empty-why` — "never a bare No data" — is the better-specified pattern; Macro should adopt it.)
- **Action-board partials duplicated per market**: `_us_act_now_board.html.j2` (583 lines), `_china_act_now_board.html.j2`, `_market_state_board.html.j2`, `_etf_board_rows.html.j2` — the same "action board" concept implemented in parallel, unshared.

### 3.4 Macro ↔ Terminal divergence

Deliberate and documented (Terminal doctrine "Explicitly NOT transferred" list; `observatory.css` header): different `--up/--down` hues, different font loading, Terminal dark-only. **Adjudication: keep the divergence for launch** — converging pixel identity across repos is not a launch gate; converging *information architecture and vocabulary* is. Two genuine Terminal defects noted for its own lane: dangling `var(--sp-3)`/`--shadow-2/3` references (the known "v7" token patch), and `--font-num: JetBrains Mono` contradicting the Terminal doctrine's own "never mono for financial numerals" law.

## 4. Strongest existing surfaces (evidence: deliberate design passes, last 6 weeks)

`fundamental_forensics.html` (UX revamp 08-11), `policy_watch.html` (Macro-style simplification 08-09), `baskets.html` ("the group read" 08-09), `hk.html` + `hk_stocks.html` (command-panel overhauls), `china_mechanics.html` (cockpit redesign), `start.html` (mobile revamp), `china_stocks.html` (zoned standout cards), `capital_structure.html`, plus the us_stocks/subsectors light-mode reference pass (doctrine §5.8) and Terminal's options desk waves. These carry the house idioms worth extending (question-as-subheading framing, `.dtp` tape, zoned cards, plain-English lanes).

## 5. Weakest recurring patterns

### 5.1 The neglected middle (evidence: only mechanical bulk commits in 6 weeks, and absent from the doctrine §7 violation inventory — i.e., outside attention entirely)

`leader_radar`, `state_of_themes`, `alt_data`, `bonds`, `forex`, `foresight`, `flow_velocity`, `smart_money`, `etfs`, `china_intel`, `china_news`, `intl`, `baskets_intl`, `options` (macro side), `darkpool`, `market_structure`, `reports`, `neural_web`, `radar`, `strategies` (+ china), `watchlist`, `news`, `sector_cycles` (+ china), `country_cycles`, `cycle`, all `allocation_*`, all heatmaps, `spr`, `commodity_strategies`, `china_special_situations`, `narrative_radar`.

That is ~30 nav-reachable surfaces with no recent design attention — most of the "Research" mega-menu and nearly all non-US market menus.

### 5.2 Recurring failure patterns (census + live diagnosis, converged)

The five most damaging patterns, each observed on multiple production pages **[live]**:

1. **Numbers that disagree with each other on the same screen.** macro.html prints the same sentence with two different terminal rates in two panels ("funds 3.63% → 4.06%" vs "→ 4.10%"); china.html names the regime twice ("Growth-scare" hero vs "Stagflation" AI brief), states PBoC policy in both directions ("easing" vs "tightening (3/3 legs agree)"), and shows "Mania · 96" sentiment beside "accumulate quality into the fear"; us_stocks states its own board size six ways (93 / 81 / 74 / 69 / 68 / 29-vs-28); plans prices Essential and Pro identically while selling one as an upgrade over the other. **This is the estate's signature defect** — a desk that cannot agree with itself cannot sell an "institutional-grade" claim.
2. **Locked value is invisible rather than explained.** Anonymous visits to macro/china fire silent 401s (`release_forecast.json`, `risk_state.json`, `mm_brain.js`) and render 33 bare `—` cells with zero occurrences of upgrade/unlock/sign-in/locked anywhere on the page — and the product nav (85 unique destinations) contains **no sign-in control and no pricing link at all**. Only us_stocks does it right (blur teaser + count + CTA + sign-in).
3. **Empty states explain the build pipeline, not the market.** "It appears here after the first nightly run" ×3 on a basket page generated that night; "Data health · 12 need attention · 187 sources" and "24 of 743 stories kept" publish ops telemetry as customer copy; the Terminal uses one `—` for both loading and no-data.
4. **Tier-3 receipts shipped at Tier 1.** "§7 take marker · display-only · W6-C", "n=6 · with its cohort n=26 · grids aligned: 2/2", raw slugs (`special_situation`, `volhole +0.80`), study IDs (DT-W1a/DT-W2), machine enums as copy (`ENTER → ACCUMULATE`, "Entry trigger — regime-blocked"). Adjacent: emoji as UI icons on ≥5 surfaces (against doctrine §5.8) and name-lookup fallbacks printing tickers as company names (`NET NET`, `SNOW SNOW`, `NVDA / NVDA`).
5. **Three products wearing one brand.** Light job-navigated public family; dark geography-navigated product family (no auth, no pricing); third-origin Terminal with a third theme and its own (job-oriented) nav; **three different signup sheets across two origins**; and a missing route (`/prophet.html`) serving a literally empty document — no 404 page exists.

### 5.3 Doctrine tensions surfaced (adjudicated)

1. **Hover demotion vs critical caveats.** House doctrine says "when in doubt, demote to hover"; the convergence doctrine (§9) says critical information must not require hover. Live case: macro's hero dial shows 50 while a tooltip reveals the blend is 77 and the dial is capped — a caveat that changes how the headline reads, demoted to hover. **Ruling (this census): demotion is for mechanics, never for a caveat that changes how the headline number should be read.** Recommend recording this as a DESIGN_DOCTRINE amendment during the reference builds.
2. **Freshness honesty vs marketing.** The landing's DEMO/PREVIEW/SCRIPTED-DEMO badges are the compliant form of "nulls printed" — and the reason the stranger test fails on proof. Not fixable by copy: the landing must carry a live, dated product output (the us_stocks board) instead of mock-ups.

## 6. P0 page diagnosis and UX scores

Live production, anonymous, 2026-08-11, scored on the 15-dimension `02` §12 scorecard (0–2 each; launch bar = **≥25/30 with no dimension at 0** and purpose/first-answer/trust/access all at 2). **No P0 page currently passes.**

| Page | Score | Archetype | Zero dimensions | Defining finding |
|---|---|---|---|---|
| `us_stocks.html` | **24/30** | B | state clarity | Best page in the estate — five stance lanes + working light-mode access teaser; sunk by stating its own size six different ways |
| Terminal `/terminal` | **22/30** | F | — | Strongest execution once loaded; loading ≡ empty (`—` for both), "regime-blocked" as headline verdict |
| `macro.html` | **20/30** | D | state, access, trust | Excellent gauge+conditional header; 33 dead `—` cells from silent 401s, no auth/pricing in nav, 4.06 vs 4.10 in one sentence |
| `/` landing | **18/30** | G | freshness, trust | Proof belt labeled "2-WEEK DELAYED" showing a 21-day-old board; DEMO/PREVIEW mockups instead of the live board one click away; 15.5 mobile screens |
| `plans.html` | **18/30** | G | state, access, trust, responsive | Essential = Pro = $900/yr with contradictory feature cells; mobile hides Free+Pro columns with no selector; static scarcity counter |
| `china.html` | **18/30** | D | state, access, trust, accessibility | Regime named two different ways on one screen; policy stated in both directions; CSI 300 tile hardcoded at 4.73 (no `data-sym` — two of four index tiles static) |
| Sign-in/registration | **16/30** | H | discoverability, visual consistency, access | Three different signup sheets across two origins; "Sign in" opens "Create your account" with "FIRST CHARGE AUGUST 18"; free signup routes through a "Billing" step |
| `basket/ai_software.html` (long-tail sample) | **13/30** | C | hierarchy, copy, state, access, accessibility | 62-word study-ID disclosure paragraph always visible (DT-W1a/DT-W2); raw model weights as copy; `NET NET`/`SNOW SNOW` name failures; three pipeline empty states |
| `stock.html#<TICKER>` (Prophet detail) | **6/30** | C | eight of fifteen | **Broken in production**: universal "Could not render the analysis" for every ticker; `?ticker=` renders a blank page; board's #1 pick badged "NOT IN LIBRARY" |

Immediate production bugs found during diagnosis (chipped to separate lanes, outside this docs-only PR): the `stock.html` render failure and the china.html hardcoded index tiles.

## 7. User-journey failures

### 7.1 The anonymous funnel, walked live **[live]**

The funnel breaks in four places:

1. **Landing → proof.** The landing's evidence is DEMO/PREVIEW/SCRIPTED-DEMO mock-ups (including invented people over real tickers: "SEN · D. Okafor · Senate — MSFT · $520K"); its one real artifact is a 21-day-old board labeled "2-WEEK DELAYED" under a caption claiming it "rebuilds tonight". The live, credible board sits one click away on us_stocks and the landing never shows it.
2. **Proof → dashboard is a one-way door.** On macro/china there is no pricing link and no sign-in control anywhere in the nav. A visitor arriving from search (the normal case for an SEO'd dashboard page) finds no funnel entrance at all — 33 dead cells, no explanation, exit via brand logo only.
3. **Dashboard → detail is broken production.** Every Prophet card links to `stock.html#<TICKER>`, which fails to render for every ticker tested. The exact action that converts a skeptic — verifying one call — fails, while badging the board's #1 pick "NOT IN LIBRARY".
4. **Plans → signup contradicts itself.** Essential and Pro both $900/yr with 8 of 12 identical comparison rows (the Founding-Pro price collision from `01` §4, live and unexplained); on mobile the comparison table hides the Free and Pro columns entirely; "Start free" leaves the origin, shows a blank chart for ~3.5s, then opens a wizard branded "MASTERMIND TERMINAL" with a **Billing** step for a no-card plan; "Sign in" on start.html opens a panel headed "Create your account" showing "FIRST CHARGE AUGUST 18".

**The healthiest segment — landing → us_stocks → "Create free account" — works and is doctrine-compliant end to end. It is also the one path the landing never explicitly offers.** The buried `.obm-sheet` tier ladder (FREE/ESSENTIAL/PRO, three plain benefits each) is the clearest access statement on the site, hidden behind an unlabelled gear icon.

### 7.2 Static-trace findings (estate census lane — stand regardless of live behavior)

1. **Public proof surface data-starved by config**: `us_track_record.html` shell is served, but its payload `factordata/us_track_history.json` is not under any public prefix in `config/site_access.yml` — the proof page's numbers 403 for the exact audience proof exists for. (Handoff A owns the fix; flagged here because it breaks the anonymous journey step 2 "product proof".)
2. **Cold signup seam**: macro CTAs send anonymous visitors to `app.mastermind-x.com/terminal?signup=1`; the onboarding sheet's provider mounts inside the authenticated shell (`OnboardingProvider.tsx:102-121`), and a documented historical redirect loop (`/terminal → /login → /terminal?signin=1 → …`, comment at `app/login/page.tsx:19-22`) shows this seam has broken before. Live verification of the current behavior: §7 journey walk.
3. **"Open the Terminal" lands on the Terminal's own marketing landing** (bare `app.mastermind-x.com`), not the product — an extra hop inserted exactly at the moment of highest intent.
4. **Account/billing has no routed page** — it is a settings drawer inside the Terminal; there is no URL a support reply or an email can link to. (`01` §7 requires an account surface showing authoritative tier/status.)
5. **No standalone Prophet detail surface** — the signal card exists only as partials inside `us_stocks.html` and ticker pages; the "inspect one opportunity fully" job has no home. (Reference set fixes this; `KILL-PROPHET-POP-MERGE` constraints respected — see IA doc §6.)

## 8. Recommended priorities

P0 (launch path, from `00` §7, mapped to reality): see the companion IA doc §8 for the full route list with owners. Highest-leverage fixes in order:

1. **Land the access matrix truth** (Handoff A) — nothing else converts while the proof page starves and the paywall is inconsistent.
2. **Build the 5 reference pages** (design packet, this PR's third doc) — Today/start, Prophet board (us_stocks), Prophet detail (new), plans, ticker dossier. These freeze the archetypes.
3. **Nav regroup to user jobs** — pure `_navlinks.html.j2` inventory change, no URL changes (IA doc §4); the single cheapest coherence win in the estate.
4. **Token completion in theme.css** (spacing/radius/type/motion scales, promote the page-macro ramp) — unblocks the migration factory from reinventing values.
5. **Shared primitives for the two most-duplicated concepts** — `.asof` stamp and `.empty-state` (with mandatory "why" line) — then adopt during migration; do not big-bang the 9 card systems.
6. **Archetype migration factory** (Handoff C registry + `03` packets) for the ~30-page neglected middle and the long tail.

---

*Census evidence: estate/navigation lane report and design-system lane report (session artifacts, 2026-08-11); live P0 diagnosis (Opus designer lane, production browse 2026-08-11/12); DESIGN_DOCTRINE.md; TERMINAL_UI_DOCTRINE_2026-07-28; config/site_access.yml; docs/TIER_PREVIEW_PATTERN.md.*

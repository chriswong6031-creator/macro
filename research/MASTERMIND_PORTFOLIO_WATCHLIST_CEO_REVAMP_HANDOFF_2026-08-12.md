# Mastermind Portfolio Intelligence & Watchlists — CEO Revamp Handoff for Fable

**Date:** 2026-08-12  
**Commissioning intent:** Product architecture correction + flagship UX overhaul + cross-repo state reconciliation  
**Primary repos:**  
- `mastermindx-market-intelligence/macro`
- `mastermindx-market-intelligence/mastermind-terminal`

**Primary surface today:** `https://www.mastermind-x.com/watchlist.html`  
**Terminal surface today:** `https://app.mastermind-x.com/portfolio`

---

# 0. READ THIS FIRST — THIS IS NOT A COSMETIC REDESIGN

Do **not** treat this assignment as:

> "Make watchlist.html prettier."

The current page is structurally confused. It is trying to simultaneously be:

1. a watchlist,
2. a portfolio ledger,
3. an institutional portfolio-risk report,
4. a pre-trade simulator,
5. an account-sync/settings surface,
6. and a ticker-analysis dashboard.

The underlying repo already contains substantial good machinery. The failure is primarily **product semantics, information architecture, state ownership, and integration**.

The objective is to turn this estate into a flagship feature that can plausibly be one of Mastermind's strongest acquisition + retention products:

> **An anonymous user can enter stocks and immediately receive a serious portfolio/watchlist analysis. A free account saves, syncs, tracks, and alerts. A registered user sees the same watchlists and real portfolio across Macro and Terminal without the two concepts contaminating one another.**

This is a product correction first, frontend rebuild second, engine-integration job third.

Do not add another layer of cards onto the current page and call that the revamp.

---

# 1. CEO PRODUCT RULING — WATCHLIST != PORTFOLIO

This ambiguity is now resolved.

## 1.1 Watchlist

A **Watchlist** is an attention set.

It answers:

> "What names do I want Mastermind to keep an eye on?"

Properties:

- A user may have **multiple named watchlists**.
- Watchlist membership alone does **not** imply ownership.
- It does not require:
  - shares,
  - cost basis,
  - entry date,
  - position size.
- It can include:
  - stocks,
  - ETFs,
  - crypto,
  - futures / macro instruments where supported.
- Watchlists may contain names the user is merely researching.
- A ticker may appear in multiple watchlists.
- A ticker may exist in a watchlist without existing in the user's Portfolio.
- Removing a ticker from a Watchlist must **never** remove it from Portfolio.
- Watchlists must be accessible in both:
  - Macro,
  - Terminal.
- Registered-user Watchlists must converge on **one canonical persisted store**.
- Anonymous users can use local watchlists / an analysis session without registration.

Canonical registered storage remains conceptually:

- `watchlists`
- `watchlist_symbols`

Do not turn Portfolio into a special `watchlists` row.

---

## 1.2 Portfolio

A **Portfolio** is the user's held-position book.

It answers:

> "What do I actually own, how is that book constructed, and what risks am I carrying?"

Properties:

- Portfolio membership implies a held/tracked position.
- A position can carry:
  - ticker,
  - shares,
  - entry price,
  - entry date,
  - notes,
  - status/open/closed.
- Portfolio has position semantics and can therefore support:
  - allocation,
  - risk contribution,
  - cost-basis returns,
  - concentration,
  - event exposure,
  - scenario analysis.
- Portfolio must be available in both:
  - Macro,
  - Terminal.
- Portfolio must **not** reuse or mutate Terminal Watchlists.
- Adding/removing a position does not implicitly add/remove the same ticker from any Watchlist.

Canonical registered storage remains:

- `portfolio_positions`

### Important default

Do **not** introduce multiple persisted portfolios in this wave unless a hard dependency requires it.

Market-specific "US / CN / HK / CA / Crypto" books are **derived views of one Portfolio**, not separate portfolios and not separate database rows.

If multiple portfolios are wanted later, that deserves a deliberate `portfolios` / `portfolio_id` schema program. Do not smuggle it into this revamp.

---

# 2. THE CROSS-PRODUCT MODEL

The correct architecture is:

```text
                           CANONICAL USER STATE
                    ┌─────────────────────────────┐
                    │ Supabase + owner-scoped RLS │
                    │                             │
                    │ watchlists                  │
                    │ watchlist_symbols           │
                    │ portfolio_positions         │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
           MACRO RENDERER                 TERMINAL RENDERER
     deep intelligence / acquisition       live operational UX
                    │                             │
         watchlist.html / analyzer            /terminal + /portfolio
```

The two products are not supposed to have two competing definitions of the user's book.

They are **two renderers over the same user state**.

## Macro's job

Macro is the better home for:

- deep portfolio diagnostics,
- public anonymous Portfolio Analyzer,
- cross-engine intelligence joins,
- explanatory risk views,
- long-form position drawers,
- acquisition funnel,
- "why this matters" analysis.

## Terminal's job

Terminal is the better home for:

- live portfolio table,
- current prices,
- chart navigation,
- quick add/remove/edit,
- quick "Add to Watchlist" vs "Add to Portfolio",
- operating on holdings while charting.

This distinction is what allows both surfaces to exist without duplication.

---

# 3. CURRENT REPO DIAGNOSIS — IMPORTANT

Before building, independently verify every item below against current `origin/main`, but this is the current diagnosis from the repo.

## 3.1 Macro Watchlist persistence is still effectively single-list

Current:

- `templates/watchlist.js`
  - owns one local blob at `mdash.watchlist.v1`.
- `templates/watchstore.js`
  - `resolvePrimaryList()` explicitly selects `.limit(1)`.
  - sync logic then operates against that one resolved watchlist.

This means the Macro product does not yet implement the desired "multiple registered watchlists" product even though the Supabase relational schema supports multiple lists.

Do not paint a list selector on top of this without fixing the store seam.

---

## 3.2 Terminal supports multiple watchlists, but the persistence model is fragmented

Current Terminal:

- TerminalShell owns named watchlists in localStorage (`mm.wls`).
- The relational Supabase watchlist tables exist.
- Some server behavior still targets the user's **first watchlist**.
- The recent `/portfolio` work reconciles server + `mm.wls` lists **display-only**.

This is not a canonical cross-product multi-list model yet.

A registered user should not have:

- Macro primary-list state,
- Terminal local custom lists,
- Supabase lists,

all partially reconciling forever.

The revamp must define one registered-user truth and make local state a cache/migration/offline layer, not a peer authority.

---

## 3.3 Terminal `/portfolio` currently has the wrong semantic source

This is a major product bug.

Current Terminal `/portfolio`:

- reads `watchlists` + `watchlist_symbols`,
- passes those into `PortfolioView`,
- displays a "Conviction Book" derived from the selected Watchlist.

`PortfolioView.tsx` is explicitly a display-only Watchlist reader.

That is **not a real Portfolio**.

Meanwhile Macro already owns actual held positions in:

- `portfolio_positions`

and Macro `watchstore.js` has full CRUD over them.

This creates a semantic split where:

- one surface calls watchlist symbols a Portfolio,
- another surface treats Portfolio as actual positions.

Fix this.

### Required ruling

Terminal `/portfolio` must become a real `portfolio_positions` consumer.

Watchlist switching does **not** belong on the Terminal Portfolio page.

---

## 3.4 The Portfolio Brief seam makes the existing mismatch even stranger

There is already:

- Macro `engine/portfolio_brief.py`
- Macro `/api/portfolio/brief`
- Terminal `/api/portfolio-brief` proxy
- Terminal `PortfolioBriefPanel`

That brief was designed to describe the user's book.

But the table below it is currently driven by Watchlist symbols.

Potentially, the top and bottom of the same Terminal page can be describing different populations.

The revamp must guarantee:

> **The brief, KPIs, risk panels, and position table refer to the same Portfolio holdings.**

---

## 3.5 The portfolio-risk core is NOT the part we should throw away

Current `templates/risk_core.js` already contains serious useful machinery:

- factor betas,
- book variance,
- factor variance contribution,
- idiosyncratic risk,
- effective number of bets,
- pairwise implied correlation,
- twin clusters,
- per-position MCTR / risk contribution,
- calm vs stress covariance lens,
- coverage honesty,
- modeled/unmodeled abstention.

Do not rebuild this from scratch merely because the UI is bad.

This is valuable substrate.

---

## 3.6 Current per-name risk machinery is also substantial

`templates/watchlist_risk.js` already has per-name risk lanes covering combinations of:

- price & trend,
- stretch,
- events,
- estimate revisions,
- balance sheet / accounting quality,
- selling / ownership,
- rate sensitivity,
- transmission-chain context,
- role / review ladder.

`templates/portfolio.js` already opens a position drawer and reuses these WRI lane helpers.

Again: **integrate and redesign; do not rebuild the same logic under new names.**

---

## 3.7 PRE-TRADE CHECK is not random code — it is badly productized

The current "PRE-TRADE CHECK" is WRI W4.

It uses:

- `RiskCore.whatIf(...)`
- current book weights,
- candidate ticker,
- candidate amount,
- active calm/stress lens.

Conceptually it is a valid **scenario diagnostic**.

The problem is the product treatment:

- it is always shoved into the hero,
- its `$` default is contextless to a normal user,
- "PRE-TRADE CHECK" sounds like an order-ticket compliance tool,
- it adds another cognitive mode to an already overloaded panel.

### Ruling

Do not delete the engine.

Move it into a secondary feature called something like:

- **Scenario Lab**
- **What if I add this?**

Default collapsed.

Later it can support:

- add candidate,
- remove candidate,
- resize candidate,

but this wave does not need to create a full optimizer.

---

## 3.8 "Account sync" is plumbing masquerading as product

Current screenshot shows an entire "ACCOUNT SYNC" container.

Delete this as a first-level panel.

A user does not come to Mastermind to admire Supabase working.

Replace it with a quiet state in the workspace header:

- `Saved`
- `Saving…`
- `Local to this browser`
- `Offline`

For anonymous users:

> **Save this portfolio + get change alerts — Free**

For registered users:

> `Saved`

Account identity and sign-out belong in global account UI, not inside the analytical reading spine.

---

## 3.9 55-name Watchlist "cutoff"

Do not assume a deliberate hard cap.

Current `watchlist.js` `viewItems()` does not intentionally `.slice()` the final Watchlist rows before render; it maps the stored items and renders the filtered/sorted set.

Therefore reproduce the CEO's 55-name case and identify the actual defect:

- DOM/layout clipping?
- hydration?
- active-market filtering?
- loading failure?
- scroll containment?
- performance collapse?
- stale persisted list mismatch?
- CSS?

Regardless, the new implementation must carry an explicit dense-list acceptance test at **55 names and 100 names**.

---

# 4. SCREENSHOT DIAGNOSIS — WHY THE CURRENT PAGE FEELS BAD

The current page visually demonstrates the architecture problem.

From top to bottom, the user gets:

1. "Watchlist & Portfolio"
2. search
3. Account Sync
4. Book Risk
5. enormous factor/correlation visualization
6. three analytic cards
7. Pre-Trade Check
8. Portfolio
9. Watchlist cards

There is no clear answer to:

> "What is the main thing this page wants me to do?"

The page spends more vertical space explaining its risk model than helping the user understand their actual names.

### The current hierarchy is inverted

The user's holdings / names should be the anchor.

Risk diagnostics explain the holdings.

Today, the risk architecture visually *is the product* and the user data feels bolted underneath it.

Reverse that relationship.

---

# 5. NEW PRODUCT IDENTITY

## 5.1 Macro page

The Macro surface becomes:

# **Portfolio Intelligence**
### with a sibling **Watchlists** mode

The URL may remain `watchlist.html` initially for compatibility, but customer-facing product identity should no longer be "Watchlist & Portfolio" as one mashed concept.

Recommended workspace switch:

```text
[ Portfolio ] [ Watchlists ]
```

Do not render both full products simultaneously in one scrolling spine.

---

## 5.2 Default mode

### Anonymous

Default to:

> **Analyze a Portfolio**

The page is an acquisition tool.

Anonymous user can:

- enter tickers,
- optionally enter sizes,
- receive real analysis immediately.

No registration wall before the analysis.

### Signed in with holdings

Default to:

> **Portfolio**

### Signed in without holdings but with Watchlists

Default can still be Portfolio with a high-quality empty state:

> "Add the names you actually own — or analyze one of your Watchlists without converting it."

---

# 6. ANONYMOUS FUNNEL — THIS SHOULD BE A REAL LEAD MAGNET

Anonymous users should get real value before signup.

## 6.1 Entry UX

Do not force one ticker at a time.

Support:

- ticker search,
- fast multi-add,
- paste list.

Examples:

```text
AAPL, MSFT, NVDA, GLD, TLT
```

and ideally:

```text
AAPL 20%
MSFT 20%
NVDA 30%
GLD 15%
TLT 15%
```

Do not overbuild the parser if it delays the core wave, but bulk entry is high leverage.

---

## 6.2 Weighting modes

Anonymous analysis should support:

- Equal weight — default if only tickers supplied.
- Percent weights — optional.
- Dollar values — optional.
- Shares + price — if available from portfolio entry.

Always state which weighting mode the analysis is using.

Never silently imply equal-weight Watchlist names are actual position allocations.

---

## 6.3 Conversion point

After the real analysis renders:

> **Keep this tracked**  
> Save it across devices and get notified when your holdings change status. Free.

This is better than a generic "Sign in to sync."

Registration unlocks:

- durable save,
- cross-device sync,
- multiple Watchlists,
- alerts,
- change history,
- daily / change-triggered digest where enabled.

Do not block the core analyzer behind registration.

---

# 7. PORTFOLIO MODE — TARGET EXPERIENCE

This is the flagship deep-analysis experience.

## 7.1 Above the fold

The top of Portfolio mode should answer:

> **How healthy is my book, what is my biggest hidden risk, and what needs my attention?**

Recommended structure:

```text
PORTFOLIO INTELLIGENCE                     Saved / Save this free

[ portfolio summary / market selector if necessary ]

┌──────────────────────────────────────────────────────────────┐
│ BOOK READ                                                     │
│ 12 positions · $1.24M tracked · effective ~4 bets            │
│ Biggest hidden risk: 52% of modeled variance comes from ...  │
│ Market state: ...                                             │
└──────────────────────────────────────────────────────────────┘

WHAT NEEDS ATTENTION
NVDA   24% of book risk · extended · earnings in 3d
MSFT   estimate revisions weakening
GLD    diversifier · low co-movement with tech cluster
```

Do not make a giant diagram the first thing the user sees.

---

## 7.2 Portfolio summary metrics

Use a small number of high-value metrics.

Candidates:

- Portfolio value — when real position sizes exist.
- Day change — if a reliable live/delayed quote plane is available.
- Effective bets.
- Largest risk contributor.
- Top factor / macro exposure.
- Number of positions in elevated review.
- Earnings/event exposure this week.

Do not print 15 KPI tiles.

---

## 7.3 Portfolio Health Score

The existing PSI charter previously authorized a display-tier Portfolio Health Score.

It may ship if and only if:

- its legs are transparent,
- coverage is explicit,
- it abstains when coverage is insufficient,
- it is never the only risk explanation,
- it does not feed signal authority / ranking / sizing.

Do **not** make score implementation a blocker for the architecture revamp.

If the score is not already production-ready, ship the new workspace first and add the score in its own wave.

---

## 7.4 "What needs attention" is more useful than an abstract score

Build a deterministic attention stack.

Examples:

- high portfolio-risk contribution,
- major concentration cluster,
- technical deterioration,
- estimate revisions weakening,
- earnings event approaching,
- parabolic extension,
- accounting / balance-sheet warning,
- major option-structure change,
- regime sensitivity.

This list must not be a mystery composite.

Use a deterministic precedence hierarchy, e.g.:

1. high-risk-contribution position + elevated risk checks,
2. event inside critical window,
3. elevated risk check on a material position,
4. major status transition since last visit,
5. context-only items.

No hidden weighted soup.

---

# 8. THE RISK CENTER — REORGANIZE THE GOOD MACHINERY

The current Book Risk hero contains useful data but presents too much at once.

Move it into a clear **Risk Center** with understandable views.

Recommended tabs / sections:

## A. Concentration

Answer:

> "Am I more concentrated than the ticker count makes me think?"

Show:

- top position weights,
- top risk contributions,
- sector concentration,
- theme concentration,
- effective number of bets,
- modeled vs unmodeled coverage.

---

## B. Correlation

Answer:

> "Which positions are secretly the same trade?"

Show:

- twin clusters,
- pairwise high-correlation groups,
- calm vs selloff behavior,
- stress-only joins,
- simple correlation matrix / cluster visualization only if it improves comprehension.

The current patch-bay visualization can survive **if** redesigned as a secondary visualization.

It should not dominate the page.

---

## C. Factors & Macro

Answer:

> "What macro trade is embedded in my book?"

Reuse the existing factor model:

- Market,
- Growth / Tech,
- Rates,
- USD,
- Oil,
- China,
- BTC,
- Gold,
- size.

Show:

- top variance drivers,
- beta / factor exposure,
- simple scenario sensitivities,
- current regime interaction where honest.

---

## D. Stress

Answer:

> "What changes when the tape gets ugly?"

Show:

- calm effective bets,
- stress effective bets,
- clusters that converge in selloffs,
- factor concentration under stress,
- scenario changes.

Do not present VaR fantasy precision if it is not properly built/calibrated.

---

## E. Events

Answer:

> "How much of my book has event risk at the same time?"

Show:

- earnings this week / next 14 days,
- clustered earnings dates,
- major company events,
- macro-sensitive event windows,
- options expected move where covered.

---

## F. Portfolio weak links / strengths

Two compact lists:

### Needs attention
positions carrying the most relevant risks.

### Working for you
positions that:
- contribute diversification,
- have constructive state,
- or reduce concentration.

Use descriptive language, not prescriptive "sell/add/hedge."

---

# 9. POSITION TABLE — THIS SHOULD BECOME THE MAIN WORK SURFACE

The current Watchlist-card wall is not the correct layout for 55 names.

For both Portfolio and Watchlists, use a **dense modern SaaS table / list** as the default.

Cards can exist as an optional view later.

## Portfolio columns

Suggested desktop columns:

- Symbol / name
- Value / weight
- Day
- Since entry
- Current signal / stage
- Risk contribution
- Attention
- Next event
- expand

Do not cram every available field into columns.

---

## Watchlist columns

Suggested:

- Symbol / name
- Last / day
- Signal / stage
- Risk flags
- Next event
- Sector / theme
- Change since last visit
- expand

---

## Large list law

Must work cleanly at:

- 55 names,
- 100 names.

Acceptance:

- no hidden rows,
- no arbitrary cap,
- no horizontal page overflow,
- search/filter remains responsive,
- per-name details hydrate progressively,
- one failed ticker does not block the table.

If virtualization is needed, use it.

Do not virtualize just for fashion if 100 lightweight rows are already fine.

---

# 10. PER-TICKER ANALYSIS — CURRENTLY NOT GOOD ENOUGH

Every Portfolio position and Watchlist ticker needs a **real intelligence drawer**.

This is one of the most important parts of the revamp.

The drawer should answer:

> "What does Mastermind know about this name right now?"

## Tier 1 — instant read

At top:

- ticker / company
- current signal
- lifecycle / stage
- simple headline:
  - "Trend intact, but extended"
  - "Estimates weakening into earnings"
  - "Healthy trend; rate sensitivity elevated"
- latest quote / day move where available
- freshness

---

## Tier 2 — structured intelligence

### Price & technical state

- trend / MA structure,
- stage,
- extension,
- distance from highs,
- relative strength,
- volatility / stretch,
- entry-state context.

### Portfolio role

If this ticker is in Portfolio:

- portfolio weight,
- share of portfolio risk,
- factor cluster,
- correlated twins,
- diversification / hedge-like behavior,
- scenario sensitivity.

### Event risk

- next earnings date,
- days to event,
- expected move where available,
- event clustering with other holdings.

### Estimates / earnings quality

- revisions,
- surprise / SUE,
- analyst direction,
- earnings context.

### Fundamental / balance-sheet risk

- solvency,
- debt,
- FCF,
- accounting-quality flags,
- capital structure / filing-forensics context where available.

### Ownership / selling

- insider,
- 13F / institutional,
- Congress where relevant,
- beneficial-ownership / selling context.

### Options / positioning

When covered:

- gamma regime,
- flip / walls,
- IV rank / band,
- skew / term,
- unusual flow / positioning state.

### Macro sensitivity

- rate sensitivity,
- USD,
- oil,
- China,
- BTC / Gold,
- current regime fit.

### Sector & theme

- sector stage / rotation,
- theme memberships,
- theme posture.

### News / company intelligence

- latest material headlines,
- key facts,
- filing / company-intelligence evidence,
- links to deeper dossier.

### Links

- Open full dossier
- Open in Terminal
- Open options / related analysis where relevant

---

## Important implementation ruling

Do not create duplicate calculations inside the drawer.

Compose already-existing sources:

- `stockdata/<T>.json`
- per-market stock stores
- `portfolio_ctx.v2`
- WRI lane engine
- factor model
- options data plane
- news / ticker intelligence
- Company Intelligence
- transmission chains

If a source is unavailable at anonymous tier, degrade honestly and do not fabricate.

---

# 11. WATCHLIST MODE — MULTIPLE LISTS, CLEAR SEMANTICS

## 11.1 Header

```text
WATCHLISTS

[ AI Infrastructure ▾ ] [+ New list]

32 names · 4 changed since last visit · 3 earnings this week
```

Allow:

- create,
- rename,
- duplicate,
- delete,
- reorder.

Registered users: synced.

Anonymous: local.

---

## 11.2 Analyze a Watchlist without pretending it is a Portfolio

This is an important reconciliation.

A Watchlist can still have useful basket analysis.

Provide an explicit action:

> **Analyze this Watchlist**

Default weighting:

> Equal weight

Then show:

- concentration,
- factor exposure,
- correlated clusters,
- events.

But label it:

> **Watchlist structure — equal weighted**

Do not call equal-weight Watchlist analysis the user's Portfolio.

Optionally:

> Convert selected names to Portfolio

must be an explicit user action.

---

# 12. TERMINAL INTEGRATION — REQUIRED

This is not complete until Terminal semantics are corrected.

## 12.1 `/portfolio`

Replace the current Watchlist-backed `PortfolioView` population.

`/portfolio` must read:

- `portfolio_positions`

not:

- selected `watchlist_symbols`.

The page should show:

- actual positions,
- live current values,
- day P&L,
- since-entry,
- risk / brief,
- chart deep links.

The existing `PortfolioBriefPanel` stays only if it describes the same holdings.

---

## 12.2 Watchlist selector must leave `/portfolio`

The recent Terminal Watchlist switcher was a reasonable feature built on the wrong product definition.

Move Watchlist selection to Watchlist contexts.

Do not keep named Watchlist pills inside the real Portfolio page.

---

## 12.3 Add-to menu

From Terminal search / chart / context menu:

```text
Add to…
────────────
Portfolio
────────────
Default
AI Infra
Gold / Miners
Earnings
+ New Watchlist
```

Portfolio is visually separated from Watchlists.

### Add to Portfolio

Open a compact modal:

- ticker
- shares optional
- entry price optional
- entry date optional
- notes optional

If the user adds a ticker without sizing data, allow the position to exist as unweighted / incomplete and say so.

### Add to Watchlist

Do not ask for position information.

---

## 12.4 Portfolio quick access in charting

It is acceptable to expose a **Portfolio view** in the Terminal rail for fast chart navigation, but it is a separate source.

Do not serialize it into `mm.wls`.

Example:

```text
MY PORTFOLIO
AAPL
NVDA
GLD

WATCHLISTS
Default
AI Infra
...
```

or a top-level toggle:

```text
[ Portfolio ] [ Watchlists ]
```

---

# 13. REGISTERED WATCHLIST SYNC — FIX THE STORE, NOT JUST THE UI

The registered-user target is:

> Create a Watchlist in Macro → see it in Terminal.  
> Create one in Terminal → see it in Macro.

No "primary list only."

## Required architecture

Define one canonical Watchlist service contract over:

- `watchlists`
- `watchlist_symbols`

Both repos consume the same contract.

Local stores become:

- anonymous persistence,
- offline cache,
- migration source,
- optimistic UI cache.

They are not permanent competing authorities.

---

## Migration

Existing users may have:

- `mdash.watchlist.v1`
- `mm.wls`
- Supabase watchlists.

Migration must be:

- additive,
- idempotent,
- conflict-safe,
- owner-scoped.

Do not mass-delete cloud state because a local cache is stale.

Name collision behavior must be specified.

Recommended:

- same name -> merge symbols,
- local-only list -> create server list,
- server-only list -> keep,
- dedupe symbols,
- preserve order as best as possible,
- record a migration marker only on success.

Add tests that run the migration twice and get the same result.

---

# 14. ACCOUNT / SAVE UX

Delete the standalone `Account sync` panel.

## Anonymous header state

Quiet top-right:

> Local to this browser

CTA:

> **Save + get alerts**

## Signed in

> Saved

Potential tooltip:

> Saved to your Mastermind account

## Network failure

> Offline — changes kept locally

Do not expose implementation nouns:

- Supabase,
- cloud adapter,
- sync engine.

---

# 15. SCENARIO LAB — REHOME THE PRE-TRADE ENGINE

Rename:

> PRE-TRADE CHECK

to something normal:

> **Scenario Lab**  
> What happens if I add this position?

Default collapsed.

When opened:

- ticker search,
- amount / weight,
- before → after:
  - effective bets,
  - top factor share,
  - risk contribution,
  - cluster joins,
  - stress behavior.

Do not assume the user understands why the input says `$49,312`.

Explain the default:

> "Using your average position size"

or start blank when the portfolio has no real dollar weights.

The engine is descriptive.

No:

- recommended sizing,
- optimizer,
- "you should add X%",
- auto-rebalance.

---

# 16. DESIGN DIRECTION

The target is:

> **Macro-quality information hierarchy + Terminal-grade live app behavior.**

Use the repo's actual design system.

Read before implementation:

- `docs/DESIGN_DOCTRINE.md`
- `research/PRODUCT_EXPERIENCE_CENSUS_2026-08.md`
- `research/MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md`
- `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md`

## Do not create

- a new token system,
- a new header family,
- another standalone card grammar.

Reuse:

- `theme.css`,
- LENS tooltips,
- `.dtp`,
- shared icons,
- existing type / spacing direction from the reference program,
- Macro's hierarchy / spacing,
- existing directional color rules.

---

## Visual goal

The page should feel more like:

- a command center,
- a research workspace,
- a premium portfolio cockpit,

and less like:

- a static report,
- a pile of unrelated cards,
- an internal engine demo.

---

# 17. INFORMATION HIERARCHY — HARD RULES

1. User holdings / names lead.
2. "What needs attention" comes before methodology.
3. Risk diagnostics explain the book; they do not visually replace it.
4. One dominant idea per section.
5. No first-level panel whose purpose is "sync."
6. No always-open methodology detail.
7. No duplicate Watchlist + Portfolio content in one uninterrupted scroll.
8. No unexplained internal words:
   - ENB,
   - MCTR,
   - WRI,
   - lane,
   - factor covariance.
9. Technical names can live in tooltips / method detail.
10. One failure must degrade one component, not blank the page.

---

# 18. ROBUST PORTFOLIO ANALYSIS — REQUIRED LAYERS

Do not judge success by "more features."

Judge by whether these questions are answered.

## Portfolio structure

- What % is in top positions?
- What % of risk comes from top positions?
- How many independent bets do I really have?
- Which names are the same trade?
- Which names diversify?

## Factor / macro

- What does the book actually bet on?
- Which factors dominate variance?
- What regime is hostile / supportive to those exposures?
- What changes under stress?

## Technical risk

- How many positions are:
  - extended,
  - losing trend,
  - topping,
  - declining,
  - in constructive stages?

## Fundamental risk

- Where are:
  - estimate cuts,
  - balance-sheet warnings,
  - accounting-quality warnings,
  - dilution / capital-structure issues?

## Event risk

- How many holdings report in the next:
  - 5 days,
  - 14 days?
- Is too much of the portfolio exposed on the same dates?

## Options / positioning

Where covered:

- IV,
- gamma,
- expected move,
- walls,
- unusual positioning.

## Liquidity

If the required source is already robust:

- ADV / dollar volume,
- concentration in illiquid names.

Do not invent a liquidity framework if source quality is insufficient. File it as a gap.

---

# 19. ACCESS / TIER MODEL

Use this as the default unless current entitlement doctrine supersedes it.

## Anonymous

Gets:

- create local analysis,
- Portfolio risk core,
- Watchlist structure,
- per-ticker basic analysis,
- real values before signup.

Cannot:

- cross-device save,
- persistent server alerts,
- portfolio change history.

## Free account

Gets:

- saved Portfolio,
- multiple Watchlists,
- Macro ↔ Terminal sync,
- change tracking,
- basic alerts / digest where system supports it,
- richer server packet.

## Paid

Gets:

- deepest per-ticker context,
- AI Portfolio Brief,
- Brain portfolio conversation,
- deeper options / Company Intelligence,
- advanced alerts.

Do not make the entire feature feel fake for Free users.

This is supposed to be a product users love before being upsold.

---

# 20. BUILD WAVES — DO NOT DO ONE 10,000-LINE PR

## W0 — Architecture contract + current-state verification

Deliver:

- independent census of current Macro + Terminal state paths,
- diagram of canonical stores and renderers,
- confirm exact RLS policies,
- confirm all current localStorage keys,
- confirm current `/api/portfolio/brief` population source,
- reproduce 55-name issue,
- update the prior IA open decision: Watchlist and Portfolio are now separate concepts.

No production UI yet.

---

## W1 — Canonical state correction

### Macro

- multi-Watchlist registered store.
- local anonymous store remains.
- no first-list-only registered behavior.

### Terminal

- canonical registered Watchlist adapter.
- migration of `mm.wls` custom lists.
- preserve anonymous local Watchlists.

### Portfolio

- keep `portfolio_positions` separate.
- add a clean reusable Portfolio service seam for both products.

Acceptance:

- CRUD isolation tests.
- cross-product sync test.

---

## W2 — Macro flagship workspace shell

Rebuild `watchlist.html` information architecture:

- `Portfolio | Watchlists` switch.
- remove Account Sync panel.
- Portfolio cockpit.
- Watchlist list selector.
- dense tables.
- clean save/local state.
- anonymous bulk-entry flow.
- no advanced engine expansion yet unless needed to light the shell.

This is primarily UX / state composition.

---

## W3 — Portfolio Risk Center

Integrate existing:

- `risk_core.js`,
- WRI per-name lanes,
- factor model,
- stress lens,
- market books.

Rebuild presentation into:

- concentration,
- correlation,
- factors,
- stress,
- events.

Move Scenario Lab here collapsed.

---

## W4 — Per-ticker Intelligence Drawer

Join:

- portfolio_ctx.v2,
- stockdata,
- WRI,
- options,
- news,
- Company Intelligence,
- transmission,
- theme / sector context.

Anonymous / Free / Paid coverage must degrade honestly.

---

## W5 — Terminal Portfolio correction

- `/portfolio` reads `portfolio_positions`.
- remove Watchlist selector from Portfolio page.
- live current values.
- portfolio CRUD.
- separate "Add to Portfolio" and "Add to Watchlist."
- Portfolio quick list in Terminal if valuable.

---

## W6 — Retention

Only after the experience is coherent:

- saved change history,
- change-triggered digest,
- holding status alerts,
- "since your last visit,"
- richer Portfolio Brief v2,
- optional Health Score if ready.

---

# 21. TEST / ACCEPTANCE MATRIX

## Semantic invariants

### Test A

- Add AAPL to Watchlist `AI`.
- Portfolio remains unchanged.

### Test B

- Add NVDA to Portfolio.
- No Watchlist changes.

### Test C

- NVDA exists in both.
- Remove it from Watchlist.
- Portfolio position remains.

### Test D

- Close Portfolio NVDA.
- Watchlist membership remains.

These are non-negotiable.

---

## Cross-product

### Macro -> Terminal Watchlist

- Create `Gold Miners` in Macro.
- Add NEM / AEM / GOLD.
- Open Terminal.
- Same list and membership appear.

### Terminal -> Macro Watchlist

- Create `Space` in Terminal.
- Add RKLB / ASTS.
- Open Macro.
- Same list appears.

### Macro -> Terminal Portfolio

- Add actual portfolio position in Macro.
- Terminal `/portfolio` shows it.

### Terminal -> Macro Portfolio

- Add position from Terminal chart.
- Macro Portfolio shows it.

---

## Anonymous

- clean browser,
- no login,
- add 8 tickers,
- full basic analysis appears,
- refresh -> local session remains,
- click Save -> signup,
- after successful signup -> local state folds once,
- no duplicate rows.

---

## Large list

- 55 names,
- 100 names,
- all present,
- no cutoff,
- no horizontal page scroll at 390w,
- no JS errors,
- progressive ticker hydration.

---

## Risk correctness

Fixture:

- 8 correlated tech names
- GLD
- TLT

Expected:

- tech concentration visible,
- effective bets materially lower than ticker count,
- GLD/TLT appear as diversifying pieces where model says so,
- stress lens can show convergence,
- no unmodeled ticker silently enters factor math.

---

## Coverage

- US modeled names.
- BTC / crypto modeled names.
- HK / CN / CA positions.
- unsupported symbol.

Expected:

- never fabricate cross-currency total.
- per-market signals still work where store exists.
- factor model says when it does not cover a market.
- unsupported row remains visible with an honest state.

---

## Visual

Required screenshots:

- desktop dark EN,
- desktop light EN,
- desktop ZH,
- 390 dark EN,
- 390 ZH.

States:

- anonymous empty,
- anonymous analyzed,
- signed-in Portfolio,
- 55-name Watchlist,
- per-ticker drawer,
- Risk Center,
- Scenario Lab,
- offline/local state.

---

# 22. PERFORMANCE / RESILIENCE

- Page shell must paint without waiting for every ticker.
- Hydrate per-ticker context progressively.
- Batch quote calls where possible.
- Pause polling when tab hidden.
- One ticker fetch failure cannot break 55 others.
- Cache immutable nightly artifacts.
- No per-user holdings in repo artifacts.
- Never log shares / cost basis.
- Preserve owner-scoped RLS.

---

# 23. DO NOT REBUILD LIST

Before coding, inspect and reuse:

Macro:

- `templates/risk_core.js`
- `templates/watchlist_risk.js`
- `templates/portfolio.js`
- `templates/watchstore.js`
- `templates/watchlist.js`
- `templates/market_books.js`
- `templates/factor_exposure.js`
- `scripts/build_portfolio_ctx.py`
- `engine/portfolio_brief.py`
- current options/news/company-intel artifacts

Terminal:

- `terminal/components/TerminalShell.tsx`
- `terminal/components/PortfolioView.tsx`
- `terminal/lib/portfolioWatchlists.ts`
- `terminal/app/(shell)/portfolio/page.tsx`
- `terminal/app/api/watchlist/route.ts`
- `terminal/app/api/portfolio-brief/route.ts`
- existing quote hub / watchlist UI

Prior docs:

- `research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md`
- `research/WATCHLIST_RISK_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
- `research/PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md`
- `research/PSI_MARKET_BOOKS_DESIGN_SPEC.md`
- `research/PRODUCT_EXPERIENCE_CENSUS_2026-08.md`
- `research/MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md`
- `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md`

The previous PSI/WRI work contains a lot of valuable engine and acceptance reasoning.

We are not throwing it away.

We are correcting the user model and product composition around it.

---

# 24. THINGS YOU ARE EXPLICITLY FORBIDDEN FROM DOING

1. Do not simply restyle the current screenshot.
2. Do not add more panels before fixing the hierarchy.
3. Do not call Watchlist symbols a Portfolio.
4. Do not store Portfolio as a special Watchlist.
5. Do not couple Watchlist membership to Portfolio membership.
6. Do not leave Terminal `/portfolio` Watchlist-backed.
7. Do not leave registered custom Watchlists permanently local-only.
8. Do not surface "Account sync" as a major panel.
9. Do not remove the useful RiskCore / WRI engines just because their current rendering is bad.
10. Do not leave Scenario Lab permanently open in the hero.
11. Do not put equal-weight Watchlist risk numbers on screen without explicitly saying equal-weight.
12. Do not silently mix USD / HKD / CNY / CAD books.
13. Do not add a mysterious composite risk number and hide its legs.
14. Do not hide the anonymous analyzer behind login.
15. Do not cap a Watchlist at 20 / 40 / 50 rows merely to make the UI easier.
16. Do not invent a new CSS token system.
17. Do not create a third auth/account experience.
18. Do not let one failed ticker blank the page.
19. Do not self-merge flagship UI without review crops.
20. Do not call the task done because unit tests pass — browser-drive the actual product.

---

# 25. DEFINITION OF "LEGENDARY"

This product is done when a user can enter a messy real-world portfolio and, within seconds, understand things they were unlikely to notice in a normal brokerage:

> "I own 14 tickers but effectively only have 4 bets."

> "53% of my book's modeled risk is the same Growth/Tech factor."

> "NVDA is only 12% of my dollars but contributes 21% of my modeled swing."

> "Three of my biggest positions report earnings in the same four-day window."

> "This name looked like diversification on calm days but joins my tech cluster in selloffs."

> "Two holdings are technically healthy but estimates have rolled over."

> "GLD is actually doing something different from the rest of my book."

And for each individual position:

> "Here is the price state, technical risk, earnings/event risk, estimates, fundamentals, ownership, options structure, macro sensitivity, sector/theme context, and why Mastermind currently has it in review."

That is the bar.

Not:

> "We added a prettier card and a gradient."

---

# 26. FABLE EXECUTION PROMPT — COPY FROM HERE

You are the commissioning Fable session for a flagship Mastermind product overhaul.

Your task is to **reconcile and rebuild the Watchlist + Portfolio estate across `macro` and `mastermind-terminal`**, following this handoff as the product authority.

This is NOT a cosmetic pass.

## First actions

Before changing code:

1. Read both repos' current `AGENTS.md` / `CLAUDE.md` / build laws.
2. Read:
   - `research/UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md`
   - `research/WATCHLIST_RISK_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
   - `research/PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md`
   - `research/PSI_MARKET_BOOKS_DESIGN_SPEC.md`
   - `research/PRODUCT_EXPERIENCE_CENSUS_2026-08.md`
   - `research/MASTER_PRODUCT_INFORMATION_ARCHITECTURE_V1.md`
   - `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md`
3. Inspect current `origin/main`; do not trust old masterplan "DONE" labels over current code.
4. Reproduce the current production page and the CEO's screenshot.
5. Reproduce a 55-name Watchlist.
6. Build a current-state diagram showing:
   - every Watchlist store,
   - every Portfolio store,
   - every Macro renderer,
   - every Terminal renderer,
   - which paths read/write `watchlists`,
   - which paths read/write `portfolio_positions`,
   - all localStorage keys.
7. Explicitly verify whether `/api/portfolio/brief` and Terminal `PortfolioView` currently describe the same population.
8. Check `docs/ACTIVE_BUILD_MAP.md` and open PRs before touching shared files.

## Product law

A Watchlist is an attention set.

A Portfolio is held positions.

They are separate.

Registered Watchlists are shared across Macro and Terminal through one canonical relational store.

Portfolio is `portfolio_positions`.

The same ticker can belong to both, and operations on one never implicitly mutate the other.

Macro is the deep-analysis + public acquisition renderer.

Terminal is the live operational renderer.

## Build discipline

Do the work in waves.

Do not combine state migration, flagship UI, Terminal semantic correction, and advanced engine expansion into one unreviewable PR.

After W0 census, propose the exact PR sequence and then execute it.

For every flagship UI wave:

- show dark/light/ZH desktop crops,
- show 390px mobile,
- use real data,
- browser-drive the real interactions,
- do not self-merge before commissioning review.

## Success path to prove

Anonymous:
- open Macro analyzer,
- enter 8 stocks,
- receive real risk + ticker analysis without login,
- signup after value,
- local state folds once into account.

Registered:
- create multiple Watchlists in Macro,
- see them in Terminal,
- create another in Terminal,
- see it in Macro,
- Portfolio remains independent,
- add a Portfolio position in either product,
- see it in the other,
- delete from Watchlist and prove Portfolio is untouched,
- delete/close Portfolio and prove Watchlist is untouched.

Large-list:
- 55 and 100 names render completely.

Portfolio:
- show concentration,
- effective bets,
- factor risk,
- correlation/twins,
- stress behavior,
- per-position risk contribution,
- event clustering,
- per-ticker structured intelligence.

## Design target

The finished Macro experience should have the information hierarchy and visual taste of the strongest current Macro surfaces, but the responsiveness and operating feel of a high-end live SaaS workspace.

Do not create a new design system.

Do not make the risk model visually bigger than the user's own holdings.

Do not stop at "looks better."

The deliverable is a coherent product.

---

# 27. COMMISSIONING OUTPUT EXPECTED FROM FABLE BEFORE FIRST BUILD PR

Return to the commissioning session with:

1. **Current-state truth table**
2. **Root-cause list**
3. **Final state architecture**
4. **Exact Supabase / local-state migration plan**
5. **Macro IA wireframe**
6. **Terminal IA wireframe**
7. **PR / wave sequence**
8. **Files expected to change per wave**
9. **New vs reused engines**
10. **Acceptance matrix**
11. **Risks / collision check**
12. **What you will explicitly delete or demote from the current page**

Only then begin the flagship rebuild.

The intent is to prevent another implementation where every requested feature technically exists but the resulting page has no coherent product story.

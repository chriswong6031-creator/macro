# Mastermind-X — Commercial Architecture (V1)

**Status:** RECOMMENDATION, 2026-08-12. Produced under the operator handoff
"Mastermind-X Monetization, Activation & Growth Architecture".
**Method:** every current-state claim below was traced in code and carries a `file:line`-grade
citation. Nothing is inferred from marketing copy.
**Verification:** a 46-agent adversarial pass re-derived every factual claim from source and
red-teamed the recommendation (2026-08-12). It confirmed 19 defects and refuted 19 more. §13
records what it retracted — including two findings that were the headline of the first draft.
Base rebased onto `origin/main` @ `5614b1fde1d`; two PRs that landed the same day (#5409, #5463)
resolved a third.
**Companion documents:** `MASTERMIND_ENTITLEMENT_MATRIX.md` ·
`MASTERMIND_ACTIVATION_AND_FUNNEL.md` · `MASTERMIND_PRICING_AND_PACKAGING.md` ·
`MASTERMIND_PAYWALL_SYSTEM_SPEC.md` · `MASTERMIND_GROWTH_INSTRUMENTATION_SPEC.md` ·
`MASTERMIND_COMMERCIAL_V1_IMPLEMENTATION_PLAN.md`.
**Relationship to prior work:** extends `research/MONETIZATION_ACCESS_MASTERPLAN_BY_FABLE.md`
(MNZ, chartered 2026-07-18), which built the billing and gating *machinery* and is largely
shipped. MNZ's §2 tier design and §7 pricing are now **superseded by measurement of the live
catalog** — see §1.6. MNZ's rulings MNZ-R1..R12 stand except where §7 of this document names an
amendment. Does not touch the design-system, Agent OS, Evaluation OS, red-team, CI, or
semantic-mapping workstreams.

---

## 0. The one-paragraph answer

Mastermind has built a genuinely large intelligence estate (82 nav-linked desks, 4,655
built pages, a Terminal, a chat brain) and a correct, fail-closed commercial *machine*
(Stripe spine, entitlement table, split-build tier previews). What it does not have is a
**commercial argument**: today an anonymous visitor can read almost the entire estate's
server-rendered content, a Free account adds almost nothing to that, and $99–149/month buys
three desks, a chat lane, and a Terminal feature. The product is not underexposed — it is
**underpriced in reasons, not in dollars**. The fix is not to lock more; it is to make the
paid product a *different kind of thing* (continuous, personal, and timely) rather than a
*larger amount* of the same thing (more pages). This document specifies that architecture.

---

## 1. PART I — The current commercial product, reconstructed from code

### 1.1 The catalog is the authority, and it is small

`config/plans.yml` is the single source of truth for products, prices, features, and offers,
read by `app/billing.py::_catalog()` and by both plans-page builders
(`scripts/build_site.py::_plans_view_model`, `scripts/build_public_pages.py::plans_view_model`).

| Product | Monthly | Annual | Annual $/mo-equiv | Trial | Features |
|---|---|---|---|---|---|
| **Essential** | $99 | $900 | $75 | **0 days** | `site_full`, `terminal_live_options` |
| **Pro** | $149 | $1,308 | $109 | **7 days** | `site_full`, `terminal_live_options`, `chat_opus` |
| **Founding Pro** (offer) | — | **$900** | $75 | inherits Pro | Pro features, `duration: forever` |

`tier_rank: [free, essential, pro]`. `lib/tiers.py` permanently aliases the legacy string
`insider` → `essential` (rows written before the rename are never back-filled, and
`immutable`-cached JS keeps emitting the old value — the tolerance has no expiry).

**The entire entitlement vocabulary is three feature keys.** Not thirty. Three:
`site_full`, `terminal_live_options`, `chat_opus`. Every commercial decision the system can
currently express is a combination of those three plus a tier string.

### 1.2 Finding A — Essential's annual product has no rational buyer

Essential annual and Founding Pro annual are **the same price to the cent**: 90000
(`config/plans.yml` `products.essential.prices.annual.unit_amount` and
`offers.founding_pro.unit_amount`). Founding Pro is strictly the superior good — every
Essential feature plus `chat_opus`, plus the forever grandfather.

This is *deliberate*, not a bug: the Founding Pro card in `templates/plans.html.j2:490` says
so out loud — "every Pro feature at the Essential annual price". It is the handoff's Option C
(Essential as anchor while Founding Pro is offered at Essential pricing), already implemented.

The consequence, however, is not neutral and does not appear to have been priced in:
**Essential's only live product is the $99 monthly.** Its annual row is dead inventory that
still occupies a third of the pricing page, still gets a Subscribe button, and can still be
bought by a customer who did not read the founder card. Any customer who buys it has made a
strictly dominated purchase on our page. That is a support ticket and a trust cost, not a sale.

The fix is a price, not a withdrawal — `MASTERMIND_PRICING_AND_PACKAGING.md` §2.2. Withdrawal
was the first draft's answer and it is a worse one: both plans builders default a missing
`unit_amount` to `0`, so deleting the price block ships "$0 /mo billed annually" and
"SAVE 100% VS MONTHLY" with a Subscribe button that 400s.

### 1.3 Finding B — the Free/paid boundary is currently almost invisible

Three independent controls decide what a visitor sees. All three were read this session.

1. **`app/regwall.py`** — registration wall. Non-allowlisted *assets* → `401` JSON
   (`{"locked":true,…}`) or `302` for documents. Kill switch `REGWALL_ENABLED`.
2. **`app/paywall.py`** — fail-closed premium wall. Requires the `site_full` entitlement.
   Gated behind `PAYWALL_ENABLED`, which **defaults to `"0"`** (`app/paywall.py::_enabled`)
   and is documented as `PAYWALL_ENABLED=0` in production (`docs/ops/site-access.md:47`).
3. **`config/site_access.yml`** — the path classification. `classify_path()` returns
   `public | free | premium | deny`; unknown is always premium.

The 2026-08-04 operator change removed the `@reg_html` matchers, so **every `*.html` shell is
now public to anonymous visitors**. The file states the doctrine plainly: *"The paid product is
the PAYLOAD, not the page."*

What is therefore actually gated **today**, with `PAYWALL_ENABLED=0`:

- `premium.enforced_early` — `/premiumdata/`, `/capital-structure-data/`,
  `/allocationdata/special_situations.json`, `/chinaspecialdata/special.json`. These 403 for
  anonymous **and Free** regardless of the switch. In practice this is **three desks**
  (Special Situations, China Special Situations, ETFs — `config.yml` `gated: true` at
  lines 1767, 6818, 6834) plus Capital Structure.
- Per-ticker `<market>stockdata/*.json` and every other undeclared data path — but only to
  the extent the *registration* wall covers them. These are Free-inclusive.

**So the current commercial ladder is:**

| | Anonymous | Free (registered) | Essential $99 | Pro $149 |
|---|---|---|---|---|
| Every `*.html` shell | ✓ | ✓ | ✓ | ✓ |
| Server-rendered page content | ✓ | ✓ | ✓ | ✓ |
| Ranked-board preview rows | 1 | 3 | full | full |
| Non-public data assets (JSON/JS) | ✗ (401) | ✓ | ✓ | ✓ |
| 3 gated desks + capital structure | ✗ | ✗ | ✓ | ✓ |
| Terminal live options | ✗ | ✗ | ✓ | ✓ |
| Fast chat | ✗ (off) | 5 / week | 300 / month | uncapped* |
| Deep chat (Opus / GPT-5.6) | ✗ | ✗ | 10 / month | 150 / month |

\* `config/brain.yml` `quotas.pro.fast.limit: -1` — uncapped by operator ruling 2026-07-28, with
`token_ceilings.fast` (5M tokens/month) as the fair-use backstop rather than a request cap.

The Free→Essential step is **three desks, a Terminal feature, and a chat quota bump.** For $99
a month. That is the central commercial problem, and it is a *packaging* problem, not a
pricing problem.

### 1.4 Finding C — five concrete inconsistencies between what we say and what we do

Each was traced to a line; none is a security issue (that stream is separate).

| # | Claim (customer-facing) | Code reality | Severity |
|---|---|---|---|
| C1 | Plans page quotas are hand-typed literals: "5 quick questions a week", "300 a month", "unlimited", "150 a month", plus four comparison-matrix cells (`templates/plans.html.j2:428, 456, 495, 496, 590-598`) | Every one of them is **correct today** — including "unlimited", which is the honest rendering of `config/brain.yml quotas.pro.fast.limit: -1`, the uncapped sentinel documented in `brain_gateway._get_allowance` and set by operator ruling 2026-07-28. But **nothing binds them.** Reprice the lane tomorrow and the page keeps its old promise, silently | **Latent, not live.** Same shape as the price-drift the derivation rule already prevents. Closed in this PR — see §8 |
| C2 | Plans page: "All **31** advanced indicator modules — all five suites" (Pro), 15 (Essential), 1 (Free), driven by `config/plans.yml terminal_indicators.access` | **The ladder IS enforced, and the counts match exactly.** `terminal/lib/suites/*` carries a per-module `tier`: 1 `free` (`trend/candlePainter.ts`), 14 `essential`, 16 `pro` — cumulative **1 / 15 / 31**. Three independent points enforce it against the tier resolved from macro-api `/api/me`: the renderer drops non-entitled modules, the picker locks their rows, the toggle refuses to enable them. `config/plans.yml:33` states the binding out loud | **No defect. Retracted** — see §13. The surviving caveat is narrower: enforcement is **client-side only** (no server recheck, and a `mm.devTier` localStorage override exists), so it is a product ladder, not a security boundary |
| C3 | Essential and Pro both advertise `terminal_live_options` and both are "paid"; the Terminal's Pine-script save gate, alerts gate and scripts page use `isPaidTier()` (any paid tier) | So Essential and Pro are *identical* in the Terminal except for the unenforced indicator count. `isProTier()` exists but is used by nothing outside alerts | Essential↔Pro differentiation is thinner than the page implies |
| C4 | `mastermind:portfolio_desk` is docstringed as "session-auth-gated" (`app/web.py:2299-2303`) | `app/auth.py:11-13`: the browser login "has been REMOVED … requires NO login anywhere". The page is anonymous to anyone with the URL (`research/PRODUCT_PAGE_CENSUS_2026-08.md` §5.1) | A P0 surface documented as gated is open |
| C5 | `scripts/check_hub_a11y.py:45` asserts the Brain launcher mounts "on EVERY page" | **Fixed on main the same day this was written** (#5409/#5463): `/mm_brain.js` is now in `config/site_access.yml` `public.exact`, so the launcher mounts for anonymous visitors on every root-level page. Two gaps survive: the **SEO subtrees** are still uncovered (the injector uses a document-relative `src`), and the **guest lane is still default-OFF** (`brain_gateway._GUEST_CFG_DEFAULT`), so the launcher opens and the first question 402s | **Half-resolved.** The script is now reachable; the *capability* is still switched off. See W1-2 |

| C6 | `config/site_access.yml` `premium.enforced_early` promises `/premiumdata/*` will "403 for anonymous AND Free" | **Two ordering/exposure defects.** (a) `app/paywall.py:364-365` returns `204` for anything classified `free` **before** `enforced_early(path)` is ever consulted — so adding a premium path to `free_registered` silently un-gates it, with no test covering the interaction. (b) The repository is **PUBLIC** (`gh repo view` → PUBLIC) and all six payloads are git-tracked, so they are downloadable today with no session, from GitHub and from the nightly Pages mirror | **The enforced_early boundary is decorative today.** This is a hard predecessor to charging money — see §10 and the implementation plan's critical path |

C5 compounds with a second fact: anonymous chat is **default OFF**
(`brain_gateway._GUEST_CFG_DEFAULT = {"enabled": False, "daily_limit": 30}`). So even if the
script loaded, the guest lane is closed. A visitor arriving from X today cannot ask Mastermind
a single question.

### 1.5 Finding D — the paywall switch is binary and estate-wide

`PAYWALL_ENABLED=1` makes **every** path not named in `public` or `free_registered` require
`site_full`. There is no middle setting. Today Free sees nearly everything; the day the switch
flips, Free collapses to "public shells with no data" — because `free_registered` lists exactly
**11 exact paths and 3 prefixes** (`/news/`, `/chinanews/`, `/macrodata/`).

This is the most important structural fact in the whole system: **there is currently no
configuration of Mastermind in which Free is a real product.** It is either almost-everything
or almost-nothing. Every recommendation in §5 depends on fixing that first, and the fix is
cheap: `free_registered` is a list in a YAML file that `app/paywall.py::_load_config` already
validates and mtime-caches.

### 1.6 Finding E — the chartered masterplan has drifted from the shipped product

`research/MONETIZATION_ACCESS_MASTERPLAN_BY_FABLE.md` (2026-07-18, Amendment 1) ratified
Insider $59/mo · $49/mo annual and Pro $89/mo · $69/mo annual. The live catalog is
$99/$75 and $149/$109 — **+53% and +58% on the ratified annual per-month rates** ($75/$49 and
$109/$69), unrecorded in that document. Its §2.2 free/paid split by page family ("Free: index, macro, news, methodology, one
sample report") was also overtaken by the 2026-08-04 all-HTML-public change.

This matters beyond bookkeeping: the masterplan is what a new session reads to learn the
commercial model, and it currently teaches a model we do not sell. §7 of this document
records the amendment.

### 1.7 What already works, and works well

It would be wrong to read the above as "the commercial system is broken". The *machine* is in
good shape and several parts are better than what most companies ship:

- **Fail-closed enforcement with a documented staleness bound.** `app/paywall.py` verifies the
  token fresh (≤60s cache), reads the entitlement store, and denies on any error, with a
  24h grace confined to *store outages only*.
- **The split-build tier-preview pattern** (`docs/TIER_PREVIEW_PATTERN.md`) — the shipped bytes
  differ, so nothing is hidden with CSS. It also encodes the right product instinct:
  *preview newest-first, never best-first*, because previewing a ranked board hands over its head.
- **Honest totals as the free give.** The pattern's rule that "a count names nobody, while the
  member rows are the product" is exactly the right line, and it is already law.
- **Cross-repo entitlement with one authority.** The Terminal resolves entitlement against
  macro-api `/api/me`, explicitly *not* against a `profiles.is_pro` UI hint, fail-closed, with a
  positive-only 45s cache. This is a well-reasoned piece of engineering.
- **The founder allotment is genuinely enforced, not cosmetic.** `app/billing.py:314-425` —
  reserved seats reduce `remaining`, and every checkout path gates on it. The payload discloses
  `claimed` and `reserved` separately. Credit where it is due: this is an honest scarcity
  *mechanism*. §5 of `MASTERMIND_PRICING_AND_PACKAGING.md` argues its *rationale* still needs work.
- **The anonymous watchlist works as of 2026-08-12, and its state transfers.**
  `templates/watchlist.js` is pure client state in `localStorage`; `templates/watchstore.js`
  folds it into the cloud on first sign-in via a one-time `mdash.watchstore.folded.v1` marker,
  inserting only missing tickers (merge, not overwrite). Until that morning every one of the
  page's ten scripts was default-deny and anonymous production served a cached husk; #5463
  promoted the five that make up the funnel shell (`watchlist.js`, `watchstore.js`,
  `market_books.js`, `portfolio.js`, `mtf.js`).
  **The half that is deliberately still closed is the half that makes it Mastermind.**
  `stockdata.js` stays gated because the page's `data_base` shim would otherwise render graded
  per-ticker output — conviction band, ladder state, entry urgency — to signed-out visitors;
  and `watchlist_risk.js` / `risk_core.js` / `factor_exposure.js` stay gated because they *are*
  the calibrated decision rule in code form. So today an anonymous visitor can build a list and
  see it persist, and Mastermind says nothing about it. Closing that gap is a deliberate
  disclosure decision (§4.1), not a husk fix.

---

## 2. PART II — The user types

Four personas. Not marketing archetypes — each is defined by the *decision* they are trying to
make, and each maps to a distinct entitlement need.

### P1 — The Arriver (anonymous, from X or search)
**Job:** confirm in under a minute that this is not another dashboard.
**Strongest hook:** a specific, checkable claim about *today* with the work shown — "silver
miners just entered the #1 flow-velocity cohort, here is the cohort, here is how it is computed,
here is what it did the last four times."
**Activation event:** interacts with something (types a ticker, asks a question, opens evidence)
rather than scrolling.
**Willingness to pay:** zero, now. Their entire value is as an input to P2/P3.
**Churn reason:** the page renders and says nothing they could not get from a free screener.

### P2 — The Operator (active trader; the Terminal's natural user)
**Job:** decide what to do today, and not miss the thing that changed overnight.
**Highest-value features:** Terminal + live options flow, alerts, Prophet's live board with
timing state, intraday flow, GEX, watchlist deltas.
**Activation event:** sets up a watchlist and returns the next market morning to check it.
**Willingness to pay:** high — $100–200/mo is inside the band they already spend on Benzinga
Pro / Unusual Whales / TradingView Premium — **conditional on timeliness**. They will not pay
for a nightly product that tells them at 06:00 what they needed at 14:30.
**Churn reason:** signals arrive too late to act on; or a stretch of not trading.

### P3 — The Allocator (serious investor, multi-week to multi-quarter horizon)
**Job:** understand the regime, find and hold themes, and see risk they cannot see position-by-position.
**Highest-value features:** macro/regime, theme intelligence, sector & subsector rotation,
fundamental forensics, capital structure, research reports, portfolio concentration risk.
**Activation event:** builds a portfolio (or a watchlist that behaves like one) and opens the
evidence behind one holding's read.
**Willingness to pay:** high and *stickier* than P2 — this is a research-budget purchase, and
annual is natural. This persona is the one Mastermind's nightly-compute architecture actually
fits best, and it is currently under-served by the packaging.
**Churn reason:** cannot tell whether the intelligence was right; feels like reading, not deciding.

### P4 — The Builder (power user; a small, loud minority)
**Job:** everything, plus their own work on top — Pine scripts, custom indicators, exports, API.
**Willingness to pay:** highest, and they generate disproportionate word-of-mouth.
**Churn reason:** hits a ceiling we will not raise (no export, no API, no data download).

**The Curious Free user is not a fifth persona.** They are P2 or P3 who has not yet been shown
the thing that matters to them. Treating them as their own segment is how a Free tier becomes
a parking lot instead of a funnel.

**Segmentation consequence for packaging:** the only *real* split in this set is
**P3 (research, nightly is fine) vs P2 (execution, timeliness is the product)**. That, and not
"a bigger bundle", is what a two-paid-tier architecture must encode. See §5.2.

---

## 3. PART III — The product value hierarchy

Ranked by conversion potential, not by engineering difficulty. Assessed against the surfaces
that exist (`templates/_navlinks.html.j2` — 80 nav-linked pages).

### Tier 1 — the "holy shit" surfaces (acquisition + conversion)
1. **The Mastermind chat brain, grounded in the live market packet.** Ask a real question about
   a real ticker and get an answer that cites the site's own artifacts. Nothing else in the
   product is this immediately legible to a stranger. Its script became
   anonymous-reachable on 2026-08-12 (#5409/#5463), but the **guest lane is still switched
   off**, so a stranger can open the launcher and cannot ask a question. Turning it on is the
   single highest-leverage change in this document (Finding C5, W1-2).
2. **Prophet with its graded history.** A board that shows what it said *before* it worked, with
   receipts. `site/prophet/showcase.json` already ships a public delayed-winners teaser
   (`scripts/build_prophet.py:18-21`). This is our best proof asset and it is used only as
   landing garnish.
3. **A ticker page that answers "what is going on with X" in one screen** across macro, sector,
   flow, options, fundamentals, and the graded read. This is the cross-domain synthesis nobody
   else can assemble, and it is the natural landing target for every social post.

### Tier 2 — activation surfaces (make the user understand)
4. **Watchlist with the full signal stack attached.** The moment a user's *own* tickers get read,
   the product stops being a website. Already built, already anonymous-capable.
5. **Risk Radar / regime state.** Compresses "what kind of market is this" into one honest read.
6. **Flow Velocity + theme intelligence.** The most *shareable* outputs — a cohort ranking is a
   screenshot-able, argument-starting artifact.

### Tier 3 — retention surfaces (bring them back)
7. **"What changed overnight" for the things I own.** Does not exist as a surface. §6.
8. **Prophet entries/exits.** A daily state change with a name attached.
9. **Catalyst calendar / earnings intelligence / BioCatalyst.** Forward-dated reasons to return.

### Tier 4 — prestige surfaces (perceived sophistication; low usage)
10. Neural Web, Calibration Lab / measurement, Market Memory, methodology pages, Committee.
    These *earn trust* and should be visible and free. They will not convert anyone on their own,
    and should not be counted on to.

### Tier 5 — power-user surfaces (narrow, high value, low volume)
11. Pine scripts, custom indicators, capital structure, filing forensics, issue desk, exports.

### The uncomfortable conclusion
**We have been treating all ~80 desks as commercially equivalent, and they are not.** A large
majority of the estate is Tier-4-shaped: real work, real quality, near-zero conversion or
retention contribution *as currently surfaced*. The commercial architecture should stop trying
to sell "all of it" and start selling the three things in Tier 1 plus the loop in Tier 3.
The rest is credibility, breadth, and SEO — valuable, but not the offer.

---

## 4. PARTS IV–VI — Anonymous, registration, and Free

Full per-feature detail is in `MASTERMIND_ENTITLEMENT_MATRIX.md`. The principles:

### 4.1 What anonymous gets, and why
**Principle: anonymous gets everything that is about the MARKET; registration begins where it
becomes about YOU.** That line is honest, explicable in one sentence, defensible against
"why is this locked", and it happens to align with what we can afford to serve.

Anonymous receives, live and interactive:
- The whole-market read: macro, regime, heatmaps, breadth, sector/subsector strength, themes.
  (Mostly already public.) *This is market data and our reading of it, not a personal service.*
- **A working chat brain, 3 questions/day per visitor.** The client is now reachable; the lane
  is not. `_guest_cfg` defaults to `{enabled: False}` and the quota files keyed by `mm_aid`
  cookie and IP hash already exist. This is the change with the highest ratio of impact to
  effort in the entire program — and it is not free: see the cost caveats in
  `MASTERMIND_ENTITLEMENT_MATRIX.md` §7 before turning it on.
- **A working watchlist, up to 5 symbols, in localStorage** — shipped 2026-08-12.
- **A read on those 5 symbols.** *Not shipped, and deliberately so.* The renderers that would
  attach the signal stack are the calibrated decision rule in code form. Giving anonymous
  visitors a read therefore needs a disclosure decision about **what** we say, not a boundary
  change: the recommendation here is a **regime-and-context read with no graded per-ticker
  claim** — what kind of market these five names are in and what they share — which is exactly
  the line `stockdata.js` is held behind.
- Prophet's **graded history** and a delayed showcase — proof, not the live board.
- One row of every ranked board (the existing `tier_preview.js` anon cap of 1).
- Three full ticker pages per day, then a soft wall.

Anonymous does **not** receive: the live ranked boards' heads, per-ticker graded emits at scale,
continuous monitoring, anything that persists, or anything with a real marginal cost per call
beyond the daily caps.

**Abuse/cost check.** The three genuinely metered things (chat, ticker pages, board rows) all
already have server-side quota machinery keyed on the httpOnly `mm_aid` cookie plus an IP hash
(`brain_gateway._guest_cookie_quota_file` / `_guest_ip_quota_file`). Scraping risk is
concentrated in the per-ticker store, which stays gated. No recommendation here depends on a
surface whose licensing we have not verified — see `MASTERMIND_ENTITLEMENT_MATRIX.md` §7.

### 4.2 Why an anonymous user should register — the four reasons
Not "sign up to continue". Four *specific* promises, each of which is true and each of which
maps to a built capability:
1. **"Keep this watchlist."** They just built one. It is in their browser and will die there.
   `watchstore.js` already folds it into the account on first sign-in.
2. **"Get told when it changes."** Continuous monitoring is the thing a session cannot give.
3. **"See three rows instead of one"** on every board (existing `tier_preview` cap).
4. **"Keep asking."** 3/day anonymous → 5/week signed-in is *not* an upgrade. Free must get a
   materially better chat allowance than anonymous or the registration trade is a downgrade.
   Recommendation: **20 fast questions/week for Free.**

### 4.3 Free as a real product
Free must be a **daily habit with a visible ceiling**, not a crippled trial. Its shape:

- **Full breadth, limited depth.** Every page reachable; the *bottom* of each page is where
  the ceiling sits. This is the inverse of most freemium ladders and it is right for us,
  because breadth is our credibility and depth is our cost.
- **Four limits a user can hold in their head** — and only four:
  1. **1 watchlist, 15 symbols.**
  2. **3 rows** of any ranked board (already implemented).
  3. **20 chat questions a week**, fast lane only.
  4. **7 days of history** on any time series or board state; paid gets full history.
- Plus: the daily brief in *weekly* form, and 1 research report per month.

Everything else Free gets in full: macro, regime, heatmaps, methodology, calibration, Prophet's
graded track record, ticker pages (unlimited), Terminal charting (free for everyone by
operator ruling MNZ-OD4), watchlist sync.

**What Free must NOT get, and why:** the live head of any ranked board (that is the product),
continuous alerting (that is the paid promise), the deep chat lane (real marginal cost), live
options (real data cost), full history (cheap to serve, but it is the single clearest
"there is more here" signal we own).

---

## 5. PART VII, VIII, XXXI — Tier architecture: three options and a verdict

### 5.1 The three viable architectures

**Architecture 1 — "Two doors."** Free → Pro. Kill Essential.
*For:* the simplest possible story; every dollar of attention goes into one conversion; no
"which one do I need" friction. *Against:* loses the $99 entry point and the anchor, and forces
a $149 first purchase on P3 — a research buyer who does not need live options at all.

**Architecture 2 — "Research vs Execution."** Free → Essential → Pro, split by *what the tier
is for*, not by how much of it you get.
- **Essential — the research desk.** Everything the engines compute overnight: all dashboards,
  all desks, all research, full history, full ranked boards, portfolio & concentration
  intelligence, fast chat, the daily brief. For P3, the Allocator.
- **Pro — the execution layer.** Essential plus everything whose value is *timeliness or
  compute*: Terminal live options, real-time alerts, intraday flow, the deep chat lane
  (Opus/GPT-5.6), the advanced indicator suites, exports/API. For P2 and P4.
*For:* the split maps to two personas that genuinely exist, and to the two capabilities with
genuine marginal cost (live options data, frontier-model tokens). Each tier answers "who is this
for" in one sentence. *Against:* requires actually building/enforcing the Pro side — today
`terminal_indicators` is unenforced (C2) and alerts use `isPaidTier()` not `isProTier()` (C3).

**Architecture 3 — "Anchor + founder" (status quo).** Essential exists mainly to make Pro look
reasonable; Founding Pro is sold at Essential's annual price.
*For:* zero work; already shipped. *Against:* Essential annual is a dominated product on our own
pricing page (Finding A); and the moment the founder window closes, we are left with
Architecture 2's problem and none of its preparation.

### 5.2 Verdict — **Architecture 2, staged through the founder window.**

**Recommendation: adopt Research vs Execution as the target architecture. Until the founder
window closes, run it in the Architecture-3 posture the catalog already implements — but stop
selling Essential annual.**

Why Architecture 2 wins: it is the only one of the three where each tier can answer *who is this
for* without referring to the other. Architecture 1's simplicity is real but it prices out the
persona our nightly-compute product serves best. Architecture 3 is not an architecture; it is a
launch tactic, and it expires.

**The single condition that would flip me to Architecture 1:** if, 60 days after launch,
Essential is under 15% of new paid subscriptions *and* the Essential→Pro upgrade rate is under
10%, Essential is not a segment — it is a discount, and it should be deleted rather than
defended. That test is pre-registered in `MASTERMIND_PRICING_AND_PACKAGING.md` §7, **together
with the four conditions that have to hold for it to mean anything** — including one event
(`subscription.tier_changed`) that does not exist yet, without which the second criterion is
simply unmeasurable.

**Immediate correction, independent of the architecture choice:** reprice Essential annual
$900 → $828 ($69/mo-equivalent). That removes the dominance by moving one number, rather than by
withdrawing a product — which turns out to matter, because withdrawing it is a code change, not
a config edit (§8). Selling a customer a strictly worse product at an identical price is a
defect regardless of which tier ladder we end up with; selling them a smaller product at a
genuinely smaller price is just a ladder.

### 5.3 The packaging vocabulary problem (PART XXXI)

Ordinary users must never meet the names of 40 internal engines. But renaming the product is not
the fix and is explicitly out of scope. The fix is a **presentation grouping** that the
navigation and the plans page share — five verbs, each of which is a user job:

| Group | Question it answers | Example surfaces |
|---|---|---|
| **Read** | What kind of market is this? | macro, regime, risk radar, heatmaps, breadth |
| **Find** | What should I be looking at? | Prophet, flow velocity, themes, screeners, special situations |
| **Understand** | Why is this happening? | ticker pages, forensics, capital structure, earnings, chat |
| **Watch** | What changed for *my* things? | watchlist, portfolio, alerts, daily brief |
| **Prove** | Was it right? | track record, calibration lab, methodology, receipts |

This grouping is a **commercial** artifact: it is how the entitlement matrix, the plans page
comparison, and the upgrade copy should all be organized, so that a customer learns one mental
model and meets it everywhere. Final visual execution belongs to the design-system workstream.
**"Prove" is free at every tier, always** — it is the trust surface, and charging for the
evidence that we were right is how a research product becomes a signal-seller.

### 5.4 PART VIII — why someone pays, ranked

The real hierarchy for *this* product, in order:

1. **Continuity.** The engines run every night whether you opened the app or not. Free gives you
   a snapshot; paid gives you a *process that does not stop*. This is the honest core of the
   offer and it should lead every upgrade surface.
2. **Compression.** The whole market, read overnight, in the time it takes to drink coffee.
3. **Risk you cannot see position-by-position.** Concentration, correlated downside, factor
   overlap across holdings. This is the most under-sold capability in the estate.
4. **Timing.** When conditions become actionable — Pro's half of the split.
5. **Discovery.** Names and cohorts you would not have found.
6. **Interpretation.** Not "we have AI" — "we show the work, including where the work says
   nothing." Our printed-nulls discipline is a genuine differentiator; see §9.

Note what is *not* on this list: "more pages". Breadth is a credibility asset, not a reason to
pay. Every upgrade message that reduces to "unlock 40 more dashboards" is wasting the moment.

---

## 6. Activation, time-to-value, and the retention loop (summary)

Full specification in `MASTERMIND_ACTIVATION_AND_FUNNEL.md`. The three headline definitions:

**Primary activation event** — a Free account is ACTIVATED when, within 7 days of first visit,
all three hold:
1. a **saved watchlist with ≥3 symbols**, and
2. a **return visit on a second distinct calendar day**, and
3. at least one **evidence open** — a receipt, an evidence drawer, a Prophet card detail, or a
   chat answer received.

Rationale: (1) proves personalization exists, (2) proves habit, (3) proves they understood that
this is an evidence product rather than a signal feed. Each is independently instrumentable with
events we do not currently emit (see §8 and the instrumentation spec).

**Primary upgrade trigger** — the *third* encounter with the same ceiling within 14 days.
Not the first: the first is information ("there is more here"). The third is intent ("I keep
wanting this"). The upgrade message names the specific thing they were reaching for.

**Primary retention loop** — **"Since you were last here."** A per-user diff, computed nightly,
over their watchlist/portfolio and the boards they follow: what entered, what exited, what
deteriorated, what is coming. It is the first thing on the dashboard when they return, and it is
the body of the daily brief. This is the one genuinely new surface this architecture requires,
and it is the difference between a site people visit and a product people open.

---

## 7. Amendments to the MNZ masterplan

Recorded so a future session reading MNZ does not learn a model we do not sell.

| Amendment | Change |
|---|---|
| **MNZ-A3** (pricing) | MNZ §2.1/OD1's ratified prices (Insider $59/$49, Pro $89/$69) are **superseded** by `config/plans.yml` as of this document: Essential $99/mo · $900/yr; Pro $149/mo · $1,308/yr; Founding Pro $900/yr forever. `config/plans.yml` is the sole authority; MNZ §2.1 is historical. |
| **MNZ-A4** (page gating) | MNZ §2.2's free/paid split by *page family* is superseded by the 2026-08-04 all-HTML-public ruling recorded in `config/site_access.yml`. The boundary is the **payload**, not the page. MNZ-R8 (tier assignments live in a manifest) survives in the form of `config/site_access.yml` + `config.yml` per-desk `gated:` switches. |
| **MNZ-A5** (Free tier) | MNZ's Free tier ("glance tier: macro, index, news, methodology, one sample report") is superseded by §4.3 above: Free is **full breadth, limited depth**, with four legible limits. Requires `free_registered` in `config/site_access.yml` to grow from 11 entries to the set in the entitlement matrix **before** `PAYWALL_ENABLED=1`. |
| **MNZ-A6** (trial) | MNZ-R9 (card-required 7-day, Stripe-native) **stands**. Added, not replacing: a once-per-account, no-card **72-hour Pro Day Pass** granted on the third paid-ceiling encounter (post-launch, Wave 2). |
| **MNZ-R13** (new) | **Every customer-facing quantitative claim about an entitlement must be derived from the config that enforces it.** Prices already obey this (`_plans_view_model`); quotas and indicator counts did not. Implemented for chat quotas in this PR; `terminal_indicators` remains a claim without an enforcer until the Terminal lane lands (C2). |

---

## 8. What ships in this PR (foundational only)

The handoff permits implementation only where the architecture is no longer ambiguous. Two
changes qualify; everything else is specification.

1. **`config/growth_events.yml` + `tests/test_growth_events_registry.py`** — the canonical
   analytics event registry (names, required properties, funnel membership). Pure addition; no
   runtime behavior. It exists so that the six implementation waves emit *one* vocabulary
   instead of six.
2. **Chat-allowance derivation (C1).** `lib/chat_allowance.py` derives every chat number on the
   plans page from `config/brain.yml` — the same file `brain_gateway._get_allowance` enforces —
   exactly as prices are already derived from `config/plans.yml`. **The rendered page is
   unchanged**, because the literals were correct; what changes is that they can no longer drift
   silently. `-1` renders as "Unlimited" and `0` renders as ✗, so the two sentinels stay legible.
   The literals on the hand-authored landing (`templates/index.html:783, 832`) and the onboarding
   sheet (`templates/onboard.js:267, 407`) cannot be derived at build time, so they are instead
   **pinned to the same config by test** — a literal a test binds to its enforcer is safe; an
   unbound one is not. All of it is covered by `tests/test_plans_chat_quota_truth.py`.

Deliberately **not** shipped here: any change to tier membership, price, `free_registered`, or
the `PAYWALL_ENABLED` posture. Each is an operator decision this document exists to inform.

**One correction to an earlier draft of this section:** withdrawing Essential annual is *not* a
one-line config change. Deleting `products.essential.prices.annual` makes both plans builders
emit `annual_pm=0`, `annual_total=0`, `save_pct=100` (the `int(prices.get("annual", {}).get(
"unit_amount", 0))` default swallows the absence), which the template renders verbatim as
"$0 /mo billed annually", "Billed $0 a year" and "SAVE 100% VS MONTHLY", with a live Subscribe
button whose checkout then 400s because `_tier_to_lookup_key('essential','annual')` returns
`None`. Withdrawing a price needs a template branch and a builder that raises on a missing
price rather than defaulting it to zero — see the implementation plan, W6-1.

---

## 9. PART XXXV/XXXVI — Positioning and trust

### The category
Mastermind is not a screener, a charting tool, a newsletter, or an AI stock picker. It is
**a market intelligence operating system**: one system that reads the entire market every night
— macro through options — and hands an individual investor the read, the evidence, and the
change since yesterday.

The positioning line that follows from what we actually built:

> **The whole market, read every night. With the work shown — including where the work says nothing.**

That last clause is the defensible part. Our epistemics law already forbids the things every
competitor does: LLMs may not originate signals or scores; nulls are printed rather than hidden;
"validated" is CI-enforced in user-facing text (`scripts/check_validated_claims.py`); a display-
tier signal may never be presented as authority. **No competitor can copy printed nulls without
changing what their product is for.** It should therefore be a front-of-house claim, not an
internal discipline.

### The trust mechanisms, and one warning
Already built and under-used: graded track record, receipts, transparent timestamps, the
Calibration Lab, methodology pages, coverage abstention.

The warning: trust is also what Findings C2–C5 spend. An indicator ladder we advertise in detail
and enforce nowhere is the same category of error as a signal we cannot defend — it is just
aimed at the wallet instead of the portfolio. Fix them before launch, not after. C1 is closed in
this PR; the rest are Wave 1 in the implementation plan.

Coordination note: every performance claim on a commercial surface must clear the Evaluation OS
before it ships. This document proposes no performance claim that is not already computed and
graded in-product.

---

## 10. PART XXXVII — Launch scope

**A smaller coherent launch will outperform a larger confusing one, and the estate is large
enough that this is not a close call.**

### Launch-critical (must be excellent — 12 surfaces)
Landing · plans · onboarding sheet · macro/regime read · ticker page · watchlist ·
Prophet (board + graded history) · chat (all three tiers incl. guest) · one flagship theme/flow
surface · the daily brief · account/billing · support.

### Supporting (must be correct and honest, not flagship)
The sector/subsector families, heatmaps, research vault, forensics, capital structure,
earnings intelligence, special situations, ETFs, the China/HK/Canada/International families.

### Beta-labelled
BioCatalyst, Neural Web, Market Memory, Issue Desk, Pine/scripts, alt data, Foresight.

### Hidden at launch (dilute the product; return when they have an owner)
The 63 nav-orphaned macro routes identified in `research/PRODUCT_PAGE_CENSUS_2026-08.md` §4,
the four `deny`-class pages still being built and committed (§5.6 there), and any surface that
renders a styled-but-empty state for its default visitor.

**Rule:** a surface that cannot answer "who is this for and what do they do next" does not
appear in navigation at launch. It can still exist, be indexed, and be linked from search.

---

## 11. PART XXXVIII/XXXIX — The first 30 days and the CEO dashboard

Detailed in `MASTERMIND_GROWTH_INSTRUMENTATION_SPEC.md`. In brief:

**Day 1:** does the funnel emit? Do visitors interact before registering (target: >25% of
sessions produce an interaction event)? Any checkout error?
**Week 1:** visit→interaction, interaction→registration, registration→activation, and the
single largest drop-off, named. Founder redemption pace vs the allotment.
**Month 1:** activation→paid, D7/D30 retention by tier and by acquisition source, the feature
most associated with conversion, and the Essential-vs-Pro test in §5.2.

The CEO report is **nine numbers and one sentence**, weekly:
qualified visitors · % who experienced intelligence · registrations · activations ·
paid conversions · MRR/ARR + cash collected · D1/D7/D30 · top feature-to-conversion correlation ·
**the largest funnel leak, stated in words.**

---

## 12. FINAL CEO ANSWER — the trader who clicks a link on X

> *A trader sees a Mastermind post on X, clicks the link, has never heard of us, and lands on the
> product.*

### Second 0 — where they land
They do **not** land on the homepage and they do **not** land on `/pricing`. The post was about
something specific, so the link goes to the surface that proves it — say
`/flow_velocity.html?cohort=silver_miners&utm=...`. Above the fold, without any JavaScript
having to succeed: the claim from the post, the cohort, the ranking, the date, and one line of
plain words saying what it means. No modal. No cookie wall. No "sign up to continue".

### Seconds 5–30 — the first useful intelligence
They scroll and the evidence is *there*: how the cohort is computed, what it did the last four
times this happened, and the honest caveat where one exists. One row of the ranked board is
visible; the rest shows an honest locked slot that says **how many** rows there are and **what
kind** of thing they are — never a blur.

At the bottom right, the Mastermind chat launcher is mounted and **working** — because
`mm_brain.js` is public and the guest lane is on. It is pre-seeded with one question about the
thing they are looking at: *"Why did silver miners move to the top of this cohort?"*

### Seconds 30–90 — the first personal act
They ask their question. They get an answer with links back into the page. That is one of their
three free questions today.

Then the surface does the thing that makes this a product instead of an article: an inline
prompt, in the flow of the page, that says **"add three tickers you actually hold"** — with the
cohort's own names as one-tap suggestions. They add three. The page immediately reads *their*
three: the regime they are in, the signal state on each, and one line about what the three have
in common. Nothing has been asked of them yet.

### Minutes 2–5 — the account, earned
They now own something. The prompt is not "sign up to continue"; it is:

> **Keep this list — and get told when it changes.** Your three names are saved in this browser
> only. Create a free account to keep them, watch them every night, and see three rows of every
> board instead of one.

One field, one button, Google-or-email. `watchstore.js` folds the local list into the account on
first sign-in — nothing is retyped and nothing is lost. Preferences (market focus, trader vs
investor, theme) are two taps and **skippable**; the product infers the rest from behavior.
Total elapsed: under five minutes, and they saw intelligence before they saw a form.

### Day 0 → Day 1 — activation
Before they leave, one line sets the return: *"We read your list again tonight. Come back
tomorrow morning and we'll show you what changed."* — plus an optional email for the weekly
brief. That is the whole retention promise, and it is true.

Next morning they open Mastermind (or the brief) and the **first thing on the page is "Since you
were last here"**: one of their three names changed state, one theme they touched accelerated,
one risk deteriorated. They open the evidence on one of them. **They are now activated** —
watchlist ≥3, second distinct day, evidence opened.

### Days 3–10 — the first upgrade moment
It arrives on the *third* time they hit the same ceiling, and it names what they were reaching
for. Not "Upgrade to Pro." This:

> **Your three semiconductor positions are driven by one factor.**
> You've opened the concentration view three times this week. Mastermind Essential watches
> correlated downside across everything you hold, every night, and tells you when the overlap
> gets dangerous. **See it on your list →**

Beside it: *"or try everything free for 7 days"* — Pro's existing card-required trial.

### The first paid session
They land on a page that is **already theirs**: the boards open at full depth, their watchlist
carries the full stack, the concentration read they were reaching for is rendered, and a single
"what you just unlocked" strip names the three things that are new *for them* — not a feature
list. Time from payment to the first thing they wanted: zero clicks.

### Why they open Mastermind tomorrow
Because overnight, something in *their* list changed, and Mastermind is the only place that will
tell them what and why — with the work shown. That is the whole loop, and everything else in
this document exists to serve it.

---

### What we are currently doing that would prevent that journey

Every item is traced, and every one was re-derived against `origin/main` after two same-day PRs
moved the boundary. In order of how early it breaks the story:

1. **The chat opens and cannot answer.** `/mm_brain.js` became public on 2026-08-12, so the
   launcher now mounts — but `brain_gateway._GUEST_CFG_DEFAULT` is `{enabled: False}`, so a
   stranger's first question 402s. *Seconds 30–90 still do not happen.* One operator-editable
   JSON file stands between the current state and the journey working — with the cost caveats
   in the entitlement matrix §7 attached.
2. **The anonymous watchlist saves but says nothing.** The funnel shell shipped the same day;
   the renderers that attach the read did not, deliberately (`stockdata.js` and the three
   decision-rule modules stay gated). *Minutes 2–5 produce a list, not intelligence* — and
   "Mastermind immediately analyzes it" is the step the journey turns on.
3. **Nothing invites a visitor to build one.** The capability is now reachable and is still not
   a funnel: no surface outside `watchlist.html` prompts it, and `watchlist.html` is a nav item
   you must already want.
4. **Social links have nowhere good to land.** No campaign-parameterized deep-link contract, no
   per-cohort/per-theme entry route, no share artifacts. *Second 0 is generic.*
5. **"Since you were last here" does not exist.** No per-user overnight diff on any surface.
   *Day 1 has no reason to open.*
6. **No commercial telemetry.** The beacon *accepts* eleven event types and *emits* nine
   (`heartbeat` and `scroll` have no emitter — scroll depth rides as a column on `exit`), and
   **none** of registration, checkout, paywall encounter, upgrade click, or watchlist creation.
   *We could not measure a single step of the journey above even if it worked.*
7. **The contextual upgrade system does not exist.** `tier_preview.js::openUpgrade()` sends
   every user to the same sheet with `plan: "essential"` hardcoded, regardless of what they
   were reaching for. *The upgrade moment is generic exactly where it must be specific.*
8. **Free is not a product.** Today it is "everything minus four desks"; the day
   `PAYWALL_ENABLED=1` it becomes "shells with no data". Neither is the tier in §4.3.
   *There is nothing to be activated into.*
9. **Essential annual is a dominated purchase on our own pricing page** — and withdrawing it is
   a code change, not a config edit (§8).
10. **The paid boundary is not a boundary yet.** The repository is PUBLIC and every
    `enforced_early` payload is git-tracked, so the four files we promise to 403 are one
    `git clone` away — and `app/paywall.py` returns 204 for anything classified `free`
    *before* it consults `enforced_early`, so a well-meant `free_registered` edit can un-gate a
    paid path silently. *Charging money for what is already published is the one failure on
    this list that costs trust rather than conversion.*

Items 1, 3, 6 and 10 are the load-bearing ones; 1 is minutes of operator work, and 10 is the
only one that must be finished before any money changes hands. The sequencing is in
`MASTERMIND_COMMERCIAL_V1_IMPLEMENTATION_PLAN.md`.

---

## 13. Corrections on the record

A 46-agent adversarial pass re-derived every factual claim in these documents from source. It
confirmed 19 defects and refuted 19 more. Three corrections changed a conclusion, not just a
sentence, and are recorded here rather than quietly edited away.

**Retraction 1 — "the plans page falsely promises unlimited chat."** Wrong. I read
`brain_gateway._load_brain_config()`'s hardcoded *fallback* (Pro fast 1000/month) and treated it
as the enforcement. The live `config/brain.yml` sets `quotas.pro.fast.limit: -1`, which
`_get_allowance` documents as uncapped, per an operator ruling of 2026-07-28. The copy is true.
*A module's fallback is not its enforcement.*

**Retraction 2 — "the 1/15/31 indicator ladder is advertised and enforced nowhere."** Wrong, and
worse: I inherited it from `PORTFOLIO_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md:735` without
re-deriving it, and my own search stopped at `indicators.ts` and `IndicatorsModal.tsx` while the
ladder lives in `terminal/lib/suites/*`. It is enforced, at three points, and the counts match
the catalog exactly. *A cited "known gap" is testimony, not observation.*

**Retraction 3 — "the chat never mounts for a stranger."** True when written against a base
commit from that morning; fixed on `main` six hours later by #5409/#5463, along with the
anonymous watchlist husk. *A finding is only as fresh as the base it was derived on — 161
commits landed on main during this session.*

Two smaller corrections: the MNZ price delta is +53%/+58%, not "68–80%"; and the count of
hand-typed chat literals is roughly twenty across five surfaces, not eight across three.

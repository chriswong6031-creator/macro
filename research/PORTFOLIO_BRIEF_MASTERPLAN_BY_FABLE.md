# Portfolio-Aware Intelligence ("Your book, through the desk's eyes") — Masterplan by Fable

**Status:** CHARTERED 2026-07-23 (operator approved the staged approach; this doc is the cold-start handoff).
**Owner lane:** new build session (Opus builds per §Model routing; this plan is the spec).
**Why this exists:** the Pro tier is quantity-differentiated (50 vs 20 Pro AI runs), not capability-differentiated.
Pricing brainstorm 07-23 picked **portfolio-aware intelligence** as Pro's flagship capability pillar. The operator's
constraint: full quant machinery (factor models, optimization, cross-correlation balancing) is too heavy to start —
so the build is staged so V1 ships with *joins, not math*, and V2 adds only the risk numbers we can compute from
data already in this repo.

Before building: read `docs/ACTIVE_BUILD_MAP.md` (regen `python scripts/build_active_build_map.py`) and
`research/DO_NOT_REBUILD.md`. Check nothing here collides with an in-flight lane or a standing kill.

---

## 1. Product definition

A **Pro-only** personalized layer: the user's holdings (Terminal watchlist / portfolio with weights) rewritten
through everything the desks already compute. It converts Mastermind from "a site I read" into "my analyst."

### V1 — composition brief (ship first; no new models)
Deterministic sentences from joins against nightly engine output. Example brief (EN; every surfaced string needs
a zh mirror if it lands on a bilingual page):

> **Your book today.** 41% of your book is semiconductors — today's read is Mixed and the rotation board has
> Semis in *Take profits*, so your effective diversification is thinner than it looks. 2 of your 9 names sit in
> *Buy now* lanes; 1 (NVDA) has its entry gate shut. **3 names report earnings inside 10 days** — AVGO is first
> (Jul 29). This week the filings desks touched 2 of your names: a Congress buy in NVDA, a fund trim in AAPL.

Facts in V1, all pre-existing:
- **Sector/theme exposure** — weighted group-by over holdings (sector from stockdata profiles; theme membership
  from baskets).
- **Rotation-lane placement** — which holdings sit in which plain-word lane (Buy now / Almost ready / Take
  profits / Stand aside), from the baskets/theme_intel lanes.
- **Signal states** — Prophet stage (Bottoming/Turning/Ready/Trend) + entry-gate state per holding.
- **Regime overlay** — the daily read (score/state/stance) + which of the user's sectors it favors/penalizes,
  re-expressing the existing rotation board (no new signal — display-tier re-expression like
  `state_of_themes._classify_lane`).
- **Earnings clock** — days-to-report per holding (alt_data earnings-catalyst-clock channel).
- **Filings touches** — insider/Congress disclosures and 13F adds/trims on the user's names this week.

### V2 — honest risk numbers (second PR; numpy over in-house data, days not months)
From ~250 trading days of daily closes (`data/baskets/ohlcv/*.parquet`, ETFs in `data/yahoo/`):
- Portfolio **beta** vs SPY (cov/var on daily returns).
- **Pairwise correlation matrix** → average intra-book correlation + the tightest pair, surfaced in plain words
  ("your names mostly move together — diversification is thinner than it looks").
- Naive **portfolio volatility** (w'Σw, annualized) vs SPY's, stated as a ratio not a Greek.
- **Concentration** (HHI or top-3 weight share).
- **Historical replay**: the current book's worst 20-day stretch over the lookback ("this exact book would have
  drawn down 18% last April").

Explicitly SKIP in V2: account-level Sharpe (needs the user's trade history we don't have — show per-name risk
contribution instead), covariance shrinkage debates, factor decomposition, stress scenarios, any
optimization/rebalancing output.

### V3 — parked (do NOT build)
Factor models, scenario stress, balancing suggestions. Revisit only after V1/V2 retention data; Bot Portfolios
may subsume it.

---

## 2. Architecture & the cross-repo contract

Two repos are involved:
- **This repo (Macro Dashboard)** computes everything nightly and owns the render budget (~67 min law — nothing
  per-user runs on the render path).
- **mastermind-terminal** (sibling checkout, default branch `master`; the app at app.mastermind-x.com) owns user
  accounts, watchlists, and the existing **Portfolio page** (currently: screens the watchlist for buy signals —
  operator judges it weak; EXTEND this page, do not build a new surface).

**Recommended contract (decide-and-confirm in W0):** the macro nightly bakes ONE compact per-ticker context
artifact — e.g. `site/data/portfolio_ctx.json` (or R2 if >1–2 MB) — keyed by ticker:

```json
{ "asof": "2026-07-23",
  "NVDA": { "sector": "Semiconductors", "themes": ["AI Software", "Mag 7"],
             "lane": "almost_ready", "stage": "Trend", "gate": "shut",
             "earnings_in_days": 34, "filings": [{"kind":"congress_buy","when":"2026-07-21"}],
             "flows_13f": {"adds": 3, "trims": 1} } }
```

The terminal backend (or macro-api) composes the per-user brief **on demand** by joining the user's holdings
against this artifact — cheap, cacheable per day, off the render path. V2 risk stats can be baked the same way
(a per-ticker daily-returns vector file or a precomputed correlation store against a fixed universe), or computed
api-side from a small returns artifact. Per-user computation NEVER runs in the nightly.

Brief composition: **deterministic sentence templates from the joins.** An LLM may only smooth
wording/transitions of already-computed facts (LLM-never-originates law) — V1 is acceptable and arguably better
with no LLM at all.

## 3. Data sources (exact paths in this repo)

| Fact | Source |
|---|---|
| Sector per ticker | `site/stockdata/<T>/profile` payloads (has sector; NO company name — known trap) |
| Theme membership + lanes | baskets engine — `BASKETS.theme_intel.themes` (lane logic per `state_of_themes` re-expression) |
| Prophet stage / entry gate | prophet feed payloads (same source the boards/scorecards render from) |
| Daily read (score/state/stance) | the macro read the landing gauge mirrors (mx5 read) |
| Earnings clock | alt_data earnings-catalyst-clock channel (shipped #3211) |
| Insider / Congress filings | the filings desks' scored data (congress_trades / insider) |
| 13F adds/trims | smart_money desk (356 tracked funds) |
| Daily OHLCV for V2 stats | `data/baskets/ohlcv/*.parquet` (stocks), `data/yahoo/*.parquet` (ETFs/indices, SPY present) |

Trap notes: `site/stockdata/` is EMPTY in fresh worktrees (nightly-populated — use main checkout copies or dev
fixtures); local engine runs can advance forward ledgers — `git restore data/ site/` before committing anything
unrelated; nightly is the SOLE advancer of ledgers.

## 4. Laws & guardrails (non-negotiable)

1. **Display-tier freely; gauntlet only at promotion.** Everything here is context/re-expression of existing
   reads — no new signal, no rank/size/gate authority. If anyone later wants the portfolio layer to *gate*
   anything, that promotion needs the pre-registered gauntlet.
2. **Descriptive, never prescriptive.** Exposures, counts, dates, lane names — never per-user "sell X / buy Y /
   rebalance to Z." This is both a quality bar and the personalized-investment-advice line. Stance words stay
   the desk's general reads ("Semis sit in Take profits"), applied to the book descriptively.
3. **LLM may only smooth calibrated/deterministic content** — never originate scores, escalations, or facts.
4. The word **"validated" is CI-banned** in user-facing copy (`scripts/check_validated_claims.py`).
5. **Bilingual**: any surface on the macro site needs EN+zh; no zh in `title=` attrs (CI). Terminal-side UI
   follows the terminal repo's conventions.
6. **Design doctrine**: read `docs/DESIGN_DOCTRINE.md` + invoke the `frontend-design:frontend-design` skill
   before any user-facing surface; glance tier = plain words, technicals demoted to hover/detail. Numbers with
   meaning ("41% semis"), no raw slugs.
7. **Render budget**: the artifact bake must be cheap (target <30s nightly); anything heavier goes off-path.
8. **Model routing** per CLAUDE.md: Opus builds/reviews via `builder`/`reviewer`; design choices via `designer`;
   Sonnet only for census/mechanical non-code sweeps.
9. Git: branch off fresh `origin/main`; never reuse a squash-merged branch; no bare `git stash` (repo-global
   stack); work in worktrees.

## 5. Tier gating & marketing

- **Pro-only** (the pricing ladder's capability pillar — see landing `#pricing`). Naming: **Flash AI / Pro AI**
  (renamed 07-23; do not reintroduce "Flash analyst"/"Pro Research").
- Do NOT add the landing matrix row or any marketing copy until the feature actually serves users. When live:
  matrix row "Portfolio-aware daily brief" (t-pro), and it becomes a headline Pro selling point alongside the
  institutional research library.
- Free/Insider see the generic brief; the upsell surface inside the product (a tasteful "your book" teaser on
  the Portfolio page) is a designer decision, not a builder default.

## 6. Build order

- **W0 — contract ruling (small PR):** confirm artifact-vs-api split with the operator; define the
  `portfolio_ctx.json` schema (versioned, `"v":1`); stub the bake with 3 tickers + tests. Cross-repo issue in
  mastermind-terminal for the consumer side.
- **W1 — V1 brief (the flagship PR):** full artifact bake wired into nightly (budget-checked); terminal-side
  composer + Portfolio page surface (extend the existing page); deterministic sentence templates (EN first);
  fixtures = 3 synthetic books (concentrated-semis, diversified-defensive, single-name) with golden-file brief
  outputs; unit tests on every join.
- **W2 — V2 risk numbers (second PR):** returns/stats module (pure, tested against hand-computed fixtures);
  plain-word surfacing; historical-replay line. Same descriptive-only guardrail.
- Each PR: same-day squash-merge, tests green, component crops for any UI, honest nulls (a ticker missing from
  the artifact renders "no desk coverage yet", never a fabricated value).

## 7. Open questions for the operator (ask before W1, not during W0 stub)

1. Holdings input: watchlist-as-equal-weight to start, or require weights/share counts? (Recommend: accept both;
   equal-weight fallback with a visible "equal-weighted" tag — honest defaults.)
2. Where does the brief render besides the Terminal Portfolio page — daily AI morning brief email/page too?
3. Universe cap for the V2 correlation store (holdings-only computed on demand vs precomputed top-N universe).

## 8. Verification bar

No fabricated numbers anywhere (the landing program was burned twice inventing prices — pull from parquets).
Golden-file tests for briefs; hand-checked beta/corr fixtures for V2; render-budget timing printed in the bake;
`?still`-style deterministic states for any animated surface. The word for the operator when it ships is a
demo on a real watchlist, not a synthetic screenshot.

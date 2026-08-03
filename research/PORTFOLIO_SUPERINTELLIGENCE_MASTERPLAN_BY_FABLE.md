# Portfolio Superintelligence (PSI) — completion & integration masterplan (by Fable)

Date: 2026-08-03 (amended same day — operator round 2)
Status: CHARTER + build contract — the **Codex execution handoff** for the operator's
portfolio-risk-intelligence vision. Operator-directed (2026-08-03 session): "independent
watchlist system … complete risk analysis of their portfolio … overallocation, cross
correlation, rotation stage, technical risk, options analysis … risks conditioned on regime
and market state … master intelligence tracking on every ticker they own … weakest links,
strongest strengths … holistic score with breakdown scores."
**Round-2 operator directives (2026-08-03, recorded verbatim in effect):** (a) **PRD-R2
OVERRIDDEN** for this surface — "this isn't a live money portfolio, it's just for viewing
by the user" → the holistic score SHIPS (§3.1 rewritten; PRD Amendment 2; DNR row
amended); (b) the portfolio analyzer becomes the **public freebie lead-magnet** — anonymous
instant analysis, free-account long-term tracking with **daily change emails**, a custom
public landing/portal, onboarding integration (§19); (c) macro-side frontend must be
**beautiful and web-app-like/live**, with per-ticker data on the page (§19.8); (d)
integrate the just-shipped **Company Intelligence dossier data** (§19.7) and **per-ticker
news intelligence** incl. a news.html ticker-feed build-out (§19.6).
Parents (all still in force; this doc composes them, it does not re-litigate them):
- `PORTFOLIO_RISK_DESK_MASTERPLAN_BY_FABLE.md` (PRD) — lanes + role ladder + Amendment 1.
- `UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md` (UWP) — store + dashboard, UWP-R1..R7.
- `WATCHLIST_RISK_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (WRI) — book-structure math, WRI-R1..R8, §5-A.
- `PORTFOLIO_BRIEF_MASTERPLAN_BY_FABLE.md` (BRIEF) — portfolio_ctx.v1 + portfolio_brief.v1 + Terminal seam.
- `OPTIONS_INTELLIGENCE` program (OIP masterplan + R0–R3 waves) — the options data plane.
Registries consulted 2026-08-03: `docs/ACTIVE_BUILD_MAP.md` (no colliding open lane; #4331
prophet-board and #4319/#4327 capital-structure/company-intel touch adjacent per-ticker data,
not this surface), `research/DO_NOT_REBUILD.md` (rows honored throughout — esp. row 45
fused-score, Signal-Commons positioning-fusion, RIC-R3 event-window gating, PSS-CD1 frozen
correlation-hazard charter), `config/ruling_graph.yml` (NWC-U4, NWP-U18, RUL-F3.2 intact).

**Read this first, Codex:** ~70% of the operator's vision is ALREADY BUILT across five
chartered programs (§2). Your job is the last 30% — integration, the options lane, the
market-state cross-read, the brief-v2 risk packet, the outcome ledger — executed WITHOUT
re-building what ships today and WITHOUT violating the standing rulings (§3). Every wave in
§14 names its acceptance gates; §0 gates bind every wave.

---

## 0. ACCEPTANCE GATES (every wave is "not done unless" — inline per spawn-handoff law)

1. **Fresh end-to-end happy path, zero manual workarounds**, demonstrated on real
   production-shaped data (not synthetic screenshots): sign in on the macro site → add
   8 correlated tech names + 2 defensives with shares/entry prices → watchlist.html shows
   book structure verdict, per-name lane chips, tape banner → the SAME book appears in the
   Terminal Portfolio page with the brief + risk panels → edit a position on one side,
   the other side reflects it after refetch. A race you reload around is a bug you own.
2. **Per-wave visual crops committed in the PR body** — light + dark + zh for macro-site
   surfaces (Terminal is dark-only but needs en + zh crops), desktop + 390px mobile,
   against the pinned design refs (§13). No first-pass self-merge of flagship UI waves:
   the commissioning session (or the operator) reviews crops before merge.
3. **The composite score ships under PRD Amendment 2's exact scope** (§3.1): display-tier
   on user-facing portfolio surfaces + digests ONLY — transparent named legs, printed v0
   weights, per-leg sub-scores, coverage-driven abstention, nightly forward grading. It
   NEVER feeds boards, rankers, the Neural Web, sizing, alert escalation, or any scored
   path (two-organisms + NWP-U18 + Signal Commons remain fully in force), and it never
   claims authority ("validated" stays CI-banned; no accuracy claims without the §12
   ledger evidence). A reviewer finding the score consumed ANYWHERE outside the
   user-facing display/digest layer rejects the PR.
4. **Descriptive, never prescriptive** — no imperative buy/sell/add/trim/hedge/rebalance
   copy anywhere; review language only ("Take-profit review", "Exit review"). All brief
   text passes the ask_brain advice filter by construction (asserted in tests, the
   `tests/test_portfolio_brief.py` pattern). "validated" is CI-banned.
5. **Privacy (PRD-R7/UWP-R1)**: per-user holdings live ONLY in Supabase (owner-scoped RLS)
   + localStorage. Nothing position-derived is committed to any repo, written into any
   `data/` or `site/` artifact, or logged with values (tickers in server logs: allowed;
   shares/entry/notional: never). New per-user tables ship RLS policies in the same PR
   (UWP-R5). The outcome ledger (§11) grades constructions on the UNIVERSE and on
   synthetic archetype books — never on user books.
6. **Coverage honesty (PRD-R6/WRI-R6)**: any ticker outside an artifact's universe
   degrades to the honest chip ("no desk coverage yet" / "unmodeled"), is excluded from
   the affected math, and never breaks the page. Stale artifacts print stale and only
   ever DOWNGRADE confidence. A book with >40% unmodeled dollars gets an abstaining
   verdict, not a fabricated one. Nulls are disclosed in plain words on Tier 1 with the
   receipt on Tier 2 (DESIGN_DOCTRINE Law 5).
7. **Contract compatibility**: `portfolio_ctx` v2 and `portfolio_brief` v2 are ADDITIVE —
   every v1 key keeps its exact shape and meaning (Terminal PR #170 and the shipped brain
   tool are built against v1; golden tests in both repos pin it). Schema bumps carry
   `"schema": "portfolio_ctx.v2"` / `"portfolio_brief.v2"` and the consumers feature-detect.
8. **Budgets**: the nightly ctx-v2 bake stays <60s and the artifact <2.5 MB raw
   (report both in the bake log; today: ~1.1 MB, ~1,500 tickers). NOTHING per-user runs
   on the render path — per-user composition happens only at request time in macro-api,
   cacheable per (uid, artifact-mtime). Render-budget law is absolute (~67 min).
9. **Bilingual + design law**: every macro-site string is a dual-span `t(en, zh)` pair;
   no translated text in `title=` (CI); Terminal strings go through `lib/i18n.tsx` LEX.
   Directional colors ALWAYS via `var(--up)/var(--down)` (zh red-up flip; Terminal
   `data-updown="east"`) — and risk-state ramps are NEVER built from --up/--down (the
   zh-flip trap; WRI CSS comment is the precedent). DESIGN_DOCTRINE tiers + word budgets
   bind every panel; banned Tier-1 vocabulary list applies (§13.3).
10. **Live verification closes every wave**: macro pages verified on `www.mastermind-x.com`
    (302 = gated is a pass for anon; 404 = missing is a fail), Terminal on
    `app.mastermind-x.com`, with the Terminal's 3-viewport e2e law (1440×900 / 820×1180 /
    390×844) for terminal waves. Ship loop per repo law: commit → push → PR → CI →
    same-day squash-merge → live verification. Cross-repo waves land the producer
    (macro) before the consumer (terminal) and verify the pair live.
11. **Funnel honesty (round-2 waves)**: the anonymous flow delivers REAL analysis before
    any prompt — no login wall, regwall, or email capture between "enter tickers" and the
    full client-side read (§19.2). Signup prompts are value-framed and dismissible, never
    modal-trapping. The landing page's demo widget runs the real math on real baked data
    — never canned screenshots posing as live output.
12. **Email compliance (digest waves)**: every digest goes through `app/mailer.py`
    `send()` (ledger-first idempotency; `cls='marketing'` so suppression +
    `email_prefs` opt-outs bind, fail-closed on lookup errors) with RFC 8058 one-click
    unsubscribe headers (`app/unsubscribe.py` machinery). Digest opt-in is an explicit
    labeled toggle at signup; a quiet day sends nothing (change-triggered, not
    calendar-spam); no position VALUES in email-log rows or server logs (tickers +
    state words only — PRD-R7 applies to the mail pipeline too).

---

## 1. One-line verdict

Finish the already-chartered portfolio intelligence stack into ONE coherent product — the
user's book read through every desk the site runs: complete `portfolio_ctx` v2 (per-ticker
master context: technicals, vol, options, macro-sensitivity, quality, personality, chains),
upgrade `portfolio_brief` → v2 from prose-only into a structured **risk packet** that both
the Terminal and the macro watchlist render, light the **options lane** (the WRI W6.3
come-back, now due), widen the **tape context** (regime/breadth/concentration/dispersion/
flow × your book), ship **weakest-links / working-for-you** ladders, and stand up the
**outcome ledger + calibration loop** that makes every displayed construction forward-graded
— plus (round 2) the **Portfolio Health Score** (operator-overridden PRD-R2, §3.1) and the
**freebie funnel** (§19): anonymous instant analysis → free-account tracking with daily
change emails → a public landing portal — all display-tier, no advice, no score authority,
no new estimators without prereg.

## 2. What already exists — DO NOT REBUILD (the 70%)

| Layer | Status | Where (evidence) |
|---|---|---|
| Per-user store: `watchlists` / `watchlist_symbols` / `portfolio_positions` (Supabase, RLS, shared macro↔Terminal) | ✅ LIVE | UWP §2/§4 (verified live 2026-07-18); `templates/watchstore.js`; Terminal reads same tables |
| Unified watchlist+portfolio dashboard (macro `watchlist.html`): positions table, add/edit modal, sync chip, FX auto-weights | ✅ LIVE | UWP W1/W2 (merged); `templates/watchlist.html.j2` `#pf_section`, `templates/portfolio.js` |
| Book-structure risk read (L2): 9-factor model betas+cov+idio (`factor_betas.json`, ~1,529 names), ENB, per-position risk contribution (MCTR), factor variance shares, pairwise implied corr, twin clusters, calm↔stress lens (`factor_cov_stress`), verdict states DIVERSIFIED/TILTED/CONCENTRATED/ONE BET | ✅ LIVE | WRI W1–W3 (#3405); `templates/risk_core.js` (pure math + tests), `templates/watchlist_risk.js`, `engine/factor_exposure.py` |
| Per-name risk lanes (L1) + role ladder (monitor→review→tighten→trim_review→exit_review) client-side chips + drawer | ✅ LIVE (port of PRD §6–7) | WRI W3; PRD §6 lane spec; review-language labels |
| Regime rail (L3): market_state/risk_radar/vol_regime × book beta | ✅ LIVE | WRI W3; `window.WRI_REGIME` in watchlist.html.j2 |
| What-if pre-trade diagnostic (candidate name → descriptive deltas) | ✅ LIVE (operator NWP-U18 sign-off 2026-07-24) | WRI W4 (#3423) |
| Crypto coverage in the book model (BTC/ETH/IBIT/ETHA/COIN) | ✅ BUILT | WRI W6.1; `engine/factor_exposure.py` CRYPTO_NAMES |
| Transmission-chain membership per ticker (contagion blast radius) + watchlist chain lane | ✅ BUILT | TXI W4 (#3527); `chains` block in portfolio_ctx |
| Nightly per-ticker context artifact `portfolio_ctx.v1` (~1,500 names: sector, themes+reco, stage, entry gate, earnings clock, insider, Congress, 13F, chains; top-level sectors conviction/rotation_state/class, regime.us, gate_go) | ✅ LIVE nightly | BRIEF W0/W1; `scripts/build_portfolio_ctx.py` → `site/data/portfolio_ctx.json` (1.1 MB) |
| Deterministic bilingual brief composer + Pro endpoint + Brain tool | ✅ LIVE | `engine/portfolio_brief.py` (pure, golden-tested), `app/main.py` `/api/portfolio/brief` (positions→watchlist fallback, tier via user_entitlements), brain_gateway `get_portfolio_brief` |
| Terminal Portfolio page ("Conviction Book": per-name verdict/wr/pf/cagr) + **PR #170** "Your book today" brief panel (proxy route, panel states 200/401/403/503, teaser, reading-spine design) | ✅ page live; **PR #170 OPEN, checks green** | mastermind-terminal `components/PortfolioView.tsx`, PR #170 (built against brief v1) |
| Options data plane (OIP): EOD options suite R0–R3 — gex/dealer-gamma state + history index, IV-rank bands, OI suite (oi_time/max_pain/oi_change), exposure profiles, screener, options workspace page, session digests, weekend-run repair, dead-man anchors | ✅ shipping nightly (hardened through #4152/#4153/#4168/#4199/#4207/#4222/#4247/#4292) | OIP masterplan + those PRs; per-ticker + index artifacts |
| Company Intelligence per-ticker dossiers; capital-structure/forensics/earnings evidence planes | ✅ shipping (adjacent context, link-out targets) | #4318/#4322 + capital-structure lanes |
| Operator held-risk desk (Mastermind repo: lanes, alerts, Discord, outcome ledger) | ✅ separate organism — UNTOUCHED by PSI | PRD §5–§9 (placement ruling) |
| Email estate: ledger-first sender (idempotent, suppression/opt-out law, queue+drain, mail-off mode) + RFC 8058 one-click unsubscribe | ✅ LIVE (the digest waves are just a new caller) | `app/mailer.py` (SEE program), `app/unsubscribe.py`, `email_log`/`email_prefs`/`email_suppression` tables |
| Per-ticker news + alt-data bundle (`intelligence.by_ticker.v2`) | ✅ LIVE nightly (§19.6 surfaces it) | `engine/intelligence.py` → `site/intelligence/by_ticker.json`; `engine.financial_news` → `site/news/by_ticker.json` |
| News machine: ticker-tagged multi-source feed (Polygon/Finnhub/GDELT), deterministic quality score + dedup, `qbus` event store, optional `news_llm` summary layer, breaking_summary citation gate, clustering floor | ✅ LIVE (TNI §19.6 composes it — build the delta, not the machine) | `engine/financial_news.py`, `engine/news_common.py`, `engine/news_llm.py`, `engine/marketing/breaking_summary.py`, intelligence desk (#4006) |
| Company Intelligence public teaser endpoint (verified allowlisted projection, CDN-safe) + authenticated context contracts | ✅ LIVE (§19.7 consumes it) | `app/company_intelligence.py`; `engine/company_intelligence/` (`context_only` authority) |
| Onboarding flow assets (landing signup estate) | ✅ LIVE (§19.4 adds a portfolio step) | `templates/onboard.js` / `onboard.css` (+ site copies; Caddy immutable list — ?v= restamp law applies) |

**PR #170 disposition (operator asked):** it is exactly the consumer half of the shipped
brief seam — KEEP it, land it FIRST (PSI-W1). It renders `portfolio_brief.v1` above the
Conviction Book with correct 401/403/503/stale states and a Pro teaser. Rebase on current
`master` (shell/nav/proxy moved since 2026-07-23), re-run checks, verify live against the
production endpoint, merge. Brief v2 (§5.2) is additive, so the panel keeps working
unmodified after v2 lands; its sections simply grow (PSI-W3 extends the same component).

## 3. The law that binds this build

Inherited rulings, restated once (violating any of these is a rejected PR, not a debate):

- **PRD-R2 — AMENDED by operator override 2026-08-03 (PRD Amendment 2; DNR row 45
  updated in this PR).** The user-facing display-tier composite portfolio score is now
  ALLOWED on watchlist/portfolio surfaces and in digest emails, under the §3.1
  construction law (transparent legs, printed weights, abstention, nightly grading).
  What Amendment 2 does NOT strike: the score may not feed any scored path, board
  ordering, ranker, Neural Web artifact, sizing, or alert-escalation authority; may
  not be described as validated/proven; and the operator-desk clause (Mastermind repo)
  is untouched. Fable dissent recorded in §3.1 — grading runs from day one so the
  disagreement resolves on evidence.
- **PRD-R7 / UWP-R1 — privacy**: nothing position-derived in any repo artifact or log.
- **UWP-R2 / NWC-U4 — two-organisms**: user holdings NEVER feed the signal path, boards,
  rankers, Neural Web, alert triage, or any scored artifact. Per-user joins happen
  client-side or at request time in macro-api; never in an engine.
- **NWP-U18 — no portfolio construction/sizing in this repo**: no optimizer, no target
  weights, no hedge suggestions. The WRI W4 what-if carve-out (user-proposed candidate,
  descriptive deltas) is the ceiling; "suggest me a hedge/size" is a NEW adjudication.
- **WRI-R2 — statistics vs composites**: a measured single-construct statistic with a
  printed method (book beta, book vol, ENB, a factor share, a pairwise ρ, an IV rank)
  MAY display. Blending heterogeneous lanes into one number/rank/dial MAY NOT.
- **WRI-R7 — regime-honest correlation**: when calm and stress reads diverge, the glance
  tier leads with the stress read; the calm number never prints alone.
- **WRI-R8 / PRD-R10 — earned authority only**: display-tier ships freely; any promotion
  of a PSI state to rank/size/gate/alert-escalation authority requires the pre-registered
  gauntlet on a forward ledger, adjudicated separately.
- **Signal Commons — positioning-fusion ILLEGAL**: positioning/ownership keys (13F,
  short interest, dealer positioning) never fuse into any score. Display context only;
  13F/ownership is context/crowding-hazard, never a positive signal (WA-R2, NEXTL-U13).
- **RIC-R3 — no calendar/event-window-gated risk legs**: earnings/FOMC/OPEX windows are
  DISPLAY context (the earnings clock), never a gate that advances a risk state.
- **PSS-CD1 (frozen prospective charter) — correlation/dispersion crowding-hazard**: the
  correlation-one overlay inside relief-hazard windows is a frozen prospective study.
  PSI displays measured correlation (WRI math) but must NOT present any correlation state
  as a "validated crowding/sell gate", and must not touch the frozen PSS families.
- **A7 / CXI-R23 — the LLM never originates** signals, scores, or escalations; brief text
  is deterministic composition (an LLM may at most smooth already-computed sentences —
  v1/v2 use none). Chat/brain surfaces read product artifacts only, never repo internals.
- **RUL-F3.2** — engine surfaces may not read as live position monitors; the carve-out
  covers only the user's own self-entered holdings view, labeled as such.
- **Falsifier-language law (operator 2026-07-27)**: no "falsifier fired / thesis refuted /
  证伪" on user cycle surfaces — "what we're watching" conditions + quiet "read being
  updated" chips; full verdicts live on the Calibration Lab below the fold.
- **Design routing**: design choices at opus-or-above (`designer` agent or main loop /
  Codex's strongest lane); DESIGN_DOCTRINE + frontend-design skill loaded before any
  surface work; mockups-first for new surfaces.

### 3.1 The holistic score — SHIPS under operator override (PRD Amendment 2, 2026-08-03)

History, so nobody relitigates it: the first draft of this charter kept PRD-R2 (no fused
number — every prior unearned-weights composite died: FR-1, WA-R1, MSP-R2, TOP3-E5, the
PRD §2 autopsy). The operator overrode same-day: *"this isn't a live money portfolio,
it's just for viewing by the user."* The override is recorded (PRD §13 Amendment 2 + the
amended DNR row), and **the score ships** — display-tier, on the portfolio surfaces and
in digests, as the freebie's headline read. **Fable dissent, on record:** display-tier or
not, a confident number with unearned weights can mislead; the §3.1.2 construction law +
day-one grading (§11) exist so the number stays honest and the weights EARN their next
version. Precedent for the pattern: `engine/us_board_rank.py` (us_prophet_v1) — an
explicit transparent 0–100 heuristic with named weighted legs, fail-closed coverage, and
full component disclosure.

#### 3.1.1 What ships (the product shape)

- **Portfolio Health Score, 0–100** (100 = structurally clean book), Tier-1 hero on the
  portfolio surface, the landing widget, and the daily digest subject line ("Your book:
  72 → 68"). One number, one plain-word state beside it (the WRI posture verdict), one
  sentence naming the biggest detractor ("concentration is what's costing you points").
- **Breakdown sub-scores (0–100 each)** — the operator's "breakdown scores on different
  factors", one per dimension, each expandable to its receipts: **Structure**
  (ENB vs book size, top-factor share), **Concentration** (top-name %, top-3 %, HHI),
  **Correlation** (avg stress-ρ, twins share of book), **Market coupling** (beta
  extremity, R² to market), **Volatility** (book vol ratio vs SPY), **Condition**
  (share of names with clean lanes; ladder counts), **Event density** (share of book
  reporting ≤10 sessions), **Options posture** (coverage-weighted IV-rank extremity —
  abstains below coverage floor). Every sub-score is a monotone map of measurements the
  packet already carries, with printed anchors.
- **Book Posture verdict, condition counts, ladders, per-construct measurements** (§7,
  §10) all remain — the score summarizes them; it never replaces them.

#### 3.1.2 Construction law (binding on every score PR)

1. **Transparent legs only**: each sub-score is a printed monotone map of named packet
   fields with printed anchors (v0 anchors = the WRI/PRD printed thresholds where they
   exist, e.g. ENB ≥4 / 2.5–4 / 1.5–2.5 / <1.5). No hidden inputs, no fitted parameters,
   no LLM anywhere in the loop (A7 is NOT overridden).
2. **v0 weights = equal across legs with coverage, printed as "v0 · equal-weighted ·
   graded nightly since <date>"** — renormalized over available legs. §12's Study-1 runs
   BEFORE any non-equal weights ship ("preliminary weighting research so the weightings
   aren't garbage" — the operator's own bar); weight changes are versioned PRs citing
   ledger evidence (v0 → v1-measured), never silent (§11.4).
3. **Coverage abstention**: a leg without data DROPS (renormalize + disclose "scored on
   6 of 8 dimensions"); a book with >40% unmodeled dollars gets NO score — the honest
   chip instead (gate 6). Never a fabricated 50.
4. **Client/server parity**: the score computes CLIENT-SIDE from public baked JSON (so
   the anonymous freebie gets it) and server-side in the composer (so digests/Terminal
   get it) — same legs, same anchors, golden-pinned both ways (§5.3). The
   server-enriched extras (realized corr) may ANNOTATE but never change the number —
   anon and signed-in must see the same score for the same book.
5. **Scope fence** (what Amendment 2 did not strike): the score never feeds board
   ordering, rankers, NW, sizing, alerts-escalation, or any engine read; it never
   appears on non-portfolio signal surfaces; "validated"/accuracy claims stay banned
   until the §12 ledger says otherwise, and the Tier-2 receipt states its version,
   weights, coverage, and grading status plainly.
6. **zh parity**: score naming/copy bilingual; the ramp uses neutral tint tokens (never
   --up/--down; gate 9).

## 4. Architecture of record

```
                          MACRO DASHBOARD (this repo)
 nightly (render-budget-bound, off-path where heavy):
   engine/* desks (existing)          engine/factor_exposure.py (existing +)
        │                                   │
        ▼                                   ▼
   scripts/build_portfolio_ctx.py  ──►  site/data/portfolio_ctx.json   (v2, §5.1)
   (JOIN-only bake, <60s, no user data)    site/factor_betas.json (betas+cov+stress)
        │                                   site/data/psi_goldens.json (§5.3, tiny)
        ▼
   data/psi_ledger/*  (§11 universe/archetype outcome ledger — nightly appender)

 request-time (macro-api, FastAPI app/main.py — per-user, cacheable, OFF render path):
   GET /api/portfolio/brief   (Pro)  = compose_brief(ctx v2, holdings)      [v1 LIVE]
                                     + risk packet sections (§5.2):        [PSI-W3]
                                       lanes per name · book stats (py mirror of
                                       risk_core math, golden-pinned) · realized K×K
                                       corr from psi_returns.v1 on R2 (§7.2) ·
                                       options posture · tape context · ladders
   holdings source: supabase portfolio_positions (open) → watchlist fallback [LIVE]

 CLIENTS (two, one contract):
   macro watchlist.html  — client-side WRI math from baked JSON (logged-out capable,
                           UWP-R6) + signed-in Pro fetch of brief v2 for the sections
                           client math cannot do (realized corr, options posture)
   Terminal /portfolio   — PR #170 panel (brief v1 prose) + PSI-W3 structured panels
                           (same brief v2 fetch through the same-origin proxy)
   Brain chat            — get_portfolio_brief tool returns the same composed packet
```

One composer, three surfaces. The Python composer is the single authority for every
server-computed number; `risk_core.js` stays the client authority for interactive/local
books; §5.3's golden harness pins the two to each other.

## 5. Contracts

### 5.1 `portfolio_ctx` v2 (additive; schema string `portfolio_ctx.v2`)

Everything in v1 keeps its exact shape (see `scripts/build_portfolio_ctx.py`). v2 ADDS,
per ticker, compact state blocks — every field copied VERBATIM from an existing nightly
artifact (the bake stays a JOIN; it originates nothing, fits nothing, thresholds nothing).
A block is OMITTED when its source has no data for the name (never null-filled).

```jsonc
"NVDA": {
  // ── v1 blocks (unchanged) ──
  "sector": "...", "themes": [...], "stage": {...}, "entry": {...},
  "earnings": {...}, "insider": {...}, "congress": [...], "f13": {...}, "chains": [...],
  // ── v2 additions (each verbatim from its source; sources table in §6) ──
  "tech":  { "ext": "...",            // extension grade (e.g. normal|stretched|parabolic)
             "ma":  {"m50": true, "m200": true},   // above/below state booleans
             "rs":  "...",            // RS-vs-SPY state word the source already prints
             "atr_z": 1.4,            // ATR z (display precision 1dp)
             "rvol63": "...",         // realized_vol_63d band word (display-tier survivor)
             "dd252": -12,            // % from 52w high, whole number
             "washout": "..." },      // oversold/washout state word IF a desk prints one
  "vol":   { "iv_rank": 62, "iv_band": "...",      // OIP IV-rank + band (verbatim)
             "term": "...", "skew": "...",         // state words if OIP prints them
             "em_earnings": 6.2 },                 // implied earnings move % if available
  "gex":   { "state": "...", "asof": "..." },      // per-name dealer-gamma state if covered
  "flow":  { "opt": "...", "asof": "..." },        // options-flow touch state if covered
  "msens": { "rate_tier": "HIGH", "read": "..." }, // stock_macro_sensitivity chip verbatim
  "fq":    { "flags": 2 },                         // count of solvency/dilution/quality flags
                                                   //   (each flag list on Tier-2; PRD lane 5 sources)
  "pers":  { "arch": "..." },                      // personality archetype (context, PRD-R12)
  "dossier": true                                  // Company-Intelligence dossier exists → link
}
```

Top-level v2 additions (small): `market` block — the tape-context states (§9) copied
verbatim from their homes: risk_radar verdict, market_state, vol_regime, regime score
(exists in v1 as `regime.us`), breadth state, concentration state, dispersion regime,
sector-flow tape state, per-sector rotation quadrant. Plus `coverage` counts per block
(the bake already prints cov counts — extend and emit them for honesty chips).

Budget: additions are state WORDS + a few small numbers — est. +0.4–0.8 MB. Gate 8 caps
at 2.5 MB; if the real number exceeds it, move `congress`/`f13` detail rows to Tier-2
lazy fetch or split a `portfolio_ctx_x.json` sidecar — decide by measurement, in the PR.

**W2 first task (verify-then-build):** field-presence census against the REAL rendered
artifacts on main (site/stockdata is render-owned and EMPTY in fresh worktrees — use the
production site copies or main-checkout `site/`; the BRIEF §3 trap note stands). Record
in the PR which §6 sources actually carry each field; a source that doesn't exist yet
(e.g. no per-name skew state) drops the field — never fabricate.

### 5.2 `portfolio_brief` v2 — the structured risk packet (additive)

v1 = prose: `headline` + `sections[]` of bilingual lines (LIVE, Terminal-rendered).
v2 keeps ALL of that and adds `data` — machine-renderable sections so both clients can
draw panels without re-deriving math:

```jsonc
{ "schema": "portfolio_brief.v2", ...v1 fields...,
  "data": {
    "book":    { "n": 9, "covered": 8, "modeled": 8, "unmodeled": ["FOO"],
                 "weighting": "positions|equal" },
    "posture": { "state": "concentrated",          // WRI verdict vocabulary, verbatim
                 "enb": 2.1, "enb_stress": 1.6,
                 "beta": 1.31, "vol_ratio": 1.4,   // book vol / SPY vol, same window
                 "top_factor": {"k": "growth_tech", "share": 64},
                 "clamped_pct": 0 },
    "concentration": { "top_name_pct": 24, "top3_pct": 55, "hhi": 0.18,
                       "sectors": [{"name": "Technology", "pct": 41, "class": "headwind",
                                    "conviction": "...", "rotation_state": "..."}],
                       "themes":  [{"id": "...", "name": "...", "pct": 33, "reco": "..."}] },
    "correlation": { "avg_rho_stress": 0.62, "avg_rho_calm": 0.44,
                     "twins": [{"names": ["NVDA","AMD","AVGO"], "rho": 0.81, "lens": "stress"}],
                     "method": "factor-implied (9F); realized 63d/252d overlay",
                     "realized": {"avg_rho_63": 0.58, "pairs_n": 28} },   // K×K from psi_returns (§7.2)
    "lanes":   { "names": {"NVDA": {"role": "trim_review",
                            "elevated": ["extension_giveback","event_window"],
                            "watch": ["sector_rotation"]}, ...},
                 "counts": {"exit_review": 0, "trim_review": 1, "tighten": 0,
                            "review": 2, "monitor": 3, "ok": 3} },
    "options": { "coverage": 6, "book_iv_rank_w": 58, "band": "...",
                 "names": {"NVDA": {"iv_rank": 62, "band": "...", "em": 6.2,
                                    "gex": "...", "flow": "..."}} },
    "tape":    { ...the §9 market block, verbatim states + which of the user's
                  sectors/themes each state touches... },
    "ladders": { "weakest": ["XYZ","NVDA", ...],   // role-ladder severity order (§10)
                 "working": ["MSFT", ...] },       // clean-lanes order (§10)
    "score":   { "value": 68, "version": "v0-equal", "graded_since": "2026-08-…",
                 "legs": {"structure": 61, "concentration": 44, "correlation": 58,
                          "coupling": 72, "volatility": 66, "condition": 78,
                          "events": 90, "options": null},   // null = abstained leg
                 "covered_legs": 7, "detractor": "concentration" },   // §3.1 law
    "news":    { "names": {"NVDA": [{"t": "...", "src": "...", "when": "...",
                                     "url": "..."}]},        // intelligence.by_ticker.v2
                 "book_count_7d": 12 }
  } }
```

Rules: every number carries its method on Tier-2 via the clients (the packet carries
`method` strings where non-obvious); all state words verbatim from sources; `data` is
OMITTED wholesale below Pro (the 403 teaser flow of PR #170 is unchanged); v1 prose
sections gain three new deterministic section builders (risk structure, options desk,
tape context) written in the same `engine/portfolio_brief.py` style — pure, bilingual,
advice-filter-clean, golden-tested (extend `scripts/_regen_portfolio_brief_goldens.py`
fixtures: concentrated_semis, diversified_defensive, single_name, +new options_heavy).

### 5.3 Cross-surface parity goldens

The book-structure math now lives twice (client `risk_core.js`, server composer). Two
copies with no shared file = drift; the guard is a SHARED GOLDEN: a COMMITTED fixture
`tests/fixtures/psi_goldens.json` — 3 fixed synthetic books (public, no user data) with
their full expected outputs (ENB, beta, shares, MCTR, twins, ρ matrix), regenerated only
by ONE generator script (`scripts/_regen_psi_goldens.py`, the brief-goldens pattern) when
the schema deliberately bumps. Tests: (a) this repo — `risk_core.js` (node harness,
exists for WRI) AND the Python composer must reproduce the goldens exactly; (b) terminal
repo — a vitest pins its rendering mapping against a vendored copy of the same fixture
(refreshed on schema bump). A math change that forgets one side goes red in CI, not in
production.

## 6. Per-ticker intelligence — lanes and sources (the "master tracking on every ticker")

L1 lanes (shipped, WRI W3) stay the spine; PSI extends coverage and depth. Lane table of
record (PRD §6 remains authoritative for thresholds; v0 heuristic thresholds print as
such on Tier-2). PSI's source-of-truth mapping for the ctx-v2 blocks:

| Block | Source artifact (nightly, this repo) | Notes |
|---|---|---|
| `tech` | per-ticker stockdata JSON blocks the WRI L1 lanes already read (ext / MA / RS / ATR / drawdown); `realized_vol_63d`, `updown_dollar_vol_ratio` from the fingerprint-survivor set | survivors are DISPLAY-TIER ONLY (DNR row 115: promotion of either needs fresh prereg; full-population effect sizes may not be cited) |
| `tech.washout` | `engine/rsi_stack_signals.py` states (`rsi_stack_oversold` all-TF ≤30 / `rsi_stack_overbought` all-TF ≥80, curl events) + washout-watcher states where a desk prints one (`hk_washout_watch`; `mag7_washout` is background-only per its DNR row) | display state only — washout×turn as an ENTRY signal is KILLED (DNR row 78); we show the state word, never an entry implication |
| `tech.ext` | `engine/extension.py` — `ext_z` (distance-from-200dma z vs own history), `grade` ∈ in-trend/steady/stretched/**parabolic**, `near_52wh` | already feeds us_standouts rows; verbatim grade words |
| `vol` / `gex` / `flow.opt` | OIP artifacts: options_hub IV-rank + bands (#4130 vocabulary), `gex_state` (gamma_regime/flip/walls + `_index.json` aggregate #4292), options_skew snapshots, oi_change / flow-leaders touch states | **Coverage reality: the ThetaData EOD store spans ~380 roots (2012–2026), not the full ~1,500-name universe** — most books will have partial options coverage and the block prints its coverage count honestly; W2 field census decides exact fields; uncovered names OMIT the blocks |
| `msens` | `stock_macro_sensitivity` chip + `factor_betas.json` rate/dollar/credit betas | verbatim tier words |
| `fq` | PRD lane-5 sources (leverage_ratios, accounting_quality, capital_allocation, dilution_events, moat_falsifiers) | ctx carries the COUNT + Tier-2 list; flags themselves stay in stockdata |
| `pers` | stock_personality archetype | context, never scores (PRD-R12) |
| `chains` | transmission chain_state (TXI) | shipped v1 |
| `dossier` | Company Intelligence dossier index | link-out only |

The complete engine inventory backing these (regime, rotation, breadth, concentration,
dispersion, turbulence, flow, options, technicals) is recorded in §App-A so Codex can
navigate without a repo-wide search.

## 7. Book-level reads (delta on shipped WRI)

Shipped and untouched: factor shares, ENB (calm+stress), MCTR bars, twins, verdict,
what-if. PSI adds:

1. **Condition counts** (Tier-1, next to Book Posture): "N of M names in review or
   worse · K lanes elevated across the book" — printed counts (PRD-R2 form). Computed
   client-side (watchlist) and server-side (packet `lanes.counts`), golden-pinned.
2. **Realized-correlation overlay** (the WRI W5 come-back, server-side home). Data-path
   reality check (verified 2026-08-03): the API host (VPS) serves `site/` + R2 and does
   NOT carry `data/` parquets — request-time composition cannot read the deep-history
   store directly. So the nightly bakes **`psi_returns.v1`** (universe × trailing 252
   session daily returns, compact rounded floats, from `data/stocks/*.parquet` — the US
   deep-history store — + `data/yahoo/` ETF/index closes) and publishes it to **R2**
   (the `options_hub` publish pattern); the composer fetches it with a TTL cache
   (`app/hub.py` precedent) and computes the K×K realized ρ (63d + 252d) for covered
   holdings: avg ρ + tightest realized pair NEXT TO the factor-implied read. Divergence
   prints as its own honest line ("model and tape disagree on how tightly X moves with
   Y — treat the higher number as the risk"). WRI-R7 stress precedence applies. R2
   unreachable → the realized block is OMITTED with the honest chip (never a guess).
   Client-side watchlist shows it for signed-in Pro via the packet.
3. **Book vol ratio** (vs SPY over the same window) — BRIEF V2's chartered stat, from
   the same `psi_returns` store; stated as a ratio in plain words, never a Greek.
4. **Historical replay line** (BRIEF V2 chartered): "this exact book's worst 20-day
   stretch in the last year was −18% (last April)" — descriptive replay of the CURRENT
   weights over stored closes (reuse the crisis-window replay machinery in
   `engine/portfolio.py`, which already frames itself "risk-budget reference, not a
   trade list"); clearly labeled "replay, not a forecast"; no VaR/ES ever (WRI §3.6
   rejection stands).
5. **Options posture** (§8) and **tape context** (§9) book blocks.

## 8. Options lane (WRI W6.3 come-back — DUE; the operator's "complete options analysis")

Precondition (verify in-wave, do not assume): the OIP EOD plane is now governed —
R0 repair sealed cadence/freshness with dead-man anchors (#4152/#4153), weekend runs fixed
(#4222), archive repaired (#4207). The lane lights ONLY behind those freshness anchors:
a stale/absent options artifact degrades the block to `coverage_missing`, never a guess.

Per-name (ctx `vol`/`gex`/`flow.opt`, §5.1) → three surfaces:
- **L1 lane chip `options_vol`** (watchlist + packet): state grammar (all verbatim OIP
  vocabulary): `elevated` = top IV-rank band PLUS a second OPTIONS fact (extreme
  dealer-gamma state, or unusual oi_change touch); `watch` on single facts. The
  earnings-window conjunction ("rich vol INTO earnings") renders as a DISPLAY sentence
  only — the calendar already has its own ladder lane (PRD §6 lane 3 event_window), so
  feeding it into options_vol too would double-count one fact in the ladder; and per
  RIC-R3 a calendar window contextualizes display, never advances a risk state.
- **Book options posture panel**: coverage count ("options desk covers 6 of your 9
  names"), book-weighted IV rank + band word, names with elevated IV into earnings,
  dealer-gamma states touching the book, this-week options-flow touches on holdings.
  Plain-word stance per DESIGN_DOCTRINE Law 1 — usually "watch — hedges are
  expensive/cheap right now" phrased descriptively ("puts on your largest name price at
  the Xth percentile of their year"), NEVER "buy puts".
- **Brief v2 options section** (prose): 2–3 deterministic sentences from the same facts.

Explicitly NOT in scope: any options-derived signal (DOI is DEAD, skew-deceleration
UNSUPPORTED — W-E1 gauntlet; DNR rows 80–81), dealer-positioning fusion into any state
(Signal Commons), options-based sizing. W-F (options) stays PARKED per its own row.

## 9. Tape context — "the market you hold this book in" (regime & market-state conditioning)

The operator's list — regime, concentration, advance/decline, sector flow, turmoil,
turbulence, sideways/rotational/indecisive tape, geopolitical, policy/rates — maps to
reads this repo ALREADY computes. PSI composes them; it builds NO new regime classifier
and NO parallel fusion (MSP-R2: risk_radar→market_state→regime_vector is the sole
authority chain).

The `market` block (ctx v2) + the watchlist L3 strip + packet `tape` section carry, each
verbatim from its home artifact with its own plain-word stance + link-out:

| Read | Home (engine/artifact — verified 2026-08-03) | Book cross (display-only join) |
|---|---|---|
| Daily regime read (quad, cycle_tag, transition_state, score/label) | `data/regime/latest.json` (engine/regime.py; v1 ctx already carries `regime.us`) | book beta × read (shipped WRI L3 sentence) |
| Risk radar verdict (state, dominant_scare) + vol regime (ts_slope_state, vrp_state, fragility_confluence) | `latest.json['risk_radar']` / `['vol_regime']` (the SOLE stress authority chain — MSP-R2) | banner tint + one review-stance line |
| Breadth / advance-decline | `data/breadth/breadth.parquet` roots (adv/dec/nh/nl/pct_above_50/200) + `engine/advanced_breadth.py` display internals; intraday `site/live/breadth.json` | "narrow tape" chip; if the book's top factor share is high AND breadth is narrow, the sentence prints BOTH facts (no blended state) |
| Market concentration | **No dedicated engine exists** (census 2026-08-03). Composed from: risk_radar `bubble` leg's `cap_leadership` flag + `engine/index_leadership.py` display ratio; PLUS one small NEW printed-arithmetic fact — top-10 weight share of the S&P 500 from `data/breadth/constituents.parquet` (pure display arithmetic, no gauntlet owed; build it in W5) | shown beside the book's own top-name % — two printed facts side by side |
| Dispersion regime | `data/dispersion/regime.json` (`dispersion_regime.v1`: verdict, pctile, avg_corr) | "stock-picker's tape vs one-trade tape" plain words |
| Market effective bets | `data/neuralweb/covariance_spine.json` (`factors_effective_bets`, `same_bet_warning`, absorption pass-through) + `engine/cross_asset.py` absorption ratio (`data/crossasset/latest.json`) | the flagship juxtaposition: "the market is running ~N independent bets right now; your book runs ~M" — two measurements, no blend |
| Sector flow tape | `engine/group_flow.py` fingerprints → `site/basketdata/flow.json` (stages EMERGING/CONFIRMED/EXHAUSTED per basket) | which of YOUR sectors/themes sit in which flow stage |
| Rotation quadrant per held sector | `engine/subsector_rotation.py` RRG quadrants → `site/marketdata/subsector_rotation.json`; `us_sector_rotation.v1`; stage boards (`data/stage_analysis/`) | per-holding `rotation_state` exists in v1 ctx; add the quadrant word + theme flow stage |
| Turbulence / stress backdrop | risk_radar (above) + absorption ratio percentile; OFR FSI (`data/ofr_fsi/`) is collected reference context | banner only |
| Policy / rates / real-rate | `data/rates_command/latest.json` (`rates_command.v1` — its deterministic stance sentence is the Tier-1 line) + `engine/fed_path.py`/`fed_stance.py` + `rate_inflation_transmission` sector map | "3 of your names are HIGH rate-sensitivity into <the rates_command stance>" — two printed facts; per-name `msens` chips |
| Geopolitical | GPR index (Caldara–Iacoviello, threat/act split, `data/uncertainty/gpr.parquet`) + `engine/dislocation.py` `geo_reversibility` context read | CONDITIONS-FRAMING ONLY (PS-R1/R4): display the tracked conditions; never probabilities, never LLM re-escalation |

"Sideways / rotational / indecisive" is NOT a shipped classifier — do NOT invent one
(that's a new signal needing its own prereg; the dispersion + breadth + rotation reads
together already SAY it in plain words). If the operator wants a named tape-character
read later, it goes through prereg like everything else.

Regime-CONDITIONED thresholds (risks that literally re-weight by regime) are a
CONSTRUCTION, not a display join — v1 does display juxtaposition only; the conditioning
study belongs to §12's program (candidate study 3) with its own prereg.

## 10. Weakest links, strongest holds, conviction

- **Weakest links** (Tier-1 list, both surfaces): names ordered by role-ladder rung
  (exit_review > trim_review > tighten > review > monitor), ties by elevated-lane count,
  then weight. Ordering by a NAMED LADDER + printed count is the PRD-R2-sanctioned
  aggregate — there is no score. Each row: name · role label (review language) · the 1–2
  lane reasons verbatim · as-of.
- **Working for you** (the "strongest" list, same grammar, inverted): names with zero
  elevated lanes, ordered by clean-lane count then tailwind context chips (sector class
  tailwind / stage-2 / theme reco) — chips are facts, the ORDER is the printed count.
  Copy stays descriptive ("nothing elevated on 4 of your 9 names").
- **Conviction**: the system does NOT emit a conviction number (fusion). The Terminal's
  Conviction Book already shows per-name track-record stats (its own single-construct
  measurements). PSI adds an OPTIONAL user-entered conviction tag (high/core/starter —
  self-declared, stored with the position row, displayed verbatim, never fed anywhere).
  The operator's real question — "which names does the evidence align on" — is answered
  by the working-for-you chips, not by a number we'd have to invent.

## 11. Outcome ledger + calibration loop (the lawful "self-learning")

The operator asked for weights that "self learn and adjust." The lawful, honest form
(A7: no self-mutating authority; PRD-R10 pattern; prophet learning-loop precedent):

1. **Universe lane-state forward grading** (nightly, off render path, `data/psi_ledger/`):
   for EVERY universe name (not user books — privacy), append the day's lane states +
   role rung, and grade matured rows at t+5/t+21 (forward return, MaxDD, whether a
   harder rung followed). This grades the CONSTRUCTIONS, not any user. **Reuse the
   house grading machinery** — `engine/track_record.py` (append-only, key-deduped,
   no-look-ahead) + `engine/grading.py` (next-bar fill convention) — do NOT write a
   new logger.
2. **Archetype-book grading**: 6 fixed synthetic books (concentrated-tech, diversified,
   defensive, high-beta, options-heavy, one-bet) re-scored nightly; their posture/ENB/
   counts + forward realized vol/DD accrue in the same ledger. These are the books the
   §12 studies read.
3. **Calibration Lab surface** (Tier-3, below the fold per the falsifier-language law):
   the ledger's honest aggregates ("exit_review names went on to underperform their
   sector at t+21 in X of N cases; CI …"). Home: the `calibration.html` estate
   (`engine/calibration_hub.py` — the self-improving-suite observability surface with
   the pre-registered promotion-gate machinery: Holm-adjusted α, desk-specific
   empirical nulls, `engine.trial_ledger` budget) — PSI reads plug into that gate
   machinery rather than inventing new statistics; `measurement.html` untouched.
4. **Recalibration protocol**: thresholds/weights NEVER mutate online. A quarterly
   formal read of the ledger may propose threshold changes as a versioned PR citing the
   ledger rows (v0-heuristic → v1-measured), reviewed like any promotion. Anything
   seeking AUTHORITY (gating/alerts/ranking beyond the ladder) goes through WRI-R8
   prereg gates.

## 12. The weighting research program (the score shipped — now its weights earn their keep)

Amendment 2 shipped the score with printed v0-equal weights (§3.1.2). This program is the
operator's "backtest and preliminary weighting research" — it now serves to (a) sanity-check
the v0 construction BEFORE launch and (b) upgrade weights on evidence, versioned:

- **PSI-Study-1 (retrospective construction study).** Question: does ANY fixed weighting
  of book-grain lane states order forward book outcomes (63d realized vol; MaxDD) better
  than (a) the printed lane COUNT and (b) book beta alone? Corpus: archetype +
  randomized synthetic books over ≥10y of stored closes. Methodology fences (violating
  any = invalid study, DNR §3): era-split across the 2010 break where data allows;
  time-controlled block bootstrap with time-contiguous blocks ≥3 months
  (ticker-cluster-only CIs FORBIDDEN — effective N = months; single-month blocks
  measured anticonservative; the PSS reports' 3-month-block CI is the house form);
  horizon at the registered ruler (t+21/t+63 swing convention); no denominator
  conditioning on resolution; single-window episode symmetry rule;
  understanding-before-backtest memo first (why WOULD these weights generalize?).
- **PSI-Study-1 launch read (W9 gate)**: before the score goes live, Study-1's FIRST
  deliverable is a sanity memo on the v0 construction over the archetype corpus — does
  a lower Health Score in fact precede worse forward realized vol/DD than a higher one,
  monotonically enough to print? If v0-equal fails even that ordering test, the launch
  legs/anchors are revised (still transparent, still printed) BEFORE any user sees the
  number. This is the operator's own "not garbage at the start" bar.
- **PSI-Study-2 (prospective, ongoing)**: the §11 ledger grades the shipped score
  nightly (score-decile → forward outcome). Quarterly formal reads may promote
  weight/anchor changes as versioned PRs (`v0-equal` → `v1-measured`, prereg'd in
  `research/PSI_COMPOSITE_PREREG.md` with the null "equal weights are not beaten").
  Accuracy CLAIMS on any surface unlock only from this ledger; until then the receipt
  says "graded since <date>, no accuracy claim yet."

## 13. Design specification (both sides)

### 13.1 Macro side (watchlist.html — the funnel home; NO new page)

The unified surface stays `watchlist.html` (UWP-R1). PSI deepens sections, in the page's
already-pinned WRI design language (`mockups/wri/watchlist_risk_mockup.html` + committed
crops `mockups/refs/wri/`): scoped `.wri*` components, aurora backdrop, eyebrow + mono
labels, state tints `--wri-ok/tilt/conc/one`, risk ramps never from `--up/--down`.
Page belongs to the `_site_nav.html.j2` family (it already does); no third header.
Design tokens/idiom of record: `theme.css` custom properties; panel `h2` rail signature;
LENS popovers (`data-tip-en/zh` string tier; rich tier `.lens-src` with `data-lens-kind`)
for every Tier-2 receipt; `ilx` (lib/illus.py) for any small illustrative series —
NEVER Plotly on this surface. Dual-span `t(en, zh)` i18n; light+dark via tokens only.

New/changed panels (design-spec wave produces exact markup/CSS BEFORE build; crops to
`mockups/refs/psi/`): ① Book Posture hero gains the condition-count line + ladder links;
② Options posture panel (new, `.wri` idiom); ③ Tape context strip (chips, each with LENS
receipt + link to home page); ④ Weakest-links / Working-for-you twin lists; ⑤ per-name
drawer gains `tech/vol/msens/fq/pers` rows + dossier link-out. Empty/logged-out states:
current UWP behavior (local mode + sync chip); Pro-only sections show the tasteful
in-place teaser (PR #170's pattern, macro-idiom styling).

### 13.2 Terminal side (mastermind-terminal — dark-only, v5 tokens)

Idiom of record: `terminal/app/globals.css` v5 tokens + the `.obs` extension layer
(`DESIGN_OBSERVATORY.md` rules — `.obs-card` always, `color-mix()` tints, no hex);
PR #170's `pbrief` reading-spine panel is the shipped design reference for brief
surfaces. PSI-W3 extends `/portfolio`: below the brief panel, structured panels from
`brief.data` — posture card (verdict word + ENB/beta/vol-ratio KPI row in the existing
`.kpis` grammar), lanes table (role badges, review language), twins/correlation card,
options posture card, tape strip. All strings through `lib/i18n.tsx` LEX (en+zh);
directional color via `var(--up)/var(--down)` ONLY (east-flip law); risk states get
their own neutral tint tokens (mirror the macro rule: never up/down for risk ramps).
Nav: `/portfolio` already registered in `AppNav.tsx` TOP + `MobileNav` mirror — no nav
change needed. Auth: page already reads the Supabase user server-side; the proxy route
pattern (PR #170) is the template for any new API fetch. Responsive: the 3-viewport e2e
law applies (1440/820/390).

### 13.3 Copy laws (both sides, enforced at review)

Tier-1 banned: internal names (WRI, ENB, MCTR, GEX, IV-rank as bare acronyms, lane slugs,
study IDs), untranslated stats, raw slugs. Plain translations of record: ENB → "your book
behaves like ~N independent bets"; MCTR share → "share of your book's swing"; IV rank →
"options there are priced rich/cheap vs their own year"; stress-corr → "move as one in
selloffs". Stance vocabulary fixed: Act · Get ready · Watch — don't chase · Protect
gains · Stand aside · Ignore (review-language variants for ladder labels). One as-of +
one merged footnote per panel. zh copy equally plain (no EN enums inside zh prose).
Numbers arrive with meaning (Law 3); receipts to LENS/Tier-2.

## 14. Waves & PR slicing (each wave = 1 PR unless noted; §0 gates bind all)

| Wave | Scope (repo) | Key gates beyond §0 |
|---|---|---|
| **W1 — land the seam** | Rebase + land Terminal **PR #170**; live-verify brief end-to-end (real Pro account, real book, 401/403/503 paths); crops in PR. (terminal) | No new features; PR #170 merges before ANY brief-touching wave |
| **W2 — ctx v2** | Field-presence census (against production artifacts) recorded in-PR → `build_portfolio_ctx.py` v2 blocks + `market` block + coverage counts; budget stamps printed; tests incl. block-omission honesty. (macro) | v1 keys byte-stable on the golden fixtures; bake <60s; artifact <2.5 MB |
| **W3 — brief v2 risk packet** | New composer sections (§5.2: posture/concentration/correlation+realized/lanes/ladders/tape prose+data); Python book-math mirror + §5.3 goldens; `psi_returns.v1` bake → R2 (§7.2); endpoint serves v2; Brain tool passthrough; Terminal structured panels; macro watchlist Pro fetch for realized-corr/options rows. (macro + terminal, producer lands first) | Advice-filter test green; golden parity (js↔py) green in both repos; PR #170 panel unbroken (renders v2 as v1); **any NEW engine module the API imports is added to the `app/deploy/update.sh` restart regex + `tests/test_deploy_update_self_heal.py` in the same PR** (else the VPS serves stale code silently) |
| **W4 — options lane** | ctx `vol/gex/flow.opt` blocks (behind OIP freshness anchors) + watchlist `options_vol` chip + book options-posture panel + brief options section. (macro; terminal panel rides W3 schema) | Stale-plane degradation path demonstrated (kill the artifact in a fixture → coverage_missing chip, no fabrication) |
| **W5 — tape context** | ctx `market` consumers: watchlist L3 strip widening + packet `tape` + brief sentences; per-read link-outs + LENS receipts. (macro) | No new classifier; every chip traces to a named artifact + asof; MSP-R2 audit note in PR |
| **W6 — ladders + drawer depth** | Weakest-links / Working-for-you lists both surfaces; per-name drawer v2 rows; dossier link-outs; optional user conviction tag (supabase column + RLS in same PR — and commit the FULL `portfolio_positions` DDL as the schema-of-record while touching it: census found the CREATE TABLE was never version-controlled, only the RLS in `templates/uwp_supabase.sql`). (macro + terminal) | Ladder ordering = named rung + printed count ONLY (reviewer asserts no hidden scalar) |
| **W7 — outcome ledger + Lab** | `data/psi_ledger/` nightly appender (universe + archetypes, budget-stamped, off render path) + Calibration Lab section. (macro) | Ledger rows carry construction versions; no user data (grep-gate in CI); Lab copy below-the-fold, falsifier-language law |
| **W8 — weighting prereg + launch sanity memo (docs+study)** | `research/PSI_COMPOSITE_PREREG.md` (§12 gates frozen) + Study-1 runner + the §12 launch sanity read on the v0 construction. | Prereg committed BEFORE any study code runs; DNR §3 estimator fences cited inline; **W9 may not ship the score without the sanity memo** |
| **W9 — Portfolio Health Score** | §3.1 score: client (`risk_core.js` extension) + server (composer `score` section) + goldens; hero UI both surfaces (design-first, crops); Tier-2 receipt (version/weights/coverage/grading status); §11 ledger grades it from day one. (macro + terminal) | §3.1.2 construction law asserted in review; anon and signed-in identical score on fixtures; scope-fence grep (score consumed nowhere outside display/digest) |
| **W10 — Public portal + funnel** | §19.2 anon-flow polish + conversion moments; §19.3 landing page `portfolio_analyzer.html` (public-nav family, live demo widget, SEO/zh); §19.4 onboarding portfolio step; packet re-tier to free-account (§19.1). (macro; design-first, Luna) | Gate 11 (zero walls before value) e2e-verified anon→analysis→signup→fold-in→tracked; SEO collision check vs #4330/SEO-Supercharge recorded in-PR; onboarding degrade-to-skip proven |
| **W11 — Daily digests** | §19.5: change-detection composer (brief-v2 builders reused), mailer integration (`cls='marketing'`, idem per user-day), prefs toggle + account UI, digest-cursor table (DDL+RLS in-PR), quiet-day suppression, weekly heartbeat default. (macro) | Gate 12 end-to-end: opt-in → change → ONE email → one-click unsub honored (live test); no position values in email_log/server logs (grep gate); mail-off mode degrades clean |
| **W12 — Ticker news feeds** | §19.6: portfolio news panel + drawer rows (anon client-join; packet `news` for accounts); news.html per-ticker feed views + "your book" filter. (macro) | ACTIVE_BUILD_MAP re-check vs live news/x-growth lanes recorded in-PR; verbatim display only (no LLM re-summary — A7) |
| **W13 — Live layer + web-app polish** | §19.8: `/api/pfolio/quotes` batch endpoint (quote-ladder wrap, rate-limited, delay-honest), visible-tab polling, optimistic-edit recompute, per-name expandable rows + `ilx` sparklines, Company-Intel drawer card (§19.7), Terminal deep links. (macro + tiny terminal link PR) | Quote labels carry the honest delay vocabulary; hidden-tab pause proven; reduced-motion honored; endpoint added to the restart regex + self-heal test |
| **W14 — TNI data plane** | §19.6.1: extend the financial_news bake with category tagging (`cats[]`: deterministic rules + our filings/analyst/earnings planes as first-class rows), per-ticker `ticker_news.v1` artifact (headlines cap, cluster-dedup, day grouping + `chg_pct` stamp from closes), R2 publish + `/api/news/ticker/{T}` read-through (+batch). (macro) | Price stamps hand-verified on fixtures; artifact size + nightly runtime budget printed; endpoint in restart regex + self-heal test; ACTIVE_BUILD_MAP re-check vs news/x-growth lanes recorded in-PR |
| **W15 — Key Facts curation lane** | §19.6.2: nightly LLM lane behind the breaking_summary-class citation gate (digit-verbatim, stance-ban, deterministic fallback), material-news qualifier, cluster→bullet, source chips, budget cap + ceiling, append-only day timeline. (macro) | Zero LLM calls in tests (env-gate pattern); gate violations provably fall back (fixture with a fabricated digit → deterministic lead sentence); A7/NAR-R4 fence note in PR; cost log printed per night |
| **W16 — TNI surfaces** | §19.6.3: Terminal Analysis-pane News section (Key facts / Headlines + category chips, timeline idiom); macro reader component (stock pages + portfolio drawer + news.html?t= views + "your book" filter); packet/digest `news` upgrade; X-growth supply-feed publication note. (macro + terminal; design-first, Luna) | Crops en+zh both idioms; east-flip-safe move colors; verbatim-content law (no re-summarization client-side); news.html lane collision check |
| Come-backs (tracked, not built now) | Foreign factor models (WRI §5-A: Asia-close collection lane first); realized-corr client-side bake; UWP W2.5 multi-list UI; alerts/sentinel symbol-only extension (B6 pattern); regime-conditioned thresholds study; tape-character read prereg; deterministic fundamentals score-leg from forensics planes (§19.7); macro-quotes Worker upgrade (billing) | Each needs its own small charter/PR |

Sequencing: W1 → W2 → W3 form the critical path. W4/W5/W6 are parallelizable after W2
(W4's terminal render rides W3). W7/W8 independent after W2; **W9 requires W7 (ledger
live) + W8 (sanity memo)**; W10 requires W9 (the score is the landing hook) and lands
the packet re-tier with it; W11 requires W2+W3 (diff source + composer) and should
follow W9 so digests carry the score; W12/W13 parallelizable after W2. TNI is its own
mini-chain W14 → W15 → W16, startable any time after W2 — the news.html + Terminal
reader halves are independent of the portfolio waves entirely and may ship early if the
operator wants the news product first (W16's drawer/digest touchpoints ride W3's
packet). Suggested order after the critical path: W7 → W8 → W9 → W10/W11 in parallel →
W14/W15 → W12/W16 → W13 → W4/W5/W6
interleaved where idle. Every macro PR: label `merge-on-green` and let the sweeper land
it; every terminal PR: the terminal repo's own definition-of-done (PR → CI → merge →
`/opt/terminal/terminal-build.sh` deploy → live verify at app.mastermind-x.com).

## 15. Codex execution protocol (operator-directed)

- **Subagents**: run this program with **Sol, Luna, and Terra** as standing lanes —
  **Sol** = data/engine lanes (W2 ctx bake, W3 composer + goldens, W7 ledger, W9 score
  math, W11 digest engine, W13 quotes endpoint: pure functions, tests-first, budget
  stamps — plus the W14 TNI bake and W15 curation lane); **Luna** = design + UI lanes
  (the §13/§19 design-spec-first waves: mockups → crops → exact markup/CSS pinned →
  then build; Luna owns the score hero, the landing page, the onboarding step, the
  web-app polish, the W16 news reader/timeline on BOTH idioms — never ships a surface
  without the crops); **Terra** = verification/QA lanes
  (field-presence census, golden parity harness, advice-filter/privacy/scope-fence grep
  gates, email-compliance live tests, anon-funnel e2e, live verification passes, the §0
  gate checklist on every PR). The main Codex loop plans, adjudicates, reviews Luna's
  design against §13/§19, and owns merges.
- **Efficient model use**: route mechanical sweeps (census, fixture regeneration, crop
  capture) to the cheapest capable tier; reserve the strongest tier for design choices,
  the composer/math code, and adversarial review of every wave (this repo's routing
  law is the template: strong models build/review/design; cheap models do mechanical
  non-code fan-out; nothing mechanical inherits a frontier tier by default).
- **Design care (operator's explicit ask)**: important UI is conducted CAREFULLY —
  DESIGN_DOCTRINE + the frontend-design skill loaded before any surface work; macro
  surfaces must read as native macro.html/WRI family (tokens, rail headers, LENS,
  dual-span i18n, light+dark), Terminal surfaces as native v5/obs family (dark, mono
  numerals, `.obs-card`, east-flip safety). When a design choice fails the
  draft-and-review test, STOP and put it through the strongest lane, not a builder.
- **House discipline (this repo's AGENTS/CLAUDE laws apply to you)**: fresh
  `origin/main` worktree branches; never reuse a squash-merged branch; no bare
  `git stash`; paired template/site plain-copy assets in the same PR
  (`python -m scripts.check_template_site_sync --fix`); GitHub annotations start the
  line; `merge-on-green` label finish; read `docs/ACTIVE_BUILD_MAP.md` before each wave
  (the sector-intelligence and prophet-board lanes are active nearby); append any NEW
  kill you adjudicate to `research/DO_NOT_REBUILD.md` in the same PR (sections 1–4 only,
  regen the compiled blocklists).
- **Cross-repo law**: macro is the producer/authority (entitlements, artifacts, math);
  terminal consumes via same-origin proxy routes (PR #170 pattern — server-verified
  Supabase session → bearer to gateway; macro-api has NO CORS by design, so the browser
  can never fetch it cross-origin; never trust client-supplied auth headers). Tier
  checks ALWAYS resolve through macro-api / `user_entitlements` — do NOT copy the
  Terminal's legacy `profiles.is_pro` boolean into anything new (census found it is the
  only server-enforced Terminal gate today and it is NOT the entitlement authority; the
  known unimplemented `terminal_indicators` gap in `config/plans.yml` is out of PSI
  scope). Note: Terminal auth is currently soft (`TERMINAL_REQUIRE_AUTH` unset — pages
  are public; the Supabase session still resolves server-side where present), so W1's
  live verification must use a REAL signed-in Pro session, not rely on route gating.
  Check both repos' AGENTS files before touching either.

## 16. Verification bar (beyond §0)

- Golden-file tests for every composer section (byte-identical, fixed today/generated_at).
- js↔py parity goldens green in both repos (§5.3).
- Unit tests with hand-computed fixtures for every new statistic (realized ρ on a 3-name
  toy book; HHI; vol ratio; replay window) — the fabricated-numbers burn happened twice;
  numbers come from parquets, never from prose.
- Privacy grep-gate: CI fails on any log/artifact write containing shares/entry_price
  fields outside the supabase client paths.
- Budget stamps printed by the bake + ledger jobs and asserted <60s in tests-with-tolerance.
- Live: real-book demo for the operator (their own watchlist), not synthetic screenshots
  — the BRIEF §8 bar stands.
- The 5-second cold-reader test on every new panel (DESIGN_DOCTRINE §5.1), en + zh.

## 17. Non-goals (restated so nobody re-opens them)

No score AUTHORITY — the Health Score never feeds boards/rankers/NW/sizing/alerts or any
engine read, and never leaves the portfolio-display + digest layer (§3.1.2 fence); no
sizing/allocation/optimizer/hedge suggestions; no VaR/ES; no short signals; no new
estimators or classifiers (incl. any "market character" read) without prereg; no per-user
compute on the render path; no engine reads of user holdings (two-organisms); no new
collectors (foreign factor models stay chartered-not-built); no operator held-desk changes
(Mastermind §5–9 untouched); no LLM-originated content in the brief, digests, or score
(A7); no "validated"; no falsifier vocabulary on user surfaces; no dark-pattern signup
walls in the freebie flow (gate 11).

## 18. Open items defaulted (operator may override; defaults chosen so Codex is never blocked)

1. **Tier gating (superseded by §19.1 round-2 directive)**: anon = full client-side
   analysis incl. the Health Score; free account = tracking + daily digests + the server
   `data` packet (realized corr, options posture, richer news); Pro = AI narrative brief
   sections + Brain portfolio chat + deepest options + unlimited AI. DEFAULT: as stated;
   the operator may re-slice which packet rows are free vs Pro without re-chartering.
1b. **Digest cadence**: 1/day hard cap, change-triggered; weekly "all quiet" heartbeat ON
   by default (operator may kill); send window = post-nightly morning ET. DEFAULT: as
   stated.
2. **ctx size overflow**: if v2 exceeds 2.5 MB → split sidecar `portfolio_ctx_x.json`
   (options/filings detail) lazy-fetched. DEFAULT: measure first, split only on breach.
2b. **`psi_returns.v1` home**: R2 (options_hub publish pattern) with API-side TTL cache;
   the realized block degrades honestly when unreachable. DEFAULT: R2 (keeps site/
   lean and the render path light); a `site/data/` copy is the fallback option only if
   R2 operational friction shows up in W3.
3. **User conviction tag**: ships in W6 as an optional column. DEFAULT: ship.
4. **Terminal risk panels placement**: below the PR #170 brief, above the Conviction
   Book. DEFAULT: as stated (Luna may re-order within the page with crops as evidence).
5. **TNI knobs (§19.6)**: material-news qualifier = quality-score floor + cluster ≥1
   top-tier source; Key Facts model = cheapest capable tier, batched, hard nightly
   ceiling with carry-to-fallback; headlines cap 50/ticker; key_facts served window
   90d; zh fact text = deterministic template + translated verbatim quotes only in v1
   (full zh LLM parity is a v1.5 knob). DEFAULT: as stated.

---

## 19. The freebie funnel (operator directive 2026-08-03 round 2)

The portfolio analyzer is the site's **lead magnet**: give real value FIRST, anonymously;
convert to a free account for permanent tracking + daily emails; let the paid relationship
grow from love of the free tier. This section charters the funnel infrastructure. The
existing UWP logged-out mode + localStorage→Supabase fold-in (already built,
`templates/watchstore.js`) is the funnel's spine — the anon→signup handoff costs ZERO new
storage code.

### 19.1 Tier ladder (DEFAULT — §18.1 governs overrides)

| Tier | Gets | Mechanism |
|---|---|---|
| **Anonymous** (no account) | The FULL client-side analysis instantly: Health Score + sub-scores, Book Posture, lane chips + ladder, tape strip, per-ticker context joins (sector/theme/stage/earnings/news counts) — computed in-browser from public baked JSON; book kept in localStorage | Existing UWP local mode + WRI math + ctx/`by_ticker` public JSON; no server calls with holdings |
| **Free account** | Everything anon has, PLUS: book synced + tracked forever (Supabase), **daily change-triggered digest emails**, the server risk packet (realized corr, options posture, richer news feed), score history over time | Signup → watchstore fold-in (built) → `/api/portfolio/brief` re-tiered to free-account (was Pro) |
| **Pro** | The AI-composed prose brief ("through the desk's eyes" narrative sections), Mastermind/Brain portfolio chat, deepest options analytics, unlimited AI runs — the existing Pro pillar, now sitting ON TOP of a generous free layer | Existing entitlement machinery; endpoint splits `data` (free) from narrative `sections` (Pro) |

Re-tiering note: the BRIEF charter made the brief Pro-only; the operator's round-2 funnel
strategy supersedes that for the DATA packet. The endpoint keeps ONE route; tier resolution
decides which parts render (packet → free account; narrative prose + Brain → Pro). Anon
users never hit the endpoint at all (client math). Update `config/plans.yml` feature rows +
the pricing matrix ONLY when the feature is live (BRIEF §5 discipline).

### 19.2 Anonymous instant-analysis flow (zero walls — gate 11)

Enter tickers (+ optional shares/cost) on the portfolio surface or the landing widget →
full analysis renders in-browser in seconds. No login, no email capture, no regwall before
the value. Conversion moments (dismissible, value-framed, Luna designs them): after first
analysis ("keep this tracked — we'll watch it nightly and email you when something
changes"), on return visit with a local book, on score change between visits (client can
diff against the localStorage snapshot). The localStorage book survives; signup folds it
into Supabase (existing code path — verify it in W10's e2e).

### 19.3 Public landing/portal page (new, after the product is built)

A dedicated marketing/SEO page — `templates/portfolio_analyzer.html` (public-nav family,
`_public_nav.html.j2` + landing idiom `landing.css` conventions; the landing/products
pages #3893/#3962 are the design benchmark) — with: hero + a LIVE demo widget (the real
client-side analyzer seeded with an example book, "try your own" input), feature story
(score → lanes → tape → emails), honest screenshots, CTA into the real surface. SEO: this
page joins the sitemap + entity package estate; check `#4330` (SEO entity package) and the
SEO Supercharge charter for collisions before building; hreflang/zh parity per house SEO
law. The funnel law (spawn-handoff §7) applies: the EXPERIENCE lives where the users are
— the landing page sells it, `watchlist.html` IS it.

### 19.4 Onboarding integration

The signup/onboarding flow (the landing `onboard.js`/`onboard.css` estate) gains a
portfolio step: "add the stocks you own — we'll analyze and track them" (skippable, with
the analyzer preview inline where feasible). If the user arrived FROM the analyzer with a
local book, the step becomes a confirm ("we found your 8 names — track these?"). Careful:
the onboarding estate shipped through the 2026-07-23 postmortem — read
`spawn-handoff-quality-law` gates before touching it; crops required; the flow must
degrade to skip cleanly.

### 19.5 Daily digest emails (the retention engine)

- **Pipeline**: a nightly post-ctx job (off render path, macro-api host or ops lane) that,
  per opted-in free/Pro account: loads the user's book (Supabase), composes the DIFF vs
  the previous ctx (role transitions per name, lanes newly elevated/cleared, score delta,
  posture change, earnings entering the 10-day window, news items on holdings, tape-state
  changes touching the book), renders a deterministic bilingual email (brief-v2 section
  builders reused — same composer, email template skin), and sends via `app/mailer.py`
  `send(cls='marketing', idem_key=f"psi_digest:{uid}:{asof}")` — idempotent per user-day,
  suppression-honoring, one-click unsub (gate 12).
- **Change-triggered**: a quiet day (no diffs) sends NOTHING. A weekly "still watching —
  all quiet" heartbeat is a §18 default (ON weekly, operator may kill it).
- **Privacy**: the job reads user books at send time and persists ONLY send-ledger
  metadata (`email_log` row — no position values, no per-name states in the ledger).
  Digest state cursor (last-sent asof + last state hash per user) lives in a new
  Supabase table (RLS, DDL in-PR per UWP-R5) — NOT in repo artifacts.
- **Consent**: explicit labeled toggle at signup + account page; `email_prefs` digest
  field; transactional-class mail is NOT used for digests (they are recurring bulk).
- **Ticker-status emails** ("changes in each ticker's status") ride the same digest —
  per-name sections inside one daily email, never N separate emails per user per day
  (frequency cap = 1 digest/day hard).

### 19.6 Ticker News Intelligence (TNI) — the two-mode reader + Key Facts timeline
### (operator directive round 3, 2026-08-03 — TradingView-benchmark assessment: FEASIBLE)

**Feasibility verdict (assessed against the repo 2026-08-03): YES — most of the machine
exists.** The reference product (two reading modes: a raw **Headlines** feed with
category filters, and a curated **Key Facts** day-timeline where each day carries the
stock's move and 1–N sourced fact bullets) decomposes onto substrate we already run:

| Reference capability | Our substrate (exists) | Gap to build |
|---|---|---|
| Per-ticker tagged headlines, many sources | `engine/financial_news.py` — Polygon `/v2/reference/news` (**pre-ticker-tagged corpus**), Finnhub, GDELT; deterministic `news_common.quality_score` (source tier × relevance × recency − clickbait) + dedup; per-ticker index already published (`site/news/by_ticker.json`) | Deepen retention per ticker; category tags |
| Category filter tabs (Earnings/Divs/Buybacks/M&A/Insider/Analysts) | Earnings wire + earnings detector (x-growth), `engine/analyst_revisions.py`, insider/congress filings desks, capital-structure verified events | Deterministic keyword/rule tagger at ingest (`cats[]` per item) + OUR OWN regulatory rows as first-class entries (insider/analyst tabs fed by our filings data, not just headlines — better than the benchmark) |
| Key Facts LLM curation w/ source chips | `engine.news_llm` layer (optional summaries + importance re-rank, "never gates a headline in or out"); `engine/marketing/breaking_summary.py` — the CITATION GATE: every digit-token verbatim in source, stance vocab banned, deterministic fallback, env-gated LLM; `qbus` item/event store + `news_events` identity layer; intelligence-desk clustering floor (#4006) for same-story grouping | The per-ticker nightly curation lane (below) |
| Day grouping + that day's stock move | `data/stocks/*.parquet` closes at bake time | Pure-arithmetic join (close-to-close %) — trivial |

The benchmark's Key Facts is almost certainly LLM-assisted; ours is lawful because every
generated bullet passes the breaking_summary-class gates and carries its source chips.

**19.6.1 Data plane — `ticker_news.v1`** (nightly lane, OFF the render path, R2 home —
the per-ticker corpus is too heavy for `site/` git):
- Per ticker with material coverage: `{headlines: [{ts, title, src, url, cats[],
  cluster_n}], key_facts: [{date, close, chg_pct, title?, facts: [{text_en, text_zh?,
  srcs[]}]}]}` — headlines capped (~50, cluster-deduped with `+N` source counts like the
  benchmark), key_facts append-only forward by day (~90d window served; full archive
  retained in the store).
- Served via a new unauthenticated read-through `GET /api/news/ticker/{T}` (the
  `app/hub.py` R2+TTL pattern; batch variant for books ≤60 syms). Endpoint joins the
  restart-regex law (W3 gate). The compact `intelligence.by_ticker.v2` stays as the
  cheap counts join for ctx/packet.
- The existing live news rail machinery covers "today" freshness on news.html; the
  per-ticker artifact updates nightly in v1 (intraday per-ticker appends = v1.5
  come-back riding the existing live-rail plane, not a new one).

**19.6.2 Key Facts curation lane (the LLM part — fenced):**
- Runs nightly AFTER the news bake, only for tickers with ≥1 qualifying story that day
  (`quality_score` floor + cluster size — most of the 1,500 universe has zero material
  news most days, which is what makes this affordable; budget cap + per-night ceiling
  printed in the job log; on cap breach the remainder carries to the deterministic
  fallback).
- Per (ticker, day): cluster same-story items → per-cluster ONE fact bullet via the
  news_llm/breaking_summary path — **citation gate mandatory** (every digit-token
  verbatim in source text; stance/advice vocab banned; deterministic
  lead-sentence fallback on any violation or LLM failure), source chips per bullet,
  cheap model tier, batched.
- **Fences (binding):** the bullets are display CONTENT, never keys — no organ state,
  no escalation, no tag feeding anything scored (A7; NAR-R4 frame-tag ban; CSP-R3's
  killed LLM contagion-tagging stays dead; this lane writes prose + receipts only).
  The day's `chg_pct` prints NEXT TO the day's facts as juxtaposed facts — copy never
  asserts causation ("what happened that day", not "why it moved").
- The (day, facts, move) archive is a genuinely valuable **event-study substrate** —
  recorded as research-tier byproduct; any signal use needs its own prereg (display
  now, science later).

**19.6.3 Surfaces (all three, one artifact):**
- **Terminal — Analysis pane News section** (new tab set: `Key facts | Headlines`,
  category chips on Headlines): consumes `/api/news/ticker/{T}` via a same-origin proxy
  route (nw/route.ts pattern). Timeline idiom per the benchmark: day nodes on a spine,
  date + close + signed % (via `var(--up)/--down)` — east-flip safe), fact bullets with
  source chips. v5/obs tokens; en+zh.
- **Macro — portfolio drawer + stock pages**: drawer news rows (latest headlines +
  latest key-facts day) already chartered above; `site/stocks/<T>.html` static dossiers
  gain the Key Facts timeline section (render-time inline of the recent window from the
  data copy, budget-checked) + client hydration for freshness.
- **news.html**: the per-ticker feed views ("news.html?t=NVDA" + "your book" filter)
  render BOTH modes with the same reader component (macro idiom twin of the terminal
  component; LENS receipts for methodology).
- **Portfolio packet/digest**: the `news` section upgrades to carry the latest
  key-facts day per holding (digest shows "MSFT: 3 facts yesterday, +3.0%").
- **X Growth**: `ticker_news.v1` becomes an available SUPPLY feed for the content
  pipeline's existing admission lanes — no posting wired here (the queue-bypass law:
  generation/admission laws live in the marketing estate; we only publish the artifact).

Collision check before building: the news rail + x-growth wire lanes are hot
(ACTIVE_BUILD_MAP re-check in-wave), and `engine.news_llm`'s existing importance re-rank
must not be double-applied.

### 19.7 Company Intelligence context (the "insane" differentiator)

The just-shipped Company Intelligence estate (per-ticker dossiers #4318/#4322, verified
earnings evidence graph #4260-family, capital-structure/forensics planes, public teaser
endpoint `app/company_intelligence.py` — allowlisted VERIFIED field projection,
CDN-safe) joins the portfolio view:
- **Per-name drawer**: a Company Intelligence card — the teaser projection for anon
  (public endpoint), the fuller authenticated context for accounts — earnings-call
  key facts, evidence-bound filing changes, dossier link-out. Fields render VERBATIM
  from the contracts (`company_intelligence_context.v1` is `context_only` authority —
  its own contract governs).
- **Scoring boundary (binding)**: `context_only` artifacts and any LLM-derived
  transcript features may NOT be score legs (A7 + the artifact's own authority tier —
  Amendment 2 did not touch either). Deterministic receipt-bound numerics (XBRL-derived
  fields from the forensics/capital-structure planes) MAY become a future
  fundamentals leg via a versioned §12 PR once those planes expose a stable per-ticker
  projection — tracked as a come-back, not built now.
- **Digest**: verified company-intel EVENTS on holdings (new filing evidence, earnings
  story updates) are digest-eligible diff items (facts with receipts, not narratives).

### 19.8 The live, web-app-grade macro frontend

The operator wants the macro side "beautiful and quite web-app like, since it should be a
very live feature," showing ticker data in place. Architecture: KEEP the static-page +
JS-island model (render-budget-free; UWP-R6 offline-degradable) and make the islands
live:
- **Live quotes layer**: a new thin macro-api endpoint `GET /api/pfolio/quotes?syms=…`
  wrapping the EXISTING server quote ladder (brain_gateway `get_quote` legs: quote-hub
  batch → VPS `quotes_full.json` snapshot — #4250) with the same honest delay vocabulary
  ("≈15-min delayed" labels), rate-limited (view_ratelimit pattern), no auth required
  for quotes (they're public data), batch-capped (≤60 syms). The portfolio page polls it
  on a visible-tab interval (60s default, pause on hidden tab), updating last/chg cells
  + book value with a subtle tick animation (reduced-motion honored). The dormant
  `macro-quotes` Worker (UWP W4) remains the upgrade path if polling load demands it —
  billing decision unchanged.
- **Web-app feel** (Luna's design brief): instant-render skeletons; optimistic CRUD on
  positions (watchstore already local-first); live score/posture recompute on every
  edit (client math is pure — recompute is free); per-name expandable rows with
  quote + day range + mini context (stage word, sector class, next earnings, news
  count) and an `ilx` sparkline (SSR-safe, never Plotly); smooth section transitions;
  the page never blocks on network (baked JSON first, live layers hydrate in).
- **Per-ticker data in place**: the drawer (§13.1 ⑤ + §19.6/19.7 rows) is the "show
  ticker data there" answer — quote, technical state, options context, news, company
  intel, dossier/stock-page link-outs (`site/stocks/<T>.html` static dossiers exist for
  ~1,595 names).
- **Terminal linkage**: deep links both ways — each holding row links to the Terminal
  chart (`app.mastermind-x.com` symbol route) and the Terminal Portfolio page links
  back to the macro analyzer; the SAME Supabase book renders on both (already true);
  brief v2 packet renders on both (W3). Live quotes on the Terminal side stay on ITS
  quote hub (separate plane — do not cross the streams).

## App-A. Engine/artifact inventory (verified 2026-08-03 — grep before wiring, never from memory)

**Signal-bus governance:** `config/synapse.yml` (~583 registered artifacts) is the
authoritative registry (tier ∈ display|shadow|confirmer|scored|infrastructure). New
producers (psi_returns, psi_ledger) REGISTER THERE FIRST (CI-gated by
`scripts/check_synapse_registry.py`), then stamp with `engine.neuralweb.envelope.stamp()`
(sibling keys, never a wrapper). Consumer entry points: `engine/neuralweb/read.py
load_world_state()` (staleness-guarded composed macro state), `engine/neuralweb/query.py`
(graded cross-engine signal history, PIT-safe), `engine/neuralweb/context_api.py
context_snapshot(ticker)` (research-side PIT per-ticker snapshot across 11 dimensions —
the reference for what "master tracking on every ticker" can already answer).

| Domain | Engines / artifacts (paths) |
|---|---|
| Regime | `engine/regime.py` → `data/regime/latest.json` (quad, cycle_tag, transition_state, + embedded risk_radar/vol_regime/dislocation/cross_asset/market_drivers/fed_path/fed_stance blocks); `regime_hmm.py` (soft probs, display-only); per-market `china/hk/canada/intl/forex/btc_regime.py`; `regime_prior.py` (conditioning prior for cycle pages) |
| Stress / turbulence | `engine/risk_radar.py` (5 evidence-gated scare families; state/top_score/dominant_scare/drawdown_prob; forward log `data/risk_radar/forward_log.jsonl`); `engine/cross_asset.py` (Kritzman–Page absorption ratio, corr matrix, top_pairs → `data/crossasset/latest.json`); OFR FSI reference `data/ofr_fsi/` |
| Vol | `engine/vol_regime.py` (VIX term slope, MOVE, VRP, SKEW, VVIX/VIX; `latest.json['vol_regime']` + `site/vol/regime.json`); `vol_forecast.py` (HAR); `vol_squeeze/velocity/sentiment/shock_scorecard` |
| Dispersion | `engine/dispersion.py` → `data/dispersion/regime.json` (`dispersion_regime.v1`: lean_in/neutral/lean_out, pctile, avg_corr) |
| Correlation (market) | `engine/neuralweb/covariance_spine.py` → `data/neuralweb/covariance_spine.json` (+site copy): factors_effective_bets, effective_independent_lobes, same_bet_warning |
| Breadth | `collectors/breadth.py` → `data/breadth/breadth.parquet` (adv/dec/nh/nl/pct_above_50/200, ad_line); `engine/advanced_breadth.py` (McClellan/ZBT/High-Low — display-only per RRX rulings); intraday `site/live/breadth.json`; per-market breadth stores |
| Concentration | NOT BUILT as an engine — risk_radar bubble leg `cap_leadership` flag; `index_leadership.py` display ratio; W5 adds the top-10-share printed fact from `data/breadth/constituents.parquet` |
| Rotation / stage | `engine/us_sector_rotation.py` (`us_sector_rotation.v1`); `engine/subsector_rotation.py` (RRG quadrants → `site/marketdata/subsector_rotation.json`); `engine/weinstein_stage.py` (`data/stage_analysis/` boards — the ctx `stage` source); `rotation_events*.py` ledgers; `sector_cycles/china_sector_cycles/country_cycles` forward logs |
| Sector/theme flow | `engine/group_flow.py` → `site/basketdata/flow.json` (per-basket EMERGING/CONFIRMED/EXHAUSTED fingerprints); `theme_flow_rollup.py`; intraday `live_flow`/`intraday_flow` lanes |
| Rates / policy | `engine/rates_inflation_command.py` → `data/rates_command/latest.json` (`rates_command.v1`, deterministic stance sentence); `fed_path.py`; `fed_stance.py`; `rate_inflation_transmission.py` (sector map); `policy_intent_desk.py` + policy calendar family; China policy watch estate |
| Geopolitical | `collectors/uncertainty_indices.py` → `data/uncertainty/gpr.parquet` (GPR threat/act) + `epu_us.parquet`; `engine/dislocation.py` geo_reversibility (context-only) |
| Per-ticker technicals | `engine/extension.py` (ext_z, grade incl. parabolic, near_52wh); `engine/rsi_stack_signals.py` (stack oversold/overbought, curls); `technicals.py`; `tech_catalog.py` → `site/factordata/tech_lab.json` (30+ families; NW ledger DARK); `pullback_zone.py`; washout watchers (`hk_washout_watch.py`; `mag7_washout.py` background-only) |
| Factor model | `engine/factor_exposure.py` → `site/factor_betas.json` (9F orthogonalized betas + factor_cov + factor_cov_stress + idio_vol + confidence tiers, ~1,529 names incl. crypto) — the WRI math spine |
| Options (OIP) | ThetaData EOD store (~380 roots, 2012–2026; ops-Mac `~/flow-ops-wt/data/thetadata_eod`, R2 mirror `thetadata_eod/`; reader `engine/thetadata_store.py`, OI shift-1 law); `options_surface.py` (GEX/VEX/CEX buckets); `options_structure.py` (gex_state/chain_heat/matrix, authority_tier tagged); `options_skew.py`; `options_ivspread.py`; `options_hub.py` + `scripts/build_options_hub_nightly.py` → `data/live_flow_out/options_hub/` + R2 (IV-rank, GEX, OI movers, max pain, hot contracts); `gex_model.py`/`gex_state.py` (gamma_regime, flip, walls, pin_probability); API `app/hub.py` `/api/hub/*` (R2 read-through, 30s TTL — the pattern §7.2 reuses) |
| Per-ticker boards / dossiers | `site/factordata/us_standouts.json` (master US board, 13 consumers, scored-path: board_ordering/top_setups — do NOT touch from PSI); `engine/stock_dossier.py` (buy-decision packet rows); `scripts/build_ticker_pages.py` → `site/stocks/<T>.html` (~1,595 static dossiers); `site/stockbrief/<T>.json`; `engine/company_intelligence/` (context_only wire contract) |
| Filings / ownership | insider_signals, beneficial_ownership, congress (parquet), smart_money 13F (ctx v1 sources); positioning/short_volume (context-only per Signal Commons) |
| Taxonomy / universe | `data/baskets/membership.json` (47 baskets, 36 curated; per-market siblings); `data/breadth/ticker_sectors.parquet` (~1,516 ticker→sector); `data/universe/membership.parquet` (3,548 rows: r2000/sp600/sp500/sp400 — broadest defined universe, NOT synapse-registered); `data/symbol_directory/` (all-listed daily snapshots) |
| Price stores | `data/stocks/*.parquet` (US deep history, yfinance-max, build-host only — NOT on VPS, NOT in git); `data/yahoo/` (ETF/index); per-market stores (`china/hk/canada_stocks`); Terminal has its own separate Polygon pipeline (~3,000 US + HK/A-share) — irrelevant to PSI math |
| Grading / calibration | `engine/track_record.py` + `engine/grading.py` (append-only forward grading, no-look-ahead, next-bar fill — §11 reuses); `engine/calibration_hub.py` → `site/calibration.html` (promotion gates: Holm α, empirical nulls, trial_ledger); `scripts/build_measurement.py` → `site/measurement.html` (cycle measurement hub — untouched) |
| Per-user plumbing | Supabase `fsldfzlxyavsuwqbceod`: `watchlists`/`watchlist_symbols`/`portfolio_positions` (+`profiles` legacy, `user_entitlements` tier authority via `scripts/deploy/0005+`); `app/main.py` `require_user` (bearer → GoTrue verify); `app/paywall.py` (fail-closed, `config/site_access.yml`); brief endpoint + `engine/portfolio_brief.py` composer; `templates/watchstore.js` client CRUD; deploy: `app/deploy/update.sh` restart-regex law (W3 gate) |

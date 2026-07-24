# Watchlist Risk Intelligence (WRI) — masterplan (by Fable)

Date: 2026-07-24
Status: CHARTER + adjudication of record. Operator-directed (2026-07-24 session): revamp
`watchlist.html` into a robust risk-detecting surface — per-position risk, book-level
uncorrelated-risk structure, grounded in how institutions actually do this.
Parents: `PORTFOLIO_RISK_DESK_MASTERPLAN_BY_FABLE.md` (lanes + ladder + Amendment 1 carve-out),
`UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md` (UWP-R1..R7, store + dashboard).
Registries consulted: `docs/ACTIVE_BUILD_MAP.md` (2026-07-24 — no colliding open lane),
`research/DO_NOT_REBUILD.md` (rows 44 fused-score, 104 volume-fingerprint, 106 forced-call —
all honored below), `config/ruling_graph.yml` (NWC-U4, NWP-U18, RUL-F3.2, PRD-R2/R6/R7).

## 0. ACCEPTANCE GATES (any UI wave is "not done unless")

1. Fresh end-to-end happy path with zero manual workarounds: empty watchlist → add 8
   correlated tech names → Book Risk verdict reads ONE BET with named twin cluster and
   factor share; add GC=F → coverage chip degrades it honestly; sign-in → synced.
2. Per-wave visual crops (light + dark + zh) posted in the PR body, against the pinned
   design spec (W2). No self-merge of first-pass UI PRs — operator/orchestrator review.
3. **No fused composite risk number anywhere on the surface** (PRD-R2): aggregates are
   printed lane counts, named states, and single-construct statistics per WRI-R2 only.
4. No advice verbs (buy/sell/add/trim as imperatives), no "validated" (CI-enforced), every
   panel answers "so what do I do" in review language — even when it's "watch, don't chase".
5. Banned-vocab / glance-tier compliance per `docs/DESIGN_DOCTRINE.md`: no internal study
   names, no untranslated stats, no raw slugs on the glance tier; technicals demoted to
   hover/detail. Bilingual EN/ZH; no translated text in `title=` attributes.
6. Out-of-model tickers never break the page: excluded from factor math, present in the
   list, chip says what's missing (PRD-R6 pattern). Supabase unreachable → localStorage
   degrade with plain sync chip (UWP-R6).

## 1. One-line verdict

Surface the risk machinery this repo already computes but never shows the user: port the
Risk Desk's deterministic per-position lanes client-side, and build the missing **book
structure layer** — factor-implied correlation, effective number of bets, per-position
risk contribution, stress-conditioned co-movement — from the already-baked orthogonalized
9-factor model (`factor_betas.json`: betas + factor_cov + idio_vol, 1,529 names), rendered
as named states and plain words on `watchlist.html`; **no fused score, no sizing advice,
no new estimators**.

## 2. Gap map (what exists vs what's missing)

| Layer | Design | Artifacts | Surface on watchlist |
|---|---|---|---|
| L1 Per-position risk (lanes + ladder) | ✅ Risk Desk §6–7 (adjudicated) | ✅ mostly baked in `stockdata/<T>.json` blocks (verify in W1) | ❌ none — only the state badge |
| L2 Book structure (correlation / concentration / effective bets) | ❌ this doc | ✅ 80% baked (`factor_betas.json` betas+cov+idio); ❌ stress-day cov | ⚠ thin: FX panel shows net betas + risk shares; no pairwise corr, no ENB, no verdict, no twins |
| L3 Regime × book (the tape you hold it in) | ⚠ pieces (risk_radar, vol_regime, market_state) | ✅ baked in regime latest | ❌ not crossed with the user's book |

The operator's ask decomposes exactly into finishing L2, porting L1, and crossing L3.

## 3. How institutions actually do this — survey and honest verdict

The operator asked how institutions "do all of this perfectly." **They don't.** LTCM died
on correlation assumptions plus leverage; 2008 securitization desks died on Gaussian-copula
correlations that went to 1 in stress; Archegos's brokers each saw a slice and nobody saw
the book (aggregation blindness — the aggregate view IS the risk product); March 2020 hurt
risk parity when even Treasuries sold off in the bid-for-cash regime. What institutions do
have is a set of practices that survived those funerals. Each, and its verdict for us:

1. **Factor risk models (Barra/MSCI, Axioma, APT lineage).** Nobody estimates a raw N×N
   sample correlation matrix — for 20 holdings on 252 days it is mostly noise (the
   estimation-error literature from Ledoit-Wolf shrinkage onward exists because of this).
   Instead: regress every name on a small set of common factors; covariance = B·F·B′ + D
   (loadings × factor cov × loadings + idiosyncratic diagonal). The factor structure
   regularizes the estimate AND makes it explainable in words ("these two names are the
   same Growth/Tech bet"). **ADOPT — and it is already built:** `engine/factor_exposure.py`
   bakes orthogonalized marginal betas, `factor_cov`, and per-name `idio_vol`. The
   institutionally-correct method is also the bandwidth-correct one for a static site: a
   9×9 cov + per-ticker 9-vector reconstructs any pairwise correlation client-side — no
   N×N matrix ever ships.
2. **Diversification counting (Markowitz's free lunch, Meucci's effective number of
   bets).** Institutions do not ask "how many tickers" but "how many independent risk
   sources." A 12-name book that is all Growth/Tech is one bet with twelve logos. **ADOPT:**
   inverse-Simpson ENB over non-negative variance contributions (§7) — under our diagonal
   factor structure this is Meucci's principal-bets construction in its simplest honest
   form. This is the single number that answers the operator's "uncorrelated risk" ask.
3. **Risk budgeting / Euler decomposition (MCTR).** The institutional per-position number
   is not weight but *contribution to book volatility* — a 5% position can be 15% of the
   swing. Sums exactly to book vol, handles hedges as negative contributions. **ADOPT** as
   the per-row bar. Weight tells you what you paid; contribution tells you what you hold.
4. **Stress-conditioned correlation (Longin-Solnik exceedance correlations; every serious
   risk desk's scenario book).** Calm-window correlation is the wrong number for the only
   question that matters — what happens when it breaks. Desks maintain stress covariances
   and scenario overrides precisely because diversification measured on all days
   evaporates on the worst days. **ADOPT:** bake a second `factor_cov_stress` estimated on
   worst-quartile SPY days; the UI's default co-movement read uses the stress lens when it
   diverges ("move as one **in selloffs**").
5. **Limits + committee review, not scores.** Real risk governance is named exposures
   against named limits with an escalation ladder — a review process, not a 0-100 dial.
   This is *exactly* the house PRD-R2 lane+ladder law, independently converged. **ALREADY
   LAW.** The Risk Desk role ladder ports as-is; institutions also run **pre-trade checks**
   ("what does this order do to the book") — that is the W4 what-if, gated per WRI-R3.
6. **What institutions have that we refuse, deliberately:**
   - **VaR/ES daily machinery** — REJECT for the surface: false precision, distribution
     literacy nobody has, and the fused-number shape PRD-R2 exists to prevent. Book vol
     (an input measurement) is shown; "you won't lose more than X at 95%" is not.
   - **Optimizers (mean-variance, Black-Litterman).** REJECT: NWP-U18 bans construction
     in this repo, and the institutional experience is itself the warning — raw MVO is so
     unusable on estimated inputs that Black-Litterman had to be invented. We diagnose;
     the user constructs.
   - **Leverage/derivatives overlay risk.** Out of scope; self-entered cash-equity books.
7. **Institutional failure lesson that binds the design:** models are review inputs, never
   autopilots. Everything ships as measurement + named state + printed method; staleness
   downgrades confidence and never fires alarms by itself (PRD-R6); regime-dependence is
   disclosed on the glance tier, not buried (WRI-R7).

## 4. Adjudication vs existing case law

- EXIT-GRID-1 ("drawdown control is an entry problem"), TOP3-E5 hazard kill, FALS-OSC kill:
  nothing here predicts tops or fits estimators — WRI composes shipped display-tier
  artifacts with printed arithmetic. PRD-R5 restated: v1 fits nothing.
- DNR row 104 (volume fingerprints): untouched — no volume features anywhere in WRI.
- DNR row 106 (Mag-7 forced call): WRI makes no directional calls; it discloses structure.
  Book states are descriptive (what you hold), never market calls.
- Amendment 1 carve-out: user-facing display-tier watchlist+portfolio risk surface in this
  repo is lawful; operator held-desk stays in Mastermind untouched.

## 5. Rulings

- **WRI-R1 (placement/state):** all book math runs client-side from baked JSON; per-user
  state only Supabase RLS + localStorage (UWP-R1). Nothing position-derived is committed,
  logged with values, or written into macro artifacts (PRD-R7). Engine changes are limited
  to extending the *universe-level* factor artifact (stress cov, coverage stamps).
- **WRI-R2 (statistics vs composites — the boundary that makes L2 legal):** a *measured
  single-construct statistic* with a printed method — book beta, book vol, a factor's
  variance share, ENB, a position's risk contribution, a pairwise correlation — is a
  measurement and MAY display. A *fused multi-construct composite* — any blending of
  heterogeneous lanes (trend + solvency + events…) into one number, rank, or dial — remains
  FORBIDDEN (PRD-R2; DNR row 44). Lane aggregation is printed counts + named ladder only.
  The FX panel's existing "share of risk" language is the compliant precedent.
- **WRI-R3 (no construction, NWP-U18):** no optimizer, no suggested weights, no
  add/trim/hedge instructions. The W4 what-if (user picks a candidate; we print the same
  descriptive statistics for the hypothetical book) is a *pre-trade diagnostic of the
  user's own proposal*; it ships only after explicit operator sign-off that this sits on
  the lawful side of NWP-U18. Until then: not built.
- **WRI-R4 (review language):** role labels use the Risk Desk's review vocabulary
  ("Take-profit review", "Exit review"); no imperative advice verbs; "validated" banned.
- **WRI-R5 (two-organisms):** holdings never feed the signal path, boards, NW, or any
  scored artifact (NWC-U4/UWP-R2). The signal join stays client-side display.
- **WRI-R6 (coverage honesty):** out-of-model tickers (futures, most crypto, sub-cutoff
  names) are excluded from factor math with a visible chip, keep price-tier lanes where
  computable, and lump into "unmodeled" — never silently dropped, never guessed. Stale
  `as_of` prints stale and only ever downgrades (PRD-R6).
- **WRI-R7 (regime-honest correlation):** wherever calm and stress reads diverge
  materially, the glance tier leads with the stress read in plain words; the calm number
  never prints alone. Method lines state windows and estimation dates.
- **WRI-R8 (measurement, not forecast):** every L2 panel carries the existing FX-panel
  legend's stance ("measurement, not a forecast"); no forward-return claims anywhere.
  Any future promotion of WRI states to authority (rank/gate/alert escalation) requires
  the gauntlet: pre-registered gates on a forward ledger, adjudicated separately.

## 6. The three-layer risk read (the product)

- **L3 banner — the tape:** market_state / risk_radar / vol_regime crossed with the book's
  measured market beta: "Your book moves ~1.3× the market, and the tape is in a growth
  scare." One line, review stance, links to macro.
- **L2 verdict — the book:** named state {DIVERSIFIED 分散 / TILTED 偏斜 / CONCENTRATED 集中 /
  ONE BET 单一押注} + the sentence that earns the page its keep: "Your 8 names are
  effectively ~2 bets — Growth/Tech drives 64% of your swing; NVDA·AMD·AVGO move as one in
  selloffs." Sub-panels: factor variance shares (upgraded FX panel), twin clusters,
  per-position risk-contribution bars, calm↔stress divergence, concentration facts.
  v0 ENB thresholds (printed as heuristic): ≥4 diversified, 2.5–4 tilted, 1.5–2.5
  concentrated, <1.5 one bet.
- **L1 chips + drawer — each name:** lane chips on the row (⚠ earnings 3d, ⚠ below
  MA50+weak RS, solvency, dilution, insider cluster, extension…), role badge from the
  Risk Desk ladder in review language, expandable drawer with reasons + as-of stamps.
  Personality context displays, never scores (PRD-R12).

## 7. Math spec (client `risk_core.js`, pure functions + tests)

Inputs baked today: per-name orthogonalized marginal betas b_i (9-vector), `factor_cov` F
(≈diagonal by construction), `idio_vol` σ_ε,i, r², sector, `as_of`. Weights w_i: dollar
values from portfolio positions (UWP W2 already pushes `{ticker→dollarValue}` via
`FX.setAutoWeights`); equal-weight fallback + existing manual editor for watchlist-only.

- Book factor exposure: β_book = Σ_i w_i·b_i. Book variance V = β′Fβ + Σ_i w_i²σ²_ε,i.
- Factor variance share: s_k = β_k(Fβ)_k / V (Euler; clamp tiny negatives to 0, disclose
  if clamped mass > 2%). Idio is NOT one bucket: each name's idio term w_i²σ²_ε,i is its
  own independent contribution — that spread is real diversification and must count.
- **ENB** = 1/Σ_j s_j² over the non-negative shares {9 factor buckets + n idio buckets}.
  Sanity anchors: 20-name pure-idio equal book → ≈20; all-one-factor book → →1.
- Pairwise implied correlation: ρ_ij = b_i′F b_j / (σ_i σ_j), σ_i² = b_i′F b_i + σ²_ε,i.
  **Twins:** greedy clustering at ρ ≥ 0.70 (stress lens; calm lens shown in drawer).
- Per-position risk contribution: MCTR_i = w_i(Σw)_i / σ_book with Σ = BFB′+D restricted
  to the book; share = MCTR_i/σ_book (can be negative → "offsets your book" chip).
- Stress lens: identical math under `factor_cov_stress` (W1 engine emit: factor
  covariance estimated on worst-quartile SPY days over a 756d window, n≈189; idio held
  v1-invariant, printed in method line). Divergence flag when stress-ENB < 0.7×calm-ENB
  or any twin appears only under stress.
- Coverage: names absent from `betas` → excluded from all book math, listed on the chip;
  if >40% of book dollars unmodeled, the L2 verdict abstains ("not enough modeled weight
  to read the book") rather than printing a false state.

## 8. Per-position lane port (L1, from Risk Desk §6)

v1 ports the lanes whose sources already live in baked per-ticker JSON (§6 source column;
field presence verified as W1's first task since `site/stockdata/` is render-owned):
price_trend, extension_giveback (ext block; giveback needs entry price → portfolio names
only), event_window, earnings_expectation, solvency_dilution, ownership_flow,
macro_sensitivity (chip + betas), sector_rotation (member_context), market_regime
(shared L3 banner), data_quality. Role ladder verbatim from Risk Desk §7, review labels.
Alert transitions stay client-side ("since you last looked" deltas) in W5; server-side
sentinel extension only ever sees symbols (B6 precedent), never positions.

## 9. Waves + routing (per CLAUDE.md model routing)

- **W0 (this PR, docs-only):** charter + adjudication. DONE on merge.
- **W1 — engine + verification (builder/opus):** extend `engine/factor_exposure.py` emit
  with `factor_cov_stress` (+ method fields, tests, off render path — small matrix on
  already-loaded data); verify per-ticker JSON lane-field presence against Risk Desk §6
  and record the v1-portable lane list in this doc; verify whether per-ticker JSON carries
  a closes series (decides the realized-corr come-back).
- **W2 — design spec (main loop / designer, flagship surface):** DESIGN_DOCTRINE +
  frontend-design skill loaded; exact markup/CSS for L3 banner, L2 verdict + sub-panels,
  L1 chips/drawer, pinned BEFORE any builder touches the page (spawn-handoff law §3).
  Reference crops committed under `mockups/refs/wri/`.
- **W3 — build (builder/opus):** `templates/risk_core.js` (pure math + unit tests with
  the §7 sanity anchors) + watchlist wiring + FX panel upgrade/absorption; paired
  template/site copies; bilingual; CI (banned vocab, nav-gap, template-site sync).
- **W4 — what-if pre-trade diagnostic:** GATED on operator NWP-U18 sign-off (WRI-R3).
- **W5 — deltas + alerts:** client transition surfacing; optional B6 symbol-sentinel
  extension. Come-backs: realized-corr overlay (pending W1 closes-check), downside-idio
  study, personality-conditioned thresholds (PRD-R12 study), Terminal parity, any
  authority promotion via pre-registered forward gates (WRI-R8).

## 10. Non-goals

No sizing/allocation/optimizer; no VaR/ES; no leverage/derivatives modeling; no fused
score at any grain; no new collectors; no estimator fitting; no server-side position
reads; no held-desk changes (Mastermind §5–9 untouched); no "validated" claims.

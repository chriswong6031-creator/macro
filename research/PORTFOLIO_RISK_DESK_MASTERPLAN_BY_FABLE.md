# Portfolio Risk Desk — masterplan & Codex adjudication (by Fable)

Date: 2026-07-07
Status: RULING OF RECORD + build contract. Build executes in the **Mastermind repo**
(`/Users/chriswong/Documents/Cluade/Mastermind`, serves bot.mastermind-x.com). This macro-repo
PR is docs-only.
Intake adjudicated: `HELD_POSITION_RISK_WATCHLIST_ENGINE_FOR_CLAUDE.md` (Codex, 2026-07-07,
vendored at `~/.codex/worktrees/portfolio-risk-watchlist-research/research/`).
Registries consulted: `docs/ACTIVE_BUILD_MAP.md` (2026-07-07), `research/DO_NOT_REBUILD.md`,
`config/ruling_graph.yml` (NWC-U4, NWP-U18, RUL-F3.2, LH-R2, FR-1, Signal Commons R3, WA-R1/R2,
GAP-RUL-3/6, TOP3-E5, per-stock-hazard n-starved ruling, stock-top-hazard-arm-comeback).

## 1. One-line verdict

Build an operator **Portfolio Desk** in the Mastermind Bot app: a Supabase-backed position
ledger (ticker + optional entry price/shares), live portfolio value, and a **held-position
evidence monitor** that composes existing nightly Macro Dashboard artifacts into ~10
deterministic per-lane risk states and a transparent review-role ladder
(`monitor → review → tighten → trim_review → exit_review`) with transition-gated Discord
alerts — **no fused numeric risk score, no fitted top-predictor, no sell instructions**.

## 2. Why not a "risk score" or a top-finder model (the failure the operator noticed)

Prior sessions failed at "finding tops" because they fit models to predict declines:
TOP3-E5 lifecycle/hazard model — KILLED (tape-laundering); per-stock hazard — ruled n-starved,
do-not-build; G-T2X HTF overlays — all run overlays KILLED; FALS-OSC oscillator family — kill
switch fired (only the down-direction cell survived, sector-level, re-test 2027-01).
EXIT-GRID-1's honest conclusion stands: *drawdown control is an entry problem*; no exit rule
beat entry discipline on 49,939 fires.

What survives case law is exactly what the operator is asking for once decomposed: the market
regime, the stock's own regime/personality, event calendars, earnings deterioration,
solvency/dilution, rate sensitivity, crowding — **each already computed nightly as a
display-tier artifact**. The correct machine is a *composition* of those lanes with
deterministic thresholds and honest coverage flags, not a new estimator. Aggregation is a
printed lane count and an AND-gate role ladder (LH-R2 / WA-R1 pattern), never a weighted
composite (Signal Commons R3, FR-1, NWC-U3, GAP-U1).

## 3. Codex memo adjudication

| Codex section | Verdict | Notes |
|---|---|---|
| Two-layer architecture (private ledger + evidence fabric) | ADOPT | Ledger = Supabase (operator-scoped). |
| **Placement of engines in Macro Dashboard** (`engine/held_position_*.py`, `scripts/run_held_position_sentinel.py`, alert_triage integration, `data/held_risk/` artifacts) | **REJECT — relocate to Mastermind repo** | NWC-U4 (no held-book data in this repo; two-organisms law), NWP-U18 (portfolio construction is Mastermind's), RUL-F3.2 (no display may read as a live position monitor here). B6 reads sanitized watchlist *symbols*; a position ledger with entry prices is held-book. |
| Risk taxonomy lanes 1–9, 11 | ADOPT (v1 subset) | Mapped to existing artifacts (§6). Options/dealer lane deferred (W-OVC/#1845 in flight). |
| Lane 10 portfolio concentration | ADOPT in Mastermind | Legal there; display-only arithmetic (largest position %, sector concentration). |
| Role ladder `info<monitor<review<tighten<trim_review<exit_review<thesis_broken` | ADOPT minus `thesis_broken` | v1 has no thesis-tag falsifier mapping; comes back with thesis tags (§10). |
| No fused 100-point score; deterministic rules only; LLM de-escalate/explain only | ADOPT | Restates house law. |
| Alert governor (idempotent IDs, transition-only, per-role cooldowns) | ADOPT | Pattern = B6 watchlist sentinel. |
| Entry/review snapshots + delta engine | ADOPT SIMPLIFIED | v1: entry-path metrics (MFE/MAE/giveback) + prior-state diff; full snapshot store is v2. |
| EDGAR 8-K/Form-4/13D parsers, FDA, halts (Phase 3–4 new collectors) | DEFER | v1 composes only *shipped* artifacts (dilution_events, insider_signals, beneficial_ownership already exist). No new collectors. |
| Forward outcome ledger + pre-registered promotion gates | ADOPT | From day one (§9). |
| `held_risk_alerts.jsonl` into macro `alert_triage.py` | REJECT | Alerts live in Mastermind (its UI + Discord). Macro alert center never shows held-book state. |

## 4. Rulings (PRD-R1..R12)

- **PRD-R1 (placement):** All held-position state, UI, monitoring, and alerting live in the
  Mastermind repo. The Macro Dashboard repo ships no code, artifact, or display for held
  positions. A row is appended to `research/DO_NOT_REBUILD.md` in this PR.
- **PRD-R2 (no fused score):** No weighted composite risk number at any grain. Aggregates are
  (a) the printed count of elevated lanes ("4 of 9 lanes elevated") and (b) the role ladder,
  each role a named AND/OR of specific lane states (§7). Roles/lanes never feed board
  ordering, sizing, allocation(), the Neural Web, or any scored path.
- **PRD-R3 (deterministic only):** Role assignment and lane states are pure functions of
  artifact fields with printed thresholds. No LLM anywhere in the v1 loop; any future LLM text
  is explanation/de-escalation of already-fired deterministic keys.
- **PRD-R4 (review language):** Roles are review prompts, not instructions. Alert and UI copy
  use no advice verbs (buy/sell/add/trim as imperatives banned; B6 precedent). UI labels:
  `trim_review` → "Take-profit review", `exit_review` → "Exit review". The word "validated"
  is banned in desk copy.
- **PRD-R5 (no new estimators):** v1 fits nothing. The parked stock-top-hazard arm
  (come-back 2026-10-07, conditional on sector gates) is neither preempted nor armed by this
  desk. If it ever passes its gates it would join as one more lane — nothing here depends on it.
- **PRD-R6 (coverage honesty):** Tickers outside the ~1,506-name macro universe degrade to
  `price_only` coverage (price/trend + extension lanes computed from fetched OHLCV; evidence
  lanes state `coverage_missing`). Stale artifacts print `stale`, and staleness only ever
  *downgrades* confidence — never creates an alert by itself beyond `data_stale`.
- **PRD-R7 (privacy):** Positions (entry price/shares) live only in Supabase (RLS
  owner-scoped) and in Mastermind's gitignored `data/` runtime state. Nothing position-derived
  is ever committed to any repo, logged with values, or written into macro-repo artifacts.
  Discord alert text carries ticker + lane evidence, never shares/notional/entry price.
- **PRD-R8 (serve-only carve-out):** VPS runs `MASTERMIND_SERVE_ONLY=1`, which blocks operator
  POSTs. Portfolio CRUD endpoints are the sole exemption, allowed because their only mutation
  target is Supabase (no VPS-local state, no LLM, no scheduler); they remain session-cookie
  auth-gated. Carve-out is explicit and commented in `app/auth.py`/`app/main.py`.
- **PRD-R9 (one-way flow):** Mastermind reads macro artifacts via the existing `vendor/macro`
  mirror (read-only). Nothing from this desk flows back into the macro signal path or NW
  (two-organisms law preserved).
- **PRD-R10 (earned authority):** A forward outcome ledger accrues from day one. Any future
  claim of edge, tier upgrade, or threshold "tuning that works" requires a pre-registered gate
  on ≥1 quarter of forward alerts, adjudicated separately.
- **PRD-R11 (descriptive vocabulary):** MFE/giveback/profit-take vocabulary is borrowed from
  EXIT-GRID-1/TRIM-GRID-1 as *descriptive reference* (those tapes are fire-tape
  counterfactuals). Thresholds in §6–7 are labeled heuristic v0.
- **PRD-R12 (personality lane is context):** `stock_personality` fields display as context
  (archetype, chart labels) in v1. Personality-conditioned thresholds are a v2 candidate
  requiring their own pre-registered study (R-SP21 anchor law applies).

## 5. Architecture of record

```
Supabase (fsldfzlxyavsuwqbceod)
  portfolio_positions  (RLS owner-scoped; ticker, shares?, entry_price?, entry_date?, notes, status)
        ▲  CRUD proxied by FastAPI /api/pfolio/* (service key, operator UUID resolved from email)
        │
Mastermind app (Mac primary, scheduler ON) ──────────────► VPS mirror (serve-only)
  portfolio/held_risk.py  — lane composer                    reads data/portfolio_watch/* (rsync'd)
    reads vendor/macro/site/stockdata/<T>.json,              serves /portfolio_desk + /api/pfolio/*
          vendor/macro/data/regime/latest.json,              live quotes via yahoo_feed (both hosts)
          site/factordata + basketdata mirrors,
          vendor/macro/data/stocks/<T>.parquet (+ yfinance fallback for out-of-universe)
    writes data/portfolio_watch/risk_state.json   (portfolio_risk_state.v1)
  portfolio/held_risk_alerts.py — transitions + cooldowns → data/portfolio_watch/alerts.jsonl
                                                          → Discord (DISCORD_WEBHOOK_PORTFOLIO)
  scheduler: compose post-nightly (~07:00 PT) + RTH interval (30m) + outcome-ledger nightly append
  UI: app/static/portfolio.html at /portfolio_desk — positions, live value, lane grid, role
      badges, market-regime strip, alerts feed, add/edit modal
```

## 6. Lane spec v1 (states: `ok | watch | elevated | coverage_missing | stale`; every state carries flags + reason strings + asof)

| # | Lane | Sources (vendor/macro unless noted) | `elevated` when (v0 heuristics; `watch` = single flag) |
|---|---|---|---|
| 1 | price_trend | OHLCV parquet or yfinance (any ticker) | close<MA50 AND (RS-vs-SPY 20d z ≤ −1 OR close<MA200); flags: MA20/50/200 breaks, ATR z ≥ 2, 20d lower-low, drawdown from 52w high |
| 2 | extension_giveback | `ext` block or computed ext_z; entry path from ledger | ext grade `parabolic`; or MFE ≥ 20% with giveback ≥ 35% of MFE; critical flag at giveback ≥ 60% of MFE ≥ 25% |
| 3 | event_window | `event_windows`, earnings.parquet | earnings within 3 sessions; flags at T-7, FOMC ≤ 2d, debt block (current_debt > cash) |
| 4 | earnings_expectation | `expectation_state`, `revisions`, `analyst` | sue_streak ≤ −2 (consecutive misses) OR (sue_latest < 0 AND pead_drift_20d ≤ −3%); flags: revisions down, gap-fade |
| 5 | solvency_dilution | `leverage_ratios`, `accounting_quality`, `capital_allocation`, dilution_events.parquet, `moat_falsifiers` | ≥2 flags of {interest_coverage<2, net_debt/EBITDA>4, altman_z<1.8 (non-financials), piotroski≤3, capital_allocation=dilutive, S-1/S-3 within 90d, ≥2 moat falsifiers}; critical: coverage<1, or altman<1.8 + dilutive |
| 6 | ownership_flow | `insider_signals`, `beneficial_ownership`, `positioning`/short_volume | short-interest z ≥ 2 AND insider sell-cluster (sellers ≥ 3, buyers = 0, net < 0); either alone = watch; 13D activist = info flag |
| 7 | macro_sensitivity | `stock_macro_sensitivity` chip, factor_betas, transmission | rate_beta_tier HIGH AND regime_read = headwind; watch: HIGH tier alone in adverse rate trend |
| 8 | sector_rotation | regime `sector_rs`, `sector_pulse`, subsector quadrant, member_context | ≥2 of {sector RS bottom quartile, pulse ∈ {fading, deteriorating}, quadrant ∈ {weakening, lagging}, member band overbought + tone down} |
| 9 | market_regime (shared) | risk_radar verdict, vol_regime, market_state, quad | ORANGE/EXTREME radar or market_state RED; displayed as portfolio banner; participates only in `tighten` (§7) |
| 10 | data_quality | artifact asof stamps | `stale` when core artifacts > 3 sessions old; `coverage_missing` per §PRD-R6 |

Personality context (non-scoring): archetype, dna_class, chart labels shown on the position
card (e.g. "volatile_momentum_vehicle — extension whipsaws are this name's normal mode").

## 7. Role ladder v0 (deterministic, first match from top; lanes 1–8 count toward "elevated")

- **exit_review** — any of: solvency critical flag AND price_trend elevated; earnings_expectation
  elevated AND price_trend elevated AND close<MA200; giveback ≥ 60% of MFE ≥ 25%; dilution filing
  ≤ 30d AND price_trend elevated.
- **trim_review** — extension_giveback elevated AND (earnings ≤ 7 sessions OR sector_rotation
  elevated OR ownership_flow elevated OR market_regime ORANGE+).
- **tighten** — price_trend elevated AND (event_window elevated OR macro_sensitivity elevated
  OR market_regime ORANGE/EXTREME).
- **review** — ≥2 elevated lanes across independent groups
  {price_trend+extension | event | expectation+solvency | ownership | macro+sector}.
- **monitor** — exactly 1 elevated lane, or ≥2 watch lanes.
- **info/ok** — otherwise.

## 8. Alert governance (pattern: B6 sentinel)

Transition-fired only (role worsens, or new independent lane joins an active role); idempotent
ids `pfolio:{ticker}:{role}:{date}:{lane_cluster}`; cooldowns (sessions): monitor 5, review 3,
tighten 2, trim_review 2, exit_review 1 (dedupe on same filing/event). State in
`data/portfolio_watch/alert_state.json`; log append-only `alerts.jsonl`; Discord via
`DISCORD_WEBHOOK_PORTFOLIO` (fallback `DISCORD_WEBHOOK_URL`), fail-soft when unset. Copy
template: `PORTFOLIO · {TICKER} {role-label} — {lane}: {reason}; {lane}: {reason} ({date})`.

## 9. Outcome ledger

`data/portfolio_watch/outcomes.jsonl`, nightly appender grades each alert at t+5/t+21
(forward return, MFE giveback avoided/foregone vs alert-day close, whether a harder breaker
followed). Descriptive only; feeds the PRD-R10 gate whenever a promotion is proposed.

## 10. Build waves, come-backs

- W0 this doc (macro repo, docs-only PR). W1 ledger+desk UI+quotes; W2 lane composer+roles+tests;
  W3 scheduler+alerts+risk UI+VPS state push; W4 Opus review; W5 deploy Mac+VPS. (Mastermind
  repo has no remote: feature branch → local merge → change-gated VPS deploy script.)
- Come-backs: options/dealer lane after #1845 stabilizes (~2026-08); thesis tags +
  `thesis_broken` falsifier mapping (v2); personality-conditioned thresholds study (v2,
  PRD-R12); outcome-ledger first read 2026-10 (with stock-top-hazard come-back window);
  Kalshi/macro-release event lane per MRI C-2 if sources land.

## 11. Non-goals

No automatic sell/trim; no sizing; no short signals (GAP-RUL-3); no NW/board/alert-triage
feeds; no new data collectors; no paid-data assumptions; no macro-repo held-book surface of
any kind (superseded by Amendment 1 for the user-facing display tier only); no "validated"
claims.

## 12. Amendment 1 (2026-07-18) — operator override: macro-repo user-facing surface carve-out

Operator directive (2026-07-18 session): the `DO_NOT_REBUILD.md` row derived from PRD-R1
("Held-position ledger / live position monitor / held-risk engine inside Macro Dashboard")
is **struck** and removed from the registry. The operator judged the placement exclusivity
over-broad for the product direction: a user-facing unified watchlist + portfolio dashboard
on the macro site (subscribers' own self-entered holdings, not the operator held-book).

**Now allowed in the macro repo:** a display-tier, user-facing watchlist + portfolio tracker
surface — chartered as the Unified Watchlist & Portfolio program
(`UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md`) — whose per-user state lives ONLY in
Supabase under owner-scoped RLS.

**Remains in force (NOT struck):**
- **PRD-R2** — no fused per-position composite risk number at any grain (registry row
  re-scoped to this clause alone).
- **PRD-R7** — privacy: nothing position-derived is ever committed to any repo, logged with
  values, or written into macro-repo artifacts.
- **NWC-U4** (two-organisms law) — no Mastermind `bot.db` bridge; user holdings never feed
  the macro signal path, boards, Neural Web, or any scored artifact (restated as UWP-R2).
- **NWP-U18** — no portfolio construction/sizing in this repo.
- **RUL-F3.2** engine-display clause — *engine* surfaces (Exit/Trim tapes, boards) still may
  not read as live position monitors; the carve-out covers only a user's own self-entered
  holdings view, labeled as such.
- The operator held-risk desk itself (§5–§9: lanes, roles, alerts, scheduler) stays in the
  Mastermind repo unchanged.

§3's placement-REJECT row and §11's "no macro-repo held-book surface" clause are superseded
to the extent above; historical text retained as adjudication record.

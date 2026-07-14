# Vol Suppression & AI Bifurcation — masterplan (VSB)

**Status:** W0 (this document) — field guide + build plan. No code shipped yet.
**Date:** 2026-07-13 · **Program code:** VSB · **Owner:** operator + Fable main loop
**Provenance:** 19-agent deep-dive (6 internal census lanes, 5 web-research lanes each with an
independent Opus adversarial verifier, 3-lens design panel). Registries read first:
`docs/ACTIVE_BUILD_MAP.md` (no open-PR collisions as of 2026-07-13) and
`research/DO_NOT_REBUILD.md` (kills honored in §7).

---

## 0. Mission — the operator's questions

1. Are the current Market Sentiment (fear/greed) factors the right ones? What's missing?
2. Should we add short-horizon VIX dynamics — velocity of change, spike detection?
3. Index VIX looks suppressed while single-name vol stays high (0DTE era, dispersion flows) —
   should we read single-name vol / implied correlation directly?
4. Can we get a granular McClellan view — WHAT is rising/falling — given that formerly
   defensive/industrial names are now AI-infrastructure proxies and inflate "breadth"?
5. The AI-buildout circular capital flow: does it mean heightened risk, or faster index
   expansion with suppressed drawdowns? Will it end badly? Are we prepared?
6. How do we detect this phenomenon and thread it through every system that should know about it?

## 1. Field guide — the mechanism (read this before building anything)

### 1.1 Three stacked vol-suppression flows (verified magnitudes)

- **Derivative-income ETFs** (~$150B+, JEPI ~$44B alone) persistently SELL index calls →
  structural supply of index vol.
- **Autocallable structured products** (~$130B+, ~70% of the structured-note market) leave
  dealers structurally LONG single-name downside to hedge → structural bid for single-name vol.
- **QIS / pod dispersion books** (JPMorgan strategic indices crossed $100B notional in 2025;
  total QIS short-correlation estimates range $370–750B) arbitrage the gap: short index vol,
  long single-name vol → they GLUE the regime in place.

Net effect: **index implied vol is mechanically cheap relative to single-name implied vol.**
Confirmed extremes: CBOE COR3M (3-month implied correlation) traded ~8–9 in mid-2024 and again
in June 2026 — the lowest since at least 2007; the VIXEQ−VIX spread hit a record 30.8 and DSPX
(dispersion index) ~44 in late-May/June 2026. This is not narrative — it is the priced state.

### 1.2 What 0DTE does and does not do to VIX (verified)

- VIX **by construction** uses only SPX options 23–37 calendar days out. 0DTE (a record 62.4%
  of SPX options volume in Aug 2025) is **invisible** to VIX — the "suppression" is first of
  all a *measurement gap*, not manipulation.
- Causal suppression exists but is modest: best-identified study (Adams/Fontaine/Ornthanalai,
  SSRN 4881008) finds realized index vol 60–90 annualized bps lower on 0DTE-heavy days via
  dealer long-gamma — and the sign FLIPS in negative-gamma episodes (amplification).
- Cboe's structural answer is **VIX1D** (launched 2023-04-24, `^VIX1D` free on Yahoo). Known
  artifact: Mon/Fri overnight zig-zag bias → gauge, never a daily-close signal.
- So: the honest statement is "VIX measures a strip the market has partly left." Read
  short-horizon fear from VIX1D/VIX9D, tail-forming risk from VVIX, and the dispersion state
  from COR/DSPX — not from spot VIX level alone.

### 1.3 The bifurcation ("two markets") — verified

- Goldman (May 2026): technology accounted for **85% of S&P 500 YTD return**; the ex-tech
  index advanced ~3%. Fewer than 25% of members outperformed; median stock ~13% below its high
  while the index printed records.
- The AI re-rating swallowed "defensives": Vistra +258% in 2024 (best S&P name, a GICS
  *utility*), CEG ~+92% 2024 (Three Mile Island PPA), GEV turbines sold out through 2030–31,
  PWR +127%/12m at ~55–96x forward vs ~47x peers, Electrical Components & Equipment at 28.7x
  forward. Utilities' canonical anti-correlation to SPX collapsed in 2024 (+24% vs +25%).
- Russell 2000 is K-shaped: 16 of its 50 best performers in the measured period were
  chip-adjacent (+400%+ names), while the non-AI rest carries a debt-maturity wall and zombie
  interest-coverage stress at ~18x forward vs S&P ~26x.
- **Consequence for breadth tools:** the A/D line and McClellan oscillator count an advancing
  AI-adjacent utility/industrial the same as an advancing consumer staple. In this regime the
  aggregate McClellan partly measures *AI flow-through*, not broad-economy participation.
  That is a composition artifact, not a broken indicator — the fix is DECOMPOSITION, not repair.

### 1.4 Circularity — is it dot-com vendor financing again? (verified, both sides)

- The loop is real and documented: NVDA up-to-$100B OpenAI commitment; OpenAI→CoreWeave $22.4B
  contracts with an NVDA $6.3B capacity backstop to 2032; AMD 160M-share warrant to OpenAI;
  Amazon→Anthropic up to $33B with $100B+ compute commitments back; $120B+ identified SPV /
  off-balance-sheet data-center financing. BIS (June 2026 Annual Report) named it a top
  systemic risk: "risks of the same asset being pledged multiple times."
- Scale vs 2000: NVDA vendor-financing-like exposure ≈ 2.8x Lucent's peak *ratio*; hyperscaler
  2026 capex ~$600–725B (+~80% y/y), on track to exceed their combined operating cash flow
  around Q3 2026; AI beneficiaries ≈ 50% of S&P 500 2026 EPS growth (Goldman).
- The honest counterargument: unlike 2000 CLECs, the buyers generate ~$450B+ real operating
  cash flow, demand is supply-constrained, and monetization is measurable. Circularity raises
  FRAGILITY (correlated failure surface), it does not by itself date a top.

### 1.5 Both of the operator's hypotheses are true — at different horizons

- **Melt-up mechanics (now):** the three-flow structure dampens index drawdowns and recycles
  capital top-to-bottom through AI-adjacent sectors — dips get bought by structural vol
  sellers, sector rotation inside the AI complex substitutes for index-level corrections
  ("leaders take turns"). This *extends* trends and suppresses realized index vol.
- **Amplifier mechanics (at the break):** the same books flip sign when correlation snaps
  toward 1. March 2026 was the live demonstration: COR1M ~15 → ~40 in weeks on the Iran
  escalation; JPM's dispersion index −4.9%, worst month since 2011. Feb-2018 (VIX +115% in a
  day, XIV dead) and Aug-2024 (VIX intraday 65.73, largest one-day spike on record; Nikkei
  −12.4%) are the same shape from different triggers. Suppression is not stability — it is
  borrowed stability with a correlation-spike repayment schedule.

### 1.6 How these regimes END — three verified failure modes + indicator lead order

1. **Structural feedback unwind** (Feb 2018, Aug 2024): days–weeks, violent, fast recovery
   when the underlying economy is fine.
2. **Slow bifurcation grind** (1999–2000): breadth peaked ~Apr 1998, ~2 years before the
   Mar-2000 top; credit and the index broke LAST. Topping was a process, not a day.
3. **Exogenous shock into crowded positioning** (Apr 2025 tariffs — VIX intraday ~60;
   Mar 2026): sharp drawdown, fast recovery IF the shock is policy-reversible.

**Lead/lag ranking (practitioner + academic consensus, honestly labeled):**
breadth divergence (leads by quarters–years, but slow/ambiguous) → implied-correlation
floor-break velocity (weeks) → VVIX/VIX divergence (days–weeks; peaked before SPX lows in
Feb-2018, Dec-2018, Mar-2020) → skew steepening (weeks, noisy) → VIX term inversion
(coincident CONFIRMER) → **HY OAS (LAGS in valuation-driven bubbles — dot-com pattern;
"credit is calm" at ~270bps today is NOT reassurance)**. No single indicator survives alone;
consensus is a 4–5 signal orthogonal stack. That stack is what this program builds.

## 2. Current-state audit — Market Sentiment composite (`engine/fear_greed.py`)

**Verdict: the composite is honestly built for what it is (display-only greed dial) and its
legs are conventional and defensible. It is NOT the instrument for the operator's question.**
Specific findings:

- 11 equal-weight legs, expanding z-scores, hard min-history gates (252d/104w/40q), young
  legs strictly excluded, disclaimer embedded, never feeds regime/scores. Good bones.
- **Concentration-of-source flaw:** 3 of 11 legs (vix_level, vix_trend, vix_term) all derive
  from index-level implied vol — the precise gauge this regime mechanically suppresses. The
  composite's whole "vol block" has a single point of failure and reads structurally greedy.
- **Coincident-to-lagging by construction:** momentum, NH/NL, McClellan, HY OAS — nothing in
  the dial leads the failure modes in §1.6. Fine for sentiment context; useless as warning.
- **No history ledger:** dial JSON is overwritten nightly (`site/basketdata/fear_greed.json`);
  the composite cannot be studied, trended, or ever gauntleted.
  (`archive_context_snapshots.py`'s `fear_greed_composite` column is the CRYPTO series — a
  naming trap.)
- **Honesty bugs:** `as_of` stamps now-UTC instead of max leg data-date (staleness masking,
  fear_greed.py:722-727); `htf_durability.fear_greed_extreme` is a dead wire (no caller).
- putcall (data since 2026-06) and aaii are hardcoded young tiles — correct treatment.

## 3. What already exists (census) — do not rebuild these

- **`engine/froth_fragility.py`** is the house "will it end badly" organ and already encodes
  §1's physics on the REALIZED side: Solnik-style cohort ρ̂ (42d EWMA), dispersion-rising,
  "VIX asleep vs internal dispersion" leg, stealth-distribution sub-score, forward outcome
  log, display-only discipline. VSB **complements** it with the IMPLIED side (COR/DSPX) and
  the AI-adjacency lens; it does not duplicate it.
- Deep stores: `_VIX` 1990+, `_VIX3M` 2006+, `_VIX9D` 2011+, `cboe/vvix.parquet` 2006+,
  `cboe/skew` 1990+, aggregate S&P breadth 1962+ (16k rows). Forward-accruing: vix_futures +
  M1–M6 curve (2026-04+), putcall (2026-06+), per-name GEX chains w/ per-strike IV ~370 names
  (2026-06-15+), options_ivspread/options_skew (~370–400 names, late-June 2026+).
- **Dead/empty wires:** `_COR1M`/`_COR3M` configured in config.yml but 1 row each — the
  collector silently fails; `thetadata_eod` store schema exists with **zero data ingested**;
  yahoo `_VVIX` has 40 rows (the good VVIX series is the cboe one).
- AI classification: finviz "Artificial Intelligence" theme (142 members, 13 subsectors,
  2026-06-27) + 8 curated AI/power baskets in membership.json (ai_infra, ai_semiconductors,
  data_center_power, power_grid, nuclear_power, semicap_equipment, memory_storage,
  ai_neoclouds). Cohesion/HHI machinery exists in group_flow/theme_crowding/leader_radar.
- Downstream sockets: risk_radar `_LEG_CALIB` Tier-B accruing pattern (lift_2020=None),
  signal_stack tier:'context' legs, alerts via ALERT_META (hidden_fragility + gex_flip_cross
  already exist), conditions.py risk-appetite block, off-render band at daily.yml:2198.

## 4. Answers to the operator (short form)

1. **Right factors?** Right for a display greed dial; wrong instrument for regime-break risk.
   Keep the dial; do not stuff new legs into it. Build the missing layer beside it.
2. **VIX velocity/spike?** Yes — as rolling-PERCENTILE constructions (252d percentile rank,
   percentile-of-change). Absolute-VIX thresholds are a registered kill (RRX-R10) and
   non-stationary. `dvix_z` (forex_regime.py) and VIX-wick (dislocation.py) already exist to
   reuse.
3. **Single-name vol / implied correlation?** Yes — this is the highest-value gap in the
   entire stack. COR1M/COR3M/DSPX/VIXEQ are free EOD (Yahoo) and our collectors are dead
   while the state sits at multi-decade extremes. Fix tonight-tier.
4. **Granular McClellan?** Build a breadth DECOMPOSITION (AI-adjacent vs non-AI participation
   split), not a new McClellan signal. MCO-thrust as a radar leg is killed (coincident); the
   display home stands. The split answers "is tape health real or AI-composition artifact."
5. **Melt-up or risk?** Both: suppression extends the melt-up now and amplifies the eventual
   break (§1.5). The regime says nothing about the date; it defines the SHAPE of the end.
6. **Prepared?** ~40%: realized-side fragility organ exists (froth_fragility), hidden_fragility
   alert exists, RRX lanes cover term-structure confirmers. Missing: the implied-correlation
   eye, 0DTE-era short-horizon gauges, the AI-adjacency lens, and a persisted PIT ledger that
   makes any of it gauntletable later. That is this program.

## 5. Build waves

Doctrine framing: everything below ships **display-tier freely** (gauntlet = promotion gate,
not build gate). Promotion-track items get pre-registered gates and come-back dates. Heavy
compute goes to the parallel cluster band / off-render job (daily.yml:2198), never the render
path. All glance-tier copy obeys DESIGN_DOCTRINE (plain-word stance, no COR/VVIX/z jargon on
Tier-1, "watch — don't chase" is a sanctioned stance).

### W1 — Collector repair + additions (tonight-tier; every day of delay = lost history)
- **W1a** Fix `^COR1M`/`^COR3M` silent-failure (1-row stubs); cross-source from CBOE CDN like
  vvix/skew if Yahoo is flaky. Add freshness/row-growth assertion so silent death cannot recur
  (mirror the SPY freshness-gate idiom).
- **W1b** Add `^VIX1D`, `^DSPX`, `^VIXEQ` to the vol collection group. Persist-only.
- **W1c** Verify next-nightly accrual (row counts grew) — explicit check, not assumption.

### W2 — PIT ledger (makes everything future-gauntletable)
- Extend `scripts/archive_context_snapshots.py` daily row with: cor1m, cor3m, dspx, vix1d,
  vix_pctile_252, dvix_pctile, vvix_vix_ratio, vix9d_vix3m_slope, top10_weight_share,
  ai_breadth_spread (from W4), fg_dial (fix the crypto/equity naming trap — new column, keep
  old). Nightly is the sole advancer. Scalar appends ≈ zero render cost.

### W3 — Vol-weather organ (display-tier; deep sources compute full history instantly)
- `engine/vol_velocity.py`: VIX 252d rolling percentile rank + percentile-of-20d-change +
  spike state (percentile construction ONLY — the absolute form is killed). Source _VIX 1990+.
- VVIX/VIX ratio percentile chip (cboe/vvix 2006+). Respect the existing promotion block
  (CONTEXT_LEGS; orthogonalization vs VIX level pending) — display only.
- VIX9D/VIX3M slope state chip. (The C6 inversion-RESOLUTION confirmer and C8 vol-instability
  veto belong to RRX W1 — reference, do not duplicate.)
- Surface: "Vol weather" tile strip in the Market Sentiment dialog reusing the young-tile
  pattern. Composite z-mean UNTOUCHED.

### W4 — AI-adjacency lens (the bifurcation layer)
- **W4a** `data/breadth/ticker_ai_tag.parquet`: ai_core / ai_infra_power / non_ai, pinned to
  committed sources (finviz AI theme ∪ the 8 AI/power baskets), refreshed with them, with a
  membership-change log (the tag set is a subjective knob — version it, never let it drift
  silently).
- **W4b** Decomposed participation series (off-render): pct>50dma, pct>200dma, and A/D counts
  for AI-tagged vs non-AI cohorts over the breadth closes caches (510 tickers, 2025-03+),
  plus the SPREAD series. This is a composition decomposition of existing display breadth —
  NOT an MCO-thrust leg, NOT a per-ticker historical A/D line (updown.parquet has 36 rows; do
  not fake depth).
- **W4c** "AI vs the rest" glance panel: one stance — is strength broad or AI-masquerade —
  plus Tier-2 receipts (cohort sizes, spread, concentration). Annotate froth_fragility Face-A
  and the existing breadth panels with the split; LLM desks may narrate/de-escalate, never
  originate the read.

### W5 — Sentiment surface honesty + context
- Fix `as_of` → max leg data-date (fear_greed.py:722-727). Resolve the `fear_greed_extreme`
  dead wire (wire it or delete the param). Persist the equity dial history (W2 column).
- "Circularity watch" context card: BIS framing, capex-vs-OCF crossover (~Q3 2026 checkpoint),
  named check-by dates; narrative receipt with plain-word stance ("watch — the tell shows in
  breadth and correlation first, credit last"), never a score.

### W6 — Forward ledgers + one alert (promotion track opens here)
- Tier-B accruing `_LEG_CALIB` entries (lift_2020=None, inert until depth):
  (1) **correlation floor-break velocity** — COR1M rising ≥15pts off a bottom-decile base
  inside 20 sessions (relative/percentile anchors, not absolute constants — bands live in the
  calibration overlay); (2) **AI-breadth-spread divergence** vs 21d forward SPY drawdown.
- One ALERT_META alert: correlation floor-break — an honest "regime unclenching /
  crisis-in-progress" CONFIRMER, labeled as such, plain_en/zh.
- Both graded by the existing risk_radar forward-log machinery. Promotion requires the
  standard gauntlet (lift_2020 ≥ 1.20 @ pre-registered thresholds); COR promotion also waits
  on the R2 lane clock (come-back 2026-10-15).

## 6. Pre-registered promotion gates (so future-us can't move them)

- vix_pctile / dvix_pctile spike states: no authority until ≥1 full accrued year of forward
  log AND lift_2020 ≥ 1.20 at thr 0.90 with era-split + freq-matched permutation (DT-R14
  primary: within-month episode-label permutation).
- COR floor-break velocity: same gauntlet, plus explicit orthogonalization against vix_term
  and VVIX/VIX (must add edge BEYOND the existing vol block, not restate it).
- AI-breadth spread: field-guide playbook first (this doc §1.3 is the seed; per-type behavior
  study before any ruler); any backtest ruler derives FROM the playbook per the
  understanding-before-backtest law. Time-preserving nulls mandatory (ticker-cluster CIs
  without time control are a registered lethal trap).

## 7. What we will NOT build (kills honored)

- McClellan MCO thrust / MCO-oversold bounce as radar/authority legs (RRX-R4/R10 —
  coincident-by-construction). W4 is a decomposition of the DISPLAY panel, full stop.
- Absolute-VIX spike-and-fade thresholds (RRX-R10 / R-SP21). All VSB vol constructions are
  percentile/relative.
- rs-based member-dispersion gates (zero-sum tautology, R-4).
- A/D-line divergence as an authority leg (0.69x in 2020+; stays display).
- RSP/SPY as a predictor (CXO pre-declared null; surface as descriptor only).
- CBOE IC−RC dispersion premium construction stays DEFERRED (coincident per its own lit;
  revisit only after the R2 COR gauntlet resolves).
- No LLM-originated bifurcation scores/escalations anywhere (de-escalation only).

## 8. Open questions the ledgers should answer over time

1. Does the AI-breadth spread lead AI-complex drawdowns, or only describe them? (W6 ledger)
2. Is COR floor-break velocity distinguishable from a VIX-term-structure event in our data,
   or redundant? (orthogonalization test at promotion)
3. Does VIX1D add information beyond VIX9D once its weekday artifact is controlled? (accrual)
4. When hyperscaler capex crosses aggregate OCF (~Q3 2026 checkpoint), does the circularity
   watch see credit-side confirmation (IG spreads of the SPV-adjacent complex) before equity
   vol? (W5 card check-by dates)
5. Single-name IV composite from our own GEX chains (~370 names, per-strike IV since
   2026-06-15) as a home-grown VIXEQ proxy — worth building once 6+ months accrue; parked
   until then (depth, not design, is the constraint).

---
*Adversarial-verification notes: all load-bearing external numbers above survived independent
re-sourcing except where corrected in place (e.g. 1998 breadth peak = April not June; Feb-2018
VIX one-day move = ~+115%; the 65.73 VIX print belongs to 2024-08-05, April-2025 peaked ~60).
Claims that could not be independently confirmed were dropped or downgraded, not reported.*

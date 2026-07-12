# International Risk Desk (IRD) — masterplan (by Fable)

**Repo:** Macro Dashboard · **Date:** 2026-07-12 · **Author:** Fable (main loop), from an 8-lane
census + 3-lane web research fan-out (11 agents) adjudicated against `INTL_FIX_MASTERPLAN.md`,
`DO_NOT_REBUILD.md`, RRX rulings, and the forex/bond dashboard honesty bars.
**Operator ask:** extensive international upgrade to track risks, rotations, velocity, rates,
central-bank actions, liquidity, forex, sovereign debt, swap lines, credit spreads/deterioration,
blow-up risk, EM stress, contagion-to-US, DXY outperformance / dollar safety.

---

## §0 — Thesis and scope fence

The 2026-07-02 INTL_FIX program settled the *scoring* question: every validated intl edge is
drawdown-side; the C1–C8 channel book was executed and mostly died honestly (only C3 global
breadth CONFIRMED-wired-accruing, C4a REER CONFIRMED-recorded-unwired). **This program does not
reopen any of that.** IRD is the *risk-desk layer* the same masterplan's §0 named but never
built out: a display/context-tier early-warning surface — who is fragile, where stress is
igniting, whether it is transmitting to US markets, and what kind of dollar move is underway.

Scope fence (IRD-R1): **zero scoring-seam wires.** Nothing here touches `conditions`,
`stock_score`, `name_score`, radar `_LEG_CALIB`/profiles, or `intl_feed` weights. Promotion of
any IRD metric to authority goes through `scripts/intl_phase0.py` as a NEW pre-registered claim
(the constitution stands unchanged). Per house law, this display/context infrastructure ships
freely — the gauntlet is a promotion gate, not a build gate.

## §1 — Adjudicated gap map (census, 2026-07-12)

Exists — reuse, do not rebuild: 7-country quad regimes + recession/equity-risk gauges;
USD leaderboard/RRG/correlation/RORO (`intl_performance`); rates desk w/ carry, real yields,
ECB impulse, EZ periphery spreads (`intl_rates`); G7 sovereign scorecard + `BAMLEMCBPIOAS` +
EMB trend (`intl_bonds`); Dollar Desk 7 legs incl. REER + smile-confirm + triple-red haven-loss
(`forex_dollar`); 6-scenario FX stress regimes incl. carry-unwind, wrecking-ball, EM
crisis/capital-flight (`forex_regime`); dollar→asset transmission betas (`forex_transmission`);
CNH basis (display; C4c scored-dead); CN/HK/CA calibrated radars (accruing to can_force,
composite frozen); US radar Tier-B `global_breadth` + `jpy_carry` (accruing); Fed plumbing lobe
(WALCL/RRP/TGA/EFFR/SOFR-vs-IORB); `global_liquidity` Fed+ECB+BoJ impulse; BIS credit gap
(US/CN only); 23-ETF country substrate (weekly, off-render); ADR sensor set; OFR FSI.

Missing — the IRD build:

| # | Gap | Confirmed by |
|---|---|---|
| G1 | Fed swap lines + FIMA: `liquidity_plumbing` Phase-5 slots are explicit nulls; no collector | plumbing lobe + data-layer lanes |
| G2 | EM credit-spread ladder: one aggregate series only; no HY/regional/quality EM OAS family; no ETF-implied long-history proxies | bonds + data-layer lanes |
| G3 | EM stress composite: no deterministic fast-trigger index; no VXEEM; no EM-dollar index panel | all lanes |
| G4 | Contagion measurement: no spillover index, no correlation-tightening read, no origin-vs-US-transmission framing anywhere | radar + weather lanes |
| G5 | Dollar-funding stress: corridor spreads exist in plumbing lobe (US-facing) but no intl surface; no x-ccy basis (no free daily source — §4 IRD-R6) | bonds lane + research |
| G6 | DXY factor: dollar strength never decomposed rates-driven vs safety-driven; DXY zero-wired on intl.html | surface + forex lanes |
| G7 | CB action desk: only ECB balance-sheet impulse exists; no cross-CB policy-rate/stance/meeting table | all lanes |
| G8 | Velocity: no rates/credit/FX velocity boards (5d/20d z), no cross-country curve-inversion board | bonds + surface lanes |
| G9 | Sovereign debt sustainability: no debt/GDP, primary balance, current-account map; BIS gaps US/CN only | bonds + research lanes |
| G10 | Bank-stress daily lane: no KRE/SPY-class relative-strength read on intl surfaces (reverse-contagion detector, Mar-2023 class) | research lane |
| G11 | Surface: intl.html has no risk desk; DXY/credit/CB/contagion absent from the page | surface lane |

## §2 — Metric taxonomy (exact free sources; two-speed law IRD-R2)

**FAST (daily, mostly coincident thermometers — the trigger layer):**

| Metric | Source (exact) | Notes |
|---|---|---|
| EM OAS ladder: EM HY, Asia, LatAm, EMEA, fin/non-fin, euro-denom, Euro HY | FRED `BAMLEMHBHYCRPIOAS`, `BAMLEMRACRPIASIAOAS`, `BAMLEMRLCRPILAOAS`, `BAMLEMRECRPIEMEAOAS`, `BAMLEMFSFCRPIOAS`, `BAMLEMNSNFCRPIOAS`, `BAMLEMEBCRPIEOAS`, `BAMLHE00EHYIOAS` (+ existing `BAMLEMCBPIOAS`, `BAMLH0A0HYM2`, `BAMLC0A0CM`, `BAMLH0A3HYC`) | builder verifies each id live, drops dead ones with a note. **Vintage law IRD-R9**: FRED caps BAML to rolling 3y (Apr-2026) — accrual starts at first fetch; long-window stats use ETF proxies until depth accrues |
| EM bond ETF proxies (long history) | yfinance `EMB`, `PCY`, `EMLC`, `VWOB` (+ existing EMB); spread proxy = ETF yield-vs-`DGS10` trend or EMB/IEF ratio | primary long-history z-score substrate |
| EM equity/FX vol | FRED `VXEEMCLS`; realized vol computed from EM FX pairs already collected (TRY/ZAR/BRL/MXN/IDR/CLP/PLN + KRW/INR/TWD in intl store) | EVZ is DEAD (ended 2025-03) — do not collect |
| EM-economies dollar index | FRED `DTWEXEMEGS` (EME), `DTWEXAFEGS` (AFE) if not already collected | broad `DTWEXBGS` exists |
| Corridor / plumbing spreads | existing FRED `SOFR`, `EFFR`, `OBFR`, `IORB` (verify presence; add missing) → SOFR−IORB, EFFR−IORB, OBFR−IORB | Sept-2019-class read; quarter-end spikes are technical — label |
| Swap lines + facilities | FRED `SWPT` (CB liquidity swaps, Wed level), `WLCFLL` (liquidity+credit facility loans), weekly | **confirmation tier** (IRD-R5): grades severity, never triggers alerts |
| Treasury vol | yfinance `^MOVE` (exists) | staleness-guarded |
| Bank-stress RS | yfinance `KRE`, `KBWB`, `EUFN` vs `SPY` (add missing tickers), 20d RS | the 2023 reverse-contagion lane; read RELATIVE only |
| DXY smile decomposition | computed: rolling OLS of DXY (`DX-Y.NYB`, exists) on US-minus-basket 2y differential (FRED `DGS2` + DE/JP/GB 2y where live); residual = safety premium; same-day flag: DXY up + `DGS2` down = safety bid | IRD-R10; window sensitivity printed |
| Spillover index (flagship) | computed: Diebold-Yilmaz total + directional connectedness, rolling generalized-VAR FEVD over Garman-Klass vols of ~12 country ETFs (`data/intl_etf`) + `EEM` + `SPY` | IRD-R4 pre-registered params: window 150d, VAR lag 2, horizon 10d, GK range vol; daily from existing stores, zero new collection |
| Correlation tightening | computed: rolling 60d EEM-vs-EM-FX-basket corr; cross-country ETF avg pairwise corr velocity | census: `intl_performance` corr matrix exists — add the *velocity* read |
| Rates/credit/FX velocity | computed on existing sovereign 10y roster, OAS series, FX pairs: Δ5d/Δ20d + z vs 2y (or max history w/ disclosure) | IRD-R13 shared vocabulary |
| Curve inversion board | computed from `intl_bonds` ROSTER (exists) + KR/IN where series live | synchronized-inversion count is the display stat |

**SLOW (monthly–annual, genuinely leading — the vulnerability map):**

| Metric | Source | Notes |
|---|---|---|
| Debt/GDP, fiscal balance, current-account | IMF DataMapper API `imf.org/external/datamapper/api/v1/{GGXWDG_NGDP,GGXCNL_NGDP,BCA_NGDPD}` (annual, WEO Apr/Oct; the GGXONLB primary-balance series is not exposed by DataMapper v1 — overall balance substituted, W1) | new tiny keyless adapter |
| BIS credit-to-GDP gap + DSR | existing BIS adapter — extend `config.bis.series` to JP/GB/EZ(XM)/KR/BR/MX/TR/ZA/IN/ID | quarterly |
| REER deviation | BIS REER already collected per-currency (H.10 family) — compute 5y-mean gap per EM | reuses forex REER pattern |
| Reserves adequacy (context row) | IMF IFS reserves where trivially fetchable; else printed as data-gap null | do not build a scraper for v1 |
| CB meeting calendar | hand-curated `data/intl_risk/cb_calendar.yml` (Fed/ECB/BoJ/BoE/SNB/BoC/RBA remaining-2026 published dates) | display-only date table; **no intent prediction** (IRD-R7) |

**Known free-data walls (print as nulls, do not fake):** daily cross-currency basis (IRD-R6),
FX risk-reversals/skew, EPFR true flows, per-country sovereign CDS, maturity-wall feeds,
PBoC balance sheet (keyless), BoE balance sheet (annual-only). TIC is 6–7wk lagged —
structural context only, never on the trigger path.

## §3 — Architecture

Collection (all additive, config-first): FRED ids ride the existing adapter via `config.yml`
`fred.series.*` (**alias-collision law**: duplicate ids must reuse the same column alias — a
conflict kills the whole fred adapter, 2026-07 8-run outage class); yfinance tickers ride
existing yahoo groups (`overwrite_overlap=True` law); BIS keys ride `config.bis.series`;
one new adapter `collectors/imf_weo.py` (annual JSON, ~20 countries × 3 indicators) in the
weekly/pipeline-batch lane; `cb_calendar.yml` is static data. Frozen-tail detector covers new
series via cadence config. **Nothing enters the daily critical path except cheap FRED/yahoo
line-items on existing fetches.**

Engines (pure leaves, fail-open, import nothing from scoring core):
- `engine/intl_risk.py` — EM stress composite (fast trigger: EM OAS level+velocity z, VXEEM,
  EM FX basket drawdown+realvol, EM equity breadth from `data/intl_etf`, EM-dollar-index
  velocity; K-of-N agreement per IRD-R8) + slow vulnerability table (IMF/BIS/REER rows,
  multi-indicator flag counts).
- `engine/contagion.py` — DY spillover (total + top-3 transmitters + US-directional), corr
  tightening, and the **two-tier read** (IRD-R3): Tier-1 origin stress (which region, what
  velocity) vs Tier-2 US transmission (US HY OAS velocity, KRE/KBWB/EUFN-vs-SPY RS, MOVE,
  corridor spreads, DXY safety residual) → one plain-word state:
  contained / watching / transmitting.
- `engine/cb_desk.py` — per-CB policy rate level, last-change date/direction, 3m trend,
  balance-sheet impulse where live (Fed/ECB/BoJ; honest nulls for PBoC/BoE), next-meeting
  dates from the YAML.
- `forex_dollar.py` extension — smile-decomposition leg (rates-driven vs safety-driven read +
  residual series) exported for both the forex page and intl.html.
- `liquidity_plumbing` Phase-5 fill — `swap_lines_bn` / `fima_repo_bn` from the new SWPT/WLCFLL
  series (the lobe's own ruling: fill only via a real collector — satisfied).
- `intl_bonds` / `intl_rates` extensions — inversion board + velocity columns (IRD-R13 grammar).

Outputs: `data/intl_risk/latest.json` (+ per-piece keys inside existing `data/intl/latest.json`
where natural), `bond_health.json` gains an `intl` namespace, synapse.yml registrations for
every new artifact (mag7-regime block = template). world_state: one display-only lobe extension
(`fx_dollar` gains smile + swap-line keys; or a thin `intl_risk` compose) with
`score_raise=False, hard_gate=False`.

Surface (`templates/intl.html.j2`, macro mode, insertion after the rates block):
1. **Global Risk Board** hero strip — 4 state chips (EM stress / contagion / dollar / funding),
   each with a plain-word stance per Design Doctrine Law 1.
2. **Contagion board** — spillover dial + who-is-transmitting + Tier-2 US-transmission chips.
3. **Central-bank desk** — cross-CB table (rate, last move, direction, BS impulse, next meeting).
4. **Credit & sovereign desk** — OAS ladder w/ velocity arrows, inversion board, EM ETF spread
   proxy sparks.
5. **Dollar decomposition card** — rates-driven vs safety-driven, safety-bid day flag.
6. **EM vulnerability map** — slow table, Berg-Pattillo caveat as the Tier-2 receipt.
All bilingual; internal names (Diebold-Yilmaz, OAS, GK vol) demoted to hover receipts;
reuse `.rcard`/`.rdesk`/`.kpi`/`.chip` scaffolding — no new idiom.

## §4 — Rulings (IRD-R1..R13)

- **IRD-R1 · Scope fence.** Display/context tier only; zero scoring-seam wires; promotion only
  through `intl_phase0` new pre-registered claims. Restates the constitution.
- **IRD-R2 · Two-speed law.** Slow fundamentals = vulnerability map (who is fragile); fast
  market = trigger (is stress igniting). Lead/lag labeled honestly on Tier 2: coincident
  thermometers (OAS, VXEEM, correlations) are never captioned "leading"; only fundamentals and
  broad-dollar+VIX earn that word.
- **IRD-R3 · Two-tier contagion framing.** Origin stress (Tier-1) and US transmission (Tier-2)
  are separate reads; "is it coming for US markets" is answered ONLY by Tier-2 observables.
  Same EM spread level with quiet Tier-2 = "contained — watch"; with hot Tier-2 = "transmitting".
- **IRD-R4 · Spillover index.** DY connectedness is the flagship self-built contagion gauge.
  Parameters pre-registered here: 150d window, VAR(2), H=10, Garman-Klass vols, basket =
  12 country ETFs + EEM + SPY. Parameter changes require a masterplan edit, not code drift.
- **IRD-R5 · Swap lines are confirmation, not triggers.** Weekly Wednesday levels lag price
  stress by days-to-weeks (2008/2011/2020 case law). They grade severity after price signals
  fire; no alert keys off them.
- **IRD-R6 · Cross-currency basis: data-blocked, not killed.** No free daily source exists
  (OFR STFM is US-repo-only; CME XEURBI paid). The futures-implied proxy is DEFERRED (noisy,
  IMM-lumpy). Corridor spreads + MOVE + swap-line usage carry the funding read. Revisit only
  with a verified free daily source in hand.
- **IRD-R7 · CB desk is descriptive.** Levels, realized changes, direction, BS impulse, and a
  static meeting-date table. Policy-intent prediction / decision forecasting stays FORBIDDEN
  (PS-R1/PS-R4 restated). No consensus-surprise scoring (no free consensus source).
- **IRD-R8 · Vulnerability map honesty.** The slow table is a fragility MAP, not a signal.
  Berg-Pattillo printed on the receipt (best EWS missed ~68% of crises OOS; ~60% of signals
  false). Any country-level "fragile" word requires ≥3 concurring indicators.
- **IRD-R9 · BAML vintage law.** All OAS series accrue nightly into our own store from first
  fetch (FRED 3y rolling cap since Apr-2026). Long-window percentiles on capped series are
  forbidden without an on-surface depth disclosure; ETF-implied proxies are the long-history
  substrate meanwhile.
- **IRD-R10 · DXY decomposition is display.** Smile residual + safety-bid flag ship as context;
  window sensitivity shown on hover; any scored use requires its own prereg through the
  constitution (C4a's deferred MRS-orthogonality gate is untouched).
- **IRD-R11 · Routing.** Sonnet builds, Opus reviews, Fable (main loop) adjudicates/merges;
  workflow stages carry explicit models; mechanical stages run effort=low.
- **IRD-R12 · Surface law.** Design Doctrine binds every panel: stance vocabulary on Tier 1,
  banned vocab demoted to hover receipts, one as-of + one footnote per panel, bilingual parity,
  reuse existing card idioms (no new tape forms; tape v3 is the only sanctioned tape).
- **IRD-R13 · Velocity grammar.** One shared construction everywhere: Δ5d and Δ20d, z-scored on
  2y history (or max available, disclosed). "Velocity" means exactly this on every IRD surface.

Standing kills this program must not disturb: C1/C2/C4c/C5/C6/C7/C8 (all CONTEXT/INVERTED,
weight 0), per-pair FX gating (INTL-43), lead-lag read-throughs beyond transmission reads
(ADJ-4), CN/HK/CA radar composites (accruing — frozen), TED-spread resurrection (LIBOR dead),
market_drivers as canonical shock read (TI-R1 — no parallel shock classifier here: the
contagion state is a cross-market transmission read, not a shock-type vocabulary).

## §5 — Field guide (understanding-before-backtest; the playbook the metrics serve)

Case law (research lane, free-data observable sequences):
- **Asia 1997**: REER overvaluation + reserves drain (slow, quarters) → THB peg break →
  regional FX cascade → US hit late and modest (DJIA −7.2% Oct, ~4mo lag). Lesson: slow map
  flags the region; FX velocity is the ignition read.
- **Russia/LTCM 1998**: sovereign default → leveraged intermediary → S&P −19% in weeks.
  Lesson: Tier-2 transmission (US credit + funding) is what converts an EM event into a US one.
- **Argentina 2001 / Turkey-Argentina 2018**: violent origin stress, Tier-2 quiet → contained;
  US barely moved. Lesson: IRD-R3 exists precisely for these — origin loudness ≠ US risk.
- **Taper 2013**: US-originated; fragile-five sorted by the slow map (CA deficit, reserves).
  Lesson: the vulnerability table predicts the cross-section, not the timing.
- **CNY 2015**: FX regime surprise → global equity spillover (S&P −12%, recovered). Spillover
  index + correlation tightening are the right thermometers.
- **COVID 2020**: dash-for-cash — basis/MOVE first, swap lines drawn to $449B *after* price
  stress. Lesson: IRD-R5 ordering (price leads, quantities confirm).
- **Gilts/LDI 2022**: sovereign-market microstructure; MOVE + GBP vol led; CB backstop resolved.
- **US regionals 2023**: reverse contagion; KRE/SPY RS led headline indices by days. Lesson:
  the bank-RS lane looks both directions.
Per-type playbooks (what the desk says to do) live in the panel stances: origin-only stress →
"watch — don't chase"; transmitting → "protect gains / de-risk EM-linked exposure";
funding stress confirmed → "expect vol everywhere, cash is a position".

## §6 — Waves (each = one PR, branch off fresh origin/main, same-day squash-merge)

- **W0 (this PR)** — masterplan + rulings.
- **W1 · Substrate** — config FRED/yahoo/BIS additions (each id liveness-verified at build
  time), `collectors/imf_weo.py` + weekly lane wiring, `cb_calendar.yml`, swap-line series →
  `liquidity_plumbing` Phase-5 fill, synapse registrations, tests (incl. alias-collision guard
  + frozen-tail cadence entries). *Sonnet builds, Opus reviews.*
- **W2 · Engines** — `intl_risk.py`, `contagion.py`, `cb_desk.py`, `forex_dollar` smile leg,
  `intl_bonds`/`intl_rates` velocity+inversion extensions, `data/intl_risk/latest.json` +
  `bond_health.json` intl namespace + world_state display lobe, tests (causality, fail-open,
  null-honesty, determinism). Runs inside `cl_markets` (fast leaves on already-loaded stores).
- **W3 · Surface** — intl.html Risk Desk section (6 panels §3), bilingual, doctrine §5
  checklist enforced in review, vm-render harness + browser screenshot verification with
  prod-shaped data.
- **W4 · Integration & close-out** — macro_context weather-station `intl_risk` domain card,
  hub stat, ACTIVE_BUILD_MAP regen, memory file, status log here.

Acceptance: intl.html answers, at a glance and in plain words, the four operator questions —
*Is EM stress igniting? Is it reaching US markets? What kind of dollar move is this? Are
central banks adding or draining?* — with every number carrying its meaning and every null
printed.

## §7 — Clocks

- 2026-07-31 / 2026-09-15 — (existing, unchanged) intl radar grades / earliest can_force.
- 2026-08-15 — IRD review: accrued BAMLEM depth check (IRD-R9 disclosure still accurate?),
  spillover-index sanity vs realized episodes, panel copy audit.
- 2026-10-15 — promotion review: if any IRD metric shows apparent lead in its forward accrual,
  draft the intl_phase0 claim (new declared family; no scan before declaration).

### Status log
- 2026-07-12 — Masterplan authored (Fable) from 11-agent census+research fan-out; W1 dispatch next.

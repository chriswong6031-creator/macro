# LIVE ORDER FLOW & THE OPTIONS TAPE — brainstorm + integration assessment by Fable

_Authored by Fable, 2026-07-04. Instigated by the operator's decision to acquire ThetaData
options access (top tier) + two external (ChatGPT) docs. Grounded in a full read of the live
codebase, the four governing masterplans (OPTIONS_ALPHA, ORACLE, NEURAL_WEB, LIVE_DATA), the
signing-calibration postmortem, and vendor/licensing research. This is an ASSESSMENT +
program-amendment doc, not a new program: the work lands as amendments to the programs that
already own these surfaces. Operator STOP list at §11._

---

## §0 In plain English

We are buying the full options tape: every option trade with the quote at execution, every
quote, daily open interest, implied volatility, and Greeks — live, and back to 2012.

The single most important thing to understand: **the biggest prize is not the "live" part.**
Our options program (OPTIONS_ALPHA_MASTERPLAN, authored yesterday) was deliberately built
around three data walls: we couldn't know trade direction (proven: bar-level signing is worse
than a coin flip), we couldn't backfill open interest (every claim had to wait months for data
to accrue), and we couldn't afford the tape. This purchase tears down all three walls at once.
Four families of pre-registered claims that were scheduled to get verdicts between September
and December 2026 can instead be backtested on 12–14 years of history **in weeks**. That is
the certain win — it's data, not alpha, so it cannot fail to arrive.

The probable win: Oracle (the rotation brain) detected June's semis→healthcare rotation as a
three-week cascade from price alone. Options pressure — put premium building in the group money
is leaving, call premium and open interest building where it's going, measured across many
members at once — should make those early detections *more trustworthy* (fewer false alarms at
the sensitive tier) and *somewhat earlier* (days per leg, honestly, not weeks). And crowding /
exhaustion signatures (everyone piling into short-dated calls after the move) attack our
weakest flank: we still have no validated exit rule, and every strong number in this repo is
defensive.

The trap to avoid: becoming an "unusual whales" dopamine feed. A big call sweep is not a
signal; it's a print with unknown intent (hedge? spread? closing?). House law already handles
this: everything ships display-only until a pre-registered gate passes, flow gets aggregated
to group level with breadth and persistence requirements, and no hand-weighted composite score
gets invented. The plan below routes every ChatGPT idea through that constitution.

---

## §1 What actually changed (the constraint-reversal table)

OPTIONS_ALPHA_MASTERPLAN §1 documented the data reality this program was designed around.
ThetaData Options Pro reverses it point by point:

| # | Constraint (as ruled 2026-07-03) | With ThetaData Pro | Consequence |
|---|---|---|---|
| F6 | **OI backfill blocked.** No OI in massive flat-files; point-in-time snapshots only from 2026-06-15. Procurement parked (§6, W4.1) | **Daily OI across all strikes/expirations, ~12y history, bulk endpoints** | S-DOI, S-CWIV, S-XZZ gates stop being accrual-bound (see §4) |
| F7 | **Flow direction permanently soft.** Minute-bar tick-rule net-sign recovery 0.41 vs Databento NBBO truth; delta-adjust tested & rejected; "reliable direction requires the trade-level NBBO tape (paid)" | **Every trade with NBBO at execution (+2 post-trade updates), and trade-stamped Greeks** | Quote-rule aggressor signing becomes possible *by construction*. The signing gate gets re-calibrated, not assumed (§7.1) |
| F4 | **Validation timelines: Sept–Dec 2026** (30-obs buckets, 60-date IC, 120-date cross-sections) | **3,000+ historical dates × full cross-section** | ETAs collapse to compute time (§4) |
| F5 | IV backfill = BS-inversion **approximation** off day-agg closes (W1.1, in flight), 2024-07→ only, rank-corr acceptance vs 18 overlap days | **Vendor IV + Greeks (1st/2nd/3rd order), 12y, tick→EOD** | W1.1 gains a ground-truth acceptance benchmark, then gets superseded for depth (§7.3) |
| §6 | Procurement table: OI history / tape / real-time all parked "until a validated use-case funds the tape" | **One subscription buys every line of that table** | The table's triggers are moot; the *discipline* (validate before scoring) is not |

Also relevant: massive.com stays — it is the **stock** day-agg plane (12,664 tickers, R2) and
the current GEX REST snapshot source. ThetaData replaces/extends only the **options** side.
US-only: none of this touches the CN/HK/CA desks (no OPRA equivalent in scope).

**In plain English:** yesterday's masterplan was a careful plan for cooking with three
ingredients missing from the pantry. We just bought the pantry. The recipes (gates, doctrine,
harnesses) were all written to survive exactly this upgrade — almost nothing needs redesign;
things need *running*.

---

## §2 What we already have (inventory — do not rebuild)

The ChatGPT docs propose building a system much of which exists. The real estate:

**Engines (options):** `options_flow.py` (measured dealer flow off minute aggs; direction
marked soft by `signing_gate.json`), `flow_signing.py` + `scripts/calibrate_flow_signing.py`
(the calibration harness, ready to point at a new tape), `gex_model.py`/`gex_engine.py`
(per-name walls/flip/regime/IV-rank; SPX board), `market_gamma.py` (whole-market dealer-gamma
vol context feeding the banner + `data/regime/latest.json`), `gex_confirm.py` (entry confirmer
wired into `build_stock_library`, gated), `options_skew.py` (XZZ) + `options_ivspread.py` (CW)
with validators + gates waiting on dates, `options_universe.py` (ONE universe resolver:
anchors + basket members, capped), `vol_regime.py` (validated, DSR 0.9998; VVIX candidate leg
recorded), `theme_flow_rollup.py` (ETF-holdings flow — a different "flow", 1–5d lag, display),
`group_flow.py` (price-based rotation fingerprint; `cohesion_chg` is the one FDR survivor).

**Data:** `data/polygon_gex/` (355–384 names/day since 2026-06-15: per-name summaries +
per-contract chains with OI/IV/greeks), `data/massive_options_day/` (day-agg cache, R2),
`data/options_flow/` accruals + `site/flow/` payloads (un-deadened 2026-07-03), `data/cboe/`
(SPX GEX, VVIX 2006→, VIX curve), `data/iv_history/` (W1.1, in flight).

**Consumers, wired and gated (the integration lattice):** stock_score GEX + IV-spread tilts
(gate-locked off), evidence-stack GEX-OPTIONS badge (one vote in k-of-n on us_standouts buy
rows), Mastermind `_flow_row` lens, gex.html surfaces. **Nothing scores today — correct.**

**Fire ledger:** `data/us_board_ledger/retro_grades.parquet` — verified: **starts 2026-06-15**
(950 rows, git archaeology to 06-16). There is no deep history of board fires. Any claim
conditioned on *our own entries* stays forward-accruing regardless of vendor history — this
bounds what backfill can and cannot buy (§4, §9).

**Reserved slots in other programs (already designed, waiting for this data):**
- Oracle P7: "options/IV/GEX columns … options layer earns its own Phase-0."
- Neural Web: options nerves register in `synapse.yml` (W0); world_state carries an options
  block (N1); Article 2 forbids display-tier signals from ranking anything.
- LIVE_DATA_ARCHITECTURE Tier E: "GEX (live options OI/IV)" = the deferred Phase 4 slot.
- DISPLAY_VS_SCORING_MANIFEST: the seam registry any eventual score-wiring must name.

---

## §3 The honest thesis: where the tape helps a 1–20d rotation/swing shop

Our identity (from the repo's own verdict lane): *a drawdown-control machine with episodic
entry edges, trading 1–20d swing entries into theme/sector rotations.* Not market-making, not
0DTE, not latency-sensitive. Ranked by expected value **for this shop**:

1. **Validation acceleration (certain).** Verdicts in weeks instead of Q4/Dec-2026 on the
   already-registered claim families. Value: every downstream program (standouts, Oracle,
   species) learns *this year* which options context matters. This alone covers the cost.
2. **Rotation confirmation quality (probable).** Oracle's early tier is the front-run edge,
   and its binding constraint is false alarms (the DEFENSIVE_ROTATION lesson: 80% false-alarm
   on naive triggers). Group-level flow breadth/persistence is an *independent* evidence leg —
   not derived from the same price panel — which is exactly what a confirmation tier wants.
3. **Exit/crowding evidence (probable, underrated).** Short-dated OTM call-share spikes, IV
   percentile blowouts with weak price response, put-selling-into-strength collapse: exhaustion
   signatures on the group we're LONG. We have **no validated exit rule** (EXIT-rule verdict:
   NO-GO; EMA8 tail-flag only), and the repo's strongest validated asymmetry is the SELL side
   (−1.24%/40% base rate). Mechanism-aligned with our defensive identity.
4. **Stealth lead (uncertain, capped).** Flow breadth rising while price velocity is flat.
   Honest calibration below (§9): expect days of lead per cascade leg, not weeks — and only
   sometimes.
5. **Entry-quality modifiers on standouts (uncertain).** IV-rank, ΔOI persistence, signed-flow
   z at fire date. Cross-sectional evidence buildable now; fire-conditioned proof still waits
   on the ledger.
6. **Live intraday flow (low, defer).** At our horizon, a 15-minute batch ≥ covers it. 40ms
   streaming buys nothing a swing book can monetize. Live tier is a *product* decision
   (dashboard freshness), not an alpha decision, and stays behind a validated use-case.

**The June counterfactual, honestly.** The cascade (foundries OUT 06-08 → … → broad index
06-29; healthcare IN stepwise from 06-01) was detected from price velocity ~3 weeks before the
page's alerts existed. Would options flow have seen it *earlier*? Probably each leg by 0–3
days (options volume/put-pressure often coincides with or slightly leads the velocity break —
Johnson-So O/S evidence is ~weekly-horizon), and the routing destination (healthcare call/ΔOI
build) possibly earlier. Would it have seen it *clearer*? Very likely — that's the breadth/
persistence/two-sided confirmation story, and it's the claim we can actually test on the
catalog (§5.1). "Much more accurate" is plausible; "much earlier" is not the base case. The
gauntlet decides.

---

## §4 The unlock table — every existing gate whose ETA collapses

_The certain value, itemized. "Now" = compute time after T1 backfill (§7), not calendar
accrual. Gate IDs from OPTIONS_ALPHA_MASTERPLAN §4._

| Gate | Claim | Old ETA (accrual-bound) | With ThetaData history | Notes |
|---|---|---|---|---|
| S-CWIV | Cremers-Weinbaum call−put IV spread, cross-sectional | ~**Dec 2026** (120 dates × 15 names) | **Now** — 3,000+ dates × 300–800 names, era-split | Needs OI-weighted PIT chains — exactly what vendor OI history provides. A2's "backfill cannot rescue them" was true *of massive*; it is false of this purchase |
| S-XZZ | Xing-Zhang-Zhao skew, cross-sectional | ~**Dec 2026** | **Now** — same | Same |
| S-DOI | ΔOI 5d persistence rank-IC | ~**mid-Sept 2026** (60 dates) | **Now** — 12y of daily OI | Also enables era-decay measurement (did it die post-2015?) |
| S-GEXR | gamma regime → forward realized vol | ~**Sept 2026** (30 obs/bucket/name) | **Now** — reconstruct per-name GEX 2012→ from chains+OI+greeks | Reconstruction must replicate `gex_model`'s dealer-sign assumptions; label as reconstructed |
| S-IVR | IV-rank as entry filter | fires n≥30/bucket **~Q4-26** | **Split:** cross-sectional IC leg now; fire-bucket leg still Q4-26 | Fire ledger starts 2026-06-15 — history does not manufacture fires |
| S-VOI | Vol>OI fresh-positioning burst | fires **~Q4-26** | Split, same as S-IVR | Cross-sectional read now; standout-conditioned read waits |
| S-WALL | put-wall stop placement | n≥100 fires (long tail) | Partial: wall-touch **base rates** computable on 12y of reconstructed walls; stop-out *on our fires* still accrues | Base rates de-risk the design before fires mature |
| S-SQZ | squeeze precondition | ~Q4-26 | Partial: historical squeeze-episode study now; fire-conditioned later | Short-interest staleness fix (W2.5) still binding |
| signing gate | `direction_reliable=false` | permanent on bar data | **Re-calibrate now** on trade+NBBO (§7.1) | Direction ≠ intent even when signing is right — §6 |
| W1.1 IV backfill | approximation acceptance (rank-corr ≥0.90 vs 18 vendor days) | in flight | Benchmark against 2y of **real** vendor IV overlap; then supersede for 12y depth | Don't cancel W1.3 stamps — swap the source |

**In plain English:** we pre-registered nine bets and were waiting months for the dice to be
rolled enough times. The purchase hands us the full history of past rolls. Some bets can be
settled immediately; the ones about *our own trades* still need our own trades.

---

## §5 Integration designs, per engine

### 5.1 Oracle (the rotation lobe) — the flagship study

Oracle P7 already reserves this and demands "its own Phase-0." Pull it forward to run right
after P2 (episode catalog exists), as **Oracle Phase-0-Options (O-OPT)**, pre-registered
before anyone looks at the joined data:

- **O-OPT-1 — Flow-before-rotation (the lead-lag question).** Join per-episode windows
  ([−15, +15] sessions around each catalog onset, sector-level 2012→, subsector-level 2021→)
  against daily group-aggregated options features: source-complex put-premium z + ΔOI-put
  build + skew steepening; sink-complex call-premium z + ΔOI-call build + IV-term lift; flow
  **breadth** (% of liquid members confirming, concentration-penalized); sector-ETF
  confirmation. Measure the *lead-lag distribution* of options pressure vs the catalog's
  early-tier price detection, per regime. Placebo: random-onset pseudo-episodes (O6's
  machinery). Kill: median lead ≤ 0 sessions vs early tier AND no false-alarm discrimination.
- **O-OPT-2 — Confirmation quality (the false-alarm question).** Among early-tier detections,
  does flow-confirmation split persistent episodes from failures? Gate on the catalog's own
  outcome labels (sink-vs-source forward spread at +5/21/63d). This is the highest-probability
  claim in the whole doc — it asks options data to *filter*, not to *lead*.
- **O-OPT-3 — Routing-matrix conditioning.** For A-breaks-down → where-does-money-go cells
  (the 73%-hit style candidates): does destination call/ΔOI pressure in the first 1–5 sessions
  improve routing hit rates? Rides the same FDR/trial-ledger discipline as O1; tiny-n cells
  stay pre-FDR candidates.
- **O-OPT-4 — Two-sided flow pairing.** The 06-26 `semis::out ↔ healthcare::in` pairing rule
  gains a flow leg: two-sided episodes with *opposed* flow signatures (puts building in
  source, calls in sink) vs one-sided. Conditional persistence delta.

Consumption on pass: new panel columns (O0 already anticipates options columns), episode-card
annotations, and — only after passing under Oracle's O6 gauntlet — a confirmation input to the
detection tiers. **Never a hard gate** (China falsification: cross-engine hard gates are
banned without their own gauntlet).

**PIT hygiene specific to this join:** options trades/quotes/OI are as-reported (clean).
The *baskets* are not — Tier-M membership is survivorship-declared; O-OPT claims on Tier M
carry the same watermark as everything else on Tier M. Sector-level (ETF + PIT-SP1500 panels,
2012→) is the validation tier; subsector is the detection-resolution tier. This mirrors
Oracle's own cross-granularity principle exactly.

### 5.2 us_stocks.html Top Standout Stocks — entry-quality modifier

The operator's ask: "higher scores for stocks with positive order flow." The constitutional
path (validate-before-score) — and the fastest honest version of it:

1. **Stamp now (extend W1.3's column family):** add signed-flow columns to the nightly stamp
   set on `retro_grades.parquet` — `opt_net_signed_prem_5d_z`, `opt_flow_breadth_group`,
   `opt_dte_quality` (8–90DTE share), `opt_crowding_flag` (short-dated OTM call-share spike ×
   price-extension), alongside the already-planned `opt_gamma_regime`/`opt_iv_rank_252`/
   `opt_doi_slope_5d`/etc. Same A9 single-writer discipline; nullable; no grading-logic
   changes.
2. **Display now:** an "Options context" chip row on standout cards (EN+ZH, popover per house
   i18n law) — IV-rank, ΔOI 5d, signed-flow tone (still `~`-soft until the signing gate
   re-passes), crowding caution. Confirmer semantics only: chips may *lower* visual
   confidence, never raise rank (Neural Web Article 2, adopted early).
3. **Validate two-lane:**
   - *Lane A (now):* cross-sectional — do signed-flow/ΔOI/IV features rank forward returns on
     the liquid US universe 2012→? This is S-DOI/S-CWIV/S-XZZ machinery extended by two signed
     features; same harness, same FDR family.
   - *Lane B (accrues):* fire-conditioned bucket tests in ledger primitives
     (`post_cushion_breach`, `terminal_state_clean8_21`, `fwd_mfe_21`) — the only currency
     gates may speak (A10). n≥30/bucket lands ~Q4-26 regardless of vendor history.
4. **Wire on verdicts (options-alpha W5, unchanged):** passed features → `stock_score` tilt
   via the manifest's named seams; the species program registers any new entry species
   through its own constitution — no back door.
5. **The crowding penalty is its own claim** (predict: it validates on the SELL/avoid side
   before anything validates on the BUY side — consistent with the house's defensive edge).

### 5.3 Neural Web — the options nerves

Neural Web is at operator STOP; when W0 (synapse) lands, options artifacts register like
every other bus citizen. What this program should hand it:

- **Nerve registrations (`synapse.yml`):** `options_flow` (per-name + group daily features),
  `gex_state` (per-name + index regime), `iv_surface` (rank/term/skew), `options_events`
  (unusual-activity events, §5.5) — each with producer, schema, freshness SLA, tier
  (DISPLAY at birth), `weights: none`.
- **World-state block (N1):** index GEX regime + IV-rank aggregate + net flow tone join
  `market_gamma`'s existing whole-market verdict as the options sense-organ of the blackboard.
- **Reliability kernel (N3):** options nerves enter with zero track record → shrunken
  posteriors keep them near-prior until graded claims accrue; no nightly significance-peeking
  (quarterly FDR batches). The kernel is *the* mechanism that answers "how much should the
  brain trust flow?" — empirically, per regime, over time.
- **Confluence graph (N4):** flow-vs-price **divergence** becomes a first-class edge type
  (options nerve contradicts price nerve on the same group) — annotation-tier until it holds
  SHADOW-with-track-record.
- **Reflex (N6, later):** ONE options reflex candidate — group-level unusual-flow burst →
  alert_triage event (sub-hour tier). It earns the push tier only by graded firing record.
- **Cortex:** flow features feed `master_brain`'s prompt state like other blocks, with
  `_tape_family` provenance so options-derived and price-derived reads of the same move don't
  double-count. LLMs never originate flow signals (Article 1; six clamps precedent).

### 5.4 GEX activation — from display shelf to decision inputs

GEX is "just sitting there" because the *gates* are young, not because the wiring is missing
(F8: the lattice exists). The activation plan is therefore: **collapse the gates, then flip
the switches that already exist.**

- **Backtest S-GEXR now** on reconstructed 2012→ per-name GEX (chains+OI+greeks). If gamma
  regime → forward-vol validates: `validate_gex` writes `scored:true`, and the already-wired
  consumers activate (stock_score tilt, evidence-stack vote weight, sizing-context surfaces) —
  as *vol/condition* context, per doctrine §2.5 (single-name dealer-sign fragility: never a
  directional pick by itself).
- **Index GEX history (new):** SPX/SPY/QQQ/IWM dealer-gamma reconstruction 2012→ upgrades
  `market_gamma` from an 18-row CBOE-delayed estimate to a 14-year validated regime series —
  candidate context leg for Risk Radar / market_state (display → gauntlet → maybe scored;
  the radar's modulator pattern is the precedent).
- **Vanna/charm exposure (new, from 2nd/3rd-order Greeks):** dealer vanna/charm maps enable
  OPEX-week charm-decay and vol-crush-flow context — ship as gex.html display layers +
  research features only; the literature here is regime-conditional and heavily decayed;
  no gate registered until a concrete claim is written.
- **Wall quality upgrade:** walls recomputed from full chains at better universe coverage fix
  the F11 sector-coverage holes (Health 24%, Comm 13%, Materials 8%, RE 0%) — which currently
  force sector-aggregate suppression. Full-universe EOD chains lift that constraint.
- **Squeeze/COILED intersections (S-COIL2, S-SQZ):** historical episode studies de-risk the
  designs now; fire-conditioned verdicts still accrue.

### 5.5 The flow desk ("our own Unusual Whales") — product design under licensing reality

**Licensing first (hard constraint):** OPRA non-professional real-time is ~$1.25/mo
pass-through — internal use is trivial. But **redistribution of ThetaData data is prohibited
without a commercial agreement**; an OPRA redistributor license is ~$1,500/mo (~$650 query-
only), and per-subscriber fees apply. Derived/aggregated display (heatmaps, scores) is a gray
zone the vendor terms do not clarify. **Ruling: the flow desk ships operator-internal only.
Nothing flow-derived appears on any customer-facing SaaS surface until ThetaData confirms
derived-data display rights in writing (STOP D5).** This also keeps us out of the non-display
"systems" fee category debate while everything is display/research.

**Build-vs-buy sanity check:** Unusual Whales (~$48–120/mo) is a human-eyeballs feed with
unauditable "unusualness" heuristics and no bulk history for gauntlets. We are buying the tape
to feed *engines and backtests* — UW cannot do that job at any price. Verdict: build thin, on
our aggregation stack; do not rebuild their UI ambitions.

**Surfaces (EOD/batch first, all display-tier):**
1. **Group Flow Heatmap** — net signed premium, flow breadth, ΔOI tone, DTE-quality, crowding
   flag per sector/theme/subsector; sits beside the existing rotation surfaces (the options
   twin of group_flow's price fingerprint). Feeds Oracle's pages once O-OPT passes anything.
2. **Unusual-activity feed** — event = {ticker, group, direction-soft, premium z vs own
   baseline, DTE bucket, breadth context, OI-confirmed-next-day flag}. Quality-filtered by
   construction (repeated / premium-heavy / 8–90DTE / not-yet-extended); ranked by a
   *labeled* heuristic, never called a signal. Lands in alerts.html triage as a new stream
   (display floor).
3. **Divergence monitor** — flow-vs-price disagreement per group (the N4 edge, surfaced).
4. **Crowding/exhaustion board** — the exit-side view (§5.6).
5. **Terminal (later):** read-only mirror over the intel/v1 bridge once the R2-leg unfreeze
   (Neural Web D7) lands; the desk itself lives on the dashboard first.

**Cadence:** nightly EOD build in daily.yml (off the render path per A7); optional 15-min
RTH batch on the Mac later — matching LIVE_DATA Tier-E and fastpath precedents. **No
websocket daemon** until a graded reflex earns the push tier.

### 5.6 The rest of the ecosystem (completeness sweep)

- **Exit overlay (new claim family, high priority):** group-level exhaustion score for groups
  we're currently long (via standout/board state): short-dated OTM call-share spike + IV-rank
  blowout + weak price response + ETF flow rolloff. Pre-register vs the SELL base-rate
  machinery. This is the options program's contribution to the missing exit rule.
- **vol_regime:** real IV surfaces (12y) add candidate legs (per-name VRP breadth, index
  term-structure). vol_regime is already validated — new legs enter as CONTEXT_LEGS via its
  own promotion discipline (VVIX precedent). Low urgency, real depth.
- **Event calendar / earnings positioning:** front-vs-back IV spread + expected-move from EOD
  chains → pre-earnings positioning chips on stock cards + anticipation-engine context.
  Display; cheap; no gate needed until someone writes a claim.
- **Mastermind:** `_flow_row` lens now gets signed (soft-labeled) flow; the Brain reads it as
  context like every other lens — clamps unchanged.
- **BTC/bonds/intl:** out of scope (no entitlement / no OPRA analog). The BTC options story
  (Deribit) is a different program if ever.

---

## §6 What NOT to build (pre-registered rejections)

1. **No flow-direction claims from prints alone.** Even with perfect NBBO signing, an
   ask-side call buy may be a hedge, a spread leg, or a close. Direction stays `~`-soft until
   the re-calibrated signing gate passes AND breadth/persistence/OI-confirmation context
   wraps every directional read. Single-print sweep-following is banned as signal.
2. **No hand-weighted "Options-Adjusted Rotation Score."** The ChatGPT 0.55/0.30/0.10/0.05
   composite is exactly the invented-weights laundering machine the composite law exists to
   stop. Options evidence enters as *separate, individually-gated legs*; any fusion must beat
   the equal-weight z-mean baseline out-of-sample.
3. **No 0DTE desk.** 0DTE features are separated and down-weighted by construction
   (dte-bucket features exist to *exclude* them from rotation claims), not traded.
4. **No raw-tick warehouse.** Aggregate-then-discard for the broad universe; raw retention
   only for ETFs + episode windows + calibration slices (§7.2). The 3PB tape stays at the
   vendor.
5. **No ClickHouse/Redis/NATS/Kafka.** Parquet + R2 + DuckDB/pandas on the existing planes
   until a measured bottleneck says otherwise. Boring wins (Neural Web rejection #1, same
   ruling).
6. **No streaming daemon pre-validation.** Sub-hour batch covers the swing horizon; the push
   tier is earned by a graded reflex, not assumed.
7. **No customer-facing flow surfaces pre-licensing-confirmation** (§5.5).
8. **No sub-30-date "backtests"** on young stores while the backfill runs — doctrine §2.3
   stands; the whole point of the purchase is to make that rule cheap to obey.

---

## §7 Data architecture (tiers, storage, sequencing)

### 7.1 Phase A — plumbing + the two calibrations (week 1)

- Theta Terminal (Java, local REST/WS) runs headless on the Mac Studio next to the massive
  collectors; `collectors/thetadata_*.py` wrap the local endpoints with the same
  graceful-degrade contract as every other collector. Entitlement probe doc appended here
  (the OPTIONS_FLOW_DATA.md pattern: measured facts, not vendor marketing).
- **Signing re-calibration (the F7 re-test):** rerun `scripts/calibrate_flow_signing.py` with
  ThetaData trade+NBBO as the source against the cached Databento truth slices (~$0). 
  Acceptance: per-trade quote-rule agreement in the literature band (≥0.75) AND minute/daily
  net-sign recovery ≥0.75 (vs 0.41 today). Pass → `signing_gate.json` flips
  `direction_reliable:true` **for tape-sourced features only**; bar-sourced stays soft.
- **IV cross-validation:** vendor IV vs W1.1's BS-inversion on the 2024-07→ overlap (per-day
  cross-sectional rank-corr, the A5 test with a real benchmark). Decides supersede-vs-keep.

### 7.2 Storage tiers (obeying A4/A8 + R2 rules)

| Tier | What | Universe / depth | Est. size | Plane |
|---|---|---|---|---|
| T1 | EOD chains + OI + IV + EOD Greeks | options_universe (≈400→800 names) + sector/index ETFs + SPX; **2012→** | ~30–80 GB | R2 (`data/thetadata_eod/`), manifest + audit tripwire |
| T2a | Daily **signed-flow features** (aggregate-then-discard from trade+NBBO+trade-greeks) | same universe, 2021→ first, extend to 2012 opportunistically | ~1–5 GB (features only) | git-budgeted per-name parquet if ≤~30 MB summaries; else R2 |
| T2b | Raw trades+NBBO retained | ETFs + episode windows (Oracle catalog ±15d) + calibration days | ~50–150 GB | R2 only |
| T3 | Live/15-min stream | deferred (§5.5) | — | — |

Order: T1 → gate re-runs (§4) → T2a 2021→ (the Oracle Tier-M era; June-cascade resolution) →
O-OPT studies → T2b as studies demand. The Mac chews T2a as a nightly batch job over ~2–4
weeks; nothing touches the 67-min render path.

### 7.3 Interaction with in-flight work

- **W1.1/W1.2 (IV backfill):** let it land — it becomes the acceptance benchmark's other leg
  and the fallback series; consumers swap to vendor IV after cross-validation. No wasted work
  (the consumers, quality flags, and rank plumbing are source-agnostic).
- **W1.3 (entry-quality harness):** unchanged; gains stamp columns (§5.2.1) via the same A9
  single-writer rule.
- **polygon_gex collector:** keeps running (it is the PIT-true forward layer and the
  cross-vendor sanity check); ThetaData supplies *history*, massive/polygon supplies
  *tomorrow's as-reported truth*. Divergence between them is itself an audit signal.
- **daily.yml placement:** nightly ThetaData EOD pull + feature build lands beside the
  existing flow step (A7: daily.yml only; render lanes never gain S3/vendor pulls).

---

## §8 Validation constitution for this data (binding)

Everything inherits OPTIONS_ALPHA doctrine §2 + Oracle O6. Additions specific to the tape:

1. **OI timing law:** vendor historical OI is as-of the reporting date (published next
   morning); every join uses `oi[t-1]` for day-t signals. Same-day OI in any feature = bug.
2. **Signing provenance:** every signed feature carries `signing_source: tape|bar` and the
   measured accuracy of its source. Mixed-source aggregates are forbidden.
3. **Reconstruction labeling:** historical GEX/walls computed from vendor chains are
   `reconstructed:true` and must replicate the live collector's assumptions; any live-vs-
   reconstructed divergence on the 2026-06-15→ overlap window is a blocking audit finding.
4. **Era discipline:** all 12-year cross-sectional claims report per-era results (2012–15 /
   2016–19 / 2020–22 / 2023→) + post-publication-decay commentary; a claim alive only
   pre-2016 is dead.
5. **FDR families:** O-OPT-* joins Oracle's registered-trial ledger; S-* extensions stay in
   the options-alpha family; standout Lane-A tests join the species/anticipation family as
   registered. Machine-proposed trials (future cortex) are their own family.
6. **Placebo law:** every episode-conditioned claim runs against random-onset pseudo-episodes;
   every fire-conditioned claim against matched non-fire name-days.
7. **The word "validated"** stays CI-enforced; new UI strings ship EN+ZH; no title-attr
   translations; direction tone stays `~` until §7.1 passes.

---

## §9 Expected value, calibrated (what "how much will it help" honestly means)

Literature anchors, with decay honesty (McLean-Pontiff: ~50% average post-publication decay;
options-signal papers are 2006–2016 vintage, single-name cross-section, institutional-latency
era): Cremers-Weinbaum IV-spread ~45–90bps/wk in-sample pre-2010, likely ≤half now;
Xing-Zhang-Zhao skew ~10%/yr long-short pre-decay; Johnson-So O/S ~1–2%/mo in-sample;
Pan-Poteshman open-buy P/C (needs open/close flags we DON'T get — aggressor+ΔOI approximates
it, imperfectly); Garleanu-Pedersen-Poteshman demand-pressure (mechanism support for group
aggregation); dealer-gamma literature (vol-conditioning, weakly directional). Our own priors:
every unconditional ranking signal tested here has been dead-or-marginal; state/episode
conditioning is where edges survived.

| Use | P(validates) | Value if it does | Verdict |
|---|---|---|---|
| Gate acceleration (§4) | ~1.0 (it's data) | Decisions this quarter instead of next year; kills or promotes 9 claims | **The reason to buy. Certain.** |
| O-OPT-2 confirmation quality | 0.5–0.65 | Early-tier false-alarm cut → the front-run tier becomes actionable | **Highest-value uncertain bet** |
| Exit/crowding overlay (§5.6) | ~0.5 | First validated exit evidence; defensive identity match | **Underrated; prioritize** |
| O-OPT-1 stealth lead | 0.3–0.4 | 0–3 days/leg earlier + destination hints | Real but capped; days not weeks |
| S-CWIV/S-XZZ/S-DOI revival | 0.3–0.5 each | Cross-sectional context legs for standouts | Decay risk is the open question — that's WHY we test eras |
| S-GEXR + index-GEX regime | ~0.5 (as vol-conditioner) | Sizing/timing context, Risk-Radar leg | Literature-consistent; never directional alone |
| Standout fire-conditioned modifiers | 0.35–0.5, verdict Q4-26 | Score tilts on the money path | Patience — the ledger is the clock |
| Live streaming desk | 0.15–0.25 (alpha) | Freshness UX; reflex latency | Defer; batch covers the horizon |

**Prediction, in writing (falsifiable):** the SELL/exhaustion side and the confirmation-
quality side validate before any BUY-side flow signal does; single-name signed-flow direction
adds nothing after breadth/ΔOI/IV-rank are in the model. If the BUY-side stealth claim
validates anywhere, it validates on *subsector breadth in high-VIX regimes* first
(cohesion_chg precedent: stress-conditional).

**Cost side:** ThetaData Pro $160/mo + OPRA non-pro ~$1.25 + R2 ~$2–5/mo (≤300 GB) + Mac
batch cycles. One-off build: roughly 8–14 agent-sessions across the phases below — comparable
to a single mid-sized wave, amortized across four programs. (Standard at $80/mo lacks 2nd/3rd
Greeks + trade Greeks and halves history to 8y — the trade-greeks stream is what makes signed
delta-notional flow cheap to compute correctly; **Pro is the right tier** while the backfill
runs; downgrade later if streaming + greeks prove unused.)

---

## §10 Phased roadmap (amendments to existing programs — no new empire)

_Border law respected: options-alpha owns per-name options signals + the tape plumbing;
Oracle owns rotation joins; Neural Web owns bus/registry; species owns entry-species. Model
routing: Sonnet builds, Opus reviews stats-heavy designs, Fable adjudicates._

| Phase | What | Owner (program) | Depends on |
|---|---|---|---|
| **A — Plumb + calibrate** (wk 1) | Theta Terminal on Mac; collectors + probe doc; signing re-calibration; IV cross-validation | options-alpha (new W1.5) | subscription active |
| **B — T1 backfill + gate collapse** (wk 1–3) | EOD chains/OI/IV/greeks 2012→ to R2; re-run S-CWIV/S-XZZ/S-DOI/S-GEXR with era splits; verdicts printed either way | options-alpha (W2 amended) | A |
| **C — Signed-flow features** (wk 2–4) | T2a aggregate-then-discard build 2021→; per-name + group daily features; signing-provenance law | options-alpha (W2 amended) | A pass |
| **D — Flow desk v1 + stamps** (wk 3–5) | Group heatmap + unusual feed + divergence board (internal, display); standout chips; ledger stamp columns | options-alpha (W3 amended) | C |
| **E — O-OPT Phase-0** (after Oracle P2) | Pre-register O-OPT-1..4; run on episode catalog; verdicts to Oracle's trial ledger | **Oracle** (P7 pulled forward) | B, C + episodes.parquet |
| **F — Exit overlay Phase-0** | Crowding/exhaustion claims vs SELL base-rate machinery | options-alpha (new) | C |
| **G — Neural Web registration** | synapse.yml entries, world_state block, kernel enrollment | **Neural Web** (when W0 lands) | D |
| **H — Score wiring** | Passed gates only → manifest-named seams; species registration for entry claims | options-alpha W5 (unchanged) | verdicts |
| **I — Live tier** | 15-min RTH batch; reflex candidate; streaming only on earned need | options-alpha W4-live (gated) | D + a validated use-case |

---

## §11 STOP list — operator decisions

- **D1 — Tier:** Options Pro ($160/mo) vs Standard ($80/mo). *(Recommended: Pro — trade
  Greeks + 12y depth are load-bearing for §5/§4; revisit after backfill completes.)*
- **D2 — Backfill depth:** 2012→ everywhere vs 2021→ first. *(Recommended: T1 chains/OI 2012→
  [cheap, small]; T2a flow features 2021→ first, extend later.)*
- **D3 — W1.1 disposition:** benchmark-then-supersede vendor IV vs keep dual series.
  *(Recommended: benchmark-then-supersede; keep BS-inversion code as audit tool.)*
- **D4 — Flow desk placement:** dashboard page first, Terminal mirror later. *(Recommended:
  yes — Terminal waits on the intel/v1 unfreeze anyway.)*
- **D5 — SaaS exposure:** request written derived-data display terms from ThetaData now, or
  defer until the desk proves internally valuable. *(Recommended: ask now — it's a free email
  and the answer shapes W8b-era product plans; ship nothing customer-facing meanwhile.)*
- **D6 — O-OPT sequencing:** hold O-OPT until Oracle P2 lands (episodes exist) vs run a
  provisional sector-ETF-only version sooner. *(Recommended: hold — pre-registration needs
  the frozen episode schema; a provisional run burns the pre-registration.)*
- **D7 — Exit-overlay priority:** run Phase F before or after the O-OPT flagship.
  *(Recommended: parallel — different owners, different data cuts, shared features.)*

## §12 Status log

| Date | Event |
|---|---|
| 2026-07-04 | Brainstorm/assessment authored (Fable): codebase-grounded read of both external docs; constraint-reversal analysis vs OPTIONS_ALPHA F5–F7; unlock table; per-engine designs; licensing research (Pro $160/mo confirmed; redistribution prohibited w/o commercial agreement; derived-display = gray zone); phased roadmap as amendments to options-alpha / Oracle P7 / Neural Web. Fire-ledger depth verified (2026-06-15→, 950 rows): fire-conditioned claims stay accrual-bound; episode/cross-sectional claims unlock immediately. At operator STOP. |

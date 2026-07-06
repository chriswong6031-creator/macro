# LIVE FLOW → PRODUCTION — reassessment + phased build-out roadmap by Fable

_Authored by Fable, 2026-07-04 (evening). Sequel to research/LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md
(#1263). Grounded in an 8-verifier evidence sweep + a 3-critic adversarial review run tonight
(backfill state, signing gate, UW-feature inventory, fear/greed leg census, program deps,
pipeline liveness, T1 schema, dark-pool feasibility; then constitution/feasibility/completeness
critique — all three returned SHIP_WITH_FIXES; every blocker is folded in below). This doc
(a) corrects the morning assessment where evidence contradicts it, (b) records the operator's
licensing reversal, (c) is the execution plan of record for the four operator-approved tracks.
Model routing: Fable orchestrates/adjudicates only; Opus = stats/reviews; Sonnet = builds;
Haiku = mechanical._

---

## §0 In plain English

Everything is further along than this morning's assessment believed. The trade-direction
calibration we listed as "the gate everything waits on" passed and was ratified this afternoon.
The Neural Web bus we said was "waiting to land" landed — through W8a. The options backfill is
running ahead of schedule, and its default universe is already the full ~360-name gate-wide set
(no extension pass needed). The operator bought display/redistribution rights, so the
"internal-only" wall around a public flow product is down.

One honest framing note: the ask said "real-time." We are deliberately shipping nightly-EOD
first and letting a 15-minute tier be EARNED by demonstrated use (P6) — at a 1–20d swing
horizon, liveness is a freshness/UX feature, not an alpha feature, and every constitution we
run under says validate before you stream.

Two genuinely new constraints surfaced tonight: vendor Greeks/IV history starts in 2017 (not
2012), so IV-based backtests get ~9 years and their era partitions must be registered BEFORE
the runs; and the per-trade tape endpoint has no bulk mode, so signed-flow history gets a
measured throughput probe before we commit to its shape.

The plan: ship the licensing-free wins first (fear/greed composite, dark-pool board, options
screener — from data we already hold), collapse the pre-registered gates as backfill lands,
build signed-flow features forward-daily plus bounded history, then open the public flow desk.
Nothing ranks or scores anything until its gate passes.

---

## §1 Reassessment of the 2026-07-04 morning assessment (evidence-backed)

| # | Morning claim | Verdict | Evidence / correction |
|---|---|---|---|
| 1 | Signing re-calibration is the pending gate | **REFUTED** | Ratified 17:04 PT, #1292: `signing_gate.json → thetadata_tape.direction_reliable_tape=true`, agreement 0.8848, recovery 0.80, n=16,366 (THETADATA_PROBE.md §4.6). Root `direction_reliable:false` permanent (bar-sourced, 0.41). Honesty note: the ratified calibration is ONE 20-min window, ONE root (SPY), 15 contracts. T2a is **build-unblocked now**; UI tone and any production gate consuming signed direction harden only on the **multi-session extension** — ≥5 further sessions spanning a high-VIX and a calm day AND multiple roots, each ≥0.75/≥0.75; any failure SUSPENDS. |
| 2 | Neural Web at operator STOP; nerves register "when W0 lands" | **REFUTED** | W0–W8a COMPLETE 2026-07-04; `config/synapse.yml` live (2,801 lines, 101 artifacts) with CI registry gates. Nerve registration is unblocked today. Only W8b remains. |
| 3 | Exit/crowding overlay waits on Phase C (tape) | **REFUTED** | T1 alone computes all unsigned exhaustion legs: DTE-bucketed C/P volume share, OTM call-share (EOD⋈greeks for underlying_price), IV-rank (2018→), P/C OI (2012→), gross premium, implied move, max pain, and full GEX reconstruction (live merge validated: SPY 2026-01-02, 10,130 rows, $5.83B). Only NET/signed premium needs tape. |
| 4 | Backfill mid-QQQ-2020; universe ~127 roots | REVISED ×2 | Ahead: SPY 2012–2026 done; QQQ through 2021+, pulling 2022+. And the chained bare pass resolves the FULL default universe: `gex_symbols()` returns **360** (config `max_underlyings=360`; baskets_universe()=680 capped) — the "127 roots" figure was a misread of membership.json. **No extension pass is needed.** Measured ETF rate = 210s/root-year mean (346s for greeks-bearing SPY years); single-name rate UNMEASURED → universe-pass ETA ~Jul-8–12, conditional on a light-name rate observation. Store now 2.8GB (greeks 2.1G); 360-root estimate ~60–120GB — R2-plane, disk fine (451GB free). |
| 5 | Dark pool "not buildable" | REVISED | True only for real-time prints. Ladder: **T1e** daily per-ticker FINRA-facility (off-exchange) reported volume + short ratio ALREADY COLLECTED (`data/finra_short_volume/panel.parquet` — CNMSshvol, T+0 ~6pm ET; the same file Quiver resells as DPI). Two catches folded in: panel is only 27 dates deep (< 30-date floor) — free history to Aug-2018 must be backfilled; and "dark-pool share" requires joining FINRA-facility volume ÷ consolidated volume from massive day-aggs. **T2e** weekly per-ATS venue breakdown = free keyless FINRA OTC Transparency API, not yet built, 2–4wk lag. **T3e** per-trade EOD prints = massive trades_v1 upgrade (~$79–199/mo, currently 403). **T4e** live prints = paid SIP/live tape only. |
| 6 | Fear/greed composite feasible | CONFIRMED+ | **14 legs: 10 HAVE + 4 DERIVABLE.** HAVE: putcall (young), 52w nh/nl, McClellan/adv-dec, HY OAS + HYG/IEF, VIX 1990→, VIX term (VIX3M + vix_curve), insider (SEC + Quiver), CBOE SKEW (9,175 rows), options premium magnitude, NAAIM/AAII (AAII young). DERIVABLE (one-liners): SPX-vs-125dma via SPY, SPY−TLT safe-haven, per-stock 52w position, m1/m2 expiry bias. Render slot: `macro.html` `#sentiment-regime` + `macro_signals.html` drill-down. This composite IS the operator's "Market Monitor" ask — every named leg (junk bond demand, safe haven, 52wk, insider, VIX/VIX-trend, expiry bias, OTM skew, P/C, momentum, breadth, premium legs) maps to the census 1:1; premium ratio/trend + volume divergence join post-P2 (magnitude now, signed later). |
| 7 | UW inventory ~60% | REVISED (details) | 13F current through Q2-2026 early filers; prediction-markets store = probabilities ONLY (no volume → "unusual PM flow" needs a collector extension); no US options screener (CN/HK embedded panel pattern exists to clone); flow pipeline live (353 names through 2026-07-02); `market_gamma` block live but built from an 18-row CBOE-delayed estimate. |
| 8 | W1.1 IV backfill "let it land" | REVISED | W1.1 still IN-FLIGHT (not merged; no `data/iv_history/`). Vendor IV (greeks store) covers 2017→ — richer than W1.1's 2024-07→ target. D3 benchmark-then-supersede stands; `opt_iv_rank_252` (null in ledger) feeds from vendor IV once the universe pass lands. |

**New load-bearing facts:**

- **F-A: Greeks/IV history starts 2017** (2012–2016 greeks rows=0 — vendor gap). S-CWIV/S-XZZ/**S-GEXR (greeks-dependent: needs gamma)** get 2017→ (~9y); IV-rank usable 2018→ (252d warm-up). S-DOI and P/C-OI keep 2012→.
- **F-B: The running backfill already covers the full ~360-root gate-wide universe** (see §1 row 4). Corollary: universe = polygon_gex parity, so the **F11 sector-coverage holes persist** (Health 24%, Comm 13%, Materials 8%, RE 0% → sector aggregates suppress <40%). Fixing F11 means growing `max_underlyings` beyond 360 — an OPEN decision deferred until gate results say per-name options context is worth buying more coverage for (default: keep 360).
- **F-C: `trade_quote` is per-contract streaming; no bulk/wildcard trade endpoint exists in v3** (collectors/thetadata.py:62-66, 847). ~57% of contract-rows are zero-volume (skippable). T2a design is probe-gated (R6).
  - **AMENDMENT — 2026-07-05: F-C is corrected by PR #1358 live evidence: bulk trade_quote EXISTS (wildcard expiration+strike, per-right; right=* → 400). T2a cost = 2 requests/root-day; P2.0's per-contract probe premise is moot; R6 priority ladder relaxes accordingly. — ruled by Fable (brainstorm session).**
- **F-D: Licensing reversal (operator, tonight):** $1,000 one-off on top of Pro $160/mo bought display + redistribution rights — operator attests "full display of data on our front-end website and use however we want." Brainstorm §5.5 internal-only ruling and §6 rejection #7 are LIFTED for vendor-data display/aggregation surfaces. **Scope discipline:** the written terms are not yet filed in-repo; P0.6 files them. Surfaces that FUSE vendor data with our engines' outputs (heuristic-ranked unusual feeds, oracle-annotated boards) get a one-time pre-publish check against the filed terms before going public; if the filing lags, those specific surfaces ship internal-first. Debrand law applies throughout (no vendor/competitor names on customer surfaces).

---

## §2 Rulings (Fable, this doc — binding until amended)

- **R1 — No universe extension pass.** The chained pass already covers ~360 roots. R1 re-scopes to: verify via `_manifest.json` that the universe pass completes; observe a single-name rate early and re-project the ETA.
- **R2 — Era partitions registered BEFORE gate runs.** No era-split was ever registered for S-CWIV/S-XZZ/S-GEXR in OPTIONS_ALPHA §4 (verified) — so this amendment REGISTERS a first partition, it does not revise one (not goalpost-moving). IV/greeks-dependent gates: 2017–19 / 2020–22 / 2023→. S-DOI (OI-only): 2012–15 / 2016–19 / 2020–22 / 2023→. Amendment PR merges before any harness runs. Opus drafts; Fable ratifies.
- **R3 — Exit-overlay prereg scope:** Phase-0 registers unsigned T1 legs — short-dated OTM call-share spike, IV-rank blowout × weak price response, P/C-OI collapse-into-strength, **and the ETF-flow rolloff leg (restored from brainstorm §5.6; theme_flow_rollup source, 1–5d lag labeled)** — vs the SELL base-rate machinery, 2018→. Signed legs enter by amendment after T2a exists.
- **R4 — Fear/greed is a DISPLAY product with a hard min-history gate:** equal-weight z-mean (composite law), 0–100 percentile dial. A leg enters the z-mean ONLY with ≥252 daily / ≥104 weekly / ≥40 lower-frequency observations for its z-window; younger legs render as raw context tiles, EXCLUDED from the composite (not flagged-but-included). At launch this EXCLUDES cboe putcall (21 rows; deepen from T1 P/C 2012→ later) and AAII (22 rows; accrues). Leg additions are PRs with stated rationale, never tuning. Any contrarian-timing claim is its own future prereg.
- **R5 — Dark-pool desk ships free tiers only** (T1e + T2e), with honest semantics: T1e tiles say "off-exchange (FINRA-facility) volume / short ratio," never "dark pool prints"; share-of-consolidated computed by joining massive day-aggs; 2018→ history backfilled before the page ships (30-date floor). T3e procurement DEFERRED until desk usage proves demand.
- **R6 — T2a design is probe-gated:** no T2a build until P2.0 measures per-contract-day pull cost on SPY + one light name. Priority ladder if tight: (1) forward-daily accrual for the live universe, (2) episode windows **2022→ (Tier-M options-era onset floor 2022-02-08 per O-OPT prereg R3 — there are zero pre-2022 subsector episodes)**, (3) ETF full history 2017→ (serves the Tier-S sector-level joins), (4) single-name history opportunistic.
- **R7 — O-OPT partial execution is legitimate:** the frozen prereg gates signed legs on the signing calibration (ratified) and everything on T1; unsigned legs (ΔOI build, IV lift, volume breadth) run as soon as the universe pass completes. No prereg edit needed.
- **R8 — No gate harness reads `data/thetadata_eod/` mid-backfill.** P1.1 starts only after `_manifest.json` marks the universe pass complete — reading a store mid-write risks partial-universe cross-sections.

---

## §3 The plan: tracks and phases

_Owners are model tiers (§4). House CI on every PR: EN+ZH strings, no title-attr translations,
"validated" word-gate, R2 plane for heavy stores, A9 single-writer for ledger columns,
nav via shared `_navlinks` + `check_nav_gap`/`check_nav_mega`. Gates between phases inline._

### P0 — This weekend: ops + paper (mostly in motion)

| Item | What | Owner | Gate/ETA |
|---|---|---|---|
| P0.1 | Backfill completes (two chained passes; no third). **Reboot runbook:** the job is a manually-launched process — if the Mac reboots, RESUME by re-running the same chained command from `/Users/chriswong/theta-ops-wt` (state file `_backfill_state.json` makes it idempotent); add a launchd keepalive wrapper so resumption is automatic | ops + Sonnet (launchd) | ETF pass ~Jul-5; universe ~Jul-8–12 (single-name rate TBD) |
| P0.2 | R2 publish of `data/thetadata_eod/` (manifest + audit tripwire per A4/A8) | Sonnet | after ETF pass |
| P0.3 | Docs PR: this roadmap + brainstorm §13 amendment (F-D licensing, D-list resolutions, F-A/F-B/F-C, corrections §1) | Fable (this PR) | Jul-4 |
| P0.4 | Multi-session signing extension: ≥5 sessions spanning high-VIX + calm days AND **multiple roots** (initial ratification was single-window single-name); append per-session records; SUSPEND rule live | Sonnet (small) + cron | opportunistic; unlocks UI tone unsoften |
| P0.5 | Era-partition registration prereg (R2) | Opus draft → Fable ratify | BEFORE P1.1 |
| P0.6 | File the ThetaData license terms (agreement text/email) under `research/licenses/`; fused-surface pre-publish check keys off it (F-D) | operator + Haiku | before P3.2 goes public |
| P0.7 | Register every new nightly producer in the data-health breaker: `run_status.json` entries + audit tripwires (theta EOD pull, T2a builder, finra_ats, PM collector) — silent failure must surface, not ship stale pages | Sonnet | lands with each producer |

### P1 — Week 1 (Jul 6–12): T1-derived products + gate collapse — no tape needed

| Item | What | Owner | Notes |
|---|---|---|---|
| P1.1 | **Gate re-runs** (AFTER manifest-complete, R8): S-DOI (2012→) → S-CWIV/S-XZZ (2017→, R2 eras) → S-GEXR via reconstructed per-name GEX 2017→ (`reconstructed:true`; replicate `gex_model` dealer-sign assumptions; blocking audit = live-vs-reconstructed divergence on the 2026-06-15→ polygon_gex overlap) | Opus (stats) | verdicts print either way; FDR families as registered |
| P1.1b | **Index-GEX 14y reconstruction → `market_gamma` upgrade** (brainstorm §5.4 item restored): SPX/SPY/QQQ/IWM dealer-gamma 2017→ replaces the 18-row CBOE-delayed estimate as the regime series; display + candidate Risk-Radar vol-context leg (own gauntlet before any modulator role) | Opus (stats) + Sonnet (wiring) | also what the P4.1 `gex_state` nerve feeds — the nerve must not ship reading the old estimate |
| P1.2 | **Fear/Greed composite v1** (`engine/fear_greed.py`): launch legs = the census legs passing R4's min-history gate (expected ~9: SPX-vs-125dma, 52w hi/lo, McClellan, HY OAS, SPY−TLT, VIX+trend, VIX term, SKEW, NAAIM; insider if its cadence clears ≥40; putcall/AAII render raw, excluded); equal-weight z-mean → 0–100 dial; macro.html card + macro_signals drill-down; EN+ZH | Sonnet build, Opus review | premium legs join post-P2 |
| P1.3 | **Exit/crowding overlay Phase-0 PREREG** (R3 legs incl. ETF-flow rolloff) vs SELL base-rate machinery, 2018→ | Opus draft → Fable ratify → Opus run (P4.4) | prereg BEFORE any joined look |
| P1.4 | **US Options Screener v1**: per-name IV-rank (2018→ true), implied move, P/C-OI, volume, gross premium, max pain, GEX tier; clone CN embedded-panel pattern; display-only; nav: US/Markets menu group | Sonnet | public (vendor-data display, F-D cleared) |
| P1.5 | **Dark Pool Desk v1 (EOD)** per R5: CNMSshvol 2018→ history backfill; off-exchange share join vs day-aggs; NEW `finra_ats_transparency` collector (weekly per-venue, labeled 2–4wk lag); page + nav (Markets group) | Sonnet | honest labels: "off-exchange volume," never "live," never "prints" |
| P1.6 | Prediction-markets extension: capture Polymarket volume/liquidity (store has probabilities only); optional Kalshi adapter; volume-delta z events → alerts stream | Sonnet (small) | enables "unusual PM flow" ask |
| P1.7 | **ETF in/out flows tile** (ask item, was missing): derive daily creation/redemption proxy from shares-outstanding × price (day-agg stores); sector-ETF volumes fold into the P3.1 heatmap columns | Sonnet (small) | display; labeled proxy |
| — | **Institutional buy/sell volumes** (ask item): served by existing quiver 13F stores (Q2-2026 early filers already in) — quarterly-lag reality, no build; surfaces via existing smart-money tracker | mapped, no work | — |

### P2 — Weeks 2–3: signed-flow features (tape)

| Item | What | Owner | Notes |
|---|---|---|---|
| P2.0 | **Throughput probe** (R6): trade_quote cost/contract-day on SPY + one light name → decide T2a shape vs the priority ladder | Sonnet | BLOCKS P2.1 design |
| P2.1 | **T2a builder**: aggregate-then-discard daily signed features (net signed premium, signed P/C, flow breadth, DTE-quality, crowding flag), `signing_source:tape` provenance, `oi[t-1]` law; forward-daily first, then episode windows 2022→, then ETF history 2017→ | Sonnet build, Opus PIT review | raw retention only ETFs + episode windows (T2b) |
| P2.2 | Ledger stamp extension (A9): `opt_net_signed_prem_5d_z`, `opt_flow_breadth_group`, `opt_dte_quality`, `opt_crowding_flag`; feed `opt_iv_rank_252` from vendor IV | Sonnet | nullable; no grading-logic changes |
| P2.3 | IV disposition (D3): benchmark W1.1 (if merged) vs vendor IV overlap; supersede for depth; keep BS-inversion as audit tool | Sonnet | unblocks screener IV-rank breadth |

### P3 — Weeks 3–4: the public Flow Desk

| Item | What | Owner | Notes |
|---|---|---|---|
| P3.1 | **Group Flow Heatmap + Market Tide**: sector/theme/subsector net signed premium (gross-premium fallback where unsigned), flow breadth, ΔOI tone, crowding chips, sector-ETF volume column; **"Top Net Impact" board = largest net-premium movers off T2a** (ask item mapped); public page + macro card; nav: Options/Flow entry beside gex.html | Sonnet | tone `~`-soft until P0.4 confirms |
| P3.2 | **Unusual-activity feed**: labeled heuristic event stream (premium-z vs own baseline, 8–90DTE filter, repeated-hit + OI-confirmed-next-day flags) → alerts.html triage, display floor | Sonnet | FUSED surface → P0.6 pre-publish check |
| P3.3 | Divergence monitor (flow-vs-price per group) + crowding/exhaustion board (exit-side view) | Sonnet | reads P1.3/P2.1 features |
| P3.4 | i18n sweep + nav wiring + CI guards (`check_nav_gap`/`check_nav_mega`) for ALL new public surfaces | Haiku | zh token flip; no title-attrs |
| P3.5 | **Vanna/charm dealer-exposure display layers on gex.html** (brainstorm §5.4 restored; 2nd/3rd-order greeks are in the store) — display/research only, no gate until a claim is written | Sonnet | OPEX-week charm-decay context |
| P3.6 | **Kill-switch:** config feature-flag per public surface (removes from nav + noindex + banner); rollback = the standard site/** push path | Sonnet (small) | first PUBLIC flow surfaces — must be able to retract same-day |

### P4 — Weeks 3–5 (parallel with P3): intelligence integration

| Item | What | Owner | Notes |
|---|---|---|---|
| P4.1 | **Neural Web nerve registrations** (unblocked NOW): `options_flow`, `gex_state` (fed by P1.1b's upgraded series, not the old 18-row estimate), `iv_surface`, `options_events` in `config/synapse.yml` + world_state options block + kernel enrollment (near-prior, quarterly FDR) | Sonnet | CI registry gates enforce |
| P4.2 | **O-OPT execution** (R7): unsigned legs after manifest-complete; signed legs after P2.1 covers episode windows 2022→; verdicts → Oracle trial ledger (~103 registered FDR trials, frozen kill criteria) | Opus (stats) | episodes_s = validation tier; episodes_m watermarked |
| P4.3 | **EI Lane-A cross-sectional studies**: options features vs forward returns on the PRE-GATE standout pool; registered species/anticipation FDR family; feeds EI P2 promotions and later P4 NW fusion | Opus | Lane B fire-conditioned stays on the ledger clock (~Q4-26) |
| P4.4 | Exit-overlay Phase-0 RUN (after P1.3 ratified + manifest-complete) | Opus | prediction on record: SELL-side validates first |

### P5 — Verdict-gated wiring (Q3→Q4 2026)

Passed gates ONLY → manifest-named seams: stock_score tilts, evidence-stack vote weights,
Oracle confirmation-tier input (never a hard gate — China falsification law), NW tier
promotions via Article-3 earn-in (Wilson-gated). Fire-conditioned buckets mature ~Q4-26.
Squeeze/COILED intersection studies (brainstorm §5.4 item 5) EXPLICITLY DEFERRED to the
species program's clock — fire-conditioned by nature.

### P6 — Live tier (earn-in, unchanged)

15-min RTH batch IF desk usage justifies; ONE reflex candidate (group flow burst →
alert_triage) earns push tier by graded firing record; streaming only on earned need.
**Terminal (app.mastermind-x.com) exposure: explicitly DEFERRED** per brainstorm D4 —
dashboard first; Terminal mirrors later via the intel/v1 bridge.

---

## §4 Model routing + token discipline

| Tier | Does | This plan |
|---|---|---|
| **Haiku** | mechanical: docs, i18n, nav sweeps | P0.6, P3.4 |
| **Sonnet** | all builds: collectors, features, pages, probes, ops | P0.1/0.2/0.4/0.7, P1.2/1.4/1.5/1.6/1.7, P2.0–2.3, P3.1–3.3/3.5/3.6, P4.1 |
| **Opus** | stats harnesses, prereg drafts, PIT audits, review of stats-heavy PRs | P0.5, P1.1/1.1b, P1.3, P2.1-review, P4.2–4.4 |
| **Fable** | adjudication only: prereg ratification, gate verdicts, tier promotions | R1–R8, P0.5/P1.3 ratify, P5 |

Dispatch: one wave = one isolated worktree off fresh origin/main, merged same-day (squash).
Builders symlink the main checkout's `data/` READ-ONLY (worktrees don't carry gitignored
stores). Stats/prereg PRs merge only after review; score-adjacent only after Fable.

## §5 What NOT to build

Brainstorm §6 rejections stand EXCEPT #7 (lifted per F-D, with the fused-surface check). Plus:
9. No UW/competitor naming on public surfaces (debrand law).
10. No "live"/"prints" labeling on EOD/weekly dark-pool surfaces — lag labels mandatory.
11. No T2a full-history commitment before the P2.0 probe (R6).
12. No composite legs by hand-weighting; no young legs inside the z-mean (R4).
13. No gate harness reads a mid-backfill store (R8).

## §6 Status log

| Date | Event |
|---|---|
| 2026-07-04 | 8-verifier reassessment + 3-critic adversarial review (all SHIP_WITH_FIXES; 10 blockers folded). Rulings R1–R8. Plan-of-record adopted. Licensing reversal recorded (F-D). Backfill live (SPY done; QQQ→2022; universe pass = full ~360 roots, no extension needed). |

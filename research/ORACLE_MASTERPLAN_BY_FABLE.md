# ORACLE — Rotation Intelligence Web — Masterplan by Fable

**Program goal.** Build the dashboard's rotation brain: a system that (1) reconstructs the daily history of every sector / theme / subsector's relative motion, (2) learns from that history which groups move together or opposite and how rotations actually behave — how they start, spread, persist, and exhaust, (3) watches the live tape for the earliest footprints of the same patterns, (4) propagates detected rotations to every consumer (alerts, banner, Mastermind, stock boards), and (5) lets users replay the whole history on the page (the Time Machine). Named **Oracle**. This is the operator's stated moat product.

**Provenance.** Operator brain dump 2026-07-04 (v2, "follow the money") + Fable adjudication of the operator's pushback against the prior Opus audit + a 5-agent data census (workflow `wf_a2fc1d99-3d1`, 2026-07-04, all claims file-evidenced). Supersedes the *detection-layer* sections of [SECTOR_ROTATION_ALERTS_PROBLEM_AUDIT_FOR_FABLE.md](SECTOR_ROTATION_ALERTS_PROBLEM_AUDIT_FOR_FABLE.md); that doc's L2/L3 propagation rails (alert taxonomy, banner contract, Mastermind directive, standout-board wiring) carry forward unchanged into O4.

---

## 0. In plain English

Rotations — money leaving one part of the market and entering another — are visible in the tape as coordinated changes in relative strength across groups of related industries. Today the dashboard can *display* this (subsector_rotation.html) but cannot *remember* it, *learn from* it, or *recognize a forming one early*. Oracle fixes all three: it builds the historical record, mines it for repeatable structure, and runs a live detector trained on that record. Selling out of a rolling-over leader is the part the evidence already supports strongly; buying the incoming group early is the part Oracle must *prove* on history before it's allowed to drive money — and the system is built so that proof (or its absence) is printed on the page, not assumed.

## 1. Adjudication carried into the design (what changed, what binds)

1. **Scope correction (retraction honored).** `DEFENSIVE_ROTATION.md` falsified *"defensive rotation predicts a vol shock within days"* — a different outcome variable than *"a detected rotation persists."* It no longer blocks this program. What it contributes instead: the strongest confound-control methodology in the repo (VIX-stratification, rates-control, trend-regime cuts, pre-registered gates) — the Phase-3 gauntlet reuses it wholesale. Its 80% false-alarm result stands as a warning about naive two-sided co-occurrence triggers → detector needs hysteresis + confirmation tiers.
2. **The nulls Oracle must beat (exact, from the census):**

   | Null | Number | Source |
   |---|---|---|
   | Sector relative momentum, clean 11-ETF universe, 27.6y | rank-IC **+0.0078** @1m (t=0.36); **−0.0051** @3m | `data/strategies/thematic_rotation_phase0.json` |
   | Best sector-momentum strategy vs EW buy-hold | CAGR 8.48% vs 8.87% — no lift (dd −0.41 vs −0.49) | same |
   | Plain stock momentum, PIT-debiased | IC **0.0008** (dead); residual-mom 0.0124, NO-GO standalone | `research/RESIDUAL_ALPHA_MOMENTUM.md` |
   | group_flow fingerprint legs (accel, broadening, persistence, flow) | **noise** — BH-FDR reject all; verdict `display_only`, forecast weights 0 | `data/group_flow/validation_meta.json` |

3. **The two validated footholds (design gifts):**
   - **`cohesion_chg`** — the change in within-group pairwise correlation — is the *one* group_flow leg that survives BH-FDR: deconfounded IC ≈ **+0.08–0.10 @20d**, and it is **stress-conditional** (high-VIX IC +0.236 vs calm +0.099 insignificant), sector-panel-only, dies on hindsight baskets. Consequence: Oracle's confirmation leg weights cohesion-*change* above raw acceleration, and the persistence model is regime-conditional *by evidence*, not by taste.
   - **State-conditional asymmetry is real where ranking is dead:** `sector_signals` validated base rates — BUY **+1.10%**/56% (n=199), **SELL −1.24%/40%** (n=169), 63d excess, 1998→2026 PIT. The repo's own numbers say: *episode/state framing carries edge; cross-sectional ranking doesn't.* Oracle is an episode/state engine. The SELL asymmetry being the largest again makes **exit the loudest output**.
4. **What failed before ≠ what Oracle tests, stated precisely.** group_flow Phase-0 tested *daily cross-sectional rank-IC of fingerprint legs on 20/60d forward RS*. Oracle tests *conditional persistence of detected episodes* (onset-gated, two-sided, breadth/cohesion-confirmed states with hysteresis). Different quantity — but the prior is informative: expect modest, regime-conditional edges at best; the system must be valuable as a **risk/exposure router even under a null persistence result** (it is: exit authority + regime awareness + the Time Machine product).
5. **"Follow the money" honesty.** Price velocity is flow-*inference*. True flow observation layers fuse in with lag stamps as they mature: SSGA sector flows (~80 obs ≈ Sep 2026), holdings conviction (1–5d lag), options positioning (Phase 7). Tooltips say "price-implied rotation," not "institutional flow," until a flow layer is validated.

## 2. Data reality (census 2026-07-04 — determines everything)

| Store | Span | Contents | Caveat |
|---|---|---|---|
| `data/yahoo/` sector ETFs (XLK…) | **1998-12-22 →** | div-adjusted close + volume | survivorship-clean (real ETFs) |
| `data/breadth/sp1500_pit_membership.parquet` | **1996 →** | 3,286 PIT intervals, 2,589 tickers, sp500/400/600 | the PIT spine; sector labels applied backward are mildly biased |
| `data/massive_stock_day/` | **2021-07-06 →** | 20,476 tickers, full OHLCV+transactions | rolling ~5y; whole-market incl. the 941 Finviz members |
| Finviz tree (40 themes / 268 subsectors / 941 members) | **current-only** | `themes_tree.json` has ONE commit ever | **membership survivorship-biased for any backtest; unarchived days are lost forever** |
| `data/subsector_rotation/snapshots.jsonl` | 2026-06-28 → (5 days) | 268 subsector-day metric rows/day | the accruing PIT layer — keep it |
| Baskets (46: 35 thematic + 11 EW-sector, 997 members) | levels 2023-05-30 → | 95% of members backdated 2023-05-09 | pre-2026-07-02 levels **declared hindsight**; PIT freeze (`basket_freeze`) is 2 days old |
| `data/stocks/` deep names | 1962/1980s → | 224 tickers OHLC+volume | explicit S&P **survivors** — pattern color only, never validation |
| Options (later quest) | OPRA day-aggs mid-2024 →; per-strike OI/IV/gamma 2026-06-15 → (355 names); skew 06-21 → | | display/research-only today |

**The three-tier substrate this forces:**
- **Tier S — the Spine (1998→, ~28y, survivorship-clean).** 11 sector ETFs + PIT-SP1500 GICS-sector member panels (the "clean unbiased sector panel" group_flow Phase-0 already builds). Deep episode learning across the 2000–02, 2008, 2011, 2015–16, 2018, 2020, 2022 cycles lives HERE. All *validated* claims are earned here.
- **Tier M — the Microscope (2021-07→, ~5y, survivorship-flagged).** 268 subsectors + 40 themes reconstructed as OUR equal-weight indices from massive-store member prices using the current tree (bias declared on-page), + the 35 thematic baskets (declared-hindsight levels). Fine-grained detection calibration + the Time Machine's showcase era (2021 top → 2022 bear → 2023–24 AI bull → 2025–26 semis→healthcare). Claims here ship **display-only with the survivorship watermark** until Tier-L accrual matures them.
- **Tier L — the Ledger (2026-06→, PIT-true).** snapshots.jsonl + basket freeze + tree archival (P1 adds it) + options stores. The forward-truth layer that slowly converts Tier-M patterns into validated ones. The forward ledger is NOT the primary validation (operator's preference honored — backtests are) — it is the free, ongoing audit.

**Cross-granularity confirmation principle:** learn *what rotations are* on Tier S (deep, clean, coarse); *detect finely* on Tier M/L (shallow, biased, sharp); a rotation visible at BOTH granularities outranks either alone. This dissolves the "only 5y of subsector history" problem instead of fighting it.

## 3. Architecture — the Oracle web (O0–O6)

Engine namespace: **`engine/oracle/`** package (`panel.py`, `graph.py`, `episodes.py`, `memory.py`, `live.py`). ⚠️ Naming: `oracle` already exists as a signal-contract key (`scripts/export_signal_contracts.py:147` → `engine.canon.confluence_signals`) and as the perfect-information-baseline term in `research/entry_timing/`. The package name avoids module collision; never touch the existing contract key; in Oracle docs call forward-peeking baselines "perfect-information benchmarks," not "oracle."

### O0 — The Rotation Panel (the substrate; one artifact, three consumers)
`scripts/build_oracle_panel.py` → `data/oracle/panel_{S,M}.parquet` (heavy → R2 per the data-plane rule). Per node per day: return, RS vs universe median, multi-horizon velocity (1W/1M/3M weekly-pace, mirroring `subsector_rotation.WEEKS`), acceleration, **cohesion + cohesion_chg** (the validated leg), breadth (%>50dma), persistence, turnover-z (massive volume — new, nothing uses volume today), regime tags (VIX pctile, rates 10d Δ, SPY vs 200d, liquidity state). PIT membership on Tier S; declared-bias membership on Tier M; coverage audit printed (941 Finviz members vs massive store). **The same parquet powers the backtests, the ML, and the Time Machine UI** — one build, three payoffs.

### O1 — The Graph (the "web": nodes, edges, learned truths)
Nodes = sectors/themes/subsectors (cross-granularity, linked by member overlap). Edges = rolling co-movement and inverse relationships + lead-lag estimates (does semis turn before hardware?), estimated on 60/120d windows so regime-dependence is *visible* rather than averaged away. Community detection (correlation clustering on RS-change) → data-derived complexes, reconciled each run against a small hand-named backbone (`ai_compute`, `defensives`, `rate_sensitives`, `commodity_cyclicals`…); disagreement between the two is **surfaced as signal, never silently resolved**. Output: the **edge-stability ledger** — every relationship with its stability score across regimes ("hardware↔software co-move: stable all regimes" vs "semis↔healthcare inverse: risk-off only"). This is the operator's "learned truths" — with confidence printed, auto-refreshed quarterly.

**The Flow-Routing Matrix (adjudication #2 — the operator's "where does the money go" made first-class).** For every complex A: conditional on outflow onset from A, the empirical distribution of where relative strength emerges over the next 1–15 sessions, per regime — plus the **lead-lag tensor** (node × node × lag). These are *structure-learning* objects: they ride the ENTIRE daily panel (hundreds of thousands of node-days), not the episode count — the data-rich half of Oracle, and the layer where the operator's "endless combinations" intuition is valid. The cost side is multiple testing, not sample size: ~35.8k subsector pairs yield ~1.8k spurious "relationships" at raw p<0.05, and cross-sectional correlation shrinks effective breadth — so an edge/route is promoted to a printed **truth** only after FDR against the registered trial ledger + stability across eras. The web learns on everything; it *asserts* only what survives.

### O2 — The Episode layer (rotation events, cataloged)
A hysteresis state machine per node and per complex — onset → acceleration → maturity → exhaustion — with a **three-tier sensitivity ladder** (early / confirmed / undeniable), each tier shipping its *measured* detection-lag distribution and false-alarm rate (the honest version of "front-running": act at the early tier knowing its error rate). Two-sided pairing: source complex (out) × sink complex (in), flagged only with cohesion on both legs. Run over Tier S+M history → **the Episode Catalog** (`data/oracle/episodes.parquet`): every rotation since 1998 (sector-level) / 2021 (subsector-level), labeled with onset date, source/sink, duration, magnitude, breadth, two-sidedness, regime backdrop, and outcomes (sink-vs-source forward spread at +5/21/63d from each detection tier). Deliverable doc: **`ORACLE_EPISODE_ATLAS.md`** — the deep study of rotations through time the operator asked for, famous episodes annotated. Expected n: low hundreds (sector) + ~100–200 (subsector era) — this number dictates the ML tier.

### O3 — Pattern memory (the brain, sized to the data)
Two metabolisms, each sized to its food supply: **structure learning** (O1's graph/routing/lead-lag) feeds on the full daily panel and can go deep; **outcome learning** (below — persistence, expected spread) feeds on episodes (n = hundreds) and stays regularized + analogue-based. Conflating the two budgets is how rotation engines die of overfitting.
- **Tier A (always ships): conditional base rates.** Per episode-type × regime × detection-tier: median sink-vs-source spread, hit rate, duration, n — printed on the page exactly like `sector_signals.STATE_BASE_RATES`. These are the "machine-learned truths," fully interpretable.
- **Tier B: regularized ML.** Gradient-boosted trees / logistic on episode features → P(persistence), expected spread, expected remaining duration. Purged/embargoed CV, era holdouts (must survive 2015+ OOS and separately 2020+ and the 2023+ AI era), FDR with a registered trial count, isotonic calibration + Brier scoring. Walk-forward monthly retraining harness with drift monitors (the "continually train" requirement, made safe).
- **kNN episode analogues (the flagship mechanism).** Current unfolding state → nearest historical episodes by DTW distance over normalized RS trajectories + feature vector → "current tape ≈ Nov-2021 semis-top, day 8 of median 40; in the 7 nearest analogues the sink outperformed in 6." Interpretable, low-overfit, UI-native, and the thing no competitor page shows.
- **Tier C (deferred, gated):** any sequence model (temporal CNN / small transformer) enters only if it beats Tier A+B out-of-sample under the same gauntlet. With n in the hundreds, a deep net is overfitting bait — the moat is the data asset + discipline, not parameter count.

### O4 — Live inference + propagation (reuses the audit doc's rails verbatim)
Nightly (Tier-L append → panel row → graph update → state machines → memory scores) → **`site/basketdata/oracle_state.json`** on the `sector_pulse` bus: per-complex rotation state + tier, active episodes with analogues + conditional stats, onset watchlist, breadth/regime aggregate. Consumers: **(a)** panels on the four pages; **(b)** alert events via `theme_alerts → alert_triage` (types: `group_rotation`, `two_sided_rotation`, `leadership_rollover` — the loud EXIT, `regime_shift`; idempotent ids, silent seed); **(c)** **banner** escalation for breadth-confirmed major shifts — deterministic threshold decides, LLM narrates and may only *de-escalate* (`whitehouse_brain` contract; Opus barred from the calibrated key); **(d)** **Mastermind directive** → `master_brain.rotation_check` (structured regime vector + exit list; tempers conviction / raises cash; never fabricates a directional buy; the quant GTAA book in `masterminds.py` holds no sectors — untouched); **(e)** stock desk — dark bounded tilt via `spotlight.theme_tilt → stock_score._axis_tailwind` (config-gated OFF, two-sided regression test, flips on Phase-0 pass) + Buy-Board-2.0 group-leadership ordering (soft; hard group gates stay banned per the China falsification).

### O5 — The Time Machine (subsector_rotation.html)
Date scrubber + play button replaying the panel: RRG quadrant view, complex-level graph view, treemap — with episode spans overlaid ("semis→healthcare rotation, day 12/~40") and the analogue panel alongside. Granularity toggle: **Sectors (1998→) / Themes+Baskets (2021→) / Subsectors (2021→)**, survivorship watermark on reconstructed tiers ("membership as of 2026-06 — historical composition approximated"). Preset "famous episodes" playlist (2020 crash+recovery, 2021 growth top, 2022 energy, 2023 AI ignition, 2025-26 semis→healthcare). Frontend feed = chunked/quantized JSON exported from the panel (the finviz-themes lazy-load pattern). This is simultaneously the research instrument, the validation showcase, and the SaaS differentiator; whether it's auth-gated premium is an operator decision (D6).

### O6 — Validation constitution (binds every claim)
Pre-registered before Phase 3 runs: (i) benchmarks — every persistence claim vs the momentum null (§1.2) AND vs `sector_signals` state base rates AND vs random-onset placebo episodes; (ii) confound controls — VIX-stratified, rates-controlled, trend-regime cut (the DEFENSIVE_ROTATION machinery); (iii) era holdouts as in O3; (iv) FDR with a registered trial ledger including machine-proposed trials; (v) detection-lag honesty — lag distributions per tier published, k≈0 findings labeled *coincident* and named for the quantity they route (drawdown/exposure), never "leading" ; (vi) survivorship stamps — Tier-M claims carry the watermark until Tier-L confirms; (vii) anything failing ships **display-only with the null printed** (house law; a legitimate outcome). The forward ledger grades every live detection from day 1 as the standing audit.

## 4. Phased plan

House model routing: **Sonnet builds, Opus reviews, Fable plans/fixes/merges.** Heavy computation runs on the Mac **off the 67-minute render path** (separate script/cron, artifacts → R2). Each PR: fresh worktree off main, hermetic tests, bilingual UI, same-day squash-merge.

| Phase | What | Key deliverables | Staffing / notes |
|---|---|---|---|
| **P0 — Census + masterplan** | *done this session* | this doc; census facts | Fable |
| **P1 — Stop the bleeding + the Panel** | (a) **immediately**: daily archival of `themes_tree.json` (hash-on-change) + keep snapshots.jsonl — every unarchived day is PIT membership lost forever; (b) build O0 panel Tiers S+M with coverage/leak audits | `collectors` tweak; `engine/oracle/panel.py`; `data/oracle/panel_*.parquet`; audit report | Sonnet ×2 PRs, Opus review. The long pole; ~2–3 sessions |
| **P2 — Graph + Episodes** | O1 + O2 over the panel; backbone map; edge-stability ledger; episode catalog + Atlas | `graph.py`, `episodes.py`, `episodes.parquet`, `ORACLE_EPISODE_ATLAS.md` | Sonnet build, Opus review, Fable adjudicates episode definitions |
| **P3 — The Gauntlet** | O6 pre-registered backtests over the catalog; verdicts decide what ships scored vs display-with-null | gate results doc + trial ledger | **Codex-outsourced grids** (per the proven triage→re-run-in-repo pattern), gates authored by Fable, survivors re-verified in-repo. Codex prompt authored at end of P2 (needs frozen schemas) |
| **P4 — Pattern memory** | Tier A base rates; Tier B GBT + calibration; kNN analogues; retraining harness | `memory.py` + calibration report | Sonnet builds, Opus reviews math |
| **P5 — Live wiring** | O4: bus payload, alerts, banner, Mastermind directive, dark spotlight tilt, Buy-Board ordering | `live.py` + wiring PRs | reuses audit-doc contracts; two-sided dark tests mandatory |
| **P6 — Time Machine UI** | O5 on subsector_rotation.html | template/JS + chunked feed | can start right after P2, parallel to P3/P4 |
| **P7 — Continual loop + later quest** | nightly append, monthly walk-forward retrain, quarterly edge refresh, forward-ledger grading; then options/IV/GEX columns (OPRA day-aggs 2024→ is real backtest depth; chains/skew still weeks old), CN/HK port | | options layer earns its own Phase-0 |

**Dependency shape:** P1 → P2 → {P3 ∥ P4-scaffold ∥ P6} → P4-final → P5 → P7. First user-visible win: the Atlas + Time Machine (P2+P6) — they need no predictive claim at all.

## 5. Risks & honest expectations
- **Subsector membership survivorship (Tier M) is the biggest epistemic hole.** Today's "AI complex" members are the cycle's winners; reconstructed 2021–23 AI indices will look artificially coherent. Mitigation: validated claims live on Tier S; Tier M is detection-resolution + display; Tier L converts patterns to validated ones as it accrues. Never quietly promote a Tier-M number.
- **Episode n is small** (hundreds, not millions). ML tier is capped accordingly; Tier C stays gated. Anyone proposing a deep net answers to the gauntlet first.
- **Finviz endpoints are undocumented** (`/api/map_perf*`) and can vanish; the panel reconstruction makes Oracle independent of them for history, and tree archival caps the damage going forward.
- **Expected outcome, stated up front:** exit-side authority and regime-conditional persistence stats are likely to validate (the repo's own SELL −1.24% and cohesion_chg findings point that way); a large unconditional entry edge is unlikely (every momentum null points that way). If the gauntlet returns "router yes, oracle no," the system is still the moat product — that verdict would be printed, not hidden.

## 6. Decisions for the operator (the STOP list)
*2026-07-04: operator approved execution. D1–D5 and D7 adopted as recommended; D6 (Time Machine free vs premium) stays open until P6 ship.*
- **D1 — Approve P1(a) tree archival immediately** even if everything else waits: it's a tiny collector change, and each day of delay is permanent PIT loss. *(Recommended: yes, now.)*
- **D2 — Scope:** US-first, CN/HK port in P7? *(Recommended: US-first.)*
- **D3 — Codex outsourcing of P3 grids** (token economy) with in-repo re-verification of survivors? *(Recommended: yes.)*
- **D4 — Name:** "Oracle" as product name with `engine/oracle/` namespace despite the docstring-level collisions? *(Recommended: yes as scoped.)*
- **D5 — Compute placement:** panel builds + retraining on the Mac off the render path, artifacts to R2? *(Recommended: yes; render budget is law.)*
- **D6 — Time Machine access:** free (marketing showcase) vs auth-gated premium (SaaS moat)? *(Operator call; recommend free scrub for Sectors tier, premium for full subsector replay + analogues.)*
- **D7 — Banner threshold:** major-rotation banner requires the *confirmed* tier + breadth floor (not *early* tier) to protect banner credibility? *(Recommended: yes.)*

## 7. Status log
- 2026-07-04 — Masterplan authored (Fable) after adjudication of the operator's pushback (DEFENSIVE_ROTATION scope-corrected; momentum nulls retained as the bar) + 5-agent data census. Program paused at the operator STOP.
- 2026-07-04 (later) — **Operator approved; execution started.** Second adjudication folded in: the "endless combinations" argument is ACCEPTED for structure learning (graph / Flow-Routing Matrix / lead-lag ride the full daily panel) and REJECTED for supervised persistence (episodes remain the unit; combinations multiply hypotheses, not observations — FDR + era-stability pay that cost). O1 gains the Flow-Routing Matrix + lead-lag tensor as first-class deliverables. P1 dispatched: P1a PIT archival + P1b rotation panel (Sonnet builds → Opus reviews → Fable fixes+merges).

# CN LIMIT ALPHA — BLINDED BRAINSTORM (ore-law §1.4 fresh-eyes lane) — 2026-08-08

**Provenance:** produced by ONE independent Fable brainstorm subagent (orchestrator gate,
FABLE-WHY: brainstorm), deliberately BLINDED to the commissioning session's §4 construction map
and to all `research/` docs; given only the operator charter, ore law, data inventory, and v0
measurement summary; grounded by its own schema probes of `data/china_*` and
`engine/china_microstructure`. Merged into the program per masterplan §5. Verbatim below —
editorial annotations appear ONLY in the masterplan, never here.

**Commissioning-session verification (2026-08-08, before commit):** the two most load-bearing
grounding claims were independently re-verified: `data/china_microstructure/limit_events.parquet`
carries event ∈ {sealed_up 27,017 · failed_up_seal 13,871 · sealed_down 11,131 ·
failed_down_seal 8,409} with `lianban_count` + `close_off_limit_pct` (strict-definition basis;
34-name history hole under heal in W1-L0), and `data/china_holder_counts/holder_counts.parquet`
carries `total_a_shares` + `holder_num`/`avg_hold_num` at disclosure cadence (6,551 rows).
`data/china_microstructure/limit_tape.parquet` is additionally a DAILY AGGREGATE series
(limit_up_count, failed_up_seal_count, lianban_max, breadth, 2011→2026-08-07) — several §C7
regime instruments pre-exist there and the W1-L2 lane's independent build doubles as its
cross-check.

---

## BLINDED BRAINSTORM — CN Limit-Move Alpha: independent construction map (verbatim)

*Produced blind: no `research/` reads; grounded only in the operator charter, ore law, v0 summary, and direct schema inspection of `data/china_zt_pool/pool.parquet`, `data/china_stocks_raw/`, `data/china_microstructure/limit_events.parquet`, `data/china_search/members.parquet`, the `engine/china_microstructure.py` API surface, and existence/schema/date-range checks of adjacent `data/china_*` stores. No measurements were run.*

**Grounding facts relied on below** (verified at schema level, 2026-08-08): raw bars are OHLCV only — **no `amount`/成交额 column**, so no VWAP proxy exists today; the house tape emits four event types `{sealed_up: 27,017, failed_up_seal: 13,871, sealed_down: 11,131, failed_down_seal: 8,409}` 2011→2026-08 with `lianban_count` and `close_off_limit_pct` = (lim−close)/lim; zt_pool = 47 dates, per-name `consec_boards`, `seal_fund_yi`, `failed_seals` (values up to 8 observed), `turnover_pct`, THS-style `sector`; `members.parquet` is coarse-sector current membership with `mktcap_yi`; adjacent stores already exist as running scrapes with shallow (mostly 2026-06→08) windows: `china_lhb` (per-name net_buy_yi, inst splits, reasons — not per-seat), `china_margin_detail` (per-name fin_balance), `china_block_trades`, `china_unlocks` (with 占流通市值 ratio), `china_inquiry`; deeper: `china_holder_counts` (股东户数 2013→now, incl. `total_a_shares`, `avg_hold_num`), `china_preannounce` (业绩预告 with 预告类型 and 公告日期), `china_connect` (aggregate-only northbound, ~11y). ST membership history starts 2026-07-06 (`ST_STORE_COVERAGE_DATE`). Volume units (shares vs 手) are unverified — a construction prerequisite, not an assumption.

---

## 1. MECHANISM TAXONOMY

Seven physically/psychologically distinct board-producing processes. They co-occur, but each has its own actors, fuel, exhaustion, and daily-bar fingerprint — and several make **opposite** predictions from the same observable (volume, especially), which is why species/mechanism classification must precede any pooled statistic.

### M1 — Shadow-price overhang (hard-news truncation)
- **Actors:** everyone; the news is real (earnings surprise, contract, asset injection, policy beneficiary designation, resumption after suspension).
- **Loop:** fair value jumps +25-40%; the band prints only +10% (or 20%); unfilled demand queues overnight; next auction gaps; repeat until the shadow price is reached. This is the purest form of the operator's thesis — the US one-session move stretched over days *by law*.
- **Exhausts when:** cumulative move ≈ news value. The tell is endogenous: supply appears (holders finally willing to sell), the seal weakens, volume expands.
- **Footprint family:** 一字板 sequences (O=H=L=C=limit; volume is pure seller capitulation into the wall — small and *shrinking* volume = queue lengthening = longer ladder); species decay sequence 一字 → T字 → 换手 as the gap to fair value closes; a terminal 开板 day (first non-locked day) with volume explosion. In zt_pool terms: huge `seal_fund_yi` relative to turnover, `failed_seals`=0 early, rising late.

### M2 — Promoter campaign (游资做庄 markup-distribution lifecycle)
- **Actors:** one or few coordinated hot-money desks vs retail followers; no hard news required, a story suffices.
- **Loop:** 建仓 (quiet accumulation) → 试盘 (probe pushes to test overhead supply) → 拉升/打板 (mark up to the board *because the board is free advertising* — the zt pool is a product feature on every retail terminal) → 洗盘 (engineered washout, often a deliberate seal-break) → second leg → 出货 (distribute into chase demand).
- **Exhausts when:** desk inventory is distributed. Boards get progressively "heavier": later seals, more breaks, higher turnover while price still rises; the final print is classically a gap-up that fades or a monster-volume T字板 — the exit-liquidity harvest.
- **Footprint family:** *pre-onset* — weeks of positive drift with up-day/down-day volume asymmetry, rising volume floor, probe days (wide H−L, small |C−O|, volume spike, high stalling at a shelf); *onset* — board following a shallow pullback (N字 setup); *late* — `failed_seals` and `turnover_pct` rising board over board. Volume signature is **inverted vs M1**: big from day one (the desk must buy the float), whereas M1 starts volumeless.

### M3 — Theme contagion and relay (题材/板块效应, 龙头-跟风 tiering)
- **Actors:** the whole speculative complex coordinated by narrative; capital allocates by concept, not fundamentals.
- **Loop:** catalyst elects a 龙头 (first/hardest boarder); its board raises theme salience; sympathy names get pattern-matched bids (龙二/龙三 → 跟风 → 补涨 laggards); each new board re-validates the theme; the leader's height sets the whole theme's risk budget (空间).
- **Exhausts when:** the leader breaks (断板/跌停) — followers reprice violently within a day; or fringe members start boarding (breadth blowoff = the theme ran out of credible names); or a newborn theme steals the capital (rotation is roughly capital-conserving).
- **Footprint family:** same-day sector limit-heat (v0's 2.39× is this, static); calendar ordering of first boards within sector (leader = earliest + highest `lianban_count`); laggard profile = low prior run-up + board arriving K days after theme inception (onset probability up, continuation quality down — the two-sided signature is the mechanism's proof); leader-death days followed by follower gap-downs.

### M4 — Float lockup / chip vacuum (筹码锁定)
- **Actors:** the desk plus converted holders; the *absence* of sellers is the mechanism.
- **Loop:** washouts transfer float from weak to strong hands; remaining tradable supply shrinks; ever-smaller buying re-seals the board; observed "strength" breeds holding, which shrinks supply further.
- **Exhausts when:** price reaches levels where locked holders finally distribute — or an external shock (regime break, 特停) forces correlated exit into no bid.
- **Footprint family:** **volume contraction on up days mid-run** (price up, volume down = no supply — bullish here, suspicious in M2's late stage; the sign of volume flips by mechanism and run-phase), range tightening before continuation, modest `seal_fund_yi` with `failed_seals`=0 (you don't need a big wall when nobody sells), low `turnover_pct` at high board counts.

### M5 — Aggregate sentiment cycle (情绪周期 — the reflexive regime)
- **Actors:** the hot-money collective's aggregate risk dial; the game itself as an organism.
- **Loop:** 冰点 (freeze) → 修复 (a first successful high board "opens space") → 发酵 → 高潮 (max height and breadth) → 退潮 (promotion failures, 炸板潮) → back to freeze. Profitability of yesterday's boards *today* (昨日涨停今日表现) is the canonical health metric the crowd itself watches — feedback is direct and fast. Cycle length lore: 2-6 weeks.
- **Exhausts when:** by definition it doesn't — it oscillates. What kills a whole *era* is exogenous: regulatory doctrine shifts (2017 speculation crackdown), structural reform (registration system killed shell value), microstructure change (ChiNext 20% bands 2020-08-24), counterparty evolution (quant T+0 desks post-2021 arbitraging around seals).
- **Footprint family:** fully computable daily series from the house tape: #sealed_up, #failed_up_seal (→ market 炸板率 = failed/(failed+sealed)), #sealed_down, max `lianban_count` alive, realized promotion rate (yesterday's boards that board again today), first-board breadth vs high-board breadth. The v0 era swing (first→second 7.93%→24.18% across years) is this mechanism's low-frequency shadow; it mandates that **every other construction carries a regime conditioning variable**.

### M6 — Calendar/mechanical catalysts
- **Actors:** issuers and the calendar; speculators front-run known dates.
- **Loop/exhaustion:** discrete — 业绩预告 windows (`china_preannounce` has 预告类型+公告日期), 高送转 season, resumption events (visible as trading-date gaps in raw bars followed by ladders; largely a pre-2016-reform phenomenon — era-scoped), IPO 一字 ladders and the distinct 次新开板 second-wave game (listing date = first row in raw file), unlock dates (`china_unlocks` — supply catalysts, board-killers), index rebalances.
- **Footprint family:** date-anchored conditioning; these are *interaction terms* for M1/M2 constructions, and era filters (resumption ladders must not contaminate post-2016 estimates).

### M7 — The mirror complex (limit-down cascades and reversals)
- **Actors:** trapped holders (T+1 means today's buyers can't flee today), pledge-liquidation supply, busted-campaign desks.
- **Loop:** limit-down closes trap everyone in; overnight fear queues sell orders; open gaps down; repeat (v0: 14.9%→38.6% mirror ladder). 地天板 (L=limit-down, C=limit-up or near) marks violent washout completion — the strongest single-bar reversal print in the game.
- **Exhausts when:** price reaches bargain-hunter depth, a white knight appears, or the forced supply (pledges, margin) is done.
- **Footprint family:** `sealed_down`/`failed_down_seal` ladders in the tape; recovery shape after first limit-down (the exit-cost table every long book needs); L-at-limit-down + strong close as reversal marker. Survivor bias is *worst* here — delisted names are exactly where cascades end — so estimates are lower bounds on severity.

---

## 2. SECOND/THIRD-ORDER STRUCTURES

**2.1 The T+1 inventory war and the day+1 open as its verdict.** Day-0 board buyers are locked overnight; at day+1's open they are the only profit-holding sellers, facing overnight-fermented new demand. The auction nets these two flows into one number — the gap — and the intraday close-vs-open resolves who won. Third order: because *everyone knows* day+1's open is the sell window, sophisticated desks pre-commit capital to absorb the open supply of names whose theme health their inventory depends on — leaders get defended at the open, followers don't. Prediction: (gap, C−O, volume ratio) on day+1 is a 3-dim sufficient statistic for day+2, and its informativeness is rank-ordered by leader status.

**2.2 Weekend/overnight fermentation asymmetry.** A Friday board gets ~65 hours of stock-forum/media fermentation before Monday's auction vs ~17 intraweek; policy announcements cluster on weekends; the slow crowd reads weekend recaps. Predictions: Friday boards carry higher Monday gap variance and fatter sympathy breadth; theme *births* cluster on Mondays; desks rationally choose Friday-afternoon launches to harvest the free amplifier — so Friday 换手板 first-boards are a distinct, richer cohort than Tuesday ones.

**2.3 Seal-wall game theory (封单 as costly-but-cancellable signal).** A wall at limit is an advertisement that costs nothing until filled and can be cancelled — partially spoofable (撤单诱多). Honesty tests available at daily resolution: (a) the **closing** wall (zt_pool `seal_fund_yi` is an end-of-day/asof snapshot) is more honest than any intraday wall since cancellation windows are gone; (b) wall size must be read *relative to traded money* (`seal_fund_yi` vs the day's turnover) — an absolute wall is meaningless; (c) the wall/next-open cross-check: monster wall → weak open reveals the wall was one desk's paint (the crowd didn't come); modest wall → big gap reveals genuine broad demand. Third order: **deliberate 炸板** — the desk pulls its own wall to trigger stops, buys the flush, re-seals; prints as T字板 with deep L and elevated volume. Hypothesis (contrarian to naive seal-quality logic): 1-2 breaks with a hard re-seal and firm close can *out-continue* a zero-break light-volume seal, because the washout happened inside the day.

**2.4 Relay tiering, the 龙头 Schelling point, and 卡位.** Capital concentrates on the recognized leader because coordination needs a focal point — the leader's board is "safest" precisely because everyone believes others believe it. Consequences: leader premium in continuation at equal height; follower fragility on leader stumbles (the crowd's stop-loss is keyed to a *different stock's* print — a genuinely unusual cross-asset structure); 卡位 — when the leader hesitates, a challenger that boards on the leader's break day inherits the crown and its continuation jumps. Followers exist, functionally, to be rotated out of; 补涨 laggards are the exit vehicle.

**2.5 Height psychology and 打开空间.** The market's living maximum ladder height is a shared risk budget: when a name crosses the cycle's previous max (opens space), every desk recalibrates achievable height upward — a market-wide state change triggered by one stock. Falling max-height = contraction phase where only leaders survive. This is a *regime input that a single name creates* — second-order reflexivity absent from Western tapes.

**2.6 The pool-as-product attention machine.** Every retail terminal ships the zt pool sorted by board count; attention → next-day demand is thus a *deterministic function of pool composition*. Two consequences: (a) pool-visible fields are the attention allocator itself, not proxies for it; (b) there is a sharp visibility discontinuity at the seal: a +9.9% sealed close is broadcast, a +9.4% near-miss is not. That boundary is a natural experiment on the attention channel, separable (imperfectly) from the mechanical supply difference the seal itself creates.

**2.7 The regulatory metagame.** 特停 hazard rises with height and media heat; inquiry letters (`china_inquiry` exists) force rumor denials that kill runs; 减持 announcements by majors reliably end ladders; LHB disclosure itself is feedback (a known one-day-punter seat on the list poisons day+2; an institutional seat legitimizes). The regulator's unwritten height tolerance is itself regime-varying — crackdown eras cap the ladder distribution's right tail *by decree*, which any height-extrapolating model must respect. Third order: desks know disclosure thresholds and manage order sizes to stay off the list — LHB absence on a huge day is itself informative (many small hands vs one big one).

**2.8 The counterparty era-shift.** Post-2021 quant T+0 desks arbitrage around seals (selling into re-seals, buying breaks); plausible fingerprints: rising market 炸板率 trend, fewer clean 一字 ladders, faster intraday mean reversion around the limit. Not a construction yet — an *era covariate* the harness must carry so that pre/post structural drift isn't read as signal decay.

**2.9 Fillability structure (the entries the mechanism actually offers).** A locked board cannot be bought — the strongest states are the least available. The practitioner taxonomy is exactly an entry-timing menu: 打板 (buy the seal moment — needs intraday), 半路 (buy mid-flight pre-seal — needs intraday), 低吸 (buy weakness in a proven name — fillable at daily resolution), 接力 (buy day+1's open — fillable, and the gap is the price of admission). At daily granularity our executable moments are **the day+1 open and weakness days**; every continuation number must therefore be restated open-anchored (O(t+1)→C(t+1), O(t+1)→O(t+2)) and gap-conditioned, with locked opens censored as unfillable. The v0 close-to-close ladder overstates capturable edge wherever gaps eat it; the residual after the gap is the product.

**2.10 The correlated-exit tail.** All ladder positions share one exit door: T+1 means Friday's buyers can only exit Monday, and a regime break (weekend policy shock, leader 天地板) sends every crowded ladder to the same auction simultaneously. The book is structurally short a liquidity option; portfolio math (§5) must price it — per-theme caps, height-bucket caps, and a regime throttle are not refinements, they are the survival constraint.

---

## 3. TESTABLE-TODAY CONSTRUCTIONS

Ranked by expected discriminative value × feasibility. Tags: **[A]** = computable now on the 15y tape/raw bars (survivors-only, 1,842-name curated slice — bias direction noted where it bites); **[B]** = computable now, display-tier only (47-date pool / recent-window stores); population, conditioning, outcome, horizon stated for each. All entry-implying outcomes are open-anchored per §2.9.

**C1. Board-species state machine (continuation core). [A]**
Population: all `sealed_up` events, 15y. Classify day-0 species from OHLCV + limit authority: 一字 (O=H=L=C=lim), T字 (O=C=H=lim, L<lim), 换手硬板 (O<lim, C=H=lim), plus depth-of-day features (L/C, O/C) as continuous seal-lateness proxies (no `amount` column → no VWAP; OHLC shape is the honest fallback), 地天 (L at limit-down). Condition: species × `lianban_count` × band era × regime tercile (C9). Outcomes: P(seal t+1), P(failed_up_seal t+1), gap(t+1), O(t+1)→C(t+1). Mechanism: species is the seal-quality print, and M1 vs M2 predict *different species sequences* along a run (一字→换手 decay vs 换手 throughout). Failure mode: species confounds with float size and era (一字 concentrated in suspension/restructure era and tiny floats underrepresented in the slice); control by era, report per-band.

**C2. The fillability frontier (open-executable continuation surface). [A]**
Population: day+1 opens following any sealed_up. Condition: state (N, species, regime) × observed gap g at the only decision moment daily data honors (the open). Outcome: E[O→C], E[O→O(t+2)], P(seal | g), with censoring rule for unfillable opens (g ≈ limit; conservative: treat g > ~7% on main as unfillable). Deliverable is a *decision surface*: pay-the-gap-or-walk by state. Mechanism: §2.1 — the gap is the crowd's posted price for the continuation option; edge is whatever the auction systematically underprices. Failure mode: open fills in reality require queue participation the daily bar can't see — haircut and later verify against the auction-snapshot collector (P5). This is the program's core table; everything else feeds it.

**C3. 炸板 shadow cohort resolution. [A — the tape already carries it]**
Population: 13,871 `failed_up_seal` events. Condition: broken depth (`close_off_limit_pct`), volume z vs 20d, run-up, whether a prior ladder existed, regime. Outcomes: P(re-seal t+1) (回封), gap(t+1), O→C(t+1), 2-day drawdown. Mechanism: the break is the single most information-dense print — a revealed contested wall; practitioners trade 回封 aggressively, and §2.3's deliberate-washout hypothesis predicts a *non-monotone* relation between break count and next-day strength. Failure mode: break depth conflates desk-engineered washouts with genuine rejections; the volume/close-shape interaction is the separator to test, not assume.

**C4. Day+1 relay-quality state (the three-number verdict). [A]**
Population: all day+1 bars after a seal. State: (gap sign/size, C−O sign/size, vol(t+1)/vol(t)). Outcome: day+2 seal/continuation and death-mode hazard (C16). Special cells: 低开红盘 (down-open, green close — flushed weak hands absorbed; predicted strongest day+2), 高开绿盘 (up-open, red close, volume blowoff — distribution climax; predicted worst). Mechanism: §2.1 inventory war resolution. Failure mode: cell sparsity at high N — merge adjacent cells by monotonicity constraints rather than free estimation.

**C5. Onset composite from accumulation footprints (首板 radar). [A]**
Population: name-days not in a ladder. Features (all daily-bar): 20d drift with up/down-day volume asymmetry (OBV-style), probe count (last 15d days with (H−L)/C > q90, |C−O|/C < q30, vol z > 1.5), range compression (5d/20d ATR ratio), shelf distance (C vs 60d max and volume mass near current price as trapped-supply density), MA posture, and the *relaxed* near-limit family (rolling 20d count of H within 2% of limit — the continuous repair of v0's unstable thin flag). Outcome: P(sealed_up within 1-5d), open-anchored. Mechanism: M2's build phase must buy shares and test supply — it cannot not print. Failure mode: each feature is weak alone (confluence-tier by design); incremental value over v0's six must be shown (their Jaccard discipline), else this is re-derivation.

**C6. Sympathy-vacancy detector (补涨 slot). [A with coarse sectors; sharpens with P7]**
Condition: sector heat ≥ 2 sealed names for ≥ 2 consecutive days (tape + members.parquet, acknowledging current-membership drift — restrict to stable industry sectors for history); candidate = member with zero boards this wave and bottom-quartile 5d run-up among members. Outcomes, two-sided by design: elevated P(onset ≤ 2d) AND degraded continuation-after-onset vs matched first boards. Mechanism: M3 tiering — capital hunts un-lifted members, but the slot it fills is the exit vehicle. The two-sided prediction makes this a *mechanism test*, not just a signal: if onset lifts without the continuation penalty, the tiering story is wrong. Failure mode: sector granularity (industry ≠ 题材); treat historical results as lower bounds on the concept-mapped version.

**C7. Market regime dial v1 (情绪周期 thermometer). [A — partially prebuilt in `aggregate_daily`]**
Daily series from the tape: sealed_up count, market 炸板率 = failed/(failed+sealed), sealed_down count, max living `lianban_count`, realized promotion rate, first-board vs high-board breadth. Compose into a 3-state regime (expansion/churn/ebb) with hysteresis; validate against the v0 era swing (the regime should *explain* most of the 7.93%→24.18% first→second variation at daily resolution). Outcome: conditioning variable for every construction + standalone throttle rule. Failure mode: curated-slice bias understates true breadth — use within-series ranks, never absolute counts; survivors inflate levels but the *cycle shape* should survive.

**C8. Leader-death contagion switch. [A coarse / sharpens with P7]**
Event: sector leader (max `lianban_count` in sector among live ladders) prints failed_up_seal, no-board day, or sealed_down. Outcome: same-day and t+1 O→C of all other laddered names in that sector vs matched ladders in healthy sectors. Mechanism: §2.4 — followers' stop-loss keys on the leader's print. This is the *exit overlay* for every follower position and the 卡位 detector (a follower sealing on the leader's death day inherits elevated continuation). Failure mode: leader ambiguity on ties; height-vs-leadership confounding (match on N).

**C9. Death-mode risk model (the stop-loss science). [A]**
Population: ladder-end days (first no-seal day after N ≥ 2), 15y. Modes: (a) gap-up-fade (O > 1.03·C(−1), C < O), (b) flat grind (|gap| ≤ 1%, red), (c) door-slam (sealed_down or L at limit-down), (d) suspension (calendar gap — censor separately, it's the 特停/inquiry channel). Outcomes: next-3d drawdown distribution by mode × prior height × species sequence; P(mode | day-0 state). Mechanism: M2's distribution endgame vs M7's trap. The T+1 trap makes exit modeling half the P&L; a continuation book without this table is unsized. Failure mode: survivor bias truncates the worst tails (delisted names) — label all severities as lower bounds.

**C10. 龙回头 second-wave (低吸 entry). [A]**
Population: ended ladders (≥ 3 boards). Pullback-quality state: drawdown vs run height, volume decay slope, days elapsed (3-6 sweet spot per lore — test, don't assume), zero limit-down prints, C holding above half-retrace. Outcome: P(new seal ≤ 5d), O→C on entry days. Mechanism: M4 — the washout completes chip transfer; the name has *proven* 承接力 (carrying capacity), and the desk that distributed re-enters cheaper. Strategically premium because fills are guaranteed (buying weakness) and adverse selection inverts. Failure mode: indistinguishable from dead-cat in ebb regimes — hard-gate on C7 state.

**C11. 一字 queue-depth proxy and the 开板 playbook. [A]**
For locked ladders: locked-day volume ≈ seller surrender rate into the wall; *falling* locked-volume = lengthening queue = longer ladder (M1). Predict remaining ladder length from day-1/2 locked volume vs the name's own 60d mean (no float data — self-normalization only). Then the first open day: classify continue-vs-top from open-day gap, volume z, close position. Failure mode: no share counts weakens normalization (P4 sharpens); resumption-era 一字 ladders are a different regime — era-split mandatory.

**C12. Near-miss attention discontinuity. [A]**
Population: days closing in [+8.5%, lim) with H < lim (never sealed — distinct from C3's breaks) vs sealed closes, matched on run-up/volume/sector-heat. Outcome: gap(t+1), O→C(t+1), P(seal ≤ 2d). Mechanism: §2.6 — the pool boundary is a visibility cliff; if sealed names outperform matched near-misses beyond what the trapped-supply difference explains, the attention channel is real and pool-visible features deserve their weight program-wide. Failure mode: the seal itself changes supply mechanics (T+1 locks buyers) — attribution is bundled; still decision-relevant (do near-misses deserve entries at all?).

**C13. Ladder volume-trajectory shape (锁仓 vs 出货 separator). [A]**
Along ladders N ≥ 2: vol_N/vol_{N−1}, vol_N vs pre-run 20d mean, range_N. Test the canonical lore: expand boards 1-2, contract 3+ (M4 healthy) vs monotone expansion with rising failed_seals (M2 distribution); terminal blowoff as top marker. Outcome: continuation + C9 death-mode hazard shift. Failure mode: slice under-represents the tiny floats where lockup is strongest; volume-unit verification is a prerequisite.

**C14. Friday/Monday fermentation differential. [A]**
All seals by weekday: Monday gap/promotion vs intraweek baseline, market-gap-adjusted; theme-birth weekday histogram; Friday-seal → Monday sector sympathy breadth. Mechanism: §2.2. Failure mode: weekend macro-news confounding is *part of the mechanism*, but index-level moves must be subtracted to isolate the name-level channel.

**C15. Cross-band theme telemetry (20% names as forecasters). [A, post-2020-08-24 era only]**
Within sector-days where a ChiNext member moved ≥ 12% while a main-board sibling laddered ≤ 10%/day: use the 20%-name's 2-day cumulative move as the theme-magnitude estimate; predict the sibling's *remaining* ladder length from the residual. Mechanism: the wide band reveals the shadow price M1 hides. Failure mode: different crowds play the two bands (ChiNext idiosyncrasy); small N; sector-map coarseness.

**C16. Limit-down mirror: trap-exit table and 地天 reversal. [A]**
(a) After a first sealed_down on a held name: P(consecutive LD), by open behavior — the sell-the-open-or-wait table by state. (b) Days with L at limit-down and C ≥ prev close: next-day continuation (washout-completion play). Mechanism: M7. Failure mode: survivorship censors the cascade endings — severities are lower bounds; treat (a) as risk table, not alpha.

**C17. Seal-wall honesty panel. [B — 47 dates, display-tier by construction]**
Cross-sectional daily within the pool: rank by `seal_fund_yi` normalized by that day's traded money and by float where `turnover_pct` implies it; interactions with `failed_seals` (big wall + many breaks = paint suspicion per §2.3) and next-day gap (wall→open cross-check). Outcome: next-day promotion/gap. Prerequisite: pin `seal_fund_yi` snapshot semantics from the collector before constructing (asof timing matters — closing wall vs last-seen). Accrues to authority-tier automatically as the scrape runs; backfill (P2) converts it retroactively.

**C18. Leader-defense asymmetry at the open. [B now / A-coarse historically]**
Split pool ladders by within-sector board-count rank: leaders vs followers, matched on N. Outcome: day+1 gap distribution and gap-fade rate (O→C given gap > 3%). Mechanism: §2.1 third order — desks defend the opens their inventory depends on. Historical coarse version from tape + sector map; sharp version needs pool/concept history (P2/P7).

**Meta-construction M. Era-robustness harness.** Every construction above reports per era (2011-14, 2015 mania, 2016-18 crackdown, 2019-21 revival incl. band change at 2020-08-24, 2022-23 grind, 2024-26 current) with sign-stability required across eras and the quant-T0 era covariate (§2.8) carried. The 3× era swing in the v0 promotion rate makes any un-era-split result unreportable. Reuse the v0 holdout discipline and Jaccard-style redundancy checks against the six established features.

---

## 4. COLLECTOR PRIORITIES

Ordered by unlocked-construction value per unit cost; extend-existing >> new scrape >> new vendor. Discovery during grounding: several "missing" datasets already exist as running scrapes with shallow windows — the cheap move is *keep them running and backfill archives*, not new integrations.

**P1. Backfill the zt_pool family (highest single unlock).** The vendor page family behind `china_zt_pool` typically also serves 炸板池, 跌停池, and 昨日涨停表现 endpoints, and several portals archive history. Even 2-3 years converts C17/C18 to gauntlet-eligible, gives a *market-wide* (not slice-biased) promotion metric and 炸板率 for C7, and provides ST/small-cap coverage the raw slice lacks. Add sibling endpoints to the existing scrape cadence at ~zero marginal cost.

**P2. Add `amount` (成交额) to the raw-bar collector, and per-name history where the source offers it.** Unlocks the VWAP proxy → seal-lateness (尾盘偷袭 detection) in C1, money-normalized walls in C17, and honest turnover weighting everywhere. Trivial collector change going forward; historical re-pull worth one attempt.

**P3. 龙虎榜 per-seat history.** `china_lhb` already scrapes per-name aggregates (6-week window). Extend to per-seat rows (branch names) and backfill from public archives (years available). Unlocks the actor-fingerprint family: known one-day-punter seats vs institutional seats vs 锁仓-style desks as continuation conditioners; §2.7's disclosure-absence signal; direct M2 lifecycle observation. This is the most mechanism-direct public dataset that exists.

**P4. Free-float share counts.** `china_holder_counts` already carries `total_a_shares` (2013→now, sparse disclosure cadence) — audit whether it approximates float; supplement with a float-history pull. Unlocks the v0-NULL turnover ratio, float-cap filters (every practitioner's first cut), wall/float and locked-volume/float normalization (C11, C13, C17). Also `avg_hold_num`/`holder_num` deltas are the direct 筹码集中 (chip-concentration) accumulation footprint for C5 — quarterly cadence limits it to slow confirmation, still worth wiring.

**P5. 9:25 auction snapshot for pool + watchlist names.** Tiny fixed-time daily scrape (matched volume, indicative price at 9:20 and 9:25). Converts C2's censoring into a measured fill model and adds the commitment-window (no-cancel) strength read (§2.9). No history exists anywhere — every day not collecting is lost; start now, accrue.

**P6. Delisted-name daily bars + ST membership history.** Kills the survivor caveat where it bites hardest (C9/C16 tails, M7 severities). `st_history` starts 2026-07-06 and accrues; delisted bars need a vendor pull — medium cost, prioritize delisted bars over ST tags.

**P7. THS concept (题材) membership snapshots, daily.** `snapshot_ths_concepts` already exists in the engine — schedule it daily and archive; concept-resolved history is expensive, but accrued snapshots make C6/C8/C15/C18 sharp within months. 题材 ≠ industry is the single biggest resolution upgrade for the relay constructions.

**P8. Regulatory event feed.** `china_inquiry` runs; add suspension/resumption notices and 减持 announcements (exchange disclosure pages). Unlocks C9's censoring cleanup and the run-killer hazard features (§2.7).

**P9. Cheap regime inputs already public:** aggregate margin balance (extend `china_margin_detail` upward / `china_margin` store), `china_connect` aggregate northbound (exists, ~11y) — feed C7 as slow covariates. Per-name northbound is dead post-2024 rule change; do not chase.

---

## 5. STRATEGY SHAPES

**S1. The relay book (接力 — core engine).** Universe: yesterday's seals (house tape live). Entry: day+1 open per C2's gap-budget surface, state = (N, species, leader rank, C4 verdict, C7 regime). Exits: C9 death-mode alarms, C8 leader-contagion switch, hard time stop (2-3 days without a new seal). Every position is an overnight hold by law — sizing prices the door-slam branch, not the mode.

**S2. The onset book (首板 capture at daily resolution).** C5 composite + C6 vacancy + C12 near-miss verdicts feed a next-open entry list of *not-yet-sealed* names — capturing first boards as a holder rather than paying the relay gap. Lower hit rate, better fills, and it buys the cheapest rung of the v0 ladder (16.5% → 36.6% escalation accrues to whoever owns the first board). Intraday 打板/半路 execution is a later program once P5 accrues.

**S3. The dip book (低吸 — churn-regime survivor).** C10 龙回头 + C3 回封 setups: buying weakness in proven names. Guaranteed fills, inverted adverse selection, and it is the only book that should trade in C7's churn state.

**S4. Portfolio mathematics.** Each candidate is a small-probability, high-convexity bet: typical loss −2 to −5% (open entry, same/next-day exit), fat left tail −10-20% (door-slam), win = +5-10% day-1 capped, with a convex continuation branch (a caught 4-6 board run pays 40-80%). The edge lives in the convex branch, so: size by full-distribution Kelly fraction (not hit rate), 5-15 concurrent positions from a daily candidate stream, per-name caps set by *fill reality* (participation limit as a fraction of typical open-auction volume — small names bound size fast), per-theme caps (C8 correlation is the dominant intra-book correlation), and a total ladder-height exposure cap (§2.10: all height is one trade against a regime break). Expect portfolio P&L to be lumpy-right-skewed; drawdown control comes from the throttle, not from per-name stops alone.

**S5. The regime dial as master throttle.** C7 state scales gross exposure: expansion = both books full; churn = S3 only; ebb = flat, full stop. The v0 era swing says the *same* signal carries 3× different potency by regime — trading through ebb is how this edge historically dies. Re-entry trigger: the space-opening tell (first new cycle-max height after a freeze, §2.5).

**S6. Execution-honesty ledger from day one.** Every backtest entry priced at the open with C2's censor; slippage haircut declared; once live probes begin, the paper-vs-fill gap is tracked per state and fed back into the gap budget. The strategy's true capacity question — can you actually get filled at the opens the model likes — is answered by P5's accruing auction data, not by assumption.

---

## 6. WHAT WOULD FALSIFY THE WHOLE THESIS

Space-level kill conditions — observations that would say the mechanism leaves no *ex-ante, daily-resolution, executable* footprint, as opposed to killing one construction:

**F1. The auction prices everything.** If, after conditioning on the day+1 open gap (C2), *no* state (species × height × regime) retains positive open-anchored expectancy in any era — the continuation ladder exists close-to-close but is fully absorbed by the gap — then the footprint is real but captured entirely at the auction, and no T+1-open strategy can monetize it. The program's daily-data form dies; only intraday sealing execution (a different program with different data) could survive.

**F2. Onset is invisible at daily resolution.** If the C5/C6/C12 onset family shows no era-stable lift beyond the v0 six, and the v0 six themselves collapse under open-executable accounting, then M2's build phase does not print in daily bars — pre-onset footprint requires order-level data we don't hold. (Per the ore law this kills the *daily-bar onset* space, not onset per se — it routes the program to P3/P5 or ends it.)

**F3. The ladder is a data artifact.** When P1 backfill arrives: if market-wide promotion rates sit materially below the curated slice's, and top-state open-anchored expectancies go non-positive on the full universe, the v0 escalation ladder was survivorship + curation, and the entire edifice rests on sand. This is the single most important external validity check the program owes itself.

**F4. Regime is unforecastable drift.** If C7's daily state fails to separate promotion rates out-of-sample — i.e., the 3× era swing is real but carries no measurable daily-resolution precursor — then the throttle (S5) cannot exist, position sizing inherits full era risk, and the portfolio thesis (small persistent edge × many bets) breaks: the edge would be episodic and unidentifiable ex ante, which for a capped-band, T+1-trapped book is uninvestable.

**F5. The tails eat the edge.** If C9/C16 death-mode tails, measured with delisted names restored (P6), are heavy enough that state-conditioned open-anchored expectancy nets negative across all continuation states at realistic fills, then continuation riding is structurally unprofitable at daily granularity regardless of hit rates — the band mechanism transfers wealth to whoever exits intraday, and daily holders are the exit liquidity.

**F6. Seal quality carries nothing.** If board species (C1) — the purest daily-bar print of seal quality — fails to rank continuation *within* height class in every era and band, then the premise that the board's character encodes information (load-bearing for most of §1-§3) is wrong at this resolution, and only the bare state variable (height N) survives — a much thinner program someone else has already arbitraged.

**F7. Legislated death (standing tripwire, not a measurement).** Announced T+0 settlement, band widening/removal on the main board, or a durable regulatory height-cap doctrine removes the mechanism's preconditions (T+1 forced holding + tight caps + pool salience). The program should carry this as a monitored kill condition at the *thesis* level: the edge is a creature of the microstructure, and the microstructure is a policy choice.

---

*Bias register carried by every construction: survivors-only raw slice (continuation and severity estimates biased favorable — direction noted per construction); 29% pool-name coverage (small-cap mechanisms muted; C7 uses ranks not levels); current-membership sector map applied to history (C6/C8/C15 historical results are lower bounds on concept-resolved versions); volume units unverified (prerequisite check before any volume-normalized construction ships); `seal_fund_yi` snapshot semantics unpinned (prerequisite for C17).*

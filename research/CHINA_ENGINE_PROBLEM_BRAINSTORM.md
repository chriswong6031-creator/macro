# China Equity Signal Suite — Problem Brainstorm (for Fable 5)

**Date:** 2026-07-01 · **Scope:** `china_stocks.html` (standout individual stocks + "what to act on now") and the China cycle/sector/basket family — `sector_central_china.html`, `baskets_china.html` (+ `baskets_china_ths.html`), `subsectors_china.html`, `sector_cycles_china.html`.

**Companion docs:** `research/ENGINE_PROBLEM_AUDIT.md` (the general 46-problem audit) + `research/ENGINE_FIX_MASTERPLAN.md` (W0–W7). This document is **China-specific and cross-page-coherence-specific** — it does *not* re-derive the general audit; where a China problem is an instance of a general theme, that is noted. The Signal-Passport primitive and the W1 Truth-Layer / grading rebuild from the masterplan are prerequisites for several fixes below.

**Method / provenance:** an 8-agent code audit (one specialist per subsystem + a cross-page-coherence analyst + a calibration/hit-rate analyst + a data-freshness analyst), a synthesis pass, and an adversarial red-team pass — 91 grounded problems total. Author (Opus) independently verified the coherence layer, the standout board, the benchmark split, and the fusion-layer status in code. **Solutions here are deliberately overview-level.** They are raw material: Fable should refute / agree / upgrade / expand with deep reasoning and novel twists. The most valuable section for Fable is **§8 (Tensions & Open Questions)** — several of the "obvious" fixes below are probably *wrong*, and the reasons are subtle.

---

## 0. The diagnosis in one causal chain

> The board **selects** individual A-share names with a US-validated **price-momentum** pattern (MACD-RSI × StochRSI confluence cascade, validated on 110 *US* names), then **overwrites** the displayed score with an **edge-less cycle-timing number** (`edge_mult=1` for CN), while the **one validated A-share edge** — 3-month within-sector reversal (Sharpe 0.58) — enters only as a **rank tiebreaker**. The five pages each recompute their **own** regime, **own** benchmark, **own** sector taxonomy, and **own** cycle label, so they routinely contradict each other. Every page also has a **self-grader** that measures its own hit-rate and **feeds nothing back**. The result: the surface a user acts on is optimized for the wrong return process (trend-follow on a mean-reverting tape), ranked by a timing score with no cross-sectional edge, presented as a flat 110-name list with the two real ideas invisible among the 108 — and the pages disagree, so a user can't triangulate.

Everything below is the anatomy of that sentence.

---

## 1. The eight systemic root causes

These are ranked by leverage. Each is code-grounded; the per-page detail is in §3.

### R1 — Graders exist but never close the loop (measure-but-never-act) — **master enabler**
Every surface has a self-grader — `china_standout_track`, `china_name_score_grader`, `china_sector_central_grader`, `subsector_track_record`, `china_sector_cycles` forward-log, `china_validation` — and **none is read back** into ranking, gating, or fusion weights. Blend constants are hand-set *in comments* (`_cn_bonus` 0.5/0.5, `CN_TIER_FRAC=0.30`, `CN_WN_FLOOR=0.60`), not fit to realized returns. Most graders are structurally stuck **"accruing"** (min-n 8/40; only the nightly lane persists; `china_validation` reads only as-of snapshots so n never crosses the bar). The system can *observe* that rank-1 beats rank-108, or that a tier grades below base rate, and does nothing. **Without this loop, none of the other fixes can be tuned or trusted.** (Instance of masterplan Theme B/G, but here it's total: no China surface consumes its own outcome ledger.)

### R2 — Selection runs on an unvalidated US momentum stack; the one validated edge is demoted/decorative
The actual selector everywhere is US-derived: the confluence cascade (US-fit), the US-SPDR `sector_signals` BUY/SETUP/TOPPING/SELL machine, the US anticipation cone, US-SPDR basket calibration. The validated China edges (within-sector reversal Sharpe 0.58; low-vol sleeve; washout-reclaim) enter only as tiebreakers inside a conviction composite that is then **overwritten** by `potential_score` with `edge_mult=1` (zero cross-sectional edge). China's own carve-out (`OVERSOLD_BOUNCE`) is hard-gated to 4 *US* defensive tickers and can never fire for a China name. **`china_reversal.py` Phase-0 found A-share momentum/breakout confirmation HURTS** ("you buy after the bounce; excess flips negative") — so the board selects on a signal research says loses money, and hides the one that works. **This is the mechanical cause of ~2/10.**

### R3 — No shared regime/gate object; each page maps macro→action independently (or not at all)
Two China regime engines coexist and never reconcile: `china_regime` (growth×inflation QUAD + PBoC-M2 liquidity + a crude early/mid/late `cycle_tag`) vs `china_masterminds.regime_state` (credit-impulse 0.45 / vol-regime 0.35 / margin-euphoria 0.20 de-risk tilt). `china.html` headline uses the QUAD; `sector_central` gates on the tilt with ad-hoc multipliers; **`china_stocks` applies NO board-level regime gate; `baskets_china` and `subsectors_china` consume neither.** Credit-impulse alone is reimplemented **3+ times** with different math. **A sector can read "AVOID" on `sector_central_china` while its member names show fresh T1/T2 "Standout buys" on `china_stocks` the same day.** *(Caution: §8 argues a shared de-risk gate may be actively wrong at the name level for a contrarian signal — this is a coherence problem, not automatically a "add one gate" fix.)*

### R4 — Same underlying series → multiple divergent "state" derivations, no canonical contract
The washout↔euphoria cycle position — the *only* Phase-0-stable China signal — is computed in **three** places (single Shenwan code vs 7-code composite vs desk `_last_pctile`), so "Consumption" carries different cycle numbers on the cycles card, the pathway block **on the same page**, and the sector desk. The same THS concept is built from **two different price stores** (dividend-adjusted `china_search` vs raw `china_stocks` OHLC) on sibling pages → contradictory signals from identical membership. **≥4 sector taxonomies** (16 Yahoo ETFs / 31 Shenwan L1 / 8 radar ETFs / THS concepts / membership baskets) mean "Semiconductors" is literally a different basket of stocks per page — a bullish sector call **cannot be traced** to names on another page even in principle.

### R5 — Lagging, confirmation-gated timing on a fast, mean-reverting tape
Entry/phase decisions lean on structurally-late inputs: weekly-MACD-confirmed 5-phase direction (0.4 of state), 22d-diff of a 252d-detrended double-EMA oscillator, **2W-Friday-resampled washout that can be ~10 trading days stale** yet is a ±0.5 top-rank mover, 200d-MA-slope-over-22d gating ENTER, calendar-3D bars with a 6-day fresh window offset from the trader's session grid, and **multiplicative single-point cycle triggers that zero a washed-out name until the lagging ladder flips**. A-share reversals are sharp; confirmed-turn gates put BUY near the middle of the up-leg — the exact failure Phase-0 warned about — and suppress the validated dip signal *precisely when it is freshest*.

### R6 — Fusion is either absent or an echo (correlated legs multiplied; orthogonal data siloed)
The two nominal fusion layers — `china_intel_bus`, `china_signal_stack` — are explicitly **display-only and feed nothing scored** (verified: `china_signal_stack` re-presents only *macro-regime* legs; it never touches the pick surfaces). Where fusion *does* exist it **multiplies co-derived technicals**: `subsector_confluence.combined_score = stock cascade × concept regime`, where the concept regime is the *same* MACD/StochRSI on an index *containing that stock* — one factor squared. Meanwhile genuinely orthogonal leading signals sit **unused**: `china_discovery` (LHB/block/buyback/attention leading-accumulation), the driver panel (southbound, margin ROC, breadth %>200d, credit-impulse), the cycle signature/pathway odds. **No component combines {regime, sector conviction, cycle phase, radar divergence, name signal} into one calibrated verdict.**

### R7 — Silent data-integrity & freshness holes upstream of every signal
Per-name drip caches (`margin_detail`, `valuation`, `zt_pool`, `comment`, `lhb`, `pledge`) bypass the run adapter and have **no staleness gate** — a GFW-blocked source freezes silently and renders as fresh. yfinance `auto_adjust=True` feeds **total-return closes** into level/limit-up/gap logic. THS truncated scrapes **fabricate mass membership removals**. The `china_search` universe is a **current top-N snapshot** (survivorship + look-ahead). Northbound flow is a **frozen placeholder** (dead since 2024-08) still assembled into the feature frame. yfinance chunk failures silently drop 30–40% of names, changing board composition for non-signal reasons. **These poison both the live signal AND the backtests used to justify it.**

### R8 — Boards are wide, flat, undifferentiated — no small high-confidence surface
Every page dumps its full population with no confidence floor and no top-few cut: `china_stocks` emits up to **110 buys** (6/sector cap), all identically styled; `sector_central` shows all **31 sectors + ~22 baskets** with only 4 carrying a validated forward leg; `baskets` shows 22 flat recos + a **237-basket THS page with zero reco desk**; `cycles` shows **53 series** each able to flash BUY; headlines use **incomparable confidence scales** (mean-confidence % vs agree/3 vs strength×reliability). Overlapping THS concepts double-count one hot name into 5+ rows. This doesn't lower *true* hit-rate so much as **realized user hit-rate**: the 2 real names are invisible among 108, so the average user picks the median — a high-variance contrarian name dressed as a "buy." *(Caution: §8 argues shrinking to 5 names may destroy the breadth that IS the edge.)*

---

## 2. Cross-page coherence map (the "they don't talk to each other" complaint, proven)

| Dimension | china_stocks | sector_central_china | baskets_china | subsectors_china | sector_cycles_china |
|---|---|---|---|---|---|
| **Regime source** | *none at board level* (per-name conviction/size nudge only) | `masterminds.regime_state` (credit/vol/margin) + `latest.json` quad | *none* | *none* (per-concept 220-bar state) | own Shenwan oscillator phase |
| **Benchmark** | CSI 300 (`510300.SS`) | SHCOMP (grader) | CSI 300 (`510300.SS`) | **SPY** (track record) / CSI300 (RS) | **SHCOMP** (`000001.SS`) |
| **Universe/taxonomy** | ~1.5k Sina search | 31 Shenwan + ~22 baskets | china_search + THS membership | THS concepts | 31 Shenwan L1 |
| **Cycle notion** | crude `cycle_tag` (early/mid/late) | desk 8-state ladder **+** card 5-phase (two labels, one page) | theme lifecycle `long_sign` | BUY/SETUP/TOPPING/SELL | oscillator phase + signature + pathway |
| **Data plane** | yfinance | yfinance + `latest.json` | yfinance | raw china_stocks OHLC | **akshare Shenwan** (serial, `stale_after_days=6`) |

**Verified, load-bearing findings:**
- **No shared regime.** ≥2 regime engines; only `build_china.py` builds the shared `latest` state — the other four build scripts never import it. Credit-impulse reimplemented 3+ times → "credit is easing" can read bull / neutral / bear the same day.
- **No shared benchmark** → "leadership"/RS is on different yardsticks: baskets vs CSI 300, Shenwan cycles vs Shanghai Composite. Per-surface excess/IC/hit-rate are **not fusable**.
- **The "Signal Stack" is decorative.** `china_signal_stack.py` docstring: *"DISPLAY-ONLY. Invents no new signal and feeds nothing scored"* — and it fuses only quad/growth/liquidity/RORO **macro** legs, never the stock/basket/subsector/sector *pick* surfaces. There is literally no engine that fuses the four pick surfaces into one verdict.
- **Cosmetic unification masks signal divergence.** `china_conviction.py` unifies the 0–100 *display band* ("High = High across surfaces") but **not the underlying inputs** — two pages can show matching "High" badges from *contradictory* reads, actively misleading the average user into thinking the pages agree.
- **Same THS concept, two indexes.** `subsectors_china` builds from raw `china_stocks` OHLC; `baskets_china_ths` from dividend-adjusted `china_search` closes — same `membership.json`, same benchmark, two different index levels, two different MACD/StochRSI cross timings.
- **Two cycle labels within one page.** `sector_central_china` renders the desk 8-state ladder (BOTTOM WATCH/DECLINE/RALLY ON) *alongside* the card 5-phase wheel (Trough/Recovery/Expansion) — a user sees "Prime entry" and "DECLINE" for one sector at once.
- **Confidence vocabulary is inconsistent** across pages (mean-confidence % vs agree/3 vs strength×reliability) rendered with similar UI language, so users falsely read them as comparable.

---

## 3. Per-page / per-layer problem inventory (condensed, grounded)

Severity in brackets. IDs match the audit dossier for traceability. Full 91-item index in the appendix.

### 3a. `china_stocks.html` — standout individual stocks + "what to act on now"
- **[critical] `gate-vs-edge-divorce`** — Board inclusion = the confluence cascade (US-validated), NOT reversal. Reversal is a tiebreaker inside a composite that is then overwritten. *`build_china_library` `eligible_rows` gate; `stock_score` CN selection axis 0.55·rev_z; overwrite at build L920-927.*
- **[critical] `displayed-score-not-the-edge`** — The big 0–100 "ready" number is `potential_score` with `edge_mult=1` → a pure timing/risk screen, zero cross-sectional edge, and it overwrites `conviction.score/band`. The biggest number the user reads carries no validated edge.
- **[high] `template-describes-dead-screen`** — Header/help/footer describe the OLD bottoming-alignment screen; the engine runs the cascade gate. The page misstates its own methodology. *(See §8: fixing the copy may cement a regression — the described screen may be the better one.)*
- **[high] `hitrate-computed-never-shown`** — `china_standout_track.grade` computes forward top-decile / rank-IC but is never rendered. The user's "is there a published hit-rate?" is effectively *no*.
- **[high] `no-regime-gate-on-board`** / **[high] `110-name-board-too-wide`** — No de-risk gate; up to 110 identically-styled buys.
- **[medium] `confluence-flag-16x16`** — "safer rebound" (reversal ∩ low-vol) badge is a 16×16 intersection (watch/sleeve still `top_n=16`) — the coverage bug is only half-fixed.
- **[medium] `washout-2w-lag`**, **`discovery-leg-orphaned`**, **`extension-close-only-blind`**, **`potential-trigger-single-point`** — lag + siloed orthogonal signal + limit-lock blind + single-point cycle veto.

### 3b. `sector_central_china.html`
- **[critical] `board-shows-all-31-no-confidence-filter`** — all 31 sectors + ~22 baskets, no confidence floor.
- **[high] `single-regime-scalar-no-sector-beta`** — one global regime scalar applied identically to all 31 sectors → it re-orders **nothing** cross-sectionally (Banks and Semis get the same gate despite opposite betas).
- **[high] `forward-tilt-only-4-of-31`** — only 4 sectors carry a validated forward leg; all 31 presented as comparable calls.
- **[high] `two-cycle-labels-one-page`**, **`regime-gate-not-shared-with-baskets-subsectors`**, **`phase-dir-hardcoded-lags`**, **`grader-not-fed-back-blind-fusion`**.
- **[medium] `confluence-of-3-includes-regime-twice`** — "agree/of-3" double-counts the global regime; state-only sectors get 2/3 by construction.

### 3c. `baskets_china.html` (+ `baskets_china_ths.html`)
- **[critical] `three-cycle-states-one-series`** — same EW series → lifecycle label + euphoria signature + BUY/TOPPING/SELL regime, unreconciled.
- **[high] `china-macro-leg-dead`** — macro/mtf/volhole legs (46% of designed weight) renormalize to zero for China → score collapses to 1-factor short-horizon momentum.
- **[high] `us-spdr-calibration-borrowed`** — signal-strength grade + THS regime states calibrated on 27y US SPDR data. *(May invert the true A-share reversal edge.)*
- **[high] `ths-no-reco-desk`** / **`no-ranked-confidence-surface`** — 237-basket THS page ships zero actionable signal; curated page shows 22 flat recos.
- **[high] `ths-overlap-double-count`**, **[medium] `ths-hindsight-single-snapshot`** (every "added" = SEED, no PIT history), **`spine-ignores-ths`**, **`ext-abs-tanh-latency`**, **`min3-members-thin-baskets`**.

### 3d. `subsectors_china.html`
- **[critical] `us-regime-machine-uncalibrated-china`** — US-SPDR state machine run verbatim on A-share concepts; the one China-appropriate branch (oversold-bounce) can never fire.
- **[high] `many-weak-legs-multiplicative-fusion`** — double-gate = the same MACD/StochRSI counted twice (self-confirming for thin concepts).
- **[high] `two-price-planes-same-concept`**, **`suspension-ffill-damps-ashare-tape`** (`close.ffill()` over suspended names freezes the index), **`no-china-track-record-grading`** (unlike US, never learns if calls work).
- **[medium] `fresh-window-plus-calendar-3d-lag`**, **`overlapping-concepts-double-count-picks`**, **`headwind-suppresses-genuine-china-reversals`** (A-share leaders run hot for long stretches), **`no-shared-china-regime-gate`**.

### 3e. `sector_cycles_china.html` + pathway
- **[high] `cycle-state-is-an-island`** — phase/signature/pathway odds feed **zero** of the stock/basket/subsector picks. The most theory-defensible China signal is disconnected while the boards surface names in sectors the cycle page flags as topping.
- **[high] `triple-signature-divergence`**, **`phase-direction-lag-daily-macd-vote`**.
- **[medium] `forward-log-never-graded`** ("accuracy over time" is asserted, not delivered), **`projection-uses-provisional-pivot`** (built off the still-open pivot), **`conditional-tercile-sample-fragility`** (Wilson CI fires on n=8 heavily-autocorrelated monthly obs), **`soft-gate-tolerates-sign-flips`** (lead-leg forward-IC can flip sign without failing the build).
- **[high] `average-user-surface-too-large`** — 31 sectors + 22 baskets × 5 sub-signals, no ranked shortlist.

### 3f. Calibration / grader loop (cross-cutting)
- **[critical] `grader-never-feeds-rank`**, **[critical] `no-confidence-cut-flat-110`**.
- **[high] `validation-perma-accruing`**, **`contrarian-signal-sold-as-buy`**, **`us-anticipation-gate-on-china`**, **`no-ensemble-across-surfaces`**, **`top-n-surface-buildable-today`**.
- **[medium] `three-benchmarks-uncomparable`**, **`standout-absolute-return-hitrate`** (absolute not benchmark-relative → beta-inflated), **`grade-thresholds-handset`**.

### 3g. Data / freshness (cross-cutting)
- **[critical] `drip-caches-no-staleness-gate`**.
- **[high] `yfinance-total-return-close`**, **`ths-truncation-fabricates-removals`**, **`no-pit-survivorship-universe`**, **`two-plane-asof-drift`**, **`regime-two-artifacts`**.
- **[medium] `monthly-macro-ffilled-as-fast`** (TSF/PMI/CPI ffilled up to 260 bdays, consumed as fresh), **`northbound-frozen-still-in-frame`**, **`asof-utc-vs-cn-session`**, **`breadth-vs-search-two-universes`** (gate calibrated on ~80 names, board runs on ~1.5k), **`coverage-drop-silent-signal-shift`**.

---

## 4. Which SIGNALS to improve, and why

1. **`china_reversal` (within-sector reversal, the one validated edge).** *Problem:* enters only as 0.55·rev_z, then overwritten; the "safer rebound" flag is a near-always-empty 16×16 intersection. *Direction:* promote to inclusion gate (top-quartile rev_z); compute the confluence flag from the full screened maps; fold rev_z into the displayed headline. *(But read §8 — the edge may be quarterly-basket-level, not daily-single-name.)*
2. **`signal_gate` cascade (US-validated) used as the CN inclusion gate.** *Problem:* selects on a US price-cross A-share research says loses money. *Direction:* demote to within-list anti-falling-knife ordering; require BOTH a buyable tier AND top-quartile rev_z for a "Standout" label; label cascade-only names "momentum entry (unvalidated on A-shares)."
3. **The two unreconciled regime gauges + triplicated credit-impulse.** *Direction:* compute each macro lead **once** in a shared `china_leads` module; persist ONE canonical regime object (quad + de-risk tilt + liquidity + asof); add a **per-sector regime beta** so the gate re-orders the ranking rather than just scaling the level.
4. **`china_discovery` leading-accumulation legs + driver-panel flow/breadth (orthogonal, leading).** *Problem:* purpose-built pre-consensus signal siloed as per-stock context. *Direction:* fuse a ≥2-leg discovery bonus into rank; add southbound/breadth/credit-impulse as **orthogonal** legs so "confluence" stops being one MACD factor squared. *(But read §8 — attention/LHB legs may anti-correlate with a contrarian edge; test sign first.)*
5. **`sector_signals` US-SPDR state machine on A-share concepts.** *Direction:* re-fit the 200d trend gate and extended/topping thresholds on CSI-300 sectors / THS history; make oversold-bounce eligibility China breadth/QVIX-driven; give explicit credit to oversold-reclaim.
6. **Freshness/latency legs** (2W washout, weekly-MACD phase, close-only extension, drip caches, total-return close). *Direction:* decay the washout bonus by bars-since-cross; blend a faster daily turn proxy into phase/trigger; ingest `zt_pool` 连板 count as a hard veto and turnover-shape to separate accumulation from blow-off; route drips through the run adapter with a consume-time staleness badge; store raw AND adjusted close (use raw for level/limit logic).

## 4b. Which MODELS to improve, and why

1. **`china_name_score.potential_score`** (the displayed 0–100 number). `edge_mult=1` → zero cross-sectional edge, yet it overwrites `conviction.score`. *Direction:* show two non-conflatable numbers — **Edge (reversal rank, validated)** and **Timing (entry)** — sorted by Edge; soften the hard multiplicative cycle trigger to a weighted leg so deep reversal fuel partially offsets an unconfirmed ladder.
2. **`china_sector_central._fuse / _regime_anchor`** — one global regime scalar re-orders nothing; confluence-of-3 double-counts regime; only 4/31 sectors have a forward leg. *Direction:* per-sector regime beta; confluence "of" = legs that actually exist per name; extend Wilson-CI pathway to more sectors; cap max tier without a forward leg; default to a "trusted picks" view.
3. **`theme_scoring.compute_theme_intel` (China variant)** driving basket recos — 46% of weight dead → 1-factor momentum; US-SPDR strength badge; lagging proxies; qualifies at 3 members; THS page has no desk. *Direction:* China theme-keyed macro prior (rates/growth/USD/commodity from `china_regime`); a China-available structural leg (cycle signature / breadth); China-specific calibration or drop the "backtested" badge; raise member floor; port the T1–T4 gate onto the THS page.
4. **`subsector_confluence.combined_score`** — one factor squared; no China track record; overlapping-concept double-counts. *Direction:* leave-one-out concept index for thin concepts; orthogonal legs (southbound, margin ROC, breadth, credit-impulse); fork `subsector_track_record` with `_BENCH=510300.SS` + China member prices; de-dup double-buy by ticker with an "also in N concepts" chip.
5. **`china_sector_cycles` / `china_sector_pathway`** — theory-defensible but an island; signature computed 3 ways; phase direction lags; projection off the open pivot; Wilson CI on n=8 overlapping monthly obs; soft-gate tolerates IC sign-flips. *Direction:* ONE canonical `position()` emitted to a shared per-sector state artifact, fed into the pick boards as a rank modifier/soft gate; confirmed pivots only; block-bootstrap CIs that show effective n; promote a persistent sign-flip to a hard gate.

---

## 5. The average-user remedy (the "10 signals, 2 work" fix)

**Core idea:** build ONE cross-surface **"High-conviction China"** card (cap ~3–5, *see the §8 caveat on size*) computed by a **new fusion layer that intersects agreement across pages** rather than re-presenting any single board. A name qualifies only when:
- **(a)** it sits in a **validated-edge slice** — top-quartile within-sector reversal rev_z **AND** washout-reclaim confirmation, not merely a cascade tier;
- **(b)** its sector reads constructive on `sector_central` **AND** the cycle page is Trough/Recovery (not Peak/Downturn);
- **(c)** the ONE shared regime gate is permissive — or, if de-risk, the card explicitly shrinks and flags "regime headwind, size small";
- **(d)** a leading **orthogonal** confirmer fires (`china_discovery` LHB/block/buyback/attention or driver-panel southbound/breadth).

Attach the honest `board_track` hit-rate ("X of last N top picks beat CSI 300 over 21d"). Default the average-user view to this small set; put the 110-name / 53-series / 237-concept walls behind an explicit **"power user" toggle**. Split the headline into **Edge** vs **Timing** so users can't conflate them, and **relabel the reversal board honestly** as a contrarian mean-reversion watch ("high-variance, size small") so a low per-name win rate is *expected*, not a broken promise.

**Every ingredient for a top-3 cut already exists per name; nothing assembles them.** *(But see §8: naive AND-gating collapses recall, and 5 names may be too few to realize a breadth edge — Fable should decide between AND-intersection, shrinkage-ensemble, and small-basket framings.)*

---

## 6. High-leverage bets (overview-level; Fable to refute/upgrade)

1. **Invert the china_stocks selection architecture** — validated reversal as the inclusion gate, cascade demoted to anti-falling-knife ordering, stop overwriting the displayed score; show Edge vs Timing. *Largest single lever on precision — but §8 disputes whether the edge survives at the daily-single-name unit.*
2. **Ship ONE canonical China state layer** — one regime object, one per-sector `position()`, one sector spine (Shenwan L1 authoritative + ETF/THS/membership crosswalk), one `china_leads` macro module — persisted once, read by all five pages. *Dissolves a whole class of coherence contradictions; prerequisite to any fusion.*
3. **Close the grader loop** — standardize all graders to CSI-300-relative forward returns, one maturity/significance policy; use realized per-rank-decile / per-tier hit-rate to set cutoffs; promote the anti-chase extension to a hard veto; shrink hand-set constants toward measured IC. *Compounding; converts asserted weights to earned ones. §8: fix the grader's own biases first (see below), or you feed back a biased signal.*
4. **Build a real cross-surface fusion → small "High-conviction China" surface** (§5). *Highest lever on **realized** user hit-rate.*
5. **Cut latency on the timing legs** — decay 2W washout by bars-since-cross; blend a daily/weekly turn proxy into phase/trigger; re-fit US-SPDR thresholds (incl. oversold-bounce eligibility) on China history.
6. **Fix the silent upstream integrity holes** — staleness-gate drips; PIT survivorship-free universe ledger; gate THS diffs on coverage; store raw+adjusted closes; drop suspended/frozen legs (suspension-ffill, northbound placeholder). *De-biasing, not additive alpha — but prerequisite to trusting any hit-rate.*
7. **Fuse the cycle clock into the boards + fix its statistics** — canonical cycle-position as a rank modifier (boost washed-out+turning, demote signature>85); confirmed pivots for projections; block-bootstrap CIs showing effective n.

---

## 7. Novel directions worth Fable's deep reasoning

Seeds that go beyond "fix the bug" — Fable should stress-test and invent around these:

- **Disagreement-as-signal, not disagreement-as-defect.** Instead of forcing one shared regime (single point of failure), let pages *disagree* and treat the disagreement as a **calibrated confidence input**. When sector-cycle says *Trough* but regime says *risk-off*, is that the highest-value contrarian setup or a trap? The graders can answer this **per historical instance** — mine it.
- **Empirical-Bayes / partial-pooling ensemble instead of AND-gates.** Every China subsystem is "many weak legs, tiny effective-N" — the textbook case for hierarchical shrinkage. Pool per-sector/per-leg estimates toward a China-wide prior weighted by each leg's *own* measured reliability and effective-N. Degrades gracefully to the prior instead of going dark (which AND-gating does when legs are lagging and inconsistent). *This directly consumes the graders that are currently discarded.*
- **Reframe the product unit.** The reversal edge is validated as a **~quarterly-rebalanced, EW-universe-relative basket with −37.6% per-name drawdown** — is a daily single-name "act now" surface even the right product for it? Maybe the honest artifact is a periodically-rebalanced **small-sized basket**, and the "act now" board is reserved for signals that genuinely operate at the name/day unit.
- **Fill-realistic ledger before any fusion.** Grade only *capturable* returns: mark a signal "unfillable" when the name gapped/locked limit-up at the reference close; enforce T+1 (earliest exit = next session). Measure how far the reported hit-rate drops. This is the single highest-value measurement to run *first*.
- **Hunt a fast, orthogonal replacement for dead northbound.** The suite has quietly lost its only fast, non-price-derived flow input (northbound dead since 2024-08); everything left is slow-monthly or price-derived — which is *why* the lag complaints are structural, not tunable. Candidates to rank by orthogonality-to-price and frequency: ETF creation/redemption, daily margin-balance velocity, southbound-as-sentiment, turnover-shape.

---

## 8. Tensions & open questions for Fable (the adversarial layer — read this first)

Several §4–6 "fixes" are the consensus view and may be **wrong**. These are the genuinely unresolved tensions; they are the most valuable thing to hand deep reasoning.

**Contrarian takes (where the obvious fix likely backfires):**
1. **"Make reversal the inclusion gate" may be wrong.** The edge is a quarterly-rebalanced, EW-universe-relative, sized-small basket with −37.6% drawdown that *buys weakness*. As a **daily single-name** gate it surfaces names in freefall with *worse* per-pick hit-rate than the cascade — and feels *more* broken. The cascade (unvalidated) may be doing real work: filtering still-falling knives the pure reversal signal would include. The honest design may be two-stage (reversal for the pool, a fast turn-confirmation for timing) — but Phase-0 says turn-confirmation *hurts* the edge. **Unresolved.**
2. **"Shrink to a small high-confidence board" may destroy the edge.** A cross-sectional skill signal derives its Sharpe from **breadth** (388 rebalances × many names). Concentrating to 5 names maximizes idiosyncratic variance — the fastest way to make a real-but-weak edge *look* broken over a user's short observation window. The honest product may be a *wide, small-per-name-sized basket* framed as "this is a portfolio, not stock tips" — the **opposite** of the unanimous UX recommendation.
3. **"Impose one shared regime gate on all pages" may make boards worse.** The de-risk regime keys on high realized vol / credit contraction — *exactly when the reversal edge is strongest (deepest dips)*. A universal de-risk **name-gate** suppresses the board when it should be most active. Regime belongs at the **sleeve-sizing** layer (how much total China risk), not as a per-name inclusion veto on a contrarian signal. And one shared regime = one wrong risk-off call propagating to all five surfaces at once.
4. **"Fuse in the discovery / LHB / smart-money leg" may anti-correlate with the edge.** 龙虎榜 and attention legs fire *after* a name moves; adding them to a signal whose thesis is "buy *before* the bounce" likely subtracts alpha. **Test for sign agreement with reversal before calling it a precision lever** — it may be a precision drain.
5. **"Fix the copy to match the cascade" may cement a regression.** The OLD bottoming-alignment screen the copy describes (weekly-not-still-falling falling-knife protection) is arguably *closer* to what a contrarian reversal board needs than the cascade that replaced it. The bug may be that the engine changed *away* from the better screen.
6. **"US-calibrated machinery is invalid for A-shares" is asserted, weakly evidenced.** Phase-0 killed *momentum-continuation*; it does **not** prove MACD/StochRSI *timing* patterns are harmful — only **untested**. Equally possible the honest answer is "A-shares have ONE thin edge (reversal) + regime sizing, and no engine work manufactures a second."
7. **"Publish the hit-rate to build trust" could backfire.** An honestly-computed, benchmark-relative, fill-adjusted, survivorship-corrected hit-rate of a daily single-name contrarian board may be genuinely *low* — surfacing it may correctly tell users the daily-single-name product doesn't exist. Trust-fix and product-viability-fix may be in direct conflict.

**Under-scoped gaps (things the audit found but likely *understated*):**
- **T+1 and limit-up unfillability are entirely unmodeled.** The only `limit_up` reference is a display badge "kept OUT of the score." Every ledger grades close-to-close returns that are often **uncapturable** (a deep-dip reversal name that bounces via limit-up gives a retail user zero fill). This is the single largest silent overstatement.
- **Survivorship is *maximally* destructive to the reversal signal specifically** — it buys the deepest decliners, which are the names most likely to be later delisted/ST'd/trimmed from the top-N universe. The bias is **not uniform across signals**; it deletes reversal's worst outcomes from both backtests and the forward ledger. "2 of 10" is likely **optimistic**, not pessimistic.
- **The graders themselves are mis-specified** (absolute not relative returns; 3 benchmarks; close-to-close on partially-unfillable names; survivorship-pruned forward universe; overlapping-horizon autocorrelation). **"Wire the grader back" on a biased grader could make ranking worse.** Fix the grader's five biases *before* closing the loop.
- **Cross-sectional factor exposure is unchecked.** The "diversified" 110-name board is probably a concentrated bet on one latent factor (beaten-down small-cap low-liquidity retail names — the T+1/limit-up-trap cohort). The 6-per-sector cap operates on labels, not realized covariance. Size/liquidity-neutralization may be the real precision lever.
- **Capacity / reflexivity.** A-shares are retail-dominated; surfacing the same beaten-down small-caps to many users is self-defeating at the exact light-mktcap tier the signal lives in.
- **PIT/leakage status of the *live board* is unverified** even though W1 just shipped a leakage-tax harness (commit `db8fae90ef`). Does it cover the live `china_stocks` feature path (rev_z, washout-2W, cascade freshness) at the as-of edge? **A leaky board would explain a good in-sample number that fails live — independent of every model-design issue above. Measure this first.**

**Ten questions for Fable:**
1. What is the correct **unit of product** for a Sharpe-0.58, quarterly-rebalanced, EW-universe-relative edge with −37.6% per-name drawdown? Is an honest *daily single-name* "act now" surface possible at all, or must it be a periodically-rebalanced small-sized basket? What is the minimum name-count below which the edge stops being statistically real for a user's horizon?
2. Can we build a **fill-realistic ledger** that grades only capturable returns (mark unfillable when gapped/locked limit-up; enforce T+1)? How much does the hit-rate drop? *(Measure before any fusion work.)*
3. Is there a decomposition where **regime governs sleeve sizing** while a **separate, faster, orthogonal** signal governs name-level timing, so the two never cancel? Or is A-share single-name timing intrinsically un-improvable given only close data (no intraday, no T+1 model, dead northbound)?
4. What is the best surviving **fast, orthogonal (non-price-derived)** A-share demand proxy to replace dead northbound? Rank candidates by orthogonality-to-price and frequency. Does adding even one break the structural lag?
5. Should coherence be **one shared regime object** (single point of failure) or an **ensemble that lets pages disagree** and surfaces the disagreement as a calibrated confidence penalty? Design the disagreement-as-signal architecture; when cycle says Trough but regime says risk-off, is that a setup or a trap — can the graders tell us, per historical instance?
6. Design an **empirical-Bayes / partial-pooling** scheme for the tiny-effective-N graders: shrinkage target, pooling strength, graceful degradation to the prior.
7. Does the reversal board's **realized factor exposure** reveal a concentrated bet on one latent factor? Is **size/liquidity-neutralization** the highest-leverage precision fix — and does it survive the T+1/limit-up capacity constraint at that liquidity tier?
8. Is there a genuine **second A-share edge** (so the product isn't a one-signal wrapper), or is the honest answer "one thin reversal edge + regime sizing, everything else is context"? Has low-vol / pathway / fill-adjusted washout-reclaim ever shown OOS cross-sectional skill *independent* of reversal on a survivorship-corrected PIT universe?
9. Would surfacing the same beaten-down small-caps to many retail users be **self-defeating via reflexivity**? At what user-AUM does the board move its own names — and does that argue for widening/randomizing the set or capping to higher-liquidity names (which Phase-0 says forfeits edge)?
10. **Before all of the above:** does the W1 leakage-tax harness cover the live china_stocks board feature path? If not, wire it there first and report the leakage tax.

---

## Appendix A — full 91-problem index by theme

| Theme | Problem IDs |
|---|---|
| **Grader loop never closed / weights hand-set / perma-accruing** | hitrate-computed-never-shown · grader-not-fed-back-blind-fusion · no-china-track-record-grading · forward-log-never-graded · grader-never-feeds-rank · validation-perma-accruing · grade-thresholds-handset · standout-absolute-return-hitrate |
| **Validated edge demoted; US momentum stack drives selection** | gate-vs-edge-divorce · displayed-score-not-the-edge · us-regime-machine-uncalibrated-china · us-spdr-calibration-borrowed · china-macro-leg-dead · us-anticipation-gate-on-china · contrarian-signal-sold-as-buy · template-describes-dead-screen |
| **No single shared regime / gate; regime not applied to boards** | no-regime-gate-on-board · regime-gate-not-shared-with-baskets-subsectors · single-regime-scalar-no-sector-beta · no-shared-china-regime-gate · two-regimes-no-reconciliation · baskets-subsectors-ungated · regime-gate-not-applied-to-list · regime-two-artifacts · gate-vs-quad-double-count-risk · signal-stack-anchor-single-leg |
| **Same series → divergent state; taxonomy & price-plane splits** | triple-signature-divergence · two-cycle-labels-one-page · three-cycle-states-one-series · two-price-planes-same-concept · four-plus-sector-taxonomies · signature-computed-twice · consumption-composite-vs-food-mismatch · basket-signature-percentile-window-mismatch · two-plane-asof-drift · triplicated-credit-impulse · radar-recomputes-price-rs-vs-cycles · confidence-semantics-mismatch |
| **Lagging, confirmation-gated timing** | washout-2w-lag · potential-trigger-single-point · phase-dir-hardcoded-lags · ext-abs-tanh-latency · fresh-window-plus-calendar-3d-lag · phase-direction-lag-daily-macd-vote · cycle-latency-monthly-shenwan · monthly-macro-ffilled-as-fast · projection-uses-provisional-pivot |
| **Fusion absent or an echo; orthogonal data siloed** | discovery-leg-orphaned · confluence-flag-16x16 · confluence-of-3-includes-regime-twice · many-weak-legs-multiplicative-fusion · cycle-state-is-an-island · fusion-layer-decorative · no-ensemble-across-surfaces · sector-bull-does-not-imply-name-bull · spine-ignores-ths |
| **Upstream data-integrity & freshness holes** | drip-caches-no-staleness-gate · yfinance-total-return-close · ths-truncation-fabricates-removals · no-pit-survivorship-universe · northbound-frozen-still-in-frame · asof-utc-vs-cn-session · coverage-drop-silent-signal-shift · ths-hindsight-single-snapshot · ffill-benchmark-stale · suspension-ffill-damps-ashare-tape · margin-detail-20td-window-approx · rs60-benchmark-reindex-nan-hole · desk-json-dependency-silent · curated-membership-survivorship-hindsight · signature-lookback-hardcoded-1260 · breadth-vs-search-two-universes |
| **Wide flat boards; no small high-confidence surface** | 110-name-board-too-wide · board-shows-all-31-no-confidence-filter · ths-no-reco-desk · no-ranked-confidence-surface · overlapping-concepts-double-count · average-user-surface-too-large · no-confidence-cut-flat-110 · board-too-large-no-top-few · top-n-surface-buildable-today · ths-overlap-double-count · min3-members-thin-baskets · forward-tilt-only-4-of-31 · momentum-confirmer-uses-rank-among-mixed-universe · overlapping-concepts-double-count-picks · headwind-suppresses-genuine-china-reversals · subsector-benches-spy-no-regime · extension-close-only-blind · soft-gate-tolerates-sign-flips · conditional-tercile-sample-fragility · three-benchmarks-uncomparable |

## Appendix B — canonical-contract shopping list (what "one shared layer" means concretely)

| Contract | Today | Should be |
|---|---|---|
| **Regime** | 2 engines (quad + masterminds tilt), unreconciled | ONE `regime_one_china` object: quad + de-risk tilt + liquidity + per-sector beta + asof |
| **Macro leads** | credit-impulse ×3, PMI/PPI/southbound ×N | ONE `china_leads` module, each lead computed once |
| **Sector spine** | 4+ taxonomies | Shenwan L1 authoritative + ETF/THS/membership crosswalk |
| **Cycle position** | 3 signature implementations | ONE `position()` → shared per-sector state artifact |
| **Benchmark** | CSI300 / SHCOMP / SPY mixed | ONE (CSI 300) for all China excess/IC/hit-rate |
| **Price plane** | yfinance total-return + akshare + raw OHLC | raw AND adjusted stored; raw for level/limit logic; one as-of edge |
| **Fusion** | display-only stacks | real ensemble consuming the graders → one confidence per name/theme |

# Entry-Stack Expansion — Masterplan (by Fable)

**Status:** RATIFIED PLAN — build not yet dispatched. Authored 2026-07-04 from a 16-agent verified census (8 sonnet lanes, each fact-checked by an opus adversary; 15 corrections applied), then red-teamed by a 3-lens opus panel (statistics/epistemics, house-law/integration, feasibility). All three verdicts: SHIP-WITH-FIXES; every blocker/major fix is integrated below and marked ⟦RT⟧ where it changed the design.
**Program owner:** Fable (main loop). Builders: Sonnet. Reviewers/judges: Opus. Per CLAUDE.md §Model routing.
**Prompted by:** external research doc (ChatGPT 5.5) proposing indicator-stack expansion beyond MACD+StochRSI, plus an Opus 4.8 assessment of it. Both were useful and both are corrected here against this repo's own falsification record.

---

## 0. Charter

> **In plain English:** Our validated buy signal (MACD+StochRSI confluence) tells us *when* momentum is turning. This program adds a small number of genuinely new, mechanically different sensors around it — a stop-run-reclaim trigger, an earnings-date safety veto, tradability/liquidity screens, a volatility-compression release trigger, and a fundamental-quality overlay for longer holds — and validates each one on *entry asymmetry* (how little a fresh entry draws down before it pays), not on long-horizon return prediction. Everything ships display-only until it earns weight under the existing species law. We explicitly do NOT re-test ideas this repo has already killed.

Scope: **US primary** (deep 224-name panel + 2,519-name basket store — the active-membership filter and its resulting count are cited in the W0 harness report ⟦RT⟧ — + massive-era cross-checks). CN secondary only where a species pre-registers its own CN test (CN gates historically kill mean-reversion edges). **HK/CA excluded by default** (every US bottom mechanism tested so far inverts or fails there — SETUP_SPECIES §HK doctrine).

Relationship to sibling programs (coordination contract in §8):
- **Setup Species (#1097)** — this program registers all new triggers as species under that constitution; no parallel taxonomy.
- **Entry Intelligence (#1302)** — owns replay-first standout upgrade + kernel-rank. We consume its replay shards when they land; until then our studies enumerate fires via `confluence_tiers.tier_stream()`. We do not touch its prefilter-bug workstream.
- **Oracle rotation** — owns sector-level lead-lag/routing. Our W4 propagation study is name-level within-cohort and must cite Oracle's P3/P8 verdicts as adjacent context.
- **Neural Web** — consumes our fires as spine engines and kernel cells (contract in §7); standing clock: kernel FDR sweep 2026-10.

---

## 1. What the verified census established (load-bearing facts)

| Fact | Evidence | Consequence |
|---|---|---|
| `data/stocks/` = 224 names, close/high/low/**volume**, NO `open`, up to 64y, dividend-adjusted total-return | panels lane; grading.py:32-34 | ADX/ATR/squeeze/OBV computable on deep history; gap features are NOT |
| `data/baskets/ohlcv/` = 2,519 names full OHLCV 2014+, adjusted; **only adjusted store with `open`** | panels lane; fetch_basket_ohlcv.py:19,116 | Gap studies run here; massive store (2021+, RAW unadjusted) is cross-check only — ex-div phantom gaps must be handled if ever used |
| `data/breadth/_closes_delisted.parquet` = 199 ex-members, close-only, 16,221 rows ⟦RT: full path pinned⟧ | panels lane | Delisted-aware checks possible for close-only species (U&R close-arm, S-EV); NOT for H/L-dependent species (S-SQ) |
| Fire enumerator EXISTS: `confluence_tiers.tier_stream()` (engine/confluence_tiers.py:297+), close-only | gate_fires lane; precedent scripts/validate_provisional_replay.py:149-165 | W0 does NOT build an enumerator, only a panel-sweep dumper. ~37k fresh T1-T3 fires on deep panel alone (AAPL: 194 fires/45y; 20-ticker mean 165.8). ⟦RT⟧ NOT fully vectorized (per-bar loops); measured 0.674s/11.5k bars ⇒ deep ≈ 2.5min, baskets ≈ 28min, massive ≈ 3.7h single-core — massive sweep is an optional multiprocess context lane, and `tier_stream` returns an EMPTY frame on any exception, so the dumper must log per-ticker fire counts + exceptions (silent-zero trap) |
| #1302's `replay_standout_pipeline.py` (production-fidelity, species-law-graded) is **UNRUN**; `data/replay/` has zero parquet shards; prefilter bug open | gate_fires lane + opus verify | Do not block on it; reconcile our tier_stream fires against replay shards when they exist (§8.2) |
| Spine is 16 dates old (1,086 rows; us_board 950 with `tier_cascade` all NULL) | gate_fires lane + verify correction | Historical evidence comes from offline studies, not spine; tier_cascade repair is a W3 hygiene item |
| Per-name options surface: skew 12 dates / iv-spread 5 dates vs 120 required; breadth fine (351-382 names) | options_depth lane | Derivatives-shape entry throttle = **ACCRUE-ONLY**, revisit ≈ 2027-01. Index-level vol series are deep (VIX 37y, VIX3M 20y, MOVE 24y, SKEW 36y) |
| `vol_squeeze.assess()` is SNAPSHOT-ONLY (one terminal dict); no series API; 10 nightly consumers | squeeze_series lane | W0 must add `assess_series()` before any squeeze study — with a fidelity pin (§6 W0) ⟦RT⟧ |
| Backtest-ready series today: ADX/DMI, ATR, bb_bandwidth, ttm_squeeze, OBV, CMF, choppiness, NR7, realized_vol (stock_technicals module fns) + 7 leak-free builders in advanced_indicators.py | squeeze_series lane | W0 series-ification list is short: BBWP/HVP percentiles, donchian_pos, rel_volume, obv_slope, squeeze states, + new primitives |
| Earnings: `data/earnings/earnings.parquet` upcoming (1,364 tickers, next_date, weekly Nasdaq drip, bot-wall risk; as_of 2026-06-19 — 10 business days stale at plan time, 32 next_date already passed ⟦RT⟧); `event_calendar.py` has ZERO earnings (macro-only); `event_blackout` exists in grading.REJECTION_TAXONOMY (grading.py:110) and **nothing emits it** | events_quality lane + RT verify | The earnings veto is a sanctioned-but-unwired slot. Live wiring needs PER-ROW staleness semantics (§3 F1) |
| ⟦RT BLOCKER FIX⟧ `data/edgar/eps_quarterly.parquet.asof_date` is **SYNTHETIC** — `period_end + 60d` constant for all 65,208 rows (std=0). `fundamentals_panel.parquet.asof_date` likewise `period_end + 120d` constant. **Neither is a real SEC filing date.** The census lane's "real filing dates overlaid" claim was WRONG (two independent re-measurements) | RT stats + RT feasibility, direct parquet measurement | S-EV's historical backtest needs a real announcement anchor: **EDGAR 8-K Item 2.02 filing dates** (repo already fetches/parses 8-Ks in guidance_gap.py). If that build fails, S-EV demotes to live-veto-only (forward-accrued). S-QL PIT language downgraded to "assumed 120d lag (not per-filer)" |
| Quality: EDGAR `fundamentals_panel.parquet` FY2009-2025, 1,331 names; **Piotroski (stock_fundamentals.py:397), Altman (:439), Sloan accruals (:568) already computed, display-only**; gross_margin coverage only 32%; analyst_revisions DEAD (no Finnhub key) | events_quality lane + RT verify | User's MACD+STOCHRSI+QUALITY hypothesis testable on positional horizons; quality defs restricted to full-coverage Piotroski/Altman in interaction arms ⟦RT⟧ |
| EOD liquidity/spread proxies: **ABSENT repo-wide** (Amihud/Corwin-Schultz/Roll: zero grep hits) | nw_liquidity lane | S-LQ builds from scratch; nearest analogue is China ADV tradability floor |
| NW new-engine contract: emit `SpinePrediction` rows (engine/spine.py:86-120; signal_id `{engine}:{as_of}:{symbol}:{horizon}`) or ledger+adapter in query.py:build_index (9 ledger sources incl. qledger pre-step); cells graded-only, deduped on (symbol,as_of); MIN_FAMILY_N=12, WILSON_MIN_N=12; quarterly FDR sweep gates any consumption | nw_liquidity lane + verify corrections | §7 wiring spec is concrete; display-first law binds |
| Trial law: register family + budget before first run (`@register_trials`); `data/trial_ledger.jsonl`; LEGACY_UNREGISTERED=33 frozen; walk_forward `_mt_bump` does NOT count as multiplicity control | harness_registration lane + verify correction | §5 pre-registers every family in this doc |
| ⟦RT⟧ Metric-definition split: `research/entry_timing/wave1.py` clean15 = **1.20 barrier + 0.97 durable-hold floor**; `engine/grading.terminal_state` CLEAN_LIFTOFF = **1.15 / 126d race**. Every cited incumbent effect (COILED +7.54pp etc.) was measured under wave1's definition | RT stats, direct code read | All program verdicts use ONE grader (grading.py); incumbent baselines are RECOMPUTED under it in W0 before bars freeze (RUL-9) |

---

## 2. The graveyard rewrites the priorities (correction record)

The external doc and the Opus assessment both proposed, as *first moves*, lanes this repo has already mined and killed. Recording the correction explicitly so no build agent re-walks the minefield:

| Proposed by ChatGPT-doc / Opus | Repo verdict | Binding source |
|---|---|---|
| Volume confirmation as entry confirmer (OBV slope, up/down imbalance, RVOL "sponsorship") — Opus backtest C, doc "high priority" | **FALSIFIED (H4)**: OBV-div, up/down ratio, capitulation spike, dry-up all sign-stable negative or noise as positive filters, deep panel W1 | SETUP_SPECIES §1.6; DURABLE_BOTTOM_FRAMEWORK.md:323 |
| Trend-alignment confirmers (rising MAs, higher-low, ATR-contraction location guards) — Opus backtest A "highest leverage" | **FALSIFIED** as per-event filters ("exposure artifact; killed on both held-DD and stop-out axes"); plus **CT-LANE**: counter-trend buyable fires NOT-WORSE than aligned (n=7,392, −0.16/−0.6pp) — alignment hard-blocks unjustified | §1.6 / CONFLUENCE_TUNING §5b; DURABLE_BOTTOM_FRAMEWORK.md:606 |
| VCP / calm-quiet-base arming (my own pre-census ledger had it) | **FALSIFIED (H2)**: fastest triggers from aged-quiet-base show worst stop-outs (46-48%) | §1.6; DURABLE_BOTTOM_FRAMEWORK.md:322 |
| Exit-rule work | **NO-GO** stands; EMA8 = tail-flag only; cut_fwd positive everywhere | §1.6 / CONFLUENCE_TUNING §8 |
| 52w-high × volume breakout alpha | **FALSIFIED** | §1.6 / NOVEL_IDEAS §3 |
| KST/multi-ROC, Fibonacci/Elliott/candlestick zoo | Skipped on collinearity/subjectivity grounds (no repo test needed; doc itself concurs on the latter) | this plan §9 |

**Two methodological laws these kills teach, now binding on every study in this program:**

- **R1 (exposure-artifact control).** Every stratum comparison must control for fire-date composition. ⟦RT: estimator pinned, RUL-12⟧ The registered estimator is a **date-fixed-effects stratified difference**: pool all fires, model outcome ~ stratum-indicator + fire-date FE (fallback era×sector-week FE only when date cells are too thin, granularity chosen ONCE per family at W0 sign-off), SEs clustered by episode block (fire-date ±10 bars within sector cohort), effect reported as the FE coefficient with block-bootstrap 95% CI. Post-hoc switching between FE granularities is banned. This is the exact control the trend/location-guard kill demands.
- **R2 (adjacency citation).** Every candidate must name its nearest falsified relative from §1.6 and state the mechanical difference in one sentence, in the species registry `adjacent_falsified` field, BEFORE first compute. Re-derivation of a graveyard idea = automatic wave failure (standing law).

Also inherited verbatim (standing doctrines, census-confirmed): display-only until earned (chip → ledger → graded bonus → gate weight); marker-date/same-bar-fill ban (+5.7pp/10d phantom); comparisons-not-absolutes under survivor bias; recall printed beside precision ("a filter that fires 5× less and wins by 1pp is a worse tool"); gates gut recall — new signals deploy as bonuses/chips, hard gates reserved for **hygiene only**; nightly is sole ledger advancer; every new store is git-added and wired into the sentinel's staging list (sentinel-staging-gap incident); BH-FDR q≤0.10 over the registered family with episode-clustered p-values.

---

## 3. The candidate book (verdict-tiered)

Each card: mechanism → nearest falsified relative (R2) → data → deployment lane → pre-registered expectation → kill line. Deployment lanes: **HYGIENE** (allowed as veto/gate), **CHIP/STRATUM** (display → bonus ladder), **SPECIES** (new independent trigger, registered under #1097), **KERNEL** (context feature for NW cells).

### Tier F — flagships

**F1. S-EV — Earnings-blackout veto (HYGIENE). The program's de-facto MVP ⟦RT⟧.**
Mechanism: a known binary event inside the stop horizon converts a timing edge into a coin flip; suppressing fresh entries T-3..T+0 before scheduled earnings removes variance we are never paid for. Not an alpha claim — a hygiene claim, the one category doctrine allows as a hard gate.
Adjacency: none falsified; `event_blackout` slot pre-sanctioned in REJECTION_TAXONOMY (grading.py:110), currently emitted by nothing. S9 (bad-news immunity, W3-queued elsewhere) is post-earnings reaction — different window, no collision.
Data ⟦RT blocker fix⟧: historical anchor = **EDGAR 8-K Item 2.02 dates** built in W1 (reuse guidance_gap.py's 8-K plumbing; keyless). The old plan's `eps_quarterly.asof_date` anchor is VOID (synthetic +60d). If the 8-K date build cannot reach ≥800 names × ≥8y, S-EV demotes to live-veto-only (forward-accrued hygiene, no historical verdict) and says so.
Live rule ⟦RT blocker fix, per-row semantics⟧: `veto iff (next_date ≥ today) AND (next_date − today ≤ k) AND (as_of within 10 trading days of today)`; rows with `next_date < today` are DROPPED (never veto on a passed date); both file-age and row-age stamped on the artifact; collector outage ⇒ fail-open (no veto) with a staleness banner, never a blocked board build.
Study: stop5/MAE/terminal-state delta for fires inside k∈{1,2,3} pre-announcement days vs the R1 estimator's matched baseline; **k=3 is the primary, k=1/2 sensitivity; era analysis runs on the pooled deep+baskets fire set** (per-era n at k=1 is unreachable on deep alone ⟦RT⟧).
Expectation: worse asymmetry inside window (close to mechanical); even a null is cheap knowledge.
Kill line: if inside-window fires are NOT worse on stop5 or mae63 (pooled FE CI includes 0 at k=3), do not wire; print the null.

**F2. S-UR — Undercut & Rally / spring reclaim (SPECIES, rotational).**
Mechanism: a break of a defined prior low runs resting stops and clears the seller queue; a fast reclaim (close back above the broken level within k bars) is direct evidence of absorption — demand strong enough to digest the flush. Enters *earlier* than oscillator confirmation, attacking the measured 11pp "oracle gap" (confirmation-wait cost, DURABLE_BOTTOM_FRAMEWORK.md:321).
Adjacency (R2) ⟦RT citation corrected⟧: the trap-context-veto *inversion* (serial failure as mean-reversion fuel) is **sign-stable but in-sample only** — the registry's S6 card records that the wave-2 recomputation never touched the OOS basket panel, and within STAR the increment is a wash (SETUP_SPECIES:595-601; DURABLE_BOTTOM:324 H5 shows +1.8pp). S-UR's case therefore rests on mechanism + never-studied status (census 3A), NOT on a validated neighbor. Shallow-dip falsification (the ugly side wins) remains supportive context. Nearest falsified relative: trap-veto (we operate its inverse); mechanical difference: we require the *reclaim event*, not the failure history.
Data: close/low(+volume optional) — deep panel (64y), baskets (12y), delisted close-only panel, massive-era cross-check.
**Frozen definition ⟦RT, no builder discretion⟧:** rolling low = `close.shift(1).rolling(N).min()`, N∈{21,63} (strictly prior — no pivot lookahead). Undercut = `low < rolling_low` on H/L panels; `close < rolling_low` on close-only panels. Depth arm = `≥ 1.0×ATR14` where H/L exist, ELSE `≥ 2%` close-only (panel-determined, never both; delisted panel is close-arm-ONLY; ATR multiplier frozen at 1.0 — not a tunable). Reclaim = `close > broken rolling_low` on any of the next k bars, k∈{2,3,5}, evaluated bar-by-bar, no same-bar fill. Forms: standalone; ∩COILED; ∩gate-fire within ±5 bars.
Expectation: standalone modest; **∩COILED is the prize** (washout context + absorption trigger = the complete mechanism story).
Kill line: species doctrine bar (§5) — non-inferiority + superiority against incumbent baselines recomputed under the program grader, dev AND holdout, recall ≥ half of COILED-FIRE's (recomputed); else falsified and buried with its parameters.

### Tier S — standard candidates

**F3. S-SQ — Squeeze-release trigger (SPECIES, rotational).**
Mechanism: volatility-regime transition — release from multi-week compression WITH direction and volume confirmation (the existing `vol_squeeze` FIRED_UP state: dual BBWP+HVP percentile gate, min_duration=5, release_window=3, vol_confirm=1.3×).
Adjacency (R2): H2 killed *calm-base arming* (anticipating inside quiet bases). S-SQ differs mechanically: it acts only on the **confirmed release bar**, direction-signed, volume-checked — confirmation vs anticipation. An "arming" variant is BANNED from the family (§9). The distinction must hold empirically or the species dies.
Data: needs H/L(+volume): deep panel + baskets; NOT delisted panel. Requires W0 `assess_series()` under its fidelity pin (§6).
Study: terminal states of FIRED_UP events vs R1 baseline; overlap with gate fires (independence measure); FIRED_UP∩gate intersection separately.
Expectation: genuine but modest standalone; the intersection is the likelier product.
Kill line: species bar; additionally if FIRED_UP co-fires >60% within ±3 bars of gate fires, it is not independent — demote to chip candidate at most.

**F4. S-LQ — Tradability & liquidity-deterioration screens (HYGIENE + KERNEL).**
Mechanism: entering a name whose effective spread is widening / depth thinning raises realized MAE mechanically (fills degrade, stops slip). Not alpha — cost physics.
Adjacency: none (census: zero EOD spread proxies repo-wide; nearest analogue is the CN ADV floor, a different construct).
Data: Amihud ILLIQ = |ret|/(close×volume) — all panels incl. deep; Corwin-Schultz HL-spread — panels with H/L. Both are new primitives (W0).
Study ⟦RT: band edges de-tuned⟧: bands are **cross-sectional terciles computed on the trailing year** (fixed rule, never fitted); deterioration = sign of the 20d slope (fixed window). Fire asymmetry per band via R1 estimator.
Expectation: floor-band effect (worst-liquidity tail carries fatter MAE); mid-range likely flat.
Kill line: if no band shows CI-excluding-0 MAE/stop5 degradation, ship nothing (no invented "liquidity tilt"); primitives still feed kernel context.

**F5. S-QL — Quality overlay on positional grades (STRATUM; the user's seed).**
Mechanism: entry timing is horizon-agnostic, but *what you hold after a good entry* determines 63/126d outcomes; profitability/accrual quality is the best-documented slow confirmer. Claim under test: MACD+STOCHRSI(+QUALITY) improves **positional** terminal states (clean-liftoff at 126d, dead-money), NOT entry MAE.
Adjacency (R2): CN quality floors on reversal HURT (falsified) — scope is US-only and *stratum*, never gate; US residual momentum falsified — this is fundamentals, not price momentum.
Data ⟦RT blocker fix⟧: Piotroski/Altman/Sloan already computed (stock_fundamentals.py:397/:439/:568) from EDGAR FY2009-2025. **PIT status: the panel's asof_date is an assumed flat 120d lag, not per-filer filing dates** — every S-QL artifact carries `pit_basis: assumed-120d-lag`; facts usable only ≥120d after FY-end by construction, which is the conservative side of the real Feb-March 10-K distribution for December FY-ends. ⟦RT⟧ Interaction arms (quality × washout-depth) restricted to full-coverage Piotroski/Altman — margin-dependent quality defs are banned (32% coverage would self-kill on n).
Study: same fires, positional grades stratified by quality tercile; interaction with washout depth as a secondary.
Expectation: modest positive spread on dead-money/clean-liftoff-126.
Kill line: no tercile spread with CI excluding 0 (pooled FE) replicated in sign on dev/holdout ⇒ print null, keep the existing display-only Piotroski chip as-is.

**F6. S-TS — ADX trend-strength residual question (STRATUM, expect-null).**
Mechanism: ADX measures trend *energy* directionlessly — mechanically distinct from the falsified direction/location guards; never studied here (census 3A).
Adjacency (R2): trend/location guards falsified (exposure artifact); CT-LANE not-worse. Both make the prior hostile; we run ONE date-matched stratification (ADX14 rising-vs-low at fire) to close the question the external doc keeps reopening.
Expectation: **pre-registered expect-null.** Value = a citable kill (or a surprise worth having).
⟦RT⟧ Non-null is defined ONLY as: pooled FE coefficient with BH-adjusted CI excluding 0. Single-era excursions are noise by pre-registration. Any non-null must then replicate on baskets OOS before even a chip is discussed.

### Tier D — demoted (allowed only if capacity remains; hostile-adjacent)

**D1. S-PP — Pocket pivot** (volume thrust off quiet base). Adjacent to falsified H4 (volume-as-positive-filter); differs by being an event (day-of thrust) not a state divergence. Appendix family only, after F-tier verdicts. Expect-null.
**D2. S-GP — Gap-and-hold** (breakaway gap out of base holding ≥2 closes). Never studied; needs `open` ⇒ baskets panel 2014+ only; massive cross-check with ex-div caution. Appendix, W4 earliest.
**D3. S-OH — Overhead-supply context** (distance-below-52w-high bands × time-underwater). `dist52` already a meta-label feature; 52w-high *breakout alpha* falsified but this is the drag/context claim. Free report column in W1 harness runs, report-only.

### Tier X — dropped / deferred (do not build)

- Volume-confirmation confirmers (OBV/CMF/RVOL strata) — H4, dropped. Volume appears ONLY inside S-SQ's release confirmation and D1's event definition.
- VCP-shape score — H2, dropped.
- KST/multi-ROC — collinear with the existing oscillator pair, dropped.
- Fibonacci/Elliott/candlestick taxonomy — dropped (subjectivity/multiplicity).
- True VWAP / volume profile / intraday order-flow — **deferred behind an explicit intraday-data decision memo** (separate from this program). Anchored-VWAP-on-daily considered and NOT included: on adjusted daily closes it degenerates into a washout-anchored MA, colinear with existing distance-from-low machinery.
- Per-name options-surface throttle (skew/IV-spread/GEX shape) — **accrue-only until ≈2027-01** (12-17 of 120 required dates as of 2026-07-02). Auto-revisit clause in §6 W5.
- Analyst-revision anything — data feed dead (no key). Out of scope.
- Index vol-state stratification — folded into the W1 harness as a free regime column (37y VIX depth), display/context only; NOT a gate candidate (vol_regime overlay already failed additive-value vs vol-target).

---

## 4. Where each survivor deploys (product surfaces)

| Candidate | Offline verdict artifact | If it earns: display | If it keeps earning: weight |
|---|---|---|---|
| S-EV | research/entry_stack/S_EV_REPORT.md + rejection-tag counts | `event_blackout` rejection chip on cards + suppressed-entry note on boards (EN/ZH, data-tip-* not title=) | Hygiene gate in `signal_gate` consumers (doctrine-legal) |
| S-UR | phase0 report + registry entry | "SPRING" chip beside COILED/STAR on standout boards | Ranking bonus à la COILED_BONUS after ledger maturation |
| S-SQ | phase0 report + registry entry | "RELEASE" chip (squeeze states already rendered on 5 markets' pages — reuse `vol_squeeze` consumers) | Bonus only; never gate |
| S-LQ | band report | Tradability footnote on cards; suppressed-tail list in QA page | Hygiene floor band if CI holds |
| S-QL | stratum report | Quality tercile chip on positional cards (Piotroski already displayed — outcome-linked framing ONLY if the validated-word gate passes) | Positional-horizon bonus |
| S-TS | kill/verdict note | none expected | none expected |

Every chip: bilingual, no translated `title=` attributes (CI guard), and **zero use of the word "validated"** unless `scripts/check_validated_claims.py` allowlist criteria are met by an artifact with `validated==true`.

---

## 5. Pre-registered validation protocol (binding numbers)

**Harness:** one new `scripts/research/entry_strata_phase0.py` (W0) consuming `data/research/gate_fires_{panel}.parquet` + primitive columns; grading exclusively via `engine.grading.forward_metrics` / `terminal_state` (T+1 fill; marker-date ban) — stop5, clean-liftoff (1.15/126 positional; 1.08/21 rotational), dead_money, mae63, mfe63, days_to_10.

**⟦RT⟧ One grader, recomputed baselines (RUL-9):** all cited incumbent effects (COILED, C2, H6, W8-B) were measured under wave1.py's clean15=1.20+durable-hold. W0 recomputes the incumbent baselines — gate-fire base rates, COILED strata, C2 recall — under **this program's grader** before any bar is read as met; wave1 numbers are cited as historical context only. Bars freeze at the W0 opus stats sign-off (RUL-7).

**Design controls:** R1 date-FE estimator (§2, RUL-12); episode-block bootstrap (cluster = fire-date ±10 bars within sector cohort); era splits {2012-2015, 2016-2019, 2020-2022, 2023-2026} on deep panel, dev/holdout ticker-halves on baskets; survivor caveat stamped on every absolute; delisted-close panel included for close-only species (S-UR close-arm, S-EV).

**Promotion bars (pre-registered; rationale stated ⟦RT⟧):**
- CHIP/STRATUM: n ≥ 400 date-deduped fires per stratum arm (pooled; era table reported); primary endpoint stop5 FE-coefficient ≥ 2pp with block-bootstrap 95% CI excluding 0; supporting MFE/|MAE| delta ≥ 0.10; sign-stable in ≥3/4 eras (pooled-panel eras where a single panel starves, as in S-EV); survives BH q≤0.10 within this program's registered family; and beats both null-competitors under the marginality test below. *Rationale: validated winners moved stop5 by ~5.5pp; 2pp ≈ one-third of that scale is the floor for the weakest deployable unit (a display chip), with multiplicity carried by BH + NC hurdles. The W0 reviewer may raise this floor at RUL-7 sign-off; it cannot be lowered.*
- SPECIES (trigger) ⟦RT: margin added⟧: n ≥ 150 deduped episodes; **non-inferiority with margin** on stop-out (CI lower bound > −1pp vs incumbent baseline, the WAVE4 C2 precedent) AND **superiority with CI excluding 0 on ≥1 of the three constitution axes** (stop-out / dead-money / cushion incidence); never return precision; recall printed and ≥ half of the recomputed COILED-FIRE recall; independence claim requires co-fire ≤60% within ±3 bars of gate fires.
- HYGIENE (S-EV, S-LQ): CI-excluding-0 degradation of the vetoed set on stop5 OR mae63 (pooled FE, k=3 primary for S-EV); vetoed volume ≤10% of fires (a hygiene rule that eats recall is a gate in disguise).

**Null-competitors (mandatory, run in W1 before any candidate verdict is read):**
- NC-1: tier-subsetting/freshness-tightening of the existing gate (T1-only; ticks=0-only) — does simple subsetting already buy the claimed asymmetry?
- NC-2: the existing calibrated `entry_quality` composite (cycles.py:1694 proximity+freshness bands). ⟦RT: marginality operationalized⟧ A candidate "beats NC-2" iff its stratum coefficient retains a CI-excluding-0 **after entry_quality-band fixed effects are added** to the R1 model (marginal value, not parallel value).

**Trial-ledger pre-registration (family → declared budget, itemized basis; all thresholds frozen in this doc are counted once):**
| Family | Budget | Itemization |
|---|---|---|
| `esx_null_competitors` | 6 | 2 NC × 3 panels |
| `esx_ev_blackout` | 9 | k∈{1,2,3} × 3 panels (k=3 primary) |
| `esx_ur_phase0` | 36 | 2 lows × 3 reclaim windows × 2 depth-arms (panel-determined) × 3 forms; ATR mult frozen 1.0 |
| `esx_sq_phase0` | 12 | frozen state grid × 2 panels × 3 forms + 3 named sensitivities (pctile_thresh=20; release_window=2; vol_confirm=1.5) |
| `esx_lq_bands` | 12 | 2 proxies × 3 fixed-tercile bands × 2 panels |
| `esx_ql_overlay` | 12 | 3 quality defs (Piotroski, Altman, Sloan-tercile) × 2 horizons × 2 forms |
| `esx_ts_adx` | 4 | 1 def × 2 panels × 2 era-splits |
| `esx_appendix` (D1/D2/D3) | 24 | capped; unlocked only after F-tier verdicts filed |
| **Total declared** | **115** | BH q≤0.10 applied per family; program-level summary printed in each report |

Nulls are printed, never hidden; every report carries recall beside precision. Failed candidates go to the graveyard with parameters (§1.6 update PR at each wave close).

---

## 6. Waves (PR-sized; model-routed; each wave gated on the previous verdict)

**⟦RT⟧ W0 is the critical path** — heaviest compute + review lift, and everything gates on it. Do not treat it as a warm-up.

**W0 — Foundations (5 PRs; Sonnet builds via `builder`, Opus reviews via `reviewer`).**
- PR-A1 `engine/entry_primitives.py` part 1: series-ifications of existing leak-free builders (bbwp_series, hvp_series, donchian_pos_series, rel_volume_series, obv_slope_series, atr_pct_pctile_series, dist_52w_high_series, time_underwater_series) + fixture tests. Low-risk; `effort: low`.
- PR-A2 part 2: new primitives (amihud_series, corwin_schultz_spread_series, undercut_rally_events per the frozen F2 definition, pocket_pivot_events + gap_hold_events [dormant, appendix-locked]) + shift-audit leak-tests on every function.
- PR-A3 `vol_squeeze.assess_series()` ⟦RT fidelity pin⟧: spec = *reproduces scalar `assess()`'s state/fired_dir on every truncation*; known-answer test replays `assess()` on ≥50 truncations of a fixture and asserts equality (mirror of the existing tier_stream↔cascade pin). Library builders keep calling snapshot `assess()` — `assess_series` is offline-only until a benchmarked PR proves its render-path delta (§ W3).
- PR-B `scripts/research/dump_gate_fires.py`: tier_stream sweep → `data/research/gate_fires_{deep,baskets}.parquet` (+ optional `massive` context shard). ⟦RT⟧ Budgeted honestly: deep ≈ minutes, baskets ≈ ~30min single-core, massive ≈ 3.7h single-core ⇒ multiprocess + resumable + per-ticker fire-count and exception log (tier_stream's empty-frame-on-exception makes silent zeros otherwise). Offline lane; store git-added + sentinel staging list updated in the same PR.
- PR-C `scripts/research/entry_strata_phase0.py` harness (R1 estimator + §5 bars baked in; `@register_trials` on every family; prints recall, survivor stamps, era table, BH panel, NC marginality test) + **incumbent-baseline recompute** (RUL-9). Opus stats review REQUIRED; thresholds freeze at sign-off.
- Gate to W1: harness passes a synthetic-fixture known-answer test + review sign-off.

**W1 — Null-competitors + hygiene + residuals (studies only, no product change).**
Run order: NC-1/NC-2 first (their table is the yardstick in every subsequent report); then the S-EV historical build (**8-K Item 2.02 date collector task first** — reuse guidance_gap plumbing; coverage gate ≥800 names × ≥8y else S-EV demotes to live-only) and k-grid study; S-TS single-shot; S-OH + index-vol-state as free report columns. Verdict doc per study under research/entry_stack/. If S-EV confirms → W1.5 ship PR: `event_blackout` emitter with the per-row staleness rule (F1), chips, sentinel staging.

**W2 — Trigger species + screens (the core; most-likely-to-stall wave ⟦RT⟧ — species studies are strictly serialized behind their registry entries, and n-bars collide with rare-fire reality here).**
S-UR phase0 (register species FIRST: registry entry with corrected adjacent_falsified + fixtures + ledger binding, status phase0); S-SQ phase0 (after registering, citing H2 distinction); S-LQ bands; S-QL overlay (with `pit_basis: assumed-120d-lag` stamped). Each = one study PR + one report PR. Survivors transition phase0→accruing via `sr.transition_validation_status` with reviewer sign-off (monthly review law).

**W3 — Ship + Neural Web wiring (only for survivors).**
Display chips (EN/ZH, i18n guards); forward-ledger emitters on the nightly (nightly-only advancement; keep-FIRST PIT); spine adapters: `adapt_confluence_fires` (historical tier fires as engine `confluence_gate`, family `confluence:T{n}`) + per-species emitters (`spring`, `squeeze_release`); repair us_board `tier_cascade` NULL (coordinate #1302 — one-line fix PR into their lane if unclaimed); `config/synapse.yml` entries (CI: check_synapse_registry); kernel cells accrue display-first (MIN_FAMILY_N=12; consumption forbidden until the quarterly FDR sweep passes — 2026-10 clock).
⟦RT⟧ Render-budget law, made concrete: **library builders keep snapshot `assess()` unchanged**; any nightly addition ships with a measured wall-clock benchmark in the PR body as a **gate** (target ≤ +30s on the 67-min render), else the artifact moves off-path (offline script or R2).

**W4 — Exploratory extensions (capacity-gated).**
Leader-follower within-cohort propagation study (first gate-fire in cohort → follower fire quality; cites Oracle P3 ONSET-tier + P8 W2 cond_b as adjacent priors; display-only graph edges via existing lead-lag records); meta-label v2 (existing meta_labeling_entry harness + surviving primitives as features; purged CV as-is); D1/D2 appendix families if unlocked.

**W5 — Promotion & clocks.**
Monthly species reviews (status moves only there); quarterly kernel FDR alignment; **auto-revisit: options-surface throttle study when the skew ledger holds ≥120 dates (≈2027-01)**; program retro; graveyard updates; memory + MEMORY.md index updates.

⟦RT⟧ Estimated shape: **17-21 PRs** (W0:5, W1:3-4, W2:5-6, W3:3-4, W4:2-3, W5:1). W0 dispatchable immediately under ultracode (builder/reviewer routing already legal per hook). If only S-EV survives its study, the program still ships a real product (the MVP) — that floor is accepted and named.

---

## 7. Neural Web integration spec (the "which sensor, when" layer)

The external doc's one deep-true claim — *learn which sensor matters, for which asset, at which horizon, in which regime* — is literally the kernel's cell design `(engine, regime_bucket, horizon)`. This program feeds it properly:

1. Every surviving trigger/hygiene sensor becomes a spine engine emitting `SpinePrediction` rows at fire time (contract of §1; size_binding=False; meta carries tier/sub/definition-version).
2. Historical backfill: one-time adapter emission from the W0 fire dumps, marked `version: backfill-v1` — analysis-grade, distinguishable from PIT-clean live rows.
3. Kernel cells accrue display-first; nothing consumes `shrunken_ic` until the quarterly FDR sweep passes (PR2 law). Event floors: MIN_FAMILY_N=12 / WILSON_MIN_N=12 — with U&R firing ~an order of magnitude rarer than gate fires, per-regime cells will take quarters to arm; the plan accepts this and does NOT manufacture pseudo-events.
4. Confluence graph: co-fire lift edges (gate×S-UR, gate×S-SQ, COILED×S-UR) via existing spine_index machinery — display_only=True until earned.
5. LLM law unchanged: models may de-escalate calibrated keys only; no LLM originates any of these signals.
6. **Event-budget doctrine (new, this program):** sensors compete for a fixed graded-event budget; a candidate whose expected fire rate cannot reach MIN_FAMILY_N per (regime×horizon) cell within 2 quarters of live accrual must justify existence at coarser cell granularity (engine×horizon only) or not ship a kernel lane at all.
7. ⟦RT: cross-artifact double-count guard, RUL-11⟧ The quarterly FDR sweep and any confluence-lift edge must EXCLUDE `backfill-v1` rows drawn from a fire-set already counted in a phase0 verdict — the same historical fire never testifies twice (once in a study, once as "independent" kernel/graph evidence).

---

## 8. Coordination contract

- **8.1 #1097 species law:** all registrations/transitions through `engine/species_registry.py` APIs; monthly review is the only status mover; falsified is terminal.
- **8.2 #1302 replay ⟦RT: legal encoding⟧:** our `dump_gate_fires` output is analysis-grade. When replay shards (`data/replay/replay_{year}.parquet`) land, W3+ verdicts re-reconcile. A chip whose effect does not replicate on production-fidelity fires within CI is handled with LEGAL registry moves: `validation_status` stays `accruing`, `deployment_status` reverts chip→`unshipped`, `gating.come_back_on` set to the adjudication date, and the replay-mismatch recorded in the gating note. (The registry enum has no "frozen" state — VALID_VALIDATION_STATUSES is {phase0, accruing, validated, falsified, retired}; we do not invent a sixth.) We do not modify replay_standout_pipeline.py or its prefilter fix.
- **8.3 Oracle:** name-level propagation (W4) files its pre-registration referencing P3 adjudication (confirmed-tier NULLs; ONSET-tier edge) to avoid double-counting the same rotation phenomenon.
- **8.4 Git/ops law:** every PR from fresh origin/main worktrees; same-day squash-merge; no bare stash; new stores git-added AND appended to the sentinel's staging list in the same PR; "Workers Builds: macro" red X ignorable; intraday lanes never advance ledgers.

---

## 9. Risks & non-goals

| Risk | Mitigation |
|---|---|
| Multiplicity creep across 8 families | Single program-level trial table (§5), BH per family, appendix capped + locked behind F-tier completion; every frozen threshold counted once |
| Survivor bias flatters absolute rates | Comparisons-only verdicts; delisted panel for close-only species; stamps everywhere |
| ⟦RT⟧ Synthetic asof_date resurfaces as fake PIT confidence | §1 fact row; S-EV re-anchored on 8-K dates or demoted to live-only; S-QL stamps `pit_basis: assumed-120d-lag`; no artifact may describe asof_date as a filing date |
| ⟦RT⟧ Earnings live veto: per-row staleness (passed next_date; unrefreshed rows) | F1 per-row rule: drop passed dates, veto only fresh in-window rows, dual age stamps, fail-open + banner |
| Squeeze study quietly re-derives H2 | Release-bar-only definition frozen pre-run; an "arming" variant is BANNED from the family |
| ⟦RT⟧ assess_series diverges from scalar assess() semantics | PR-A3 fidelity pin: truncation-replay equality test, ≥50 known answers |
| Massive store unadjusted OHLC (ex-div phantom gaps) | Gap studies on adjusted baskets panel only; massive = cross-check with ex-div exclusion note |
| ⟦RT⟧ Silent-zero fire dumps (tier_stream empty-frame-on-exception) | PR-B per-ticker fire-count + exception log; zero-fire tickers explicitly listed |
| Kernel cells starved by rare species | §7.6 event-budget doctrine; coarser cells or no kernel lane |
| Program duplicates #1302 replay | §8.2 reconciliation clause; consumption not construction |
| ⟦RT⟧ W0 stalls the whole program | W0 named critical path; PR-A split 3-ways; massive sweep optional; harness fixture test is the only W1 gate |

Non-goals: predicting long-horizon index returns; any intraday data purchase (separate memo); HK/CA ports; exit-rule revival; touching allocation/sizing anywhere.

---

## 10. Rulings (citable by build agents)

- **RUL-1:** Volume-confirmation confirmers are DEAD (H4) — no W1/W2 family may include them; volume appears only inside S-SQ release confirmation and D1's event definition.
- **RUL-2:** Every stratum study runs the R1 estimator and cites adjacency (R2); a study lacking either is invalid regardless of result.
- **RUL-3:** Null-competitors NC-1/NC-2 run first and appear as the first table in every W1/W2 report; NC-2 marginality = coefficient survives entry_quality-band fixed effects.
- **RUL-4:** S-EV is the only candidate permitted to target a hard gate, and only under hygiene semantics with the F1 per-row fail-open rule.
- **RUL-5:** Trigger species register (with adjacent_falsified + fixtures) BEFORE first compute; expect-null studies (S-TS) pre-register the null as the expected outcome, with non-null defined as pooled BH-adjusted CI excluding 0 only.
- **RUL-6:** Derivatives-shape throttle is accrue-only until the skew ledger holds ≥120 dates; the W5 auto-revisit is the only path back.
- **RUL-7:** Thresholds in §5 are frozen at W0 review sign-off (the reviewer may RAISE the CHIP floor, never lower it); any later change requires a new ruling logged here, never a silent edit.
- **RUL-8:** Backfilled spine rows carry `version: backfill-v1` and are excluded from any live-accrual claim.
- **RUL-9 ⟦RT⟧:** One grader per program: all candidate AND incumbent-baseline numbers are computed under `engine.grading` definitions; wave1-era numbers are historical context only and may not satisfy a bar.
- **RUL-10 ⟦RT⟧:** Replay-mismatch handling uses only legal registry moves (accruing + deployment revert + come_back_on); no new lifecycle states.
- **RUL-11 ⟦RT⟧:** No fire testifies twice: FDR sweeps and confluence edges exclude backfill rows whose fire-set already produced a phase0 verdict.
- **RUL-12 ⟦RT⟧:** The R1 estimator is the date-FE stratified difference with episode-clustered SEs and block-bootstrap CIs; FE granularity fixed once per family at W0 sign-off; post-hoc granularity switching is banned.

*Filed by Fable, 2026-07-04. Census run wf_97b99a75-1ca (16 agents). Red-team: 3 opus reviewers, all SHIP-WITH-FIXES, fixes integrated. Build dispatch awaits ultracode session.*

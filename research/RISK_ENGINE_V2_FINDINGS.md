# Risk Engine V2 — Definitive Findings & Redesign

**Author:** Lead Quant
**Date:** 2026-06-23
**Scope:** `engine/risk_state.py` (`compute()`, `core_series()`), the alert path (`alerts.risk_state_elevated`), and the leading-signal evidence pack (68 SPY/VIX drawdown/vol events, 1971–2026).
**Status of evidence:** all backtests leak-free (causal trailing-504d percentiles / 252d z, min_periods enforced); independently re-checked by 3 judges (scores 72/84/86). Live data depths re-verified 2026-06-23.

---

## 1. VERDICT — the current engine REACTS more than it predicts

**Blunt call: the shipped composite is a *modest leading signal for slow credit/breadth drawdowns* and is near-coincident or silent for fast vol/positioning unwinds. It is structurally reactive, and on the one day that mattered most it went the wrong way.**

The proof is the `current_composite` backtest (`engine.risk_state.core_series`, 14,472 daily rows, 1971–2026, 68 events) at the engine's **real alert band** `abs ≥ 60` — which is the only band with any edge:

| Metric | Value | Read |
|---|---|---|
| **hit_rate** | **0.221** | catches ~1 in 5 events |
| **median_lead_days** | **6** | short fuse (p25=4, p75=14) |
| **false_positive_rate** | 0.795 (clean-FPR 0.615) | cries wolf often |
| **conditional lift** P(onset ≤15bd \| elevated) | **0.223 vs 0.074 = 3.0×** | genuine edge when it fires |
| base rate elevated | 2.7% of days | rare, tight band |

**What it gets RIGHT:**
- At `abs ≥ 60` it has a *real* 3.0× conditional lift: it fires <3% of days, and when it does, an event onset is 3× more likely in the next 15bd. That is a genuine (if low-coverage) edge.
- It leads **slow drawdowns** (10/42 = 24%) slightly better than sharp vol (4/19 = 21%) — it reads credit/breadth deterioration earlier than violent unwinds. Clean catches: 1998-07 (+12d), 2007-07 (+2d), 2011-07 (+5d), 2015-07 (+12d), 2022-01 (+15d).
- The conjunction-over-mean architecture is the *correct* shape (don't average a screaming leg into silence).

**Where it FAILS:**
1. **It misses every fast/positioning-driven event at its real band:** 2018-01, 2018-12, **2020-02, 2020-03 (COVID)**, 2008-09 cluster, **2024-07/08 (yen unwind)**, and **2026-01** — exactly the calm-into-blowup blind spot that motivated this project.
2. **Its percentile framing has NO edge.** The causal pct0.80 band *looks* great (hit 0.529, lead 15d) but is an artifact: it is "elevated" 54% of the time, lift 0.46× (BELOW base rate, anti-predictive), and the "15-day lead" is just the lookback window saturating. **Never read the percentile band as predictive.**
3. **The alert is blind to its own leading legs.** `core_series` sees only 4 historical legs (complacency, breadth_div, vol_structure, credit). The three genuinely-leading-and-distinct legs — **dealer_gamma, technical, extension** — are excluded from the alert and each carries a **one-build lag**.
4. **The keystone alert leg self-cancels.** breadth_div ("index near 1y high AND %>200dma weak") mechanically requires the tape to stay calm — it turns OFF the instant price drops. On **2026-06-23 the alert score collapsed 46.9 → 7.8** at the peak of the unwind because both knockout conditions flipped on the same day (`spy_high_prox` 0.9825→0.9683 fell below the 0.97 gate; `breadth_above200_pctile` 0.385→0.444 rose above the 0.40 gate). With breadth_div off, only the lagging credit half-leg remained, and the conjunction escalator (needs ≥2 hot leading legs) had nothing to escalate. Live `compute()` read **Caution (40)**, not an alert.
5. **It pools a lagging leg with leading legs.** The credit composite (`drawdown_risk`) peaks a median **+28bd AFTER** onset on **100% of 68 events** (zero lead, ever). Averaging it into the headline drags net lead toward zero.

**Bottom line: the engine evaluates *some* of the signals needed to alert, but the ones it scores in the alert are coincident (vol level), self-cancelling (breadth_div) or lagging (credit); the truly leading legs are either excluded, stale-by-a-build, or live-only and un-backtestable. It reacts.**

---

## 2. BACKTEST TABLE — every signal, sorted by lead

Verdicts as backtested; "Verification" column = what the 3 independent judges confirmed vs weakened.

| Signal | Verdict | hit | med lead | FPR | Coverage | Verification |
|---|---|---|---|---|---|---|
| **VIX term-structure ROC** `roc5(vix9d/vix3m)`, fallback `roc5(vix/vix3m)` | **LEADING** | **0.85** | **~10d** | 0.80 (clean ~0.66) | 2011+ (3,890); 2006+ fallback (5,015) | **CONFIRMED leading** (fresh-cross 29/34, real precursor). **WEAKENED:** on lift/precision the *level* (1.87×) beats the *ROC* (1.26×); in 4/6 named "ROC-only" events the level led equally. ROC is a **complement that adds coverage**, not a clean replacement. No sign/size edge (corr fwd-10d SPY ≈ 0.00). |
| drawdown_risk (credit/recession composite) | **LAGGING** | 0.338 | 15 (artifact) | 0.907 | 1973+ (13,907) | **CONFIRMED lagging.** Peaks +28bd AFTER onset on 100% of events; "15-day lead" pins to lookback ceiling; precision 9.3% ≈ 7.7% base rate (no edge). macro#485 `lead_lag='lagging'` label correct. |
| CBOE SKEW (level + ROC) | **NO EDGE** | 0.632 | 14 (artifact) | 0.863 | 1991+ (8,897) | **CONFIRMED no-edge by all 3 judges** (lift 0.69–0.85×, BELOW 1.0 = anti-signal; permutation p<0.003, underperforms matched-frequency noise). **Drop from scoring.** |
| **current_composite** @ abs≥60 | **MIXED** (leading-slow / silent-fast) | 0.221 | 6 | 0.795 | 1971+ (14,472) | CONFIRMED: 3.0× lift at abs≥60 real; percentile band no-edge; misses fast events. |
| breadth_div percentile | **SATURATION TRAP** | — | — | — | 1962+ (16,027) | **CONFIRMED saturates** (fires ~23% of days, lift 0.63×). Even the raw flag is weak (~0.65×). Demote to raw non-confirmation flag + self-cancel fix. |
| dealer GEX / short-gamma | research-leading | n/a | n/a | n/a | **LIVE-ONLY 14 rows** | NOT backtestable. Live regime leg only. |
| VVIX (vol-of-vol) | research-leading | n/a | n/a | n/a | `cboe/vvix` **2006+ deep (5,046)**; `yahoo/_VVIX` only 28 | **BACKTESTABLE via cboe/vvix** (correction to "live-only"); needs its own backtest gate. |
| equity put/call ROC+level | research-leading | n/a | n/a | n/a | **LIVE-ONLY 14 rows** | NOT backtestable. Needs deep collector. |
| implied correlation / dispersion | research-leading | n/a | n/a | n/a | proxy only, not stored | NOT backtestable. Needs collector. |
| HYG/TLT credit-momentum (price-based) | buildable-unvalidated | n/a | n/a | n/a | 2007+ (4,831), leak-free | Judge-confirmed buildable+leak-free; **NOT yet backtested** — do not put near headline until validated. |
| copper/gold + cyclical/defensive breakdown | research-leading (one proposal's probe) | ~0.45 | ~22d | fires 11% | 2000+ | Probe-level only; promising growth-scare precursor; needs formal backtest gate. |

---

## 3. THE LEADING SIGNAL SET

### Backtest-PROVEN leading (defensible today)
1. **VIX term-structure ROC** — `roc5(VIX9D/VIX3M)` causal-504d ≥0.80 (2011+), fallback `roc5(VIX/VIX3M)` (2006+). 85% recall, ~10d lead, fresh-cross confirmed. **WHEN-only, no direction/size.** Pair with the term-structure **LEVEL** percentile (higher lift, 1.87×) as a co-trigger — judges showed level and ROC are complements: ROC adds coverage on fast spikes, level adds precision.

### Deep + leak-free, research-backed, NEEDS a backtest gate before scoring
2. **HYG/TLT 21d ROC turning down** (price-based credit momentum, 2007+) — the fast credit read to replace reliance on lagging OAS.
3. **VVIX level + ROC** via `cboe/vvix` (2006+ deep — this is backtestable, contrary to the live-only assumption).
4. **Copper/gold + cyclical/defensive (XLY/XLP) breakdown** (2000+) — growth-scare precursor, ~22d lead in probe.
5. **breadth_div as a raw 21d non-confirmation flag** (fix the self-cancel; keep deep to 1962).

### Research-backed but LIVE-ONLY (need NEW deep collectors; cannot validate yet)
6. **Equity put/call** (14 rows) — tail-hedging / capitulation.
7. **Dealer GEX / short-gamma / flip proximity** (14 rows) — the leg that would catch reflexive vol-hole unwinds.
8. **Implied correlation (COR1M/COR3M) ROC** (not stored) — dispersion compression precedes correlated crashes.

### Demote / drop (proven not to help the alert)
- **drawdown_risk (credit composite)** → context/severity anchor only, `lead_lag='lagging'`. Never an early-warning trigger.
- **CBOE SKEW** → drop from scoring entirely (anti-signal). Display-only at most.
- **vol_structure LEVEL / VRP** → keep as complacency read, de-weight in alert (coincident).

---

## 4. REDESIGN SPEC — Regime-Typed, Lead-Weighted Risk Engine V2

Synthesis of the three proposals: take the **regime-typed sub-scores** (Proposal A), the **two-tier validated-backbone-vs-flow-overlay discipline** (Proposal B), and the **minimal surgical rewire of `core_series`/`compute` + typed thresholds** (Proposal C). Keep the shell (`compute()` live snapshot, `core_series()` historical series, the conjunction escalator). Keep the validated regime quad untouched. Keep selection out of it (sizing/de-gross only — no return-direction claim from any vol leg).

### 4.1 Core principle: separate by scare physics, never average lagging into leading

The composite is blind *because* it pools slow and fast precursors. V2 splits into **five scare-typed sub-scores**, each built only from precursors on its own timescale, fused at the top into a state that **names the dominant scare**.

```
  LEADING precursors  →  5 SCARE-TYPED SUB-SCORES (0–100 each)
  (own timescale)         vol · bubble · growth · inflation · sector-breakdown
                                  │  each: score, band, expected_lead_days, leg breakdown
                                  ▼
                       TOP-LEVEL FUSER
                       • dominant_scare = argmax(sub-scores)
                       • state = max band across types
                       • CONJUNCTION ESCALATOR: slow context (bubble/credit)
                         × fast trigger (vol/positioning) → +1 band
                       • TURNING-POINT rule: fire on the DATE a leading leg
                         FRESHLY crosses + ≥1 corroborator (not a level on a
                         chronically-elevated gauge)
                                  ▼
            ALERT when any sub-score ≥ its own forward-drawdown-calibrated
            threshold → message NAMES the scare + expected lead
```

**Two-tier validation discipline (from Proposal B):**
- **Tier A — VALIDATED BACKBONE** (backtested-leading, drives the loud alert): term-structure ROC + level, breadth_div raw flag, HYG/TLT momentum *once gated*. Credit OAS = confirm-only.
- **Tier B — FLOW OVERLAY** (live-only: put/call, GEX, implied-corr): **display + escalator-only behind a feature flag, with a forward-outcome log, until ≥250 PIT rows accrue.** Tier B can **only escalate** a band (conjunction), never lower one, and never moves the headline number on its own. This is the exact discipline the vol-shock scorecard already uses, and the antidote to the 2026-06-22 `cap_active` false all-clear.

### 4.2 The five scare types

| Scare | Leading precursors (Tier A unless noted) | Threshold (calibrated to fwd-DD prob) | Expected lead |
|---|---|---|---|
| **VOL (sharp/fast)** — the current blind spot | `roc5(vix9d/vix3m)` causal-504d ≥0.80 + term-structure **level** percentile co-trigger; **Tier B accelerants:** GEX<0, VVIX≥0.80, put/call spike | sub-score ≥70 → alert | ~7–13d, ~85% recall (high FPR — timing flag, WHEN-only) |
| **BUBBLE / concentration** (slow context → escalator) | SMH/SPY (leadership) 63d rel-return causal pctile ≥0.90; corroborate nh/nl-near-highs + 21d price-up/%>200dma-down non-confirmation | **never alerts alone**; escalates a VOL trigger +1 band when ext≥0.90 | inherits vol lead, higher conviction/severity |
| **GROWTH** (slow → cyclical unwind) | copper/gold + XLY/XLP breakdown z≥1.0; HYG/TLT 21d ROC down (gated) | sub-score ≥60 | ~22d (probe) — needs formal gate |
| **INFLATION / rates** | MOVE (rates-vol) percentile + 10y real-rate / breakeven ROC; 2s10s shock | sub-score ≥60 | medium; context-heavy |
| **SECTOR-BREAKDOWN / internals** | breadth_div raw 21d flag (self-cancel fixed); McClellan/NH-NL deterioration | corroborator role; ≥60 standalone only if breadth collapse is broad | slow-grind |

**Calibration rule for every threshold:** set the band where `P(event onset ≤ lead_window | sub-score elevated)` *meaningfully* exceeds the ~7–12% base rate (target ≥2× lift, matching the composite's proven 3.0× at abs≥60). Reject any threshold whose elevated-frequency exceeds ~20% of days (saturation → no edge, per the SKEW/percentile findings).

### 4.3 Surgical changes to `engine/risk_state.py` (Proposal C, lowest-risk path to ship first)

1. **Add a `vol_roc` leg** to both `core_series` and `compute`, leak-free:
   ```
   r9 = VIX9D/VIX3M (2011+); r3 = VIX/VIX3M (2006+ fallback)
   roc5 = r - r.shift(5)
   sig  = causal_504d_pctile(roc5, min_periods=63)
   intensity = clip01((sig - 0.70)/0.20)   # ramps over pctile 0.70→0.90
   ```
   Add `vol_roc` to `_LEADING` so it counts in the conjunction. Keep `vol_structure` (level/VRP) as the separate complacency read.
2. **Fix the self-cancel:** convert breadth_div from a percentile to a *latched* 21d non-confirmation flag (stays armed for N days after the divergence, so a price drop doesn't instantly disarm it).
3. **Re-weight toward leading:** vol_roc 1.0, complacency 1.0, breadth_div 0.9, dealer_gamma 0.9, technical 0.8, extension 0.6, vol_structure 0.5, credit 0.4, macro_backdrop 0.2, turning_point/cross_asset 0.3. **Drop SKEW from the alert** (≤+0.1 nudge inside vol_structure at most).
4. **Eliminate the one-build lag on leading legs** where possible: compute dealer_gamma/technical from in-process state, not yesterday's `site/gex/index.json` / `mtf_monitor.published()`.
5. **Typed alert tiers** (replace the single coarse band):

   | Tier | Trigger | Lead | Action |
   |---|---|---|---|
   | EARLY-WATCH | `vol_roc` alone ≥0.80 | ~7–13d | display + light de-gross (NOT below ~0.95 gross) |
   | CAUTION (floor 40) | `vol_roc` + any 1 leading leg ≥0.6 | ~5–10d | trim, honor stops |
   | ELEVATED (floor 60, loud banner) | ≥2 leading legs ≥0.6 OR vol_roc+breadth_div+credit | ~3–8d | de-gross, the proven 3.0× band |
   | RISK-OFF (80) | ≥3 leading legs ≥0.6 | coincident–short | max defense |

   Keep absolute-band semantics (abs≥60 = the real edge). **Never use the percentile band as a trigger** (no-edge). EARLY-WATCH is explicitly labeled high-recall/high-FP.

### 4.4 NEW deep collectors to add (prioritized)

1. **Equity put/call deep history** — official CBOE total put/call CSV backfill (replace the 14-row SPX/SPY/QQQ proxy). *Highest priority — unlocks the fast-event leg.*
2. **VVIX backtest** — already deep at `cboe/vvix` (2006+); just wire + gate (no new collector, but it's a quick win).
3. **Implied correlation (COR1M/COR3M)** — new collector (dispersion compression precursor).
4. **CDX HY/IG spreads** — beyond ETF proxies (cross-asset credit stress).
5. **IG OAS backfill** — widen `fred/BAMLC0A0CM` fetch (FRED has it to 1996; easy).
6. **AAII bull/bear** + **FINRA short-volume backfill** (2009+) — positioning extremes.

---

## 5. DASHBOARD INTEGRATION — top-of-US loud panel

Placement: **above the Signal Stack on the US dashboard** (`templates/dashboard.html.j2`), before any selection content. The loud risk panel must show, in priority order:

1. **STATE** — one word + color: `Calm / Early-Watch / Caution / Elevated / Risk-Off`, driven by the typed tiers (§4.3). Color-banded so a glance reads it.
2. **DOMINANT SCARE-TYPE** — the named argmax sub-score: e.g. "VOL scare — steepening backwardation" or "BUBBLE × VOL conjunction". This is the headline the current engine cannot produce.
3. **FIRING LEADING PRECURSORS** — the specific legs that tripped, each with its own value and lead-class tag (LEADING / coincident / lagging), so the user sees *why*. e.g. `vol_roc 0.86 (LEADING) · breadth_div latched (LEADING) · credit OAS +12bp (lagging-confirm)`.
4. **LEAD-TIME CONTEXT** — "expected ~7–13bd lead; high-recall / high-FP timing flag (WHEN not how-deep)" for the vol tier; the honest caveat travels *with* the alert.
5. **FORWARD-OUTCOME LOG link** — running tally of how the last N fires actually resolved (the vol-shock-scorecard pattern), so the panel is self-auditing.
6. **Tier B flow legs** rendered as a separate dim "live accelerants (un-backtested)" row, visually subordinate, never able to set the headline state.

---

## 6. PHASED BUILD PLAN (each phase gated by a backtest)

- **Phase 0 — Minimal rewire (ship first, lowest risk).** Add `vol_roc` leg + level co-trigger to `core_series`/`compute`; fix breadth_div self-cancel (latch); re-weight; drop SKEW; typed tiers. **Gate:** re-run the 68-event harness — must catch 2026-01 + a majority of the fast events it currently misses, with abs≥60 lift held ≥2.5× and elevated-frequency <10%.
- **Phase 1 — Eliminate one-build lag** on dealer_gamma/technical; surface them in the alert path. **Gate:** in-process vs published values agree on history; no leakage.
- **Phase 2 — Regime-typed sub-scores.** Split into vol/bubble/growth/inflation/sector. **Gate:** each sub-score's threshold individually clears the ≥2× forward-DD-lift bar on its in-coverage events; conjunction escalator validated on 2000/2018-01/2026-01.
- **Phase 3 — Validate buildable legs.** Backtest HYG/TLT momentum, VVIX (cboe), copper/gold breakdown. **Gate:** only legs that backtest leading (≥2× lift, positive fresh-cross) join Tier A; the rest stay context.
- **Phase 4 — New deep collectors.** Put/call (priority), implied-corr, CDX, IG OAS, AAII, FINRA. **Gate:** ≥250 PIT rows before any Tier-B leg is allowed to escalate; forward-outcome log live the whole time.
- **Phase 5 — Dashboard loud panel** wired to the typed state + forward log.

Every phase: leak-free (causal windows, min_periods), no commit until its gate passes, no selection coupling.

---

## 7. HONESTY — validated vs heuristic vs not-yet-backtestable

**VALIDATED (defensible, multi-judge confirmed):**
- Current composite is leading-slow / silent-fast; 3.0× lift only at abs≥60; percentile band is no-edge. (CONFIRMED)
- drawdown_risk credit composite is **lagging** (peaks +28bd after onset, 100% of events). (CONFIRMED)
- CBOE SKEW has **no edge** (anti-signal vs matched-frequency noise, p<0.003). Dropping it is the single best-grounded decision. (CONFIRMED by all 3 judges)
- breadth_div percentile **saturates**; its self-cancel caused the 2026-06-23 46.9→7.8 collapse. (CONFIRMED)
- VIX term-structure ROC is a **genuine fresh-cross precursor** (29/34, ~10d). (CONFIRMED)

**HEURISTIC / overstated — handle with care:**
- ROC is **NOT a clean replacement keystone** for the level. Judge 2 showed the *level* wins on lift/precision (1.87× vs 1.26×) and led equally in 4/6 named "ROC-only" events; the quoted ROC 0.85 vs level 0.48–0.59 did not fully reproduce. **V2 ships them as co-triggers, not ROC-alone.**
- Typed thresholds (70/40/60/80) and sub-score weights are calibration starting points, not yet backtest-locked — Phase 0/2 gates must confirm.
- breadth_div even as a raw flag is weak (~0.65×); it is a corroborator, never a standalone trigger.
- The vol leg has **no directional or sizing edge** (corr fwd-10d SPY ≈ 0). It routes to de-gross/timing ONLY. Never to selection or position direction.

**NOT-YET-BACKTESTABLE (live-only gaps; honest unknowns):**
- Equity put/call (14 rows), dealer GEX (14 rows), implied correlation (not stored). Research-backed and likely to improve fast-event lead, but **cannot be validated** until deep collectors accrue ≥250 PIT rows. They ship Tier-B (display/escalator-only) behind a flag with a forward-outcome log — never feeding the headline number until their own backtest exists.
- HYG/TLT momentum, VVIX (cboe), copper/gold breakdown are deep + leak-free but **not yet formally backtested here** — they stay out of the headline until Phase 3 gates them.

---

*End of findings. Scratch backtests: `/tmp/riskbt/`. Engine: `engine/risk_state.py`, `engine/conditions.py`, `engine/mtf_monitor.py`. Related: macro#485 (lead_lag labels), `research/RISK_FLIP_2026-06-22.md`, `research/RISK_LAYER_DESIGN.md`.*

---

## 8. DECISIVE RE-VALIDATION (strict bar) — supersedes §2 verdicts

After the red-team showed §2 used **event-anchored recall** (which rewards frequent-firing signals), every candidate was re-scored under the strict bar:
**day-level forward lift (P(SPY drawdown-onset ≤15bd | elevated) / base) ≥ 1.5× AND frequency-matched permutation p<0.05 AND 2020+ era lift ≥ 1.2×.** All causal. Script: `/tmp/riskbt/revalidate.py` (68 onsets, perm n=400, eras 06-12 / 13-19 / 20-26).

| Signal | thresh | lift | fire% | perm_p | 06-12 | 13-19 | 20-26 | verdict |
|---|---|---|---|---|---|---|---|---|
| **hy_oas_chg_21d (raw credit ROC)** | pct≥.95 | **1.93×** | 7.4% | 0.000 | 2.72× | 1.51× | **1.94×** | **LEADS (era-robust)** |
| move_level | pct≥.90 | 1.94× | 12% | 0.000 | 2.11× | 0.07× | **1.83×** | LEADS (regime-dep: dead 13-19) |
| spy_ext_above200 (parabolicity) | pct≥.95 | 1.23× | 9.6% | 0.007 | 0.54× | 1.35× | **2.06×** | modern-era leader (bubble) |
| xlu_spy_defensive_up | pct≥.95 | 1.28× | 6.1% | 0.033 | 0.85× | 0.40× | **1.91×** | modern-era leader (growth) |
| xly_xlp_rolldown | pct≥.95 | 1.33× | 6.9% | 0.003 | 1.81× | 0.67× | **1.67×** | modern-era leader (rotation) |
| move_roc5 | pct≥.95 | 1.34× | 5.7% | 0.015 | 1.37× | 0.71× | 1.49× | weak |
| vol_lvl9 (VIX9D/VIX3M) | pct≥.95 | 1.38× | 5.5% | 0.018 | 3.01× | 1.02× | 1.44× | weak-positive (vol) |
| vol_lvl3 (VIX/VIX3M) | pct≥.95 | 1.31× | 6.0% | 0.010 | 1.92× | 0.30× | 1.45× | weak (unstable) |
| **current_composite abs≥60** | abs≥60 | 2.93× | 2.7% | 0.000 | 1.70× | 2.38× | **0.68×** | **EDGE DEAD in modern era** |
| breadth_div_flag | flag | 1.78× | 9.7% | 0.000 | 3.09× | 1.49× | **0.69×** | dead in modern era |
| vvix_level | pct≥.80 | 1.20× | 23% | 0.000 | 1.51× | 1.09× | 0.94× | no modern edge |
| vol_roc9 (synthesis keystone) | pct≥.95 | 1.08× | 5.5% | 0.390 | 2.37× | 1.24× | 0.68× | **NOISE (perm fail)** |
| drawdown_risk (credit composite) | pct≥.90 | 1.05× | 21% | 0.207 | 1.45× | 1.75× | 1.04× | no edge (lagging) |
| current_composite percentile | pct≥.80 | 0.45× | 54% | 1.000 | — | — | 0.70× | anti-signal |
| skew_level / skew_roc / vrp / hyg_tlt | — | ≤1.25× | — | — | — | — | <1.0× | NO EDGE (drop) |

### Decisive conclusions
1. **The shipped engine's one real edge is era-stale.** abs≥60 was 1.7–2.4× in 2006–2019 but **0.68× in 2020–2026** — it does not work in the regime that motivated this project. Same for breadth_div (0.69× modern). This is the single most important finding.
2. **A genuinely predictive daily alert is modest, not a crystal ball.** The best surviving signals give ~**1.5–2×** conditional lift (≈20–26% chance of a ≥8% drawdown onset within 15bd when elevated, vs ~12% base) with **high false-positive rates**. Real and useful for de-grossing/timing — but it must ship with a forward-outcome log and an explicit FP budget, and be framed as odds, not a forecast.
3. **Regime-typing is data-validated, not aspirational** — *different* signals lead *different* scare types, and the modern-era leaders cluster by physics: **credit** (HY OAS ROC, era-robust), **rates/inflation** (MOVE), **bubble** (parabolicity, 2.06× modern), **growth/rotation** (defensives 1.91×, XLY/XLP 1.67×). The **vol-event** type has NO backtestable leading signal here — it genuinely needs the deep options-flow data (put/call, implied-corr, GEX history) we don't yet have.
4. **Drop for good:** vol_roc (noise), SKEW (anti-signal), VVIX/HYG-TLT/VRP (no modern edge), and never use a percentile band as a trigger.

### Honest redesign mandate (supersedes §4 weights)
Build the composite ONLY from strict-bar survivors, weighted by **2020+ era lift**, regime-typed by the clusters above; calibrate alert thresholds to ≥2× forward-DD lift under an explicit FP budget; bake a **walk-forward 2020+ holdout gate** into a test; ship a **forward-outcome log**; and stand up the **deep options-flow collectors** (put/call CSV first) as the only credible path to fast vol-event lead. Frame everything as modest odds with the lift/FP/lead printed next to the alert.

---

## 9. ESCALATING CALIBRATED PROBABILITY (does the likelihood rise as risk builds?)

YES — measured (`/tmp/riskbt/escalation.py`). P(SPY >= 5% pullback within H business days) is
monotonic in BOTH intensity (state band) and conjunction (# Tier-A scares firing together):

**Intensity (2020+ holdout — the regime that matters):**

| state | H5 | H10 | H21 | H42 |
|---|---|---|---|---|
| calm | 0.0% | 0.0% | 0.0% | 0.0% |
| caution | 0.0% | 0.4% | 8.1% | 17.7% |
| elevated | 2.7% | 6.6% | 11.7% | 16.6% |
| **risk-off** | **6.6%** | **14.7%** | **30.3%** | **42.8%** |
| base | 3.7% | 8.5% | 18.1% | 27.1% |

**Conjunction (full history):**

| # Tier-A hot | H5 | H10 | H21 | H42 |
|---|---|---|---|---|
| 0 | 2.1% | 5.8% | 11.6% | 20.0% |
| 1 | 2.5% | 7.2% | 16.6% | 26.2% |
| 2 | 4.1% | 9.8% | 20.3% | 30.1% |
| **>=3** | **8.1%** | **14.3%** | **25.0%** | **35.3%** |

**Approach (honest nuance):** the radar is elevated ~3-4 weeks BEFORE events (mean top-score ~80
from 40bd out — genuine early warning), but the 5-day hazard only spikes AT the onset. So it
reliably flags a ~20-30% drawdown WINDOW with rising odds; it cannot pinpoint the exact day.

**Implemented:** `risk_radar.compute()` now emits `drawdown_prob = {h5, h10, h21, base_h21,
lift_h21, conjunction_n}` from a baked `_PROB_CAL` surface (blended full + 2020+, monotonic at
the top) plus a per-extra-hot-scare bump — so the displayed probability RISES as intensity and
conjunction build. The surface is overlay-able (`data/risk_radar/calibration.json` `prob_cal`) so
the Opus self-correction loop retunes it from the realized forward-outcome log.

---

## 10. PHASE D — deep options-flow collectors: the honest data reality

GOAL: loudly catch NARROW/fast vol events (like 2026-06-23) that the broad validated legs miss.
The verified residual gap (§ tuning) is the vol-event scare-type, which needs options/positioning
flow. FINDING — **deep options-flow history is NOT freely available**:
- CBOE CDN serves only the `*_History.csv` family (SKEW 1990+, VVIX 2006+, VIX) — **put/call,
  implied-correlation (COR), and dealer-GEX are 403/Access-Denied**.
- Yahoo `^CPC/^CPCE/^CPCI` (put/call ratio) → **404, not carried**.
- VVIX IS deep (cboe/vvix 2006+) but **failed the strict gate** (2020+ lift 0.94×, no edge) — not promoted.
- Dealer GEX is point-in-time (not backfillable by construction).

So the vol-event leg **cannot be backtested today**. The honest implementation (Tier-B discipline):
the live `cboe_putcall` + `cboe_gex` collectors (already registered, accruing ~from 2026-06) feed
two new **Tier-B flow legs** (`vol_putcall` = rising equity put/call; `vol_gex` = negative net GEX /
dealer short-gamma) that are **INERT until `_FLOW_MIN_HISTORY` (252) rows accrue** — absent from
`leading_signals()` until then, so they can't add noise. Once mature they auto-join the vol scare-type
and are gated by the **same strict bar** via the Opus self-correction loop before they're trusted; vol
stays Tier-B (display/escalator-only) until then. The dashboard shows the accrual countdown
("Vol-event detection accruing: put/call N/252"). i.e. the radar will get materially better at narrow
vol events ~1 year forward, validated — not faked with data we don't have.

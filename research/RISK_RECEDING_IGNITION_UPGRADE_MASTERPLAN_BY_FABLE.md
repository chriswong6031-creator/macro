# Risk-Receding Multi-Channel Upgrade + Ignition Radar — masterplan (RRX2 / IGN)

**Author:** Fable (main loop) · **Date:** 2026-07-11 · **Status:** ADJUDICATED BUILD PLAN (operator-directed)
**Charter (operator, 2026-07-11):** (1) the "risk receding" read must not hang on Fed liquidity alone — expand to
technicals, sentiment, positioning and news/rhetoric tone; (2) the reader must always see WHY risk receded (which
scares faded, what turned); (3) card UI fixes (icon ladder, redundant "Liquidity" row label); (4) a brand-new
OPPOSITE layer — an alert that fires when the market is entering a risk-ON condition, covering both the
early-2025-style broad breadth-thrust case and the 2026-style narrow AI-semiconductor ignition case.
**Parent doc:** `research/RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` (RRX-R1..R10 all remain binding).
**Method:** subsystem census (2 lanes) + 7-lane web research with adversarial verification (workflow
`risk-regime-deep-research`), synthesized by Fable. Research appendix (§7) records the evidence grades.

---

## 1. What the June–July 2026 episode exposed

The radar worked: growth-scare intensity peaked at **90.8 on 2026-06-26** and receded to 62 (watch) by 07-10,
trajectory `receding`, velocity −21.7 pts/wk. But the recovery panel could only say *"Fed liquidity expanding"*:

- **V-recovery blind spot.** All 7 market-internal chips (C1–C7) are washout/retest/backwardation-shaped. In a
  fast V (no %>20dma washout below 25%, no VIX backwardation episode, no price retest, OAS ROC peak only at the
  70th pctile), none can arm — BY DESIGN. The panel then presents the liquidity channel as the *only* evidence,
  which reads as "risk receding = Fed liquidity" even though price, breadth and credit all improved.
- **No drivers narration.** The panel never says *which scare faded* (growth 91→38) or *what is still warm*
  (semis-concentration bubble read at 62). The "why is it fine again" question had no surface.
- **No risk-on layer.** Nothing in the US engine detects thrust/ignition as a positive event — `sector_ignition`
  exists for HK/Canada baskets only, and the C1–C4 thrust detections are buried as recovery confirmers.

## 2. Rulings issued here

- **RRX2-R1 (channels, not a composite).** The recovery panel expands from 2 to 4 evidence channels, each shown
  as its own chip row, never fused into any score: **Central banks** (existing 4 liquidity catalysts, renamed row),
  **Market internals** (C1–C8, unchanged), **Mood** (C9–C11 sentiment/positioning chips), **Tape** (C12
  fast-reclaim + recovery-morphology label). `turn_confirmed` (liquidity∧receding) and `turn_confirmed_full`
  (∧ internals) keep their exact current semantics — Mood/Tape chips are context, they confirm nothing.
- **RRX2-R2 (same ruler).** C9–C12 accrue in the recovery forward log and are graded on the SAME rebound-capture
  ruler (RRX-R2), with the same `accruing` honesty labels. RRX-R7 extends to them verbatim: never `_LEG_CALIB`,
  never state/gross/banner.
- **RRX2-R3 (fusion ban honored).** Sentiment/positioning enter ONLY as separate display chips (Signal Commons
  R3; WA-R2 — positioning is context/crowding-hazard, never a scored input).
- **RRX2-R4 (deterministic tone only).** The news/rhetoric channel uses the SF-Fed **Daily News Sentiment Index**
  (published deterministic NLP series already in store, 16.9k rows) — lag-honest label. No LLM anywhere in the
  detection path (CONST-ART1). Fed-rhetoric change is already covered deterministically by `fed_stance`/
  `fed_path` in the Central-banks channel.
- **RRX2-R5 (vol kill honored).** No new VIX-level/spike-fade chips (DO_NOT_REBUILD: absolute-VIX REJECT-STAT).
  The vol voice on the recovery side remains C6 (term-structure resolution) + C8 (instability veto).
- **RRX2-R6 (drivers line).** "What faded / still warm" is computed from the radar's own per-scare sub-score
  history (peak-day score vs today, same leak-free substrate as `trajectory`) — narration, display-only.
- **IGN-R1 (the new layer).** **Ignition Radar** (点火雷达) is the risk-ON mirror of the Risk Radar:
  display-tier, forward-graded, never a buy call, never sizing. Its states are evidence-taxonomy labels.
- **IGN-R2 (two channels, label not score).** BROAD (market thrust/participation confluence, K-of-N count) and
  NARROW (per-theme ignition over the US baskets) are shown separately; the cross-channel read is a LABEL
  ("Broad ignition" / "Narrow ignition — fragile until participation confirms" / "Broad + theme leading"),
  never a fused score (R3).
- **IGN-R3 (single source, K-of-N).** The BROAD channel reuses `risk_radar_market_catalysts` detections (C1
  thrust confluence, C2 summation swing, C3 washout→thrust, C4 FTD) — one compute, two surfaces, no drift —
  plus four participation confirms computed in the ignition engine: %>50dma recovery (level ≥55 AND +5pts over
  10d), net new-high flip (10d mean of nh−nl crossing positive from below within 10bd), RSP/SPY 20d RS slope
  turning positive, and sector participation (≥8 of 11 GICS sector ETFs above a rising 50dma — the
  ignition-vs-bubble discriminator, §7.3). K-of-8 counting only.
- **IGN-R4 (port, don't clone).** The NARROW channel calls `engine/sector_ignition.compute_basket_ignition`
  (unchanged, pure) over the US thematic baskets (`data/baskets/membership.json`, 46 baskets, SPY benchmark) —
  a US port of the HK/CA layer, honoring the operator's "port, don't clone" law.
- **IGN-R5 (pre-declared ignition ruler).** BROAD states grade on SPY forward returns at **h21/h63 (h126
  printed)** vs the all-days base rate + MAE; NARROW items grade exactly like HK/CA ignition (basket-minus-SPY
  excess at h20/h40, `engine/ignition_audit` pattern). Ledger: `data/ignition_log/us_ignition.jsonl` (synapse-
  registered). Significance by within-episode time-preserving permutation at maturity. Display-only until ≥30
  grades AND a fresh operator ruling (RRX-R7 pattern).
- **IGN-R6 (the narrow/fragile tension).** Narrow-without-broad is explicitly labeled as fragile participation
  (the 2026 semis case: real theme momentum, thin market confirmation); broad+narrow is the strongest read
  (the mid-2025 case). Concrete rule (§7.4): a narrow `igniting` theme WITHOUT (RSP/SPY confirm OR ≥8/11 sector
  participation) carries the *"narrow — fragile until participation broadens"* tag. Resolved by labeling, never
  by scoring.

## 3. Build waves

### WA — recovery panel multi-channel + card UI (PR-A, this PR)

1. **Icon ladder** (`_risk_radar_card.html.j2`): 🛑 risk-off / 🚨 elevated / ⚠️ caution / watch: **🌤️ when
   `recovery.receding` else 📡** (👀 retired) / ✅ calm.
2. **Row label**: `Liquidity` → **`Central banks`（央行）** — the chips (Fed liquidity expanding / cuts priced /
   PBoC easing / global tide) name the *what*; the row names the *who*. No more double-"liquidity".
3. **Drivers line** (RRX2-R6): trajectory gains per-scare `drivers` (peak-day vs now sub-scores); card renders
   e.g. *"What faded: growth scare 91→38 · rates 55→32 — still warm: narrow semis leadership 62"*.
4. **New chips** in `risk_radar_market_catalysts.py`, each with a `channel` field (`internals` C1–C8 unchanged;
   `mood` C9–C11; `tape` C12), all accruing/display-only:
   - **C9 — Managers re-grossing (NAAIM).** Weekly NAAIM exposure: washout = 13w min ≤ 20th causal pctile (3y);
     recovery = latest ≥ washout+15 pts AND up 2 consecutive weeks. Fresh ≤ 3 weeks.
   - **C10 — News tone recovering (SF-Fed DNSI).** 21d mean: washout = ≤10th causal pctile (504d) within last
     63d; recovery = 10d slope > 0 AND level ≥ washout + 0.15·σ504. Chip label carries the series' own date
     (T+~5 publication lag, lag-honest per RRX-R8 spirit).
   - **C11 — Speculators washed out (COT ES).** `net_spec_pct_oi` ≤ 10th causal pctile (156w) within last 8
     weeks AND rising over the last 2 reports. Weekly-lag label.
   - **C12 — Fast reclaim (V-recovery).** Episode = ≥3% drawdown from 63d high within last 63d (the June-2026
     SPY episode was ~3.7% — it MUST qualify); reclaim = ≥60% of the drawdown recovered within ≤15 sessions of
     the trough AND 3 consecutive closes above the 20dma. Fresh ≤ 10bd. *Acceptance: fires fresh on 2026-07-10
     live data.*
   - **Morphology label** (§4C of parent plan, built here): `V-shape` (C12 geometry) / `retest` (C5 geometry) /
     `grinding` (neither) — one line on the panel: V-shape explains WHY washout confirmers stay quiet.
   - `market_confirmed` / veto semantics: **C1–C7-only, unchanged** (mood/tape never flip confirmations).
5. **Audit wiring**: recovery forward log rows record C9–C12 states + morphology alongside C1–C8 (rebound ruler
   grades them identically).
6. Thresholds above are descriptive display-tier choices, not claims; the forward grades are the only ruler.

### WB — Ignition Radar (PR-B)

- `engine/ignition_radar.py` (pure compute + snapshot-shaped payload), `engine/ignition_audit.py` gains the US
  arm + broad-state grading, `templates/_ignition_radar_card.html.j2` + CSS (`.igx`, green accent, mirrors
  `.rrx` anatomy), rendered on the macro + US-stocks dashboards beside the Risk Radar card with a cross-reference
  chip ("Risk Radar: receding" ↔ "Ignition: warming"). Bilingual, plain-word glance tier.
- States (BROAD): `ignited` (K≥3 fresh within 10bd incl. ≥1 thrust event) / `warming` (K≥1 fresh) / `off`.
  NARROW: per-basket `igniting/running/fading/idle` (sector_ignition vocabulary), top items surfaced.
- Synapse: `data/ignition_log/us_ignition.jsonl` producer/consumers registered; tests whitelisted in ci.yml.

### Clocks

- **2026-08-15** — joins the RRX W0/W1 clock: are C9–C12 + ignition rows accruing?
- **2026-10-15** — narrow-channel first grades (h20/h40 mature); check against HK/CA ignition first read.
- **2027-01-15** — first rebound-ruler read incl. C9–C12; broad-ignition grades still small-N, printed.

## 4. Explicit non-goals / defers

- **AAII chip** — store has 23 rows (weeks); deferred until ≥3y accrued. **Put/call & GEX chips** — 25 rows,
  INERT (<252d law). **CNN Fear&Greed** — not collected; not planned (proprietary composite, redundant with C9/C10).
- **No tariff/geopolitics keyword detector** — GDELT-tone constructions deferred; DNSI (C10) is the deterministic
  tone read; revisit only with a pre-registered spec.
- **No change to state machine, bands, gross, context gate, or `deescalation` eligibility** — one risk voice
  stands; everything here is display/confirmation tier.
- The Ignition Radar does NOT feed `market_state` score, `sector_central` gating, or any allocation surface.

## 5. CI / house-law compliance checklist (both PRs)

Bilingual everywhere; no "validated" in user copy (CI); no CJK in `title=`; `.j2` exempt from template-site
sync; new tests added to ci.yml pytest whitelist; new artifacts synapse-registered; inline JS parses; intl cards
degrade (mood/tape/ignition are US-only: absent keys render nothing); degrade-don't-crash on every store read;
nightly is the sole ledger advancer (intraday discards `data/` writes).

## 6. Rulings appended to the registry

RRX2-R1..R6, IGN-R1..R6 (above). No new kills; AAII/putcall/GEX chips are data-defers, not kills.

## 7. Research appendix — evidence grades (workflow `risk-regime-deep-research`, 7 lanes / 65 findings)

**Honesty note:** the adversarial verification stage of the workflow was truncated by a session limit; the stats
below are **as reported by cited sources, single-sourced, not our own forward record** (house label law applies
verbatim on every chip). Grades are Fable's read of lane quality: A = multiple independent quant confirmations,
B = single credible quant source, C = folklore/contested/mixed.

### 7.1 Receding-confirmation evidence

| Signal | Grade | Key numbers (as reported) | Note |
|---|---|---|---|
| VIX/VIX3M backwardation→contango resolution (C6) | B+ | 43 episodes 2009–26: +3.0% 5d fwd @88%, +6.9% 63d @88% | Blind to slow grinds (2022 stayed in contango) — C6 already ships; keep |
| HY OAS spike-and-rollover (C7) | B | Premier lead INTO risk-off (median 7-mo lead, 8 episodes since 1997); no threshold-based all-clear rule exists in lit | Rollover = directional confirmation only; C7 stands |
| Fed net liquidity (fed_netliq catalyst) | **C — contested** | Rolling 52w corr with SPX +0.94 (2021) → **−0.80 (2026)**; its own researchers call it "a plumbing diagnostic, not a market-timing indicator" | The operator's complaint is empirically right: this cannot be the lone turn evidence. It stays as ONE chip among four channels |
| Fed-funds repricing / policy pivot (fed_policy) | B | Dec-2018: hike odds 71%→13% in 4 wks; recovery began Dec 24 | Crisis-inflection catalyst; already a chip |
| V-recovery detection (C12) | B | Practitioner reads: same-session VWAP reclaim + breadth golden-cross (>80% above 50d); Apr-2025 was 2nd-fastest 19%+ drawdown recovery in 75y | Daily-data version specified in §3.4; the June-2026 gap this plan closes |
| Percentile VIX (context) | B | 80th–85th pctile capture "20/80" excess-return concentration (Bansal-Stivers 1990–2022) | Already honored: engine is percentile-native; absolute-VIX kill stands |

### 7.2 Mood-channel evidence

| Signal | Grade | Key numbers | Disposition |
|---|---|---|---|
| Equity-only put/call spike-decay | A− (evidence) | SentimenTrader 43-instance/25y study | **Data-blocked** (25 rows, INERT) — deferred, not killed |
| NAAIM washout-and-recovery (C9) | B | Washout <40 + recovery w/ price confirmation | Ships; recovery-shaped rule (§3.4) inside a receding-phase panel = price context present |
| AAII bear-spread reversal | B | −20% spread extremes; Apr-2025: 8 consecutive weeks >50% bearish (35y record broken) | **Data-blocked** (23 rows) — deferred |
| COT net-spec washout (C11) | C standalone | R²≈0.02 vs 4w SPY returns (best academic study) | Ships as confluence-context chip only, weekly-lag label — exactly what RRX2-R3 allows |
| SF-Fed Daily News Sentiment (C10) | C for equity timing | Designed as a macro forecaster; equity link "empirically mixed" | Ships as the single deterministic tone read (operator asked for rhetoric); grade honestly on the rebound ruler |
| Buyback-window reopening | C | ~$4–5bn/day flow; index-level significance not established (SSGA) | Not built |
| CTA/vol-target reflow | B (flows real) | GS/MS public estimates post-vol-crush | Not built (no flow feed); revisit if a deterministic proxy lands |

### 7.3 Broad-ignition evidence (IGN)

| Signal | Grade | Key numbers | In IGN |
|---|---|---|---|
| Zweig Breadth Thrust | A− as-reported | 20th firing since 1945 on 2025-04-24/25; fwd 6m/12m strongly positive across variants; **failures cluster in Fed-tightening regimes (2002, 2022)** | C1 (already computed); IGN broad reuses |
| Double 80%+ up days / 90% up-volume | A− | 2025-04-09 (94% advancers, +9.5%) + 2025-04-22 pair | C1/W2 volume collector accrues |
| IBD Follow-Through Day | B− | Independent verification ~55% (not IBD's 70–80%) | C4; necessary-not-sufficient framing on the chip |
| %-above-50d recovery + sector participation (≥8 of 11 GICS expanding >50d breadth) | B | Ignition-vs-bubble discriminator | New confirm in IGN broad K-of-N (§3 WB) |
| RSP/SPY participation slope | B | Thrust-quality confirm; 2026 counter-case | New confirm in IGN broad |
| Net new-high flip | B | May-2025 A/D + NH expansion confirmed the thrust cluster | New confirm in IGN broad |

### 7.4 Narrow-ignition evidence (IGN)

| Signal | Grade | Key numbers | In IGN |
|---|---|---|---|
| Industry momentum (academic) | A | Moskowitz-Grinblatt: industry momentum explains most stock momentum | The narrow channel's foundation |
| Sector RS-line new high + volume >150% of 20d | B | 3,700+ breakouts: 72% continuation, +11.4% avg over 31d | Quality flag on narrow items |
| Sector breadth thrust (0→90% above 10d MA in 21d) | B | 52 signals/30y in energy; 69–82% 6m WR | Covered by the ported breadth_thrust leg |
| Rising 200d filter | B | Lifts 6m WR 69%→82% | Quality flag on narrow items |
| SOX-leads-SPX | C for timing | Real at cycle turns; lead noisy | Context copy only |
| **Fragility configuration** | B | Cap-weight highs + EW persistently lagging + falling count-above-200d = fragile, NOT ignition | IGN-R6 concrete rule: narrow igniting AND NOT (RSP confirm OR ≥8/11 participation) → labeled fragile |

### 7.5 The June→July 2026 turn (why the market is "fine again")

Radar-side: growth-scare intensity peaked **90.8 on 06-26** (defensives bid: XLU +4.7%, SPLV>MTUM by ~178bp
mid-June), receding since 06-29/07-01 to 62 (watch) — a fast V, so C1–C7 stayed dark and only `fed_netliq` lit.
News-side drivers, dated: **(1)** 06-05 Broadcom AI-guidance miss (−$1.3T chip-sector cap) + hot May jobs; **(2)**
06-11 CPI 4.2% + 06-17 hawkish first Warsh FOMC (9/18 dots projecting a 2026 hike; 2y +16bp) = the growth/rate
scare; **(3)** the turn: 06-17 US-Iran memorandum (Hormuz de-escalation; WTI back under $70, −30% on the quarter),
**06-24 Micron blowout** (rev $41.5B vs $35.7B, HBM sold out through 2027, +15.7%) re-igniting AI-semi capex
conviction, 06-29 reversal pivot (SMH +3%), **07-02 weak jobs (57K vs 115K)** taking the September hike off the
table; **(4)** confirmation: VIX 22.2→~16, HY OAS ~268bp (tight), SPX back within ~1% of records by 07-09/10,
SMH/SPY RS at 92nd pctile. Cross-checks the radar exactly: rate/growth scare faded; the **bubble/narrow-semis
scare is what remains** (dominant today at 62, `bubble_leadership` 92.5th pctile confirmed).

### 7.6 The 2025 reference case (broad) vs 2026 (narrow)

Apr-2025: capitulation (VIX 60 intraday 04-07, ~4% of SPX above 200d, record AAII bear streak) → policy U-turn
(04-09 tariff pause: +9.52%, 94% advancers) → thrust cluster (04-22 FTD + second 80% day; 04-24/25 ZBT #20; ~80%
above 50d by late May; RSP + R2K ATHs mid-June) = **broad regime, the thrust textbook**. 2026: Hormuz-crisis low
03-31 → SOX 17 straight up days (32y record), +87.8% Q2 — but ~23 stocks = the entire SPX YTD gain, EW lagging,
1/3 of R3000 still 30%+ off highs = **narrow regime: theme ignition + index fragility simultaneously**. The two
cases are why IGN keeps channels separate and labels fragility instead of netting one score.

### 7.7 Rhetoric verdict

Tone/rhetoric measures add marginal, window-specific value beyond price/vol (pre-FOMC drift; tariff-pause
announcements; TPU more predictive when already elevated). Deterministic constructions exist (EPU/TPU/GPR —
monthly, too slow for this layer; GDELT daily tone — deferred, needs a pre-registered spec; SF-Fed DNSI — daily,
in store). Ruling stands: **C10 (DNSI) is the one tone chip now**; Fed-rhetoric change stays covered by the
deterministic `fed_stance`/`fed_path` reads; no LLM anywhere in the path (CONST-ART1).

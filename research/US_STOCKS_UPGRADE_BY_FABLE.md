# US Stocks Pre-Breakout Upgrade — Masterplan (by Fable)

> **Canonical program doc.** Fable 5 is orchestrator + designer; Opus/Sonnet execute waves.
> Inputs: `research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md` (board-internal audit),
> `research/US_STOCKS_FRONTRUN_AND_FEEDER_INTEGRATION_AUDIT_FOR_FABLE.md` (feeder/front-run audit),
> `research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md` (stale-gate audit),
> `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (measurement constitution + falsified ledger),
> plus the 2026-07-03 seven-agent diagnostic run (findings inline below, all adversarially verified
> or file:line-cited). Authored 2026-07-03.

## 0. Status log

- **2026-07-03** — Program opened. Diagnostics complete (7 agents). Masterplan authored.
  W0 launched: (a) W-ARM + CT-LANE pre-registration & panel backtest (wave-8 harness);
  (b) yellow-alert icon/popover UI fix; (c) us_board_track grader populate/robustness fix.
- **2026-07-03** — W0(b) SHIPPED #1061 (alert icon + tap/hover popover, pulse, i18n-safe;
  fast-render verified; china/hk/canada siblings flagged for parity follow-up).
  W0(c) SHIPPED #1062 (grader hardened + 950 graded rows). **First forward reading:** h5
  buy-lane n=611, hit 62.7% vs SPY (CI 58.8–66.4), median excess +1.60% — the board's buys
  are real; but **P@1 board-order = 28.6% vs 71.4% under alpha-order of the same names** —
  the #1 slot is near-worst under current ordering. The P5/W2 rank fix (lane → state →
  alpha) is now *forward-measured*, not just audited. Wave-8 backtest still running.
- **2026-07-03 (wave-8 verdicts, both panels)** — **W8-C: `_ALIGN_BAD_STATES` hard-block
  unjustified (Lane R licensed).** **W8-A W-ARM: NOT PROMOTED** (clean15 gate fail deep;
  stop5 edge did not transfer OOS — ARMED chip closed; the weekly trigger carries nothing
  beyond basing). **W8-B SHAKEN: CONFIRMED on both panels** (deep 35.8 vs 40.3, OOS 42.5 vs
  47.1 stop5, sign-stable all splits) — ships as chip + eligibility, no rank power. BASED
  ships as claim-free eligibility door. All postcross states accrue silently in the forward
  ledger. Full numbers: DURABLE_BOTTOM_FRAMEWORK.md §8. W1 in flight; scope-B merge shape
  amended accordingly (drop ARMED display, keep SHAKEN + BASED door + ledger fields).
- **2026-07-03 — W1 SHIPPED #1095** (implement → Opus adversarial review → orchestrator
  merge-gate): Lane R dual-lane admission (knife + weekly-falling guarded — review catch),
  alpha-within-lane ordering, `entry_open_first` removed as terminal sort, headline arbiter
  (ELV fixture), `engine/postcross.py` (BASED/ARMED/SHAKEN detector, honesty contract in
  docstring), lane+postcross strata into grade_us_board. Merge-gate surgery applied the OOS
  verdicts: ARMED chip stripped (fields accrue silently), SHAKEN chip confirmed-copy, all
  new chips' bilingual `title=` attrs removed (i18n rule), one mis-attributed claim deleted.
  35/35 targeted tests; CI clean. **First Lane R names appear at the next nightly render.**
  NEXT: W2 (running ledger strip + chip popovers via #1061 pattern + remaining arbiter
  invariants), W3 evidence stack, W4 sector re-arm bus + tailwind inversion, W5 grading
  maturity (P@k new-vs-old order on the live ledger is the program's success metric).

- **2026-07-03 — W2 SHIPPED #1122** (+ parallel complements #1123/#1126 from a second
  session: survivorship disclosure `n_skipped_no_price`): surfaced-outcome strip (exited
  buy names -> visible P&L ledger, |move|-sorted; first live read: 7 running incl. AGYS
  +26.6%, 8 stopped incl. MPWR −21.9%, median −15.2%), chip explanatory copy via the
  repo-standard data-tip popovers, and check_board_contradictions.py as a two-tier guard
  (PR job artifact-conditional + pages.yml deploy-gate twin).
- **2026-07-03 — W3 SHIPPED #1127**: evidence stack v1 — 7 PIT-safe lenses (insider
  cluster, GEX confirmer, altdata convergence, SUE freshness, news burst, smartmoney 13F,
  anticipation stop-budget) as display chips behind per-source freshness gates
  (stale ⇒ `evidence_health` unknown, never neutral), Confluence+ k-of-n badge with
  independence groups, and per-lens grader strata. ZERO ordering power — every lens must
  earn tilt through the live ledger.
- **2026-07-03 — wave-9 measurement launched** (gates W4): W9-A sector-conditioned
  re-arm (cohort-washout conditioning of the BASED population) + W9-B tailwind A/B
  (bottoming-phase score vs incumbent 20d-rel as outcome stratifier; three-way decision
  rule pre-registered incl. demote-to-display). W4 implements per verdicts. W5 (grading
  maturity) awaits live accrual.

## 1. What the diagnostics established (the evidence base)

**F1 — The REGN/VEEV "disappearance" was not a bug, and the truth is more useful than a bug.**
- VEEV was never on any buy list. It sat on **discovery.html's AVOID table** (bottom-6 Health-Care
  laggards). The owner bought from the Avoid list at ~$159 → +20.7%. It vanished on 06-30 19:02
  because its alpha **improved** (−1.93 → −1.70), lifting it off the bottom-6 (`build_discovery.py:291`).
  Working as designed; the design just has no surface for "washed-out laggard turning up" — which is
  the owner's actual shopping list.
- REGN was never on the stock board either. Its actionable surface was the **big_pharma basket page**:
  `wait_pullback` with an explicit entry zone at $609 on 06-21 → `hold` for 12 days → formal
  `act_now` BUY only on **07-03 at $654 (+7.3% after the owner's entry)**. Meanwhile **gex.html showed
  a persistent $700 max-pain magnet from 06-24** (spot $623) that never joined any stock-board flow.
- Both names sat in a sector reading CONFIRMED_DOWN. **The owner systematically trades contrarian
  washout-recovery entries inside weak sectors; the product labels that cohort "Avoid."**

**F2 — The alignment gate bans the owner's archetype by name.**
Zero overlap this week between Top Setups (12 names) and Standout buys (24). **7 of 12 setups names
are hard-blocked from the Standout board by `_ALIGN_BAD_STATES` because their ladder state is
`COUNTERTREND BOUNCE`** (BMY, SBRA, TR, NI, MATW, HE + MTCH via TOP WATCH). At a genuine sector
bottom the weekly is *always* still broken — demanding weekly alignment = demanding confirmation =
serving mid-cycle entries. Exhibit: the board's only Health-Care buy, **ELV, is +31.9% / 13.8 ATR
extended since its cross of 2026-04-09 (20 ticks ago), weekly showing early topping — labeled
"FRESH BUY."** The board surfaces the launched name and excludes the based ones.

**F3 — The owner's weekly-MACD instrument is real, and it is the *RSI-MACD*.**
The "histogram fading above −0.75 toward a bullish cross" only makes sense on the **weekly RSI-MACD**
(EMA14−EMA60 of RSI14, EMA5 signal) — already the gate's own weekly confirm leg
(`confluence_tiers.py:174-176`). Because RSI is bounded 0–100, the histogram is ~scale-free across
price levels (MCK −0.28 @ $768 vs KO −0.30 @ $81 comparable) — **the extension-normalization problem
the owner worried about largely dissolves in RSI units.** Verified live (2026-07-01 closes):
- **MCK**: 3D cross 06-11, 5 ticks old, ext −2.43% (−2.0 ATR), max-drawup 0%; weekly hist
  −1.99 → −0.28 rising 5 consecutive bars, **extrapolated cross ≈ 1.1 weeks**; vetoed today by a
  borderline stoch_ob (k=81.5 vs 80). The owner's case, quantified.
- **MCD**: 3D cross 06-09, 6 ticks, ext −4.54% (−3.9 ATR); weekly hist −1.93 → −0.79 (net-rising,
  stalled last bar); weekly StochRSI k=21 rising toward d=27; below 200SMA; vetoed by stoch_bear
  (k<d by 0.4). The "shaken" case: post-cross fake-out, smash, recovery.
- **KO**: based (ext −2.1%) but weekly hist oscillating ~−0.3 with no approach signature — correctly
  NOT an armed candidate. The instrument discriminates *within* the based cohort.

**F4 — The measurement constitution exists, the panel is local, and the neighbors are mapped.**
`research/entry_timing/` waves + `tuning_harness`: per-fire count-fair metrics (stop5 / clean15 /
dead-money / recall / entry-premium), 224-name deep panel (1962→2026, fully local, no R2 dependency),
basket OOS panel (2,519 files, 2014+), delisted panel. Pre-registration required before first run.
**Adjacent falsified/near-miss cells that W-ARM must provably differ from:** H2 washout-age+calm
(wrong sign), H4 volume dry-up, BASED chip (operationally falsified, wave 5), RETEST 2D re-cross
(NO-SHIP, wave 5), **F7 weekly-stoch-turn (NEAR-MISS +1.47/+1.55pp, wave 6, blocked population)**.
F7's near-miss is encouraging: a weekly-turn carries *some* signal; W-ARM differs by instrument
(RSI-MACD histogram approach, not stoch turn), by population (stale 3–8-tick crosses, not
COILED-blocked), and by the extension condition.

**F5 — The forward ledger is one command away, not broken.**
`us_board_track.json` is empty because the 05:12 grader run found no matured rows in its cache
window; `data/us_board_ledger/retro_grades.parquet` already holds 529 graded h5 rows (06-15..06-22),
and boards through 06-24 have matured h5 **now**. Populate + harden (don't emit `empty:true` when
the parquet has rows).

**F6 — UI contradictions, enumerated (24 buy cards):** 15 score-vs-alpha inversions;
`alpha_entry=laggard` **exists in the JSON but is never rendered** (8 cards); urgency=imminent on
label=BOTTOMING-blocked (4); risk ≥0.35 shown on BUY cards with no downgrade (8); within-score-tie
order not alpha-descending. Yellow alerts: 15 cautions across 24 cards, up to 181 chars, inflating
grid height (`dashboard.html.j2:2578`, CSS L605-607).

**F7 — Evidence-stack inventory (top validated/PIT-safe sources ready to wire):**
COILED/COILED-FIRE (validated: +7.5pp clean15 / −5.6pp stop5), Insider Form-4 cluster (the lone FDR
survivor), sector spotlight stage, altdata convergence ≥2 (activist/gov-contract/congress+insider),
anticipation drawdown budget (validated stop-width GO legs), vol-squeeze BBWP × GEX vol_hole
conjunction, SUE freshness chip (context, not alpha), news-burst convergence, GEX confirmer
(accruing — the REGN $700-magnet lesson).

## 2. Root cause, one sentence

**The board demands confirmation (weekly alignment, freshness of the fast cross) at exactly the
moment the owner's edge lives in anticipation (washed-out sector, based name, slow-timeframe trigger
approaching) — and it has no lifecycle model to tell "based and arming" from "launched and late,"
so it drops both the same way and surfaces whatever already moved.**

## 3. Architecture — the Pre-Breakout Board

### P1 — Post-cross lifecycle state machine (replaces the binary fresh/stale)
Every confluence event enters a tracked lifecycle keyed on **extension-since-cross (ATR-normalized)**
and the **weekly RSI-MACD approach**, not tick-age alone:

```
            ┌── LAUNCHED (maxDU_atr > launch_thresh) ──→ RUNNING ledger (visible, graded)
FRESH (0-2t)┤
            └── BASED (3-8t, |ext_atr| ≤ band, not OB)
                   └── ARMED (BASED + weekly RSI-MACD hist <0, net-rising, > −θ, cross ≤2wk;
                              optional weekly StochRSI confluence)  ←— the owner's W-ARM instrument
                   └── SHAKEN (post-cross new low > 1.5 ATR below cross, then recovery) — MCD sub-cell
            └── FAILED (stop band breached) ──→ graded, closed
```
- ARMED/BASED ship first as **chips + capped rank bonus + forward-ledger fields** (repo discipline:
  display → grade → earn gate power). FRESH keeps its current power.
- Regression fixtures (permanent): JNJ/AMAT-2026 (launched, must never re-admit); **ELV must render
  as LAUNCHED/extended, never FRESH BUY**; MCK-2026-07 must be ARMED; KO must be BASED-not-ARMED.
- Answers the owner's "exceptions to override the gate": exceptions become **named, graded states**,
  not ad-hoc overrides.

### P2 — Dual-lane admission (fixes the COUNTERTREND ban + the divergence)
- **Lane T (trend)**: today's alignment-gated inclusion, unchanged.
- **Lane R (recovery)**: admits `COUNTERTREND BOUNCE`/washout names iff fresh confluence
  (`is_buyable`) **or** BASED/ARMED state, with low extension — priority-boosted when the sector
  cohort is washed-out-and-turning (coiled fraction, sector_bottom durable-bottom, subsector
  improving). Cards carry the lane label; **lanes are never blended into one fused score.**
- Board order: lane → **alpha** (the validated leg finally orders what the user reads).
  *Amended 2026-07-03 per W8-A verdict:* lifecycle states are **eligibility + display only, never
  ordering power** — the rank-lift claim failed its gate (clean15 spread +1.37pp, ticker-halves
  unstable), while the safety claim passed (stop5 −4/−5pp, NI on clean15). Expected effect: the
  four healthcare setups names appear on the board in Lane R instead of being invisible.

### P3 — Evidence stack v1 (the "human judgment" layer)
Per-card dossier of independent, PIT-safe lenses — each a chip with its own forward grade, plus a
**capped** priority tilt (no lens can flip a state, only re-order within it):
insider cluster · COILED/FIRE · sector spotlight stage · altdata convergence ≥2 · news burst ·
SUE freshness · GEX confirmer (max-pain magnet distance + regime flip — the exact signals that
called REGN to $700 while our flow ignored them) · vol-squeeze × GEX-vol-hole conjunction.
The **anticipation drawdown budget** renders as the card's stop-width guidance (sizing rigor).
k-of-n agreement (≥2 independent lenses) earns the "confluence+" badge — precision from redundancy
while individual track records accrue.

### P4 — Running ledger + honest grading (fixes "winners vanish" + empty track)
- Names exiting entry surfaces (LAUNCHED/FAILED) move to a visible **"Surfaced → outcome" strip**
  with surfaced date/price and live P&L — REGN/VEEV-class winners become marketing instead of
  confusion, losers become accountability.
- `grade_us_board.py` populated + hardened (F5); precision@k under new lane-order vs old order
  becomes the program's own scoreboard.

### P5 — UI single-arbiter (fixes F6)
- The loud fields (state/label/urgency/band color) become **functions of** the fields that set rank;
  build-time invariants fail the render on: FRESH label with ext_atr > threshold or cross age > N,
  BUY-ish state with alpha_entry=laggard unrendered, imminent urgency on blocked label.
- Render `alpha_entry`; risk ≥0.35 demotes the band color one step.
- Yellow alerts → pulsing icon + count badge, popover on hover/tap (dual-span i18n inside the
  popover body, never in attributes).

## 4. Validation constitution (what ships only after numbers)

Pre-registered wave-8 cells (deep panel 2012+, per-fire count-fair, time-halves + ticker-halves,
DURABLE_BOTTOM §4.3 promotion gates):
- **W-ARM cell**: population = 3D RSI-MACD cross aged 3–8 ticks, ext_atr ∈ band (sweep), maxDU below
  launch threshold (sweep), 3D stoch not OB. Trigger = weekly RSI-MACD hist <0, net-rising (sweep
  strict-consecutive vs net-over-3-bars), hist > −θ (sweep −1.0/−0.75/−0.5), extrapolated cross ≤2wk.
  Variant: + weekly StochRSI k>d or rising-from-<30. Baselines: FRESH fires; stale-3-8t-without-trigger;
  F7 recomputed on this population; BASED-chip definition (must show different fires AND outcomes).
  Fixtures: MCK fires; KO does not; ELV/JNJ never fire.
- **SHAKEN sub-cell**: post-cross new low >1.5 ATR then recovery + same weekly trigger (MCD anatomy).
  Reported separately (smaller n).
- **CT-LANE cell**: fires with ladder state ∈ _ALIGN_BAD_STATES (esp. COUNTERTREND BOUNCE) passing
  is_buyable — vs aligned fires. If not-worse on stop5/clean15 (or better with cohort-washout
  conditioning), the hard-block is unjustified and Lane R is validated.
- Promotion: constitution gates (≥5pp clean15 spread, n≥300/side, sign-stable both splits, stop5 not
  worse >2pp). Failures recorded in the §8 ledger and closed.

## 5. Waves

| Wave | Content | Owner | Gate |
|---|---|---|---|
| **W0** (now) | Wave-8 backtest (W-ARM/SHAKEN/CT-LANE); alert icon UI; board-track populate+fix | Sonnet ×3, Opus review | methodology review before full run |
| **W1** | Verdict → implement P1 states + P2 lanes in `build_stock_library` as chips/bonus + ledger fields; fixtures in tests | Sonnet | W0 verdicts |
| **W2** | P4 Running ledger strip + P5 arbiter/invariants + lane-then-alpha order + render alpha_entry | Sonnet | W1 merged |
| **W3** | P3 evidence stack v1 (chips + capped tilt + forward grades; GEX magnet/flip chips) | Sonnet | W1 merged |
| **W4** | Sector re-arm bus (sector confirmation events re-arm BASED constituents); basket tailwind inversion (phase score replaces 20d-rel) | Sonnet | W0/W1 verdicts |
| **W5** | Grading maturity review: precision@k new-vs-old order, ledger audit, promote/demote gate powers | Opus | 2–3 wks accrual |

## 6. Direct answers to the owner

- **"Why did REGN/VEEV disappear?"** They were never on the stock board; VEEV left the discovery
  *Avoid* list because it improved, REGN's basket page upgraded to BUY 12 days after your entry.
  Your instinct front-ran every surface we ship — the program's yardstick is now "would the new
  board have surfaced them?" (VEEV: Lane R candidate at the 06-22 washout; REGN: GEX-magnet +
  wait_pullback zone = evidence-stack candidate).
- **"How do we quantify extension?"** ATR-normalized extension-since-cross for price (per-name
  scale-free), and the weekly **RSI-MACD** histogram for the trigger (bounded RSI units ≈ scale-free
  across price/cap/sector). Band edges are swept in wave-8, not hand-set.
- **"MCK/MCD reconciliation?"** BASED/ARMED/SHAKEN states (P1) — MCK is the ARMED prototype (1.1
  weeks to cross), MCD the SHAKEN prototype. Both validated before gate power.
- **"Exceptions to the gate?"** Exceptions = named lifecycle states with forward grades, never
  silent overrides.

## 7. Guardrails (do not regress)

Honesty contracts stay (no return-alpha claims for timing); FRESH_TICKS=2 keeps its job in Lane T;
falsified ledger is law (H2/H4/BASED-chip/RETEST closed; F7 near-miss is context, not license);
display-first → grade → gate-power rollout for every new lever; JNJ/AMAT/ELV fixtures permanent.

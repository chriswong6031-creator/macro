# PROPHET US MISSED IGNITIONS — AUDIT + UPGRADE MASTERPLAN (BY FABLE)

**Date:** 2026-08-05 · **Trigger:** operator escalation — the US systems missed two broad
rally ignitions end-to-end: (1) the precious-metals ignition (silver +$6 off its $55 low,
gold +166, PGMs up, after ~3 weeks of basing that the operator saw by eye) while
`commodities.html` still printed "Momentum down" on gold/silver and "Cycle low" on silver,
the Sector Intelligence buy board had gold_miners on **reduce/avoid**, and China Sector
Intelligence had gold at the **top of its buy board all week**; (2) the Space theme
(RKLB/ASTS-class) washout-buy that no US board surfaced. Operator's standard: "we're not
asking it to produce alpha — we're asking it to observe, anticipate, feel and detect."

**Parents:** `PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (the funnel repair;
its §0 gates inherited), `PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` (the
composition roadmap; its §5 stand-in doctrine), `PROPHET_US_IGNITION_LAYER_W8` (#4564,
name-grain ignition sensors — this plan is the SECTOR/ASSET-grain complement and shares
no sensor with it), `CN_TO_US_PROPHET_HANDOFF_2026-08-04.md` (the method transfer this
plan executes at sector grain).

---

## §0 ACCEPTANCE GATES (inline in every build prompt spawned from this plan)

- **G0.1 (tier labels).** Every shipped surface/key is labeled `display` / `ops-telemetry`
  / `shadow-accrual` / `scored`. Nothing in this plan ships `scored`. Anything that later
  wants authority goes through its own prereg on the roadmap §3 ladder.
- **G0.2 (case receipts).** A wave claiming to fix a §2 defect reproduces the case from
  the shipped artifact in its PR body (gold_miners / silver / RKLB / ASTS receipts below).
- **G0.3 (population fences).** The graded board population, the buy lanes' membership,
  and every prereg-frozen constant (§6 fence table of the trend masterplan census) stay
  byte-identical. New lanes are watch-only, "never buy words" (CN precedent).
- **G0.4 (honest nulls).** Every new watch/turn surface carries its measured basis or its
  null disclosure in plain words: the sector washout→turn standalone construction is a
  measured NULL as a scored trigger (Oracle P8 P-W1; DNR §2 "Washout × turn"), so every
  surface built here is a *disclosure of engine state*, never a buy claim. Falsifier
  language stays background (operator 2026-07-27).
- **G0.5 (bilingual + design law).** All user-facing strings EN/zh; glance-tier word
  budgets; no internal study names front-facing; DESIGN_DOCTRINE + frontend-design skill
  before surface work; no third header family; no new page.
- **G0.6 (era honesty).** Any coverage or input repair to a forward-accruing organ stamps
  an era break in the organ's ledger/README (the #4579 disclosure pattern): the pre-fix
  window may not be cited as a null.

## §1 The failure, restated precisely

The ignitions were visible at three altitudes and missed at all three — for different,
now-measured reasons. The pattern across every layer is the same sentence: **the engines
saw it; nothing the operator looks at said so.**

| Altitude | What the engine knew | What the operator saw |
|---|---|---|
| Commodity (futures) | `technical_arming`: silver `basing=True, days_in_base=23` (the operator's "3 weeks"); cycle `pos` gold 1.7 / silver 1.0 / plat 0.9 (extreme lows); 12-m TSMOM **up** on gold/silver/platinum | "Momentum down" ×3, "Cycle low" on silver, empty basing board ("No washout or basing signals right now"), and the recovery signature scored as a **top-side** "divergence" |
| Basket/sector | `sector_cycles` forward log (2026-08-04): **`b-gold_miners: Trough, pos=2.0, osc_slope=+1.3, signal=BUY`**; `b-space_economy: Trough, pos=2.1`; both baskets exist with correct membership | Act board: gold_miners **reduce/avoid** (score 31, rank 44/47); no bottoming lane exists on the US board; the basket-turn organ has never once been able to print IGNITION (§2 D11-D12) |
| Name | RKLB flagged in `watch` 07-27 (DECLINE, correctly mid-washout); ASTS on the board 07-30/31 (COUNTERTREND BOUNCE) | RKLB silently vanished from every later snapshot; ASTS sized down with a caution citing the WRONG basket ("Defense & Aerospace below trend") while its space_economy membership was the sharp washout-recovery read |

China called gold because its machinery **guarantees a bottoming candidate is never
invisible**: a dedicated `bottoming_watch` lane (Trough + rising oscillator), the FT-R1
dual-read law ("may be bottoming" chip on reduce/avoid rows), and a basket-turn organ
rider — plus its committed data had already flipped r20 positive. The US board has the
same cycle engine, the same fresh data, **and none of the three surfacing mechanisms.**

## §2 Defect map (receipts; file:line as of this audit)

**Commodities pipeline** (`scripts/build_commodities.py`, data FRESH at T-2 — formula
and semantics lag, not collection):
- **D1** Momentum = 6 equal votes (EMA-trend, EMA20/50 cross, MACD hist, SMA200, ROC20,
  RSI zone) EWM-smoothed + tri-state hysteresis (enter |0.5|, exit 0.25, 3-day confirm)
  (`engine/commodity_signals.py:76-143`). On 08-03 gold voted macd +1, roc20 +1 — and
  stayed "bear" on the three slow anchors. A 3-week base-and-ignite is structurally
  invisible until EMA50 bends.
- **D2** Cycle phase direction vote = weekly MACD ×2 + 3D MACD ×1 + osc-slope tiebreak
  (`engine/sector_cycles.py:285-340`): silver at pos=1.0 stays "Trough"→"Cycle low" until
  the WEEKLY MACD turns — weeks of structural lag — and the glance copy reads as *avoid*
  when pos=1.0 is the cycle's buy zone.
- **D3** `technical_arming` catches the stoch curl only within 3 bars while %K<30
  (`config.yml:3884-3908`): silver's curl came and went; by 08-03 %K=55 → `armed=False`
  forever after. The one detector built for this exact moment has a 3-day shutter.
- **D4** `commodity_confluence` scores `ts_trend=up ∧ momentum_state=bear ∧ price
  elevated` as **top-side "exhaustion divergence"** (`engine/commodity_confluence.py:578-593`)
  — gold and silver both fired it AT THE CYCLE LOW (pos ≤ 2), actively counting the
  recovery signature as bearish. Bottom scores: gold 19, silver 16 vs `early_threshold=40`.
- **D5** Commodities feed no cross-asset surface: zero references in any Prophet/board
  path.

**US Act-Now board** (`engine/theme_scoring.py`):
- **D6** `_label()` first branch `r20<0 ∧ breaking → "deteriorating" → AVOID`
  unconditional (`theme_scoring.py:660-661`) — no basing exception, no dual read.
  gold_miners 07-31: score 31, rank 44/47, reasons "20d −8.1% vs S&P".
- **D7** `theme_intel.as_of = 2026-07-31` while `sector_central.json` on the same page is
  08-04 — the theme desk's member-price cache (deep `data/stocks/` store, 220/235 frames
  ending 07-31) lags the ETF cache by 2+ sessions. Named freshness defect.
- **D8** gold_miners absent from `_MACRO_PRIOR`/`_SECTOR_PROXY` → macro leg forced 0.
- **D9** No `bottoming_watch` lane, no FT-R1 dual-read chip, no turn-organ rider — the
  three CN mechanisms (`engine/china_act_now.py:348-391`) have no US counterpart, while
  the US input they need is computed nightly and fresh (`data/sector_cycles/
  forward_log.parquet`).
- **D10** `sector_central` conviction board correctly prints gold_miners "Bottoming ·
  turn signal BUY" then halves it under the validated 200dma drawdown gate → 56 =
  "Neutral", and nothing tells the operator "cycle says BUY, trend gate says wait."

**Basket-turn organ** (`engine/basket_turn_watch.py`):
- **D11** SPY benchmark unreadable since ship (2026-07-09) → 3 of 6 legs dead → IGNITION
  arithmetically unreachable (fix #4579, rebased by this session, merge-on-green armed).
- **D12** Members load ONLY from the deep `data/stocks/` store (235 names): gold_miners
  reads **1/12** members, space_economy **0/15** — silently (`basket_turn_watch.py:
  257-275,998`). #4579's ladder is deliberately benchmark-scoped and does NOT fix this.
- **D13** No member-coverage disclosure on the artifact; a basket scored on 1 member
  prints indistinguishably from a fully-read one (the `dead-shared-input` trap class).

**Theme rotation / Theme Tape / Foresight:**
- **D14** Theme Tape floor `emerging_score>0 ∧ quadrant∈{leading,improving}`
  (`engine/theme_tape.py:586-604`): a washout-turn prints 1W **up** / 1M deep down →
  quadrant "lagging" → structurally invisible. Space Tech ranked 28/41 with every one of
  its 5 subsectors turning up on 1W. The tape cannot say "washed out, now turning".
- **D15** Foresight Desk theme `space_satellite` = {IRDM, GD, LHX, RTX, HWM, BWXT}
  (`config.yml:1351-1353`) — defense primes; RKLB/ASTS/LUNR/PL absent. Layer-7
  anticipation is structurally blind to new-space.

**Prophet US name chain:**
- **D16** Universe is NOT the blocker: NEM (breadth), HL/CDE/MP (midcap), GOLD/SSRM
  (russell), AEM/AU/KGC/EGO/RKLB/ASTS/LUNR (extras) all resolve. Exclusion is downstream.
- **D17** The 200dma reclaim veto (`signal_quality.py:207-225`, US default ON) is
  unsatisfiable during a genuine washout (a name 17% below the line cannot reclaim it in
  2 bars). HK measured the identical leg refusing 12 names that ran +8.7%..+44% and
  dropped it with an era stamp (#4470, `hk_prophet_v2`). The US has never assembled its
  own decision packet.
- **D18** `stage_for` routes **BOTTOM WATCH** (`dir="down"` in the display ladder) to
  STAGE_BLOCKED unconditionally (`us_board_rank.py:376-423`) — the basing state itself
  is invisible-by-construction. This clause is an unmeasured implementation choice, not
  a prereg-frozen rule (census verdict).
- **D19** The caution-basket rule cites the name's BEST-ranked basket
  (`build_stock_library.py:2609-2624`): ASTS was sized down citing flat Defense &
  Aerospace while its space_economy membership read washout-recovery. One membership's
  state silently overwrote the other's.
- **D20** Door R requires `above200 ∧ weekly_bull` — no door exists for the washed-out
  cohort, and Door T inherits D14's RRG floor through theme heat.
- **D21** `prophet_postmortem` grades from the four breadth caches only: ASTS sits in
  `tickers_no_price_path` (12 names) — extras-universe board rows are structurally
  ungradeable today.

## §3 Root-cause synthesis (ranked)

1. **RC-A — Assembly, not detection.** The cycle engine, the basing detector, and the
   taxonomy all fired. No lane, chip, or copy carried the state to a decision surface.
   (D9, D14, D18, D10, D5 — the Mag-7 "detection-without-narration" class, now proven at
   sector grain.)
2. **RC-B — Momentum-monoculture states.** Every surfaced verdict (act-board label,
   commodity momentum cell, tape floor) is a trailing-window momentum read with no
   second axis; a washout-turn is by definition the state momentum lenses certify last.
   (D1, D2, D6, D14.)
3. **RC-C — Silent coverage holes.** The one organ purpose-built for basket ignition ran
   with a dead benchmark AND a member store missing 92-100% of exactly the baskets that
   ignited — both silently. (D11, D12, D13, D7.)
4. **RC-D — Perverse scoring at the boundary.** The recovery signature (long-trend up,
   short-momentum still bear) is actively counted AGAINST the bottom (D4); the caution
   system cites the wrong basket (D19); "Cycle low" copy reads as a warning (D2).
5. **RC-E — No lawful door for the washed-out cohort.** (D17, D18, D20 — the deliberate
   anti-chase architecture correctly refuses to CHASE, but it also has nowhere to WATCH.)

## §4 Design principles

- **P1 — Wire before invent** (inherited). Every wave composes organs that exist and are
  fresh tonight. The only new detector work in this plan is the ROC battery (research).
- **P2 — Watch-lanes, never buy claims.** The sector washout→turn scored construction is
  a measured null; everything here ships as state disclosure with "watch, don't chase"
  vocabulary — exactly the compliant CN form.
- **P3 — A state the engine holds must be visible somewhere the operator looks, with the
  conflict printed when two lenses disagree** (cycle BUY vs trend gate; TSMOM up vs
  hysteresis bear; defense flat vs space recovering). Dual-read chips, not resolution.
- **P4 — Coverage failures must be loud.** Member-coverage counts on artifacts, warnings
  at thresholds, era stamps on repairs.
- **P5 — CN stays untouched**; its lanes are the reference implementation and control.

## §5 The program

### W-A — US Bottoming Watch lane + dual-read law (display; the CN port)
New `engine/us_act_now.py` assembling the Act board payload the template already reads:
lanes buy/wait/reduce unchanged from `theme_intel.act_now`; NEW `bottoming_watch` lane =
US baskets/sectors with `phase=="Trough" ∧ osc_slope>0` from `data/sector_cycles/
forward_log.parquet` (the exact CN rule; gold_miners qualifies on tonight's data), with
`signal=="BUY"` rows annotated "cycle turn signal — watch only"; FT-R1 dual-read chip on
reduce/avoid rows that also qualify ("may be bottoming"); the trend-gate conflict from
D10 printed as the row's second line ("cycle says turn; below 200-day trend — gate
shut"). Never-buy words, EN/zh, capped rows, honest-null state ("no basing candidates").
*Routing: builder (opus) with the CN lane as pinned reference; template edit scoped to
the Act-board section of `sector_central.html.j2`.*

### W-B — Basket-turn organ: member ladder + coverage disclosure (infra; after #4579)
Member loads walk `("stocks", "baskets/ohlcv")` (the `audit_universe.MembershipResolver`
precedent) — benchmark ladder from #4579 untouched; per-basket `members_read/members_total`
on every artifact row; `::warning` when coverage <60%; era-break stamp in the ledger
README (G0.6): the pre-fix window's emptiness may not be cited. *Routing: builder (opus);
rebases on #4579's merged head.*

### W-C — Commodities honesty + ignition repairs (display)
1. **Divergence de-perversion (D4):** the top-side divergence condition additionally
   requires the cycle NOT in Trough/Recovery (pos>32) — at the low, TSMOM-up ∧
   hysteresis-bear is the recovery signature; below the threshold it stops feeding the
   top score and instead surfaces as a "turn developing — momentum read lags" chip.
2. **`armed_recent` (D3):** display state = basing ∧ (stoch curl within 10 bars ∨ %K
   traversed <30→>50 during the base's exit); the strict 3-bar `armed` stays untouched
   for the prereg. Copy: "Igniting — early turn confirming, watch only."
3. **Momentum dual-read (D1):** when momentum_state=bear ∧ ts_trend=up ∧ roc20>0 —
   the cell gains "read being updated — short-term thrust against trend anchors" (house
   'read being updated' idiom) instead of a bare "Momentum down".
4. **Cycle-low copy (D2):** Trough + basing renders "At cycle low — basing" (EN/zh), a
   state description, not a warning.
*Routing: builder (opus). Config-tier formula edits documented in the page's method
notes; the confluence prereg (`COMMODITY_BOTTOM_TOP_PREREG.md`) gains an amendment row
recording the divergence gate change BEFORE its gauntlet ever runs.*

### W-D — Theme Tape washout-turn lane + Foresight space membership (display)
1. Theme Tape gains a second, clearly-labeled section below the heat rows: **"Turning
   from washout — early, unconfirmed"** = themes failing the RRG floor with (1W rel >
   +2% ∧ 1M rel < −10%) ∨ basket-turn state ∈ {BASING, TURNING} once W-B lights it.
   Same member-state narration as the main rows; capped at 3; honest-null.
2. `space_satellite` foresight theme gains RKLB/ASTS/LUNR/PL/RDW alongside the primes
   (the desk's supply-chain legs read the same stores for these).
3. **Caution dual-read (D19):** when the cited best-ranked basket and another membership
   disagree on state (one flat/deteriorating, one Trough-recovering), the caution line
   discloses both ("Defense flat; Space Economy turning from washout").
*Routing: builder (opus); tape template collision with #4553 checked at rebase.*

### W-E — Prophet chain: basing visibility + basket-grain miss telemetry (display/ops)
1. **`basing` stage (D18):** BOTTOM WATCH names with a cascade-eligible-or-near verdict
   get stage `basing` (a visible shelf with "basing — no entry signal yet" words) instead
   of vanishing into STAGE_BLOCKED. Graded population untouched (stages are
   presentation); the RKLB case reproduces as the PR receipt.
2. **Basket-grain miss layer (ops):** `prophet_miss_audit` gains a nightly block — for
   each basket, EW 5d/10d return vs board representation; a basket in its top decile of
   own-history 10d return with zero board names prints as a named miss ("the gold
   question", automated).
3. **Postmortem closes ladder (D21):** the grading resolver walks breadth caches →
   `data/baskets/ohlcv` → extras, ending the `tickers_no_price_path` class for
   extras-universe names (ASTS).
*Routing: builder (opus).*

### W-F — Reclaim-veto decision packet (research; operator-gated)
Assemble the US mirror of HK's #4470 evidence: every name refused SOLELY by the reclaim
leg over the trailing 126 sessions, with forward returns from the refusal day, split by
drawdown depth — the honest cost/benefit of the veto on the current US tape, beside the
validated drawdown benefit it was shipped for. Ships as a research doc + committed
receipts; **no flip** — an era-stamped `us_prophet_v2` is the operator's call. (The
HK receipts: 12 refused names, +8.7%..+44%.)

### W-G — ROC Extremes & Burst-Grammar battery (research; running)
Four sensors at the grains the kills leave open — S-ROCX-TOP (per-name-percentile ROC(12)
extension extremes inside uptrends, with the mandatory ext_z redundancy fence),
S-ROCW-GRAIN (washout extreme + stabilization at basket/ETF/futures grain — deliberately
NOT name-grain), S-BURST-RHYTHM (the ASTS burst-rest-burst grammar), S-ROC12-TERM (does
an extreme ROC(12) mark the local top — the operator's ">80% terminates" claim, per-name
percentile primary, absolute bands descriptive). W4 gate-matched ruler, month-block
bootstrap, backward-only stamping. Verdicts feed: the "extended" display chip charter
(if TOP validates), the US extension-read port of China's validated F6 construction, and
the burst-profile dossier block. `research/prophet_us_audit/roc_extremes_battery.py`.

### W-H — Silver sleeve (taxonomy)
`silver_miners` basket (the sleeve the gold_miners charter explicitly deferred), members
gated on `data/baskets/ohlcv` presence; ETF proxy SIL (proxy-only if the series is
uncollected, disclosed). Turn-watch and cycle engines inherit it on their next nightly.

## §6 What this plan does NOT do

- No scored authority anywhere; no board-population change; no prereg-frozen constant
  moves (FRESH_TICKS=2, reclaim veto, not-topped legs, door constants, tier weights).
- No revival of killed constructions: sector washout→turn as a scored trigger (P-W1
  NULL), bottom-radar PRIMED gating, washout×turn entry seed, xsec commodity momentum,
  FRESH_TICKS widening. The watch lanes surface ENGINE STATE with the null disclosed.
- No parallel rotation-schedule surface (DNR row 54) — everything lands on existing
  pages/organs. No Ignition-Radar re-surface (row 152 gate unmet; the radar's own record
  keeps accruing untouched).
- No forced directional calls (row 117): every new surface is watch-vocabulary, and the
  one place a "BUY" word from the cycle engine appears (W-A) it is quoted as the organ's
  own registered signal with its gate conflict printed beside it.
- No LLM-originated signals (A7). No CN-side edits.

## §7 Ship order + collision fences

| PR | Content | Depends on |
|---|---|---|
| 1 | This masterplan | — |
| 2 | W-G battery + results + tests | — |
| 3 | W-C commodities repairs | — |
| 4 | W-A bottoming watch lane | — (template region fenced vs #4572/#4497) |
| 5 | W-D tape lane + foresight + caution dual-read | #4553 rebase check |
| 6 | W-B member ladder + coverage | **#4579 merged** |
| 7 | W-E basing stage + miss layer + closes ladder | — |
| 8 | W-H silver sleeve + W-F decision packet | — |

## §8 Success metrics (graded by the miss-audit once W-E.2 lands; baselines = this audit)

| Metric | Baseline (2026-08-05) | Target |
|---|---|---|
| Sector-grain miss latency: basket top-decile 10d move → first surfaced state | ∞ (no surface existed) | ≤1 nightly |
| Bottoming candidates visible on a decision surface | 0 lanes | 100% of Trough∧rising rows, capped |
| Basket-turn member coverage disclosed | 0/47 baskets | 47/47, warning <60% |
| Commodity ignition states | armed shutter 3 bars, divergence perverse | armed_recent ≤1 nightly lag; divergence fenced at pos≤32 |
| Washout-turn themes on the tape | invisible (RRG floor) | labeled section, ≤3 rows, honest-null |
| Extras-universe gradeability (ASTS class) | 12 names ungradeable | 0 |

*Related: SECTOR_BOTTOM_RADAR.md (validated sector-grain bc machinery — the future
promotion path for lane ordering), FAST_TURN_TWO_SPEED_TAPE_MASTERPLAN (turn-watch
governance), ORACLE_GAUNTLET_P8 (the null that scopes §4-P2), #4470 (the HK era-stamp
precedent W-F mirrors), #4579 (the benchmark heal W-B stacks on).*

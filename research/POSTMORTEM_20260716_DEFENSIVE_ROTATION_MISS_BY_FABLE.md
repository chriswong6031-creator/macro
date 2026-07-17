# Postmortem 2026-07-16 — the defensive/healthcare rotation miss, the full-system audit, and the XSR program charter

Status: ADJUDICATED BY FABLE (main loop), 2026-07-16. Third rotation-miss postmortem in 21 days
(after `POSTMORTEM` in #2286 / Rotation Command, 06-25 semis→Mag7; and
`POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md` / MLC, 07-14). This document is (a) the tape
postmortem, (b) a cross-cutting audit of why the whole sector stack keeps missing rotations,
and (c) the charter for the **XSR program (Cross-Sector Rotation & Fast Clocks)**, XSR-R1..R14.

Evidence basis: five internal audit lanes (board artifacts, ranker methodology, local-store
rotation timeline, regime/dispersion wiring, live-site extraction) + one adversarially-verified
web research pass (107 agents; findings cited below as [DR-n], all 3-0 or 2-1 verified unless
noted). Registry check done: `docs/ACTIVE_BUILD_MAP.md` (2026-07-16, 0 open PRs) and
`research/DO_NOT_REBUILD.md` reviewed in full before chartering; constraint map in §6.

---

## 0. Executive verdict

The operator asked why no major board recommends healthcare (REGN/MCK/BMY/GILD, WM/KO) while
a defensive rotation is visibly underway. The audit's answer:

1. **The signal was in our own stores weeks ago.** A 10d relative-strength window flags the
   healthcare names on **2026-06-10 (23 sessions before today)**; healthcare-vs-tech member
   breadth crossed on **06-04/05** and reached a +56pp spread by 07-07. XLV itself flipped
   05-19. Nothing consumed any of it.
2. **The conviction ranker cannot see moves younger than ~2 months.** The score is dominated
   by a 252d oscillator + 200d/252d trend gate; the only sub-63d input is a 22d slope
   tiebreaker. Measured lag to top-3 for a fresh leader: **40–60 trading days.**
3. **The system detected the regime and routed it nowhere.** COR1M at percentile ~1, DSPX at
   percentile ~98 (our own VSB collectors), healthcare breadth 83% vs tech 37% (a parquet with
   zero consumers), `rotation_events` "ai_semis→mag7 MAJOR day 9", mag7 `running_narrow`,
   flow lens "Health Care confirmed, rs_pctile 0.93" — **sixteen distinct display-only
   dead-ends**, plus a `config.yml sector_preferences` table (Q3/Q4 → XLP/XLV/XLU) that
   `sector_central` never imports.
4. **On 07-15 the Act-Now BUY list was `[mag7, payments_fintech, financials]`** — steering
   users into the rugpull the night before it happened, while the pick lab held WM at
   "BUY NOW" and BMY at "HALF SIZE / now" **gated ineligible** (sector headwind: XLV=Reduce).
5. **The research layer already made the call.** `JULY_2026_MARKET_NAVIGATION_PLAYBOOK.md`
   (07-13, #2545) recommended *"selective healthcare… MCK-led basket (MCK, GILD, BMY, REGN)"*
   — the exact trade — and is wired to no surface.
6. **This is the third identical miss.** Same seven root causes as 06-25 and 07-14. The
   postmortem→program loop keeps producing display-tier context organs that the boards ignore,
   and in one case (Leadership Board, #2580) the fix was removed from the macro page days
   after shipping (#2604/#2608).

The failure class is **clocks + grain + ontology + wiring + cadence**, not missing detectors.
XSR is chartered as a *wiring and clocks* program: connect what exists, at display tier, under
the operator-ratified China #2634 precedent, with forward grading from day 1 and promotion
preregs as the only path to authority.

---

## 1. What happened on the tape (internal stores + verified external timeline)

### 1.1 Verified external timeline [DR]

- **06-03** — SpotGamma flags **DSPX at Covid/Apr-2025 crisis extremes while COR1M nears its
  all-time low** — an unprecedented combination (prior dispersion extremes came *with*
  correlation spikes), attributed to concentrated AI-name chasing creating "positioning risk
  for the stock market". Our own Cboe store confirms COR1M 6.32 on 06-03 = 0.29th percentile
  of 20y history. **The regime was quantitatively flagged six weeks before the unwind, on
  instruments we collect nightly.** [DR-0, DR-1]
- **06-25** — memory/semis top: SK Hynix Seoul intraday record (on its Nasdaq ADR listing
  announcement), Micron record $1,255. [DR-2]
- **07-01/07-02** — US memory dump (MU/SNDK −10%+) → Korea capitulation (Hynix −14.6%,
  Samsung −9.1%, KOSPI −7.9%). [DR-3]
- **07-07** — memory complex in technical bear market; ~$1.5T semi market cap erased since
  06-25. [DR-2, DR-4]
- **07-13** — record crash: Hynix −15.4% (worst session in company history; HBM4
  ramp-shortfall note), KOSPI −8.95% with a 20-minute circuit breaker (7th of 2026),
  Samsung −10.7%. [DR-5, DR-6]
- **July Mag-7 leg** — ~$3.2T swing: Mag 7 +$1.5T while semis ex-NVDA −$1.7T; AAPL prints a
  record close 07-15 (327.50, confirmed in our store). By 07-16 the leg is fading (GOOGL −4%,
  MAGS flat). [DR-13]
- **07-16** — TSMC's capex-raise/margin-compression guide (not Korea) is the proximate
  catalyst; AMD/INTC −4-6%, neoclouds derate further (NBIS −14%; month: NBIS −36%, CRWV −28%),
  Asia re-crashes (Hynix −11.5%, Samsung −8.8%). **At the US index level the day was NARROW:
  only Tech (−2.28%) and Comms (−0.63%) fell; 358/503 S&P names were green; S&P −0.51%; VIX
  16.73.** Staples/healthcare/real-estate led, healthcare partly on earnings catalysts
  (ABT +12%, UNH +5.6%). [DR-8, DR-9, DR-10, DR-11, DR-12]
- **Mechanism discipline** — BIS Bulletin 95 (Aug-2024 episode): do **not** attribute index-vol
  events to "dispersion-trade unwinds" without index-option flow evidence. COR1M had still not
  spiked as of 07-15 (3.70) — the dispersion regime had not yet resolved into correlated
  selling. [DR-14]

### 1.2 The rotation was detectable in our own stores — onset table

From `data/yahoo` / `data/stocks` closes through 07-15 (10d rolling excess vs SPY, sustained
≥3 sessions):

| Group | First sustained 10d-RS signal | Sessions before 07-16 |
|---|---|---|
| XLV (ETF) | **2026-05-19** | 38 |
| HC names {MCK,REGN,GILD,BMY} EW | **2026-06-10** (5d: 06-05) | 23 |
| Defensives {KO,MCD,WM} EW | **2026-06-05** | 26 |
| SMH negative flip | **2026-07-02** (5d was noisy/false in June) | 8 |

Member breadth (%>20dma): healthcare crossed above tech **06-04/05**, peaked at **+56pp**
(07-07: HC 96.7% vs tech 40.6%). The 07-14/15 HC-breadth dip (to 63-67%) is the JNJ/LLY
correction — both peaked 07-07 and drew down −7.6%/−6.4%, dragging cap-weighted XLV while the
mid-cap rotation continued underneath. MCK's surge is a recovery (still ~20% below its high),
not an extended breakout — precisely the profile a fresh-turn lens should catch and a 12-1
momentum lens structurally cannot.

Honest counterpoints the data adds: **XLP as an ETF is not leading** (negative excess on every
window; KO/WM lead, MCD is the worst name in the group on every window — the operator's "MCD
turning" is a fresh-turn hypothesis, not yet confirmed); and realized cross-sectional
dispersion normalized after April — the live signature is **implied** (DSPX/COR1M) plus the
**SPY-vs-QQQ realized-vol spread** (QQQ 20d RV spiked to 35% on 07-06 while SPY stayed
~14-16%). Detector constructions in W4 must use those, not realized cross-sectional std.

---

## 2. What the product said (as of 07-15/16)

| Surface | Healthcare verdict | Tech/semis verdict | Right? |
|---|---|---|---|
| sector_central (07-16) | **#10/11, score 24, Reduce** (RS #3 "leading" shown beside it); Managed Care 16 = lowest basket in system | XLK Cautious 31 + SELL; XLU **#1 Accumulate 75 (RS #10)** | Wrong on HC entry; right on semis; laggard-buying on XLU |
| us_stocks Act-Now (07-15) | Big Pharma TRIM, Managed Care TRIM; XLV "NEARING A HIGH", entry quality −43 | **BUY = [mag7, payments_fintech, financials]** | Steered into the 07-16 rugpull |
| pick lab (07-15) | REGN 9, MCK 27, BMY 48 "HALF SIZE/now", GILD 4 — **all `gate_state=ineligible`**; WM 49 "BUY NOW/now" also ineligible | — | Gates suppress the correct names |
| allocation model | holds managed_care since 07-01 (label now TRIM) | **holds memory_storage as LEADER** mid-unwind (63/126/252d exit gate ≈ needs −38% cum.) | Worst surface of the audit |
| subsectors.html (live) | pharma on **HEADWIND board, "TOPPING/avoid"**; Entry-Now = HC REITs + medical instruments, both "EXTENDED/avoid" (all 5 entry-now rows are avoid-class — board self-contradiction) | — | Operator's observation confirmed |
| subsector_rotation.html | zero HC/defensive events; **all 6 rotation events intra-XLK** | ai_semis→mag7 MAJOR day 9 confirmed | Cross-sector rotation unrepresentable |
| Turn Desk (ruled canonical rotation surface) | `rotation_tag: quiet`, 0 active episodes; `oracle_turn_desk.json` artifact absent | — | Silent |
| Display-only context that had it right | subsector_rotation alerts (Diagnostics "rotating in" TODAY; Therapeutics 07-10; Genomics 07-07; Aging Pharma 07-08); flow lens HC "confirmed" rs_pctile 0.925; XLV 1M flows +$461M; cycle-DNA narrative *"cheap-quality defensive rotation beginning to assert itself"*; macro seasonality box "Favor XLV·XLP·XLU"; altdata convergence BMY/GILD/MCK; **07-13 playbook: MCK/GILD/BMY/REGN basket** | vol_weather COR1M pctile 1 / DSPX pctile 98; breadth_split AI −19.6pp; mag7 running_narrow; sector_breadth XLV 83.1% vs XLK 37.5% (no consumer) | All unwired |

The product's message to a user on 07-15/16 was: *trim healthcare, buy Mag 7 / financials /
utilities*. The correct message (operator's, and the private playbook's): *rotate into
mid-cap healthcare + selective defensives; tech is distribution*.

---

## 3. Root-cause anatomy — five failures plus a meta-failure

**F1 — Clock failure.** Conviction runs on 252d constructions; rotations happen on 5-20d
clocks. Measured ranker lag 40-60 sessions; the earliest correct call (10d RS, 06-10) beat the
ranker's earliest possible call by ~2 months. The only sub-63d conviction input is a 22d slope
tiebreaker (`sector_cycles.py:628`). China was fixed for exactly this (#2634); the US wasn't.

**F2 — Grain failure (the aggregate veto, now bidirectional).** 06-25: semis-poisoned
cap-weighted XLK vetoed Mag-7 members (RC-1). 07-16: JNJ/LLY-poisoned XLV (both peaked 07-07)
vetoes MCK/REGN/GILD/BMY members — BMY "HALF SIZE/now" and WM "BUY NOW" sit gate-ineligible
under a sector-headwind rule. Same bug, opposite direction, one month apart.
`sector_fragmentation` exists to detect exactly this ("is the aggregate representative?") and
is display-only.

**F3 — Ontology failure (buy-the-laggard).** `state = 0.6·(50−pos)/50 + …`
(`sector_central.py:257-281`) structurally scores washed-out sectors as attractive and strong
sectors as dangerous: XLU = Accumulate 75 at RS #10; XLV = Reduce 24 at RS #3. Diagnosed
verbatim in MLC-4.3 on 07-14; unchanged. A cycle-position clock is a *mean-reversion* lens; in
a leadership-rotation regime it is the wrong mode, and there is no mode switch.

**F4 — Wiring failure (asymmetric, 16 dead-ends).** Detection→consequence paths found: one
(MRS credit gate — currently reading Goldilocks, so inert). Dead-ends: COR/DSPX chips,
corr_floor_break, breadth_split, sector_breadth parquet (zero consumers), mag7 trend_state,
leadership_regime, rotation_events (`may_rank:false`), fragmentation, bottom/sector_bottom
radars, narrative_brain (degraded), preference table (never imported), flow lens, ETF flows,
subsector rotation alerts, seasonality box. Under MLC-R8 the system may de-escalate displayed
buys but nothing may escalate — so context can only ever make the boards *more* bearish,
never rotate them *toward* a new leader. The de-escalation half is also incomplete: mag7
rolling over cannot demote mag7 from Act-Now BUY same-day.

**F5 — Cadence failure.** The intraday fastpath refreshes price-driven leaves only (overlay,
risk_state, heatmap, basket pulse). No conviction-relevant organ (sector_central, mag7_regime,
vol_weather scoring, breadth) runs intraday; today's Mag-7 rollover was invisible to every
scored surface all day. China has a live risk-state lane (#2549); the US has none for sectors.

**F6 — Meta-failure (the postmortem loop itself).** Three misses, three programs (RC, MLC,
now), each shipping display-tier organs that the ranked surfaces ignore; promotion studies
(RC S1/S2) honestly ACCRUE at n=13<20, so no authority path has opened; one shipped fix was
removed from its page days later; the one document that called the trade (07-13 playbook) had
no surface. Detection keeps improving; **recommendation surfaces have not changed since before
the first miss.** Separately, the 07-16 healthcare pop was partly earnings-catalyzed
[DR-9] — even perfect rotation wiring would have caught the *trend* (June onset), not
predicted the *day*; the goal is the former, and honesty about that belongs in the copy.

---

## 4. Why the prior fixes didn't fire

- **RC rotation_events**: fires only within registered sector legs; all 20 ledger events are
  intra-XLK; no cross-sector pairs exist in `config/sector_legs.json` → tech→healthcare is
  *unrepresentable*, not merely undetected.
- **Turn Desk** (ruled canonical, #1750): keyed to Oracle sector-ETF episodes (A15: washout +
  ≥2 opposite-complex sectors rotating out); zero active episodes; artifact missing on site.
- **MLC W2b stance matrix + conflicted shelf** (#2635, merged 07-16): first nightly render
  pending; artifact absent in site/ at audit time; and by design it is disclosure +
  de-escalation only.
- **VSB (COR/DSPX)**: collectors + vol-weather organ shipped 07-13/14 — the instruments that
  gave professionals a six-week lead [DR-0] — explicitly "never scored, no forward claim."
- **RC S1/S2**: ACCRUE (n=13; med x_sector_20 −0.24pp, WR 46%, p_adj 0.71) — honest nulls; no
  stance authority. (Correctly so: the gauntlet is a promotion gate, and it has not passed.)
- **narrative_regime**: retired (D7); **defensive-rotation Phase-0** (XLU-bottoming ×
  tech-topping as a *vol-shock predictor*): FALSIFIED — a construction-scoped kill; it does not
  block defensive-rotation *display detection* on other constructions.

---

## 5. What the professionals used (external, verified)

The one documented leading indicator that beat price RS was the **DSPX-high / COR1M-low
divergence, flagged 06-03** — six weeks ahead [DR-0, DR-1]. We collect both series nightly
(VSB W1, `data/cboe/`). Secondary confirmations available same-week in our stores: healthcare
member-breadth crossover (06-04/05), 5-10d RS onsets (06-05..06-10), ETF flow divergence, and
the SPY/QQQ realized-vol spread. External coverage of *flow-based* early detection was thin
(the deep-research pass found no surviving hedge-fund positioning/fund-flow claims for the
healthcare bid, and BIS cautions against unwind narratives without flow evidence [DR-14]) —
so XSR's detectors stand on price/breadth/vol-surface constructions we can compute locally,
with flows as display context only.

---

## 6. Constraint map (registry + rulings honored by this charter)

Binding: no `sector_rotation_schedule.v1` parallel surface (fold into Turn Desk /
`oracle_state.json` Family-D, #1750); rotation × cycle-position **entry-confluence** DON'T-TEST;
rs-based member-dispersion **gates** DON'T-TEST (display OK); positioning fusion ILLEGAL;
LLM-originated signals/scores FORBIDDEN (de-escalation only); calendar-gated risk legs
FORBIDDEN; MLC-R8 (overlays demote, never originate/upgrade a displayed buy); US stock-table
rank-blend Phase-0 NULL (no timing-into-rank re-blend); short-side = AVOID-not-SHORT; verdicts
only at pre-declared horizon rulers; "validated" wording CI-gated.

Distinction relied on: the **China #2634 display re-rank** (fast RS + state governor + OB
penalty, operator-ratified, "ONE rank system page-wide") is house-legal precedent that a
*display-tier re-ordering of a board* is neither an entry gate (so the rotation×cycle
DON'T-TEST does not apply) nor an escalation of a calibrated key (MLC-R8 untouched). XSR W1
copies that shape exactly.

---

## 7. The XSR program (Cross-Sector Rotation & Fast Clocks) — rulings and waves

Mission: make the boards say, at display tier and within house law, what the system already
knows — with clocks matched to rotation speed, grain matched to where trades live, one
coherent glance verdict, and a graded forward record from day 1.

### Rulings

- **XSR-R1 (consume, don't rebuild).** No new detection engines where an organ already exists
  (COR/DSPX, breadth, fragmentation, rotation_events, mag7_regime, flow lens, subsector
  rotation). Extends MLC-R1. Waves below are wiring, porting, and registration.
- **XSR-R2 (US Fast Sector Lens).** Port the #2634 display re-rank to US sectors + named
  baskets: mom20 anchor + state-gated 5d/10d fast RS + ladder governor + OB penalty
  (max of ETF vs EW-member oscillator — the anti-JNJ/LLY-poisoning term) + gated MACD-cross
  demotion. Display-tier ONLY; re-orders sector/basket boards; ONE rank system per page
  (China lesson: no dual ranks). Forward-graded from first render under a pre-declared 10/20d
  excess ruler. Never gates, sizes, or feeds any calibrated key.
- **XSR-R3 (cross-sector pairs).** Register donor→receiver complexes in the rotation_events
  config: XLK↔{XLV, XLP, XLU, XLF}, semis-complex↔defensive-complex, mag7↔EW-market. Events
  remain display; new columns fold into Turn Desk / `oracle_state.json` as Family-D per #1750
  (no parallel surface). Owner: RC (this is an RC-R14-style extension, not a new program).
- **XSR-R4 (receiving-sector detector).** A `sector_breadth.parquet` consumer at last: flag a
  sector when member %>20dma crosses a donor sector's AND its own 60d mean while rising, with
  fast-RS confirm. Chip on sector boards + Turn Desk column. Expected-null forward ledger;
  display-tier; breadth *display*, never a gate (respects the rs-dispersion-gate kill).
- **XSR-R5 (dispersion-regime state).** A calendar-agnostic context state from COR1M pctile +
  DSPX pctile + SPY/QQQ 20d RV spread (constructions per §1.2; realized cross-sectional std
  explicitly rejected). Two lawful consequences only: (a) prominence — in dispersion regime,
  boards lead with the Fast Lens view and print the split; (b) **de-escalation** of
  laggard-Accumulate calls (cap Accumulate→Constructive when RS rank ≥9 and receiving-sector
  evidence points elsewhere) per MLC-R8. No escalations, no score fusion.
- **XSR-R6 (aggregate-veto honesty).** When `sector_fragmentation` flags a sector
  non-representative, sector-headwind suppressions (pick lab, subsector confluence,
  theme_scoring demotion) must render as **disclosed split-view** ("stock says BUY NOW; sector
  aggregate says Reduce; aggregate is fragmented — members diverge") instead of silent
  `ineligible`. Changing any gate from veto→non-veto is an authority change: requires operator
  ratification per lane (precedent: #2628 cascade gate swap). Disclosure itself ships freely.
- **XSR-R7 (US intraday fast lane).** Extend the existing 30-min fastpath with price-only
  recomputes of: Fast Lens re-rank, mag7 trend_state, rotation-event day-advance, dispersion
  state. Display + alerts only; nightly remains the sole ledger advancer; intraday lanes
  discard `data/` writes (house law). Precedent: China live risk-state (#2549).
- **XSR-R8 (research-desk bridge).** Operator-ratified playbooks/desk notes get a surfaced
  "House research" panel (title, date, thesis chips, link), provenance'd and dated, display
  tier. This is publication of ratified research artifacts, not LLM runtime origination; the
  A7 ORIGINATE ban is untouched. The 07-13 playbook would have been visible.
- **XSR-R9 (coherence completion — owner: MLC).** The stance matrix (W2b) extends to the
  sector boards: wherever conviction and Fast Lens/RS disagree ≥2 tiers, the glance verdict
  renders the split explicitly (MLC-R7), plain words, e.g. XLV: *"Slow clock: extended after
  the May run. Fast tape: money rotating in — mid-caps leading. Split view."* No silent
  averaging; no banned vocab.
- **XSR-R10 (ontology repair is a study, not a patch).** The `(50−pos)/50` laggard bias may
  not be hot-fixed by sign flips or ad-hoc reweights. A state-conditional scoring study
  (mean-reversion mode vs rotation mode) must be pre-registered with frozen rulers before any
  conviction-formula change. Until then the fix is coherence + Fast Lens prominence, not
  formula surgery.
- **XSR-R11 (grade the meta-loop).** One rotation-miss ledger (06-25, 07-14, 07-16 seeded).
  Every future miss appends a row with which XSR surface caught it and how early. The program
  is judged on lead-time-to-board, not organ count.
- **XSR-R12 (allocation honesty).** The allocation model's holdings render with a fast-tape
  disagreement chip (it held memory_storage as leader through a −20% unwind). Changing its
  exit rule is authority — deferred to its own prereg; disclosure ships now.
- **XSR-R13 (promotion path).** Preregs S-XSR-1 (Fast Lens top-3 vs conviction top-3, 10/20d
  excess, era-split, episode-permutation primary) and S-XSR-2 (receiving-sector detector
  lead-time vs 63d RS baseline) registered before any outcome is read. Authority only through
  the gauntlet; nulls printed; non-standalone survivors retained as confluence inputs.
- **XSR-R14 (non-goals).** No new parallel rotation surface; no positioning fusion; no
  vol-shock prediction revival (falsified construction stays dead); no US stock-table rank
  re-blend; no shorting lobe; no calendar-gated legs; no LLM-originated scores.

### Waves

| Wave | Content | Owner / tier |
|---|---|---|
| W1 | US Fast Sector Lens (#2634 port: engine + sector_central/us_stocks board re-rank + forward ledger) | XSR / display |
| W2 | Cross-sector pair registration + Turn Desk Family-D columns + rotation-events cross-sector lane | RC extension / display |
| W3 | Receiving-sector breadth detector (sector_breadth consumer) + chips | XSR / display |
| W4 | Dispersion-regime state + prominence switch + lawful de-escalations | XSR+VSB / display + de-esc |
| W5 | Aggregate-veto split-view disclosure (pick lab, subsectors, theme_scoring); ratification docket for any gate swaps | XSR / display, gates pending ratification |
| W6 | US intraday fast lane (fastpath extension) | XSR ops / display |
| W7 | Research-desk bridge panel | XSR / display |
| W8 | Coherence completion on sector surfaces (stance-matrix extension) | MLC / display |
| W9 | S-XSR-1/2 preregs frozen; grading live; promotion review on maturity | XSR / evidence |

Acceptance for the program (XSR-R11 ruler): on the next genuine rotation, at least one ranked
board surfaces the receiving sector within 5 sessions of the 10d-RS onset, with the split
disclosed at glance tier. Counterfactual check at W1-merge: replay 2026-06-01→07-15; the Fast
Lens must place healthcare top-3 by mid-June and demote semis by 07-03 on historical data, and
the replay ships with the PR as its come-back receipt.

### Immediate ops fixes (this week, no charter needed)

1. Verify MLC stance_matrix artifact renders after tonight's build (W2b merged 07-16).
2. `subsectors.html` Entry-Now board self-contradiction (all 5 rows avoid-class): render the
   regime override as the primary label, or suppress avoid-class rows from an "entry" lane.
3. Turn Desk artifact `oracle_turn_desk.json` missing on site — restore or render its absence
   honestly.
4. Rotation-miss ledger seeded with the three 2026 episodes.

---

## 8. Appendix — evidence index (file:line)

- Ranker formula/lag: `engine/sector_central.py:257-298,333-377`; `engine/sector_cycles.py:146-157,285-314,404-408,628,642-643`; `engine/narrative_rotation.py:47-50,244-251`.
- Unwired preference table: `config.yml:2586-2590` (sector_preferences), `:2632-2643` (sector_macro_beta); `engine/sectors.py:49-66` (preference_check, display-only).
- Stock-level exclusion: `engine/residual_alpha.py:149-153` (12-1 window, sector-neutral); pick-lab gate states `data/pick_lab/snapshots/2026-07.parquet`.
- Dead-end inventory: `engine/vol_velocity.py` (COR/DSPX display-only), `engine/breadth_split.py`, `data/breadth/sector_breadth.parquet` (no consumer), `engine/mag7_regime.py`, `engine/leader_lifecycle.py:~720`, `site/marketdata/rotation_events.json` (`may_rank:false`), `site/marketdata/sector_fragmentation.json`, `engine/sector_fragmentation.py:16`, `engine/sector_bottom.py:37`, `engine/sector_ignition.py:27-28`.
- Board states 07-15/16: `site/sector_central_data.js`, `data/sector_central/calls.parquet`, `data/sector_cycles/forward_log.parquet`, `data/allocation/latest_us.json`, `data/subsector_rotation/alerts.jsonl`, `data/sector_cycles/cycle_dna.json`, `data/sector_cycles/narratives.json`.
- China precedent: `engine/china_sector_rotation.py:120-168,431-465,536-601` (#2634).
- Prior programs: `research/ROTATION_COMMAND_MASTERPLAN_BY_FABLE.md` (RC-R1..15, S1/S2 ACCRUE), `research/MEGACAP_LEADERSHIP_COHERENCE_MASTERPLAN_BY_FABLE.md` + `research/POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md` (MLC), `research/FLOW_CONTINUITY_MASTERPLAN_BY_FABLE.md`, `research/JULY_2026_MARKET_NAVIGATION_PLAYBOOK.md` (#2545), `research/SP500_NASDAQ_REGIME_ROTATION_ATLAS_2013_2026.md` (#2491).
- External findings [DR-0..14]: deep-research run wf_afe0895d-340, 2026-07-16 (SpotGamma 06-03 DSPX/COR1M; Cboe; BIS Bulletin 95; TSMC 6-K; UNH 8-K; timeline sources), adversarially verified 3-0/2-1.

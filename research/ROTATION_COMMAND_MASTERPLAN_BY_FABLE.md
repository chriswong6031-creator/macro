# Rotation Command — first-class rotation events, fragmentation-aware sector authority, honest late-classing

Status: ADJUDICATED MASTERPLAN (Fable, 2026-07-11). Operator-initiated: "Mag 7 (MAGS etf)
and leaders like NVDA APPLE META bottomed two weeks ago and have been rising ever since,
yet our current cycle models and systems have not surfaced any of this… we missed the
entire rebound in select tech stocks due to rotation from semis/memory into mag7, which
was not surfaced through our cycle system due to all of these being tech… the system is
wrong and needs sweeping upgrades."

Companion programs (all 2026-07-11, none duplicated here): MAG7_COMMAND (shipped —
us_stocks/baskets display lens, #2273–#2279), RATIO_LENS (W1 shipped, #2240),
LEADER_RADAR (W1 engine merged, W2 pending), INDEX_HYBRID_MOMENTUM (W0 docs, #2280).
M7C §0 documented the *baskets/us_stocks* face of this incident. This masterplan owns the
**cycles/confluence-stack** face — sector_cycles, subsector_rotation, the ENTRY-NOW
double gate — where the miss was not cosmetic but *structural*: the stack detected the
turn and then suppressed it.

---

## 0. Incident of record — point-in-time verified

Method: ground truth from yfinance daily closes cross-checked against our own
`data/baskets/ohlcv/*.parquet`; system state reconstructed by `git show` of committed
renders (the repo commits `site/` on every render), taking the last commit before each
date 23:59. No current-file state was trusted (see §0.4 for why that matters).

### 0.1 Ground truth: a two-leg violent handoff, not a dip-buy

| Ticker | June low | Close 7/10 | Off low | Shape |
|---|---|---|---|---|
| MAGS | **06-25** (61.07) | 67.68 | **+10.8%** | V-bottom exactly 06-25 |
| META | 06-25 | 669.21 | **+23.3%** | strongest general |
| AAPL | 06-25 | 315.32 | +14.6% | |
| MSFT | 06-25 | 385.10 | +9.1% | −23.4% into the low (hardest crash) |
| NVDA | **06-26** | 210.96 | +9.6% | bottomed with Mag 7, **not** with semis |
| SMH | 06-05 | 611.03 | +7.3% | but −4.1% *since 06-25* |
| MU | 06-05 | 979.30 | +13.4% | +40.5% 06-05→06-25 blowoff, then **−22.7%** |
| WDC | 06-10 | 582.59 | +18.9% | +52.3% in 6 sessions to 06-18, then **−28.7%** |
| STX | 06-10 | 910.34 | +11.6% | +34.1% blowoff, then −24.3% |

Since the 06-25 close (→07-10): MAGS +10.8, META +23.3, AAPL +14.6 vs MU −19.3,
WDC −13.7, STX −11.2, SMH −4.1 (SPY +2.8). **MAGS/SMH inflected 06-22, +15.7% since;
MAGS/SPY inflected exactly 06-25.** Mid-June the flow ran the *other* way (money leaving
Mag 7 into the memory melt-up; MAGS −12.6% 06-01→06-25). 06-25/26 was the handoff.
NVDA is carried in both `mag7` and `ai_semiconductors`; the tape says it traded as a
general (low 06-26 with MAGS; NVDA/SMH +13.2% since 06-30) while its two homes displayed
opposite reads all window.

### 0.2 What the cycles stack displayed, day by day (verified renders)

The mag7 row of `site/marketdata/basket_confluence.json`, point-in-time:

| Render | as_of | class | entry.buyable | entry.reason |
|---|---|---|---|---|
| 06-29 (`e5398f1f`) | 06-29 | neutral | false | "flat: sell" |
| 06-30 (`e992b550…`) | 06-30 | **tailwind** (1 day) | **false** | "flat: sell" |
| 07-02 (`1111fce1`) | 07-01 | **late** | false | "flat: sell" |
| 07-07 (`d363832e`) | 07-06 | late | false | "flat: sell" |
| 07-10 (`39ca5858`) | 07-09 | late | false | "flat: sell" |
| 07-11 (`173e3106`) | 07-10 | late | false | "flat: sell" |

Alongside: XLK on sector_cycles read **Topping / SELL for all 11 sessions** of the rally
(pos 83.5→73.4). The mag7 basket *phase* flipped to **Bottoming in the 06-30 render**
(asof 07-01, +5.3% off the low, T+3 — a timely, correct cycle read) but its stance was
COUNTERTREND BOUNCE → HIGH-RISK BOUNCE for the entire window, and the pre-registered
forward log (`data/sector_cycles/forward_log.parquet`, born 07-02) records b-mag7 as
Trough + HIGH-RISK BOUNCE on every logged day. The risk layer printed its **maximum
growth-scare (91) on 06-26 — the bottom day** — and de-escalated to "watch" only 07-09.
Rotation alerts (`data/subsector_rotation/alerts.jsonl`, engine born 06-28) flagged
"Rotating in — Niche/Advertising (Social Media)" and "Ads & Search (AI)" on **06-30** —
the earliest constructive print anywhere, +4–5% off the low — at *minor* severity, buried
among 21 alerts of that run. software-application + ai-agents + non-ai-software went
ENTRY_NOW asof 07-01 (honest credit; software ≠ Mag 7). internet-content-information
(META/GOOGL's home) stayed "mixed" until a pending-buy visible **07-11**, ten sessions
and +10.8% late, one render after being labeled HEADWIND.

The short side was **correct everywhere from birth**: memory-storage HEADWIND 06-29,
short-bias 3D state all window, semis quadrant ranks 255–268/268 "weakening" from the
desk's first render. The system caught the rotate-OUT. The rotate-IN had no home.

### 0.3 Verdict

**This was a stance-gating miss, not a detection miss.** The phase engine found the Mag-7
bottom at T+3. Three authority layers above it each independently suppressed the finding:

1. the sector aggregate (XLK, cap-weighted, semi-poisoned) held Topping/SELL veto;
2. the marker entry gate never printed a buy (`flat: sell` all window), so
   `buyable=false` regardless of phase;
3. the class ladder re-labeled the cohort "late" at +7.8% off the low — then watched it
   add another 10 points while displaying *avoid — don't chase*.

By construction, **any** leadership handoff into a cohort inside a Topping sector will
be (a) labeled countertrend, (b) blocked by the marker gate, (c) reclassified late within
days, (d) alerted only via adjacent proxies at minor severity. The Mag-7 episode is the
general case, not an outlier. That is the sweeping-upgrade target.

### 0.4 Integrity finding (separate severity: HIGH)

Committed render history shows **signal markers being silently re-dated**:
`site/subsector_signals/b-ai-software.json` carried a `2026-07-06` buy marker in the
07-07 render (`d363832e`) which is *absent* in the 07-10 render (`39ca5858`), replaced by
`2026-07-09`; software-application's 07-01 rebuy was re-graded take→block between 07-07
and 07-10. Whatever the mechanism (recompute from revised data, non-PIT marker rebuild),
the consequence is: **current-file marker history is not a point-in-time record**, and any
self-grading built on it is unfalsifiable. This postmortem was only possible because
renders are committed to git. Fixed by RC-R2 below.

---

## 1. Root causes, ranked (each with the code that did it)

- **RC-1 — Sector aggregate holds veto over its legs.** The double gate
  (`engine/subsector_confluence.py:20-26`) requires subsector/basket buyable AND stock
  buyable; a member buyable under a TOPPING/SELL sector is demoted to `headwind_warn`
  (`:317-331`). XLK's read is a single cap-weighted SPDR close — no leg awareness — and
  post-melt-up it was semi-heavy exactly when the generals turned. There is no concept of
  "the sector aggregate is not representative right now."
- **RC-2 — The marker entry gate cannot see V-bottoms.** `engine/signal_gate.py:146-151`:
  position is flat because the last marker is a sell → `reason "flat: sell"`,
  `is_buyable=false`, forever, until the slow marker machine prints a fresh buy tier. The
  gate is calibrated for base-building entries. Mega-cap V-recoveries (M7C field guide:
  61 episodes of CW-composite runs ≥+8% in ≤30 sessions since 2015) confirm faster than
  the machine can re-arm.
- **RC-3 — "Late" is mis-calibrated for cohort recoveries.**
  `engine/subsector_confluence.py:185-198` `_classify`: not buyable + EXTENDED-family
  state → `late` ("don't chase", `:96`). Mag 7 was late at +7.8% of what became (median
  field-guide episode) a +8–15% run. A binary late-flag with no episode ruler
  structurally guarantees missing every V-recovery after its first ~3 days.
- **RC-4 — Rotate-IN has no first-class home.** The 268-node Finviz rotation taxonomy
  (`finviz_themes/finviz_themes_map.csv`) contains **zero** mega-cap/Mag-7 grouping
  (grep: 0 matches). The desk expressed the semis breakdown perfectly (ranks 255–268) and
  could only express the Mag-7 bid as "Social Media / Ads & Search rotating in", minor
  severity. There is no *rotation event* object anywhere: nothing pairs a rotate-OUT with
  a rotate-IN and says "this is a handoff, act like it."
- **RC-5 — The new organs that see it are fenced out of the stack that decides.**
  `engine/mag7_regime.py:1-30` is explicitly DISPLAY-ONLY; Ratio Lens states
  (`data/oracle/ratio_pairs.json` — `mag7_vs_ailogic`, `memory_vs_ailogic`,
  `qqq_vs_rsp`… registered 2026-07-11) are authority-fenced (RL-R10) with cycles
  integration parked (RL-R14); Leader Radar's handoff watch (LR-R4) is W2-pending. All
  correct per promotion-gate law — but nothing owns *stitching* them into an evidence
  path that can ever change a stance.

Cross-cutting findings: **(i)** markers mutate across renders (§0.4); **(ii)** basis
inconsistency inside one payload — XLK row `basis: "price"`, basket rows `basis: "tr"`
(`site/sector_cycles_data.js`, 07-10 render); **(iii)** two phase vocabularies co-print
on the same row (b-mag7 07-10: wheel "Downturn" + ladder "Bottoming") even though
`engine/cycle_ontology.py` (W1.2) already exists as the canonical crosswalk — an
adoption gap, not a missing build; **(iv)** dual-membership names (NVDA) get opposite
reads from their two homes with no arbitration or disclosure.

---

## 2. Doctrine position and boundary map

Everything in W1 is **display/context tier** and ships freely under the promotion-gate
law. Nothing here touches the backtested `deteriorating→avoid` sector channel (M7C-R4
standing, not re-litigated). No construct in the DO_NOT_REBUILD registry is rebuilt.
Gate/stance *changes* (RC-R8, RC-R9) ship only behind pre-registered studies run on
backfilled point-in-time replays — this plan builds the evidence path, then promotes or
kills on the ruler, not on this episode's vividness. One episode is an existence proof,
not a validation.

| Existing organ | Owns | Rotation Command consumes / adds |
|---|---|---|
| Ratio Lens (W1 live) | pair state machines, decomposition, stretch | consumes pair states as detector inputs; **this doc is the RL-R14 joint-ruling proposal** for cycles-page integration |
| M7C mag7_regime (live) | Mag-7 cohort trend×structure state | consumed as the rotate-IN leg's regime read; stays display-only |
| Leader Radar (W1 engine) | per-name lifecycle, LR-R4 handoff watch (pair-level, name-grain) | RC events are *cohort-grain*; LR chips cross-linked, not duplicated |
| IHM (W0) | index-grain depth-context / washout_turn | RC-R11 consumes washout context when W1 lands; no momentum math built here |
| subsector_rotation desk | 268-node quadrant flows + alerts | gains the mega-cap node (RC-R4), rotation-event lane (RC-R3), severity fix (RC-R5) |
| subsector_confluence / signal_gate | ENTRY-NOW double gate | gains disclosure chips in W1; gate surgery only via RC-R8/R9 preregs |
| cycle_ontology (W1.2) | canonical phase/stance/position | RC-R13 is pure adoption/enforcement |

---

## 3. Requirements

### W1 — ship now (display/context tier, ~1 week)

- **RC-R1 — Rotation Event object + detector.** New `engine/rotation_events.py` emitting
  append-only `data/rotation_events/events.jsonl`. A ROTATION event fires when, over a
  trailing 10–20d window, ALL of: (a) leg-A **blowoff-crash signature** (runup z-score ≥
  threshold into a local high, then drawdown ≥ threshold from it — MU/WDC/STX shape);
  (b) leg-B **turn signature** (cycle phase enters Trough/Bottoming family, or 20d
  low + reclaim); (c) the **pair ratio** B/A confirms (Ratio Lens state transition or
  10d ratio slope flip); (d) legs are peers (same parent sector or registered pair).
  Emits: legs, direction, severity (function of leg market-cap share and move size),
  evidence receipts (which of a-d, with values), event_id. Deterministic price/breadth
  arithmetic only; no LLM. On 06-25 inputs this fires memory→mag7 at severity=major
  within 3 sessions (§4).
- **RC-R2 — Append-only marker integrity (PIT law).** Signal markers become an
  append-only ledger: a marker, once rendered, may be *superseded* (new row referencing
  the old) but never re-dated or deleted. Add a render-time regression test that diffs
  the previous committed render's marker set against the new one and fails on silent
  mutation (the exact b-ai-software 07-06→07-09 case as the fixture). Without this,
  every ledger and grader downstream is unfalsifiable.
- **RC-R3 — Rotation lane on surfaces.** subsector_rotation.html gets a "Rotation
  events" rail (active events with receipts, EN/ZH); sector_cycles.html sector cards and
  the affected basket cards get an event chip ("⟲ handoff: memory→mag7, day N");
  board/action surfaces get the chip in the same lane as regime banners. Tier-2 hover =
  receipts. No stance words beyond the chip; the stance stays whatever the stack says —
  the event is *context that the stack disagrees with itself*.
- **RC-R4 — Mega-cap node in the rotation taxonomy.** Add the Mag-7/mega-cap-generals
  grouping (and `us-sector-*-ew` counterparts where missing) to the rotation universe so
  rotate-IN flows have a first-class home. Config-only where possible; the quadrant math
  is unchanged.
- **RC-R5 — Alert severity honesty.** Rotation-desk alerts currently drown (21/run,
  META/GOOGL proxies at minor). Severity gains a size term (market-cap share of the
  node) and rotation events (RC-R1) get their own alert class routed to the top of the
  triage, not mixed into per-node flow alerts.
- **RC-R6 — Fragmentation index + representativeness chip (all sectors).** Per sector,
  per day: dispersion of leg returns (20d), leg-phase disagreement count, and max
  leg-vs-sector ratio z-move. Above threshold → sector card prints "aggregate not
  representative — legs disagree (semis ↓ / generals ↑)" and the double gate's
  `headwind_warn` copy discloses it. Leg registries (config): XLK {mag7-generals, ai
  semis, memory, semicap, software, non-AI hardware}; XLC {interactive media, telco,
  entertainment}; XLY {AMZN/TSLA megacap-consumer, discretionary ex-megacap}; XLV
  {pharma, biotech, managed care, devices}; XLF {megabanks, regionals, payments,
  insurers, brokers}; XLE {integrated, services, E&P}; XLI {defense, machinery,
  transports, electrical}. Reuses existing basket stores; equal-weight legs; no new
  collectors.
- **RC-R7 — Dual-membership arbitration chip.** For names in >1 basket with conflicting
  reads (NVDA): print "behaves-as" from trailing 20d correlation of the name vs each
  home's ex-name composite, on both basket cards. Display-only; membership is not
  re-curated (Ratio Lens purity law).

### W2 — evidence path (2–4 weeks, still no authority)

- **RC-R8 — PIT replay + forward-log backfill.** Replay the detector and the confluence
  stack 2015→present on frozen stores to (a) census all rotation events (expected
  ~dozens: 2017 semis→FANG legs, 2020 COVID growth handoffs, 2022 megacap→energy, 2023
  AI ignition, 2024-25 semis↔software rounds); (b) backfill
  `data/rotation_events/forward_log` with fwd10/20/60 outcomes of the rotate-IN leg
  (absolute + vs SPY + vs parent sector); (c) grade the *counterfactual stack*: on each
  historical event, what did/would XLK-style aggregates and the marker gate display.
  This converts empty prospective ledgers into hundreds of matured windows on day one
  (same doctrine as the cycle-audit Phase-3 recommendation).
- **RC-R9 — Two pre-registered promotion studies** (run on RC-R8 output, thresholds
  frozen before looking): **(S1) handoff stance override** — on event days, does
  re-labeling the rotate-IN leg from COUNTERTREND/HIGH-RISK BOUNCE to HANDOFF CANDIDATE
  carry positive fwd20/60 expectancy vs the do-nothing baseline, net of the false-fire
  rate? **(S2) reclaim entry lane** — a second `signal_gate` lane (fast-reclaim: cross
  above short MA + ratio confirmation, only *while an event is active*) vs the existing
  marker lane: hit rate, expectancy, drawdown. Promote, demote, or kill each on its
  ruler; the "late" recalibration (RC-R10) inherits S1's episode census.
- **RC-R10 — Honest late-classing.** Replace binary `late` copy with the episode ruler:
  "at +7.8% of median historical handoff run +12% (p25 +6 / p75 +19), day 4 of median
  14" — computed from the RC-R8 census (superset of the M7C field-guide 61 episodes).
  Class boundaries only change if S1/S2 pass; the *display* honesty ships in W2
  regardless.
- **RC-R11 — Washout counter-read chip.** When the risk layer prints an extreme
  (growth-scare ≥ p90) while an index/cohort sits at a depth extreme (IHM washout_turn
  when live; interim: 63d drawdown percentile), print "capitulation-zone reading —
  historically two-sided" on the risk banner. Ledgered, expected-NULL, display-only. The
  06-26 growth-scare-91-on-the-low print becomes a labeled pattern instead of an
  unexamined embarrassment.

### W3 — consolidation (4–8 weeks)

- **RC-R12 — Promotion or kill.** Apply S1/S2 verdicts to `subsector_confluence` /
  `signal_gate` behind flags, with kill-registry entries for whatever fails. Any stance
  change carries its receipt inline ("HANDOFF — S1 promoted 2026-08-xx, n=41, WR 63%").
- **RC-R13 — Ontology adoption enforcement.** One phase vocabulary per row on all cycles
  payloads via `engine/cycle_ontology.resolve_state()`; per-row `basis` printed on-card
  (price vs TR — finding (ii)); crosswalk test that fails renders emitting wheel+ladder
  contradictions like Downturn+Bottoming.
- **RC-R14 — Cross-region reuse.** Same detector + leg registries for China/HK desks
  (sector_cycles_china, subsector_rotation_china) where basket stores exist; explicitly
  out of W1/W2 scope.
- **RC-R15 — Self-grading.** Rotation-event family registered in the FDR registry
  (`rotation_events_v1`); quarterly census note auto-appended to the field guide;
  the 2026-06-25 memory→mag7 event is **case zero** in the ledger, graded prospectively
  from 07-11 (no retro credit).

---

## 4. The 06-25 episode replayed under Rotation Command (honest walk-through)

With W1 shipped as specced, on frozen real inputs: **06-26/27** — leg-A signature
completes (MU runup z≈3 into 06-25 high, −8% in 2 sessions; WDC already −15% off 06-18);
leg-B turn not yet confirmed → no event, correctly (mid-June the *reverse* handoff was in
progress; a naive detector fires mag7→memory around 06-10, which the pair-ratio
confirmation (c) suppresses until the blowoff signature (a) completes). **06-30** — leg-B
turn signature lands (mag7 basket phase → Bottoming family in that evening's compute;
MAGS reclaim of 10d high; MAGS/SMH 10d slope positive since ~06-26) → **ROTATION event
memory→mag7, severity major (leg cap-share ~30% of sector), day 1**, chip on XLK card,
top-of-triage alert, rotation rail entry — at **+5.3% off the low**, T+3, eleven sessions
and one day before the first constructive Mag-7-adjacent ENTRY_NOW actually printed.
The stance stays HIGH-RISK BOUNCE in W1 (no authority) — but the operator sees the stack
disagree with itself with receipts, which is the difference between "system said avoid"
and "system said avoid *while flagging a major handoff against its own read*". S1/S2
(W2) then decide with historical evidence whether the stance itself may move. What W1
does **not** do: fire before 06-30 (the turn needs one confirmed session — accepting
T+3 as the honest floor), or make anyone buy.

---

## 5. Acceptance

- W1: rotation rail + chips render EN/ZH from a fixture events file; detector unit tests
  on synthetic legs (blowoff+turn+ratio permutations, incl. the naive-fire suppression
  case); marker-mutation regression test red on the b-ai-software fixture, green after
  RC-R2; fragmentation chip visible on XLK with 06-25→07-10 replayed inputs; taxonomy
  node live in the rotation desk; no change to any stance/gate/rank output (diff test).
- W2: backfilled census + forward log committed; S1/S2 prereg docs merged *before*
  results; late-ruler copy live.
- W3: promotion/kill recorded in DECISIONS.md; ontology crosswalk test green repo-wide.

## 6. Open questions (parked, not blockers)

1. Event *decay*: when does a rotation event end — ratio slope re-flip, leg-B phase
   exit, or fixed 20-session TTL? (W1 ships TTL + re-fire lockout; revisit with census.)
2. Should Neural Web `market_plane.json` carry active rotation events for the Terminal
   strip? (Cross-repo; propose after W1 renders stabilize.)
3. Does the fragmentation index subsume the existing basket_breadth_divergence signal or
   complement it? (Census both in RC-R8 before touching either.)
4. NVDA-class dual-membership: is "behaves-as" correlation stable enough intra-episode,
   or does it need a shrunk/regime-conditioned estimator? (W2 data question.)

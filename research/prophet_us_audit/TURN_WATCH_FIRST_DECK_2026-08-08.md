# TURN WATCH desk — first deck (ANTICIPATION §6.9 R8)

**Built:** 2026-08-08 · **Data session:** 2026-08-07 · **Era:** `anticipation-v1-2026-08-08`
· **Anchor era:** `abs-session-2026-08-06` · **Artifact:** `site/prophet/turn_watch.json`
· **Engine:** `engine/us_turn_watch.py` · **Builder:** `scripts/build_turn_watch.py`

## §0 What this is, and what it is not

The operator reframe that commissioned it (masterplan §6.9 R8):

> *"if we get the signal early, I do the holistic review myself — but if we don't surface
> them, names reach my desk up 10-15% and I chase."*

The operator IS the second-stage filter. So this deck optimises **recall and context
density, not precision**. A row is not a candidate, not a plan, not a pick — it is a name
whose earliest mechanical evidence moved, printed next to enough context to decide in
seconds whether to look harder. **Most rows will go nowhere. That is the design.**

**Display tier, zero scored authority.** Nothing here ranks, gates or sizes a graded
position. The `context_score` is a display-only reading order (formula in §5), labelled
non-authoritative in the artifact itself. No forward claim, no directional call
(`DNR:KILL-FORCED-CALLS`), no promotion of any kind is asserted by this ship.

Voice: windows, not certainties. The page ships next session under the design lane — this
PR is the data plane only.

## §1 Coverage (measured, this run)

| | |
|---|---|
| Universe (`data/yahoo`, equities only) | 697 |
| Graded (≥ 200 daily bars) | **681** |
| Skipped, short history | 16 |
| Triggered (any trigger within 5 sessions) | **348** (51.1% of graded) |
| Deck (capped) | 40 |
| Beyond the cap | **308** — listed in §6, and in the artifact's `beyond_cap` |
| Group states read (`us_basket_turn`) | 49 baskets |
| Runtime | **100.8 s** (nightly budget 600 s; self-reported as `runtime_seconds`) |

Triggered by lane: `dot_1d` 171 · `pre_confluence_2d` 154 · `basket_turn` 78 ·
`leader_reset_turn` 28. In the deck: 9 · 35 · 26 · 5.

A 51% trigger rate is high **on purpose**. Recall is the product; the cap and the reading
order are what make it usable, and both are disclosed rather than tuned away.

## §2 The trigger union

A name enters the deck if ANY of these fired within the last **5 sessions**.

| id | What fires it | Source |
|---|---|---|
| `dot_1d` | Daily StochRSI %K crosses above %D · %D was < 20 within the last 8 sessions · daily RSI-MACD histogram rising | `confluence_tiers._stoch_rsi_kd` / `._rsi_macd` on the DAILY series |
| `pre_confluence_2d` | Fresh 2D RSI-MACD cross (≤ 2 2D-ticks) while the **3D has NOT crossed** — the 3D `bars_to_cross` is printed on the row | the module's 2D/3D machinery |
| `basket_turn` | Member of any basket in `us_basket_turn` state TURNING or CONFIRMED | that organ's committed artifact/ledger |
| `leader_reset_turn` | High-RS leader · uptrend intact · shallow controlled retrace · daily stoch reset · turn back up | soft-imports `engine.us_leader_pullback` (R4); **absent on this base**, so the minimal inline signature ran and is stamped per row |

The indicator helpers are **imported from `engine.confluence_tiers`, never forked**. The
deck's whole claim — "the slow tier has not admitted this yet" — is only meaningful if both
sides read the same instrument. The known cost is that a private-helper import carries its
owner's era, so the era travels with the numbers: every artifact stamps `anchor_era` and
`indicator_source`.

## §3 TODAY'S DECK (2026-08-07 tape)

Columns: **Ctx** = display-only context score · **3D btc** = 3D RSI-MACD bars-to-cross
(the pre-confluence quantifier) · **Blocking legs** = why the confirmation cascade has not
taken it · **Off reset low** = distance above the 20-session low (the structure anchor) ·
**HTF washout** = monthly / 2W StochRSI, `pinned` = %D below 20, `/Ns` = daily sessions
pinned, `^` = turning · **Group** = primary basket, its `us_basket_turn` state and its 20d
relative strength.

| # | Ticker | Ctx | Triggers (days since) | Slow tier now | 3D btc | Blocking legs | Off 52w hi | Base depth / age | Off reset low | 20d RS | 200d | HTF washout | Group (state, 20d RS) |
|---:|---|---:|---|---|---:|---|---:|---|---:|---:|---:|---|---|
| 1 | **ASTS** | 80.0 | 2D>3D(1) · group(0) | T2 (deep, 1t) | null | — | -46.0% | -60.1% / 49s | 35.7% | -4.3pp | -12.2% | M:pinned/49s 2W:pinned/21s^ | space_economy (TURNING, 9.6pp) |
| 2 | **OKLO** | 80.0 | 2D>3D(1) · group(0) | T2 (deep, 1t) | null | — | -72.2% | -78.8% / 204s | 31.4% | -3.3pp | -33.3% | M:pinned/90s 2W:pinned/11s^ | nuclear_power (TURNING, -6.3pp) |
| 3 | **MP** | 77.0 | 2D>3D(0) · group(0) | — | 0.02 | macd_below_signal, below_200dma | -48.2% | -61.4% / 204s | 34.1% | -4.5pp | -12.2% | M:off 2W:pinned/11s^ | critical_minerals (TURNING, 0.4pp) |
| 4 | **RDW** | 76.9 | 2D>3D(0) · group(0) | — | 0.05 | macd_below_signal | -47.5% | -70.0% / 49s | 74.7% | 31.1pp | 34.7% | M:off 2W:pinned/1s | space_economy (TURNING, 9.6pp) |
| 5 | **NNE** | 76.5 | 2D>3D(0) · group(0) | — | 0.20 | macd_below_signal, below_200dma | -66.7% | -73.7% / 209s | 26.7% | -2.5pp | -30.7% | M:null 2W:pinned/11s^ | nuclear_power (TURNING, -6.3pp) |
| 6 | **USAR** | 76.3 | 2D>3D(0) · group(0) | — | 0.29 | macd_below_signal | -50.0% | -69.2% / 205s | 47.9% | 2.2pp | 0.2% | M:off 2W:pinned/1s | critical_minerals (TURNING, 0.4pp) |
| 7 | **SGML** | 76.0 | 2D>3D(0) · group(0) | — | 0.42 | macd_below_signal, below_200dma | -51.9% | -60.4% / 63s | 21.4% | -6.9pp | -11.4% | M:off 2W:pinned/11s | critical_minerals (TURNING, 0.4pp) |
| 8 | **ALM** | 75.4 | 2D>3D(0) · group(0) | — | 0.64 | macd_below_signal | -39.5% | -53.2% / 77s | 29.5% | -17.1pp | 1.5% | M:off 2W:pinned/30s^ | critical_minerals (TURNING, 0.4pp) |
| 9 | **LAC** | 75.4 | 2D>3D(0) · group(0) | — | 0.64 | macd_below_signal, below_200dma | -67.9% | -73.0% / 204s | 19.2% | -5.1pp | -31.1% | M:off 2W:pinned/11s^ | critical_minerals (TURNING, 0.4pp) |
| 10 | **CRML** | 75.3 | 2D>3D(0) · group(0) | — | 0.69 | macd_below_signal, below_200dma | -75.8% | -82.9% / 204s | 41.3% | -11.2pp | -28.7% | M:off 2W:pinned/21s^ | critical_minerals (TURNING, 0.4pp) |
| 11 | **RKLB** | 75.1 | 2D>3D(0) · group(0) | — | 0.75 | macd_below_signal | -44.9% | -61.0% / 50s | 41.4% | -0.2pp | 6.2% | M:off 2W:pinned/11s^ | space_economy (TURNING, 9.6pp) |
| 12 | **PL** | 74.7 | 2D>3D(0) · group(0) | — | 0.92 | macd_below_signal, below_200dma | -53.4% | -62.1% / 49s | 22.9% | -10.6pp | -8.2% | M:off 2W:pinned/11s^ | space_economy (TURNING, 9.6pp) |
| 13 | **LUNR** | 74.7 | 2D>3D(0) · group(0) | — | 0.94 | macd_below_signal, below_200dma | -64.1% | -75.1% / 49s | 44.0% | -0.8pp | -14.5% | M:off 2W:pinned/11s^ | space_economy (TURNING, 9.6pp) |
| 14 | **SOUN** | 74.0 | 2D>3D(1) · group(0) | T2 (deep, 1t) **S1** | null | — | -62.5% | -73.4% / 203s | 40.7% | 18.4pp | -12.8% | M:pinned/131s 2W:off^ | ai_agents (TURNING, 7.3pp) |
| 15 | **CAMT** | 73.2 | 2D>3D(0) · group(0) | — | 0.19 | macd_below_signal | -25.1% | -38.8% / 61s | 22.4% | 5.6pp | 4.6% | M:off 2W:pinned/1s | semicap_equipment (TURNING, -11.3pp) |
| 16 | **FORM** | 72.1 | 2D>3D(0) · group(0) | — | 1.69 | macd_below_signal | -26.6% | -47.8% / 27s | 40.7% | -2.5pp | 22.6% | M:off 2W:pinned/1s | semicap_equipment (TURNING, -11.3pp) |
| 17 | **BKSY** | 71.0 | 2D>3D(1) · group(0) | T2 (deep, 2t) | null | — | -43.5% | -60.1% / 49s | 41.5% | 14.1pp | 10.5% | M:off 2W:pinned/11s^ | space_economy (TURNING, 9.6pp) |
| 18 | **UAMY** | 71.0 | 2D>3D(1) · group(0) | T2 (deep, 2t) | null | — | -60.8% | -74.3% / 204s | 39.5% | 3.6pp | -14.4% | M:off 2W:pinned/39s^ | critical_minerals (TURNING, 0.4pp) |
| 19 | **UUUU** | 71.0 | 2D>3D(1) · group(0) | T2 (deep, 2t) | null | — | -49.0% | -61.3% / 132s | 31.7% | 1.7pp | -20.2% | M:off 2W:pinned/97s^ | uranium_miners (TURNING, 4.5pp) |
| 20 | **ALB** | 70.2 | 2D>3D(1) · group(0) | T2 (deep, 2t) | null | — | -39.0% | -47.4% / 78s | 15.9% | 1.6pp | -14.1% | M:off 2W:pinned/39s^ | critical_minerals (TURNING, 0.4pp) |
| 21 | **FLY** | 70.1 | 2D>3D(0) · group(0) | — | 0.35 | macd_below_signal, below_200dma | -55.7% | -72.2% / 251s | 49.7% | 8.4pp | -2.8% | M:null 2W:null | space_economy (TURNING, 9.6pp) |
| 22 | **XPEV** | 70.0 | dot(0) · 2D>3D(0) | — | null | macd_below_signal, below_200dma | -56.8% | -58.4% / 184s | 3.9% | -9.3pp | -31.4% | M:pinned/69s^ 2W:pinned/145s^ | — |
| 23 | **URG** | 69.7 | 2D>3D(1) · group(0) | T2 (deep, 2t) | null | — | -33.3% | -45.7% / 204s | 18.6% | 3.6pp | -8.0% | M:off 2W:pinned/21s^ | uranium_miners (TURNING, 4.5pp) |
| 24 | **JOBY** | 69.0 | 2D>3D(1) | T2 (deep, 1t) | null | — | -55.9% | -66.0% / 210s | 29.9% | 9.5pp | -22.6% | M:pinned/69s 2W:pinned/11s^ | — |
| 25 | **QUBT** | 68.9 | 2D>3D(0) | — | 0.03 | macd_below_signal, below_200dma | -62.7% | -74.4% / 211s | 25.8% | 3.6pp | -8.7% | M:pinned/112s^ 2W:off | quantum_computing (NONE, 4.0pp) |
| 26 | **ORCL** | 68.9 | 2D>3D(0) | — | 0.05 | macd_below_signal, below_200dma | -54.7% | -64.6% / 228s | 27.9% | 2.1pp | -17.5% | M:pinned/112s 2W:off | ai_software (NONE, 7.1pp) |
| 27 | **QBTS** | 68.3 | 2D>3D(0) | — | 0.28 | macd_below_signal, below_200dma | -53.6% | -71.0% / 203s | 28.3% | 0.9pp | -8.4% | M:pinned/90s 2W:off | quantum_computing (NONE, 4.0pp) |
| 28 | **UPST** | 67.5 | 2D>3D(0) | — | 0.60 | macd_below_signal, below_200dma | -57.9% | -67.2% / 236s | 16.9% | -7.5pp | -12.6% | M:pinned/151s^ 2W:off^ | payments_fintech (FALLING, 0.1pp) |
| 29 | **CCJ** | 67.1 | 2D>3D(1) · group(0) | T2 (deep, 2t) | null | — | -27.4% | -36.9% / 132s | 15.2% | -1.0pp | -6.9% | M:off 2W:pinned/39s^ | uranium_miners (TURNING, 4.5pp) |
| 30 | **ENTG** | 66.7 | 2D>3D(0) · group(0) | — | 0.75 | macd_below_signal | -17.3% | -41.8% / 33s | 42.1% | 2.3pp | 26.4% | M:off 2W:off | semicap_equipment (TURNING, -11.3pp) |
| 31 | **AEIS** | 66.5 | 2D>3D(1) · group(0) | T2 (deep, 1t) | null | — | -16.4% | -35.1% / 67s | 28.7% | 3.1pp | 12.1% | M:off 2W:pinned/39s | semicap_equipment (TURNING, -11.3pp) |
| 32 | **MNSO** | 65.0 | dot(0) | — | null | stoch_overbought, stoch_bear_cross, stoch_3d_not_crossed | -51.7% | -56.5% / 240s | 9.9% | 4.0pp | -23.7% | M:pinned/112s^ 2W:pinned/154s^ | — |
| 33 | **MPWR** | 61.3 | 2D>3D(0) · leader(0) | — | 1.00 | macd_below_signal | -16.9% | -26.0% / 45s | 12.2% | 1.2pp | 15.2% | M:off 2W:pinned/1s | ai_semiconductors (NONE, -5.4pp) |
| 34 | **UCTT** | 61.0 | dot(0) · group(0) | — | 7.04 | macd_below_signal, macd_2d_not_crossed | -38.8% | -51.2% / 27s | 25.4% | -20.3pp | 40.3% | M:off 2W:off | semicap_equipment (TURNING, -11.3pp) |
| 35 | **FWONK** | 60.5 | dot(1) · 2D>3D(3) | T4 (shallow, 0t) | null | — | -5.1% | -24.8% / 210s | 7.1% | 4.6pp | 12.0% | M:pinned/131s^ 2W:off | — |
| 36 | **TUR** | 60.0 | dot(4) · 2D>3D(0) | — | 0.32 | stoch_bear_cross, macd_below_signal, no_deep_or_weekly_confirm | -10.3% | -16.1% / 61s | 2.7% | -2.9pp | 2.2% | M:off 2W:pinned/11s | — |
| 37 | **FDS** | 46.0 | dot(3) · leader(3) | — | null | stoch_overbought | -25.1% | -50.6% / 242s | 17.1% | 13.1pp | 16.2% | M:pinned/215s^ 2W:off^ | us_sector_financials (FALLING, 1.9pp) |
| 38 | **GSG** | 45.6 | dot(1) · leader(1) | — | null | stoch_bear_cross | -10.6% | -18.8% / 55s | 2.1% | 3.1pp | 11.0% | M:off 2W:pinned/11s^ | — |
| 39 | **DBC** | 45.0 | dot(1) · leader(1) | — | null | stoch_bear_cross | -8.8% | -16.5% / 60s | 2.1% | 2.6pp | 10.0% | M:off 2W:pinned/11s^ | — |
| 40 | **YOU** | 44.8 | dot(2) · 2D>3D(1) · leader(2) | — | null | macd_below_signal, macd_2d_not_crossed | -17.5% | -19.2% / 51s | 0.0% | -9.5pp | 14.1% | M:off 2W:off | — |

### What the deck says tonight, in plain words

The board is one story: **critical minerals / space / nuclear-uranium / semicap are all
sitting at a 3D cross that has not happened yet.** Twenty-one of the top 21 rows carry
`macd_below_signal` or a fresh T2, and the `3D btc` column is under 1.0 bar on ten of them
(MP 0.02, RDW 0.05, NNE 0.20, USAR 0.29, SGML 0.42, ALM/LAC 0.64, CRML 0.69, RKLB 0.75,
PL 0.92). Those are names the confirmation cascade will very likely admit within a session
or two — which is exactly the window the operator says he currently misses.

Nine rows have already crossed (T2, 1-2 ticks). One carries an S1 badge (SOUN).

**RKLB — the name that started this program — is on the deck at rank 11, one bar before its
3D cross, 41.4% off its reset low and 6.2% above its 200dMA.** No claim attaches to that;
it is the surfacing, which is all this desk does.

The bottom of the deck is the lane floor working (§5): FDS/GSG/DBC/YOU score 44-46 and are
there because the leader-pullback and dot lanes are guaranteed slots. Without the floor the
deck would have shown **zero** leader-pullback rows.

## §4 ACCEPTANCE MINI-REPLAY

120 sessions, per-day **truncated** evaluation (the `prophet_stage_shadow` pattern: the
series is cut at each day before every read, so the 2D/3D legs see the incomplete trailing
bucket they actually had that day).

Two comparisons are reported because the naive one is boundary-pinned:

* **First-in-window** — the first deck entry anywhere in the 120 sessions. Four of six fire
  on day 1-2 of the window, i.e. they were *already* triggering before it opened. That date
  is a floor imposed by the window, not a measurement, and is flagged.
* **Leg-paired (the number that answers the question)** — the first deck entry inside the
  up-leg the confirmation actually happened on, where the leg starts at the low the
  `% off 20-day low` column is itself measured against. Trigger and confirmation are then
  read off the **same low, in the same move**.

| Name | Leg low | **Deck entry** | % off 20d low | Trigger | → | **Confirm (T2)** | % off 20d low | **Lead** |
|---|---|---|---:|---|---|---|---:|---:|
| **RKLB** | 2026-03-30 | 2026-03-31 | **+11.92%** | dot | | 2026-04-14 | **+25.86%** | **9 sessions** |
| **ASTS** | 2026-05-05 | 2026-05-06 | **+10.66%** | dot | | 2026-05-18 | **+35.95%** | **8 sessions** |
| **NVDA** | 2026-07-29 | 2026-07-31 | **+5.65%** | dot | | 2026-08-05 | **+15.37%** | **3 sessions** |
| **GDX** | 2026-06-10 | 2026-06-11 | **+5.30%** | dot | | 2026-06-17 | **+14.29%** | **4 sessions** |
| **NEM** | 2026-04-29 | 2026-05-04 | **+0.67%** | leader | | 2026-05-08 | **+8.27%** | **4 sessions** |
| **ADAM** | — | — | — | — | | **never admitted** | — | — |

Median entry-vs-low: **deck +5.65% vs confirmation +15.37%** — the deck surfaces at roughly
**a third of the run-up**, 3-9 sessions earlier, on all five names that the confirmation
tier eventually admitted. On ASTS the gap is +10.66% vs +35.95%.

First-in-window, for completeness (and its boundary flag):

| Name | First entry | % off 20d low | At window edge? | Fires in 120 sessions |
|---|---|---:|---|---:|
| RKLB | 2026-02-17 | +5.88% | **yes** | 22 |
| ASTS | 2026-02-18 | +2.69% | **yes** | 24 |
| NVDA | 2026-03-04 | +6.49% | no | 19 |
| ADAM | 2026-02-26 | +5.34% | no | 18 |
| GDX | 2026-02-18 | +10.95% | **yes** | 38 |
| NEM | 2026-02-18 | +14.89% | **yes** | 35 |

### Nulls and caveats, printed

* **ADAM never triggers in the deck** — and could not, on two counts. (1) It has **no
  `data/yahoo` store file**; it lives only under `data/baskets/ohlcv`, so it is outside the
  nightly deck universe entirely. The replay above reached it through the store ladder for
  measurement only. (2) The confirmation tier never admitted it in this window either, so
  there is no pairing to make. Its 18 in-window triggers (first 2026-02-26 at +5.34%, on
  the leader-reset lane) are what the deck *would* have shown had it been in the universe.
  **Fixing ADAM's universe membership is a data question, not this desk's**, and is left
  un-actioned rather than patched around.
* **Trigger (c) is absent from the replay by construction.** `us_basket_turn`'s forward
  ledger begins 2026-08-07 (one date, 49 rows), so there is no honest historical basket
  state to read. Back-filling one would manufacture exactly the earliness the replay exists
  to measure. Every replay number above is therefore the union of (a), (b) and (d) only —
  **a lower bound** on what the live deck surfaces.
* **The paired-adjacent lead is ~1 session on every name.** `pre_confluence_2d` fires by
  construction on the bar before the 3D crosses, so the *last* trigger before a T2 is
  nearly always adjacent. That number is computed and published (`paired_lead_sessions`)
  precisely so it cannot be hidden; it understates the desk, and the leg-paired figure is
  the one to quote.
* **Confirm = first CROSSED tier (T1/T2).** `cascade()` awards no T1 without an explicit
  `take_date`, so in practice every confirm above is a first T2. The first ANY-tier
  admission (including the T3/T4 projections) is also recorded in the artifact; on all five
  admitted names it is the same date.
* **Five names is five names.** This is an acceptance check that the mechanism does what
  §6.9 R8 describes, not a measured edge. No promotion, no ranking claim, and no gauntlet
  is passed or attempted here.

## §5 The context score (display-only)

```
context_score = 100 × (0.30·recency + 0.20·breadth + 0.15·washout
                     + 0.15·base + 0.10·cohort + 0.10·proximity)
```

* `recency` = 1 − days_since_newest_**dated** trigger / 5. Group-turn is a **state, not a
  dated event**, and is excluded from this term — counting it would hand every member of a
  turning basket full recency and let a name that did nothing itself outrank one whose dot
  printed yesterday. The group's contribution lives in `cohort`.
* `breadth` = triggers_fired / 4 · `washout` = 0.6·monthly_pinned + 0.4·2W_pinned
* `base` = min(|base_depth|, 50)/50 · `cohort` = 1.0 CONFIRMED / 0.6 TURNING / 0 none
* `proximity` = 1 if the slow tier is already live, else max(0, 1 − 3D_btc/4)

**Every unknowable term contributes zero and is NAMED** in the row's
`context_score_nulls`, so a row that sorts low because its context could not be read is
distinguishable from one whose context was read and was thin.

**Non-authoritative.** A reading order for this deck only — not a rank, not a score, not an
input to any graded lane.

### The lane floor, and why it exists

The first full run exposed a defect in a pure score sort: the top 40 held **2 dot rows and
ZERO leader-pullback rows** (the first leader row sat at rank 41). Two of the score's terms
(`washout`, `base`) are washout-shaped by construction, and a leader-pullback name is
*shallow by definition* — it can never compete on them. A cap that silently deletes an
entire lane is not a recall surface, and §6.8(d) is explicit that no single lane is the
answer ("the battery is the answer").

`LANE_FLOOR = 5` therefore guarantees each of the four lanes five slots before the score
fills the remainder. It changes what is **visible**, never what is claimed; every row still
carries its own score and the same non-authoritative label, and both `lane_floor` and
`deck_by_trigger` are published in `coverage`.

## §6 Beyond the cap (308 names, in reading order)

The cap is 40. These triggered and did not make it; the full list ships in the artifact's
`beyond_cap` so nothing is hidden by the cap:

> NRG, AA, VOYG, BWXT, IREN, RGTI, DXYZ, CIEN, SMR, NXT, KRRO, FTAI, ORA, APLD, SQM, COHR,
> SMCI, FN, FIP, COIN, RBRK, LITE, IONQ, SPOT, VIAV, TER, TAN, LUMN, GOOG, GOOGL, FLL, GLW,
> MTSI, IRDM, NIO, VSEC, ISRG, CRWV, ENPH, SPGI, NB, TIP, DUOL, FICO, LRN, PPTA, LQD, CHKP,
> CODI, CABA, KALU, VRSK, FSLR, NOVT, NVT, CVNA, VWOB, EMB, ERIE, PCY, PWR, HPE, GH, IWF,
> BIRK, CIFR, MTZ, ONON, CHTR, KVYO, RBLX, TOST, TTD, ADI, XLI, VPL, BEP, NKE, HOOD, CAVA,
> PLTR, IWM, XLK, HUT, NTAP, **NVDA**, HD, MCD, EFX, POOL, FSV, EEM, TWLO, ASHR, QQQ, SSP,
> XLY, PAYX, EWN, WRB, AG, NOW, UEC, ALHC, CF, AAXJ, SPHB, NVO, D, F, EU, SPG, VCYT, COR,
> EWJ, IEF, CGNX, APP, DKNG, HUBS, KTOS, LEU, PLG, WHR, ZS, LOW, BR, CI, HUBB, MCK, MLM,
> DNN, PNR, CTRA, CW, ITRI, AIT, VXUS, IRM, GILD, FSM, CL, MKL, RVTY, ETHA, U, BIDU, XLU,
> PAAS, CPB, RSPU, RMD, CART, RSPC, LNG, ABBV, MRK, XLRE, RIVN, IDXX, XYL, ALT, INSP, MSTR,
> OGN, SE, TECH, ITB, SBUX, ST, ARQT, TEM, CRM, CEG, AZN, ARE, IMPUY, KRMN, PAYC, RDDT,
> SBSW, UROY, W, WDAY, CHRW, PPG, VST, PCVX, JNJ, EXK, AGCO, AAPL, APO, ONCY, BZFD, LLY,
> SRRK, SIRI, ASPI, CB, UNH, SVM, GEN, ANGPY, OMC, TLN, XLC, CDW, ONTO, ETN, HYG, SPY, HOG,
> NVMI, DLTR, ADP, NXE, DE, CTVA, NCDL, HEI, NEE, XHB, IBIT, BLK, PG, DIS, HLT, HQY, PATH,
> CVS, EME, RELY, VECO, FBIN, MAGS, NWS, COHU, ACLS, AMCR, XME, NSSC, STZ, MSI, ICHR, KLAC,
> XLV, QCOM, SPLV, MKSI, STLD, LRCX, BA, SHW, RIO, PMPEX, EWL, NEO, AMAT, WMT, DXCM, KLIC,
> AMZN, IGV, BHP, CRS, KEX, LUV, BBIO, OC, AEP, TLT, MIDD, XYZ, SARO, IBB, AVGO, VKTX, GEV,
> VLY, V, CARR, RSP, XLF, RSPF, AMT, EWS, RSPH, USMV, URI, DCO, ELV, DRI, ALLY, DBA, CSX,
> INDB, FULT, KRE, GE, WCC, VIK, KBE, PNC, NUE, IWD, S, SWK

Note **NVDA** sits at position 85 of the beyond-cap list: its dot fired on 07-31 and the
cascade admitted it (T2) on 08-05, so by 08-07 it is a name the slow tier has already
taken — the deck's job on it is done.

## §7 Two defects found and closed while building

**(1) The session stamp failed open — the G0.2 shape, verbatim.** The first implementation
stamped the deck's `data_session` with `max()` over the universe's last bars. Five 24/7
crypto/FX tapes (BTC-USD, ETH-USD, SOL-USD, USDIDR_X, USDSGD_X) carried a **2026-08-08 bar
— a Saturday** — against 726 equities at 08-07, and the whole surface read a session
fresher than the tape it computes on. This is the measured G0.2 defect repeating in a new
organ (6 of 3,029 panel members reaching a later date flipped a frozen board's `delayed`
badge to false, 2026-08-06). Both halves are now closed:

* the session stamp is **majority-based**, with `max_session` and a plain-word
  `session_note` published beside it, so an advancing tape stays visible but cannot
  manufacture freshness for rows that did not advance;
* crypto (`-USD`), FX (`_X`) and futures (`_F` — 21 contracts; the suffix match is exact,
  so `PL_F` platinum leaves while `PL` Planet Labs stays) leave the universe. They are the
  commodities lane's business, not a single-name turn desk's.

A test pins the majority behaviour with an explicit index — a `freq="B"` fixture would snap
08-08 back to Friday and make the test silently vacuous.

**(2) The cap deleted a whole lane** — see §5. Measured, then structurally fixed, then
pinned by a test that reproduces the exact failure (60 high-scoring group rows plus one
leader row).

## §8 What ships, what does not

**Ships:** `engine/us_turn_watch.py`, `scripts/build_turn_watch.py`,
`tests/test_us_turn_watch.py` (61 assertions, frozen fixtures only), the `config/dag.yml`
+ `.github/workflows/daily.yml` paired registration in the `engine` job, and the first
`site/prophet/turn_watch.json` so the deck exists immediately (house precedent: the Prophet
family is 2-for-2 on committing the first site/ artifact in the builder's own commit —
`474129213e02` build_prophet, `1d97633e9c57` build_track_record_page).

**Does not ship:** the page (design lane, next session), any ledger, any authority, any
promotion. The `reset` cell is an anchor and a distance — **not a buy zone**: it carries no
band, no chase-above and no size, and exists so the R3 entry-zone builder has a structure
low to build from (sibling receipt PR #5007 measured the zone mechanism moving entry-vs-low
7.26% → 2.29%).

**Open, and deliberately not actioned here:**

1. ADAM (and any name whose only store rung is `data/baskets/ohlcv`) is invisible to the
   deck. Universe question, not a desk question.
2. `engine/us_leader_pullback.py` (R4) was absent on this base, so lane (d) ran on the
   minimal inline signature. The swap is one import site and the live source is stamped on
   every row as `leader_pullback_source`; when R4 lands, the deck should be re-baked and
   this receipt's lane-(d) numbers re-read.
3. `us_basket_turn`'s ledger has one date. Trigger (c)'s `days_since` is 0 while the state
   holds and null otherwise — it is never back-dated. The replay's (c) column stays null
   until that ledger has history.

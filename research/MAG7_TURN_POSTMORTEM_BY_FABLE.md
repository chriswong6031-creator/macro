# Post-mortem — the 2026-06-26 Mag-7 turn and the 15-day detection gap

Status: ADJUDICATED POST-MORTEM (Fable, 2026-07-11). Method: three census lanes over
stores/git/ledgers + one web-research lane, then two independent recompute lanes
re-deriving every load-bearing number from the primary stores, then an Opus red-team of
the causal synthesis (verdict REVISE — all required hedges incorporated below).
Companion docs: `MAG7_COMMAND_MASTERPLAN_BY_FABLE.md` (#2273, merged, W1 build landed
same day), `FLOW_CONTINUITY_MASTERPLAN_BY_FABLE.md`.

## 1. The episode of record

MAGS $61.60 (06-26 close) → $65.10 (07-02) → ~$67 (07-10); SPY +2.2% and SMH −3.2%
over the first window. June context: the cohort had shed ~$2.2-2.3T of market cap
(MSFT ~−17-20% for June). Memory (the year's hottest trade) broke 06-25/26: MU/SNDK
−10.6% on 06-26 alone; by 07-07 MU, Samsung, SK Hynix were all >20% off highs.
Leadership inside the recovery rotated: AAPL first, META (+8.8% on the 07-01 "Meta
Compute" announcement), NVDA/AVGO joining 07-07/08, META again 07-09/10.

## 2. Findings (each verified against primary stores; corrections in §6)

**F1 — The dedicated turn organs did not exist during the window** (verified birth
dates on origin/main): real engine-produced `turn_watch` 07-10 (the 07-09 file was a
synthetic fixture, immediately untracked); `mtf_upturn` ledger's first session rows
06-29/07-10, committed 07-11; `ignition_radar` born 07-11; the EOD options-flow summary
store born 07-02; the live flow poller TCC-dead until the 07-06 plist fix (first
day_state 07-07). `notify_state.json` shows all seven `mtf_upturn_mag7_last` keys =
NONE and zero ignition/tape_disagreement dedup keys — **no Mag-7 turn alert was ever
dispatched**. Scope note (red-team): this exculpates only the *absent* organs; it does
not cover the pieces that existed (F2, F3) — those are design findings.

**F2 — Pre-existing signals fired in-window and were never synthesized.** Verified rows
in `data/alerts/alerts_log.parquet`: 06-23 XLK holdings accumulation NVDA +2.31pp and
AAPL +2.04pp, both labeled "cycle NEARING A LOW · GET READY"; 06-25 "XLK RS vs SPY
crossed above 90th pctile (now 91)" — the session before the low; 06-26 "Net liquidity
4-week RoC flipped positive… −31bn → +69bn" — on the turn date; 06-30 XLK RS again (93).
Four rule families, info/warn severity, no cohort frame, no synthesis — while the
basket layer simultaneously labeled mag7 deteriorating→avoid (EW pct50 quantization +
20d-window straddle; see the Mag-7 Command masterplan L2 for the mechanics and the
merged fixes).

**F3 — Where an anticipation organ existed, it pointed at the wrong cohort.** The one
momentum-turn organ alive in the window (`mtf_upturn`, session 06-29) fired
UPTURN_CONFIRMED for four defensives — DGX, FIS, JNJ, REG — and zero Mag-7 members.
The EW-breadth and 20d-window constructions that suppressed the basket labels are
**design choices that predate the window**, not laws of nature (red-team correction of
our own first framing). Weekly/monthly MTF legs cannot confirm a 15-session V by
construction — that part is real physics — but the cohort-blindness was chosen.

**F4 — The flow stores saw the rotation; nothing aggregated or surfaced it.**
Recomputed cohort net premium (sum of the 7 members, Lee-Ready-signed pilot store,
$M): 06-22 −24.9 · 06-23 −33.8 · 06-24 −51.8 · **06-25 +146.8** · 06-26 +60.6 ·
06-29 +121.9 · 06-30 +85.2 · 07-01 +187.5 · 07-02 +15.6. The daily series flipped
positive one session before the price low; the 5-session sum first turned positive on
06-26, the low itself. Honesty constraints (red-team, binding): (i) this is
**coincident-to-at-most-one-session-leading — "flow led price" is NOT established**,
and flow-as-shadow-of-price is not excluded; (ii) the *generals lagged in flow* —
06-25 was led by the non-generals (+$110.2M vs AAPL+META +$36.6M), NVDA was −$11.1M on
the low day itself, and META's signature +$148.8M call spike came 07-01, five sessions
after the low (a confirmation, not a lead); (iii) the direction signing failed its own
promotion gate (bar recovery 0.41 vs the 0.70 bar; 44-65% of trades excluded at
midpoint), so a real-time cohort chip would have been **display-only visibility, not a
tradable signal**. What is honestly claimable: a cohort-level flow surface would have
made the generals-bid / memory-hedge split *visible* as it formed — MU put-heavy on
06-23/24/25/26 (and again 07-01/02), call-positive only 06-22/29/30; by 07-06 MU showed
+79k net new put OI vs META +90k net new call OI with SMH P/C at 6.28 — and today that
split is invisible because GICS grouping folds both into "Information Technology".

**F5 — The cycle organ was closer to right than the dashboards.** By 07-07
`cycle_pattern` had memory_storage at Phase=Peak, 3-month hazard 1.0 (maximum), and
mag7 at Phase=**Trough**, 3-month hazard 0.047 — directionally correct on both sides,
surfaced only as "HIGH-RISK BOUNCE" stances on a lab page (§6 corrects our own earlier
mis-read of this artifact).

**F6 — Ops failures compounded exactly at the peak.** Nightly failures 07-08/09; the
07-11 collect job cancelled at exactly its 100m timeout (silent cancelled-conclusion
class) so the engine ran green on a store frozen at 07-09 — the two strongest sessions
(META/NVDA leadership) never reached the site. Fixed same day (#2274 + a concurrent
operator fix; staleness now warns loudly).

**F7 — The narrative stores could not have answered the operator's question.** No
statement tape exists: `data/trumpflow` is a family-investment graph (EDGAR), the
whitehouse lane only began ingesting 07-03, news_vector keeps a ~5-day rolling window,
and financial_news has one archived day (07-04) in the window. The policy-put doctrine
read "put-present" every day but never fired an active signal at the turn.

## 3. The narrative question ("was it Trump?")

Verified external timeline (web lane; quotes sourced; narrative **context, not
findings**): 06-07 Truth Social "stocks should go up, not down"; 06-26 Warsh-confidence
/ low-rates remarks (day 0 — coincident); 07-02 CNBC Kernen interview ("81 records…
everybody's profiting"); 07-06 Rose Garden "a couple of guys who went short, those poor
bastards… being wiped out". **The loud statements trailed the low by 4-7 sessions.**
The press-attributed recovery drivers — June positioning washout, MS/GS buy-the-dip
calls, Iran-relapse haven bid into mega-caps, OBBBA/tariff tailwinds, Q2 capex-preview
optimism — and the memory-crash drivers (profit-taking after the 06-24 Micron blowout
peak, NAND capacity-addition fears, the 07-07 Samsung expectations miss; HBM itself
reported still structurally tight) are hindsight narrative fit: plausible, sourced, and
**unverifiable within our data** — we label them context and build the statement tape
(FC-R9) so the next episode is checkable in-house.

**The "Trump says buy" heuristic, honestly:** the catalog is n≈3-4 *selected* episodes
(2018-12-26: one day after the exact bear low, +7.9% next month; 2025-04-09: durable
low, statement hours *before* the policy action; 2020-03-13: ten days and −10% early)
with **no false-positive denominator** — nobody counted the loud statements that marked
nothing. That is an anecdote, not an edge. This 2026 instance is a *miss* for the
heuristic as an entry trigger (statements trailed the low); the operator's real-time
doubt ("memory was falling off a cliff") was reasonable. What is worth building is not
a statement-follow signal but the deterministic statement *tape* + event catalog
(conditions-framing, PS-R1-compliant), so the base rate can ever be measured.

## 4. Failure → fix map

| Failure | Fix | Status |
|---|---|---|
| No cohort regime read (F2/F3) | mag7_regime.v1 + "Mag 7" panel + leadership_split disclosure + 10d horizon | **merged** #2273-#2279, #2291 |
| Persistence punished (F2) | ignition narrow "running · day N" (card + strip) | **merged** #2275, #2291 |
| Silent ops death (F6) | collect timeout + stale-store warnings | **merged** #2274 (+operator fix) |
| No cohort flow lens (F4) | Flow Continuity FL-B cohort aggregation + flow_desk strip | dispatched |
| No flow history (F4) | FL-A backfill from massive_options_day (2024-07→) | dispatched |
| Live flow 35-min latency, 18-ETF baselines, 48h evaporation (F4) | FL-C live-lane ops | dispatched |
| Turn surfaces flow-blind (F4) | FL-D display chips + expected-null ledger | dispatched |
| No statement tape (F7) | FL-E statement tape + event catalog exhibit | dispatched |
| Signing gate unpassed (F4) | FC-R10 calibration sessions scheduled | ops clock |

## 5. Standing lessons (memory-bound)

1. **Cohort visibility beats signal cleverness**: the rotation was visible in magnitude
   and P/C primitives we already trusted; it was the *aggregation frame* that was missing.
2. **A quiet state must never bury a persistent one** (freshness gates penalizing
   persistence is a recurring class — fixed twice this week).
3. **Post-mortems must separate absent organs from mis-designed ones** — "it didn't
   exist yet" and "it existed and pointed elsewhere" demand different fixes.
4. Verification pays: two recompute lanes + a red-team overturned three census numbers
   and one causal frame before publication (§6).

## 6. Corrections log (census → verified)

- NVDA signed-flow path: negative streak ended 06-24 (−$66.4M heaviest); **06-25 was
  +$23.7M**; 06-26 −$11.1M; positive from 06-29. (Census had "negative through 06-26,
  flip 06-29".)
- MU volumes: call-positive 06-22/06-29/06-30; put-heavy 06-23→06-26 **and 07-01/07-02**
  (census called 07-01/02 call-positive).
- options_flow summary store: **369** files (not 371); the store has **no z-score
  columns at all** — z is computed at flow_desk build time with `z_raw_fallback` until
  ≥20 obs accrue (census said "z columns NaN").
- cycle_pattern 07-07: mag7 Phase=**Trough**, hazard_3m **0.047** (census swapped in
  memory's Peak/1.0 numbers — the organ was more right than we first reported).
- intraday_flow (#2167/#2173) **is** in origin/main incl. a 30-min fastpath writing
  `site/live/flow_pulse.json` (a census lane read a stale checkout); the artifact shows
  `mode=no_data` as of 07-10 — investigated under FL-C.

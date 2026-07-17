# Risk & Scoring Revamp — program masterplan (adjudicated by Fable)

Status: **CHARTERED** 2026-07-17 by operator order, issued during the live 07-16→17 breakdown
(KOSPI −6.4%, Nikkei −4%, TWII −6.5% intraday; NQ futures −2.2% overnight after weekly NQ −4.8%;
AI-hardware member carnage median −25.6% off 63d highs) while macro.html displayed **Mixed / 50**
with no alert. Operator verdict: *"systems are not adequate or robust enough… needs a complete
revamp and improvement upgrade to our risk systems, scoring systems."*

Inputs: 6-lane diagnosis workflow (07-17 ~06:00Z) + 6-lane design/judge workflow (07-17 ~09:00Z);
all findings verified against live stores by an adversarial judge lane before adjudication.
Related shipped work: #2739 (overnight/Asia strip, intl cascade + spillover chips, staleness note,
us_stocks context strip — display-tier). Related chip: `task_88e38fba` (KR FX anti-fire + US
global-leg latency preregs). Registry: two construction kills appended to
`research/DO_NOT_REBUILD.md` §2 in this PR.

---

## §1 Postmortem — what actually failed (evidence-final)

1. **The signals existed in-house; none had a path upward.** On 07-16 close, all of the following
   were already written in our own stores, each dead-ending in a display-only organ:
   - QQQ **weekly MACD bear cross dated 07-03** (depth 72.5%ile) + 3B StochRSI pinned at k=7.7 —
     in `index_momentum.v1` (data/regime/latest.json); consumed only by an allocation-page context row.
   - AI-hardware **member carnage**: median member −25.6% off its own 63d high, ~70% of members
     ≥20% off, ranks 43/44/45/46 of 46 in us_sector_rotation (memory_storage = DECLINE) — no
     market_state or radar consumer.
   - **CN/HK/TW intl radars at 98/91/98 alert=true** — zero wired path into the US radar; the US
     "global" leg reads day-stale US-listed country ETFs (87% above 200dma → calm 49.7).
2. **A real correctness bug masked the operator's own signal.** `market_state.trend` (weight 0.24)
   reads `cycles.mtf_snapshot` → `daily.resample("W-FRI").last()` on the live frame
   (engine/cycles.py:283), so the **partial** bounce week (07-14..16) printed `macd_pos=True /
   trend=85 GOOD` while the **completed** 07-10 weekly bar had already rolled (QQQ hist −0.212,
   vel3 −1.324). The weekly signal the operator read off TradingView was in our data and our own
   trend component overwrote it with an unfinished bar.
3. **The displayed score was structurally floored at 50.** Raw 76 → capped 50 by the radar
   override; every path below 50 requires SPY<200dma (8.1% above), a drawdown-band escalation, or
   ≥3 radar corroborators. The loud-alert 200dma gate is pre-registered anti-cry-wolf calibration
   (precision 0.085→0.249) and is NOT the defect; the missing piece is any expression of
   **trajectory** between "Mixed" and "alert".
4. **Hard measurement limit (governs this whole program):** every forward log begins 06-23/06-26;
   the entire recorded history IS this one deterioration episode. **No calm-regime false-positive
   rate is computable from repo data today.** Every "would have fired" table below is in-sample on
   the motivating episode.

## §2 Rulings

- **R1 — The 200dma loud-alert track is untouched.** No threshold, band, weight, or gate of the
  existing risk_radar/market_state calibration changes in this program. Making yesterday alert is
  reactive overfitting (RISK_RADAR_TUNING §5 precedent; count-conjunction kill at its line 93/107
  stands). Standing.
- **R2 — Because no FP budget is backtestable (§1.4), every new construction ships display-tier
  with a forward ledger from day one** and carries the plain-word unproven disclosure
  (doctrine-compliant: Tier-1 stance + Tier-2 receipt "accruing since 2026-07-17, unproven").
  **Earliest promotion review: 2026-10-17** (one quarter of out-of-episode accrual), via the
  standard gauntlet (day-level lift ≥1.20 + permutation + era split). No exceptions, including
  for operator urgency.
- **R3 — W1 BUILD-NOW: Weekly Trend-Health organ** (`engine/trend_health.py`, display): 4-state
  machine (HEALTHY / COOLING / ROLLING / BROKEN) per index (SPY/QQQ/IWM) read from **completed**
  W-FRI bars in the already-accruing `index_momentum.v1` grids (hist sign, hist_vel3, cross
  events, 3B StochRSI confirmation). 07-16 print: SPY COOLING · QQQ ROLLING (since the 07-10 bar)
  · IWM COOLING. Zero new data. Hero chip + risk-dialog receipt.
- **R3b — W1b correctness fix (paired, disclosed):** `market_state.trend` must read the
  **completed** weekly bar, not the live partial resample. This is premise repair of an existing
  component (same class as the #2574 gamma fix), not signal origination — but it DOES change a
  scored input, so it ships as its own PR with a dated before/after disclosure on the affected
  component score (07-16 counterfactual: trend 85 → materially lower) and a note in the
  market_state forward log at the switch date. Never batched silently with other changes.
- **R4 — W2 BUILD-NOW: `leadership_crack` organ** (display): fused two-leg state machine over the
  AI-hardware complex (union of ai_semiconductors/ai_infra/memory_storage/semicap_equipment
  members from data/baskets/ohlcv; freshness-gated; SPY leg from data/yahoo — SPY is absent from
  baskets/ohlcv):
  **Leg-1 velocity** = causal z of 5d equal-weight cohort return minus SPY (fired z=−3.36 on
  07-02, −3.9 on 07-07 — ~2 weeks of lead, judge-verified exact);
  **Leg-2 carnage level** (the former D2-B, folded in — never standalone) = median member
  drawdown from own 63d high + 3d-EMA share of members ≤−10/−20/−30% (07-15: −25.6% median, ~70%
  ≥20% off) with worst-6 named members.
  States INTACT / CRACKING / BROKEN. Distinct from killed IBD-distribution/MCO/Hindenburg
  families (cohort-relative velocity + absolute member drawdown, not market breadth counting);
  froth_fragility is structurally blind to this (grades on index-level −8% moves).
- **R5 — W3 BUILD-NOW: cross-market cascade meter** (`deterioration_cascade.v1`, display): state
  machine (STEADY / SLIPPING / DETERIORATING-FAST) on breadth + speed of foreign risk-off:
  n_alert across the 10 intl radar forward logs + band-escalation velocity. **Mandatory
  log-maturity guard** (judge finding): a market's escalation counts only once its log holds ≥5
  prior sessions — 7 of 10 logs were born 07-15/16 and TW's first-ever row IS 07-16; without the
  guard the 07-16 "fast" print is an artifact of log birth. Placement to be agreed with the ITR
  lane (cascade aggregate tile vs standalone macro organ) — coordination, not collision.
- **R6 — KILLED (registry rows appended §2 of DO_NOT_REBUILD):**
  (a) *cross-organ flip-counter (conjunction-of-transitions) as a standalone organ* — double-counts
  the cascade meter's intl leg, carries a log-birth FP (07-07), and is count-conjunction-class
  (governed by the RISK_RADAR_TUNING kill for any authority path);
  (b) *"4-of-4 defensive-lean floor bundle" as constructed (v1)* — its claimed 1-2 day lead
  **collapsed under verification** (only CN+HK alerted pre-07-16; TW's log began 07-16 → zero
  lead over the gap), and it is itself count-conjunction-class. The floor QUESTION stays open
  (R7); this construction is dead.
- **R7 — Floor mechanics (score below 50 pre-tape-break) is deferred to prereg, not built now.**
  Predicate: ≥1 quarter of W1–W3 forward accrual (R2), then a pre-registered study of whether
  any non-conjunction composition of the three organs earns the right to cap the displayed
  stance to "Defensive lean". Until then, deterioration is expressed by the organs' own chips
  next to the score — the score itself stays honest to its calibration.
- **R8 — Sequencing:** W1's `_macd_fade` helper extraction shares a seam with OPEN MLC W4 #2680
  (basket-scale histogram fade). W1 lands AFTER #2680 merges, or #2680 rebases onto the extracted
  helper — build order owned by this program; do not fork the helper.
- **R9 — task_88e38fba (KR FX anti-fire + US global-leg latency preregs) folds into this program
  as W4** (scoring-tier studies; unchanged scope).

## §3 Workstreams & build order

| W | What | Tier | Status |
|---|---|---|---|
| W0 | Overnight/Asia strip + cascade/spillover chips + context strips | display | **SHIPPED #2739** |
| W1 | Weekly Trend-Health organ (completed-bar MTF states) + hero chip | display + ledger | BUILD-NOW (after/with #2680 seam, R8) |
| W1b | market_state.trend completed-bar correctness fix | scoring (premise repair) | BUILD-NOW, own PR + disclosure (R3b) |
| W2 | leadership_crack organ (velocity + carnage) + hero chip | display + ledger | BUILD-NOW |
| W3 | deterioration_cascade meter (log-maturity-guarded) | display + ledger | BUILD-NOW (placement w/ ITR) |
| W4 | KR FX anti-fire + global-leg latency preregs (task_88e38fba) | prereg | chartered |
| W5 | Floor-mechanics prereg (defensive lean below 50) | prereg | GATED on R2 clock (≥2026-10-17) |
| W6 | Promotion review of W1–W3 ledgers | gauntlet | 2026-10-17+ |

## §4 Come-back checks

- First nightly after W1–W3 land: three new forward ledgers each append their first row; hero
  shows trend-health + crack + cascade chips with unproven receipts.
- 07-17/18 sessions: QQQ trend-health stays ROLLING on completed bars; leadership_crack state on
  fresh members; cascade meter respects the maturity guard (should NOT print DETERIORATING-FAST
  off log births).
- #2680 merge → W1 seam unblocked.

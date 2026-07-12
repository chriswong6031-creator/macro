# Rebalance & Liquidity Transmission (RLT) — masterplan

Status: ACTIVE — W0 ratified by Fable adjudication 2026-07-12 (this doc). Operator
complaint of record: 2026-07-12 session ("quarter-end tracking… TGA fell sharply…
did not transmit… still recommending healthcare… a failure").
Rulings: RLT-R1..RLT-R12. Waves: W1 (build, dispatched same day), W2 (evidence +
preregs), W3 (promotion adjudications).
Clocks: 2026-07-25 first pulse-ledger read · 2026-08-15 W2 prereg status review ·
2026-09-30 first LIVE quarter-end window under full instrumentation · 2026-10-15
promotion decisions alongside RC/FC/IHM program reviews.

---

## §0 Postmortem of record — June 26 → July 9, 2026

Operator thesis: the June tech correction bottomed on the Russell-reconstitution
volume day (traded June 26, effective June 27); the TGA drawdown after quarter-end
(~$919B Jun-30 → ~$745B Jul-9, ≈$175B injected) backstopped the correction; China
policy (State Council AI meeting Jun-29/30, PBOC half-year smoothing, Jul-7
PBOC/HKMA/SFC HK package) was confluent. The system failed to use any of it.

What the census (6-lane, 2026-07-12) actually found, with receipts:

**Captured and classified correctly (the complaint "did not transmit to Neural Web"
is factually wrong at the data layer):**
- TGA drawdown fully captured in `data/treasury/tga.parquet`: 919.1 (Jun-30) →
  807.4 → 770.6 → … → 744.6 (Jul-9). Net-liquidity canon (WALCL − RRP − TGA,
  `engine/canon.py`) showed +65bn/20d expansion.
- `neuralweb.liquidity_plumbing.v1` classified the episode honestly:
  `stress_liquidity_expansion` (RRP=0.5bn exhausted → mechanical, low-quality
  tailwind), `entry_effect=tailwind/low_quality_tailwind`. Transmitted to
  `world_state.json`, ask_brain, committee card, macro_context panel.
- The Risk Radar recovery chip **fired**: `turn_confirmed=True` by Jul-6 with
  catalyst `fed_netliq` — "Net liquidity (WALCL − RRP − TGA) rising — TGA drawdown /
  reserves added" (`data/market_state/latest.json`, asof Jul-8). Radar receded from
  the Jun-26 peak (top_score 90.8, caution) to `watch` by Jul-9.
- `sector_central` liquidity gate nudged gate_factor ×1.1 on expanding overlay.
- Jul-7 PBOC/HKMA/SFC package captured in `data/china_official/corpus_2026-07-07.parquet`
  (organ=pboc, title + Pan Gongsheng speech).

**Where it actually failed (the real complaint, restated precisely):**
1. **No salience.** The liquidity tailwind lived in a committee card and a
   macro-context sub-panel. Nothing at glance tier said "Treasury just injected
   ~$175B; the measured effect of this state is better dip-buying odds." The repo
   already OWNS a gauntlet-passed fact for exactly this — `research/LIQUIDITY_LADDER.md`:
   buy-setups under `liquidity_overlay=expanding` hit **+6.4pp better at 21d**
   (perm-p=0.013, month-dominant units; +8.3pp at episode units, p≈0.06; drawdown
   10th-pctile shallower). A validated odds edge existed and was not put in front
   of the user at the moment it mattered.
2. **Calendar blindness.** No engine knows US quarter-end dates, Russell
   reconstitution (rank/effective), or S&P quarterly rebalance as *events*.
   `engine/opex.py` knows quad-witching; `engine/hk_catalyst_calendar.py` knows
   FTSE/HSI/MSCI reviews for HK/CN — the US rebalance calendar is an unowned gap
   (also explicitly listed as a missing modality in
   `research/INTELLIGENCE_HUB_V2_RESEARCH.md`).
3. **The volume anomaly was in the stores and nothing read it.** June-26 per-name
   RVOL vs 20d: AAPL 4.65×, AMZN 4.88×, MSFT 4.32×, GOOGL 3.13× (`data/breadth/
   _volume_cache.parquet`); market volume 1.60× with up-volume share ~61%
   (`data/breadth/updown.parquet`). Note the honest wrinkle: NVDA 1.07×, META 0.99×,
   TSLA 1.15× did NOT spike — the pattern is quarter-end/S&P-flow-shaped at least as
   much as Russell-2000-shaped. Classification must be data-led, not narrative-led.
4. **No broad-market ETF flow data.** `engine/etf_flows.py` proxies
   creation/redemption for the 11 sector SPDRs only. SPY/QQQ/IWM/RSP have no
   primary-flow series, so "net inflow/outflow" cannot currently be measured at the
   index level.
5. **Standout board is constitutionally siloed from rotation.** Selection is pure
   per-stock bottoming-alignment; W9-B (2026-07-03) zeroed the US tailwind axis;
   `build_stock_library.py` has zero references to rotation_events /
   sector_fragmentation. Live board (as_of 07-10): VTRS(23), UTHR(20) as BOTTOM
   WATCH while `sector_central` reads XLV=Reduce(25) — and 4 Real-Estate names
   coexist with XLRE=Reduce(15). The board never *tells the user* about the
   disagreement. The sanctioned path to rotation-aware selection is RC-R9 S2
   (pre-registered study, W2-pending in Rotation Command) — not a naive gate.
6. **China policy plumbing is stale/partial.** `communiques.parquet` ends
   2026-04-28 (71d stale; backfill owned by CHINA_INTEL_CYCLES W1, in flight), so
   `china_policy_transmission` never saw the July events; official-corpus
   collection only began 2026-07-02 (Jun-29/30 State Council window predates it);
   no OMO *volume*, HKMA facility, or Bond Connect quota series exists; the
   asia-close lane was dead 07-03..07-10 (fixed #2193/#2199), compounding staleness.
7. **Ignition ledger gap (ops).** `data/ignition_log/us_ignition.jsonl` does not
   exist on the analysis box (only ca/hk) — whether the broad ignition channel
   fired at the bottom is not reconstructable locally. Fire-status must be
   auditable after the fact.

**Verdict on the operator's framing:** the failure was not collection and not
classification — it was (a) two genuinely missing data modalities (rebalance
calendar, broad ETF flows), (b) salience/actionability of an already-validated
liquidity odds edge, and (c) a disclosure gap on the standout board. The
constitution (LLM-origination ban, positioning-fusion ban, display-first gauntlet)
worked as designed and is not the defect; the defect is that the display tier
under-served the operator at the moment of confluence.

---

## §1 Rulings

**RLT-R1 — US rebalance calendar organ (display/context).** New
`engine/rebalance_calendar.py`: pure-rule calendar over `lib/nyse_calendar` —
quarter-end (last trading session of Mar/Jun/Sep/Dec ± window), Russell
reconstitution (rule: last Friday of June, with an explicit `RECON_OVERRIDES`
table seeded 2020-2026; 2026-06-26 is the seed row), S&P quarterly rebalance
(3rd-Friday quad dates via `engine/opex.py`), month-end (bond-index extension
days). Emits per-session tags (`td_to_quarter_end`, `in_qtr_end_window`,
`is_russell_recon_session`, `is_sp_rebalance_session`, `is_month_end_session`).
No signal claims, no seasonality scores (IHM "no seasonal signal" law respected;
TOM is dead post-2000 per NOVEL_IDEAS.md and is NOT revived here).

**RLT-R2 — Rebalance Pulse detector (display/context, ledgered).** New
`engine/rebalance_pulse.py` + `scripts/build_rebalance_pulse.py` (nightly,
off-render): deterministic day-classifier joining calendar tags × market volume
(`updown.parquet`: total-volume ratio vs 20d median, up-volume share) × per-name
RVOL breadth among mega-caps (`_volume_cache.parquet`) × close direction × (once
RLT-R3 lands) broad ETF net-flow direction. Vocabulary (frozen):
`mechanical_spike_absorbed` (calendar window + volume ≥1.5× + up-share ≥0.55),
`mechanical_spike_distributed` (…+ up-share ≤0.45), `mechanical_spike_mixed`,
`unscheduled_volume_event` (spike with no calendar tag), `quiet`. Append-only
ledger `data/rebalance_pulse/events.jsonl` (RC-R2 marker-integrity law applies) +
`site/marketdata/rebalance_pulse.json` with authority block
`{may_rank:false, may_gate:false, may_size:false}`. Synapse-registered; composed
into `world_state.json`; committee card. **It is NEVER a bottom-caller** — a
rebalance-day spike marking THE low is coincident-by-construction (RRX-R4/R10
class); the pulse ships as context with a forward ledger and may only seek
recovery-confirmer status later via the RRX-R2 rebound-capture ruler under a
pre-registered study (W2).

**RLT-R3 — Broad ETF primary-flow proxy.** Extend `engine/etf_flows.py` delta-SO ×
NAV proxy from the 11 sector SPDRs to broad index carriers (SPY, QQQ, IWM, RSP,
DIA) — closes the missing modality named in INTELLIGENCE_HUB_V2_RESEARCH. Stores
`data/flows/<T>.parquet` + net-flow z vs trailing 60d. Display/context; feeds
RLT-R2 classification and the flow-continuity cohort surfaces as context only
(FC-R12 non-circumvention respected: no Oracle/NW scoring wire).

**RLT-R4 — Named TGA impulse.** `liquidity_plumbing.v1` gains a
`treasury.tga_impulse` sub-block: episode detector on the TGA series (drawdown or
build ≥ $75bn within ≤10 business sessions, or ≥ $120bn within a quarter-start
window), with fields `{direction, magnitude_bn, days, since, quarter_end_adjacent,
summary_en, summary_zh}`. Plain-word summary of the mechanism ("Treasury spending
down its account puts cash into the system — supportive while it lasts"). The
existing quality machinery (stress-expansion vs benign, RRP-exhausted caveat)
stays authoritative — the impulse NAMES the event; it does not upgrade its
quality. Schema bump within display tier; de-escalation-only authority unchanged;
`score_raise=False` stays a hard constant. Also: fix the stale
`p3_reserve_balances="fail_open_until_wresbal_collected"` phase label to reflect
actual load state.

**RLT-R5 — Liquidity salience law (glance tier).** When
`entry_effect.direction=tailwind` AND radar trajectory ∈ {peaking, receding}, the
macro surface MUST carry a glance-tier plain-word line (existing chip/evidence-row
idiom, bilingual) of the form: state + stance + measured basis — e.g. "Treasury
cash is flowing into markets (+$65B/20d). Historically this state improved
buy-the-dip odds by ~6pp at 21 days — an odds edge, not a promise." Word budget
and banned-vocab per `docs/DESIGN_DOCTRINE.md`; the +6.4pp figure is the
LIQUIDITY_LADDER measured read and is quoted as "measured/backtested", never
"validated" (CI word-guard). The recovery panel's `fed_netliq` chip gains
magnitude detail (netliq Δ20d, TGA component). No new authority — this is
disclosure of an already-measured edge.

**RLT-R6 — Standout-board honesty chips (disclosure, not gating).** Every standout
row gains its sector's `sector_central` stance chip (e.g. "Sector: Reduce") and,
when stance ∈ {Reduce, Cautious}, a disagreement note: "per-stock bottoming
trigger; sector stance says reduce — this is not a sector call" (EN/ZH, existing
chip idiom, hover receipt to Tier-2). **Selection/rank/composition unchanged** —
suppressing or demoting names by sector-rotation state is rotation×cycle
entry-confluence (DON'T-TEST) and is only reachable via RC-R9 S2 under the
Rotation Command program. RLT contributes evidence and preregs to RC W2 (RLT-R8)
rather than duplicating a gate.

**RLT-R7 — Tech-cohort liquidity conditioning prereg (W2, display until passed).**
Pre-register BEFORE any outcome computation: does the liquidity tailwind state
(overlay expanding; secondarily plumbing headline states) improve washout→recovery
odds for TECH/Mag7 cohorts specifically (the operator's "buy dips in tech" ask),
vs the all-market LIQUIDITY_LADDER baseline? Estimator laws binding: episode-unit
permutation primary (month-block bootstrap anti-conservative; ticker-cluster CIs
without time control forbidden), pre-declared horizon ruler (21d primary per
ladder precedent), era-split printed. Null outcome → retained as confluence
context (context-accrual law); pass → promotion adjudication in W3.

**RLT-R8 — Rotation Command contribution (not duplication).** RLT builds, under
RC masterplan authority: (a) the RC-R8 PIT replay harness inputs it needs anyway
(rebalance-calendar tags joined onto rotation-event episodes), and (b) drafts of
the RC-R9 S1/S2 prereg docs for Fable/operator ratification in the RC program.
Any stance/gate change to standout selection remains RC-owned.

**RLT-R9 — China mechanical-liquidity registry (W2, narrow).** Curated,
deterministic, display-only: `data/china_official/hk_liquidity_facilities.yml`
(HKMA RMB Business Facility size 200B→500B w/ effective dates, Bond Connect quota
rows, discount-window injections), surfaced as context rows in the China intel hub
"what changed" packet (RUL-8 home). OMO *volume* collection investigated via
akshare (open question from census). Corpus→communiqués freshness is
CHINA_INTEL_CYCLES W1 property — RLT does NOT touch it; non-collision declared.
PS-R4/NAR-R4 respected: no LLM classification, no signed polarity before the W2
event study grades phrases.

**RLT-R10 — Ignition ledger ops honesty.** The US ignition ledger must be
reconstructable: ensure `us_ignition.jsonl` is written wherever the organ runs and
mirrored with the other forward ledgers (same class as the #2264 idle-refresh
pattern). Fire-status during Jun-27..Jul-9 to be back-audited from production once
mirrored; if unrecoverable, print the gap honestly on the committee card.

**RLT-R11 — Estimator & integrity laws (restated as binding).** Append-only
ledgers, nightly sole advancer; PIT discipline on every new store; no composite of
liquidity × rotation × flow into any score (positioning-fusion ILLEGAL,
RRX-R8 composite ban); verdicts only at pre-declared horizon rulers; "validated"
word-guard respected in all copy.

**RLT-R12 — Routing & build laws.** Sonnet builds, Opus reviews, Fable
adjudicates/merges; heavy compute off the render path; bilingual EN/ZH on every
user-facing string (no translated `title=`); design-doctrine read required before
surface work; existing chip idioms only in W1 (no new surface idiom without
mockup ratification).

---

## §2 What RLT will NOT build (standing kills honored)

- **No "buy dips in tech" stance fusion.** Liquidity state + tech washout →
  combined stance/score is positioning-fusion (ILLEGAL, Signal Commons 2026-07-05)
  and LLM-origination is forbidden. The legal form is: named display context +
  the measured ladder odds line (RLT-R5) + the RLT-R7 prereg → gauntlet →
  promotion path.
- **No sector-rotation suppression of standout names** outside RC-R9 S2 (rotation ×
  cycle-position entry-confluence is DON'T-TEST).
- **No rebalance-volume bottom-caller.** Coincident-by-construction (RRX-R4/R10
  class); context + forward ledger only, RRX-R2 ruler for any future confirmer
  claim.
- **No turn-of-month/seasonality signal revival** (dead post-2000; D2-10 blocked);
  the D2-11 quarter-end pension-rebalance *signal* study stays in its authorized
  LG-US-RATES-CAL slot — RLT provides the calendar/flow inputs, not the verdict.
- **No touching the sector deteriorating→avoid channel** (M7C-R4: operator-ratified
  prereg required) and no re-litigating W9-B tailwind-weight-zero by code change.

## §3 Waves

**W1 (dispatched 2026-07-12, four PRs, display/context tier — ships freely):**
- PR-A: RLT-R1 calendar + RLT-R2 pulse organ + ledger + synapse/world_state/
  committee wiring + descriptive field-guide census of 2023→2026 quarter-end
  windows (field-guide-first law) + macro context chip in existing idiom.
- PR-B: RLT-R4 TGA impulse + RLT-R5 salience line + recovery-chip magnitude +
  WRESBAL phase-label fix.
- PR-C: RLT-R3 broad ETF flow proxy extension.
- PR-D: RLT-R6 standout sector-stance/disagreement chips.

**W2 (next):** RLT-R7 prereg doc + execution on historical PIT data; RLT-R8 RC
contribution (replay inputs + S1/S2 prereg drafts); RLT-R9 China registry +
OMO-volume collector investigation; RLT-R10 ignition ledger mirror + back-audit;
first live quarter-end dry-run review (2026-09-30 window).

**W3:** promotion adjudications on RLT-R7 result and pulse-ledger accrual;
RC-R12 alignment; kill/retain rows appended to DO_NOT_REBUILD as earned.

## §4 Collisions declared

- Rotation Command (RC-R8/R9 pending): RLT contributes, does not duplicate; no
  stance/gate change in RLT PRs.
- Flow Continuity (FC-R12): no Oracle/NW wiring of flows; cohort surfaces get
  context labels only.
- CHINA_INTEL_CYCLES W1 (communiqué backfill in flight): untouched by RLT.
- INTL_RISK_DESK (W0 2026-07-12, unmerged): SOFR quarter-end "technical — label"
  and Phase-5 swap lines belong to IRD; RLT-R4 names TGA impulses only.
- LG-US-RATES-CAL (D2-11/12 authorized slot): signal verdicts on quarter-end
  pension rebalance stay there.
- Open PRs #2317/#2129/#2098/#1888/#1875/#1780/#1639: no file overlap identified.

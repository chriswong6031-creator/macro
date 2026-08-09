# CN LIMIT-MOVE ALPHA — Fable orchestrator handoff — 2026-08-08

> **2026-08-09 STOP-SHIP re-audit.** Every Wave-0 exact-board, continuation-rate,
> feature-lift, headline multiplier, tolerant vendor-agreement, and 300363
> price/return/legal-band claim is withdrawn.
> The input was the Yahoo-adjusted `data/china_stocks` plane, which cannot establish nominal
> CNY ticks or exchange legal bands. Until an authorized, complete TuShare unadjusted `daily`
> + vendor `stk_limit` plane passes the canonical manifest and bounded integer-cent equality
> gates, the only admissible verdict is `BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT`.
> Nothing in this handoff has candidate, ranking, sizing, gating, Prophet, Neural Web, or
> trading authority; outcome-selected examples remain context-only ore.

**To:** a fresh Fable-led session (operator-ordered frontier orchestration; you plan, adjudicate,
and brainstorm — Opus builders execute measurements/backtests; you never grind token-heavy
tests in your own loop). FABLE-WHY: creative: operator-ordered open-ended strategy invention
over a novel mechanism space — fails the draft-and-review test by construction.
**From:** the 2026-08-08 ANTICIPATION session (Fable). Program root: `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(f)(2), §6.9.
**Operator charter (distilled from the 2026-08-08 order, preserve this intent):** the A-share
limit-up/limit-down mechanism is structurally ripe for edge: capped daily bands stretch what US
tapes price in one 20-40% session into 3-4 days of consecutive boards (连板), forced-spectator
psychology (T+1, weekends, after-hours 发酵) invites crowding and chase, and the game is so
mainstream that TongHuaShun ships a daily limit-up board as a product feature. Even a 5-10%
true probability of onset is a PORTFOLIO edge (spread across many names, "delta-neutral-like"
expectancy). Continuation matters as much as onset — the goal includes entering DURING the
first board day and riding rerating windows. Do not lock into 10%-every-day rigidity: the
target is the trajectory of rerating windows (6% one day, 8% the next, a board here and there).
The operator believes footprints exist before onset and before continuation, and orders
aggressive first-principles + second/third-order brainstorming, reverse engineering from past
examples, and probability construction from our technicals/confluences/Prophet methods. This
session exists to find them or to prove — construction by construction, with an ore ledger —
what was actually tried.

## §1 THE ORE LAW (binding on every verdict in this session)

Operator doctrine, 2026-08-08, now standing law: **an operator hypothesis is ORE, not a
claim.** The failure mode to prevent: applying hypothesis-HARDENING lenses (pre-registration,
strict nulls, single-construction tests) during the hypothesis-EXPLORATION stage, so a rough
thesis with gold in it gets trashed on its first adverse measurement — the baby with the
bathwater. Mechanism, mandatory:

1. **Construction-space map BEFORE any verdict.** For every thesis, enumerate the plausible
   constructions (variants, relaxations, adjacent mechanisms, different rulers/horizons/
   regimes) — Fable-level brainstorm work — and test the strongest few, not the first one.
2. **The ore ledger.** Every wave's receipt carries an explicit `UNTESTED VARIANTS` section.
   A null on one construction NEVER closes the hypothesis; a kill names exactly what was and
   was NOT tested. (This session's precedent: the earnings-confluence null tested ONE
   construction — marker-confluence in [T-5,T-1] — while the flow-footprint variant, the one
   matching the operator's actual SPCX observation, remains untested. That near-miss is the
   ore law's origin story.)
3. **Exploration tier ≠ promotion tier.** House epistemics already says the gauntlet gates
   PROMOTION only. In exploration: generous constructions, printed nulls, fast iteration,
   display-tier everything. Pre-registration discipline applies WITHIN a construction (no
   post-hoc feature audition inside one test), never ACROSS the space (trying many
   constructions is the job, not p-hacking — the holdout/forward ledger is what keeps us
   honest at promotion time).
4. **Fresh-eyes rule.** Mid-program, spawn ONE independent Fable brainstorm subagent
   (`orchestrator` + explicit `model:'fable'` + FABLE-WHY per routing law) BLINDED to §3-§4
   below — give it only §0-§2 and the data inventory — then merge its construction list with
   yours. Anchoring on the commissioning session's ideas is itself an ore-loss mechanism.

## §2 What exists (read these before inventing)

**Receipts (all committed):**
- `research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.{md,json}` + script (PR #4999)
  — legacy Wave-0 instrument, now `SUBSTRATE_INVALID_DIAGNOSTIC_ONLY`. Its event keys,
  transition/return tables, legal-band classifications, and verdict are not admissible market
  findings because the Yahoo plane is split-adjusted. It may be used only to audit detector
  engineering; it cannot supply a probability, lift, feature, strategy, or promotion claim.
- `research/cn_prophet_audit/CASE_300363_FULL_CHAIN_2026-08-08.md` — post-selection pipeline
  forensic only. All exact price, return, legal-board, fillability, score, and rank claims are
  quarantined. The remaining ore is store/run lineage, missing execution receipts, and mutable
  ledger provenance; none authorizes selection or a port.
- `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` and
  `research/cn_limit_alpha_sol/W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.md` — canonical
  replacement contract and present truth: foundation-only, no live vendor authority, and
  `BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT`.
- ANTICIPATION receipts for method idioms: zone mechanics (−4.97pp entry location, PR #5007),
  §6.6 revision rules, era stamps, forward-ledger law.

**Data + machinery inventory:**
- `data/china_stocks/*.parquet` is a curated Yahoo `auto_adjust=True` OHLCV plane. It may
  support non-legal-band diagnostics but is forbidden for exact limit-event or strategy
  measurement. The replacement substrate is authorized TuShare unadjusted `daily` joined to
  same-key vendor `stk_limit`; current repository receipts say that plane is not ready.
- `data/china_pick_lab/fires.jsonl` — limit machinery already modeled: `limit_width`,
  `limit_state` (open/locked), `fillable`, `t_plus_one_risk`. READ ITS EMITTER first.
- `engine/china_microstructure` — house limit-width/board-type conventions (10%/20%, ST 5%,
  new-listing exemptions). `data/china_microstructure/limit_events.parquet` — KNOWN DEFECT:
  34 names missing pre-2026-07 history while `backfill=True` claims completeness (data-plane
  heal is fair game for a wave).
- **`china_zt_pool`** — an independent vendor scrape that may become a reconciliation witness
  or richer metadata source. It is not legal-band ground truth and no tolerant agreement rate
  is admissible until exact keys are reconciled against the canonical TuShare event plane.
  A small 封单 order-wall sample exists; any collector extension remains data context only and
  requires its own provenance/licensing receipt.
- CN board machinery for features: `engine/china_basket_turn.py` (washout lifecycle),
  `china_board_rank.py` (species_id, reversal_member, theme_timing), `setup_tier.py`
  (ripening), `subsector_confluence.py` CN half (THS-concept confluence — the 题材 mapping!).
- House traps that WILL bite: per-date-ledger-run-date-stamping, keep-first dual-run latch,
  resolution-conditioned denominators, numpy-bool truthiness, TZ (CN sessions vs UTC), the
  curated-universe survivorship shape.

## §3 First-principles decomposition (my brainstorm — the blinded subagent must NOT see §3-§4)

**Mechanism taxonomy (different physics ⇒ different footprints ⇒ separate models):**
(a) NEWS/RERATING boards — a repricing event too big for the band. The quarantined 300363
outcome-selected anecdote may motivate constructions but supplies no quantitative evidence. Footprint
family: pre-event accumulation (vol-z, run-up), sector/theme heat, washout-maturity of the
base it launches from. Continuation physics: distance-to-fair-value proxy (how much rerate is
"left"), measured by post-event drift in comparable US/HK names when a cross-listed or
sector-parallel exists (BABA/9988-style pairs; the US tape prices the same news instantly —
**a cross-market oracle for how many boards the rerate "should" take"** — likely novel, test it).
(b) THEME/CASCADE boards (题材接力) — leaders seal, followers chase in relay tiers. Footprint:
sector limit-heat, leader's board count, the follower's rank within the
concept (THS confluence machinery maps this). Second-order: relay EXHAUSTS when follower
quality degrades (later movers are junkier) — a measurable quality-gradient clock.
(c) MOMENTUM/GAME boards (打板 games) — reflexive, driven by the board ecology itself.
Regime instruments (computable from our catalog TODAY): daily first-board count, highest
active board count (the sentiment ceiling), next-day continuation realized rate (rolling),
炸板 proxy via near-limit-close-without-limit frequency. Third-order: when the highest-board
name breaks, the whole ladder de-rates next session (measurable as conditional continuation
collapse on ladder-leader failure days).
(d) SQUEEZE/SEAL mechanics — the seal (封单) is a commitment signal; daily bars see only its
shadows: **next-day OPEN GAP is the overnight-demand read on seal strength** (auction reveals
what the lock hid). P(board T+1 | board T, open-gap decile at T+1 open) is an ENTRY-TIMED
probability — decidable at 9:25 auction, tradable at open. This may be the single most
tradable construction we have with daily data alone.

**T+1 and the crowd clock:** buyers on board-day are forced holders; their next-open P&L
drives the morning auction; weekend boards ferment (operator's observation) — test
day-of-week conditioning on continuation. After-hours discussion cycles imply LATE-DAY seals
(if/when we get first-touch time) carry different continuation than open seals — flag as a
data-gap question for the 封单/first-touch collector.

**Fillability is the strategy's spine, not a footnote:** a locked board is unfillable; the
tradable set is {pre-seal entries, seal-break (开板) re-entries, next-open entries}. EVERY
backtest must price entries at a fillable moment (fires.jsonl idiom) — expectancy computed on
unfillable fills is fiction, and this is where most retail 打板 backtests lie.

**Portfolio construction (the operator's spreading hypothesis):** onset plays may be
lottery-like and continuation may differ by ladder state, but no probability, legal cap,
fillability, or Kelly input is validated yet. Construction work may model a joint onset /
continuation / regime book only after the canonical substrate gate; no sizing ships from the
legacy receipt.

## §4 Strategy shapes to seed the space (test the strongest, not the first)

S1 NEXT-OPEN CONTINUATION RIDER: enter at T+1 open on gap/feature filter after a first/second
board; exit rules per board-state machine (hold while sealed-by-close, exit on break + fail
to re-seal, time-stop). The most data-feasible TODAY.
S2 ONSET PORTFOLIO: daily top-K by the six-feature probability (calibrated, holdout), entered
near close BEFORE any board (the 9.5%/19% near-limit shadow as same-day confirmation),
spread thin. Needs the calibation wave first.
S3 THEME RELAY: leader-board detection → follower ranking via THS-concept machinery →
follower entries while fillable. `subsector_confluence` is a construction scaffold; the
quarantined 300363 case is not evidence for it.
S4 REGIME GATE over everything: board-ecology instruments (first-board count, ceiling count,
realized continuation) as an on/off/size hypothesis. The legacy era rates are withdrawn; a
regime conclusion requires the canonical point-in-time full-A plane.
S5 CROSS-MARKET RERATE ORACLE: for dual-context names/sectors, use the uncapped market's
instant repricing to estimate boards-remaining. Novel; measure before believing.

## §5 Execution protocol

- **Waves, session-chained**, each: Fable construction-map → Opus builders measure (isolated
  worktrees, targeted tests, receipts committed) → Fable adjudicates → ore ledger updated →
  ship display-tier artifacts freely (operator §6.0 ruling: not live to other users; ship
  fast, they review daily). Model routing law binds: builders/reviewers Opus; census Sonnet;
  your loop and the ONE blinded brainstormer are the only Fable contexts.
- **Forward ledger from wave 1** (the zone precedent): every probability the system emits
  gets stamped and graded nightly — the calibration curve IS the product's spine. Era-stamp
  everything; nightly is the sole ledger advancer; fillability recorded per entry.
- **Universe honesty:** extend beyond the curated 1,842 where the game lives (zt_pool names
  as the completion set; ST/new-listing exclusions explicit). The 34-name/backfill-flag
  defect in limit_events.parquet is a wave-0 heal candidate.
- **Success definition (not profit promises):** a calibrated P(board) / P(continuation) model
  beating the base-rate ladder on holdout AND a fillability-honest paper book with a graded
  forward ledger ≥10 sessions, plus the regime gate. Authority promotion (any live surface
  claiming action) goes through the gauntlet per house law — display-tier ships freely.
- **When blocked on data**, propose collectors with expected discriminative value (封单,
  closing-auction imbalance, first-touch/seal-break times, THS concept membership snapshots)
  — the operator pre-authorized building data context and reads proposals daily.

## §6 Sibling ore-veins (NOT this session's scope — recorded so they are not lost)

- EARNINGS FLOW FOOTPRINT (US): the confluence construction nulled (#4993) but the operator's
  actual observation (AMZN/MSFT/DLB/SPCX) was arguably FLOW-shaped and the tested window
  never even admitted their receipts (chart OPEN-label illusion + 8-session lead). The flow
  variant (volume character / darkpool / GEX pre-event anomalies) is unmined ore — recommend
  a second Fable handoff after this session's wave 1.
- US species-conditional ladder + leader-pullback v1 (leg timing, zone-with-expiry) — in the
  ANTICIPATION chain, Opus-executable, no fresh Fable needed.
- The §6.6 US status re-measurement's H≥21 empty cells — re-run as anticipation-era episodes
  mature; the CN-ordering question is NOT settled, only unmeasured at its chartered horizon.

Operator, verbatim intent to honor throughout: *"intuition and dense contextual local state is
the value that I can bring to the table... I would like it to be completely unraveled and
tested so we don't throw away the ore half refined."* That sentence is this session's contract.

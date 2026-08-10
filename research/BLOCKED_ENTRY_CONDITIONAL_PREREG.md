# Blocked-entry conditional override — PRE-REGISTRATION

**Registration commit:** `98fe6113af617a7f37f6efce85c6945eaa37cff0` at
`2026-08-10T05:35:10Z`. Author attestation: frozen before any held-out results were
viewed; no study implementation or results artifact exists in the repository at that commit.
**Family:** `blocked_entry_conditional_v1` (Terminal `bear_block` override arm).
**Instrument:** scratchpad `blocked_entry_study/study.py` (committed with results doc on completion).
**Operator direction (2026-08-10):** no shadow-ledger delay; mine the full backtest history now;
distill WHEN blocked fires should be taken vs honored; grade with stop-based execution, not
fixed-horizon averages. This prereg freezes that study's gates so a passing result is immediately
ratifiable and a failing one closes cleanly.

## §0 Standing-law position (why this is legal to run tonight)

- `DNR:KILL-200DMA-RECLAIM-VETO-FLAT` bars a FLAT drop of Prophet's reclaim veto; its §9 ruling
  explicitly sanctions **regime-conditional constructions through their own prereg**. This is that,
  applied first to the Terminal's `bear_block` (a sibling gate, distinct era/fence). A passing
  verdict here does NOT flip Prophet — the Prophet arm gets its own prereg under `us_prophet_v1→v2`.
- Not a regime scorecard/fusion (`DNR:KILL-REGIME-SCORECARD`, `KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR`):
  conditioning uses two plain, existing measures (SPY drawdown/200dma state; the name's own 2-week
  StochRSI) — no composite score, no positioning keys.
- Research tier: context-only, with no display or accrual authority; it cannot rank, gate, size,
  enter, issue, or alter Prophet/Neural Web. Any LIVE veto behavior change requires the operator
  era stamp (§4) — the LLM originates nothing (A7).

## §1 Cohort and execution construction (frozen)

Events: every raw CB/revBuy fire vetoed **only** by `bear_block` (would-enter with the veto off;
keeper-quality `block` bars excluded), replayed by the production `signal_layer` over full local
history, ~1,540-name US panel + HK/CN names where local OHLC exists. PIT entry at the first session
after the fire is knowable (`known_ts`).

Execution: stop = min(low, fire 3D bar + 2 prior) − 0.5×ATR14(daily) [design-era tunable ×only];
stopped on daily close < stop; graded (a) stop-only + 252d time exit, (b) breakeven trail at +1R,
(c) 63d fixed. Metrics: expectancy in R, win/stop-hit rates, bought-the-low rate, p90/p95, runup
capture 126/252d; arms: taken-entries, per-name-year matched random-date placebo.

## §2 Pre-registered hypotheses and gates (held-out era 2019+, parameters frozen on ≤2018)

- **H1 — ordinary washout override.** Blocked fires with the market NOT in systemic bear
  (SPY <15% off 252d high AND not >40 sessions below its 200dma; definition may be tuned only in
  the design era) have stop-execution expectancy **> 0** AND **> the matched placebo arm**, on the
  held-out era, with a date-clustered bootstrap 95% CI excluding 0 on the R-expectancy. Per-date
  weighting reported alongside pooled (both must be sign-positive; magnitude gate on pooled only).
- **H2 — systemic-bear total-washout timing.** Within systemic-bear windows, blocked fires with the
  **total-washout flag** (name 2W StochRSI %K turned up from <15 within the last 2 two-week bars)
  beat those without it: conditional expectancy difference > 0, date-clustered 95% CI excluding 0,
  held-out era. If either cell has <30 fires or <10 distinct dates, the verdict is **UNDERPOWERED —
  DISCLOSED**, not a pass or fail; the cell keeps accruing.
- **Sensitivities (no independent verdicts):** intrabar-low stops, entry-at-close basis, depth bands,
  fire-density breadth. Multiple-testing budget: H1+H2 are the only promotion-bearing tests.

## §3 Decision rule (what each outcome ships)

A study verdict is context-only: neither a display promotion nor an entry-mask change is automatic.
Both require the operator ratification and era fence in §4 before they can ship.

- **H1 PASS →** Terminal display promotion: non-systemic blocked fires render as a distinct
  "washout override candidate" class (amber→green-outline tier, plain-word copy; falsifier language
  stays off user surfaces), and the live `enter` mask change (take these fires) is queued behind the
  §4 era stamp — a one-line conditional in `confluence_v2`, shipped only with operator ratification.
- **H2 PASS →** the same, extended inside systemic bears gated on the total-washout flag.
- **H1 FAIL →** the override construction (this stop/entry definition) closes for the non-systemic
  cell; the ⊘ stays refusal-only there. Closes THIS construction, not the search space (ore law).
- **Any outcome →** results doc + tables commit next to this file; the six operator exemplars
  (UEC/HL/NEM/9988/600547/002716) reported as named rows regardless of verdict.

## §4 Era stamp and fences

Live Terminal behavior change requires: operator ratification recorded in this file's §5; a Terminal
signal-era fence (`signal_layer` emission version bump, mirroring `hk_prophet_v2`'s
`BOARD_DEFINITION` pattern) so pre/post events never pool; slice `schema` field carries the version.
Prophet-side reclaim-veto conditional: separate prereg, `us_prophet_v1→v2`, per packet §9.

## §6 AMENDMENT 1 — local-systemic altitude (frozen 2026-08-10 ~07:1xZ, before round-2 results)

**Operator objection (2026-08-10, accepted):** the SPY-drawdown gate is the wrong altitude in a
rotational tape — the index sits at highs while names/baskets crash, so the §2-discovered sysA rule
would refuse all six live exemplars. SPY-systemic is DEMOTED to a disclosed venue. Round-2 axes,
index-free, gates frozen before any round-2 number is viewed (second look, labeled; A1/A2 are the
only promotion-bearing tests of this amendment):

- **A1 — local (sector/complex) systemic:** blocked fires where the same-sector peer-median
  drawdown from the 252d high exceeds 20% (threshold and the sector-label source tunable/selectable
  on the design era only; sector coverage % reported with a ≥60% floor, unmapped names excluded not
  defaulted). Gates (held-out 2019+, date-clustered B=2000 CIs): expectancy R CI > 0 AND
  (local-systemic − complement) difference CI > 0.
- **A2 — washout breadth:** same-date blocked-fire count at or above the design-era 80th percentile
  (panel-size-normalized). Same two gates.
- **A3 (descriptive, no gate):** coverage — would A1∪A2 have admitted the six live exemplars'
  fire dates (to local-tape edge), and what share of held-out blocked fires each axis admits.
- Composite scores remain forbidden (DNR:KILL-REGIME-SCORECARD) — A1 and A2 are two plain
  measures adjudicated separately; no fusion, no weights.

**§6 ADJUDICATION (2026-08-10 ~08:3xZ; round-2 receipts in session scratchpad
`blocked_entry_study_r2/`, run from the committed instrument @83230a70d9d):** **A1 PASS** on both
registered gates, both weightings (held-out cell +1.675R [1.294,2.088]; diff vs complement +1.228R
[0.821,1.620]; equal-date diff +0.535 [0.134,0.914]; 11 episodes; episode-clustered CI
[0.520,3.689] — ~3× wider, still >0). **A2 SPLIT → NOT promoted** (equal-date diff CI crosses 0:
[−0.028,1.067]); keeps accruing. **sysA re-scored at 6 episodes — episode-thin; stays demoted.**
Floor ruling: the §6 coverage floor is read FIRE-WEIGHTED (61.6% PASS — the floor's purpose is
coverage of the adjudicated events); name-weighted 59.7% and the mapping-selection effect
(unmapped non-index micro-caps are a weaker cohort, 0.722 vs 0.843 meanR) are disclosed — A1's
verdict claims mapped-universe validity only. **COVERAGE-GATE FINDING (why A1-as-constructed does
NOT ship):** at the design-selected 25% threshold A1 admits 1 of 3 computable live exemplar fires
(UEC refused — GICS "Energy" peers dilute the uranium complex); 20% admits 2 of 3; today's
membership is threshold-critical (25% → IT only; 30% → none). Sector is the right ALTITUDE, wrong
PEER SET. **Survivorship: panel confirmed survivor-only**; the delisted store (199 names,
closes-only, 83.4% absent from the panel) cannot repair a stop-based study; bias bound
Δ ≈ −2.675p (p=20% → −0.54R); A1's episode-CI floor approximately survives; all LEVELS read
optimistic, CONTRASTS are the more robust quantity. **Episode-clustered CIs supersede
date-clustered for every promotion-bearing read from this point.**

## §7 AMENDMENT 2 — thematic-basket peer set (frozen 2026-08-10 ~08:4xZ, before round-3 results)

**A1b — basket-local systemic:** identical construction to A1 with the peer set replaced by the
repo's own thematic-basket membership (candidates-parquet `theme_membership_ids` /
`site/basketdata` definitions; a name's peers = its primary basket's members; names in no basket
fall back to GICS sector; both coverages reported, fire-weighted ≥60% floor on the union).
Threshold grid {15,20,25,30}% peer-median drawdown from 252d highs, design-era-selected by
absolute separation as before; **exemplar admission per threshold is REPORTED, and the shipped
threshold is an explicit operator aggressiveness choice at ratification — not a statistical
claim.** Gates identical to A1 (held-out cell CI>0 AND diff-vs-complement CI>0, equal-date read
alongside pooled) PLUS episode-clustered CI>0 (per §6 adjudication). Third look, labeled. **Run
gated on the round-1 red-team resolving the gap-through-stop fill and CN limit-fill questions —
any confirmed sim flaw is repaired first and round 3 runs on the repaired instrument.**

## §5 Ratification log

- **2026-08-10 ~06:4xZ — ADJUDICATED** (results:
  `research/BLOCKED_ENTRY_CONDITIONAL_RESULTS_2026-08-10.md`): H1 **PASS, CONTEXT-ONLY**
  (held-out +0.572R [+0.384,+0.785]; vs placebo +0.580R [+0.390,+0.777]; registered equal-date
  reads +0.492R and +0.419R with CIs excluding 0); H2 **FAIL-INVERTED** (washT−washF −1.003R
  [−1.729,−0.367] — the wait-for-turn precondition is harmful, construction closed). Post-hoc
  discovered rule (systemic-bear immediate entry, +1.45..+1.79R, CIs exclude 0, only
  positive-median cell) is the promotion candidate — **awaiting operator ratification** of that
  specific rule plus the production-feed re-grade (results §3.2) before any live `enter`-mask
  change. Display promotion is not automatic either; it awaits the same ratification/re-grade and
  the §4 era fence. No live or reader-facing behavior changed by this entry.

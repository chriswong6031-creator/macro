# CN limit-move alpha — independent SOL construction map — Wave 1

**Date:** 2026-08-08 (America/Vancouver)  
**Tier:** exploration / display / audit only  
**Authority:** none; this document does not rank, size, gate, or recommend a live trade  
**Common charter:** `research/CN_LIMIT_ALPHA_FABLE_HANDOFF_2026-08-08.md` on
`origin/claude/rklb-prophet-missing-3d6c35`  
**Independence boundary:** this SOL lane read the handoff, the required v0 receipt, the 300363
case receipt, current `origin/main`, and public primary sources. It deliberately did **not** read
any `claude/cn-limit-w1-*` branch, worktree, result, or receipt.

This is the mandatory construction-space map **before** Wave-1 measurement. A weak result may
close one named construction. It may not close a mechanism family. Every receipt produced from
this map must end with `UNTESTED VARIANTS` and identify the exact entry clock, outcome ruler,
universe, era, fill rule, exit rule, and cost assumption that were measured.

## 0. Common prior, collisions, and corrections

The common-prior v0 receipt established a usable event catalog over the curated nominal-price
store, a large first-board continuation lift, material era dependence, and six sign-stable
pre-board features. It did **not** establish capturable returns or a calibrated joint model.
Its Markdown correctly adjudicates the tolerant rule as primary, but the frozen JSON definitions
and parts of the script payload still describe strict as primary. Downstream model IDs must mint
their own consistent, tested definition contract; they may not inherit that split-brain metadata.
The older `research/CHINA_ENGINE_REASSESSMENT.md` tested a different construction: a dip-plus-limit
flag entered with a fill-realistic delay. That generic positive-rank construction collapsed to
approximately flat at 5 sessions and negative at 21 sessions. It remains binding evidence against
an unconditional chase. It is not evidence against auction-timed, board-count-, regime-, flow-,
or rerating-conditioned constructions.

Three corrections are binding from the outset:

1. **Timestamp truth:** a feature known at the close cannot buy that same close unless it was
   frozen before the closing auction. Wave 1 therefore uses signals frozen after session `T-1`
   and entries at session `T` open. Same-day near-limit confirmation is a separate intraday-data
   construction, not smuggled into the daily-bar test.
2. **T+1 truth:** stock bought on `T` cannot be sold until `T+1`. A next-open rider bought on
   `T+1` cannot be sold until `T+2`. Every return ruler and state-machine exit starts no earlier.
3. **Fill truth:** a daily close labelled `sealed_up` says nothing by itself about whether the
   next opening auction is fillable. The entry session's open relative to that session's limit,
   plus a conservative queue rule, decides eligibility. A locked limit-down exit carries forward;
   it is never priced at a fictional close.

There is also a current rule-era defect in `engine/china_microstructure.py`. Both exchanges moved
main-board risk-warning stocks from a 5% band to a 10% band effective **2026-07-06**, while the
engine still returns 5% for every main-board ST date. The SSE states the change and effective date
directly in its [2026 rule release](https://star.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml),
and the current SZSE rule sets main-board stocks to 10% in
[rule 3.3.13](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf).
Wave 1 must era-stamp and heal this before treating post-2026-07-06 ST rows as events.

The current store audit found two wider data defects that also precede strategy measurement:

- the historical event tape's visible 34-name gap is only a symptom. The original backfill scanned
  1,587 raw files; the current store has 1,842. Of the 255 later additions, 241 have pre-July events
  missing from the tape—11,042 recomputable rows—and 204 of those names have no stored event at
  all, so a “late first event” audit cannot see them;
- `china_zt_pool` contains weekend rows stamped with the requested Saturday/Sunday date even when
  the vendor returned Friday's pool. Day-of-week and weekend-fermentation tests are forbidden until
  session identity is validated and those clones are quarantined.

## 1. The construction space

### 1.1 Outcomes are a family, not one label

| Family | Constructions | Why they differ |
|---|---|---|
| First-board onset | limit close on `T`; first limit close within `T..T+2`; band-normalized max return; ordinary 6%/8% rerating day without a board | The operator's thesis is rerating windows, not a rigid 10%-every-day label. |
| Board continuation | next limit close; any additional board within 2/3 sessions; maximum board streak; boards remaining before first failure | A next-day miss may still be a continuing repricing path. |
| Capturable return | `T+1` open, `T+1` close, `T+2` open, state-machine exit, 3/5/10-session net return | Event probability and tradable expectancy are different products. |
| Adverse path | first tradable exit, maximum drawdown, locked-down carry days, gap-down probability | T+1 and limit-down mechanics make tail shape more important than mean return. |
| Relative outcome | stock return minus board/sector/index return | Separates a market-wide board festival from name selection. |

Wave 1 measures both event and return rulers. No event lift may be described as alpha without the
corresponding fillable return ruler.

### 1.2 Entry clocks

| ID | Clock | Observable information | Fill rule | Status |
|---|---|---|---|---|
| `O-OPEN` | onset signal after `T-1` close, buy `T` opening auction | all features through `T-1` | exclude an open at/within the tolerant cushion of `T` upper limit | Wave-1 primary |
| `O-PRECLOSE` | signal frozen before `T-1` closing auction, buy `T-1` close | only data available before 14:57 | requires intraday/frozen pre-close snapshot | untested data gap |
| `O-NEAR` | buy late on `T` after 95%-of-band approach but before seal | same-day path, first-touch time, queue state | actual timestamp and executable quote required | untested data gap |
| `C-AUCTION` | after a board on `T`, submit a `T+1` opening-auction order | board count and features known by `T` close; **not** the realised `T+1` gap | exclude opening-limit queues; sell no earlier than `T+2` | Wave-1 daily-data primary |
| `C-POSTGAP` | observe the 09:25 auction result, then buy from 09:30 | board count, prior features, realised `T+1` auction gap | first trade / first-5-minute VWAP and actual queue state | untested until intraday collector |
| `C-BREAK` | buy a seal break/reseal on `T+1` | intraday break time, queue depletion, reseal | actual intraday print required | untested data gap |
| `C-PREBOARD` | already owned before board `T`, continue holding | onset model caused the ownership | no new fill; exit state machine only | Wave-1 portfolio bridge |

### 1.3 Mechanism families and plausible constructions

#### A. News / fundamental rerating

- Pre-event accumulation: volume shock, positive gap, run-up acceleration, rising dollar volume,
  close-location, volatility contraction then expansion.
- Base maturity: washout lifecycle, distance from 52-week low/high, reversal membership, runway.
- News magnitude: announcement class, filing surprise, policy beneficiary, analyst revision.
- Uncapped oracle: same-company A/H/N-share or same-sector HK/US move available before the next
  onshore open; boards remaining estimated from the uncapped repricing gap.
- Falsifier construction: large-investor/hot-money buying on the board day may predict a next-day
  unload and longer reversal rather than remaining fair-value distance.

#### B. Theme cascade / relay

- Same THS concept leader count, leader board number, follower rank, breadth acceleration.
- Leader/follower distance: whether the candidate is an early high-quality follower or a late,
  low-quality residual.
- Quality-gradient clock: later relay names degrade in liquidity, base maturity, profitability,
  or institutional participation.
- Theme concentration versus multi-theme breadth; one dominant theme may be powerful early and
  fragile late.
- Leader failure shock: after the highest-board name fails, next-session continuation across its
  concept and the whole ladder.

#### C. Reflexive board ecology

- Level: first-board count, continuation rate, active ceiling, limit-up/down breadth.
- Acceleration: 3/5-session change in those quantities, not only their level.
- Dispersion: sector concentration, share of first boards versus late boards, width mix.
- Failure pressure: failed-seal share, near-limit failures, limit-down encroachment.
- State constructions: continuous probability offset; hot/neutral/cold bins; transition shock;
  leader-failure veto; exposure scaler.
- All ecology inputs for a `T` open decision are lagged through `T-1`.

#### D. Seal, auction, and participant composition

- `T+1` open-gap percentile, band-normalized and board-specific. It is known after the 09:25
  auction print and may update a 09:30 decision; it cannot filter an order and also claim the
  already-realised official-open fill.
- Seal wall normalized by turnover, free float, market value, or board-day traded value.
- Failed seals, first-touch time, cumulative sealed minutes, final seal time.
- Opening-auction matched volume and unmatched order imbalance.
- Raw hot-money LHB versus institutional-seat net buying; participant divergence is likely more
  useful than either level alone.
- Short-sale eligibility / securities-lending availability as a price-discovery conditioner.

Primary research makes the participant split non-cosmetic. Account-level SZSE evidence finds that
large investors tend to buy on an upper-limit day, sell the next day, and that their board-day net
buying predicts stronger long-run reversal
([NBER Working Paper 24014](https://www.nber.org/papers/w24014)). Existing `china_lhb` history is
therefore a feasible terminal-board filter, not merely a generic positive confirmer.

#### E. Crowd clock

- Monday through Friday separately; Friday-to-Monday fermentation versus ordinary overnight.
- Holiday gap length, not a weekend binary only.
- First board versus later board interaction with the gap length.
- Overnight gap confirmation versus exhaustion: moderate gap, extreme gap, and gap-down are
  separate shapes; a monotone assumption is forbidden until measured.
- Attention acceleration from THS rankings, news counts, search interest, or forum traffic.

#### F. Down-limit mirror

- Continuation / avoidance: sell or refuse entry after a first down-limit when an exit is
  executable.
- Release reversal: buy only after the first non-locked opening following a down-limit chain.
- Capitulation state: down-limit breadth spike plus improving failed-down-seal rate.
- Asymmetry by shortability, market regime, board width, and prior up-board history.
- Delisted-name absence makes every historical long result an upper bound; this family cannot be
  promoted on the current survivorship store.

### 1.4 Exit clocks

Wave 1 compares, rather than silently chooses among:

1. earliest legal next-session open;
2. earliest legal next-session close;
3. hold while each close remains sealed, exit next open after first unsealed close;
4. 2/3/5-session time stop;
5. trailing stop evaluated at a later open only;
6. locked-down carry: defer exit until the first opening auction below the down limit.

Every exit reports both gross and 0/30/60/100 bp round-trip friction scenarios. The state-machine
construction is conservative with daily bars: it never claims an intraday sale at an unknowable
seal break.

### 1.5 Model shapes

- Board/era base-rate ladder only.
- Single-feature bucket rules using the six v0 stable-sign inputs.
- Fixed regularized logistic combination of those six inputs.
- Monotone additive bucket score, which can preserve nonlinear tails without a feature search.
- Separate onset and continuation models; a shared model is an explicit alternative, not the
  default.
- Probability offset from lagged regime ecology.
- Interactions frozen before measurement: board count × auction gap, first-board count × rolling
  continuation, seal wall × failed seals, and hot-money × institutional-seat divergence.
- Tree/boosting models are held for a later nested-validation construction; Wave 1 will not turn
  the holdout into a feature audition.

## 2. Wave-1 frozen shortlist

Wave 1 tests four linked packets. The date boundaries may move only if a required field has no
coverage in a named block; any movement is printed as a deviation.

### Packet A — `O-OPEN` first-board onset

- Universe: main board primary; post-2020-08-24 ChiNext secondary; STAR descriptive; BSE/ST only
  after their rule and membership histories are honest.
- Population: every usable non-board name-day. Outcome is a first tolerant limit-up close on the
  next session; strict definition rides beside it.
- Inputs frozen: five name-local v0 axes (`vol_z20`, `runup_5`, `gap_pct`, `dist_52w_low`,
  `consec_up_days`). Current broad-sector membership applied backward is not point-in-time;
  `sector_heat` is therefore a separate construction. A lagged ecology offset is also evaluated
  separately, not folded into the base model post hoc.
- Trade clock: score after `T-1`; buy `T` open if auction-fillable; earliest exit `T+1`.
- Comparators: board/era unconditional base, each feature alone, fixed equal-rank blend, fixed-L2
  logistic blend.
- Metrics: Brier, log loss, calibration slope/intercept, ECE, top-K precision/lift, coverage,
  event rate, net return, drawdown, and locked-exit count.

### Packet B — continuation rider

- Population: tolerant first and second boards, separately by board/era.
- Daily-data entry (`C-AUCTION`): place the order from `T`-close information and model an official
  next-open fill only when the realised auction was below the new upper-limit queue threshold.
  The realised opening gap is an execution outcome here, not a selection feature.
- Post-auction construction (`C-POSTGAP`): the band-normalized opening gap updates the probability
  at 09:25, but any claimed fill must use a 09:30 first trade or first-5-minute VWAP. Until that
  collector exists, Wave 1 may measure the gap-conditioned event probability but may not report a
  fill-honest strategy return for it.
- Pre-auction features: board count, prior five name-local inputs, board-day geometry,
  weekday/holiday gap, lagged ecology, and point-in-time seal/LHB fields where covered. The
  zt_pool and LHB fields are separate short-history strata, never backfilled with zero.
- Outcomes: next close board; any board in two sessions; `T+2` open/close return; state-machine net
  return; adverse excursion and locked-down carry.
- Shapes frozen: raw ladder; pre-auction ladder × ecology; Friday interaction; LHB
  hot-money/institution divergence where point-in-time coverage exists; and **probability-only**
  post-auction gap deciles / ladder × gap until executable intraday prices exist.
- The older unconditional fill-realistic null is the baseline to beat, not an inconvenient result
  to omit.

### Packet C — lagged board-ecology regime

- Inputs: first-board count, active ceiling, trailing realised first-to-second continuation,
  limit-up/down breadth, failed-seal share, and sector concentration. Every rolling field is
  shifted one session.
- Constructions: continuous probability offset; fit-window terciles; 3-session acceleration;
  leader-failure shock.
- Test: incremental calibration and net-return improvement over Packets A/B without the ecology
  terms. Any exposure scaler remains paper/display tier.

### Packet D — data and ledger integrity

- Era-aware main-board ST width: 5% before 2026-07-06, 10% on/after that date.
- Full backfill must state files discovered, files read, earliest/latest session, missing/error
  counts, and whether every row marked `backfill=True` actually has the claimed history.
- `fires.jsonl.fillable` remains a fire-time field; it may not be reused as a next-auction fill.
- Forward candidate rows carry `signal_date`, `decision_available_at`, `entry_session`,
  `entry_rule`, `probability`, `model_version`, `era`, `board`, `universe_id`, `limit_definition`,
  `fillable_state`, and immutable input hashes.
- Nightly is the sole ledger advancer. Re-running one stamp date is idempotent and may not mutate
  an entry price or probability already published.
- Every emitted probability is graded, including candidates that later become inconvenient.

## 3. Frozen time design and honesty labels

- Main-board long-history packets: fit 2011-2019; calibration/design check 2020-2023; locked replay
  evaluation 2024-01-02 through 2026-06-12; vendor-rich audit 2026-06-15 through 2026-08-07.
  Purge ten sessions at boundaries. The prospective ledger begins with the 2026-08-10 decision
  cycle.
- The replay block is **not virgin holdout**: the common-prior v0 receipt already exposed the six
  inputs' signs through 2026-08-07. It is labelled `historical_replay_after_common_prior`, never
  `unseen_test`.
- ChiNext uses only its 20% era for magnitude comparisons, with an independent split inside that
  era.
- zt_pool, LHB, and other short tapes use their actual point-in-time windows and print thin cells;
  absence before collection began is null, not zero.
- The only clean confirmation of current calibration is the prospective nightly ledger. Ten
  graded sessions are required before even considering the promotion gauntlet.

Date-block bootstrap and by-name summaries accompany pooled rows. Multiple constructions are
expected in exploration. Promotion, if ever proposed, gets a separately frozen family-wise test;
Wave 1 itself does not spend that authority budget.

## 4. Ore ledger — untested variants at Wave-1 start

The following remain open even if every Wave-1 packet is null:

- pre-close and intraday near-limit onset entries;
- post-auction gap-rider returns using a real 09:30/first-5-minute execution price;
- first-touch time, cumulative seal duration, queue depth, closing-auction imbalance, and actual
  order priority;
- full-market small-cap/ST/BSE universe and delisted names;
- historically correct ST membership before the current store;
- free-float-normalized turnover and seal wall;
- true participant-size flow outside the LHB subset;
- THS concept membership as it existed on each historical date;
- news-class and fair-value-distance models;
- A/H/N same-company and sector-level uncapped rerating oracles;
- seal-break/reseal entries;
- limit-down release reversals with delisting-complete data;
- tree/boosting and survival/hazard models under nested validation;
- live slippage, queue rejection, partial fills, commissions, stamp duty, and capacity outside the
  stated friction grid;
- cross-name portfolio dependence, theme caps, fractional Kelly, and book-level drawdown controls
  beyond the first equal-weight paper construction.

The first paper book keeps cash for rejected/ambiguous fills, prevents duplicate ticker exposure,
and transitions an owned onset position into the continuation sleeve without a second fictional
fill. Its expectancy is computed as `P(fill) * E(net return | fill)`, with success and failure arms
shown separately. It must never be described as delta-neutral: limit events cluster by date and
theme, so a many-name book can still be one crowded factor bet.

No future receipt may shorten this list merely because one adjacent construction failed.

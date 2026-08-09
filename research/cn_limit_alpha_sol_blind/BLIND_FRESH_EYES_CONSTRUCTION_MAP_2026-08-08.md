# A-share price-band alpha: blinded fresh-eyes construction map

**Date:** 2026-08-08

**Status:** independent ore map; no measurement, backtest, outcome verdict, profit claim, or authority promotion

**Intended next use:** reconcile by construction key with a separately produced research map, then pre-register narrow measurement cells

## 0. Blind information set and independence statement

This document was constructed from a deliberately restricted information set.

### Information available to this author

1. The operator charter and common prior reproduced in the commissioning prompt:
   - daily price bands, T+1, forced-spectator/crowd mechanics, multi-session repricing, flexible 6%/8%/board paths, portfolio probability, and fillability are the target mechanism space;
   - the supplied v0 conditional next-board frequencies by lianban count, the supplied unconditional next-board frequency, and the six supplied sign-stable axes;
   - the supplied warning that previous-day near-limit was unstable, that turnover could not be tested because shares were absent, and that a tolerant 0.2%-from-band event definition agreed closely with the vendor pool;
   - the supplied 300363 washout/reversal example and its unfillable +20% board day;
   - the supplied near-null result for one old generic dip-plus-limit-up continuation baseline, explicitly bounded to that construction;
   - the supplied inventory and coverage facts, including the short vendor-pool history and the 514/1,770 local-overlap limitation;
   - the supplied execution laws.
2. The worktree's full `CLAUDE.md`.
3. Ordinary repository machinery and schemas, limited to:
   - `engine/china_microstructure.py` and `scripts/backfill_china_limit_tape.py`;
   - `collectors/china_zt_pool.py`, `collectors/china_lhb.py`, and `collectors/china_block_tape.py`;
   - the China Pick Lab fire/snapshot schema code;
   - column schemas, but not row values or outcomes, for the local daily OHLCV, limit-event/tape, zt-pool, LHB, THS-membership, ST-history, and breadth stores.
4. Current primary public exchange rules from SSE, SZSE, and BSE, used only to define legal market mechanics and regime clocks.

### Information deliberately unavailable and not inspected

- `research/CN_LIMIT_ALPHA_FABLE_HANDOFF_2026-08-08.md`;
- every artifact under `research/cn_limit_alpha_sol/`;
- every `claude/cn-limit-w1-*` branch, ref, or worktree;
- active SOL worktrees or their results;
- handoff sections 3-4 from any source;
- sibling-agent ideas, measurements, or interim reports.

No backtest, descriptive outcome calculation, row-value inspection, or case search was run for this task. No memory material was consulted. The rankings below are design-priority judgments only; they are not empirical rankings.

## 1. Binding ore law

Every item below is **ore**, not a finding. The following rules bind later work:

1. **Construction before verdict.** A topic is a space of event definitions, clocks, entries, outcomes, regimes, and portfolios—not one regression.
2. **Exact closure only.** A null closes only the exact frozen tuple that was measured. It cannot close “washouts,” “failed boards,” “crowding,” or another broad topic.
3. **Three boundaries on every family.** Each family states what the common prior measured, what remains untested, and what exact evidence would close a cell.
4. **Probability and execution are different objects.** `P(path | signal)` and `P(fill | order, path)` get different labels, models, diagnostics, and collectors.
5. **Nonfills remain cash.** A candidate that cannot be bought contributes zero to strategy expectancy. It is never silently removed from the denominator.
6. **Exact sessions are sacred.** Missing, halted, or locked successor sessions do not jump to resumption. They receive explicit competing-risk states.
7. **Exploration is not promotion.** Data accrual, detectors, receipts, and research views may remain exploration/display tier. Nothing here proposes ranking, sizing, gating, Neural Web authority, or Prophet authority.
8. **Nulls stay visible.** A standalone null may remain a confluence input; it does not become evidence of absence.
9. **The `UNTESTED VARIANTS` ledger is mandatory** and appears in Section 12.

## 2. Canonical construction key

A result is interpretable only if it names the full construction:

```text
K = U × R × E × D × X × O × F × Y × H × P × C

U  universe and security eligibility
R  rule/market/sector/crowd regime
E  event or onset definition
D  feature-freeze and decision timestamp
X  feature transform and comparator
O  order protocol
F  fill rule and nonfill treatment
Y  outcome/path label
H  exit/liquidation horizon
P  portfolio assembly and dependence treatment
C  costs, caps, and missing-data policy
```

Two studies that differ anywhere in `K` are different constructions. Reconciliation with another team should happen at this key level, not by comparing family names.

### Priority scales

**Expected discriminative value (EDV)** is the expected ability to distinguish competing mechanisms, not expected return:

- **D3:** likely to separate mechanism alternatives or expose a major execution/data confound.
- **D2:** useful conditional discriminator after a D3 spine exists.
- **D1:** exploratory or heavily confounded; collect cheaply but do not lead with it.

**Data feasibility:**

- **A:** testable now with local daily data after rule/security-master audit.
- **B:** partially testable now; short history, overlap, or PIT weakness prevents a broad verdict.
- **C:** needs minute bars, auction data, exact publication clocks, or a new PIT reference collector.
- **D:** needs order-book/queue events or broker execution telemetry.

## 3. First-principles mechanism map

The daily band is not merely a return threshold. It can censor price discovery and convert a one-session information shock into a state machine:

```text
information / attention / inventory shock
                   |
          unconstrained desired price
                   |
       price band truncates visible move
                   |
     queue + no-trade spectators + T+1 vintages
          /             |                 \
 next-session seal   partial rerating   failed seal / reversal
          |             |                 |
    crowd ladder     6%/8% staircase   inventory transfer
          \             |                 /
       sector diffusion, rotation, or exhaustion
```

The map therefore needs three linked but separately measured planes:

1. **Latent repricing:** how much directional demand or supply remains after the visible close.
2. **Market access:** whether an executable order could participate in that latent repricing.
3. **Crowd redistribution:** where capital goes when the focal name is unfillable or unattractive.

Second- and third-order effects live mainly in plane 3. A locked leader can affect followers even when the leader itself is not a possible holding; a failed leader can release attention and capital into substitutes; a wider-band leader can absorb more of a theme's demand before creating spectator spillover; and T+1 creates distinct inventory vintages whose first legal sell session may shape the unlock path.

## 4. Construction-space overview

| ID | Family | Core question | EDV | Feasibility |
|---|---|---|---:|---:|
| O1 | Compression-reversal ignition | Does path compression plus reclaim identify delayed onset beyond distance-from-low? | D3 | A/B |
| O2 | Partial-band rerating staircase | Do 6%/8% and band-normalized steps carry information that sealed-board labels discard? | D3 | A |
| O3 | Overnight/auction assimilation | Does pre-open imbalance resolve or extend a prior close's latent repricing? | D3 | C |
| O4 | Spectator-halo onset | Does an unfillable leader redirect demand into eligible followers? | D3 | B/C/D |
| C1 | Seal morphology and queue durability | Which apparent boards represent durable demand rather than a closing snapshot? | D3 | B/C/D |
| C2 | Ladder topology and survivor age | Is continuation driven by focal streak length or by the whole ladder's shape? | D3 | A/B |
| C3 | Cadenced continuation | Are board-pause-board and partial-step sequences distinct from consecutive boards? | D3 | A |
| C4 | T+1 inventory-vintage stack | Does first legal sell eligibility create predictable unlock states? | D3 | C/D |
| D1 | Failed-up absorption vs distribution | Which failed seals transfer inventory constructively and which exhaust demand? | D3 | A/C |
| D2 | Limit-down supply deferral and release | Does a locked sell queue stretch downside or create a first-unlock reversal window? | D3 | A/C/D |
| D3 | Two-sided band traversal | Does touching both tails reveal forced transfer rather than generic volatility? | D2 | A/C |
| D4 | Failed-leader redistribution | After a board fails, does theme capital rotate to followers, leave the theme, or reverse? | D3 | B/C |
| R1 | Crowd-temperature nonlinearity | Are continuation mechanics strongest in a warm middle and weaker in cold/euphoric states? | D3 | A/B |
| R2 | Sector diffusion/entropy clock | Is theme age better described by concentration and graph spread than raw sector heat? | D3 | B/C |
| R3 | Width/lifecycle/rule cohorts | Do 10%, 20%, 30%, IPO, risk-warning, and rule-change regimes require separate models? | D3 | A/C |
| R4 | LHB/block sponsorship and attention | Does pre-existing sponsorship differ from post-event publicity? | D2 | B/C |
| R5 | Float and supply elasticity | Does queue/volume pressure matter only after normalization by tradable supply? | D3 | C |
| R6 | Coverage and observability selection | Are local conclusions conditional on being in the 29.04% overlap slice? | D3 | A/C |

## 5. Detailed family cards

### O1. Compression-reversal ignition

**Ore thesis.** A board can be the visible end of an onset process that began with forced selling, range compression, and a reclaim. The discriminating information may be path shape rather than simply being near a 52-week low.

**Construction cells.** Independently freeze cells over:

- antecedent window `{5, 10, 20, 40}` exact trading sessions;
- prior drawdown or distance-from-low quantiles computed from past-only cross-sections;
- compression measures: declining true range, declining volume, inside-day count, downside-gap count;
- ignition shape: close-location value, lower-wick reclaim, gap reclaim, range expansion, positive close without a board, or sealed board;
- market/sector state from R1/R2;
- paths `non-board ignition → +6%/+8%`, `failed-up → reseal`, and `washout → board` as separate cells.

**Decision/order/outcome.** Freeze after session D; enter only by a named D+1 protocol. Primary outcomes are next-session seal probability and 3/5-session first passage to `+6%`, `+8%`, or `0.8 × limit_width` before a frozen adverse barrier.

**Measured boundary.** The common prior covers distance from the 52-week low and one named case; it also reports a near-null old generic dip-plus-limit-up baseline. It does not measure compression, reclaim morphology, non-board ignition, regime interaction, or the fill-aware cells above.

**Untested boundary.** Every path-shape, window, comparator, and entry cell above remains untested here.

**Exact falsifier.** Close only one frozen O1 cell if, on locked holdout data and versus a nested baseline containing the six common-prior axes, the upper 95% confidence bound for both proper-score improvement on its primary probability label and fill-aware return-path improvement is `<= 0` in both temporal halves. Other O1 cells remain open.

**Priority:** D3; A for daily morphology, C for intraday washout/reclaim order.

### O2. Partial-band rerating staircase

**Ore thesis.** The market may reveal delayed repricing through a staircase of large but non-board moves. Absolute 6%/8% moves and progress as a fraction of the applicable band can carry different information.

**Construction cells.** Define `band_progress_D = (close_D / close_D-1 - 1) / limit_width_D` and keep separate:

- absolute close-return buckets around `+4%`, `+6%`, `+8%`;
- band-progress buckets `{0.4-0.6, 0.6-0.8, 0.8-<1.0, sealed}`;
- one-step, two-step, and three-step paths such as `6→6`, `8→flat→board`, `board→6`, and `6→failed-board`;
- high-close-location versus long-upper-wick versions;
- raw and sector-relative returns;
- 10% and 20% boards as separate cohorts before any pooled model.

**Decision/order/outcome.** D-close freeze; D+1 executable open or post-close fixed-price entry as separate modes. Outcomes are flexible first-passage trajectories, not only “next board.”

**Measured boundary.** The common prior covers 5-day run-up, prior gap, consecutive-up days, and an unstable near-limit-previous-day feature. It does not cover band-normalized progress, multi-step path grammar, or flexible first passage.

**Untested boundary.** All staircase sequences, barriers, width interactions, and order modes are untested.

**Exact falsifier.** Close a specific sequence grammar only if its locked-holdout transition distribution is indistinguishable from a duration-, board-, and regime-matched path baseline on both the primary first-passage label and fill-aware contribution, with both upper 95% bounds `<= 0`.

**Priority:** D3; A.

### O3. Overnight and opening-auction assimilation

**Ore thesis.** A prior close's latent repricing can be confirmed, exhausted, or reversed during the opening auction. The informative object may be imbalance persistence and its conversion into executable prints, not the opening gap alone.

**Construction cells.** Keep four legal clocks distinct:

1. **Pre-submitted auction order:** signal frozen at D close; D+1 auction order price cap uses D information only.
2. **Indicative-auction read:** imbalance frozen at a named D+1 timestamp; entry begins only in continuous trading after the auction.
3. **First-5-minute confirmation:** freeze the first five complete minutes; order begins on the next minute.
4. **Auction fade:** indicative gap/imbalance is large but first continuous prints reject it.

Features requiring collection include indicative price path, matched/unmatched volume, cancellations before the non-cancel interval, final auction fill, first-print delay, and first-five-minute absorption.

**Measured boundary.** The common prior reports prior gap as sign-stable. It does not measure auction imbalance, cancellations, matched volume, or gap conversion.

**Untested boundary.** All auction clocks and fill protocols are untested.

**Exact falsifier.** Close one timestamp/order cell if its locked-holdout auction features add no proper-score improvement over the prior-gap baseline and its executable fill model adds no calibration improvement, with upper 95% bounds `<= 0` in both halves.

**Priority:** D3; C, with D for true queue rank.

### O4. Spectator-halo onset

**Ore thesis.** When a theme leader is locked and unfillable, would-be demand may move into tradable peers. The leader is then a context event, not a holding candidate.

**Construction cells.** On D, identify a focal leader and past-only concept membership. On D+1, compare:

- direct peers versus sector-matched non-peers;
- one-hop versus multi-concept bridge names;
- peers already at `+4%/+6%/+8%` versus quiet peers;
- exclusive members versus names belonging to many hot concepts;
- 10% versus 20% leader locks;
- low versus high leader queue pressure;
- single locked leader versus multiple locked leaders in the same concept.

The third-order variant is `leader lock × concept exclusivity × follower tradability`: congestion may spill into the nearest eligible substitute, but diffuse membership may dissipate it.

**Decision/order/outcome.** Leader state and membership freeze at D close; follower order uses D+1 named protocol. The leader's nonfill remains zero and is not counted as a missed hypothetical trade. Follower outcomes include 6%/8%/board paths and downside.

**Measured boundary.** Sector limit heat is in the common prior, and one unfillable case is supplied. Neither establishes substitution, graph distance, width interaction, or follower fillability.

**Untested boundary.** The entire spectator-spillover mechanism remains untested.

**Exact falsifier.** Close one leader/follower graph cell if matched followers show no incremental path discrimination versus matched non-followers and the interaction with leader unfillability has an upper 95% bound `<= 0` in both temporal halves. This does not close other graph radii, widths, or clocks.

**Priority:** D3; B with current short vendor/PIT membership history, C/D for queue-conditioned variants.

### C1. Seal morphology and queue durability

**Ore thesis.** “Closed at the band” collapses materially different intraday histories: one-price lock, early seal with repeated breaks, late seal, failed seal then reseal, and closing-auction paint.

**Construction cells.** Separate:

- first-seal time and last-seal time;
- number and duration of open-board intervals;
- sealed-volume fraction and time-at-limit fraction;
- queue size normalized by free-float value and median minute volume;
- queue additions, cancellations, and executions;
- pre-close continuous seal versus closing-auction-only seal;
- vendor `failed_seals`, `seal_fund`, and turnover as short-history daily proxies only.

**Decision/order/outcome.** Features must exist before the chosen decision. A closing seal can inform only post-close or D+1 orders. Intraday “first seal” cells enter only after an actual reopen and executable quote; a queue is never a fill.

**Measured boundary.** The common prior supplies conditional continuation by lianban count and notes available vendor seal/failure fields. It supplies no seal-morphology verdict.

**Untested boundary.** All timing, duration, queue-normalized, and closing-auction variants are untested.

**Exact falsifier.** Close a morphology cell only if it fails to improve both next-session state prediction and order-specific fill calibration over `lianban_count + six axes` on locked holdout, with both upper 95% bounds `<= 0` in both halves.

**Priority:** D3; B for current vendor proxies, C for minute timing, D for queue events.

### C2. Ladder topology and survivor age

**Ore thesis.** A focal name's streak may be less informative than the entire market/sector ladder: counts at each board age, breadth below the leader, gaps in the ladder, and concentration in one theme.

**Construction cells.** Build a D-close ladder vector:

```text
L_D = [n_1board, n_2board, ..., n_6plus,
       max_age, second_max_age, age_entropy,
       same_sector_share, follower_depth, gap_count]
```

Keep separate:

- leader continuation versus follower catch-up;
- smooth pyramids versus top-heavy ladders;
- single-theme versus multi-theme ladders;
- newborn ladders versus aging ladders;
- market ladder versus sector-local ladder.

**Decision/order/outcome.** D-close ladder; D+1 order. Primary labels are focal next-session state and portfolio count of eligible successes, with cluster dependence retained.

**Measured boundary.** The supplied prior measures focal next-board probability by lianban N. It does not measure ladder shape, entropy, gaps, theme concentration, or follower depth.

**Untested boundary.** All topology interactions remain untested.

**Exact falsifier.** Close one topology transform if it adds no held-out proper-score improvement to focal streak length and no calibration improvement for cohort success counts, with upper 95% bounds `<= 0` in both halves.

**Priority:** D3; A for locally reconstructed ladders, B for vendor-complete ladders.

### C3. Cadenced continuation

**Ore thesis.** Delayed repricing need not be consecutive sealed boards. A pause, partial step, failed attempt, or controlled pullback may reset accessible supply without ending the path.

**Construction cells.** Enumerate immutable path words over the alphabet:

```text
B = sealed board
F = failed-up seal
P = +4% to <band
N = -2% to +2% pause
R = controlled retrace
D = sealed/failed down state
```

Candidate words include `B-N-B`, `B-R-B`, `P-P-B`, `B-P-P`, `F-N-B`, and `B-F-P`. Window length `{2,3,5}` and width cohort are part of the key. Do not merge words after seeing outcomes.

**Decision/order/outcome.** Freeze only complete words at D close; enter D+1. Compare against duration- and cumulative-return-matched nonword paths. Outcomes are next state and 3/5-session first passage.

**Measured boundary.** Consecutive-up days and lianban count are in the common prior. Nonconsecutive cadence grammars are not.

**Untested boundary.** Every word, width, and comparator remains untested.

**Exact falsifier.** Each path word closes independently if it adds no held-out state or first-passage discrimination over matched cumulative return, volatility, streak, and regime baselines in both halves.

**Priority:** D3; A.

### C4. T+1 inventory-vintage stack

**Ore thesis.** T+1 creates dated inventory cohorts. Buyers on an ignition or reopen day cannot sell until the next exact session; a multi-day path accumulates cohorts with different cost bases, and the first-unlock session can change available supply.

**Construction cells.** Approximate or collect:

- ignition-day traded volume and volume-at-price distribution;
- next-session fraction of prior volume that is in profit at the open;
- cohort cost stack across `{1,2,3,5}` sessions;
- first unlocked cohort after a one-price lock;
- unlock into gap-up, flat, or gap-down auction states;
- interaction with free float, queue congestion, and LHB/block sponsorship.

Daily OHLCV can create crude turnover-free volume vintages but cannot identify holder identity or executable supply. Minute volume-at-price improves the proxy; account/order data would be the strongest version.

**Decision/order/outcome.** D+1 state must use only cohorts legally sellable then. Exact-session lock or halt is an outcome, not a skipped date.

**Measured boundary.** T+1 is a supplied execution law. No inventory-vintage result is supplied.

**Untested boundary.** Every cohort-cost and unlock interaction is untested.

**Exact falsifier.** Close one vintage proxy if it adds no held-out prediction of first-unlock state or sell-side executable volume beyond gap, volume-z, streak, and regime, with upper 95% bounds `<= 0` in both halves. Better vintage data remain a separate construction.

**Priority:** D3; C, D for holder/queue-realistic versions.

### D1. Failed-up seal: absorption versus distribution

**Ore thesis.** A failed seal can mean either supply was absorbed while price discovery remained constructive, or demand exhausted and late buyers became trapped. Daily `high at band, close below` mixes the two.

**Construction cells.** Daily cells:

- close distance from band;
- close-location value and upper-wick fraction;
- volume-z and gap;
- prior ladder age and sector heat;
- next exact session tradability.

Intraday cells:

- early break then reseal versus late break without recovery;
- cumulative volume before/after first break;
- number/duration of breaks;
- VWAP reclaim after break;
- closing-auction behavior;
- queue depletion versus cancellation.

**Decision/order/outcome.** D-close daily cells enter D+1. Intraday cells enter only after a named post-break confirmation minute. Labels include next-session seal, +6%/+8% first passage, negative first passage, and fill.

**Measured boundary.** Failed seals exist in local/vendor machinery, but the common prior supplies no failed-seal outcome verdict.

**Untested boundary.** All daily bifurcation and intraday absorption cells are untested.

**Exact falsifier.** Close only the exact morphology/clock cell if it cannot discriminate the preregistered positive versus negative first-passage outcome beyond the common-prior axes and adds no fill-aware improvement on both halves.

**Priority:** D3; A for coarse daily split, C/D for the intended mechanism.

### D2. Limit-down supply deferral and release

**Ore thesis.** A sealed lower band censors sellers just as an upper band censors buyers. Deferred supply may extend downside, while a failed-down seal or first executable unlock may reveal capitulation and inventory transfer.

**Construction cells.** Keep separate:

- first sealed-down day versus consecutive lower boards;
- sealed-down versus touched/failed-down;
- open-at-lower-limit versus intraday descent;
- first unlock gap and first-five-minute reclaim;
- market-wide lower-band cluster versus idiosyncratic event;
- follower damage after a theme leader locks down;
- avoidance/risk-filter use versus positive reversal entry.

**Decision/order/outcome.** No purchase at a locked lower limit is assumed merely because the quote exists. D+1 open and first-unlock minute are different entries. A planned sale that meets a sealed-down queue is an unexecuted exit and must remain so.

**Measured boundary.** Local limit-event machinery supplies sealed/failed-down labels; no outcome result is supplied.

**Untested boundary.** All downside continuation, release, and reversal cells remain untested.

**Exact falsifier.** Close one lower-band state/entry cell if its exact-session competing-risk distribution and executable path do not differ from matched high-volatility non-limit declines on both halves, with upper 95% bounds `<= 0` for the preregistered direction.

**Priority:** D3; A for state paths, C/D for first unlock and sell-queue execution.

### D3. Two-sided band traversal

**Ore thesis.** A name that touches both upper and lower constraint regions in a short window may represent forced inventory transfer and disagreement rather than generic volatility.

**Construction cells.** Distinguish:

- same-session upper and lower touch;
- upper touch D then lower touch D+1, and the reverse;
- failed-up followed by failed-down versus sealed transitions;
- path order, time between touches, and market cluster state;
- normalized range relative to the applicable band.

**Decision/order/outcome.** Daily event pairs are available for coarse ordering; same-day ordering needs minute data. The primary use may be exclusion/uncertainty calibration rather than long entry.

**Measured boundary.** None of the common-prior axes isolates two-sided traversal.

**Untested boundary.** Entire family untested.

**Exact falsifier.** Close one ordering/window cell if it adds no held-out calibration of subsequent path dispersion or direction beyond realized range, volume-z, gap, and regime in both halves.

**Priority:** D2; A for cross-day ordering, C for same-day ordering.

### D4. Failed-leader redistribution

**Ore thesis.** A leader's failed board may rotate theme capital into a tradable second leader, drain the theme entirely, or reverse the whole cohort. The cross-section, not the focal return, distinguishes these mechanisms.

**Construction cells.** On leader failure D, classify D+1 theme response:

- follower catch-up;
- new-leader replacement;
- theme-wide retreat;
- cross-theme rotation into the market's next-hot cluster;
- exclusive versus bridge-member recipient;
- high versus low prior spectator congestion.

**Decision/order/outcome.** Membership freezes at D. Orders target only D+1 eligible recipients. Primary labels are recipient path and portfolio theme outcome; the failed leader can be held out as context only.

**Measured boundary.** Sector heat is supplied as sign-stable, but no redistribution result is supplied.

**Untested boundary.** Entire redistribution graph remains untested.

**Exact falsifier.** Close one source/recipient graph rule if matched recipients show no incremental D+1-to-D+5 path discrimination over sector-relative momentum and market rotation controls in both halves.

**Priority:** D3; B with short PIT membership/vendor data, C with minute attention/flow clocks.

### R1. Crowd-temperature nonlinearity

**Ore thesis.** Continuation may be weakest in a cold market, strongest in a warm expanding crowd, and weaker again in euphoric congestion. A single linear “more heat is better” coefficient can hide this.

**Construction cells.** Build past-only market states from:

- sealed-up and failed-up breadth;
- seal rate;
- lower-limit breadth;
- ladder max and ladder entropy;
- sector concentration of boards;
- median gap/volume-z of event names;
- day-over-day acceleration and deceleration.

Test categorical state machines, splines, and hysteresis separately. A state entered by acceleration is not assumed equivalent to the same level entered by deceleration.

**Decision/order/outcome.** Crowd state freezes at D close and conditions, but does not replace, name-level features. Outcomes include probability, fillability, and cross-name dependence.

**Measured boundary.** Sector limit heat is supplied as sign-stable; no nonlinearity, hysteresis, or market-wide interaction is supplied.

**Untested boundary.** Every state boundary and interaction remains untested.

**Exact falsifier.** Close one frozen state partition if it adds no held-out proper-score or dependence-calibration improvement over continuous breadth/heat controls in both halves. Other partitions and hysteresis definitions remain open.

**Priority:** D3; A/B.

### R2. Sector diffusion and entropy clock

**Ore thesis.** Raw sector heat does not distinguish a one-name spike, orderly diffusion, broad saturation, or rotation. Theme age may be encoded by concentration and graph spread.

**Construction cells.** Freeze:

- board count and share of sector members;
- Herfindahl/concentration of event strength;
- membership-graph radius from the first leader;
- new-member arrival rate;
- leader turnover and age;
- cross-concept bridge count;
- acceleration, saturation, and decay states;
- raw sector taxonomy versus PIT THS concepts.

**Decision/order/outcome.** Membership and graph use only snapshots available by D. D+1 entry. Compare leader, follower, and bridge-name outcomes separately.

**Measured boundary.** Sector limit heat is in the common prior. Entropy, diffusion radius, bridge topology, and theme-age state are not.

**Untested boundary.** Entire diffusion clock remains untested.

**Exact falsifier.** Close one graph/taxonomy cell if it adds no held-out discrimination to raw sector heat for leader/follower outcomes in both halves. A null in THS does not close an industry taxonomy construction.

**Priority:** D3; B now, C for deep PIT membership.

### R3. Width, lifecycle, and rule cohorts

**Ore thesis.** A 6% move means something different under a 10%, 20%, or 30% band. IPO no-limit windows, risk-warning rules, post-close fixed-price trading, and board reforms create separate natural regimes.

**Construction cells.** At minimum stratify:

- main, ChiNext, STAR, and BSE;
- exact `limit_width` and `band_progress`;
- IPO/no-limit versus ordinary sessions;
- risk-warning status using PIT membership and an effective-dated rule table;
- pre/post board-rule changes;
- pre/post 2026-07-06 exchange-rule regime;
- auction-only, continuous, and post-close fixed-price execution modes.

**Verified prerequisite, not an alpha result.** Current official SSE and SZSE rules moved main-board risk-warning stocks from 5% to 10% effective 2026-07-06. The inspected local `engine/china_microstructure.py` still returns 5% for current main-board ST names and has only shallow historical ST membership. Therefore post-2026-07-06 risk-warning event rows must be quarantined until the detector and effective-dated security master are audited. The 2026 exchange revisions also expanded post-close fixed-price trading to all A-shares, creating a distinct execution regime whose volume/queue is not separated in ordinary daily OHLCV.

**Measured boundary.** The common prior supplies similar lianban behavior on main and ChiNext and board-aware event fields. It does not justify pooling widths/lifecycles or ignoring rule changes.

**Untested boundary.** All width-normalized interactions and new-rule execution cells are untested.

**Exact falsifier.** Close one pooled transform if board/rule-stratified holdout residuals show no heterogeneity and pooling improves proper score without calibration loss in both halves. This does not close board-specific constructions.

**Priority:** D3; A after rule repair, C for effective-dated masters and post-close tape.

### R4. LHB/block sponsorship and attention

**Ore thesis.** Pre-existing institutional or block-trade sponsorship may support a path, while post-event LHB appearance may simply amplify attention after the move. Event date and information-availability date must not be conflated.

**Construction cells.** Separate:

- block premium/discount and size known by D-1;
- institutional-seat net buy versus hot-money-only LHB appearances;
- first LHB appearance versus repeated appearance;
- LHB trigger reason;
- pre-onset sponsorship versus same-day/post-event publicity;
- sponsorship interaction with failed seal, first unlock, and spectator halo.

**Decision/order/outcome.** Require `event_time`, `published_at`, `collected_at`, and `usable_at`. If publication timing is absent, lag one full session. Never use a trailing-window aggregate as though every component was known at the historical event close.

**Measured boundary.** The common prior says LHB/block data exist. It supplies no forward result.

**Untested boundary.** Every causal clock and interaction remains untested.

**Exact falsifier.** Close one availability-safe sponsorship cell if it adds no held-out path or fill discrimination to price/volume/sector controls in both halves. A post-event attention null does not close pre-event sponsorship.

**Priority:** D2; B now for coarse lagged cells, C for exact publication clocks and identity history.

### R5. Float and supply elasticity

**Ore thesis.** Raw volume, turnover, and seal fund are incomplete without the tradable supply denominator. A queue of one unit can be huge or trivial depending on free float and normal executable depth.

**Construction cells.** Collect effective-dated:

- total shares, free-float shares, float market cap, restricted shares, and unlock schedule;
- queue value / free-float market cap;
- event volume / free-float shares;
- seal fund / median daily value traded;
- failed-seal volume / prior queue size;
- block volume / free float;
- ownership concentration where legally and reliably available.

Interact supply elasticity with width, ladder age, and T+1 inventory vintages.

**Measured boundary.** The common prior explicitly says turnover was null because shares were absent. That is a data-boundary result, not a turnover-family verdict.

**Untested boundary.** Every correctly normalized supply construction remains untested.

**Exact falsifier.** Close one denominator/transform cell if effective-dated float normalization adds no held-out probability, fill, or path calibration over raw volume/seal fund on both halves. Do not close alternative denominator vintages.

**Priority:** D3; C.

### R6. Coverage and observability selection

**Ore thesis.** Being in the local OHLCV slice may correlate with exchange, age, liquidity, distress, or data-vendor survivorship. Coverage is therefore a selection process to model, not a harmless missing row.

**Construction cells.** Build a security-session spine for the vendor universe and classify:

- observed raw OHLCV;
- vendor limit event but no local OHLCV;
- local OHLCV but absent vendor pool;
- suspended/halted/not-listed;
- board/security-master mismatch;
- corporate-action or limit-rule uncertainty.

Estimate coverage propensity from pre-event metadata only; report raw-slice, overlap-only, and weighted sensitivity panels separately. Weighting cannot repair totally unobserved outcome data, so full-universe collection remains primary.

**Measured boundary.** The supplied overlap is 514 of 1,770 vendor limit-up tickers, or 29.04%. No generalization beyond that observed slice is established.

**Untested boundary.** Selection mechanisms and full-universe replication are untested.

**Exact falsifier.** Coverage is not an alpha thesis to “kill.” Close only a proposed weighting model if it fails held-out calibration of observation status. Conclusions remain slice-conditional until outcomes are collected.

**Priority:** D3; A for observability audit, C for full-universe completion.

## 6. Outcome and trajectory lattice

One binary next-board label is too lossy. Future preregistration should select from this lattice without outcome-driven switching.

### State labels on the exact next session

- `sealed_up`, `touched_up_failed`, `open`, `failed_down`, `sealed_down`;
- `halted`, `missing_expected_session`, `not_listed`, `rule_unknown`;
- `upper_queue_no_fill`, `lower_queue_no_exit`, and `tradable_no_fill` where order data permit.

### Flexible upward path labels

For horizon `h ∈ {1,2,3,5,10}` exact trading sessions:

- first passage to cumulative `+6%`;
- first passage to cumulative `+8%`;
- first passage to `q × applicable_band`, `q ∈ {0.6, 0.8, 1.0}`;
- first sealed-board session;
- number of sealed and failed-board states;
- path word from C3;
- maximum favorable excursion and close-to-close terminal return.

### Competing downside labels

- first passage to frozen `-4%`, `-6%`, or `-q × band` barriers;
- first lower-band touch and first lower-band seal;
- exact-session gap-down and first-unlock failure;
- maximum adverse excursion;
- unresolved liquidation because the exit order could not trade.

### Barrier discipline

Every first-passage construction freezes:

1. the reference price;
2. upper and lower barriers;
3. intraday-high/low versus close-only observation;
4. tie-breaking if both barriers occur in one daily bar;
5. treatment of halts, missing bars, and locked exits.

Daily bars cannot order two barriers touched in the same session. Such rows become `path_order_unknown`, not guessed winners; minute data defines a different construction.

## 7. Regime and crowd clocks

Every name-level family should be crossed first with a small, preregistered regime set rather than an uncontrolled interaction farm.

| Clock | Past-only state examples | Why it may matter | Current feasibility |
|---|---|---|---|
| Rule clock | board width, IPO window, risk-warning rule, 2026-07-06 regime | Defines the band and legal execution set | A/C; effective-dated repair required |
| Market crowd clock | cold, warming, broad-hot, concentrated-euphoria, cooling | Continuation and correlation may be nonlinear | A/B |
| Ladder clock | birth, expansion, mature, broken | Separates a leader's age from the market's age structure | A/B |
| Sector diffusion clock | single-leader, follower expansion, saturation, rotation | Locates spectator spillover and exhaustion | B/C |
| Volatility/liquidity clock | normal, stressed, limit-down cluster | Fill and downside are state-dependent | A |
| Information clock | no named catalyst, fresh filing/news, repeated narrative | Distinguishes information from pure attention | C |
| Supply clock | pre-unlock, unlock, low/high free-float pressure | Changes queue elasticity and T+1 cohort supply | C |
| Publication clock | pre-event, after-close, next-morning available | Prevents LHB/block/news leakage | B/C |

Interactions should be hierarchical: test the main family, one mechanism-mandated interaction, and a held-out confirmation. Do not create hundreds of bins and retain only attractive ones.

## 8. Data-clock audit and testability matrix

### Clock contract

Every input row should carry, or be conservatively assigned:

```text
event_at       when the market/company event happened
published_at   when the source first exposed it
collected_at   when the pipeline obtained it
usable_at      first strategy decision timestamp allowed to use it
revision_at    when a historical value changed, if revisions exist
source_id      immutable provenance/version key
```

`date` alone is not a point-in-time contract.

### What can be tested now versus what cannot

| Surface | Observed schema/capability | Safe current use | Boundary / missing collector |
|---|---|---|---|
| Nominal daily OHLCV | open/high/low/close/volume by local ticker | O1/O2/C2/C3 and coarse D1-D3 paths | No shares/float, no amount, no intraday ordering; slice incomplete |
| Reconstructed limit events | date, ticker, board, width, event, lianban, close distance | Daily state/path grammar and market tape | Effective-dated ST/rule repair; corporate actions and shallow ST history; no seal timing |
| Aggregate limit tape | breadth, sealed/failed counts, ladder max | R1 market crowd state | Local-universe conditional; historical rule errors can contaminate aggregates |
| Vendor zt pool | lianban, seal fund, failed seals, turnover, sector, date/asof | Short-history C1/R2 proxy and label audit | Only 36 supplied sessions; only pool names; 29.04% ticker overlap; no denominator/full universe |
| China Pick Lab fires | limit width/state/fillable/T+1 stamps on selected fires | Audit frozen feature and nonfill conventions | Selection-conditioned, not a universe study; daily `fillable` is a lock proxy, not executed fill |
| LHB | event/history and trailing summary fields | Conservative lagged R4 cells | Need exact `published_at`, complete seat history, and event-level PIT availability |
| Block trades | collector/schema for aggregate and per-trade details | Conservative D-1 sponsorship cells after local coverage audit | Local partition coverage not audited here; exact publication clock and PIT industry membership needed |
| THS membership | current map plus snapshot/history schema | Membership as of an actually stored prior snapshot | Deeper PIT history and delist/reclassification handling needed |
| ST/security master | shallow ST history plus current snapshot | Quarantine/audit only around affected names | Effective-dated risk-warning, listing, suspension, board, corporate-action, and rule tables needed |
| Minute/auction | not in inspected inventory | none | Collect trades/quotes, indicative auction state, first/last seal, reopen order |
| Order book/queue | not in inspected inventory | none | L2 snapshots/events or broker telemetry required |
| Free float/unlocks | shares absent from daily bars | none beyond raw-volume proxy | Effective-dated shares, float cap, restrictions, and unlock calendar required |
| Post-close fixed price | legal regime exists from 2026-07-06 for all A-shares | separate prospective construction only | Need separate orders/trades/volume and provider OHLCV-inclusion semantics |

### Required quarantines before any broad daily measurement

1. Post-2026-07-06 main-board risk-warning events until official width rules and PIT status are effective-dated in the detector.
2. IPO/no-limit windows and ambiguous first-bar listing histories.
3. Bars with unresolved corporate-action reference prices.
4. Tickers without a deterministic exchange/board mapping.
5. Sessions where a successor should exist but the security-level trading status is unknown.
6. Any feature whose `usable_at` is later than the claimed decision.

Quarantine is not deletion. Counts and reasons must be printed.

## 9. Fill funnel: candidate is not position

### Funnel stages

```text
N0 observed universe-session
 -> N1 event detected before decision
 -> N2 security/order legally eligible
 -> N3 order price reachable
 -> N4 executable opposing volume exists
 -> N5 queue/time priority permits execution
 -> N6 realized or conservatively simulated fill
 -> N7 T+1 sell eligibility reached
 -> N8 planned exit executable
 -> N9 realized liquidation; otherwise unresolved/carry state
```

Report every `N0...N9` count and conditional rate. Never report only filled winners.

### Entry protocols that must remain separate

| Code | Freeze | Order | What can be claimed |
|---|---|---|---|
| E-OPEN | D close | D+1 opening auction/first executable open with frozen price cap | Daily proxy if open is tradable; exact auction fill needs auction data |
| E-CONT | D close or named D+1 auction timestamp | D+1 continuous-auction marketable limit | Requires quote/minute data; cannot inherit opening price |
| E-M5 | first five complete minutes | order begins next minute | Minute-fill construction only |
| E-UNLOCK | first documented reopen after a seal | order begins after reopen | Requires event/quote order; no same-timestamp lookahead |
| E-PCF | D regular close | D post-close fixed-price order, 2026-07-06+ only | Requires separate post-close queue/trade tape; same-day close is not an assumed fill |
| E-QUEUE | pre-seal decision | limit order joins upper queue | Fill only from order-rank/execution evidence; otherwise zero |

### Daily fill proxy boundary

Daily data can say that a next session was not a one-price upper lock, but it cannot prove a particular order filled at the open, at VWAP, or in a queue. Use terms such as `daily_tradability_proxy`, never `filled`, unless the order protocol is supported by finer data.

### Two-model decomposition

For candidate `i` and frozen order `o`:

```text
p_path_i = P(target path | information available at decision)
p_fill_i = P(order fills | order o, information available at submission)
contribution_i = I(fill_i) × realized_net_path_i
nonfill_i = 0
```

Do not multiply optimistic point estimates and call the product validated expectancy. Calibrate both distributions out of sample and retain their covariance.

## 10. Exit and portfolio construction

### Exit lattice

Every entry cell should be crossed with only a small preregistered exit set:

1. exact D+1, D+2, D+3, D+5, or D+10 close;
2. first executable session after a frozen upward target, with target detection and execution separated;
3. state exit after a failed seal or sector-clock transition, decided only after that state is known;
4. fixed adverse barrier, recognizing that T+1 prevents a same-day stop after purchase;
5. post-close fixed-price liquidation as a separate 2026-regime protocol;
6. unresolved exit when halted or lower-limit locked—never a jump to the resumption date.

For each horizon, publish both:

- mark-to-market path at the exact session; and
- executable liquidation result under the named order.

They are not interchangeable.

### Portfolio sleeves

Measure at least four portfolios without choosing among them after seeing outcomes:

| Sleeve | Assembly | Purpose |
|---|---|---|
| Focal leader | top one eligible name | Tests whether concentration is doing all the work |
| Equal-weight eligible cohort | top `K` frozen before order, nonfills left cash | Measures opportunity breadth |
| Sector-capped cohort | max one/two names per PIT concept cluster | Controls common-theme dependence |
| Spectator-substitution basket | excludes locked leader; holds eligible followers by frozen graph rule | Directly tests O4/D4 |

Additional laws:

- rank only with features frozen at decision;
- deduplicate a ticker across overlapping themes;
- cap name and sector exposure before knowing fills;
- apply costs and slippage to fills only, while cash earns the preregistered cash assumption;
- do not backfill an unfilled slot with the next ex-post winner;
- report turnover, capacity proxy, and concentration alongside path statistics.

### Portfolio probability

The useful operator object can be “probability the cohort produces at least one executable target path,” but independence is usually false.

```text
P(any success) = 1 - Π(1 - p_i)
```

is only an independence benchmark. The research object should model sector/day clustering with empirical cohort counts, a beta-binomial model, or another preregistered dependence model. Compare:

- name-level calibration;
- number-of-fills calibration;
- number-of-successes-given-fills calibration;
- `P(any)`, `P(at least 2)`, and downside-cluster probability;
- realized capital deployment, including cash from nonfills.

## 11. Collector priorities

The priorities below rank marginal ability to distinguish mechanisms and enforce execution, not ease alone.

### P0 — unblock valid denominators and labels

1. **Full-universe security-session spine.** Effective-dated ticker/exchange/board, listing and delisting dates, IPO no-limit windows, suspensions, risk-warning status, reference prices, corporate actions, and applicable rule version. EDV D3; feasibility C.
2. **Full-universe nominal daily OHLCV completion.** Expand beyond the 514-overlap slice and log vendor/local observation states. EDV D3; feasibility C.
3. **Effective-dated limit-rule engine.** Encode the 2026-07-06 risk-warning change and other board/rule epochs; retain source/version receipts. EDV D3; feasibility A/C.
4. **Exact successor-session status.** Security-level calendar and halt/resumption state so missing bars never jump. EDV D3; feasibility C.

### P1 — distinguish board morphology and opening conversion

5. **Historical raw zt-pool expansion.** Collect all available sessions and all raw columns, including first/last seal time if exposed, not only the current parsed subset. Preserve vendor row and `collected_at`. EDV D3; feasibility B/C.
6. **Minute trade bars for events plus matched controls.** At least auction/open, first/last seal, reopen, and closing-auction windows. EDV D3; feasibility C.
7. **Opening-auction snapshots.** Indicative price, matched/unmatched quantity, top levels if licensed, cancellation phases, final execution. EDV D3; feasibility C/D.
8. **Post-close fixed-price tape.** Separate 15:00 close from post-close orders, matched volume, queue, and fills for the 2026 regime. EDV D3; feasibility C/D.

### P2 — make supply and queue hypotheses real

9. **Effective-dated free float and unlock calendar.** Shares, float cap, restricted cohorts, unlock dates, and revisions. EDV D3; feasibility C.
10. **Order-book/queue events at both bands.** Queue size, additions, cancellations, executions, first rank, and time at limit. EDV D3; feasibility D.
11. **Volume-at-price / trade-sign tape.** Needed for inventory-vintage and absorption cells. EDV D3; feasibility C/D.

### P3 — causal clocks and cross-sectional redistribution

12. **Deep PIT concept membership.** THS plus stable industry taxonomy, membership `valid_from/valid_to`, and bridge graph. EDV D3; feasibility C.
13. **LHB event/publication/seat tape.** Event timestamp, trigger, seats, amounts, publication/availability, and revisions. EDV D2; feasibility C.
14. **Block-trade PIT completion.** Event, buyer/seller identity class, premium, size, publication/availability, and PIT industry. EDV D2; feasibility B/C.
15. **Company announcement/catalyst tape.** Exact dissemination time, type, novelty/repetition, and source receipt; text models remain context-only. EDV D2; feasibility C.
16. **Broker execution telemetry or conservative paper-order receipts.** Order sent, acknowledged, queue rank where available, partial fills, cancels, rejections, and fees. EDV D3 for execution; feasibility D.

## 12. UNTESTED VARIANTS

**Every row in this ledger is untested ore. None is a result or recommendation.** Each row must become one or more canonical construction keys before measurement.

| Variant | Linked family | Required data | EDV | Why it is a separate construction |
|---|---|---|---:|---|
| V01 `+6% → +6%` without a board | O2/C3 | daily | D3 | Tests staircase repricing rather than board recurrence |
| V02 `+8% → pause → board` | O2/C3 | daily | D3 | Separates cadence from near-limit one-day state |
| V03 band-progress `0.6→0.8` across 10% vs 20% boards | O2/R3 | daily + rule master | D3 | Same absolute move implies different constraint proximity |
| V04 compressed range + lower-wick reclaim + non-board close | O1 | daily | D3 | Path-shape onset without requiring a board |
| V05 failed-down seal → reclaim → +6% first passage | O1/D2 | daily/minute | D3 | Downside release route, not generic dip buying |
| V06 locked leader → exclusive follower | O4 | zt pool + PIT membership | D3 | Direct spectator substitute |
| V07 locked leader → multi-concept bridge follower | O4/R2 | PIT graph | D3 | Tests whether attention traverses theme bridges |
| V08 20% leader lock × 10% follower response | O4/R3 | PIT membership + queue proxy | D3 | Width asymmetry may change spillover intensity |
| V09 multiple locked leaders in one theme → follower crowd-out | O4/R2 | pool + PIT membership | D2 | Spillover can saturate rather than amplify |
| V10 early seal-break-reseal | C1/D1 | minute/queue | D3 | Potential absorption morphology |
| V11 late seal break without VWAP reclaim | C1/D1 | minute | D3 | Potential demand exhaustion morphology |
| V12 closing-auction-only seal | C1/R3 | auction/minute | D3 | A close snapshot can differ from continuous demand |
| V13 queue half-life normalized by free float | C1/R5 | L2 + float | D3 | Raw seal fund lacks supply scale |
| V14 smooth ladder pyramid versus top-heavy ladder | C2 | daily/vendor pool | D3 | Whole-crowd topology beyond focal streak |
| V15 market ladder gap with isolated high-age leader | C2/R1 | daily | D2 | Tests survivor isolation/exhaustion |
| V16 board-pause-board | C3 | daily | D3 | Tolerates inventory reset between boards |
| V17 failed-board-pause-board | C3/D1 | daily/minute | D3 | Failure may be transfer rather than terminal |
| V18 first legal sell session after ignition-volume spike | C4 | minute volume-at-price | D3 | T+1 inventory-vintage clock |
| V19 cohort cost-stack pressure on first unlock | C4/R5 | minute + float | D3 | Distinct cost vintages can alter supply |
| V20 failed-up close-location × break time | D1 | daily + minute | D3 | Daily wick and intraday timing are complementary |
| V21 lower-limit first unlock with auction reclaim | D2/O3 | auction/minute/L2 | D3 | Direct supply-release mechanism |
| V22 lower-limit leader → peer damage versus peer rotation | D2/D4 | PIT membership | D3 | Downside spectator redistribution |
| V23 same-session upper-then-lower touch | D3 | minute | D2 | Ordering is invisible in daily bars |
| V24 lower-then-upper traversal | D3 | minute | D2 | Reversal order differs from exhaustion order |
| V25 failed leader → new theme leader | D4/R2 | PIT graph + minute | D3 | Cross-sectional capital rotation |
| V26 warm-middle crowd state versus cold/euphoric tails | R1 | daily/vendor pool | D3 | Tests nonmonotonic continuation |
| V27 equal heat entered by acceleration versus deceleration | R1 | daily | D3 | Hysteresis, not level alone |
| V28 rising sector breadth with falling concentration | R2 | PIT membership | D3 | Orderly diffusion state |
| V29 high breadth with rising concentration | R2 | PIT membership | D2 | Possible late leader domination |
| V30 post-2026 risk-warning 10% cohort | R3 | corrected rule/ST master | D3 | Current detector's 5% assumption is invalid after the rule change |
| V31 post-close fixed-price D entry versus D+1 open | R3/O2 | post-close tape | D3 | Different legal fill clock and overnight exposure |
| V32 LHB pre-event institutional buy versus post-event appearance | R4 | exact publication/seat tape | D2 | Sponsorship and publicity have opposite clocks |
| V33 block premium before ignition × failed seal | R4/D1 | block PIT + daily/minute | D2 | Inventory sponsor may change failure interpretation |
| V34 queue value / free-float cap | R5/C1 | float + L2/vendor | D3 | Corrects raw queue scale |
| V35 event volume / free-float shares × T+1 unlock | R5/C4 | float + minute | D3 | Supply cohort rather than raw volume |
| V36 observability-weighted overlap panel | R6 | security spine | D3 | Sensitivity, not substitute for missing outcomes |
| V37 full-vendor-universe replication | R6 | completed OHLCV | D3 | Tests whether slice conclusions generalize |
| V38 halted exact successor as competing risk | D2/R6 | security-session spine | D3 | Prevents resumption-date lookahead |
| V39 daily tradability proxy versus true opening-auction fill | O3/C1 | auction execution | D3 | Quantifies proxy error rather than assuming equivalence |
| V40 sector-capped `P(any executable target)` | O4/C2/P | portfolio ledger | D3 | Portfolio probability under dependence |
| V41 unfilled leader plus filled follower basket | O4/P | fill ledger + PIT graph | D3 | Treats spectator context and position separately |
| V42 lianban undercount sensitivity around incremental lookback | C2/R6 | corrected backfill labels | D2 | Data-generation path can distort ladder age |
| V43 residual vendor/reconstruction disagreements | R3/R6 | dual-source receipts | D2 | Audit rule/corporate-action errors before considering mechanism |
| V44 first/last seal time × post-close fixed-price demand | C1/R3 | minute + post-close tape | D3 | Regular-session queue may migrate to a new execution venue/time |
| V45 repeated abnormal-trading publicity × crowd cooling | R4/R1 | announcement clock | D2 | Regulatory attention may change crowd participation |

The ledger must grow append-only during ideation. Measurement may add `tested_key`, date, and receipt columns, but it must not delete null variants or collapse them into a topic-level verdict.

## 13. Measurement sequence and reconciliation protocol

### Wave A — validity before alpha

1. Build the effective-dated security/rule spine.
2. Repair/quarantine post-2026-07-06 risk-warning labels.
3. Census local/vendor/full-universe observation states.
4. Pin exact successor-session, halt, and corporate-action handling.
5. Freeze a dual-source event-definition audit.

### Wave B — broad daily discrimination

Pre-register a small set of D3 daily cells:

- O1 compression/reclaim;
- O2 band-progress staircase;
- C2 ladder topology;
- C3 cadenced paths;
- D1 coarse failed-seal bifurcation;
- D2 coarse lower-band release;
- R1 crowd nonlinearity;
- R6 overlap sensitivity.

Use a nested common-prior baseline so “new” value means incremental discrimination, not rediscovery of the supplied six axes or lianban frequency.

### Wave C — short vendor/PIT interaction panel

Use the 36-session pool only as a clearly bounded pilot for data integrity, morphology proxies, and collector design. Do not generalize a short-overlap verdict to the historical family.

### Wave D — prospective microstructure accrual

Accrue auction, minute, queue, post-close, float, and fill receipts prospectively. Exploration/display surfaces can show data quality and frozen receipts without any promotion.

### Reconciliation with the other independent team

For every proposed construction from either team:

1. normalize it into `K = U×R×E×D×X×O×F×Y×H×P×C`;
2. label exact overlap, parameter variant, orthogonal mechanism, or contradiction;
3. preserve both variants when any coordinate differs;
4. rank by EDV, feasibility, leakage risk, and collector reuse;
5. identify which common-prior fact it extends rather than re-tests;
6. mint a preregistration key only after clocks/fills/falsifier are complete;
7. record nulls at the key level and keep the parent family open.

No “consensus” is required for ore. The point of reconciliation is to expose missing coordinates and correlated blind spots, not to vote ideas away.

## 14. Primary rule references used for mechanics only

- [SSE Trading Rules (2026 revision), effective 2026-07-06](https://big5.sse.com.cn/site/cht/www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)
- [SSE summary of the 2026 revisions, including risk-warning width and post-close fixed-price expansion](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml)
- [SZSE Trading Rules (2026 revision), effective 2026-07-06](https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html)
- [SZSE 2026 risk-warning trading guidance](https://www.szse.cn/lawrules/service/member/t20260630_621404.html)
- [BSE Trading Rules published 2026-04-24, effective 2026-07-06](https://www.bse.cn/jygl_list/200028217.html)
- [SSE explanation of price/time priority and call-auction matching](https://english.sse.com.cn/start/trading/mechanism/)

These sources define market mechanics and rule epochs. They do not support any alpha verdict in this map.

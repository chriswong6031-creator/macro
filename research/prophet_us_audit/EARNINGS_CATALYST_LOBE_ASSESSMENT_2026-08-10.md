# Prophet earnings-window assessment

**Decision date:** 2026-08-10
**Scope:** fresh US Prophet entries near scheduled earnings, the user-facing treatment of those names, and the next research lane.
**Decision:** keep the three-trading-day `Buy now` holdout, stop hiding the names, and build a separate forward-tested earnings catalyst lobe on the existing Company Event Intelligence spine.

## Bottom line

Earnings are opportunity **and** discontinuity. The mistake is forcing both ideas into one label.

- A normal Prophet entry says the setup and entry timing are good enough to act on now.
- A pre-earnings entry is also a bet on an event whose expectations, guidance and reaction are not yet modeled by Prophet.
- Those should not silently be treated as the same trade.

The current gate is supported by the house evidence: entries inside the earnings window have a fatter immediate downside tail without a distinguishable improvement in average return. But the old UI turned a risk distinction into disappearance. The names should remain visible in an **Earnings watch** below the actionable cards, with a direct link to each dossier.

## What the house evidence actually says

### 1. The original broad event-window study supports the holdout

The preregistered primary comparison in [`research/entry_stack/W1_SEV_REPORT.md`](../entry_stack/W1_SEV_REPORT.md) covered 57,595 gradable fires. For the three-trading-day window, 4,332 treatment rows were compared with 53,263 controls.

- Five-session stop risk was **8.7 percentage points higher** in the earnings-window arm; 95% CI **+7.8 to +9.9 points**.
- The direction held in all four eras.
- The rule affected 6.0% of covered fires, below its 10% budget.
- The 21- and 63-session adverse-excursion measures were indistinguishable. The measured penalty appears in the first five sessions; no longer-horizon adverse-excursion difference was detected.

That is a risk result, not a claim that earnings-window names are bad companies or have no upside.

It is also not a perfect replay of today's calendar gate. The historical design uses Item 2.02 filing dates as the event anchor rather than a live scheduled-event feed, and its source panels carry a survivor-bias warning. The preregistered stop-risk result is strong support for caution, but the forward ledger must test the production calendar contract directly.

### 2. The study closest to the user's hypothesis did not find an earnings edge

[`EARNINGS_IGNITION_MEASUREMENT_2026-08-08.md`](./EARNINGS_IGNITION_MEASUREMENT_2026-08-08.md) asks the more specific question: does a fresh Prophet-style confluence in the five sessions before earnings predict a better announcement reaction?

- Pre-report confluence: mean reaction **+0.047%**, n=726, 95% CI **-0.32% to +0.42%**.
- Other covered reports: mean reaction **+0.352%**, n=9,497.
- Difference: **-0.305 percentage points**, 95% CI **-0.690 to +0.079** — indistinguishable.
- At the entry anchor, the mean five-session excess return was also indistinguishable, while the downside tail was much wider near earnings.
- Holding the existing quality label fixed, five-session losers were **10.2% vs 3.3%** for `take` rows and **35.4% vs 21.1%** for `block` rows.
- 357 of 726 pre-report confluences had a negative reaction: 49.2%.

This does not support promoting the shortcut “curling upward before earnings probably means informed buying” into a Prophet decision rule. A smaller edge below the study's detection threshold remains possible, and the intuition can be true in individual cases; this signal did not identify those cases reliably enough to act on.

### 3. External research supports the possibility, not the shortcut

The broader literature explains why the user's intuition is worth testing:

- Frazzini and Lamont document an average earnings-announcement premium tied strongly to announcement-period volume and investor attention ([NBER Working Paper 13090](https://www.nber.org/papers/w13090)).
- Baker, Litov, Wachter and Wurgler find that stocks mutual funds bought before earnings subsequently outperformed stocks they sold around the announcement ([NBER Working Paper 10685](https://www.nber.org/papers/w10685)).
- Brennan, Huh and Subrahmanyam find evidence that informed trading can impound part of corporate-announcement news before the event ([Review of Financial Studies](https://academic.oup.com/rfs/article-abstract/31/6/2326/4817078)).

None of these papers says that a generic price curl or momentum cross identifies informed buying. Fund trades, informed-order-flow estimates, announcement attention and Prophet's setup detector are different instruments. The house event study is the relevant test of the instrument actually used here.

## Product decision

### Keep

Keep the fresh-entry holdout from `T-3` through the report for the normal Prophet `Buy now` lane. Do not apply it to active positions, and keep the existing fail-open behavior when the earnings calendar is missing or stale.

### Change

Replace “setups suppressed” with an **Earnings watch** below the actionable board:

- keep every ticker visible and linked;
- say the setup still exists;
- say earnings can reprice the stock quickly in either direction;
- make clear that Prophet waits through the report date before issuing its normal entry call.

For this release, the tickers link to their dossiers. A later iteration should show the scheduled timing and event state only from the canonical point-in-time company-event spine, so “scheduled,” “published” and “corrected” cannot be confused.

This is not semantic sugar. It separates two trade contracts:

1. **Prophet entry:** act on a measured setup under ordinary price continuity.
2. **Earnings event trade:** knowingly accept gap risk because an explicit view on the report, expectations and reaction justifies it.

The second contract can become a real product only after it earns its own evidence.

## Start the forward ledger now

The next improvement is measurement before modeling. Every Prophet candidate near earnings should create one immutable ledger row, whether or not the normal board holds it out.

### Identity and point-in-time fields

- stable company-event ID and correction lineage from the existing Company Event Intelligence spine;
- ticker, issuer ID, report fiscal period, scheduled event time and calendar vintage known at decision time;
- candidate timestamp, Prophet version, rank, stage, entry range and all setup components as known then;
- explicit cohort: `normal_entry`, `earnings_watch`, or future `event_sleeve`;
- source timestamps and availability flags; no later-restated value may replace the decision-time value.

### Event facts

- consensus EPS and revenue, revision path, dispersion and recency;
- company guidance and prior guidance changes;
- actual EPS, revenue, margins, important segment or operating KPIs, and new guidance;
- surprise values on a consistent GAAP/non-GAAP basis;
- report timing, filing/release/transcript availability and corrections;
- options-implied move, skew and term structure when genuinely available point in time.

### Outcomes

- prior close, first tradable post-report price and close;
- event gap and event-day excess return;
- H5, H10 and H21 excess return;
- maximum favorable and adverse excursion;
- whether the realized move exceeded the pre-event implied move;
- post-event drift and whether the original Prophet setup survived.

The nightly job should be the sole outcome advancer. It must also write the counterfactual normal-entry result for held-out names so the gate remains auditable instead of becoming an unmeasured permanent rule.

## The earnings catalyst lobe

This is **not** a new transcript system. The repository already has exact earnings evidence, immutable event objects, Company Intelligence, Earnings Wire and post-selection Prophet context. Extend that spine; do not create another earnings interpretation.

### Predict three different things

Do not collapse “earnings beat” and “stock goes up” into one target.

1. **Fundamental surprise:** probabilities of EPS, revenue and guidance beating, meeting or missing decision-time expectations.
2. **Event reaction:** probability and size of the post-report move, including whether it exceeds the options-implied move.
3. **Post-event drift:** direction and risk over H5, H10 and H21 after the first tradable reaction.

A company can beat EPS and fall because guidance, revenue quality, valuation or already-priced expectations disappoint. Separate targets force the system to learn that distinction.

### Candidate inputs

- consensus level, revision momentum, analyst dispersion and forecast age;
- management guidance, estimate-to-guidance distance and prior guidance behavior;
- revenue, margin, cash-flow and segment trends from exact filings and releases;
- peer reports already published in the same industry earnings wave;
- options-implied move, skew, term structure and pre-event volume when available;
- price strength, volume behavior, relative strength and the existing Prophet setup components;
- short interest, institutional and insider context only when point-in-time provenance is clean;
- cited transcript, release and filing claims from the canonical event spine.

Pre-earnings momentum belongs here as **one feature**, not as proof of informed buying.

### Modeling and evaluation

- use walk-forward, purged time splits; never random train/test shuffles across adjacent quarters;
- group issuer and closely related share classes to prevent leakage;
- compare against consensus-only, revision-only, implied-move and simple base-rate benchmarks;
- measure calibration as well as ranking; a useful 60% probability must behave like 60%;
- report performance by era, sector, market-cap band, report timing and data-availability state;
- include class balance, coverage, transaction costs, gap slippage and the untradeable after-hours interval;
- keep missing inputs explicit instead of silently imputing a favorable value.

Recent work is a useful warning against a model-first victory lap. Campbell, Ham, Lu and Wood report that 90% of the machine-forecast specifications they examined failed to beat analysts, with results highly sensitive to specification choices ([SSRN 4495297](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4495297)). The FinCall-Surprise benchmark likewise finds that apparent high accuracy can be an illusion created by class imbalance ([arXiv 2510.03965](https://arxiv.org/abs/2510.03965)).

### Authority ladder

1. **Shadow:** write forecasts and outcomes; no UI, rank, size or gate effect.
2. **Display:** show calibrated event probabilities and cited reasons after enough forward evidence, still without changing normal Prophet.
3. **Optional event sleeve:** a separately labeled catalyst trade with its own sizing, gap-risk budget and track record.
4. **Normal Prophet influence:** only after a preregistered forward comparison shows that the lobe improves outcomes net of costs and survives era and sector checks.

The existing `DNR:KILL-CALENDAR-GATED-RISK` rule still applies: an earnings calendar by itself cannot become a market-risk sizing leg. This proposal is issuer-level event research, kept separate from the normal Prophet entry contract until it earns authority.

## Required order of work

1. Ship the human UI treatment and keep the current gate.
2. Retire or quarantine the legacy split-brain earnings-score influence described in [`EARNINGS_COMPANY_EVENT_SUITE_REMAINING_BUILD_HANDOFF_FOR_CLAUDE_2026-08-06.md`](../EARNINGS_COMPANY_EVENT_SUITE_REMAINING_BUILD_HANDOFF_FOR_CLAUDE_2026-08-06.md); missing legacy data must not alter a plan.
3. Add the immutable candidate/event/outcome ledger on the canonical company-event ID.
4. Freeze a point-in-time feature manifest and benchmark docket.
5. Run the lobe in shadow and publish its honest forward scorecard.

## Verdict

Do **not** lift the earnings holdout today. Do **not** hide the names either.

Treat earnings-window candidates as a visible researchable opportunity set, then earn the right to trade the event with a separate, calibrated catalyst lobe. That preserves the Prophet board's promise while opening the more ambitious path the current system does not yet possess.

# Stock Personality — Operator Playbook (by Fable)

Date: 2026-07-07
Status: OPERATOR DOCTRINE — display/context tier; nothing here scores, sizes, or gates
Companions: `research/STOCK_PERSONALITY_FIELD_GUIDE.md` (measured behavior, our data) ·
`research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md` (ontology + laws)
Provenance: institutional-practice research sweep wf_66debfa4 (6 cited lanes + completeness
critic) × descriptive field-guide sweep wf_b08c6af3 (223-name deep corpus) — 2026-07-07.
Sources are cited per claim in the research transcripts; practitioner lore is flagged as lore.

---

## 0. What this document is for

The personality labels exist to answer four questions the chart alone cannot:

1. **Who is on the other side?** Every type has a characteristic mix of forced flows
   (mandates, index events, ETF arbitrage, dealer hedging) and discretionary flows.
   The same candlestick means different things depending on whose balance sheet
   produced it.
2. **Which patterns deserve trust here?** Momentum, mean-reversion, breakouts, PEAD,
   and 52-week-high anchoring are all *type-conditional* in the literature — each
   works in specific habitats and is a trap in others.
3. **How much patience does this animal deserve?** Drawdown durations, recovery
   odds, and event sensitivity differ so much by type that a single stop/patience
   rule is provably wrong.
4. **How much does the label itself tell you?** Label informativeness varies ~3× by
   type. Treating all labels as equally binding is a category error.

**In plain English:** this is the manual for reading each kind of stock the way the
people who move the money read it — before any signal fires. It tells you what kind
of tape you are looking at, who made it, what usually works on it, and the classic
mistake it invites.

---

## 1. Cross-cutting laws (PB-L1..L10)

**PB-L1 — Know the forced flow before reading the tape.** Index reconstitution,
style-box migration, ETF creation/redemption, and quarter-end window dressing are
*price-indifferent* flows with outsized impact (inelastic-markets result). The S&P
inclusion pop is arbitraged away (7.4% in the 1990s → <1% 2010-2020, Greenwood &
Sammon); the *deletion overshoot* is not — deleted names with intact balance sheets
outperform ~7%/yr for two years (Research Affiliates). Announcement dates, not
effective dates, are the catalyst. Selling into a deletion window is mechanical,
not informed — never read it as fundamental conviction.

**PB-L2 — Sponsorship decides which entry patterns work.** In `long_only_sponsor`
names, institutions add on weakness under participation constraints (10-25% of ADV,
multi-week programs): shallow pullbacks with volume contraction are *entries*, and
multi-day drift without news is usually an ongoing program (metaorder impact decays
to a permanent residual — don't fade the first 3 days). In unsponsored or
`retail_attention` names the same pullback has no natural buyer. 52-week-high
proximity is a *positive* filter under institutional ownership (George & Hwang
anchoring — and it does not long-run reverse) and a *negative* one under retail
ownership. Breakouts deserve trust roughly in proportion to sponsorship + volume
confirmation (the Lane-6 practitioner dataset uses >150% of 20d average volume;
O'Neil's separate rule is 40-50% above the 50d average — both lore-grade).

**PB-L3 — Labels are not equally informative.** Within-type outcome dispersion in
our data: `financial` 0.16, `quality_compounder` 0.18 … `speculative_unprofitable`
0.54. Knowing a name is a financial tells you a lot about its year; knowing a name
is speculative tells you almost nothing — single-name work dominates there, and
type-level treatment rules are weakest exactly where the tape is wildest.

**PB-L4 — Patience budgets are type-specific (measured, our data).**
`high_beta_momentum`: median 121 trading days below peak, 61% of label-years never
reclaim the prior peak. `quality_compounder`: down-capture 0.57 (essentially tied
with `dividend_defensive` at 0.567 for lowest) and only 38% non-recovery — both
statistics from a 3-ticker cell, illustrative. `broken_growth` is the only type
whose down-capture (1.05) structurally exceeds up-capture (0.92).
`dividend_defensive` is low-vol but has the heaviest left tail (skew −0.25; n=4
tickers): its losses are lumpy tail events. Holding a momentum name to a compounder's patience budget — or trusting a
defensive name's calm as tail-safety — are both measured mistakes.

**PB-L5 — Chart labels split into personalities and states.** Measured dwell times:
`failed_breakout_trap` ~35 trading days (a sticky regime), `stair_step_leader` ~10d,
`mean_reversion_rubber_band` ~3d (a spike state that exits to mixed 86% of the
time). Treat trap/leader/grind as *personalities* you plan around; treat
rubber_band as *weather* you react to. `mixed_chart` (66% of all name-days) is the
waiting room, not a personality.

**PB-L6 — Type transitions LAG price.** The archetype upgrade
(`speculative_unprofitable → rate_sensitive`) arrives after a median +29.5%
change-year move; the label confirms, it does not lead. `financial` is near-terminal
(P(stay)=0.96); `secular_growth` and `broken_growth` are 1-year way-stations
(P(stay)=0.56); `speculative_unprofitable` is the ecosystem's gravity well
(receives exits from every other type). Secular growth usually fades *gracefully*
(→ cyclical/mixed, rarely straight to distressed). Read a fresh label change as
"the past year is now official," not as news.

**PB-L7 — Event windows have per-type chart authority.** Earnings amplification is
~1.5-1.7× for `deep_value` (1.70), `cyclical` (1.49) and `financial`/`dividend_defensive`
(1.47) — a sharp signal on a quiet tape. The low-amplification types are
`high_beta_momentum` (1.26) and `distressed`/`quality_compounder` (1.23);
`speculative_unprofitable` is mid-pack at 1.34 — its earnings add proportionally
less only because its *non-earnings* baseline (|ret| ~1.2%/day, the highest) is
already event-grade noise. Two different facts govern the post-print week:
`quality_compounder` has the least-disruptive earnings *day* (lowest amplification,
lowest p90 move 3.14%) but an above-median post-earnings 5-day dispersion (IQR
6.59%; n=3 tickers, illustrative) — the measured *tightest* post-event drift
belongs to `mixed` (4.93%) and `financial` (5.21%). `high_beta_momentum` and
`speculative_unprofitable` post-event dispersion (~9-10% IQR) is ~2× everyone
else's — chart patterns lose the most authority there for a week after prints.
`biotech`-style binaries (event_override mode) suspend chart authority entirely:
run-up and hold-through are separate trades with separate sizing.

**PB-L8 — Our own engine has a revealed personality bias.** Fires are over-weighted
to `failed_breakout_trap` names (1.18× overall, rising to 1.41× at the
highest-conviction gate tier) and starkly under-weighted to `stair_step_leader`
(0.68×; 0.355× at T3) and `smooth_compounder_grind` at high tiers (0.41×). The
system hunts technical distress and is structurally cold on clean leaders — the
two-brains diagnosis made visible. This is a *coverage* fact, not an outcome claim;
the chartered question it raises is listed in §7.

**PB-L9 — The classic anomalies are type-conditional; applying them off-habitat is
the standard retail error.** Momentum lives in low-coverage/high-uncertainty
growth names and *crashes* in the post-panic rebound (Daniel-Moskowitz: the short
leg becomes a short call on distressed/high-beta names — do not press momentum
shorts in weeks 1-4 of a broad recovery). Short-term reversal is real only where
liquidity provision dominates (`wide_spread_impact` / `slow_mean_reversion_liquidity`
micro tiers) — on tight-spread names it is arbitraged and cost-eaten. PEAD survives
only in small/low-coverage/high-cost names; it is dead in large caps. The MAX
"lottery" effect makes post-spike chasing in `retail_attention`+`speculative` names
a documented negative-alpha trap. BAB favors defensives in risk-off and punishes
them in early-cycle recoveries; QMJ says quality lags violently for ~60-90 days
after a panic low while junk rallies. (All: post-publication decay applies —
assume 30-50% haircuts, larger in liquid large caps.)

**PB-L10 — Squeeze and gamma mechanics override chart personality.** When
`short_interest_tinderbox` + `retail_attention` co-occur with negative-gamma
conditions, dealer hedging plus forced covering removes the mean-reversion anchor
entirely (GME/AMC class): rubber-band logic is void, time-stops (3-5 days) replace
price targets, and float-starvation rallies (HKD class — insider-controlled float,
not even a squeeze) cannot be safely shorted for lack of borrow. Conversely, in
`options_pin` mode near heavy OI at expiration, breakouts within 1-2% of the pin
strike tend to fail into the close — and 0DTE-driven pins reset daily and only bind
in the final hours. Single-name GEX is only trustworthy where options ADV is deep.

---

## 2. Archetype playbook cards

Format per card: **Identity · Other side of the trade · Measured behavior (ours) ·
Treatment · Classic mistake.** Treatment lines are context doctrine — display-tier
guidance for the operator, never automated gates.

### quality_compounder
- **Identity:** durable ROIC above cost of capital, reinvestment runway.
- **Other side:** long-only accumulation programs, passive weight, quality funds;
  low short interest. The marginal buyer *wants* pullbacks.
- **Measured:** near-lowest down-capture (0.57, tied with dividend_defensive) and
  the best drawdown recovery (38% non-recovery) — 3-ticker cell, illustrative;
  calmest earnings *day* of all types (1.23× amplification, p90 3.14%), though the
  post-earnings *week* is above-median dispersed (IQR 6.59%) — read the print,
  respect the week. Label is informative (dispersion 0.18).
- **Treatment:** default long-bias patience; buy programs' shallow pullbacks (3-8%
  with volume contraction); do NOT apply Lynch's stalwart 30-50% profit rule to a
  true compounder — exit on moat erosion (multi-year ROIC decline, >3pp gross-margin
  compression), not on gain. Deep-washout entry species will rarely fire here (the
  good ones don't fall that far) — that is expected, not a coverage bug.
- **Classic mistake:** selling a compounder because it is "up a lot," or waiting
  for a deep washout that never comes.

### secular_growth
- **Identity:** long-duration earnings story; a duration asset wearing a stock.
- **Other side:** growth mandates + momentum universes on the way up; the same
  mandates *forced out* on style migration when growth breaks.
- **Measured:** most regime-torqued type (median 21d +3.1% in Q4 vs −1.1% in Q3;
  worst-decile −11.4% in Q3); positive skew at moderate vol; a 1-year way-station
  label (P(stay)=0.56) that usually fades gracefully to cyclical/mixed.
- **Treatment:** regime vector must be on the table for every entry (rates/quads do
  the heavy lifting); track PEG-style deceleration — two quarters of slowing growth
  is the leading exit indicator (Lynch fast-grower discipline); a stock leaving this
  label is usually *already* repriced (PB-L6).
- **Classic mistake:** buying the dip in a de-rating regime because the company is
  still "great" — the label's returns belong mostly to the discount rate.

### high_beta_momentum
- **Identity:** fast-money risk-appetite expression.
- **Other side:** momentum quants (12-1 universes, quarterly rebalances), hedge-fund
  crowding, options flow; thin true sponsorship.
- **Measured:** worst patience profile in the book — median 121d below peak, 61%
  of years never recover; near-zero macro-cycle sensitivity in medians but the
  fattest Q4 tails (P10 −12.8%). Post-earnings week ~2× less chart-readable.
- **Treatment:** rent, don't own: enter early in momentum phases on natural
  pullbacks (institutional momentum at scale is real only in liquid names), take
  the O'Neil 20-25% extension trims, and treat any climax signature (25-50% in 2-3
  weeks on record volume after a 100%+ run) as an immediate distribution flag
  regardless of thesis. Never press shorts on these after a >15% market drawdown
  begins to rebound (momentum-crash law, PB-L9).
- **Classic mistake:** converting a rented momentum trade into an owned position
  after the first drawdown — the 61% non-recovery stat is the counterparty.

### cyclical
- **Identity:** earnings torque on the macro/sector cycle.
- **Other side:** sector rotators, value screens (often at the wrong time),
  industrial specialists.
- **Measured:** beta 1.11 with down-capture > up-capture (1.12 vs 1.08); earnings
  amplification 1.49× (events matter on a quiet tape); large sticky cluster
  (P(stay)=0.90) with a revolving door to speculative on quality loss.
- **Treatment:** Lynch's inversion is the law here — *high* trailing P/E at trough
  earnings is the buy configuration, *low* P/E at peak earnings is the exit; naive
  value screens fire backwards on this type. Time entries with the sector/Oracle
  rotation clock rather than single-name patterns; industry leading indicators
  (inventories, capacity, commodity direction) outrank price signals for exits.
- **Classic mistake:** buying "cheap" at peak earnings — the value trap with the
  best PR.

### rate_sensitive
- **Identity:** bond-substitute equity; the discount rate is the business.
- **Other side:** income mandates that mechanically rebalance on >50bp yield moves
  (front-run AND lagged), duration overlays, sector ETFs (XLU/XLRE conduits).
- **Measured:** the largest single archetype cluster in our corpus; middling vol
  (0.27) but real drawdowns (−20%); second-largest liquidity-regime spread.
- **Treatment:** disaggregate by *contract duration* before any rate thesis (hotel
  REITs reprice daily; net-lease REITs are 10-20y duration; mREITs are curve
  instruments, not equities); the multi-week window *after* a large rate move —
  when mechanical rebalancers finish — is the cleaner entry; BAB dynamics mean
  these attract institutional rotation in risk-off and lag in early recoveries.
- **Classic mistake:** treating the archetype as one trade — duration dispersion
  inside the label is wider than between labels.

### dividend_defensive
- **Identity:** yield/low-vol expression; Lynch's slow grower.
- **Other side:** income funds, low-vol funds, BAB-constrained institutions.
- **Measured:** the all-weather type (quad medians 1.0-1.7%, shallowest tails
  ~−6%) — but the most left-skewed daily returns in the book (−0.25): when it
  breaks, it gaps.
- **Treatment:** the only buy thesis is yield × coverage (payout ratio >70% is the
  danger zone; FCF coverage below ~1.2× or a first cut is the operator's exit cue, not a dip); expect
  underperformance in early-cycle risk-on and do not chase it there; its earnings
  days are rare but violent relative to baseline (highest p90 event contrast) — do
  not sell tail insurance on a "boring" name.
- **Classic mistake:** reading low vol as low tail risk. The skew says otherwise.

### deep_value
- **Identity:** asset-backed cheapness; Lynch's asset play.
- **Other side:** value funds, activists, special-sits; often *nobody* (that's the
  problem).
- **Measured:** small corpus (6 deep names — illustrative only); highest earnings
  amplification in the book (1.70×): the tape sleeps between proofs.
- **Treatment:** cheapness is necessary, a *catalyst pathway* is sufficient
  (activist filing, spin, strategic review, refinancing that marks the assets);
  without one, expect `stale_dead_money` mode and pay the patience cost knowingly;
  PEAD-style post-event drift is most alive in this habitat (small, under-covered,
  costly to arb).
- **Classic mistake:** buying the discount without asking who closes it.

### financial
- **Identity:** leveraged spread business; sector-keyed label.
- **Other side:** rate/credit macro funds, index weight, yield buyers.
- **Measured:** the most label-stable type (P(stay)=0.96, median dwell 11y) and the
  most *informative* label (dispersion 0.16); beta 1.14 with slight down-skewed
  capture; smoothest large-move profile (lowest top-4-day concentration).
- **Treatment:** trade the group, not the name — single-name selection adds least
  here of all types; credit conditions and curve shape outrank any chart pattern;
  crisis regimes suspend the label's calm (balance-sheet opacity is the tail).
- **Classic mistake:** stock-picking energy spent where the label already told you
  ~85% of the story.

### distressed
- **Identity:** Altman-zone impairment; survival is the thesis.
- **Other side:** structural shorts with thesis letters, distressed/special-sits
  funds, forced sellers (index deletions, mandate exits).
- **Measured:** *paradoxically low beta* (0.68) — idiosyncrasy, not safety; the
  most liquidity-regime-sensitive type (3× expanding-vs-contracting spread); a
  moderate-stickiness trap (28% of runs last 5+ years); one of the tighter
  post-earnings drift profiles (~5.3% IQR — orderly relative to its own beta)
  because the tape is event-driven year-round.
- **Treatment:** Lynch's turnaround law — require *evidence already in hand* (debt
  restructuring done, credible management change, first positive-FCF quarter; two
  of three) before size; pilot-size anything earlier; distinguish structural-decline
  shorts from squeeze tinderboxes before ever being short (DTC + borrow trend);
  the junk-rally window (~60-90 days off a panic low) is the one regime where this
  type structurally outruns quality — rent it, don't re-rate it.
- **Classic mistake:** confusing a restructuring *announcement* with a
  restructuring.

### broken_growth
- **Identity:** a growth story the market has stopped believing.
- **Other side:** growth mandates *still exiting* (style migration + redemptions —
  supply overhead persists until the holder base rotates), shorts, eventually value
  buyers.
- **Measured:** the worst capture asymmetry in the book (down 1.05 / up 0.92);
  transient label (dwell 1y) that resolves either back to growth or down the
  gravity well; heaviest episodic event concentration (top-4 days = 10.6% of
  annual movement).
- **Treatment:** check whether the peak-era growth holders have actually left
  (13F/ownership footprint) before any "it's cheap now" entry — unrotated holder
  bases mean the air pocket has floors made of paper; after gap-downs, no
  mean-reversion entitlement for 5-15 days (no-natural-buyer law); the repair
  entry is `basing_accumulator` + proof triggers, never the first bounce.
- **Classic mistake:** anchoring to the old highs. The label exists because those
  highs belonged to a different owner base.

### speculative_unprofitable
- **Identity:** pre-profit optionality; the gravity well every other type can fall
  into.
- **Other side:** retail attention, lottery-preference flows, momentum tourists,
  shorts constrained by borrow; almost no mandate-grade sponsorship.
- **Measured:** highest vol (0.38), highest dispersion (0.54 — the label tells you
  the least here), right-skew lottery profile, widest post-earnings dispersion,
  counter-narrative regime medians driven by 2021-era concentration (honest
  small-history caveat).
- **Treatment:** single-name work or nothing — type-level rules are weakest here
  (PB-L3); MAX-effect law: never chase the post-spike continuation; dilution is
  the second axis of every thesis (shelf/ATM watch, attention half-life exits on
  volume fade rather than price); insider-controlled float variants (HKD class)
  are unshortable regardless of apparent absurdity.
- **Classic mistake:** importing any other card's playbook because the chart
  rhymes for a week.

### mixed (+ the honest residual)
- ~35% of archetype-label-years. The card is: *the label has abstained.* Fall back to chart
  personality + ownership habitat + mode; expect middling everything (our tables
  confirm). Do not force a story onto a name the classifier declined to type.

---

## 3. Chart-personality cards (with persistence tier)

- **smooth_compounder_grind** *(personality; co-fires with tight spreads, never
  with gap-risk)* — institutional program tape (PB-L2). Trust: pullback/base
  entries, multi-day drift. Distrust: deep-washout expectations, fade-the-drift
  trades. New-high exposure 11.6% of days — 52wk-high anchoring works *for* you
  under sponsorship.
- **stair_step_leader** *(personality, ~10d dwell)* — O'Neil habitat: valid-base
  breakouts on >150% volume, partial trims +20-25%, climax-top reclassification to
  distribution on record-volume verticals. Trust: RS-before-price, high-volume
  breakouts, 52wk-high proximity under institutional ownership. Distrust:
  mean-reversion fades. NOTE PB-L8: our engine structurally under-fires here —
  when it *does* fire on a leader, that scarcity is context.
- **volatile_momentum_vehicle** — rented tape (see high_beta_momentum card);
  entry timing strictness scales with hv percentile; post-event week is
  chart-blind (PB-L7).
- **mean_reversion_rubber_band** *(STATE, 3-day spike; 86% exits to mixed)* —
  react, don't plan: short-horizon reversal logic is legitimate only when the
  microstructure tier says liquidity provision dominates (PB-L9); on tight-spread
  names the snap is cost-eaten.
- **basing_accumulator** — the Weinstein/O'Neil accumulation habitat (lore-grade
  but mechanism-consistent): demand volume dry-up on red days inside the base,
  expansion on green; ≥5-week bases (favor 7+); under `long_only_sponsor` this is
  the highest-confidence breakout environment; under retail/tinderbox habitats the
  same shape is usually pre-squeeze consolidation, not accumulation.
- **event_gapper** — the calendar outranks the chart; PEAD-style drift is real
  only in the small/under-covered/costly corner; technical stops through known
  event dates are donations.
- **failed_breakout_trap** *(personality, stickiest at 35d dwell)* — Wyckoff
  upthrust habitat: breakout buyers are exit liquidity. First breakouts are
  suspect by default; only reclaim-after-shakeout earns trust. Highest-vol label
  with the deepest habitual pullbacks. Never a "second chance to buy."
- **defensive_range_stock** — range logic + macro/rate context; BAB seasonality
  (bid in risk-off, laggard in early recovery); do not import breakout logic.

---

## 4. Ownership-habitat cards (who is on the other side)

- **passive_index_magnet** — flow calendar ≻ fundamentals at reconstitution;
  inclusion pop is dead (PB-L1), deletion overshoot is alive (2-year reversion,
  balance-sheet filter mandatory); DMM/LULD Tier-1 status = trustworthy auctions,
  tighter halt bands; price discovery is *slower* under passive dominance —
  mispricings persist longer both ways.
- **etf_basketed_conduit** — check parent-ETF flow before reading single-name
  weakness (redemption pressure is mechanical and overshoots; premium/discount to
  NAV is the tell); ETF ownership raises volatility and co-movement (Ben-David et
  al.) — individual price moves carry less name-specific information.
- **long_only_sponsor** — the pullback-buyer habitat (PB-L2); 3+ quarters of
  rising 13F breadth = self-reinforcing herding trend (trust it); 3+ falling =
  don't catch it until breadth stabilizes; concentrated 2-3-holder books are
  *fragile* (Greenwood-Thesmar) — one redemption event moves the name.
- **insider_founder_controlled** — institutional mandates screen it out (float
  liquidity screens): thin two-sided books, deeper unbought pullbacks (8-15%),
  gap risk is the primary microstructure fact; a Form-4 buy after a pullback IS
  the sponsorship signal here; size down 30-50% vs sponsored comparables; never
  short float-starvation rallies.
- **short_interest_tinderbox** — a context modifier, never a direction signal;
  diagnose structural-short vs squeeze-candidate (fundamentals + DTC + borrow
  trend + float); >17-20% SI with DTC >3-5 = discontinuous-regime rules (PB-L10);
  threshold-list membership narrows dealer shorting exemptions — liquidity gets
  worse exactly when it matters.
- **retail_attention** — attention is a *fade* axis, not a confirmation axis
  (Barber-Odean; WSB peak-attention entries realize deeply negative episode
  returns): the tradeable moment is before the social-volume spike, the exit is
  volume-fade not price; institutional-flow tooling (13F reads, sponsorship logic)
  is structurally blind here — different instruments required.

---

## 5. Microstructure + mode notes (execution layer)

- **tight_spread_absorber** — levels and auctions are trustworthy; reversal edges
  are cost-dead; institutional programs leave readable footprints.
- **wide_spread_impact / slow_mean_reversion_liquidity** — dealer inventory
  half-life ~1 day (Hendershott-Menkveld): 1-2% adverse moves are often inventory,
  not information — stops belong outside the reversion band; short-term reversal
  logic is legitimately at home here (PB-L9); Corwin-Schultz *understates* true
  spreads on exactly these names — assume one tier worse than labeled.
- **gap_discontinuity_risk** — the operator sizes for the LULD band the name actually trades in (Tier-2
  = 10%); no market orders near limit states; halts + reopen auctions are the tape.
- **options_pin / negative_gamma_trend** — pin gravity binds within ~1-2% of heavy
  OI strikes into expiration and 0DTE pins bind only in the last hours and reset
  daily; single-name GEX is meaningful only with deep options ADV — treat thin-name
  gamma modes as suggestive; in negative-gamma trends do not fade — dealers are
  trend-amplifying until positioning flips (PB-L10).
- **squeeze / forced_liquidation / event_override / post_news_attention /
  stale_dead_money** — the fast layer exists to *suspend* the slow playbook:
  squeeze = time-stops not price-targets; forced_liquidation = mechanical supply
  (and the momentum-crash long setup when it resolves post-panic); event_override
  = chart authority suspended; post_news_attention = strength is contaminated for
  days; stale_dead_money = the patience cost is the position.

---

## 6. Integration (display-tier, per house law)

- **UI:** each label chip on the stock page carries its card's one-line treatment
  (EN/ZH) — the operator reads the doctrine at the point of decision.
- **Species:** the cards name which of our species families are *designed* for
  each type (washout/reversal species ↔ rubber_band micro-tiers and repair bases;
  reclaim species ↔ trap shakeouts; RS/base species ↔ leaders and accumulators) —
  context beside fires, never a gate.
- **Cortex/NW:** the playbook is citable context for de-escalation only (LLM law).
- Nothing in this document ranks, sizes, or gates. Promotion of any doctrine line
  into mechanics goes through pre-registration — with rulers derived FROM these
  claims (the understanding-first law).

## 7. Chartered follow-ups (from the completeness critic + PB-L8)

1. **Per-type sizing/risk conventions** (vol-targeting, ADV-based caps) — the one
   playbook layer institutions codify that we have not.
2. **Dilution/lockup calendar** (lockup expiries, ATM/shelf overhang, convert
   hedging) — dominant supply events for spec/insider types; buildable from EDGAR.
3. **Tax-loss/January seasonality by type** — mechanical Q4 headwind + January
   rebound in prior-year losers (broken_growth/spec).
4. **Cross-type book construction** — crowding overlap and factor netting (a book
   of "different" names can be one latent trade).
5. **Borrow-side data** (CTB, hard-to-borrow, threshold list) — the missing
   actionability axis for tinderbox treatment.
6. **Sector-specialist calendars** (PDUFA/data readouts, FFO conventions, stress
   tests) — the specialist ruler for rate_sensitive/biotech-adjacent types.
7. **PB-L8 coverage question** — why the gate cascade under-fires on leaders and
   compounders at high tiers; whether a leader-compatible species is a gap in the
   species roster (routes through the species program's monthly review).

## 8. Honesty block

Field-guide numbers are from the 223-name survivorship-flagged deep corpus (some
cards lean on 3-6 name cells — flagged in the field guide). Literature effect
sizes carry post-publication decay (assume 30-50% haircuts). Practitioner-lore
claims (base statistics, breakout follow-through percentages, junk-rally clocks)
are flagged as lore: mechanism-plausible, effect-size-unaudited. The Phase-0
compat study's printed null (0/40 cells on P(STOPPED) at the species rulers)
constrains one specific claim family — that labels shift *setup safety outcomes* —
and says nothing about the interpretive value codified here. Where this playbook
generates testable claims, they enter ledgers as pre-registered studies with
rulers derived from the claim, per the understanding-first law.

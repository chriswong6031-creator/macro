# PSS §4 brainstorm — W-SIG shortlist (durable-reset identification families)

Status: SYNTHESIS OF RECORD (Fable main loop, 2026-07-25). Executes
`research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md` §4. Panel: 7 opus
reviewer lenses (workflow `pss-s4-brainstorm-panel`, 33 candidates, every one
12y-testable from daily OHLCV) + 1 opus DNR/blocklist cross-checker (5 clear /
21 adjacent-needs-distinction / 4 duplicate-of-seed / 3 duplicate-in-panel).
Fable synthesis rule: one representative per redundancy cluster; earliness with
2022 containment; measurement-first axis quality; personality differentiation
(the operator's "different tools for different stock types"). The five CLEAR
verdicts and the cluster analysis converge on the same five constructions —
four families + one shared gate.

Copy law (R-W1T-3) governs all of it: candidate language is exhaustion /
reset-confirmation / terminality — no construction here "calls bottoms"; each
one detects a component of seller exhaustion and must prove its earliness claim
on the timing ruler (charter §7).

## The W-SIG slate (≤4 families; each gets ONE prereg on the standard rails)

### F1 — Down-volume envelope decay (forced-supply exhaustion on new lows)
Rank 1: the purest durable-reset mechanism (a durable low IS supply exhaustion);
pre-trough; STRUCTURALLY silent in the 2022 failure class (down-volume was
rising into every 2022 leg). Lens: flows. Panel id C6.

**Mechanism.** Forced sellers — margin calls, tax-loss, fund redemptions, index-deletion flow — are a FINITE inventory; a durable bottom is where each successive new-low bar prints on LESS down-day dollar volume because the seller cohort is emptying, so supply dries up BEFORE demand arrives, which is precisely why this fires early.

**Construction (sketch, prereg pins the final form).** From daily OHLCV: isolate the sequence of lower-low bars in the decline; fit the slope of down-day dollar volume across those new-low bars over the per-name window. Fire when new lows are being made on a NEGATIVE down-volume slope (contraction) — no-supply-on-new-lows. Entry at the first new-low bar whose down-volume is below the decayed envelope. Compose with the reversion rung as a confirmation gate, not a score.

**Per-name measurement axis (codex column).** Per-name down-volume PERSISTENCE HALF-LIFE: the decay constant of the autocorrelation of down-day dollar volume (how many bars a selling cohort in this name typically takes to empty). The half-life sets the envelope-fit window and the slope-significance bar; names with short half-lives (fast-clearing supply) get shorter windows.

**Personality scope.** Should work on names that bottom via seller-exhaustion rather than event-reversal: liquid mega/large-caps with orderly forced-selling cohorts (AAPL MSFT GOOGL META HD JPM XOM; basing_accumulator). Should FAIL on names whose bottoms are single-gap event reversals (earnings/headline-driven volatile_momentum_vehicle: NVDA TSLA around catalysts) where supply does not decay gradually, and on ever-liquid defensives (KO PG) whose declines are too shallow to generate a measurable down-volume envelope — accept as loss.

**Falsifier (pre-stated).** Pre-stated kill: if new-low bars with a contracting down-volume envelope do not precede the MAE-minimizing / within-5%-of-low entry more often than a RANDOM new-low bar in the same decline (per-name base rate, cluster-bootstrapped, α/m), the exhaustion signature is illusory and it dies. Era-split (pre/post-2021) required — a full-sample-only effect is disqualified.

**2022-class containment.** This is the explicit anti-2022 candidate: in the 2022 catastrophes down-volume was ELEVATING into each new low (fresh forced supply per leg), so a contracting envelope is absent and the detector is SILENT there by design. The contraction requirement IS the discriminator against early fires in sustained downtrends — the failure class cannot trigger it.

> **VERDICT (executed 2026-07-25, `reports/pss_f1_downvol.md`, family `pss_f1_downvol`): KILLED as a standalone timer — falsifier not cleared.** Coverage 943/1300 eligible. F1's near-low rate is real (U_W5 vs all-days +23..+35pp, both eras) but GENERIC to new-low conditioning: the treatment-disjoint complement of ordinary new-low bars gets the SAME +23..+34pp, and F1−complement straddles 0 on both U_MAE and U_W5 in both eras (gated and ungated). The contracting envelope carries no incremental MAE/proximity information. The 2022-containment prediction also did not hold per-name (JPM 7 / META 9 H1-2022 fires vs 2–3 near the Oct low). Down-volume persistence half-life is RETAINED as a codex measurement axis and a candidate W-CONF confluence input; the volume-exhaustion search space is not closed. DNR §2 row added (scoped to the standalone construction). Errata E1 (per-name-first estimator conformance — the initial −7pp U_W5 was a pooled-median-of-a-binary artifact) and E2 (RNL null decontamination) applied post-review; deterministic rerun reproduces byte-identical.


### F2 — Overnight-vs-intraday return decomposition flip (who is selling)
Rank 2: a genuinely new decomposition axis nothing in the estate reads
(overnight fear leg vs session accumulation leg decouple before the net daily
return turns); pre-trough with its 2022 exposure carried openly behind the
non-accelerating-ATR veto analog. Lens: microstructure. Panel id C4.

**Mechanism.** Daily OHLC separates the overnight jump (open/prior_close) from the intraday drift (close/open). In a healthy downtrend BOTH legs are negative (gap down, then bleed down). At a durable low the two DECOUPLE: overnight stays negative (fear still gaps it down at the open) while the intraday leg turns persistently POSITIVE (buyers accumulate all session and close it up off the open) — the composition of the day inverts before the net daily return does, so it precedes the level turn the oscillator waits for.

**Construction (sketch, prereg pins the final form).** Per name: overnight_ret = open/prior_close-1; intraday_ret = close/open-1. Signal = rolling window where median overnight_ret stays <0 (fear at the open persists) AND median intraday_ret flips >0 and exceeds the name's quantile (session accumulation), for K bars at the reversion rung. Fully OHLC-derivable; a genuinely EARLY read because the intraday leg can flip while net daily returns and the smoothed oscillator are still falling.

**Per-name measurement axis (codex column).** the name's own overnight/intraday return-split distribution and its baseline intraday-leg volatility (a bars-derived 'how much of MY daily move is gap vs session' parameter) — sets the flip threshold and K per name

**Personality scope.** Strongest on institutionally-accumulated mega-caps where session buying is a real distinct force (AAPL MSFT AMZN GOOGL UNH HD COST). Should FAIL on names dominated by overnight/headline gaps with little session structure (some TSLA/NVDA regimes are all-gap, intraday leg is noise) and on thin defensives where the open/close split is microstructure noise. It reads the presence of a session accumulator — silent where there isn't one.

**Falsifier (pre-stated).** Pre-registered kill: if the overnight-negative / intraday-positive decoupling window sits no earlier and no closer to the trough than net-daily-return momentum (i.e. the decomposition adds nothing over just watching close-to-close), the split carries no information and it dies. Hard requirement: the earliness claim must be validated as td_to_trough strictly earlier than the Stoch-RSI cross on the same names, or the 'pre-trough' claim is retracted to at/post.

**2022-class containment.** This is the candidate MOST exposed to the 2022 early-fire class because it explicitly claims pre-trough firing — so it carries the risk knowingly and imports the mitigation as a hard gate: fire ONLY when the intraday-leg flip is accompanied by a NON-accelerating multi-bar ATR (the accelerating-tightening/expansion veto analog from the incumbent), because in 2022 the intraday leg's brief green flips came amid still-accelerating range. Without that veto it will fire into downtrends; WITH it, it must prove it retains earliness. If the veto removes all the earliness, the candidate is honestly null.


### F3 — Idiosyncratic residual reset (beta-stripped own-flush exhaustion)
Rank 3: the deepest personality content in the panel — it operationalizes
systemic-vs-idiosyncratic bottoms as a per-name, per-episode distinction and is
silent by construction in systemic flushes (which is why 2022 cannot fire it);
pre-trough. Needs sector-ETF benchmark series (available, deep history). Lens:
cross-asset. Panel id C19.

**Mechanism.** At a durable idiosyncratic bottom the name's forced/discretionary sellers exhaust while the market tide is still going out, so the beta-stripped RESIDUAL (name return minus its rolling beta times benchmark return) prints its capitulation and turns up BEFORE the raw price low, because the price is still being dragged by a falling benchmark it no longer leads down.

**Construction (sketch, prereg pins the final form).** Per name: rolling OLS beta vs its GICS-sector ETF (data/sector_holdings membership -> XLK/XLF/XLE... series in data/yahoo, deep history) estimated on a trailing window; daily residual r_res = r_name - alpha - beta*r_bench; build cumulative residual drawdown from its trailing residual high. Signal = residual-drawdown reaches a per-name z-extreme AND the residual makes a higher-low / turns up (residual momentum sign flip) while the RAW price drawdown is still deepening or flat. Fires only when residual and systemic components DISAGREE (residual recovering, benchmark still down). Compose: emit only at the name's structure-derived rung from the codex; confluence-GATE with Stoch-RSI reset-confirmer, never blend scores.

**Per-name measurement axis (codex column).** Per-name residual-return autocorrelation / half-life at the ladder of bar sizes (same rho-ladder machinery as W1b structure-measurement, computed on the RESIDUAL series not raw) -> the bar size where residual mean-reversion is strongest is the rung; plus the trailing beta-estimation window length chosen by residual-fit stationarity (split-era beta drift score). Both bars-derivable, no event fitting.

**Personality scope.** Should work on high-idiosyncratic-variance names whose drawdowns are stock-specific: TSLA, NVDA, META, and single-name-headline defensives (JNJ litigation, UNH, PG). Should FAIL (stay silent, correctly) on names whose drawdowns are almost entirely systemic/high-R^2-to-benchmark (KO, PG in broad selloffs, index-like MSFT during macro flushes) where there is no residual to lead the price -- and that silence is the feature, not a miss.

**Falsifier (pre-stated).** If, on the focus names, residual-turn fires do NOT beat the per-name random-day within-5%-of-low base rate on the timing ruler, OR their MAE-to-trough is no shallower than the raw Stoch-RSI reset-confirmer, OR the fires cluster in HIGH-R^2 (systemic) windows rather than low-R^2 (idiosyncratic) windows, the mechanism is dead. Pre-stated: residual-lead should concentrate where trailing name-benchmark R^2 is in its own lower tercile.

**2022-class containment.** Avoids the early-fire-in-downtrend class BY CONSTRUCTION: 2022 mega-cap troughs were SYSTEMIC (names fell WITH a falling benchmark, high R^2, residual not leading), so the disagreement gate stays shut through the 2022 downtrend and only opens when the systemic component itself turns -- it structurally cannot fire the 2022-catastrophe pattern because that pattern has no idiosyncratic-residual-up / systemic-down signature.


### F4 — Downside-vol asymmetry flip (semivariance regime turn)
Rank 4: at-trough; the cleanest distinct vol-object among five second-moment
candidates (asymmetry ratio ≠ vol level ≠ vol-of-vol); honest per-name
eligibility gate (baseline-symmetric defensives are declared out of scope
rather than mis-graded). Lens: vol-structure. Panel id C10.

**Mechanism.** A falling stock is dominated by DOWN-day variance (semivariance): the tape is one-sided as sellers hit bids. A durable trough is the bar where that asymmetry INVERTS — down-vol stops leading and up-day variance draws level or exceeds it — because the marginal seller is gone and buyers now set the range; a dead-cat bounce raises up-vol transiently but down-vol re-dominates within days (asymmetry snaps back), whereas at a real bottom the symmetry PERSISTS.

**Construction (sketch, prereg pins the final form).** Per name: rolling downside semi-deviation RV_down and upside semi-deviation RV_up over window n. Asymmetry ratio A = RV_down / RV_up. Fire when A crosses from >=A_hi (down-dominated, its own trailing high band) down through ~1 (symmetric) AND stays <=1 for at least P consecutive bars (persistence gate that kills dead-cats). Signal = first bar of the sustained-symmetric run. Semivariances are pure close-to-close; ratio and bands are per-name trailing percentiles (PIT).

**Per-name measurement axis (codex column).** per-name baseline asymmetry A_base and its dispersion, measured over FIT — some names (defensives) live near A≈1 always (no signal content, correctly excluded by a min-baseline-asymmetry eligibility gate), while high-beta names run structurally down-skewed in drawdowns; A_hi is set as the name's own trailing upper percentile of A, and the persistence length P is scaled by the name's vol-cluster timescale (same axis as candidate 1).

**Personality scope.** Should work on names that trade with strong directional-vol asymmetry in selloffs — beta>1 mega-caps and cyclicals (NVDA, TSLA, AMZN, JPM, XOM, HD). Should be NULL and excluded on names with A≈1 at baseline (KO, PG, WMT, COST — low-drama defensives whose down-vol never dominated), where the flip has no signal. Also should not work where down-vol is chronically elevated regardless of trend (correctly filtered by requiring a prior down-dominated regime to flip FROM).

**Falsifier (pre-stated).** If the sustained-symmetric-run start date does not beat the per-name random-day within-5%-of-low base rate (charter §7: ~16% ambient) at CI-clean margin, OR if requiring persistence P pushes the fire so late that td_to_trough is no better than the incumbent's -2..-10 (i.e. it collapses into another reset-confirmer with no earliness gain), it is dead.

**2022-class containment.** The persistence gate (P consecutive symmetric bars) is the 2022 defense: in the 2022 bears, brief symmetry patches during relief bounces re-inverted to down-dominance within a few bars, so a sufficiently long P never triggered until the true trough — the early-fire failures were precisely the un-persisted single-bar reads. Tuning P too short re-imports the failure class; grade P on the era-split (2021+) MAE tail to pin it.


## The shared guard — decline-deceleration terminality gate (C32)

NOT a fifth family: a GATE measurement added to the codex and carried as a
pre-registered conditioner column in ALL FOUR family preregs (and available to
W-CONF as a gate condition, never a score). The ground-truth lens measured the
need directly on 2022 bars: raw stretch fired 18× in H1-2022 vs 2× near the
October low; a swing-reclaim construction fired 265× vs 74 — no early family
survives 2022 without a terminality condition, and deceleration-into-a-fresh-low
is the only candidate that is structurally FALSE during a constant-slope
descent. Each family prereg grades its results WITH and WITHOUT the gate
(pre-stated column, not post-hoc): the gate earns its place only if it cuts
downtrend false fires by a large margin while retaining near-trough coverage.

**Mechanism.** A sustained downtrend keeps making new lows at a roughly constant or accelerating pace; a durable low is preceded by the RATE of decline flattening — successive lower lows come at a decelerating slope and the 20d rate-of-change stops deepening even as price grinds lower — because the marginal seller is drying even while the last forced supply prints the final low.

**Construction (sketch, prereg pins the final form).** Per name from closes: roc20=20d return; measure the SLOPE of the rolling low sequence (e.g. regression slope of 10d-min over the last M bars) and whether roc20 has stopped making new negatives (roc20[today] > min(roc20[-20:]) while price <= 60d low). Fire the GATE true only when the decline is decelerating INTO a fresh low. This is the missing piece I proved is required: raw stretch (T2) fired 18x in H1-2022 vs 2 near the low; the swing-reclaim fired 265x vs 74; NEITHER is downtrend-safe alone. Deceleration is the only context that is structurally FALSE during a constant-slope descent and only turns TRUE as it terminates.

**Per-name measurement axis (codex column).** Per-name deceleration lookback M and the roc horizon set from the name's own typical down-leg duration (autocorrelation-derived, composing with the structure rung) — fast-moving names get a short M, slow grinders a long M.

**Personality scope.** Universal as a GATE across all focus names (it only ever narrows, never originates). Most valuable on the grinding/rounded bottoms (2022-10, 2023-10) where climax-reclaim (candidate 3) has zero coverage — deceleration is visible on grinds that have no climax bar. Least informative on instant one-bar gap bottoms where there is no multi-day decline to decelerate.

**Falsifier (pre-stated).** Killed if conjoining the deceleration gate with candidates 1-3 does NOT cut the H1-2022 downtrend false-fire counts I measured (15/18/265) by a large margin while retaining near-trough coverage — i.e. if deceleration is present just as often mid-downtrend as at terminal lows (directly testable on the 2022 tape). If it cannot separate the Oct-2022 low from the June-2022 low, it dies.

**2022-class containment.** This candidate exists specifically to defuse the 2022 early-fire class: it is the pre-statable filter that must turn the early triggers' downtrend false-fires off. Its own risk is being too strict and suppressing real early fires (raising lateness back toward the incumbent) — that trade-off (earliness vs 2022-safety) is the honest frontier this whole search sits on, and it must be graded, not assumed.


## Why these four (and what they deliberately span)

Four independent mechanism channels — volume (F1), session composition (F2),
cross-sectional residual (F3), vol asymmetry (F4) — so the later W-CONF
2-of-N confluence test has genuinely uncorrelated legs, alongside the validated
incumbent (Stoch-RSI at the structure-derived rung, the late-but-safe
reset-confirmer). Personality coverage is complementary by design: F2 reads
institutionally-accumulated mega-caps, F1 reads orderly forced-selling cohorts,
F3 reads idiosyncratic-variance names and correctly goes silent on systemic
flushes, F4 reads high-beta down-skewed names and excludes low-drama
defensives at eligibility. Names none of them cover are accepted losses per
the operator's ruling ("if it's untradeable, it's fine").

## Panel disposition — all 33 candidates

Verdicts by the DNR/blocklist cross-checker (opus). Non-shortlisted candidates
are NOT killed — they enter the foundry pool (`research/foundry/LENSES.md`
process; rejected-with-reason rows become brainstorm memory per masterplan
W-FOUNDRY step 3).

| id | lens | candidate | earliness | verdict | reason (abridged) |
|---|---|---|---|---|---|
| C0 | microstructure | Down-day range-expansion elasticity collapse | at-trough | adjacent-needs-distinction | Rhymes with C10 'Terminal vol-expansion → compression handoff' (vol-structure) — both key on range/v |
| C1 | microstructure | Failed-breakdown reversal-bar cluster | at-trough | duplicate-of-seed | Deepening of the seeded undercut-and-reclaim, and the panel already carries three undercut-reclaim d |
| C2 | microstructure | Exhaustion-gap absorption | at-trough | duplicate-in-panel | Same construction as C19 'Downside-exhaustion gap reclaim' (behavioral): per-name down-gap detection |
| C3 | microstructure | Lower-tail-shadow accumulation ladder | at-trough | adjacent-needs-distinction | Measures the same intrabar-position object as C13 'Range-expansion exhaustion via close-location-in- |
| C4 | microstructure | Overnight-vs-intraday return decomposition flip | pre-trough | clear | No registry row: overnight_ret=open/prior_close−1 vs intraday_ret=close/open−1 decomposition is a di |
| C5 | flows | Absorption at the low | at-trough | adjacent-needs-distinction | Its own falsifier correctly pre-registers against BL-017/BL-G060 cn_supply_absorption ('price-only a |
| C6 | flows | Down-volume envelope decay | pre-trough | clear | Distinct construction: down-day dollar-volume CONTRACTING across successive lower-low bars (no-suppl |
| C7 | flows | Up/down dollar-volume participation reversal | at-trough | adjacent-needs-distinction | Deepens the real engine feature updown_dollar_vol_ratio (winner_autopsy.py:1065 — citation verified) |
| C8 | flows | Dollar-volume regime shift = climax flush + participation  | post-trough-confirm | duplicate-of-seed | Explicitly a deepening of the seeded volume-capitulation family. It is materially sharper than the s |
| C9 | vol-structure | Terminal vol-expansion → compression handoff | at-trough | adjacent-needs-distinction | Shares the ACF-of-/returns/ vol-cluster-timescale measurement family with C12 (vov collapse) and C14 |
| C10 | vol-structure | Downside-vol asymmetry flip | at-trough | clear | Down/up semi-deviation ratio A=RV_down/RV_up crossing through ~1 with a persistence gate is a distin |
| C11 | vol-structure | Vol-of-vol collapse gated on a completed down-flush | at-trough | duplicate-of-seed | Deepens the seeded vol-of-vol-collapse family and is materially sharper: (i) daily-bar-derived per-n |
| C12 | vol-structure | Range-expansion exhaustion via close-location-in-range rec | pre-trough | adjacent-needs-distinction | Same intrabar-position object (CLR = (close−low)/range) as C4 'Lower-tail-shadow accumulation ladder |
| C13 | vol-structure | Vol-persistence break: GARCH-style shock-memory decay coll | at-trough | adjacent-needs-distinction | Reads the SAME ACF-of-squared-returns object as C10 (RV level) and C12 (vov = std of RV) — panel tex |
| C14 | behavioral | Anchored-underwater release | at-trough | adjacent-needs-distinction | Rhymes with PM1 (DNR line 78 / BL-G042 'AVWAP-from-base-low distance', FALSIFIED phase-0 as a standa |
| C15 | behavioral | Undercut-and-reclaim, absorption-sharpened | at-trough | duplicate-of-seed | Deepening of the seeded undercut-and-reclaim; the sharpening (supply-exhaustion down-volume ratio ≤  |
| C16 | behavioral | Drawdown-duration exhaustion | at-trough | adjacent-needs-distinction | Same measurement axis as C27 'Drawdown-duration maturity by personality class' (seasonality): per-na |
| C17 | behavioral | Prior-shelf / round-number defense | at-trough | adjacent-needs-distinction | Its own text flags the PM2/PM4 adjacency and PM4 is a registry kill (DNR line 80 / BL-G044 'overhead |
| C18 | behavioral | Downside-exhaustion gap reclaim | at-trough | duplicate-in-panel | Same construction as C3 'Exhaustion-gap absorption' (microstructure): per-name capitulation down-gap |
| C19 | cross-asset | Idiosyncratic residual reset | pre-trough | clear | Beta-stripped residual drawdown + residual momentum turn while raw price still falling is a distinct |
| C20 | cross-asset | Systemic-vs-idiosyncratic drawdown decomposition router | at-trough | adjacent-needs-distinction | A router/gate that selects which pre-validated family may fire per episode (systemic-share vs idiosy |
| C21 | cross-asset | Down-capture collapse | pre-trough | adjacent-needs-distinction | Downside-beta (beta on benchmark-negative days) collapsing while benchmark still net-negative — a di |
| C22 | cross-asset | Peer-cohort trough clustering | pre-trough | adjacent-needs-distinction | Two adjacencies it must clear. (1) rs member-dispersion / rs zero-sum tautology (DNR line 38 / BL-02 |
| C23 | cross-asset | Beta compression + relief snapback | at-trough | adjacent-needs-distinction | Rolling-beta peak-and-compress (correlation-to-one deleveraging then de-correlation) overlaps C22 'D |
| C24 | seasonality-time | Tax-loss exhaustion clock | at-trough | adjacent-needs-distinction | Two rows to distinguish. (1) RIC-R3 (DNR line 52 / BL-G021): calendar/event windows are FORBIDDEN as |
| C25 | seasonality-time | Post-earnings information-vacuum floor | at-trough | adjacent-needs-distinction | Adjacent to RIC-R3 (DNR line 52 / BL-G021, calendar windows forbidden as state-advancing legs, permi |
| C26 | seasonality-time | Drawdown-duration maturity by personality class | post-trough-confirm | adjacent-needs-distinction | Same measurement axis as C17 'Drawdown-duration exhaustion' (behavioral): per-name empirical drawdow |
| C27 | seasonality-time | OPEX-cycle supply-relief phase as a rung-tie-breaker | post-trough-confirm | adjacent-needs-distinction | Directly names and is governed by RIC-R3 (DNR line 52 / BL-G021): OPEX-as-leg is explicitly forbidde |
| C28 | tape-at-real-resets | Climax-lead volatility-regime flip | at-trough | adjacent-needs-distinction | OHLC-range version of the expansion→contraction handoff that C10 'Terminal vol-expansion → compressi |
| C29 | tape-at-real-resets | Swing-pivot undercut-and-reclaim | at-trough | duplicate-in-panel | Duplicate of C2 'Failed-breakdown reversal-bar cluster' (microstructure): both are PRICE/RANGE-ONLY  |
| C30 | tape-at-real-resets | Reclaim-of-climax-high expansion bar | at-trough | adjacent-needs-distinction | Reclaims the wide down CLIMAX bar's HIGH on an expansion up-bar — a distinct quantity from undercut- |
| C31 | tape-at-real-resets | Personality-scaled stretch-snap fuel gate | at-trough | adjacent-needs-distinction | dev=close/SMA50−1 deep-stretch band is close kin to the extension/distance metrics the registry foun |
| C32 | tape-at-real-resets | Decline-deceleration terminality gate | pre-trough | clear | Rate-of-decline flattening (rolling-low-slope + roc20 stops making new negatives into a fresh low) i |

Notable dispositions:
- **Seed deepenings recorded** (upgrade the seed definitions if those seeds
  later earn preregs): C8 two-part climax-flush + participation-persistence
  (volume-capitulation seed); C11 vov-collapse gated on a completed down-flush
  (vol-of-vol seed); C15/C1/C29 absorption-sharpened undercut-and-reclaim with
  name-relative close-location (undercut-reclaim seed — three independent
  panel derivations converged on the same sharpening, which is evidence the
  sharpening is real).
- **Adjacency discipline**: every adjacent-needs-distinction candidate that
  reaches a prereg MUST carry a distinctions block naming the registry row it
  rhymes with (MWR §6 precedent). The checker's reasons are the seed text.
- **Router (C20)** is W-CONF material (tool-selection gate), not a family.
- **Calendar candidates (C24/C25/C27)** survive only as tool-selection /
  display context per RIC-R3 — never state-advancing legs.

## Execution rails (binding, from masterplan §0/§2)

Each family: wrong-ruler check in the script header BEFORE statistics; ONE
mechanism hypothesis; trial-ledger family registered pre-outcome
(`pss_f1_downvol` … `pss_f4_semivar`); timing ruler (MAE primary, proximity
co-primary, per-name random-day nulls); era split DT-R16; month-cluster
bootstrap DT-R14; small pinned grid disclosed as the multiplicity budget; the
C32 gate as a pre-registered conditioner column; earliness claim graded as
td_to_trough vs the incumbent on the same names; display-tier until gauntlet.
No per-name best-of-grid selection anywhere (two-ruler kill row governs).

Next actions: F1 prereg first (rank 1, simplest construction), then F2-F4 as
separate preregs; codex (W2, building now) carries the measurement axes.

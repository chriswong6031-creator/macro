# Amendment 3 — Candidate Book DRAFT (Fable first-principles brainstorm, pre-red-team)

**Status: DRAFT — not ratified, not registered. This document is the raw brainstorm input to the
Amendment-3 red-team round. Nothing here may be computed against the fire tape until the
amendment is ratified and families are registered.**

Operator directive (2026-07-06): expand the entry stack with (a) additional momentum-category
factors — e.g. 2W / 1M StochRSI washout (HTF washout) and other MACD/RSI/StochRSI variants or
confluence pairings — and (b) additional non-momentum technicals and their confluences. First
principles first, then test.

---

## 0. The verdict lattice this brainstorm must respect (read before adding ideas)

Binding kills / hostile priors (do NOT re-derive; R2 adjacency law applies):

| Prior | Verdict | Source |
|---|---|---|
| Multi-TF stoch **washout DEPTH** behind a fire (incl. 2W deep) | **H1 FAIL** — +2.9pp clean15 but +3.5pp stop5; `w2_deep ≈ 0 alone`; depth works only through the cohort lens (H6→COILED) | DURABLE_BOTTOM §8 ledger, WAVE1_REPORT §2 |
| Washout **age + calm base** (incl. "old low", ATR crush) | **H2 FALSIFIED wrong-sign** — worst stop-outs in program (46–48%) | same |
| Volume confirmers (OBV-div, dry-up, up/down ratio, capitulation spike) | **H4 FALSIFIED** | same; ESX RUL-1 |
| Trap-context veto (monthly RSI-MACD falling, % below 200MA, failed-fire count) | **H5 FAIL**; failed2 BACKWARDS (serial failure = mean-reversion fuel, in-sample) | same |
| Trend/location guards; CT-LANE not-worse | FALSIFIED as per-event filters (exposure artifact) | CONFLUENCE_TUNING §5b/§9.2 |
| Deep (<20) vs shallow StochRSI cross at fire TF | shallow NOT worse (36.1 vs 41.8 stop-out) — recent violence predicts stops | TIERED_CASCADE §4 |
| Raw washout depth (>18% below 200MA) as boost | knife-risk; only deep×REVERSING wins (+26pp held21, state-level) | BOTTOM_CONFIDENCE Ph1-2 |
| "More oscillators don't help; confirmation depth + orthogonal/higher-TF context do" | BOTTOM_CONFIDENCE Result 4 | binding style prior |
| Tier/freshness subsetting (NC-1) | NULL both panels | W1_NC |
| S-UR spring reclaim | standalone + ∩COILED WORSE on stop5; gatefire form nullified by NC-2 proximity de-confounding | W2_SUR |
| ADX rising-vs-low stratum (S-TS) | expect-null pre-registered (confirm final verdict from report) | W1_STS |
| KST/multi-ROC, Fib/Elliott/candles, VWAP-on-daily | dropped (collinearity/subjectivity) | masterplan §9 |

Live incumbents every candidate must beat or be marginal to:
- **NC-2 proximity** (63-bar close-min proxy): −4.3pp (deep) / −10.1pp (baskets) stop5 at ~34% recall — the S-UR killer. Every A3 family carries a mandatory NC-2-proxy band-FE marginality arm in its PRIMARY read.
- **COILED** (H6 cohort-washout × H3 divergence composite): +7.54pp clean15 / −5.64pp stop5 OOS.
- **S-EV earnings blackout** hygiene (+8.7pp stop5 degradation inside window).

Supportive state-level priors (motivate but do not validate):
- Weekly TURN adds +19pp held21 (68.4 vs 49.0) at state level; deep×reversing +26pp; **4-TF turn-confluence count monotone 43.7→61.4%** (BOTTOM_CONFIDENCE Ph1-2, 68,916 evals — state-level, held21, NOT fire-conditional, NOT ESX grader).

**Census-verified additions to the lattice (2026-07-06 workflow wf_eb240cc2):**

| Prior | Verdict | Source |
|---|---|---|
| Bullish divergence STANDALONE (H3 without cohort) | **actively BAD** (clean15 31.63 vs 32.60; stop5 48.46 vs 44.54) — works only as co-condition inside COILED | DURABLE_BOTTOM:343 |
| Weekly stoch washout→turn as standalone SECTOR-ETF trigger (P-W1) | **NULL** (0.45% exc @63d < 1.1% boring baseline; BH fail) — sector-level, return-alpha ruler (later ruled wrong ruler for reversion class) | ORACLE_GAUNTLET_P8_RESULTS |
| Monthly stoch washout→turn sector trigger (S-W3) | NULL/negative (−0.86% @63d, hit 43.7%) | same |
| F7 weekly-stoch-turn stratum on BLOCKED (counter-trend) population | **NEAR-MISS** +1.47/+1.55/+2.78pp clean15 all 3 panels, sign-stable, stop not-worse — only leg favorable everywhere; but collapses to ~0 inside ¬bear_ctx (bear-context confound) | WAVE6_REPORT §3.1/§3.3 |
| W8-A W-ARM (weekly RSI-MACD hist approaching zero-cross, stale-cross population) | FAILED OOS ticker-half stability — ARMED chip not shipped | DURABLE_BOTTOM W8 ledger |
| W8-B SHAKEN (undercut >1.5ATR + midpoint reclaim + weekly hist NET-RISING, stale population) | **SHIPPED** (stop5 −4.59pp both panels) — the weekly-motion ingredient rides inside a shipped chip | same |
| H5 monthly RSI-MACD *falling* as trap veto | FAIL (≈0, unstable) | DURABLE_BOTTOM ledger |
| Bottom-confidence TF weights | W dominant (0.45) vs M (0.15); "+19pp weekly vs +4pp monthly" state-level | engine/cycles.py:1870 |
| 2W-turn timing case anatomy | "measured catastrophically late" (MCD lead 80d) | WAVE6 §case studies |
| CN-WASHOUT species (2W stoch washout in CN setup tiers) | VALIDATED gate_weight — but CN market only; CN≠US porting is bidirectionally suspect | species registry; setup_tier.py |

Structural fact: **the gate already conditions on weekly RSI-MACD state** — `confirm3 = (weekly
RSI-MACD bullish) OR (3D stoch recently oversold)` (confluence_tiers.py:195), and T1's buy-filter
carries similar weekly gates. So a weekly-STATE stratum partially decomposes the gate's own OR-leg
admission structure; new information lives in weekly/2W/1M **histogram slope (motion)**, which the
gate does not read. Any A3 study must print the admission-leg decomposition as context.

The one-sentence lesson of the lattice: **at fire time, cycle-scale POSITION (depth/age/location)
is dead or NC-2-confounded; cycle-scale MOTION (turn evidence) is a near-miss/validated-ingredient
at state level, on blocked populations, and inside shipped chips (SHAKEN) — but never adjudicated
on the gate-fire tape itself.** Amendment 3's momentum lane therefore targets HTF motion, not HTF
position — and every family must survive proximity de-confounding (the S-UR killer) and cite the
bear-context-confound lesson (the F7 ¬bear_ctx collapse).

---

## 1. Momentum-category candidates

### A. esx_htf_turn — HTF oscillator TURN state at fire (flagship)

Mechanism: the gate's 2D/3D cross proves the *daily-swing* degree turned. Whether the *cycle*
degree (weekly / 2-week / monthly) has begun turning is separate information about seller
exhaustion at the scale that produces durable bottoms vs trap bounces. State-level evidence says
this is where the washout thesis actually lives (weekly turn +19pp; turn-count monotone). Never
tested fire-conditionally.

Frozen-definition sketch (to freeze exactly at registration; leak law = last **completed** HTF bar
whose known-date ≤ fire date, via the incumbent known-date machinery — reuse
`engine/oracle/oscillators.resample_weekly_leakfree` / `confluence_tiers._tf_bars` pattern; math
pinned to the faithful port: RSI-MACD = EMA(RSI14,14)−EMA(RSI14,60) sig EMA5;
StochRSI = `_stoch_rsi_kd` 14/3/3 K&D — never `cycles.stoch_rsi` K-only, never price `macd_parts`):
- A1 `w_hist_rising`: weekly RSI-MACD histogram net-rising (h_last > h_{last−1}) on known weekly bars.
- A2 `w2_stoch_turn`: 2W StochRSI K>D on latest known 2W bar AND K rising (K_last > K_{last−1}).
- A3 `m_hist_rising`: 1M RSI-MACD histogram net-rising on known monthly bars (never-included rung).
- Contrast each vs complement. Free context column (no inference): gate admission-leg decomposition
  (weekly-bull leg vs fromos3 leg per confluence_tiers confirm3).

Adjacency (R2): H1 depth FAIL (this is motion, not position); F7 WAVE6 near-miss on the BLOCKED
population incl. the ¬bear_ctx collapse (different population — our tape is ELIGIBLE gate fires;
our R1 date-FE + proximity-FE arms are the controls F7's raw gaps lacked); P8 P-W1/S-W3 sector-ETF
NULLs (different universe, ruler and role: trigger vs stratum); W8-A W-ARM OOS failure
(stale-cross population, approaching-cross extrapolation — not our definition); W8-B SHAKEN
shipped (weekly net-rising as ingredient — supportive); H5 monthly-falling trap veto FAIL
(different direction/lane); trend/location guards + CT-LANE (price-trend constructs, not
oscillator motion — and we run strata, never filters).

Expectation: turn-present fires better on stop5/mae21/clean8_21 with recall in the 30–60% band
(printed). Prediction two-sided on the 1M rung (state-level monthly added only +4pp vs weekly
+19pp; and 2W turn timing measured "catastrophically late" in case anatomy).
Kill line: CHIP bar (RUL-21) incl. NC-2-proxy marginality; else null printed and buried.

### B. esx_htf_turn_dose — turn-count ladder {0,1,2,3} across {W, 2W, 1M}

Mechanism: dose-response mirror of the state-level monotone 4-TF result; ordinal version of A.
Derived from A's columns (cheap). Monotonicity read (Jonckheere-style or FE on ordinal) only;
unlocked for verdict only if ≥1 A-form shows CI-excluding-0 (mirrors esx_support_dose gating,
RUL-25). Budget tiny.

### C. esx_washout_x_turn — HTF washout × HTF turn interaction

Mechanism: the state-level winner cell (deep AND reversing) fire-conditionally. Uses H1's exact
frozen washout feature (2W StochRSI D min over trailing 6 completed 2W bars < 25) × A-turn flags.
This is the honest version of the operator's "2W StochRSI washout" seed: depth counts only when
the higher degree is also turning.
Adjacency: H1 FAIL (depth alone — this is the interaction, explicitly the cell H1's verdict
pointed to); H2 FALSIFIED (age×calm — no age/calm ingredient permitted in this family);
BOTTOM_CONFIDENCE deep×reversing (supportive, state-level).
Expectation: the interaction cell beats both marginals on clean8_21 without paying H1's stop tax.
Kill line: CHIP bar; if the interaction adds nothing beyond A alone (marginality arm: interaction
coef with A-flag FE added), fold into A's verdict and close.

### D. ~~esx_div_fire~~ — DROPPED at census

Standalone bullish divergence is already anti-validated ("div WITHOUT cohort is actively BAD",
DURABLE_BOTTOM:343 — clean15 31.63 vs 32.60, stop5 48.46 vs 44.54). Re-running it on the ESX tape
would be re-derivation of a graveyard idea (R2 = automatic wave failure). Divergence stays where
it earned its keep: inside COILED/STAR. DROPPED.

### E. Declined momentum ideas (recorded so nobody re-walks them)

- New oscillator species (TSI, Williams %R, CCI, MFI, ultimate, Connors RSI2, DeMark counts):
  declined per BOTTOM_CONFIDENCE Result 4 + KST/multi-ROC collinearity ruling + faithful-math law.
  RSI2-deep-oversold ≈ proximity restated (NC-2). MFI needs volume (RUL-1 territory).
- Price-MACD (vs RSI-MACD) HTF states: collinear transform of the same information; declined.
- Oscillator washout DURATION ("time pinned <20"): position/age family — H1/H2 graveyard adjacency
  too hot; declined without a mechanism story that distinguishes it from H2's kill.
- Cardwell RSI range rules: regime relabeling of trend alignment; hostile (CT-LANE); declined.

---

## 2. Non-momentum candidates

### F. esx_underwater — drawdown-episode duration at fire

Mechanism: time spent below the prior 126d/252d peak measures how completely the holder base has
rotated/capitulated — an episode-structure claim, not a base-age claim. Primitive exists
(`entry_primitives.time_underwater_series`, W0, leak-tested). Two-sided by pre-registration.
Adjacency: H2 age×calm FALSIFIED (that was days-since-63d-LOW + vol crush on fast triggers; this
is episode length below a PEAK — different anchor, different scale, still cited); S-OH/D3
overhead-supply context (report column; distinct construct: distance vs duration).
Expectation: honest coin-flip; value = closing a never-tested structural dimension cheaply.
Kill line: CHIP bar; single run, no parameter shopping (terciles fixed cross-sectionally trailing).

### G. esx_second_test — retest-hold structure (double-bottom vs fresh-low fire)

CONDITIONAL — only if red-team finds it sufficiently distinct from S-UR's corpse. Mechanism: fire
occurring while price holds ≥ prior swing low within +8% (a second test that did NOT need the
undercut) vs fire at a fresh 63d low. S-UR tested the undercut-reclaim EVENT as a trigger; this is
a STRATUM over existing fires describing where in the base structure the fire lands.
Adjacency: S-UR (killed — must state why stratum≠trigger escapes its verdict); NC-2 proximity (the
confound that killed S-UR's last form — mandatory marginality arm, expect it to bite).
Prior: hostile. Pre-register expect-null; value = citable closure of the double-bottom folklore.

### H. Declined non-momentum ideas

- Stretch-below-MA in σ/ATR units: position/depth family (knife-risk kill + NC-2 collinearity);
  declined. RUL-14 vol-scaled outcomes already handle the vol confound the honest way.
- Donchian/range position, %B: proximity restated; declined (NC-2).
- Down-day density / capitulation cadence veto: the ¬turn arm of family A already carries this
  information; KNIFE_RISK label exists in labels_v1; declined as a separate family.
- Gap structure (D2), pocket pivot (D1): appendix-locked behind F-tier verdicts (masterplan);
  untouched here.
- Squeeze release (S-SQ): already registered W2 property of the base program; not A3's to touch.
- Cohort/breadth-of-fires, RS repair, sector velocity: owned (H6/COILED, #1302, Oracle/B2).
- Seasonality/calendar: out of scope (separate existing study `calendar_seasonality_tom_moy.py`).

---

## 3. Design laws for every A3 family (inherited, restated as binding)

1. 21d primaries per RUL-13: stop5 + mae21 co-primary + zone_held_21/stop_vol_21 (RUL-14);
   clean8_21 supporting; 63/126d = holdability descriptors only.
2. R1 date-FE estimator, frozen granularities (deep=date, baskets=date); episode-block bootstrap;
   era table; dev/holdout ticker halves on baskets; survivor stamps.
3. **Mandatory NC-2-proxy marginality arm in the PRIMARY read** (63-bar close-min proxy band FE) —
   the S-UR lesson. A candidate whose effect dies under proximity FE is a proximity shadow: null.
4. HTF features: last COMPLETED HTF bar strictly prior to fire; incumbent resampler; faithful math;
   leak-audit section mandatory (shift audit fixtures per primitive).
5. Recall printed beside every effect; no hard gates (RUL-4); chips/strata ceiling; display-first.
6. BH q≤0.10 within family; budgets itemized at registration; no mid-study forms.
7. No fire testifies twice (RUL-11): A3 families run on the frozen ESX tape; COILED overlap handled
   by marginality arms, not by re-scoring COILED.

## 4. Proposed budget sketch (to itemize at ratification)

| Family | Sketch budget | Basis |
|---|---|---|
| esx_htf_turn | 12 | 3 turn-defs × 2 panels × 2 contrasts |
| esx_htf_turn_dose | 2 | 1 ordinal × 2 panels (locked behind A) |
| esx_washout_x_turn | 8 | 2 interaction forms × 2 panels × 2 contrasts |
| esx_underwater | 4 | 1 def × 2 panels × 2 contrasts |
| esx_second_test | 4 | 1 def × 2 panels × 2 contrasts (expect-null) |
| **Total new** | **30** | ceiling 165 → 195 |

Harness/ledger hygiene items to ride the A3 T0 PR (census findings): (1) A2 families' declared_budget
rows never materialized in trial_ledger.jsonl (_register_all_families not re-run since the code edit)
— A3 registration run must materialize both A2 and A3 rows; (2) W2 SUR/SLQ runners produced reports
but logged 0 trials — A3 runners must log every trial via led.log_trial (budget field is `n` on
declared rows); (3) NC fast_effect_table lacks mae21/zone co-primaries — A3 runners use the harness
effect_table or extend fast_effect_table with the RUL-13/14 columns.

*Drafted by Fable, 2026-07-06, pre-census-verification and pre-red-team. Numbers cited from
firsthand doc reads this session; the census workflow's verified facts supersede on conflict.*

---

# ADJUDICATION TRAIL (Fable, 2026-07-06 — after 4 opus idea lenses + 4 opus red-teams, wf_817d5705)

**This section supersedes the draft above. The ratified book is
`research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md` (RUL-27..34).** All four red-team
verdicts: SHIP-WITH-FIXES. Disposition of every candidate that appeared in this program:

| Candidate (origin) | Disposition | Deciding argument |
|---|---|---|
| esx_htf_turn (draft A; endorsed by all lanes) | **REGISTERED, budget 12** | fixed: admission-leg decomposition promoted from context to BINDING control (RUL-29 — operative read within ¬wbull subset); monthly rung switched to StochRSI (RSI-MACD EMA-60 unconverged on baskets ⟦RT blocker⟧); 2W/1M rungs demoted to expect-weak |
| esx_htf_turn_dose (draft B) | **REGISTERED, budget 2, locked** | reframed as fire-conditional adjudication of the shipped-display bottom_confidence tf-count claim; collinear-legs caveat pre-registered |
| esx_washout_x_turn (draft C) | **REGISTERED, budget 8** | the operator's seed in its only live form; pre-registered expectation that proximity-FE bites hard; marginality-vs-A is the meaningful read |
| esx_sub_x_turn (evidence_gap lane) | **REGISTERED, budget 2, locked** | powered (59/41 × ~40-60%), nearly free, tests whether the deep-sub violence penalty attenuates under weekly turn |
| esx_decline_geometry (mechanism lane) | **REGISTERED, budget 4** — non-momentum flagship | genuinely new dimension (path shape: flush vs grind), scale-free, no depth/age/amplitude ingredient; full RUL-30 battery |
| esx_underwater (draft F) | **REGISTERED, budget 4** | primitive description corrected (saturating window); pure-age covariate added to prove ≠H2; ¬bear_ctx decomposition binding |
| esx_vol_transition (mechanism lane) | **REGISTERED, budget 4, expect-null** | settles whether vol MOTION escapes the H2 level-kill; realized-vol-LEVEL FE binding |
| esx_serial_fuel + esx_episode_spacing (stat_design lane) | **REJECTED — S6 owns it** | S6 Failed-Fire Fuel: registered species, phase0-PASSED OOS (+4.29pp clean8_21 q=0.032); pre-registered primary = failed2×COILED. 3 of 4 red-teams flagged independently |
| esx_second_test (draft G) | **REJECTED — proximity shadow** | held-above-prior-low = distance-to-low restated; modal outcome = the NC-2-proxy nullification that killed S-UR |
| esx_coil_range_at_fire (evidence_gap lane) | **REJECTED — banned variant** | the S-SQ family pre-registered its "arming" (state-without-release) variant as BANNED (masterplan §3 F3/§9) |
| esx_base_efficiency (mechanism lane) | **REJECTED** | Kaufman ER killed BY NAME (§5b); choppiness = CHARTER folklore/avoid, ER-collinear |
| esx_degree_alignment (mechanism lane) | **DEFERRED to A4** | untested cross-scale price structure, but position-family confound profile; buy only if A survives |
| esx_sub_x_freshticks (stat_design lane) | **REJECTED — unpowered** | deep×ticks≥1 ≈ 740 fires; NC-1 killed the ticks main effect |
| esx_div_fire (draft D) | REJECTED at census | standalone divergence anti-validated (DURABLE_BOTTOM:343) |
| esx_episode_first_only (stat_design lane) | MERGED | it was serial_fuel's complement arm — rejected with it |

Cross-cutting red-team fixes ratified into RUL-27..34: CHIP promotion blocked until true eq_band
(verdict vocabulary capped at DISPLAY-CANDIDATE/NULL/KILLED); NC-2-proxy = kill-arm not
promotion evidence; ¬bear_ctx decomposition (WAVE6 F8 frozen def) + realized-vol-level FE for
vol/bear-adjacent families; delisted-panel claims struck; extra_columns materialization law;
not_topped/eligible = tape constants (banned); stale mae21 hygiene claim corrected (already
landed); marginals-first (broader confluences = A4, gated on survivors).

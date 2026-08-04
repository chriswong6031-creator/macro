# CHINA PROPHET LOSER INTELLIGENCE — MASTERPLAN (BY FABLE)

**Date:** 2026-08-04 · **Trigger:** operator directive ("deep audit on the losers of
our V1 board … figure out what caused us to buy these and what went wrong … reduce
the likelihood of stocks that crash after we buy them WITHOUT tightening so winners
get cut … find joint causes … make China's board show more winners and fewer losers,
and identify even more winners — continuation winners, rotational winners").
**Evidence instruments:** `research/cn_prophet_audit/v1_loser_audit.py` +
`v1_runner_coverage_audit.py`, frozen numbers in
`research/cn_prophet_audit/RESULTS_2026-08-04.md`. All numbers reproduce from
committed stores; the loser instrument reproduces the shipped ledger headline
(407 matured / 68.6% win) before printing anything new.

Sibling program: `research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
(PR #4472, waves live in #4485-#4488). The US audit diagnosed why a
washout-resumption detector MISSES winners in a trending tape. This audit is the
mirror image: why the same family's CHINA implementation — in its native
mean-reverting habitat, with a genuinely strong record — still manufactures its
losers. The two failure surfaces are different and so are the fixes; nothing here
touches the US lanes.

---

## §0 ACCEPTANCE GATES — binding on every build wave spawned from this plan (inline in prompts)

- **G0.1 (no silent authority).** Every shipped surface/key is labeled `display` /
  `ops-telemetry` / `shadow-accrual` / `scored`. Anything `scored` cites a fresh
  prereg that cleared its gate or an operator-ratified adjudication. Display and
  shadow tiers ship freely (house epistemics); a null NEVER blocks accrual.
- **G0.2 (telemetry before tuning).** The W0 nightly CN loser+miss telemetry
  artifact must exist and be green for 5 consecutive nightlies before any W3+
  scored change merges.
- **G0.3 (case receipts).** A wave claiming to fix a §2 cohort (chase-cohort,
  entry-status inversion, HOT-late, re-admission churn) reproduces that cohort's
  numbers from the shipped artifact in its PR body.
- **G0.4 (population fences).** cn_prophet_v2 graded MEMBERSHIP changes only via
  operator-ratified adjudication. Shadow doors grade in their own ledgers
  (`WATCH_DEFINITIONS` pattern — never the headline grade). Era discipline stands:
  prior_record is a closed book, never pooled, never edited.
- **G0.5 (kills respected).** No wave rebuilds: subsector-state gating of A-share
  reversal (DNR row 85 — FALSIFIED, hurts vs flat), rotation × cycle-position
  entry-confluence (row 37 — DON'T-TEST), washout × turn seed (row 78 — KILLED),
  parallel rotation-schedule surfaces (row 54), LLM-originated signals (A7).
  §6 states how each new construction differs from its nearest kill.
- **G0.6 (bilingual + design law).** User-facing chips/lanes follow
  DESIGN_DOCTRINE + glance-tier budgets; zh parity; no internal study names
  front-facing; falsifier language stays background.
- **G0.7 (winner-forfeiture pricing).** Any candidate restriction ships with its
  measured cost table (losers removed vs winners forfeited vs kept-cohort delta).
  A restriction whose removed cohort has POSITIVE median excess is dead on
  arrival — this is the operator's "don't cut winners" constraint, made binding.

---

## §1 The ask, restated precisely

Four deliverables, each with a different mechanic:

1. **Fewer crash-after-buy losers** — the 128 lag episodes (31.4% of matured), median
   loser −10.8% absolute, MAE −13.7%, mostly slow bleeds with one ≥7% down day.
2. **No winner forfeiture** — every proposed restriction priced against the 279
   winners; blunt tightenings measured and rejected (§2.6).
3. **More winners surfaced** — the era's top runners the board never caught,
   classified by which DOOR would have caught them (continuation / rotation).
4. **V2 delta-audit** — which of these failure modes cn_prophet_v2 (live 2026-07-30)
   already fixes, which it carries forward, and which it makes worse.

## §2 Evidence (receipts — full tables in RESULTS_2026-08-04.md)

### 2.1 What the losers share (the chase fingerprint)

Losers were admitted HOT-short-term inside still-depressed charts: trailing-5d
+6.6% vs winners +3.7%; trailing-21d +2.8% vs −2.1%; +5.9% above MA20 vs +2.5%;
14.1% admitted on a close-at-high/limit day vs 5.0%; day-0 volume surge 1.36×.
Meanwhile drawdown-from-high was IDENTICAL (−30.4% vs −29.8%) — the losers were
not "extended" in the sense the anti-chase machinery measures. The V1 extension
score fired >0.3 on 12/842 admissions (1.4%) and its 3 matured fires all WON —
**the anti-chase leg watched extension-from-lows while the killer was
short-horizon thrust**. The `setup` score driving V1's rank was HIGHER on losers
(0.50 vs 0.32) and board rank-IC was +0.073 (anti-predictive): the board ordered
by exactly the thrust that mean-reverts.

### 2.2 Sector/theme concentration (the joint cause)

Technology 66% loser rate (median excess −6.6), Industrials 48%; two sectors =
~42% of all losers; same-day same-sector cohorts died together (6/30 Industrials
5/5, 7/02 Tech 3/3, 7/10 Tech 4/5). Defensives/Utilities/Energy ran 6-16% loser
rates. Theme narrative at admission: **HOT members lost at 42% vs WARMING 16%** —
HOT lost even inside strong sectors (Healthcare HOT 5/12 lost vs 16% sector-wide).
`ab_tier` A inverted (43% vs B 22%). The board consumed theme heat as card
decoration while buying INTO late theme heat — theme *timing*, not theme *level*,
is the predictive axis.

### 2.3 The entry-status inversion (live V2 defect)

The entry gauge's patience statuses were the era's best cohort — bounce_wait 6.9%
loser rate (+6.3 median), wait_pullback 7.7% (+6.9) — while its action statuses
were the worst: buy_soon 46.7%, partial 41.4%, buy_now 30.0%. Retro-applying V2's
featured gate (buy_now/partial ∧ not extended): **featured-like win 60.5% vs
78.5% for the cohort it excludes.** cn_prophet_v2's featured shelf — and its
entry score leg (buy_now 1.0 > wait_pullback 0.55) — selects INTO the loser
fingerprint. The stage `RAN_LATE` cohort (continuation; +6.0 median excess, 83%
win) is likewise excluded from featured by `non_entry_stage`.

### 2.4 Churn and paths

Re-admission after a losing episode: 33% win (n=15) vs 86% after a winning one
(n=50). All 15 fired before the prior verdict resolved — the buildable trigger is
price-vs-prior-fill, not the verdict. Path anatomy: 90/128 losers were slow
bleeds; 72 had a ≥7% single down day (22 hit an outright limit-down; winners: 4).
Day-3 mark ≤ −3% → 70% eventual loser rate finishing at median −14.6%
(front-loaded, persistent bleeds — partly mechanical overlap with the H=10
verdict; exit implications go to the W5 study, not to a hot patch).

### 2.5 The tape context

CSI300's forward-10 window was negative on 10 of 12 graded entry dates
(−0.7%…−5.9%). The record is CSI300-relative so the desk still won the era, but
absolute crash pain concentrates where the tape fell; the 6/30 initialization
cohort (whole standing board logged as day-one entries) ran a 48% loser rate vs
71.5% win on fresh admissions. own_market_regime stamps exist on the ledger (PIT
store since 2026-07-12) with zero consumers.

### 2.6 The obvious fixes are wrong (measured)

| Naive restriction | removed | L/W removed | removed medX | verdict |
|---|---|---|---|---|
| Sector cap 4/day on entries | 52 | 19/**33** | **+3.6** | forfeits winners — REJECT |
| Shrink board to top-40 | 141 | 38/**103** | +4.8 | rank is anti-predictive; bottom was fine — REJECT |
| vs-MA20 ≥ +15% block | 11 | 3/8 | +6.1 | REJECT |
| consec-up ≥ 5 block | 17 | 7/10 | +3.7 | REJECT |
| day-0 pop ≥5% block | 68 | 39/29 | −3.2 | too blunt; winners forfeited 1:0.75 |

vs the surgical lever:

| **chase_composite** (limit-day close-at-high ∪ T+1 gap ≥3% ∪ trail-21d ≥ +25%) | 31 | **22/9** | **−13.0** | kept win 71.8% (+3.2pp) — SHADOW-ACCRUE → prereg |

### 2.7 Missed winners (era runner funnel)

Top-150 era runners: **caught 88 (59%) · eligible_missed 45 (30%) ·
never_eligible 17 (11%)** — CN's funnel is structurally healthy where the US
one collapsed (US: 2/102 sighting→plan). All cohorts are washout-shaped
(era winners had median dd-from-high −27%…−40% at era start): the detector
family fits this tape, confirming the US audit's §2.4 regime read. The two
improvement pockets:
- the 45 eligible-missed (deepest washouts, median dd −40%) — a
  conversion/capacity pocket (V1 logged only top-60 of ~110 buy rows, so this
  number bounds rather than proves invisibility);
- the 17 never-eligible — the SHALLOWEST charts (dd −27%, trail-63 −11%),
  blocked by counter-trend/no-200-reclaim filters: the continuation/rotation
  shape the family structurally cannot admit; median era return +18.7%. This is
  S3's target cohort, and its size (11%) says CN needs a continuation door as a
  complement, not a rebuild.

### 2.8 What is built but unwired (census, 2026-08-04)

Confirmed by file:line sweep across the live pipeline (blend_sorted is CN-dead
since the 2026-07-30 cutover; V2 order = `prophet_score` sort, lanes =
`partition_board_rows`):

- **Zero pick-chain authority for every CN sector/theme engine.**
  `china_sector_central`, `subsector_rotation_china`, `china_basket_turn`,
  `china_sector_rotation`, `sector_legs_china`/rotation_events,
  `china_narrative_radar`, `china_sector_pathway`: absent from the pick chain
  entirely. `china_sector_cycles` reaches rows only as the `sector_turn` display
  flag; `china_narrative_tags` reaches rows only as display columns — both are
  named in `china_board_rank._ZERO_SCORE_AUTHORITY`, and narrative attachment is
  build-time ASSERTED to leave order byte-identical. The one theme→score channel
  that exists in code (`name_score` tailwind leg, ±15%) is structurally inert for
  CN: `basket_ctx` is never passed, and `_runway_value` reads only `fuel`.
- **Events are structurally absent** from the CN pick chain
  (`china_event_calendar` is LEAF/display by its own discipline block; zero
  imports from any pick-chain file). No catalyst can boost, suppress, or
  anticipate a CN pick — the US RC5 gap, CN edition.
- **A chase guard half-exists.** `china_microstructure` chase_veto fires on
  sealed limit-up (unfillable) or 5-session run ≥15%; `extension_read` even has
  a limit-up leg — but its `extended` threshold (score ≥ 0.60) fired on 1.4% of
  admissions while the measured crash cohort ran through it (median loser
  ext_score 0.0045). A dormant zt/连板 veto (`assert_zt_not_positive`) exists
  with NO production call site — a ready-made hook for S1.
- **The V2 ledger now grades ONLY the featured shelf.** `append_board` receives
  `wide["buy"]` = featured (≤ FEATURED_CAP 24; the top_n=60 param is a pre-v2
  holdover) — so the accruing cn_prophet_v2 record IS the record of the shelf
  §2.3 measures as anti-selective. The full scored universe (every lane, all
  components) is separately PIT-logged by `china_prophet_shadow` into
  `data/china_prophet_rank/candidates.parquet` since 2026-07-30 — the challenger
  data spine already exists; it lacks only a forward-return grader.

---

## §3 Root causes, ranked by measured impact

1. **CN-RC1 — Chase-cohort admission.** The A-share-specific pattern (admission on
   limit/close-at-high days, T+1 gaps, hot 21d trails inside washouts) supplies
   the deepest losers (removed-cohort median −13%); the machinery that should
   catch it (extension score) measures a different axis and was dark (1.4% fire
   rate, wrong sign where it fired).
2. **CN-RC2 — Entry-status inversion in the featured shelf.** The one cohort
   evidence favors (patience statuses, 93% win) is structurally excluded from
   featured; the cohort evidence indicts (buy_now/partial) is what featured
   selects. Live in cn_prophet_v2 today.
3. **CN-RC3 — Theme/sector intelligence unwired (CN edition of US RC3).** Theme
   heat exists on cards (narr_*), sector-turn exists as a flag, rotation engines
   exist as artifacts — none conditions candidacy, ordering, admission, or
   surfacing; the measured usable axis (WARMING-early vs HOT-late) is not even
   displayed as a distinction.
4. **CN-RC4 — Ordering anti-signal.** Board rank-IC +0.073; setup-score chase
   bias put the worst cohort at the top of the board the user reads.
5. **CN-RC5 — No continuation/rotation doors.** RAN_LATE cohort +6.0 medX / 83%
   win sits excluded from featured; era runner cohorts (§2.7) show which winners
   have no admissible door at all.
6. **CN-RC6 — Churn + ledger hygiene.** Sub-verdict re-admission churn (33% win);
   `n_skipped_no_price` mislabel; last-row-wins rk/tr in the shipped table;
   initialization-cohort drag undisclosed in the closed book.

## §4 What cn_prophet_v2 already fixed (delta-audit)

| V1 failure | V2 status |
|---|---|
| T4/no-tier rows buyable (2 T4 episodes, both ≤ −21% excess) | **FIXED** — T4 → forming lane, is_buyable excludes |
| No execution safeguards (locked-limit fills, illiquid names) | **FIXED** — micro fillability + chase_veto + ADV ≥ 0.5亿 floor |
| Extension penalty dark in rank | **PARTIAL** — extension now excludes from featured; but detector still measures extension-from-lows, not short-horizon thrust (CN-RC1 untouched) |
| No sector logic | **PARTIAL** — featured sector cap 4 (display-tier discipline); no sector-direction conditioning; naive entry-cap measured harmful anyway |
| Eligible rows silently dropped | **FIXED** — total-partition lanes (featured/more_actionable/late_or_unfillable/forming) |
| Stale-signal admission | **FIXED** — same-day input receipt required for featured |
| Setup-score chase bias in ordering | **PARTIAL** — setup has zero score authority in V2; but the entry leg re-introduces the same inversion (CN-RC2) |
| Entry-status inversion | **NOT FIXED — made structural** (featured gate + entry weights select the measured-worst statuses) |
| Theme/sector intelligence unwired | **NOT FIXED** (zero score authority AND no display of the timing axis) |
| Continuation exclusion | **NOT FIXED** (non_entry_stage → late_or_unfillable) |
| Re-admission churn | **NOT FIXED** |
| Regime throttle | **NOT FIXED** (stamps accrue, zero consumers) |

---

## §5 The program

### W0 — CN loser+miss telemetry engine (ops-telemetry; build first)
Productionize both instruments as `engine/cn_prophet_audit.py` + nightly artifact
`data/cn_prophet_audit/latest.json` (+ forward log): per-night matured-episode
loser forensics (chase-fingerprint fields, sector/theme cells, entry-status
cohorts, re-admission flags), era-runner coverage funnel
(caught / eligible_missed / never_eligible), and the V2 featured-vs-excluded
running score. Emits `::warning` (bare print, line-start, flushed) when the
chase-composite share of featured rises or when `no_price` skips are real.
Coordination fence: reuses the US W0 engine's artifact pattern (#4486) but is a
separate CN module — no shared file edits until the US wave merges. **Gate:
G0.2.** *Routing: builder (opus), 1 PR.*

### W1 — Ledger + closed-book hygiene (ops/display; ships freely)
1. Split `n_skipped_no_price` → `awaiting_t1` vs `no_price`; alarm only real.
2. Per-episode rk/tr from the admission row (not last-row-wins).
3. Prior-record panel: one disclosure line for the 6/30 initialization cohort
   (48% loser rate day-one stock vs 71.5% fresh-admission win) — honest-tier,
   below the fold, both languages.
4. Board-date × definition keep-first already fixed; add a test pinning the
   episode-grain rk/tr join. *Routing: builder (opus).*

### W2 — Chase-risk + theme-timing + day-3 pulse chips (display-tier; ships freely)
1. **Chase chip** on CN board cards whose row matches the chase composite
   (plain words: "enters after a limit-day pop — historically the crash cohort" /
   zh equivalent under glance budgets; Tier-2 hover carries the numbers).
2. **Theme-timing chip**: WARMING (early heat) vs HOT (late heat) distinction on
   the existing narrative chip — the measured axis, replacing undifferentiated
   heat display. No new surface (row 54 fence): these live on existing cards.
3. **Day-3 thesis pulse** on featured/live rows: "3 sessions in: on track /
   under review" from the existing interim marks (management surface, no exit
   authority).
4. **Re-admission flag**: "re-entering below prior exit" chip when a name returns
   under its prior episode fill.
No rank/gate/size authority anywhere in W2. *Routing: designer (opus) for chip
language/placement, builder (opus) for wiring; frontend-design skill +
DESIGN_DOCTRINE mandatory.*

### W3 — Shadow ledgers for the three candidate authorities (shadow-accrual → prereg)
Each accrues nightly in its own ledger (WATCH_DEFINITIONS pattern), each with a
pre-registered promotion gate (≥100 matured, ≥60td, and the G0.7 cost table
sustained prospectively) before any admission/rank authority:
- **S1 chase-veto shadow:** the composite from §2.6 as a would-have-vetoed flag;
  grades vetoed vs kept cohorts. Wiring home: the dormant
  `china_signals.assert_zt_not_positive` hook + `china_prophet_shadow`
  candidates.parquet as the PIT feature source. Differs from killed
  constructions: keys on admission-day tape mechanics (limit-day/gap/trail), not
  extension level (the ≥0.60 detector that fired on 1.4%), not washout-depth
  (#1747-A3), not subsector state (row 85). Overlap with the live micro
  chase_veto (sealed-limit / 5d ≥15%) is disclosed per-row so S1 grades only the
  RESIDUAL the live veto misses.
- **S2 patience-shelf shadow:** featured-alternative selecting the
  bounce_wait/wait_pullback/hold cohort (with V2's execution safeguards kept);
  races the live featured shelf on identical grading. The flip, if won, is a
  featured-definition adjudication (G0.4).
- **S3 continuation door (CN Door R):** RAN_LATE + re-arm rows (intact trend,
  reset-and-recross) as a shadow lane — the CN mirror of US W3 Door R, separate
  ledger, separate prereg. Differs from row 37 (no cycle-position leg) and
  row 78 (no 2W turn interaction): trend-intactness + reset only.
All three read features from the EXISTING `china_prophet_shadow`
candidates.parquet PIT store (every lane, every component, logged since
2026-07-30) — W3 builds graders, not new collectors.
*Routing: builder (opus) per shadow; preregs adjudicated in main loop.*

### W4 — Rotation-aware surfacing (display; the sector-intelligence wiring)
CN Theme Tape on china_stocks: top warming/hot themes × member board states with
why-not attributions (mirrors US W2 #4488 pattern; CN reference implementation is
the partition idiom). Sector-direction context chip per card (sector 20d relative
trend, plain words). Zero authority; the display half of CN-RC3. The scored half
(any theme-timing boost) waits for its own prereg on S-ledger evidence — and must
state its difference from DNR rows 37/85 explicitly. *Routing: designer+builder
(opus).*

### W5 — CN exit-policy + regime studies (research; feeds preregs, not weights)
1. CN edition of `exit_policy_study` over the 407-episode frame (A-share fills,
   limit-day exclusions): test the day-3 review family (§2.4) against the H=10
   incumbent — the US result (nothing beat H=10) does NOT port automatically;
   CN bleeds are front-loaded (median loser day-3 −5.5% → final −10.8%).
2. Regime-throttle study once own_market_regime accrues a second regime: does
   full-rate admission into falling-CSI windows cost absolute pain the
   excess-basis record hides?
*Routing: builder (opus) instruments, main-loop adjudication.*

### W6 — Learning-loop closure (ops)
Extend the postmortem protocol: CN loser taxonomy (chase / sector-cohort /
theme-late / churn / other) auto-stamped nightly by W0; weekly governor report
joins CN losers × missed runners into tilt preregs. Never hot-patched weights.

---

## §6 What this plan deliberately does NOT do

- No naive sector caps / board shrinking / momentum blocks on membership — each
  measured winner-negative (§2.6); G0.7 makes the pricing binding forever.
- No loosening of V2's execution safeguards (micro/liquidity/fresh-signal) — not
  implicated by any loser cohort.
- No subsector-state gate on reversal (row 85), no rotation×cycle confluence
  (row 37), no washout×turn (row 78), no parallel rotation surface (row 54), no
  washout-depth ranking (#1747-A3), no LLM-originated signals (A7).
- No touching the US Prophet lanes (#4485-#4488) or the HK board (#4421).
- No era pooling; prior_record stays a closed book; cn_prophet_v2 membership
  byte-identical until an operator-ratified flip.
- No exit-rule hot patch from the day-3 tell — study first (W5), display pulse
  only (W2).

## §7 Rollout, fences, collisions

Order: **W0 → W1 → W2 → (W3 ∥ W4) → W5 → W6.** W0-W2 are one build week; W3
shadows accrue from merge day; nothing scored moves before G0.2 + its prereg.
Collisions checked 2026-08-04: US waves #4485-#4488 (separate files; reuse
patterns only after merge), HK resurrection #4421 (separate market), SI China
consolidation (#4418/#4450 SEO lanes — display pages this plan doesn't touch),
washout reversal_watch shelf (#4393 — watch-tier, untouched; S-ledgers use the
same WATCH_DEFINITIONS isolation so headline grade can never flip onto a shadow).
Model routing per CLAUDE.md: Opus builds/reviews/designs; sonnet only for census
sweeps; main-loop Fable adjudicates preregs and promotions.

## §8 Pre-registered success metrics (graded by W0's artifact; baselines = this audit)

| Metric | Baseline (V1 era) | Target (next 90 graded sessions) |
|---|---|---|
| M1 loser rate among matured episodes | 31.4% | ≤ 25% without M2 regressing |
| M2 median excess | +4.44 | ≥ baseline (winner protection) |
| M3 chase-cohort share of admissions | 7.6% (31/407) | flagged 100% (display); shadow veto graded |
| M4 featured-vs-excluded gap (V2 shelf) | −18pp win (60.5 vs 78.5) | ≥ 0 (shelf no longer anti-selective) |
| M5 catastrophic losers (≤ −15% abs) | 47/407 (11.5%) | ≤ 8% |
| M6 era-runner coverage (caught / sighted) | 59% / 89% | caught ≥ 70% with doors, no record dilution |
| M7 re-admission-below-prior-fill flagged | 0% | 100% (display) |

M1/M2/M5 are the honest headline pair — improvement must come from composition,
not from shrinking n. All targets grade in the forward ledger; none is a promise.

---

*Related: PROPHET_US_TREND_INTELLIGENCE (the mirror audit), PROPHET_LEARNING_LOOP
(postmortem/exit machinery + era discipline), PROPHET_BOARD_PRIORITY_ENGINE
(#4331 CN unified grid), CHINA_STANDOUT_DOUBLE_CONFLUENCE (the V1 detector
family), TIERED_CASCADE.md (blend mechanics), DNR rows 37/54/78/85 (fences).*

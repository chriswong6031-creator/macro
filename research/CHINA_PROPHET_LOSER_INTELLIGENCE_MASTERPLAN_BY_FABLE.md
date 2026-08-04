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
- **G0.8 (ratified-tier discipline; added 2026-08-04).** Every operator-ratified
  direct wiring (§5 R-slate) ships in the same PR with: (a) a parallel shadow
  grading of the displaced definition (the race runs anyway, with the evidence-
  favored side live), (b) a named auto-tripwire in the W0 artifact with its
  threshold and revert action, and (c) a clean single-commit revert path. A
  pending study whose decision-relevant summary CONTRADICTS a slate item pauses
  that item pending operator read.

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

### 2.9 The chase cohort is BIMODAL (operator challenge round, 2026-08-04)

The operator asked why the chase composite ships shadow-first if it helps, and
whether its forfeited winners are weak. Measured answer: **the forfeited winners
are the STRONGEST winners** — the 9 chase-cohort winners median +14.5 excess vs
+6.8 for non-chase winners (incl. +37.8 and +54.8). The chase cohort is the
A-share 龙头/跟风 dichotomy in one bucket: relay leaders AND bagholders. And the
system's own theme intelligence separates them **in-era**: chase × narr HOT =
median **+14.5** (3/5 win); chase × no-theme = median **−14.3** (6/26 win). A
naive blanket veto is aggregate-positive (+217pp total avoided) but amputates
the exact fast-winner right tail the desk exists to catch. The correct wiring is
CONDITIONAL: naked chase (no theme behind it) demotes; theme-backed chase is the
relay class and stays. 12-month out-of-era formalization:
`ignition_chase_study.py` (§5 W-B).

### 2.10 The intelligence had ex-ante value (measured, not assumed)

`sector_intel_exante_test.py` joins the PIT `china_sector_cycles`
forward_log (accrued nightly, covers the whole era) + PIT-dated curated basket
membership onto the 407 matured episodes at admission:

| Ex-ante state at admission | n | loser rate | median excess |
|---|---|---|---|
| In a curated basket (any state) | 84 | **13.1%** | +7.2 |
| NOT in any curated basket | 323 | **36.2%** | — |
| Basket phase Trough, oscillator turning up ("Trough+") | 28 | **3.6%** | +8.3 |
| Basket Recovery+ | 7 | 0% | +9.0 |
| Basket Trough− | 37 | 16.2% | +5.9 |
| Basket Downturn− | 4 | 50% | −7.5 |
| Basket above 200d (late-stage theme) | 19 | 26.3% | +4.5 |

Membership in a researched theme — and the cycle engine's own early-turn states —
separated losers from winners point-in-time, with the direction consistent
across three independent instruments (narrative WARMING>HOT §2.2, chase×theme
§2.9, phase×slope here). The pick chain consumed none of it. Caveats: 21%
coverage (22 curated baskets), thin cells, one era — corroboration at 12-month
scale in W-B; the coverage split partially reflects curation quality itself,
which is still an admissible prior (researched-theme membership is PIT-knowable).

### 2.11 Why the entry gauge inverts (mechanism, not mystery)

`entry_signal.assess` maps a daily-cycle ladder's urgency to statuses;
`bounce_wait` is specifically the **regime-gate demotion of an already-fired
daily buy** — "washed out far below its 200dma, turn not confirmed". In a
mean-reversion tape, that demotion selects exactly the early-reclaim cohort
(measured 93% win), while "confirmed window open" (`buy_now`) fires after the
bounce has matured (the loser cohort). The gauge is not broken — its
trend-confirmation semantics invert in this regime. This is the operator's
"confluence gating as deterrent" instinct, measured: **confirmation is
negatively priced at CN entry timing.** The featured shelf must feature the
early window and demote the confirmed-late window, not vice versa.

### 2.12 The 12-month formalization verdicts (W-B, PR #4506 — G0.8 applied)

`ignition_chase_study.py` (241 sessions, 1,668 names, 257 baskets, 7,816
matured chase events) re-ran the §2.9 constructions at scale:

- **Chase×theme-heat DOES NOT REPLICATE** — chase inside HOT: median −2.04pp /
  win 43.4% (n=3,317) vs chase with no theme: −1.51pp / 45.3% (n=3,694). The
  in-era n=5 relay-winner cell was noise. Theme heat is NOT the chase
  separator; R3's theme-backed leg was dropped before implementation.
- **Blanket chase veto stays unjustifiable at scale** — median worse
  (−1.72 vs −1.04) but mean (+0.98 vs +0.25) and win% better: a wider
  distribution in both directions. Deleting the cohort deletes the right tail.
- **RELAY POSITION is the real, monotone, robust separator**: early (≤1 other
  same-theme member limit-closed in 3d) −1.17pp / 46.0% → mid −2.61pp / 42.3%
  → late (≥4) **−5.32pp / 36.0%** (n=406; H=21 −8.36pp / 31.3%); the ladder
  holds inside HOT and WARMING separately and across window halves. It is a
  RANKING, not a green light — the only n≥100 name-level cell above water is
  WARMING|early (+0.25pp, 50.6%), which weakly supports R2's WARMING-early
  direction.
- **Theme ignition leads at the BASKET level** (+1.25pp / 58% forward-10 after
  a WARMING/HOT upgrade vs +0.33 control) **but naive member fresh-print
  entries do not capture it** (−1.46pp vs −1.06 baseline) — the ride is real,
  the naive translation to name-level entries fails. Any member-level
  exploitation needs a construction that beats this measured null.
- **Weakest joint (prerequisite for any relay promotion):** THS basket
  membership is a single 2026-07-08 snapshot applied backward — the two
  available PIT snapshots differ by 7.7% of member-slots in 8 days. Nightly
  PIT membership snapshots are chartered as a W-C sub-task. (The §2.10 ex-ante
  receipt is unaffected: it used the CURATED membership with PIT added/removed
  dates.)

---

## §3 Root causes, ranked by measured impact

1. **CN-RC0 — Confirmation is negatively priced at CN entry timing (the unifying
   cause).** Three layers of the chain wait for confirmation and each waiting
   step selects a later, worse entry: the entry gauge's "window open" statuses
   (§2.11), the fresh-cross recency inside the cascade (losers' 5d trail +6.6%),
   and the featured shelf built on both. The record's edge lived in the cohorts
   every confirmation layer demoted (bounce_wait 93%, blocked 5/5, Trough+ 96%).
2. **CN-RC1 — Unconditional chase admission.** The A-share limit-day/relay
   pattern is bimodal (§2.9); the chain neither demotes the naked-chase
   bagholder class nor recognizes the theme-backed relay class — the extension
   detector measures a different axis (1.4% fire rate).
3. **CN-RC2 — Entry-status inversion made structural in V2's featured shelf**
   (60.5% vs 78.5% excluded), and the V2 ledger now grades exactly that shelf.
4. **CN-RC3 — Theme/cycle intelligence unwired despite measured ex-ante value**
   (§2.10: membership 13% vs 36% loser rate; Trough+ 3.6%; three instruments
   agree). US RC3's CN edition, now with the wiring case quantified.
5. **CN-RC4 — Ordering anti-signal.** Board rank-IC +0.073; setup-score chase
   bias put the worst cohort at the top of the board the user reads.
6. **CN-RC5 — No continuation/relay doors.** RAN_LATE +6.0 medX / 83% win
   excluded from featured; 11% of era runners never-eligible (counter-trend
   blocks); relay winners only enter by accident.
7. **CN-RC6 — Churn + ledger hygiene.** Sub-verdict re-admission churn (33%
   win); `n_skipped_no_price` mislabel; last-row-wins rk/tr; initialization-
   cohort drag undisclosed.

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

## §5 The program — CHINA PROPHET V3 "RELAY ENGINE"

Amended 2026-08-04 after the operator's challenge round ("solutions not powerful
enough; wire the intelligence in"). The amendment upgrades the plan from
shadow-first conservatism to a **ratified direct-wiring slate with tripwires**:
the gauntlet remains the promotion gate for *future* tuning, but the changes
below cite measured in-era evidence plus mechanism, ship with parallel shadow
grading of the displaced definition, and auto-alarm on regression (new G0.8).
The operator's directive in the 2026-08-04 session is the ratification event
G0.4 requires; each R-item below is individually revertible.

**The architecture (three axes, one sentence each):**
- **WHERE (theme/cycle context):** a pick's theme membership, heat *timing*
  (warming-early vs hot-late), and basket cycle state (Trough+/Recovery+ vs
  Downturn−) condition admission priors, score, and surfacing — §2.10 measured.
- **WHEN (entry timing):** featured = the EARLY-reclaim window (the demoted
  cohorts that won 92-93%), confirmed-late demotes — §2.3/§2.11 measured.
- **WHO ELSE (relay/breadth):** limit-day/velocity events are read through
  theme ignition: theme-backed relay ≠ naked chase — §2.9 measured.

### R-SLATE — ratified direct wirings (ship now; each with tripwire + shadow)

**R1 — Featured shelf re-founded on the prime window (`cn_prophet_v3`).**
`engine/china_board_rank.py`: `_FEATURED_ENTRY_STATUSES` becomes the
prime-window set {bounce_wait, wait_pullback, hold, buy_now, partial} MINUS the
confirmed-late demotion: buy_now/partial admit to featured only with
`signal.ticks ≤ 1` and no R3 naked-chase flag; bounce_wait/wait_pullback/hold
admit with the same execution safeguards as today (fresh signal, micro clear,
liquid, not extended). `_ENTRY_VALUE` re-ordered to the measured order
(bounce_wait 1.0, wait_pullback 0.95, hold 0.8, buy_now 0.7, partial 0.6,
buy_soon 0.35, extended 0.3, rest unchanged at ≤0.3). BOARD_DEFINITION bumps to
`cn_prophet_v3` so the graded record forks cleanly (era discipline; v2 record
closes at 39 rows/0 matured — no era pooling). The old v2 featured definition
keeps grading as a labeled shadow (`cn_prophet_v2_shadow`) via a second
append_board call under WATCH_DEFINITIONS, so the race the operator would have
waited weeks for runs anyway — with v3 LIVE and v2 as the challenger.
User-facing copy: featured = "prime entry window — early turn"; demoted late
entries say so in plain words (glance budgets, zh parity).
*Tripwire (G0.8):* W0 telemetry compares v3-featured vs v2-shadow on rolling
matured cohorts; if v3 trails by ≥5pp win-rate over ≥60 matured episodes,
`::warning` + revert proposal to the operator.

**R2 — Theme/cycle context gains bounded score + admission authority.**
`china_board_rank.SCORE_WEIGHTS` rebalanced: signal 30 / entry 20 / runway 15 /
bottom_quality 10 / reversal_member 10 / **theme_timing 15** (sums 100).
`theme_timing` value per name (all PIT, from inputs build_china_library already
computes): 1.0 = basket member AND (narr WARMING or basket phase Trough+/
Recovery+); 0.6 = basket member, neutral state; 0.25 = non-member (curated ∪ THS
union); 0.0 = member of HOT-fading (narr HOT with rel20_slope5 < 0) or
Downturn− basket. Narrative/cycle attachment moves BEFORE `enrich_and_score_rows`
in `build_china_library.py`; the W2-B order-invariance assertion is REPLACED by
its inverse contract (a test pinning that theme_timing has exactly the bounded
authority above and that `sector_turn`/raw heat still add zero) —
`_ZERO_SCORE_AUTHORITY` updated to name the surviving zero-authority keys and
the docstring/design-law comments updated in the same commit. DNR row 85
differentiation: this is a bounded score tilt + admission prior on the standout
board keyed to theme-basket cycle/timing states, not the falsified binary
subsector-state gate on the reversal sleeve; rows 37/78 untouched (no
cycle-position×rotation confluence, no washout×turn term).
*Tripwire:* W0 stratifies nightly by theme_timing bucket; if the 1.0 bucket's
rolling loser rate exceeds the 0.25 bucket's over ≥60 matured, alarm + revert.

**R3 — Relay-position chase guard (REVISED 2026-08-04 per §2.12 / G0.8; the
original theme-backed form was refuted before implementation).**
Build-time-knowable composite (T+1 gap is grading-side): admission-day
limit-close (close==high AND day move ≥ 0.95×limit, limit by board_type — not
raw code prefix) OR trail-21d ≥ +25% OR the micro chase_veto's 5-session ≥15%
leg. Per-candidate `relay_count_3d` = distinct OTHER members of the name's
baskets printing a limit-close in [d−2, d]; position early ≤1 / mid 2-3 /
late ≥4 / none (no membership). **The only admission effect:** chase-composite
∧ relay LATE → featured-shortfall `relay_late` (routes to more_actionable —
ordering-grade demotion, per the study's "a ranking, not a buy trigger").
Everything else about chase is display/ledger: the chase + relay fields ride
every row so W0 grades all branches nightly. No naked-chase demote (refuted),
no relay green-light mark (refuted). *Tripwire:* relay_late demoted-vs-kept
featured, rolling 60 matured.

**R4 — Doors surface immediately (display), grade in shadow.**
- Relay door: R3's theme-backed relay marks are a visible featured-adjacent
  class from day one.
- Continuation door: the §2.7 never-eligible cohort (intact-trend names blocked
  by counter-trend/200-reclaim filters) surfaces as a labeled watch strip when
  theme-backed (member of WARMING/igniting basket), shadow-graded under
  `cn_continuation_watch_v1` (WATCH_DEFINITIONS pattern; zero population
  authority until its prereg clears). Implementation W-C (builder wave, needs
  candidate plumbing outside `eligible_rows`).
- Both doors' promotion to population authority stays gauntleted (≥100 matured,
  ≥60td, G0.7 table) — surfacing now, authority by evidence.

**R5 — Exits: DECIDED by the CN exit study (W-E, PR #4507; 0/11 challengers
beat the incumbent's headline stats).** The record basis stays the H=10 forced
verdict — the US "nothing beats the incumbent" result now holds MEASURED in CN.
The day-3 review family is refuted for exits (the tell is not sharper at bar 3
than bar 1: 0.71→0.68; one flagged name in three is a forfeited winner). What
survives: (a) the day-3 pulse ships as an honest STATUS line only ("under
review"), never implying an exit rule; (b) the hard-stop family's
tail-compression finding — S10 improves 54 losers per 6 winners degraded
(9:1), MAE p10 −16.9→−12.0, mean excess +0.64 [0.17, 1.15] blocked-CI —
becomes a DISPLAY-tier "risk line" candidate on pick cards for real-money
holders, quoted with its execution bound (stops filled a weighted −2.39pp
below trigger; 43/406 exits fired on limit-locked sessions where selling was
unreliable — the printed line is guidance, never a guaranteed fill); any
graded form needs its own prereg. (c) The winners-run/extension family is
CENSORED (103/141 rows marked, not realized) — re-run as caches mature.

### Build waves (all Opus builders; specs above are binding)

### W-A — R1+R2+R3 implementation (one PR)
`china_board_rank.py` + `build_china_library.py` wiring + tests (entry-map
order, theme_timing bounds, naked-vs-relay routing, v3 definition stamp,
v2-shadow parallel grading, updated invariants). Case receipts in PR body per
G0.3: the §2.3 inversion table, §2.9 split, §2.10 table.

### W-B — 12-month formalization (DONE — PR #4506; verdicts in §2.12)
Chase×theme refuted; relay ladder established; basket-level ignition lead real,
naive member translation null. R3 revised accordingly BEFORE implementation
(G0.8 worked as designed).

### W-C — Continuation door plumbing + Theme Tape CN + PIT membership (display + shadow ledger)
The §2.7 cohort surfacing + `cn_continuation_watch_v1` ledger; CN Theme Tape on
china_stocks reusing the US W2 pattern (#4488) — theme heat × member states ×
why-not attributions, glance-tier, zh parity. NEW sub-task (W-B's weakest-joint
flag): nightly PIT snapshots of THS basket membership (append-only store,
keep-first per date) — the prerequisite for ANY future relay-construction
promotion; member-slot drift measured at 7.7%/8 days. Any member-level
ignition door must beat the §2.12 measured null (member fresh-prints after
theme upgrade −1.46pp), not just show a positive cell.

### W-E — CN exit-policy study (DONE — PR #4507; verdict in R5)
0/11 challengers beat the incumbent's win rate or median; day-3 review refuted;
stop-family tail compression → display-tier risk-line candidate with execution
bound; extension family censored, re-run on maturity.

### W0 — CN loser+miss telemetry engine (ops-telemetry; RUNNING — now also the
R-slate tripwire host: v3-vs-v2-shadow race, theme_timing strata, chase-branch
grades, all in the nightly artifact + forward log)
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

### (Superseded by the R-slate, 2026-08-04 amendment)
The original shadow-first waves W2 (display chips), W3 (S1 chase-veto / S2
patience-shelf / S3 continuation shadows), W4 (rotation surfacing) and W5.1
(exit study) are absorbed as follows: S1→R3 (conditional, direct), S2→R1
(direct flip, v2 becomes the shadow), S3→R4/W-C, W2 chips→W-A copy + W-C Theme
Tape, W4→W-C, W5.1→W-E. W5.2 (regime-throttle study once own_market_regime
accrues a second regime) remains open as a research follow-up. The day-3 pulse
and re-entry-below-prior-fill display chips remain in scope inside W-A/W-C.

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
- No BLANKET chase veto — measured to amputate the strongest winners (§2.9);
  only the conditional R3 form ships.
- No touching the US Prophet lanes (#4485-#4488) or the HK board (#4421).
- No era pooling; prior_record and the 39-row cn_prophet_v2 book stay closed,
  labeled eras; the R1 flip is the operator-ratified event G0.4 contemplates
  (2026-08-04 directive), stamped as a NEW definition — never an in-place edit.
- No exit-rule hot patch from the day-3 tell — the W-E study decides (R5);
  display pulse only until then.
- No population deletion anywhere: naked-chase and demoted names stay on the
  board in labeled lanes; only featured membership and ordering move.

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

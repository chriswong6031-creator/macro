# D1 owner-surface field mapping — site/marketdata/subsector_rotation.json
Producer: engine/subsector_rotation.py (_rotation_metrics, attach_turn) + engine/subsector_turn.py
(node_read/advance_state/fast_rank) via scripts/build_subsector_rotation.py.
Row schema shared verbatim across themes[]/subsectors[]/sectors[] (58/58/59 keys, diffs only in
identity+membership fields). Verdicts: REUSE / TRANSFORM / REJECT / OWNER_ONLY.

## Top-level fields
asof            TRANSFORM  Finviz perf_snapshot.json's own asof (build_subsector_rotation.py:256) -
                           own-source PIT date, not a fused clock.
generated_utc   OWNER_ONLY render wall-clock (datetime.now(utc)), not a state feature.
source          REUSE      "finviz-themes" provenance tag - reuse AS a provenance label only;
                           rights_class=unresolved/internal_only (config/theme_sources.yml).
timeframes/mom_horizons  OWNER_ONLY  config lists, not data.
n_subsectors/n_themes/n_sectors  OWNER_ONLY  coverage counts, not features (no coverage math per scope).
themes_unit     OWNER_ONLY unclear internal flag (observed false); not chased further (out of scope).
highlights{emerging,fading,leaders,laggards}  TRANSFORM  curated top-N lists derived from emerging_score
                           - inherits that field's REJECT/TRANSFORM caveat below.
turn / turn_themes / turn_sectors  TRANSFORM  turn-engine cross-section summaries (counts, params,
                           leg_weights, nominations) - display tier, house plain-word law applies if reused.
track_record    OWNER_ONLY self-referential IC/lead-time grading of subsector_rotation's OWN score;
                           not a portable feature.

## Row fields (themes[] / subsectors[] / sectors[] — shared schema)
theme/key/name/name_zh/theme_zh   TRANSFORM  identity strings; theme_crosswalk.yml already joins on
                           these (`subsector_keys` references themes[].theme verbatim) - existing join
                           key, not itself a feature. No new identity resolution proposed (out of scope).
n_subs/n_members/members  OWNER_ONLY  composition/membership list; reuse would be a taxonomy-mapping
                           decision, out of this scope.
perf{1D..YTD}    REUSE     raw % return per horizon - direct "performance" primitive, no transform needed.
rs{1W..1Y}       TRANSFORM own-median-subtracted relative perf (engine/subsector_rotation.py:100-102) -
                           "performance relative to universe" but median is THIS cross-section's own
                           subsectors, not a canonical benchmark.
rs_ratio         TRANSFORM mean(zscore(rs[1M]), zscore(rs[3M])) (:117) - RRG "ratio" axis, a level not a feature primitive.
rs_mom           TRANSFORM mean(zrs[1W],zrs[1M]) - mean(zrs[3M],zrs[6M]) (:118-119) - RRG "momentum" axis;
                           closest existing analog to "velocity of relative strength" but is a
                           difference-of-z-score-means, not a raw derivative.
accel            TRANSFORM rate[1W] - rate[3M] where rate=perf/weeks (:107-112) - a real acceleration
                           PROXY (pace-now minus pace-over-13wk) but a simple difference, not a 2nd
                           derivative of a smoothed series. Per mission instruction: does NOT by itself
                           satisfy a rigorous V4 "acceleration" definition - flag, don't assume.
z_accel          TRANSFORM cross-sectional z of `accel` (:113). Same formula caveat as accel.
quadrant         TRANSFORM sign(rs_ratio)/sign(rs_mom) → leading/weakening/improving/lagging (:81-84) -
                           discretized performance+velocity joint state, Finviz-cross-section-specific.
emerging_score   REJECT    0.5*z_accel + 0.8*rs_mom + 0.3*zrs[1W] (:121) - bespoke weighted composite,
                           weights not calibrated/receipted in this file; not a V4 primitive as-is.
pace/pace_rel/pace_mkt  TRANSFORM  return/weeks per segment (y1x/m6x/m3x/m1x/w1/d1) - closest existing
                           "velocity" primitive (rate of return per unit time); simple mean-rate, not
                           robust/smoothed.
path/path_ages/rs_path   OWNER_ONLY  6-point normalized level curve for charting; not a scalar feature.
pos_in_range/rs_pos_in_range  TRANSFORM  position in 1y range (0-100). NOTE: superficially reads like
                           "diffusion" but is a PRICE-RANGE position, not member/constituent
                           participation - do not conflate with masterplan diffusion vocabulary.
dd_from_peak/up_from_trough/days_since_peak_approx/days_since_trough_approx (+ rs_* variants)
                 TRANSFORM  drawdown/rally + age stats; could inform a future "cycle stage" feature.
noise_w/noise_src/vol_cold/vol_abs_w  OWNER_ONLY  internal tracking-error normalization constants of
                           THIS engine's z-scores; not portable.
impulse_z/accel_z/curve_z/trend_z/today_z  TRANSFORM  engine/subsector_turn.py:456-461,589-590 - EXCESS
                           (vs-market) pace derivatives normalized by node noise floor. THESE, not the
                           top-level `accel`/`z_accel`, are the engine's actual velocity/acceleration/
                           curvature (jerk) constructs. IMPORTANT: two different fields both named
                           "accel*" (top-level accel/z_accel vs turn-engine accel_z) use DIFFERENT
                           formulas - D3 must not conflate them.
base_pace        TRANSFORM mean(excess m3x, excess m6x) (:454) - a velocity baseline/floor term.
fell/rose/basis_up/basis_dn  OWNER_ONLY  turn-engine precondition gate flags, engine-specific.
bottom_score/top_score  REJECT  weighted-leg turn-confidence composite (0-1, engine/subsector_turn.py
                           :483-496) - bespoke heuristic, not a calibrated V4 primitive as-is.
legs_up/legs_dn  OWNER_ONLY  internal sub-leg breakdown (flip/regime/rs/part), engine-specific receipts.
breadth{n,up_1w,beat_mkt_1w,turn_up,turn_dn,disp_w,med_minus_mean,top_share,concentrated}
                 TRANSFORM  member_breadth() (engine/subsector_turn.py:363-421) - fraction of
                           CONSTITUENTS whose excess pace is turning up/down vs the tape. CLOSEST
                           direct analog to masterplan breadth/diffusion vocabulary. Caveats: computed
                           "today only - never replayed" (no PIT history), null below
                           breadth_min_members=3.
rs_ratio_v2/rs_mom_v2/rank_score_v2  REJECT (for now)  explicitly unpromoted v2 experiment "graded
                           head-to-head... the ledger decides" (fast_rank docstring, :660-676) - do not
                           treat as settled; epistemics law (gauntlet=promotion gate) applies.
turn_state/turn_since/turn_age/persist_up/persist_dn/turn_score/tail
                 TRANSFORM  hysteresis state machine over turn-engine score (advance_state, STATES
                           tuple :159) - discretized turning-point regime w/ persistence. House law:
                           plain-word/no-falsifier-language display copy only (operator 2026-07-27).
turn_label*/turn_say*  OWNER_ONLY  bilingual UI copy strings, not features.
rank_v2          REJECT    ranking derived from the unpromoted rank_score_v2.

## Clocks (verbatim, read 2026-08-17 from site/marketdata/subsector_rotation.json)
asof: "2026-08-13"
generated_utc: "2026-08-17 23:53"
-> ~4-day gap between the underlying Finviz snapshot date and tonight's render/publish time.
Reported as read; no causal diagnosis attempted (out of scope for this commission).

## Related-but-distinct owner surface (reconciliation note, NOT field-mapped here)
"What To Act On Now" = the Act-Now board, site/basketdata/action_board.json, produced by
scripts/build_sector_central.py / engine/entry_radar/producers/boards.py / engine/basket_score.py /
engine/theme_scoring.py / engine/us_act_now.py (bottoming-watch lane, cycle engine). Different taxonomy
(49 mastermind_curated baskets, rights_class=direct_display_ok, vs subsector_rotation's 41 Finviz
themes/269 subsectors, rights_class=unresolved). Different clock, different purpose (individual
basket buy/wait/reduce guidance vs group/theme rotation strength). Do not conflate the two surfaces or
their field vocabularies; subsector_rotation.json is the one structurally aligned with masterplan
§12.5's group-level performance/velocity/acceleration/breadth vocabulary. Full field-level mapping of
the Act-Now board was NOT done (out of the effort budget / not the artifact named in the commission)
- flag as a GAP if D3 needs it.

## RIGHTS_DECISION_REQUIRED items surfaced
1. Finviz "derived display" tier (W3A §1, config/theme_sources.yml finviz_themes row): unresolved -
   forcing point is W6. subsector_rotation.json/themes_heatmap.json are grandfathered AS-IS, but any
   NEW GMI-authored derivative built on top of them inherits internal_only until resolved.
2. Citrini basket-definition commit: citrini_basket_ids stays [] until actual definitions are
   committed to the repo (config/theme_crosswalk.yml:21-25) - a delivery/operator action, not a new
   rights ruling (the ruling itself - CITR-2 definitions-only - is already made, 2026-08-11).
3. Theia TIIC/TWI license purchase: open procurement decision for the Chairman
   (DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS) - no urgency, not blocking.
4. S&P/Kensho systematic constituent ingestion: explicitly a procurement decision, not yet raised
   (W3A §4) - prepare only when a wave actually needs the evidence.

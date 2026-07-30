# Subsector Turn Engine — reading cycle turns off a return term structure

**Status:** SHIPPED (display/context tier), 2026-07-30. Engine `engine/subsector_turn.py`,
wired through `engine/subsector_rotation.py` → `site/subsector_rotation.html`.
**Authority:** `may_rank:false, may_gate:false, may_size:false, may_escalate:false`. The
incumbent read is untouched and both are graded head-to-head — see §5.
**Parents:** `research/ROTATION_COMMAND_MASTERPLAN_BY_FABLE.md` (RC-R4/R5 wiring),
`research/POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md` §4.2/§4.3 (why the actionable
surfaces run late, and why cycle position may never carry a score's sign).

---

## 0. The problem, stated as arithmetic

The rotation desk reads Finviz's broad-universe theme→subsector snapshot: eight
**cumulative** horizon returns per node (1D/1W/1M/MTD/3M/6M/1Y/YTD) across 268 subsectors
and 40 themes. The incumbent metrics treat those eight numbers as eight independent
features. They are nested, and the nesting is the latency:

| Incumbent | Defect |
|---|---|
| `accel = pace(1W) − pace(3M)` | the 13-week baseline **contains** the week being measured; the fresh signal enters its own denominator at weight 5/63 and the difference is dominated by the shared 58-day tail |
| `rs_mom = mean(z1W,z1M) − mean(z3M,z6M)` | 1M ⊂ 3M ⊂ 6M, so the "momentum of momentum" is largely one slow, highly autocorrelated component |
| every z-score | computed on raw returns with no volatility scaling, so the cross-section ranks **volatility** as much as trend and high-beta groups permanently occupy both extremes |
| — | nothing knows where a node sits in its own cycle, so "top" and "bottom" are inexpressible; the desk can only say "high or low versus peers right now" |

## 1. What the engine does

**A term structure is a path.** Cumulative returns at nested horizons algebraically
determine the *disjoint* segments between them — `seg(1M ex-1W) = g(1M)/g(1W)` where
`g(h) = 1 + perf[h]/100`. As geometric weekly paces those five segments are a **pace
curve** (oldest → newest); `1/g(h)` at each horizon is a six-knot **level path** normalised
to now = 100. Non-overlapping derivatives come off the curve (impulse, acceleration,
curvature); the cycle facts come off the path (drawdown from the reconstructed 1-year peak,
run off the trough, position in that range, and how old each extreme is).

**A move only means something relative to the tape, in units of the node's own noise.**
`data/themes_heatmap/subsector_perf_history.jsonl` is an append-only PIT archive of the
daily snapshot (irreplaceable — Finviz's full-universe aggregates cannot be rebuilt later).
Its `1D` column is a genuine daily return series, so every turn derivative is measured on
the **excess** pace curve (node − cross-sectional median) and scaled by the node's own
**tracking error** (realised vol of its excess daily return). The same archive lets the
whole read be **replayed** each run, so persistence, confirmation and rotation tails exist
on the first run instead of waiting for a state file to accrue.

**Four independent legs, then a state machine.** `flip` (how big the change is, in this
node's own tracking error, and only if the previous segment ran the other way) · `regime`
(what it turned *from* — how adverse its excess trend was, so a turn out of a beaten-down
trend outranks a wobble in a flat one) · `rs` (how rare the change is across the
cross-section) · `part` (member participation versus the tape). Weighted 0.30/0.20/0.25/0.25
into a bounded [0,1] score; a missing leg abstains rather than voting zero. The score arms a
candidate at 0.45 and confirms at 0.62 held across two sessions (or one reading ≥ 0.80 — V-
recoveries confirm in about three sessions per the Rotation Command field guide, and a
two-session wait spends most of that). Confirmed states need three contrary sessions or a
20-session TTL to leave, then a 10-session lockout stops a still-firing node re-announcing
itself as a fresh turn.

**Cycle position gates; it never scores.** A bottom requires a prior decline, a top a prior
advance, and the extreme turned from must be at least a month old. Both the price path and
the **relative-strength path** (the RS line, reconstructed the same way from excess returns)
supply that precondition, so a theme whose leadership peaked three months ago reads as
rolling over even while its price grinds sideways. Position never contributes sign or size —
postmortem §4.3 documents how a `(50 − pos)/50` state score structurally fades leaders and
buys laggards, and the repo's own PIT evidence (8,344 stamps) found position predicts nothing
at any decile or horizon.

## 2. Defects found and closed while building (each pinned by a test)

Measured on the live 2026-07-30 cross-section. Every item below was a real wrong answer, not
a hypothetical:

1. **Absolute legs read the market, not the rotation.** With turn derivatives measured
   absolutely, one risk-on week put **92 of 268 nodes** into a top state. Relativising the
   pace curve fixed it. (Cross-sectional axes were unaffected — subtracting a cross-sectional
   constant leaves a z-score identical, which is exactly why the axes were already
   market-neutral and the legs were not.) → `test_market_wide_move_fires_nothing`
2. **Weekend archive rows are not sessions.** 6 of 22 archive rows were byte-identical
   repeats of the previous row — on a weekend or holiday Finviz still serves Friday's
   numbers (Sat+Sun+Mon of 07-18..07-20 all carried Friday's snapshot). Counting them handed
   the state machine free confirmations: a candidate armed on Friday "confirmed across three
   sessions" without one new observation, and the repeated `1D` padded the volatility sample
   with a copy of itself. → `test_non_session_rows_do_not_confirm`
3. **A five-day-old low qualified a node as "topping."** +16% off a trough five sessions old
   satisfied the "has run" precondition. The extreme now needs to be ≥ 21 days old. →
   `test_age_gate_blocks_fresh_extreme`
4. **Five legs that were one dimension in a costume.** `flip`/`accel`/`curve` are all
   monotone in the same difference (the newest excess pace dwarfs every older segment,
   ±15%/wk against ±1%/wk), so they maxed out together and scores saturated at 1.000 for
   dozens of nodes, destroying rank information. Replaced by the four independent legs above;
   `flip`↔`regime` correlation is now −0.01. `accel`/`curve` remain as receipts. →
   `test_legs_are_independent`, `test_scores_do_not_saturate_on_real_shaped_input`
5. **Cold volatility inflated every z.** Before `vol_min_obs` daily observations exist the
   noise scale falls back to pace dispersion, which is small; the first sessions of the
   archive replay printed 29 confirmed upturns that decayed to 3 once vol samples existed. A
   cold read may now arm but never confirm. → `test_cold_read_cannot_confirm`
6. **TTL was cosmetic.** A node that never stopped firing re-confirmed on the session after
   TTL expiry, resetting `since` and `age` — a 40-session trend advertised itself as "day 1
   of a fresh turn" forever. Now a lockout blocks re-announcement, released the moment the
   condition genuinely lapses. → `test_confirmed_state_expires_on_ttl_and_cannot_instantly_re_announce`
7. **Float dust made a tie a win.** A member exactly at the market pace counted as beating
   it — the geometric pace of a round 10% week lands at 10.000000000000009. →
   `test_breadth_is_measured_against_the_tape`

Resulting selectivity on 2026-07-30 (a genuinely wide day — cross-sectional p90 of |1W| was
13.4% against 6–8% on a normal session): 4 confirmed upturns, 7 confirmed downturns, 31
bottoming and 40 topping candidates out of 268; at theme grain, 1 confirmed turn up and 1
down out of 40.

## 3. Honest limits

- **Six knots cannot see inside a segment.** An extreme that happened between two horizon
  anchors is invisible, so `pos_in_range` is a lower bound on the true range and peak/trough
  dating is coarse to ±the segment span. Fields carrying that limitation are named `*_approx`
  and the surface says "rebuilt from return windows, so both are approximate".
- **Breadth is today-only.** Member perf is deliberately not archived (it is reconstructable
  from the whole-market store, and ~100 KB/day of duplicated member JSON in git forever fails
  the repo's heavy-store discipline), so participation cannot be replayed. Historical legs
  abstain on it.
- **Theme back-history uses today's membership.** The archive is subsector-grain, so a
  theme's history is re-aggregated with the current tree for every past day. A theme that
  gained a subsector last week has it in its back-history too. `tree_history.jsonl` exists;
  re-deriving PIT membership is a separate job.
- **Thresholds are interpretable, not fitted.** There is no forward data to fit to yet. They
  are round points on a bounded score, pre-set before any forward return was examined, and
  the ledger below is what will judge them.
- **The archive is 17 distinct sessions deep** (22 rows, 5 non-sessions) as of 2026-07-30 and
  grows nightly. `warm` is published; the surface discloses provisional reads.

## 4. Rotation-universe nominations (why the frozen registry is not touched)

Confirmed turns are paired into **handoff nominations** — a rolling-over donor and a turning
receiver inside the same theme, with receipts — written to
`site/marketdata/subsector_turns.json` and accrued in
`data/subsector_rotation/universe_nominations.jsonl`.

`config/rotation_universe.json` is **not modified**. It is pre-registered under
`research/ROTATION_UNIVERSE_EXTENSION_PREREG.md` (registered 2026-07-18, registry hash in the
doc), and that prereg resets the promotion clock for each family with `n` starting at 0;
adding series to a pre-registered detector universe would void its accrual. Nominations
accrue their own census instead, so a future extension can adopt a candidate that already has
history on the board. This is the "reflect quickly into the rotation universe" path that does
not cost the prereg.

## 5. Falsifiability — the head-to-head

`engine/subsector_track_record.py` now logs the turn engine's rank (`score_v2`) and stage
(`stage_v2`) beside the incumbent's on every snapshot row, and grades both on the **same**
matured rows, the same hit rule, and the same Newey-West lag. `track_record.head_to_head`
prints both information coefficients, the gap, and both HAC t-statistics per horizon, and
declares no winner until the turn columns reach the same matured-n floor any promotion needs.

This matters because the incumbent is not a straw man: as of 2026-07-30 its measured rank IC
is +0.14 / +0.25 / +0.27 at 5/10/21 days over 1,912–4,319 matured observations. The turn
engine ships because its arithmetic is defensible, **not** because it has out-scored anything.
Rows logged before this shipped carry no v2 columns and simply do not accrue to them, so the
two columns can legitimately disagree on `n` — disclosed, not averaged away.

## 6. Surfaces

- **`subsector_rotation.html` — "Turns this week" rail** (between the map and the versus
  scorecard): confirmed up / confirmed down columns, a still-forming chip strip, handoff
  pairs, one merged footnote. Per `docs/DESIGN_DOCTRINE.md`: plain state words, numbers that
  arrive with their meaning ("fell 12% · 10 of 11 turning · day 2"), one stance ("Watch —
  don't chase"), and every mechanic — legs, tracking error, thresholds — demoted to the
  hover receipt and the `?` tip. No falsifier or refutation language anywhere (operator
  2026-07-27). The rail follows the unit toggle, so subsectors / themes / sector ETFs each
  read their own turn summary, and it hides entirely on a payload without a turn block.
- **Range notch**: each row carries the node's reconstructed 1-year range as a track with a
  marker where it sits now, whose glyph carries the direction it just turned.
- **Table**: `Turn` and `In range` columns, both sortable.
- **Alerts**: `rotation_turn_up` / `rotation_turn_down` fire once on the transition into a
  confirmed state, with severity from **size and breadth** (RC-R5 — the desk previously fired
  21 alerts a run, all `minor`, so the one that mattered was indistinguishable). A single-name
  move cannot print `high` however violent its z-score.

## 7. Deliberate non-goals

- **The China twin** (`subsector_rotation_china.html`) is untouched and degrades gracefully —
  the rail hides. It has no PIT perf archive, and deriving history from its normalised level
  series while today's numbers come from the basket perf snapshot would mix sources at the
  seam and manufacture turns at the join. It needs its own archive first.
- **No stance, gate or sizing change anywhere.** The double gate, the marker lane and the
  sector conviction channel are as they were. RC-R8/R9's pre-registered studies remain the
  only path to authority for any of this.

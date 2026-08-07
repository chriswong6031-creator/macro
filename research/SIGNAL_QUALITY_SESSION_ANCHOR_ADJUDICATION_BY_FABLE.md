# Absolute session anchor for the §7 signal_quality master — adjudication

**Date:** 2026-08-06 · **Adjudicator:** Fable (main loop) · **Charter:** amendment A3 of
`research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md` (the confluence anchor
ruling): repair the sibling defect in the §7 marker engine, as its own charter with its own
era stamp. **Era stamp:** `sq-abs-session-2026-08-06` (DT-R16 family — a dated
graded-population change, labelled forever, never silent; `abs-session-2026-08-06` covers
ONLY `confluence_tiers`' buckets and does NOT cover this change).

## The defect (verified, reproduced in-PR)

`engine/signal_quality.py` — the VALIDATED §7 marker engine whose `take_active`/`take_date`
feed INTO the cascade through `signal_gate.gate()` — still built its grids with pandas
`resample("3B"/"2B")`, whose bin edges anchor to the SERIES' FIRST timestamp, at four sites:
the 3D main grid (`signal_frame`), the 2D early-anticipation leg, the 3D high/low band, and
`_bucket_last_session` (the `confirmation_date` geometry). So while the CASCADE layer is
start-invariant since `abs-session-2026-08-06` (measured 0/0/0), `gate()` END-TO-END was not.

Measured tonight (2026-08-06 tape, `gate()` end-to-end, dropping k leading bars):

* **k=1, data/stocks (238 graded):** 238/238 (100%) move their last §7 marker date;
  91 (38%) change the last marker's IDENTITY (type/quality — e.g. PEP `buy/block`↔`cut`,
  SW `sell`↔`rebuy/block`, WMT `block`↔`pending`); 95 flip `ticks` (PEP 8→4, SW 16→4 —
  the same names A3 recorded at 7→3/15→3 on the 08-05 tape); 11 flip gate ELIGIBILITY;
  3 flip the final `is_buyable` board verdict.
* **any k in 1..6:** 127/238 (53%) change last-marker identity, 125 flip ticks, 18 flip
  eligibility, 6 flip buyable. k=3/k=6 mostly (not fully) return to base — the mod-3
  bin-phase mechanism, with holiday placement breaking pure periodicity: the bins are
  bdate-grid bins, so they also MIS-SPLIT buckets at every market holiday (the same defect
  `engine/canon.py::resample_sessions`' docstring records as relocating ~80% of NVDA signal
  dates).
* **k=1, data/baskets/ohlcv (2,696 graded — the 2014-start loader):** 2,696/2,696 move
  the last marker date; 935 (35%) flip identity; 1,038 flip ticks; **130 flip gate
  ELIGIBILITY (4.8%)**; **59 flip the final buyable verdict (2.2%)**. Any k≤6: 1,271
  identity flips (47%), 241 eligibility (8.9%), 86 buyable (3.2%). The cross-store
  symptom shows directly: ohlcv-ECL's base read (`rebuy/block`, ticks 4) equals the deep
  store's k=1 slice, while the deep store's base reads `buy/block` 2026-06-02 ticks 16 —
  one name, one night, two §7 stories, pure phase.

The four production history depths that reach `gate()` (deep stores; 345/777-bar caches;
2014-start ohlcv; 2021-start scan tier) therefore each read a DIFFERENT §7 marker stream for
the same name — the two main US loaders disagree about the §7 layer the same night the
cascade layer now agrees.

## What "validated" currently rests on (measured, not assumed)

The lineage cited in docstrings (`signal_quality`, `signal_gate`, `track_record`): the
buy-filter cut avg loose-hold max-DD **−23.7% → −15.5%, shallower on 84%** of the then-110
held-out US names (`research/signal_engine/test_buyfilter.py`). Three facts about that
lineage tonight:

1. **The research validation construction is NOT the production construction.** The
   research twin (`research/signal_engine/confluence.py`) retired `resample("3B")` for
   session-grouped 3D bars long ago ("~80% of NVDA signal dates relocated"; verified 5/5
   against TradingView 3D crosshairs), phase-anchored at the symbol's IPO, labelled by
   bucket OPEN date. Production `signal_quality` was the LAGGARD still carrying calendar
   bins. This repair moves production TOWARD the validated research geometry, not away.
2. **The stop-aware gold harness (`walk_forward.py --gold`) as shipped drops ~67% of 3D
   known-dates** (measured AAPL/NUE/PEP: 67.3–67.6%): its `tf_bars` still labels by
   `resample("3B")` bins and exact-match-reindexes onto `confluence`'s session-grouped
   OPEN-date labels, so two diverging label systems only coincide when the cumulative
   holiday count since series start ≡ 0 (mod 3). Its absolute numbers are a subsample
   artifact (14 vs ~47 trades/name against a locally-fixed harness). Chipped for its own
   repair; NOT this PR's scope. Verdict direction happens to survive the fix (REJECT both
   ways — see below), but the margin moves 44%→58%.
3. **The panel drifted 110 → 238 names** since the citation. Tonight's numbers are the
   238-name re-read.

## Re-validation (the promotion-gate lens applied to the change itself)

Both validation constructions were re-run OLD′-vs-NEW with everything held fixed except the
bucket phase (scratch harness recorded in the PR body; OLD′ = series-start session phase,
NEW = absolute `session_positions // 3`):

* **Drawdown lineage (the citation's own construction, `test_buyfilter` geometry):**
  OLD′ −24.2→−15.0, filter shallower on 87% (strict 86%); NEW −24.7→−15.3, shallower on 82%
  (strict −24.9→−15.5, 82%); citation −23.7→−15.5, 84%. The claim REPRODUCES under the
  absolute anchor.
* **Stop-aware gold (locally-fixed known-date geometry):** stop-out raw→filtered
  41.95→39.65 (OLD′) vs 42.94→40.02 (NEW); OOS frac-improved 0.59 vs 0.61; trades/name
  46.7→17.7 vs 46.5→17.7; attribution (selection-only improves) 85% vs 84%; kill-rule
  verdict IDENTICAL (REJECT at the 70% bar — the stop-aware doctrine's standing
  recommendation to ship the simpler baseline is a pre-existing research matter, untouched
  and unchanged by the anchor in either direction).

Every metric moves ≤1.1pp between phases while the filter's measured effects reproduce.
**Ruling: the anchor is a de-noising of an arbitrary phase realization, not a behavioral
revision.** The validated property transfers; the docstring citations become PRE-era
citations carried beside the post-era re-read (both quoted, never silently re-baked).

## Rulings

**R-SQ1 — One calendar: reuse `engine.session_anchor` (R1–R3) verbatim.**
`bucket(d) = session_positions(d, market) // n`. `analyze()` infers `market` from its own
`ticker` argument via `session_anchor.market_for_ticker` (no caller edits);
`signal_frame`, `confirmation_date`, `fresh_breach_mask` gain a keyword-only
`market="US"` threaded by their callers where the ticker is known (`hk_board_rank` passes
HK). REJECTED: the research twin's per-name IPO anchor (TradingView parity). Production
loaders feed truncated windows with no IPO knowledge; `ipo_bar_anchor`'s deep-store lookup
is a data dependency that silently falls back to 0 when the store is absent (the
fallback-chain disease), and a vendor-revised first row would re-phase every bucket (the R1
argument). The research twin KEEPS its IPO anchor for TV-parity work — a different purpose;
the two grids coincide for names whose IPO session position ≡ 0 (mod 3), and §7 markers
were never TV-phased in production (they were loader-phased calendar bins).

**R-SQ2 — Labels: a bucket is labelled by its OPEN date** — the first TRADED session of the
bucket (the research twin's TV-timestamp convention). This preserves the §7 public
semantics: the charter's "Dates are 3D bar dates" becomes literally true (the old synthetic
bin edges could be holidays); the marker keeps sitting at the trough that created the
signal; `_ticks_since`/`_bars_since` keep their calibrated off-by-one conventions, so there
is NO systematic freshness-window shift. REJECTED: known-date labels (the
`confluence_tiers._tf_bars` internal convention) — they would systematically age every take
by one fewer tick and silently widen the freshness gate ~3 sessions; label conventions are
consumer-driven, and unlike the cascade's internal grid, §7 labels ARE the public contract.

**R-SQ3 — Era stamp.** `signal_quality.ANCHOR_ERA = "sq-abs-session-2026-08-06"`, emitted
as `anchor_era` on every `analyze()` §7 payload (site/signals/<T>.json and the brain-leaf
rows inherit it), and copied by `signal_gate` onto every verdict as `sq_anchor_era` —
riding beside the cascade's `anchor_era` in `_VERDICT_KEYS` and `_BUY_KEYS` exactly as
`young_history` travels. A verdict is jointly produced by two bucketing eras (the cascade's
grid and the §7 stream's grid); a graded record must be able to place a row against BOTH.
Ledger history: no backfill, no retro-edit; rows logged pre-era keep their dates, and the
era field is the cohort boundary (the emitter-fix-cannot-heal-logged-rows law).

**R-SQ4 — The marker stream re-draws ONCE, disclosed, era-stamped.** Under the new anchor
most names' §7 histories re-phase (marker dates move 0–2 sessions; some crosses appear or
vanish where 3D closes change). This is the one-time cost of removing the loader-phase
dependence, and it is measured per production loader in the committed blast-radius report
(`reports/sq_anchor_blast_radius.md`), including the ledger re-key surface: the count of
names whose CURRENT open `take_date` moves, per lane. Forward ledgers grade new rows under
the new era; frozen research packets are untouched and cited era-explicitly.

**R-SQ5 — canon / Terminal: untouched (R8 upheld).** `engine/canon.py::resample_sessions`
(the golden oracle `golden_gate` pins 1:1 to the Terminal's `compute_signals`) is NOT
changed — `signal_quality` is not the golden oracle. The Terminal's own computed overlays
remain series-ordinal-grouped and therefore still phase to the Terminal's loaded window —
a PRE-EXISTING divergence this PR neither creates nor fixes; it stays flagged for the
Terminal's own adjudication (the R8 flag stands). The §7 site JSONs the charting layer
READS re-draw once under R-SQ4 like every other §7 consumer.

**R-SQ6 — What does NOT change.** The W-FRI weekly leg (calendar-absolute, R8 precedent).
Every filter semantic: `_buy_filter`/`_confirm_legs`/`_bear_div`/`_swing_highs`,
`CONFIRM_BARS = 2`, the reclaim-veto policy switch, reason strings — byte-identical. The
90-bucket / 5-row floors (self-disclosing via `analyze() → None` → "insufficient history";
the phase-worst-case boundary shift is ±1 bucket ≈ 3 daily bars, measured in the blast
radius). `fresh_breach_mask`/`risk_flags`/`early_markers` semantics (they ride the same
grids). The research twin (`research/signal_engine/confluence.py`) and its IPO anchor.
`walk_forward.py` (chipped separately). Ledger history.

**R-SQ7 — The rendered stream crosses the era ONCE, by law, not by accident
(`engine/marker_integrity.py` made era-aware).** RC-R2's append-only merge law exists to
stop UNEXPLAINED nightly mutation of rendered §7 history — and it would otherwise absorb
this repair: a re-dated marker within `TOL_DAYS=4` keeps its old rendered date forever, a
legitimately re-phased historical marker beyond tolerance is DROPPED (`drift_deep_new`) or
ghost-RETAINED (`drift_lost`), so the invariance property would never reach
`site/signals/<T>.json` while every live `gate()` consumer (boards, HK/CN lanes) moved to
the new grid immediately — a permanent split-brain between the chart record and the boards,
plus a one-time drift-counter burst burying real future drift. Ruling: `analyze()`'s
`anchor_era` is stored in the payload, and `merge_payload` compares eras: on MISMATCH the
merge yields exactly once — tonight's recompute replaces the marker history wholesale, and
`pit["era_cutover"]` records `{from, to, at_asof, prev_markers}` forever — then the
append-only law resumes under the new era. A labelled, adjudicated era change is the
explained mutation RC-R2's law anticipates (the same doctrine as
`regen_hk_g1_fixture --force`: "an engine-change PR knows itself"); unexplained re-datings
stay blocked exactly as before, and under the absolute anchor the nightly recompute jitter
RC-R2 was built against is structurally gone.

**R-SQ8 — The track-record ledger crosses the era without re-keying.**
`engine/track_record.py`'s identity is literally `(ticker, marker date, type)`,
keep-FIRST, append-only, never-purge — and it ingests the full (post-R-SQ7, freshly
re-dated) marker files, so with no guard the cutover would mint a duplicate row beside
every pre-era row whose marker date moved: permanent double-counting of the same physical
event. Ruling: ingestion gains the era floor `SQ_ANCHOR_ERA_FLOOR = "2026-08-06"` — a NEW
key is appended only if its marker date is ON/AFTER the floor AND no existing row of the
same `(ticker, type)` sits within 4 calendar days (the boundary-week guard, mirroring
`TOL_DAYS`); pre-floor history in tonight's file is treated as the re-dated image of
already-logged events, never as new events. **Implementation amendment (build 2026-08-06,
accepted):** the floor is SCOPED TO ITS OWN PREMISE — a pre-floor key is refused only for
a ticker that ALREADY HAS logged rows, because "re-dated image of an already-logged event"
is only true where the ledger was recording the name at the time. An unscoped floor would
have made the store non-reconstructable (a rebuilt ledger and every backtest fixture would
log zero rows); on the live ledger every ticker has history, so the protection is
unchanged. Skips are counted and named (`pre_era_marker` / `boundary_week_duplicate`),
never a silent continue, and the guard's index is snapshotted BEFORE ingestion so rows
appended during a run cannot suppress a genuine later print in the same file. Existing
rows keep maturing normally (fills touch only null maturation columns). New rows gain an
`anchor_era` column so the graded record can fence cohorts forever. Pre-era rows are never
edited (the emitter-fix-cannot-heal-logged-rows law).

## Consumer surfaces (censused 2026-08-06, verified at the cited lines)

* **Chart layer:** `site/chart.js` `mapMarkers()` already snaps a marker to the first bar
  with `time >= date` and drops out-of-window dates — robust to the re-draw; no chart-side
  change. (Its own 3D candles resample `floor(i/3)` over the LOADED window — client-side
  start-anchoring, a separate display-grid follow-up chartered outside this PR.)
* **`scripts/regen_hk_g1_fixture.py`** is the designed tripwire: its `classify()` REFUSES a
  re-pin when verdicts change while stored closes did not — this PR runs `--force`
  deliberately and commits the regenerated fixture; the
  `test_every_frozen_window_starts_on_a_3b_bucket_boundary` pin guards the OLD phase
  invariant (moot under an absolute anchor) and is retired/replaced with rationale in-PR.
* **Insulated by design (verified):** `china_standout_track` (asof-keyed, marker-date
  grading forbidden), `board_ledger` (asof-keyed; `gate_ver`/`board_definition` fences),
  `grade_us_board` retro grades (`as_of` keys), `congress_entry`/`htf_oscillators` (pure
  math imports on their own epoch grids), `validate_signals` (order-only),
  `t0_indicator`/`us_board_rank`/`hk_board_rank` (recomputed display, no marker-date keys).
* **Auto-inheriting:** `rule_replay` and `dump_breakdown_events` call
  `signal_frame`/`fresh_breach_mask` live — historical re-runs shift once with the era
  (rule_replay's `vintage_stamp` discipline and the breakdown summary's vintage note carry
  the disclosure).
* **Follow-ups chartered separately (not this PR):** `engine/bar_derive.py`'s claim that
  its own `resample("2B"/"3B")` candles equal `signal_frame`'s grid becomes false — the
  display-grid alignment charter covers bar_derive + chart.js `floor(i/3)` together;
  `board_ledger._SCHEMA` carries NEITHER anchor era (columns must be added explicitly —
  its reindex silently drops unlisted columns); `signal_gate.write_signal_file` has zero
  callers (dead §7 API, retire deliberately).

## Sibling triage (charter item 4 — measured 2026-08-06, 99 deep US names, k = bars dropped)

Every A3 sibling carries the defect materially; the mod-2/mod-3 near-recovery at k=2/k=3
fingerprints the bin-phase mechanism in each:

| probe (grid) | k=1 flips | k=2 | k=3 |
|---|---:|---:|---:|
| `coiled.washout_ctx` (3B) | 0 | 0 | 0 |
| `coiled.bull_div` (3B) | 10 | 10 | 0 |
| `coiled.fire_recent` (3B+2B) | 70 | 27 | 67 |
| `mtf_upturn._build_trend_fields.d3` (3B) | 49 | 56 | 5 |
| `mtf_upturn._leg_d3_confluence` (3B via signal_frame*) | 8 | 7 | 0 |
| `leader_lifecycle.tf_state_2d` (2B) | 93 | 7 | 90 |
| `cycles._tf_state` on 3B (line ~2534 shape) | 99 | 92 | 9 |
| `pick_lab.signals_1d.compute_grids` d2 (panel 2B) | 60/60 rows | 5 | 60 |

*`_leg_d3_confluence` consumes `signal_quality.signal_frame`, so THIS PR's repair fixes
that leg automatically; `mtf_upturn`'s own `resample("3B")` proxy (line ~327) remains.

**Census correction — A3's list was one site short.** `engine/cycles.py::mtf_snapshot`
(line ~331) resamples with a PARAMETERIZED freq (`tf3 = CYCLE_PRESETS[kind]["tf3"] =
"3B"`), which is why the literal `resample("3B")` grep missed it — and it is the
highest-stakes carrier of the class: its `mtf["3D"]` feeds `mtf_alignment()`, the
standout strip's SELECTION filter (the shipped `bottoming-alignment` rank key on every
US/CN/HK/CA board, nightly), off the same deep-store-vs-rolling-breadth-cache loader mix,
and its ladder state persists to `data/ticker_alerts/ladder_log.parquet` keyed
`(asset, signal_date, state)` — a window-drift state flip inserts a phantom transition
row dedup cannot suppress. The breadth caches' start CREEPS forward every refresh
(`collectors/breadth.py:446`), so these grids re-phase build-to-build with zero price
action. A seventh same-class site: `scripts/build_hk_library.py:~2077`'s own raw 3B
resample for `d3_macd_xup_bars`. Lesson for future sweeps: grep `resample(` with variable
frequencies too, never only the literals.

**Verdict: chartered follow-ups, not folded in.** The A3 rule that gave signal_quality
its own charter binds here symmetrically — each group has its own consumer surface, era
stamp, and blast measurement. Chips filed 2026-08-06 with tonight's numbers and the
census's cited surfaces: (1) **cycles `mtf_snapshot`/`tf3` + `calibrate_ladder` +
`leader_lifecycle.tf_state_2d`** (board admission gate; phantom ladder-log rows;
intra-run re-anchoring walk-forward — HIGHEST priority, repair-next); (2) **coiled
`bull_div`/`fire_recent` + mtf_upturn `trend.d3`** (standout-board rank bonus +
day-diffed `fire_ticks`; display chip); (3) **pick_lab `compute_grids` d2 +
build_hk_library's 3B site** (never-backfilled PIT snapshot contamination; no live gate
reads d2 yet — fix before one does). `washout_ctx` measured insensitive (0 flips) —
no action. `mtf_upturn._leg_d3_confluence` heals via THIS PR (it consumes
`signal_quality.signal_frame`); its forward ledger is clean (keys `(symbol, session)`,
carries no `trend`). The display-grid pair (`bar_derive` + chart.js `floor(i/3)`) and
the board_ledger era columns are chartered separately above.

## Ship requirements (all in this PR)

1. **Blast radius, committed:** `scripts/measure_sq_anchor_blast_radius.py` →
   `reports/sq_anchor_blast_radius.md` + `.json`. Old-vs-new per production loader
   (stocks/, ohlcv/, 345/777-bar depth views, CN panel, HK stores, scan tier where
   restored): last-marker date/identity moves, take/ticks/eligibility/buyable flips,
   stocks∩ohlcv agreement BEFORE and AFTER on the §7 layer (target: 0 after, quintet named),
   open-take re-key counts, and a NEW-anchor start-invariance re-run (must be 0 flips).
2. Era stamp per R-SQ3.
3. `tests/test_sq_anchor_invariance.py`: `analyze(c) == analyze(c.iloc[k:])` k=1..6 on
   marker stream, risk_flags, early_markers, state fields (asof exempt only when the
   truncation eats the first bucket — it cannot, k≤6 < warmup); `gate()` end-to-end
   invariance on verdict fields; real-NYSE holiday-span fixtures per the confluence battery
   pattern; label-convention pins (labels are traded sessions; OPEN-date semantics).
4. `tests/test_signal_quality_no_leak.py`: the geometry re-derivation test rewritten
   against the anchored geometry (same structural pins, new independent derivation);
   everything else in the suite must pass UNCHANGED (the look-ahead facts are
   construction-independent).
5. Downstream suite green (`signal_gate`, boards, ledgers, replay consumers).
6. R-SQ7: `marker_integrity` era-aware cutover + tests (era flip → fresh history wins once,
   `pit["era_cutover"]` recorded; same era → the incumbent law byte-identical, existing
   suite untouched).
7. R-SQ8: `track_record` era floor + boundary-week guard + `anchor_era` column + tests
   (re-dated pre-floor history → zero new rows; fresh post-floor marker → appended once;
   maturation fills untouched).
8. `regen_hk_g1_fixture --force` run; fixture committed; the 3B-phase boundary test
   retired/replaced with rationale.
9. Ship loop per repo law; this document + the measurement report are the PR's evidence.

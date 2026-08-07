# Absolute session anchor for the cycle-ladder grids — adjudication

**Date:** 2026-08-06 · **Adjudicator:** Fable (main loop) · **Charter:** sibling-triage
group (1) of `research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`
(chip 2026-08-06, "HIGHEST priority, repair-next"), itself amendment A3 of
`research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`. **Era stamp:**
`cyc-abs-session-2026-08-06` (DT-R16 family — a dated graded-population change, labelled
forever, never silent; `abs-session-2026-08-06` covers ONLY `confluence_tiers`' buckets and
`sq-abs-session-2026-08-06` ONLY `signal_quality`'s; neither covers these grids).

## The defect (verified; measured by the sibling triage 2026-08-06, session musing-driscoll)

Three grids under the cycle-ladder family still cut n-session bars with pandas
`resample`, whose bin edges anchor to the SERIES' FIRST timestamp:

1. **`engine/cycles.py::mtf_snapshot` (line ~331)** — `daily.resample(tf3)` with
   `tf3 = CYCLE_PRESETS[kind]["tf3"]`, a PARAMETERIZED freq (`"3B"` equity/fx, `"3D"`
   crypto), which is why A3's literal `resample("3B")` grep missed it. Measured: the 3B
   grid's `cycles._tf_state` flips on **99/99** deep US names at k=1 leading-bar drop
   (92 at k=2, 9 at k=3 — the mod-3 bin-phase fingerprint).
2. **`engine/cycles.py::calibrate_ladder` (line ~2534)** — its own `sub.resample("3B")`
   on a walk-forward window whose START slides every `step=5` bars (5 mod 3 = 2), so the
   grid re-phases INTRA-RUN: the per-state forward stats shipped to the UI were measured
   on a state machine whose 3D leg jittered with the window, not with price.
   `signal_age()` walks the same trailing-600 window back per day, so the state-flip date
   it derives (`signal_date` — the ladder-log key) compares a full-history grid against
   per-step re-phased grids.
3. **`engine/leader_lifecycle.py::tf_state_2d` (line ~685)** — `resample("2B")` into the
   same `cycles._tf_state`. Measured: flips **93/99** at k=1 (7 at k=2, 90 at k=3 — the
   mod-2 fingerprint). Folded into this charter because it consumes the same `_tf_state`
   and rides the same payload family; same era stamp.

Why it is the highest-stakes carrier of the class: `mtf_snapshot`'s `mtf["3D"]` feeds
`ladder_state()` AND `mtf_alignment()` — by its own docstring the standout strip's
SELECTION filter, the shipped `bottoming-alignment` rank key on every US/CN/HK/CA board
(`scripts/us_board_studies.py:36` notes it was never fed to any validation harness) —
called nightly per name by build_stock_library / build_china_library / build_hk_library /
build_canada_library / build_intl_library / build_site. The loaders mix deep stores with
ROLLING ~3y breadth caches whose start CREEPS forward every refresh
(`collectors/breadth.py:446`), so admission verdicts could differ by loader depth
same-night and re-phase build-to-build with zero price action. The ladder state persists
to `data/ticker_alerts/ladder_log.parquet` keyed `(asset, signal_date, state)` — a
window-drift state flip or a walk-back `signal_date` jitter inserts a PHANTOM transition
row that the dedup key cannot suppress (`engine/ticker_alerts.py:399-429`, rendered on
every ticker page by `ladder_history_events`).

## Rulings

**R-CY1 — One calendar: reuse `engine.session_anchor` (R1–R3) verbatim; crypto gets the
epoch-day anchor.** For session-bar freqs (`"3B"`, `"2B"`):
`bucket(d) = session_anchor.session_positions(d, market) // n`. For crypto's
calendar-day freq (`"3D"`, a 7-day/week series): pandas fixed-freq bins default to
`origin='start_day'` — the SAME series-start disease — so the bucket id is
`(d − 1970-01-01).days // 3`, absolute epoch arithmetic with zero data dependencies
(the R6 fortnight idiom one level down). A session CALENDAR would be wrong for a 24/7
asset, exactly as the CYCLE_PRESETS comment already records for `"3B"` on crypto.

**R-CY2 — Labels are internal here; buckets are labelled by their last TRADED session.**
Unlike §7 markers (R-SQ2: labels ARE the public contract), nothing downstream reads the
3D/2B bar INDEX: `_tf_state` consumes values positionally from the end and emits scalars;
`mtf_snapshot` returns dicts with no dates; `mtf_alignment`/`ladder_state`/`tf_state_2d`
consume those dicts. The A4 label-arithmetic sweep for this family found zero consumers.
The helper labels each bucket by its last traded session (the `confluence_tiers._tf_bars`
convention) and the invariance battery pins the geometry so a future consumer inherits a
pinned contract rather than an accident.

**R-CY3 — Market routing.** `mtf_snapshot`, `analyze`, `signal_age` gain keyword
`market: str = "US"`; the nightly builders pass it where the market is static
(`build_china_library`/`build_china` → `"CN"`, `build_hk_library`/`build_hk` → `"HK"`,
`build_canada_library`/`build_canada` → `"CA"`). `calibrate_ladder` gains
`market: str = "US"` threaded to every window (its panels are single-market by
construction: `scripts/calibrate_china.py` passes `"CN"`, `scripts/calibrate_hk.py`
`"HK"`; per-name suffix inference was REJECTED because the HK/CN panels mix suffixed
constituents with unsuffixed index tickers, which would silently split one panel across
two calendars). `tf_state_2d` gains `market: str = "US"` for symmetry (its leader-radar
callers are US). FX (`kind="fx"`) routes to the US reference, disclosed: FX has no
exchange calendar; sessions absent from the reference (an FX bar on a NYSE holiday)
deterministically share the next reference session's bucket (R2's absent-date rule) —
the same approximation class the old `"3B"` bins applied everywhere, now fixed instead
of floating. The intl library keeps the US reference (R1, disclosed).

**R-CY4 — Era stamp.** `cycles.ANCHOR_ERA = "cyc-abs-session-2026-08-06"`, emitted as
(a) `cycle_anchor_era` on every `analyze()` return (top level — named distinctly because
the libraries spread that dict into a record (`**res`) whose `confluence` block carries
the CASCADE's own `anchor_era`, and a graded row must be placeable against BOTH eras,
the R-SQ3 doctrine), and as `anchor_era` on (b) every `ladder_state()`
payload — the dict the libraries persist and the ladder log ingests, (c) every ladder-log
row (`ticker_alerts.ladder_row` copies it; the parquet gains the column, pre-era rows
read null — the cohort fence), (d) `calibrate_ladder()`'s per-state cells (`anchor_era`
INSIDE each state's stats dict — the artifact's top level is iterated by state-name
consumers, so a top-level key would masquerade as a state). NOT stamped inside the `mtf`
dict itself: `build_china`/`build_hk`/`build_canada` JSON-dump `a["mtf"]` wholesale into
`mtf_json` payloads whose client iterates timeframe keys — a foreign key there is a
display hazard with zero fencing value; the analyze-level stamp covers those payloads.
`leader_lifecycle.tf_state_2d` rides the same era string (imported constant), disclosed
in its docstring; its radar payload is rebuilt nightly with no accruing key, so no
per-row stamp. Pre-era numbers cited in docstrings (`ladder_calibration.json` trust
tables, `research/ENTRY_QUALITY.md` stats) are PRE-era measurements — re-baked by the
next scheduled recalibration under the new era, never silently.

**R-CY5 — The ladder log crosses the era ONCE; the boundary guard is scoped to the era
seam (the R-SQ8 pattern).** No retro-edits: pre-era rows keep their dates and their null
`anchor_era` forever (the emitter-fix-cannot-heal-logged-rows law). At cutover two row
classes appear: (i) genuine state re-draws (old grid read A, absolute grid reads B) —
these APPEND normally, prev_state intact: the read really was updated, and the timeline
records it; (ii) pure `signal_date` RE-KEYS — same asset, same state, a walk-back date
moved 1–3 sessions — which the `(asset, signal_date, state)` dedup would mint as a
duplicate "Signal: X" card days apart. Ruling: `write_ladder_log_batch` refuses a row
whose `(asset, state)` already has a row within **4 calendar days** (mirroring
`TOL_DAYS`) **when the eras differ** (stored era null/different vs incoming) — scoped to
its premise exactly as R-SQ8's floor was: after cutover every stored row carries the era,
the guard goes dormant, and a genuine same-era whipsaw (A→B→A inside 4 days) still
appends. Skips are counted and returned (`era_rekey_skips`), logged by the batch writer,
never a silent continue.

**R-CY6 — `calibrate_ladder` and `signal_age` heal structurally; the healing is
asserted, not assumed.** Once buckets are absolute, `position // n` is
window-independent: every walk-forward step and every walk-back day reads THE grid, so
the intra-run re-phasing (defect 2) vanishes with no further code. Two assertions pin
it: (a) the invariance battery proves the bucketed bars of a slid window equal the fixed
window's on their shared tail (exact, deterministic); (b) the blast-radius report runs
the fixed-vs-slid state comparison old-vs-new and prints the agreement improvement —
the residual disagreement under the new anchor is EWM warm-up memory (the confluence
battery's named residual), which decays with depth and is not the structural defect.

**R-CY7 — Warmup floors re-checked phase-worst-case; none move.** The gates are
`len(daily) > 150` for the 3D leg (worst-phase bucket count 150//3 = 50 ≥ `_tf_state`'s
40-bar floor), `len(daily) ≥ 80` for `tf_state_2d` (80//2 = 40, exactly the floor), and
`_tf_state`'s own `len < 40` bow-out — all satisfied at every reference phase, so no
R7-style floor re-measurement is triggered. The M/W gates ride calendar-absolute freqs
and are untouched.

**R-CY8 — Folded in: `commodity_mtf._long_timeframes`' fortnight phase (the R6 idiom).**
Census addendum (this adjudication, 2026-08-06): `engine/commodity_mtf.py:43` builds its
`"2W"` chip row with `daily.resample("2W-FRI")` — W-FRI is calendar-absolute but the
PAIRING of weeks into fortnights phases to the series start (the exact R6 defect,
repaired for `confluence_tiers` with the epoch-Friday absolute fortnight id). It feeds
`cycles._tf_state` and ships inside the same `a["mtf"]` payload family through the
commodity and FX cards, so it rides THIS era: fixed here with the absolute fortnight id
`((week_friday − 1970-01-02).days) // 14`, live-tail semantics preserved (no
completed-only change), pinned by its own invariance test. Display-chip surface, no
admission gate, no ledger — synthetic invariance is the proportionate evidence.

**R-CY9 — What does NOT change.** W-FRI weekly and ME monthly legs everywhere
(calendar-absolute; R8 precedent). `engine/canon.py` (the Terminal's golden oracle — R8
stands). Every ladder/alignment SEMANTIC: states, thresholds, `_tf_phase`,
`_three_day_fresh`, `_daily_trigger`, `_overextended`, scores, copy — byte-identical
given the same bars. `cycle_state`/`find_troughs` (daily + W-FRI structure math; no
n-session bins). The ladder log's history (R-CY5). The research twin and every frozen
packet. Out of scope, censused and chartered separately (the A3 symmetry rule): group
(2) `coiled.py` + `mtf_upturn.py:328`; group (3) `pick_lab/signals_1d.py` +
`build_hk_library.py`'s raw 3B site; the display-grid pair (`bar_derive` + chart.js);
and the census addenda found by this adjudication's variable-freq + fortnight sweeps,
each carrying its own consumer surface and needing its own era stamp:
`engine/btc_signals.py:427`'s `resample("3D")` (crypto cockpit surface);
`engine/advanced_indicators.py::_resample` (`TF3="3B"`, defensive-rotation research
surface); and the remaining START-PHASED FORTNIGHT sites `engine/setup_tier.py:153`,
`engine/entry_primitives.py:795`, `engine/btc_mtf.py:28` (`2W-MON`), and
`scripts/build_china_library.py:2045/3077/3105` (the 2W StochRSI washout flag) — the
repo already carries the repaired idiom for that class
(`engine/htf_durability._biweekly_close`, which FORBIDS raw `resample("2W-FRI")` for
exactly this drift), so those repairs are mechanical adoptions of an in-house
precedent, chartered as a follow-up chip with this document as the census record.

## Ship requirements (all in this PR)

1. **Blast radius, committed:** `scripts/measure_cycles_anchor_blast_radius.py` →
   `reports/cycles_anchor_blast_radius.md` + `.json`. Old-vs-new per production loader
   (data/stocks deep, baskets/ohlcv 2014-start, breadth-cache depth views as available,
   CN/HK/CA stores): `mtf_alignment` tier/admission flips (the board SELECTION surface),
   ladder state flips, `signal_date` re-key counts (the phantom-row surface, i.e. the
   cutover's one-time ladder-log insertion bound), `calibrate_ladder` old-vs-new
   per-state table drift on the recalibrate panel shape, fixed-vs-slid agreement
   old-vs-new (R-CY6b), and a NEW-anchor start-invariance re-run (must be 0 movers).
2. Era stamp per R-CY4.
3. `tests/test_cycles_anchor_invariance.py` mirroring the confluence battery:
   grid invariance k=1..6 (exact) on real-NYSE fixtures incl. holiday spans and halts;
   `mtf_snapshot`/`analyze` field invariance deep (bit-exact) and shallow (anchor fields
   exact); crypto epoch-day grid invariance; `tf_state_2d` invariance; the
   fixed-vs-slid calibrate-window grid assertion (R-CY6a); ladder-log era-guard tests
   (re-key within 4 days across the seam → skipped+counted; same-era whipsaw →
   appended; state change at seam → appended); fortnight pins (R-CY8).
4. Ladder-log guard per R-CY5.
5. Downstream suite green (cycles/ladder/alignment/boards/ticker-alert consumers).
6. Ship loop per repo law; this document + the measurement report are the PR's evidence.

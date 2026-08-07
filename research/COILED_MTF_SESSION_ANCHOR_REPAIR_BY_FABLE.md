# Absolute session anchor for coiled + mtf_upturn trend.d3 — repair charter

**Date:** 2026-08-06 · **Adjudicator:** Fable (main loop) · **Charter:**
`research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md` §Sibling triage
chip (2), executed as its own PR with its own era per the A3 rule. **Era stamp:**
`coiled-mtf-abs-session-2026-08-06` (DT-R16 family — a dated graded-population change,
labelled forever, never silent). ONE era covers BOTH modules' buckets: they ship in one
PR and one graded surface family (the US/CN standout boards' display + rank chips), and
a grader must be able to fence both re-draws on a single boundary. Mechanics reuse
`engine.session_anchor` (R1–R3) verbatim; this document records only the decisions that
are NEW here.

## The defect (measured 2026-08-06, 99 deep US names, k = leading bars dropped)

`engine/coiled.py` — the wave-2-validated COILED ranking bonus + wave-4 COILED-FIRE
chip — and `engine/mtf_upturn.py`'s U7 trend display cut their 3D/2D grids with pandas
`resample("3B"/"2B")` (series-start-anchored bins): `bull_div` flipped 10/99 at k=1,
`fire_recent` 70/99 (its `ticks` field is grid-derived), `mtf_upturn.trend.d3` 49/99.
The US standout universe (`build_stock_library.universe()`) mixes deep `data/stocks`
histories with ROLLING ~3y breadth caches whose window start creeps forward every
refresh (`collectors/breadth.py`), so these payloads re-phased BUILD-TO-BUILD with zero
price action — minting fake day-over-day `fire_ticks` deltas in the graded snapshots
(`grade_us_board`, `china_standout_track`) and disagreeing across the two US loaders
the same night (measured in-PR: 81/237 shared names disagreed on `ticks`, 100/237 on
`d3.bars_since_cross` — see the committed report).

## Rulings

**R-CM1 — One calendar, per-module grids.** Both modules bucket by
`session_anchor.session_positions(dates, market) // n` (the R1 reference sources, the
R2 edge semantics, the R3 market routing — all by reference, nothing re-adjudicated).
Each module owns its minimal grid cut (`coiled._tf_close`; an inline cut in
`mtf_upturn._build_trend_fields`) rather than importing another engine's `_Grid`:
the aggregation semantics differ per module and a shared rich helper would couple
unrelated release cadences.

**R-CM2 — coiled labels are KNOWN dates, not OPEN dates.** `signal_quality` R-SQ2 chose
OPEN-date labels because §7 marker dates are a public contract. coiled's grid labels
never escape the module: both `bull_div` and `fire_recent` used the old bin labels ONLY
as a join key to a known-date (max-traded-date-per-bucket) mapping before touching the
daily index. Indexing the anchored grid directly by each bucket's last traded session
IS that mapping with one fewer moving part; the public payloads (booleans, `ticks`
counted from the series end, `src`) are label-free. mtf's `trend.d3` consumes histogram
VALUES only — its labels are equally internal.

**R-CM3 — Market routing is explicit at the CN builders, inferred in mtf.**
`bull_div`/`fire_recent` gain `market: str = "US"`; `build_china_library` passes
`market="CN"` explicitly at its three call sites (an unsuffixed CN ticker must never
silently route to the NYSE calendar, so per-ticker inference is the WRONG default
there). `mtf_upturn._compute_symbol` infers via `session_anchor.market_for_ticker(sym)`
— it already did for the `_leg_d3_confluence` leg (sq era), the CN lane's symbols are
suffixed by construction, and one inference now feeds both 3D consumers. The US
builders pass nothing (default US).

**R-CM4 — Era stamp on every persisted payload; the mtf ledger is exempt.**
`coiled.ANCHOR_ERA == mtf_upturn.ANCHOR_ERA == "coiled-mtf-abs-session-2026-08-06"`
(equality pinned in the battery). `assess()` — which IS the persisted
us_standouts/china_standouts `coiled` block — and `fire_recent()` emit `anchor_era` on
every path including the never-raise fallbacks; the mtf site artifacts
(`site/stockdata/mtf_upturn.json`, `site/chinastockdata/mtf_upturn_cn.json`) carry it
top-level. The graders snapshot the coiled block as-of-keyed (schema-union-safe
columns), so the stamp reaches the graded record without grader edits, and
`conviction_delta`-class day-over-day differs can fence the one-time re-draw. The
mtf forward ledger (`data/mtf_upturn/ledger.jsonl`, key `(symbol, session)`) carries
NO trend fields — this PR's own buckets touch only the display chip — so its rows get
no stamp; its `legs.d3_confluence` input crossed eras under `sq-abs-session-2026-08-06`
(the parent PR), which owns that disclosure.

**R-CM5 — The chips re-draw ONCE, disclosed, measured.** No marker-integrity-style
merge law exists on these surfaces (they are recomputed nightly, not append-merged), so
the cutover needs no engine gate — the blast radius is the disclosure:
`reports/coiled_mtf_anchor_blast_radius.md` (+`.json`), committed, measured per
production loader (deep stocks/, 2014-start ohlcv/, 345/777-bar depth views, the three
present rolling breadth caches at native depth, the CN panel; the russell cache is
absent from dev checkouts and is named `unavailable`, never silently skipped). The
rank-bearing move is exactly `STAR_EXTRA = ±0.15` (≈0.3 cascade tier) on names where
`star = coiled ∧ div` flips — `coiled` itself (washout ∧ cohort) has no grid input and
cannot flip; measured 7 star flips on tonight's 40-name coiled cohort. The graded
`fire_ticks` field moved on ~56% of names — the one-time cost of removing the phase
noise that was previously re-minting moves of that size build-to-build.

**R-CM6 — What does NOT change.** `washout_ctx` (pure trailing-window daily
arithmetic, measured 0 flips — pinned in the battery), `weekly_d_last` and every W-FRI
weekly leg (calendar-absolute, R8 precedent), `_biweekly_close` (epoch-anchored
already), `_monthly_phase` ("ME" month ends, calendar-absolute), every threshold/
window/K-of-N/hysteresis semantic, the bonus constants, the wave-2/wave-4 validated
numbers' citations (PRE-era measurements, quoted as such — the wave gates were
verdicts about cohort behaviour, not about any single grid phase; the anchor is a
de-noising of an arbitrary phase realization, the same argument the sq re-validation
measured at ≤1.1pp). Forward ledgers: no backfill, no retro-edit
(emitter-fix-cannot-heal-logged-rows).

## Ship requirements (all in this PR)

1. Blast radius committed: `scripts/measure_coiled_mtf_anchor_blast_radius.py` →
   `reports/coiled_mtf_anchor_blast_radius.md` + `.json` — old-vs-new per loader,
   the STAR/bonus lens on the production union universe, stocks∩ohlcv agreement
   BEFORE/AFTER (residuals named), NEW-anchor start-invariance re-run (must be 0).
2. Era stamps per R-CM4.
3. Battery `tests/test_coiled_mtf_anchor_invariance.py` (the confluence battery's
   fixture pattern: real NYSE sessions, holiday spans, a halt, shallow depths;
   bull_div/fire_recent/trend.d3 bit-identical k=1..6; grid-geometry pins; era pins;
   market-threading pins incl. the CN-builder monkeypatch assertions in
   `tests/test_coiled.py`; CN-calendar invariance on the tracked reference).
4. Downstream suites green (coiled, mtf_upturn, bottom_sensors, board_tenure,
   china_standout_track, cn_standout_audit, grade_us_board).
5. Ship loop per repo law; this document + the measurement report are the PR's
   evidence. Stacked on the sq PR (#4738) — `session_anchor` and the mtf
   `_leg_d3_confluence` heal live there; this PR carries only the chip-(2) delta.

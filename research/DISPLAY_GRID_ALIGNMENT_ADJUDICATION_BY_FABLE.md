# Display-grid alignment — bar_derive + chart.js on the absolute session anchor

**Era:** `display-grid-abs-session-2026-08-06` · **Status:** ADJUDICATED (this ruling
landed on `main` separately in #4853); the implementation it describes lands with THIS
PR (#4799). Until this merges, nothing under "the fix" is on `main` — check
`git cat-file -e origin/main:engine/session_anchor.py` before building on any of it.
**Charter lineage:** chartered by `research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`
(§Consumer surfaces + §Sibling triage: "The display-grid pair (`bar_derive` + chart.js
`floor(i/3)`) … chartered separately"), itself the A3 follow-up of
`research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md` (R1–R3).
**Sibling eras:** `abs-session-2026-08-06` (cascade), `sq-abs-session-2026-08-06` (§7 stream).

## The defect

Two display surfaces still cut multi-session buckets on start-anchored grids after the
engine moved to the absolute session calendar:

1. **`engine/bar_derive.py` `derive_2d_ohlcv`/`derive_3d_ohlcv`** bucketed with raw
   `resample("2B"/"3B")` — bin edges phased to the series' first timestamp, holiday
   mis-splits included — while the 3D docstring claimed its close "equals what
   `signal_frame` derives internally". That claim goes FALSE the moment era
   `sq-abs-session-2026-08-06` (PR #4738) lands, because `signal_quality._tf_grid` then
   buckets by `session_anchor.session_positions // n` while `bar_derive` would not.
   **As of this writing it still HOLDS on `main`**: both sides sit on `resample("3B")`
   (`signal_quality.py:87`, `bar_derive.py:207`), so they agree by both being wrong the
   same way. (Zero production callers today — the defect is a loaded footgun plus a
   contract about to go false, not a live wrong number.)

   **This is why the ordering is load-bearing, not a preference.** Landing the
   `bar_derive` fix BEFORE #4738 would move this surface to the absolute grid while
   `signal_frame` stayed on `3B` — *breaking* a contract that currently holds, and
   creating the very divergence this ruling exists to close. #4738 first, then the
   implementation.

2. **`site/chart.js` `resample()`** builds its 3D candles by `floor(i/3)` over the LOADED
   window — and the window is `tail(MAX_BARS=1300)` of a store that advances one session
   per night (`scripts/build_chart_data.py`), so `i = 0` moves nightly and the client's
   entire 3D grouping re-phases mod 3. The engine's §7 marker dates (OPEN-date labels,
   R-SQ2) land on those candles via `mapMarkers` snap-forward — documented in-file as a
   workaround for the phase mismatch.

## Measurement (probe 2026-08-06; committed run: `reports/display_grid_blast_radius.md`)

Client grid vs the absolute grid, on `data/stocks` × the shipped 1300-bar windows, with
the committed `site/signals` marker set. **Per the DT-R16 era-split family law the pooled
figure may not be read without the phase rows** — the window phase is a fleet-wide
lottery (deep names share one window end, hence one phase; only short-history/gapped
names phase independently):

| window phase (nightly slide) | in-window markers | on a candle ≠ engine bucket | names affected |
|---|---:|---:|---:|
| tonight (aligned — the 1-in-3 day) | 8,317 | 154 (1.9%) | 6/235 |
| −1 session | 8,319 | 8,272 (**99.4%**) | 233/235 |
| −2 sessions | 8,334 | 8,287 (**99.4%**) | 233/235 |

230/235 capped names' entire 3D grouping regroups on a one-session slide. The six
always-wrong names tonight (EA, SATS, HOOD, CEG, KVUE, GEV — 100% of their in-window
markers each) are the short-history/gapped names whose phase is independent of the fleet
coin-flip. A "1.9% cosmetic issue" reading of tonight's chart would have been the exact
pooled-verdict error DT-R16 exists to forbid: on two of every three nights ~99% of every
US chart's markers sit on candles that disagree with the engine grid, and the whole 3D
view redraws for no price reason.

The committed measurement recomputes the table with the post-era §7 stream (in-tree
`analyze()`), adds the engine-side `bar_derive` old-vs-new bucket drift + healed
holiday mis-splits, the k-drop invariance re-run (must be 0), payload weight, and trim
distribution. This probe is the adjudication basis; the committed report is the shipping
receipt.

## The decision the charter left open

**Ship the session-position grid to the client — AND snap-forward stays, upgraded from
workaround to exact contract.** Both halves ruled; neither left implicit:

- Every StockChart ohlc payload (US `ohlc/`, CN `chinaohlc/`, CA `canadaohlc/`, intl
  `intlohlc/`, HK `hkohlc/` + the hk_lookup inline path, subsector family) ships
  `anchor: {era, b3}` where `b3` = row indices opening each absolute 3D bucket, computed
  server-side on the market's calendar (`session_anchor`, R1–R3 verbatim).
- chart.js buckets 3D by `b3` when present; `floor(i/3)` remains only as the fallback for
  stale cached payloads.
- `mapMarkers` snap-forward (first bar with `time >= date`) is retained: under an aligned
  grid it is exact — the previous bucket's last session < the marker's OPEN-date label ≤
  its own bucket's last session — and it keeps degrading safely on stale payloads.

**Rejected alternatives:**
- *Adjudicate snap-forward alone as the contract (no candle change).* "No marker is
  lost" (the SQ adjudication's robustness note) is true and insufficient: robust-to a
  re-draw is not aligned-with the engine grid. The phase lottery is structural nightly
  instability of a shipped surface, not a tail case — 99.4% wrong-candle on 2 of 3
  nights, every night a full regroup.
- *Phase-offset only* (ship `position(first row) % 3`, client keeps row arithmetic) —
  halt-fragile: one missing reference session mid-window (CN/HK suspensions, US halts,
  the six lottery-loser names above) silently drifts every later bucket. `b3` is exact by
  construction for ~2.2 KB raw (~0.7 KB gz) against ~50 KB payloads.
- *Builder-side boundary trim only (no b3)* — same halt fragility. Trim is KEPT as the
  cosmetic stabilizer (complete first candle, stable visible window) but is not the
  correctness carrier.
- *Re-stamping client candle times to OPEN dates* (full engine-label parity) — would move
  every historical 3D/1W/1M candle's x-coordinate for zero membership gain; alignment is
  bucket membership. Client label convention unchanged (DG-R5).

## Rulings

- **DG-R1 — One calendar.** All 2D/3D display buckets cut by
  `session_anchor.session_positions(dates, market) // n`; market inferred per R1/R3; no
  fallback chain.
- **DG-R2 — bar_derive labels are OPEN dates** (first session with a finite close in the
  bucket) — R-SQ2 mirrored; the docstring equality claim becomes true again and is
  CI-pinned against `signal_quality._tf_grid`, not left as prose
  (copy-that-points-elsewhere is an untested contract).
- **DG-R3 — The client buckets by shipped boundaries, never by row arithmetic.**
  `anchor: {era, b3}` in every StockChart payload, fetched and inline alike;
  `floor(i/3)` demoted to stale-payload fallback.
- **DG-R4 — Window trim.** Emitter windows open on a bucket boundary (≤2 rows dropped
  after NaN filtering): complete first candle, night-stable visible grid. Cosmetic; b3
  remains authoritative.
- **DG-R5 — Client candle time-stamps unchanged** (last-session labels). Engine §7
  marker dates stay OPEN-date (R-SQ2). The seam between the two conventions is exactly
  `mapMarkers` snap-forward, now exact under DG-R1/R3.
- **DG-R6 — Era stamp.** `bar_derive.ANCHOR_ERA = "display-grid-abs-session-2026-08-06"`,
  the single source imported by every emitter into `anchor.era` — the R-SQ3 stamp
  pattern; the payload-visible stamp is the DT-R16-family disclosure that the rendered
  grid crossed an era once, deliberately.
- **DG-R7 — Measured before shipped, committed, phase-split.** No pooled hop figure
  without the per-phase rows.
- **DG-R8 — The footgun is closed, not just bypassed.** `resample_ohlcv` refuses
  `nB` (n≥2) rules with a pointer to the anchored derivers; "1D"/"W-FRI" untouched.

## What does NOT change

The 1W/1M/4H client buckets (calendar-absolute / epoch-absolute already). Client
candle stamps (DG-R5). `mapMarkers`' out-of-window drop (site/ohlc caps are a payload
budget, not a grid property). `site/signals` payloads and their nightly era cutover
(owned by R-SQ7 `marker_integrity`; this lane commits no regenerated payloads).
`engine/canon.py::resample_sessions` and the Terminal's own overlays (R8/R-SQ5 stand;
the Terminal's window-phased overlays remain flagged for its own adjudication).
`leader_lifecycle.tf_state_2d` and the cycles/coiled/pick_lab sibling grids — chartered
and chipped under the SQ adjudication's sibling triage, not folded in here.

## Ship requirements

1. Anchored `derive_2d_ohlcv`/`derive_3d_ohlcv` + truthful, CI-pinned docstrings (DG-R1,
   DG-R2, DG-R8).
2. Anchor block in every emitter incl. HK inline + subsector; DG-R4 trim (DG-R3/R4/R6).
3. chart.js b3 bucketing + fallback + rewritten :785 comment (DG-R3/R5).
4. Real-session test fixtures (the old June-2026 bdate fixture contains Juneteenth — a
   business day, not a session); k-drop bit-exact invariance; independent first-principles
   bucket pin; synthetic-halt b3 pin; refusal pin; era-slug single-source pin.
5. `scripts/measure_display_grid_blast_radius.py` + committed reports (DG-R7).
6. Ship loop per repo law; PR stacked on the sq-abs-session era PR (#4738) until it
   lands, then rebased --onto main.

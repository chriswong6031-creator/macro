# Pick Lab — Amendment 1: measurement audit, horizon pre-registration, LH-2 adjudication (by Fable)

Date: 2026-07-16 · Status: ADJUDICATED — ratified with the P0 fix PR
Parent: `research/PICK_LAB_MASTERPLAN_BY_FABLE.md` (2026-07-09) · Program id: `pick_lab`
Ratification fact: at adjudication time `data/pick_lab/grades.jsonl` (and CN/HK grade ledgers)
are EMPTY — no grade row has matured anywhere. Every ruler and schema declaration below is
therefore pre-registered ahead of data, per house pre-registration law.

---

## §A1 Audit defect register (2026-07-16 full audit; 7-agent workflow + main-loop verification)

Verified operational defects, all pre-first-maturation (US matures ~2026-07-21, CN as early
as 2026-07-17):

| # | Defect | Evidence | Fix |
|---|---|---|---|
| D1 | SPY + all 11 GICS sector ETFs absent from every close-cache tier the grader loads → `ret_excess_spy`/`ret_rel_sector` null on every future grade row; primary ruler, all lift columns, and NAV null for all non-reversion books | `data/{breadth,midcap_breadth,smallcap_breadth}/_closes_cache.parquet` inspected — zero benchmark columns; `build_pick_lab.py` falls back to empty SPY series | P0 PR: benchmark close store wired into the grade panel |
| D2 | Liquidity gate no-op: `adv.ge(10e6).fillna(True)` — float64 `NaN.ge()` returns `False`, fillna dead → 86.7% of snapshot rows (null `dollar_adv_20d`) silently excluded; books picked from ~227 of 1,702 names | Reproduced on snapshot asof 2026-07-15 | P0 PR: `adv.isna() \| adv.ge(...)`. **Cohort fence: fires with `fire_date` ≤ 2026-07-16 were drawn from the biased large-cap pool; fires after the fix are drawn from the full universe. Any pre/post analysis must fence on this date.** |
| D3 | MFE/MAE keep-first trap: per-horizon return rows are written before the 25-session MFE window matures → `mfe`/`mae` would be null FOREVER on h5/h10/h21 rows (grades never re-scored in place); scoreboard 21d MFE/asym columns would never populate | Code-path analysis (`grade.py` maturation gates × `ledger.py` keep-first) | P0 PR: path rows (§A3) |
| D4 | NAV "max drawdown" is a linear-smear artifact: terminal 21d excess attributed as `total/21` per `BDay` (holidays included) — contains no price path; cannot measure real drawdown | `book.py:_nav_ladder` | P1: mark-to-market NAV or relabel; until then the column is NOT a realized-drawdown claim |
| D5 | CN/HK inline graders diverge from measurement law: CN omits MFE/MAE entirely; both count horizons on each ticker's OWN calendar (halt bias within a book); excess written as `ret_excess_spy` though benchmark is CSI 300/HSI | `build_china_pick_lab.py`, `build_hk_pick_lab.py` | P0 PR: route both through shared `grade_fires()` on the benchmark calendar |
| D6 | Eight masterplan books can NEVER fire (data-encoding mismatches, §A4) | Verified against snapshot 2026-07-15 | P1 revivals (§A4) |
| D7 | CN fire drought: 122 fires 2026-07-10, nothing since despite nightly asia-close wiring | `data/china_pick_lab/fires.jsonl` git history | Diagnosed in P0 PR lane; fix per diagnosis |

Audit also CLEARED (verified correct, do not re-flag): US grader exec-date/horizon indexing,
SPY-leg session alignment, keep-first dedup keying, mixed-maturity aggregation in `book.py`,
grading wiring in the nightly runner (grades absent on 2026-07-16 = nothing matured yet, not
a defect).

## §A2 Horizon pre-registration (per-family; declared before any grade matured)

Motivation (operator directive 2026-07-16): books enter at structurally different points of
a move — a 1D-gate book buys 1–2 sessions after the daily cross (early), a 3D-gate book
buys after the move is confirmed (late). A single flat 21d verdict horizon measures
different economic things across families and, for the 1D-velocity family specifically,
risks a false null on the PL-R11 speed-cost thesis (early moves that peak and mean-revert
before session 21 are under-credited at 21d).

Rulings:

- **PL-A2-1 (common primary retained).** The 21d family rulers of PL-R3 stand unchanged as
  every book's PRIMARY ruler (cross-family comparability; continuity with the ratified
  oracle-reversion convention for Family C).
- **PL-A2-2 (family-native secondary rulers, pre-registered now).** In addition to the
  primary, the following secondary verdict horizons are declared. At promotion time a book
  is judged at BOTH its primary and its family secondary (both pre-declared here, ahead of
  data; a book failing one and passing the other is reported as exactly that — no cherry-pick):
  - Family A (1D velocity, books 1–4): **10d SPY-excess** (mechanics: 1D triggers lead the
    3D gate by ~2 sessions per Wave-1 evidence; burst edges decay fast).
  - Family B (momentum/continuation, books 5–8): **63d SPY-excess** (continuation theses
    need room; breakout/base moves run multi-month).
  - Family C (washout/reversion, 9–11): none — the 21-session absolute reversion-capture
    ruler (#1458) already matches the family's mechanics.
  - Family D (EDGE/quality, 12–14): **63d SPY-excess** (composite-EDGE theses are slow).
  - Family E (context, 15–16): none (low-n books; 21d only).
  - Family F (flagship ablations + avoid, 17–19): none — ablations must be judged at the
    flagship's own ruler or they stop pricing the gate.
  - Families G/H (flow, leader — post-masterplan additions): rulers stay as declared by
    their chartering programs (21d SPY-excess); not re-adjudicated here.
  - LH grids: unchanged (126/252d, descriptive, PL-R6 firewall).
- **PL-A2-3 (descriptive ladder + capture surfaced).** The 5/10/21/63 ladder and the
  path-row capture ratios (§A3) are display/descriptive everywhere — free under
  gauntlet-is-promotion-not-build. The UI must surface them (P1).
- **PL-A2-4 (anti-pattern ban).** Post-hoc per-book horizon selection is FORBIDDEN:
  no verdict language at any horizon not pre-registered in PL-R3 or PL-A2-2. Picking a
  book's best-looking ladder rung after grades mature is a multiple-comparisons trap.
  A future per-book optimal-hold claim requires a fresh pre-registered ruler on a new
  engine_id (PL-R2) with the multiplicity acknowledged in its prereg.

## §A3 Measurement-law addendum: path rows (grade schema v1.1)

`grade_fires` emits, per entry-book fire, in addition to the per-horizon return rows
(kind `ret`, implicit), two **path rows** keyed `(engine_id, ticker, fire_date, horizon=w,
kind='path')` for w ∈ {25, 63}, each written only once w sessions have FULLY elapsed
after exec:

```
{engine_id, ticker, fire_date, horizon: w, kind: "path",
 exec_date, exec_price,
 mfe, mae,                    # close-based max/min pct vs exec over [exec+1, exec+w]
 t_mfe, t_mae,                # session index (1-based after exec) of peak/trough
 mfe_hl, mae_hl,              # intraday variants from high/low panels (null-honest)
 mae_before_mfe,              # t_mae < t_mfe (close-based)
 sessions_underwater,         # sessions in window with close < exec_price
 matured: true, graded_at, authority: "display_only"}
```

- Path rows are the authoritative source of MFE/MAE statistics; the legacy per-horizon
  `mfe`/`mae` fields on `ret` rows remain (spec §4 continuity) and stay null-honest.
- Per-horizon **capture ratio** (`ret_abs_h / mfe_25`, fires with `mfe_25 > 0`) is computed
  at read time in `book.py` — never stored on immutable rows.
- The grade dedup key gains `kind` (absent → `ret`); ledgers were empty at ratification,
  so there is no migration and no re-score.
- The close-based `mfe`/`mae` convention of spec §4 is unchanged; `_hl` fields exist because
  a real stop is hit on the intraday low — close-only MAE understates drawdown risk.
  Scoreboard risk readouts may cite either, labeled.
- CN/HK grade through the same code on their benchmark calendars (CSI 300 / HSI);
  their excess remains in the `ret_excess_spy` column with `benchmark_ticker` stamped
  (renaming the column is a P2 polish item, tracked, not a law change).

## §A4 Dead-book register and revival authorization

Eight masterplan books have zero lifetime fires because their conditions reference enum
values or scales that do not exist in the snapshot data (all verified 2026-07-16):

| Book | Cause | Correct condition |
|---|---|---|
| `plab_1d_blastoff` | `ext_grade == 'none'` — data enum is {null, steady, stretched, parabolic}; null means "no extension" | `ext_grade` null or `'none'` |
| `plab_washout_deep` | `dd_pct > 25` vs fractional data (0–0.834) | `dd_pct > 0.25` |
| `plab_washout_clean` | `dd_pct > 20` + `dilution_events_365d` 100%-null treated as fail | `dd_pct > 0.20`; dilution null passes (masterplan §3 wrote "=0"; snapshot never populates the column — wiring gap tracked separately) |
| `plab_hi_base` | squeeze check accepts `True/'on'/'active'/'squeeze'`; data enum is `COILED/COMPRESSED/...` | `vol_squeeze_state ∈ {COILED, COMPRESSED}` |
| `plab_sector_trough` | `sector_phase` 100% null (documented §9 gap, silent) | unblocks when the sector-cycle enrichment source ships |
| `plab_revision_accel` | `implied_upside_pct` 100% null; `edge_revision` data is 0–100 scale vs config `1.0` | thresholds re-derived on real scales once upside column ships |
| `plab_lh_compounder` | `dilution_events_365d` 100% null + fail-on-null | dilution null passes |
| `plab_lh_washout_survivor` | `dd_pct` scale + `interest_coverage`/`dilution` 100% null fail-on-null | `dd_pct > 0.40`; null-tolerant quality clauses pending column wiring |

(`plab_beta_squeeze` is a ninth suspect: `'squeeze'` did not appear in the `current_mode`
enum on the audited night — verify the emitter's enum before concluding.)

**2026-07-17 P1 scouting addenda:**
- `plab_beta_squeeze` CLEARED — `'squeeze'` is a real enum in
  `engine/stock_personality.py::CURRENT_MODE_PRECEDENCE`; the book is regime-quiet,
  not broken. No change.
- `plab_sector_trough` phase source ruled OUT for now: the only committed candidate,
  `data/sector_cycles/leg_context.json`, was 17 days stale at inspection and uses a
  different phase vocabulary (Bottoming/Prime entry/Trending/Topping/Rolling over vs
  the masterplan's Trough/Recovery). Wiring it would stamp stale, mistranslated
  phases — the book stays dead with an AWAITING-DATA badge until a nightly-committed
  phase feed exists.
- `plab_revision_accel` stays dead (implied_upside_pct still unwired), but its
  `edge_revision` threshold is corrected to the column's real 0–100 percentile scale
  (config 1.0 was a z-score intent → 84.0, the percentile equivalent of z≥1) so the
  book is correct the day the upside column ships.

**PL-A4-1 (revival law).** Because every affected book has ZERO lifetime fires (verified),
in-place condition correction with a refreshed `config_hash` and a dated registry comment is
authorized as equivalent to PL-R2's engine-v2-with-fresh-ledger (the ledger IS fresh). Any
future correction to a book that HAS fires must ship as `-v2`. Revivals are P1 work; each
revived book's accrual clock restarts at its fix date. The 100%-null context columns
(`dilution_events_365d`, `interest_coverage`, `days_since_shelf`, `implied_upside_pct`,
`is_blackout`) are snapshot-producer wiring gaps — books gated on them stay honestly dead
until the columns ship; do not fake the gates away.

## §A5 LH-2 (`plab_lh_edge_durability`) adjudication — operator complaint 2026-07-16

Complaint: the grid bought semiconductor/memory names (SNDK, WDC, AMAT, AMD + VRT
adjacent) on 2026-07-13 that the operator reads as overbought/extended/rolling-over.

Findings (snapshot-of-record 2026-07-13):

1. The picks were NOT short-term overbought — SNDK was RSI 46, −15.1% vs 20dma, −28.3% off
   its 52w high, `washout_active`, daily stoch K≈20; WDC/AMAT similar. They were mid-
   breakdown after the memory-complex run. Two picks (CSX d1_k=100, TRGP) WERE overbought.
   The operator's economic read stands: the book bought late-cycle leaders as they rolled.
2. Mechanics: `axis_selection` is loaded with trailing `edge_alpha` (SNDK 3.0, WDC 2.7 —
   top of universe), which peaks precisely AFTER a monster run → the selector structurally
   favors post-run leaders at cycle tops.
3. The "quality > median" gate is near-vacuous: universe median `axis_quality` = **−0.21**,
   so negative-quality names (CSX −0.2, NUE −0.11) pass.
4. No sector cap: 4–5 of 10 picks in one complex → effective N ≈ 3 clusters
   (ticker-cluster time-confound law) — 126d outcomes would measure the memory cycle,
   not the construction.
5. The book ignored the engine's own risk reads (`cycle_state` = "UNCONFIRMED — HIGH RISK"
   on 4 picks, "DON'T CHASE" on CSX) — BY DESIGN: LH grids are hold-thesis books with
   deliberately zero entry conditions.

**Ruling PL-A5-1: tweak-and-pair; no kill.** The EDGE-durability thesis is untested (first
maturation ~2027-01) and killing on entry aesthetics before any grade matures would violate
the measurement-lens law (nothing here separates mechanism-false from construct-flawed).
But defects 3–4 make the v1 verdict weak REGARDLESS of outcome. Therefore:

- **v1 keeps firing** as the no-gate control; its 10 existing fires stand and mature —
  "bought the rolling-over leaders" is itself a valuable 126d test case. The UI must
  relabel it as a control, not advice (P1).
- **LH-2b ships in P1** (`plab_lh_edge_durability_b`, fresh ledger): same
  `axis_selection` top-decile ranking PLUS `axis_quality > 0` absolute floor, sector cap
  ≤3 per GICS sector per fire-date. v1-vs-2b divergence at 126d directly measures whether
  quality floors + diversification caps matter for hold-theses.
- **All LH fires stamp entry context going forward** (instrumentation, never gates):
  `cycle_state`, `pct_vs_20dma`, `off_52w_high_pct`, trailing 252d return.
- A kill decision, if ever, belongs to the operator at/after first maturation with the
  v1-vs-2b comparison in hand.

Note: the other two LH grids (`plab_lh_compounder`, `plab_lh_washout_survivor`) are D6
dead-at-birth books (§A4) — the Long-Hold tab currently shows one live grid of three; the
empty grids are a defect, not a design statement.

## §A6 Registry delta note

The live registry holds 27 books, not the masterplan's 23: Family G
(`plab_flow_leader`, `plab_flow_washout` — Flow Leaders W2, #2224) and Family H
(`plab_leader_precipice`, `plab_leader_onset` — Leader Radar W2a, #2248) were added by
their own chartered programs with frozen configs and their own rulers. This amendment
records the delta; their adjudications live with their programs. Known quirk carried
forward: G/H books sourced from external artifacts apply only the close ≥ $5 floor for
tickers absent from the snapshot (ADV unknown → `liq_unknown=true`, spec-compliant but
worth remembering when reading their lift columns).

## §A7 P1/P2 backlog (from the audit; not built in the P0 PR)

P1: dead-book revivals (§A4); UI — surface ladder + capture ratios + path-row risk stats,
relabel LH-2 v1 as control, honest "structurally dead" badges for §A4 books; LH-2b book;
same-names-random-DAYS timing control (current random book only randomizes names →
measures selection, not timing); universe buy-anytime base rate (PL-R5 second control,
currently hardwired null); run-up-before-entry stamping on velocity-book fires
(`pct_gain_since_swing_low`, `bars_since_trough`, `pct_vs_20dma`).
P2: mark-to-market NAV (or relabel max_dd); `ret_excess_spy` column rename with
migration; masterplan §3 refresh for Families G/H; real-calendar test fixtures beyond
those added in P0.

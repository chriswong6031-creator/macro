# Short-Side Phase-0b — Species-Batch Tape Extension (PRE-REGISTRATION)

**Author:** Fable (orchestrating session), 2026-07-06
**Status:** pre-registered BEFORE the extended dump runs. Definitions FROZEN; amendments require a dated entry below, committed before the amended run.
**Governing docs:** `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md` §3–§4; `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md` (RUL-U4); parent apparatus `research/short_side/BD_PHASE0_PREREG.md`.
**Contamination stamp:** `derived_from_surface: bd_phase0_tape` — the three definitions are pre-frozen and price-only (not selected from Phase-0 results), but this batch is a re-read of an already-read tape period; its report is a contamination surface for any later prereg on this tape.
**Budget semantics:** `log_declared_budget` is a per-family **max()** floor, not a sum (see BD_ECON1_PREREG header note) — the declared 3 is a within-batch floor; the harness additionally logs each definition as a distinct config so the family `literal_n` accumulates, and outputs print both the literal count and the max()-basis divergence note.

## §0. Scope

Three additional price-computable breakdown definitions from the masterplan §3 inventory, run through the Phase-0 apparatus VERBATIM — same universe, liquidity floor ($5M 21d median dollar volume, price ≥ $3), ERA-LAW window (2021-07-06+, ≥252 prior bars), episode collapse (21 bars), paired two-sided grading (`terminal_state` / `terminal_state_short`, horizons 21/63/126, same barrier parameters), seeded random-bar controls (3 per event), survivorship stamps. `scripts/research/dump_breakdown_events.py` is EXTENDED (same single writer); summary schema bumps to v3; the overlap matrix extends to all six definitions. **S7⁻ is excluded** (masterplan flag: S7 registered two-sided in the entry-species program — coordinate, don't duplicate). EDGAR/news-gated species stay parked.

`TrialLedger.log_declared_budget(3, family='short_side')` BEFORE the run (three definitions, no threshold search; the family's cumulative count is printed).

## §1. BD-4 — S4⁻ Two-Clock Rollover (frozen)

Deliberately self-contained construction (no canonical per-name two-clock state exists in `engine/` to import; the cycles-ladder machinery is index/sector-grain). Let `C` = split-adjusted close.

- `pos63_t` = 100 × (C_t − min(C, 63 bars)) / (max(C, 63) − min(C, 63)); skip bar if max == min. `daily_osc` = EMA5 of pos63.
- `pos252_t` = same over 252 bars; `weekly_osc` = EMA21 of pos252.
- `rollover(osc)`: max(osc, trailing 15 bars) ≥ 80 AND osc ≤ that trailing peak − 15 AND (osc_t − osc_{t−5}) < 0.
- `extended`: C_t ≥ 0.88 × max(C, 252 bars).
- **Warmup floor:** the weekly oscillator needs 252 bars for pos252 plus EMA21 burn-in — BD-4 events may not fire before a ticker has **≥273 prior bars** on the plane (raising the ERA-LAW ≥252 floor for this definition only).
- **Event:** first bar where rollover(daily_osc) AND rollover(weekly_osc) AND extended all hold.
- **Obligation:** BD-4 is mechanically adjacent to BD-3 (both fire near highs on momentum loss). The BD-4↔BD-3 episode overlap share is a REQUIRED output row; if >50% of BD-4 episodes overlap BD-3 episodes (±21 bars), the summary must carry a redundancy flag and any Phase-1 consideration treats BD-4 as a BD-3 variant, not an independent species.

## §2. BD-5 — S5⁻ Coiled Breakdown (frozen)

- `coil_ratio_t` = (max(C, 21) − min(C, 21)) / median(C, 21).
- `coiled`: coil_ratio_{t−1} ≤ 20th percentile of its own trailing 252-bar distribution (computed at t−1).
- `distribution`: the 21-bar-sum series of `sign_volume` is ≤ −0.5σ below its own trailing-252-bar mean, where σ = rolling-252 std **of the 21-bar-sum series** (BD-1's implemented convention verbatim: `sv_21.rolling(252)`; sign_volume = volume × ((C−L)−(H−C))/(H−L), H==L → 0).
- `breakdown`: C_t < min(C over the 21 bars ending t−1).
- **Event:** breakdown bar with `coiled` and `distribution` both true.

## §3. BD-6 — S13⁻ Within-Sector Leader Fade (frozen)

- Sector assignment: `data/breadth/ticker_sectors.parquet` (the `scripts/build_sector_map.py` output; exact artifact + as_of recorded in the run stamp). **Declared limitation:** a current-date sector map applied to historical bars is an anachronism, accepted because sector membership is slow-moving (the same declaration as L6-P0 §2.5.4). Sectors with <8 covered members on a bar are skipped for that bar.
- **Build note (not a per-ticker drop-in):** BD-6 needs cross-sectional sector context; the builder adds a sector-panel pre-pass (load universe closes → per-bar sector top-decile cutoffs and 21-bar-return medians → per-name lookup) BEFORE the per-ticker detection loop. The single-writer and summary-v3 obligations are unchanged.
- `leader`: ticker's trailing 126-bar return in the top decile of its sector's covered members as of t.
- `rel21_t` = ticker 21-bar return − sector median 21-bar return. `fade`: rel21_t ≤ −1.0 × std(rel21, trailing 252 bars); bars where std(rel21, 252) == 0 are skipped (degenerate flat-window guard).
- `near_highs`: C_t ≥ 0.85 × max(C, 126 bars).
- **Event:** first bar where leader AND fade AND near_highs hold.

## §4. Output and reading guide

Same deliverable as Phase-0 §6: per definition — episode count, per-year counts, both-side terminal-state base rates, paired asymmetry deltas with episode-clustered bootstrap CIs, control-baseline comparison, six-definition overlap matrix. Reading guide UNCHANGED from BD_PHASE0_PREREG §6 (worth-a-Phase-1 iff long-stop gap ≥5pp with CI excluding 0; avoid-only taxonomy; <100 episodes → parked), plus one inherited amendment (RUL-U4): **any Phase-1 forward prereg arising from Phase-0b must carry a compensating gate at least as strict as BD-AVOID-1's ≥8pp** (this tape will have been read once). No cross-definition selection statistic; no promotion; no site surface.

## §5. What this does NOT show

Identical to BD_PHASE0_PREREG §7. Additionally: BD-4/5/6 base rates say nothing about BD-2/BD-3 (already registered forward via BD-AVOID-1); nothing here re-reads or amends the Phase-0 definitions.

## Amendments

(none)

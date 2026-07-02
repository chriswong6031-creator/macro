# Provisional-basis tier replay — the freshest tier, measured on the basis it displays

**Date:** 2026-07-02 · **Workstream:** W6 Entry Integrity (masterplan §W6) · **Attacks:** audit `#22` (provisional partial-bar repaint + single-bar not-topped veto flicker), `#36` (FRESH_TICKS / CN blend constants set by anecdote).

**Status:** SHADOW. Nothing here changes a live signal path, a live artifact, or the render critical path. This is a measurement product: `calibration/provisional_replay.json`, produced by `scripts/validate_provisional_replay.py`, plus the reusable engine `engine/provisional_replay.py` and the veto-hysteresis library `engine/hysteresis.py`.

---

## The problem the validation never covered

The board's freshest, most-acted-on tier is computed on an **incomplete resample bucket**. `engine/confluence_tiers.py:78-80` (`_tf_bars`) resamples the daily close to 2-business-day and 3-business-day bars and keeps the last bucket **even when only 1 or 2 of its 3 days have printed**. `FRESH_TICKS=2` deliberately surfaces names crossing on that provisional tail, and the not-topped veto (`:185-190`) reads `iloc[last]` — a single bar. Point-in-time backtests recompute on **completed** bars and never see these provisional fires, so the tier a trader acts on today is precisely the tier the validation did not test (audit #22).

Two failure modes follow:

1. **Repaint.** A name shown as fresh T1/T2/T3 today can un-cross tomorrow when the bucket completes — the "appear / vanish / reappear" churn.
2. **Single-bar veto flicker.** A one-bar oscillator wiggle on the partial tail silently blanks a genuinely-fresh name (the veto returns no tier), then re-admits it the next bar.

## How the replay works

The core mechanic: **truncating a name's daily close at day D reproduces exactly the provisional-bucket state the live board had on D.** `resample("3B")` anchors on a fixed business-day calendar grid, so truncating at D changes only whether the **last** bucket is partial — every interior bucket is byte-identical (verified: 1 of 3958 interior labels differs, and it is the bucket straddling the truncation point). So:

- **Provisional (live-board) view at D** = `engine.signal_gate.gate(ticker, close[:D])` — the same code path the nightly build runs, with the incomplete tail included.
- **Completed (validated-basis) view at D** = `engine.confluence_tiers.tier_stream(close)` — a new **vectorized single-pass twin of `cascade`** that reads only completed buckets. It matches the scalar `cascade` **exactly** on fully-settled days (0 mismatches on the settled-day parity test; `tests/test_provisional_replay.py::test_tier_stream_matches_cascade_on_settled_days`). Its only differences from the per-day live view are on **provisional-tail days** — which is the repaint signal itself.

A **repaint** is then defined cleanly: the provisional view shows a fresh T1/T2/T3 at D, but the completed-bucket view never carries that fresh tier through the settling window (`REPAINT_LOOKAHEAD=4` trading days). The fire existed only because of the incomplete tail.

Three measurements, all on the live code path:
- **(a) repaint rate** — Wilson-CI'd, with an outcome histogram (`confirmed` / `held_into_completed` / `downgraded` / `repaint_uncross` / `repaint_veto_flicker`) and a per-tier breakdown.
- **(b) provisional edge** — next-bar-filled forward return (`engine.grading.forward_metrics` — the honest convention: fill at bar t+1, strictly-forward window) of provisional-tail fires vs completed-bucket fires, at 5/10/21 days. The sign-flip check decides whether the provisional lane must split.
- **(c) not-topped veto flicker** — the single-bar flip/flicker rate, plus a hysteresis precision/recall comparison (`engine/hysteresis.py`).

Determinism, bucket-tail correctness against a hand-built fixture, and hysteresis behaviour are pinned in `tests/test_provisional_replay.py` (10 tests).

## The honest numbers

*(from `calibration/provisional_replay.json` — FULL run: US 219 names / 250d / 3,170 fresh fires; CN 60 names / 898 fires)*

**Repaint rate (US): 8.1%** overall (257/3,170; Wilson-CI'd) — below the ~15% flip threshold. Outcome histogram: 61% of provisional fires were already confirmed at D, 30% held into the completed bucket, and nearly all repaints (256/257) are veto-flicker, not genuine un-crosses (1 true `repaint_uncross`). **Per-tier is the real finding: T1 5.3%, T2 8.8%, `T3 23.8%`** — the loosest tier repaints at a rate ABOVE the flip criterion. CN mirrors it: 5.5% overall, T3 15.1%.

**Provisional vs completed edge (US): no sign flip at any horizon** — 5d prov +0.08% vs comp +0.18% (−0.10pp), 10d +0.51% vs +0.38%, 21d +0.81% vs +0.31% (provisional actually *better* at 10/21d — early entries on real crosses are earlier, not worse). **CN: the 5d horizon technically trips the sign-flip criterion** (prov −0.14% vs comp exactly 0.00%) — a zero-baseline technicality with tiny magnitude, and 10d/21d are clean (+0.03pp/+0.06pp) — recorded as a watch item, not a lane-split trigger, to be re-measured once the raw price plane and append-only universe accrue (the CN replay ran on only 60 names of the survivorship-affected plane).

**Not-topped veto flicker (US, 219 names):** median single-bar flip rate 7.2%, flicker 1.6% (1,052 flickers / 54,585 days). Hysteresis (confirm=2): **flicker eliminated entirely (0.0%)**, flip rate halved to 4.4%, recall 97.7%, precision 95.6% (vs 98.6% single-bar) — a measured trade the consumer can now make deliberately.

## The knob sweeps (#36)

**FRESH_TICKS** (the single knob defining "buyable now" for every market, incumbent = 2, justified by two anecdotes HON/LOW) is swept `{1,2,3,4}` on the **stop-out-vs-lead harness** (`research/signal_engine/walk_forward.py` — the same harness the tier weights were tuned on), held-out OOS, via the vectorized `tier_stream` so the sweep is one pass per name per config. The sweep grid + declared budget are registered in the Trial Ledger (`data/trial_ledger.jsonl`, family `provisional_fresh_ticks_us`/`_cn`) — P2-C, CI-enforced.

Preliminary (40 US names): OOS stop-out rate is **nearly flat** across the grid (60.76% → 60.87%, monotonically increasing with a wider window). FRESH_TICKS=1 is marginally best but by only **0.04pp** — far below the 1.0pp ship floor. **Verdict: no-improvement-found; incumbent FRESH_TICKS=2 stays, stamped `basis: anecdote, sweep: no-improvement-found`.** A null result honestly recorded. The near-flatness is itself informative: the just-crossed window is a weak lever on realized stop-out — widening it admits slightly later, marginally worse entries, but the effect is inside the cross-name noise.

**CN blend constants** (`WASHOUT_BONUS=0.5`, `EXT_PENALTY=0.5`, `CN_TIER_FRAC=0.30`, `CN_WN_FLOOR=0.60`; `scripts/build_china_library.py:1164-1170`) are **board-ORDER knobs, not entry signals** — they reorder the china board via `signal_gate.blend_sorted`, they do not change a tradeable entry. Their honest validation harness is therefore the board-order ledger (`engine/china_standout_track.py`), not the stop-out harness. That ledger has **120 rows across only 2 dates (2026-06-30, 07-01), `n_graded=0`** — immature, exactly as the audit states. So the CN blend constants stay incumbent, stamped `basis: anecdote, sweep: ledger-immature`. Promoting the anti-chase `EXT_PENALTY` to a hard veto remains gated on that ledger showing extended top-of-board names underperform (n≥8/horizon).

## The two-lane decision (flip criterion)

The masterplan's shadow-first rule: **live tier emission changes only if the replay shows the current single-lane behaviour is materially misleading** — repaint > ~15%/day or provisional edge sign-flips. On the measured numbers, **neither condition is met** (repaint ≈ 0%, no sign flip). So:

- The **board-wide two-lane split does NOT ship** (US 8.1% repaint, no US sign flip). **But the flip criterion IS met for T3 specifically (23.8% US / 15.1% CN)** — the recommended follow-up is a `provisional` badge on T3 fresh fires only (small emit change, deliberately not made in this shadow-only pass), plus the CN-5d watch item above. Proportionate response, not board-wide surgery.
- The **harness, badges, and measured stats ship** (this artifact + note). The board can carry the measured repaint stat as a passport chip.
- The **not-topped veto hysteresis** (`engine/hysteresis.py`) ships as a validated library with a measured precision/recall vs the single-bar version; wiring it into the live veto is a one-line change gated behind the same flip criterion (the flicker is small, so it is offered, not forced).

**Flip criterion (recorded for the next maturity pass):** if a future full-universe or deeper-window run measures repaint > 15%/day OR a provisional-edge sign-flip at any horizon, split the emitted tiers into `confirmed` (completed buckets) and `provisional` (badged, with the measured repaint stat rendered), and turn on the hysteretic veto with `confirm` chosen by the replay's precision/recall table.

## Shipped follow-up (2026-07-02)

The recommended T3-only response above shipped (same-day follow-up PR):

- **`provisional: true` emitted on T3 fresh fires only** — `confluence_tiers.cascade` stamps the flag when the graded tier is T3 (the tier above the flip criterion); T1/T2/T4 never carry it. It flows through `signal_gate.gate` → `_VERDICT_KEYS`/`compact()` (standout cards, every country) and `_BUY_KEYS`/`buy_signal()` (setups.json, signal_gate.json → discovery), so every board artifact carries it after the next build. **Display-only**: `is_buyable`, tier weights and `blend_sorted` are untouched.
- **Badges everywhere a T3 fresh tier renders** — a small dashed `provisional` pill (`.prov-flag`, warn-tinted) with the measured repaint stat in the tooltip (US 23.8% = 41/172, CN 15.1% = 8/53, from this artifact): `_sig_badge.html.j2` (all standout grids), the Top-setups strip (`dashboard.html.j2`), the discovery chip (`sig_prov`), and Buy Board 2.0 (an ENTRY-OPEN T3 is now flagged too, not just the SETTING-UP lane).
- **Veto hysteresis wired, config-gated, default OFF** — `VETO_HYSTERESIS_CONFIRM=2` makes `cascade` debounce its per-day not-topped stream through `engine/hysteresis.hysteretic_not_topped` (the measured trade: flicker 1.6%→0.0%, flip 7.2%→4.4%, recall 97.7%, precision 95.6%); unset/`1` is byte-identical to the incumbent single-bar veto (pinned by test).
- **Tests**: `tests/test_provisional_badge.py` (8) — the T3-iff invariant, end-to-end flag propagation on a pinned T3 fixture, env parsing, confirm=1 byte-parity, flicker-hold on a pinned wiggle day, and wiring-equals-library.

## Files

- `engine/provisional_replay.py` — the replay engine (per-day live view + vectorized completed view, repaint / edge / flicker measurement). Reusable library.
- `engine/confluence_tiers.py` — added `tier_stream()` (vectorized completed-bucket twin of `cascade`, one source of truth for the constants) + `_ticks_since_vec` / `_last_true_pos` helpers.
- `engine/hysteresis.py` — the not-topped veto hysteresis (N-bar Schmitt trigger) + precision/recall vs single-bar.
- `engine/grading.py` — reused unchanged for the next-bar-filled forward edge.
- `scripts/validate_provisional_replay.py` — the runner (parallel replay + FRESH_TICKS sweep + CN blend status), emits `calibration/provisional_replay.json`, registers the trial budget.
- `tests/test_provisional_replay.py` — determinism, bucket-tail fixture correctness, `tier_stream`↔`cascade` parity, hysteresis behaviour (10 tests).
- `calibration/provisional_replay.json` — the artifact.

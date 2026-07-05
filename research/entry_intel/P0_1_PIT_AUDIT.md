# P0.1 Replay Harness — Adversarial PIT / Lookahead Audit

**Program:** Entry Intelligence (EI), masterplan §4/P0.1, ruling R8.
**Artifact audited:** PR #1312 `ei(P0.1): production replay harness + graded verdict ledger`
— branch `ei/p0-1-replay-harness`, single file `scripts/replay_standout_pipeline.py` (1,142 lines, additive).
**Auditor:** Opus (PIT audit delegate, §7). Method: read PR diff via `gh`/`git show origin/...` (no shared-checkout mutation); read all production engine deps on `origin/main`; empirical spot-checks against canonical `data/yahoo/` (read-only).
**Date:** 2026-07-04.

---

## VERDICT: BLOCKED

One BLOCKING finding (F1: prefilter silently drops production fires — a recall bug) and one BLOCKING finding (F2: the golden test passes **vacuously** and has never actually diffed production-vs-replay). Neither is a forward-in-time price lookahead — the core PIT price path is **clean and proven** (see "What is correct", verified by re-slice invariance). But R8 is explicit: *"a lookahead bug poisons everything downstream"* and the golden test is the *hard gate* that must be clean before any P1 study runs. A prefilter that omits true fires poisons the pre-gate pool (R1) and the recall audit (P1.4) just as surely as a lookahead would, and the golden test in its current form provides **zero** verification, so the merge gate is not met.

Recommend: **do not merge** until F1 (prefilter recall) and F2 (golden-test validity) are fixed and re-audited. F3–F7 are ADVISORY (feature fidelity / completeness / claim accuracy) and can ride the same fix PR.

---

## What is CORRECT (verified, not just asserted)

These were adversarially tested and hold — the harness earns credit here:

- **No production engine modules were modified.** `git diff origin/main...origin/ei/p0-1-replay-harness -- engine/` is empty; the diff is one new script, +1142/-0. The gate/grading/cascade code is imported and called, never reimplemented (except study covariates — see F5).
- **Core PIT price path is leak-free.** The loop is `close_pit = close_full.loc[:signal_date]; signal_gate.gate(ticker, close_pit)` (harness L510, L516). All indicators (`analyze`, `confluence_tiers.cascade`, `mtf_snapshot`) compute on the truncated slice and read only the last bar. **Decisive test:** on ZS/NET, truncating a +20-bar-extended series back to a fire date reproduces the fire date's verdict byte-identically (`tier_cascade`, `eligible`, `ticks` all equal) — future bars do NOT leak into a past bar's verdict. Resample-anchor stability holds *within* a given truncation. (NET 2023-11-06: exact vs re-slice both `T1/True/ticks=1`.)
- **Fill is strictly next-bar (never same-bar).** `fill_index` = `loc+1` (grading.py L160-168); empirically `fill_offset=1`, entry = fill-bar close, `fwd_ret_H = close[fill+H]/entry-1`, forward MDD/MFE windows are strictly `(fill, fill+H]` (grading.py L223-238). Confirmed on NET: signal 2025-04-22 → fill 2025-04-23. Satisfies §3 inherited law ("fills strictly-after signal bar, never same-bar").
- **No marker-date lookahead.** `signal_quality._buy_filter` reads bars i+1/i+2 and its docstring forbids grading off a `take` marker date (+5.7pp/10d leak). The harness never fires on a `take`: on the last bar of `close_pit`, `_buy_filter` returns `pending` (i+1≥n), and the harness fires on the confluence `tier_cascade` evaluated at the last bar from past bars only. Grading anchors on that confluence-fire bar = "the first close at which the label was knowable." The forbidden path is not taken.
- **Fire classification is faithful.** Harness `_classify_verdict` fire test (`eligible and tier_cascade in BUYABLE_TIERS`, L447) is byte-equal to production `signal_gate.is_buyable`. 0 mismatches over 276 sampled PIT bars on NET.
- **Grading uses the full series for forward returns by design** — this is the OUTCOME being graded, not lookahead. `terminal_state`/`forward_metrics` anchor on `signal_date` and only ever read bars after the fill; correct.
- **Survivor-bias stamp present** per §4: `survivor_bias = (year < 2015)` (L505, `SURVIVOR_BIAS_YEAR=2015`), stamped on every row (L563). Matches masterplan "pre-2015 rows carry survivor-bias stamp."
- **Prefilter soundness positive-control ran and passed** as specified (555 non-candidate pairs, 0 fires; `data/replay/soundness_check.json`). But note F1: this control is structurally incapable of catching the actual bug.

---

## BLOCKING FINDINGS

### F1 — BLOCKING: Prefilter silently DROPS production fires (recall bug from resample-anchor drift)

**Where:** `scripts/replay_standout_pipeline.py` `prefilter_candidates()` L205-306 (3D/2D RSI-MACD cross detection L226-259), consumed by `replay_ticker()` L497-507 which evaluates the gate **only on candidate dates**.

**Claim in PR / agent report:** prefilter is a "CONSERVATIVE net (false positives are OK; false negatives violate the soundness check)" (L211-212); soundness "confirmed 0 false fires in 555 non-candidate pairs."

**Reality — confirmed end-to-end:** the prefilter is NOT conservative. It misses real fires.

- **Hard case: ZS 2024-05-10.** Production `signal_gate.gate(ZS, close.loc[:2024-05-10])` returns `buyable=True, tier=T1, ticks=0` (a master 3D-MACD cross completing on that exact bar). `2024-05-10 ∉ prefilter_candidates(ZS)`. `replay_ticker('ZS', c, cands, 2024, {})` produces **10** fire rows for ZS in 2024 and **2024-05-10 is not among them** — the fire is silently absent from the ledger. Surrounding days 05-09 and 05-14 ARE candidates; 05-10 and 05-13 are holes.

- **Mechanism (root cause):** resample-anchor divergence between prefilter and production.
  - Prefilter resamples the **full** series: `c.resample("3B")` yields 3D bars `[…,05-07,05-10,05-15,…]` (known-dates `[…,05-06,05-09,05-14,…]`) and detects the 3D-MACD zero-cross on the bar whose known-date is **05-14**, mapping the cross event to 05-14 only (non-ffill "event" placement).
  - Production `cascade()` on the **truncated** series `c.loc[:05-10]` re-anchors the final partial 3D bucket so the cross completes on the **last bar, 05-10, ticks=0**.
  - The two disagree on 3D bucket boundaries near the truncation point. The prefilter's `any_cross.rolling(10).max()` looks BACKWARD from 05-10 and cannot see the 05-14 event; the neighboring candidate flags come from the StochRSI ffill path, which happens to leave 05-10/05-13 uncovered. Net: a genuine T1 fire with the freshest possible cross (`ticks=0`) is dropped.

- **Prevalence:** ticker-dependent. NET (0/23 missed), CRWD (0/16), NOC (0/153 — but NOC's prefilter degraded to *all 11,214 bars = candidates*, so its recall is trivially 100% and tells us nothing). The by-tier sample (PYPL/ZS/RIVN/TNDM) missed **1 T1** out of 114 fires; the miss was a `ticks=0` boundary case. The drop is systematically concentrated on the **cross-completion bar** (`ticks=0`) where full-vs-truncated bucket anchoring differs most.

**Why the soundness check cannot catch this:** the positive control samples **non-candidate** pairs and asserts they are non-fire. ZS 2024-05-10 IS a non-candidate that DOES fire — it is exactly the failure the control is meant to detect — but the check draws a *random* 555-pair sample with no coverage guarantee, and the systematic `ticks=0` boundary misses are a small fraction of all non-candidate bars, so they are essentially never sampled. The check passed while the bug is present. (An honest positive control for a recall bug must be **exhaustive over a per-ticker fire set**, or must compare the candidate set against a full-series `tier_stream` fire mask — not a random sample.)

**Impact under the masterplan:** every dropped fire is missing from the pre-gate pool (R1 separability), the fire cell counts (R2 gate P&L), and — most damagingly — the **recall audit P1.4**, whose entire job is to measure coverage. A prefilter that omits fires biases the coverage census in the optimistic-looking direction (fewer "fired" events than truly fired). R8: this poisons downstream studies.

**Fix direction (for the rebuild, not prescriptive):** anchor the prefilter on the SAME point-in-time basis production uses — e.g. use `confluence_tiers.tier_stream(close)` (the vectorized, PIT-correct twin that already exists and is imported-but-unused, L106) to build the candidate/fire mask, or widen the candidate rule to also mark the cross-completion bar under the truncated-bucket anchoring. Then replace the random soundness sample with an exhaustive candidate-vs-tier_stream recall assertion.

---

### F2 — BLOCKING: Golden test passes VACUOUSLY; it has never diffed production-vs-replay

**Where:** `run_golden_test()` L704-826, specifically the pass predicate L817: `"golden_test_passed": exact_match or not replay_exists`.

**Design contract (§4/P0.1):** *"Golden test (hard gate): for the latest date … run the production gate directly per ticker and diff against the replay's logged verdicts for that date — must match ticker-by-ticker exactly."* Done-criteria: "golden test passes."

**Reality (`data/replay/golden_test.json`, the harness's own output):**
```
replay_exists : false
exact_match   : false
in_live_not_replay : [all 31 live-fire tickers]   # replay had 0 fires to compare
in_replay_not_live : []
golden_test_passed : true                          # <-- passes because replay_exists=false
note : "PENDING — replay not yet computed for the latest date"
```

The production gate found 31 fires on 2026-07-02; the replay parquet for 2026 did not exist; so the diff compared 31 live fires against 0 replay fires (a total mismatch), and the predicate `exact_match or not replay_exists` returned **true via the `not replay_exists` branch**. The agent report's `"golden_test_passed": true` is literally true but **carries no verification** — production and replay were never actually compared on identical inputs. The design contract's "must match ticker-by-ticker exactly" was never exercised.

Empirically confirmed the replay produced **no** per-year parts: `data/replay/` contains only `soundness_check.json` (19:54) and `golden_test.json` (19:57) — **no `replay_YYYY.parquet`**. The 2012–2026 replay the report says is "running in background" is not running now (0 processes) and left no parts and no log. So the golden test still cannot be run for real.

Additionally, the `run_golden_test` design has a latent second problem even once replay exists: it compares live `gate(close)` (full series) against a replay row whose verdict was computed on `gate(close.loc[:latest_date])`. For the latest date these are the same slice, so that is fine — BUT the replay for the latest date is written by `replay_year`, which only evaluates **candidate** dates. If the latest date is a `ticks=0` boundary fire that the prefilter drops (F1), the golden test will then show `in_live_not_replay` non-empty and FAIL — i.e. F1 will surface as a golden-test failure once the replay is actually computed. The two findings are linked.

**Impact:** R8 gates the merge on a clean golden test. A vacuous pass is not a clean golden test; the merge gate is unmet. The done-criterion "golden test passes" has not been genuinely satisfied.

**Fix direction:** `golden_test_passed` must be `exact_match` (require `replay_exists=True`); a `PENDING`/no-replay state must be reported as NOT-passed (or the test must first compute the latest year's replay part, then diff). Re-run after F1 is fixed so the latest-date candidate set contains every latest-date fire.

---

## ADVISORY FINDINGS

### F3 — ADVISORY: PR/report claim "no indicator logic reimplemented" is false for study features
`ext_z`, `ext_atr`, `knife_z` are reimplemented locally in `compute_study_features` (L352-385) instead of calling production `engine/extension.py`. `from engine.extension import grade as ext_grade` (L104) is imported but **never used** (confirmed by grep). The local formulas ("mirrors extension_signals", "approximation") will not match production `extension.py` and are not validated against it. These are logged covariates, not gate inputs, so they do not affect fire/non-fire — but P1.1 separability reads these columns, so a silent divergence from the production extension grade would be attributed to the wrong feature definition. Either call `ext_grade`/`extension_signals` on the PIT slice or stamp the columns clearly as harness-local approximations. (PIT-safe: all use the truncated slice.)

### F4 — ADVISORY: `imm2` T3/T4 projection tier not independently detected by the prefilter (currently masked, latent recall risk)
T3/T4 fire on `imm2` (2D-MACD *projected* to cross, not yet crossed) gated by a recent StochRSI cross. The prefilter has no `imm2` detector; it relies on the StochRSI cross (within CONF_W=8 ≤ lookback 10) as the anchor, which is structurally sound for the current thresholds. But this coupling is undocumented and brittle: if `EARLY_CROSS_BARS`/`CONF_W`/`FRESH_TICKS` change, or a T3/T4 fires with its anchoring StochRSI cross >10 daily bars back, the projection fire is dropped with no soundness signal. Same root class as F1. The by-tier scan saw T3 covered (6/6) in the small sample, so no live instance yet — hence ADVISORY. Should be covered by the F1 fix (tier_stream-based mask captures T3/T4 directly).

### F5 — ADVISORY: three §4-mandated study features are null / proxy-only
- `rs_sector_quartile` is **always None** (L432; the "filled in post-processing if sector_closes provided" path is never wired — `replay_ticker` calls `compute_study_features(ticker, close_pit, sector_map)` with no `sector_closes`).
- `adv_dollar_21d` is **always None** (L400) with `adv_dollar_21d_proxy=True`. The comment "volume not available in the close-only series" (L399) is **factually wrong**: `data/yahoo/*.parquet` carries a `volume` column (verified on ZS: `['close','volume','close_price']`); `load_universe` (L138-158) simply never reads it. This feature is also the P0.3/R10 liquidity-hygiene field, so it should be computed.
- `washout_proximity` (L403-411) is a local `price ≤ 200dma×0.90 within 21 bars` proxy, NOT the production cohort-washout logic the masterplan references. §4 says "cohort-washout proximity where computable"; the proxy should be labeled as such.

Net: 3 of 12 §4 features are effectively absent and 3 more (F3) are unvalidated reimplementations. P1.1 separability would run on a half-populated feature set. Not a lookahead; a completeness gap.

### F6 — ADVISORY: near-miss / rejection taxonomy mapping is a lossy heuristic
`_classify_verdict` (L441-474) maps the raw gate reason string to `REJECTION_TAXONOMY` keys via substring matching, with a catch-all `else: tax_reason = "tier_cutoff"` (L471, L473). Only `not_topped_veto` and `freshness_expired` are set precisely (from the gate's own `near_miss_reason`); everything else collapses to `tier_cutoff` or a few guesses. `extension_demote`, `knife_demote`, `sector_cap_displaced`, `board_rank_cutoff`, `event_blackout`, `cohort_null` (all in the closed taxonomy) are never produced by this mapping — because those gates live in the board builder (`build_stock_library.py`), not in `signal_gate.gate()`. So the replay's rejection histogram will be dominated by `tier_cutoff` and will NOT reflect the true rejection reasons that P1.2 (gate P&L per rejection reason) depends on. The fire counts are unaffected; the rejection *labels* are unreliable. Does not block the harness's PIT correctness but limits P1.2 validity — flag for the P1.2 PREREG.

### F7 — ADVISORY: zero overlap between replay fires and the shipped board (worth an explicit note, not necessarily a bug)
Golden test soft check: **0/31** live gate-fires appear in the committed `us_standouts.json` buy list (24 names). The harness dismisses this as expected divergence (different `rank_by`). Per the masterplan grounding facts this is plausible (two-board divergence: standouts uses bottoming-alignment rank, the gate is pure confluence), and the standouts buy list is a *ranked, sector-capped, width-limited* subset, not the raw gate-fire set. But **zero** overlap (not "small") is a strong statement and should be affirmatively explained/tested in the golden test rather than hand-waved — e.g. confirm the 31 gate-fires are a superset that the board's rank+cap+width filters down to a disjoint 24, or investigate whether the gate path and the board's gate path have diverged. Advisory: verify before leaning on the replay for the two-board unification (P2.4).

---

## Bottom line for Fable

The harness's **price-time PIT discipline is genuinely clean** — no same-bar fill, no future-bar leak into past verdicts, no marker-date grading, engine untouched. That part earns a pass and was proven, not assumed.

But it **fails the P0.1 merge gate on two counts**: (F1) the tractability prefilter silently drops real production fires via resample-anchor drift, and its soundness control is structurally blind to that failure; (F2) the golden test — the R8 hard gate — has never actually run (no replay parts exist) and passes vacuously by design when replay data is absent. Both must be fixed and the golden test re-run for real (with F1's fix so latest-date fires are all captured) before merge. F3–F7 are fidelity/completeness issues to fold into the same fix PR; none is a lookahead, but F5 leaves the study feature set half-empty and F6 makes the rejection histogram unreliable for P1.2.

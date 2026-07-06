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

---
---

# P0.1 Replay Harness — PIT AUDIT v2 (fresh adversarial re-audit of the repair PR)

**Artifact re-audited:** PR #1312 branch `ei/p0-1-replay-harness` @ `c60f2d3cec` (repair of the v1-BLOCKED harness). Same single file `scripts/replay_standout_pipeline.py`, now **1,588 lines** (was 1,142; +446 additive, engine still untouched — `git diff origin/main...ei/p0-1-replay-harness -- engine/` empty).
**Auditor:** Opus (PIT audit delegate, §7). **Method:** read PR diff via `git show origin/ei/p0-1-replay-harness:…` (no shared-checkout mutation); loaded the harness by absolute path and **re-ran the load-bearing checks empirically** against `data/massive_stock_day/`, `data/yahoo/`, and the on-disk `data/replay/` parts. Default skeptical — every regression claim independently reproduced, not read from the fix agent's report.
**Date:** 2026-07-05.

## VERDICT v2: CLEAN (mergeable under R8) — 0 BLOCKING, 5 ADVISORY

Both v1 blockers are **genuinely dead** (verified four independent ways below, not by reading the report). The core price-time PIT discipline from v1 still holds and the new Massive rewiring introduces **no lookahead** — the one theoretically-concerning path (future-split back-adjustment leaking into a past PIT slice) was tested and proven verdict-neutral because the leak is a *uniform scalar* on the slice and every gate indicator is scale-invariant. The harness is mergeable. Five ADVISORY items remain; none blocks, but **AF1 (concordance mis-diagnosis)** and **AF2 (report/artifact number mismatch)** should be corrected in the PR text before P1 studies cite them, and **AF3 (Massive-truncated-history anchor divergence)** must be surfaced in the P1 PREREGs as a known measurement property.

> First-sentence claim, strongest true form: **F1 and F2 are fixed and I reproduced both fixes from scratch; the Massive path is PIT-clean; the residual issues are a wrong prose diagnosis of a real ~3–5% yahoo-vs-Massive gate divergence and a report number that isn't on disk — advisory, not blocking.**

---

## REGRESSION CHECKS (each verified empirically)

### RC1 — F1 dead (recall). **PASS.**
- **Mechanism of the fix is structural, not a patched heuristic.** `candidate_dates()` (harness L320-350) returns **every** sufficient-history bar (≥250-bar warm-up, ≥`MASSIVE_ERA_START`), and `main()` wires exactly this into the ledger (L1488) — the lossy prefilter is quarantined into `prefilter_candidates_fast()` explicitly marked "EXPLORATION ONLY … must never feed the ledger" (L353-359) and is used only inside the diagnostic concordance sampler. Since the gate runs on every bar, **candidate ⊇ every fire trivially**; the v1 resample-anchor drop is impossible by construction.
- **The exhaustive recall assertion exists, runs, and passes.** `run_recall_assertion()` (L786-878) calls the *production* `signal_gate.gate()` on the PIT-truncated slice at every bar and halts on the first `fire ∉ candidate`. The on-disk `data/replay/_recall.log` shows a real run: **20 tickers, 20,100 bars gated, 1,197 fires, 0 candidate_misses, 100% coverage, "RECALL PASSED"** (23:42→00:04, 22 min — consistent with the ~0.11 s/bar cost). Not a random sample; exhaustive per-ticker with halt-on-miss.
- **ZS 2024-05-10 (the v1 witness) is a genuine T1/ticks=0 fire and the harness reproduces it.** I re-ran it independently: `signal_gate.gate('ZS', yahoo.loc[:2024-05-10])` → `buyable=True, tier=T1, ticks=0`; `replay_ticker('ZS', …)` → `fire, tier=T1`. The golden test asserts this in code with `raise AssertionError` on failure (L985) and records `passed:true`.
- **Caveat (see AF3):** ZS is **not** in the 57-ticker primary cohort, so the regeneration proof of ZS lives in the golden test's yahoo path, **not** in the primary parquet parts — and on the *Massive* panel the same date is **not** buyable (tier=None, ticks=43). That divergence is AF3, not an F1 regression.

### RC2 — F2 dead (golden). **PASS.**
- `golden_test_passed = bool(replay_exists and exact_match)` (L964) — the v1 vacuous `exact_match or not replay_exists` is **gone**, and `replay_exists` now requires the replay path to have actually produced fires (L952).
- The stored `data/replay/golden_test.json` shows a **real diff run in yahoo-fidelity mode**: `prod_fire_count=62`, `replay_fire_count=62`, `in_prod_not_replay=[]`, `in_replay_not_prod=[]`, `tier_mismatches=[]`, `exact_match=true`. The test drives the harness's OWN `replay_ticker()` path (L945) against the production `_gate_fires_on_date()` on the same yahoo panel — apples-to-apples, exact. This is the design contract ("must match ticker-by-ticker exactly") genuinely exercised.
- The v1 "no parts exist" condition is resolved: `data/replay/replay_2022..2026.parquet` exist with real content (see RC-DATA).

### RC3 — Board-stage post-pass (F6/F7). **PASS (with honest, convincing diagnosis for the non-reproducible part).**
- **F6 fixed:** the `tier_cutoff` catch-all is **eliminated** from `_classify_verdict()` (L566-602). Gate rejections now carry true causes; the on-disk histogram is `no_signal 42,510 / not_topped_veto 5,988 / board_rank_cutoff 932 / hygiene_screen 486`. `no_signal` dominating is *honest* (most bars have no cross), not a laundered catch-all. `board_post_pass()` (L1098-1194) adds PIT-computable board reasons — `knife_demote 1,459`, `board_rank_unresolved 1,208`, `extension_demote 728` — using the **production** `STRETCHED_Z` threshold for the extension brake.
- **F7 (0/62 board overlap) is diagnosed, not hand-waved, and the diagnosis is correct.** The board buy list is produced by `build_stock_library.py` L1900-2083 from `stock_score.conviction_profile()→composite_z` (needs cross-sectional PEAD/quality/tailwind axes) + `entry_signal.assess()` + coiled cohort-washout + `ladder.state` — none derivable from a close-only PIT slice. Forcing reproduction would be verification theater; the harness correctly stamps the non-reconstructable residual `board_rank_unresolved` rather than inventing a reason. **This is the right call under §4.2/§4.4 (boring-baseline / quarantine).**

### RC-DATA — parts exist, counts match the report's headline. **PASS.**
- `data/replay/replay_2022..2026.parquet` = **54,361 rows** total (2022:6,466 / 2023:13,010 / 2024:13,783 / 2025:14,000 / 2026:7,102), **3,395 fires** (`verdict_type=="fire"`, byte-equal to `eligible & tier∈BUYABLE`), 1,050 near-miss, 49,916 rejection. Matches the report's `primary_window_rows:54361 / fires_primary_window:3395` **exactly**.
- The report/log figure `rows=108722 fires=6790` is the **pre-fix double-count** (the summary glob matched `replay_boarded.parquet`); commit `c60f2d3c` fixed it and the current `print_summary`/`board_post_pass` globs (`replay_2*.parquet`) correctly exclude the boarded file. The 54,361 figure is the deduplicated truth. Reconciled.
- Grading integrity intact: `fill_offset==1` on all 3,394 fillable fires (1 last-bar fire correctly unfilled), `fwd_ret_21` populated 3,009/3,009 on non-censored fires, terminal states populated.

---

## NEW-SCOPE (Massive rewiring) — LOOKAHEAD & VALIDITY

### NS1 — Massive split-adjust PIT-safety. **PASS (proven verdict-neutral).**
Concern: `load_universe()` applies `split_adjust()` **once to the full series** (L257), then `replay_ticker` slices the already-adjusted series (L647). A **future** split therefore back-multiplies the *past* bars inside a PIT slice — I confirmed this directly (AVGO 10:1 2024-07-15: past bars in a 2024-07-10 slice sit at ~174 = post-split scale, a 9× shift vs a true-PIT re-adjust). **But this is verdict-neutral**: because a future split is at a full-series position *after the entire slice*, its factor is a **uniform scalar** on every bar of `close_pit` (measured scale-ratio spread = `1.00000000`), and every gate indicator (RSI/MACD/StochRSI/SMA ratios) is scale-invariant. Empirical proof: `gate(full-adjust-then-slice)` == `gate(adjust-only-close_pit)` on AVGO at 4 pre-split dates — identical `tier`/`ticks`/`buyable`. **No lookahead reaches the fire verdict or forward *returns* (ratios).** *Cosmetic only:* absolute `entry_price`/`adv_dollar_21d` recorded for a pre-split fire are on the post-split scale — irrelevant to any ratio-based study statistic, but P1 should not read raw `entry_price` levels across a split without normalizing.
`split_adjust()` reconstruction verified vs yahoo shape: PANW/ZS **0.00%**, NVDA **0.34%** max deviation — the panels are equivalent in shape.

### NS2 — Stamp rules S1/S2/S3 per the memo (default-true on ambiguity). **PASS.**
`survivor_bias = not(s1_era and s2_source)` with `s1_era = sd≥2021-07-06`, `s2_source = price_source=="massive"` (L660-665) — strict/default-true, exactly §2.1/§2.2. On disk: **all 54,361 rows** `survivor_bias=False`, `price_source=massive`, min signal_date 2022-06-30 (250-bar warm-up from Massive's 2021-07-06 start — correct, not a bug). `verdict_grade == (¬survivor_bias ∧ ¬horizon_censored)` holds for **every** row; 47,147 verdict-grade / 7,214 horizon_censored — matches the report. No pre-2021 row is unstamped (0 exist to test, vacuously satisfied). Memo-conformant.

### NS3 — Feature completeness actually populated in the parts (not just coded). **PARTIAL — see AF4.**
Verified by reading the parquet, not the code: on the **per-year parts**, fires carry `ext_z / near_52wh / ext_grade` (production `extension_signals`, **100%**), `adv_dollar_21d` (**100%**, `proxy=False` — F5's "volume unavailable" error is fixed, volume read from both stores), `ext_atr/knife_z/washout_proximity` (**100%**, correctly stamped harness-local). Features are **PIT-invariant** (re-verified: feature values on `close.loc[:t]` are identical regardless of trailing data). **BUT `rs_sector_quartile` is 0% on the per-year parts** and only filled (1,806/3,395 = **53%**) in `replay_boarded.parquet` by the date-major post-pass. P1 studies MUST read `replay_boarded.parquet` (67 cols, adds `board_reason/board_verdict/sd`) for that column, not the raw parts — see AF4.

---

## ADVISORY FINDINGS (v2)

### AF1 — ADVISORY: concordance residual is **mis-diagnosed** (resample-anchor/history-length, NOT dividends).
The report claims the yahoo-vs-Massive concordance residual is "dividend adjustment (yahoo is total-return), diagnosed as non-systematic." **This is falsified.** Decisive test: ZS pays no dividend and its yahoo and Massive-split-adjusted prices are **penny-identical** around 2024-05-10, yet `gate(yahoo-full)` = T1/ticks=0 while `gate(Massive)` = None/ticks=43. Truncating the *yahoo* series to Massive's start date (2021-07-06) reproduces the Massive verdict **exactly** (None/ticks=43). The divergence is therefore driven by **series start/length shifting the 3D/2D resample-bucket anchoring** — the same mechanism as the original F1 — **not** dividends. Prevalence on identical-price names: ~**5%** buyable-disagreement for long-history names, ~**3%** even for names with no truncation confound (residual tail-alignment sensitivity). Not blocking (concordance still >95%), but the PR's causal prose is wrong and would mislead P1.

### AF2 — ADVISORY: the report's concordance numbers are **not on disk**.
The fix agent's report states concordance "95.6% over 50 names/1960 bars (98.5% in-harness cohort)." Only the **98.5% over 12 names / 480 bars** figure exists in `golden_test.json`; "95.6 / 50 names / 1960 bars" appears in **no** artifact (grepped all `data/replay/*.json` and `*.log`). Both exceed the 95% STOP threshold and my independent broad recomputation (~95–97% on a 60-name random sample) confirms the real number is genuinely above threshold and **not hiding a sub-95% result** — so this is accuracy, not a gate breach. Fix the report to cite the on-disk 98.5%/12-names value (or re-run and persist the 50-name computation) before any P1 PREREG cites a concordance number.

### AF3 — ADVISORY: Massive's 2021-07-06 truncated start systematically anchor-shifts every ledger verdict vs full-history production.
Because the verdict-grade ledger reads Massive (every name starts 2021-07-06), the gate's resample buckets are anchored on a warm-up-truncated series. The ledger is **internally consistent and PIT-clean** (all names share the same basis; the gate is deterministic on it), so this does not corrupt within-ledger P1 statistics. But it means: (a) the golden-test 62==62 match is proven on the **yahoo** panel, which is a *different detector* from the Massive ledger for names whose true history predates 2021-07-06 (~40% divergence-prone bars near the window's leading edge); (b) the earliest ~1 year of the window can't produce candidates (250-bar warm-up), so the ledger effectively starts 2022-06-30 not 2021-07-06 — the memo's "2021-07-06 →" primary window is ~11 months narrower in practice. **P1 PREREGs must state the effective window as ~2022-06-30 → last-replay-date** and treat the golden-test fidelity as a yahoo-panel guarantee, not a Massive-panel one. Honest measurement property, not a lookahead.

### AF4 — ADVISORY: two-artifact split (`rs_sector_quartile` only in `replay_boarded.parquet`) is a footgun.
`rs_sector_quartile` (a §4-mandated feature P1.1 separability reads) is **null in the per-year parts** and only populated (53%) in `replay_boarded.parquet`. A P1 study that reads the natural `replay_2*.parquet` glob gets an all-null column with no error. Document loudly that `replay_boarded.parquet` is the canonical P1 input, or backfill the column into the parts. The 53% fill is honestly limited by the 57-ticker cohort's thin same-sector cross-section (cohorts with <4 peers stay null) — a fuller universe raises it. Not a bug; a consumption hazard.

### AF5 — ADVISORY: primary replay ran on a 57-ticker board-priority cohort, not the full 927-name universe.
`--max-universe 60` capped the run (all-bars gating at ~0.11 s/bar makes the full 927-name universe ~28 h). The parts are per-year resumable and the code path is identical, so extending is a plumbing re-run with no code change — but **the current ledger is a 57-name slice**, and P1 episode-clustered n-floors (memo §2.4.6) will be thin on it. Not a correctness issue; a coverage/power caveat the P1 studies must inherit and, per the memo, honor with INSUFFICIENT-POWER rather than borrowing. (S&P500 membership also uses the current snapshot, not PIT-historical — memo §3 already parks this; delisted names still enter via Massive + donor lists.)

---

## Bottom line for Fable (v2)

**The repair is real and the harness is mergeable under R8.** F1 is dead by construction (candidate = every bar) with an exhaustive halt-on-miss recall assertion that ran and passed (1,197 fires, 0 misses); F2 is dead (`golden_test_passed = replay_exists ∧ exact_match`, 62==62 exact diff on the yahoo panel, ZS 2024-05-10 T1 asserted in code); F3/F5/F6 fixed (production `extension_signals`, `adv_dollar_21d` from volume, gate taxonomy with no `tier_cutoff` catch-all); stamps memo-conformant; grading next-bar-clean. The new Massive path is **not** a lookahead — the only concerning route (future-split adjustment) is a uniform scalar the scale-invariant gate ignores, proven verdict-identical.

The residual work is **prose and consumption discipline, not code correctness**: the PR mis-diagnoses a real ~3–5% yahoo-vs-Massive gate divergence as "dividends" when it is resample-anchor/history-length (AF1); the report cites a concordance number that isn't on disk though the true value clears the threshold (AF2); and P1 must be told that the effective window is ~2022-06-30 (not 2021-07-06), that the fidelity guarantee is yahoo-panel not Massive-panel (AF3), that `replay_boarded.parquet` is the canonical input (AF4), and that the ledger is a 57-name power-limited slice (AF5). Fix AF1/AF2 in the PR text and carry AF3–AF5 into the P1 PREREGs. **CLEAN.**


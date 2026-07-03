# W3 (volume program) — Verification + Adversarial Review

*Gate verdict: **SHIP** (with 3 non-blocking report/doc-accuracy fixes filed). China Alpha Program · Wave W3 (F7). Verifier run 2026-07-03.*

Both phase-0s reproduce their headline numbers **exactly and deterministically**; both land the pre-registered NO-GO the reports claim; the infra collectors route through the run adapter, fail open on akshare, are idempotent, and are staged by the nightly asia lane; all 62 touched tests + 670-test bounded smoke pass; **zero template/builder/page/rank changes** — the "nothing wired" law holds. No blocker rises to false-ship level. The three findings below are real but do not flip any verdict and do not put bad data on a live surface.

---

## 1. Reproduction (deterministic — the load-bearing check)

Re-ran both scripts end-to-end (`PYTHONPATH=$PWD python3.12 ...`):

- **`scripts/china_turnover_phase0.py`** → NO-GO. Full |t|=**0.69**, perm_p=**0.5115**, residual⊥reversal t=**0.72**, positive control (reversal) t=**1.18** mean +0.638, T6 fill 0.362 vs c2c 0.331, decile Spearman +0.079. **Report byte-identical on re-run** (`diff` empty). Every number in `W3A_ABNORMAL_TURNOVER.md` §7 matches.
- **`scripts/china_max_phase0.py`** → NO-GO. Full t_HAC=**-1.118**, pre-2021 -0.605, post-2021 -0.982, IC t=**-3.985**, screen lift **0.015%/p=0.606**, perm_p=**0.278**, positive control t=**2.333**, monotonicity **6/9**, corr(MAX,rev)=-0.384. All match `china-max-phase0.md`.

Both scripts: seeded RNG (turnover SEED=3, MAX SEED=42), 2000 perms each, no network, read-only on `data/` (write only `reports/` + the w3 mirror). Confirmed by grep — no `requests`/`urllib`/`akshare` import in either backtest.

## 2. Constitution compliance (binding — masterplan §4)

- **Substrate = `china_stocks_raw` for RETURNS in BOTH** (`RAW_DIR="data/china_stocks_raw"`). `china_search/members.parquet` used **only as an auxiliary sector join** — justified, not a returns dependency → **not a blocker**. (Turnover drops 98 no-sector names for the within-sector residualisation; correct.)
- CSI300-relative excess (510300.SS), T+1 (H+L)/2 entry, locked-limit (`hi==lo==close`) exclusion at the entry bar, >20%-locked name drop, |ret|>0.25 split-artifact zeroing — all present in code (turnover L181-195, L213-217; MAX build_locked_limit_mask + T+1 fill).
- Close-to-close reported alongside fill-realistic (turnover T6; MAX §1). Time-half + pre/post-era splits present. 2000-perm placebo present and reproduced. Positive control fires in both.
- **Orthogonality**: turnover T2 residualises on within-sector 3M reversal (residual t=0.72 → REDUNDANT-WITH-REVERSAL rule logged even though raw is null). MAX dual check present (§6: partial-IC vs reversal AND abn-turn; corr both reported).
- **Registry**: `data/experiments/registry_seed.json` valid JSON, schema `experiments_registry_seed.v1`, **+68 insertions / 0 deletions** (additions-only, no clobbering — unlike the #1121 incident). Four W3 entries present: `w3a-abnormal-turnover`, `w3b-max-lottery-screen`, `w3c-margin-velocity-substrate`, `w3c-lhb-backfill`, all `program: china_alpha, wave: W3`; recorded verdicts match the reproduced numbers.
- **Nothing wired**: `git diff --stat` shows only `collectors/china_lhb.py`, `collectors/china_margin_detail.py`, `scripts/collect.py`, `registry_seed.json`, `data/china_lhb/events.parquet`. No template / builder / rank / page touched.

## 3. Infra review (W3-C)

- **Run-adapter routing**: `ChinaLhbAdapter` / `ChinaMarginDetailAdapter` both subclass `collectors.base.Adapter`, `.fetch()` calls `refresh()` and returns a non-empty sentinel DataFrame so `run_adapter` records success even on an idempotent no-op (avoids false circuit-breaker trips). Both registered in `scripts/collect.py` L155-156.
- **Shard/staging**: both group keys start with `china` → `group_members("asia")` (collect.py L280-281) auto-includes them. `asia-close.yml` L73 `git add data/` stages `data/china_lhb/` and `data/china_margin_detail/`. Not in the sentinel lane, so the #1026 staging-gap does not apply. Evidence verified in-file.
- **akshare fail-open**: LHB `_fetch_detail`/`_fetch_inst` catch per-call → return None; `refresh()` returns 0 without raising. Margin `_detail_for` catches per-exchange → `continue`, returns {} on total failure; `refresh()` returns 0. Confirmed by the passing `test_*_akshare_failure_non_fatal` tests.
- **Idempotency**: LHB per-UTC-day asof guard; margin `_stored_sessions()` per-session guard; both dedup via `_drip.append_snapshot` (date,ticker) keep-last. Tests pass.
- **LHB backfill real run SUCCEEDED**: `data/china_lhb/events.parquet` grew HEAD 687 rows/6 dates → **28,580 rows / 409 dates / 4,313 tickers / 2024-07-01..2026-07-03**; `history.parquet` alias = 28,580 (byte-copy). Size 0.34 MB << 20 MB → in-tree correct. One 2024-11 chunk gap acknowledged (akshare transient).

## 4. Tests + hygiene

- Touched files: **62 passed** (`test_china_alpha_w3c_infra.py` 13, `test_china_max_phase0.py`, `test_china_turnover_phase0.py`).
- Bounded smoke `-k "china or turnover or max or lhb or margin"`: **670 passed, 1 skipped, 0 failed** (144s).
- **Hygiene**: `git status` identical before/after verification — my re-runs dirtied **no additional tracked data** (tests mock akshare + use tmp paths). `data/vector/regime_calibration.json` is untracked/pre-existing (left uncommitted, per instruction). `events.parquet` + `registry_seed.json` modifications are the executors' intended writes, not test pollution. **I restored `reports/china-max-phase0.md` + the w3 mirror to their original hand-edited content after my reproduction re-run overwrote them** (numbers identical; only the hand-added U-shape prose paragraph differs — see finding F2).

---

## Findings (all NON-BLOCKING — filed for cleanup, none flips a verdict)

**F1 — MAX universe is gated on a current board snapshot (survivorship-narrowing).**
`scripts/china_max_phase0.py:80-87` restricts the universe to `board_tickers = set(members.index)` from `china_search/members.parquet` (a **current curated snapshot**, 1495 names), loading **1487 of 1568** raw names and silently dropping **81 still-trading** names not on today's board. This is a mild forward-looking selection the constitution's "build on raw, not the members-driven universe" spirit warns against. The **turnover** harness does NOT do this (it loads the full raw universe, dropping only 98 no-sector names). Severity is low because (a) the excluded names are curation-dropped, not delisted (so not classic delisting survivorship), and (b) a survivorship-narrowed universe biases *toward* finding an effect — a NO-GO here is the conservative direction. Recommend the future re-run use the full raw universe (as turnover does) and demote members to a sector-join only. Not a false-ship risk.

**F2 — MAX report §4 placebo prose contradicts its own number.** `scripts/china_max_phase0.py:763-764` hardcodes: *"Real t at a remarkable percentile (perm-p < 0.05) confirms the L/S is genuine...not measurement noise."* — but perm-p is **0.278** (NOT < 0.05), i.e. the L/S is statistically indistinguishable from the null. This boilerplate is FALSE for this NO-GO result and appears verbatim in both report copies. The §7 verdict is correctly NO-GO, so no decision is affected, but the line is misleading and should be made conditional on the actual perm-p. (Also: the report's hand-added §1 "Key divergence / U-shaped" paragraph is a manual post-run edit — its numbers are consistent with the reproduced decile table, so it is sound, just not machine-emitted.)

**F3 — Infra report row-count line is inaccurate.** `W3C_DATA_ACCRUAL_INFRA.md` C2 table says *"Events written 33,605 (net in events.parquet after dedup)"* — but `events.parquet` actually holds **28,580** rows (verified). 33,605 is the **pre-dedup** append count; calling it "net after dedup" is wrong. Related: the backfill docstring (`scripts/backfill_china_lhb.py:10`) claims dedup on `(date, ticker, reason)`, but `_drip.append_snapshot` dedups on **(date, ticker)** keep-last only — so multi-reason same-day appearances are collapsed to one row (with one reason's net_buy kept, not summed). This is a **substrate caveat the future LHB seat-quality phase-0 must know** (net_buy per name/date is under-counted when a name lists for >1 reason); it does not affect this wave since nothing runs on the store yet.

---

## Verdict: **SHIP**

Both phase-0s are well-powered true negatives reproduced to the digit; both correctly land NO-GO against pre-registered thresholds written before the results; the positive control fires in both (MAX t=2.33 cleanly; turnover t=1.18 at directional-liveness with full transparency about the conservative construction); the orthogonality gates are present and correct; the infra is production-shaped (adapter-routed, fail-open, idempotent, staged, backfill run succeeded at 28.6k events); registry is additions-only valid JSON; nothing is wired. The three findings are report/doc-accuracy and a methodology-tightening note for the *next* wave — none is a false-ship risk (F1 biases conservative, F2/F3 are prose/count corrections on NO-GO results). Clean to land; fold F1-F3 into a follow-up cleanup.

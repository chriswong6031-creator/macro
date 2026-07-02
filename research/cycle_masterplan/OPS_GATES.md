# OPS_GATES.md — Gate-Semantics Register

**Wave:** W1.5 — ops-lane ownership
**Ruling:** A10 of `research/CYCLE_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
**Status:** 2026-07-02 — initial register; updated as downstream waves land.

---

## 0 · Purpose

Every gate the cycle-intelligence masterplan names must declare:

1. **Where it runs** — `ci.yml` hard job / weekly lane resilient step / `cycle-calibration.yml` step.
2. **Abort-lane vs log-and-skip** — does a failure fail the workflow job (abort-lane), or is the failure
   annotated + summarized but the job exits 0 (log-and-skip / fail-open)?
3. **Current status** — `EXISTS` (code merged to main, gate live) / `PLANNED (Wx.y)` (wave that will add it).

The resilient `run_py` wrapper in `weekly.yml` makes every step inside it fail-open by design (non-zero exit
→ `::error::` annotation + job summary entry, but the job continues and exits 0).  A gate placed inside
`run_py` is therefore always log-and-skip, regardless of whether the script itself raises.  Load-bearing
gates **must** be placed in `ci.yml` or `cycle-calibration.yml` outside `run_py` to have abort-lane teeth.

---

## 1 · Gate register

| Gate | Where it runs | Semantics | Wave added | Status |
|---|---|---|---|---|
| **ontology-JS drift** (`gen_ontology_js --check`) | `ci.yml` job `cycle-ontology-js` | ABORT-LANE — PR fails RED if `site/cycle_ontology.js` drifts from `engine/cycle_ontology.py` output | W1.5 | EXISTS |
| **ontology-JS drift** (first weekly-lane step) | `weekly.yml` `run_py` wrapper | LOG-AND-SKIP — stale committed JS is re-generated before any page builder runs; failure annotates but doesn't kill weekly | A12 ruling; add in weekly lane step when W1.2 weekly hook is written | PLANNED (W3.1) |
| **forward-log writer** (`test_cycle_forward_log.py`) | `ci.yml` job `cycle-forward-log` | ABORT-LANE — keep-FIRST invariant + cone edges are structural contracts for measurement | W1.5 | EXISTS |
| **forward-log writer** | `cycle-calibration.yml` step | ABORT-LANE — monthly re-check that the writer still passes after any engine edits | W1.5 | EXISTS |
| **grading_stats library** (`test_grading_stats.py`) | `ci.yml` job `cycle-grading-stats` | ABORT-LANE — one `cone_coverage`, correct China-grader refactor regression | W1.5 | EXISTS |
| **grading_stats library** | `cycle-calibration.yml` step | ABORT-LANE — monthly re-check | W1.5 | EXISTS |
| **validated-grep** (eng: `validated`/`已验证` token in all graded artifacts) | `ci.yml` (to be added as new job when D2 grader ships) | ABORT-LANE — no graded artifact can omit its provenance token | PLANNED (W2.4) | PLANNED (W2.4) |
| **epoch homogeneity** (`basis_version_homogeneous` check on backfill.parquet) | `cycle-calibration.yml` step (LOG-AND-SKIP) | LOG-AND-SKIP — mixed-epoch warning annotates the run; a full HARD version gates W2.3 acceptance | PLANNED (W2.3) | PLANNED (W2.3) |
| **stale-tape fail-closed** (`check_cycle_tape_freshness`) | `cycle-calibration.yml` step (LOG-AND-SKIP) | LOG-AND-SKIP — stale series renders `DATA_MISSING` chip; the check reports which series crossed the threshold but never blocks the lane | PLANNED (W3.x) | PLANNED (W3.x) |
| **price-basis audit** (`audit_price_basis.py`) | `cycle-calibration.yml` step (LOG-AND-SKIP) | LOG-AND-SKIP — AST scan is authoritative; this generates the report for human review; does not block | PLANNED (W2.2) | PLANNED (W2.2) |
| **hazard-model freshness** (`check_hazard_model_freshness.py`) | `cycle-calibration.yml` step (LOG-AND-SKIP) | LOG-AND-SKIP — >100d stale triggers card degradation to prior; the check alerts but never blocks | PLANNED (W4.2) | PLANNED (W4.2) |
| **nav guards** (`check_nav_mega`, `check_nav_gap`) for measurement.html | `ci.yml` existing jobs (already run on `site/**` changes) | ABORT-LANE — existing jobs cover any new page added by D2/D3 waves | EXISTS (A18 ruling) | EXISTS |
| **badge-passport ratchet** (`check_badge_passport.py`) | `ci.yml` job `outcome-spine` | ABORT-LANE — no conviction badge without a provenance passport | W4 | EXISTS |

---

## 2 · Concurrency group map

| Workflow | Concurrency group | cancel-in-progress | Lane purpose |
|---|---|---|---|
| `weekly.yml` | `pipeline-batch` | false | Deep-dive: collectors + calibrations + all dashboards |
| `backfill.yml` | `pipeline-batch` | false | Full-history data collection (serializes behind weekly) |
| `special-sits-backfill.yml` | `pipeline-batch` | false | LLM special-sits enrichment (serializes behind weekly) |
| `daily.yml` | `pipeline-daily` | false | Nightly: collect → engine → render → deploy |
| `cycle-calibration.yml` | `cycle-calibration` | false | Monthly cycle-intelligence validation (this wave) |
| `ci.yml` | _(none — each job is independent)_ | n/a | Pre-merge guards; each job runs in parallel |
| `engine-render.yml` | _(none)_ | n/a | Fast re-render on engine push |
| `render.yml` | _(none)_ | n/a | Fast re-render on template push |

`cycle-calibration` is its own group so it never blocks the main `pipeline-batch` queue and is never evicted
by a concurrent dispatch of `weekly.yml` or `backfill.yml`.

---

## 3 · Weekly lane wall-time budget

The weekly lane runs on a 2-core self-hosted macstudio runner (`runs-on: [self-hosted, macstudio]`) with a
**120-minute timeout**.  R2 §0 confirmed the "45m was too tight" comment and the `pipeline-batch` serialized
queue shared with `backfill.yml` (also 120 min) and `special-sits-backfill.yml`.

### 3.1 · Steps as of W1.5 (from `weekly.yml`)

| Step label | Script | Timing estimate | Source |
|---|---|---|---|
| weekly collectors (COT/NAAIM/AAII/fundamentals) | `scripts.collect` | ~5 min | R2 §4 prose |
| dead-name CIK crawl (EDGAR FTS, SEC-paced, ~200/run) | `scripts.build_dead_name_fundamentals --resolve-only` | ~3 min | R2 prose |
| dead-name fundamentals (de-bias, ~200 filers/run) | `scripts.build_dead_name_fundamentals` | ~3 min | R2 prose |
| dead-name prices (Stooq/Polygon, ~150/run) | `scripts.build_dead_name_prices` | ~2 min | R2 prose |
| dead-name bankruptcy imputation (8-K 1.03) | `scripts.build_dead_name_delisting` | ~2 min | R2 prose |
| de-biased IC scorecard | `scripts.factor_ic_scorecard --debiased` | ~2 min | R2 prose |
| signal factory (breadth honesty) | `scripts.signal_factory` | ~3 min | R2 prose |
| recalibrate (macro) | `scripts.recalibrate` | ~5 min | R2 prose |
| regime engine (`engine.run`) | `engine.run` | ~3 min | R2 prose |
| S&P allocation vector | `scripts.build_spvector` | ~2 min | R2 prose |
| macro dashboard + US stocks (build_site) | `scripts.build_site` | ~15 min (render ≈ 67 min profile; build_site subset) | R2 §0 verified |
| china fundamentals (subset + widen) | `collectors.china_fundamentals` ×2 | ~5 min | R2 prose |
| calibrate china | `scripts.calibrate_china` | ~3 min | R2 prose |
| build china | `scripts.build_china` | ~5 min | R2 prose |
| HK fundamentals + calibrate + build | 3 × HK scripts | ~5 min | R2 prose |
| calibrate/build commodities | 2 scripts | ~3 min | R2 prose |
| research commodity conviction | `scripts.research_commodity_conviction` | ~2 min | R2 prose |
| calibrate/build bonds + rate-inflation | 3 scripts | ~3 min | R2 prose |
| calibrate/validate GEX/build vector | 3 scripts | ~3 min | R2 prose |
| AI brief | `scripts.build_aibrief` | ~3 min | R2 prose |
| library rebuilds (×4) | `scripts.build_{china,hk,canada,intl}_library` | ~3 min | R2 prose |
| inject data-base shim | `scripts.inject_data_base` | <1 min | R2 prose |
| commit + push (with rebase retry) | git | ~2 min | R2 prose |
| strip heavy stores + upload pages artifact | bash + actions | ~2 min | R2 prose |
| **Estimated total** | | **~80–95 min** | R2 net (conservative) |

**Headroom:** ~25–40 min before the 120-min timeout.  R2 warning stands: the queue is near-full.  Every
new calibration step added to the weekly lane must declare its wall-time.

### 3.2 · Steps NOT in the weekly lane yet (planned waves)

| Planned step | Wave | Estimated runtime | Lane target |
|---|---|---|---|
| D2 PIT backfill loop (membership-free universes) | W2.3 | ~10–15 min (R2 §4) | `cycle-calibration.yml` (own group — NOT weekly) |
| D5 hazard panel fit + walk-forward | W4.2 | unknown; ~1,590-pair lead-lag Stage-A alone is unquantified (R2 §A16) | `cycle-calibration.yml` |
| D4 price-basis audit report | W2.2 | <2 min (AST scan) | `cycle-calibration.yml` |
| D3 stale-tape freshness check | W3.x | <1 min | `cycle-calibration.yml` |

**Critical note from R2 §A4:** D5 lead-lag ~1,590 pairs × 6 lags × 2000-block-bootstrap is **unquantified**
on a 2-core box.  R2 calls it "not single-digit minutes."  Before this is scheduled, the runtime must be
measured and declared.  It must NOT land in the `pipeline-batch` (weekly) lane.

---

## 4 · Fail-open vs fail-closed decision tree

```
Is the gate catching a DATA CORRECTNESS issue that would silently ship wrong numbers?
  YES → ci.yml hard job (abort-lane, blocks PR merge) OR cycle-calibration hard step (abort-lane)
  NO  → Is the gate a calibration freshness / staleness check?
          YES → cycle-calibration step with `|| true` (log-and-skip)
          NO  → weekly lane run_py step (always log-and-skip inside run_py)
```

The `run_py` wrapper in `weekly.yml` ALWAYS makes a step fail-open regardless of the script's own exit code.
**Never rely on a weekly-lane `run_py` step to enforce a hard gate.**

---

## 5 · Alert gap register

The production Telegram/Discord alert path (`python -m scripts.notify`) reads `data/run_status.json`, which
is written only by the main pipeline (`daily.yml` and `weekly.yml`).  The `cycle-calibration.yml` lane does
not write to `run_status.json`, so its failures do **not** trigger Telegram/Discord alerts.

Current alert mechanism for calibration failures:
- GitHub `::error::` step annotation (visible on the run page and the PR check)
- Run-page summary table (written by the `calibration failure summary` step on `if: failure()`)
- GitHub's built-in workflow-failure email notification (if enabled per user settings)

Gap: no Telegram/Discord push on calibration lane failure.  The fix is either:
(a) write a lightweight `data/calibration_status.json` from the calibration lane and extend
    `scripts.notify` to read it, or
(b) call `scripts.notify` directly with a `CALIBRATION_FAIL=1` env var.

This gap is documented here; wiring it is a follow-up task for the first wave that adds a calibration
step that is painful to miss (e.g., W4.2 hazard refit failure → mass card degradation).

---

## 6 · Measurement method for weekly lane wall-times

Per-step wall-times are not currently logged as CI artifacts.  To measure them:

1. Add `time python -m <script>` wrapper inside the `run_py` shell function body in a local `weekly.yml`
   copy, or run the scripts individually on the macstudio and record wall-clock.
2. The GitHub Actions run log timestamps each step's start/end — the run page shows per-step elapsed
   times; export via the GitHub Actions API (`GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs`).
3. The `$GITHUB_STEP_SUMMARY` pattern in `run_py` captures `tail -n 60` of each step's log — extend it to
   also write the elapsed seconds to capture timing data automatically.

Until a measurement pass runs, the times in §3.1 are **estimates from R2 prose and the 67-min full-render
profile** (R2 §0 confirmed render.yml alone is 75 min; `build_site` as called from `weekly.yml` is a subset
of that).

---

## 7 · Status log

| Date | Wave | Change |
|---|---|---|
| 2026-07-02 | W1.5 | Initial register; `cycle-calibration.yml` created; three hard gates added to `ci.yml` (`cycle-ontology-js`, `cycle-forward-log`, `cycle-grading-stats`); ci.yml paths extended to watch cycle-intelligence files. |

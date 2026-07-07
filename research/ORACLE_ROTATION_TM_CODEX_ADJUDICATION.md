# Oracle Adjudication — Codex Rotation Time Machine Extended Patterns

**Date:** 2026-07-06 · **Adjudicator:** Fable (main loop) · **Verification:** 4 lanes (Opus ×3, Sonnet ×1)
**Subject:** External research run by Codex GPT-5.5 (xHigh), reading OUR Oracle Time Machine tape.
**Governance:** intake-only. No engine/registry/grammar change. No new compound registered (see §5). No cycle-position confluence used (the 2026-07-05 "rotation × cycle-position = DON'T TEST" ruling is not touched). "No Codex for Oracle" is respected: this is Fable-adjudicated intake of external SPEC-level research, not Codex-authored evaluation code.

## 0. Source artifacts

- Report (copied on-record): [`reports/rotation-time-machine-extended-patterns.md`](../reports/rotation-time-machine-extended-patterns.md) and the base [`reports/rotation-time-machine-sector-etf-research.md`](../reports/rotation-time-machine-sector-etf-research.md).
- Codex scripts + heavy CSVs remain untracked in a separate Codex worktree (`~/.codex/worktrees/dbbf/`); the 80 MB `enriched_daily_features.csv` and mined CSVs are deliberately NOT committed (R2 data-plane norm). Everything they read — `site/oracledata/` (175 committed files), `data/yahoo`, `data/fred` — already lives in this repo, so any follow-up runs in-tree with no Codex worktree.

## 1. What the run did

A pattern gauntlet over the Oracle episode catalog + sector-ETF tape: 31 curated rotation rules + a mined boolean scan (2 intents × 5 anchors × 15 filters + pairs ≈ 1,210 combinations), scored by next-session-close entry and forward return relative to the equal-weight sector-ETF cross-section, with a Newey–West (HAC) t. It reported **3 KEEP** (`episode_onset_in`, `episode_onset_in_peak_ge_1_5`, `onset_in_plus_same_complex`), **4 WATCH**, **24 PRUNE**, and proposed a display-only `sector_rotation_schedule.v1` shadow artifact.

## 2. Verification (method + reproduction)

Four independent lanes; models routed per house law (Opus for red-team/review, Sonnet for reproduction):

- **Reproduction (Sonnet):** rebuilt the panel from scratch (4.7 s) and matched every headline number exactly — `episode_onset_in` n=356 / 0.5342% / hit 58.7% / t 3.467; `episode_onset_in_peak_ge_1_5` n=342 / 0.5448% / t 3.378; `onset_in_plus_same_complex` n=186 / 0.5859% / t 3.418. CSV↔report transcription clean. Both scripts compile. The research is honest and reproducible.
- **Statistics red-team (Opus):** the base `episode_onset_in` effect survives a month-block cluster bootstrap (t≈4.19), a dev/holdout split at 2019-12-31 (holdout n=116, t=2.15), and BH-FDR q=0.10 across the 31-test family — i.e. it clears a *pre-registration / display* bar, not a *promotion* bar. Three real problems: (a) a look-ahead filter in one KEEP (§3.2); (b) a hidden **2009–2016 dead regime** the median-split "stability" metric cannot surface (§6); (c) the mined scan is selection-post-mining with ~5× n-inflation (`onset_in_5d` is a 5-day rolling-max, turning 357 point events into 1,783 rows), and ~1,130 non-survivors are discarded before saving, so no honest family FDR is recoverable from the artifacts — promote none.
- **PIT / leakage red-team (Opus):** entry timing is clean (genuine `close[t+1]` entry, `ENTRY_LAG=1`; the onset event itself is causally detected and knowable that evening — consistent with the house already granting `entry_onset_21d` DISPLAY-WITH-EDGE). Two leaks: the `peak_accel_z ≥ 1.5` filter is a full-episode maximum realized ~29 days after entry (`engine/oracle/episodes.py:377-379`) = look-ahead; and the whole onset population is **survivorship-filtered** — the catalog only holds onsets that later confirmed / met minimum duration (`episodes.py` catalog-append filter), so the measured means are an upper bound vs a live first-crossing signal (quantified in §7). Macro conditioners (HY-OAS/dollar) carry FRED publication lag but the +1-session entry buffer covers it — not a leak. The full-sample inverse-partner map contaminates the `inverse_*`, `schedule_score`, and `fade_risk_score` fields.
- **Redundancy / integration-fit review (Opus)** + **live-registry recon (this adjudication):** see §3–§5.

## 3. Per-pattern disposition

### 3.1 `episode_onset_in` — REJECT-REDUNDANT (it is already ours)
Keys off the SAME episode-onset events as the Oracle's `entry_onset_21d` — the sole FDR survivor of 109 P3 trials (n=356 here vs n=355 there, same 11-ETF universe). The only deltas are a 10-day horizon (vs the pre-declared 21d verdict ruler) and an equal-weight-XL ruler (vs the panel/SPY-relative ruler); neither changes the science, and the Codex 21d number (0.44%) agrees in magnitude with P3's +0.62%. This is external **replication** of a known edge, not a discovery. Value: it independently corroborates `entry_onset_21d` and surfaces two new caveats on it (§6, §7).

### 3.2 `episode_onset_in_peak_ge_1_5` — INVALID (look-ahead + already-null)
Three independent kills: (a) `peak_accel_z` is a full-episode max known only ~29 d after the onset entry — direct look-ahead (`episodes.py:377-379`). (b) The filter passes **96.1%** of onsets (343/357), so it is a near-no-op relabel of plain `episode_onset_in`, not an independent pattern. (c) Onset-day acceleration quality was already tested properly by the shipped Turn-Asymmetry **W1 Onset-Quality Discriminator** (16 PIT onset-day features incl. `accel_z`/`accel_z_5d`, LOEO over 4 eras + 200-perm null) and **printed NULL** under both the pos63 and reversion rulers (AUC 0.489 / 0.484, null p 0.68 / 0.715 — "no onset_quality score ships"). The Codex t=3.378 is exactly the uncorrected in-sample univariate split that protocol was built to, and did, falsify.

### 3.3 `onset_in_plus_same_complex` — REJECT-REDUNDANT (already screened dead on the canonical map)
This was the one cell the redundancy reviewer flagged as *arguably new* — but the reviewer read a 119-commit-stale worktree. On the **current registry**, the same-complex IN-onset construction already exists as a screened family, built on the CANONICAL `rotation_groups` complex map via the grammar's native `episode_event{direction:in, complex_scope:"same"}` primitive (`engine/oracle/compounds.py:400-408`), and it is dead at the Oracle's rulers:

| spec (canonical map) | construction | n | eff21d | eff63d | hit63 | era 3/4 |
|---|---|---:|---:|---:|---:|:--:|
| `A18_SAME_IN_FRESH_RS_GATE` | same-cx in-onset ≤20 + rs≥0 | 1468 | −0.09% | −0.13% | 50.5% | 2 |
| `A19_SAME_IN_FAST_RELAY` | same-cx in-onset ≤10 + vel_1w↑ | 214 | +0.30% | −0.54% | 49.1% | 2 |
| `A24_SAME_IN_LOW_VOL_ROUTE` | same-cx in-onset ×2 + vix<0.85 | 406 | +0.26% | −1.65% | 34.5% | 4 |
| `A5_SAME_IN_BREADTH_REPAIR` | same-cx in-onset + breadth↑ | 76 | −0.27% | −0.69% | 49.3% | 1 |
| `A27_CONF_SAME_IN_PERSIST` | same-cx confirmed-in + persist | 3909 | −0.15% | −0.27% | 47.7% | 2 |

None crosses the promotion floor (|eff63| ≥ 1% or hit63 ≥ 55%, n ≥ 100, ≥3/4 eras). The best 21d effect is +0.30% and every construction decays to negative by 63d — the identical decay the Codex table itself shows (0.59% → 0.46% → pooled 0.15% / t=0.67). Codex's version additionally (a) uses a NON-canonical hand-coded growth/cyclical/defensive map (wrong for XLK→ai_compute, XLY→short_duration_value, XLC→software) and (b) reports only the short-horizon, high-momentum-tail slice (n=186). Registering it would duplicate an already-counted, already-dead trial family and misrepresent novelty — so no spec is registered (§5). Separately, "same-complex momentum > 0" as a *state* gate is the participation-state-gating shape the program already declared a dead basin across families; re-testing it would also require a new panel feature (reviewed change) to probe a known-dead shape — not warranted.

### 3.4 The 4 WATCH, the quadrant/RRG features, and the shadow artifact
- **WATCH:** `episode_onset_out` is our existing `exit_onset_5d` (display_with_edge; NULL at 21d in P3); `cyclical_onset_hy_tightening` is n=72 (sub-floor) Family-D macro conditioning; `direct_us_sector_mom_pos` and `mom_cross_down_right` fail even the Codex gate. Nothing to integrate.
- **Quadrant/RRG state** (`q_age`, `mature_leading`, `right_rollover`, `fresh_improving`): all economically dead (rank-IC negative; `fade_risk_score` t≈−2.2) and already displayed on `subsector_rotation.html`. No new value.
- **`sector_rotation_schedule.v1`: DO NOT BUILD.** It substantially duplicates the shipped **Turn Desk** (#1541), which already surfaces onset + flow-displacement + destination-routing + stale-leadership on the canonical map behind the constitution's watermark/error-rate discipline. Two of its scores are contaminated (full-sample inverse-partner map) and `fade_risk_score` has negative rank-IC. The only genuinely-absent fields are the macro conditioners, which — if wanted — fold into the existing Turn Desk / `oracle_state.json` as Family-D conditioning columns, not a parallel uncalibrated surface.
- **Mined scan (26 long + 6 short "robust"):** selection-post-mining + n-inflated + no recoverable family FDR. Idea-generators only; promote none.

## 4. Search-width ledger (for Harvey–Liu–Zhu accounting)
For the record, so any future promotion carries the correct multiple-testing penalty: this run tested **31 curated rules + ≈1,210 mined boolean combinations** (2 intents × 5 anchors × ~121 filter-combos each, n≥60 gate), reusing the KEEP gate as the "robust" filter. None of it was pre-registered. Nothing here counts as an independent discovery against the Oracle trial ledger.

## 5. Why no compound is registered
The constitution's firewall permits external contributors to submit SPECS (Tier-1), and a Fable-adjudicated intake is legal. But the evidence says registering would be wrong, not merely optional: the only candidate-new cell (§3.3) is already present in `registry.jsonl` as the A5/A18/A19/A24/A27 same-in family, already screened, already in `trial_ledger.jsonl`, and dead at 21d/63d. Adding a duplicate would inflate the counted-trial ledger and launder novelty. **Disposition: REJECT-REDUNDANT across all three KEEPs; no registry write.**

## 6. Boomerang caveat #1 — the 2009–2016 dead regime on our own onset edge (CONFIRMED on our tape)
Per-era HAC-t on `episode_onset_in` (= our `entry_onset_21d` population), recomputed against our committed tape at both horizons:

| era | n | mean 10d | t 10d | mean 21d | t 21d |
|---|---:|---:|---:|---:|---:|
| 1999–2008 | 113 | +0.77% | 4.37 | +0.79% | 4.76 |
| **2009–2016** | 95 | **+0.19%** | **0.95** | **+0.16%** | **0.43** |
| 2017–2026 | 148 | +0.58% | 2.94 | +0.34% | 1.05 |

The 8-year middle is statistically dead at both horizons; the recent era is alive at 10d but fades to noise by 21d. The catalog's `split_min_mean` gate splits at the ~2013 median, so the strong early and recovering-recent halves each look strong and the dead middle never surfaces. This is a property of `entry_onset_21d` itself and should be disclosed wherever that key displays.

## 7. Boomerang caveat #2 — catalog survivorship on the onset population
The Oracle episode catalog only holds onsets that later confirmed / met a minimum duration, so a backtest entering at catalog-onset+1 measures an upper bound versus a live first-crossing detector that must also eat the onsets that fizzle. Re-measurement (`scripts/research/rotation_onset_firstcrossing_remeasure.py` → `reports/artifacts/rotation_onset_firstcrossing_remeasure.json`):

| universe | n | mean 10d | t 10d | mean 21d | t 21d |
|---|---:|---:|---:|---:|---:|
| catalog onsets (baseline, reproduced) | 356 | +0.53% | 4.39\* | +0.44% | 2.17 |
| first-crossing universe (proxy) | 1235 | −0.05% | −0.63 | −0.03% | −0.26 |
| died-young subset (never confirmed) | 1126 | −0.10% | −1.30 | −0.10% | −0.82 |

\* Catalog n and mean reproduce Codex exactly; the HAC-t differs (4.39 vs 3.47) only by Bartlett-kernel lag choice — both significant. Inflation catalog−proxy = **+0.58 pp (10d) / +0.47 pp (21d)**, an n-ratio of 3.47×, with a **sign flip**.

**Honesty caveats — do NOT read −0.58 pp as a clean point estimate:**
1. **Proxy, not the true FSM.** The raw `accel_z` panel (`engine/oracle/panel.py`) is not in the committed Time Machine tape (only tile `rs_ratio`/`rs_mom`), so the first-crossing predicate is a tile-based proxy that fires at a *stricter* threshold and reproduces only 37% of catalog onsets. The true FSM first-crossing set is larger and its edge is unknown without rebuilding the raw panel (`scripts/build_oracle_panel --tier s`; `data/oracle/*.parquet` is R2/gitignored).
2. **cond_a confound.** Because the proxy selects the highest-acceleration crossings, its universe overlaps the population `cond_a` already found significantly NEGATIVE ("entry after acceleration is late = bad"). So part of the proxy's negative return is cond_a, not pure survivorship. A clean study must use the true onset predicate, not a high-accel proxy.

**Bottom line:** the direction — catalog onset stats are inflated by the confirmation filter, and a naive real-time first-crossing signal carries little-to-no edge — is corroborated and plausibly material, but the magnitude is proxy-bounded. This does **not** downgrade `entry_onset_21d`, which trades the confirmed-onset population and already ships with printed detection error rates (constitution §IV); it quantifies why those error rates matter — the edge must be consumed *with* them, never as a clean +0.53%. A definitive first-crossing study on the rebuilt raw panel is the queued follow-up.

## 8. Bottom line
The Codex run is honest, reproducible, and useful — but as *external replication + red-team fuel*, not as new alpha. All three KEEPs resolve to REJECT-REDUNDANT (×2) / INVALID (×1); the shadow artifact is DO-NOT-BUILD (duplicates the Turn Desk); the mined scan is idea-generation only. Nothing is wired, nothing is registered. The durable yield is two disclosed caveats on our own `entry_onset_21d` edge (2009–2016 dead regime; catalog-survivorship inflation) plus a queued first-crossing study on the rebuilt panel.

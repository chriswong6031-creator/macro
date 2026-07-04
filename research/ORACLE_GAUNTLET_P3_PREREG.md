# Oracle P3 Gauntlet — Pre-Registration

**Status: REGISTERED before any result was computed.** Authored by Fable 2026-07-04, committed and merged prior to the first execution of the harness. No effect size from the episode catalog had been observed by the author at registration time — the only catalog queries run before this document were structural (column names, maturity counts, n by direction; transcript-verifiable). The P2 detection thresholds (`EPISODE_CFG`, `CONFIG`) were frozen at #1218/#1217 merge from *distribution quantiles* of the panel (weakly data-dependent, outcome-blind) and are **not tuned further anywhere in P3** — any re-tuning voids this registration and requires a new one.

**What P3 decides.** Which Oracle claims graduate from display-grade to *validated* (eligible to drive alerts/sizing per the masterplan's promotion contracts), and which ship display-only with their nulls printed. House law: a null result ships on the page; it is a legitimate outcome.

---

## 1. Data and samples

| Sample | Source | Role |
|---|---|---|
| **PRIMARY** | `data/oracle/episodes_s.parquet` (749 episodes: 357 IN / 392 OUT; ~740 matured per tier/horizon; 1999-08 → 2026-06; survivorship-clean ETF nodes) | All primary endpoints |
| CONFIRMATORY | `episodes_m.parquet` (5,653 episodes, 506 two-sided; 2021-07→; survivorship-watermarked) | Direction-consistency check only; NO headline claim may rest on Tier M |
| Routing | `graph_{s,m}.json` routing matrices | H4 |
| Panel | `panel_s.parquet` / `panel_m.parquet` | placebo sampling, benchmarks |

Outcome variable: `outcome_rs_{h}d[{_tier}]` — the node's forward RS change measured from each detection-tier date, h ∈ {5, 21, 63}, already stored look-ahead-safe (immature ⇒ NaN, excluded). Signed convention for aggregation: for OUT episodes the *hypothesized* direction is negative forward RS; report raw means AND direction-adjusted means (× −1 for OUT) so "edge" is always positive-is-good.

## 2. Hypotheses and endpoints

**PRIMARY endpoints (2 — these carry the headline):**
- **P-EXIT** — Tier-S OUT episodes, **confirmed** tier, **+21d**: mean direction-adjusted forward RS > 0 (i.e., rolled-over nodes keep underperforming), significant per the gates in §3.
- **P-ENTRY** — Tier-S IN episodes, **confirmed** tier, **+21d**: same, for incoming nodes.

Registered expectation (falsifiable): P-EXIT passes; P-ENTRY is weaker and may fail — per the repo's momentum nulls and the SELL-side asymmetry in `sector_signals` (−1.24%/40% vs BUY +1.10%/56%).

**SECONDARY endpoints (FDR-corrected together with primaries; all Tier S unless noted):**
- S1: the 5d/63d horizons and onset/undeniable tiers of P-EXIT/P-ENTRY (grid: 2 directions × 3 tiers × 3 horizons = 18 cells incl. primaries).
- S2: **two-sided premium** (Tier M only): direction-adjusted +21d outcome of two-sided episodes vs non-two-sided episodes matched by direction. n=506 vs ~5,100. Watermarked; can never graduate past display on its own.
- S3: **early-tier price of front-running**: onset→confirmed conversion rate; fraction of onset-tier episodes whose direction-adjusted +10d outcome is negative (the false-start rate); detection-lag distribution (sessions from first accel_z>0 crossing of the episode's run to each tier date). Descriptive — no pass/fail, published as measured error rates.
- S4: **routing cells** (H4): every cell of `routing` in graph_s and graph_m (source × dest × regime × 3 horizons). Each cell's hit_rate tested against the placebo routing distribution (§3.G5, applied to routing onsets). Registered trial count: all cells with `sufficient=true`, enumerated by the harness at runtime and written into the trial ledger BEFORE p-values are computed.
- S5: **era consistency** (gates, not endpoints): eras 1999–2014 / 2015–2019 / 2020–2022 / 2023–2026.

**BENCHMARKS (comparisons, not new trials):**
- B1 (momentum null): on each episode's detection date, the same direction-adjusted forward RS computed for the top/bottom-decile trailing-1M-RS nodes (bottom decile for OUT, top for IN). The episode edge must EXCEED the rank-extreme edge to claim the state machine adds information beyond plain RS ranking (known sector momentum rank-IC ≈ +0.0078, t=0.36).
- B2 (existing validated map): Tier-S undeniable-tier OUT @63d compared against `sector_signals` SELL (−1.24%, hit 40%, n=169). If Oracle's exit signal is not comparable-or-better, the boring baseline wins and that verdict ships (§4.2 of fable doctrine: the boring solution winning IS a finding).

## 3. Gates (ALL must pass for a primary endpoint to be declared VALIDATED)

- **G1 — Placebo dominance.** For each endpoint: 200 placebo draws; each draw samples, per node, the same number of pseudo-onset dates as real episodes (uniform over that node's panel dates, excluding dates inside ±10 sessions of any real same-direction episode span), computes the same direction-adjusted mean. PASS = real mean > 95th percentile of the placebo distribution (one-sided).
- **G2 — Block-bootstrap CI.** 2,000 iterations, 21-day blocks over episodes ordered by detection date; 95% CI of the direction-adjusted mean must exclude zero. (Methodology inherited from DEFENSIVE_ROTATION.md.)
- **G3 — Regime-stratification survival.** Within-stratum direction-adjusted means recomputed for: VIX pctile above/below 0.6, and SPY above/below 200dma at detection. PASS = the pooled edge does not collapse: at least the larger stratum retains a positive direction-adjusted mean AND no stratum reverses sign with |mean| > half the pooled edge. (Kills "it's just a VIX/trend proxy.")
- **G4 — Era consistency.** Direction-adjusted mean positive in ≥3 of 4 eras (S5), including 2023–2026 (the AI era — the operator's own caution that "cycles may differ").
- **G5 — BH-FDR.** All registered trials (18 episode cells + S2 + all sufficient routing cells) enter one Benjamini-Hochberg correction at q=0.10. p-values: one-sided bootstrap p from G2's distribution. An endpoint "passes FDR" iff its q-adjusted rejection holds.
- **G6 — Benchmark exceedance** (primaries only): beats B1 point estimate; for exit additionally the B2 comparison is reported (informative, not blocking — different universe granularities).

**Verdict vocabulary (pre-bound):** VALIDATED (all gates) / DISPLAY-WITH-EDGE (G1+G2 pass but any of G3–G6 fail — printed with caveats) / NULL (G1 or G2 fail — printed as null). No third category may be invented post hoc.

## 4. What is explicitly OUT of scope for P3
- Any re-tuning of detection thresholds (voids registration).
- Any Tier-M-only headline claim (watermark law).
- Position sizing, alert wiring, banner thresholds (P5 consumes P3 verdicts; nothing here ships to a user surface).
- The kNN analogue layer (P4; will be validated under its own registration).

## 5. Execution and roles
- **Harness** (`scripts/oracle_gauntlet_p3.py`): built by a Sonnet agent to this spec verbatim; hermetic tests for the placebo sampler (excludes real-episode spans; per-node counts match), bootstrap (reproduces a known synthetic CI), FDR (matches a hand-computed BH example), and the direction-adjustment sign. Runs on the real parquets via `--data-dir`; writes `data/oracle/gauntlet/p3_results.json` + a trial ledger (every cell enumerated with its p-value) + `research/ORACLE_GAUNTLET_P3_RESULTS.md` (tables only).
- **Independent cross-check** (Haiku): recomputes 6 specified cells (P-EXIT/P-ENTRY at 21d + onset-tier variants + n's) directly from the parquet with plain pandas; numbers must match the harness to 1e-9.
- **Adversarial audit** (Opus): verifies harness-vs-registration fidelity (placebo construction, era boundaries, trial-ledger completeness, no threshold drift, look-ahead in benchmark construction), and that a deliberately corrupted placebo (seeded inside episode spans) FAILS the sampler test.
- **Adjudication** (Fable): applies §3 verdicts mechanically; writes the verdict section; updates masterplan + memory. No verdict discretion beyond the pre-bound vocabulary.
- Seed: 20260704. All randomness seeded; reruns byte-identical.

## 6. Registered trial ledger (ex-ante shape)
18 episode cells (2 dir × 3 tiers × 3 horizons) + 1 two-sided premium + N_routing sufficient cells (enumerated at runtime before p-computation; expected order ~100–300). Expected FDR reality, stated in advance: at q=0.10 with ~300 trials and Tier-M routing n≈10–22, **routing cells are expected to fail FDR en masse** — they remain display-grade candidates accruing n on the Ledger tier. That outcome would be correct behavior, not failure.

---
*Registration locked at merge. Results doc must link back here; any deviation between harness and this text is an audit finding, not an interpretation choice.*

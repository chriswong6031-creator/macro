# US Buy Board — Measurement (§W6-US, Agent US-2)

*The empirical answer to "does the board actually work?" and the knob recommendations for the Buy Board 2.0 redesign (US-3). Two independent evidence sources converge: (1) **git-archaeology retro-grading** of the shipped `us_standouts.json` board reconstructed from 90 daily revisions, and (2) three **panel studies** (MAE, precision@k, dispersion) on the residual-alpha / timing legs. Everything here is TINY-n and honestly bounded — read the caveats before quoting any number.*

**Artifacts produced:**
- `scripts/grade_us_board.py` — git-archaeology retro-grader + forward-accruing ledger (wired into `daily.yml --nightly`).
- `scripts/us_board_studies.py` — the three deciding studies.
- `data/us_board_ledger/retro_grades.parquet` — one row per (as_of, lane, ticker, horizon); the graded ledger.
- `data/us_board_ledger/snapshots.jsonl` — append-only forward snapshot (accrues nightly).
- `data/us_board_ledger/studies.json` — MAE / precision@k / dispersion outputs.
- `site/factordata/us_board_track.json` — aggregated track record (per-lane/band/verdict/tier/dispersion hit-rate + Wilson CI, precision@k board-order vs alpha-order counterfactual).

---

## 0. The honesty frame (mandatory context for every number below)

- **TINY n.** Prices in this worktree end **2026-06-30**. Only boards with `as_of` ≤ 2026-06-22 have matured to the 5-day horizon; **nothing has matured to 10d or 21d.** The retro track record is **5 distinct board-dates (2026-06-15..06-22), 437 buy-lane name-observations at 5d.** That is roughly *one week* of independent information.
- **THE MATURED BOARDS ARE THE OLD REGIME.** Those 5 matured boards were `rank_by="conviction"` (the 120-row board). The **current live `bottoming-alignment` 34-row board only began ~2026-06-24 and has NOT matured to even 5d.** So the retro grade measures the *predecessor* ranking, not the live one. This is stated everywhere; do not read the retro numbers as a verdict on the live board's ordering — read them as a verdict on **conviction/composite_z ordering**, which the live board still uses as a tiebreak.
- **THE LIVE RANK KEY WAS NEVER VALIDATED.** `bottoming-alignment` (`engine.cycles.mtf_alignment`) was fed to **no** harness — not the deep phase0 run, not this one. Study 2 uses short-term reversal as the closest harness-testable proxy and flags the gap. **Grading the true live key end-to-end remains the honest first step** (audit open question A1).
- **OVERLAPPING WINDOWS.** Daily boards × multi-day horizons → heavy serial correlation. The effective independent-sample count is a fraction of n. **Wilson CIs are computed on raw n and are therefore optimistically narrow** — treat them as a *lower bound* on uncertainty.
- **SURVIVORSHIP.** The panel studies run on the `broad` cache (current S&P-1500 membership; delisted names invisible). This inflates hit-rates, especially for reversal/laggard cohorts. The deep survivorship-clean panel + PIT membership are local-only artifacts absent from the repo (dropped in `031900e7`), so Study 2/3 are **UNPOWERED and survivor-biased — directional shape, never a GO.** The powered anchor is the committed `reports/stock-conviction-phase0.md`.
- **STRONG-TAPE CONFOUND.** The 5 matured boards all sit inside a rising SPY tape into 06-30. Absolute hit-rates (65.7% vs SPY) are inflated by that; the *ranking* findings (top-of-board vs board-average) are tape-robust because both legs share it.

---

## 1. Retro track record (git archaeology) — the immediate answer

Reconstructed every board from `git log`/`git show` of `site/factordata/us_standouts.json`, tolerant to schema drift (fields moved/nested across 90 revisions; earliest boards had a 120-row buy lane, no `watch`/`entry_signal`/`signal` fields). Entry = **next session's close** after `as_of` (next-bar realism). Returns are dividend-adjusted total return; excess subtracts the benchmark on the same basis.

### Buy-lane, 5d horizon (n = 437 name-obs across 5 board-dates; rank_by = conviction)

| Metric | vs SPY | vs sector ETF |
|---|---|---|
| Hit rate (P[excess > 0]) | **0.657** (Wilson [0.611, 0.700]) | 0.579 ([0.532, 0.624]) |
| Median excess | +2.59% | +0.94% |
| Mean excess | +2.11% | +0.81% |
| Median close-path MAE (excess vs SPY) | **−0.47%** | — |

Base-rate context: with a rising tape, most names beat nothing — the *sector-relative* 57.9% is the honest read of stock selection, and it's barely above a coin flip.

### The ranking is inverted at the top — the load-bearing finding

| Ranking of the *same* 5 boards | P@1 | P@3 | P@5 | P@10 |
|---|---|---|---|---|
| **As published (conviction / board order)** | **0.20** | 0.40 | 0.52 | 0.58 |
| Counterfactual: re-ordered by residual alpha | **0.60** | 0.667 | 0.60 | 0.64 |

- `corr(board_position, excess_5d) = +0.071` — **higher board slots did slightly WORSE.** (Position ascending = higher rank; positive corr = rank anti-predictive.) This mirrors the audit's live `corr(board_position, alpha) = +0.266`.
- **P(fwd > 0 | top-5) = 0.52 vs base rate 0.657 → lift = −13.7 points.** The names the board pushed to the top *underperformed the board average.*
- Board-order P@k ≡ composite_z-order P@k (these boards literally ranked by conviction), so **conviction/composite_z ordering is the broken one**; alpha ordering fixes the top.

**Retro verdict:** on the matured (conviction-ranked) boards, the board *as a screen* was fine in a strong tape (65.7% beat SPY) but the *ranking was actively harmful at the top* — the No.1–5 slots underperformed both the board average and an alpha re-ordering of the identical names. This is direct, if tiny-n, support for "demote conviction/composite_z as the sort; the top slots must be earned by the positive-IC leg."

### Dispersion slice (buy lane, 5d) — a caution, not a signal
`lean_in` 60.2% (n=83), `neutral` 46.1% (n=89), `None`/early-schema 74.0% (n=265). The `neutral` regime actually had the *worst* buy-lane hit-rate here — but with 2 dispersion states populated across 5 correlated board-days this is noise, not a modulator. See Study 3 for the panel read.

---

## 2. Study 1 — MAE: is timing a legitimate risk-placement layer? (contrarian #1)

The analysis's biggest blind spot: nobody had measured whether bottoming-alignment entries place *shallower drawdowns* than alpha-ranked entries, even at ~0 return edge. Panel = 24 monthly rebalances (2024-06..2026-05), UNPOWERED/survivor-biased. Top-decile cohorts; timing = short-term-reversal proxy (the live key was never harness-testable — see §0).

| Horizon | Cohort | Median MAE (excess) | Mean MAE | p5 MAE (deep tail) | Median excess | Hit rate |
|---|---|---|---|---|---|---|
| 5d | alpha-ranked | −2.22% | −3.80% | −12.79% | −0.03% | 0.497 |
| 5d | timing-gated | **−1.95%** | −3.42% | −12.16% | −0.28% | 0.480 |
| 10d | alpha-ranked | −3.76% | −5.49% | −17.85% | +0.79% | 0.536 |
| 10d | timing-gated | −3.68% | −5.29% | −17.22% | −0.60% | 0.467 |
| 21d | alpha-ranked | −5.91% | −7.88% | −23.20% | +0.31% | 0.507 |
| 21d | timing-gated | −5.92% | −7.71% | −21.81% | −0.74% | 0.470 |

**Verdict: the "timing = shallower drawdowns" claim is NOT supported here.** The timing cohort's median MAE is within rounding of the alpha cohort's (−1.95% vs −2.22% at 5d; −5.92% vs −5.91% at 21d — the benefit vanishes by 21d), and it comes with a **consistent, larger return AND hit-rate cost** (timing median excess negative at every horizon; hit-rate 47–48% vs 51–54%). The only place timing looks marginally protective is the **deep tail (p5 MAE) at short horizons** (−12.2% vs −12.8% at 5d) — a real but small, noisy, decaying effect.

Design implication: **do not gate heavily on timing for drawdown reduction.** The redesign's timing gate should be justified by *entry-quality / not-chasing* (the confluence contract), not by a drawdown benefit this panel can't find. Order by edge; use timing as a light admission gate + badge, not a risk-placement engine you lean on.

---

## 3. Study 2 — precision@k for candidate rank keys (their Q3)

Rank-IC is the wrong yardstick for a discrete BUY classifier; measure P(fwd>0 | top-k) and top-k mean excess. Same 24-rebalance panel.

| Key | Horizon | Mean rank-IC | P@1 | P@5 | P@10 | Mean excess @1 |
|---|---|---|---|---|---|---|
| **residual alpha** | 5d | +0.009 | 0.458 | 0.483 | 0.496 | +2.57% |
| residual alpha | 10d | +0.044 | 0.458 | 0.500 | 0.533 | +3.23% |
| **residual alpha** | 21d | +0.027 | 0.435 | 0.444 | 0.500 | **+8.33%** |
| timing proxy (bottoming) | 5d | **−0.025** | 0.417 | 0.492 | — | −2.38% |
| timing proxy | 10d | −0.024 | 0.500 | 0.533 | — | −0.70% |
| timing proxy | 21d | −0.003 | 0.348 | 0.444 | — | −3.21% |
| composite (alpha+timing) | 5d | −0.004 | 0.417 | 0.492 | 0.488 | +0.50% |
| composite | 10d | +0.015 | 0.458 | 0.508 | 0.533 | +2.59% |
| **composite** | 21d | +0.013 | **0.522** | 0.478 | 0.500 | +4.50% |

Readings:
- **Residual alpha is the only positive-IC key at every horizon, and its edge is TAIL-CONCENTRATED in magnitude**: top-1 mean excess **+8.3% at 21d** while its hit-rate P@1 is only ~0.44. This is exactly the tail-concentration the audit's Q3 hypothesized — a rank-IC ~0 can still carry a fat top bucket. **Order by alpha and the top names win big when they win**, even if they don't win more often.
- **The timing/bottoming proxy is net-negative**: negative IC and negative top-1 mean excess at every horizon. This matches the deep phase0 panel's `entry axis (reversal proxy)` (negative IC at 21d/63d/126d). **Timing must never sort the board.**
- **The alpha+timing composite gives the best top-1 HIT-RATE at 21d (0.522)** — blending lifts the *frequency* of a top-1 win even though timing alone hurts. If the product wants a legible hero pick that's right more often than not, a light edge+timing blend at the very top beats pure alpha on hit-rate (while pure alpha beats it on magnitude). This is a genuine two-axis tradeoff for US-3 to choose between (legibility vs slugging).

---

## 4. Study 3 — dispersion-bucket conditioning (their D2, validate-first)

Does the dispersion regime actually modulate selection payoff *on our legs*? Conditioned residual-alpha rank-IC / P@5 on cross-sectional dispersion terciles (63d cross-sec return std). ~8 rebalances/bucket.

| Bucket | alpha IC h5 | alpha IC h10 | alpha IC h21 | alpha P@5 (h5) |
|---|---|---|---|---|
| low dispersion | **−0.058** | −0.024 | −0.010 | 0.425 |
| mid dispersion | +0.063 | +0.090 | +0.087 | 0.600 |
| high dispersion | +0.021 | +0.065 | +0.002 | 0.425 |

**Direction is suggestive and roughly monotone in the right way**: alpha selection is *negative* in the lowest-dispersion tercile and *positive* in mid/high — consistent with the literature prior (selection pays when cross-sectional dispersion is higher). The IC spread across buckets at h21 is ~0.096. **But 8 correlated rebalances per bucket forbids any claim.** Per the passport rule (W6 dispersion dial: "measure-or-demote"), this stays **display-only** — it is NOT yet a validated modulator of the edge floor. The China falsification (subsector-state gates *hurt* A-share reversal) is the standing caution against hard-gating on a regime state before the ledger proves it.

---

## 5. Knob-recommendation table for US-3

Confidence legend: **A** = both retro ledger and panel agree + directionally matches the powered deep anchor; **B** = one source, tiny-n, directional; **C** = suggestive only, keep display-only.

| Knob (Buy Board 2.0) | Recommendation | Evidence | Conf |
|---|---|---|---|
| **Primary sort key** | Order by **residual alpha** (or an alpha+timing blend at the very top). NEVER by `bottoming-alignment` / `composite_z` / `potential_score`. | Retro: board-order P@1 0.20 vs alpha-order 0.60; `corr(position,excess)=+0.07`; P(fwd>0\|top5) −13.7pts vs base. Panel: alpha only positive-IC key (top-1 excess +8.3%@21d); timing IC negative at all h. | **A** |
| **Edge floor (WHAT-gate)** | Gate inclusion on **`composite_z > 0` (or residual-alpha percentile > ~50th)**. Keep it a *floor*, not a fine ranker — the edge can't rank-order 34 names, but it can exclude the negative-alpha half. | Panel: alpha edge is real but tail-concentrated; below-median alpha adds noise. Retro: 15/34 live buys had negative alpha (audit) — those are the dilution. | **B** |
| **Timing gate (WHEN-gate)** | Keep the validated **MACD-2D×StochRSI-3D confluence as a hard admission gate + freshness badge**. Justify it as *entry-quality / not-chasing*, **NOT** as a drawdown-reduction engine. Timing sets eligibility + the badge; it never sorts. | Study 1: timing cohort MAE ≈ alpha cohort (benefit within noise, gone by 21d) at a real return + hit-rate cost. Study 2: timing IC negative. | **A** |
| **Freshness window** | Keep it *short* (a few bars) as an eligibility condition; do **not** widen it to fill slots. No evidence a wider window helps; the point is "fresh cross, not chasing." | Panel can't price the exact window (proxy); default to the tight confluence-fresh definition already in `setups.json`. Flag for the W6 stop-out harness to calibrate `FRESH_TICKS`. | **C** |
| **Does timing show a MAE benefit?** | **No — not one worth leaning on.** Marginal deep-tail shallowness at 5d only; equal by 21d; return cost dominates. Do not add a "timing reduces drawdown" claim to the UI. | Study 1 table §2. | **A** |
| **Should dispersion modulate the edge floor?** | **Not yet — display-only.** Direction is right (alpha IC negative in low-dispersion, positive in mid/high) but n forbids gating. Surface the regime; do NOT let it move the floor or the count until the ledger matures. | Study 3; passport rule; China gate falsification. | **C** |
| **precision@k by key (what to trust at the top)** | Pure **alpha** for top-slot *magnitude* (top-1 excess +8.3%@21d); **alpha+timing blend** for top-1 *hit-rate* (0.522@21d). Pick by product intent: slugging vs being-right-more-often. Either way, **not conviction/composite_z** (P@1 0.20 retro). | Study 2 §3; retro §1. | **A** (alpha beats conviction) / **B** (blend-vs-pure choice) |
| **Board width / variable N** | Support the plan's **variable-width, two-lane** design. The edge can't justify a fixed 34; an empty ENTRY-OPEN lane is honest. Kill `ALIGN_MIN_KEEP` backfill + `entry_open_first`. | Root-cause synthesis + retro (top slots are the worst) + panel (edge is thin/tail-concentrated). | **A** |
| **Hero / No.1 slot** | If a No.1 exists, it must be the **top alpha (or blend) name above the edge floor with a fresh confluence cross** — never `entry_open_first`'s sparse `buy_now` flag. | Retro: board-order P@1 0.20 (worst); the current #1 selector is edge-blind. | **A** |
| **Track-record surface** | Ship the **live `us_board_track.json` hit-rate + Wilson CI per lane/band on the header** once it matures. Frame the honest ~coin-flip sector-relative number as a feature (kills false confidence). Ledger accrues from tonight via `--nightly`. | §1; the ledger is now wired and accruing. | **A** |

**One-line steer for US-3:** *Order by edge, gate by timing, never the reverse — and let width float.* The retro board's top slots underperformed its own average because it sorted by the wrong quantity; the panel confirms alpha is the only positive-IC leg (tail-concentrated) and timing is net-negative to sort by. Timing earns its place as a not-chasing admission gate, not as a drawdown story or a ranker.

---

## 6. Nightly accrual wiring

`scripts/grade_us_board.py --nightly`:
1. Snapshots today's committed `us_standouts.json` into `data/us_board_ledger/snapshots.jsonl` (append-only, idempotent per `as_of`) — so the ledger survives even if git blobs are pruned.
2. Unions git-history boards + snapshots (de-duped on `as_of`), grades everything matured, rewrites `retro_grades.parquet` + `us_board_track.json`.

Registered in `.github/workflows/daily.yml` as **"US Buy Board ledger"**, placed in the deterministic-scorer cluster (context-only, `|| true`, before the `commit engine outputs` step that does `git add data/ site/`). Standalone cron-able entry point: `python -m scripts.grade_us_board --nightly`.

**What matures when:** 10d slices appear ~2026-07-02, 21d ~2026-07-12 (for the earliest live `bottoming-alignment` boards). Re-run this measurement once the *live-schema* boards mature — only then can the true live key be graded (and the retro P@k finding re-confirmed on the board people actually read).

---

## 7. What was cut / open

- **True live-key grading.** Reconstructing `mtf_alignment`'s full W/3D/D MACD+StochRSI stack across the panel is a multi-session build; Study 2 used a reversal proxy and flags it. This is the single most important follow-up — the ranking recommendation rests on the proxy + the retro conviction-board finding, not on the exact live key.
- **Deep+PIT re-run.** The deep panel is local-only/absent; Studies 2–3 are unpowered/survivor-biased. When the deep panel is restored, re-run `us_board_studies.py` (it auto-detects `powered`).
- **10d/21d retro.** Not yet matured — nothing to grade at those horizons until July.
- **MAE with intraday lows.** Only close-path MAE (understates true drawdown). If intraday lows land in the price layer, upgrade the MAE leg.

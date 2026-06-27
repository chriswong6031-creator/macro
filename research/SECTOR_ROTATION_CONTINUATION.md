# Sector-Rotation Risk-State Web — Continuation Handoff

*For a fresh Opus 4.8 Ultracode session. Read [`SECTOR_ROTATION_NEURAL_WEB.md`](SECTOR_ROTATION_NEURAL_WEB.md) (the full blueprint) first — this is the executable next-steps layer.*

## Where things stand (2026-06-27)

- **SHIPPED + MERGED to main (PR #525):** the Sector Cycle Intelligence page — `site/sector_cycles.html`, engine `engine/sector_cycles.py`, builder `scripts/build_sector_cycles.py`, template/CSS/JS in `templates/sector_cycles.*`. Two independent sections (Sector ETFs / Thematic Baskets), Price⇄Cycle modes with log re-anchoring, BUY/SELL signals, phase-sorted cards, full EN+中文 narratives. 9 engine tests green.
- **Narratives:** `data/sector_cycles/narratives.json` — `sectors{}` (11, keyed `xlk`…) + `baskets{}` (34, keyed `mag7`…). Build merges them into one NARR keyed by chart id (`xlk`, `b-mag7`). All 88 sector legs already carry the **rotation/regime lens** (EN+中文).
- **Rotation substrate (the key new tool):** `scripts/sector_rotation_context.py` → `data/sector_cycles/leg_context.json`. For each leg it measures, from real prices, the cross-sector+macro backdrop (leaders/laggards, defensives-vs-cyclicals, SPHB−SPLV, IWF−IWD, VIX, TLT, DXY, RSP−SPY, oil, copper−gold) and derives rotation SIGNALS (flight-to-safety, defensives-starved, rate/dollar/quad, breadth). **The proven pattern: compute factual context (deterministic) FIRST, then narrate + adversarially verify against the numbers — never let agents guess rotations.**
- **IN FLIGHT (background workflow `wnxzz9hnm`, branch `feat/sector-rotation-followups`):** rewriting the 34 **basket** legs with the same regime lens (EN+中文), self-merging + opening a PR. Verify that PR landed before starting below.
- **Blueprint:** `research/SECTOR_ROTATION_NEURAL_WEB.md` — the honest architecture. Core finding: the edge is **drawdown-control + regime-classification + rotation-timing, NOT front-running alpha / directional pinpointing** (coin-flip everywhere tested). Build to refuse, by construction, what failed the gates.

## The validation gate (apply to EVERY new predictive claim, in lethality order)

0. **GATE-0 — PIT-membership survivorship** (most important; see below).
1. **Incremental-IC-beyond-VIX ≈ 0** — the single most lethal test (killed credit-divergence as "VIX-in-disguise"). Mandatory for every VIX-correlated leg.
2. **2020+ era holdout** — killed risk_state V1, breadth_div, macd_stochrsi.
3. **FWER / maxT / BH-FDR** with a registered trial count (incl. machine-proposed trials).
4. **lead-lag k=0 ⇒ coincident, not leading** — label must name the *quantity* it leads (drawdown / 63d-excess), never bare "direction".
5. **Deflated Sharpe + purged/embargoed CV (CPCV)**, trial-count tracked.
6. **Forward-outcome log + FP budget + a standing WRONG-condition in CI.**
7. **Leak checks** — keep the `3B` resample left-label fix intact (3-day bar at index *i* uses no close dated > *i*); strictly future-dated `check_by`.

Anything that doesn't clear ships **display-only with the null printed on the page** — a legitimate outcome.

## Next steps (each its own Ultracode session; do GATE-0 first)

### GATE-0 — PIT-membership survivorship audit *(do before any tuning)*
- **Why:** every cited "validated" sector-signal number (BUY +0.87%, AVOID −1.34%, washout 73%, liquidity +6.4pp) was computed on **current** membership unless proven otherwise. If the edge halves on historical constituents, all downstream weights re-tune.
- **Data:** `data/stocks/sp1500_pit_membership.parquet` (PIT constituents) + `data/stocks/_closes_cache.parquet`. The 11 sector ETFs themselves are survivorship-clean (real ETF prices) — the concern is the **calibration/backtest universe** that validated the ladder states.
- **Do:** re-derive the `engine/sector_signals.py` BUY/AVOID/SETUP forward hit-rates + 63d-excess on PIT constituents (not current). Compare to the published numbers. Write `research/GATE0_SURVIVORSHIP.md` with the verdict.
- **Validation bar:** if AVOID's all-4-era negativity survives on PIT data → label stays VALIDATED; if it weakens, downgrade the label and re-scope downstream.

### P0 — Flow-router (the validated, safe first build)
- **What:** use the `leg_context` regime label as a **COINCIDENT risk-router** on the sector buy/sell board: a cyclical BUY firing during a *concurrent* flight-to-safety / strong-dollar / risk-off gets down-weighted or routed to **WAIT**. Also **promote AVOID/TOPPING to the loudest primary output** (lead with "what to exit").
- **Where:** the sector buy/sell board is built in `engine/sector_signals.py` + surfaced via `build_site` `sector_setup_view` → `templates/dashboard.html.j2` / `sector.html.j2`. Add the router as an overlay (do NOT fork `engine.cycles`). Reuse the `leg_context` `now_ctx`/signals logic (or call `sector_rotation_context.leg_ctx`).
- **Validation bar:** ships as narrative-fact-check / display while it merely down-weights or routes-to-WAIT. To actually GATE a lane: PIT-spread audit + purged-CV 2020+ showing gated-BUY ≥ hit-rate / ≤ drawdown vs ungated; and the regime state used must be **available at entry** (no end-of-leg look-ahead — the `now_ctx` is a trailing window, fine; a leg's *end* state is not).

### P1 — Regime vector
- **What:** emit `latest.regime_vector = {quad, quad_pref_sectors[], liq_state, liq_tilt_bp(21d-capped), mrs, sector_penalty[], fed_put_state, disagreement_flag}` and regime-condition the L1 sector states (weights/signs flow DOWN only).
- **Engines (already validated, untouched):** `engine/regime.py` (`raw_quad`/`classify`, `liquidity_overlay` — the strongest orthogonal factor, **21d-capped**), `engine/sectors.py::preference_check`, `engine/conditions.py` (MRS × sector_macro_beta, subtract-only), the Fed-put master switch (`research/DISLOCATION_VALIDATION.md`).
- **Also:** `refined_buy` is NOT a sector edge (failed the within-regime permutation test on sector data per `engine/sector_signals.py`) — keep it out of the sector spine.

### Later (P3–P6): de-risk stack (credit-OAS-ROC residualized-vs-VIX + curve + defensive-leadership + vol-proxy; **note MOVE has no ticker — use TLT realized-vol**) → re-risk stack (capitulation→**existing `engine/advanced_breadth.py` thrust**, PIT-backtest it, don't build a collector) → L5 fusion+calibration (orthogonalize-before-counting; effective-breadth; isotonic + Brier/reliability) → Opus layer (out-of-the-key, **de-escalate-only CODE clamp**, blind-adversary κ, three-clocks leakage firewall, **migrate DeepSeek desks → claude-opus-4-8**). See blueprint §4, §6, §7, §8.

## Load-bearing gotchas
- **Confluence fidelity:** any node ingesting the MACD/StochRSI confluence must call the faithful **RSI-based-MACD + stoch-of-RSI** port (`research/signal_engine/confluence.py`), never price `macd_parts`. It's a risk/timing overlay (shallower DD), NOT a return strategy — needs a 200d/weekly trend gate or it catches knives.
- **Orthogonalize before counting:** `IR = IC·√(effective_breadth)` collapses under correlation; print *measured* effective breadth, not green-leg count.
- **Opus is barred from the calibrated key** — context-only, de-escalate-only, trial-taxed.
- **Build/verify:** `python -m scripts.build_sector_cycles`; tests `pytest tests/test_sector_cycles.py`; preview serves the worktree's own `site/` via `.claude/launch.json` (hash-only nav doesn't reload — `location.reload()`).

*Key in-tree refs:* `engine/{cycles,sector_signals,sector_cycles,sectors,regime,conditions,risk_radar,risk_radar_backtest,market_gamma,advanced_breadth,cross_asset,master_brain,desk_scorer,calibration_hub}.py`, `scripts/sector_rotation_context.py`, `data/sector_cycles/{narratives,leg_context}.json`, `research/{SECTOR_ROTATION_NEURAL_WEB,SECTOR_CONFLUENCE,BOTTOM_CONFIDENCE,DISLOCATION_VALIDATION,RISK_ENGINE_V2_FINDINGS,LIQUIDITY_LADDER}.md`.

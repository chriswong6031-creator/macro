# DRL continuation handoff — 2026-08-10 (session 1)

Program: Dislocation & Recovery (`research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md`,
v2 with §12 red-team log). Engine namespace `engine/price_pressure/`; surface = Pressure
Watch band on the stocks hub. This doc is the session-chain state; update, don't duplicate.

## Shipped this session

- Masterplan v1→v2 (census-complete, red-team adjudicated: 4 BLOCKERs + 10 findings folded).
- W1: `engine/price_pressure/` (LSR-imported fence, PIT ledger `data/price_pressure/events.parquet`,
  frozen `base_rates.json`, display `latest.json`, nightly tail-desks step, synapse rows,
  market_packet block, analyst-doctrine scope sentence, tests) — PR #5269.
- Backfill run on the 2021-07-06..2026-07-02 store snapshot (R2-canonical; local caches lag) —
  events/base-rates committed; MU April-2025 printed as measured non-fire (worst z −2.44).
- W2: Pressure Watch band (resolved-first inversion, both sides, recency ordering,
  coverage-honest chips, fail-soft warm-up) — PR #5266 (parity verified against the emitted artifact: day.banner, ret, h21_share_partial, basket_zh all present).

## Next session queue (in order)

1. **Verify the gap-era catch-up did its job**: after the first nightly advance post-merge,
   confirm `data/price_pressure/events.parquet` contains the July-03→Aug sessions with
   `era="gap"`, that CDE's 2026-08 earnings shock appears (family `filing-coverage-unknown`,
   basket framing vs the precious-metals basket), and the band + market-packet block render it.
   Then update masterplan §6 exemplars with the actual readout.
2. **Live verification debt**: (a) after both merges + a covering render, confirm the band renders on /stocks/ (warm state until first nightly, then populated); (b) after the first nightly, confirm gap-era rows + CDE episode + market-packet PRESSURE section; (c) decide events.parquet storage (10.8 MB nightly rewrite ≈ 4 GB/yr git growth) — move to R2 with restore/publish pair in the nightly step, or accept; decide BEFORE many nights accrue.
3. **§8 leg 1 — R4 VIX-gradient prereg**: **DONE 2026-08-10 (session 2, rev 2 after a
   10-blocker red-team pass)** — `research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md`
   (all in-sample looks disclosed incl. the review's own h=21 weak read; R4-A h=5 sole
   gating claim, power-based floors 240 stressed dates/≥8 runs/480 calm ≈ 5.5y clock;
   R4-B descriptive-only forever). Remaining: check floors each session — stressed
   accrues ~44 dates/yr (the percentile arm is common at any vol level, NOT rare).
4. **§8 leg 4 — XBRL transitory-decomposition context** (CDE PPA case): deterministic only,
   `data/edgar/statements.parquet` + `dilution_events.parquet`; context fields, never scores.
5. **§8 legs 2/3/5/6** are clock- or dependency-blocked (revisions ≈2028+, tape via tick-plane
   TP-1+, winners-program linkage, FINRA HOLD lift) — do not start; check clocks each session.

## Standing cautions (bite here specifically)

- The fence, thresholds, horizons, and peer basis are **LSR-pinned; re-tuning any of them is
  DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER territory** — display taxonomy may change,
  the construction may not.
- Base rates are span-bound to the rolling store; a re-freeze silently drops the oldest era —
  stamp and state the span every time.
- `era ∈ {backfill, gap}` rows are NEVER promotion evidence; §7 needs forward-era only,
  ≥200 episodes across ≥40 distinct dates, level-vs-gradient gate split.
- Ordering anywhere user-visible: recency then ticker — never |z|/|resid| (ranking authority).
- The worktree harness creates SPARSE checkouts — `git sparse-checkout add data site tests
  templates` before building/testing, or failures are fake.
- Store freshness: R2 is canonical; every local checkout's `data/massive_stock_day` is a
  stale cache (manifest is tracked and tells the truth; parquets don't).

## Session-2 entry point

Read this doc + masterplan §12 + memory `dislocation-recovery-price-pressure-program`,
then start at queue item 1.

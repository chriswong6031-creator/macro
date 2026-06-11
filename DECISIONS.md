# Engineering decisions log

Newest first. Each entry: what was decided, why, and what would change it.

## 2026-06-10 — initial build

**D1. Dedicated git repo inside the project folder.** The parent home directory
contained a stray commit-less git repo at `~`. Committing data there would be
wrong; `git init` was run in the project folder itself. When publishing,
`git remote add origin <github-url> && git push -u origin main`.

**D2. FRED access: official API when `FRED_API_KEY` is set, keyless
`fredgraph.csv` otherwise.** The keyless endpoint serves identical data but
intermittently 504s (observed during build), hence 4 retries with exponential
backoff. CI should set the key (free at fred.stlouisfed.org/docs/api/api_key.html).

**D3. OAS rolling-window mitigation (confirmed live).** As of build day FRED
returns only ~3 years for `BAMLH0A0HYM2`/`BAMLC0A0CM` (first obs 2023-06-12).
Mitigations: (a) `lib/store.upsert` is append-only — rows existing only on disk
are never dropped, so every live observation is cached permanently from day one;
(b) full 1996→2025 history restored from Wayback Machine captures of FRED's own
endpoints, stored in `data/archive/` with spot-check verification
(see `data/archive/PROVENANCE.md`). IG archive ends 2024-10-24; live FRED window
(2023-06→present) overlaps it, so the merged series has no gap.

**D4. One vectorized engine code path.** The engine recomputes the full daily
history every run (seconds of compute); the live signal is the last row. The
Phase-2e backtest therefore exercises *exactly* the production classifier — no
separate backtest implementation that could drift.

**D5. Slope z-scoring = drift t-stat.** "Direction of change" = mean daily
change of log level (plain level for series already in %) over 20d, divided by
(60d daily-change volatility / √20) — a t-statistic of recent drift. Scored ±1
beyond |z| ≥ 0.25. Chosen over z-scoring the slope against its own trailing
mean because that variant decays to zero during steady trends — a two-year
expansion must keep reading as growth-up. Windows/threshold in `config.yml`.

**D6. ISM is not on FRED anymore (`NAPM` discontinued 2016).** Econ confirmation
uses payrolls 3-month change sign and INDPRO yoy sign at half weight instead.
Monthly series are step-filled forward (~40 trading days max) — honest
representation of "last known print", and only direction is consumed.

**D7. Monthly econ scored by sign, not slope-z.** A 20d slope on a step-filled
monthly series is zero most days and spikes on release days; sign of the 3m/12m
change is the debuggable equivalent. Lower weight (0.5) per spec.

**D8. Breadth constituent close matrix is a local cache, not repo data.**
Committing ~500 price series daily would bloat the repo (parquet doesn't
delta-compress in git). Only the small computed aggregates
(`data/breadth/breadth.parquet`) are committed; the raw close matrix lives in a
gitignored cache restored via `actions/cache` in CI (on miss: ~2 min re-download).
Backtest aggregates computed once from full constituent history (survivorship
bias documented in LIMITATIONS.md).

**D9. Treasury DTS schema change handled explicitly.** TGA value lives in
`close_today_bal` under account type `Federal Reserve Account` before Oct-2021
and in `open_today_bal` under `Treasury General Account (TGA) Closing Balance`
after (verified against the live API at 2007/2015/2021/2026 dates). Net
issuance = Table IIIA Marketable Issues − Redemptions.

**D10. Net liquidity units.** Normalized to $bn: WALCL(mn)/1000 − RRP(bn) −
TGA(mn)/1000. WALCL is weekly (Wed) and forward-filled ≤7 days; the dashboard
flags the staleness rather than hiding it.

**D11. Holdings active-decision SO normalization.** Fund shares outstanding for
the expected-shares formula is proxied by the total share growth of positions
common to both snapshots when the sponsor doesn't publish SO in the same file.
Exact SO is used where available (iShares embeds it; SSGA fund API).

**D12. Hysteresis interpretation.** "Single-day axis score beyond ±0.7" flips
immediately only when that axis *disagrees with the incumbent quad's sign* —
an extreme reading that agrees with the incumbent regime is confirmation, not
a shock.

**D13. Recession/inflation-shock are refinements (labels), not extra states** —
exactly as specced; hysteresis operates on the 4 quads only.

**D14. GEX flag is live-only.** No free historical dealer-gamma series exists;
in the backtest the GEX transition flag is simply False (NaN-safe). Validation
whipsaw/accuracy stats therefore use 5 of the 6 flags historically.

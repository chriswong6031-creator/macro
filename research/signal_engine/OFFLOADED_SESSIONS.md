# Offloaded Sessions — what each one is working on

Quick-reference map of the parallel Opus sessions spun up for the signal-engine program.
All build on / target the **`feat/signal-engine-buy-filter`** integration branch (NOT `origin/main`,
which is a deploy target). Every session is told to read `research/signal_engine/CHARTER.md` first.

Legend: 🟢 running · ⚪ chip pending (click the chip to launch in its own worktree)

---

## Research & signals
| # | Session | Status | What it's doing | Output |
|---|---------|--------|-----------------|--------|
| 1 | **Research new buy-signal candidates** | 🟢 | Brainstorm + adversarially vet NEW, orthogonal buy signals to add as extra confluences (judged on drawdown/generalization, not return). | `research/signal_engine/NEW_BUY_SIGNALS.md` |
| 2 | **Tune 2D/3D confluence entry timing** | 🟢 | Fix the lagging-3D-MACD chase: test 2D-MACD / 3D-StochRSI combos + an early-anticipation trigger to enter just before the breakout. *(Already surfaced the `early` advance-warning leg.)* | `research/signal_engine/CONFLUENCE_TUNING.md` |
| 3 | **Validated simple EXIT signal** | 🟢 | Test exit rules vs the baseline on drawdown across held-out names, with a kill rule. *(Already concluded: Chandelier/EMA trailing stops did NOT generalize → kept the simple baseline; EMA8 breach kept as a display-only tail-risk flag.)* | `engine/signal_quality.py` exit notes, `diagnose_v5_exits.py` |
| 4 | **Gate Standout grids with the confluence** | ⚪ | Make the validated confluence the PRIMARY gated buy-entry for the Standout Top Stocks grid on ALL country dashboards, with an anticipation exception. **Starts after #2 reports** (reads `CONFLUENCE_TUNING.md`). | Standout grid builders, per country |

## Brain & validation
| # | Session | Status | What it's doing | Output |
|---|---------|--------|-----------------|--------|
| 5 | **Wire mtf_signals breadth into the brain** | 🟢 | Make Mastermind consume the shipped `latest['mtf_signals']` leaf as a cross-sectional entry-quality breadth check, surfaced only when it diverges from the macro read. | `engine/master_brain.py` |
| 6 | **Reusable purged walk-forward harness** | 🟢 | The one leak-free validation backbone (purged/embargoed WF + cross-sectional %-improved + overfit guard), proven by recovering the buy-filter's −23.7%→−15.5%. | `research/signal_engine/walk_forward.py`, `HARNESS_USAGE.md` |
| 7 | **Signal track-record logger** | ⚪ | Append-only log of every deployed signal + backfilled forward outcomes (20/60/180d) to grade take-vs-block, per-regime, per-archetype on live data. | `data/signal_archive/track_record.parquet`, `track_record_audit.py` |
| 8 | **Consolidate modules + README** | ⚪ | Extract clean reusable modules (`buy_filters.py`, `exit_rules.py` stub) + a README. **Additive-only, merge LAST** (other sessions import the current files). | `research/signal_engine/{buy_filters,exit_rules}.py`, `README.md` |

## Charting, data & infra
| # | Session | Status | What it's doing | Output |
|---|---------|--------|-----------------|--------|
| 9 | **Custom live charting web-app** | 🟢 | The separate TradingView-style charting product (going live soon). Consumes the §7 marker contract. *(Pre-existing workstream.)* | the charting app |
| 10 | **Render signal markers on the chart** | ⚪ | Render buy/sell/cut/rebuy markers (take=solid, block=hollow) on `site/chart.js`, built to the §7 contract so it's portable to #9. | `site/chart.js` |
| 11 | **Signal-marker schema + validator** | 🟢 | Freeze the §7 contract as JSONSchema + a build-time gate so writer (engine) and readers (charts) never drift. The single source of truth to hand #9/#10. | `research/signal_engine/SCHEMA.json`, `scripts/validate_signals.py` |
| 12 | **Wire Polygon standard live-data** | ⚪ | Activate the existing Polygon intraday collector + live-quotes overlay on the **standard plan (15-min delayed, key in CI)**, architected for a later real-time websocket upgrade. | `data/intraday/`, live overlay, `research/LIVE_DATA_POLYGON.md` |
| 13 | **Reconstruct high/low for close-only** | ⚪ | Conservative high/low imputation so HK/CN (and the close-only US engine) support candles + ATR/swing/divergence. | reconstructed OHLC path |
| 14 | **Data-quality audit suite** | ⚪ | Deterministic read-only audits (gaps, OHLC validity, NaN, backwards revisions, stale, coverage) wired at end of collection; abort >5% failure. | `scripts/audit_{prices,macro,universe}.py`, `data/quality/` |

---

## Sequencing notes
- **#11 (schema) → #10 (chart markers) & #9 (web-app):** schema first / in parallel so both chart surfaces build to a validated contract.
- **#6 (harness) → #3 (exit) & future signal work:** validate through the shared harness when available.
- **#2 (tuning) → #4 (Standout gate):** the gate uses the tuning session's best variant.
- **#8 (consolidate) merges LAST** so it doesn't yank files out from under the other running sessions.
- **#13 (high/low)** softly enables #3's ATR exits and #10's candles for close-only names.

## Held for owner decision (NOT offloaded)
- **CN/HK/Canada per-ticker OHLC history source** — those stores are snapshot-only; #4 will gate non-US gracefully and report coverage, but a true rollout needs a chosen data source.
- **Real-time websocket data plan** — #12 uses the 15-min-delayed standard plan; upgrade is a later cost decision.

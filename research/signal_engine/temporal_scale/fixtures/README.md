# TradingView Temporal Recipe Probe — External Capture Runbook

This is an operator recipe for the separately Chairman-delivered external capture child. It does
not claim that any chart was captured, does not instruct a login, and does not create data,
signal, trade, portfolio, or production authority. Keep all licensed/raw exports outside this
repository unless an explicit rights record permits redistribution.

## Scope and identity fence

Capture each motivating chart as a separate packet. WMT and every observed “silver” chart remain
independent packets: do not pool, average, substitute, or use one to complete the other.

1. Record the exact observed TradingView symbol, vendor-qualified feed, `syminfo.tickerid`,
   `syminfo.main_tickerid`, exchange/feed label, asset class, currency, and chart description.
   Preserve the observed chart; Yahoo, Polygon, Massive, or another proxy/control never satisfies
   a different TradingView identity.
2. Data OS owns canonical identity semantics. Record a concrete listed future as
   `FUT:<MIC>:<ROOT>:<YYYYMM>` only when the observed product supplies its exact contract month;
   record spot FX with the existing `FX:<BASE><QUOTE>` semantics. This runbook does not create an
   identity master.
3. For silver, classify the observed item separately as spot, CFD, concrete COMEX future,
   continuous future, ETF, or other. A concrete future needs its exact `contract_month`; a
   continuous future or CFD needs its exact vendor/feed, session, and `roll_recipe`. `SI`,
   `SI1!`, XAGUSD, SLV, and any other product are not interchangeable.

## Chart and indicator provenance

1. Record the chart timeframe, named session, exchange timezone, and the manually selected chart
   display timezone. Record extended-hours state and every data-modification setting: split,
   dividend, back-adjustment, settlement-as-close, corrections, and any vendor-specific setting.
2. Record all seven chart-type states from the probe: standard, Heikin-Ashi, Renko, Line Break,
   Kagi, Point & Figure, and Range. They must be coherent: standard is true only when every
   nonstandard type is false; otherwise exactly one nonstandard type is true. An unknown or
   incoherent type remains an exact incomplete recipe, never a normalized standard OHLC chart.
3. Add and compile the exact committed Git probe source at
   `research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine`. The separate
   capture child records its Git blob SHA at capture time; it does not deliver this source to the
   repository. Its fixed inputs are RSI 14; RSI-MACD 14/60/5; and StochRSI 14/3/3. Read the
   metadata table and preserve all listed symbol/feed/session/timezone/timeframe and input values.
4. Record observed-indicator provenance independently from the owner probe: observed family,
   title, source kind, source hash, and inputs; then probe family, Git blob SHA, inputs, EMA
   adjustment, and RMA seed semantics. Title similarity is never equality. Invite-only,
   closed-source, and unknown observed math remains incomplete even when the owner probe exists.
5. At capture time, obtain and record the exact Git blob SHA for the committed probe source. Do
   not infer it from a title, a later local edit, or a related indicator.

## History, export, and receipt procedure

1. Load sufficient left history before exporting. The prefix-drop sequence is exactly
   (1, 5, 13, 31, 63); 256 is the comparison-tail length, not a prefix drop. The conservative
   floor is 63 + 871 + 256 = 1190 confirmed rows: the maximum 63-row prefix drop, the 871-bar
   post-drop convergence floor, and the 256-bar comparison tail. A low-precision export is
   `INSUFFICIENT_EXPORT_PRECISION` and cannot enter parity.
2. Export the chart and data-window probe columns to a location outside this repository. Preserve
   exact UTF-8 bytes and calculate the receipt with `shasum -a 256 chart.csv`. Record the filename,
   SHA-256, row count, first open, last close, and loaded-history start without placing raw rows in
   Git.
3. Require explicit precision-16 OHLCV and oscillator output. Preserve the integer metadata and
   boolean data-window columns at precision 0: opens, closes, trading-day timestamp, duration,
   bar index, confirmed state, and all session flags.
4. Record whether the final exported row is provisional. Quarantine that final provisional row for
   parity; reject any unconfirmed interior row. A 30-minute aggregate row is not evidence of
   traded minutes. Leave trade-count, traded-time, volume-time, and variance-time clocks marked
   unavailable unless true source fields establish them.

## Recipe completion and rights

1. Build `mastermind.temporal_chart_recipe.v1` with no inferred defaults. A complete recipe needs
   all load-bearing identity, chart, observed/probe provenance, export hash, and rights values.
2. When a required observed value is unavailable, write an incomplete recipe and list exactly every
   absent path in `missing_fields`; never replace missing values with zero, a proxy, or a guessed
   session/roll identity.
3. Record `rights.use=local_research_only`, the observed redistribution status, and the source
   reference. Raw TradingView or vendor exports remain outside Git unless the applicable rights
   record expressly permits redistribution.

## Hard stop

This capture packet is evidence provenance only. Do not read or report outcomes, returns, trades,
portfolio results, signal rankings, W1B usefulness claims, or production decisions. If exact
identity, session, roll, observed indicator math, rights, or export precision cannot be frozen,
return an independently typed incomplete/`UNRESOLVED_DATA` packet for that chart rather than using
another symbol, vendor, session, or product.

## Local W1A CLI

The repository child does not perform the external capture. After a separate authorized capture
child has produced a recipe and local CSV, run the deterministic coordinator from the repository
root. Keep all inputs and outputs outside tracked production paths.

```bash
python3 scripts/research/run_temporal_scale_artifact_attack.py validate-recipe \
  --recipe "$MMX_TEMPORAL_RESEARCH_INPUTS/chart/recipe.json" \
  --csv "$MMX_TEMPORAL_RESEARCH_INPUTS/chart/chart.csv" \
  --output-dir "$MMX_TEMPORAL_RESEARCH_OUTPUTS/chart"

python3 scripts/research/run_temporal_scale_artifact_attack.py parity \
  --recipe "$MMX_TEMPORAL_RESEARCH_INPUTS/chart/recipe.json" \
  --csv "$MMX_TEMPORAL_RESEARCH_INPUTS/chart/chart.csv" \
  --output-dir "$MMX_TEMPORAL_RESEARCH_OUTPUTS/chart"

python3 scripts/research/run_temporal_scale_artifact_attack.py attack \
  --recipe "$MMX_TEMPORAL_RESEARCH_INPUTS/chart/recipe.json" \
  --csv "$MMX_TEMPORAL_RESEARCH_INPUTS/chart/chart.csv" \
  --lower-grain-csv "$MMX_TEMPORAL_RESEARCH_INPUTS/chart/lower-grain.csv" \
  --ledger-path "$MMX_TEMPORAL_RESEARCH_OUTPUTS/chart/trial_ledger.jsonl" \
  --output-dir "$MMX_TEMPORAL_RESEARCH_OUTPUTS/chart"
```

If `--ledger-path` is omitted, `attack` uses `OUTPUT_DIR/trial_ledger.jsonl`. The production
`data/trial_ledger.jsonl` path is always refused and has no override. The command validates and
hashes inputs before creating outputs, prints the frozen grid hash before diagnostics, never prints
source rows, and writes strict canonical JSON through atomic replacement.

The evidence bundle contains `normalized_recipe.json`, `bar_receipts.json`,
`kernel_signature.json`, `parity_receipt.json`, `frozen_grid.json`, and `run_manifest.json`.
`attack` additionally writes `artifact_attack_result.json` and the explicit nonproduction trial
ledger. The manifest records the exact command, interpreter and platform, current Git head when
available, input and output hashes, and the invariant declarations `network_used=false` and
`production_ledger_used=false`.

A complete packet with parity `FAIL` exits nonzero and Gate 2 does not execute. A schema-valid
incomplete recipe exits zero with a typed `UNRESOLVED_DATA` result without opening the named CSV;
this is the correct path for an absent real WMT or silver packet. `MECHANICALLY_SURVIVES` is only a
W1A construction result. It confers no ranking, gating, sizing, trading, Prophet, W1B, or
production authority.

# Characteristic Market Time × Signal Grain — Gate 1/2 Design Specification

**Date:** 2026-09-03  
**Status:** W0 design freeze; implementation not started  
**Workstream:** `WS:TEMPORAL-GRAIN-INTELLIGENCE`  
**Implements:** `research/signal_engine/temporal_scale/CHARACTERISTIC_MARKET_TIME_SIGNAL_GRAIN_ARCHITECTURE_FREEZE_2026-09-03.md`  
**First implementation operation:** `temporal-grain-gakd-artifact-attack-r1-20260903-sol-001`

## 1. Goal

Build a deterministic, research-only harness that accepts an exact TradingView chart recipe and
CSV export, proves the input identity and integrity, reproduces the canonical RSI-MACD/StochRSI
vector, reconstructs actual session/bar receipts, separates bar grain (G), anchor/session (A),
kernel memory (K) and data plane (D), and returns a typed artifact classification **without reading
trading outcomes**.

The first real inputs are the exact WMT 12H extended-hours chart and the exact silver 8H chart.
Neither instrument is a confirmation sample.

## 2. Non-goals

The release does not:

- choose a best timeframe for a ticker;
- calculate entry returns, Sharpe, total return or portfolio outcomes;
- modify `engine/signal_quality.py`, Golden Oracle, Prophet, Entry Radar or Stock Identity v0;
- backfill or persist vendor market data;
- create an event store, signal ledger, evaluator, identity plane, lifecycle or chart renderer;
- grant rank, gate, size, trade or `can_open_entry` authority;
- infer missing identity fields;
- substitute XAGUSD, SI, SLV or another silver product for the observed symbol;
- commit restricted TradingView/vendor exports.

## 3. File structure and responsibilities

### Research capture

`research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine`

- Pine v6 indicator used only to expose chart identity, actual time boundaries, session flags and
  canonical indicator plots for TradingView CSV export.
- It does not create a signal or alert.
- Its Git blob SHA is part of every chart recipe.

`research/signal_engine/temporal_scale/fixtures/README.md`

- Exact manual capture procedure.
- Explains why raw licensed exports stay outside Git.
- Names required local filenames and hashing command.

### Python package

`scripts/research/temporal_scale/contracts.py`

- Immutable dataclasses and strict JSON parsing/serialization.
- Owns `ChartRecipe`, `BarReceipt`, `KernelSignature`, `ArtifactTest`, and
  `ArtifactAttackResult`.
- Rejects unknown enum values, NaN/Inf, missing required fields and inconsistent status.

`scripts/research/temporal_scale/chart_export.py`

- Loads TradingView CSV without guessing column names.
- Validates required probe plots, monotone bar timestamps, exact CSV SHA-256 and recipe range.
- Produces one normalized `pandas.DataFrame` and `BarReceipt` sequence.
- Performs no network access.

`scripts/research/temporal_scale/kernel_memory.py`

- Deterministic EMA/RMA half-life functions.
- Converts target clock half-lives to approximate bar-count lengths.
- Implements continuous-time EMA over elapsed/traded/activity increments.
- Produces `KernelSignature`; it does not optimize parameters.

`scripts/research/temporal_scale/session_bars.py`

- Reconstructs candidate bars from already-loaded lower-grain rows.
- Requires explicit IANA timezone and session intervals.
- Discloses effective duration, clipping, empty intervals and confirmation.
- Generates prespecified phase/session variants; never uses naïve calendar resampling as truth.

`scripts/research/temporal_scale/parity.py`

- Imports the canonical indicator through `engine.entry_radar.indicator_core`.
- Compares exported TradingView plots with Python values only after both are finite.
- Computes the first comparable bar and per-series max absolute error.
- Runs leading-history truncation invariance.

`scripts/research/temporal_scale/artifact_attack.py`

- Builds the frozen G/A/K/D diagnostic grid.
- Runs human-chart, memory-matched, anchor/session and implementation/data-plane controls.
- Reports bar/indicator/signal-density diagnostics only.
- Applies deterministic classification rules for
  `ARTIFACT`, `FILTER_MEMORY`, `SESSION_GRAMMAR`, `MIXED`, or `UNRESOLVED_DATA`.
- It never imports an outcome, return, trade or portfolio module.

`scripts/research/run_temporal_scale_artifact_attack.py`

- CLI coordinator.
- Accepts recipe path, CSV path, output directory and optional lower-grain fixture path.
- Uses an explicitly supplied TrialLedger path; the production ledger is not touched by tests.
- Writes strict JSON receipts atomically.

### Tests

- `tests/test_temporal_scale_contracts.py`
- `tests/test_temporal_scale_kernel_memory.py`
- `tests/test_temporal_scale_session_bars.py`
- `tests/test_temporal_scale_parity.py`
- `tests/test_temporal_scale_artifact_attack.py`

Tests use synthetic and rights-safe fixtures only.

## 4. Exact interfaces

### 4.1 Contracts

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

CaptureStatus = Literal["complete", "incomplete"]
AssetClass = Literal["equity", "futures", "spot_fx", "cfd", "etf", "other"]
NamedSession = Literal["regular", "extended", "24h", "us_regular", "vendor_named"]
ClockBasis = Literal[
    "bar_count", "elapsed_time", "traded_time",
    "volume_time", "trade_time", "variance_time",
]
ParityStatus = Literal["PASS", "FAIL", "UNRESOLVED_DATA"]
ArtifactClassification = Literal[
    "ARTIFACT", "FILTER_MEMORY", "SESSION_GRAMMAR", "MIXED", "UNRESOLVED_DATA",
]


@dataclass(frozen=True, slots=True)
class ChartRecipe:
    schema_version: str
    recipe_id: str
    captured_at: str
    capture_status: CaptureStatus
    observer: str
    instrument: Mapping[str, Any]
    chart: Mapping[str, Any]
    indicator: Mapping[str, Any]
    export: Mapping[str, Any]
    rights: Mapping[str, Any]
    missing_fields: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ChartRecipe": ...

    @classmethod
    def from_json(cls, path: Path) -> "ChartRecipe": ...

    def validate(self) -> None: ...

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class BarReceipt:
    schema_version: str
    recipe_id: str
    bar_index: int
    open_ms: int
    close_ms: int
    nominal_minutes: int
    effective_minutes: int
    traded_minutes: int | None
    volume: float | None
    trade_count: int | None
    realized_variance: float | None
    session_flags: Mapping[str, bool]
    clipped: bool
    confirmed: bool
    empty_interval: bool
    known_at_ms: int
    source_row_sha256: str

    def validate(self) -> None: ...

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class KernelSignature:
    schema_version: str
    indicator_spec_hash: str
    input_series: str
    components: tuple[Mapping[str, Any], ...]
    bar_memory: Mapping[str, float]
    clock_basis: ClockBasis
    clock_parameter: Mapping[str, Any]
    warmup_first_finite_index: Mapping[str, int | None]
    linear_diagnostics: Mapping[str, Any]
    nonlinear_caveat: str

    def validate(self) -> None: ...

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ArtifactTest:
    test_id: str
    axis: Literal["G", "A", "K", "D", "PARITY", "TRUNCATION", "DENSITY"]
    variant_id: str
    input_hash: str
    status: Literal["PASS", "FAIL", "UNAVAILABLE"]
    metrics: Mapping[str, Any]
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ArtifactAttackResult:
    schema_version: str
    operation_key: str
    recipes: tuple[str, ...]
    frozen_grid_hash: str
    trial_family: str
    tests: tuple[ArtifactTest, ...]
    parity: Mapping[str, Any]
    classification: ArtifactClassification
    classification_receipts: tuple[str, ...]
    authority: Mapping[str, bool]

    def validate(self) -> None: ...

    def to_dict(self) -> dict[str, Any]: ...
```

Ellipses above denote implementation bodies, not unresolved interface decisions. The implementation
plan supplies exact validation behavior and tests.

### 4.2 CSV loader

```python
REQUIRED_PROBE_COLUMNS: tuple[str, ...] = (
    "TG_time_open_ms",
    "TG_time_close_ms",
    "TG_duration_ms",
    "TG_bar_index",
    "TG_is_confirmed",
    "TG_is_market",
    "TG_is_premarket",
    "TG_is_postmarket",
    "TG_is_firstbar",
    "TG_is_lastbar",
    "TG_is_firstbar_regular",
    "TG_is_lastbar_regular",
    "TG_rsi",
    "TG_rsi_macd",
    "TG_rsi_macd_signal",
    "TG_rsi_macd_hist",
    "TG_stoch_k",
    "TG_stoch_d",
)


@dataclass(frozen=True, slots=True)
class LoadedChartExport:
    recipe: ChartRecipe
    frame: "pd.DataFrame"
    receipts: tuple[BarReceipt, ...]
    csv_sha256: str


def sha256_file(path: Path) -> str: ...


def resolve_column(frame: "pd.DataFrame", exact_title: str) -> str:
    """Return the one exact/export-prefixed matching column; raise on zero or multiple."""


def load_chart_export(recipe_path: Path, csv_path: Path) -> LoadedChartExport: ...
```

Column resolution may accept TradingView’s script-name prefix but must match the exact plot title
suffix. It may not fuzzy-match “MACD” or silently choose among duplicates.

### 4.3 Kernel memory

```python
def ema_half_life_bars(length: int) -> float: ...
def rma_half_life_bars(length: int) -> float: ...

def ema_length_for_half_life_bars(target_half_life_bars: float) -> int:
    """Nearest integer N >= 1 minimizing absolute half-life error; deterministic tie -> smaller N."""

def continuous_ema(
    values: "pd.Series",
    clock_increments: "pd.Series",
    *,
    tau: float,
    seed: float | None = None,
) -> "pd.Series": ...

def canonical_kernel_signature(
    close: "pd.Series",
    *,
    clock_basis: ClockBasis = "bar_count",
    clock_parameter: Mapping[str, Any] | None = None,
) -> KernelSignature: ...
```

`continuous_ema` requires finite nonnegative increments, strictly positive `tau`, and aligned indexes.
A zero increment carries the prior state. Missing values produce missing output and do not silently
advance the state.

### 4.4 Session bars

```python
@dataclass(frozen=True, slots=True)
class SessionInterval:
    start_local: str
    end_local: str
    label: str


@dataclass(frozen=True, slots=True)
class BarGridSpec:
    grid_id: str
    timezone: str
    nominal_minutes: int
    phase_minutes: int
    intervals: tuple[SessionInterval, ...]
    include_empty: bool
    close_delay_minutes: int

    def validate(self) -> None: ...


def build_session_bars(
    rows: "pd.DataFrame",
    *,
    recipe_id: str,
    grid: BarGridSpec,
) -> tuple["pd.DataFrame", tuple[BarReceipt, ...]]: ...

def generate_phase_variants(
    base: BarGridSpec,
    phase_minutes: Sequence[int],
) -> tuple[BarGridSpec, ...]: ...
```

Input rows require UTC `open_ms`, `close_ms`, OHLCV and optionally trade count. Grid intervals use an
IANA timezone. Overnight intervals are explicit. DST conversion uses `zoneinfo`, not fixed offsets.
Bars never cross a declared closed interval. The final bar in each interval clips to the interval end.

### 4.5 Parity and truncation

```python
PARITY_FIELDS: tuple[tuple[str, str], ...] = (
    ("TG_rsi", "rsi"),
    ("TG_rsi_macd", "rsi_macd"),
    ("TG_rsi_macd_signal", "rsi_macd_signal"),
    ("TG_rsi_macd_hist", "rsi_macd_hist"),
    ("TG_stoch_k", "stoch_k"),
    ("TG_stoch_d", "stoch_d"),
)


@dataclass(frozen=True, slots=True)
class ParityReceipt:
    status: ParityStatus
    tolerance: float
    first_comparable_bar_ms: int | None
    compared_rows: int
    max_abs_error: Mapping[str, float | None]
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]: ...


def canonical_indicator_frame(close: "pd.Series") -> "pd.DataFrame": ...

def compare_indicator_parity(
    loaded: LoadedChartExport,
    *,
    tolerance: float = 1e-10,
) -> ParityReceipt: ...

def truncation_invariance(
    close: "pd.Series",
    *,
    drop_prefixes: Sequence[int],
    tolerance: float = 1e-10,
    comparison_tail: int = 256,
) -> tuple[ArtifactTest, ...]: ...
```

Parity compares only timestamps where both sides are finite. It fails if no field reaches a finite
comparison, if timestamps are duplicated/nonmonotone, or if any field exceeds tolerance.

### 4.6 Artifact grid and classification

```python
@dataclass(frozen=True, slots=True)
class ArtifactGrid:
    human_chart_grains_minutes: tuple[int, ...]
    memory_matched_grains_minutes: tuple[int, ...]
    anchor_phase_fractions: tuple[float, ...]
    session_variants: tuple[str, ...]
    implementation_controls: tuple[str, ...]
    data_plane_controls: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]: ...
    def sha256(self) -> str: ...


def default_artifact_grid(recipe: ChartRecipe) -> ArtifactGrid: ...

def register_artifact_grid(
    grid: ArtifactGrid,
    *,
    ledger_path: Path,
    family: str = "temporal_grain_gakd_r1",
    info_cutoff: str,
) -> int: ...

def run_artifact_attack(
    loaded: LoadedChartExport,
    *,
    lower_grain_rows: "pd.DataFrame | None",
    grid: ArtifactGrid,
    ledger_path: Path,
) -> ArtifactAttackResult: ...
```

`default_artifact_grid` is a transparent deterministic function of the motivating grain and session,
not outcomes. The exact W1 constants are:

- human/memory grains: one-half, two-thirds, exact, four-thirds and two-times the motivating nominal
  minutes, rounded only when the value is an integer minute and deduplicated;
- anchor phases: `0`, one-quarter, one-half and three-quarters of each candidate grain;
- session variants: the exact active session plus only named alternatives explicitly supplied in the
  recipe manifest;
- implementation controls: `owner_rsi_macd_stochrsi`, `standard_price_macd_12_26_9`;
- data-plane controls: exact plane only unless an additional fully specified recipe is supplied.

The diagnostic grid registers every generated variant before computation. It is not written to the
production ledger by tests.

Classification is deterministic:

1. incomplete recipe or parity unresolved -> `UNRESOLVED_DATA`;
2. parity fails, truncation fails, or one arbitrary phase alone creates the observation ->
   `ARTIFACT`;
3. after exact parity, fixed-bar differences disappear under matched-memory variants across at least
   two grains -> `FILTER_MEMORY`;
4. after exact parity, the effect survives at semantic session variants and fails most arbitrary
   phase shifts -> `SESSION_GRAMMAR`;
5. evidence independently meets both rules 3 and 4 -> `MIXED`;
6. otherwise -> `UNRESOLVED_DATA`.

The word “effect” in rules 3–5 is limited in W1 to indicator-path diagnostics frozen in the plan:
cross/turn timestamps, indicator total variation, phase displacement and signal density. It does not
include returns or trade outcomes. The W1 report must not call any of these diagnostics “edge”.

## 5. Pine probe design

The Pine source uses `//@version=6` and one `indicator()` with no `request.security()`, alerts,
orders or external inputs except the six indicator lengths.

Metadata table fields:

- probe version;
- `syminfo.tickerid`;
- `syminfo.main_tickerid`;
- `syminfo.type`;
- `syminfo.currency`;
- `syminfo.session`;
- `syminfo.timezone`;
- `timeframe.period`;
- six input values.

Numeric plots have the exact titles in `REQUIRED_PROBE_COLUMNS` and use
`display=display.data_window` so TradingView’s chart-data export includes them without cluttering the
chart.

Canonical calculations:

```pine
float rsi = ta.rsi(close, rsiLen)
float macd = ta.ema(rsi, fastLen) - ta.ema(rsi, slowLen)
float macdSignal = ta.ema(macd, signalLen)
float macdHist = macd - macdSignal
float rsiLow = ta.lowest(rsi, stochLen)
float rsiHigh = ta.highest(rsi, stochLen)
float rawStoch = rsiHigh == rsiLow ? na : 100.0 * (rsi - rsiLow) / (rsiHigh - rsiLow)
float stochK = ta.sma(rawStoch, smoothK)
float stochD = ta.sma(stochK, smoothD)
```

Session flags are plotted as `1.0` or `0.0`; `time`, `time_close`, `time_close-time`, `bar_index` and
`barstate.isconfirmed` are plotted numerically. The recipe manifest separately records the manual
chart timezone and data-modification settings because the script cannot prove every UI setting.

## 6. Data and rights behavior

- The implementation performs no network calls.
- Real chart CSVs and lower-grain vendor files are external inputs.
- Every external input is content-hashed before parsing.
- Raw data is never copied into a receipt.
- The default output contains aggregate counts, timestamps, hashes and diagnostics only.
- `rights.use != local_research_only` or `rights.redistribution=unknown` never authorizes committing
  raw data.
- Massive can support a separately specified WMT D-plane reconstruction, but it cannot be called
  “TradingView parity” unless the TradingView feed is itself Massive and exact bar identity matches.
- Silver data is rejected until its exact product/vendor/contract/roll fields are complete.

## 7. Time, null and correction behavior

- All persisted timestamps are integer Unix milliseconds.
- Timezone inputs are IANA names; fixed UTC offsets are rejected for exchange-session construction.
- A bar is confirmed only when `known_at_ms <= observation_ms`.
- No-trade intervals remain absent or explicit empty receipts according to the grid; OHLC is never
  forward-filled.
- Null activity fields mean unavailable.
- NaN and Infinity are rejected at JSON boundaries.
- Duplicate timestamps fail closed.
- Vendor corrections create a new input hash and result receipt; they do not overwrite prior
  evidence without lineage.
- Adjusted/raw and individual/continuous futures series remain separate recipe identities.
- A clipped bar reports nominal and effective minutes.
- Early closes, holidays and maintenance breaks are represented by explicit session intervals.

## 8. Failure states

Typed failures include:

- `RECIPE_INCOMPLETE`
- `CSV_HASH_MISMATCH`
- `CSV_COLUMN_MISSING`
- `CSV_COLUMN_AMBIGUOUS`
- `TIMESTAMP_NON_MONOTONE`
- `TIMESTAMP_DUPLICATE`
- `BAR_DURATION_INVALID`
- `IANA_TIMEZONE_INVALID`
- `SESSION_INTERVAL_INVALID`
- `PARITY_NO_COMPARABLE_ROWS`
- `PARITY_TOLERANCE_EXCEEDED`
- `TRUNCATION_INVARIANCE_FAILED`
- `SILVER_IDENTITY_UNRESOLVED`
- `RIGHTS_UNKNOWN`
- `LOWER_GRAIN_REQUIRED`
- `GRID_HASH_MISMATCH`
- `OUTCOME_IMPORT_FORBIDDEN`

The CLI emits a nonzero exit code for malformed contracts or integrity/parity failure. A scientifically
unresolved but well-formed recipe writes a valid `UNRESOLVED_DATA` result and exits zero so
unresolved evidence is not disguised as a software crash.

## 9. Testing strategy

Tests must establish:

1. strict contract and hash behavior;
2. known EMA/RMA half-lives and deterministic inverse mapping;
3. continuous-time decay on unequal increments;
4. RTH/extended/overnight grid clipping, DST and early-close behavior;
5. missing intervals are not filled;
6. canonical indicator parity on a fixture generated from `engine.entry_radar.indicator_core`;
7. injected perturbation exceeds tolerance and fails;
8. leading-history phase changes are detected;
9. full grid registration occurs before diagnostics;
10. fixed deterministic classification rules;
11. AST/source guards reject network, outcome and production-ledger imports;
12. output authority booleans are always false.

Real proof then adds exact WMT and silver packets, hashes and commands. Synthetic tests alone do not
satisfy Gate 1.

## 10. Acceptance

The implementation PR is acceptable only when:

- all tests pass;
- `python3 scripts/agentos.py validate` passes for its return records;
- the exact TradingView probe compiles on Pine v6;
- at least one complete real chart packet runs through parity;
- WMT and silver are reported independently;
- exact recipes and CSV hashes are printed;
- no restricted raw market data is committed;
- no outcome module is imported;
- the frozen grid hash is stable across input-order changes;
- the result is one typed classification with receipts;
- the PR remains zero-authority and production-inert.

Gate 1 scientific completion requires both motivators or an explicit independent
`UNRESOLVED_DATA` result for the missing one. Gate 2 scientific completion requires exact parity
before any mechanism classification other than `ARTIFACT`/`UNRESOLVED_DATA`.

## 11. Stop condition and continuation

Stop before structure-scale modeling if exact parity fails, identity is incomplete, a result is
arbitrary-phase-only, memory matching removes the apparent phenomenon, rights are unknown, or a
duplicate owner would be required.

Only a Sol ruling after Gate 2 may authorize a separate structure-derived-scale preregistration.
That later child must freeze an outcome-blind mapping and use instrument-disjoint confirmation.

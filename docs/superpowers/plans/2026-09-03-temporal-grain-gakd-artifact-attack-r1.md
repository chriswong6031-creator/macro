# Temporal Grain G/A/K/D Artifact Attack R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, zero-authority Gate-1/2 research harness that reproduces exact TradingView indicator vectors and separates bar grain, session anchor, kernel memory and data plane before any trading outcome is read.

**Architecture:** A Pine v6 probe exports exact chart timestamps, session flags and canonical RSI-MACD/StochRSI plots. A pure Python research package validates a strict chart manifest and CSV hash, reconstructs actual bar receipts, reproduces `engine.entry_radar.indicator_core`, runs a preregistered G/A/K/D diagnostic grid, and emits one typed artifact classification. Licensed chart files stay outside Git; only code, rights-safe fixtures, hashes and summary receipts are committed.

**Tech Stack:** Python 3.11+, standard library, pandas, numpy, pytest, `zoneinfo`, TradingView Pine Script v6, `engine.entry_radar.indicator_core`, `engine.trial_ledger.TrialLedger`.

**Spec:** `docs/superpowers/specs/2026-09-03-characteristic-market-time-signal-grain-design.md`

## Global Constraints

- Operation: `temporal-grain-gakd-artifact-attack-r1-20260903-sol-001`.
- Read the W0 architecture freeze and the design spec before editing.
- Authorized implementation paths are exactly those listed below.
- Do not modify `engine/signal_quality.py`, `engine/canon.py`, `engine/entry_radar/indicator_core.py`, `engine/entry_radar/four_hour.py`, `engine/stock_identity/`, Prophet, Golden Oracle, Terminal or production data paths.
- No network calls, credentials, vendor collectors or committed restricted chart exports.
- No outcome, return, trade, Sharpe, portfolio or “best timeframe” computation.
- Use the existing TrialLedger with an explicit non-production path; never append to `data/trial_ledger.jsonl` from tests or the default CLI.
- Persist strict UTF-8 JSON only; reject NaN, Infinity, ambiguous columns and inferred identity.
- All rank, gate, size, trade, `can_open_entry`, Prophet and Golden-Oracle authority remains false.
- WMT and the motivating silver chart are discovery examples, not confirmation evidence.
- Do not silently substitute another symbol, contract, feed, session or roll recipe.
- Return to Sol before structure-scale modeling or production integration.

---

## File Map

### Create

- `research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine`
- `research/signal_engine/temporal_scale/fixtures/README.md`
- `scripts/research/temporal_scale/__init__.py`
- `scripts/research/temporal_scale/contracts.py`
- `scripts/research/temporal_scale/chart_export.py`
- `scripts/research/temporal_scale/kernel_memory.py`
- `scripts/research/temporal_scale/session_bars.py`
- `scripts/research/temporal_scale/parity.py`
- `scripts/research/temporal_scale/artifact_attack.py`
- `scripts/research/run_temporal_scale_artifact_attack.py`
- `tests/test_temporal_scale_contracts.py`
- `tests/test_temporal_scale_kernel_memory.py`
- `tests/test_temporal_scale_session_bars.py`
- `tests/test_temporal_scale_parity.py`
- `tests/test_temporal_scale_artifact_attack.py`
- `agentos/handoffs/TEMPORAL-GRAIN-INTELLIGENCE-W1-R1.md`

### Modify

- `agentos/workstreams/WS-TEMPORAL-GRAIN-INTELLIGENCE.md`

No other path is authorized.

---

### Task 1: Strict chart, bar, kernel and result contracts

**Files:**
- Create: `scripts/research/temporal_scale/__init__.py`
- Create: `scripts/research/temporal_scale/contracts.py`
- Test: `tests/test_temporal_scale_contracts.py`

**Interfaces:**
- Produces `ChartRecipe`, `BarReceipt`, `KernelSignature`, `ArtifactTest`, `ArtifactAttackResult`, `strict_json_dumps`, and `atomic_write_json`.
- Consumed by Tasks 3–8.

- [ ] **Step 1: Write failing contract tests**

Create tests for a complete WMT recipe, an explicitly incomplete recipe, unresolved silver futures identity, duration inconsistency, NaN rejection and authority escalation. The base helper must be:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research.temporal_scale.contracts import (
    ArtifactAttackResult,
    BarReceipt,
    ChartRecipe,
    ContractError,
    strict_json_dumps,
)


def complete_recipe_dict() -> dict:
    return {
        "schema_version": "mastermind.temporal_chart_recipe.v1",
        "recipe_id": "wmt-720-extended-fixture",
        "captured_at": "2026-09-03T06:00:00Z",
        "capture_status": "complete",
        "observer": "fixture",
        "instrument": {
            "display_symbol": "WMT",
            "tickerid": "NYSE:WMT",
            "main_tickerid": "NYSE:WMT",
            "asset_class": "equity",
            "exchange": "NYSE",
            "vendor_feed": "fixture",
            "currency": "USD",
            "contract_month": None,
            "continuous_symbol": None,
            "roll_recipe": None,
            "settlement_basis": None,
        },
        "chart": {
            "timeframe_period": "720",
            "named_session": "extended",
            "exchange_timezone": "America/New_York",
            "chart_timezone": "America/New_York",
            "extended_hours_enabled": True,
            "price_adjustment": "split_adjusted",
            "dividend_adjustment": "off",
            "back_adjustment": "not_applicable",
            "settlement_as_close": "not_applicable",
            "allowed_session_variants": ["extended", "regular"],
        },
        "indicator": {
            "family": "owner_rsi_macd_stochrsi",
            "probe_version": "temporal-recipe-probe-v1",
            "source_git_blob_sha": "1" * 40,
            "inputs": {
                "rsi_len": 14,
                "macd_fast": 14,
                "macd_slow": 60,
                "macd_signal": 5,
                "stoch_len": 14,
                "smooth_k": 3,
                "smooth_d": 3,
            },
            "ema_adjust": False,
            "rma_seed": "sma_seeded",
        },
        "export": {
            "csv_filename": "wmt.csv",
            "csv_sha256": "2" * 64,
            "row_count": 3,
            "first_bar_open_ms": 1_700_000_000_000,
            "last_bar_close_ms": 1_700_100_000_000,
            "loaded_history_start_ms": 1_690_000_000_000,
        },
        "rights": {
            "use": "local_research_only",
            "redistribution": "blocked",
            "source_reference": "fixture",
        },
        "missing_fields": [],
    }


def test_complete_recipe_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(complete_recipe_dict()), encoding="utf-8")
    recipe = ChartRecipe.from_json(path)
    assert recipe.to_dict() == complete_recipe_dict()


def test_complete_recipe_rejects_missing_tickerid(tmp_path: Path) -> None:
    raw = complete_recipe_dict()
    raw["instrument"]["tickerid"] = ""
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ContractError, match="instrument.tickerid"):
        ChartRecipe.from_json(path)


def test_incomplete_recipe_names_every_missing_field(tmp_path: Path) -> None:
    raw = complete_recipe_dict()
    raw["capture_status"] = "incomplete"
    raw["instrument"]["tickerid"] = ""
    raw["missing_fields"] = ["instrument.tickerid"]
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert ChartRecipe.from_json(path).capture_status == "incomplete"


def test_continuous_silver_requires_roll_recipe(tmp_path: Path) -> None:
    raw = complete_recipe_dict()
    raw["instrument"].update({
        "display_symbol": "SI",
        "tickerid": "COMEX:SI1!",
        "main_tickerid": "COMEX:SI1!",
        "asset_class": "futures",
        "exchange": "COMEX",
        "continuous_symbol": "SI1!",
        "roll_recipe": None,
    })
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ContractError, match="roll_recipe"):
        ChartRecipe.from_json(path)


def test_strict_json_rejects_nonfinite() -> None:
    with pytest.raises(ContractError, match="finite"):
        strict_json_dumps({"bad": float("nan")})


def test_result_rejects_authority_escalation() -> None:
    raw = {
        "schema_version": "mastermind.temporal_artifact_attack.v1",
        "operation_key": "temporal-grain-gakd-artifact-attack-r1-20260903-sol-001",
        "recipes": ["r"],
        "frozen_grid_hash": "a" * 64,
        "trial_family": "temporal_grain_gakd_r1",
        "tests": [],
        "parity": {"status": "PASS"},
        "classification": "FILTER_MEMORY",
        "classification_receipts": ["receipt"],
        "authority": {
            "may_rank": True,
            "may_gate": False,
            "may_size": False,
            "may_trade": False,
            "may_modify_prophet": False,
        },
    }
    with pytest.raises(ContractError, match="authority"):
        ArtifactAttackResult.from_dict(raw)
```

- [ ] **Step 2: Run tests and confirm RED**

```bash
python3 -m pytest tests/test_temporal_scale_contracts.py -q
```

Expected: import failure because the package does not exist.

- [ ] **Step 3: Implement the immutable contracts**

Use frozen `@dataclass(slots=True)` records with `from_dict`, `from_json`, `validate`, and `to_dict` methods matching the design spec. Implement strict JSON and atomic writes exactly as follows:

```python
class ContractError(ValueError):
    pass


def _reject_nonfinite(value: object, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"{path} must be finite")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_nonfinite(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_nonfinite(child, f"{path}[{index}]")


def strict_json_dumps(value: object) -> str:
    _reject_nonfinite(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = strict_json_dumps(value) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)
```

Validation requirements:

- exact schema version strings;
- complete recipes require every load-bearing identity field and `missing_fields=[]`;
- incomplete recipes require every absent load-bearing field to be named;
- continuous futures require `continuous_symbol` and nonempty `roll_recipe`;
- concrete futures require `contract_month`;
- `open_ms < close_ms <= known_at_ms`;
- `effective_minutes == (close_ms-open_ms)//60000`;
- clipped means effective minutes are less than nominal minutes;
- empty intervals cannot carry volume/trade count/variance values;
- all result authority values are exactly false;
- all hashes have the declared hexadecimal length.

- [ ] **Step 4: Confirm GREEN and commit**

```bash
python3 -m pytest tests/test_temporal_scale_contracts.py -q
git add scripts/research/temporal_scale/__init__.py scripts/research/temporal_scale/contracts.py tests/test_temporal_scale_contracts.py
git commit -m "feat(temporal-scale): add strict research contracts"
```

---

### Task 2: TradingView Pine recipe probe and capture runbook

**Files:**
- Create: `research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine`
- Create: `research/signal_engine/temporal_scale/fixtures/README.md`

**Interfaces:**
- Produces exact plot titles consumed by `chart_export.REQUIRED_PROBE_COLUMNS`.
- Produces no signal, strategy, alert or network action.

- [ ] **Step 1: Create the Pine v6 probe**

Use this exact indicator core and plot-title contract:

```pine
//@version=6
indicator("Mastermind Temporal Recipe Probe v1", overlay=false)

int rsiLen = input.int(14, "RSI length", minval=1)
int fastLen = input.int(14, "RSI-MACD fast", minval=1)
int slowLen = input.int(60, "RSI-MACD slow", minval=2)
int signalLen = input.int(5, "RSI-MACD signal", minval=1)
int stochLen = input.int(14, "StochRSI length", minval=1)
int smoothK = input.int(3, "StochRSI K", minval=1)
int smoothD = input.int(3, "StochRSI D", minval=1)

float rsi = ta.rsi(close, rsiLen)
float macd = ta.ema(rsi, fastLen) - ta.ema(rsi, slowLen)
float macdSignal = ta.ema(macd, signalLen)
float macdHist = macd - macdSignal
float rsiLow = ta.lowest(rsi, stochLen)
float rsiHigh = ta.highest(rsi, stochLen)
float rawStoch = rsiHigh == rsiLow ? na : 100.0 * (rsi - rsiLow) / (rsiHigh - rsiLow)
float stochK = ta.sma(rawStoch, smoothK)
float stochD = ta.sma(stochK, smoothD)

plot(time, "TG_time_open_ms", display=display.data_window)
plot(time_close, "TG_time_close_ms", display=display.data_window)
plot(time_close - time, "TG_duration_ms", display=display.data_window)
plot(bar_index, "TG_bar_index", display=display.data_window)
plot(barstate.isconfirmed ? 1.0 : 0.0, "TG_is_confirmed", display=display.data_window)
plot(session.ismarket ? 1.0 : 0.0, "TG_is_market", display=display.data_window)
plot(session.ispremarket ? 1.0 : 0.0, "TG_is_premarket", display=display.data_window)
plot(session.ispostmarket ? 1.0 : 0.0, "TG_is_postmarket", display=display.data_window)
plot(session.isfirstbar ? 1.0 : 0.0, "TG_is_firstbar", display=display.data_window)
plot(session.islastbar ? 1.0 : 0.0, "TG_is_lastbar", display=display.data_window)
plot(session.isfirstbar_regular ? 1.0 : 0.0, "TG_is_firstbar_regular", display=display.data_window)
plot(session.islastbar_regular ? 1.0 : 0.0, "TG_is_lastbar_regular", display=display.data_window)
plot(rsi, "TG_rsi", display=display.data_window)
plot(macd, "TG_rsi_macd", display=display.data_window)
plot(macdSignal, "TG_rsi_macd_signal", display=display.data_window)
plot(macdHist, "TG_rsi_macd_hist", display=display.data_window)
plot(stochK, "TG_stoch_k", display=display.data_window)
plot(stochD, "TG_stoch_d", display=display.data_window)

var table metadata = table.new(position.top_right, 2, 11)
if barstate.islast
    table.cell(metadata, 0, 0, "probe")
    table.cell(metadata, 1, 0, "temporal-recipe-probe-v1")
    table.cell(metadata, 0, 1, "tickerid")
    table.cell(metadata, 1, 1, syminfo.tickerid)
    table.cell(metadata, 0, 2, "main_tickerid")
    table.cell(metadata, 1, 2, syminfo.main_tickerid)
    table.cell(metadata, 0, 3, "type")
    table.cell(metadata, 1, 3, syminfo.type)
    table.cell(metadata, 0, 4, "currency")
    table.cell(metadata, 1, 4, syminfo.currency)
    table.cell(metadata, 0, 5, "session")
    table.cell(metadata, 1, 5, syminfo.session)
    table.cell(metadata, 0, 6, "exchange timezone")
    table.cell(metadata, 1, 6, syminfo.timezone)
    table.cell(metadata, 0, 7, "timeframe")
    table.cell(metadata, 1, 7, timeframe.period)
    table.cell(metadata, 0, 8, "RSI / fast / slow")
    table.cell(metadata, 1, 8, str.format("{0}/{1}/{2}", rsiLen, fastLen, slowLen))
    table.cell(metadata, 0, 9, "signal / stoch")
    table.cell(metadata, 1, 9, str.format("{0}/{1}", signalLen, stochLen))
    table.cell(metadata, 0, 10, "K / D")
    table.cell(metadata, 1, 10, str.format("{0}/{1}", smoothK, smoothD))
```

- [ ] **Step 2: Write the capture runbook**

The README must require:

1. Preserve the exact observed symbol/feed; no substitution.
2. Record chart timeframe, named session, exchange timezone, manually selected chart timezone, extended-hours state and every data-modification setting.
3. For silver, classify the observed instrument as spot/CFD, concrete COMEX contract, continuous future with exact roll recipe, ETF or other.
4. Load enough history to expose the full warm-up.
5. Add the exact probe from Git, compile it and record its Git blob SHA.
6. Export chart data to a directory outside the repository.
7. Hash with `shasum -a 256 chart.csv`.
8. Complete `mastermind.temporal_chart_recipe.v1` without inferred values.
9. Use an incomplete recipe with named missing fields when exact identity is unavailable.
10. Never commit raw TradingView/vendor exports unless a rights record explicitly permits redistribution.

- [ ] **Step 3: Validate the Pine source mechanically and commit**

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine")
s = p.read_text(encoding="utf-8")
required = [
    "//@version=6", "syminfo.tickerid", "syminfo.main_tickerid",
    "syminfo.session", "syminfo.timezone", "timeframe.period",
    "TG_time_open_ms", "TG_time_close_ms", "TG_rsi_macd_hist", "TG_stoch_d",
]
missing = [item for item in required if item not in s]
for forbidden in ["strategy(", "alert(", "alertcondition(", "request.security("]:
    if forbidden in s:
        raise SystemExit(f"forbidden Pine construct: {forbidden}")
if missing:
    raise SystemExit(f"missing Pine fields: {missing}")
print("probe source contract ok")
PY
git add research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine research/signal_engine/temporal_scale/fixtures/README.md
git commit -m "research(temporal-scale): add exact TradingView recipe probe"
```

---

### Task 3: CSV integrity, column identity and bar receipts

**Files:**
- Create: `scripts/research/temporal_scale/chart_export.py`
- Test: `tests/test_temporal_scale_chart_export.py`

**Interfaces:**
- Produces `LoadedChartExport`, `sha256_file`, `resolve_column`, and `load_chart_export`.
- Consumed by parity and artifact attack.

- [ ] **Step 1: Write failing CSV tests**

Create a fixture writer with 160 deterministic closing prices and all exact probe titles. Test:

- exact SHA passes;
- changed byte fails `CSV_HASH_MISMATCH`;
- a missing plot fails `CSV_COLUMN_MISSING`;
- two columns ending in the same title fail `CSV_COLUMN_AMBIGUOUS`;
- duplicate or nonmonotone timestamps fail closed;
- duration mismatch fails;
- no-trade activity remains null rather than zero;
- bar receipts hash each normalized row.

Required assertion shape:

```python
def test_hash_mismatch_fails_before_parsing(tmp_path: Path) -> None:
    csv_path, recipe_path = write_export_fixture(tmp_path)
    csv_path.write_text(csv_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ExportError, match="CSV_HASH_MISMATCH"):
        load_chart_export(recipe_path, csv_path)
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest tests/test_temporal_scale_chart_export.py -q
```

- [ ] **Step 3: Implement exact column resolution and receipts**

```python
REQUIRED_PROBE_COLUMNS = (
    "TG_time_open_ms", "TG_time_close_ms", "TG_duration_ms", "TG_bar_index",
    "TG_is_confirmed", "TG_is_market", "TG_is_premarket", "TG_is_postmarket",
    "TG_is_firstbar", "TG_is_lastbar", "TG_is_firstbar_regular",
    "TG_is_lastbar_regular", "TG_rsi", "TG_rsi_macd",
    "TG_rsi_macd_signal", "TG_rsi_macd_hist", "TG_stoch_k", "TG_stoch_d",
)


def resolve_column(frame: pd.DataFrame, exact_title: str) -> str:
    matches = [
        str(column) for column in frame.columns
        if str(column) == exact_title or str(column).endswith(f": {exact_title}")
    ]
    if not matches:
        raise ExportError(f"CSV_COLUMN_MISSING:{exact_title}")
    if len(matches) != 1:
        raise ExportError(f"CSV_COLUMN_AMBIGUOUS:{exact_title}:{matches}")
    return matches[0]
```

`load_chart_export` must hash before parsing; normalize numeric columns explicitly; verify row count and first/last times against the recipe; require increasing unique `open_ms`; verify `time_close-time == duration`; convert flags only from `0/1`; create immutable `BarReceipt` rows; and never print or persist source rows.

- [ ] **Step 4: Confirm GREEN and commit**

```bash
python3 -m pytest tests/test_temporal_scale_chart_export.py -q
git add scripts/research/temporal_scale/chart_export.py tests/test_temporal_scale_chart_export.py
git commit -m "feat(temporal-scale): validate chart exports and bar receipts"
```

---

### Task 4: Kernel-memory signatures and unequal-time decay

**Files:**
- Create: `scripts/research/temporal_scale/kernel_memory.py`
- Test: `tests/test_temporal_scale_kernel_memory.py`

**Interfaces:**
- Produces `ema_half_life_bars`, `rma_half_life_bars`, `ema_length_for_half_life_bars`, `continuous_ema`, and `canonical_kernel_signature`.

- [ ] **Step 1: Write failing mathematical tests**

```python
import math

import numpy as np
import pandas as pd
import pytest

from scripts.research.temporal_scale.kernel_memory import (
    KernelMemoryError,
    continuous_ema,
    ema_half_life_bars,
    ema_length_for_half_life_bars,
    rma_half_life_bars,
)


def test_known_half_lives() -> None:
    assert ema_half_life_bars(14) == pytest.approx(4.843767254792992)
    assert ema_half_life_bars(60) == pytest.approx(20.79172760465854)
    assert ema_half_life_bars(5) == pytest.approx(1.7095112913514545)
    assert rma_half_life_bars(14) == pytest.approx(9.353206684999464)


def test_inverse_length_uses_deterministic_nearest_integer() -> None:
    assert ema_length_for_half_life_bars(ema_half_life_bars(14)) == 14


def test_continuous_ema_respects_unequal_increments() -> None:
    values = pd.Series([0.0, 10.0, 10.0])
    increments = pd.Series([0.0, 1.0, 2.0])
    out = continuous_ema(values, increments, tau=1.0, seed=0.0)
    expected1 = 10.0 * (1.0 - math.exp(-1.0))
    expected2 = 10.0 * (1.0 - math.exp(-2.0)) + expected1 * math.exp(-2.0)
    assert out.iloc[1] == pytest.approx(expected1)
    assert out.iloc[2] == pytest.approx(expected2)


def test_negative_increment_fails() -> None:
    with pytest.raises(KernelMemoryError, match="nonnegative"):
        continuous_ema(pd.Series([1.0]), pd.Series([-1.0]), tau=1.0)
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest tests/test_temporal_scale_kernel_memory.py -q
```

- [ ] **Step 3: Implement exact formulas**

```python
def ema_half_life_bars(length: int) -> float:
    if length < 1:
        raise KernelMemoryError("EMA length must be >= 1")
    alpha = 2.0 / (float(length) + 1.0)
    if alpha == 1.0:
        return 0.0
    return math.log(0.5) / math.log1p(-alpha)


def rma_half_life_bars(length: int) -> float:
    if length < 1:
        raise KernelMemoryError("RMA length must be >= 1")
    alpha = 1.0 / float(length)
    if alpha == 1.0:
        return 0.0
    return math.log(0.5) / math.log1p(-alpha)


def ema_length_for_half_life_bars(target: float) -> int:
    if not math.isfinite(target) or target < 0.0:
        raise KernelMemoryError("target half-life must be finite and nonnegative")
    candidates = range(1, max(2, int(math.ceil(target * 12.0)) + 8))
    return min(candidates, key=lambda n: (abs(ema_half_life_bars(n) - target), n))
```

`continuous_ema` must align indexes, reject nonfinite/negative increments, require positive finite `tau`, carry the prior state on zero increment, emit NaN on a missing value without advancing state, and use `alpha_i=1-exp(-delta_i/tau)`.

`canonical_kernel_signature` must call `engine.entry_radar.indicator_core`, record the exact finite warm-up index for each output, hash the exact indicator spec and report bar-count/clock diagnostics without fitting outcomes.

- [ ] **Step 4: Confirm GREEN and commit**

```bash
python3 -m pytest tests/test_temporal_scale_kernel_memory.py -q
git add scripts/research/temporal_scale/kernel_memory.py tests/test_temporal_scale_kernel_memory.py
git commit -m "feat(temporal-scale): model kernel memory across clocks"
```

---

### Task 5: Session-aware bars, clipping, phases and DST

**Files:**
- Create: `scripts/research/temporal_scale/session_bars.py`
- Test: `tests/test_temporal_scale_session_bars.py`

**Interfaces:**
- Produces `SessionInterval`, `BarGridSpec`, `build_session_bars`, and `generate_phase_variants`.

- [ ] **Step 1: Write failing session tests**

Cover these exact constructions with one-minute rights-safe rows:

- U.S. equity extended interval 04:00–20:00 ET and 720-minute nominal grain produces 04:00–16:00 plus clipped 16:00–20:00;
- U.S. RTH 09:30–16:00 and 240-minute grain produces 09:30–13:30 plus clipped 13:30–16:00;
- 13:00 ET early close clips the only 240-minute RTH bar at 13:00;
- an overnight 18:00–17:00 interval does not cross its 17:00–18:00 maintenance break;
- DST conversion uses `America/New_York`, not a fixed offset;
- missing minutes are counted and not forward-filled;
- phase variants remain deterministic and deduplicated.

Core assertion:

```python
def test_wmt_extended_12h_has_clipped_residual() -> None:
    rows = minute_rows("2026-08-31", "04:00", "20:00", "America/New_York")
    grid = BarGridSpec(
        grid_id="wmt-extended-720-p0",
        timezone="America/New_York",
        nominal_minutes=720,
        phase_minutes=0,
        intervals=(SessionInterval("04:00", "20:00", "extended"),),
        include_empty=False,
        close_delay_minutes=0,
    )
    _, receipts = build_session_bars(rows, recipe_id="wmt", grid=grid)
    assert [r.effective_minutes for r in receipts] == [720, 240]
    assert [r.clipped for r in receipts] == [False, True]
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest tests/test_temporal_scale_session_bars.py -q
```

- [ ] **Step 3: Implement explicit interval construction**

Use `zoneinfo.ZoneInfo`, parse `HH:MM` strictly, allow overnight intervals only when end local time is less than or equal to start, and enumerate each session interval independently. Aggregate OHLCV from rows whose timestamps fall inside each effective bucket. Never generate a price for an empty bucket; when `include_empty=True`, emit an empty receipt with null activity and no OHLC row.

A bucket’s end is:

```python
effective_end = min(bucket_start + timedelta(minutes=grid.nominal_minutes), interval_end)
```

Its confirmation time is `effective_end + close_delay_minutes`. Phase shifts move the first bucket boundary inside each interval but never cause a bar to cross a declared closed interval.

- [ ] **Step 4: Confirm GREEN and commit**

```bash
python3 -m pytest tests/test_temporal_scale_session_bars.py -q
git add scripts/research/temporal_scale/session_bars.py tests/test_temporal_scale_session_bars.py
git commit -m "feat(temporal-scale): construct session-aware bar grids"
```

---

### Task 6: Canonical indicator parity and history-truncation invariance

**Files:**
- Create: `scripts/research/temporal_scale/parity.py`
- Test: `tests/test_temporal_scale_parity.py`

**Interfaces:**
- Produces `ParityReceipt`, `canonical_indicator_frame`, `compare_indicator_parity`, and `truncation_invariance`.

- [ ] **Step 1: Write failing parity tests**

Generate a deterministic close series, create expected values by calling `engine.entry_radar.indicator_core`, and write those values into a synthetic loaded export. Test exact pass, one-value perturbation failure, no-comparable-row failure, timestamp mismatch and leading-history truncation detection.

```python
def test_exact_canonical_fixture_passes() -> None:
    loaded = loaded_export_from_canonical_fixture(n=320)
    receipt = compare_indicator_parity(loaded, tolerance=1e-10)
    assert receipt.status == "PASS"
    assert receipt.compared_rows > 0
    assert max(value for value in receipt.max_abs_error.values() if value is not None) <= 1e-10


def test_perturbed_histogram_fails() -> None:
    loaded = loaded_export_from_canonical_fixture(n=320, perturb=("TG_rsi_macd_hist", -1, 1e-4))
    receipt = compare_indicator_parity(loaded, tolerance=1e-10)
    assert receipt.status == "FAIL"
    assert any("TG_rsi_macd_hist" in item for item in receipt.failures)
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest tests/test_temporal_scale_parity.py -q
```

- [ ] **Step 3: Implement canonical parity**

`canonical_indicator_frame` must call only:

```python
rsi = indicator_core.rsi(close)
macd, signal = indicator_core.rsi_macd(close)
stoch_k, stoch_d = indicator_core.stoch_rsi_kd(close)
```

and return columns `rsi`, `rsi_macd`, `rsi_macd_signal`, `rsi_macd_hist`, `stoch_k`, and `stoch_d` indexed by chart `open_ms`.

Parity requirements:

- compare only rows finite on both sides;
- require at least one comparable row for every field;
- record the latest first-comparable timestamp across fields;
- fail when any max absolute error exceeds the frozen tolerance;
- never round before comparison.

Truncation invariance must recompute after each declared prefix drop and compare the final `comparison_tail` rows at common timestamps. It returns typed `TRUNCATION` tests and does not hide a shorter warm-up.

- [ ] **Step 4: Confirm GREEN and commit**

```bash
python3 -m pytest tests/test_temporal_scale_parity.py -q
git add scripts/research/temporal_scale/parity.py tests/test_temporal_scale_parity.py
git commit -m "feat(temporal-scale): prove indicator parity and phase stability"
```

---

### Task 7: Frozen G/A/K/D grid, TrialLedger registration and typed classification

**Files:**
- Create: `scripts/research/temporal_scale/artifact_attack.py`
- Test: `tests/test_temporal_scale_artifact_attack.py`

**Interfaces:**
- Produces `ArtifactGrid`, `default_artifact_grid`, `register_artifact_grid`, `run_artifact_attack`, and `classify_artifact_attack`.

- [ ] **Step 1: Write failing grid and guard tests**

Tests must prove:

- the default grain family is exactly one-half, two-thirds, exact, four-thirds and twice the motivating nominal minutes when integer-valued;
- anchor phases are exactly 0, 1/4, 1/2 and 3/4 of each grain;
- session alternatives come only from the recipe’s explicit allowlist;
- input ordering cannot change the grid hash;
- every generated variant is registered before diagnostics;
- the production TrialLedger path is refused;
- source AST imports no network, outcome, trade, portfolio or production signal module;
- all result authority values remain false;
- classification rules are deterministic.

```python
def test_default_grid_for_720_minutes() -> None:
    grid = default_artifact_grid(complete_recipe(timeframe_period="720"))
    assert grid.human_chart_grains_minutes == (360, 480, 720, 960, 1440)
    assert grid.memory_matched_grains_minutes == (360, 480, 720, 960, 1440)
    assert grid.anchor_phase_fractions == (0.0, 0.25, 0.5, 0.75)


def test_grid_registration_precedes_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(artifact_attack, "register_artifact_grid", lambda *a, **k: calls.append("register") or 20)
    monkeypatch.setattr(artifact_attack, "_run_diagnostics", lambda *a, **k: calls.append("run") or [])
    artifact_attack.run_artifact_attack(
        loaded_export(), lower_grain_rows=lower_rows(),
        grid=default_artifact_grid(complete_recipe()), ledger_path=tmp_path / "ledger.jsonl",
    )
    assert calls == ["register", "run"]
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest tests/test_temporal_scale_artifact_attack.py -q
```

- [ ] **Step 3: Implement the frozen grid and registration**

Serialize the grid with strict sorted JSON and SHA-256 it. Generate one explicit config record per axis/variant and call:

```python
ledger = TrialLedger(path=ledger_path, family="temporal_grain_gakd_r1")
ledger.log_grid(configs, info_cutoff=info_cutoff, source="frozen_gakd_grid")
```

Resolve both the provided ledger path and `engine.trial_ledger.DEFAULT_PATH`; reject equality.

Diagnostics are outcome-free and include:

- evaluable bar count;
- finite indicator count;
- bullish/bearish cross count;
- histogram turn count;
- total variation;
- cross/turn timestamps;
- event density per traded session;
- warm-up loss;
- clipped/empty/missing prevalence;
- timestamp displacement from the exact recipe.

The human-chart family retains bar-count lengths. The memory-matched family derives approximate lengths from the exact motivating kernel’s clock half-lives. Anchor/session variants require lower-grain rows and explicit session definitions. The standard price-MACD control is labeled a D/K implementation control and never competes to replace the owner indicator.

- [ ] **Step 4: Implement deterministic classification**

Apply rules in this order:

```python
def classify_artifact_attack(parity_status: str, tests: Sequence[ArtifactTest]) -> str:
    if parity_status == "UNRESOLVED_DATA":
        return "UNRESOLVED_DATA"
    if parity_status == "FAIL" or any(t.status == "FAIL" and t.axis in {"PARITY", "TRUNCATION"} for t in tests):
        return "ARTIFACT"
    memory = any("fixed_bar_difference_disappears_under_memory_match" in t.findings for t in tests)
    session = any("semantic_session_survives_and_arbitrary_phases_fail" in t.findings for t in tests)
    arbitrary_only = any("single_arbitrary_phase_only" in t.findings for t in tests)
    if arbitrary_only:
        return "ARTIFACT"
    if memory and session:
        return "MIXED"
    if memory:
        return "FILTER_MEMORY"
    if session:
        return "SESSION_GRAMMAR"
    return "UNRESOLVED_DATA"
```

A finding token may be emitted only by a named deterministic predicate whose metrics and threshold are stored in the same `ArtifactTest`; free-form model prose cannot drive classification.

- [ ] **Step 5: Confirm GREEN, run source guards and commit**

```bash
python3 -m pytest tests/test_temporal_scale_artifact_attack.py -q
python3 - <<'PY'
import ast
from pathlib import Path
paths = list(Path("scripts/research/temporal_scale").glob("*.py"))
forbidden = ("requests", "httpx", "urllib", "socket", "yfinance", "ccxt", "trade", "portfolio", "returns")
for path in paths:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    bad = [name for name in imports if any(token in name.lower() for token in forbidden)]
    if bad:
        raise SystemExit(f"{path}: forbidden imports {bad}")
print("research package boundary ok")
PY
git add scripts/research/temporal_scale/artifact_attack.py tests/test_temporal_scale_artifact_attack.py
git commit -m "feat(temporal-scale): add frozen GAKD artifact attack"
```

---

### Task 8: Reproducible CLI and real WMT/silver packets

**Files:**
- Create: `scripts/research/run_temporal_scale_artifact_attack.py`
- Modify: `tests/test_temporal_scale_artifact_attack.py`
- Modify: `research/signal_engine/temporal_scale/fixtures/README.md`

**Interfaces:**
- Commands: `validate-recipe`, `parity`, and `attack`.
- Writes normalized recipe, bar receipts, kernel signature, parity receipt, frozen grid, artifact result and run manifest.

- [ ] **Step 1: Add failing CLI tests**

Use `subprocess.run` with synthetic recipe/CSV helpers. Assert successful validation writes the expected files, the manifest says `network_used=false` and `production_ledger_used=false`, and a ledger path resolving to `data/trial_ledger.jsonl` is refused.

```python
def test_cli_validate_recipe(tmp_path: Path) -> None:
    recipe_path, csv_path = write_complete_fixture(tmp_path)
    output = tmp_path / "out"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/research/run_temporal_scale_artifact_attack.py",
            "validate-recipe",
            "--recipe", str(recipe_path),
            "--csv", str(csv_path),
            "--output-dir", str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["network_used"] is False
    assert manifest["production_ledger_used"] is False
```

- [ ] **Step 2: Confirm RED**

```bash
python3 -m pytest tests/test_temporal_scale_artifact_attack.py -q
```

- [ ] **Step 3: Implement the CLI**

Use `argparse` subcommands with common arguments:

```text
--recipe PATH
--csv PATH
--output-dir PATH
--ledger-path PATH
--lower-grain-csv PATH
--observation-ms INTEGER
```

Behavior:

- default ledger path is `$OUTPUT_DIR/trial_ledger.jsonl`;
- reject the production ledger path with no override flag;
- validate and hash inputs before outputs;
- write JSON atomically;
- record exact command, Python version, platform, input hashes and `git rev-parse HEAD` when available;
- malformed contracts, integrity failures and parity failure exit nonzero;
- a well-formed `UNRESOLVED_DATA` scientific result exits zero;
- never print source rows;
- print the frozen grid hash before diagnostics execute.

- [ ] **Step 4: Confirm synthetic GREEN**

```bash
python3 -m pytest tests/test_temporal_scale_*.py -q
```

- [ ] **Step 5: Capture the exact WMT packet**

Preserve the exact symbol/feed Chris observed, set the observed 12H/`720` chart and its exact extended-hours/data-modification settings, compile the committed probe, load the full history, export outside Git, complete the recipe and run:

```bash
python3 scripts/research/run_temporal_scale_artifact_attack.py parity \
  --recipe "$MMX_TEMPORAL_RESEARCH_INPUTS/wmt/recipe.json" \
  --csv "$MMX_TEMPORAL_RESEARCH_INPUTS/wmt/chart.csv" \
  --output-dir "$MMX_TEMPORAL_RESEARCH_OUTPUTS/wmt"
```

Accept only `PASS`, `FAIL`, or typed `UNRESOLVED_DATA` with hashes.

- [ ] **Step 6: Capture the exact silver packet**

Freeze whether the observed chart is XAGUSD/spot/CFD, concrete COMEX `SI`, a continuous future with exact roll semantics, `SLV`, or another product. Preserve vendor, session and data-modification settings, then run:

```bash
python3 scripts/research/run_temporal_scale_artifact_attack.py parity \
  --recipe "$MMX_TEMPORAL_RESEARCH_INPUTS/silver/recipe.json" \
  --csv "$MMX_TEMPORAL_RESEARCH_INPUTS/silver/chart.csv" \
  --output-dir "$MMX_TEMPORAL_RESEARCH_OUTPUTS/silver"
```

If identity cannot be frozen, create a valid incomplete recipe naming each missing field and return `UNRESOLVED_DATA`; do not substitute another silver product.

- [ ] **Step 7: Run Gate 2 only for parity-passing packets**

```bash
python3 scripts/research/run_temporal_scale_artifact_attack.py attack \
  --recipe "$RECIPE" \
  --csv "$CHART_CSV" \
  --lower-grain-csv "$LOWER_GRAIN_CSV" \
  --ledger-path "$OUTPUT/trial_ledger.jsonl" \
  --output-dir "$OUTPUT"
```

Preserve receipt hashes in the return handoff/PR comment. Do not commit restricted raw inputs.

- [ ] **Step 8: Commit CLI and synthetic proof**

```bash
git add scripts/research/run_temporal_scale_artifact_attack.py tests/test_temporal_scale_artifact_attack.py research/signal_engine/temporal_scale/fixtures/README.md
git commit -m "feat(temporal-scale): add reproducible artifact attack CLI"
```

---

### Task 9: Durable return, exact-head verification and hold for Sol

**Files:**
- Create: `agentos/handoffs/TEMPORAL-GRAIN-INTELLIGENCE-W1-R1.md`
- Modify: `agentos/workstreams/WS-TEMPORAL-GRAIN-INTELLIGENCE.md`

**Interfaces:**
- Produces one exact-head return with immutable hashes and typed scientific status.
- Starts no W2 or structure-scale work.

- [ ] **Step 1: Update the workstream truthfully**

Set W1 `in_progress` only after a separate START. Use `awaiting_ci` while exact-head source checks run. For a missing identity/data/rights gate, set workstream status `blocked`, keep W1 `in_progress`, and name the blocker. Set W1 `done` only after exact-head tests plus independent WMT and silver typed results are accepted by Sol. Keep W2 held behind Sol adjudication.

- [ ] **Step 2: Write the standard Agent OS handoff**

Record:

- exact operation, session, model and end reason;
- exact base and W0 merge SHA;
- every changed path;
- every verified claim with command/result;
- every unverified claim with exact verifying evidence;
- WMT and silver status independently;
- recipe/export/result hashes without raw data;
- exact PR/head/tree;
- zero-authority and production-inert effect;
- one Sol adjudication next action;
- no-rebuild and danger areas.

Use actual values only; no template token may remain.

- [ ] **Step 3: Run exact verification**

```bash
python3 -m pytest tests/test_temporal_scale_*.py -q
python3 scripts/agentos.py validate
python3 scripts/check_trial_registration.py
git diff --check
git status --short
```

Expected: temporal tests pass, Agent OS has zero errors, trial registration either recognizes the family/harness or returns the repository’s accepted not-applicable result, diff check is clean, and only authorized paths remain.

- [ ] **Step 4: Enforce the exact path ceiling**

```bash
python3 - <<'PY'
from pathlib import Path
import subprocess

authorized = {
    "research/signal_engine/temporal_scale/tradingview_temporal_recipe_probe.pine",
    "research/signal_engine/temporal_scale/fixtures/README.md",
    "scripts/research/temporal_scale/__init__.py",
    "scripts/research/temporal_scale/contracts.py",
    "scripts/research/temporal_scale/chart_export.py",
    "scripts/research/temporal_scale/kernel_memory.py",
    "scripts/research/temporal_scale/session_bars.py",
    "scripts/research/temporal_scale/parity.py",
    "scripts/research/temporal_scale/artifact_attack.py",
    "scripts/research/run_temporal_scale_artifact_attack.py",
    "tests/test_temporal_scale_contracts.py",
    "tests/test_temporal_scale_chart_export.py",
    "tests/test_temporal_scale_kernel_memory.py",
    "tests/test_temporal_scale_session_bars.py",
    "tests/test_temporal_scale_parity.py",
    "tests/test_temporal_scale_artifact_attack.py",
    "agentos/handoffs/TEMPORAL-GRAIN-INTELLIGENCE-W1-R1.md",
    "agentos/workstreams/WS-TEMPORAL-GRAIN-INTELLIGENCE.md",
}
changed = set(subprocess.check_output(
    ["git", "diff", "--name-only", "origin/main...HEAD"], text=True,
).splitlines())
extra = changed - authorized
if extra:
    raise SystemExit(f"unauthorized paths: {sorted(extra)}")
print(f"authorized paths only: {len(changed)}")
PY
```

- [ ] **Step 5: Commit and publish immutable HOLD-FOR-SOL**

```bash
git add agentos/handoffs/TEMPORAL-GRAIN-INTELLIGENCE-W1-R1.md agentos/workstreams/WS-TEMPORAL-GRAIN-INTELLIGENCE.md
git commit -m "records(temporal-scale): return GAKD artifact attack"
```

Push one branch and open/update one draft PR. Post one `RESULT / HOLD-FOR-SOL` receipt containing the operation key, exact current-main base, immutable head/tree, exact changed paths, test commands/results, independent WMT and silver statuses/hashes, overall typed classification, `authority=ZERO`, and `effect=RESEARCH_ONLY / PRODUCTION_INERT`.

Do not merge, begin W2, or call the result validated. Sol performs clause-by-clause review, current-head collision check and the explicit continuation or STOP edge.

---

## Completion Standard

This plan is complete only when a fresh reviewer can reproduce exact chart identity, CSV hash, indicator parity and G/A/K/D diagnostics from the return commands and receipts. Synthetic green CI alone is `BUILT_NOT_PROVEN`. Real packet execution plus immutable receipts is research proof, not signal validation, production proof or trading authority.

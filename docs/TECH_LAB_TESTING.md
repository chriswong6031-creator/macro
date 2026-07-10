# Tech Lab Testing Guide

How an LLM session or human tests any Tech Lab indicator programmatically.

## Overview

The Tech Lab has four testing entry points:

| Entry point | Use for |
|------------|---------|
| `pytest` test suite | Correctness and regression |
| CLI harness (`tech_lab_cli.py`) | Interactive signal exploration |
| `--sample` flag (build script) | Smoke-test the export pipeline |
| Parity fixtures | Cross-platform indicator parity with Terminal TypeScript |

---

## 1. Pytest entry points

Run all Tech Lab tests:

```sh
python -m pytest tests/test_tech_stars_metrics.py \
                 tests/test_tech_events_export.py \
                 tests/test_tech_lab_cli.py \
                 tests/test_tech_parity_fixtures.py \
                 tests/test_tech_catalog.py \
                 -q
```

Individual test modules:

| File | Tests |
|------|-------|
| `tests/test_tech_stars_metrics.py` | `compute_fire_metrics` — exact per-fire return values, horizon edge cases, empty-pos |
| `tests/test_tech_events_export.py` | tech_events schema, PIT integrity, fire dates are real bar dates |
| `tests/test_tech_lab_cli.py` | All CLI subcommands: tier stamp, era-split keys, horizon whitelist |
| `tests/test_tech_parity_fixtures.py` | Fixture determinism (byte-identical regeneration), structure, warmup nulls |
| `tests/test_tech_catalog.py` | Signal catalog: no duplicates, required keys, callable fn |
| `tests/test_tech_score.py` | Composite score builder |

---

## 2. CLI harness

The CLI reads the signal catalog and computes indicators on real or synthetic data.
All output is JSON to stdout. Exit 0 on honest nulls (zero fires is not an error).

### Signal inventory

```sh
python -m scripts.tech_lab_cli list
python -m scripts.tech_lab_cli list --family ichimoku
```

### Per-ticker state (requires data/stocks/)

```sh
python -m scripts.tech_lab_cli state NVDA
python -m scripts.tech_lab_cli state AAPL | python -m json.tool
```

### Descriptive fire profile (requires data/stocks/)

Horizons must be in {10, 21, 42, 63} trading days (TLT-R6 restriction).
Era split (pre/post 2010) is always printed (DT-R16).
n_fires and n_months are always printed (DT-R14).

```sh
# Single horizon, all tickers
python -m scripts.tech_lab_cli profile rsi14_oversold --horizon 21

# Multiple horizons, sample of universe
python -m scripts.tech_lab_cli profile golden_star_st_7_35 --horizon 10 --horizon 21 --sample 20

# Specific tickers
python -m scripts.tech_lab_cli profile ichimoku_tk_cross_up --tickers NVDA,AAPL,MSFT --horizon 21
```

Invalid horizon returns an error with the allowed list:
```sh
python -m scripts.tech_lab_cli profile rsi14_oversold --horizon 7
# → {"error": "Horizon(s) [7] are not in the allowed ladder ...", "valid_horizons": [10, 21, 42, 63]}
```

### Per-bar series tail (for chart debugging)

```sh
python -m scripts.tech_lab_cli series rsi14_oversold NVDA --tail 30
python -m scripts.tech_lab_cli series ichimoku_above_cloud AAPL --tail 50
```

---

## 3. Smoke-test the export pipeline

Run on 5 tickers into a temp directory:

```sh
python scripts/build_tech_lab_data.py --sample 5 --output-dir /tmp/te_check
ls /tmp/te_check/tech_events/
# → _index.json  AAPL.json  AMZN.json  ...
python -m json.tool /tmp/te_check/tech_events/_index.json | head -20
```

Verify a per-ticker file:

```sh
python -m json.tool /tmp/te_check/tech_events/NVDA.json | head -40
```

---

## 4. Parity fixtures

The fixtures in `tests/fixtures/tech_parity/` are the anti-drift contract between
this Python engine and the Terminal's TypeScript `indicatorMath`.

### Regenerate fixtures

```sh
python scripts/build_tech_parity_fixtures.py
```

This must produce byte-identical output to the committed files (verified by
`test_tech_parity_fixtures.py::TestFixtureDeterminism`).

### Verify fixture determinism manually

```sh
python scripts/build_tech_parity_fixtures.py --output-dir /tmp/parity_check
diff tests/fixtures/tech_parity/expected_rsi.json /tmp/parity_check/expected_rsi.json
# → (no output = byte-identical)
```

### Fixture tolerance

When porting to TypeScript: assert `abs(a - b) / max(abs(a), 1e-12) < 1e-6` for each bar.
Null entries correspond to warmup bars where the indicator is undefined.

---

## 5. House rules for test output

Per the house laws and TLT-R6:

- The word `validated` (or `已验证`) must **not** appear in any output string.
- No buy/sell threshold semantics in display output.
- Every `profile` output stamps `{"tier": "descriptive_profile"}`.
- Era split (pre/post 2010) is always in profile output.
- Horizons are restricted to `{10, 21, 42, 63}` trading days.
- Zero fires is an honest null (exit 0), not an error.

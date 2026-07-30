"""Tests for engine.neuralweb.brain_analogues (US historical-analogue retrieval).

Every case builds its OWN synthetic parquet store under tmp_path — nothing here
reads the repo's data/, so the suite is green on a fresh clone and cannot be
quietly disarmed by a substrate change that only the live store carries.

The fixture plants an exact twin of the final day at a known offset, so the
nearest-neighbour assertion pins a specific date rather than "some list came
back". Anything the plant does not fix (the 63-observation curve change) is
matched too, which is why the expected distance is exactly 0.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from engine.neuralweb import brain_analogues as ba   # noqa: E402

N_DAYS = 500
PLANT = 100          # positional index of the planted twin of the final day
LIQUIDITIES = ("expanding", "neutral", "contracting")
CYCLES = ("early", "mid", "late")

# The exact top-level key set. `query_lag_note` is the one conditional member —
# present only when the query fell back off the last row of history.
BASE_KEYS = {"schema", "asof", "coverage", "n_candidates",
             "query", "episodes", "disclaimer"}


# --------------------------------------------------------------------------- #
# Fixture store
# --------------------------------------------------------------------------- #

def _build_store(
    root: Path,
    *,
    n: int = N_DAYS,
    spx_days: int | None = None,
    break_last_n: int = 0,
) -> dict:
    """Write a synthetic store and return the metadata the tests assert against.

    spx_days     -- truncate the SPX series to this many sessions (PIT test).
    break_last_n -- NaN out a feature on the final `break_last_n` days (query-lag
                    fallback and fail-soft tests).
    """
    dates = pd.bdate_range("2019-01-02", periods=n)
    t = np.arange(n, dtype=float)

    growth = np.sin(t / 17.0)
    infl = np.cos(t / 23.0)
    s2 = 1.0 + 0.5 * np.sin(t / 11.0)
    s3 = 1.5 + 0.5 * np.cos(t / 13.0)
    vix = 18.0 + 5.0 * np.sin(t / 9.0)
    b200 = 50.0 + 20.0 * np.sin(t / 29.0)
    us10y = 3.0 + 0.4 * np.sin(t / 19.0)
    spx = 3000.0 * np.exp(np.cumsum(np.full(n, 0.0004)) + 0.02 * np.sin(t / 7.0))

    quad = np.array(["Q1" if (i // 40) % 2 == 0 else "Q3" for i in range(n)], dtype=object)
    liq = np.array([LIQUIDITIES[(i // 13) % 3] for i in range(n)], dtype=object)
    cyc = np.array([CYCLES[(i // 31) % 3] for i in range(n)], dtype=object)

    # Plant an exact twin of the final day, including the value the 63-observation
    # curve change reaches back for, so its distance to the query is exactly 0.
    for arr in (growth, infl, s2, s3, vix, b200):
        arr[PLANT] = arr[n - 1]
    s2[PLANT - ba.SPREAD_CHANGE_OBS] = s2[n - 1 - ba.SPREAD_CHANGE_OBS]
    for arr in (quad, liq, cyc):
        arr[PLANT] = arr[n - 1]

    if break_last_n:
        b200[n - break_last_n:] = np.nan

    (root / "data" / "regime").mkdir(parents=True, exist_ok=True)
    (root / "data" / "breadth").mkdir(parents=True, exist_ok=True)
    (root / "data" / "fred").mkdir(parents=True, exist_ok=True)
    (root / "data" / "yahoo").mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        {
            "growth_score": growth,
            "inflation_score": infl,
            "quad": quad,
            "liquidity": liq,
            "cycle": cyc,
            # A column the module must never surface, named like the banned key.
            "regime_confidence": np.full(n, 0.77),
        },
        index=dates,
    ).to_parquet(root / "data" / "regime" / "regime_history.parquet")

    pd.DataFrame(
        {"pct_above_200": b200, "pct_above_50": b200, "n_members": np.full(n, 500)},
        index=dates,
    ).to_parquet(root / "data" / "breadth" / "breadth.parquet")

    pd.DataFrame({"spread_2s10s": s2}, index=dates).to_parquet(
        root / "data" / "fred" / "T10Y2Y.parquet")
    pd.DataFrame({"spread_10y3m": s3}, index=dates).to_parquet(
        root / "data" / "fred" / "T10Y3M.parquet")
    pd.DataFrame({"us10y": us10y}, index=dates).to_parquet(
        root / "data" / "fred" / "DGS10.parquet")
    pd.DataFrame({"close": vix, "close_price": vix}, index=dates).to_parquet(
        root / "data" / "yahoo" / "_VIX.parquet")

    k = n if spx_days is None else min(n, spx_days)
    pd.DataFrame({"close": spx[:k], "close_price": spx[:k]},
                 index=dates[:k]).to_parquet(root / "data" / "yahoo" / "_GSPC.parquet")

    return {
        "dates": dates,
        "query_date": dates[n - 1 - break_last_n],
        "last_row_date": dates[n - 1],
        "plant_date": dates[PLANT],
    }


@pytest.fixture(autouse=True)
def _clear_cache():
    """The module cache is process-global; a stale entry would mask a real fail."""
    ba._CACHE.clear()
    yield
    ba._CACHE.clear()


@pytest.fixture
def store(tmp_path):
    meta = _build_store(tmp_path)
    meta["root"] = tmp_path
    return meta


# --------------------------------------------------------------------------- #
# 1. Happy path
# --------------------------------------------------------------------------- #

def test_happy_path_schema_and_nearest_first(store):
    out = ba.get_historical_analogues(store["root"])

    # A complete final row carries NO lag note — the note must never read as
    # decoration on a current state.
    assert set(out) == BASE_KEYS
    assert out["schema"] == "brain.analogues.v1"
    assert "error" not in out
    assert out["asof"] == str(store["query_date"].date())
    assert out["asof"] == str(store["last_row_date"].date())
    assert out["disclaimer"] == ba.DISCLAIMER
    assert out["n_candidates"] > 0
    # coverage is "<first>–<last eligible>". The first eligible day is bounded by
    # the 63-observation curve-change feature, not by the first row of history —
    # exactly the "never impute" rule the engine is built on.
    first_eligible = store["dates"][ba.SPREAD_CHANGE_OBS]
    assert out["coverage"] == (
        f"{first_eligible.date()}–{store['query_date'].date()}"
    )

    assert set(out["query"]) == {"date", "quad", "liquidity", "cycle",
                                 "growth_z", "inflation_z", "spread_2s10s",
                                 "spread_10y3m", "vix", "breadth_pct_above_200"}
    assert out["query"]["quad"] in ("Q1", "Q3")
    assert out["query"]["liquidity"] in LIQUIDITIES
    assert out["query"]["cycle"] in CYCLES

    eps = out["episodes"]
    assert 1 <= len(eps) <= 8
    for ep in eps:
        assert set(ep) == {"date", "distance", "quad", "liquidity", "cycle",
                           "spread_2s10s", "vix", "breadth_pct_above_200", "fwd"}
        assert set(ep["fwd"]) == {"spx_h5", "spx_h20", "spx_h60",
                                  "us10y_bp_h20", "vix_pts_h20"}

    dists = [ep["distance"] for ep in eps]
    assert dists == sorted(dists), "episodes must be nearest-first"

    # The planted twin is an exact match, so it must lead the list at distance 0.
    assert eps[0]["date"] == str(store["plant_date"].date())
    assert eps[0]["distance"] == 0.0
    # ...and its stored levels round-trip as the query's own.
    assert eps[0]["vix"] == out["query"]["vix"]
    assert eps[0]["breadth_pct_above_200"] == out["query"]["breadth_pct_above_200"]
    # Forward numbers are real on a full-history store.
    assert eps[0]["fwd"]["spx_h20"] is not None
    assert eps[0]["fwd"]["us10y_bp_h20"] is not None


def test_no_regime_confidence_column_leaks(store):
    """An upstream column is only ever read, never spread into the output."""
    out = ba.get_historical_analogues(store["root"])
    assert "regime_confidence" not in json.dumps(out)


# --------------------------------------------------------------------------- #
# 2. Time exclusion
# --------------------------------------------------------------------------- #

def test_time_exclusion_window(store):
    out = ba.get_historical_analogues(store["root"])
    cutoff = store["query_date"] - pd.Timedelta(days=ba.TIME_EXCLUSION_DAYS)
    for ep in out["episodes"]:
        assert pd.Timestamp(ep["date"]) <= cutoff, (
            f"{ep['date']} sits inside the {ba.TIME_EXCLUSION_DAYS}-day exclusion"
        )


# --------------------------------------------------------------------------- #
# 3. Diversity
# --------------------------------------------------------------------------- #

def test_diversity_spacing(store):
    out = ba.get_historical_analogues(store["root"])
    dates = [pd.Timestamp(ep["date"]) for ep in out["episodes"]]
    for i, a in enumerate(dates):
        for b in dates[i + 1:]:
            assert abs((a - b).days) >= ba.DIVERSITY_DAYS, (
                f"{a.date()} and {b.date()} are closer than "
                f"{ba.DIVERSITY_DAYS} calendar days"
            )


# --------------------------------------------------------------------------- #
# 4. PIT forwards — an off-history horizon is null, the episode still shows
# --------------------------------------------------------------------------- #

def test_forward_window_past_end_of_history_is_null(tmp_path):
    # SPX stops 30 sessions after the plant: h5/h20 fit, h60 runs off the end.
    meta = _build_store(tmp_path, spx_days=PLANT + 31)
    out = ba.get_historical_analogues(tmp_path)

    plant = str(meta["plant_date"].date())
    ep = next((e for e in out["episodes"] if e["date"] == plant), None)
    assert ep is not None, "episode must still appear with a truncated forward path"
    assert ep["fwd"]["spx_h5"] is not None
    assert ep["fwd"]["spx_h20"] is not None
    assert ep["fwd"]["spx_h60"] is None
    # The non-SPX horizons come from untruncated series and stay populated.
    assert ep["fwd"]["vix_pts_h20"] is not None


def test_missing_forward_series_yields_all_null_spx(tmp_path):
    _build_store(tmp_path)
    (tmp_path / "data" / "yahoo" / "_GSPC.parquet").unlink()
    out = ba.get_historical_analogues(tmp_path)
    assert out.get("episodes"), "a missing price series must not empty the list"
    for ep in out["episodes"]:
        assert ep["fwd"]["spx_h5"] is None
        assert ep["fwd"]["spx_h20"] is None
        assert ep["fwd"]["spx_h60"] is None
        assert ep["fwd"]["vix_pts_h20"] is not None


# --------------------------------------------------------------------------- #
# 5. Fail-soft
# --------------------------------------------------------------------------- #

def test_missing_store_fails_soft(tmp_path):
    out = ba.get_historical_analogues(tmp_path / "nothing_here")
    assert out == {"schema": "brain.analogues.v1",
                   "error": "analogues_unavailable",
                   "detail": out["detail"]}
    assert out["detail"]
    assert "episodes" not in out


def test_missing_feature_series_fails_soft(tmp_path):
    _build_store(tmp_path)
    (tmp_path / "data" / "fred" / "T10Y2Y.parquet").unlink()
    out = ba.get_historical_analogues(tmp_path)
    assert out["error"] == "analogues_unavailable"


def test_missing_pandas_fails_soft(store, monkeypatch):
    """The API venv may have no pandas/pyarrow at all — that is a null, not a 500."""
    import builtins
    real_import = builtins.__import__

    def _no_pandas(name, *args, **kwargs):
        if name == "pandas":
            raise ImportError("No module named 'pandas'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_pandas)
    out = ba.get_historical_analogues(store["root"])
    assert out["error"] == "analogues_unavailable"
    assert "ImportError" in out["detail"]


def test_corrupt_parquet_fails_soft(tmp_path):
    _build_store(tmp_path)
    (tmp_path / "data" / "regime" / "regime_history.parquet").write_bytes(b"not parquet")
    out = ba.get_historical_analogues(tmp_path)
    assert out["error"] == "analogues_unavailable"


# --------------------------------------------------------------------------- #
# 6. Determinism
# --------------------------------------------------------------------------- #

def test_deterministic_and_cache_isolated(store):
    a = ba.get_historical_analogues(store["root"])
    b = ba.get_historical_analogues(store["root"])
    assert a == b
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    # A caller mutating the result must not poison the cached payload.
    a["episodes"].clear()
    a["query"]["vix"] = -1
    c = ba.get_historical_analogues(store["root"])
    assert c == b


# --------------------------------------------------------------------------- #
# 7. Banned vocabulary
# --------------------------------------------------------------------------- #

def test_output_carries_no_banned_epistemics_language(store):
    out = ba.get_historical_analogues(store["root"])
    blob = json.dumps(out)
    low = blob.lower()

    assert "confidence" not in low
    assert "validated" not in low
    assert "%" not in blob

    # The disclaimer is the ONE place these words may appear, and only negated
    # ("never signals, forecasts, or probabilities"). Everything else in the
    # payload must be free of probability-style framing.
    assert "never signals, forecasts, or probabilities" in out["disclaimer"]
    body = json.dumps({k: v for k, v in out.items() if k != "disclaimer"}).lower()
    for phrase in ("probability", "probabilit", "odds", "of the time", "hit rate",
                   "base rate", "forecast", "expected return", "win rate",
                   "chance"):
        assert phrase not in body, f"probability-style phrasing leaked: {phrase}"
    # No key anywhere in the payload is named like a certainty measure.
    for ep in out["episodes"]:
        assert not any("conf" in k for k in ep)
        assert not any("conf" in k for k in ep["fwd"])
    assert not any("conf" in k for k in out["query"])
    # The disclaimer names the epistemic status in plain words.
    assert "context only" in out["disclaimer"]


def test_tool_schema_shape_and_language():
    schema = ba.ANALOGUES_TOOL_SCHEMA
    assert schema["name"] == "get_historical_analogues"
    assert schema["input_schema"]["type"] == "object"
    assert set(schema["input_schema"]["properties"]) == {"limit"}
    assert schema["input_schema"]["required"] == []
    desc = schema["description"]
    assert "DISPLAY-TIER CONTEXT ONLY" in desc
    assert "validated" not in desc.lower()
    assert "%" not in desc


# --------------------------------------------------------------------------- #
# 8. Limit clamp
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("limit,expected_max", [(1, 1), (3, 3), (8, 8), (99, 8)])
def test_limit_clamp(store, limit, expected_max):
    out = ba.get_historical_analogues(store["root"], limit=limit)
    assert len(out["episodes"]) <= expected_max
    if limit >= 3:
        assert len(out["episodes"]) >= 1


def test_limit_zero_and_garbage_clamp_to_range(store):
    assert len(ba.get_historical_analogues(store["root"], limit=0)["episodes"]) == 1
    assert len(ba.get_historical_analogues(store["root"], limit=-5)["episodes"]) == 1
    out = ba.get_historical_analogues(store["root"], limit="nope")  # type: ignore[arg-type]
    assert 1 <= len(out["episodes"]) <= 8
    # A smaller limit is a prefix of the larger one — same ranking, fewer rows.
    full = ba.get_historical_analogues(store["root"], limit=8)["episodes"]
    assert ba.get_historical_analogues(store["root"], limit=3)["episodes"] == full[:3]


# --------------------------------------------------------------------------- #
# 9. Incomplete latest row -> stamped fallback, not a dark tool
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("lag", [1, 3, ba.QUERY_LAG_MAX_ROWS - 1])
def test_incomplete_latest_day_falls_back_and_stamps_the_lag(tmp_path, lag):
    """A late-publishing input degrades to the newest COMPLETE day, disclosed.

    This is the freshness idiom, not a partial match: the query never mixes a
    half-featured final row into a full-featured comparison.
    """
    meta = _build_store(tmp_path / str(lag), break_last_n=lag)
    out = ba.get_historical_analogues(tmp_path / str(lag))

    assert "error" not in out, "a one-day publication lag must not darken the tool"
    assert set(out) == BASE_KEYS | {"query_lag_note"}

    expected = str(meta["query_date"].date())
    assert out["asof"] == expected
    assert out["query"]["date"] == expected
    assert out["asof"] != str(meta["last_row_date"].date())
    # coverage's right edge is the day actually used, not the broken final row.
    assert out["coverage"].endswith(expected)

    note = out["query_lag_note"]
    assert expected in note
    assert str(meta["last_row_date"].date()) in note
    assert "full feature set" in note

    # The retrieval itself still works off the fallback day.
    assert out["episodes"], "fallback query must still return episodes"
    cutoff = meta["query_date"] - pd.Timedelta(days=ba.TIME_EXCLUSION_DAYS)
    for ep in out["episodes"]:
        assert pd.Timestamp(ep["date"]) <= cutoff


@pytest.mark.parametrize("broken", [ba.QUERY_LAG_MAX_ROWS,
                                    ba.QUERY_LAG_MAX_ROWS + 5])
def test_no_complete_day_in_trailing_window_fails_soft(tmp_path, broken):
    """Past the bounded fallback the substrate is broken, not merely late.

    Exactly QUERY_LAG_MAX_ROWS broken rows is the first failing case: it leaves
    no complete day INSIDE the trailing window, which is the boundary the
    fallback is specified against (the case one row shorter is asserted to
    succeed in the test above).
    """
    _build_store(tmp_path / str(broken), break_last_n=broken)
    out = ba.get_historical_analogues(tmp_path / str(broken))
    assert out["error"] == "analogues_unavailable"
    assert "no complete state in the trailing" in out["detail"]
    assert "episodes" not in out
    assert "query_lag_note" not in out


def test_unknown_quad_on_latest_day_falls_back(tmp_path):
    """An unknown quad is an incomplete state, handled by the same fallback."""
    meta = _build_store(tmp_path)
    p = tmp_path / "data" / "regime" / "regime_history.parquet"
    df = pd.read_parquet(p)
    df.iloc[-1, df.columns.get_loc("quad")] = "unknown"
    df.to_parquet(p)
    out = ba.get_historical_analogues(tmp_path)
    assert "error" not in out
    assert out["asof"] == str(meta["dates"][-2].date())
    assert "query_lag_note" in out
    assert out["query"]["quad"] in ("Q1", "Q3")


def test_unknown_liquidity_is_an_ordinary_category(tmp_path):
    """China idiom: unknown liquidity/cycle stays a candidate (it just mismatches)."""
    _build_store(tmp_path)
    p = tmp_path / "data" / "regime" / "regime_history.parquet"
    df = pd.read_parquet(p)
    col = df.columns.get_loc("liquidity")
    df.iloc[:60, col] = "unknown"
    df.to_parquet(p)
    out = ba.get_historical_analogues(tmp_path)
    assert out.get("episodes"), "unknown liquidity must not empty the candidate pool"
    assert out["n_candidates"] > 0


# --------------------------------------------------------------------------- #
# Sanity: the module is import-safe with no heavy deps at module scope
# --------------------------------------------------------------------------- #

def test_module_imports_no_pandas_at_module_scope():
    src = Path(ba.__file__).read_text()
    head = src.split("# ---", 1)[0]
    assert "\nimport pandas" not in src.split("def _build", 1)[0], (
        "pandas must be imported lazily inside the build, not at module scope"
    )
    assert "import numpy" not in head

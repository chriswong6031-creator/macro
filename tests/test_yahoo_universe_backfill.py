"""The off-render yahoo universe backfill (scripts/backfill_yahoo_universe.py).

WHY THIS SUITE EXISTS — a SECOND writer into data/yahoo is a silent-poison seam.
Every hub grader prices names from data/yahoo/<T>.parquet and reads ``close``
directly off the parquet (engine/trajectory.py:66, engine/desk_grader.py:124).
``close`` is total-return (split+dividend) adjusted and ``close_price`` is
split-only, so a backfilled frame that swaps the two, drops one, reorders the
columns, or lands a tz-aware index READS AS COVERAGE and grades wrong — no
exception, no red, just a wrong number on a scorecard. Hence a schema gate with
teeth and a suite that pins them.

Pins (all network-free — the download layer is stubbed):
1. SCHEMA PARITY (the hard gate): the parquet a backfill writes is byte-identical
   to the one the collector's own path writes from the same response, carries
   ``collectors.yahoo.STORE_COLUMNS`` in order, float prices, a tz-naive sorted
   DatetimeIndex named Date — and matches the LIVE collector-produced store
   (data/yahoo/SPY.parquet) on all of it.
2. The gate REFUSES and never writes: wrong columns, wrong order, non-float
   prices, tz-aware index, unsorted/duplicate index, NaN or non-positive close.
3. Adjustment-ratio sanity: constant close/close_price SEGMENTS are the dividend
   adjustment WORKING and must not be flagged; a per-bar-varying ratio, a ratio
   above 1.0, and a tip off 1.0 are named — and none of them parks a name.
4. Priority order (current surface -> ledger-recent -> rest), unsupported symbols
   excluded, already-stored tickers excluded.
5. Cap + budget bound one run; the next run resumes where it stopped and never
   re-fetches a name that already has a parquet.
6. Three failed fetches park a name as ``fetch_failed`` — with NO death or
   delisting claim anywhere in the state file, and without touching
   lib/delisted_symbols.
7. The run annotation is a BARE line-start print (a logger-prefixed annotation is
   silently dropped by GitHub Actions).

Run: TZ=UTC .venv/bin/python -m pytest tests/test_yahoo_universe_backfill.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import yahoo as yahoo_mod  # noqa: E402
from lib import config, store  # noqa: E402
from scripts import backfill_yahoo_universe as bf  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

YF_FIELDS = ("Open", "High", "Low", "Close", "Adj Close", "Volume")


# ---------------------------------------------------------------------------
# fixtures / builders
# ---------------------------------------------------------------------------
def _bars(n: int, start: str = "2024-01-01", base: float = 100.0,
          div_steps: tuple[int, ...] = (), volume_int: bool = False) -> pd.DataFrame:
    """One symbol's yfinance-shaped bars.

    ``div_steps`` are row positions of ex-dividend dates: Adj Close is discounted
    by 1% for every dividend at or after the bar, which is exactly the shape
    yfinance serves — a ratio that is CONSTANT between dividends and 1.0 at the
    tip."""
    idx = pd.bdate_range(start, periods=n, name="Date")
    close = pd.Series(base + np.arange(n) * 0.1, index=idx)
    factor = np.ones(n)
    for pos in div_steps:
        factor[:pos] *= 0.99
    adj = close * factor
    vol = pd.Series(np.arange(1_000_000, 1_000_000 + n), index=idx)
    return pd.DataFrame({
        "Open": close - 0.5, "High": close + 0.5, "Low": close - 1.0,
        "Close": close, "Adj Close": adj,
        "Volume": vol.astype("int64" if volume_int else "float64"),
    }, index=idx)


def _yf_response(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """A ``yf.download(..., group_by='ticker')`` response: MultiIndex (symbol, field),
    union index, NaN-padded — the exact shape measured live on 2026-08-08."""
    out = {}
    for sym, f in frames.items():
        for field in YF_FIELDS:
            out[(sym, field)] = f[field]
    df = pd.DataFrame(out)
    df.columns = pd.MultiIndex.from_tuples(df.columns, names=["Ticker", "Price"])
    df.index.name = "Date"
    return df.sort_index()


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """An isolated repo-shaped tree: data/ + site/ with a hub ledger and hub.json."""
    data = tmp_path / "data"
    site = tmp_path / "site"
    (data / "yahoo").mkdir(parents=True)
    (data / "hub").mkdir(parents=True)
    (site / "intel_hub").mkdir(parents=True)
    monkeypatch.setattr(config, "data_dir", lambda: data)
    monkeypatch.setattr(config, "site_dir", lambda: site)
    return tmp_path


def _write_ledger(tree, rows: list[tuple[str, str]]) -> None:
    p = tree / "data" / "hub" / "signal_snapshots.jsonl"
    with open(p, "w") as f:
        for date_, ticker in rows:
            f.write(json.dumps({"date": date_, "t": ticker, "opp": 50.0,
                                "edge": 0.5, "stage": "early", "lean": 1}) + "\n")


def _write_hub(tree, **lists) -> None:
    payload = {k: [{"ticker": t} for t in v] for k, v in lists.items()}
    with open(tree / "site" / "intel_hub" / "hub.json", "w") as f:
        json.dump(payload, f)


def _stub_download(monkeypatch, responses, calls=None):
    """Replace the network leg. ``responses`` maps a frozenset of requested symbols
    to a response frame, an Exception to raise, or None (empty response)."""
    def fake(symbols, period):
        key = frozenset(symbols)
        if calls is not None:
            calls.append(sorted(symbols))
        out = responses.get(key, responses.get("*"))
        if isinstance(out, Exception):
            raise out
        return out
    monkeypatch.setattr(bf, "download_batch", fake)
    monkeypatch.setattr(bf.time, "sleep", lambda *_a, **_k: None)


# ---------------------------------------------------------------------------
# 1. schema parity — the hard gate
# ---------------------------------------------------------------------------
def test_backfilled_parquet_is_identical_to_the_collector_write(tree, monkeypatch):
    """Same response in, same parquet out — the backfill post-processes NOTHING.

    Both paths share ``extract_store_frame``, so this does not re-test the rename;
    what it pins is that the backfill adds no rounding, cast, reindex, reorder or
    tz step of its own on the way to disk. Any such step would show up here as a
    frame difference, and nowhere else until a grader printed a wrong number."""
    resp = _yf_response({"AAA": _bars(300, div_steps=(100, 200))})
    _write_ledger(tree, [("2026-08-01", "AAA")])
    _write_hub(tree, command=["AAA"])
    _stub_download(monkeypatch, {frozenset({"AAA"}): resp})

    bf.run(cap=5, batch_size=5, sleep_s=0, period="max")
    written = pd.read_parquet(tree / "data" / "yahoo" / "AAA.parquet")

    adapter = yahoo_mod.YahooAdapter()
    ref = adapter.validate("AAA", adapter._extract(resp, "AAA", set(), []))
    store.upsert("yahoo", "COLLECTOR_REF", ref)
    collector = pd.read_parquet(tree / "data" / "yahoo" / "COLLECTOR_REF.parquet")

    pd.testing.assert_frame_equal(written, collector)


def test_backfilled_parquet_carries_the_pinned_store_schema(tree, monkeypatch):
    resp = _yf_response({"AAA": _bars(300, div_steps=(150,))})
    _write_ledger(tree, [("2026-08-01", "AAA")])
    _write_hub(tree, command=["AAA"])
    _stub_download(monkeypatch, {frozenset({"AAA"}): resp})

    bf.run(cap=5, batch_size=5, sleep_s=0)
    df = pd.read_parquet(tree / "data" / "yahoo" / "AAA.parquet")

    assert tuple(df.columns) == yahoo_mod.STORE_COLUMNS == ("close_price", "close", "volume")
    assert df["close"].dtype.kind == "f" and df["close_price"].dtype.kind == "f"
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is None
    assert df.index.name == "Date"
    assert df.index.is_monotonic_increasing and not df.index.has_duplicates
    # `close` is the TOTAL-RETURN basis: dividend-discounted history sits BELOW
    # the split-only close. Swapping the two columns would pass every structural
    # assertion above and silently invert every grader's excess return.
    assert (df["close"] <= df["close_price"] + 1e-9).all()
    assert df["close"].iloc[-1] == pytest.approx(df["close_price"].iloc[-1])


def test_int64_volume_from_the_vendor_is_accepted_not_rejected(tree, monkeypatch):
    """yfinance serves int64 Volume for a homogeneous batch and float64 once
    NaN-padding kicks in; the collector's OWN store carries both (measured
    2026-08-08: 667 files float64, 74 int64, BRK.B among the int64 ones). A gate
    that demanded float would park real names over a vendor detail."""
    resp = _yf_response({"AAA": _bars(120, volume_int=True)})
    # single-symbol response: no NaN padding, so Volume stays int64
    flat = resp["AAA"].dropna(how="all")
    assert flat["Volume"].dtype.kind == "i"
    _write_ledger(tree, [("2026-08-01", "AAA")])
    _write_hub(tree, command=["AAA"])
    _stub_download(monkeypatch, {frozenset({"AAA"}): resp})

    rep = bf.run(cap=5, batch_size=5, sleep_s=0)
    assert rep["written"] == 1 and rep["schema_rejected"] == 0
    df = pd.read_parquet(tree / "data" / "yahoo" / "AAA.parquet")
    assert df["volume"].dtype.kind in "iu"


def test_schema_matches_the_live_collector_store():
    """Cross-check the pinned schema against a parquet the NIGHTLY COLLECTOR wrote.

    Schema only — columns, dtypes, index type/tz/name. Deliberately not values or
    dates: this file is refreshed every night, and a test that asserted about its
    contents would be asserting about today."""
    p = REPO / "data" / "yahoo" / "SPY.parquet"
    if not p.exists():
        pytest.skip("data/yahoo/SPY.parquet not in this checkout")
    spy = pd.read_parquet(p)
    assert tuple(spy.columns) == yahoo_mod.STORE_COLUMNS
    assert spy["close"].dtype.kind == "f" and spy["close_price"].dtype.kind == "f"
    assert spy["volume"].dtype.kind in "fiu"
    assert isinstance(spy.index, pd.DatetimeIndex)
    assert spy.index.tz is None and spy.index.name == "Date"
    assert bf.schema_violation(spy) is None


# ---------------------------------------------------------------------------
# 2. the gate refuses
# ---------------------------------------------------------------------------
def _good_frame() -> pd.DataFrame:
    b = _bars(120, div_steps=(60,))
    return pd.DataFrame({"close_price": b["Close"], "close": b["Adj Close"],
                         "volume": b["Volume"].astype(float)}, index=b.index)


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d.drop(columns=["close_price"]), "columns"),
    (lambda d: d[["close", "close_price", "volume"]], "columns"),
    (lambda d: d.assign(extra=1.0), "columns"),
    (lambda d: d.assign(close=d["close"].astype(str)), "non-float price"),
    (lambda d: d.set_index(d.index.tz_localize("America/New_York")), "tz-aware"),
    (lambda d: d.iloc[::-1], "not sorted"),
    (lambda d: pd.concat([d, d.iloc[[0]]]).sort_index(), "duplicate index"),
    (lambda d: d.assign(close=d["close"].mask(d.index == d.index[5])), "NaN in close"),
    (lambda d: d.assign(close=d["close"] * -1), "non-positive close"),
    (lambda d: d.iloc[:1], "row(s)"),
    (lambda d: d.iloc[:0], "empty"),
])
def test_schema_gate_refuses_every_divergence(mutate, expect):
    good = _good_frame()
    assert bf.schema_violation(good) is None
    bad = mutate(good.copy())
    reason = bf.schema_violation(bad)
    assert reason is not None and expect in reason, f"{expect!r} not in {reason!r}"


def test_a_refused_frame_is_never_written_and_is_charged_an_attempt(tree, monkeypatch, capsys):
    """The gate's TEETH, not just its verdict: a bad frame leaves NO parquet.

    Drives the real run loop with an extractor that returns a schema-violating
    frame — the one shape that would otherwise reach disk looking like coverage."""
    resp = _yf_response({"AAA": _bars(120)})
    _write_ledger(tree, [("2026-08-01", "AAA")])
    _write_hub(tree, command=["AAA"])
    _stub_download(monkeypatch, {frozenset({"AAA"}): resp})
    monkeypatch.setattr(bf, "extract_store_frame",
                        lambda sub, t, **kw: _good_frame().drop(columns=["close_price"]))

    rep = bf.run(cap=5, batch_size=5, sleep_s=0)

    assert rep["schema_rejected"] == 1 and rep["written"] == 0
    assert not (tree / "data" / "yahoo" / "AAA.parquet").exists()
    state = json.loads((tree / "data" / bf.STATE_FILE).read_text())
    assert state["pending"]["AAA"]["attempts"] == 1
    assert "schema gate" in state["pending"]["AAA"]["error"]
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("::warning title=yahoo-backfill-schema")]
    assert warn, "a refused frame must raise a line-start ::warning"


# ---------------------------------------------------------------------------
# 3. adjustment-ratio sanity (soft)
# ---------------------------------------------------------------------------
def test_constant_ratio_segments_are_the_dividend_adjustment_not_an_anomaly():
    """close/close_price steps at each ex-dividend date and is FLAT between them.
    That is the feature. Flagging it would be flagging the dual-basis store."""
    frame = _good_frame()
    ratio = frame["close"] / frame["close_price"]
    rel = (ratio.diff() / ratio.shift()).dropna().abs()
    # exactly one real step (the ex-dividend date); everything else is float noise
    assert int((rel > bf.RATIO_TOL).sum()) == 1
    rep = bf.ratio_report(frame)
    assert rep["anomalies"] == []
    assert rep["tip_ratio"] == pytest.approx(1.0)
    assert rep["step_fraction"] < bf.RATIO_STEP_FRACTION_MAX


def test_a_no_dividend_name_has_a_flat_unit_ratio_and_no_anomaly():
    frame = _good_frame()
    frame["close"] = frame["close_price"]
    rep = bf.ratio_report(frame)
    assert rep["anomalies"] == [] and rep["step_fraction"] == 0.0


def test_ratio_report_names_a_per_bar_varying_ratio():
    """The two bases are supposed to be TR and split-only, which differ only at
    ex-dividend dates. A ratio that moves on every bar is not that."""
    frame = _good_frame()
    rng = np.random.default_rng(7)
    frame["close"] = frame["close_price"] * (1 - rng.uniform(0.01, 0.05, len(frame)))
    rep = bf.ratio_report(frame)
    assert any("of bars step" in a for a in rep["anomalies"])


def test_ratio_report_names_a_ratio_above_one_and_a_tip_off_one():
    frame = _good_frame()
    frame["close"] = frame["close_price"] * 1.01
    rep = bf.ratio_report(frame)
    assert any("> 1.0" in a for a in rep["anomalies"])
    assert any("!= 1.0" in a for a in rep["anomalies"])


def test_a_ratio_anomaly_annotates_but_still_writes_the_name(tree, monkeypatch, capsys):
    """Soft by design: IBIT is a live counterexample to the <=1 and tip rules in
    the collector's own store, and the anomaly lives in a column no grader reads.
    Parking a name over it would trade real coverage for a vendor quirk."""
    b = _bars(120)
    b["Adj Close"] = b["Close"] * 1.01          # TR above split-only, tip off 1.0
    resp = _yf_response({"AAA": b})
    _write_ledger(tree, [("2026-08-01", "AAA")])
    _write_hub(tree, command=["AAA"])
    _stub_download(monkeypatch, {frozenset({"AAA"}): resp})

    rep = bf.run(cap=5, batch_size=5, sleep_s=0)

    assert rep["written"] == 1 and rep["ratio_anomalies"] == 1 and rep["parked"] == 0
    assert (tree / "data" / "yahoo" / "AAA.parquet").exists()
    lines = [ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("::warning title=yahoo-backfill-basis")]
    assert lines and "AAA" in lines[0]


# ---------------------------------------------------------------------------
# 4. the needed set + priority order
# ---------------------------------------------------------------------------
def test_priority_order_current_surface_then_recent_then_rest(tree):
    _write_ledger(tree, [
        ("2026-08-01", "CURRENT"), ("2026-08-01", "RECENT"),
        ("2026-01-05", "OLD"), ("2026-08-01", "HAVE"),
    ])
    _write_hub(tree, command=["CURRENT"], emerging=[], discovery=[])
    store.upsert("yahoo", "HAVE", _good_frame())

    queue, census = needed = bf.needed_queue({}, today=pd.Timestamp("2026-08-08").date())
    order = [t for t, _ in queue]

    assert order == ["CURRENT", "RECENT", "OLD"], order
    assert dict(queue) == {"CURRENT": 1, "RECENT": 2, "OLD": 3}
    assert "HAVE" not in order, "a ticker with a parquet is already covered"
    assert census["already_stored"] == 1 and census["missing"] == 3
    assert needed[1]["bucket_1_current"] == 1


def test_hub_only_names_join_the_needed_set(tree):
    """A name on tonight's board that the ledger has not written yet still needs a
    price series — the union is ledger OR hub, not ledger AND hub."""
    _write_ledger(tree, [("2026-08-01", "LEDGONLY")])
    _write_hub(tree, command=["HUBONLY"], discovery=["DISC"], exhausted=["EXH"])
    queue, census = bf.needed_queue({}, today=pd.Timestamp("2026-08-08").date())
    buckets = dict(queue)
    assert buckets["HUBONLY"] == 1 and buckets["DISC"] == 1
    # exhausted/catalysts are universe members but not the CURRENT surface
    assert buckets["EXH"] == 3 and buckets["LEDGONLY"] == 2
    assert census["hub_current_surface"] == 2


def test_unsupported_symbols_never_enter_the_queue(tree):
    """The ledger carries China/HK numeric board codes and parse artifacts
    (measured 886 of the 7,108 missing on 2026-08-08). Asking Yahoo for them
    spends nightly budget to learn nothing — and their exclusion is a statement
    about THIS lane's reach, never about the security."""
    _write_ledger(tree, [("2026-08-01", t) for t in
                         ("GOOD", "000100", "N/A", "()", "ASX:PEX", "IT:ETH")])
    _write_hub(tree)
    queue, census = bf.needed_queue({}, today=pd.Timestamp("2026-08-08").date())
    assert [t for t, _ in queue] == ["GOOD"]
    assert census["unsupported_symbols"] == 5
    for bad in ("000100", "N/A", "()", "ASX:PEX", "IT:ETH"):
        assert not bf.addressable(bad)
    for ok in ("GOOD", "BRK.B", "AAC-UN", "A"):
        assert bf.addressable(ok)


def test_retries_trail_never_asked_names_inside_a_bucket(tree):
    _write_ledger(tree, [("2026-08-01", "AAA"), ("2026-08-01", "BBB")])
    _write_hub(tree)
    state = {"pending": {"AAA": {"attempts": 2}}}
    queue, _ = bf.needed_queue(state, today=pd.Timestamp("2026-08-08").date())
    assert [t for t, _ in queue] == ["BBB", "AAA"]


def test_class_share_dots_become_dashes_for_the_vendor():
    """Yahoo serves US class shares with a dash (BRK.B -> BRK-B). Verified live on
    BRK.B: 7,610 bars from 1996-05-09, Berkshire class B's first session. This is
    punctuation, NOT a rename, so it does not belong in lib/ticker_aliases —
    every entry there must be justified by a live pull of a genuine vendor
    disagreement."""
    assert bf.vendor_symbol("BRK.B") == "BRK-B"
    assert bf.vendor_symbol("BF.B") == "BF-B"
    assert bf.vendor_symbol("AAPL") == "AAPL"
    assert bf.vendor_symbol("AAC-UN") == "AAC-UN"
    # the alias table still wins — it encodes real renames
    assert bf.vendor_symbol("MMC") == "MRSH"


def test_the_store_key_is_the_ledger_ticker_not_the_vendor_symbol(tree, monkeypatch):
    """Fetch under the vendor symbol, STORE under the ledger ticker: the ledger
    key is the join key every grader and page uses."""
    resp = _yf_response({"BRK-B": _bars(200)})
    _write_ledger(tree, [("2026-08-01", "BRK.B")])
    _write_hub(tree, command=["BRK.B"])
    calls: list[list[str]] = []
    _stub_download(monkeypatch, {frozenset({"BRK-B"}): resp}, calls=calls)

    rep = bf.run(cap=5, batch_size=5, sleep_s=0)

    assert calls == [["BRK-B"]]
    assert rep["written"] == 1
    assert (tree / "data" / "yahoo" / "BRK.B.parquet").exists()
    assert not (tree / "data" / "yahoo" / "BRK-B.parquet").exists()


# ---------------------------------------------------------------------------
# 5. cap, budget, resumability
# ---------------------------------------------------------------------------
def test_cap_bounds_the_run_and_the_next_run_resumes(tree, monkeypatch):
    names = [f"T{i:02d}" for i in range(10)]
    _write_ledger(tree, [("2026-08-01", t) for t in names])
    _write_hub(tree)
    responses = {frozenset(names[i:i + 3]): _yf_response(
        {t: _bars(120) for t in names[i:i + 3]}) for i in range(0, 10, 3)}
    responses[frozenset(names[9:])] = _yf_response({names[9]: _bars(120)})
    calls: list[list[str]] = []
    _stub_download(monkeypatch, responses, calls=calls)

    first = bf.run(cap=3, batch_size=3, sleep_s=0)
    assert first["planned"] == 3 and first["written"] == 3
    assert first["remaining"] == 7
    assert sorted(p.stem for p in (tree / "data" / "yahoo").glob("*.parquet")) == names[:3]

    second = bf.run(cap=3, batch_size=3, sleep_s=0)
    assert second["written"] == 3
    assert sorted(p.stem for p in (tree / "data" / "yahoo").glob("*.parquet")) == names[:6]
    # never re-requested a name that already has a parquet
    assert calls == [names[0:3], names[3:6]]

    state = json.loads((tree / "data" / bf.STATE_FILE).read_text())
    assert sorted(state["done"]) == names[:6]
    assert state["done"]["T00"]["rows"] == 120


def test_resumability_survives_a_deleted_state_file(tree, monkeypatch):
    """The needed set comes from DISK, so the state file is provenance, not
    correctness: deleting it must not re-fetch what is already stored."""
    names = ["AAA", "BBB"]
    _write_ledger(tree, [("2026-08-01", t) for t in names])
    _write_hub(tree)
    calls: list[list[str]] = []
    _stub_download(monkeypatch, {"*": _yf_response({t: _bars(120) for t in names})},
                   calls=calls)

    bf.run(cap=1, batch_size=1, sleep_s=0)
    (tree / "data" / bf.STATE_FILE).unlink()
    bf.run(cap=1, batch_size=1, sleep_s=0)

    assert calls == [["AAA"], ["BBB"]]


def test_a_corrupt_state_file_warns_and_starts_clean(tree, monkeypatch, capsys):
    (tree / "data" / bf.STATE_FILE).write_text("{not json")
    state = bf.load_state()
    assert state["done"] == {} and state["parked"] == {}
    out = capsys.readouterr().out
    assert any(ln.startswith("::warning title=yahoo-backfill::state file unreadable")
               for ln in out.splitlines())


def test_wall_clock_budget_stops_the_run_between_batches(tree, monkeypatch):
    names = [f"T{i:02d}" for i in range(6)]
    _write_ledger(tree, [("2026-08-01", t) for t in names])
    _write_hub(tree)
    _stub_download(monkeypatch, {"*": _yf_response({t: _bars(120) for t in names})})
    clock = iter([0.0, 0.0, 999.0])   # t0, batch-1 gate (pass), batch-2 gate (over)
    monkeypatch.setattr(bf.time, "monotonic", lambda: next(clock, 999.0))

    rep = bf.run(cap=6, batch_size=2, sleep_s=0, budget_s=10.0)

    assert rep["budget_exhausted"] is True
    assert rep["attempted"] == 2 and rep["planned"] == 6


def test_a_batch_transport_failure_charges_nobody_an_attempt(tree, monkeypatch):
    """A network blip is not evidence about a symbol. Charging the batch would let
    three bad nights park perfectly good names."""
    _write_ledger(tree, [("2026-08-01", "AAA"), ("2026-08-01", "BBB")])
    _write_hub(tree)
    _stub_download(monkeypatch, {"*": RuntimeError("connection reset")})

    rep = bf.run(cap=2, batch_size=2, sleep_s=0)

    assert rep["batch_errors"] == 1 and rep["attempted"] == 0 and rep["parked"] == 0
    state = json.loads((tree / "data" / bf.STATE_FILE).read_text())
    assert state["pending"] == {} and state["parked"] == {}


# ---------------------------------------------------------------------------
# 6. parking is never a death claim
# ---------------------------------------------------------------------------
def test_three_no_data_runs_park_the_name_as_fetch_failed(tree, monkeypatch):
    _write_ledger(tree, [("2026-08-01", "GHOST")])
    _write_hub(tree)
    _stub_download(monkeypatch, {"*": None})     # empty response = no data for the symbol

    for expected in (1, 2, 3):
        rep = bf.run(cap=1, batch_size=1, sleep_s=0, max_attempts=3)
        state = json.loads((tree / "data" / bf.STATE_FILE).read_text())
        if expected < 3:
            assert state["pending"]["GHOST"]["attempts"] == expected
            assert "GHOST" not in state["parked"]
            assert rep["parked"] == 0
        else:
            assert rep["parked"] == 1
            assert "GHOST" not in state.get("pending", {})

    parked = state["parked"]["GHOST"]
    assert parked["reason"] == "fetch_failed" and parked["attempts"] == 3
    assert "GHOST" in parked["error"] or "no data" in parked["error"]

    # A park is a statement about a REQUEST. Nothing in the record may claim the
    # security stopped existing — index exit, a rename nobody told us about, and a
    # non-US listing all 404 identically from here. Swept over every field EXCEPT
    # `note`, which is the disclosure itself and must carry the negation.
    lifecycle = ("delist", "dead", "died", "death", "defunct", "expired", "zombie")
    scrubbed = dict(parked)
    note = scrubbed.pop("note")
    blob = json.dumps({**state, "parked": {"GHOST": scrubbed}}).lower()
    for word in lifecycle:
        assert word not in blob, f"{word!r} in the state record"
    assert "not a delisting or death claim" in note.lower()

    # and the run stops asking once it is parked
    calls: list[list[str]] = []
    _stub_download(monkeypatch, {"*": None}, calls=calls)
    rep = bf.run(cap=1, batch_size=1, sleep_s=0, max_attempts=3)
    assert calls == [] and rep["planned"] == 0


def test_parking_never_writes_the_delisted_ledger(tree, monkeypatch):
    from lib import delisted_symbols
    before = set(delisted_symbols.tickers())
    _write_ledger(tree, [("2026-08-01", "GHOST")])
    _write_hub(tree)
    _stub_download(monkeypatch, {"*": None})
    for _ in range(3):
        bf.run(cap=1, batch_size=1, sleep_s=0, max_attempts=3)
    assert set(delisted_symbols.tickers()) == before


def test_a_park_keeps_every_row_the_name_already_had(tree, monkeypatch):
    """Parking removes a name from the FETCH QUEUE and nothing else."""
    store.upsert("yahoo", "AAA", _good_frame())
    rows = len(pd.read_parquet(tree / "data" / "yahoo" / "AAA.parquet"))
    _write_ledger(tree, [("2026-08-01", "AAA"), ("2026-08-01", "GHOST")])
    _write_hub(tree)
    _stub_download(monkeypatch, {"*": None})
    for _ in range(3):
        bf.run(cap=5, batch_size=5, sleep_s=0, max_attempts=3)
    assert len(pd.read_parquet(tree / "data" / "yahoo" / "AAA.parquet")) == rows


# ---------------------------------------------------------------------------
# 7. the annotation
# ---------------------------------------------------------------------------
def test_run_notice_is_a_bare_line_start_print(tree, monkeypatch, capsys):
    """A logger-prefixed annotation is silently DROPPED by GitHub Actions — the
    call reviews as an alarm, runs clean, and produces nothing in the summary.
    So the line must START the line (see tests/test_gh_annotation_line_start.py)."""
    _write_ledger(tree, [("2026-08-01", "AAA"), ("2026-08-01", "BBB")])
    _write_hub(tree, command=["AAA"])
    _stub_download(monkeypatch, {"*": _yf_response({"AAA": _bars(120)})})

    rep = bf.run(cap=1, batch_size=1, sleep_s=0)

    notices = [ln for ln in capsys.readouterr().out.splitlines()
               if ln.startswith("::notice title=yahoo-backfill::")]
    assert len(notices) == 1, notices
    assert notices[0] == (f"::notice title=yahoo-backfill::backfilled {rep['written']}, "
                          f"parked {rep['parked']}, remaining {rep['remaining']}")


def test_dry_run_touches_no_network_and_writes_nothing(tree, monkeypatch, capsys):
    _write_ledger(tree, [("2026-08-01", "AAA"), ("2026-08-01", "BBB")])
    _write_hub(tree, command=["AAA"])

    def explode(*_a, **_k):
        raise AssertionError("--dry-run must not touch the network")
    monkeypatch.setattr(bf, "download_batch", explode)

    rep = bf.run(cap=5, batch_size=5, sleep_s=0, dry_run=True)

    assert rep["written"] == 0 and rep["remaining"] == 2
    assert rep["plan_sample"] == ["AAA", "BBB"]
    assert list((tree / "data" / "yahoo").glob("*.parquet")) == []
    assert not (tree / "data" / bf.STATE_FILE).exists()
    assert any(ln.startswith("::notice title=yahoo-backfill::")
               for ln in capsys.readouterr().out.splitlines())


def test_cli_exits_zero_so_the_lane_can_never_red_the_night(tree, monkeypatch):
    """Additive off-render lane: a night that backfilled nothing must not fail the
    collect job. The ::notice / ::warning lines carry the outcome."""
    _write_ledger(tree, [("2026-08-01", "AAA")])
    _write_hub(tree)
    _stub_download(monkeypatch, {"*": None})
    assert bf.main(["--cap", "1", "--batch-size", "1", "--sleep", "0"]) == 0

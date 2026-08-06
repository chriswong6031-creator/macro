"""Column-grain contracts for the Stock Connect collector (collectors/base +
collectors/china_connect).

The failure mode this guards: ``detect_stale_series`` is FRAME-grain — it asks
when the frame last had ANY observation — so one live column keeps a whole series
looking healthy while its siblings are dead.  china_connect/northbound reported
fresh every night for ~2 years while ``net``/``buy``/``sell`` were entirely null
(SSE/SZSE ended daily northbound flow disclosure after 2024-08-16), because
``turnover`` kept ticking daily in the same frame.  Nothing could see it.

``detect_dark_columns`` closes that hole per column, and is PURE: ``today`` is
injected, so nothing here is asserted against the wall clock.  A retired column
must stay SILENT in its expected all-null steady state — an alarm that fires every
night for a permanent, known condition is an alarm nobody reads — and speak only
if upstream resurrects it.

Run: .venv/bin/python -m pytest tests/test_china_connect_contracts.py -q
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import collectors.base as b  # noqa: E402
from collectors.base import (  # noqa: E402
    Adapter,
    ColumnContract,
    dark_column_annotation,
    detect_dark_columns,
    run_adapter,
)
from collectors.china_connect import (  # noqa: E402
    _DAILY_DARK_DAYS,
    _NB_RETIRED,
    ChinaConnectAdapter,
    _frame_from_rows,
)

TODAY = date(2026, 8, 4)          # pinned everywhere — never the wall clock
RETIRED_ON = "2024-08-16"


def _frame(last: str, n: int = 30, col: str = "live", freq: str = "D") -> pd.DataFrame:
    """n daily rows ending on *last*, all non-null."""
    idx = pd.date_range(end=pd.Timestamp(last), periods=n, freq=freq)
    return pd.DataFrame({col: [float(i) for i in range(n)]}, index=idx)


# ---------------------------------------------------------------------------
# 1-3: live column contracts
# ---------------------------------------------------------------------------

def test_live_column_within_horizon_is_silent():
    """A column observed inside its horizon produces nothing."""
    df = _frame("2026-08-03")           # 1 day old vs pinned today
    out = detect_dark_columns("grp", "ser", df,
                              {"live": ColumnContract(max_dark_days=18)}, TODAY)
    assert out == []


def test_live_column_past_horizon_is_dark():
    """Past the horizon -> one dark entry, and its annotation starts the line."""
    df = _frame("2026-07-01")           # 34 days old vs pinned today
    out = detect_dark_columns("china_connect", "northbound", df,
                              {"live": ColumnContract(max_dark_days=18,
                                                      note="turnover posts daily")},
                              TODAY)
    assert len(out) == 1, out
    e = out[0]
    assert e["kind"] == "dark"
    assert (e["group"], e["series"], e["column"]) == ("china_connect", "northbound", "live")
    assert e["last_obs"] == "2026-07-01"
    assert e["age_days"] == 34
    assert e["max_dark_days"] == 18

    line = dark_column_annotation(e)
    assert line.startswith("::warning "), line
    assert "\n" not in line, "an annotation must be ONE line"
    assert "china_connect/northbound.live" in line
    assert "2026-07-01" in line and "34d" in line
    assert "turnover posts daily" in line
    assert "see collectors/china_connect.py" in line


def test_live_column_missing_from_frame_is_dark_with_unbounded_age():
    """A contracted column that is not in the frame at all is dark.

    last_obs/age_days are None rather than a magic number: the age is genuinely
    unbounded, and a sentinel like -1 would read as a real age to any consumer.
    """
    df = _frame("2026-08-03", col="something_else")
    out = detect_dark_columns("grp", "ser", df,
                              {"live": ColumnContract(max_dark_days=18)}, TODAY)
    assert len(out) == 1
    assert out[0]["kind"] == "dark"
    assert out[0]["last_obs"] is None and out[0]["age_days"] is None

    line = dark_column_annotation(out[0])
    assert line.startswith("::warning "), line
    assert "grp/ser.live" in line
    assert "NO non-null value" in line


def test_all_null_live_column_is_dark():
    """Present but entirely null is the same unbounded-age dark case."""
    df = _frame("2026-08-03")
    df["live"] = float("nan")
    out = detect_dark_columns("grp", "ser", df,
                              {"live": ColumnContract(max_dark_days=18)}, TODAY)
    assert len(out) == 1 and out[0]["last_obs"] is None


# ---------------------------------------------------------------------------
# 4-5: retired column contracts
# ---------------------------------------------------------------------------

def test_retired_column_all_null_after_retirement_is_silent():
    """THE steady state: a retired column must not warn every single night."""
    idx = pd.date_range("2024-06-01", "2026-08-03", freq="B")
    df = pd.DataFrame({"net": [1.0] * len(idx)}, index=idx)
    df.loc[df.index > pd.Timestamp(RETIRED_ON), "net"] = float("nan")
    out = detect_dark_columns("china_connect", "northbound", df,
                              {"net": ColumnContract(retired=RETIRED_ON)}, TODAY)
    assert out == [], "a retired column in its expected state must stay silent"


def test_retired_column_absent_from_frame_is_silent():
    """Retired AND dropped from the frame is still the expected state."""
    df = _frame("2026-08-03")
    out = detect_dark_columns("china_connect", "northbound", df,
                              {"net": ColumnContract(retired=RETIRED_ON)}, TODAY)
    assert out == []


def test_retired_column_with_a_value_after_retirement_resurrects():
    """The ONE event worth surfacing: upstream may have resumed disclosure."""
    idx = pd.DatetimeIndex(["2024-08-15", "2024-08-16", "2026-07-31"])
    df = pd.DataFrame({"net": [1.0, 2.0, 3.0]}, index=idx)
    out = detect_dark_columns("china_connect", "northbound", df,
                              {"net": ColumnContract(retired=RETIRED_ON,
                                                     note="Apr-2024 CSRC rule change")},
                              TODAY)
    assert len(out) == 1, out
    e = out[0]
    assert e["kind"] == "resurrected"
    assert e["retired"] == RETIRED_ON
    assert e["last_obs"] == "2026-07-31"

    line = dark_column_annotation(e)
    assert line.startswith("::notice "), line
    assert "\n" not in line
    assert "china_connect/northbound.net" in line
    assert RETIRED_ON in line and "2026-07-31" in line
    assert "Apr-2024 CSRC rule change" in line


def test_value_exactly_on_the_retirement_date_does_not_resurrect():
    """The retirement date itself is the LAST legitimate observation."""
    df = pd.DataFrame({"net": [1.0]}, index=pd.DatetimeIndex([RETIRED_ON]))
    out = detect_dark_columns("grp", "ser", df,
                              {"net": ColumnContract(retired=RETIRED_ON)}, TODAY)
    assert out == []


# ---------------------------------------------------------------------------
# 6: the detector is an alarm, never a gate
# ---------------------------------------------------------------------------

def test_detector_never_raises_on_junk():
    """Empty frames, object dtypes and non-datetime indexes must degrade, not crash."""
    live = {"live": ColumnContract(max_dark_days=18)}
    retired = {"net": ColumnContract(retired=RETIRED_ON)}

    assert isinstance(detect_dark_columns("g", "s", pd.DataFrame(), live, TODAY), list)
    assert detect_dark_columns("g", "s", pd.DataFrame(), retired, TODAY) == []

    junk = pd.DataFrame({"live": ["a", "b"], "net": ["x", "y"]},
                        index=pd.DatetimeIndex(["2026-08-01", "2026-08-03"]))
    assert isinstance(detect_dark_columns("g", "s", junk, live, TODAY), list)

    # a non-datetime index makes the retired-side comparison raise; it must be swallowed
    bad_index = pd.DataFrame({"net": [1.0]}, index=["not-a-date"])
    assert detect_dark_columns("g", "s", bad_index, retired, TODAY) == []

    assert detect_dark_columns("g", "s", _frame("2026-08-03"), {}, TODAY) == []


def test_column_contract_requires_exactly_one_mode():
    """A contract with both modes (or neither) is a typo that must fail loudly."""
    with pytest.raises(ValueError):
        ColumnContract()
    with pytest.raises(ValueError):
        ColumnContract(max_dark_days=18, retired=RETIRED_ON)


# ---------------------------------------------------------------------------
# 7: _frame_from_rows (pure shaping helper — no HTTP)
# ---------------------------------------------------------------------------

def _row(day: str, **kw) -> dict:
    base = {"TRADE_DATE": day, "NET_DEAL_AMT": None, "BUY_AMT": None,
            "SELL_AMT": None, "DEAL_AMT": None, "HOLD_MARKET_CAP": None}
    base.update(kw)
    return base


def test_frame_from_rows_coerces_zero_hold_mktcap_to_nan():
    """A literal 0 is an upstream non-disclosure artifact, never an observation.

    hold_mktcap is a cumulative holdings LEVEL (~19,000亿 at the Aug-2024 freeze),
    so zero is impossible. It must not reach the store: upsert merges
    new.combine_first(old), so a stored 0.0 can never be displaced by a later NaN.
    """
    out = _frame_from_rows([
        _row("2026-06-30", HOLD_MARKET_CAP=3.10237500377334e12, DEAL_AMT=100.0),
        _row("2026-07-01", HOLD_MARKET_CAP=0, DEAL_AMT=101.0),
        _row("2026-07-02", HOLD_MARKET_CAP=0.0, DEAL_AMT=102.0),
    ])
    hm = out["hold_mktcap"]
    assert hm.isna().sum() == 2, "both literal zeros must become NaN"
    assert not (hm == 0.0).any()
    # real value scaled by 1e8 into 亿元
    assert hm.loc[pd.Timestamp("2026-06-30")] == pytest.approx(31023.7500377334)


def test_frame_from_rows_drops_all_null_rows_and_sorts():
    out = _frame_from_rows([
        _row("2026-07-02", DEAL_AMT=102.0),
        _row("2026-07-03"),                       # every field null -> dropped
        _row("2026-07-01", DEAL_AMT=101.0),
    ])
    assert list(out.index) == [pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-02")]


def test_frame_from_rows_row_whose_only_value_is_a_zero_hold_is_dropped():
    """Coercion happens BEFORE dropna, so a 0-only row carries no information."""
    out = _frame_from_rows([
        _row("2026-07-01", DEAL_AMT=101.0),
        _row("2026-07-02", HOLD_MARKET_CAP=0),
    ])
    assert list(out.index) == [pd.Timestamp("2026-07-01")]


def test_frame_from_rows_omits_columns_absent_from_the_source():
    """Post-2024-08-16 northbound rows carry no NET_DEAL_AMT at all."""
    rows = [{"TRADE_DATE": "2026-07-01", "DEAL_AMT": 101.0},
            {"TRADE_DATE": "2026-07-02", "DEAL_AMT": 102.0}]
    out = _frame_from_rows(rows)
    assert "net" not in out.columns
    assert "buy" not in out.columns and "sell" not in out.columns
    assert list(out.columns) == ["turnover"]


# ---------------------------------------------------------------------------
# the declared production contracts
# ---------------------------------------------------------------------------

def test_declared_china_connect_contracts_match_the_documented_truth():
    """Pin the per-column facts: net/buy/sell died TOGETHER, turnover did not."""
    cc = ChinaConnectAdapter.column_contracts
    assert set(cc) == {"northbound", "southbound"}

    nb = cc["northbound"]
    for col in ("net", "buy", "sell"):
        assert nb[col].retired == _NB_RETIRED == "2024-08-16", col
        assert nb[col].max_dark_days is None, col
        assert nb[col].note, f"{col} contract needs a note saying what to do"
    assert nb["turnover"].max_dark_days == _DAILY_DARK_DAYS
    assert nb["turnover"].retired is None, "turnover is LIVE, not retired"
    assert nb["hold_mktcap"].max_dark_days == 120, "quarter-end-only since 2024-09"

    sb = cc["southbound"]
    assert set(sb) == {"net", "buy", "sell", "turnover", "hold_mktcap"}
    assert all(c.max_dark_days == _DAILY_DARK_DAYS and c.retired is None
               for c in sb.values()), "southbound is fully live daily"


# ---------------------------------------------------------------------------
# 8: run_adapter integration
# ---------------------------------------------------------------------------

class _Stub(Adapter):
    name = "stub_src"
    group = "stub_group"
    stale_after_days = 5
    column_contracts = {
        "leg": {
            "live": ColumnContract(max_dark_days=3, note="posts daily"),
            "net": ColumnContract(retired=RETIRED_ON, note="disclosure ended"),
        }
    }

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def fetch(self, full_history: bool = False):
        return {"leg": self._frame}


def _stub_store(monkeypatch) -> dict:
    """upsert echoes the frame; status lives in a plain dict."""
    status: dict = {}
    monkeypatch.setattr(b.store, "upsert", lambda group, name, df, **kw: df)
    monkeypatch.setattr(b.store, "read_status", lambda: status)
    monkeypatch.setattr(b.store, "write_status", lambda s: status.update(s))
    return status


def _mixed_frame(dark: bool) -> pd.DataFrame:
    """A frame that is FRESH frame-grain (so detect_stale_series stays quiet)
    while one column is optionally dark — the exact shape that hid northbound."""
    today = pd.Timestamp(b.datetime.now(b.timezone.utc).date())
    idx = pd.date_range(end=today, periods=40, freq="D")
    df = pd.DataFrame({"live": [1.0] * len(idx), "other": [2.0] * len(idx)}, index=idx)
    if dark:
        df.loc[df.index > today - pd.Timedelta(days=30), "live"] = float("nan")
    return df


def test_run_adapter_prints_a_line_start_annotation_and_writes_run_status(
        monkeypatch, capsys):
    """The frame is fresh; only the COLUMN is dark — and it must be visible."""
    status = _stub_store(monkeypatch)
    res = run_adapter(_Stub(_mixed_frame(dark=True)))

    assert res.status == "ok", res.error
    out = capsys.readouterr().out
    hits = [ln for ln in out.splitlines() if "dark-column" in ln]
    assert len(hits) == 1, out
    line = hits[0]
    # repo law: GitHub only parses a workflow command at column 0
    assert line.startswith("::"), repr(line)
    assert line.startswith("::warning title=dark-column::"), repr(line)
    assert "stub_group/leg.live" in line
    assert "posts daily" in line

    entries = status["dark_columns"]
    assert len(entries) == 1
    e = entries[0]
    assert (e["group"], e["series"], e["column"]) == ("stub_group", "leg", "live")
    assert e["kind"] == "dark" and e["detected_at"]
    assert any("dark column: leg.live" in n for n in res.notes), res.notes


def test_run_adapter_is_silent_when_every_column_is_on_contract(monkeypatch, capsys):
    """Healthy live column + retired column in its steady state = no annotation.

    This is the nightly steady state for china_connect/northbound after the
    2024-08-16 retirement: it must never print anything.
    """
    status = _stub_store(monkeypatch)
    res = run_adapter(_Stub(_mixed_frame(dark=False)))

    assert res.status == "ok", res.error
    out = capsys.readouterr().out
    assert not [ln for ln in out.splitlines() if ln.startswith("::")], out
    assert "dark_columns" not in status
    assert res.notes == []


def test_a_broken_contract_pass_cannot_fail_the_adapter(monkeypatch, capsys):
    """The alarm is bolted onto a fetch that already succeeded — it may never
    turn an 'ok' adapter into a 'failed' one."""
    _stub_store(monkeypatch)

    def boom(*a, **kw):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(b, "detect_dark_columns", boom)
    res = run_adapter(_Stub(_mixed_frame(dark=True)))
    assert res.status == "ok", f"{res.status}: {res.error}"

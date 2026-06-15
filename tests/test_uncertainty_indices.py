"""Pure-parser tests for collectors/uncertainty_indices.py (EPU + GPR daily).

Both endpoints are reachable from the sandbox, but tests stay OFFLINE: synthetic
CSV/XLSX bytes exercise the defensive column detection and the date construction.
A key invariant: the EPU frame returns TWO columns so the runner's single-column,
price-oriented outlier guard cannot quarantine legitimate (spiky) EPU prints.

Run as a plain script:  python tests/test_uncertainty_indices.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.uncertainty_indices import UncertaintyIndicesAdapter as A  # noqa: E402


# --------------------------------------------------------------------------- #
# EPU CSV parser
# --------------------------------------------------------------------------- #
def _epu_csv() -> bytes:
    # real header order: day,month,year,daily_policy_index
    rows = ["day,month,year,daily_policy_index"]
    for d in range(1, 11):
        rows.append(f"{d},1,2020,{100 + d * 10}")
    rows.append("11,1,2020,9999")              # a legitimate spike (must survive)
    return ("\n".join(rows) + "\n").encode()


def test_parse_epu_columns_and_dates():
    df = A._parse_epu(_epu_csv())
    assert list(df.columns) == ["epu", "epu_ma7"], "EPU must be 2-col (disables the outlier guard)"
    assert df.index.name == "date" and df.index.is_monotonic_increasing
    assert str(df.index.min().date()) == "2020-01-01"
    assert float(df["epu"].iloc[-1]) == 9999.0          # spike preserved, not dropped
    # MA is a trailing mean (min_periods=1) -> first value equals the level
    assert round(float(df["epu_ma7"].iloc[0]), 1) == 110.0


def test_parse_epu_column_detection_is_caseinsensitive():
    body = b"Year,Month,Day,Daily_Policy_Index\n2021,3,4,150\n2021,3,5,160\n"
    df = A._parse_epu(body)
    assert float(df["epu"].iloc[0]) == 150.0 and str(df.index[0].date()) == "2021-03-04"


def test_parse_epu_bad_columns_raises():
    try:
        A._parse_epu(b"a,b,c\n1,2,3\n")
    except ValueError:
        return
    raise AssertionError("expected ValueError on unrecognised EPU columns")


# --------------------------------------------------------------------------- #
# GPR XLSX parser (synthetic .xlsx; parser is engine-agnostic so openpyxl is fine)
# --------------------------------------------------------------------------- #
def _gpr_xlsx() -> bytes:
    df = pd.DataFrame({
        "DAY": [20260101, 20260102, 20260103],
        "N10D": [10, 11, 12],
        "GPRD": [100.0, 150.0, 200.0],
        "GPRD_ACT": [90.0, 140.0, 260.0],
        "GPRD_THREAT": [110.0, 160.0, 150.0],
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "GPRD_MA7": [100, 125, 150],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def test_parse_gpr_threat_act_split():
    df = A._parse_gpr(_gpr_xlsx())
    assert {"gpr", "gpr_threat", "gpr_act"} <= set(df.columns)
    assert "n10d" not in [c.lower() for c in df.columns] and "gprd_ma7" not in df.columns
    assert df.index.name == "date" and str(df.index[-1].date()) == "2026-01-03"
    last = df.iloc[-1]
    assert float(last["gpr"]) == 200.0
    assert float(last["gpr_act"]) == 260.0 and float(last["gpr_threat"]) == 150.0  # act-led day


def test_parse_gpr_builds_date_from_day_when_no_date_col():
    df = pd.DataFrame({"DAY": [20260601, 20260602], "GPRD": [120.0, 130.0],
                       "GPRD_THREAT": [60.0, 70.0], "GPRD_ACT": [60.0, 60.0]})
    buf = io.BytesIO(); df.to_excel(buf, index=False, engine="openpyxl")
    out = A._parse_gpr(buf.getvalue())
    assert str(out.index[0].date()) == "2026-06-01" and float(out["gpr"].iloc[1]) == 130.0


def test_parse_gpr_missing_index_raises():
    df = pd.DataFrame({"GPRD_ACT": [1.0], "GPRD_THREAT": [2.0]})  # no GPRD headline col
    buf = io.BytesIO(); df.to_excel(buf, index=False, engine="openpyxl")
    try:
        A._parse_gpr(buf.getvalue())
    except ValueError:
        return
    raise AssertionError("expected ValueError when the GPRD headline column is absent")


# --------------------------------------------------------------------------- #
# adapter shape
# --------------------------------------------------------------------------- #
def test_adapter_metadata():
    a = A()
    assert a.name == "uncertainty_indices" and a.group == "uncertainty"
    assert a.stale_after_days >= 7                       # daily but with publication lag


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")

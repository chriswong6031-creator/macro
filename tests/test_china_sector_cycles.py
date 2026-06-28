"""China Sector Cycles engine tests.

Pure-function invariants (accent palette, GS mapping, basket-series reconstruction, the
point-in-time forward log) always run. The data-dependent compute() smoke test skips
cleanly when the china_sectors plane is absent (a bare checkout) and asserts the full
output contract when it is present (CI commits the data).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from engine import china_sector_cycles as ccc
from engine import china_sector_index as csi

HAVE_DATA = csi.sw_close("801780") is not None


# --------------------------------------------------------------- pure functions ----

def test_accent_is_legible_hsl():
    a = ccc._accent(3, 31)
    assert a.startswith("hsl(") and a.endswith(")")


def test_gs_mapping_codes_are_known_sectors():
    # every GS-mapped Shenwan code must be a sector the engine actually builds
    for code in ccc._GS_BY_SW:
        assert code in ccc._SW, f"GS-mapped code {code} missing from _SW"
    # and must resolve to a real pathway key
    assert set(ccc._GS_BY_SW.values()) <= set(csi.GS_BASKETS)


def test_basket_series_reconstructs_from_chart_payload():
    dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2021-01-01", periods=400, freq="B")]
    lvl = [1000.0 * (1.0005 ** i) for i in range(400)]
    chart = {"dates": dates, "baskets": {"cn_x": lvl}}
    s = ccc._basket_series("cn_x", chart)
    assert s is not None and len(s) == 400 and (s > 0).all()
    # too-short series rejected
    short = {"dates": dates[:50], "baskets": {"cn_x": lvl[:50]}}
    assert ccc._basket_series("cn_x", short) is None
    # length-mismatch rejected
    assert ccc._basket_series("cn_x", {"dates": dates, "baskets": {"cn_x": lvl[:10]}}) is None


def test_forward_log_appends_and_dedupes(tmp_path, monkeypatch):
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    data = {"meta": {"asOf": "2026-06-26"}, "sectors": [
        {"id": "801780", "kind": "sector", "name": "Banks",
         "now": {"phase": "Trough", "pos": 7.4, "signature": {"score": 10.0}, "rs_63d": -9.1},
         "proj": {"nextTurn": "peak", "central": "2027-06"},
         "pathway": {"conditional": {"h6": {"cond_rate": 0.79, "base_rate": 0.58}},
                     "setup": {"tercile": "high"}}}], "baskets": []}
    n = ccc.append_forward_log(data)
    assert n == 1
    p = tmp_path / "china_sector_cycles" / "forward_log.parquet"
    assert p.exists()
    # re-appending the SAME date keeps the first row (point-in-time, no rewrite)
    data["sectors"][0]["now"]["phase"] = "Recovery"
    ccc.append_forward_log(data)
    df = pd.read_parquet(p)
    assert len(df) == 1 and df.iloc[0]["phase"] == "Trough"
    # a new date adds a row
    data["meta"]["asOf"] = "2026-06-27"
    ccc.append_forward_log(data)
    df = pd.read_parquet(p)
    assert len(df) == 2


# ------------------------------------------------------------ data-dependent ----

@pytest.mark.skipif(not HAVE_DATA, reason="china_sectors data plane absent")
def test_compute_contract():
    data = ccc.compute()
    assert data and data["sectors"]
    m = data["meta"]
    assert m["region"] == "china" and m["forecastPoint"] is True and m["experimental"] is True
    assert m["benchmark"] == "SHCOMP"
    assert m["n_sectors"] >= 20            # ~31 Shenwan L1 sectors
    # phases taxonomy carried through
    assert set(data["phases"]) == {"Trough", "Recovery", "Expansion", "Peak", "Downturn"}
    # every sector record has the cycle contract
    for s in data["sectors"]:
        assert s["kind"] == "sector" and s["shenwan_code"]
        assert s["price"] and s["osc"] and "turns" in s
        nw = s["now"]
        assert nw["phase"] in data["phases"] and 0 <= nw["pos"] <= 100
    # exactly the four GS-style sectors carry the evidence-gated pathway block
    pw_sectors = [s for s in data["sectors"] if s.get("pathway")]
    assert len(pw_sectors) == 4
    for s in pw_sectors:
        assert s["pathway"]["caveat_en"]
        for c in (s["pathway"].get("conditional") or {}).values():
            assert c["ci_lo"] <= c["cond_rate"] <= c["ci_hi"]
    # at least some sectors carry the washout↔euphoria signature
    assert any((s["now"].get("signature") or {}).get("score") is not None for s in data["sectors"])
    # JSON-serialisable with no NaN / Infinity
    blob = json.dumps(data, default=str)
    assert "NaN" not in blob and "Infinity" not in blob


@pytest.mark.skipif(not HAVE_DATA, reason="china_sectors data plane absent")
def test_compute_has_baskets_with_cycle_fields():
    data = ccc.compute()
    if not data.get("baskets"):
        pytest.skip("china_search basket cache absent")
    b = data["baskets"][0]
    assert b["kind"] == "basket" and b["basket_id"]
    assert b["price"] and "turns" in b and b["now"]["phase"] in data["phases"]

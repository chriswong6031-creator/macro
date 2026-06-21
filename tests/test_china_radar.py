"""China Divergence Radar — kernel + ledger contract tests (network-free where pure)."""
from __future__ import annotations

from engine import china_radar as cr
from engine import china_radar_ledger as rl


# ---- 2×2 divergence kernel (pure) ------------------------------------------ #
def test_divergence_positive_negative_inline():
    sig_up = {"dir": 1, "strength": 0.8}
    sig_dn = {"dir": -1, "strength": 0.8}
    # support improving, price lagging -> positive
    assert cr._divergence(sig_up, -5.0, -1.5)[0] == "positive"
    # support fading, price extended -> negative
    assert cr._divergence(sig_dn, 5.0, 1.5)[0] == "negative"
    # same direction -> in line (silent)
    assert cr._divergence(sig_up, 5.0, 1.5)[0] == "in_line"
    assert cr._divergence(sig_dn, -5.0, -1.5)[0] == "in_line"
    # no signal direction or no price -> in line
    assert cr._divergence({"dir": 0, "strength": 0.5}, -5.0, -1.0)[0] == "in_line"
    assert cr._divergence(sig_up, None, None)[0] == "in_line"


def test_winsor():
    assert cr._winz(9.0) == cr._WINSOR and cr._winz(-9.0) == -cr._WINSOR
    assert cr._winz(1.0) == 1.0


def test_scan_structure_and_none_safe():
    r = cr.scan()
    if r is None:
        return
    assert r["schema"] == cr.SCHEMA
    for k in ("divergences", "in_line", "n_active", "n_pairs"):
        assert k in r
    for d in r["divergences"]:
        assert d["sign"] in ("positive", "negative")
        assert d["sector"] and d["signal_key"]
        assert d["hypothesis_en"]            # active divergences carry a falsifiable hypothesis
    # active sorted by strength desc
    st = [d["strength"] for d in r["divergences"]]
    assert st == sorted(st, reverse=True)


# ---- ledger ---------------------------------------------------------------- #
def test_ledger_accrue_keep_first(tmp_path, monkeypatch):
    # redirect the ledger parquet to a temp file
    monkeypatch.setattr(rl, "_path", lambda: tmp_path / "ledger.parquet")
    scan = {"asof": "2026-06-20", "divergences": [
        {"pair": "ppi->512400.SS", "signal_key": "ppi", "sector_etf": "512400.SS",
         "sector_en": "Nonferrous", "sign": "positive", "price_rs": -8.6, "signal_value": 3.9}]}
    s1 = rl.accrue(scan)
    assert s1["n_total"] == 1 and s1["n_new"] == 1
    # same month, same pair -> keep-FIRST, no growth
    scan2 = {**scan, "asof": "2026-06-25"}
    s2 = rl.accrue(scan2)
    assert s2["n_total"] == 1 and s2["n_new"] == 0


def test_ledger_track_record_none_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(rl, "_path", lambda: tmp_path / "empty.parquet")
    assert rl.track_record() is None      # no ledger yet

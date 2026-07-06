"""China Divergence Radar — kernel + ledger contract tests (network-free where pure)."""
from __future__ import annotations

from engine import china_radar as cr
from engine import china_radar_ledger as rl


# ---- 2×2 divergence kernel (pure) ------------------------------------------ #
def test_divergence_uses_rs_z_with_deadband():
    sig_up = {"dir": 1, "strength": 0.8}
    sig_dn = {"dir": -1, "strength": 0.8}
    # support improving, price lagging (rs_z deeply negative) -> positive
    assert cr._divergence(sig_up, -5.0, -1.5)[0] == "positive"
    # support fading, price extended (rs_z positive) -> negative
    assert cr._divergence(sig_dn, 5.0, 1.5)[0] == "negative"
    # same direction -> in line (silent)
    assert cr._divergence(sig_up, 5.0, 1.5)[0] == "in_line"
    assert cr._divergence(sig_dn, -5.0, -1.5)[0] == "in_line"
    # DEADBAND: a mild rs_z (|z|<=0.3) is silent regardless of raw rel return sign
    assert cr._divergence(sig_up, -9.0, 0.1)[0] == "in_line"
    assert cr._divergence(sig_up, -9.0, -0.2)[0] == "in_line"
    # the regime-one-sidedness fix: a sector outperforming its OWN history (rs_z>0) with an
    # improving signal is NOT a positive divergence even if raw rel return is negative
    assert cr._divergence(sig_up, -1.0, 0.9)[0] == "in_line"
    # no signal direction or no rs_z -> in line
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
        assert 0 <= d["conviction100"] <= 100
        assert d["reliability"]["basis"] in ("pair", "signal_key", "unproven")
        assert "candidates" in d
    # active sorted by conviction100 desc (reliability-weighted strength)
    cs = [d["conviction100"] for d in r["divergences"]]
    assert cs == sorted(cs, reverse=True)


def test_ledger_reliability_aggregation(monkeypatch):
    from engine import china_radar_ledger as rl
    fake = {"rows": [
        {"pair": "pboc_easing->512880.SS", "signal_key": "pboc_easing", "status": "hit"},
        {"pair": "pboc_easing->512880.SS", "signal_key": "pboc_easing", "status": "hit"},
        {"pair": "pboc_easing->512880.SS", "signal_key": "pboc_easing", "status": "miss"},
        {"pair": "pmi->512400.SS", "signal_key": "pmi", "status": "open"},
    ]}
    monkeypatch.setattr(rl, "track_record", lambda: fake)
    by_pair, by_signal = cr._ledger_reliability()
    assert by_pair["pboc_easing->512880.SS"]["n_resolved"] == 3
    assert by_pair["pboc_easing->512880.SS"]["hit_rate"] == round(2 / 3, 2)
    assert by_signal["pboc_easing"]["n_resolved"] == 3
    # an 'open' (unresolved) row contributes nothing
    assert "pmi->512400.SS" not in by_pair


def test_ppi_artifact_guard(monkeypatch):
    import pandas as pd
    from lib import store
    # implausible -1.9 -> +3.9 reflation (6m range 5.8 > 5.0) must be guarded to None
    bad = pd.DataFrame({"ppi_yoy": [-1.9, -1.4, -0.9, 0.5, 2.8, 3.9]},
                       index=pd.date_range("2026-01-01", periods=6, freq="MS"))
    monkeypatch.setattr(store, "read", lambda g, n: bad if n == "ppi" else None)
    assert cr._sig_ppi() is None


# ---- ledger ---------------------------------------------------------------- #
def test_ledger_accrue_keep_first(tmp_path, monkeypatch):
    # redirect the ledger parquet to a temp file
    monkeypatch.setattr(rl, "_path", lambda: tmp_path / "ledger.parquet")
    # Lane guard: accrue() requires CN_LANE=asia (PR #1640 FIX 2)
    monkeypatch.setenv("CN_LANE", "asia")
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

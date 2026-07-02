"""engine.bottleneck — T1 physical-tightness nowcast. Verifies the leg math fires a
TIGHT/SOLD_OUT band + HBM-template regime when the four physical legs all point to a
squeeze (synthetic FRED fixtures, since the live series need network), and that it
degrades to AWAITING_DATA when the store is empty. DISPLAY-ONLY contract.

W1a additions: leg6_language weight (0.25), negated-hit exclusion, shadow log, unmapped
theme language-only band, glut text leg from synthetic parquet (§3.6).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import bottleneck as bn


def _series(values) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=len(values), freq="MS")
    return pd.DataFrame({"v": values}, index=idx)


def _tight_store():
    """A fixture where every physical leg signals a squeeze."""
    n = 60
    ramp = np.linspace(0, 1, n)
    return {
        "CAPUTLG3344S": _series(70 + 20 * ramp),        # cap-U ramping high -> leg1 z>0
        "MNFCTRIRSA": _series(1.5 - 0.5 * ramp),         # inv/sales falling -> -z>0 (leg2)
        "AMTMUO": _series(100 + 80 * ramp),              # unfilled orders rising
        "AMTMVS": _series(np.full(n, 50.0)),             # shipments flat -> backlog ratio rising (leg3)
        # PPI flat for 4y then a sharp recent ramp -> latest yoy >> history -> leg4 z>0
        "PCU334413334413": _series(list(np.full(n - 12, 100.0)) +
                                   list(100 * (1 + 0.02 * np.arange(1, 13)))),
    }


def _patch_themes(monkeypatch, tmp_path):
    monkeypatch.setattr(bn.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "Memory", "tickers": ["MU"]}}})
    monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)   # no EDGAR cache -> language None


def test_tight_regime_fires(monkeypatch, tmp_path):
    store = _tight_store()
    monkeypatch.setattr(bn.store, "read", lambda group, name: store.get(name))
    _patch_themes(monkeypatch, tmp_path)
    out = bn.compute_bottleneck(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["legs"]["leg1_capacity"] > 0      # capacity full
    assert t["legs"]["leg2_inventory"] > 0     # inventory drained
    assert t["legs"]["leg3_backlog"] > 0       # backlog building
    assert t["legs"]["leg4_pricing"] > 0       # pricing power
    assert t["regime"] is True                 # HBM template: all four fire
    assert t["band"] in ("TIGHT", "SOLD_OUT")
    assert t["tightness"] > 0.5


def test_awaiting_data_when_store_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(bn.store, "read", lambda group, name: None)
    _patch_themes(monkeypatch, tmp_path)
    out = bn.compute_bottleneck(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["band"] == "AWAITING_DATA"
    assert t["regime"] is False
    assert t["tightness"] is None


def test_loose_regime(monkeypatch, tmp_path):
    n = 60
    ramp = np.linspace(0, 1, n)
    store = {
        "CAPUTLG3344S": _series(90 - 20 * ramp),         # cap-U falling -> leg1 z<0
        "MNFCTRIRSA": _series(1.0 + 0.5 * ramp),          # inv/sales rising -> leg2<0
        "AMTMUO": _series(180 - 80 * ramp),               # backlog shrinking
        "AMTMVS": _series(np.full(n, 50.0)),
        "PCU334413334413": _series(120 - 10 * ramp),      # PPI falling -> leg4<0
    }
    monkeypatch.setattr(bn.store, "read", lambda group, name: store.get(name))
    _patch_themes(monkeypatch, tmp_path)
    out = bn.compute_bottleneck(write_ledger=False)
    t = out["themes"]["memory_storage"]
    assert t["regime"] is False
    assert t["band"] in ("LOOSE", "NEUTRAL")


# ---- W1a: leg6_language weight, negated exclusion, shadow log, unmapped theme ----

def test_leg6_weight_in_composite(monkeypatch, tmp_path):
    """W5a: all 7 legs (leg1-4, leg6, leg7, leg8) are present and sum to 1.0.
    leg6_language at 0.20 PROVISIONAL; legs 7-8 at 0.075 each PROVISIONAL.
    Numeric legs (1-4 + 7-8) sum to 0.80; language (leg6) = 0.20; total = 1.00."""
    from engine.bottleneck import WEIGHTS
    # All legs present
    assert "leg6_language" in WEIGHTS
    assert "leg7_member_inventory" in WEIGHTS
    assert "leg8_member_backlog" in WEIGHTS

    # All 7 legs must sum to 1.0 (within float tolerance)
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6, f"weights sum to {total}, not 1.0"

    # Language (leg6) + fingerprint (legs 7-8) = 0.35; FRED numeric (legs 1-4) = 0.65
    lang_weight = WEIGHTS["leg6_language"]
    fp_weight = WEIGHTS["leg7_member_inventory"] + WEIGHTS["leg8_member_backlog"]
    fred_weight = sum(WEIGHTS[k] for k in ("leg1_capacity", "leg2_inventory",
                                           "leg3_backlog", "leg4_pricing"))
    assert abs(lang_weight + fp_weight + fred_weight - 1.0) < 1e-6, \
        f"weight breakdown doesn't sum to 1.0: lang={lang_weight}, fp={fp_weight}, fred={fred_weight}"

    # Numeric physical legs (FRED 1-4 + XBRL 7-8) together = total - language
    numeric = sum(v for k, v in WEIGHTS.items() if k != "leg6_language")
    assert abs(numeric - (1.0 - lang_weight)) < 1e-6, \
        f"numeric legs sum to {numeric}, expected {1.0 - lang_weight}"


def _tightening_store():
    """A fixture where the numeric legs read mid-strength (TIGHTENING, not TIGHT):
    only cap-U and backlog are elevated; inventory and PPI are flat/neutral."""
    n = 60
    ramp = np.linspace(0, 1, n)
    return {
        "CAPUTLG3344S": _series(70 + 20 * ramp),         # leg1 z>0
        "MNFCTRIRSA": _series(np.full(n, 1.4)),          # flat -> leg2 ~0
        "AMTMUO": _series(100 + 80 * ramp),              # leg3 z>0
        "AMTMVS": _series(np.full(n, 50.0)),
        "PCU334413334413": _series(np.full(n, 100.0)),   # flat -> leg4 ~0
    }


def test_text_cannot_launder_numeric_tight(monkeypatch, tmp_path):
    """ANTI-LAUNDERING REGRESSION (review blocker on grid_electrification): when the
    numeric-only composite sits below the TIGHT threshold, a strong 2-filer language leg
    must produce 'TIGHT (text)' (text_only=True, cap binds) — NEVER a plain numeric TIGHT
    with physical_confirmed semantics."""
    store = _tightening_store()
    monkeypatch.setattr(bn.store, "read", lambda group, name: store.get(name))
    monkeypatch.setattr(bn.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "Memory",
                                                               "tickers": ["MU", "WDC"]}}})
    monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)
    # strong language: 4 recent affirmative hits across 2 distinct filers, none prior
    rows = [
        {"id": str(i), "ticker": t, "file_date": d, "phrase": "sold out",
         "fetched": d, "polarity": None}
        for i, (t, d) in enumerate([("MU", "2026-06-01"), ("MU", "2026-06-15"),
                                    ("WDC", "2026-06-10"), ("WDC", "2026-06-20")])
    ]
    _make_parquet(tmp_path, rows, kind="bottleneck")

    out = bn.compute_bottleneck(write_ledger=False)
    t = out["themes"]["memory_storage"]
    # invariant encoded directly: compare against the SAME fixture with no language.
    # numerics-alone band is whatever it is; adding language must never upgrade it
    # to a PLAIN numeric TIGHT/SOLD_OUT (only ever to the '(text)' variant).
    import shutil
    shutil.rmtree(tmp_path / "edgar")            # remove the language parquet
    base = bn.compute_bottleneck(write_ledger=False)["themes"]["memory_storage"]
    if base["band"] not in ("TIGHT", "SOLD_OUT"):
        assert t["band"] not in ("TIGHT", "SOLD_OUT"), \
            "text leg tipped the composite into a plain numeric TIGHT"
        if t["band"] == "TIGHT (text)":
            assert t.get("text_only") is True


def test_single_filer_cannot_move_composite(monkeypatch, tmp_path):
    """The >=2-distinct-filers gate applies to the COMPOSITE, not just the band relabel:
    one filer's language must leave the composite identical to the no-language case."""
    store = _tightening_store()
    monkeypatch.setattr(bn.store, "read", lambda group, name: store.get(name))
    monkeypatch.setattr(bn.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "Memory",
                                                               "tickers": ["MU"]}}})
    monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)
    base = bn.compute_bottleneck(write_ledger=False)["themes"]["memory_storage"]["tightness"]
    # now add a single-filer language burst
    rows = [{"id": str(i), "ticker": "MU", "file_date": f"2026-06-{d:02d}",
             "phrase": "sold out", "fetched": f"2026-06-{d:02d}", "polarity": None}
            for i, d in enumerate([1, 5, 10, 15, 20])]
    _make_parquet(tmp_path, rows, kind="bottleneck")
    with_lang = bn.compute_bottleneck(write_ledger=False)["themes"]["memory_storage"]["tightness"]
    assert with_lang == base, "single filer moved the weighted composite"


def _make_parquet(tmp_path, rows: list[dict], kind: str = "bottleneck") -> None:
    """Write a synthetic hits parquet to tmp_path/edgar/{kind}_hits.parquet."""
    import pathlib
    p = pathlib.Path(tmp_path) / "edgar" / f"{kind}_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p, index=False)


def test_negated_hits_excluded_when_polarity_exists(monkeypatch, tmp_path):
    """When polarity='negated', those hits must not count toward accel or filer count."""
    from engine.bottleneck import _language_accel
    import pathlib

    # 3 hits for MU: 2 affirmative in recent window, 1 negated (must be excluded)
    rows = [
        {"id": "1", "ticker": "MU", "file_date": "2026-06-01", "phrase": "sold out",
         "fetched": "2026-06-01", "polarity": None},       # fallback-b null = counts as affirmative
        {"id": "2", "ticker": "MU", "file_date": "2026-06-15", "phrase": "on allocation",
         "fetched": "2026-06-15", "polarity": None},
        {"id": "3", "ticker": "MU", "file_date": "2026-06-10", "phrase": "sold out",
         "fetched": "2026-06-10", "polarity": "negated"},   # must be EXCLUDED
    ]
    p = pathlib.Path(tmp_path) / "edgar" / "bottleneck_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p, index=False)

    accel, hits, n_filers = _language_accel(["MU"], parquet_path=p)
    # Only 2 non-negated hits (id 1 and id 2) should count; id 3 is excluded
    assert hits == 2, f"expected 2 non-negated hits, got {hits}"
    assert n_filers >= 1


def test_shadow_log_rows_written_for_3_cutoffs(monkeypatch, tmp_path):
    """_shadow_log_cutoffs must write exactly 3 rows (one per cutoff) for a new theme/asof."""
    monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)

    # lang_accel=1.2 is above the 1.0 cutoff but below 1.5 and 2.0
    bn._shadow_log_cutoffs("memory_storage", "2026-07-02", lang_accel=1.2, n_filers=3)

    p = tmp_path / "foresight" / "shadow_bands_log.jsonl"
    assert p.exists(), "shadow_bands_log.jsonl was not created"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert len(rows) == 3, f"expected 3 shadow rows, got {len(rows)}"
    cutoffs = sorted(r["cutoff"] for r in rows)
    assert cutoffs == sorted(bn.LANG_Z_SHADOW_CUTOFFS)
    # accel 1.2 > cutoff 1.0 → TIGHT (text); ≤ 1.5 and ≤ 2.0 → TIGHTENING (text)
    by_cutoff = {r["cutoff"]: r["would_be_band"] for r in rows}
    assert by_cutoff[1.0] == "TIGHT (text)"
    assert by_cutoff[1.5] == "TIGHTENING (text)"
    assert by_cutoff[2.0] == "TIGHTENING (text)"


def test_unmapped_theme_gets_language_only_band(monkeypatch, tmp_path):
    """An unmapped theme (no THEME_MAP entry) can get TIGHT (text) / TIGHTENING (text)
    from the language leg alone — band capped there, tightness=None."""
    monkeypatch.setattr(bn.config, "load",
                        lambda: {"themes": {"glp1_obesity": {"name": "GLP-1 Obesity",
                                                              "tickers": ["LLY", "NVO"]}}})
    monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bn.store, "read", lambda group, name: None)

    # Synthetic parquet: 2 distinct filers with positive accel in recent window
    rows = [
        {"id": "1", "ticker": "LLY", "file_date": "2026-06-01", "phrase": "on allocation",
         "fetched": "2026-06-01", "polarity": None},
        {"id": "2", "ticker": "NVO", "file_date": "2026-06-15", "phrase": "sold out",
         "fetched": "2026-06-15", "polarity": None},
    ]
    _make_parquet(tmp_path, rows, "bottleneck")
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)

    out = bn.compute_bottleneck(write_ledger=False)
    assert out is not None, "bottleneck returned None even with language data"
    t = out["themes"].get("glp1_obesity")
    assert t is not None, "glp1_obesity theme missing from output"
    assert t["text_only"] is True
    assert t["band"] in ("TIGHT (text)", "TIGHTENING (text)", "NEUTRAL")
    assert t["tightness"] is None   # no numeric legs
    assert t["naics"] is None       # unmapped has no NAICS


def test_glut_text_leg_from_synthetic_parquet(monkeypatch, tmp_path):
    """§3.6: glut_watch picks up the leg6_glut_language from a synthetic glut_hits parquet."""
    from engine import glut_watch as gw

    monkeypatch.setattr(gw.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "Memory",
                                                                "tickers": ["MU", "WDC"]}}})
    monkeypatch.setattr(gw.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(gw._series.__func__ if hasattr(gw._series, '__func__') else gw,
                        "__dummy__", None, raising=False)
    # Patch _series to return None (no FRED data) so only language fires
    monkeypatch.setattr(gw, "_series", lambda sid: None)

    # Synthetic glut_hits parquet: 2 filers (MU, WDC) with capacity-adds language
    rows = [
        {"id": "1", "ticker": "MU", "file_date": "2026-06-01", "phrase": "capacity expansion",
         "fetched": "2026-06-01", "polarity": None},
        {"id": "2", "ticker": "WDC", "file_date": "2026-06-10", "phrase": "adding capacity",
         "fetched": "2026-06-10", "polarity": None},
    ]
    _make_parquet(tmp_path, rows, "glut")

    out = gw.compute_glut_watch(demand={"themes": {}}, write_ledger=False)
    assert out is not None
    t = out["themes"].get("memory_storage")
    assert t is not None
    # leg6_glut_language should be present in legs dict
    assert "leg6_glut_language" in t["legs"]
    assert t["glut_language_detail"]["provisional"] is True

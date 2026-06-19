"""International dashboard expansion — Australia + India markets, multi-fund
universe deepening (UK FTSE 100 + 250), and the periodicity-aware CPI handling
that the new markets exposed.

Pure unit tests: config shape, the universe fund-iteration, and the CPI YoY
transform — no network. The data-quality bug these guard: a quarterly CPI index
(Australia) computed with a 12-step YoY would report a ~3-year change, and a long
1957-base index (India) whose FULL-history median sits below the index threshold
would be mis-read as an already-YoY rate (showing ~150 "percent").
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.intl_universe import IntlUniverseAdapter  # noqa: E402
from engine import intl_inputs  # noqa: E402
from lib import config  # noqa: E402


# -- config shape ------------------------------------------------------------
def test_new_markets_present_and_well_formed():
    countries = config.load()["intl"]["countries"]
    for cc in ("IN", "AU"):
        assert cc in countries, f"{cc} missing from intl.countries"
        c = countries[cc]
        for key in ("name", "name_zh", "flag", "region", "index", "fx", "ucits", "fred"):
            assert c.get(key), f"{cc}.{key} missing/empty"
        u = c["ucits"]
        assert {"product_id", "file_name", "suffix", "slug"} <= set(u), f"{cc}.ucits incomplete"
    # India 10y comes from the India-specific FRED id (no OECD IRLTLT01IN series exists)
    assert countries["IN"]["fred"]["yield_10y"] == "INDIRLTLT01STM"
    # Australia is a fuller pole (rates + labour + output)
    assert {"yield_10y", "short_3m", "unemployment", "gdp"} <= set(countries["AU"]["fred"])


def test_uk_has_extra_ftse250_fund():
    gb = config.load()["intl"]["countries"]["GB"]
    extra = gb.get("ucits_extra") or []
    assert any(u.get("file_name") == "MIDD" for u in extra), "FTSE 250 (MIDD) extra fund missing"
    for u in extra:
        assert {"product_id", "file_name", "suffix", "slug"} <= set(u)


# -- multi-fund universe assembly --------------------------------------------
def test_all_members_iterates_primary_plus_extra(monkeypatch):
    """_all_members must pull the primary ucits AND every ucits_extra fund."""
    called: list[tuple[str, str]] = []

    def fake_fetch(self, cc, c, u):  # noqa: ANN001
        called.append((cc, u["file_name"]))
        return pd.DataFrame([{"ticker": u["file_name"], "name": u["file_name"],
                              "sector": "Financials", "country": cc, "flag": c["flag"],
                              "market": c["name"], "weight": 1.0}])

    monkeypatch.setattr(IntlUniverseAdapter, "_fetch_holdings", fake_fetch)
    members = IntlUniverseAdapter()._all_members()

    funds = {fn for _, fn in called}
    assert {"ISF", "MIDD"} <= funds, "UK must contribute both FTSE 100 (ISF) and FTSE 250 (MIDD)"
    assert {"SAUS", "NDIA"} <= funds, "Australia (SAUS) + India (NDIA) funds must be fetched"
    # GB fetched twice (primary + extra); each resulting ticker is in the pooled index
    assert [fn for cc, fn in called if cc == "GB"] == ["ISF", "MIDD"]
    assert "MIDD" in members.index and "ISF" in members.index


# -- periodicity-aware CPI ----------------------------------------------------
def _closes(cc: str) -> pd.DataFrame:
    c = config.load()["intl"]["countries"][cc]
    idx = pd.date_range("2015-01-01", periods=2200, freq="B")
    return pd.DataFrame({c["index"]: np.linspace(5000, 8000, len(idx)),
                         c["fx"]: np.linspace(0.7, 0.7, len(idx))}, index=idx)


def test_quarterly_cpi_index_uses_4_step_yoy():
    """Australia's CPI is a QUARTERLY index — YoY must step 4 quarters, not 12
    (12 would report a ~3-year change). Index detected via recent level (~108>40)."""
    q = pd.date_range("2015-03-31", periods=44, freq="QE")
    cpi_index = pd.Series(100.0 * (1.025 ** (np.arange(44) / 4.0)), index=q)  # ~2.5%/yr
    macro = pd.DataFrame({"AU_cpi_yoy": cpi_index})
    f = intl_inputs.country_frame("AU", closes=_closes("AU"), macro=macro)
    cpi = f["cpi_yoy"].dropna()
    assert not cpi.empty
    assert 2.0 < float(cpi.iloc[-1]) < 3.0, "quarterly YoY ~2.5%, not the 3-yr (~7.7%) nor raw index"


def test_long_history_index_detected_via_recent_level():
    """India's CPI is a long 2010=100 index back to ~1957: its FULL-history median
    sits below 40, so the OLD median>40 test mis-read it as an already-YoY rate
    (showing ~150 'percent'). Recent-window detection fixes it."""
    m = pd.date_range("1957-01-31", periods=828, freq="ME")
    years = 1957 + np.arange(828) / 12.0
    cpi_index = pd.Series(100.0 * (1.06 ** (years - 2010)), index=m)  # exp, 2010=100, ~6%/yr
    assert float(cpi_index.median()) < 40, "fixture must reproduce the low full-history median"
    assert float(cpi_index.tail(24).median()) > 40, "recent level must look like an index"
    macro = pd.DataFrame({"IN_cpi_yoy": cpi_index})
    f = intl_inputs.country_frame("IN", closes=_closes("IN"), macro=macro)
    cpi = f["cpi_yoy"].dropna()
    assert not cpi.empty
    assert 4.0 < float(cpi.iloc[-1]) < 8.0, "detected as INDEX -> ~6% YoY, not the raw ~level"


def test_yoy_percent_series_passes_through():
    """A series already in YoY % (recent values ~0-15) must NOT be diff'd again."""
    m = pd.date_range("2016-01-31", periods=120, freq="ME")
    cpi_pct = pd.Series(3.0 + np.sin(np.arange(120) / 6.0), index=m)  # ~2-4%
    macro = pd.DataFrame({"GB_cpi_yoy": cpi_pct})
    f = intl_inputs.country_frame("GB", closes=_closes("GB"), macro=macro)
    cpi = f["cpi_yoy"].dropna()
    assert not cpi.empty
    assert 1.0 < float(cpi.iloc[-1]) < 5.0, "YoY % series passes through unchanged"

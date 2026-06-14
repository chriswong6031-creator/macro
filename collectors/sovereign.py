"""Foreign sovereign-yield collector — Bonds dashboard Phase 5.

Daily euro-area + Japan government yields, free/official, for the sovereign
global-risk pillar (research/BOND_HEALTH_DASHBOARD.md §5):

  • ECB Data Portal yield curve (data-api.ecb.europa.eu/service/data/YC) — euro-area
    AAA-rated and ALL-government spot yields, daily since 2004. The ALL-minus-AAA
    10y spread is a clean, official, daily proxy for BTP-Bund-style periphery
    FRAGMENTATION (AAA ≈ Germany/Netherlands core; ALL includes Italy/Spain
    periphery). AAA 10y doubles as the Bund core safe-rate read.
  • Japan MoF (jgbcm_all.csv) — the full JGB curve, Shift-JIS encoded with
    Japanese-era dates (S/H/R = Showa/Heisei/Reiwa, history from 1974). The 2s10s
    captures the post-YCC normalization steepening.

Resilient: a JGB parse failure still returns the ECB legs (and vice-versa).
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_ERA = {"S": 1925, "H": 1988, "R": 2018}   # Showa/Heisei/Reiwa base year (era yr + base = Western)
_UA = "Mozilla/5.0 (macro-dashboard research)"


def _jp_date(s) -> pd.Timestamp:
    """'R8.5.29' -> 2026-05-29 (Reiwa 8). NaT on anything unparseable."""
    s = str(s).strip()
    if len(s) < 2 or s[0] not in _ERA:
        return pd.NaT
    try:
        y, m, d = s[1:].split(".")
        return pd.Timestamp(_ERA[s[0]] + int(y), int(m), int(d))
    except Exception:  # noqa: BLE001
        return pd.NaT


class SovereignAdapter(Adapter):
    name = "sovereign"
    group = "sovereign"
    stale_after_days = 7   # official daily series, tolerate a few business days' lag

    def __init__(self) -> None:
        self.cfg = config.load()["sovereign"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        out.update(self._ecb())                       # ECB is the robust core
        try:
            out.update(self._jgb())
        except Exception as e:  # noqa: BLE001 — JGB is optional; never lose the ECB legs
            log.warning("sovereign: JGB fetch/parse failed (%s); shipping ECB legs only", e)
        if not out:
            raise RuntimeError("sovereign: no series fetched (ECB + JGB both failed)")
        return out

    def _ecb(self) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for name, key in self.cfg["ecb_series"].items():
            r = self.http_get(f"{self.cfg['ecb_url']}/{key}", retries=self.cfg["retries"],
                              timeout=60, params={"format": "csvdata"},
                              headers={"User-Agent": _UA})
            df = pd.read_csv(io.StringIO(r.text))
            if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
                raise ValueError(f"unexpected ECB columns for {name}: {list(df.columns)[:6]}")
            d = df[["TIME_PERIOD", "OBS_VALUE"]].rename(columns={"TIME_PERIOD": "date", "OBS_VALUE": name})
            d["date"] = pd.to_datetime(d["date"], errors="coerce")
            d[name] = pd.to_numeric(d[name], errors="coerce")
            out[name] = d.dropna().set_index("date")
        return out

    def _jgb(self) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["mof_url"], retries=self.cfg["retries"], timeout=90,
                          headers={"User-Agent": _UA})
        txt = r.content.decode("shift_jis", errors="replace")
        df = pd.read_csv(io.StringIO(txt), skiprows=1)          # row 0 = Japanese title
        df["_d"] = df.iloc[:, 0].map(_jp_date)
        df = df.dropna(subset=["_d"]).set_index("_d")
        out: dict[str, pd.DataFrame] = {}
        for name, col in self.cfg["jgb_tenors"].items():
            if col in df.columns:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if not s.empty:
                    out[name] = s.to_frame(name)
        if not out:
            raise ValueError(f"JGB: no configured tenors {list(self.cfg['jgb_tenors'].values())} in {list(df.columns)[:6]}")
        return out

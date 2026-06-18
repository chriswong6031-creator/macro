"""Hong Kong residential property — Centaline 中原城市領先指數 (CCL) weekly index.

The CCL (Centa-City Leading Index) is THE high-frequency read on HK home prices:
a weekly, secondary-market repeat-sale index covering ~100+ representative estates,
published by Centaline (中原地產). It leads the official RVD price index by weeks
and is the de-facto barometer the HK property cycle is quoted on. Pure context /
DISPLAY for the HK macro card — never a scored leg (HK property is a slow,
policy-driven cycle; this is regime colour, not a forecast input).

Source (keyless JSON, live-verified 2026-06-17): the Centaline CCI dashboard at
hk.centanet.com is a Nuxt SPA whose chart pulls from a same-host JSON API under
``/centanetAPI/api/Index/*`` (NOT ``/api/...`` at the web root — that 404s):

  /centanetAPI/api/Index/CCL       headline CCL: ``ccl.chartData`` = aligned
                                   ``date[]`` + ``index[]`` weekly history back to
                                   1994 (~1690 pts), plus latest ``ccl.index`` /
                                   ``trendChangeWeek`` (WoW %), and ``estate`` =
                                   the CCL Mass (大型屋苑, district MASSEST) latest
                                   level (no history array — accrues weekly via
                                   store.upsert).
  /centanetAPI/api/Index/CCLChart  ``rawData`` with an aligned ``times[]`` and
                                   full-history arrays incl. ``cvi`` (中原估價指數
                                   Centa Valuation Index) + ``csi`` (中原經紀人指數
                                   Centa Salesman/Agent Index).

GOTCHAS:
- The legacy ``hk.centadata.com`` / ``www.centadata.com`` hosts present a cert with
  a HOSTNAME MISMATCH (SSL verify fails) — we deliberately avoid them and use the
  modern centanet JSON host instead.
- The web root ``hk.centanet.com/api/...`` 404s; the real axios baseURL is
  ``/centanetAPI/api`` (extracted from the Nuxt bundle).
- Centaline is a single non-exchange host with a JS-rendered front end, so the JSON
  layout can break / bot-block at any time. We set ``self.expected_failure`` → a
  break reports status 'blocked' and NEVER trips the circuit breaker. JSON-first,
  with a ``pd.read_html`` fallback over the served page if the JSON shape changes.

Stored under group ``hk_property``, weekly DatetimeIndex (week-ending):
  ccl   columns: ccl (headline CCL level) · ccl_chg (WoW %) · ccl_mass (CCL Mass
        大型屋苑 level — latest week only, history accretes via upsert)
  cci   columns: cvi (Centa Valuation Index) · csi (Centa Salesman Index)
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# modern Centaline JSON API (axios baseURL from the Nuxt bundle); web root /api 404s
_API = "https://hk.centanet.com/centanetAPI/api/Index"
_REFERER = "https://hk.centanet.com/CCI/index"
# served page for the pd.read_html degradation path if the JSON layout ever breaks
_PAGE = "https://hk.centanet.com/icms/template.aspx?series=CCI&code=E-CCL"


class HkPropertyAdapter(Adapter):
    name = "hk_property"
    group = "hk_property"
    stale_after_days = 12   # weekly index, published with a multi-day lag + HK holidays
    # KNOWN-FRAGILE single host w/ JS front end: a layout break reports 'blocked'
    # (degrade to absent) instead of failing and tripping the breaker.
    expected_failure = "Centaline CCL layout/host change — degrade to absent"

    def __init__(self) -> None:
        self.cfg = config.load().get("hk", {}).get("property", {}) or {}
        self.retries = int(self.cfg.get("retries", 3))

    def _headers(self) -> dict:
        return {"User-Agent": _UA, "Referer": _REFERER,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9,zh-HK;q=0.8"}

    def _get_json(self, path: str) -> dict:
        r = self.http_get(f"{_API}/{path}", retries=self.retries,
                          headers=self._headers(), timeout=40)
        try:
            return r.json() or {}
        except ValueError as e:
            raise ValueError(f"{path}: non-JSON payload ({e})")

    # -- headline CCL + WoW + CCL Mass ----------------------------------------
    def _ccl(self) -> pd.DataFrame:
        """Headline 中原城市領先指數 (CCL): weekly level + derived WoW % + latest
        CCL Mass (大型屋苑). The full date-aligned history lives in ``ccl.chartData``;
        the latest ``trendChangeWeek`` confirms the WoW we derive from the level."""
        j = self._get_json("CCL")
        ccl = (j or {}).get("ccl") or {}
        cd = ccl.get("chartData") or {}
        dates, idx = cd.get("date"), cd.get("index")
        if not dates or not idx or len(dates) != len(idx):
            raise ValueError("ccl: missing/misaligned chartData (date/index)")
        out = pd.DataFrame(index=pd.to_datetime(dates))
        out["ccl"] = pd.to_numeric(pd.Series(idx, index=out.index), errors="coerce")
        out = out.dropna(subset=["ccl"]).sort_index()
        if out.empty:
            raise ValueError("ccl: no usable index values")
        # WoW % straight off the level (matches the reported trendChangeWeek)
        out["ccl_chg"] = (out["ccl"].pct_change() * 100).round(3)
        # CCL Mass (大型屋苑) — latest scalar only; history accretes via upsert
        mass = ((j.get("estate") or {}).get("index"))
        if mass is not None:
            try:
                out.loc[out.index[-1], "ccl_mass"] = float(mass)
            except (TypeError, ValueError):
                pass
        return out

    # -- Centa Valuation + Salesman indices (optional companion) ---------------
    def _cci(self) -> pd.DataFrame:
        """CVI (中原估價指數, banks' valuation sentiment) + CSI (中原經紀人指數,
        agent sentiment) from ``CCLChart.rawData``, aligned to its ``times[]``."""
        j = self._get_json("CCLChart")
        rd = (j or {}).get("rawData") or {}
        times = rd.get("times")
        if not times:
            raise ValueError("cci: missing times[] axis")
        index = pd.to_datetime(times)
        out = pd.DataFrame(index=index)
        for stored, src in (("cvi", "cvi"), ("csi", "csi")):
            arr = rd.get(src)
            if isinstance(arr, list) and len(arr) == len(index):
                out[stored] = pd.to_numeric(pd.Series(arr, index=index), errors="coerce")
        out = out.dropna(how="all").sort_index()
        if out.empty:
            raise ValueError("cci: no usable cvi/csi values")
        return out

    # -- degradation path: scrape any table off the served CCL page -----------
    def _ccl_from_html(self) -> pd.DataFrame:
        """Last-ditch: if the JSON API shape changes, parse a date/level table off
        the served page with pd.read_html. Best-effort — picks the first table that
        yields a parseable (date, numeric level) pair."""
        r = self.http_get(_PAGE, retries=self.retries,
                          headers={"User-Agent": _UA, "Referer": _REFERER}, timeout=40)
        try:
            tables = pd.read_html(io.StringIO(r.text))
        except ValueError as e:
            raise ValueError(f"ccl_html: no tables ({e})")
        for tbl in tables:
            if tbl.shape[1] < 2:
                continue
            t = tbl.copy()
            t.columns = [str(c) for c in range(t.shape[1])]
            dt = pd.to_datetime(t["0"], errors="coerce")
            lvl = pd.to_numeric(t["1"], errors="coerce")
            mask = dt.notna() & lvl.notna()
            if mask.sum() < 4:
                continue
            out = pd.DataFrame({"ccl": lvl[mask].to_numpy()},
                               index=dt[mask]).sort_index()
            out["ccl_chg"] = (out["ccl"].pct_change() * 100).round(3)
            return out
        raise ValueError("ccl_html: no table with parseable (date, level)")

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        # primary headline CCL, with the HTML scrape as a degradation fallback
        try:
            frames["ccl"] = self._ccl()
        except Exception as e:  # noqa: BLE001 — per-series isolation; try the fallback
            log.warning("hk_property ccl JSON failed (%s); trying HTML fallback", e)
            try:
                frames["ccl"] = self._ccl_from_html()
            except Exception as e2:  # noqa: BLE001
                errors.append(f"ccl: {e} | html: {e2}")
                log.warning("hk_property ccl HTML fallback failed: %s", e2)
        # optional companion valuation/agent indices
        try:
            frames["cci"] = self._cci()
        except Exception as e:  # noqa: BLE001 — optional; never blocks the headline
            errors.append(f"cci: {e}")
            log.warning("hk_property cci failed: %s", e)
        if not frames:
            # no series resolved — raise so the runner can act (status 'blocked'
            # here because expected_failure is set: a layout break never trips the breaker)
            raise RuntimeError("hk_property: all series failed — " + " | ".join(errors))
        if errors:
            log.info("hk_property: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames

"""Policy- & geopolitical-uncertainty indices — keyless daily CONTEXT series.

Two peer-reviewed, free, daily text-uncertainty indices that quantify the
NARRATIVE REGIME the dashboard's price/momentum signals degrade in (the
"manufactured-volatility" backdrop — tariff scares, geopolitical escalations):

  • EPU  — US daily news-based Economic Policy Uncertainty (Baker, Bloom & Davis).
    policyuncertainty.com ships it as a small CSV (day, month, year,
    daily_policy_index), history from 1985. A higher value = more newspaper
    coverage of policy uncertainty.

  • GPR  — daily Geopolitical Risk index (Caldara & Iacoviello, AER 2022). A small
    legacy .xls with the index PLUS its THREAT / ACT decomposition — the one
    directional-ish, published-validated reading we use downstream: the THREAT
    component reverts (~3 months) while realized ACTS persist, so a threat-driven
    spike is a reversible-scare candidate and an act-driven one is a regime break.

WHAT THIS IS / IS NOT (the house rule). These are stored as date-indexed CONTEXT
series only. The replicated finding across the literature is one-directional:
text-uncertainty has robust content for realized VOLATILITY / tail risk / risk
premia and WEAK, unstable content for return DIRECTION — and for vol forecasting
itself VIX typically beats EPU. So nothing here is (yet) a scored input; it feeds a
display regime read (engine/news_vector.py) and, only if a separately-gated Phase-0
clears an incremental-over-VIX bar, a subtract-only conditioner later. See
memory narrative-quant-framework.

Both endpoints are reachable from the sandbox (unlike FRED). Defensive,
substring-based column detection (column casing/order drifts between vintages).
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class UncertaintyIndicesAdapter(Adapter):
    name = "uncertainty_indices"
    group = "uncertainty"
    stale_after_days = 12   # daily series, but a few days' publication lag (EPU/GPR)

    def __init__(self) -> None:
        self.cfg = config.load().get("uncertainty_indices", {}) or {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        retries = int(self.cfg.get("retries", 3))
        out: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        # EPU — US daily news-based policy uncertainty (CSV)
        try:
            r = self.http_get(self.cfg["epu_daily_url"], retries=retries, timeout=90,
                              headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
            out["epu_us"] = self._parse_epu(r.content)
        except Exception as e:  # noqa: BLE001 — one source down must not lose the other
            errors.append(f"epu:{type(e).__name__}:{e}")
            log.warning("EPU daily fetch/parse failed (%s)", e)
        # GPR — daily geopolitical risk with THREAT / ACT split (legacy .xls)
        try:
            r = self.http_get(self.cfg["gpr_daily_url"], retries=retries, timeout=90,
                              headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
            out["gpr"] = self._parse_gpr(r.content)
        except Exception as e:  # noqa: BLE001
            errors.append(f"gpr:{type(e).__name__}:{e}")
            log.warning("GPR daily fetch/parse failed (%s)", e)
        if not out:
            raise RuntimeError("uncertainty_indices: both sources failed (" + "; ".join(errors) + ")")
        return out

    # ----------------------------------------------------------------------- #
    # pure parsers (no network) — unit-tested on synthetic frames
    # ----------------------------------------------------------------------- #
    @staticmethod
    def _parse_epu(content: bytes) -> pd.DataFrame:
        """US daily EPU CSV -> DataFrame[date -> epu, epu_ma7]. PURE.

        Returned with a 7-day MA companion column ON PURPOSE: a daily news-based
        uncertainty index is intentionally spiky, so the runner's single-column,
        price-oriented outlier guard (which would quarantine legitimate spikes) must
        NOT apply — a 2-column frame disables it, and the MA is genuinely useful for
        the display smoothing."""
        df = pd.read_csv(io.BytesIO(content))
        low = {str(c).lower().strip(): c for c in df.columns}
        ycol = next((o for k, o in low.items() if k == "year" or k.startswith("year")), None)
        mcol = next((o for k, o in low.items() if k == "month" or k.startswith("month")), None)
        dcol = next((o for k, o in low.items() if k == "day" or k.startswith("day")), None)
        vcol = next((o for k, o in low.items()
                     if "policy_index" in k or k.endswith("index") or "epu" in k), None)
        if not (ycol and mcol and dcol and vcol):
            raise ValueError(f"unexpected EPU columns: {list(df.columns)}")
        idx = pd.to_datetime(dict(year=pd.to_numeric(df[ycol], errors="coerce"),
                                  month=pd.to_numeric(df[mcol], errors="coerce"),
                                  day=pd.to_numeric(df[dcol], errors="coerce")), errors="coerce")
        val = pd.to_numeric(df[vcol], errors="coerce")
        out = (pd.DataFrame({"epu": val.values}, index=idx)
               .dropna().sort_index())
        out = out[~out.index.duplicated(keep="last")]
        out["epu_ma7"] = out["epu"].rolling(7, min_periods=1).mean()
        out.index.name = "date"
        return out

    @staticmethod
    def _parse_gpr(content: bytes) -> pd.DataFrame:
        """Daily GPR .xls -> DataFrame[date -> gpr, gpr_threat, gpr_act]. PURE.

        Caldara-Iacoviello daily file columns: DAY (YYYYMMDD), GPRD, GPRD_THREAT,
        GPRD_ACT, date, GPRD_MA7/30, ... Multi-column by construction, so the
        price outlier guard is already inactive."""
        df = pd.read_excel(io.BytesIO(content))
        low = {str(c).lower().strip(): c for c in df.columns}
        # exact 'gprd' is the headline index (must not match gprd_act / gprd_threat / gprd_ma*)
        gcol = low.get("gprd")
        tcol = low.get("gprd_threat")
        acol = low.get("gprd_act")
        if gcol is None:
            raise ValueError(f"unexpected GPR columns: {list(df.columns)}")
        # date: prefer an explicit 'date' column, else build from the YYYYMMDD 'day' int
        if "date" in low:
            idx = pd.to_datetime(df[low["date"]], errors="coerce")
        elif "day" in low:
            idx = pd.to_datetime(df[low["day"]].astype("Int64").astype(str),
                                 format="%Y%m%d", errors="coerce")
        else:
            raise ValueError(f"GPR: no date/day column in {list(df.columns)}")
        data = {"gpr": pd.to_numeric(df[gcol], errors="coerce").values}
        if tcol is not None:
            data["gpr_threat"] = pd.to_numeric(df[tcol], errors="coerce").values
        if acol is not None:
            data["gpr_act"] = pd.to_numeric(df[acol], errors="coerce").values
        out = (pd.DataFrame(data, index=idx)
               .dropna(subset=["gpr"]).sort_index())
        out = out[~out.index.duplicated(keep="last")]
        out.index.name = "date"
        return out

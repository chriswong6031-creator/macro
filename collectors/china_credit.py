"""China Total Social Financing (社会融资规模) — the single most-watched China macro
lead for equities and commodities.

Source: mofcom's shrzgm query (data.mofcom.gov.cn), the same series akshare wraps.
The host speaks a legacy TLS dialect that a modern OpenSSL refuses by default
(SSLV3_ALERT_HANDSHAKE_FAILURE) — so this collector mounts an adapter that re-enables
legacy renegotiation + a lower security level, the classic fix for old Chinese-gov
endpoints. Returns the monthly social-financing INCREMENT (增量) with its components,
2015-01-> (mofcom only serves from there); archive-forever via store.upsert.

The downstream engine derives the CREDIT IMPULSE (YoY of the trailing-12-month TSF
sum), which historically leads risk assets by a couple of quarters.
"""
from __future__ import annotations

import logging
import ssl

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

from collectors.base import Adapter

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_URL = "https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery"

# mofcom field -> stored column (all 亿元, monthly increment)
_FIELDS = {
    "tiosfs":      "tsf_total",     # 社会融资规模增量（总量）
    "rmblaon":     "rmb_loans",     # 人民币贷款 (note the upstream typo 'rmblaon')
    "forcloan":    "fx_loans",      # 外币贷款
    "entrustloan": "entrust",       # 委托贷款
    "trustloan":   "trust",         # 信托贷款
    "ndbab":       "accept_bills",  # 未贴现银行承兑汇票
    "bibae":       "corp_bonds",    # 企业债券
    "sfinfe":      "equity",        # 非金融企业境内股票融资
}


class _LegacyAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **k):
        ctx = create_urllib3_context()
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except Exception:  # noqa: BLE001
            pass
        k["ssl_context"] = ctx
        return super().init_poolmanager(*a, **k)


class ChinaCreditAdapter(Adapter):
    name = "china_credit"
    group = "china_credit"
    stale_after_days = 70   # monthly TSF releases mid-month for the prior month (≈6-week lag)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = requests.Session()
        s.mount("https://", _LegacyAdapter())
        s.headers.update({"User-Agent": _UA})
        import urllib3
        urllib3.disable_warnings()
        r = s.post(_URL, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or not data:
            raise ValueError("china_credit: empty/unexpected mofcom payload")
        raw = pd.DataFrame(data)
        idx = pd.to_datetime(raw["date"].astype(str), format="%Y%m")
        out = pd.DataFrame(index=idx)
        for src, stored in _FIELDS.items():
            if src in raw.columns:
                out[stored] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
        out = out.dropna(how="all").sort_index()
        if out.empty or "tsf_total" not in out.columns:
            raise ValueError("china_credit: no usable TSF columns parsed")
        return {"tsf": out}

"""OpenFIGI CUSIP→ticker master — the free fix for our 13F "no free CUSIP master" gap.

`engine/smart_money.py` resolves a 13F info-table line to a ticker via a ~60-CUSIP
ARK-harvested seed (`cusip_ticker_seed`) plus fuzzy issuer-name matching against the
S&P-1500 membership. Foreign/ADR/renamed/non-index lines that miss both fall through
and are silently HIDDEN. OpenFIGI's keyless `/v3/mapping` endpoint maps a CUSIP →
the consolidated US-composite ticker (Bloomberg-sourced), unhiding those lines.

Free + keyless: 25 req/min, 10 CUSIPs per request. An optional free OPENFIGI_API_KEY
raises that to 25 req / 6 s and 100 CUSIPs per request. We map only the CUSIPs we
don't already have cached (idempotent), write a committed cache to
data/openfigi/cusip_ticker.parquet, and degrade to 'blocked' only if the host is down.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

BASE = "https://api.openfigi.com/v3/mapping"
# US composite + the regional MIC codes OpenFIGI tags US listings with; we only
# keep equity matches that are US-listed (so a CUSIP's foreign line doesn't win).
_US_EXCH = {"US", "UN", "UQ", "UA", "UR", "UP", "UV", "UW", "UC", "UD", "UF"}
MAX_CUSIPS_PER_RUN = 2500


def _key() -> str | None:
    return config.secret("OPENFIGI_API_KEY")


def _cache_path():
    return config.data_dir() / "openfigi" / "cusip_ticker.parquet"


def load_cusip_ticker() -> dict[str, str]:
    """{cusip: ticker} from the committed OpenFIGI cache. Empty if not built yet."""
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return {}
    df = df[df["ticker"].notna() & (df["ticker"].astype(str) != "")]
    return {str(c).strip().upper(): str(t).strip().upper()
            for c, t in zip(df["cusip"], df["ticker"])}


def _candidate_cusips() -> list[str]:
    """Unique 9-char equity CUSIPs across every retained 13F snapshot (sh_type==SH)."""
    base = config.data_dir() / "smart_money"
    if not base.exists():
        return []
    seen: set[str] = set()
    for p in base.glob("*/*.parquet"):
        try:
            df = pd.read_parquet(p, columns=["cusip", "sh_type"])
        except Exception:  # noqa: BLE001
            try:
                df = pd.read_parquet(p, columns=["cusip"])
                df["sh_type"] = "SH"
            except Exception:  # noqa: BLE001
                continue
        df = df[df.get("sh_type", "SH") == "SH"]
        for c in df["cusip"].astype(str):
            c = c.strip().upper()
            if len(c) >= 8:
                seen.add(c)
    return sorted(seen)


def _pick(matches: list[dict]) -> dict | None:
    """Best US-listed equity match for a CUSIP from OpenFIGI's per-exchange rows."""
    if not matches:
        return None
    eq = [m for m in matches if m.get("marketSector") == "Equity"] or matches
    us = [m for m in eq if str(m.get("exchCode", "")).upper() in _US_EXCH]
    m = (us or eq)[0]
    # share-class convention: OpenFIGI uses "/" (BRK/A), our universe uses "-"
    tk = str(m.get("ticker") or "").strip().upper().replace("/", "-")
    if not tk:
        return None
    return {"ticker": tk, "name": m.get("name"),
            "exch": m.get("exchCode"), "sec_type": m.get("securityType2")}


class OpenFigiAdapter(Adapter):
    name = "openfigi"
    group = "openfigi"
    stale_after_days = 30          # a CUSIP→ticker map is near-static

    def __init__(self) -> None:
        self.api_key = _key()
        self.jobs_per_req = 100 if self.api_key else 10
        self.pace_s = 0.3 if self.api_key else 2.6   # 25/6s with key, 25/min without

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-OPENFIGI-APIKEY"] = self.api_key
        return h

    def _map_batch(self, cusips: list[str]) -> list[dict | None]:
        import requests
        body = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
        resp = requests.post(BASE, json=body, headers=self._headers(), timeout=40)
        if resp.status_code == 429:
            raise requests.HTTPError("HTTP 429 (rate)", response=resp)
        resp.raise_for_status()
        out: list[dict | None] = []
        for job in resp.json():
            out.append(_pick(job.get("data", [])) if isinstance(job, dict) else None)
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        cands = _candidate_cusips()
        if not cands:
            raise RuntimeError("openfigi: no 13F CUSIPs to map (smart_money empty)")
        have = set(load_cusip_ticker())
        # also skip CUSIPs we already tried-and-missed (cached with empty ticker)
        cache_p = _cache_path()
        prev = pd.read_parquet(cache_p) if cache_p.exists() else pd.DataFrame()
        tried = set(prev["cusip"].astype(str).str.upper()) if not prev.empty else set()
        todo = [c for c in cands if c not in have and c not in tried][:MAX_CUSIPS_PER_RUN]
        if not todo:
            hb = pd.DataFrame({"mapped": [0], "cached": [len(have)]},
                              index=[pd.Timestamp(datetime.now(timezone.utc).date())])
            return {"openfigi__ingest": hb}

        rows: list[dict] = []
        done = 0
        for i in range(0, len(todo), self.jobs_per_req):
            batch = todo[i:i + self.jobs_per_req]
            try:
                picks = self._map_batch(batch)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e) and done == 0:
                    raise                         # host down -> runner marks failed
                log.warning("openfigi batch failed (%s); stopping at %d", e, done)
                break
            for c, pick in zip(batch, picks):
                rows.append({"cusip": c, "ticker": (pick or {}).get("ticker", ""),
                             "name": (pick or {}).get("name"),
                             "exch": (pick or {}).get("exch"),
                             "sec_type": (pick or {}).get("sec_type")})
            done += len(batch)
            time.sleep(self.pace_s)

        if not rows:
            raise RuntimeError("openfigi: mapped 0 rows")
        fresh = pd.DataFrame(rows)
        fresh["_mapped_at"] = datetime.now(timezone.utc).isoformat()
        combined = pd.concat([prev, fresh], ignore_index=True) if not prev.empty else fresh
        combined = combined.drop_duplicates(subset=["cusip"], keep="last").reset_index(drop=True)
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_p)
        n_hit = int((fresh["ticker"].astype(str) != "").sum())
        log.info("openfigi: mapped %d CUSIPs (%d resolved), cache=%d",
                 len(fresh), n_hit, len(combined))
        hb = pd.DataFrame({"mapped": [len(fresh)], "resolved": [n_hit]},
                          index=[pd.Timestamp(datetime.now(timezone.utc).date())])
        return {"openfigi__ingest": hb}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    OpenFigiAdapter().fetch()

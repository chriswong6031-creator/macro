"""QuiverQuant alternative-data -> monthly per-ticker series feeding the Divergence Radar.

Adds independent non-price observables of "is real activity happening on this theme":
  * govcontracts  — federal new-award $        (a 2nd, independent feed vs usaspending)
  * congress      — congressional NET-BUY $    (signed: purchase +, sale −; anticipatory)
  * lobbying      — lobbying spend             (regime-change anticipation; leads price)
  * patents       — patent grants              (innovation pipeline)
  * offexchange   — off-exchange short ratio   (contested-narrative → CROWD context, down-size)
  * wsb           — WallStreetBets mentions    (retail crowding → CROWD context, down-size)

Trader tier (all of the above). KEYLESS-SAFE: no QUIVER_API_KEY → clean no-op. Resumable
capped DRIP (the universe is ~300 tickers across the baskets, so we refresh each ticker
weekly and cap calls/run — never a per-build flood), like collectors/edgar_facts. Writes
wide [month × ticker] parquets via store.upsert (append-only, column-wise merge).

API: GET https://api.quiverquant.com/beta/historical/<dataset>/<TICKER>, header
`Authorization: Token <KEY>` (per the official quiverquant client — NOT Bearer). Parsing is
SCHEMA-TOLERANT (candidate field lists) and lives in pure module functions so it is unit-
testable without the live key; live validation happens in CI where the secret is present.

engine/theme_activity.py auto-consumes govcontracts/congress/lobbying/patents as fusable
real-activity legs; offexchange/wsb are stored for the crowd-context (down-size only) layer.
Display-only context, never a trade trigger.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

BASE = "https://api.quiverquant.com/beta/historical/"
PACING_S = 0.25
REFRESH_DAYS = 7          # the histories move monthly; refresh each ticker weekly
MAX_TICKERS_PER_RUN = 90  # per dataset; ~300 universe / weekly cadence fits well under this

# dataset configs — `value`/`date` are CANDIDATE field lists (first present wins).
DATASETS: dict[str, dict] = {
    "govcontracts": {"path": "govcontractsall", "date": ["Date"], "value": ["Amount"], "agg": "sum"},
    "congress": {"path": "congresstrading", "date": ["TransactionDate", "Traded", "ReportDate", "Date"],
                 "value": ["Amount", "Trade_Size_USD"], "range": ["Range"], "direction": ["Transaction"], "agg": "sum_signed"},
    "lobbying": {"path": "lobbying", "date": ["Date"], "value": ["Amount"], "agg": "sum"},
    "patents": {"path": "allpatents", "date": ["Date", "DateFiled", "DateGranted"],
                "value": ["Patents", "Count", "PatentCount"], "agg": "sum_or_count"},
    "offexchange": {"path": "offexchange", "date": ["Date"], "value": ["Short_Volume", "ShortVolume", "DPI_Short"],
                    "denom": ["Total_Volume", "TotalVolume", "Volume"], "alt": ["DPI"], "agg": "ratio"},
    "wsb": {"path": "wallstreetbets", "date": ["Date"], "value": ["Mentions", "Count"], "agg": "sum"},
}


def _resolve(cols, candidates) -> str | None:
    s = set(cols)
    for c in candidates or []:
        if c in s:
            return c
    return None


def _range_mid(text) -> float:
    """Midpoint of a congress dollar RANGE like '$1,001 - $15,000'. NaN if unparseable."""
    nums = re.findall(r"[\d,]+(?:\.\d+)?", str(text))
    vals = [float(n.replace(",", "")) for n in nums if n.replace(",", "").replace(".", "").isdigit()]
    if not vals:
        return float("nan")
    return float(sum(vals[:2]) / len(vals[:2]))


def rows_to_monthly(cfg: dict, rows: list[dict]) -> pd.Series | None:
    """Aggregate one ticker's dataset rows into a monthly Series. PURE + schema-tolerant.
    sum / sum_signed (congress) / sum_or_count (patents) / ratio (offexchange short share)."""
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    dcol = _resolve(df.columns, cfg["date"])
    if not dcol:
        return None
    m = pd.to_datetime(df[dcol], errors="coerce").dt.to_period("M").dt.to_timestamp()
    df = df.assign(_m=m).dropna(subset=["_m"])
    if df.empty:
        return None
    agg = cfg["agg"]

    if agg == "ratio":
        vcol, ncol = _resolve(df.columns, cfg["value"]), _resolve(df.columns, cfg.get("denom", []))
        if vcol and ncol:
            sv = pd.to_numeric(df[vcol], errors="coerce")
            tv = pd.to_numeric(df[ncol], errors="coerce").replace(0, np.nan)
            v = sv / tv
        else:
            acol = _resolve(df.columns, cfg.get("alt", []))
            if not acol:
                return None
            v = pd.to_numeric(df[acol], errors="coerce")
        return df.assign(_v=v).groupby("_m")["_v"].mean().dropna().sort_index()

    if agg == "sum_signed":
        vcol = _resolve(df.columns, cfg["value"])
        if vcol:
            val = pd.to_numeric(df[vcol], errors="coerce")
        else:
            rcol = _resolve(df.columns, cfg.get("range", []))
            if not rcol:
                return None
            val = df[rcol].map(_range_mid)
        dircol = _resolve(df.columns, cfg.get("direction", []))
        if dircol:
            sign = df[dircol].astype(str).str.lower().map(
                lambda s: -1.0 if ("sale" in s or "sell" in s) else 1.0)
            val = val * sign
        return df.assign(_v=val).groupby("_m")["_v"].sum().dropna().sort_index()

    if agg == "sum_or_count":
        vcol = _resolve(df.columns, cfg["value"])
        val = pd.to_numeric(df[vcol], errors="coerce") if vcol else pd.Series(1.0, index=df.index)
        return df.assign(_v=val).groupby("_m")["_v"].sum().dropna().sort_index()

    # default: sum a dollar column
    vcol = _resolve(df.columns, cfg["value"])
    if not vcol:
        return None
    val = pd.to_numeric(df[vcol], errors="coerce")
    return df.assign(_v=val).groupby("_m")["_v"].sum().dropna().sort_index()


def _basket_universe() -> list[str]:
    """All live US basket members (the fuser maps each per basket)."""
    try:
        mem = json.loads((config.data_dir() / "baskets" / "membership.json").read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return []
    out = set()
    for b in mem.values():
        for m in b.get("members", []):
            if m.get("ticker") and not m.get("removed"):
                out.add(m["ticker"])
    return sorted(out)


class QuiverAdapter(Adapter):
    name = "quiver"
    group = "quiver"
    stale_after_days = 9

    def __init__(self) -> None:
        self.key = config.secret("QUIVER_API_KEY")

    def _state_path(self):
        return config.data_dir() / "quiver" / "_fetch_state.json"

    def _load_state(self) -> dict:
        p = self._state_path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return {}

    def _save_state(self, state: dict) -> None:
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps(state, separators=(",", ":")))
        except Exception as e:  # noqa: BLE001
            log.debug("quiver state save failed: %s", e)

    def _stale(self, state: dict, ds: str, ticker: str, full: bool) -> bool:
        if full:
            return True
        ts = (state.get(ds) or {}).get(ticker)
        if not ts:
            return True
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days >= REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return True

    def _fetch_ticker(self, path: str, ticker: str) -> list[dict]:
        url = f"{BASE}{path}/{ticker}"
        headers = {"Authorization": f"Token {self.key}",
                   "User-Agent": config.load()["sponsors"]["user_agent"]}
        import requests
        r = requests.get(url, headers=headers, timeout=40)
        if r.status_code in (401, 403):
            raise PermissionError(f"quiver auth/tier {r.status_code} for {path}")
        if r.status_code == 404:
            return []
        r.raise_for_status()
        try:
            j = r.json()
        except Exception:  # noqa: BLE001
            return []
        return j if isinstance(j, list) else []

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.key:
            log.info("quiver: no QUIVER_API_KEY — skipping (no-op)")
            return {}
        universe = _basket_universe()
        if not universe:
            log.info("quiver: empty basket universe — skipping")
            return {}
        state = self._load_state()
        cap = 10 ** 9 if full_history else MAX_TICKERS_PER_RUN
        out: dict[str, pd.DataFrame] = {}
        tier_blocked: set[str] = set()
        for ds_name, cfg in DATASETS.items():
            if ds_name in tier_blocked:
                continue
            todo = [t for t in universe if self._stale(state, ds_name, t, full_history)][:cap]
            if not todo:
                continue
            series, n_err = {}, 0
            for t in todo:
                try:
                    rows = self._fetch_ticker(cfg["path"], t)
                    time.sleep(PACING_S)
                except PermissionError as e:
                    log.warning("quiver %s: %s — skipping dataset (tier?)", ds_name, e)
                    tier_blocked.add(ds_name)
                    break
                except Exception as e:  # noqa: BLE001
                    if is_connection_error(e):
                        raise
                    n_err += 1
                    continue
                state.setdefault(ds_name, {})[t] = datetime.now(timezone.utc).isoformat()
                ser = rows_to_monthly(cfg, rows)
                if ser is not None and not ser.empty:
                    series[t] = ser
            if series:
                out[ds_name] = pd.concat(series, axis=1).sort_index()
            log.info("quiver %s: fetched %d, %d with data, %d errors", ds_name, len(todo), len(series), n_err)
        self._save_state(state)
        self._write_meta(out)
        return out

    def _write_meta(self, out: dict) -> None:
        p = config.data_dir() / "quiver" / "_meta.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps({
                "built": datetime.now(timezone.utc).isoformat(),
                "datasets": {k: {"tickers": int(v.shape[1]), "months": int(v.shape[0])} for k, v in out.items()},
            }, indent=2))
        except Exception as e:  # noqa: BLE001
            log.debug("quiver meta write failed: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # offline parser smoke test (no key needed)
    sample = [{"Date": "2026-03-01", "Amount": "1000000", "Ticker": "LMT"},
              {"Date": "2026-03-15", "Amount": "500000", "Ticker": "LMT"}]
    print("govcontracts parse:", rows_to_monthly(DATASETS["govcontracts"], sample).to_dict())
    cong = [{"TransactionDate": "2026-03-01", "Transaction": "Purchase", "Range": "$1,001 - $15,000", "Ticker": "NVDA"},
            {"TransactionDate": "2026-03-02", "Transaction": "Sale", "Range": "$15,001 - $50,000", "Ticker": "NVDA"}]
    print("congress net-buy parse:", rows_to_monthly(DATASETS["congress"], cong).to_dict())

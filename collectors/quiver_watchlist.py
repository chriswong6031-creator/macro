"""Quiver per-ticker collectors (Top Shareholders + Executive Compensation).

These two Quiver datasets are PARAMETRIZED by ticker (no bulk cross-section), so instead
of pulling the whole market we query only a focused WATCHLIST — the names the alt-data
system already flagged: the curated latent-stake graph tickers (data/trumpflow/intel.json)
+ the recent cross-signal convergent names (data/altdata/by_ticker.json from the prior
build). For a flagged name, "who else owns it" (institutional concentration) and "how the
executives are paid" (insider alignment) are useful context.

Keyed by ticker; append-only key-deduped with a _collected snapshot date.
data/quiver/topshareholders.parquet + data/quiver/execcomp.parquet.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class QuiverWatchlistAdapter(Adapter):
    name = "quiver_watchlist"
    group = "quiver"
    stale_after_days = 21
    MAX_TICKERS = 25

    def __init__(self) -> None:
        cfg = config.load().get("quiver", {})
        self.base_url = str(cfg.get("base_url", "https://api.quiverquant.com")).rstrip("/")
        self.timeout = int(cfg.get("timeout", 60))
        self.retries = int(cfg.get("retries", 3))
        self.api_key = config.secret("QUIVER_API_KEY")
        if not self.api_key:
            self.expected_failure = "QUIVER_API_KEY not set"

    # -- watchlist -------------------------------------------------------------
    def _watchlist(self) -> list[str]:
        tickers: set[str] = set()
        try:
            intel = json.loads((config.data_dir() / "trumpflow" / "intel.json").read_text())
            for e in intel.get("entities", []):
                if e.get("ticker"):
                    tickers.add(str(e["ticker"]).upper())
        except Exception:  # noqa: BLE001
            pass
        try:
            bt = json.loads((config.data_dir() / "altdata" / "by_ticker.json").read_text())
            for tk, rec in (bt.get("tickers") or {}).items():
                if int(rec.get("convergence_score", 0) or 0) >= 2:
                    tickers.add(str(tk).upper())
        except Exception:  # noqa: BLE001
            pass
        return sorted(t for t in tickers if t and t.lower() not in ("nan", "none"))[: self.MAX_TICKERS]

    # -- http ------------------------------------------------------------------
    def _get(self, endpoint: str):
        r = self.http_get(f"{self.base_url}{endpoint}", retries=self.retries, timeout=self.timeout,
                          headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"})
        return r.json()

    # -- storage ---------------------------------------------------------------
    def _merge(self, dataset: str, new: pd.DataFrame, keys: list[str]) -> int:
        if new.empty:
            return 0
        new = new.copy()
        new["_collected"] = datetime.now(timezone.utc).date().isoformat()
        path = config.data_dir() / self.group / f"{dataset}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            combined = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        else:
            combined = new
        ksub = [k for k in keys if k in combined.columns]
        combined = combined.drop_duplicates(subset=ksub or None, keep="first").reset_index(drop=True)
        combined.to_parquet(path)
        return len(new)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("QUIVER_API_KEY not set")
        wl = self._watchlist()
        if not wl:
            raise RuntimeError("quiver_watchlist: empty watchlist")
        holders, comp = [], []
        for tk in wl:
            try:
                d = self._get(f"/beta/live/topshareholders/{tk}")
                for o in (d.get("ownership", []) if isinstance(d, dict) else []):
                    holders.append({"ticker": tk, "owner_name": o.get("owner_name"),
                                    "owner_title": o.get("owner_title"), "shares": o.get("shares")})
            except Exception as e:  # noqa: BLE001
                log.warning("topshareholders %s failed: %s", tk, e)
            try:
                d = self._get(f"/beta/historical/executivecompensation/{tk}")
                for c in (d.get("data", []) if isinstance(d, dict) else []):
                    comp.append({"ticker": tk, "name": c.get("Name"), "role": c.get("Role"),
                                 "year": c.get("Year"), "total_comp": c.get("TotalCompensation"),
                                 "salary": c.get("Salary"), "bonus": c.get("Bonus")})
            except Exception as e:  # noqa: BLE001
                log.warning("execcomp %s failed: %s", tk, e)
        nh = self._merge("topshareholders", pd.DataFrame(holders),
                         ["ticker", "owner_name", "_collected"]) if holders else 0
        nc = self._merge("execcomp", pd.DataFrame(comp), ["ticker", "name", "year"]) if comp else 0
        if not holders and not comp:
            raise RuntimeError("quiver_watchlist: no data for any watchlist ticker")
        log.info("quiver_watchlist: %d tickers -> %d holders, %d comp rows", len(wl), nh, nc)
        ingest = pd.DataFrame({"tickers": [len(wl)], "holders": [nh], "comp": [nc]},
                              index=[pd.Timestamp(datetime.now(timezone.utc).date())])
        return {"watchlist__ingest": ingest}

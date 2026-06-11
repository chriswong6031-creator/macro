"""Treasury FiscalData collector (free, no key).

- TGA daily operating cash balance. Schema changed over time:
    * pre Oct-2021: account_type == 'Federal Reserve Account', value in close_today_bal
    * since Oct-2021: account_type == 'Treasury General Account (TGA) Closing Balance',
      value (oddly) in open_today_bal, close_today_bal is null.
  Both are $ millions.
- Net marketable issuance from DTS Table IIIA (public_debt_transactions):
  Issues minus Redemptions, Marketable only, $ millions, aggregated monthly
  by the engine.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from collectors.base import Adapter
from lib import config, store


class TreasuryAdapter(Adapter):
    name = "treasury"
    group = "treasury"

    def __init__(self) -> None:
        self.cfg = config.load()["treasury"]

    def _paged(self, endpoint: str, flt: str, fields: str | None = None) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            params = {"filter": flt, "page[size]": str(self.cfg["page_size"]),
                      "page[number]": str(page), "sort": "record_date"}
            if fields:
                params["fields"] = fields
            r = self.http_get(self.cfg["base_url"] + endpoint,
                              retries=self.cfg["retries"], params=params, timeout=120)
            j = r.json()
            out.extend(j["data"])
            if page >= j["meta"]["total-pages"]:
                break
            page += 1
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if full_history:
            start = "2005-01-01"
        else:
            last = store.last_date(self.group, "tga") or (date.today() - timedelta(days=30))
            start = str(last - timedelta(days=7))
        return {"tga": self._fetch_tga(start),
                "net_issuance": self._fetch_issuance(start)}

    def _fetch_tga(self, start: str) -> pd.DataFrame:
        rows = self._paged(
            self.cfg["tga_endpoint"],
            f"record_date:gte:{start}",
            "record_date,account_type,open_today_bal,close_today_bal",
        )
        recs = []
        for x in rows:
            at = x["account_type"]
            if at == "Federal Reserve Account":
                val = x.get("close_today_bal")
            elif at == "Treasury General Account (TGA) Closing Balance":
                val = x.get("open_today_bal")  # known DTS API quirk
            else:
                continue
            recs.append((x["record_date"], val))
        df = pd.DataFrame(recs, columns=["date", "tga_mn"])
        df["tga_mn"] = pd.to_numeric(df["tga_mn"], errors="coerce")
        return df.dropna().set_index("date")

    def _fetch_issuance(self, start: str) -> pd.DataFrame:
        rows = self._paged(
            self.cfg["debt_txn_endpoint"],
            f"record_date:gte:{start},security_market:eq:Marketable",
            "record_date,transaction_type,security_market,transaction_today_amt",
        )
        df = pd.DataFrame(rows)
        if df.empty:
            raise ValueError("no debt transaction rows")
        df["amt"] = pd.to_numeric(df["transaction_today_amt"], errors="coerce").fillna(0)
        piv = df.pivot_table(index="record_date", columns="transaction_type",
                             values="amt", aggfunc="sum")
        out = pd.DataFrame(index=piv.index)
        out["net_issuance_mn"] = piv.get("Issues", 0) - piv.get("Redemptions", 0)
        return out

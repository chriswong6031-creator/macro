"""FRED collector.

Two paths:
- Official API (api.stlouisfed.org) when FRED_API_KEY is set — full history,
  reliable. Preferred in CI.
- Keyless fredgraph.csv fallback — same data, but the endpoint is flaky
  (occasional 504s), hence aggressive retries.

OAS caveat: since April 2026 FRED serves only a rolling 3-year window for the
ICE BofA OAS series (BAMLH0A0HYM2, BAMLC0A0CM). The store's upsert is
append-only, so every observation we ever see is kept permanently. Pre-window
history lives in data/archive/ (see DECISIONS.md for provenance).
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# Revision-prone series whose LATEST-revised value differs from what was knowable
# in real time — economic releases (revised for months/years), model nowcasts, and
# the weekly-revised financial-conditions indices. Market data (rates, OAS, VIX,
# FX, dollar) is never revised, so it is deliberately excluded. SAHMREALTIME is
# already a point-in-time construct but is cheap to archive too. Overridable via
# config fred.vintage_series.
DEFAULT_VINTAGE_SERIES = [
    "PAYEMS", "INDPRO", "M2SL", "WEI", "GDPNOW",            # growth / money nowcasts
    "RECPROUSM156N", "THREEFYTP10", "SAHMREALTIME",         # recession-risk model series
    "STICKCPIM157SFRBATL", "CORESTICKM157SFRBATL",          # inflation nowcasts (revised)
    "FLEXCPIM157SFRBATL", "MEDCPIM158SFRBCLE",
    "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE",            # official CPI/PCE releases (revised; core PCE = Fed target)
    "PPIFIS", "PPIFES", "ECIALLCIV", "ECIWAG",             # PPI + ECI wage growth (revised)
    # DEFERRED — the Cleveland expected-inflation curve (EXPINF*) is a MODEL whose
    # whole history re-revises each release (like NFCI below), so it is excluded from
    # the bounded initial-release matrix.
    "STLFSI4",                                             # St. Louis financial-stress (revised)
    "UMCSENT", "MICH",                                      # surveys (revised)
    "ICSA", "IC4WSA", "CCSA",                              # jobless claims (revised the following week)
    # DEFERRED — the Indeed job-postings family (IHLIDXUS/IHLIDXNEWUS) re-revises its
    # whole history on each methodology change (like NFCI below) AND is copyrighted,
    # so it is intentionally excluded from the PIT vintage matrix.
    # DEFERRED — the Chicago Fed NFCI family (NFCI/ANFCI/NFCIRISK/NFCICREDIT/
    # NFCILEVERAGE) revises its WHOLE weekly history every release, so the initial-
    # release vintage matrix is large and the API read-times-out here. Add via
    # config fred.vintage_series with a patient connection if you need their PIT path.
]


class FredAdapter(Adapter):
    name = "fred"
    group = "fred"

    def __init__(self) -> None:
        self.cfg = config.load()["fred"]
        self.api_key = config.secret("FRED_API_KEY")

    def _all_series(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for grp in self.cfg["series"].values():
            out.update(grp)
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        consecutive_fails = 0
        for sid, col in self._all_series().items():
            if consecutive_fails >= 3 and not frames:
                # endpoint is down, not one bad series — stop burning retries
                errors.append("aborted remaining series: endpoint down")
                break
            try:
                frames[sid] = self._fetch_one(sid, col)
                consecutive_fails = 0
            except Exception as e:  # noqa: BLE001 — partial success allowed
                consecutive_fails += 1
                errors.append(f"{sid}: {e}")
        if not frames:
            raise RuntimeError(f"all FRED series failed: {errors}")
        if errors:
            # surfaced via logs; missing series simply stay at last stored date
            import logging
            logging.getLogger(__name__).warning("FRED partial failure: %s", errors)
        return frames

    def _fetch_one(self, sid: str, col: str) -> pd.DataFrame:
        if self.api_key:
            return self._fetch_api(sid, col)
        return self._fetch_csv(sid, col)

    def _fetch_api(self, sid: str, col: str) -> pd.DataFrame:
        r = self.http_get(
            self.cfg["api_url"],
            retries=self.cfg["retries"],
            backoff_base=self.cfg["backoff_base_s"],
            params={"series_id": sid, "api_key": self.api_key,
                    "file_type": "json", "limit": 100000},
        )
        obs = r.json()["observations"]
        df = pd.DataFrame(obs)[["date", "value"]]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.set_index("date").rename(columns={"value": col})
        return df.dropna()

    def _fetch_csv(self, sid: str, col: str) -> pd.DataFrame:
        r = self.http_get(
            f"{self.cfg['csv_url']}?id={sid}",
            retries=self.cfg["retries"],
            backoff_base=self.cfg["backoff_base_s"],
            timeout=90,
        )
        df = pd.read_csv(io.StringIO(r.text))
        if df.shape[1] != 2 or "observation_date" not in df.columns[0].lower().replace(" ", "_"):
            # fredgraph returns an HTML error page on failure; first col header
            # is normally 'observation_date' (legacy 'DATE')
            if df.columns[0].upper() not in ("DATE", "OBSERVATION_DATE"):
                raise ValueError(f"unexpected fredgraph response for {sid}: cols={list(df.columns)}")
        df.columns = ["date", col]
        df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.set_index("date").dropna()

    # --- ALFRED point-in-time vintages ------------------------------------- #
    # The live path above stores the LATEST-revised value per date, so a backtest
    # that reads it sees numbers nobody had in real time (e.g. payrolls revised
    # ~558k lower across the years after 2008; NFCI re-revised every week). ALFRED
    # serves the vintage history. We store the INITIAL RELEASE per period
    # (output_type=4): one row per period stamped with realtime_start = the date it
    # was FIRST published. That is bounded (~1 row/period — the full vintage matrix
    # is millions of rows for weekly-fully-revised series like NFCI and blows the
    # API's 100k cap) and is the standard point-in-time convention: it strips ALL
    # later revisions, the dominant look-ahead. as_of_series(date) then returns each
    # period's first-published value that was knowable by `date`. ADDITIVE — a
    # separate store the live regime engine does NOT read; it feeds point-in-time
    # macro backtests (and a future, separately-validated switch of the regime
    # inputs). Requires the API key (fredgraph has no vintages); skipped if absent.
    def _vintage_series(self) -> list[str]:
        return list(self.cfg.get("vintage_series", DEFAULT_VINTAGE_SERIES))

    def _fetch_vintage_one(self, sid: str, realtime_start: str) -> pd.DataFrame:
        r = self.http_get(
            self.cfg["api_url"],
            retries=self.cfg["retries"],
            backoff_base=self.cfg["backoff_base_s"],
            timeout=90,
            params={"series_id": sid, "api_key": self.api_key, "file_type": "json",
                    "output_type": 4,                      # initial release only (one row/period)
                    "realtime_start": realtime_start, "realtime_end": "9999-12-31",
                    "limit": 100000},

        )
        obs = r.json().get("observations", [])
        if not obs:
            return pd.DataFrame()
        df = pd.DataFrame(obs)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"]).rename(columns={"date": "period"})
        df["series"] = sid
        return df[["series", "period", "value", "realtime_start", "realtime_end"]]

    def fetch_vintages(self) -> pd.DataFrame:
        """Build the ALFRED vintage matrix for the revision-prone series and write
        data/fred_vintage/vintages.parquet. Returns the combined frame (empty if no
        API key)."""
        if not self.api_key:
            log.warning("FRED vintages need an API key (fredgraph has none) — skipping")
            return pd.DataFrame()
        rt0 = str(self.cfg.get("vintage_realtime_start", "1997-01-01"))
        frames, errors = [], []
        for sid in self._vintage_series():
            try:
                d = self._fetch_vintage_one(sid, rt0)
                if not d.empty:
                    frames.append(d)
            except Exception as e:  # noqa: BLE001 — partial success allowed
                errors.append(f"{sid}: {e}")
        if errors:
            log.warning("FRED vintage partial failure: %s", errors)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        for c in ("period", "realtime_start", "realtime_end"):
            out[c] = pd.to_datetime(out[c], errors="coerce")
        out = out.dropna(subset=["period", "realtime_start"]).reset_index(drop=True)
        p = config.data_dir() / "fred_vintage"
        p.mkdir(parents=True, exist_ok=True)
        out.to_parquet(p / "vintages.parquet")
        log.info("FRED vintages: %d rows across %d series (realtime from %s)",
                 len(out), out["series"].nunique(), rt0)
        return out


# --- point-in-time readers (module-level; no adapter needed) --------------- #
def _vintage_path():
    return config.data_dir() / "fred_vintage" / "vintages.parquet"


def load_vintages() -> pd.DataFrame | None:
    p = _vintage_path()
    return pd.read_parquet(p) if p.exists() else None


def as_of_series(series: str, asof, vintages: pd.DataFrame | None = None) -> pd.Series:
    """The series as it was KNOWN on `asof`: each period's first-published value
    whose release date (realtime_start) was on or before `asof`. The store holds
    initial releases, so this is the leak-free input a point-in-time macro backtest
    reads at each rebalance date — never the latest-revised value the live store
    keeps, and never a period not yet published by `asof`."""
    v = vintages if vintages is not None else load_vintages()
    if v is None:
        return pd.Series(dtype=float)
    asof = pd.Timestamp(asof)
    sub = v[(v["series"] == series) & (v["realtime_start"] <= asof)]
    if sub.empty:
        return pd.Series(dtype=float)
    return sub.set_index("period")["value"].sort_index()


def initial_release(series: str, vintages: pd.DataFrame | None = None) -> pd.Series:
    """First-published value per period (no date filter) — the full initial-release
    series, useful for release-surprise / nowcast studies."""
    v = vintages if vintages is not None else load_vintages()
    if v is None:
        return pd.Series(dtype=float)
    sub = v[v["series"] == series]
    return sub.set_index("period")["value"].sort_index() if not sub.empty else pd.Series(dtype=float)

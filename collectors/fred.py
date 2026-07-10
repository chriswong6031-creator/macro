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
from requests.utils import default_user_agent

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# fred.stlouisfed.org grew a bot-protection WAF (~June 2026) that resets the
# connection for the project's descriptive User-Agent AND for browser UAs, but
# lets the honest requests-library UA through. Send that on the keyless
# fredgraph.csv path. (The official API host, api.stlouisfed.org, is NOT gated —
# so setting FRED_API_KEY is the fully robust path and bypasses this entirely.)
# Imported by collectors/intl_macro.py and collectors/canada_macro.py, which also
# scrape fredgraph.csv keylessly.
FREDGRAPH_UA = default_user_agent()

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
            headers={"User-Agent": FREDGRAPH_UA},
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


# ---------------------------------------------------------------------------
# Multi-vintage collector (output_type=2) — additive; Track R W11-D MRI-R37
# The existing output_type=4 pipeline (initial-print-only) is untouched.
# ---------------------------------------------------------------------------

def fetch_all_vintages(
    series_id: str,
    output_type: int = 2,
    realtime_start: str = "1997-01-01",
    api_key: str | None = None,
) -> pd.DataFrame:
    """Fetch the full vintage matrix for a single series from ALFRED.

    output_type=2 returns ALL observation vintages in a WIDE matrix format:
    one row per observation period, one column per vintage (realtime) date,
    named "{series_id}_{YYYYMMDD}". This function melts it to LONG format:
    one row per (period, realtime_start) pair.

    output_type=4 returns the initial-release-only path (one row per period,
    long format directly from FRED). This function supports both output types.

    Requires FRED_API_KEY (no keyless path for vintage data).
    Returns an empty DataFrame if the key is unavailable (fail-open).

    Schema returned (long format):
        period (datetime), realtime_start (datetime), realtime_end (datetime),
        value (float).

    For output_type=2, realtime_end is inferred as the next vintage date minus 1 day
    (the period when that vintage value was the "current" value), with 9999-12-31
    for the latest vintage. This mirrors the ALFRED output_type=4 convention.

    Parameters
    ----------
    series_id:
        FRED series identifier, e.g. "PAYEMS".
    output_type:
        2 = all vintages/wide matrix, melted to long (default);
        4 = initial releases only, already long.
    realtime_start:
        ALFRED real-time start date (FRED's archive begins ~1997).
    api_key:
        Override the environment FRED_API_KEY; defaults to config.secret().
    """
    key = api_key or config.secret("FRED_API_KEY")
    if not key:
        log.warning(
            "fetch_all_vintages(%s): FRED_API_KEY absent — returning empty DataFrame",
            series_id,
        )
        return pd.DataFrame(
            columns=["period", "realtime_start", "realtime_end", "value"]
        )

    cfg = config.load()["fred"]
    api_url = cfg["api_url"]
    retries = cfg.get("retries", 4)
    backoff_base = cfg.get("backoff_base_s", 3)

    # Use a minimal Adapter subclass instance for the retry-capable http_get
    adapter = _VintageAdapter()

    all_chunks: list[pd.DataFrame] = []
    offset = 0
    limit = 100000

    while True:
        params = {
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "output_type": output_type,
            "realtime_start": realtime_start,
            "realtime_end": "9999-12-31",
            "sort_order": "asc",
            "limit": limit,
            "offset": offset,
        }
        r = adapter.http_get(api_url, retries=retries, backoff_base=backoff_base,
                             timeout=90, params=params)
        data = r.json()
        obs = data.get("observations", [])
        if not obs:
            break
        all_chunks.append(pd.DataFrame(obs))

        # FRED paginates at `limit` rows; if fewer returned, we're done
        if len(obs) < limit:
            break
        offset += limit
        log.debug(
            "fetch_all_vintages(%s): paginating, offset=%d, rows_so_far=%d",
            series_id,
            offset,
            sum(len(x) for x in all_chunks),
        )

    if not all_chunks:
        log.warning("fetch_all_vintages(%s): zero observations returned", series_id)
        return pd.DataFrame(
            columns=["period", "realtime_start", "realtime_end", "value"]
        )

    raw = pd.concat(all_chunks, ignore_index=True)

    if output_type == 2:
        # Wide format: columns are 'date' (the observation period) and
        # '{series_id}_{YYYYMMDD}' per vintage date. Melt to long.
        if "date" not in raw.columns:
            log.warning("fetch_all_vintages(%s): 'date' column missing in wide response", series_id)
            return pd.DataFrame(columns=["period", "realtime_start", "realtime_end", "value"])

        # Identify vintage columns: those named '{series_id}_YYYYMMDD'
        prefix = f"{series_id}_"
        vintage_cols = [c for c in raw.columns if c.startswith(prefix)]
        if not vintage_cols:
            log.warning(
                "fetch_all_vintages(%s): no vintage columns found (prefix=%s)", series_id, prefix
            )
            return pd.DataFrame(columns=["period", "realtime_start", "realtime_end", "value"])

        # Melt to long: id_vars='date', value_vars=vintage_cols
        melted = raw[["date"] + vintage_cols].melt(
            id_vars="date", var_name="vintage_col", value_name="value"
        )
        # Extract realtime_start date from column name suffix
        melted["realtime_start"] = pd.to_datetime(
            melted["vintage_col"].str[len(prefix):], format="%Y%m%d", errors="coerce"
        )
        melted = melted.rename(columns={"date": "period"})
        melted["period"] = pd.to_datetime(melted["period"], errors="coerce")
        melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
        melted = melted.dropna(subset=["period", "realtime_start", "value"])
        melted = melted[["period", "realtime_start", "value"]].copy()
        melted = melted.sort_values(["period", "realtime_start"]).reset_index(drop=True)

        # Infer realtime_end: the next vintage date for each vintage column minus 1 day,
        # 9999-12-31 for the latest vintage per period.
        # Sort vintage dates globally
        all_rt_dates = sorted(pd.to_datetime(vintage_cols, format=f"{prefix}%Y%m%d", errors="coerce").dropna())

        def _rt_end(rt: pd.Timestamp) -> pd.Timestamp:
            idx = all_rt_dates.index(rt) if rt in all_rt_dates else -1
            if idx == -1 or idx == len(all_rt_dates) - 1:
                return pd.Timestamp("9999-12-31")
            return all_rt_dates[idx + 1] - pd.Timedelta(days=1)

        melted["realtime_end"] = melted["realtime_start"].map(_rt_end)
        out = melted[["period", "realtime_start", "realtime_end", "value"]]

    else:
        # output_type=4: long format directly; columns: date, value, realtime_start, realtime_end
        raw = raw.rename(columns={"date": "period"})
        raw["value"] = pd.to_numeric(raw["value"], errors="coerce")
        for col in ("period", "realtime_start", "realtime_end"):
            if col in raw.columns:
                raw[col] = pd.to_datetime(raw[col], errors="coerce")
        raw = raw.dropna(subset=["period", "realtime_start", "value"])
        out = raw[["period", "realtime_start", "realtime_end", "value"]].sort_values(
            ["period", "realtime_start"]
        )

    out = out.reset_index(drop=True)
    log.info(
        "fetch_all_vintages(%s, output_type=%d): %d rows, %d unique periods",
        series_id,
        output_type,
        len(out),
        out["period"].nunique(),
    )
    return out


class _VintageAdapter(Adapter):
    """Minimal Adapter subclass for module-level multi-vintage fetches."""

    name = "fred_vintage_all"
    group = "fred_vintage"

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:  # type: ignore[override]
        return {}

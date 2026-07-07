"""Kalshi macro-release bracket-market collector (MRI PR-K).

Keyless read-only access to Kalshi's prediction markets for US macro releases:
CPI, payrolls (NFP), and initial jobless claims.  No authentication required —
the Kalshi v2 trade API returns market data for public series without any
Authorization header (confirmed live on 2026-07-07 against
https://api.elections.kalshi.com/trade-api/v2/).

== Taxonomy (LIVE VERIFIED 2026-07-07) ==

Series ticker  Target variable                  Strike units   Event pattern
KXCPI          US CPI headline MoM %, SA        pct (e.g. 0.3) KXCPI-{YY}{MON}
KXPAYROLLS     US non-farm payrolls MoM, k jobs level in jobs   KXPAYROLLS-{YY}{MON}
KXJOBLESSCLAIMS US initial jobless claims, level level in claims  KXJOBLESSCLAIMS-{YY}{MMDD}

Market question template: "Will CPI rise more than X%?" / "Will above X jobs be
added?" — each individual market is a binary that resolves YES when the actual
release exceeds the floor_strike.  P(YES) ≡ survival function value S(X) =
P(outcome > X).  The set of brackets over a single event forms a staircase of
S() values from which we extract:

  CDF:          F(X) = 1 - S(X) = 1 - P(YES at X)
  Implied pdf:  Δ mass at bracket [k_i, k_{i+1}) = F(k_{i+1}) - F(k_i)
  Median:       linear interpolation where CDF crosses 0.50
  Mean:         Σ k_i * mass_i (bracket midpoint weighted by mass)
  p_above(T):   S(T) — probability outcome exceeds threshold T
  p_below(T):   1 - S(T)

Prices: we use the MID (average of best bid and best ask) when both are
available, else the last traded price, else the yes_bid or yes_ask alone.
Kalshi prices are in cents (0-100); we normalize to probabilities (0-1).

== Storage ==

data/prediction_markets/kalshi_releases.parquet

Keyed (asof_date, release_type, period, strike) with keep="first" — a
row already in the store is never overwritten or re-dated (MRI-R6 PIT law).
Each row is a snapshot of one bracket at one date; the full distribution is
reconstructed by grouping on (asof_date, release_type, period).

Summary rows (one per snapshot) are stored at a lighter key
(asof_date, release_type, period) in the same parquet file via
the 'is_summary' flag, holding implied_median, implied_mean, p_above_*, etc.

Schema columns:
  asof_date     str   YYYY-MM-DD  collection date (UTC)
  release_type  str   cpi | nfp | claims
  period        str   YYYY-MM for CPI/NFP; YYYY-MM-DD (survey-week-end) for claims
  strike        float bracket floor_strike in native units
  p_survival    float P(outcome > strike) in [0, 1]; None if no price
  price_type    str   mid | last | bid | ask | missing
  is_summary    bool  True only on the per-(asof_date, release_type, period) summary row
  implied_median float|None  (summary rows only)
  implied_mean   float|None  (summary rows only)
  p_above_0     float|None  P(CPI > 0) / P(NFP > 0) / P(claims > reference)
  n_brackets    int|None    number of brackets with prices (summary rows only)
  event_ticker  str   Kalshi event_ticker (e.g. KXCPI-26JUN)
  close_time    str|None  ISO8601 market close time

Fail-open: any error in fetch or parse logs a warning and returns {} — the
collect lane is never blocked.  A 12-hour TTL prevents redundant re-fetches
within the same day's collect run.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kalshi v2 API — keyless, no auth header required (verified 2026-07-07)
# ---------------------------------------------------------------------------
_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# ---------------------------------------------------------------------------
# Series definitions (LIVE VERIFIED against Kalshi v2 /events endpoint, 2026-07-07)
#
# Series ticker  → description of target variable
# KXCPI         → US CPI headline MoM % (seasonally adjusted)
#                  each bracket: "Will CPI rise more than X%?"
#                  P(YES) = P(CPI MoM SA > X pct)
#                  Source: api.elections.kalshi.com, series_ticker=KXCPI
#
# KXPAYROLLS    → US non-farm payrolls MoM change (thousands, jobs)
#                  each bracket: "Will above X jobs be added in [month]?"
#                  P(YES) = P(NFP MoM > X jobs)
#                  Source: api.elections.kalshi.com, series_ticker=KXPAYROLLS
#                  (KXUSNFP is a distinct older series for the same underlying;
#                   KXPAYROLLS is the primary monthly series as of 2026-07-07)
#
# KXJOBLESSCLAIMS → US initial jobless claims, weekly level (count)
#                  each bracket: "How many initial jobless claims will there be
#                  the week ending [date]?" — exceedance binary
#                  P(YES) = P(claims level > X)
#                  Source: api.elections.kalshi.com, series_ticker=KXJOBLESSCLAIMS
# ---------------------------------------------------------------------------
_SERIES_CONFIG: dict[str, dict[str, Any]] = {
    "KXCPI": {
        "release_type": "cpi",
        "target_desc": "US CPI headline MoM % SA",
        "units": "pct_mom",
        "period_fmt": "monthly",  # YYYY-MM
    },
    "KXPAYROLLS": {
        "release_type": "nfp",
        "target_desc": "US non-farm payrolls MoM change, thousands",
        "units": "k_jobs",
        "period_fmt": "monthly",  # YYYY-MM
    },
    "KXJOBLESSCLAIMS": {
        "release_type": "claims",
        "target_desc": "US initial jobless claims, weekly level",
        "units": "level",
        "period_fmt": "weekly",   # YYYY-MM-DD (survey-week-end date)
    },
}

# Event ticker -> (release_type, period) parsing patterns
_CPI_EVENT_RE = re.compile(
    r"^KXCPI-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$",
    re.IGNORECASE,
)
_NFP_EVENT_RE = re.compile(
    r"^KXPAYROLLS-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$",
    re.IGNORECASE,
)
_CLAIMS_EVENT_RE = re.compile(r"^KXJOBLESSCLAIMS-(\d{2}[A-Z0-9]+)$", re.IGNORECASE)

_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# ---------------------------------------------------------------------------
# Price extraction helpers
# ---------------------------------------------------------------------------

def _mid_price(market: dict) -> tuple[float | None, str]:
    """Return (prob_survival, price_type) from a Kalshi market dict.

    Kalshi prices are in cents (0-100); we normalize to [0, 1].
    Priority: mid (bid+ask) > last_price > yes_bid > yes_ask > None.
    Returns P(outcome > strike) = P(YES).
    """
    yes_bid = market.get("yes_bid")
    yes_ask = market.get("yes_ask")
    last_price = market.get("last_price")

    def _norm(v: int | float | None) -> float | None:
        if v is None:
            return None
        try:
            return float(v) / 100.0
        except (TypeError, ValueError):
            return None

    bid = _norm(yes_bid)
    ask = _norm(yes_ask)
    last = _norm(last_price)

    if bid is not None and ask is not None:
        return (bid + ask) / 2.0, "mid"
    if last is not None:
        return last, "last"
    if bid is not None:
        return bid, "bid"
    if ask is not None:
        return ask, "ask"
    return None, "missing"


# ---------------------------------------------------------------------------
# Distribution math — PURE (testable without network)
# ---------------------------------------------------------------------------

def brackets_to_distribution(
    strikes: list[float],
    survivals: list[float | None],
) -> dict[str, float | None]:
    """Convert sorted bracket (strike, survival) pairs to distribution summary.

    Parameters
    ----------
    strikes   : sorted list of floor_strike values (ascending)
    survivals : P(outcome > strike) for each corresponding bracket;
                None entries are treated as missing and excluded

    Returns dict with keys:
        implied_median   float|None
        implied_mean     float|None
        p_above_0        float|None  — P(outcome > 0)
        n_brackets       int         — number of valid-price brackets
    """
    if not strikes or not survivals:
        return _null_distribution()

    # Filter to pairs with non-None, in-range survival values
    pairs = [
        (k, s) for k, s in zip(strikes, survivals)
        if s is not None and 0.0 <= s <= 1.0
    ]
    if not pairs:
        return _null_distribution()

    pairs_sorted = sorted(pairs, key=lambda x: x[0])
    ks = [p[0] for p in pairs_sorted]
    ss = [p[1] for p in pairs_sorted]

    # CDF: F(k) = 1 - S(k)
    cdfs = [1.0 - s for s in ss]

    # Implied median via linear interpolation of CDF
    implied_median = _interpolate_quantile(ks, cdfs, 0.50)

    # Implied mean: bracket midpoints weighted by probability mass
    # Mass in bracket [k_i, k_{i+1}): F(k_{i+1}) - F(k_i)
    # Bottom tail: mass below k[0] = F(k[0])
    # Top tail: mass above k[-1] = 1 - F(k[-1]) = S(k[-1])
    implied_mean = _bracket_mean(ks, cdfs)

    # p_above_0: interpolate S() at 0
    p_above_0 = _interpolate_survival(ks, ss, 0.0)

    return {
        "implied_median": implied_median,
        "implied_mean": implied_mean,
        "p_above_0": p_above_0,
        "n_brackets": len(pairs_sorted),
    }


def _null_distribution() -> dict[str, float | None]:
    return {
        "implied_median": None,
        "implied_mean": None,
        "p_above_0": None,
        "n_brackets": 0,
    }


def _interpolate_quantile(
    ks: list[float],
    cdfs: list[float],
    q: float,
) -> float | None:
    """Linear interpolation: find x where CDF = q.

    If q is below the lowest known CDF value or above the highest, returns
    the boundary strike without extrapolation.
    """
    if not ks:
        return None

    # Handle degenerate single bracket
    if len(ks) == 1:
        return ks[0] if abs(cdfs[0] - q) < 0.5 else None

    # q below the range: return lowest strike (can't extrapolate)
    if q <= cdfs[0]:
        return float(ks[0])

    # q above the range: return highest strike
    if q >= cdfs[-1]:
        return float(ks[-1])

    # Find the crossing bracket
    for i in range(1, len(ks)):
        if cdfs[i - 1] <= q <= cdfs[i]:
            # Linear interpolation
            denom = cdfs[i] - cdfs[i - 1]
            if abs(denom) < 1e-10:
                return float(ks[i - 1])
            frac = (q - cdfs[i - 1]) / denom
            return ks[i - 1] + frac * (ks[i] - ks[i - 1])

    return float(ks[-1])


def _bracket_mean(ks: list[float], cdfs: list[float]) -> float | None:
    """Estimate E[X] from the bracket CDF using midpoint rule.

    Represents each interval [k_{i-1}, k_i) as a point mass at the midpoint.
    Bottom tail mass (below ks[0]) is assigned to ks[0].
    Top tail mass (above ks[-1]) is assigned to ks[-1].
    """
    if not ks:
        return None
    if len(ks) == 1:
        return float(ks[0])

    total_mean = 0.0
    # Bottom tail
    total_mean += ks[0] * cdfs[0]
    # Interior brackets
    for i in range(1, len(ks)):
        mass = cdfs[i] - cdfs[i - 1]
        midpoint = (ks[i - 1] + ks[i]) / 2.0
        total_mean += midpoint * mass
    # Top tail
    top_mass = 1.0 - cdfs[-1]
    total_mean += ks[-1] * top_mass

    return total_mean


def _interpolate_survival(
    ks: list[float],
    ss: list[float],
    target: float,
) -> float | None:
    """Linear interpolation of survival S(target) from the sorted (ks, ss) pairs.

    Survival S(k) = P(outcome > k) is a non-increasing staircase. We interpolate
    linearly between bracket midpoints.  If target is outside the observed range
    we return the boundary S value without extrapolation.
    """
    if not ks:
        return None
    if target <= ks[0]:
        return ss[0]
    if target >= ks[-1]:
        return ss[-1]
    for i in range(1, len(ks)):
        if ks[i - 1] <= target <= ks[i]:
            denom = ks[i] - ks[i - 1]
            if abs(denom) < 1e-12:
                return ss[i - 1]
            frac = (target - ks[i - 1]) / denom
            return ss[i - 1] + frac * (ss[i] - ss[i - 1])
    return ss[-1]


# ---------------------------------------------------------------------------
# Period parsing
# ---------------------------------------------------------------------------

def _parse_event_period(event_ticker: str) -> tuple[str | None, str | None]:
    """Return (release_type, period_str) from a Kalshi event ticker.

    CPI:    KXCPI-26JUN         -> ('cpi',    '2026-06')
    NFP:    KXPAYROLLS-26JUL    -> ('nfp',    '2026-07')
    Claims: KXJOBLESSCLAIMS-26JUL09 -> ('claims', '2026-07-09')

    Returns (None, None) on unrecognised format.
    """
    m = _CPI_EVENT_RE.match(event_ticker)
    if m:
        yy, mon = m.group(1), m.group(2).upper()
        year = 2000 + int(yy)
        month = _MONTH_MAP[mon]
        return "cpi", f"{year}-{month:02d}"

    m = _NFP_EVENT_RE.match(event_ticker)
    if m:
        yy, mon = m.group(1), m.group(2).upper()
        year = 2000 + int(yy)
        month = _MONTH_MAP[mon]
        return "nfp", f"{year}-{month:02d}"

    m = _CLAIMS_EVENT_RE.match(event_ticker)
    if m:
        # Suffix after the year prefix: e.g. "26JUL09" → date-like "2026-07-09"
        suffix = m.group(1)  # e.g. "26JUL09"
        yy_str = suffix[:2]
        rest = suffix[2:]    # e.g. "JUL09"
        # Parse month+day from rest (3-char month abbrev + 2-digit day)
        mon_re = re.match(r"^([A-Z]{3})(\d{2})$", rest, re.IGNORECASE)
        if mon_re:
            mon = mon_re.group(1).upper()
            day = int(mon_re.group(2))
            year = 2000 + int(yy_str)
            month = _MONTH_MAP.get(mon)
            if month:
                return "claims", f"{year}-{month:02d}-{day:02d}"

    return None, None


# ---------------------------------------------------------------------------
# Parquet store
# ---------------------------------------------------------------------------

_STORE_PATH_RELATIVE = "prediction_markets/kalshi_releases.parquet"
_KEY_COLS = ["asof_date", "release_type", "period", "strike", "is_summary"]


def _upsert_parquet(path: Path, new_rows: pd.DataFrame) -> int:
    """First-seen append-only upsert keyed on _KEY_COLS.

    Returns the number of genuinely new rows written.
    """
    if new_rows.empty:
        return 0

    # Normalise key column types in new_rows before any dedup
    for col in _KEY_COLS:
        if col in new_rows.columns:
            new_rows[col] = new_rows[col].astype(str)

    if path.exists():
        existing = pd.read_parquet(path)
        for col in _KEY_COLS:
            if col in existing.columns:
                existing[col] = existing[col].astype(str)
        n_existing = len(existing)
        combined = pd.concat([existing, new_rows], ignore_index=True)
        combined = combined.drop_duplicates(subset=_KEY_COLS, keep="first")
        n_new = len(combined) - n_existing
    else:
        # Even on first write, dedup within the batch itself (first-seen wins)
        combined = new_rows.drop_duplicates(subset=_KEY_COLS, keep="first").copy()
        n_new = len(combined)

    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    return max(n_new, 0)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class KalshiReleasesAdapter(Adapter):
    """Kalshi macro-release bracket collector.

    Fetches all OPEN bracket markets for CPI, NFP (payrolls), and initial
    jobless claims from Kalshi's keyless v2 API.  Converts the exceedance-
    binary bracket ladders into implied distributions (median, mean, P(>0))
    and stores append-only first-seen snapshots.

    Fail-open: any network or parse error returns {} without raising.
    TTL: stale_after_days=0.5 — the collect lane runs this at most once
    per 12-hour window (bounded to daily cadence in practice).
    """

    name = "kalshi_releases"
    group = "kalshi_releases"
    stale_after_days = 1   # daily cadence; 12h effective TTL via collect runner

    def __init__(self) -> None:
        cfg = config.load()
        self.cfg = cfg.get("kalshi_releases", {})
        self._retries = self.cfg.get("retries", 3)
        self._timeout = self.cfg.get("timeout", 30)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Fetch all open bracket markets, compute distributions, upsert store.

        Fail-open: returns {} on any error.
        """
        try:
            return self._fetch_inner()
        except Exception as exc:  # noqa: BLE001 — fail-open contract
            log.warning(
                "kalshi_releases: fetch failed (%s: %s) — skipping",
                type(exc).__name__, exc,
            )
            return {}

    def _fetch_inner(self) -> dict[str, pd.DataFrame]:
        asof_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_rows: list[dict] = []

        for series_ticker, series_meta in _SERIES_CONFIG.items():
            try:
                rows = self._fetch_series(series_ticker, series_meta, asof_date)
                all_rows.extend(rows)
            except Exception as exc:  # noqa: BLE001 — fail-open per series
                log.warning(
                    "kalshi_releases: series %s failed (%s: %s) — skipping",
                    series_ticker, type(exc).__name__, exc,
                )

        if not all_rows:
            log.warning("kalshi_releases: no rows collected across all series")
            return {}

        new_df = pd.DataFrame(all_rows)
        store_path = config.data_dir() / _STORE_PATH_RELATIVE
        n_new = _upsert_parquet(store_path, new_df)

        log.info(
            "kalshi_releases: %d new rows written to store (asof=%s)",
            n_new, asof_date,
        )

        # Return a summary frame so the base runner can report rows/last_date
        today_ts = pd.Timestamp(asof_date)
        summary = pd.DataFrame(
            {"rows_written": [n_new]},
            index=pd.DatetimeIndex([today_ts], name="date"),
        )
        return {"kalshi_releases_snapshot": summary}

    def _fetch_series(
        self,
        series_ticker: str,
        series_meta: dict,
        asof_date: str,
    ) -> list[dict]:
        """Fetch all open markets for one series and return rows for the store."""
        url = f"{_BASE_URL}/markets"
        params: dict[str, Any] = {
            "series_ticker": series_ticker,
            "status": "open",
            "limit": 200,
        }

        rows: list[dict] = []
        cursor: str | None = None

        while True:
            if cursor:
                params["cursor"] = cursor

            resp = self.http_get(
                url,
                retries=self._retries,
                timeout=self._timeout,
                params=params,
            )
            data = resp.json()
            markets = data.get("markets") or []

            # Group by event_ticker
            by_event: dict[str, list[dict]] = {}
            for mkt in markets:
                et = mkt.get("event_ticker", "")
                if not et:
                    continue
                by_event.setdefault(et, []).append(mkt)

            for event_ticker, event_markets in by_event.items():
                release_type, period = _parse_event_period(event_ticker)
                if release_type is None or period is None:
                    log.debug(
                        "kalshi_releases: unrecognised event ticker %s — skipping",
                        event_ticker,
                    )
                    continue

                event_rows = self._process_event(
                    event_ticker, release_type, period, event_markets, asof_date,
                )
                rows.extend(event_rows)

            # Pagination
            cursor = data.get("cursor")
            if not cursor or not markets:
                break

        return rows

    def _process_event(
        self,
        event_ticker: str,
        release_type: str,
        period: str,
        markets: list[dict],
        asof_date: str,
    ) -> list[dict]:
        """Convert bracket markets for one event into store rows (bracket + summary)."""
        rows: list[dict] = []

        # Build (strike, p_survival, price_type, close_time) per bracket
        bracket_data: list[tuple[float, float | None, str, str | None]] = []

        for mkt in markets:
            strike = mkt.get("floor_strike")
            if strike is None:
                continue
            try:
                strike = float(strike)
            except (TypeError, ValueError):
                continue

            p_surv, price_type = _mid_price(mkt)
            close_time = mkt.get("close_time")

            bracket_data.append((strike, p_surv, price_type, close_time))
            rows.append({
                "asof_date": asof_date,
                "release_type": release_type,
                "period": period,
                "strike": strike,
                "p_survival": p_surv,
                "price_type": price_type,
                "is_summary": False,
                "implied_median": None,
                "implied_mean": None,
                "p_above_0": None,
                "n_brackets": None,
                "event_ticker": event_ticker,
                "close_time": close_time,
            })

        # Compute distribution summary from all brackets with prices
        if bracket_data:
            sorted_brackets = sorted(bracket_data, key=lambda x: x[0])
            strikes = [b[0] for b in sorted_brackets]
            survivals = [b[1] for b in sorted_brackets]
            dist = brackets_to_distribution(strikes, survivals)

            close_time_ref = sorted_brackets[0][3] if sorted_brackets else None
            rows.append({
                "asof_date": asof_date,
                "release_type": release_type,
                "period": period,
                "strike": float("nan"),   # summary rows have no single strike
                "p_survival": None,
                "price_type": "summary",
                "is_summary": True,
                "implied_median": dist["implied_median"],
                "implied_mean": dist["implied_mean"],
                "p_above_0": dist["p_above_0"],
                "n_brackets": dist["n_brackets"],
                "event_ticker": event_ticker,
                "close_time": close_time_ref,
            })

        return rows

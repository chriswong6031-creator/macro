"""Google Trends weekly relative search-interest -> a DISPLAY-ONLY attention chip
for the Stage Analysis page (SGA masterplan §W4).

Keyless via `pytrends` (an unofficial Google Trends client). One parquet per ticker
under data/google_trends/, date-indexed weekly, `interest` in [0,100] (Google's own
relative scale — 100 = the peak week within the requested window), plus a 2nd
`_norm` column so run_adapter's single-column outlier guard never clips a genuine
attention SPIKE (a viral surge is precisely the signal — mirrors wiki_pageviews).

Term map: config/narrative_sources.yml `google_trends:` (ticker -> a brand/product
search term where consumer search interest is a meaningful demand proxy — AAPL:'iphone',
TSLA:'tesla'). The map is deliberately small and hand-curated (only liquid, brand-name
names where search interest tracks a real signal); it grows with the stage board.

Honest prior (shown on the page): search interest -> a CROWDING / fade-risk CAUTION,
not a directional buy signal — an attention spike marks late-cycle enthusiasm at least
as often as an early trend. It is context, never a gate (SGA-R2/R4 discipline).

FRAGILITY: pytrends scrapes an undocumented endpoint that Google rate-limits (HTTP 429)
and may not be installed at all. Both are EXPECTED, not exceptional:
  * pytrends absent            -> expected_failure set -> runner reports 'blocked' (no-op)
  * HTTP 429 / block mid-run   -> stop the run, keep whatever landed, one ::warning::
Never crashes the nightly. ~20 names/night on a rotating daily offset over the full map,
5-10 s between calls (Google blocks aggressive polling fast).
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

TOP_N = 20            # names per run (Google blocks fast; a small daily slice rotates)
PACE_S = 7.0         # 5-10 s between calls — Google rate-limits aggressive polling
ROTATE_SALT = "google_trends_v1"   # stable salt for daily offset rotation
TIMEFRAME = "today 12-m"           # ~52 weekly points; Google returns weekly buckets here
GEO = "US"                         # US search interest (the equity universe is US-listed)


def _today_offset(n_total: int, n_pick: int) -> int:
    """Deterministic daily offset so coverage rotates across the full term map."""
    day_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    h = int(hashlib.md5(f"{ROTATE_SALT}:{day_str}".encode()).hexdigest(), 16)
    if n_total <= n_pick:
        return 0
    return h % (n_total - n_pick + 1)


def _term_map() -> dict[str, str]:
    """{TICKER: search_term} from config/narrative_sources.yml `google_trends:`.

    Fail-open: a missing file / missing section / malformed rows yield {} (the
    adapter then no-ops with a warning rather than raising into a hard failure)."""
    try:
        import yaml
        path = config.ROOT / "config" / "narrative_sources.yml"
        if not path.exists():
            return {}
        doc = yaml.safe_load(path.read_text()) or {}
        section = doc.get("google_trends") or {}
        terms = section.get("terms") or {}
        out: dict[str, str] = {}
        for tk, term in terms.items():
            if tk and term and str(term).strip():
                out[str(tk).upper()] = str(term).strip()
        return out
    except Exception as e:  # noqa: BLE001 — config problem never crashes the run
        log.warning("google_trends: term map unreadable (%s) — no-op", e)
        return {}


def parse_interest(df: pd.DataFrame, term: str) -> pd.DataFrame:
    """Pure: a pytrends `interest_over_time()` frame -> a date-indexed
    (interest, _norm) frame. Returns an empty frame when the term column is
    absent (Google returned no data for it) or all-zero.

    pytrends returns a DataFrame indexed by date with one column per keyword plus
    an `isPartial` flag column; the trailing partial-week bucket is dropped so the
    stored series is completed-week-only (stable, no same-week churn)."""
    if df is None or df.empty or term not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    if "isPartial" in out.columns:
        # drop any partial (incomplete current-week) buckets — keep completed weeks only
        partial = out["isPartial"].astype(str).str.lower().isin(("true", "1"))
        out = out[~partial]
    if out.empty:
        return pd.DataFrame()
    s = pd.to_numeric(out[term], errors="coerce").dropna()
    if s.empty or float(s.abs().sum()) == 0.0:
        return pd.DataFrame()
    res = pd.DataFrame({"interest": s.astype(float)})
    res.index = pd.to_datetime(res.index)
    res = res.sort_index()
    # 2nd column so run_adapter's outlier_col guard is disabled (a viral attention
    # SPIKE must not be clipped) — mirrors collectors/wiki_pageviews.py's log_views.
    res["_norm"] = np.log1p(res["interest"])
    return res


class GoogleTrendsAdapter(Adapter):
    name = "google_trends"
    group = "google_trends"
    stale_after_days = 10   # weekly series on a rotating ~20/night slice; lag tolerated

    def __init__(self) -> None:
        # pytrends is an optional dep (an unofficial scraper). Its absence is an
        # EXPECTED failure, not a crash — mark it so the runner reports 'blocked'
        # (mirrors the gated-plane collectors' expected_failure idiom).
        self.expected_failure: str | None = None
        try:
            import pytrends  # noqa: F401
        except Exception:  # noqa: BLE001 — ImportError or a broken transitive dep
            self.expected_failure = "pytrends not installed — Google Trends lane skipped"

    def _client(self):
        """Build a pytrends client. Isolated so tests can monkeypatch it and the
        import stays lazy (module absent -> expected_failure already set in init)."""
        from pytrends.request import TrendReq
        # hl/tz are cosmetic; a modest backoff softens Google's rate limiting.
        return TrendReq(hl="en-US", tz=0, retries=2, backoff_factor=0.3)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if self.expected_failure:
            # Belt-and-braces: init already flagged it, but if fetch is called
            # directly, degrade to a no-op raise the runner classifies as 'blocked'.
            raise RuntimeError(self.expected_failure)

        term_map = _term_map()
        if not term_map:
            raise ValueError("google_trends: empty term map "
                             "(config/narrative_sources.yml google_trends.terms)")

        # deterministic daily rotation over a stable ticker ordering
        tickers = sorted(term_map)
        offset = _today_offset(len(tickers), TOP_N)
        batch = tickers[offset: offset + TOP_N]

        try:
            client = self._client()
        except Exception as e:  # noqa: BLE001 — client build failed (import/scrape break)
            if is_connection_error(e):
                raise
            log.warning("google_trends: client build failed (%s) — no-op this run", e)
            return {}

        frames: dict[str, pd.DataFrame] = {}
        errors = 0
        blocked = False
        for tk in batch:
            term = term_map[tk]
            try:
                client.build_payload([term], timeframe=TIMEFRAME, geo=GEO)
                raw = client.interest_over_time()
                df = parse_interest(raw, term)
                if not df.empty:
                    frames[tk] = df
            except Exception as e:  # noqa: BLE001 — one term never kills the run
                if is_connection_error(e):
                    raise
                msg = str(e).lower()
                if "429" in msg or "too many requests" in msg or "rate" in msg:
                    log.warning("google_trends: rate-limited on %s (%s) — stopping run",
                                tk, e)
                    blocked = True
                    break
                log.debug("google_trends %s (%s): %s", tk, term, e)
                errors += 1
            time.sleep(PACE_S)

        if blocked:
            log.warning("google_trends: blocked after %d terms; stored %d series so far",
                        len(frames), len(frames))
        else:
            log.info("google_trends: %d terms polled, %d stored, %d errors",
                     len(batch), len(frames), errors)
        if not frames:
            # Nothing landed this run. Raise so the runner records a transient failure
            # (circuit breaker sees it) rather than silently reporting 'ok, 0 rows'.
            raise ValueError("google_trends: no term resolved to interest this run")
        return frames


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    GoogleTrendsAdapter().fetch()

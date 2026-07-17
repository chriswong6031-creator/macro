"""SEC EDGAR quarterly diluted-EPS panel for the SUE earnings-momentum factor.

The annual fundamentals panel (collectors/edgar.py) carries only annual NetIncome,
which cannot express the QUARTERLY earnings surprise (SUE / post-earnings-announcement
drift) the literature documents. This module fetches the quarterly
EarningsPerShareDiluted frames (CY{year}Q{1..4}, uom USD-per-shares) — one keyless
call per calendar quarter, ~5k filers each — and builds a long point-in-time panel
keyed (ticker, period_end).

The frames API does NOT carry the filing date, so for the PIT as-of we overlay the
REAL earliest SEC filing date of each quarter's diluted-EPS, fetched per company from
the keyless companyconcept API (`fetch_eps_filing_dates`, full history in one call/CIK,
earliest `filed` per `end` = the original disclosure, ignoring later comparative re-tags).
This is the date the surprise actually became public (median ~34d after quarter-end, vs
the old synthetic +60d which made every surprise look ~26d staler and clustered ~74% of
names at one value) — it sharpens the PEAD-freshness decay in engine.stock_score and is
strictly more point-in-time-accurate. A company whose filing date is unavailable falls
back to the synthetic period_end + `quarterly_lag_days`. See scripts/validate_sue.py,
scripts/pead_freshness_phase0.py and research/DATA_SIGNAL_EXPANSION_2026.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

import time

from collectors.edgar import _cfg, _frame, _get_json, _ticker_cik_map, _universe_tickers
from lib import config

log = logging.getLogger(__name__)

EPS_CONCEPT = "EarningsPerShareDiluted"
EPS_UNIT = "USD-per-shares"
# companyconcept reports the unit as "USD/shares" (the frames endpoint uses "USD-per-shares").
_CC_UNITS = ("USD/shares", "USD-per-shares")
# only the ORIGINAL periodic reports tag the canonical quarter/year EPS. Excluding the
# amendments (10-K/A, 10-Q/A) and the 8-K earnings release keeps the filing-date source
# CONSISTENT across names (amendments file later anyway, so min() would skip them; 8-K EPS
# tagging is inconsistent and only ~a few days earlier than the 10-Q).
_ORIG_FORMS = {"10-Q", "10-K"}


def eps_panel_path():
    return config.data_dir() / "edgar" / "eps_quarterly.parquet"


def _filing_dates_path():
    return config.data_dir() / "edgar" / "eps_filing_dates.parquet"


def _built_age_days(cache_path) -> float | None:
    """Age of a weekly cache in days, from its sidecar meta's `built` stamp
    (<name>_meta.json next to the parquet) — NEVER file mtime. On CI runners a
    checkout rewrites files with mtime = checkout time, so a committed
    months-old cache always looks brand-new by mtime and the refresh
    short-circuits forever (the polygon-universe frozen-cache class, #2690;
    eps_quarterly.parquet froze at its 2026-06-14 fill the same way). The meta
    is written only when a GOOD pass lands a new cache, so a partial/aborted
    pass keeps retrying nightly instead of freezing for a week. Missing or
    unreadable meta returns None — callers treat that as stale."""
    meta_p = cache_path.with_name(cache_path.stem + "_meta.json")
    try:
        import json
        built = json.loads(meta_p.read_text()).get("built")
        if not built:
            return None
        built_dt = datetime.fromisoformat(str(built))
        if built_dt.tzinfo is None:
            built_dt = built_dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - built_dt).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return None


def _write_built_meta(cache_path, n_rows: int) -> None:
    """Stamp the sidecar meta after a successful cache write (fetch-date stamp)."""
    import json
    meta_p = cache_path.with_name(cache_path.stem + "_meta.json")
    try:
        meta_p.write_text(json.dumps(
            {"built": datetime.now(timezone.utc).isoformat(), "rows": int(n_rows)}))
    except Exception as e:  # noqa: BLE001
        log.warning("edgar_eps: cannot write %s (%s)", meta_p, e)


def _fd_frame(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    fd = pd.DataFrame(rows, columns=["ticker", "period_end", "filed_date"])
    fd["period_end"] = pd.to_datetime(fd["period_end"], errors="coerce")
    fd["filed_date"] = pd.to_datetime(fd["filed_date"], errors="coerce")
    return fd.dropna(subset=["period_end", "filed_date"]).drop_duplicates(["ticker", "period_end"])


def fetch_eps_filing_dates(cik2tic: dict[int, str], *, max_age_days: int = 7,
                           force: bool = False, max_seconds: float = 540.0,
                           min_coverage: float = 0.5) -> pd.DataFrame:
    """Per (ticker, period_end) the REAL earliest SEC filing date of that quarter's
    diluted-EPS, from the keyless EDGAR companyconcept API — one call per CIK, full
    history. For each (cik, end) we take min(`filed`) across the ORIGINAL 10-Q/10-K facts
    so amendments and later comparative re-tags (a Q1 value re-reported in next year's
    10-Q) NEVER overwrite the ORIGINAL disclosure date. This becomes the SUE panel's PIT
    as-of (the date the surprise became public) in place of the synthetic period_end + lag
    — sharpening the PEAD-freshness decay in engine.stock_score.

    Weekly-cached to data/edgar/eps_filing_dates.parquet (freshness judged from the
    sidecar meta's built stamp, never mtime — see _built_age_days). HARDENED for
    CI (runs inside the time-boxed engine job): a `max_seconds` wall-clock BUDGET bounds the
    ~1100-CIK pass so an SEC 429/throttle episode (whose per-call backoff could otherwise
    run ~85min) can never blow the job timeout — on a budget hit we keep what we have and
    stop. And a partial / budget-capped / empty pass (coverage < `min_coverage`) NEVER
    overwrites a good prior cache (returns it instead), so one throttled run can't poison the
    cache for a week. Graceful throughout: a CIK that 404s is skipped (its rows fall back to
    the synthetic lag). Columns: ticker, period_end, filed_date."""
    p = _filing_dates_path()
    if not force and p.exists():
        age_d = _built_age_days(p)
        if age_d is not None and age_d < max_age_days:
            log.info("eps_filing_dates cache fresh (%.1fd) — skip fetch", age_d)
            return pd.read_parquet(p)
    host = _cfg()["base_url"].split("/api/")[0]            # https://data.sec.gov
    retries = int(_cfg().get("retries", 3))
    rows: list[tuple[str, str, str]] = []
    n_ok, n_seen, capped = 0, 0, False
    t0 = time.monotonic()
    for cik, tic in cik2tic.items():
        if time.monotonic() - t0 > max_seconds:           # wall-clock budget — never blow CI
            capped = True
            log.warning("eps_filing_dates: %.0fs budget hit after %d/%d CIKs — stopping",
                        max_seconds, n_seen, len(cik2tic))
            break
        n_seen += 1
        url = f"{host}/api/xbrl/companyconcept/CIK{int(cik):010d}/us-gaap/{EPS_CONCEPT}.json"
        data = _get_json(url, retries)
        time.sleep(0.12)                                  # SEC fair-access pacing (<10 req/s)
        if not data:
            continue
        units = data.get("units") or {}
        facts = next((units[u] for u in _CC_UNITS if u in units), [])
        earliest: dict[str, str] = {}
        for f in facts:
            end, filed = f.get("end"), f.get("filed")
            if not end or not filed or f.get("form") not in _ORIG_FORMS:
                continue
            cur = earliest.get(end)
            if cur is None or filed < cur:                # ISO dates sort lexicographically
                earliest[end] = filed
        if earliest:
            n_ok += 1
            rows.extend((tic, end, filed) for end, filed in earliest.items())
    coverage = n_ok / max(len(cik2tic), 1)
    if not rows or capped or coverage < min_coverage:
        # a partial/aborted pass must not clobber a good prior cache.
        if p.exists():
            log.warning("eps_filing_dates: partial pass (%.0f%% coverage%s) — retaining prior cache",
                        100 * coverage, ", budget-capped" if capped else "")
            return pd.read_parquet(p)
        if not rows:
            return pd.DataFrame(columns=["ticker", "period_end", "filed_date"])
        log.warning("eps_filing_dates: partial cold pass (%.0f%%) — using %d rows WITHOUT caching "
                    "(next build retries)", 100 * coverage, len(rows))
        return _fd_frame(rows)
    fd = _fd_frame(rows)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd.to_parquet(p)
    _write_built_meta(p, len(fd))
    log.info("eps_filing_dates: %d (ticker,quarter) rows from %d/%d CIKs (%.0f%% coverage)",
             len(fd), n_ok, len(cik2tic), 100 * coverage)
    return fd


def _apply_filing_dates(df: pd.DataFrame, fd: pd.DataFrame | None, *, lag: int) -> pd.DataFrame:
    """Overlay the real SEC filing date onto `asof_date` where available and valid
    (filed_date >= period_end — a date earlier than the period close is junk and is
    ignored). Rows without a real date KEEP their synthetic period_end + lag as-of, so a
    missing filing date degrades to the conservative fallback, never to NaT (NaT would
    silently hide the row in sue_cross_section's asof_date<=d gate). Pure → unit-tested."""
    if fd is None or fd.empty:
        return df
    out = df.merge(fd, on=["ticker", "period_end"], how="left")
    real = out["filed_date"].notna() & (out["filed_date"] >= out["period_end"])
    out.loc[real, "asof_date"] = out.loc[real, "filed_date"]
    log.info("eps_quarterly: %d/%d rows (%.0f%%) use the REAL filing date "
             "(rest fall back to period_end + %dd)",
             int(real.sum()), len(out), 100.0 * (real.mean() if len(out) else 0), lag)
    return out.drop(columns=["filed_date"])


def build_eps_panel(start_year: int = 2008, end_year: int | None = None,
                    reporting_lag_days: int | None = None,
                    max_age_days: int = 7, force: bool = False) -> pd.DataFrame:
    """Fetch the quarterly diluted-EPS frames and write data/edgar/eps_quarterly.parquet.
    Columns: ticker, period_end, eps_q, asof_date. Universe = S&P 1500 breadth caches.
    Weekly-cached (like the annual panel): a fresh parquet is returned without refetching
    the ~72 frames, so the daily build only recomputes the factor ranks."""
    p = eps_panel_path()
    if not force and p.exists():
        age_d = _built_age_days(p)
        if age_d is not None and age_d < max_age_days:
            log.info("eps_quarterly cache fresh (%.1fd) — skip fetch", age_d)
            return pd.read_parquet(p)
    if end_year is None:
        end_year = datetime.now(timezone.utc).year
    lag = reporting_lag_days if reporting_lag_days is not None \
        else int(_cfg().get("quarterly_lag_days", 60))
    universe = _universe_tickers()
    if not universe:
        # no-regress: a lane without breadth caches (re-render / fresh clone)
        # returns the prior panel rather than raising — same fallback shape as
        # the sibling collectors (finra/sec_insider). Raise only cold-start.
        if p.exists():
            log.warning("eps_quarterly: no breadth close caches — retaining prior panel")
            return pd.read_parquet(p)
        raise RuntimeError("no breadth close caches — run breadth collectors first")
    tic_cik = _ticker_cik_map(universe, end_year - 1)
    cik2tic: dict[int, str] = {}
    for t, c in tic_cik.items():
        cik2tic.setdefault(int(c), t)        # dedup dual-class: first ticker per CIK
    base = _cfg()["base_url"]
    rows: list[tuple[str, str, float]] = []
    for year in range(start_year, end_year + 1):
        for q in ("Q1", "Q2", "Q3", "Q4"):
            fr = _frame(base, EPS_CONCEPT, f"CY{year}{q}", EPS_UNIT)
            for cik, (eps, end) in fr.items():
                t = cik2tic.get(cik)
                if t and end:
                    rows.append((t, end, float(eps)))
    if not rows:
        # no-regress: an SEC outage keeps the prior panel (meta NOT bumped, so the
        # next build retries); raise only when there is nothing to fall back to.
        if p.exists():
            log.warning("eps_quarterly: no frames returned (SEC unreachable?) — retaining prior panel")
            return pd.read_parquet(p)
        raise RuntimeError("no quarterly EPS frames returned (SEC unreachable?)")
    df = pd.DataFrame(rows, columns=["ticker", "period_end", "eps_q"])
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    df = df.dropna(subset=["period_end"]).sort_values("period_end")
    # one EPS per (ticker, period_end): a duration frame may carry near-dup rows
    df = df.drop_duplicates(["ticker", "period_end"], keep="last").reset_index(drop=True)
    # synthetic period_end + lag is the FALLBACK as-of; overlay the real SEC filing date
    # (the actual public date of the surprise) wherever companyconcept supplies it.
    df["asof_date"] = df["period_end"] + pd.Timedelta(days=lag)
    try:
        df = _apply_filing_dates(df, fetch_eps_filing_dates(cik2tic, force=force), lag=lag)
    except Exception as e:  # noqa: BLE001 — overlay is additive, never fatal
        log.warning("real filing-date overlay skipped (%s) — synthetic lag retained", e)
        df = df.drop(columns=[c for c in ("filed_date",) if c in df.columns])
    p = eps_panel_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)
    _write_built_meta(p, len(df))
    log.info("eps_quarterly: %d rows, %d tickers, %s..%s", len(df), df["ticker"].nunique(),
             df["period_end"].min().date(), df["period_end"].max().date())
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_eps_panel()

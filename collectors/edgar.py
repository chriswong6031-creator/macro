"""SEC EDGAR XBRL fundamentals collector for the cross-sectional factor engine.

The EDGAR "frames" API returns ONE us-gaap concept across EVERY filer for a
calendar period in a single keyless call (data.sec.gov/api/xbrl/frames/...).
That makes a genuine fundamentals cross-section buildable for free — no
Compustat/I-B-E-S vendor — which we join to the S&P 1500 price universe already
in the breadth close caches.

We pull a small set of concepts for the latest complete fiscal year (+ the prior
year where a factor needs a change), filter to our universe, and write a wide
ticker-indexed table to data/edgar/fundamentals.parquet. Fundamentals move
quarterly, so the fetch is cached (refreshed weekly); the factor RANKS recompute
daily from this cache + fresh prices (market cap = price x shares).

Honesty: free fundamentals are sparse for some tags (dividends/buybacks/gross
profit), fiscal-year-ends differ (we scan the 4 quarterly instantaneous frames
and keep each filer's most recent balance), and values are lagged to the filing
period (no look-ahead). Factors are ranks/context, not a backtested alpha.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# instantaneous (balance-sheet) concepts — scanned across the 4 quarter frames
BALANCE = {
    "assets": "Assets",
    "equity": "StockholdersEquity",
    "debt_lt": "LongTermDebtNoncurrent",
}
SHARES_USGAAP = "CommonStockSharesOutstanding"
SHARES_DEI = "EntityCommonStockSharesOutstanding"
# duration (flow) concepts — single annual frame CY{fy}
FLOW = {
    "ni": "NetIncomeLoss",
    "gross_profit": "GrossProfit",
    "cfo": "NetCashProvidedByUsedInOperatingActivities",
    "dividends": "PaymentsOfDividendsCommonStock",
    "repurchases": "PaymentsForRepurchaseOfCommonStock",
    # W2 PR-H additions (Long-Hold Thesis Layer, 2026-07-06):
    # op_income: needed to un-alias quality_z ≡ profitability_z (W1 kill-test finding)
    # interest_exp: needed for interest_coverage (was 0% coverage in W1 due to absence here)
    "op_income": "OperatingIncomeLoss",
    "interest_exp": "InterestExpense",
}
REVENUE_CONCEPTS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]


def _cfg() -> dict:
    return config.load()["edgar"]


def _headers() -> dict:
    return {"User-Agent": _cfg()["user_agent"], "Accept-Encoding": "gzip, deflate"}


def _get_json(url: str, retries: int = 3) -> dict | None:
    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(), timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 — tolerate per-frame failure
            if attempt == retries - 1:
                log.warning("edgar GET failed %s: %s", url.split("/api/")[-1], e)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def _frame(base: str, concept: str, period: str, unit: str) -> dict[int, tuple[float, str]]:
    """{cik: (val, end_date)} for one concept/period frame (empty on miss)."""
    url = f"{base}/{concept}/{unit}/{period}.json"
    data = _get_json(url, _cfg()["retries"])
    time.sleep(0.12)                       # SEC fair-access pacing (<10 req/s)
    if not data or "data" not in data:
        return {}
    return {int(r["cik"]): (float(r["val"]), r.get("end", "")) for r in data["data"]
            if r.get("val") is not None}


_SUFFIX = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
           "HOLDINGS", "HOLDING", "GROUP", "THE", "CLASS", "COM", "NEW", "LP",
           "LLC", "TRUST", "INCORPORATED", "INTERNATIONAL", "INTL", "&"}


def _norm_name(s: str) -> str:
    s = s.upper()
    for ch in ".,&/'-()":
        s = s.replace(ch, " ")
    toks = [t for t in s.split() if t and t not in _SUFFIX and not (len(t) == 1)]
    return " ".join(toks)


def _frame_names(base: str, concept: str, period: str, unit: str) -> dict[int, str]:
    """{cik: entityName} for one frame (used by the name-matching fallback)."""
    data = _get_json(f"{base}/{concept}/{unit}/{period}.json", _cfg()["retries"])
    time.sleep(0.12)
    if not data or "data" not in data:
        return {}
    return {int(r["cik"]): r.get("entityName", "") for r in data["data"]}


def _universe_names() -> dict[str, str]:
    """{ticker: company name} from the breadth constituents tables."""
    out: dict[str, str] = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            meta = pd.read_parquet(p)
            for t, row in meta.iterrows():
                out.setdefault(str(t), str(row.get("name", t)))
    return out


def _latest_balance_dated(concept: str, year: int) -> dict[int, tuple[float, str]]:
    """{cik: (val, end_date)} — most recent instantaneous value per CIK across the
    4 quarter frames of a year (a Sep-FY firm lands in Q3I, a Dec-FY in Q4I). The
    end date is what the point-in-time panel stamps as the period close."""
    base = _cfg()["base_url"]
    best: dict[int, tuple[float, str]] = {}
    for q in ("Q4I", "Q3I", "Q2I", "Q1I"):
        for cik, (val, end) in _frame(base, concept, f"CY{year}{q}", "USD").items():
            if cik not in best or end > best[cik][1]:
                best[cik] = (val, end)
    return best


def _latest_balance(concept: str, year: int) -> dict[int, float]:
    """Most recent instantaneous value per CIK across the 4 quarter frames of a
    year — covers all fiscal-year-ends (a Sep-FY firm lands in Q3I, a Dec-FY in
    Q4I)."""
    return {cik: v for cik, (v, _e) in _latest_balance_dated(concept, year).items()}


def _annual(concept: str, year: int, unit: str = "USD") -> dict[int, float]:
    return {cik: v for cik, (v, _e) in _frame(_cfg()["base_url"], concept, f"CY{year}", unit).items()}


def _shares(year: int) -> dict[int, float]:
    """Shares outstanding: us-gaap balance scan, dei cover-page fallback."""
    out = _latest_balance_shares(SHARES_USGAAP, year, _cfg()["base_url"])
    dei_base = _cfg()["shares_url"]
    best: dict[int, tuple[float, str]] = {}
    for q in ("Q4I", "Q3I", "Q2I", "Q1I"):
        for cik, (val, end) in _frame(dei_base, SHARES_DEI, f"CY{year}{q}", "shares").items():
            if cik not in best or end > best[cik][1]:
                best[cik] = (val, end)
    for cik, (val, _e) in best.items():
        out.setdefault(cik, val)           # only fill gaps us-gaap missed
    return out


def _latest_balance_shares(concept: str, year: int, base: str) -> dict[int, float]:
    best: dict[int, tuple[float, str]] = {}
    for q in ("Q4I", "Q3I", "Q2I", "Q1I"):
        for cik, (val, end) in _frame(base, concept, f"CY{year}{q}", "shares").items():
            if cik not in best or end > best[cik][1]:
                best[cik] = (val, end)
    return {cik: v for cik, (v, _e) in best.items()}


def _universe_tickers() -> list[str]:
    """Current S&P 1500 tickers (breadth close caches) UNION names that have dropped
    out of the index (the membership ledger marks them inactive) — so the panel
    retains delisted names' fundamentals going forward (the fundamentals half of the
    survivorship fix; pairs with engine/universe_history.py)."""
    tickers: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            tickers.update(pd.read_parquet(p, columns=None).columns)
    try:                                   # additive — never fatal if the ledger is absent
        from engine.universe_history import dropped_members
        tickers.update(dropped_members())
    except Exception:  # noqa: BLE001
        pass
    return sorted(tickers)


def _load_company_tickers() -> dict | None:
    """SEC's ticker->CIK file, cached locally (it rarely changes and www.sec.gov
    rate-limits hard). Fetch only if the cache is missing/stale; fall back to the
    cache on any fetch failure."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    fresh = False
    if cache.exists():
        try:
            age_d = (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime) / 86400.0
            fresh = age_d < 30
        except Exception:  # noqa: BLE001
            fresh = True
    if not fresh:
        data = _get_json(_cfg()["tickers_url"], _cfg()["retries"])
        if data:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data))
            return data
    if cache.exists():
        return json.loads(cache.read_text())
    return None


def _ticker_cik_map(universe: list[str], fy: int) -> dict[str, int]:
    """ticker -> CIK. Primary: SEC company_tickers.json (exact, cached). Fallback
    when that endpoint is blocked: match the frame entityName against our universe
    company names (normalized)."""
    data = _load_company_tickers()
    if data:
        sec = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
        out: dict[str, int] = {}
        for t in universe:
            u = t.upper()
            for cand in (u, u.replace("-", "."), u.replace(".", "-"),
                         u.split("-")[0], u.split(".")[0]):
                if cand in sec:
                    out[t] = sec[cand]
                    break
        if len(out) >= 0.5 * len(universe):
            return out
        log.warning("company_tickers mapped only %d/%d — augmenting with name match",
                    len(out), len(universe))
    else:
        out = {}
        log.warning("company_tickers.json unavailable — using entityName fallback map")

    # name-matching fallback (or augmentation)
    base = _cfg()["base_url"]
    cik_name: dict[int, str] = {}
    for q in ("Q4I", "Q3I", "Q2I"):
        cik_name.update(_frame_names(base, "Assets", f"CY{fy}{q}", "USD"))
    name_cik: dict[str, int] = {}
    for cik, nm in cik_name.items():
        name_cik.setdefault(_norm_name(nm), cik)
    for t, nm in _universe_names().items():
        if t in out:
            continue
        cik = name_cik.get(_norm_name(nm))
        if cik:
            out[t] = cik
    return out


def _cache_path():
    p = config.data_dir() / "edgar" / "fundamentals.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _cache_age_days() -> float | None:
    p = _cache_path()
    if not p.exists():
        return None
    meta = config.data_dir() / "edgar" / "_meta.json"
    if meta.exists():
        try:
            built = datetime.fromisoformat(json.loads(meta.read_text())["built"])
            return (datetime.now(timezone.utc) - built).total_seconds() / 86400.0
        except Exception:  # noqa: BLE001
            pass
    return 999.0


def fetch_company_tickers(max_age_days: int = 30, force: bool = False) -> bool:
    """Fetch and cache the SEC broad CIK→ticker map (company_tickers.json).

    Called once per month by the collector pipeline. The file is committed to
    the repo (data/edgar/company_tickers.json) because:
      • engine/name_resolver reads it keylessly at query time to reach ~10k-name
        coverage (vs 4,101 without it).
      • www.sec.gov enforces a declared User-Agent (SEC fair-access policy); our
        email-bearing UA in config["edgar"]["user_agent"] satisfies that.
      • special_situations.py has an independent copy (_ensure_company_tickers)
        using the same endpoint — this collector variant makes the file available
        regardless of whether special_situations is enabled.

    Returns True if the cache is fresh (was already up to date or successfully
    refreshed). Never raises.
    """
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if not force and cache.exists():
        try:
            age_d = (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime) / 86400.0
            if age_d < max_age_days:
                return True
        except Exception:  # noqa: BLE001
            pass
    data = _get_json(_cfg()["tickers_url"], _cfg()["retries"])
    if data:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
        log.info("edgar: cached company_tickers.json (%d filers)", len(data))
        return True
    log.warning("edgar: company_tickers.json fetch failed; cache %s",
                "retained" if cache.exists() else "absent")
    return False


def fetch_fundamentals(force: bool = False, max_age_days: int = 7) -> pd.DataFrame:
    """Fetch (or load cached) the wide ticker-indexed fundamentals table."""
    cache = _cache_path()
    age = _cache_age_days()
    if not force and age is not None and age < max_age_days:
        log.info("edgar fundamentals cache fresh (%.1fd) — skip fetch", age)
        return pd.read_parquet(cache)

    cfg = _cfg()
    universe = _universe_tickers()
    if not universe:
        raise RuntimeError("no breadth close caches — run breadth collectors first")

    # resolve the latest fiscal year that is actually populated
    fy = int(cfg["latest_fy"])
    for cand in (fy, fy - 1):
        if len(_annual("NetIncomeLoss", cand)) >= cfg["min_filers_ok"]:
            fy = cand
            break

    tcik = _ticker_cik_map(universe, fy)
    cik_t = {c: t for t, c in tcik.items()}        # first ticker wins on dup CIK
    log.info("edgar: %d universe tickers, %d mapped to CIK, FY%d", len(universe), len(tcik), fy)

    cols: dict[str, dict[int, float]] = {}
    for key, concept in BALANCE.items():
        cols[key] = _latest_balance(concept, fy)
    cols["assets_prior"] = _latest_balance("Assets", fy - 1)
    cols["shares"] = _shares(fy)
    for key, concept in FLOW.items():
        cols[key] = _annual(concept, fy)
    cols["ni_prior"] = _annual("NetIncomeLoss", fy - 1)
    rev: dict[int, float] = {}
    for c in REVENUE_CONCEPTS:
        for cik, v in _annual(c, fy).items():
            rev.setdefault(cik, v)
    cols["revenue"] = rev

    # assemble wide table keyed by ticker
    rows = []
    for cik, t in cik_t.items():
        rec = {"ticker": t, "cik": cik}
        for key, m in cols.items():
            rec[key] = m.get(cik)
        rows.append(rec)
    df = pd.DataFrame(rows).set_index("ticker")
    df = df.dropna(subset=["assets", "equity"], how="all")
    df.to_parquet(cache)
    (config.data_dir() / "edgar" / "_meta.json").write_text(
        json.dumps({"built": datetime.now(timezone.utc).isoformat(), "fy": fy,
                    "n_tickers": int(len(df)), "n_universe": len(universe)}))
    log.info("edgar fundamentals: %d tickers, FY%d, %d cols", len(df), fy, df.shape[1])
    return df


# --------------------------------------------------------------------------- #
# Point-in-time PANEL — the leak-free upgrade.
#
# fetch_fundamentals() (above) overwrites a single latest-FY snapshot, so a factor
# backtest run on it would use TODAY's restated numbers at every past date
# (look-ahead) and only TODAY's listed tickers (survivorship). The panel fixes the
# look-ahead fully: the EDGAR *frames* API serves any historical calendar period,
# so we fetch one annual cross-section per fiscal year back to `panel_start_fy`
# (XBRL was mandated ~2009) and stamp each row with `period_end` plus an
# `asof_date` = period_end + `reporting_lag_days` — a CONSERVATIVE proxy for when
# the 10-K was knowable (frames carry the period end but NOT the SEC `filed`
# timestamp; the true filed date would need per-company companyfacts calls — a
# later upgrade). `as_of_cross_section(date)` then returns exactly what was
# knowable on `date`. Survivorship is only partially addressed: historical frames
# DO include since-delisted filers, but the current company_tickers.json can't map
# their CIK to a ticker (and free prices don't cover them), so the panel is still
# current-universe tickers carrying their OWN historical fundamentals. The honest
# go-forward survivorship fix is to accumulate point-in-time index membership from
# now on (separate); this module removes the look-ahead, which is the larger bias.
# --------------------------------------------------------------------------- #
PANEL_NUMERIC = ["assets", "equity", "debt_lt", "shares", "ni", "gross_profit",
                 "cfo", "dividends", "repurchases", "revenue", "assets_prior", "ni_prior",
                 # W2 PR-H: op_income + interest_exp to fix quality_z≡profitability_z alias
                 # and restore interest_coverage (was 0% coverage in W1 kill-test).
                 # PIT discipline is identical to existing FLOW fields: values are stamped
                 # with asof_date = period_end + reporting_lag_days (120d conservative proxy).
                 "op_income", "interest_exp"]

# LT-1c: capex is NOT available from the EDGAR frames API (it is a sub-line of the
# cash-flow statement that the frames endpoint does not serve as a standalone concept).
# Instead it is joined from data/edgar/statements.parquet (statements-lane provenance)
# by (ticker, fy) inside fetch_panel after the frames build.  PIT gate: each joined
# value is accepted only if statements.period_end + reporting_lag_days <= panel
# asof_date; otherwise the value is NaN'd.  This prevents look-ahead for non-Dec-FYE
# filers where the panel's calendar-year period_end proxy diverges from the true
# fiscal end recorded in statements.parquet (empirically 49 of 7295 capex-bearing
# rows, median 365d early, max 1096d — see review notes for PR #1633).
# Coverage after gating is bounded by statements.parquet ticker×fy intersection
# (~87% of rows that have a statements entry; see LT1_DATA_REPAIR_REPORT.md).
PANEL_STATEMENTS_JOIN = ["capex"]  # fields joined from statements.parquet post-build


def _panel_path():
    p = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _join_statements_fields(
    panel: pd.DataFrame,
    fields: list[str],
    reporting_lag_days: int = 120,
) -> pd.DataFrame:
    """Join selected fields from data/edgar/statements.parquet into the panel by
    (ticker, fy).  Fields in `fields` that already exist in the panel are
    overwritten only where the panel value is NaN (statements-lane fills gaps).

    PIT discipline: for each joined value the function reads the statements row's
    own period_end and gates the value on
        statements.period_end + reporting_lag_days <= panel.asof_date
    Values that fail this gate are set to NaN — they were not yet knowable at the
    panel row's point-in-time cutoff.  Rows whose statements.period_end is missing
    are accepted without a PIT check (conservative: we cannot verify, but this
    affects <1% of rows empirically).

    This is stricter than the original approach of inheriting the panel row's
    asof_date, which silently treated the panel's calendar-year period_end proxy
    as the true fiscal year end — a look-ahead for non-Dec-FYE filers and any FY
    whose statements.period_end differs from the frames-API period_end.

    Returns the panel with `fields` added (or filled).  Rows with no matching
    statement entry get NaN for the joined fields.  Never raises — on any error
    the panel is returned unchanged with a warning logged.

    Provenance note: fields joined via this function carry statements-lane
    provenance (sourced from the SEC companyfacts collector edgar_facts.py rather
    than from the EDGAR frames API used by the rest of the panel).
    """
    stmt_path = config.data_dir() / "edgar" / "statements.parquet"
    if not stmt_path.exists():
        log.warning("statements.parquet not found — %s will be all-NaN", fields)
        for f in fields:
            if f not in panel.columns:
                panel = panel.copy()
                panel[f] = float("nan")
        return panel

    # Include period_end from statements so we can PIT-gate each joined value.
    read_cols = ["ticker", "fy", "period_end"] + [
        f for f in fields if f != "period_end"
    ]
    try:
        stmt = pd.read_parquet(stmt_path, columns=read_cols)
    except Exception as exc:  # noqa: BLE001
        log.warning("statements.parquet load failed (%s) — %s will be all-NaN", exc, fields)
        for f in fields:
            if f not in panel.columns:
                panel = panel.copy()
                panel[f] = float("nan")
        return panel

    stmt["period_end"] = pd.to_datetime(stmt["period_end"], errors="coerce")
    # statements-lane asof: the date from which the value is knowable
    stmt["_stmt_asof"] = stmt["period_end"] + pd.Timedelta(days=reporting_lag_days)

    # Deduplicate (ticker, fy) — keep last row if any duplicates exist
    stmt = stmt.drop_duplicates(subset=["ticker", "fy"], keep="last")

    panel = panel.copy()
    merged = panel.merge(stmt, on=["ticker", "fy"], how="left", suffixes=("", "_stmt"))

    # PIT gate: null out any joined field value where the statement's own
    # asof date is AFTER the panel row's asof_date (look-ahead prevention).
    # Rows where _stmt_asof is NaT (no period_end in statements) are kept as-is.
    if "_stmt_asof" in merged.columns and "asof_date" in merged.columns:
        stmt_asof = merged["_stmt_asof"]
        panel_asof = merged["asof_date"]
        lookahead_mask = stmt_asof.notna() & (stmt_asof > panel_asof)
        n_gated = int(lookahead_mask.sum())
        if n_gated:
            log.warning(
                "panel statements join: PIT gate nulled %d rows where "
                "stmt period_end + %dd > panel asof_date (non-Dec-FYE or FY mismatch)",
                n_gated, reporting_lag_days,
            )
            for f in fields:
                # Determine which column name the statements value landed in after merge.
                # If f was already in the panel the merge suffixed it as f_stmt;
                # otherwise it kept its original name.
                stmt_col = f"{f}_stmt" if f in panel.columns else f
                if stmt_col in merged.columns:
                    merged.loc[lookahead_mask, stmt_col] = float("nan")

    for f in fields:
        stmt_col = f"{f}_stmt" if f in panel.columns else f
        if stmt_col in merged.columns:
            if f in panel.columns:
                # Fill NaN values in existing column from statements
                merged[f] = merged[f].where(merged[f].notna(), merged[stmt_col])
                merged = merged.drop(columns=[stmt_col])
            else:
                merged = merged.rename(columns={stmt_col: f})

    # Drop the temporary join helper column
    if "_stmt_asof" in merged.columns:
        merged = merged.drop(columns=["_stmt_asof"])
    if "period_end_stmt" in merged.columns:
        merged = merged.drop(columns=["period_end_stmt"])

    log.info("panel statements join: %d rows, fields %s coverage: %s",
             len(merged),
             fields,
             {f: int(merged[f].notna().sum()) for f in fields if f in merged.columns})
    return merged


def _panel_meta_path():
    return config.data_dir() / "edgar" / "_panel_meta.json"


def _panel_age_days() -> float | None:
    mp = _panel_meta_path()
    if not _panel_path().exists() or not mp.exists():
        return None
    try:
        built = datetime.fromisoformat(json.loads(mp.read_text())["built"])
        return (datetime.now(timezone.utc) - built).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return 999.0


def _year_fundamentals(year: int) -> dict[int, dict]:
    """{cik: {concept: val, ..., 'period_end': 'YYYY-MM-DD'}} for one fiscal year,
    assembled from the frames API (balance scan + annual flows)."""
    out: dict[int, dict] = {}
    bal = {k: _latest_balance_dated(v, year) for k, v in BALANCE.items()}
    for cik, (val, end) in bal["assets"].items():
        out[cik] = {"assets": val, "period_end": end}
    for key in ("equity", "debt_lt"):
        for cik, (val, _e) in bal[key].items():
            out.setdefault(cik, {})[key] = val
    for cik, val in _shares(year).items():
        out.setdefault(cik, {})["shares"] = val
    for key, concept in FLOW.items():
        for cik, val in _annual(concept, year).items():
            out.setdefault(cik, {})[key] = val
    rev: dict[int, float] = {}
    for c in REVENUE_CONCEPTS:
        for cik, val in _annual(c, year).items():
            rev.setdefault(cik, val)
    for cik, val in rev.items():
        out.setdefault(cik, {})["revenue"] = val
    return out


def fetch_panel(force: bool = False, max_age_days: int = 7,
                years: list[int] | None = None) -> pd.DataFrame:
    """Build (or load cached) the point-in-time fundamentals panel — one row per
    (ticker, fiscal_year) with period_end + asof_date, back to `panel_start_fy`.
    Also refreshes the latest-FY `fundamentals.parquet` slice (back-compat). Pass
    `years` to restrict the fetch (used by tests / partial backfills)."""
    panel_p = _panel_path()
    age = _panel_age_days()
    if not force and age is not None and age < max_age_days:
        log.info("edgar panel cache fresh (%.1fd) — skip fetch", age)
        return pd.read_parquet(panel_p)

    cfg = _cfg()
    universe = _universe_tickers()
    if not universe:
        raise RuntimeError("no breadth close caches — run breadth collectors first")

    latest_fy = int(cfg["latest_fy"])
    for cand in (latest_fy, latest_fy - 1):
        if len(_annual("NetIncomeLoss", cand)) >= cfg["min_filers_ok"]:
            latest_fy = cand
            break
    start_fy = int(cfg.get("panel_start_fy", 2009))
    lag = int(cfg.get("reporting_lag_days", 120))
    yrs = years if years is not None else list(range(start_fy, latest_fy + 1))

    tcik = _ticker_cik_map(universe, latest_fy)
    cik_t = {c: t for t, c in tcik.items()}     # first ticker wins on dup CIK
    log.info("edgar panel: %d universe, %d mapped, FY%d..%d (lag %dd)",
             len(universe), len(tcik), min(yrs), max(yrs), lag)

    by_year = {y: _year_fundamentals(y) for y in yrs}
    rows = []
    for y in yrs:
        prior = by_year.get(y - 1, {})
        for cik, rec in by_year[y].items():
            t = cik_t.get(cik)
            if t is None:
                continue                        # delisted / unmapped — can't join to prices
            row = {"ticker": t, "cik": cik, "fy": y}
            for k in PANEL_NUMERIC:
                if k not in ("assets_prior", "ni_prior"):
                    row[k] = rec.get(k)
            row["assets_prior"] = prior.get(cik, {}).get("assets")
            row["ni_prior"] = prior.get(cik, {}).get("ni")
            row["period_end"] = rec.get("period_end")
            rows.append(row)

    panel = pd.DataFrame(rows)
    panel = panel.dropna(subset=["assets", "equity"], how="all")
    panel["period_end"] = pd.to_datetime(panel["period_end"], errors="coerce")
    panel["asof_date"] = panel["period_end"] + pd.Timedelta(days=lag)
    panel = panel.dropna(subset=["period_end"]).sort_values(["ticker", "fy"]).reset_index(drop=True)

    # LT-1c: join capex (and other PANEL_STATEMENTS_JOIN fields) from statements.parquet.
    # These fields are not available from the EDGAR frames API; they carry statements-lane
    # provenance.  PIT gate: values are nulled where statements.period_end + lag > panel
    # asof_date to prevent look-ahead from non-Dec-FYE filers and FY mismatch cases.
    if PANEL_STATEMENTS_JOIN:
        panel = _join_statements_fields(panel, PANEL_STATEMENTS_JOIN, reporting_lag_days=lag)

    panel.to_parquet(panel_p)
    all_numeric = PANEL_NUMERIC + [f for f in PANEL_STATEMENTS_JOIN if f in panel.columns]
    _panel_meta_path().write_text(json.dumps({
        "built": datetime.now(timezone.utc).isoformat(),
        "fy_min": int(panel["fy"].min()), "fy_max": int(panel["fy"].max()),
        "reporting_lag_days": lag, "n_rows": int(len(panel)),
        "n_tickers": int(panel["ticker"].nunique()),
        "statements_join_fields": PANEL_STATEMENTS_JOIN,
        "capex_coverage": int(panel["capex"].notna().sum()) if "capex" in panel.columns else 0,
    }))
    log.info("edgar panel: %d rows, %d tickers, FY%d..%d",
             len(panel), panel["ticker"].nunique(), panel["fy"].min(), panel["fy"].max())

    # refresh the live latest-FY slice (back-compat with equity_factors live path)
    latest = panel[panel["fy"] == panel["fy"].max()].set_index("ticker")
    keep = ["cik"] + PANEL_NUMERIC + [f for f in PANEL_STATEMENTS_JOIN if f in panel.columns]
    latest[[c for c in keep if c in latest.columns]].to_parquet(_cache_path())
    (config.data_dir() / "edgar" / "_meta.json").write_text(json.dumps({
        "built": datetime.now(timezone.utc).isoformat(), "fy": int(panel["fy"].max()),
        "n_tickers": int(len(latest)), "n_universe": len(universe),
        "panel": True}))
    return panel


def as_of_cross_section(asof, panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Leak-free ticker-indexed fundamentals knowable at `asof`: per ticker, the
    most recent fiscal year whose asof_date (period_end + reporting lag) is on or
    before `asof`. This is the cross-section a point-in-time factor backtest must
    use at each rebalance date so it never peeks at a not-yet-filed report."""
    if panel is None:
        p = _panel_path()
        if not p.exists():
            raise RuntimeError("no fundamentals_panel.parquet — run collectors.edgar fetch_panel")
        panel = pd.read_parquet(p)
    asof = pd.Timestamp(asof)
    sub = panel[panel["asof_date"] <= asof]
    if sub.empty:
        return sub.set_index("ticker") if "ticker" in sub.columns else sub
    idx = sub.groupby("ticker")["fy"].idxmax()
    return sub.loc[idx].set_index("ticker")

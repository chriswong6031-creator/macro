"""engine.theme_warn — Per-basket WARN Act layoff-notice velocity leg.

DISPLAY / CONFLUENCE CONTEXT ONLY.
Authority: may_rank=false, may_gate=false, may_size=false, may_escalate=false,
           is_context_only=true.

Framing (R-TIL-2, TI-R5): loser-cohort / disruption AVOID-shaped evidence only.
No rotation calls.  No short calls.  warn_z is descriptive — "this basket's
members are seeing elevated layoff-notice activity vs their own history."

CRITICAL FENCE (spec PR-B): warn_z is a SEPARATE display leg.
Do NOT fold into fused_obs_z — the radar IC harness (113 theses accruing)
grades against the current fused_obs_z composition; changing its inputs
mid-accrual corrupts PIT comparability.

Output key shape (per basket_id in the returned dict):
    {
        "warn_z": float | None,          # cross-sectional robust-z of recent velocity
        "warn_workers_90d": int | None,  # raw workers laid off in trailing 90 days
        "warn_count_90d": int | None,    # raw notice count in trailing 90 days
        "warn_workers_prior": int | None,# same window, 1 year ago (YoY base)
        "warn_yoy_ratio": float | None,  # recent / prior (winsorised), None if thin
        "matched_employers": list[str],  # provenance: employer_raw strings that matched
        "matched_tickers": list[str],    # provenance: matched tickers
        "n_matched": int,                # number of notices matched to basket members
        "coverage_note": str,            # EN coverage caveat
        "coverage_note_zh": str,         # ZH coverage caveat
    }

Data availability (known lethal false-null trap):
  The WARN store (data/warn/notices.parquet) is runner-local and NOT committed
  to git.  The worktree may not have it.  We check:
    1. WARN_STORE env var override (absolute path or relative to ROOT)
    2. The MAIN checkout path: /Users/chriswong/Documents/Cluade/Macro Dashboard/data/warn/
    3. Worktree-local data/warn/notices.parquet

  When the store is absent: returns {} gracefully (honest null; exit 0 always).

Ticker map:
  Uses scripts/w2044_warn_ticker_map.csv (the same map as the w2044 backtest).
  Loaded via lib.warn_fuzzy.  Map absent -> all baskets return null (coverage_note
  explains; still exit 0).

Usage (nightly collect lane, off the render critical path):
    from engine.theme_warn import compute_warn_activity
    result = compute_warn_activity(baskets_payload)
    # result: {basket_id: {...}} — parallel key alongside theme_activity output

    # With store path override:
    result = compute_warn_activity(baskets_payload, store_path=Path("/path/to/notices.parquet"))
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from lib.warn_fuzzy import load_ticker_map, match_ticker

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (display-tier only; display/context, no scoring)
# ---------------------------------------------------------------------------
AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
    "framing": "loser_cohort_avoid_shaped_evidence",
    "rotation_calls": False,
    "short_calls": False,
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WARN_WINDOW_DAYS: int = 90       # "recent" window for worker-count sum
YOY_DAYS: int = 365              # offset to prior window for year-on-year comparison
ACCEL_CLAMP: tuple[float, float] = (0.1, 20.0)   # winsorise raw yoy ratio
Z_CLAMP: float = 3.5             # winsorise cross-sectional robust-z

# Minimum covered notices in a basket to compute a meaningful metric
MIN_NOTICES: int = 1

# Default WARN store path (relative to repo root; also checked via env var)
_DEFAULT_STORE_REL = Path("data/warn/notices.parquet")

# Candidates for the WARN store (tried in order)
_STORE_CANDIDATES: list[Path] = [
    # Main checkout (runner-local; not in git)
    Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/warn/notices.parquet"),
]

# Ticker map path (relative to repo root)
_TICKER_MAP_REL = Path("scripts/w2044_warn_ticker_map.csv")

# EN/ZH coverage caveats
_COV_ABSENT_EN = (
    "WARN store absent — no employer layoff data for this basket. "
    "Store is runner-local (data/warn/notices.parquet). "
    "Missing states include TX, PA, FL, MI, OH (top-5 by volume)."
)
_COV_ABSENT_ZH = "WARN数据不可用（数据仓库不在本工作区）"

_COV_THIN_EN = "Basket member layoff data thin (<{n} notices in trailing 90d)"
_COV_THIN_ZH = "篮子成员裁员公告数据不足"

_COV_OK_EN = "{n} layoff notices matched; {states} states covered in trailing 90d"
_COV_OK_ZH = "{n}条裁员公告匹配（近90天）"


def _find_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _find_store(root: Path, store_path: Optional[Path] = None) -> Optional[Path]:
    """Find the WARN notices.parquet, checking env var override first.

    Order:
      1. Explicit `store_path` argument.
      2. WARN_STORE env var.
      3. Worktree-local data/warn/notices.parquet.
      4. Known main-checkout path(s).
    """
    if store_path is not None:
        p = store_path if store_path.is_absolute() else root / store_path
        return p if p.exists() else None

    env_val = os.environ.get("WARN_STORE", "").strip()
    if env_val:
        p = Path(env_val) if Path(env_val).is_absolute() else root / env_val
        if p.exists():
            return p
        log.warning("WARN_STORE env points to non-existent path: %s", p)

    local = root / _DEFAULT_STORE_REL
    if local.exists():
        return local

    for candidate in _STORE_CANDIDATES:
        if candidate.exists():
            return candidate

    return None


def _find_ticker_map(root: Path) -> Optional[Path]:
    p = root / _TICKER_MAP_REL
    return p if p.exists() else None


def _load_notices(store: Path) -> Optional[pd.DataFrame]:
    """Load WARN notices parquet; return None on any error."""
    try:
        df = pd.read_parquet(store)
        if df.empty or "employer_raw" not in df.columns:
            log.warning("WARN store empty or missing employer_raw column: %s", store)
            return None
        # Ensure notice_date is datetime
        if "notice_date" in df.columns:
            df["notice_date"] = pd.to_datetime(df["notice_date"], errors="coerce")
        # Drop rows with no employer or no date
        df = df[df["employer_raw"].notna() & (df["employer_raw"] != "")]
        df = df[df["notice_date"].notna()]
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("WARN store load failed: %s", exc)
        return None


def _robust_z(values: list[float]) -> list[float]:
    """Median/MAD robust-z, winsorised to +/-Z_CLAMP. Returns 0.0 for all-null."""
    arr = np.asarray([v if v is not None and np.isfinite(v) else np.nan for v in values], float)
    good = arr[~np.isnan(arr)]
    if len(good) < 2:
        return [0.0] * len(arr)
    med = float(np.median(good))
    mad = float(np.median(np.abs(good - med))) * 1.4826
    scale = mad if mad > 1e-9 else float(np.std(good))
    if not scale or scale < 1e-9:
        return [0.0] * len(arr)
    return [
        0.0 if np.isnan(v) else float(np.clip((v - med) / scale, -Z_CLAMP, Z_CLAMP))
        for v in arr
    ]


def _resolve_notices(
    notices_df: pd.DataFrame,
    ticker_rows: list[dict],
) -> list[dict]:
    """Pre-resolve every notice to a ticker in a single vectorized pass.

    Returns a flat list of dicts, one per notice row, with the resolved ticker
    (or None) already attached.  This amortises the O(notices × map_rows) cost
    across all baskets instead of repeating it per basket.

    Perf note: iterrows is used here because employer strings need per-row
    string ops (strip, lower, suffix-strip, regex).  The key win is that this
    loop runs ONCE regardless of how many baskets are queried.
    """
    resolved: list[dict] = []
    for _, row in notices_df.iterrows():
        nd = pd.Timestamp(row["notice_date"])
        employer = str(row.get("employer_raw", "") or "").strip()
        if not employer:
            continue
        nd_str = nd.strftime("%Y-%m-%d")
        ticker = match_ticker(employer, ticker_rows, nd_str)
        workers = row.get("workers")
        try:
            w = int(float(workers)) if workers is not None and str(workers).strip() else 0
        except (ValueError, TypeError):
            w = 0
        resolved.append({
            "employer": employer,
            "ticker": ticker,  # may be None
            "workers": w,
            "state": str(row.get("state", "") or ""),
            "notice_date": nd,
            "notice_date_str": nd_str,
        })
    return resolved


def _basket_warn_metric(
    basket_id: str,
    members: list[str],
    notices_df: pd.DataFrame,
    ticker_rows: list[dict],
    *,
    as_of: Optional[datetime] = None,
    _resolved: Optional[list[dict]] = None,
) -> Optional[dict]:
    """Compute WARN velocity metric for one basket.

    When *_resolved* is provided (pre-resolved notice list from
    ``_resolve_notices``), the per-notice ticker lookup is skipped and the
    basket simply filters by membership.  This is the fast path used by
    ``compute_warn_activity`` — callers that use this function directly (e.g.
    tests) can omit *_resolved* and the old O(notices × map_rows) path runs.

    Returns a dict with raw counts + yoy_ratio + metric (log(yoy_ratio)),
    or None when insufficient data.
    """
    if not members:
        return None

    t0 = as_of or datetime.now(timezone.utc)
    if isinstance(t0, str):
        t0 = pd.Timestamp(t0).to_pydatetime()
    t0 = pd.Timestamp(t0)
    # Normalise to tz-naive UTC for comparison with parquet dates (which are tz-naive)
    if t0.tzinfo is not None:
        t0 = t0.tz_convert(None)

    recent_start = t0 - timedelta(days=WARN_WINDOW_DAYS)
    prior_end = t0 - timedelta(days=YOY_DAYS)
    prior_start = prior_end - timedelta(days=WARN_WINDOW_DAYS)

    members_set = set(members)

    # Resolve each notice to a ticker + check membership
    matched_recent: list[dict] = []
    matched_prior: list[dict] = []
    matched_employers: list[str] = []
    matched_tickers: list[str] = []
    seen_employer_ticker: set[tuple] = set()

    # Use pre-resolved list when available (fast path); fall back to per-row match
    if _resolved is not None:
        rows_iter = _resolved
        fast_path = True
    else:
        rows_iter = None  # type: ignore[assignment]
        fast_path = False

    if fast_path:
        for rec in rows_iter:  # type: ignore[union-attr]
            ticker = rec["ticker"]
            if ticker is None or ticker not in members_set:
                continue
            nd = rec["notice_date"]
            employer = rec["employer"]
            w = rec["workers"]

            key = (employer.lower(), ticker)
            if key not in seen_employer_ticker:
                matched_employers.append(employer)
                matched_tickers.append(ticker)
                seen_employer_ticker.add(key)

            record = {"employer": employer, "ticker": ticker, "workers": w,
                      "state": rec["state"], "notice_date": nd}
            if recent_start <= nd <= t0:
                matched_recent.append(record)
            elif prior_start <= nd <= prior_end:
                matched_prior.append(record)
    else:
        # Slow path — used by direct callers (e.g. tests) that don't pre-resolve
        for _, row in notices_df.iterrows():
            nd = pd.Timestamp(row["notice_date"])
            employer = str(row.get("employer_raw", "") or "").strip()
            if not employer:
                continue
            nd_str = nd.strftime("%Y-%m-%d")
            ticker = match_ticker(employer, ticker_rows, nd_str)
            if ticker is None or ticker not in members_set:
                continue

            key = (employer.lower(), ticker)
            if key not in seen_employer_ticker:
                matched_employers.append(employer)
                matched_tickers.append(ticker)
                seen_employer_ticker.add(key)

            workers = row.get("workers")
            try:
                w = int(float(workers)) if workers is not None and str(workers).strip() else 0
            except (ValueError, TypeError):
                w = 0

            record = {"employer": employer, "ticker": ticker, "workers": w,
                      "state": row.get("state", ""), "notice_date": nd}
            if recent_start <= nd <= t0:
                matched_recent.append(record)
            elif prior_start <= nd <= prior_end:
                matched_prior.append(record)

    if not matched_recent and not matched_prior:
        return None

    workers_recent = sum(r["workers"] for r in matched_recent)
    workers_prior = sum(r["workers"] for r in matched_prior)
    count_recent = len(matched_recent)

    # YoY ratio (winsorised); None when prior window empty
    if workers_prior > 0:
        ratio = float(np.clip(workers_recent / workers_prior, *ACCEL_CLAMP))
        metric = float(np.log(ratio))
    elif workers_recent > 0:
        # New activity vs a quiet prior year — use hard-clamp ceiling
        ratio = float(ACCEL_CLAMP[1])
        metric = float(np.log(ratio))
    else:
        ratio = None
        metric = None

    states = sorted({r["state"] for r in matched_recent if r["state"]})

    return {
        "metric": metric,          # log(yoy_ratio) for cross-sectional z
        "warn_yoy_ratio": None if ratio is None else round(ratio, 3),
        "warn_workers_90d": workers_recent,
        "warn_count_90d": count_recent,
        "warn_workers_prior": workers_prior,
        "matched_employers": sorted(set(matched_employers)),
        "matched_tickers": sorted(set(matched_tickers)),
        "n_matched": count_recent,
        "states": states,
    }


def compute_warn_activity(
    baskets_payload: dict,
    *,
    store_path: Optional[Path] = None,
    ticker_map_path: Optional[Path] = None,
    as_of: Optional[datetime] = None,
    root: Optional[Path] = None,
) -> dict:
    """Compute per-basket WARN velocity (warn_z) as a parallel display leg.

    CRITICAL FENCE: warn_z is SEPARATE from fused_obs_z and must NOT be
    folded into it.  This function returns a standalone dict keyed by basket_id.

    Parameters
    ----------
    baskets_payload:
        Same payload as theme_activity.compute_real_activity — must have
        ``baskets`` list with ``id`` + ``members`` list.
    store_path:
        Override the WARN store path (useful for tests).
    ticker_map_path:
        Override the ticker map path (useful for tests).
    as_of:
        Reference datetime for the recent / prior windows.
    root:
        Repo root override (for tests).

    Returns
    -------
    dict
        ``{basket_id: {warn_z, warn_workers_90d, ...}}`` for every basket;
        empty dict when store is absent (honest null, no crash).
    """
    if root is None:
        root = _find_root()

    baskets = (baskets_payload or {}).get("baskets") or []
    if not baskets:
        return {}

    # --- locate store ---
    store = _find_store(root, store_path)
    if store is None:
        log.info("theme_warn: WARN store absent — returning honest null for all baskets")
        absent: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                absent[bid] = {
                    "warn_z": None,
                    "warn_workers_90d": None,
                    "warn_count_90d": None,
                    "warn_workers_prior": None,
                    "warn_yoy_ratio": None,
                    "matched_employers": [],
                    "matched_tickers": [],
                    "n_matched": 0,
                    "coverage_note": _COV_ABSENT_EN,
                    "coverage_note_zh": _COV_ABSENT_ZH,
                    "authority": AUTHORITY,
                }
        return absent

    # --- load notices ---
    notices_df = _load_notices(store)
    if notices_df is None or notices_df.empty:
        log.info("theme_warn: WARN store present but empty — returning null")
        empty: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                empty[bid] = {
                    "warn_z": None, "warn_workers_90d": None, "warn_count_90d": None,
                    "warn_workers_prior": None, "warn_yoy_ratio": None,
                    "matched_employers": [], "matched_tickers": [], "n_matched": 0,
                    "coverage_note": _COV_ABSENT_EN, "coverage_note_zh": _COV_ABSENT_ZH,
                    "authority": AUTHORITY,
                }
        return empty

    # --- resolve as_of: prefer explicit arg, then payload field, then now() ---
    if as_of is None:
        payload_asof = (baskets_payload or {}).get("as_of")
        if payload_asof:
            try:
                as_of = pd.Timestamp(payload_asof).to_pydatetime()
            except Exception:  # noqa: BLE001
                pass
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    # --- load ticker map ---
    if ticker_map_path is None:
        ticker_map_path = _find_ticker_map(root)
    ticker_rows = load_ticker_map(ticker_map_path) if ticker_map_path else []
    if not ticker_rows:
        log.info("theme_warn: ticker map absent or empty — all matches null")

    # --- pre-resolve ALL notices to tickers in a single pass ---
    # This is the performance-critical step: O(notices × map_rows) runs ONCE
    # here, not once per basket.  Per-basket work is then O(resolved_notices).
    resolved = _resolve_notices(notices_df, ticker_rows)
    log.debug("theme_warn: pre-resolved %d notices from %d rows", len(resolved), len(notices_df))

    # --- per-basket raw metrics (fast path: filter pre-resolved list) ---
    raw: dict[str, dict] = {}
    for b in baskets:
        bid = b.get("id")
        if not bid:
            continue
        members = [m.get("symbol") for m in b.get("members", []) if m.get("symbol")]
        if not members:
            continue
        m = _basket_warn_metric(bid, members, notices_df, ticker_rows,
                                as_of=as_of, _resolved=resolved)
        if m is not None:
            raw[bid] = m

    if not raw:
        # No basket had any matched notices
        result: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                result[bid] = {
                    "warn_z": None, "warn_workers_90d": None, "warn_count_90d": None,
                    "warn_workers_prior": None, "warn_yoy_ratio": None,
                    "matched_employers": [], "matched_tickers": [], "n_matched": 0,
                    "coverage_note": _COV_ABSENT_EN, "coverage_note_zh": _COV_ABSENT_ZH,
                    "authority": AUTHORITY,
                }
        return result

    # --- cross-sectional robust-z over the baskets that had any match ---
    bids = list(raw)
    metrics = [raw[bid].get("metric") for bid in bids]
    zs = _robust_z([m if m is not None else float("nan") for m in metrics])
    z_by_bid = dict(zip(bids, zs))

    # --- assemble output ---
    out: dict = {}
    for b in baskets:
        bid = b.get("id")
        if not bid:
            continue
        if bid in raw:
            r = raw[bid]
            n = r["n_matched"]
            states = r.get("states", [])
            cov_en = _COV_OK_EN.format(
                n=n, states=",".join(states) if states else "n/a"
            )
            cov_zh = _COV_OK_ZH.format(n=n)
            out[bid] = {
                "warn_z": round(z_by_bid[bid], 3),
                "warn_workers_90d": r["warn_workers_90d"],
                "warn_count_90d": r["warn_count_90d"],
                "warn_workers_prior": r["warn_workers_prior"],
                "warn_yoy_ratio": r.get("warn_yoy_ratio"),
                "matched_employers": r["matched_employers"],
                "matched_tickers": r["matched_tickers"],
                "n_matched": n,
                "coverage_note": cov_en,
                "coverage_note_zh": cov_zh,
                "authority": AUTHORITY,
            }
        else:
            # Not matched — honest null
            out[bid] = {
                "warn_z": None,
                "warn_workers_90d": None,
                "warn_count_90d": None,
                "warn_workers_prior": None,
                "warn_yoy_ratio": None,
                "matched_employers": [],
                "matched_tickers": [],
                "n_matched": 0,
                "coverage_note": _COV_THIN_EN.format(n=MIN_NOTICES),
                "coverage_note_zh": _COV_THIN_ZH,
                "authority": AUTHORITY,
            }

    return out

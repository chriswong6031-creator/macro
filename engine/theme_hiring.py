"""engine/theme_hiring — Per-basket DOL hiring-intent velocity leg (TIL W7).

DISPLAY / CONFLUENCE CONTEXT ONLY.
Authority: may_rank=false, may_gate=false, may_size=false, may_escalate=false,
           is_context_only=true.

Framing (R-TIL-9, spec PR-W7):
  DOL PERM/LCA certified caseload → per-basket hiring-intent velocity.
  Fills the SINGLE cited gap in the demand desk: no free per-company
  leading hiring source with job-title granularity.  3-6mo leading; keyed
  by legal employer name + worksite state; on no equity screen.

CRITICAL FENCE: hiring-velocity metrics are a SEPARATE display leg.
Do NOT fold into fused_obs_z — the radar IC harness PIT comparability
must be preserved (same fence as WARN precedent in engine/theme_warn.py).

Employer → ticker: via lib.warn_fuzzy (shared matcher, NO second matcher).
The shared ticker map (scripts/w2044_warn_ticker_map.csv) is reused;
additional aliases for new employer strings should be added there, not here.

AI/ML title lexicon (AI_TITLE_PATTERNS — versioned constant v1):
  ~20 patterns matching roles that signal AI/ML/data-infra capability staffing.
  Curated from public job postings and common industry role titles.
  Pattern matching is case-insensitive word-boundary (same as warn_fuzzy).

Velocity computation:
  cert_velocity_z : robust cross-sectional z of trailing-2q vs prior-4q
                    certified-case count change (per basket, employer-matched)
  ai_title_share  : fraction of matched job titles matching AI_TITLE_PATTERNS
  median_wage_yoy : median annualized wage % change year-over-year

Output:
  data/dol_certs/hiring_velocity.json    (runner-local; gitignored)
  site/basketdata/hiring_intent.json     (site projection; git-tracked)

Data availability (lethal false-null trap — mirrors WARN pattern):
  The DOL certs store (data/dol_certs/certs.parquet) is runner-local and
  NOT committed to git.  Multi-path fallback:
    1. DOL_CERTS_STORE env var override
    2. Worktree-local data/dol_certs/certs.parquet
    3. Main checkout /Users/chriswong/Documents/Cluade/Macro Dashboard/data/dol_certs/

  When store is absent: returns honest null (coverage_note explains), exit 0.

Usage (collect-lane step, off render critical path):
    from engine.theme_hiring import compute_hiring_velocity
    result = compute_hiring_velocity(baskets_payload)
    # result: {basket_id: {...}} — parallel key alongside theme_activity output
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from lib.warn_fuzzy import load_ticker_map, match_ticker

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (display-tier; display/context only, no scoring)
# ---------------------------------------------------------------------------
AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
    "framing": "hiring_intent_leading_evidence",
    "rotation_calls": False,
    "short_calls": False,
    "fused_obs_z_fence": "SEPARATE_DISPLAY_LEG — never fold into fused_obs_z",
}

# ---------------------------------------------------------------------------
# AI/ML/Data-Infra title lexicon — version 1 (versioned constant)
# 20 curated patterns for roles that reveal AI/ML capability staffing intent.
# Word-boundary matched (case-insensitive), same as warn_fuzzy.
# ---------------------------------------------------------------------------
AI_TITLE_PATTERNS_V1: list[str] = [
    "machine learning",
    "deep learning",
    "artificial intelligence",
    r"\bai engineer",
    r"\bai researcher",
    "large language model",
    r"\bllm\b",
    "natural language processing",
    r"\bnlp engineer",
    "data scientist",
    "mlops",
    "ml platform",
    "ml infrastructure",
    "computer vision engineer",
    "foundation model",
    "generative ai",
    "reinforcement learning",
    "data infrastructure",
    "data platform engineer",
    "applied scientist",
]
_AI_TITLE_RES = [
    re.compile(p, re.IGNORECASE) for p in AI_TITLE_PATTERNS_V1
]

# ---------------------------------------------------------------------------
# Velocity windows
# ---------------------------------------------------------------------------
# "Trailing 2 quarters" vs "prior 4 quarters" (spec)
RECENT_QUARTERS: int = 2
PRIOR_QUARTERS: int = 4
# Approximate: 91 days per quarter
QUARTER_DAYS: int = 91

# Cross-sectional robust-z clamp
Z_CLAMP: float = 3.5

# Minimum employer matches to compute a basket metric
MIN_MATCHES: int = 1

# ---------------------------------------------------------------------------
# Store paths
# ---------------------------------------------------------------------------
_DEFAULT_STORE_REL = Path("data/dol_certs/certs.parquet")
_TICKER_MAP_REL = Path("scripts/w2044_warn_ticker_map.csv")

_STORE_CANDIDATES = [
    Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/dol_certs/certs.parquet"),
]

# EN/ZH coverage caveats
_COV_ABSENT_EN = (
    "DOL certs store absent — hiring-intent data unavailable for this basket. "
    "Store is runner-local (data/dol_certs/certs.parquet; DOL_CERTS_STORE override). "
    "Run scripts/collect_dol_certs.py to ingest the first quarterly file."
)
_COV_ABSENT_ZH = "DOL雇佣意向数据不可用（数据仓库不在本工作区）"

_COV_THIN_EN = "Basket hiring-intent data thin (<{n} matched employers in recent quarters)"
_COV_THIN_ZH = "篮子雇佣意向数据不足"

_COV_OK_EN = "{n_emp} employers matched; {n_certs} certs in recent 2 quarters; coverage={rate:.0%}"
_COV_OK_ZH = "{n_certs}份LCA/PERM认证匹配（近两个季度）"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _find_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _find_store(root: Path, store_path: Optional[Path] = None) -> Optional[Path]:
    """Resolve DOL certs store path."""
    if store_path is not None:
        p = store_path if store_path.is_absolute() else root / store_path
        return p if p.exists() else None

    env_val = os.environ.get("DOL_CERTS_STORE", "").strip()
    if env_val:
        p = Path(env_val) if Path(env_val).is_absolute() else root / env_val
        if p.exists():
            return p
        log.warning("DOL_CERTS_STORE env points to non-existent path: %s", p)

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


def _load_certs(store: Path) -> Optional[pd.DataFrame]:
    """Load DOL certs parquet; return None on error."""
    try:
        df = pd.read_parquet(store)
        if df.empty or "employer_name" not in df.columns:
            log.warning("DOL certs store empty or missing employer_name: %s", store)
            return None
        if "decision_date" in df.columns:
            df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce")
        df = df[df["employer_name"].notna() & (df["employer_name"] != "")]
        df = df[df["decision_date"].notna()]
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("DOL certs store load failed: %s", exc)
        return None


def _matches_ai_title(job_title: str) -> bool:
    """Return True if job_title matches any AI/ML/data-infra pattern."""
    t = str(job_title).lower()
    return any(pat.search(t) for pat in _AI_TITLE_RES)


def _robust_z(values: list[float]) -> list[float]:
    """Median/MAD robust-z, winsorised to +/-Z_CLAMP."""
    arr = np.asarray(
        [v if v is not None and np.isfinite(v) else np.nan for v in values],
        dtype=float,
    )
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


def _pre_resolve_certs(
    certs_df: pd.DataFrame,
    ticker_rows: list[dict],
) -> list[dict]:
    """
    Resolve every cert row to a ticker in a single pass.
    O(certs × map_rows) runs ONCE here, not once per basket.
    """
    resolved: list[dict] = []
    for _, row in certs_df.iterrows():
        employer = str(row.get("employer_name", "") or "").strip()
        if not employer:
            continue
        nd = pd.Timestamp(row["decision_date"])
        nd_str = nd.strftime("%Y-%m-%d")
        ticker = match_ticker(employer, ticker_rows, nd_str)

        job_title = str(row.get("job_title", "") or "")
        is_ai = _matches_ai_title(job_title)

        try:
            wage = float(row.get("wage_annualized") or 0) or None
        except (ValueError, TypeError):
            wage = None

        resolved.append({
            "employer": employer,
            "ticker": ticker,
            "decision_date": nd,
            "job_title": job_title,
            "is_ai_title": is_ai,
            "wage": wage,
            "program": str(row.get("program", "") or ""),
        })
    return resolved


def _quarter_bin(dt: pd.Timestamp) -> str:
    """Return YYYY-QN string for a datetime."""
    m = dt.month
    q = (m - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _basket_hiring_metric(
    members_set: set[str],
    resolved: list[dict],
    as_of: pd.Timestamp,
) -> Optional[dict]:
    """Compute hiring velocity for one basket."""
    # Time windows
    # Recent = trailing RECENT_QUARTERS quarters
    recent_start = as_of - pd.Timedelta(days=RECENT_QUARTERS * QUARTER_DAYS)
    # Prior = the PRIOR_QUARTERS quarters before that
    prior_end = recent_start
    prior_start = prior_end - pd.Timedelta(days=PRIOR_QUARTERS * QUARTER_DAYS)

    recent_rows: list[dict] = []
    prior_rows: list[dict] = []
    all_matched: list[dict] = []

    for rec in resolved:
        ticker = rec["ticker"]
        if ticker is None or ticker not in members_set:
            continue
        nd = rec["decision_date"]
        all_matched.append(rec)
        if recent_start <= nd <= as_of:
            recent_rows.append(rec)
        elif prior_start <= nd < prior_end:
            prior_rows.append(rec)

    if not recent_rows and not prior_rows:
        return None

    # cert_velocity: count change (recent vs prior, normalized to quarters)
    count_recent = len(recent_rows)
    count_prior = len(prior_rows)

    # Velocity metric: log ratio (count_recent/recent_q) / (count_prior/prior_q)
    # Use counts per-quarter to normalize window lengths
    rate_recent = count_recent / RECENT_QUARTERS
    rate_prior = count_prior / PRIOR_QUARTERS if count_prior > 0 else None

    if rate_prior and rate_prior > 0:
        velocity_metric = float(np.log(max(rate_recent, 0.1) / rate_prior))
    elif count_recent > 0:
        velocity_metric = float(np.log(max(rate_recent, 0.1) + 1))
    else:
        velocity_metric = 0.0

    # AI title share in recent window
    if recent_rows:
        ai_count = sum(1 for r in recent_rows if r["is_ai_title"])
        ai_title_share = round(ai_count / len(recent_rows), 4)
    else:
        ai_title_share = None

    # Median wage YoY (recent vs prior)
    wages_recent = [r["wage"] for r in recent_rows if r["wage"] and r["wage"] > 0]
    wages_prior = [r["wage"] for r in prior_rows if r["wage"] and r["wage"] > 0]
    if wages_recent and wages_prior:
        med_recent = float(np.median(wages_recent))
        med_prior = float(np.median(wages_prior))
        median_wage_yoy = round((med_recent - med_prior) / med_prior, 4) if med_prior > 0 else None
    else:
        median_wage_yoy = None

    # Matched employers and tickers
    matched_employers = sorted(set(r["employer"] for r in all_matched))
    matched_tickers = sorted(set(r["ticker"] for r in all_matched if r["ticker"]))

    return {
        "velocity_metric": velocity_metric,
        "cert_count_recent": count_recent,
        "cert_count_prior": count_prior,
        "ai_title_share": ai_title_share,
        "median_wage_yoy": median_wage_yoy,
        "matched_employers": matched_employers,
        "matched_tickers": matched_tickers,
        "n_matched_employers": len(matched_employers),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_hiring_velocity(
    baskets_payload: dict,
    *,
    store_path: Optional[Path] = None,
    ticker_map_path: Optional[Path] = None,
    as_of: Optional[datetime] = None,
    root: Optional[Path] = None,
) -> dict:
    """Compute per-basket DOL hiring-intent velocity (separate display leg).

    CRITICAL FENCE: cert_velocity_z is SEPARATE from fused_obs_z and must
    NOT be folded into it.

    Parameters
    ----------
    baskets_payload :
        Same payload as theme_activity — must have ``baskets`` list with
        ``id`` + ``members`` list.
    store_path :
        Override the certs store path (useful for tests; env DOL_CERTS_STORE also works).
    ticker_map_path :
        Override the ticker map path (useful for tests).
    as_of :
        Reference datetime for the recent / prior windows.
    root :
        Repo root override (for tests).

    Returns
    -------
    dict
        ``{basket_id: {cert_velocity_z, ai_title_share, ...}}`` for every basket;
        empty dict when store is absent (honest null, no crash).
    """
    if root is None:
        root = _find_root()

    baskets = (baskets_payload or {}).get("baskets") or []
    if not baskets:
        return {}

    # Locate store
    store = _find_store(root, store_path)
    if store is None:
        log.info(
            "theme_hiring: DOL certs store absent — returning honest null for all baskets"
        )
        absent: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                absent[bid] = {
                    "cert_velocity_z": None,
                    "cert_count_recent": None,
                    "cert_count_prior": None,
                    "ai_title_share": None,
                    "median_wage_yoy": None,
                    "matched_employers": [],
                    "matched_tickers": [],
                    "n_matched_employers": 0,
                    "coverage_note": _COV_ABSENT_EN,
                    "coverage_note_zh": _COV_ABSENT_ZH,
                    "authority": AUTHORITY,
                }
        return absent

    certs_df = _load_certs(store)
    if certs_df is None or certs_df.empty:
        log.info("theme_hiring: DOL certs store present but empty — returning null")
        empty: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                empty[bid] = {
                    "cert_velocity_z": None,
                    "cert_count_recent": None,
                    "cert_count_prior": None,
                    "ai_title_share": None,
                    "median_wage_yoy": None,
                    "matched_employers": [],
                    "matched_tickers": [],
                    "n_matched_employers": 0,
                    "coverage_note": _COV_ABSENT_EN,
                    "coverage_note_zh": _COV_ABSENT_ZH,
                    "authority": AUTHORITY,
                }
        return empty

    # Resolve as_of
    if as_of is None:
        payload_asof = (baskets_payload or {}).get("as_of")
        if payload_asof:
            try:
                as_of = pd.Timestamp(payload_asof).to_pydatetime()
            except Exception:  # noqa: BLE001
                pass
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    as_of_ts = pd.Timestamp(as_of)
    if as_of_ts.tzinfo is not None:
        as_of_ts = as_of_ts.tz_convert(None)

    # Load ticker map
    if ticker_map_path is None:
        ticker_map_path = _find_ticker_map(root)
    ticker_rows = load_ticker_map(ticker_map_path) if ticker_map_path else []
    if not ticker_rows:
        log.info("theme_hiring: ticker map absent or empty — all matches null")

    # Pre-resolve all cert rows to tickers in one pass
    resolved = _pre_resolve_certs(certs_df, ticker_rows)
    log.debug("theme_hiring: pre-resolved %d cert rows", len(resolved))

    # Basket universe membership total (for match_rate)
    universe_size = sum(len(b.get("members", [])) for b in baskets)

    # Per-basket raw metrics
    raw: dict[str, dict] = {}
    for b in baskets:
        bid = b.get("id")
        if not bid:
            continue
        members = [m.get("symbol") for m in b.get("members", []) if m.get("symbol")]
        if not members:
            continue
        members_set = set(members)
        m = _basket_hiring_metric(members_set, resolved, as_of_ts)
        if m is not None:
            m["n_basket_members"] = len(members)
            raw[bid] = m

    if not raw:
        result: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                result[bid] = {
                    "cert_velocity_z": None,
                    "cert_count_recent": None,
                    "cert_count_prior": None,
                    "ai_title_share": None,
                    "median_wage_yoy": None,
                    "matched_employers": [],
                    "matched_tickers": [],
                    "n_matched_employers": 0,
                    "coverage_note": _COV_THIN_EN.format(n=MIN_MATCHES),
                    "coverage_note_zh": _COV_THIN_ZH,
                    "authority": AUTHORITY,
                }
        return result

    # Cross-sectional robust-z of velocity_metric
    bids = list(raw)
    metrics = [raw[bid]["velocity_metric"] for bid in bids]
    zs = _robust_z(metrics)
    z_by_bid = dict(zip(bids, zs))

    # Compute global match stats (for coverage)
    all_matched_tickers = set(
        t for r in raw.values() for t in r.get("matched_tickers", [])
    )
    n_matched_global = len(all_matched_tickers)
    match_rate = n_matched_global / universe_size if universe_size > 0 else 0.0

    # Assemble output
    out: dict = {}
    for b in baskets:
        bid = b.get("id")
        if not bid:
            continue
        if bid in raw:
            r = raw[bid]
            n_emp = r["n_matched_employers"]
            n_certs = r["cert_count_recent"]
            basket_match_rate = (
                n_emp / r["n_basket_members"] if r["n_basket_members"] > 0 else 0.0
            )
            cov_en = _COV_OK_EN.format(
                n_emp=n_emp, n_certs=n_certs, rate=basket_match_rate
            )
            cov_zh = _COV_OK_ZH.format(n_certs=n_certs)
            out[bid] = {
                "cert_velocity_z": round(z_by_bid[bid], 3),
                "cert_count_recent": r["cert_count_recent"],
                "cert_count_prior": r["cert_count_prior"],
                "ai_title_share": r["ai_title_share"],
                "median_wage_yoy": r["median_wage_yoy"],
                "matched_employers": r["matched_employers"],
                "matched_tickers": r["matched_tickers"],
                "n_matched_employers": n_emp,
                "coverage_note": cov_en,
                "coverage_note_zh": cov_zh,
                "authority": AUTHORITY,
            }
        else:
            out[bid] = {
                "cert_velocity_z": None,
                "cert_count_recent": None,
                "cert_count_prior": None,
                "ai_title_share": None,
                "median_wage_yoy": None,
                "matched_employers": [],
                "matched_tickers": [],
                "n_matched_employers": 0,
                "coverage_note": _COV_THIN_EN.format(n=MIN_MATCHES),
                "coverage_note_zh": _COV_THIN_ZH,
                "authority": AUTHORITY,
            }

    return out
